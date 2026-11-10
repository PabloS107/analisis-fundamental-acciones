"""
sec_segment_extractor.py - Extractor dinámico y universal de segmentos operativos,
líneas de producto y regiones geográficas desde notas XBRL (ASC 280 y ASC 606).
"""

import json
import logging
import re
from pathlib import Path
import pandas as pd

try:
    from json_io import atomic_json_write
    from config_loader import DATA_PROCESSED_DIR
except ImportError:
    try:
        from pipeline.json_io import atomic_json_write
        from pipeline.config_loader import DATA_PROCESSED_DIR
    except ImportError:
        from ..json_io import atomic_json_write
        from ..config_loader import DATA_PROCESSED_DIR

logger = logging.getLogger(__name__)

_GEO_REGEX = re.compile(
    r"(?:\b("
    r"americas|europe|greater china|china|japan|asia|pacific|international|domestic|"
    r"united states|non-us|taiwan|latin america|latin america/caribbean|caribbean|brazil|mexico|"
    r"argentina|rest of world|emea|apac|ireland|other regions|rest of asia pacific|"
    r"north america|south america|central america|middle east|africa|canada|"
    r"united kingdom|germany|france|india|singapore|korea|australia|other countries"
    r")\b|\bu\.s\.?|\buk\b)",
    re.IGNORECASE,
)

_DISCLOSURE_NOISE_REGEX = re.compile(
    r"(foreign currencies|foreign currency|constant currency|exchange rate|translation adjustment|"
    r"sales revenue, net - net sales|sales revenue, net - international|international net sales)",
    re.IGNORECASE,
)

_CHANNEL_REGEX = re.compile(
    r"^(wholesale|direct-to-consumer|direct to consumer|directly to consumer|dtc|retail|e-commerce|consumer direct|distributor)$",
    re.IGNORECASE,
)

_BASE_BAD_ROLE_KEYWORDS = (
    "marketable",
    "fairvalue",
    "cash",
    "receivable",
    "deferredrevenue",
    "performanceobligation",
    "debt",
    "concentration",
    "accumulatedothercomprehensive",
)

_EXTRA_10K_BAD_ROLE_KEYWORDS = (
    "goodwill",
    "propertyplant",
    "propertyandequipment",
    "rightofuse",
    "leaseassets",
    "leaseliabilit",
    "reclassification",
    "minimumfutureannualrental",
    "scheduleofoperatinglease",
    "scheduleofgoodwill",
)

_IRRELEVANT_ROW_KEYWORDS = (
    "reclassifications, net of tax",
    "reclassification out of aoci",
    "pension and other postretirement",
    "payroll",
    "advertising expense",
    "rent and occupancy",
    "depreciation",
    "sg&a",
    "impairment",
    "accounting standards update",
    "minimum",
    "maximum",
    "shares of common stock",
    "movement in deferred revenue",
    "balance at end of period",
    "useful life",
    "operating expenses and indirect costs",
    "indirect costs of net revenues",
    "compensation expense",
    "noncompensation expense",
    "provision for loan",
    "provision for credit",
    "benefit driven by tax",
    "tax audit",
    "return on equity",
    "overhead ratio",
    "average equity",
    "total assets",
    "retained loans",
    "noncurrent assets",
    "long-lived assets",
)

_SEGMENT_ALIAS_MAP = {
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
    "us & canada": "United States & Canada",
    "us and canada": "United States & Canada",
    "u.s. & canada": "United States & Canada",
    "u.s. and canada": "United States & Canada",
    "usa & canada": "United States & Canada",
    "usa and canada": "United States & Canada",
    "united states & canada": "United States & Canada",
    "united states and canada": "United States & Canada",
}

_RECONCILING_KEYWORDS = (
    "hedging gains (losses)",
    "hedging gain",
    "hedging loss",
    "hedges",
    "reconciling items",
    "corporate and reconciling",
    "corporate reconciling",
    "corporate items",
    "corporate non-segment",
    "intersegment eliminations",
    "eliminations",
    "other reconciling items",
)

