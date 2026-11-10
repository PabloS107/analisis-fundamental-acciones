"""
financial_scoring_engine.py - Orquestador y fachada unificada del Motor Cuantitativo
de Scoring Fundamental (Piotroski, Mohanram, Novy-Marx, ROIC Intangibles, Greenblatt ROC,
WACC/Ke, Forense y Solvencia). Delega el cálculo en pipeline/scoring_modules/.
"""

import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, Optional

try:
    from config_loader import DATA_PROCESSED_DIR
    from json_io import atomic_json_write
    from scoring_modules import (
        CombinedMatrixClassifier,
        DebtSolvencyEngine,
        ForensicAccountingEngine,
        GreenblattROCCalculator,
        IntangibleROICCalculator,
        MohanramScoreCalculator,
        NovyMarxCalculator,
        PiotroskiScoreCalculator,
        WACCCalculator,
        _clean_sic_code,
        _safe_float,
        _to_millions,
        compute_peer_benchmarks,
        extract_period_metrics,
        get_sector_benchmarks,
        load_industry_medians,
        load_peer_benchmarks,
        normalize_archetype,
    )
    from scoring_modules.scoring_utils import _chronological_annual_fys
except ImportError:
    from pipeline.config_loader import DATA_PROCESSED_DIR
    from pipeline.json_io import atomic_json_write
    from pipeline.scoring_modules import (
        CombinedMatrixClassifier,
        DebtSolvencyEngine,
        ForensicAccountingEngine,
        GreenblattROCCalculator,
        IntangibleROICCalculator,
        MohanramScoreCalculator,
        NovyMarxCalculator,
        PiotroskiScoreCalculator,
        WACCCalculator,
        _clean_sic_code,
        _safe_float,
        _to_millions,
        compute_peer_benchmarks,
        extract_period_metrics,
        get_sector_benchmarks,
        load_industry_medians,
        load_peer_benchmarks,
        normalize_archetype,
    )
    from pipeline.scoring_modules.scoring_utils import _chronological_annual_fys

logger = logging.getLogger(__name__)

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception as exc:
        logger.debug("No se pudo reconfigurar stdout a UTF-8: %s", exc)


def _resolve_sic_code(financials: Dict[str, Any], base_folder: Path) -> Optional[str]:
    """Resuelve el código SIC de 4 dígitos desde financial_statements o archivos hermanos."""
    sic_code = _clean_sic_code(financials.get("sic_code"))
    if sic_code:
        return sic_code

    for filename, extractor in (
        ("sec_narrative.json", lambda d: d.get("sic_code")),
        ("company_profile.json", lambda d: d.get("sic_code") or (d.get("header", {}) or {}).get("sic_code")),
    ):
        candidate = base_folder / filename
        if not candidate.exists():
            continue
        try:
            with open(candidate, "r", encoding="utf-8") as fh:
                parsed = json.load(fh)
            sic_code = _clean_sic_code(extractor(parsed))
            if sic_code:
                return sic_code
        except (OSError, json.JSONDecodeError, TypeError) as exc:
            logger.debug("No se pudo leer sic_code desde %s: %s", candidate, exc)
    return None


