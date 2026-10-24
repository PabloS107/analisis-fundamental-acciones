import sys
import json
from pathlib import Path
from django.shortcuts import render, Http404
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST
from django.views.decorators.csrf import csrf_exempt

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "processed"
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
PIPELINE_DIR = PROJECT_ROOT / "pipeline"
for p_dir in (PROJECT_ROOT, PIPELINE_DIR):
    if p_dir.exists() and str(p_dir) not in sys.path:
        sys.path.insert(0, str(p_dir))

from .pipeline_runner import search_companies, launch_pipeline_job, get_job_status
from .views_statements import (
    resolve_canonical_capital_flows,
    resolve_canonical_balance_sheet,
    resolve_canonical_income_statement,
    resolve_canonical_cash_flow,
    _extract_multi_source_val,
    _extract_multi_source_sum,
    build_statements_context,
)
from .views_scoring import build_scoring_context
from .views_charts import build_charts_and_segments_context
from .views_valuation import build_valuation_context


def index(request):
    companies = []

    # Importar MarketDataExtractor para obtener cotizaciones en tiempo real
    mkt_extractor = None
    try:
        from market_data_provider import MarketDataExtractor
        mkt_extractor = MarketDataExtractor
    except Exception:
        pass

    cache_file = DATA_DIR.parent / "cache" / "market_data_cache.json"
    cache_data = {}
    if cache_file.exists():
        try:
            with open(cache_file, "r", encoding="utf-8") as cf:
                cache_data = json.load(cf)
        except Exception:
            pass

    if DATA_DIR.exists():
        for d in DATA_DIR.iterdir():
            if d.is_dir() and (d / "fundamental_scores.json").exists():
                try:
                    with open(d / "fundamental_scores.json", "r", encoding="utf-8") as f:
                        sc = json.load(f)
                    ticker = sc.get("ticker", d.name)
                    name = sc.get("company_name", ticker)

                    # 1. Scores Fundamentales (Piotroski y Mohanram)
                    recent_fy = sc.get("fiscal_years", [None])[0] if sc.get("fiscal_years") else None
                    f_dict = sc.get("piotroski_f_score", {})
                    f_ltm = f_dict.get("LTM", {})
                    f_sc = f_ltm.get("total_score")
                    if f_sc is None and recent_fy:
                        f_sc = f_dict.get(recent_fy, {}).get("total_score")
                    if f_sc is None:
                        f_sc = f_dict.get("latest_result", {}).get("total_score", "-")

                    g_dict = sc.get("mohanram_g_score", {})
                    g_ltm = g_dict.get("LTM", {})
                    g_sc = g_ltm.get("total_score")
                    if g_sc is None and recent_fy:
                        g_sc = g_dict.get(recent_fy, {}).get("total_score")
                    if g_sc is None:
                        g_sc = g_dict.get("latest_result", {}).get("total_score", "-")

                    # 2. Novy-Marx GP/A
                    nm = sc.get("novy_marx_analysis", {}).get("latest_result", {})
                    gpa_val = nm.get("gross_profitability_total")
                    if gpa_val is not None:
                        gpa = (gpa_val * 100.0) if abs(gpa_val) <= 1.5 else gpa_val
                        gpa_str = f"{gpa:.1f}%"
                    else:
                        gpa_str = "N/A"

                    # 3. Solvencia & Rating
                    solv = sc.get("debt_and_solvency_analysis", {}).get("latest_result", {})
                    distress = solv.get("distress_models", {})
                    z_score = distress.get("altman_z_double_prime")
                    if z_score is None:
                        z_score = distress.get("altman_z_score")
                    if z_score is None or str(z_score) == "None":
                        z_score = "N/A"
                    rating = distress.get("synthetic_rating", "AAA")

                    # 4. ROIC Ajustado, WACC y Spread EVA (Diferencia entre ROIC y WACC)
                    wacc_obj = sc.get("wacc_and_spread_analysis", {})
                    wacc_val = wacc_obj.get("wacc")
                    if wacc_val is None:
                        wacc_val = sc.get("roic_wacc_analysis", {}).get("wacc", {}).get("wacc", 0.095)
                    wacc_pct = (wacc_val * 100.0) if wacc_val <= 1.0 else wacc_val

                    roic_val = wacc_obj.get("roic_adjusted")
                    if roic_val is None:
                        roic_val = sc.get("intangible_roic_analysis", {}).get("latest_result", {}).get("adjusted_roic", 0.0)
                    roic_pct = (roic_val * 100.0) if roic_val <= 1.5 else roic_val

                    spread_val = wacc_obj.get("economic_spread_adjusted")
                    if spread_val is None:
                        spread_val = (roic_val - wacc_val) if (roic_val and wacc_val) else 0.0
                    spread_pp = (spread_val * 100.0) if abs(spread_val) <= 1.5 else spread_val

                    moat_badge = wacc_obj.get("moat_badge") or "WIDE MOAT"

                    # 5. Detección de Arquetipo de Industria
                    fs_path = d / "financial_statements.json"
                    fs_data = {}
                    archetype = sc.get("archetype")
                    if fs_path.exists():
                        try:
                            with open(fs_path, "r", encoding="utf-8") as fs_f:
                                fs_data = json.load(fs_f)
                                if not archetype:
                                    archetype = fs_data.get("archetype")
                        except Exception:
                            pass
                    if not archetype:
                        if sc.get("is_financial_institution") or fs_data.get("is_financial"):
                            archetype = "FINANCIAL_BANKING"
                        else:
                            archetype = "STANDARD_CORPORATE"

                    is_banking_card = (archetype == "FINANCIAL_BANKING")

                    kr = fs_data.get("key_ratios", {})
                    roe_raw = kr.get("roe_pct", {}).get("LTM") or kr.get("roe_pct", {}).get(recent_fy) or 0.0
                    roe_val = float(roe_raw) if roe_raw is not None else 0.0

                    nim_raw = kr.get("risk_adj_nim_pct", {}).get("LTM") or kr.get("risk_adj_nim_pct", {}).get(recent_fy) or 0.0
                    nim_val = float(nim_raw) if nim_raw is not None else 0.0

                    # 6. Cotización de Mercado en Tiempo Real
                    price = None
                    if mkt_extractor:
                        try:
                            m_data = mkt_extractor.get_market_data(ticker, bypass_cache=False)
                            price = m_data.get("price")
                        except Exception:
                            pass
                    if not price:
                        price = cache_data.get(ticker, {}).get("price") or wacc_obj.get("market_data", {}).get("price")

                    companies.append({
                        "ticker": ticker,
                        "name": name,
                        "archetype": archetype,
                        "is_banking": is_banking_card,
                        "price": f"${price:.2f}" if price else "-",
                        "price_raw": price,
                        "f_score": f_sc,
                        "g_score": g_sc,
                        "gpa": gpa_str,
                        "roic_adj": f"{roic_pct:.1f}%",
                        "roe": f"{roe_val:.1f}%",
                        "nim": f"{nim_val:.1f}%",
                        "wacc": f"{wacc_pct:.2f}%",
                        "spread": f"+{spread_pp:.1f} pp" if spread_pp > 0 else f"{spread_pp:.1f} pp",
                        "spread_positive": spread_pp >= 0,
                        "z_score": f"{z_score:.2f}" if isinstance(z_score, (int, float)) else str(z_score),
                        "rating": rating,
                        "moat_badge": moat_badge,
                    })
                except Exception:
                    continue

    return render(request, "index.html", {"companies": companies})


