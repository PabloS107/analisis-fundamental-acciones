# -*- coding: utf-8 -*-
"""
Utilidades compartidas y Fuente Única de Verdad (SSOT) para el paquete analytics.views.
Centraliza rutas, clasificación de arquetipos, conversión explícita de unidades y búsqueda en CF.
"""
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
PIPELINE_DIR = PROJECT_ROOT / "pipeline"
for _p_dir in (PROJECT_ROOT, PIPELINE_DIR):
    if _p_dir.exists() and str(_p_dir) not in sys.path:
        sys.path.insert(0, str(_p_dir))

from pipeline.config_loader import (  # noqa: E402
    DATA_CACHE_DIR,
    DATA_PROCESSED_DIR,
    DRIVE_INPUT_DIR,
    resolve_market_cache_path,
)
from pipeline.entity_classifier import (  # noqa: E402
    CANONICAL_ARCHETYPES,
    detect_company_archetype,
    normalize_archetype,
)

DATA_DIR = DATA_PROCESSED_DIR
logger = logging.getLogger("analytics.views")


def first_present(*values: Any) -> Any:
    """Retorna el primer valor no nulo, preservando 0 y 0.0 contables."""
    for v in values:
        if v is not None:
            return v
    return None


def safe_float(val: Any) -> Optional[float]:
    """Convierte un escalar a float de forma segura; retorna None si es inválido o nulo."""
    if val is None or isinstance(val, bool):
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def usd_to_m(val: Any) -> Optional[float]:
    """Convierte USD crudos (estados SEC/canónicos) a millones ($M), preservando None."""
    num = safe_float(val)
    return round(num / 1e6, 1) if num is not None else None


def already_m(val: Any) -> Optional[float]:
    """Formatea un valor ya expresado en $M (p. ej. scoring JSON) sin reescalado heurístico."""
    num = safe_float(val)
    return round(num, 1) if num is not None else None


def pct_from_key_ratio(val: Any) -> Optional[float]:
    """Convierte ratios de key_ratios (ya expresados en % 0-100, p. ej. 0.86%) sin multiplicar <=1."""
    num = safe_float(val)
    return round(num, 2) if num is not None else None


def ratio_to_pct(val: Any, decimal_threshold: float = 1.5) -> Optional[float]:
    """Convierte ratios de scoring (donde fracciones <= decimal_threshold están en 0-1) a %."""
    num = safe_float(val)
    if num is None:
        return None
    return (num * 100.0) if abs(num) <= decimal_threshold else num


def fmt_money_m(m_val: Optional[float]) -> str:
    """Formatea un monto ya expresado en $M o retorna '-' si es None."""
    if m_val is None:
        return "-"
    if m_val == 0.0:
        return "$0.0M"
    prefix = "-$" if m_val < 0 else "$"
    return f"{prefix}{abs(m_val):,.1f}M"


def resolve_company_archetype(
    fs_data: Optional[Dict[str, Any]] = None,
    scores_data: Optional[Dict[str, Any]] = None,
    ticker: Optional[str] = None,
) -> str:
    """Resuelve el arquetipo canónico delegando en entity_classifier SSOT."""
    fs_obj = fs_data or {}
    sc_obj = scores_data or {}

    raw_arch = fs_obj.get("archetype") or sc_obj.get("archetype")
    if raw_arch:
        norm = normalize_archetype(raw_arch)
        if norm in CANONICAL_ARCHETYPES:
            return norm

    sic_code = fs_obj.get("sic_code") or sc_obj.get("sic_code")
    if fs_obj.get("income_statement_detail") or fs_obj.get("balance_sheet_detail") or sic_code:
        detected = detect_company_archetype(
            company=ticker or sc_obj.get("company_name") or fs_obj.get("company_name"),
            sic_code=sic_code,
            income_data=fs_obj.get("income_statement_detail"),
            balance_data=fs_obj.get("balance_sheet_detail"),
        )
        if detected in CANONICAL_ARCHETYPES:
            return detected

    if fs_obj.get("is_financial") or sc_obj.get("is_financial_institution"):
        return "FINANCIAL_BANKING"
    return "STANDARD_CORPORATE"


def build_chart_periods(
    fys: List[str],
    canonical: Dict[str, Any],
    drop_duplicate_ltm: bool = False,
    latest_form: Optional[str] = None,
) -> tuple[List[str], bool]:
    """Construye la ventana temporal cronológica de gráficos excluyendo cierres vacíos iniciales."""
    first_fy = next((p for p in fys if p != "LTM"), None)
    is_ltm_equal_latest_fy = False
    if latest_form in ("10-K", "20-F") and first_fy:
        c_rev = canonical.get("revenue", {})
        rev_ltm = c_rev.get("LTM")
        rev_fy = c_rev.get(first_fy)
        if rev_ltm is not None and rev_fy is not None and abs(float(rev_ltm) - float(rev_fy)) < 1.0:
            is_ltm_equal_latest_fy = True

    raw_chart_periods = list(reversed(fys))
    if drop_duplicate_ltm and is_ltm_equal_latest_fy and "LTM" in raw_chart_periods:
        raw_chart_periods = [p for p in raw_chart_periods if p != "LTM"]

    valid_chart_indices = [
        idx
        for idx, p in enumerate(raw_chart_periods)
        if canonical.get("revenue", {}).get(p) is not None
        or canonical.get("net_income", {}).get(p) is not None
        or canonical.get("operating_income", {}).get(p) is not None
    ]
    chart_periods = raw_chart_periods[valid_chart_indices[0]:] if valid_chart_indices else raw_chart_periods
    return chart_periods, is_ltm_equal_latest_fy


def find_cf_detail_concept(
    cf_sources: List[Dict[str, Any]],
    candidate_keys: List[str],
    period: str,
    take_abs: bool = True,
    ignore_zero: bool = True,
) -> Optional[float]:
    """Busca un concepto en fuentes de cash_flow_detail/statement evitando bucles duplicados."""
    for cf_src in cf_sources:
        if not cf_src:
            continue
        for c_k in candidate_keys:
            c_k_lower = c_k.lower()
            for src_k, src_obj in cf_src.items():
                src_k_token = src_k.lower().split(":")[-1].split("_")[-1]
                if src_k == c_k or src_k.lower() == c_k_lower or src_k_token == c_k_lower:
                    if isinstance(src_obj, dict) and "values" in src_obj:
                        v_cand = safe_float(src_obj["values"].get(period))
                    elif isinstance(src_obj, dict):
                        v_cand = safe_float(src_obj.get(period))
                    else:
                        v_cand = None
                    if v_cand is not None and (not ignore_zero or v_cand != 0.0):
                        return abs(v_cand) if take_abs else v_cand
    return None
