# -*- coding: utf-8 -*-
"""
Fachada del Módulo de Scoring Fundamental, Contabilidad Forense, Solvencia Crediticia y Retornos sobre el Capital.
Delega a views_scoring_quality y views_scoring_forensics manteniendo compatibilidad total con views.py.
"""
import json

from .view_utils import build_chart_periods, usd_to_m
from .views_scoring_forensics import build_montier_detail, build_sloan_detail, build_solvency_and_distress_context
from .views_scoring_quality import build_quality_scores_context, build_returns_and_peers_context


def _to_m(val):
    """Compatibilidad para conversión de USD crudos a millones ($M)."""
    return usd_to_m(val)


def build_scoring_context(
    ticker,
    scores,
    fs,
    fys,
    statements_fys,
    latest_p,
    canonical,
    archetype,
    is_banking,
    bs_data,
):
    """Construye el contexto completo de calidad, retornos, pares Novy-Marx, forense y solvencia."""
    chart_periods, _ = build_chart_periods(fys, canonical)
    quality_ctx = build_quality_scores_context(scores)
    returns_ctx = build_returns_and_peers_context(
        ticker=ticker,
        scores=scores,
        fs=fs,
        canonical=canonical,
        statements_fys=statements_fys,
        chart_periods=chart_periods,
        archetype=archetype,
    )

    forn_data = scores.get("forensic_accounting_analysis", {}) or {}
    forn_lr = forn_data.get("latest_result", {}) or {}
    sloan_str, sloan_detail = build_sloan_detail(forn_data, forn_lr)
    montier_detail = build_montier_detail(forn_data, forn_lr)
    solvency_ctx = build_solvency_and_distress_context(
        scores=scores,
        canonical=canonical,
        bs_data=bs_data,
        latest_p=latest_p,
        is_banking=is_banking,
    )

    return {
        **quality_ctx,
        "gp_total": returns_ctx["gp_total"],
        "gp_total_val": returns_ctx["gp_total_val"],
        "gp_exc": returns_ctx["gp_exc"],
        "p_label": returns_ctx["p_label"],
        "median_gpa": returns_ctx["median_gpa"],
        "median_gpa_val": returns_ctx["median_gpa_val"],
        "gpa_diff_str": returns_ctx["gpa_diff_str"],
        "gpa_is_higher": returns_ctx["gpa_is_higher"],
        "peers": returns_ctx["peers"],
        "roc_green": returns_ctx["roc_green"],
        "roic_adj": returns_ctx["roic_adj"],
        "wacc_val": returns_ctx["wacc_val"],
        "spread_val": returns_ctx["spread_val"],
        "z_score": returns_ctx["z_score"],
        "rating_synth": returns_ctx["rating_synth"],
        "interest_cov": returns_ctx["interest_cov"],
        "interest_cov_display": returns_ctx["interest_cov_display"],
        "kpis_returns": returns_ctx["kpis_returns"],
        "sloan": sloan_str,
        "montier": montier_detail["score"],
        "montier_score": montier_detail["score"],
        "montier_rating": montier_detail["rating"],
        "montier_badge": montier_detail["badge"],
        "montier_verdict": montier_detail["verdict"],
        "montier_flags": montier_detail["flags"],
        "sloan_detail": sloan_detail,
        "montier_detail": montier_detail,
        **solvency_ctx,
        "roic_trad_series_json": json.dumps(returns_ctx["roic_trad_series"]),
        "roic_adj_series_json": json.dumps(returns_ctx["roic_adj_series"]),
        "wacc_chart_series_json": json.dumps(returns_ctx["wacc_chart_series"]),
        "roc_series_json": json.dumps(returns_ctx["roc_series"]),
        "nm_gpa_series_json": json.dumps(returns_ctx["nm_gpa_series"]),
        "nm_gpa_exc_series_json": json.dumps(returns_ctx["nm_gpa_exc_series"]),
    }
