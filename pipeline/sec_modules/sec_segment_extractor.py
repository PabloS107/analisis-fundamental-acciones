"""
sec_segment_extractor.py - Extractor dinámico y universal de segmentos operativos,
líneas de producto y regiones geográficas desde notas XBRL (ASC 280 y ASC 606).
"""

import json
import re
from pathlib import Path
import pandas as pd


def build_and_save_segments_data(company, all_fys, output_dir=None, canonical_rev=None, latest_10q_inc=None):
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
    geographic_segments = []
    segment_op_income = []
    detected_prod_names = set()
    detected_geo_names = set()
    detected_op_inc_names = set()

    def _norm_seg_key(name_str):
        return re.sub(r'\s+', ' ', str(name_str).lower().replace('&', 'and')).strip()

    def _scale_to_millions(num):
        if abs(num) > 1e7:
            return num / 1e6
        elif abs(num) > 1e4 and canonical_rev and abs(num) < (canonical_rev.get("LTM", 1e9) / 100.0):
            return num / 1000.0
        elif abs(num) > 5e5 and not canonical_rev:
            return num / 1000.0
        return num

    # Función auxiliar para mapear columnas XBRL a etiquetas canónicas FY
    def _map_col_to_fy(col_name):
        c_str = str(col_name).strip()
        m = re.search(r'(\d{4})', c_str)
        if m:
            return f"FY{m.group(1)}"
        return c_str

    geo_keywords = {
        "americas", "europe", "greater china", "china", "japan", "asia", "pacific",
        "international", "domestic", "united states", "u.s.", "non-us", "taiwan",
        "latin america", "latin america/caribbean", "caribbean", "brazil", "mexico",
        "argentina", "other countries", "rest of world", "emea", "apac", "ireland",
        "other regions", "rest of asia pacific", "north america", "south america",
        "central america", "middle east", "africa", "canada", "united kingdom", "uk",
        "germany", "france", "india", "singapore", "korea", "australia"
    }

    try:
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
                x_10k = doc_filing.xbrl()
            except Exception:
                continue
            if not x_10k or not hasattr(x_10k, "statements"):
                continue

            statements_to_scan = []
            for s in x_10k.statements:
                r = str(getattr(s, "role_or_type", ""))
                r_low = r.lower()
                if any(bad in r_low for bad in [
                    "marketable", "fairvalue", "cash", "receivable", "deferredrevenue",
                    "performanceobligation", "debt", "concentration", "accumulatedothercomprehensive"
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

                    for _, row in df.iterrows():
                        lbl = str(row.get("label", "")).strip()
                        conc = str(row.get("concept", "")).lower()

                        if not lbl or len(lbl) < 2:
                            continue
                        # Filtrar filas irrelevantes o de costos no operacionales
                        if any(bad in lbl.lower() for bad in [
                            "reclassifications, net of tax", "reclassification out of aoci", "pension and other postretirement",
                            "payroll", "advertising expense", "rent and occupancy", "depreciation", "sg&a", "impairment"
                        ]):
                            continue

                        # Extracción de ingresos y beneficio operativo
                        is_rev = any(k in conc for k in ["revenue", "sales"])
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

                        clean_name = re.sub(r'^(reportable segments?|operating segments?|segment reporting|segments?)\s*[-:]\s*', '', lbl, flags=re.IGNORECASE).strip()
                        parent_segment = None
                        is_subsegment = False

                        # Detección de subsegmentos jerárquicos ("Advertising - Family of Apps", etc.)
                        if " - " in clean_name and not any(g in clean_name.lower() for g in geo_keywords):
                            parts = clean_name.split(" - ")
                            if any(k in parts[0].lower() for k in ["operating segment", "reportable segment", "segment reporting"]):
                                clean_name = parts[-1].strip()
                            elif len(parts) == 2:
                                clean_name = parts[0].strip()
                                parent_segment = parts[1].strip()
                                is_subsegment = True
                            else:
                                clean_name = parts[-1].strip()

                        is_geo = any(g in clean_name.lower() for g in geo_keywords) or any(g in lbl.lower() for g in geo_keywords)

                        # Partidas de conciliación y coberturas corporativas (ASC 280 / ASC 815)
                        is_reconciling = any(k in clean_name.lower() for k in [
                            "hedging gains (losses)", "hedging gain", "hedging loss", "hedges",
                            "reconciling items", "corporate and reconciling", "corporate reconciling", "corporate items",
                            "intersegment eliminations", "eliminations", "other reconciling items"
                        ])

                        # Detección de totales consolidados para no mezclarlos con segmentos de producto
                        is_consolidated_total = (not is_reconciling) and (any(k in clean_name.lower() for k in [
                            "total revenue", "total revenues", "total net sales", "total net revenue",
                            "consolidated revenue", "consolidated net sales", "revenue from contract with customers",
                            "revenues from external customers", "net revenues and financial income",
                            "as reported", "reclassification"
                        ]) or clean_name.lower() in ["revenue", "net sales", "total", "revenues"])

                        is_sub = is_consolidated_total or any(k in clean_name.lower() for k in ["total", "products", "operating segments", "wholesale", "direct-to-consumer", "direct to consumer", "dtc"])

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

        # Resolución dinámica de jerarquías sin hardcoding (Regla 4)
        all_geo_names = {item["name"].lower() for item in geographic_segments}
        for item in geographic_segments:
            name_low = item["name"].lower()
            if item.get("parent") and item["parent"].lower() not in all_geo_names:
                item["parent"] = None
                item["is_subsegment"] = False

            if name_low in ["united states", "u.s."]:
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

        all_prod_names = {item["name"].lower() for item in product_segments}
        for item in product_segments:
            if item.get("parent") and item["parent"].lower() not in all_prod_names:
                item["parent"] = None
                item["is_subsegment"] = False

        # Escaneo de Formulario 10-Q para cálculo exacto de LTM (FY_latest + YTD_actual - YTD_anterior)
        if f10q_list and (product_segments or geographic_segments):
            try:
                k_rep_date = str(getattr(f10k_list[0], "period_of_report", "")) if f10k_list else ""
                q_rep_date = str(getattr(f10q_list[0], "period_of_report", ""))
                if not k_rep_date or q_rep_date > k_rep_date:
                    x_10q = f10q_list[0].xbrl()
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
                                if " - " in q_clean_name and not any(g in q_clean_name.lower() for g in geo_keywords):
                                    parts = q_clean_name.split(" - ")
                                    if any(k in parts[0].lower() for k in ["operating segment", "reportable segment", "segment reporting"]):
                                        q_clean_name = parts[-1].strip()
                                    else:
                                        q_clean_name = parts[0].strip() if len(parts) == 2 else parts[-1].strip()
                                q_norm = _norm_seg_key(q_clean_name)

                                target_lists = [segment_op_income] if is_op_inc else [product_segments, geographic_segments]
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
        for t_list in [product_segments, geographic_segments, segment_op_income]:
            for item in t_list:
                if "LTM" not in item["values"] and latest_fy in item["values"]:
                    item["values"]["LTM"] = item["values"][latest_fy]

    except Exception as e:
        print(f"[SEC Extractor] Aviso escaneando XBRL de segmentos: {e}")

    # Si no se extrajeron elementos por XBRL, cargar segments_data.json preexistente si está disponible
    if not product_segments and not geographic_segments and seg_json_path.exists():
        try:
            with open(seg_json_path, "r", encoding="utf-8") as f:
                cached = json.load(f)
            product_segments = cached.get("product_segments", [])
            geographic_segments = cached.get("geographic_segments", [])
            segment_op_income = cached.get("segment_operating_income", [])
        except Exception:
            pass

    # Cruce canónico de Ingresos y Beneficio Operativo por Segmento (ASC 280)
    for seg_list in [product_segments, geographic_segments]:
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
    seg_dict = {
        "periods": all_fys,
        "product_segments": product_segments,
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


def build_10yr_segment_df(company, all_fys, latest_10q_inc=None, output_dir=None, canonical_rev=None):
    """Enlace retrocompatible para extracción de segmentos."""
    return build_and_save_segments_data(company, all_fys, output_dir=output_dir, canonical_rev=canonical_rev, latest_10q_inc=latest_10q_inc)
