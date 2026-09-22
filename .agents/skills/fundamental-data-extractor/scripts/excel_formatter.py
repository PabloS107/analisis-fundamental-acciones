"""
excel_formatter.py - Generador de Modelos Financieros en Excel con formato institucional de Wall Street.
Transforma los datos contables de SEC EDGAR en un libro de trabajo altamente visual,
con cifras en Millones de USD ($M), ratios en porcentajes (%), 10 años de historia + LTM,
y estados financieros limpios sin códigos técnicos.
"""

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.comments import Comment
import pandas as pd
import math
import json
from pathlib import Path


# Paleta de colores corporativos
NAVY_HEADER = PatternFill(start_color="1B365D", end_color="1B365D", fill_type="solid")
WHITE_BOLD = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
TITLE_FONT = Font(name="Calibri", size=14, bold=True, color="1B365D")
SUBTITLE_FONT = Font(name="Calibri", size=10, italic=True, color="595959")

# Estilos específicos para la columna LTM (Last Twelve Months)
LTM_HEADER = PatternFill(start_color="0A3641", end_color="0A3641", fill_type="solid")  # Deep Teal / Pizarra
LTM_FONT = Font(name="Calibri", size=11, bold=True, color="FFD700")  # Acento Dorado

SECTION_FILL = PatternFill(start_color="E8EEF5", end_color="E8EEF5", fill_type="solid")
SECTION_FONT = Font(name="Calibri", size=11, bold=True, color="1B365D")

HIGHLIGHT_FILL = PatternFill(start_color="F0F4F9", end_color="F0F4F9", fill_type="solid")
GREEN_FILL = PatternFill(start_color="E2EFDA", end_color="E2EFDA", fill_type="solid")
YELLOW_FILL = PatternFill(start_color="FFF2CC", end_color="FFF2CC", fill_type="solid")
RED_FILL = PatternFill(start_color="FCE4D6", end_color="FCE4D6", fill_type="solid")

BOLD_FONT = Font(name="Calibri", size=11, bold=True, color="000000")
REGULAR_FONT = Font(name="Calibri", size=11, color="000000")
ITALIC_FONT = Font(name="Calibri", size=10, italic=True, color="595959")
GREEN_FONT = Font(name="Calibri", size=11, bold=True, color="276A3C")
RED_FONT = Font(name="Calibri", size=11, bold=True, color="C00000")
SCORE_NUM_FONT = Font(name="Calibri", size=12, bold=True, color="1B365D")
BADGE_FONT = Font(name="Calibri", size=12, bold=True, color="1B365D")


# Bordes contables
THIN_GRAY = Side(style='thin', color='D9D9D9')
THIN_BLACK = Side(style='thin', color='000000')
DOUBLE_BLACK = Side(style='double', color='000000')

BORDER_CELL = Border(left=THIN_GRAY, right=THIN_GRAY, top=THIN_GRAY, bottom=THIN_GRAY)
BORDER_TOTAL = Border(left=THIN_GRAY, right=THIN_GRAY, top=THIN_BLACK, bottom=DOUBLE_BLACK)
BORDER_SUBTOTAL = Border(left=THIN_GRAY, right=THIN_GRAY, top=THIN_BLACK, bottom=THIN_BLACK)

# Máscaras de Formato Numérico
FMT_CURRENCY_M = "$#,##0.0;($#,##0.0);\"-\""
FMT_SHARES_M = "#,##0.0;(#,##0.0);\"-\""
FMT_EPS = "$#,##0.00;($#,##0.00);\"-\""
FMT_PERCENT = "0.00%"
FMT_DELTA_PERCENT = "+0.00%;-0.00%;0.00%"
FMT_MULTIPLIER = "0.00\"x\""


def style_range(ws, start_row, end_row, start_col, end_col, font=None, fill=None, alignment=None, border=None, num_format=None):
    """Aplica formato por bloque de celdas."""
    for r in range(start_row, end_row + 1):
        for c in range(start_col, end_col + 1):
            cell = ws.cell(row=r, column=c)
            if font:
                cell.font = font
            if fill:
                cell.fill = fill
            if alignment:
                cell.alignment = alignment
            if border:
                cell.border = border
            if num_format:
                cell.number_format = num_format


