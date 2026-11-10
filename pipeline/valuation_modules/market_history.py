"""
market_history.py - Series históricas de precios reales, bandas Z-Score (EV / NOPAT),
múltiplos cronológicos multianuales y trazabilidad White-Box de auditoría.
"""

import json
import logging
from typing import Any, Dict, List, Optional, Tuple

try:
    from config_loader import resolve_market_cache_path
    from json_io import atomic_json_write
except ImportError:
    from pipeline.config_loader import resolve_market_cache_path
    from pipeline.json_io import atomic_json_write

logger = logging.getLogger(__name__)


def _latest_ltm_or_first(canon_dict: Optional[Dict[str, Any]]) -> Optional[float]:
    """Obtiene el valor LTM o el más reciente disponible en un diccionario canónico."""
    if not isinstance(canon_dict, dict) or not canon_dict:
        return None
    v = canon_dict.get("LTM")
    if v is not None:
        return float(v)
    for val in canon_dict.values():
        if val is not None:
            return float(val)
    return None


def _fetch_yf_history(ticker: str, period: str, interval: Optional[str] = None):
    """Descarga histórico de cierres vía yfinance con trazabilidad explícita ante fallos."""
    try:
        import yfinance as yf
        kwargs = {"period": period}
        if interval:
            kwargs["interval"] = interval
        hist = yf.Ticker(ticker).history(**kwargs)
        return hist if hist is not None and not hist.empty else None
    except Exception as exc:
        logger.debug("No se pudo obtener histórico yfinance (%s, %s): %s", ticker, period, exc)
        return None


def calculate_z_score_valuation(
    ticker: str,
    current_price: float,
    shares_m: float,
    net_debt_m: float,
    nopat_adj_m: float,
    is_financial: bool = False,
) -> Dict[str, Any]:
    """
    Calcula bandas Z-Score sobre EV / NOPAT Ajustado a partir de cierres trimestrales reales.
    Regla 6: si no existe histórico de precios reales, nunca fabrica cotizaciones sintéticas.
    """
    if is_financial or nopat_adj_m <= 0 or current_price <= 0 or shares_m <= 0:
        return {
            "z_score": None,
            "status": "N/D (Arquetipo Financiero o NOPAT <= 0)",
            "current_multiple": None,
            "mean_multiple": None,
            "std_multiple": None,
            "bands": {},
            "history": [],
        }

    cur_ev = (current_price * shares_m) + net_debt_m
    cur_multiple = round(cur_ev / nopat_adj_m, 1)

    cache_path = resolve_market_cache_path()
    cached_prices: Dict[str, float] = {}
    if cache_path.exists():
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                cached_prices = json.load(f).get(ticker, {}).get("historical_quarterly_prices", {})
        except (OSError, json.JSONDecodeError, TypeError) as exc:
            logger.debug("Error leyendo caché Z-Score para %s: %s", ticker, exc)

    dates: List[str] = []
    closes: List[float] = []
    if cached_prices:
        dates = list(cached_prices.keys())
        closes = [float(v) for v in cached_prices.values()]
    else:
        hist = _fetch_yf_history(ticker, period="5y", interval="3mo")
        if hist is not None:
            for dt, row in hist.iterrows():
                d_str = dt.strftime("%Y-%m")
                c_val = float(row["Close"])
                dates.append(d_str)
                closes.append(c_val)
                cached_prices[d_str] = round(c_val, 2)
            if cache_path.exists() and cached_prices:
                try:
                    with open(cache_path, "r", encoding="utf-8") as f:
                        c_all = json.load(f)
                    c_all.setdefault(ticker, {})["historical_quarterly_prices"] = cached_prices
                    atomic_json_write(cache_path, c_all, indent=2)
                except (OSError, json.JSONDecodeError, TypeError) as exc:
                    logger.debug("No se pudo persistir histórico trimestral en caché para %s: %s", ticker, exc)

    if not closes:
        return {
            "z_score": None,
            "current_multiple": cur_multiple,
            "mean_multiple": None,
            "std_multiple": None,
            "status": "N/D (Histórico de precios insuficiente)",
            "status_color": "slate",
            "bands": {},
            "history": [],
        }

    history = []
    multiples = []
    for dt, p in zip(dates, closes):
        m_t = round(((p * shares_m) + net_debt_m) / nopat_adj_m, 1)
        multiples.append(m_t)
        history.append({"date": dt, "price": round(p, 2), "multiple": m_t})

    import numpy as np

    mu = float(np.mean(multiples))
    sigma = float(np.std(multiples)) if len(multiples) > 1 else 3.5
    z_score = round((cur_multiple - mu) / sigma, 2) if sigma > 0 else 0.0

    bands = {
        "minus_2sigma": round(max(0.0, mu - 2.0 * sigma), 1),
        "minus_1sigma": round(max(0.0, mu - 1.0 * sigma), 1),
        "mean": round(mu, 1),
        "plus_1sigma": round(mu + 1.0 * sigma, 1),
        "plus_2sigma": round(mu + 2.0 * sigma, 1),
    }
    if z_score <= -1.5:
        status, status_color = "COMPRA FUERTE / SUELO HISTÓRICO", "emerald"
    elif z_score <= 1.0:
        status, status_color = "VALORACIÓN NORMAL / RAZONABLE", "sky"
    elif z_score < 2.0:
        status, status_color = "RANGO ALTO HISTÓRICO", "amber"
    else:
        status, status_color = "EUFORIA / SOBRECOMPRA EXTREMA", "rose"

    return {
        "z_score": z_score,
        "current_multiple": cur_multiple,
        "mean_multiple": round(mu, 1),
        "std_multiple": round(sigma, 1),
        "status": status,
        "status_color": status_color,
        "bands": bands,
        "history": history[-12:],
    }


