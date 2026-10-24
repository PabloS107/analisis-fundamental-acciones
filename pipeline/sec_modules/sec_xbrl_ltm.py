"""
sec_xbrl_ltm.py - Extracción cruda XBRL, consultas a Company Facts, fusión multi-período
y cálculo de series LTM/TTM (US-GAAP 10-Q y parser interino HTML Form 6-K para FPIs).
"""

import os
import sys
import io
import re
from pathlib import Path
from datetime import datetime
import pandas as pd
import numpy as np

try:
    from financial_taxonomy import XBRL_TAXONOMY_MAP, BANKING_TAXONOMY_MAP
except ImportError:
    try:
        from ..financial_taxonomy import XBRL_TAXONOMY_MAP, BANKING_TAXONOMY_MAP
    except ImportError:
        from pipeline.financial_taxonomy import XBRL_TAXONOMY_MAP, BANKING_TAXONOMY_MAP


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
        
    for _, row in df.iterrows():
        concept = row.get('concept')
        if not concept or pd.isna(concept) or str(concept) == 'nan':
            continue
            
        concept_str = str(concept).strip()
        label = str(row.get('label', '')).strip()
        std_concept = str(row.get('standard_concept', '')).strip()
        
        values = {}
        for p in periods:
            if p in df.columns:
                val = row.get(p)
                if pd.notna(val) and str(val) != 'nan':
                    try:
                        num_val = float(val)
                        # Normalización contable: costos y gastos operativos deben ser magnitudes positivas
                        c_low = concept_str.lower()
                        expense_indicators = (
                            'costof', 'expense', 'expenses', 'charges', 'provisions',
                            'recurringcapitalexpenditures', 'paymentsforcapitalimprovements',
                            'paymentsforpropertyimprovements'
                        )
                        non_expense_exclusions = (
                            'income', 'revenue', 'gain', 'operatingincomeloss',
                            'netincomeloss', 'profitloss'
                        )
                        if any(ind in c_low for ind in expense_indicators) and not any(excl in c_low for excl in non_expense_exclusions):
                            num_val = abs(num_val)
                        values[p] = num_val
                    except (ValueError, TypeError):
                        pass
                        
        depth_val = int(row.get('depth', 0)) if pd.notna(row.get('depth')) else 0
        is_abstract = bool(row.get('is_abstract', False)) if pd.notna(row.get('is_abstract')) else False
        is_total = bool(row.get('is_total', False)) if pd.notna(row.get('is_total')) else False
        section_val = str(row.get('section', '')).strip() if pd.notna(row.get('section')) else ''

        if concept_str not in data_by_concept or len(values) > len(data_by_concept[concept_str].get("values", {})):
            data_by_concept[concept_str] = {
                "label": label,
                "standard_concept": std_concept if std_concept != 'None' else None,
                "values": values,
                "depth": depth_val,
                "is_abstract": is_abstract,
                "is_total": is_total,
                "section": section_val
            }
            
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
                val = c_data["values"].get(period)
                if val is not None and not pd.isna(val):
                    try:
                        total += float(val)
                        matched = True
                        matched_tokens.add(k_token)
                    except (ValueError, TypeError):
                        pass
    return total if matched else None


def get_mrq_fact(facts_df, concept_candidates, mrq_date=None):
    """Busca el saldo al cierre del trimestre más reciente (MRQ / LTM Balance Sheet) en Company Facts."""
    if facts_df is None or facts_df.empty:
        return None
    if mrq_date is None:
        asset_matches = facts_df[facts_df['concept'].astype(str).str.endswith(':Assets') | facts_df['concept'].astype(str).str.endswith(':StockholdersEquity')]
        if not asset_matches.empty:
            mrq_date = asset_matches['period_end'].dropna().max()
        else:
            mrq_date = facts_df['period_end'].dropna().max()
            
    concepts_series = facts_df['concept'].astype(str)
    concepts_tokens = concepts_series.str.split(':').str[-1].str.split('_').str[-1].str.lower()
    
    for cand in concept_candidates:
        cand_lower = cand.lower()
        matches = facts_df[(facts_df['period_end'] == mrq_date) & (concepts_tokens == cand_lower)]
        if not matches.empty:
            val = matches.iloc[-1].get('numeric_value')
            if pd.notna(val) and str(val) != 'nan':
                try:
                    return float(val)
                except (ValueError, TypeError):
                    pass
    return None


def get_mrq_fact_sum(facts_df, concept_candidates, mrq_date=None):
    """Suma acumulativamente conceptos en facts_df al cierre de MRQ (ej. deuda corriente + valores negociables)."""
    if facts_df is None or facts_df.empty:
        return None
    if mrq_date is None:
        asset_matches = facts_df[facts_df['concept'].astype(str).str.endswith(':Assets') | facts_df['concept'].astype(str).str.endswith(':StockholdersEquity')]
        if not asset_matches.empty:
            mrq_date = asset_matches['period_end'].dropna().max()
        else:
            mrq_date = facts_df['period_end'].dropna().max()
            
    concepts_series = facts_df['concept'].astype(str)
    concepts_tokens = concepts_series.str.split(':').str[-1].str.split('_').str[-1].str.lower()
    
    total = 0.0
    matched = False
    matched_tokens = set()
    for cand in concept_candidates:
        cand_lower = cand.lower().split(':')[-1].split('_')[-1]
        matches = facts_df[(facts_df['period_end'] == mrq_date) & (concepts_tokens == cand_lower)]
        if not matches.empty and cand_lower not in matched_tokens:
            val = matches.iloc[-1].get('numeric_value')
            if pd.notna(val) and str(val) != 'nan':
                try:
                    total += float(val)
                    matched = True
                    matched_tokens.add(cand_lower)
                except (ValueError, TypeError):
                    pass
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
        
        # Trimestres discretos (60 a 115 días)
        q_rows = sub[(sub['days'] >= 60) & (sub['days'] <= 115)].sort_values('p_end')
        q_rows = q_rows.drop_duplicates(subset=['p_end'], keep='last')
        
        # Derivar Q4 = FY - 9M si Q4 no se reporta de forma independiente
        fy_rows = sub[(sub['days'] >= 330) & (sub['days'] <= 380)].sort_values('p_end')
        ytd9_rows = sub[(sub['days'] >= 240) & (sub['days'] <= 300)].sort_values('p_end')
        
        derived_q4s = []
        for _, fy_r in fy_rows.iterrows():
            fy_end = fy_r['p_end']
            fy_val = fy_r['num_val']
            matching_9m = ytd9_rows[(ytd9_rows['p_start'] == fy_r['p_start']) & (ytd9_rows['p_end'] < fy_end)]
            if not matching_9m.empty:
                ytd_val = matching_9m.iloc[-1]['num_val']
                if mode == 'avg':
                    q4_val = 4.0 * fy_val - 3.0 * ytd_val
                else:
                    q4_val = fy_val - ytd_val
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
                else:
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
        # Balance Sheet / Point in Time: MRQ
        if any("shares" in c.lower() for c in concept_candidates):
            avg_sh = get_ltm_quarterly_metric(facts_df, concept_candidates, mode='avg')
            if avg_sh is not None:
                return avg_sh
        return get_mrq_fact(facts_df, concept_candidates)
        
    year_digits = ''.join(filter(str.isdigit, fy_str))
    if not year_digits:
        return None
    fy_int = int(year_digits)
    
    # Extraer token local para todos los conceptos en facts_df (sin namespace)
    concepts_series = facts_df['concept'].astype(str)
    concepts_tokens = concepts_series.str.split(':').str[-1].str.split('_').str[-1].str.lower()
    
    # Matching temporal: primero por period_end (año de balance contable real)
    p_end_year = facts_df['period_end'].astype(str).str[:4]
    
    for cand in concept_candidates:
        cand_lower = cand.lower()
        # 1. Matching exacto por año de period_end
        matches = facts_df[(p_end_year == str(fy_int)) & (concepts_tokens == cand_lower)]
        if matches.empty:
            # 2. Respaldo por fiscal_year
            matches = facts_df[(facts_df['fiscal_year'] == fy_int) & (concepts_tokens == cand_lower)]
            
        if not matches.empty:
            fy_matches = matches[matches['fiscal_period'].astype(str).str.upper() == 'FY']
            chosen_subset = fy_matches if not fy_matches.empty else matches
            
            # Si es flujo contable (Income Statement / Cash Flow), asegurar duración anual (>= 300 días)
            # para evitar trimestres aislados (ej. Q4) erróneamente etiquetados como fiscal_period: FY
            if is_flow:
                start_col = None
                for c in ['period_start', 'start']:
                    if c in chosen_subset.columns:
                        start_col = c
                        break
                end_col = None
                for c in ['period_end', 'end']:
                    if c in chosen_subset.columns:
                        end_col = c
                        break
                if start_col and end_col:
                    try:
                        starts = pd.to_datetime(chosen_subset[start_col], errors='coerce')
                        ends = pd.to_datetime(chosen_subset[end_col], errors='coerce')
                        durations = (ends - starts).dt.days
                        long_subset = chosen_subset[durations >= 300]
                        if not long_subset.empty:
                            chosen_subset = long_subset
                    except Exception:
                        pass

            for f_col in ['filed', 'filing_date']:
                if f_col in chosen_subset.columns:
                    chosen_subset = chosen_subset.sort_values(f_col)
                    break
            chosen = chosen_subset.iloc[-1]
            val = chosen.get('numeric_value')
            if pd.notna(val) and str(val) != 'nan':
                try:
                    return float(val)
                except (ValueError, TypeError):
                    pass
    return None


