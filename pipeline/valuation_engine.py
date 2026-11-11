# -*- coding: utf-8 -*-
"""
valuation_engine.py - Orquestador y fachada unificada de Modelado Financiero y Valuación Intrínseca:
Reverse DCF (Expectations Investing), Excess Return P/TBV vs ROTCE (Banca/Seguros),
Múltiplos Históricos, Owner Earnings, Z-Score y Sensibilidad Bidimensional.
Delega modelos matemáticos e histórico en pipeline/valuation_modules/ y clasificación al SSOT entity_classifier.
"""

import json
import logging
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_PIPELINE_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _PIPELINE_DIR.parent
for _p in (
    _PROJECT_ROOT,
    _PIPELINE_DIR,
    *(_PIPELINE_DIR / _s for _s in ("infra", "sec_modules", "audit_modules", "scoring_modules", "valuation_modules")),
):
    if _p.exists() and str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

try:
    from config_loader import DATA_PROCESSED_DIR, resolve_market_cache_path
    from entity_classifier import detect_company_archetype, normalize_archetype
    from json_io import atomic_json_write
    from valuation_modules import (
        _compute_series_cagr,
        _compute_share_reduction_rate,
        _fmt_money,
        _fmt_pct,
        build_audit_traceability,
        calculate_5y_forward_irr,
        calculate_dcf_details,
        calculate_epv_pvgo,
        calculate_eva_valuation,
        calculate_historical_multiples_analysis,
        calculate_multiples_valuation,
        calculate_owner_earnings_and_capex,
        calculate_z_score_valuation,
        compute_two_stage_excess_return_ptbv,
        get_valuation_football_field,
        solve_reverse_dcf,
        solve_reverse_dcf_3stage,
    )
except ImportError:
    from pipeline.config_loader import DATA_PROCESSED_DIR, resolve_market_cache_path
    from pipeline.entity_classifier import detect_company_archetype, normalize_archetype
    from pipeline.json_io import atomic_json_write
    from pipeline.valuation_modules import (
        _compute_series_cagr,
        _compute_share_reduction_rate,
        _fmt_money,
        _fmt_pct,
        build_audit_traceability,
        calculate_5y_forward_irr,
        calculate_dcf_details,
        calculate_epv_pvgo,
        calculate_eva_valuation,
        calculate_historical_multiples_analysis,
        calculate_multiples_valuation,
        calculate_owner_earnings_and_capex,
        calculate_z_score_valuation,
        compute_two_stage_excess_return_ptbv,
        get_valuation_football_field,
        solve_reverse_dcf,
        solve_reverse_dcf_3stage,
    )

logger = logging.getLogger(__name__)
DEFAULT_DATA_DIR = DATA_PROCESSED_DIR


def _resolve_processed_path(ticker: str, filename: str) -> Path:
    """Resuelve la ruta canónica del archivo en data/processed/{ticker}/ con invariancia de CWD."""
    p_abs = DEFAULT_DATA_DIR / ticker / filename
    if p_abs.exists():
        return p_abs
    p_rel = Path(f"data/processed/{ticker}/{filename}")
    return p_rel if p_rel.exists() else p_abs


def get_report_archetype(scoring_data: Dict[str, Any]) -> str:
    """Resuelve canónicamente el arquetipo contable delegando en el SSOT entity_classifier."""
    arch = scoring_data.get("archetype") or scoring_data.get("scoring_results", {}).get("archetype")
    if arch:
        return normalize_archetype(str(arch), default="STANDARD_CORPORATE")
    if scoring_data.get("is_financial_institution"):
        return "FINANCIAL_BANKING"

    bm = scoring_data.get("benchmarks_used", {}) or {}
    sic = str(scoring_data.get("sic_code") or bm.get("sic_code", "")).strip()
    ind_name = str(scoring_data.get("industry_name") or "").strip()
    business_model = str(scoring_data.get("business_model") or "").strip()
    if bm.get("gics_sector") == "Financials" and not sic:
        combined = f"{ind_name} {business_model}".upper()
        return "INSURANCE" if "INSUR" in combined else "FINANCIAL_BANKING"

    return detect_company_archetype(
        profile_data={
            "industry": ind_name,
            "sector": str(bm.get("gics_sector") or ""),
            "business_model": business_model,
        },
        sic_code=sic or None,
        balance_data=scoring_data.get("canonical_summary"),
    )


def get_solvency_archetype(scoring_data: Dict[str, Any]) -> str:
    """Clasifica el arquetipo de solvencia separando banca y seguros del bloque corporativo."""
    arch = get_report_archetype(scoring_data)
    return arch if arch in ("FINANCIAL_BANKING", "INSURANCE") else "CORPORATE"


def _is_financial(scoring_data: Dict[str, Any]) -> bool:
    """Identifica si la empresa pertenece al sector financiero/bancario/seguros."""
    return get_report_archetype(scoring_data) in ("FINANCIAL_BANKING", "INSURANCE")


def _extract_ltm_or_latest_fy(val_map: Optional[Dict[str, Any]]) -> Optional[float]:
    """Obtiene LTM o el ejercicio fiscal FY más reciente dentro de una serie canónica."""
    if not isinstance(val_map, dict) or not val_map:
        return None
    if val_map.get("LTM") is not None:
        return float(val_map["LTM"])
    fy_keys = sorted(
        [k for k, v in val_map.items() if str(k).startswith("FY") and v is not None],
        key=lambda k: int(re.search(r"(\d{4})", k).group(1)) if re.search(r"(\d{4})", k) else 0,
        reverse=True,
    )
    return float(val_map[fy_keys[0]]) if fy_keys else None


def _compute_rev_cagr(canon: Dict[str, Any], yrs_back: int) -> Optional[float]:
    """Calcula CAGR de ingresos a yrs_back años usando ejercicios fiscales FY completos."""
    return _compute_series_cagr(canon.get("revenue"), years=yrs_back) if yrs_back in (3, 5, 10) else None


