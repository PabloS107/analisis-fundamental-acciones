"""
sec_statement_reconciler.py - Construcción de estados financieros As-Reported fieles a la SEC
(emparejamiento histórico de 3 niveles con candado dimensional) y validación/sanitización
post-extracción (homogeneización de signos, etiquetas bilingües y resolución canónica).
"""

import logging
import re
import pandas as pd

logger = logging.getLogger(__name__)

_OCI_CONCEPT_PATTERN = r'OtherComprehensiveIncome|ComprehensiveIncomeNetOfTax|StatementOfIncomeAndComprehensiveIncome'

try:
    from pipeline.financial_bilingual_map import get_spanish_clarification, get_spanish_label
except ImportError:
    try:
        from financial_bilingual_map import get_spanish_clarification, get_spanish_label
    except ImportError:
        def get_spanish_clarification(label, concept=None):
            return None
        def get_spanish_label(label, concept=None):
            return label

try:
    from financial_taxonomy import (
        XBRL_TAXONOMY_MAP,
        BANKING_TAXONOMY_MAP,
        REIT_TAXONOMY_MAP,
        INSURANCE_TAXONOMY_MAP,
        PLATFORM_TAXONOMY_MAP,
    )
except ImportError:
    try:
        from ..financial_taxonomy import (
            XBRL_TAXONOMY_MAP,
            BANKING_TAXONOMY_MAP,
            REIT_TAXONOMY_MAP,
            INSURANCE_TAXONOMY_MAP,
            PLATFORM_TAXONOMY_MAP,
        )
    except ImportError:
        from pipeline.financial_taxonomy import (
            XBRL_TAXONOMY_MAP,
            BANKING_TAXONOMY_MAP,
            REIT_TAXONOMY_MAP,
            INSURANCE_TAXONOMY_MAP,
            PLATFORM_TAXONOMY_MAP,
        )

try:
    from .sec_xbrl_ltm import (
        normalize_fiscal_year,
        _clean_concept_token,
        _safe_float,
        sanitize_multiclass_eps_df,
        get_mrq_fact,
        get_ltm_quarterly_metric,
    )
except ImportError:
    try:
        from sec_modules.sec_xbrl_ltm import (
            normalize_fiscal_year,
            _clean_concept_token,
            _safe_float,
            sanitize_multiclass_eps_df,
            get_mrq_fact,
            get_ltm_quarterly_metric,
        )
    except ImportError:
        from pipeline.sec_modules.sec_xbrl_ltm import (
            normalize_fiscal_year,
            _clean_concept_token,
            _safe_float,
            sanitize_multiclass_eps_df,
            get_mrq_fact,
            get_ltm_quarterly_metric,
        )


def _filter_face_statement_df(df: pd.DataFrame, s_name: str) -> pd.DataFrame:
    """Filtra líneas de reclasificación/OCI, desambigua EPS multi-clase y aísla partidas de carátula."""
    if df is None or df.empty:
        return pd.DataFrame()
    work = df.copy()
    if "label" in work.columns:
        work = work[~work["label"].astype(str).str.contains(r'-\s*(?:As reported|Reclassification)', case=False, regex=True)].copy()

    if "dimension" in work.columns:
        is_pure_face = (work["dimension"] == False) | work["dimension"].isna() | (work["dimension"].astype(str).isin(["", "nan", "None"]))
        if s_name == "income_statement":
            is_prod_serv = (
                work["dimension_member"].astype(str).str.contains(r'ProductMember|ServiceMember', case=False, na=False)
                if "dimension_member" in work.columns else False
            )
            if not getattr(is_prod_serv, "any", lambda: False)() and "label" in work.columns:
                is_prod_serv = work["label"].astype(str).str.strip().str.lower().isin(["products", "services"]) & (work["dimension"] == True)
            face = work[is_pure_face | is_prod_serv].copy()
        else:
            face = work[is_pure_face].copy()
    elif "is_breakdown" in work.columns:
        face = work[work["is_breakdown"] == False].copy()
    else:
        face = work

    if s_name == "income_statement":
        if "concept" in face.columns:
            face = face[~face["concept"].astype(str).str.contains(_OCI_CONCEPT_PATTERN, case=False, regex=True)].copy()
        sanitize_multiclass_eps_df(face)
    return face