def _lookup_fy_close_price(hist_df: Any, fy: str, f_month: str) -> Optional[float]:
    """Busca el último cierre real disponible hasta el mes de cierre fiscal del año FY."""
    if hist_df is None or hist_df.empty:
        return None
    yr = fy.replace("FY", "")
    try:
        sub = hist_df.loc[: f"{yr}-{f_month}-28"]
        if not sub.empty:
            return float(sub.iloc[-1]["Close"])
    except Exception as exc:
        logger.debug("Sin precio histórico para %s (%s): %s", fy, f_month, exc)
    return None


def _compute_financial_hist_series(
    selected_fys: List[str],
    hist_df: Any,
    f_month: str,
    canon: Dict[str, Any],
    current_price: float,
    current_shares_m: float,
    tbv_per_share: float,
) -> Tuple[Dict[str, List[Optional[float]]], List[str], List[Optional[float]], List[Dict[str, Any]]]:
    """Construye la serie histórica de múltiplos P/TBV, P/E y P/Sales para entidades financieras."""
    series_data: Dict[str, List[Optional[float]]] = {"p_tbv": [], "pe_gaap": [], "p_sales": []}
    actual_periods: List[str] = []
    prices_list: List[Optional[float]] = []
    annual_table: List[Dict[str, Any]] = []

    for fy in selected_fys:
        p_val = _lookup_fy_close_price(hist_df, fy, f_month)
        sh_raw = canon.get("shares_diluted_adjusted", {}).get(fy)
        sh_m = (float(sh_raw) / 1e6) if sh_raw is not None else current_shares_m
        mc_m = (p_val * sh_m) if (p_val is not None and p_val > 0 and sh_m > 0) else None
        eq_m = (float(canon.get("stockholders_equity", {}).get(fy)) / 1e6) if canon.get("stockholders_equity", {}).get(fy) is not None else 0.0
        ni_m = (float(canon.get("net_income", {}).get(fy)) / 1e6) if canon.get("net_income", {}).get(fy) is not None else 0.0
        r_m = (float(canon.get("revenue", {}).get(fy)) / 1e6) if canon.get("revenue", {}).get(fy) is not None else 0.0

        v_ptbv = round(mc_m / eq_m, 2) if (mc_m and eq_m > 0) else None
        v_pe = round(mc_m / ni_m, 1) if (mc_m and ni_m > 0) else None
        v_ps = round(mc_m / r_m, 1) if (mc_m and r_m > 0) else None
        p_rounded = round(p_val, 2) if p_val is not None else None

        actual_periods.append(fy)
        prices_list.append(p_rounded)
        series_data["p_tbv"].append(v_ptbv)
        series_data["pe_gaap"].append(v_pe)
        series_data["p_sales"].append(v_ps)
        annual_table.append({"period": fy, "price": p_rounded, "p_tbv": v_ptbv, "pe_gaap": v_pe, "p_sales": v_ps})

    cur_mc = current_price * current_shares_m if (current_price > 0 and current_shares_m > 0) else 0.0
    cur_ni_m = (_latest_ltm_or_first(canon.get("net_income")) or 0.0) / 1e6
    cur_rev_m = (_latest_ltm_or_first(canon.get("revenue")) or 0.0) / 1e6

    v_ltm_ptbv = round(current_price / tbv_per_share, 2) if (tbv_per_share > 0 and current_price > 0) else None
    v_ltm_pe = round(cur_mc / cur_ni_m, 1) if (cur_mc > 0 and cur_ni_m > 0) else None
    v_ltm_ps = round(cur_mc / cur_rev_m, 1) if (cur_mc > 0 and cur_rev_m > 0) else None
    cur_p = round(current_price, 2) if current_price > 0 else None

    actual_periods.append("LTM")
    prices_list.append(cur_p)
    series_data["p_tbv"].append(v_ltm_ptbv)
    series_data["pe_gaap"].append(v_ltm_pe)
    series_data["p_sales"].append(v_ltm_ps)
    annual_table.append({"period": "LTM", "price": cur_p, "p_tbv": v_ltm_ptbv, "pe_gaap": v_ltm_pe, "p_sales": v_ltm_ps})
    return series_data, actual_periods, prices_list, annual_table


