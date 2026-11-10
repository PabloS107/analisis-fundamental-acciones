"""
sec_xbrl_ltm.py - Extracción cruda XBRL, consultas a Company Facts, fusión multi-período
y cálculo de series LTM/TTM (US-GAAP 10-Q y parser interino HTML Form 6-K para FPIs).
"""

import io
import logging
import re
import statistics
from datetime import datetime
from typing import Any, Dict, List, Optional
import pandas as pd

try:
    from financial_taxonomy import XBRL_TAXONOMY_MAP, BANKING_TAXONOMY_MAP
except ImportError:
    try:
        from ..financial_taxonomy import XBRL_TAXONOMY_MAP, BANKING_TAXONOMY_MAP
    except ImportError:
        from pipeline.financial_taxonomy import XBRL_TAXONOMY_MAP, BANKING_TAXONOMY_MAP

logger = logging.getLogger(__name__)

_EPS_CONCEPT_TOKENS = {
    "earningspersharebasic",
    "earningspersharediluted",
    "earningspersharebasicanddiluted",
    "basicearningspershare",
    "dilutedearningspershare",
}

_STATEMENT_META_COLS = {
    "concept", "label", "standard_concept", "level", "depth", "section",
    "abstract", "is_abstract", "is_total", "dimension", "is_breakdown",
    "dimension_axis", "dimension_member", "dimension_member_label",
    "dimension_label", "balance", "weight", "preferred_sign",
    "parent_concept", "parent_abstract_concept",
}


def _safe_float(val: Any) -> Optional[float]:
    """Convierte un valor tabular XBRL a `float` de forma segura sin enmascarar otros errores."""
    if val is None or (isinstance(val, str) and not val.strip()):
        return None
    try:
        if pd.isna(val):
            return None
        return float(val)
    except (ValueError, TypeError):
        return None


def _is_dimensional_row(row: Any) -> bool:
    """Detecta si una fila de DataFrame XBRL corresponde a un desglose dimensional."""
    dim_val = row.get("dimension")
    if isinstance(dim_val, bool):
        if dim_val:
            return True
    elif dim_val is not None and str(dim_val).strip().lower() in ("true", "1"):
        return True
    axis_val = str(row.get("dimension_axis") or "").strip()
    return bool(axis_val and axis_val.lower() not in ("none", "nan"))


def _append_rows_safely(target_df: pd.DataFrame, row_dicts: List[Dict[str, Any]]) -> None:
    """
    Añade filas al DataFrame in-place evitando `FutureWarning` de pandas por
    concatenación implícita de columnas `all-NA` en `.loc[len(df)] = dict`.
    """
    if target_df is None or not row_dicts:
        return
    valid_cols = set(target_df.columns)
    next_idx = (int(target_df.index.max()) + 1) if len(target_df) > 0 and pd.api.types.is_integer_dtype(target_df.index) else len(target_df)
    for offset, row_dict in enumerate(row_dicts):
        idx = next_idx + offset
        wrote_any = False
        for col, val in row_dict.items():
            if col in valid_cols and val is not None and not (isinstance(val, float) and pd.isna(val)):
                target_df.loc[idx, col] = val
                wrote_any = True
        if not wrote_any and "concept" in valid_cols:
            target_df.loc[idx, "concept"] = row_dict.get("concept", "")


def _select_primary_class_eps(child_entries: List[tuple]) -> Optional[float]:
    """
    Selecciona el BPA legítimo de la clase ordinaria primaria cuando un DataFrame XBRL
    contiene filas hijas bajo `StatementClassOfStockAxis`.
    Prioriza: clase combinada (A y B) -> Clase A común -> mediana entre miembros únicos.
    """
    if not child_entries:
        return None
    for priority_tokens in (
        ("commonclassaandcommonclassb", "classaandclassb", "class a and class b"),
        ("commonclassamember", "class a common", "class a"),
        ("commonclassbmember", "class b common", "class b"),
    ):
        for member, lbl, val in child_entries:
            haystack = f"{member} {lbl}".lower()
            if any(tok in haystack for tok in priority_tokens):
                return round(float(val), 4)
    # Deduplicar por miembro/etiqueta antes de tomar mediana para evitar sesgo por alias repetidos
    seen_members = {}
    for member, lbl, val in child_entries:
        key = member.strip().lower() or lbl.strip().lower()
        if key not in seen_members:
            seen_members[key] = float(val)
    return round(float(statistics.median(list(seen_members.values()))), 4)


def sanitize_multiclass_eps_df(df: Optional[pd.DataFrame]) -> Optional[pd.DataFrame]:
    """
    Desambigua e impide la suma espuria multi-clase en `EarningsPerShare*` (p. ej. `GOOGL` bajo
    `us-gaap:StatementClassOfStockAxis` donde herramientas XBRL suman Clase A + Clase B + Clase C).
    Es matemática y contablemente inválida la suma de ratios *per-share* entre clases de acciones.
    """
    if df is None or df.empty or "concept" not in df.columns:
        return df

    tokens = df["concept"].astype(str).apply(_clean_concept_token)
    eps_mask = tokens.isin(_EPS_CONCEPT_TOKENS)
    if not eps_mask.any() or ("dimension" not in df.columns and "dimension_axis" not in df.columns):
        return df

    period_cols = [
        c for c in df.columns
        if c not in _STATEMENT_META_COLS
        and not str(c).startswith(("dim_", "level", "weight"))
    ]
    if not period_cols:
        return df

    is_dim_series = df.apply(_is_dimensional_row, axis=1)
    dim_axis_series = df["dimension_axis"].astype(str) if "dimension_axis" in df.columns else pd.Series("", index=df.index)
    dim_member_series = df["dimension_member"].astype(str) if "dimension_member" in df.columns else pd.Series("", index=df.index)
    label_series = df["label"].astype(str) if "label" in df.columns else pd.Series("", index=df.index)

    is_class_child = is_dim_series & (
        dim_axis_series.str.contains("StatementClassOfStockAxis", case=False, na=False)
        | dim_member_series.str.contains(r"Class[A-Z]|ClassOfStock", case=False, na=False, regex=True)
        | label_series.str.contains(r"\bClass\s+[A-Z]\b", case=False, na=False, regex=True)
    )

    for eps_tok in tokens[eps_mask].unique():
        parent_indices = df.index[(tokens == eps_tok) & (~is_dim_series)].tolist()
        child_indices = df.index[(tokens == eps_tok) & is_class_child].tolist()
        if not parent_indices or len(child_indices) < 2:
            continue

        for col in period_cols:
            child_entries = []
            for c_idx in child_indices:
                v = _safe_float(df.at[c_idx, col])
                if v is not None:
                    child_entries.append((str(dim_member_series.at[c_idx]), str(label_series.at[c_idx]), v))
            non_zero_vals = [v for _, _, v in child_entries if abs(v) > 1e-6]
            if len(non_zero_vals) < 2:
                continue

            child_sum = sum(v for _, _, v in child_entries)
            rep_val = _select_primary_class_eps(child_entries)
            if rep_val is None:
                continue

            for p_idx in parent_indices:
                p_val = _safe_float(df.at[p_idx, col])
                if p_val is None:
                    df.at[p_idx, col] = rep_val
                elif (
                    abs(child_sum) > 1e-6
                    and abs(p_val - child_sum) <= max(0.05, 0.02 * abs(child_sum))
                    and all(abs(v - p_val) > max(0.05, 0.02 * abs(v)) for v in non_zero_vals)
                ):
                    df.at[p_idx, col] = rep_val
                    logger.info(
                        "EPS multi-clase corregido (%s[%s]): %.2f (suma de clases) -> %.2f",
                        eps_tok, col, p_val, rep_val,
                    )
    return df


def _infer_mrq_date(facts_df: pd.DataFrame) -> Optional[Any]:
    """Determina la fecha más reciente de balance (Assets / StockholdersEquity) en Company Facts."""
    asset_matches = facts_df[
        facts_df["concept"].astype(str).str.endswith(":Assets")
        | facts_df["concept"].astype(str).str.endswith(":StockholdersEquity")
    ]
    if not asset_matches.empty:
        return asset_matches["period_end"].dropna().max()
    return facts_df["period_end"].dropna().max()


def _extract_row_values(row: Any, periods: List[str], concept_str: str) -> Dict[str, float]:
    """Extrae valores por período normalizando a positivo los gastos/costos operativos."""
    c_low = concept_str.lower()
    expense_indicators = (
        "costof", "expense", "expenses", "charges", "provisions",
        "recurringcapitalexpenditures", "paymentsforcapitalimprovements",
        "paymentsforpropertyimprovements",
    )
    non_expense_exclusions = (
        "income", "revenue", "gain", "operatingincomeloss",
        "netincomeloss", "profitloss",
    )
    is_expense_concept = (
        any(ind in c_low for ind in expense_indicators)
        and not any(excl in c_low for excl in non_expense_exclusions)
    )
    values = {}
    for p in periods:
        num_val = _safe_float(row.get(p))
        if num_val is not None:
            values[p] = abs(num_val) if is_expense_concept else num_val
    return values


def normalize_fiscal_year(col_name):
    """Convierte '2025-09-27 (FY)' o 'FY 2025' a una etiqueta unificada 'FY2025'."""
    col_str = str(col_name).strip()
    if col_str == "LTM":
        return "LTM"
    m = re.search(r'(\d{4})', col_str)
    if m:
        return f"FY{m.group(1)}"
    return col_str


def _clean_concept_token(c):
    """Limpia prefijos de namespace (us-gaap:, ifrs-full_) y normaliza a minusculas."""
    if not c or pd.isna(c):
        return ""
    s = str(c).strip()
    if ":" in s:
        s = s.split(":")[-1]
    if "_" in s:
        s = s.split("_")[-1]
    return s.lower()


