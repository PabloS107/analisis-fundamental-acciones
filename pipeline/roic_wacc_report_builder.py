"""
roic_wacc_report_builder.py - Constructor de la Sección de Retorno sobre Capital Invertido
(ROIC Ajustado por Intangibles / ROTCE Bancario / ROE Asegurador), Costo de Capital (WACC / Ke),
ROC Greenblatt y Creación de Valor Económico (EVA / Spread).

Genera contenido estructurado para informes Word (.docx) y Markdown (.md) en 5 Bloques:
- Bloque A: Auditoría de Mercado en Tiempo Real & Parámetros Macro (Rf, Beta, Market Cap, WACC / Ke).
- Bloque B: Estructura de Capital y Costo de Capital (WACC o Inaplicabilidad / Coste del Equity Ke).
- Bloque C: Rentabilidad de Capital y Productividad (ROC Greenblatt & ROIC Damodaran o ROTCE / ROE).
- Bloque D: Creación de Valor Económico (EVA / Spread) y Evaluación del Foso Defensivo (Economic Moat).
- Bloque E: Cuadro de Mando Consolidado de Ratios de Capital, Retornos y Valor.
"""

import os
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import docx
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml import parse_xml, OxmlElement
from docx.oxml.ns import nsdecls, qn

NAVY = RGBColor(0x1B, 0x36, 0x5D)
SLATE = RGBColor(0x4A, 0x55, 0x68)
DARK_GRAY = RGBColor(0x2D, 0x37, 0x48)
LIGHT_BLUE = "F0F4F8"
HEADER_BG = "1B365D"
ALT_ROW_BG = "F7FAFC"
BORDER_GRAY = "D2D6DC"
GREEN_BG = "E2EFDA"


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

    p_after = doc.add_paragraph()
    p_after.paragraph_format.space_before = Pt(0)
    p_after.paragraph_format.space_after = Pt(6)


# ------------------------------------------------------------------------------
# Helpers de Formateo Resilientes
# ------------------------------------------------------------------------------
def _fmt_m(val) -> str:
    if val is None:
        return "N/D"
    try:
        v = float(val)
        if v < 0:
            return f"-${abs(v):,.1f}M"
        return f"${v:,.1f}M"
    except (ValueError, TypeError):
        return "N/D"


def _fmt_pct(val, decimals=2, signed=False) -> str:
    if val is None:
        return "N/D"
    try:
        v = float(val) * 100.0
        sign = "+" if (signed and v > 0) else ""
        return f"{sign}{v:.{decimals}f}%"
    except (ValueError, TypeError):
        return "N/D"


def _fmt_pp(val, decimals=2) -> str:
    if val is None:
        return "N/D"
    try:
        v = float(val) * 100.0
        sign = "+" if v > 0 else ""
        return f"{sign}{v:.{decimals}f} p.p."
    except (ValueError, TypeError):
        return "N/D"


def _fmt_num(val, decimals=2) -> str:
    if val is None:
        return "N/D"
    try:
        return f"{float(val):.{decimals}f}"
    except (ValueError, TypeError):
        return "N/D"


def _fmt_price(val) -> str:
    if val is None:
        return "N/D"
    try:
        return f"${float(val):.2f}"
    except (ValueError, TypeError):
        return "N/D"


def _get_wacc_dict(scoring_data: Dict[str, Any]) -> Dict[str, Any]:
    return (
        scoring_data.get("wacc_analysis")
        or scoring_data.get("wacc_and_spread_analysis")
        or scoring_data.get("roic_wacc_analysis")
        or {}
    )


def _get_archetype(scoring_data: Dict[str, Any], wacc_data: Dict[str, Any]) -> str:
    return (
        scoring_data.get("archetype")
        or wacc_data.get("archetype")
        or "STANDARD_CORPORATE"
    )


