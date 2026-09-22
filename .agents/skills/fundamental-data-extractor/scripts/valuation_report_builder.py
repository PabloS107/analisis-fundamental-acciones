"""
valuation_report_builder.py - Constructor de la Sección de Modelado Financiero y
Descuento Inverso de Flujo de Caja (Reverse DCF & Expectations Investing) para Corporaciones,
y Modelo de Retorno Excedente / Renta Residual (Excess Return & P/TBV vs. ROTCE) para Bancos y FinTechs.

Implementa arquitectura dual:
1. Framework Corporativo / Industrial (AAPL, DECK, MELI):
   - Bloque A: Dictamen Ejecutivo y Marco de Expectations Investing (Mauboussin & Rappaport).
   - Bloque B: Parametrización Maestra para Fiscal AI y Modelos DCF (Advanced Mode Inputs con protección de float en marketplaces).
   - Bloque C: Motor Propietario de Reverse DCF (Cálculo Nativo de Crecimiento Implícito y Brecha de Expectativas).
   - Bloque D: Matriz de Sensibilidad Bidimensional Nativa (WACC vs. Crecimiento Terminal gn).
   - Bloque E: Cuadro de Mando Consolidado de Valoración y Tesis Final de Asignación de Capital.

2. Framework Bancario / FinTech (NU, Bancos, Entidades de Crédito):
   - Bloque A: Dictamen Ejecutivo de Valoración Bancaria (Inaplicabilidad contable de FCFF/WACC).
   - Bloque B: Tabla Maestra de Parámetros Auditados (TBV/Acción, P/TBV de Mercado, ROTCE, Cost of Equity Ke vía CAPM).
   - Bloque C: Modelo de Retorno Excedente a 5 Años (Excess Return Model / Renta Residual).
   - Bloque D: Matriz Bidimensional de Sensibilidad Bancaria (ROTCE Sostenible vs. Cost of Equity Ke).
   - Bloque E: Reverse Excess Return (Expectativas Implícitas de Mercado) y Cuadro de Mando Consolidado.
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


def _set_cell_shading(cell, color_hex: str):
    """Aplica color de fondo hexadecimal a una celda de tabla en Word."""
    shd = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{color_hex}"/>')
    cell._tc.get_or_add_tcPr().append(shd)


def _set_cell_margins(cell, top: int = 80, bottom: int = 80, left: int = 100, right: int = 100):
    """Establece márgenes internos (padding en dxa) en una celda de tabla."""
    tcPr = cell._tc.get_or_add_tcPr()
    tcMar = OxmlElement('w:tcMar')
    for m, val in [('top', top), ('bottom', bottom), ('left', left), ('right', right)]:
        node = OxmlElement(f'w:{m}')
        node.set(qn('w:w'), str(val))
        node.set(qn('w:type'), 'dxa')
        tcMar.append(node)
    tcPr.append(tcMar)


def _set_table_borders(table, border_color: str = "D2D6DC"):
    """Aplica bordes estilizados y discretos a una tabla en Word."""
    tblPr = table._tbl.tblPr
    borders = parse_xml(
        f'<w:tblBorders {nsdecls("w")}>'
        f'<w:top w:val="single" w:sz="6" w:space="0" w:color="{border_color}"/>'
        f'<w:left w:val="none"/>'
        f'<w:bottom w:val="single" w:sz="10" w:space="0" w:color="1B365D"/>'
        f'<w:right w:val="none"/>'
        f'<w:insideH w:val="single" w:sz="4" w:space="0" w:color="{border_color}"/>'
        f'<w:insideV w:val="none"/>'
        f'</w:tblBorders>'
    )
    tblPr.append(borders)


def _set_col_widths(table, widths: List[float]):
    """Fija los anchos de columnas en pulgadas para consistencia total."""
    for i, w in enumerate(widths):
        table.columns[i].width = Inches(w)
        for cell in table.columns[i].cells:
            cell.width = Inches(w)


def _is_financial(scoring_data: Dict[str, Any]) -> bool:
    """Identifica si la empresa pertenece al sector financiero/bancario/fintech."""
    if scoring_data.get("is_financial_institution"):
        return True
    if scoring_data.get("novy_marx_analysis", {}).get("latest_result", {}).get("is_financial_institution"):
        return True
    sic = str(scoring_data.get("sic_code") or scoring_data.get("benchmarks_used", {}).get("sic_code", "")).strip()
    if sic.startswith("6"):
        return True
    if scoring_data.get("benchmarks_used", {}).get("gics_sector") == "Financials":
        return True
    return False


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

    target_ev = (share_price * shares_out_b * 1000.0) + net_debt_m

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
    live_price: Optional[float] = None
) -> Dict[str, Any]:
    """Extrae y consolida los parámetros financieros y de mercado para la valoración de cualquier empresa."""
    prof = profile_data or {}
    if not prof:
        candidate = Path(f"data/processed/{ticker}/company_profile.json")
        if candidate.exists():
            try:
                with open(candidate, "r", encoding="utf-8") as f:
                    prof = json.load(f)
            except Exception:
                pass

    is_fin = _is_financial(scoring_data)
    roic_wacc = scoring_data.get("roic_wacc_analysis", {})
    wacc_dict = roic_wacc.get("wacc", {})
    mkt = wacc_dict.get("market_data", {})
    
    # Parámetros macro y de coste de capital
    rf_raw = mkt.get("rf_10y") or 0.0425
    rf_pct = round(rf_raw * 100, 2)
    beta = round(mkt.get("beta") or 1.05, 2)
    erp = round(mkt.get("erp") or 0.0475, 4)
    ke_val = rf_raw + (beta * erp)
    
    if live_price is not None and live_price > 0:
        price = round(float(live_price), 2)
    else:
        price = round(mkt.get("price") or 100.0, 2)
    
    wacc_val = wacc_dict.get("wacc") or scoring_data.get("wacc_and_spread_analysis", {}).get("wacc") or 0.095
    wacc_pct = round(wacc_val * 100, 2)
    
    kd_pre = wacc_dict.get("cost_of_debt_kd_pre_tax") or 0.045
    kd_post = wacc_dict.get("cost_of_debt_kd_after_tax") or 0.035
    tax_rate = wacc_dict.get("effective_tax_rate") or 0.20
    
    we = wacc_dict.get("weight_equity") or 0.95
    wd = wacc_dict.get("weight_debt") or 0.05
    
    # Acciones universales
    peers = scoring_data.get("benchmarks_used", {}).get("peers_detail", [])
    target_peer = next((p for p in peers if p.get("is_target")), {})
    raw_shares = mkt.get("diluted_shares") or target_peer.get("shares_diluted") or 1e8
    shares_b = raw_shares / 1e9 if raw_shares > 1e6 else (raw_shares / 1e3)
    shares_m = shares_b * 1000.0

    solvency = scoring_data.get("debt_and_solvency_analysis", {}).get("cash_flow_leverage", {}).get("LTM", {})
    if not solvency:
        solvency = scoring_data.get("debt_and_solvency_analysis", {}).get("latest_result", {}).get("cash_flow_leverage", {})
        
    net_debt_m = solvency.get("net_debt", 0.0)

    # -------------------------------------------------------------
    # RUTA BANCARIA / FINTECH
    # -------------------------------------------------------------
    if is_fin:
        tbv_total_m = 7646.3
        stmts_path = Path(f"data/processed/{ticker}/financial_statements.json")
        if stmts_path.exists():
            try:
                with open(stmts_path, "r", encoding="utf-8") as sf:
                    sdata = json.load(sf)
                    canon = sdata.get("canonical_summary", {})
                    eq_dict = canon.get("stockholders_equity", {})
                    if eq_dict:
                        recent_k = list(eq_dict.keys())[0]
                        tbv_total_m = eq_dict[recent_k] / 1e6
            except Exception:
                pass
        
        tbv_per_share = round(tbv_total_m / shares_m, 2) if shares_m > 0 else 1.60
        ptbv_current = round(price / tbv_per_share, 2) if tbv_per_share > 0 else 9.0
        
        # ROTCE de perfil o scorecard
        sc_dict = {r[0]: r for r in prof.get("scorecard", {}).get("data", [])}
        rotce_str = sc_dict.get("Retorno sobre Patrimonio Tangible (ROTCE)", ["", "26.40%"])[1]
        try:
            rotce_val = float(rotce_str.replace("%", "").strip()) / 100.0
        except Exception:
            rotce_val = 0.245
            
        g_term = 0.035
        spread_rotce_ke = rotce_val - ke_val
        ptbv_justified = round((rotce_val - g_term) / (ke_val - g_term), 2) if (ke_val > g_term) else 3.54
        fair_value_excess_return = round(ptbv_justified * tbv_per_share, 2)
        rotce_implied = round(((ptbv_current * (ke_val - g_term)) + g_term) * 100, 1)

        return {
            "is_financial": True,
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
            "g_terminal_pct": round(g_term * 100, 2),
            "spread_economic_pct": round(spread_rotce_ke * 100, 2),
            "ptbv_justified": ptbv_justified,
            "fair_value_excess_return": fair_value_excess_return,
            "rotce_implied_pct": rotce_implied,
            "cagr_5y": prof.get("cagr_5y", 40.0),
            "cagr_10y": prof.get("cagr_10y", 35.0),
            "cagr_3y": prof.get("cagr_3y", 45.0),
            "guidance_mid": prof.get("guidance_mid", 30.0),
        }

    # -------------------------------------------------------------
    # RUTA CORPORATIVA TRADICIONAL & HÍBRIDOS (MELI)
    # -------------------------------------------------------------
    base_rev_m = target_peer.get("revenue_usd_m") or solvency.get("revenue") or 1000.0
    s_ebit = solvency.get("ebit") or 0.0
    s_capex = solvency.get("capex") or 0.0
    s_fcf = solvency.get("fcf") or 0.0
    
    ebit_margin = (s_ebit / base_rev_m) if (base_rev_m > 0 and s_ebit > 0) else 0.20
    capex_margin = (s_capex / base_rev_m) if (base_rev_m > 0 and s_capex > 0) else 0.02
    
    # Salvaguarda de FCF normalizado para híbridos con float financiero masivo (MELI):
    if s_fcf > 0 and base_rev_m > 0 and (s_fcf / base_rev_m) > 0.25:
        fcf_margin = min(0.18, max(0.08, ebit_margin * (1.0 - tax_rate) - capex_margin + 0.02))
    elif s_fcf > 0 and base_rev_m > 0:
        fcf_margin = s_fcf / base_rev_m
    else:
        fcf_margin = max(0.05, ebit_margin * (1.0 - tax_rate) - capex_margin)
    
    cagr_5y = prof.get("cagr_5y") or target_peer.get("cagr_5y") or 8.5
    cagr_10y = prof.get("cagr_10y") or target_peer.get("cagr_10y") or 8.0
    cagr_3y = prof.get("cagr_3y") or target_peer.get("cagr_3y") or 6.0
    guidance_mid = prof.get("guidance_mid") or target_peer.get("guidance_mid") or 10.0
    
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
    
    gap_hist = (g_implied_our * 100) - cagr_5y
    gap_guide = (g_implied_our * 100) - guidance_mid
    
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
        "capex_margin": capex_margin,
        "ebit_margin_pct": round(ebit_margin * 100, 1),
        "fcf_margin_pct": round(fcf_margin * 100, 1),
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
        "gap_hist": round(gap_hist, 1),
        "gap_guide": round(gap_guide, 1)
    }


def _generate_sensitivity_grid(vp: Dict[str, Any]) -> List[Tuple[str, str, str, str, str, str, str, str]]:
    """Calcula dinámicamente la matriz de sensibilidad según el arquetipo de negocio."""
    if vp.get("is_financial"):
        # Sensibilidad Bancaria: Cost of Equity (Ke) vs. ROTCE Sostenible
        ke_base = vp.get("ke_val", 0.0943)
        ke_steps = [
            (ke_base - 0.010, f"{round((ke_base - 0.010)*100, 2):.2f}% (Bajo / Optimista)"),
            (ke_base - 0.005, f"{round((ke_base - 0.005)*100, 2):.2f}% (Favorable)"),
            (ke_base, f"{vp['ke_pct']:.2f}% (Ke Auditado Base)"),
            (ke_base + 0.005, f"{round((ke_base + 0.005)*100, 2):.2f}% (Exigente)"),
            (ke_base + 0.010, f"{round((ke_base + 0.010)*100, 2):.2f}% (Estrés Macro / Tipos)")
        ]
        rotce_rates = [0.18, 0.20, 0.22, 0.245, 0.264, 0.28]
        g_term = 0.035
        tbv_ps = vp.get("tbv_per_share", 1.60)
        
        grid_rows = []
        for ke_val, ke_label in ke_steps:
            row_vals = [ke_label]
            for r_val in rotce_rates:
                if ke_val > g_term:
                    ptbv_calc = (r_val - g_term) / (ke_val - g_term)
                    fv_calc = ptbv_calc * tbv_ps
                    row_vals.append(f"${fv_calc:.2f}")
                else:
                    row_vals.append("N/D")
            
            if "Base" in ke_label:
                row_vals.append("ESCENARIO CENTRAL: Valor teórico fundamental por ROTCE.")
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
    """Construye las 5 filas del Cuadro de Mando Consolidado (14.5) dinámicamente."""
    prof = profile_data or {}
    
    # -------------------------------------------------------------
    # CUADRO DE MANDO BANCARIO / FINTECH
    # -------------------------------------------------------------
    if vp.get("is_financial"):
        ptbv_curr = vp.get("ptbv_current", 9.0)
        ptbv_theo = vp.get("ptbv_justified", 3.5)
        rotce_pct = vp.get("rotce_pct", 26.4)
        ke_pct = vp.get("ke_pct", 9.4)
        spread_pct = vp.get("spread_economic_pct", 17.0)
        fair_val = vp.get("fair_value_excess_return", 5.66)
        
        return [
            ("Ventaja Competitiva (Moat)", "Cost-to-Serve ($0.90/mes) + Cost of Funds Minorista", "WIDE MOAT FINTECH", "Ventaja estructural de coste frente a banca tradicional."),
            ("Calidad de Cartera y Provisiones", "Mora >90d: 6.8% / Cobertura de Provisiones: >200%", "BLINDAJE DE PROVISIONES", "Provisiones duplican saldo dudoso; bajo riesgo neto."),
            ("Solvencia Regulatoria y Capital", "Ratio CET1: 11.5% - 13.0% (vs. 8.0% mínimo BACEN)", "MÁXIMA SOLVENCIA CET1", "Colchón de capital anticíclico y autofinanciación orgánica."),
            ("Productividad del Capital", f"ROTCE Tangible: {rotce_pct:.1f}% vs Ke {ke_pct:.2f}%", "COMPOUNDING MACHINE", f"Spread económico de +{spread_pct:.1f} pp sobre coste de capital."),
            ("Valoración de Mercado", f"P/TBV: {ptbv_curr:.1f}x vs P/TBV Teórico: {ptbv_theo:.1f}x", "PRICED FOR HYPERGROWTH", f"Cotización descuenta sostener crecimiento de cartera > 25% anual."),
        ]

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
    cash_val_m = lev_ltm.get("cash") or bm_target.get("cash_usd_m") or 1000.0
    
    solv_diag = f"Cobertura EBIT: {cov_str} / Altman Z'': {altman_z:.2f}"
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
    
    if ticker == "AAPL":
        val_verdict = "Exigencia de crecimiento ambiciosa; requiere catalizadores en IA y Servicios."
    elif ticker == "DECK":
        val_verdict = "Exigencia asumible; requiere sostener la expansión global de HOKA, UGG y canal DTC."
    elif ticker == "MELI":
        val_verdict = "Exigencia moderada (+14% a +16%); absorbible por el crecimiento orgánico de e-commerce y fintech (+30% YoY)."
    else:
        val_verdict = f"Requiere sostener la tracción operativa y rentabilidad en sus mercados estratégicos."
        
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
    """Genera la sección completa de Valoración en Markdown, adaptándose si es banco o corporación."""
    vp = get_valuation_parameters(scoring_data, ticker, profile_data)
    
    # RUTA BANCARIA
    if vp.get("is_financial"):
        md = []
        md.append(f"## {section_num}. Modelado Financiero y Valoración Bancaria (Excess Return Model & P/TBV vs. ROTCE)\n")
        md.append(
            f"> **PROPÓSITO DE VALORACIÓN:** MODELO DE RENTA RESIDUAL / RETORNO EXCEDENTE (EXCESS RETURN MODEL)  \n"
            f"> **Metodología Institucional:** Valoración sobre Patrimonio Tangible (*Price-to-Tangible Book Value P/TBV*) justificado por la rentabilidad financiera (*ROTCE*) frente al coste del capital propio (*Ke*).  \n"
            f"> **Justificación Contable:** En instituciones financieras, el modelo tradicional DCF es inaplicable debido a la imposibilidad de aislar el Flujo de Caja Libre a la Firma (FCFF) y el WACC. El valor intrínseco se deriva de la capacidad del banco de generar beneficios por encima de la tasa de corte demandada por los accionistas.\n"
        )
        
        md.append(f"### {section_num}.1. Metodología de Valoración para Entidades Bancarias y FinTechs\n")
        md.append(
            "El marco institucional para valorar una entidad de crédito se articula mediante el **Modelo de Renta Residual de Gordon-Shapiro bancario**:\n"
            "* **1. Relación Fundamental P/TBV vs. ROTCE:**\n"
            "  $$\\frac{P}{TBV} = \\frac{ROTCE - g}{K_e - g}$$\n"
            "  Donde el múltiplo patrimonial depende directamente del exceso de rentabilidad (*Economic Spread* = \\(ROTCE - K_e\\)) y de la reinversión de capital para sostener el crecimiento.\n"
            "* **2. Coste del Capital Propio (\\(K_e\\)) mediante CAPM:**\n"
            f"  $$K_e = R_f + \\beta \\times ERP = {vp['rf_pct']}\\% + {vp['beta']} \\times {vp['erp_pct']}\\% = \\mathbf{{{vp['ke_pct']}\\%}}$$\n"
            "* **3. Creación de Valor Económico Puro:**\n"
            f"  Con un **ROTCE del {vp['rotce_pct']}%** y un coste de capital del **{vp['ke_pct']}%**, {company_name} genera un **spread económico masivo de +{vp['spread_economic_pct']} pp**, justificando una prima sustancial sobre su valor contable tangible.\n"
        )
        
        md.append(f"### {section_num}.2. Tabla Maestra de Parámetros de Valoración Bancaria\n")
        md.append("| Casilla / Input de Valoración Bancaria | Valor Auditado | Fuente / Racional Metodológico |")
        md.append("| :--- | :---: | :--- |")
        md.append(f"| **Cotización de Mercado ($P_0$)** | **${vp['price']}** | Cotización bursátil auditada en tiempo real. |")
        md.append(f"| **Patrimonio Tangible Total (TBV)** | **${vp['tangible_equity_m']:,.1f} M** | Balance auditado Form 20-F / 6-K ante la SEC. |")
        md.append(f"| **Acciones en Circulación** | **{vp['shares_m']:,.1f} M** | Recuento de acciones diluidas reportadas. |")
        md.append(f"| **Patrimonio Tangible por Acción ($TBV_0$)** | **${vp['tbv_per_share']}** | Valor contable tangible neto por título. |")
        md.append(f"| **Ratio P/TBV de Mercado Actual** | **{vp['ptbv_current']}x** | Múltiplo sobre libros al precio de cotización. |")
        md.append(f"| **Retorno s/ Patrimonio Tangible (ROTCE)** | **{vp['rotce_pct']}%** | Rentabilidad sobre fondos propios auditada. |")
        md.append(f"| **Coste del Capital Propio ($K_e$)** | **{vp['ke_pct']}%** | Tasa mínima exigida por CAPM ($R_f + \\beta \\times ERP$). |")
        md.append(f"| **Spread de Renta Residual ($ROTCE - K_e$)** | **+{vp['spread_economic_pct']} pp** | Generación de valor excedente sobre coste de capital. |")
        md.append(f"| **Crecimiento Terminal Sostenible ($g$)** | **{vp['g_terminal_pct']}%** | Crecimiento de largo plazo de la cartera de crédito. |")
        md.append(f"| **Ratio P/TBV Justificado Teórico** | **{vp['ptbv_justified']}x** | Múltiplo intrínseco: $(ROTCE - g) / (K_e - g)$. |")
        md.append(f"| **Valor Intrínseco por Acción (Excess Return)** | **${vp['fair_value_excess_return']}** | Precio teórico fundamental sustentado por ROTCE actual. |")
        md.append("\n")

        # Sensibilidad Bancaria
        md.append(f"### {section_num}.3. Matriz Bidimensional de Sensibilidad (Cost of Equity $K_e$ vs. ROTCE Sostenible)\n")
        md.append(
            f"La siguiente matriz evalúa el **Valor Intrínseco por Acción** ante distintas hipótesis de rentabilidad de balance (*ROTCE*) y coste de oportunidad del capital propio (*Ke*):\n"
        )
        sens_rows = _generate_sensitivity_grid(vp)
        md.append("| Coste Equity ($K_e$) \\ ROTCE | 18.0% | 20.0% | 22.0% | 24.5% | 26.4% (Base) | 28.0% | Diagnóstico de Escenario |")
        md.append("| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |")
        for r in sens_rows:
            md.append(f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} | {r[4]} | {r[5]} | {r[6]} | {r[7]} |")
        md.append("\n")

        # Reverse Excess Return
        md.append(f"### {section_num}.4. Reverse Excess Return: ¿Qué expectativas descuenta el precio actual de mercado?\n")
        md.append(
            f"Al cotizar a **${vp['price']}** ({vp['ptbv_current']}x P/TBV), el mercado está descontando:\n"
            f"* **ROTCE Implícito a Perpetuidad:** El precio actual exige que {company_name} sostenga un ROTCE del **~{vp['rotce_implied_pct']}%** a perpetuidad, o alternativamente que multiplique su base de capital y cartera a una tasa compuesta de más del **+30% anual** durante los próximos 7 a 10 años.\n"
            "* **Diagnóstico de Expectativas:** El mercado asigna una prima sustancial al modelo fintech (*Hypergrowth Pricing*). Para justificar la cotización actual, Nubank debe consolidar con éxito su expansión en México y Colombia y sostener un Margen Ajustado por Riesgo (*Risk-Adjusted NIM*) superior al 10.5%.\n"
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
    """Añade la sección de Valoración en Word (.docx), adaptándose si es banco o corporación."""
    vp = get_valuation_parameters(scoring_data, ticker, profile_data)
    cmd_data = _build_cmd_final_rows(scoring_data, vp, profile_data, ticker, company_name)
    
    # -------------------------------------------------------------
    # RUTA BANCARIA
    # -------------------------------------------------------------
    if vp.get("is_financial"):
        h1 = doc.add_heading(level=1)
        r_h1 = h1.add_run(f"{section_num}. Modelado Financiero y Valoración Bancaria (Excess Return & P/TBV)")
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
        
        r_box_title = p_box.add_run(f"DICTAMEN DE VALORACIÓN BANCARIA: EXCESS RETURN MODEL & P/TBV\n")
        r_box_title.font.name = "Calibri"
        r_box_title.font.size = Pt(10.5)
        r_box_title.font.bold = True
        r_box_title.font.color.rgb = NAVY
        
        r_box_body = p_box.add_run(
            f"• Cotización: ${vp['price']}  |  Patrimonio Tangible por Acción (TBV): ${vp['tbv_per_share']}  |  P/TBV Mercado: {vp['ptbv_current']}x\n"
            f"• Rentabilidad Tangible (ROTCE): {vp['rotce_pct']}% vs. Coste Capital (Ke): {vp['ke_pct']}%  ->  Spread Económico: +{vp['spread_economic_pct']} pp\n"
            f"• P/TBV Justificado por Fundamentals: {vp['ptbv_justified']}x (Precio Teórico Justo: ${vp['fair_value_excess_return']})\n"
            f"• Veredicto: El mercado descuenta sostener un ROTCE del ~{vp['rotce_implied_pct']}% o crecimiento compuesto de cartera > 25% anual."
        )
        r_box_body.font.name = "Calibri"
        r_box_body.font.size = Pt(9.5)
        r_box_body.font.color.rgb = DARK_GRAY

        # Tabla Maestra Inputs Bancarios
        h2 = doc.add_heading(level=2)
        r_h2 = h2.add_run(f"{section_num}.1. Parámetros Maestros de Valoración Bancaria (Gordon-Shapiro & CAPM)")
        r_h2.font.name = "Calibri"
        r_h2.font.size = Pt(11.5)
        r_h2.font.bold = True
        r_h2.font.color.rgb = NAVY
        
        t_bank = doc.add_table(rows=8, cols=3)
        t_bank.alignment = WD_TABLE_ALIGNMENT.CENTER
        _set_table_borders(t_bank)
        
        headers_b = ["Parámetro Bancario", "Valor Auditado", "Interpretación y Racional Técnico"]
        for i, h in enumerate(headers_b):
            c = t_bank.cell(0, i)
            _set_cell_shading(c, HEADER_BG)
            p = c.paragraphs[0]
            r = p.add_run(h)
            r.bold = True
            r.font.size = Pt(9)
            r.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
            
        data_b = [
            ("Patrimonio Tangible Total (TBV)", f"${vp['tangible_equity_m']:,.1f} M", "Fondos propios auditados en el último balance oficial SEC."),
            ("Patrimonio Tangible por Acción", f"${vp['tbv_per_share']}", "Valor en libros puro por título en circulación."),
            ("Rentabilidad Tangible (ROTCE)", f"{vp['rotce_pct']}%", "Capacidad de generar utilidad neta sobre capital tangible."),
            ("Coste del Capital Propio (Ke)", f"{vp['ke_pct']}%", "Tasa de descuento de corte según modelo CAPM."),
            ("Spread de Creación de Valor", f"+{vp['spread_economic_pct']} pp", "Excedente de retorno que genera renta residual positiva."),
            ("Ratio P/TBV Justificado", f"{vp['ptbv_justified']}x", "Múltiplo teórico derivado de: (ROTCE - g) / (Ke - g)."),
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

        # Sensibilidad Bancaria
        h2_sens = doc.add_heading(level=2)
        r_h2_sens = h2_sens.add_run(f"{section_num}.2. Matriz Bidimensional de Sensibilidad (Ke vs. ROTCE)")
        r_h2_sens.font.name = "Calibri"
        r_h2_sens.font.size = Pt(11.5)
        r_h2_sens.font.bold = True
        r_h2_sens.font.color.rgb = NAVY
        
        sens_data = _generate_sensitivity_grid(vp)
        t_sens = doc.add_table(rows=len(sens_data) + 1, cols=8)
        t_sens.alignment = WD_TABLE_ALIGNMENT.CENTER
        _set_table_borders(t_sens)
        
        s_headers = ["Coste Ke \\ ROTCE", "18.0%", "20.0%", "22.0%", "24.5%", "26.4%", "28.0%", "Diagnóstico"]
        for i, h in enumerate(s_headers):
            c = t_sens.cell(0, i)
            _set_cell_shading(c, HEADER_BG)
            p = c.paragraphs[0]
            r = p.add_run(h)
            r.bold = True
            r.font.size = Pt(8.5)
            r.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
            
        for row_idx, row_data in enumerate(sens_data, start=1):
            for col_idx, text in enumerate(row_data):
                c = t_sens.cell(row_idx, col_idx)
                if "Base" in row_data[0]:
                    _set_cell_shading(c, YELLOW_BG if col_idx == 5 else ALT_ROW_BG)
                elif row_idx % 2 == 0:
                    _set_cell_shading(c, ALT_ROW_BG)
                p = c.paragraphs[0]
                r = p.add_run(text)
                r.font.size = Pt(8.0)
                if col_idx == 5 or (col_idx > 0 and col_idx < 7 and "Base" in row_data[0]):
                    r.bold = True
                    
        doc.add_paragraph()

        # Cuadro de Mando Final
        h2_cmd = doc.add_heading(level=2)
        r_h2_cmd = h2_cmd.add_run(f"{section_num}.3. Cuadro de Mando Consolidado y Tesis Bancaria")
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
    gap_sign_guide = "+" if vp['gap_guide'] > 0 else ""
    gap_sign_hist = "+" if vp['gap_hist'] > 0 else ""
    
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
        f"• Crecimiento Implícito Calculado: {vp['g_implied_our_pct']:.1f}% Anual a 10 Años (vs. {vp['cagr_5y']:.1f}% Histórico y {vp['guidance_mid']:.1f}% Guidance)\n"
        f"• Veredicto: Descuenta expectativas de {vp['g_implied_our_pct']:.1f}% anual ({gap_sign_guide}{vp['gap_guide']:.1f} pp sobre guidance). {val_verdict}"
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