def _filter_by_dimension_lock(cand_df: pd.DataFrame, is_row_dim: bool, row_dim_member: str, clean_lbl: str) -> pd.DataFrame:
    """Aplica candado dimensional estricto al emparejar filas entre 10-K y 10-Q/hist_df."""
    if cand_df is None or cand_df.empty:
        return pd.DataFrame()
    if is_row_dim and "dimension_member" in cand_df.columns:
        filtered = cand_df[cand_df["dimension_member"].astype(str).str.strip() == row_dim_member]
        if not filtered.empty or not clean_lbl or "label" not in cand_df.columns:
            return filtered
    if is_row_dim and "label" in cand_df.columns:
        return cand_df[cand_df["label"].astype(str).str.strip().str.lower() == clean_lbl.lower()]
    if not is_row_dim and "dimension" in cand_df.columns:
        return cand_df[(cand_df["dimension"] == False) | cand_df["dimension"].isna() | cand_df["dimension"].astype(str).isin(["", "nan", "None"])]
    return cand_df


def _normalize_statement_row_signs(s_name: str, conc: str, clean_lbl: str, vals: dict) -> dict:
    """Homogeneiza signos algebraicos en toda la serie de una fila As-Reported."""
    c_low = conc.lower()
    l_low = clean_lbl.lower()
    if s_name == "income_statement":
        is_expense = (
            any(ind in c_low or ind in l_low for ind in (
                'cost of', 'costof', 'expense', 'expenses', 'charges', 'provision',
                'research', 'selling', 'administrative', 'impairment', 'benefitslosses',
            ))
            and not any(excl in c_low for excl in ('income', 'revenue', 'gain', 'operatingincomeloss', 'netincomeloss', 'profitloss'))
        )
        if is_expense:
            for p_k, v in vals.items():
                if v is not None:
                    vals[p_k] = abs(v)
    elif s_name == "balance_sheet":
        is_equity_or_fluctuating = any(x in c_low for x in (
            'retainedearnings', 'accumulateddeficit', 'accumulatedothercomprehensiveincome',
            'othercomprehensiveincome', 'treasurystock', 'accumulatedgain', 'accumulatedloss',
        ))
        if not is_equity_or_fluctuating:
            valid_nums = [v for p_k, v in vals.items() if v is not None and v != 0.0 and p_k != "LTM"]
            if valid_nums:
                pos_count = sum(1 for v in valid_nums if v > 0)
                neg_count = sum(1 for v in valid_nums if v < 0)
                tot_cnt = len(valid_nums)
                if pos_count / tot_cnt >= 0.8:
                    for p_k, v in vals.items():
                        if v is not None:
                            vals[p_k] = abs(v)
                elif neg_count / tot_cnt >= 0.8:
                    for p_k, v in vals.items():
                        if v is not None:
                            vals[p_k] = -abs(v)
    return vals


def _insert_new_10q_face_rows(face_df: pd.DataFrame, q_face: pd.DataFrame, fy_cols_map: dict) -> pd.DataFrame:
    """Incorpora partidas legítimas de carátula presentes en el 10-Q sin disparar FutureWarning."""
    if q_face is None or q_face.empty or face_df is None or face_df.empty:
        return face_df

    k_toks = set(face_df["concept"].astype(str).apply(_clean_concept_token)) if "concept" in face_df.columns else set()
    k_lbls = {re.sub(r'[^a-zA-Z0-9]', '', str(l).lower()) for l in face_df["label"].dropna()} if "label" in face_df.columns else set()
    new_q_rows = []

    for q_idx in range(len(q_face)):
        r_q = q_face.iloc[q_idx]
        q_tok = _clean_concept_token(r_q.get("concept", ""))
        q_lbl = re.sub(r'[^a-zA-Z0-9]', '', str(r_q.get("label", "")).lower())
        if not q_tok or (q_tok in k_toks) or (q_lbl in k_lbls) or bool(r_q.get("abstract", False)):
            continue

        target_insert_pos = None
        for prev_i in range(q_idx - 1, -1, -1):
            cand_tok = _clean_concept_token(q_face.iloc[prev_i].get("concept", ""))
            if cand_tok in k_toks:
                for f_i in range(len(face_df)):
                    if _clean_concept_token(face_df.iloc[f_i].get("concept", "")) == cand_tok:
                        target_insert_pos = f_i + 1
                        break
                if target_insert_pos is not None:
                    break

        if target_insert_pos is None:
            for next_i in range(q_idx + 1, len(q_face)):
                cand_tok = _clean_concept_token(q_face.iloc[next_i].get("concept", ""))
                if cand_tok in k_toks:
                    for f_i in range(len(face_df)):
                        if _clean_concept_token(face_df.iloc[f_i].get("concept", "")) == cand_tok:
                            target_insert_pos = f_i
                            break
                    if target_insert_pos is not None:
                        break

        new_q_rows.append((target_insert_pos, r_q))
        k_toks.add(q_tok)

    if not new_q_rows:
        return face_df

    rows_list = face_df.to_dict("records")
    face_cols = list(face_df.columns)
    for ins_pos, r_q in sorted(new_q_rows, key=lambda x: (x[0] if x[0] is not None else 999999), reverse=True):
        new_row_dict = {col: None for col in face_cols}
        for col_q in r_q.index:
            if col_q in new_row_dict:
                new_row_dict[col_q] = r_q[col_q]
            else:
                norm_q = normalize_fiscal_year(col_q)
                if norm_q in fy_cols_map:
                    new_row_dict[fy_cols_map[norm_q]] = r_q[col_q]
        new_row_dict["concept"] = r_q.get("concept")
        new_row_dict["label"] = r_q.get("label")
        new_row_dict["abstract"] = False
        new_row_dict["level"] = r_q.get("level", 3)
        new_row_dict["dimension"] = False
        pos = len(rows_list) if ins_pos is None else min(ins_pos, len(rows_list))
        rows_list.insert(pos, new_row_dict)

    return pd.DataFrame(rows_list, columns=face_cols)


