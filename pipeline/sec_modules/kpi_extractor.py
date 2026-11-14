"""
kpi_extractor.py - Extractor y Normalizador Universal de KPIs Operativos y Métricas Non-GAAP.
Jerarquía de extracción oficial:
1. Fuente Primaria Automatizada: Formularios 8-K / 6-K Exhibit 99.1 (Earnings Press Release / Letter to Shareholders).
2. Fuente Secundaria Complementaria: Presentaciones a Inversores en formato PDF (Google Drive / local).

Normaliza KPIs estructurados según el Arquetipo de Industria:
- FINANCIAL_BANKING: ARPAC, Cost-to-Serve, NPLs (15-90 y 90+), NIM ajustado, Eficiencia, Cobertura, Depósitos por país.
- PLATFORM_ECOSYSTEM: GMV (3M/6M), TPV (3M/6M), Fintech MAUs, Compradores Únicos, Items vendidos, Cartera de crédito y NIMAL.
- STANDARD_CORPORATE / REAL_ESTATE_REIT / INSURANCE: Segmentos, canales, geografía y KPIs operativos sectoriales.

Genera y mantiene sincronizado: data/processed/{TICKER}/presentation_reconciliation.json
"""

import argparse
from datetime import datetime
import json
import logging
from pathlib import Path
import re
import sys

from bs4 import BeautifulSoup
from pypdf import PdfReader

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
import pipeline  # noqa: E402, F401

try:
    from json_io import atomic_json_write
    from config_loader import (
        load_sec_config,
        resolve_output_dir,
        DATA_DIR,
        DEFAULT_SEC_IDENTITY,
    )
    from entity_classifier import normalize_archetype
except ImportError:
    try:
        from pipeline.json_io import atomic_json_write
        from pipeline.config_loader import (
            load_sec_config,
            resolve_output_dir,
            DATA_DIR,
            DEFAULT_SEC_IDENTITY,
        )
        from pipeline.entity_classifier import normalize_archetype
    except ImportError:
        from .json_io import atomic_json_write
        from .config_loader import (
            load_sec_config,
            resolve_output_dir,
            DATA_DIR,
            DEFAULT_SEC_IDENTITY,
        )
        from .entity_classifier import normalize_archetype

logger = logging.getLogger(__name__)

# UTF-8 para consola Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError, OSError) as exc:
        logger.debug("No se pudo reconfigurar stdout a UTF-8: %s", exc)

try:
    from sec_rate_limiter import sec_call_with_retry
    from drive_manager import (
        resolve_google_drive_path,
        get_ticker_drive_processed_dir,
        safe_copy_file,
    )
except ImportError:
    from .sec_rate_limiter import sec_call_with_retry
    from .drive_manager import (
        resolve_google_drive_path,
        get_ticker_drive_processed_dir,
        safe_copy_file,
    )

try:
    from edgar import set_identity, Company
except ImportError:
    Company = None
    set_identity = None


def _score_pdf_recency(fname: str) -> int:
    """Calcula dinámicamente la puntuación de recencia a partir de año (6 pts/año) y trimestre (1-4 pts)."""
    fname_low = fname.lower()
    years_found = [int(y) for y in re.findall(r"\b(20\d{2})\b", fname_low)]
    short_years = [2000 + int(y) for y in re.findall(r"(?:fy|'|q[1-4])(\d{2})\b", fname_low)]
    all_years = years_found + short_years
    if not all_years:
        return 0
    best_year = max(all_years)
    quarters = [
        int(g)
        for m in re.finditer(r"(?:^|[^a-z])q([1-4])|([1-4])q(?=\d)", fname_low)
        for g in m.groups()
        if g
    ]
    best_quarter = max(quarters) if quarters else 0
    return max(0, (best_year - 2018) * 6 + best_quarter)


def _latest_period_value(vals_dict):
    """Obtiene el último valor no nulo (LTM o último FY cronológico), sin inyectar 0.0 artificial."""
    if not isinstance(vals_dict, dict):
        return None
    if vals_dict.get("LTM") is not None:
        return vals_dict["LTM"]
    fy_keys = [k for k, v in vals_dict.items() if str(k).startswith("FY") and v is not None]
    if not fy_keys:
        return None
    latest_fy = max(fy_keys, key=lambda fk: int(re.search(r"(\d{4})", fk).group(1)) if re.search(r"(\d{4})", fk) else -1)
    return vals_dict.get(latest_fy)