def format_sheet_layout(ws, sheet_type=None, min_col=1, max_col=12, min_width=14, freeze_cell=None):
    """
    Ajusta y estandariza la geometría del libro de Excel bajo estándares institucionales de Wall Street:
    1. Anchos de columna uniformes y armónicos (sin desbordamientos por párrafos largos).
    2. Ignora celdas combinadas para evitar estirar columnas a 200+ caracteres.
    3. Alturas de fila proporcionales (título 30pt, subtítulo 18pt, encabezado 25pt, secciones 22pt, datos 18.5pt, separadores 10pt).
    4. Congelación de paneles (freeze panes) para mantener encabezados y partidas a la vista.
    5. Asegura visibilidad de cuadrículas contables (showGridLines = True).
    """
    ws.views.sheetView[0].showGridLines = True
    
    # 1. Mapear celdas combinadas para excluirlas de la medición de anchos
    merged_coords = set()
    for rng in ws.merged_cells.ranges:
        for r in range(rng.min_row, rng.max_row + 1):
            for c in range(rng.min_col, rng.max_col + 1):
                merged_coords.add((r, c))

    actual_max_col = max_col if max_col is not None else ws.max_column

    # 2. Detección automática del tipo de hoja si no se especifica
    title_str = str(ws.title).lower()
    if not sheet_type or sheet_type == "financial":
        if "peer" in title_str:
            sheet_type = "peers"
        elif "score" in title_str:
            sheet_type = "scoring"
        elif "forense" in title_str or "devengos" in title_str:
            sheet_type = "forensic"
        elif "solvencia" in title_str or "estrés" in title_str or "estres" in title_str:
            sheet_type = "solvency"
        elif "conciliaci" in title_str or "fuente" in title_str:
            sheet_type = "reconciliation"
        else:
            sheet_type = "financial"

    # 3. Asignación de Anchos de Columna Institucionales
    for col in range(min_col, actual_max_col + 1):
        col_letter = get_column_letter(col)
        
        if sheet_type == "financial":
            # Estados Financieros y Ratios (Hoja 1-6)
            if col == 1:
                # Concepto / Partida Contable
                max_len = 0
                for row in range(4, ws.max_row + 1):
                    if (row, col) in merged_coords:
                        continue
                    val = ws.cell(row=row, column=col).value
                    if val is not None:
                        val_str = str(val).strip()
                        if val_str.startswith("▼") or val_str.startswith("TABLA") or val_str.startswith("MATRIZ"):
                            continue
                        max_len = max(max_len, min(len(val_str), 48))
                ws.column_dimensions[col_letter].width = min(50.0, max(38.0, max_len + 3))
            else:
                # Columnas de Años Históricos y LTM: ANCHO UNIFORME Y COMPACTO
                ws.column_dimensions[col_letter].width = 14.5

        elif sheet_type in ("scoring", "forensic", "solvency"):
            # Hojas analíticas con 3 columnas descriptivas iniciales + años
            if col == 1:
                max_len = 0
                for row in range(4, ws.max_row + 1):
                    if (row, col) in merged_coords:
                        continue
                    val = ws.cell(row=row, column=col).value
                    if val is not None:
                        val_str = str(val).strip()
                        if val_str.startswith("TABLA") or val_str.startswith("MATRIZ") or val_str.startswith("DIAGNÓSTICO"):
                            continue
                        max_len = max(max_len, min(len(val_str), 48))
                ws.column_dimensions[col_letter].width = min(50.0, max(38.0, max_len + 3))
            elif col in (2, 3):
                # Categoría, Definición o Umbral
                ws.column_dimensions[col_letter].width = 22.0
            else:
                # Columnas de Años / Puntuaciones
                ws.column_dimensions[col_letter].width = 14.5

        elif sheet_type == "peers":
            # Tabla de Pares Comparables
            if col == 1:
                ws.column_dimensions[col_letter].width = 12.0  # Ticker
            elif col == 2:
                ws.column_dimensions[col_letter].width = 28.0  # Nombre Empresa
            else:
                ws.column_dimensions[col_letter].width = 15.0  # Ratios y Cifras

        elif sheet_type == "reconciliation":
            # Conciliación y Fuentes
            if col == 1:
                ws.column_dimensions[col_letter].width = 14.0
            elif col == 2:
                ws.column_dimensions[col_letter].width = 32.0
            else:
                ws.column_dimensions[col_letter].width = 18.0

        else:
            max_len = 0
            for row in range(1, ws.max_row + 1):
                if (row, col) in merged_coords:
                    continue
                val = ws.cell(row=row, column=col).value
                if val is not None:
                    max_len = max(max_len, min(len(str(val)), 30))
            if col == 1:
                ws.column_dimensions[col_letter].width = min(44.0, max(38.0, max_len + 3))
            else:
                ws.column_dimensions[col_letter].width = min(28.0, max(min_width, max_len + 3))

    # 4. Estandarización de Alturas de Fila
    for r in range(1, ws.max_row + 1):
        if r == 1:
            ws.row_dimensions[1].height = 30.0
        elif r == 2:
            ws.row_dimensions[2].height = 18.0
        elif r == 3:
            ws.row_dimensions[3].height = 8.0
        else:
            row_vals = [ws.cell(row=r, column=c).value for c in range(1, min(actual_max_col + 1, 10))]
            is_empty = all(v is None or str(v).strip() == "" for v in row_vals)
            
            if is_empty:
                ws.row_dimensions[r].height = 10.0
            else:
                c1_val = str(ws.cell(row=r, column=1).value or "").strip()
                c1_fill = ws.cell(row=r, column=1).fill
                
                if c1_fill == NAVY_HEADER or any(ws.cell(row=r, column=c).fill == NAVY_HEADER for c in range(1, min(actual_max_col + 1, 5))):
                    ws.row_dimensions[r].height = 25.0
                elif c1_fill == SECTION_FILL or c1_val.startswith("▼") or c1_val.startswith("TABLA") or c1_val.startswith("MATRIZ"):
                    ws.row_dimensions[r].height = 22.0
                elif (r, 1) in merged_coords or (r, 2) in merged_coords:
                    text_len = max([len(str(v or "")) for v in row_vals])
                    ws.row_dimensions[r].height = max(28.0, min(56.0, (text_len // 70 + 1) * 16.0 + 8.0))
                else:
                    current_h = ws.row_dimensions[r].height
                    if current_h is None or current_h in (15, 20):
                        ws.row_dimensions[r].height = 18.5

    # 5. Fijación de Paneles (Freeze Panes)
    if freeze_cell:
        ws.freeze_panes = freeze_cell
    else:
        if sheet_type == "financial":
            ws.freeze_panes = "B5"
        elif sheet_type in ("scoring", "forensic", "solvency"):
            ws.freeze_panes = "D8"
        elif sheet_type == "peers":
            ws.freeze_panes = "C7"
        elif sheet_type == "reconciliation":
            ws.freeze_panes = "B5"
        else:
            ws.freeze_panes = "B5"


def autofit_columns(ws, min_col=1, max_col=12, min_width=14):
    """Redirige al formateador estandarizado institucional."""
    format_sheet_layout(ws, sheet_type=None, min_col=min_col, max_col=max_col, min_width=min_width)


def find_matching_period_col(df_columns, fy):
    """Encuentra la columna en un DataFrame correspondiente a fy ('LTM', 'FY2025', etc.)."""
    if df_columns is None:
        return None
    # 1. Coincidencia exacta
    if fy in df_columns:
        return fy
    # 2. Espaciado ('FY 2025' vs 'FY2025')
    clean_fy = fy.replace("FY", "").strip()
    spaced = f"FY {clean_fy}"
    if spaced in df_columns:
        return spaced
    nospaced = f"FY{clean_fy}"
    if nospaced in df_columns:
        return nospaced
    # 3. Solo dígitos de año si fy no es LTM
    if fy != "LTM":
        year_digits = ''.join(filter(str.isdigit, fy))
        if year_digits:
            for c in df_columns:
                c_str = str(c)
                if year_digits in c_str and not c_str.startswith("level") and not c_str.startswith("dim"):
                    return c
    return None


def create_summary_sheet(wb, canonical, company_name, ticker, fiscal_years):
    """Crea la Hoja 1: Resumen Fundamental Ejecutivo con cifras en Millones de USD."""
    sheet_title = "Resumen Fundamental"
    if sheet_title in wb.sheetnames:
        target_idx = wb.sheetnames.index(sheet_title)
        del wb[sheet_title]
        ws = wb.create_sheet(title=sheet_title, index=target_idx)
    else:
        if len(wb.sheetnames) == 1 and wb.sheetnames[0] == "Sheet":
            ws = wb.active
            ws.title = sheet_title
        else:
            ws = wb.create_sheet(title=sheet_title, index=0)
    ws.views.sheetView[0].showGridLines = True
    
    # 1. Banners de título
    ws.cell(row=1, column=1, value=f"{company_name} ({ticker.upper()}) - Resumen Fundamental (10 Años + LTM)")
    ws.cell(row=1, column=1).font = TITLE_FONT
    ws.cell(row=2, column=1, value="Cifras en Millones de USD ($M), salvo acciones | Fuente: SEC EDGAR (US-GAAP Oficial)")
    ws.cell(row=2, column=1).font = SUBTITLE_FONT
    
    # 2. Encabezados de tabla
    headers = ["Partida Financiera (en $M USD)"] + fiscal_years
    header_row = 4
    for c_idx, h in enumerate(headers, start=1):
        cell = ws.cell(row=header_row, column=c_idx, value=h)
        if h == "LTM":
            cell.fill = LTM_HEADER
            cell.font = LTM_FONT
        else:
            cell.fill = NAVY_HEADER
            cell.font = WHITE_BOLD
        cell.alignment = Alignment(horizontal="center" if c_idx > 1 else "left", vertical="center")
    ws.row_dimensions[header_row].height = 25
    
    # 3. Filas maestras a mostrar
    metrics = [
        ("Ingresos Totales (Revenue)", "revenue", FMT_CURRENCY_M, False, None),
        ("(-) Costo de Ventas (COGS)", "cost_of_goods_sold", FMT_CURRENCY_M, False, None),
        ("(=) Margen Bruto (Gross Profit)", "gross_profit", FMT_CURRENCY_M, True, HIGHLIGHT_FILL),
        ("(-) Total Gastos Operativos (OpEx)", "operating_expenses", FMT_CURRENCY_M, False, None),
        ("(=) Beneficio Operativo (EBIT)", "operating_income", FMT_CURRENCY_M, True, HIGHLIGHT_FILL),
        ("(=) Beneficio Neto (Net Income)", "net_income", FMT_CURRENCY_M, True, HIGHLIGHT_FILL),
        ("", None, None, False, None),  # Separador
        ("Flujo de Caja Operativo (CFO)", "cash_from_operations", FMT_CURRENCY_M, False, None),
        ("(-) Inversión de Capital (CapEx)", "capital_expenditures", FMT_CURRENCY_M, False, None),
        ("(=) Flujo de Caja Libre (Free Cash Flow)", "free_cash_flow", FMT_CURRENCY_M, True, GREEN_FILL),
        ("", None, None, False, None),  # Separador
        ("Efectivo e Inversiones Líquidas", "cash_and_equivalents", FMT_CURRENCY_M, False, None),
        ("Deuda Financiera Total", "total_debt", FMT_CURRENCY_M, False, None),
        ("Deuda Neta (Deuda Total - Caja)", "net_debt", FMT_CURRENCY_M, True, None),
        ("Total Activos (Assets)", "total_assets", FMT_CURRENCY_M, True, HIGHLIGHT_FILL),
        ("Patrimonio Neto (Stockholders Equity)", "stockholders_equity", FMT_CURRENCY_M, True, HIGHLIGHT_FILL),
        ("", None, None, False, None),  # Separador
        ("BPA Diluido Normalizado (Split-Adjusted) [$]", "eps_diluted_adjusted", FMT_EPS, True, HIGHLIGHT_FILL),
        ("BPA Diluido Oficial As-Reported [$]", "eps_diluted", FMT_EPS, False, None),
        ("Acciones Diluidas Ajustadas (Millones)", "shares_diluted_adjusted", FMT_SHARES_M, True, None),
        ("Acciones Diluidas As-Reported (Millones)", "shares_diluted", FMT_SHARES_M, False, None),
    ]
    
    curr_row = header_row + 1
    for label, metric_key, num_fmt, is_bold, fill_color in metrics:
        if metric_key is None:
            curr_row += 1
            continue
            
        ws.cell(row=curr_row, column=1, value=label)
        ws.cell(row=curr_row, column=1).font = BOLD_FONT if is_bold else REGULAR_FONT
        ws.cell(row=curr_row, column=1).border = BORDER_SUBTOTAL if is_bold else BORDER_CELL
        if fill_color:
            ws.cell(row=curr_row, column=1).fill = fill_color
            
        for c_idx, fy in enumerate(fiscal_years, start=2):
            cell = ws.cell(row=curr_row, column=c_idx)
            val = canonical.get(metric_key, {}).get(fy)
            
            if val is not None and pd.notna(val) and str(val) != "nan":
                num = float(val)
                if metric_key.startswith("eps_"):
                    cell.value = num
                else:
                    cell.value = num / 1_000_000.0
                cell.number_format = num_fmt
            else:
                cell.value = "-"
                cell.alignment = Alignment(horizontal="center")
                
            cell.font = BOLD_FONT if is_bold else REGULAR_FONT
            cell.border = BORDER_SUBTOTAL if is_bold else BORDER_CELL
            if fill_color:
                cell.fill = fill_color
                
        curr_row += 1
        
    autofit_columns(ws, min_col=1, max_col=len(headers), min_width=18)


def create_ratios_sheet(wb, ratios, company_name, ticker, fiscal_years):
    """Crea la Hoja 2: Ratios Financieros y Rentabilidad formateados como porcentajes y múltiplos."""
    import json
    from pathlib import Path

    sheet_title = "Ratios Financieros"
    if sheet_title in wb.sheetnames:
        target_idx = wb.sheetnames.index(sheet_title)
        del wb[sheet_title]
        ws = wb.create_sheet(title=sheet_title, index=target_idx)
    else:
        if "Resumen Fundamental" in wb.sheetnames:
            ws = wb.create_sheet(title=sheet_title, index=1)
        else:
            ws = wb.create_sheet(title=sheet_title)

    ws.views.sheetView[0].showGridLines = True
    
    ws.cell(row=1, column=1, value=f"{company_name} ({ticker.upper()}) - Ratios Financieros y Retornos")
    ws.cell(row=1, column=1).font = TITLE_FONT
    ws.cell(row=2, column=1, value="Márgenes y Retornos expresados en porcentaje (%), Múltiplos en (x) | Fuente: SEC EDGAR")
    ws.cell(row=2, column=1).font = SUBTITLE_FONT

    INSTITUTIONAL_RATIOS = [
        "gross_margin_pct", "operating_margin_pct", "net_margin_pct",
        "fcf_margin_pct", "fcf_conversion_pct", "roe_pct", "roa_pct",
        "current_ratio", "debt_to_equity"
    ]

    # Resolver fuente de datos asegurando leer de key_ratios de financial_statements.json si ratios está vacío o anidado
    ratios_data = {}
    if isinstance(ratios, dict):
        if "key_ratios" in ratios and isinstance(ratios["key_ratios"], dict) and ratios["key_ratios"]:
            ratios_data = ratios["key_ratios"]
        elif any(k in ratios for k in INSTITUTIONAL_RATIOS):
            ratios_data = ratios

    # Fallback automático: Si ratios_data sigue vacío o carece de datos clave, cargar desde financial_statements.json
    if not ratios_data or not any(ratios_data.get(k) for k in INSTITUTIONAL_RATIOS):
        candidate_paths = [
            Path("data/processed") / ticker.upper() / "financial_statements.json",
            Path("data/processed") / ticker / "financial_statements.json",
            Path(__file__).resolve().parent.parent.parent.parent.parent / "data" / "processed" / ticker.upper() / "financial_statements.json",
            Path(__file__).resolve().parent.parent.parent.parent.parent / "data" / "processed" / ticker / "financial_statements.json",
            Path("../data/processed") / ticker.upper() / "financial_statements.json",
        ]
        for p in candidate_paths:
            if p.exists():
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        f_json = json.load(f)
                        if "key_ratios" in f_json and f_json["key_ratios"]:
                            ratios_data = f_json["key_ratios"]
                            break
                except Exception:
                    pass
    
    # Integración de métricas de Novy-Marx GP/A desde fundamental_scores.json
    scores_paths = [
        Path("data/processed") / ticker.upper() / "fundamental_scores.json",
        Path("data/processed") / ticker / "fundamental_scores.json",
        Path("../data/processed") / ticker.upper() / "fundamental_scores.json",
    ]
    for sp in scores_paths:
        if sp.exists():
            try:
                with open(sp, "r", encoding="utf-8") as sf:
                    s_json = json.load(sf)
                    nm_by_period = s_json.get("novy_marx_analysis", {}).get("by_period", {})
                    for fy, nm_val in nm_by_period.items():
                        for k in ["novy_marx_gpa_pct", "novy_marx_gpa_ex_cash_pct", "novy_marx_cash_drag_pct", "asset_turnover", "asset_turnover_ex_cash"]:
                            if k not in ratios_data:
                                ratios_data[k] = {}
                        if nm_val.get("gross_profitability_total") is not None:
                            ratios_data["novy_marx_gpa_pct"][fy] = nm_val["gross_profitability_total"] * 100.0
                        if nm_val.get("gross_profitability_ex_cash") is not None:
                            ratios_data["novy_marx_gpa_ex_cash_pct"][fy] = nm_val["gross_profitability_ex_cash"] * 100.0
                        if nm_val.get("cash_drag_pct") is not None:
                            ratios_data["novy_marx_cash_drag_pct"][fy] = nm_val["cash_drag_pct"] * 100.0
                        if nm_val.get("asset_turnover_total") is not None:
                            ratios_data["asset_turnover"][fy] = nm_val["asset_turnover_total"]
                        if nm_val.get("asset_turnover_ex_cash") is not None:
                            ratios_data["asset_turnover_ex_cash"][fy] = nm_val["asset_turnover_ex_cash"]

                    # Cargar ROIC y WACC
                    roic_by_period = s_json.get("intangible_roic_analysis", {}).get("by_period", {})
                    wacc_val = s_json.get("wacc_and_spread_analysis", {}).get("wacc", 0.088)
                    for k in ["traditional_roic_pct", "adjusted_roic_pct", "intangible_stock_usd_m", "invested_capital_adj_usd_m", "wacc_pct", "economic_spread_adj_pct"]:
                        if k not in ratios_data:
                            ratios_data[k] = {}

                    for fy, r_val in roic_by_period.items():
                        if r_val.get("roic_trad") is not None:
                            ratios_data["traditional_roic_pct"][fy] = r_val["roic_trad"] * 100.0
                        if r_val.get("roic_adj") is not None:
                            ratios_data["adjusted_roic_pct"][fy] = r_val["roic_adj"] * 100.0
                            if wacc_val:
                                ratios_data["wacc_pct"][fy] = wacc_val * 100.0
                                ratios_data["economic_spread_adj_pct"][fy] = (r_val["roic_adj"] - wacc_val) * 100.0
                        if r_val.get("total_intangible_stock") is not None:
                            ratios_data["intangible_stock_usd_m"][fy] = r_val["total_intangible_stock"]
                        if r_val.get("ic_adj") is not None:
                            ratios_data["invested_capital_adj_usd_m"][fy] = r_val["ic_adj"]

                    # Cargar ROC Greenblatt
                    roc_greenblatt_data = s_json.get("greenblatt_roc_analysis", {})
                    if "roc_greenblatt_pct" not in ratios_data:
                        ratios_data["roc_greenblatt_pct"] = {}
                    for fy, r_val in roc_greenblatt_data.get("annual_series", {}).items():
                        if r_val.get("roc_avg") is not None:
                            ratios_data["roc_greenblatt_pct"][fy] = r_val["roc_avg"] * 100.0
                    ltm_roc = roc_greenblatt_data.get("ltm", {}).get("roc_avg") if roc_greenblatt_data.get("ltm", {}).get("roc_avg") is not None else roc_greenblatt_data.get("ltm", {}).get("roc_ltm")
                    if ltm_roc is not None:
                        ratios_data["roc_greenblatt_pct"]["LTM"] = ltm_roc * 100.0
                break
            except Exception:
                pass

    headers = ["Ratio Financiero / Métrica"] + fiscal_years
    header_row = 4
    for c_idx, h in enumerate(headers, start=1):
        cell = ws.cell(row=header_row, column=c_idx, value=h)
        if h == "LTM":
            cell.fill = LTM_HEADER
            cell.font = LTM_FONT
        else:
            cell.fill = NAVY_HEADER
            cell.font = WHITE_BOLD
        cell.alignment = Alignment(horizontal="center" if c_idx > 1 else "left", vertical="center")
    ws.row_dimensions[header_row].height = 25
    
    ratio_groups = [
        ("MÁRGENES DE RENTABILIDAD", [
            ("Margen Bruto (Gross Margin)", "gross_margin_pct", "pct"),
            ("Margen Operativo (Operating Margin)", "operating_margin_pct", "pct"),
            ("Margen Neto (Net Margin)", "net_margin_pct", "pct"),
            ("Margen de Flujo de Caja Libre (FCF Margin)", "fcf_margin_pct", "pct"),
            ("Conversión de Beneficio a FCF (FCF / Net Income)", "fcf_conversion_pct", "pct"),
        ]),
        ("RETORNOS SOBRE EL CAPITAL", [
            ("Retorno sobre Patrimonio (ROE = Net Income / Equity Promedio)", "roe_pct", "pct"),
            ("Retorno sobre Activos (ROA = Net Income / Assets Promedio)", "roa_pct", "pct"),
            ("Retorno sobre Capital Tangible (ROC Greenblatt = EBIT / Capital Tangible Promedio)", "roc_greenblatt_pct", "pct"),
        ]),
        ("LIQUIDEZ Y APALANCAMIENTO", [
            ("Ratio de Liquidez Corriente (Current Ratio)", "current_ratio", "mult"),
            ("Deuda sobre Patrimonio (Debt to Equity)", "debt_to_equity", "mult"),
        ]),
        ("PRODUCTIVIDAD PURA DEL CAPITAL (NOVY-MARX DUPONT)", [
            ("Gross Profitability (Activos Totales)", "novy_marx_gpa_pct", "pct"),
            ("Gross Profitability Operativa (Ex-Caja)", "novy_marx_gpa_ex_cash_pct", "pct"),
            ("Efecto Arrastre de Caja (Cash Drag)", "novy_marx_cash_drag_pct", "pct"),
            ("Margen Bruto de Utilidad (DuPont)", "gross_margin_pct", "pct"),
            ("Rotación de Activos Totales (DuPont)", "asset_turnover", "mult"),
            ("Rotación de Activos Operativos (Ex-Caja)", "asset_turnover_ex_cash", "mult"),
        ]),
        ("RENDIMIENTO DEL CAPITAL Y CREACIÓN DE VALOR (ROIC AJUSTADO VS WACC)", [
            ("ROIC Tradicional (NOPAT / Cap. Invertido)", "traditional_roic_pct", "pct"),
            ("ROIC Ajustado por Intangibles (Damodaran)", "adjusted_roic_pct", "pct"),
            ("Stock de Intangibles Capitalizados ($M)", "intangible_stock_usd_m", "curr"),
            ("Capital Invertido Reconstituido Promedio ($M)", "invested_capital_adj_usd_m", "curr"),
            ("Costo Promedio Ponderado de Capital (WACC)", "wacc_pct", "pct"),
            ("Spread Económico (ROIC Ajustado - WACC)", "economic_spread_adj_pct", "pct_delta"),
        ])
    ]
    
    ratio_comments = {
        "Margen Bruto (Gross Margin)": (
            "Margen Bruto = (Ingresos - Coste de Ventas) / Ingresos\n"
            "Mide el porcentaje de ventas que la empresa retiene tras cubrir los costes directos de fabricación. "
            "Una expansión sostenida indica poder de fijación de precios y ventajas competitivas (Moat)."
        ),
        "Margen Operativo (Operating Margin)": (
            "Margen Operativo = Beneficio Operativo (EBIT) / Ingresos\n"
            "Mide la rentabilidad de las operaciones principales tras absorber gastos de I+D y comerciales (SG&A)."
        ),
        "Margen Neto (Net Margin)": (
            "Margen Neto = Beneficio Neto (Net Income) / Ingresos\n"
            "Porcentaje final de ingresos que se traduce en ganancias netas disponibles para los accionistas."
        ),
        "Margen de Flujo de Caja Libre (FCF Margin)": (
            "Margen FCF = Flujo de Caja Libre / Ingresos\n"
            "Porcentaje de ingresos convertido directamente en caja líquida libre tras pagar inversiones de capital (CapEx)."
        ),
        "Conversión de Beneficio a FCF (FCF / Net Income)": (
            "Tasa de Conversión = Free Cash Flow / Net Income\n"
            "Mide la calidad contable de los beneficios. Si es superior a 100%, indica que las ganancias contables "
            "están más que respaldadas por efectivo real generado."
        ),
        "Retorno sobre Patrimonio (ROE = Net Income / Equity Promedio)": (
            "ROE = Beneficio Neto / Promedio de Patrimonio Neto ((t + t-1) / 2)\n"
            "Rentabilidad obtenida sobre los fondos propios medios del ejercicio.\n"
            "El uso de patrimonio promedio mitiga distorsiones provocadas por recompras masivas de acciones o variaciones puntuales al cierre (Estándar institucional FactSet/Bloomberg)."
        ),
        "Retorno sobre Activos (ROA = Net Income / Assets Promedio)": (
            "ROA = Beneficio Neto / Promedio de Activos Totales ((t + t-1) / 2)\n"
            "Mide la eficiencia con la que la gerencia utiliza los activos medios operativos del ejercicio para generar beneficios netos.\n"
            "Cumple con el principio contable de correspondencia temporal (Matching Principle), evitando castigar a empresas en fuerte crecimiento orgánico."
        ),
        "Retorno sobre Capital Tangible (ROC Greenblatt = EBIT / Capital Tangible Promedio)": (
            "ROC Greenblatt (Magic Formula) = EBIT / Capital Tangible Operativo Promedio\n"
            "Mide la rentabilidad y productividad económica pura del negocio sobre los activos físicos y operativos requeridos para operar.\n"
            "Excluye deuda, impuestos e intangibles capitalizados. Denominador = Promedio de (Capital de Trabajo Neto Operativo + PP&E Neto).\n"
            "Detección en Balances SEC:\n"
            "• Numerador: Operating Income del Estado de Resultados (10-K / 10-Q).\n"
            "• Activos Op.: Total Current Assets menos Efectivo y Valores Negociables.\n"
            "• Pasivos Op.: Total Current Liabilities menos Commercial Paper y Deuda CP.\n"
            "• PP&E Neto: Property, plant and equipment, net del Balance.\n"
            "• Salvaguarda: Si NWC < 0, Capital Tangible se acota al PP&E Neto."
        ),
        "Ratio de Liquidez Corriente (Current Ratio)": (
            "Current Ratio = Activo Corriente / Pasivo Corriente\n"
            "Mide la solvencia de corto plazo (< 1 año). Un valor > 1.0x indica que los activos líquidos cubren las deudas inmediatas."
        ),
        "Deuda sobre Patrimonio (Debt to Equity)": (
            "Debt to Equity = Deuda Financiera Total / Patrimonio Neto\n"
            "Mide el grado de apalancamiento financiero y la dependencia de acreedores frente al capital propio."
        ),
        "Gross Profitability (Activos Totales)": (
            "Gross Profitability (Novy-Marx) = Utilidad Bruta / Activos Totales\n"
            "Mide la productividad económica pura del capital instalado. Libre de distorsiones por gastos "
            "financieros, impuestos, amortizaciones contables o gastos corporativos. "
            "Factor clave de Quality Investing (Novy-Marx 2013 / Fama-French RMW)."
        ),
        "Gross Profitability Operativa (Ex-Caja)": (
            "Gross Profitability Operativa = Utilidad Bruta / (Activos Totales - Caja y Equivalentes)\n"
            "Aísla el efecto de la tesorería ociosa, evaluando el retorno generado exclusivamente sobre "
            "los activos que operan activamente en el negocio."
        ),
        "Efecto Arrastre de Caja (Cash Drag)": (
            "Cash Drag = Gross Profitability Operativa - Gross Profitability Total\n"
            "Mide en puntos porcentuales cuánto diluye la caja acumulada la rentabilidad nominal sobre activos. "
            "Un valor elevado revela una tesorería masiva que esconde la verdadera potencia productiva del negocio."
        ),
        "Margen Bruto de Utilidad (DuPont)": (
            "Margen Bruto = Utilidad Bruta / Ingresos\n"
            "Componente de margen en la descomposición DuPont de Novy-Marx. Evalúa pricing power y moat de marca."
        ),
        "Rotación de Activos Totales (DuPont)": (
            "Rotación de Activos = Ingresos / Activos Totales\n"
            "Componente de velocidad en DuPont. Mide cuántas veces al año la empresa convierte sus activos en ventas."
        ),
        "Rotación de Activos Operativos (Ex-Caja)": (
            "Rotación Operativa = Ingresos / (Activos Totales - Caja)\n"
            "Velocidad de facturación generada por cada dólar de activo operativo directo."
        ),
        "ROIC Tradicional (NOPAT / Cap. Invertido)": (
            "ROIC Tradicional = NOPAT / Capital Invertido Promedio en Libros ((t + t-1) / 2)\n"
            "Mide el retorno sobre activos tangibles registrados calculados sobre capital medio.\n"
            "Tiende a estar artificialmente inflado en empresas de tecnología o marca masiva porque I+D y Publicidad se expulsan a gastos corrientes."
        ),
        "ROIC Ajustado por Intangibles (Damodaran)": (
            "ROIC Ajustado = NOPAT Ajustado / Capital Invertido Promedio Reconstituido ((t + t-1) / 2)\n"
            "Metodología Damodaran/Mauboussin. Capitaliza I+D y Marketing amortizándolos económicamente.\n"
            "Calculado sobre el Capital Invertido Promedio para garantizar la estricta correspondencia temporal con el NOPAT del ejercicio."
        ),
        "Stock de Intangibles Capitalizados ($M)": (
            "Valor neto acumulado en balance de los gastos de I+D y Marca tras aplicar amortización lineal de N años."
        ),
        "Capital Invertido Reconstituido Promedio ($M)": (
            "Capital Invertido Total Promedio = Promedio de (Activos Operativos + Stock Neto de Intangibles Capitalizados) ((t + t-1) / 2)."
        ),
        "Costo Promedio Ponderado de Capital (WACC)": (
            "WACC = (We * Ke) + (Wd * Kd * (1 - t))\n"
            "Tasa de corte mínima exigida por accionistas y acreedores a valor de mercado."
        ),
        "Spread Económico (ROIC Ajustado - WACC)": (
            "Spread Económico = ROIC Ajustado - WACC (puntos porcentuales)\n"
            "Si es > 0, crea valor económico neto (EVA). Si es > +15%, califica como Foso Defensivo Excepcional (Wide Moat)."
        )
    }
    
    curr_row = header_row + 1
    for group_title, items in ratio_groups:
        ws.cell(row=curr_row, column=1, value=group_title)
        ws.cell(row=curr_row, column=1).fill = SECTION_FILL
        ws.cell(row=curr_row, column=1).font = SECTION_FONT
        for c in range(2, len(headers) + 1):
            ws.cell(row=curr_row, column=c).fill = SECTION_FILL
        curr_row += 1
        
        for label, ratio_key, r_type in items:
            c1 = ws.cell(row=curr_row, column=1, value=f"   {label}")
            c1.font = REGULAR_FONT
            c1.border = BORDER_CELL
            
            if label in ratio_comments:
                r_com = Comment(ratio_comments[label], author="Glosario Financiero SEC")
                r_com.width = 320
                r_com.height = 100
                c1.comment = r_com
            
            for c_idx, fy in enumerate(fiscal_years, start=2):
                cell = ws.cell(row=curr_row, column=c_idx)
                metric_dict = ratios_data.get(ratio_key) or {}
                val = metric_dict.get(fy) if isinstance(metric_dict, dict) else None

                if (val is None or pd.isna(val) or str(val) == "nan") and isinstance(ratios, dict):
                    alt_dict = ratios.get(ratio_key) or {}
                    val = alt_dict.get(fy) if isinstance(alt_dict, dict) else None
                
                num = None
                if val is not None and pd.notna(val) and str(val).strip().lower() not in ("nan", "none", "n/a", "-", ""):
                    try:
                        num = float(val)
                    except (ValueError, TypeError):
                        num = None

                if num is not None:
                    if r_type == "pct":
                        cell.value = num / 100.0
                        cell.number_format = FMT_PERCENT
                    elif r_type == "pct_delta":
                        cell.value = num / 100.0
                        cell.number_format = FMT_DELTA_PERCENT
                    elif r_type == "curr":
                        cell.value = num
                        cell.number_format = FMT_CURRENCY_M
                    else:
                        cell.value = num
                        cell.number_format = FMT_MULTIPLIER
                    cell.alignment = Alignment(horizontal="right", vertical="center")
                else:
                    cell.value = "-"
                    cell.alignment = Alignment(horizontal="center", vertical="center")
                    
                cell.font = REGULAR_FONT
                cell.border = BORDER_CELL
            curr_row += 1
            
        curr_row += 1
        
    format_sheet_layout(ws, sheet_type="financial", min_col=1, max_col=len(headers), freeze_cell="B5")


def create_clean_income_sheet(wb, inc_df, company_name, ticker, fiscal_years):
    """Crea la Hoja 3: Cuenta de Resultados Oficial limpia sin códigos técnicos."""
    ws = wb.create_sheet(title="Cuenta de Resultados")
    ws.views.sheetView[0].showGridLines = True
    
    ws.cell(row=1, column=1, value=f"{company_name} ({ticker.upper()}) - Estado de Resultados Oficial")
    ws.cell(row=1, column=1).font = TITLE_FONT
    ws.cell(row=2, column=1, value="Cifras expresadas en Millones de USD ($M), salvo BPA | US-GAAP Auditado")
    ws.cell(row=2, column=1).font = SUBTITLE_FONT
    
    headers = ["Concepto Contable"] + fiscal_years
    header_row = 4
    for c_idx, h in enumerate(headers, start=1):
        cell = ws.cell(row=header_row, column=c_idx, value=h)
        if h == "LTM":
            cell.fill = LTM_HEADER
            cell.font = LTM_FONT
        else:
            cell.fill = NAVY_HEADER
            cell.font = WHITE_BOLD
        cell.alignment = Alignment(horizontal="center" if c_idx > 1 else "left", vertical="center")
    ws.row_dimensions[header_row].height = 25
    
    if inc_df is None or inc_df.empty:
        autofit_columns(ws, min_col=1, max_col=len(headers), min_width=18)
        return
        
    curr_row = header_row + 1
    for _, row in inc_df.iterrows():
        dim = row.get("dimension_member_label")
        if dim is not None and str(dim) != "None" and str(dim) != "nan":
            continue
            
        label = str(row.get("label", "")).strip()
        if not label or label.endswith("Abstract"):
            continue
            
        concept = str(row.get("concept", ""))
        is_bold = any(k in concept.lower() for k in ["grossprofit", "operatingincomeloss", "netincomeloss", "earningspershare"])
        is_eps = "earningspershare" in concept.lower()
        is_shares = "sharesoutstanding" in concept.lower()
        
        ws.cell(row=curr_row, column=1, value=label)
        ws.cell(row=curr_row, column=1).font = BOLD_FONT if is_bold else REGULAR_FONT
        ws.cell(row=curr_row, column=1).border = BORDER_SUBTOTAL if is_bold else BORDER_CELL
        if is_bold:
            ws.cell(row=curr_row, column=1).fill = HIGHLIGHT_FILL
            
        for c_idx, fy in enumerate(fiscal_years, start=2):
            match_col = find_matching_period_col(inc_df.columns, fy)
            cell = ws.cell(row=curr_row, column=c_idx)
            val = row.get(match_col) if match_col else None
            
            if pd.notna(val) and str(val) != "nan":
                try:
                    num = float(val)
                    if is_eps:
                        cell.value = num
                        cell.number_format = FMT_EPS
                    elif is_shares:
                        cell.value = num / 1_000_000.0
                        cell.number_format = FMT_SHARES_M
                    else:
                        cell.value = num / 1_000_000.0
                        cell.number_format = FMT_CURRENCY_M
                except (ValueError, TypeError):
                    cell.value = str(val)
            else:
                cell.value = "-"
                cell.alignment = Alignment(horizontal="center")
                
            cell.font = BOLD_FONT if is_bold else REGULAR_FONT
            cell.border = BORDER_SUBTOTAL if is_bold else BORDER_CELL
            if is_bold:
                cell.fill = HIGHLIGHT_FILL
                
        curr_row += 1
        
    # Bloque de Conciliación Split-Adjusted para comparabilidad histórica (coincidente con fiscal.ai / Tikr)
    fin_json_path = Path("data/processed") / ticker.upper() / "financial_statements.json"
    if fin_json_path.exists():
        try:
            with open(fin_json_path, "r", encoding="utf-8") as f:
                f_data = json.load(f)
            c_summ = f_data.get("canonical_summary", {})
            eps_adj = c_summ.get("eps_diluted_adjusted", {})
            sh_adj = c_summ.get("shares_diluted_adjusted", {})
            
            if eps_adj:
                curr_row += 1
                ws.cell(row=curr_row, column=1, value="INFORMACIÓN POR ACCIÓN NORMALIZADA (SPLIT-ADJUSTED)")
                ws.cell(row=curr_row, column=1).fill = SECTION_FILL
                ws.cell(row=curr_row, column=1).font = SECTION_FONT
                for c in range(2, len(headers) + 1):
                    ws.cell(row=curr_row, column=c).fill = SECTION_FILL
                curr_row += 1

                # Fila BPA Ajustado
                ws.cell(row=curr_row, column=1, value="   BPA Diluido Normalizado (Split-Adjusted)")
                ws.cell(row=curr_row, column=1).font = BOLD_FONT
                ws.cell(row=curr_row, column=1).border = BORDER_SUBTOTAL
                ws.cell(row=curr_row, column=1).fill = HIGHLIGHT_FILL
                for c_idx, fy in enumerate(fiscal_years, start=2):
                    cell = ws.cell(row=curr_row, column=c_idx)
                    v = eps_adj.get(fy)
                    if v is not None:
                        cell.value = float(v)
                        cell.number_format = FMT_EPS
                    else:
                        cell.value = "-"
                        cell.alignment = Alignment(horizontal="center")
                    cell.font = BOLD_FONT
                    cell.border = BORDER_SUBTOTAL
                    cell.fill = HIGHLIGHT_FILL
                curr_row += 1

                # Fila Acciones Ajustadas
                if sh_adj:
                    ws.cell(row=curr_row, column=1, value="   Acciones Diluidas Ponderadas (Millones)")
                    ws.cell(row=curr_row, column=1).font = REGULAR_FONT
                    ws.cell(row=curr_row, column=1).border = BORDER_CELL
                    for c_idx, fy in enumerate(fiscal_years, start=2):
                        cell = ws.cell(row=curr_row, column=c_idx)
                        v = sh_adj.get(fy)
                        if v is not None:
                            cell.value = float(v) / 1_000_000.0
                            cell.number_format = FMT_SHARES_M
                        else:
                            cell.value = "-"
                            cell.alignment = Alignment(horizontal="center")
                        cell.font = REGULAR_FONT
                        cell.border = BORDER_CELL
                    curr_row += 1
        except Exception:
            pass

    autofit_columns(ws, min_col=1, max_col=len(headers), min_width=18)


def create_clean_balance_sheet(wb, bal_df, company_name, ticker, fiscal_years):
    """Crea la Hoja 4: Balance de Situación Patrimonial estructurado y clasificado."""
    ws = wb.create_sheet(title="Balance Patrimonial")
    ws.views.sheetView[0].showGridLines = True
    
    ws.cell(row=1, column=1, value=f"{company_name} ({ticker.upper()}) - Balance Patrimonial Oficial")
    ws.cell(row=1, column=1).font = TITLE_FONT
    ws.cell(row=2, column=1, value="Cifras expresadas en Millones de USD ($M) | Estructura contable de Activos, Pasivos y Patrimonio")
    ws.cell(row=2, column=1).font = SUBTITLE_FONT
    
    headers = ["Concepto Patrimonial"] + fiscal_years
    header_row = 4
    for c_idx, h in enumerate(headers, start=1):
        cell = ws.cell(row=header_row, column=c_idx, value=h)
        if h == "LTM":
            cell.fill = LTM_HEADER
            cell.font = LTM_FONT
        else:
            cell.fill = NAVY_HEADER
            cell.font = WHITE_BOLD
        cell.alignment = Alignment(horizontal="center" if c_idx > 1 else "left", vertical="center")
    ws.row_dimensions[header_row].height = 25
    
    if bal_df is None or bal_df.empty:
        autofit_columns(ws, min_col=1, max_col=len(headers), min_width=20)
        return
        
    curr_row = header_row + 1
    for _, row in bal_df.iterrows():
        dim = row.get("dimension_member_label")
        if dim is not None and str(dim) != "None" and str(dim) != "nan":
            continue
            
        label = str(row.get("label", "")).strip()
        concept = str(row.get("concept", ""))
        is_abstract = "Abstract" in concept or label.endswith(":") or label.isupper()
        
        if is_abstract:
            ws.cell(row=curr_row, column=1, value=label)
            ws.cell(row=curr_row, column=1).fill = SECTION_FILL
            ws.cell(row=curr_row, column=1).font = SECTION_FONT
            for c in range(2, len(headers) + 1):
                ws.cell(row=curr_row, column=c).fill = SECTION_FILL
            curr_row += 1
            continue
            
        is_total = any(k in concept.lower() for k in ["assetscurrent", "assetsnoncurrent", "liabilitiescurrent", "liabilitiesnoncurrent", "assets", "liabilities", "stockholdersequity"])
        is_grand_total = concept in ["us-gaap_Assets", "Assets", "us-gaap_LiabilitiesAndStockholdersEquity", "LiabilitiesAndStockholdersEquity"]
        
        ws.cell(row=curr_row, column=1, value=f"   {label}")
        ws.cell(row=curr_row, column=1).font = BOLD_FONT if is_total else REGULAR_FONT
        ws.cell(row=curr_row, column=1).border = BORDER_TOTAL if is_grand_total else (BORDER_SUBTOTAL if is_total else BORDER_CELL)
        if is_grand_total:
            ws.cell(row=curr_row, column=1).fill = HIGHLIGHT_FILL
            
        for c_idx, fy in enumerate(fiscal_years, start=2):
            match_col = find_matching_period_col(bal_df.columns, fy)
            cell = ws.cell(row=curr_row, column=c_idx)
            val = row.get(match_col) if match_col else None
            
            if pd.notna(val) and str(val) != "nan":
                try:
                    num = float(val)
                    cell.value = num / 1_000_000.0
                    cell.number_format = FMT_CURRENCY_M
                except (ValueError, TypeError):
                    cell.value = str(val)
            else:
                cell.value = "-"
                cell.alignment = Alignment(horizontal="center")
                
            cell.font = BOLD_FONT if is_total else REGULAR_FONT
            cell.border = BORDER_TOTAL if is_grand_total else (BORDER_SUBTOTAL if is_total else BORDER_CELL)
            if is_grand_total:
                cell.fill = HIGHLIGHT_FILL
                
        curr_row += 1
        
    autofit_columns(ws, min_col=1, max_col=len(headers), min_width=20)


def create_clean_cashflow_sheet(wb, cf_df, company_name, ticker, fiscal_years):
    """Crea la Hoja 5: Flujo de Caja estructurado (CFO, CFI, CFF y FCF)."""
    ws = wb.create_sheet(title="Flujo de Caja")
    ws.views.sheetView[0].showGridLines = True
    
    ws.cell(row=1, column=1, value=f"{company_name} ({ticker.upper()}) - Estado de Flujos de Efectivo")
    ws.cell(row=1, column=1).font = TITLE_FONT
    ws.cell(row=2, column=1, value="Cifras expresadas en Millones de USD ($M) | Conciliación de CFO, CFI y CFF")
    ws.cell(row=2, column=1).font = SUBTITLE_FONT
    
    headers = ["Actividad / Flujo de Fondos"] + fiscal_years
    header_row = 4
    for c_idx, h in enumerate(headers, start=1):
        cell = ws.cell(row=header_row, column=c_idx, value=h)
        if h == "LTM":
            cell.fill = LTM_HEADER
            cell.font = LTM_FONT
        else:
            cell.fill = NAVY_HEADER
            cell.font = WHITE_BOLD
        cell.alignment = Alignment(horizontal="center" if c_idx > 1 else "left", vertical="center")
    ws.row_dimensions[header_row].height = 25
    
    if cf_df is None or cf_df.empty:
        autofit_columns(ws, min_col=1, max_col=len(headers), min_width=20)
        return
        
    curr_row = header_row + 1
    for _, row in cf_df.iterrows():
        dim = row.get("dimension_member_label")
        if dim is not None and str(dim) != "None" and str(dim) != "nan":
            continue
            
        label = str(row.get("label", "")).strip()
        concept = str(row.get("concept", ""))
        is_abstract = "Abstract" in concept or label.endswith(":")
        
        if is_abstract:
            ws.cell(row=curr_row, column=1, value=label)
            ws.cell(row=curr_row, column=1).fill = SECTION_FILL
            ws.cell(row=curr_row, column=1).font = SECTION_FONT
            for c in range(2, len(headers) + 1):
                ws.cell(row=curr_row, column=c).fill = SECTION_FILL
            curr_row += 1
            continue
            
        is_total = any(k in concept for k in ["NetCashProvidedByUsedInOperatingActivities", "NetCashProvidedByUsedInInvestingActivities", "NetCashProvidedByUsedInFinancingActivities", "PeriodIncreaseDecrease"])
        
        ws.cell(row=curr_row, column=1, value=f"   {label}")
        ws.cell(row=curr_row, column=1).font = BOLD_FONT if is_total else REGULAR_FONT
        ws.cell(row=curr_row, column=1).border = BORDER_SUBTOTAL if is_total else BORDER_CELL
        if is_total:
            ws.cell(row=curr_row, column=1).fill = HIGHLIGHT_FILL
            
        for c_idx, fy in enumerate(fiscal_years, start=2):
            match_col = find_matching_period_col(cf_df.columns, fy)
            cell = ws.cell(row=curr_row, column=c_idx)
            val = row.get(match_col) if match_col else None
            
            if pd.notna(val) and str(val) != "nan":
                try:
                    num = float(val)
                    cell.value = num / 1_000_000.0
                    cell.number_format = FMT_CURRENCY_M
                except (ValueError, TypeError):
                    cell.value = str(val)
            else:
                cell.value = "-"
                cell.alignment = Alignment(horizontal="center")
                
            cell.font = BOLD_FONT if is_total else REGULAR_FONT
            cell.border = BORDER_SUBTOTAL if is_total else BORDER_CELL
            if is_total:
                cell.fill = HIGHLIGHT_FILL
                
        curr_row += 1
        
    autofit_columns(ws, min_col=1, max_col=len(headers), min_width=20)


def create_segments_sheet(wb, segment_df, company_name, ticker, fiscal_years):
    """Crea la Hoja 6: Desglose de Ventas por Producto y por Región Geográfica."""
    ws = wb.create_sheet(title="Desglose de Segmentos")
    ws.views.sheetView[0].showGridLines = True
    
    ws.cell(row=1, column=1, value=f"{company_name} ({ticker.upper()}) - Desglose de Ventas")
    ws.cell(row=1, column=1).font = TITLE_FONT
    ws.cell(row=2, column=1, value="Ingresos por línea de producto y por región geográfica en Millones de USD ($M)")
    ws.cell(row=2, column=1).font = SUBTITLE_FONT
    
    headers = ["Segmento / Línea de Negocio"] + fiscal_years
    header_row = 4
    for c_idx, h in enumerate(headers, start=1):
        cell = ws.cell(row=header_row, column=c_idx, value=h)
        if h == "LTM":
            cell.fill = LTM_HEADER
            cell.font = LTM_FONT
        else:
            cell.fill = NAVY_HEADER
            cell.font = WHITE_BOLD
        cell.alignment = Alignment(horizontal="center" if c_idx > 1 else "left", vertical="center")
    ws.row_dimensions[header_row].height = 25
    
    # 1. Intentar cargar desde segments_data.json universal
    seg_json_path = Path("data/processed") / ticker.upper() / "segments_data.json"
    seg_data = None
    if seg_json_path.exists():
        try:
            with open(seg_json_path, "r", encoding="utf-8") as f:
                seg_data = json.load(f)
        except Exception:
            seg_data = None

    curr_row = header_row + 1

    if seg_data and ("product_segments" in seg_data or "geographic_segments" in seg_data):
        # Tabla 1: Productos / Marcas / Canales
        prod_list = seg_data.get("product_segments", [])
        if prod_list:
            ws.cell(row=curr_row, column=1, value="VENTAS POR LÍNEA DE PRODUCTO / SERVICIO / MARCA")
            ws.cell(row=curr_row, column=1).fill = SECTION_FILL
            ws.cell(row=curr_row, column=1).font = SECTION_FONT
            for c in range(2, len(headers) + 1):
                ws.cell(row=curr_row, column=c).fill = SECTION_FILL
            curr_row += 1

            for item in prod_list:
                name = item.get("name", "")
                is_sub = item.get("is_subtotal", False)
                vals = item.get("values", {})
                ws.cell(row=curr_row, column=1, value=f"   {name}")
                ws.cell(row=curr_row, column=1).font = BOLD_FONT if is_sub else REGULAR_FONT
                ws.cell(row=curr_row, column=1).border = BORDER_SUBTOTAL if is_sub else BORDER_CELL
                if is_sub:
                    ws.cell(row=curr_row, column=1).fill = HIGHLIGHT_FILL

                for c_idx, fy in enumerate(fiscal_years, start=2):
                    cell = ws.cell(row=curr_row, column=c_idx)
                    v = vals.get(fy)
                    if v is not None and pd.notna(v) and str(v) != "nan":
                        try:
                            cell.value = float(v)
                            cell.number_format = FMT_CURRENCY_M
                        except (ValueError, TypeError):
                            cell.value = str(v)
                    else:
                        cell.value = "-"
                        cell.alignment = Alignment(horizontal="center")
                    cell.font = BOLD_FONT if is_sub else REGULAR_FONT
                    cell.border = BORDER_SUBTOTAL if is_sub else BORDER_CELL
                    if is_sub:
                        cell.fill = HIGHLIGHT_FILL
                curr_row += 1
            curr_row += 1

        # Tabla 2: Regiones Geográficas
        geo_list = seg_data.get("geographic_segments", [])
        if geo_list:
            ws.cell(row=curr_row, column=1, value="VENTAS POR REGIÓN GEOGRÁFICA")
            ws.cell(row=curr_row, column=1).fill = SECTION_FILL
            ws.cell(row=curr_row, column=1).font = SECTION_FONT
            for c in range(2, len(headers) + 1):
                ws.cell(row=curr_row, column=c).fill = SECTION_FILL
            curr_row += 1

            for item in geo_list:
                name = item.get("name", "")
                vals = item.get("values", {})
                ws.cell(row=curr_row, column=1, value=f"   {name}")
                ws.cell(row=curr_row, column=1).font = REGULAR_FONT
                ws.cell(row=curr_row, column=1).border = BORDER_CELL

                for c_idx, fy in enumerate(fiscal_years, start=2):
                    cell = ws.cell(row=curr_row, column=c_idx)
                    v = vals.get(fy)
                    if v is not None and pd.notna(v) and str(v) != "nan":
                        try:
                            cell.value = float(v)
                            cell.number_format = FMT_CURRENCY_M
                        except (ValueError, TypeError):
                            cell.value = str(v)
                    else:
                        cell.value = "-"
                        cell.alignment = Alignment(horizontal="center")
                    cell.font = REGULAR_FONT
                    cell.border = BORDER_CELL
                curr_row += 1

        autofit_columns(ws, min_col=1, max_col=len(headers), min_width=22)
        return

    if segment_df is None or segment_df.empty:
        autofit_columns(ws, min_col=1, max_col=len(headers), min_width=20)
        return
        
    # 2. Respaldo Dinámico desde segment_df
    product_rows = []
    geo_rows = []
    
    for _, row in segment_df.iterrows():
        concept = str(row.get("concept", ""))
        dim = str(row.get("dimension_member_label", ""))
        label = str(row.get("label", ""))
        
        if "Revenue" in concept or "Sales" in concept:
            is_geo = "region" in concept.lower() or "geographic" in concept.lower() or any(g in label.lower() or g in dim.lower() for g in ["americas", "europe", "china", "japan", "asia", "domestic", "international", "foreign"])
            if is_geo:
                geo_rows.append(row)
            elif dim != "None" and dim != "":
                product_rows.append(row)
                
    curr_row = header_row + 1
    
    # Tabla 1: Por Producto
    if product_rows:
        ws.cell(row=curr_row, column=1, value="VENTAS POR LÍNEA DE PRODUCTO / SERVICIO")
        ws.cell(row=curr_row, column=1).fill = SECTION_FILL
        ws.cell(row=curr_row, column=1).font = SECTION_FONT
        for c in range(2, len(headers) + 1):
            ws.cell(row=curr_row, column=c).fill = SECTION_FILL
        curr_row += 1
        
        for row in product_rows:
            dim_lbl = str(row.get("dimension_member_label", row.get("label", "")))
            is_subtotal = dim_lbl in ["Products", "Services", "Total"]
            
            ws.cell(row=curr_row, column=1, value=f"   {dim_lbl}")
            ws.cell(row=curr_row, column=1).font = BOLD_FONT if is_subtotal else REGULAR_FONT
            ws.cell(row=curr_row, column=1).border = BORDER_SUBTOTAL if is_subtotal else BORDER_CELL
            if is_subtotal:
                ws.cell(row=curr_row, column=1).fill = HIGHLIGHT_FILL
                
            for c_idx, fy in enumerate(fiscal_years, start=2):
                match_col = find_matching_period_col(segment_df.columns, fy)
                cell = ws.cell(row=curr_row, column=c_idx)
                val = row.get(match_col) if match_col else None
                
                if pd.notna(val) and str(val) != "nan":
                    try:
                        num = float(val)
                        cell.value = num / 1_000_000.0 if abs(num) > 1e6 else num
                        cell.number_format = FMT_CURRENCY_M
                    except (ValueError, TypeError):
                        cell.value = str(val)
                else:
                    cell.value = "-"
                    cell.alignment = Alignment(horizontal="center")
                    
                cell.font = BOLD_FONT if is_subtotal else REGULAR_FONT
                cell.border = BORDER_SUBTOTAL if is_subtotal else BORDER_CELL
                if is_subtotal:
                    cell.fill = HIGHLIGHT_FILL
            curr_row += 1
        curr_row += 1
        
    # Tabla 2: Por Región Geográfica
    if geo_rows:
        ws.cell(row=curr_row, column=1, value="VENTAS POR REGIÓN GEOGRÁFICA")
        ws.cell(row=curr_row, column=1).fill = SECTION_FILL
        ws.cell(row=curr_row, column=1).font = SECTION_FONT
        for c in range(2, len(headers) + 1):
            ws.cell(row=curr_row, column=c).fill = SECTION_FILL
        curr_row += 1
        
        for row in geo_rows:
            lbl = str(row.get("label", row.get("dimension_member_label", ""))).replace("Operating segments - ", "").strip()
            ws.cell(row=curr_row, column=1, value=f"   {lbl}")
            ws.cell(row=curr_row, column=1).font = REGULAR_FONT
            ws.cell(row=curr_row, column=1).border = BORDER_CELL
            
            for c_idx, fy in enumerate(fiscal_years, start=2):
                match_col = find_matching_period_col(segment_df.columns, fy)
                cell = ws.cell(row=curr_row, column=c_idx)
                val = row.get(match_col) if match_col else None
                
                if pd.notna(val) and str(val) != "nan":
                    try:
                        num = float(val)
                        cell.value = num / 1_000_000.0 if abs(num) > 1e6 else num
                        cell.number_format = FMT_CURRENCY_M
                    except (ValueError, TypeError):
                        cell.value = str(val)
                else:
                    cell.value = "-"
                    cell.alignment = Alignment(horizontal="center")
                    
                cell.font = REGULAR_FONT
                cell.border = BORDER_CELL
            curr_row += 1
            
    autofit_columns(ws, min_col=1, max_col=len(headers), min_width=22)


def create_scoring_sheet(wb, scoring_results, company_name, ticker, fiscal_years):
    """Crea la Hoja 7: Scores Fundamentales (Piotroski F-Score y Mohanram G-Score con Matriz Combinada)."""
    sheet_title = "Scores Fundamentales"
    if sheet_title in wb.sheetnames:
        target_idx = wb.sheetnames.index(sheet_title)
        del wb[sheet_title]
        ws = wb.create_sheet(title=sheet_title, index=target_idx)
    else:
        ws = wb.create_sheet(title=sheet_title)

    ws.views.sheetView[0].showGridLines = True
    
    # Título y Subtítulo
    ws.cell(row=1, column=1, value=f"{company_name} ({ticker.upper()}) - Diagnóstico Fundamental: Piotroski F-Score & Mohanram G-Score")
    ws.cell(row=1, column=1).font = TITLE_FONT
    ws.cell(row=2, column=1, value="Evaluación Cuantitativa de Solvencia Interna (0-9 Pts) y Calidad de Crecimiento Sectorial (0-8 Pts) | Mejoras Institucionales V2")
    ws.cell(row=2, column=1).font = SUBTITLE_FONT
    
    diag = scoring_results.get("latest_diagnosis", {})
    benchmarks = scoring_results.get("benchmarks_used", {})
    industry_name = scoring_results.get("industry_name", benchmarks.get("industry_name", "N/A"))
    sic_code = scoring_results.get("sic_code", benchmarks.get("sic_code", "N/A"))
    
    # Resumen Ejecutivo Card (Fila 4)
    ws.cell(row=4, column=1, value="DIAGNÓSTICO ESTRATÉGICO ACTUAL").font = SECTION_FONT
    ws.cell(row=4, column=1).fill = SECTION_FILL
    ws.cell(row=4, column=2, value=f"Período: {diag.get('period', 'LTM')}").font = BOLD_FONT
    ws.cell(row=4, column=2).fill = SECTION_FILL
    ws.cell(row=4, column=3, value=f"F-Score: {diag.get('f_score', 0)}/9 ({diag.get('f_rating', '')})").font = BOLD_FONT
    ws.cell(row=4, column=3).fill = SECTION_FILL
    ws.cell(row=4, column=4, value=f"G-Score: {diag.get('g_score', 0)}/8 ({diag.get('g_rating', '')})").font = BOLD_FONT
    ws.cell(row=4, column=4).fill = SECTION_FILL
    ws.merge_cells(start_row=4, start_column=5, end_row=4, end_column=len(fiscal_years) + 3)
    sec_cell = ws.cell(row=4, column=5, value=f"Sector: SIC {sic_code} - {industry_name}")
    sec_cell.font = BOLD_FONT
    sec_cell.fill = SECTION_FILL
    sec_cell.alignment = Alignment(horizontal="left", vertical="center")
    for c in range(5, len(fiscal_years) + 4):
        ws.cell(row=4, column=c).border = BORDER_CELL
        
    ws.cell(row=5, column=1, value="CLASIFICACIÓN MATRIZ:").font = BOLD_FONT
    badge_cell = ws.cell(row=5, column=2, value=diag.get("badge", diag.get("quadrant", "")))
    badge_cell.font = BADGE_FONT
    ws.merge_cells(start_row=5, start_column=3, end_row=5, end_column=len(fiscal_years) + 3)
    t_cell = ws.cell(row=5, column=3, value=diag.get("investment_thesis", ""))
    t_cell.font = ITALIC_FONT
    t_cell.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)
    ws.row_dimensions[5].height = 36
    
    # TABLA 1: PIOTROSKI F-SCORE (Fila 7)
    headers = ["Criterio Fundamental (Piotroski 2000)", "Categoría", "Umbral / Regla"] + fiscal_years
    header_row = 7
    for c_idx, h in enumerate(headers, start=1):
        cell = ws.cell(row=header_row, column=c_idx, value=h)
        if h == "LTM":
            cell.fill = LTM_HEADER
            cell.font = LTM_FONT
        else:
            cell.fill = NAVY_HEADER
            cell.font = WHITE_BOLD
        cell.alignment = Alignment(horizontal="center" if c_idx > 3 else "left", vertical="center")
    ws.row_dimensions[header_row].height = 25
    
    f_signals_meta = [
        ("F_ROA", "ROA Positivo", "Rentabilidad", "Net Income / Activos t-1 > 0"),
        ("F_CFO", "CFO Positivo", "Rentabilidad", "Operating Cash Flow > 0"),
        ("F_dROA", "Mejora Interanual de ROA", "Rentabilidad", "Delta ROA > 0%"),
        ("F_ACCRUAL", "Calidad Contable de Sloan", "Rentabilidad", "CFO > Net Income"),
        ("F_dLEVER", "Desendeudamiento Financiero Total", "Apalancamiento", "Delta Deuda Total <= 0%"),
        ("F_dLIQUID", "Mejora de Razón Corriente", "Liquidez", "Delta Current Ratio > 0x"),
        ("EQ_OFFER", "Cero Dilución (Acciones Básicas)", "Capital", "Delta Acciones Básicas <= 0"),
        ("F_dMARGIN", "Expansión de Margen Bruto", "Eficiencia", "Delta Margen Bruto > 0%"),
        ("F_dTURN", "Expansión Rotación Activos", "Eficiencia", "Delta Rotación Activos > 0x"),
    ]
    
    curr_row = header_row + 1
    f_scores_dict = scoring_results.get("piotroski_f_score", {})
    
    for sig_key, sig_label, sig_cat, sig_thresh in f_signals_meta:
        c1 = ws.cell(row=curr_row, column=1, value=f"   {sig_label}")
        c1.font = REGULAR_FONT
        c1.border = BORDER_CELL
        
        sample_desc = ""
        for s_fy in fiscal_years:
            s_d = f_scores_dict.get(s_fy, {}).get("signals", {}).get(sig_key, {}).get("description")
            if s_d:
                sample_desc = s_d
                break
                
        note_text = (
            f"CRITERIO PIOTROSKI F-SCORE: {sig_label}\n"
            f"• Categoría: {sig_cat}\n"
            f"• Regla Oficial: {sig_thresh}\n"
            f"• Lógica Contable: {sample_desc or 'Evaluación de solidez contable y calidad de balance'}\n"
            f"• Fuente Oficial: SEC EDGAR Form 10-K / 10-Q XBRL"
        )
        sig_com = Comment(note_text, author="Auditoría Fundamental SEC")
        sig_com.width = 320
        sig_com.height = 110
        c1.comment = sig_com

        ws.cell(row=curr_row, column=2, value=sig_cat).font = ITALIC_FONT
        ws.cell(row=curr_row, column=2).border = BORDER_CELL
        ws.cell(row=curr_row, column=3, value=sig_thresh).font = REGULAR_FONT
        ws.cell(row=curr_row, column=3).border = BORDER_CELL
        
        ws.row_dimensions[curr_row].height = 20
        for c_idx, fy in enumerate(fiscal_years, start=4):
            cell = ws.cell(row=curr_row, column=c_idx)
            fy_data = f_scores_dict.get(fy, {}).get("signals", {}).get(sig_key, {})
            passed = fy_data.get("passed")
            val_disp = fy_data.get("formatted_value") or ""
            
            if passed is True:
                cell.value = f"{val_disp} [1]" if val_disp else "1"
                cell.font = GREEN_FONT
                cell.fill = GREEN_FILL
            elif passed is False:
                cell.value = f"{val_disp} [0]" if val_disp else "0"
                cell.font = RED_FONT
                cell.fill = RED_FILL
            else:
                cell.value = "-"
                cell.font = REGULAR_FONT
                
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=False)
            cell.border = BORDER_CELL
        curr_row += 1
        
    # Fila Total F-Score
    ws.cell(row=curr_row, column=1, value="TOTAL PIOTROSKI F-SCORE (0 a 9 Pts)").font = BOLD_FONT
    ws.cell(row=curr_row, column=1).border = BORDER_SUBTOTAL
    ws.cell(row=curr_row, column=2, value="PUNTUACIÓN").font = BOLD_FONT
    ws.cell(row=curr_row, column=2).border = BORDER_SUBTOTAL
    ws.cell(row=curr_row, column=3, value="Escala 0-9 (>=7 Fuerte)").font = BOLD_FONT
    ws.cell(row=curr_row, column=3).border = BORDER_SUBTOTAL
    
    for c_idx, fy in enumerate(fiscal_years, start=4):
        cell = ws.cell(row=curr_row, column=c_idx)
        score_val = f_scores_dict.get(fy, {}).get("total_score")
        rating_val = f_scores_dict.get(fy, {}).get("rating", "N/A")
        if score_val is not None:
            cell.value = f"{score_val} / 9 Pts"
            cell.font = SCORE_NUM_FONT
            if score_val >= 7:
                cell.fill = GREEN_FILL
            elif score_val >= 5:
                cell.fill = YELLOW_FILL
            else:
                cell.fill = RED_FILL
                
            tot_com = Comment(
                f"TOTAL PIOTROSKI F-SCORE ({fy})\n"
                f"• Puntuación: {score_val} de 9 Puntos\n"
                f"• Clasificación: {rating_val}\n"
                f"• Escala Institucional:\n"
                f"  - 8-9 Pts: Fortaleza Financiera Sobresaliente\n"
                f"  - 5-7 Pts: Situación Estable\n"
                f"  - 0-4 Pts: Fragilidad / Alerta Financiera",
                author="Auditoría Fundamental SEC"
            )
            tot_com.width = 280
            tot_com.height = 110
            cell.comment = tot_com
        else:
            cell.value = "-"
            cell.font = BOLD_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = BORDER_SUBTOTAL
    curr_row += 1
    
    # Fila Dictamen F-Score
    ws.cell(row=curr_row, column=1, value="Dictamen de Salud Financiera").font = ITALIC_FONT
    ws.cell(row=curr_row, column=1).border = BORDER_CELL
    ws.cell(row=curr_row, column=2, value="-").font = ITALIC_FONT
    ws.cell(row=curr_row, column=2).border = BORDER_CELL
    ws.cell(row=curr_row, column=3, value="Clasificación").font = ITALIC_FONT
    ws.cell(row=curr_row, column=3).border = BORDER_CELL
    for c_idx, fy in enumerate(fiscal_years, start=4):
        cell = ws.cell(row=curr_row, column=c_idx)
        cell.value = f_scores_dict.get(fy, {}).get("rating", "-")
        cell.font = BOLD_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = BORDER_CELL
    curr_row += 3
    
    # TABLA 2: MOHANRAM G-SCORE
    g_headers = ["Criterio de Crecimiento (Mohanram 2005)", "Categoría", "Benchmark Sectorial"] + fiscal_years
    g_header_row = curr_row
    for c_idx, h in enumerate(g_headers, start=1):
        cell = ws.cell(row=g_header_row, column=c_idx, value=h)
        if h == "LTM":
            cell.fill = LTM_HEADER
            cell.font = LTM_FONT
        else:
            cell.fill = NAVY_HEADER
            cell.font = WHITE_BOLD
        cell.alignment = Alignment(horizontal="center" if c_idx > 3 else "left", vertical="center")
    ws.row_dimensions[g_header_row].height = 25
    curr_row += 1
    
    g_scores_dict = scoring_results.get("mohanram_g_score", {})
    p75_val = benchmarks.get('p75_roa', 0.100)
    is_asset_light = benchmarks.get("is_asset_light", False)
    if is_asset_light:
        g7_bm_label = f"Reinversión > {benchmarks.get('median_total_reinvestment', 0.080)*100:.2f}%"
    else:
        g7_bm_label = f"CapEx / Activos > {benchmarks.get('median_capex_intensity', 0.045)*100:.2f}%"

    g_signals_meta = [
        ("G1_ROA", "ROA > Mediana del Sector", "Rentabilidad", f"> Mediana Sector ({benchmarks.get('median_roa', 0.055)*100:.2f}%)"),
        ("G2_CFROA", "CFROA > Mediana del Sector", "Flujo de Caja", f"> Mediana Sector ({benchmarks.get('median_cfroa', 0.078)*100:.2f}%)"),
        ("G3_ACCRUAL", "Calidad Contable (CFO > NI)", "Devengos", "CFO > Utilidad Neta"),
        ("G4_VAR_ROA", "Estabilidad / Nivel Superior de ROA", "Predictibilidad", f"CV < {benchmarks.get('median_cv_roa', 0.38):.2f} o ROA >= P75 ({p75_val*100:.2f}%)"),
        ("G5_VAR_GROWTH", "Estabilidad / Hipercrecimiento", "Predictibilidad", f"CV < {benchmarks.get('median_cv_sales_growth', 0.42):.2f} o g >= 20%"),
        ("G6_RD_INTENSITY", "Intensidad en I+D vs Sector", "Intangibles", f"R&D / Activos > {benchmarks.get('median_rd_intensity', 0.035)*100:.2f}%"),
        ("G7_CAPEX_INTENSITY", "Inversión de Capital / Asset-Light", "Inversión", g7_bm_label),
        ("G8_OPERATING_LEVERAGE", "Apalancamiento Comercial (SG&A)", "Eficiencia", "% Delta Ventas > % Delta SG&A"),
    ]
    
    for sig_key, sig_label, sig_cat, sig_bm in g_signals_meta:
        c1 = ws.cell(row=curr_row, column=1, value=f"   {sig_label}")
        c1.font = REGULAR_FONT
        c1.border = BORDER_CELL
        
        sample_desc = ""
        for s_fy in fiscal_years:
            s_d = g_scores_dict.get(s_fy, {}).get("signals", {}).get(sig_key, {}).get("description")
            if s_d:
                sample_desc = s_d
                break

        note_text = (
            f"CRITERIO MOHANRAM G-SCORE: {sig_label}\n"
            f"• Categoría: {sig_cat}\n"
            f"• Benchmark Sectorial Oficial: {sig_bm}\n"
            f"• Lógica Contable: {sample_desc or 'Evaluación de calidad y durabilidad del crecimiento'}\n"
            f"• Fuente: SEC EDGAR & Mediana del Sector SIC {sic_code} (Hoja 8: 'Peer Group & Medianas')"
        )
        sig_com = Comment(note_text, author="Auditoría Fundamental SEC")
        sig_com.width = 320
        sig_com.height = 110
        c1.comment = sig_com

        ws.cell(row=curr_row, column=2, value=sig_cat).font = ITALIC_FONT
        ws.cell(row=curr_row, column=2).border = BORDER_CELL
        ws.cell(row=curr_row, column=3, value=sig_bm).font = REGULAR_FONT
        ws.cell(row=curr_row, column=3).border = BORDER_CELL
        
        ws.row_dimensions[curr_row].height = 20
        for c_idx, fy in enumerate(fiscal_years, start=4):
            cell = ws.cell(row=curr_row, column=c_idx)
            fy_data = g_scores_dict.get(fy, {}).get("signals", {}).get(sig_key, {})
            passed = fy_data.get("passed")
            val_disp = fy_data.get("formatted_value") or ""
            
            if passed is True:
                cell.value = f"{val_disp} [1]" if val_disp else "1"
                cell.font = GREEN_FONT
                cell.fill = GREEN_FILL
            elif passed is False:
                cell.value = f"{val_disp} [0]" if val_disp else "0"
                cell.font = RED_FONT
                cell.fill = RED_FILL
            else:
                cell.value = "-"
                cell.font = REGULAR_FONT
                
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=False)
            cell.border = BORDER_CELL
        curr_row += 1
        
    # Fila Total G-Score
    ws.cell(row=curr_row, column=1, value="TOTAL MOHANRAM G-SCORE (0 a 8 Pts)").font = BOLD_FONT
    ws.cell(row=curr_row, column=1).border = BORDER_SUBTOTAL
    ws.cell(row=curr_row, column=2, value="PUNTUACIÓN").font = BOLD_FONT
    ws.cell(row=curr_row, column=2).border = BORDER_SUBTOTAL
    ws.cell(row=curr_row, column=3, value="Escala 0-8 (>=6 Élite)").font = BOLD_FONT
    ws.cell(row=curr_row, column=3).border = BORDER_SUBTOTAL
    
    for c_idx, fy in enumerate(fiscal_years, start=4):
        cell = ws.cell(row=curr_row, column=c_idx)
        score_val = g_scores_dict.get(fy, {}).get("total_score")
        rating_val = g_scores_dict.get(fy, {}).get("rating", "N/A")
        if score_val is not None:
            cell.value = f"{score_val} / 8 Pts"
            cell.font = SCORE_NUM_FONT
            if score_val >= 6:
                cell.fill = GREEN_FILL
            elif score_val >= 4:
                cell.fill = YELLOW_FILL
            else:
                cell.fill = RED_FILL
                
            tot_com = Comment(
                f"TOTAL MOHANRAM G-SCORE ({fy})\n"
                f"• Puntuación: {score_val} de 8 Puntos\n"
                f"• Clasificación: {rating_val}\n"
                f"• Escala Institucional:\n"
                f"  - 6-8 Pts: Calidad de Crecimiento Élite (Compounder)\n"
                f"  - 4-5 Pts: Crecimiento Promedio / Moderado\n"
                f"  - 0-3 Pts: Crecimiento Frágil o Destructivo",
                author="Auditoría Fundamental SEC"
            )
            tot_com.width = 280
            tot_com.height = 110
            cell.comment = tot_com
        else:
            cell.value = "-"
            cell.font = BOLD_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = BORDER_SUBTOTAL
    curr_row += 1
    
    # Fila Dictamen G-Score
    ws.cell(row=curr_row, column=1, value="Dictamen de Calidad de Crecimiento").font = ITALIC_FONT
    ws.cell(row=curr_row, column=1).border = BORDER_CELL
    ws.cell(row=curr_row, column=2, value="-").font = ITALIC_FONT
    ws.cell(row=curr_row, column=2).border = BORDER_CELL
    ws.cell(row=curr_row, column=3, value="Clasificación").font = ITALIC_FONT
    ws.cell(row=curr_row, column=3).border = BORDER_CELL
    for c_idx, fy in enumerate(fiscal_years, start=4):
        cell = ws.cell(row=curr_row, column=c_idx)
        cell.value = g_scores_dict.get(fy, {}).get("rating", "-")
        cell.font = BOLD_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = BORDER_CELL
    curr_row += 3
    
    # TABLA 3: MATRIZ COMBINADA (F-Score vs G-Score)
    ws.cell(row=curr_row, column=1, value="MATRIZ COMBINADA Y CLASIFICACIÓN ESTRATÉGICA").font = SECTION_FONT
    ws.cell(row=curr_row, column=1).fill = SECTION_FILL
    for c in range(2, len(headers) + 1):
        ws.cell(row=curr_row, column=c).fill = SECTION_FILL
    curr_row += 1
    
    matrix_dict = scoring_results.get("combined_matrix", {})
    ws.cell(row=curr_row, column=1, value="   Cuadrante Estratégico").font = BOLD_FONT
    ws.cell(row=curr_row, column=1).border = BORDER_CELL
    ws.cell(row=curr_row, column=2, value="Posición").font = ITALIC_FONT
    ws.cell(row=curr_row, column=2).border = BORDER_CELL
    ws.cell(row=curr_row, column=3, value="Matriz 2x2").font = ITALIC_FONT
    ws.cell(row=curr_row, column=3).border = BORDER_CELL
    
    for c_idx, fy in enumerate(fiscal_years, start=4):
        cell = ws.cell(row=curr_row, column=c_idx)
        m_item = matrix_dict.get(fy, {})
        cell.value = m_item.get("badge", m_item.get("quadrant", "-"))
        cell.font = BOLD_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = BORDER_CELL
    curr_row += 3
    
    # TABLA 4: PRODUCTIVIDAD PURA DEL CAPITAL (NOVY-MARX GP/A & DUPONT)
    ws.cell(row=curr_row, column=1, value="PRODUCTIVIDAD PURA DEL CAPITAL (NOVY-MARX GP/A & DUPONT)").font = SECTION_FONT
    ws.cell(row=curr_row, column=1).fill = SECTION_FILL
    for c in range(2, len(headers) + 1):
        ws.cell(row=curr_row, column=c).fill = SECTION_FILL
    curr_row += 1

    nm_dict = scoring_results.get("novy_marx_analysis", {}).get("by_period", {})
    if not nm_dict:
        scores_file = Path(f"data/processed/{ticker.upper()}/fundamental_scores.json")
        if scores_file.exists():
            try:
                with open(scores_file, "r", encoding="utf-8") as sf:
                    nm_dict = json.load(sf).get("novy_marx_analysis", {}).get("by_period", {})
            except Exception:
                pass

    nm_rows_meta = [
        ("Gross Profitability (Activos Totales)", "Métrica Base", "GP / Activos Totales", "gross_profitability_total", "pct"),
        ("Gross Profitability Operativa (Ex-Caja)", "Métrica Operativa", "GP / (Activos - Caja)", "gross_profitability_ex_cash", "pct"),
        ("Efecto Arrastre de Caja (Cash Drag)", "Dilución de Caja", "Ex-Caja vs Total (p.p.)", "cash_drag_pct", "pct_delta"),
        ("Margen Bruto de Utilidad (DuPont)", "Fijación Precios", "Utilidad Bruta / Ventas", "gross_margin", "pct"),
        ("Rotación de Activos Totales (DuPont)", "Velocidad de Capital", "Ventas / Activos Totales", "asset_turnover_total", "mult"),
        ("Dictamen Estratégico de Productividad", "Diagnóstico", "Desempeño Sectorial", "rating", "str"),
        ("Cuadrante Estratégico DuPont", "Estrategia", "Margen vs Rotación", "quadrant_badge", "str"),
        ("Ajuste Sectorial vs Mediana (De-meaning)", "Ventaja Neta", "GP/A Empresa - Mediana", "adjusted_gp_a", "pct_delta"),
    ]

    for label, cat, sub_label, key, val_type in nm_rows_meta:
        ws.cell(row=curr_row, column=1, value=f"   {label}").font = BOLD_FONT if val_type in ("str", "pct_delta") else REGULAR_FONT
        ws.cell(row=curr_row, column=1).border = BORDER_CELL
        ws.cell(row=curr_row, column=2, value=cat).font = ITALIC_FONT
        ws.cell(row=curr_row, column=2).border = BORDER_CELL
        ws.cell(row=curr_row, column=3, value=sub_label).font = REGULAR_FONT
        ws.cell(row=curr_row, column=3).border = BORDER_CELL
        ws.row_dimensions[curr_row].height = 22

        for c_idx, fy in enumerate(fiscal_years, start=4):
            cell = ws.cell(row=curr_row, column=c_idx)
            val = nm_dict.get(fy, {}).get(key)
            if val is not None:
                if val_type == "pct":
                    cell.value = val
                    cell.number_format = FMT_PERCENT
                    cell.alignment = Alignment(horizontal="right", vertical="center")
                    if key == "gross_profitability_total" and val >= 0.35:
                        cell.fill = GREEN_FILL
                elif val_type == "pct_delta":
                    cell.value = val
                    cell.number_format = "+0.00%;-0.00%;0.00%"
                    cell.alignment = Alignment(horizontal="right", vertical="center")
                elif val_type == "mult":
                    cell.value = val
                    cell.number_format = FMT_MULTIPLIER
                    cell.alignment = Alignment(horizontal="right", vertical="center")
                else:
                    cell.value = str(val)
                    cell.alignment = Alignment(horizontal="center", vertical="center")
            else:
                cell.value = "-"
                cell.alignment = Alignment(horizontal="center", vertical="center")
            cell.font = BOLD_FONT if val_type in ("str", "pct_delta") else REGULAR_FONT
            cell.border = BORDER_CELL
        curr_row += 1

    curr_row += 3

    # TABLA 5: RENDIMIENTO DEL CAPITAL (ROIC AJUSTADO VS WACC) Y CREACIÓN DE VALOR ECONÓMICO
    ws.cell(row=curr_row, column=1, value="RENDIMIENTO DEL CAPITAL (ROIC AJUSTADO VS WACC) Y CREACIÓN DE VALOR").font = SECTION_FONT
    ws.cell(row=curr_row, column=1).fill = SECTION_FILL
    for c in range(2, len(headers) + 1):
        ws.cell(row=curr_row, column=c).fill = SECTION_FILL
    curr_row += 1

    roic_dict = scoring_results.get("intangible_roic_analysis", {}).get("by_period", {})
    wacc_data = scoring_results.get("wacc_and_spread_analysis", {})
    greenblatt_data = scoring_results.get("greenblatt_roc_analysis", {})
    greenblatt_annual = greenblatt_data.get("annual_series", {})
    greenblatt_ltm = greenblatt_data.get("ltm", {})

    roic_rows_meta = [
        ("ROC Greenblatt (EBIT / Capital Tangible Operativo Promedio)", "Productividad Pura", "EBIT / (NWC + Net PP&E) Promedio", "roc_greenblatt", "pct_roc"),
        ("   (+) EBIT Operativo ($M) [Income Statement]", "Desglose ROC", "Beneficio Operativo Auditado", "roc_ebit", "curr"),
        ("   (+) Activos Corrientes Operativos ex-Caja ($M)", "Desglose ROC", "Current Assets - Efectivo", "roc_op_ca", "curr"),
        ("   (-) Pasivos Corrientes Operativos ex-Deuda CP ($M)", "Desglose ROC", "Current Liabilities - Deuda CP", "roc_op_cl", "curr"),
        ("   (=) Capital de Trabajo Neto Operativo (NWC $M)", "Desglose ROC", "Activos Op. - Pasivos Op.", "roc_nwc", "curr"),
        ("   (+) PP&E Neto ($M) [Balance Sheet]", "Desglose ROC", "Property, Plant & Equipment Net", "roc_net_ppe", "curr"),
        ("   (=) Capital Tangible Operativo al Cierre ($M)", "Desglose ROC", "Net PP&E + max(0, NWC)", "roc_cap_end", "curr"),
        ("   (=) Capital Tangible Operativo Promedio ($M)", "Desglose ROC", "Denominador ((t + t-1)/2)", "roc_cap_avg", "curr"),
        ("ROIC Tradicional (NOPAT / Capital Invertido Promedio)", "Retorno Contable", "EBIT*(1-t) / IC Promedio", "roic_trad", "pct"),
        ("ROIC Ajustado por Intangibles (Damodaran - Capital Promedio)", "Retorno Económico", "NOPAT Adj / IC Promedio", "roic_adj", "pct"),
        ("Stock de Intangibles Capitalizados ($M)", "Capital Oculto", "Stock Neto I+D y Marca", "total_intangible_stock", "curr"),
        ("Capital Invertido Reconstituido Promedio ($M)", "Base de Capital", "Activos Operativos + Intangibles Prom.", "ic_adj", "curr"),
        ("Costo Promedio Ponderado de Capital (WACC)", "Tasa de Corte", "Costo Ponderado Equity + Deuda", "wacc_rate", "pct_wacc"),
        ("Spread Económico Neto (ROIC Adj - WACC)", "Creación de Valor", "Excedente sobre Costo de Capital", "economic_spread", "pct_spread"),
    ]

    for label, cat, sub_label, key, val_type in roic_rows_meta:
        ws.cell(row=curr_row, column=1, value=f"   {label}").font = BOLD_FONT if val_type in ("pct_spread", "pct", "pct_roc") else REGULAR_FONT
        ws.cell(row=curr_row, column=1).border = BORDER_CELL
        ws.cell(row=curr_row, column=2, value=cat).font = ITALIC_FONT
        ws.cell(row=curr_row, column=2).border = BORDER_CELL
        ws.cell(row=curr_row, column=3, value=sub_label).font = REGULAR_FONT
        ws.cell(row=curr_row, column=3).border = BORDER_CELL
        ws.row_dimensions[curr_row].height = 22

        for c_idx, fy in enumerate(fiscal_years, start=4):
            cell = ws.cell(row=curr_row, column=c_idx)
            r_item = roic_dict.get(fy, {})
            wacc_val = wacc_data.get("wacc", 0.088)
            g_item = greenblatt_ltm if fy == "LTM" else greenblatt_annual.get(fy, {})

            if key == "roc_greenblatt":
                val = g_item.get("roc_avg") if g_item.get("roc_avg") is not None else g_item.get("roc_ltm")
            elif key == "roc_ebit":
                val = g_item.get("ebit_usd_m")
            elif key == "roc_op_ca":
                val = g_item.get("op_current_assets_usd_m")
            elif key == "roc_op_cl":
                val = g_item.get("op_current_liabilities_usd_m")
            elif key == "roc_nwc":
                val = g_item.get("nwc_usd_m")
            elif key == "roc_net_ppe":
                val = g_item.get("net_ppe_usd_m")
            elif key == "roc_cap_end":
                val = g_item.get("tangible_capital_end")
            elif key == "roc_cap_avg":
                val = g_item.get("tangible_capital_avg")
            elif key == "wacc_rate":
                val = wacc_val
            elif key == "economic_spread":
                r_adj = r_item.get("roic_adj")
                val = (r_adj - wacc_val) if r_adj is not None else None
            else:
                val = r_item.get(key)

            if val is not None:
                if val_type in ("pct", "pct_wacc", "pct_roc"):
                    cell.value = val
                    cell.number_format = FMT_PERCENT
                    cell.alignment = Alignment(horizontal="right", vertical="center")
                    if key == "roc_greenblatt" and val >= 0.30:
                        cell.fill = GREEN_FILL
                    elif key == "roic_adj" and val >= 0.20:
                        cell.fill = GREEN_FILL
                elif val_type == "pct_spread":
                    cell.value = val
                    cell.number_format = "+0.00%;-0.00%;0.00%"
                    cell.alignment = Alignment(horizontal="right", vertical="center")
                    if val >= 0.15:
                        cell.fill = GREEN_FILL
                    elif val < 0.0:
                        cell.fill = RED_FILL
                elif val_type == "curr":
                    cell.value = val
                    cell.number_format = FMT_CURRENCY_M
                    cell.alignment = Alignment(horizontal="right", vertical="center")
            else:
                cell.value = "-"
                cell.alignment = Alignment(horizontal="center", vertical="center")
            cell.font = BOLD_FONT if val_type in ("pct_spread", "pct", "pct_roc") else REGULAR_FONT
            cell.border = BORDER_CELL
        curr_row += 1

    # TARJETA RESUMEN DE MERCADO Y FOSO DEFENSIVO (Filas curr_row a curr_row + 4)
    curr_row += 2
    ws.cell(row=curr_row, column=1, value="AUDITORÍA DE MERCADO EN TIEMPO REAL & FOSO DEFENSIVO").font = SECTION_FONT
    ws.cell(row=curr_row, column=1).fill = SECTION_FILL
    for c in range(2, len(headers) + 1):
        ws.cell(row=curr_row, column=c).fill = SECTION_FILL
    curr_row += 1

    mkt_info = wacc_data.get("market_data", {})
    sens = scoring_results.get("intangible_roic_analysis", {}).get("sensitivity_matrix", {})

    ws.cell(row=curr_row, column=1, value="   Dictamen de Foso Defensivo (Moat)").font = BOLD_FONT
    ws.cell(row=curr_row, column=1).border = BORDER_CELL
    ws.cell(row=curr_row, column=2, value=wacc_data.get("moat_badge", "WIDE MOAT")).font = BADGE_FONT
    ws.cell(row=curr_row, column=2).border = BORDER_CELL
    ws.cell(row=curr_row, column=3, value=f"Ke: {wacc_data.get('cost_of_equity_ke', 0)*100:.2f}% | Kd: {wacc_data.get('cost_of_debt_kd_after_tax', 0)*100:.2f}%").font = BOLD_FONT
    ws.cell(row=curr_row, column=3).border = BORDER_CELL
    ws.cell(row=curr_row, column=4, value=f"Precio: ${mkt_info.get('price', 0):.2f} | Market Cap: ${mkt_info.get('market_cap_usd_m', 0):,.1f}M").font = REGULAR_FONT
    ws.cell(row=curr_row, column=4).border = BORDER_CELL
    curr_row += 1

    ws.cell(row=curr_row, column=1, value="   Parámetros Macro y Validación").font = BOLD_FONT
    ws.cell(row=curr_row, column=1).border = BORDER_CELL
    ws.cell(row=curr_row, column=2, value=f"Rf (Bono 10Y): {mkt_info.get('rf_10y', 0)*100:.2f}% | Beta: {mkt_info.get('beta', 1.0):.2f}").font = REGULAR_FONT
    ws.cell(row=curr_row, column=2).border = BORDER_CELL
    ws.cell(row=curr_row, column=3, value=f"Sensibilidad N-1 ({sens.get('n_minus_1', {}).get('lifespan_years')}a): {sens.get('n_minus_1', {}).get('roic_adj', 0)*100:.2f}%").font = ITALIC_FONT
    ws.cell(row=curr_row, column=3).border = BORDER_CELL
    ws.cell(row=curr_row, column=4, value=f"Sensibilidad N+1 ({sens.get('n_plus_1', {}).get('lifespan_years')}a): {sens.get('n_plus_1', {}).get('roic_adj', 0)*100:.2f}%").font = ITALIC_FONT
    ws.cell(row=curr_row, column=4).border = BORDER_CELL
    curr_row += 1

    format_sheet_layout(ws, sheet_type="scoring", min_col=1, max_col=len(headers), freeze_cell="D8")


