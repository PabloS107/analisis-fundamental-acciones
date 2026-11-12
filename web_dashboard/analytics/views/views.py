# -*- coding: utf-8 -*-
"""
Vistas principales y endpoints JSON de analytics.
Consume rutas y utilidades SSOT de view_utils delegando cada pestaña a su módulo cohesivo.
"""
import json
import time
from typing import Any, Dict, Optional, Tuple

from django.http import JsonResponse
from django.shortcuts import Http404, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from .view_utils import (
    DATA_DIR,
    DRIVE_INPUT_DIR,
    PIPELINE_DIR,
    PROJECT_ROOT,
    first_present,
    logger,
    ratio_to_pct,
    resolve_company_archetype,
    resolve_market_cache_path,
    safe_float,
)
from ..json_cache import load_json_cached
from ..pipeline_runner import get_job_status, launch_pipeline_job, search_companies
from .views_charts import build_charts_and_segments_context
from .views_scoring import build_scoring_context
from .views_statements import (
    _extract_multi_source_sum,
    _extract_multi_source_val,
    build_statements_context,
    resolve_canonical_balance_sheet,
    resolve_canonical_capital_flows,
    resolve_canonical_cash_flow,
    resolve_canonical_income_statement,
)
from .views_valuation import build_valuation_context
from .views_sec_viewer import cell_evidence_api, sec_report_proxy_api

# Caché en memoria para frescura SEC (Salvaguarda 3: TTL de 15 minutos / 900s)
_FRESHNESS_CACHE: Dict[str, Tuple[float, Dict[str, Any]]] = {}
_FRESHNESS_CACHE_TTL = 900.0


def get_cached_sec_freshness(ticker: str, force_refresh: bool = False) -> Dict[str, Any]:
    t = ticker.strip().upper()
    now = time.time()
    if not force_refresh and t in _FRESHNESS_CACHE:
        cached_time, cached_data = _FRESHNESS_CACHE[t]
        if (now - cached_time) < _FRESHNESS_CACHE_TTL:
            return cached_data

    from pipeline.sec_modules.sec_freshness import check_sec_freshness

    data = check_sec_freshness(t, force_network=True)
    _FRESHNESS_CACHE[t] = (now, data)
    return data


def clear_freshness_cache(ticker: str):
    _FRESHNESS_CACHE.pop(ticker.strip().upper(), None)


def _resolve_latest_score(score_dict: Dict[str, Any], recent_fy: Optional[str]) -> Any:
    """Resuelve el puntaje LTM, último FY o latest_result preservando el 0 entero."""
    if not isinstance(score_dict, dict):
        return "-"
    val = score_dict.get("LTM", {}).get("total_score")
    if val is None and recent_fy:
        val = score_dict.get(recent_fy, {}).get("total_score")
    if val is None:
        val = score_dict.get("latest_result", {}).get("total_score")
    return val if val is not None else "-"


def _load_optional_json(path, timeout: Optional[int] = None) -> Dict[str, Any]:
    """Carga un artefacto JSON opcional registrando cualquier error de lectura."""
    if not path or not path.exists():
        return {}
    try:
        return load_json_cached(path, timeout=timeout) if timeout else load_json_cached(path)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Error leyendo artefacto opcional %s: %s", path, exc)
        return {}


