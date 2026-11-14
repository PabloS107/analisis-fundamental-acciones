"""
sec_segment_extractor.py - Extractor dinámico y universal de segmentos operativos,
líneas de producto, canales de venta y regiones geográficas desde notas XBRL (ASC 280 y ASC 606).
"""

from datetime import date
import json
import logging
from pathlib import Path
import re
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
    r"united kingdom|germany|france|india|singapore|korea|australia|other countries|"
    r"all other countries|foreign countries"
    r")\b|\bu\.s\.?|\bu\.k\.?|\buk\b)",
    re.IGNORECASE,
)

_DISCLOSURE_NOISE_REGEX = re.compile(
    r"(foreign currencies|foreign currency|constant currency|exchange rate|translation adjustment|"
    r"sales revenue, net - net sales|sales revenue, net - international|international net sales|"
    r"long-lived assets|noncurrent assets|concentration risk|customer concentration|major customer)",
    re.IGNORECASE,
)

_CHANNEL_REGEX = re.compile(
    r"^(wholesale|direct-to-consumer|direct to consumer|directly to consumer|dtc|e-commerce|consumer direct|distributor)$",
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
    "intangible",
    "abovemarket",
    "belowmarket",
    "portfoliosegment",
    "loandelinquency",
    "delinquency",
    "longlivedassets",
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

_BAD_DIMENSION_AXES = (
    "restatementaxis",
    "consolidatedentitiesaxis",
    "awardtypeaxis",
    "sharebasedcompensation",
    "majorcustomersaxis",
    "concentrationrisk",
    "propertyplantandequipment",
    "longlivedassets",
    "leaseliability",
    "valuationallowances",
)

_BAD_CONCEPT_SUBSTRINGS = (
    "liability",
    "contractwithcustomerasset",
    "longlivedassets",
    "rightofuseasset",
    "totalassets",
    "receivable",
    "payable",
    "obligation",
    "deferred",
    "goodwill",
    "concentration",
    "percentage",
    "ratio",
    "depreciation",
    "amortization",
    "impairment",
    "provision",
    "allowance",
    "incometax",
    "deferredtax",
    "taxexpense",
    "taxbenefit",
    "taxasset",
    "taxliability",
    "leasecost",
    "rentexpense",
    "equity",
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
    "restatement adjustment",
    "remaining performance obligation",
    "allowance for credit",
)

_SEGMENT_ALIAS_MAP = {
    "directly to consumer": "Direct-to-Consumer",
    "direct to consumer": "Direct-to-Consumer",
    "ccb": "Consumer & Community Banking (CCB)",
    "consumer & community banking": "Consumer & Community Banking (CCB)",
    "consumer and community banking": "Consumer & Community Banking (CCB)",
    "consumer and community banking (ccb)": "Consumer & Community Banking (CCB)",
    "cib": "Commercial & Investment Bank (CIB)",
    "corporate & investment bank": "Commercial & Investment Bank (CIB)",
    "corporate and investment bank": "Commercial & Investment Bank (CIB)",
    "commercial & investment bank": "Commercial & Investment Bank (CIB)",
    "commercial and investment bank": "Commercial & Investment Bank (CIB)",
    "commercial banking": "Commercial Banking",
    "awm": "Asset & Wealth Management",
    "asset & wealth management": "Asset & Wealth Management",
    "asset and wealth management": "Asset & Wealth Management",
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
    "latam": "Latin America",
    "latin america (latam)": "Latin America",
    "emea": "Europe, Middle East and Africa",
    "europe, middle east and africa (emea)": "Europe, Middle East and Africa",
    "europe, middle east and africa": "Europe, Middle East and Africa",
    "europe, middle east & africa": "Europe, Middle East and Africa",
    "apac": "Asia Pacific",
    "asia pacific (apac)": "Asia Pacific",
    "u.k.": "United Kingdom",
    "u.k": "United Kingdom",
    "uk": "United Kingdom",
    "all other countries": "All other countries",
}

_RECONCILING_KEYWORDS = (
    "hedging gains (losses)",
    "hedging gain",
    "hedging loss",
    "hedges",
    "foreign exchange derivative",
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

_EXACT_TOTAL_NAMES = {
    "revenue",
    "net sales",
    "total",
    "revenues",
    "google",
    "apple",
    "reportable segments",
    "operating segments",
}

_COUNTRY_LEVEL_NAMES = {
    "united states",
    "u.s.",
    "u.s",
    "us",
    "united kingdom",
    "u.k.",
    "china",
    "taiwan",
    "brazil",
    "mexico",
    "argentina",
    "germany",
    "france",
    "ireland",
    "india",
    "singapore",
    "japan",
    "korea",
    "canada",
    "australia",
    "other countries",
    "all other countries",
    "foreign countries",
}

_REGIONAL_GROUP_NAMES = {
    "americas",
    "europe",
    "greater china",
    "rest of asia pacific",
    "united states and canada",
    "latin america",
    "europe, middle east and africa",
    "asia pacific",
    "emea",
    "apac",
    "north america",
    "international",
    "domestic",
}


def _norm_seg_key(name_str):
    return re.sub(r"\s+", " ", str(name_str).lower().replace("&", "and")).strip()


def _canon_match_key(name_str):
    """Normaliza claves de emparejamiento quitando acrónimos entre paréntesis y sufijo 'segment', preservando calificadores geográficos."""
    s = _norm_seg_key(name_str)
    s = re.sub(r'\s*\(\s*"[^"]+"\s*\)\s*$', "", s).strip()
    m_par = re.search(r"\s*\(([^)]{1,14})\)\s*$", s)
    if m_par:
        par_inner = m_par.group(1).strip()
        is_geo_or_scope_qual = (
            par_inner.startswith(("including", "excluding"))
            or par_inner in ("other", "u.s.", "u.s", "us", "u.k.", "u.k", "uk", "rest of world", "domestic", "international")
            or bool(_GEO_REGEX.search(par_inner))
        )
        if not is_geo_or_scope_qual:
            s = s[: m_par.start()].strip()
    s = re.sub(r"\s+segment$", "", s).strip()
    return _norm_seg_key(_SEGMENT_ALIAS_MAP.get(s, s))


def _scale_to_millions(num):
    if num is None:
        return None
    val = num / 1e6 if abs(num) >= 2e6 else float(num)
    return 0.0 if round(val, 1) == 0.0 else val


def _detect_statement_divisor(df, cols):
    """Determina un divisor único por tabla XBRL (1e6 si dólares crudos, 1.0 si ya en millones)."""
    if df is None or not cols:
        return 1.0
    max_abs = 0.0
    for _, row in df.iterrows():
        conc = str(row.get("concept", "")).lower()
        if not _is_valid_segment_concept(conc)[0]:
            continue
        for c in cols:
            raw = row.get(c)
            if pd.notna(raw) and raw != "":
                try:
                    v = abs(float(raw))
                    if v > max_abs:
                        max_abs = v
                except (ValueError, TypeError):
                    continue
    return 1e6 if max_abs >= 2e6 else 1.0


def _scale_with_divisor(raw_val, divisor):
    scaled = round(float(raw_val) / divisor, 1)
    return 0.0 if scaled == 0.0 else scaled


def _map_col_to_fy(col_name):
    c_str = str(col_name).strip()
    m = re.search(r"(\d{4})", c_str)
    return f"FY{m.group(1)}" if m else c_str


def _is_valid_segment_concept(conc):
    """Retorna (is_valid, is_rev, is_op_inc, priority_rank) validando conceptos XBRL."""
    c_low = str(conc or "").lower()
    if any(bad in c_low for bad in _BAD_CONCEPT_SUBSTRINGS):
        return False, False, False, 99
    is_op_inc = any(k in c_low for k in ("operatingincome", "incomelossfromcontinuingoperations"))
    is_rev = any(k in c_low for k in ("revenue", "sales", "premiumsearned", "leaseincome", "contractwithcustomer"))
    if not (is_rev or is_op_inc):
        return False, False, False, 99
    is_secondary_comp = any(k in c_low for k in ("feesandother", "otherrevenue", "otheroperatingincome", "commission")) and not any(
        p in c_low for p in ("contractwithcustomer", "premiumsearned", "leaseincome", "salesrevenue")
    )
    rank = 2 if is_secondary_comp else 1
    return True, is_rev and not is_op_inc, is_op_inc, rank


def _is_bad_dimension_axis(dim_axis):
    d_low = str(dim_axis or "").lower()
    return any(bad in d_low for bad in _BAD_DIMENSION_AXES)


def _strip_inline_quoted_acronym(text):
    """Elimina acrónimos citados y marcadores de nota al pie al final (ej. '(\"US&CAN\")' o '(2)')."""
    cleaned = re.sub(r'\s*\(\s*"[^"]{1,16}"\s*\)\s*$', "", str(text or "")).strip()
    cleaned = re.sub(r"\s*\(\s*\d{1,2}\s*\)\s*$", "", cleaned).strip()
    return cleaned


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
        str(lbl or ""),
        flags=re.IGNORECASE,
    ).strip()
    clean_name = re.sub(r"\s*\[member\]", "", clean_name, flags=re.IGNORECASE).strip()
    clean_name = re.sub(r"^(country of|region of)\s+", "", clean_name, flags=re.IGNORECASE).strip()
    clean_name = _strip_inline_quoted_acronym(clean_name)

    parent_segment = None
    is_subsegment = False

    if " - " in clean_name:
        parts = [p.strip() for p in clean_name.split(" - ")]
        parts = [re.sub(r"\s*\[member\]", "", p, flags=re.IGNORECASE).strip() for p in parts]
        parts = [re.sub(r"^(country of|region of)\s+", "", p, flags=re.IGNORECASE).strip() for p in parts]
        parts = [_strip_inline_quoted_acronym(p) for p in parts]
        parts = [
            p
            for p in parts
            if p and not any(bad in p.lower() for bad in ("as reported", "reclassification", "operating segment", "reportable segment"))
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
            elif (
                not _GEO_REGEX.search(p0)
                and not any(k in p0_low for k in ("underwriting operations", "underwriting", "insurance operations"))
                and (_GEO_REGEX.search(p1) or p1_low in ("other", "rest of world"))
            ):
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
    if re.search(r"\s+segment$", clean_name, flags=re.IGNORECASE):
        stripped = re.sub(r"\s+segment$", "", clean_name, flags=re.IGNORECASE).strip()
        if stripped:
            clean_name = _SEGMENT_ALIAS_MAP.get(stripped.lower(), stripped)

    low_name = clean_name.lower()
    dim_low = str(dim_axis or "").lower()

    is_geo_axis = any(g_ax in dim_low for g_ax in ("geograph", "country", "territor"))
    is_prod_axis = any(p_ax in dim_low for p_ax in ("product", "service", "businesssegment", "subsegment", "market"))
    is_channel_axis = any(c_ax in dim_low for c_ax in ("saleschannel", "channel"))

    is_geo = (
        (is_geo_axis or bool(_GEO_REGEX.search(clean_name)))
        and not is_prod_axis
        and not any(k in low_name for k in ("commerce", "fintech", "retail", "industrial", "product", "service"))
    )
    if not parent_segment and _norm_seg_key(clean_name) in (_COUNTRY_LEVEL_NAMES | _REGIONAL_GROUP_NAMES):
        is_geo = True
    is_channel = bool(_CHANNEL_REGEX.match(clean_name.strip())) or (is_channel_axis and low_name == "retail")
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


def _upsert_segment_entry(target_list, entry_fields, v_dict, match_parent=False, geo_supremacy=False, concept_rank=1):
    """Inserta o combina cronológicamente un segmento en la lista correspondiente."""
    norm_key = _canon_match_key(entry_fields["name"])
    parent_norm = _canon_match_key(entry_fields.get("parent") or "")

    existing = next(
        (
            item
            for item in target_list
            if _canon_match_key(item.get("name", "")) == norm_key
            and (not match_parent or _canon_match_key(item.get("parent") or "") == parent_norm)
        ),
        None,
    )
    if existing:
        existing_ranks = existing.setdefault("_concept_ranks", {})
        if geo_supremacy and not entry_fields.get("is_subsegment") and entry_fields.get("parent") is None and (
            existing.get("is_subsegment") or existing.get("parent")
        ):
            existing["is_subsegment"] = False
            existing["parent"] = None
            for fy, val in v_dict.items():
                existing["values"][fy] = val
                existing_ranks[fy] = concept_rank
        else:
            for fy, val in v_dict.items():
                prev_rank = existing_ranks.get(fy, 99)
                if fy not in existing["values"] or concept_rank < prev_rank:
                    existing["values"][fy] = val
                    existing_ranks[fy] = concept_rank
    else:
        entry_copy = dict(entry_fields)
        entry_copy["values"] = dict(v_dict)
        entry_copy["_concept_ranks"] = {fy: concept_rank for fy in v_dict}
        target_list.append(entry_copy)


def _scan_10k_segment_filings(valid_k_filings, filing_context):
    """Escanea hasta 10 filings 10-K/20-F para extraer segmentos producto/canal/geografía y EBIT por segmento."""
    product_segments, channel_segments, geographic_segments, segment_op_income = [], [], [], []

    for doc_filing in valid_k_filings[:10]:
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
                if not fy_cols:
                    continue
                divisor = _detect_statement_divisor(df, list(fy_cols.keys()))
                last_prod_level_map = {}
                prev_conc_axis = None

                for _, row in df.iterrows():
                    lbl = str(row.get("label", "")).strip()
                    conc_raw = str(row.get("concept", "")).strip()
                    conc = conc_raw.lower()
                    dim_axis = str(row.get("dimension_axis") or row.get("dimension") or "").lower()
                    row_lvl = int(row.get("level", 0)) if (pd.notna(row.get("level")) and str(row.get("level")).isdigit()) else 0

                    if not lbl or len(lbl) < 2 or _DISCLOSURE_NOISE_REGEX.search(lbl):
                        continue
                    if _is_bad_dimension_axis(dim_axis):
                        continue
                    if any(bad in lbl.lower() for bad in _IRRELEVANT_ROW_KEYWORDS):
                        continue

                    is_valid, is_rev, is_op_inc, concept_rank = _is_valid_segment_concept(conc)
                    if not is_valid:
                        continue

                    if (conc, dim_axis) != prev_conc_axis:
                        last_prod_level_map = {}
                        prev_conc_axis = (conc, dim_axis)

                    v_dict = {}
                    for raw_col, fy_norm in fy_cols.items():
                        val = row.get(raw_col)
                        if pd.notna(val) and val != "":
                            try:
                                v_dict[fy_norm] = _scale_with_divisor(float(val), divisor)
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
                        _upsert_segment_entry(segment_op_income, {"name": clean_name}, v_dict, concept_rank=concept_rank)
                    elif parsed["is_channel"]:
                        _upsert_segment_entry(
                            channel_segments,
                            {"name": clean_name, "is_subtotal": False, "is_subsegment": is_subsegment, "parent": parent_segment},
                            v_dict,
                            concept_rank=concept_rank,
                        )
                    elif parsed["is_geo"]:
                        _upsert_segment_entry(
                            geographic_segments,
                            {"name": clean_name, "is_subtotal": parsed["is_sub"], "is_subsegment": is_subsegment, "parent": parent_segment},
                            v_dict,
                            geo_supremacy=True,
                            concept_rank=concept_rank,
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
                                "source_concept": conc_raw,
                            },
                            v_dict,
                            match_parent=True,
                            concept_rank=concept_rank,
                        )
            except Exception as s_err:
                logger.warning("Aviso analizando tabla de segmentos 10-K: %s", s_err)

    return product_segments, channel_segments, geographic_segments, segment_op_income


def _deduplicate_segment_list(seg_list):
    """Combina duplicados residuales por nombre canónico tras resolver jerarquías."""
    merged = []
    for item in seg_list:
        _upsert_segment_entry(
            merged,
            {k: v for k, v in item.items() if k not in ("values", "_concept_ranks")},
            item.get("values", {}),
            match_parent=True,
        )
    return merged


def _can_subordinate_us_to_other_countries(us_item, geographic_segments, latest_fy):
    """Valida si EE. UU. es un desglose dentro de 'Other countries' (vigencia y cota de magnitud)."""
    other_item = next((g for g in geographic_segments if g["name"].lower() == "other countries"), None)
    if not other_item:
        return None
    intl_siblings = [
        g for g in geographic_segments
        if g["name"].lower() in ("brazil", "mexico", "latin america", "europe")
    ]
    if not intl_siblings:
        return None

    us_vals = us_item.get("values", {}) or {}
    other_vals = other_item.get("values", {}) or {}
    if latest_fy and us_vals.get(latest_fy) is not None:
        if other_vals.get(latest_fy) is None:
            return None
        if not any((s.get("values", {}) or {}).get(latest_fy) is not None for s in intl_siblings):
            return None

    common = [p for p in us_vals if us_vals.get(p) is not None and other_vals.get(p) is not None]
    if common:
        ref_p = latest_fy if latest_fy in common else sorted(common, reverse=True)[0]
        if float(us_vals[ref_p]) > float(other_vals[ref_p]) * 1.05:
            return None

    return other_item["name"]


def _resolve_segment_hierarchies(product_segments, geographic_segments, latest_fy):
    """Resuelve dinámicamente jerarquías geográficas, nodos padres sintéticos y huérfanos."""
    all_geo_names = {item["name"].lower() for item in geographic_segments}
    active_geo_names = {
        item["name"].lower()
        for item in geographic_segments
        if latest_fy and (item.get("values", {}) or {}).get(latest_fy) is not None
    }
    for item in geographic_segments:
        name_low = item["name"].lower()
        if item.get("parent") and item["parent"].lower() not in all_geo_names:
            item["parent"] = None
            item["is_subsegment"] = False

        if name_low in ("united states", "u.s.", "u.s", "us"):
            parent_found = next((p for p in ("americas", "united states & canada", "north america") if p in all_geo_names), None)
            if parent_found:
                parent_item = next(g for g in geographic_segments if g["name"].lower() == parent_found)
                # Sólo subordina EE.UU. al padre regional si es menor o igual que la región (ej. META);
                # si coexiste con una partición estatutaria completa, _resolve_competing_geo_partitions lo aislará.
                p_vals = parent_item.get("values", {}) or {}
                u_vals = item.get("values", {}) or {}
                common = [p for p in u_vals if u_vals.get(p) is not None and p_vals.get(p) is not None]
                ref_p = latest_fy if latest_fy in common else (sorted(common, reverse=True)[0] if common else None)
                if ref_p and float(u_vals[ref_p]) <= float(p_vals[ref_p]) * 1.01:
                    item["is_subsegment"] = True
                    item["parent"] = parent_item["name"]
                else:
                    item["is_subsegment"] = False
                    item["parent"] = None
            else:
                other_parent = _can_subordinate_us_to_other_countries(item, geographic_segments, latest_fy)
                if other_parent:
                    item["is_country_breakdown"] = True
                    item["is_subsegment"] = True
                    item["parent"] = other_parent
                else:
                    item["is_country_breakdown"] = False
                    item["is_subsegment"] = False
                    item["parent"] = None
        elif name_low == "china":
            if "greater china" in all_geo_names:
                item["is_subsegment"] = True
                item["parent"] = next(g["name"] for g in geographic_segments if g["name"].lower() == "greater china")
            else:
                item["is_subsegment"] = False
                item["parent"] = None
        elif name_low in ("other countries", "all other countries"):
            ref_names = active_geo_names if latest_fy and (item.get("values", {}) or {}).get(latest_fy) is not None else all_geo_names
            item["is_country_breakdown"] = any(
                r in ref_names for r in ("americas", "europe", "greater china", "rest of asia pacific", "united states & canada", "latin america", "europe, middle east and africa", "asia pacific")
            )

    for item in product_segments:
        p_raw = item.get("parent")
        if p_raw and _canon_match_key(p_raw) in ("other", "u.k.", "united kingdom"):
            item_canon = _canon_match_key(item["name"])
            if item_canon != _canon_match_key(p_raw):
                matching_children = [
                    c for c in product_segments
                    if c is not item and c.get("parent") and _canon_match_key(c["parent"]) == item_canon
                ]
                if matching_children:
                    item["parent"] = None
                    item["is_subsegment"] = False

    all_prod_names = {_canon_match_key(item["name"]) for item in product_segments}
    synthetic_parents = []
    for item in product_segments:
        p_name = item.get("parent")
        p_canon = _canon_match_key(p_name) if p_name else ""
        if p_name and p_canon not in all_prod_names:
            matching_children = [
                c for c in product_segments
                if c.get("parent") and _canon_match_key(c["parent"]) == p_canon
            ]
            if matching_children and not any(_canon_match_key(sp["name"]) == p_canon for sp in synthetic_parents):
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
                        "status": "active" if any(p_vals.get(p) is not None for p in (latest_fy, "LTM")) else "discontinued",
                        "values": p_vals,
                    }
                )
                all_prod_names.add(p_canon)
    if synthetic_parents:
        product_segments = synthetic_parents + product_segments

    all_prod_names = {_canon_match_key(item["name"]) for item in product_segments}
    for item in product_segments:
        if item.get("parent") and _canon_match_key(item["parent"]) not in all_prod_names:
            item["parent"] = None
            item["is_subsegment"] = False

    product_segments = _deduplicate_segment_list(product_segments)
    return product_segments