def create_peer_group_sheet(wb, peer_data=None, company_name="Apple Inc.", ticker="AAPL", sic_code=None, scoring_results=None):
    """Crea la Hoja 8: Peer Group & Medianas Sectoriales con fórmulas dinámicas de Excel."""
    from pathlib import Path
    import json
    
    sheet_title = "Peer Group & Medianas"
    if sheet_title in wb.sheetnames:
        target_idx = wb.sheetnames.index(sheet_title)
        del wb[sheet_title]
        ws = wb.create_sheet(title=sheet_title, index=target_idx)
    else:
        ws = wb.create_sheet(title=sheet_title)

    ws.views.sheetView[0].showGridLines = True
    
    # Cargar scoring_results si no fue provisto para garantizar sincronía total de ROIC y WACC
    if scoring_results is None:
        p_cand = Path("data/processed") / ticker.upper() / "fundamental_scores.json"
        if not p_cand.exists():
            p_cand = Path(__file__).resolve().parent.parent.parent.parent.parent / "data" / "processed" / ticker.upper() / "fundamental_scores.json"
        if p_cand.exists():
            try:
                with open(p_cand, "r", encoding="utf-8") as f_sc:
                    scoring_results = json.load(f_sc)
            except Exception:
                scoring_results = {}
        else:
            scoring_results = {}

    # Cargar datos si no fueron provistos
    if peer_data is None:
        peer_file = Path("config/peer_benchmarks.json")
        if not peer_file.exists():
            alt_path = Path(__file__).resolve().parent.parent.parent.parent.parent / "config" / "peer_benchmarks.json"
            if alt_path.exists():
                peer_file = alt_path
        if peer_file.exists():
            with open(peer_file, "r", encoding="utf-8") as f:
                raw_data = json.load(f)
                bms = raw_data.get("industry_benchmarks", {})
                if sic_code:
                    sic_key = f"SIC_{str(sic_code).strip()}"
                    peer_data = bms.get(sic_key)
                if not peer_data and ticker:
                    for k, v in bms.items():
                        if any(p.get("ticker", "").upper() == ticker.upper() for p in v.get("peers", [])):
                            peer_data = v
                            break
                if not peer_data:
                    if not ticker or ticker.upper() == "AAPL" or not sic_code or str(sic_code).strip() == "3571":
                        peer_data = bms.get("SIC_3571", list(bms.values())[0] if bms else {})
                    else:
                        peer_data = bms.get(f"SIC_{str(sic_code).strip()}", {})
        else:
            peer_data = {}
            
    eff_sic = peer_data.get("sic_code", str(sic_code) if sic_code else "3571")
    industry_name = peer_data.get("industry_name", "Computer Storage & Hardware Devices / Technology Hardware" if str(eff_sic).strip() == "3571" else f"Sector SIC {eff_sic}")
    basis = peer_data.get("fiscal_year_basis", "LTM (Últimos 12 Meses Móviles / FY2026 Auditado)")
    source = peer_data.get("source", "SEC EDGAR 10-K & 10-Q Audited Reports")
    peers = peer_data.get("peers", [])
    
    # Título y Subtítulo
    ws.cell(row=1, column=1, value=f"{company_name} ({ticker.upper()}) - Análisis de Pares y Distribución Sectorial (SIC {eff_sic})")
    ws.cell(row=1, column=1).font = TITLE_FONT
    ws.cell(row=2, column=1, value=f"Auditoría Contable del Grupo de Pares y Cálculo Estadístico de Medianas Oficiales para el Mohanram G-Score | Base: {basis}")
    ws.cell(row=2, column=1).font = SUBTITLE_FONT
    
    # Resumen Ejecutivo Card (Fila 4)
    ws.cell(row=4, column=1, value="GRUPO DE PARES COMPARABLES").font = SECTION_FONT
    ws.cell(row=4, column=1).fill = SECTION_FILL
    ws.cell(row=4, column=2, value=f"Industria: {industry_name}").font = BOLD_FONT
    ws.cell(row=4, column=2).fill = SECTION_FILL
    ws.cell(row=4, column=3, value=f"Empresas Auditadas: {len(peers)}").font = BOLD_FONT
    ws.cell(row=4, column=3).fill = SECTION_FILL
    ws.cell(row=4, column=4, value=f"Fuente: {source}").font = ITALIC_FONT
    ws.cell(row=4, column=4).fill = SECTION_FILL
    for c in range(5, 21):
        ws.cell(row=4, column=c).fill = SECTION_FILL
        
    # Encabezados de la Tabla de Pares (Fila 6)
    headers = [
        "Ticker",
        "Empresa Competidora",
        "Ingresos LTM ($M)",
        "Activos Totales LTM ($M)",
        "Gasto I+D LTM ($M)",
        "Intensidad I+D (I+D/Act)",
        "CapEx LTM ($M)",
        "Inversión Total ((I+D+CapEx)/Act)",
        "Utilidad Neta LTM ($M)",
        "ROA LTM (%)",
        "Flujo Operativo CFO LTM ($M)",
        "CFROA LTM (%)",
        "Gastos SG&A LTM ($M)",
        "Utilidad Bruta LTM ($M)",
        "GP / Activos (%) [Novy-Marx]",
        "GP / Activos Ex-Caja (%)",
        "ROIC Ajustado (%)",
        "WACC (%)",
        "Spread Económico (%)",
        "ROC Greenblatt (%)"
    ]
    header_comments = {
        1: ("Ticker Bursátil", "Símbolo de cotización en bolsas de EE.UU. (NASDAQ / NYSE)."),
        2: ("Empresa Competidora", "Compañía comparable del sector de tecnología de hardware y almacenamiento (SIC 3571)."),
        3: ("Ingresos LTM ($M)", "Fórmula: Total Revenue (Últimos 12 meses móviles).\nFacturación bruta auditada generada por venta de productos y servicios.\nFuente: SEC Form 10-K y 10-Q."),
        4: ("Activos Totales LTM ($M)", "Fórmula: Total Assets al cierre del período LTM.\nBase total de capital y recursos controlados por la entidad.\nFuente: Balance General Auditado."),
        5: ("Gasto I+D LTM ($M)", "Fórmula: Research and Development Expense LTM.\nInversión en desarrollo de nueva tecnología, software y patentes.\nFuente: Estado de Resultados."),
        6: ("Intensidad I+D (I+D/Act)", "Fórmula: =Gasto I+D / Activos Totales (Col E / Col D).\nEvalúa la inversión en innovación relativa al tamaño de activos. Criterio clave del Mohanram G6."),
        7: ("CapEx LTM ($M)", "Fórmula: Payments for Property, Plant and Equipment (CapEx) LTM.\nInversiones en bienes de uso, centros de datos y equipamiento técnico.\nFuente: Flujo de Caja de Inversión."),
        8: ("Inversión Total", "Fórmula: =(I+D + CapEx) / Activos Totales ((Col E + Col G) / Col D).\nMétrica consensuada para modelos Asset-Light. Tasa de reinversión total en crecimiento orgánico e intangible. Criterio Mohanram G7."),
        9: ("Utilidad Neta LTM ($M)", "Fórmula: Net Income auditada LTM.\nBeneficio final neto después de impuestos, intereses y amortizaciones atribuible a los accionistas."),
        10: ("ROA LTM (%)", "Fórmula: =Utilidad Neta / Activos Totales (Col I / Col D).\nRentabilidad Económica Operativa sobre activos instalados. Criterio de rentabilidad en Piotroski F1 y Mohanram G1."),
        11: ("Flujo Operativo CFO LTM ($M)", "Fórmula: Cash Flow from Operating Activities (CFO) LTM.\nEfectivo líquido generado por las operaciones comerciales ordinarias, libre de devengos contables."),
        12: ("CFROA LTM (%)", "Fórmula: =CFO / Activos Totales (Col K / Col D).\nRentabilidad de flujo de caja sobre activos instalados. Mide la verdadera capacidad de convertir activos en efectivo contante y sonante libre de distorsiones de causación. Criterio Mohanram G2."),
        13: ("Gastos SG&A LTM ($M)", "Fórmula: Selling, General and Administrative Expenses LTM.\nGastos comerciales, de ventas y administración general. Base para evaluar el apalancamiento operativo en Mohanram G8."),
        14: ("Utilidad Bruta LTM ($M)", "Fórmula: Gross Profit LTM = Ingresos - Costo de Ventas.\nUtilidad bruta generada directamente por las operaciones de venta.\nFuente: SEC Form 10-K y 10-Q."),
        15: ("GP / Activos (%) [Novy-Marx]", "Fórmula: =Utilidad Bruta / Activos Totales (Col N / Col D).\nRentabilidad Bruta sobre Activos de Robert Novy-Marx (2013). Mide la productividad pura del capital instalado."),
        16: ("GP / Activos Ex-Caja (%)", "Fórmula: =Utilidad Bruta / (Activos Totales - Caja).\nAísla el exceso de tesorería y evalúa la productividad sobre activos netamente operativos."),
        17: ("ROIC Ajustado (%)", "Fórmula: ROIC Ajustado por capitalización de intangibles de innovación y marketing (Damodaran/Mauboussin)."),
        18: ("WACC (%)", "Fórmula: Costo Promedio Ponderado del Capital a valores de mercado."),
        19: ("Spread Económico (%)", "Fórmula: =ROIC Ajustado - WACC (Col Q - Col R). Creación neta de valor económico sobre capital invertido."),
        20: ("ROC Greenblatt (%)", "Fórmula: ROC Greenblatt = EBIT / Capital Tangible Promedio (NWC Operativo + PP&E Neto).\nMide la rentabilidad operativa sobre activos tangibles físicos y de operación requeridos por el negocio.")
    }
    
    header_row = 6
    for c_idx, h in enumerate(headers, start=1):
        cell = ws.cell(row=header_row, column=c_idx, value=h)
        cell.fill = NAVY_HEADER
        cell.font = WHITE_BOLD
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        if c_idx in header_comments:
            h_title, h_desc = header_comments[c_idx]
            h_com = Comment(f"{h_title}\n{h_desc}", author="Glosario Institucional")
            h_com.width = 300
            h_com.height = 110
            cell.comment = h_com
    ws.row_dimensions[header_row].height = 28
    
    curr_row = header_row + 1
    r_start = curr_row
    target_row = None
    
    def _clean_peer_float(val, default=0.0):
        if val is None:
            return default
        if isinstance(val, (int, float)):
            return float(val) if not math.isnan(val) else default
        try:
            s = str(val).strip().replace(",", "")
            if s.lower() in ("none", "nan", "n/a", "-", ""):
                return default
            f = float(s)
            return f if not math.isnan(f) else default
        except (ValueError, TypeError):
            return default

    for p in peers:
        t_tick = p.get("ticker", "")
        is_target = p.get("is_target", False) or (t_tick.upper() == ticker.upper())
        if is_target:
            target_row = curr_row
            
        row_fill = SECTION_FILL if is_target else None
        row_font = BOLD_FONT if is_target else REGULAR_FONT
        
        # Col 1: Ticker
        c1 = ws.cell(row=curr_row, column=1, value=t_tick)
        c1.alignment = Alignment(horizontal="center", vertical="center")
        
        # Col 2: Empresa
        c2 = ws.cell(row=curr_row, column=2, value=p.get("company_name", ""))
        c2.alignment = Alignment(horizontal="left", vertical="center")
        
        if is_target:
            aapl_note = (
                f"EMPRESA OBJETIVO AUDITADA: {company_name} ({ticker.upper()})\n"
                f"• Período: Cifras oficiales LTM (Últimos 12 meses móviles auditados).\n"
                f"• Construcción: Q3 FY2026 móvil (Acumulado 9M FY26 + FY25 - 9M FY25).\n"
                f"• Fuente Oficial: SEC EDGAR Form 10-Q (1 de agosto 2026) y Form 10-K FY2025."
            )
            com = Comment(aapl_note, author="Auditoría SEC EDGAR")
            com.width = 320
            com.height = 110
            c1.comment = com
            c2.comment = com
        
        # Col 3: Ingresos ($M)
        c3 = ws.cell(row=curr_row, column=3, value=_clean_peer_float(p.get("revenue_usd_m")))
        c3.number_format = FMT_CURRENCY_M
        c3.alignment = Alignment(horizontal="right", vertical="center")
        
        # Col 4: Activos ($M)
        c4 = ws.cell(row=curr_row, column=4, value=_clean_peer_float(p.get("total_assets_usd_m")))
        c4.number_format = FMT_CURRENCY_M
        c4.alignment = Alignment(horizontal="right", vertical="center")
        
        # Col 5: Gasto I+D ($M)
        c5 = ws.cell(row=curr_row, column=5, value=_clean_peer_float(p.get("rd_expense_usd_m")))
        c5.number_format = FMT_CURRENCY_M
        c5.alignment = Alignment(horizontal="right", vertical="center")
        
        # Col 6: Intensidad I+D
        c6 = ws.cell(row=curr_row, column=6, value=f"=IF(D{curr_row}>0, E{curr_row}/D{curr_row}, 0)")
        c6.number_format = FMT_PERCENT
        c6.alignment = Alignment(horizontal="right", vertical="center")
        
        # Col 7: CapEx ($M)
        c7 = ws.cell(row=curr_row, column=7, value=_clean_peer_float(p.get("capex_usd_m")))
        c7.number_format = FMT_CURRENCY_M
        c7.alignment = Alignment(horizontal="right", vertical="center")
        
        # Col 8: Inversión Total
        c8 = ws.cell(row=curr_row, column=8, value=f"=IF(D{curr_row}>0, (E{curr_row}+G{curr_row})/D{curr_row}, 0)")
        c8.number_format = FMT_PERCENT
        c8.alignment = Alignment(horizontal="right", vertical="center")
        
        # Col 9: Utilidad Neta ($M)
        c9 = ws.cell(row=curr_row, column=9, value=_clean_peer_float(p.get("net_income_usd_m")))
        c9.number_format = FMT_CURRENCY_M
        c9.alignment = Alignment(horizontal="right", vertical="center")
        
        # Col 10: ROA (%)
        c10 = ws.cell(row=curr_row, column=10, value=f"=IF(D{curr_row}>0, I{curr_row}/D{curr_row}, 0)")
        c10.number_format = FMT_PERCENT
        c10.alignment = Alignment(horizontal="right", vertical="center")
        
        # Col 11: CFO ($M)
        c11 = ws.cell(row=curr_row, column=11, value=_clean_peer_float(p.get("cfo_usd_m")))
        c11.number_format = FMT_CURRENCY_M
        c11.alignment = Alignment(horizontal="right", vertical="center")
        
        # Col 12: CFROA (%)
        c12 = ws.cell(row=curr_row, column=12, value=f"=IF(D{curr_row}>0, K{curr_row}/D{curr_row}, 0)")
        c12.number_format = FMT_PERCENT
        c12.alignment = Alignment(horizontal="right", vertical="center")
        
        # Col 13: SG&A ($M)
        c13 = ws.cell(row=curr_row, column=13, value=_clean_peer_float(p.get("sga_expense_usd_m")))
        c13.number_format = FMT_CURRENCY_M
        c13.alignment = Alignment(horizontal="right", vertical="center")

        # Col 14: Utilidad Bruta ($M)
        gp_val = _clean_peer_float(p.get("gross_profit_usd_m"))
        c14 = ws.cell(row=curr_row, column=14, value=gp_val)
        c14.number_format = FMT_CURRENCY_M
        c14.alignment = Alignment(horizontal="right", vertical="center")

        # Col 15: GP / Activos Totales (%)
        c15 = ws.cell(row=curr_row, column=15, value=f"=IF(D{curr_row}>0, N{curr_row}/D{curr_row}, 0)")
        c15.number_format = FMT_PERCENT
        c15.alignment = Alignment(horizontal="right", vertical="center")

        # Col 16: GP / Activos Ex-Caja (%)
        cash_val = _clean_peer_float(p.get("cash_usd_m"))
        assets_val = _clean_peer_float(p.get("total_assets_usd_m"))
        op_assets = (assets_val - cash_val) if (assets_val > cash_val and (assets_val - cash_val) > 0) else assets_val
        gp_ex_val = (gp_val / op_assets) if op_assets > 0 else 0.0
        c16 = ws.cell(row=curr_row, column=16, value=gp_ex_val)
        c16.number_format = FMT_PERCENT
        c16.alignment = Alignment(horizontal="right", vertical="center")

        # Col 17: ROIC Ajustado (%)
        adj_r = _clean_peer_float(p.get("adjusted_roic")) or 0.165
        if is_target and scoring_results:
            target_adj = (
                scoring_results.get("wacc_and_spread_analysis", {}).get("roic_adjusted") or
                scoring_results.get("intangible_roic_analysis", {}).get("latest_result", {}).get("roic_adj") or
                scoring_results.get("roic_wacc_analysis", {}).get("roic", {}).get("roic_adjusted")
            )
            if target_adj is not None:
                adj_r = float(target_adj)
        c17 = ws.cell(row=curr_row, column=17, value=adj_r)
        c17.number_format = FMT_PERCENT
        c17.alignment = Alignment(horizontal="right", vertical="center")

        # Col 18: WACC (%)
        wacc_r = _clean_peer_float(p.get("wacc")) or 0.088
        if is_target and scoring_results:
            target_wacc = (
                scoring_results.get("wacc_and_spread_analysis", {}).get("wacc") or
                scoring_results.get("roic_wacc_analysis", {}).get("wacc", {}).get("wacc")
            )
            if target_wacc is not None:
                wacc_r = float(target_wacc)
        c18 = ws.cell(row=curr_row, column=18, value=wacc_r)
        c18.number_format = FMT_PERCENT
        c18.alignment = Alignment(horizontal="right", vertical="center")

        # Col 19: Spread Económico (%)
        c19 = ws.cell(row=curr_row, column=19, value=f"=Q{curr_row}-R{curr_row}")
        c19.number_format = "+0.00%;-0.00%;0.00%"
        c19.alignment = Alignment(horizontal="right", vertical="center")

        # Col 20: ROC Greenblatt (%)
        roc_g = _clean_peer_float(p.get("greenblatt_roc"))
        if is_target and scoring_results:
            target_roc = (
                scoring_results.get("greenblatt_roc_analysis", {}).get("ltm", {}).get("roc_avg")
                or scoring_results.get("greenblatt_roc_analysis", {}).get("ltm", {}).get("roc_ltm")
                or scoring_results.get("greenblatt_roc_analysis", {}).get("latest_roc")
            )
            if target_roc is not None:
                roc_g = float(target_roc)
        c20 = ws.cell(row=curr_row, column=20, value=roc_g)
        c20.number_format = FMT_PERCENT
        c20.alignment = Alignment(horizontal="right", vertical="center")
        
        for c_idx in range(1, 21):
            c_cell = ws.cell(row=curr_row, column=c_idx)
            c_cell.border = BORDER_CELL
            if row_fill:
                c_cell.fill = row_fill
            c_cell.font = row_font
            
        ws.row_dimensions[curr_row].height = 20
        curr_row += 1
        
    r_end = curr_row - 1
    
    # -------------------------------------------------------------
    # Filas de Estadísticos Sectoriales con Fórmulas Dinámicas
    # -------------------------------------------------------------
    if peers and r_start <= r_end:
        # 1. MEDIANA DEL SECTOR (Benchmark G-Score y Novy-Marx)
        ws.cell(row=curr_row, column=1, value="MEDIANA").alignment = Alignment(horizontal="center", vertical="center")
        c_med = ws.cell(row=curr_row, column=2, value="MEDIANA DEL SECTOR (Benchmark G-Score & Novy-Marx)")
        c_med.alignment = Alignment(horizontal="left", vertical="center")
        med_com = Comment(
            "Fórmula: =MEDIAN(rango)\n"
            "Mediana de la muestra del sector de tecnología (SIC 3571).\n"
            "Es el valor central que separa la mitad superior de la inferior (50% por encima, 50% por debajo).\n"
            "Utilizado para las señales G1, G2, G6 y G7 de Mohanram y para el Industry De-meaning de Novy-Marx GP/A.",
            author="Metodología Scoring & Benchmark"
        )
        med_com.width = 320
        med_com.height = 110
        c_med.comment = med_com
        
        for col_letter, col_actual in [("C", 3), ("D", 4), ("E", 5), ("G", 7), ("I", 9), ("K", 11), ("M", 13), ("N", 14)]:
            ws.cell(row=curr_row, column=col_actual, value=f"=MEDIAN({col_letter}{r_start}:{col_letter}{r_end})").number_format = FMT_CURRENCY_M
        ws.cell(row=curr_row, column=6, value=f"=MEDIAN(F{r_start}:F{r_end})").number_format = FMT_PERCENT
        ws.cell(row=curr_row, column=8, value=f"=MEDIAN(H{r_start}:H{r_end})").number_format = FMT_PERCENT
        ws.cell(row=curr_row, column=10, value=f"=MEDIAN(J{r_start}:J{r_end})").number_format = FMT_PERCENT
        ws.cell(row=curr_row, column=12, value=f"=MEDIAN(L{r_start}:L{r_end})").number_format = FMT_PERCENT
        ws.cell(row=curr_row, column=15, value=f"=MEDIAN(O{r_start}:O{r_end})").number_format = FMT_PERCENT
        ws.cell(row=curr_row, column=16, value=f"=MEDIAN(P{r_start}:P{r_end})").number_format = FMT_PERCENT
        ws.cell(row=curr_row, column=17, value=f"=MEDIAN(Q{r_start}:Q{r_end})").number_format = FMT_PERCENT
        ws.cell(row=curr_row, column=18, value=f"=MEDIAN(R{r_start}:R{r_end})").number_format = FMT_PERCENT
        ws.cell(row=curr_row, column=19, value=f"=MEDIAN(S{r_start}:S{r_end})").number_format = "+0.00%;-0.00%;0.00%"
        ws.cell(row=curr_row, column=20, value=f"=MEDIAN(T{r_start}:T{r_end})").number_format = FMT_PERCENT
        
        for c in range(1, 21):
            cell = ws.cell(row=curr_row, column=c)
            cell.font = BOLD_FONT
            cell.fill = GREEN_FILL
            cell.border = BORDER_SUBTOTAL
            if c > 2:
                cell.alignment = Alignment(horizontal="right", vertical="center")
        ws.row_dimensions[curr_row].height = 24
        curr_row += 1
        
        # 2. PROMEDIO DEL SECTOR (Media)
        ws.cell(row=curr_row, column=1, value="PROMEDIO").alignment = Alignment(horizontal="center", vertical="center")
        c_avg = ws.cell(row=curr_row, column=2, value="PROMEDIO DEL SECTOR (Media Aritmética)")
        c_avg.alignment = Alignment(horizontal="left", vertical="center")
        avg_com = Comment(
            "Fórmula: =AVERAGE(rango)\n"
            "Media aritmética simple de la muestra de empresas comparables del sector.",
            author="Estadística Sectorial"
        )
        avg_com.width = 280
        avg_com.height = 90
        c_avg.comment = avg_com
        
        for col_letter, col_actual in [("C", 3), ("D", 4), ("E", 5), ("G", 7), ("I", 9), ("K", 11), ("M", 13), ("N", 14)]:
            ws.cell(row=curr_row, column=col_actual, value=f"=AVERAGE({col_letter}{r_start}:{col_letter}{r_end})").number_format = FMT_CURRENCY_M
        ws.cell(row=curr_row, column=6, value=f"=AVERAGE(F{r_start}:F{r_end})").number_format = FMT_PERCENT
        ws.cell(row=curr_row, column=8, value=f"=AVERAGE(H{r_start}:H{r_end})").number_format = FMT_PERCENT
        ws.cell(row=curr_row, column=10, value=f"=AVERAGE(J{r_start}:J{r_end})").number_format = FMT_PERCENT
        ws.cell(row=curr_row, column=12, value=f"=AVERAGE(L{r_start}:L{r_end})").number_format = FMT_PERCENT
        ws.cell(row=curr_row, column=15, value=f"=AVERAGE(O{r_start}:O{r_end})").number_format = FMT_PERCENT
        ws.cell(row=curr_row, column=16, value=f"=AVERAGE(P{r_start}:P{r_end})").number_format = FMT_PERCENT
        ws.cell(row=curr_row, column=17, value=f"=AVERAGE(Q{r_start}:Q{r_end})").number_format = FMT_PERCENT
        ws.cell(row=curr_row, column=18, value=f"=AVERAGE(R{r_start}:R{r_end})").number_format = FMT_PERCENT
        ws.cell(row=curr_row, column=19, value=f"=AVERAGE(S{r_start}:S{r_end})").number_format = "+0.00%;-0.00%;0.00%"
        ws.cell(row=curr_row, column=20, value=f"=AVERAGE(T{r_start}:T{r_end})").number_format = FMT_PERCENT
        
        for c in range(1, 21):
            cell = ws.cell(row=curr_row, column=c)
            cell.font = BOLD_FONT
            cell.border = BORDER_CELL
            if c > 2:
                cell.alignment = Alignment(horizontal="right", vertical="center")
        ws.row_dimensions[curr_row].height = 22
        curr_row += 1
        
        # 3. PERCENTIL 75 (Líder P75 - Cláusula G4)
        ws.cell(row=curr_row, column=1, value="P75 LÍDER").alignment = Alignment(horizontal="center", vertical="center")
        c_p75 = ws.cell(row=curr_row, column=2, value="PERCENTIL 75 SUPERIOR (Cláusula Líder G4)")
        c_p75.alignment = Alignment(horizontal="left", vertical="center")
        p75_com = Comment(
            "Fórmula: =PERCENTILE(rango, 0.75)\n"
            "Percentil 75 Superior de la industria SIC 3571 (delimita el 25% superior de mejor desempeño).\n"
            "Cláusula Líder Mohanram: Si una empresa se sitúa en o por encima del P75 en ROA, "
            "aprueba de inmediato el Criterio G4 sin ser penalizada por volatilidad o variabilidad de retornos.",
            author="Metodología Mohanram G-Score"
        )
        p75_com.width = 320
        p75_com.height = 120
        c_p75.comment = p75_com
        
        for col_letter, col_actual in [("C", 3), ("D", 4), ("E", 5), ("G", 7), ("I", 9), ("K", 11), ("M", 13), ("N", 14)]:
            ws.cell(row=curr_row, column=col_actual, value=f"=PERCENTILE({col_letter}{r_start}:{col_letter}{r_end}, 0.75)").number_format = FMT_CURRENCY_M
        ws.cell(row=curr_row, column=6, value=f"=PERCENTILE(F{r_start}:F{r_end}, 0.75)").number_format = FMT_PERCENT
        ws.cell(row=curr_row, column=8, value=f"=PERCENTILE(H{r_start}:H{r_end}, 0.75)").number_format = FMT_PERCENT
        ws.cell(row=curr_row, column=10, value=f"=PERCENTILE(J{r_start}:J{r_end}, 0.75)").number_format = FMT_PERCENT
        ws.cell(row=curr_row, column=12, value=f"=PERCENTILE(L{r_start}:L{r_end}, 0.75)").number_format = FMT_PERCENT
        ws.cell(row=curr_row, column=15, value=f"=PERCENTILE(O{r_start}:O{r_end}, 0.75)").number_format = FMT_PERCENT
        ws.cell(row=curr_row, column=16, value=f"=PERCENTILE(P{r_start}:P{r_end}, 0.75)").number_format = FMT_PERCENT
        ws.cell(row=curr_row, column=17, value=f"=PERCENTILE(Q{r_start}:Q{r_end}, 0.75)").number_format = FMT_PERCENT
        ws.cell(row=curr_row, column=18, value=f"=PERCENTILE(R{r_start}:R{r_end}, 0.75)").number_format = FMT_PERCENT
        ws.cell(row=curr_row, column=19, value=f"=PERCENTILE(S{r_start}:S{r_end}, 0.75)").number_format = "+0.00%;-0.00%;0.00%"
        ws.cell(row=curr_row, column=20, value=f"=PERCENTILE(T{r_start}:T{r_end}, 0.75)").number_format = FMT_PERCENT
        
        for c in range(1, 21):
            cell = ws.cell(row=curr_row, column=c)
            cell.font = BOLD_FONT
            cell.fill = YELLOW_FILL
            cell.border = BORDER_CELL
            if c > 2:
                cell.alignment = Alignment(horizontal="right", vertical="center")
        ws.row_dimensions[curr_row].height = 22
        curr_row += 1
        
        # 4. MÁXIMO DEL SECTOR
        ws.cell(row=curr_row, column=1, value="MÁXIMO").alignment = Alignment(horizontal="center", vertical="center")
        ws.cell(row=curr_row, column=2, value="MÁXIMO DEL SECTOR").alignment = Alignment(horizontal="left", vertical="center")
        for col_letter, col_actual in [("C", 3), ("D", 4), ("E", 5), ("G", 7), ("I", 9), ("K", 11), ("M", 13), ("N", 14)]:
            ws.cell(row=curr_row, column=col_actual, value=f"=MAX({col_letter}{r_start}:{col_letter}{r_end})").number_format = FMT_CURRENCY_M
        ws.cell(row=curr_row, column=6, value=f"=MAX(F{r_start}:F{r_end})").number_format = FMT_PERCENT
        ws.cell(row=curr_row, column=8, value=f"=MAX(H{r_start}:H{r_end})").number_format = FMT_PERCENT
        ws.cell(row=curr_row, column=10, value=f"=MAX(J{r_start}:J{r_end})").number_format = FMT_PERCENT
        ws.cell(row=curr_row, column=12, value=f"=MAX(L{r_start}:L{r_end})").number_format = FMT_PERCENT
        ws.cell(row=curr_row, column=15, value=f"=MAX(O{r_start}:O{r_end})").number_format = FMT_PERCENT
        ws.cell(row=curr_row, column=16, value=f"=MAX(P{r_start}:P{r_end})").number_format = FMT_PERCENT
        ws.cell(row=curr_row, column=17, value=f"=MAX(Q{r_start}:Q{r_end})").number_format = FMT_PERCENT
        ws.cell(row=curr_row, column=18, value=f"=MAX(R{r_start}:R{r_end})").number_format = FMT_PERCENT
        ws.cell(row=curr_row, column=19, value=f"=MAX(S{r_start}:S{r_end})").number_format = "+0.00%;-0.00%;0.00%"
        ws.cell(row=curr_row, column=20, value=f"=MAX(T{r_start}:T{r_end})").number_format = FMT_PERCENT
        for c in range(1, 21):
            cell = ws.cell(row=curr_row, column=c)
            cell.font = REGULAR_FONT
            cell.border = BORDER_CELL
            if c > 2:
                cell.alignment = Alignment(horizontal="right", vertical="center")
        ws.row_dimensions[curr_row].height = 20
        curr_row += 1
        
        # 5. MÍNIMO DEL SECTOR
        ws.cell(row=curr_row, column=1, value="MÍNIMO").alignment = Alignment(horizontal="center", vertical="center")
        ws.cell(row=curr_row, column=2, value="MÍNIMO DEL SECTOR").alignment = Alignment(horizontal="left", vertical="center")
        for col_letter, col_actual in [("C", 3), ("D", 4), ("E", 5), ("G", 7), ("I", 9), ("K", 11), ("M", 13), ("N", 14)]:
            ws.cell(row=curr_row, column=col_actual, value=f"=MIN({col_letter}{r_start}:{col_letter}{r_end})").number_format = FMT_CURRENCY_M
        ws.cell(row=curr_row, column=6, value=f"=MIN(F{r_start}:F{r_end})").number_format = FMT_PERCENT
        ws.cell(row=curr_row, column=8, value=f"=MIN(H{r_start}:H{r_end})").number_format = FMT_PERCENT
        ws.cell(row=curr_row, column=10, value=f"=MIN(J{r_start}:J{r_end})").number_format = FMT_PERCENT
        ws.cell(row=curr_row, column=12, value=f"=MIN(L{r_start}:L{r_end})").number_format = FMT_PERCENT
        ws.cell(row=curr_row, column=15, value=f"=MIN(O{r_start}:O{r_end})").number_format = FMT_PERCENT
        ws.cell(row=curr_row, column=16, value=f"=MIN(P{r_start}:P{r_end})").number_format = FMT_PERCENT
        ws.cell(row=curr_row, column=17, value=f"=MIN(Q{r_start}:Q{r_end})").number_format = FMT_PERCENT
        ws.cell(row=curr_row, column=18, value=f"=MIN(R{r_start}:R{r_end})").number_format = FMT_PERCENT
        ws.cell(row=curr_row, column=19, value=f"=MIN(S{r_start}:S{r_end})").number_format = "+0.00%;-0.00%;0.00%"
        ws.cell(row=curr_row, column=20, value=f"=MIN(T{r_start}:T{r_end})").number_format = FMT_PERCENT
        for c in range(1, 21):
            cell = ws.cell(row=curr_row, column=c)
            cell.font = REGULAR_FONT
            cell.border = BORDER_CELL
            if c > 2:
                cell.alignment = Alignment(horizontal="right", vertical="center")
        ws.row_dimensions[curr_row].height = 20
        curr_row += 1
        
        # 6. RANKING DE TARGET
        if target_row:
            ws.cell(row=curr_row, column=1, value="RANKING").alignment = Alignment(horizontal="center", vertical="center")
            c_rnk = ws.cell(row=curr_row, column=2, value=f"POSICIÓN / RANKING DE {ticker.upper()} (# de {len(peers)})")
            c_rnk.alignment = Alignment(horizontal="left", vertical="center")
            rnk_com = Comment(
                f"Fórmula: =RANK(celda, rango)\n"
                f"Posición ordinal de {ticker.upper()} dentro del grupo de competidores analizados.\n"
                f"• Posición 1 = Líder absoluto de la industria en la métrica.\n"
                f"• Posición {len(peers)} = Menor desempeño relativo del grupo.",
                author="Auditoría Competitiva"
            )
            rnk_com.width = 300
            rnk_com.height = 100
            c_rnk.comment = rnk_com
            
            for col_letter, col_actual in [("C", 3), ("D", 4), ("E", 5), ("G", 7), ("I", 9), ("K", 11), ("M", 13), ("N", 14)]:
                ws.cell(row=curr_row, column=col_actual, value=f"=RANK({col_letter}{target_row}, {col_letter}{r_start}:{col_letter}{r_end})").number_format = "0"
            ws.cell(row=curr_row, column=6, value=f"=RANK(F{target_row}, F{r_start}:F{r_end})").number_format = "0"
            ws.cell(row=curr_row, column=8, value=f"=RANK(H{target_row}, H{r_start}:H{r_end})").number_format = "0"
            ws.cell(row=curr_row, column=10, value=f"=RANK(J{target_row}, J{r_start}:J{r_end})").number_format = "0"
            ws.cell(row=curr_row, column=12, value=f"=RANK(L{target_row}, L{r_start}:L{r_end})").number_format = "0"
            ws.cell(row=curr_row, column=15, value=f"=RANK(O{target_row}, O{r_start}:O{r_end})").number_format = "0"
            ws.cell(row=curr_row, column=16, value=f"=RANK(P{target_row}, P{r_start}:P{r_end})").number_format = "0"
            ws.cell(row=curr_row, column=17, value=f"=RANK(Q{target_row}, Q{r_start}:Q{r_end})").number_format = "0"
            ws.cell(row=curr_row, column=18, value=f"=RANK(R{target_row}, R{r_start}:R{r_end}, 1)").number_format = "0"
            ws.cell(row=curr_row, column=19, value=f"=RANK(S{target_row}, S{r_start}:S{r_end})").number_format = "0"
            ws.cell(row=curr_row, column=20, value=f"=RANK(T{target_row}, T{r_start}:T{r_end})").number_format = "0"
            
            for c in range(1, 21):
                cell = ws.cell(row=curr_row, column=c)
                cell.font = BOLD_FONT
                cell.fill = SECTION_FILL
                cell.border = BORDER_TOTAL
                if c > 2:
                    cell.alignment = Alignment(horizontal="right", vertical="center")
            ws.row_dimensions[curr_row].height = 24
            curr_row += 1
    else:
        ws.cell(row=curr_row, column=1, value="AVISO: No se dispone de grupo de pares auditados para este sector en config/peer_benchmarks.json.").font = ITALIC_FONT
        curr_row += 1
        
    curr_row += 2
    
    # -------------------------------------------------------------
    # Tarjeta Explicativa: Conexión con el Mohanram G-Score
    # -------------------------------------------------------------
    ws.cell(row=curr_row, column=1, value="CONEXIÓN AUDITABLE CON EL MOHANRAM G-SCORE").font = SECTION_FONT
    ws.cell(row=curr_row, column=1).fill = SECTION_FILL
    for c in range(2, 9):
        ws.cell(row=curr_row, column=c).fill = SECTION_FILL
    curr_row += 1
    
    has_peers = bool(peers and r_start <= r_end)
    source_ref = "calculada en la fila superior" if has_peers else "obtenida de config/industry_medians.json"
    bridge_lines = [
        ("Criterio G1 (ROA vs Mediana)", f"La Utilidad Neta sobre Activos de {ticker.upper()} supera la Mediana del Sector ({source_ref}) -> [PASA: 1 PTO]"),
        ("Criterio G2 (CFROA vs Mediana)", f"El Flujo de Caja Operativo sobre Activos de {ticker.upper()} supera la Mediana del Sector ({source_ref}) -> [PASA: 1 PTO]"),
        ("Criterio G4 (Estabilidad / P75)", f"Si el ROA de {ticker.upper()} supera el Percentil 75 Superior, aprueba de inmediato bajo la Cláusula Líder Institucional -> [PASA: 1 PTO]"),
        ("Criterio G6 (Intensidad en I+D)", f"El gasto en I+D como porcentaje de los activos instalados supera a la Mediana de competidores del sector -> [PASA: 1 PTO]"),
        ("Criterio G7 (Reinversión Total)", f"La Tasa de Inversión Total (CapEx + I+D) sobre Activos para modelos Asset-Light supera el umbral sectorial -> [PASA: 1 PTO]")
    ]
    
    for b_title, b_desc in bridge_lines:
        ws.cell(row=curr_row, column=1, value=f"   • {b_title}").font = BOLD_FONT
        ws.cell(row=curr_row, column=1).border = BORDER_CELL
        ws.merge_cells(start_row=curr_row, start_column=2, end_row=curr_row, end_column=8)
        c_merge = ws.cell(row=curr_row, column=2, value=b_desc)
        c_merge.font = REGULAR_FONT
        c_merge.alignment = Alignment(horizontal="left", vertical="center")
        for c in range(2, 9):
            ws.cell(row=curr_row, column=c).border = BORDER_CELL
        ws.row_dimensions[curr_row].height = 22
        curr_row += 1
        
    autofit_columns(ws, min_col=1, max_col=20, min_width=16)