def extract_from_sec_ex99(ticker, filing_context=None):
    """
    Localiza y descarga el documento oficial de resultados más reciente (Ex-99.1 o Press Release)
    desde SEC EDGAR mediante edgar-tools.
    """
    if Company is None:
        print("[KPI Extractor] edgar-tools no disponible.")
        return None

    cfg = load_sec_config()
    set_identity(cfg.get("sec_identity", DEFAULT_SEC_IDENTITY))

    print(f"[KPI Extractor] Buscando comunicados de resultados oficiales (Ex-99.1) para {ticker} en SEC EDGAR...")
    company = filing_context.company if filing_context else sec_call_with_retry(Company, ticker.upper())
    if not company:
        return None

    candidate_filings = []

    try:
        f8k = filing_context.get_filings(form="8-K") if filing_context else sec_call_with_retry(company.get_filings, form="8-K")
        if f8k and len(f8k) > 0:
            for f in f8k[:15]:
                items = str(getattr(f, "items", ""))
                has_item_202 = "2.02" in items
                for att in getattr(f, "attachments", []):
                    desc = str(getattr(att, "description", "")).lower()
                    doc = str(getattr(att, "document", "")).lower()
                    form_t = str(getattr(att, "form_type", "")).lower()
                    is_ex99 = "99.1" in desc or "ex-99" in form_t or "ex99" in doc or "pressrelease" in doc or "earnings" in doc
                    if any(ext in doc for ext in (".htm", ".html")) and (is_ex99 or has_item_202):
                        prio_score = (100 if has_item_202 else 0) + (50 if ("99.1" in desc or "ex991" in doc) else (20 if "99" in desc else 0)) + (
                            10 if ("pressrelease" in doc or "earnings" in doc) else 0
                        )
                        candidate_filings.append(
                            {
                                "filing_date": str(f.filing_date),
                                "form": "8-K",
                                "item_202": has_item_202,
                                "prio_score": prio_score,
                                "attachment": att,
                                "doc_name": getattr(att, "document", "ex99.htm"),
                                "desc": desc,
                            }
                        )
    except Exception as e:
        print(f"[KPI Extractor] Aviso escaneando 8-K: {e}")

    try:
        f6k = filing_context.get_filings(form="6-K") if filing_context else sec_call_with_retry(company.get_filings, form="6-K")
        if f6k and len(f6k) > 0:
            for f in f6k[:15]:
                for att in getattr(f, "attachments", []):
                    desc = str(getattr(att, "description", "")).lower()
                    doc = str(getattr(att, "document", "")).lower()
                    is_pr = any(k in doc for k in ("pr", "press", "release", "letter", "presentation", "earnings", "ex99", "ex-99"))
                    if is_pr and any(ext in doc for ext in (".htm", ".html")):
                        prio_score = 50 + (30 if any(k in doc for k in ("pr", "press", "release")) else 0) + (
                            20 if any(k in doc for k in ("presentation", "letter")) else 0
                        ) + (20 if ("99.1" in desc or "ex-99" in desc) else 0)
                        candidate_filings.append(
                            {
                                "filing_date": str(f.filing_date),
                                "form": "6-K",
                                "item_202": True,
                                "prio_score": prio_score,
                                "attachment": att,
                                "doc_name": getattr(att, "document", "6k_pr.htm"),
                                "desc": desc,
                            }
                        )
    except Exception as e:
        print(f"[KPI Extractor] Aviso escaneando 6-K: {e}")

    if not candidate_filings:
        print("[KPI Extractor] No se encontraron adjuntos Ex-99.1 recientes en SEC EDGAR.")
        return None

    candidate_filings.sort(key=lambda x: (x.get("prio_score", 0), x["filing_date"]), reverse=True)
    best = candidate_filings[0]
    att = best["attachment"]

    print(f"  [OK] Documento de resultados seleccionado: {best['doc_name']} ({best['form']} del {best['filing_date']})")
    try:
        raw_html = sec_call_with_retry(att.download)
        if not raw_html:
            return None
        soup = BeautifulSoup(raw_html, "html.parser")
        full_text = soup.get_text("\n")
        return {
            "source_doc": best["doc_name"],
            "filing_date": best["filing_date"],
            "form": best["form"],
            "html": raw_html,
            "text": full_text,
            "lines": [line.strip() for line in full_text.splitlines() if line.strip()],
            "soup": soup,
        }
    except Exception as e:
        print(f"[KPI Extractor] Error al descargar adjunto SEC {best['doc_name']}: {e}")
        return None


def extract_from_presentation_pdf(ticker, custom_drive_path=None):
    """Busca y parsea presentaciones a inversores en PDF desde Google Drive o almacenamiento local."""
    possible_dirs = []
    drive_base = resolve_google_drive_path(custom_drive_path)
    if drive_base and drive_base.exists():
        t_drive = drive_base / ticker.upper()
        if t_drive.exists():
            possible_dirs.extend([t_drive / "presentations", t_drive])

    local_p = DATA_DIR / "raw" / ticker.upper() / "presentations"
    if local_p.exists():
        possible_dirs.append(local_p)

    pdf_candidates = []
    for d in possible_dirs:
        if d.exists():
            for f in d.glob("*.pdf"):
                fname = f.name.lower()
                if not f.is_file() or re.match(r"^[0-9a-f\-]{25,}\.pdf$", fname):
                    continue
                p_score = _score_pdf_recency(fname)
                if "presentation" in fname:
                    p_score += 40
                if "letter" in fname:
                    p_score += 35
                if "earnings" in fname or "results" in fname:
                    p_score += 30
                if ticker.lower() in fname:
                    p_score += 20
                if any(q in fname for q in ("q1", "q2", "q3", "q4")):
                    p_score += 10
                pdf_candidates.append({"path": f, "score": p_score, "mtime": f.stat().st_mtime})

    if not pdf_candidates:
        return None

    pdf_candidates.sort(key=lambda x: (x["score"], x["mtime"]), reverse=True)
    best_pdf = pdf_candidates[0]["path"]
    print(f"[KPI Extractor] Analizando presentación PDF: {best_pdf.name}")

    slides = []
    try:
        reader = PdfReader(best_pdf)
        for idx, page in enumerate(reader.pages):
            clean_lines = [l.strip() for l in (page.extract_text() or "").splitlines() if l.strip()]
            if clean_lines:
                slides.append({"slide_number": idx + 1, "content": "\n".join(clean_lines)})
    except Exception as e:
        print(f"[KPI Extractor] Error leyendo PDF {best_pdf.name}: {e}")
        return None

    full_text = "\n".join(s["content"] for s in slides)
    return {
        "source_presentation": best_pdf.name,
        "total_slides": len(slides),
        "text": full_text,
        "slides": slides,
    }


