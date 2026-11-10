# -*- coding: utf-8 -*-
"""
Submódulo de Scoring de Calidad (Piotroski, Mohanram), Retornos sobre Capital y Pares Novy-Marx.
Cumple estrictamente con Regla 4 (SSOT) y Regla 6 (cero valores ficticios).
"""
from .view_utils import already_m, first_present, logger, ratio_to_pct, safe_float, usd_to_m

_SLATE_BADGE = "bg-slate-100 text-slate-700 border-slate-300"
_EMERALD_BADGE = "bg-emerald-100 text-emerald-800 border-emerald-300"
_SKY_BADGE = "bg-sky-100 text-sky-800 border-sky-300"
_AMBER_BADGE = "bg-amber-100 text-amber-800 border-amber-300"
_ROSE_BADGE = "bg-rose-100 text-rose-800 border-rose-300"


def _score_style(score, high_cut: int, mid_cut: int, low_cut: int):
    """Retorna (badge_class, text_class) semánticos para un puntaje 0..N o None."""
    if not isinstance(score, (int, float)):
        return _SLATE_BADGE, "text-slate-600"
    if score >= high_cut:
        return _EMERALD_BADGE, "text-emerald-700"
    if score >= mid_cut:
        return _SKY_BADGE, "text-sky-700"
    if score >= low_cut:
        return _AMBER_BADGE, "text-amber-700"
    return _ROSE_BADGE, "text-rose-700"


def _build_signals_list(signals_raw, default_thresh: str, include_benchmark: bool = False):
    """Normaliza la lista de señales de Piotroski/Mohanram preservando ceros contables."""
    items = []
    for s in signals_raw:
        comp = s.get("comparison_label") or s.get("condition") or s.get("name")
        thresh = s.get("threshold") or s.get("benchmark") or default_thresh
        val_num = s.get("value")
        fmt_val = s.get("formatted_value") or (f"{val_num:.2f}" if isinstance(val_num, (int, float)) else "")
        entry = {
            "name": s.get("name", ""),
            "category": s.get("category", "General"),
            "passed": bool(s.get("passed", False)),
            "points": first_present(s.get("points"), 1 if s.get("passed") else 0),
            "comparison_label": comp,
            "threshold": thresh,
            "formatted_value": fmt_val,
            "description": s.get("description") or s.get("rationale") or "",
        }
        if include_benchmark:
            entry["benchmark"] = s.get("benchmark") or s.get("threshold") or default_thresh
        items.append(entry)
    return items


def build_quality_scores_context(scores: dict) -> dict:
    """Construye el contexto de Piotroski F-Score y Mohanram G-Score sin falsos defaults."""
    f_obj = scores.get("piotroski_f_score", {}).get("LTM", {}) or {}
    f_score = first_present(f_obj.get("total_score"), f_obj.get("score"))
    f_signals = _build_signals_list(list((f_obj.get("signals") or {}).values()), "Norma Contable")
    f_badge_class, f_text_class = _score_style(f_score, high_cut=8, mid_cut=5, low_cut=3)
    f_summary = f_obj.get("summary_text") or (
        f"Puntaje Piotroski {f_score}/9 evaluado." if f_score is not None else "Datos insuficientes para calcular Piotroski F-Score."
    )
    f_rating = f_obj.get("rating") or ("N/D" if f_score is None else f"F-Score {f_score}/9")

    g_obj = scores.get("mohanram_g_score", {}).get("LTM", {}) or {}
    g_score = first_present(g_obj.get("total_score"), g_obj.get("score"))
    g_signals = _build_signals_list(list((g_obj.get("signals") or {}).values()), "Mediana Sectorial", include_benchmark=True)
    g_badge_class, g_text_class = _score_style(g_score, high_cut=6, mid_cut=4, low_cut=2)
    g_summary = g_obj.get("summary_text") or (
        f"Puntaje Mohanram {g_score}/8 evaluado." if g_score is not None else "Datos insuficientes para calcular Mohanram G-Score."
    )
    g_rating = g_obj.get("rating") or ("N/D" if g_score is None else f"G-Score {g_score}/8")

    return {
        "f_score": f_score,
        "f_signals": f_signals,
        "f_summary": f_summary,
        "f_rating": f_rating,
        "f_badge_class": f_badge_class,
        "f_text_class": f_text_class,
        "g_score": g_score,
        "g_signals": g_signals,
        "g_summary": g_summary,
        "g_rating": g_rating,
        "g_badge_class": g_badge_class,
        "g_text_class": g_text_class,
    }