def _build_latest_diagnosis(scoring_results: Dict[str, Any], recent_fy: str, rec_roic_data: Dict[str, Any]) -> Dict[str, Any]:
    """Construye el bloque compacto latest_diagnosis a partir de todas las series calculadas."""
    latest_f = scoring_results["piotroski_f_score"].get(recent_fy, {})
    latest_g = scoring_results["mohanram_g_score"].get(recent_fy, {})
    latest_matrix = scoring_results["combined_matrix"].get(recent_fy, {})
    novy_series = scoring_results["novy_marx_analysis"]
    latest_nm = novy_series.get("latest_result", {})
    green_series = scoring_results["greenblatt_roc_analysis"]
    wacc_data = scoring_results["wacc_analysis"]
    latest_forensic = scoring_results["forensic_accounting_analysis"].get("latest_result", {})
    latest_solvency = scoring_results["debt_and_solvency_analysis"].get("latest_result", {})

    return {
        "period": recent_fy,
        "f_score": latest_f.get("total_score", 0),
        "f_max": 9,
        "f_rating": latest_f.get("rating", "N/A"),
        "g_score": latest_g.get("total_score", 0),
        "g_max": 8,
        "g_rating": latest_g.get("rating", "N/A"),
        "quadrant": latest_matrix.get("quadrant", "N/A"),
        "badge": latest_matrix.get("badge", "N/A"),
        "color": latest_matrix.get("color", "N/A"),
        "investment_thesis": latest_matrix.get("investment_thesis", ""),
        "novy_marx": {
            "gross_profitability_total": latest_nm.get("gross_profitability_total"),
            "gross_profitability_ex_cash": latest_nm.get("gross_profitability_ex_cash"),
            "cash_drag_pct": latest_nm.get("cash_drag_pct"),
            "gross_margin": latest_nm.get("gross_margin"),
            "asset_turnover_total": latest_nm.get("asset_turnover_total"),
            "quadrant": latest_nm.get("quadrant"),
            "quadrant_badge": latest_nm.get("quadrant_badge"),
            "rating": latest_nm.get("rating"),
            "percentile_label": latest_nm.get("percentile_label"),
            "percentile_explanation": latest_nm.get("percentile_explanation"),
            "adjusted_gp_a": latest_nm.get("adjusted_gp_a"),
            "trend_diagnosis": novy_series.get("trend", {}).get("trend_diagnosis"),
        },
        "greenblatt_roc": {
            "is_applicable": green_series.get("is_applicable", True),
            "roc_avg": green_series.get("latest_roc"),
            "roc_pct": green_series.get("latest_roc_pct"),
            "peer_median_pct": green_series.get("peer_roc_median_pct"),
            "spread_vs_peer_pct": green_series.get("spread_vs_peer_pct"),
            "rating": green_series.get("rating"),
            "roc_rating": green_series.get("roc_rating", green_series.get("rating")),
            "rating_label": green_series.get("rating_label"),
        },
        "roic_wacc": {
            "model_type": wacc_data.get("model_type"),
            "wacc": wacc_data.get("wacc"),
            "ke": wacc_data.get("cost_of_equity_ke"),
            "kd_after_tax": wacc_data.get("cost_of_debt_kd_after_tax"),
            "we": wacc_data.get("weight_equity"),
            "wd": wacc_data.get("weight_debt"),
            "roic_traditional": wacc_data.get("roic_traditional"),
            "roic_adjusted": wacc_data.get("roic_adjusted"),
            "rotce": wacc_data.get("rotce"),
            "roe": wacc_data.get("roe"),
            "economic_spread_adjusted": wacc_data.get("economic_spread_adjusted"),
            "spread": wacc_data.get("spread"),
            "moat_rating": wacc_data.get("moat_rating"),
            "moat_badge": wacc_data.get("moat_badge"),
            "total_intangibles_usd_m": rec_roic_data.get("total_intangible_stock"),
            "market_data_status": wacc_data.get("market_data", {}).get("audit", {}).get("status"),
        },
        "forensic_audit": {
            "sloan_ratio_pct": latest_forensic.get("sloan_accrual", {}).get("sloan_ratio_pct"),
            "sloan_status": latest_forensic.get("sloan_accrual", {}).get("status"),
            "sloan_badge": latest_forensic.get("sloan_accrual", {}).get("badge"),
            "montier_score": latest_forensic.get("montier_c_score", {}).get("total_score"),
            "montier_max": 6,
            "montier_rating": latest_forensic.get("montier_c_score", {}).get("rating"),
            "montier_badge": latest_forensic.get("montier_c_score", {}).get("badge"),
            "ar_sales_spread_pct": latest_forensic.get("divergences", {}).get("ar_sales_spread", {}).get("spread_pct"),
            "inv_cogs_spread_pct": latest_forensic.get("divergences", {}).get("inv_cogs_spread", {}).get("spread_pct"),
            "soft_assets_ratio_pct": latest_forensic.get("divergences", {}).get("soft_assets", {}).get("soft_assets_ratio_pct"),
            "global_verdict": latest_forensic.get("forensic_verdict"),
            "global_badge": latest_forensic.get("global_badge"),
            "global_color": latest_forensic.get("global_color"),
        },
        "solvency_credit": {
            "net_debt_usd_m": latest_solvency.get("cash_flow_leverage", {}).get("net_debt"),
            "net_debt_to_ebitda": latest_solvency.get("cash_flow_leverage", {}).get("net_debt_to_ebitda"),
            "net_debt_to_ebitda_str": latest_solvency.get("cash_flow_leverage", {}).get("net_debt_to_ebitda_str"),
            "net_debt_to_fcf": latest_solvency.get("cash_flow_leverage", {}).get("net_debt_to_fcf"),
            "net_debt_to_fcf_str": latest_solvency.get("cash_flow_leverage", {}).get("net_debt_to_fcf_str"),
            "interest_coverage": latest_solvency.get("debt_service", {}).get("interest_coverage"),
            "interest_coverage_str": latest_solvency.get("debt_service", {}).get("interest_coverage_str"),
            "quick_ratio": latest_solvency.get("liquidity", {}).get("quick_ratio"),
            "cash_ratio": latest_solvency.get("liquidity", {}).get("cash_ratio"),
            "rollover_risk_pct": latest_solvency.get("liquidity", {}).get("rollover_risk_pct"),
            "altman_z_score": latest_solvency.get("distress_models", {}).get("altman_z_double_prime"),
            "altman_zone": latest_solvency.get("distress_models", {}).get("altman_zone"),
            "synthetic_rating": latest_solvency.get("distress_models", {}).get("synthetic_rating"),
            "synthetic_rating_desc": latest_solvency.get("distress_models", {}).get("synthetic_rating_desc"),
            "default_spread_pct": latest_solvency.get("distress_models", {}).get("default_spread_pct"),
            "default_probability": latest_solvency.get("distress_models", {}).get("default_probability"),
            "solvency_verdict": latest_solvency.get("solvency_verdict"),
            "global_badge": latest_solvency.get("global_badge"),
            "global_color": latest_solvency.get("global_color"),
        },
    }


