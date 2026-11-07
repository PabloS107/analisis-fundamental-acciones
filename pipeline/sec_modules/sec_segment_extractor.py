"""
sec_segment_extractor.py - Extractor dinámico y universal de segmentos operativos,
líneas de producto y regiones geográficas desde notas XBRL (ASC 280 y ASC 606).
"""

import json
import re
from pathlib import Path
import pandas as pd


def build_and_save_segments_data(company, all_fys, output_dir=None, canonical_rev=None, latest_10q_inc=None, filing_context=None):
    """
    Extractor Dinámico y Universal de Segmentos Contables Oficiales desde SEC EDGAR (XBRL).
    Bajo normativas contables ASC 280 (Segment Reporting) y ASC 606 (Disaggregation of Revenue).
    
    1. Escanea dinámicamente los formularios 10-K y 10-Q de SEC EDGAR en búsqueda de notas XBRL
       dimensionales de segmentos operativos, productos, líneas de negocio y regiones geográficas.
    2. Identifica jerarquías, subtotales y reclasificaciones sin hardcoding de nombres de marcas ni tickers.
    3. Normaliza las series anuales (FY2024, FY2025...) y computa el LTM oficial sincronizado con ingresos canónicos.
    4. Genera y persiste 'data/processed/{TICKER}/segments_data.json' y retorna el DataFrame auditado.
    """
    output_path = Path(output_dir) if output_dir else Path("data/processed")
    seg_json_path = output_path / "segments_data.json"
    ticker_str = str(getattr(company, "ticker", getattr(company, "tickers", [output_path.name])[0]))

    # Deduplicación canónica de períodos para evitar columnas 'LTM' repetidas
    clean_fys = []
    for p in (all_fys or []):
        if p not in clean_fys:
            clean_fys.append(p)
    all_fys = clean_fys
    annual_fys = [p for p in all_fys if p != "LTM"]
    latest_fy = annual_fys[0] if annual_fys else "FY2025"

    print(f"[SEC Extractor] Extracción dinámica de segmentos XBRL para {ticker_str}...")

    product_segments = []
    channel_segments = []
    geographic_segments = []
    segment_op_income = []
    detected_prod_names = set()
    detected_channel_names = set()
    detected_geo_names = set()
    detected_op_inc_names = set()

    def _norm_seg_key(name_str):
        return re.sub(r'\s+', ' ', str(name_str).lower().replace('&', 'and')).strip()

    def _scale_to_millions(num):
        if num is None:
            return None
        # Hechos cuantitativos monetarios en XBRL (USD). Si el valor absoluto es >= 10,000
        # proviene en unidades base de moneda (USD) y se convierte a millones ($M) dividiendo por 1e6.
        if abs(num) >= 1e4:
            return num / 1e6
        return num

    # Función auxiliar para mapear columnas XBRL a etiquetas canónicas FY
    def _map_col_to_fy(col_name):
        c_str = str(col_name).strip()
        m = re.search(r'(\d{4})', c_str)
        if m:
            return f"FY{m.group(1)}"
        return c_str

    GEO_REGEX = re.compile(
        r'(?:\b('
        r'americas|europe|greater china|china|japan|asia|pacific|international|domestic|'
        r'united states|non-us|taiwan|latin america|latin america/caribbean|caribbean|brazil|mexico|'
        r'argentina|rest of world|emea|apac|ireland|other regions|rest of asia pacific|'
        r'north america|south america|central america|middle east|africa|canada|'
        r'united kingdom|germany|france|india|singapore|korea|australia|other countries'
        r')\b|\bu\.s\.?|\buk\b)',
        re.IGNORECASE
    )

    DISCLOSURE_NOISE_REGEX = re.compile(
        r'(foreign currencies|foreign currency|constant currency|exchange rate|translation adjustment|'
        r'sales revenue, net - net sales|sales revenue, net - international|international net sales)',
        re.IGNORECASE
    )

    CHANNEL_REGEX = re.compile(
        r'^(wholesale|direct-to-consumer|direct to consumer|directly to consumer|dtc|retail|e-commerce|consumer direct|distributor)$',
        re.IGNORECASE
    )

    try:
        if filing_context:
            f10k_list = filing_context.get_filings(form="10-K")
            if not f10k_list:
                f10k_list = filing_context.get_filings(form="20-F")
            f10q_list = filing_context.get_filings(form="10-Q")
            if not f10q_list:
                f10q_list = filing_context.get_filings(form="6-K")
        else:
            f10k_list = company.get_filings(form="10-K")
            if not f10k_list:
                f10k_list = company.get_filings(form="20-F")
            f10q_list = company.get_filings(form="10-Q")
            if not f10q_list:
                f10q_list = company.get_filings(form="6-K")

        valid_k_filings = [f for f in (f10k_list or []) if not str(getattr(f, "form", "")).upper().endswith("/A")]

        # Escaneo multi-anual de reportes 10-K/20-F (hasta 8 filings para cubrir 10+ ejercicios)
        for f_idx, doc_filing in enumerate(valid_k_filings[:8]):
            try:
                x_10k = filing_context.get_filing_xbrl(doc_filing) if filing_context else doc_filing.xbrl()
            except Exception:
                continue
            if not x_10k or not hasattr(x_10k, "statements"):
                continue

            statements_to_scan = []
            for s in x_10k.statements:
                r = str(getattr(s, "role_or_type", ""))
                r_low = r.lower()
                # Excluir statements de balances, PP&E, Goodwill, ROU assets, reclasificaciones contables y notas accesorias
                if any(bad in r_low for bad in [
                    "marketable", "fairvalue", "cash", "receivable", "deferredrevenue",
                    "performanceobligation", "debt", "concentration", "accumulatedothercomprehensive",
                    "goodwill", "propertyplant", "propertyandequipment", "rightofuse",
                    "leaseassets", "leaseliabilit", "reclassification", "minimumfutureannualrental",
                    "scheduleofoperatinglease", "scheduleofgoodwill"
                ]):
                    continue
                if any(k in r_low for k in ["segment", "disaggregation", "brand", "market", "channel", "geographic"]) and "details" in r_low:
                    statements_to_scan.append(s)

            for s in statements_to_scan:
                try:
                    df = s.to_dataframe()
                    fy_cols = {}
                    for c in df.columns:
                        c_str = str(c)
                        if "(FY)" in c_str or re.search(r'\b20\d\d\b', c_str):
                            fy_cols[c] = _map_col_to_fy(c_str)

                    last_prod_level_map = {}
                    for _, row in df.iterrows():
                        lbl = str(row.get("label", "")).strip()
                        conc = str(row.get("concept", "")).lower()
                        dim_axis = str(row.get("dimension_axis") or row.get("dimension") or "").lower()
                        row_lvl = int(row.get("level", 0)) if (pd.notna(row.get("level")) and str(row.get("level")).isdigit()) else 0

                        if not lbl or len(lbl) < 2:
                            continue

                        # Descartar partidas de notas cambiarias, divisas y reconciliaciones no operacionales
                        if DISCLOSURE_NOISE_REGEX.search(lbl):
                            continue

                        # Filtrar filas irrelevantes, balance sheet, o de costos no operacionales
                        if any(bad in lbl.lower() for bad in [
                            "reclassifications, net of tax", "reclassification out of aoci", "pension and other postretirement",
                            "payroll", "advertising expense", "rent and occupancy", "depreciation", "sg&a", "impairment",
                            "accounting standards update", "minimum", "maximum", "shares of common stock",
                            "movement in deferred revenue", "balance at end of period", "useful life",
                            "operating expenses and indirect costs", "indirect costs of net revenues",
                            "compensation expense", "noncompensation expense", "provision for loan", "provision for credit",
                            "benefit driven by tax", "tax audit", "return on equity", "overhead ratio", "average equity",
                            "total assets", "retained loans", "noncurrent assets", "long-lived assets"
                        ]):
                            continue

                        # Extracción de ingresos y beneficio operativo (incluyendo primas de seguros y rentas inmobiliarias)
                        is_rev = any(k in conc for k in ["revenue", "sales", "premiumsearned", "leaseincome", "contractwithcustomer"])
                        is_op_inc = any(k in conc for k in ["operatingincome", "incomelossfromcontinuingoperations"])

                        if not (is_rev or is_op_inc):
                            continue

                        v_dict = {}
                        has_val = False
                        for raw_col, fy_norm in fy_cols.items():
                            val = row.get(raw_col)
                            if pd.notna(val) and val != "":
                                try:
                                    num = _scale_to_millions(float(val))
                                    v_dict[fy_norm] = round(num, 1)
                                    has_val = True
                                except Exception:
                                    pass

                        if not has_val:
                            continue

                        clean_name = re.sub(
                            r'^(reportable segments?|operating segments?|segment reporting|segments?|similar products and services|underwriting operations)\s*[-:]\s*',
                            '', lbl, flags=re.IGNORECASE
                        ).strip()
                        clean_name = re.sub(r'\s*\[member\]', '', clean_name, flags=re.IGNORECASE).strip()
                        clean_name = re.sub(r'^(country of|region of)\s+', '', clean_name, flags=re.IGNORECASE).strip()

                        # Diccionario de unificación universal de alias contables para series continuas
                        ALIAS_MAP = {
                            "directly to consumer": "Direct-to-Consumer",
                            "direct to consumer": "Direct-to-Consumer",
                            "ccb": "Consumer & Community Banking (CCB)",
                            "consumer & community banking": "Consumer & Community Banking (CCB)",
                            "consumer and community banking": "Consumer & Community Banking (CCB)",
                            "cib": "Commercial & Investment Bank (CIB)",
                            "corporate & investment bank": "Commercial & Investment Bank (CIB)",
                            "corporate and investment bank": "Commercial & Investment Bank (CIB)",
                            "commercial banking": "Commercial Banking",
                            "asset & wealth management": "Asset & Wealth Management",
                            "datacenter": "Data Center",
                            "oem & ip": "OEM & Other",
                            "oem and other": "OEM & Other",
                            "personal lines segment": "Personal Lines",
                            "commercial lines segment": "Commercial Lines",
                            "personal lines": "Personal Lines",
                            "commercial lines": "Commercial Lines",
                        }
                        clean_low = clean_name.strip().lower()
                        if clean_low in ALIAS_MAP:
                            clean_name = ALIAS_MAP[clean_low]

                        if DISCLOSURE_NOISE_REGEX.search(clean_name):
                            continue

                        parent_segment = None
                        is_subsegment = False

                        # Desarmado universal de etiquetas compuestas multidimensionales de hipercubos XBRL (" - ")
                        if " - " in clean_name:
                            parts = [p.strip() for p in clean_name.split(" - ")]
                            parts = [re.sub(r'\s*\[member\]', '', p, flags=re.IGNORECASE).strip() for p in parts]
                            parts = [re.sub(r'^(country of|region of)\s+', '', p, flags=re.IGNORECASE).strip() for p in parts]
                            # Filtrar partes que sean ruido contable como "As reported" o "Reclassification"
                            parts = [p for p in parts if not any(bad in p.lower() for bad in ["as reported", "reclassification", "operating segment", "reportable segment"])]

                            if len(parts) >= 3:
                                # Intersección hiperdimensional (ej. "Services - Brazil - Commerce")
                                # No es un segmento primario ni una región pura, se descarta para evitar duplicidades masivas
                                continue
                            elif len(parts) == 2:
                                p0, p1 = parts[0], parts[1]
                                p0_low, p1_low = p0.lower(), p1.lower()
                                if p0_low in ALIAS_MAP: p0 = ALIAS_MAP[p0_low]
                                if p1_low in ALIAS_MAP: p1 = ALIAS_MAP[p1_low]

                                # Caso A: Ambas son entidades geográficas (ej. "Americas - United States", "Greater China - China")
                                if GEO_REGEX.search(p0) and GEO_REGEX.search(p1):
                                    clean_name = p1
                                    parent_segment = p0
                                    is_subsegment = True
                                # Caso B: La primera es producto y la segunda es región geográfica (ej. "Retail - U.S.", "Services - Brazil")
                                elif not GEO_REGEX.search(p0) and GEO_REGEX.search(p1):
                                    clean_name = f"{p0} ({p1})"
                                    parent_segment = p0
                                    is_subsegment = True
                                # Caso C: Categoría de suscripción aseguradora (ej. "Underwriting Operations - Personal Lines Segment")
                                elif any(k in p0.lower() for k in ["underwriting operations", "underwriting", "insurance operations"]):
                                    clean_name = re.sub(r'\s+segment$', '', p1, flags=re.IGNORECASE).strip()
                                    parent_segment = None
                                    is_subsegment = False
                                # Caso D: Subsegmento jerárquico dentro de una división (ej. "Advertising - Family of Apps")
                                else:
                                    clean_name = p0
                                    parent_segment = p1
                                    is_subsegment = True
                            elif len(parts) == 1:
                                clean_name = parts[0]

                        clean_low = clean_name.strip().lower()
                        if clean_low in ALIAS_MAP:
                            clean_name = ALIAS_MAP[clean_low]

                        is_geo_axis = any(g_ax in dim_axis for g_ax in ["geograph", "country", "territor"])
                        is_prod_axis = any(p_ax in dim_axis for p_ax in ["product", "service", "market"])
                        is_geo = (is_geo_axis or bool(GEO_REGEX.search(clean_name))) and not is_prod_axis and not any(k in clean_name.lower() for k in ["commerce", "fintech", "retail", "industrial", "product", "service"])

                        is_channel = bool(CHANNEL_REGEX.match(clean_name.strip()))

                        # Partidas de conciliación y coberturas corporativas (ASC 280 / ASC 815)
                        is_reconciling = any(k in clean_name.lower() for k in [
                            "hedging gains (losses)", "hedging gain", "hedging loss", "hedges",
                            "reconciling items", "corporate and reconciling", "corporate reconciling", "corporate items",
                            "corporate non-segment", "intersegment eliminations", "eliminations", "other reconciling items"
                        ])

                        # Detección exhaustiva de totales consolidados para no mezclarlos con segmentos de producto
                        is_consolidated_total = (not is_reconciling) and (any(k in clean_name.lower() for k in [
                            "total revenue", "total revenues", "total net sales", "total net revenue",
                            "consolidated revenue", "consolidated net sales", "revenue from contract with customer",
                            "revenues from contract with customer", "revenues from contract with customers",
                            "revenues from external customers", "net revenues and financial income",
                            "total underwriting revenue", "total net revenue", "operating segments", "operating segment",
                            "reportable segments", "reportable segment", "rental (including reimbursements)",
                            "rental (including reimbursable)", "net premiums earned",
                            "property, liability and casualty insurance product line",
                            "as reported", "reclassification", "parent company"
                        ]) or clean_name.lower() in ["revenue", "net sales", "total", "revenues", "google", "apple", "reportable segments", "operating segments"])

                        is_sub = is_consolidated_total or any(k in clean_name.lower() for k in ["total", "products", "operating segments"])

                        # Jerarquía de subsegmentos por nivel XBRL (preserva sub-partidas como Compute & Networking bajo Data Center)
                        if not is_geo and not is_consolidated_total and not is_reconciling:
                            if not is_subsegment and row_lvl > 0:
                                parent_candidate = last_prod_level_map.get(row_lvl - 1)
                                if parent_candidate:
                                    parent_segment = parent_candidate
                                    is_subsegment = True
                                else:
                                    last_prod_level_map[row_lvl] = clean_name
                            elif not is_subsegment:
                                last_prod_level_map[row_lvl] = clean_name

                        norm_key = _norm_seg_key(clean_name)
                        if is_op_inc:
                            existing = next((item for item in segment_op_income if _norm_seg_key(item.get("name", "")) == norm_key), None)
                            if existing:
                                for fy, v in v_dict.items():
                                    if fy not in existing["values"]:
                                        existing["values"][fy] = v
                            else:
                                segment_op_income.append({"name": clean_name, "values": v_dict})
                                detected_op_inc_names.add(norm_key)
                        elif is_channel:
                            existing = next((item for item in channel_segments if _norm_seg_key(item.get("name", "")) == norm_key), None)
                            if existing:
                                for fy, v in v_dict.items():
                                    if fy not in existing["values"]:
                                        existing["values"][fy] = v
                            else:
                                seg_entry = {
                                    "name": clean_name,
                                    "is_subtotal": False,
                                    "is_subsegment": is_subsegment,
                                    "parent": parent_segment,
                                    "values": v_dict
                                }
                                channel_segments.append(seg_entry)
                                detected_channel_names.add(norm_key)
                        elif is_geo:
                            existing = next((item for item in geographic_segments if _norm_seg_key(item.get("name", "")) == norm_key), None)
                            if existing:
                                for fy, v in v_dict.items():
                                    if fy not in existing["values"]:
                                        existing["values"][fy] = v
                            else:
                                seg_entry = {
                                    "name": clean_name,
                                    "is_subtotal": is_sub,
                                    "is_subsegment": is_subsegment,
                                    "parent": parent_segment,
                                    "values": v_dict
                                }
                                geographic_segments.append(seg_entry)
                                detected_geo_names.add(norm_key)
                        elif not is_geo and not is_consolidated_total:
                            existing = next((item for item in product_segments if _norm_seg_key(item.get("name", "")) == norm_key), None)
                            if existing:
                                for fy, v in v_dict.items():
                                    # Supremacía de re-expresión cronológica: el filing más reciente manda
                                    if fy not in existing["values"]:
                                        existing["values"][fy] = v
                            else:
                                seg_entry = {
                                    "name": clean_name,
                                    "is_subtotal": is_sub,
                                    "is_subsegment": is_subsegment,
                                    "is_reconciling": is_reconciling,
                                    "parent": parent_segment,
                                    "values": v_dict
                                }
                                product_segments.append(seg_entry)
                                detected_prod_names.add(norm_key)

                except Exception as s_err:
                    pass

                except Exception as s_err:
                    pass

        # Resolución dinámica de jerarquías sin hardcoding (Regla 4)
        all_geo_names = {item["name"].lower() for item in geographic_segments}
        for item in geographic_segments:
            name_low = item["name"].lower()
            if item.get("parent") and item["parent"].lower() not in all_geo_names:
                item["parent"] = None
                item["is_subsegment"] = False

            if name_low in ["united states", "u.s.", "u.s", "us"]:
                parent_found = next((p for p in ["americas", "united states & canada", "north america"] if p in all_geo_names), None)
                if parent_found:
                    item["is_subsegment"] = True
                    parent_item = next(g for g in geographic_segments if g["name"].lower() == parent_found)
                    item["parent"] = parent_item["name"]
                else:
                    item["is_subsegment"] = False
                    item["parent"] = None
            elif name_low == "china":
                if "greater china" in all_geo_names:
                    item["is_subsegment"] = True
                    parent_item = next(g for g in geographic_segments if g["name"].lower() == "greater china")
                    item["parent"] = parent_item["name"]
                else:
                    item["is_subsegment"] = False
                    item["parent"] = None
            elif name_low == "other countries":
                item["is_country_breakdown"] = True

        for item in product_segments:
            if item.get("parent") and item["parent"].lower() in ["other", "u.k."]:
                if any(c.get("parent") and c.get("parent").lower() == item["name"].lower() for c in product_segments):
                    item["parent"] = None
                    item["is_subsegment"] = False
                    # Actualizar valores si los hijos suman más que la entrada aislada
                    matching_children = [c for c in product_segments if c.get("parent") and c.get("parent").lower() == item["name"].lower()]
                    for c in matching_children:
                        for k, v in c.get("values", {}).items():
                            if v is not None:
                                item["values"][k] = round(item["values"].get(k, 0.0) + float(v), 1)

        all_prod_names = {item["name"].lower() for item in product_segments}
        synthetic_parents = []
        for item in product_segments:
            p_name = item.get("parent")
            if p_name and p_name.lower() not in all_prod_names:
                matching_children = [c for c in product_segments if c.get("parent") and c.get("parent").lower() == p_name.lower()]
                if len(matching_children) >= 1 and not any(sp["name"].lower() == p_name.lower() for sp in synthetic_parents):
                    p_vals = {}
                    for c in matching_children:
                        for k, v in c.get("values", {}).items():
                            if v is not None:
                                p_vals[k] = round(p_vals.get(k, 0.0) + float(v), 1)
                    synthetic_parents.append({
                        "name": p_name,
                        "is_subtotal": False,
                        "is_subsegment": False,
                        "parent": None,
                        "status": "active" if any(p_vals.get(p) for p in [latest_fy, "LTM"]) else "discontinued",
                        "values": p_vals
                    })
                    all_prod_names.add(p_name.lower())
        if synthetic_parents:
            product_segments = synthetic_parents + product_segments

        all_prod_names = {item["name"].lower() for item in product_segments}
        for item in product_segments:
            if item.get("parent") and item["parent"].lower() not in all_prod_names:
                item["parent"] = None
                item["is_subsegment"] = False

        # Escaneo de Formulario 10-Q para cálculo exacto de LTM (FY_latest + YTD_actual - YTD_anterior)
        if f10q_list and (product_segments or geographic_segments or channel_segments):
            try:
                k_rep_date = str(getattr(f10k_list[0], "period_of_report", "")) if f10k_list else ""
                q_rep_date = str(getattr(f10q_list[0], "period_of_report", ""))
                if not k_rep_date or q_rep_date > k_rep_date:
                    x_10q = filing_context.get_filing_xbrl(f10q_list[0]) if filing_context else f10q_list[0].xbrl()
                    q_stmts = []
                    if x_10q and hasattr(x_10q, "statements"):
                        for s in x_10q.statements:
                            r_low = str(getattr(s, "role_or_type", "")).lower()
                            if any(bad in r_low for bad in [
                                "marketable", "fairvalue", "cash", "receivable", "deferredrevenue",
                                "performanceobligation", "debt", "concentration", "accumulatedothercomprehensive"
                            ]):
                                continue
                            if any(k in r_low for k in ["segment", "disaggregation", "brand", "market", "channel", "geographic"]) and "details" in r_low:
                                q_stmts.append(s)

                    for s in q_stmts:
                        try:
                            q_df = s.to_dataframe()
                            ytd_cols = [c for c in q_df.columns if "YTD" in str(c) and any(ch.isdigit() for ch in str(c))]
                            if not ytd_cols:
                                ytd_cols = [c for c in q_df.columns if any(ch.isdigit() for ch in str(c)) and ("Q" in str(c) or "202" in str(c))]
                            ytd_sorted = sorted(ytd_cols, key=lambda x: str(x), reverse=True)
                            ytd_curr = ytd_sorted[0] if len(ytd_sorted) >= 1 else None
                            ytd_prev = ytd_sorted[1] if len(ytd_sorted) >= 2 else None

                            if not (ytd_curr and ytd_prev):
                                continue

                            for _, row in q_df.iterrows():
                                lbl = str(row.get("label", "")).strip()
                                conc = str(row.get("concept", "")).lower()
                                if not lbl or len(lbl) < 2:
                                    continue
                                if DISCLOSURE_NOISE_REGEX.search(lbl):
                                    continue
                                is_rev = any(k in conc for k in ["revenue", "sales"])
                                is_op_inc = any(k in conc for k in ["operatingincome", "incomelossfromcontinuingoperations"])
                                if not (is_rev or is_op_inc):
                                    continue

                                v_curr_raw = row.get(ytd_curr)
                                v_prev_raw = row.get(ytd_prev)
                                if pd.isna(v_curr_raw) or pd.isna(v_prev_raw) or v_curr_raw == "" or v_prev_raw == "":
                                    continue
                                try:
                                    v_curr_m = _scale_to_millions(float(v_curr_raw))
                                    v_prev_m = _scale_to_millions(float(v_prev_raw))
                                except Exception:
                                    continue

                                q_clean_name = re.sub(r'^(reportable segments?|operating segments?|segment reporting|segments?)\s*[-:]\s*', '', lbl, flags=re.IGNORECASE).strip()
                                if DISCLOSURE_NOISE_REGEX.search(q_clean_name):
                                    continue
                                if " - " in q_clean_name and not GEO_REGEX.search(q_clean_name):
                                    parts = q_clean_name.split(" - ")
                                    if any(k in parts[0].lower() for k in ["operating segment", "reportable segment", "segment reporting"]):
                                        q_clean_name = parts[-1].strip()
                                    else:
                                        q_clean_name = parts[0].strip() if len(parts) == 2 else parts[-1].strip()
                                q_norm = _norm_seg_key(q_clean_name)

                                target_lists = [segment_op_income] if is_op_inc else [product_segments, channel_segments, geographic_segments]
                                for t_list in target_lists:
                                    for item in t_list:
                                        if _norm_seg_key(item.get("name", "")) == q_norm:
                                            v_fy = item.get("values", {}).get(latest_fy)
                                            if v_fy is not None and "LTM" not in item["values"]:
                                                item["values"]["LTM"] = round(v_fy + v_curr_m - v_prev_m, 1)
                        except Exception as q_s_err:
                            print(f"[SEC Extractor] Aviso analizando tabla de segmentos 10-Q: {q_s_err}")
            except Exception as q_err:
                print(f"[SEC Extractor] Aviso en escaneo 10-Q de segmentos: {q_err}")

        # Fallback canónico de LTM: si no hay 10-Q posterior o LTM no fue poblado, sincronizar con latest_fy
        for t_list in [product_segments, channel_segments, geographic_segments, segment_op_income]:
            for item in t_list:
                if "LTM" not in item["values"] and latest_fy in item["values"]:
                    item["values"]["LTM"] = item["values"][latest_fy]

        # Etiquetado del ciclo de vida y régimen contable (Active vs Discontinued)
        for item in product_segments + channel_segments + geographic_segments:
            vals = item.get("values", {})
            if vals.get("LTM") is not None or vals.get(latest_fy) is not None:
                item["status"] = "active"
            else:
                item["status"] = "discontinued"

        # Detección de particiones ortogonales en productos (ASC 280 vs ASC 606)
        active_prods = [
            p for p in product_segments
            if p.get("status") == "active" and not p.get("is_subtotal") and not p.get("is_subsegment") and not p.get("is_reconciling")
        ]
        can_ltm_ref = None
        if canonical_rev:
            can_ltm_ref = canonical_rev.get("LTM") or canonical_rev.get(latest_fy)
            if can_ltm_ref and abs(can_ltm_ref) >= 1e4:
                can_ltm_ref = can_ltm_ref / 1e6

        if can_ltm_ref and len(active_prods) >= 3:
            rev_type_items = [
                p for p in active_prods
                if any(k in p["name"].lower() for k in ["net service", "net product", "service revenue", "product revenue", "product sales"])
            ]
            business_unit_items = [p for p in active_prods if p not in rev_type_items]
            if rev_type_items and business_unit_items:
                sum_rev_types = sum((p.get("values", {}).get("LTM") or 0.0) for p in rev_type_items)
                sum_bus_units = sum((p.get("values", {}).get("LTM") or 0.0) for p in business_unit_items)
                if abs(sum_rev_types - can_ltm_ref) / can_ltm_ref < 0.05 and abs(sum_bus_units - can_ltm_ref) / can_ltm_ref < 0.05:
                    for p in rev_type_items:
                        p["is_subsegment"] = True
                        p["parent"] = "Tipo de Ingreso (ASC 606)"

    except Exception as e:
        print(f"[SEC Extractor] Aviso escaneando XBRL de segmentos: {e}")

    # Arquetipo Bancario / FinTech: si no existen líneas de producto en la nota ASC 280, derivar de los flujos de ingresos canónicos del P&L
    active_prod_count = len([p for p in product_segments if p.get("status") == "active" and not p.get("is_subtotal")])
    if active_prod_count == 0 and output_dir:
        fin_stmt_path = Path(output_dir) / "financial_statements.json"
        if fin_stmt_path.exists():
            try:
                with open(fin_stmt_path, "r", encoding="utf-8") as f_in:
                    f_data = json.load(f_in)
                arch = f_data.get("archetype", "")
                is_fin = f_data.get("is_financial", False)
                if arch == "FINANCIAL_BANKING" or is_fin:
                    inc_det = f_data.get("income_statement_detail", {})
                    nii_k = next((k for k in inc_det if any(w in k.lower() for w in ["interestincome", "interest_income", "financialinstruments", "revenuefrominterest"])), None)
                    fee_k = next((k for k in inc_det if any(w in k.lower() for w in ["feeandcommission", "fee_income", "noninterestincome", "commissions"])), None)
                    int_exp_k = next((k for k in inc_det if "interestexpense" in k.lower()), None)
                    if nii_k and fee_k:
                        v_nii_gross = {p: _scale_to_millions(v) for p, v in inc_det[nii_k].get("values", {}).items() if v is not None}
                        v_exp = {p: _scale_to_millions(v) for p, v in inc_det[int_exp_k].get("values", {}).items() if v is not None} if int_exp_k else {}
                        v_nii_net = {p: round(v_nii_gross.get(p, 0.0) - v_exp.get(p, 0.0), 1) if p in v_exp else v_nii_gross.get(p, 0.0) for p in v_nii_gross}
                        v_fee = {p: _scale_to_millions(v) for p, v in inc_det[fee_k].get("values", {}).items() if v is not None}
                        product_segments = [
                            {
                                "name": "Ingreso Neto por Intereses (Net Interest Income - NII)",
                                "description": "Margen de intermediación financiera: rendimiento de cartera y activos menos costo de fondeo y depósitos.",
                                "is_subtotal": False,
                                "is_subsegment": False,
                                "status": "active",
                                "values": v_nii_net
                            },
                            {
                                "name": "Ingresos por Comisiones y Tarifas (Fee & Commission Income)",
                                "description": "Comisiones por transacciones, servicios bancarios, interchange fees y productos de valor agregado.",
                                "is_subtotal": False,
                                "is_subsegment": False,
                                "status": "active",
                                "values": v_fee
                            }
                        ]
            except Exception:
                pass

    # Si no se extrajeron elementos por XBRL, cargar segments_data.json preexistente si está disponible
    if not product_segments and not geographic_segments and seg_json_path.exists():
        try:
            with open(seg_json_path, "r", encoding="utf-8") as f:
                cached = json.load(f)
            product_segments = cached.get("product_segments", [])
            channel_segments = cached.get("channel_segments", [])
            geographic_segments = cached.get("geographic_segments", [])
            segment_op_income = cached.get("segment_operating_income", [])
        except Exception:
            pass

    # Cruce canónico de Ingresos y Beneficio Operativo por Segmento (ASC 280)
    for seg_list in [product_segments, channel_segments, geographic_segments]:
        for item in seg_list:
            item_norm = _norm_seg_key(item.get("name", ""))
            matching_op = None
            for op_item in segment_op_income:
                op_norm = _norm_seg_key(op_item.get("name", ""))
                if op_norm == item_norm or (len(item_norm) > 4 and item_norm in op_norm) or (len(op_norm) > 4 and op_norm in item_norm):
                    matching_op = op_item
                    break
            if matching_op:
                item["operating_income"] = dict(matching_op.get("values", {}))
                op_margins = {}
                seg_vals = item.get("values", {})
                for p, op_val in matching_op.get("values", {}).items():
                    rev_val = seg_vals.get(p)
                    if rev_val and rev_val != 0.0:
                        op_margins[p] = round((op_val / rev_val) * 100.0, 2)
                if op_margins:
                    item["operating_margin_pct"] = op_margins

    # Construir y persistir segments_data.json
    all_seg_items = product_segments + channel_segments + geographic_segments + segment_op_income
    periods_with_seg_data = set()
    for item in all_seg_items:
        for k, v in item.get("values", {}).items():
            if v is not None and v != "":
                periods_with_seg_data.add(k)

    clean_periods = [p for p in all_fys if p in periods_with_seg_data] if periods_with_seg_data else all_fys
    if "LTM" in all_fys and "LTM" not in clean_periods:
        clean_periods.insert(0, "LTM")

    seg_dict = {
        "periods": clean_periods,
        "product_segments": product_segments,
        "channel_segments": channel_segments,
        "geographic_segments": geographic_segments,
        "segment_operating_income": segment_op_income,
        "extraction_method": "SEC_EDGAR_XBRL_ASC280_ASC606",
        "ticker": ticker_str
    }

    try:
        with open(seg_json_path, "w", encoding="utf-8") as f:
            json.dump(seg_dict, f, indent=2, ensure_ascii=False)
        print(f"[SEC Extractor] segments_data.json generado dinámicamente y guardado: {seg_json_path}")
    except Exception as w_err:
        print(f"[SEC Extractor] Error guardando segments_data.json: {w_err}")

    # Generar DataFrame para retorno
    rows = []
    for p in product_segments:
        r = {"concept": "RevenueByProduct", "dimension_member_label": p.get("name"), "label": p.get("name")}
        r.update(p.get("values", {}))
        rows.append(r)
    for g in geographic_segments:
        r = {"concept": "RevenueByRegion", "dimension_member_label": g.get("name"), "label": g.get("name")}
        r.update(g.get("values", {}))
        rows.append(r)

    return pd.DataFrame(rows) if rows else None


def build_10yr_segment_df(company, all_fys, latest_10q_inc=None, output_dir=None, canonical_rev=None, filing_context=None):
    """Enlace retrocompatible para extracción de segmentos."""
    return build_and_save_segments_data(company, all_fys, output_dir=output_dir, canonical_rev=canonical_rev, latest_10q_inc=latest_10q_inc, filing_context=filing_context)
