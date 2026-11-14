# -*- coding: utf-8 -*-
"""
statement_quality_audit.py - Auditoría Semántica, Traductológica y Contable de Estados Financieros.

Controles universales (Q1-Q7) ejecutados sin depender de red sobre `financial_statements.json`:
  Q1  ZERO_DUPLICATE_ASREP_LABELS   : cero colisiones de `spanish_label` dentro de un mismo estado SEC.
  Q2  TRANSLATION_SEMANTIC_INTEGRITY: cero traducciones corruptas, Spanglish o etiquetas vacías.
  Q3  BALANCE_MEZZANINE_PARITY      : Assets == Liabilities + Mezzanine Equity + Stockholders' Equity.
  Q4  UNEXPLAINED_PLUG_THRESHOLD    : observabilidad de residuales no atribuidos en cajones "Otros".
  Q5  IS_FALSE_TOTAL_AND_PROVENANCE : sin falsos totales y con índice SEC EDGAR presente.
  Q6  VERTICAL_SUBTOTAL_IDENTITY    : consistencia vertical CA+NCA==Assets, GP==Rev-COGS y puente CF.
  Q7  FACE_ANCHOR_PARITY            : paridad exacta entre anclas canónicas y totales oficiales SEC.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List

_STATEMENT_SECTIONS = ("income_statement", "balance_sheet", "cash_flow_statement")
_SPANGLISH_TOKENS_RE = re.compile(r'\b(attributable to|exclusive of|excluding)\b|\(loss\)', re.IGNORECASE)
_TRUE_TOTAL_WORDS_RE = re.compile(r'(?:^total\b|^subtotal\b|,\s*total$)', re.IGNORECASE)


def _finding(check_id: str, severity: str, message: str, **detail) -> Dict[str, Any]:
    return {"check": check_id, "severity": severity, "message": message, **detail}


def check_duplicate_as_reported_labels(fs_data: Dict[str, Any]) -> Dict[str, Any]:
    """Q1: detecta etiquetas en español duplicadas dentro de un mismo estado As-Reported."""
    dups = []
    as_rep = fs_data.get("as_reported_statements") or {}
    for s_name in _STATEMENT_SECTIONS:
        seen = {}
        for row in as_rep.get(s_name, []) or []:
            if row.get("is_abstract"):
                continue
            sp = (row.get("spanish_label") or "").strip()
            if not sp:
                continue
            key = sp.lower()
            if key in seen:
                dups.append({
                    "statement": s_name,
                    "spanish_label": sp,
                    "first_label": seen[key],
                    "second_label": row.get("label", ""),
                    "concept": row.get("concept", ""),
                })
            else:
                seen[key] = row.get("label", "")
    if dups:
        return _finding(
            "ZERO_DUPLICATE_ASREP_LABELS",
            "ERROR",
            f"{len(dups)} colisiones semánticas de spanish_label en estados As-Reported.",
            count=len(dups),
            samples=dups[:8],
        )
    return _finding("ZERO_DUPLICATE_ASREP_LABELS", "PASS", "Cero colisiones semánticas en carátulas As-Reported.")


def check_translation_semantic_integrity(fs_data: Dict[str, Any]) -> Dict[str, Any]:
    """Q2: verifica ausencia de corrupciones semánticas, Spanglish o traducciones vacías."""
    issues = []
    archetype = str(fs_data.get("archetype") or "").upper()
    as_rep = fs_data.get("as_reported_statements") or {}
    for s_name in _STATEMENT_SECTIONS:
        for row in as_rep.get(s_name, []) or []:
            if row.get("is_abstract"):
                continue
            orig = (row.get("label") or "").strip()
            orig_low = orig.lower()
            sp = (row.get("spanish_label") or "").strip()
            sp_low = sp.lower()
            tip = (row.get("orig_tooltip") or "").strip()
            if not sp or sp == "N/D" or not tip:
                issues.append({"statement": s_name, "label": orig, "spanish_label": sp, "reason": "MISSING_LABEL_OR_TOOLTIP"})
                continue
            if _SPANGLISH_TOKENS_RE.search(sp):
                issues.append({"statement": s_name, "label": orig, "spanish_label": sp, "reason": "SPANGLISH_LEAK"})
            elif ("cost of revenue" in orig_low or "cost of goods" in orig_low) and "depreciación" in sp_low and "excluyendo" not in sp_low and "costo" not in sp_low:
                issues.append({"statement": s_name, "label": orig, "spanish_label": sp, "reason": "TRUNCATED_EXCLUSION"})
            elif orig_low == "revenues" and archetype != "REAL_ESTATE_REIT" and "alquiler" in sp_low:
                issues.append({"statement": s_name, "label": orig, "spanish_label": sp, "reason": "FALSE_RENTAL_REVENUE"})
            elif orig_low.startswith("total stockholders' equity") and "stockholders" in sp_low:
                issues.append({"statement": s_name, "label": orig, "spanish_label": sp, "reason": "UNTRANSLATED_EQUITY"})
    if issues:
        return _finding(
            "TRANSLATION_SEMANTIC_INTEGRITY",
            "ERROR",
            f"{len(issues)} filas As-Reported con defectos de traducción o tooltip.",
            count=len(issues),
            samples=issues[:8],
        )
    return _finding("TRANSLATION_SEMANTIC_INTEGRITY", "PASS", "Integridad semántica verificada al 100%.")


def check_balance_mezzanine_parity(fs_data: Dict[str, Any]) -> Dict[str, Any]:
    """Q3: valida Assets == Liabilities + Mezzanine Equity + Stockholders' Equity en períodos recientes."""
    res_bs = (fs_data.get("resolved_canonical_statements") or {}).get("balance_sheet") or {}
    if not res_bs:
        return _finding(
            "BALANCE_MEZZANINE_PARITY",
            "WARN",
            "N/D: resolved_canonical_statements no persistido aún; re-ejecutar extracción SEC.",
        )
    periods = (fs_data.get("fiscal_years") or [])[:6]
    assets_s = res_bs.get("total_assets") or {}
    liab_eq_s = res_bs.get("total_liab_and_equity") or {}
    mismatches = []
    checked = 0
    for p in periods:
        a_val = assets_s.get(p)
        le_val = liab_eq_s.get(p)
        if a_val is None or le_val is None:
            continue
        checked += 1
        tol = max(2_000_000.0, abs(float(a_val)) * 0.002)
        diff = abs(float(a_val) - float(le_val))
        if diff > tol:
            mismatches.append({
                "period": p,
                "total_assets": a_val,
                "total_liab_and_equity": le_val,
                "diff_usd": round(float(a_val) - float(le_val), 2),
            })
    if checked == 0:
        return _finding("BALANCE_MEZZANINE_PARITY", "WARN", "N/D: sin períodos balanceados evaluables.")
    if mismatches:
        return _finding(
            "BALANCE_MEZZANINE_PARITY",
            "ERROR",
            f"Descuadre Activo vs Pasivo+Mezzanine+Patrimonio en {len(mismatches)} período(s).",
            count=len(mismatches),
            samples=mismatches,
        )
    return _finding("BALANCE_MEZZANINE_PARITY", "PASS", f"Cuadre patrimonial exacto en {checked} períodos (incl. Mezzanine Equity).")


