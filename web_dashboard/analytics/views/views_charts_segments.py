# -*- coding: utf-8 -*-
"""
Submódulo de Desglose de Segmentos de Negocio, Canales y Geografía (ASC 280 / ASC 606).
Incluye conciliación universal al 100%, márgenes operativos por segmento, manejo de
re-segmentaciones intermedias, particiones estatutarias por país, series y donuts.
"""
import json
import re

from ..json_cache import load_json_cached
from .view_utils import logger, usd_to_m

_SEGMENT_PALETTE = [
    "#38bdf8", "#a855f7", "#10b981", "#f59e0b", "#f43f5e",
    "#ec4899", "#6366f1", "#14b8a6", "#84cc16", "#eab308",
]

_GEO_ICONS = [
    (("united states", "u.s", "domestic", "estados unidos"), "🇺🇸"),
    (("brazil", "brasil"), "🇧🇷"),
    (("mexico", "méxico"), "🇲🇽"),
    (("argentina",), "🇦🇷"),
    (("china",), "🇨🇳"),
    (("japan", "japón"), "🇯🇵"),
    (("europe", "europa", "emea", "germany", "france"), "🇪🇺"),
    (("united kingdom", "uk", "reino unido"), "🇬🇧"),
    (("taiwan",), "🇹🇼"),
    (("singapore", "singapur"), "🇸🇬"),
    (("asia", "apac"), "🌏"),
    (("latin america", "latam"), "🌎"),
    (("colombia",), "🇨🇴"),
    (("international", "internacional", "world", "foreign", "resto", "other"), "🌐"),
]


def _canon_key(name_str: str) -> str:
    s = re.sub(r"\s+", " ", str(name_str or "").lower().replace("&", "and")).strip()
    s = re.sub(r'\s*\(\s*"[^"]+"\s*\)\s*$', "", s).strip()
    m_par = re.search(r"\s*\(([^)]{1,14})\)\s*$", s)
    if m_par and not m_par.group(1).strip().startswith(("including", "excluding")):
        s = s[: m_par.start()].strip()
    s = re.sub(r"\s+segment$", "", s).strip()
    return s


def _fmt_seg_val(val):
    if val is None:
        return "-"
    return f"${val:,.0f}M" if abs(val) >= 10000 else f"${val:,.1f}M"


def _calc_seg_yoy(v_curr, curr_period, values_dict: dict, seg_periods: list, is_ltm_equal_latest_fy: bool, first_fy) -> str:
    if v_curr is None or float(v_curr) <= 0 or not curr_period or curr_period not in seg_periods:
        return "-"
    curr_idx = seg_periods.index(curr_period)
    prior_p = None
    for p in seg_periods[curr_idx + 1:]:
        if curr_period == "LTM" and is_ltm_equal_latest_fy and p == first_fy:
            continue
        v_raw = values_dict.get(p)
        if v_raw is not None and float(v_raw) > 0:
            if curr_period == "LTM" and is_ltm_equal_latest_fy and abs(float(v_raw) - float(v_curr)) < 0.01:
                continue
            prior_p = p
            break
    if not prior_p or values_dict.get(prior_p) is None or float(values_dict[prior_p]) <= 0:
        return "-"
    g = ((float(v_curr) - float(values_dict[prior_p])) / float(values_dict[prior_p])) * 100.0
    return f"+{g:.1f}%" if g >= 0 else f"{g:.1f}%"


def _get_geo_icon(name: str) -> str:
    low = str(name).lower()
    for tokens, icon in _GEO_ICONS:
        if any(tok in low for tok in tokens):
            return icon
    return "📍"


def _resolve_segment_periods(segments_raw: dict, fys: list, is_ltm_equal_latest_fy: bool, first_fy) -> list:
    raw_seg_periods = segments_raw.get("periods", fys)
    all_items = (
        segments_raw.get("product_segments", [])
        + segments_raw.get("geographic_segments", [])
        + segments_raw.get("channel_segments", [])
        + segments_raw.get("segment_operating_income", [])
    )
    active_seg_periods = {
        k
        for item in all_items
        for k, v in item.get("values", {}).items()
        if v is not None and v != ""
    }
    fys_set = set(fys) if fys else None
    seg_periods = []
    for p in (raw_seg_periods or []):
        if (fys_set is None or p in fys_set) and p not in seg_periods and (not active_seg_periods or p in active_seg_periods):
            seg_periods.append(p)
    if (
        "LTM" in (raw_seg_periods or [])
        and (fys_set is None or "LTM" in fys_set)
        and "LTM" not in seg_periods
        and "LTM" in active_seg_periods
    ):
        seg_periods.insert(0, "LTM")
    if is_ltm_equal_latest_fy and "LTM" in seg_periods and first_fy in seg_periods:
        seg_periods = [p for p in seg_periods if p != "LTM"]
    return seg_periods


