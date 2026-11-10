"""
dcf_models.py - Modelos matemáticos de valoración intrínseca e inversa:
Reverse DCF (2 y 3 etapas), Excess Return P/TBV vs ROTCE, EPV/PVGO, EVA,
5Y Forward IRR, Múltiplos comparables, Owner Earnings y Valuation Football Field.
"""

import re
from typing import Any, Dict, List, Optional


def _fmt_money(val: Any, default: str = "N/D", prefix: str = "$", suffix: str = "") -> str:
    """Formatea valores monetarios a cadena amigable."""
    if val is None or val == "" or str(val).upper() == "N/D":
        return default
    try:
        return f"{prefix}{float(val):,.1f}{suffix}"
    except (ValueError, TypeError):
        return default


def _fmt_pct(val: Any, default: str = "N/D") -> str:
    """Formatea ratios y tasas a porcentaje legible."""
    if val is None or val == "" or str(val).upper() == "N/D":
        return default
    try:
        fval = float(val)
        return f"{fval * 100.0:.2f}%" if abs(fval) <= 1.0 and fval != 0.0 else f"{fval:.2f}%"
    except (ValueError, TypeError):
        return default


def _compute_series_cagr(val_map: Optional[Dict[str, Any]], years: int = 5) -> Optional[float]:
    """Calcula el CAGR histórico entre los últimos N períodos fiscales cerrados (FY)."""
    if not val_map or not isinstance(val_map, dict):
        return None
    fy_keys = sorted(
        [k for k, v in val_map.items() if k.startswith("FY") and v is not None and float(v) > 0],
        key=lambda x: int(re.search(r"(\d{4})", x).group(1)) if re.search(r"(\d{4})", x) else 0,
    )
    if len(fy_keys) >= (years + 1):
        v_now, v_prev = float(val_map[fy_keys[-1]]), float(val_map[fy_keys[-(years + 1)]])
        if v_prev > 0 and v_now > 0:
            return round((((v_now / v_prev) ** (1.0 / float(years))) - 1.0) * 100.0, 1)
    elif len(fy_keys) >= 2:
        n = len(fy_keys) - 1
        v_now, v_prev = float(val_map[fy_keys[-1]]), float(val_map[fy_keys[0]])
        if v_prev > 0 and v_now > 0:
            return round((((v_now / v_prev) ** (1.0 / float(n))) - 1.0) * 100.0, 1)
    return None


def _compute_share_reduction_rate(shares_map: Optional[Dict[str, Any]], years: int = 5) -> float:
    """Calcula la tasa anualizada de reducción neta de acciones diluidas (0.0 si no hay histórico)."""
    cagr = _compute_series_cagr(shares_map, years=years)
    return -round(cagr, 2) if cagr is not None else 0.0


def compute_two_stage_excess_return_ptbv(
    rotce_val: float,
    ke_val: float,
    g_term: float = 0.030,
    cagr_5y: Optional[float] = None,
    is_insurance: bool = False,
    fade_years: int = 5,
) -> float:
    """Calcula el múltiplo P/TBV justificado mediante Modelo de Retorno Excedente de 2 etapas."""
    if ke_val <= g_term or rotce_val <= 0:
        return 1.0

    if is_insurance:
        r_terminal = min(rotce_val, ke_val + 0.105) if rotce_val > (ke_val + 0.105) else rotce_val
        retention = 0.45
    else:
        is_high_growth_bank = cagr_5y is not None and cagr_5y >= 25.0
        spread_cap = 0.145 if is_high_growth_bank else 0.105
        r_terminal = min(rotce_val, ke_val + spread_cap) if rotce_val > (ke_val + spread_cap) else rotce_val
        retention = 0.72 if is_high_growth_bank else 0.40

    bv_t = 1.0
    pv_excess_stage1 = 0.0
    for t in range(1, fade_years + 1):
        weight = float(t) / float(fade_years)
        r_t = rotce_val * (1.0 - weight) + r_terminal * weight
        pv_excess_stage1 += ((r_t - ke_val) * bv_t) / ((1.0 + ke_val) ** t)
        g_bv_t = min(0.22, max(g_term, r_t * retention))
        bv_t *= 1.0 + g_bv_t

    terminal_excess_multiple = (r_terminal - ke_val) / (ke_val - g_term)
    pv_terminal_excess = (terminal_excess_multiple * bv_t) / ((1.0 + ke_val) ** fade_years)
    return round(max(0.5, 1.0 + pv_excess_stage1 + pv_terminal_excess), 2)