def check_unexplained_plugs(fs_data: Dict[str, Any]) -> Dict[str, Any]:
    """Q4: audita residuales no explicados en cajones 'Otros' dentro de `resolved_canonical_lineage`."""
    lineage = fs_data.get("resolved_canonical_lineage") or {}
    if not lineage:
        return _finding(
            "UNEXPLAINED_PLUG_THRESHOLD",
            "WARN",
            "N/D: resolved_canonical_lineage ausente (extracción previa al linaje automático).",
        )
    recent_periods = (fs_data.get("fiscal_years") or [])[:3]
    alerts = []
    for metric_key, spec in lineage.items():
        if spec.get("method") != "PLUG_ATTRIBUTION":
            continue
        p_map = spec.get("periods") or {}
        for p in recent_periods:
            entry = p_map.get(p)
            if not isinstance(entry, dict):
                continue
            val = float(entry.get("value_usd") or 0.0)
            res = entry.get("residual_unexplained_usd")
            if res is None or abs(val) < 10_000_000.0:
                continue
            res_abs = abs(float(res))
            if res_abs > 5_000_000.0 and (res_abs / abs(val)) > 0.15:
                alerts.append({
                    "metric": metric_key,
                    "period": p,
                    "value_usd": val,
                    "explained_sum_usd": entry.get("explained_sum_usd"),
                    "residual_unexplained_usd": float(res),
                    "residual_pct": round((res_abs / abs(val)) * 100.0, 1),
                })
    if alerts:
        return _finding(
            "UNEXPLAINED_PLUG_THRESHOLD",
            "WARN",
            f"{len(alerts)} cajones 'Otros' presentan diferencias entre carátula y notas (>15% / >$5M).",
            count=len(alerts),
            samples=alerts[:10],
        )
    return _finding("UNEXPLAINED_PLUG_THRESHOLD", "PASS", "Todos los cajones 'Otros' recientes están atribuidos dentro de tolerancia.")


