"""
period_integrity.py - Invariantes de integridad de período y vigencia de la verificación cruzada.

Controles universales (invariantes respecto del emisor y del arquetipo) que se ejecutan sobre
`financial_statements.json` sin depender de la red:

  P1  METADATA_PRESENTE      : debe existir `sec_metadata` (procedencia del LTM).
  P2  PERIODO_NO_POSTERIOR   : `ltm_period_end` <= `latest_periodic_date` (fecha de presentación).
  P3  PERIODO_NO_FUTURO      : `ltm_period_end` <= fecha de extracción.
  P4  LTM_IGUAL_FY           : si el último periódico es anual (10-K/20-F), LTM == FY más reciente
                               en cada partida as-reported.
  P5  VERIFICACION_VIGENTE   : el reporte de verificación cruzada corresponde a la extracción actual.

Severidades: ERROR (dato inconsistente), WARN (no verificable / desactualizado), PASS.
"""

import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

LTM_FY_REL_TOLERANCE = 0.001
_STATEMENT_SECTIONS = ("income_statement", "balance_sheet", "cash_flow_statement")


def file_fingerprint(path: Path) -> Optional[str]:
    """SHA-256 del archivo, o None si no existe."""
    path = Path(path)
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _parse_date(value: Any) -> Optional[date]:
    try:
        return date.fromisoformat(str(value)[:10]) if value else None
    except ValueError:
        return None


def _finding(check_id: str, severity: str, message: str, **detail) -> Dict[str, Any]:
    return {"check": check_id, "severity": severity, "message": message, **detail}


def _latest_fiscal_year(fs_data: Dict[str, Any]) -> Optional[str]:
    return next((fy for fy in fs_data.get("fiscal_years", []) if fy != "LTM"), None)


def _check_ltm_equals_fy(fs_data: Dict[str, Any], latest_fy: str) -> List[Dict[str, Any]]:
    """P4: filas as-reported cuyo LTM difiere del FY fuente."""
    mismatches = []
    for section in _STATEMENT_SECTIONS:
        for row in fs_data.get("as_reported_statements", {}).get(section, []) or []:
            if row.get("is_abstract"):
                continue
            values = row.get("values") or {}
            ltm, fy_val = values.get("LTM"), values.get(latest_fy)
            if ltm is None or fy_val is None:
                continue
            if abs(ltm - fy_val) > max(1.0, abs(fy_val) * LTM_FY_REL_TOLERANCE):
                mismatches.append({
                    "section": section,
                    "label": row.get("label"),
                    "concept": row.get("concept"),
                    "fy_value": fy_val,
                    "ltm_value": ltm,
                })
    return mismatches


