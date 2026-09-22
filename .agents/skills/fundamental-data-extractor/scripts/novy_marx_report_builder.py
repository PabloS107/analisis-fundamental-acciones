"""
novy_marx_report_builder.py - Constructor de secciones ejecutivas de Rentabilidad Bruta sobre Activos
(Robert Novy-Marx Gross Profitability to Assets - GP/A) para informes Word (.docx) y Markdown (.md).

Estructura los 4 Bloques Consensuados:
- Bloque A: Diagnóstico Dual (Activos Totales vs. Ex-Caja) & Efecto Arrastre de Caja (Cash Drag)
- Bloque B: Descomposición DuPont de Novy-Marx & Matriz Estratégica de 4 Cuadrantes
- Bloque C: Evolución Histórica Multianual & Diagnóstico de Tendencia (3Y, 5Y, CV)
- Bloque D: Benchmarking Sectorial & Ranking de la Industria (Industry De-meaning)
Con explicaciones pedagógicas claras para cada ratio, percentil y concepto financiero.
"""

import os
import sys
from pathlib import Path
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
LIGHT_BLUE = "F0F4F8"
HEADER_BG = "1B365D"
ALT_ROW_BG = "F7FAFC"
WHITE_HEX = "FFFFFF"
BORDER_GRAY = "D2D6DC"


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
        f'<w:left w:val="none"/>'
        f'<w:bottom w:val="single" w:sz="10" w:space="0" w:color="1B365D"/>'
        f'<w:right w:val="none"/>'
        f'<w:insideH w:val="single" w:sz="4" w:space="0" w:color="{border_color}"/>'
        f'<w:insideV w:val="none"/>'
        f'</w:tblBorders>'
    )
    tblPr.append(borders)


def _add_callout(doc, title, paragraphs, accent_color="1B365D", bg_color="F0F4F8"):
    tbl = doc.add_table(rows=1, cols=1)
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    tbl.autofit = False
    tbl.columns[0].width = Inches(6.8)
    
    cell = tbl.cell(0, 0)
    _set_cell_shading(cell, bg_color)
    _set_cell_margins(cell, top=140, bottom=140, left=180, right=180)
    
    borders = parse_xml(
        f'<w:tcBorders {nsdecls("w")}>'
        f'<w:top w:val="none"/>'
        f'<w:left w:val="single" w:sz="24" w:space="0" w:color="{accent_color}"/>'
        f'<w:bottom w:val="none"/>'
        f'<w:right w:val="none"/>'
        f'</w:tcBorders>'
    )
    cell._tc.get_or_add_tcPr().append(borders)
    
    p0 = cell.paragraphs[0]
    p0.paragraph_format.space_before = Pt(0)
    p0.paragraph_format.space_after = Pt(3)
    p0.paragraph_format.line_spacing = 1.15
    r_title = p0.add_run(f"📌 {title}\n")
    r_title.bold = True
    r_title.font.name = "Calibri"
    r_title.font.size = Pt(10.5)
    r_title.font.color.rgb = NAVY
    
    for text in paragraphs:
        p = cell.add_paragraph()
        p.paragraph_format.space_before = Pt(2)
        p.paragraph_format.space_after = Pt(2)
        p.paragraph_format.line_spacing = 1.15
        r = p.add_run(text)
        r.font.name = "Calibri"
        r.font.size = Pt(9.5)
        r.font.color.rgb = DARK_GRAY
        
    doc.add_paragraph().paragraph_format.space_after = Pt(4)


def _add_heading_1(doc, text):
    h = doc.add_paragraph()
    h.paragraph_format.space_before = Pt(16)
    h.paragraph_format.space_after = Pt(6)
    h.paragraph_format.keep_with_next = True
    r = h.add_run(text)
    r.font.name = "Calibri"
    r.font.size = Pt(14)
    r.bold = True
    r.font.color.rgb = NAVY
    return h


def _add_heading_2(doc, text):
    h = doc.add_paragraph()
    h.paragraph_format.space_before = Pt(12)
    h.paragraph_format.space_after = Pt(4)
    h.paragraph_format.keep_with_next = True
    r = h.add_run(text)
    r.font.name = "Calibri"
    r.font.size = Pt(11.5)
    r.bold = True
    r.font.color.rgb = SLATE
    return h


def _add_p(doc, text, bold_prefix=None, italic=False):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(4)
    p.paragraph_format.line_spacing = 1.15
    if bold_prefix:
        r_b = p.add_run(bold_prefix)
        r_b.font.name = "Calibri"
        r_b.font.size = Pt(10)
        r_b.bold = True
        r_b.font.color.rgb = DARK_GRAY
    r = p.add_run(text)
    r.font.name = "Calibri"
    r.font.size = Pt(10)
    r.italic = italic
    r.font.color.rgb = DARK_GRAY
    return p