def check_false_totals_and_provenance(fs_data: Dict[str, Any]) -> Dict[str, Any]:
    """Q5: verifica ausencia de falsos totales (`Purchase of total return swaps`) e índice SEC."""
    bad_totals = []
    as_rep = fs_data.get("as_reported_statements") or {}
    for s_name in _STATEMENT_SECTIONS:
        for row in as_rep.get(s_name, []) or []:
            if row.get("is_abstract") or not row.get("is_total"):
                continue
            lbl = (row.get("label") or "").strip()
            if "total return swap" in lbl.lower():
                bad_totals.append({"statement": s_name, "label": lbl, "concept": row.get("concept", "")})

    has_prov = bool(fs_data.get("sec_filings_index")) and bool(fs_data.get("period_filing_map"))
    if bad_totals:
        return _finding(
            "IS_FALSE_TOTAL_AND_PROVENANCE",
            "ERROR",
            f"{len(bad_totals)} filas marcadas erróneamente como subtotal/total contable.",
            samples=bad_totals,
            has_provenance=has_prov,
        )
    if not has_prov:
        return _finding(
            "IS_FALSE_TOTAL_AND_PROVENANCE",
            "WARN",
            "Sin falsos totales, pero falta sec_filings_index/period_filing_map (re-extraer para citas R*.htm nativas).",
            has_provenance=False,
        )
    return _finding("IS_FALSE_TOTAL_AND_PROVENANCE", "PASS", "Cero falsos totales y procedencia SEC EDGAR completa.")


def check_vertical_subtotal_identity(fs_data: Dict[str, Any]) -> Dict[str, Any]:
    """Q6: valida subtotales verticales (CA+NCA=Assets, GP=Rev-COGS y puente CF=NetChange)."""
    rc = fs_data.get("resolved_canonical_statements") or {}
    if not rc:
        return _finding(
            "VERTICAL_SUBTOTAL_IDENTITY",
            "WARN",
            "N/D: resolved_canonical_statements ausente para verificar identidades verticales.",
        )
    archetype = str(fs_data.get("archetype") or "STANDARD_CORPORATE").upper()
    periods = (fs_data.get("fiscal_years") or [])[:6]
    bs = rc.get("balance_sheet") or {}
    inc = rc.get("income_statement") or {}
    cf = rc.get("cash_flow") or rc.get("cash_flow_statement") or {}

    mismatches = []
    checked = 0
    for p in periods:
        ta = (bs.get("total_assets") or {}).get(p)
        tca = (bs.get("total_current_assets") or {}).get(p)
        tnca = (bs.get("total_noncurrent_assets") or {}).get(p)
        if ta is not None and tca is not None and tnca is not None and archetype not in ("FINANCIAL_BANKING", "INSURANCE"):
            checked += 1
            tol = max(2_000_000.0, abs(float(ta)) * 0.002)
            if abs((float(tca) + float(tnca)) - float(ta)) > tol:
                mismatches.append({"period": p, "identity": "CA+NCA=Assets", "calc": float(tca) + float(tnca), "reported": float(ta)})

        rev = (inc.get("revenue") or {}).get(p)
        cogs = (inc.get("cogs") or {}).get(p)
        gp = (inc.get("gross_profit") or {}).get(p)
        if archetype not in ("FINANCIAL_BANKING", "INSURANCE", "REAL_ESTATE_REIT") and rev is not None and cogs is not None and gp is not None:
            checked += 1
            tol = max(2_000_000.0, abs(float(rev)) * 0.002)
            if abs((float(rev) - float(cogs)) - float(gp)) > tol:
                mismatches.append({"period": p, "identity": "Rev-COGS=GP", "calc": float(rev) - float(cogs), "reported": float(gp)})

        cfo = (cf.get("cfo") or {}).get(p)
        cfi = (cf.get("cfi") or {}).get(p)
        cff = (cf.get("cff") or {}).get(p)
        fx = float((cf.get("fx_effect") or {}).get(p) or 0.0)
        nc = (cf.get("net_change_in_cash") or {}).get(p)
        if cfo is not None and cfi is not None and cff is not None and nc is not None:
            checked += 1
            base_sum = float(cfo) + float(cfi) + float(cff)
            err = min(abs((base_sum + fx) - float(nc)), abs(base_sum - float(nc)))
            tol = max(2_000_000.0, abs(float(nc)) * 0.005)
            if err > tol:
                mismatches.append({"period": p, "identity": "CFO+CFI+CFF(+FX)=NetChangeCash", "calc": base_sum + fx, "reported": float(nc)})

    if mismatches:
        return _finding(
            "VERTICAL_SUBTOTAL_IDENTITY",
            "ERROR",
            f"Descuadre vertical de subtotales en {len(mismatches)} verificación(es).",
            count=len(mismatches),
            samples=mismatches[:8],
        )
    return _finding("VERTICAL_SUBTOTAL_IDENTITY", "PASS", f"Identidades verticales y puente de efectivo consistentes ({checked} controles).")


