"""
sec_freshness.py - Motor Canónico de Detección de Frescura y Nuevos Períodos en SEC EDGAR.

Compara la información de estados financieros locales en data/processed/{TICKER}/ contra
las últimas presentaciones oficiales disponibles en SEC EDGAR:
1. Reportes Periódicos Auditables: Form 10-K, 10-Q, 20-F (y Form 6-K exclusivamente con XBRL / tablas contables).
2. Eventos Relevantes de Resultados: Form 8-K con Item 2.02 (Results of Operations and Financial Condition).
"""

import os
import re
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List

try:
    from edgar import Company, set_identity
except ImportError:
    Company = None
    set_identity = None

try:
    from ..sec_config import load_sec_config
except ImportError:
    try:
        from pipeline.sec_config import load_sec_config
    except ImportError:
        def load_sec_config():
            return {"sec_identity": "Pablo Inversiones pablo_inversiones@gmail.com"}

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data" / "processed"


def derive_period_label(form: str, report_date_str: str, filing_date_str: str = "") -> str:
    """
    Deriva una etiqueta representativa del período (ej. 'Q3 2026', 'FY2025')
    a partir del tipo de formulario y las fechas de reporte / presentación.
    """
    form_u = (form or "").upper().strip()
    rd = str(report_date_str or "").strip()
    fd = str(filing_date_str or "").strip()
    
    date_to_use = rd if (rd and rd != "None") else fd
    if not date_to_use or len(date_to_use) < 7:
        return form_u or "LTM"
        
    try:
        year = int(date_to_use[:4])
        month = int(date_to_use[5:7])
    except (ValueError, TypeError):
        return form_u or "LTM"
        
    if "10-K" in form_u or "20-F" in form_u:
        return f"FY{year}"
    elif "10-Q" in form_u or "6-K" in form_u:
        if month in (1, 2, 3, 4):
            return f"Q1 {year}"
        elif month in (5, 6, 7):
            return f"Q2 {year}"
        elif month in (8, 9, 10):
            return f"Q3 {year}"
        else:
            return f"Q4 {year}"
    return f"{form_u} {date_to_use[:7]}"


def get_local_sec_metadata(ticker: str, processed_dir: Optional[Path] = None) -> Dict[str, Any]:
    """
    Obtiene los metadatos de presentación SEC almacenados localmente para un ticker.
    Incluye retrocompatibilidad total (Salvaguarda 1) con archivos legacy sin bloque sec_metadata.
    """
    t = ticker.strip().upper()
    p_dir = processed_dir or (DATA_DIR / t)
    fs_file = p_dir / "financial_statements.json"
    sn_file = p_dir / "sec_narrative.json"

    result = {
        "ticker": t,
        "has_local_data": False,
        "ltm_period": "LTM",
        "ltm_period_end": None,
        "latest_periodic_form": None,
        "latest_periodic_date": None,
        "latest_periodic_accession": None,
        "latest_8k_earnings_date": None,
        "extraction_timestamp": None,
        "is_fallback": True
    }

    if not fs_file.exists():
        return result

    try:
        with open(fs_file, "r", encoding="utf-8") as f:
            fs_data = json.load(f)
    except Exception:
        return result

    result["has_local_data"] = True
    ext_ts = fs_data.get("extraction_timestamp")
    result["extraction_timestamp"] = ext_ts

    # 1. Si ya cuenta con el bloque sec_metadata estructurado, usarlo directamente
    if "sec_metadata" in fs_data and isinstance(fs_data["sec_metadata"], dict):
        sm = fs_data["sec_metadata"]
        result["ltm_period"] = sm.get("ltm_period") or result["ltm_period"]
        result["ltm_period_end"] = sm.get("ltm_period_end")
        result["latest_periodic_form"] = sm.get("latest_periodic_form")
        result["latest_periodic_date"] = sm.get("latest_periodic_date")
        result["latest_periodic_accession"] = sm.get("latest_periodic_accession")
        result["latest_8k_earnings_date"] = sm.get("latest_8k_earnings_date")
        result["is_fallback"] = False
        return result

    # 2. Salvaguarda 1 (Fallback Retrocompatible sin bloquear 'N/D')
    # Buscar en sec_narrative.json para el último 10-K
    k_date = None
    k_acc = None
    if sn_file.exists():
        try:
            with open(sn_file, "r", encoding="utf-8") as snf:
                sn_data = json.load(snf)
                k_date = sn_data.get("filing_date")
                k_acc = sn_data.get("accession_number")
        except Exception:
            pass

    # Inspeccionar fiscal_years para saber cuál es el año base
    fys = fs_data.get("fiscal_years", [])
    latest_fy = fys[1] if len(fys) > 1 and fys[0] == "LTM" else (fys[0] if fys else "FY2025")

    # Si hay extraction_timestamp, derivar período estimado razonable
    if ext_ts:
        ext_date = ext_ts[:10]
        # Estimación preliminar según fecha de extracción
        m = int(ext_date[5:7]) if len(ext_date) >= 7 else 6
        y = int(ext_date[:4]) if len(ext_date) >= 4 else 2026
        if m in (1, 2, 3, 4):
            result["ltm_period"] = f"Q4 {y-1}" if m <= 2 else f"Q1 {y}"
        elif m in (5, 6, 7):
            result["ltm_period"] = f"Q1 {y}" if m <= 5 else f"Q2 {y}"
        elif m in (8, 9, 10):
            result["ltm_period"] = f"Q2 {y}" if m <= 9 else f"Q3 {y}"
        else:
            result["ltm_period"] = f"Q3 {y}"
        result["latest_periodic_date"] = ext_date
        result["latest_periodic_form"] = "10-Q"
    else:
        result["ltm_period"] = f"LTM ({latest_fy})"
        result["latest_periodic_form"] = "10-K"
        result["latest_periodic_date"] = k_date

    result["latest_periodic_accession"] = k_acc
    return result


