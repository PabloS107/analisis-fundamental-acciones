"""
pipeline/scoring_modules - Submódulos cuantitativos cohesivos para scoring fundamental,
productividad del capital, auditoría forense y análisis de solvencia/crédito.
"""

import sys as _sys
from pathlib import Path as _Path

_PIPELINE_DIR = _Path(__file__).resolve().parent.parent
_PROJECT_ROOT = _PIPELINE_DIR.parent
for _p in (
    _PROJECT_ROOT,
    _PIPELINE_DIR,
    *(_PIPELINE_DIR / _s for _s in ("infra", "sec_modules", "audit_modules", "scoring_modules", "valuation_modules")),
):
    if _p.exists() and str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))

from .scoring_utils import (
    normalize_archetype,
    _safe_float,
    _to_millions,
    _clean_sic_code,
    load_industry_medians,
    load_peer_benchmarks,
    compute_peer_benchmarks,
    get_sector_benchmarks,
    extract_period_metrics,
)
from .piotroski_mohanram import (
    PiotroskiScoreCalculator,
    MohanramScoreCalculator,
    CombinedMatrixClassifier,
)
from .profitability_capital import (
    NovyMarxCalculator,
    IntangibleROICCalculator,
    GreenblattROCCalculator,
    WACCCalculator,
)
from .forensic_accounting import ForensicAccountingEngine
from .solvency_credit import DebtSolvencyEngine

__all__ = [
    "normalize_archetype",
    "_safe_float",
    "_to_millions",
    "_clean_sic_code",
    "load_industry_medians",
    "load_peer_benchmarks",
    "compute_peer_benchmarks",
    "get_sector_benchmarks",
    "extract_period_metrics",
    "PiotroskiScoreCalculator",
    "MohanramScoreCalculator",
    "CombinedMatrixClassifier",
    "NovyMarxCalculator",
    "IntangibleROICCalculator",
    "GreenblattROCCalculator",
    "WACCCalculator",
    "ForensicAccountingEngine",
    "DebtSolvencyEngine",
]