def _load_valuation_inputs(
    scoring_data: Dict[str, Any],
    ticker: str,
    profile_data: Optional[Dict[str, Any]],
    fs_data: Optional[Dict[str, Any]],
) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
    """Carga company_profile.json y financial_statements.json locales si no fueron inyectados."""
    prof = dict(profile_data or {})
    if not prof and ticker:
        candidate = _resolve_processed_path(ticker, "company_profile.json")
        if candidate.exists():
            try:
                with open(candidate, "r", encoding="utf-8") as f:
                    prof = json.load(f)
            except (OSError, json.JSONDecodeError, TypeError) as exc:
                logger.debug("No se pudo cargar perfil %s: %s", candidate, exc)

    fs_obj = fs_data
    if fs_obj is None and ticker:
        fs_path = _resolve_processed_path(ticker, "financial_statements.json")
        if fs_path.exists():
            try:
                with open(fs_path, "r", encoding="utf-8") as f_fs:
                    fs_obj = json.load(f_fs)
            except (OSError, json.JSONDecodeError, TypeError) as exc:
                logger.debug("No se pudo cargar financial_statements %s: %s", fs_path, exc)
                fs_obj = None
    return prof, fs_obj


def _resolve_capital_structure_and_wacc(
    scoring_data: Dict[str, Any],
    prof: Dict[str, Any],
    live_price: Optional[float],
    is_fin: bool,
) -> Dict[str, Any]:
    """Consolida tasas de descuento (Rf, Beta, ERP, Ke, WACC), precio y acciones diluidas."""
    wacc_dict = (
        scoring_data.get("wacc_analysis")
        or scoring_data.get("wacc_and_spread_analysis")
        or scoring_data.get("roic_wacc_analysis", {}).get("wacc", {})
        or {}
    )
    mkt = wacc_dict.get("market_data", {}) or scoring_data.get("market_data", {}) or {}

    rf_raw = float(mkt["rf_10y"]) if mkt.get("rf_10y") is not None else 0.0425
    beta = round(float(mkt["beta"]), 2) if mkt.get("beta") is not None else 1.05
    erp = round(float(mkt["erp"]), 4) if mkt.get("erp") is not None else 0.0475
    ke_val = float(wacc_dict["cost_of_equity_ke"]) if wacc_dict.get("cost_of_equity_ke") is not None else (rf_raw + beta * erp)
    if is_fin:
        if beta < 0.80:
            beta = round(0.67 * beta + 0.33 * 1.0, 2)
        ke_val = max(ke_val, rf_raw + beta * erp, rf_raw + 0.0325)

    if live_price is not None and live_price > 0:
        price = round(float(live_price), 2)
    elif mkt.get("price") is not None and float(mkt["price"]) > 0:
        price = round(float(mkt["price"]), 2)
    elif prof.get("price") is not None and float(prof["price"]) > 0:
        price = round(float(prof["price"]), 2)
    else:
        price = 0.0

    wacc_val = float(wacc_dict["wacc"]) if wacc_dict.get("wacc") is not None else ke_val
    kd_pre = float(wacc_dict["cost_of_debt_kd_pre_tax"]) if wacc_dict.get("cost_of_debt_kd_pre_tax") is not None else 0.045
    kd_post = float(wacc_dict["cost_of_debt_kd_after_tax"]) if wacc_dict.get("cost_of_debt_kd_after_tax") is not None else 0.035
    tax_rate = float(wacc_dict["effective_tax_rate"]) if wacc_dict.get("effective_tax_rate") is not None else 0.20
    we = float(wacc_dict["weight_equity"]) if wacc_dict.get("weight_equity") is not None else (1.0 if is_fin else 0.95)
    wd = float(wacc_dict["weight_debt"]) if wacc_dict.get("weight_debt") is not None else (0.0 if is_fin else 0.05)

    peers = scoring_data.get("benchmarks_used", {}).get("peers_detail", [])
    target_peer = next((p for p in peers if p.get("is_target")), {})
    raw_shares = mkt.get("diluted_shares") or target_peer.get("shares_diluted")
    if not raw_shares and mkt.get("shares_m"):
        raw_shares = float(mkt["shares_m"]) * 1e6
    if not raw_shares and scoring_data.get("canonical_summary", {}).get("shares_diluted"):
        vals = list(scoring_data["canonical_summary"]["shares_diluted"].values())
        raw_shares = vals[0] if vals else 0.0
    raw_shares = float(raw_shares or 0.0)
    shares_b = (raw_shares / 1e9 if raw_shares > 1e6 else raw_shares / 1e3) if raw_shares > 0 else 0.0

    return {
        "wacc_dict": wacc_dict,
        "rf_pct": round(rf_raw * 100.0, 2),
        "beta": beta,
        "erp": erp,
        "ke_val": ke_val,
        "wacc_val": wacc_val,
        "wacc_pct": round(wacc_val * 100.0, 2),
        "kd_pre": kd_pre,
        "kd_post": kd_post,
        "tax_rate": tax_rate,
        "we": we,
        "wd": wd,
        "price": price,
        "shares_b": shares_b,
        "shares_m": shares_b * 1000.0,
        "peers": peers,
        "target_peer": target_peer,
    }


def _resolve_net_debt_m(scoring_data: Dict[str, Any], solvency: Dict[str, Any], fs_obj: Optional[Dict[str, Any]]) -> float:
    """Resuelve deuda neta canónica en millones descontando caja e inversiones a corto plazo."""
    net_debt_m = float(solvency.get("net_debt") or 0.0)
    if not fs_obj:
        return net_debt_m
    try:
        canon_sum = fs_obj.get("canonical_summary", {})
        bs_det = fs_obj.get("balance_sheet_detail", {})
        tot_d = _extract_ltm_or_latest_fy(canon_sum.get("total_debt"))
        c_eq = _extract_ltm_or_latest_fy(canon_sum.get("cash_and_equivalents")) or 0.0
        st_inv = canon_sum.get("short_term_investments", {}).get("LTM")
        if st_inv is None:
            for tag in ("MarketableSecuritiesCurrent", "us-gaap_MarketableSecuritiesCurrent", "ShortTermInvestments"):
                if tag in bs_det:
                    v_det = bs_det[tag].get("values", bs_det[tag]).get("LTM")
                    if v_det is not None and v_det > 0:
                        st_inv = float(v_det)
                        break
        if tot_d is not None:
            return round((float(tot_d) - (float(c_eq) + float(st_inv or 0.0))) / 1e6, 1)
    except (ValueError, TypeError, AttributeError) as exc:
        logger.debug("No se pudo derivar deuda neta desde canonical_summary: %s", exc)
    return net_debt_m