def dataframe_to_concept_dict(df, periods):
    """Convierte un DataFrame con columnas de períodos a un diccionario indexado por concepto US-GAAP."""
    data_by_concept = {}
    if df is None or df.empty:
        return data_by_concept

    valid_periods = [p for p in periods if p in df.columns]
    has_dim_col = "dimension" in df.columns or "dimension_axis" in df.columns
    non_dim_concepts = set()

    # Procesar primero filas no dimensionales para evitar que desgloses de clase/segmento
    # contaminen el diccionario canónico consolidado.
    row_items = list(df.iterrows())
    if has_dim_col:
        row_items.sort(key=lambda item: 1 if _is_dimensional_row(item[1]) else 0)

    for _, row in row_items:
        concept = row.get('concept')
        if not concept or pd.isna(concept) or str(concept) == 'nan':
            continue

        concept_str = str(concept).strip()
        is_dim = _is_dimensional_row(row) if has_dim_col else False
        if is_dim and concept_str in non_dim_concepts:
            continue

        label = str(row.get('label', '')).strip()
        std_concept = str(row.get('standard_concept', '')).strip()
        values = _extract_row_values(row, valid_periods, concept_str)

        depth_val = int(row.get('depth', 0)) if pd.notna(row.get('depth')) else 0
        is_abstract = bool(row.get('is_abstract', False)) if pd.notna(row.get('is_abstract')) else False
        is_total = bool(row.get('is_total', False)) if pd.notna(row.get('is_total')) else False
        section_val = str(row.get('section', '')).strip() if pd.notna(row.get('section')) else ''

        if not is_dim:
            non_dim_concepts.add(concept_str)

        if concept_str not in data_by_concept:
            data_by_concept[concept_str] = {
                "label": label,
                "standard_concept": std_concept if std_concept != 'None' else None,
                "values": values,
                "depth": depth_val,
                "is_abstract": is_abstract,
                "is_total": is_total,
                "section": section_val
            }
        else:
            for p_k, p_v in values.items():
                old_v = data_by_concept[concept_str]["values"].get(p_k)
                if p_v is not None and (old_v is None or (old_v < 1e7 and p_v > 1e7)):
                    data_by_concept[concept_str]["values"][p_k] = p_v
            if not data_by_concept[concept_str].get("label") and label:
                data_by_concept[concept_str]["label"] = label
            if not data_by_concept[concept_str].get("standard_concept") and std_concept and std_concept != 'None':
                data_by_concept[concept_str]["standard_concept"] = std_concept

    return data_by_concept


def get_all_matching_sum(data_by_concept, concept_candidates, period):
    """
    Suma acumulativamente partidas independientes de una categoría contable (ej. adquisiciones M&A
    desglosadas o tramos de deuda/inversiones) evitando duplicar conceptos.
    """
    total = 0.0
    matched = False
    matched_tokens = set()
    for cand in concept_candidates:
        cand_lower = cand.lower().split(':')[-1].split('_')[-1]
        for c_key, c_data in data_by_concept.items():
            if 'abstract' in c_key.lower():
                continue
            k_lower = c_key.lower()
            k_token = k_lower.split(':')[-1].split('_')[-1]
            if (k_token == cand_lower or k_lower == cand_lower) and k_token not in matched_tokens:
                num_val = _safe_float(c_data["values"].get(period))
                if num_val is not None:
                    total += num_val
                    matched = True
                    matched_tokens.add(k_token)
    return total if matched else None


def get_mrq_fact(facts_df, concept_candidates, mrq_date=None):
    """Busca el saldo al cierre del trimestre más reciente (MRQ / LTM Balance Sheet) en Company Facts."""
    if facts_df is None or facts_df.empty:
        return None
    if mrq_date is None:
        mrq_date = _infer_mrq_date(facts_df)

    concepts_tokens = facts_df['concept'].astype(str).str.split(':').str[-1].str.split('_').str[-1].str.lower()
    for cand in concept_candidates:
        cand_lower = cand.lower()
        matches = facts_df[(facts_df['period_end'] == mrq_date) & (concepts_tokens == cand_lower)]
        if not matches.empty:
            num_val = _safe_float(matches.iloc[-1].get('numeric_value'))
            if num_val is not None:
                return num_val
    return None


def get_mrq_fact_sum(facts_df, concept_candidates, mrq_date=None):
    """Suma acumulativamente conceptos en facts_df al cierre de MRQ (ej. deuda corriente + valores negociables)."""
    if facts_df is None or facts_df.empty:
        return None
    if mrq_date is None:
        mrq_date = _infer_mrq_date(facts_df)

    concepts_tokens = facts_df['concept'].astype(str).str.split(':').str[-1].str.split('_').str[-1].str.lower()
    total = 0.0
    matched = False
    matched_tokens = set()
    for cand in concept_candidates:
        cand_lower = cand.lower().split(':')[-1].split('_')[-1]
        matches = facts_df[(facts_df['period_end'] == mrq_date) & (concepts_tokens == cand_lower)]
        if not matches.empty and cand_lower not in matched_tokens:
            num_val = _safe_float(matches.iloc[-1].get('numeric_value'))
            if num_val is not None:
                total += num_val
                matched = True
                matched_tokens.add(cand_lower)
    return total if matched else None


def get_ltm_quarterly_metric(facts_df, concept_candidates, mode='sum'):
    """Calcula una métrica LTM (suma o promedio ponderado de 4 trimestres consecutivos) vía Company Facts."""
    if facts_df is None or facts_df.empty:
        return None
    concepts_series = facts_df['concept'].astype(str)
    concepts_tokens = concepts_series.str.split(':').str[-1].str.split('_').str[-1].str.lower()

    for cand in concept_candidates:
        cand_lower = cand.lower()
        sub = facts_df[concepts_tokens == cand_lower].copy()
        if sub.empty:
            continue

        start_col = 'period_start' if 'period_start' in sub.columns else ('start' if 'start' in sub.columns else None)
        end_col = 'period_end' if 'period_end' in sub.columns else ('end' if 'end' in sub.columns else None)
        if not start_col or not end_col:
            continue

        sub['p_start'] = pd.to_datetime(sub[start_col], errors='coerce')
        sub['p_end'] = pd.to_datetime(sub[end_col], errors='coerce')
        sub['days'] = (sub['p_end'] - sub['p_start']).dt.days
        sub['num_val'] = pd.to_numeric(sub['numeric_value'], errors='coerce')
        sub = sub.dropna(subset=['p_end', 'num_val'])

        q_rows = sub[(sub['days'] >= 60) & (sub['days'] <= 115)].sort_values('p_end')
        q_rows = q_rows.drop_duplicates(subset=['p_end'], keep='last')

        fy_rows = sub[(sub['days'] >= 330) & (sub['days'] <= 380)].sort_values('p_end')
        ytd9_rows = sub[(sub['days'] >= 240) & (sub['days'] <= 300)].sort_values('p_end')

        derived_q4s = []
        for _, fy_r in fy_rows.iterrows():
            fy_end = fy_r['p_end']
            fy_val = fy_r['num_val']
            matching_9m = ytd9_rows[(ytd9_rows['p_start'] == fy_r['p_start']) & (ytd9_rows['p_end'] < fy_end)]
            if not matching_9m.empty:
                ytd_val = matching_9m.iloc[-1]['num_val']
                q4_val = (4.0 * fy_val - 3.0 * ytd_val) if mode == 'avg' else (fy_val - ytd_val)
                if fy_end not in q_rows['p_end'].values:
                    derived_q4s.append({'p_end': fy_end, 'num_val': q4_val, 'days': 90})

        if derived_q4s:
            q_rows = pd.concat([q_rows, pd.DataFrame(derived_q4s)], ignore_index=True).sort_values('p_end')
            q_rows = q_rows.drop_duplicates(subset=['p_end'], keep='last')

        last_4 = q_rows.tail(4)
        if len(last_4) == 4:
            span = (last_4.iloc[-1]['p_end'] - last_4.iloc[0]['p_end']).days
            if 250 <= span <= 300:
                if mode == 'avg':
                    return float(last_4['num_val'].mean())
                return round(float(last_4['num_val'].sum()), 2)
    return None


def get_fact_fallback(facts_df, concept_candidates, fy_str, is_flow=False):
    """Busca una partida en Company Facts como respaldo si no figura en el estado multi-período."""
    if facts_df is None or facts_df.empty:
        return None
    if fy_str == "LTM":
        if is_flow:
            if any("earningspershare" in c.lower() or "eps" in c.lower() for c in concept_candidates):
                return get_ltm_quarterly_metric(facts_df, concept_candidates, mode='sum')
            return None
        if any("shares" in c.lower() for c in concept_candidates):
            avg_sh = get_ltm_quarterly_metric(facts_df, concept_candidates, mode='avg')
            if avg_sh is not None:
                return avg_sh
        return get_mrq_fact(facts_df, concept_candidates)

    year_digits = ''.join(filter(str.isdigit, fy_str))
    if not year_digits:
        return None
    fy_int = int(year_digits)

    concepts_tokens = facts_df['concept'].astype(str).str.split(':').str[-1].str.split('_').str[-1].str.lower()
    p_end_year = facts_df['period_end'].astype(str).str[:4]

    for cand in concept_candidates:
        cand_lower = cand.lower()
        matches = facts_df[(p_end_year == str(fy_int)) & (concepts_tokens == cand_lower)]
        if matches.empty:
            matches = facts_df[(facts_df['fiscal_year'] == fy_int) & (concepts_tokens == cand_lower)]

        if not matches.empty:
            fy_matches = matches[matches['fiscal_period'].astype(str).str.upper() == 'FY']
            chosen_subset = fy_matches if not fy_matches.empty else matches

            if is_flow:
                start_col = next((c for c in ('period_start', 'start') if c in chosen_subset.columns), None)
                end_col = next((c for c in ('period_end', 'end') if c in chosen_subset.columns), None)
                if start_col and end_col:
                    try:
                        starts = pd.to_datetime(chosen_subset[start_col], errors='coerce')
                        ends = pd.to_datetime(chosen_subset[end_col], errors='coerce')
                        durations = (ends - starts).dt.days
                        long_subset = chosen_subset[durations >= 300]
                        if not long_subset.empty:
                            chosen_subset = long_subset
                    except (ValueError, TypeError) as exc:
                        logger.debug("No se pudo filtrar duración anual para %s (%s): %s", cand, fy_str, exc)

            for f_col in ('filed', 'filing_date'):
                if f_col in chosen_subset.columns:
                    chosen_subset = chosen_subset.sort_values(f_col)
                    break
            num_val = _safe_float(chosen_subset.iloc[-1].get('numeric_value'))
            if num_val is not None:
                return num_val
    return None


def detect_global_doc_scale(html_content):
    """
    Nivel 2: Salvaguarda Global del Documento.
    Detecta si los estados financieros declaran a nivel general que las cifras
    están expresadas en miles ('in thousands of u.s. dollars') o millones.
    """
    if not html_content:
        return 1.0
    clean_sample = re.sub(r'\s+', ' ', str(html_content)[:150000].lower())

    millions_patterns = (
        "in millions of u.s. dollars", "(in millions of u.s. dollars",
        "in millions of us dollars", "(in millions of us dollars",
        "in millions of dollars", "(in millions of dollars",
        "amounts in millions", "(in millions)", "stated in millions",
    )
    thousands_patterns = (
        "in thousands of u.s. dollars", "(in thousands of u.s. dollars",
        "in thousands of us dollars", "(in thousands of us dollars",
        "in thousands of dollars", "(in thousands of dollars",
        "amounts in thousands", "(in thousands)", "stated in thousands",
    )

    if any(m in clean_sample for m in millions_patterns):
        return 1_000_000.0
    if any(t in clean_sample for t in thousands_patterns):
        return 1_000.0
    return 1.0