def _build_index_card(company_dir, cache_data: Dict[str, Any], mkt_extractor) -> Dict[str, Any]:
    """Construye la tarjeta de resumen de inicio para un ticker sin valores ficticios."""
    sc = load_json_cached(company_dir / "fundamental_scores.json")
    ticker = sc.get("ticker", company_dir.name)
    name = sc.get("company_name", ticker)
    recent_fy = sc.get("fiscal_years", [None])[0] if sc.get("fiscal_years") else None

    f_sc = _resolve_latest_score(sc.get("piotroski_f_score", {}), recent_fy)
    g_sc = _resolve_latest_score(sc.get("mohanram_g_score", {}), recent_fy)

    nm = sc.get("novy_marx_analysis", {}).get("latest_result", {})
    gpa_pct = ratio_to_pct(nm.get("gross_profitability_total"))
    gpa_str = f"{gpa_pct:.1f}%" if gpa_pct is not None else "N/A"

    fs_data = _load_optional_json(company_dir / "financial_statements.json")
    archetype = resolve_company_archetype(fs_data, sc, ticker=ticker)
    is_banking_card = archetype == "FINANCIAL_BANKING"

    solv = sc.get("debt_and_solvency_analysis", {}).get("latest_result", {})
    distress = solv.get("distress_models", {})
    z_score = first_present(distress.get("altman_z_double_prime"), distress.get("altman_z_score"))
    z_score_str = f"{float(z_score):.2f}" if isinstance(z_score, (int, float)) else (str(z_score) if z_score is not None else "N/A")
    rating = distress.get("synthetic_rating") or ("Regulada" if is_banking_card else "N/D")

    wacc_obj = sc.get("wacc_and_spread_analysis", {})
    wacc_raw = first_present(wacc_obj.get("wacc"), sc.get("roic_wacc_analysis", {}).get("wacc", {}).get("wacc"))
    wacc_num = safe_float(wacc_raw)
    wacc_pct = (wacc_num * 100.0 if wacc_num <= 1.0 else wacc_num) if wacc_num is not None else None

    roic_raw = first_present(
        wacc_obj.get("roic_adjusted"),
        sc.get("intangible_roic_analysis", {}).get("latest_result", {}).get("adjusted_roic"),
    )
    roic_pct = ratio_to_pct(roic_raw)

    spread_raw = safe_float(wacc_obj.get("economic_spread_adjusted"))
    if spread_raw is None and roic_raw is not None and wacc_num is not None:
        roic_dec = float(roic_raw) / 100.0 if abs(float(roic_raw)) > 1.5 else float(roic_raw)
        wacc_dec = wacc_num / 100.0 if wacc_num > 1.0 else wacc_num
        spread_raw = roic_dec - wacc_dec
    spread_pp = ratio_to_pct(spread_raw)

    moat_badge = wacc_obj.get("moat_badge") or "N/D"

    kr = fs_data.get("key_ratios", {})
    roe_val = safe_float(first_present(kr.get("roe_pct", {}).get("LTM"), kr.get("roe_pct", {}).get(recent_fy)))
    nim_val = safe_float(
        first_present(kr.get("risk_adj_nim_pct", {}).get("LTM"), kr.get("risk_adj_nim_pct", {}).get(recent_fy))
    )

    price = None
    if mkt_extractor:
        try:
            price = mkt_extractor.get_market_data(ticker, bypass_cache=False).get("price")
        except Exception as exc:
            logger.debug("MarketDataExtractor falló para %s en index: %s", ticker, exc)
    if price is None:
        price = first_present(cache_data.get(ticker, {}).get("price"), wacc_obj.get("market_data", {}).get("price"))

    return {
        "ticker": ticker,
        "name": name,
        "archetype": archetype,
        "is_banking": is_banking_card,
        "price": f"${float(price):.2f}" if safe_float(price) is not None and float(price) > 0 else "-",
        "price_raw": price,
        "f_score": f_sc,
        "g_score": g_sc,
        "gpa": gpa_str,
        "roic_adj": f"{roic_pct:.1f}%" if roic_pct is not None else "N/D",
        "roe": f"{roe_val:.1f}%" if roe_val is not None else "N/D",
        "nim": f"{nim_val:.1f}%" if nim_val is not None else "N/D",
        "wacc": f"{wacc_pct:.2f}%" if wacc_pct is not None else "N/D",
        "spread": (f"+{spread_pp:.1f} pp" if spread_pp > 0 else f"{spread_pp:.1f} pp") if spread_pp is not None else "N/D",
        "spread_positive": (spread_pp >= 0) if spread_pp is not None else False,
        "z_score": z_score_str,
        "rating": rating,
        "moat_badge": moat_badge,
    }


def index(request):
    """Portada principal con tarjetas comparativas de empresas analizadas."""
    companies = []
    mkt_extractor = None
    try:
        from market_data_provider import MarketDataExtractor

        mkt_extractor = MarketDataExtractor
    except ImportError as exc:
        logger.warning("MarketDataExtractor no disponible para index: %s", exc)

    cache_data = _load_optional_json(resolve_market_cache_path(), timeout=300)

    if DATA_DIR.exists():
        for company_dir in DATA_DIR.iterdir():
            if company_dir.is_dir() and (company_dir / "fundamental_scores.json").exists():
                try:
                    companies.append(_build_index_card(company_dir, cache_data, mkt_extractor))
                except Exception as exc:
                    logger.exception("Error construyendo tarjeta de índice para %s: %s", company_dir.name, exc)

    return render(request, "index.html", {"companies": companies})


@require_GET
def company_search(request):
    """Endpoint JSON para autocompletado y búsqueda de empresas por nombre o ticker."""
    q = request.GET.get("q", "").strip()
    if not q:
        return JsonResponse({"results": []})
    return JsonResponse({"results": search_companies(q, limit=6)})


@csrf_exempt
@require_POST
def trigger_pipeline(request):
    """Endpoint para iniciar la incorporación de una nueva empresa de forma 100% automatizada."""
    ticker = request.POST.get("ticker", "").strip().upper()
    if not ticker:
        try:
            body = json.loads(request.body.decode("utf-8"))
            ticker = body.get("ticker", "").strip().upper()
        except (UnicodeDecodeError, json.JSONDecodeError, AttributeError) as exc:
            logger.debug("Body JSON no válido en trigger_pipeline: %s", exc)

    if not ticker:
        return JsonResponse({"success": False, "error": "Ticker no especificado."}, status=400)

    clear_freshness_cache(ticker)
    job = launch_pipeline_job(ticker)
    return JsonResponse({"success": True, "job": job})


