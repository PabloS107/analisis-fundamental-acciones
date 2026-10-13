"""
tests/test_roc_greenblatt.py - Suite de pruebas unitarias y de integración
para el cálculo del Return on Capital (ROC) según la metodología Greenblatt (Magic Formula),
con Capital Tangible Operativo Promedio, salvaguardas contables institucionales y benchmark sectorial.
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
    GreenblattROCCalculator,
    load_peer_benchmarks,
    compute_peer_benchmarks,
    calculate_fundamental_scores
)
from sec_extractor import XBRL_TAXONOMY_MAP


class TestGreenblattROC(unittest.TestCase):

    def test_01_taxonomy_map_net_ppe(self):
        """Verifica que la taxonomía XBRL incluya mapeo robusto para net_ppe en US-GAAP e IFRS."""
        self.assertIn("net_ppe", XBRL_TAXONOMY_MAP)
        concepts = XBRL_TAXONOMY_MAP["net_ppe"]
        self.assertTrue(any("PropertyPlantAndEquipmentNet" in c for c in concepts))
        self.assertTrue(any("PropertyPlantAndEquipment" in c for c in concepts))

    def test_02_calculator_positive_nwc(self):
        """Verifica el cálculo de ROC con capital de trabajo neto positivo."""
        calc = GreenblattROCCalculator()
        # Año t-1: NWC = (1000 - 200) - (500 - 100) = 800 - 400 = 400. PP&E = 600. Cap = 1000.
        # Año t: NWC = (1200 - 300) - (600 - 100) = 900 - 500 = 400. PP&E = 800. Cap = 1200.
        # Cap Promedio = (1000 + 1200) / 2 = 1100.
        # EBIT = 330 -> ROC = 330 / 1100 = 30.0%
        history = {
            "FY2023": {
                "operating_income": 250.0,
                "current_assets": 1000.0,
                "cash": 200.0,
                "current_liabilities": 500.0,
                "short_term_debt": 100.0,
                "net_ppe": 600.0
            },
            "FY2024": {
                "operating_income": 330.0,
                "current_assets": 1200.0,
                "cash": 300.0,
                "current_liabilities": 600.0,
                "short_term_debt": 100.0,
                "net_ppe": 800.0
            }
        }
        res_data = calc.calculate_series(["FY2023", "FY2024"], history, {})
        res = res_data["annual_series"]
        self.assertIn("FY2024", res)
        self.assertAlmostEqual(res["FY2024"]["tangible_capital_avg"], 1100.0, places=1)
        self.assertAlmostEqual(res["FY2024"]["roc_avg"], 0.30, places=2)

    def test_03_calculator_negative_nwc_safeguard(self):
        """Verifica la salvaguarda para modelos con capital de trabajo negativo (Asset-Light como AAPL)."""
        calc = GreenblattROCCalculator()
        # NWC = (50 - 40) - (100 - 10) = 10 - 90 = -80. Net PP&E = 50.
        # NWC + PP&E = -30. Con salvaguarda max(net_ppe, nwc + net_ppe) = max(50, -30) = 50.
        cap = calc.compute_tangible_capital(
            current_assets=50.0,
            cash=40.0,
            current_liabilities=100.0,
            short_term_debt=10.0,
            net_ppe=50.0
        )
        self.assertEqual(cap, 50.0)

    def test_04_rating_tiers(self):
        """Verifica las categorías de calificación del ROC Greenblatt."""
        calc = GreenblattROCCalculator()
        self.assertEqual(calc.rate_roc(0.55), "ELITE (> 40%)")
        self.assertEqual(calc.rate_roc(0.35), "EXCELENTE (25% - 40%)")
        self.assertEqual(calc.rate_roc(0.18), "SÓLIDO (15% - 25%)")
        self.assertEqual(calc.rate_roc(0.12), "MODERADO (10% - 15%)")
        self.assertEqual(calc.rate_roc(0.05), "DEFICIENTE (< 10%)")
        self.assertEqual(calc.rate_roc(-0.02), "DESTRUCTOR (< 0%)")

    def test_05_peer_benchmarks_contain_greenblatt_roc(self):
        """Verifica que el catálogo config/peer_benchmarks.json contenga greenblatt_roc en todos los pares."""
        raw = load_peer_benchmarks("config/peer_benchmarks.json")
        bms = raw.get("industry_benchmarks", raw)
        for sic in ["SIC_3571", "SIC_3021"]:
            self.assertIn(sic, bms)
            peers = bms[sic].get("peers", [])
            self.assertTrue(len(peers) > 0)
            for p in peers:
                self.assertIn("greenblatt_roc", p, f"Par {p.get('ticker')} en {sic} debe tener greenblatt_roc")
                self.assertIsInstance(p["greenblatt_roc"], (int, float))
            
            # Verificar compute_peer_benchmarks
            computed = compute_peer_benchmarks(bms[sic])
            self.assertIn("median_greenblatt_roc", computed)
            self.assertGreater(computed["median_greenblatt_roc"], 0.0)

    def test_06_scoring_engine_full_integration_aapl(self):
        """Verifica que calculate_fundamental_scores genere la sección greenblatt_roc_analysis completa."""
        json_path = Path("data/processed/AAPL/financial_statements.json")
        if not json_path.exists():
            self.skipTest("data/processed/AAPL/financial_statements.json no encontrado")
        
        scores = calculate_fundamental_scores("AAPL", json_path)
        self.assertIn("greenblatt_roc_analysis", scores)
        roc_data = scores["greenblatt_roc_analysis"]
        self.assertIn("annual_series", roc_data)
        self.assertIn("ltm", roc_data)
        self.assertIn("peer_comparison", roc_data)
        
        ltm_res = roc_data["ltm"]
        self.assertIsNotNone(ltm_res.get("roc_avg"))
        self.assertGreater(ltm_res["roc_avg"], 0.50, "AAPL ROC LTM debe superar 50%")
        
        peer_comp = roc_data["peer_comparison"]
        self.assertIn("peer_median_roc", peer_comp)
        self.assertIn("spread_vs_peer_median", peer_comp)
        self.assertGreater(peer_comp["spread_vs_peer_median"], 0.0)

    def test_07_inhibit_roc_for_banking_and_insurance_with_guidance(self):
        """
        Verifica que el calculador Greenblatt ROC inhiba el cómputo para FINANCIAL_BANKING e INSURANCE:
        1. is_applicable == False.
        2. rating == 'NO APLICABLE' y roc_rating == 'NO APLICABLE'.
        3. latest_roc == None y series numéricas vacías/None.
        4. Inclusión de guía pedagógica institucional completa (Regla 3) explicando el uso de ROTCE/ROE.
        """
        calc = GreenblattROCCalculator()
        history = {
            "FY2024": {"operating_income": 500.0, "current_assets": 1000.0, "net_ppe": 100.0},
            "FY2025": {"operating_income": 600.0, "current_assets": 1200.0, "net_ppe": 120.0}
        }

        # 1. Banca
        res_bank = calc.calculate_series(["FY2024", "FY2025"], history, {}, ticker="TEST_BANK", archetype="FINANCIAL_BANKING")
        self.assertFalse(res_bank["is_applicable"])
        self.assertEqual(res_bank["rating"], "NO APLICABLE")
        self.assertEqual(res_bank["roc_rating"], "NO APLICABLE")
        self.assertIsNone(res_bank["latest_roc"])
        self.assertIn("pedagogical_guidance", res_bank)
        self.assertIn("ROTCE", res_bank["pedagogical_guidance"]["why_not_applicable"])
        self.assertIn("ROE", res_bank["pedagogical_guidance"]["replacement_metrics"])

        # 2. Seguros
        res_ins = calc.calculate_series(["FY2024", "FY2025"], history, {}, ticker="TEST_INS", archetype="INSURANCE")
        self.assertFalse(res_ins["is_applicable"])
        self.assertEqual(res_ins["rating"], "NO APLICABLE")
        self.assertEqual(res_ins["roc_rating"], "NO APLICABLE")
        self.assertIsNone(res_ins["latest_roc"])
        self.assertIn("pedagogical_guidance", res_ins)

    def test_08_corporate_roc_normal_execution(self):
        """
        Verifica que para entidades corporativas estándar el ROC Greenblatt se calcule con normalidad.
        """
        calc = GreenblattROCCalculator()
        history = {
            "FY2024": {
                "operating_income": 400.0,
                "current_assets": 1000.0,
                "cash": 200.0,
                "current_liabilities": 400.0,
                "short_term_debt": 50.0,
                "net_ppe": 500.0
            },
            "FY2025": {
                "operating_income": 500.0,
                "current_assets": 1200.0,
                "cash": 250.0,
                "current_liabilities": 450.0,
                "short_term_debt": 60.0,
                "net_ppe": 600.0
            }
        }
        res_corp = calc.calculate_series(["FY2024", "FY2025"], history, {}, ticker="TEST_CORP", archetype="STANDARD_CORPORATE")
        self.assertTrue(res_corp["is_applicable"])
        self.assertNotEqual(res_corp["rating"], "NO APLICABLE")
        self.assertIsNotNone(res_corp["latest_roc"])
        self.assertIn("FY2025", res_corp["annual_series"])
        self.assertIsNotNone(res_corp["annual_series"]["FY2025"]["roc_avg"])

    def test_09_zero_or_negative_tangible_capital_handling(self):
        """
        Verifica el blindaje ante capital tangible operativo nulo o negativo:
        max(1.0, tangible_cap) garantiza que nunca se produzca ZeroDivisionError.
        """
        calc = GreenblattROCCalculator()
        # NWC muy negativo y cero PP&E
        cap = calc.compute_tangible_capital(
            current_assets=50.0,
            cash=100.0,
            current_liabilities=500.0,
            short_term_debt=0.0,
            net_ppe=0.0
        )
        self.assertGreaterEqual(cap, 1.0)


if __name__ == "__main__":
    unittest.main()