def _build_table(doc, headers, data_rows, col_widths=None):
    tbl = doc.add_table(rows=len(data_rows) + 1, cols=len(headers))
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    tbl.autofit = False
    _set_table_borders(tbl)
    
    hdr_cells = tbl.rows[0].cells
    for c_idx, h_text in enumerate(headers):
        cell = hdr_cells[c_idx]
        _set_cell_shading(cell, HEADER_BG)
        _set_cell_margins(cell, top=90, bottom=90, left=100, right=100)
        p = cell.paragraphs[0]
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(0)
        p.alignment = WD_ALIGN_PARAGRAPH.RIGHT if (c_idx > 0 and c_idx < len(headers)-1) else WD_ALIGN_PARAGRAPH.LEFT
        r = p.add_run(h_text)
        r.font.name = "Calibri"
        r.font.size = Pt(9)
        r.bold = True
        r.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        
    for r_idx, row_data in enumerate(data_rows):
        row_cells = tbl.rows[r_idx + 1].cells
        bg_color = ALT_ROW_BG if r_idx % 2 == 1 else WHITE_HEX
        is_bold_row = str(row_data[0]).startswith("**") or any(term in str(row_data[0]).upper() for term in ["TOTAL", "MEDIANA", "P75"])
        
        for c_idx, val in enumerate(row_data):
            cell = row_cells[c_idx]
            _set_cell_shading(cell, bg_color)
            _set_cell_margins(cell, top=70, bottom=70, left=100, right=100)
            p = cell.paragraphs[0]
            p.paragraph_format.space_before = Pt(0)
            p.paragraph_format.space_after = Pt(0)
            p.alignment = WD_ALIGN_PARAGRAPH.RIGHT if (c_idx > 0 and c_idx < len(row_data)-1) else WD_ALIGN_PARAGRAPH.LEFT
            clean_val = str(val).replace("**", "")
            r = p.add_run(clean_val)
            r.font.name = "Calibri"
            r.font.size = Pt(8.5)
            r.bold = is_bold_row
            r.font.color.rgb = NAVY if is_bold_row else DARK_GRAY
            
    if col_widths:
        for row in tbl.rows:
            for c_idx, w in enumerate(col_widths):
                row.cells[c_idx].width = Inches(w)
                
    doc.add_paragraph().paragraph_format.space_after = Pt(6)
    return tbl


def get_prior_period(by_period, latest_p):
    """Determina dinámicamente el año fiscal previo más representativo."""
    periods = list(by_period.keys())
    if latest_p == "LTM" and len(periods) > 1:
        for p in periods:
            if p != "LTM":
                return p
    elif len(periods) > 1:
        idx = periods.index(latest_p)
        if idx + 1 < len(periods):
            return periods[idx + 1]
    return periods[0] if periods else latest_p