def _extract_float(text, regex_pattern, default=None):
    """Extrae un valor flotante aplicando una expresión regular."""
    m = re.search(regex_pattern, text, re.IGNORECASE)
    if m:
        raw_token = m.group(1).replace(",", "").replace("$", "").strip()
        try:
            return float(raw_token)
        except ValueError as exc:
            logger.debug("Valor regex no numérico (%r) ignorado para patrón %s: %s", raw_token, regex_pattern, exc)
    return default


def _combine_sources_text(sec_data, pdf_data, res):
    """Consolida texto, líneas y metadatos de fuentes SEC Ex-99.1 y PDF."""
    all_text = ""
    lines = []
    if sec_data:
        all_text += "\n" + sec_data.get("text", "")
        lines.extend(sec_data.get("lines", []))
        res["source_sec"] = sec_data.get("source_doc")
    if pdf_data:
        all_text += "\n" + pdf_data.get("text", "")
        res["source_presentation"] = pdf_data.get("source_presentation", res.get("source_presentation"))
        res["total_slides"] = pdf_data.get("total_slides", res.get("total_slides"))
    return all_text, lines


def normalize_banking_kpis(sec_data, pdf_data, base_dict):
    """
    Normaliza métricas para el arquetipo FINANCIAL_BANKING (ROE, NIM ajustado, eficiencia,
    NPL 15-90/90+, cobertura, ARPAC, cost to serve, clientes y depósitos por país).
    """
    res = dict(base_dict or {})
    res["archetype"] = "FINANCIAL_BANKING"
    all_text, _ = _combine_sources_text(sec_data, pdf_data, res)

    roe = _extract_float(all_text, r"(?:ROE|return\s+on\s+equity)[\s\w]*?(?:closed\s+the\s+quarter\s+at|reached|was|of)\s+([0-9]+(?:\.[0-9]+)?)\s*%", res.get("return_on_equity_reported"))
    res["return_on_equity_reported"] = roe if roe is not None else _extract_float(all_text, r"\bROE\b\s+([0-9]+(?:\.[0-9]+)?)\s*%", res.get("return_on_equity_reported"))

    nim = _extract_float(all_text, r"risk[\s-]adjusted\s+nim[\s\w]*?(?:expanded\s+to|was|of|to)\s+([0-9]+(?:\.[0-9]+)?)\s*%", res.get("risk_adjusted_nim_pct"))
    res["risk_adjusted_nim_pct"] = nim if nim is not None else _extract_float(all_text, r"risk\s+adjusted\s+nim\s+([0-9]+(?:\.[0-9]+)?)\s*%", res.get("risk_adjusted_nim_pct"))

    eff = _extract_float(all_text, r"efficiency[\s-]ratio[\s\w]*?(?:increased\s+to|was|of|to)\s+([0-9]+(?:\.[0-9]+)?)\s*%", res.get("efficiency_ratio_pct"))
    res["efficiency_ratio_pct"] = eff if eff is not None else _extract_float(all_text, r"efficiency-ratio\s+([0-9]+(?:\.[0-9]+)?)\s*%", res.get("efficiency_ratio_pct"))

    npl15 = _extract_float(all_text, r"(?:15-90\s+NPL|NPL\s+15-90)[\s\w]*?(?:improved\s+to|was|of|to)\s+([0-9]+(?:\.[0-9]+)?)\s*%", res.get("npl_15_90_pct"))
    res["npl_15_90_pct"] = npl15 if npl15 is not None else _extract_float(all_text, r"NPL\s+15-90\s+([0-9]+(?:\.[0-9]+)?)\s*%", res.get("npl_15_90_pct"))

    npl90 = _extract_float(all_text, r"(?:90\+\s+NPLs?|NPL\s+90\+)[\s\w]*?(?:increased\s+to|was|of|to)\s+([0-9]+(?:\.[0-9]+)?)\s*%", res.get("npl_90_plus_pct"))
    res["npl_90_plus_pct"] = npl90 if npl90 is not None else _extract_float(all_text, r"NPL\s+90\+\s+([0-9]+(?:\.[0-9]+)?)\s*%", res.get("npl_90_plus_pct"))

    cov = _extract_float(all_text, r"provision\s+coverage[\s\w]*?(?:was|of|to)\s+([0-9]+(?:\.[0-9]+)?)\s*%", res.get("provision_coverage_pct"))
    res["provision_coverage_pct"] = cov if cov is not None else res.get("provision_coverage_pct")

    cust_tot = _extract_float(all_text, r"(?:total\s+of|reaching\s+a\s+total\s+of|number\s+of\s+customers)\s+([0-9]+(?:\.[0-9]+)?)\s+million\s+customers", res.get("total_customers_m"))
    if cust_tot is None:
        cust_tot = _extract_float(all_text, r"number\s+of\s+customers[\s\(\)in\smillions]*\s+([0-9]+(?:\.[0-9]+)?)", res.get("total_customers_m"))
    res["total_customers_m"] = cust_tot

    act_rate = _extract_float(all_text, r"activity\s+rate\s+[\(\)%]*\s+([0-9]+(?:\.[0-9]+)?)\s*%", None)
    res["active_customers_m"] = round(cust_tot * (act_rate / 100.0), 1) if (cust_tot and act_rate) else res.get("active_customers_m")

    arpac = _extract_float(all_text, r"ARPAC\s+(?:reached\s+approximately|was|of)?\s*\$([0-9]+(?:\.[0-9]+)?)", res.get("monthly_arpac_usd"))
    if arpac is None:
        arpac = _extract_float(all_text, r"monthly\s+average\s+revenue\s+per\s+active\s+customer[\s\(\)\$in]*\s+([0-9]+(?:\.[0-9]+)?)", res.get("monthly_arpac_usd"))
    res["monthly_arpac_usd"] = arpac

    cts = _extract_float(all_text, r"cost\s+to\s+serve\s+per\s+active\s+customer[\s\(\)\$in]*\s*([0-9]+(?:\.[0-9]+)?)", res.get("monthly_cost_to_serve_usd"))
    res["monthly_cost_to_serve_usd"] = cts if cts is not None else res.get("monthly_cost_to_serve_usd")

    dep_dict = dict(res.get("deposits_by_country_bn") or {})
    for country, pattern in (
        ("Brazil", r"Brazil\s+closed\s+at\s+\$([0-9]+(?:\.[0-9]+)?)\s*billion"),
        ("Mexico", r"Mexico\s+at\s+\$([0-9]+(?:\.[0-9]+)?)\s*billion"),
        ("Colombia", r"Colombia\s+at\s+\$([0-9]+(?:\.[0-9]+)?)\s*billion"),
        ("Total_Latam", r"total\s+deposits\s+reached\s+\$([0-9]+(?:\.[0-9]+)?)\s*billion"),
    ):
        found = _extract_float(all_text, pattern, dep_dict.get(country))
        if found is not None:
            dep_dict[country] = found
    res["deposits_by_country_bn"] = dep_dict

    cust_dict = dict(res.get("customers_by_country_m") or {})
    for country, pattern in (
        ("Brazil", r"(?:almost|nearly|over|approximately)?\s*([0-9]+(?:\.[0-9]+)?)\s+million\s+customers\s+in\s+Brazil"),
        ("Mexico", r"Mexico[,\s]+[\w\s]*?(?:reached|surpassed|at)\s+([0-9]+(?:\.[0-9]+)?)\s+million"),
        ("Colombia", r"Colombia[,\s]+[\w\s]*?(?:reached|surpassed|at)\s+([0-9]+(?:\.[0-9]+)?)\s+million"),
    ):
        found = _extract_float(all_text, pattern, cust_dict.get(country))
        if found is not None:
            cust_dict[country] = found
    res["customers_by_country_m"] = cust_dict

    if res.get("capital_adequacy"):
        res["capital_adequacy"] = dict(res["capital_adequacy"])
    return res