def solve_reverse_dcf(
    share_price: float,
    shares_out_b: float,
    net_debt_m: float,
    base_revenue_m: float,
    wacc: float,
    terminal_growth: float = 0.025,
    fcf_margin: float = 0.252,
    forecast_years: int = 10,
) -> float:
    """Resuelve numéricamente la tasa anual implícita de crecimiento de ventas en Reverse DCF."""
    if share_price <= 0 or shares_out_b <= 0 or base_revenue_m <= 0 or wacc <= terminal_growth or fcf_margin <= 0:
        return 0.0

    target_ev = (share_price * shares_out_b * 1000.0) + net_debt_m

    def calc_ev(g: float) -> float:
        pv_ufcf = 0.0
        rev_t = base_revenue_m
        ufcf_t = 0.0
        for t in range(1, forecast_years + 1):
            rev_t *= 1.0 + g
            ufcf_t = rev_t * fcf_margin
            pv_ufcf += ufcf_t / ((1.0 + wacc) ** t)
        tv_n = (ufcf_t * (1.0 + terminal_growth)) / (wacc - terminal_growth)
        return pv_ufcf + (tv_n / ((1.0 + wacc) ** forecast_years))

    low, high = -0.30, 0.80
    mid = 0.0
    for _ in range(100):
        mid = (low + high) / 2.0
        ev_mid = calc_ev(mid)
        if abs(ev_mid - target_ev) < 1.0:
            return mid
        if ev_mid < target_ev:
            low = mid
        else:
            high = mid
    return mid


def solve_reverse_dcf_3stage(
    share_price: float,
    shares_out_b: float,
    net_debt_m: float,
    base_revenue_m: float,
    wacc: float,
    terminal_growth: float = 0.025,
    fcf_margin: float = 0.252,
    forecast_years: int = 10,
    fade_start_year: int = 5,
) -> float:
    """Resuelve el crecimiento inicial g1 (años 1..5) en Reverse DCF de 3 etapas con fade competitivo."""
    if share_price <= 0 or shares_out_b <= 0 or base_revenue_m <= 0 or wacc <= terminal_growth or fcf_margin <= 0:
        return 0.0

    target_ev = (share_price * shares_out_b * 1000.0) + net_debt_m
    fade_span = float(max(1, forecast_years - fade_start_year))

    def calc_ev_3stage(g: float) -> float:
        pv_ufcf = 0.0
        rev_t = base_revenue_m
        ufcf_t = 0.0
        for t in range(1, forecast_years + 1):
            if t <= fade_start_year:
                g_t = g
            else:
                weight = float(t - fade_start_year) / fade_span
                g_t = g * (1.0 - weight) + terminal_growth * weight
            rev_t *= 1.0 + g_t
            ufcf_t = rev_t * fcf_margin
            pv_ufcf += ufcf_t / ((1.0 + wacc) ** t)
        tv_n = (ufcf_t * (1.0 + terminal_growth)) / max(0.005, wacc - terminal_growth)
        return pv_ufcf + (tv_n / ((1.0 + wacc) ** forecast_years))

    low, high = -0.50, 1.50
    mid = 0.0
    for _ in range(80):
        mid = (low + high) / 2.0
        ev_mid = calc_ev_3stage(mid)
        if abs(ev_mid - target_ev) < 1.0:
            return mid
        if ev_mid < target_ev:
            low = mid
        else:
            high = mid
    return mid