def get_preceding_html_context(html_content, table, window_size=2500):
    """
    Nivel 1: Contexto Precedente a Cada Tabla.
    Extrae el bloque de texto HTML (hasta window_size caracteres) inmediatamente anterior
    a la apertura de la etiqueta <table> correspondiente a la tabla dada.
    """
    if not html_content or table is None:
        return ""
    try:
        lower_html = html_content.lower()
        for r_idx in range(min(6, len(table))):
            for c_idx in range(min(3, table.shape[1])):
                cell_val = str(table.iloc[r_idx, c_idx]).strip()
                if len(cell_val) >= 5 and cell_val.lower() not in ('none', 'nan', 'null', 'total', 'assets', 'equity', 'period', 'three', 'six', 'nine'):
                    pos = lower_html.find(cell_val.lower())
                    if pos != -1:
                        tbl_tag_pos = lower_html.rfind('<table', max(0, pos - 6000), pos)
                        target_pos = tbl_tag_pos if tbl_tag_pos != -1 else pos
                        start_pos = max(0, target_pos - window_size)
                        return html_content[start_pos:target_pos]
    except (IndexError, AttributeError, TypeError) as exc:
        logger.debug("No se pudo extraer contexto HTML precedente de tabla: %s", exc)
    return ""


def detect_table_scale_factor(table, doc_context="", preceding_html=""):
    """
    Detecta dinámicamente si los números en una tabla de reporte financiero (ej. 6-K HTML)
    están expresados en miles ('in thousands'), millones ('in millions') o unidades directas/base.
    Prioriza el contexto HTML inmediatamente precedente a la apertura de la tabla.
    """
    sample_parts = []
    if preceding_html:
        sample_parts.append(str(preceding_html).lower())
    if table is not None:
        try:
            sample_parts.append(' '.join(table.iloc[:5, :].astype(str).values.flatten()).lower())
        except (IndexError, AttributeError, TypeError) as exc:
            logger.debug("No se pudo leer cabecera de tabla para detectar escala: %s", exc)
    if doc_context:
        sample_parts.append(str(doc_context)[:25000].lower())

    clean_sample = re.sub(r'\s+', ' ', ' '.join(sample_parts))

    if any(k in clean_sample for k in (
        "in millions", "in million", "$ in millions", "$ in million",
        "(in millions", "(in million", "stated in millions", "amounts in millions",
    )):
        return 1_000_000.0
    if any(k in clean_sample for k in (
        "in thousands", "in thousand", "$ in thousands", "$ in thousand",
        "(in thousands", "(in thousand", "stated in thousands", "amounts in thousands",
    )):
        return 1_000.0
    if any(k in clean_sample for k in ("in billions", "in billion", "(in billions")):
        return 1_000_000_000.0
    return 1.0


def _clean_6k_val(v: Any) -> Optional[float]:
    """Parsea celdas numéricas HTML de formularios 6-K (`$`, paréntesis negativos, comas)."""
    if pd.isna(v):
        return None
    s = str(v).replace('$', '').replace(',', '').replace(' ', '').replace('(', '-').replace(')', '').strip()
    return _safe_float(s)


def _clean_6k_text(s: Any) -> str:
    """Normaliza etiquetas HTML 6-K a texto minúsculo alfanumérico."""
    cleaned = re.sub(r'[^a-zA-Z0-9\s]', ' ', str(s).lower())
    return re.sub(r'\s+', ' ', cleaned).strip()


def _find_interim_ytd_columns(tbl, curr_yr: int, prev_yr: int, fallback_curr: int, fallback_prev: Optional[int]):
    """Localiza índices de columna YTD actual y comparativo anterior en tablas 6-K."""
    for dur_kw in ('nine', '9', 'six', '6', 'three', '3'):
        c_curr, c_prev = None, None
        for c_idx in range(tbl.shape[1]):
            col_hdr = ' '.join(tbl.iloc[:4, c_idx].astype(str).tolist()).lower()
            if dur_kw in col_hdr:
                if str(curr_yr) in col_hdr and c_curr is None:
                    c_curr = c_idx
                elif str(prev_yr) in col_hdr and c_prev is None:
                    c_prev = c_idx
        if c_curr is not None and c_prev is not None:
            return c_curr, c_prev

    c_curr, c_prev = None, None
    for c_idx in range(tbl.shape[1]):
        col_hdr = ' '.join(tbl.iloc[:4, c_idx].astype(str).tolist()).lower()
        if str(curr_yr) in col_hdr and c_curr is None:
            c_curr = c_idx
        elif str(prev_yr) in col_hdr and c_prev is None:
            c_prev = c_idx
    if c_curr is not None:
        return c_curr, c_prev

    resolved_prev = fallback_prev if (fallback_prev is not None and tbl.shape[1] > fallback_prev) else (
        fallback_curr + 1 if tbl.shape[1] > fallback_curr + 1 else None
    )
    return fallback_curr, resolved_prev


def _match_6k_rows_three_pass(
    df: pd.DataFrame,
    interim_items: List[tuple],
    synonym_groups: List[tuple],
    master_groups: Optional[List[tuple]] = None,
    enforce_total_parity: bool = False,
) -> Dict[Any, tuple]:
    """Empareja filas IFRS/US-GAAP con ítems extraídos de tablas 6-K en 3 pasadas (exacto, sinónimos, subcadena)."""
    matched: Dict[Any, tuple] = {}
    used_indices = set()

    for idx, row in df.iterrows():
        c_name = str(row.get('concept', ''))
        if 'abstract' in c_name.lower():
            continue
        l_clean = _clean_6k_text(row.get('label', ''))
        for item_idx, item in enumerate(interim_items):
            if item_idx in used_indices:
                continue
            if l_clean == item[0]:
                used_indices.add(item_idx)
                matched[idx] = item
                break

    for idx, row in df.iterrows():
        if idx in matched:
            continue
        c_name = str(row.get('concept', ''))
        if 'abstract' in c_name.lower():
            continue
        c_tok = c_name.split(':')[-1].split('_')[-1].lower()
        l_clean = _clean_6k_text(row.get('label', ''))

        m_found = False
        if master_groups:
            for c_syns, tbl_syns in master_groups:
                if c_tok in c_syns:
                    for ts in tbl_syns:
                        for item_idx, item in enumerate(interim_items):
                            if item_idx in used_indices:
                                continue
                            if item[0] == ts or ts in item[0]:
                                used_indices.add(item_idx)
                                matched[idx] = item
                                m_found = True
                                break
                        if m_found:
                            break
                if m_found:
                    break
        if m_found:
            continue

        for c_syns, tbl_syns in synonym_groups:
            if any(cs == c_tok or cs in c_tok or cs in l_clean for cs in c_syns):
                for ts in tbl_syns:
                    for item_idx, item in enumerate(interim_items):
                        if item_idx in used_indices:
                            continue
                        if enforce_total_parity and ('total' in item[0]) != ('total' in l_clean):
                            continue
                        match_ok = (item[0] == ts) if enforce_total_parity else (item[0] == ts or ts in item[0])
                        if match_ok:
                            used_indices.add(item_idx)
                            matched[idx] = item
                            m_found = True
                            break
                    if m_found:
                        break
            if m_found:
                break

    for idx, row in df.iterrows():
        if idx in matched:
            continue
        c_name = str(row.get('concept', ''))
        if 'abstract' in c_name.lower():
            continue
        c_tok = c_name.split(':')[-1].split('_')[-1].lower()
        l_clean = _clean_6k_text(row.get('label', ''))
        for item_idx, item in enumerate(interim_items):
            if item_idx in used_indices:
                continue
            lbl = item[0]
            if enforce_total_parity and ('total' in lbl) != ('total' in l_clean):
                continue
            if (len(lbl) > 8 and (lbl in l_clean or l_clean in lbl)) or (c_tok == lbl.replace(' ', '')):
                used_indices.add(item_idx)
                matched[idx] = item
                break

    return matched


_BS_6K_SYNONYMS = [
    (['deferredtaxassets'], ['deferred tax assets']),
    (['rightofuseassets', 'operatingleaserightofuse'], ['right of use assets']),
    (['intangibleassetsotherthangoodwill', 'intangibleassets'], ['intangible assets']),
    (['otherreceivables'], ['other receivables']),
    (['otherassets'], ['other assets']),
    (['otherliabilities'], ['other liabilities']),
    (['issuedcapital'], ['share capital']),
    (['sharepremium'], ['share premium reserve']),
    (['accumulatedothercomprehensiveincome'], ['other comprehensive income loss']),
    (['noncontrollinginterests'], ['equity attributable to non controlling interests']),
    (['deposits', 'depositsfromcustomers'], ['deposits']),
    (['payablestonetwork'], ['payables to network']),
    (['borrowingsandfinancing', 'longtermdebt'], ['borrowings and financing']),
    (['repurchaseagreements', 'shorttermdebt'], ['repurchase agreements']),
    (['salariesallowances'], ['salaries allowances and social security contributions']),
    (['taxliabilities'], ['tax liabilities']),
    (['leaseliabilities'], ['lease liabilities']),
    (['provisionsandcontingentliabilities'], ['provisions and contingent liabilities']),
    (['deferredincome'], ['deferred income']),
    (['loanstocustomers'], ['loans to customers']),
    (['creditcardreceivables'], ['credit card receivables']),
    (['compulsorydeposits'], ['compulsory and other deposits at central banks']),
    (['investmentsinassociates'], ['investments in associates']),
    (['propertyplantandequipment'], ['property plant and equipment']),
    (['cashandcashequivalents'], ['cash and cash equivalents']),
    (['assets', 'totalassets'], ['total assets', 'assets']),
    (['equity', 'totalequity'], ['total equity', 'total shareholders equity', 'total stockholders equity']),
    (['liabilities', 'totalliabilities'], ['total liabilities']),
    (['liabilitiesandequity', 'totalliabilitiesandequity'], ['total liabilities and equity']),
]