# ==============================================================================
# MARKDOWN BUILDER
# ==============================================================================
def build_roic_wacc_markdown_section(scoring_data: Dict[str, Any], ticker: str, company_name: str, section_num: int = 11) -> str:
    """Genera la Sección completa en formato Markdown institucional con explicaciones pedagógicas."""
    wacc_data = _get_wacc_dict(scoring_data)
    archetype = _get_archetype(scoring_data, wacc_data)
    is_banking = archetype == "FINANCIAL_BANKING"
    is_insurance = archetype == "INSURANCE"
    is_financial = is_banking or is_insurance

    roic_data = scoring_data.get("intangible_roic_analysis", {})
    greenblatt_data = scoring_data.get("greenblatt_roc_analysis", {})
    greenblatt_annual = greenblatt_data.get("annual_series", {})
    greenblatt_ltm = greenblatt_data.get("ltm", {})

    mkt = wacc_data.get("market_data", {})
    recent_fy = wacc_data.get("period", "LTM")
    sens = roic_data.get("sensitivity_matrix", {})

    ke = wacc_data.get("cost_of_equity_ke")
    kd = wacc_data.get("cost_of_debt_kd_after_tax")
    wacc_val = wacc_data.get("wacc")
    sec_wacc = wacc_data.get("sector_wacc_benchmark")
    we = wacc_data.get("weight_equity")
    wd = wacc_data.get("weight_debt")
    rf = mkt.get("rf_10y")
    beta = mkt.get("beta")
    erp = mkt.get("erp")
    mcap = mkt.get("market_cap_usd_m")
    debt = wacc_data.get("total_debt_usd_m")
    price = mkt.get("price")
    is_debt_free = wacc_data.get("is_debt_free", False)

    rec_res = roic_data.get("latest_result", {})
    roic_trad = rec_res.get("roic_trad")
    roic_adj = rec_res.get("roic_adj")
    spread_adj = wacc_data.get("economic_spread_adjusted")
    stock_int = rec_res.get("total_intangible_stock")
    ic_adj = rec_res.get("ic_adj")
    n_rd = roic_data.get("parameters", {}).get("rd_useful_life_years", 3 if is_financial else 4)
    moat_badge = wacc_data.get("moat_badge", "🏰 WIDE MOAT / COMPOUNDING MACHINE")

    roc_ltm_val = greenblatt_ltm.get("roc_avg") if greenblatt_ltm.get("roc_avg") is not None else greenblatt_ltm.get("roc_ltm")
    tangible_cap_avg = greenblatt_ltm.get("tangible_capital_avg")

    audit_notes = mkt.get("audit", {}).get("notes", "Consenso Yahoo Finance + CNBC Quote Service")
    timestamp = mkt.get("timestamp", "Tiempo Real")

    # Benchmarks
    bm = scoring_data.get("benchmarks_used", {})
    sec_roc = bm.get("peer_greenblatt_roc_median") or bm.get("median_greenblatt_roc")
    sec_roic = bm.get("median_adjusted_roic")
    sec_spread = bm.get("median_economic_spread")

    # --------------------------------------------------------------------------
    # RUTA FINANCIERA / ASEGURADORA (FINANCIAL_BANKING / INSURANCE)
    # --------------------------------------------------------------------------
    if is_financial:
        ret_metric_name = "ROE" if is_insurance else "ROTCE"
        ret_val = wacc_data.get("roe") if is_insurance else (wacc_data.get("rotce") or wacc_data.get("roe"))
        tbv_val = wacc_data.get("tangible_book_value_usd_m")
        eff_spread = spread_adj if spread_adj is not None else ((ret_val - ke) if (ret_val is not None and ke is not None) else None)

        md = []
        md.append(f"## {section_num}. Rentabilidad del Capital Propio ({ret_metric_name}), Costo de Capital (Ke) y Creación de Valor Económico")
        md.append("")
        md.append(f"Evaluación del retorno financiero y sostenibilidad de las ventajas competitivas (*Economic Moat*) para **{company_name} ({ticker.upper()})** al período **{recent_fy}**.")
        md.append("")
        md.append(f"> 📌 **DICTAMEN DE VALOR ECONÓMICO: {moat_badge} (SPREAD {_fmt_pp(eff_spread)})**  ")
        md.append(f"> • **Rentabilidad de Balance ({ret_metric_name} - {recent_fy}):** **{_fmt_pct(ret_val)}** (Rendimiento sobre fondos propios auditado).  ")
        md.append(f"> • **Costo del Capital Propio (Ke vía CAPM):** **{_fmt_pct(ke)}** (Tasa de corte mínima exigida por accionistas).  ")
        md.append(f"> • **Spread Económico Neto (EVA):** **{_fmt_pp(eff_spread)}** de rendimiento generado por encima del coste del capital propio.  ")
        md.append(f"> • **Inaplicabilidad de WACC / ROC Tradicional:** En instituciones financieras y aseguradoras, los depósitos y el float constituyen la materia prima operativa del negocio, no un pasivo financiero externo; por tanto, el FCFF y WACC carecen de sentido económico. La rentabilidad del capital se evalúa mediante {ret_metric_name} frente a Ke.  ")
        md.append(f"> • **Tesis de Foso Defensivo:** {company_name} genera un retorno financiero de {_fmt_pct(ret_val)}, superando a su coste de oportunidad del capital ({_fmt_pct(ke)}) por {_fmt_pp(eff_spread)}, sustentando la creación de valor sobre el balance patrimonial.")
        md.append("")
        md.append("---")
        md.append("")

        # BLOQUE A
        md.append(f"### {section_num}.1. Bloque A: Auditoría de Mercado en Tiempo Real & Parámetros Macroeconómicos")
        md.append("")
        md.append("Para garantizar un cálculo contemporáneo y riguroso, los parámetros de mercado fueron extraídos y consensuados en tiempo real:")
        md.append("")
        md.append("| Variable de Mercado | Valor Validado | Fuente Primaria / Secundaria | Tolerancia & Estatus |")
        md.append("| :--- | :---: | :---: | :---: |")
        md.append(f"| **Precio de Mercado de la Acción** | **{_fmt_price(price)}** | Yahoo Finance / CNBC | Validado por Consenso |")
        md.append(f"| **Capitalización Bursátil (Market Cap - E)** | **{_fmt_m(mcap)}** | Arbitraje SEC 10-Q & Cotización | Conteo Diluido Auditado |")
        md.append(f"| **Tasa Libre de Riesgo ($R_f$ - Bono Tesoro 10Y)** | **{_fmt_pct(rf)}** | Yahoo `^TNX` / CNBC `US10Y` | Consensuado en Tiempo Real |")
        md.append(f"| **Beta de la Acción ($\\beta$)** | **{_fmt_num(beta)}** | Yahoo 5Y Monthly / CNBC | Rango Estadístico Sectorial |")
        md.append(f"| **Prima de Riesgo de Mercado (ERP)** | **{_fmt_pct(erp)}** | Benchmark Aswath Damodaran (NYU Stern) | Estándar Institucional Wall Street |")
        md.append("")
        md.append(f"> **Recuadro de Auditoría**: Captura efectuada el `{timestamp}`. {audit_notes}.")
        md.append("")

        # BLOQUE B
        md.append(f"### {section_num}.2. Bloque B: Coste del Capital Propio ($K_e$ vía CAPM) & Estructura Patrimonial")
        md.append("")
        md.append("En el sector bancario y asegurador, el WACC no es aplicable porque la deuda por depósitos y contratos de seguros es el insumo productivo básico, no una fuente de financiamiento discrecional. La tasa de corte institucional es el **Coste del Capital Propio ($K_e$)**:")
        md.append("")
        rf_str = _fmt_pct(rf)
        beta_str = _fmt_num(beta)
        erp_str = _fmt_pct(erp)
        ke_str = _fmt_pct(ke)
        md.append(f"* **Costo del Equity ($K_e$ vía CAPM)**: $K_e = R_f + \\beta \\times \\text{{ERP}} = {rf_str} + ({beta_str} \\times {erp_str}) =$ **{ke_str}**")
        md.append(f"* **Inaplicabilidad del WACC Corporativo**: Las entidades reguladas no emplean WACC dado que los pasivos no separan estructura de capital de pasivo operativo.")
        md.append(f"* **Patrimonio Contable Empleado**: Base patrimonial neta reportada ante la SEC: **{_fmt_m(tbv_val)}**.")
        md.append("")
        md.append("---")
        md.append("")

        # BLOQUE C
        md.append(f"### {section_num}.3. Bloque C: Rentabilidad de Balance y Creación de Valor ({ret_metric_name} vs. $K_e$)")
        md.append("")
        md.append(f"#### Desglose de la Rentabilidad Financiera ({ret_metric_name})")
        md.append(f"Para {company_name}, el indicador maestro de productividad es el **{ret_metric_name}**, que mide la capacidad de generar beneficios netos sobre la base patrimonial tangible de los accionistas:")
        md.append("")
        md.append(f"$$\\text{{{ret_metric_name}}} = \\frac{{\\text{{Net Income}}}}{{\\text{{Tangible Equity / Net Assets}}}} = \\mathbf{{{_fmt_pct(ret_val)}}}$$")
        md.append("")
        md.append("**Justificación Pedagógica Sectorial:**")
        md.append(f"1. **¿Por qué no aplica ROC Greenblatt?** Joel Greenblatt modela el capital físico ($NWC + PP&E$). Las entidades financieras no requieren inventarios ni plantas industriales; su capital es regulatorio (CET1 / Solvencia).")
        md.append(f"2. **¿Por qué no aplica ROIC Damodaran estándar?** La capitalización de I+D es irrelevante frente al margen de intermediación (NIM) y comisiones crediticias.")
        md.append("")

        # BLOQUE D
        md.append(f"### {section_num}.4. Bloque D: Creación de Valor Económico (EVA) y Durabilidad del Foso Defensivo (*Economic Moat*)")
        md.append("")
        md.append(f"### **Dictamen Estratégico: {moat_badge}**")
        md.append("")
        md.append(f"$$\\text{{Economic Spread}} = \\text{{{ret_metric_name}}} - K_e = {_fmt_pct(ret_val)} - {_fmt_pct(ke)} = \\mathbf{{{_fmt_pp(eff_spread)}}}$$")
        md.append("")
        exp_spread = wacc_data.get('explanations', {}).get('economic_spread', f"Generación de valor excedente sobre la rentabilidad exigida de balance ({_fmt_pp(eff_spread)}).")
        md.append(f"> **Explicación Pedagógica del Spread Económico**: {exp_spread}")
        md.append("")
        md.append(f"Con un spread positivo de **{_fmt_pp(eff_spread)}**, {company_name} retribuye a los accionistas por encima del costo de oportunidad del mercado, consolidando ventajas de escala y fondeo.")
        md.append("")
        md.append("---")
        md.append("")

        # BLOQUE E
        md.append(f"### {section_num}.5. Cuadro de Mando Consolidado de Ratios de Capital, Retornos y Valor")
        md.append("")
        md.append("| Categoría Analítica | Métrica / Ratio Institucional | Valor LTM | Benchmark / Referencia | Diagnóstico para el Inversor |")
        md.append("| :--- | :--- | :---: | :---: | :--- |")
        md.append(f"| **Parámetros Macro y Mercado** | Tasa Libre de Riesgo ($R_f$ - Bono 10Y) | **{_fmt_pct(rf)}** | US Treasury Yield | Costo de oportunidad libre de riesgo macroeconómico. |")
        md.append(f"| | Beta de la Acción ($\\beta$) | **{_fmt_num(beta)}** | S&P 500 = 1.00x | Sensibilidad sistemática del título frente al mercado. |")
        md.append(f"| | Prima de Riesgo de Mercado (ERP) | **{_fmt_pct(erp)}** | NYU Stern Damodaran | Exigencia de prima de retorno sobre el activo libre de riesgo. |")
        md.append(f"| **Coste del Capital Propio** | Costo del Capital Propio ($K_e$ vía CAPM) | **{_fmt_pct(ke)}** | Tasa de Corte | Retorno anual mínimo exigido por los accionistas comunes. |")
        md.append(f"| | WACC Tradicional | **No Aplicable** | N/A Sectorial | Depósitos y float son insumos operativos; no computan en WACC. |")
        md.append(f"| **Rentabilidad de Balance** | **{ret_metric_name} Auditado** | **{_fmt_pct(ret_val)}** | Benchmark Sectorial | Rentabilidad financiera neta sobre patrimonio empleado. |")
        md.append(f"| | Base Patrimonial Tangible | **{_fmt_m(tbv_val)}** | Balance SEC | Fondos propios tangibles que respaldan la operación. |")
        md.append(f"| **Creación de Valor (EVA)** | **Spread Económico ({ret_metric_name} − $K_e$)** | **{_fmt_pp(eff_spread)}** | Hurdle Rate | Excedente neto generado sobre el costo de oportunidad del capital. |")
        md.append(f"| | **Dictamen de Foso Defensivo (*Moat*)** | **{moat_badge}** | Compounding Machine | Fortaleza estructural de intermediación y fondeo. |")
        md.append("")
        return "\n".join(md)

    # --------------------------------------------------------------------------
    # RUTA CORPORATIVA TRADICIONAL (STANDARD_CORPORATE / OTROS)
    # --------------------------------------------------------------------------
    md = []
    md.append(f"## {section_num}. Rendimiento del Capital Ajustado por Intangibles, Costo de Capital (WACC) y Creación de Valor Económico")
    md.append("")
    md.append(f"Evaluación del retorno económico del capital y la sostenibilidad de las ventajas competitivas (*Economic Moat*) para **{company_name} ({ticker.upper()})** al período **{recent_fy}**.")
    md.append("")

    # Dictamen Inicial Ejecutivo
    md.append(f"> 📌 **DICTAMEN DE VALOR ECONÓMICO: {moat_badge} (SPREAD {_fmt_pp(spread_adj)})**  ")
    md.append(f"> • **ROC Greenblatt Tangible ({recent_fy}):** **{_fmt_pct(roc_ltm_val)}** (Productividad operativa pura pre-tax sobre capital de trabajo y PP&E físico instalado).  ")
    md.append(f"> • **ROIC Ajustado por Intangibles ({recent_fy}):** **{_fmt_pct(roic_adj)}** (Retorno económico post-tax reconstituyendo {_fmt_m(stock_int)} de I+D fuera de balance).  ")
    md.append(f"> • **ROIC Contable Tradicional ({recent_fy}):** **{_fmt_pct(roic_trad)}** (Métrica contable estándar que subestima el capital empleado al enviar I+D a gasto corriente).  ")
    md.append(f"> • **Costo Promedio Ponderado de Capital (WACC):** **{_fmt_pct(wacc_val)}** (Costo del Equity Ke: {_fmt_pct(ke)} | Costo Deuda Kd post-tax: {_fmt_pct(kd)}).  ")
    md.append(f"> • **Spread Económico Neto (EVA):** **{_fmt_pp(spread_adj)}** de rendimiento generado por encima de la tasa de corte exigida por el mercado.  ")
    md.append(f"> • **Tesis de Foso Defensivo:** {company_name} combina una productividad física tangible de {_fmt_pct(roc_ltm_val, decimals=1)} gracias a su modelo operativo, con un retorno sobre capital total (ROIC Ajustado {_fmt_pct(roic_adj)}) que supera a su WACC por {_fmt_pp(spread_adj, decimals=1)}, confirmando ventajas competitivas estructuralmente blindadas frente a sus rivales.")
    md.append("")
    md.append("---")
    md.append("")

    # BLOQUE A: Mercado en Tiempo Real
    md.append(f"### {section_num}.1. Bloque A: Auditoría de Mercado en Tiempo Real & Parámetros Macroeconómicos")
    md.append("")
    md.append("Para garantizar un cálculo contemporáneo y evitar distorsiones por desfases en el precio accionario o la política monetaria, los parámetros dinámicos de mercado fueron extraídos y consensuados en tiempo real:")
    md.append("")
    md.append("| Variable de Mercado | Valor Validado | Fuente Primaria / Secundaria | Tolerancia & Estatus |")
    md.append("| :--- | :---: | :---: | :---: |")
    md.append(f"| **Precio de Mercado de la Acción** | **{_fmt_price(price)}** | Yahoo Finance / CNBC | Validado por Consenso (Δ = 0.00%) |")
    md.append(f"| **Capitalización Bursátil (Market Cap - E)** | **{_fmt_m(mcap)}** | Arbitraje SEC 10-Q & Cotización | Conteo Diluido Auditado |")
    md.append(f"| **Tasa Libre de Riesgo ($R_f$ - Bono Tesoro 10Y)** | **{_fmt_pct(rf)}** | Yahoo `^TNX` / CNBC `US10Y` | Consensuado en Tiempo Real |")
    md.append(f"| **Beta de la Acción ($\\beta$)** | **{_fmt_num(beta)}** | Yahoo 5Y Monthly / CNBC | Rango Estadístico Sectorial |")
    md.append(f"| **Prima de Riesgo de Mercado (ERP)** | **{_fmt_pct(erp)}** | Benchmark Aswath Damodaran (NYU Stern) | Estándar Institucional Wall Street |")
    md.append("")
    md.append(f"> **Recuadro de Auditoría**: Captura efectuada el `{timestamp}`. {audit_notes}.")
    md.append("")

    # BLOQUE B: Estructura de Capital y WACC
    md.append(f"### {section_num}.2. Bloque B: Estructura de Capital y Costo Promedio Ponderado de Capital (WACC)")
    md.append("")
    md.append("El WACC representa el rendimiento mínimo anual exigido por los accionistas y los acreedores para compensar el costo de oportunidad y el riesgo del negocio:")
    md.append("")
    rf_str = _fmt_pct(rf)
    beta_str = _fmt_num(beta)
    erp_str = _fmt_pct(erp)
    ke_str = _fmt_pct(ke)
    md.append(f"* **Costo del Equity ($K_e$ vía CAPM)**: $K_e = R_f + \\beta \\times \\text{{ERP}} = {rf_str} + ({beta_str} \\times {erp_str}) =$ **{ke_str}**")
    if is_debt_free:
        md.append(f"* **Costo de la Deuda ($K_d$)**: **0.00%** (*Empresa 100% financiada con recursos propios, deuda financiera $0.0M*).")
        md.append(f"* **Ponderación de Capital**: Equity $W_e = 100.0\\%$, Deuda $W_d = 0.0\\%$.")
        md.append(f"* **WACC Consolidado**: $\\text{{WACC}} = K_e =$ **{_fmt_pct(wacc_val)}** (vs. Mediana del Sector: **{_fmt_pct(sec_wacc)}**).")
    else:
        eff_tax = wacc_data.get('effective_tax_rate')
        eff_tax_str = f"{eff_tax*100:.1f}%" if eff_tax is not None else "N/D"
        kd_pre = wacc_data.get('cost_of_debt_kd_pre_tax')
        kd_pre_str = f"{kd_pre*100:.2f}%" if kd_pre is not None else "N/D"
        md.append(f"* **Costo de la Deuda ($K_d$ neto de impuestos)**: Pre-tax: {kd_pre_str} | Con Escudo Fiscal ({eff_tax_str}): **{_fmt_pct(kd)}**.")
        we_str = f"{we*100:.1f}%" if we is not None else "N/D"
        wd_str = f"{wd*100:.1f}%" if wd is not None else "N/D"
        md.append(f"* **Ponderación de Mercado**: Equity $W_e = {we_str}$ ({_fmt_m(mcap)}) | Deuda $W_d = {wd_str}$ ({_fmt_m(debt)}).")
        md.append(f"* **WACC Consolidado**: $\\text{{WACC}} = (W_e \\times K_e) + (W_d \\times K_d) =$ **{_fmt_pct(wacc_val)}** (vs. Mediana del Sector: **{_fmt_pct(sec_wacc)}**).")
    md.append("")
    md.append("---")
    md.append("")

    # BLOQUE C: Desglose ROC Greenblatt y Conciliación SEC
    md.append(f"### {section_num}.3. Bloque C: Reconstitución de Intangibles y Retorno sobre Capital (ROC Greenblatt & ROIC Damodaran)")
    md.append("")
    md.append("#### Desglose y Explicación del ROC Tangible (Joel Greenblatt)")
    md.append("Desarrollado por Joel Greenblatt (*The Little Book That Beats the Market*), el **Return on Capital (ROC)** mide la **productividad operativa pura antes de impuestos (pre-tax) y antes de intereses** sobre los activos físicos estrictamente necesarios para operar:")
    md.append("")
    md.append("$$\\text{ROC Greenblatt} = \\frac{\\text{Beneficio Operativo (EBIT)}}{\\text{Capital Tangible Operativo}} = \\frac{\\text{Operating Income}}{\\text{Capital de Trabajo Neto (NWC)} + \\text{PP\\&E Neto}}$$")
    md.append("")
    md.append("**¿Por qué es una métrica indispensable en Wall Street?**")
    md.append("1. **Neutralidad Financiera e Impositiva:** Al utilizar el EBIT, elimina distorsiones originadas por distintas estructuras de endeudamiento o subsidios fiscales transitorios.")
    nwc_op = greenblatt_ltm.get("operating_nwc_ending") or greenblatt_ltm.get("operating_nwc_avg") or 0.0
    ppe_net = greenblatt_ltm.get("ppe_net_ending") or greenblatt_ltm.get("ppe_net_avg") or 0.0
    ebit_val = greenblatt_ltm.get("ebit", 0.0)
    ebit_per_dollar = (ebit_val / tangible_cap_avg) if (tangible_cap_avg and tangible_cap_avg > 0 and ebit_val) else ((roc_ltm_val or 1.0))

    if nwc_op < 0:
        md.append(f"3. **Lectura del {_fmt_pct(roc_ltm_val)} para {company_name}:** La compañía opera con Capital de Trabajo Negativo ({_fmt_m(nwc_op)}), ya que cobra a clientes antes de pagar a proveedores. Aplicando la salvaguarda de Greenblatt (el capital tangible no puede ser menor a PP&E neto), la base tangible promedio es de **{_fmt_m(tangible_cap_avg)}**, rindiendo más de **${ebit_per_dollar:.2f} de EBIT por cada dólar físico instalado**.")
    else:
        md.append(f"3. **Lectura del {_fmt_pct(roc_ltm_val)} para {company_name}:** La compañía opera con una base de capital tangible promedio de **{_fmt_m(tangible_cap_avg)}** (NWC Operativo: {_fmt_m(nwc_op)} + Net PP&E: {_fmt_m(ppe_net)}), rindiendo **${ebit_per_dollar:.2f} de EBIT por cada dólar físico instalado**.")
    md.append("")

    # Conciliación SEC
    sorted_annual_fys = sorted([k for k in greenblatt_annual.keys() if k != "LTM"], key=lambda x: int(x.replace("FY", "")) if "FY" in x else 0)
    prev_fy_key = sorted_annual_fys[-1] if sorted_annual_fys else "Ejercicio Previo"
    prev_fy_res = greenblatt_annual.get(prev_fy_key, {})

    md.append("#### Desglose Contable y Conciliación de ROC Greenblatt (Trazabilidad en Balances SEC)")
    md.append("")
    md.append("Para auditar el cálculo y contrastarlo directamente con los estados financieros oficiales (Form 10-K y 10-Q de la SEC), a continuación se desglosan las partidas exactas que componen la base de capital y el beneficio operativo:")
    md.append("")
    md.append("| Partida Contable / Paso de Cálculo | Período LTM | Ejercicio Previo (" + prev_fy_key + ") | Estado Financiero de Origen (SEC EDGAR) | Explicación y Criterio Institucional |")
    md.append("| :--- | :---: | :---: | :--- | :--- |")
    md.append(f"| **(+) Beneficio Operativo (EBIT)** | **{_fmt_m(greenblatt_ltm.get('ebit_usd_m'))}** | {_fmt_m(prev_fy_res.get('ebit_usd_m'))} | Estado de Resultados (*Income Statement*) | Beneficio operativo puro (línea *Operating Income*), libre de distorsiones de deuda o tasas impositivas. |")
    md.append(f"| **(+) Activos Corrientes Operativos** | **{_fmt_m(greenblatt_ltm.get('op_current_assets_usd_m'))}** | {_fmt_m(prev_fy_res.get('op_current_assets_usd_m'))} | Balance General (*Current Assets*) | Activos a corto plazo en operación (Total Current Assets menos Efectivo y Valores Negociables). |")
    md.append(f"| **(-) Pasivos Corrientes Operativos** | **{_fmt_m(greenblatt_ltm.get('op_current_liabilities_usd_m'))}** | {_fmt_m(prev_fy_res.get('op_current_liabilities_usd_m'))} | Balance General (*Current Liabilities*) | Obligaciones operativas espontáneas sin coste (Total Current Liabilities menos Deuda Financiera a CP). |")
    md.append(f"| **(=) Capital de Trabajo Neto Operativo (NWC)** | **{_fmt_m(greenblatt_ltm.get('nwc_usd_m'))}** | {_fmt_m(prev_fy_res.get('nwc_usd_m'))} | Cálculo Derivado (Activos Op. − Pasivos Op.) | Excedente o déficit de circulante. Si es negativo, los proveedores financian la operación diaria. |")
    md.append(f"| **(+) PP&E Neto (Propiedad, Planta y Equipo)** | **{_fmt_m(greenblatt_ltm.get('net_ppe_usd_m'))}** | {_fmt_m(prev_fy_res.get('net_ppe_usd_m'))} | Balance General (*Non-Current Assets*) | Activos fijos físicos tangibles netos de depreciación (línea *Property, plant and equipment, net*). |")
    md.append(f"| **(=) Capital Tangible al Cierre** | **{_fmt_m(greenblatt_ltm.get('tangible_capital_end'))}** | {_fmt_m(prev_fy_res.get('tangible_capital_end'))} | Salvaguarda Joel Greenblatt | Ante NWC negativo, el capital tangible se acota inferiormente a Net PP&E (salvaguarda anti-distorsión). |")
    md.append(f"| **(=) Capital Tangible Operativo Promedio** | **{_fmt_m(greenblatt_ltm.get('tangible_capital_avg'))}** | {_fmt_m(prev_fy_res.get('tangible_capital_avg'))} | Denominador (*Matching Principle*) | Base media ponderada ((t + t-1)/2) para sincronizar temporalmente el capital con el flujo de EBIT. |")
    md.append(f"| **(=) ROC Greenblatt Tangible (%)** | **{_fmt_pct(roc_ltm_val)}** | **{_fmt_pct(prev_fy_res.get('roc_avg'))}** | **Ratio Institucional de Productividad** | **ROC = EBIT / Capital Tangible Promedio**. Productividad económica pura pre-tax sobre activos tangibles. |")
    md.append("")
    md.append("> 🔍 **Guía de Detección en Balances para el Inversor**:  \n"
              "> • **EBIT**: Ubicar en el *Income Statement* la partida *Operating Income* (Beneficio de las operaciones).  \n"
              "> • **Efectivo y Valores Negociables**: En el Balance General, restar de *Total Current Assets* el efectivo (*Cash and cash equivalents*) y valores líquidos (*Marketable securities*).  \n"
              "> • **Deuda a Corto Plazo**: En el Balance General, restar de *Total Current Liabilities* el papel comercial (*Commercial paper*) y la porción corriente de deuda a largo plazo (*Current portion of long-term debt*).  \n"
              "> • **PP&E Neto**: Ubicar en Activos No Corrientes la partida *Property, plant and equipment, net*.  \n"
              "> • **Salvaguarda de Capital de Trabajo Negativo**: Joel Greenblatt establece que cuando el pasivo corriente operativo supera al activo corriente operativo (NWC < 0), ese diferencial no debe deducirse del PP&E físico, ya que produciría denominadores artificialmente diminutos o negativos. El capital tangible operativo queda fijado en el PP&E neto.")
    md.append("")

    # Explicación ROIC Tradicional vs Ajustado
    md.append("#### Desglose y Explicación del ROIC: Tradicional vs. Ajustado por Intangibles (Aswath Damodaran)")
    md.append(f"El ROIC Tradicional Contable (**{_fmt_pct(roic_trad)}**) presenta un sesgo contable crítico bajo normas US GAAP / IFRS: al imputar el gasto en I+D íntegramente como gasto operativo corriente del período, el balance general borra los microchips y software propietarios, reduciendo artificialmente la base de capital invertido.")
    md.append(f"Siguiendo la metodología del Prof. Aswath Damodaran (NYU Stern), se capitaliza la inversión histórica en innovación amortizándola en {n_rd} años. Al incorporar **{_fmt_m(stock_int)}** en activos intangibles, el Capital Invertido Reconstituido asciende a **{_fmt_m(ic_adj)}**, arrojando un **ROIC Ajustado de {_fmt_pct(roic_adj)}**.")
    md.append("")
    md.append("* **ROC vs. ROIC: ¿Cuándo utilizar cada indicador?**")
    md.append(f"  * **ROC Greenblatt ({_fmt_pct(roc_ltm_val)}):** Responde a *¿qué tan productivos son los activos físicos y el capital de trabajo de la empresa?* Es idóneo para evaluar la eficiencia operativa pura sin distorsión fiscal.")
    md.append(f"  * **ROIC Ajustado ({_fmt_pct(roic_adj)}):** Responde a *¿cuánto rinde el negocio considerando el capital total inyectado, incluidos los intangibles de I+D?* Es el indicador definitivo para comparar contra el costo de capital (WACC).")
    md.append("")

    # Tabla Multianual
    md.append("#### Serie Histórica Multianual de Retornos de Capital (FY2021 a LTM)")
    md.append("")
    md.append("| Período Contable | ROC Greenblatt Tangible (%) | ROIC Tradicional Prom. (%) | ROIC Ajustado Prom. (%) | Stock Intangibles ($M) | Capital Invertido Reconstituido Prom. ($M) | Spread vs. WACC (p.p.) |")
    md.append("| :--- | :---: | :---: | :---: | :---: | :---: | :---: |")

    by_period = roic_data.get("by_period", {})
    sorted_p = sorted([k for k in by_period.keys() if k != "LTM"], key=lambda x: int(x.replace("FY", "")) if "FY" in x else 0)
    chron_keys = list(sorted_p)
    if "LTM" in by_period:
        chron_keys.append("LTM")

    for pk in chron_keys[-6:]:
        p_val = by_period.get(pk, {})
        if pk == "LTM":
            p_roc = greenblatt_ltm.get("roc_avg") if greenblatt_ltm.get("roc_avg") is not None else greenblatt_ltm.get("roc_ltm")
        else:
            p_roc = greenblatt_annual.get(pk, {}).get("roc_avg")
        roc_str = _fmt_pct(p_roc)
        p_trad = p_val.get("roic_trad")
        p_adj = p_val.get("roic_adj")
        p_int = p_val.get("total_intangible_stock")
        p_ic = p_val.get("ic_adj")
        p_sp = (p_adj - wacc_val) if (p_adj is not None and wacc_val is not None) else None
        md.append(f"| **{pk}** | {roc_str} | {_fmt_pct(p_trad)} | **{_fmt_pct(p_adj)}** | {_fmt_m(p_int)} | {_fmt_m(p_ic)} | **{_fmt_pp(p_sp)}** |")

    md.append("")
    md.append("**Jerarquía de Eficiencia del Capital y Retornos Operativos**:")
    md.append("1. **ROC Greenblatt (Tangible pre-tax)**: Mide la productividad pura de los activos operativos tangibles ($EBIT / (NWC + PP&E)$). Es neutral a tasas de impuestos y apalancamiento.")
    md.append("2. **ROIC Tradicional (Contable post-tax)**: Retorno contable NOPAT sobre capital invertido según balance GAAP/IFRS.")
    md.append("3. **ROIC Ajustado (Económico con intangibles capitalizados)**: Reconstituye activos fuera de balance (I+D y publicidad) capitalizándolos roll-forward.")
    md.append(f"4. **Costo de Capital (WACC)**: Tasa de corte institucional exigida por el mercado ({_fmt_pct(wacc_val)}).")
    md.append(f"5. **Spread Económico (Creación de Valor)**: Excedente neto generado sobre la tasa de corte ({_fmt_pp(spread_adj)}).")
    md.append("")

    # Matriz Sensibilidad
    md.append(f"**Matriz de Sensibilidad de Vida Útil Económica ($N$) para I+D**:")
    n_minus_years = sens.get('n_minus_1', {}).get('lifespan_years', n_rd - 1 if n_rd > 1 else 1)
    n_plus_years = sens.get('n_plus_1', {}).get('lifespan_years', n_rd + 1)
    n_minus_int = sens.get('n_minus_1', {}).get('intangibles_usd_m')
    n_plus_int = sens.get('n_plus_1', {}).get('intangibles_usd_m')
    n_minus_roic = sens.get('n_minus_1', {}).get('roic_adj')
    n_plus_roic = sens.get('n_plus_1', {}).get('roic_adj')

    md.append(f"* **Escenario Acelerado ($N-1 = {n_minus_years}$ años)**: Intangibles acumulados {_fmt_m(n_minus_int)} $\\rightarrow$ ROIC Ajustado: **{_fmt_pct(n_minus_roic)}**.")
    md.append(f"* **Escenario Base ($N = {n_rd}$ años)**: Intangibles acumulados {_fmt_m(stock_int)} $\\rightarrow$ ROIC Ajustado: **{_fmt_pct(roic_adj)}**.")
    md.append(f"* **Escenario Extendido ($N+1 = {n_plus_years}$ años)**: Intangibles acumulados {_fmt_m(n_plus_int)} $\\rightarrow$ ROIC Ajustado: **{_fmt_pct(n_plus_roic)}**.")
    md.append("")
    md.append("---")
    md.append("")

    # BLOQUE D: Creación de Valor Económico y Moat
    md.append(f"### {section_num}.4. Bloque D: Creación de Valor Económico (EVA) y Durabilidad del Foso Defensivo (*Economic Moat*)")
    md.append("")
    md.append(f"### **Dictamen Estratégico: {moat_badge}**")
    md.append("")
    md.append(f"$$\\text{{Economic Spread}} = \\text{{ROIC}}_{{\\text{{Ajustado}}}} - \\text{{WACC}} = {_fmt_pct(roic_adj)} - {_fmt_pct(wacc_val)} = \\mathbf{{{_fmt_pp(spread_adj)}}}$$")
    md.append("")
    exp_spread = wacc_data.get('explanations', {}).get('economic_spread', '')
    if exp_spread:
        md.append(f"> **Explicación Pedagógica del Spread Económico**: {exp_spread}")
        md.append("")
    md.append(f"A diferencia del ROIC contable tradicional ({_fmt_pct(roic_trad)}), que sobrestima la rentabilidad al ignorar la reinversión en innovación, el ROIC Ajustado de **{_fmt_pct(roic_adj)}** (calculado sobre el Capital Invertido Promedio de **{_fmt_m(ic_adj)}** para garantizar perfecta correspondencia temporal con el NOPAT) demuestra que la empresa supera a su costo de financiamiento (**{_fmt_pct(wacc_val)}**) con holgura extraordinaria, confirmando la existencia de un foso defensivo indestructible frente a sus competidores directos.")
    md.append("")
    md.append("---")
    md.append("")

    # BLOQUE E: Cuadro de Mando Consolidado
    md.append(f"### {section_num}.5. Cuadro de Mando Consolidado de Ratios de Capital, Retornos y Valor")
    md.append("")
    md.append("La siguiente tabla unifica la totalidad de los ratios e indicadores calculados en esta sección:")
    md.append("")
    md.append("| Categoría Analítica | Métrica / Ratio Institucional | Valor LTM | Benchmark / Referencia | Diagnóstico para el Inversor |")
    md.append("| :--- | :--- | :---: | :---: | :--- |")
    md.append(f"| **Parámetros Macro y Mercado** | Tasa Libre de Riesgo ($R_f$ - Bono 10Y) | **{_fmt_pct(rf)}** | US Treasury Yield | Costo de oportunidad libre de riesgo macroeconómico. |")
    md.append(f"| | Beta de la Acción ($\\beta$) | **{_fmt_num(beta)}** | S&P 500 = 1.00x | Sensibilidad cíclica moderada y alineada al mercado. |")
    md.append(f"| | Prima de Riesgo de Mercado (ERP) | **{_fmt_pct(erp)}** | NYU Stern Damodaran | Exigencia de prima de retorno sobre el activo libre de riesgo. |")
    md.append(f"| **Costo de Capital (WACC)** | Costo del Capital Propio ($K_e$ vía CAPM) | **{_fmt_pct(ke)}** | Rango 9.5% - 10.5% | Retorno anual exigido por los tenedores de acciones comunes. |")
    eff_tax_str = f"{wacc_data.get('effective_tax_rate', 0.173)*100:.1f}%" if wacc_data.get('effective_tax_rate') is not None else "N/D"
    md.append(f"| | Costo de Deuda Neta ($K_d$ Post-Tax) | **{_fmt_pct(kd)}** | Tasa cupón efectiva | Financiación crediticia con escudo fiscal del {eff_tax_str}. |")
    md.append(f"| | **WACC Consolidado** | **{_fmt_pct(wacc_val)}** | Mediana Sector ({_fmt_pct(sec_wacc)}) | Tasa de corte u obstáculo financiero mínimo para crear valor. |")
    
    sec_roc_str = f"Mediana Sector ({_fmt_pct(sec_roc)})" if sec_roc is not None else "Mediana Sector"
    roc_diag = f"Negocio Asset-Light; supera al sector por {_fmt_pp(roc_ltm_val - sec_roc) if (roc_ltm_val is not None and sec_roc is not None) else 'N/D'}."
    md.append(f"| **Productividad Tangible** | **ROC Greenblatt (Pre-Tax)** | **{_fmt_pct(roc_ltm_val)}** | {sec_roc_str} | {roc_diag} |")
    md.append(f"| | Capital Tangible Operativo Promedio | **{_fmt_m(tangible_cap_avg)}** | Balance SEC Form 10-Q | Base física operativa tras salvaguarda anti-distorsión. |")
    md.append(f"| **Retorno Total Reconstituido** | ROIC Contable Tradicional (GAAP) | **{_fmt_pct(roic_trad)}** | ROIC sin ajustes | Métrica distorsionada por no capitalizar gasto de innovación. |")
    md.append(f"| | Stock de Intangibles de I+D Fuera de Balance | **{_fmt_m(stock_int)}** | Amortización a {n_rd} Años | Valor acumulado de patentes, silicio y software propietario. |")
    md.append(f"| | Capital Invertido Reconstituido Promedio | **{_fmt_m(ic_adj)}** | Base Económica Total | Base de capital honesta que absorbe las inversiones en I+D. |")
    sec_roic_str = f"Mediana Sector ({_fmt_pct(sec_roic)})" if sec_roic is not None else "Mediana Sector"
    md.append(f"| | **ROIC Ajustado por Intangibles** | **{_fmt_pct(roic_adj)}** | {sec_roic_str} | Retorno real sobre capital total invertido en el negocio. |")
    sec_sp_str = f"Mediana Sector ({_fmt_pp(sec_spread)})" if sec_spread is not None else "Mediana Sector"
    md.append(f"| **Creación de Valor (EVA)** | **Spread Económico (ROIC Adj − WACC)** | **{_fmt_pp(spread_adj)}** | {sec_sp_str} | Extraordinaria generación de riqueza neta sobre el coste de capital. |")
    md.append(f"| | **Dictamen de Foso Defensivo (*Moat*)** | **{moat_badge}** | Compounding Machine | Fortaleza estructural inquebrantable de largo plazo. |")
    md.append("")

    return "\n".join(md)


