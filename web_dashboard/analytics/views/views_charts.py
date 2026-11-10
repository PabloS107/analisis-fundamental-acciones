# -*- coding: utf-8 -*-
"""
Fachada del Módulo de Series para Gráficos (Chart.js), Asignación de Capital, KPIs Sectoriales y Segmentos.
Delega a views_charts_series, views_charts_sector y views_charts_segments manteniendo retrocompatibilidad total.
"""
import json

from .view_utils import build_chart_periods, usd_to_m
from .views_charts_sector import build_sector_kpis_and_series
from .views_charts_segments import build_segments_context
from .views_charts_series import (
    build_profitability_and_cash_series,
    build_shareholder_and_allocation_context,
)


def _to_m(val):
    """Compatibilidad para conversión de USD crudos a millones ($M)."""
    return usd_to_m(val)


def build_charts_and_segments_context(
    ticker_dir,
    fs,
    fys,
    canonical,
    key_ratios,
    enriched,
):
    """Construye las series temporales de ingresos, flujos, recompras, asignación de capital, segmentos y KPIs."""
    meta = fs.get("sec_metadata", {})
    latest_form = meta.get("latest_periodic_form")
    first_fy = next((p for p in fys if p != "LTM"), None)

    chart_periods, is_ltm_equal_latest_fy = build_chart_periods(
        fys, canonical, drop_duplicate_ltm=True, latest_form=latest_form
    )
    prof_ctx = build_profitability_and_cash_series(canonical, key_ratios, chart_periods)
    share_alloc_ctx = build_shareholder_and_allocation_context(fs, fys, canonical, chart_periods)
    sector_ctx = build_sector_kpis_and_series(canonical, key_ratios, enriched, chart_periods)
    seg_ctx = build_segments_context(
        ticker_dir, fys, canonical, sector_ctx["corp_kpis"], is_ltm_equal_latest_fy, first_fy
    )

    return {
        "chart_periods_json": json.dumps(chart_periods),
        "rev_series_json": json.dumps(prof_ctx["rev_series"]),
        "gp_series_json": json.dumps(prof_ctx["gp_series"]),
        "ebit_series_json": json.dumps(prof_ctx["ebit_series"]),
        "ni_series_json": json.dumps(prof_ctx["ni_series"]),
        "cfo_series_json": json.dumps(prof_ctx["cfo_series"]),
        "capex_series_json": json.dumps(prof_ctx["capex_series"]),
        "fcf_series_json": json.dumps(prof_ctx["fcf_series"]),
        "gm_series_json": json.dumps(prof_ctx["gm_series"]),
        "om_series_json": json.dumps(prof_ctx["om_series"]),
        "nm_series_json": json.dumps(prof_ctx["nm_series"]),
        "fcf_m_series_json": json.dumps(prof_ctx["fcf_m_series"]),
        "cash_conv_rates_json": json.dumps(prof_ctx["cash_conv_rates"]),
        "cash_conv_summary": prof_ctx["cash_conv_summary"],
        "net_buybacks_series_json": json.dumps(share_alloc_ctx["net_buybacks_series"]),
        "net_buyback_colors_json": json.dumps(share_alloc_ctx["net_buyback_colors"]),
        "net_buyback_borders_json": json.dumps(share_alloc_ctx["net_buyback_borders"]),
        "sbc_series_json": json.dumps(share_alloc_ctx["sbc_series"]),
        "shares_yoy_pct_json": json.dumps(share_alloc_ctx["shares_yoy_pct"]),
        "buybacks_series_json": json.dumps(share_alloc_ctx["buybacks_series"]),
        "shares_series_json": json.dumps(share_alloc_ctx["shares_series"]),
        "eps_series_json": json.dumps(share_alloc_ctx["eps_series"]),
        "shares_unit": share_alloc_ctx["shares_unit"],
        "buybacks_unit": share_alloc_ctx["buybacks_unit"],
        "buybacks_summary": share_alloc_ctx["buybacks_summary"],
        "ltm_is_latest_fy": is_ltm_equal_latest_fy,
        "seg_periods": seg_ctx["seg_periods"],
        "seg_periods_3y": seg_ctx["seg_periods_3y"],
        "seg_periods_5y": seg_ctx["seg_periods_5y"],
        "table_products": seg_ctx["table_products"],
        "table_products_discontinued": seg_ctx["table_products_discontinued"],
        "has_discontinued_products": seg_ctx["has_discontinued_products"],
        "table_channels": seg_ctx["table_channels"],
        "table_geos": seg_ctx["table_geos"],
        "table_geos_discontinued": seg_ctx["table_geos_discontinued"],
        "has_discontinued_geos": seg_ctx["has_discontinued_geos"],
        "geo_territories": seg_ctx["geo_territories"],
        "has_geo_territories": seg_ctx["has_geo_territories"],
        "kpis_segments": seg_ctx["kpis_segments"],
        "seg_chart_periods_json": json.dumps(seg_ctx["seg_chart_periods"]),
        "prod_chart_periods_json": json.dumps(seg_ctx["prod_chart_periods"]),
        "geo_chart_periods_json": json.dumps(seg_ctx["geo_chart_periods"]),
        "products_trend_json": json.dumps(seg_ctx["products_trend_datasets"]),
        "geos_trend_json": json.dumps(seg_ctx["geos_trend_datasets"]),
        "donut_prod_labels_json": json.dumps(seg_ctx["donut_prod_labels"]),
        "donut_prod_data_json": json.dumps(seg_ctx["donut_prod_data"]),
        "donut_prod_colors_json": json.dumps(seg_ctx["donut_prod_colors"]),
        "donut_geo_labels_json": json.dumps(seg_ctx["donut_geo_labels"]),
        "donut_geo_data_json": json.dumps(seg_ctx["donut_geo_data"]),
        "donut_geo_colors_json": json.dumps(seg_ctx["donut_geo_colors"]),
        "banking_kpis": sector_ctx["banking_kpis"],
        "platform_kpis": sector_ctx["platform_kpis"],
        "corp_kpis": sector_ctx["corp_kpis"],
        "nii_series_json": json.dumps(sector_ctx["nii_series"]),
        "non_ii_series_json": json.dumps(sector_ctx["non_ii_series"]),
        "deposits_series_json": json.dumps(sector_ctx["deposits_series"]),
        "loans_series_json": json.dumps(sector_ctx["loans_series"]),
        "clp_series_json": json.dumps(sector_ctx["clp_series"]),
        "cost_of_risk_series_json": json.dumps(sector_ctx["cost_of_risk_series"]),
        "donut_dep_labels_json": json.dumps(sector_ctx["donut_dep_labels"]),
        "donut_dep_data_json": json.dumps(sector_ctx["donut_dep_data"]),
        "donut_dep_colors_json": json.dumps(sector_ctx["donut_dep_colors"]),
        "gmv_tpv_labels_json": json.dumps(sector_ctx["gmv_tpv_labels"]),
        "gmv_series_json": json.dumps(sector_ctx["gmv_series"]),
        "tpv_series_json": json.dumps(sector_ctx["tpv_series"]),
        "buyers_mau_labels_json": json.dumps(sector_ctx["buyers_mau_labels"]),
        "buyers_mau_data_json": json.dumps(sector_ctx["buyers_mau_data"]),
        "alloc_kpis": share_alloc_ctx["alloc_kpis"],
        "alloc_unit": share_alloc_ctx["alloc_unit"],
        "alloc_capex_series_json": json.dumps(share_alloc_ctx["alloc_capex_series"]),
        "alloc_buybacks_series_json": json.dumps(share_alloc_ctx["alloc_buybacks_series"]),
        "alloc_dividends_series_json": json.dumps(share_alloc_ctx["alloc_dividends_series"]),
        "alloc_ma_series_json": json.dumps(share_alloc_ctx["alloc_ma_series"]),
        "alloc_debt_series_json": json.dumps(share_alloc_ctx["alloc_debt_series"]),
        "alloc_cfo_series_json": json.dumps(share_alloc_ctx["alloc_cfo_series"]),
        "chart_alloc_data_json": json.dumps(share_alloc_ctx["chart_alloc_data"]),
    }