def detect_global_doc_scale(html_content):
    """
    Nivel 2: Salvaguarda Global del Documento.
    Detecta si los estados financieros declaran a nivel general que las cifras
    están expresadas en miles ('in thousands of u.s. dollars') o millones.
    """
    if not html_content:
        return 1.0
    doc_sample = str(html_content)[:150000].lower()
    clean_sample = re.sub(r'\s+', ' ', doc_sample)
    
    millions_patterns = [
        "in millions of u.s. dollars", "(in millions of u.s. dollars",
        "in millions of us dollars", "(in millions of us dollars",
        "in millions of dollars", "(in millions of dollars",
        "amounts in millions", "(in millions)", "stated in millions"
    ]
    thousands_patterns = [
        "in thousands of u.s. dollars", "(in thousands of u.s. dollars",
        "in thousands of us dollars", "(in thousands of us dollars",
        "in thousands of dollars", "(in thousands of dollars",
        "amounts in thousands", "(in thousands)", "stated in thousands"
    ]
    
    for m in millions_patterns:
        if m in clean_sample:
            return 1_000_000.0
    for t in thousands_patterns:
        if t in clean_sample:
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
                if len(cell_val) >= 5 and cell_val.lower() not in ['none', 'nan', 'null', 'total', 'assets', 'equity', 'period', 'three', 'six', 'nine']:
                    pos = lower_html.find(cell_val.lower())
                    if pos != -1:
                        tbl_tag_pos = lower_html.rfind('<table', max(0, pos - 6000), pos)
                        target_pos = tbl_tag_pos if tbl_tag_pos != -1 else pos
                        start_pos = max(0, target_pos - window_size)
                        return html_content[start_pos:target_pos]
    except Exception:
        pass
    return ""


def detect_table_scale_factor(table, doc_context="", preceding_html=""):
    """
    Detecta dinámicamente si los números en una tabla de reporte financiero (ej. 6-K HTML)
    están expresados en miles ('in thousands'), millones ('in millions') o unidades directas/base.
    Prioriza el contexto HTML inmediatamente precedente a la apertura de la tabla.
    """
    sample_text = ""
    if preceding_html:
        sample_text += " " + str(preceding_html).lower()
    if table is not None:
        try:
            sample_text += ' ' + ' '.join(table.iloc[:5, :].astype(str).values.flatten()).lower()
        except Exception:
            pass
    if doc_context:
        sample_text += " " + str(doc_context)[:25000].lower()
        
    clean_sample = re.sub(r'\s+', ' ', sample_text)
    
    if any(k in clean_sample for k in [
        "in millions", "in million", "$ in millions", "$ in million",
        "(in millions", "(in million", "stated in millions", "amounts in millions"
    ]):
        return 1_000_000.0
    elif any(k in clean_sample for k in [
        "in thousands", "in thousand", "$ in thousands", "$ in thousand",
        "(in thousands", "(in thousand", "stated in thousands", "amounts in thousands"
    ]):
        return 1_000.0
    elif any(k in clean_sample for k in [
        "in billions", "in billion", "(in billions"
    ]):
        return 1_000_000_000.0
        
    return 1.0