def _match_historical_row(
    hist_df: pd.DataFrame,
    hist_concept_toks: pd.Series,
    hist_labels_clean: pd.Series,
    face_concept_tokens: set,
    all_tax_maps: list,
    used_hist_indices: set,
    conc_tok: str,
    clean_lbl: str,
    is_row_dim: bool,
    row_dim_member: str,
):
    """Emparejamiento histórico de 3 niveles en `hist_df` con candado dimensional."""
    if hist_df is None or hist_df.empty:
        return None
    h_cand_df = _filter_by_dimension_lock(hist_df, is_row_dim, row_dim_member, clean_lbl)
    if h_cand_df.empty:
        return None
    h_unclaimed = h_cand_df[~h_cand_df.index.isin(used_hist_indices)]
    if h_unclaimed.empty:
        return None

    h_toks = hist_concept_toks.loc[h_unclaimed.index]
    h_lbls = hist_labels_clean.loc[h_unclaimed.index]
    lbl_clean_val = re.sub(r'[^a-zA-Z0-9]', '', clean_lbl.lower()) if clean_lbl else ""
    matched_h_row = None

    if conc_tok:
        m1 = h_unclaimed[h_toks == conc_tok]
        if len(m1) == 1:
            matched_h_row = m1.iloc[0]
        elif len(m1) > 1:
            m1_lbl = m1[h_lbls.loc[m1.index] == lbl_clean_val]
            matched_h_row = m1_lbl.iloc[0] if not m1_lbl.empty else m1.iloc[0]

    if matched_h_row is None and lbl_clean_val:
        m2 = h_unclaimed[h_lbls == lbl_clean_val]
        if not m2.empty:
            matched_h_row = m2.iloc[0]

    if matched_h_row is None and conc_tok and not is_row_dim:
        for tmap in all_tax_maps:
            for cands in tmap.values():
                tok_cands = [_clean_concept_token(c_item) for c_item in cands]
                if conc_tok in tok_cands:
                    allowed = [tok for tok in tok_cands if (tok == conc_tok) or (tok not in face_concept_tokens)]
                    if allowed:
                        m3 = h_unclaimed[h_toks.isin(allowed)]
                        if not m3.empty:
                            matched_h_row = m3.iloc[0]
                            break
            if matched_h_row is not None:
                break

    if matched_h_row is not None and hasattr(matched_h_row, 'name'):
        used_hist_indices.add(matched_h_row.name)
    return matched_h_row


