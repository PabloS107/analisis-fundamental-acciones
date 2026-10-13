"""
tests/test_audit_engine.py - Tests unitarios para el motor de auditoría contable (pipeline/audit_engine.py).
Cubre:
- Identidad de margen bruto (GP = Rev - COGS) sin máscaras y rechazo de COGS negativo.
- Identidad de Free Cash Flow ramificada por arquetipo (AFFO = FFO - CapEx Mantenimiento para REITs,
  SKIP para bancos y aseguradoras, CFO - CapEx para corporativas).
- Límites de sanidad contable (rechazo de COGS y OpEx negativos).
"""

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "pipeline"))

from audit_engine import (
    audit_gross_profit,
    audit_free_cash_flow,
    audit_sanity_bounds,
    run_full_audit,
)


class TestAuditEngineAccountingRules(unittest.TestCase):
    """Pruebas unitarias para las identidades y reglas de auditoría contable."""

    def test_gross_profit_identity_pure_pass(self):
        """Verifica que GP = Rev - COGS aprueba con magnitudes positivas puras."""
        data = {
            "canonical_summary": {
                "revenue": {"FY2025": 1000.0},
                "cost_of_goods_sold": {"FY2025": 600.0},
                "gross_profit": {"FY2025": 400.0},
            }
        }
        res = audit_gross_profit(data, "FY2025")
        self.assertTrue(res["passed"])
        self.assertEqual(res["status"], "PASS")
        self.assertEqual(res["gross_profit_calculated"], 400.0)
        self.assertEqual(res["discrepancy_usd"], 0.0)

    def test_gross_profit_rejects_negative_cogs(self):
        """Verifica que audit_gross_profit falle explícitamente si COGS es negativo (sin enmascarar)."""
        data = {
            "canonical_summary": {
                "revenue": {"FY2025": 1000.0},
                "cost_of_goods_sold": {"FY2025": -600.0},
                "gross_profit": {"FY2025": 400.0},
            }
        }
        res = audit_gross_profit(data, "FY2025")
        self.assertFalse(res["passed"])
        self.assertEqual(res["status"], "FAIL")
        self.assertIn("signo negativo", res["message"])

    def test_free_cash_flow_reit_affo_identity(self):
        """Verifica que para REAL_ESTATE_REIT la auditoría valide AFFO = FFO - CapEx Mantenimiento."""
        data = {
            "archetype": "REAL_ESTATE_REIT",
            "canonical_summary": {
                "ffo": {"FY2025": 3405.15},
                "recurring_capex_maintenance": {"FY2025": 131.80},
                "free_cash_flow": {"FY2025": 3273.35},
            }
        }
        res = audit_free_cash_flow(data, "FY2025")
        self.assertTrue(res["passed"])
        self.assertEqual(res["status"], "PASS")
        self.assertEqual(res["fcf_calculated"], 3273.35)
        self.assertEqual(res["discrepancy_usd"], 0.0)

    def test_free_cash_flow_skips_financials(self):
        """Verifica que para entidades bancarias y aseguradoras el FCF reporte SKIP."""
        data_bank = {
            "archetype": "FINANCIAL_BANKING",
            "canonical_summary": {"free_cash_flow": {"FY2025": None}}
        }
        res_bank = audit_free_cash_flow(data_bank, "FY2025")
        self.assertIsNone(res_bank["passed"])
        self.assertEqual(res_bank["status"], "SKIP")

        data_ins = {
            "archetype": "INSURANCE",
            "canonical_summary": {"free_cash_flow": {"FY2025": None}}
        }
        res_ins = audit_free_cash_flow(data_ins, "FY2025")
        self.assertIsNone(res_ins["passed"])
        self.assertEqual(res_ins["status"], "SKIP")

    def test_sanity_bounds_rejects_negative_expenses(self):
        """Verifica que límites de sanidad detecten COGS u OpEx negativos."""
        data_clean = {
            "canonical_summary": {
                "revenue": {"FY2025": 1000.0},
                "cost_of_goods_sold": {"FY2025": 500.0},
                "operating_expenses": {"FY2025": 300.0},
                "cash_and_equivalents": {"FY2025": 200.0},
                "shares_diluted": {"FY2025": 100.0},
            },
            "key_ratios": {"gross_margin_pct": {"FY2025": 50.0}}
        }
        res_clean = audit_sanity_bounds(data_clean, "FY2025")
        self.assertTrue(res_clean["passed"])
        self.assertEqual(res_clean["status"], "PASS")

        data_neg = {
            "canonical_summary": {
                "revenue": {"FY2025": 1000.0},
                "cost_of_goods_sold": {"FY2025": -500.0},
                "operating_expenses": {"FY2025": -300.0},
                "cash_and_equivalents": {"FY2025": 200.0},
                "shares_diluted": {"FY2025": 100.0},
            },
            "key_ratios": {"gross_margin_pct": {"FY2025": 50.0}}
        }
        res_neg = audit_sanity_bounds(data_neg, "FY2025")
        self.assertFalse(res_neg["passed"])
        self.assertEqual(res_neg["status"], "FAIL")
        self.assertTrue(any("Costo de ventas (COGS) negativo" in err for err in res_neg["anomalies"]))
        self.assertTrue(any("Gastos operativos (OpEx) negativos" in err for err in res_neg["anomalies"]))


class TestAuditEngineArtifactVerification(unittest.TestCase):
    """Verifica que los artefactos procesados en disco pasen la auditoría."""

    def test_meli_processed_audit_passes_100_percent(self):
        """MELI procesado debe pasar la auditoría contable con 100% de cumplimiento."""
        res = run_full_audit("MELI")
        self.assertEqual(res["compliance_score_pct"], 100.0)
        self.assertEqual(res["failed_tests"], 0)

    def test_realty_income_processed_audit_affo_passes(self):
        """O (Realty Income) procesado debe pasar la auditoría de FCF/AFFO sin fallos de discrepancia inmobiliaria."""
        res = run_full_audit("O")
        # El cumplimiento debe ser >= 90% (todas las pruebas de FCF pasan)
        self.assertGreaterEqual(res["compliance_score_pct"], 90.0)
        # Verificar que ninguna de las fallas sea de FCF
        for fy, tests in res.get("years_audited", {}).items():
            for test in tests:
                if "Free Cash Flow" in test.get("test_name", ""):
                    self.assertNotEqual(test.get("status"), "FAIL", f"O FCF falló en {fy}: {test}")


if __name__ == "__main__":
    unittest.main()