@require_GET
def pipeline_status(request, ticker):
    """Endpoint JSON para consultar el progreso en vivo de la incorporación."""
    return JsonResponse(get_job_status(ticker))


@require_GET
def sec_freshness_view(request, ticker):
    """Endpoint JSON para consultar la frescura de reportes SEC con caché de 15 min."""
    force = request.GET.get("force") in ("1", "true", "True")
    return JsonResponse(get_cached_sec_freshness(ticker, force_refresh=force))


def company_detail(request, ticker):
    """Orquestador principal de la vista de detalle de una empresa."""
    ticker = ticker.upper()
    ticker_dir = DATA_DIR / ticker
    scores_file = ticker_dir / "fundamental_scores.json"
    fs_file = ticker_dir / "financial_statements.json"

    if not scores_file.exists() or not fs_file.exists():
        raise Http404(f"No se encontraron datos para {ticker}")

    try:
        scores = load_json_cached(scores_file)
        fs = load_json_cached(fs_file)
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as exc:
        raise Http404(
            f"Los datos de {ticker} están dañados o incompletos ({exc.__class__.__name__}). "
            f"Reprocese la empresa desde el panel o revise data/processed/{ticker}/."
        )

    company_name = scores.get("company_name", ticker)
    cik = scores.get("cik", "N/A")
    statements_fys = list(fs.get("fiscal_years", [])[:11])
    fys = list(statements_fys)
    latest_p = statements_fys[0] if statements_fys else "LTM"
    canonical = fs.get("canonical_summary", {})
    key_ratios = fs.get("key_ratios", {})

    archetype = resolve_company_archetype(fs, scores, ticker=ticker)
    is_banking = archetype == "FINANCIAL_BANKING"
    is_platform = archetype == "PLATFORM_ECOSYSTEM"
    is_corporate = archetype == "STANDARD_CORPORATE"
    is_reit = archetype == "REAL_ESTATE_REIT"
    is_insurance = archetype == "INSURANCE"
    is_financial = bool(fs.get("is_financial") or scores.get("is_financial_institution") or is_banking or is_insurance)

    pr_file = ticker_dir / "presentation_reconciliation.json"
    if not pr_file.exists():
        fallback_pr = DRIVE_INPUT_DIR / ticker / "processed" / "presentation_reconciliation.json"
        if fallback_pr.exists():
            pr_file = fallback_pr

    pr_data = _load_optional_json(pr_file)
    enriched = {**pr_data.get("banking_kpis_enriched", {}), **pr_data.get("kpis_enriched", {})}

    resolved_pre = fs.get("resolved_canonical_statements", {})
    bs_data = resolved_pre.get("balance_sheet") or resolve_canonical_balance_sheet(fs, statements_fys, archetype=archetype)
    pnl_data = resolved_pre.get("income_statement") or resolve_canonical_income_statement(fs, statements_fys, archetype=archetype)
    cap_flows = resolved_pre.get("capital_flows") or resolve_canonical_capital_flows(fs, statements_fys)
    cf_data = resolved_pre.get("cash_flow") or resolve_canonical_cash_flow(fs, statements_fys, capital_flows=cap_flows, archetype=archetype)

    statements_ctx = build_statements_context(
        fs=fs, fys=fys, statements_fys=statements_fys, latest_p=latest_p, canonical=canonical,
        key_ratios=key_ratios, archetype=archetype, is_banking=is_banking, is_insurance=is_insurance,
        is_reit=is_reit, is_financial=is_financial, enriched=enriched, bs_data=bs_data,
        pnl_data=pnl_data, cap_flows=cap_flows, cf_data=cf_data,
    )
    scoring_ctx = build_scoring_context(
        ticker=ticker, scores=scores, fs=fs, fys=fys, statements_fys=statements_fys,
        latest_p=latest_p, canonical=canonical, archetype=archetype, is_banking=is_banking, bs_data=bs_data,
    )
    charts_ctx = build_charts_and_segments_context(
        ticker_dir=ticker_dir, fs=fs, fys=fys, canonical=canonical, key_ratios=key_ratios, enriched=enriched,
    )
    valuation_ctx = build_valuation_context(
        request=request, DATA_DIR=DATA_DIR, ticker=ticker, scores=scores, fs=fs,
        statements_fys=statements_fys, canonical=canonical, archetype=archetype, is_banking=is_banking,
    )

    from pipeline.sec_modules.sec_freshness import get_local_sec_metadata

    sec_meta = fs.get("sec_metadata") or get_local_sec_metadata(ticker)

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
        "sec_meta": sec_meta,
        **statements_ctx,
        **scoring_ctx,
        **charts_ctx,
        **valuation_ctx,
    }
    return render(request, "company_detail.html", context)