def _resolve_novy_marx_peers(ticker: str, scores: dict, fs: dict, archetype: str, nm: dict, gp_total_raw, gp_exc_raw):
    """Construye el ranking de pares sectoriales Novy-Marx con fallback dinámico documentado."""
    raw_peers = list(scores.get("novy_marx_analysis", {}).get("peer_ranking", []) or [])
    profile = fs.get("company_profile", {})
    if not raw_peers:
        try:
            from pipeline.financial_scoring_engine import _safe_float, get_sector_benchmarks, load_industry_medians

            raw_sic = (
                scores.get("sic_code")
                or fs.get("sic_code")
                or profile.get("sic_code")
                or (profile.get("header", {}) or {}).get("sic_code")
            )
            med_db = load_industry_medians()
            dyn_bm = get_sector_benchmarks(raw_sic, med_db, ticker=ticker, archetype=archetype)
            for bp in dyn_bm.get("peers_detail", []):
                b_assets = _safe_float(bp.get("total_assets_usd_m"))
                b_rev = _safe_float(bp.get("revenue_usd_m"))
                b_gp = _safe_float(bp.get("gross_profit_usd_m"))
                b_cash = _safe_float(bp.get("cash_usd_m")) or 0.0
                if b_assets and b_assets > 0 and b_gp is not None:
                    b_op_assets = (b_assets - b_cash) if (b_assets > b_cash and (b_assets - b_cash) > 0) else b_assets
                    raw_peers.append({
                        "ticker": bp.get("ticker"),
                        "company_name": bp.get("company_name", bp.get("ticker")),
                        "is_target": str(bp.get("ticker", "")).strip().upper() == ticker.upper(),
                        "period": bp.get("period", "LTM"),
                        "gross_profitability_total": b_gp / b_assets,
                        "gross_profitability_ex_cash": b_gp / b_op_assets,
                        "gross_margin": (b_gp / b_rev) if (b_rev and b_rev > 0) else None,
                        "asset_turnover": (b_rev / b_assets) if (b_rev and b_rev > 0) else None,
                    })
        except Exception as exc:
            logger.warning("No se pudo construir ranking dinámico Novy-Marx para %s: %s", ticker, exc)

    target_in_peers = False
    normalized_peers = []
    for p in raw_peers:
        p_copy = dict(p)
        p_ticker = str(p_copy.get("ticker", "")).strip()
        is_target = p_ticker.upper() == ticker.upper()
        p_copy["is_target"] = is_target
        if is_target:
            target_in_peers = True
            if gp_total_raw is not None:
                p_copy["gross_profitability_total"] = gp_total_raw
            if gp_exc_raw is not None:
                p_copy["gross_profitability_ex_cash"] = gp_exc_raw
            if nm.get("gross_margin") is not None:
                p_copy["gross_margin"] = nm.get("gross_margin")
            if nm.get("asset_turnover_total") is not None:
                p_copy["asset_turnover"] = nm.get("asset_turnover_total")
        normalized_peers.append(p_copy)

    if not target_in_peers and gp_total_raw is not None:
        normalized_peers.append({
            "ticker": ticker.upper(),
            "company_name": scores.get("company_name") or fs.get("company_name") or ticker.upper(),
            "is_target": True,
            "period": scores.get("novy_marx_analysis", {}).get("latest_period", "LTM"),
            "gross_profitability_total": gp_total_raw,
            "gross_profitability_ex_cash": gp_exc_raw,
            "gross_margin": nm.get("gross_margin"),
            "asset_turnover": nm.get("asset_turnover_total"),
        })

    normalized_peers.sort(
        key=lambda x: x.get("gross_profitability_total") if isinstance(x.get("gross_profitability_total"), (int, float)) else -999.0,
        reverse=True,
    )

    peers = []
    for p in normalized_peers:
        gp_tot = p.get("gross_profitability_total")
        gp_exc_p = p.get("gross_profitability_ex_cash")
        gm = p.get("gross_margin")
        turnover = p.get("asset_turnover")
        peers.append({
            **p,
            "gp_tot_pct": f"{gp_tot * 100.0:.2f}%" if isinstance(gp_tot, (int, float)) else "N/D",
            "gp_exc_pct": f"{gp_exc_p * 100.0:.2f}%" if isinstance(gp_exc_p, (int, float)) else "N/D",
            "gm_pct": f"{gm * 100.0:.2f}%" if isinstance(gm, (int, float)) else "N/D",
            "turnover_str": f"{turnover:.2f}x" if isinstance(turnover, (int, float)) else "N/D",
        })
    return peers


