# -*- coding: utf-8 -*-
"""
Endpoints API del Visor Interactivo de Procedencia SEC EDGAR (Evidence Drawer & R*.htm Proxy).
Expone:
1. `cell_evidence_api`: fórmula, puente LTM, líneas As-Reported / cajones "Otros" y enlaces SEC.
2. `sec_report_proxy_api`: proxy cacheado SEC `R*.htm` con resaltado quirúrgico y scroll al tag XBRL.
"""
from __future__ import annotations

import json
import re
import time
import xml.etree.ElementTree as ET
from functools import lru_cache
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import requests
from django.http import HttpResponse, JsonResponse
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.http import require_GET

from ..json_cache import load_json_cached
from .view_utils import DATA_DIR, logger

_ACCESSION_RE = re.compile(r'^\d{10}-\d{2}-\d{6}$')
_REPORT_FILE_RE = re.compile(r'^R\d+\.htm$', re.IGNORECASE)
_TICKER_RE = re.compile(r'^[A-Z0-9.-]{1,12}$')
_SEC_PROXY_CACHE: Dict[str, tuple[float, str]] = {}
_SEC_PROXY_TTL = 1800.0


@lru_cache(maxsize=1)
def _sec_user_agent() -> str:
    """Obtiene el User-Agent oficial SEC desde `config/sec_config.json`."""
    try:
        from pipeline.config_loader import DEFAULT_SEC_IDENTITY, load_sec_config
        return str(load_sec_config().get("sec_identity") or DEFAULT_SEC_IDENTITY)
    except (ImportError, OSError, ValueError):
        return "AnalizadorFundamental/1.0 (contact@example.com)"


def _fetch_sec_text_cached(url: str) -> Optional[str]:
    """Descarga texto/HTML/XML desde SEC EDGAR con caché en memoria TTL 30m."""
    now = time.time()
    cached = _SEC_PROXY_CACHE.get(url)
    if cached and (now - cached[0]) < _SEC_PROXY_TTL:
        return cached[1]
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": _sec_user_agent(), "Accept-Encoding": "gzip, deflate"},
            timeout=12,
        )
        if resp.status_code != 200:
            logger.warning("SEC proxy HTTP %s para %s", resp.status_code, url)
            return None
        resp.encoding = resp.apparent_encoding or "utf-8"
        text = resp.text
        if len(_SEC_PROXY_CACHE) > 96:
            oldest = sorted(_SEC_PROXY_CACHE.items(), key=lambda kv: kv[1][0])[:32]
            for k, _ in oldest:
                _SEC_PROXY_CACHE.pop(k, None)
        _SEC_PROXY_CACHE[url] = (now, text)
        return text
    except (requests.RequestException, ValueError) as exc:
        logger.warning("Error consultando SEC EDGAR %s: %s", url, exc)
        return None


def _resolve_report_file_from_summary(filing_base_url: str, stmt_type: str) -> Optional[dict]:
    """Descarga y parsea `FilingSummary.xml` bajo demanda si `statement_reports` no estaba cacheado."""
    xml_text = _fetch_sec_text_cached(f"{filing_base_url.rstrip('/')}/FilingSummary.xml")
    if not xml_text:
        return None
    try:
        from pipeline.sec_modules.sec_provenance import classify_statement_report_name
        root = ET.fromstring(xml_text)
    except (ET.ParseError, ImportError) as exc:
        logger.debug("No se pudo parsear FilingSummary.xml: %s", exc)
        return None

    for rep in root.findall(".//Report"):
        cat = (rep.findtext("MenuCategory") or "").strip().lower()
        if cat and cat != "statements":
            continue
        short_name = (rep.findtext("ShortName") or "").strip()
        if classify_statement_report_name(short_name) != stmt_type:
            continue
        html_file = (rep.findtext("HtmlFileName") or "").strip()
        if html_file and _REPORT_FILE_RE.match(html_file):
            return {"report_file": html_file, "short_name": short_name}
    return None