def _compute_as_reported_ltm_val(
    is_flow: bool,
    q_face: pd.DataFrame,
    q_mrq_col,
    ytd_curr,
    ytd_prev,
    matched_h_row,
    hist_cols_norm: dict,
    facts_df,
    latest_fy: str,
    row_vals: dict,
    conc_tok: str,
    clean_lbl: str,
    is_row_dim: bool,
    row_dim_member: str,
):
    """Resuelve el importe LTM/MRQ para una fila As-Reported respetando candado dimensional y Regla 6."""
    ltm_val = None
    if not is_flow and not q_face.empty and q_mrq_col:
        q_cand = _filter_by_dimension_lock(q_face, is_row_dim, row_dim_member, clean_lbl)
        if not q_cand.empty:
            q_toks = q_cand["concept"].astype(str).apply(_clean_concept_token)
            q_match = q_cand[(q_toks == conc_tok) & (q_cand["label"].astype(str).str.strip().str.lower() == clean_lbl.lower())]
            if q_match.empty:
                q_match = q_cand[q_toks == conc_tok]
            if not q_match.empty:
                ltm_val = _safe_float(q_match.iloc[0].get(q_mrq_col))

    if ltm_val is None and matched_h_row is not None and "LTM" in hist_cols_norm:
        ltm_val = _safe_float(matched_h_row.get(hist_cols_norm["LTM"]))

    if ltm_val is None and is_flow and not q_face.empty:
        q_cand = _filter_by_dimension_lock(q_face, is_row_dim, row_dim_member, clean_lbl)
        if not q_cand.empty:
            q_toks = q_cand["concept"].astype(str).apply(_clean_concept_token)
            q_match = q_cand[(q_toks == conc_tok) & (q_cand["label"].astype(str).str.strip().str.lower() == clean_lbl.lower())]
            if q_match.empty:
                q_match = q_cand[q_toks == conc_tok]
            if q_match.empty and clean_lbl:
                lbl_norm = re.sub(r'[^a-zA-Z0-9]', '', clean_lbl.lower())
                q_lbls = q_cand["label"].astype(str).apply(lambda s: re.sub(r'[^a-zA-Z0-9]', '', str(s).lower()))
                q_match = q_cand[q_lbls == lbl_norm]
            if not q_match.empty and ytd_curr and ytd_prev and row_vals.get(latest_fy) is not None:
                v_curr = _safe_float(q_match.iloc[0].get(ytd_curr))
                v_prev = _safe_float(q_match.iloc[0].get(ytd_prev))
                if v_curr is not None and v_prev is not None:
                    ltm_val = row_vals[latest_fy] + v_curr - v_prev

    if ltm_val is None and is_flow and facts_df is not None and not facts_df.empty and conc_tok and not is_row_dim:
        q4_sum = get_ltm_quarterly_metric(facts_df, [conc_tok], mode='sum')
        if q4_sum is not None:
            ltm_val = float(q4_sum)

    is_apic_row = ('additionalpaidincapital' in conc_tok) or ('additional paid-in' in clean_lbl.lower()) or ('paid-in capital' in clean_lbl.lower())
    if not is_flow and is_apic_row and ltm_val is None and facts_df is not None and not facts_df.empty:
        ltm_val = get_mrq_fact(facts_df, ['AdditionalPaidInCapital', 'AdditionalPaidInCapitalCommonStock'])
        if ltm_val is None:
            eq_m = get_mrq_fact(facts_df, ['StockholdersEquity', 'StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest'])
            re_m = get_mrq_fact(facts_df, ['RetainedEarningsAccumulatedDeficit', 'RetainedEarnings'])
            aoci_m = get_mrq_fact(facts_df, ['AccumulatedOtherComprehensiveIncomeLossNetOfTax']) or 0.0
            treas_m = get_mrq_fact(facts_df, ['TreasuryStockValue', 'TreasuryStockCommonValue']) or 0.0
            if eq_m is not None and re_m is not None:
                derived_apic = round(eq_m - re_m - aoci_m + abs(treas_m), 2)
                if derived_apic > 0:
                    ltm_val = derived_apic

    return ltm_val