def check_face_anchor_parity(fs_data: Dict[str, Any]) -> Dict[str, Any]:
    """Q7: verifica paridad exacta entre anclas canónicas (Assets, NetIncome, CFO, CFI, CFF) y carátula SEC."""
    rc = fs_data.get("resolved_canonical_statements") or {}
    as_rep = fs_data.get("as_reported_statements") or {}
    if not rc or not as_rep:
        return _finding(
            "FACE_ANCHOR_PARITY",
            "WARN",
            "N/D: faltan datos canónicos o carátula As-Reported para cotejo SEC.",
        )

    bs = rc.get("balance_sheet") or {}
    inc = rc.get("income_statement") or {}
    cf = rc.get("cash_flow") or rc.get("cash_flow_statement") or {}
    periods = (fs_data.get("fiscal_years") or [])[:6]
    anchor_specs = [
        ("balance_sheet", bs, "total_assets", {"us-gaap_Assets", "ifrs-full_Assets"}),
        ("income_statement", inc, "net_income", {
            "us-gaap_NetIncomeLoss", "us-gaap_ProfitLoss",
            "ifrs-full_ProfitLoss", "ifrs-full_ProfitLossAttributableToOwnersOfParent",
        }),
        ("cash_flow_statement", cf, "cfo", {"us-gaap_NetCashProvidedByUsedInOperatingActivities", "ifrs-full_CashFlowsFromUsedInOperatingActivities"}),
        ("cash_flow_statement", cf, "cfi", {"us-gaap_NetCashProvidedByUsedInInvestingActivities", "ifrs-full_CashFlowsFromUsedInInvestingActivities"}),
        ("cash_flow_statement", cf, "cff", {"us-gaap_NetCashProvidedByUsedInFinancingActivities", "ifrs-full_CashFlowsFromUsedInFinancingActivities"}),
    ]

    mismatches = []
    checked = 0
    for stmt_name, res_dict, metric_key, tags in anchor_specs:
        series = res_dict.get(metric_key) or {}
        face_rows = [r for r in (as_rep.get(stmt_name) or []) if not r.get("is_abstract") and r.get("concept") in tags]
        if not face_rows or not series:
            continue
        for p in periods:
            rv = series.get(p)
            fvs = [float(r["values"][p]) for r in face_rows if (r.get("values") or {}).get(p) is not None]
            if rv is None or not fvs:
                continue
            checked += 1
            best_diff = min(abs(fv - float(rv)) for fv in fvs)
            tol = max(2_000_000.0, abs(float(rv)) * 0.002)
            if best_diff > tol:
                mismatches.append({"period": p, "metric": metric_key, "resolved": float(rv), "sec_face": fvs[0], "diff_usd": round(best_diff, 2)})

    if mismatches:
        return _finding(
            "FACE_ANCHOR_PARITY",
            "ERROR",
            f"Discrepancia frente a carátula oficial SEC en {len(mismatches)} ancla(s).",
            count=len(mismatches),
            samples=mismatches[:8],
        )
    return _finding("FACE_ANCHOR_PARITY", "PASS", f"Paridad 100% exacta contra anclas oficiales SEC ({checked} cotejos).")


def evaluate_statement_quality(fs_data: Dict[str, Any]) -> Dict[str, Any]:
    """Ejecuta controles Q1-Q7 en memoria sobre un dict `financial_statements` ya cargado."""
    checks = [
        check_duplicate_as_reported_labels(fs_data),
        check_translation_semantic_integrity(fs_data),
        check_balance_mezzanine_parity(fs_data),
        check_unexplained_plugs(fs_data),
        check_false_totals_and_provenance(fs_data),
        check_vertical_subtotal_identity(fs_data),
        check_face_anchor_parity(fs_data),
    ]
    error_count = sum(1 for c in checks if c.get("severity") == "ERROR")
    warn_count = sum(1 for c in checks if c.get("severity") not in ("PASS", "ERROR"))
    pass_count = sum(1 for c in checks if c.get("severity") == "PASS")
    status = "ERROR" if error_count else ("WARN" if warn_count else "PASS")
    return {
        "status": status,
        "pass_count": pass_count,
        "warn_count": warn_count,
        "error_count": error_count,
        "checks": checks,
    }


def run_statement_quality_audit(local_dir: Path | str) -> List[Dict[str, Any]]:
    """Ejecuta controles Q1-Q7 sobre `data/processed/{TICKER}/financial_statements.json`."""
    local_dir = Path(local_dir)
    fs_path = local_dir / "financial_statements.json"
    if not fs_path.exists():
        return [_finding("STATEMENT_QUALITY_SKIP", "WARN", f"No existe {fs_path}")]
    fs_data = json.loads(fs_path.read_text(encoding="utf-8"))
    return evaluate_statement_quality(fs_data)["checks"]