def _get_item_ref_value(item: dict, ref_period, use_interim: bool = False):
    """Retorna el monto numérico de referencia (LTM, FY vigente o interim YTD consistente)."""
    if use_interim:
        interim = item.get("interim_disclosure") or {}
        if interim.get("current_ytd") is not None:
            return float(interim["current_ytd"])
    vals = item.get("values", {}) or {}
    if ref_period and vals.get(ref_period) is not None:
        return float(vals[ref_period])
    return None


def _select_primary_items(items: list, seg_periods: list, exclude_country: bool = False) -> list:
    """Identifica segmentos primarios activos excluyendo subsegmentos, totales y conciliaciones."""
    excluded_words = ("hedging", "reconcil", "intersegment", "elimination")
    excluded_names = {"revenue", "products", "total net sales", "total revenues", "total revenue", "google", "apple"}
    top_period = seg_periods[0] if seg_periods else None

    real = []
    for item in items:
        if item.get("is_subtotal") or item.get("is_subsegment") or item.get("is_reconciling"):
            continue
        if exclude_country and item.get("is_country_breakdown"):
            continue
        low_name = item.get("name", "").lower()
        if any(k in low_name for k in excluded_words) or low_name in excluded_names:
            continue
        if item.get("status") == "discontinued":
            continue
        vals = item.get("values", {}) or {}
        has_period_val = (vals.get("LTM") is not None) or (top_period and vals.get(top_period) is not None)
        has_interim = bool((item.get("interim_disclosure") or {}).get("current_ytd") is not None)
        if has_period_val or has_interim:
            real.append(item)

    if real:
        return real

    # Fallback para archivos JSON legados sin atributo "status" explícito
    has_explicit_status = any("status" in i for i in items)
    if has_explicit_status:
        return []

    return [
        item for item in items
        if not item.get("is_subtotal") and not item.get("is_subsegment") and not item.get("is_reconciling")
        and (not exclude_country or not item.get("is_country_breakdown"))
        and not any(k in item.get("name", "").lower() for k in excluded_words)
        and item.get("name", "").lower() not in excluded_names
    ]


def _build_channel_table(channel_items: list, seg_periods: list, can_ref_m) -> list:
    table_channels = []
    ref_p = "LTM" if "LTM" in seg_periods else (seg_periods[0] if seg_periods else None)
    tot_chan = usd_to_m(can_ref_m) if can_ref_m else 1.0
    primary = [
        item for item in channel_items
        if not item.get("is_subsegment") and not item.get("is_subtotal") and item.get("status") != "discontinued"
    ]
    for item in primary:
        v_ref = item["values"].get(ref_p) if ref_p else None
        mix_pct = (v_ref / tot_chan * 100.0) if (tot_chan and tot_chan > 0 and v_ref is not None) else None
        table_channels.append({
            "name": item["name"],
            "mix_pct": f"{mix_pct:.1f}%" if mix_pct is not None else "-",
            "values": [_fmt_seg_val(item["values"].get(p)) for p in seg_periods],
            "is_total": False,
        })
    if table_channels:
        tot_vals = [
            _fmt_seg_val(s) if (s := sum(item["values"].get(p, 0.0) for item in primary if item["values"].get(p) is not None)) > 0 else "-"
            for p in seg_periods
        ]
        table_channels.append({"name": "(=) Total Neto Consolidado", "mix_pct": "100.0%", "values": tot_vals, "is_total": True})
    return table_channels


def _resolve_segment_op_margin(item: dict, ref_period, seg_op_income_raw: list, use_interim: bool = False):
    """Extrae margen operativo por segmento para el período activo exacto (sin fallbacks obsoletos)."""
    if use_interim:
        op_int = item.get("operating_income_interim")
        rev_int = (item.get("interim_disclosure") or {}).get("current_ytd")
        if op_int is not None and rev_int is not None and abs(float(rev_int)) >= 10.0:
            return round((float(op_int) / float(rev_int)) * 100.0, 1)

    op_m_dict = item.get("operating_margin_pct", {}) or {}
    if ref_period and op_m_dict.get(ref_period) is not None:
        return op_m_dict[ref_period]

    item_canon = _canon_key(item.get("name", ""))
    for op_entry in seg_op_income_raw:
        if _canon_key(op_entry.get("name", "")) != item_canon:
            continue
        if ref_period:
            op_v = (op_entry.get("values", {}) or {}).get(ref_period)
            rev_v = (item.get("values", {}) or {}).get(ref_period)
            if op_v is not None and rev_v is not None and abs(float(rev_v)) >= 10.0:
                return round((float(op_v) / float(rev_v)) * 100.0, 1)
        break
    return None