def extract_6k_fpi_interim(company, annual_fys, latest_fy, inc_df, bal_df, cf_df=None):
    """
    Parsea los estados financieros interinos de Form 6-K para Foreign Private Issuers
    y calcula el período LTM acumulado mediante la identidad móvil:
    LTM = FY_latest - Interino_prev + Interino_curr
    """
    try:
        import io, re
        f_list = company.get_filings(form='6-K')
        cand_filings = [f for f in f_list if any(k in str(getattr(f, 'primary_document', '')).lower() for k in ['nufs', 'financial', 'statement', 'interim'])]
        if not cand_filings:
            cand_filings = f_list[:8]

        def _clean_val(v):
            if pd.isna(v): return None
            s = str(v).replace('$', '').replace(',', '').replace(' ', '').replace('(', '-').replace(')', '').strip()
            try: return float(s)
            except: return None

        def clean_txt(s):
            s = re.sub(r'[^a-zA-Z0-9\s]', ' ', str(s).lower())
            s = re.sub(r'\s+', ' ', s).strip()
            return s

        for filing in cand_filings:
            try:
                html_content = filing.html()
                if not html_content or len(html_content) < 50000:
                    continue
                tables = pd.read_html(io.StringIO(html_content))
                is_tbl, bs_a_tbl, bs_l_tbl = None, None, None
                cf_o_tbl, cf_i_tbl, cf_f_tbl = None, None, None
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

                if is_tbl is not None and bs_a_tbl is not None and bs_l_tbl is not None:
                    # Nivel 2: Detección global de escala
                    doc_scale = detect_global_doc_scale(html_content)

                    # Nivel 1: Detección local en contexto precedente a cada tabla
                    is_pre = get_preceding_html_context(html_content, is_tbl)
                    bs_pre = get_preceding_html_context(html_content, bs_a_tbl)
                    cf_tbl_ref = cf_o_tbl if cf_o_tbl is not None else (cf_i_tbl if cf_i_tbl is not None else cf_f_tbl)
                    cf_pre = get_preceding_html_context(html_content, cf_tbl_ref)

                    is_scale = detect_table_scale_factor(is_tbl, doc_context="", preceding_html=is_pre)
                    bs_scale = detect_table_scale_factor(bs_a_tbl, doc_context="", preceding_html=bs_pre)
                    cf_scale = detect_table_scale_factor(cf_tbl_ref, doc_context="", preceding_html=cf_pre)

                    # Si la escala local dio 1.0, aplicar salvaguarda global del documento
                    if is_scale == 1.0 and doc_scale > 1.0:
                        is_scale = doc_scale
                    if bs_scale == 1.0 and doc_scale > 1.0:
                        bs_scale = doc_scale
                    if cf_scale == 1.0 and doc_scale > 1.0:
                        cf_scale = doc_scale

                    print(f"[SEC Extractor] Escalas 6-K detectadas: IS={is_scale}, BS={bs_scale}, CF={cf_scale} (Doc Global={doc_scale})")

                    # Encontrar dinámicamente los años reportados en las cabeceras
                    all_years_is = []
                    for c_idx in range(is_tbl.shape[1]):
                        hdr_text = ' '.join(is_tbl.iloc[:4, c_idx].astype(str).tolist())
                        yrs = [int(y) for y in re.findall(r'\b(20\d\d)\b', hdr_text)]
                        all_years_is.extend(yrs)
                    
                    if all_years_is:
                        curr_yr = max(all_years_is)
                        prev_yr = curr_yr - 1
                    else:
                        curr_yr = datetime.now().year
                        prev_yr = curr_yr - 1

                    # Priorizar período acumulado YTD (nueve meses > seis meses > tres meses)
                    col_curr_is, col_prev_is = None, None
                    for dur_kw in ['nine', '9', 'six', '6', 'three', '3']:
                        c_curr, c_prev = None, None
                        for c_idx in range(is_tbl.shape[1]):
                            col_hdr = ' '.join(is_tbl.iloc[:4, c_idx].astype(str).tolist()).lower()
                            if dur_kw in col_hdr:
                                if str(curr_yr) in col_hdr and c_curr is None:
                                    c_curr = c_idx
                                elif str(prev_yr) in col_hdr and c_prev is None:
                                    c_prev = c_idx
                        if c_curr is not None and c_prev is not None:
                            col_curr_is, col_prev_is = c_curr, c_prev
                            break

                    if col_curr_is is None:
                        for c_idx in range(is_tbl.shape[1]):
                            col_hdr = ' '.join(is_tbl.iloc[:4, c_idx].astype(str).tolist()).lower()
                            if str(curr_yr) in col_hdr and col_curr_is is None:
                                col_curr_is = c_idx
                            elif str(prev_yr) in col_hdr and col_prev_is is None:
                                col_prev_is = c_idx

                    if col_curr_is is None:
                        col_curr_is = 7 if is_tbl.shape[1] > 7 else 3
                        col_prev_is = 9 if is_tbl.shape[1] > 9 else (col_curr_is + 1 if is_tbl.shape[1] > col_curr_is + 1 else None)

                    interim_is = []
                    for _, r in is_tbl.iterrows():
                        lbl = clean_txt(r[0])
                        vc = _clean_val(r[col_curr_is])
                        vp = _clean_val(r[col_prev_is]) if col_prev_is is not None else None
                        if vc is not None:
                            interim_is.append((lbl, vc * is_scale, (vp * is_scale) if vp is not None else 0.0))

                    def find_is_match(c_name, l_name):
                        c_clean = clean_txt(c_name)
                        l_clean = clean_txt(l_name)
                        for lbl, vc, vp in interim_is:
                            if l_clean == lbl:
                                return lbl, vc, vp
                        if 'incometax' in c_clean and 'before' not in c_clean and 'before' not in l_clean:
                            for lbl, vc, vp in interim_is:
                                if lbl == 'income taxes': return lbl, vc, vp
                        if 'interest' in c_clean and 'expense' in c_clean:
                            for lbl, vc, vp in interim_is:
                                if 'interest' in lbl and 'expense' in lbl:
                                    return lbl, vc, vp
                        if 'profitlossbeforetax' in c_clean or 'before income taxes' in l_clean:
                            for lbl, vc, vp in interim_is:
                                if 'before income taxes' in lbl: return lbl, vc, vp
                        if ('netincome' in c_clean or 'profitloss' in c_clean) and 'attributable' not in c_clean and 'noncontrolling' not in c_clean:
                            if 'period' in l_clean or 'year' in l_clean or l_clean == 'net income':
                                for lbl, vc, vp in interim_is:
                                    if 'net income for the period' in lbl: return lbl, vc, vp
                        is_diluted_shares = 'adjustedaverageweightedshares' in c_clean or ('diluted' in l_clean and 'share' in l_clean) or ('diluted' in c_clean and 'share' in c_clean)
                        is_basic_shares = ('weightedaverageshares' in c_clean or ('ordinary' in l_clean and 'share' in l_clean) or ('share' in l_clean and 'weighted' in l_clean)) and not is_diluted_shares

                        if is_diluted_shares:
                            for lbl, vc, vp in interim_is:
                                if 'weighted average' in lbl and 'diluted' in lbl:
                                    return lbl, vc, vp
                        elif is_basic_shares:
                            for lbl, vc, vp in interim_is:
                                if 'weighted average' in lbl and ('basic' in lbl or 'diluted' not in lbl):
                                    return lbl, vc, vp

                        is_diluted_eps = ('diluted' in c_clean or 'diluted' in l_clean) and any(w in c_clean or w in l_clean for w in ['eps', 'earnings', 'pershare'])
                        is_basic_eps = ('basic' in c_clean or 'basic' in l_clean or ('pershare' in c_clean and not is_diluted_eps)) and any(w in c_clean or w in l_clean for w in ['eps', 'earnings', 'pershare'])

                        if is_diluted_eps:
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

                    # Población de LTM en inc_df
                    if 'LTM' not in inc_df.columns and latest_fy in inc_df.columns:
                        ltm_col = []
                        for _, row in inc_df.iterrows():
                            concept = str(row.get('concept', ''))
                            label = str(row.get('label', ''))
                            fy_val = row.get(latest_fy)
                            val = None
                            
                            m_lbl, vc, vp = find_is_match(concept, label)
                            if m_lbl and pd.notna(fy_val):
                                if 'weighted average' in m_lbl or 'shares' in concept.lower():
                                    val = vc
                                elif 'earnings per share' in m_lbl or 'pershare' in concept.lower():
                                    if vp is not None and vc is not None:
                                        val = round(float(fy_val) - vp + vc, 4)
                                    else:
                                        val = float(fy_val)
                                else:
                                    val = float(fy_val) - vp + vc
                            ltm_col.append(val)
                        inc_df.insert(inc_df.columns.get_loc(latest_fy), 'LTM', ltm_col)

                    # Población de LTM en bal_df
                    interim_bs = []
                    for b_tbl in [bs_a_tbl, bs_l_tbl]:
                        col_bs_date = None
                        for c_idx in range(b_tbl.shape[1]):
                            hdr_txt = ' '.join(b_tbl.iloc[:3, c_idx].astype(str).tolist()).lower()
                            if str(curr_yr) in hdr_txt:
                                col_bs_date = c_idx
                                break
                        if col_bs_date is None:
                            col_bs_date = 3 if b_tbl.shape[1] > 3 else (1 if b_tbl.shape[1] > 1 else 0)
                        for _, r in b_tbl.iterrows():
                            lbl = clean_txt(r[0])
                            v = _clean_val(r[col_bs_date])
                            if v is not None:
                                interim_bs.append((lbl, v * bs_scale))

                    # Nivel 3: Calibración Triangulada de Sanidad Contable (Cross-Period Ratio Validation)
                    fy_assets = None
                    for _, r in bal_df.iterrows():
                        c_cn = str(r.get('concept', '')).lower()
                        l_lb = str(r.get('label', '')).lower()
                        if 'abstract' in c_cn:
                            continue
                        if c_cn.endswith('assets') or l_lb in ['assets', 'total assets']:
                            val = r.get(latest_fy)
                            if pd.notna(val) and float(val) > 0:
                                fy_assets = float(val)
                                break
                    interim_assets = None
                    for lbl, v in interim_bs:
                        if lbl in ['total assets', 'assets'] and v is not None and v > 0:
                            interim_assets = float(v)
                            break

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
                            if cf_scale < calib_factor:
                                cf_scale = calib_factor

                    used_bs_indices = set()
                    def find_bs_match(c_name, l_name):
                        if 'abstract' in c_name.lower():
                            return None, None
                        c_clean = clean_txt(c_name)
                        l_clean = clean_txt(l_name)
                        for idx, (lbl, v) in enumerate(interim_bs):
                            if idx in used_bs_indices:
                                continue
                            if l_clean == lbl:
                                used_bs_indices.add(idx)
                                return lbl, v
                        if 'cash' in c_clean and 'cash' in l_clean and 'central' not in l_clean:
                            for idx, (lbl, v) in enumerate(interim_bs):
                                if idx in used_bs_indices: continue
                                if lbl == 'cash and cash equivalents':
                                    used_bs_indices.add(idx)
                                    return lbl, v
                        if 'central' in c_clean or 'central' in l_clean:
                            for idx, (lbl, v) in enumerate(interim_bs):
                                if idx in used_bs_indices: continue
                                if 'central' in lbl:
                                    used_bs_indices.add(idx)
                                    return lbl, v
                        if 'creditcard' in c_clean or 'credit card' in l_clean:
                            for idx, (lbl, v) in enumerate(interim_bs):
                                if idx in used_bs_indices: continue
                                if 'credit card' in lbl:
                                    used_bs_indices.add(idx)
                                    return lbl, v
                        if 'loansandadvances' in c_clean or 'loans to customers' in l_clean:
                            for idx, (lbl, v) in enumerate(interim_bs):
                                if idx in used_bs_indices: continue
                                if 'loans to customers' in lbl:
                                    used_bs_indices.add(idx)
                                    return lbl, v
                        if 'depositsfromcustomers' in c_clean or l_clean == 'deposits':
                            for idx, (lbl, v) in enumerate(interim_bs):
                                if idx in used_bs_indices: continue
                                if lbl == 'deposits':
                                    used_bs_indices.add(idx)
                                    return lbl, v
                        if 'borrowings' in c_clean or 'borrowing' in l_clean:
                            for idx, (lbl, v) in enumerate(interim_bs):
                                if idx in used_bs_indices: continue
                                if 'borrowing' in lbl:
                                    used_bs_indices.add(idx)
                                    return lbl, v
                        if 'repurchase' in c_clean or 'repurchase' in l_clean:
                            for idx, (lbl, v) in enumerate(interim_bs):
                                if idx in used_bs_indices: continue
                                if 'repurchase' in lbl:
                                    used_bs_indices.add(idx)
                                    return lbl, v
                        if c_clean in ['assets', 'totalassets'] or l_clean in ['assets', 'total assets']:
                            for idx, (lbl, v) in enumerate(interim_bs):
                                if idx in used_bs_indices: continue
                                if lbl in ['total assets', 'assets']:
                                    used_bs_indices.add(idx)
                                    return lbl, v
                        if 'total' in l_clean and 'equity' in l_clean:
                            for idx, (lbl, v) in enumerate(interim_bs):
                                if idx in used_bs_indices: continue
                                if lbl in ['total equity', 'total shareholders equity', 'total stockholders equity']:
                                    used_bs_indices.add(idx)
                                    return lbl, v
                        for idx, (lbl, v) in enumerate(interim_bs):
                            if idx in used_bs_indices: continue
                            # Excluir explícitamente que cuentas 'total' coincidan con cuentas no-totales
                            if ('total' in lbl) != ('total' in l_clean):
                                continue
                            if len(lbl) > 8 and (lbl == l_clean):
                                used_bs_indices.add(idx)
                                return lbl, v
                        return None, None

                    if 'LTM' not in bal_df.columns and latest_fy in bal_df.columns:
                        ltm_bal_col = []
                        for _, row in bal_df.iterrows():
                            concept = str(row.get('concept', ''))
                            label = str(row.get('label', ''))
                            fy_val = row.get(latest_fy)
                            val = None
                            m_lbl, v_match = find_bs_match(concept, label)
                            if m_lbl:
                                val = v_match
                            ltm_bal_col.append(val)
                        bal_df.insert(bal_df.columns.get_loc(latest_fy), 'LTM', ltm_bal_col)

                    # Población de LTM en cf_df
                    if cf_df is not None and 'LTM' not in cf_df.columns and latest_fy in cf_df.columns:
                        cfo_ltm, capex_ltm = None, None
                        
                        col_curr_cf, col_prev_cf = None, None
                        active_cf_tbl = cf_o_tbl if cf_o_tbl is not None else cf_i_tbl
                        if active_cf_tbl is not None:
                            for dur_kw in ['nine', '9', 'six', '6', 'three', '3']:
                                c_curr, c_prev = None, None
                                for c_idx in range(active_cf_tbl.shape[1]):
                                    hdr = ' '.join(active_cf_tbl.iloc[:4, c_idx].astype(str).tolist()).lower()
                                    if dur_kw in hdr:
                                        if str(curr_yr) in hdr and c_curr is None: c_curr = c_idx
                                        elif str(prev_yr) in hdr and c_prev is None: c_prev = c_idx
                                if c_curr is not None and c_prev is not None:
                                    col_curr_cf, col_prev_cf = c_curr, c_prev
                                    break
                            if col_curr_cf is None:
                                for c_idx in range(active_cf_tbl.shape[1]):
                                    hdr = ' '.join(active_cf_tbl.iloc[:4, c_idx].astype(str).tolist()).lower()
                                    if str(curr_yr) in hdr and col_curr_cf is None: col_curr_cf = c_idx
                                    elif str(prev_yr) in hdr and col_prev_cf is None: col_prev_cf = c_idx
                        if col_curr_cf is None:
                            col_curr_cf = 3 if (active_cf_tbl is not None and active_cf_tbl.shape[1] > 3) else 1
                            col_prev_cf = 5 if (active_cf_tbl is not None and active_cf_tbl.shape[1] > 5) else (col_curr_cf + 1 if active_cf_tbl is not None and active_cf_tbl.shape[1] > col_curr_cf + 1 else None)

                        if cf_o_tbl is not None:
                            for _, r in cf_o_tbl.iterrows():
                                r_lbl = clean_txt(r[0])
                                if 'cash flows generated from' in r_lbl or 'used in operating activities' in r_lbl:
                                    vc = _clean_val(r[col_curr_cf])
                                    vp = _clean_val(r[col_prev_cf]) if col_prev_cf is not None else None
                                    if vc is not None and vp is not None:
                                        fy_cfo = None
                                        for _, cr in cf_df.iterrows():
                                            c_cn = str(cr.get('concept', '')).lower()
                                            if 'abstract' in c_cn:
                                                continue
                                            if 'operatingactivities' in c_cn or 'cashflowsfromusedinoperatingactivities' in c_cn:
                                                val_chk = cr.get(latest_fy)
                                                if pd.notna(val_chk):
                                                    fy_cfo = val_chk
                                                    break
                                        if pd.notna(fy_cfo):
                                            cfo_ltm = float(fy_cfo) - (vp * cf_scale) + (vc * cf_scale)
                        if cf_i_tbl is not None:
                            capex_c, capex_p = 0.0, 0.0
                            for _, r in cf_i_tbl.iterrows():
                                r_lbl = clean_txt(r[0])
                                if any(k in r_lbl for k in ['acquisition of property', 'purchase of property', 'acquisition and development of intangible', 'additions to property']):
                                    vc = _clean_val(r[col_curr_cf])
                                    vp = _clean_val(r[col_prev_cf]) if col_prev_cf is not None else None
                                    if vc is not None: capex_c += abs(vc * cf_scale)
                                    if vp is not None: capex_p += abs(vp * cf_scale)
                            fy_capex = 0.0
                            for _, cr in cf_df.iterrows():
                                c_cn = str(cr.get('concept', '')).lower()
                                if 'abstract' in c_cn:
                                    continue
                                if any(k in c_cn for k in ['intangibleassets', 'productiveassets', 'propertyplantandequipment', 'propertyplantequipment']):
                                    val_chk = cr.get(latest_fy)
                                    if pd.notna(val_chk):
                                        fy_capex += abs(float(val_chk))
                            if fy_capex > 0:
                                capex_ltm = fy_capex - capex_p + capex_c

                        # Parser de recompras de acciones en tabla de financiación 6-K (cf_f_tbl)
                        rep_ltm = None
                        if cf_f_tbl is not None:
                            rep_c, rep_p = None, None
                            for _, r in cf_f_tbl.iterrows():
                                r_lbl = clean_txt(r[0])
                                if any(k in r_lbl for k in ['share repurchase', 'repurchase of common stock', 'purchase of treasury shares', 'nu_sharesrepurchased', 'purchase of own shares', 'repurchase of shares']):
                                    vc = _clean_val(r[col_curr_cf])
                                    vp = _clean_val(r[col_prev_cf]) if col_prev_cf is not None else None
                                    if vc is not None:
                                        rep_c = abs(vc * cf_scale)
                                    if vp is not None:
                                        rep_p = abs(vp * cf_scale)
                                    break

                            if rep_c is not None:
                                # Buscar si el concepto tenía valor en latest_fy
                                fy_rep = None
                                for _, cr in cf_df.iterrows():
                                    c_cn = str(cr.get('concept', '')).lower()
                                    if 'abstract' in c_cn:
                                        continue
                                    if any(k in c_cn for k in ['sharesrepurchased', 'paymentsforpurchaseofownshares', 'repurchaseofcommonstock', 'purchaseoftreasuryshares', 'paymentstorepurchasecommonstock']):
                                        val_chk = cr.get(latest_fy)
                                        if pd.notna(val_chk) and float(val_chk) != 0.0:
                                            fy_rep = abs(float(val_chk))
                                        break

                                # Cálculo dinámico de LTM para recompras sin año base:
                                # Si el concepto tenía valor nulo o cero en latest_fy, asignar directamente el valor interino actual
                                if fy_rep is not None and fy_rep > 0:
                                    rep_ltm = fy_rep - (rep_p or 0.0) + rep_c
                                else:
                                    rep_ltm = rep_c

                        ltm_cf_col = []
                        rep_matched_in_cf = False
                        for _, row in cf_df.iterrows():
                            c_name = str(row.get('concept', '')).lower()
                            fy_val = row.get(latest_fy)
                            val = None
                            if 'abstract' in c_name:
                                val = None
                            elif ('operatingactivities' in c_name or 'cashflowsfromusedinoperatingactivities' in c_name) and cfo_ltm is not None:
                                val = cfo_ltm
                            elif any(k in c_name for k in ['intangibleassets', 'productiveassets', 'propertyplantandequipment', 'propertyplantequipment']) and capex_ltm is not None:
                                val = capex_ltm
                            elif any(k in c_name for k in ['sharesrepurchased', 'paymentsforpurchaseofownshares', 'repurchaseofcommonstock', 'purchaseoftreasuryshares', 'paymentstorepurchasecommonstock']) and rep_ltm is not None:
                                val = rep_ltm
                                rep_matched_in_cf = True
                            ltm_cf_col.append(val)
                        cf_df.insert(cf_df.columns.get_loc(latest_fy), 'LTM', ltm_cf_col)

                        # Incorporar la fila extraída a cf_df si no existía el concepto para que se exporte a cash_flow_detail
                        if rep_ltm is not None and not rep_matched_in_cf:
                            prefix = str(cf_df['concept'].iloc[0]).split('_')[0] if (len(cf_df) > 0 and '_' in str(cf_df['concept'].iloc[0])) else None
                            cand_concept = f"{prefix}_SharesRepurchased" if prefix else 'PaymentsForPurchaseOfOwnShares'
                            new_row = {col: None for col in cf_df.columns}
                            new_row['concept'] = cand_concept
                            new_row['label'] = 'Repurchase of shares'
                            new_row['standard_concept'] = 'PaymentsForPurchaseOfOwnShares'
                            new_row['LTM'] = rep_ltm
                            cf_df.loc[len(cf_df)] = new_row

                    print(f"[SEC Extractor] Parser 6-K exitoso: {filing.primary_document} incorporado a LTM con estados IS, BS y CF.")
                    return True
            except Exception as e:
                continue
    except Exception as e:
        print(f"[SEC Extractor] Nota en parser 6-K: {e}")
    return False

