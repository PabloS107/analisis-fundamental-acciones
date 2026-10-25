"""
sec_statement_reconciler.py - Construcción de estados financieros As-Reported fieles a la SEC
(emparejamiento histórico de 3 niveles con candado dimensional) y validación/sanitización
post-extracción (homogeneización de signos, etiquetas bilingües y resolución canónica).
"""

import re
import pandas as pd

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
        get_mrq_fact,
        get_ltm_quarterly_metric,
    )
except ImportError:
    try:
        from sec_modules.sec_xbrl_ltm import (
            normalize_fiscal_year,
            _clean_concept_token,
            get_mrq_fact,
            get_ltm_quarterly_metric,
        )
    except ImportError:
        from pipeline.sec_modules.sec_xbrl_ltm import (
            normalize_fiscal_year,
            _clean_concept_token,
            get_mrq_fact,
            get_ltm_quarterly_metric,
        )


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
    
    statements_meta = [
        ("income_statement", "income_statement", "income_statement", inc_df, True),
        ("balance_sheet", "balance_sheet", "balance_sheet", bal_df, False),
        ("cash_flow_statement", "cash_flow_statement", "cash_flow_statement", cf_df, True)
    ]
    
    for s_name, k_attr, q_attr, hist_df, is_flow in statements_meta:
        k_stmt = None
        if latest_10k_obj:
            k_stmt = getattr(latest_10k_obj, k_attr, None)
            if not k_stmt and hasattr(latest_10k_obj, 'financials') and latest_10k_obj.financials:
                k_fn = getattr(latest_10k_obj.financials, k_attr, None)
                if k_fn:
                    k_stmt = k_fn()
        
        if not k_stmt:
            if hist_df is not None and not hist_df.empty:
                fallback_rows = []
                for _, r in hist_df.iterrows():
                    lbl = str(r.get("label", "")).strip()
                    conc = str(r.get("concept", "")).strip()
                    if not lbl and not conc:
                        continue
                    row_vals = {}
                    for p in (["LTM"] + annual_fys):
                        if p in hist_df.columns:
                            v = r.get(p)
                            row_vals[p] = float(v) if pd.notna(v) else None
                    fallback_rows.append({
                        "label": lbl or conc,
                        "clarification": get_spanish_clarification(lbl, conc),
                        "concept": conc,
                        "level": int(r.get("depth", 0)) if pd.notna(r.get("depth")) else 0,
                        "is_abstract": bool(r.get("is_abstract", False)),
                        "is_total": bool(r.get("is_total", False)),
                        "values": row_vals
                    })
                as_reported[s_name] = fallback_rows
            continue

        try:
            k_df = k_stmt.to_dataframe()
        except Exception:
            k_df = None

        if k_df is None or k_df.empty:
            continue

        # Filtrar líneas de reclasificación de notas (- As reported, - Reclassification)
        if "label" in k_df.columns:
            k_df = k_df[~k_df["label"].astype(str).str.contains(r'-\s*(?:As reported|Reclassification)', case=False, regex=True)].copy()

        # Filtrado de líneas de carátula (Face-only items)
        if "dimension" in k_df.columns:
            if s_name == "income_statement":
                # En Income Statement, permitir la apertura oficial de carátula Product / Service (ej. AAPL, MELI)
                is_prod_serv = k_df["dimension_member"].astype(str).str.contains(r'ProductMember|ServiceMember', case=False, na=False) if "dimension_member" in k_df.columns else False
                if not is_prod_serv.any() and "label" in k_df.columns:
                    is_prod_serv = k_df["label"].astype(str).str.strip().str.lower().isin(["products", "services"]) & (k_df["dimension"] == True)
                is_pure_face = (k_df["dimension"] == False) | k_df["dimension"].isna() | (k_df["dimension"].astype(str).isin(["", "nan", "None"]))
                face_df = k_df[is_pure_face | is_prod_serv].copy()
            else:
                is_pure_face = (k_df["dimension"] == False) | k_df["dimension"].isna() | (k_df["dimension"].astype(str).isin(["", "nan", "None"]))
                face_df = k_df[is_pure_face].copy()
        elif "is_breakdown" in k_df.columns:
            face_df = k_df[k_df["is_breakdown"] == False].copy()
        else:
            face_df = k_df.copy()

        # Excluir filas de Other Comprehensive Income (OCI) del Income Statement principal (DECK, O, PGR)
        oci_pattern = r'OtherComprehensiveIncome|ComprehensiveIncomeNetOfTax|StatementOfIncomeAndComprehensiveIncome'
        if s_name == "income_statement" and "concept" in face_df.columns:
            face_df = face_df[~face_df["concept"].astype(str).str.contains(oci_pattern, case=False, regex=True)].copy()

        # Obtener 10-Q correspondiente
        q_stmt = None
        if latest_10q_obj:
            q_stmt = getattr(latest_10q_obj, q_attr, None)
            if not q_stmt and hasattr(latest_10q_obj, 'financials') and latest_10q_obj.financials:
                q_fn = getattr(latest_10q_obj.financials, q_attr, None)
                if q_fn:
                    q_stmt = q_fn()

        q_df = None
        if q_stmt:
            try:
                q_df = q_stmt.to_dataframe()
            except Exception:
                q_df = None
        elif s_name == "income_statement" and q_inc is not None:
            q_df = q_inc
        elif s_name == "balance_sheet" and q_bal is not None:
            q_df = q_bal
        elif s_name == "cash_flow_statement" and q_cf is not None:
            q_df = q_cf

        if q_df is not None and not q_df.empty:
            if "label" in q_df.columns:
                q_df = q_df[~q_df["label"].astype(str).str.contains(r'-\s*(?:As reported|Reclassification)', case=False, regex=True)].copy()
            if "dimension" in q_df.columns:
                if s_name == "income_statement":
                    is_prod_serv_q = q_df["dimension_member"].astype(str).str.contains(r'ProductMember|ServiceMember', case=False, na=False) if "dimension_member" in q_df.columns else False
                    if not is_prod_serv_q.any() and "label" in q_df.columns:
                        is_prod_serv_q = q_df["label"].astype(str).str.strip().str.lower().isin(["products", "services"]) & (q_df["dimension"] == True)
                    is_pure_q = (q_df["dimension"] == False) | q_df["dimension"].isna() | (q_df["dimension"].astype(str).isin(["", "nan", "None"]))
                    q_face = q_df[is_pure_q | is_prod_serv_q].copy()
                else:
                    is_pure_q = (q_df["dimension"] == False) | q_df["dimension"].isna() | (q_df["dimension"].astype(str).isin(["", "nan", "None"]))
                    q_face = q_df[is_pure_q].copy()
            elif "is_breakdown" in q_df.columns:
                q_face = q_df[q_df["is_breakdown"] == False].copy()
            else:
                q_face = q_df.copy()
            if s_name == "income_statement" and "concept" in q_face.columns:
                q_face = q_face[~q_face["concept"].astype(str).str.contains(oci_pattern, case=False, regex=True)].copy()
        else:
            q_face = pd.DataFrame()

        # Mapear columnas anuales del 10-K a FYxxxx
        fy_cols_map = {}
        for c in face_df.columns:
            norm_c = normalize_fiscal_year(c)
            if norm_c.startswith("FY"):
                fy_cols_map[norm_c] = c

        # Incorporar partidas legítimas de carátula presentes en el 10-Q que no existían en el 10-K anual
        if not q_face.empty and not face_df.empty:
            k_toks = set(face_df["concept"].astype(str).apply(_clean_concept_token)) if "concept" in face_df.columns else set()
            k_lbls = {re.sub(r'[^a-zA-Z0-9]', '', str(l).lower()) for l in face_df["label"].dropna()} if "label" in face_df.columns else set()
            new_q_rows = []
            for q_idx in range(len(q_face)):
                r_q = q_face.iloc[q_idx]
                q_conc = str(r_q.get("concept", "")).strip()
                q_tok = _clean_concept_token(q_conc)
                q_lbl = re.sub(r'[^a-zA-Z0-9]', '', str(r_q.get("label", "")).lower())
                is_abs_q = bool(r_q.get("abstract", False))
                if q_tok and (q_tok not in k_toks) and (q_lbl not in k_lbls) and not is_abs_q:
                    target_insert_pos = None
                    for prev_i in range(q_idx - 1, -1, -1):
                        cand_prev = q_face.iloc[prev_i]
                        cand_tok = _clean_concept_token(cand_prev.get("concept", ""))
                        if cand_tok in k_toks:
                            for f_i in range(len(face_df)):
                                if _clean_concept_token(face_df.iloc[f_i].get("concept", "")) == cand_tok:
                                    target_insert_pos = f_i + 1
                                    break
                            if target_insert_pos is not None:
                                break
                    if target_insert_pos is None:
                        for next_i in range(q_idx + 1, len(q_face)):
                            cand_next = q_face.iloc[next_i]
                            cand_tok = _clean_concept_token(cand_next.get("concept", ""))
                            if cand_tok in k_toks:
                                for f_i in range(len(face_df)):
                                    if _clean_concept_token(face_df.iloc[f_i].get("concept", "")) == cand_tok:
                                        target_insert_pos = f_i
                                        break
                                if target_insert_pos is not None:
                                    break
                    new_q_rows.append((target_insert_pos, r_q))
                    k_toks.add(q_tok)

            for ins_pos, r_q in sorted(new_q_rows, key=lambda x: (x[0] if x[0] is not None else 999999), reverse=True):
                new_row_dict = {col: None for col in face_df.columns}
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

                df_above = face_df.iloc[:ins_pos] if ins_pos is not None else face_df
                df_below = face_df.iloc[ins_pos:] if ins_pos is not None else pd.DataFrame(columns=face_df.columns)
                face_df = pd.concat([df_above, pd.DataFrame([new_row_dict]), df_below], ignore_index=True)

        # Detectar columnas relevantes en el 10-Q para LTM
        q_mrq_col = None
        ytd_curr = None
        ytd_prev = None
        q_curr = None
        if not q_face.empty:
            if not is_flow:
                mrq_cols = sorted([col for col in q_face.columns if re.match(r'^\d{4}-\d{2}-\d{2}$', str(col))], reverse=True)
                q_mrq_col = mrq_cols[0] if mrq_cols else None
            else:
                ytd_cols = [c for c in q_face.columns if 'YTD' in str(c)]
                if not ytd_cols:
                    ytd_cols = [c for c in q_face.columns if any(ch.isdigit() for ch in str(c)) and ('Q' in str(c) or '202' in str(c))]
                ytd_curr = sorted(ytd_cols, reverse=True)[0] if len(ytd_cols) >= 1 else None
                ytd_prev = sorted(ytd_cols, reverse=True)[1] if len(ytd_cols) >= 2 else None
                q_cols = [c for c in q_face.columns if re.search(r'\(Q\d\)', str(c))]
                q_curr = sorted(q_cols, reverse=True)[0] if q_cols else None

        # Preparar índices de búsqueda en hist_df
        hist_concept_toks = None
        hist_labels_clean = None
        hist_cols_norm = {}
        if hist_df is not None and not hist_df.empty:
            if "concept" in hist_df.columns:
                hist_concept_toks = hist_df["concept"].apply(_clean_concept_token)
            else:
                hist_concept_toks = pd.Series([""] * len(hist_df), index=hist_df.index)
            if "label" in hist_df.columns:
                hist_labels_clean = hist_df["label"].astype(str).apply(lambda x: re.sub(r'[^a-zA-Z0-9]', '', x.lower()))
            else:
                hist_labels_clean = pd.Series([""] * len(hist_df), index=hist_df.index)
            for col_h in hist_df.columns:
                norm_h = normalize_fiscal_year(col_h)
                if norm_h.startswith("FY") or norm_h == "LTM":
                    hist_cols_norm[norm_h] = col_h

        # Registrar conceptos explícitos presentes en la carátula para evitar usurpación en Nivel 3
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

            # Evitar filas duplicadas de NetIncomeLoss en Income Statement (PGR, O)
            if s_name == "income_statement" and not is_abs and conc_tok == "netincomeloss":
                if "netincomeloss" in seen_statement_concepts:
                    continue
                seen_statement_concepts.add("netincomeloss")

            # Candado dimensional
            is_row_dim = bool(r.get("dimension", False)) or (pd.notna(r.get("dimension_member")) and str(r.get("dimension_member")).strip() not in ("", "nan", "None"))
            row_dim_member = str(r.get("dimension_member", "")).strip() if is_row_dim else ""

            # Limpiar etiquetas excesivamente extensas (par value, shares authorized)
            clean_lbl = lbl
            clean_detail = None
            if ";" in lbl and len(lbl) > 50:
                parts = [p.strip() for p in lbl.split(";") if p.strip()]
                clean_lbl = parts[0]
                clean_detail = "; ".join(parts[1:])
            elif "(" in lbl and ")" in lbl and len(lbl) > 80:
                m_par = re.search(r'\(([^)]+)\)', lbl)
                if m_par and len(m_par.group(1)) > 30 and any(w in m_par.group(1).lower() for w in ["share", "par value", "note", "class"]):
                    clean_detail = m_par.group(1)
                    clean_lbl = re.sub(r'\s*\([^)]+\)', '', lbl).strip()

            base_clarif = get_spanish_clarification(clean_lbl, conc)
            if clean_detail:
                clarif = f"{base_clarif} · {clean_detail}" if base_clarif else clean_detail
            else:
                clarif = base_clarif

            # En Flujo de Efectivo, evitar duplicados del saldo final de caja
            is_cf_cash = (s_name == "cash_flow_statement") and ("cash" in conc_tok and "equivalents" in conc_tok)
            if is_cf_cash:
                if "beginning" in clean_lbl.lower() or "start" in clean_lbl.lower():
                    clean_lbl = "Cash, cash equivalents and restricted cash, beginning of period"
                elif seen_cash_flow_ending_cash:
                    continue
                else:
                    seen_cash_flow_ending_cash = True

            # Reconciliación Histórica de 3 Niveles en hist_df con candado dimensional
            matched_h_row = None
            if hist_df is not None and not hist_df.empty:
                if is_row_dim and "dimension_member" in hist_df.columns:
                    h_cand_df = hist_df[hist_df["dimension_member"].astype(str).str.strip() == row_dim_member]
                    if h_cand_df.empty and clean_lbl:
                        lbl_clean_val = re.sub(r'[^a-zA-Z0-9]', '', clean_lbl.lower())
                        h_cand_df = hist_df[hist_labels_clean == lbl_clean_val]
                elif is_row_dim and "label" in hist_df.columns:
                    lbl_clean_val = re.sub(r'[^a-zA-Z0-9]', '', clean_lbl.lower())
                    h_cand_df = hist_df[hist_labels_clean == lbl_clean_val]
                elif not is_row_dim and "dimension" in hist_df.columns:
                    h_cand_df = hist_df[(hist_df["dimension"] == False) | hist_df["dimension"].isna() | hist_df["dimension"].astype(str).isin(["", "nan", "None"])]
                else:
                    h_cand_df = hist_df

                h_cand_concept_toks = hist_concept_toks.loc[h_cand_df.index] if not h_cand_df.empty else pd.Series()
                h_cand_labels_clean = hist_labels_clean.loc[h_cand_df.index] if not h_cand_df.empty else pd.Series()

                # Filtrar filas de hist_df ya reclamadas por otras cuentas de la carátula
                h_unclaimed_cand_df = h_cand_df[~h_cand_df.index.isin(used_hist_indices)] if not h_cand_df.empty else pd.DataFrame()
                h_unclaimed_toks = h_cand_concept_toks.loc[h_unclaimed_cand_df.index] if not h_unclaimed_cand_df.empty else pd.Series()
                h_unclaimed_labels = h_cand_labels_clean.loc[h_unclaimed_cand_df.index] if not h_unclaimed_cand_df.empty else pd.Series()

                # Nivel 1: Coincidencia por token de concepto
                if conc_tok and not h_unclaimed_cand_df.empty:
                    m1 = h_unclaimed_cand_df[h_unclaimed_toks == conc_tok]
                    if len(m1) == 1:
                        matched_h_row = m1.iloc[0]
                    elif len(m1) > 1:
                        lbl_clean_val = re.sub(r'[^a-zA-Z0-9]', '', clean_lbl.lower())
                        m1_lbl = m1[h_unclaimed_labels.loc[m1.index] == lbl_clean_val]
                        matched_h_row = m1_lbl.iloc[0] if not m1_lbl.empty else m1.iloc[0]

                # Nivel 2: Coincidencia por nombre de cuenta en carátula limpia (solo si el concepto no entra en conflicto)
                if matched_h_row is None and clean_lbl and not h_unclaimed_cand_df.empty:
                    lbl_clean_val = re.sub(r'[^a-zA-Z0-9]', '', clean_lbl.lower())
                    if lbl_clean_val:
                        m2 = h_unclaimed_cand_df[h_unclaimed_labels == lbl_clean_val]
                        if not m2.empty:
                            matched_h_row = m2.iloc[0]

                # Nivel 3: Grupo sinónimo de taxonomía canónica (restringido para no usurpar cuentas de la carátula)
                if matched_h_row is None and conc_tok and not is_row_dim and not h_unclaimed_cand_df.empty:
                    for tmap in all_tax_maps:
                        for syn_group, cands in tmap.items():
                            tok_cands = [_clean_concept_token(c_item) for c_item in cands]
                            if conc_tok in tok_cands:
                                allowed_cands = [tok for tok in tok_cands if (tok == conc_tok) or (tok not in face_concept_tokens)]
                                if allowed_cands:
                                    m3 = h_unclaimed_cand_df[h_unclaimed_toks.isin(allowed_cands)]
                                    if not m3.empty:
                                        matched_h_row = m3.iloc[0]
                                        break
                        if matched_h_row is not None:
                            break

                if matched_h_row is not None and hasattr(matched_h_row, 'name'):
                    used_hist_indices.add(matched_h_row.name)

            # Extracción de importes anuales
            row_vals = {}
            for p in annual_fys:
                val = None
                # 1. Filing actual 10-K
                if p in fy_cols_map:
                    v_raw = r.get(fy_cols_map[p])
                    if pd.notna(v_raw):
                        try:
                            val = float(v_raw)
                        except (ValueError, TypeError):
                            val = None
                # 2. Histórico 10 años (hist_df)
                if val is None and matched_h_row is not None:
                    h_col = hist_cols_norm.get(p)
                    if h_col:
                        v_h = matched_h_row.get(h_col)
                        if pd.notna(v_h):
                            try:
                                val = float(v_h)
                            except (ValueError, TypeError):
                                val = None
                # 3. Respaldo por grupo sinónimo para año específico (respetando allowed_cands)
                if val is None and conc_tok and not is_row_dim and hist_df is not None and not hist_df.empty:
                    for tmap in all_tax_maps:
                        for syn_group, cands in tmap.items():
                            tok_cands = [_clean_concept_token(c_item) for c_item in cands]
                            if conc_tok in tok_cands:
                                allowed_cands = [tok for tok in tok_cands if (tok == conc_tok) or (tok not in face_concept_tokens)]
                                if allowed_cands:
                                    syn_matches = hist_df[hist_concept_toks.isin(allowed_cands)]
                                    h_col = hist_cols_norm.get(p)
                                    if h_col and not syn_matches.empty:
                                        for _, syn_r in syn_matches.iterrows():
                                            v_syn = syn_r.get(h_col)
                                            if pd.notna(v_syn):
                                                try:
                                                    val = float(v_syn)
                                                    break
                                                except (ValueError, TypeError):
                                                    pass
                                if val is not None:
                                    break
                        if val is not None:
                            break

                row_vals[p] = val

            # Cálculo de LTM bajo integridad temporal y candado dimensional
            if is_abs:
                row_vals["LTM"] = None
            else:
                ltm_val = None
                # 1. Para Balance Sheet (point-in-time), consultar el 10-Q trimestral oficial al cierre de MRQ
                if not is_flow and not q_face.empty and q_mrq_col:
                    q_toks = q_face["concept"].astype(str).apply(_clean_concept_token)
                    if is_row_dim and "dimension_member" in q_face.columns:
                        q_cand = q_face[q_face["dimension_member"].astype(str).str.strip() == row_dim_member]
                    elif is_row_dim and "label" in q_face.columns:
                        q_cand = q_face[q_face["label"].astype(str).str.strip().str.lower() == clean_lbl.lower()]
                    elif not is_row_dim and "dimension" in q_face.columns:
                        q_cand = q_face[(q_face["dimension"] == False) | q_face["dimension"].isna() | q_face["dimension"].astype(str).isin(["", "nan", "None"])]
                    else:
                        q_cand = q_face

                    if not q_cand.empty:
                        q_cand_toks = q_toks.loc[q_cand.index]
                        q_match = q_cand[(q_cand_toks == conc_tok) & (q_cand["label"].astype(str).str.strip().str.lower() == clean_lbl.lower())]
                        if q_match.empty:
                            q_match = q_cand[q_cand_toks == conc_tok]
                        if not q_match.empty:
                            v_q = q_match.iloc[0].get(q_mrq_col)
                            if pd.notna(v_q):
                                try:
                                    ltm_val = float(v_q)
                                except (ValueError, TypeError):
                                    pass

                # 2. Consultar LTM calibrado en hist_df (4Q sum EPS, flujo acumulado TTM)
                if ltm_val is None and matched_h_row is not None and "LTM" in hist_cols_norm:
                    cand_ltm = matched_h_row.get(hist_cols_norm["LTM"])
                    if pd.notna(cand_ltm):
                        try:
                            ltm_val = float(cand_ltm)
                        except (ValueError, TypeError):
                            ltm_val = None

                # 3. Respaldo de flujo (YTD delta) con candado dimensional
                if ltm_val is None and is_flow and not q_face.empty:
                    q_toks = q_face["concept"].astype(str).apply(_clean_concept_token)
                    if is_row_dim and "dimension_member" in q_face.columns:
                        q_cand = q_face[q_face["dimension_member"].astype(str).str.strip() == row_dim_member]
                    elif is_row_dim and "label" in q_face.columns:
                        q_cand = q_face[q_face["label"].astype(str).str.strip().str.lower() == clean_lbl.lower()]
                    elif not is_row_dim and "dimension" in q_face.columns:
                        q_cand = q_face[(q_face["dimension"] == False) | q_face["dimension"].isna() | q_face["dimension"].astype(str).isin(["", "nan", "None"])]
                    else:
                        q_cand = q_face

                    if not q_cand.empty:
                        q_cand_toks = q_toks.loc[q_cand.index]
                        q_match = q_cand[(q_cand_toks == conc_tok) & (q_cand["label"].astype(str).str.strip().str.lower() == clean_lbl.lower())]
                        if q_match.empty:
                            q_match = q_cand[q_cand_toks == conc_tok]
                        if q_match.empty and clean_lbl:
                            lbl_clean_norm = re.sub(r'[^a-zA-Z0-9]', '', clean_lbl.lower())
                            q_lbls_clean = q_cand["label"].astype(str).apply(lambda s: re.sub(r'[^a-zA-Z0-9]', '', str(s).lower()))
                            q_match = q_cand[q_lbls_clean == lbl_clean_norm]
                        if not q_match.empty and ytd_curr and ytd_prev and latest_fy in row_vals and row_vals[latest_fy] is not None:
                            v_curr = q_match.iloc[0].get(ytd_curr)
                            v_prev = q_match.iloc[0].get(ytd_prev)
                            if pd.notna(v_curr) and pd.notna(v_prev):
                                try:
                                    ltm_val = row_vals[latest_fy] + float(v_curr) - float(v_prev)
                                except (ValueError, TypeError):
                                    pass

                # 4. Respaldo de facts_df para partidas de flujo sin delta en 10-Q (Regla 6: NUNCA copiar FY_latest)
                if ltm_val is None and is_flow and facts_df is not None and not facts_df.empty and conc_tok and not is_row_dim:
                    q4_sum = get_ltm_quarterly_metric(facts_df, [conc_tok], mode='sum')
                    if q4_sum is not None:
                        ltm_val = float(q4_sum)

                # 5. Para Balance Sheet (APIC en META y partidas condensadas en 10-Q)
                is_apic_row = ('additionalpaidincapital' in conc_tok) or ('additional paid-in' in clean_lbl.lower()) or ('paid-in capital' in clean_lbl.lower())
                if not is_flow and is_apic_row and ltm_val is None:
                    if facts_df is not None and not facts_df.empty:
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

                row_vals["LTM"] = ltm_val

            # Homogeneización de signos algebraicos a lo largo de toda la serie temporal
            if s_name == "income_statement":
                c_low = conc.lower()
                l_low = clean_lbl.lower()
                is_expense = (
                    any(ind in c_low or ind in l_low for ind in ('cost of', 'costof', 'expense', 'expenses', 'charges', 'provision', 'research', 'selling', 'administrative', 'impairment'))
                    and not any(excl in c_low for excl in ('income', 'revenue', 'gain', 'operatingincomeloss', 'netincomeloss', 'profitloss'))
                )
                if is_expense:
                    for p_k in row_vals:
                        if row_vals[p_k] is not None:
                            row_vals[p_k] = abs(row_vals[p_k])
            else:
                valid_nums = [v for p_k, v in row_vals.items() if v is not None and v != 0.0 and p_k != "LTM"]
                if valid_nums:
                    pos_count = sum(1 for v in valid_nums if v > 0)
                    neg_count = sum(1 for v in valid_nums if v < 0)
                    tot_cnt = len(valid_nums)
                    if pos_count / tot_cnt >= 0.8:
                        for p_k in row_vals:
                            if row_vals[p_k] is not None:
                                row_vals[p_k] = abs(row_vals[p_k])
                    elif neg_count / tot_cnt >= 0.8:
                        for p_k in row_vals:
                            if row_vals[p_k] is not None:
                                row_vals[p_k] = -abs(row_vals[p_k])

            rows.append({
                "label": clean_lbl,
                "clarification": clarif,
                "concept": conc,
                "level": lvl,
                "is_abstract": is_abs,
                "is_total": is_tot,
                "values": row_vals
            })

        as_reported[s_name] = rows
        print(f"[SEC Extractor] {s_name}: {len(rows)} partidas As-Reported extraídas fielmente de la SEC.")

    return as_reported



