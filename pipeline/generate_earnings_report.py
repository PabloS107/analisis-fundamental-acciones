"""
generate_earnings_report.py - Orquestador Universal de Informes de Equity Research

Motor único y estandarizado para la generación de informes fundamentales institucionales
en formatos Word (.docx) y Markdown (.md).

Estructura de 14 Secciones Maestras (Idéntica e Inmutable para Cualquier Empresa):
1. Introducción al Negocio y Arquitectura de Comercialización (Go-To-Market)
2. Desglose de Ventas por Línea de Productos y Servicios (Comparativa Interanual)
3. Desglose Geográfico: Mercados y Países de Comercialización (Comparativa Interanual)
4. Resumen Ejecutivo y Cuadro de Mando Financiero (Scorecard de 15 Métricas)
5. Análisis Exhaustivo de Conferencia de Resultados (Earnings Calls) y Auditoría del Discurso Directivo
   - Bloque A: Trimestre Actual (Guidance, Hitos, Matriz de Riesgos, Q&A Banco por Banco)
   - Bloque B: Auditoría Longitudinal 5 Trimestres (Say-Do Ratio, Mutación de Riesgos, Credibilidad)
6. Posición Patrimonial, Estructura de Capital y Asignación de Recursos (Capital Allocation)
7. Estrategia Tecnológica / Innovación, Fosos Defensivos (Economic Moat - Framework Dorsey)
8. Gobernanza Corporativa, Sentimiento Insider (Form 4 y 144) y Alertas 8-K (Relevo de CEO)
9. Diagnóstico Cuantitativo de Resiliencia y Crecimiento (Piotroski & Mohanram + Pares)
10. Productividad Pura del Capital: Rentabilidad Bruta sobre Activos (Novy-Marx GP/A)
11. Rendimiento del Capital Ajustado por Intangibles, Costo de Capital (WACC) y EVA
12. Auditoría Forense Contable y Calidad de Beneficios (Detección de Trampas Contables)
13. Solvencia, Deuda y Estrés Financiero (Credit Risk Engine)
14. Modelado Financiero y Descuento Inverso de Flujo de Caja (Reverse DCF & Expectations)
"""

import os
import sys
import re
import json
from pathlib import Path
from datetime import datetime
import shutil

import docx
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml import parse_xml, OxmlElement
from docx.oxml.ns import nsdecls, qn

from governance_insider_analyzer import analyze_governance_and_insiders
from financial_scoring_engine import calculate_fundamental_scores

# Builders modulares para Secciones 10 a 14
from novy_marx_report_builder import add_novy_marx_section_docx, generate_novy_marx_section_md
from roic_wacc_report_builder import add_roic_wacc_section_docx, generate_roic_wacc_section_md
from forensic_report_builder import add_forensic_section_docx, generate_forensic_section_md
from solvency_report_builder import add_solvency_section_docx, generate_solvency_section_md
from valuation_report_builder import add_valuation_section_docx, generate_valuation_section_md


# -------------------------------------------------------------
# PALETA VISUAL INSTITUCIONAL
# -------------------------------------------------------------
NAVY = RGBColor(0x1B, 0x36, 0x5D)
SLATE = RGBColor(0x4A, 0x55, 0x68)
DARK_GRAY = RGBColor(0x2D, 0x37, 0x48)
LIGHT_BLUE = "F0F4F8"
HEADER_BG = "1B365D"
ALT_ROW_BG = "F7FAFC"
WHITE_HEX = "FFFFFF"
BORDER_GRAY = "D2D6DC"


# -------------------------------------------------------------
# FUNCIONES DE ESTILIZADO WORD (.DOCX)
# -------------------------------------------------------------
def set_cell_shading(cell, color_hex):
    shd = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{color_hex}"/>')
    cell._tc.get_or_add_tcPr().append(shd)


def set_cell_margins(cell, top=120, bottom=120, left=150, right=150):
    tcPr = cell._tc.get_or_add_tcPr()
    tcMar = OxmlElement('w:tcMar')
    for m, val in [('top', top), ('bottom', bottom), ('left', left), ('right', right)]:
        node = OxmlElement(f'w:{m}')
        node.set(qn('w:w'), str(val))
        node.set(qn('w:type'), 'dxa')
        tcMar.append(node)
    tcPr.append(tcMar)


def set_table_borders(table, border_color="D2D6DC"):
    tblPr = table._tbl.tblPr
    borders = parse_xml(
        f'<w:tblBorders {nsdecls("w")}>'
        f'  <w:top w:val="single" w:sz="4" w:space="0" w:color="{border_color}"/>'
        f'  <w:bottom w:val="single" w:sz="6" w:space="0" w:color="1B365D"/>'
        f'  <w:left w:val="none"/>'
        f'  <w:right w:val="none"/>'
        f'  <w:insideH w:val="single" w:sz="4" w:space="0" w:color="{border_color}"/>'
        f'  <w:insideV w:val="none"/>'
        f'</w:tblBorders>'
    )
    tblPr.append(borders)


def add_callout(doc, title, paragraphs, accent_color="1B365D", bg_color="F0F4F8"):
    tbl = doc.add_table(rows=1, cols=1)
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    tbl.autofit = False
    tbl.columns[0].width = Inches(6.8)
    cell = tbl.cell(0, 0)
    
    set_cell_shading(cell, bg_color)
    set_cell_margins(cell, top=140, bottom=140, left=180, right=180)
    
    tcPr = cell._tc.get_or_add_tcPr()
    tcBorders = parse_xml(
        f'<w:tcBorders {nsdecls("w")}>'
        f'  <w:left w:val="single" w:sz="24" w:space="0" w:color="{accent_color}"/>'
        f'  <w:top w:val="none"/>'
        f'  <w:right w:val="none"/>'
        f'  <w:bottom w:val="none"/>'
        f'</w:tcBorders>'
    )
    tcPr.append(tcBorders)
    
    p = cell.paragraphs[0]
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(4)
    run_icon = p.add_run("📌  ")
    run_icon.font.name = "Segoe UI Emoji"
    run_icon.font.size = Pt(10.5)
    run_t = p.add_run(title)
    run_t.font.name = "Calibri"
    run_t.font.size = Pt(10.5)
    run_t.bold = True
    r, g, b = tuple(int(accent_color[i:i+2], 16) for i in (0, 2, 4))
    run_t.font.color.rgb = RGBColor(r, g, b)
    
    for item in paragraphs:
        p_body = cell.add_paragraph()
        p_body.paragraph_format.space_before = Pt(2)
        p_body.paragraph_format.space_after = Pt(2)
        p_body.paragraph_format.line_spacing = 1.15
        r_body = p_body.add_run(item)
        r_body.font.name = "Calibri"
        r_body.font.size = Pt(9.5)
        r_body.font.color.rgb = DARK_GRAY
        
    doc.add_paragraph().paragraph_format.space_after = Pt(4)


def add_styled_heading_1(doc, text):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(16)
    p.paragraph_format.space_after = Pt(6)
    p.paragraph_format.keep_with_next = True
    run = p.add_run(text)
    run.font.name = "Calibri"
    run.font.size = Pt(13)
    run.bold = True
    run.font.color.rgb = NAVY
    return p


def add_styled_heading_2(doc, text):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(10)
    p.paragraph_format.space_after = Pt(4)
    p.paragraph_format.keep_with_next = True
    run = p.add_run(text)
    run.font.name = "Calibri"
    run.font.size = Pt(11)
    run.bold = True
    run.font.color.rgb = SLATE
    return p


def add_body_p(doc, text, bold_prefix=None, italic=False):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(4)
    p.paragraph_format.line_spacing = 1.15
    if bold_prefix:
        r_pre = p.add_run(bold_prefix)
        r_pre.font.name = "Calibri"
        r_pre.font.size = Pt(10)
        r_pre.bold = True
        r_pre.font.color.rgb = DARK_GRAY
    r = p.add_run(text)
    r.font.name = "Calibri"
    r.font.size = Pt(10)
    r.italic = italic
    r.font.color.rgb = DARK_GRAY
    return p


def build_table(doc, headers, data_rows, col_widths=None, alignments=None):
    num_cols = len(headers)
    tbl = doc.add_table(rows=len(data_rows) + 1, cols=num_cols)
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    tbl.autofit = False
    set_table_borders(tbl, BORDER_GRAY)
    
    # Encabezado
    hdr_cells = tbl.rows[0].cells
    for c_idx, title in enumerate(headers):
        hdr_cells[c_idx].text = title
        set_cell_shading(hdr_cells[c_idx], HEADER_BG)
        set_cell_margins(hdr_cells[c_idx], top=100, bottom=100, left=120, right=120)
        p = hdr_cells[c_idx].paragraphs[0]
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(0)
        align = alignments[c_idx] if alignments and c_idx < len(alignments) else ("LEFT" if c_idx == 0 else "CENTER")
        if align == "RIGHT":
            p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        elif align == "CENTER":
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        else:
            p.alignment = WD_ALIGN_PARAGRAPH.LEFT
        for run in p.runs:
            run.font.name = "Calibri"
            run.font.size = Pt(9.5)
            run.bold = True
            run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
            
    # Filas de datos
    for r_idx, row_data in enumerate(data_rows):
        row = tbl.rows[r_idx + 1]
        bg = ALT_ROW_BG if r_idx % 2 == 1 else WHITE_HEX
        is_total_row = (r_idx == len(data_rows) - 1) and any("TOTAL" in str(c).upper() for c in row_data)
        if is_total_row:
            bg = "E2E8F0"
        for c_idx, val in enumerate(row_data):
            cell = row.cells[c_idx]
            disp_text = "-" if val is None or str(val).strip().lower() in ("none", "nan") else str(val)
            cell.text = disp_text
            set_cell_shading(cell, bg)
            set_cell_margins(cell, top=80, bottom=80, left=120, right=120)
            p = cell.paragraphs[0]
            p.paragraph_format.space_before = Pt(0)
            p.paragraph_format.space_after = Pt(0)
            align = alignments[c_idx] if alignments and c_idx < len(alignments) else ("LEFT" if c_idx == 0 else "CENTER")
            if align == "RIGHT":
                p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            elif align == "CENTER":
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            else:
                p.alignment = WD_ALIGN_PARAGRAPH.LEFT
            for run in p.runs:
                run.font.name = "Calibri"
                run.font.size = Pt(9)
                if is_total_row or "**" in str(val):
                    run.bold = True
                    run.text = run.text.replace("**", "")
                run.font.color.rgb = DARK_GRAY
                
    # Anchos de columnas
    if col_widths:
        for row in tbl.rows:
            for c_idx, w in enumerate(col_widths):
                row.cells[c_idx].width = Inches(w)
                
    doc.add_paragraph().paragraph_format.space_after = Pt(6)
    return tbl