def calculate_dcf_details(
    base_revenue_m: float,
    g_rev: float,
    fcf_margin: float,
    wacc: float,
    terminal_growth: float,
    net_debt_m: float,
    shares_m: float,
    model_type: str = "2STAGE",
    forecast_years: int = 10,
    fade_start_year: int = 5,
) -> Dict[str, Any]:
    """Calcula valor presente de flujos, valor terminal y precio justo teórico."""
    if base_revenue_m <= 0 or shares_m <= 0 or wacc <= terminal_growth:
        return {"fair_price": 0.0, "ev": 0.0, "equity_val": 0.0, "pv_fcf": 0.0, "pv_tv": 0.0}

    pv_ufcf = 0.0
    rev_t = base_revenue_m
    ufcf_t = 0.0
    fade_span = float(max(1, forecast_years - fade_start_year))
    for t in range(1, forecast_years + 1):
        if model_type == "3STAGE" and t > fade_start_year:
            weight = float(t - fade_start_year) / fade_span
            g_t = g_rev * (1.0 - weight) + terminal_growth * weight
        else:
            g_t = g_rev
        rev_t *= 1.0 + g_t
        ufcf_t = rev_t * fcf_margin
        pv_ufcf += ufcf_t / ((1.0 + wacc) ** t)

    tv_n = (ufcf_t * (1.0 + terminal_growth)) / max(0.005, wacc - terminal_growth)
    pv_tv = tv_n / ((1.0 + wacc) ** forecast_years)
    ev_total = pv_ufcf + pv_tv
    equity_val = ev_total - net_debt_m
    fair_price = equity_val / shares_m if shares_m > 0 else 0.0
    return {
        "fair_price": round(max(0.0, fair_price), 2),
        "ev": round(ev_total, 1),
        "equity_val": round(equity_val, 1),
        "pv_fcf": round(pv_ufcf, 1),
        "pv_tv": round(pv_tv, 1),
    }


def calculate_epv_pvgo(
    base_revenue_m: float,
    ebit_margin: float,
    tax_rate: float,
    sbc_usd_m: float,
    wacc: float,
    net_debt_m: float,
    shares_m: float,
    current_price: float,
) -> Dict[str, Any]:
    """Calcula Earnings Power Value (EPV) sin crecimiento y la proporción PVGO del precio."""
    if base_revenue_m <= 0 or shares_m <= 0 or wacc <= 0:
        return {
            "epv_operating_m": 0.0,
            "epv_equity_m": 0.0,
            "epv_per_share": 0.0,
            "pvgo_per_share": 0.0,
            "epv_pct": 0.0,
            "pvgo_pct": 0.0,
            "status": "N/D",
            "sustainable_nopat_m": 0.0,
        }

    norm_ebit_m = base_revenue_m * ebit_margin
    sustainable_nopat_m = max(0.0, (norm_ebit_m * (1.0 - tax_rate)) - sbc_usd_m)
    epv_operating_m = sustainable_nopat_m / wacc
    epv_equity_m = epv_operating_m - net_debt_m
    epv_per_share = round(max(0.0, epv_equity_m / shares_m), 2)

    if current_price > 0:
        pvgo_per_share = round(max(0.0, current_price - epv_per_share), 2)
        epv_pct = round(min(100.0, max(0.0, (epv_per_share / current_price) * 100.0)), 1)
        pvgo_pct = round(max(0.0, 100.0 - epv_pct), 1)
        if epv_per_share >= current_price:
            status = "CRECIMIENTO GRATIS (EPV ≥ Precio Mercado)"
        elif pvgo_pct <= 35.0:
            status = "ALTA PROTECCIÓN DE BENEFICIOS ACTUALES"
        elif pvgo_pct <= 65.0:
            status = "EXPECTATIVAS EQUILIBRADAS DE CRECIMIENTO"
        else:
            status = "ALTA DEPENDENCIA DE CRECIMIENTO FUTURO"
    else:
        pvgo_per_share, epv_pct, pvgo_pct, status = 0.0, 0.0, 0.0, "N/D"

    return {
        "epv_operating_m": round(epv_operating_m, 1),
        "epv_equity_m": round(epv_equity_m, 1),
        "epv_per_share": epv_per_share,
        "pvgo_per_share": pvgo_per_share,
        "epv_pct": epv_pct,
        "pvgo_pct": pvgo_pct,
        "status": status,
        "sustainable_nopat_m": round(sustainable_nopat_m, 1),
    }


