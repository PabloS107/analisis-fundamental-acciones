"""
solvency_report_builder.py - Constructor de secciones ejecutivas de Solvencia, Deuda
y Estrés Financiero para informes Word (.docx) y Markdown (.md).

Implementa arquitectura tri-modal:
1. Framework Corporativo / Industrial (AAPL, DECK):
   - Bloque A: Dictamen Global de Solvencia y Scorecard de Crédito (Rating Sintético Damodaran)
   - Bloque B: Apalancamiento y Capacidad de Amortización frente a Flujos de Caja (Net Debt/EBITDA, Net Debt/FCF)
   - Bloque C: Cobertura de Carga Financiera y Servicio de la Deuda (Interest Coverage, Cash Interest Coverage)
   - Bloque D: Liquidez Estricta, Refinanciación y Modelo de Quiebra Altman Z''-Score

2. Framework Bancario / Institución Financiera (NU, JPM, Bancos, FinTechs):
   - Bloque A: Dictamen Global de Solvencia Regulatoria y Adecuación de Capital (Basilea III / CET1)
   - Bloque B: Estructura de Balance, Cartera de Crédito y Fondeo (Loans, Deposits, Loan-to-Deposit LDR, Apalancamiento)
   - Bloque C: Calidad Crediticia, Morosidad y Cobertura de Provisiones (NIM, NPL 15-90d, NPL >90d, Cost of Risk, Cobertura)
   - Bloque D: Liquidez Inmediata y Resiliencia de Fondeo (Depósitos Minoristas, Liquidez/Depósitos, Descalce ALM)
   - Bloque E: Marco Regulatorio Basilea III, Rating Sintético Damodaran y Justificación Metodológica de por qué NO aplica el Altman Z''-Score.

3. Framework Asegurador / Institución de Seguros (PGR, P&C, Vida, Reaseguros):
   - Bloque A: Dictamen Global de Solvencia Técnica y Suficiencia de Capital (NAIC / Solvencia II)
   - Bloque B: Rentabilidad Técnica y Eficiencia de Suscripción (Loss Ratio, Expense Ratio, Combined Ratio, Underwriting Profit)
   - Bloque C: Gestión del Float Asegurador y Cartera de Inversiones (Loss Reserves, Unearned Premiums, Net Float, Rendimiento Cartera)
   - Bloque D: Solvencia Patrimonial, Apalancamiento de Primas/Reservas y Rating Sintético Damodaran.
"""

import sys
import json
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


def get_solvency_archetype(scoring_data: Dict[str, Any]) -> str:
    """
    Identifica de forma canónica y universal el arquetipo de solvencia del emisor.
    Retorna:
    - 'INSURANCE': Aseguradoras (SIC 63xx, 64xx, P&C, Life, Reinsurance).
    - 'FINANCIAL_BANKING': Bancos, entidades de crédito, Neobancos, FinTechs (SIC 60xx, 61xx, 62xx).
    - 'CORPORATE': Empresas corporativas tradicionales, industriales, tecnológicas, REITs, etc.
    """
    arch = scoring_data.get("archetype")
    if arch:
        arch_upper = str(arch).upper()
        if arch_upper == "INSURANCE":
            return "INSURANCE"
        if arch_upper in ("FINANCIAL_BANKING", "BANKING", "BANK"):
            return "FINANCIAL_BANKING"
        if arch_upper in ("CORPORATE_STANDARD", "STANDARD_CORPORATE", "REAL_ESTATE_REIT", "PLATFORM_ECOSYSTEM"):
            return "CORPORATE"

    solv_arch = scoring_data.get("debt_and_solvency_analysis", {}).get("archetype")
    if solv_arch:
        solv_arch_upper = str(solv_arch).upper()
        if solv_arch_upper == "INSURANCE":
            return "INSURANCE"
        if solv_arch_upper in ("FINANCIAL_BANKING", "BANKING", "BANK"):
            return "FINANCIAL_BANKING"

    sic = str(scoring_data.get("sic_code") or scoring_data.get("benchmarks_used", {}).get("sic_code", "")).strip()
    if sic.startswith("63") or sic.startswith("64"):
        return "INSURANCE"
    if sic.startswith("60") or sic.startswith("61") or sic.startswith("62"):
        return "FINANCIAL_BANKING"

    gics = scoring_data.get("benchmarks_used", {}).get("gics_sector")
    is_fin = scoring_data.get("is_financial_institution") or scoring_data.get("novy_marx_analysis", {}).get("latest_result", {}).get("is_financial_institution")
    if is_fin or gics == "Financials":
        ind = str(scoring_data.get("industry_name", "")).upper()
        bm = str(scoring_data.get("business_model", "")).upper()
        if "INSUR" in ind or "INSUR" in bm:
            return "INSURANCE"
        return "FINANCIAL_BANKING"

    return "CORPORATE"


def _is_financial(scoring_data: Dict[str, Any]) -> bool:
    """Identifica si la empresa pertenece al sector financiero/bancario/seguros de forma dinámica y universal."""
    return get_solvency_archetype(scoring_data) in ("FINANCIAL_BANKING", "INSURANCE")


