# -*- coding: utf-8 -*-
"""
Construcción de Índices de Procedencia SEC EDGAR (`sec_filings_index` y `period_filing_map`).
Mapea cada período (`LTM`, `FY2025`...`FY2016`) a su filing oficial SEC, accession number,
URL del visor Inline XBRL (`sec.gov/ix`), documento primario y reportes individuales `R*.htm`
extraídos de `FilingSummary.xml` / `filing.reports`.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Optional

logger = logging.getLogger(__name__)


def classify_statement_report_name(short_name: str) -> Optional[str]:
    """Mapea `short_name` de FilingSummary.xml hacia el tipo de estado canónico."""
    s = (short_name or "").strip().lower()
    if not s or "parenthetical" in s:
        return None
    if "comprehensive" in s:
        return None
    if any(k in s for k in ("cash flow", "cash flows")):
        return "cash_flow_statement"
    if any(k in s for k in ("balance sheet", "financial position", "assets and liabilities", "financial condition")):
        return "balance_sheet"
    if any(k in s for k in (
        "statement of operations",
        "statements of operations",
        "statement of income",
        "statements of income",
        "statement of earnings",
        "statements of earnings",
        "statement of profit or loss",
        "income statement",
        "results of operations",
    )) and "stockholders" not in s and "shareholders" not in s and "equity" not in s:
        return "income_statement"
    return None


def extract_statement_reports_from_filing(filing: Any, filing_base_url: str) -> dict:
    """Extrae el mapa `statement_type -> {report_file, short_name, url}` desde `filing.reports`."""
    found = {}
    try:
        reps = getattr(filing, "reports", None)
    except Exception as exc:
        logger.debug("No se pudieron cargar reports del filing: %s", exc)
        return found

    if reps is None:
        return found

    items = getattr(reps, "reports", None)
    if items is None:
        try:
            items = list(reps)
        except Exception:
            items = []
    for rep in items:
        cat = str(getattr(rep, "menu_category", "") or "").strip().lower()
        if cat and cat != "statements":
            continue
        short_name = str(getattr(rep, "short_name", "") or "").strip()
        stmt_type = classify_statement_report_name(short_name)
        if not stmt_type or stmt_type in found:
            continue
        html_file = str(getattr(rep, "html_file_name", "") or getattr(rep, "file_name", "") or "").strip()
        if not html_file:
            continue
        found[stmt_type] = {
            "report_file": html_file,
            "short_name": short_name,
            "url": f"{filing_base_url.rstrip('/')}/{html_file}" if filing_base_url else "",
        }
        if len(found) == 3:
            break
    return found


def _build_filing_entry(filing: Any, cik_int: str, fetch_reports: bool = False) -> Optional[dict]:
    """Construye una entrada compacta para `sec_filings_index`."""
    acc = str(getattr(filing, "accession_number", "") or "").strip()
    if not acc:
        return None
    acc_nodash = acc.replace("-", "")
    form = str(getattr(filing, "form", "") or "").strip()
    fdate = str(getattr(filing, "filing_date", "") or "")[:10]
    por = str(getattr(filing, "period_of_report", "") or getattr(filing, "report_date", "") or "")[:10]
    primary_doc = str(
        getattr(filing, "primary_document", None)
        or getattr(getattr(filing, "document", None), "document", "")
        or ""
    ).strip()

    filing_base_url = f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_nodash}" if cik_int and acc_nodash else ""
    sec_htm_url = (
        f"{filing_base_url}/{primary_doc}"
        if (filing_base_url and primary_doc)
        else str(getattr(filing, "filing_url", "") or "")
    )
    sec_ixbrl_url = (
        f"https://www.sec.gov/ix?doc=/Archives/edgar/data/{cik_int}/{acc_nodash}/{primary_doc}"
        if (cik_int and acc_nodash and primary_doc.lower().endswith((".htm", ".html")))
        else sec_htm_url
    )

    stmt_reports = extract_statement_reports_from_filing(filing, filing_base_url) if fetch_reports else {}
    return {
        "accession_number": acc,
        "acc_nodash": acc_nodash,
        "cik_int": cik_int,
        "form": form,
        "filing_date": fdate,
        "period_of_report": por,
        "primary_document": primary_doc,
        "filing_base_url": filing_base_url,
        "sec_htm_url": sec_htm_url,
        "sec_ixbrl_url": sec_ixbrl_url,
        "statement_reports": stmt_reports,
    }


def _infer_fy_from_por(por: str, fdate: str) -> Optional[str]:
    """Deriva la etiqueta `FYyyyy` coherente con el período de reporte del filing anual."""
    date_s = por or fdate
    m = re.match(r'^(\d{4})-(\d{2})', str(date_s or '').strip())
    if not m:
        return None
    year = int(m.group(1))
    month = int(m.group(2))
    # Cierres tempranos de enero suelen pertenecer al año fiscal que terminó el 31/12 anterior
    if month == 1 and int(str(date_s)[8:10] or 15) <= 7:
        year -= 1
    return f"FY{year}"


def _safe_detect_ytd_pair(q_inc: Any) -> tuple[Optional[str], Optional[str]]:
    """Detecta las etiquetas de columnas YTD actual/anterior si `q_inc` está disponible."""
    if q_inc is None or getattr(q_inc, "empty", True):
        return None, None
    try:
        from .sec_xbrl_ltm import _detect_ytd_columns
        return _detect_ytd_columns(q_inc)
    except Exception:
        cols = [str(c) for c in getattr(q_inc, "columns", []) if "ytd" in str(c).lower()]
        return (cols[0], cols[1] if len(cols) > 1 else None) if cols else (None, None)


def build_sec_provenance_index(
    filing_context: Any,
    annual_fys: list[str],
    has_ltm: bool = False,
    q_inc: Any = None,
    latest_fy: Optional[str] = None,
    sec_metadata: Optional[dict] = None,
) -> tuple[dict, dict]:
    """
    Construye `(sec_filings_index, period_filing_map)` para almacenar en `financial_statements.json`.
    Descarga `FilingSummary.xml` únicamente para los filings activos más recientes (<=4 llamadas),
    dejando años antiguos listos para resolución cacheada bajo demanda en el visor web.
    """
    if filing_context is None:
        return {}, {}

    raw_cik = str(getattr(filing_context, "cik", "") or "").strip()
    cik_digits = re.sub(r'\D', '', raw_cik)
    cik_int = str(int(cik_digits)) if cik_digits else ""

    sec_filings_index: dict[str, dict] = {}
    period_filing_map: dict[str, dict] = {}

    annual_forms = ["10-K", "20-F"]
    interim_forms = ["10-Q", "6-K"]

    try:
        annual_filings = list(filing_context.get_filings(form=annual_forms) or [])[:12]
        if not annual_filings:
            annual_filings = list(filing_context.get_filings(form="40-F") or [])[:12]
    except Exception as exc:
        logger.debug("No se pudieron listar filings anuales para procedencia: %s", exc)
        annual_filings = []

    try:
        interim_filings = list(filing_context.get_filings(form=interim_forms) or [])[:6]
    except Exception as exc:
        logger.debug("No se pudieron listar filings trimestrales para procedencia: %s", exc)
        interim_filings = []

    fy_to_accession: dict[str, str] = {}
    latest_annual_acc: Optional[str] = None
    for idx, fl in enumerate(annual_filings):
        entry = _build_filing_entry(fl, cik_int, fetch_reports=(idx < 2))
        if not entry:
            continue
        acc = entry["accession_number"]
        sec_filings_index[acc] = entry
        if latest_annual_acc is None:
            latest_annual_acc = acc
        fy_lbl = _infer_fy_from_por(entry["period_of_report"], entry["filing_date"])
        if fy_lbl and fy_lbl not in fy_to_accession:
            fy_to_accession[fy_lbl] = acc

    latest_10q_acc: Optional[str] = None
    latest_10q_por: Optional[str] = None
    for idx, fl in enumerate(interim_filings):
        form_u = str(getattr(fl, "form", "") or "").upper()
        # Evitar descargar 6-K no XBRL salvo que tenga reportes
        is_10q = "10-Q" in form_u
        entry = _build_filing_entry(fl, cik_int, fetch_reports=(idx < 2 and (is_10q or not latest_annual_acc)))
        if not entry:
            continue
        acc = entry["accession_number"]
        sec_filings_index[acc] = entry
        if latest_10q_acc is None and (is_10q or entry["statement_reports"]):
            latest_10q_acc = acc
            latest_10q_por = entry["period_of_report"] or entry["filing_date"]
        elif latest_10q_acc is None and idx == 0:
            latest_10q_acc = acc
            latest_10q_por = entry["period_of_report"] or entry["filing_date"]

    # Mapear cada FY solicitado a su filing directo o 10-K comparativo más cercano
    for fy in (annual_fys or []):
        direct_acc = fy_to_accession.get(fy)
        if direct_acc:
            period_filing_map[fy] = {
                "accession": direct_acc,
                "method": "NATIVE_ANNUAL_FILING",
                "period_of_report": sec_filings_index[direct_acc].get("period_of_report"),
            }
        elif latest_annual_acc:
            period_filing_map[fy] = {
                "accession": latest_annual_acc,
                "method": "COMPARATIVE_IN_ANNUAL_FILING",
                "period_of_report": sec_filings_index[latest_annual_acc].get("period_of_report"),
            }

    # Mapear LTM (puente FY_base + YTD_curr - YTD_prev vs 10-K)
    if has_ltm:
        ytd_curr, ytd_prev = _safe_detect_ytd_pair(q_inc)
        ltm_src_type = str((sec_metadata or {}).get("ltm_basis") or "").upper()
        base_acc = fy_to_accession.get(latest_fy or "") or latest_annual_acc
        latest_10q_is_newer = False
        if latest_10q_acc and base_acc:
            q_por = sec_filings_index[latest_10q_acc].get("period_of_report") or ""
            k_por = sec_filings_index[base_acc].get("period_of_report") or ""
            latest_10q_is_newer = bool(q_por > k_por)
        elif latest_10q_acc and not base_acc:
            latest_10q_is_newer = True

        if ("10-K" in ltm_src_type or "20-F" in ltm_src_type) or (not latest_10q_is_newer and base_acc):
            period_filing_map["LTM"] = {
                "accession": base_acc,
                "base_accession": base_acc,
                "ytd_accession": base_acc,
                "base_fy": latest_fy,
                "method": "ANNUAL_10K",
                "period_label": latest_fy or "Annual",
            }
        else:
            period_filing_map["LTM"] = {
                "accession": latest_10q_acc or base_acc,
                "base_accession": base_acc,
                "ytd_accession": latest_10q_acc,
                "base_fy": latest_fy,
                "ytd_curr": str(ytd_curr or latest_10q_por or "YTD Actual"),
                "ytd_prev": str(ytd_prev or "YTD Previo"),
                "method": "6K_INTERIM" if ("6-K" in ltm_src_type) else "FY_PLUS_YTD_MINUS_PRIOR_YTD",
                "period_label": str(ytd_curr or latest_10q_por or "LTM"),
            }

    return sec_filings_index, period_filing_map