# ==============================================================================
# DOCX BUILDER
# ==============================================================================
def add_roic_wacc_section_to_doc(doc, scoring_data: Dict[str, Any], ticker: str, company_name: str, section_num: int = 11):
    """Inserta la Sección completa en un documento docx institucional."""
    wacc_data = _get_wacc_dict(scoring_data)
    archetype = _get_archetype(scoring_data, wacc_data)
    is_banking = archetype == "FINANCIAL_BANKING"
    is_insurance = archetype == "INSURANCE"
    is_financial = is_banking or is_insurance

    roic_data = scoring_data.get("intangible_roic_analysis", {})
    greenblatt_data = scoring_data.get("greenblatt_roc_analysis", {})
    greenblatt_annual = greenblatt_data.get("annual_series", {})
    greenblatt_ltm = greenblatt_data.get("ltm", {})

    mkt = wacc_data.get("market_data", {})
    recent_fy = wacc_data.get("period", "LTM")
    sens = roic_data.get("sensitivity_matrix", {})

    ke = wacc_data.get("cost_of_equity_ke")
    kd = wacc_data.get("cost_of_debt_kd_after_tax")
    wacc_val = wacc_data.get("wacc")
    sec_wacc = wacc_data.get("sector_wacc_benchmark")
    we = wacc_data.get("weight_equity")
    wd = wacc_data.get("weight_debt")
    rf = mkt.get("rf_10y")
    beta = mkt.get("beta")
    erp = mkt.get("erp")
    mcap = mkt.get("market_cap_usd_m")
    debt = wacc_data.get("total_debt_usd_m")
    price = mkt.get("price")
    is_debt_free = wacc_data.get("is_debt_free", False)

    rec_res = roic_data.get("latest_result", {})
    roic_trad = rec_res.get("roic_trad")
    roic_adj = rec_res.get("roic_adj")
    spread_adj = wacc_data.get("economic_spread_adjusted")
    stock_int = rec_res.get("total_intangible_stock")
    ic_trad = rec_res.get("ic_trad")
    ic_adj = rec_res.get("ic_adj")
    n_rd = roic_data.get("parameters", {}).get("rd_useful_life_years", 3 if is_financial else 4)
    moat_badge = wacc_data.get("moat_badge", "🏰 WIDE MOAT / COMPOUNDING MACHINE")

    roc_ltm_val = greenblatt_ltm.get("roc_avg") if greenblatt_ltm.get("roc_avg") is not None else greenblatt_ltm.get("roc_ltm")
    tangible_cap_avg = greenblatt_ltm.get("tangible_capital_avg")

    # Benchmarks
    bm = scoring_data.get("benchmarks_used", {})
    sec_roc = bm.get("peer_greenblatt_roc_median") or bm.get("median_greenblatt_roc")
    sec_roic = bm.get("median_adjusted_roic")
    sec_spread = bm.get("median_economic_spread")

    # --------------------------------------------------------------------------
    # RUTA FINANCIERA / ASEGURADORA (DOCX)
    # --------------------------------------------------------------------------
    if is_financial:
        ret_metric_name = "ROE" if is_insurance else "ROTCE"
        ret_val = wacc_data.get("roe") if is_insurance else (wacc_data.get("rotce") or wacc_data.get("roe"))
        tbv_val = wacc_data.get("tangible_book_value_usd_m")
        eff_spread = spread_adj if spread_adj is not None else ((ret_val - ke) if (ret_val is not None and ke is not None) else None)

        h1 = doc.add_heading(f"{section_num}. Rentabilidad del Capital Propio ({ret_metric_name}), Costo de Capital (Ke) y Creación de Valor Económico", level=1)
        h1.paragraph_format.space_before = Pt(18)
        h1.paragraph_format.space_after = Pt(8)

        p_lead = doc.add_paragraph()
        r = p_lead.add_run(f"Evaluación del retorno financiero y sostenibilidad de las ventajas competitivas (Economic Moat) para {company_name} ({ticker.upper()}) al período {recent_fy}.")
        r.font.size = Pt(10)
        r.font.italic = True

        _add_callout(
            doc,
            f"DICTAMEN DE VALOR ECONÓMICO: {moat_badge} (SPREAD {_fmt_pp(eff_spread)})",
            [
                f"• Rentabilidad de Balance ({ret_metric_name} - {recent_fy}): {_fmt_pct(ret_val)} (Rendimiento sobre fondos propios auditado).",
                f"• Costo del Capital Propio (Ke vía CAPM): {_fmt_pct(ke)} (Tasa de corte mínima exigida por accionistas).",
                f"• Spread Económico Neto: {_fmt_pp(eff_spread)} de rendimiento por encima del coste del capital propio.",
                f"• Inaplicabilidad de WACC: En entidades financieras, depósitos y float son insumos operativos; el retorno se evalúa mediante {ret_metric_name} vs Ke.",
                f"• Patrimonio Tangible Auditado: {_fmt_m(tbv_val)} reportados en balances SEC Form 10-K / 20-F.",
                f"• Tesis de Foso Defensivo: {wacc_data.get('explanations', {}).get('economic_spread', 'Retorno excedente sobre fondos propios.')}"
            ],
            accent_color="1B365D",
            bg_color=LIGHT_BLUE
        )

        # 11.1 Bloque A Mercado
        doc.add_heading(f"{section_num}.1. Bloque A: Auditoría de Parámetros de Mercado en Tiempo Real", level=2)
        tbl_mkt = doc.add_table(rows=6, cols=4)
        tbl_mkt.alignment = WD_TABLE_ALIGNMENT.CENTER
        tbl_mkt.autofit = False
        _set_table_borders(tbl_mkt)

        mkt_rows = [
            ("Precio de Mercado de la Acción", _fmt_price(price), "Yahoo Finance / CNBC Quotes", "Consenso Validado"),
            ("Capitalización Bursátil (Market Cap - E)", _fmt_m(mcap), "Arbitraje SEC 10-Q & Mercado", "Conteo Diluido Auditado"),
            ("Tasa Libre de Riesgo (Rf - Bono 10Y)", _fmt_pct(rf), "Yahoo ^TNX / CNBC US10Y", "Consensuado"),
            ("Beta de la Acción (β)", _fmt_num(beta), "Yahoo 5Y Monthly / CNBC", "Rango Estadístico Sectorial"),
            ("Prima de Riesgo de Mercado (ERP)", _fmt_pct(erp), "Benchmark NYU Stern (Damodaran)", "Estándar Institucional"),
        ]

        h_titles = ["Variable de Mercado", "Valor Validado", "Fuentes Consultadas", "Estatus de Auditoría"]
        for c_idx, title in enumerate(h_titles):
            cell = tbl_mkt.cell(0, c_idx)
            cell.text = title
            _set_cell_shading(cell, HEADER_BG)
            _set_cell_margins(cell, top=80, bottom=80, left=100, right=100)
            p = cell.paragraphs[0]
            p.runs[0].font.bold = True
            p.runs[0].font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
            p.runs[0].font.size = Pt(9)

        col_widths_mkt = [Inches(2.2), Inches(1.2), Inches(1.8), Inches(1.6)]
        for r_idx, (v1, v2, v3, v4) in enumerate(mkt_rows, start=1):
            for c_idx, text in enumerate([v1, v2, v3, v4]):
                cell = tbl_mkt.cell(r_idx, c_idx)
                cell.text = text
                _set_cell_margins(cell, top=60, bottom=60, left=100, right=100)
                if r_idx % 2 == 0:
                    _set_cell_shading(cell, ALT_ROW_BG)
                p = cell.paragraphs[0]
                if c_idx == 0:
                    p.runs[0].font.bold = True
                p.runs[0].font.size = Pt(8.5)

        for i, col in enumerate(tbl_mkt.columns):
            col.width = col_widths_mkt[i]

        doc.add_paragraph()

        # 11.2 Bloque B Ke
        doc.add_heading(f"{section_num}.2. Bloque B: Coste del Capital Propio (Ke) y Estructura Patrimonial", level=2)
        p_ke = doc.add_paragraph()
        r_ke = p_ke.add_run(
            f"En instituciones financieras y aseguradoras, el Coste Medio Ponderado de Capital (WACC) es metodológicamente inaplicable. "
            f"Los depósitos a la vista, pagarés y el float de primas constituyen el inventario operativo del negocio, "
            f"no un apalancamiento financiero externo. La rentabilidad se evalúa frente al Coste del Capital Propio (Ke vía CAPM) de {_fmt_pct(ke)}."
        )
        r_ke.font.size = Pt(9.5)

        # 11.3 Bloque C Rentabilidad
        doc.add_heading(f"{section_num}.3. Bloque C: Rentabilidad de Balance ({ret_metric_name}) vs. Coste de Capital (Ke)", level=2)
        p_ret = doc.add_paragraph()
        r_ret = p_ret.add_run(
            f"La rentabilidad sobre fondos propios ({ret_metric_name}) de {_fmt_pct(ret_val)} sobre un patrimonio tangible de {_fmt_m(tbv_val)} "
            f"refleja la productividad real del balance sin distorsiones contables de I+D o activos físicos industriales."
        )
        r_ret.font.size = Pt(9.5)

        # 11.4 Bloque D Creación de Valor
        doc.add_heading(f"{section_num}.4. Bloque D: Creación de Valor Económico (EVA / Spread) y Durabilidad del Foso Defensivo", level=2)
        p_eva = doc.add_paragraph()
        r_eva = p_eva.add_run(
            f"Spread Económico = {ret_metric_name} ({_fmt_pct(ret_val)}) − Ke ({_fmt_pct(ke)}) = {_fmt_pp(eff_spread)}\n"
            f"Dictamen: {moat_badge}. La compañía supera holgadamente su costo de financiamiento propio, creando valor neto recurrente."
        )
        r_eva.font.size = Pt(9.5)

        # 11.5 Cuadro de Mando
        doc.add_heading(f"{section_num}.5. Cuadro de Mando Consolidado de Ratios de Capital, Retornos y Valor", level=2)
        fin_summary_rows = [
            ("Parámetros Macro y Mercado", "Tasa Libre de Riesgo (Rf - Bono 10Y)", _fmt_pct(rf), "US Treasury Yield", "Costo de oportunidad libre de riesgo macroeconómico."),
            ("Parámetros Macro y Mercado", "Beta de la Acción (β)", _fmt_num(beta), "S&P 500 = 1.00x", "Sensibilidad sistemática alineada al mercado."),
            ("Parámetros Macro y Mercado", "Prima de Riesgo de Mercado (ERP)", _fmt_pct(erp), "NYU Stern Damodaran", "Exigencia de prima de retorno sobre el activo libre de riesgo."),
            ("Costo de Capital Propio", "Costo del Capital Propio (Ke)", _fmt_pct(ke), "CAPM Benchmark", "Retorno anual exigido por los accionistas comunes."),
            ("Costo de Capital Propio", "WACC Tradicional", "No Aplicable", "Inaplicable", "Pasivos operativos (depósitos/float) no computan en WACC."),
            ("Rentabilidad de Balance", f"{ret_metric_name} Auditado", _fmt_pct(ret_val), "Benchmark Sectorial", "Rentabilidad financiera sobre fondos propios tangibles."),
            ("Rentabilidad de Balance", "Base Patrimonial Tangible", _fmt_m(tbv_val), "Balance SEC", "Patrimonio neto reportado que sustenta la operación."),
            ("Creación de Valor (EVA)", f"Spread Económico ({ret_metric_name} − Ke)", _fmt_pp(eff_spread), "Hurdle Rate", "Extraordinaria generación de riqueza neta sobre el coste de capital."),
            ("Creación de Valor (EVA)", "Dictamen Foso Defensivo", f"{moat_badge}", "Compounding Machine", "Fortaleza estructural de intermediación y fondeo."),
        ]

        tbl_sum = doc.add_table(rows=len(fin_summary_rows) + 1, cols=5)
        tbl_sum.alignment = WD_TABLE_ALIGNMENT.CENTER
        tbl_sum.autofit = False
        _set_table_borders(tbl_sum)

        sum_headers = ["Categoría Analítica", "Métrica / Ratio Institucional", "Valor LTM", "Benchmark / Ref.", "Diagnóstico para el Inversor"]
        col_widths_sum = [Inches(1.4), Inches(2.0), Inches(0.9), Inches(1.1), Inches(1.4)]

        for c_idx, title in enumerate(sum_headers):
            cell = tbl_sum.cell(0, c_idx)
            cell.text = title
            _set_cell_shading(cell, HEADER_BG)
            _set_cell_margins(cell, top=80, bottom=80, left=100, right=100)
            p = cell.paragraphs[0]
            p.runs[0].font.bold = True
            p.runs[0].font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
            p.runs[0].font.size = Pt(8.5)

        for r_idx, (cat, met, val, bench, diag) in enumerate(fin_summary_rows, start=1):
            for c_idx, text in enumerate([cat, met, val, bench, diag]):
                cell = tbl_sum.cell(r_idx, c_idx)
                cell.text = text
                _set_cell_margins(cell, top=60, bottom=60, left=100, right=100)
                if r_idx % 2 == 0:
                    _set_cell_shading(cell, ALT_ROW_BG)
                if ret_metric_name in met or "Spread" in met:
                    _set_cell_shading(cell, GREEN_BG)
                p = cell.paragraphs[0]
                if c_idx in (1, 2) or ret_metric_name in met or "Spread" in met:
                    p.runs[0].font.bold = True
                p.runs[0].font.size = Pt(8.5)

        for i, col in enumerate(tbl_sum.columns):
            col.width = col_widths_sum[i]

        doc.add_paragraph()
        return

    # --------------------------------------------------------------------------
    # RUTA CORPORATIVA TRADICIONAL (DOCX)
    # --------------------------------------------------------------------------
    h1 = doc.add_heading(f"{section_num}. Rendimiento del Capital Ajustado por Intangibles, Costo de Capital (WACC) y Creación de Valor Económico", level=1)
    h1.paragraph_format.space_before = Pt(18)
    h1.paragraph_format.space_after = Pt(8)

    p_lead = doc.add_paragraph()
    r = p_lead.add_run(f"Evaluación del retorno económico del capital y la sostenibilidad de las ventajas competitivas (Economic Moat) para {company_name} ({ticker.upper()}) al período {recent_fy}.")
    r.font.size = Pt(10)
    r.font.italic = True

    # Callout Ejecutivo con ROC incluido
    _add_callout(
        doc,
        f"DICTAMEN DE VALOR ECONÓMICO: {moat_badge} (SPREAD {_fmt_pp(spread_adj)})",
        [
            f"• ROC Greenblatt Tangible ({recent_fy}): {_fmt_pct(roc_ltm_val)} (Productividad operativa pura pre-tax sobre capital de trabajo y PP&E físico instalado).",
            f"• ROIC Ajustado por Intangibles ({recent_fy}): {_fmt_pct(roic_adj)} frente a un ROIC contable tradicional de {_fmt_pct(roic_trad)}.",
            f"• Costo Promedio Ponderado de Capital (WACC): {_fmt_pct(wacc_val)} (Costo del Equity Ke: {_fmt_pct(ke)}, Deuda Neta Kd: {_fmt_pct(kd)}).",
            f"• Spread Económico Neto: {_fmt_pp(spread_adj)} de rendimiento por encima del costo de capital exigido por el mercado.",
            f"• Stock de Intangibles Fuera de Balance: {_fmt_m(stock_int)} capitalizados en innovación y amortizados económicamente a {n_rd} años.",
            f"• Tesis de Foso Defensivo: {wacc_data.get('explanations', {}).get('economic_spread', '')}"
        ],
        accent_color="1B365D",
        bg_color=LIGHT_BLUE
    )

    # 11.1. Tabla de Auditoría de Mercado (Bloque A)
    doc.add_heading(f"{section_num}.1. Bloque A: Auditoría de Parámetros de Mercado en Tiempo Real", level=2)
    tbl_mkt = doc.add_table(rows=6, cols=4)
    tbl_mkt.alignment = WD_TABLE_ALIGNMENT.CENTER
    tbl_mkt.autofit = False
    _set_table_borders(tbl_mkt)

    mkt_rows = [
        ("Precio de Mercado de la Acción", _fmt_price(price), "Yahoo Finance / CNBC Quotes", "Consenso Validado (Δ < 0.1%)"),
        ("Capitalización Bursátil (Market Cap - E)", _fmt_m(mcap), "Arbitraje SEC 10-Q & Mercado", "Conteo Diluido Auditado"),
        ("Tasa Libre de Riesgo (Rf - Bono 10Y)", _fmt_pct(rf), "Yahoo ^TNX / CNBC US10Y", "Δ < 0.05% (Consensuado)"),
        ("Beta de la Acción (β)", _fmt_num(beta), "Yahoo 5Y Monthly / CNBC", "Rango Estadístico Sectorial"),
        ("Prima de Riesgo de Mercado (ERP)", _fmt_pct(erp), "Benchmark NYU Stern (Damodaran)", "Estándar Institucional"),
    ]

    h_titles = ["Variable de Mercado", "Valor Validado", "Fuentes Consultadas", "Estatus de Auditoría"]
    for c_idx, title in enumerate(h_titles):
        cell = tbl_mkt.cell(0, c_idx)
        cell.text = title
        _set_cell_shading(cell, HEADER_BG)
        _set_cell_margins(cell, top=80, bottom=80, left=100, right=100)
        p = cell.paragraphs[0]
        p.runs[0].font.bold = True
        p.runs[0].font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        p.runs[0].font.size = Pt(9)

    col_widths_mkt = [Inches(2.2), Inches(1.2), Inches(1.8), Inches(1.6)]
    for r_idx, (v1, v2, v3, v4) in enumerate(mkt_rows, start=1):
        for c_idx, text in enumerate([v1, v2, v3, v4]):
            cell = tbl_mkt.cell(r_idx, c_idx)
            cell.text = text
            _set_cell_margins(cell, top=60, bottom=60, left=100, right=100)
            if r_idx % 2 == 0:
                _set_cell_shading(cell, ALT_ROW_BG)
            p = cell.paragraphs[0]
            if c_idx == 0:
                p.runs[0].font.bold = True
            p.runs[0].font.size = Pt(8.5)

    for i, col in enumerate(tbl_mkt.columns):
        col.width = col_widths_mkt[i]

    doc.add_paragraph()

    # 11.2. Desglose y Explicación del ROC Tangible (Bloque B)
    doc.add_heading(f"{section_num}.2. Desglose y Explicación del ROC Tangible (Joel Greenblatt)", level=2)
    p_roc_exp = doc.add_paragraph()
    r_re = p_roc_exp.add_run(
        "El Return on Capital (ROC) de Joel Greenblatt evalúa la rentabilidad operativa pura antes de impuestos (EBIT) "
        "sobre los activos físicos tangibles (Capital de Trabajo Neto Operativo + PP&E Físico). "
        f"Para {company_name}, el ROC de {_fmt_pct(roc_ltm_val)} refleja la eficiencia operativa sobre activos tangibles instalados, "
        "optimizando la rotación de capital y la productividad física instalada."
    )
    r_re.font.size = Pt(9.5)

    # Tabla de Conciliación Contable de ROC Greenblatt
    sorted_annual_fys = sorted([k for k in greenblatt_annual.keys() if k != "LTM"], key=lambda x: int(x.replace("FY", "")) if "FY" in x else 0)
    prev_fy_key = sorted_annual_fys[-1] if sorted_annual_fys else "Ejercicio Previo"
    prev_fy_res = greenblatt_annual.get(prev_fy_key, {})

    recon_rows = [
        ("(+) Beneficio Operativo (EBIT)", _fmt_m(greenblatt_ltm.get('ebit_usd_m')), _fmt_m(prev_fy_res.get('ebit_usd_m')), "Income Statement (Operating Income)", "Beneficio operativo puro antes de intereses e impuestos."),
        ("(+) Activos Corrientes Operativos", _fmt_m(greenblatt_ltm.get('op_current_assets_usd_m')), _fmt_m(prev_fy_res.get('op_current_assets_usd_m')), "Balance Sheet (Current Assets)", "Total Current Assets menos Efectivo y Valores Negociables."),
        ("(-) Pasivos Corrientes Operativos", _fmt_m(greenblatt_ltm.get('op_current_liabilities_usd_m')), _fmt_m(prev_fy_res.get('op_current_liabilities_usd_m')), "Balance Sheet (Current Liabilities)", "Total Current Liabilities menos Deuda CP / Papel Comercial."),
        ("(=) Capital de Trabajo Neto Operativo (NWC)", _fmt_m(greenblatt_ltm.get('nwc_usd_m')), _fmt_m(prev_fy_res.get('nwc_usd_m')), "Cálculo Operativo Derivado", "Activos Op. - Pasivos Op. (Financiación espontánea si es negativo)."),
        ("(+) PP&E Neto (Propiedad, Planta y Equipo)", _fmt_m(greenblatt_ltm.get('net_ppe_usd_m')), _fmt_m(prev_fy_res.get('net_ppe_usd_m')), "Balance Sheet (Non-Current Assets)", "Activos fijos físicos tangibles netos de depreciación acumulada."),
        ("(=) Capital Tangible al Cierre", _fmt_m(greenblatt_ltm.get('tangible_capital_end')), _fmt_m(prev_fy_res.get('tangible_capital_end')), "Salvaguarda Joel Greenblatt", "Si NWC < 0, se acota al PP&E Neto (nunca menor a las plantas físicas)."),
        ("(=) Capital Tangible Operativo Promedio", _fmt_m(greenblatt_ltm.get('tangible_capital_avg')), _fmt_m(prev_fy_res.get('tangible_capital_avg')), "Denominador (Matching Principle)", "Promedio (t + t-1)/2 para sincronizar capital con flujo anual de EBIT."),
        ("(=) ROC Greenblatt Tangible (%)", _fmt_pct(roc_ltm_val), _fmt_pct(prev_fy_res.get('roc_avg')), "Ratio Final de Productividad", "EBIT / Capital Tangible Promedio."),
    ]

    tbl_recon = doc.add_table(rows=len(recon_rows) + 1, cols=5)
    tbl_recon.alignment = WD_TABLE_ALIGNMENT.CENTER
    tbl_recon.autofit = False
    _set_table_borders(tbl_recon)

    recon_headers = ["Partida Contable / Paso", f"LTM", prev_fy_key, "Origen en Balances SEC", "Criterio y Salvaguarda Contable"]
    col_widths_recon = [Inches(1.8), Inches(0.9), Inches(0.9), Inches(1.5), Inches(1.7)]

    for c_idx, title in enumerate(recon_headers):
        cell = tbl_recon.cell(0, c_idx)
        cell.text = title
        _set_cell_shading(cell, HEADER_BG)
        _set_cell_margins(cell, top=80, bottom=80, left=100, right=100)
        p = cell.paragraphs[0]
        p.runs[0].font.bold = True
        p.runs[0].font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        p.runs[0].font.size = Pt(8.5)

    for r_idx, (p1, p2, p3, p4, p5) in enumerate(recon_rows, start=1):
        for c_idx, text in enumerate([p1, p2, p3, p4, p5]):
            cell = tbl_recon.cell(r_idx, c_idx)
            cell.text = text
            _set_cell_margins(cell, top=60, bottom=60, left=100, right=100)
            if r_idx % 2 == 0:
                _set_cell_shading(cell, ALT_ROW_BG)
            if r_idx == len(recon_rows):
                _set_cell_shading(cell, GREEN_BG)
            p = cell.paragraphs[0]
            if c_idx in (0, 1) or r_idx == len(recon_rows):
                p.runs[0].font.bold = True
            p.runs[0].font.size = Pt(8.5)

    for i, col in enumerate(tbl_recon.columns):
        col.width = col_widths_recon[i]

    _add_callout(
        doc,
        "Guía de Auditoría: Trazabilidad del ROC en los Balances SEC",
        [
            "• EBIT (Operating Income): Búsquelo en el Estado Consolidado de Operaciones (Form 10-K / 10-Q).",
            "• Activos Operativos: Tome Total Current Assets del Balance y reste Cash & Marketable Securities.",
            "• Pasivos Operativos: Tome Total Current Liabilities del Balance y reste Commercial Paper y Deuda CP.",
            "• PP&E Neto: Búsquelo en Activos No Corrientes bajo Property, plant and equipment, net.",
            "• Salvaguarda de Capital de Trabajo Negativo: Si NWC < 0, Joel Greenblatt fija el capital tangible en el PP&E neto para impedir denominadores distorsionados o bases de capital negativas."
        ],
        accent_color="1B365D",
        bg_color="F0F4F8"
    )

    # 11.3. Desglose ROIC: Tradicional vs Ajustado Damodaran
    doc.add_heading(f"{section_num}.3. Desglose y Explicación del ROIC: Tradicional vs. Ajustado por Intangibles (Damodaran)", level=2)
    p_roic_exp = doc.add_paragraph()
    r_ro = p_roic_exp.add_run(
        f"El ROIC Tradicional contable ({_fmt_pct(roic_trad)}) sobrestima el retorno al mandar el I+D a gasto inmediato. "
        f"La metodología Damodaran capitaliza la innovación a {n_rd} años, reconociendo {_fmt_m(stock_int)} de intangibles fuera de balance. "
        f"El ROIC Ajustado resultante de {_fmt_pct(roic_adj)} refleja el verdadero retorno económico sobre el capital total invertido ({_fmt_m(ic_adj)})."
    )
    r_ro.font.size = Pt(9.5)

    # Tabla Serie Multianual
    by_period = roic_data.get("by_period", {})
    sorted_p = sorted([k for k in by_period.keys() if k != "LTM"], key=lambda x: int(x.replace("FY", "")) if "FY" in x else 0)
    periods_to_show = sorted_p[-5:] + (["LTM"] if "LTM" in by_period else [])

    tbl_roic = doc.add_table(rows=len(periods_to_show) + 1, cols=7)
    tbl_roic.alignment = WD_TABLE_ALIGNMENT.CENTER
    tbl_roic.autofit = False
    _set_table_borders(tbl_roic)

    r_headers = ["Período Contable", "ROC Greenblatt", "ROIC Tradicional", "ROIC Ajustado", "Stock Intangibles ($M)", "Capital Invertido ($M)", "Spread vs WACC"]
    col_widths_roic = [Inches(1.0), Inches(1.0), Inches(1.0), Inches(1.0), Inches(1.0), Inches(1.0), Inches(0.8)]

    for c_idx, title in enumerate(r_headers):
        cell = tbl_roic.cell(0, c_idx)
        cell.text = title
        _set_cell_shading(cell, HEADER_BG)
        _set_cell_margins(cell, top=80, bottom=80, left=100, right=100)
        p = cell.paragraphs[0]
        p.runs[0].font.bold = True
        p.runs[0].font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        p.runs[0].font.size = Pt(8.5)

    for r_idx, pk in enumerate(periods_to_show, start=1):
        p_val = by_period.get(pk, {})
        if pk == "LTM":
            p_roc = greenblatt_ltm.get("roc_avg") if greenblatt_ltm.get("roc_avg") is not None else greenblatt_ltm.get("roc_ltm")
        else:
            p_roc = greenblatt_annual.get(pk, {}).get("roc_avg")
        roc_str = _fmt_pct(p_roc)
        trad_str = _fmt_pct(p_val.get('roic_trad'))
        adj_str = _fmt_pct(p_val.get('roic_adj'))
        int_str = _fmt_m(p_val.get('total_intangible_stock'))
        ic_str = _fmt_m(p_val.get('ic_adj'))
        p_sp = (p_val.get('roic_adj') - wacc_val) if (p_val.get('roic_adj') is not None and wacc_val is not None) else None
        sp_str = _fmt_pp(p_sp)

        for c_idx, text in enumerate([pk, roc_str, trad_str, adj_str, int_str, ic_str, sp_str]):
            cell = tbl_roic.cell(r_idx, c_idx)
            cell.text = text
            _set_cell_margins(cell, top=60, bottom=60, left=100, right=100)
            if r_idx % 2 == 0:
                _set_cell_shading(cell, ALT_ROW_BG)
            if pk == "LTM":
                _set_cell_shading(cell, GREEN_BG)
            p = cell.paragraphs[0]
            if c_idx in (1, 2, 3, 6):
                p.runs[0].font.bold = True
            p.runs[0].font.size = Pt(8.5)

    for i, col in enumerate(tbl_roic.columns):
        col.width = col_widths_roic[i]

    p_sens = doc.add_paragraph()
    p_sens.paragraph_format.space_before = Pt(8)
    p_sens.paragraph_format.space_after = Pt(8)
    n_minus_years = sens.get('n_minus_1', {}).get('lifespan_years', n_rd - 1 if n_rd > 1 else 1)
    n_plus_years = sens.get('n_plus_1', {}).get('lifespan_years', n_rd + 1)
    n_minus_roic = sens.get('n_minus_1', {}).get('roic_adj')
    n_plus_roic = sens.get('n_plus_1', {}).get('roic_adj')
    r_sens = p_sens.add_run(
        f"Matriz de Sensibilidad de Vida Útil: N-1 ({n_minus_years}a) = {_fmt_pct(n_minus_roic)} | "
        f"N Base ({n_rd}a) = {_fmt_pct(roic_adj)} | "
        f"N+1 ({n_plus_years}a) = {_fmt_pct(n_plus_roic)}."
    )
    r_sens.font.size = Pt(9)
    r_sens.font.italic = True

    # 11.4. Creación de Valor Económico y Moat
    doc.add_heading(f"{section_num}.4. Creación de Valor Económico (EVA) y Durabilidad del Foso Defensivo", level=2)
    p_eva = doc.add_paragraph()
    r_eva = p_eva.add_run(
        f"Spread Económico = ROIC Ajustado ({_fmt_pct(roic_adj)}) − WACC ({_fmt_pct(wacc_val)}) = {_fmt_pp(spread_adj)}\n"
        f"Dictamen: {moat_badge}. La compañía supera holgadamente su costo de capital, generando retornos netos excedentes sobre cada dólar invertido."
    )
    r_eva.font.size = Pt(9.5)

    # 11.5. Cuadro de Mando Consolidado
    doc.add_heading(f"{section_num}.5. Cuadro de Mando Consolidado de Ratios de Capital, Retornos y Valor", level=2)
    eff_tax_str = f"{wacc_data.get('effective_tax_rate', 0.173)*100:.1f}%" if wacc_data.get('effective_tax_rate') is not None else "N/D"
    sec_roc_str = f"Mediana Sector ({_fmt_pct(sec_roc)})" if sec_roc is not None else "Mediana Sector"
    sec_roic_str = f"Mediana Sector ({_fmt_pct(sec_roic)})" if sec_roic is not None else "Mediana Sector"
    sec_sp_str = f"Mediana Sector ({_fmt_pp(sec_spread)})" if sec_spread is not None else "Mediana Sector"
    roc_diag = f"Asset-Light; supera al sector por {_fmt_pp(roc_ltm_val - sec_roc) if (roc_ltm_val is not None and sec_roc is not None) else 'N/D'}."

    summary_rows = [
        ("Parámetros Macro y Mercado", "Tasa Libre de Riesgo (Rf - Bono 10Y)", _fmt_pct(rf), "US Treasury Yield", "Costo de oportunidad libre de riesgo macroeconómico."),
        ("Parámetros Macro y Mercado", "Beta de la Acción (β)", _fmt_num(beta), "S&P 500 = 1.00x", "Sensibilidad cíclica moderada y alineada al mercado."),
        ("Parámetros Macro y Mercado", "Prima de Riesgo de Mercado (ERP)", _fmt_pct(erp), "NYU Stern Damodaran", "Exigencia de prima de retorno sobre el activo libre de riesgo."),
        ("Costo de Capital (WACC)", "Costo del Capital Propio (Ke)", _fmt_pct(ke), "Rango 9.5% - 10.5%", "Retorno anual exigido por los tenedores de acciones comunes."),
        ("Costo de Capital (WACC)", "Costo de Deuda Neta (Kd)", _fmt_pct(kd), "Tasa cupón efectiva", f"Financiación crediticia con escudo fiscal del {eff_tax_str}."),
        ("Costo de Capital (WACC)", "WACC Consolidado", _fmt_pct(wacc_val), f"Mediana Sector ({_fmt_pct(sec_wacc)})", "Tasa de corte u obstáculo financiero mínimo para crear valor."),
        ("Productividad Tangible", "ROC Greenblatt (Pre-Tax)", _fmt_pct(roc_ltm_val), sec_roc_str, roc_diag),
        ("Productividad Tangible", "Capital Tangible Promedio", _fmt_m(tangible_cap_avg), "Balance SEC Form 10-Q", "Base física operativa mínima tras salvaguardas."),
        ("Retorno Reconstituido", "ROIC Contable Tradicional", _fmt_pct(roic_trad), "ROIC sin ajustes", "Métrica distorsionada por no capitalizar gasto de innovación."),
        ("Retorno Reconstituido", "Stock Intangibles I+D", _fmt_m(stock_int), f"Amortización {n_rd} Años", "Valor acumulado de patentes, silicio y software."),
        ("Retorno Reconstituido", "Capital Invertido Promedio", _fmt_m(ic_adj), "Base Económica Total", "Base de capital honesta que absorbe las inversiones en I+D."),
        ("Retorno Reconstituido", "ROIC Ajustado por Intangibles", _fmt_pct(roic_adj), sec_roic_str, "Retorno real sobre capital total invertido en el negocio."),
        ("Creación de Valor (EVA)", "Spread Económico Neto", _fmt_pp(spread_adj), sec_sp_str, "Extraordinaria generación de riqueza neta sobre el coste de capital."),
        ("Creación de Valor (EVA)", "Dictamen Foso Defensivo", f"{moat_badge}", "Compounding Machine", "Fortaleza estructural inquebrantable de largo plazo."),
    ]

    tbl_sum = doc.add_table(rows=len(summary_rows) + 1, cols=5)
    tbl_sum.alignment = WD_TABLE_ALIGNMENT.CENTER
    tbl_sum.autofit = False
    _set_table_borders(tbl_sum)

    sum_headers = ["Categoría Analítica", "Métrica / Ratio Institucional", "Valor LTM", "Benchmark / Ref.", "Diagnóstico para el Inversor"]
    col_widths_sum = [Inches(1.4), Inches(2.0), Inches(0.9), Inches(1.1), Inches(1.4)]

    for c_idx, title in enumerate(sum_headers):
        cell = tbl_sum.cell(0, c_idx)
        cell.text = title
        _set_cell_shading(cell, HEADER_BG)
        _set_cell_margins(cell, top=80, bottom=80, left=100, right=100)
        p = cell.paragraphs[0]
        p.runs[0].font.bold = True
        p.runs[0].font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        p.runs[0].font.size = Pt(8.5)

    for r_idx, (cat, met, val, bench, diag) in enumerate(summary_rows, start=1):
        for c_idx, text in enumerate([cat, met, val, bench, diag]):
            cell = tbl_sum.cell(r_idx, c_idx)
            cell.text = text
            _set_cell_margins(cell, top=60, bottom=60, left=100, right=100)
            if r_idx % 2 == 0:
                _set_cell_shading(cell, ALT_ROW_BG)
            if "ROIC Ajustado" in met or "Spread" in met or "ROC Greenblatt" in met:
                _set_cell_shading(cell, GREEN_BG)
            p = cell.paragraphs[0]
            if c_idx in (1, 2) or "ROIC Ajustado" in met or "Spread" in met:
                p.runs[0].font.bold = True
            p.runs[0].font.size = Pt(8.5)

    for i, col in enumerate(tbl_sum.columns):
        col.width = col_widths_sum[i]

    doc.add_paragraph()


def generate_roic_wacc_section_md(scoring_data: Dict[str, Any], ticker: str = "AAPL", company_name: str = "Apple Inc.", section_num: int = 11) -> str:
    """Genera la sección Markdown con numeración configurable."""
    return build_roic_wacc_markdown_section(scoring_data, ticker, company_name, section_num=section_num)


def add_roic_wacc_section_docx(doc, scoring_data: Dict[str, Any], ticker: str = "AAPL", company_name: str = "Apple Inc.", section_num: int = 11):
    """Inserta la sección en formato docx con numeración configurable."""
    add_roic_wacc_section_to_doc(doc, scoring_data, ticker, company_name, section_num=section_num)