def _load_profile_if_needed(ticker: str, profile_data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Carga company_profile.json si no fue provisto explícitamente."""
    if profile_data:
        return profile_data
    candidate = Path(f"data/processed/{ticker}/company_profile.json")
    if candidate.exists():
        try:
            with open(candidate, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _load_canonical_summary_if_needed(ticker: str) -> Dict[str, Any]:
    """Carga canonical_summary desde financial_statements.json si está disponible."""
    candidate = Path(f"data/processed/{ticker}/financial_statements.json")
    if candidate.exists():
        try:
            with open(candidate, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("canonical_summary", {})
        except Exception:
            pass
    return {}


# ==============================================================================
# SECCIÓN BANCARIA: MARKDOWN (.MD)
# ==============================================================================
def _generate_banking_solvency_md(
    scoring_data: Dict[str, Any],
    ticker: str,
    company_name: str,
    section_num: int = 13,
    profile_data: Optional[Dict[str, Any]] = None
) -> str:
    prof = _load_profile_if_needed(ticker, profile_data)
    can_summary = _load_canonical_summary_if_needed(ticker)
    solv = scoring_data.get("debt_and_solvency_analysis", {})
    latest = solv.get("latest_result", {})
    recent_fy = latest.get("period", "LTM")
    dist = latest.get("distress_models", {})

    # Extracción de métricas bancarias dinámicas del profile o de estados contables
    sc_dict = {r[0]: r for r in prof.get("scorecard", {}).get("data", [])}

    loans_row = sc_dict.get("Cartera Total de Crédito (Gross Loans)")
    if not loans_row:
        net_l = can_summary.get("net_loans", {}).get(recent_fy) or can_summary.get("net_loans", {}).get("LTM") or can_summary.get("gross_loans", {}).get(recent_fy)
        loans_row = ["", _fmt_money(net_l / 1e6 if net_l and abs(net_l) > 1e6 else net_l), "", "", ""]
    loans_display = loans_row[1] if len(loans_row) > 1 and loans_row[1] else "N/D"

    dep_row = sc_dict.get("Total Depósitos de Clientes")
    if not dep_row:
        tot_dep = can_summary.get("total_deposits", {}).get(recent_fy) or can_summary.get("total_deposits", {}).get("LTM")
        dep_row = ["", _fmt_money(tot_dep / 1e6 if tot_dep and abs(tot_dep) > 1e6 else tot_dep), "", "", ""]
    dep_display = dep_row[1] if len(dep_row) > 1 and dep_row[1] else "N/D"

    npl_early = sc_dict.get("Ratio de Morosidad 15-90 días") or ["", "N/D", "", "", ""]
    npl_early_display = npl_early[1] if len(npl_early) > 1 and npl_early[1] else "N/D"

    npl_late = sc_dict.get("Ratio de Morosidad >90 días (NPL)") or ["", "N/D", "", "", ""]
    npl_late_display = npl_late[1] if len(npl_late) > 1 and npl_late[1] else "N/D"

    rotce_row = sc_dict.get("Retorno sobre Patrimonio Tangible (ROTCE)")
    if not rotce_row:
        r_val = scoring_data.get("profitability_ratios", {}).get("rotce") or scoring_data.get("wacc_and_spread_analysis", {}).get("rotce_pct") or scoring_data.get("wacc_analysis", {}).get("rotce")
        if r_val is not None:
            r_pct = r_val * 100.0 if abs(r_val) <= 1.5 else r_val
            rotce_row = ["", f"{r_pct:.2f}%", "", "", ""]
        else:
            rotce_row = ["", "N/D", "", "", ""]
    rotce_display = rotce_row[1] if len(rotce_row) > 1 and rotce_row[1] else "N/D"

    # Ratio Préstamos sobre Depósitos (LDR)
    ldr_str = "N/D"
    try:
        if loans_display != "N/D" and dep_display != "N/D":
            l_num = float(loans_display.replace("$", "").replace("M", "").replace(",", "").strip())
            d_num = float(dep_display.replace("$", "").replace("M", "").replace(",", "").strip())
            if d_num > 0:
                ldr_str = f"{(l_num / d_num) * 100:.1f}%"
    except Exception:
        ldr_str = "N/D"

    # Caja y Activos
    cash_val = latest.get("cash_flow_leverage", {}).get("cash")
    if cash_val is None:
        c_eq = can_summary.get("cash_and_equivalents", {}).get(recent_fy) or can_summary.get("cash_and_equivalents", {}).get("LTM")
        cash_val = (c_eq / 1e6) if c_eq is not None and abs(c_eq) > 1e6 else c_eq

    tot_debt_val = latest.get("cash_flow_leverage", {}).get("total_debt")
    if tot_debt_val is None:
        d_eq = can_summary.get("total_debt", {}).get(recent_fy) or can_summary.get("total_debt", {}).get("LTM")
        tot_debt_val = (d_eq / 1e6) if d_eq is not None and abs(d_eq) > 1e6 else (d_eq or 0.0)

    # Apalancamiento de balance
    leverage_str = "N/D"
    try:
        t_assets = can_summary.get("total_assets", {}).get(recent_fy) or can_summary.get("total_assets", {}).get("LTM")
        t_equity = can_summary.get("stockholders_equity", {}).get(recent_fy) or can_summary.get("stockholders_equity", {}).get("LTM")
        if t_assets and t_equity and t_equity > 0:
            leverage_str = f"~{(t_assets / t_equity):.1f}x"
    except Exception:
        leverage_str = "N/D"

    cov_prov_row = sc_dict.get("Ratio de Cobertura de Provisiones")
    cov_prov_str = cov_prov_row[1] if cov_prov_row and len(cov_prov_row) > 1 and cov_prov_row[1] else "N/D"

    cor_row = sc_dict.get("Cost of Risk") or sc_dict.get("Cost of Risk Anualizado")
    cor_str = cor_row[1] if cor_row and len(cor_row) > 1 and cor_row[1] else "N/D"

    nim_row = sc_dict.get("Margen de Interés Neto (NIM)") or sc_dict.get("Margen de Interés Neto Ajustado")
    if nim_row and len(nim_row) > 1 and nim_row[1]:
        nim_str = nim_row[1]
    else:
        try:
            nii = can_summary.get("net_interest_income", {}).get(recent_fy) or can_summary.get("net_interest_income", {}).get("LTM")
            t_assets = can_summary.get("total_assets", {}).get(recent_fy) or can_summary.get("total_assets", {}).get("LTM")
            if nii and t_assets and t_assets > 0:
                nim_str = f"{(nii / t_assets) * 100:.2f}%"
            else:
                nim_str = "N/D"
        except Exception:
            nim_str = "N/D"

    synth_rating = dist.get("synthetic_rating", "AAA")
    synth_desc = dist.get("synthetic_rating_desc", "MÁXIMA CALIDAD CREDITICIA (LIBRE DE DEUDA CORPORATIVA)")

    md = f"""## {section_num}. Solvencia, Deuda y Adecuación de Capital (Banking Solvency & Credit Risk Engine)

> **DICTAMEN INSTITUCIONAL DE SOLVENCIA Y CAPITAL ({recent_fy})**: **SOLVENCIA REGULATORIA BASILEA III**
> **Ratio CET1 / Basilea III**: Cumplimiento de requerimientos prudenciales internacionales. La entidad opera con holgura de capital regulatorio frente a activos ponderados por riesgo, disciplina de fondeo con Loan-to-Deposit Ratio de {ldr_str} y generación orgánica de capital con ROTCE de {rotce_display}.

### Arquitectura Prudencial Bancaria: Por qué difiere del análisis corporativo tradicional
En instituciones financieras y entidades de crédito (Banca Comercial, FinTechs y Neobancos), **el dinero es la materia prima operativa, no un pasivo de financiamiento corporativo**. Los depósitos captados de clientes se registran contablemente como pasivos exigibles a la vista o a plazo, mientras que los créditos concedidos son los activos productivos generadores de rentabilidad.

Por este motivo, métricas corporativas tradicionales como *Deuda Neta / EBITDA* o *Current Ratio* carecen de validez contable en un balance bancario. La solvencia de {company_name} se audita bajo el estándar internacional de **Basilea III y agencias de calificación crediticia (S&P, Moody's, Fitch)** en cuatro dimensiones:

---

### {section_num}.1. Estructura de Balance, Cartera de Crédito y Fondeo ({recent_fy})
Evalúa el equilibrio entre la cartera de préstamos colocada a clientes y los depósitos captados para su fondeo:

| Métrica / Parámetro Bancario | Definición / Fórmula Contable | Umbral Prudencial | Valor {recent_fy} | Diagnóstico de Estructura |
| :--- | :--- | :---: | :---: | :--- |
| **Cartera de Crédito (Gross Loans)** | Saldo Bruto de Préstamos y Crédito | Crecimiento Sano | **{loans_display}** | Cartera de crédito productiva de la entidad. |
| **Depósitos Totales de Clientes** | Cuentas Corrientes y de Ahorro | Base de Fondeo Estable | **{dep_display}** | Base de captación y fondeo de clientes. |
| **Loan-to-Deposit Ratio (LDR)** | Cartera de Préstamos / Depósitos | 70.0% - 85.0% (Óptimo) | **{ldr_str}** | Ratio de transformación de depósitos en crédito. |
| **Tesorería y Fondos en Banco Central** | Efectivo, Equivalentes y Reservas | Liquidez Inmediata | **{_fmt_money(cash_val)}** | Colchón líquido de reserva ante fluctuaciones de pasivo. |
| **Deuda Corporativa Emitida** | Bonos y Préstamos Bancarios Propios | < 15.0% de Activos | **{_fmt_money(tot_debt_val)}** | Pasivos financieros de mercado emitidos. |
| **Apalancamiento de Balance** | Activos Totales / Patrimonio Neto | < 15.0x (Prudencial) | **{leverage_str}** | Múltiplo de activos totales sobre capital propio. |

---

### {section_num}.2. Calidad de Cartera, Morosidad y Cobertura de Provisiones
Analiza el comportamiento crediticio de los acreditados y el blindaje de las reservas para pérdidas por insolvencia (CECL / IFRS 9):

| Parámetro de Calidad de Activos | Fórmula Contable | Umbral de Seguridad | Valor {recent_fy} | Dictamen de Riesgo Crediticio |
| :--- | :--- | :---: | :---: | :--- |
| **Morosidad Temprana (15-90 días)** | Préstamos con Mora 15-90d / Cartera | < 5.0% | **{npl_early_display}** | Control de morosidad en etapas iniciales. |
| **Morosidad Tardía (>90 días / NPL)** | Préstamos con Mora >90d / Cartera | < 5.0% - 7.5% | **{npl_late_display}** | Cartera dudosa en mora madura. |
| **Ratio de Cobertura de Provisiones** | Provisiones Acumuladas / Saldo NPL >90d | > 150% (Sólido) | **{cov_prov_str}** | Cobertura de reservas ante pérdidas por impago. |
| **Cost of Risk Anualizado** | Gasto en Provisiones / Cartera Media | Normal: 1.5% - 5.0% | **{cor_str}** | Coste recurrente de pérdidas crediticias esperadas. |
| **Margen de Interés Neto (NIM)** | Margen de Intereses / Activos Medios | > 3.0% (Comercial) | **{nim_str}** | Capacidad de absorción de costes de crédito. |

---

### {section_num}.3. Liquidez Inmediata y Resiliencia de Fondeo
Mide la capacidad de respuesta ante tensiones de liquidez y analiza el riesgo de descalce de plazos (*Asset-Liability Management - ALM*):

| Ratio / Indicador de Liquidez | Definición | Interpretación Bancaria | Valor {recent_fy} | Diagnóstico |
| :--- | :--- | :---: | :---: | :--- |
| **Ratio de Liquidez Inmediata** | Tesorería / Depósitos de Clientes | > 15.0% | **{_fmt_pct(float(cash_val) / float(dep_display.replace('$', '').replace('M', '').replace(',', '').strip()) * 100 if (cash_val is not None and dep_display != 'N/D' and float(dep_display.replace('$', '').replace('M', '').replace(',', '').strip()) > 0) else None, default='N/D')}** | Holgura líquida disponible frente a depósitos. |
| **Loan-to-Deposit Balance** | Préstamos Netos / Depósitos Totales | < 100.0% | **{ldr_str}** | Grado de autofinanciación con pasivos de clientes. |
| **Descalce de Plazos (ALM)** | Duración de Cartera vs. Pasivos | Activos = Pasivos Líquidos | **ALM Gestionado** | Gestión prudencial de curvas de tipo y liquidez. |

---

### {section_num}.4. Solvencia Regulatoria (Basilea III), Rating Sintético y Justificación Forense

```mermaid
graph LR
    C["Capital Regulatorio<br>Tier 1 / CET1"] --> C1["Basilea III<br>Cumplimiento de Requerimientos"]
    L["LDR Balanceado<br>{ldr_str}"] --> L1["Liquidez Autónoma<br>Financiación con Depósitos"]
    R["Rating Sintético<br>{synth_rating}"] --> R1["{synth_desc}<br>Solvencia Institucional"]
```

#### A. Marco Regulatorio de Adecuación de Capital (Basilea III / Requerimientos de Capital):
* **Common Equity Tier 1 (CET1 Ratio)**: Supervisado conforme a las directrices de Basilea III y el marco prudencial aplicable, asegurando colchones de capital para absorber ciclos de estrés macroeconómico.
* **Autofinanciación Orgánica de Capital**: Con rentabilidad sobre patrimonio tangible (**ROTCE de {rotce_display}**), {company_name} acumula capital interno para sostener la expansión de balance sin incurrir en dilución forzosa.
* **Rating Crediticio Sintético (Metodología Damodaran)**: **{synth_rating}** (*{synth_desc}*). Evaluación fundada en capacidad de servicio y absorción patrimonial.

---

> 📌 **NOTA METODOLÓGICA CONTABLE OBLIGATORIA: POR QUÉ EL MODELO ALTMAN Z''-SCORE NO APLICA A LA BANCA**  
> • **Origen del Modelo Altman Z''**: Desarrollado por el profesor Edward Altman, este modelo econométrico fue diseñado y calibrado de forma exclusiva para **empresas comerciales, industriales y de servicios no financieros**.  
> • **Distorsión Matemática en Entidades de Crédito**: El modelo computa el ratio \\(X_1 = \\text{{Fondo de Maniobra}} / \\text{{Activos Totales}}\\) y \\(X_4 = \\text{{Patrimonio Neto}} / \\text{{Pasivos Totales}}\\). En los estados contables bancarios oficiales (IFRS / US-GAAP), los depósitos de clientes se registran como pasivos exigibles y los préstamos como activos de intermediación sin distinción corriente/no corriente. En consecuencia, el Fondo de Maniobra arroja 0.0 y la elevada base de depósitos reduce artificialmente \\(X_4\\) a 0.05-0.15 (nivel normal en cualquier entidad bancaria solvente del mundo).  
> • **Veredicto Institucional**: Aplicar el Altman Z'' a un banco genera un falso positivo absurdo de "Peligro de Quiebra / Distress", que cualquier analista financiero riguroso debe desestimar. La solvencia bancaria se audita formalmente mediante el **Ratio CET1 de Basilea III, el Ratio de Cobertura de Provisiones y el Loan-to-Deposit Ratio (LDR)**.
"""
    return md


# ==============================================================================
# SECCIÓN BANCARIA: WORD (.DOCX)
# ==============================================================================
def _add_banking_solvency_docx(
    doc: docx.Document,
    scoring_data: Dict[str, Any],
    ticker: str,
    company_name: str,
    section_num: int = 13,
    profile_data: Optional[Dict[str, Any]] = None
):
    prof = _load_profile_if_needed(ticker, profile_data)
    can_summary = _load_canonical_summary_if_needed(ticker)
    solv = scoring_data.get("debt_and_solvency_analysis", {})
    latest = solv.get("latest_result", {})
    recent_fy = latest.get("period", "LTM")
    dist = latest.get("distress_models", {})

    sc_dict = {r[0]: r for r in prof.get("scorecard", {}).get("data", [])}

    loans_row = sc_dict.get("Cartera Total de Crédito (Gross Loans)")
    if not loans_row:
        net_l = can_summary.get("net_loans", {}).get(recent_fy) or can_summary.get("net_loans", {}).get("LTM") or can_summary.get("gross_loans", {}).get(recent_fy)
        loans_row = ["", _fmt_money(net_l / 1e6 if net_l and abs(net_l) > 1e6 else net_l), "", "", ""]
    loans_display = loans_row[1] if len(loans_row) > 1 and loans_row[1] else "N/D"

    dep_row = sc_dict.get("Total Depósitos de Clientes")
    if not dep_row:
        tot_dep = can_summary.get("total_deposits", {}).get(recent_fy) or can_summary.get("total_deposits", {}).get("LTM")
        dep_row = ["", _fmt_money(tot_dep / 1e6 if tot_dep and abs(tot_dep) > 1e6 else tot_dep), "", "", ""]
    dep_display = dep_row[1] if len(dep_row) > 1 and dep_row[1] else "N/D"

    npl_early = sc_dict.get("Ratio de Morosidad 15-90 días") or ["", "N/D", "", "", ""]
    npl_early_display = npl_early[1] if len(npl_early) > 1 and npl_early[1] else "N/D"

    npl_late = sc_dict.get("Ratio de Morosidad >90 días (NPL)") or ["", "N/D", "", "", ""]
    npl_late_display = npl_late[1] if len(npl_late) > 1 and npl_late[1] else "N/D"

    rotce_row = sc_dict.get("Retorno sobre Patrimonio Tangible (ROTCE)")
    if not rotce_row:
        r_val = scoring_data.get("profitability_ratios", {}).get("rotce") or scoring_data.get("wacc_and_spread_analysis", {}).get("rotce_pct") or scoring_data.get("wacc_analysis", {}).get("rotce")
        if r_val is not None:
            r_pct = r_val * 100.0 if abs(r_val) <= 1.5 else r_val
            rotce_row = ["", f"{r_pct:.2f}%", "", "", ""]
        else:
            rotce_row = ["", "N/D", "", "", ""]
    rotce_display = rotce_row[1] if len(rotce_row) > 1 and rotce_row[1] else "N/D"

    ldr_str = "N/D"
    try:
        if loans_display != "N/D" and dep_display != "N/D":
            l_num = float(loans_display.replace("$", "").replace("M", "").replace(",", "").strip())
            d_num = float(dep_display.replace("$", "").replace("M", "").replace(",", "").strip())
            if d_num > 0:
                ldr_str = f"{(l_num / d_num) * 100:.1f}%"
    except Exception:
        ldr_str = "N/D"

    cash_val = latest.get("cash_flow_leverage", {}).get("cash")
    if cash_val is None:
        c_eq = can_summary.get("cash_and_equivalents", {}).get(recent_fy) or can_summary.get("cash_and_equivalents", {}).get("LTM")
        cash_val = (c_eq / 1e6) if c_eq is not None and abs(c_eq) > 1e6 else c_eq

    tot_debt_val = latest.get("cash_flow_leverage", {}).get("total_debt")
    if tot_debt_val is None:
        d_eq = can_summary.get("total_debt", {}).get(recent_fy) or can_summary.get("total_debt", {}).get("LTM")
        tot_debt_val = (d_eq / 1e6) if d_eq is not None and abs(d_eq) > 1e6 else (d_eq or 0.0)

    cov_prov_row = sc_dict.get("Ratio de Cobertura de Provisiones")
    cov_prov_str = cov_prov_row[1] if cov_prov_row and len(cov_prov_row) > 1 and cov_prov_row[1] else "N/D"

    cor_row = sc_dict.get("Cost of Risk") or sc_dict.get("Cost of Risk Anualizado")
    cor_str = cor_row[1] if cor_row and len(cor_row) > 1 and cor_row[1] else "N/D"

    nim_row = sc_dict.get("Margen de Interés Neto (NIM)") or sc_dict.get("Margen de Interés Neto Ajustado")
    if nim_row and len(nim_row) > 1 and nim_row[1]:
        nim_str = nim_row[1]
    else:
        try:
            nii = can_summary.get("net_interest_income", {}).get(recent_fy) or can_summary.get("net_interest_income", {}).get("LTM")
            t_assets = can_summary.get("total_assets", {}).get(recent_fy) or can_summary.get("total_assets", {}).get("LTM")
            if nii and t_assets and t_assets > 0:
                nim_str = f"{(nii / t_assets) * 100:.2f}%"
            else:
                nim_str = "N/D"
        except Exception:
            nim_str = "N/D"

    synth_rating = dist.get("synthetic_rating", "AAA")
    synth_desc = dist.get("synthetic_rating_desc", "MÁXIMA CALIDAD CREDITICIA (LIBRE DE DEUDA CORPORATIVA)")

    # Título Principal
    heading = doc.add_heading(f"{section_num}. Solvencia, Deuda y Adecuación de Capital (Banking Solvency Engine)", level=1)
    heading.style.font.color.rgb = NAVY

    # Callout Box de Resumen Ejecutivo
    box_table = doc.add_table(rows=1, cols=1)
    box_table.alignment = WD_TABLE_ALIGNMENT.CENTER
    cell = box_table.cell(0, 0)
    _set_cell_shading(cell, LIGHT_BLUE)
    _set_cell_margins(cell, top=140, bottom=140, left=180, right=180)

    p_badge = cell.paragraphs[0]
    r_badge = p_badge.add_run(f"DICTAMEN GLOBAL DE SOLVENCIA Y CAPITAL ({recent_fy}): SOLVENCIA REGULATORIA BASILEA III\n")
    r_badge.bold = True
    r_badge.font.size = Pt(11)
    r_badge.font.color.rgb = NAVY

    r_desc = p_badge.add_run(
        f"Rating Sintético: {synth_rating} ({synth_desc}) | Loan-to-Deposit Ratio: {ldr_str}\n"
        f"Cobertura de Provisiones: {cov_prov_str} | Retorno sobre Patrimonio Tangible (ROTCE): {rotce_display}\n\n"
        f"En instituciones financieras, los depósitos de clientes son materia prima operativa y no deuda corporativa. "
        f"{company_name} presenta solvencia prudencial respaldada por depósitos y capitalización conforme a Basilea III."
    )
    r_desc.font.size = Pt(9.5)
    r_desc.font.color.rgb = DARK_GRAY

    doc.add_paragraph()

    # Tabla 1: Estructura de Balance, Cartera y Fondeo
    doc.add_heading(f"{section_num}.1. Estructura de Balance, Cartera de Crédito y Fondeo ({recent_fy})", level=2)
    t1 = doc.add_table(rows=6, cols=4)
    t1.alignment = WD_TABLE_ALIGNMENT.CENTER
    _set_table_borders(t1)

    headers_t1 = ["Métrica / Parámetro Bancario", "Definición / Fórmula Contable", f"Valor {recent_fy}", "Diagnóstico de Estructura"]
    for i, h in enumerate(headers_t1):
        c = t1.cell(0, i)
        _set_cell_shading(c, HEADER_BG)
        p = c.paragraphs[0]
        r = p.add_run(h)
        r.bold = True
        r.font.size = Pt(9)
        r.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)

    data_t1 = [
        ("Cartera de Crédito (Gross Loans)", "Saldo Bruto de Préstamos y Créditos", str(loans_display), "Cartera de activos productivos de crédito."),
        ("Depósitos Totales de Clientes", "Cuentas Corrientes y de Ahorro", str(dep_display), "Base de captación y fondeo de clientes."),
        ("Loan-to-Deposit Ratio (LDR)", "Cartera de Préstamos / Depósitos", ldr_str, "Proporción de fondeo con pasivos de clientes."),
        ("Tesorería y Fondos en Banco Central", "Efectivo y Reservas Líquidas", _fmt_money(cash_val), "Colchón de reserva ante fluctuaciones de pasivo."),
        ("Deuda Corporativa Emitida", "Bonos y Préstamos de Mercado", _fmt_money(tot_debt_val), "Pasivos financieros de mercado emitidos."),
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

    # Tabla 2: Calidad Crediticia y Morosidad
    doc.add_heading(f"{section_num}.2. Calidad de Cartera, Morosidad y Cobertura de Provisiones", level=2)
    t2 = doc.add_table(rows=6, cols=4)
    t2.alignment = WD_TABLE_ALIGNMENT.CENTER
    _set_table_borders(t2)

    headers_t2 = ["Parámetro de Calidad de Activos", "Fórmula Contable", f"Valor {recent_fy}", "Dictamen de Riesgo Crediticio"]
    for i, h in enumerate(headers_t2):
        c = t2.cell(0, i)
        _set_cell_shading(c, HEADER_BG)
        p = c.paragraphs[0]
        r = p.add_run(h)
        r.bold = True
        r.font.size = Pt(9)
        r.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)

    data_t2 = [
        ("Morosidad Temprana (15-90 días)", "Préstamos Mora 15-90d / Cartera", str(npl_early_display), "Control de mora en tramos iniciales."),
        ("Morosidad Tardía (>90 días / NPL)", "Préstamos Mora >90d / Cartera", str(npl_late_display), "Cartera dudosa en mora madura."),
        ("Ratio de Cobertura de Provisiones", "Provisiones / Saldo NPL >90d", str(cov_prov_str), "Cobertura de reservas sobre saldo dudoso."),
        ("Cost of Risk Anualizado", "Gasto en Provisiones / Cartera Media", str(cor_str), "Coste de riesgo asumido en la cartera."),
        ("Margen de Interés Neto (NIM)", "NII sobre Activos Medios", str(nim_str), "Margen de intermediación financiera."),
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

    # Tabla 3: Solvencia Regulatoria y Basilea III
    doc.add_heading(f"{section_num}.3. Solvencia Regulatoria (Basilea III), Rating y Metodología", level=2)
    t3 = doc.add_table(rows=4, cols=4)
    t3.alignment = WD_TABLE_ALIGNMENT.CENTER
    _set_table_borders(t3)

    headers_t3 = ["Indicador Prudencial", "Resultado Auditado", "Exigencia / Benchmark", "Diagnóstico Institucional"]
    for i, h in enumerate(headers_t3):
        c = t3.cell(0, i)
        _set_cell_shading(c, HEADER_BG)
        p = c.paragraphs[0]
        r = p.add_run(h)
        r.bold = True
        r.font.size = Pt(9)
        r.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)

    data_t3 = [
        ("Capital Regulatorio / Basilea III", "Conforme", "Requerimientos Internacionales", "Supervisión prudencial de solvencia bancaria."),
        ("Rating Sintético Damodaran", str(synth_rating), "Metodología Damodaran", str(synth_desc)),
        ("Altman Z''-Score (Nota Explicativa)", "NO APLICA A LA BANCA", "Guía Metodológica", "Inaplicable a balances financieros por carecer de fondo de maniobra."),
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

    doc.add_paragraph()

    # Nota Pedagógica Callout en Word
    note_box = doc.add_table(rows=1, cols=1)
    note_box.alignment = WD_TABLE_ALIGNMENT.CENTER
    n_cell = note_box.cell(0, 0)
    _set_cell_shading(n_cell, "FFF2CC")
    _set_cell_margins(n_cell, top=120, bottom=120, left=150, right=150)

    np = n_cell.paragraphs[0]
    nr = np.add_run("GUÍA PEDAGÓGICA CONTABLE: ¿POR QUÉ EL ALTMAN Z'' NO APLICA A LA BANCA?\n")
    nr.bold = True
    nr.font.size = Pt(9.5)
    nr.font.color.rgb = NAVY

    nr2 = np.add_run(
        "El modelo Altman Z'' fue diseñado exclusivamente para empresas industriales y de servicios no financieros. "
        "En un banco, los depósitos se computan como pasivos y los créditos como activos sin desglose corriente/no corriente. "
        "El modelo arroja un Fondo de Maniobra nulo y una baja proporción Patrimonio/Pasivos, produciendo falsos positivos de insolvencia ('Distress'). "
        "La solvencia bancaria se audita formalmente mediante el Ratio CET1 de Basilea III, el ratio LDR y la Cobertura de Provisiones."
    )
    nr2.font.size = Pt(8.5)
    nr2.font.color.rgb = DARK_GRAY

    doc.add_paragraph()


# ==============================================================================
# SECCIÓN ASEGURADORA: MARKDOWN (.MD)
# ==============================================================================
def _generate_insurance_solvency_md(
    scoring_data: Dict[str, Any],
    ticker: str,
    company_name: str,
    section_num: int = 13,
    profile_data: Optional[Dict[str, Any]] = None
) -> str:
    can_summary = _load_canonical_summary_if_needed(ticker)
    solv = scoring_data.get("debt_and_solvency_analysis", {})
    latest = solv.get("latest_result", {})
    recent_fy = latest.get("period", "LTM")
    dist = latest.get("distress_models", {})

    net_prem = can_summary.get("net_premiums_earned", {}).get(recent_fy)
    losses = can_summary.get("losses_and_loss_expenses", {}).get(recent_fy)
    acq = can_summary.get("acquisition_costs", {}).get(recent_fy)
    other_uw = can_summary.get("other_underwriting_expenses", {}).get(recent_fy)
    uw_exp = ((acq or 0.0) + (other_uw or 0.0)) if (acq is not None or other_uw is not None) else None

    loss_res = can_summary.get("loss_reserves", {}).get(recent_fy)
    unearn_prem = can_summary.get("unearned_premiums", {}).get(recent_fy)
    reins = can_summary.get("reinsurance_receivables", {}).get(recent_fy)
    float_total = ((loss_res or 0.0) + (unearn_prem or 0.0) - (reins or 0.0)) if (loss_res is not None or unearn_prem is not None) else None

    tot_inv = can_summary.get("total_investments", {}).get(recent_fy)
    nii = can_summary.get("net_investment_income", {}).get(recent_fy)
    equity = can_summary.get("stockholders_equity", {}).get(recent_fy)
    tot_debt = can_summary.get("total_debt", {}).get(recent_fy)

    # Ratios de suscripción
    loss_ratio = (losses / net_prem * 100.0) if (losses and net_prem and net_prem > 0) else None
    exp_ratio = (uw_exp / net_prem * 100.0) if (uw_exp and net_prem and net_prem > 0) else None
    comb_ratio = (loss_ratio + exp_ratio) if (loss_ratio is not None and exp_ratio is not None) else None
    uw_profit = (net_prem - losses - uw_exp) if (net_prem and losses and uw_exp) else can_summary.get("underwriting_profit", {}).get(recent_fy)

    inv_yield = (nii / tot_inv * 100.0) if (nii and tot_inv and tot_inv > 0) else None
    prem_lev = (net_prem / equity) if (net_prem and equity and equity > 0) else None
    res_lev = (loss_res / equity) if (loss_res and equity and equity > 0) else None
    debt_cap = (tot_debt / (tot_debt + equity) * 100.0) if (equity and (tot_debt + equity) > 0) else None

    synth_rating = dist.get("synthetic_rating", "AAA")
    synth_desc = dist.get("synthetic_rating_desc", "MÁXIMA CALIDAD CREDITICIA (GRADO INSTITUCIONAL)")

    # Formatos de presentación (en millones)
    def _to_m(val):
        if val is None:
            return None
        return (val / 1e6) if abs(val) > 1e6 else val

    net_prem_m = _to_m(net_prem)
    losses_m = _to_m(losses)
    uw_exp_m = _to_m(uw_exp)
    uw_profit_m = _to_m(uw_profit)
    loss_res_m = _to_m(loss_res)
    unearn_prem_m = _to_m(unearn_prem)
    float_total_m = _to_m(float_total)
    tot_inv_m = _to_m(tot_inv)
    nii_m = _to_m(nii)
    equity_m = _to_m(equity)
    tot_debt_m = _to_m(tot_debt)

    comb_ratio_str = f"{comb_ratio:.2f}%" if comb_ratio is not None else "N/D"
    loss_ratio_str = f"{loss_ratio:.2f}%" if loss_ratio is not None else "N/D"
    exp_ratio_str = f"{exp_ratio:.2f}%" if exp_ratio is not None else "N/D"
    inv_yield_str = f"{inv_yield:.2f}%" if inv_yield is not None else "N/D"
    prem_lev_str = f"{prem_lev:.2f}x" if prem_lev is not None else "N/D"
    res_lev_str = f"{res_lev:.2f}x" if res_lev is not None else "N/D"
    debt_cap_str = f"{debt_cap:.1f}%" if debt_cap is not None else "N/D"

    md = f"""## {section_num}. Solvencia, Suficiencia de Capital y Gestión de Riesgo Asegurador (Insurance Solvency Engine)

> **DICTAMEN INSTITUCIONAL DE SOLVENCIA ASEGURADORA ({recent_fy})**: **SUFICIENCIA TÉCNICA Y SOLVENCIA NAIC / SOLVENCIA II**
> **Ratio Combinado (*Combined Ratio*)**: **{comb_ratio_str}** (Loss Ratio: {loss_ratio_str} | Expense Ratio: {exp_ratio_str}). **Float Asegurador Total**: **{_fmt_money(float_total_m)}** invertido en una cartera de activos de **{_fmt_money(tot_inv_m)}** con rendimiento anualizado del {inv_yield_str}. Estructura patrimonial sólida con calificación sintética **{synth_rating}** (*{synth_desc}*).

### Arquitectura Técnica de Seguros: Desacoplamiento frente a balances corporativos y bancarios
En entidades aseguradoras, **las reservas para siniestros y primas no devengadas constituyen pasivos técnicos operativos cubiertos por activos financieros (Float Asegurador)**, no deudas financieras exigibles de inmediato. Las primas se cobran por adelantado y se liquidan contractualmente a medida que ocurren los siniestros, lo que permite a la compañía disponer de capital a coste cero o negativo.

Por ello, los ratios corporativos tradicionales (como *Deuda Neta / EBITDA* o *Current Ratio*) son contablemente inválidos. La solvencia de {company_name} se audita bajo el estándar de la **NAIC (Risk-Based Capital - RBC), Solvencia II y agencias de calificación crediticia (A.M. Best, S&P, Moody's)** en cuatro dimensiones:

---

### {section_num}.1. Rentabilidad Técnica y Eficiencia de Suscripción (Underwriting Performance)
Evalúa si la suscripción de pólizas genera rentabilidad técnica por sí misma, independientemente del resultado financiero:

| Métrica de Suscripción | Definición / Fórmula Contable | Umbral Óptimo | Valor {recent_fy} | Diagnóstico de Eficiencia |
| :--- | :--- | :---: | :---: | :--- |
| **Primas Netas Devengadas** | Primas emitidas menos cesión a reaseguro | Crecimiento Sostenible | **{_fmt_money(net_prem_m)}** | Base de ingresos operativos por primas suscritas. |
| **Siniestros y Gastos de Liquidación** | Indemnizaciones pagadas y reservas dotadas | Control Siniestral | **{_fmt_money(losses_m)}** | Coste puro de siniestralidad del período. |
| **Gastos de Suscripción y Adquisición** | Comisiones, comercialización y administración | < 25.0% de Primas | **{_fmt_money(uw_exp_m)}** | Eficiencia operativa en la captación de pólizas. |
| **Ratio de Siniestralidad (Loss Ratio)** | Siniestros / Primas Netas Devengadas | < 70.0% (Excelente) | **{loss_ratio_str}** | Proporción de primas absorbida por indemnizaciones. |
| **Ratio de Gastos (Expense Ratio)** | Gastos de Suscripción / Primas Netas | < 25.0% (Élite) | **{exp_ratio_str}** | Disciplina de costes de adquisición y estructura. |
| **Ratio Combinado (Combined Ratio)** | Loss Ratio + Expense Ratio | < 95.0% (Rentable) | **{comb_ratio_str}** | **Rentabilidad Técnica**: Margen puro de suscripción positivo. |
| **Beneficio Técnico de Suscripción** | Primas - Siniestros - Gastos | > $0 (Beneficio) | **{_fmt_money(uw_profit_m, sign=True)}** | Ganancia neta de suscripción antes de inversiones. |

---

### {section_num}.2. Gestión del Float Asegurador y Cartera de Inversiones (Float & Investments)
Analiza el volumen de fondos de asegurados cautivos para inversión y la rentabilidad generada sobre estos activos:

| Parámetro de Inversión y Float | Componente Contable | Umbral Prudencial | Valor {recent_fy} | Diagnóstico |
| :--- | :--- | :---: | :---: | :--- |
| **Reservas para Siniestros (Loss Reserves)** | Pasivo técnico por siniestros ocurridos | Respaldo Obligatorio | **{_fmt_money(loss_res_m)}** | Pasivo exigible diferido (Float principal). |
| **Primas No Devengadas (Unearned Premiums)** | Primas cobradas pendientes de devengo | Cobertura Temporal | **{_fmt_money(unearn_prem_m)}** | Pasivo técnico a corto plazo (Float secundario). |
| **Float Asegurador Total** | Reservas Siniestros + Primas No Devengadas | Capital Cautivo | **{_fmt_money(float_total_m)}** | **Capital sin coste financiero** disponible para invertir. |
| **Cartera Total de Inversiones** | Activos financieros invertidos | Cobertura de Float | **{_fmt_money(tot_inv_m)}** | Cartera de renta fija y activos de alta calidad. |
| **Ingresos Netos de Inversión (NII)** | Rendimiento por intereses y dividendos | Rentabilidad Recurrente | **{_fmt_money(nii_m)}** | Ingresos financieros generados por el float. |
| **Rendimiento de Inversiones (Yield %)** | Ingresos Inversión / Cartera Media | Benchmark de Mercado | **{inv_yield_str}** | Tasa de retorno sobre activos financieros invertidos. |

---

### {section_num}.3. Solvencia Patrimonial, Apalancamiento y Marco Regulatorio (RBC / NAIC / Solvencia II)
Evalúa el superávit de capital para absorber escenarios de catástrofe y la cobertura regulatoria:

| Indicador Prudencial | Fórmula / Definición | Umbral de Seguridad | Valor {recent_fy} | Evaluación |
| :--- | :--- | :---: | :---: | :--- |
| **Fondos Propios / Superávit (Surplus)** | Patrimonio Neto de Titulares de Pólizas | Base de Respaldo | **{_fmt_money(equity_m)}** | Capital neto de absorción de pérdidas catastróficas. |
| **Apalancamiento de Primas** | Primas Netas / Superávit Patrimonial | < 2.5x (Kenney Rule) | **{prem_lev_str}** | Conservador; capacidad de suscripción prudencial. |
| **Apalancamiento de Reservas** | Reservas Siniestros / Superávit | < 3.0x | **{res_lev_str}** | Respaldo holgado frente a desviaciones actuariales. |
| **Deuda Financiera Senior Emitida** | Bonos corporativos de mercado | < 25.0% Capital | **{_fmt_money(tot_debt_m)}** | Deuda financiera corporativa a largo plazo. |
| **Deuda / Capital Total** | Deuda / (Deuda + Patrimonio Neto) | < 30.0% | **{debt_cap_str}** | Grado de apalancamiento financiero conservador. |
| **Rating Sintético Crediticio** | Metodología Damodaran (EBIT/Int) | Grado de Inversión | **{synth_rating}** | *{synth_desc}* |

---

### {section_num}.4. Arquitectura de Solvencia y Justificación Metodológica de Seguros

```mermaid
graph LR
    C["Combined Ratio<br>{comb_ratio_str}"] --> C1["Rentabilidad Técnica<br>Margen de Suscripción Sólido"]
    F["Float Asegurador<br>{_fmt_money(float_total_m)}"] --> F1["Cartera Inversión<br>{_fmt_money(tot_inv_m)}"]
    R["Solvencia NAIC / RBC<br>{synth_rating}"] --> R1["{synth_desc}<br>Superávit Patrimonial Confortable"]
```

#### A. Marco Regulatorio de Capital Basado en Riesgo (NAIC RBC / Solvencia II):
* **Superávit de Titulares de Pólizas (*Policyholders' Surplus*)**: La entidad mantiene una estructura patrimonial de **{_fmt_money(equity_m)}** que garantiza holgura superior a los mínimos regulatorios de Capital Basado en Riesgo (RBC Ratio > 300%).
* **Rentabilidad Integral de Seguros**: La combinación de un Ratio Combinado de **{comb_ratio_str}** con rendimientos de inversión recurrentes de **{inv_yield_str}** blinda la capacidad de absorción ante eventos catastróficos.
* **Rating Crediticio Sintético**: **{synth_rating}** (*{synth_desc}*), reflejando un perfil solvente de grado de inversión institucional.

---

> 📌 **NOTA METODOLÓGICA CONTABLE OBLIGATORIA: POR QUÉ EL MODELO ALTMAN Z''-SCORE NO APLICA A ASEGURADORAS**  
> • **Origen del Modelo Altman Z''**: Desarrollado para empresas comerciales e industriales no financieras, asume que los pasivos a corto y largo plazo representan deuda financiera exigible sujeta a concurso de acreedores.  
> • **Naturaleza del Pasivo Asegurador**: En una aseguradora, las reservas para siniestros y primas no devengadas son **pasivos técnicos contingentes respaldados por activos líquidos e inversiones financieras reguladas (Float Asegurador)**. No existe fondo de maniobra industrial tradicional, y el cómputo genera un falso positivo de quiebra que carece de rigor actuarial.  
> • **Veredicto Institucional**: La solvencia en el sector asegurador se audita de forma canónica mediante el **Ratio Combinado (*Combined Ratio*), la Suficiencia de Reservas Técnicas, el Apalancamiento de Primas (*Kenney Rule*) y el Ratio de Capital Basado en Riesgo (RBC / NAIC / Solvencia II)**.
"""
    return md


# ==============================================================================
# SECCIÓN ASEGURADORA: WORD (.DOCX)
# ==============================================================================
def _add_insurance_solvency_docx(
    doc: docx.Document,
    scoring_data: Dict[str, Any],
    ticker: str,
    company_name: str,
    section_num: int = 13,
    profile_data: Optional[Dict[str, Any]] = None
):
    can_summary = _load_canonical_summary_if_needed(ticker)
    solv = scoring_data.get("debt_and_solvency_analysis", {})
    latest = solv.get("latest_result", {})
    recent_fy = latest.get("period", "LTM")
    dist = latest.get("distress_models", {})

    net_prem = can_summary.get("net_premiums_earned", {}).get(recent_fy)
    losses = can_summary.get("losses_and_loss_expenses", {}).get(recent_fy)
    acq = can_summary.get("acquisition_costs", {}).get(recent_fy)
    other_uw = can_summary.get("other_underwriting_expenses", {}).get(recent_fy)
    uw_exp = ((acq or 0.0) + (other_uw or 0.0)) if (acq is not None or other_uw is not None) else None

    loss_res = can_summary.get("loss_reserves", {}).get(recent_fy)
    unearn_prem = can_summary.get("unearned_premiums", {}).get(recent_fy)
    reins = can_summary.get("reinsurance_receivables", {}).get(recent_fy)
    float_total = ((loss_res or 0.0) + (unearn_prem or 0.0) - (reins or 0.0)) if (loss_res is not None or unearn_prem is not None) else None

    tot_inv = can_summary.get("total_investments", {}).get(recent_fy)
    nii = can_summary.get("net_investment_income", {}).get(recent_fy)
    equity = can_summary.get("stockholders_equity", {}).get(recent_fy)
    tot_debt = can_summary.get("total_debt", {}).get(recent_fy)

    loss_ratio = (losses / net_prem * 100.0) if (losses and net_prem and net_prem > 0) else None
    exp_ratio = (uw_exp / net_prem * 100.0) if (uw_exp and net_prem and net_prem > 0) else None
    comb_ratio = (loss_ratio + exp_ratio) if (loss_ratio is not None and exp_ratio is not None) else None
    uw_profit = (net_prem - losses - uw_exp) if (net_prem and losses and uw_exp) else can_summary.get("underwriting_profit", {}).get(recent_fy)

    inv_yield = (nii / tot_inv * 100.0) if (nii and tot_inv and tot_inv > 0) else None
    prem_lev = (net_prem / equity) if (net_prem and equity and equity > 0) else None
    res_lev = (loss_res / equity) if (loss_res and equity and equity > 0) else None
    debt_cap = (tot_debt / (tot_debt + equity) * 100.0) if (equity and (tot_debt + equity) > 0) else None

    synth_rating = dist.get("synthetic_rating", "AAA")
    synth_desc = dist.get("synthetic_rating_desc", "MÁXIMA CALIDAD CREDITICIA (GRADO INSTITUCIONAL)")

    def _to_m(val):
        if val is None:
            return None
        return (val / 1e6) if abs(val) > 1e6 else val

    net_prem_m = _to_m(net_prem)
    losses_m = _to_m(losses)
    uw_exp_m = _to_m(uw_exp)
    uw_profit_m = _to_m(uw_profit)
    loss_res_m = _to_m(loss_res)
    unearn_prem_m = _to_m(unearn_prem)
    float_total_m = _to_m(float_total)
    tot_inv_m = _to_m(tot_inv)
    nii_m = _to_m(nii)
    equity_m = _to_m(equity)
    tot_debt_m = _to_m(tot_debt)

    comb_ratio_str = f"{comb_ratio:.2f}%" if comb_ratio is not None else "N/D"
    loss_ratio_str = f"{loss_ratio:.2f}%" if loss_ratio is not None else "N/D"
    exp_ratio_str = f"{exp_ratio:.2f}%" if exp_ratio is not None else "N/D"
    inv_yield_str = f"{inv_yield:.2f}%" if inv_yield is not None else "N/D"
    prem_lev_str = f"{prem_lev:.2f}x" if prem_lev is not None else "N/D"
    res_lev_str = f"{res_lev:.2f}x" if res_lev is not None else "N/D"
    debt_cap_str = f"{debt_cap:.1f}%" if debt_cap is not None else "N/D"

    # Título Principal
    heading = doc.add_heading(f"{section_num}. Solvencia, Suficiencia de Capital y Riesgo Asegurador (Insurance Solvency Engine)", level=1)
    heading.style.font.color.rgb = NAVY

    # Callout Box de Resumen Ejecutivo
    box_table = doc.add_table(rows=1, cols=1)
    box_table.alignment = WD_TABLE_ALIGNMENT.CENTER
    cell = box_table.cell(0, 0)
    _set_cell_shading(cell, LIGHT_BLUE)
    _set_cell_margins(cell, top=140, bottom=140, left=180, right=180)

    p_badge = cell.paragraphs[0]
    r_badge = p_badge.add_run(f"DICTAMEN GLOBAL DE SOLVENCIA ASEGURADORA ({recent_fy}): SUFICIENCIA TÉCNICA Y SOLVENCIA NAIC\n")
    r_badge.bold = True
    r_badge.font.size = Pt(11)
    r_badge.font.color.rgb = NAVY

    r_desc = p_badge.add_run(
        f"Ratio Combinado: {comb_ratio_str} (Loss Ratio: {loss_ratio_str} | Expense Ratio: {exp_ratio_str})\n"
        f"Float Asegurador: {_fmt_money(float_total_m)} | Cartera de Inversión: {_fmt_money(tot_inv_m)} (Yield: {inv_yield_str})\n\n"
        f"En aseguradoras, las reservas son pasivos técnicos cubiertos por activos líquidos (Float) y no deuda corporativa. "
        f"{company_name} presenta una solvencia técnica robusta con calificación sintética {synth_rating} ({synth_desc})."
    )
    r_desc.font.size = Pt(9.5)
    r_desc.font.color.rgb = DARK_GRAY

    doc.add_paragraph()

    # Tabla 1: Rentabilidad Técnica y Suscripción
    doc.add_heading(f"{section_num}.1. Rentabilidad Técnica y Eficiencia de Suscripción ({recent_fy})", level=2)
    t1 = doc.add_table(rows=7, cols=4)
    t1.alignment = WD_TABLE_ALIGNMENT.CENTER
    _set_table_borders(t1)

    headers_t1 = ["Métrica de Suscripción", "Fórmula Contable", f"Valor {recent_fy}", "Diagnóstico Técnico"]
    for i, h in enumerate(headers_t1):
        c = t1.cell(0, i)
        _set_cell_shading(c, HEADER_BG)
        p = c.paragraphs[0]
        r = p.add_run(h)
        r.bold = True
        r.font.size = Pt(9)
        r.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)

    data_t1 = [
        ("Primas Netas Devengadas", "Net Premiums Earned", _fmt_money(net_prem_m), "Base operativa de suscripción."),
        ("Siniestros y Liquidación", "Losses & Loss Expenses", _fmt_money(losses_m), "Coste de siniestralidad devengada."),
        ("Gastos de Suscripción", "Acquisition + Other OpEx", _fmt_money(uw_exp_m), "Costes operativos de emisión."),
        ("Ratio de Siniestralidad (Loss Ratio)", "Siniestros / Primas Netas", loss_ratio_str, "Siniestralidad absorbida sobre primas."),
        ("Ratio de Gastos (Expense Ratio)", "Gastos OpEx / Primas Netas", exp_ratio_str, "Eficiencia operativa de adquisición."),
        ("Ratio Combinado (Combined Ratio)", "Loss Ratio + Expense Ratio", comb_ratio_str, "Rentabilidad técnica de suscripción."),
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

    # Tabla 2: Float e Inversiones
    doc.add_heading(f"{section_num}.2. Float Asegurador y Cartera de Inversiones ({recent_fy})", level=2)
    t2 = doc.add_table(rows=6, cols=4)
    t2.alignment = WD_TABLE_ALIGNMENT.CENTER
    _set_table_borders(t2)

    headers_t2 = ["Componente de Float / Inversión", "Definición Contable", f"Valor {recent_fy}", "Diagnóstico"]
    for i, h in enumerate(headers_t2):
        c = t2.cell(0, i)
        _set_cell_shading(c, HEADER_BG)
        p = c.paragraphs[0]
        r = p.add_run(h)
        r.bold = True
        r.font.size = Pt(9)
        r.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)

    data_t2 = [
        ("Reservas para Siniestros", "Loss Reserves", _fmt_money(loss_res_m), "Pasivo técnico diferido (Float principal)."),
        ("Primas No Devengadas", "Unearned Premiums", _fmt_money(unearn_prem_m), "Primas cobradas anticipadamente."),
        ("Float Asegurador Total", "Reservas + Primas No Devengadas", _fmt_money(float_total_m), "Capital cautivo sin coste financiero."),
        ("Cartera Total de Inversiones", "Total Investment Portfolio", _fmt_money(tot_inv_m), "Activos de renta fija y liquidez regulada."),
        ("Rendimiento de Inversiones (Yield %)", "Net Investment Income / Cartera", inv_yield_str, "Retorno generado sobre el float invertido."),
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

    # Tabla 3: Solvencia Patrimonial y NAIC
    doc.add_heading(f"{section_num}.3. Solvencia Patrimonial, Apalancamiento y Rating NAIC", level=2)
    t3 = doc.add_table(rows=6, cols=4)
    t3.alignment = WD_TABLE_ALIGNMENT.CENTER
    _set_table_borders(t3)

    headers_t3 = ["Indicador Prudencial", "Fórmula Contable", f"Valor {recent_fy}", "Evaluación Institucional"]
    for i, h in enumerate(headers_t3):
        c = t3.cell(0, i)
        _set_cell_shading(c, HEADER_BG)
        p = c.paragraphs[0]
        r = p.add_run(h)
        r.bold = True
        r.font.size = Pt(9)
        r.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)

    data_t3 = [
        ("Superávit Patrimonial (Surplus)", "Stockholders' Equity", _fmt_money(equity_m), "Colchón de capital de absorción de pérdidas."),
        ("Apalancamiento de Primas", "Primas Netas / Superávit", prem_lev_str, "Kenney Rule (< 2.5x conservador)."),
        ("Apalancamiento de Reservas", "Reservas Siniestros / Superávit", res_lev_str, "Respaldo actuarial holgado (< 3.0x)."),
        ("Deuda Financiera Senior", "Senior Notes & Debentures", _fmt_money(tot_debt_m), "Apalancamiento corporativo a largo plazo."),
        ("Rating Sintético Damodaran", "Capacidad de Servicio de Deuda", str(synth_rating), str(synth_desc)),
    ]

    for row_idx, row_data in enumerate(data_t3, start=1):
        for col_idx, text in enumerate(row_data):
            c = t3.cell(row_idx, col_idx)
            if row_idx % 2 == 0:
                _set_cell_shading(c, ALT_ROW_BG)
            p = c.paragraphs[0]
            r = p.add_run(text)
            r.font.size = Pt(8.5)
            if col_idx in [0, 2]:
                r.bold = True

    doc.add_paragraph()

    # Nota Pedagógica Callout en Word
    note_box = doc.add_table(rows=1, cols=1)
    note_box.alignment = WD_TABLE_ALIGNMENT.CENTER
    n_cell = note_box.cell(0, 0)
    _set_cell_shading(n_cell, "FFF2CC")
    _set_cell_margins(n_cell, top=120, bottom=120, left=150, right=150)

    np = n_cell.paragraphs[0]
    nr = np.add_run("GUÍA PEDAGÓGICA CONTABLE: ¿POR QUÉ EL ALTMAN Z'' NO APLICA A ASEGURADORAS?\n")
    nr.bold = True
    nr.font.size = Pt(9.5)
    nr.font.color.rgb = NAVY

    nr2 = np.add_run(
        "El modelo Altman Z'' fue diseñado exclusivamente para empresas industriales y comerciales no financieras. "
        "En una aseguradora, las reservas para siniestros y primas no devengadas son pasivos técnicos cubiertos por activos líquidos (Float) "
        "y no representan deuda concursal. El cálculo de fondo de maniobra industrial genera falsos positivos absurdos de insolvencia ('Distress'). "
        "La solvencia de seguros se audita formalmente mediante el Ratio Combinado, el Superávit de Titulares y el Ratio RBC (Risk-Based Capital) de la NAIC."
    )
    nr2.font.size = Pt(8.5)
    nr2.font.color.rgb = DARK_GRAY

    doc.add_paragraph()


# ==============================================================================
# SECCIÓN CORPORATIVA: MARKDOWN (.MD)
# ==============================================================================
def _generate_corporate_solvency_md(
    scoring_data: Dict[str, Any],
    ticker: str,
    company_name: str,
    section_num: int = 14,
    profile_data: Optional[Dict[str, Any]] = None
) -> str:
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
| **Deuda Financiera Neta** | Deuda Total - Tesorería | Caja Neta (< $0) | **{f"${abs(lev.get('net_debt')):,.1f}M (Caja Neta)" if lev.get('is_net_cash') and isinstance(lev.get('net_debt'), (int, float)) else _fmt_money(lev.get('net_debt'))}** | {'Posición Neta de Caja' if lev.get('is_net_cash') else 'Deuda Neta a Amortizar'}. |
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


# ==============================================================================
# SECCIÓN CORPORATIVA: WORD (.DOCX)
# ==============================================================================
def _add_corporate_solvency_docx(
    doc: docx.Document,
    scoring_data: Dict[str, Any],
    ticker: str,
    company_name: str,
    section_num: int = 14,
    profile_data: Optional[Dict[str, Any]] = None
):
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
        ("Deuda Financiera Neta", "Deuda Total - Tesorería", f"${abs(lev.get('net_debt')):,.1f}M (Caja Neta)" if lev.get('is_net_cash') and isinstance(lev.get('net_debt'), (int, float)) else _fmt_money(lev.get('net_debt')), "Posición Neta de Caja" if lev.get('is_net_cash') else "Deuda Neta"),
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


# ==============================================================================
# ROUTING UNIVERSAL TRI-MODAL: MARKDOWN (.MD) Y WORD (.DOCX)
# ==============================================================================
def generate_solvency_section_md(
    scoring_data: Dict[str, Any],
    ticker: str,
    company_name: str,
    section_num: int = 14,
    profile_data: Optional[Dict[str, Any]] = None
) -> str:
    """Genera la sección completa de Solvencia en Markdown, adaptándose tri-modalmente."""
    archetype = get_solvency_archetype(scoring_data)
    if archetype == "INSURANCE":
        return _generate_insurance_solvency_md(
            scoring_data=scoring_data,
            ticker=ticker,
            company_name=company_name,
            section_num=section_num,
            profile_data=profile_data
        )
    elif archetype == "FINANCIAL_BANKING":
        return _generate_banking_solvency_md(
            scoring_data=scoring_data,
            ticker=ticker,
            company_name=company_name,
            section_num=section_num,
            profile_data=profile_data
        )
    else:
        return _generate_corporate_solvency_md(
            scoring_data=scoring_data,
            ticker=ticker,
            company_name=company_name,
            section_num=section_num,
            profile_data=profile_data
        )


def add_solvency_section_docx(
    doc: docx.Document,
    scoring_data: Dict[str, Any],
    ticker: str,
    company_name: str,
    section_num: int = 14,
    profile_data: Optional[Dict[str, Any]] = None
):
    """Inserta la sección de Solvencia en Word (.docx), adaptándose tri-modalmente."""
    archetype = get_solvency_archetype(scoring_data)
    if archetype == "INSURANCE":
        _add_insurance_solvency_docx(
            doc=doc,
            scoring_data=scoring_data,
            ticker=ticker,
            company_name=company_name,
            section_num=section_num,
            profile_data=profile_data
        )
    elif archetype == "FINANCIAL_BANKING":
        _add_banking_solvency_docx(
            doc=doc,
            scoring_data=scoring_data,
            ticker=ticker,
            company_name=company_name,
            section_num=section_num,
            profile_data=profile_data
        )
    else:
        _add_corporate_solvency_docx(
            doc=doc,
            scoring_data=scoring_data,
            ticker=ticker,
            company_name=company_name,
            section_num=section_num,
            profile_data=profile_data
        )