_CF_6K_MASTER_TOTALS = [
    (['cashflowsfromusedinoperatingactivities', 'cashflowsfromoperatingactivities', 'netcashprovidedbyusedinoperatingactivities'],
     ['cash flows generated from used in operating activities', 'cash flows from operating activities', 'net cash generated from used in operating activities']),
    (['cashflowsfromusedininvestingactivities', 'cashflowsfrominvestingactivities', 'netcashprovidedbyusedininvestingactivities'],
     ['cash flow generated from used in investing activities', 'cash flows in investing activities', 'cash flows from investing activities']),
    (['cashflowsfromusedinfinancingactivities', 'cashflowsfromfinancingactivities', 'netcashprovidedbyusedinfinancingactivities'],
     ['cash flows generated from used in financing activities', 'cash flows in financing activities', 'cash flows from financing activities']),
    (['increasedecreaseincashandcashequivalents', 'netchangeincash', 'changeincashandcashequivalents'],
     ['change in cash and cash equivalents', 'increase decrease in cash and cash equivalents']),
    (['cashandcashequivalents'],
     ['cash and cash equivalents end of the period', 'cash and cash equivalents end of the year']),
]

_CF_6K_SYNONYMS = [
    (['profitlossfromcontinuingoperations', 'profitloss', 'netincome'], ['net income for the period', 'profit loss for the period', 'net income for the year', 'profit for the period']),
    (['depreciation', 'amortisation', 'amortization'], ['depreciation and amortization']),
    (['expectedcreditloss', 'creditloss', 'creditlossallowance'], ['expected credit loss']),
    (['deferredtax', 'deferredincometax', 'deferredtaxexpense'], ['deferred income taxes']),
    (['provisionsandcontingentliabilities', 'provisions'], ['provisions and contingent liabilities']),
    (['unrealizedgain', 'unrealizedloss', 'unrealizedlosses'], ['unrealized gains losses on financial instruments']),
    (['interestaccrued', 'accruedinterest'], ['interest accrued']),
    (['sharebased', 'stockcompensation'], ['share based compensation']),
    (['shareoflossinassociates', 'lossinassociates'], ['share of loss in associates']),
    (['operatingsecurities'], ['securities']),
    (['creditcardreceivables', 'cardreceivables'], ['credit card receivables']),
    (['loanstocustomers'], ['loans to customers']),
    (['compulsorydeposits'], ['compulsory and other deposits at central banks']),
    (['depositstocustomers', 'depositsfromcustomers', 'depositliabilities'], ['deposits']),
    (['payablestonetwork', 'networkpayables'], ['payables to network']),
    (['deferredincome'], ['deferred income']),
    (['otherliabilities'], ['other liabilities']),
    (['interestpaid'], ['interest paid']),
    (['incometaxpaid'], ['income tax paid']),
    (['interestreceived'], ['interest received']),
    (['propertyplantandequipment', 'propertyplantequipment'], ['acquisition of property plant and equipment']),
    (['intangibleassets', 'acquisitionanddevelopmentofintangible'], ['acquisition and development of intangible assets']),
    (['proceedsfromborrowings'], ['proceeds from borrowings and financing']),
    (['paymentsfromborrowings', 'paymentsofborrowings', 'repaymentsofborrowings'], ['payments of borrowings and financing']),
    (['repurchaseofshares', 'sharesrepurchased', 'treasuryshares'], ['repurchase of shares']),
    (['stockoptions', 'exerciseofstockoptions'], ['exercise of stock options']),
    (['leasepayments'], ['lease payments']),
    (['effectofexchangerate', 'foreignexchangerate'], ['foreign exchange rate changes on cash and cash equivalents']),
    (['cashandcashequivalentsatbeginning', 'cashbeginning'], ['cash and cash equivalents beginning of the period']),
]


def _extract_6k_ecl_ltm(tables, bal_df, latest_fy: str, curr_yr: int, prev_yr: int, calib_factor: float) -> None:
    """Extrae e inyecta provisiones acumuladas / ECL desde notas de cobertura en Form 6-K."""
    def _is_ecl_row(r_concept, r_label):
        c_low = str(r_concept or '').lower()
        l_low = str(r_label or '').lower()
        if any(ex in l_low or ex in c_low for ex in ('salar', 'social security', 'remuneration', 'employee')):
            return False
        if any(k.lower() in c_low for k in BANKING_TAXONOMY_MAP.get("allowance_for_credit_losses", [])):
            return True
        return ('credit' in l_low or 'loan' in l_low or 'financing' in l_low) and ('loss' in l_low or 'allowance' in l_low or 'expected' in l_low)

    has_ltm_allowance = 'LTM' in bal_df.columns and any(
        _is_ecl_row(r.get('concept'), r.get('label')) and (_safe_float(r.get('LTM')) or 0.0) > 1e7
        for _, r in bal_df.iterrows()
    )
    if has_ltm_allowance:
        return

    ecl_ltm_sum, ecl_prev_sum = 0.0, 0.0
    for t in tables:
        t_clean = ' '.join(' '.join(t.astype(str).values.flatten()).split()).lower()
        if 'expected credit loss' in t_clean and ('coverage ratio' in t_clean or 'gross exposures' in t_clean) and 'stage 1' in t_clean:
            r3_lbl = ' '.join(str(t.iloc[3, 0]).split()).lower() if len(t) > 3 else ''
            if 'stage 1' not in r3_lbl:
                continue
            c_ltm_ecl, c_prev_ecl = None, None
            for c in range(t.shape[1]):
                h_date = ' '.join(str(t.iloc[0, c]).split()).lower()
                h_hdr = ' '.join(str(t.iloc[1, c]).split()).lower()
                if 'expected credit loss' in h_hdr and '%' not in h_hdr:
                    if str(curr_yr) in h_date and c_ltm_ecl is None:
                        c_ltm_ecl = c
                    elif str(prev_yr) in h_date and c_prev_ecl is None:
                        c_prev_ecl = c
            if c_ltm_ecl is not None:
                for r in range(len(t)):
                    lbl = ' '.join(str(t.iloc[r, 0]).split()).lower()
                    if any(st in lbl for st in ('stage 1', 'stage 2', 'stage 3')):
                        v1 = _safe_float(re.sub(r'[^\d.]', '', str(t.iloc[r, c_ltm_ecl])))
                        if v1 is not None:
                            ecl_ltm_sum += v1
                        if c_prev_ecl is not None:
                            v2 = _safe_float(re.sub(r'[^\d.]', '', str(t.iloc[r, c_prev_ecl])))
                            if v2 is not None:
                                ecl_prev_sum += v2

    if ecl_ltm_sum <= 0:
        return
    scale = calib_factor if calib_factor > 1.0 else 1000.0
    allow_indices = [
        i for i, r in bal_df.iterrows()
        if str(r.get('concept', '')).strip() in (
            'AllowanceAccountForCreditLossesOfFinancialAssets',
            'FinancingReceivableAllowanceForCreditLosses',
        )
    ]
    if allow_indices:
        for idx in allow_indices:
            bal_df.at[idx, 'LTM'] = ecl_ltm_sum * scale
            if latest_fy in bal_df.columns and ecl_prev_sum > 0:
                bal_df.at[idx, latest_fy] = ecl_prev_sum * scale
            bal_df.at[idx, 'label'] = 'Allowance for expected credit losses'
            bal_df.at[idx, 'standard_concept'] = 'FinancingReceivableAllowanceForCreditLosses'
    else:
        new_row = {
            'concept': 'AllowanceAccountForCreditLossesOfFinancialAssets',
            'label': 'Allowance for expected credit losses',
            'standard_concept': 'FinancingReceivableAllowanceForCreditLosses',
            'LTM': ecl_ltm_sum * scale,
        }
        if latest_fy in bal_df.columns and ecl_prev_sum > 0:
            new_row[latest_fy] = ecl_prev_sum * scale
        _append_rows_safely(bal_df, [new_row])


def _find_6k_is_match(interim_is: List[tuple], c_name: str, l_name: str):
    """Empareja una fila de Income Statement contra partidas extraídas de un 6-K."""
    c_clean = _clean_6k_text(c_name)
    l_clean = _clean_6k_text(l_name)
    for lbl, vc, vp in interim_is:
        if l_clean == lbl:
            return lbl, vc, vp
    if 'incometax' in c_clean and 'before' not in c_clean and 'before' not in l_clean:
        for lbl, vc, vp in interim_is:
            if lbl == 'income taxes':
                return lbl, vc, vp
    if 'interest' in c_clean and 'expense' in c_clean:
        for lbl, vc, vp in interim_is:
            if 'interest' in lbl and 'expense' in lbl:
                return lbl, vc, vp
    if 'profitlossbeforetax' in c_clean or 'before income taxes' in l_clean:
        for lbl, vc, vp in interim_is:
            if 'before income taxes' in lbl:
                return lbl, vc, vp
    if ('netincome' in c_clean or 'profitloss' in c_clean) and 'attributable' not in c_clean and 'noncontrolling' not in c_clean:
        if 'period' in l_clean or 'year' in l_clean or l_clean == 'net income':
            for lbl, vc, vp in interim_is:
                if 'net income for the period' in lbl:
                    return lbl, vc, vp

    is_eps = any(w in l_clean or w in c_clean for w in ('pershare', 'per share', 'eps', 'earnings per share'))
    is_shares = ('share' in l_clean or 'share' in c_clean or 'weightedaverageshares' in c_clean) and not is_eps
    is_diluted_shares = is_shares and ('diluted' in l_clean or 'diluted' in c_clean or 'adjustedaverageweightedshares' in c_clean)
    is_basic_shares = is_shares and not is_diluted_shares
    is_diluted_eps = is_eps and ('diluted' in c_clean or 'diluted' in l_clean)
    is_basic_eps = is_eps and not is_diluted_eps

    if is_diluted_shares:
        for lbl, vc, vp in interim_is:
            if 'weighted average' in lbl and 'diluted' in lbl:
                return lbl, vc, vp
    elif is_basic_shares:
        for lbl, vc, vp in interim_is:
            if 'weighted average' in lbl and ('basic' in lbl or 'diluted' not in lbl):
                return lbl, vc, vp
    elif is_diluted_eps:
        for lbl, vc, vp in interim_is:
            if 'earnings per share' in lbl and 'diluted' in lbl:
                return lbl, vc, vp
    elif is_basic_eps:
        for lbl, vc, vp in interim_is:
            if 'earnings per share' in lbl and ('basic' in lbl or 'diluted' not in lbl):
                return lbl, vc, vp

    for lbl, vc, vp in interim_is:
        if len(lbl) > 8 and (lbl in l_clean or l_clean in lbl):
            return lbl, vc, vp
    return None, None, None


