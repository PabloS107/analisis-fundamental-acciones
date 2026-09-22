"""
generate_report.py - Genera el informe institucional ejecutivo en formato Word (.docx) y Markdown (.md).
"""
import sys
from pathlib import Path

shared_scripts = Path(__file__).resolve().parent.parent.parent / "fundamental-data-extractor" / "scripts"
if str(shared_scripts) not in sys.path:
    sys.path.insert(0, str(shared_scripts))

from generate_earnings_report import generate_full_report

if __name__ == "__main__":
    ticker = sys.argv[1] if len(sys.argv) > 1 else "AAPL"
    generate_full_report(ticker)