_CONSOLIDATED_TOTAL_KEYWORDS = (
    "total revenue",
    "total revenues",
    "total net sales",
    "total net revenue",
    "consolidated revenue",
    "consolidated net sales",
    "revenue from contract with customer",
    "revenues from contract with customer",
    "revenues from contract with customers",
    "revenues from external customers",
    "net revenues and financial income",
    "total underwriting revenue",
    "operating segments",
    "operating segment",
    "reportable segments",
    "reportable segment",
    "rental (including reimbursements)",
    "rental (including reimbursable)",
    "net premiums earned",
    "property, liability and casualty insurance product line",
    "as reported",
    "reclassification",
    "parent company",
)

_EXACT_TOTAL_NAMES = {"revenue", "net sales", "total", "revenues", "google", "apple", "reportable segments", "operating segments"}


def _norm_seg_key(name_str):
    return re.sub(r"\s+", " ", str(name_str).lower().replace("&", "and")).strip()


def _scale_to_millions(num):
    if num is None:
        return None
    return num / 1e6 if abs(num) >= 1e4 else num


def _map_col_to_fy(col_name):
    c_str = str(col_name).strip()
    m = re.search(r"(\d{4})", c_str)
    return f"FY{m.group(1)}" if m else c_str


def _filter_segment_statements(xbrl_doc, include_extra_bad=False):
    """Selecciona roles XBRL de notas de desglose por segmentos y geografía."""
    if not xbrl_doc or not hasattr(xbrl_doc, "statements"):
        return []
    bad_keywords = _BASE_BAD_ROLE_KEYWORDS + (_EXTRA_10K_BAD_ROLE_KEYWORDS if include_extra_bad else ())
    selected = []
    for stmt in xbrl_doc.statements:
        r_low = str(getattr(stmt, "role_or_type", "")).lower()
        if any(bad in r_low for bad in bad_keywords):
            continue
        if any(k in r_low for k in ("segment", "disaggregation", "brand", "market", "channel", "geographic")) and "details" in r_low:
            selected.append(stmt)
    return selected


def _clean_segment_label_and_parent(lbl, dim_axis):
    """Normaliza la etiqueta XBRL del segmento, descompone ejes hiperdimensionales y clasifica dominio."""
    clean_name = re.sub(
        r"^(reportable segments?|operating segments?|segment reporting|segments?|similar products and services|underwriting operations)\s*[-:]\s*",
        "",
        lbl,
        flags=re.IGNORECASE,
    ).strip()
    clean_name = re.sub(r"\s*\[member\]", "", clean_name, flags=re.IGNORECASE).strip()
    clean_name = re.sub(r"^(country of|region of)\s+", "", clean_name, flags=re.IGNORECASE).strip()

    clean_low = clean_name.strip().lower()
    if clean_low in _SEGMENT_ALIAS_MAP:
        clean_name = _SEGMENT_ALIAS_MAP[clean_low]

    if _DISCLOSURE_NOISE_REGEX.search(clean_name):
        return None

    parent_segment = None
    is_subsegment = False

    if " - " in clean_name:
        parts = [p.strip() for p in clean_name.split(" - ")]
        parts = [re.sub(r"\s*\[member\]", "", p, flags=re.IGNORECASE).strip() for p in parts]
        parts = [re.sub(r"^(country of|region of)\s+", "", p, flags=re.IGNORECASE).strip() for p in parts]
        parts = [
            p
            for p in parts
            if not any(bad in p.lower() for bad in ("as reported", "reclassification", "operating segment", "reportable segment"))
        ]
        if len(parts) >= 3:
            return None
        if len(parts) == 2:
            p0, p1 = parts[0], parts[1]
            p0_low, p1_low = p0.lower(), p1.lower()
            p0 = _SEGMENT_ALIAS_MAP.get(p0_low, p0)
            p1 = _SEGMENT_ALIAS_MAP.get(p1_low, p1)

            if (
                (_GEO_REGEX.search(p0) and not _GEO_REGEX.search(p1) and any(b in p1.lower() for b in ("commerce", "fintech", "corporate")))
                or (not _GEO_REGEX.search(p0) and _GEO_REGEX.search(p1) and any(b in p0.lower() for b in ("commerce", "fintech", "corporate")))
            ):
                return None

            if _GEO_REGEX.search(p0) and _GEO_REGEX.search(p1):
                clean_name, parent_segment, is_subsegment = p1, p0, True
            elif not _GEO_REGEX.search(p0) and _GEO_REGEX.search(p1):
                clean_name, parent_segment, is_subsegment = f"{p0} ({p1})", p0, True
            elif any(k in p0_low for k in ("underwriting operations", "underwriting", "insurance operations")):
                clean_name = re.sub(r"\s+segment$", "", p1, flags=re.IGNORECASE).strip()
            else:
                clean_name, parent_segment, is_subsegment = p0, p1, True
                if p1_low == "fintech" and p0_low in ("services", "net service revenues and financial income"):
                    clean_name = "Financial services and income"
                elif p1_low == "fintech" and p0_low == "product sales":
                    clean_name = "Fintech product sales"
        elif len(parts) == 1:
            clean_name = parts[0]

    clean_name = _SEGMENT_ALIAS_MAP.get(clean_name.strip().lower(), clean_name)
    low_name = clean_name.lower()

    is_geo_axis = any(g_ax in dim_axis for g_ax in ("geograph", "country", "territor"))
    is_prod_axis = any(p_ax in dim_axis for p_ax in ("product", "service", "market"))
    is_geo = (
        (is_geo_axis or bool(_GEO_REGEX.search(clean_name)))
        and not is_prod_axis
        and not any(k in low_name for k in ("commerce", "fintech", "retail", "industrial", "product", "service"))
    )
    is_channel = bool(_CHANNEL_REGEX.match(clean_name.strip()))
    is_reconciling = any(k in low_name for k in _RECONCILING_KEYWORDS)
    is_consolidated_total = (not is_reconciling) and (
        any(k in low_name for k in _CONSOLIDATED_TOTAL_KEYWORDS) or low_name in _EXACT_TOTAL_NAMES
    )
    is_sub = is_consolidated_total or any(k in low_name for k in ("total", "products", "operating segments"))

    return {
        "clean_name": clean_name,
        "parent_segment": parent_segment,
        "is_subsegment": is_subsegment,
        "is_geo": is_geo,
        "is_channel": is_channel,
        "is_reconciling": is_reconciling,
        "is_consolidated_total": is_consolidated_total,
        "is_sub": is_sub,
    }


