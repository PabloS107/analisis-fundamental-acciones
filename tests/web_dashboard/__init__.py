"""Subpaquete de pruebas del dashboard web Django, gráficos e infraestructura."""

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

if __name__ == "web_dashboard":
    _django_web_pkg = str(_PROJECT_ROOT / "web_dashboard" / "web_dashboard")
    if _django_web_pkg not in __path__:
        __path__.append(_django_web_pkg)

import tests  # noqa: E402, F401