def _order_hierarchy_items(items: list, is_geo: bool = False, exclude_country_partition: bool = False) -> list:
    if is_geo:
        filtered = [i for i in items if not (exclude_country_partition and i.get("is_country_breakdown"))]
        primary = [i for i in filtered if not i.get("is_subtotal") and not i.get("is_subsegment") and not i.get("is_country_breakdown")]
        subs = [i for i in filtered if i.get("is_subsegment")]
    else:
        bad_names = {"revenue", "total revenue", "total revenues", "total net sales"}
        primary = [i for i in items if not i.get("is_subtotal") and not i.get("is_subsegment") and not i.get("is_reconciling") and i.get("name", "").lower() not in bad_names]
        subs = [i for i in items if i.get("is_subsegment")]

    if primary and subs:
        ordered = []
        for prim in primary:
            ordered.append(prim)
            for sub in subs:
                if sub.get("parent") and sub.get("parent", "").lower() == prim.get("name", "").lower():
                    ordered.append(sub)
        for sub in subs:
            if sub not in ordered:
                if is_geo or (
                    not any(b in (sub.get("parent") or "").lower() for b in ("asc 606", "tipo de ingreso", "revenue"))
                    and not any(b in sub.get("name", "").lower() for b in ("net service", "net product"))
                ):
                    ordered.append(sub)
        return ordered
    if primary:
        return primary
    return [i for i in items if not i.get("is_subtotal") and (is_geo or not i.get("is_reconciling")) and not (exclude_country_partition and i.get("is_country_breakdown"))]


def _build_product_table(
    prod_items,
    real_prod_items,
    seg_periods,
    canonical_rev_m,
    tot_prod_ref,
    seg_op_income_raw,
    is_ltm_equal_latest_fy,
    first_fy,
    corp_kpis,
    use_interim_mix,
    metadata,
):
    ordered = _order_hierarchy_items(prod_items, is_geo=False)
    ref_p = "LTM" if "LTM" in seg_periods else (seg_periods[0] if seg_periods else None)
    table, disc = [], []

    for item in ordered:
        is_sub, is_subseg = bool(item.get("is_subtotal")), bool(item.get("is_subsegment"))
        vals = item.get("values", {}) or {}
        has_interim = bool((item.get("interim_disclosure") or {}).get("current_ytd") is not None)
        is_disc = (item.get("status") == "discontinued") or (not has_interim and vals.get("LTM") is None and all(vals.get(p) is None for p in seg_periods[:3]))

        v_mix_ref = _get_item_ref_value(item, ref_p, use_interim=use_interim_mix)
        mix_pct = (v_mix_ref / tot_prod_ref * 100.0) if (tot_prod_ref > 0 and not is_sub and v_mix_ref is not None and not is_disc) else None

        if is_disc:
            first_non_null_p = next((p for p in seg_periods if vals.get(p) is not None), None)
            yoy_str = _calc_seg_yoy(vals.get(first_non_null_p), first_non_null_p, vals, seg_periods, is_ltm_equal_latest_fy, first_fy) if first_non_null_p else "-"
            op_m_val = _resolve_segment_op_margin(item, first_non_null_p, seg_op_income_raw) if (not is_sub and first_non_null_p) else None
        elif has_interim and (use_interim_mix or vals.get(ref_p) is None):
            iyoy = (item.get("interim_disclosure") or {}).get("yoy_pct")
            yoy_str = (f"+{iyoy:.1f}%" if iyoy >= 0 else f"{iyoy:.1f}%") if iyoy is not None else "-"
            op_m_val = None if is_sub else _resolve_segment_op_margin(item, ref_p, seg_op_income_raw, use_interim=True)
        else:
            curr_p = ref_p if (ref_p and vals.get(ref_p) is not None) else next((p for p in seg_periods if vals.get(p) is not None), None)
            yoy_str = _calc_seg_yoy(vals.get(curr_p), curr_p, vals, seg_periods, is_ltm_equal_latest_fy, first_fy) if curr_p else "-"
            op_m_val = None if is_sub else _resolve_segment_op_margin(item, curr_p, seg_op_income_raw)

        interim_tag = None
        if item.get("is_new_in_latest_10q") and item.get("interim_disclosure"):
            int_d = item["interim_disclosure"]
            interim_tag = f"{int_d.get('period_label', 'YTD')}: {_fmt_seg_val(int_d.get('current_ytd'))}"

        row_dict = {
            "name": ("↳ " + item["name"]) if is_subseg else item["name"],
            "raw_name": item["name"],
            "description": item.get("description", ""),
            "is_subtotal": is_sub,
            "is_subsegment": is_subseg,
            "is_discontinued": is_disc,
            "discontinued_after": item.get("discontinued_after"),
            "ltm_disclosure_status": item.get("ltm_disclosure_status"),
            "interim_tag": interim_tag,
            "indent": is_subseg,
            "is_total": False,
            "mix_pct": f"{mix_pct:.1f}%" if (mix_pct is not None and not is_sub) else "-",
            "mix_pct_num": round(mix_pct, 1) if (mix_pct is not None and not is_sub) else 0.0,
            "yoy_str": yoy_str,
            "op_margin_ltm": f"{float(op_m_val):.1f}%" if op_m_val is not None else "-",
            "op_margin_num": round(float(op_m_val), 1) if op_m_val is not None else None,
            "values": [_fmt_seg_val(vals.get(p)) if vals.get(p) is not None else "-" for p in seg_periods],
        }
        (disc if is_disc else table).append(row_dict)

    active = [i for i in ordered if i.get("status") != "discontinued" and not i.get("is_new_in_latest_10q")]
    has_unrec, res_vals = False, {}
    for p in seg_periods:
        c_m = canonical_rev_m.get(p)
        s_val = sum((i.get("values", {}).get(p) or 0.0) for i in active if not i.get("is_subsegment") and not i.get("is_subtotal"))
        if c_m is not None and s_val != 0.0 and abs(c_m - s_val) > 1.0:
            has_unrec, res_vals[p] = True, round(c_m - s_val, 1)
        else:
            res_vals[p] = None
    if has_unrec:
        if metadata.get("product_resegmented"):
            rec_name = f"Segmentos Discontinuados / Predecesores (ver tabla inferior) + Conciliación"
            rec_desc = "Diferencia histórica previa a la re-segmentación del último 10-Q; su desglose completo figura en la tabla de Segmentos Predecesores."
        elif metadata.get("product_table_scope"):
            scope_lbl = metadata["product_table_scope"]
            rec_name = f"Otros Ingresos No Incluidos en Desglose ({scope_lbl})"
            rec_desc = f"El cuadro ASC 606 de la compañía desagrega específicamente '{scope_lbl}'; este saldo representa el resto de ingresos operativos consolidados."
        else:
            rec_name = "Ajustes de Conciliación y Coberturas (Hedging / ASC 280)"
            rec_desc = "Ajustes contables, eliminaciones intersegmento y coberturas de divisas que concilian la suma de segmentos con los ingresos consolidados."
        res_ref = res_vals.get(ref_p) if not use_interim_mix else None
        res_mix = (res_ref / tot_prod_ref * 100.0) if (tot_prod_ref > 0 and res_ref is not None) else None
        table.append({
            "name": rec_name,
            "raw_name": rec_name,
            "description": rec_desc,
            "is_subtotal": False, "is_subsegment": False, "indent": False, "is_total": False, "is_reconciling": True,
            "mix_pct": f"{res_mix:.1f}%" if res_mix is not None else "-", "mix_pct_num": 0.0, "yoy_str": "-", "op_margin_ltm": "-",
            "values": [_fmt_seg_val(res_vals.get(p)) for p in seg_periods],
        })

    tot_vals = [
        _fmt_seg_val(canonical_rev_m[p] if canonical_rev_m.get(p) is not None else sum(i["values"].get(p) or 0.0 for i in real_prod_items))
        for p in seg_periods
    ]
    tot_om_str = f"{corp_kpis['operating_margin_pct']:.1f}%" if corp_kpis.get("operating_margin_pct") is not None else "-"
    table.append({"name": "(=) Total Neto Consolidado", "description": "", "is_subtotal": True, "is_total": True, "mix_pct": "100.0%", "op_margin_ltm": tot_om_str, "values": tot_vals})
    return table, disc