def _upsert_segment_entry(target_list, entry_fields, v_dict, match_parent=False, geo_supremacy=False):
    """Inserta o combina cronológicamente un segmento en la lista correspondiente."""
    norm_key = _norm_seg_key(entry_fields["name"])
    parent_norm = _norm_seg_key(entry_fields.get("parent") or "")

    existing = next(
        (
            item
            for item in target_list
            if _norm_seg_key(item.get("name", "")) == norm_key
            and (not match_parent or _norm_seg_key(item.get("parent") or "") == parent_norm)
        ),
        None,
    )
    if existing:
        if geo_supremacy and not entry_fields.get("is_subsegment") and entry_fields.get("parent") is None and (
            existing.get("is_subsegment") or existing.get("parent")
        ):
            existing["is_subsegment"] = False
            existing["parent"] = None
            for fy, val in v_dict.items():
                existing["values"][fy] = val
        else:
            for fy, val in v_dict.items():
                if fy not in existing["values"]:
                    existing["values"][fy] = val
    else:
        target_list.append({**entry_fields, "values": v_dict})


def _scan_10k_segment_filings(valid_k_filings, filing_context):
    """Escanea hasta 8 filings 10-K/20-F para extraer segmentos producto/canal/geografía y EBIT por segmento."""
    product_segments, channel_segments, geographic_segments, segment_op_income = [], [], [], []

    for doc_filing in valid_k_filings[:8]:
        try:
            x_10k = filing_context.get_filing_xbrl(doc_filing) if filing_context else doc_filing.xbrl()
        except Exception as exc:
            logger.debug("Omitiendo filing 10-K/20-F sin XBRL legible en segmentos: %s", exc)
            continue

        for stmt in _filter_segment_statements(x_10k, include_extra_bad=True):
            try:
                df = stmt.to_dataframe()
                fy_cols = {
                    c: _map_col_to_fy(str(c))
                    for c in df.columns
                    if "(FY)" in str(c) or re.search(r"\b20\d\d\b", str(c))
                }
                last_prod_level_map = {}

                for _, row in df.iterrows():
                    lbl = str(row.get("label", "")).strip()
                    conc = str(row.get("concept", "")).lower()
                    dim_axis = str(row.get("dimension_axis") or row.get("dimension") or "").lower()
                    row_lvl = int(row.get("level", 0)) if (pd.notna(row.get("level")) and str(row.get("level")).isdigit()) else 0

                    if not lbl or len(lbl) < 2 or _DISCLOSURE_NOISE_REGEX.search(lbl):
                        continue
                    if any(bad in lbl.lower() for bad in _IRRELEVANT_ROW_KEYWORDS):
                        continue

                    is_rev = any(k in conc for k in ("revenue", "sales", "premiumsearned", "leaseincome", "contractwithcustomer"))
                    is_op_inc = any(k in conc for k in ("operatingincome", "incomelossfromcontinuingoperations"))
                    if not (is_rev or is_op_inc):
                        continue

                    v_dict = {}
                    for raw_col, fy_norm in fy_cols.items():
                        val = row.get(raw_col)
                        if pd.notna(val) and val != "":
                            try:
                                v_dict[fy_norm] = round(_scale_to_millions(float(val)), 1)
                            except (ValueError, TypeError) as exc:
                                logger.debug("Valor no numérico ignorado en segmento %s (%s): %s", lbl, raw_col, exc)
                    if not v_dict:
                        continue

                    parsed = _clean_segment_label_and_parent(lbl, dim_axis)
                    if parsed is None:
                        continue

                    clean_name = parsed["clean_name"]
                    parent_segment = parsed["parent_segment"]
                    is_subsegment = parsed["is_subsegment"]

                    if not parsed["is_geo"] and not parsed["is_consolidated_total"] and not parsed["is_reconciling"]:
                        if not is_subsegment and row_lvl > 0 and last_prod_level_map.get(row_lvl - 1):
                            parent_segment = last_prod_level_map[row_lvl - 1]
                            is_subsegment = True
                        elif not is_subsegment:
                            last_prod_level_map[row_lvl] = clean_name

                    if is_op_inc:
                        _upsert_segment_entry(segment_op_income, {"name": clean_name}, v_dict)
                    elif parsed["is_channel"]:
                        _upsert_segment_entry(
                            channel_segments,
                            {"name": clean_name, "is_subtotal": False, "is_subsegment": is_subsegment, "parent": parent_segment},
                            v_dict,
                        )
                    elif parsed["is_geo"]:
                        _upsert_segment_entry(
                            geographic_segments,
                            {"name": clean_name, "is_subtotal": parsed["is_sub"], "is_subsegment": is_subsegment, "parent": parent_segment},
                            v_dict,
                            geo_supremacy=True,
                        )
                    elif not parsed["is_consolidated_total"]:
                        _upsert_segment_entry(
                            product_segments,
                            {
                                "name": clean_name,
                                "is_subtotal": parsed["is_sub"],
                                "is_subsegment": is_subsegment,
                                "is_reconciling": parsed["is_reconciling"],
                                "parent": parent_segment,
                            },
                            v_dict,
                            match_parent=True,
                        )
            except Exception as s_err:
                logger.warning("Aviso analizando tabla de segmentos 10-K: %s", s_err)

    return product_segments, channel_segments, geographic_segments, segment_op_income