def _resolve_competing_geo_partitions(geographic_segments, latest_fy, canonical_rev):
    """Detecta particiones estatutarias por país (~100% revenue) compitiendo con regiones operativas y las marca como country breakdown."""
    if not geographic_segments:
        return
    ref_p = "LTM" if any(g.get("values", {}).get("LTM") is not None for g in geographic_segments) else latest_fy
    if not ref_p:
        return

    can_ref = None
    if canonical_rev:
        raw_ref = canonical_rev.get(ref_p) or canonical_rev.get(latest_fy)
        if raw_ref is not None:
            can_ref = _scale_to_millions(raw_ref)

    active_geos = [
        g for g in geographic_segments
        if not g.get("is_subtotal") and g.get("values", {}).get(ref_p) is not None
    ]
    regional_cohort = [
        g for g in active_geos
        if not g.get("is_subsegment") and _canon_match_key(g["name"]) in _REGIONAL_GROUP_NAMES
    ]
    country_cohort = [
        g for g in active_geos
        if _canon_match_key(g["name"]) in _COUNTRY_LEVEL_NAMES
    ]
    has_other_countries = any(
        _canon_match_key(g["name"]) in ("other countries", "all other countries", "foreign countries")
        for g in country_cohort
    )
    if len(regional_cohort) < 2 or len(country_cohort) < 2 or not has_other_countries:
        return

    reg_sum = sum(float(g["values"][ref_p]) for g in regional_cohort)
    ctry_sum = sum(float(g["values"][ref_p]) for g in country_cohort)
    target_rev = can_ref or max(reg_sum, ctry_sum)
    if target_rev <= 0:
        return

    # Países que forman parte de la partición regional primaria (ej. Japan en AAPL)
    # no deben reclasificarse como breakdown secundario si moverlos al cohort regional
    # reduce simultáneamente el error de ambas particiones contra consolidated revenue.
    for cand in list(country_cohort):
        ck = _canon_match_key(cand["name"])
        if ck in ("other countries", "all other countries", "foreign countries") or cand.get("is_subsegment"):
            continue
        val_c = float(cand["values"][ref_p])
        if val_c <= 0:
            continue
        if (
            abs((reg_sum + val_c) - target_rev) < abs(reg_sum - target_rev)
            and abs((ctry_sum - val_c) - target_rev) < abs(ctry_sum - target_rev)
        ):
            country_cohort.remove(cand)
            regional_cohort.append(cand)
            reg_sum += val_c
            ctry_sum -= val_c

    if abs(reg_sum - target_rev) / target_rev <= 0.15 and abs(ctry_sum - target_rev) / target_rev <= 0.15:
        for g in country_cohort:
            g["is_country_breakdown"] = True
            g["is_subsegment"] = True


