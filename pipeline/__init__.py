"""
pipeline - Paquete principal del Orquestador Universal de Análisis Fundamental.

Expone las 5 fachadas de alto nivel en `pipeline/` y extiende `__path__` y `sys.path`
con los 5 subpaquetes temáticos (`infra`, `sec_modules`, `audit_modules`,
`scoring_modules`, `valuation_modules`) para preservar 100% de retrocompatibilidad en
importaciones de paquete (`from pipeline.<mod> import ...`) e importaciones directas
(`from <mod> import ...`).
"""

import sys
from pathlib import Path

_PIPELINE_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _PIPELINE_DIR.parent
_SUBPACKAGE_NAMES = (
    "infra",
    "sec_modules",
    "audit_modules",
    "scoring_modules",
    "valuation_modules",
)


def _bootstrap_pipeline_paths() -> None:
    """Registra los 5 subpaquetes en __path__ y sys.path de forma idempotente."""
    for sub_name in _SUBPACKAGE_NAMES:
        sub_dir = _PIPELINE_DIR / sub_name
        if sub_dir.exists():
            sub_str = str(sub_dir)
            if sub_str not in __path__:
                __path__.append(sub_str)

    for path_entry in (
        _PROJECT_ROOT,
        _PIPELINE_DIR,
        *(_PIPELINE_DIR / sub_name for sub_name in _SUBPACKAGE_NAMES),
    ):
        if path_entry.exists():
            entry_str = str(path_entry)
            if entry_str not in sys.path:
                sys.path.insert(0, entry_str)


_bootstrap_pipeline_paths()
