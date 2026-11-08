# -*- coding: utf-8 -*-
"""
valuation_engine.py - Motor de Modelado Financiero y Valuación Intrínseca:
Reverse DCF con Expectations Investing (Corporativo) y Excess Return Model P/TBV vs. ROTCE (Financiero/Bancos/Seguros).

Usado por el Dashboard Web Django (views_valuation.py) para simulación dinámica y matrices de sensibilidad.
"""

import sys
import re
import json
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA_DIR = PROJECT_ROOT / "data" / "processed"

try:
    from sec_extractor import normalize_archetype
except ImportError:
    try:
        from pipeline.sec_extractor import normalize_archetype
    except ImportError:
        def normalize_archetype(archetype: str, default: str = "STANDARD_CORPORATE") -> str:
            if not archetype:
                return default
            arch = str(archetype).strip().upper()
            aliases = {
                "CORPORATE_STANDARD": "STANDARD_CORPORATE",
                "STANDARD_CORPORATE": "STANDARD_CORPORATE",
                "FINANCIAL_BANKING": "FINANCIAL_BANKING",
                "BANKING_FINANCIAL": "FINANCIAL_BANKING",
                "BANKING": "FINANCIAL_BANKING",
                "INSURANCE": "INSURANCE",
                "INSURER": "INSURANCE",
                "REAL_ESTATE_REIT": "REAL_ESTATE_REIT",
                "REIT": "REAL_ESTATE_REIT",
                "PLATFORM_ECOSYSTEM": "PLATFORM_ECOSYSTEM",
            }
            return aliases.get(arch, arch)


def _resolve_processed_path(ticker: str, filename: str) -> Path:
    """Resuelve la ruta canónica del archivo en data/processed/{ticker}/ garantizando invariancia de CWD."""
    p_abs = DEFAULT_DATA_DIR / ticker / filename
    if p_abs.exists():
        return p_abs
    p_rel = Path(f"data/processed/{ticker}/{filename}")
    if p_rel.exists():
        return p_rel
    return p_abs


def get_report_archetype(scoring_data: Dict[str, Any]) -> str:
    """Resuelve canónicamente el arquetipo contable del emisor."""
    arch = scoring_data.get("archetype") or scoring_data.get("scoring_results", {}).get("archetype")
    if arch:
        return str(arch).strip()
    if scoring_data.get("is_financial_institution"):
        return "FINANCIAL_BANKING"
    sic = str(scoring_data.get("sic_code") or scoring_data.get("benchmarks_used", {}).get("sic_code", "")).strip()
    if sic.startswith("63") or sic.startswith("64"):
        return "INSURANCE"
    if sic.startswith("60") or sic.startswith("61") or sic.startswith("62"):
        return "FINANCIAL_BANKING"
    if sic == "6798":
        return "REAL_ESTATE_REIT"
    if scoring_data.get("benchmarks_used", {}).get("gics_sector") == "Financials":
        ind = str(scoring_data.get("industry_name", "")).upper()
        bm = str(scoring_data.get("business_model", "")).upper()
        if "INSUR" in ind or "INSUR" in bm:
            return "INSURANCE"
        return "FINANCIAL_BANKING"
    return "STANDARD_CORPORATE"


def get_solvency_archetype(scoring_data: Dict[str, Any]) -> str:
    """Clasifica el arquetipo de solvencia para separar banca/seguros del análisis corporativo estándar."""
    arch = (scoring_data.get("archetype") or scoring_data.get("scoring_results", {}).get("archetype") or "").upper()
    if not arch and scoring_data.get("is_financial_institution"):
        arch = "FINANCIAL_BANKING"
    if arch in ["FINANCIAL_BANKING", "INSURANCE"]:
        return arch
    return "CORPORATE"


def _fmt_money(val: Any, default: str = "N/D", prefix: str = "$", suffix: str = "") -> str:
    """Formatea valores monetarios a cadena amigable."""
    if val is None or val == "" or str(val).upper() == "N/D":
        return default
    try:
        fval = float(val)
        return f"{prefix}{fval:,.1f}{suffix}"
    except (ValueError, TypeError):
        return default


def _fmt_pct(val: Any, default: str = "N/D") -> str:
    """Formatea ratios y tasas a porcentaje legible."""
    if val is None or val == "" or str(val).upper() == "N/D":
        return default
    try:
        fval = float(val)
        if abs(fval) <= 1.0 and fval != 0.0:
            return f"{fval * 100.0:.2f}%"
        return f"{fval:.2f}%"
    except (ValueError, TypeError):
        return default



def _is_financial(scoring_data: Dict[str, Any]) -> bool:
    """Identifica si la empresa pertenece al sector financiero/bancario/seguros."""
    return get_report_archetype(scoring_data) in ("FINANCIAL_BANKING", "INSURANCE")


def _compute_series_cagr(val_map: Optional[Dict[str, Any]], years: int = 5) -> Optional[float]:
    """Calcula el CAGR histórico entre los últimos N períodos fiscales cerrados (FY)."""
    if not val_map or not isinstance(val_map, dict):
        return None
    fy_keys = sorted(
        [k for k in val_map.keys() if k.startswith("FY") and val_map[k] is not None and float(val_map[k]) > 0],
        key=lambda x: int(x.replace("FY", "")) if x.replace("FY", "").isdigit() else 0
    )
    if len(fy_keys) >= (years + 1):
        v_now = float(val_map[fy_keys[-1]])
        v_prev = float(val_map[fy_keys[-(years + 1)]])
        if v_prev > 0 and v_now > 0:
            return round((((v_now / v_prev) ** (1.0 / float(years))) - 1.0) * 100.0, 1)
    elif len(fy_keys) >= 2:
        n = len(fy_keys) - 1
        v_now = float(val_map[fy_keys[-1]])
        v_prev = float(val_map[fy_keys[0]])
        if v_prev > 0 and v_now > 0:
            return round((((v_now / v_prev) ** (1.0 / float(n))) - 1.0) * 100.0, 1)
    return None


def _compute_share_reduction_rate(shares_map: Optional[Dict[str, Any]], years: int = 5) -> float:
    """Calcula la tasa anualizada de reducción neta de acciones diluidas (Buyback Yield positivo / Dilución negativa)."""
    cagr = _compute_series_cagr(shares_map, years=years)
    if cagr is not None:
        return -round(cagr, 2)
    return 1.5


def compute_two_stage_excess_return_ptbv(
    rotce_val: float,
    ke_val: float,
    g_term: float = 0.030,
    cagr_5y: Optional[float] = None,
    is_insurance: bool = False,
    fade_years: int = 5
) -> float:
    """
    Calcula el múltiplo P/TBV (o P/BV) justificado mediante un Modelo de Retorno Excedente
    (Residual Income / Excess Return Model) de 2 Etapas (Damodaran):
    - Etapa 1 (años 1..N): El retorno sobre el capital (ROTCE/ROE) converge linealmente desde rotce_val
      hacia un retorno sostenible de ciclo completo (r_terminal), mientras el valor en libros por acción
      crece por retención de beneficios (g_bv).
    - Etapa 2 (Valor Terminal): (r_terminal - g_term) / (ke_val - g_term) aplicado sobre el BV del año N.
    """
    if ke_val <= g_term or rotce_val <= 0:
        return 1.0

    # Retorno terminal sostenible tras reversión competitiva a la media del ciclo
    if is_insurance:
        # En seguros P&C los picos de ciclo duro (>25% ROE) convergen hacia Ke + 10.5% (~18%)
        r_terminal = min(rotce_val, ke_val + 0.105) if rotce_val > (ke_val + 0.105) else rotce_val
        retention = 0.45
    else:
        # En banca: neobancos de alto crecimiento vs banca tradicional madura
        is_high_growth_bank = (cagr_5y is not None and cagr_5y >= 25.0)
        spread_cap = 0.145 if is_high_growth_bank else 0.105
        r_terminal = min(rotce_val, ke_val + spread_cap) if rotce_val > (ke_val + spread_cap) else rotce_val
        retention = 0.72 if is_high_growth_bank else 0.40

    bv_t = 1.0  # Normalizado a $1.00 de Book Value inicial
    pv_excess_stage1 = 0.0

    for t in range(1, fade_years + 1):
        weight = float(t) / float(fade_years)
        r_t = rotce_val * (1.0 - weight) + r_terminal * weight
        excess_return_t = (r_t - ke_val) * bv_t
        pv_excess_stage1 += excess_return_t / ((1.0 + ke_val) ** t)
        g_bv_t = min(0.22, max(g_term, r_t * retention))
        bv_t *= (1.0 + g_bv_t)

    terminal_excess_multiple = (r_terminal - ke_val) / (ke_val - g_term)
    pv_terminal_excess = (terminal_excess_multiple * bv_t) / ((1.0 + ke_val) ** fade_years)

    ptbv_just = 1.0 + pv_excess_stage1 + pv_terminal_excess
    return round(max(0.5, ptbv_just), 2)