def _parse_10q_col_meta(col_name):
    c_str = str(col_name).strip()
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})\s*(?:\(([^)]+)\))?", c_str)
    if not m:
        return None
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    tag = (m.group(4) or "").strip().upper()
    if tag == "FY":
        return None
    try:
        dt = date(y, mo, d)
    except ValueError:
        return None
    return {"col": col_name, "date": dt, "tag": tag}


def _extract_10q_period_pair(q_df, k_rep_date=""):
    """Encuentra el par comparable (YTD_actual, YTD_prev) ignorando columnas vacías o trimestres aislados."""
    candidates = []
    for col in q_df.columns:
        meta = _parse_10q_col_meta(col)
        if meta:
            candidates.append(meta)
    if not candidates:
        return None

    # Contar celdas numéricas válidas por columna solo sobre filas candidatas de ingresos/EBIT
    valid_mask = q_df.apply(lambda r: _is_valid_segment_concept(r.get("concept", ""))[0], axis=1)
    sub_df = q_df[valid_mask] if valid_mask.any() else q_df

    populated = []
    for meta in candidates:
        series = sub_df[meta["col"]]
        nn = sum(1 for v in series if pd.notna(v) and str(v).strip() != "")
        if nn > 0:
            populated.append(meta)
    if len(populated) < 2:
        return None

    ytd_pops = [m for m in populated if m["tag"] == "YTD"]
    q1_pops = [m for m in populated if m["tag"] == "Q1"]
    other_pops = [m for m in populated if m["tag"] in ("", "Q2", "Q3")]

    ordered_pools = [p for p in (ytd_pops, q1_pops, other_pops) if len(p) >= 2]
    if not ordered_pools:
        ordered_pools = [populated]

    for pool in ordered_pools:
        pool_sorted = sorted(pool, key=lambda m: m["date"], reverse=True)
        for i, curr in enumerate(pool_sorted):
            target_y = curr["date"].year - 1
            target_d = min(curr["date"].day, 28) if (curr["date"].month == 2 and curr["date"].day == 29) else curr["date"].day
            target_prev_dt = date(target_y, curr["date"].month, target_d)
            best_prev = None
            best_delta = 999
            for prev in pool_sorted[i + 1:]:
                if prev["tag"] != curr["tag"] and curr["tag"] == "YTD":
                    continue
                delta = abs((prev["date"] - target_prev_dt).days)
                if delta <= 15 and delta < best_delta:
                    best_delta = delta
                    best_prev = prev
            if best_prev:
                months_label = "3M" if curr["tag"] == "Q1" else ("YTD")
                if k_rep_date:
                    try:
                        ky, km, _ = [int(x) for x in str(k_rep_date)[:10].split("-")]
                        diff_m = ((curr["date"].year - ky) * 12 + (curr["date"].month - km)) % 12
                        if diff_m in (3, 6, 9):
                            months_label = f"{diff_m}M YTD"
                    except (ValueError, IndexError):
                        pass
                return {
                    "curr_col": curr["col"],
                    "prev_col": best_prev["col"],
                    "curr_date": curr["date"].isoformat(),
                    "prev_date": best_prev["date"].isoformat(),
                    "period_label": f"{months_label} ({curr['date'].isoformat()})",
                }
    return None