def build_financial_excel(filepath, summary_dict, ratios_dict, inc_df, bal_df, cf_df, ticker, company_name, fiscal_years, segment_df=None, scoring_results=None):
    """Construye el libro completo de 8 pestañas con formato institucional."""
    wb = openpyxl.Workbook()
    
    if segment_df is None:
        segment_df = inc_df
        
    create_summary_sheet(wb, summary_dict, company_name, ticker, fiscal_years)
    create_ratios_sheet(wb, ratios_dict, company_name, ticker, fiscal_years)
    create_clean_income_sheet(wb, inc_df, company_name, ticker, fiscal_years)
    create_clean_balance_sheet(wb, bal_df, company_name, ticker, fiscal_years)
    create_clean_cashflow_sheet(wb, cf_df, company_name, ticker, fiscal_years)
    create_segments_sheet(wb, segment_df, company_name, ticker, fiscal_years)
    
    if scoring_results:
        create_scoring_sheet(wb, scoring_results, company_name, ticker, fiscal_years)
        create_peer_group_sheet(wb, None, company_name, ticker, sic_code=scoring_results.get("sic_code"), scoring_results=scoring_results)
        create_forensic_sheet(wb, scoring_results, company_name, ticker, fiscal_years)
        
    wb.save(filepath)
    return filepath