def calculate_eva_valuation(
    invested_capital_m: float,
    roic_val: Optional[float],
    wacc_val: float,
    net_debt_m: float,
    shares_m: float,
    growth_reinvest: float = 0.035,
    fade_years: int = 10,
    g_terminal: float = 0.025,
) -> Dict[str, Any]:
    """Valora la empresa por Beneficio Económico (EVA / Residual Income) sobre Capital Invertido."""
    if invested_capital_m <= 0 or shares_m <= 0 or wacc_val <= g_terminal or roic_val is None:
        return {"fair_price_eva": 0.0, "ev_eva": 0.0, "ic_base_m": 0.0, "pv_eva_sum": 0.0, "pv_terminal_eva": 0.0, "spread_pct": 0.0}

    spread = roic_val - wacc_val
    ic_t = invested_capital_m
    pv_eva_sum = 0.0
    r_term = min(roic_val, wacc_val + 0.04)
    for t in range(1, fade_years + 1):
        weight = float(t) / float(fade_years)
        r_t = roic_val * (1.0 - weight) + r_term * weight
        pv_eva_sum += (ic_t * (r_t - wacc_val)) / ((1.0 + wacc_val) ** t)
        ic_t *= 1.0 + growth_reinvest

    eva_terminal = ic_t * (r_term - wacc_val)
    terminal_val = (eva_terminal * (1.0 + g_terminal)) / max(0.005, wacc_val - g_terminal)
    pv_terminal_eva = terminal_val / ((1.0 + wacc_val) ** fade_years)
    ev_eva = invested_capital_m + pv_eva_sum + pv_terminal_eva
    return {
        "fair_price_eva": round(max(0.0, (ev_eva - net_debt_m) / shares_m), 2),
        "ev_eva": round(ev_eva, 1),
        "ic_base_m": round(invested_capital_m, 1),
        "pv_eva_sum": round(pv_eva_sum, 1),
        "pv_terminal_eva": round(pv_terminal_eva, 1),
        "spread_pct": round(spread * 100.0, 2),
    }