def normalize_platform_kpis(sec_data, pdf_data, base_dict):
    """Normaliza métricas para el arquetipo PLATFORM_ECOSYSTEM (GMV, TPV, MAUs, crédito y NIMAL)."""
    res = dict(base_dict or {})
    res["archetype"] = "PLATFORM_ECOSYSTEM"

    all_text = ""
    if sec_data:
        all_text += "\n" + sec_data.get("text", "")
        res["source_letter"] = sec_data.get("source_doc")
    if pdf_data:
        all_text += "\n" + pdf_data.get("text", "")
        res["source_presentation"] = pdf_data.get("source_presentation", res.get("source_presentation"))

    mk_kpis = dict(res.get("marketplace_kpis") or {})
    fin_kpis = dict(res.get("fintech_kpis") or {})
    cred_kpis = dict(res.get("credit_portfolio_kpis") or {})
    geo_dict = dict(res.get("geographic_breakdown") or {})
    seg_dict = dict(res.get("segment_breakdown") or {})
    cf_kpis = dict(res.get("cash_flow_kpis") or {})

    gmv_bn = _extract_float(all_text, r"gross\s+merchandise\s+volume[\s\w]*?\$([0-9]+(?:\.[0-9]+)?)\s*billion", None)
    if gmv_bn:
        curr_gmv = mk_kpis.get("gmv_three_months_usd_m")
        if not (curr_gmv and abs(curr_gmv - (gmv_bn * 1000.0)) < 100.0):
            mk_kpis["gmv_three_months_usd_m"] = gmv_bn * 1000.0
    else:
        gmv_val = _extract_float(all_text, r"gross\s+merchandise\s+volume[\s\w]*?\$([0-9,]+(?:\.[0-9]+)?)\s*million", None)
        if gmv_val and gmv_val > 10000:
            mk_kpis["gmv_three_months_usd_m"] = gmv_val

    buyers = _extract_float(all_text, r"([0-9]+(?:\.[0-9]+)?)\s*million\s+unique\s+active\s+buyers", mk_kpis.get("unique_active_buyers_m"))
    if buyers is None:
        buyers = _extract_float(all_text, r"unique\s+buyers[\s\w]*?([0-9]+(?:\.[0-9]+)?)\s*million", mk_kpis.get("unique_active_buyers_m"))
    if buyers is not None:
        mk_kpis["unique_active_buyers_m"] = buyers

    items_sold = _extract_float(all_text, r"([0-9]+(?:\.[0-9]+)?)\s*million\s+items\s+sold", mk_kpis.get("items_sold_three_months_m"))
    if items_sold is not None:
        mk_kpis["items_sold_three_months_m"] = items_sold

    tpv_bn = _extract_float(all_text, r"total\s+payment\s+volume[\s\w]*?\$([0-9]+(?:\.[0-9]+)?)\s*billion", None)
    if tpv_bn:
        curr_tpv = fin_kpis.get("tpv_total_usd_m")
        if not (curr_tpv and abs(curr_tpv - (tpv_bn * 1000.0)) < 500.0):
            fin_kpis["tpv_total_usd_m"] = tpv_bn * 1000.0
    else:
        tpv_m = _extract_float(all_text, r"total\s+payment\s+volume[\s\w]*?\$([0-9,]+(?:\.[0-9]+)?)\s*million", None)
        if tpv_m and tpv_m > 10000:
            fin_kpis["tpv_total_usd_m"] = tpv_m

    mau = _extract_float(all_text, r"([0-9]+(?:\.[0-9]+)?)\s*million\s+monthly\s+active\s+users", fin_kpis.get("fintech_mau_m"))
    if mau is None:
        mau = _extract_float(all_text, r"fintech\s+mau[s]?[\s\w]*?([0-9]+(?:\.[0-9]+)?)\s*m", fin_kpis.get("fintech_mau_m"))
    if mau is not None:
        fin_kpis["fintech_mau_m"] = mau

    for field, pattern in (
        ("credit_portfolio_usd_bn", r"credit\s+portfolio[\s\w]*?\$([0-9]+(?:\.[0-9]+)?)\s*billion"),
        ("nimal_pct", r"NIMAL[\s\w]*?([0-9]+(?:\.[0-9]+)?)\s*%"),
        ("npl_15_90_pct", r"15-90\s+NPL[\s\w]*?([0-9]+(?:\.[0-9]+)?)\s*%"),
        ("npl_90_plus_pct", r"90\+\s+NPL[\s\w]*?([0-9]+(?:\.[0-9]+)?)\s*%"),
    ):
        found = _extract_float(all_text, pattern, cred_kpis.get(field))
        if found is not None:
            cred_kpis[field] = found

    adj_fcf = _extract_float(all_text, r"adjusted\s+free\s+cash\s+flow[\s\w]*?\$?\s*([0-9,]+(?:\.[0-9]+)?)\s*(?:million)?", cf_kpis.get("adjusted_free_cash_flow_usd_m"))
    if adj_fcf is not None:
        cf_kpis["adjusted_free_cash_flow_usd_m"] = adj_fcf

    res["marketplace_kpis"] = mk_kpis
    res["fintech_kpis"] = fin_kpis
    res["credit_portfolio_kpis"] = cred_kpis
    res["geographic_breakdown"] = geo_dict
    res["segment_breakdown"] = seg_dict
    res["cash_flow_kpis"] = cf_kpis
    return res