def sanitize_and_validate_statements(full_dataset: dict) -> dict:
    """
    Candado Automático Post-Extracción (Reglas 1, 4 y 6):
    1. Homogeneiza signos algebraicos en toda la serie de cada fila en as_reported_statements.
    2. Enriquecer cada fila con `spanish_label` (traducción institucional en español)
       y `orig_tooltip` (nombre original en inglés y concepto XBRL).
    3. Garantiza coherencia en Balance LTM y bloquea colisiones dimensionales o cuentas de reclasificación residual.
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

            # Filtro defensivo contra filas residuales de reclasificación
            l_low = lbl.lower()
            if any(term in l_low for term in ["- as reported", "- reclassification"]):
                continue

            # Evitar duplicaciones de la misma clave exacta
            dedup_key = (lbl, conc)
            if dedup_key in seen_keys:
                continue
            seen_keys.add(dedup_key)

            # 1. Asignar traducción institucional al español y tooltip original
            sp_label = get_spanish_label(lbl, conc)
            orig_tooltip = f"{lbl} ({conc})" if conc else lbl
            row["spanish_label"] = sp_label
            row["orig_tooltip"] = orig_tooltip

            # 2. Homogeneización de signos en serie temporal
            vals = row.get("values", {})
            if s_name == "income_statement":
                c_low = conc.lower()
                is_expense = (
                    any(ind in c_low or ind in l_low for ind in (
                        'cost of', 'costof', 'expense', 'expenses', 'charges', 'provision',
                        'research', 'selling', 'administrative', 'impairment', 'benefitslosses'
                    ))
                    and not any(excl in c_low for excl in ('income', 'revenue', 'gain', 'operatingincomeloss', 'netincomeloss', 'profitloss'))
                )
                if is_expense:
                    for p_k in vals:
                        if vals[p_k] is not None:
                            vals[p_k] = abs(vals[p_k])
            else:
                valid_nums = [v for p_k, v in vals.items() if v is not None and v != 0.0 and p_k != "LTM"]
                if valid_nums:
                    pos_count = sum(1 for v in valid_nums if v > 0)
                    neg_count = sum(1 for v in valid_nums if v < 0)
                    tot_cnt = len(valid_nums)
                    if pos_count / tot_cnt >= 0.8:
                        for p_k in vals:
                            if vals[p_k] is not None:
                                vals[p_k] = abs(vals[p_k])
                    elif neg_count / tot_cnt >= 0.8:
                        for p_k in vals:
                            if vals[p_k] is not None:
                                vals[p_k] = -abs(vals[p_k])

            row["values"] = vals
            cleaned_rows.append(row)

        as_reported[s_name] = cleaned_rows

    # Candado de carátula para evitar contaminación por notas dimensionales (Regla 6)
    can_summary = full_dataset.get("canonical_summary", {})
    as_rep_bs = as_reported.get("balance_sheet", [])
    as_rep_cf = as_reported.get("cash_flow_statement", [])
    as_rep_inc = as_reported.get("income_statement", [])
    bs_detail = full_dataset.get("balance_sheet_detail", {})
    cf_detail = full_dataset.get("cash_flow_detail", {})
    inc_detail = full_dataset.get("income_statement_detail", {})

    # A. Sincronizar Inversiones a Corto Plazo con carátula de Balance Sheet si difieren materialmente (caso META)
    for r in as_rep_bs:
        c_tok = str(r.get("concept", "")).split(":")[-1].split("_")[-1].lower()
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

    # B. Sincronizar Dividendos LTM canónicos con el flujo acumulado 10-Q oficial
    for r in as_rep_cf:
        c_tok = str(r.get("concept", "")).split(":")[-1].split("_")[-1].lower()
        if c_tok in ("paymentsofdividends", "paymentsofdividendscommonstock"):
            v_ltm = r.get("values", {}).get("LTM")
            if v_ltm is not None and float(v_ltm) != 0.0:
                audited_div = abs(float(v_ltm))
                can_summary.setdefault("dividends_paid", {})["LTM"] = audited_div
                for k_cf in ("PaymentsOfDividends", "us-gaap_PaymentsOfDividends", "DividendsPaid", "PaymentsOfDividendsCommonStock"):
                    if k_cf in cf_detail and isinstance(cf_detail[k_cf], dict) and "values" in cf_detail[k_cf]:
                        cf_detail[k_cf]["values"]["LTM"] = -audited_div if float(v_ltm) < 0 else audited_div
            break

    # C. Resolver colisiones dimensionales en as_reported_statements (Regla 1 y Regla 6)
    # Si dos filas no abstractas del mismo estado comparten el mismo LTM no nulo pero difieren en FY_latest,
    # verificar con los detalles oficiales (detail) cuál de ellas posee legítimamente ese valor LTM.
    fys = [x for x in full_dataset.get("fiscal_years", []) if x != "LTM"]
    if fys:
        latest_fy = fys[0]
        details_map = {
            "income_statement": inc_detail,
            "balance_sheet": bs_detail,
            "cash_flow_statement": cf_detail
        }
        for s_name, rows in as_reported.items():
            s_det = details_map.get(s_name, {})
            non_abs = [r for r in rows if not r.get("is_abstract") and r.get("values", {}).get("LTM") is not None]
            for i in range(len(non_abs)):
                for j in range(i + 1, len(non_abs)):
                    r1 = non_abs[i]
                    r2 = non_abs[j]
                    v1_ltm = r1["values"].get("LTM")
                    v2_ltm = r2["values"].get("LTM")
                    v1_fy = r1["values"].get(latest_fy)
                    v2_fy = r2["values"].get(latest_fy)
                    if v1_fy is not None and v2_fy is not None and v1_fy != v2_fy and v1_fy != 0.0 and v2_fy != 0.0:
                        if v1_ltm == v2_ltm and v1_ltm != 0.0:
                            c1_tok = str(r1.get("concept", "")).split(":")[-1].split("_")[-1].lower()
                            c2_tok = str(r2.get("concept", "")).split(":")[-1].split("_")[-1].lower()
                            
                            r1_det_val = None
                            r2_det_val = None
                            for k, v in s_det.items():
                                k_tok = k.split(":")[-1].split("_")[-1].lower()
                                if k_tok == c1_tok and v.get("values", {}).get("LTM") is not None:
                                    r1_det_val = v["values"]["LTM"]
                                if k_tok == c2_tok and v.get("values", {}).get("LTM") is not None:
                                    r2_det_val = v["values"]["LTM"]
                            
                            if r1_det_val == v1_ltm and r2_det_val != v2_ltm:
                                r2["values"]["LTM"] = r2_det_val
                            elif r2_det_val == v2_ltm and r1_det_val != v1_ltm:
                                r1["values"]["LTM"] = r1_det_val

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