def _build_dynamic_acronym_map(items):
    """Construye un mapa dinámico de acrónimos a claves canónicas desde segmentos 10-K ya extraídos."""
    acronym_map = {}
    for item in items:
        name = str(item.get("name", ""))
        canon = _canon_match_key(name)
        for grp in re.findall(r"\(([A-Za-z&/]{2,10})\)", name):
            acronym_map[grp.lower()] = canon
        words = [w for w in re.split(r"[\s,&/-]+", name) if w and w.lower() not in ("and", "of", "the", "in", "segment")]
        if len(words) >= 2:
            initials = "".join(w[0].lower() for w in words if w[0].isalpha())
            if len(initials) >= 2 and initials not in acronym_map:
                acronym_map[initials] = canon
    return acronym_map


def _match_10q_target_item(parsed, target_list, acronym_map):
    """Empareja una fila parsed del 10-Q con un ítem existente del 10-K respetando jerarquía."""
    q_name = parsed["clean_name"]
    q_canon = _canon_match_key(q_name)
    q_alias = acronym_map.get(q_canon, q_canon)
    q_parent = parsed.get("parent_segment")
    q_parent_canon = _canon_match_key(q_parent) if q_parent else ""

    exact_matches = []
    for item in target_list:
        i_canon = _canon_match_key(item.get("name", ""))
        if i_canon in (q_canon, q_alias):
            exact_matches.append(item)

    if not exact_matches:
        return None
    if len(exact_matches) == 1 and not (q_parent_canon and exact_matches[0].get("parent")):
        return exact_matches[0]
    for item in exact_matches:
        i_parent_canon = _canon_match_key(item.get("parent") or "")
        if q_parent_canon == i_parent_canon or (not q_parent_canon and not i_parent_canon):
            return item
    return exact_matches[0] if not q_parent_canon else None