def _build_financial_pillars(
    ticker: str,
    is_ins: bool,
    ctx: Dict[str, Any],
    fs_obj: Optional[Dict[str, Any]],
    scoring_data: Dict[str, Any],
    tbv_total_m: float,
    tbv_per_share: float,
    rotce_val: Optional[float],
    spread_rotce_ke: Optional[float],
    ptbv_justified: float,
    fair_value_excess_return: float,
    cagr_5y_dyn: Optional[float],
) -> Dict[str, Any]:
    """Calcula múltiplos, EPV, EVA, 5Y IRR y Football Field para banca/seguros."""
    ke_val, price, shares_m, peers = ctx["ke_val"], ctx["price"], ctx["shares_m"], ctx["peers"]
    fin_canon = (fs_obj or {}).get("canonical_summary", {})
    eps_diluted_fin = _extract_ltm_or_latest_fy(fin_canon.get("eps_diluted_adjusted")) or 0.0
    cagr_eps_fin = _compute_series_cagr(fin_canon.get("eps_diluted_adjusted"), 5)
    buyback_rate_fin = _compute_share_reduction_rate(fin_canon.get("shares_diluted_adjusted"), 5)
    div_ltm_fin = fin_canon.get("dividends_paid", {}).get("LTM")
    div_m_fin = abs(float(div_ltm_fin)) / 1e6 if div_ltm_fin is not None else 0.0
    div_yield_fin = round((div_m_fin / (price * shares_m) * 100.0), 2) if (price * shares_m) > 0 else 0.0

    rotce_eff = rotce_val if rotce_val is not None else 0.0
    multiples_fin = calculate_multiples_valuation(
        price=price, shares_m=shares_m, net_debt_m=0.0, base_rev_m=tbv_total_m, ebit_m=0.0, ebitda_m=0.0,
        net_income_m=tbv_total_m * rotce_eff, fcf_m=0.0, eps_diluted=eps_diluted_fin, cagr_5y=cagr_5y_dyn,
        cagr_eps_5y=cagr_eps_fin, peers_detail=peers, is_financial=True, tbv_per_share=tbv_per_share,
        ptbv_justified=ptbv_justified, dividend_yield_pct=div_yield_fin,
    )

    sustainable_ni_fin = tbv_total_m * rotce_eff
    epv_eq_fin = (sustainable_ni_fin / ke_val) if ke_val > 0 else tbv_total_m
    epv_ps_fin = round(max(0.0, epv_eq_fin / shares_m), 2) if shares_m > 0 else 0.0
    pvgo_ps_fin = round(max(0.0, price - epv_ps_fin), 2) if price > 0 else 0.0
    epv_pct_fin = round(min(100.0, max(0.0, (epv_ps_fin / price) * 100.0)), 1) if price > 0 else 0.0
    pvgo_pct_fin = round(max(0.0, 100.0 - epv_pct_fin), 1) if price > 0 else 0.0
    epv_status = (
        "N/D" if price <= 0 else (
            "CRECIMIENTO GRATIS (EPV ≥ Precio)" if epv_ps_fin >= price else (
                "ALTA PROTECCIÓN DE BENEFICIOS" if pvgo_pct_fin <= 35.0 else "ALTA DEPENDENCIA DE CRECIMIENTO"
            )
        )
    )

    retention_fin = 0.45 if is_ins else 0.50
    g_tbv_fin = rotce_eff * retention_fin
    tbv_5y_fin = tbv_per_share * ((1.0 + g_tbv_fin) ** 5)
    target_5y_fin = round(tbv_5y_fin * ptbv_justified, 2)
    price_cagr_fin = ((target_5y_fin / price) ** (1.0 / 5.0)) - 1.0 if (price > 0 and target_5y_fin > 0) else 0.0
    irr_fin = price_cagr_fin + (div_yield_fin / 100.0) if price > 0 else 0.0

    return {
        "multiples_analysis": multiples_fin,
        "epv_analysis": {
            "epv_operating_m": round(epv_eq_fin, 1), "epv_equity_m": round(epv_eq_fin, 1),
            "epv_per_share": epv_ps_fin, "pvgo_per_share": pvgo_ps_fin,
            "epv_pct": epv_pct_fin, "pvgo_pct": pvgo_pct_fin,
            "status": epv_status, "sustainable_nopat_m": round(sustainable_ni_fin, 1),
        },
        "eva_analysis": {
            "fair_price_eva": fair_value_excess_return, "ev_eva": round(tbv_total_m * ptbv_justified, 1),
            "ic_base_m": round(tbv_total_m, 1), "pv_eva_sum": round(max(0.0, fair_value_excess_return - tbv_per_share) * shares_m, 1),
            "pv_terminal_eva": 0.0, "spread_pct": round(spread_rotce_ke * 100.0, 2) if spread_rotce_ke is not None else None,
        },
        "forward_5y_analysis": {
            "target_price_5y": target_5y_fin, "forward_irr_pct": round(irr_fin * 100.0, 2),
            "price_cagr_pct": round(price_cagr_fin * 100.0, 2),
            "total_return_pct": round(((target_5y_fin * ((1.0 + div_yield_fin / 100.0) ** 5) - price) / price) * 100.0, 1) if (price > 0 and target_5y_fin > 0) else 0.0,
            "fcf_per_share_5y": round(tbv_5y_fin, 2), "shares_5y_m": shares_m,
            "rev_5y_m": round(tbv_total_m * ((1.0 + g_tbv_fin) ** 5), 1),
            "bridge": {
                "growth_contrib": round(g_tbv_fin * 100.0, 2), "margin_contrib": 0.0,
                "buyback_contrib": round(buyback_rate_fin, 2), "multiple_contrib": 0.0, "div_contrib": div_yield_fin,
            },
        },
        "football_field": get_valuation_football_field(
            price=price, dcf_price=fair_value_excess_return, multiples_price=multiples_fin["imputed_prices"]["composite"],
            epv_price=epv_ps_fin, eva_price=fair_value_excess_return, target_5y_price=target_5y_fin, ke_val=ke_val,
        ),
        "dividend_yield_pct": div_yield_fin,
        "buyback_rate_pct": buyback_rate_fin,
        "historical_multiples": calculate_historical_multiples_analysis(
            ticker=ticker, current_price=price, current_shares_m=round(shares_m, 2),
            current_net_debt_m=0.0, current_nopat_adj_m=0.0, current_oe_m=0.0,
            fs_obj=fs_obj, scoring_data=scoring_data, is_financial=True, tbv_per_share=tbv_per_share,
        ),
    }