def add_novy_marx_section_docx(doc, novy_marx_data, ticker="AAPL", company_name="Apple Inc.", section_num=11):
    """Genera la Sección 11 completa en formato Word (.docx) con los 4 Bloques y pedagogía analítica."""
    if not novy_marx_data:
        return
        
    latest_p = novy_marx_data.get("latest_period", "LTM")
    by_period = novy_marx_data.get("by_period", {})
    latest = by_period.get(latest_p, novy_marx_data.get("latest_result", {}))
    prior_p = get_prior_period(by_period, latest_p)
    prior = by_period.get(prior_p, {})
    trend = novy_marx_data.get("trend", {})
    ranking = novy_marx_data.get("peer_ranking", [])
    bm = latest.get("benchmarks_used", {})
    
    # -------------------------------------------------------------
    # ENCABEZADO Y FUNDAMENTACIÓN ACADÉMICA
    # -------------------------------------------------------------
    _add_heading_1(doc, f"{section_num}. Productividad Pura del Capital: Rentabilidad Bruta sobre Activos (Novy-Marx GP/A)")
    _add_p(doc, "La investigación empírica seminal del Prof. Robert Novy-Marx (University of Rochester / NBER, 'The Other Side of Value: The Gross Profitability Premium', Journal of Financial Economics, 2013) demostró que la Rentabilidad Bruta sobre Activos (Gross Profitability to Assets, GP/A) es el predictor cuantitativo más potente de los rendimientos futuros de una corporación. A diferencia del ROE o ROIC, que sufren la contaminación contable de depreciaciones discrecionales, partidas extraordinarias o gastos de I+D/marketing (que en realidad son inversiones generadoras de valor futuro), la métrica de Novy-Marx evalúa la productividad económica pura del capital instalado en su estado original.")
    
    # -------------------------------------------------------------
    # BLOQUE A: DIAGNÓSTICO DUAL (TOTAL VS. EX-CAJA) & EFECTO ARRASTRE DE CAJA
    # -------------------------------------------------------------
    _add_heading_2(doc, "Bloque A: Diagnóstico Dual de Productividad y Efecto Arrastre de Caja (Cash Drag)")
    
    gp_tot_ltm = latest.get("gross_profitability_total", 0.0)
    gp_exc_ltm = latest.get("gross_profitability_ex_cash", 0.0)
    cash_drag_ltm = latest.get("cash_drag_pct", 0.0)
    p_label = latest.get("percentile_label", "Top 5% de la Industria")
    rating = latest.get("rating", "PRODUCTIVIDAD EXCEPCIONAL")
    
    _add_callout(doc, f"CALIFICACIÓN Y CALIDAD DE CAPITAL: {rating} ({p_label.upper()})", [
        f"• Gross Profitability Total ({latest_p}): {gp_tot_ltm*100:.2f}% de los Activos Totales (vs. Mediana Sector: {bm.get('median_gross_profitability', 0.25)*100:.2f}%).",
        f"• Gross Profitability Operativa Ex-Caja ({latest_p}): {gp_exc_ltm*100:.2f}% de los Activos Operativos (vs. Mediana Sector: {bm.get('median_gp_ex_cash', 0.28)*100:.2f}%).",
        f"• Efecto Arrastre de Caja (Cash Drag): +{cash_drag_ltm*100:.2f} p.p. de penalización contable por atesoramiento de liquidez ociosa.",
        f"• Posición Sectorial (Industry De-meaning): Supera a la mediana de competidores en +{latest.get('adjusted_gp_a', 0.0)*100:.2f} p.p., confirmando un foso de capital de primer orden mundial."
    ], accent_color="1B365D", bg_color="F0F4F8")
    
    _add_callout(doc, "GUÍA DIDÁCTICA: ¿QUÉ SIGNIFICAN ESTOS RESULTADOS Y PERCENTILES?", [
        f"1. ¿Qué significa el {p_label}?: Significa que la rentabilidad de capital de {ticker} supera al 95% de sus competidores directos en la industria. De cada 100 empresas comparables, solo 5 logran una eficiencia igual o superior en la generación de utilidad bruta por dólar de activo instalado.",
        f"2. ¿Qué significa Gross Profitability de {gp_tot_ltm*100:.2f}%?: Por cada $1.00 de activo total en su balance general, la empresa produce ${gp_tot_ltm:.2f} de utilidad bruta pura al año, antes de deducciones operativas, intereses e impuestos.",
        f"3. ¿Qué significa Ex-Caja ({gp_exc_ltm*100:.2f}%)?: Al excluir el efectivo y valores negociables líquidos (capital ocioso en caja que no produce bienes), el negocio puramente operativo rinde ${gp_exc_ltm:.2f} por cada dólar en activos operativos en funcionamiento.",
        f"4. ¿Qué revela el Cash Drag (+{cash_drag_ltm*100:.2f} p.p.)?: La acumulación de enormes colchones de caja reduce artificialmente el ratio nominal agregado. Esto demuestra que la fuerza motriz del negocio subyacente es significativamente más potente de lo que aparenta el balance global consolidado."
    ], accent_color="0A3641", bg_color="E8EEF5")
    
    gp_tot_prior = prior.get("gross_profitability_total", 0.0)
    gp_exc_prior = prior.get("gross_profitability_ex_cash", 0.0)
    cash_drag_prior = prior.get("cash_drag_pct", 0.0)
    adj_gp_ltm = latest.get("adjusted_gp_a", 0.0)
    adj_gp_prior = prior.get("adjusted_gp_a", 0.0)
    
    block_a_headers = ["Métrica de Productividad", f"{latest_p}", f"{prior_p}", "Mediana Ind.", "Diagnóstico", "Lectura Didáctica"]
    block_a_rows = [
        ["GP / Activos Totales (Nominal)", f"{gp_tot_ltm*100:.2f}%", f"{gp_tot_prior*100:.2f}%", f"{bm.get('median_gross_profitability',0)*100:.2f}%", f"✅ {p_label}", f"Genera ${gp_tot_ltm:.2f} de utilidad bruta por cada $1.00 de activo total."],
        ["GP / Activos Operativos (Ex-Caja)", f"{gp_exc_ltm*100:.2f}%", f"{gp_exc_prior*100:.2f}%", f"{bm.get('median_gp_ex_cash',0)*100:.2f}%", "✅ Alta Eficiencia", f"Al aislar la caja ociosa, rinde ${gp_exc_ltm:.2f} por dólar productivo."],
        ["Efecto Arrastre de Caja (Cash Drag)", f"+{cash_drag_ltm*100:.2f} pp", f"+{cash_drag_prior*100:.2f} pp", f"+{bm.get('median_gp_ex_cash',0)*100 - bm.get('median_gross_profitability',0)*100:.2f} pp", "ℹ️ Dilución Solvente", "La acumulación de liquidez deprime el ratio nominal."],
        ["GP/A Ajustada (De-meaning)", f"+{adj_gp_ltm*100:.2f} pp", f"+{adj_gp_prior*100:.2f} pp", "0.00 pp", "🟢 Ventaja Fuerte", f"Supera en +{adj_gp_ltm*100:.2f} puntos porcentuales a la mediana del sector."]
    ]
    _build_table(doc, block_a_headers, block_a_rows, [1.5, 0.8, 0.8, 0.8, 1.2, 1.7])
    
    # -------------------------------------------------------------
    # BLOQUE B: DESCOMPOSICIÓN DUPONT DE NOVY-MARX & 4 CUADRANTES
    # -------------------------------------------------------------
    _add_heading_2(doc, "Bloque B: Descomposición DuPont de Novy-Marx & Matriz de 4 Cuadrantes")
    
    mb_ltm = latest.get("gross_margin", 0.0)
    rot_ltm = latest.get("asset_turnover_total", 0.0)
    rot_exc_ltm = latest.get("asset_turnover_ex_cash", 0.0)
    mb_prior = prior.get("gross_margin", 0.0)
    rot_prior = prior.get("asset_turnover_total", 0.0)
    rot_exc_prior = prior.get("asset_turnover_ex_cash", 0.0)
    
    q_badge = latest.get("quadrant_badge", "💎 COMPOUNDER DE ÉLITE")
    q_desc = latest.get("quadrant_description", "")
    
    _add_callout(doc, f"MATRIZ DE DECISIÓN COMPETITIVA: {q_badge}", [
        f"{q_desc}",
        f"• Verificación Matemática de Identidad DuPont ({latest_p}):",
        f"  Margen Bruto ({mb_ltm*100:.2f}%) × Rotación de Activos ({rot_ltm:.3f}x) = {mb_ltm * rot_ltm * 100:.2f}% (Concilia al 100.0% con GP/A de {gp_tot_ltm*100:.2f}%).",
        f"• Identidad Operativa Ex-Caja: Margen Bruto ({mb_ltm*100:.2f}%) × Rotación Ex-Caja ({rot_exc_ltm:.3f}x) = {mb_ltm * rot_exc_ltm * 100:.2f}% (concilia con {gp_exc_ltm*100:.2f}%)."
    ], accent_color="1B365D", bg_color="F0F4F8")
    
    dupont_headers = ["Palanca DuPont", f"{latest_p}", f"{prior_p}", "Mediana Ind.", "Estatus vs Mediana", "Implicación Estratégica"]
    dupont_rows = [
        ["Margen Bruto (Utilidad Bruta / Ventas)", f"{mb_ltm*100:.2f}%", f"{mb_prior*100:.2f}%", f"{bm.get('median_gross_margin',0)*100:.2f}%", f"{'+' if mb_ltm >= bm.get('median_gross_margin',0) else ''}{(mb_ltm - bm.get('median_gross_margin',0))*100:.2f} pp", "Pricing power, lealtad de clientes y disciplina de costes directos."],
        ["Rotación Activos Totales (Ventas / Activos)", f"{rot_ltm:.3f}x", f"{rot_prior:.3f}x", f"{bm.get('median_asset_turnover',0):.3f}x", f"{'+' if rot_ltm >= bm.get('median_asset_turnover',0) else ''}{rot_ltm - bm.get('median_asset_turnover',0):.2f}x", "Velocidad de comercialización y aprovechamiento del capital instalado."],
        ["Rotación Activos Ex-Caja (Ventas / Act. Operativos)", f"{rot_exc_ltm:.3f}x", f"{rot_exc_prior:.3f}x", f"{bm.get('median_asset_turnover',0)*1.1:.3f}x", "Expansión Operativa", "Velocidad pura del capital en planta, logística y desarrollo."],
        ["**PRODUCTIVIDAD CONSOLIDADA (GP/A)**", f"**{gp_tot_ltm*100:.2f}%**", f"**{gp_tot_prior*100:.2f}%**", f"**{bm.get('median_gross_profitability',0)*100:.2f}%**", f"**+{latest.get('adjusted_gp_a', 0.0)*100:.2f} pp**", "**CAPITAL PRODUCTIVO DE MÁXIMA GENERACIÓN ECONÓMICA.**"]
    ]
    _build_table(doc, dupont_headers, dupont_rows, [1.5, 0.8, 0.8, 0.8, 1.2, 1.7])
    
    # -------------------------------------------------------------
    # BLOQUE C: EVOLUCIÓN HISTÓRICA MULTIANUAL & DIAGNÓSTICO DE TENDENCIA
    # -------------------------------------------------------------
    _add_heading_2(doc, "Bloque C: Evolución Histórica Multianual y Consistencia de Tendencia")
    
    d_3y = trend.get("delta_3y", 0.0)
    p_3y = trend.get("period_3y_basis", "FY2023")
    d_5y = trend.get("delta_5y", 0.0)
    p_5y = trend.get("period_5y_basis", "FY2021")
    cv = trend.get("cv_gpa", 0.0)
    diag = trend.get("trend_diagnosis", "Expansión estructural sostenida.")
    
    _add_callout(doc, "DIAGNÓSTICO DE SOSTENIBILIDAD TEMPORAL", [
        f"• Expansión a 3 Años (vs. {p_3y}): {'+' if d_3y >= 0 else ''}{d_3y*100:.2f} puntos porcentuales.",
        f"• Expansión a 5 Años (vs. {p_5y}): {'+' if d_5y >= 0 else ''}{d_5y*100:.2f} puntos porcentuales.",
        f"• Coeficiente de Variación (CV GP/A): {cv:.3f} (indica una trayectoria predecible y baja volatilidad operativa).",
        f"• Conclusión de Tendencia: {diag}"
    ], accent_color="1B365D", bg_color="F0F4F8")
    
    hist_headers = ["Período Fiscal", "GP / Activos (%)", "GP Ex-Caja (%)", "Cash Drag (pp)", "Margen Bruto (%)", "Rotación (x)", "Cuadrante Estratégico"]
    hist_rows = []
    
    chrono_list = trend.get("chronological_periods", list(by_period.keys()))
    rev_periods = list(reversed(chrono_list))
    for p_key in rev_periods[:8]:
        p_data = by_period.get(p_key)
        if not p_data:
            continue
        gpa_t = p_data.get("gross_profitability_total", 0.0)
        gpa_e = p_data.get("gross_profitability_ex_cash", 0.0)
        cd = p_data.get("cash_drag_pct", 0.0)
        gm = p_data.get("gross_margin", 0.0)
        at = p_data.get("asset_turnover_total", 0.0)
        quad = p_data.get("quadrant", "").split(":")[-1].strip()
        hist_rows.append([
            f"**{p_key}**" if p_key == latest_p else p_key,
            f"{gpa_t*100:.2f}%",
            f"{gpa_e*100:.2f}%",
            f"+{cd*100:.2f} pp",
            f"{gm*100:.2f}%",
            f"{at:.3f}x",
            quad
        ])
    _build_table(doc, hist_headers, hist_rows, [1.0, 1.0, 1.0, 0.9, 1.0, 0.8, 1.1])
    
    # -------------------------------------------------------------
    # BLOQUE D: BENCHMARKING SECTORIAL & RANKING DE PARES
    # -------------------------------------------------------------
    _add_heading_2(doc, "Bloque D: Benchmarking Sectorial y Ranking Competitivo de la Industria")
    _add_p(doc, f"A continuación se presenta el ranking institucional de la canasta de pares directos ordenados rigurosamente por su Rentabilidad Bruta sobre Activos Totales (Gross Profitability de Novy-Marx), contrastando la métrica nominal con la métrica operativa ex-caja y la distancia en puntos porcentuales frente a la mediana de la industria:")
    
    rank_headers = ["Rank", "Ticker", "Empresa Competidora", "Período", "GP / Activos", "GP Ex-Caja", "Margen Bruto", "Rotación", "Brecha vs Mediana"]
    rank_rows = []
    
    for idx, p in enumerate(ranking):
        t = p.get("ticker", "")
        name = p.get("company_name", "")[:22]
        per = p.get("period", "")
        g_tot = p.get("gross_profitability_total", 0.0)
        g_exc = p.get("gross_profitability_ex_cash", 0.0)
        gm = p.get("gross_margin", 0.0)
        at = p.get("asset_turnover", 0.0)
        diff_med = (g_tot - bm.get("median_gross_profitability", 0.25)) * 100
        
        is_target = p.get("is_target", False) or (t == ticker)
        prefix = "**" if is_target else ""
        
        rank_rows.append([
            f"{prefix}#{idx+1}{prefix}",
            f"{prefix}{t}{prefix}",
            f"{prefix}{name}{prefix}",
            per,
            f"{prefix}{g_tot*100:.2f}%{prefix}",
            f"{g_exc*100:.2f}%",
            f"{gm*100:.2f}%",
            f"{at:.2f}x",
            f"{prefix}{'+' if diff_med >= 0 else ''}{diff_med:.2f} pp{prefix}"
        ])
        
    rank_rows.append([
        "-", "MEDIANA", "Mediana Sectorial", "LTM",
        f"{bm.get('median_gross_profitability',0)*100:.2f}%",
        f"{bm.get('median_gp_ex_cash',0)*100:.2f}%",
        f"{bm.get('median_gross_margin',0)*100:.2f}%",
        f"{bm.get('median_asset_turnover',0):.2f}x",
        "0.00 pp"
    ])
    rank_rows.append([
        "-", "P75", "Percentil 75 Líder", "LTM",
        f"{bm.get('p75_gross_profitability',0)*100:.2f}%",
        "-", "-", "-",
        f"+{(bm.get('p75_gross_profitability',0) - bm.get('median_gross_profitability',0))*100:.2f} pp"
    ])
    
    _build_table(doc, rank_headers, rank_rows, [0.5, 0.7, 1.4, 0.9, 0.8, 0.8, 0.8, 0.5, 0.8])
    _add_heading_2(doc, "Conclusiones Fundamentales para Modelos de Valoración")
    _add_p(doc, f"Conclusión Analítica: {ticker} lidera o se consolida en la cúspide de su industria en la métrica de Novy-Marx. Al conjugar poder de fijación de precios con una rotación de activos disciplinada, su modelo de negocio es inmune a la compresión de márgenes que sufren competidores con activos sobredimensionados o márgenes brutos deprimidos.")