def _resolve_segment_hierarchies(product_segments, geographic_segments, latest_fy):
    """Resuelve dinámicamente jerarquías geográficas, nodos padres sintéticos y huérfanos."""
    all_geo_names = {item["name"].lower() for item in geographic_segments}
    for item in geographic_segments:
        name_low = item["name"].lower()
        if item.get("parent") and item["parent"].lower() not in all_geo_names:
            item["parent"] = None
            item["is_subsegment"] = False

        if name_low in ("united states", "u.s.", "u.s", "us"):
            parent_found = next((p for p in ("americas", "united states & canada", "north america") if p in all_geo_names), None)
            if parent_found:
                item["is_subsegment"] = True
                item["parent"] = next(g["name"] for g in geographic_segments if g["name"].lower() == parent_found)
            elif any(k in all_geo_names for k in ("brazil", "mexico", "latin america", "europe")) and "other countries" in all_geo_names:
                item["is_country_breakdown"] = True
                item["is_subsegment"] = True
                parent_item = next((g for g in geographic_segments if g["name"].lower() == "other countries"), None)
                if parent_item:
                    item["parent"] = parent_item["name"]
            else:
                item["is_subsegment"] = False
                item["parent"] = None
        elif name_low == "china":
            if "greater china" in all_geo_names:
                item["is_subsegment"] = True
                item["parent"] = next(g["name"] for g in geographic_segments if g["name"].lower() == "greater china")
            else:
                item["is_subsegment"] = False
                item["parent"] = None
        elif name_low == "other countries":
            item["is_country_breakdown"] = any(r in all_geo_names for r in ("americas", "europe", "greater china", "rest of asia pacific"))

    for item in product_segments:
        if item.get("parent") and item["parent"].lower() in ("other", "u.k."):
            matching_children = [c for c in product_segments if c.get("parent") and c["parent"].lower() == item["name"].lower()]
            if matching_children:
                item["parent"] = None
                item["is_subsegment"] = False
                for child in matching_children:
                    for k, v in child.get("values", {}).items():
                        if v is not None:
                            item["values"][k] = round(item["values"].get(k, 0.0) + float(v), 1)

    all_prod_names = {item["name"].lower() for item in product_segments}
    synthetic_parents = []
    for item in product_segments:
        p_name = item.get("parent")
        if p_name and p_name.lower() not in all_prod_names:
            matching_children = [c for c in product_segments if c.get("parent") and c["parent"].lower() == p_name.lower()]
            if matching_children and not any(sp["name"].lower() == p_name.lower() for sp in synthetic_parents):
                p_vals = {}
                for child in matching_children:
                    for k, v in child.get("values", {}).items():
                        if v is not None:
                            p_vals[k] = round(p_vals.get(k, 0.0) + float(v), 1)
                synthetic_parents.append(
                    {
                        "name": p_name,
                        "is_subtotal": False,
                        "is_subsegment": False,
                        "parent": None,
                        "status": "active" if any(p_vals.get(p) for p in (latest_fy, "LTM")) else "discontinued",
                        "values": p_vals,
                    }
                )
                all_prod_names.add(p_name.lower())
    if synthetic_parents:
        product_segments = synthetic_parents + product_segments

    all_prod_names = {item["name"].lower() for item in product_segments}
    for item in product_segments:
        if item.get("parent") and item["parent"].lower() not in all_prod_names:
            item["parent"] = None
            item["is_subsegment"] = False

    return product_segments


