# -*- coding: utf-8 -*-
"""
Regresión E2E de integridad contable: verifica 0 residuales sin atribuir
(abs(residual_unexplained_usd) < $10,000) y 7/7 controles Q1-Q7 en PASS
para todas las empresas procesadas del data lake.
"""

import json
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PIPELINE_DIR = PROJECT_ROOT / "pipeline"
for _p in (PROJECT_ROOT, PIPELINE_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import pipeline  # noqa: E402, F401
from pipeline.audit_modules.statement_quality_audit import evaluate_statement_quality  # noqa: E402

PROCESSED_TICKERS = ("AAPL", "DECK", "GOOGL", "JPM", "MELI", "META", "NU", "NVDA", "O", "PGR", "UBER")


class TestZeroUnexplainedResiduals(unittest.TestCase):
    """Garantiza cero residuales sin atribuir y 7/7 PASS (Q1-Q7) en todo el data lake."""

    def test_all_companies_zero_residuals_and_q1_q7_pass(self):
        for ticker in PROCESSED_TICKERS:
            fs_path = PROJECT_ROOT / "data" / "processed" / ticker / "financial_statements.json"
            audit_path = PROJECT_ROOT / "data" / "processed" / ticker / "audit_report.json"
            self.assertTrue(fs_path.exists(), f"Falta {fs_path}")
            self.assertTrue(audit_path.exists(), f"Falta {audit_path}")

            fs = json.loads(fs_path.read_text(encoding="utf-8"))
            recent_periods = [p for p in (fs.get("fiscal_years") or [])[:6] if p == "LTM" or p >= "FY2022"]
            lineage = fs.get("resolved_canonical_lineage") or {}
            self.assertTrue(lineage, f"[{ticker}] resolved_canonical_lineage vacío")

            bad_cells = []
            for metric_key, spec in lineage.items():
                if spec.get("method") != "PLUG_ATTRIBUTION":
                    continue
                p_map = spec.get("periods") or {}
                for period in recent_periods:
                    entry = p_map.get(period)
                    if not isinstance(entry, dict):
                        continue
                    res = entry.get("residual_unexplained_usd")
                    if res is None or abs(float(res)) >= 10_000.0:
                        bad_cells.append((metric_key, period, res))

            self.assertEqual(bad_cells, [], f"[{ticker}] Residuales >= $10k detectados: {bad_cells}")

            quality = evaluate_statement_quality(fs)
            self.assertEqual(quality["pass_count"], 7, f"[{ticker}] Se esperaban 7/7 PASS en Q1-Q7: {quality}")
            self.assertEqual(quality["status"], "PASS", f"[{ticker}] Estado Q1-Q7 no es PASS: {quality}")

            audit_data = json.loads(audit_path.read_text(encoding="utf-8"))
            persisted_q = audit_data.get("statement_quality") or []
            self.assertEqual(len(persisted_q), 7, f"[{ticker}] audit_report.json debe persistir 7 controles Q1-Q7")
            self.assertTrue(
                all(c.get("severity") == "PASS" for c in persisted_q),
                f"[{ticker}] audit_report.json contiene controles no-PASS: {persisted_q}",
            )


if __name__ == "__main__":
    unittest.main()