def build_as_reported_statements(
    company,
    annual_fys,
    latest_fy,
    inc_df,
    bal_df,
    cf_df,
    latest_10k_obj=None,
    latest_10q_obj=None,
    q_inc=None,
    q_bal=None,
    q_cf=None,
    facts_df=None
):
    """
    Construye los tres estados financieros principales bajo formato As-Reported (Filing Presentation fiel a la SEC).
    Preserva jerarquía, líneas oficiales, notas anuales y reconciliación de 10 años + LTM mediante emparejamiento de 3 niveles.
    Aplica candado dimensional estricto, homogeneización de signos y prohibición de defaults ficticios (Regla 6).
    """
    all_tax_maps = [XBRL_TAXONOMY_MAP, BANKING_TAXONOMY_MAP, REIT_TAXONOMY_MAP, INSURANCE_TAXONOMY_MAP, PLATFORM_TAXONOMY_MAP]
    as_reported = {}
    q_fallback_map = {"income_statement": q_inc, "balance_sheet": q_bal, "cash_flow_statement": q_cf}
    statements_meta = [
        ("income_statement", "income_statement", "income_statement", inc_df, True),
        ("balance_sheet", "balance_sheet", "balance_sheet", bal_df, False),
        ("cash_flow_statement", "cash_flow_statement", "cash_flow_statement", cf_df, True),
    ]

    for s_name, k_attr, q_attr, hist_df, is_flow in statements_meta:
        k_stmt = getattr(latest_10k_obj, k_attr, None) if latest_10k_obj else None
        if not k_stmt and latest_10k_obj and getattr(latest_10k_obj, 'financials', None):
            k_fn = getattr(latest_10k_obj.financials, k_attr, None)
            k_stmt = k_fn() if k_fn else None

        if not k_stmt:
            if hist_df is not None and not hist_df.empty:
                fallback_rows = []
                for _, r in hist_df.iterrows():
                    lbl = str(r.get("label", "")).strip()
                    conc = str(r.get("concept", "")).strip()
                    if not lbl and not conc:
                        continue
                    row_vals = {p: _safe_float(r.get(p)) for p in (["LTM"] + annual_fys) if p in hist_df.columns}
                    fallback_rows.append({
                        "label": lbl or conc,
                        "clarification": get_spanish_clarification(lbl, conc),
                        "concept": conc,
                        "level": int(r.get("depth", 0)) if pd.notna(r.get("depth")) else 0,
                        "is_abstract": bool(r.get("is_abstract", False)),
                        "is_total": bool(r.get("is_total", False)),
                        "values": row_vals,
                    })
                as_reported[s_name] = fallback_rows
            continue

        try:
            k_df = k_stmt.to_dataframe()
        except Exception as exc:
            logger.debug("Error convirtiendo carátula 10-K %s a DataFrame: %s", s_name, exc)
            k_df = None
        if k_df is None or k_df.empty:
            continue

        face_df = _filter_face_statement_df(k_df, s_name)

        q_stmt = getattr(latest_10q_obj, q_attr, None) if latest_10q_obj else None
        if not q_stmt and latest_10q_obj and getattr(latest_10q_obj, 'financials', None):
            q_fn = getattr(latest_10q_obj.financials, q_attr, None)
            q_stmt = q_fn() if q_fn else None

        q_df = None
        if q_stmt:
            try:
                q_df = q_stmt.to_dataframe()
            except Exception as exc:
                logger.debug("Error convirtiendo carátula 10-Q %s a DataFrame: %s", s_name, exc)
        else:
            q_df = q_fallback_map.get(s_name)

        q_face = _filter_face_statement_df(q_df, s_name) if (q_df is not None and not q_df.empty) else pd.DataFrame()

        fy_cols_map = {
            normalize_fiscal_year(c): c
            for c in face_df.columns if normalize_fiscal_year(c).startswith("FY")
        }
        face_df = _insert_new_10q_face_rows(face_df, q_face, fy_cols_map)

        q_mrq_col = ytd_curr = ytd_prev = None
        if not q_face.empty:
            if not is_flow:
                mrq_cols = sorted([col for col in q_face.columns if re.match(r'^\d{4}-\d{2}-\d{2}$', str(col))], reverse=True)
                q_mrq_col = mrq_cols[0] if mrq_cols else None
            else:
                ytd_cols = [c for c in q_face.columns if 'YTD' in str(c)] or [
                    c for c in q_face.columns if any(ch.isdigit() for ch in str(c)) and ('Q' in str(c) or '202' in str(c))
                ]
                ytd_cols_sorted = sorted(ytd_cols, reverse=True)
                ytd_curr = ytd_cols_sorted[0] if len(ytd_cols_sorted) >= 1 else None
                ytd_prev = ytd_cols_sorted[1] if len(ytd_cols_sorted) >= 2 else None

        hist_concept_toks = hist_labels_clean = None
        hist_cols_norm = {}
        if hist_df is not None and not hist_df.empty:
            hist_concept_toks = hist_df["concept"].apply(_clean_concept_token) if "concept" in hist_df.columns else pd.Series([""] * len(hist_df), index=hist_df.index)
            hist_labels_clean = (
                hist_df["label"].astype(str).apply(lambda x: re.sub(r'[^a-zA-Z0-9]', '', x.lower()))
                if "label" in hist_df.columns else pd.Series([""] * len(hist_df), index=hist_df.index)
            )
            for col_h in hist_df.columns:
                norm_h = normalize_fiscal_year(col_h)
                if norm_h.startswith("FY") or norm_h == "LTM":
                    hist_cols_norm[norm_h] = col_h

        face_concept_tokens = set(face_df["concept"].astype(str).apply(_clean_concept_token)) if "concept" in face_df.columns else set()
        rows = []
        seen_cash_flow_ending_cash = False
        seen_statement_concepts = set()
        used_hist_indices = set()

        for _, r in face_df.iterrows():
            lbl = str(r.get("label", "")).strip()
            conc = str(r.get("concept", "")).strip()
            is_abs = bool(r.get("abstract", False))
            lvl = int(r.get("level", 0)) if pd.notna(r.get("level")) else 0
            is_tot = ("total" in lbl.lower()) or bool(r.get("is_total", False))
            conc_tok = _clean_concept_token(conc)

            if s_name == "income_statement" and not is_abs and conc_tok == "netincomeloss":
                if "netincomeloss" in seen_statement_concepts:
                    continue
                seen_statement_concepts.add("netincomeloss")

            is_row_dim = bool(r.get("dimension", False)) or (pd.notna(r.get("dimension_member")) and str(r.get("dimension_member")).strip() not in ("", "nan", "None"))
            row_dim_member = str(r.get("dimension_member", "")).strip() if is_row_dim else ""

            clean_lbl, clean_detail = lbl, None
            if ";" in lbl and len(lbl) > 50:
                parts = [p.strip() for p in lbl.split(";") if p.strip()]
                clean_lbl, clean_detail = parts[0], "; ".join(parts[1:])
            elif "(" in lbl and ")" in lbl and len(lbl) > 80:
                m_par = re.search(r'\(([^)]+)\)', lbl)
                if m_par and len(m_par.group(1)) > 30 and any(w in m_par.group(1).lower() for w in ("share", "par value", "note", "class")):
                    clean_detail = m_par.group(1)
                    clean_lbl = re.sub(r'\s*\([^)]+\)', '', lbl).strip()

            base_clarif = get_spanish_clarification(clean_lbl, conc)
            clarif = f"{base_clarif} · {clean_detail}" if (clean_detail and base_clarif) else (clean_detail or base_clarif)

            if s_name == "cash_flow_statement" and ("cash" in conc_tok and "equivalents" in conc_tok):
                if "beginning" in clean_lbl.lower() or "start" in clean_lbl.lower():
                    clean_lbl = "Cash, cash equivalents and restricted cash, beginning of period"
                elif seen_cash_flow_ending_cash:
                    continue
                else:
                    seen_cash_flow_ending_cash = True

            matched_h_row = _match_historical_row(
                hist_df, hist_concept_toks, hist_labels_clean, face_concept_tokens,
                all_tax_maps, used_hist_indices, conc_tok, clean_lbl, is_row_dim, row_dim_member,
            )

            row_vals = {}
            for p in annual_fys:
                val = _safe_float(r.get(fy_cols_map[p])) if p in fy_cols_map else None
                if val is None and matched_h_row is not None and p in hist_cols_norm:
                    val = _safe_float(matched_h_row.get(hist_cols_norm[p]))
                if val is None and conc_tok and not is_row_dim and hist_df is not None and not hist_df.empty and p in hist_cols_norm:
                    for tmap in all_tax_maps:
                        for cands in tmap.values():
                            tok_cands = [_clean_concept_token(c_item) for c_item in cands]
                            if conc_tok in tok_cands:
                                allowed_cands = [tok for tok in tok_cands if (tok == conc_tok) or (tok not in face_concept_tokens)]
                                if allowed_cands:
                                    for _, syn_r in hist_df[hist_concept_toks.isin(allowed_cands)].iterrows():
                                        val = _safe_float(syn_r.get(hist_cols_norm[p]))
                                        if val is not None:
                                            break
                                if val is not None:
                                    break
                        if val is not None:
                            break
                row_vals[p] = val

            row_vals["LTM"] = None if is_abs else _compute_as_reported_ltm_val(
                is_flow, q_face, q_mrq_col, ytd_curr, ytd_prev,
                matched_h_row, hist_cols_norm, facts_df, latest_fy, row_vals,
                conc_tok, clean_lbl, is_row_dim, row_dim_member,
            )
            _normalize_statement_row_signs(s_name, conc, clean_lbl, row_vals)

            rows.append({
                "label": clean_lbl,
                "clarification": clarif,
                "concept": conc,
                "level": lvl,
                "is_abstract": is_abs,
                "is_total": is_tot,
                "values": row_vals,
            })

        as_reported[s_name] = rows
        print(f"[SEC Extractor] {s_name}: {len(rows)} partidas As-Reported extraídas fielmente de la SEC.")

    return as_reported


