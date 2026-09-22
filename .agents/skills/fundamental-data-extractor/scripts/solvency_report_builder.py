"""
solvency_report_builder.py - Constructor de secciones ejecutivas de Solvencia, Deuda
y Estrés Financiero para informes Word (.docx) y Markdown (.md).

Implementa los 4 Bloques Institucionales:
- Bloque A: Dictamen Global de Solvencia y Scorecard de Crédito (Rating Sintético Damodaran)
- Bloque B: Apalancamiento y Capacidad de Amortización frente a Flujos de Caja (Net Debt/EBITDA, Net Debt/FCF)
- Bloque C: Cobertura de Carga Financiera y Servicio de la Deuda (Interest Coverage, Cash Interest Coverage)
- Bloque D: Liquidez Estricta, Refinanciación y Modelo de Quiebra Altman Z''-Score
Con explicaciones pedagógicas claras para cada ratio, umbral y parámetro de estrés evaluado.
"""

import sys
from pathlib import Path
from typing import Dict, Any, List, Optional
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


def _fmt_money(val, default="N/D", sign=False):
    if val is None:
        return default
    try:
        f = float(val)
        if sign:
            return f"${f:+,.1f}M"
        return f"${f:,.1f}M"
    except (ValueError, TypeError):
        return default

def _fmt_pct(val, default="N/D"):
    if val is None:
        return default
    try:
        return f"{float(val):.2f}%"
    except (ValueError, TypeError):
        return default