def _build_geo_table_and_territories(geo_items, real_geo_items, seg_periods, canonical_rev_m, tot_geo_ref, is_ltm_equal_latest_fy, first_fy):
    ordered = _order_hierarchy_items(geo_items, is_geo=True, exclude_country_partition=True)
    ref_p = "LTM" if "LTM" in seg_periods else (seg_periods[0] if seg_periods else None)
    table, disc, active = [], [], []

    for item in ordered:
        is_sub, is_subseg = bool(item.get("is_subtotal")), bool(item.get("is_subsegment"))
        vals = item.get("values", {}) or {}
        is_disc = (item.get("status") == "discontinued") or (vals.get("LTM") is None and all(vals.get(p) is None for p in seg_periods[:3]))
        v_ref = vals.get(ref_p) if ref_p else None
        mix_pct = (v_ref / tot_geo_ref * 100.0) if (tot_geo_ref > 0 and not is_sub and v_ref is not None and not is_disc) else None

        if is_disc:
            first_non_null_p = next((p for p in seg_periods if vals.get(p) is not None), None)
            yoy_str = _calc_seg_yoy(vals.get(first_non_null_p), first_non_null_p, vals, seg_periods, is_ltm_equal_latest_fy, first_fy) if (first_non_null_p and not is_sub) else "-"
        else:
            curr_p = ref_p if (ref_p and vals.get(ref_p) is not None) else next((p for p in seg_periods if vals.get(p) is not None), None)
            yoy_str = _calc_seg_yoy(vals.get(curr_p), curr_p, vals, seg_periods, is_ltm_equal_latest_fy, first_fy) if (curr_p and not is_sub) else "-"

        row_dict = {
            "name": ("↳ " + item["name"]) if is_subseg else item["name"],
            "raw_name": item["name"],
            "description": item.get("description", ""),
            "is_subtotal": is_sub, "is_subsegment": is_subseg, "indent": is_subseg, "is_total": False,
            "ltm_disclosure_status": item.get("ltm_disclosure_status"),
            "mix_pct": f"{mix_pct:.1f}%" if (mix_pct is not None and not is_sub) else "-",
            "yoy_str": yoy_str,
            "op_margin_ltm": "-",
            "values": [_fmt_seg_val(vals.get(p)) if vals.get(p) is not None else "-" for p in seg_periods],
        }
        if is_disc:
            disc.append(row_dict)
        else:
            table.append(row_dict)
            active.append(item)

    has_unrec, res_vals = False, {}
    for p in seg_periods:
        c_m = canonical_rev_m.get(p)
        s_val = sum((i.get("values", {}).get(p) or 0.0) for i in active if not i.get("is_subsegment") and not i.get("is_subtotal"))
        if c_m is not None and s_val != 0.0 and abs(c_m - s_val) > 1.0:
            has_unrec, res_vals[p] = True, round(c_m - s_val, 1)
        else:
            res_vals[p] = None
    if has_unrec:
        res_ref = res_vals.get(ref_p) if ref_p else None
        res_mix = (res_ref / tot_geo_ref * 100.0) if (tot_geo_ref > 0 and res_ref is not None) else None
        table.append({
            "name": "Ajustes no Asignados / Coberturas Corporativas",
            "description": "Partidas corporativas consolidadas, coberturas cambiarias o ingresos no asignados a regiones geográficas individuales.",
            "is_subtotal": False, "is_subsegment": False, "indent": False, "is_total": False,
            "mix_pct": f"{res_mix:.1f}%" if res_mix is not None else "-", "op_margin_ltm": "-",
            "values": [_fmt_seg_val(res_vals.get(p)) for p in seg_periods],
        })

    if table:
        tot_vals = [
            _fmt_seg_val(canonical_rev_m[p] if canonical_rev_m.get(p) is not None else sum(i["values"].get(p) or 0.0 for i in real_geo_items))
            for p in seg_periods
        ]
        table.append({"name": "(=) Total Neto Consolidado", "description": "", "is_subtotal": True, "is_total": True, "mix_pct": "100.0%", "values": tot_vals})

    country_rows = []
    for item in geo_items:
        if not item.get("is_country_breakdown") or item.get("status") == "discontinued":
            continue
        vals = item.get("values", {}) or {}
        v_ref = vals.get(ref_p) if ref_p else None
        mix_pct = (v_ref / tot_geo_ref * 100.0) if (tot_geo_ref > 0 and v_ref is not None) else None
        curr_p = ref_p if (ref_p and vals.get(ref_p) is not None) else next((p for p in seg_periods if vals.get(p) is not None), None)
        country_rows.append({
            "name": item["name"],
            "raw_name": item["name"],
            "mix_pct": f"{mix_pct:.1f}%" if mix_pct is not None else "-",
            "yoy_str": _calc_seg_yoy(vals.get(curr_p), curr_p, vals, seg_periods, is_ltm_equal_latest_fy, first_fy) if curr_p else "-",
            "values": [_fmt_seg_val(vals.get(p)) if vals.get(p) is not None else "-" for p in seg_periods],
        })

    geo_territories = []
    for item in real_geo_items:
        vals = item.get("values", {}) or {}
        v_ref = vals.get(ref_p) if ref_p else None
        if v_ref is None:
            curr_p = next((p for p in seg_periods if vals.get(p) is not None), None)
            v_ref = vals.get(curr_p) if curr_p else None
        else:
            curr_p = ref_p
        if v_ref is None or v_ref <= 0:
            continue
        mix_num = (v_ref / tot_geo_ref * 100.0) if tot_geo_ref > 0 else 0.0
        geo_territories.append({
            "name": item["name"], "icon": _get_geo_icon(item["name"]), "ltm_str": _fmt_seg_val(v_ref),
            "mix_pct": f"{mix_num:.1f}%", "mix_num": round(mix_num, 1),
            "yoy_str": _calc_seg_yoy(v_ref, curr_p, vals, seg_periods, is_ltm_equal_latest_fy, first_fy),
            "values": [_fmt_seg_val(vals.get(p)) for p in seg_periods[:5]],
        })
    geo_territories.sort(key=lambda x: x["mix_num"], reverse=True)
    return table, disc, geo_territories, country_rows