def extract_6k_fpi_interim(company, annual_fys, latest_fy, inc_df, bal_df, cf_df=None, filing_context=None):
    """
    Parsea los estados financieros interinos de Form 6-K para Foreign Private Issuers
    y calcula el período LTM acumulado mediante la identidad móvil:
    LTM = FY_latest - Interino_prev + Interino_curr
    """
    try:
        f_list = filing_context.get_filings(form='6-K') if filing_context else company.get_filings(form='6-K')
        cand_filings = [f for f in f_list if any(k in str(getattr(f, 'primary_document', '')).lower() for k in ('nufs', 'financial', 'statement', 'interim'))]
        if not cand_filings:
            cand_filings = f_list[:8]

        for filing in cand_filings:
            try:
                html_content = filing.html()
                if not html_content or len(html_content) < 50000:
                    continue
                tables = pd.read_html(io.StringIO(html_content))
                is_tbl = bs_a_tbl = bs_l_tbl = cf_o_tbl = cf_i_tbl = cf_f_tbl = None

                for t in tables[:35]:
                    t_str = re.sub(r'\s+', ' ', ' '.join(t.astype(str).values.flatten()).lower())
                    if 'fee and commission income' in t_str and 'gross profit' in t_str and is_tbl is None:
                        is_tbl = t
                    if 'cash and cash equivalents' in t_str and 'total assets' in t_str and bs_a_tbl is None:
                        bs_a_tbl = t
                    if 'deposits' in t_str and 'total liabilities and equity' in t_str and bs_l_tbl is None:
                        bs_l_tbl = t
                    if 'cash flows from operating activities' in t_str and cf_o_tbl is None:
                        cf_o_tbl = t
                    if ('cash flows in investing activities' in t_str or 'investing activities' in t_str) and cf_i_tbl is None:
                        cf_i_tbl = t
                    if ('cash flows from financing activities' in t_str or 'financing activities' in t_str) and cf_f_tbl is None:
                        cf_f_tbl = t

                if is_tbl is None or bs_a_tbl is None or bs_l_tbl is None:
                    continue

                doc_scale = detect_global_doc_scale(html_content)
                cf_tbl_ref = cf_o_tbl if cf_o_tbl is not None else (cf_i_tbl if cf_i_tbl is not None else cf_f_tbl)
                is_scale = detect_table_scale_factor(is_tbl, preceding_html=get_preceding_html_context(html_content, is_tbl))
                bs_scale = detect_table_scale_factor(bs_a_tbl, preceding_html=get_preceding_html_context(html_content, bs_a_tbl))
                cf_scale = detect_table_scale_factor(cf_tbl_ref, preceding_html=get_preceding_html_context(html_content, cf_tbl_ref))
                if doc_scale > 1.0:
                    is_scale = doc_scale if is_scale == 1.0 else is_scale
                    bs_scale = doc_scale if bs_scale == 1.0 else bs_scale
                    cf_scale = doc_scale if cf_scale == 1.0 else cf_scale
                print(f"[SEC Extractor] Escalas 6-K detectadas: IS={is_scale}, BS={bs_scale}, CF={cf_scale} (Doc Global={doc_scale})")

                all_years_is = [
                    int(y)
                    for c_idx in range(is_tbl.shape[1])
                    for y in re.findall(r'\b(20\d\d)\b', ' '.join(is_tbl.iloc[:4, c_idx].astype(str).tolist()))
                ]
                curr_yr = max(all_years_is) if all_years_is else datetime.now().year
                prev_yr = curr_yr - 1

                col_curr_is, col_prev_is = _find_interim_ytd_columns(
                    is_tbl, curr_yr, prev_yr,
                    fallback_curr=7 if is_tbl.shape[1] > 7 else 3,
                    fallback_prev=9 if is_tbl.shape[1] > 9 else None,
                )
                interim_is = []
                for _, r in is_tbl.iterrows():
                    vc = _clean_6k_val(r[col_curr_is])
                    if vc is not None:
                        vp = _clean_6k_val(r[col_prev_is]) if col_prev_is is not None else None
                        interim_is.append((_clean_6k_text(r[0]), vc * is_scale, (vp * is_scale) if vp is not None else 0.0))

                if 'LTM' not in inc_df.columns and latest_fy in inc_df.columns:
                    ltm_col = []
                    for _, row in inc_df.iterrows():
                        concept, label = str(row.get('concept', '')), str(row.get('label', ''))
                        fy_val = _safe_float(row.get(latest_fy))
                        val = None
                        m_lbl, vc, vp = _find_6k_is_match(interim_is, concept, label)
                        if m_lbl and fy_val is not None:
                            if 'weighted average' in m_lbl or 'shares' in concept.lower():
                                val = vc
                            elif 'earnings per share' in m_lbl or 'pershare' in concept.lower():
                                val = round(fy_val - vp + vc, 4) if (vp is not None and vc is not None) else fy_val
                            else:
                                val = fy_val - vp + vc
                        ltm_col.append(val)
                    inc_df.insert(inc_df.columns.get_loc(latest_fy), 'LTM', ltm_col)

                interim_bs = []
                for b_tbl in (bs_a_tbl, bs_l_tbl):
                    col_bs_date = next(
                        (c_idx for c_idx in range(b_tbl.shape[1]) if str(curr_yr) in ' '.join(b_tbl.iloc[:3, c_idx].astype(str).tolist()).lower()),
                        3 if b_tbl.shape[1] > 3 else (1 if b_tbl.shape[1] > 1 else 0),
                    )
                    for _, r in b_tbl.iterrows():
                        v = _clean_6k_val(r[col_bs_date])
                        if v is not None:
                            interim_bs.append((_clean_6k_text(r[0]), v * bs_scale))

                fy_assets = next(
                    (_safe_float(r.get(latest_fy)) for _, r in bal_df.iterrows()
                     if 'abstract' not in str(r.get('concept', '')).lower()
                     and (str(r.get('concept', '')).lower().endswith('assets') or str(r.get('label', '')).lower() in ('assets', 'total assets'))
                     and (_safe_float(r.get(latest_fy)) or 0.0) > 0),
                    None,
                )
                interim_assets = next((float(v) for lbl, v in interim_bs if lbl in ('total assets', 'assets') and v is not None and v > 0), None)
                calib_factor = 1.0
                if fy_assets and interim_assets:
                    ratio = fy_assets / interim_assets
                    if 700.0 <= ratio <= 1300.0:
                        calib_factor = 1000.0
                    elif 700_000.0 <= ratio <= 1_300_000.0:
                        calib_factor = 1_000_000.0
                    if calib_factor > 1.0:
                        print(f"[SEC Extractor] Calibración de escala 6-K aplicada (ratio FY_latest/interino = {ratio:.1f}): multiplicando balance interino por {calib_factor:.0f}x")
                        interim_bs = [(lbl, v * calib_factor) for lbl, v in interim_bs]
                        cf_scale = max(cf_scale, calib_factor)

                matched_bs = _match_6k_rows_three_pass(bal_df, interim_bs, _BS_6K_SYNONYMS, enforce_total_parity=True)
                if 'LTM' not in bal_df.columns and latest_fy in bal_df.columns:
                    bal_df.insert(bal_df.columns.get_loc(latest_fy), 'LTM', [matched_bs.get(idx, (None, None))[1] for idx in bal_df.index])

                _extract_6k_ecl_ltm(tables, bal_df, latest_fy, curr_yr, prev_yr, calib_factor)

                if cf_df is not None and 'LTM' not in cf_df.columns and latest_fy in cf_df.columns:
                    active_cf_tbl = cf_o_tbl if cf_o_tbl is not None else cf_i_tbl
                    if active_cf_tbl is not None:
                        col_curr_cf, col_prev_cf = _find_interim_ytd_columns(
                            active_cf_tbl, curr_yr, prev_yr,
                            fallback_curr=3 if active_cf_tbl.shape[1] > 3 else 1,
                            fallback_prev=5 if active_cf_tbl.shape[1] > 5 else None,
                        )
                    else:
                        col_curr_cf, col_prev_cf = 1, None

                    interim_cf, seen_tbl_ids = [], set()
                    for tbl in (cf_o_tbl, cf_i_tbl, cf_f_tbl):
                        if tbl is not None and id(tbl) not in seen_tbl_ids:
                            seen_tbl_ids.add(id(tbl))
                            for _, r in tbl.iterrows():
                                vc = _clean_6k_val(r[col_curr_cf]) if (col_curr_cf is not None and col_curr_cf < tbl.shape[1]) else None
                                vp = _clean_6k_val(r[col_prev_cf]) if (col_prev_cf is not None and col_prev_cf < tbl.shape[1]) else None
                                if vc is not None or vp is not None:
                                    interim_cf.append((_clean_6k_text(r[0]), (vc or 0.0) * cf_scale, (vp or 0.0) * cf_scale))

                    matched_cf = _match_6k_rows_three_pass(cf_df, interim_cf, _CF_6K_SYNONYMS, master_groups=_CF_6K_MASTER_TOTALS)
                    ltm_cf_col, rep_matched_in_cf = [], False
                    for idx, row in cf_df.iterrows():
                        fy_val = _safe_float(row.get(latest_fy))
                        val = None
                        if idx in matched_cf:
                            m_lbl, vc, vp = matched_cf[idx]
                            if any(k in m_lbl for k in ('cash and cash equivalents end', 'end of the period')):
                                val = vc
                            elif any(k in m_lbl for k in ('repurchase of shares', 'shares repurchased')):
                                rep_matched_in_cf = True
                                val = (fy_val - (vp or 0.0) + (vc or 0.0)) if (fy_val is not None and fy_val != 0.0) else vc
                            elif fy_val is not None:
                                val = fy_val - (vp or 0.0) + (vc or 0.0)
                            else:
                                val = vc
                        ltm_cf_col.append(val)
                    cf_df.insert(cf_df.columns.get_loc(latest_fy), 'LTM', ltm_cf_col)

                    rep_item = next((item for item in interim_cf if 'repurchase of shares' in item[0]), None)
                    if rep_item and not rep_matched_in_cf:
                        prefix = str(cf_df['concept'].iloc[0]).split('_')[0] if (len(cf_df) > 0 and '_' in str(cf_df['concept'].iloc[0])) else None
                        _append_rows_safely(cf_df, [{
                            'concept': f"{prefix}_SharesRepurchased" if prefix else 'PaymentsForPurchaseOfOwnShares',
                            'label': 'Repurchase of shares',
                            'standard_concept': 'PaymentsForPurchaseOfOwnShares',
                            'LTM': rep_item[1],
                        }])

                print(f"[SEC Extractor] Parser 6-K exitoso: {filing.primary_document} incorporado a LTM con estados IS, BS y CF.")
                return True
            except Exception as exc:
                logger.debug("Error parseando candidato 6-K %s: %s", getattr(filing, 'primary_document', '?'), exc)
                continue
    except Exception as exc:
        print(f"[SEC Extractor] Nota en parser 6-K: {exc}")
    return False