def _sync_short_term_investments_and_cash_ltm(as_rep_bs: list, can_summary: dict, bs_detail: dict) -> None:
    """Sincroniza Inversiones a Corto Plazo LTM con carátula de Balance Sheet si difieren materialmente."""
    for r in as_rep_bs:
        c_tok = _clean_concept_token(r.get("concept", ""))
        if c_tok in ("marketablesecuritiescurrent", "shortterminvestments"):
            v_ltm = r.get("values", {}).get("LTM")
            if v_ltm is not None and float(v_ltm) > 0:
                can_sti = can_summary.get("short_term_investments", {}).get("LTM")
                if can_sti is not None and abs(float(v_ltm) - float(can_sti)) > 1000.0:
                    can_summary["short_term_investments"]["LTM"] = float(v_ltm)
                    for k_bs in ("us-gaap_MarketableSecuritiesCurrent", "MarketableSecuritiesCurrent"):
                        if k_bs in bs_detail:
                            bs_detail[k_bs]["values"]["LTM"] = float(v_ltm)
                    c_v = can_summary.get("cash_and_equivalents", {}).get("LTM") or 0.0
                    tot_liq = round(c_v + float(v_ltm), 2)
                    can_summary["total_liquid_cash"]["LTM"] = tot_liq
                    tot_d = can_summary.get("total_debt", {}).get("LTM") or 0.0
                    can_summary["net_debt"]["LTM"] = round(tot_d - tot_liq, 2)
            break


