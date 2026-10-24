# -*- coding: utf-8 -*-
"""
Módulo de Valuación Intrínseca / Inversa (DCF & Excess Return), Grilla de Sensibilidad y Cotización en Tiempo Real.
"""
import json


def build_valuation_context(
    request,
    DATA_DIR,
    ticker,
    scores,
    fs,
    statements_fys,
    canonical,
    archetype,
    is_banking,
):
    """Construye los parámetros de valuación DCF / Excess Return, matriz de sensibilidad 5x6 y advertencias de datos."""
    # Datos de Mercado en Vivo & Modelo DCF Intrínseco / Inverso (Consumido de valuation_report_builder)
    # -------------------------------------------------------------------------------------------------
    prof_data = {}
    prof_path = DATA_DIR / ticker / "company_profile.json"
    if prof_path.exists():
        try:
            with open(prof_path, "r", encoding="utf-8") as pf:
                prof_data = json.load(pf)
        except Exception:
            pass

    # Extracción de Mercado en Vivo (con soporte para bypass_cache si ?refresh=1)
    force_refresh = (request.GET.get("refresh") == "1")
    live_price = None
    market_updated_at = None
    try:
        from market_data_provider import MarketDataExtractor
        m_live = MarketDataExtractor.get_market_data(ticker, bypass_cache=force_refresh)
        live_price = m_live.get("price")
        market_updated_at = m_live.get("cached_at") or m_live.get("timestamp")
    except Exception:
        pass

    from valuation_report_builder import get_valuation_parameters, _generate_sensitivity_grid

    vp = get_valuation_parameters(scores, ticker=ticker, profile_data=prof_data, live_price=live_price, fs_data=fs)
    raw_grid = _generate_sensitivity_grid(vp)
    
    # Formatear la matriz 5x6 para la plantilla Django
    sensitivity_grid = []
    for idx, row in enumerate(raw_grid):
        sensitivity_grid.append({
            "wacc_label": row[0],
            "g_10": row[1],
            "g_15": row[2],
            "g_20": row[3],
            "g_25": row[4],
            "g_30": row[5],
            "g_35": row[6],
            "diagnosis": row[7],
            "is_base": (idx == 2)
        })

    is_financial = vp.get("is_financial", False)
    stock_price = vp.get("price", 0.0)
    shares_m = round(vp.get("shares_b", 0.0) * 1000.0, 2)

    if is_financial:
        rev_base = vp.get("tangible_equity_m", 0.0)
        fcf_margin = 0.0
        fcf_margin_pct = 0.0
        net_debt_m = 0.0
        hist_growth_pct = float(vp.get("cagr_5y") or 0.0)
        hist_growth = hist_growth_pct / 100.0
        wacc_dec = vp.get("ke_val", 0.0943)
        gn_dec = (vp.get("g_terminal_pct", 3.5)) / 100.0
        fair_price_base = vp.get("fair_value_excess_return", stock_price)
        g_implied = (vp.get("rotce_implied_pct", 0.0)) / 100.0
        gap_exp = (g_implied - (vp.get("rotce_val", 0.264))) * 100.0
    else:
        rev_base = vp.get("base_rev_m", 0.0)
        fcf_margin = vp.get("fcf_margin", 0.0)
        fcf_margin_pct = vp.get("fcf_margin_pct", 0.0)
        net_debt_m = vp.get("net_debt_m", 0.0)
        hist_growth_pct = float(vp.get("cagr_5y") or 0.0)
        hist_growth = hist_growth_pct / 100.0
        wacc_dec = vp.get("wacc_val", 0.095)
        gn_dec = 0.025

        # Cálculo del Valor Intrínseco Teórico (DCF a 10 años con Gordon-Shapiro)
        # Para evitar distorsiones hiperbólicas de extrapolación a 10 años en empresas de hipercrecimiento (ej. MELI 48.7%, NVDA 66.9%),
        # la hipótesis inicial de partida se normaliza a una tasa sostenible de proyección (máx 20.0%),
        # preservando el CAGR histórico 5Y íntegro como referencia en pantalla y permitiendo ajuste total en los deslizadores.
        init_proj_growth = min(hist_growth, 0.20) if hist_growth > 0.20 else max(hist_growth, -0.05)
        pv_fcf = 0.0
        r_t = rev_base
        for t in range(1, 11):
            r_t *= (1.0 + init_proj_growth)
            pv_fcf += (r_t * fcf_margin) / ((1.0 + wacc_dec) ** t)
        tv = (r_t * (1.0 + gn_dec) * fcf_margin) / max(wacc_dec - gn_dec, 0.005)
        pv_tv = tv / ((1.0 + wacc_dec) ** 10)
        ev_total = pv_fcf + pv_tv
        equity_val = ev_total - net_debt_m
        fair_price_base = equity_val / shares_m if shares_m > 0 else stock_price

        g_implied = vp.get("g_implied_our_pct", 0.0) / 100.0
        gap_exp = (g_implied - init_proj_growth) * 100.0

    init_growth_disp = (vp.get("rotce_pct") or 0.0) if is_financial else (init_proj_growth * 100.0)
    gap_expectations_str = f"{'+' if gap_exp >= 0 else ''}{gap_exp:.1f} pp"

    premium_pct = ((stock_price - fair_price_base) / fair_price_base) * 100.0 if fair_price_base > 0 else 0.0
    if premium_pct > 25.0:
        valuation_status = "SOBREVALORADA"
    elif premium_pct < -15.0:
        valuation_status = "INFRAVALORADA"
    else:
        valuation_status = "JUSTO"

    data_warnings = []
    if "LTM" not in statements_fys:
        data_warnings.append("Período LTM no reportado de forma desglosada en los reportes interinos SEC (10-Q/6-K). Se visualizan exclusivamente los ejercicios fiscales anuales cerrados.")
    else:
        if not is_banking and archetype not in ("FINANCIAL_BANKING", "INSURANCE"):
            ltm_capex = canonical.get("capital_expenditures", {}).get("LTM")
            ltm_cfo = canonical.get("cash_from_operations", {}).get("LTM")
            if ltm_capex is None:
                data_warnings.append("CapEx LTM no desglosado en el último informe trimestral 10-Q. El Flujo de Caja Libre (FCF) LTM se presenta como '-' para evitar distorsiones con el ejercicio anterior.")
            elif ltm_cfo is None:
                data_warnings.append("Flujo de Caja Operativo (CFO) LTM no disponible. Los flujos y márgenes derivados reflejan '-'.")
        elif archetype == "FINANCIAL_BANKING":
            ltm_nii = canonical.get("net_interest_income", {}).get("LTM")
            if ltm_nii is None:
                data_warnings.append("Margen de Intereses Neto (NII) LTM no desglosado en el informe trimestral. Ratios interinos derivados reflejan '-'.")

    if vp and vp.get("guidance_mid") is None:
        data_warnings.append("La empresa no ha emitido guidance cuantitativo oficial para el ejercicio en curso. La proyección del simulador utiliza el CAGR histórico como referencia inicial.")


    return {
        "data_warnings": data_warnings,
        "is_financial": is_financial,
        "stock_price": stock_price,
        "fair_price_base": fair_price_base,
        "valuation_status": valuation_status,
        "premium_pct": premium_pct,
        "g_implied_pct": g_implied * 100.0,
        "hist_growth_pct": hist_growth * 100.0,
        "init_growth_disp": init_growth_disp,
        "gap_expectations_str": gap_expectations_str,
        "rev_base": rev_base,
        "shares_m": shares_m,
        "fcf_margin_pct": fcf_margin * 100.0,
        "net_debt_m": net_debt_m,
        "sensitivity_grid": sensitivity_grid,
        "vp": vp,
        "market_updated_at": market_updated_at,
        "is_live_price": (live_price is not None),
    }
