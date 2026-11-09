# -*- coding: utf-8 -*-
"""
Módulo de Valuación Intrínseca / Inversa (DCF & Excess Return), Grilla de Sensibilidad y Cotización en Tiempo Real.
Consume el cálculo unificado desde pipeline.valuation_engine.
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

    from valuation_engine import get_valuation_parameters, _generate_sensitivity_grid

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
        "is_financial": vp.get("is_financial", False),
        "stock_price": vp.get("price", 0.0),
        "fair_price_base": vp.get("fair_price_base", vp.get("price", 0.0)),
        "valuation_status": vp.get("valuation_status", "JUSTO"),
        "premium_pct": vp.get("premium_pct", 0.0),
        "g_implied_pct": vp.get("g_implied_pct", 0.0),
        "g_implied_3stage_pct": vp.get("g_implied_3stage_pct", vp.get("g_implied_pct", 0.0)),
        "g_implied_3stage_true_pct": vp.get("g_implied_3stage_true_pct", vp.get("g_implied_pct", 0.0)),
        "hist_growth_pct": vp.get("hist_growth_pct", 0.0),
        "init_growth_disp": vp.get("init_growth_disp", 0.0),
        "gap_expectations_str": vp.get("gap_expectations_str", "0.0 pp"),
        "rev_base": vp.get("rev_base", 0.0),
        "shares_m": round(vp.get("shares_b", 0.0) * 1000.0, 2),
        "fcf_margin_pct": vp.get("fcf_margin", 0.0) * 100.0,
        "fcf_margin_true_pct": vp.get("fcf_margin_true_pct", vp.get("fcf_margin", 0.0) * 100.0),
        "sbc_usd_m": vp.get("sbc_usd_m", 0.0),
        "sbc_margin_pct": vp.get("sbc_margin_pct", 0.0),
        "implied_cap_years": vp.get("implied_cap_years", 10.0),
        "net_debt_m": vp.get("net_debt_m", 0.0),
        "sensitivity_grid": sensitivity_grid,
        "vp": vp,
        "market_updated_at": market_updated_at,
        "is_live_price": (live_price is not None),
        "multiples_analysis": vp.get("multiples_analysis", {}),
        "epv_analysis": vp.get("epv_analysis", {}),
        "eva_analysis": vp.get("eva_analysis", {}),
        "forward_5y_analysis": vp.get("forward_5y_analysis", {}),
        "football_field": vp.get("football_field", {}),
        "dividend_yield_pct": vp.get("dividend_yield_pct", 0.0),
        "buyback_rate_pct": vp.get("buyback_rate_pct", 1.5),
        "cagr_eps_5y": vp.get("cagr_eps_5y"),
        "cagr_fcf_5y": vp.get("cagr_fcf_5y"),
        "historical_multiples": vp.get("historical_multiples", {}),
        "historical_multiples_json": json.dumps(vp.get("historical_multiples", {})),
        "owner_earnings_analysis": vp.get("owner_earnings_analysis", {}),
        "z_score_analysis": vp.get("z_score_analysis", {}),
        "audit_traceability": vp.get("audit_traceability", {}),
        "oe_margin_pct": vp.get("oe_margin_pct", 0.0),
        "g_implied_oe_pct": vp.get("g_implied_oe_pct", 0.0),
        "fair_price_oe": vp.get("fair_price_oe", vp.get("fair_price_base", 0.0)),
    }