def calculate_5y_forward_irr(
    price: float,
    base_revenue_m: float,
    revenue_growth_pct: float,
    fcf_margin_pct: float,
    shares_m: float,
    net_buyback_yield_pct: float,
    exit_multiple: float,
    dividend_yield_pct: float,
    base_fcf_margin_pct: Optional[float] = None,
    current_multiple: Optional[float] = None,
) -> Dict[str, Any]:
    """Simula la TIR esperada a 5 años descomponiendo ventas, margen, recompras, múltiplo y dividendo."""
    if price <= 0 or base_revenue_m <= 0 or shares_m <= 0:
        return {
            "target_price_5y": 0.0,
            "forward_irr_pct": 0.0,
            "price_cagr_pct": 0.0,
            "total_return_pct": 0.0,
            "bridge": {"growth_contrib": 0.0, "margin_contrib": 0.0, "buyback_contrib": 0.0, "multiple_contrib": 0.0, "div_contrib": 0.0},
        }

    g_rev = revenue_growth_pct / 100.0
    m_target = fcf_margin_pct / 100.0
    m_base = (base_fcf_margin_pct / 100.0) if (base_fcf_margin_pct and base_fcf_margin_pct > 0) else m_target
    r_buyback = net_buyback_yield_pct / 100.0
    div_y = dividend_yield_pct / 100.0

    rev_5 = base_revenue_m * ((1.0 + g_rev) ** 5)
    fcf_5 = rev_5 * m_target
    shares_5 = shares_m * ((1.0 - r_buyback) ** 5)
    fcf_per_share_5 = (fcf_5 / shares_5) if shares_5 > 0 else 0.0
    target_price_5y = round(max(0.01, fcf_per_share_5 * exit_multiple), 2) if fcf_per_share_5 > 0 and exit_multiple > 0 else 0.0

    price_cagr = (((target_price_5y / price) ** (1.0 / 5.0)) - 1.0) if target_price_5y > 0 else -1.0
    forward_irr = price_cagr + div_y
    total_return_5y = ((target_price_5y * ((1.0 + div_y) ** 5) - price) / price) * 100.0

    margin_ratio = (m_target / m_base) if m_base > 0 else 1.0
    cur_mult = current_multiple if (current_multiple and current_multiple > 0) else exit_multiple
    mult_ratio = (exit_multiple / cur_mult) if cur_mult > 0 else 1.0

    return {
        "target_price_5y": target_price_5y,
        "forward_irr_pct": round(forward_irr * 100.0, 2),
        "price_cagr_pct": round(price_cagr * 100.0, 2),
        "total_return_pct": round(total_return_5y, 1),
        "fcf_per_share_5y": round(fcf_per_share_5, 2),
        "shares_5y_m": round(shares_5, 1),
        "rev_5y_m": round(rev_5, 1),
        "bridge": {
            "growth_contrib": round(g_rev * 100.0, 2),
            "margin_contrib": round(((margin_ratio ** (1.0 / 5.0)) - 1.0) * 100.0, 2),
            "buyback_contrib": round(r_buyback * 100.0, 2),
            "multiple_contrib": round(((mult_ratio ** (1.0 / 5.0)) - 1.0) * 100.0, 2),
            "div_contrib": round(div_y * 100.0, 2),
        },
    }