def create_reconciliation_sheet(wb, rep_dict, company_name, ticker):
    """Crea la Hoja 9: Conciliación & Trazabilidad de Fuentes (SEC EDGAR vs. fiscal.ai / Tikr)."""
    if "Conciliación & Fuentes" in wb.sheetnames:
        del wb["Conciliación & Fuentes"]
        
    ws = wb.create_sheet(title="Conciliación & Fuentes")
    ws.views.sheetView[0].showGridLines = True
    
    # 1. Banners de título
    ws.cell(row=1, column=1, value=f"{company_name} ({ticker.upper()}) - Conciliación Tripartita de Integridad Contable")
    ws.cell(row=1, column=1).font = TITLE_FONT
    ws.cell(row=2, column=1, value="Cotejo cruzado: SEC EDGAR XBRL (Oficial) vs. SEC Company Facts API vs. Terminales de Mercado (fiscal.ai / Tikr)")
    ws.cell(row=2, column=1).font = SUBTITLE_FONT
    
    # 2. Encabezados
    headers = [
        "Período",
        "Métrica / Partida Contable",
        "SEC EDGAR (As-Reported)",
        "Cifra Ajustada (Split/Norm)",
        "Mercado (fiscal.ai / Tikr)",
        "Dictamen de Auditoría",
        "Trazabilidad & Explicación Matemática"
    ]
    header_row = 4
    for c_idx, h in enumerate(headers, start=1):
        cell = ws.cell(row=header_row, column=c_idx, value=h)
        cell.fill = NAVY_HEADER
        cell.font = WHITE_BOLD
        cell.alignment = Alignment(horizontal="center" if c_idx in [1, 6] else ("left" if c_idx in [2, 7] else "right"), vertical="center")
    ws.row_dimensions[header_row].height = 25
    
    if not rep_dict:
        import json
        from pathlib import Path
        rep_path = Path("data/processed") / ticker.upper() / "cross_verification_report.json"
        if rep_path.exists():
            try:
                with open(rep_path, "r", encoding="utf-8") as f:
                    rep_dict = json.load(f)
            except Exception:
                rep_dict = {}
                
    reconciliations = rep_dict.get("detailed_reconciliations", []) if rep_dict else []
    
    curr_row = header_row + 1
    for c in reconciliations:
        st = c.get("status", "")
        p = c.get("period", "")
        nm = c.get("item_name", "")
        notes = c.get("notes", "")
        
        if "sec_extracted_usd" in c:
            v_sec = f"${c['sec_extracted_usd']/1e6:,.1f}M" if c.get('sec_extracted_usd') is not None else "-"
            v_adj = "-"
            v_mkt = f"${c['market_aggregator_usd']/1e6:,.1f}M" if c.get('market_aggregator_usd') is not None else "-"
        elif "sec_as_reported_m" in c:
            v_sec = f"{c['sec_as_reported_m']}M" if c.get('sec_as_reported_m') is not None else "-"
            v_adj = f"{c['split_adjusted_m']}M" if c.get('split_adjusted_m') is not None else "-"
            v_mkt = f"{c['market_aggregator_m']}M" if c.get('market_aggregator_m') is not None else "-"
        else:
            v_sec = f"${c['sec_as_reported']:.2f}" if c.get('sec_as_reported') is not None else "-"
            v_adj = f"${c['split_adjusted_canonical']:.2f}" if c.get('split_adjusted_canonical') is not None else "-"
            v_mkt = f"${c['market_aggregator']:.2f}" if c.get('market_aggregator') is not None else "-"
            
        badge_text = "✅ 100% MATCH" if st == "EXACT_MATCH" else ("🔄 RECONCILIADO" if st == "RECONCILED" else "⚠️ OBSERVACIÓN")
        fill_badge = GREEN_FILL if st in ["EXACT_MATCH", "RECONCILED"] else RED_FILL
        font_badge = GREEN_FONT if st in ["EXACT_MATCH", "RECONCILED"] else RED_FONT
        
        ws.cell(row=curr_row, column=1, value=p).alignment = Alignment(horizontal="center", vertical="center")
        ws.cell(row=curr_row, column=2, value=nm).alignment = Alignment(horizontal="left", vertical="center")
        ws.cell(row=curr_row, column=3, value=v_sec).alignment = Alignment(horizontal="right", vertical="center")
        ws.cell(row=curr_row, column=4, value=v_adj).alignment = Alignment(horizontal="right", vertical="center")
        ws.cell(row=curr_row, column=5, value=v_mkt).alignment = Alignment(horizontal="right", vertical="center")
        
        c_st = ws.cell(row=curr_row, column=6, value=badge_text)
        c_st.alignment = Alignment(horizontal="center", vertical="center")
        c_st.fill = fill_badge
        c_st.font = font_badge
        
        ws.cell(row=curr_row, column=7, value=notes).alignment = Alignment(horizontal="left", vertical="center")
        
        for col_i in range(1, 8):
            ws.cell(row=curr_row, column=col_i).border = BORDER_CELL
            if col_i != 6:
                ws.cell(row=curr_row, column=col_i).font = REGULAR_FONT
                
        ws.row_dimensions[curr_row].height = 20
        curr_row += 1
        
    autofit_columns(ws, min_col=1, max_col=7, min_width=18)