def convert_xb_statement_to_df(stmt_rows):
    """Convierte la lista de diccionarios de un rol XBRL en DataFrame con columnas FYxxxx."""
    data = []
    for r in stmt_rows:
        row_dict = {
            'concept': str(r.get('concept', '')).strip(),
            'label': str(r.get('label', '')).strip(),
        }
        vals = r.get('values', {})
        if isinstance(vals, dict):
            for p_k, v in vals.items():
                m = re.search(r'(\d{4})', str(p_k))
                if m and v != '':
                    f_v = _safe_float(v)
                    if f_v is not None:
                        row_dict[f"FY{m.group(1)}"] = f_v
        data.append(row_dict)
    return pd.DataFrame(data)


def merge_annual_statement_df(source_df, target_df, annual_fys, updated_cells=None, overwrite_if_newer=False):
    """
    Fusiona conceptos y valores de source_df en target_df.
    Aplica Latest Filed Priority y evita que filas dimensionales (p. ej. desgloses por clase
    o segmento) sobrescriban totales consolidados no dimensionales.
    """
    if source_df is None or source_df.empty or target_df is None:
        return
    if updated_cells is None:
        updated_cells = set()

    has_src_dim = "dimension" in source_df.columns or "dimension_axis" in source_df.columns
    has_tgt_dim = "dimension" in target_df.columns or "dimension_axis" in target_df.columns

    # Si un token tiene fila no dimensional en source_df, ignorar desgloses dimensionales del mismo token
    src_non_dim_tokens = set()
    if has_src_dim:
        for _, s_row in source_df.iterrows():
            c_tok = _clean_concept_token(s_row.get('concept'))
            if c_tok and not _is_dimensional_row(s_row):
                src_non_dim_tokens.add(c_tok)

    # Índice de destino O(1), priorizando filas no dimensionales frente a dimensionales
    target_idx_by_token: Dict[str, Any] = {}
    for t_idx, t_row in target_df.iterrows():
        t_tok = _clean_concept_token(t_row.get('concept'))
        if not t_tok:
            continue
        if t_tok not in target_idx_by_token:
            target_idx_by_token[t_tok] = t_idx
        elif has_tgt_dim and _is_dimensional_row(target_df.loc[target_idx_by_token[t_tok]]) and not _is_dimensional_row(t_row):
            target_idx_by_token[t_tok] = t_idx

    rows_to_append: List[Dict[str, Any]] = []
    for _, s_row in source_df.iterrows():
        c_concept = str(s_row.get('concept', '')).strip()
        if not c_concept or c_concept == 'nan':
            continue
        c_token = _clean_concept_token(c_concept)
        if has_src_dim and c_token in src_non_dim_tokens and _is_dimensional_row(s_row):
            continue

        match_idx = target_idx_by_token.get(c_token, -1)
        if match_idx != -1:
            for fy in annual_fys:
                if fy in source_df.columns and fy in target_df.columns:
                    f_sv = _safe_float(s_row.get(fy))
                    cell_key = (c_token, fy)
                    if f_sv is not None:
                        tv = target_df.at[match_idx, fy]
                        if overwrite_if_newer:
                            if cell_key not in updated_cells:
                                target_df.at[match_idx, fy] = f_sv
                                updated_cells.add(cell_key)
                        elif (tv is None or pd.isna(tv)) and cell_key not in updated_cells:
                            target_df.at[match_idx, fy] = f_sv
                            updated_cells.add(cell_key)
        else:
            new_row_dict: Dict[str, Any] = {"concept": c_concept, "label": str(s_row.get('label', c_concept))}
            has_any = False
            for fy in annual_fys:
                f_val = _safe_float(s_row.get(fy)) if fy in source_df.columns else None
                if f_val is not None:
                    new_row_dict[fy] = f_val
                    has_any = True
                    if overwrite_if_newer:
                        updated_cells.add((c_token, fy))
            if has_any:
                rows_to_append.append(new_row_dict)
                target_idx_by_token[c_token] = len(target_df) + len(rows_to_append) - 1

    if rows_to_append:
        _append_rows_safely(target_df, rows_to_append)


def _extract_20f_ecl_notes(doc_filing, bal_df, annual_fys):
    """
    Extrae provisiones acumuladas / ECL por etapa de las notas de riesgo de crédito en Form 20-F
    para bancos internacionales bajo IFRS cuando el balance general reporta cartera neta.
    """
    try:
        missing_fys = [
            fy for fy in annual_fys[:5]
            if fy in bal_df.columns and not any(
                str(r.get('concept', '')).strip() in BANKING_TAXONOMY_MAP.get("allowance_for_credit_losses", [])
                and (_safe_float(r.get(fy)) or 0.0) > 1e7
                for _, r in bal_df.iterrows()
            )
        ]
        if not missing_fys:
            return

        doc_html = doc_filing.html() if hasattr(doc_filing, 'html') else None
        if not doc_html or 'expected credit loss' not in doc_html.lower():
            return

        matches = re.findall(
            r'<table[^>]*>(?:(?!<table).)*?expected credit loss(?:(?!<table).)*?stage 1(?:(?!<table).)*?</table>',
            doc_html, re.IGNORECASE | re.DOTALL,
        )
        if not matches:
            return

        ecl_by_fy = {}
        for m in matches:
            try:
                t = pd.read_html(io.StringIO(m), flavor='lxml')[0]
                header_txt = ' '.join(t.iloc[:3, :].astype(str).values.flatten())
                years = re.findall(r'\b(202\d)\b', header_txt)
                if not years:
                    continue
                yr_tag = f"FY{years[0]}"
                if yr_tag not in annual_fys:
                    continue
                for r_idx in range(len(t)):
                    lbl = ' '.join(str(t.iloc[r_idx, 0]).split()).lower()
                    if 'expected credit loss at end of the year' in lbl:
                        for c_idx in range(t.shape[1] - 1, -1, -1):
                            raw_v = str(t.iloc[r_idx, c_idx]).replace(',', '').strip()
                            m_v = re.search(r'^\(?(\d+(?:\.\d+)?)\)?$', raw_v)
                            if m_v:
                                ecl_by_fy[yr_tag] = ecl_by_fy.get(yr_tag, 0.0) + float(m_v.group(1))
                                break
                        break
            except Exception as exc:
                logger.debug("Tabla ECL 20-F omitida por error de parseo: %s", exc)
                continue

        if ecl_by_fy:
            scale = 1000.0
            allow_indices = [
                i for i, r in bal_df.iterrows()
                if str(r.get('concept', '')).strip() in (
                    'AllowanceAccountForCreditLossesOfFinancialAssets',
                    'FinancingReceivableAllowanceForCreditLosses',
                )
            ]
            if allow_indices:
                for idx in allow_indices:
                    for fy_k, fy_v in ecl_by_fy.items():
                        if fy_k in bal_df.columns and (pd.isna(bal_df.at[idx, fy_k]) or (_safe_float(bal_df.at[idx, fy_k]) or 0.0) < 1e7):
                            bal_df.at[idx, fy_k] = fy_v * scale
                    bal_df.at[idx, 'label'] = 'Allowance for expected credit losses'
                    bal_df.at[idx, 'standard_concept'] = 'FinancingReceivableAllowanceForCreditLosses'
            else:
                new_row = {
                    'concept': 'AllowanceAccountForCreditLossesOfFinancialAssets',
                    'label': 'Allowance for expected credit losses',
                    'standard_concept': 'FinancingReceivableAllowanceForCreditLosses',
                }
                for fy_k, fy_v in ecl_by_fy.items():
                    if fy_k in bal_df.columns:
                        new_row[fy_k] = fy_v * scale
                _append_rows_safely(bal_df, [new_row])
            print(f"[SEC Extractor] Provisiones crediticias anuales extraídas de notas 20-F: {ecl_by_fy}")
    except Exception as exc:
        print(f"[SEC Extractor] Nota al extraer ECL de 20-F: {exc}")


def enrich_annual_statements_with_individual_filings(company, inc_df, bal_df, cf_df, annual_fys, filing_context=None):
    """
    Enriquece los estados contables de 10 años con los formularios anuales individuales (10-K o 20-F).
    Permite capturar conceptos contables modernos, extensiones o ejercicios recientes (Latest Filed Priority).
    """
    latest_fy = annual_fys[0] if annual_fys else None
    try:
        if filing_context:
            ann_filings = filing_context.get_filings(form="10-K") or filing_context.get_filings(form="20-F")
        else:
            ann_filings = company.get_filings(form="10-K") or company.get_filings(form="20-F")
        if ann_filings and len(ann_filings) > 0:
            updated_cells = {"inc": set(), "bal": set(), "cf": set()}
            for doc_filing in ann_filings[:10]:
                doc_single = filing_context.get_filing_obj(doc_filing) if filing_context else doc_filing.obj()
                if not doc_single or not doc_single.financials:
                    continue

                new_fys_detected = []
                for stmt_name in ('income_statement', 'balance_sheet', 'cash_flow_statement'):
                    s_check = getattr(doc_single.financials, stmt_name, None)
                    s_chk_obj = s_check() if s_check else None
                    chk_df = s_chk_obj.to_dataframe() if s_chk_obj is not None else None
                    if chk_df is not None and not chk_df.empty:
                        for c in chk_df.columns:
                            m = re.search(r'(\d{4})', str(c))
                            if m and not str(c).startswith(('level', 'dim')):
                                tag = f"FY{m.group(1)}"
                                if tag not in annual_fys and tag not in new_fys_detected:
                                    new_fys_detected.append(tag)
                if new_fys_detected:
                    print(f"[SEC Extractor] ¡Nuevos ejercicios anuales detectados en filing ({doc_filing.form})!: {new_fys_detected}")
                    annual_fys = sorted(
                        list(dict.fromkeys(new_fys_detected + annual_fys)),
                        key=lambda x: int(re.search(r'\d+', x).group(0)) if re.search(r'\d+', x) else 0,
                        reverse=True,
                    )
                    latest_fy = annual_fys[0]
                    for nfy in new_fys_detected:
                        for target_d in (inc_df, bal_df, cf_df):
                            if nfy not in target_d.columns:
                                target_d[nfy] = None

                stmts_to_merge = [
                    ('cash_flow_statement', cf_df, updated_cells["cf"]),
                    ('income_statement', inc_df, updated_cells["inc"]),
                    ('balance_sheet', bal_df, updated_cells["bal"]),
                ]
                for stmt_attr, target_df, up_cells in stmts_to_merge:
                    stmt_fn = getattr(doc_single.financials, stmt_attr, None)
                    s_obj = stmt_fn() if stmt_fn else None
                    s_raw_df = s_obj.to_dataframe() if s_obj is not None else None
                    if s_raw_df is not None and not s_raw_df.empty:
                        s_ren = {
                            c: f"FY{re.search(r'(\d{4})', str(c)).group(1)}"
                            for c in s_raw_df.columns
                            if re.search(r'(\d{4})', str(c)) and not str(c).startswith(('level', 'dim'))
                        }
                        s_df = s_raw_df.rename(columns=s_ren)
                        if stmt_attr == 'income_statement':
                            sanitize_multiclass_eps_df(s_df)
                        merge_annual_statement_df(s_df, target_df, annual_fys, updated_cells=up_cells, overwrite_if_newer=True)

                xb = getattr(doc_single.financials, 'xb', None)
                if xb:
                    try:
                        for s_meta in xb.get_all_statements():
                            rn = str(s_meta.get('role_name', '')).lower()
                            defi = str(s_meta.get('definition', '')).lower()
                            if ('profit' in rn or 'profit' in defi or 'loss' in rn) and 'comprehensive' not in rn and 'comprehensive' not in defi:
                                xb_rows = xb.get_statement(s_meta.get('role'))
                                if xb_rows and isinstance(xb_rows, list):
                                    xb_df = convert_xb_statement_to_df(xb_rows)
                                    if not xb_df.empty:
                                        sanitize_multiclass_eps_df(xb_df)
                                        merge_annual_statement_df(xb_df, inc_df, annual_fys, updated_cells=updated_cells["inc"], overwrite_if_newer=True)
                    except Exception as exc:
                        logger.debug("Error leyendo roles XBRL de profit/loss en %s: %s", getattr(doc_filing, 'form', 'filing'), exc)

            for doc_filing in ann_filings[:2]:
                if str(getattr(doc_filing, 'form', '')).upper() == '20-F':
                    _extract_20f_ecl_notes(doc_filing, bal_df, annual_fys)
                    break
    except Exception as exc:
        print(f"[SEC Extractor] Nota al enriquecer con reportes anuales individuales: {exc}")
    return annual_fys, latest_fy