def _load_company_fs(ticker: str) -> Optional[dict]:
    t = str(ticker or "").strip().upper()
    if not _TICKER_RE.match(t):
        return None
    fs_path = DATA_DIR / t / "financial_statements.json"
    if not fs_path.exists():
        return None
    try:
        return load_json_cached(fs_path)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("No se pudo leer financial_statements.json para %s: %s", t, exc)
        return None


def _resolve_lineage_for_request(fs: dict) -> dict:
    lin = fs.get("resolved_canonical_lineage")
    if isinstance(lin, dict) and lin:
        return lin
    try:
        from pipeline.sec_modules.canonical_lineage import build_resolved_canonical_lineage
        res_can = fs.get("resolved_canonical_statements") or {}
        periods = (fs.get("fiscal_years") or [])[:11]
        if res_can:
            return build_resolved_canonical_lineage(
                fs,
                res_can.get("balance_sheet") or {},
                res_can.get("income_statement") or {},
                res_can.get("cash_flow") or {},
                periods,
            )
    except Exception as exc:
        logger.debug("No se pudo calcular linaje bajo demanda: %s", exc)
    return {}


def _build_filing_links(
    ticker: str,
    fs: dict,
    period: str,
    stmt: str,
    highlight_concept: str,
    highlight_label: str,
) -> List[dict]:
    """Construye los enlaces directos (`proxy_url`, `R*.htm`, `sec.gov/ix`) para el período."""
    idx = fs.get("sec_filings_index") or {}
    pf_map = fs.get("period_filing_map") or {}
    pf = pf_map.get(period) or {}

    targets: List[tuple[str, str]] = []
    if period == "LTM" and isinstance(pf, dict):
        ytd_acc = pf.get("ytd_accession") or pf.get("accession")
        base_acc = pf.get("base_accession")
        if ytd_acc:
            targets.append(("Último reporte (MRQ / YTD)", str(ytd_acc)))
        if base_acc and str(base_acc) != str(ytd_acc):
            targets.append((f"Annual Base ({pf.get('base_fy') or '10-K'})", str(base_acc)))
    elif isinstance(pf, dict) and pf.get("accession"):
        role = "Annual Filing (Comparative)" if pf.get("method") == "COMPARATIVE_IN_ANNUAL_FILING" else f"Native Filing ({period})"
        targets.append((role, str(pf["accession"])))

    if not targets:
        sec_meta = fs.get("sec_metadata") or {}
        if period == "LTM" and sec_meta.get("latest_periodic_accession"):
            targets.append(("Último filing SEC", str(sec_meta["latest_periodic_accession"])))
        elif sec_meta.get("latest_annual_accession"):
            targets.append(("Último 10-K / 20-F", str(sec_meta["latest_annual_accession"])))

    links = []
    q_concept = quote(highlight_concept or "")
    q_lbl = quote(highlight_label or "")
    for role_lbl, acc in targets:
        meta = idx.get(acc) or {}
        cik_digits = re.sub(r'\D', '', str(meta.get("cik_int") or fs.get("cik") or ""))
        cik_int = str(int(cik_digits)) if cik_digits else ""
        acc_nodash = meta.get("acc_nodash") or acc.replace("-", "")
        base_url = meta.get("filing_base_url") or (
            f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_nodash}" if cik_int and acc_nodash else ""
        )
        stmt_rep = (meta.get("statement_reports") or {}).get(stmt) or {}
        rep_file = stmt_rep.get("report_file") or "AUTO"
        proxy_url = (
            f"/api/sec-report-proxy/{ticker}/{acc}/{rep_file}/"
            f"?stmt={quote(stmt)}&concept={q_concept}&raw_label={q_lbl}"
        ) if _ACCESSION_RE.match(acc) else ""
        direct_r = stmt_rep.get("url") or (f"{base_url}/{rep_file}" if base_url and rep_file != "AUTO" else "")
        text_frag = f"{direct_r}#:~:text={quote(highlight_label[:60])}" if (direct_r and highlight_label) else direct_r
        links.append({
            "role": role_lbl,
            "accession": acc,
            "form": meta.get("form") or ("10-Q" if "MRQ" in role_lbl else "10-K"),
            "filing_date": meta.get("filing_date") or "",
            "period_of_report": meta.get("period_of_report") or "",
            "report_file": rep_file,
            "short_name": stmt_rep.get("short_name") or "",
            "proxy_url": proxy_url,
            "text_fragment_url": text_frag,
            "sec_ixbrl_url": meta.get("sec_ixbrl_url") or "",
            "sec_htm_url": meta.get("sec_htm_url") or "",
        })
    return links