def _sync_dividends_and_cf_signs(as_rep_cf: list, can_summary: dict, cf_detail: dict) -> None:
    """Sincroniza Dividendos LTM y signos de Flujo de Caja As-Reported con el detalle oficial SEC."""
    for r in as_rep_cf:
        c_tok = _clean_concept_token(r.get("concept", ""))
        if c_tok in ("paymentsofdividends", "paymentsofdividendscommonstock"):
            v_ltm = r.get("values", {}).get("LTM")
            if v_ltm is not None and float(v_ltm) != 0.0:
                audited_div = abs(float(v_ltm))
                can_summary.setdefault("dividends_paid", {})["LTM"] = audited_div
                for k_cf in ("PaymentsOfDividends", "us-gaap_PaymentsOfDividends", "DividendsPaid", "PaymentsOfDividendsCommonStock"):
                    if k_cf in cf_detail and isinstance(cf_detail[k_cf], dict) and "values" in cf_detail[k_cf]:
                        cf_detail[k_cf]["values"]["LTM"] = -audited_div if float(v_ltm) < 0 else audited_div
            break

    for r in as_rep_cf:
        conc = r.get("concept", "")
        if conc in cf_detail and isinstance(cf_detail[conc], dict):
            det_vals = cf_detail[conc].get("values", {})
            for p_k, det_v in det_vals.items():
                if det_v is not None and r.get("values", {}).get(p_k) is not None and abs(r["values"][p_k]) == abs(det_v):
                    r["values"][p_k] = det_v


def _resolve_as_reported_dimensional_collisions(as_reported: dict, details_map: dict, latest_fy: str) -> None:
    """Resuelve colisiones dimensionales donde dos filas comparten el mismo LTM no nulo pero difieren en latest_fy."""
    for s_name, rows in as_reported.items():
        s_det = details_map.get(s_name, {})
        non_abs = [r for r in rows if not r.get("is_abstract") and r.get("values", {}).get("LTM") is not None]
        for i in range(len(non_abs)):
            for j in range(i + 1, len(non_abs)):
                r1, r2 = non_abs[i], non_abs[j]
                v1_ltm, v2_ltm = r1["values"].get("LTM"), r2["values"].get("LTM")
                v1_fy, v2_fy = r1["values"].get(latest_fy), r2["values"].get(latest_fy)
                if (
                    v1_fy is not None and v2_fy is not None and v1_fy != v2_fy
                    and v1_fy != 0.0 and v2_fy != 0.0 and v1_ltm == v2_ltm and v1_ltm != 0.0
                ):
                    c1_tok = _clean_concept_token(r1.get("concept", ""))
                    c2_tok = _clean_concept_token(r2.get("concept", ""))
                    r1_det_val = next(
                        (v["values"]["LTM"] for k, v in s_det.items() if _clean_concept_token(k) == c1_tok and v.get("values", {}).get("LTM") is not None),
                        None,
                    )
                    r2_det_val = next(
                        (v["values"]["LTM"] for k, v in s_det.items() if _clean_concept_token(k) == c2_tok and v.get("values", {}).get("LTM") is not None),
                        None,
                    )
                    if r1_det_val == v1_ltm and r2_det_val != v2_ltm:
                        r2["values"]["LTM"] = r2_det_val
                    elif r2_det_val == v2_ltm and r1_det_val != v1_ltm:
                        r1["values"]["LTM"] = r1_det_val


