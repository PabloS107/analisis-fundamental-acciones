"""Paquete raíz de pruebas automatizadas del Orquestador Universal."""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PIPELINE_DIR = PROJECT_ROOT / "pipeline"
WEB_DASHBOARD_DIR = PROJECT_ROOT / "web_dashboard"

_SYS_PATHS = [
    PROJECT_ROOT,
    PIPELINE_DIR,
    PIPELINE_DIR / "infra",
    PIPELINE_DIR / "sec_modules",
    PIPELINE_DIR / "audit_modules",
    PIPELINE_DIR / "scoring_modules",
    PIPELINE_DIR / "valuation_modules",
    WEB_DASHBOARD_DIR,
]

for _path in reversed(_SYS_PATHS):
    _path_str = str(_path)
    if _path_str not in sys.path:
        sys.path.insert(0, _path_str)

import pipeline  # noqa: E402, F401
import web_dashboard as _web_pkg  # noqa: E402

# Evita colisión de nombres entre el proyecto Django (`web_dashboard/web_dashboard`)
# y el subpaquete de pruebas (`tests/web_dashboard`) al usar `unittest discover -s tests`.
for _web_pkg_path in (
    str(WEB_DASHBOARD_DIR / "web_dashboard"),
    str(Path(__file__).resolve().parent / "web_dashboard"),
):
    if hasattr(_web_pkg, "__path__") and _web_pkg_path not in _web_pkg.__path__:
        _web_pkg.__path__.append(_web_pkg_path)
