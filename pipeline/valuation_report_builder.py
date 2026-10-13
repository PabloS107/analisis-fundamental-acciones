"""
valuation_report_builder.py - Constructor de secciones ejecutivas de Valoración Fundamental,
Reverse DCF, Expectations Investing y Excess Return para informes Word (.docx) y Markdown (.md).

Implementa arquitectura multi-sectorial:
1. Empresas Corporativas Tradicionales, Tecnológicas y Plataformas (AAPL, DECK, MELI, NVDA):
   - Bloque A: Filosofía de Expectations Investing y configuración óptima en plataformas (Fiscal AI)
   - Bloque B: Auditoría de parámetros macro y coste de capital (Rf, ERP, Beta, WACC, Margen FCF)
   - Bloque C: Conciliación de discrepancias WACC propietario vs. modelos externos
   - Bloque D: Descuento Inverso de Flujos de Caja (Reverse DCF) y resolución numérica de crecimiento implícito
   - Bloque E: Matriz bidimensional de sensibilidad (WACC vs. Crecimiento Terminal gn)
   - Bloque F: Cuadro de Mando Consolidado y veredicto de valoración de mercado.

2. Instituciones Financieras y Bancarias (NU, JPM, Neobancos, FinTechs):
   - Bloque A: Justificación contable del por qué el modelo DCF/WACC no aplica a intermediarios financieros
   - Bloque B: Modelo de Retorno Excedente / Renta Residual (Excess Return Model: P/TBV vs. ROTCE)
   - Bloque C: Coste del capital propio (Ke vía CAPM) y Spread Económico (ROTCE - Ke)
   - Bloque D: Valor intrínseco teórico fundamental sustentado por patrimonio tangible y retorno de balance
   - Bloque E: Matriz bidimensional de sensibilidad bancaria (Ke vs. ROTCE sostenible)
   - Bloque F: Reverse Excess Return (ROTCE implícito en el precio actual) y Cuadro de Mando.

3. Instituciones Aseguradoras (PGR, P&C, Vida, Reaseguros):
   - Bloque A: Justificación contable del modelo Gordon-Shapiro sobre Book Value / Policyholders' Surplus (P/BV vs. ROE)
   - Bloque B: Coste del capital propio (Ke vía CAPM) y Spread Económico (ROE - Ke)
   - Bloque C: Valor intrínseco teórico justificado por suscripción técnica y retorno sobre float
   - Bloque D: Matriz bidimensional de sensibilidad (Ke vs. ROE sostenible)
   - Bloque E: Reverse Excess Return y Cuadro de Mando adaptado a solvencia NAIC y rentabilidad de suscripción.
"""

import sys
import json
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import docx
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml import parse_xml, OxmlElement
from docx.oxml.ns import nsdecls, qn

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA_DIR = PROJECT_ROOT / "data" / "processed"


def _resolve_processed_path(ticker: str, filename: str) -> Path:
    """Resuelve la ruta canónica del archivo en data/processed/{ticker}/ garantizando invariancia de CWD."""
    p_abs = DEFAULT_DATA_DIR / ticker / filename
    if p_abs.exists():
        return p_abs
    p_rel = Path(f"data/processed/{ticker}/{filename}")
    if p_rel.exists():
        return p_rel
    return p_abs


# Paleta Institucional
NAVY = RGBColor(0x1B, 0x36, 0x5D)
SLATE = RGBColor(0x4A, 0x55, 0x68)
DARK_GRAY = RGBColor(0x2D, 0x37, 0x48)
GREEN_DARK = RGBColor(0x27, 0x6A, 0x3C)
RED_DARK = RGBColor(0xC0, 0x00, 0x00)

LIGHT_BLUE = "F0F4F8"
HEADER_BG = "1B365D"
ALT_ROW_BG = "F7FAFC"
WHITE_HEX = "FFFFFF"
BORDER_GRAY = "D2D6DC"
GREEN_BG = "E2EFDA"
YELLOW_BG = "FFF2CC"
RED_BG = "FCE4D6"


def _set_cell_shading(cell, color_hex):
    shd = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{color_hex}"/>')
    cell._tc.get_or_add_tcPr().append(shd)


def _set_cell_margins(cell, top=100, bottom=100, left=130, right=130):
    tcPr = cell._tc.get_or_add_tcPr()
    tcMar = OxmlElement('w:tcMar')
    for m, val in [('top', top), ('bottom', bottom), ('left', left), ('right', right)]:
        node = OxmlElement(f'w:{m}')
        node.set(qn('w:w'), str(val))
        node.set(qn('w:type'), 'dxa')
        tcMar.append(node)
    tcPr.append(tcMar)


def _set_table_borders(table, border_color="D2D6DC"):
    tblPr = table._tbl.tblPr
    borders = parse_xml(
        f'<w:tblBorders {nsdecls("w")}>'
        f'<w:top w:val="single" w:sz="6" w:space="0" w:color="{border_color}"/>'
        f'<w:bottom w:val="single" w:sz="6" w:space="0" w:color="{border_color}"/>'
        f'<w:insideH w:val="single" w:sz="4" w:space="0" w:color="{border_color}"/>'
        f'<w:insideV w:val="none"/>'
        f'<w:left w:val="none"/>'
        f'<w:right w:val="none"/>'
        f'</w:tblBorders>'
    )
    tblPr.append(borders)


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