def _build_financial_valuation(
    ticker: str,
    arch: str,
    is_ins: bool,
    ctx: Dict[str, Any],
    prof: Dict[str, Any],
    fs_obj: Optional[Dict[str, Any]],
    scoring_data: Dict[str, Any],
) -> Dict[str, Any]:
    """Ejecuta la rama de valoración Excess Return (P/TBV vs ROTCE/ROE) para banca y seguros."""
    wacc_dict, ke_val, price, shares_b, shares_m = ctx["wacc_dict"], ctx["ke_val"], ctx["price"], ctx["shares_b"], ctx["shares_m"]
    target_peer = ctx["target_peer"]

    tbv_total_m = wacc_dict.get("tangible_book_value_usd_m")
    if not tbv_total_m and fs_obj:
        try:
            val_raw = _extract_ltm_or_latest_fy(fs_obj.get("canonical_summary", {}).get("stockholders_equity", {}))
            tbv_total_m = (val_raw / 1e6) if val_raw is not None else 0.0
        except (ValueError, TypeError) as exc:
            logger.debug("Error calculando TBV en %s: %s", ticker, exc)
    tbv_total_m = float(tbv_total_m or 0.0)
    tbv_per_share = round(tbv_total_m / shares_m, 2) if (shares_m > 0 and tbv_total_m > 0) else 0.0
    ptbv_current = round(price / tbv_per_share, 2) if (tbv_per_share > 0 and price > 0) else 0.0

    rotce_val = (wacc_dict.get("roe") or wacc_dict.get("rotce")) if is_ins else (wacc_dict.get("rotce") or wacc_dict.get("roe"))
    if rotce_val is None and prof:
        sc_dict = {r[0]: r for r in prof.get("scorecard", {}).get("data", []) if r}
        ret_key = "Retorno sobre Fondos Propios (ROE)" if is_ins else "Retorno sobre Patrimonio Tangible (ROTCE)"
        rotce_str = sc_dict.get(ret_key, ["", ""])[1] or sc_dict.get("Retorno sobre Patrimonio Tangible (ROTCE)", ["", ""])[1]
        if rotce_str:
            try:
                rotce_val = float(str(rotce_str).replace("%", "").strip()) / 100.0
            except (ValueError, TypeError) as exc:
                logger.debug("No se pudo parsear ROTCE desde scorecard (%s): %s", ticker, exc)

    fin_canon = (fs_obj or {}).get("canonical_summary", {})
    cagr_5y_dyn = _compute_series_cagr(fin_canon.get("revenue"), 5)
    if cagr_5y_dyn is None:
        cagr_5y_dyn = prof.get("cagr_5y") or target_peer.get("cagr_5y")
    cagr_10y_dyn = prof.get("cagr_10y") or target_peer.get("cagr_10y")
    cagr_3y_dyn = prof.get("cagr_3y") or target_peer.get("cagr_3y")
    guidance_dyn = prof.get("guidance_mid") or target_peer.get("guidance_mid")

    g_term = 0.030
    spread_rotce_ke = (rotce_val - ke_val) if rotce_val is not None else None
    ptbv_justified = (
        compute_two_stage_excess_return_ptbv(rotce_val, ke_val, g_term=g_term, cagr_5y=cagr_5y_dyn, is_insurance=is_ins)
        if rotce_val is not None else 1.0
    )
    fair_value_excess_return = round(ptbv_justified * tbv_per_share, 2) if tbv_per_share > 0 else 0.0
    rotce_implied = round(((ptbv_current * (ke_val - g_term)) + g_term) * 100.0, 1) if ptbv_current > 0 else 0.0

    base_r = round(rotce_val if (rotce_val is not None and rotce_val > 0) else ke_val, 4)
    rotce_rates = [round(max(0.04, base_r + step), 3) for step in (-0.06, -0.04, -0.02, 0.0, 0.02, 0.04)]
    rotce_labels = [f"{r*100:.1f}%" if r != base_r else f"{r*100:.1f}% (Base)" for r in rotce_rates]
    fair_price_base = fair_value_excess_return if fair_value_excess_return > 0 else price
    gap_exp_pp = ((rotce_implied / 100.0) - rotce_val) * 100.0 if (rotce_val is not None and ptbv_current > 0) else 0.0
    premium_pct_val = ((price - fair_price_base) / fair_price_base) * 100.0 if (fair_price_base > 0 and price > 0) else 0.0
    val_status = "SOBREVALORADA" if premium_pct_val > 25.0 else ("INFRAVALORADA" if premium_pct_val < -15.0 else "JUSTO")

    pillars = _build_financial_pillars(
        ticker, is_ins, ctx, fs_obj, scoring_data, tbv_total_m, tbv_per_share,
        rotce_val, spread_rotce_ke, ptbv_justified, fair_value_excess_return, cagr_5y_dyn,
    )
    return {
        "is_financial": True, "is_insurance": is_ins, "archetype": arch, "price": price,
        "shares_b": round(shares_b, 4), "shares_m": round(shares_m, 1),
        "rf_pct": ctx["rf_pct"], "erp_pct": round(ctx["erp"] * 100.0, 2), "beta": ctx["beta"],
        "ke_val": ke_val, "ke_pct": round(ke_val * 100.0, 2),
        "tangible_equity_m": tbv_total_m, "tbv_per_share": tbv_per_share, "ptbv_current": ptbv_current,
        "rotce_val": rotce_val, "rotce_pct": round(rotce_val * 100.0, 2) if rotce_val is not None else None,
        "rotce_rates": rotce_rates, "rotce_labels": rotce_labels,
        "g_terminal_pct": round(g_term * 100.0, 2),
        "spread_economic_pct": round(spread_rotce_ke * 100.0, 2) if spread_rotce_ke is not None else None,
        "ptbv_justified": ptbv_justified, "fair_value_excess_return": fair_value_excess_return,
        "fair_price_base": fair_price_base, "rotce_implied_pct": rotce_implied,
        "g_implied_pct": rotce_implied, "g_implied_3stage_pct": rotce_implied,
        "fcf_margin_true_pct": 0.0, "sbc_usd_m": 0.0, "sbc_margin_pct": 0.0,
        "hist_growth_pct": float(cagr_5y_dyn or 0.0),
        "init_growth_disp": round(rotce_val * 100.0, 2) if rotce_val is not None else 0.0,
        "gap_expectations_str": f"{'+' if gap_exp_pp >= 0 else ''}{gap_exp_pp:.1f} pp",
        "premium_pct": premium_pct_val, "valuation_status": val_status,
        "rev_base": tbv_total_m, "fcf_margin_pct": 0.0, "net_debt_m": 0.0,
        "cagr_5y": cagr_5y_dyn, "cagr_10y": cagr_10y_dyn, "cagr_3y": cagr_3y_dyn, "guidance_mid": guidance_dyn,
        **pillars,
        "owner_earnings_analysis": {"is_financial": True, "status": "NO APLICA (Arquetipo Financiero)", "oe_margin_pct": 0.0, "g_implied_oe_pct": 0.0, "fair_price_oe": fair_value_excess_return},
        "z_score_analysis": {"z_score": None, "status": "N/D (Arquetipo Financiero)", "bands": {}},
        "audit_traceability": {"is_financial": True, "dictum": "Arquetipo Financiero: Se audita mediante Tangible Book Value y ROTCE Sostenible."},
        "oe_margin_pct": 0.0, "g_implied_oe_pct": 0.0, "fair_price_oe": fair_value_excess_return,
    }