def _build_return_series_and_kpis(
    scores: dict,
    canonical: dict,
    statements_fys: list,
    chart_periods: list,
    roic_data: dict,
    roic_adj,
    roc_green,
    gp_total,
    gp_exc,
    median_gpa,
    gpa_diff_str: str,
    gpa_is_higher: bool,
    wacc_val,
    spread_val,
):
    """Construye las series temporales de ROIC/ROC/GP-A y las tarjetas kpis_returns."""
    def _fmt_pct_or_nd(val, decimals=1):
        return f"{val:.{decimals}f}%" if val is not None else "N/D"

    roic_by_p = scores.get("intangible_roic_analysis", {}).get("by_period", {}) or {}
    roic_trad_series = [
        round(float(roic_by_p[p]["roic_trad"]) * 100.0, 2)
        if p in roic_by_p and roic_by_p[p].get("roic_trad") is not None else None
        for p in chart_periods
    ]
    roic_adj_series = [
        round(float(roic_by_p[p]["roic_adj"]) * 100.0, 2)
        if p in roic_by_p and roic_by_p[p].get("roic_adj") is not None else None
        for p in chart_periods
    ]
    wacc_chart_series = [round(wacc_val, 2) if wacc_val is not None else None for _ in chart_periods]

    roc_data = scores.get("greenblatt_roc_analysis", {}) or {}
    roc_ann = roc_data.get("annual_series", {}) or {}
    roc_ltm = roc_data.get("ltm", {}) or {}
    roc_series = [
        round(float(v), 2) if safe_float(v) is not None else None
        for v in (
            first_present(roc_ltm.get("roc_pct"), roc_data.get("latest_result", {}).get("roc_pct")) if p == "LTM"
            else roc_ann.get(p, {}).get("roc_pct")
            for p in chart_periods
        )
    ]

    by_p_nm = scores.get("novy_marx_analysis", {}).get("by_period", {}) or {}
    nm_gpa_series = [
        round(float(by_p_nm[p]["gross_profitability_total"]) * 100.0, 2)
        if p in by_p_nm and by_p_nm[p].get("gross_profitability_total") is not None else None
        for p in chart_periods
    ]
    nm_gpa_exc_series = [
        round(float(by_p_nm[p]["gross_profitability_ex_cash"]) * 100.0, 2)
        if p in by_p_nm and by_p_nm[p].get("gross_profitability_ex_cash") is not None else None
        for p in chart_periods
    ]

    roic_trad_ltm_val = first_present(
        next((x for x in reversed(roic_trad_series) if x is not None), None),
        (float(roic_data["roic_trad"]) * 100.0) if safe_float(roic_data.get("roic_trad")) is not None else None,
    )
    roic_adj_ltm_val = first_present(next((x for x in reversed(roic_adj_series) if x is not None), None), roic_adj)
    roc_ltm_val = first_present(next((x for x in reversed(roc_series) if x is not None), None), roc_green)
    nm_gpa_ltm_val = first_present(next((x for x in reversed(nm_gpa_series) if x is not None), None), gp_total)
    nm_gpa_exc_ltm_val = first_present(next((x for x in reversed(nm_gpa_exc_series) if x is not None), None), gp_exc)

    roic_nopat_m = already_m(first_present(roic_data.get("nopat_adj"), roic_data.get("nopat_trad"), roic_data.get("ebit")))
    roic_ic_m = already_m(
        first_present(roic_data.get("ic_adj"), roic_data.get("ic_adj_end"), roic_data.get("ic_trad_avg"), roic_data.get("ic_trad"))
    )

    recent_annual = statements_fys[0] if statements_fys else None
    nm_gp_m = usd_to_m(first_present(canonical.get("gross_profit", {}).get("LTM"), canonical.get("gross_profit", {}).get(recent_annual) if recent_annual else None))
    nm_assets_m = usd_to_m(first_present(canonical.get("total_assets", {}).get("LTM"), canonical.get("total_assets", {}).get(recent_annual) if recent_annual else None))
    nm_cash_m = usd_to_m(first_present(canonical.get("cash", {}).get("LTM"), canonical.get("cash", {}).get(recent_annual) if recent_annual else None))
    nm_assets_exc_m = round(max(0.0, nm_assets_m - nm_cash_m), 1) if (nm_assets_m is not None and nm_cash_m is not None) else None

    spread_badge_class, spread_text_class = (
        (_SLATE_BADGE, "text-slate-600") if spread_val is None
        else ((_EMERALD_BADGE, "text-emerald-700") if spread_val >= 0 else (_ROSE_BADGE, "text-rose-700"))
    )
    gpa_badge_class, gpa_text_class = (
        (_SLATE_BADGE, "text-slate-600") if (gp_total is None or median_gpa is None)
        else ((_EMERALD_BADGE, "text-emerald-700") if gpa_is_higher else (_ROSE_BADGE, "text-rose-700"))
    )

    kpis_returns = {
        "roic_trad_ltm": _fmt_pct_or_nd(roic_trad_ltm_val, 1),
        "roic_adj_ltm": _fmt_pct_or_nd(roic_adj_ltm_val, 1),
        "roc_greenblatt_ltm": _fmt_pct_or_nd(roc_ltm_val, 1),
        "nm_gpa_ltm": _fmt_pct_or_nd(nm_gpa_ltm_val, 1),
        "nm_gpa_exc_ltm": _fmt_pct_or_nd(nm_gpa_exc_ltm_val, 1),
        "wacc_val": _fmt_pct_or_nd(wacc_val, 2),
        "spread_val": (f"+{spread_val:.1f} pp" if spread_val > 0 else f"{spread_val:.1f} pp") if spread_val is not None else "N/D",
        "median_gpa": _fmt_pct_or_nd(median_gpa, 1),
        "gpa_diff_str": gpa_diff_str,
        "roic_trad_is_higher": (roic_trad_ltm_val >= wacc_val) if (roic_trad_ltm_val is not None and wacc_val is not None) else False,
        "roic_adj_is_higher": (roic_adj_ltm_val >= wacc_val) if (roic_adj_ltm_val is not None and wacc_val is not None) else False,
        "roc_is_higher": (roc_ltm_val >= wacc_val) if (roc_ltm_val is not None and wacc_val is not None) else False,
        "spread_badge_class": spread_badge_class,
        "spread_text_class": spread_text_class,
        "gpa_badge_class": gpa_badge_class,
        "gpa_text_class": gpa_text_class,
        "roic_nopat_m": f"${roic_nopat_m:,.1f}M" if roic_nopat_m is not None else "-",
        "roic_ic_m": f"${roic_ic_m:,.1f}M" if roic_ic_m is not None else "-",
        "nm_gp_m": f"${nm_gp_m:,.1f}M" if nm_gp_m is not None else "-",
        "nm_assets_m": f"${nm_assets_m:,.1f}M" if nm_assets_m is not None else "-",
        "nm_cash_m": f"${nm_cash_m:,.1f}M" if nm_cash_m is not None else "-",
        "nm_assets_exc_m": f"${nm_assets_exc_m:,.1f}M" if nm_assets_exc_m is not None else "-",
    }

    return {
        "kpis_returns": kpis_returns,
        "roic_trad_series": roic_trad_series,
        "roic_adj_series": roic_adj_series,
        "wacc_chart_series": wacc_chart_series,
        "roc_series": roc_series,
        "nm_gpa_series": nm_gpa_series,
        "nm_gpa_exc_series": nm_gpa_exc_series,
    }