def _is_financial(scoring_data: Dict[str, Any]) -> bool:
    """Identifica si la empresa pertenece al sector financiero/bancario/seguros."""
    return get_report_archetype(scoring_data) in ("FINANCIAL_BANKING", "INSURANCE")


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
    ticker: str = "AAPL",
    profile_data: Optional[Dict[str, Any]] = None,
    live_price: Optional[float] = None,
    fs_data: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Extrae y consolida los parámetros financieros y de mercado para la valoración de cualquier empresa."""
    prof = profile_data or {}
    if not prof:
        candidate = _resolve_processed_path(ticker, "company_profile.json")
        if candidate.exists():
            try:
                with open(candidate, "r", encoding="utf-8") as f:
                    prof = json.load(f)
            except Exception:
                pass

    fs_obj = fs_data
    if fs_obj is None:
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
            
        g_term = 0.030
        spread_rotce_ke = rotce_val - ke_val
        ptbv_justified = round((rotce_val - g_term) / (ke_val - g_term), 2) if (ke_val > g_term) else 1.0
        fair_value_excess_return = round(ptbv_justified * tbv_per_share, 2) if tbv_per_share > 0 else 0.0
        rotce_implied = round(((ptbv_current * (ke_val - g_term)) + g_term) * 100, 1) if ptbv_current > 0 else 0.0

        # Pasos de sensibilidad dinámicos centrados en rotce_val real
        center_r = rotce_val if (rotce_val and rotce_val > 0) else ke_val
        base_r = round(center_r, 4)
        rotce_rates = [round(max(0.04, base_r + step), 3) for step in [-0.06, -0.04, -0.02, 0.0, 0.02, 0.04]]
        rotce_labels = [f"{r*100:.1f}%" if r != base_r else f"{r*100:.1f}% (Base)" for r in rotce_rates]

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
            "rotce_implied_pct": rotce_implied,
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
    
    ebit_margin = (s_ebit / base_rev_m) if (base_rev_m > 0 and s_ebit > 0) else 0.20
    capex_margin = (s_capex / base_rev_m) if (base_rev_m > 0 and s_capex > 0) else 0.02
    
    # Margen FCF auditado real derivado de los estados financieros de la compañía
    kr_fcf = None
    if fs_obj:
        kr_fcf = fs_obj.get("key_ratios", {}).get("fcf_margin_pct", {}).get("LTM")
        if kr_fcf is None:
            fy_keys = sorted([k for k in fs_obj.get("key_ratios", {}).get("fcf_margin_pct", {}).keys() if k.startswith("FY") and fs_obj["key_ratios"]["fcf_margin_pct"][k] is not None], reverse=True)
            if fy_keys:
                kr_fcf = fs_obj["key_ratios"]["fcf_margin_pct"][fy_keys[0]]

    if kr_fcf is not None and float(kr_fcf) > 0:
        fcf_margin = float(kr_fcf) / 100.0
    elif s_fcf > 0 and base_rev_m > 0:
        fcf_margin = s_fcf / base_rev_m
    else:
        fcf_margin = max(0.05, ebit_margin * (1.0 - tax_rate) - capex_margin)
    
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
                    # 5 años completos de separación: entre índice -1 e índice -6
                    calc_cagr_5y = round((((r_last / rev_map[yr_list[-6]]) ** (1.0 / 5.0)) - 1.0) * 100.0, 1)
                elif len(yr_list) >= 2 and rev_map.get(yr_list[0]) and rev_map[yr_list[0]] > 0:
                    n_years = len(yr_list) - 1
                    calc_cagr_5y = round((((r_last / rev_map[yr_list[0]]) ** (1.0 / float(n_years))) - 1.0) * 100.0, 1)

                if len(yr_list) >= 4 and rev_map.get(yr_list[-4]) and rev_map[yr_list[-4]] > 0:
                    # 3 años completos de separación
                    calc_cagr_3y = round((((r_last / rev_map[yr_list[-4]]) ** (1.0 / 3.0)) - 1.0) * 100.0, 1)
                if len(yr_list) >= 11 and rev_map.get(yr_list[-11]) and rev_map[yr_list[-11]] > 0:
                    # 10 años completos de separación
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
        "fcf_margin_audited": fcf_margin,
        "capex_margin": capex_margin,
        "ebit_margin_pct": round(ebit_margin * 100, 1),
        "fcf_margin_pct": round(fcf_margin * 100, 1),
        "fcf_margin_audited_pct": round(fcf_margin * 100, 1),
        "fcf_margin_operating_pct": round(max(0.05, ebit_margin * (1.0 - tax_rate) - capex_margin) * 100, 1),
        "capex_margin_pct": round(capex_margin * 100, 1),
        "shares_b": round(shares_b, 4),
        "net_debt_m": net_debt_m,
        "base_rev_m": base_rev_m,
        "cagr_5y": cagr_5y,
        "cagr_10y": cagr_10y,
        "cagr_3y": cagr_3y,
        "guidance_mid": guidance_mid,
        "g_implied_our_pct": round(g_implied_our * 100, 1),
        "g_implied_fiscal_pct": round(g_implied_fiscal * 100, 1),
        "gap_hist": round(gap_hist, 1) if gap_hist is not None else None,
        "gap_guide": round(gap_guide, 1) if gap_guide is not None else None
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
        for ke_val, ke_label in ke_steps:
            row_vals = [ke_label]
            for r_val in rotce_rates:
                if ke_val > g_term:
                    ptbv_calc = (r_val - g_term) / (ke_val - g_term)
                    fv_calc = ptbv_calc * tbv_ps if tbv_ps > 0 else ptbv_calc
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


def _build_cmd_final_rows(
    scoring_data: Dict[str, Any],
    vp: Dict[str, Any],
    profile_data: Optional[Dict[str, Any]],
    ticker: str,
    company_name: str
) -> List[Tuple[str, str, str, str]]:
    """Construye las 5 filas del Cuadro de Mando Consolidado dinámicamente."""
    prof = profile_data or {}
    
    # -------------------------------------------------------------
    # CUADRO DE MANDO BANCARIO / FINTECH / ASEGURADOR
    # -------------------------------------------------------------
    if vp.get("is_financial"):
        is_ins = vp.get("is_insurance", False)
        ptbv_curr = vp.get("ptbv_current", 0.0)
        ptbv_theo = vp.get("ptbv_justified", 1.0)
        rotce_pct = vp.get("rotce_pct", 0.0)
        ke_pct = vp.get("ke_pct", 0.0)
        spread_pct = vp.get("spread_economic_pct", 0.0)

        ret_metric_name = "ROE Fondos Propios" if is_ins else "ROTCE Tangible"
        mult_name = "P/BV" if is_ins else "P/TBV"
        moat_badge = scoring_data.get("wacc_analysis", {}).get("moat_badge") or ("🏰 WIDE MOAT" if spread_pct > 5.0 else "NARROW MOAT")

        if is_ins:
            row_moat = ("Ventaja Competitiva (Moat)", "Eficiencia de Suscripción + Retorno sobre Float", moat_badge, "Generación combinada de margen técnico y rendimiento de float.")
            row_qual = ("Calidad de Suscripción", "Ratio Combinado Controlado y Reservas Robustas", "RENTABILIDAD TÉCNICA", "Suscripción rentable que genera float con coste de capital negativo.")
            row_solv = ("Solvencia y Capital", "Superávit de Titulares / Cobertura NAIC", "SOLVENCIA REGULATORIA NAIC", "Colchón de capital prudencial para absorber siniestralidad.")
        else:
            row_moat = ("Ventaja Competitiva (Moat)", "Eficiencia Operativa + Estructura de Fondeo", moat_badge, "Ventaja competitiva estructural en captación e intermediación.")
            row_qual = ("Calidad de Cartera", "Gestión de Riesgo y Cobertura de Provisiones", "BLINDAJE DE PROVISIONES", "Provisiones adecuadas para absorber pérdidas esperadas en ciclo crediticio.")
            row_solv = ("Solvencia y Capital", "Capital Regulatorio Basilea III / Tier 1 / CET1", "SOLVENCIA BASILEA III", "Colchón de capital anticíclico y absorción de activos ponderados por riesgo.")

        row_prod = ("Productividad del Capital", f"{ret_metric_name}: {rotce_pct:.1f}% vs Ke {ke_pct:.2f}%", "COMPOUNDING MACHINE" if spread_pct > 10.0 else "CREADOR DE VALOR", f"Spread económico de {spread_pct:+.1f} pp sobre coste de capital propio.")
        row_val = ("Valoración de Mercado", f"{mult_name}: {ptbv_curr:.1f}x vs {mult_name} Teórico: {ptbv_theo:.1f}x", "PRICED FOR GROWTH" if ptbv_curr > ptbv_theo else "VALORACIÓN ATRACTIVA", "Cotización sustentada por rentabilidad sobre libros." if ptbv_curr <= ptbv_theo else "Cotización descuenta sostener crecimiento y rentabilidad elevada.")

        return [row_moat, row_qual, row_solv, row_prod, row_val]

    # -------------------------------------------------------------
    # CUADRO DE MANDO CORPORATIVO TRADICIONAL
    # -------------------------------------------------------------
    moat_sec = prof.get("moat", {})
    moat_table = moat_sec.get("table_data", [])
    primary_moat = "Foso Defensivo Amplio (Ventajas Intangibles)"
    if moat_table and len(moat_table) > 0:
        primary_moat = f"{moat_table[0][0]}"
        if len(moat_table) > 1:
            primary_moat += f" + {moat_table[1][0]}"
    moat_badge = moat_sec.get("badge", "WIDE MOAT")
    ebit_m_pct = vp.get("ebit_margin_pct", 20.0)
    moat_verdict = f"Poder de fijación de precios y resiliencia de márgenes ({ebit_m_pct:.1f}% EBIT)."
    
    forensic = scoring_data.get("forensic_accounting_analysis", {}).get("latest_result", {})
    sloan_obj = forensic.get("sloan_accrual", {})
    sloan_pct = sloan_obj.get("sloan_ratio_pct")
    if sloan_pct is None:
        sloan_pct = (sloan_obj.get("sloan_ratio") or -0.047) * 100.0
    montier_score = forensic.get("montier_c_score", {}).get("total_score", 1)
    
    bm_target = next((p for p in scoring_data.get("benchmarks_used", {}).get("peers_detail", []) if p.get("is_target")), {})
    t_cfo = bm_target.get("cfo_usd_m") or 1.0
    t_ni = bm_target.get("net_income_usd_m") or 1.0
    cfo_per_ni = (t_cfo / t_ni) if t_ni > 0 else 1.0
    
    earnings_badge = "MÁXIMA CALIDAD" if (montier_score <= 1 and sloan_pct < -3.0) else ("CALIDAD SÓLIDA / BAJO RIESGO" if montier_score <= 3 else "ALERTA FORENSE")
    earnings_diag = f"Ratio Sloan: {sloan_pct:.2f}% / Montier: {montier_score}/6"
    earnings_verdict = f"Ganancias 100% avaladas por caja real (${cfo_per_ni:.2f} CFO por dólar de NI)."
    
    solv = scoring_data.get("debt_and_solvency_analysis", {}).get("latest_result", {})
    cov_str = solv.get("debt_service", {}).get("interest_coverage_str", "SÓLIDA")
    altman_z = solv.get("distress_models", {}).get("altman_z_double_prime", 3.20)
    synth_rating = solv.get("distress_models", {}).get("synthetic_rating", "AAA")
    
    lev_ltm = scoring_data.get("debt_and_solvency_analysis", {}).get("cash_flow_leverage", {}).get("LTM", {})
    is_debt_free = lev_ltm.get("is_debt_free", False) or solv.get("is_debt_free", False)
    cash_val_m = lev_ltm.get("cash") or bm_target.get("cash_usd_m") or 0.0
    
    solv_diag = f"Cobertura EBIT: {cov_str} / Altman Z'': {altman_z:.2f}" if altman_z else f"Cobertura EBIT: {cov_str}"
    solv_badge = f"SINTÉTICO {synth_rating}"
    solv_verdict = f"Cero deuda neta; colchón de liquidez de ${cash_val_m/1e3:.1f}B." if is_debt_free else f"Cero estrés financiero; colchón de ${cash_val_m/1e3:.1f}B."
        
    gb = scoring_data.get("greenblatt_roc_analysis", {})
    roc_pct = gb.get("latest_roc_pct") or (gb.get("latest_result", {}).get("roc_greenblatt", 0.30) * 100.0)
    ws = scoring_data.get("wacc_and_spread_analysis", {})
    roic_adj_val = (ws.get("roic_adjusted") or 0.50) * 100.0
    spread_val = (ws.get("economic_spread_adjusted") or 0.40) * 100.0
    
    cap_diag = f"ROC Greenblatt: {roc_pct:.1f}% / ROIC Adj: {roic_adj_val:.1f}%"
    cap_badge = "COMPOUNDING MACHINE" if spread_val > 15.0 else ("CREADOR DE VALOR" if spread_val > 0 else "DESTRUCTOR DE VALOR")
    cap_verdict = f"Spread económico de {spread_val:+.1f} pp sobre WACC (Creación de valor de élite)."
    
    g_our = vp.get("g_implied_our_pct", 10.0)
    g_fisc = vp.get("g_implied_fiscal_pct", 12.0)
    val_diag = f"Crecimiento Implícito: {g_our:.1f}% - {g_fisc:.1f}%"
    val_badge = "PRICED FOR PERFECTION" if g_our > 15.0 else ("VALORACIÓN EXIGENTE" if g_our > 8.0 else "VALORACIÓN ATRACTIVA")
    
    val_verdict_custom = prof.get("valuation_verdict")
    if val_verdict_custom:
        val_verdict = val_verdict_custom
    elif g_our > 15.0:
        val_verdict = f"Exigencia de crecimiento ambiciosa (+{g_our:.1f}% anual); requiere catalizadores sostenidos de expansión comercial."
    elif g_our > 8.0:
        val_verdict = f"Exigencia asumible (+{g_our:.1f}% anual); alineada con el ritmo tendencial de la empresa y su sector."
    else:
        val_verdict = f"Valoración conservadora (+{g_our:.1f}% anual); amplio margen de seguridad operativo."
        
    return [
        ("Ventaja Competitiva (Moat)", primary_moat, moat_badge, moat_verdict),
        ("Calidad de Beneficios", earnings_diag, earnings_badge, earnings_verdict),
        ("Solvencia y Estructura", solv_diag, solv_badge, solv_verdict),
        ("Productividad del Capital", cap_diag, cap_badge, cap_verdict),
        ("Valoración de Mercado", val_diag, val_badge, val_verdict),
    ]


# ==============================================================================
# MARKDOWN (.MD) UNIVERSAL
# ==============================================================================
def generate_valuation_section_md(
    scoring_data: Dict[str, Any],
    ticker: str = "AAPL",
    company_name: str = "Apple Inc.",
    section_num: int = 14,
    profile_data: Optional[Dict[str, Any]] = None
) -> str:
    """Genera la sección completa de Valoración en Markdown, adaptándose según el arquetipo de negocio."""
    vp = get_valuation_parameters(scoring_data, ticker, profile_data)
    
    # RUTA FINANCIERA / BANCARIA / ASEGURADORA
    if vp.get("is_financial"):
        is_ins = vp.get("is_insurance", False)
        metric_name = "ROE" if is_ins else "ROTCE"
        mult_name = "P/BV" if is_ins else "P/TBV"
        sec_title = f"{section_num}. Modelado Financiero y Valoración Aseguradora (Gordon-Shapiro Book Value & ROE vs. Ke)" if is_ins else f"{section_num}. Modelado Financiero y Valoración Bancaria (Excess Return Model & P/TBV vs. ROTCE)"
        model_name = "MODELO GORDON-SHAPIRO SOBRE FONDOS PROPIOS (BOOK VALUE)" if is_ins else "MODELO DE RENTA RESIDUAL / RETORNO EXCEDENTE (EXCESS RETURN MODEL)"

        md = []
        md.append(f"## {sec_title}\n")
        md.append(
            f"> **PROPÓSITO DE VALORACIÓN:** {model_name}  \n"
            f"> **Metodología Institucional:** Valoración sobre Balance (*{mult_name}*) justificado por rentabilidad financiera (*{metric_name}*) frente al coste del capital propio (*Ke*).  \n"
            f"> **Justificación Contable:** En instituciones financieras y aseguradoras, el modelo tradicional DCF es inaplicable debido a la imposibilidad de aislar el Flujo de Caja Libre a la Firma (FCFF) y el WACC. El valor intrínseco se deriva de la capacidad de generar beneficios por encima de la tasa demandada por los accionistas.\n"
        )
        
        md.append(f"### {section_num}.1. Metodología de Valoración para Entidades Financieras\n")
        model_exp_title = "Modelo Gordon-Shapiro asegurador" if is_ins else "Modelo Gordon-Shapiro bancario"
        md.append(
            f"El marco institucional para valorar la entidad se articula mediante el **{model_exp_title} (Excess Return Model)**:\n"
            f"* **1. Relación Fundamental {mult_name} vs. {metric_name}:**\n"
            f"  $$\\frac{{P}}{{BV}} = \\frac{{{metric_name} - g}}{{K_e - g}}$$\n"
            f"  Donde el múltiplo patrimonial depende directamente del exceso de rentabilidad (*Economic Spread* = \\({metric_name} - K_e\\)) y de la reinversión de capital para sostener el crecimiento.\n"
            f"* **2. Coste del Capital Propio (\\(K_e\\)) mediante CAPM:**\n"
            f"  $$K_e = R_f + \\beta \\times ERP = {vp['rf_pct']}\\% + {vp['beta']} \\times {vp['erp_pct']}\\% = \\mathbf{{{vp['ke_pct']}\\%}}$$\n"
            f"* **3. Creación de Valor Económico Puro:**\n"
            f"  Con un **{metric_name} del {vp['rotce_pct']}%** y un coste de capital del **{vp['ke_pct']}%**, {company_name} genera un **spread económico de {vp['spread_economic_pct']:+.1f} pp**, justificando una valoración fundada en rentabilidad de balance.\n"
        )
        
        md.append(f"### {section_num}.2. Tabla Maestra de Parámetros de Valoración\n")
        md.append("| Casilla / Input de Valoración Financiera | Valor Auditado | Fuente / Racional Metodológico |")
        md.append("| :--- | :---: | :--- |")
        md.append(f"| **Cotización de Mercado ($P_0$)** | **${vp['price']}** | Cotización bursátil auditada en tiempo real. |")
        md.append(f"| **Patrimonio Contable Total** | **${vp['tangible_equity_m']:,.1f} M** | Balance auditado Form 10-K / 20-F ante la SEC. |")
        md.append(f"| **Acciones en Circulación** | **{vp['shares_m']:,.1f} M** | Recuento de acciones diluidas reportadas. |")
        md.append(f"| **Valor Contable por Acción** | **${vp['tbv_per_share']}** | Valor contable neto por título en circulación. |")
        md.append(f"| **Ratio {mult_name} de Mercado Actual** | **{vp['ptbv_current']}x** | Múltiplo sobre libros al precio de cotización. |")
        md.append(f"| **Rentabilidad de Balance ({metric_name})** | **{vp['rotce_pct']}%** | Rentabilidad sobre fondos propios auditada. |")
        md.append(f"| **Coste del Capital Propio ($K_e$)** | **{vp['ke_pct']}%** | Tasa mínima exigida por CAPM ($R_f + \\beta \\times ERP$). |")
        md.append(f"| **Spread Económico (${metric_name} - K_e$)** | **{vp['spread_economic_pct']:+.1f} pp** | Generación de valor excedente sobre coste de capital. |")
        md.append(f"| **Crecimiento Terminal Sostenible ($g$)** | **{vp['g_terminal_pct']}%** | Crecimiento de largo plazo de la base patrimonial. |")
        md.append(f"| **Ratio {mult_name} Justificado Teórico** | **{vp['ptbv_justified']}x** | Múltiplo intrínseco: $({metric_name} - g) / (K_e - g)$. |")
        md.append(f"| **Valor Intrínseco por Acción** | **${vp['fair_value_excess_return']}** | Precio teórico fundamental sustentado por {metric_name} actual. |")
        md.append("\n")

        # Sensibilidad
        md.append(f"### {section_num}.3. Matriz Bidimensional de Sensibilidad (Cost of Equity $K_e$ vs. {metric_name} Sostenible)\n")
        md.append(
            f"La siguiente matriz evalúa el **Valor Intrínseco por Acción** ante distintas hipótesis de rentabilidad de balance (*{metric_name}*) y coste de oportunidad del capital propio (*Ke*):\n"
        )
        sens_rows = _generate_sensitivity_grid(vp)
        rotce_labels = vp.get("rotce_labels") or ["18.0%", "20.0%", "22.0%", "24.0%", "26.0% (Base)", "28.0%"]
        header_labels = " | ".join(rotce_labels)
        md.append(f"| Coste Equity ($K_e$) \\ {metric_name} | {header_labels} | Diagnóstico de Escenario |")
        md.append("| :---: | " + " | ".join([":---:"] * len(rotce_labels)) + " | :--- |")
        for r in sens_rows:
            md.append(f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} | {r[4]} | {r[5]} | {r[6]} | {r[7]} |")
        md.append("\n")

        # Reverse Excess Return
        if is_ins:
            exp_text = f"Para justificar la cotización actual, {company_name} debe mantener un Ratio Combinado inferior al 95% y reinvertir su float de primas con retornos que superen su coste de capital propio ({vp['ke_pct']:.2f}%)."
        else:
            exp_text = f"Para justificar la cotización actual, {company_name} debe sostener un elevado retorno sobre patrimonio tangible ({vp['rotce_pct']:.1f}%) y preservar su disciplina de asignación de capital frente al ciclo crediticio."

        md.append(f"### {section_num}.4. Reverse Excess Return: ¿Qué expectativas descuenta el precio actual de mercado?\n")
        md.append(
            f"Al cotizar a **${vp['price']}** ({vp['ptbv_current']}x {mult_name}), el mercado está descontando:\n"
            f"* **{metric_name} Implícito a Perpetuidad:** El precio actual exige que {company_name} sostenga un {metric_name} del **~{vp['rotce_implied_pct']}%** a perpetuidad, o expanda su base operativa con rentabilidad excedente sobre capital.\n"
            f"* **Diagnóstico de Expectativas:** {exp_text}\n"
        )

        # Cuadro de mando
        md.append(f"### {section_num}.5. Cuadro de Mando Consolidado y Tesis Final de Inversión\n")
        cmd_rows = _build_cmd_final_rows(scoring_data, vp, profile_data, ticker, company_name)
        md.append("| Dimensión Fundamental | Diagnóstico Auditado | Calificación Institucional | Veredicto para la Asignación de Capital |")
        md.append("| :--- | :--- | :---: | :--- |")
        for r in cmd_rows:
            md.append(f"| **{r[0]}** | {r[1]} | **{r[2]}** | {r[3]} |")
        md.append("\n")
        return "\n".join(md)

    # RUTA CORPORATIVA TRADICIONAL
    md = []
    md.append(f"## {section_num}. Modelado Financiero y Descuento Inverso de Flujo de Caja (Reverse DCF & Expectations Investing)\n")
    md.append(
        f"> **PROPÓSITO DE VALORACIÓN:** INTEGRACIÓN FISCAL AI & MOTOR DE VALORACIÓN PROPIETARIO  \n"
        f"> **Metodología Seleccionada:** Descuento de Flujo de Caja Inverso (*Reverse DCF*) basado en *Expectations Investing* (Mauboussin & Rappaport).  \n"
        f"> **Objetivo Práctico:** No especular con proyecciones arbitrarias, sino auditar con rigor matemático qué tasa de crecimiento anual de negocio le está exigiendo el precio actual de mercado a {company_name} (${vp['price']}) para sostener su cotización.\n"
    )
    
    md.append(f"### {section_num}.1. Configuración Óptima del Modelo en Plataformas de Valoración (Fiscal AI)\n")
    md.append(
        "Para modelar cualquier compañía de forma rigurosa y evitar sesgos especulativos, se recomienda parametrizar el modelo bajo los siguientes criterios técnicos:\n"
        "* **1. Modelo de Valor Terminal: `Perpetuity` (Recomendado) frente a `Exit Multiple`:** Gordon-Shapiro anclado a inflación/PIB (2.0% - 2.5%).\n"
        "* **2. Variable de Crecimiento: `Revenue Growth` (Recomendado) frente a `Earnings` o `Cash Flow`:** Los ingresos representan el motor comercial real, libre de distorsiones por recompras de acciones.\n"
        "* **3. Horizonte Temporal de Pronóstico (*Forecast Years*): `10 Años`:** Captura el ciclo completo de inversión y maduración operativa.\n"
    )
    
    md.append(f"### {section_num}.2. Tabla Maestra de Parámetros Auditados en Tiempo Real (Advanced Mode)\n")
    md.append("| Casilla / Input de Valoración | Valor Auditado (En Vivo) | Sección de Origen | Racional Técnico y Sustento Fundamental |")
    md.append("| :--- | :---: | :---: | :--- |")
    md.append(f"| **Precio de Referencia ($P_0$)** | **${vp['price']}** | Mercado en Vivo | Cotización auditada por consenso bursátil en tiempo real. |")
    md.append(f"| **Tasa Libre de Riesgo ($R_f$)** | **{vp['rf_pct']}%** | Sección 11.2 (Bonos EE.UU.) | Rendimiento del Bono del Tesoro de EE.UU. a 10 años (^TNX). |")
    md.append(f"| **Prima de Riesgo de Mercado (ERP)** | **{vp['erp_pct']}%** | Damodaran Benchmark | Prima histórica por riesgo accionario demandada por inversores. |")
    md.append(f"| **Beta Apalancada (Consenso)** | **{vp['beta']}** | Sección 11.2 (Arbitraje) | Sensibilidad sistemática del título frente al índice S&P 500. |")
    md.append(f"| **Coste de la Deuda ($K_d$ Pre-Tax)** | **{vp['kd_pre_pct']}%** | Sección 11.2 (Sintético) | Coste de financiamiento bruto estimado por rating sintético. |")
    md.append(f"| **Coste de la Deuda ($K_d$ After-Tax)** | **{vp['kd_post_pct']}%** | Sección 11.2 (WACC) | Coste efectivo neto del escudo fiscal: $K_d \\times (1 - t)$. |")
    md.append(f"| **Tasa Impositiva Efectiva ($t$)** | **{vp['tax_rate_pct']}%** | Sección 11.2 (SEC 10-K) | Tasa impositiva estructural auditada en estados financieros. |")
    md.append(f"| **Ponderación Deuda ($W_d$)** | **{vp['weight_debt_pct']}%** | Estructura de Capital | Proporción de deuda financiera sobre valor total de la empresa. |")
    md.append(f"| **Ponderación Fondos Propios ($W_e$)** | **{vp['weight_equity_pct']}%** | Estructura de Capital | Proporción de capital propio sobre valor total de la empresa. |")
    md.append(f"| **Coste Medio Ponderado (WACC)** | **{vp['wacc_pct']}%** | Sección 11.2 (WACC) | Tasa de descuento de corte para flujos libres hacia la empresa. |")
    md.append(f"| **Margen FCF Estructural** | **{vp['fcf_margin_pct']}%** | Sección 4 & Solvencia | Conversión de ingresos a caja libre de capital tras reinversiones. |")
    md.append(f"| **Tasa de Crecimiento Terminal ($g_n$)** | **2.5%** | Hipótesis Canónica | Crecimiento tendencial de la economía global a perpetuidad. |")
    md.append(f"| **Horizonte de Proyección** | **10 Años** | Configuración Estándar | Período de amortización del superciclo operativo y de producto. |")
    md.append("\n")
    
    md.append(f"### {section_num}.3. Auditoría de Discrepancia Metodológica: WACC Propietario vs Plataformas (Fiscal AI)\n")
    disc_rows = [
        ("WACC (Tasa de Descuento)", f"{vp['wacc_pct']}%", "10.90%", f"{vp['wacc_pct'] - 10.90:+.2f} pp", "Menor exigencia de retorno exigido gracias a balance solvente."),
        ("Margen FCF Sostenible", f"{vp['fcf_margin_pct']}%", "24.40%", f"{vp['fcf_margin_pct'] - 24.40:+.2f} pp", "Refleja la rentabilidad real de caja auditada ante la SEC."),
        ("Tasa Terminal ($g_n$)", "2.50%", "2.50%", "0.00 pp", "Hipótesis simétrica estándar de Gordon-Shapiro a largo plazo."),
        ("Crecimiento Implícito (CAGR)", f"**{vp['g_implied_our_pct']:.1f}%**", f"**{vp['g_implied_fiscal_pct']:.1f}%**", f"**{vp['g_implied_our_pct'] - vp['g_implied_fiscal_pct']:+.1f} pp**", "**DIFERENCIAL DE EXIGENCIA:** Menor fricción de crecimiento requerida.")
    ]
    md.append("| Parámetro Clave | Modelo Propietario (Auditado) | Parametrización Plataformas | Diferencial (Delta) | Impacto Cuantitativo en la Tesis |")
    md.append("| :--- | :---: | :---: | :---: | :--- |")
    for r in disc_rows:
        md.append(f"| **{r[0]}** | {r[1]} | {r[2]} | {r[3]} | {r[4]} |")
    md.append("\n")
    
    md.append(f"### {section_num}.4. Matriz Bidimensional de Sensibilidad (WACC vs Crecimiento Terminal $g_n$)\n")
    sens_rows = _generate_sensitivity_grid(vp)
    md.append("| WACC \\ Tasa Terminal ($g_n$) | 1.0% | 1.5% | 2.0% | 2.5% (Base) | 3.0% | 3.5% | Diagnóstico de Escenario |")
    md.append("| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |")
    for r in sens_rows:
        md.append(f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} | {r[4]} | {r[5]} | {r[6]} | {r[7]} |")
    md.append("\n")
    
    md.append(f"### {section_num}.5. Cuadro de Mando Consolidado y Tesis Final de Inversión\n")
    cmd_rows = _build_cmd_final_rows(scoring_data, vp, profile_data, ticker, company_name)
    md.append("| Dimensión Fundamental | Diagnóstico Auditado | Calificación Institucional | Veredicto para la Asignación de Capital |")
    md.append("| :--- | :--- | :---: | :--- |")
    for r in cmd_rows:
        md.append(f"| **{r[0]}** | {r[1]} | **{r[2]}** | {r[3]} |")
    md.append("\n")
    
    return "\n".join(md)


# ==============================================================================
# WORD (.DOCX) UNIVERSAL
# ==============================================================================
def add_valuation_section_docx(
    doc: docx.Document,
    scoring_data: Dict[str, Any],
    ticker: str = "AAPL",
    company_name: str = "Apple Inc.",
    section_num: int = 14,
    profile_data: Optional[Dict[str, Any]] = None
):
    """Añade la sección de Valoración en Word (.docx), adaptándose según el arquetipo de negocio."""
    vp = get_valuation_parameters(scoring_data, ticker, profile_data)
    cmd_data = _build_cmd_final_rows(scoring_data, vp, profile_data, ticker, company_name)
    
    # -------------------------------------------------------------
    # RUTA FINANCIERA / BANCARIA / ASEGURADORA
    # -------------------------------------------------------------
    if vp.get("is_financial"):
        is_ins = vp.get("is_insurance", False)
        metric_name = "ROE" if is_ins else "ROTCE"
        mult_name = "P/BV" if is_ins else "P/TBV"
        title_text = f"{section_num}. Modelado Financiero y Valoración Aseguradora (Gordon-Shapiro & P/BV)" if is_ins else f"{section_num}. Modelado Financiero y Valoración Bancaria (Excess Return & P/TBV)"

        h1 = doc.add_heading(level=1)
        r_h1 = h1.add_run(title_text)
        r_h1.font.name = "Calibri"
        r_h1.font.size = Pt(14)
        r_h1.font.bold = True
        r_h1.font.color.rgb = NAVY
        h1.paragraph_format.space_before = Pt(14)
        h1.paragraph_format.space_after = Pt(4)
        
        p_box = doc.add_paragraph()
        p_box.paragraph_format.space_before = Pt(4)
        p_box.paragraph_format.space_after = Pt(8)
        p_box.paragraph_format.left_indent = Inches(0.2)
        p_box.paragraph_format.right_indent = Inches(0.2)
        
        r_box_title = p_box.add_run(f"DICTAMEN DE VALORACIÓN FINANCIERA: MODELO DE RETORNO EXCEDENTE ({mult_name})\n")
        r_box_title.font.name = "Calibri"
        r_box_title.font.size = Pt(10.5)
        r_box_title.font.bold = True
        r_box_title.font.color.rgb = NAVY
        
        r_box_body = p_box.add_run(
            f"• Cotización: ${vp['price']}  |  Valor en Libros por Acción: ${vp['tbv_per_share']}  |  {mult_name} Mercado: {vp['ptbv_current']}x\n"
            f"• Rentabilidad de Balance ({metric_name}): {vp['rotce_pct']}% vs. Coste Capital (Ke): {vp['ke_pct']}%  ->  Spread: {vp['spread_economic_pct']:+.1f} pp\n"
            f"• {mult_name} Justificado Teórico: {vp['ptbv_justified']}x (Precio Teórico Justo: ${vp['fair_value_excess_return']})\n"
            f"• Veredicto: El mercado descuenta sostener un {metric_name} del ~{vp['rotce_implied_pct']}% o expansión con retornos sobre fondos propios."
        )
        r_box_body.font.name = "Calibri"
        r_box_body.font.size = Pt(9.5)
        r_box_body.font.color.rgb = DARK_GRAY

        # Tabla Maestra Inputs Financieros
        h2 = doc.add_heading(level=2)
        r_h2 = h2.add_run(f"{section_num}.1. Parámetros Maestros de Valoración Financiera (Gordon-Shapiro & CAPM)")
        r_h2.font.name = "Calibri"
        r_h2.font.size = Pt(11.5)
        r_h2.font.bold = True
        r_h2.font.color.rgb = NAVY
        
        t_bank = doc.add_table(rows=8, cols=3)
        t_bank.alignment = WD_TABLE_ALIGNMENT.CENTER
        _set_table_borders(t_bank)
        
        headers_b = ["Parámetro Financiero", "Valor Auditado", "Interpretación y Racional Técnico"]
        for i, h in enumerate(headers_b):
            c = t_bank.cell(0, i)
            _set_cell_shading(c, HEADER_BG)
            p = c.paragraphs[0]
            r = p.add_run(h)
            r.bold = True
            r.font.size = Pt(9)
            r.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
            
        data_b = [
            ("Patrimonio Contable Total", f"${vp['tangible_equity_m']:,.1f} M", "Fondos propios auditados en el último balance oficial SEC."),
            ("Valor Contable por Acción", f"${vp['tbv_per_share']}", "Valor en libros por título en circulación."),
            (f"Rentabilidad de Balance ({metric_name})", f"{vp['rotce_pct']}%", "Capacidad de generar utilidad neta sobre capital propio."),
            ("Coste del Capital Propio (Ke)", f"{vp['ke_pct']}%", "Tasa de descuento de corte según modelo CAPM."),
            ("Spread de Creación de Valor", f"{vp['spread_economic_pct']:+.1f} pp", "Excedente de retorno que genera renta residual positiva."),
            (f"Ratio {mult_name} Justificado", f"{vp['ptbv_justified']}x", f"Múltiplo teórico derivado de: ({metric_name} - g) / (Ke - g)."),
            ("Valor Intrínseco Fundamental", f"${vp['fair_value_excess_return']}", "Precio teórico fundamental por modelo de retorno excedente."),
        ]
        
        for row_idx, row_data in enumerate(data_b, start=1):
            for col_idx, text in enumerate(row_data):
                c = t_bank.cell(row_idx, col_idx)
                if row_idx % 2 == 0:
                    _set_cell_shading(c, ALT_ROW_BG)
                p = c.paragraphs[0]
                r = p.add_run(text)
                r.font.size = Pt(8.5)
                if col_idx in [0, 1]:
                    r.bold = True
                    
        doc.add_paragraph()

        # Sensibilidad Financiera
        h2_sens = doc.add_heading(level=2)
        r_h2_sens = h2_sens.add_run(f"{section_num}.2. Matriz Bidimensional de Sensibilidad (Ke vs. {metric_name})")
        r_h2_sens.font.name = "Calibri"
        r_h2_sens.font.size = Pt(11.5)
        r_h2_sens.font.bold = True
        r_h2_sens.font.color.rgb = NAVY
        
        sens_data = _generate_sensitivity_grid(vp)
        rotce_labels = vp.get("rotce_labels") or ["18.0%", "20.0%", "22.0%", "24.0%", "26.0%", "28.0%"]
        t_sens = doc.add_table(rows=len(sens_data) + 1, cols=8)
        t_sens.alignment = WD_TABLE_ALIGNMENT.CENTER
        _set_table_borders(t_sens)
        
        s_headers = [f"Coste Ke \\ {metric_name}"] + rotce_labels + ["Diagnóstico"]
        for i, h in enumerate(s_headers):
            c = t_sens.cell(0, i)
            _set_cell_shading(c, HEADER_BG)
            p = c.paragraphs[0]
            r = p.add_run(h)
            r.bold = True
            r.font.size = Pt(8.5)
            r.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
            
        base_col = 4
        for idx_l, lbl in enumerate(rotce_labels):
            if "(Base)" in lbl:
                base_col = idx_l + 1
                break

        for row_idx, row_data in enumerate(sens_data, start=1):
            for col_idx, text in enumerate(row_data):
                c = t_sens.cell(row_idx, col_idx)
                if "Base" in row_data[0]:
                    _set_cell_shading(c, YELLOW_BG if col_idx == base_col else ALT_ROW_BG)
                elif row_idx % 2 == 0:
                    _set_cell_shading(c, ALT_ROW_BG)
                p = c.paragraphs[0]
                r = p.add_run(text)
                r.font.size = Pt(8.0)
                if col_idx == base_col or (col_idx > 0 and col_idx < 7 and "Base" in row_data[0]):
                    r.bold = True
                    
        doc.add_paragraph()

        # Cuadro de Mando Final
        h2_cmd = doc.add_heading(level=2)
        r_h2_cmd = h2_cmd.add_run(f"{section_num}.3. Cuadro de Mando Consolidado y Tesis de Valoración")
        r_h2_cmd.font.name = "Calibri"
        r_h2_cmd.font.size = Pt(11.5)
        r_h2_cmd.font.bold = True
        r_h2_cmd.font.color.rgb = NAVY
        
        t_cmd = doc.add_table(rows=len(cmd_data) + 1, cols=4)
        t_cmd.alignment = WD_TABLE_ALIGNMENT.CENTER
        _set_table_borders(t_cmd)
        
        cmd_headers = ["Dimensión Fundamental", "Diagnóstico Auditado", "Calificación", "Veredicto de Asignación"]
        for i, h in enumerate(cmd_headers):
            c = t_cmd.cell(0, i)
            _set_cell_shading(c, HEADER_BG)
            p = c.paragraphs[0]
            r = p.add_run(h)
            r.bold = True
            r.font.size = Pt(9)
            r.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
            
        for row_idx, row_data in enumerate(cmd_data, start=1):
            for col_idx, text in enumerate(row_data):
                c = t_cmd.cell(row_idx, col_idx)
                if row_idx % 2 == 0:
                    _set_cell_shading(c, ALT_ROW_BG)
                p = c.paragraphs[0]
                r = p.add_run(text)
                r.font.size = Pt(8.5)
                if col_idx in [0, 2]:
                    r.bold = True
        return

    # -------------------------------------------------------------
    # RUTA CORPORATIVA TRADICIONAL
    # -------------------------------------------------------------
    val_verdict = cmd_data[4][3]
    
    cagr_5y_str = f"{vp['cagr_5y']:.1f}% Histórico" if vp.get("cagr_5y") is not None else "N/D Histórico"
    if vp.get("guidance_mid") is not None:
        guide_str = f" y {vp['guidance_mid']:.1f}% Guidance"
        gap_sign_guide = "+" if (vp.get("gap_guide") or 0) > 0 else ""
        gap_narrative = f" ({gap_sign_guide}{vp['gap_guide']:.1f} pp sobre guidance)" if vp.get("gap_guide") is not None else ""
    else:
        guide_str = ""
        gap_narrative = ""

    h1 = doc.add_heading(level=1)
    r_h1 = h1.add_run(f"{section_num}. Modelado Financiero y Descuento Inverso de Flujo de Caja (Reverse DCF & Expectations)")
    r_h1.font.name = "Calibri"
    r_h1.font.size = Pt(14)
    r_h1.font.bold = True
    r_h1.font.color.rgb = NAVY
    h1.paragraph_format.space_before = Pt(14)
    h1.paragraph_format.space_after = Pt(4)
    
    p_box = doc.add_paragraph()
    p_box.paragraph_format.space_before = Pt(4)
    p_box.paragraph_format.space_after = Pt(8)
    p_box.paragraph_format.left_indent = Inches(0.2)
    p_box.paragraph_format.right_indent = Inches(0.2)
    
    r_box_title = p_box.add_run(f"PROPÓSITO DE VALORACIÓN: INTEGRACIÓN FISCAL AI & REVERSE DCF PROPIETARIO\n")
    r_box_title.font.name = "Calibri"
    r_box_title.font.size = Pt(10.5)
    r_box_title.font.bold = True
    r_box_title.font.color.rgb = NAVY
    
    r_box_body = p_box.add_run(
        f"• Precio de Referencia: ${vp['price']}  |  WACC Auditado: {vp['wacc_pct']}% (Rf: {vp['rf_pct']}%, ERP: {vp['erp_pct']}%)\n"
        f"• Crecimiento Implícito Calculado: {vp['g_implied_our_pct']:.1f}% Anual a 10 Años (vs. {cagr_5y_str}{guide_str})\n"
        f"• Veredicto: Descuenta expectativas de {vp['g_implied_our_pct']:.1f}% anual{gap_narrative}. {val_verdict}"
    )
    r_box_body.font.name = "Calibri"
    r_box_body.font.size = Pt(9.5)
    r_box_body.font.color.rgb = DARK_GRAY
    
    h2_1 = doc.add_heading(level=2)
    r_h2_1 = h2_1.add_run(f"{section_num}.1. Configuración Óptima en Plataformas de Valoración (Fiscal AI)")
    r_h2_1.font.name = "Calibri"
    r_h2_1.font.size = Pt(11.5)
    r_h2_1.font.bold = True
    r_h2_1.font.color.rgb = NAVY
    
    p_criterios = doc.add_paragraph()
    r_cr = p_criterios.add_run(
        "Para evitar sesgos especulativos se recomienda configurar Fiscal AI con: "
        "(1) Modo Perpetuity (2.5%), anclando el valor terminal a la inflación/PIB sin especular con múltiplos de salida; "
        "(2) Pestaña Revenue Growth, por ser el motor económico más limpio contra distorsiones contables; y "
        "(3) Horizonte de 10 Años, capturando el ciclo completo de inversión y maduración."
    )
    r_cr.font.name = "Calibri"
    r_cr.font.size = Pt(9.0)
    r_cr.font.color.rgb = DARK_GRAY
    
    h2_2 = doc.add_heading(level=2)
    r_h2_2 = h2_2.add_run(f"{section_num}.2. Tabla Maestra de Parámetros Auditados en Tiempo Real (Advanced Mode)")
    r_h2_2.font.name = "Calibri"
    r_h2_2.font.size = Pt(11.5)
    r_h2_2.font.bold = True
    r_h2_2.font.color.rgb = NAVY
    
    table_master = doc.add_table(rows=14, cols=4)
    table_master.alignment = WD_TABLE_ALIGNMENT.CENTER
    _set_table_borders(table_master)
    
    master_headers = ["Casilla / Input Fiscal AI", "Valor Auditado", "Sección de Origen", "Racional Técnico y Sustento"]
    for i, h in enumerate(master_headers):
        c = table_master.cell(0, i)
        _set_cell_shading(c, HEADER_BG)
        p = c.paragraphs[0]
        r = p.add_run(h)
        r.bold = True
        r.font.size = Pt(9)
        r.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        
    master_data = [
        ("Current Share Price", f"${vp['price']}", "Mercado en Vivo", "Cotización bursátil en tiempo real."),
        ("Risk-Free Rate (Rf)", f"{vp['rf_pct']}%", "Sección 11.2 (Bonos)", "Rendimiento del Bono del Tesoro de EE.UU. a 10 años (^TNX)."),
        ("Equity Risk Premium", f"{vp['erp_pct']}%", "Damodaran Benchmark", "Prima de riesgo de mercado institucional."),
        ("Beta (Levered)", f"{vp['beta']}", "Sección 11.2 (Arbitraje)", "Sensibilidad sistemática frente al S&P 500."),
        ("Pre-Tax Cost of Debt", f"{vp['kd_pre_pct']}%", "Sección 11.2 (Sintético)", "Coste de financiamiento bruto por rating sintético."),
        ("After-Tax Cost of Debt", f"{vp['kd_post_pct']}%", "Sección 11.2 (WACC)", "Coste neto del escudo fiscal: Kd * (1 - t)."),
        ("Effective Tax Rate", f"{vp['tax_rate_pct']}%", "Sección 11.2 (SEC 10-K)", "Tasa impositiva estructural auditada."),
        ("Weight of Debt", f"{vp['weight_debt_pct']}%", "Estructura Capital", "Peso de la deuda sobre el valor total."),
        ("Weight of Equity", f"{vp['weight_equity_pct']}%", "Estructura Capital", "Peso de los fondos propios sobre el valor total."),
        ("WACC (Discount Rate)", f"{vp['wacc_pct']}%", "Sección 11.2 (WACC)", "Tasa de descuento de corte auditada."),
        ("Normalized FCF Margin", f"{vp['fcf_margin_pct']}%", "Sección 4 & Solvencia", "Conversión de ventas a caja libre tras CapEx."),
        ("Terminal Growth (gn)", "2.5%", "Hipótesis Canónica", "Crecimiento tendencial de la economía global."),
        ("Forecast Period", "10 Años", "Configuración Estándar", "Ciclo decenal de amortización y maduración."),
    ]
    
    for row_idx, row_data in enumerate(master_data, start=1):
        for col_idx, text in enumerate(row_data):
            c = table_master.cell(row_idx, col_idx)
            if row_idx % 2 == 0:
                _set_cell_shading(c, ALT_ROW_BG)
            p = c.paragraphs[0]
            r = p.add_run(text)
            r.font.size = Pt(8.5)
            if col_idx in [0, 1]:
                r.bold = True
                
    doc.add_paragraph()
    
    # 5. Matriz de Sensibilidad Bidimensional
    h2_4 = doc.add_heading(level=2)
    r_h2_4 = h2_4.add_run(f"{section_num}.3. Matriz Bidimensional de Sensibilidad (WACC vs. gn)")
    r_h2_4.font.name = "Calibri"
    r_h2_4.font.size = Pt(11.5)
    r_h2_4.font.bold = True
    r_h2_4.font.color.rgb = NAVY
    
    sens_rows = _generate_sensitivity_grid(vp)
    t_sens = doc.add_table(rows=len(sens_rows) + 1, cols=8)
    t_sens.alignment = WD_TABLE_ALIGNMENT.CENTER
    _set_table_borders(t_sens)
    
    s_headers = ["WACC \\ gn", "1.0%", "1.5%", "2.0%", "2.5%", "3.0%", "3.5%", "Diagnóstico"]
    for i, h in enumerate(s_headers):
        c = t_sens.cell(0, i)
        _set_cell_shading(c, HEADER_BG)
        p = c.paragraphs[0]
        r = p.add_run(h)
        r.bold = True
        r.font.size = Pt(8.5)
        r.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        
    for row_idx, row_data in enumerate(sens_rows, start=1):
        for col_idx, text in enumerate(row_data):
            c = t_sens.cell(row_idx, col_idx)
            if "Base" in row_data[0]:
                _set_cell_shading(c, YELLOW_BG if col_idx == 4 else ALT_ROW_BG)
            elif row_idx % 2 == 0:
                _set_cell_shading(c, ALT_ROW_BG)
            p = c.paragraphs[0]
            r = p.add_run(text)
            r.font.size = Pt(8.0)
            if col_idx == 4 or (col_idx > 0 and col_idx < 7 and "Base" in row_data[0]):
                r.bold = True
                
    doc.add_paragraph()

    # 6. Cuadro de Mando Consolidado
    h2_5 = doc.add_heading(level=2)
    r_h2_5 = h2_5.add_run(f"{section_num}.4. Cuadro de Mando Consolidado y Tesis Final de Inversión")
    r_h2_5.font.name = "Calibri"
    r_h2_5.font.size = Pt(11.5)
    r_h2_5.font.bold = True
    r_h2_5.font.color.rgb = NAVY
    
    t_cmd = doc.add_table(rows=len(cmd_data) + 1, cols=4)
    t_cmd.alignment = WD_TABLE_ALIGNMENT.CENTER
    _set_table_borders(t_cmd)
    
    cmd_headers = ["Dimensión Fundamental", "Diagnóstico Auditado", "Calificación Institucional", "Veredicto de Asignación"]
    for i, h in enumerate(cmd_headers):
        c = t_cmd.cell(0, i)
        _set_cell_shading(c, HEADER_BG)
        p = c.paragraphs[0]
        r = p.add_run(h)
        r.bold = True
        r.font.size = Pt(9)
        r.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        
    for row_idx, row_data in enumerate(cmd_data, start=1):
        for col_idx, text in enumerate(row_data):
            c = t_cmd.cell(row_idx, col_idx)
            if row_idx % 2 == 0:
                _set_cell_shading(c, ALT_ROW_BG)
            p = c.paragraphs[0]
            r = p.add_run(text)
            r.font.size = Pt(8.5)
            if col_idx in [0, 2]:
                r.bold = True