def _build_segment_charts(real_prod_items, real_geo_items, seg_periods, is_ltm_equal_latest_fy, first_fy, use_interim_mix=False):
    seg_chart_periods = list(reversed(seg_periods))
    ref_p = "LTM" if "LTM" in seg_periods else (seg_periods[0] if seg_periods else None)

    prod_series_items = [
        i for i in real_prod_items
        if any((i.get("values", {}) or {}).get(p) is not None for p in seg_chart_periods)
    ]
    sorted_prods = sorted(prod_series_items, key=lambda x: (x.get("values", {}).get(ref_p) or 0.0), reverse=True)
    tot_prod_ref = sum((i.get("values", {}).get(ref_p) or 0.0) for i in prod_series_items) or 1.0
    major_prods = [i for i in sorted_prods if ((i.get("values", {}).get(ref_p) or i.get("values", {}).get(first_fy) or 0.0) / tot_prod_ref) >= 0.10]
    if not major_prods and prod_series_items:
        major_prods = sorted_prods[:2]

    cand_start = next((p for p in seg_chart_periods if major_prods and all(i.get("values", {}).get(p) is not None for i in major_prods)), None)
    if cand_start:
        prod_chart_periods = seg_chart_periods[seg_chart_periods.index(cand_start):]
    else:
        prod_valid = [p for p in seg_chart_periods if any(i.get("values", {}).get(p) is not None for i in prod_series_items)]
        prod_chart_periods = seg_chart_periods[seg_chart_periods.index(prod_valid[0]):] if prod_valid else seg_chart_periods

    geo_series_items = [
        i for i in real_geo_items
        if any((i.get("values", {}) or {}).get(p) is not None for p in seg_chart_periods)
    ]
    sorted_geos = sorted(geo_series_items, key=lambda x: (x.get("values", {}).get(ref_p) or 0.0), reverse=True)
    tot_geo_ref = sum((i.get("values", {}).get(ref_p) or 0.0) for i in geo_series_items) or 1.0
    major_geos = [i for i in sorted_geos if ((i.get("values", {}).get(ref_p) or i.get("values", {}).get(first_fy) or 0.0) / tot_geo_ref) >= 0.10]
    if not major_geos and geo_series_items:
        major_geos = sorted_geos[:2]

    geo_cand_start = next((p for p in seg_chart_periods if major_geos and all(i.get("values", {}).get(p) is not None for i in major_geos)), None)
    if geo_cand_start:
        geo_chart_periods = seg_chart_periods[seg_chart_periods.index(geo_cand_start):]
    else:
        geo_valid = [p for p in seg_chart_periods if any(i.get("values", {}).get(p) is not None for i in geo_series_items)]
        geo_chart_periods = seg_chart_periods[seg_chart_periods.index(geo_valid[0]):] if geo_valid else seg_chart_periods

    products_trend = [
        {
            "label": item["name"],
            "data": [round(float(item["values"][p]), 1) if item.get("values", {}).get(p) is not None else None for p in prod_chart_periods],
            "borderColor": _SEGMENT_PALETTE[idx % len(_SEGMENT_PALETTE)], "backgroundColor": "transparent",
            "borderWidth": 2.5, "tension": 0.2, "pointRadius": 4, "pointHoverRadius": 7, "pointHitRadius": 10,
        }
        for idx, item in enumerate(prod_series_items)
    ]
    geos_trend = [
        {
            "label": item["name"],
            "data": [round(float(item["values"][p]), 1) if item.get("values", {}).get(p) is not None else None for p in geo_chart_periods],
            "borderColor": _SEGMENT_PALETTE[idx % len(_SEGMENT_PALETTE)], "backgroundColor": "transparent",
            "borderWidth": 2.5, "tension": 0.2, "pointRadius": 4, "pointHoverRadius": 7,
        }
        for idx, item in enumerate(real_geo_items)
    ]

    def _build_donut(items, use_interim=False):
        labels, data, colors = [], [], []
        for item in items:
            v = _get_item_ref_value(item, ref_p, use_interim=use_interim)
            if v is not None and float(v) > 0:
                labels.append(item["name"])
                data.append(round(float(v), 1))
                colors.append(_SEGMENT_PALETTE[len(labels) % len(_SEGMENT_PALETTE)])
        return labels, data, colors

    d_prod_l, d_prod_d, d_prod_c = _build_donut(real_prod_items, use_interim=use_interim_mix)
    d_geo_l, d_geo_d, d_geo_c = _build_donut(real_geo_items, use_interim=False)
    return {
        "seg_chart_periods": seg_chart_periods, "prod_chart_periods": prod_chart_periods, "geo_chart_periods": geo_chart_periods,
        "products_trend_datasets": products_trend, "geos_trend_datasets": geos_trend,
        "donut_prod_labels": d_prod_l, "donut_prod_data": d_prod_d, "donut_prod_colors": d_prod_c,
        "donut_geo_labels": d_geo_l, "donut_geo_data": d_geo_d, "donut_geo_colors": d_geo_c,
    }