def _compute_interim_yoy(v_curr_m, v_prev_m):
    if v_prev_m is None or abs(v_prev_m) < 0.1:
        return None
    return round(((v_curr_m - v_prev_m) / abs(v_prev_m)) * 100.0, 2)


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
    """Escanea el último 10-Q/6-K para calcular LTM exacto, detectar re-segmentaciones o señalar ausencia en 10-Q."""
    k_rep_date = str(getattr(f10k_list[0], "period_of_report", "")) if f10k_list else ""
    q_rep_date = str(getattr(f10q_list[0], "period_of_report", "")) if f10q_list else ""
    q_is_newer = bool(f10q_list and (not k_rep_date or q_rep_date > k_rep_date))

    matched_ids = {"product": set(), "geo": set(), "channel": set(), "op": set()}
    new_10q_items = {"product": [], "geo": [], "channel": []}
    interim_consolidated_rev = None
    interim_period_label = None

    if q_is_newer:
        try:
            x_10q = filing_context.get_filing_xbrl(f10q_list[0]) if filing_context else f10q_list[0].xbrl()
            acronym_map = _build_dynamic_acronym_map(product_segments + geographic_segments + channel_segments + segment_op_income)

            for stmt in _filter_segment_statements(x_10q, include_extra_bad=False):
                try:
                    q_df = stmt.to_dataframe()
                    pair = _extract_10q_period_pair(q_df, k_rep_date=k_rep_date)
                    if not pair:
                        continue
                    curr_col, prev_col = pair["curr_col"], pair["prev_col"]
                    interim_period_label = interim_period_label or pair["period_label"]
                    divisor = _detect_statement_divisor(q_df, [curr_col, prev_col])
                    last_prod_level_map = {}
                    prev_conc_axis = None

                    for _, row in q_df.iterrows():
                        lbl = str(row.get("label", "")).strip()
                        conc_raw = str(row.get("concept", "")).strip()
                        conc = conc_raw.lower()
                        dim_axis = str(row.get("dimension_axis") or row.get("dimension") or "").lower()
                        row_lvl = int(row.get("level", 0)) if (pd.notna(row.get("level")) and str(row.get("level")).isdigit()) else 0

                        if not lbl or len(lbl) < 2 or _DISCLOSURE_NOISE_REGEX.search(lbl):
                            continue
                        if _is_bad_dimension_axis(dim_axis):
                            continue
                        if any(bad in lbl.lower() for bad in _IRRELEVANT_ROW_KEYWORDS):
                            continue

                        is_valid, is_rev, is_op_inc, concept_rank = _is_valid_segment_concept(conc)
                        if not is_valid:
                            continue

                        if (conc, dim_axis) != prev_conc_axis:
                            last_prod_level_map = {}
                            prev_conc_axis = (conc, dim_axis)

                        v_curr_raw, v_prev_raw = row.get(curr_col), row.get(prev_col)
                        if pd.isna(v_curr_raw) or pd.isna(v_prev_raw) or v_curr_raw == "" or v_prev_raw == "":
                            continue
                        try:
                            v_curr_m = _scale_with_divisor(float(v_curr_raw), divisor)
                            v_prev_m = _scale_with_divisor(float(v_prev_raw), divisor)
                        except (ValueError, TypeError) as exc:
                            logger.debug("Valor no numérico en 10-Q segmento %s: %s", lbl, exc)
                            continue

                        parsed = _clean_segment_label_and_parent(lbl, dim_axis)
                        if parsed is None:
                            continue

                        clean_name = parsed["clean_name"]
                        if parsed["is_consolidated_total"] and is_rev:
                            if interim_consolidated_rev is None or v_curr_m > interim_consolidated_rev:
                                interim_consolidated_rev = v_curr_m
                            continue

                        if not parsed["is_geo"] and not parsed["is_consolidated_total"] and not parsed["is_reconciling"]:
                            if not parsed["is_subsegment"] and row_lvl > 0 and last_prod_level_map.get(row_lvl - 1):
                                parsed["parent_segment"] = last_prod_level_map[row_lvl - 1]
                                parsed["is_subsegment"] = True
                            elif not parsed["is_subsegment"]:
                                last_prod_level_map[row_lvl] = clean_name

                        interim_info = {
                            "period_label": pair["period_label"],
                            "period_end": pair["curr_date"],
                            "prior_period_end": pair["prev_date"],
                            "current_ytd": v_curr_m,
                            "prior_ytd": v_prev_m,
                            "yoy_pct": _compute_interim_yoy(v_curr_m, v_prev_m),
                        }

                        if is_op_inc:
                            matched_op = _match_10q_target_item(parsed, segment_op_income, acronym_map)
                            if matched_op is not None:
                                v_fy = matched_op.get("values", {}).get(latest_fy)
                                if v_fy is not None and "LTM" not in matched_op["values"]:
                                    matched_op["values"]["LTM"] = round(v_fy + v_curr_m - v_prev_m, 1)
                                matched_ids["op"].add(id(matched_op))
                            else:
                                new_op = {"name": clean_name, "values": {}, "interim_disclosure": interim_info}
                                segment_op_income.append(new_op)
                            continue

                        if parsed["is_channel"]:
                            dom_key, target_list = "channel", channel_segments
                        elif parsed["is_geo"]:
                            dom_key, target_list = "geo", geographic_segments
                        else:
                            dom_key, target_list = "product", product_segments

                        matched = _match_10q_target_item(parsed, target_list, acronym_map)
                        if matched is not None:
                            if matched.get("_interim_rank", 99) > concept_rank or "interim_disclosure" not in matched:
                                matched["interim_disclosure"] = interim_info
                                matched["_interim_rank"] = concept_rank
                            v_fy = matched.get("values", {}).get(latest_fy)
                            if v_fy is not None and ("LTM" not in matched["values"] or concept_rank < matched.get("_ltm_rank", 99)):
                                matched["values"]["LTM"] = round(v_fy + v_curr_m - v_prev_m, 1)
                                matched["_ltm_rank"] = concept_rank
                            matched_ids[dom_key].add(id(matched))
                        else:
                            new_entry = {
                                "name": clean_name,
                                "is_subtotal": parsed["is_sub"],
                                "is_subsegment": parsed["is_subsegment"],
                                "is_reconciling": parsed["is_reconciling"],
                                "parent": parsed["parent_segment"],
                                "status": "active",
                                "is_new_in_latest_10q": True,
                                "values": {},
                                "interim_disclosure": interim_info,
                                "source_concept": conc_raw,
                                "_concept_ranks": {"interim": concept_rank},
                            }
                            existing_new = _match_10q_target_item(parsed, new_10q_items[dom_key], acronym_map)
                            if existing_new is None:
                                new_10q_items[dom_key].append(new_entry)
                except Exception as q_s_err:
                    logger.warning("Aviso analizando tabla de segmentos 10-Q: %s", q_s_err)
        except Exception as q_err:
            logger.warning("Aviso en escaneo 10-Q de segmentos: %s", q_err)

    for dom_key, target_list in (("product", product_segments), ("geo", geographic_segments), ("channel", channel_segments)):
        for new_item in new_10q_items[dom_key]:
            target_list.append(new_item)
            matched_ids[dom_key].add(id(new_item))

    # Re-vincular jerarquías si un nuevo hijo 10-Q tiene padre sintético o existente
    all_prod_names = {p["name"].lower() for p in product_segments}
    for item in product_segments:
        if item.get("parent") and item["parent"].lower() not in all_prod_names:
            item["parent"] = None
            item["is_subsegment"] = False

    reseg_meta = _apply_ltm_and_status_policy(
        q_is_newer=q_is_newer,
        latest_fy=latest_fy,
        product_segments=product_segments,
        channel_segments=channel_segments,
        geographic_segments=geographic_segments,
        segment_op_income=segment_op_income,
        matched_ids=matched_ids,
        new_10q_items=new_10q_items,
        interim_consolidated_rev=interim_consolidated_rev,
        interim_period_label=interim_period_label,
        canonical_rev=canonical_rev,
    )
    return reseg_meta