def _compute_corporate_margins_and_dcf(
    arch: str,
    ctx: Dict[str, Any],
    prof: Dict[str, Any],
    fs_obj: Optional[Dict[str, Any]],
    solvency: Dict[str, Any],
    net_debt_m: float,
) -> Dict[str, Any]:
    """Calcula márgenes operativos/FCF, CAGRs históricos y Reverse DCF 2 y 3 etapas."""
    price, shares_b, wacc_val, tax_rate = ctx["price"], ctx["shares_b"], ctx["wacc_val"], ctx["tax_rate"]
    target_peer = ctx["target_peer"]
    canon_sum = (fs_obj or {}).get("canonical_summary", {})

    rev_raw = _extract_ltm_or_latest_fy(canon_sum.get("revenue"))
    base_rev_m = (rev_raw / 1e6) if (rev_raw is not None and rev_raw > 0) else float(target_peer.get("revenue_usd_m") or solvency.get("revenue") or 0.0)
    s_ebit = float(solvency.get("ebit") or 0.0)
    s_capex = float(solvency.get("capex") or 0.0)
    s_fcf = float(solvency.get("fcf") or 0.0)
    s_dna = float(solvency.get("dna") or 0.0)

    dna_margin = (s_dna / base_rev_m) if (base_rev_m > 0 and s_dna > 0) else 0.025
    ebit_margin = (s_ebit / base_rev_m) if (base_rev_m > 0 and s_ebit > 0) else 0.20
    capex_margin = (s_capex / base_rev_m) if (base_rev_m > 0 and s_capex > 0) else 0.02
    op_fcf_margin = max(0.05, ebit_margin * (1.0 - tax_rate) + dna_margin - capex_margin)

    kr_fcf = _extract_ltm_or_latest_fy((fs_obj or {}).get("key_ratios", {}).get("fcf_margin_pct"))
    raw_fcf_margin = (kr_fcf / 100.0) if (kr_fcf is not None and kr_fcf > 0) else ((s_fcf / base_rev_m) if (s_fcf > 0 and base_rev_m > 0) else op_fcf_margin)
    fcf_margin = round((op_fcf_margin * 0.65) + (min(raw_fcf_margin, 0.18) * 0.35), 4) if (arch == "PLATFORM_ECOSYSTEM" and raw_fcf_margin > (op_fcf_margin * 1.5)) else raw_fcf_margin

    cagr_5y = _compute_rev_cagr(canon_sum, 5)
    cagr_3y = _compute_rev_cagr(canon_sum, 3)
    cagr_10y = _compute_rev_cagr(canon_sum, 10)
    cagr_5y = cagr_5y if cagr_5y is not None else (prof.get("cagr_5y") or target_peer.get("cagr_5y"))
    cagr_3y = cagr_3y if cagr_3y is not None else (prof.get("cagr_3y") or target_peer.get("cagr_3y"))
    cagr_10y = cagr_10y if cagr_10y is not None else (prof.get("cagr_10y") or target_peer.get("cagr_10y"))
    guidance_mid = prof.get("guidance_mid") or target_peer.get("guidance_mid")

    gn_dec = 0.025
    g_implied_our = solve_reverse_dcf(price, shares_b, net_debt_m, base_rev_m, wacc_val, gn_dec, fcf_margin, 10)
    hist_growth_pct_val = float(cagr_5y or 0.0)
    hist_growth_dec = hist_growth_pct_val / 100.0
    init_proj_growth = min(hist_growth_dec, 0.20) if hist_growth_dec > 0.20 else max(hist_growth_dec, -0.05)

    shares_m_rounded = round(round(shares_b, 4) * 1000.0, 2)
    fair_price_base = calculate_dcf_details(base_rev_m, init_proj_growth, fcf_margin, wacc_val, gn_dec, net_debt_m, shares_m_rounded)["fair_price"] if (base_rev_m > 0 and shares_m_rounded > 0) else price
    g_implied_our_pct_rounded = round(g_implied_our * 100.0, 1)
    gap_exp_pp = ((g_implied_our_pct_rounded / 100.0) - init_proj_growth) * 100.0
    premium_pct_val = ((price - fair_price_base) / fair_price_base) * 100.0 if (fair_price_base > 0 and price > 0) else 0.0
    val_status = "SOBREVALORADA" if premium_pct_val > 25.0 else ("INFRAVALORADA" if premium_pct_val < -15.0 else "JUSTO")

    sbc_raw = _extract_ltm_or_latest_fy(canon_sum.get("stock_based_compensation"))
    sbc_usd_m = (abs(sbc_raw) / 1e6) if sbc_raw is not None else 0.0
    sbc_margin_pct = round((sbc_usd_m / base_rev_m) * 100.0, 2) if base_rev_m > 0 else 0.0
    fcf_margin_true_pct = round(max(1.0, (fcf_margin * 100.0) - sbc_margin_pct), 2)
    fcf_margin_true = fcf_margin_true_pct / 100.0

    return {
        "canon_sum": canon_sum, "base_rev_m": base_rev_m, "s_ebit": s_ebit, "s_dna": s_dna,
        "dna_margin": dna_margin, "ebit_margin": ebit_margin, "capex_margin": capex_margin,
        "op_fcf_margin": op_fcf_margin, "raw_fcf_margin": raw_fcf_margin, "fcf_margin": fcf_margin,
        "cagr_5y": cagr_5y, "cagr_3y": cagr_3y, "cagr_10y": cagr_10y, "guidance_mid": guidance_mid,
        "gn_dec": gn_dec, "g_implied_our": g_implied_our, "g_implied_our_pct_rounded": g_implied_our_pct_rounded,
        "hist_growth_pct_val": hist_growth_pct_val, "init_proj_growth": init_proj_growth,
        "shares_m_rounded": shares_m_rounded, "fair_price_base": fair_price_base,
        "gap_exp_pp": gap_exp_pp, "premium_pct_val": premium_pct_val, "val_status": val_status,
        "sbc_usd_m": sbc_usd_m, "sbc_margin_pct": sbc_margin_pct,
        "fcf_margin_true_pct": fcf_margin_true_pct, "fcf_margin_true": fcf_margin_true,
        "g_implied_3stage_pct": round(solve_reverse_dcf_3stage(price, shares_b, net_debt_m, base_rev_m, wacc_val, gn_dec, fcf_margin, 10, 5) * 100.0, 1),
        "g_implied_3stage_true_pct": round(solve_reverse_dcf_3stage(price, shares_b, net_debt_m, base_rev_m, wacc_val, gn_dec, fcf_margin_true, 10, 5) * 100.0, 1),
    }