def _inject_10q_ltm_segments(
    f10k_list,
    f10q_list,
    filing_context,
    product_segments,
    channel_segments,
    geographic_segments,
    segment_op_income,
    latest_fy,
    canonical_rev,
):
    """Escanea 10-Q para LTM por segmentos (FY + YTD_actual - YTD_prev), asigna status y particiones ASC."""
    if f10q_list and (product_segments or geographic_segments or channel_segments):
        try:
            k_rep_date = str(getattr(f10k_list[0], "period_of_report", "")) if f10k_list else ""
            q_rep_date = str(getattr(f10q_list[0], "period_of_report", ""))
            if not k_rep_date or q_rep_date > k_rep_date:
                x_10q = filing_context.get_filing_xbrl(f10q_list[0]) if filing_context else f10q_list[0].xbrl()
                for stmt in _filter_segment_statements(x_10q, include_extra_bad=False):
                    try:
                        q_df = stmt.to_dataframe()
                        ytd_cols = [c for c in q_df.columns if "YTD" in str(c) and any(ch.isdigit() for ch in str(c))]
                        if not ytd_cols:
                            ytd_cols = [c for c in q_df.columns if any(ch.isdigit() for ch in str(c)) and ("Q" in str(c) or "202" in str(c))]
                        ytd_sorted = sorted(ytd_cols, key=str, reverse=True)
                        if len(ytd_sorted) < 2:
                            continue
                        ytd_curr, ytd_prev = ytd_sorted[0], ytd_sorted[1]

                        for _, row in q_df.iterrows():
                            lbl = str(row.get("label", "")).strip()
                            conc = str(row.get("concept", "")).lower()
                            if not lbl or len(lbl) < 2 or _DISCLOSURE_NOISE_REGEX.search(lbl):
                                continue
                            is_rev = any(k in conc for k in ("revenue", "sales"))
                            is_op_inc = any(k in conc for k in ("operatingincome", "incomelossfromcontinuingoperations"))
                            if not (is_rev or is_op_inc):
                                continue

                            v_curr_raw, v_prev_raw = row.get(ytd_curr), row.get(ytd_prev)
                            if pd.isna(v_curr_raw) or pd.isna(v_prev_raw) or v_curr_raw == "" or v_prev_raw == "":
                                continue
                            try:
                                v_curr_m = _scale_to_millions(float(v_curr_raw))
                                v_prev_m = _scale_to_millions(float(v_prev_raw))
                            except (ValueError, TypeError) as exc:
                                logger.debug("Valor no numérico en 10-Q segmento %s: %s", lbl, exc)
                                continue

                            q_clean_name = re.sub(
                                r"^(reportable segments?|operating segments?|segment reporting|segments?)\s*[-:]\s*",
                                "",
                                lbl,
                                flags=re.IGNORECASE,
                            ).strip()
                            if _DISCLOSURE_NOISE_REGEX.search(q_clean_name):
                                continue

                            q_parent = None
                            if " - " in q_clean_name and not _GEO_REGEX.search(q_clean_name):
                                parts = q_clean_name.split(" - ")
                                if any(k in parts[0].lower() for k in ("operating segment", "reportable segment", "segment reporting")):
                                    q_clean_name = parts[-1].strip()
                                elif len(parts) == 2:
                                    q_clean_name, q_parent = parts[0].strip(), parts[1].strip()
                                else:
                                    q_clean_name = parts[-1].strip()

                            if q_parent and q_parent.lower() == "fintech" and q_clean_name.lower() in ("services", "net service revenues and financial income"):
                                q_norm_names = [_norm_seg_key(q_clean_name), "financial services and income"]
                            elif q_parent and q_parent.lower() == "fintech" and q_clean_name.lower() == "product sales":
                                q_norm_names = [_norm_seg_key(q_clean_name), "fintech product sales"]
                            else:
                                q_norm_names = [_norm_seg_key(q_clean_name)]

                            target_lists = [segment_op_income] if is_op_inc else [product_segments, channel_segments, geographic_segments]
                            for t_list in target_lists:
                                for item in t_list:
                                    matches_name = _norm_seg_key(item.get("name", "")) in q_norm_names or _norm_seg_key(item.get("name", "")) == _norm_seg_key(lbl)
                                    matches_parent = True if not (q_parent and item.get("parent")) else (_norm_seg_key(item.get("parent")) == _norm_seg_key(q_parent))
                                    if matches_name and matches_parent:
                                        v_fy = item.get("values", {}).get(latest_fy)
                                        if v_fy is not None and "LTM" not in item["values"]:
                                            item["values"]["LTM"] = round(v_fy + v_curr_m - v_prev_m, 1)
                    except Exception as q_s_err:
                        print(f"[SEC Extractor] Aviso analizando tabla de segmentos 10-Q: {q_s_err}")
        except Exception as q_err:
            print(f"[SEC Extractor] Aviso en escaneo 10-Q de segmentos: {q_err}")

    for t_list in (product_segments, channel_segments, geographic_segments, segment_op_income):
        for item in t_list:
            if "LTM" not in item["values"] and latest_fy in item["values"]:
                item["values"]["LTM"] = item["values"][latest_fy]

    for item in product_segments + channel_segments + geographic_segments:
        vals = item.get("values", {})
        item["status"] = "active" if (vals.get("LTM") is not None or vals.get(latest_fy) is not None) else "discontinued"

    active_prods = [
        p
        for p in product_segments
        if p.get("status") == "active" and not p.get("is_subtotal") and not p.get("is_subsegment") and not p.get("is_reconciling")
    ]
    can_ltm_ref = None
    if canonical_rev:
        can_ltm_ref = canonical_rev.get("LTM") or canonical_rev.get(latest_fy)
        if can_ltm_ref and abs(can_ltm_ref) >= 1e4:
            can_ltm_ref = can_ltm_ref / 1e6

    if can_ltm_ref and len(active_prods) >= 3:
        rev_type_items = [
            p
            for p in active_prods
            if any(k in p["name"].lower() for k in ("net service", "net product", "service revenue", "product revenue", "product sales"))
        ]
        business_unit_items = [p for p in active_prods if p not in rev_type_items]
        if rev_type_items and business_unit_items:
            sum_rev_types = sum((p.get("values", {}).get("LTM") or 0.0) for p in rev_type_items)
            sum_bus_units = sum((p.get("values", {}).get("LTM") or 0.0) for p in business_unit_items)
            if abs(sum_rev_types - can_ltm_ref) / can_ltm_ref < 0.05 and abs(sum_bus_units - can_ltm_ref) / can_ltm_ref < 0.05:
                for p in rev_type_items:
                    p["is_subsegment"] = True
                    p["parent"] = "Tipo de Ingreso (ASC 606)"