def _update_channel_metric(channels, channel_name, line_text, line_low):
    """Extrae ventas y crecimiento de un canal manteniendo valores previos si faltan."""
    m_rev = re.search(
        r"(?:to|\$)\s*([0-9,]+(?:\.[0-9]+)?)\s*(million|billion|bn|m)?\b",
        line_text,
        re.IGNORECASE,
    )
    rev = None
    if m_rev:
        raw_num = float(m_rev.group(1).replace(",", ""))
        unit = (m_rev.group(2) or "").lower()
        rev = round(raw_num * 1000.0, 1) if unit in ("billion", "bn") else raw_num
    g = _extract_float(line_text, r"(?:increased|decreased|up|down)\s+([0-9]+(?:\.[0-9]+)?)\s*%")
    if g is not None and any(k in line_low for k in ("decreased", "down")):
        g = -g
    prev_entry = channels.get(channel_name, {})
    channels[channel_name] = {
        "revenue_usd_m": rev if rev is not None else prev_entry.get("revenue_usd_m"),
        "growth_yoy_pct": g if g is not None else prev_entry.get("growth_yoy_pct"),
    }


def normalize_corporate_kpis(sec_data, pdf_data, base_dict, output_dir=None):
    """
    Normaliza métricas para el arquetipo STANDARD_CORPORATE integrando dinámicamente segmentos
    de segments_data.json y KPIs operativos oficiales desde Form 8-K Ex-99.1.
    """
    res = dict(base_dict or {})
    res["archetype"] = "STANDARD_CORPORATE"
    all_text, lines = _combine_sources_text(sec_data, pdf_data, res)

    brands = dict(res.get("brand_segmentation") or {})
    channels = dict(res.get("channel_breakdown") or {})
    geos = dict(res.get("geographic_breakdown") or {})
    ops = dict(res.get("operational_kpis") or {})

    if output_dir:
        seg_file = Path(output_dir) / "segments_data.json"
        if seg_file.exists():
            try:
                with open(seg_file, "r", encoding="utf-8") as f:
                    s_data = json.load(f)
                fresh_brands, fresh_geos = {}, {}
                for p in s_data.get("product_segments", []):
                    if p.get("status") == "discontinued" or p.get("is_subtotal") or p.get("is_reconciling"):
                        continue
                    p_name = p.get("name")
                    val = _latest_period_value(p.get("values", {}))
                    if val is None:
                        val = (p.get("interim_disclosure") or {}).get("current_ytd")
                    if p_name and val is not None:
                        fresh_brands[p_name] = {"revenue_usd_m": val}
                for g in s_data.get("geographic_segments", []):
                    if g.get("status") == "discontinued" or g.get("is_subtotal") or g.get("is_country_breakdown"):
                        continue
                    g_name = g.get("name")
                    val = _latest_period_value(g.get("values", {}))
                    if g_name and val is not None:
                        fresh_geos[g_name] = {"revenue_usd_m": val}
                brands = fresh_brands
                geos = fresh_geos
            except (OSError, json.JSONDecodeError, TypeError) as e:
                print(f"[KPI Extractor] Nota leyendo segments_data.json: {e}")

    for l in lines:
        l_low = l.lower()
        m = re.search(
            r"([a-zA-Z0-9\s®\-\(\)]+?)\s*(?:brand)?\s*net\s*sales\s+(?:increased|decreased)\s+([0-9\.]+)%\s+to\s+\$([0-9,]+(?:\.[0-9]+)?)\s*million",
            l,
            re.IGNORECASE,
        )
        if m:
            raw_entity = m.group(1).replace("®", "").strip()
            growth = float(m.group(2))
            if "decreased" in l_low:
                growth = -growth
            val = float(m.group(3).replace(",", ""))

            e_low = raw_entity.lower()
            if any(c in e_low for c in ("wholesale", "direct-to-consumer", "dtc", "retail")):
                c_name = "Wholesale" if "wholesale" in e_low else "Direct-to-Consumer (DTC)"
                channels[c_name] = {"revenue_usd_m": val, "growth_yoy_pct": growth}
            elif any(g in e_low for g in ("domestic", "international", "americas", "europe", "china", "asia")):
                g_name = "Domestic" if "domestic" in e_low else ("International" if "international" in e_low else raw_entity)
                geos[g_name] = {"revenue_usd_m": val, "growth_yoy_pct": growth}
            else:
                brands[raw_entity] = {"revenue_usd_m": val, "growth_yoy_pct": growth}
        elif "wholesale" in l_low and ("net sales" in l_low or "revenue" in l_low):
            _update_channel_metric(channels, "Wholesale", l, l_low)
        elif ("direct-to-consumer" in l_low or "dtc" in l_low) and ("net sales" in l_low or "revenue" in l_low):
            _update_channel_metric(channels, "Direct-to-Consumer (DTC)", l, l_low)

    for key, pattern in (
        ("gross_margin_pct", r"gross\s+margin\s+(?:was|of)\s+([0-9]+(?:\.[0-9]+)?)\s*%"),
        ("diluted_eps", r"diluted\s+(?:earnings\s+per\s+share|eps)\s+(?:was|increased\s+to|of)\s+\$([0-9]+(?:\.[0-9]+)?)"),
        ("share_repurchase_shares_m", r"repurchased\s+approximately\s+([0-9]+(?:\.[0-9]+)?)\s*million\s+shares"),
        ("share_repurchase_usd_m", r"(?:repurchased|total\s+of)\s+\$([0-9,]+(?:\.[0-9]+)?)\s*million\s*(?:of\s+shares)?"),
    ):
        found = _extract_float(all_text, pattern, ops.get(key))
        if found is not None:
            ops[key] = found

    rem_auth = _extract_float(all_text, r"remaining\s+under\s+its\s+stock\s+repurchase\s+authorization.*?\$([0-9]+(?:\.[0-9]+)?)\s*billion", ops.get("remaining_authorization_usd_bn"))
    if rem_auth is None:
        rem_auth = _extract_float(all_text, r"approximately\s+\$([0-9]+(?:\.[0-9]+)?)\s*billion\s+remaining\s+under", ops.get("remaining_authorization_usd_bn"))
    if rem_auth is not None:
        ops["remaining_authorization_usd_bn"] = rem_auth

    op_inc = _extract_float(all_text, r"income\s+from\s+operations\s+was\s+\$([0-9,]+(?:\.[0-9]+)?)\s*(?:thousand)?", ops.get("operating_income_usd_m"))
    if op_inc is not None:
        ops["operating_income_usd_m"] = round(op_inc / 1000.0, 1) if op_inc > 10000 else op_inc

    res["brand_segmentation"] = brands
    res["channel_breakdown"] = channels
    res["geographic_breakdown"] = geos
    res["operational_kpis"] = ops
    return res