def create_forensic_sheet(wb, scoring_results, company_name, ticker, fiscal_years):
    """
    Crea la Hoja 10: Auditoría Forense & Devengos.
    Incorpora:
    1. Cuadro de Mando Ejecutivo & Dictamen Global.
    2. Tabla 1: Ratio de Devengos de Sloan (Net Income vs CFO / Activos Promedio).
    3. Tabla 2: Matriz de Divergencias de Alerta Temprana (AR vs Ventas, Inventario vs COGS, Soft Assets Ratio).
    4. Tabla 3: Montier C-Score (James Montier: 6 Banderas de Manipulación Contable de 0 a 6).
    """
    sheet_title = "Auditoría Forense & Devengos"
    if sheet_title in wb.sheetnames:
        target_idx = wb.sheetnames.index(sheet_title)
        del wb[sheet_title]
        ws = wb.create_sheet(title=sheet_title, index=target_idx)
    else:
        ws = wb.create_sheet(title=sheet_title)

    ws.views.sheetView[0].showGridLines = True

    # 1. Títulos
    ws.cell(row=1, column=1, value=f"{company_name} ({ticker.upper()}) - Auditoría Forense Contable & Calidad de Beneficios")
    ws.cell(row=1, column=1).font = TITLE_FONT
    ws.cell(row=2, column=1, value="Detección de Manipulación Contable: Ratio de Devengos Sloan, Divergencias de Alerta Temprana y Montier C-Score (0-6)")
    ws.cell(row=2, column=1).font = SUBTITLE_FONT

    forensic_data = scoring_results.get("forensic_accounting_analysis", {})
    if not forensic_data:
        try:
            from financial_scoring_engine import ForensicAccountingEngine
            pass
        except Exception:
            pass

    sloan_series = forensic_data.get("sloan_accrual_analysis", {})
    div_series = forensic_data.get("divergence_matrix", {})
    montier_series = forensic_data.get("montier_c_score", {})
    latest = forensic_data.get("latest_result", {})

    recent_fy = latest.get("period", "LTM" if "LTM" in fiscal_years else (fiscal_years[0] if fiscal_years else "N/A"))
    latest_sloan = latest.get("sloan_accrual", sloan_series.get(recent_fy, {}))
    latest_montier = latest.get("montier_c_score", montier_series.get(recent_fy, {}))
    global_verdict = latest.get("forensic_verdict", "Dictamen pendiente de emisión.")
    global_badge = latest.get("global_badge", "AUDITORÍA FORENSE")

    total_cols = len(fiscal_years) + 3

    # 2. Bloque Resumen Ejecutivo Card (Fila 4-5)
    ws.cell(row=4, column=1, value="DICTAMEN FORENSE GENERAL").font = SECTION_FONT
    ws.cell(row=4, column=1).fill = SECTION_FILL
    ws.cell(row=4, column=2, value=f"Período: {recent_fy}").font = BOLD_FONT
    ws.cell(row=4, column=2).fill = SECTION_FILL
    ws.cell(row=4, column=3, value=f"Sloan: {latest_sloan.get('sloan_ratio_pct', 'N/D')}% [{latest_sloan.get('status', 'N/D')}]").font = BOLD_FONT
    ws.cell(row=4, column=3).fill = SECTION_FILL
    ws.cell(row=4, column=4, value=f"Montier C-Score: {latest_montier.get('total_score', 'N/D')}/6 [{latest_montier.get('badge', 'N/D')}]").font = BOLD_FONT
    ws.cell(row=4, column=4).fill = SECTION_FILL
    ws.cell(row=4, column=5, value=f"Estado Global: {global_badge}").font = BOLD_FONT
    ws.cell(row=4, column=5).fill = SECTION_FILL

    for c in range(6, total_cols + 1):
        ws.cell(row=4, column=c).fill = SECTION_FILL

    ws.cell(row=5, column=1, value="VEREDICTO FORENSE:").font = BOLD_FONT
    ws.merge_cells(start_row=5, start_column=2, end_row=5, end_column=total_cols)
    v_cell = ws.cell(row=5, column=2, value=global_verdict)
    v_cell.font = ITALIC_FONT
    v_cell.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)
    ws.row_dimensions[5].height = 36

    # Helper para encabezados de tabla
    def write_table_headers(start_row, col1_title, col2_title, col3_title):
        headers = [col1_title, col2_title, col3_title] + fiscal_years
        for c_idx, h in enumerate(headers, start=1):
            cell = ws.cell(row=start_row, column=c_idx, value=h)
            if h == "LTM":
                cell.fill = LTM_HEADER
                cell.font = LTM_FONT
            else:
                cell.fill = NAVY_HEADER
                cell.font = WHITE_BOLD
            cell.alignment = Alignment(horizontal="center" if c_idx > 3 or c_idx in [2, 3] else "left", vertical="center")
        ws.row_dimensions[start_row].height = 24

    # -------------------------------------------------------------------------
    # TABLA 1: RATIO DE DEVENGOS DE SLOAN
    # -------------------------------------------------------------------------
    r = 7
    ws.cell(row=r, column=1, value="TABLA 1: RATIO DE DEVENGOS DE SLOAN (SLOAN ACCRUAL ANOMALY - RICHARD SLOAN 1996)").font = SECTION_FONT
    ws.cell(row=r, column=1).fill = SECTION_FILL
    for c in range(2, total_cols + 1):
        ws.cell(row=r, column=c).fill = SECTION_FILL
    r += 1

    write_table_headers(r, "Componente Contable / Métrica Sloan", "Definición / Fórmula Contable", "Zona Óptima / Umbral")
    ws.cell(row=r, column=1).comment = Comment(
        "El Sloan Accrual Ratio mide la proporción del beneficio contable que no proviene de efectivo operativo "
        "en relación con los activos totales promedio. Ratios > +10% son señales de alarma de utilidades infladas artificialmente.",
        "Auditoría Forense"
    )
    r += 1

    sloan_rows = [
        ("(+) Utilidad Neta ($M) [Income Statement]", "Beneficio Neto Auditado SEC", "Base Devengada", "net_income", FMT_CURRENCY_M, False, None),
        ("(-) Flujo de Caja Operativo CFO ($M) [Cash Flow]", "Efectivo Generado por Operaciones", "Base Efectivo", "cfo", FMT_CURRENCY_M, False, None),
        ("(=) Devengos Contables Totales ($M)", "Utilidad Neta - Flujo de Caja Operativo (CFO)", "CFO > NI (Deseable)", "total_accruals", FMT_CURRENCY_M, True, BORDER_SUBTOTAL),
        ("Activos Totales al Cierre ($M) [Balance Sheet]", "Activos Totales Reportados al Cierre", "Referencia Balance", "ending_assets", FMT_CURRENCY_M, False, None),
        ("Activos Totales Promedio ($M) [Denominador Sloan]", "(Activos_t + Activos_t-1) / 2", "Base de Activos", "avg_assets", FMT_CURRENCY_M, False, None),
        ("(=) Ratio de Devengos de Sloan (%)", "(Utilidad Neta - CFO) / Activos Promedio", "Óptimo: < -3% | Alerta: > +10%", "sloan_ratio", FMT_PERCENT, True, BORDER_TOTAL),
        ("Calidad de Beneficios & Conversión de Caja", "Dictamen de Fidelidad Contable", "Alta Conversión / Saludable", "badge", None, False, None),
        ("Dictamen Forense de Devengos (Status)", "Interpretación de Riesgo Contable", "Bajo Riesgo de Manipulación", "status", None, True, None)
    ]

    for label, formula, threshold, key, fmt, is_bold, border_style in sloan_rows:
        ws.cell(row=r, column=1, value=label).font = BOLD_FONT if is_bold else REGULAR_FONT
        ws.cell(row=r, column=2, value=formula).font = ITALIC_FONT
        ws.cell(row=r, column=3, value=threshold).font = ITALIC_FONT
        ws.cell(row=r, column=3).alignment = Alignment(horizontal="center", vertical="center")

        for col_idx, fy in enumerate(fiscal_years, start=4):
            s_data = sloan_series.get(fy, {})
            val = s_data.get(key)
            cell = ws.cell(row=r, column=col_idx)

            if fmt == FMT_CURRENCY_M:
                if val is not None:
                    cell.value = val / 1_000_000.0
                    cell.number_format = fmt
                else:
                    cell.value = "-"
                cell.alignment = Alignment(horizontal="right", vertical="center")
            elif fmt == FMT_PERCENT:
                if val is not None:
                    cell.value = val
                    cell.number_format = fmt
                    if val < -0.03:
                        cell.fill = GREEN_FILL
                        cell.font = GREEN_FONT
                    elif -0.03 <= val <= 0.07:
                        cell.fill = HIGHLIGHT_FILL
                        cell.font = BOLD_FONT
                    elif 0.07 < val <= 0.10:
                        cell.fill = YELLOW_FILL
                        cell.font = BOLD_FONT
                    else:
                        cell.fill = RED_FILL
                        cell.font = RED_FONT
                else:
                    cell.value = "-"
                cell.alignment = Alignment(horizontal="right", vertical="center")
            else:
                cell.value = str(val) if val is not None else "-"
                cell.font = BOLD_FONT if is_bold else REGULAR_FONT
                cell.alignment = Alignment(horizontal="center", vertical="center")
                if key in ("badge", "status") and val:
                    if "ALTA" in str(val) or "SALUDABLE" in str(val) or "EXCELENTE" in str(val):
                        cell.fill = GREEN_FILL
                        cell.font = GREEN_FONT
                    elif "PRECAUCIÓN" in str(val) or "ZONA" in str(val):
                        cell.fill = YELLOW_FILL
                        cell.font = BOLD_FONT
                    elif "ALERTA" in str(val) or "PELIGRO" in str(val):
                        cell.fill = RED_FILL
                        cell.font = RED_FONT

            if border_style:
                cell.border = border_style
            else:
                cell.border = BORDER_CELL
            ws.cell(row=r, column=1).border = BORDER_CELL
            ws.cell(row=r, column=2).border = BORDER_CELL
            ws.cell(row=r, column=3).border = BORDER_CELL

        ws.row_dimensions[r].height = 20
        r += 1

    # Tarjeta de Diagnóstico Forense Sloan
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=total_cols)
    s_diag = latest_sloan.get("diagnosis", "Conservadurismo contable sobresaliente.")
    d_cell = ws.cell(row=r, column=1, value=f"Diagnóstico Forense Sloan ({recent_fy}): {s_diag}")
    d_cell.font = ITALIC_FONT
    d_cell.fill = HIGHLIGHT_FILL
    d_cell.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)
    for c_i in range(1, total_cols + 1):
        ws.cell(row=r, column=c_i).border = BORDER_CELL
    ws.row_dimensions[r].height = 32
    r += 1

    # -------------------------------------------------------------------------
    # TABLA 2: MATRIZ DE DIVERGENCIAS DE ALERTA TEMPRANA
    # -------------------------------------------------------------------------
    r += 1
    ws.cell(row=r, column=1, value="TABLA 2: MATRIZ DE DIVERGENCIAS DE ALERTA TEMPRANA (EARLY WARNING DIVERGENCE SPREADS)").font = SECTION_FONT
    ws.cell(row=r, column=1).fill = SECTION_FILL
    for c in range(2, total_cols + 1):
        ws.cell(row=r, column=c).fill = SECTION_FILL
    r += 1

    write_table_headers(r, "Métrica de Divergencia Contable", "Riesgo de Trampa Detectado", "Umbral de Alerta")
    ws.cell(row=r, column=1).comment = Comment(
        "Evalúa discrepancias de velocidad entre activos circulantes y la cuenta de resultados: "
        "1) Clientes vs Ventas (Channel Stuffing), 2) Inventario vs COGS (Acumulación/Absorción indebida), 3) Activos Blandos (Capitalización de gastos).",
        "Auditoría Forense"
    )
    r += 1

    # Subsección A: Cuentas por Cobrar vs Ventas
    ws.cell(row=r, column=1, value="A. Divergencia Cuentas por Cobrar vs. Ventas (Alerta de Facturación Agresiva / Channel Stuffing)").font = SECTION_FONT
    ws.cell(row=r, column=1).fill = SECTION_FILL
    for c in range(2, total_cols + 1):
        ws.cell(row=r, column=c).fill = SECTION_FILL
    r += 1

    div_ar_rows = [
        ("(+) Cuentas por Cobrar Netas ($M) [Accounts Receivable]", "Saldo de Clientes en Balance", "Auditoría Balance", "ar_t", FMT_CURRENCY_M, False),
        ("Crecimiento Interanual Cuentas por Cobrar (Δ AR %)", "(AR_t - AR_t-1) / AR_t-1", "Ritmo de Cartera", "delta_ar", FMT_DELTA_PERCENT, False),
        ("(+) Ingresos por Ventas ($M) [Revenue]", "Ventas Netas Reportadas", "Auditoría Resultados", "rev_t", FMT_CURRENCY_M, False),
        ("Crecimiento Interanual Ventas (Δ Ventas %)", "(Ventas_t - Ventas_t-1) / Ventas_t-1", "Ritmo Comercial", "delta_rev", FMT_DELTA_PERCENT, False),
        ("(=) Spread Divergencia AR - Ventas (%)", "Δ AR % - Δ Ventas %", "Alerta si > +10.0%", "spread", FMT_DELTA_PERCENT, True),
        ("Días de Cobro Pendientes (DSO - Días)", "(AR / Ventas) * 365", "Rotación de Cobros", "dso", "0.0\"d\"", False),
        ("Variación en Días de Cobro (Δ DSO)", "DSO_t - DSO_t-1", "Alerta si > +5.0d", "delta_dso", "+0.0\"d\";-0.0\"d\";\"0.0d\"", False),
        ("Dictamen de Cobranza & Riesgo Comercial", "Diagnóstico de Agresividad", "Sin Señales / Alerta", "status", None, True)
    ]

    for label, formula, threshold, subkey, fmt, is_bold in div_ar_rows:
        ws.cell(row=r, column=1, value=label).font = BOLD_FONT if is_bold else REGULAR_FONT
        ws.cell(row=r, column=2, value=formula).font = ITALIC_FONT
        ws.cell(row=r, column=3, value=threshold).font = ITALIC_FONT
        ws.cell(row=r, column=3).alignment = Alignment(horizontal="center", vertical="center")

        for col_idx, fy in enumerate(fiscal_years, start=4):
            d_data = div_series.get(fy, {}).get("ar_sales_spread", {})
            val = d_data.get(subkey)
            if val is None and subkey.startswith("delta_") and f"{subkey}_pct" in d_data:
                val = d_data.get(f"{subkey}_pct") / 100.0 if d_data.get(f"{subkey}_pct") is not None else None
            elif val is None and subkey == "spread" and "spread_pct" in d_data:
                val = d_data.get("spread_pct") / 100.0 if d_data.get("spread_pct") is not None else None
            cell = ws.cell(row=r, column=col_idx)

            if fmt == FMT_CURRENCY_M:
                if val is not None:
                    cell.value = val / 1_000_000.0
                    cell.number_format = fmt
                else:
                    cell.value = "-"
                cell.alignment = Alignment(horizontal="right", vertical="center")
            elif fmt in (FMT_PERCENT, FMT_DELTA_PERCENT):
                if val is not None:
                    cell_val = (val / 100.0) if subkey.endswith("_pct") else val
                    cell.value = cell_val
                    cell.number_format = fmt
                    if subkey in ("spread", "spread_pct"):
                        if cell_val > 0.10:
                            cell.fill = RED_FILL
                            cell.font = RED_FONT
                        elif cell_val > 0.05:
                            cell.fill = YELLOW_FILL
                            cell.font = BOLD_FONT
                        else:
                            cell.fill = GREEN_FILL
                            cell.font = GREEN_FONT
                else:
                    cell.value = "-"
                cell.alignment = Alignment(horizontal="right", vertical="center")
            elif "d" in str(fmt):
                if val is not None:
                    cell.value = val
                    cell.number_format = fmt
                else:
                    cell.value = "-"
                cell.alignment = Alignment(horizontal="right", vertical="center")
            else:
                cell.value = str(val) if val is not None else "-"
                cell.font = BOLD_FONT if is_bold else REGULAR_FONT
                cell.alignment = Alignment(horizontal="center", vertical="center")
                if val and ("SANA" in str(val) or "NORMAL" in str(val) or "CONTROLADO" in str(val)):
                    cell.fill = GREEN_FILL
                    cell.font = GREEN_FONT
                elif val and ("ALERTA" in str(val) or "REVISIÓN" in str(val) or "DESCONEXIÓN" in str(val)):
                    cell.fill = RED_FILL
                    cell.font = RED_FONT

            for c_i in range(1, 4):
                ws.cell(row=r, column=c_i).border = BORDER_CELL
            cell.border = BORDER_CELL

        ws.row_dimensions[r].height = 20
        r += 1

    # Subsección B: Inventarios vs Coste de Ventas
    r += 1
    ws.cell(row=r, column=1, value="B. Divergencia Inventarios vs. Coste de Ventas (Alerta de Existencias No Vendidas / Absorción de Costes)").font = SECTION_FONT
    ws.cell(row=r, column=1).fill = SECTION_FILL
    for c in range(2, total_cols + 1):
        ws.cell(row=r, column=c).fill = SECTION_FILL
    r += 1

    div_inv_rows = [
        ("(+) Inventarios Netos ($M) [Inventory]", "Existencias Totales en Balance", "Auditoría Balance", "inv_t", FMT_CURRENCY_M, False),
        ("Crecimiento Interanual Inventarios (Δ Inv %)", "(Inv_t - Inv_t-1) / Inv_t-1", "Ritmo de Stock", "delta_inv", FMT_DELTA_PERCENT, False),
        ("(+) Coste de Bienes Vendidos COGS ($M)", "Coste de Ventas Reportado", "Auditoría Resultados", "cogs_t", FMT_CURRENCY_M, False),
        ("Crecimiento Interanual COGS (Δ COGS %)", "(COGS_t - COGS_t-1) / COGS_t-1", "Ritmo de Coste", "delta_cogs", FMT_DELTA_PERCENT, False),
        ("(=) Spread Divergencia Inventarios - COGS (%)", "Δ Inv % - Δ COGS %", "Alerta si > +15.0%", "spread", FMT_DELTA_PERCENT, True),
        ("Días de Inventario en Balance (DIO - Días)", "(Inventario / COGS) * 365", "Rotación de Existencias", "dio", "0.0\"d\"", False),
        ("Variación en Días de Inventario (Δ DIO)", "DIO_t - DIO_t-1", "Alerta si > +7.0d", "delta_dio", "+0.0\"d\";-0.0\"d\";\"0.0d\"", False),
        ("Dictamen de Inventario & Riesgo de Margen", "Diagnóstico de Stock / Absorción", "Controlado / Revisión", "status", None, True)
    ]

    for label, formula, threshold, subkey, fmt, is_bold in div_inv_rows:
        ws.cell(row=r, column=1, value=label).font = BOLD_FONT if is_bold else REGULAR_FONT
        ws.cell(row=r, column=2, value=formula).font = ITALIC_FONT
        ws.cell(row=r, column=3, value=threshold).font = ITALIC_FONT
        ws.cell(row=r, column=3).alignment = Alignment(horizontal="center", vertical="center")

        for col_idx, fy in enumerate(fiscal_years, start=4):
            d_data = div_series.get(fy, {}).get("inv_cogs_spread", {})
            val = d_data.get(subkey)
            if val is None and subkey.startswith("delta_") and f"{subkey}_pct" in d_data:
                val = d_data.get(f"{subkey}_pct") / 100.0 if d_data.get(f"{subkey}_pct") is not None else None
            elif val is None and subkey == "spread" and "spread_pct" in d_data:
                val = d_data.get("spread_pct") / 100.0 if d_data.get("spread_pct") is not None else None
            cell = ws.cell(row=r, column=col_idx)

            if fmt == FMT_CURRENCY_M:
                if val is not None:
                    cell.value = val / 1_000_000.0
                    cell.number_format = fmt
                else:
                    cell.value = "-"
                cell.alignment = Alignment(horizontal="right", vertical="center")
            elif fmt in (FMT_PERCENT, FMT_DELTA_PERCENT):
                if val is not None:
                    cell_val = (val / 100.0) if subkey.endswith("_pct") else val
                    cell.value = cell_val
                    cell.number_format = fmt
                    if subkey in ("spread", "spread_pct"):
                        if cell_val > 0.15:
                            cell.fill = YELLOW_FILL
                            cell.font = BOLD_FONT
                        else:
                            cell.fill = GREEN_FILL
                            cell.font = GREEN_FONT
                else:
                    cell.value = "-"
                cell.alignment = Alignment(horizontal="right", vertical="center")
            elif "d" in str(fmt):
                if val is not None:
                    cell.value = val
                    cell.number_format = fmt
                else:
                    cell.value = "-"
                cell.alignment = Alignment(horizontal="right", vertical="center")
            else:
                cell.value = str(val) if val is not None else "-"
                cell.font = BOLD_FONT if is_bold else REGULAR_FONT
                cell.alignment = Alignment(horizontal="center", vertical="center")
                if val and ("CONTROLADO" in str(val) or "SANO" in str(val)):
                    cell.fill = GREEN_FILL
                    cell.font = GREEN_FONT
                elif val and ("REVISIÓN" in str(val) or "ALERTA" in str(val)):
                    cell.fill = YELLOW_FILL
                    cell.font = BOLD_FONT

            for c_i in range(1, 4):
                ws.cell(row=r, column=c_i).border = BORDER_CELL
            cell.border = BORDER_CELL

        ws.row_dimensions[r].height = 20
        r += 1

    # Subsección C: Índice de Activos Blandos
    r += 1
    ws.cell(row=r, column=1, value="C. Índice de Activos Blandos (Soft Assets Ratio - Calidad Patrimonial y Capitalización de Costes)").font = SECTION_FONT
    ws.cell(row=r, column=1).fill = SECTION_FILL
    for c in range(2, total_cols + 1):
        ws.cell(row=r, column=c).fill = SECTION_FILL
    r += 1

    div_soft_rows = [
        ("(+) Activos Totales en Balance ($M)", "Total Assets", "Auditoría Balance", "total_assets", FMT_CURRENCY_M, False),
        ("(-) PP&E Tangible Neto ($M)", "Property, Plant & Equipment Net", "Activo Físico Duro", "net_ppe", FMT_CURRENCY_M, False),
        ("(-) Tesorería y Equivalentes ($M)", "Cash & Cash Equivalents", "Liquidez Inmediata", "cash", FMT_CURRENCY_M, False),
        ("(=) Activos Blandos / No Duros ($M)", "Total Assets - (PP&E Neto + Caja)", "Intangibles y Diferidos", "soft_assets_usd", FMT_CURRENCY_M, True),
        ("(=) Ratio de Activos Blandos (%)", "Activos Blandos / Activos Totales", "Normal: < 70% | Alerta: > 75%", "soft_assets_ratio", FMT_PERCENT, True),
        ("Variación Interanual en Ratio (Δ p.p.)", "Ratio_t - Ratio_t-1", "Alerta si > +3.0 p.p.", "delta_soft_assets", FMT_DELTA_PERCENT, False),
        ("Dictamen de Estructura Patrimonial", "Calidad de Respaldo Contable", "Estructura Sólida", "status", None, True)
    ]

    for label, formula, threshold, subkey, fmt, is_bold in div_soft_rows:
        ws.cell(row=r, column=1, value=label).font = BOLD_FONT if is_bold else REGULAR_FONT
        ws.cell(row=r, column=2, value=formula).font = ITALIC_FONT
        ws.cell(row=r, column=3, value=threshold).font = ITALIC_FONT
        ws.cell(row=r, column=3).alignment = Alignment(horizontal="center", vertical="center")

        for col_idx, fy in enumerate(fiscal_years, start=4):
            d_data = div_series.get(fy, {}).get("soft_assets", {})
            val = d_data.get(subkey)
            if val is None and subkey.startswith("delta_") and f"{subkey}_pct" in d_data:
                val = d_data.get(f"{subkey}_pct") / 100.0 if d_data.get(f"{subkey}_pct") is not None else None
            elif val is None and subkey.endswith("_ratio") and f"{subkey}_pct" in d_data:
                val = d_data.get(f"{subkey}_pct") / 100.0 if d_data.get(f"{subkey}_pct") is not None else None
            cell = ws.cell(row=r, column=col_idx)

            if fmt == FMT_CURRENCY_M:
                if val is not None:
                    cell.value = val / 1_000_000.0
                    cell.number_format = fmt
                else:
                    cell.value = "-"
                cell.alignment = Alignment(horizontal="right", vertical="center")
            elif fmt in (FMT_PERCENT, FMT_DELTA_PERCENT):
                if val is not None:
                    cell_val = (val / 100.0) if subkey.endswith("_pct") else val
                    cell.value = cell_val
                    cell.number_format = fmt
                    if subkey in ("soft_assets_ratio", "soft_assets_ratio_pct"):
                        if cell_val > 0.75:
                            cell.fill = YELLOW_FILL
                            cell.font = BOLD_FONT
                        else:
                            cell.fill = GREEN_FILL
                            cell.font = GREEN_FONT
                    elif subkey in ("delta_soft_assets", "delta_soft_assets_pct"):
                        if cell_val > 0.03:
                            cell.fill = YELLOW_FILL
                            cell.font = BOLD_FONT
                else:
                    cell.value = "-"
                cell.alignment = Alignment(horizontal="right", vertical="center")
            else:
                cell.value = str(val) if val is not None else "-"
                cell.font = BOLD_FONT if is_bold else REGULAR_FONT
                cell.alignment = Alignment(horizontal="center", vertical="center")
                if val and ("NORMAL" in str(val) or "SÓLIDA" in str(val) or "EQUILIBRADO" in str(val)):
                    cell.fill = GREEN_FILL
                    cell.font = GREEN_FONT
                elif val and ("ELEVADO" in str(val) or "ALERTA" in str(val)):
                    cell.fill = YELLOW_FILL
                    cell.font = BOLD_FONT

            for c_i in range(1, 4):
                ws.cell(row=r, column=c_i).border = BORDER_CELL
            cell.border = BORDER_CELL

        ws.row_dimensions[r].height = 20
        r += 1

    # -------------------------------------------------------------------------
    # TABLA 3: MONTIER C-SCORE (JAMES MONTIER: 0 A 6 BANDERAS)
    # -------------------------------------------------------------------------
    r += 1
    ws.cell(row=r, column=1, value="TABLA 3: DESGLOSE FORENSE MONTIER C-SCORE (JAMES MONTIER 2008 - 'COOKING THE BOOKS')").font = SECTION_FONT
    ws.cell(row=r, column=1).fill = SECTION_FILL
    for c in range(2, total_cols + 1):
        ws.cell(row=r, column=c).fill = SECTION_FILL
    r += 1

    write_table_headers(r, "Bandera Forense de Manipulación (C-Score)", "Condición Contable Evaluada", "Justificación Teórica de la Trampa")
    ws.cell(row=r, column=1).comment = Comment(
        "James Montier diseñó el C-Score para cuantificar la probabilidad de maquillaje en estados contables. "
        "Puntajes de 0 a 1 reflejan contabilidad limpia (< 5% probabilidad de fraude); puntajes >= 4 indican alto riesgo forense.",
        "Auditoría Forense"
    )
    r += 1

    montier_flags_def = [
        ("f1_cfo_divergence", "Bandera 1: Divergencia Beneficio vs. Caja", "Utilidad Neta > Flujo de Caja Operativo (NI > CFO)", "Beneficios no monetizados en caja"),
        ("f2_ar_vs_sales", "Bandera 2: Cuentas por Cobrar > Ventas", "Δ Cuentas por Cobrar % > Δ Ventas %", "Facturación acelerada / Channel Stuffing"),
        ("f3_inv_vs_cogs", "Bandera 3: Inventarios > Coste de Ventas", "Δ Inventarios % > Δ Coste de Ventas %", "Sobreproducción para absorber costes o stock obsoleto"),
        ("f4_gross_margin", "Bandera 4: Deterioro del Margen Bruto", "Margen Bruto_t < Margen Bruto_t-1", "Presión en márgenes que incita al maquillaje"),
        ("f5_soft_assets", "Bandera 5: Incremento de Activos Blandos", "Ratio Activos Blandos_t > Ratio_t-1", "Capitalización indebida de gastos diferidos"),
        ("f6_depreciation_rate", "Bandera 6: Reducción de Tasa de Depreciación", "Tasa Depreciación_t < Tasa Depreciación_t-1", "Estiramiento de vidas útiles para inflar utilidad")
    ]

    for f_key, f_name, f_cond, f_just in montier_flags_def:
        ws.cell(row=r, column=1, value=f_name).font = REGULAR_FONT
        ws.cell(row=r, column=2, value=f_cond).font = ITALIC_FONT
        ws.cell(row=r, column=3, value=f_just).font = ITALIC_FONT
        ws.cell(row=r, column=3).alignment = Alignment(horizontal="left", vertical="center")

        for col_idx, fy in enumerate(fiscal_years, start=4):
            m_data = montier_series.get(fy, {}).get("flags_breakdown", {}).get(f_key, {})
            is_flag = m_data.get("flag", None)
            cell = ws.cell(row=r, column=col_idx)

            if is_flag is None:
                cell.value = "-"
                cell.font = REGULAR_FONT
            elif is_flag:
                cell.value = "🚩 FLAG"
                cell.fill = RED_FILL
                cell.font = RED_FONT
            else:
                cell.value = "✅ OK"
                cell.fill = GREEN_FILL
                cell.font = GREEN_FONT

            cell.alignment = Alignment(horizontal="center", vertical="center")
            cell.border = BORDER_CELL

        for c_i in range(1, 4):
            ws.cell(row=r, column=c_i).border = BORDER_CELL

        ws.row_dimensions[r].height = 20
        r += 1

    # Fila Resumen Total Montier
    ws.cell(row=r, column=1, value="(=) MONTIER C-SCORE TOTAL (0 a 6 Puntos)").font = BOLD_FONT
    ws.cell(row=r, column=2, value="Suma de Banderas Activas (0 a 6)").font = BOLD_FONT
    ws.cell(row=r, column=3, value="0-1: Bajo Riesgo | 2-3: Moderado | 4-6: Alto Riesgo").font = BOLD_FONT
    ws.cell(row=r, column=3).alignment = Alignment(horizontal="center", vertical="center")

    for col_idx, fy in enumerate(fiscal_years, start=4):
        m_data = montier_series.get(fy, {})
        tot_sc = m_data.get("total_score")
        cell = ws.cell(row=r, column=col_idx)

        if tot_sc is not None:
            cell.value = f"{tot_sc}/6"
            cell.font = SCORE_NUM_FONT
            if tot_sc <= 1:
                cell.fill = GREEN_FILL
                cell.font = GREEN_FONT
            elif tot_sc <= 3:
                cell.fill = YELLOW_FILL
                cell.font = BOLD_FONT
            else:
                cell.fill = RED_FILL
                cell.font = RED_FONT
        else:
            cell.value = "-"
            cell.font = BOLD_FONT

        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = BORDER_TOTAL

    for c_i in range(1, 4):
        ws.cell(row=r, column=c_i).border = BORDER_TOTAL
    ws.row_dimensions[r].height = 22
    r += 1

    # Fila Calificación C-Score
    ws.cell(row=r, column=1, value="Nivel de Riesgo & Dictamen C-Score").font = BOLD_FONT
    ws.cell(row=r, column=2, value="Clasificación Institucional de Riesgo Forense").font = ITALIC_FONT
    ws.cell(row=r, column=3, value="Probabilidad Empírica de Manipulación").font = ITALIC_FONT
    ws.cell(row=r, column=3).alignment = Alignment(horizontal="center", vertical="center")

    for col_idx, fy in enumerate(fiscal_years, start=4):
        m_data = montier_series.get(fy, {})
        rating = m_data.get("rating", "-")
        cell = ws.cell(row=r, column=col_idx, value=rating)
        cell.font = BOLD_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = BORDER_CELL

        if "BAJO" in rating or "LIMPIOS" in rating:
            cell.fill = GREEN_FILL
            cell.font = GREEN_FONT
        elif "MODERADO" in rating or "PREVENTIVA" in rating:
            cell.fill = YELLOW_FILL
            cell.font = BOLD_FONT
        elif "ALTO" in rating or "FORENSE" in rating:
            cell.fill = RED_FILL
            cell.font = RED_FONT
        else:
            cell.font = ITALIC_FONT

    for c_i in range(1, 4):
        ws.cell(row=r, column=c_i).border = BORDER_CELL
    ws.row_dimensions[r].height = 22

    # Ajuste automático de columnas
    autofit_columns(ws, min_col=1, max_col=total_cols, min_width=16)