def _compute_corporate_hist_series(
    selected_fys: List[str],
    hist_df: Any,
    f_month: str,
    canon: Dict[str, Any],
    scoring_data: Optional[Dict[str, Any]],
    current_price: float,
    current_shares_m: float,
    current_net_debt_m: float,
    current_nopat_adj_m: float,
    current_oe_m: float,
) -> Tuple[Dict[str, List[Optional[float]]], List[str], List[Optional[float]], List[Dict[str, Any]]]:
    """Construye la serie histórica de múltiplos operativos/EV para emisoras no financieras."""
    ira = (scoring_data or {}).get("intangible_roic_analysis", {}).get("by_period", {})
    series_data: Dict[str, List[Optional[float]]] = {
        k: [] for k in ("ev_nopat_adj", "p_oe", "pe_gaap", "ev_ebit", "ev_ebitda", "ev_fcf", "ev_sales")
    }
    actual_periods: List[str] = []
    prices_list: List[Optional[float]] = []
    annual_table: List[Dict[str, Any]] = []

    for fy in selected_fys:
        p_val = _lookup_fy_close_price(hist_df, fy, f_month)
        sh_raw = canon.get("shares_diluted_adjusted", {}).get(fy)
        sh_m = (float(sh_raw) / 1e6) if sh_raw is not None else current_shares_m
        mc_m = (p_val * sh_m) if (p_val is not None and p_val > 0 and sh_m > 0) else None
        tot_d_m = (float(canon.get("total_debt", {}).get(fy)) / 1e6) if canon.get("total_debt", {}).get(fy) is not None else 0.0
        c_eq_m = (float(canon.get("cash_and_equivalents", {}).get(fy)) / 1e6) if canon.get("cash_and_equivalents", {}).get(fy) is not None else 0.0
        st_inv_m = (float(canon.get("short_term_investments", {}).get(fy)) / 1e6) if canon.get("short_term_investments", {}).get(fy) is not None else 0.0
        ev_m = (mc_m + (tot_d_m - (c_eq_m + st_inv_m))) if mc_m is not None else None

        nopat_adj = float(ira.get(fy, {}).get("nopat_adj") or 0.0)
        ni_m = (float(canon.get("net_income", {}).get(fy)) / 1e6) if canon.get("net_income", {}).get(fy) is not None else 0.0
        fcf_m = (float(canon.get("free_cash_flow", {}).get(fy)) / 1e6) if canon.get("free_cash_flow", {}).get(fy) is not None else 0.0
        r_m = (float(canon.get("revenue", {}).get(fy)) / 1e6) if canon.get("revenue", {}).get(fy) is not None else 0.0
        op_inc_raw = canon.get("operating_income", {}).get(fy)
        if op_inc_raw is None:
            op_inc_raw = canon.get("ebit", {}).get(fy)
        ebit_m = (float(op_inc_raw) / 1e6) if op_inc_raw is not None else 0.0

        capex_raw = canon.get("capital_expenditures", {}).get(fy)
        capex_m = (abs(float(capex_raw)) / 1e6) if capex_raw is not None else 0.0
        dna_raw = canon.get("depreciation_amortization", {}).get(fy)
        dna_m = (float(dna_raw) / 1e6) if dna_raw is not None else (capex_m * 0.70)
        ebitda_m = ebit_m + dna_m

        maint_c = min(capex_m, dna_m * 0.90)
        growth_c = max(0.0, capex_m - maint_c)
        rd_exp = float(ira.get(fy, {}).get("rd_investment") or 0.0)
        rd_amort = float(ira.get(fy, {}).get("rd_amortization") or (rd_exp * 0.85))
        oe_m = fcf_m + growth_c + max(0.0, rd_exp - rd_amort)

        row_m = {
            "ev_nopat_adj": round(ev_m / nopat_adj, 1) if (ev_m and ev_m > 0 and nopat_adj > 0) else None,
            "p_oe": round(mc_m / oe_m, 1) if (mc_m and mc_m > 0 and oe_m > 0) else None,
            "pe_gaap": round(mc_m / ni_m, 1) if (mc_m and mc_m > 0 and ni_m > 0) else None,
            "ev_ebit": round(ev_m / ebit_m, 1) if (ev_m and ev_m > 0 and ebit_m > 0) else None,
            "ev_ebitda": round(ev_m / ebitda_m, 1) if (ev_m and ev_m > 0 and ebitda_m > 0) else None,
            "ev_fcf": round(ev_m / fcf_m, 1) if (ev_m and ev_m > 0 and fcf_m > 0) else None,
            "ev_sales": round(ev_m / r_m, 1) if (ev_m and ev_m > 0 and r_m > 0) else None,
        }
        p_rounded = round(p_val, 2) if p_val is not None else None
        actual_periods.append(fy)
        prices_list.append(p_rounded)
        for mk, mv in row_m.items():
            series_data[mk].append(mv)
        annual_table.append({"period": fy, "price": p_rounded, **row_m})

    cur_mc = current_price * current_shares_m if (current_price > 0 and current_shares_m > 0) else 0.0
    cur_ev = (cur_mc + current_net_debt_m) if cur_mc > 0 else 0.0
    cur_ni_m = (_latest_ltm_or_first(canon.get("net_income")) or 0.0) / 1e6
    cur_fcf_m = (_latest_ltm_or_first(canon.get("free_cash_flow")) or 0.0) / 1e6
    cur_rev_m = (_latest_ltm_or_first(canon.get("revenue")) or 0.0) / 1e6
    cur_oe = current_oe_m if current_oe_m > 0 else (cur_fcf_m * 1.08)
    cur_ebit_m = (_latest_ltm_or_first(canon.get("operating_income")) or 0.0) / 1e6
    cur_dna_m = (_latest_ltm_or_first(canon.get("depreciation_amortization")) or 0.0) / 1e6
    if cur_dna_m <= 0:
        cur_capex_m = abs(_latest_ltm_or_first(canon.get("capital_expenditures")) or 0.0) / 1e6
        cur_dna_m = cur_capex_m * 0.70
    cur_ebitda_m = cur_ebit_m + cur_dna_m

    ltm_m = {
        "ev_nopat_adj": round(cur_ev / current_nopat_adj_m, 1) if (cur_ev > 0 and current_nopat_adj_m > 0) else None,
        "p_oe": round(cur_mc / cur_oe, 1) if (cur_mc > 0 and cur_oe > 0) else None,
        "pe_gaap": round(cur_mc / cur_ni_m, 1) if (cur_mc > 0 and cur_ni_m > 0) else None,
        "ev_ebit": round(cur_ev / cur_ebit_m, 1) if (cur_ev > 0 and cur_ebit_m > 0) else None,
        "ev_ebitda": round(cur_ev / cur_ebitda_m, 1) if (cur_ev > 0 and cur_ebitda_m > 0) else None,
        "ev_fcf": round(cur_ev / cur_fcf_m, 1) if (cur_ev > 0 and cur_fcf_m > 0) else None,
        "ev_sales": round(cur_ev / cur_rev_m, 1) if (cur_ev > 0 and cur_rev_m > 0) else None,
    }
    cur_p = round(current_price, 2) if current_price > 0 else None
    actual_periods.append("LTM")
    prices_list.append(cur_p)
    for mk, mv in ltm_m.items():
        series_data[mk].append(mv)
    annual_table.append({"period": "LTM", "price": cur_p, **ltm_m})
    return series_data, actual_periods, prices_list, annual_table