def sanitize_and_validate_statements(full_dataset: dict) -> dict:
    """
    Candado Automático Post-Extracción (Reglas 1, 4 y 6):
    1. Homogeneiza signos algebraicos en toda la serie de cada fila en as_reported_statements.
    2. Enriquece cada fila con `spanish_label` y `orig_tooltip`.
    3. Garantiza coherencia en Balance LTM y resuelve colisiones dimensionales.
    """
    try:
        from pipeline.financial_bilingual_map import get_spanish_label
    except ImportError:
        try:
            from financial_bilingual_map import get_spanish_label
        except ImportError:
            from ..financial_bilingual_map import get_spanish_label

    as_reported = full_dataset.get("as_reported_statements", {})
    if not as_reported:
        return full_dataset

    for s_name, rows in as_reported.items():
        cleaned_rows = []
        seen_keys = set()
        for row in rows:
            lbl = row.get("label", "").strip()
            conc = row.get("concept", "")
            if any(term in lbl.lower() for term in ("- as reported", "- reclassification")):
                continue
            dedup_key = (lbl, conc)
            if dedup_key in seen_keys:
                continue
            seen_keys.add(dedup_key)

            row["spanish_label"] = get_spanish_label(lbl, conc)
            row["orig_tooltip"] = f"{lbl} ({conc})" if conc else lbl
            row["values"] = _normalize_statement_row_signs(s_name, conc, lbl, row.get("values", {}))
            cleaned_rows.append(row)
        as_reported[s_name] = cleaned_rows

    can_summary = full_dataset.get("canonical_summary", {})
    bs_detail = full_dataset.get("balance_sheet_detail", {})
    cf_detail = full_dataset.get("cash_flow_detail", {})
    inc_detail = full_dataset.get("income_statement_detail", {})

    _sync_short_term_investments_and_cash_ltm(as_reported.get("balance_sheet", []), can_summary, bs_detail)
    _sync_dividends_and_cf_signs(as_reported.get("cash_flow_statement", []), can_summary, cf_detail)

    fys = [x for x in full_dataset.get("fiscal_years", []) if x != "LTM"]
    if fys:
        _resolve_as_reported_dimensional_collisions(
            as_reported,
            {"income_statement": inc_detail, "balance_sheet": bs_detail, "cash_flow_statement": cf_detail},
            fys[0],
        )

    full_dataset["as_reported_statements"] = as_reported
    try:
        from pipeline.canonical_resolvers import (
            resolve_canonical_balance_sheet,
            resolve_canonical_income_statement,
            resolve_canonical_capital_flows,
            resolve_canonical_cash_flow,
        )
    except ImportError:
        from canonical_resolvers import (
            resolve_canonical_balance_sheet,
            resolve_canonical_income_statement,
            resolve_canonical_capital_flows,
            resolve_canonical_cash_flow,
        )
    periods_res = full_dataset.get("fiscal_years", [])[:11]
    arch_res = full_dataset.get("archetype") or ("FINANCIAL_BANKING" if full_dataset.get("is_financial") else "STANDARD_CORPORATE")
    cap_flows_res = resolve_canonical_capital_flows(full_dataset, periods_res)
    full_dataset["resolved_canonical_statements"] = {
        "balance_sheet": resolve_canonical_balance_sheet(full_dataset, periods_res, archetype=arch_res),
        "income_statement": resolve_canonical_income_statement(full_dataset, periods_res, archetype=arch_res),
        "capital_flows": cap_flows_res,
        "cash_flow": resolve_canonical_cash_flow(full_dataset, periods_res, capital_flows=cap_flows_res, archetype=arch_res),
    }
    return full_dataset
