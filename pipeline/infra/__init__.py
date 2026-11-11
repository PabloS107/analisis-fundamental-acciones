"""
pipeline/infra - Subpaquete transversal de infraestructura del pipeline:
configuración SSOT (config_loader), escritura atómica JSON (json_io), control de
tasa SEC EDGAR (sec_rate_limiter) y sincronización con Google Drive (drive_manager,
sync_to_drive).
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