@require_GET
def company_search(request):
    """Endpoint JSON para autocompletado y búsqueda de empresas por nombre o ticker."""
    q = request.GET.get("q", "").strip()
    if not q:
        return JsonResponse({"results": []})
    results = search_companies(q, limit=6)
    return JsonResponse({"results": results})


@csrf_exempt
@require_POST
def trigger_pipeline(request):
    """Endpoint para iniciar la incorporación de una nueva empresa de forma 100% automatizada."""
    ticker = request.POST.get("ticker", "").strip().upper()
    if not ticker:
        try:
            body = json.loads(request.body.decode("utf-8"))
            ticker = body.get("ticker", "").strip().upper()
        except Exception:
            pass

    if not ticker:
        return JsonResponse({"success": False, "error": "Ticker no especificado."}, status=400)

    job = launch_pipeline_job(ticker)
    return JsonResponse({"success": True, "job": job})


@require_GET
def pipeline_status(request, ticker):
    """Endpoint JSON para consultar el progreso en vivo de la incorporación."""
    job = get_job_status(ticker)
    return JsonResponse(job)


def company_detail(request, ticker):
    """Orquestador principal de la vista de detalle de una empresa."""
    ticker = ticker.upper()
    ticker_dir = DATA_DIR / ticker
    scores_file = ticker_dir / "fundamental_scores.json"
    fs_file = ticker_dir / "financial_statements.json"

    if not scores_file.exists() or not fs_file.exists():
        raise Http404(f"No se encontraron datos para {ticker}")

    with open(scores_file, "r", encoding="utf-8") as f:
        scores = json.load(f)
    with open(fs_file, "r", encoding="utf-8") as f:
        fs = json.load(f)

    company_name = scores.get("company_name", ticker)
    cik = scores.get("cik", "N/A")
    fys = fs.get("fiscal_years", [])[:10]
    statements_fys = [p for p in fs.get("fiscal_years", [])[:11]]
    latest_p = statements_fys[0] if statements_fys else "LTM"
    canonical = fs.get("canonical_summary", {})
    key_ratios = fs.get("key_ratios", {})

    # 1. Arquetipo de Industria e Ingesta de KPIs Enriquecidos
    archetype = fs.get("archetype") or scores.get("archetype")
    if not archetype:
        if fs.get("is_financial") or scores.get("is_financial_institution"):
            archetype = "FINANCIAL_BANKING"
        else:
            archetype = "STANDARD_CORPORATE"

    is_banking = (archetype == "FINANCIAL_BANKING")
    is_platform = (archetype == "PLATFORM_ECOSYSTEM")
    is_corporate = (archetype == "STANDARD_CORPORATE")
    is_reit = (archetype == "REAL_ESTATE_REIT")
    is_insurance = (archetype == "INSURANCE")
    is_financial = bool(fs.get("is_financial") or scores.get("is_financial_institution") or is_banking or is_insurance)

    pr_file = ticker_dir / "presentation_reconciliation.json"
    if not pr_file.exists():
        fallback_pr = Path("drive_input") / ticker / "processed" / "presentation_reconciliation.json"
        if fallback_pr.exists():
            pr_file = fallback_pr

    pr_data = {}
    if pr_file.exists():
        try:
            with open(pr_file, "r", encoding="utf-8") as pr_f:
                pr_data = json.load(pr_f)
        except Exception:
            pass

    banking_kpis_enriched = pr_data.get("banking_kpis_enriched", {})
    kpis_enriched = pr_data.get("kpis_enriched", {})
    enriched = {**banking_kpis_enriched, **kpis_enriched}

    # 2. Lectura Pre-Calculada o Resolución Canónica de Estados Financieros (Módulo pipeline.canonical_resolvers)
    resolved_pre = fs.get("resolved_canonical_statements", {})
    bs_data = resolved_pre.get("balance_sheet") or resolve_canonical_balance_sheet(fs, statements_fys, archetype=archetype)
    pnl_data = resolved_pre.get("income_statement") or resolve_canonical_income_statement(fs, statements_fys, archetype=archetype)
    cap_flows = resolved_pre.get("capital_flows") or resolve_canonical_capital_flows(fs, statements_fys)
    cf_data = resolved_pre.get("cash_flow") or resolve_canonical_cash_flow(fs, statements_fys, capital_flows=cap_flows, archetype=archetype)

    statements_ctx = build_statements_context(
        fs=fs,
        fys=fys,
        statements_fys=statements_fys,
        latest_p=latest_p,
        canonical=canonical,
        key_ratios=key_ratios,
        archetype=archetype,
        is_banking=is_banking,
        is_insurance=is_insurance,
        is_reit=is_reit,
        is_financial=is_financial,
        enriched=enriched,
        bs_data=bs_data,
        pnl_data=pnl_data,
        cap_flows=cap_flows,
        cf_data=cf_data,
    )

    # 3. Scoring, Solvencia, Forense y Retornos sobre el Capital (Módulo views_scoring.py)
    scoring_ctx = build_scoring_context(
        ticker=ticker,
        scores=scores,
        fs=fs,
        fys=fys,
        statements_fys=statements_fys,
        latest_p=latest_p,
        canonical=canonical,
        archetype=archetype,
        is_banking=is_banking,
        bs_data=bs_data,
    )

    # 4. Gráficos, Asignación de Capital y Segmentos (Módulo views_charts.py)
    charts_ctx = build_charts_and_segments_context(
        ticker_dir=ticker_dir,
        fs=fs,
        fys=fys,
        canonical=canonical,
        key_ratios=key_ratios,
        enriched=enriched,
    )

    # 5. Valuación Intrínseca / Inversa y Mercado en Vivo (Módulo views_valuation.py)
    valuation_ctx = build_valuation_context(
        request=request,
        DATA_DIR=DATA_DIR,
        ticker=ticker,
        scores=scores,
        fs=fs,
        statements_fys=statements_fys,
        canonical=canonical,
        archetype=archetype,
        is_banking=is_banking,
    )

    context = {
        "ticker": ticker,
        "company_name": company_name,
        "cik": cik,
        "fys": fys,
        "archetype": archetype,
        "is_banking": is_banking,
        "is_platform": is_platform,
        "is_corporate": is_corporate,
        "is_reit": is_reit,
        "is_insurance": is_insurance,
        **statements_ctx,
        **scoring_ctx,
        **charts_ctx,
        **valuation_ctx,
    }

    return render(request, "company_detail.html", context)
