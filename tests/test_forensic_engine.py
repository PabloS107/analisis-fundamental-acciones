"""
tests/test_forensic_engine.py - Suite de pruebas unitarias y de integración
para el Motor de Auditoría Forense Contable y Detección de Manipulación de Beneficios:
Ratio Sloan de Devengos, Matriz de Divergencias de Alerta Temprana y Montier C-Score.
"""

import os
import sys
import json
import unittest
from pathlib import Path

# Añadir scripts al path
scripts_dir = Path("pipeline").resolve()
sys.path.insert(0, str(scripts_dir))

from financial_scoring_engine import (
    ForensicAccountingEngine,
    calculate_fundamental_scores
)
from forensic_report_builder import generate_forensic_section_md


class TestForensicEngine(unittest.TestCase):

    def setUp(self):
        self.sample_metrics = {
            "FY2024": {
                "net_income": 90.0,
                "cfo": 120.0,
                "total_assets": 1000.0,
                "revenue": 800.0,
                "cost_of_goods_sold": 450.0,
                "gross_profit": 350.0,
                "accounts_receivable": 80.0,
                "inventory": 60.0,
                "net_ppe": 200.0,
                "cash": 150.0,
                "depreciation_and_amortization": 25.0,
                "other_current_assets": 30.0
            },
            "FY2025": {
                "net_income": 100.0,
                "cfo": 140.0,
                "total_assets": 1080.0,
                "revenue": 900.0,
                "cost_of_goods_sold": 500.0,
                "gross_profit": 400.0,
                "accounts_receivable": 85.0,
                "inventory": 65.0,
                "net_ppe": 220.0,
                "cash": 180.0,
                "depreciation_and_amortization": 30.0,
                "other_current_assets": 32.0
            }
        }
        self.fys = ["FY2025", "FY2024"]

    def test_01_sloan_accrual_high_quality(self):
        """Verifica que cuando CFO > NI el ratio de Sloan sea negativo (alta calidad contable)."""
        res = ForensicAccountingEngine.calculate_forensic_series(self.fys, self.sample_metrics, ticker="TEST")
        sloan = res["sloan_accrual_analysis"]["FY2025"]
        
        # NI = 100, CFO = 140 -> Total Accruals = -40
        # Avg Assets = (1100 + 1000) / 2 = 1050
        # Sloan Ratio = -40 / 1050 = -0.0381 (-3.81%)
        self.assertIsNotNone(sloan.get("sloan_ratio"))
        self.assertAlmostEqual(sloan["sloan_ratio"], -40.0 / 1050.0, places=3)
        self.assertEqual(sloan["status"], "EXCELENTE")
        self.assertIn("ALTA CONVERSIÓN", sloan["badge"])

    def test_02_sloan_accrual_red_flag(self):
        """Verifica que una desconexión severa (NI >> CFO) active la alerta roja de devengos (> +10%)."""
        manipulated_metrics = {
            "FY2024": {
                "net_income": 80.0,
                "cfo": 90.0,
                "total_assets": 1000.0
            },
            "FY2025": {
                "net_income": 200.0,  # Beneficio inflado
                "cfo": 50.0,          # Baja caja
                "total_assets": 1000.0
            }
        }
        res = ForensicAccountingEngine.calculate_forensic_series(["FY2025", "FY2024"], manipulated_metrics, ticker="MANIP")
        sloan = res["sloan_accrual_analysis"]["FY2025"]
        
        # Accruals = 200 - 50 = 150 / 1000 = +15.0%
        self.assertGreater(sloan["sloan_ratio"], 0.10)
        self.assertEqual(sloan["status"], "ALERTA ROJA")
        self.assertIn("PELIGRO DE MANIPULACIÓN", sloan["badge"])

    def test_03_divergence_matrix_spikes(self):
        """Verifica la detección de Channel Stuffing y acumulación de inventario."""
        aggressive_metrics = {
            "FY2024": {
                "accounts_receivable": 100.0,
                "revenue": 1000.0,
                "inventory": 100.0,
                "cost_of_goods_sold": 500.0,
                "total_assets": 1000.0,
                "net_ppe": 200.0,
                "cash": 100.0
            },
            "FY2025": {
                # Cuentas por cobrar suben +50%, ventas solo +5% -> Spread +45% (Channel Stuffing)
                "accounts_receivable": 150.0,
                "revenue": 1050.0,
                # Inventario sube +60%, COGS solo +10% -> Spread +50% (Inventory Bloat)
                "inventory": 160.0,
                "cost_of_goods_sold": 550.0,
                "total_assets": 1200.0,
                "net_ppe": 100.0,
                "cash": 50.0
            }
        }
        res = ForensicAccountingEngine.calculate_forensic_series(["FY2025", "FY2024"], aggressive_metrics, ticker="AGGR")
        divs = res["divergence_matrix"]["FY2025"]
        
        ar_spread = divs["ar_sales_spread"]
        self.assertTrue(ar_spread["flag"])
        self.assertEqual(ar_spread["status"], "ALERTA DE DESCONEXIÓN")
        self.assertGreater(ar_spread["spread_pct"], 10.0)

        inv_spread = divs["inv_cogs_spread"]
        self.assertTrue(inv_spread["flag"])
        self.assertEqual(inv_spread["status"], "REVISIÓN OPERATIVA")
        self.assertGreater(inv_spread["spread_pct"], 15.0)

    def test_04_montier_c_score_flags(self):
        """Verifica la activación y consistencia de las 6 banderas canónicas de Montier C-Score."""
        clean_res = ForensicAccountingEngine.calculate_forensic_series(self.fys, self.sample_metrics, ticker="CLEAN")
        montier = clean_res["montier_c_score"]["FY2025"]
        
        self.assertEqual(montier["max_score"], 6)
        self.assertLessEqual(montier["total_score"], 1)
        self.assertIn("BAJO", montier["rating"])
        
        expected_flags = [
            "f1_cfo_divergence", "f2_ar_vs_sales", "f3_inv_vs_cogs",
            "f4_other_current_assets", "f5_depreciation_rate", "f6_asset_growth"
        ]
        bd = montier["flags_breakdown"]
        for ef in expected_flags:
            self.assertIn(ef, bd)
            self.assertIn("name", bd[ef])
            self.assertIn("condition", bd[ef])
            self.assertIn("value_str", bd[ef])
            self.assertIn("flag", bd[ef])
            self.assertIn("status", bd[ef])
            self.assertIn("rationale", bd[ef])

        # Caso crítico: empresa con las 6 banderas activadas (Score = 6)
        fraud_metrics = {
            "FY2024": {
                "net_income": 50.0, "cfo": 100.0,
                "revenue": 1000.0, "cost_of_goods_sold": 600.0,
                "accounts_receivable": 100.0, "inventory": 100.0,
                "other_current_assets": 20.0,
                "total_assets": 2000.0, "net_ppe": 800.0, "cash": 200.0,
                "depreciation_and_amortization": 100.0
            },
            "FY2025": {
                "net_income": 120.0, "cfo": 40.0,  # F1: NI > CFO (+1)
                "revenue": 1020.0, "cost_of_goods_sold": 610.0,
                "accounts_receivable": 150.0,  # F2: AR +50% vs Rev +2% (+1)
                "inventory": 160.0,  # F3: Inv +60% vs COGS +1.6% (+1)
                "other_current_assets": 60.0,  # F4: OCA/Rev 5.88% vs 2.0% (+1)
                "total_assets": 2600.0,  # F6: Assets +30% > 10% (+1)
                "net_ppe": 850.0, "cash": 150.0,
                "depreciation_and_amortization": 40.0  # F5: Depr rate 4.4% vs 11.1% (+1)
            }
        }
        fraud_res = ForensicAccountingEngine.calculate_forensic_series(self.fys, fraud_metrics, ticker="FRAUD")
        fraud_m = fraud_res["montier_c_score"]["FY2025"]
        self.assertEqual(fraud_m["total_score"], 6)
        self.assertIn("ALTO", fraud_m["rating"])

    def test_05_integration_aapl_and_deck_scores(self):
        """Verifica que calculate_fundamental_scores genere la auditoría forense en AAPL y DECK."""
        for ticker in ["AAPL", "DECK"]:
            fin_path = Path(f"data/processed/{ticker}/financial_statements.json")
            if not fin_path.exists():
                continue
            scores = calculate_fundamental_scores(ticker, fin_path)
            
            self.assertIn("forensic_accounting_analysis", scores)
            fa = scores["forensic_accounting_analysis"]
            self.assertIn("sloan_accrual_analysis", fa)
            self.assertIn("divergence_matrix", fa)
            self.assertIn("montier_c_score", fa)
            self.assertIn("latest_result", fa)
            
            diag = scores.get("latest_diagnosis", {})
            self.assertIn("forensic_audit", diag)
            self.assertIsNotNone(diag["forensic_audit"].get("sloan_ratio_pct"))
            self.assertIsNotNone(diag["forensic_audit"].get("montier_score"))

    def test_07_markdown_forensic_report_builder(self):
        """Verifica que generate_forensic_section_md genere la estructura esperada."""
        fin_path = Path("data/processed/AAPL/fundamental_scores.json")
        if not fin_path.exists():
            return
        with open(fin_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        md = generate_forensic_section_md(data, ticker="AAPL", company_name="Apple Inc.", section_num=13)
        self.assertIn("## 13. Auditoría Forense Contable y Calidad de Beneficios", md)
        self.assertIn("Ratio de Devengos de Sloan", md)
        self.assertIn("Montier C-Score", md)
    def test_08_percentage_scaling_and_t_minus_1(self):
        """Verifica que porcentajes pequeños (< 1.0%) se almacenen como decimales puros y que sin t-1 sea N/D."""
        res = ForensicAccountingEngine.calculate_forensic_series(
            ["FY2025", "FY2024"],
            self.sample_metrics,
            ticker="TEST"
        )
        
        # FY2024 es el año más antiguo, no tiene t-1
        montier_24 = res["montier_c_score"]["FY2024"]
        self.assertIsNone(montier_24["total_score"])
        self.assertEqual(montier_24["rating"], "DATOS INSUFICIENTES (SIN T-1)")
        for flag_info in montier_24["flags_breakdown"].values():
            self.assertIsNone(flag_info["flag"])
            self.assertEqual(flag_info["status"], "N/D")

        # FY2025 tiene t-1: verificar que existan claves puras decimales
        divs_25 = res["divergence_matrix"]["FY2025"]
        self.assertIn("delta_ar", divs_25["ar_sales_spread"])
        self.assertIn("delta_rev", divs_25["ar_sales_spread"])
        self.assertIn("spread", divs_25["ar_sales_spread"])
        self.assertIn("delta_inv", divs_25["inv_cogs_spread"])
        self.assertIn("delta_cogs", divs_25["inv_cogs_spread"])
        self.assertIn("spread", divs_25["inv_cogs_spread"])
    def test_09_financial_archetype_not_applicable(self):
        """Verifica que para arquetipos FINANCIAL_BANKING e INSURANCE, Montier C-Score sea NO APLICABLE sin fake defaults."""
        for arch in ["FINANCIAL_BANKING", "INSURANCE"]:
            res = ForensicAccountingEngine.calculate_forensic_series(
                ["FY2025", "FY2024"],
                self.sample_metrics,
                ticker="FIN_TEST",
                archetype=arch
            )
            montier_25 = res["montier_c_score"]["FY2025"]
            self.assertIsNone(montier_25["total_score"])
            self.assertEqual(montier_25["rating"], "NO APLICABLE")
            self.assertEqual(montier_25["badge"], "NO APLICABLE")
            self.assertEqual(montier_25["color"], "#607D8B")
            self.assertIn("NO APLICABLE", montier_25["verdict"])

            for flag_key, flag_val in montier_25["flags_breakdown"].items():
                self.assertIsNone(flag_val["flag"])
                self.assertEqual(flag_val["value_str"], "N/A")
                self.assertEqual(flag_val["status"], "N/A")

            # Divergencias
            div_25 = res["divergence_matrix"]["FY2025"]
            self.assertEqual(div_25["ar_sales_spread"]["status"], "NO APLICABLE")
            self.assertEqual(div_25["inv_cogs_spread"]["status"], "NO APLICABLE")

            # Dictamen global
            latest = res["latest_result"]
            self.assertEqual(latest["global_badge"], "ANÁLISIS SECTORIAL BANCARIO")
            self.assertEqual(latest["global_color"], "#607D8B")


if __name__ == "__main__":
    unittest.main()