def _apply_ltm_and_status_policy(
    q_is_newer,
    latest_fy,
    product_segments,
    channel_segments,
    geographic_segments,
    segment_op_income,
    matched_ids,
    new_10q_items,
    interim_consolidated_rev,
    interim_period_label,
    canonical_rev,
):
    """Asigna LTM honesto (sin copias ficticias cuando el 10-Q omite el dato) y clasifica re-segmentaciones."""
    metadata = {
        "q_is_newer_than_10k": q_is_newer,
        "latest_interim_period": interim_period_label,
        "product_ltm_status": "10k_is_latest" if not q_is_newer else "unknown",
        "geo_ltm_status": "10k_is_latest" if not q_is_newer else "unknown",
        "product_resegmented": False,
        "geo_resegmented": False,
        "superseded_after_fy": None,
    }

    if not q_is_newer:
        for t_list in (product_segments, channel_segments, geographic_segments, segment_op_income):
            for item in t_list:
                if "LTM" not in item["values"] and latest_fy in item["values"]:
                    item["values"]["LTM"] = item["values"][latest_fy]
                    item["ltm_disclosure_status"] = "10k_is_latest"
        for item in product_segments + channel_segments + geographic_segments:
            vals = item.get("values", {})
            item["status"] = "active" if (vals.get("LTM") is not None or vals.get(latest_fy) is not None) else "discontinued"
    else:
        for dom_key, target_list, status_key, reseg_key in (
            ("product", product_segments, "product_ltm_status", "product_resegmented"),
            ("geo", geographic_segments, "geo_ltm_status", "geo_resegmented"),
            ("channel", channel_segments, "channel_ltm_status", "channel_resegmented"),
        ):
            has_10q_cov = len(matched_ids[dom_key]) > 0
            new_list = new_10q_items[dom_key]
            active_in_10q = [i for i in target_list if id(i) in matched_ids[dom_key]]
            top_10q_ytd_sum = sum(
                (i.get("interim_disclosure", {}).get("current_ytd") or 0.0)
                for i in active_in_10q
                if not i.get("is_subsegment") and not i.get("is_subtotal") and not i.get("is_reconciling")
            )
            q_covers_most_rev = (
                bool(interim_consolidated_rev)
                and interim_consolidated_rev > 0
                and (top_10q_ytd_sum / interim_consolidated_rev) >= 0.85
            )
            parents_with_new_children = {
                _canon_match_key(n["parent"]) for n in new_list if n.get("is_subsegment") and n.get("parent")
            }
            resegmented_domain = bool(new_list) and (q_covers_most_rev or bool(parents_with_new_children))
            if dom_key in ("product", "geo"):
                metadata[reseg_key] = resegmented_domain
                if resegmented_domain:
                    metadata["superseded_after_fy"] = latest_fy

            if not has_10q_cov:
                if dom_key in ("product", "geo"):
                    metadata[status_key] = "annual_only_not_in_10q"
                for item in target_list:
                    if item.get("values", {}).get(latest_fy) is not None:
                        item["status"] = "active"
                        item["ltm_disclosure_status"] = "annual_only"
                    else:
                        item["status"] = "discontinued"
            else:
                if dom_key in ("product", "geo"):
                    metadata[status_key] = "resegmented_in_10q" if resegmented_domain else "ltm_updated_from_10q"
                for item in target_list:
                    vals = item.get("values", {})
                    if id(item) in matched_ids[dom_key]:
                        item["status"] = "active"
                        item["ltm_disclosure_status"] = (
                            "new_in_10q_interim" if item.get("is_new_in_latest_10q") else "ltm_computed_from_10q"
                        )
                    elif vals.get(latest_fy) is not None:
                        parent_canon = _canon_match_key(item.get("parent") or "")
                        is_child_of_matched = bool(item.get("is_subsegment") and any(
                            _canon_match_key(a.get("name", "")) == parent_canon for a in active_in_10q
                        ))
                        if resegmented_domain and (not item.get("is_subsegment") or parent_canon in parents_with_new_children):
                            item["status"] = "discontinued"
                            item["discontinued_reason"] = "superseded_in_latest_10q"
                            item["discontinued_after"] = latest_fy
                            vals.pop("LTM", None)
                        elif is_child_of_matched or item.get("is_subsegment"):
                            item["status"] = "active"
                            item["ltm_disclosure_status"] = "annual_only"
                            vals.pop("LTM", None)
                        else:
                            item["status"] = "discontinued"
                            item["discontinued_reason"] = "omitted_in_latest_10q"
                            item["discontinued_after"] = latest_fy
                            vals.pop("LTM", None)
                    else:
                        item["status"] = "discontinued"

    # Detección de desglose secundario ASC 606 (producto vs unidad de negocio)
    active_prods = [
        p
        for p in product_segments
        if p.get("status") == "active" and not p.get("is_subtotal") and not p.get("is_subsegment") and not p.get("is_reconciling")
    ]
    can_ltm_ref = None
    if canonical_rev:
        raw_can = canonical_rev.get("LTM") or canonical_rev.get(latest_fy)
        if raw_can is not None:
            can_ltm_ref = _scale_to_millions(raw_can)

    if can_ltm_ref and len(active_prods) >= 3:
        rev_type_items = [
            p
            for p in active_prods
            if any(k in p["name"].lower() for k in ("net service", "net product", "service revenue", "product revenue", "product sales"))
        ]
        business_unit_items = [p for p in active_prods if p not in rev_type_items]
        if rev_type_items and business_unit_items:
            sum_rev_types = sum((p.get("values", {}).get("LTM") or p.get("values", {}).get(latest_fy) or 0.0) for p in rev_type_items)
            sum_bus_units = sum((p.get("values", {}).get("LTM") or p.get("values", {}).get(latest_fy) or 0.0) for p in business_unit_items)
            if abs(sum_rev_types - can_ltm_ref) / can_ltm_ref < 0.05 and abs(sum_bus_units - can_ltm_ref) / can_ltm_ref < 0.05:
                for p in rev_type_items:
                    p["is_subsegment"] = True
                    p["parent"] = "Tipo de Ingreso (ASC 606)"

    # Detectar alcance de tabla de productos si suma <96% de ingresos consolidados (ej. LeaseIncome en REIT)
    ref_p = "LTM" if any(p.get("values", {}).get("LTM") is not None for p in active_prods) else latest_fy
    if can_ltm_ref and ref_p and active_prods:
        top_sum = sum((p.get("values", {}).get(ref_p) or 0.0) for p in active_prods)
        concepts = {str(p.get("source_concept", "")) for p in active_prods if p.get("source_concept")}
        if 0 < top_sum < can_ltm_ref * 0.96 and len(concepts) == 1:
            only_conc = next(iter(concepts))
            if any(k in only_conc.lower() for k in ("leaseincome", "premiumsearned")):
                metadata["product_table_scope"] = only_conc

    return metadata


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
    """Cruza ingresos y beneficio operativo por segmento mediante coincidencia canónica exacta."""
    op_by_canon = {}
    for op_item in segment_op_income:
        key = _canon_match_key(op_item.get("name", ""))
        if key and key not in op_by_canon:
            op_by_canon[key] = op_item

    for seg_list in (product_segments, channel_segments, geographic_segments):
        for item in seg_list:
            if item.get("is_subsegment") or item.get("is_country_breakdown") or item.get("is_reconciling") or item.get("is_subtotal"):
                continue
            item_canon = _canon_match_key(item.get("name", ""))
            matching_op = op_by_canon.get(item_canon)
            if not matching_op:
                continue

            item["operating_income"] = dict(matching_op.get("values", {}))
            if matching_op.get("interim_disclosure"):
                item["operating_income_interim"] = matching_op["interim_disclosure"].get("current_ytd")

            seg_vals = item.get("values", {})
            op_margins = {}
            for p, op_val in matching_op.get("values", {}).items():
                rev_val = seg_vals.get(p)
                if rev_val is None or abs(rev_val) < 10.0:
                    continue
                margin = round((op_val / rev_val) * 100.0, 2)
                if abs(margin) > 100.0 and abs(rev_val) < 50.0:
                    continue
                op_margins[p] = margin
            if op_margins:
                item["operating_margin_pct"] = op_margins