def _build_cutover_notices(metadata: dict, prod_disc: list, geo_disc: list) -> tuple:
    """Construye avisos pedagógicos claros cuando hubo discontinuación o cambio de taxonomía."""
    prod_notice = None
    if metadata.get("product_resegmented") or prod_disc:
        disc_names = ", ".join(r["raw_name"] for r in prod_disc[:6] if not r.get("is_subsegment"))
        cut_fy = metadata.get("superseded_after_fy") or next((r.get("discontinued_after") for r in prod_disc if r.get("discontinued_after")), None)
        interim_lbl = metadata.get("latest_interim_period")
        if metadata.get("product_resegmented") and interim_lbl:
            prod_notice = (
                f"Cambio de taxonomía operativa en {interim_lbl}: los KPIs activos reflejan el último trimestre presentado "
                f"(con historia anual disponible para segmentos continuos; sin serie anual previa para nuevas líneas). "
                f"Las líneas anteriores ({disc_names}) se discontinuaron después de {cut_fy or 'el último cierre anual'} y se conservan en la tabla predecesora inferior."
            )
        elif disc_names:
            prod_notice = f"Segmentos históricos discontinuados/reclasificados en períodos recientes: {disc_names}."

    geo_notice = None
    disc_geo_names = [r["raw_name"] for r in geo_disc if not r.get("is_subsegment")]
    if metadata.get("geo_resegmented") or disc_geo_names:
        geo_notice = (
            f"Desglose geográfico actualizado: {', '.join(disc_geo_names[:5])} dejaron de reportarse por separado y figuran en la tabla histórica discontinuada inferior."
        )
    return prod_notice, geo_notice