def generate_solvency_section_md(
    scoring_data: Dict[str, Any],
    ticker: str,
    company_name: str,
    section_num: int = 14
) -> str:
    """Genera la sección completa de Solvencia, Deuda y Estrés Financiero en formato Markdown enriquecido."""
    solv = scoring_data.get("debt_and_solvency_analysis", {})
    if not solv:
        return ""

    latest = solv.get("latest_result", {})
    recent_fy = latest.get("period", "LTM")
    lev = latest.get("cash_flow_leverage", {})
    cov = latest.get("debt_service", {})
    liq = latest.get("liquidity", {})
    dist = latest.get("distress_models", {})
    verdict = latest.get("solvency_verdict", "")
    badge = latest.get("global_badge", "SOLVENCIA INSTITUCIONAL")

    md = f"""## {section_num}. Solvencia, Deuda y Estrés Financiero (Credit Risk Engine)

> **DICTAMEN INSTITUCIONAL DE SOLVENCIA ({recent_fy})**: **{badge}**
> {verdict}

A diferencia de los ratios tradicionales de balance (como Deuda/Patrimonio, que se distorsionan severamente por programas de recompra de acciones o en firmas libres de deuda), este módulo evalúa la solvencia corporativa bajo el estándar de **banca de inversión y agencias de calificación crediticia (S&P, Moody's)** a través de cuatro dimensiones fundamentales:

---

### {section_num}.1. Apalancamiento y Capacidad de Amortización frente a Caja (Cash Flow Leverage)
Mide en cuántos años de generación operativa bruta (**EBITDA**) o caja de libre disposición (**FCF**) la empresa podría cancelar el 100% de su deuda neta:

| Métrica / Componente | Definición / Fórmula Contable | Umbral Óptimo | Valor {recent_fy} | Diagnóstico de Repago |
| :--- | :--- | :---: | :---: | :--- |
| **Deuda Financiera Total** | Deuda a Corto + Largo Plazo | Referencia | **{_fmt_money(lev.get('total_debt'))}** | Nivel de apalancamiento bruto emitido. |
| **Tesorería y Equivalentes** | Efectivo y Activos Líquidos | Liquidez Inmediata | **{_fmt_money(lev.get('cash'))}** | Colchón de caja disponible. |
| **Deuda Financiera Neta** | Deuda Total - Tesorería | Caja Neta (< $0) | **{_fmt_money(lev.get('net_debt'), sign=True)}** | {'Posición Neta de Caja' if lev.get('is_net_cash') else 'Deuda Neta a Amortizar'}. |
| **EBITDA Generado** | EBIT + Depreciación y Amortización | Base Operativa Bruta | **{_fmt_money(lev.get('ebitda'), default='N/D (Bancario)')}** | Flujo operativo bruto de negocio. |
| **Deuda Neta / EBITDA** | Deuda Neta / EBITDA | < 1.5x (Excelente) | **{lev.get('net_debt_to_ebitda_str', 'N/D')}** | {lev.get('status', 'N/D')} |
| **Flujo de Caja Libre (FCF)** | Flujo Operativo (CFO) - CapEx | Caja Real Disponible | **{_fmt_money(lev.get('fcf'))}** | Caja libre tras reinversión e impuestos. |
| **Deuda Neta / FCF** | Deuda Neta / FCF | < 2.0x (Sólido) | **{lev.get('net_debt_to_fcf_str', 'N/D')}** | Años de caja libre para liquidar deuda. |

---

### {section_num}.2. Cobertura de Carga Financiera y Servicio de la Deuda
Evalúa el margen de seguridad de los beneficios y del flujo de caja para absorber el pago obligatorio de intereses bancarios:

| Parámetro Evaluado | Fórmula Contable | Umbral de Seguridad | Valor {recent_fy} | Dictamen de Cobertura |
| :--- | :--- | :---: | :---: | :--- |
| **Beneficio Operativo (EBIT)** | Ingresos - Costes Operativos | Fondo de Cobertura | **{_fmt_money(cov.get('ebit'), default='N/D (Bancario)')}** | Margen operativo para servir la deuda. |
| **Gasto por Intereses** | Carga Financiera Reportada/Estimada | Obligación Anual | **{_fmt_money(cov.get('interest_expense'))}** | Intereses devengados por bonos y préstamos. |
| **Cobertura Operativa (EBIT/Int)** | EBIT / Gasto por Intereses | > 10.0x (AAA) | **{cov.get('interest_coverage_str', 'N/D')}** | {cov.get('status', 'N/D')} |
| **Cobertura en Efectivo (CFO/Int)** | CFO / Gasto por Intereses | > 8.0x (Robusta) | **{cov.get('cash_interest_coverage_str', 'N/D')}** | Cobertura con caja líquida generada. |
| **Carga Financiera sobre CFO** | (Intereses / CFO) * 100 | < 5.0% (Mínima) | **{_fmt_pct(cov.get('financial_burden_pct'))}** | Porcentaje de la caja consumido por deuda. |

---

### {section_num}.3. Liquidez Inmediata, Estructura y Perfil de Vencimiento
Analiza la capacidad de responder a obligaciones de corto plazo sin depender de liquidar inventarios, y evalúa el riesgo de refinanciación (*rollover risk*):

| Ratio / Estructura | Fórmula | Interpretación | Valor {recent_fy} | Diagnóstico |
| :--- | :--- | :---: | :---: | :--- |
| **Current Ratio** | Activo Corriente / Pasivo Corriente | Normal: 1.0x - 2.5x | **{liq.get('current_ratio', 'N/D')}x** | Liquidez corriente total. |
| **Quick Ratio (Ratio Ácido)** | (Caja + Clientes) / Pasivo Corriente | > 1.0x (Holgado) | **{liq.get('quick_ratio', 'N/D')}x** | {liq.get('status', 'N/D')} |
| **Cash Ratio** | Caja / Pasivo Corriente | > 0.20x | **{liq.get('cash_ratio', 'N/D')}x** | Cobertura inmediata en cuenta corriente. |
| **Riesgo Refinanciación (CP/Total)** | Deuda Corto Plazo / Deuda Total | < 20.0% (Bajo) | **{liq.get('rollover_risk_pct', 0):.1f}%** | Proporción de deuda con vencimiento en <= 12 meses. |
| **Deuda / Capital Total** | Deuda / (Deuda + Patrimonio) | < 40.0% | **{liq.get('debt_to_capital_pct', 0):.1f}%** | Peso de la deuda en la estructura de capital. |

---

### {section_num}.4. Modelos Predictivos de Quiebra y Rating Sintético

```mermaid
graph LR
    Z["Altman Z''-Score<br>{dist.get('altman_z_double_prime', 'N/D')}"] --> Z1["{dist.get('altman_badge', 'N/D')}<br>{dist.get('altman_zone', 'N/D')}"]
    R["Cobertura de Intereses<br>{cov.get('interest_coverage_str', 'N/D')}"] --> R1["Rating Sintético Damodaran<br>{dist.get('synthetic_rating', 'N/D')} ({dist.get('synthetic_rating_desc', 'N/D')})"]
    R1 --> S["Spread de Default: {dist.get('default_spread_pct', 0):.2f}%<br>Probabilidad de Default: {dist.get('default_probability', 'N/D')}"]
```

* **Altman Z''-Score (Modelo de 4 Variables para Empresas Globales y Servicios)**:
  $$Z'' = 6.56 X_1 + 3.26 X_2 + 6.72 X_3 + 1.05 X_4 = \\mathbf{{{dist.get('altman_z_double_prime', 'N/D')}}}$$
  * $X_1$ (Fondo de Maniobra / Activos): `{dist.get('altman_x1', 'N/D')}`
  * $X_2$ (Resultados Acumulados / Activos): `{dist.get('altman_x2', 'N/D')}`
  * $X_3$ (EBIT / Activos Totales): `{dist.get('altman_x3', 'N/D')}`
  * $X_4$ (Patrimonio Neto / Pasivos Totales): `{dist.get('altman_x4', 'N/D')}`
  * **Veredicto Econométrico**: **{dist.get('altman_zone', 'N/D')}**. {dist.get('altman_diagnosis', '')}

* **Rating Crediticio Sintético (Metodología Aswath Damodaran - Stern NYU)**:
  * **Calificación Asignada**: **{dist.get('synthetic_rating', 'N/D')}** (*{dist.get('synthetic_rating_desc', 'N/D')}*).
  * **Spread de Crédito Teórico**: **+{dist.get('default_spread_pct', 0):.2f}%** sobre el tipo libre de riesgo.
  * **Probabilidad Empírica de Default a 10 Años**: **{dist.get('default_probability', 'N/D')}**.
"""
    return md