@require_GET
def cell_evidence_api(request, ticker: str) -> JsonResponse:
    """Devuelve evidencia cuantitativa, atribución de 'Otros', puente LTM y enlaces SEC para una celda."""
    t = str(ticker or "").strip().upper()
    fs = _load_company_fs(t)
    if fs is None:
        return JsonResponse({"error": f"No existe dataset SEC para {t}."}, status=404)

    stmt = (request.GET.get("stmt") or "income_statement").strip()
    metric = (request.GET.get("metric") or "").strip()
    period = (request.GET.get("period") or "LTM").strip()
    concept = (request.GET.get("concept") or "").strip()
    raw_label = (request.GET.get("raw_label") or "").strip()
    view_mode = (request.GET.get("view") or "std").strip()

    pf_map = fs.get("period_filing_map") or {}
    payload: Dict[str, Any] = {
        "ticker": t,
        "stmt": stmt,
        "metric": metric,
        "period": period,
        "view": view_mode,
        "method": "XBRL_CONCEPT",
        "formula_display": "",
        "value_usd": None,
        "sources": [],
        "components": {},
        "explained_sum_usd": None,
        "residual_unexplained_usd": None,
        "ltm_bridge": None,
    }

    hi_concept, hi_label = concept, raw_label
    if view_mode == "std" and metric:
        lineage = _resolve_lineage_for_request(fs)
        spec = lineage.get(metric) or {}
        p_info = (spec.get("periods") or {}).get(period) or {}
        payload["method"] = spec.get("method") or "CANONICAL_FORMULA"
        payload["formula_display"] = spec.get("formula_display") or f"Métrica estándar `{metric}` del esquema canónico."
        payload["value_usd"] = p_info.get("value_usd")
        payload["sources"] = p_info.get("sources") or []
        payload["components"] = p_info.get("components") or {}
        payload["explained_sum_usd"] = p_info.get("explained_sum_usd")
        payload["residual_unexplained_usd"] = p_info.get("residual_unexplained_usd")
        payload["ltm_bridge"] = p_info.get("ltm_bridge")
        if payload["sources"] and not hi_concept:
            hi_concept = payload["sources"][0].get("concept", "")
            hi_label = payload["sources"][0].get("raw_label", "")
    else:
        rows = (fs.get("as_reported_statements") or {}).get(stmt) or []
        matched = next(
            (r for r in rows if concept and r.get("concept") == concept and (not raw_label or raw_label in (r.get("label"), r.get("raw_label")))),
            None,
        ) or next(
            (r for r in rows if (concept and r.get("concept") == concept) or (raw_label and raw_label in (r.get("label"), r.get("raw_label")))),
            None,
        )
        if matched:
            val = (matched.get("values") or {}).get(period)
            payload["value_usd"] = float(val) if val is not None else None
            payload["method"] = "SEC_EXTENSION_TAG" if matched.get("is_extension_tag") else "SEC_AS_REPORTED"
            payload["formula_display"] = (
                f"Partida oficial extraída de carátula SEC (`{matched.get('concept') or 'Sin tag XBRL'}`)"
                + (f" — Sección: {matched.get('section_path')}" if matched.get("section_path") else "")
            )
            sec_raw_lbl = matched.get("raw_label") or matched.get("label") or ""
            payload["sources"] = [{
                "concept": matched.get("concept", ""),
                "raw_label": sec_raw_lbl,
                "display_label": matched.get("label", ""),
                "spanish_label": matched.get("spanish_label", ""),
                "section_path": matched.get("section_path", ""),
                "is_extension_tag": bool(matched.get("is_extension_tag", False)),
                "val_usd": payload["value_usd"],
            }]
            hi_concept = matched.get("concept") or hi_concept
            hi_label = sec_raw_lbl or hi_label
            if period == "LTM" and isinstance(pf_map.get("LTM"), dict):
                ltm_p = pf_map["LTM"]
                base_fy = ltm_p.get("base_fy")
                payload["ltm_bridge"] = {
                    "mode": "MRQ_STOCK" if stmt == "balance_sheet" else ltm_p.get("method", "FY_PLUS_YTD_MINUS_PRIOR_YTD"),
                    "base_fy": base_fy,
                    "base_fy_val": (matched.get("values") or {}).get(base_fy) if base_fy else None,
                    "ytd_curr": ltm_p.get("ytd_curr"),
                    "ytd_prev": ltm_p.get("ytd_prev"),
                    "ltm_val": payload["value_usd"],
                }

    payload["highlight_concept"] = hi_concept
    payload["highlight_label"] = hi_label
    payload["filing_links"] = _build_filing_links(t, fs, period, stmt, hi_concept, hi_label)
    return JsonResponse(payload)


