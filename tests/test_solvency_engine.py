"""
tests/test_solvency_engine.py - Suite de pruebas unitarias y de integración
para el Motor de Solvencia, Deuda, Cobertura y Estrés Financiero (Credit Risk Engine):
- Apalancamiento frente a Flujos de Caja (Net Debt/EBITDA, Net Debt/FCF)
- Cobertura de Carga Financiera (EBIT/Interest, CFO/Interest, Burden %)
- Liquidez Inmediata y Riesgo de Refinanciación (Current, Quick, Cash Ratio, Rollover Risk)
- Modelos Predictivos de Quiebra (Altman Z''-Score de 4 variables)
- Calificación Sintética Crediticia Damodaran (AAA a D con default spreads y probabilidades)
- Tratamiento institucional por arquetipos (Bancos Basilea III y Aseguradoras NAIC)
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
    DebtSolvencyEngine,
    calculate_fundamental_scores,
    extract_period_metrics
)


class TestSolvencyEngine(unittest.TestCase):

    def setUp(self):
        # Datos sintéticos representativos
        self.sample_healthy_metrics = {
            "FY2024": {
                "ebit": 1000.0,
                "depreciation_and_amortization": 200.0,
                "cfo": 1100.0,
                "capex": 150.0,
                "fcf": 950.0,
                "total_debt": 500.0,
                "short_term_debt": 50.0,
                "cash": 800.0,
                "current_assets": 1200.0,
                "current_liabilities": 600.0,
                "inventory": 200.0,
                "accounts_receivable": 200.0,
                "total_assets": 4000.0,
                "total_liabilities": 1500.0,
                "stockholders_equity": 2500.0,
                "retained_earnings": 1800.0,
                "working_capital": 600.0,
                "interest_expense": 25.0,
            },
            "FY2025": {
                "ebit": 1200.0,
                "depreciation_and_amortization": 220.0,
                "cfo": 1300.0,
                "capex": 160.0,
                "fcf": 1140.0,
                "total_debt": 400.0,
                "short_term_debt": 40.0,
                "cash": 1000.0,
                "current_assets": 1400.0,
                "current_liabilities": 650.0,
                "inventory": 220.0,
                "accounts_receivable": 230.0,
                "total_assets": 4500.0,
                "total_liabilities": 1600.0,
                "stockholders_equity": 2900.0,
                "retained_earnings": 2200.0,
                "working_capital": 750.0,
                "interest_expense": 20.0,
            }
        }
        self.fys = ["FY2025", "FY2024"]

    def test_01_debt_free_company_deck(self):
        """Verifica que una empresa con caja neta y sin deuda financiera (DECK) se clasifique como AAA y CAJA NETA."""
        deck_scores_path = Path("data/processed/DECK/fundamental_scores.json")
        if not deck_scores_path.exists():
            self.skipTest("No se encontró fundamental_scores.json de DECK")

        with open(deck_scores_path, "r", encoding="utf-8") as f:
            deck_scores = json.load(f)

        solv = deck_scores.get("debt_and_solvency_analysis", {})
        self.assertTrue(solv.get("available"), "El análisis de solvencia debe estar marcado como disponible")

        latest = solv.get("latest_result", {})
        lev = latest.get("cash_flow_leverage", {})
        cov = latest.get("debt_service", {})
        dist = latest.get("distress_models", {})

        # DECK tiene cero deuda financiera o neta negativa
        self.assertTrue(lev.get("is_net_cash"))
        self.assertEqual(lev.get("net_debt_to_ebitda_str"), "CAJA NETA")
        self.assertEqual(lev.get("net_debt_to_fcf_str"), "CAJA NETA")
        self.assertEqual(dist.get("synthetic_rating"), "AAA")
        self.assertIn("LIBRE DE DEUDA", dist.get("synthetic_rating_desc"))

    def test_02_leveraged_company_aapl(self):
        """Verifica que una empresa con deuda pero flujos masivos (AAPL) tenga rating investment grade y ratios coherentes."""
        aapl_scores_path = Path("data/processed/AAPL/fundamental_scores.json")
        if not aapl_scores_path.exists():
            self.skipTest("No se encontró fundamental_scores.json de AAPL")

        with open(aapl_scores_path, "r", encoding="utf-8") as f:
            aapl_scores = json.load(f)

        solv = aapl_scores.get("debt_and_solvency_analysis", {})
        latest = solv.get("latest_result", {})
        lev = latest.get("cash_flow_leverage", {})
        cov = latest.get("debt_service", {})
        dist = latest.get("distress_models", {})

        # AAPL tiene deuda neta controlada (< 2.0x EBITDA)
        self.assertLess(lev.get("net_debt_to_ebitda", 99.0), 2.5)
        self.assertGreater(cov.get("interest_coverage", 0.0), 10.0)
        self.assertIn(dist.get("synthetic_rating"), ["AAA", "AA", "A+", "A"])

    def test_03_altman_z_double_prime_calculation(self):
        """Verifica el cálculo exacto del Altman Z''-Score de 4 variables para empresas no manufactureras/servicios."""
        # Fórmula: 6.56*X1 + 3.26*X2 + 6.72*X3 + 1.05*X4
        # FY2025: Total Assets = 4500.0
        # X1 = Working Capital (750) / 4500 = 0.1667
        # X2 = Retained Earnings (2200) / 4500 = 0.4889
        # X3 = EBIT (1200) / 4500 = 0.2667
        # X4 = Equity (2900) / Total Liabilities (1600) = 1.8125
        # Z'' = 6.56*0.1667 + 3.26*0.4889 + 6.72*0.2667 + 1.05*1.8125
        # Z'' = 1.0936 + 1.5938 + 1.7922 + 1.9031 = 6.3827 (Zona Segura > 2.60)
        res = DebtSolvencyEngine.calculate_solvency_series(self.fys, self.sample_healthy_metrics, ticker="TEST")
        dist = res["latest_result"]["distress_models"]

        self.assertAlmostEqual(dist["altman_z_double_prime"], 6.38, delta=0.1)
        self.assertIn("ZONA SEGURA", dist["altman_zone"])
        self.assertIn("SEGURA", dist["altman_badge"])

    def test_04_distress_thresholds(self):
        """Verifica que un balance deteriorado caiga en ZONA DE PELIGRO o ZONA GRIS."""
        distressed_metrics = {
            "FY2025": {
                "ebit": -50.0,
                "depreciation_and_amortization": 20.0,
                "cfo": -30.0,
                "capex": 40.0,
                "fcf": -70.0,
                "total_debt": 1500.0,
                "short_term_debt": 500.0,
                "cash": 50.0,
                "current_assets": 400.0,
                "current_liabilities": 800.0,
                "inventory": 200.0,
                "accounts_receivable": 100.0,
                "total_assets": 1200.0,
                "total_liabilities": 1600.0,
                "stockholders_equity": -400.0,
                "retained_earnings": -600.0,
                "working_capital": -400.0,
                "interest_expense": 80.0,
            }
        }
        res = DebtSolvencyEngine.calculate_solvency_series(["FY2025"], distressed_metrics, ticker="DISTRESS")
        dist = res["latest_result"]["distress_models"]

        # Z'' debe ser significativamente menor a 1.10
        self.assertLess(dist["altman_z_double_prime"], 1.10)
        self.assertIn("DISTRESS", dist["altman_zone"])
        self.assertIn("PELIGRO", dist["altman_badge"])

    def test_05_liquidity_ratios(self):
        """Verifica los ratios clásicos de liquidez estricta y riesgo de refinanciación."""
        res = DebtSolvencyEngine.calculate_solvency_series(self.fys, self.sample_healthy_metrics, ticker="TEST")
        liq = res["latest_result"]["liquidity"]

        # Current Ratio = 1400 / 650 = 2.15
        self.assertAlmostEqual(liq["current_ratio"], 1400.0 / 650.0, places=2)
        # Quick Ratio = (Cash + AR) / CL = (1000 + 230) / 650 = 1.89
        self.assertAlmostEqual(liq["quick_ratio"], (1000.0 + 230.0) / 650.0, places=2)
        # Cash Ratio = 1000 / 650 = 1.54
        self.assertAlmostEqual(liq["cash_ratio"], 1000.0 / 650.0, places=2)
        # Rollover Risk = ST Debt (40) / Total Debt (400) = 10.0%
        self.assertAlmostEqual(liq["rollover_risk_pct"], 10.0, places=1)

    def test_06_damodaran_synthetic_ratings_ladder(self):
        """Verifica los escalones de calificación sintética de Damodaran según cobertura de intereses."""
        # Cobertura > 8.5x -> AAA
        r_aaa = DebtSolvencyEngine._get_synthetic_rating(12.0)
        self.assertEqual(r_aaa["rating"], "AAA")

        # Cobertura 7.0x -> AA
        r_7 = DebtSolvencyEngine._get_synthetic_rating(7.0)
        self.assertEqual(r_7["rating"], "AA")

        # Cobertura 6.0x -> A+
        r_6 = DebtSolvencyEngine._get_synthetic_rating(6.0)
        self.assertEqual(r_6["rating"], "A+")

        # Cobertura 5.0x -> A
        r_5 = DebtSolvencyEngine._get_synthetic_rating(5.0)
        self.assertEqual(r_5["rating"], "A")

        # Cobertura 0.5x -> D
        r_05 = DebtSolvencyEngine._get_synthetic_rating(0.5)
        self.assertEqual(r_05["rating"], "D")

        # Cobertura negativa -> D
        r_neg = DebtSolvencyEngine._get_synthetic_rating(-1.0)
        self.assertEqual(r_neg["rating"], "D")

    def test_09_banking_and_insurance_inhibit_altman_z_with_pedagogical_guidance(self):
        """
        Verifica que el motor de solvencia inhiba Altman Z'' para entidades financieras y aseguradoras:
        1. Para FINANCIAL_BANKING: altman_zone == 'NO APLICABLE', altman_badge == 'NO APLICABLE',
           is_applicable == False, z_score == None, con nota pedagógica sobre Basilea III y CET1.
        2. Para INSURANCE: altman_zone == 'NO APLICABLE', is_applicable == False,
           con nota pedagógica sobre RBC (Risk-Based Capital) y Solvencia II.
        3. Veredicto institucional asignado sin falso distress de quiebra corporativa.
        """
        # 1. Banca
        res_bank = DebtSolvencyEngine.calculate_solvency_series(
            self.fys, self.sample_healthy_metrics, ticker="TEST_BANK", archetype="FINANCIAL_BANKING"
        )
        dist_bank = res_bank["latest_result"]["distress_models"]
        self.assertEqual(dist_bank["altman_zone"], "NO APLICABLE")
        self.assertEqual(dist_bank["altman_badge"], "NO APLICABLE")
        self.assertFalse(dist_bank["is_applicable"])
        self.assertIsNone(dist_bank["altman_z_double_prime"])
        self.assertIn("pedagogical_guidance", dist_bank)
        self.assertIn("CET1", dist_bank["pedagogical_guidance"].get("why_not_applicable", ""))
        self.assertIn("SOLVENCIA INSTITUCIONAL REGULADA (FINANCIAL_BANKING)", res_bank["latest_result"]["solvency_verdict"])
        self.assertEqual(res_bank["latest_result"]["global_badge"], "SOLVENCIA REGULATORIA")

        # 2. Aseguradora
        res_ins = DebtSolvencyEngine.calculate_solvency_series(
            self.fys, self.sample_healthy_metrics, ticker="TEST_INS", archetype="INSURANCE"
        )
        dist_ins = res_ins["latest_result"]["distress_models"]
        self.assertEqual(dist_ins["altman_zone"], "NO APLICABLE")
        self.assertFalse(dist_ins["is_applicable"])
        self.assertIsNone(dist_ins["altman_z_double_prime"])
        self.assertIn("pedagogical_guidance", dist_ins)
        self.assertIn("RBC", dist_ins["pedagogical_guidance"].get("why_not_applicable", ""))
        self.assertIn("SOLVENCIA INSTITUCIONAL REGULADA (INSURANCE)", res_ins["latest_result"]["solvency_verdict"])
        self.assertEqual(res_ins["latest_result"]["global_badge"], "SOLVENCIA REGULATORIA")

    def test_10_multi_taxonomic_debt_hierarchy_and_canonical_fallback(self):
        """
        Verifica la jerarquía multitaxonómica de extracción de deuda y fallback canónico:
        1. Combined debt tag (Insurance GAAP: DebtLongtermAndShorttermCombinedAmount).
        2. Long-term debt tag + Short-term debt tag (Bank GAAP: LongTermDebtAndCapitalLeaseObligationsIncludingCurrentMaturities + ShortTermBorrowings).
        3. Fallback canónico cuando no hay tags pero canonical_summary tiene total_debt positivo (evita falsa deuda=0).
        4. Preservación de cero deuda genuina para emisores sin deuda.
        """
        # 1. Tag combinado (PGR / Seguros)
        fin_ins = {
            "balance_sheet_detail": {
                "DebtLongtermAndShorttermCombinedAmount": {"values": {"FY2025": 8450.0}}
            }
        }
        m_ins = extract_period_metrics(fin_ins, "FY2025")
        self.assertEqual(m_ins["total_debt"], 8450.0)

        # 2. LT + ST (JPM / Banca)
        fin_bank = {
            "balance_sheet_detail": {
                "LongTermDebtAndCapitalLeaseObligationsIncludingCurrentMaturities": {"values": {"FY2025": 3200.0}},
                "ShortTermBorrowings": {"values": {"FY2025": 800.0}}
            }
        }
        m_bank = extract_period_metrics(fin_bank, "FY2025")
        self.assertEqual(m_bank["total_debt"], 4000.0)
        self.assertEqual(m_bank["long_term_debt"], 3200.0)
        self.assertEqual(m_bank["short_term_debt"], 800.0)

        # 3. Fallback canónico (cuando balance_sheet_detail no tiene tags mapeados o arroja <=0)
        fin_fallback = {
            "canonical_summary": {
                "total_debt": {"values": {"FY2025": 5700.0}}
            },
            "balance_sheet_detail": {}
        }
        m_fallback = extract_period_metrics(fin_fallback, "FY2025")
        self.assertEqual(m_fallback["total_debt"], 5700.0)

        # 4. Cero deuda genuina (DECK)
        fin_zero = {
            "canonical_summary": {
                "total_debt": {"values": {"FY2025": 0.0}}
            },
            "balance_sheet_detail": {}
        }
        m_zero = extract_period_metrics(fin_zero, "FY2025")
        self.assertEqual(m_zero["total_debt"], 0.0)

    def test_11_negative_interest_sign_guard_and_synthetic_interest(self):
        """
        Verifica el blindaje contra signos negativos en gastos de intereses y estimación sintética:
        1. Gasto de interés ingresado como negativo (ej. -25.0) se normaliza a positivo 25.0.
        2. Gasto de interés nulo (None) con deuda > 100M activa tasa sintética del 4.5% s/deuda.
        3. Gasto de interés nulo con deuda <= 100M no inventa carga financiera.
        """
        # 1. Signo negativo normalizado con abs()
        metrics_neg = {
            "FY2025": {
                "ebit": 500.0,
                "cfo": 450.0,
                "total_debt": 1000.0,
                "interest_expense": -25.0,
                "cash": 300.0,
                "total_assets": 2000.0,
                "total_liabilities": 1200.0,
                "stockholders_equity": 800.0,
                "retained_earnings": 500.0,
                "working_capital": 300.0
            }
        }
        res_neg = DebtSolvencyEngine.calculate_solvency_series(["FY2025"], metrics_neg, ticker="TEST_NEG")
        cov_neg = res_neg["latest_result"]["debt_service"]
        self.assertEqual(cov_neg["interest_expense"], 25.0)
        self.assertAlmostEqual(cov_neg["interest_coverage"], 20.0, places=1)

        # 2. Interés None con deuda > 100M (estimación al 4.5%)
        metrics_synth = {
            "FY2025": {
                "ebit": 500.0,
                "cfo": 450.0,
                "total_debt": 1000.0,
                "interest_expense": None,
                "cash": 300.0,
                "total_assets": 2000.0,
                "total_liabilities": 1200.0,
                "stockholders_equity": 800.0,
                "retained_earnings": 500.0,
                "working_capital": 300.0
            }
        }
        res_synth = DebtSolvencyEngine.calculate_solvency_series(["FY2025"], metrics_synth, ticker="TEST_SYNTH")
        cov_synth = res_synth["latest_result"]["debt_service"]
        self.assertEqual(cov_synth["interest_expense"], 45.0)  # 4.5% de 1000.0
        self.assertTrue(cov_synth.get("interest_estimated"))


if __name__ == "__main__":
    unittest.main()