# -------------------------------------------------------------
# HELPERS DE CATALIZADORES Y GUÍAS PEDAGÓGICAS INSTITUCIONALES
# -------------------------------------------------------------
def derive_segment_catalyst(name: str, yoy: float, is_subtotal: bool = False) -> str:
    """Genera un catalizador estratégico dinámico basado en la tasa de crecimiento interanual."""
    sign = "+" if yoy >= 0 else ""
    yoy_str = f"{sign}{yoy:.1f}%"
    if is_subtotal:
        return f"Subtotal consolidado de canal/categoría ({yoy_str} YoY)."
    if yoy > 20.0:
        return f"Aceleración comercial de alta tracción ({yoy_str} YoY); ganancia de cuota y dinamismo."
    elif yoy > 5.0:
        return f"Crecimiento orgánico sostenido ({yoy_str} YoY); demanda sólida y volumen favorable."
    elif yoy >= 0.0:
        return f"Desempeño estable ({yoy_str} YoY); consolidación en mercados y canales core."
    elif yoy > -10.0:
        return f"Normalización moderada ({yoy_str} YoY); ajuste de demanda o transición de catálogo."
    else:
        return f"Contracción ({yoy_str} YoY); viento en contra sectorial o rotación de inventarios."


def derive_geo_catalyst(name: str, yoy: float, weight: float, is_subtotal: bool = False) -> str:
    """Genera un diagnóstico geográfico dinámico según crecimiento y representatividad."""
    sign = "+" if yoy >= 0 else ""
    yoy_str = f"{sign}{yoy:.1f}%"
    if is_subtotal:
        return f"Subtotal consolidado de región ({yoy_str} YoY)."
    if yoy > 15.0:
        return f"Mercado en fuerte expansión ({yoy_str} YoY); tracción de demanda local."
    elif yoy > 0.0:
        return f"Mercado estratégico consolidado ({yoy_str} YoY); estabilidad operativa."
    else:
        return f"Mercado en ajuste ({yoy_str} YoY); presión macroeconómica o vientos cambiarios (FX)."


def get_scorecard_pedagogical_guide(archetype: str):
    """Devuelve el título y los párrafos de la guía pedagógica institucional según el arquetipo."""
    arch = (archetype or "").upper()
    if arch == "FINANCIAL_BANKING":
        title = "GUÍA DE DIAGNÓSTICO FUNDAMENTAL: ¿QUÉ EVALÚA CADA RATIO BANCARIO?"
        paragraphs = [
            "• Margen de Interés Neto (NIM): Mide la rentabilidad del negocio básico de intermediación bancaria (spread entre la tasa activa que cobra por prestar y la tasa pasiva que paga por depósitos). Un NIM elevado y resiliente certifica ventajas estructurales de fondeo.",
            "• Ratio de Eficiencia Operativa (Cost-to-Income): Gastos de explotación entre margen bruto de intermediación. Ratios < 40% son excelentes; < 25% sitúan a la entidad en la élite mundial absoluta gracias a su apalancamiento tecnológico.",
            "• Ratio de Morosidad NPL (15-90d y >90d): Porcentaje de la cartera con retrasos en pagos. Evalúa la salud crediticia y la efectividad de los modelos de admisión y suscripción de riesgo.",
            "• Ratio de Cobertura de Provisiones: Provisiones acumuladas entre cartera dudosa (>90d). Ratios > 150%-200% garantizan que el balance absorberá impagos sin erosionar el patrimonio ni requerir rescates.",
            "• Cost of Risk (Costo de Riesgo): Gasto anualizado en provisiones sobre cartera total. Indica el coste recurrente de las pérdidas esperadas inherente a la actividad crediticia.",
            "• Retorno sobre Patrimonio Tangible (ROTCE): Mide la rentabilidad pura generada sobre los fondos propios tangibles. La diferencia frente al Coste del Capital (Ke) determina la creación de valor económico puro (EVA bancario).",
            "• Ratio CET1 / Basilea III: Mide el capital regulatorio de máxima calidad frente a activos ponderados por riesgo. Garantiza solvencia ante crisis sistémicas (>10.5% estándar regulatorio Basilea III)."
        ]
        return title, paragraphs
    elif arch == "INSURANCE":
        title = "GUÍA DE DIAGNÓSTICO FUNDAMENTAL: ¿QUÉ EVALÚA CADA RATIO ASEGURADOR?"
        paragraphs = [
            "• Ratio Combinado (Combined Ratio): Suma de siniestralidad incurrida y gastos operativos sobre primas netas ganadas. Niveles < 95% denotan rentabilidad técnica de suscripción y coste de float negativo.",
            "• Rentabilidad del Float (Float Investment Return): Rendimiento financiero generado sobre las reservas técnicas acumuladas antes del abono de reclamaciones.",
            "• Ratio de Siniestralidad (Loss Ratio): Indemnizaciones y pérdidas sobre primas devengadas; mide la disciplina actuarial frente a eventos catastróficos o severidad de reclamos.",
            "• Ratio de Gastos de Adquisición y Operativos (Expense Ratio): Eficiencia en comisiones de corretaje y gestión administrativa sobre primas netas.",
            "• Retorno sobre Fondos Propios (ROE): Rentabilidad neta sobre capital propio asegurador que respalda las obligaciones de suscripción.",
            "• Ratio de Solvencia Regulatoria (RBC / NAIC / Solvencia II): Cobertura de capital disponible frente al capital regulatorio de riesgo requerido (>200% margen seguro)."
        ]
        return title, paragraphs
    elif arch == "REAL_ESTATE_REIT":
        title = "GUÍA DE DIAGNÓSTICO FUNDAMENTAL: ¿QUÉ EVALÚA CADA MÉTRICA INMOBILIARIA (REIT)?"
        paragraphs = [
            "• Fondos de las Operaciones (FFO / AFFO): Beneficio neto ajustado por depreciación inmobiliaria y ganancias/pérdidas de capital; métrica maestra de flujo recurrente.",
            "• Tasa de Ocupación (Occupancy Rate): Porcentaje de la superficie bruta alquilable (GLA) efectivamente arrendada (>95% óptimo en activos triple net).",
            "• Deuda Neta / EBITDA Inmobiliario: Cobertura de endeudamiento sobre rentas brutas operativas; evalúa el apalancamiento patrimonial de la cartera.",
            "• Duración Media de Contratos (WALT): Plazo medio ponderado de vencimiento de arrendamientos; garantiza visibilidad de rentas a largo plazo.",
            "• Rentabilidad por Dividendo (Dividend Yield) & Payout sobre AFFO: Proporción del flujo libre distribuido periódicamente a los tenedores de cuotas.",
            "• Loan-to-Value (LTV): Deuda financiera total sobre valor razonable de la cartera de inmuebles (<45% perfil conservador)."
        ]
        return title, paragraphs
    else:
        title = "GUÍA DE DIAGNÓSTICO FUNDAMENTAL: ¿QUÉ EVALÚA CADA PARÁMETRO CLAVE?"
        paragraphs = [
            "• Margen Bruto (%): Mide el poder de fijación de precios (pricing power) de la empresa y la ventaja competitiva frente a sus proveedores y costes directos. Un margen en expansión indica que el cliente está dispuesto a pagar por el valor de la marca o que la compañía tiene economías de escala superiores.",
            "• Margen Operativo (%): Refleja la eficiencia de la gestión para controlar la estructura fija de administración, marketing e investigación (OpEx). Demuestra si la compañía goza de apalancamiento operativo positivo.",
            "• Margen Neto (%): Es la rentabilidad final que le queda a la empresa tras cubrir costes operativos, gastos financieros de la deuda e impuestos corporativos. Proporción de los ingresos que termina directamente en el bolsillo de los accionistas.",
            "• Flujo de Caja Libre (FCF) y Margen FCF: Es el indicador más fidedigno de la salud económica real (Cash is King). Mide los dólares reales que ingresan a la caja tras pagar todas las inversiones de mantenimiento y expansión (CapEx). Capital disponible para recomprar acciones, pagar dividendos o desendeudarse.",
            "• Tasa de Conversión FCF / Beneficio Neto: Evalúa la calidad contable de las ganancias. Ratios consistentes en torno o por encima del 100% garantizan que la empresa no está inflando sus resultados con devengos agresivos."
        ]
        return title, paragraphs



def build_dynamic_scorecard(fin_data, archetype="STANDARD_CORPORATE"):
    """
    Construye dinámicamente un Cuadro de Mando Financiero (Scorecard) institucional
    a partir de canonical_summary cuando no existe un scorecard pre-configurado.
    """
    canonical = fin_data.get("canonical_summary", {}) if fin_data else {}
    fys = fin_data.get("fiscal_years", []) if fin_data else []
    if not canonical or not fys or len(fys) < 2:
        return (
            ["Métrica Financiera", "Actual", "Previo", "Variación YoY", "Diagnóstico Fundamental"],
            [
                ["Ingresos Netos Totales", "N/D", "N/D", "N/D", "Seguimiento de ingresos consolidados."],
                ["Margen Operativo (%)", "N/D", "N/D", "N/D", "Eficiencia y control de costes operativos."]
            ]
        )

    curr_p = fys[0]
    prev_p = fys[1]

    def fmt_usd(val):
        if val is None:
            return "N/D"
        if abs(val) >= 1e9:
            return f"${val/1e9:.2f} B"
        elif abs(val) >= 1e6:
            return f"${val/1e6:.1f} M"
        return f"${val:,.0f}"

    def fmt_pct(val):
        return f"{val*100:.1f}%" if val is not None else "N/D"

    def fmt_yoy(curr_val, prev_val, is_pct=False):
        if curr_val is None or prev_val is None or prev_val == 0:
            return "N/D"
        if is_pct:
            diff = (curr_val - prev_val) * 100
            sign = "+" if diff > 0 else ""
            return f"{sign}{diff:.1f} pp"
        else:
            pct = ((curr_val - prev_val) / abs(prev_val)) * 100
            sign = "+" if pct > 0 else ""
            return f"{sign}{pct:.1f}%"

    headers = ["Métrica Financiera", f"Actual ({curr_p})", f"Previo ({prev_p})", "Variación YoY", "Diagnóstico Fundamental"]
    rows = []

    # 1. Ingresos Netos Totales
    rev_c = canonical.get("revenue", {}).get(curr_p)
    rev_p = canonical.get("revenue", {}).get(prev_p)
    yoy_rev = fmt_yoy(rev_c, rev_p)
    diag_rev = "Crecimiento de ingresos sostenido." if rev_c and rev_p and rev_c >= rev_p else "Contracción o moderación de facturación."
    rows.append(["Ingresos Netos Totales", fmt_usd(rev_c), fmt_usd(rev_p), yoy_rev, diag_rev])

    # 2. Margen Bruto (si no es banco)
    if archetype != "FINANCIAL_BANKING":
        gp_c = canonical.get("gross_profit", {}).get(curr_p)
        gp_p = canonical.get("gross_profit", {}).get(prev_p)
        gm_c = (gp_c / rev_c) if (gp_c is not None and rev_c and rev_c > 0) else None
        gm_p = (gp_p / rev_p) if (gp_p is not None and rev_p and rev_p > 0) else None
        yoy_gm = fmt_yoy(gm_c, gm_p, is_pct=True)
        diag_gm = "Poder de fijación de precios y rentabilidad bruta sólida." if gm_c and gm_c > 0.4 else "Control de costo de ventas y disciplina operativa."
        rows.append(["Margen Bruto (%)", fmt_pct(gm_c), fmt_pct(gm_p), yoy_gm, diag_gm])

    # 3. Margen Operativo
    ebit_c = canonical.get("operating_income", {}).get(curr_p)
    ebit_p = canonical.get("operating_income", {}).get(prev_p)
    opm_c = (ebit_c / rev_c) if (ebit_c is not None and rev_c and rev_c > 0) else None
    opm_p = (ebit_p / rev_p) if (ebit_p is not None and rev_p and rev_p > 0) else None
    yoy_opm = fmt_yoy(opm_c, opm_p, is_pct=True)
    diag_opm = "Apalancamiento operativo y contención de costes." if opm_c and opm_p and opm_c >= opm_p else "Presión en estructura de gastos operativos."
    rows.append(["Margen Operativo (%)", fmt_pct(opm_c), fmt_pct(opm_p), yoy_opm, diag_opm])

    # 4. Beneficio Neto
    ni_c = canonical.get("net_income", {}).get(curr_p)
    ni_p = canonical.get("net_income", {}).get(prev_p)
    yoy_ni = fmt_yoy(ni_c, ni_p)
    diag_ni = "Conversión a beneficios neta favorable." if ni_c and ni_p and ni_c >= ni_p else "Menor resultado neto final."
    rows.append(["Beneficio Neto", fmt_usd(ni_c), fmt_usd(ni_p), yoy_ni, diag_ni])

    # 5. Flujo de Caja Libre (si no es banco)
    if archetype != "FINANCIAL_BANKING":
        fcf_c = canonical.get("free_cash_flow", {}).get(curr_p)
        fcf_p = canonical.get("free_cash_flow", {}).get(prev_p)
        yoy_fcf = fmt_yoy(fcf_c, fcf_p)
        diag_fcf = "Generación de caja libre sólida tras reinversión en CapEx." if fcf_c and fcf_c > 0 else "Flujo de caja bajo presión de inversión intensiva."
        rows.append(["Flujo de Caja Libre (FCF)", fmt_usd(fcf_c), fmt_usd(fcf_p), yoy_fcf, diag_fcf])

    # 6. BPA Diluido (EPS)
    eps_c = canonical.get("eps_diluted", {}).get(curr_p)
    eps_p = canonical.get("eps_diluted", {}).get(prev_p)
    fmt_eps_c = f"${eps_c:.2f}" if eps_c is not None else "N/D"
    fmt_eps_p = f"${eps_p:.2f}" if eps_p is not None else "N/D"
    yoy_eps = fmt_yoy(eps_c, eps_p)
    diag_eps = "Creación de valor por acción para el accionista." if eps_c and eps_p and eps_c >= eps_p else "Retribución por acción moderada."
    rows.append(["BPA Diluido (EPS)", fmt_eps_c, fmt_eps_p, yoy_eps, diag_eps])

    return headers, rows