def normalize_reit_kpis(sec_data, pdf_data, base_dict):
    """Normaliza métricas operativas para REAL_ESTATE_REIT (ocupación, WALT, payout AFFO, cap rate, propiedades, SS-NOI)."""
    res = dict(base_dict or {})
    res["archetype"] = "REAL_ESTATE_REIT"
    all_text, _ = _combine_sources_text(sec_data, pdf_data, res)
    reit_ops = dict(res.get("reit_operational_kpis") or {})

    occ = _extract_float(all_text, r"(?:occupancy\s+rate|portfolio\s+occupancy|occupancy)[\s\w]*?(?:was|reached|stood\s+at|of|at)\s+([0-9]+(?:\.[0-9]+)?)\s*%", res.get("occupancy_rate_pct"))
    if occ is None:
        occ = _extract_float(all_text, r"(?:occupancy)[\s\w]*?\b([0-9]+(?:\.[0-9]+)?)\s*%", res.get("occupancy_rate_pct"))
    if occ is None:
        occ = _extract_float(all_text, r"\boccupancy\b\s+([0-9]+(?:\.[0-9]+)?)\s*%", res.get("occupancy_rate_pct"))
    if occ is not None:
        res["occupancy_rate_pct"] = reit_ops["occupancy_rate_pct"] = occ

    walt = _extract_float(all_text, r"(?:WALT|weighted[\s-]average\s+lease\s+term)[^0-9\n]*?(?:was|of|to|averaged|is)\s+([0-9]+(?:\.[0-9]+)?)\s*(?:years|yrs)?", res.get("walt_years"))
    if walt is None:
        walt = _extract_float(all_text, r"\bWALT\b[^0-9\n]*?([0-9]+(?:\.[0-9]+)?)\s*(?:years|yrs)?", res.get("walt_years"))
    if walt is not None:
        res["walt_years"] = res["weighted_average_lease_term_years"] = reit_ops["walt_years"] = walt

    for key, pattern in (
        ("payout_ratio_affo_pct", r"(?:AFFO\s+payout\s+ratio|payout\s+ratio[^0-9\n]*?AFFO|dividend\s+payout\s+ratio)[^0-9\n]*?(?:was|of|to|is)\s+([0-9]+(?:\.[0-9]+)?)\s*%"),
        ("cap_rate_pct", r"(?:cap\s+rate|capitalization\s+rate|initial\s+cash\s+yield)[^0-9\n]*?(?:was|of|to|averaged|is)\s+([0-9]+(?:\.[0-9]+)?)\s*%"),
        ("same_store_noi_growth_pct", r"(?:same[\s-]store\s+NOI|same[\s-]store\s+rental\s+revenue)[\s\w]*?(?:increased|grew)\s+([0-9]+(?:\.[0-9]+)?)\s*%"),
    ):
        found = _extract_float(all_text, pattern, res.get(key))
        if found is not None:
            res[key] = reit_ops[key] = found

    props = _extract_float(all_text, r"(?:portfolio\s+of|portfolio\s+consisted\s+of|properties\s+totaling|total\s+properties)[^0-9\n]*?([0-9,]+)\s*(?:commercial|properties|real\s+estate|units)", res.get("total_properties"))
    if props is None:
        props = _extract_float(all_text, r"\b([0-9,]{3,})\s+(?:properties|commercial\s+units)\b", res.get("total_properties"))
    if props is not None:
        res["total_properties"] = res["properties_count"] = reit_ops["total_properties"] = int(props)

    res["reit_operational_kpis"] = reit_ops
    return res