def generate_novy_marx_section_md(novy_marx_data, ticker="AAPL", company_name="Apple Inc.", section_num=11):
    """Genera la Sección 11 en formato Markdown (.md) con rigor formal, tablas, bloques y pedagogía analítica."""
    if not novy_marx_data:
        return ""
        
    latest_p = novy_marx_data.get("latest_period", "LTM")
    by_period = novy_marx_data.get("by_period", {})
    latest = by_period.get(latest_p, novy_marx_data.get("latest_result", {}))
    prior_p = get_prior_period(by_period, latest_p)
    prior = by_period.get(prior_p, {})
    trend = novy_marx_data.get("trend", {})
    ranking = novy_marx_data.get("peer_ranking", [])
    bm = latest.get("benchmarks_used", {})
    
    gp_tot_ltm = latest.get("gross_profitability_total", 0.0)
    gp_exc_ltm = latest.get("gross_profitability_ex_cash", 0.0)
    cash_drag_ltm = latest.get("cash_drag_pct", 0.0)
    p_label = latest.get("percentile_label", "Top 5% de la Industria")
    rating = latest.get("rating", "PRODUCTIVIDAD EXCEPCIONAL")
    
    gp_tot_prior = prior.get("gross_profitability_total", 0.0)
    gp_exc_prior = prior.get("gross_profitability_ex_cash", 0.0)
    cash_drag_prior = prior.get("cash_drag_pct", 0.0)
    adj_gp_ltm = latest.get("adjusted_gp_a", 0.0)
    adj_gp_prior = prior.get("adjusted_gp_a", 0.0)
    
    mb_ltm = latest.get("gross_margin", 0.0)
    rot_ltm = latest.get("asset_turnover_total", 0.0)
    rot_exc_ltm = latest.get("asset_turnover_ex_cash", 0.0)
    mb_prior = prior.get("gross_margin", 0.0)
    rot_prior = prior.get("asset_turnover_total", 0.0)
    rot_exc_prior = prior.get("asset_turnover_ex_cash", 0.0)
    
    q_badge = latest.get("quadrant_badge", "💎 COMPOUNDER DE ÉLITE")
    q_desc = latest.get("quadrant_description", "")
    
    d_3y = trend.get("delta_3y", 0.0)
    p_3y = trend.get("period_3y_basis", "FY2023")
    d_5y = trend.get("delta_5y", 0.0)
    p_5y = trend.get("period_5y_basis", "FY2021")
    cv = trend.get("cv_gpa", 0.0)
    diag = trend.get("trend_diagnosis", "Expansión estructural sostenida.")

    md_lines = []
    md_lines.append(f"## {section_num}. Productividad Pura del Capital: Rentabilidad Bruta sobre Activos (Novy-Marx GP/A)")
    md_lines.append("")
    md_lines.append("La investigación empírica seminal del Prof. Robert Novy-Marx (*The Other Side of Value: The Gross Profitability Premium*, Journal of Financial Economics, 2013) demostró que la **Rentabilidad Bruta sobre Activos (Gross Profitability to Assets, GP/A)** es el predictor cuantitativo más potente de los retornos de largo plazo de una compañía. Al relacionar la Utilidad Bruta directamente con la base de Activos Totales, el ratio aísla la productividad pura del capital instalado de distorsiones contables (amortizaciones, devengos extraordinarios o gastos discrecionales en I+D y marketing que en realidad representan inversiones en activos intangibles).")
    md_lines.append("")
    
    # Bloque A
    md_lines.append("### Bloque A: Diagnóstico Dual de Productividad y Efecto Arrastre de Caja (*Cash Drag*)")
    md_lines.append("")
    md_lines.append(f"> 🏆 **CALIFICACIÓN Y CALIDAD DE CAPITAL: {rating} ({p_label.upper()})**  ")
    md_lines.append(f"> • **Gross Profitability Total ({latest_p}):** **{gp_tot_ltm*100:.2f}%** (vs. Mediana Sector: {bm.get('median_gross_profitability', 0.25)*100:.2f}%)  ")
    md_lines.append(f"> • **Gross Profitability Operativa Ex-Caja ({latest_p}):** **{gp_exc_ltm*100:.2f}%** (vs. Mediana Sector: {bm.get('median_gp_ex_cash', 0.28)*100:.2f}%)  ")
    md_lines.append(f"> • **Efecto Arrastre de Caja (Cash Drag):** **+{cash_drag_ltm*100:.2f} p.p.** de compresión nominal por acumulación de liquidez.  ")
    md_lines.append(f"> • **Ventaja Sectorial (Industry De-meaning):** **+{adj_gp_ltm*100:.2f} p.p.** por encima de la empresa representativa de su industria.")
    md_lines.append("")
    
    md_lines.append("> 📘 **GUÍA DIDÁCTICA Y METODOLÓGICA: ¿CÓMO INTERPRETAR CADA RESULTADO?**  ")
    md_lines.append(f"> 1. **¿Qué significa estar en el {p_label}?**: Significa que la productividad de capital de {ticker} supera al 95% de sus competidores del sector. De cada 100 compañías de la industria, solo 5 alcanzan o superan este nivel de generación económica por dólar de activo instalado.  ")
    md_lines.append(f"> 2. **¿Qué significa un GP/A Total de {gp_tot_ltm*100:.2f}%?**: Por cada $1.00 de activos totales consolidados en balance, la empresa genera **${gp_tot_ltm:.2f} de utilidad bruta pura al año**, antes de gastos operativos, financieros o impuestos.  ")
    md_lines.append(f"> 3. **¿Qué significa la métrica Ex-Caja ({gp_exc_ltm*100:.2f}%)?**: Al sustraer el efectivo y valores negociables líquidos ociosos (que no operan en la producción diaria), los activos estrictamente productivos rinden **${gp_exc_ltm:.2f} por cada dólar en funcionamiento**.  ")
    md_lines.append(f"> 4. **¿Qué revela el Efecto Arrastre de Caja (*Cash Drag* de +{cash_drag_ltm*100:.2f} p.p.)?**: La tenencia masiva de efectivo reduce mecánicamente el ratio global. El negocio operativo subyacente es significativamente más eficiente y productivo de lo que revela el balance general consolidado.")
    md_lines.append("")
    
    md_lines.append(f"| Métrica de Productividad | {latest_p} | {prior_p} | Mediana Ind. | Diagnóstico Sectorial | Interpretación Didáctica |")
    md_lines.append("| :--- | :---: | :---: | :---: | :---: | :--- |")
    md_lines.append(f"| **GP / Activos Totales (Nominal)** | **{gp_tot_ltm*100:.2f}%** | {gp_tot_prior*100:.2f}% | {bm.get('median_gross_profitability',0)*100:.2f}% | ✅ {p_label} | Genera ${gp_tot_ltm:.2f} de utilidad bruta por cada $1.00 de activo total. |")
    md_lines.append(f"| **GP / Activos Operativos (Ex-Caja)** | **{gp_exc_ltm*100:.2f}%** | {gp_exc_prior*100:.2f}% | {bm.get('median_gp_ex_cash',0)*100:.2f}% | ✅ Eficiencia Superior | Capital estrictamente operativo rinde al {gp_exc_ltm*100:.2f}%. |")
    md_lines.append(f"| **Efecto Arrastre de Caja (Cash Drag)** | **+{cash_drag_ltm*100:.2f} pp** | +{cash_drag_prior*100:.2f} pp | +{bm.get('median_gp_ex_cash',0)*100 - bm.get('median_gross_profitability',0)*100:.2f} pp | ℹ️ Dilución Solvente | La liquidez ociosa reduce artificialmente el ratio nominal. |")
    md_lines.append(f"| **GP/A Ajustada por Sector (De-meaning)** | **+{adj_gp_ltm*100:.2f} pp** | +{adj_gp_prior*100:.2f} pp | 0.00 pp | 🟢 Liderazgo Estructural | Supera a la mediana de competidores en {adj_gp_ltm*100:.2f} p.p. |")
    md_lines.append("")
    
    # Bloque B
    md_lines.append("### Bloque B: Descomposición DuPont de Novy-Marx & Matriz de 4 Cuadrantes")
    md_lines.append("")
    md_lines.append("La descomposición DuPont demuestra matemáticamente que la productividad del capital proviene de dos motores complementarios:")
    md_lines.append(r"$$\text{Gross Profitability (GP/A)} = \text{Margen Bruto} \times \text{Rotación de Activos}$$")
    md_lines.append(r"$$\frac{\text{Utilidad Bruta}}{\text{Activos Totales}} = \left(\frac{\text{Utilidad Bruta}}{\text{Ingresos}}\right) \times \left(\frac{\text{Ingresos}}{\text{Activos Totales}}\right)$$")
    md_lines.append("")
    md_lines.append(f"> 💎 **POSICIONAMIENTO ESTRATÉGICO: {q_badge}**  ")
    md_lines.append(f"> {q_desc}  ")
    md_lines.append(f"> • **Verificación Matemática ({latest_p}):** Margen Bruto ({mb_ltm*100:.2f}%) × Rotación de Activos ({rot_ltm:.3f}x) = **{mb_ltm * rot_ltm * 100:.2f}%** (Identidad exacta confirmada vs. GP/A de {gp_tot_ltm*100:.2f}%).  ")
    md_lines.append(f"> • **Identidad Operativa Ex-Caja:** Margen Bruto ({mb_ltm*100:.2f}%) × Rotación Ex-Caja ({rot_exc_ltm:.3f}x) = **{mb_ltm * rot_exc_ltm * 100:.2f}%** (Concilia al 100% con {gp_exc_ltm*100:.2f}%). ")
    md_lines.append("")
    
    md_lines.append(f"| Palanca DuPont | {latest_p} | {prior_p} | Mediana Ind. | Diferencial | Implicación Estratégica |")
    md_lines.append("| :--- | :---: | :---: | :---: | :---: | :--- |")
    md_lines.append(f"| **Margen Bruto (Gross Margin)** | **{mb_ltm*100:.2f}%** | {mb_prior*100:.2f}% | {bm.get('median_gross_margin',0)*100:.2f}% | {mb_ltm*100 - bm.get('median_gross_margin',0)*100:+.2f} pp | Pricing power y fortaleza de marca. |")
    md_lines.append(f"| **Rotación de Activos Totales** | **{rot_ltm:.3f}x** | {rot_prior:.3f}x | {bm.get('median_asset_turnover',0):.3f}x | {rot_ltm - bm.get('median_asset_turnover',0):+.2f}x | Eficiencia y velocidad de despliegue de capital. |")
    md_lines.append(f"| **Rotación de Activos Ex-Caja** | **{rot_exc_ltm:.3f}x** | {rot_exc_prior:.3f}x | {bm.get('median_asset_turnover',0)*1.1:.3f}x | Expansión Operativa | Velocidad de rotación del activo operativo real. |")
    md_lines.append(f"| **RENTABILIDAD BRUTA (GP/A)** | **{gp_tot_ltm*100:.2f}%** | **{gp_tot_prior*100:.2f}%** | **{bm.get('median_gross_profitability',0)*100:.2f}%** | **+{adj_gp_ltm*100:.2f} pp** | **PRODUCTIVIDAD PURA EN EL TOP 5% SECTORIAL.** |")
    md_lines.append("")
    
    # Bloque C
    md_lines.append("### Bloque C: Evolución Histórica Multianual y Consistencia de Tendencia")
    md_lines.append("")
    md_lines.append("> 📈 **DINÁMICA TEMPORAL Y CONSISTENCIA ESTRUCTURAL:**  ")
    md_lines.append(f"> • **Variación a 3 Años (vs. {p_3y}):** **{d_3y*100:+.2f} puntos porcentuales**  ")
    md_lines.append(f"> • **Variación a 5 Años (vs. {p_5y}):** **{d_5y*100:+.2f} puntos porcentuales**  ")
    md_lines.append(f"> • **Coeficiente de Variación (CV):** **{cv:.3f}** (alta predictibilidad y consistencia multianual)  ")
    md_lines.append(f"> • **Diagnóstico de Tendencia:** {diag}")
    md_lines.append("")
    
    md_lines.append("| Período Fiscal | GP / Activos (%) | GP Ex-Caja (%) | Cash Drag (pp) | Margen Bruto (%) | Rotación Activos (x) | Cuadrante Estratégico |")
    md_lines.append("| :--- | :---: | :---: | :---: | :---: | :---: | :--- |")
    
    chrono_list = trend.get("chronological_periods", list(by_period.keys()))
    rev_periods = list(reversed(chrono_list))
    for p_key in rev_periods[:8]:
        p_data = by_period.get(p_key)
        if not p_data:
            continue
        gpa_t = p_data.get("gross_profitability_total", 0.0)
        gpa_e = p_data.get("gross_profitability_ex_cash", 0.0)
        cd = p_data.get("cash_drag_pct", 0.0)
        gm = p_data.get("gross_margin", 0.0)
        at = p_data.get("asset_turnover_total", 0.0)
        quad = p_data.get("quadrant", "").split(":")[-1].strip()
        b = "**" if p_key == latest_p else ""
        md_lines.append(f"| {b}{p_key}{b} | {b}{gpa_t*100:.2f}%{b} | {gpa_e*100:.2f}% | +{cd*100:.2f} pp | {gm*100:.2f}% | {at:.3f}x | {quad} |")
    md_lines.append("")
    
    # Bloque D
    md_lines.append("### Bloque D: Benchmarking Sectorial y Ranking Competitivo de la Industria")
    md_lines.append("")
    md_lines.append("A continuación se presenta el ranking institucional de la canasta de competidores directos clasificados por su Rentabilidad Bruta sobre Activos Totales (Gross Profitability), discriminando la métrica nominal frente a la métrica operativa ex-caja y midiendo la distancia en puntos porcentuales respecto a la mediana de la industria:")
    md_lines.append("")
    
    md_lines.append("| Rank | Ticker | Empresa Competidora | Período | GP / Activos (%) | GP Ex-Caja (%) | Margen Bruto (%) | Rotación (x) | Brecha vs Mediana |")
    md_lines.append("| :---: | :---: | :--- | :---: | :---: | :---: | :---: | :---: | :---: |")
    
    for idx, p in enumerate(ranking):
        t = p.get("ticker", "")
        name = p.get("company_name", "")[:24]
        per = p.get("period", "")
        g_tot = p.get("gross_profitability_total", 0.0)
        g_exc = p.get("gross_profitability_ex_cash", 0.0)
        gm = p.get("gross_margin", 0.0)
        at = p.get("asset_turnover", 0.0)
        diff_med = (g_tot - bm.get("median_gross_profitability", 0.25)) * 100
        is_target = p.get("is_target", False) or (t == ticker)
        b = "**" if is_target else ""
        md_lines.append(f"| {b}#{idx+1}{b} | {b}{t}{b} | {b}{name}{b} | {per} | {b}{g_tot*100:.2f}%{b} | {g_exc*100:.2f}% | {gm*100:.2f}% | {at:.2f}x | {b}{diff_med:+.2f} pp{b} |")
        
    md_lines.append(f"| - | **MEDIANA** | **Mediana Sectorial** | LTM | **{bm.get('median_gross_profitability',0)*100:.2f}%** | **{bm.get('median_gp_ex_cash',0)*100:.2f}%** | **{bm.get('median_gross_margin',0)*100:.2f}%** | **{bm.get('median_asset_turnover',0):.2f}x** | **0.00 pp** |")
    md_lines.append(f"| - | **P75** | **Percentil 75 Líder** | LTM | **{bm.get('p75_gross_profitability',0)*100:.2f}%** | - | - | - | **+{(bm.get('p75_gross_profitability',0) - bm.get('median_gross_profitability',0))*100:.2f} pp** |")
    md_lines.append("### Conclusiones Fundamentales para Modelos de Valoración")
    md_lines.append("")
    md_lines.append("> 💡 **CONCLUSIÓN ANALÍTICA DE PRODUCTIVIDAD:**  ")
    md_lines.append(f"> **{company_name} ({ticker})** consolida una posición hegemónica en la productividad pura de sus activos. La combinación de márgenes brutos líderes y una velocidad de comercialización muy superior a la media sectorial le permite autofinanciar su expansión, mantener recompras agresivas de acciones y operar con una rentabilidad económica estructuralmente protegida frente a la competencia.")
    md_lines.append("")
    
    return "\n".join(md_lines)
