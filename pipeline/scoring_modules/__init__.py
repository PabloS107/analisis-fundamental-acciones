"""
pipeline/scoring_modules - Submódulos cuantitativos cohesivos para scoring fundamental,
productividad del capital, auditoría forense y análisis de solvencia/crédito.
"""

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
