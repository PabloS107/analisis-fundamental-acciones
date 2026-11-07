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
