"""
pipeline/valuation_modules - Submódulos cohesivos de valoración intrínseca,
Reverse DCF, Excess Return P/TBV, múltiplos históricos, Owner Earnings y Z-Score.
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

from .dcf_models import (
    _fmt_money,
    _fmt_pct,
    _compute_series_cagr,
    _compute_share_reduction_rate,
    compute_two_stage_excess_return_ptbv,
    solve_reverse_dcf,
    solve_reverse_dcf_3stage,
    calculate_dcf_details,
    calculate_epv_pvgo,
    calculate_eva_valuation,
    calculate_5y_forward_irr,
    calculate_multiples_valuation,
    calculate_owner_earnings_and_capex,
    get_valuation_football_field,
)
from .market_history import (
    calculate_z_score_valuation,
    calculate_historical_multiples_analysis,
    build_audit_traceability,
)

__all__ = [
    "_fmt_money",
    "_fmt_pct",
    "_compute_series_cagr",
    "_compute_share_reduction_rate",
    "compute_two_stage_excess_return_ptbv",
    "solve_reverse_dcf",
    "solve_reverse_dcf_3stage",
    "calculate_dcf_details",
    "calculate_epv_pvgo",
    "calculate_eva_valuation",
    "calculate_5y_forward_irr",
    "calculate_multiples_valuation",
    "calculate_owner_earnings_and_capex",
    "get_valuation_football_field",
    "calculate_z_score_valuation",
    "calculate_historical_multiples_analysis",
    "build_audit_traceability",
]