def _sanitize_internal_keys(seg_list):
    for item in seg_list:
        for priv in ("_concept_ranks", "_ltm_rank", "_interim_rank"):
            item.pop(priv, None)


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

    print(f"[SEC Extractor] Extracción dinámica de segmentos XBRL para {ticker_str}...")

    clean_fys = list(dict.fromkeys(all_fys or []))
    annual_fys = [p for p in clean_fys if p != "LTM"]
    latest_fy = annual_fys[0] if annual_fys else "FY2025"

    product_segments, channel_segments, geographic_segments, segment_op_income = [], [], [], []
    reseg_meta = {}

    try:
        src_ctx = filing_context or company
        f10k_list = src_ctx.get_filings(form="10-K") or src_ctx.get_filings(form="20-F")
        f10q_list = src_ctx.get_filings(form="10-Q") or src_ctx.get_filings(form="6-K")
        valid_k_filings = [f for f in (f10k_list or []) if not str(getattr(f, "form", "")).upper().endswith("/A")]

        product_segments, channel_segments, geographic_segments, segment_op_income = _scan_10k_segment_filings(
            valid_k_filings, filing_context
        )
        product_segments = _resolve_segment_hierarchies(product_segments, geographic_segments, latest_fy)
        geographic_segments = _deduplicate_segment_list(geographic_segments)
        reseg_meta = _inject_10q_ltm_segments(
            f10k_list,
            f10q_list,
            filing_context,
            product_segments,
            channel_segments,
            geographic_segments,
            segment_op_income,
            latest_fy,
            canonical_rev,
        ) or {}
        _resolve_competing_geo_partitions(geographic_segments, latest_fy, canonical_rev)
    except Exception as e:
        print(f"[SEC Extractor] Aviso escaneando XBRL de segmentos: {e}")

    product_segments, channel_segments, geographic_segments, segment_op_income = _apply_banking_and_cache_fallbacks(
        output_dir, seg_json_path, product_segments, channel_segments, geographic_segments, segment_op_income
    )
    _attach_segment_operating_income(product_segments, channel_segments, geographic_segments, segment_op_income)

    for lst in (product_segments, channel_segments, geographic_segments, segment_op_income):
        _sanitize_internal_keys(lst)

    all_seg_items = product_segments + channel_segments + geographic_segments + segment_op_income
    periods_with_seg_data = {k for item in all_seg_items for k, v in item.get("values", {}).items() if v is not None and v != ""}
    clean_periods = [p for p in clean_fys if p in periods_with_seg_data] if periods_with_seg_data else clean_fys
    if "LTM" in clean_fys and "LTM" in periods_with_seg_data and "LTM" not in clean_periods:
        clean_periods.insert(0, "LTM")

    has_active_geo = any(
        g.get("status") == "active" and not g.get("is_subtotal") and not g.get("is_country_breakdown")
        for g in geographic_segments
    )
    reseg_meta.setdefault("geo_reported", has_active_geo)

    seg_dict = {
        "periods": clean_periods,
        "product_segments": product_segments,
        "channel_segments": channel_segments,
        "geographic_segments": geographic_segments,
        "segment_operating_income": segment_op_income,
        "metadata": reseg_meta,
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