def _is_valid_periodic_filing(f) -> bool:
    """
    Salvaguarda 2: Filtra formularios para considerar sólo reportes periódicos legítimos:
    - 10-K, 10-Q, 20-F siempre son periódicos auditables.
    - 6-K se descartan por defecto salvo que contengan XBRL o tablas contables explícitas.
    """
    form = str(getattr(f, "form", "")).upper().strip()
    if form in ("10-K", "10-Q", "20-F", "10-K/A", "10-Q/A", "20-F/A"):
        return True
    if form in ("6-K", "6-K/A"):
        is_xbrl = getattr(f, "is_xbrl", 0)
        if is_xbrl == 1:
            return True
        prim_doc = str(getattr(f, "primary_document", "")).lower()
        if any(token in prim_doc for token in ("nufs", "financial", "statement", "interim")):
            return True
        return False
    return False


def check_sec_freshness(
    ticker: str,
    force_network: bool = True,
    processed_dir: Optional[Path] = None
) -> Dict[str, Any]:
    """
    Compara las presentaciones más recientes de SEC EDGAR contra el dataset local.
    Implementa:
    - Salvaguarda 1: Retrocompatibilidad total con JSONs existentes.
    - Salvaguarda 2: Filtro de 6-K en emisores extranjeros para evitar falsos positivos.
    """
    t = ticker.strip().upper()
    local_meta = get_local_sec_metadata(t, processed_dir=processed_dir)

    response = {
        "ticker": t,
        "is_fresh": True,
        "has_newer_filing": False,
        "has_pending_8k": False,
        "local_ltm_period": local_meta.get("ltm_period") or "LTM",
        "local_period_end": local_meta.get("ltm_period_end"),
        "local_filing_date": local_meta.get("latest_periodic_date"),
        "local_filing_form": local_meta.get("latest_periodic_form") or "10-Q",
        "local_accession": local_meta.get("latest_periodic_accession"),
        "sec_latest_period": None,
        "sec_latest_period_end": None,
        "sec_latest_filing_date": None,
        "sec_latest_form": None,
        "sec_latest_accession": None,
        "latest_8k_date": None,
        "latest_8k_items": None,
        "status": "UP_TO_DATE",
        "checked_at": datetime.now().isoformat(),
        "error": None
    }

    if not force_network or Company is None:
        return response

    try:
        cfg = load_sec_config()
        if set_identity:
            set_identity(cfg.get("sec_identity", "Pablo Inversiones pablo_inversiones@gmail.com"))

        c = Company(t)
        
        # 1. Obtener reportes periódicos (10-K, 10-Q, 20-F, 6-K filtrados)
        f_periodic = c.get_filings(form=["10-K", "10-Q", "20-F", "6-K"])
        valid_filings = []
        for f in f_periodic[:15]:
            if _is_valid_periodic_filing(f):
                valid_filings.append(f)

        latest_sec = valid_filings[0] if valid_filings else None
        
        if latest_sec:
            sec_form = str(latest_sec.form).strip()
            sec_filed = str(latest_sec.filing_date).strip()
            sec_rep = str(getattr(latest_sec, "report_date", "") or "").strip()
            sec_acc = str(latest_sec.accession_number).strip()
            sec_period = derive_period_label(sec_form, sec_rep, sec_filed)

            response["sec_latest_period"] = sec_period
            response["sec_latest_period_end"] = sec_rep if sec_rep and sec_rep != "None" else None
            response["sec_latest_filing_date"] = sec_filed
            response["sec_latest_form"] = sec_form
            response["sec_latest_accession"] = sec_acc

            # Determinar filing local exacto
            loc_acc = local_meta.get("latest_periodic_accession")
            loc_date = local_meta.get("latest_periodic_date")
            ext_ts = local_meta.get("extraction_timestamp", "")
            ext_cutoff = ext_ts[:10] if ext_ts else (loc_date or "2099-12-31")

            # Si es fallback sin sec_metadata guardado, buscar cuál era el último filing disponible a la fecha de extracción
            if local_meta.get("is_fallback"):
                cand_local = [f for f in valid_filings if str(f.filing_date) <= ext_cutoff]
                if cand_local:
                    loc_f = cand_local[0]
                    loc_form = str(loc_f.form).strip()
                    loc_filed = str(loc_f.filing_date).strip()
                    loc_rep = str(getattr(loc_f, "report_date", "") or "").strip()
                    loc_acc = str(loc_f.accession_number).strip()
                    loc_period = derive_period_label(loc_form, loc_rep, loc_filed)

                    response["local_ltm_period"] = loc_period
                    response["local_period_end"] = loc_rep if loc_rep and loc_rep != "None" else None
                    response["local_filing_date"] = loc_filed
                    response["local_filing_form"] = loc_form
                    response["local_accession"] = loc_acc

            # Comparación de frescura
            if loc_acc:
                if sec_acc != loc_acc and sec_filed > (response["local_filing_date"] or ""):
                    response["has_newer_filing"] = True
                    response["is_fresh"] = False
                    response["status"] = "NEW_PERIODIC_AVAILABLE"
            elif sec_filed > (response["local_filing_date"] or ""):
                response["has_newer_filing"] = True
                response["is_fresh"] = False
                response["status"] = "NEW_PERIODIC_AVAILABLE"

        # 2. Consultar Form 8-K con Item 2.02 (Resultados de Operaciones y Situación Financiera)
        f_8k = c.get_filings(form=["8-K"])
        latest_8k_202 = None
        for f in f_8k[:8]:
            items = str(getattr(f, "items", "") or "")
            if "2.02" in items:
                latest_8k_202 = f
                break

        if latest_8k_202:
            k8_date = str(latest_8k_202.filing_date).strip()
            k8_items = str(getattr(latest_8k_202, "items", ""))
            response["latest_8k_date"] = k8_date
            response["latest_8k_items"] = k8_items

            # Advertir si el 8-K es posterior al reporte periódico local
            local_date_ref = response["local_filing_date"] or ""
            if k8_date > local_date_ref:
                response["has_pending_8k"] = True
                if response["status"] == "UP_TO_DATE":
                    response["status"] = "PENDING_8K_EARNINGS"

    except Exception as exc:
        response["error"] = str(exc)
        # Mantener los metadatos locales para no romper la interfaz
        response["is_fresh"] = True

    return response