def convert_xb_statement_to_df(stmt_rows):
    """Convierte la lista de diccionarios de un rol XBRL en DataFrame con columnas FYxxxx."""
    data = []
    for r in stmt_rows:
        row_dict = {
            'concept': str(r.get('concept', '')).strip(),
            'label': str(r.get('label', '')).strip()
        }
        vals = r.get('values', {})
        if isinstance(vals, dict):
            for p_k, v in vals.items():
                m = re.search(r'(\d{4})', str(p_k))
                if m and v != '' and pd.notna(v):
                    try:
                        row_dict[f"FY{m.group(1)}"] = float(v)
                    except (ValueError, TypeError):
                        pass
        data.append(row_dict)
    return pd.DataFrame(data)


def merge_annual_statement_df(source_df, target_df, annual_fys, updated_cells=None, overwrite_if_newer=False):
    """
    Fusiona conceptos y valores de source_df en target_df.
    Aplica Latest Filed Priority: si overwrite_if_newer=True o si se suministra updated_cells,
    los reportes anuales más recientes tienen precedencia y actualizan reexpresiones / reformulaciones
    de ejercicios comparativos (ej. FY2023 restated en FY2024/FY2025).
    """
    if source_df is None or source_df.empty:
        return
    if updated_cells is None:
        updated_cells = set()

    for _, s_row in source_df.iterrows():
        c_concept = str(s_row.get('concept', '')).strip()
        if not c_concept or c_concept == 'nan':
            continue
        c_token = c_concept.split(':')[-1].split('_')[-1].lower()
        
        match_idx = -1
        for t_idx, t_row in target_df.iterrows():
            t_concept = str(t_row.get('concept', '')).strip()
            t_token = t_concept.split(':')[-1].split('_')[-1].lower()
            if t_token == c_token:
                match_idx = t_idx
                break
                
        if match_idx >= 0:
            for fy in annual_fys:
                if fy in source_df.columns and fy in target_df.columns:
                    sv = s_row.get(fy)
                    cell_key = (c_token, fy)
                    if pd.notna(sv) and sv != '':
                        try:
                            f_sv = float(sv)
                            tv = target_df.at[match_idx, fy]
                            if overwrite_if_newer:
                                if cell_key not in updated_cells:
                                    target_df.at[match_idx, fy] = f_sv
                                    updated_cells.add(cell_key)
                            else:
                                if (tv is None or pd.isna(tv)) and cell_key not in updated_cells:
                                    target_df.at[match_idx, fy] = f_sv
                                    updated_cells.add(cell_key)
                        except (ValueError, TypeError):
                            pass
        else:
            new_row_dict = {"concept": c_concept, "label": str(s_row.get('label', c_concept))}
            has_any = False
            for fy in annual_fys:
                if fy in source_df.columns:
                    val = s_row.get(fy)
                    if pd.notna(val) and val != '':
                        try:
                            f_val = float(val)
                            new_row_dict[fy] = f_val
                            has_any = True
                            if overwrite_if_newer:
                                updated_cells.add((c_token, fy))
                        except (ValueError, TypeError):
                            new_row_dict[fy] = None
                    else:
                        new_row_dict[fy] = None
                else:
                    new_row_dict[fy] = None
            if has_any:
                target_df.loc[len(target_df)] = new_row_dict


