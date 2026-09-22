"""
update_excel_model.py - Genera o actualiza el modelo Excel interactivo de 8 pestañas.
"""
import sys
from pathlib import Path

shared_scripts = Path(__file__).resolve().parent.parent.parent / "fundamental-data-extractor" / "scripts"
if str(shared_scripts) not in sys.path:
    sys.path.insert(0, str(shared_scripts))

from excel_formatter import generate_full_excel_workbook

if __name__ == "__main__":
    ticker = sys.argv[1] if len(sys.argv) > 1 else "AAPL"
    generate_full_excel_workbook(ticker)