def calculate_historical_multiples_analysis(
    ticker: str,
    current_price: float,
    current_shares_m: float,
    current_net_debt_m: float,
    current_nopat_adj_m: float,
    current_oe_m: float,
    fs_obj: Optional[Dict[str, Any]] = None,
    scoring_data: Optional[Dict[str, Any]] = None,
    is_financial: bool = False,
    tbv_per_share: float = 0.0,
) -> Dict[str, Any]:
    """
    Calcula la serie cronológica multianual de múltiplos usando exclusivamente cierres reales
    de ejercicios fiscales previos y LTM (sin fabricar cotizaciones ficticias 0.85x).
    """
    import numpy as np

    canon = (fs_obj or {}).get("canonical_summary", {})
    sec_meta = (fs_obj or {}).get("sec_metadata", {})
    ltm_date = sec_meta.get("ltm_period_end", "2026-09-30")
    f_month = ltm_date.split("-")[1] if "-" in ltm_date else "12"

    rev_map = canon.get("revenue", {}) or canon.get("net_income", {})
    fys = sorted(
        [k for k in rev_map.keys() if k.startswith("FY") and rev_map[k]],
        key=lambda x: int(x.replace("FY", "")) if x.replace("FY", "").isdigit() else 0,
    )
    selected_fys = fys[-5:] if len(fys) >= 5 else fys
    hist_df = _fetch_yf_history(ticker, period="8y") if (selected_fys and current_price > 0) else None

    if is_financial:
        series_data, actual_periods, prices_list, annual_table = _compute_financial_hist_series(
            selected_fys, hist_df, f_month, canon, current_price, current_shares_m, tbv_per_share
        )
    else:
        series_data, actual_periods, prices_list, annual_table = _compute_corporate_hist_series(
            selected_fys,
            hist_df,
            f_month,
            canon,
            scoring_data,
            current_price,
            current_shares_m,
            current_net_debt_m,
            current_nopat_adj_m,
            current_oe_m,
        )

    stats: Dict[str, Any] = {}
    for m_key, vals in series_data.items():
        clean_vals = [v for v in vals if v is not None and v > 0]
        if not clean_vals:
            continue
        cur_v = vals[-1]
        hist_vals = clean_vals[:-1] if len(clean_vals) > 1 else clean_vals
        med = round(float(np.median(hist_vals)), 1)
        mean_v = round(float(np.mean(hist_vals)), 1)
        min_v = round(float(np.min(clean_vals)), 1)
        max_v = round(float(np.max(clean_vals)), 1)
        if cur_v and med > 0:
            diff = round(((cur_v - med) / med) * 100.0, 1)
            if diff > 15.0:
                status, status_color = f"Sobrevalorado (+{diff:.1f}% vs Mediana)", "rose"
            elif diff < -15.0:
                status, status_color = f"Descuento ({diff:.1f}% vs Mediana)", "emerald"
            else:
                status, status_color = f"Rango Histórico Equilibrado ({diff:+.1f}% vs Mediana)", "sky"
            imputed_price = round(current_price * (med / cur_v), 2)
        else:
            diff, status, status_color, imputed_price = None, "N/D (LTM No Disponible o Pérdidas)", "slate", current_price

        stats[m_key] = {
            "current": cur_v,
            "median": med,
            "mean": mean_v,
            "min": min_v,
            "max": max_v,
            "diff_pct": diff,
            "status": status,
            "status_color": status_color,
            "imputed_price": imputed_price,
        }

    return {
        "is_financial": is_financial,
        "periods": actual_periods,
        "prices": prices_list,
        "series": series_data,
        "stats": stats,
        "annual_table": annual_table,
    }