def _check_quarterly_newer_than_fy(ytd_curr_inc: Optional[str], facts_df, latest_fy: Optional[str]) -> bool:
    """Determina si el 10-Q más reciente es posterior al cierre del 10-K de `latest_fy`."""
    if not (ytd_curr_inc and facts_df is not None and not facts_df.empty and latest_fy):
        return True
    m_q = re.search(r'(\d{4}-\d{2}-\d{2})', str(ytd_curr_inc))
    if not m_q:
        return True
    q_date = m_q.group(1)
    try:
        fy_num = int(str(latest_fy).replace('FY', ''))
        k_facts = facts_df[(facts_df['fiscal_year'] == fy_num) & (facts_df.get('fiscal_period', '') == 'FY')]
        if k_facts.empty and 'period_end' in facts_df.columns:
            k_facts = facts_df[facts_df['fiscal_year'] == fy_num]
        if not k_facts.empty:
            k_period_end = str(k_facts['period_end'].dropna().max())
            if k_period_end and q_date <= k_period_end:
                print(f"[SEC Extractor] El 10-Q ({q_date}) es previo o igual al cierre del 10-K ({k_period_end}) de {latest_fy}. LTM sincronizado canónicamente con {latest_fy}.")
                return False
    except (ValueError, TypeError, KeyError) as exc:
        logger.debug("No se pudo comparar fecha de 10-Q contra %s: %s", latest_fy, exc)
    return True


def _detect_ytd_columns(q_df):
    """Detecta las columnas YTD actual y previa en un DataFrame trimestral (10-Q)."""
    if q_df is None:
        return None, None
    all_q_cols = [c for c in q_df.columns if any(ch.isdigit() for ch in str(c)) and ('Q' in str(c) or 'YTD' in str(c) or '202' in str(c))]
    ytd_cols = sorted([c for c in all_q_cols if 'YTD' in str(c)] or all_q_cols, reverse=True)
    return (ytd_cols[0] if len(ytd_cols) >= 1 else None), (ytd_cols[1] if len(ytd_cols) >= 2 else None)


def _calibrate_ltm_eps_and_shares(inc_df: pd.DataFrame, facts_df) -> None:
    """Calibra EPS y acciones promedio ponderadas LTM mediante suma/promedio de 4 trimestres GAAP o NI/sh."""
    try:
        q4_eps_d = get_ltm_quarterly_metric(facts_df, XBRL_TAXONOMY_MAP["eps_diluted"], mode='sum') if facts_df is not None else None
        q4_eps_b = get_ltm_quarterly_metric(facts_df, XBRL_TAXONOMY_MAP["eps_basic"], mode='sum') if facts_df is not None else None
        q4_sh_d = get_ltm_quarterly_metric(facts_df, XBRL_TAXONOMY_MAP["shares_diluted"], mode='avg') if facts_df is not None else None
        q4_sh_b = get_ltm_quarterly_metric(facts_df, XBRL_TAXONOMY_MAP["shares_basic"], mode='avg') if facts_df is not None else None

        clean_sh_d_toks = {_clean_concept_token(x) for x in XBRL_TAXONOMY_MAP["shares_diluted"]}
        clean_sh_b_toks = {_clean_concept_token(x) for x in XBRL_TAXONOMY_MAP["shares_basic"]}
        clean_eps_d_toks = {_clean_concept_token(x) for x in XBRL_TAXONOMY_MAP["eps_diluted"]}
        clean_eps_b_toks = {_clean_concept_token(x) for x in XBRL_TAXONOMY_MAP["eps_basic"]}

        has_dim_col = "dimension" in inc_df.columns or "dimension_axis" in inc_df.columns
        for idx_r, r in inc_df.iterrows():
            cn = str(r.get('concept', ''))
            cn_tok = _clean_concept_token(cn)
            if 'adjustment' in cn.lower() or (has_dim_col and _is_dimensional_row(r)):
                continue
            if cn_tok in clean_eps_d_toks and q4_eps_d is not None and q4_eps_d > 0:
                inc_df.at[idx_r, 'LTM'] = q4_eps_d
                print(f"[SEC Extractor] LTM Diluted EPS calibrado por suma de 4 trimestres: ${q4_eps_d}")
            elif cn_tok in clean_eps_b_toks and q4_eps_b is not None and q4_eps_b > 0:
                inc_df.at[idx_r, 'LTM'] = q4_eps_b
                print(f"[SEC Extractor] LTM Basic EPS calibrado por suma de 4 trimestres: ${q4_eps_b}")
            elif cn_tok in clean_sh_d_toks and q4_sh_d is not None and q4_sh_d > 0:
                inc_df.at[idx_r, 'LTM'] = q4_sh_d
                print(f"[SEC Extractor] LTM Diluted Shares calibrado por promedio de 4 trimestres: {q4_sh_d:,.0f}")
            elif cn_tok in clean_sh_b_toks and q4_sh_b is not None and q4_sh_b > 0:
                inc_df.at[idx_r, 'LTM'] = q4_sh_b
                print(f"[SEC Extractor] LTM Basic Shares calibrado por promedio de 4 trimestres: {q4_sh_b:,.0f}")

        if q4_eps_d is None:
            ni_match = inc_df[inc_df['concept'].astype(str).str.lower().str.contains('netincome', na=False)]
            sh_match = inc_df[inc_df['concept'].astype(str).str.lower().str.contains('dilutedshares', na=False) | inc_df['concept'].astype(str).str.lower().str.contains('sharesoutstandingdiluted', na=False)]
            if not ni_match.empty and not sh_match.empty:
                ni_val_ltm = _safe_float(ni_match.iloc[0].get('LTM')) or 0.0
                sh_val_ltm = _safe_float(sh_match.iloc[0].get('LTM')) or 0.0
                if ni_val_ltm > 0 and sh_val_ltm > 0:
                    exp_ltm_eps = round(ni_val_ltm / sh_val_ltm, 2)
                    for idx_r, r in inc_df.iterrows():
                        cn = str(r.get('concept', '')).lower()
                        if 'earningspersharediluted' in cn or 'dilutedearningspershare' in cn:
                            cur_v = _safe_float(r.get('LTM'))
                            if cur_v is None or cur_v < exp_ltm_eps * 0.4:
                                inc_df.at[idx_r, 'LTM'] = exp_ltm_eps
                                print(f"[SEC Extractor] LTM Diluted EPS calibrado a 12 meses acumulados (NI/sh): ${exp_ltm_eps} (en vez de ${cur_v})")
        if q4_eps_b is None:
            ni_match = inc_df[inc_df['concept'].astype(str).str.lower().str.contains('netincome', na=False)]
            sh_b_match = inc_df[(inc_df['concept'].astype(str).str.lower().str.contains('shares', na=False) | inc_df['concept'].astype(str).str.lower().str.contains('weightedaverage', na=False)) & (~inc_df['concept'].astype(str).str.lower().str.contains('diluted', na=False)) & (~inc_df['concept'].astype(str).str.lower().str.contains('adjusted', na=False))]
            if not ni_match.empty and not sh_b_match.empty:
                ni_val_ltm = _safe_float(ni_match.iloc[0].get('LTM')) or 0.0
                sh_b_val_ltm = _safe_float(sh_b_match.iloc[0].get('LTM')) or 0.0
                if ni_val_ltm > 0 and sh_b_val_ltm > 0:
                    exp_ltm_eps_b = round(ni_val_ltm / sh_b_val_ltm, 2)
                    for idx_r, r in inc_df.iterrows():
                        cn = str(r.get('concept', '')).lower()
                        if ('earningspershare' in cn or 'basicearnings' in cn) and 'diluted' not in cn:
                            cur_v = _safe_float(r.get('LTM'))
                            if cur_v is None or cur_v < exp_ltm_eps_b * 0.4:
                                inc_df.at[idx_r, 'LTM'] = exp_ltm_eps_b
                                print(f"[SEC Extractor] LTM Basic EPS calibrado a 12 meses acumulados (NI/sh): ${exp_ltm_eps_b} (en vez de ${cur_v})")
    except Exception as exc:
        print(f"[SEC Extractor] Nota sobre calibración de EPS y Acciones LTM: {exc}")