def _apply_banking_and_cache_fallbacks(output_dir, seg_json_path, product_segments, channel_segments, geographic_segments, segment_op_income):
    """Deriva líneas NII/Fee en banca si no hay ASC 280 y cae a caché si la nota está vacía."""
    active_prod_count = len([p for p in product_segments if p.get("status") == "active" and not p.get("is_subtotal")])
    if active_prod_count == 0 and output_dir:
        fin_stmt_path = Path(output_dir) / "financial_statements.json"
        if fin_stmt_path.exists():
            try:
                with open(fin_stmt_path, "r", encoding="utf-8") as f_in:
                    f_data = json.load(f_in)
                if f_data.get("archetype") == "FINANCIAL_BANKING" or f_data.get("is_financial", False):
                    inc_det = f_data.get("income_statement_detail", {})
                    nii_k = next((k for k in inc_det if any(w in k.lower() for w in ("interestincome", "interest_income", "financialinstruments", "revenuefrominterest"))), None)
                    fee_k = next((k for k in inc_det if any(w in k.lower() for w in ("feeandcommission", "fee_income", "noninterestincome", "commissions"))), None)
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
                                "values": v_nii_net,
                            },
                            {
                                "name": "Ingresos por Comisiones y Tarifas (Fee & Commission Income)",
                                "description": "Comisiones por transacciones, servicios bancarios, interchange fees y productos de valor agregado.",
                                "is_subtotal": False,
                                "is_subsegment": False,
                                "status": "active",
                                "values": v_fee,
                            },
                        ]
            except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
                logger.debug("Fallback bancario de segmentos omitido: %s", exc)

    if not product_segments and not geographic_segments and seg_json_path.exists():
        try:
            with open(seg_json_path, "r", encoding="utf-8") as f:
                cached = json.load(f)
            product_segments = cached.get("product_segments", [])
            channel_segments = cached.get("channel_segments", [])
            geographic_segments = cached.get("geographic_segments", [])
            segment_op_income = cached.get("segment_operating_income", [])
        except (OSError, json.JSONDecodeError) as exc:
            logger.debug("No se pudo leer caché de segmentos (%s): %s", seg_json_path, exc)

    return product_segments, channel_segments, geographic_segments, segment_op_income