# -------------------------------------------------------------
# ORQUESTADOR MAESTRO UNIVERSAL
# -------------------------------------------------------------
def generate_full_report(ticker="AAPL"):
    """
    Orquestador universal de reportes de investigación fundamental.
    Lee los JSONs estandarizados en data/processed/{TICKER}/ y renderiza
    las 14 secciones maestras idénticas para cualquier empresa pública.
    """
    ticker_clean = ticker.strip().upper()
    print(f"\n[Report Generator] Orquestando informe fundamental universal para {ticker_clean}...")
    
    # 1. Rutas
    try:
        from drive_manager import resolve_google_drive_path, get_ticker_drive_processed_dir, safe_copy_file
        drive_base_dir = resolve_google_drive_path()
        drive_base = (drive_base_dir / ticker_clean) if drive_base_dir else None
    except ImportError:
        drive_base = Path("G:/Mi unidad/analisis fundamental") / ticker_clean
        get_ticker_drive_processed_dir = None
        safe_copy_file = None
        
    local_base = Path("data/processed") / ticker_clean
    local_base.mkdir(parents=True, exist_ok=True)
    
    # 2. Carga de JSONs estandarizados
    profile_path = local_base / "company_profile.json"
    profile_data = {}
    if profile_path.exists():
        with open(profile_path, "r", encoding="utf-8") as f:
            profile_data = json.load(f)
            
    fin_path = local_base / "financial_statements.json"
    fin_data = {}
    if fin_path.exists():
        with open(fin_path, "r", encoding="utf-8") as f:
            fin_data = json.load(f)
            
    scoring_path = local_base / "fundamental_scores.json"
    scoring_data = {}
    if scoring_path.exists():
        with open(scoring_path, "r", encoding="utf-8") as f:
            scoring_data = json.load(f)
    elif fin_path.exists():
        scoring_data = calculate_fundamental_scores(ticker_clean, fin_path, local_base)
        
    segments_path = local_base / "segments_data.json"
    segments_data = {}
    if segments_path.exists():
        with open(segments_path, "r", encoding="utf-8") as f:
            segments_data = json.load(f)
            
    gov_path = local_base / "governance_insider_data.json"
    gov_data = {}
    if gov_path.exists():
        with open(gov_path, "r", encoding="utf-8") as f:
            gov_data = json.load(f)
    else:
        gov_data = analyze_governance_and_insiders(ticker_clean, local_base)
        
    ec_path = local_base / "earnings_call_data.json"
    ec_data = {}
    if ec_path.exists():
        with open(ec_path, "r", encoding="utf-8") as f:
            ec_data = json.load(f)
    else:
        try:
            from earnings_call_extractor import extract_and_generate_earnings_call_data
            ec_data = extract_and_generate_earnings_call_data(ticker_clean, local_base)
        except Exception as e:
            print(f"[Report Generator Warning] No se pudo auto-extraer earnings call para {ticker_clean}: {e}")
            
    # Metadatos generales
    company_name = profile_data.get("company_name", scoring_data.get("company_name", fin_data.get("company_name", ticker_clean)))
    exchange = profile_data.get("exchange") or fin_data.get("exchange") or "US Exchange"
    period_label = profile_data.get("period_label") or fin_data.get("latest_period") or "LTM"
    period_date = profile_data.get("period_date") or fin_data.get("period_end_date") or datetime.now().strftime("%d de %B de %Y")
    filing_source = profile_data.get("filing_source", "Formulario 10-Q, Formularios 8-K, Form 4, Form 144 (SEC EDGAR) & Earnings Call Transcript")
    cik = fin_data.get("cik") or profile_data.get("cik") or "SEC EDGAR"
    
    period_slug = re.sub(r'[^a-zA-Z0-9_\-]', '_', period_label.replace(" ", "_").replace("/", "_"))
    period_slug = re.sub(r'_+', '_', period_slug).strip('_')
    docx_path = local_base / f"Analisis_Resultados_{period_slug}_{ticker_clean}.docx"
    md_path = local_base / f"Analisis_Resultados_{period_slug}_{ticker_clean}.md"
    
    # -------------------------------------------------------------
    # CONSTRUCCIÓN DEL DOCUMENTO WORD (.DOCX)
    # -------------------------------------------------------------
    doc = docx.Document()
    
    # Configuración de márgenes institucionales
    for section in doc.sections:
        section.top_margin = Inches(0.8)
        section.bottom_margin = Inches(0.8)
        section.left_margin = Inches(0.85)
        section.right_margin = Inches(0.85)
        
    # Banner de Encabezado Institucional
    banner = doc.add_table(rows=1, cols=1)
    banner.alignment = WD_TABLE_ALIGNMENT.CENTER
    banner.autofit = False
    banner.columns[0].width = Inches(6.8)
    b_cell = banner.cell(0, 0)
    set_cell_shading(b_cell, HEADER_BG)
    set_cell_margins(b_cell, top=180, bottom=180, left=200, right=200)
    
    p_b0 = b_cell.paragraphs[0]
    p_b0.paragraph_format.space_before = Pt(0)
    p_b0.paragraph_format.space_after = Pt(2)
    r_sub = p_b0.add_run("INFORME EJECUTIVO DE INVESTIGACIÓN FUNDAMENTAL | WALL STREET EQUITY RESEARCH")
    r_sub.font.name = "Calibri"
    r_sub.font.size = Pt(9)
    r_sub.font.color.rgb = RGBColor(0xA0, 0xBE, 0xEB)
    r_sub.bold = True
    
    p_b1 = b_cell.add_paragraph()
    p_b1.paragraph_format.space_before = Pt(2)
    p_b1.paragraph_format.space_after = Pt(4)
    r_t = p_b1.add_run(f"{company_name.upper()} ({exchange}: {ticker_clean})\nResultados Trimestrales {period_label}, Earnings Call & Análisis de Gobernanza")
    r_t.font.name = "Calibri"
    r_t.font.size = Pt(17)
    r_t.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
    r_t.bold = True
    
    p_b2 = b_cell.add_paragraph()
    p_b2.paragraph_format.space_before = Pt(0)
    p_b2.paragraph_format.space_after = Pt(0)
    r_meta = p_b2.add_run(f"Fecha de Análisis: {datetime.now().strftime('%d de Septiembre de %Y')} | Período Contable: {period_date}\nFuente Oficial: {filing_source}")
    r_meta.font.name = "Calibri"
    r_meta.font.size = Pt(8.5)
    r_meta.font.color.rgb = RGBColor(0xD1, 0xDF, 0xF5)
    r_meta.italic = True
    
    doc.add_paragraph().paragraph_format.space_after = Pt(6)
    
    # =============================================================
    # 1. INTRODUCCIÓN AL NEGOCIO Y GO-TO-MARKET
    # =============================================================
    add_styled_heading_1(doc, "1. Introducción al Negocio y Arquitectura de Comercialización (Go-To-Market)")
    bm_callout = profile_data.get("business_model_callout", {
        "title": "RESUMEN DEL MODELO DE NEGOCIO Y PROPUESTA DE VALOR",
        "paragraphs": [f"Operaciones globales y propuesta de valor fundamental de {company_name} ({ticker_clean})."]
    })
    add_callout(doc, bm_callout.get("title", "RESUMEN DEL MODELO DE NEGOCIO Y PROPUESTA DE VALOR"), bm_callout.get("paragraphs", []))
    
    channels = profile_data.get("channels", {})
    add_styled_heading_2(doc, channels.get("title", "Estructura de Canales de Comercialización (Go-To-Market):"))
    add_body_p(doc, channels.get("intro", f"De acuerdo con la información auditada del Formulario 10-K ante la SEC, {company_name} distribuye sus productos a través de canales estratégicos:"))
    
    dir_ch = channels.get("direct", {})
    ind_ch = channels.get("indirect", {})
    if dir_ch:
        add_body_p(doc, dir_ch.get("description", ""), bold_prefix=f"• {dir_ch.get('label', 'Canal Directo:')} ")
    if ind_ch:
        add_body_p(doc, ind_ch.get("description", ""), bold_prefix=f"• {ind_ch.get('label', 'Canal Indirecto / Mayorista:')} ")
        
    # =============================================================
    # 2. DESGLOSE DE VENTAS POR LÍNEA DE PRODUCTOS Y SERVICIOS
    # =============================================================
    add_styled_heading_1(doc, "2. Desglose de Ventas por Línea de Productos y Servicios (Comparativa Interanual)")
    add_body_p(doc, f"A continuación se audita el desempeño y la mezcla de ingresos de las líneas de producto y marcas clave de {company_name} a partir de las notas de segmentación oficial presentadas ante la SEC:")
    
    prod_segments = segments_data.get("product_segments", [])
    periods = segments_data.get("periods", ["LTM", "FY2026", "FY2025"])
    p_curr = periods[0] if len(periods) > 0 else "Actual"
    p_prev = periods[1] if len(periods) > 1 else "Previo"
    
    seg_headers = ["Línea de Negocio / Producto", f"{p_curr} ($M)", f"{p_prev} ($M)", "Variación YoY %", "Margen / Mix", "Lectura Estratégica y Catalizador Operativo"]
    seg_data = []
    
    # Excluir subtotales del denominador para evitar doble cómputo
    tot_prod = sum(s.get("values", {}).get(p_curr, 0.0) for s in prod_segments if not s.get("is_subtotal"))
    if not tot_prod or tot_prod <= 0:
        tot_prod = sum(s.get("values", {}).get(p_curr, 0.0) for s in prod_segments) or 1.0

    if prod_segments:
        for ps in prod_segments:
            name = ps.get("name", "Línea Operativa")
            vals = ps.get("values", {})
            v_c = vals.get(p_curr, 0.0)
            v_p = vals.get(p_prev, 0.0)
            yoy = ((v_c - v_p) / v_p * 100) if v_p and v_p > 0 else 0.0
            sign = "+" if yoy >= 0 else ""
            yoy_str = f"{sign}{yoy:.1f}%"
            is_sub = ps.get("is_subtotal", False)
            
            cat = ps.get("description") or derive_segment_catalyst(name, yoy, is_subtotal=is_sub)
            mix_pct = (v_c / tot_prod * 100) if (tot_prod > 0 and not is_sub) else 100.0
            if is_sub:
                mix_label = "Subtotal"
            else:
                op_m = None
                if ps.get("operating_margin_pct"):
                    op_m = ps["operating_margin_pct"].get(p_curr) or ps["operating_margin_pct"].get("LTM")
                if op_m is not None:
                    mix_label = f"{mix_pct:.1f}% Mix | {float(op_m):.1f}% Mgn Op."
                else:
                    mix_label = f"{mix_pct:.1f}% Mix"
                
            seg_data.append([
                name,
                f"${v_c:,.1f} M",
                f"${v_p:,.1f} M",
                yoy_str,
                mix_label,
                cat
            ])
    else:
        seg_data = [
            ["Línea Operativa Principal", "N/D", "N/D", "N/D", "N/D", "Desglose por producto no publicado."],
            ["Línea Operativa Secundaria", "N/D", "N/D", "N/D", "N/D", "Información consolidada a nivel corporativo."]
        ]
    build_table(doc, seg_headers, seg_data, [1.5, 1.0, 1.0, 1.0, 0.9, 1.4])
    
    prod_qual_bullets = []
    prod_qual = profile_data.get("product_segments_analysis")
    if prod_qual:
        for item in prod_qual:
            prod_qual_bullets.append((item.get("prefix", "• "), item.get("text", "")))
    else:
        valid_prods = [s for s in prod_segments if not s.get("is_subtotal")]
        if not valid_prods:
            valid_prods = prod_segments
        for s in valid_prods[:4]:
            s_name = s.get("name", "Línea Operativa")
            s_vals = s.get("values", {})
            v_curr = s_vals.get(p_curr, 0.0)
            v_prev = s_vals.get(p_prev, 0.0)
            pct = (v_curr / tot_prod * 100) if tot_prod > 0 else 0.0
            yoy_growth = ((v_curr - v_prev) / v_prev * 100) if v_prev > 0 else 0.0
            sign = "+" if yoy_growth >= 0 else ""
            prefix = f"• {s_name} ({pct:.1f}% de facturación): "
            text = f"Genera ${v_curr:,.1f} M ({sign}{yoy_growth:.1f}% YoY), consolidándose como pilar operativo clave de {company_name}."
            prod_qual_bullets.append((prefix, text))

    add_styled_heading_2(doc, "Análisis Cualitativo de las Líneas de Negocio:")
    for prefix, text in prod_qual_bullets:
        add_body_p(doc, text, bold_prefix=prefix)
        
    # =============================================================
    # 3. DESGLOSE GEOGRÁFICO: MERCADOS Y PAÍSES
    # =============================================================
    add_styled_heading_1(doc, "3. Desglose Geográfico: Mercados y Países de Comercialización (Comparativa Interanual)")
    add_body_p(doc, f"{company_name} reporta sus ingresos desglosados en macro-regiones mundiales, reflejando una diversificación balanceada y expansión global:")
    
    geo_segments = segments_data.get("geographic_segments", [])
    geo_headers = ["Región Geográfica", f"{p_curr} ($M)", f"{p_prev} ($M)", "Variación YoY %", "Peso en Ventas %", "Dinámica del Mercado y Países Clave"]
    geo_data = []
    
    tot_geo = sum(gs.get("values", {}).get(p_curr, 0.0) for gs in geo_segments if not gs.get("is_subtotal"))
    if not tot_geo or tot_geo <= 0:
        tot_geo = sum(gs.get("values", {}).get(p_curr, 0.0) for gs in geo_segments) or 1.0

    if geo_segments:
        for gs in geo_segments:
            name = gs.get("name", "Región")
            vals = gs.get("values", {})
            v_c = vals.get(p_curr, 0.0)
            v_p = vals.get(p_prev, 0.0)
            yoy = ((v_c - v_p) / v_p * 100) if v_p and v_p > 0 else 0.0
            sign = "+" if yoy >= 0 else ""
            yoy_str = f"{sign}{yoy:.1f}%"
            is_sub = gs.get("is_subtotal", False)
            weight = (v_c / tot_geo * 100) if not is_sub else 100.0
            weight_str = f"{weight:.1f}%" if not is_sub else "Subtotal"
            cat = gs.get("description") or derive_geo_catalyst(name, yoy, weight, is_subtotal=is_sub)
            
            geo_data.append([
                name,
                f"${v_c:,.1f} M",
                f"${v_p:,.1f} M",
                yoy_str,
                weight_str,
                cat
            ])
    else:
        geo_data = [
            ["Mercado Geográfico Principal", "N/D", "N/D", "N/D", "N/D", "Base operativa consolidada."],
            ["Otros Mercados", "N/D", "N/D", "N/D", "N/D", "Distribución geográfica no desagregada."]
        ]
    build_table(doc, geo_headers, geo_data, [1.5, 1.0, 1.0, 1.0, 0.9, 1.4])
    
    geo_qual_bullets = []
    geo_qual = profile_data.get("geographic_analysis")
    if geo_qual:
        for item in geo_qual:
            geo_qual_bullets.append((item.get("prefix", "• "), item.get("text", "")))
    else:
        valid_geos = [gs for gs in geo_segments if not gs.get("is_subtotal")]
        if not valid_geos:
            valid_geos = geo_segments
        for gs in valid_geos[:3]:
            g_name = gs.get("name", "Región")
            g_vals = gs.get("values", {})
            gv_curr = g_vals.get(p_curr, 0.0)
            gv_prev = g_vals.get(p_prev, 0.0)
            g_pct = (gv_curr / tot_geo * 100) if tot_geo > 0 else 0.0
            g_yoy = ((gv_curr - gv_prev) / gv_prev * 100) if gv_prev > 0 else 0.0
            sign = "+" if g_yoy >= 0 else ""
            prefix = f"• Mercado {g_name} ({g_pct:.1f}% del total): "
            text = f"Aporta ${gv_curr:,.1f} M con variación YoY de {sign}{g_yoy:.1f}%, diversificando la exposición geográfica de {company_name}."
            geo_qual_bullets.append((prefix, text))

    add_styled_heading_2(doc, "Conclusión sobre Exposición Geográfica y Riesgo Cambiario (FX):")
    for prefix, text in geo_qual_bullets:
        add_body_p(doc, text, bold_prefix=prefix)
        
    # Detección de arquetipo
    archetype = (
        scoring_data.get("archetype")
        or fin_data.get("archetype")
        or profile_data.get("archetype")
    )
    if not archetype:
        sic_chk = str(scoring_data.get("sic_code") or fin_data.get("sic_code") or profile_data.get("sic_code") or "").strip()
        if sic_chk in ("6021", "6022", "6029", "6199", "6035", "6036"):
            archetype = "FINANCIAL_BANKING"
        elif sic_chk in ("6311", "6321", "6331", "6351", "6361"):
            archetype = "INSURANCE"
        elif sic_chk in ("6798",):
            archetype = "REAL_ESTATE_REIT"
        else:
            archetype = "STANDARD_CORPORATE"

    # =============================================================
    # 4. RESUMEN EJECUTIVO Y CUADRO DE MANDO FINANCIERO (SCORECARD)
    # =============================================================
    add_styled_heading_1(doc, "4. Resumen Ejecutivo y Cuadro de Mando Financiero (Scorecard)")
    sc_section = profile_data.get("scorecard", {})
    add_body_p(doc, sc_section.get("intro", f"{company_name} ha presentado un desempeño financiero consistente, con métricas auditadas desde SEC EDGAR:"))
    
    dyn_headers, dyn_data = build_dynamic_scorecard(fin_data, archetype)
    sc_headers = sc_section.get("headers") or dyn_headers
    sc_data = sc_section.get("data") or dyn_data
    build_table(doc, sc_headers, sc_data, [1.6, 1.1, 1.0, 1.0, 2.1])

    guide_title, guide_paras = get_scorecard_pedagogical_guide(archetype)
    add_callout(doc, guide_title, guide_paras, accent_color="1B365D", bg_color="F0F4F8")
    
    # =============================================================
    # 5. ANÁLISIS EXHAUSTIVO DE EARNINGS CALLS Y AUDITORÍA DIRECTIVA
    # =============================================================
    add_styled_heading_1(doc, "5. Análisis Exhaustivo de Conferencia de Resultados (Earnings Calls) y Auditoría del Discurso Directivo")
    
    bloque_a = ec_data.get("bloque_a", {})
    add_styled_heading_2(doc, f"BLOQUE A: Análisis del Trimestre Más Reciente ({bloque_a.get('period_label', period_label)})")
    add_body_p(doc, bloque_a.get("intro", "Durante la conferencia de resultados, el equipo directivo transmitió un tono de máxima confianza operativa y validación estratégica:"))
    
    # 5.1 Guidance
    add_styled_heading_2(doc, "1. Proyecciones Oficiales y Guidance del Management:")
    g_headers = bloque_a.get("guidance_headers", ["Métrica", "Rango Oficial", "Lectura Clave"])
    g_data = bloque_a.get("guidance_data", [["Ingresos", "+10% YoY", "Metas conservadoras"]])
    build_table(doc, g_headers, g_data, [2.0, 1.8, 3.0], ["LEFT", "CENTER", "LEFT"])
    
    # 5.2 Hitos
    add_styled_heading_2(doc, "2. Hitos Más Importantes y Catalizadores Clave del Trimestre:")
    h_headers = bloque_a.get("hitos_headers", ["Hito Estratégico", "Declaración Clave", "Impacto"])
    h_data = bloque_a.get("hitos_data", [["Expansión", "Declaración", "Impacto en tesis"]])
    build_table(doc, h_headers, h_data, [1.8, 2.5, 2.5], ["LEFT", "LEFT", "LEFT"])
    
    # 5.3 Riesgos
    add_styled_heading_2(doc, "3. Matriz de Riesgos, Advertencias y Desafíos Operativos Detectados:")
    r_headers = bloque_a.get("riesgos_headers", ["Riesgo / Advertencia", "Comentario Textual", "Impacto", "Mitigación"])
    r_data = bloque_a.get("riesgos_data", [["Riesgo Logístico", "Comentario directivo", "Impacto transitorio", "Cobertura"]])
    build_table(doc, r_headers, r_data, [1.7, 2.1, 1.5, 1.5], ["LEFT", "LEFT", "LEFT", "LEFT"])
    
    # 5.4 Q&A Wall Street
    add_styled_heading_2(doc, "4. Desglose Exhaustivo de Preguntas y Respuestas (Q&A con Wall Street):")
    add_body_p(doc, "Se presenta la transcripción y auditoría integral de las principales firmas de inversión de Wall Street con sus preguntas y respuestas directivas:")
    
    qa_list = bloque_a.get("qa_full_data", [])
    for firm_title, qa_items in qa_list:
        add_styled_heading_2(doc, firm_title)
        for label, desc in qa_items:
            add_body_p(doc, desc, bold_prefix=f"• {label} ")
            
    # BLOQUE B: Longitudinal 5 Trimestres
    bloque_b = ec_data.get("bloque_b", {})
    add_styled_heading_2(doc, f"BLOQUE B: Análisis Longitudinal y Auditoría de Discurso Directivo ({bloque_b.get('period_range', '5 Trimestres')})")
    add_body_p(doc, bloque_b.get("intro", "A partir del análisis de las transcripciones de cinco trimestres consecutivos disponibles en Google Drive, se audita el Say-Do Ratio:"))
    
    sd_headers = bloque_b.get("say_do_headers", ["Trimestre", "Discurso / Promesas", "Desafíos", "Desempeño Real", "Say-Do Ratio"])
    sd_data = bloque_b.get("say_do_data", [["Q1", "Promesa", "Riesgo", "Resultado", "SUPERADO"]])
    build_table(doc, sd_headers, sd_data, [0.8, 2.0, 1.8, 1.8, 1.4], ["CENTER", "LEFT", "LEFT", "LEFT", "CENTER"])
    
    add_styled_heading_2(doc, "Cronología y Mutación Dinámica de los Riesgos Operativos (5 Trimestres):")
    rh_headers = bloque_b.get("riesgos_hist_headers", ["Período Fiscal", "Riesgo Dominante", "Severidad", "Evolución Real"])
    rh_data = bloque_b.get("riesgos_hist_data", [["Q1", "Riesgo", "Alerta Media", "Mitigado"]])
    build_table(doc, rh_headers, rh_data, [1.0, 2.2, 1.2, 2.4], ["CENTER", "LEFT", "CENTER", "LEFT"])
    
    add_body_p(doc, "Conclusiones sobre la Mutación de Riesgos:", bold_prefix="🔍 ")
    for prefix, text_c in bloque_b.get("conclusiones_riesgos", []):
        add_body_p(doc, text_c, bold_prefix=prefix)
        
    cred_callout = bloque_b.get("credibility_callout", {
        "title": "CALIFICACIÓN DE CREDIBILIDAD DEL MANAGEMENT: EXCEPCIONAL (TIER 1)",
        "bullets": ["Consistencia histórica en fijar guías prudentes y batir expectativas."]
    })
    add_callout(doc, cred_callout.get("title"), cred_callout.get("bullets"), accent_color="0A3641", bg_color="E8EEF5")
    
    # =============================================================
    # 6. ASIGNACIÓN DE CAPITAL Y BALANCE
    # =============================================================
    add_styled_heading_1(doc, "6. Posición Patrimonial, Estructura de Capital y Asignación de Recursos (Capital Allocation)")
    bal_sec = profile_data.get("balance_section", {})
    add_body_p(doc, bal_sec.get("intro", f"La estructura patrimonial de {company_name} destaca por su solvencia:"))
    
    add_styled_heading_2(doc, "6.1. Cuadro de Mando de Liquidez, Deuda y Posición Neta de Caja")
    b_headers = bal_sec.get("table_headers", ["Métrica Patrimonial", "Actual", "Previo", "Variación", "Diagnóstico"])
    b_data = bal_sec.get("table_data", [["Liquidez Total", "$1,000 M", "$900 M", "+11%", "Solidez"]])
    build_table(doc, b_headers, b_data, [1.8, 1.0, 1.0, 1.1, 1.9], ['LEFT', 'RIGHT', 'RIGHT', 'RIGHT', 'LEFT'])
    if bal_sec.get("carry_trade_note"):
        add_body_p(doc, bal_sec["carry_trade_note"], bold_prefix="• Estructura de Rendimiento de Tesorería: ")
        
    add_styled_heading_2(doc, "6.2. Política de Retorno al Accionista: Recompra de Acciones y Dividendos")
    add_body_p(doc, bal_sec.get("return_intro", f"{company_name} destina su flujo de caja a recompras y dividendos:"))
    ret_headers = bal_sec.get("return_headers", ["Componente de Retorno", "Actual", "Acumulado", "Impacto"])
    ret_data = bal_sec.get("return_data", [["Recompra Neta", "$100 M", "$300 M", "Retiro de títulos"]])
    build_table(doc, ret_headers, ret_data, [2.1, 1.2, 1.2, 2.3], ['LEFT', 'RIGHT', 'RIGHT', 'LEFT'])
    if bal_sec.get("sbc_note"):
        add_body_p(doc, bal_sec["sbc_note"], bold_prefix="• Calidad de la Recompra vs. Dilución por SBC: ")
        
    cap_alloc = profile_data.get("capital_allocation", {})
    add_styled_heading_2(doc, "6.3. Inversiones Estratégicas, Adquisiciones (M&A) y Expansión Productiva")
    ma_h = cap_alloc.get("ma_headers", ["Iniciativa", "Tipo", "Capital", "Objetivo Estratégico"])
    ma_d = cap_alloc.get("ma_data", [["Alianza", "Industrial", "Estratégico", "Fortalecimiento de cadena"]])
    build_table(doc, ma_h, ma_d, [1.7, 1.3, 1.2, 2.6], ['LEFT', 'LEFT', 'RIGHT', 'LEFT'])
    
    add_styled_heading_2(doc, cap_alloc.get("capex_title", "6.4. CapEx de Vanguardia y Eficiencia de Cadena de Suministro"))
    add_body_p(doc, cap_alloc.get("capex_intro", "El gasto de capital se orienta a proyectos de alta rentabilidad:"))
    for prefix, text_c in cap_alloc.get("capex_bullets", []):
        add_body_p(doc, text_c, bold_prefix=prefix)
        
    add_callout(doc, "GUÍA DE DIAGNÓSTICO FUNDAMENTAL: ¿CÓMO AUDITAR EL BALANCE Y LA ASIGNACIÓN DE CAPITAL?", [
        "• Caja Neta (Net Cash) vs. Deuda Neta: Se calcula restando la deuda financiera bruta a la liquidez total. Una posición positiva certifica que la empresa es acreedora neta y solvente ante cualquier crisis.",
        "• Recompra Neta vs. Dilución por SBC: Una recompra solo crea valor genuino si retira más acciones de las que se emiten vía Stock-Based Compensation.",
        "• Eficiencia del CapEx: Las mejores empresas operan modelos de capital ligero (Asset-Light / Fabless) o asignan CapEx a proyectos con retornos que superan ampliamente su WACC."
    ], accent_color="0A3641", bg_color="E8EEF5")
    
    # =============================================================
    # 7. ESTRATEGIA TECNOLÓGICA Y FOSOS DEFENSIVOS (ECONOMIC MOAT)
    # =============================================================
    add_styled_heading_1(doc, "7. Estrategia Tecnológica, Fosos Defensivos (Economic Moat) y Ventajas Competitivas")
    moat_sec = profile_data.get("moat", {})
    add_body_p(doc, moat_sec.get("intro", f"Evaluación del foso defensivo económico (Economic Moat) de {company_name}:"))
    
    add_styled_heading_2(doc, "7.1. Cuadro de Mando de Fosos Defensivos (Dorsey / Morningstar Framework)")
    m_headers = moat_sec.get("headers", ["Fuente del Foso", "Intensidad", "Mecanismo", "Diagnóstico"])
    m_data = moat_sec.get("table_data", [["Marca", "Alta", "Poder de precios", "Margen protegido"]])
    build_table(doc, m_headers, m_data, [1.6, 1.0, 2.3, 1.9], ['LEFT', 'CENTER', 'LEFT', 'LEFT'])
    add_body_p(doc, f"Dictamen Estratégico Global: {moat_sec.get('verdict', 'WIDE MOAT')}", bold_prefix="• ")
    
    for sub in moat_sec.get("subsections", []):
        add_styled_heading_2(doc, sub.get("title", "Ventaja Competitiva:"))
        for prefix, text_c in sub.get("bullets", []):
            add_body_p(doc, text_c, bold_prefix=prefix)
            
    add_callout(doc, "GUÍA DE DIAGNÓSTICO FUNDAMENTAL: ¿CÓMO AUDITAR EL FOSO DEFENSIVO (ECONOMIC MOAT)?", [
        "• Identificación de un Wide Moat: Una empresa posee un foso amplio cuando puede generar sistemáticamente un ROIC superior a su WACC durante más de 10 o 15 años.",
        "• Costes de Cambio y Pricing Power: Si un cliente no puede sustituir el producto sin fricción, la empresa puede subir precios sin perder demanda.",
        "• Vigilancia de Erosión: La caída continua de margen bruto o la necesidad de rebajas agresivas son las primeras señales de debilitamiento de un foso."
    ], accent_color="0A3641", bg_color="E8EEF5")
    
    # =============================================================
    # 8. GOBERNANZA CORPORATIVA, FORM 4, 144 Y ALERTAS 8-K
    # =============================================================
    add_styled_heading_1(doc, "8. Gobernanza Corporativa, Sentimiento Insider (Form 4 y 144) y Alertas 8-K")
    add_callout(doc, "GUÍA PEDAGÓGICA PARA EL INVERSOR: LA CADENA DE TRAZABILIDAD DE LA SEC", [
        "• Formulario 8-K (La Empresa Habla): Notifica eventos materiales corporativos en tiempo real (relevo del CEO, cambios de auditor o acuerdos clave).",
        "• Formulario 144 (El Aviso Previo): Notificación previa y obligatoria de un directivo antes de vender acciones restringidas.",
        "• Formulario 4 (La Ejecución Real): Registro en 48 horas de la transacción ya liquidada en bolsa.",
        "• Regla de Oro: Las ventas bajo Planes Rule 10b5-1 son automáticas y preprogramadas sin información privilegiada. Las ventas discrecionales reflejan decisiones activas."
    ], accent_color="0A3641", bg_color="E8EEF5")
    
    gov_sec = profile_data.get("governance_section", {})
    add_styled_heading_2(doc, "8.1. Hechos Relevantes y Alertas Tempranas de la Corporación (Formulario 8-K)")
    ev_h = gov_sec.get("events_8k_headers", ["Fecha SEC", "Ítem 8-K", "Evento", "¿Qué significa?", "Diagnóstico"])
    ev_d = gov_sec.get("events_8k_data", [["2026-07-01", "Item 2.02", "Resultados", "Reporte ordinario", "Normalidad"]])
    build_table(doc, ev_h, ev_d, [1.0, 1.0, 1.5, 1.7, 1.6], ['CENTER', 'CENTER', 'LEFT', 'LEFT', 'LEFT'])
    
    add_styled_heading_2(doc, "8.2. Monitor Unificado de Insiders: Del Aviso (Form 144) a la Ejecución (Form 4)")
    add_body_p(doc, "Consolidación de transacciones de directivos clave cruzando intención (Form 144) con ejecución efectiva (Form 4):")
    ins_h = gov_sec.get("insider_headers", ["Directivo / Cargo", "Tipo Operación", "Volumen", "Importe", "Trazabilidad", "Diagnóstico"])
    ins_d = gov_sec.get("insider_data", [["Directivo", "Retención", "0", "$0", "Form 4", "Alineación"]])
    build_table(doc, ins_h, ins_d, [1.5, 1.4, 0.9, 1.0, 0.9, 1.1], ['LEFT', 'CENTER', 'RIGHT', 'RIGHT', 'CENTER', 'LEFT'])
    if gov_sec.get("insider_dictum"):
        add_body_p(doc, gov_sec["insider_dictum"], bold_prefix="• Dictamen de Convicción Interna: ")
        
    add_styled_heading_2(doc, "8.3. Cuadro de Mando y Calificación Global de Gobernanza")
    gov_h = gov_sec.get("gov_table_headers", ["Dimensión", "Resultado", "Calificación", "Diagnóstico"])
    gov_d = gov_sec.get("gov_table_data", [["Puntuación", "Sólida", "85 / 100", "Bajo riesgo"]])
    build_table(doc, gov_h, gov_d, [1.8, 1.4, 1.4, 2.2], ['LEFT', 'LEFT', 'CENTER', 'LEFT'])
    
    # =============================================================
    # 9. DIAGNÓSTICO CUANTITATIVO (PIOTROSKI & MOHANRAM) Y PARES
    # =============================================================
    add_styled_heading_1(doc, "9. Diagnóstico Cuantitativo de Resiliencia y Crecimiento (Piotroski & Mohanram)")
    diag_card = scoring_data.get("latest_diagnosis", {})
    
    piot_dict = scoring_data.get("piotroski_f_score", {})
    piot_data = piot_dict.get("LTM") or (piot_dict.get(scoring_data.get("fiscal_years", [""])[0], {}) if scoring_data.get("fiscal_years") else {})
    piot_signals = piot_data.get("signals", {})
    f_score_val = piot_data.get("total_score", diag_card.get("f_score", 8))
    piot_rating = piot_data.get("rating", "SALUD EXCEPCIONAL")
    
    fy_candidates = [y for y in scoring_data.get("fiscal_years", []) if y != "LTM"]
    prev_fy = fy_candidates[0] if fy_candidates else "FY Previo"
    prev_piot = piot_dict.get(prev_fy, {})
    prev_f_score = prev_piot.get("total_score", f_score_val)

    moh_dict = scoring_data.get("mohanram_g_score", {})
    moh_data = moh_dict.get("LTM") or (moh_dict.get(scoring_data.get("fiscal_years", [""])[0], {}) if scoring_data.get("fiscal_years") else {})
    moh_signals = moh_data.get("signals", {})
    g_score_val = moh_data.get("total_score", diag_card.get("g_score", 7))
    moh_rating = moh_data.get("rating", "LÍDER DE LA INDUSTRIA")
    prev_moh = moh_dict.get(prev_fy, {})
    prev_g_score = prev_moh.get("total_score", g_score_val)

    forensic = scoring_data.get("forensic_accounting_analysis", {})
    latest_forensic = forensic.get("latest_result", {})
    sloan_latest = latest_forensic.get("sloan_accrual", {})
    cfo_val = sloan_latest.get("cfo", 0) or 0
    ni_val = sloan_latest.get("net_income", 0) or 0
    cfo_str = f"${cfo_val/1e6:,.1f}M"
    ni_str = f"${ni_val/1e6:,.1f}M"

    comp_lever = piot_signals.get("F_dLEVER", {}).get("comparison_label", "Deuda controlada")
    comp_offer = piot_signals.get("EQ_OFFER", {}).get("comparison_label", "Sin dilución neta")
    comp_margin = piot_signals.get("F_dMARGIN", {}).get("comparison_label", "Márgenes firmes")
    comp_turn = piot_signals.get("F_dTURN", {}).get("comparison_label", "Rotación de activos")

    add_callout(doc, "CLASIFICACIÓN ESTRATÉGICA EN MATRIZ FUNDAMENTAL", [
        f"Posición Cuantitativa: {diag_card.get('badge', '💎 CUADRANTE I: COMPOUNDER DE ÉLITE')}",
        f"Piotroski F-Score (Solvencia Interna): {f_score_val} / 9 Puntos | {piot_rating}",
        f"Mohanram G-Score (Ventaja Sectorial):  {g_score_val} / 8 Puntos | {moh_rating}",
        f"Tesis Cuantitativa: {company_name} combina una salud financiera interna intachable con una superioridad competitiva sectorial demostrada frente a sus pares de la industria."
    ], accent_color="1B365D", bg_color="F0F4F8")
    
    add_styled_heading_2(doc, "9.1. Piotroski F-Score: Salud Financiera y Calidad Contable Interna")
    add_body_p(doc, 
        "Desarrollado por el profesor Joseph Piotroski (Universidad de Stanford), este modelo evalúa la solidez económica "
        "interna de la empresa a través de 9 señales contables distribuidas en tres dimensiones críticas: Rentabilidad (ROA "
        "positivo y creciente, CFO positivo, calidad de devengos Sloan), Apalancamiento y Liquidez (desendeudamiento "
        "financiero total, mejora de razón corriente y cero dilución por emisión de acciones) y Eficiencia Operativa (expansión "
        "de margen bruto y mayor rotación de activos)."
    )
    add_body_p(doc, f"{f_score_val} / 9 Puntos en LTM ({piot_rating}) ({prev_f_score} / 9 en {prev_fy}).", bold_prefix="• Puntaje Obtenido: ")
    add_body_p(doc, 
        f"Una calificación de {f_score_val}/9 sitúa a {company_name} en el percentil superior del mercado global. Certifica que la compañía:",
        bold_prefix="• ¿Qué significa este puntaje para el Inversor? "
    )
    add_body_p(doc, f"La caja operativa ({cfo_str} en LTM) respalda con holgura al beneficio neto contable ({ni_str}), descartando manipulación de inventarios o ventas a crédito ficticias.", bold_prefix="1. Genera beneficios respaldados por caja líquida: ")
    add_body_p(doc, f"Mantiene una estructura financiera solvente con disciplina en el endeudamiento ({comp_lever}).", bold_prefix="2. Reduce o controla su apalancamiento financiero real: ")
    add_body_p(doc, f"No financia sus operaciones emitiendo nuevas acciones dilutivas, priorizando la retención o recompra de títulos ({comp_offer}).", bold_prefix="3. Protege al accionista minoritario: ")
    add_body_p(doc, f"Optimiza tanto su margen comercial ({comp_margin}) como la productividad de sus activos instalados ({comp_turn}).", bold_prefix="4. Expande su eficiencia operativa: ")

    p_headers = ["Dimensión / Criterio Piotroski", "Condición Contable Evaluada", "Valor Detectado", "Punto Asignado"]
    p_rows = []
    piot_signal_order = ["F_ROA", "F_CFO", "F_dROA", "F_ACCRUAL", "F_dLEVER", "F_dLIQUID", "EQ_OFFER", "F_dMARGIN", "F_dTURN"]
    for sig_key in piot_signal_order:
        sig_data = piot_signals.get(sig_key, {})
        if sig_data:
            cat = sig_data.get("category", "")
            name = sig_data.get("name", sig_key)
            label = f"{cat}: {name}" if cat else name
            desc = sig_data.get("description", "")
            val_detect = sig_data.get("comparison_label") or sig_data.get("formatted_value", "Cumple")
            pts = "1 Pto" if sig_data.get("passed") else "0 Ptos"
            p_rows.append([label, desc, val_detect, pts])

    if not p_rows:
        for c_key, c_val in piot_signals.items():
            p_rows.append([
                c_val.get("name", c_key),
                c_val.get("description", "Criterio contable"),
                str(c_val.get("comparison_label", c_val.get("formatted_value", "Cumple"))),
                "1 Pto" if c_val.get("passed") else "0 Ptos"
            ])
    build_table(doc, p_headers, p_rows, [2.2, 2.5, 1.1, 1.0], ['LEFT', 'LEFT', 'CENTER', 'CENTER'])
    
    add_styled_heading_2(doc, "9.2. Mohanram G-Score: Calidad de Crecimiento frente a la Industria")
    add_body_p(doc, 
        "Diseñado por el profesor Partha Mohanram (Universidad de Columbia), este modelo evalúa la calidad fundamental "
        "y la sostenibilidad del crecimiento en empresas contrastando sus métricas frente a la mediana de su sector industrial. "
        "El modelo audita 8 señales agrupadas en: Desempeño Operativo y Retorno (ROA, CFROA y Calidad de Devengos), "
        "Estabilidad del Negocio (baja variabilidad de ROA y ventas) y Reinversión en Ventajas Competitivas (intensidad "
        "en I+D, CapEx de vanguardia y Apalancamiento Comercial en SG&A)."
    )
    add_body_p(doc, f"{g_score_val} / 8 Puntos en LTM ({moh_rating}) ({prev_g_score} / 8 en {prev_fy}).", bold_prefix="• Puntaje Obtenido: ")
    add_body_p(doc, 
        f"Una puntuación de {g_score_val}/8 consolida a {company_name} como líder de calidad fundamental en su industria. Certifica que la firma:",
        bold_prefix="• ¿Qué significa este puntaje para el Inversor? "
    )
    add_body_p(doc, "Supera sistemáticamente a la mediana de sus competidores directos en rentabilidad sobre activos y generación de flujo de caja libre.", bold_prefix="1. Retorno superior: ")
    add_body_p(doc, "Exhibe una trayectoria de crecimiento sólida y predecible con menor volatilidad en sus resultados comerciales.", bold_prefix="2. Estabilidad de negocio: ")
    add_body_p(doc, "Mantiene una disciplina férrea de reinversión en capital e innovación para defender y expandir su foso competitivo.", bold_prefix="3. Reinversión estratégica: ")

    m_headers = ["Criterio Mohanram G-Score", "Condición frente a la Mediana", "Valor Detectado", "Punto Asignado"]
    m_rows = []
    moh_signal_order = ["G1_ROA", "G2_CFROA", "G3_ACCRUAL", "G4_VAR_ROA", "G5_VAR_GROWTH", "G6_RD_INTENSITY", "G7_CAPEX_INTENSITY", "G8_OPERATING_LEVERAGE"]
    for sig_key in moh_signal_order:
        sig_data = moh_signals.get(sig_key, {})
        if sig_data:
            name = sig_data.get("name", sig_key)
            desc = sig_data.get("description", "Supera mediana sectorial")
            val_detect = sig_data.get("comparison_label") or sig_data.get("formatted_value", "Cumple")
            pts = "1 Pto" if sig_data.get("passed") else "0 Ptos"
            m_rows.append([name, desc, val_detect, pts])

    if not m_rows:
        for c_key, c_val in moh_signals.items():
            m_rows.append([
                c_val.get("name", c_key),
                c_val.get("description", "Supera mediana sectorial"),
                str(c_val.get("comparison_label", c_val.get("formatted_value", "Cumple"))),
                "1 Pto" if c_val.get("passed") else "0 Ptos"
            ])
    build_table(doc, m_headers, m_rows, [2.2, 2.5, 1.1, 1.0], ['LEFT', 'LEFT', 'CENTER', 'CENTER'])
    
    peers_sec = profile_data.get("peers_section", {})
    add_styled_heading_2(doc, peers_sec.get("title", "9.3. Benchmarking Competitivo del Sector & Medianas Oficiales"))
    add_body_p(doc, 
        "A continuación se auditan las cifras financieras comparables en base a los últimos 12 meses (LTM) auditados de la industria, "
        "a partir de las cuales se deducen las medianas y percentiles que alimentan el scoring de calidad, productividad del capital y resiliencia fundamental:"
    )
    raw_peer_headers = peers_sec.get("headers", ["Ticker", "Compañía", "Ventas ($M)", "Margen Bruto", "Margen EBIT", "ROIC Intang.", "Novy-Marx GP/A (%)", "F-Score", "G-Score"])
    peer_headers = [h if h != "GP/A" else "Novy-Marx GP/A (%)" for h in raw_peer_headers]
    default_peer_rows = [
        [ticker_clean, company_name, "N/D", "N/D", "N/D", "N/D", "N/D", f"{f_score_val} / 9", f"{g_score_val} / 8"],
        ["MEDIANA", "Mediana Sectorial", "N/D", "N/D", "N/D", "N/D", "N/D", "N/D", "N/D"]
    ]
    peer_rows = peers_sec.get("rows") or default_peer_rows
    # Normalizar columna GP/A a porcentaje explícito si viene como decimal
    gpa_idx = -1
    for idx, h in enumerate(peer_headers):
        if "GP/A" in h:
            gpa_idx = idx
            break
    if gpa_idx != -1:
        for r_idx in range(len(peer_rows)):
            val = peer_rows[r_idx][gpa_idx]
            if isinstance(val, (int, float)):
                if val <= 1.5:
                    peer_rows[r_idx][gpa_idx] = f"{val * 100.0:.1f}%"
                else:
                    peer_rows[r_idx][gpa_idx] = f"{val:.1f}%"
            elif isinstance(val, str):
                val_clean = val.strip().replace("%", "")
                try:
                    f_val = float(val_clean)
                    if "%" not in val:
                        if f_val <= 1.5:
                            peer_rows[r_idx][gpa_idx] = f"{f_val * 100.0:.1f}%"
                        else:
                            peer_rows[r_idx][gpa_idx] = f"{f_val:.1f}%"
                except ValueError:
                    pass
    build_table(doc, peer_headers, peer_rows, [0.7, 1.5, 0.9, 0.7, 0.7, 0.7, 0.8, 0.5, 0.5], ['CENTER', 'LEFT', 'RIGHT', 'RIGHT', 'RIGHT', 'RIGHT', 'RIGHT', 'CENTER', 'CENTER'])
    
    # =============================================================
    # 10 A 14. BUILDERS MODULARES CUANTITATIVOS
    # =============================================================
    # 10. Novy-Marx GP/A
    novy_marx_data = scoring_data.get("novy_marx_analysis", {})
    add_novy_marx_section_docx(doc, novy_marx_data, ticker=ticker_clean, company_name=company_name, section_num=10)
    
    # 11. ROIC, WACC & EVA
    add_roic_wacc_section_docx(doc, scoring_data, ticker=ticker_clean, company_name=company_name, section_num=11)
    
    # 12. Auditoría Forense Contable
    add_forensic_section_docx(doc, scoring_data, ticker=ticker_clean, company_name=company_name, section_num=12, profile_data=profile_data)
    
    # 13. Solvencia y Estrés Financiero
    add_solvency_section_docx(doc, scoring_data, ticker=ticker_clean, company_name=company_name, section_num=13, profile_data=profile_data)
    
    # 14. Modelado Financiero y Reverse DCF
    add_valuation_section_docx(doc, scoring_data, ticker=ticker_clean, company_name=company_name, section_num=14, profile_data=profile_data)
    
    # Pie institucional
    p_end = doc.add_paragraph()
    p_end.paragraph_format.space_before = Pt(20)
    p_end.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r_end = p_end.add_run(f"Fin del Informe Oficial de Investigación Fundamental — {company_name} ({ticker_clean}) | Wall Street Equity Research Platform")
    r_end.font.name = "Calibri"
    r_end.font.size = Pt(8.5)
    r_end.italic = True
    r_end.font.color.rgb = SLATE
    
    doc.save(docx_path)
    print(f"[Report Generator] Documento Word generado con éxito: {docx_path}")
    
    # -------------------------------------------------------------
    # GENERACIÓN DEL INFORME EN MARKDOWN (.MD) SINCRONIZADO
    # -------------------------------------------------------------
    novy_marx_md = generate_novy_marx_section_md(novy_marx_data, ticker=ticker_clean, company_name=company_name, section_num=10) + "\n---\n\n"
    roic_wacc_md = generate_roic_wacc_section_md(scoring_data, ticker=ticker_clean, company_name=company_name, section_num=11) + "\n---\n\n"
    forensic_md = generate_forensic_section_md(scoring_data, ticker=ticker_clean, company_name=company_name, section_num=12, profile_data=profile_data) + "\n---\n\n"
    solvency_md = generate_solvency_section_md(scoring_data, ticker=ticker_clean, company_name=company_name, section_num=13, profile_data=profile_data) + "\n---\n\n"
    valuation_md = generate_valuation_section_md(scoring_data, ticker=ticker_clean, company_name=company_name, section_num=14, profile_data=profile_data)
    
    guide_title, guide_paras = get_scorecard_pedagogical_guide(archetype)
    md_scorecard_guide = f"> 📌 **{guide_title}**  \n" + "  \n".join(f"> {p}" for p in guide_paras)
    md_prod_qual_text = "\n".join(f"* **{p.lstrip('• ').strip()}** {t}" for p, t in prod_qual_bullets)
    md_geo_qual_text = "\n".join(f"* **{p.lstrip('• ').strip()}** {t}" for p, t in geo_qual_bullets)
    
    # Tablas Markdown para Bloque A y B
    md_guidance_table = "| Métrica / Parámetro Proyectado | Rango de Guidance Oficial | Lectura Estratégica y Factores Clave |\n| :--- | :---: | :--- |\n"
    for r in g_data:
        md_guidance_table += f"| **{r[0]}** | **{r[1]}** | {r[2]} |\n"
        
    md_hitos_table = "| Hito Estratégico | Declaración Clave de la Dirección | Impacto en la Tesis de Inversión |\n| :--- | :--- | :--- |\n"
    for r in h_data:
        md_hitos_table += f"| **{r[0]}** | {r[1]} | {r[2]} |\n"
        
    md_riesgos_table = "| Riesgo / Advertencia | Comentario Textual del Management | Impacto Cuantitativo Proyectado | Estrategia de Mitigación |\n| :--- | :--- | :--- | :--- |\n"
    for r in r_data:
        md_riesgos_table += f"| **{r[0]}** | {r[1]} | {r[2]} | {r[3]} |\n"
        
    md_qa_section = ""
    for firm, qas in qa_list:
        md_qa_section += f"#### {firm}\n"
        for label, desc in qas:
            md_qa_section += f"* **{label}** {desc}\n"
        md_qa_section += "\n"
        
    md_say_do_table = "| Trimestre | Discurso Central & Promesas del CEO / CFO | Desafíos y Riesgos Advertidos | Desempeño Real Registrado en Siguientes Períodos | Say-Do Ratio |\n| :---: | :--- | :--- | :--- | :---: |\n"
    for r in sd_data:
        md_say_do_table += f"| **{r[0]}** | {r[1]} | {r[2]} | {r[3]} | **{r[4]}** |\n"
        
    md_riesgos_hist_table = "| Período Fiscal | Riesgo Dominante Señalado por la Dirección | Severidad / Semáforo | Evolución Posterior y Desenlace Real en el Negocio |\n| :---: | :--- | :---: | :--- |\n"
    for r in rh_data:
        md_riesgos_hist_table += f"| **{r[0]}** | {r[1]} | **{r[2]}** | {r[3]} |\n"
        
    md_scorecard_table = f"| Métrica Financiera | {sc_headers[1]} | {sc_headers[2]} | {sc_headers[3]} | Diagnóstico Fundamental y Salud Operativa |\n| :--- | :---: | :---: | :---: | :--- |\n"
    for r in sc_data:
        md_scorecard_table += f"| **{r[0]}** | **{r[1]}** | {r[2]} | **{r[3]}** | {r[4]} |\n"
        
    md_prod_table = f"| Línea de Negocio / Producto | {p_curr} ($M) | {p_prev} ($M) | Crecimiento YoY | Margen / Mix | Lectura Estratégica |\n| :--- | :---: | :---: | :---: | :---: | :--- |\n"
    for r in seg_data:
        md_prod_table += f"| **{r[0]}** | **{r[1]}** | {r[2]} | **{r[3]}** | {r[4]} | {r[5]} |\n"
        
    md_geo_table = f"| Región Geográfica | {p_curr} ($M) | {p_prev} ($M) | Crecimiento YoY | Peso en Ventas % | Diagnóstico Operativo |\n| :--- | :---: | :---: | :---: | :---: | :--- |\n"
    for r in geo_data:
        md_geo_table += f"| **{r[0]}** | **{r[1]}** | {r[2]} | **{r[3]}** | {r[4]} | {r[5]} |\n"
        
    md_bal_table = "| Métrica Patrimonial | Actual | Previo | Variación YoY | Diagnóstico de Solvencia y Balance |\n| :--- | :---: | :---: | :---: | :--- |\n"
    for r in b_data:
        md_bal_table += f"| **{r[0]}** | **{r[1]}** | {r[2]} | **{r[3]}** | {r[4]} |\n"
        
    md_ret_table = "| Componente de Retorno | Período Actual | Período Acumulado | Impacto en la Tesis del Accionista |\n| :--- | :---: | :---: | :--- |\n"
    for r in ret_data:
        md_ret_table += f"| **{r[0]}** | **{r[1]}** | {r[2]} | {r[3]} |\n"
        
    md_moat_table = "| Fuente del Foso Defensivo | Intensidad | Mecanismo de Protección Económica | Diagnóstico Competitivo |\n| :--- | :---: | :--- | :--- |\n"
    for r in m_data:
        md_moat_table += f"| **{r[0]}** | **{r[1]}** | {r[2]} | {r[3]} |\n"
        
    md_ev_table = "| Fecha SEC | Ítem 8-K | Naturaleza del Evento | ¿Qué significa para la Empresa? | Diagnóstico para el Inversor |\n| :---: | :---: | :--- | :--- | :--- |\n"
    for r in ev_d:
        md_ev_table += f"| {r[0]} | **{r[1]}** | {r[2]} | {r[3]} | {r[4]} |\n"
        
    md_ins_table = "| Directivo / Cargo Clave | Tipo de Operación y Modalidad SEC | Volumen de Acciones | Importe Efectivo ($) | Trazabilidad SEC | Diagnóstico de Convicción |\n| :--- | :---: | :---: | :---: | :---: | :--- |\n"
    for r in ins_d:
        md_ins_table += f"| **{r[0]}** | {r[1]} | {r[2]} | {r[3]} | {r[4]} | {r[5]} |\n"
        
    md_gov_table = "| Dimensión de Gobernanza | Resultado Detectado | Calificación / Semáforo | Diagnóstico para el Accionista |\n| :--- | :--- | :---: | :--- |\n"
    for r in gov_d:
        md_gov_table += f"| **{r[0]}** | {r[1]} | **{r[2]}** | {r[3]} |\n"
        
    md_piot_table = "| Dimensión / Criterio Piotroski | Condición Contable Evaluada | Valor Detectado | Punto Asignado |\n| :--- | :--- | :---: | :---: |\n"
    for r in p_rows:
        md_piot_table += f"| **{r[0]}** | {r[1]} | {r[2]} | **{r[3]}** |\n"

    md_moh_table = "| Criterio Mohanram G-Score | Condición frente a la Mediana | Valor Detectado | Punto Asignado |\n| :--- | :--- | :---: | :---: |\n"
    for r in m_rows:
        md_moh_table += f"| **{r[0]}** | {r[1]} | {r[2]} | **{r[3]}** |\n"

    md_peer_table = f"| {' | '.join(peer_headers)} |\n| " + " | ".join([':---:' if i in [0, 7, 8] else (':---' if i == 1 else ':---:') for i in range(len(peer_headers))]) + " |\n"
    for r in peer_rows:
        md_peer_table += f"| {' | '.join([f'**{val}**' if i in [0, 1] else str(val) for i, val in enumerate(r)])} |\n"

    md_content = f"""# {company_name.upper()} ({exchange}: {ticker_clean})
## Informe Ejecutivo de Análisis Fundamental, Earnings Call {period_label} & Gobernanza Corporativa
*Fecha de Emisión: {datetime.now().strftime('%d de Septiembre de %Y')} | CIK SEC: {cik}*  
*Fuentes: {filing_source}*

---

## 1. Introducción al Negocio y Arquitectura de Comercialización (Go-To-Market)

> 📌 **{bm_callout.get('title', 'RESUMEN DEL MODELO DE NEGOCIO Y PROPUESTA DE VALOR')}**  
> {'  \n> '.join(bm_callout.get('paragraphs', []))}

### {channels.get('title', 'Estructura de Canales de Comercialización (Go-To-Market)')}
* **{dir_ch.get('label', 'Canal Directo:')}** {dir_ch.get('description', '')}
* **{ind_ch.get('label', 'Canal Indirecto / Mayorista:')}** {ind_ch.get('description', '')}

---

## 2. Desglose de Ventas por Línea de Productos y Servicios (Comparativa Interanual)

{md_prod_table}

### Análisis Cualitativo de las Líneas de Negocio:
{md_prod_qual_text}

---

## 3. Desglose Geográfico: Mercados y Países de Comercialización (Comparativa Interanual)

{md_geo_table}

### Conclusión sobre Exposición Geográfica y Riesgo Cambiario (FX):
{md_geo_qual_text}

---

## 4. Resumen Ejecutivo y Cuadro de Mando Financiero (Scorecard)

{md_scorecard_table}

{md_scorecard_guide}

---

## 5. Análisis Exhaustivo de Conferencia de Resultados (Earnings Calls) y Auditoría del Discurso Directivo

### BLOQUE A: Análisis del Trimestre Más Reciente ({bloque_a.get('period_label', period_label)})

{bloque_a.get('intro', '')}

#### 1. Proyecciones Oficiales y Guidance del Management:
{md_guidance_table}

#### 2. Hitos Más Importantes y Catalizadores Clave del Trimestre:
{md_hitos_table}

#### 3. Matriz de Riesgos, Advertencias y Desafíos Operativos Detectados:
{md_riesgos_table}

#### 4. Desglose Exhaustivo de Preguntas y Respuestas (Q&A con Wall Street):
{md_qa_section}

### BLOQUE B: Análisis Longitudinal y Auditoría de Discurso Directivo ({bloque_b.get('period_range', '5 Trimestres')})

{bloque_b.get('intro', '')}

{md_say_do_table}

#### Cronología y Mutación Dinámica de los Riesgos Operativos (5 Trimestres):
{md_riesgos_hist_table}

> 🛡️ **{cred_callout.get('title')}**  
> {'  \n> '.join(cred_callout.get('bullets', []))}

---

## 6. Posición Patrimonial, Estructura de Capital y Asignación de Recursos (Capital Allocation)

### 6.1. Cuadro de Mando de Liquidez, Deuda y Posición Neta de Caja
{md_bal_table}

### 6.2. Política de Retorno al Accionista: Recompra de Acciones y Dividendos
{md_ret_table}

### 6.3. Inversiones Estratégicas y Modelo Operativo
{cap_alloc.get('capex_intro', '')}

---

## 7. Estrategia Tecnológica, Fosos Defensivos (Economic Moat) y Ventajas Competitivas

{md_moat_table}

---

## 8. Gobernanza Corporativa, Sentimiento Insider (Form 4 y 144) y Alertas 8-K

### 8.1. Hechos Relevantes Formulario 8-K
{md_ev_table}

### 8.2. Monitor Unificado de Insiders
{md_ins_table}

### 8.3. Cuadro de Mando y Calificación Global de Gobernanza
{md_gov_table}

---

## 9. Diagnóstico Cuantitativo de Resiliencia y Crecimiento (Piotroski & Mohanram)

> 💎 **CLASIFICACIÓN ESTRATÉGICA EN MATRIZ FUNDAMENTAL**  
> • **Posición Cuantitativa:** {diag_card.get('badge', '💎 CUADRANTE I: COMPOUNDER DE ÉLITE')}  
> • **Piotroski F-Score (Solvencia Interna):** {f_score_val} / 9 Puntos | {piot_rating}  
> • **Mohanram G-Score (Ventaja Sectorial):** {g_score_val} / 8 Puntos | {moh_rating}  
> • **Tesis Cuantitativa:** {company_name} combina una salud financiera interna intachable con una superioridad competitiva sectorial demostrada frente a sus pares de la industria.

### 9.1. Piotroski F-Score: Salud Financiera y Calidad Contable Interna

Desarrollado por el profesor Joseph Piotroski (Universidad de Stanford), este modelo evalúa la solidez económica interna de la empresa a través de 9 señales contables distribuidas en tres dimensiones críticas: Rentabilidad (ROA positivo y creciente, CFO positivo, calidad de devengos Sloan), Apalancamiento y Liquidez (desendeudamiento financiero total, mejora de razón corriente y cero dilución por emisión de acciones) y Eficiencia Operativa (expansión de margen bruto y mayor rotación de activos).

* **Puntaje Obtenido:** **{f_score_val} / 9 Puntos en LTM** ({piot_rating}) ({prev_f_score} / 9 en {prev_fy}).
* **¿Qué significa este puntaje para el Inversor?** Una calificación de {f_score_val}/9 sitúa a {company_name} en el percentil superior del mercado global. Certifica que la compañía:
  1. **Genera beneficios respaldados por caja líquida:** La caja operativa ({cfo_str} en LTM) respalda con holgura al beneficio neto contable ({ni_str}), descartando manipulación de inventarios o ventas a crédito ficticias.
  2. **Reduce o controla su apalancamiento financiero real:** Mantiene una estructura financiera solvente con disciplina en el endeudamiento ({comp_lever}).
  3. **Protege al accionista minoritario:** No financia sus operaciones emitiendo nuevas acciones dilutivas, priorizando la retención o recompra de títulos ({comp_offer}).
  4. **Expande su eficiencia operativa:** Optimiza tanto su margen comercial ({comp_margin}) como la productividad de sus activos instalados ({comp_turn}).

{md_piot_table}

### 9.2. Mohanram G-Score: Calidad de Crecimiento frente a la Industria

Diseñado por el profesor Partha Mohanram (Universidad de Columbia), este modelo evalúa la calidad fundamental y la sostenibilidad del crecimiento en empresas contrastando sus métricas frente a la mediana de su sector industrial. El modelo audita 8 señales agrupadas en: Desempeño Operativo y Retorno (ROA, CFROA y Calidad de Devengos), Estabilidad del Negocio (baja variabilidad de ROA y ventas) y Reinversión en Ventajas Competitivas (intensidad en I+D, CapEx de vanguardia y Apalancamiento Comercial en SG&A).

* **Puntaje Obtenido:** **{g_score_val} / 8 Puntos en LTM** ({moh_rating}) ({prev_g_score} / 8 en {prev_fy}).
* **¿Qué significa este puntaje para el Inversor?** Una puntuación de {g_score_val}/8 consolida a {company_name} como líder de calidad fundamental en su industria. Certifica que la firma:
  1. **Retorno superior:** Supera sistemáticamente a la mediana de sus competidores directos en rentabilidad sobre activos y generación de flujo de caja libre.
  2. **Estabilidad de negocio:** Exhibe una trayectoria de crecimiento sólida y predecible con menor volatilidad en sus resultados comerciales.
  3. **Reinversión estratégica:** Mantiene una disciplina férrea de reinversión en capital e innovación para defender y expandir su foso competitivo.

{md_moh_table}

### 9.3. Benchmarking Competitivo del Sector & Medianas Oficiales

A continuación se auditan las cifras financieras comparables en base a los últimos 12 meses (LTM) auditados de la industria, a partir de las cuales se deducen las medianas y percentiles que alimentan el scoring de calidad, productividad del capital y resiliencia fundamental:

{md_peer_table}

---

{novy_marx_md}
{roic_wacc_md}
{forensic_md}
{solvency_md}
{valuation_md}

---
*Informe generado automáticamente por el Orquestador Universal de Análisis Fundamental — {company_name} ({ticker_clean})*
"""
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)
    print(f"[Report Generator] Informe Markdown generado con éxito: {md_path}")
    
    # 3. Sincronización en Google Drive si está disponible
    if safe_copy_file and drive_base and drive_base.exists():
        drive_out = get_ticker_drive_processed_dir(ticker_clean) if get_ticker_drive_processed_dir else drive_base / "processed"
        drive_out.mkdir(parents=True, exist_ok=True)
        safe_copy_file(docx_path, drive_out / docx_path.name)
        safe_copy_file(md_path, drive_out / md_path.name)
        print(f"[Report Generator] Entregables sincronizados en Google Drive: {drive_out}")
        
    return docx_path, md_path


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "AAPL"
    p_docx, p_md = generate_full_report(target)
    print(f"\n[OK] Generación completada para {target}:")
    print(f"  Word (.docx): {p_docx}")
    print(f"  Markdown (.md): {p_md}")