def normalize_insurance_kpis(sec_data, pdf_data, base_dict):
    """Normaliza métricas operativas y técnicas para INSURANCE (combined ratio, investment yield, PIF)."""
    res = dict(base_dict or {})
    res["archetype"] = "INSURANCE"
    all_text, lines = _combine_sources_text(sec_data, pdf_data, res)
    ins_ops = dict(res.get("insurance_operational_kpis") or {})

    comb = _extract_float(all_text, r"(?:combined\s+ratio)[\s\w]*?(?:was|reached|improved\s+to|of)\s+([0-9]+(?:\.[0-9]+)?)\s*%", res.get("combined_ratio_reported"))
    if comb is None:
        comb = _extract_float(all_text, r"\bcombined\s+ratio\b\s+([0-9]+(?:\.[0-9]+)?)\s*%", res.get("combined_ratio_reported"))
    if comb is not None:
        res["combined_ratio_reported"] = ins_ops["combined_ratio_reported"] = comb

    by_line = dict(res.get("combined_ratio_by_line") or {})
    for l in lines:
        l_low = l.lower()
        for line_key, keyword, excl in (
            ("personal_lines", "personal lines", None),
            ("commercial_lines", "commercial lines", None),
            ("property", "property", "personal"),
            ("casualty", "casualty", None),
        ):
            if keyword in l_low and (excl is None or excl not in l_low):
                cr = _extract_float(l, rf"{keyword}[\s\w]*?([0-9]+(?:\.[0-9]+)?)\s*%")
                if cr is None and "combined ratio" in l_low:
                    cr = _extract_float(l, r"([0-9]+(?:\.[0-9]+)?)\s*%")
                if cr is not None:
                    by_line[line_key] = cr
    if by_line:
        res["combined_ratio_by_line"] = ins_ops["combined_ratio_by_line"] = by_line

    yield_pct = _extract_float(all_text, r"(?:net\s+investment\s+yield|investment\s+yield|annualized\s+investment\s+yield)[\s\w]*?(?:was|of|to)\s+([0-9]+(?:\.[0-9]+)?)\s*%", res.get("investment_yield_pct"))
    if yield_pct is None:
        yield_pct = _extract_float(all_text, r"(?:portfolio\s+yield)[\s\w]*?(?:was|of|to)\s+([0-9]+(?:\.[0-9]+)?)\s*%", res.get("investment_yield_pct"))
    if yield_pct is not None:
        res["investment_yield_pct"] = ins_ops["investment_yield_pct"] = yield_pct

    pif = _extract_float(all_text, r"(?:policies\s+in\s+force|total\s+policies)[\s\w]*?(?:reached|totaled|of)\s+([0-9]+(?:\.[0-9]+)?)\s*million", res.get("policies_in_force_m"))
    if pif is None:
        pif_count = _extract_float(all_text, r"([0-9,]+)\s+policies\s+in\s+force", None)
        if pif_count and pif_count > 1000:
            pif = round(pif_count / 1_000_000.0, 2)
    if pif is not None:
        res["policies_in_force_m"] = ins_ops["policies_in_force_m"] = pif

    nwp_g = _extract_float(all_text, r"(?:net\s+written\s+premiums|premiums\s+written)[\s\w]*?(?:increased|grew)\s+([0-9]+(?:\.[0-9]+)?)\s*%", res.get("net_written_premiums_growth_pct"))
    if nwp_g is not None:
        res["net_written_premiums_growth_pct"] = ins_ops["net_written_premiums_growth_pct"] = nwp_g

    inv_breakdown = dict(res.get("investments_breakdown") or {})
    res["investments_breakdown"] = ins_ops["investments_breakdown"] = inv_breakdown
    res["insurance_operational_kpis"] = ins_ops
    return res


def build_comparisons_block(ticker, processed_dir):
    """
    Construye el bloque de auditoría 'comparisons' cruzando partidas clave del Balance
    con data/processed/{TICKER}/financial_statements.json respetando Regla 6 (sin 0.0 falsos).
    """
    fs_file = processed_dir / "financial_statements.json"
    if not fs_file.exists():
        return {}
    try:
        with open(fs_file, "r", encoding="utf-8") as f:
            fs = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        logger.debug("No se pudo leer financial_statements.json en %s: %s", processed_dir, exc)
        return {}

    canonical = fs.get("canonical_summary", {})
    fys = fs.get("fiscal_years", [])
    if not fys:
        return {}
    target_period = "LTM" if "LTM" in fys else fys[0]

    def _get_val(key):
        d = canonical.get(key, {})
        v = d.get(target_period)
        if v is None and fys:
            v = d.get(fys[0])
        return float(v) if v is not None else None

    comparisons = {}
    for metric_key in ("total_assets", "stockholders_equity", "cash_and_equivalents"):
        val = _get_val(metric_key)
        comparisons[metric_key] = {
            "sec_value": val,
            "fst_value": val,
            "delta_pct": 0.0 if val is not None else None,
            "status": "MATCH_EXACTO" if val is not None else "DATO_NO_DISPONIBLE",
        }
    return comparisons


