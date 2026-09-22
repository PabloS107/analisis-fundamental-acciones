"""
run_scoring.py - Punto de entrada para el Motor Cuantitativo de Scoring Fundamental.
Calcula Piotroski F-Score (0-9) y Mohanram G-Score (0-8) contra medianas sectoriales dinámicas.
"""
import sys
from pathlib import Path

shared_scripts = Path(__file__).resolve().parent.parent.parent / "fundamental-data-extractor" / "scripts"
if str(shared_scripts) not in sys.path:
    sys.path.insert(0, str(shared_scripts))

from financial_scoring_engine import calculate_fundamental_scores

if __name__ == "__main__":
    ticker = sys.argv[1] if len(sys.argv) > 1 else "AAPL"
    json_path = Path("data/processed") / ticker.upper() / "financial_statements.json"
    calculate_fundamental_scores(ticker, json_path)