def build_returns_and_peers_context(
    ticker: str,
    scores: dict,
    fs: dict,
    canonical: dict,
    statements_fys: list,
    chart_periods: list,
    archetype: str,
) -> dict:
    """Construye métricas de ROIC, WACC, Spread, Novy-Marx, pares y series históricas."""
    is_banking = archetype == "FINANCIAL_BANKING"
    nm = scores.get("novy_marx_analysis", {}).get("latest_result", {}) or {}
    gp_total_raw = nm.get("gross_profitability_total")
    gp_total = ratio_to_pct(gp_total_raw)
    gp_exc_raw = nm.get("gross_profitability_ex_cash")
    gp_exc = ratio_to_pct(gp_exc_raw)
    p_label = nm.get("percentile_label") or "N/D"

    median_gpa_raw = scores.get("benchmarks_used", {}).get("median_gross_profitability")
    median_gpa = (float(median_gpa_raw) * 100.0) if safe_float(median_gpa_raw) is not None else None
    if gp_total is not None and median_gpa is not None:
        gpa_diff = gp_total - median_gpa
        gpa_diff_str = f"+{gpa_diff:.2f} pp" if gpa_diff >= 0 else f"{gpa_diff:.2f} pp"
        gpa_is_higher = gp_total >= median_gpa
    else:
        gpa_diff_str, gpa_is_higher = "N/D", False

    roc_raw_pct = safe_float(scores.get("greenblatt_roc_analysis", {}).get("latest_roc_pct"))
    roc_green = roc_raw_pct if roc_raw_pct is not None else ratio_to_pct(
        scores.get("greenblatt_roc_analysis", {}).get("latest_result", {}).get("roc_greenblatt")
    )

    roic_data = scores.get("intangible_roic_analysis", {}).get("latest_result", {}) or {}
    roic_adj = ratio_to_pct(
        first_present(roic_data.get("adjusted_roic"), scores.get("wacc_and_spread_analysis", {}).get("roic_adjusted"))
    )

    wacc_data = scores.get("wacc_and_spread_analysis", {}) or {}
    wacc_num = safe_float(wacc_data.get("wacc"))
    wacc_val = ((wacc_num * 100.0) if wacc_num <= 1.0 else wacc_num) if wacc_num is not None else safe_float(wacc_data.get("wacc_percentage"))

    spread_raw = first_present(wacc_data.get("economic_spread_adjusted"), wacc_data.get("economic_spread_traditional"))
    spread_val = ratio_to_pct(spread_raw) if spread_raw is not None else safe_float(wacc_data.get("economic_spread_percentage"))

    solv_data = scores.get("debt_and_solvency_analysis", {}).get("latest_result", {}) or {}
    distress = solv_data.get("distress_models", {}) or {}
    z_score = first_present(distress.get("altman_z_double_prime"), distress.get("altman_z_score"), "N/D")
    rating_synth = distress.get("synthetic_rating") or ("Regulada" if is_banking else "N/D")

    debt_srv = solv_data.get("debt_service", {}) or {}
    interest_cov_raw = debt_srv.get("interest_coverage")
    interest_cov_str = debt_srv.get("interest_coverage_str")
    if is_banking:
        interest_cov_display = "N/A (Banca)"
    elif interest_cov_str:
        interest_cov_display = interest_cov_str
    elif isinstance(interest_cov_raw, (int, float)):
        interest_cov_display = f"{interest_cov_raw:.1f}x"
    else:
        interest_cov_display = "N/D"
    interest_cov = interest_cov_raw if interest_cov_raw is not None else interest_cov_display

    peers = _resolve_novy_marx_peers(ticker, scores, fs, archetype, nm, gp_total_raw, gp_exc_raw)
    series_kpis = _build_return_series_and_kpis(
        scores, canonical, statements_fys, chart_periods, roic_data, roic_adj, roc_green,
        gp_total, gp_exc, median_gpa, gpa_diff_str, gpa_is_higher, wacc_val, spread_val,
    )

    return {
        "gp_total": f"{gp_total:.2f}%" if gp_total is not None else "N/D",
        "gp_total_val": gp_total,
        "gp_exc": f"{gp_exc:.2f}%" if gp_exc is not None else "N/D",
        "p_label": p_label,
        "median_gpa": f"{median_gpa:.2f}%" if median_gpa is not None else "N/D",
        "median_gpa_val": median_gpa,
        "gpa_diff_str": gpa_diff_str,
        "gpa_is_higher": gpa_is_higher,
        "peers": peers,
        "roc_green": f"{roc_green:.1f}%" if roc_green is not None else "N/D",
        "roic_adj": f"{roic_adj:.2f}%" if roic_adj is not None else "N/D",
        "wacc_val": f"{wacc_val:.2f}%" if wacc_val is not None else "N/D",
        "spread_val": f"{spread_val:.2f}" if spread_val is not None else "N/D",
        "z_score": f"{z_score:.2f}" if isinstance(z_score, (int, float)) else str(z_score),
        "rating_synth": rating_synth,
        "interest_cov": f"{interest_cov:.1f}x" if isinstance(interest_cov, (int, float)) else str(interest_cov),
        "interest_cov_display": interest_cov_display,
        **series_kpis,
    }
