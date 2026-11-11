"""Subpaquete de pruebas de auditoría contable, integridad y conciliación."""

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import tests  # noqa: E402, F401