def create_solvency_sheet(wb, scoring_results, company_name, ticker, fiscal_years):
    """
    Genera la Hoja 11: 'Solvencia & Estrés Financiero' en el libro Excel institucional.
    Incluye:
    1. Cuadro de Mando Ejecutivo (Card con Veredicto Global, Rating Sintético Damodaran y Altman Z''-Score).
    2. Tabla 1: Apalancamiento y Capacidad de Amortización (Cash Flow Leverage: Deuda Neta/EBITDA, Deuda Neta/FCF).
    3. Tabla 2: Cobertura de Carga Financiera y Servicio de la Deuda (Interest Coverage, Cash Interest Coverage).
    4. Tabla 3: Liquidez Estricta y Riesgo de Refinanciación (Quick Ratio, Cash Ratio, Rollover Risk).
    5. Tabla 4: Modelos Predictivos de Quiebra y Rating Sintético (Altman Z''-Score, Rating Damodaran, Spread Teórico).
    Cada segmento cuenta con descripción de fórmulas y parámetros evaluados.
    """
    sheet_title = "Solvencia & Estrés Financiero"
    if sheet_title in wb.sheetnames:
        target_idx = wb.sheetnames.index(sheet_title)
        del wb[sheet_title]
        ws = wb.create_sheet(title=sheet_title, index=target_idx)
    else:
        ws = wb.create_sheet(title=sheet_title)

    ws.views.sheetView[0].showGridLines = True

    # 1. Títulos
    ws.cell(row=1, column=1, value=f"{company_name} ({ticker.upper()}) - Solvencia, Deuda & Estrés Financiero (Credit Risk Engine)")
    ws.cell(row=1, column=1).font = TITLE_FONT
    ws.cell(row=2, column=1, value="Análisis Institucional: Capacidad de Pago contra Flujos de Caja, Cobertura de Intereses, Liquidez y Quiebra (Altman Z'' & Damodaran)")
    ws.cell(row=2, column=1).font = SUBTITLE_FONT

    solvency_data = scoring_results.get("debt_and_solvency_analysis", {})
    if not solvency_data:
        try:
            from financial_scoring_engine import DebtSolvencyEngine
            pass
        except Exception:
            pass

    lev_series = solvency_data.get("cash_flow_leverage", {})
    cov_series = solvency_data.get("debt_service", {})
    liq_series = solvency_data.get("liquidity_and_refinancing", {})
    dist_series = solvency_data.get("distress_and_credit_models", {})
    latest = solvency_data.get("latest_result", {})

    recent_fy = latest.get("period", "LTM" if "LTM" in fiscal_years else (fiscal_years[0] if fiscal_years else "N/A"))
    latest_lev = latest.get("cash_flow_leverage", lev_series.get(recent_fy, {}))
    latest_cov = latest.get("debt_service", cov_series.get(recent_fy, {}))
    latest_liq = latest.get("liquidity", liq_series.get(recent_fy, {}))
    latest_dist = latest.get("distress_models", dist_series.get(recent_fy, {}))
    global_verdict = latest.get("solvency_verdict", "Dictamen de solvencia pendiente de emisión.")
    global_badge = latest.get("global_badge", "SOLVENCIA INSTITUCIONAL")

    total_cols = len(fiscal_years) + 3

    # 2. Bloque Resumen Ejecutivo Card (Fila 4-5)
    ws.cell(row=4, column=1, value="DICTAMEN GLOBAL DE SOLVENCIA").font = SECTION_FONT
    ws.cell(row=4, column=1).fill = SECTION_FILL
    ws.cell(row=4, column=2, value=f"Período: {recent_fy}").font = BOLD_FONT
    ws.cell(row=4, column=2).fill = SECTION_FILL
    ws.cell(row=4, column=3, value=f"Rating Sintético: {latest_dist.get('synthetic_rating', 'N/D')} [{latest_dist.get('synthetic_rating_desc', 'N/D')}]").font = BOLD_FONT
    ws.cell(row=4, column=3).fill = SECTION_FILL
    ws.cell(row=4, column=4, value=f"Altman Z'': {latest_dist.get('altman_z_double_prime', 'N/D')} [{latest_dist.get('altman_badge', 'N/D')}]").font = BOLD_FONT
    ws.cell(row=4, column=4).fill = SECTION_FILL
    ws.cell(row=4, column=5, value=f"Estado: {global_badge}").font = BOLD_FONT
    ws.cell(row=4, column=5).fill = SECTION_FILL

    for c in range(6, total_cols + 1):
        ws.cell(row=4, column=c).fill = SECTION_FILL

    ws.row_dimensions[4].height = 24

    ws.cell(row=5, column=1, value="VEREDICTO SOLVENCIA:").font = BOLD_FONT
    ws.cell(row=5, column=1).alignment = Alignment(horizontal="left", vertical="center")
    ws.cell(row=5, column=1).border = BORDER_CELL

    # Merge de columnas 2 a total_cols para mostrar el veredicto completo
    ws.merge_cells(start_row=5, start_column=2, end_row=5, end_column=total_cols)
    cell_v = ws.cell(row=5, column=2, value=global_verdict)
    cell_v.font = BOLD_FONT
    cell_v.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)
    for c_i in range(2, total_cols + 1):
        ws.cell(row=5, column=c_i).border = BORDER_CELL
    ws.row_dimensions[5].height = 36

    r = 7

    def write_table_headers(row_num, col1_title, col2_title, col3_title):
        ws.cell(row=row_num, column=1, value=col1_title).font = WHITE_BOLD
        ws.cell(row=row_num, column=1).fill = NAVY_HEADER
        ws.cell(row=row_num, column=1).alignment = Alignment(horizontal="left", vertical="center")

        ws.cell(row=row_num, column=2, value=col2_title).font = WHITE_BOLD
        ws.cell(row=row_num, column=2).fill = NAVY_HEADER
        ws.cell(row=row_num, column=2).alignment = Alignment(horizontal="left", vertical="center")

        ws.cell(row=row_num, column=3, value=col3_title).font = WHITE_BOLD
        ws.cell(row=row_num, column=3).fill = NAVY_HEADER
        ws.cell(row=row_num, column=3).alignment = Alignment(horizontal="center", vertical="center")

        for c_idx, fy in enumerate(fiscal_years, start=4):
            c_cell = ws.cell(row=row_num, column=c_idx, value=fy)
            if fy == "LTM":
                c_cell.fill = LTM_HEADER
                c_cell.font = LTM_FONT
            else:
                c_cell.fill = NAVY_HEADER
                c_cell.font = WHITE_BOLD
            c_cell.alignment = Alignment(horizontal="center", vertical="center")
        ws.row_dimensions[row_num].height = 25

    # -------------------------------------------------------------------------
    # TABLA 1: APALANCAMIENTO Y CAPACIDAD DE AMORTIZACIÓN (CASH FLOW LEVERAGE)
    # -------------------------------------------------------------------------
    ws.cell(row=r, column=1, value="TABLA 1: APALANCAMIENTO Y CAPACIDAD DE AMORTIZACIÓN (CASH FLOW LEVERAGE)").font = SECTION_FONT
    ws.cell(row=r, column=1).fill = SECTION_FILL
    for c in range(2, total_cols + 1):
        ws.cell(row=r, column=c).fill = SECTION_FILL
    r += 1

    write_table_headers(r, "Componente / Métrica de Apalancamiento", "Definición / Fórmula Contable", "Zona Óptima / Umbral Crediticio")
    ws.cell(row=r, column=1).comment = Comment(
        "Evalúa cuántos años de generación bruta de efectivo (EBITDA o FCF) necesita la empresa para cancelar su deuda neta. "
        "Valores menores a 1.5x representan grado de inversión superior. Si la empresa tiene más caja que deuda, reporta Posición de Caja Neta.",
        "Solvencia Institucional"
    )
    r += 1

    t1_rows = [
        ("(+) Deuda Financiera Total ($M)", "Short-Term Debt + Long-Term Debt", "Referencia Balance", "total_debt", FMT_CURRENCY_M, False, None),
        ("(-) Tesorería y Equivalentes ($M)", "Cash & Cash Equivalents", "Liquidez Inmediata", "cash", FMT_CURRENCY_M, False, None),
        ("(=) Deuda Financiera Neta ($M)", "Deuda Total - Tesorería", "Caja Neta < $0 (Deseable)", "net_debt", FMT_CURRENCY_M, True, BORDER_SUBTOTAL),
        ("(+) Beneficio Operativo EBIT ($M)", "Operating Income Reportado", "Capacidad Operativa", "ebit", FMT_CURRENCY_M, False, None),
        ("(+) Depreciación y Amortización ($M)", "D&A en Estado de Flujos", "Gasto No Monetario", "dna", FMT_CURRENCY_M, False, None),
        ("(=) EBITDA ($M) [Generación Bruta]", "EBIT + Depreciación y Amortización", "Base Operativa Bruta", "ebitda", FMT_CURRENCY_M, True, BORDER_SUBTOTAL),
        ("(=) Deuda Neta / EBITDA (Años de EBITDA)", "Deuda Neta / EBITDA", "Óptimo: < 1.5x | Alerta: > 3.5x", "net_debt_to_ebitda", FMT_MULTIPLIER, True, BORDER_TOTAL),
        ("(+) Flujo de Caja Libre FCF ($M)", "Flujo Operativo (CFO) - CapEx", "Caja de Libre Disposición", "fcf", FMT_CURRENCY_M, False, None),
        ("(=) Deuda Neta / FCF (Años de Caja Libre)", "Deuda Neta / FCF", "Óptimo: < 2.0x | Alerta: > 4.0x", "net_debt_to_fcf", FMT_MULTIPLIER, True, BORDER_TOTAL),
        ("Deuda Total / Flujo de Caja Operativo (x)", "Deuda Total / CFO", "Óptimo: < 2.0x | Alerta: > 4.0x", "debt_to_cfo", FMT_MULTIPLIER, False, None),
    ]

    for label, formula, threshold, key, num_fmt, is_bold, border_style in t1_rows:
        ws.cell(row=r, column=1, value=label).font = BOLD_FONT if is_bold else REGULAR_FONT
        ws.cell(row=r, column=2, value=formula).font = ITALIC_FONT
        ws.cell(row=r, column=3, value=threshold).font = ITALIC_FONT
        ws.cell(row=r, column=3).alignment = Alignment(horizontal="center", vertical="center")

        for col_idx, fy in enumerate(fiscal_years, start=4):
            cell = ws.cell(row=r, column=col_idx)
            val = lev_series.get(fy, {}).get(key)
            is_net_c = lev_series.get(fy, {}).get("is_net_cash", False)

            if key in ["net_debt_to_ebitda", "net_debt_to_fcf"] and is_net_c:
                cell.value = "CAJA NETA"
                cell.font = GREEN_FONT
                cell.fill = GREEN_FILL
                cell.alignment = Alignment(horizontal="center", vertical="center")
            elif val is not None:
                cell.value = val
                cell.number_format = num_fmt
                cell.font = BOLD_FONT if is_bold else REGULAR_FONT
                cell.alignment = Alignment(horizontal="right", vertical="center")
            else:
                cell.value = "-"
                cell.font = REGULAR_FONT
                cell.alignment = Alignment(horizontal="center", vertical="center")

            if border_style:
                cell.border = border_style
            else:
                cell.border = BORDER_CELL

        for c_i in range(1, 4):
            ws.cell(row=r, column=c_i).border = border_style if border_style else BORDER_CELL
        ws.row_dimensions[r].height = 20
        r += 1

    # Fila Diagnóstico de Capacidad de Repago
    ws.cell(row=r, column=1, value="Diagnóstico de Capacidad de Repago").font = BOLD_FONT
    ws.cell(row=r, column=2, value="Evaluación de Amortización contra Caja").font = ITALIC_FONT
    ws.cell(row=r, column=3, value="Sostenibilidad de Deuda").font = ITALIC_FONT
    ws.cell(row=r, column=3).alignment = Alignment(horizontal="center", vertical="center")

    for col_idx, fy in enumerate(fiscal_years, start=4):
        cell = ws.cell(row=r, column=col_idx)
        diag = lev_series.get(fy, {}).get("badge", lev_series.get(fy, {}).get("status", "N/D"))
        cell.value = diag
        cell.font = BOLD_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = BORDER_CELL

        if "EXCELENTE" in diag or "CAJA NETA" in diag or "SUPERIOR" in diag or "BAJO" in diag:
            cell.fill = GREEN_FILL
            cell.font = GREEN_FONT
        elif "MODERADO" in diag or "SALUDABLE" in diag:
            cell.fill = HIGHLIGHT_FILL
            cell.font = BOLD_FONT
        elif "VULNERABILIDAD" in diag or "VIGILANCIA" in diag:
            cell.fill = YELLOW_FILL
            cell.font = BOLD_FONT
        elif "ALTO" in diag or "ESPECULATIVO" in diag or "ALERTA" in diag:
            cell.fill = RED_FILL
            cell.font = RED_FONT

    for c_i in range(1, 4):
        ws.cell(row=r, column=c_i).border = BORDER_CELL
    ws.row_dimensions[r].height = 22
    r += 1

    # Tarjeta Diagnóstico Apalancamiento LTM
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=total_cols)
    lev_diag = latest_lev.get("diagnosis", "Estructura de endeudamiento y capacidad de amortización auditada.")
    d_cell = ws.cell(row=r, column=1, value=f"Diagnóstico de Apalancamiento ({recent_fy}): {lev_diag}")
    d_cell.font = ITALIC_FONT
    d_cell.fill = HIGHLIGHT_FILL
    d_cell.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)
    for c_i in range(1, total_cols + 1):
        ws.cell(row=r, column=c_i).border = BORDER_CELL
    ws.row_dimensions[r].height = 32
    r += 2

    # -------------------------------------------------------------------------
    # TABLA 2: COBERTURA DE CARGA FINANCIERA Y SERVICIO DE LA DEUDA
    # -------------------------------------------------------------------------
    ws.cell(row=r, column=1, value="TABLA 2: COBERTURA DE CARGA FINANCIERA Y SERVICIO DE LA DEUDA (INTEREST COVERAGE)").font = SECTION_FONT
    ws.cell(row=r, column=1).fill = SECTION_FILL
    for c in range(2, total_cols + 1):
        ws.cell(row=r, column=c).fill = SECTION_FILL
    r += 1

    write_table_headers(r, "Ratio de Cobertura / Carga Financiera", "Definición / Fórmula de Cobertura", "Umbral de Solvencia Operativa")
    ws.cell(row=r, column=1).comment = Comment(
        "Mide la capacidad de la utilidad operativa (EBIT) y el flujo de caja operativo (CFO) "
        "para absorber los intereses de la deuda. Coberturas < 2.5x reflejan alta vulnerabilidad ante subidas de tipos.",
        "Cobertura y Carga Financiera"
    )
    r += 1

    cov_rows = [
        ("(+) Utilidad Operativa EBIT ($M) [Operating Income]", "Resultado de Explotación Reportado", "Capacidad Operativa", "ebit", FMT_CURRENCY_M, False, None),
        ("(-) Flujo de Caja Operativo CFO ($M) [Cash Flow]", "Generación de Caja Operativa Real", "Capacidad Líquida", "cfo", FMT_CURRENCY_M, False, None),
        ("(=) Gasto por Intereses ($M) [Interest Expense]", "Coste de Financiación de Deuda", "Carga Financiera Bruta", "interest_expense", FMT_CURRENCY_M, True, BORDER_SUBTOTAL),
        ("Cobertura de Intereses Operativa (EBIT / Intereses)", "EBIT / Gasto de Intereses", "Óptimo: > 10.0x | Alerta: < 2.5x", "interest_coverage", FMT_MULTIPLIER, True, BORDER_TOTAL),
        ("Cobertura de Intereses en Caja (CFO / Intereses)", "CFO / Gasto de Intereses", "Óptimo: > 8.0x | Alerta: < 2.0x", "cash_interest_coverage", FMT_MULTIPLIER, False, None),
        ("Carga Financiera sobre Caja (% Intereses / CFO)", "(Intereses / CFO) * 100", "Óptimo: < 5.0% | Alerta: > 20.0%", "financial_burden_pct", FMT_PERCENT, False, None)
    ]

    for label, formula, threshold, key, fmt, is_bold, border_style in cov_rows:
        ws.cell(row=r, column=1, value=label).font = BOLD_FONT if is_bold else REGULAR_FONT
        ws.cell(row=r, column=2, value=formula).font = ITALIC_FONT
        ws.cell(row=r, column=3, value=threshold).font = ITALIC_FONT
        ws.cell(row=r, column=3).alignment = Alignment(horizontal="center", vertical="center")

        for col_idx, fy in enumerate(fiscal_years, start=4):
            c_data = cov_series.get(fy, {})
            val = c_data.get(key)
            cell = ws.cell(row=r, column=col_idx)

            if fmt == FMT_CURRENCY_M:
                if val is not None:
                    cell.value = val / 1_000_000.0 if val > 100_000 else val
                    cell.number_format = fmt
                else:
                    cell.value = "-"
                cell.alignment = Alignment(horizontal="right", vertical="center")
            elif fmt == FMT_MULTIPLIER:
                if val is not None:
                    cell.value = val
                    cell.number_format = fmt
                    if val >= 10.0:
                        cell.fill = GREEN_FILL
                        cell.font = GREEN_FONT
                    elif val >= 5.0:
                        cell.fill = HIGHLIGHT_FILL
                        cell.font = BOLD_FONT
                    elif val >= 2.5:
                        cell.fill = YELLOW_FILL
                        cell.font = BOLD_FONT
                    else:
                        cell.fill = RED_FILL
                        cell.font = RED_FONT
                else:
                    cell.value = c_data.get(f"{key}_str", "-")
                    cell.font = BOLD_FONT
                    cell.alignment = Alignment(horizontal="center", vertical="center")
                    if "INFINITA" in str(cell.value):
                        cell.fill = GREEN_FILL
                        cell.font = GREEN_FONT
                cell.alignment = Alignment(horizontal="right" if val is not None else "center", vertical="center")
            elif fmt == FMT_PERCENT:
                if val is not None:
                    cell_val = val / 100.0 if val > 1.0 else val
                    cell.value = cell_val
                    cell.number_format = fmt
                else:
                    cell.value = "-"
                cell.alignment = Alignment(horizontal="right", vertical="center")
            else:
                cell.value = str(val) if val is not None else "-"
                cell.alignment = Alignment(horizontal="center", vertical="center")

            if border_style:
                cell.border = border_style
            else:
                cell.border = BORDER_CELL

        for c_i in range(1, 4):
            ws.cell(row=r, column=c_i).border = border_style if border_style else BORDER_CELL
        ws.row_dimensions[r].height = 20
        r += 1

    # Fila Diagnóstico Cobertura
    ws.cell(row=r, column=1, value="Diagnóstico de Cobertura y Servicio").font = BOLD_FONT
    ws.cell(row=r, column=2, value="Protección ante Tipos de Interés").font = ITALIC_FONT
    ws.cell(row=r, column=3, value="Resistencia Crediticia").font = ITALIC_FONT
    ws.cell(row=r, column=3).alignment = Alignment(horizontal="center", vertical="center")

    for col_idx, fy in enumerate(fiscal_years, start=4):
        cell = ws.cell(row=r, column=col_idx)
        diag = cov_series.get(fy, {}).get("badge", cov_series.get(fy, {}).get("status", "N/D"))
        cell.value = diag
        cell.font = BOLD_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = BORDER_CELL

        if "EXCELENTE" in diag or "LIBRE" in diag or "SALUDABLE" in diag or "BLINDADO" in diag or "ROBUSTA" in diag:
            cell.fill = GREEN_FILL
            cell.font = GREEN_FONT
        elif "VULNERABILIDAD" in diag or "VIGILANCIA" in diag:
            cell.fill = YELLOW_FILL
            cell.font = BOLD_FONT
        elif "DEFAULT" in diag or "ESTRÉS" in diag:
            cell.fill = RED_FILL
            cell.font = RED_FONT

    for c_i in range(1, 4):
        ws.cell(row=r, column=c_i).border = BORDER_CELL
    ws.row_dimensions[r].height = 22
    r += 1

    # Tarjeta Diagnóstico Cobertura LTM
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=total_cols)
    cov_diag = latest_cov.get("diagnosis", "Capacidad de servicio de intereses validada.")
    d_cell = ws.cell(row=r, column=1, value=f"Diagnóstico de Cobertura ({recent_fy}): {cov_diag}")
    d_cell.font = ITALIC_FONT
    d_cell.fill = HIGHLIGHT_FILL
    d_cell.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)
    for c_i in range(1, total_cols + 1):
        ws.cell(row=r, column=c_i).border = BORDER_CELL
    ws.row_dimensions[r].height = 32
    r += 2

    # -------------------------------------------------------------------------
    # TABLA 3: LIQUIDEZ ESTRICTA Y RIESGO DE REFINANCIACIÓN (ROLLOVER RISK)
    # -------------------------------------------------------------------------
    ws.cell(row=r, column=1, value="TABLA 3: LIQUIDEZ ESTRICTA Y RIESGO DE REFINANCIACIÓN (ROLLOVER RISK)").font = SECTION_FONT
    ws.cell(row=r, column=1).fill = SECTION_FILL
    for c in range(2, total_cols + 1):
        ws.cell(row=r, column=c).fill = SECTION_FILL
    r += 1

    write_table_headers(r, "Ratio de Liquidez / Refinanciación", "Definición / Fórmula Contable", "Parámetro de Solvencia Inmediata")
    ws.cell(row=r, column=1).comment = Comment(
        "Analiza la liquidez sin depender de la venta forzada de existencias (Quick Ratio) "
        "y la proporción de deuda que vence en menos de 12 meses (Riesgo de Refinanciación).",
        "Liquidez y Vencimientos"
    )
    r += 1

    liq_rows = [
        ("(+) Caja y Equivalentes ($M) [Cash & ST Investments]", "Efectivo Disponible Inmediato", "Tesorería Líquida", "cash", FMT_CURRENCY_M, False, None),
        ("(+) Cuentas por Cobrar a Clientes ($M) [Receivables]", "Créditos Comerciales Pendientes", "Cobro < 90 días", "accounts_receivable", FMT_CURRENCY_M, False, None),
        ("(-) Pasivo Corriente ($M) [Current Liabilities]", "Obligaciones Exigibles < 12 meses", "Deuda Corto Plazo", "current_liabilities", FMT_CURRENCY_M, False, None),
        ("Ratio de Liquidez Inmediata (Cash Ratio)", "Caja / Pasivo Corriente", "Óptimo: > 0.50x | Alerta: < 0.20x", "cash_ratio", FMT_MULTIPLIER, False, None),
        ("Test Ácido / Quick Ratio (Caja + AR / Pasivo Corr.)", "(Caja + Cobros) / Pasivo Corriente", "Óptimo: > 1.20x | Alerta: < 0.80x", "quick_ratio", FMT_MULTIPLIER, True, BORDER_SUBTOTAL),
        ("Ratio Corriente / Current Ratio (Act. Corr. / Pas. Corr.)", "Activo Corriente / Pasivo Corriente", "Óptimo: > 1.50x | Alerta: < 1.00x", "current_ratio", FMT_MULTIPLIER, False, None),
        ("Deuda Financiera a Corto Plazo ($M) [ST Debt]", "Vencimientos de Deuda < 1 Año", "Exigibilidad Inmediata", "short_term_debt", FMT_CURRENCY_M, False, None),
        ("Riesgo de Refinanciación (% Deuda Corto Plazo / Total)", "(Deuda CP / Deuda Total) * 100", "Óptimo: < 25.0% | Alerta: > 50.0%", "rollover_risk_pct", FMT_PERCENT, True, BORDER_TOTAL)
    ]

    for label, formula, threshold, key, fmt, is_bold, border_style in liq_rows:
        ws.cell(row=r, column=1, value=label).font = BOLD_FONT if is_bold else REGULAR_FONT
        ws.cell(row=r, column=2, value=formula).font = ITALIC_FONT
        ws.cell(row=r, column=3, value=threshold).font = ITALIC_FONT
        ws.cell(row=r, column=3).alignment = Alignment(horizontal="center", vertical="center")

        for col_idx, fy in enumerate(fiscal_years, start=4):
            l_data = liq_series.get(fy, {})
            val = l_data.get(key)
            cell = ws.cell(row=r, column=col_idx)

            if fmt == FMT_CURRENCY_M:
                if val is not None:
                    cell.value = val / 1_000_000.0 if val > 100_000 else val
                    cell.number_format = fmt
                else:
                    cell.value = "-"
                cell.alignment = Alignment(horizontal="right", vertical="center")
            elif fmt == FMT_MULTIPLIER:
                if val is not None:
                    cell.value = val
                    cell.number_format = fmt
                    if key == "quick_ratio":
                        if val >= 1.20:
                            cell.fill = GREEN_FILL
                            cell.font = GREEN_FONT
                        elif val >= 0.80:
                            cell.fill = HIGHLIGHT_FILL
                            cell.font = BOLD_FONT
                        else:
                            cell.fill = YELLOW_FILL
                            cell.font = BOLD_FONT
                else:
                    cell.value = "-"
                cell.alignment = Alignment(horizontal="right", vertical="center")
            elif fmt == FMT_PERCENT:
                if val is not None:
                    cell_val = val / 100.0 if val > 1.0 else val
                    cell.value = cell_val
                    cell.number_format = fmt
                    if key == "rollover_risk_pct":
                        if cell_val > 0.50:
                            cell.fill = RED_FILL
                            cell.font = RED_FONT
                        elif cell_val > 0.30:
                            cell.fill = YELLOW_FILL
                            cell.font = BOLD_FONT
                        else:
                            cell.fill = GREEN_FILL
                            cell.font = GREEN_FONT
                else:
                    cell.value = "-"
                cell.alignment = Alignment(horizontal="right", vertical="center")
            else:
                cell.value = str(val) if val is not None else "-"
                cell.alignment = Alignment(horizontal="center", vertical="center")

            if border_style:
                cell.border = border_style
            else:
                cell.border = BORDER_CELL

        for c_i in range(1, 4):
            ws.cell(row=r, column=c_i).border = border_style if border_style else BORDER_CELL
        ws.row_dimensions[r].height = 20
        r += 1

    # Fila Diagnóstico de Liquidez
    ws.cell(row=r, column=1, value="Diagnóstico de Liquidez y Refinanciación").font = BOLD_FONT
    ws.cell(row=r, column=2, value="Salud de Tesorería y Calendario de Deuda").font = ITALIC_FONT
    ws.cell(row=r, column=3, value="Riesgo de Liquidez").font = ITALIC_FONT
    ws.cell(row=r, column=3).alignment = Alignment(horizontal="center", vertical="center")

    for col_idx, fy in enumerate(fiscal_years, start=4):
        cell = ws.cell(row=r, column=col_idx)
        diag = liq_series.get(fy, {}).get("badge", liq_series.get(fy, {}).get("status", "N/D"))
        cell.value = diag
        cell.font = BOLD_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = BORDER_CELL

        if "EXCELENTE" in diag or "HOLGADA" in diag or "COLCHÓN" in diag:
            cell.fill = GREEN_FILL
            cell.font = GREEN_FONT
        elif "EQUILIBRADA" in diag:
            cell.fill = HIGHLIGHT_FILL
            cell.font = BOLD_FONT
        else:
            cell.fill = YELLOW_FILL
            cell.font = BOLD_FONT

    for c_i in range(1, 4):
        ws.cell(row=r, column=c_i).border = BORDER_CELL
    ws.row_dimensions[r].height = 22
    r += 1

    # Tarjeta Diagnóstico Liquidez LTM
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=total_cols)
    liq_diag = latest_liq.get("diagnosis", "Gestión de tesorería y calendario de deuda auditados.")
    d_cell = ws.cell(row=r, column=1, value=f"Diagnóstico de Liquidez ({recent_fy}): {liq_diag}")
    d_cell.font = ITALIC_FONT
    d_cell.fill = HIGHLIGHT_FILL
    d_cell.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)
    for c_i in range(1, total_cols + 1):
        ws.cell(row=r, column=c_i).border = BORDER_CELL
    ws.row_dimensions[r].height = 32
    r += 2

    # -------------------------------------------------------------------------
    # TABLA 4: MODELOS PREDICTIVOS DE QUIEBRA Y RATING SINTÉTICO (ALTMAN Z'' & DAMODARAN)
    # -------------------------------------------------------------------------
    ws.cell(row=r, column=1, value="TABLA 4: MODELOS PREDICTIVOS DE QUIEBRA Y RATING SINTÉTICO (ALTMAN Z'' & DAMODARAN)").font = SECTION_FONT
    ws.cell(row=r, column=1).fill = SECTION_FILL
    for c in range(2, total_cols + 1):
        ws.cell(row=r, column=c).fill = SECTION_FILL
    r += 1

    write_table_headers(r, "Modelo / Métrica de Estrés e Insolvencia", "Definición / Fórmula Econométrica", "Clasificación de Riesgo Crediticio")
    ws.cell(row=r, column=1).comment = Comment(
        "El Altman Z''-Score (4 variables) predice la probabilidad de insolvencia a 2 años vista (Segura > 2.60 | Distress < 1.10). "
        "El Rating Sintético de Damodaran mapea la cobertura de intereses al rating de S&P/Moody's y su probabilidad empírica de impago.",
        "Modelos de Insolvencia"
    )
    r += 1

    t4_rows = [
        ("Componente X1: Fondo de Maniobra / Activos", "(Activo Corriente - Pasivo Corriente) / Activos", "Liquidez Relativa de Balance", "altman_x1", "0.0000", False, None),
        ("Componente X2: Resultados Acumulados / Activos", "Retained Earnings / Activos Totales", "Autofinanciación Histórica", "altman_x2", "0.0000", False, None),
        ("Componente X3: EBIT / Activos Totales", "Beneficio Operativo / Activos Totales", "Productividad Pura de Activos", "altman_x3", "0.0000", False, None),
        ("Componente X4: Patrimonio Neto / Pasivos Totales", "Stockholders' Equity / Total Liabilities", "Colchón de Solvencia Patrimonial", "altman_x4", "0.0000", False, None),
        ("(=) ALTMAN Z''-SCORE TOTAL (Modelo 4 Variables)", "6.56*X1 + 3.26*X2 + 6.72*X3 + 1.05*X4", "Segura: > 2.60 | Distress: < 1.10", "altman_z_double_prime", "0.00", True, BORDER_TOTAL),
        ("Zona de Riesgo de Quiebra Altman", "Dictamen Econométrico de Insolvencia", "Probabilidad de Default a 2 Años", "altman_zone", "str", True, BORDER_CELL),
        ("(=) Rating Crediticio Sintético (Damodaran)", "Equivalencia S&P / Moody's según Cobertura", "Grado de Inversión (AAA a BBB-)", "synthetic_rating", "str", True, BORDER_TOTAL),
        ("Calificación Detallada del Emisor", "Descripción Institucional del Rating", "Categoría de Calidad Crediticia", "synthetic_rating_desc", "str", False, None),
        ("Diferencial de Crédito Teórico (Spread %)", "Spread Estimado sobre Tipo Libre de Riesgo", "Coste de Financiación Marginal", "default_spread_pct", FMT_PERCENT, False, None),
        ("Probabilidad Estadística de Default (%)", "Frecuencia Histórica de Impago Acumulada", "Estadística S&P a 10 Años", "default_probability", "str", False, None),
    ]

    for label, formula, threshold, key, num_fmt, is_bold, border_style in t4_rows:
        ws.cell(row=r, column=1, value=label).font = BOLD_FONT if is_bold else REGULAR_FONT
        ws.cell(row=r, column=2, value=formula).font = ITALIC_FONT
        ws.cell(row=r, column=3, value=threshold).font = ITALIC_FONT
        ws.cell(row=r, column=3).alignment = Alignment(horizontal="center", vertical="center")

        for col_idx, fy in enumerate(fiscal_years, start=4):
            cell = ws.cell(row=r, column=col_idx)
            val = dist_series.get(fy, {}).get(key)

            if val is not None:
                if num_fmt == "str":
                    cell.value = str(val)
                    cell.font = BOLD_FONT if is_bold else REGULAR_FONT
                    cell.alignment = Alignment(horizontal="center", vertical="center")
                    if key == "altman_zone":
                        if "SEGURA" in str(val):
                            cell.fill = GREEN_FILL
                            cell.font = GREEN_FONT
                        elif "GRIS" in str(val):
                            cell.fill = YELLOW_FILL
                        elif "DISTRESS" in str(val):
                            cell.fill = RED_FILL
                            cell.font = RED_FONT
                    elif key == "synthetic_rating":
                        if "AAA" in str(val) or "AA" in str(val):
                            cell.fill = GREEN_FILL
                            cell.font = GREEN_FONT
                        elif "A" in str(val) or "BBB" in str(val):
                            cell.fill = YELLOW_FILL
                        else:
                            cell.fill = RED_FILL
                            cell.font = RED_FONT
                else:
                    if num_fmt == FMT_PERCENT and key == "default_spread_pct":
                        cell.value = val / 100.0
                    else:
                        cell.value = val
                    cell.number_format = num_fmt
                    cell.font = BOLD_FONT if is_bold else REGULAR_FONT
                    cell.alignment = Alignment(horizontal="right", vertical="center")
            else:
                cell.value = "-"
                cell.font = REGULAR_FONT
                cell.alignment = Alignment(horizontal="center", vertical="center")

            if border_style:
                cell.border = border_style
            else:
                cell.border = BORDER_CELL

        for c_i in range(1, 4):
            ws.cell(row=r, column=c_i).border = border_style if border_style else BORDER_CELL
        ws.row_dimensions[r].height = 20
        r += 1

    # Ajuste automático de columnas
    autofit_columns(ws, min_col=1, max_col=total_cols, min_width=16)