def calculate_fundamental_scores(
    ticker: str,
    financials_json_path: Path,
    out_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Ejecuta el motor integral de scoring fundamental para todos los períodos y LTM."""
    with open(financials_json_path, "r", encoding="utf-8") as f:
        financials = json.load(f)

    cik = financials.get("cik", "N/A")
    company_name = financials.get("company_name", ticker)
    fiscal_years = financials.get("fiscal_years", [])
    archetype = normalize_archetype(financials.get("archetype"), default="STANDARD_CORPORATE")

    sic_code = _resolve_sic_code(financials, Path(financials_json_path).parent)
    benchmarks = get_sector_benchmarks(sic_code, load_industry_medians(), ticker=ticker, archetype=archetype)
    if isinstance(benchmarks, dict):
        benchmarks["archetype"] = archetype

    period_metrics = {fy: extract_period_metrics(financials, fy) for fy in fiscal_years}
    annual_fys_sorted = _chronological_annual_fys(fiscal_years)
    hist_series = [
        {
            "period": y,
            "net_income": period_metrics[y].get("net_income"),
            "revenue": period_metrics[y].get("revenue"),
            "total_assets": period_metrics[y].get("total_assets"),
        }
        for y in annual_fys_sorted
    ]

    scoring_results: Dict[str, Any] = {
        "ticker": ticker.upper(),
        "company_name": company_name,
        "cik": cik,
        "archetype": archetype,
        "sic_code": benchmarks.get("sic_code"),
        "industry_name": benchmarks.get("industry_name"),
        "benchmarks_used": benchmarks,
        "fiscal_years": fiscal_years,
        "piotroski_f_score": {},
        "mohanram_g_score": {},
        "combined_matrix": {},
        "latest_diagnosis": {},
    }

    for fy in fiscal_years:
        curr_m = period_metrics.get(fy, {})
        if fy == "LTM":
            prev_fy = annual_fys_sorted[-1] if len(annual_fys_sorted) >= 1 else None
            prev2_fy = annual_fys_sorted[-2] if len(annual_fys_sorted) >= 2 else None
            sub_hist = hist_series[-5:]
        else:
            idx = annual_fys_sorted.index(fy) if fy in annual_fys_sorted else -1
            prev_fy = annual_fys_sorted[idx - 1] if idx >= 1 else None
            prev2_fy = annual_fys_sorted[idx - 2] if idx >= 2 else None
            sub_hist = hist_series[max(0, idx - 4): idx + 1] if idx >= 0 else hist_series[-5:]

        f_res = PiotroskiScoreCalculator.calculate_year(fy, curr_m, period_metrics.get(prev_fy) if prev_fy else None, period_metrics.get(prev2_fy) if prev2_fy else None)
        g_res = MohanramScoreCalculator.calculate_year(fy, curr_m, period_metrics.get(prev_fy) if prev_fy else None, sub_hist, benchmarks)
        scoring_results["piotroski_f_score"][fy] = f_res
        scoring_results["mohanram_g_score"][fy] = g_res
        scoring_results["combined_matrix"][fy] = CombinedMatrixClassifier.classify(f_res["total_score"], g_res["total_score"])

    scoring_results["novy_marx_analysis"] = NovyMarxCalculator.calculate_series(fiscal_years, period_metrics, benchmarks, ticker=ticker, company_name=company_name)
    roic_analysis = IntangibleROICCalculator.calculate_series(fiscal_years, period_metrics, benchmarks, ticker=ticker)
    scoring_results["intangible_roic_analysis"] = roic_analysis
    scoring_results["greenblatt_roc_analysis"] = GreenblattROCCalculator.calculate_series(fiscal_years, period_metrics, benchmarks, ticker=ticker, archetype=archetype)

    recent_fy = "LTM" if "LTM" in fiscal_years else (fiscal_years[0] if fiscal_years else "N/A")
    rec_roic_data = roic_analysis.get("latest_result", {})
    rec_metrics = period_metrics.get(recent_fy, {})
    wacc_analysis = WACCCalculator.calculate_wacc_and_spread(
        ticker=ticker,
        recent_fy=recent_fy,
        period_data=rec_metrics,
        roic_adjusted=rec_roic_data.get("roic_adj"),
        roic_traditional=rec_roic_data.get("roic_trad"),
        benchmarks=benchmarks,
        diluted_shares_10q=rec_metrics.get("diluted_shares"),
        archetype=archetype,
    )
    scoring_results["wacc_analysis"] = wacc_analysis
    scoring_results["wacc_and_spread_analysis"] = wacc_analysis
    scoring_results["roic_wacc_analysis"] = {"roic": roic_analysis, "wacc": wacc_analysis}
    scoring_results["forensic_accounting_analysis"] = ForensicAccountingEngine.calculate_forensic_series(fiscal_years, period_metrics, benchmarks, ticker=ticker, archetype=archetype)

    mcap_solv = _safe_float(wacc_analysis.get("market_data", {}).get("market_cap_usd_m")) or None
    scoring_results["debt_and_solvency_analysis"] = DebtSolvencyEngine.calculate_solvency_series(
        fiscal_years, period_metrics, benchmarks, ticker=ticker, market_cap=mcap_solv, archetype=archetype
    )
    scoring_results["latest_diagnosis"] = _build_latest_diagnosis(scoring_results, recent_fy, rec_roic_data)
    scoring_results["scoring_results"] = {"archetype": archetype, "ticker": ticker.upper(), "company_name": company_name}

    if out_dir:
        out_path = Path(out_dir) / "fundamental_scores.json"
        atomic_json_write(out_path, scoring_results, indent=2)
        print(f"[Scoring Engine] Resultados cuantitativos guardados exitosamente en: {out_path}")

    return scoring_results


if __name__ == "__main__":
    arg = sys.argv[1].upper() if len(sys.argv) > 1 else "ALL"
    tickers = sorted(d.name for d in DATA_PROCESSED_DIR.iterdir() if d.is_dir() and (d / "financial_statements.json").exists()) if arg == "ALL" else [arg]
    for t in tickers:
        json_path = DATA_PROCESSED_DIR / t / "financial_statements.json"
        if not json_path.exists():
            print(f"Error: No se encontró {json_path}")
            continue
        out = calculate_fundamental_scores(t, json_path, json_path.parent)
        diag = out.get("latest_diagnosis", {})
        nm, fa = diag.get("novy_marx", {}), diag.get("forensic_audit", {})
        print(f"\n{'='*75}\n  DIAGNÓSTICO FUNDAMENTAL CUANTITATIVO: {t.upper()} ({diag.get('period', 'N/A')})\n{'='*75}")
        print(f"  Arquetipo:               {out.get('archetype')}")
        print(f"  Piotroski F-Score:       {diag.get('f_score')}/9 ({diag.get('f_rating')})")
        print(f"  Mohanram G-Score:        {diag.get('g_score')}/8 ({diag.get('g_rating')})")
        print(f"  Matriz F/G:              {diag.get('badge')}")
        gp_tot = nm.get("gross_profitability_total")
        gp_exc = nm.get("gross_profitability_ex_cash")
        cdrag = nm.get("cash_drag_pct")
        print(f"  Novy-Marx GP/A (Total):  {f'{gp_tot*100:.2f}%' if gp_tot is not None else 'N/A'} [{nm.get('percentile_label', 'N/A')}]")
        print(f"  Novy-Marx GP/A (Ex-Caja):{f'{gp_exc*100:.2f}%' if gp_exc is not None else 'N/A'} {f'(Cash Drag: {cdrag*100:+.2f} p.p.)' if cdrag is not None else ''}")
        print(f"  DuPont Estratégico:      {nm.get('quadrant_badge')}")
        print(f"  ROC Greenblatt:          {diag.get('greenblatt_roc', {}).get('roc_pct', 'N/A')}%")
        print(f"  Ratio Sloan Devengos:    {fa.get('sloan_ratio_pct', 'N/A')}% [{fa.get('sloan_badge', 'N/A')}]")
        print(f"  Montier C-Score:         {fa.get('montier_score', 'N/A')}/6 [{fa.get('montier_badge', 'N/A')}]")
        print(f"  Dictamen Forense:        {fa.get('global_badge', 'N/A')}")
        print(f"  Tesis Ejecutiva:         {diag.get('investment_thesis')}\n{'='*75}\n")