def _build_corporate_valuation(
    ticker: str,
    arch: str,
    ctx: Dict[str, Any],
    prof: Dict[str, Any],
    fs_obj: Optional[Dict[str, Any]],
    scoring_data: Dict[str, Any],
    solvency: Dict[str, Any],
    net_debt_m: float,
) -> Dict[str, Any]:
    """Ensambla pilares de valoración, Owner Earnings, Z-Score y trazabilidad para corporaciones."""
    m = _compute_corporate_margins_and_dcf(arch, ctx, prof, fs_obj, solvency, net_debt_m)
    price, wacc_val, wacc_pct, tax_rate = ctx["price"], ctx["wacc_val"], ctx["wacc_pct"], ctx["tax_rate"]
    canon_sum, base_rev_m, shares_m_rounded = m["canon_sum"], m["base_rev_m"], m["shares_m_rounded"]
    ebit_margin, fcf_margin, gn_dec = m["ebit_margin"], m["fcf_margin"], m["gn_dec"]

    eps_diluted_val = _extract_ltm_or_latest_fy(canon_sum.get("eps_diluted_adjusted")) or 0.0
    cagr_eps_5y = _compute_series_cagr(canon_sum.get("eps_diluted_adjusted"), 5)
    cagr_fcf_5y = _compute_series_cagr(canon_sum.get("free_cash_flow"), 5)
    buyback_rate_pct = _compute_share_reduction_rate(canon_sum.get("shares_diluted_adjusted"), 5)
    div_ltm_raw = _extract_ltm_or_latest_fy(canon_sum.get("dividends_paid"))
    div_m = (abs(div_ltm_raw) / 1e6) if div_ltm_raw is not None else 0.0
    dividend_yield_pct = round((div_m / (price * shares_m_rounded) * 100.0), 2) if (price * shares_m_rounded) > 0 else 0.0

    net_inc_raw = canon_sum.get("net_income", {}).get("LTM")
    net_inc_m = (float(net_inc_raw) / 1e6) if net_inc_raw is not None else 0.0
    ebitda_val = (m["s_ebit"] + m["s_dna"]) if (m["s_ebit"] > 0 or m["s_dna"] > 0) else (base_rev_m * (ebit_margin + m["dna_margin"]))

    multiples_analysis = calculate_multiples_valuation(
        price=price, shares_m=shares_m_rounded, net_debt_m=net_debt_m, base_rev_m=base_rev_m,
        ebit_m=m["s_ebit"] if m["s_ebit"] > 0 else (base_rev_m * ebit_margin), ebitda_m=ebitda_val,
        net_income_m=net_inc_m, fcf_m=base_rev_m * fcf_margin, eps_diluted=eps_diluted_val,
        cagr_5y=m["cagr_5y"], cagr_eps_5y=cagr_eps_5y, cagr_fcf_5y=cagr_fcf_5y,
        peers_detail=ctx["peers"], is_financial=False, dividend_yield_pct=dividend_yield_pct,
    )
    epv_analysis = calculate_epv_pvgo(base_rev_m, ebit_margin, tax_rate, m["sbc_usd_m"], wacc_val, net_debt_m, shares_m_rounded, price)

    roic_periods = scoring_data.get("roic_wacc_analysis", {}).get("roic", {}).get("by_period", {})
    ic_val = float(roic_periods[sorted(roic_periods.keys())[-1]].get("ic_adj_end", 0.0)) if roic_periods else 0.0
    if ic_val <= 0 and base_rev_m > 0:
        ic_val = max(100.0, base_rev_m * 0.70)
    roic_used = scoring_data.get("wacc_analysis", {}).get("roic_adjusted")
    eva_analysis = calculate_eva_valuation(ic_val, roic_used, wacc_val, net_debt_m, shares_m_rounded)

    forward_5y_analysis = calculate_5y_forward_irr(
        price=price, base_revenue_m=base_rev_m,
        revenue_growth_pct=m["cagr_5y"] if m["cagr_5y"] is not None else (m["init_proj_growth"] * 100.0),
        fcf_margin_pct=fcf_margin * 100.0, shares_m=shares_m_rounded, net_buyback_yield_pct=buyback_rate_pct,
        exit_multiple=multiples_analysis.get("normal_pe") or 22.0, dividend_yield_pct=dividend_yield_pct,
        base_fcf_margin_pct=fcf_margin * 100.0, current_multiple=multiples_analysis.get("pe_current"),
    )

    ira_data = scoring_data.get("intangible_roic_analysis", {})
    ltm_ira = ira_data.get("latest_result", {})
    nopat_adj_val = ltm_ira.get("nopat_adj") or (base_rev_m * ebit_margin * (1.0 - tax_rate))
    rd_inv_val, rd_amort_val, rd_stock_val = float(ltm_ira.get("rd_investment") or 0.0), float(ltm_ira.get("rd_amortization") or 0.0), float(ltm_ira.get("rd_stock") or 0.0)
    ebit_adj_val = float(ltm_ira.get("ebit_adj") or (base_rev_m * ebit_margin))

    cfo_raw = _extract_ltm_or_latest_fy(canon_sum.get("cash_from_operations"))
    cfo_m_val = (cfo_raw / 1e6) if cfo_raw is not None else float(base_rev_m * fcf_margin)
    capex_raw = _extract_ltm_or_latest_fy(canon_sum.get("capital_expenditures"))
    capex_m_val = (abs(capex_raw) / 1e6) if capex_raw is not None else 0.0
    dna_raw = _extract_ltm_or_latest_fy(canon_sum.get("depreciation_amortization"))
    da_m_val = (dna_raw / 1e6) if dna_raw is not None else None

    owner_earnings_analysis = calculate_owner_earnings_and_capex(
        cfo_m_val, capex_m_val, da_m_val, base_rev_m, nopat_adj_val, rd_inv_val, rd_amort_val,
        price=price, shares_m=shares_m_rounded, net_debt_m=net_debt_m, wacc_val=wacc_val, gn_dec=gn_dec, is_financial=False,
    )
    z_score_analysis = calculate_z_score_valuation(ticker, price, shares_m_rounded, net_debt_m, nopat_adj_val, is_financial=False)

    by_period_dict = ira_data.get("by_period", {})
    sorted_fys = sorted([k for k in by_period_dict if k != "LTM"], key=lambda x: int(x.replace("FY", "")) if "FY" in x and x.replace("FY", "").isdigit() else 0)
    by_period_history = [
        {
            "period": fy_k, "ebit_m": round(by_period_dict[fy_k].get("ebit", 0.0), 1),
            "ebit_adj_m": round(by_period_dict[fy_k].get("ebit_adj", 0.0), 1),
            "nopat_adj_m": round(by_period_dict[fy_k].get("nopat_adj", 0.0), 1),
            "rd_inv_m": round(by_period_dict[fy_k].get("rd_investment", 0.0), 1),
            "rd_stock_m": round(by_period_dict[fy_k].get("rd_stock", 0.0), 1),
            "roic_trad_pct": round((by_period_dict[fy_k].get("roic_trad") or 0.0) * 100.0, 1),
            "roic_adj_pct": round((by_period_dict[fy_k].get("roic_adj") or 0.0) * 100.0, 1),
        }
        for fy_k in sorted_fys[-5:]
    ]

    roic_eff = float(roic_used or 0.0)
    audit_traceability = build_audit_traceability(
        ticker=ticker, ebit_reported_m=round(m["s_ebit"] if m["s_ebit"] > 0 else (base_rev_m * ebit_margin), 1),
        rd_expense_m=round(rd_inv_val, 1), rd_amortization_m=round(rd_amort_val, 1), ebit_adjusted_m=round(ebit_adj_val, 1),
        tax_rate_pct=round(tax_rate * 100.0, 1), nopat_adjusted_m=round(nopat_adj_val, 1), cfo_m=round(cfo_m_val, 1),
        capex_total_m=round(capex_m_val, 1), maint_capex_m=owner_earnings_analysis.get("maint_capex_m", 0.0),
        growth_capex_m=owner_earnings_analysis.get("growth_capex_m", 0.0), net_rd_inv_m=owner_earnings_analysis.get("net_rd_inv_m", 0.0),
        fcf_reported_m=owner_earnings_analysis.get("fcf_reported_m", 0.0), owner_earnings_m=owner_earnings_analysis.get("owner_earnings_m", 0.0),
        shares_m=shares_m_rounded, stock_price=price, net_debt_m=net_debt_m, wacc_pct=wacc_pct, gn_pct=round(gn_dec * 100.0, 2),
        rd_stock_m=round(rd_stock_val, 1), roic_trad_pct=round(float(scoring_data.get("wacc_analysis", {}).get("roic_traditional") or 0.0) * 100.0, 1),
        roic_adj_pct=round(roic_eff * 100.0, 1), spread_pct=round((roic_eff - wacc_val) * 100.0, 1),
        z_score_obj=z_score_analysis, by_period_history=by_period_history, is_financial=False,
        g_implied_oe_pct=owner_earnings_analysis.get("g_implied_oe_pct", 0.0),
    )

    return {
        "is_financial": False, "price": price, "rf_pct": ctx["rf_pct"], "erp_pct": round(ctx["erp"] * 100.0, 2),
        "beta": ctx["beta"], "kd_pre_pct": round(ctx["kd_pre"] * 100.0, 2), "kd_post_pct": round(ctx["kd_post"] * 100.0, 2),
        "tax_rate_pct": round(tax_rate * 100.0, 1), "weight_debt_pct": round(ctx["wd"] * 100.0, 1),
        "weight_equity_pct": round(ctx["we"] * 100.0, 1), "wacc_pct": wacc_pct, "wacc_val": wacc_val,
        "ebit_margin": ebit_margin, "fcf_margin": fcf_margin, "fcf_margin_reported_pct": round(m["raw_fcf_margin"] * 100.0, 1),
        "fcf_margin_audited": fcf_margin, "capex_margin": m["capex_margin"], "ebit_margin_pct": round(ebit_margin * 100.0, 1),
        "fcf_margin_pct": round(fcf_margin * 100.0, 1), "fcf_margin_audited_pct": round(fcf_margin * 100.0, 1),
        "fcf_margin_operating_pct": round(m["op_fcf_margin"] * 100.0, 1), "capex_margin_pct": round(m["capex_margin"] * 100.0, 1),
        "shares_b": round(ctx["shares_b"], 4), "shares_m": shares_m_rounded, "net_debt_m": net_debt_m,
        "base_rev_m": base_rev_m, "rev_base": base_rev_m, "cagr_5y": m["cagr_5y"], "cagr_10y": m["cagr_10y"],
        "cagr_3y": m["cagr_3y"], "guidance_mid": m["guidance_mid"], "g_implied_our_pct": m["g_implied_our_pct_rounded"],
        "g_implied_fiscal_pct": round(m["g_implied_our"] * 100.0, 1),
        "gap_hist": round((m["g_implied_our"] * 100.0) - m["cagr_5y"], 1) if m["cagr_5y"] is not None else None,
        "gap_guide": round((m["g_implied_our"] * 100.0) - m["guidance_mid"], 1) if m["guidance_mid"] is not None else None,
        "fair_price_base": m["fair_price_base"], "valuation_status": m["val_status"], "premium_pct": m["premium_pct_val"],
        "g_implied_pct": m["g_implied_our_pct_rounded"], "hist_growth_pct": m["hist_growth_pct_val"],
        "init_growth_disp": m["init_proj_growth"] * 100.0, "gap_expectations_str": f"{'+' if m['gap_exp_pp'] >= 0 else ''}{m['gap_exp_pp']:.1f} pp",
        "sbc_usd_m": m["sbc_usd_m"], "sbc_margin_pct": m["sbc_margin_pct"], "fcf_margin_true_pct": m["fcf_margin_true_pct"],
        "fcf_margin_true": m["fcf_margin_true"], "g_implied_3stage_pct": m["g_implied_3stage_pct"],
        "g_implied_3stage_true_pct": m["g_implied_3stage_true_pct"], "cagr_eps_5y": cagr_eps_5y, "cagr_fcf_5y": cagr_fcf_5y,
        "buyback_rate_pct": buyback_rate_pct, "dividend_yield_pct": dividend_yield_pct,
        "multiples_analysis": multiples_analysis, "epv_analysis": epv_analysis, "eva_analysis": eva_analysis,
        "forward_5y_analysis": forward_5y_analysis,
        "football_field": get_valuation_football_field(
            price=price, dcf_price=m["fair_price_base"], multiples_price=multiples_analysis["imputed_prices"]["composite"],
            epv_price=epv_analysis["epv_per_share"], eva_price=eva_analysis["fair_price_eva"],
            target_5y_price=forward_5y_analysis["target_price_5y"], ke_val=wacc_val,
        ),
        "historical_multiples": calculate_historical_multiples_analysis(
            ticker=ticker, current_price=price, current_shares_m=shares_m_rounded, current_net_debt_m=net_debt_m,
            current_nopat_adj_m=nopat_adj_val, current_oe_m=owner_earnings_analysis.get("owner_earnings_m", 0.0),
            fs_obj=fs_obj, scoring_data=scoring_data, is_financial=False,
        ),
        "owner_earnings_analysis": owner_earnings_analysis, "z_score_analysis": z_score_analysis, "audit_traceability": audit_traceability,
        "oe_margin_pct": owner_earnings_analysis.get("oe_margin_pct", 0.0),
        "g_implied_oe_pct": owner_earnings_analysis.get("g_implied_oe_pct", 0.0),
        "fair_price_oe": owner_earnings_analysis.get("fair_price_oe", m["fair_price_base"]),
    }