def check_period_integrity(fs_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Ejecuta P1-P4 sobre el contenido de financial_statements.json."""
    meta = fs_data.get("sec_metadata")
    if not isinstance(meta, dict) or not meta:
        return [_finding(
            "METADATA_PRESENTE", "WARN",
            "N/D: falta sec_metadata; no es posible certificar el período LTM ni su filing de origen. "
            "Re-ejecutar la extracción SEC.",
        )]

    findings = [_finding("METADATA_PRESENTE", "PASS", "sec_metadata presente.")]
    period_end = _parse_date(meta.get("ltm_period_end"))
    filed = _parse_date(meta.get("latest_periodic_date"))
    extracted = _parse_date(meta.get("extraction_timestamp") or fs_data.get("extraction_timestamp"))

    if period_end is None:
        findings.append(_finding("PERIODO_NO_POSTERIOR", "WARN", "N/D: ltm_period_end ausente en sec_metadata."))
    elif filed and period_end > filed:
        findings.append(_finding(
            "PERIODO_NO_POSTERIOR", "ERROR",
            f"El período {meta.get('ltm_period')} cierra {period_end} pero el filing se presentó {filed}.",
            ltm_period=meta.get("ltm_period"), ltm_period_end=str(period_end), filed=str(filed),
            accession=meta.get("latest_periodic_accession"),
        ))
    else:
        findings.append(_finding("PERIODO_NO_POSTERIOR", "PASS", "Cierre de período anterior o igual a la presentación."))

    if period_end and extracted and period_end > extracted:
        findings.append(_finding(
            "PERIODO_NO_FUTURO", "ERROR",
            f"El período {meta.get('ltm_period')} cierra {period_end}, posterior a la extracción ({extracted}).",
            ltm_period_end=str(period_end), extraction=str(extracted),
        ))
    else:
        findings.append(_finding("PERIODO_NO_FUTURO", "PASS", "Cierre de período no posterior a la extracción."))

    latest_fy = _latest_fiscal_year(fs_data)
    is_annual_source = str(meta.get("latest_periodic_form", "")).upper() in ("10-K", "20-F", "40-F")
    if latest_fy and is_annual_source and meta.get("ltm_period") == latest_fy:
        bad = _check_ltm_equals_fy(fs_data, latest_fy)
        if bad:
            findings.append(_finding(
                "LTM_IGUAL_FY", "ERROR",
                f"{len(bad)} partidas as-reported con LTM distinto de {latest_fy} aunque el LTM proviene del reporte anual.",
                count=len(bad), samples=bad[:10],
            ))
        else:
            findings.append(_finding("LTM_IGUAL_FY", "PASS", f"LTM coincide con {latest_fy} en todas las partidas."))
    else:
        findings.append(_finding("LTM_IGUAL_FY", "PASS", "No aplica: el LTM no proviene de un reporte anual."))
    return findings


def check_verification_freshness(local_dir: Path) -> Dict[str, Any]:
    """P5: compara el reporte de verificación cruzada contra la extracción vigente."""
    local_dir = Path(local_dir)
    report_path = local_dir / "cross_verification_report.json"
    fs_path = local_dir / "financial_statements.json"
    if not report_path.exists():
        return _finding("VERIFICACION_VIGENTE", "WARN", "N/D: no existe cross_verification_report.json.", state="MISSING")
    if not fs_path.exists():
        return _finding("VERIFICACION_VIGENTE", "WARN", "N/D: no existe financial_statements.json.", state="MISSING")

    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _finding("VERIFICACION_VIGENTE", "WARN", "Reporte de verificación ilegible.", state="STALE")

    current_fp = file_fingerprint(fs_path)
    report_fp = report.get("source_fingerprint")
    if report_fp:
        if report_fp == current_fp:
            return _finding("VERIFICACION_VIGENTE", "PASS", "Verificación corresponde a la extracción vigente.", state="CURRENT")
        return _finding(
            "VERIFICACION_VIGENTE", "WARN",
            "STALE: financial_statements.json cambió después de la verificación cruzada. Re-ejecutar data_verifier.",
            state="STALE",
        )

    # Reportes legacy sin huella: comparar fecha de verificación contra fecha de extracción.
    try:
        fs_data = json.loads(fs_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _finding("VERIFICACION_VIGENTE", "WARN", "financial_statements.json ilegible.", state="STALE")
    verified_at = _parse_date(report.get("verification_timestamp"))
    extracted_at = _parse_date((fs_data.get("sec_metadata") or {}).get("extraction_timestamp") or fs_data.get("extraction_timestamp"))
    if verified_at is None or extracted_at is None:
        return _finding(
            "VERIFICACION_VIGENTE", "WARN",
            "STALE: reporte legacy sin huella y sin fechas comparables. Re-ejecutar data_verifier.", state="STALE",
        )
    if verified_at < extracted_at:
        return _finding(
            "VERIFICACION_VIGENTE", "WARN",
            f"STALE: verificada {verified_at}, extracción posterior {extracted_at}. Re-ejecutar data_verifier.",
            state="STALE",
        )
    return _finding("VERIFICACION_VIGENTE", "WARN", "Reporte legacy sin huella; vigencia inferida solo por fecha.", state="LEGACY_UNVERIFIABLE")


def run_period_integrity(local_dir: Path) -> List[Dict[str, Any]]:
    """Ejecuta P1-P5 para el directorio data/processed/{TICKER}."""
    local_dir = Path(local_dir)
    fs_path = local_dir / "financial_statements.json"
    fs_data = json.loads(fs_path.read_text(encoding="utf-8"))
    return check_period_integrity(fs_data) + [check_verification_freshness(local_dir)]