def solve_reverse_dcf(
    share_price: float,
    shares_out_b: float,
    net_debt_m: float,
    base_revenue_m: float,
    wacc: float,
    terminal_growth: float = 0.025,
    fcf_margin: float = 0.252,
    forecast_years: int = 10
) -> float:
    """Resuelve numéricamente la tasa anual de crecimiento de ingresos (g_implied) en un modelo Reverse DCF."""
    if share_price <= 0 or shares_out_b <= 0 or base_revenue_m <= 0 or wacc <= terminal_growth:
        return 0.10

    target_ev = (share_price * shares_out_b * 1000) + net_debt_m

    def calc_ev(g: float) -> float:
        pv_ufcf = 0.0
        rev_t = base_revenue_m
        for t in range(1, forecast_years + 1):
            rev_t *= (1.0 + g)
            ufcf_t = rev_t * fcf_margin
            pv_ufcf += ufcf_t / ((1.0 + wacc) ** t)
        
        tv_n = (ufcf_t * (1.0 + terminal_growth)) / (wacc - terminal_growth)
        pv_tv = tv_n / ((1.0 + wacc) ** forecast_years)
        return pv_ufcf + pv_tv

    low = -0.30
    high = 0.80
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
    """
    Resuelve numéricamente la tasa anual de crecimiento inicial g1 (años 1..5)
    bajo un modelo de 3 Etapas con Fade Competitivo (Damodaran & Mauboussin):
    - Etapa 1 (años 1..5): crecimiento g1 constante.
    - Etapa 2 (años 6..10): desaceleración lineal de g_t hacia terminal_growth.
    - Etapa 3 (año 11+): valor terminal perpetuo a terminal_growth.
    """
    if share_price <= 0 or shares_out_b <= 0 or base_revenue_m <= 0 or wacc <= terminal_growth:
        return 0.10

    target_ev = (share_price * shares_out_b * 1000) + net_debt_m
    fade_span = float(max(1, forecast_years - fade_start_year))

    def calc_ev_3stage(g: float) -> float:
        pv_ufcf = 0.0
        rev_t = base_revenue_m
        for t in range(1, forecast_years + 1):
            if t <= fade_start_year:
                g_t = g
            else:
                weight = float(t - fade_start_year) / fade_span
                g_t = g * (1.0 - weight) + terminal_growth * weight
            rev_t *= (1.0 + g_t)
            ufcf_t = rev_t * fcf_margin
            pv_ufcf += ufcf_t / ((1.0 + wacc) ** t)
        
        tv_n = (ufcf_t * (1.0 + terminal_growth)) / max(0.005, wacc - terminal_growth)
        pv_tv = tv_n / ((1.0 + wacc) ** forecast_years)
        return pv_ufcf + pv_tv

    low = -0.50
    high = 1.50
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
    """Calcula el valor presente, valor terminal, múltiplo de salida y precio justo teórico."""
    if base_revenue_m <= 0 or shares_m <= 0 or wacc <= terminal_growth:
        return {
            "fair_price": 0.0,
            "ev": 0.0,
            "equity_val": 0.0,
            "pv_fcf": 0.0,
            "pv_tv": 0.0,
            "tv_pct": 0.0,
            "terminal_multiple": 0.0,
        }

    pv_ufcf = 0.0
    rev_t = base_revenue_m
    fade_span = float(max(1, forecast_years - fade_start_year))

    for t in range(1, forecast_years + 1):
        if model_type == "3STAGE" and t > fade_start_year:
            weight = float(t - fade_start_year) / fade_span
            g_t = g_rev * (1.0 - weight) + terminal_growth * weight
        else:
            g_t = g_rev
        rev_t *= (1.0 + g_t)
        ufcf_t = rev_t * fcf_margin
        pv_ufcf += ufcf_t / ((1.0 + wacc) ** t)

    tv_n = (ufcf_t * (1.0 + terminal_growth)) / max(0.005, wacc - terminal_growth)
    pv_tv = tv_n / ((1.0 + wacc) ** forecast_years)
    ev_total = pv_ufcf + pv_tv
    equity_val = ev_total - net_debt_m
    fair_price = equity_val / shares_m if shares_m > 0 else 0.0
    tv_pct = (pv_tv / ev_total * 100.0) if ev_total > 0 else 0.0
    terminal_multiple = (1.0 + terminal_growth) / max(0.005, wacc - terminal_growth)

    return {
        "fair_price": round(max(0.0, fair_price), 2),
        "ev": round(ev_total, 1),
        "equity_val": round(equity_val, 1),
        "pv_fcf": round(pv_ufcf, 1),
        "pv_tv": round(pv_tv, 1),
        "tv_pct": round(tv_pct, 1),
        "terminal_multiple": round(terminal_multiple, 1),
    }