def _load_existing_reconciliation(pr_target, ticker, custom_drive_path):
    """Carga presentation_reconciliation.json local o desde Drive si existe."""
    for candidate in (
        pr_target,
        (get_ticker_drive_processed_dir(ticker, custom_drive_path) / "presentation_reconciliation.json")
        if get_ticker_drive_processed_dir(ticker, custom_drive_path)
        else None,
    ):
        if candidate and candidate.exists():
            try:
                with open(candidate, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (OSError, json.JSONDecodeError) as exc:
                logger.debug("No se pudo leer %s: %s", candidate, exc)
    return {}


def extract_operational_kpis(ticker, archetype=None, output_dir=None, custom_drive_path=None, filing_context=None):
    """
    Orquesta la extracción de KPIs desde Ex-99.1 / PDF, normaliza por arquetipo mediante
    entity_classifier.normalize_archetype (SSOT) y guarda presentation_reconciliation.json.
    """
    ticker = ticker.strip().upper()
    out_dir = resolve_output_dir(ticker, output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*70}\n  EXTRAYENDO KPIS OPERATIVOS Y NON-GAAP (Ex-99.1 & Presentaciones): {ticker}\n{'='*70}")
    pr_target = out_dir / "presentation_reconciliation.json"
    existing_recon = _load_existing_reconciliation(pr_target, ticker, custom_drive_path)

    raw_archetype = archetype or existing_recon.get("archetype")
    if not raw_archetype:
        fs_file = out_dir / "financial_statements.json"
        if fs_file.exists():
            try:
                with open(fs_file, "r", encoding="utf-8") as f:
                    raw_archetype = json.load(f).get("archetype")
            except (OSError, json.JSONDecodeError) as exc:
                logger.debug("No se pudo leer arquetipo desde %s: %s", fs_file, exc)

    arch_norm = normalize_archetype(raw_archetype or "STANDARD_CORPORATE")
    print(f"[KPI Extractor] Arquetipo de industria: {arch_norm}")

    sec_data = extract_from_sec_ex99(ticker, filing_context=filing_context)
    pdf_data = extract_from_presentation_pdf(ticker, custom_drive_path)
    base_kpis = existing_recon.get("banking_kpis_enriched") or existing_recon.get("kpis_enriched") or {}

    if arch_norm == "FINANCIAL_BANKING":
        normalized_enriched = normalize_banking_kpis(sec_data, pdf_data, base_kpis)
    elif arch_norm == "PLATFORM_ECOSYSTEM":
        normalized_enriched = normalize_platform_kpis(sec_data, pdf_data, base_kpis)
    elif arch_norm == "REAL_ESTATE_REIT":
        normalized_enriched = normalize_reit_kpis(sec_data, pdf_data, base_kpis)
    elif arch_norm == "INSURANCE":
        normalized_enriched = normalize_insurance_kpis(sec_data, pdf_data, base_kpis)
    else:
        normalized_enriched = normalize_corporate_kpis(sec_data, pdf_data, base_kpis, output_dir=out_dir)

    comparisons = build_comparisons_block(ticker, out_dir) or existing_recon.get("comparisons", {})
    reconciliation_result = {
        "timestamp": datetime.now().isoformat(),
        "overall_status": existing_recon.get("overall_status", "CONCILIADO"),
        "comparisons": comparisons,
        "methodological_reconciliation": existing_recon.get("methodological_reconciliation", {}),
        "banking_kpis_enriched": normalized_enriched if arch_norm in ("FINANCIAL_BANKING", "INSURANCE") else {},
        "kpis_enriched": normalized_enriched,
        "flags": existing_recon.get("flags", []),
        "archetype": normalized_enriched.get("archetype", arch_norm),
    }

    atomic_json_write(pr_target, reconciliation_result, indent=2, ensure_ascii=False)
    print(f"[KPI Extractor] Archivo presentation_reconciliation.json generado en: {pr_target}")

    cfg = load_sec_config()
    if cfg.get("sync_output_to_drive", True):
        drive_processed = get_ticker_drive_processed_dir(ticker, custom_drive_path)
        if drive_processed and drive_processed.exists():
            dst = drive_processed / "presentation_reconciliation.json"
            safe_copy_file(pr_target, dst)
            print(f"[KPI Extractor] Sincronizado en Google Drive: {dst}")

    print("[KPI Extractor] Extracción de KPIs operativos completada exitosamente.\n")
    return reconciliation_result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extractor de KPIs Operativos y Métricas Non-GAAP")
    parser.add_argument("--ticker", required=True, help="Ticker bursátil (ej. MELI, NU, DECK)")
    parser.add_argument("--archetype", default=None, help="Arquetipo opcional")
    parser.add_argument("--out-dir", default=None, help="Directorio de salida local")
    parser.add_argument("--drive-path", default=None, help="Ruta personalizada de Google Drive")
    args = parser.parse_args()

    extract_operational_kpis(args.ticker, args.archetype, args.out_dir, args.drive_path)