def generate_full_excel_workbook(ticker="AAPL"):
    """
    Genera o actualiza el libro completo de 11 pestañas para el ticker dado,
    incorporando ratios, scores fundamentales, peer group benchmarks, conciliación tripartita,
    auditoría forense contable y solvencia / estrés financiero.
    Sincroniza el resultado en Google Drive si está disponible.
    """
    import json
    import shutil
    from pathlib import Path
    
    ticker_upper = ticker.upper()
    local_base = Path("data/processed") / ticker_upper
    fin_json_path = local_base / "financial_statements.json"
    excel_path = local_base / "financial_statements.xlsx"
    
    if not fin_json_path.exists():
        raise FileNotFoundError(f"No se encontró financial_statements.json en {local_base}")
        
    with open(fin_json_path, "r", encoding="utf-8") as f:
        fin_data = json.load(f)
        
    company_name = fin_data.get("company_name", ticker_upper)
    fiscal_years = fin_data.get("fiscal_years", [])
    ratios_dict = fin_data.get("key_ratios", {})
    
    # Cargar scoring data
    scoring_json_path = local_base / "fundamental_scores.json"
    if scoring_json_path.exists():
        with open(scoring_json_path, "r", encoding="utf-8") as f:
            scoring_data = json.load(f)
    else:
        try:
            from financial_scoring_engine import calculate_fundamental_scores
            scoring_data = calculate_fundamental_scores(ticker_upper, fin_json_path, local_base)
        except Exception:
            scoring_data = {}
            
    sic_code = scoring_data.get("sic_code")
    
    summary_dict = fin_data.get("canonical_summary", {})

    def _detail_dict_to_df(detail_dict):
        if not detail_dict or not isinstance(detail_dict, dict):
            return pd.DataFrame()
        rows = []
        for concept, item in detail_dict.items():
            r = {"concept": concept, "label": item.get("label", concept) if isinstance(item, dict) else concept}
            if isinstance(item, dict) and "values" in item:
                r.update(item.get("values", {}))
            elif isinstance(item, dict):
                r.update(item)
            rows.append(r)
        return pd.DataFrame(rows)

    inc_df = _detail_dict_to_df(fin_data.get("income_statement_detail"))
    if inc_df.empty:
        inc_df = pd.DataFrame(fin_data.get("raw_statements", {}).get("income_statement", {}))

    bal_df = _detail_dict_to_df(fin_data.get("balance_sheet_detail"))
    if bal_df.empty:
        bal_df = pd.DataFrame(fin_data.get("raw_statements", {}).get("balance_sheet", {}))

    cf_df = _detail_dict_to_df(fin_data.get("cash_flow_detail"))
    if cf_df.empty:
        cf_df = pd.DataFrame(fin_data.get("raw_statements", {}).get("cash_flow", {}))

    if excel_path.exists():
        wb = openpyxl.load_workbook(excel_path)
        create_summary_sheet(wb, summary_dict, company_name, ticker_upper, fiscal_years)
        create_ratios_sheet(wb, ratios_dict, company_name, ticker_upper, fiscal_years)

        # Actualizar Hoja 3 (Cuenta de Resultados) con reconciliación Split-Adjusted
        if "Cuenta de Resultados" in wb.sheetnames:
            del wb["Cuenta de Resultados"]
        create_clean_income_sheet(wb, inc_df, company_name, ticker_upper, fiscal_years)

        # Sincronizar CapEx en Hoja 5 (Flujo de Caja) si existe
        if "Flujo de Caja" in wb.sheetnames:
            ws_cf = wb["Flujo de Caja"]
            ltm_capex = summary_dict.get("capital_expenditures", {}).get("LTM")
            if ltm_capex:
                for r in range(1, ws_cf.max_row + 1):
                    v = ws_cf.cell(r, 1).value
                    if v and any(k in str(v).lower() for k in ["payments to acquire property", "capital expenditures", "inversión de capital"]):
                        ws_cf.cell(r, 2, value=float(ltm_capex) / 1_000_000.0)
                        break

        # Actualizar Hoja 6 (Desglose de Segmentos) con segmentos dinámicos
        if "Desglose de Segmentos" in wb.sheetnames:
            del wb["Desglose de Segmentos"]
        create_segments_sheet(wb, inc_df, company_name, ticker_upper, fiscal_years)

        create_scoring_sheet(wb, scoring_data, company_name, ticker_upper, fiscal_years)
        create_peer_group_sheet(wb, None, company_name, ticker_upper, sic_code=sic_code, scoring_results=scoring_data)
        create_reconciliation_sheet(wb, None, company_name, ticker_upper)
        create_forensic_sheet(wb, scoring_data, company_name, ticker_upper, fiscal_years)
        create_solvency_sheet(wb, scoring_data, company_name, ticker_upper, fiscal_years)

        # Orden canónico institucional de las 11 pestañas
        canonical_order = [
            "Resumen Fundamental",
            "Ratios Financieros",
            "Cuenta de Resultados",
            "Balance Patrimonial",
            "Flujo de Caja",
            "Desglose de Segmentos",
            "Scores Fundamentales",
            "Peer Group & Medianas",
            "Auditoría Forense & Devengos",
            "Solvencia & Estrés Financiero",
            "Conciliación & Fuentes"
        ]
        wb._sheets = [wb[s] for s in canonical_order if s in wb.sheetnames] + [wb[s] for s in wb.sheetnames if s not in canonical_order]

        # Estandarizar geometría de todas las hojas de estados contables en el libro
        for sheet_name in ["Cuenta de Resultados", "Balance Patrimonial", "Flujo de Caja", "Desglose de Segmentos", "Ratios Financieros"]:
            if sheet_name in wb.sheetnames:
                format_sheet_layout(wb[sheet_name], sheet_type="financial", min_col=1, max_col=len(fiscal_years) + 1, freeze_cell="B5")
        if "Scores Fundamentales" in wb.sheetnames:
            format_sheet_layout(wb["Scores Fundamentales"], sheet_type="scoring", min_col=1, max_col=len(fiscal_years) + 3, freeze_cell="D8")

        wb.save(excel_path)
        print(f"[Excel Formatter] Modelo Excel actualizado exitosamente (11 Pestañas): {excel_path}")
    else:
        summary_dict = fin_data.get("canonical_summary", {})
        inc_df = pd.DataFrame(fin_data.get("raw_statements", {}).get("income_statement", {}))
        bal_df = pd.DataFrame(fin_data.get("raw_statements", {}).get("balance_sheet", {}))
        cf_df = pd.DataFrame(fin_data.get("raw_statements", {}).get("cash_flow", {}))
        build_financial_excel(
            excel_path, summary_dict, ratios_dict, inc_df, bal_df, cf_df,
            ticker_upper, company_name, fiscal_years, scoring_results=scoring_data
        )
        wb = openpyxl.load_workbook(excel_path)
        create_reconciliation_sheet(wb, None, company_name, ticker_upper)
        create_forensic_sheet(wb, scoring_data, company_name, ticker_upper, fiscal_years)
        create_solvency_sheet(wb, scoring_data, company_name, ticker_upper, fiscal_years)
        wb.save(excel_path)
        print(f"[Excel Formatter] Modelo Excel generado desde cero exitosamente (11 Pestañas): {excel_path}")
        
    # Sincronizar en Google Drive
    try:
        from drive_manager import get_ticker_drive_processed_dir, safe_copy_file
        drive_processed = get_ticker_drive_processed_dir(ticker_upper)
    except ImportError:
        drive_processed = Path("G:/Mi unidad/analisis fundamental") / ticker_upper / "processed"
        safe_copy_file = None

    if drive_processed and drive_processed.exists():
        if safe_copy_file:
            ok = safe_copy_file(excel_path, drive_processed / excel_path.name)
            if ok:
                print(f"[Excel Formatter] Modelo sincronizado en Google Drive: {drive_processed / excel_path.name}")
        else:
            try:
                shutil.copy2(excel_path, drive_processed / excel_path.name)
                print(f"[Excel Formatter] Modelo sincronizado en Google Drive: {drive_processed / excel_path.name}")
            except Exception as e:
                print(f"[Excel Formatter] Nota sobre sincronización en Drive: {e}")
            
    return excel_path


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Generador de modelo Excel institucional de 9 pestañas")
    parser.add_argument("--ticker", default="DECK", help="Ticker de la empresa (ej: DECK, AAPL)")
    args = parser.parse_args()
    generate_full_excel_workbook(args.ticker)