def build_audit_traceability(
    ticker: str,
    ebit_reported_m: float,
    rd_expense_m: float,
    rd_amortization_m: float,
    ebit_adjusted_m: float,
    tax_rate_pct: float,
    nopat_adjusted_m: float,
    cfo_m: float,
    capex_total_m: float,
    maint_capex_m: float,
    growth_capex_m: float,
    net_rd_inv_m: float,
    fcf_reported_m: float,
    owner_earnings_m: float,
    shares_m: float,
    stock_price: float,
    net_debt_m: float,
    wacc_pct: float,
    gn_pct: float,
    rd_stock_m: float,
    roic_trad_pct: float,
    roic_adj_pct: float,
    spread_pct: float,
    z_score_obj: Dict[str, Any],
    by_period_history: Optional[List[Dict[str, Any]]] = None,
    is_financial: bool = False,
    g_implied_oe_pct: Optional[float] = None,
) -> Dict[str, Any]:
    """Construye la trazabilidad matemática White-Box (NOPAT, CapEx, ROIC, Reverse DCF)."""
    if is_financial:
        return {
            "is_financial": True,
            "dictum": "Arquetipo Financiero: Se audita mediante Tangible Book Value y ROTCE Sostenible.",
            "steps_nopat": [],
            "steps_capex": [],
            "multiyear_table": [],
        }

    g_oe_val = g_implied_oe_pct if g_implied_oe_pct is not None else float(z_score_obj.get("g_implied_oe_pct", 0.0) or 0.0)
    ev_b = round((shares_m * stock_price + net_debt_m) / 1000.0, 1)
    return {
        "is_financial": False,
        "steps_nopat": [
            {"item": "Beneficio Operativo (EBIT) Reportado", "val": f"${ebit_reported_m:,.1f}M", "note": "Income Statement (Operating Income)"},
            {"item": "(+) Gasto en I+D Revertido", "val": f"+${rd_expense_m:,.1f}M", "note": "I+D del ejercicio tratada como inversión capitalizable"},
            {"item": "(−) Amortización Económica de I+D", "val": f"-${rd_amortization_m:,.1f}M", "note": "Amortización lineal de los últimos 3 a 5 años"},
            {"item": "(=) EBIT Económico Ajustado", "val": f"${ebit_adjusted_m:,.1f}M", "note": "EBIT depurado de distorsiones contables"},
            {"item": "(×) Factor Impositivo Efectivo (1 − Tax)", "val": f"{100.0 - tax_rate_pct:.1f}%", "note": f"Tasa impositiva real del ejercicio: {tax_rate_pct:.1f}%"},
            {"item": "(=) NOPAT Ajustado por Intangibles", "val": f"${nopat_adjusted_m:,.1f}M", "note": "Cifra base depurada para el modelo de valoración"},
        ],
        "steps_capex": [
            {"item": "Flujo de Caja Operativo (CFO)", "val": f"${cfo_m:,.1f}M", "note": "Cash Flow Statement (CFO Auditado)"},
            {"item": "(−) CapEx Total Reportado", "val": f"-${capex_total_m:,.1f}M", "note": "Deducción contable tradicional de 1930"},
            {"item": "(=) Flujo de Caja Libre (FCF) Reportado", "val": f"${fcf_reported_m:,.1f}M", "note": "CFO − CapEx Total"},
            {"item": "(+) CapEx de Crecimiento (Expansión)", "val": f"+${growth_capex_m:,.1f}M", "note": f"CapEx Total menos Mantenimiento (${maint_capex_m:,.1f}M)"},
            {"item": "(+) Inversión Neta en I+D Económica", "val": f"+${net_rd_inv_m:,.1f}M", "note": "Gasto I+D menos Amortización del periodo"},
            {"item": "(=) Beneficios del Propietario (Owner Earnings)", "val": f"${owner_earnings_m:,.1f}M", "note": "Caja real extraíble sin reducir la escala competitiva"},
        ],
        "math_formulas": {
            "nopat": {
                "title": "1. Capitalización de I+D y Reconstrucción del NOPAT Ajustado",
                "latex_formula": r"\text{NOPAT}_{adj} = \left[ \text{EBIT}_{\text{Reportado}} + \text{Gasto I+D}_t - \text{Amortización I+D}_t \right] \times (1 - \text{Tax Rate})",
                "latex_substituted": rf"\text{{NOPAT}}_{{adj}} = \left[ \${ebit_reported_m:,.1f}\text{{M}} + \${rd_expense_m:,.1f}\text{{M}} - \${rd_amortization_m:,.1f}\text{{M}} \right] \times \left(1 - {tax_rate_pct/100.0:.2f}\right) = \mathbf{{\${nopat_adjusted_m:,.1f}\text{{M}}}}",
                "explanation": "El gasto en I+D genera valor duradero multi-ejercicio. Se capitaliza y amortiza linealmente a 5 años, eliminando el castigo contable tradicional y descubriendo el verdadero NOPAT operativo.",
            },
            "owner_earnings": {
                "title": "2. Beneficios del Propietario (Owner Earnings - Buffett/Greenwald)",
                "latex_formula": r"\text{Owner Earnings} = \text{FCF}_{\text{Reportado}} + \text{CapEx Crecimiento} + \text{Inversión Neta I+D}",
                "latex_substituted": rf"\text{{Owner Earnings}} = \${fcf_reported_m:,.1f}\text{{M}} + \${growth_capex_m:,.1f}\text{{M}} + \${net_rd_inv_m:,.1f}\text{{M}} = \mathbf{{\${owner_earnings_m:,.1f}\text{{M}}}}",
                "explanation": "El CapEx reportado se divide en mantenimiento (≈ D&A) y crecimiento discrecional. Al reintegrar el CapEx de expansión y la inversión neta de I+D, se revela el flujo de caja económico real.",
            },
            "roic": {
                "title": "3. ROIC Ajustado por Intangibles & Economic Spread (Stern Stewart)",
                "latex_formula": r"\text{ROIC}_{adj} = \frac{\text{NOPAT}_{adj}}{\text{Capital Invertido Tangible} + \text{Activo I+D}} \quad\Big|\quad \text{Spread} = \text{ROIC}_{adj} - \text{WACC}",
                "latex_substituted": rf"\text{{ROIC}}_{{adj}} = \mathbf{{{roic_adj_pct:.1f}\%}} \quad\Big|\quad \text{{Spread}} = {roic_adj_pct:.1f}\% - {wacc_pct:.1f}\% = \mathbf{{+{spread_pct:.1f}\text{{ pp}}}}",
                "explanation": "Incorporar el activo intangible acumulado de I+D en el denominador evita inflar el retorno sobre capital. Un spread económico durable confirma la presencia de un foso competitivo (Moat).",
            },
            "reverse_dcf": {
                "title": "4. Reverse DCF Económico (Despeje de Crecimiento Implícito)",
                "latex_formula": r"\text{EV}_{\text{Mercado}} = \sum_{t=1}^{10} \frac{\text{Owner Earnings}_0 \times (1 + g)^t}{(1 + \text{WACC})^t} + \frac{\text{TV}_{10}}{(1 + \text{WACC})^{10}} \implies \text{Resolver } g",
                "latex_substituted": rf"\text{{EV}} = \${ev_b:,.1f}\text{{B}} \quad\Big|\quad \text{{WACC}} = {wacc_pct:.1f}\% \implies g_{{\text{{implícito}}}} = \mathbf{{{g_oe_val:.1f}\%}}",
                "explanation": "En lugar de realizar proyecciones subjetivas, el algoritmo despeja numéricamente qué tasa de crecimiento compuesto exige la cotización actual a 10 años.",
            },
        },
        "rd_stock_m": rd_stock_m,
        "roic_trad_pct": roic_trad_pct,
        "roic_adj_pct": roic_adj_pct,
        "spread_pct": spread_pct,
        "wacc_pct": wacc_pct,
        "gn_pct": gn_pct,
        "z_score_val": z_score_obj.get("z_score"),
        "z_score_status": z_score_obj.get("status"),
        "multiyear_table": by_period_history or [],
    }