def add_solvency_section_docx(
    doc: docx.Document,
    scoring_data: Dict[str, Any],
    ticker: str,
    company_name: str,
    section_num: int = 14
):
    """Inserta la sección de Solvencia, Deuda y Estrés Financiero en un documento Word (.docx)."""
    solv = scoring_data.get("debt_and_solvency_analysis", {})
    if not solv:
        return

    latest = solv.get("latest_result", {})
    recent_fy = latest.get("period", "LTM")
    lev = latest.get("cash_flow_leverage", {})
    cov = latest.get("debt_service", {})
    liq = latest.get("liquidity", {})
    dist = latest.get("distress_models", {})
    verdict = latest.get("solvency_verdict", "")
    badge = latest.get("global_badge", "SOLVENCIA INSTITUCIONAL")

    # Título Principal
    heading = doc.add_heading(f"{section_num}. Solvencia, Deuda y Estrés Financiero (Credit Risk Engine)", level=1)
    heading.style.font.color.rgb = NAVY

    # Callout Box de Resumen Ejecutivo
    box_table = doc.add_table(rows=1, cols=1)
    box_table.alignment = WD_TABLE_ALIGNMENT.CENTER
    cell = box_table.cell(0, 0)
    _set_cell_shading(cell, LIGHT_BLUE)
    _set_cell_margins(cell, top=140, bottom=140, left=180, right=180)

    p_badge = cell.paragraphs[0]
    r_badge = p_badge.add_run(f"DICTAMEN GLOBAL DE SOLVENCIA ({recent_fy}): {badge}\n")
    r_badge.bold = True
    r_badge.font.size = Pt(11)
    r_badge.font.color.rgb = NAVY

    r_desc = p_badge.add_run(
        f"Rating Sintético Damodaran: {dist.get('synthetic_rating', 'N/D')} ({dist.get('synthetic_rating_desc', 'N/D')}) | "
        f"Altman Z''-Score: {dist.get('altman_z_double_prime', 'N/D')} [{dist.get('altman_badge', 'N/D')}]\n\n"
        f"{verdict}"
    )
    r_desc.font.size = Pt(9.5)
    r_desc.font.color.rgb = DARK_GRAY

    doc.add_paragraph()

    # Tabla 1: Apalancamiento y Capacidad de Amortización
    doc.add_heading(f"{section_num}.1. Apalancamiento y Capacidad de Amortización (Cash Flow Leverage)", level=2)
    t1 = doc.add_table(rows=6, cols=4)
    t1.alignment = WD_TABLE_ALIGNMENT.CENTER
    _set_table_borders(t1)

    headers = ["Métrica de Amortización", "Fórmula Contable", "Valor LTM", "Diagnóstico"]
    for i, h in enumerate(headers):
        c = t1.cell(0, i)
        _set_cell_shading(c, HEADER_BG)
        p = c.paragraphs[0]
        r = p.add_run(h)
        r.bold = True
        r.font.size = Pt(9)
        r.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)

    data_t1 = [
        ("Deuda Financiera Total", "Short + Long Term Debt", _fmt_money(lev.get('total_debt')), "Referencia Balance"),
        ("Tesorería y Equivalentes", "Cash & Equivalents", _fmt_money(lev.get('cash')), "Liquidez Inmediata"),
        ("Deuda Financiera Neta", "Deuda Total - Tesorería", _fmt_money(lev.get('net_debt'), sign=True), "Posición Neta de Caja" if lev.get('is_net_cash') else "Deuda Neta"),
        ("Deuda Neta / EBITDA", "Deuda Neta / EBITDA", str(lev.get('net_debt_to_ebitda_str', 'N/D')), lev.get('status', 'N/D')),
        ("Deuda Neta / FCF", "Deuda Neta / FCF", str(lev.get('net_debt_to_fcf_str', 'N/D')), "Años de Caja Libre"),
    ]

    for row_idx, row_data in enumerate(data_t1, start=1):
        for col_idx, text in enumerate(row_data):
            c = t1.cell(row_idx, col_idx)
            if row_idx % 2 == 0:
                _set_cell_shading(c, ALT_ROW_BG)
            p = c.paragraphs[0]
            r = p.add_run(text)
            r.font.size = Pt(8.5)
            if col_idx in [0, 2]:
                r.bold = True

    doc.add_paragraph()

    # Tabla 2: Cobertura de Intereses y Servicio de Deuda
    doc.add_heading(f"{section_num}.2. Cobertura de Intereses y Carga Financiera", level=2)
    t2 = doc.add_table(rows=5, cols=4)
    t2.alignment = WD_TABLE_ALIGNMENT.CENTER
    _set_table_borders(t2)

    headers_t2 = ["Métrica de Cobertura", "Fórmula Contable", "Valor LTM", "Evaluación"]
    for i, h in enumerate(headers_t2):
        c = t2.cell(0, i)
        _set_cell_shading(c, HEADER_BG)
        p = c.paragraphs[0]
        r = p.add_run(h)
        r.bold = True
        r.font.size = Pt(9)
        r.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)

    data_t2 = [
        ("Beneficio Operativo (EBIT)", "Operating Income", _fmt_money(cov.get('ebit'), default="N/D (Bancario)"), "Fondo de Cobertura"),
        ("Gasto por Intereses", "Gasto Financiero Auditado/Estimado", _fmt_money(cov.get('interest_expense')), "Carga Obligatoria"),
        ("Cobertura de Intereses Operativa", "EBIT / Gasto Financiero", str(cov.get('interest_coverage_str', 'N/D')), cov.get('status', 'N/D')),
        ("Carga Financiera sobre CFO", "(Intereses / CFO) * 100", _fmt_pct(cov.get('financial_burden_pct')), "Impacto en Caja"),
    ]

    for row_idx, row_data in enumerate(data_t2, start=1):
        for col_idx, text in enumerate(row_data):
            c = t2.cell(row_idx, col_idx)
            if row_idx % 2 == 0:
                _set_cell_shading(c, ALT_ROW_BG)
            p = c.paragraphs[0]
            r = p.add_run(text)
            r.font.size = Pt(8.5)
            if col_idx in [0, 2]:
                r.bold = True

    doc.add_paragraph()

    # Tabla 3: Quiebra y Rating Sintético
    doc.add_heading(f"{section_num}.3. Modelos de Quiebra (Altman Z'') y Rating Sintético", level=2)
    t3 = doc.add_table(rows=4, cols=4)
    t3.alignment = WD_TABLE_ALIGNMENT.CENTER
    _set_table_borders(t3)

    headers_t3 = ["Instrumento Predictivo", "Resultado Cuantitativo", "Calificación / Zona", "Interpretación Institucional"]
    for i, h in enumerate(headers_t3):
        c = t3.cell(0, i)
        _set_cell_shading(c, HEADER_BG)
        p = c.paragraphs[0]
        r = p.add_run(h)
        r.bold = True
        r.font.size = Pt(9)
        r.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)

    spread_pct = _fmt_pct(dist.get('default_spread_pct'))
    spread_str = f"Spread Teórico: +{spread_pct}" if spread_pct != "N/D" else "Spread Teórico: N/D"
    data_t3 = [
        ("Altman Z''-Score (4 Variables)", str(dist.get('altman_z_double_prime', 'N/D')), str(dist.get('altman_badge', 'N/D')), dist.get('altman_zone', 'N/D')),
        ("Rating Sintético Damodaran", str(dist.get('synthetic_rating', 'N/D')), str(dist.get('synthetic_rating_desc', 'N/D')), spread_str),
        ("Probabilidad de Default a 10 Años", str(dist.get('default_probability', 'N/D')), "Estadística S&P", "Mínimo riesgo crediticio histórico."),
    ]

    for row_idx, row_data in enumerate(data_t3, start=1):
        for col_idx, text in enumerate(row_data):
            c = t3.cell(row_idx, col_idx)
            if row_idx % 2 == 0:
                _set_cell_shading(c, ALT_ROW_BG)
            p = c.paragraphs[0]
            r = p.add_run(text)
            r.font.size = Pt(8.5)
            if col_idx in [0, 1]:
                r.bold = True