def enrich_annual_statements_with_individual_filings(company, inc_df, bal_df, cf_df, annual_fys):
    """
    Enriquece los estados contables de 10 años con los formularios anuales individuales (10-K o 20-F).
    Permite capturar conceptos contables modernos, extensiones o ejercicios recientes (Latest Filed Priority).
    """
    latest_fy = annual_fys[0] if annual_fys else None
    try:
        ann_filings = company.get_filings(form="10-K")
        if not ann_filings:
            ann_filings = company.get_filings(form="20-F")
        if ann_filings and len(ann_filings) > 0:
            updated_cells_inc = set()
            updated_cells_bal = set()
            updated_cells_cf = set()
            for doc_filing in ann_filings[:10]:
                doc_single = doc_filing.obj()
                if not doc_single or not doc_single.financials:
                    continue
                # 1. Detectar si el reporte anual individual contiene ejercicios fiscales más recientes (ej. FY2025)
                new_fys_detected = []
                for stmt_name in ['income_statement', 'balance_sheet', 'cash_flow_statement']:
                    s_check = getattr(doc_single.financials, stmt_name, None)
                    if s_check:
                        s_chk_obj = s_check()
                        if s_chk_obj is not None:
                            chk_df = s_chk_obj.to_dataframe()
                            if chk_df is not None and not chk_df.empty:
                                for c in chk_df.columns:
                                    m = re.search(r'(\d{4})', str(c))
                                    if m and not str(c).startswith('level') and not str(c).startswith('dim'):
                                        tag = f"FY{m.group(1)}"
                                        if tag not in annual_fys and tag not in new_fys_detected:
                                            new_fys_detected.append(tag)
                if new_fys_detected:
                    print(f"[SEC Extractor] ¡Nuevos ejercicios anuales detectados en filing ({doc_filing.form})!: {new_fys_detected}")
                    annual_fys = sorted(list(dict.fromkeys(new_fys_detected + annual_fys)), key=lambda x: int(re.search(r'\d+', x).group(0)) if re.search(r'\d+', x) else 0, reverse=True)
                    latest_fy = annual_fys[0]
                    for nfy in new_fys_detected:
                        for target_d in [inc_df, bal_df, cf_df]:
                            if nfy not in target_d.columns:
                                target_d[nfy] = None

                stmts_to_merge = [
                    ('cash_flow_statement', cf_df, updated_cells_cf),
                    ('income_statement', inc_df, updated_cells_inc),
                    ('balance_sheet', bal_df, updated_cells_bal)
                ]
                for stmt_attr, target_df, up_cells in stmts_to_merge:
                    stmt_fn = getattr(doc_single.financials, stmt_attr, None)
                    if stmt_fn:
                        s_obj = stmt_fn()
                        if s_obj is not None:
                            s_raw_df = s_obj.to_dataframe()
                            if s_raw_df is not None and not s_raw_df.empty:
                                s_ren = {}
                                for c in s_raw_df.columns:
                                    m = re.search(r'(\d{4})', str(c))
                                    if m and not str(c).startswith('level') and not str(c).startswith('dim'):
                                        s_ren[c] = f"FY{m.group(1)}"
                                s_df = s_raw_df.rename(columns=s_ren)
                                merge_annual_statement_df(s_df, target_df, annual_fys, updated_cells=up_cells, overwrite_if_newer=True)

                # También verificar roles de XBRL para StatementsOfProfitOrLoss si income_statement no trajo las partidas
                xb = getattr(doc_single.financials, 'xb', None)
                if xb:
                    try:
                        all_stmts = xb.get_all_statements()
                        for s_meta in all_stmts:
                            rn = str(s_meta.get('role_name', '')).lower()
                            defi = str(s_meta.get('definition', '')).lower()
                            if ('profit' in rn or 'profit' in defi or 'loss' in rn) and 'comprehensive' not in rn and 'comprehensive' not in defi:
                                xb_rows = xb.get_statement(s_meta.get('role'))
                                if xb_rows and isinstance(xb_rows, list):
                                    xb_df = convert_xb_statement_to_df(xb_rows)
                                    if not xb_df.empty:
                                        merge_annual_statement_df(xb_df, inc_df, annual_fys, updated_cells=updated_cells_inc, overwrite_if_newer=True)
                    except Exception:
                        pass
    except Exception as e:
        print(f"[SEC Extractor] Nota al enriquecer con reportes anuales individuales: {e}")
    return annual_fys, latest_fy


