"""
pipeline/audit_modules - Submódulos especializados de auditoría contable,
reconciliación tripartita SEC/CompanyFacts/Mercado (data_verifier) y verificación
de integridad y vigencia temporal de períodos (period_integrity).
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