def _attach_segment_operating_income(product_segments, channel_segments, geographic_segments, segment_op_income):
    """Cruza ingresos y beneficio operativo por segmento calculando márgenes operativos."""
    for seg_list in (product_segments, channel_segments, geographic_segments):
        for item in seg_list:
            item_norm = _norm_seg_key(item.get("name", ""))
            matching_op = next(
                (
                    op_item
                    for op_item in segment_op_income
                    if _norm_seg_key(op_item.get("name", "")) == item_norm
                    or (len(item_norm) > 4 and item_norm in _norm_seg_key(op_item.get("name", "")))
                    or (len(_norm_seg_key(op_item.get("name", ""))) > 4 and _norm_seg_key(op_item.get("name", "")) in item_norm)
                ),
                None,
            )
            if matching_op:
                item["operating_income"] = dict(matching_op.get("values", {}))
                seg_vals = item.get("values", {})
                op_margins = {
                    p: round((op_val / seg_vals[p]) * 100.0, 2)
                    for p, op_val in matching_op.get("values", {}).items()
                    if seg_vals.get(p) and seg_vals[p] != 0.0
                }
                if op_margins:
                    item["operating_margin_pct"] = op_margins


def build_and_save_segments_data(company, all_fys, output_dir=None, canonical_rev=None, latest_10q_inc=None, filing_context=None):
    """
    Extractor Dinámico y Universal de Segmentos Contables Oficiales desde SEC EDGAR (XBRL)
    bajo normativas ASC 280 y ASC 606; genera segments_data.json y retorna el DataFrame auditado.
    """
    ticker_str = str(getattr(company, "ticker", getattr(company, "tickers", ["UNKNOWN"])[0]))
    output_path = Path(output_dir) if output_dir else (DATA_PROCESSED_DIR / ticker_str.upper())
    seg_json_path = output_path / "segments_data.json"
    if output_dir and ticker_str == "UNKNOWN":
        ticker_str = output_path.name

    clean_fys = list(dict.fromkeys(all_fys or []))
    annual_fys = [p for p in clean_fys if p != "LTM"]
    latest_fy = annual_fys[0] if annual_fys else "FY2025"

    print(f"[SEC Extractor] Extracción dinámica de segmentos XBRL para {ticker_str}...")
    product_segments, channel_segments, geographic_segments, segment_op_income = [], [], [], []

    try:
        src_ctx = filing_context or company
        f10k_list = src_ctx.get_filings(form="10-K") or src_ctx.get_filings(form="20-F")
        f10q_list = src_ctx.get_filings(form="10-Q") or src_ctx.get_filings(form="6-K")
        valid_k_filings = [f for f in (f10k_list or []) if not str(getattr(f, "form", "")).upper().endswith("/A")]

        product_segments, channel_segments, geographic_segments, segment_op_income = _scan_10k_segment_filings(
            valid_k_filings, filing_context
        )
        product_segments = _resolve_segment_hierarchies(product_segments, geographic_segments, latest_fy)
        _inject_10q_ltm_segments(
            f10k_list,
            f10q_list,
            filing_context,
            product_segments,
            channel_segments,
            geographic_segments,
            segment_op_income,
            latest_fy,
            canonical_rev,
        )
    except Exception as e:
        print(f"[SEC Extractor] Aviso escaneando XBRL de segmentos: {e}")

    product_segments, channel_segments, geographic_segments, segment_op_income = _apply_banking_and_cache_fallbacks(
        output_dir, seg_json_path, product_segments, channel_segments, geographic_segments, segment_op_income
    )
    _attach_segment_operating_income(product_segments, channel_segments, geographic_segments, segment_op_income)

    all_seg_items = product_segments + channel_segments + geographic_segments + segment_op_income
    periods_with_seg_data = {k for item in all_seg_items for k, v in item.get("values", {}).items() if v is not None and v != ""}
    clean_periods = [p for p in clean_fys if p in periods_with_seg_data] if periods_with_seg_data else clean_fys
    if "LTM" in clean_fys and "LTM" not in clean_periods:
        clean_periods.insert(0, "LTM")

    seg_dict = {
        "periods": clean_periods,
        "product_segments": product_segments,
        "channel_segments": channel_segments,
        "geographic_segments": geographic_segments,
        "segment_operating_income": segment_op_income,
        "extraction_method": "SEC_EDGAR_XBRL_ASC280_ASC606",
        "ticker": ticker_str,
    }

    try:
        atomic_json_write(seg_json_path, seg_dict, indent=2, ensure_ascii=False)
        print(f"[SEC Extractor] segments_data.json generado dinámicamente y guardado: {seg_json_path}")
    except Exception as w_err:
        print(f"[SEC Extractor] Error guardando segments_data.json: {w_err}")

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
    return build_and_save_segments_data(
        company,
        all_fys,
        output_dir=output_dir,
        canonical_rev=canonical_rev,
        latest_10q_inc=latest_10q_inc,
        filing_context=filing_context,
    )