def compute_and_inject_ltm_columns(
    inc_df, bal_df, cf_df,
    q_inc, q_cf,
    inc_ttm_df, cf_ttm_df, bal_mrq_df,
    facts_df, latest_fy, latest_mrq_date=None
):
    """
    Calcula e inyecta la columna 'LTM' (Trailing Twelve Months / MRQ) en inc_df, bal_df y cf_df.
    """
    print("[SEC Extractor] Calculando métricas LTM (Trailing Twelve Months)...")
    # --- Income Statement LTM ---
    # Detectar columnas trimestrales y YTD
    all_q_cols = [c for c in q_inc.columns if any(ch.isdigit() for ch in str(c)) and ('Q' in str(c) or 'YTD' in str(c) or '202' in str(c))] if q_inc is not None else []
    ytd_cols_inc = [c for c in all_q_cols if 'YTD' in str(c)]
    if not ytd_cols_inc:
        ytd_cols_inc = all_q_cols
    ytd_curr_inc = sorted(ytd_cols_inc, reverse=True)[0] if len(ytd_cols_inc) >= 1 else None
    ytd_prev_inc = sorted(ytd_cols_inc, reverse=True)[1] if len(ytd_cols_inc) >= 2 else None
    
    q_cols_ttm = [col for col in inc_ttm_df.columns if col.startswith('Q')] if inc_ttm_df is not None else []
    latest_q_ttm = q_cols_ttm[0] if q_cols_ttm else None
    ltm_inc_map = {}
    if inc_ttm_df is not None and latest_q_ttm:
        for _, row in inc_ttm_df.iterrows():
            lbl = str(row.get('label', '')).strip()
            val = row.get(latest_q_ttm)
            if pd.notna(val):
                ltm_inc_map[lbl.lower()] = float(val)
                
    ltm_vals_inc = []
    for _, row in inc_df.iterrows():
        c_name = str(row.get('concept', '')).strip()
        lbl = str(row.get('label', '')).strip()
        fy_val = row.get(latest_fy)
        val = None
        
        # Conceptos de acciones (point in time: saldo al cierre del trimestre) vs EPS (flujo acumulado 12M)
        is_share_count = any(k in c_name.lower() or k in lbl.lower() for k in ['sharesoutstanding', 'numberofshares'])
        is_per_share = any(k in c_name.lower() or k in lbl.lower() for k in ['pershare', 'per_share', 'per share'])
        
        c_tok = c_name.split(':')[-1].split('_')[-1].lower()
        if is_share_count and q_inc is not None and ytd_curr_inc:
            q_toks = q_inc['concept'].astype(str).apply(lambda x: x.split(':')[-1].split('_')[-1].lower())
            match_q = q_inc[(q_toks == c_tok) | q_inc['concept'].astype(str).str.lower().str.endswith(c_name.lower()) | (q_inc['concept'].astype(str).str.lower() == c_name.lower())]
            if not match_q.empty:
                v_curr = match_q.iloc[0].get(ytd_curr_inc)
                if pd.notna(v_curr):
                    try:
                        val = float(v_curr)
                    except (ValueError, TypeError):
                        pass
        elif q_inc is not None and ytd_curr_inc and ytd_prev_inc and pd.notna(fy_val):
            q_toks = q_inc['concept'].astype(str).apply(lambda x: x.split(':')[-1].split('_')[-1].lower())
            match_q = q_inc[(q_toks == c_tok) | q_inc['concept'].astype(str).str.lower().str.endswith(c_name.lower()) | (q_inc['concept'].astype(str).str.lower() == c_name.lower())]
            if not match_q.empty:
                q_row = match_q.iloc[0]
                v_curr = q_row.get(ytd_curr_inc)
                v_prev = q_row.get(ytd_prev_inc)
                if pd.notna(v_curr) and pd.notna(v_prev):
                    try:
                        val = float(fy_val) + float(v_curr) - float(v_prev)
                    except (ValueError, TypeError):
                        pass
        if val is None and not is_share_count and lbl.lower() in ltm_inc_map:
            val = ltm_inc_map[lbl.lower()]
        ltm_vals_inc.append(val)
        
    inc_df.insert(inc_df.columns.get_loc(latest_fy), 'LTM', ltm_vals_inc)
    
    # Corroborar y calibrar que EPS y acciones en LTM reflejen el estándar GAAP institucional (suma/promedio 4 trimestres)
    try:
        q4_eps_d = get_ltm_quarterly_metric(facts_df, XBRL_TAXONOMY_MAP["eps_diluted"], mode='sum') if facts_df is not None else None
        q4_eps_b = get_ltm_quarterly_metric(facts_df, XBRL_TAXONOMY_MAP["eps_basic"], mode='sum') if facts_df is not None else None
        q4_sh_d = get_ltm_quarterly_metric(facts_df, XBRL_TAXONOMY_MAP["shares_diluted"], mode='avg') if facts_df is not None else None
        q4_sh_b = get_ltm_quarterly_metric(facts_df, XBRL_TAXONOMY_MAP["shares_basic"], mode='avg') if facts_df is not None else None
        
        clean_sh_d_toks = {_clean_concept_token(x) for x in XBRL_TAXONOMY_MAP["shares_diluted"]}
        clean_sh_b_toks = {_clean_concept_token(x) for x in XBRL_TAXONOMY_MAP["shares_basic"]}
        clean_eps_d_toks = {_clean_concept_token(x) for x in XBRL_TAXONOMY_MAP["eps_diluted"]}
        clean_eps_b_toks = {_clean_concept_token(x) for x in XBRL_TAXONOMY_MAP["eps_basic"]}

        for idx_r, r in inc_df.iterrows():
            cn = str(r.get('concept', ''))
            cn_tok = _clean_concept_token(cn)
            if 'adjustment' in cn.lower():
                continue
            if cn_tok in clean_eps_d_toks:
                if q4_eps_d is not None and q4_eps_d > 0:
                    inc_df.at[idx_r, 'LTM'] = q4_eps_d
                    print(f"[SEC Extractor] LTM Diluted EPS calibrado por suma de 4 trimestres: ${q4_eps_d}")
            elif cn_tok in clean_eps_b_toks:
                if q4_eps_b is not None and q4_eps_b > 0:
                    inc_df.at[idx_r, 'LTM'] = q4_eps_b
                    print(f"[SEC Extractor] LTM Basic EPS calibrado por suma de 4 trimestres: ${q4_eps_b}")
            elif cn_tok in clean_sh_d_toks:
                if q4_sh_d is not None and q4_sh_d > 0:
                    inc_df.at[idx_r, 'LTM'] = q4_sh_d
                    print(f"[SEC Extractor] LTM Diluted Shares calibrado por promedio de 4 trimestres: {q4_sh_d:,.0f}")
            elif cn_tok in clean_sh_b_toks:
                if q4_sh_b is not None and q4_sh_b > 0:
                    inc_df.at[idx_r, 'LTM'] = q4_sh_b
                    print(f"[SEC Extractor] LTM Basic Shares calibrado por promedio de 4 trimestres: {q4_sh_b:,.0f}")

        # Respaldo por identidad contable NI / Shares si no se detectaron trimestres
        if q4_eps_d is None:
            ni_match = inc_df[inc_df['concept'].astype(str).str.lower().str.contains('netincome', na=False)]
            sh_match = inc_df[inc_df['concept'].astype(str).str.lower().str.contains('dilutedshares', na=False) | inc_df['concept'].astype(str).str.lower().str.contains('sharesoutstandingdiluted', na=False)]
            if not ni_match.empty and not sh_match.empty:
                ni_val_ltm = float(ni_match.iloc[0].get('LTM', 0))
                sh_val_ltm = float(sh_match.iloc[0].get('LTM', 0))
                if ni_val_ltm > 0 and sh_val_ltm > 0:
                    exp_ltm_eps = round(ni_val_ltm / sh_val_ltm, 2)
                    for idx_r, r in inc_df.iterrows():
                        cn = str(r.get('concept', '')).lower()
                        if 'earningspersharediluted' in cn or 'dilutedearningspershare' in cn:
                            cur_v = r.get('LTM')
                            if cur_v is None or (exp_ltm_eps > 0 and cur_v < exp_ltm_eps * 0.4):
                                inc_df.at[idx_r, 'LTM'] = exp_ltm_eps
                                print(f"[SEC Extractor] LTM Diluted EPS calibrado a 12 meses acumulados (NI/sh): ${exp_ltm_eps} (en vez de ${cur_v})")
        if q4_eps_b is None:
            ni_match = inc_df[inc_df['concept'].astype(str).str.lower().str.contains('netincome', na=False)]
            sh_b_match = inc_df[(inc_df['concept'].astype(str).str.lower().str.contains('shares', na=False) | inc_df['concept'].astype(str).str.lower().str.contains('weightedaverage', na=False)) & (~inc_df['concept'].astype(str).str.lower().str.contains('diluted', na=False)) & (~inc_df['concept'].astype(str).str.lower().str.contains('adjusted', na=False))]
            if not ni_match.empty and not sh_b_match.empty:
                ni_val_ltm = float(ni_match.iloc[0].get('LTM', 0))
                sh_b_val_ltm = float(sh_b_match.iloc[0].get('LTM', 0))
                if ni_val_ltm > 0 and sh_b_val_ltm > 0:
                    exp_ltm_eps_b = round(ni_val_ltm / sh_b_val_ltm, 2)
                    for idx_r, r in inc_df.iterrows():
                        cn = str(r.get('concept', '')).lower()
                        if ('earningspershare' in cn or 'basicearnings' in cn) and 'diluted' not in cn:
                            cur_v = r.get('LTM')
                            if cur_v is None or (exp_ltm_eps_b > 0 and cur_v < exp_ltm_eps_b * 0.4):
                                inc_df.at[idx_r, 'LTM'] = exp_ltm_eps_b
                                print(f"[SEC Extractor] LTM Basic EPS calibrado a 12 meses acumulados (NI/sh): ${exp_ltm_eps_b} (en vez de ${cur_v})")
    except Exception as e:
        print(f"[SEC Extractor] Nota sobre calibración de EPS y Acciones LTM: {e}")
    
    # --- Balance Sheet MRQ for LTM ---
    mrq_cols = [c for c in bal_mrq_df.columns if c.startswith('Q')] if bal_mrq_df is not None else []
    latest_mrq_col = mrq_cols[0] if mrq_cols else None
    
    # Determinar fecha MRQ para rescate en Company Facts si bal_mrq_df viene condensado
    if latest_mrq_date is None and facts_df is not None and not facts_df.empty and 'period_end' in facts_df.columns:
        asset_matches = facts_df[facts_df['concept'].astype(str).str.endswith(':Assets') | facts_df['concept'].astype(str).str.endswith(':StockholdersEquity')]
        if not asset_matches.empty:
            latest_mrq_date = asset_matches['period_end'].dropna().max()
        else:
            latest_mrq_date = facts_df['period_end'].dropna().max()

    ltm_vals_bal = []
    for _, row in bal_df.iterrows():
        c_name = str(row.get('concept', '')).strip()
        fy_val = row.get(latest_fy)
        val = None

        # Conceptos abstractos de balance (encabezados de sección) no llevan importe
        if c_name.lower().endswith('abstract') or str(row.get('label', '')).lower().endswith('[abstract]'):
            ltm_vals_bal.append(None)
            continue

        if bal_mrq_df is not None and latest_mrq_col:
            c_tok = c_name.split(':')[-1].split('_')[-1].lower()
            b_toks = bal_mrq_df['concept'].astype(str).apply(lambda x: x.split(':')[-1].split('_')[-1].lower())
            match_b = bal_mrq_df[(b_toks == c_tok) | bal_mrq_df['concept'].astype(str).str.lower().str.endswith(c_name.lower()) | (bal_mrq_df['concept'].astype(str).str.lower() == c_name.lower())]
            if not match_b.empty:
                v = match_b.iloc[0].get(latest_mrq_col)
                if pd.notna(v):
                    try:
                        val = float(v)
                    except (ValueError, TypeError):
                        pass
        # Si no está en el balance condensado del 10-Q, buscar en facts_df al cierre de MRQ
        if val is None and facts_df is not None and not facts_df.empty:
            c_tok = c_name.split(':')[-1].split('_')[-1]
            cand_search = [c_name, c_tok]
            is_sti_row = any(w in c_tok.lower() for w in ['marketablesecurities', 'shortterminvestments', 'securitiescurrent'])
            for k_tax, cands_tax in {**XBRL_TAXONOMY_MAP, **BANKING_TAXONOMY_MAP}.items():
                if any(cand.lower() == c_tok.lower() for cand in cands_tax):
                    cand_search.extend(cands_tax)
            if is_sti_row:
                cand_search.extend(XBRL_TAXONOMY_MAP["marketable_securities_current"])
                val = get_mrq_fact_sum(facts_df, ["DebtSecuritiesCurrent", "EquitySecuritiesFvNi"], mrq_date=latest_mrq_date)
                if val is None:
                    val = get_mrq_fact(facts_df, cand_search, mrq_date=latest_mrq_date)
            else:
                val = get_mrq_fact(facts_df, cand_search, mrq_date=latest_mrq_date)
        ltm_vals_bal.append(val)
        
    bal_df.insert(bal_df.columns.get_loc(latest_fy), 'LTM', ltm_vals_bal)
    
    # --- Cash Flow Statement LTM ---
    all_q_cols_cf = [c for c in q_cf.columns if any(ch.isdigit() for ch in str(c)) and ('Q' in str(c) or 'YTD' in str(c) or '202' in str(c))] if q_cf is not None else []
    ytd_cols_cf = [c for c in all_q_cols_cf if 'YTD' in str(c)]
    if not ytd_cols_cf:
        ytd_cols_cf = all_q_cols_cf
    ytd_curr_cf = sorted(ytd_cols_cf, reverse=True)[0] if len(ytd_cols_cf) >= 1 else None
    ytd_prev_cf = sorted(ytd_cols_cf, reverse=True)[1] if len(ytd_cols_cf) >= 2 else None
    # Detectar datos directos de TTM para Cash Flow si están disponibles
    q_cols_cf_ttm = [col for col in cf_ttm_df.columns if col.startswith('Q')] if cf_ttm_df is not None else []
    latest_q_cf_ttm = q_cols_cf_ttm[0] if q_cols_cf_ttm else None
    ltm_cf_map = {}
    if cf_ttm_df is not None and latest_q_cf_ttm:
        for _, row_cf in cf_ttm_df.iterrows():
            lbl_cf = str(row_cf.get('label', '')).strip().lower()
            c_cf = str(row_cf.get('concept', '')).strip()
            val_cf = row_cf.get(latest_q_cf_ttm)
            if pd.notna(val_cf):
                try:
                    ltm_cf_map[lbl_cf] = float(val_cf)
                    if c_cf:
                        ltm_cf_map[c_cf.split(':')[-1].split('_')[-1].lower()] = float(val_cf)
                except (ValueError, TypeError):
                    pass

    ENDING_CASH_CONCEPTS = {
        "cashcashequivalentsrestrictedcashandrestrictedcashequivalents",
        "cashandcashequivalentsatcarryingvalue",
        "cashandcashequivalents",
        "cash",
        "restrictedcashandcashequivalentsatcarryingvalue",
        "restrictedcashandcashequivalentsnoncurrent",
        "restrictedcashandcashequivalents",
        "cashandcashequivalentsfairvaluedisclosure",
    }
    BEGINNING_CASH_CONCEPTS = {
        "cashcashequivalentsrestrictedcashandrestrictedcashequivalentsbeginningofperiod",
        "cashandcashequivalentsatbeginningofperiod",
        "cashandcashequivalentsatcarryingvaluebeginningofperiod",
        "cashbeginningofperiod",
    }

    ltm_vals_cf = []
    for _, row in cf_df.iterrows():
        c_name = str(row.get('concept', '')).strip()
        fy_val = row.get(latest_fy)
        val = None
        c_tok = _clean_concept_token(c_name)
        is_ending_cash = c_tok in ENDING_CASH_CONCEPTS
        is_beg_cash = c_tok in BEGINNING_CASH_CONCEPTS

        if q_cf is not None and ytd_curr_cf and ytd_prev_cf:
            q_toks = q_cf['concept'].astype(str).apply(_clean_concept_token)
            # Coincidencia exacta de token o concepto para evitar colisiones con prefijos como EffectOfExchangeRateOn...
            match_cf = q_cf[(q_toks == c_tok) | (q_cf['concept'].astype(str).str.lower() == c_name.lower())]
            if match_cf.empty:
                match_cf = q_cf[q_cf['concept'].astype(str).str.lower().str.endswith(':' + c_tok) | q_cf['concept'].astype(str).str.lower().str.endswith('_' + c_tok)]
            # Si no encuentra coincidencia exacta pero es un concepto de CapEx, buscar variantes en la taxonomía
            if match_cf.empty and any(cand.lower() in c_name.lower() for cand in XBRL_TAXONOMY_MAP["capital_expenditures"]):
                for cand in XBRL_TAXONOMY_MAP["capital_expenditures"]:
                    c_clean = _clean_concept_token(cand)
                    cand_match = q_cf[(q_toks == c_clean) | (q_cf['concept'].astype(str).str.lower() == cand.lower())]
                    if not cand_match.empty:
                        match_cf = cand_match
                        break
            if not match_cf.empty:
                q_row = match_cf.iloc[0]
                v_curr = q_row.get(ytd_curr_cf)
                v_prev = q_row.get(ytd_prev_cf)
                if is_ending_cash:
                    # El saldo de cierre de LTM es el saldo puntual a la fecha de corte del trimestre más reciente (MRQ)
                    if pd.notna(v_curr):
                        try:
                            val = float(v_curr)
                        except (ValueError, TypeError):
                            pass
                elif is_beg_cash:
                    # El saldo de inicio del trailing 12M es el saldo puntual a la fecha de inicio (12 meses antes)
                    if pd.notna(v_prev):
                        try:
                            val = float(v_prev)
                        except (ValueError, TypeError):
                            pass
                elif pd.notna(v_curr) and pd.notna(v_prev) and pd.notna(fy_val):
                    try:
                        f_fy = float(fy_val)
                        f_curr = float(v_curr)
                        f_prev = float(v_prev)
                        val = f_fy + f_curr - f_prev
                    except (ValueError, TypeError):
                        pass

        # Respaldo para ending_cash desde facts_df si no vino en q_cf
        if val is None and is_ending_cash and facts_df is not None and not facts_df.empty:
            cand_search = [c_name, c_tok]
            val = get_mrq_fact(facts_df, cand_search, mrq_date=latest_mrq_date)

        if val is None and ltm_cf_map and not is_ending_cash and not is_beg_cash:
            if c_tok in ltm_cf_map:
                val = ltm_cf_map[c_tok]
            elif str(row.get('label', '')).strip().lower() in ltm_cf_map:
                val = ltm_cf_map[str(row.get('label', '')).strip().lower()]
        if val is None and pd.notna(fy_val) and any(cand.lower() in c_name.lower() for cand in XBRL_TAXONOMY_MAP["acquisitions_ma"]):
            try:
                val = float(fy_val)
            except (ValueError, TypeError):
                pass
        ltm_vals_cf.append(val)
        
    cf_df.insert(cf_df.columns.get_loc(latest_fy), 'LTM', ltm_vals_cf)
    