def _inject_highlight_into_sec_html(raw_html: str, base_url: str, concept: str, raw_label: str) -> str:
    """Inserta `<base href>` y resaltado/auto-scroll quirúrgico hacia el concepto XBRL o etiqueta."""
    clean_html = re.sub(r'<script\b[^>]*>.*?</script>', '', raw_html, flags=re.IGNORECASE | re.DOTALL)
    base_tag = f'<base href="{base_url.rstrip("/")}/">'
    if re.search(r'<head\b[^>]*>', clean_html, re.IGNORECASE):
        clean_html = re.sub(r'(<head\b[^>]*>)', r'\1' + base_tag, clean_html, count=1, flags=re.IGNORECASE)
    else:
        clean_html = base_tag + clean_html

    norm_conc = (concept or "").strip().replace(":", "_")
    short_conc = norm_conc.split("_")[-1] if "_" in norm_conc else norm_conc
    js_payload = json.dumps({"concept": norm_conc, "shortConcept": short_conc, "label": (raw_label or "").strip()})

    snippet = f"""
<style id="agy-sec-style">
  tr.agy-sec-highlight > td, tr.agy-sec-highlight > th {{
    background-color: #fef08a !important;
    border-top: 2px solid #d97706 !important;
    border-bottom: 2px solid #d97706 !important;
    font-weight: 700 !important;
  }}
  tr.agy-sec-highlight td:first-child {{
    border-left: 4px solid #d97706 !important;
  }}
</style>
<script>
(function() {{
  const target = {js_payload};
  const normText = (s) => (s || '').toLowerCase().replace(/[^a-z0-9]/g, '');
  function findRow() {{
    const rows = Array.from(document.querySelectorAll('table.report tr, tr'));
    if (target.concept || target.shortConcept) {{
      for (const tr of rows) {{
        const a = tr.querySelector('a[onclick]');
        const oc = a ? (a.getAttribute('onclick') || '') : '';
        if (target.concept && oc.includes('defref_' + target.concept)) return tr;
      }}
      if (target.shortConcept && target.shortConcept.length > 5) {{
        for (const tr of rows) {{
          const a = tr.querySelector('a[onclick]');
          const oc = a ? (a.getAttribute('onclick') || '') : '';
          if (oc.toLowerCase().includes('_' + target.shortConcept.toLowerCase())) return tr;
        }}
      }}
    }}
    const wantedLbl = normText(target.label);
    if (wantedLbl.length >= 4) {{
      for (const tr of rows) {{
        const firstTd = tr.querySelector('td.pl, td');
        if (firstTd && normText(firstTd.textContent) === wantedLbl) return tr;
      }}
      for (const tr of rows) {{
        const firstTd = tr.querySelector('td.pl, td');
        if (firstTd && normText(firstTd.textContent).includes(wantedLbl)) return tr;
      }}
    }}
    return null;
  }}
  window.addEventListener('DOMContentLoaded', function() {{
    const row = findRow();
    if (row) {{
      row.classList.add('agy-sec-highlight');
      setTimeout(() => row.scrollIntoView({{ behavior: 'smooth', block: 'center' }}), 80);
    }}
  }});
}})();
</script>
"""
    if re.search(r'</body>', clean_html, re.IGNORECASE):
        return re.sub(r'</body>', snippet + '</body>', clean_html, count=1, flags=re.IGNORECASE)
    return clean_html + snippet