def calculate_implied_cap(
    share_price: float,
    shares_b: float,
    net_debt_m: float,
    base_revenue_m: float,
    wacc: float,
    base_growth: float,
    fcf_margin: float,
    terminal_growth: float = 0.025,
    max_cap_years: int = 35,
) -> float:
    """
    Despeja cuántos años N (Competitive Advantage Period - Mauboussin) de crecimiento
    sostenido a base_growth justifican la cotización actual antes de converger a terminal_growth.
    """
    if share_price <= 0 or shares_b <= 0 or base_revenue_m <= 0 or wacc <= terminal_growth:
        return 10.0

    target_ev = (share_price * shares_b * 1000) + net_debt_m
    shares_m = shares_b * 1000

    details_1 = calculate_dcf_details(base_revenue_m, base_growth, fcf_margin, wacc, terminal_growth, net_debt_m, shares_m, forecast_years=1)
    if details_1["ev"] >= target_ev:
        return 1.0

    low_n = 1.0
    high_n = float(max_cap_years)

    def eval_n(n_years: float) -> float:
        n_floor = int(n_years)
        n_ceil = min(max_cap_years, n_floor + 1)
        frac = n_years - n_floor
        d_floor = calculate_dcf_details(base_revenue_m, base_growth, fcf_margin, wacc, terminal_growth, net_debt_m, shares_m, forecast_years=n_floor)
        d_ceil = calculate_dcf_details(base_revenue_m, base_growth, fcf_margin, wacc, terminal_growth, net_debt_m, shares_m, forecast_years=n_ceil)
        return d_floor["ev"] * (1.0 - frac) + d_ceil["ev"] * frac

    if eval_n(high_n) < target_ev:
        return float(max_cap_years)

    for _ in range(30):
        mid_n = (low_n + high_n) / 2.0
        ev_mid = eval_n(mid_n)
        if abs(ev_mid - target_ev) < 5.0:
            return round(mid_n, 1)
        if ev_mid < target_ev:
            low_n = mid_n
        else:
            high_n = mid_n
    return round(mid_n, 1)


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
    """
    Calcula el Earnings Power Value (Bruce Greenwald - Columbia) sin crecimiento
    y descompone el precio en valor actual sostenible (EPV) vs. expectativas futuras (PVGO).
    """
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
        pvgo_per_share = 0.0
        epv_pct = 100.0
        pvgo_pct = 0.0
        status = "N/D"

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
    roic_val: float,
    wacc_val: float,
    net_debt_m: float,
    shares_m: float,
    growth_reinvest: float = 0.035,
    fade_years: int = 10,
    g_terminal: float = 0.025,
) -> Dict[str, Any]:
    """
    Valora la empresa según el Beneficio Económico (EVA / Residual Income) sobre el Capital Invertido:
    EV = IC_0 + PV(EVA_1..N) + PV(Terminal EVA)
    """
    if invested_capital_m <= 0 or shares_m <= 0 or wacc_val <= g_terminal:
        return {
            "fair_price_eva": 0.0,
            "ev_eva": 0.0,
            "ic_base_m": 0.0,
            "pv_eva_sum": 0.0,
            "pv_terminal_eva": 0.0,
            "spread_pct": 0.0,
        }

    spread = roic_val - wacc_val
    ic_t = invested_capital_m
    pv_eva_sum = 0.0
    r_term = min(roic_val, wacc_val + 0.04)

    for t in range(1, fade_years + 1):
        weight = float(t) / float(fade_years)
        r_t = roic_val * (1.0 - weight) + r_term * weight
        eva_t = ic_t * (r_t - wacc_val)
        pv_eva_sum += eva_t / ((1.0 + wacc_val) ** t)
        ic_t *= (1.0 + growth_reinvest)

    eva_terminal = ic_t * (r_term - wacc_val)
    terminal_val = (eva_terminal * (1.0 + g_terminal)) / max(0.005, wacc_val - g_terminal)
    pv_terminal_eva = terminal_val / ((1.0 + wacc_val) ** fade_years)

    ev_eva = invested_capital_m + pv_eva_sum + pv_terminal_eva
    equity_eva = ev_eva - net_debt_m
    fair_price_eva = round(max(0.0, equity_eva / shares_m), 2)

    return {
        "fair_price_eva": fair_price_eva,
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
    """
    Simula el Retorno Total Anualizado Esperado (Forward IRR / CAGR) a 5 Años
    descomponiendo los 4 motores de retorno: ventas, margen, recompras/dilución y re-rating de múltiplo.
    """
    if price <= 0 or base_revenue_m <= 0 or shares_m <= 0:
        return {
            "target_price_5y": 0.0,
            "forward_irr_pct": 0.0,
            "price_cagr_pct": 0.0,
            "total_return_pct": 0.0,
            "bridge": {
                "growth_contrib": 0.0,
                "margin_contrib": 0.0,
                "buyback_contrib": 0.0,
                "multiple_contrib": 0.0,
                "div_contrib": 0.0,
            }
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
    target_price_5y = round(max(0.01, fcf_per_share_5 * exit_multiple), 2)

    price_cagr = ((target_price_5y / price) ** (1.0 / 5.0)) - 1.0 if target_price_5y > 0 else -1.0
    forward_irr = price_cagr + div_y
    total_return_5y = ((target_price_5y * ((1.0 + div_y) ** 5) - price) / price) * 100.0

    growth_contrib = g_rev * 100.0
    margin_ratio = (m_target / m_base) if m_base > 0 else 1.0
    margin_contrib = ((margin_ratio ** (1.0 / 5.0)) - 1.0) * 100.0
    buyback_contrib = r_buyback * 100.0

    cur_mult = current_multiple if (current_multiple and current_multiple > 0) else exit_multiple
    mult_ratio = (exit_multiple / cur_mult) if cur_mult > 0 else 1.0
    mult_contrib = ((mult_ratio ** (1.0 / 5.0)) - 1.0) * 100.0
    div_contrib = div_y * 100.0

    return {
        "target_price_5y": target_price_5y,
        "forward_irr_pct": round(forward_irr * 100.0, 2),
        "price_cagr_pct": round(price_cagr * 100.0, 2),
        "total_return_pct": round(total_return_5y, 1),
        "fcf_per_share_5y": round(fcf_per_share_5, 2),
        "shares_5y_m": round(shares_5, 1),
        "rev_5y_m": round(rev_5, 1),
        "bridge": {
            "growth_contrib": round(growth_contrib, 2),
            "margin_contrib": round(margin_contrib, 2),
            "buyback_contrib": round(buyback_contrib, 2),
            "multiple_contrib": round(mult_contrib, 2),
            "div_contrib": round(div_contrib, 2),
        }
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
) -> Dict[str, Any]:
    """
    Calcula los múltiplos actuales, históricos y de pares sectoriales,
    el ratio PEG riguroso y los precios justos imputados por reversión a la media.
    """
    market_cap_m = price * shares_m if (price > 0 and shares_m > 0) else 0.0
    ev_m = market_cap_m + net_debt_m if market_cap_m > 0 else 0.0

    # Múltiplos actuales
    pe_current = round(price / eps_diluted, 2) if (eps_diluted > 0 and price > 0) else (
        round(market_cap_m / net_income_m, 2) if (net_income_m > 0 and market_cap_m > 0) else None
    )
    ev_ebitda_current = round(ev_m / ebitda_m, 2) if (ebitda_m > 0 and ev_m > 0) else None
    ev_ebit_current = round(ev_m / ebit_m, 2) if (ebit_m > 0 and ev_m > 0) else None
    ev_fcf_current = round(ev_m / fcf_m, 2) if (fcf_m > 0 and ev_m > 0) else None
    ps_current = round(market_cap_m / base_rev_m, 2) if (base_rev_m > 0 and market_cap_m > 0) else None
    fcf_yield_pct = round((fcf_m / market_cap_m) * 100.0, 2) if (fcf_m > 0 and market_cap_m > 0) else None

    # Ratio PEG
    peg_ratio = None
    peg_explanation = "Crecimiento ≤ 0% o No Disponible"
    if pe_current and pe_current > 0:
        if cagr_eps_5y and cagr_eps_5y > 0:
            peg_ratio = round(pe_current / cagr_eps_5y, 2)
            peg_explanation = f"P/E {pe_current:.1f}x ÷ CAGR EPS 5Y ({cagr_eps_5y:.1f}%)"
        elif cagr_5y and cagr_5y > 0:
            peg_ratio = round(pe_current / cagr_5y, 2)
            peg_explanation = f"P/E {pe_current:.1f}x ÷ CAGR Ventas 5Y ({cagr_5y:.1f}%)"

    # Mediana de pares sectoriales
    peer_pes = []
    peer_ev_ebitdas = []
    peer_ev_fcfs = []
    if peers_detail:
        for p in peers_detail:
            if p.get("is_target"):
                continue
            p_mc = p.get("market_cap_usd_m", 0.0)
            p_ni = p.get("net_income_usd_m", 0.0)
            p_cfo = p.get("cfo_usd_m", 0.0)
            p_capex = p.get("capex_usd_m", 0.0)
            p_debt = p.get("total_debt_usd_m", 0.0)
            p_cash = p.get("cash_usd_m", 0.0)
            p_ev = p_mc + p_debt - p_cash
            p_fcf = p_cfo - p_capex
            if p_mc > 0 and p_ni > 0:
                p_pe = p_mc / p_ni
                if 2.0 <= p_pe <= 80.0:
                    peer_pes.append(p_pe)
            if p_ev > 0 and p_fcf > 0:
                p_ev_fcf = p_ev / p_fcf
                if 2.0 <= p_ev_fcf <= 80.0:
                    peer_ev_fcfs.append(p_ev_fcf)

    peer_median_pe = round(float(sorted(peer_pes)[len(peer_pes) // 2]), 1) if peer_pes else (14.0 if is_financial else 22.0)
    peer_median_ev_fcf = round(float(sorted(peer_ev_fcfs)[len(peer_ev_fcfs) // 2]), 1) if peer_ev_fcfs else 18.0

    # Múltiplos históricos / normales de referencia (blended target vs peers)
    if is_financial:
        normal_pe = min(18.0, max(8.0, peer_median_pe))
        normal_ptbv = ptbv_justified
        imputed_pe = round(eps_diluted * normal_pe, 2) if eps_diluted > 0 else price
        imputed_ptbv = round(tbv_per_share * normal_ptbv, 2) if tbv_per_share > 0 else price
        imputed_prices = {
            "pe": imputed_pe,
            "ptbv": imputed_ptbv,
            "composite": round((imputed_pe + imputed_ptbv) / 2.0, 2),
        }
    else:
        normal_pe = min(32.0, max(12.0, round((pe_current * 0.4 + peer_median_pe * 0.6), 1) if pe_current else peer_median_pe))
        normal_ev_ebitda = 14.0
        normal_ev_fcf = min(30.0, max(10.0, round((ev_fcf_current * 0.4 + peer_median_ev_fcf * 0.6), 1) if ev_fcf_current else peer_median_ev_fcf))

        imputed_pe = round(eps_diluted * normal_pe, 2) if eps_diluted > 0 else price
        imputed_ev_ebitda = round((ebitda_m * normal_ev_ebitda - net_debt_m) / shares_m, 2) if (shares_m > 0 and ebitda_m > 0) else price
        imputed_ev_fcf = round((fcf_m * normal_ev_fcf - net_debt_m) / shares_m, 2) if (shares_m > 0 and fcf_m > 0) else price

        valid_imputed = [v for v in [imputed_pe, imputed_ev_ebitda, imputed_ev_fcf] if v > 0]
        composite_imputed = round(sum(valid_imputed) / len(valid_imputed), 2) if valid_imputed else price
        imputed_prices = {
            "pe": imputed_pe,
            "ev_ebitda": imputed_ev_ebitda,
            "ev_fcf": imputed_ev_fcf,
            "composite": composite_imputed,
        }

    return {
        "pe_current": pe_current,
        "ev_ebitda_current": ev_ebitda_current,
        "ev_ebit_current": ev_ebit_current,
        "ev_fcf_current": ev_fcf_current,
        "ps_current": ps_current,
        "fcf_yield_pct": fcf_yield_pct,
        "peg_ratio": peg_ratio,
        "peg_explanation": peg_explanation,
        "peer_median_pe": peer_median_pe,
        "peer_median_ev_fcf": peer_median_ev_fcf if not is_financial else None,
        "normal_pe": normal_pe,
        "normal_ev_fcf": normal_ev_fcf if not is_financial else None,
        "imputed_prices": imputed_prices,
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
    """Genera las barras comparativas de rango [Min, Base, Max] para el gráfico Football Field."""
    target_pv = round(target_5y_price / ((1.0 + ke_val) ** 5), 2) if target_5y_price > 0 else price

    methods = [
        {
            "id": "dcf",
            "name": "Reverse DCF (Expectations)",
            "badge": "Flujos Descontados",
            "low": round(dcf_price * 0.85, 2),
            "base": round(dcf_price, 2),
            "high": round(dcf_price * 1.18, 2),
            "color": "sky",
        },
        {
            "id": "multiples",
            "name": "Múltiplos Comparables",
            "badge": "Valoración Relativa",
            "low": round(multiples_price * 0.88, 2),
            "base": round(multiples_price, 2),
            "high": round(multiples_price * 1.15, 2),
            "color": "amber",
        },
        {
            "id": "epv",
            "name": "Earnings Power Value (EPV)",
            "badge": "Columbia / Crecimiento 0%",
            "low": round(epv_price * 0.90, 2),
            "base": round(epv_price, 2),
            "high": round((epv_price + dcf_price) / 2.0, 2) if epv_price < dcf_price else round(epv_price * 1.20, 2),
            "color": "emerald",
        },
        {
            "id": "eva",
            "name": "Beneficio Económico (EVA)",
            "badge": "ROIC vs. WACC",
            "low": round(eva_price * 0.86, 2),
            "base": round(eva_price, 2),
            "high": round(eva_price * 1.16, 2),
            "color": "purple",
        },
        {
            "id": "target5y",
            "name": "Simulador 5Y (PV a hoy)",
            "badge": "Retorno Compuesto",
            "low": round(target_pv * 0.85, 2),
            "base": round(target_pv, 2),
            "high": round(target_pv * 1.20, 2),
            "color": "indigo",
        },
    ]

    base_prices = [m["base"] for m in methods if m["base"] > 0]
    sorted_bases = sorted(base_prices)
    consensus_price = round(sorted_bases[len(sorted_bases) // 2], 2) if sorted_bases else price
    margin_safety_pct = round(((consensus_price - price) / price) * 100.0, 1) if price > 0 else 0.0

    return {
        "methods": methods,
        "consensus_price": consensus_price,
        "margin_safety_pct": margin_safety_pct,
        "current_price": price,
    }


def get_valuation_parameters(
    scoring_data: Dict[str, Any],
    ticker: str = "",
    profile_data: Optional[Dict[str, Any]] = None,
    live_price: Optional[float] = None,
    fs_data: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Extrae y consolida los parámetros financieros y de mercado para la valoración de cualquier empresa."""
    ticker = ticker or scoring_data.get("ticker", "")
    prof = profile_data or {}
    if not prof and ticker:
        candidate = _resolve_processed_path(ticker, "company_profile.json")
        if candidate.exists():
            try:
                with open(candidate, "r", encoding="utf-8") as f:
                    prof = json.load(f)
            except Exception:
                pass

    fs_obj = fs_data
    if fs_obj is None and ticker:
        fs_path = _resolve_processed_path(ticker, "financial_statements.json")
        if fs_path.exists():
            try:
                with open(fs_path, "r", encoding="utf-8") as f_fs:
                    fs_obj = json.load(f_fs)
            except Exception:
                fs_obj = None

    arch = get_report_archetype(scoring_data)
    is_fin = arch in ("FINANCIAL_BANKING", "INSURANCE")
    is_ins = (arch == "INSURANCE")

    wacc_dict = (
        scoring_data.get("wacc_analysis")
        or scoring_data.get("wacc_and_spread_analysis")
        or scoring_data.get("roic_wacc_analysis", {}).get("wacc", {})
        or {}
    )
    mkt = wacc_dict.get("market_data", {}) or scoring_data.get("market_data", {})
    
    # Parámetros macro y de coste de capital
    rf_raw = mkt.get("rf_10y") if mkt.get("rf_10y") is not None else 0.0425
    rf_pct = round(rf_raw * 100, 2)
    beta = round(float(mkt.get("beta")), 2) if mkt.get("beta") is not None else 1.05
    erp = round(float(mkt.get("erp")), 4) if mkt.get("erp") is not None else 0.0475
    ke_val = wacc_dict.get("cost_of_equity_ke") if wacc_dict.get("cost_of_equity_ke") is not None else (rf_raw + (beta * erp))
    if is_fin:
        if beta < 0.80:
            beta = round(0.67 * beta + 0.33 * 1.0, 2)
        ke_val = max(ke_val, rf_raw + (beta * erp), rf_raw + 0.0325)
    
    if live_price is not None and live_price > 0:
        price = round(float(live_price), 2)
    elif mkt.get("price") is not None:
        price = round(float(mkt.get("price")), 2)
    else:
        price = round(float(prof.get("price", 100.0)), 2)
    
    wacc_val = wacc_dict.get("wacc") if wacc_dict.get("wacc") is not None else (ke_val if is_fin else 0.095)
    wacc_pct = round(wacc_val * 100, 2)
    
    kd_pre = wacc_dict.get("cost_of_debt_kd_pre_tax") if wacc_dict.get("cost_of_debt_kd_pre_tax") is not None else 0.045
    kd_post = wacc_dict.get("cost_of_debt_kd_after_tax") if wacc_dict.get("cost_of_debt_kd_after_tax") is not None else 0.035
    tax_rate = wacc_dict.get("effective_tax_rate") if wacc_dict.get("effective_tax_rate") is not None else 0.20
    
    we = wacc_dict.get("weight_equity") if wacc_dict.get("weight_equity") is not None else (1.0 if is_fin else 0.95)
    wd = wacc_dict.get("weight_debt") if wacc_dict.get("weight_debt") is not None else (0.0 if is_fin else 0.05)
    
    # Acciones universales
    peers = scoring_data.get("benchmarks_used", {}).get("peers_detail", [])
    target_peer = next((p for p in peers if p.get("is_target")), {})
    raw_shares = mkt.get("diluted_shares") or target_peer.get("shares_diluted")
    if not raw_shares and scoring_data.get("canonical_summary", {}).get("shares_diluted"):
        raw_shares = list(scoring_data["canonical_summary"]["shares_diluted"].values())[0]
    if not raw_shares:
        raw_shares = 1e8

    shares_b = raw_shares / 1e9 if raw_shares > 1e6 else (raw_shares / 1e3)
    shares_m = shares_b * 1000

    solvency = scoring_data.get("debt_and_solvency_analysis", {}).get("cash_flow_leverage", {}).get("LTM", {})
    if not solvency:
        solvency = scoring_data.get("debt_and_solvency_analysis", {}).get("latest_result", {}).get("cash_flow_leverage", {})
        
    net_debt_m = solvency.get("net_debt", 0.0)

    # Resolución canónica universal de Deuda Neta deduciendo efectivo y valores negociables corrientes
    if fs_obj:
        try:
            canon_sum = fs_obj.get("canonical_summary", {})
            bs_det = fs_obj.get("balance_sheet_detail", {})
            tot_d = canon_sum.get("total_debt", {}).get("LTM")
            if tot_d is None and canon_sum.get("total_debt"):
                tot_d = list(canon_sum["total_debt"].values())[0]
            c_eq = canon_sum.get("cash_and_equivalents", {}).get("LTM")
            if c_eq is None and canon_sum.get("cash_and_equivalents"):
                c_eq = list(canon_sum["cash_and_equivalents"].values())[0]
            c_eq = c_eq or 0.0
            st_inv_val = canon_sum.get("short_term_investments", {}).get("LTM")
            if st_inv_val is None:
                for tag in ["MarketableSecuritiesCurrent", "us-gaap_MarketableSecuritiesCurrent", "ShortTermInvestments"]:
                    if tag in bs_det:
                        v_det = bs_det[tag].get("values", bs_det[tag]).get("LTM")
                        if v_det is not None and v_det > 0:
                            st_inv_val = float(v_det)
                            break
            st_inv_val = st_inv_val or 0.0
            if tot_d is not None:
                debt_m = tot_d / 1e6 if abs(tot_d) > 1e6 else tot_d
                liq_m = (c_eq + st_inv_val) / 1e6 if abs(c_eq + st_inv_val) > 1e6 else (c_eq + st_inv_val)
                net_debt_m = round(debt_m - liq_m, 1)
        except Exception:
            pass

    # -------------------------------------------------------------
    # RUTA BANCARIA / FINTECH / SEGUROS
    # -------------------------------------------------------------
    if is_fin:
        tbv_total_m = wacc_dict.get("tangible_book_value_usd_m")
        if not tbv_total_m and fs_obj:
            try:
                canon = fs_obj.get("canonical_summary", {})
                eq_dict = canon.get("stockholders_equity", {})
                if eq_dict:
                    recent_k = list(eq_dict.keys())[0]
                    val_raw = eq_dict[recent_k]
                    tbv_total_m = (val_raw / 1e6) if abs(val_raw) > 1e6 else val_raw
            except Exception:
                pass
        if not tbv_total_m:
            tbv_total_m = 0.0
        
        tbv_per_share = round(tbv_total_m / shares_m, 2) if (shares_m > 0 and tbv_total_m > 0) else 0.0
        ptbv_current = round(price / tbv_per_share, 2) if (tbv_per_share > 0) else 0.0
        
        # ROTCE / ROE auditado real
        if is_ins:
            rotce_val = wacc_dict.get("roe") or wacc_dict.get("rotce")
        else:
            rotce_val = wacc_dict.get("rotce") or wacc_dict.get("roe")

        if rotce_val is None:
            sc_dict = {r[0]: r for r in prof.get("scorecard", {}).get("data", [])}
            ret_key = "Retorno sobre Fondos Propios (ROE)" if is_ins else "Retorno sobre Patrimonio Tangible (ROTCE)"
            rotce_str = sc_dict.get(ret_key, ["", ""])[1]
            if not rotce_str:
                rotce_str = sc_dict.get("Retorno sobre Patrimonio Tangible (ROTCE)", ["", ""])[1]
            try:
                rotce_val = float(rotce_str.replace("%", "").strip()) / 100.0
            except Exception:
                rotce_val = 0.15
            
        # Cálculo dinámico de CAGR para entidades financieras si tienen serie de ingresos
        fin_rev_map = (fs_obj or {}).get("canonical_summary", {}).get("revenue", {})
        fin_yr_list = sorted(
            [k for k in fin_rev_map.keys() if k.startswith("FY") and fin_rev_map[k] and fin_rev_map[k] > 0],
            key=lambda x: int(x.replace("FY", "")) if x.replace("FY", "").isdigit() else 0
        )
        fin_calc_cagr_5y = None
        if len(fin_yr_list) >= 6 and fin_rev_map.get(fin_yr_list[-6]) and fin_rev_map[fin_yr_list[-6]] > 0:
            fin_calc_cagr_5y = round((((fin_rev_map[fin_yr_list[-1]] / fin_rev_map[fin_yr_list[-6]]) ** (1.0 / 5.0)) - 1.0) * 100.0, 1)
        elif len(fin_yr_list) >= 2 and fin_rev_map.get(fin_yr_list[0]) and fin_rev_map[fin_yr_list[0]] > 0:
            fin_calc_cagr_5y = round((((fin_rev_map[fin_yr_list[-1]] / fin_rev_map[fin_yr_list[0]]) ** (1.0 / float(len(fin_yr_list) - 1))) - 1.0) * 100.0, 1)

        cagr_5y_dyn = fin_calc_cagr_5y if fin_calc_cagr_5y is not None else (prof.get("cagr_5y") or target_peer.get("cagr_5y"))
        cagr_10y_dyn = prof.get("cagr_10y") or target_peer.get("cagr_10y")
        cagr_3y_dyn = prof.get("cagr_3y") or target_peer.get("cagr_3y")
        guidance_dyn = prof.get("guidance_mid") or target_peer.get("guidance_mid")

        g_term = 0.030
        spread_rotce_ke = rotce_val - ke_val
        ptbv_justified = compute_two_stage_excess_return_ptbv(
            rotce_val=rotce_val,
            ke_val=ke_val,
            g_term=g_term,
            cagr_5y=cagr_5y_dyn,
            is_insurance=is_ins
        )
        fair_value_excess_return = round(ptbv_justified * tbv_per_share, 2) if tbv_per_share > 0 else 0.0
        rotce_implied = round(((ptbv_current * (ke_val - g_term)) + g_term) * 100, 1) if ptbv_current > 0 else 0.0

        # Pasos de sensibilidad dinámicos centrados en rotce_val real
        center_r = rotce_val if (rotce_val and rotce_val > 0) else ke_val
        base_r = round(center_r, 4)
        rotce_rates = [round(max(0.04, base_r + step), 3) for step in [-0.06, -0.04, -0.02, 0.0, 0.02, 0.04]]
        rotce_labels = [f"{r*100:.1f}%" if r != base_r else f"{r*100:.1f}% (Base)" for r in rotce_rates]

        fair_price_base = fair_value_excess_return if fair_value_excess_return > 0 else price
        hist_growth_pct_val = float(cagr_5y_dyn or 0.0)
        g_implied_dec = rotce_implied / 100.0
        gap_exp_pp = (g_implied_dec - rotce_val) * 100.0
        premium_pct_val = ((price - fair_price_base) / fair_price_base) * 100.0 if fair_price_base > 0 else 0.0
        if premium_pct_val > 25.0:
            val_status = "SOBREVALORADA"
        elif premium_pct_val < -15.0:
            val_status = "INFRAVALORADA"
        else:
            val_status = "JUSTO"

        # Métricas complementarias de valoración bancaria/aseguradora
        fin_canon = (fs_obj or {}).get("canonical_summary", {})
        eps_diluted_fin = fin_canon.get("eps_diluted_adjusted", {}).get("LTM") or 0.0
        cagr_eps_fin = _compute_series_cagr(fin_canon.get("eps_diluted_adjusted"), 5)
        buyback_rate_fin = _compute_share_reduction_rate(fin_canon.get("shares_diluted_adjusted"), 5)
        div_ltm_fin = fin_canon.get("dividends_paid", {}).get("LTM") or 0.0
        div_m_fin = abs(float(div_ltm_fin)) / 1e6 if (div_ltm_fin and abs(float(div_ltm_fin)) > 1e6) else float(div_ltm_fin or 0.0)
        div_yield_fin = round((div_m_fin / (price * shares_m) * 100.0), 2) if (price * shares_m) > 0 else 0.0

        multiples_fin = calculate_multiples_valuation(
            price=price,
            shares_m=shares_m,
            net_debt_m=0.0,
            base_rev_m=tbv_total_m,
            ebit_m=0.0,
            ebitda_m=0.0,
            net_income_m=tbv_total_m * rotce_val,
            fcf_m=0.0,
            eps_diluted=eps_diluted_fin,
            cagr_5y=cagr_5y_dyn,
            cagr_eps_5y=cagr_eps_fin,
            peers_detail=peers,
            is_financial=True,
            tbv_per_share=tbv_per_share,
            ptbv_justified=ptbv_justified,
        )

        sustainable_ni_fin = tbv_total_m * rotce_val
        epv_eq_fin = (sustainable_ni_fin / ke_val) if ke_val > 0 else tbv_total_m
        epv_ps_fin = round(max(0.01, epv_eq_fin / shares_m), 2) if shares_m > 0 else 0.0
        pvgo_ps_fin = round(max(0.0, price - epv_ps_fin), 2)
        epv_pct_fin = round(min(100.0, max(0.0, (epv_ps_fin / price) * 100.0)), 1) if price > 0 else 100.0
        pvgo_pct_fin = round(max(0.0, 100.0 - epv_pct_fin), 1)

        epv_fin = {
            "epv_operating_m": round(epv_eq_fin, 1),
            "epv_equity_m": round(epv_eq_fin, 1),
            "epv_per_share": epv_ps_fin,
            "pvgo_per_share": pvgo_ps_fin,
            "epv_pct": epv_pct_fin,
            "pvgo_pct": pvgo_pct_fin,
            "status": "CRECIMIENTO GRATIS (EPV ≥ Precio)" if epv_ps_fin >= price else ("ALTA PROTECCIÓN DE BENEFICIOS" if pvgo_pct_fin <= 35.0 else "ALTA DEPENDENCIA DE CRECIMIENTO"),
            "sustainable_nopat_m": round(sustainable_ni_fin, 1),
        }

        eva_fin = {
            "fair_price_eva": fair_value_excess_return,
            "ev_eva": round(tbv_total_m * ptbv_justified, 1),
            "ic_base_m": round(tbv_total_m, 1),
            "pv_eva_sum": round(max(0.0, fair_value_excess_return - tbv_per_share) * shares_m, 1),
            "pv_terminal_eva": 0.0,
            "spread_pct": round(spread_rotce_ke * 100.0, 2),
        }

        retention_fin = 0.50 if not is_ins else 0.45
        g_tbv_fin = rotce_val * retention_fin
        tbv_5y_fin = tbv_per_share * ((1.0 + g_tbv_fin) ** 5)
        target_5y_fin = round(tbv_5y_fin * ptbv_justified, 2)
        price_cagr_fin = ((target_5y_fin / price) ** (1.0 / 5.0)) - 1.0 if price > 0 else 0.0
        irr_fin = price_cagr_fin + (div_yield_fin / 100.0)

        forward_5y_fin = {
            "target_price_5y": target_5y_fin,
            "forward_irr_pct": round(irr_fin * 100.0, 2),
            "price_cagr_pct": round(price_cagr_fin * 100.0, 2),
            "total_return_pct": round(((target_5y_fin * ((1.0 + div_yield_fin/100.0)**5) - price) / price) * 100.0, 1) if price > 0 else 0.0,
            "fcf_per_share_5y": round(tbv_5y_fin, 2),
            "shares_5y_m": shares_m,
            "rev_5y_m": round(tbv_total_m * ((1.0 + g_tbv_fin)**5), 1),
            "bridge": {
                "growth_contrib": round(g_tbv_fin * 100.0, 2),
                "margin_contrib": 0.0,
                "buyback_contrib": round(buyback_rate_fin, 2),
                "multiple_contrib": 0.0,
                "div_contrib": div_yield_fin,
            }
        }

        football_field_fin = get_valuation_football_field(
            price=price,
            dcf_price=fair_value_excess_return,
            multiples_price=multiples_fin["imputed_prices"]["composite"],
            epv_price=epv_ps_fin,
            eva_price=fair_value_excess_return,
            target_5y_price=target_5y_fin,
            ke_val=ke_val,
        )

        return {
            "is_financial": True,
            "is_insurance": is_ins,
            "archetype": arch,
            "price": price,
            "shares_b": round(shares_b, 4),
            "shares_m": round(shares_m, 1),
            "rf_pct": rf_pct,
            "erp_pct": round(erp * 100, 2),
            "beta": beta,
            "ke_val": ke_val,
            "ke_pct": round(ke_val * 100, 2),
            "tangible_equity_m": tbv_total_m,
            "tbv_per_share": tbv_per_share,
            "ptbv_current": ptbv_current,
            "rotce_val": rotce_val,
            "rotce_pct": round(rotce_val * 100, 2),
            "rotce_rates": rotce_rates,
            "rotce_labels": rotce_labels,
            "g_terminal_pct": round(g_term * 100, 2),
            "spread_economic_pct": round(spread_rotce_ke * 100, 2),
            "ptbv_justified": ptbv_justified,
            "fair_value_excess_return": fair_value_excess_return,
            "fair_price_base": fair_price_base,
            "rotce_implied_pct": rotce_implied,
            "g_implied_pct": rotce_implied,
            "g_implied_3stage_pct": rotce_implied,
            "implied_cap_years": 10.0,
            "fcf_margin_true_pct": 0.0,
            "sbc_usd_m": 0.0,
            "sbc_margin_pct": 0.0,
            "hist_growth_pct": hist_growth_pct_val,
            "init_growth_disp": round(rotce_val * 100, 2),
            "gap_expectations_str": f"{'+' if gap_exp_pp >= 0 else ''}{gap_exp_pp:.1f} pp",
            "premium_pct": premium_pct_val,
            "valuation_status": val_status,
            "rev_base": tbv_total_m,
            "fcf_margin_pct": 0.0,
            "net_debt_m": 0.0,
            "cagr_5y": cagr_5y_dyn,
            "cagr_10y": cagr_10y_dyn,
            "cagr_3y": cagr_3y_dyn,
            "guidance_mid": guidance_dyn,
            "multiples_analysis": multiples_fin,
            "epv_analysis": epv_fin,
            "eva_analysis": eva_fin,
            "forward_5y_analysis": forward_5y_fin,
            "football_field": football_field_fin,
            "dividend_yield_pct": div_yield_fin,
            "buyback_rate_pct": buyback_rate_fin,
        }

    # -------------------------------------------------------------
    # RUTA CORPORATIVA TRADICIONAL & HÍBRIDOS (MELI)
    # -------------------------------------------------------------
    base_rev_m = 0.0
    if fs_obj:
        try:
            rev_map = fs_obj.get("canonical_summary", {}).get("revenue", {})
            if rev_map:
                val_r = rev_map.get("LTM")
                if not val_r:
                    fy_keys = sorted([k for k in rev_map.keys() if k.startswith("FY") and rev_map[k]], reverse=True)
                    if fy_keys:
                        val_r = rev_map[fy_keys[0]]
                if val_r:
                    base_rev_m = (val_r / 1e6) if abs(val_r) > 1e6 else float(val_r)
        except Exception:
            pass
    if base_rev_m <= 0:
        base_rev_m = target_peer.get("revenue_usd_m") or solvency.get("revenue") or 100.0

    s_ebit = solvency.get("ebit") or 0.0
    s_capex = solvency.get("capex") or 0.0
    s_fcf = solvency.get("fcf") or 0.0
    s_dna = solvency.get("dna") or 0.0
    dna_margin = (s_dna / base_rev_m) if (base_rev_m > 0 and s_dna > 0) else 0.025
    
    ebit_margin = (s_ebit / base_rev_m) if (base_rev_m > 0 and s_ebit > 0) else 0.20
    capex_margin = (s_capex / base_rev_m) if (base_rev_m > 0 and s_capex > 0) else 0.02
    op_fcf_margin = max(0.05, ebit_margin * (1.0 - tax_rate) + dna_margin - capex_margin)
    
    # Margen FCF auditado real derivado de los estados financieros de la compañía
    kr_fcf = None
    if fs_obj:
        kr_fcf = fs_obj.get("key_ratios", {}).get("fcf_margin_pct", {}).get("LTM")
        if kr_fcf is None:
            fy_keys = sorted([k for k in fs_obj.get("key_ratios", {}).get("fcf_margin_pct", {}).keys() if k.startswith("FY") and fs_obj["key_ratios"]["fcf_margin_pct"][k] is not None], reverse=True)
            if fy_keys:
                kr_fcf = fs_obj["key_ratios"]["fcf_margin_pct"][fy_keys[0]]

    raw_fcf_margin = (float(kr_fcf) / 100.0) if (kr_fcf is not None and float(kr_fcf) > 0) else ((s_fcf / base_rev_m) if (s_fcf > 0 and base_rev_m > 0) else op_fcf_margin)
    if arch == "PLATFORM_ECOSYSTEM" and raw_fcf_margin > (op_fcf_margin * 1.5):
        # En ecosistemas híbridos E-Commerce + FinTech, aislar el flujo operativo comercial/fintech sin depósitos de terceros
        fcf_margin = round((op_fcf_margin * 0.65) + (min(raw_fcf_margin, 0.18) * 0.35), 4)
    else:
        fcf_margin = raw_fcf_margin
    
    # Cálculo dinámico de CAGRs históricos de ingresos con separación estricta de períodos anuales completos:
    calc_cagr_5y = None
    calc_cagr_3y = None
    calc_cagr_10y = None
    if fs_obj:
        try:
            rev_map = fs_obj.get("canonical_summary", {}).get("revenue", {})
            yr_list = sorted(
                [k for k in rev_map.keys() if k.startswith("FY") and rev_map[k] and rev_map[k] > 0],
                key=lambda x: int(x.replace("FY", "")) if x.replace("FY", "").isdigit() else 0
            )
            if len(yr_list) >= 2:
                r_last = rev_map[yr_list[-1]]
                if len(yr_list) >= 6 and rev_map.get(yr_list[-6]) and rev_map[yr_list[-6]] > 0:
                    calc_cagr_5y = round((((r_last / rev_map[yr_list[-6]]) ** (1.0 / 5.0)) - 1.0) * 100.0, 1)
                elif len(yr_list) >= 2 and rev_map.get(yr_list[0]) and rev_map[yr_list[0]] > 0:
                    n_years = len(yr_list) - 1
                    calc_cagr_5y = round((((r_last / rev_map[yr_list[0]]) ** (1.0 / float(n_years))) - 1.0) * 100.0, 1)

                if len(yr_list) >= 4 and rev_map.get(yr_list[-4]) and rev_map[yr_list[-4]] > 0:
                    calc_cagr_3y = round((((r_last / rev_map[yr_list[-4]]) ** (1.0 / 3.0)) - 1.0) * 100.0, 1)
                if len(yr_list) >= 11 and rev_map.get(yr_list[-11]) and rev_map[yr_list[-11]] > 0:
                    calc_cagr_10y = round((((r_last / rev_map[yr_list[-11]]) ** (1.0 / 10.0)) - 1.0) * 100.0, 1)
        except Exception:
            pass

    cagr_5y = calc_cagr_5y if calc_cagr_5y is not None else (prof.get("cagr_5y") or target_peer.get("cagr_5y"))
    cagr_10y = calc_cagr_10y if calc_cagr_10y is not None else (prof.get("cagr_10y") or target_peer.get("cagr_10y"))
    cagr_3y = calc_cagr_3y if calc_cagr_3y is not None else (prof.get("cagr_3y") or target_peer.get("cagr_3y"))
    guidance_mid = prof.get("guidance_mid") or target_peer.get("guidance_mid")
    
    g_implied_our = solve_reverse_dcf(
        share_price=price,
        shares_out_b=shares_b,
        net_debt_m=net_debt_m,
        base_revenue_m=base_rev_m,
        wacc=wacc_val,
        terminal_growth=0.025,
        fcf_margin=fcf_margin,
        forecast_years=10
    )
    
    g_implied_fiscal = solve_reverse_dcf(
        share_price=price,
        shares_out_b=shares_b,
        net_debt_m=net_debt_m,
        base_revenue_m=base_rev_m,
        wacc=0.1090,
        terminal_growth=0.025,
        fcf_margin=0.244,
        forecast_years=10
    )
    
    gap_hist = round((g_implied_our * 100) - cagr_5y, 1) if cagr_5y is not None else None
    gap_guide = round((g_implied_our * 100) - guidance_mid, 1) if guidance_mid is not None else None

    # Cálculo canónico del Valor Intrínseco Teórico Base (DCF a 10 años con Gordon-Shapiro)
    hist_growth_pct_val = float(cagr_5y or 0.0)
    hist_growth_dec = hist_growth_pct_val / 100.0
    gn_dec = 0.025
    init_proj_growth = min(hist_growth_dec, 0.20) if hist_growth_dec > 0.20 else max(hist_growth_dec, -0.05)
    pv_fcf = 0.0
    r_t = base_rev_m
    for t in range(1, 11):
        r_t *= (1.0 + init_proj_growth)
        pv_fcf += (r_t * fcf_margin) / ((1.0 + wacc_val) ** t)
    tv = (r_t * (1.0 + gn_dec) * fcf_margin) / max(wacc_val - gn_dec, 0.005)
    pv_tv = tv / ((1.0 + wacc_val) ** 10)
    ev_total = pv_fcf + pv_tv
    equity_val = ev_total - net_debt_m
    shares_m_rounded = round(round(shares_b, 4) * 1000, 2)
    fair_price_base = equity_val / shares_m_rounded if shares_m_rounded > 0 else price

    g_implied_our_pct_rounded = round(g_implied_our * 100, 1)
    g_implied_dec = g_implied_our_pct_rounded / 100.0
    gap_exp_pp = (g_implied_dec - init_proj_growth) * 100.0
    premium_pct_val = ((price - fair_price_base) / fair_price_base) * 100.0 if fair_price_base > 0 else 0.0
    if premium_pct_val > 25.0:
        val_status = "SOBREVALORADA"
    elif premium_pct_val < -15.0:
        val_status = "INFRAVALORADA"
    else:
        val_status = "JUSTO"

    # -------------------------------------------------------------------------
    # MEJORAS INSTITUCIONALES REVERSE DCF (True FCF ex-SBC, 3-Stage Fade & CAP)
    # -------------------------------------------------------------------------
    canon_sum = (fs_obj or {}).get("canonical_summary", {})
    sbc_raw = canon_sum.get("stock_based_compensation", {}).get("LTM")
    if sbc_raw is None and canon_sum.get("stock_based_compensation"):
        sbc_raw = list(canon_sum["stock_based_compensation"].values())[0]
    sbc_usd_m = (abs(float(sbc_raw)) / 1e6) if (sbc_raw and abs(float(sbc_raw)) > 1e6) else float(sbc_raw or 0.0)
    sbc_margin_pct = round((sbc_usd_m / base_rev_m) * 100.0, 2) if base_rev_m > 0 else 0.0
    fcf_margin_true_pct = round(max(1.0, (fcf_margin * 100.0) - sbc_margin_pct), 2)
    fcf_margin_true = fcf_margin_true_pct / 100.0

    # Reverse DCF de 3 Etapas con Fade Competitivo (Damodaran & Mauboussin)
    g_implied_3stage = solve_reverse_dcf_3stage(
        share_price=price,
        shares_out_b=shares_b,
        net_debt_m=net_debt_m,
        base_revenue_m=base_rev_m,
        wacc=wacc_val,
        terminal_growth=0.025,
        fcf_margin=fcf_margin,
        forecast_years=10,
        fade_start_year=5
    )
    g_implied_3stage_pct = round(g_implied_3stage * 100.0, 1)

    g_implied_3stage_true = solve_reverse_dcf_3stage(
        share_price=price,
        shares_out_b=shares_b,
        net_debt_m=net_debt_m,
        base_revenue_m=base_rev_m,
        wacc=wacc_val,
        terminal_growth=0.025,
        fcf_margin=fcf_margin_true,
        forecast_years=10,
        fade_start_year=5
    )
    g_implied_3stage_true_pct = round(g_implied_3stage_true * 100.0, 1)

    # Detalle de Valor Terminal y Auditoría de Flujos
    dcf_details_2stage = calculate_dcf_details(base_rev_m, init_proj_growth, fcf_margin, wacc_val, gn_dec, net_debt_m, shares_m_rounded, model_type="2STAGE")
    dcf_details_3stage = calculate_dcf_details(base_rev_m, init_proj_growth, fcf_margin, wacc_val, gn_dec, net_debt_m, shares_m_rounded, model_type="3STAGE")

    # Años de Ventaja Competitiva Implícita (Implied CAP - Mauboussin Runway)
    implied_cap_years = calculate_implied_cap(
        share_price=price,
        shares_b=shares_b,
        net_debt_m=net_debt_m,
        base_revenue_m=base_rev_m,
        wacc=wacc_val,
        base_growth=init_proj_growth,
        fcf_margin=fcf_margin
    )

    # -------------------------------------------------------------------------
    # 4 NUEVOS PILARES DE VALORACIÓN (Múltiplos, EPV, EVA & 5Y Forward IRR)
    # -------------------------------------------------------------------------
    eps_diluted_val = canon_sum.get("eps_diluted_adjusted", {}).get("LTM") or 0.0
    if not eps_diluted_val and canon_sum.get("eps_diluted_adjusted"):
        eps_diluted_val = list(canon_sum["eps_diluted_adjusted"].values())[0] or 0.0
    cagr_eps_5y = _compute_series_cagr(canon_sum.get("eps_diluted_adjusted"), 5)
    cagr_fcf_5y = _compute_series_cagr(canon_sum.get("free_cash_flow"), 5)
    buyback_rate_pct = _compute_share_reduction_rate(canon_sum.get("shares_diluted_adjusted"), 5)

    div_ltm_raw = canon_sum.get("dividends_paid", {}).get("LTM")
    if div_ltm_raw is None and canon_sum.get("dividends_paid"):
        div_ltm_raw = list(canon_sum["dividends_paid"].values())[0]
    div_m = abs(float(div_ltm_raw)) / 1e6 if (div_ltm_raw and abs(float(div_ltm_raw)) > 1e6) else float(div_ltm_raw or 0.0)
    dividend_yield_pct = round((div_m / (price * shares_m_rounded) * 100.0), 2) if (price * shares_m_rounded) > 0 else 0.0

    net_inc_raw = canon_sum.get("net_income", {}).get("LTM")
    net_inc_m = (float(net_inc_raw) / 1e6) if (net_inc_raw and abs(float(net_inc_raw)) > 1e6) else float(net_inc_raw or 0.0)
    ebitda_val = s_ebit + s_dna if (s_ebit > 0 or s_dna > 0) else (base_rev_m * (ebit_margin + dna_margin))

    # Pilar A: Múltiplos
    multiples_analysis = calculate_multiples_valuation(
        price=price,
        shares_m=shares_m_rounded,
        net_debt_m=net_debt_m,
        base_rev_m=base_rev_m,
        ebit_m=s_ebit if s_ebit > 0 else (base_rev_m * ebit_margin),
        ebitda_m=ebitda_val,
        net_income_m=net_inc_m,
        fcf_m=base_rev_m * fcf_margin,
        eps_diluted=eps_diluted_val,
        cagr_5y=cagr_5y,
        cagr_eps_5y=cagr_eps_5y,
        cagr_fcf_5y=cagr_fcf_5y,
        peers_detail=peers,
        is_financial=False
    )

    # Pilar B: EPV & PVGO
    epv_analysis = calculate_epv_pvgo(
        base_revenue_m=base_rev_m,
        ebit_margin=ebit_margin,
        tax_rate=tax_rate,
        sbc_usd_m=sbc_usd_m,
        wacc=wacc_val,
        net_debt_m=net_debt_m,
        shares_m=shares_m_rounded,
        current_price=price
    )

    # Pilar C: EVA (Beneficio Económico sobre Capital Invertido)
    ic_val = 0.0
    roic_periods = scoring_data.get("roic_wacc_analysis", {}).get("roic", {}).get("by_period", {})
    if roic_periods:
        latest_k = sorted(list(roic_periods.keys()))[-1]
        ic_val = float(roic_periods[latest_k].get("ic_adj_end", 0.0))
    if ic_val <= 0:
        ic_val = max(100.0, base_rev_m * 0.70)
    roic_used = scoring_data.get("wacc_analysis", {}).get("roic_adjusted") or 0.22
    eva_analysis = calculate_eva_valuation(
        invested_capital_m=ic_val,
        roic_val=roic_used,
        wacc_val=wacc_val,
        net_debt_m=net_debt_m,
        shares_m=shares_m_rounded
    )

    # Pilar D: Simulador 5Y Forward IRR
    exit_pe_ref = multiples_analysis.get("normal_pe") or 22.0
    forward_5y_analysis = calculate_5y_forward_irr(
        price=price,
        base_revenue_m=base_rev_m,
        revenue_growth_pct=cagr_5y if cagr_5y is not None else (init_proj_growth * 100.0),
        fcf_margin_pct=fcf_margin * 100.0,
        shares_m=shares_m_rounded,
        net_buyback_yield_pct=buyback_rate_pct,
        exit_multiple=exit_pe_ref,
        dividend_yield_pct=dividend_yield_pct,
        base_fcf_margin_pct=fcf_margin * 100.0,
        current_multiple=multiples_analysis.get("pe_current")
    )

    # Resumen Ejecutivo: Valuation Football Field
    football_field = get_valuation_football_field(
        price=price,
        dcf_price=fair_price_base,
        multiples_price=multiples_analysis["imputed_prices"]["composite"],
        epv_price=epv_analysis["epv_per_share"],
        eva_price=eva_analysis["fair_price_eva"],
        target_5y_price=forward_5y_analysis["target_price_5y"],
        ke_val=wacc_val
    )

    return {
        "is_financial": False,
        "price": price,
        "rf_pct": rf_pct,
        "erp_pct": round(erp * 100, 2),
        "beta": beta,
        "kd_pre_pct": round(kd_pre * 100, 2),
        "kd_post_pct": round(kd_post * 100, 2),
        "tax_rate_pct": round(tax_rate * 100, 1),
        "weight_debt_pct": round(wd * 100, 1),
        "weight_equity_pct": round(we * 100, 1),
        "wacc_pct": wacc_pct,
        "wacc_val": wacc_val,
        "ebit_margin": ebit_margin,
        "fcf_margin": fcf_margin,
        "fcf_margin_reported_pct": round(raw_fcf_margin * 100, 1),
        "fcf_margin_audited": fcf_margin,
        "capex_margin": capex_margin,
        "ebit_margin_pct": round(ebit_margin * 100, 1),
        "fcf_margin_pct": round(fcf_margin * 100, 1),
        "fcf_margin_audited_pct": round(fcf_margin * 100, 1),
        "fcf_margin_operating_pct": round(op_fcf_margin * 100, 1),
        "capex_margin_pct": round(capex_margin * 100, 1),
        "shares_b": round(shares_b, 4),
        "shares_m": shares_m_rounded,
        "net_debt_m": net_debt_m,
        "base_rev_m": base_rev_m,
        "rev_base": base_rev_m,
        "cagr_5y": cagr_5y,
        "cagr_10y": cagr_10y,
        "cagr_3y": cagr_3y,
        "guidance_mid": guidance_mid,
        "g_implied_our_pct": g_implied_our_pct_rounded,
        "g_implied_fiscal_pct": round(g_implied_fiscal * 100, 1),
        "gap_hist": round(gap_hist, 1) if gap_hist is not None else None,
        "gap_guide": round(gap_guide, 1) if gap_guide is not None else None,
        "fair_price_base": fair_price_base,
        "valuation_status": val_status,
        "premium_pct": premium_pct_val,
        "g_implied_pct": g_implied_our_pct_rounded,
        "hist_growth_pct": hist_growth_pct_val,
        "init_growth_disp": init_proj_growth * 100.0,
        "gap_expectations_str": f"{'+' if gap_exp_pp >= 0 else ''}{gap_exp_pp:.1f} pp",
        # Nuevas Métricas Institucionales
        "sbc_usd_m": sbc_usd_m,
        "sbc_margin_pct": sbc_margin_pct,
        "fcf_margin_true_pct": fcf_margin_true_pct,
        "fcf_margin_true": fcf_margin_true,
        "g_implied_3stage_pct": g_implied_3stage_pct,
        "g_implied_3stage_true_pct": g_implied_3stage_true_pct,
        "implied_cap_years": implied_cap_years,
        "dcf_details_2stage": dcf_details_2stage,
        "dcf_details_3stage": dcf_details_3stage,
        "cagr_eps_5y": cagr_eps_5y,
        "cagr_fcf_5y": cagr_fcf_5y,
        "buyback_rate_pct": buyback_rate_pct,
        "dividend_yield_pct": dividend_yield_pct,
        "multiples_analysis": multiples_analysis,
        "epv_analysis": epv_analysis,
        "eva_analysis": eva_analysis,
        "forward_5y_analysis": forward_5y_analysis,
        "football_field": football_field,
    }


def _generate_sensitivity_grid(vp: Dict[str, Any]) -> List[Tuple[str, str, str, str, str, str, str, str]]:
    """Calcula dinámicamente la matriz de sensibilidad según el arquetipo de negocio."""
    if vp.get("is_financial"):
        # Sensibilidad Financiera / Aseguradora: Ke vs Retorno Sostenible (ROTCE / ROE)
        ke_base = vp.get("ke_val", 0.0943)
        ke_steps = [
            (ke_base - 0.010, f"{round((ke_base - 0.010)*100, 2):.2f}% (Bajo / Optimista)"),
            (ke_base - 0.005, f"{round((ke_base - 0.005)*100, 2):.2f}% (Favorable)"),
            (ke_base, f"{vp['ke_pct']:.2f}% (Ke Auditado Base)"),
            (ke_base + 0.005, f"{round((ke_base + 0.005)*100, 2):.2f}% (Exigente)"),
            (ke_base + 0.010, f"{round((ke_base + 0.010)*100, 2):.2f}% (Estrés Macro / Tipos)")
        ]
        rotce_rates = vp.get("rotce_rates") or [0.18, 0.20, 0.22, 0.24, 0.26, 0.28]
        g_term = (vp.get("g_terminal_pct", 3.0) / 100.0)
        tbv_ps = vp.get("tbv_per_share", 0.0)
        
        grid_rows = []
        for ke_val_step, ke_label in ke_steps:
            row_vals = [ke_label]
            for r_val in rotce_rates:
                if ke_val_step > g_term:
                    ptbv_calc = compute_two_stage_excess_return_ptbv(
                        rotce_val=r_val,
                        ke_val=ke_val_step,
                        g_term=g_term,
                        cagr_5y=vp.get("cagr_5y"),
                        is_insurance=vp.get("is_insurance", False)
                    )
                    fv_calc = round(ptbv_calc * tbv_ps, 2) if tbv_ps > 0 else ptbv_calc
                    row_vals.append(f"${fv_calc:.2f}" if tbv_ps > 0 else f"{ptbv_calc:.2f}x")
                else:
                    row_vals.append("N/D")
            
            if "Base" in ke_label:
                row_vals.append("ESCENARIO CENTRAL: Valor teórico fundamental por rentabilidad de balance.")
            elif "Bajo" in ke_label:
                row_vals.append("Favorable: Expansión de múltiplos por menor prima de riesgo.")
            elif "Estrés" in ke_label:
                row_vals.append("Estrés: Contracción por alza de tipos de interés o riesgo soberano.")
            else:
                row_vals.append("Escenario de sensibilidad financiera.")
            grid_rows.append(tuple(row_vals))
        return grid_rows

    # Matriz Corporativa Tradicional: WACC vs gn
    base_wacc = vp.get("wacc_val") or (vp.get("wacc_pct", 9.5) / 100.0)
    wacc_steps = [
        (base_wacc - 0.010, f"{round((base_wacc - 0.010)*100, 2):.2f}% (Bajo / Expansión)"),
        (base_wacc - 0.005, f"{round((base_wacc - 0.005)*100, 2):.2f}% (Favorable)"),
        (base_wacc, f"{vp['wacc_pct']:.2f}% (WACC Auditado Base)"),
        (base_wacc + 0.005, f"{round((base_wacc + 0.005)*100, 2):.2f}% (Exigente)"),
        (base_wacc + 0.010, f"{round((base_wacc + 0.010)*100, 2):.2f}% (Estrés / Tipos Altos)")
    ]
    terminal_rates = [0.010, 0.015, 0.020, 0.025, 0.030, 0.035]
    fcf_m = vp.get("fcf_margin") or (vp.get("fcf_margin_pct", 20.0) / 100.0)
    
    grid_rows = []
    for w_val, w_label in wacc_steps:
        row_vals = [w_label]
        for g_term in terminal_rates:
            g_sol = solve_reverse_dcf(
                share_price=vp["price"],
                shares_out_b=vp["shares_b"],
                net_debt_m=vp["net_debt_m"],
                base_revenue_m=vp["base_rev_m"],
                wacc=w_val,
                terminal_growth=g_term,
                fcf_margin=fcf_m,
                forecast_years=10
            )
            row_vals.append(f"{g_sol * 100.0:.1f}%")
            
        if "Base" in w_label:
            row_vals.append("ESCENARIO CENTRAL: Crecimiento implícito real de mercado.")
        elif "Bajo" in w_label:
            row_vals.append("Escenario favorable; exigencia de crecimiento más moderada.")
        elif "Estrés" in w_label:
            row_vals.append("Vulnerabilidad a correcciones si el coste de capital aumenta.")
        else:
            row_vals.append("Escenario de sensibilidad operativa.")
            
        grid_rows.append(tuple(row_vals))
    return grid_rows
