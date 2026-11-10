# -*- coding: utf-8 -*-
"""
Submódulo de Desglose de Segmentos de Negocio, Canales y Geografía (ASC 280).
Incluye conciliación universal al 100%, márgenes operativos por segmento, series y donuts.
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
    (("asia", "apac"), "🌏"),
    (("taiwan",), "🇹🇼"),
    (("colombia",), "🇨🇴"),
    (("international", "internacional", "world", "foreign", "resto"), "🌐"),
]


def _fmt_seg_val(val):
    if val is None:
        return "-"
    return f"${val:,.0f}M" if abs(val) >= 10000 else f"${val:,.1f}M"


def _calc_seg_yoy(v_curr, values_dict: dict, seg_periods: list, is_ltm_equal_latest_fy: bool, first_fy) -> str:
    if v_curr is None or float(v_curr) <= 0:
        return "-"
    prior_p = None
    for p in seg_periods:
        if p == "LTM" or (is_ltm_equal_latest_fy and p == first_fy):
            continue
        v_raw = values_dict.get(p)
        if v_raw is not None:
            v_cand = float(v_raw)
            if v_cand > 0:
                if is_ltm_equal_latest_fy and abs(v_cand - float(v_curr)) < 0.01:
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
    seg_periods = []
    for p in (raw_seg_periods or []):
        if p not in seg_periods and (not active_seg_periods or p in active_seg_periods):
            seg_periods.append(p)
    if "LTM" in (raw_seg_periods or []) and "LTM" not in seg_periods and (not active_seg_periods or "LTM" in active_seg_periods):
        seg_periods.insert(0, "LTM")
    if is_ltm_equal_latest_fy and "LTM" in seg_periods and first_fy in seg_periods:
        seg_periods = [p for p in seg_periods if p != "LTM"]
    return seg_periods


def _select_primary_items(items: list, seg_periods: list, exclude_country: bool = False) -> list:
    """Identifica segmentos primarios activos excluyendo subsegmentos, totales y conciliaciones."""
    excluded_words = ("hedging", "reconcil", "intersegment", "elimination")
    excluded_names = {"revenue", "products", "total net sales", "total revenues", "total revenue", "google", "apple"}
    real = [
        item for item in items
        if not item.get("is_subtotal") and not item.get("is_subsegment") and not item.get("is_reconciling")
        and (not exclude_country or not item.get("is_country_breakdown"))
        and not any(k in item.get("name", "").lower() for k in excluded_words)
        and item.get("status") != "discontinued"
        and item.get("name", "").lower() not in excluded_names
        and (item.get("values", {}).get("LTM") is not None or (seg_periods and item.get("values", {}).get(seg_periods[0]) is not None))
    ]
    if not real:
        real = [
            item for item in items
            if not item.get("is_subtotal") and not item.get("is_reconciling")
            and (not exclude_country or not item.get("is_country_breakdown"))
            and not any(k in item.get("name", "").lower() for k in excluded_words)
            and item.get("name", "").lower() not in (excluded_names - {"google", "apple"})
        ]
    if not real:
        real = [item for item in items if not item.get("is_subtotal") and not item.get("is_reconciling")]
    return real or items


def _build_channel_table(channel_items: list, seg_periods: list, can_ltm_m_ref) -> list:
    table_channels = []
    tot_chan_ltm = usd_to_m(can_ltm_m_ref) if can_ltm_m_ref else 1.0
    primary = [item for item in channel_items if not item.get("is_subsegment") and not item.get("is_subtotal")]
    for item in primary:
        v_ltm = item["values"].get("LTM")
        mix_pct = (v_ltm / tot_chan_ltm * 100.0) if (tot_chan_ltm and tot_chan_ltm > 0 and v_ltm is not None) else None
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


def _resolve_segment_op_margin(item: dict, seg_periods: list, seg_op_income_raw: list):
    """Extrae margen operativo por segmento (ASC 280) desde atributo directo o tabla de op_income."""
    op_m_dict = item.get("operating_margin_pct", {})
    if op_m_dict:
        if op_m_dict.get("LTM") is not None:
            return op_m_dict["LTM"]
        for p in seg_periods:
            if op_m_dict.get(p) is not None:
                return op_m_dict[p]

    item_norm = re.sub(r"\s+", " ", item["name"].lower().replace("&", "and")).strip()
    for op_entry in seg_op_income_raw:
        op_norm = re.sub(r"\s+", " ", op_entry.get("name", "").lower().replace("&", "and")).strip()
        if op_norm == item_norm or (len(item_norm) > 4 and item_norm in op_norm) or (len(op_norm) > 4 and op_norm in item_norm):
            op_v = op_entry.get("values", {}).get("LTM")
            rev_v = item["values"].get("LTM")
            if op_v is None or rev_v is None:
                for p in seg_periods:
                    if p in op_entry.get("values", {}) and p in item.get("values", {}):
                        op_v, rev_v = op_entry["values"][p], item["values"][p]
                        break
            if op_v is not None and rev_v and float(rev_v) != 0.0:
                return (float(op_v) / float(rev_v)) * 100.0
            break
    return None


def _order_hierarchy_items(items: list, is_geo: bool = False) -> list:
    if is_geo:
        primary = [i for i in items if not i.get("is_subtotal") and not i.get("is_subsegment") and not i.get("is_country_breakdown")]
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
    return [i for i in items if not i.get("is_subtotal") and (is_geo or not i.get("is_reconciling"))]


def _build_product_table(prod_items, real_prod_items, seg_periods, canonical_rev_m, tot_prod_ltm, seg_op_income_raw, is_ltm_equal_latest_fy, first_fy, corp_kpis):
    ordered = _order_hierarchy_items(prod_items, is_geo=False)
    table, disc = [], []
    for item in ordered:
        is_sub, is_subseg = bool(item.get("is_subtotal")), bool(item.get("is_subsegment"))
        is_disc = item.get("status") == "discontinued" or (item["values"].get("LTM") is None and all(item["values"].get(p) is None for p in seg_periods[:3]))
        v_ltm = item["values"].get("LTM")
        mix_pct = (v_ltm / tot_prod_ltm * 100.0) if (tot_prod_ltm > 0 and not is_sub and v_ltm is not None) else None
        v_curr = v_ltm or (item["values"].get(first_fy) if is_ltm_equal_latest_fy else (item["values"].get(seg_periods[0]) if seg_periods else None))
        op_m_val = None if is_sub else _resolve_segment_op_margin(item, seg_periods, seg_op_income_raw)
        row_dict = {
            "name": ("↳ " + item["name"]) if is_subseg else item["name"],
            "raw_name": item["name"],
            "description": item.get("description", ""),
            "is_subtotal": is_sub,
            "is_subsegment": is_subseg,
            "is_discontinued": is_disc,
            "indent": is_subseg,
            "is_total": False,
            "mix_pct": f"{mix_pct:.1f}%" if (mix_pct is not None and not is_sub) else "-",
            "mix_pct_num": round(mix_pct, 1) if (mix_pct is not None and not is_sub) else 0.0,
            "yoy_str": _calc_seg_yoy(v_curr, item["values"], seg_periods, is_ltm_equal_latest_fy, first_fy),
            "op_margin_ltm": f"{float(op_m_val):.1f}%" if op_m_val is not None else "-",
            "op_margin_num": round(float(op_m_val), 1) if op_m_val is not None else None,
            "values": [_fmt_seg_val(item["values"].get(p)) if item["values"].get(p) is not None else "-" for p in seg_periods],
        }
        (disc if is_disc else table).append(row_dict)

    active = [i for i in ordered if i.get("status") != "discontinued" and (i["values"].get("LTM") is not None or any(i["values"].get(p) is not None for p in seg_periods[:3]))]
    has_unrec, res_vals = False, {}
    for p in seg_periods:
        c_m = canonical_rev_m.get(p)
        s_val = sum((i["values"].get(p) or 0.0) for i in active if not i.get("is_subsegment") and not i.get("is_subtotal"))
        if c_m is not None and s_val != 0.0 and abs(c_m - s_val) > 1.0:
            has_unrec, res_vals[p] = True, round(c_m - s_val, 1)
        else:
            res_vals[p] = None
    if has_unrec:
        res_ltm = res_vals.get("LTM")
        res_mix = (res_ltm / tot_prod_ltm * 100.0) if (tot_prod_ltm > 0 and res_ltm is not None) else None
        table.append({
            "name": "Ajustes de Conciliación y Coberturas (Hedging / ASC 280)",
            "raw_name": "Ajustes de Conciliación y Coberturas",
            "description": "Ajustes contables, eliminaciones y coberturas de divisas que concilian la suma de segmentos con los ingresos consolidados.",
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


def _build_geo_table_and_territories(geo_items, real_geo_items, seg_periods, canonical_rev_m, tot_geo_ltm, is_ltm_equal_latest_fy, first_fy):
    ordered = _order_hierarchy_items(geo_items, is_geo=True)
    table, disc, active = [], [], []
    for item in ordered:
        is_sub, is_subseg = bool(item.get("is_subtotal")), bool(item.get("is_subsegment"))
        is_disc = item.get("status") == "discontinued" or (item["values"].get("LTM") is None and all(item["values"].get(p) is None for p in seg_periods[:3]))
        v_ltm = item["values"].get("LTM") or (item["values"].get(first_fy) if is_ltm_equal_latest_fy else None)
        mix_pct = (v_ltm / tot_geo_ltm * 100.0) if (tot_geo_ltm > 0 and not is_sub and v_ltm is not None) else None
        row_dict = {
            "name": ("↳ " + item["name"]) if is_subseg else item["name"],
            "raw_name": item["name"],
            "description": item.get("description", ""),
            "is_subtotal": is_sub, "is_subsegment": is_subseg, "indent": is_subseg, "is_total": False,
            "mix_pct": f"{mix_pct:.1f}%" if (mix_pct is not None and not is_sub) else "-",
            "yoy_str": _calc_seg_yoy(v_ltm, item["values"], seg_periods, is_ltm_equal_latest_fy, first_fy) if not is_sub else "-",
            "op_margin_ltm": "-",
            "values": [_fmt_seg_val(item["values"].get(p)) if item["values"].get(p) is not None else "-" for p in seg_periods],
        }
        if is_disc:
            disc.append(row_dict)
        else:
            table.append(row_dict)
            active.append(item)

    has_unrec, res_vals = False, {}
    for p in seg_periods:
        c_m = canonical_rev_m.get(p)
        s_val = sum((i["values"].get(p) or 0.0) for i in active if not i.get("is_subsegment") and not i.get("is_subtotal"))
        if c_m is not None and s_val != 0.0 and abs(c_m - s_val) > 1.0:
            has_unrec, res_vals[p] = True, round(c_m - s_val, 1)
        else:
            res_vals[p] = None
    if has_unrec:
        res_ltm = res_vals.get("LTM")
        res_mix = (res_ltm / tot_geo_ltm * 100.0) if (tot_geo_ltm > 0 and res_ltm is not None) else None
        table.append({
            "name": "Ajustes no Asignados / Coberturas Corporativas",
            "description": "Partidas corporativas consolidadas, coberturas cambiarias o ingresos no asignados a regiones geográficas individuales.",
            "is_subtotal": False, "is_subsegment": False, "indent": False, "is_total": False,
            "mix_pct": f"{res_mix:.1f}%" if res_mix is not None else "-", "op_margin_ltm": "-",
            "values": [_fmt_seg_val(res_vals.get(p)) for p in seg_periods],
        })

    tot_vals = [
        _fmt_seg_val(canonical_rev_m[p] if canonical_rev_m.get(p) is not None else sum(i["values"].get(p) or 0.0 for i in real_geo_items))
        for p in seg_periods
    ]
    table.append({"name": "(=) Total Neto Consolidado", "description": "", "is_subtotal": True, "is_total": True, "mix_pct": "100.0%", "values": tot_vals})

    geo_territories = []
    for item in real_geo_items:
        v_ltm = item["values"].get("LTM") or (item["values"].get(first_fy) if is_ltm_equal_latest_fy else None)
        if v_ltm is None or v_ltm <= 0:
            continue
        mix_num = (v_ltm / tot_geo_ltm * 100.0) if tot_geo_ltm > 0 else 0.0
        geo_territories.append({
            "name": item["name"], "icon": _get_geo_icon(item["name"]), "ltm_str": _fmt_seg_val(v_ltm),
            "mix_pct": f"{mix_num:.1f}%", "mix_num": round(mix_num, 1),
            "yoy_str": _calc_seg_yoy(v_ltm, item["values"], seg_periods, is_ltm_equal_latest_fy, first_fy),
            "values": [_fmt_seg_val(item["values"].get(p)) for p in seg_periods[:5]],
        })
    geo_territories.sort(key=lambda x: x["mix_num"], reverse=True)
    return table, disc, geo_territories


def _build_segment_charts(real_prod_items, real_geo_items, seg_periods, is_ltm_equal_latest_fy, first_fy):
    seg_chart_periods = list(reversed(seg_periods))
    sorted_prods = sorted(real_prod_items, key=lambda x: x["values"].get("LTM") or 0.0, reverse=True)
    tot_prod_ltm = sum(i["values"].get("LTM") or 0.0 for i in real_prod_items) or 1.0
    major_prods = [i for i in sorted_prods if (i.get("values", {}).get("LTM") or i.get("values", {}).get(first_fy) or 0.0) / tot_prod_ltm >= 0.10]
    if not major_prods and real_prod_items:
        major_prods = sorted_prods[:2]

    cand_start = next((p for p in seg_chart_periods if major_prods and all(i.get("values", {}).get(p) is not None for i in major_prods)), None)
    if cand_start:
        prod_chart_periods = seg_chart_periods[seg_chart_periods.index(cand_start):]
    else:
        prod_valid = [p for p in seg_chart_periods if any(i.get("values", {}).get(p) is not None for i in real_prod_items)]
        prod_chart_periods = seg_chart_periods[seg_chart_periods.index(prod_valid[0]):] if prod_valid else seg_chart_periods

    geo_valid = [p for p in seg_chart_periods if any(i.get("values", {}).get(p) is not None for i in real_geo_items)]
    geo_chart_periods = seg_chart_periods[seg_chart_periods.index(geo_valid[0]):] if geo_valid else seg_chart_periods

    products_trend = [
        {
            "label": item["name"],
            "data": [round(float(item["values"][p]), 1) if item["values"].get(p) is not None else None for p in prod_chart_periods],
            "borderColor": _SEGMENT_PALETTE[idx % len(_SEGMENT_PALETTE)], "backgroundColor": "transparent",
            "borderWidth": 2.5, "tension": 0.2, "pointRadius": 4, "pointHoverRadius": 7, "pointHitRadius": 10,
        }
        for idx, item in enumerate(real_prod_items)
    ]
    geos_trend = [
        {
            "label": item["name"],
            "data": [round(float(item["values"][p]), 1) if item["values"].get(p) is not None else None for p in geo_chart_periods],
            "borderColor": _SEGMENT_PALETTE[idx % len(_SEGMENT_PALETTE)], "backgroundColor": "transparent",
            "borderWidth": 2.5, "tension": 0.2, "pointRadius": 4, "pointHoverRadius": 7,
        }
        for idx, item in enumerate(real_geo_items)
    ]

    def _build_donut(items):
        labels, data, colors = [], [], []
        for item in items:
            v = item["values"].get("LTM") or (item["values"].get(first_fy) if is_ltm_equal_latest_fy else None)
            if v is not None and float(v) > 0:
                labels.append(item["name"])
                data.append(round(float(v), 1))
                colors.append(_SEGMENT_PALETTE[len(labels) % len(_SEGMENT_PALETTE)])
        return labels, data, colors

    d_prod_l, d_prod_d, d_prod_c = _build_donut(real_prod_items)
    d_geo_l, d_geo_d, d_geo_c = _build_donut(real_geo_items)
    return {
        "seg_chart_periods": seg_chart_periods, "prod_chart_periods": prod_chart_periods, "geo_chart_periods": geo_chart_periods,
        "products_trend_datasets": products_trend, "geos_trend_datasets": geos_trend,
        "donut_prod_labels": d_prod_l, "donut_prod_data": d_prod_d, "donut_prod_colors": d_prod_c,
        "donut_geo_labels": d_geo_l, "donut_geo_data": d_geo_d, "donut_geo_colors": d_geo_c,
    }


def build_segments_context(ticker_dir, fys: list, canonical: dict, corp_kpis: dict, is_ltm_equal_latest_fy: bool, first_fy) -> dict:
    """Construye tablas, KPIs y series de segmentos de negocio y geografías."""
    seg_file = ticker_dir / "segments_data.json"
    segments_raw = {}
    if seg_file.exists():
        try:
            segments_raw = load_json_cached(seg_file)
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Error leyendo segments_data en %s: %s", seg_file, exc)

    seg_periods = _resolve_segment_periods(segments_raw, fys, is_ltm_equal_latest_fy, first_fy)
    prod_items = segments_raw.get("product_segments", [])
    geo_items = segments_raw.get("geographic_segments", [])
    channel_items = segments_raw.get("channel_segments", [])
    seg_op_income_raw = segments_raw.get("segment_operating_income", [])
    can_rev_dict = canonical.get("revenue", {})

    real_prod_items = _select_primary_items(prod_items, seg_periods, exclude_country=False)
    real_geo_items = _select_primary_items(geo_items, seg_periods, exclude_country=True)

    canonical_rev_m = {p: usd_to_m(can_rev_dict.get(p)) for p in seg_periods}
    can_ltm_m = canonical_rev_m.get("LTM") or canonical_rev_m.get(seg_periods[0] if seg_periods else None)
    raw_prod_ltm = sum(i["values"].get("LTM") or 0.0 for i in real_prod_items)
    raw_geo_ltm = sum(i["values"].get("LTM") or 0.0 for i in real_geo_items)
    tot_prod_ltm = can_ltm_m if (can_ltm_m is not None and can_ltm_m > 0) else (raw_prod_ltm if raw_prod_ltm > 0 else 1.0)
    tot_geo_ltm = can_ltm_m if (can_ltm_m is not None and can_ltm_m > 0) else (raw_geo_ltm if raw_geo_ltm > 0 else 1.0)

    can_ltm_m_ref = can_rev_dict.get("LTM") or can_rev_dict.get(seg_periods[0] if seg_periods else None)
    table_channels = _build_channel_table(channel_items, seg_periods, can_ltm_m_ref)
    table_products, table_products_disc = _build_product_table(
        prod_items, real_prod_items, seg_periods, canonical_rev_m, tot_prod_ltm, seg_op_income_raw, is_ltm_equal_latest_fy, first_fy, corp_kpis,
    )
    table_geos, table_geos_disc, geo_territories = _build_geo_table_and_territories(
        geo_items, real_geo_items, seg_periods, canonical_rev_m, tot_geo_ltm, is_ltm_equal_latest_fy, first_fy,
    )

    sorted_prods = sorted(real_prod_items, key=lambda x: x["values"].get("LTM") or 0.0, reverse=True)
    top_prod = sorted_prods[0] if len(sorted_prods) > 0 else {"name": "Línea Principal", "values": {}}
    second_prod = sorted_prods[1] if len(sorted_prods) > 1 else {"name": "Línea Secundaria", "values": {}}
    top_prod_ltm = top_prod["values"].get("LTM") or 0.0
    second_prod_ltm = second_prod["values"].get("LTM") or 0.0

    sorted_geos = sorted(real_geo_items, key=lambda x: x["values"].get("LTM") or 0.0, reverse=True)
    top_geo = sorted_geos[0] if len(sorted_geos) > 0 else {"name": "Mercado Principal", "values": {}}
    top_geo_ltm = top_geo["values"].get("LTM") or 0.0
    intl_item = next((i for i in real_geo_items if any(w in i["name"].lower() for w in ("international", "foreign", "resto"))), None)
    intl_ltm = (intl_item["values"].get("LTM") or 0.0) if intl_item else max(0.0, tot_geo_ltm - top_geo_ltm)
    intl_pct = (intl_ltm / tot_geo_ltm * 100.0) if tot_geo_ltm > 0 else 0.0

    charts = _build_segment_charts(real_prod_items, real_geo_items, seg_periods, is_ltm_equal_latest_fy, first_fy)
    return {
        "seg_periods": seg_periods, "seg_periods_3y": seg_periods[:3], "seg_periods_5y": seg_periods[:5],
        "table_products": table_products, "table_products_discontinued": table_products_disc, "has_discontinued_products": len(table_products_disc) > 0,
        "table_channels": table_channels,
        "table_geos": table_geos, "table_geos_discontinued": table_geos_disc, "has_discontinued_geos": len(table_geos_disc) > 0,
        "geo_territories": geo_territories, "has_geo_territories": len(geo_territories) > 0,
        "kpis_segments": {
            "top_product_name": top_prod["name"], "top_product_ltm": _fmt_seg_val(top_prod_ltm),
            "top_product_mix": f"{(top_prod_ltm / tot_prod_ltm * 100.0):.1f}%" if tot_prod_ltm > 0 else "-",
            "second_product_name": second_prod["name"], "second_product_ltm": _fmt_seg_val(second_prod_ltm),
            "second_product_mix": f"{(second_prod_ltm / tot_prod_ltm * 100.0):.1f}%" if tot_prod_ltm > 0 else "-",
            "top_geo_name": top_geo["name"], "top_geo_ltm": _fmt_seg_val(top_geo_ltm),
            "top_geo_mix": f"{(top_geo_ltm / tot_geo_ltm * 100.0):.1f}%" if tot_geo_ltm > 0 else "-",
            "intl_ltm": _fmt_seg_val(intl_ltm), "intl_pct": f"{intl_pct:.1f}%",
        },
        **charts,
    }