@require_GET
@xframe_options_sameorigin
def sec_report_proxy_api(request, ticker: str, accession: str, report_file: str) -> HttpResponse:
    """Proxy seguro e inyectado para renderizar reportes oficiales `R*.htm` de SEC dentro del Evidence Drawer."""
    t = str(ticker or "").strip().upper()
    if not _TICKER_RE.match(t) or not _ACCESSION_RE.match(accession):
        return HttpResponse("Parámetros de filing SEC inválidos.", status=400)

    is_auto = (report_file.upper() == "AUTO")
    if not is_auto and not _REPORT_FILE_RE.match(report_file):
        return HttpResponse("Nombre de reporte XBRL inválido.", status=400)

    fs = _load_company_fs(t)
    if fs is None:
        return HttpResponse("Empresa no encontrada.", status=404)

    idx_entry = (fs.get("sec_filings_index") or {}).get(accession) or {}
    cik_digits = re.sub(r'\D', '', str(idx_entry.get("cik_int") or fs.get("cik") or ""))
    if not cik_digits:
        return HttpResponse("CIK no disponible.", status=404)

    base_url = idx_entry.get("filing_base_url") or f"https://www.sec.gov/Archives/edgar/data/{int(cik_digits)}/{accession.replace('-', '')}"
    stmt = (request.GET.get("stmt") or "income_statement").strip()
    actual_file = report_file
    if is_auto:
        cached_rep = (idx_entry.get("statement_reports") or {}).get(stmt) or {}
        actual_file = cached_rep.get("report_file") or ""
        if not actual_file:
            resolved = _resolve_report_file_from_summary(base_url, stmt)
            actual_file = resolved["report_file"] if resolved else ""
        if not actual_file:
            return HttpResponse(
                f"<html><body style='font-family:sans-serif;padding:20px;color:#334155'>"
                f"<h3>No se encontró tabla resumida R*.htm para {stmt} en este filing</h3>"
                f"<p>Puedes abrir el filing completo directamente en SEC EDGAR iXBRL usando el botón superior.</p>"
                f"</body></html>",
                content_type="text/html; charset=utf-8",
            )

    raw_html = _fetch_sec_text_cached(f"{base_url.rstrip('/')}/{actual_file}")
    if not raw_html:
        return HttpResponse(
            "<html><body style='font-family:sans-serif;padding:20px;color:#b91c1c'>"
            "No fue posible descargar el reporte R*.htm desde SEC EDGAR en este momento.</body></html>",
            status=502,
            content_type="text/html; charset=utf-8",
        )

    patched = _inject_highlight_into_sec_html(
        raw_html,
        base_url,
        concept=(request.GET.get("concept") or "").strip(),
        raw_label=(request.GET.get("raw_label") or "").strip(),
    )
    return HttpResponse(patched, content_type="text/html; charset=utf-8")