def compute_and_inject_ltm_columns(
    inc_df, bal_df, cf_df,
    q_inc, q_cf,
    inc_ttm_df, cf_ttm_df, bal_mrq_df,
    facts_df, latest_fy, latest_mrq_date=None
):
    """Calcula e inyecta la columna 'LTM' (Trailing Twelve Months / MRQ) en inc_df, bal_df y cf_df."""
    print("[SEC Extractor] Calculando métricas LTM (Trailing Twelve Months)...")
    ytd_curr_inc, ytd_prev_inc = _detect_ytd_columns(q_inc)
    q_is_newer = _check_quarterly_newer_than_fy(ytd_curr_inc, facts_df, latest_fy)

    # --- Income Statement LTM ---
    q_cols_ttm = [col for col in inc_ttm_df.columns if col.startswith('Q')] if inc_ttm_df is not None else []
    latest_q_ttm = q_cols_ttm[0] if q_cols_ttm else None
    ltm_inc_map = {}
    if inc_ttm_df is not None and latest_q_ttm:
        for _, row in inc_ttm_df.iterrows():
            f_v = _safe_float(row.get(latest_q_ttm))
            if f_v is not None:
                ltm_inc_map[str(row.get('label', '')).strip().lower()] = f_v

    ltm_vals_inc = []
    for _, row in inc_df.iterrows():
        c_name = str(row.get('concept', '')).strip()
        lbl = str(row.get('label', '')).strip()
        fy_val = _safe_float(row.get(latest_fy))
        val = None

        if not q_is_newer and fy_val is not None:
            ltm_vals_inc.append(fy_val)
            continue

        is_share_count = any(k in c_name.lower() or k in lbl.lower() for k in ('sharesoutstanding', 'numberofshares'))
        c_tok = _clean_concept_token(c_name)
        if q_inc is not None and ytd_curr_inc:
            q_toks = q_inc['concept'].astype(str).apply(_clean_concept_token)
            match_q = q_inc[(q_toks == c_tok) | q_inc['concept'].astype(str).str.lower().str.endswith(c_name.lower()) | (q_inc['concept'].astype(str).str.lower() == c_name.lower())]
            if not match_q.empty:
                v_curr = _safe_float(match_q.iloc[0].get(ytd_curr_inc))
                if is_share_count:
                    val = v_curr
                elif ytd_prev_inc and fy_val is not None and v_curr is not None:
                    v_prev = _safe_float(match_q.iloc[0].get(ytd_prev_inc))
                    if v_prev is not None:
                        val = fy_val + v_curr - v_prev

        if val is None and not is_share_count and lbl.lower() in ltm_inc_map:
            val = ltm_inc_map[lbl.lower()]
        ltm_vals_inc.append(val)

    inc_df.insert(inc_df.columns.get_loc(latest_fy), 'LTM', ltm_vals_inc)
    if q_is_newer:
        _calibrate_ltm_eps_and_shares(inc_df, facts_df)

    # --- Balance Sheet MRQ for LTM ---
    mrq_cols = [c for c in bal_mrq_df.columns if c.startswith('Q')] if bal_mrq_df is not None else []
    latest_mrq_col = mrq_cols[0] if mrq_cols else None
    if latest_mrq_date is None and facts_df is not None and not facts_df.empty and 'period_end' in facts_df.columns:
        latest_mrq_date = _infer_mrq_date(facts_df)

    ltm_vals_bal = []
    for _, row in bal_df.iterrows():
        c_name = str(row.get('concept', '')).strip()
        fy_val = _safe_float(row.get(latest_fy))
        val = None

        if not q_is_newer and fy_val is not None:
            ltm_vals_bal.append(fy_val)
            continue
        if c_name.lower().endswith('abstract') or str(row.get('label', '')).lower().endswith('[abstract]'):
            ltm_vals_bal.append(None)
            continue

        if bal_mrq_df is not None and latest_mrq_col:
            c_tok = _clean_concept_token(c_name)
            b_toks = bal_mrq_df['concept'].astype(str).apply(_clean_concept_token)
            match_b = bal_mrq_df[(b_toks == c_tok) | bal_mrq_df['concept'].astype(str).str.lower().str.endswith(c_name.lower()) | (bal_mrq_df['concept'].astype(str).str.lower() == c_name.lower())]
            if not match_b.empty:
                val = _safe_float(match_b.iloc[0].get(latest_mrq_col))

        if val is None and facts_df is not None and not facts_df.empty:
            c_tok_raw = c_name.split(':')[-1].split('_')[-1]
            cand_search = [c_name, c_tok_raw]
            for cands_tax in {**XBRL_TAXONOMY_MAP, **BANKING_TAXONOMY_MAP}.values():
                if any(cand.lower() == c_tok_raw.lower() for cand in cands_tax):
                    cand_search.extend(cands_tax)
            if any(w in c_tok_raw.lower() for w in ('marketablesecurities', 'shortterminvestments', 'securitiescurrent')):
                cand_search.extend(XBRL_TAXONOMY_MAP["marketable_securities_current"])
                val = get_mrq_fact_sum(facts_df, ["DebtSecuritiesCurrent", "EquitySecuritiesFvNi"], mrq_date=latest_mrq_date) or get_mrq_fact(facts_df, cand_search, mrq_date=latest_mrq_date)
            else:
                val = get_mrq_fact(facts_df, cand_search, mrq_date=latest_mrq_date)
        ltm_vals_bal.append(val)

    bal_df.insert(bal_df.columns.get_loc(latest_fy), 'LTM', ltm_vals_bal)

    # --- Cash Flow Statement LTM ---
    ytd_curr_cf, ytd_prev_cf = _detect_ytd_columns(q_cf)
    q_cols_cf_ttm = [col for col in cf_ttm_df.columns if col.startswith('Q')] if cf_ttm_df is not None else []
    latest_q_cf_ttm = q_cols_cf_ttm[0] if q_cols_cf_ttm else None
    ltm_cf_map = {}
    if cf_ttm_df is not None and latest_q_cf_ttm:
        for _, row_cf in cf_ttm_df.iterrows():
            f_v = _safe_float(row_cf.get(latest_q_cf_ttm))
            if f_v is not None:
                ltm_cf_map[str(row_cf.get('label', '')).strip().lower()] = f_v
                c_cf = str(row_cf.get('concept', '')).strip()
                if c_cf:
                    ltm_cf_map[_clean_concept_token(c_cf)] = f_v

    ENDING_CASH_CONCEPTS = {
        "cashcashequivalentsrestrictedcashandrestrictedcashequivalents",
        "cashandcashequivalentsatcarryingvalue", "cashandcashequivalents", "cash",
        "restrictedcashandcashequivalentsatcarryingvalue", "restrictedcashandcashequivalentsnoncurrent",
        "restrictedcashandcashequivalents", "cashandcashequivalentsfairvaluedisclosure",
    }
    BEGINNING_CASH_CONCEPTS = {
        "cashcashequivalentsrestrictedcashandrestrictedcashequivalentsbeginningofperiod",
        "cashandcashequivalentsatbeginningofperiod",
        "cashandcashequivalentsatcarryingvaluebeginningofperiod", "cashbeginningofperiod",
    }
    cf_categories = (
        "dividends_paid", "share_repurchases", "share_repurchases_sbc_tax",
        "capital_expenditures", "acquisitions_ma", "stock_plans_proceeds",
        "debt_repayments", "debt_issuances", "operating_cash_flow", "cash_from_operations",
    )

    ltm_vals_cf = []
    for _, row in cf_df.iterrows():
        c_name = str(row.get('concept', '')).strip()
        fy_val = _safe_float(row.get(latest_fy))
        val = None

        if not q_is_newer and fy_val is not None:
            ltm_vals_cf.append(fy_val)
            continue

        c_tok = _clean_concept_token(c_name)
        is_ending_cash = c_tok in ENDING_CASH_CONCEPTS
        is_beg_cash = c_tok in BEGINNING_CASH_CONCEPTS

        if q_cf is not None and ytd_curr_cf and ytd_prev_cf:
            q_toks = q_cf['concept'].astype(str).apply(_clean_concept_token)
            match_cf = q_cf[(q_toks == c_tok) | (q_cf['concept'].astype(str).str.lower() == c_name.lower())]
            if match_cf.empty:
                match_cf = q_cf[q_cf['concept'].astype(str).str.lower().str.endswith(':' + c_tok) | q_cf['concept'].astype(str).str.lower().str.endswith('_' + c_tok)]
            if match_cf.empty:
                for cat in cf_categories:
                    cand_list = XBRL_TAXONOMY_MAP.get(cat, [])
                    if c_tok in {_clean_concept_token(cand) for cand in cand_list} or any(cand.lower() in c_name.lower() for cand in cand_list):
                        for cand in cand_list:
                            c_clean = _clean_concept_token(cand)
                            cand_match = q_cf[(q_toks == c_clean) | (q_cf['concept'].astype(str).str.lower() == cand.lower())]
                            if not cand_match.empty:
                                match_cf = cand_match
                                break
                    if not match_cf.empty:
                        break
            if match_cf.empty and 'label' in q_cf.columns and 'label' in row:
                lbl_raw = str(row.get('label', '')).strip()
                if lbl_raw and not c_name.lower().endswith('abstract'):
                    lbl_clean = re.sub(r'[^a-z0-9]', '', lbl_raw.lower())
                    if len(lbl_clean) >= 4:
                        q_lbls_clean = q_cf['label'].astype(str).apply(lambda s: re.sub(r'[^a-z0-9]', '', str(s).lower()))
                        cand_lbl = q_cf[(q_lbls_clean == lbl_clean) & (~q_cf['concept'].astype(str).str.lower().str.endswith('abstract'))]
                        if not cand_lbl.empty:
                            match_cf = cand_lbl

            if not match_cf.empty:
                q_row = match_cf.iloc[0]
                v_curr = _safe_float(q_row.get(ytd_curr_cf))
                v_prev = _safe_float(q_row.get(ytd_prev_cf))
                if is_ending_cash:
                    val = v_curr
                elif is_beg_cash:
                    end_match = q_cf[q_cf['concept'].astype(str).apply(_clean_concept_token).isin(ENDING_CASH_CONCEPTS)]
                    if not end_match.empty:
                        val = _safe_float(end_match.iloc[0].get(ytd_prev_cf))
                    if val is None:
                        val = v_prev
                elif v_curr is not None:
                    if v_prev is not None and fy_val is not None:
                        val = fy_val + v_curr - v_prev
                    elif v_prev is not None:
                        val = v_curr - v_prev

        if val is None and is_ending_cash and facts_df is not None and not facts_df.empty:
            val = get_mrq_fact(facts_df, [c_name, c_tok], mrq_date=latest_mrq_date)

        if val is None and ltm_cf_map and not is_ending_cash and not is_beg_cash:
            if c_tok in ltm_cf_map:
                val = ltm_cf_map[c_tok]
            elif str(row.get('label', '')).strip().lower() in ltm_cf_map:
                val = ltm_cf_map[str(row.get('label', '')).strip().lower()]

        if val is None and fy_val is not None and any(cand.lower() in c_name.lower() for cand in XBRL_TAXONOMY_MAP["acquisitions_ma"]):
            val = fy_val

        ltm_vals_cf.append(val)

    cf_df.insert(cf_df.columns.get_loc(latest_fy), 'LTM', ltm_vals_cf)