def build_segments_context(ticker_dir, fys: list, canonical: dict, corp_kpis: dict, is_ltm_equal_latest_fy: bool, first_fy) -> dict:
    """Construye tablas, KPIs y series de segmentos de negocio y geografías."""
    seg_file = ticker_dir / "segments_data.json"
    segments_raw = {}
    if seg_file.exists():
        try:
            segments_raw = load_json_cached(seg_file)
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Error leyendo segments_data en %s: %s", seg_file, exc)

    metadata = segments_raw.get("metadata", {}) or {}
    seg_periods = _resolve_segment_periods(segments_raw, fys, is_ltm_equal_latest_fy, first_fy)
    ref_p = "LTM" if "LTM" in seg_periods else (seg_periods[0] if seg_periods else None)

    prod_items = segments_raw.get("product_segments", [])
    geo_items = segments_raw.get("geographic_segments", [])
    channel_items = segments_raw.get("channel_segments", [])
    seg_op_income_raw = segments_raw.get("segment_operating_income", [])
    can_rev_dict = canonical.get("revenue", {}) or {}

    real_prod_items = _select_primary_items(prod_items, seg_periods, exclude_country=False)
    real_geo_items = _select_primary_items(geo_items, seg_periods, exclude_country=True)

    # Usar base interim uniforme para mix/donuts si algún segmento activo top-level solo existe en el 10-Q actual
    use_interim_mix = bool(
        real_prod_items
        and any(_get_item_ref_value(i, ref_p, use_interim=False) is None for i in real_prod_items)
        and all(_get_item_ref_value(i, ref_p, use_interim=True) is not None for i in real_prod_items)
    )

    canonical_rev_m = {p: usd_to_m(can_rev_dict.get(p)) for p in seg_periods}
    can_ref_m = canonical_rev_m.get(ref_p) if ref_p else None
    raw_prod_ref = sum((_get_item_ref_value(i, ref_p, use_interim=use_interim_mix) or 0.0) for i in real_prod_items)
    raw_geo_ref = sum((_get_item_ref_value(i, ref_p, use_interim=False) or 0.0) for i in real_geo_items)

    if use_interim_mix and raw_prod_ref > 0:
        tot_prod_ref = raw_prod_ref
        product_basis_label = metadata.get("latest_interim_period") or "Último 10-Q"
    elif metadata.get("product_table_scope") and raw_prod_ref > 0:
        tot_prod_ref = can_ref_m if (can_ref_m is not None and can_ref_m > 0) else raw_prod_ref
        product_basis_label = ref_p or "Anual"
    else:
        tot_prod_ref = can_ref_m if (can_ref_m is not None and can_ref_m > 0) else (raw_prod_ref if raw_prod_ref > 0 else 1.0)
        product_basis_label = "Anual (sin 10-Q)" if metadata.get("product_ltm_status") == "annual_only_not_in_10q" else (ref_p or "LTM")

    tot_geo_ref = can_ref_m if (can_ref_m is not None and can_ref_m > 0) else (raw_geo_ref if raw_geo_ref > 0 else 1.0)

    can_ltm_m_ref = can_rev_dict.get(ref_p) if ref_p else None
    table_channels = _build_channel_table(channel_items, seg_periods, can_ltm_m_ref)
    table_products, table_products_disc = _build_product_table(
        prod_items, real_prod_items, seg_periods, canonical_rev_m, tot_prod_ref, seg_op_income_raw,
        is_ltm_equal_latest_fy, first_fy, corp_kpis, use_interim_mix, metadata,
    )
    table_geos, table_geos_disc, geo_territories, table_geos_countries = _build_geo_table_and_territories(
        geo_items, real_geo_items, seg_periods, canonical_rev_m, tot_geo_ref, is_ltm_equal_latest_fy, first_fy,
    )

    sorted_prods = sorted(real_prod_items, key=lambda x: (_get_item_ref_value(x, ref_p, use_interim=use_interim_mix) or 0.0), reverse=True)
    top_prod = sorted_prods[0] if len(sorted_prods) > 0 else None
    second_prod = sorted_prods[1] if len(sorted_prods) > 1 else None
    top_prod_val = _get_item_ref_value(top_prod, ref_p, use_interim=use_interim_mix) if top_prod else None
    second_prod_val = _get_item_ref_value(second_prod, ref_p, use_interim=use_interim_mix) if second_prod else None

    has_geo_data = len(real_geo_items) > 0
    if has_geo_data:
        sorted_geos = sorted(real_geo_items, key=lambda x: (_get_item_ref_value(x, ref_p) or 0.0), reverse=True)
        top_geo = sorted_geos[0]
        top_geo_val = _get_item_ref_value(top_geo, ref_p) or 0.0
        intl_item = next((i for i in real_geo_items if any(w in i["name"].lower() for w in ("international", "foreign", "resto"))), None)
        intl_val = (_get_item_ref_value(intl_item, ref_p) or 0.0) if intl_item else max(0.0, tot_geo_ref - top_geo_val)
        intl_pct = (intl_val / tot_geo_ref * 100.0) if tot_geo_ref > 0 else 0.0
        geo_kpis = {
            "top_geo_name": top_geo["name"],
            "top_geo_ltm": _fmt_seg_val(top_geo_val),
            "top_geo_mix": f"{(top_geo_val / tot_geo_ref * 100.0):.1f}%" if tot_geo_ref > 0 else "N/D",
            "intl_ltm": _fmt_seg_val(intl_val),
            "intl_pct": f"{intl_pct:.1f}%",
        }
    else:
        geo_kpis = {
            "top_geo_name": "Sin desglose geográfico (ASC 280)",
            "top_geo_ltm": "N/D",
            "top_geo_mix": "N/D",
            "intl_ltm": "N/D",
            "intl_pct": "N/D",
        }

    prod_notice, geo_notice = _build_cutover_notices(metadata, table_products_disc, table_geos_disc)
    charts = _build_segment_charts(real_prod_items, real_geo_items, seg_periods, is_ltm_equal_latest_fy, first_fy, use_interim_mix=use_interim_mix)
    scope_note = (
        f"Alcance contable: desglose ASC 606 reportado específicamente sobre '{metadata['product_table_scope']}'."
        if metadata.get("product_table_scope") else None
    )

    return {
        "seg_periods": seg_periods, "seg_periods_3y": seg_periods[:3], "seg_periods_5y": seg_periods[:5],
        "table_products": table_products, "table_products_discontinued": table_products_disc, "has_discontinued_products": len(table_products_disc) > 0,
        "table_channels": table_channels,
        "table_geos": table_geos, "table_geos_discontinued": table_geos_disc, "has_discontinued_geos": len(table_geos_disc) > 0,
        "table_geos_countries": table_geos_countries, "has_geo_countries": len(table_geos_countries) > 0,
        "geo_territories": geo_territories, "has_geo_territories": len(geo_territories) > 0,
        "geo_reported": has_geo_data,
        "product_basis_label": product_basis_label,
        "product_cutover_notice": prod_notice,
        "geo_cutover_notice": geo_notice,
        "product_table_scope_note": scope_note,
        "kpis_segments": {
            "top_product_name": top_prod["name"] if top_prod else "N/D",
            "top_product_ltm": _fmt_seg_val(top_prod_val) if top_prod_val is not None else "N/D",
            "top_product_mix": f"{(top_prod_val / tot_prod_ref * 100.0):.1f}%" if (top_prod_val is not None and tot_prod_ref > 0) else "N/D",
            "second_product_name": second_prod["name"] if second_prod else "N/D",
            "second_product_ltm": _fmt_seg_val(second_prod_val) if second_prod_val is not None else "N/D",
            "second_product_mix": f"{(second_prod_val / tot_prod_ref * 100.0):.1f}%" if (second_prod_val is not None and tot_prod_ref > 0) else "N/D",
            **geo_kpis,
        },
        **charts,
    }