def calculate_multiples_valuation(
    price: float,
    shares_m: float,
    net_debt_m: float,
    base_rev_m: float,
    ebit_m: float,
    ebitda_m: float,
    net_income_m: float,
    fcf_m: float,
    eps_diluted: float,
    cagr_5y: Optional[float] = None,
    cagr_eps_5y: Optional[float] = None,
    cagr_fcf_5y: Optional[float] = None,
    peers_detail: Optional[List[Dict[str, Any]]] = None,
    is_financial: bool = False,
    tbv_per_share: float = 0.0,
    ptbv_justified: float = 1.0,
    dividend_yield_pct: float = 0.0,
) -> Dict[str, Any]:
    """Calcula múltiplos actuales, de pares, PEG/PEGY y precios imputados."""
    market_cap_m = price * shares_m if (price > 0 and shares_m > 0) else 0.0
    ev_m = market_cap_m + net_debt_m if market_cap_m > 0 else 0.0

    pe_current = round(price / eps_diluted, 2) if (eps_diluted > 0 and price > 0) else (
        round(market_cap_m / net_income_m, 2) if (net_income_m > 0 and market_cap_m > 0) else None
    )
    ev_ebitda_current = round(ev_m / ebitda_m, 2) if (ebitda_m > 0 and ev_m > 0) else None
    ev_ebit_current = round(ev_m / ebit_m, 2) if (ebit_m > 0 and ev_m > 0) else None
    ev_fcf_current = round(ev_m / fcf_m, 2) if (fcf_m > 0 and ev_m > 0) else None
    ps_current = round(market_cap_m / base_rev_m, 2) if (base_rev_m > 0 and market_cap_m > 0) else None
    fcf_yield_pct = round((fcf_m / market_cap_m) * 100.0, 2) if (fcf_m > 0 and market_cap_m > 0) else None

    peg_ratio, peg_expl = None, "Crecimiento ≤ 0% o No Disponible"
    if pe_current and pe_current > 0:
        if cagr_eps_5y and cagr_eps_5y > 0:
            peg_ratio = round(pe_current / cagr_eps_5y, 2)
            peg_expl = f"P/E {pe_current:.1f}x ÷ CAGR EPS 5Y ({cagr_eps_5y:.1f}%)"
        elif cagr_5y and cagr_5y > 0:
            peg_ratio = round(pe_current / cagr_5y, 2)
            peg_expl = f"P/E {pe_current:.1f}x ÷ CAGR Ventas 5Y ({cagr_5y:.1f}%)"

    pegy_ratio, pegy_expl = None, "No disponible"
    if pe_current and pe_current > 0:
        base_g = cagr_eps_5y if (cagr_eps_5y and cagr_eps_5y > 0) else (cagr_5y if (cagr_5y and cagr_5y > 0) else 0.0)
        tot_ret = base_g + (dividend_yield_pct or 0.0)
        if tot_ret > 0:
            pegy_ratio = round(pe_current / tot_ret, 2)
            pegy_expl = f"P/E {pe_current:.1f}x ÷ (Crec. {base_g:.1f}% + Div. {dividend_yield_pct or 0.0:.1f}%)"

    peer_pes, peer_ev_fcfs = [], []
    for p in peers_detail or []:
        if p.get("is_target"):
            continue
        p_mc = p.get("market_cap_usd_m", 0.0)
        p_ni = p.get("net_income_usd_m", 0.0)
        p_ev = p_mc + p.get("total_debt_usd_m", 0.0) - p.get("cash_usd_m", 0.0)
        p_fcf = p.get("cfo_usd_m", 0.0) - p.get("capex_usd_m", 0.0)
        if p_mc > 0 and p_ni > 0 and 2.0 <= (p_mc / p_ni) <= 80.0:
            peer_pes.append(p_mc / p_ni)
        if p_ev > 0 and p_fcf > 0 and 2.0 <= (p_ev / p_fcf) <= 80.0:
            peer_ev_fcfs.append(p_ev / p_fcf)

    peer_median_pe = round(float(sorted(peer_pes)[len(peer_pes) // 2]), 1) if peer_pes else (14.0 if is_financial else 22.0)
    peer_median_ev_fcf = round(float(sorted(peer_ev_fcfs)[len(peer_ev_fcfs) // 2]), 1) if peer_ev_fcfs else 18.0

    if is_financial:
        normal_pe = min(18.0, max(8.0, peer_median_pe))
        imputed_pe = round(eps_diluted * normal_pe, 2) if eps_diluted > 0 else 0.0
        imputed_ptbv = round(tbv_per_share * ptbv_justified, 2) if tbv_per_share > 0 else 0.0
        valid_fin = [v for v in (imputed_pe, imputed_ptbv) if v > 0]
        imputed_prices = {
            "pe": imputed_pe,
            "ptbv": imputed_ptbv,
            "composite": round(sum(valid_fin) / len(valid_fin), 2) if valid_fin else 0.0,
        }
        normal_ev_fcf = None
    else:
        normal_pe = min(32.0, max(12.0, round((pe_current * 0.4 + peer_median_pe * 0.6), 1) if pe_current else peer_median_pe))
        normal_ev_fcf = min(30.0, max(10.0, round((ev_fcf_current * 0.4 + peer_median_ev_fcf * 0.6), 1) if ev_fcf_current else peer_median_ev_fcf))
        imputed_pe = round(eps_diluted * normal_pe, 2) if eps_diluted > 0 else 0.0
        imputed_ev_ebitda = round((ebitda_m * 14.0 - net_debt_m) / shares_m, 2) if (shares_m > 0 and ebitda_m > 0) else 0.0
        imputed_ev_fcf = round((fcf_m * normal_ev_fcf - net_debt_m) / shares_m, 2) if (shares_m > 0 and fcf_m > 0) else 0.0
        valid_imp = [v for v in (imputed_pe, imputed_ev_ebitda, imputed_ev_fcf) if v > 0]
        imputed_prices = {
            "pe": imputed_pe,
            "ev_ebitda": imputed_ev_ebitda,
            "ev_fcf": imputed_ev_fcf,
            "composite": round(sum(valid_imp) / len(valid_imp), 2) if valid_imp else 0.0,
        }

    return {
        "pe_current": pe_current,
        "ev_ebitda_current": ev_ebitda_current,
        "ev_ebit_current": ev_ebit_current,
        "ev_fcf_current": ev_fcf_current,
        "ps_current": ps_current,
        "fcf_yield_pct": fcf_yield_pct,
        "peg_ratio": peg_ratio,
        "peg_explanation": peg_expl,
        "pegy_ratio": pegy_ratio,
        "pegy_explanation": pegy_expl,
        "dividend_yield_pct": dividend_yield_pct,
        "peer_median_pe": peer_median_pe,
        "peer_median_ev_fcf": peer_median_ev_fcf if not is_financial else None,
        "normal_pe": normal_pe,
        "normal_ev_fcf": normal_ev_fcf,
        "imputed_prices": imputed_prices,
    }


def calculate_owner_earnings_and_capex(
    cfo_m: float,
    capex_total_m: float,
    da_m: Optional[float],
    rev_m: float,
    nopat_adj_m: float,
    rd_exp_m: float,
    rd_amort_m: float,
    delta_nwc_m: Optional[float] = None,
    price: float = 0.0,
    shares_m: float = 0.0,
    net_debt_m: float = 0.0,
    wacc_val: float = 0.095,
    gn_dec: float = 0.025,
    is_financial: bool = False,
) -> Dict[str, Any]:
    """Descompone CapEx (Mantenimiento vs Crecimiento) y calcula Owner Earnings."""
    if is_financial:
        return {
            "is_financial": True,
            "status": "NO APLICA (Arquetipo Financiero / Bancario)",
            "cfo_m": 0.0,
            "capex_total_m": 0.0,
            "maint_capex_m": 0.0,
            "growth_capex_m": 0.0,
            "growth_capex_pct_of_total": 0.0,
            "fcf_reported_m": 0.0,
            "owner_earnings_m": 0.0,
            "net_rd_inv_m": 0.0,
            "fcf_margin_pct": 0.0,
            "oe_margin_pct": 0.0,
            "g_implied_oe_pct": 0.0,
            "fair_price_oe": price,
            "reconciliation_steps": [],
        }

    da_used = da_m if (da_m is not None and da_m > 0) else round(capex_total_m * 0.40, 1)
    maint_capex_m = round(min(capex_total_m, da_used), 1)
    growth_capex_m = round(max(0.0, capex_total_m - maint_capex_m), 1)
    net_rd_inv_m = round(max(0.0, rd_exp_m - rd_amort_m), 1)
    fcf_reported_m = round(cfo_m - capex_total_m, 1)

    owner_earnings_m = round(fcf_reported_m + growth_capex_m + net_rd_inv_m, 1)
    if owner_earnings_m <= 0 and nopat_adj_m > 0:
        owner_earnings_m = round(max(0.0, nopat_adj_m - maint_capex_m - (delta_nwc_m or 0.0)), 1)

    fcf_margin_pct = round((fcf_reported_m / rev_m) * 100.0, 2) if rev_m > 0 else 0.0
    oe_margin_pct = round((owner_earnings_m / rev_m) * 100.0, 2) if rev_m > 0 else 0.0

    shares_b = shares_m / 1000.0 if shares_m > 0 else 0.0
    g_implied_oe, fair_price_oe = 0.0, price
    if price > 0 and rev_m > 0 and oe_margin_pct > 0 and shares_b > 0:
        g_implied_oe = solve_reverse_dcf_3stage(
            share_price=price,
            shares_out_b=shares_b,
            net_debt_m=net_debt_m,
            base_revenue_m=rev_m,
            wacc=wacc_val,
            terminal_growth=gn_dec,
            fcf_margin=oe_margin_pct / 100.0,
            forecast_years=10,
            fade_start_year=5,
        )
        fair_price_oe = calculate_dcf_details(
            rev_m, 0.08, oe_margin_pct / 100.0, wacc_val, gn_dec, net_debt_m, shares_m, model_type="3STAGE"
        ).get("fair_price", price)

    return {
        "is_financial": False,
        "status": "OPERATIVO",
        "cfo_m": cfo_m,
        "capex_total_m": capex_total_m,
        "maint_capex_m": maint_capex_m,
        "growth_capex_m": growth_capex_m,
        "growth_capex_pct_of_total": round((growth_capex_m / capex_total_m * 100.0), 1) if capex_total_m > 0 else 0.0,
        "fcf_reported_m": fcf_reported_m,
        "owner_earnings_m": owner_earnings_m,
        "net_rd_inv_m": net_rd_inv_m,
        "fcf_margin_pct": fcf_margin_pct,
        "oe_margin_pct": oe_margin_pct,
        "g_implied_oe_pct": round(g_implied_oe * 100.0, 1),
        "fair_price_oe": round(fair_price_oe, 2),
        "reconciliation_steps": [
            {"step": "1. Flujo de Caja Libre Contable (FCF Reportado)", "value_m": fcf_reported_m, "formula": f"CFO (${cfo_m:,.1f}M) - CapEx Total (${capex_total_m:,.1f}M)"},
            {"step": "2. (+) Reintegro de CapEx de Crecimiento (Expansión Opcional)", "value_m": growth_capex_m, "formula": f"CapEx Total (${capex_total_m:,.1f}M) - Mantenimiento (${maint_capex_m:,.1f}M)"},
            {"step": "3. (+) Inversión Neta en I+D Económica", "value_m": net_rd_inv_m, "formula": f"Gasto I+D (${rd_exp_m:,.1f}M) - Amortización Económica (${rd_amort_m:,.1f}M)"},
            {"step": "4. (=) Beneficios del Propietario (Owner Earnings)", "value_m": owner_earnings_m, "formula": "FCF Reportado + CapEx Crecimiento + Inversión Neta I+D"},
        ],
    }


def get_valuation_football_field(
    price: float,
    dcf_price: float,
    multiples_price: float,
    epv_price: float,
    eva_price: float,
    target_5y_price: float,
    ke_val: float = 0.095,
) -> Dict[str, Any]:
    """Genera los rangos [Min, Base, Max] para el gráfico Valuation Football Field."""
    target_pv = round(target_5y_price / ((1.0 + ke_val) ** 5), 2) if target_5y_price > 0 else 0.0
    methods = [
        {"id": "dcf", "name": "Reverse DCF (Expectations)", "badge": "Flujos Descontados", "low": round(dcf_price * 0.85, 2), "base": round(dcf_price, 2), "high": round(dcf_price * 1.18, 2), "color": "sky"},
        {"id": "multiples", "name": "Múltiplos Comparables", "badge": "Valoración Relativa", "low": round(multiples_price * 0.88, 2), "base": round(multiples_price, 2), "high": round(multiples_price * 1.15, 2), "color": "amber"},
        {"id": "epv", "name": "Earnings Power Value (EPV)", "badge": "Columbia / Crecimiento 0%", "low": round(epv_price * 0.90, 2), "base": round(epv_price, 2), "high": round((epv_price + dcf_price) / 2.0, 2) if epv_price < dcf_price else round(epv_price * 1.20, 2), "color": "emerald"},
        {"id": "eva", "name": "Beneficio Económico (EVA)", "badge": "ROIC vs. WACC", "low": round(eva_price * 0.86, 2), "base": round(eva_price, 2), "high": round(eva_price * 1.16, 2), "color": "purple"},
        {"id": "target5y", "name": "Simulador 5Y (PV a hoy)", "badge": "Retorno Compuesto", "low": round(target_pv * 0.85, 2), "base": round(target_pv, 2), "high": round(target_pv * 1.20, 2), "color": "indigo"},
    ]
    sorted_bases = sorted(m["base"] for m in methods if m["base"] > 0)
    consensus_price = round(sorted_bases[len(sorted_bases) // 2], 2) if sorted_bases else 0.0
    margin_safety_pct = round(((consensus_price - price) / price) * 100.0, 1) if (price > 0 and consensus_price > 0) else 0.0
    return {"methods": methods, "consensus_price": consensus_price, "margin_safety_pct": margin_safety_pct, "current_price": price}