def get_valuation_parameters(
    scoring_data: Dict[str, Any],
    ticker: str = "",
    profile_data: Optional[Dict[str, Any]] = None,
    live_price: Optional[float] = None,
    fs_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Consolida los parámetros financieros y de valoración dual (DCF o Excess Return) sin hardcodes."""
    ticker = ticker or scoring_data.get("ticker", "")
    prof, fs_obj = _load_valuation_inputs(scoring_data, ticker, profile_data, fs_data)
    arch = get_report_archetype(scoring_data)
    is_fin = arch in ("FINANCIAL_BANKING", "INSURANCE")
    ctx = _resolve_capital_structure_and_wacc(scoring_data, prof, live_price, is_fin)

    if is_fin:
        return _build_financial_valuation(ticker, arch, arch == "INSURANCE", ctx, prof, fs_obj, scoring_data)

    solvency = scoring_data.get("debt_and_solvency_analysis", {}).get("cash_flow_leverage", {}).get("LTM", {})
    if not solvency:
        solvency = scoring_data.get("debt_and_solvency_analysis", {}).get("latest_result", {}).get("cash_flow_leverage", {})
    net_debt_m = _resolve_net_debt_m(scoring_data, solvency, fs_obj)
    return _build_corporate_valuation(ticker, arch, ctx, prof, fs_obj, scoring_data, solvency, net_debt_m)


def _generate_sensitivity_grid(vp: Dict[str, Any]) -> List[Tuple[str, str, str, str, str, str, str, str]]:
    """Calcula dinámicamente la matriz de sensibilidad 5×6 según el arquetipo."""
    if vp.get("is_financial"):
        ke_base = float(vp.get("ke_val") or 0.0943)
        ke_steps = [
            (ke_base - 0.010, f"{round((ke_base - 0.010)*100, 2):.2f}% (Bajo / Optimista)"),
            (ke_base - 0.005, f"{round((ke_base - 0.005)*100, 2):.2f}% (Favorable)"),
            (ke_base, f"{vp.get('ke_pct', round(ke_base * 100, 2)):.2f}% (Ke Auditado Base)"),
            (ke_base + 0.005, f"{round((ke_base + 0.005)*100, 2):.2f}% (Exigente)"),
            (ke_base + 0.010, f"{round((ke_base + 0.010)*100, 2):.2f}% (Estrés Macro / Tipos)"),
        ]
        rotce_rates = vp.get("rotce_rates") or [0.18, 0.20, 0.22, 0.24, 0.26, 0.28]
        g_term = float(vp.get("g_terminal_pct", 3.0)) / 100.0
        tbv_ps = float(vp.get("tbv_per_share", 0.0))

        grid_rows = []
        for ke_step, ke_label in ke_steps:
            row_vals = [ke_label]
            for r_val in rotce_rates:
                if ke_step > g_term:
                    ptbv_c = compute_two_stage_excess_return_ptbv(r_val, ke_step, g_term=g_term, cagr_5y=vp.get("cagr_5y"), is_insurance=vp.get("is_insurance", False))
                    row_vals.append(f"${round(ptbv_c * tbv_ps, 2):.2f}" if tbv_ps > 0 else f"{ptbv_c:.2f}x")
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

    base_wacc = float(vp.get("wacc_val") or (vp.get("wacc_pct", 9.5) / 100.0))
    wacc_steps = [
        (base_wacc - 0.010, f"{round((base_wacc - 0.010)*100, 2):.2f}% (Bajo / Expansión)"),
        (base_wacc - 0.005, f"{round((base_wacc - 0.005)*100, 2):.2f}% (Favorable)"),
        (base_wacc, f"{vp.get('wacc_pct', round(base_wacc * 100, 2)):.2f}% (WACC Auditado Base)"),
        (base_wacc + 0.005, f"{round((base_wacc + 0.005)*100, 2):.2f}% (Exigente)"),
        (base_wacc + 0.010, f"{round((base_wacc + 0.010)*100, 2):.2f}% (Estrés / Tipos Altos)"),
    ]
    terminal_rates = (0.010, 0.015, 0.020, 0.025, 0.030, 0.035)
    fcf_m = float(vp.get("fcf_margin") or (vp.get("fcf_margin_pct", 20.0) / 100.0))
    has_dcf_inputs = vp.get("price", 0.0) > 0 and vp.get("shares_b", 0.0) > 0 and vp.get("base_rev_m", 0.0) > 0 and fcf_m > 0

    grid_rows = []
    for w_val, w_label in wacc_steps:
        row_vals = [w_label]
        for g_term in terminal_rates:
            if has_dcf_inputs and w_val > g_term:
                g_sol = solve_reverse_dcf(vp["price"], vp["shares_b"], vp["net_debt_m"], vp["base_rev_m"], w_val, g_term, fcf_m, 10)
                row_vals.append(f"{g_sol * 100.0:.1f}%")
            else:
                row_vals.append("N/D")
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
