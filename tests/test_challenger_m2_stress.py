"""
tests/test_challenger_m2_stress.py - Suite de Pruebas de Estrés Adversarial Empírico
Milestone 2: Financial Scoring Engine Decoupling

Ejecutado por: Challenger M2.1 (Gen 2) - Empirical Challenger & Forensic Specialist.
Objetivo:
- Verificar empíricamente que Altman Z'' y Greenblatt ROC NUNCA disparan falsas alarmas
  de quiebra (< 1.10) o retornos absurdos de miles por ciento en balances bancarios y aseguradores.
- Verificar la correcta inhibición bajo arquetipos FINANCIAL_BANKING e INSURANCE y todos sus alias.
- Verificar la preservación absoluta de Altman Z'' y ROC en STANDARD_CORPORATE y sus variantes.
- Verificar la preservación de WACC vs Ke, TBV, y jerarquía de deuda.
- Verificar cero regresiones en empresas de control (AAPL, DECK) y auditoría de los 8 artefactos reales.
- Verificar la ausencia de hardcoding de tickers (Regla 4 de AGENTS.md).
"""

import unittest
import json
import tempfile
import shutil
from pathlib import Path
from typing import Dict, Any

from pipeline.financial_scoring_engine import (
    normalize_archetype,
    DebtSolvencyEngine,
    GreenblattROCCalculator,
    WACCCalculator,
    extract_period_metrics,
    calculate_fundamental_scores,
    PiotroskiScoreCalculator
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent


class TestBankingArchetypeInhibition(unittest.TestCase):
    """Pruebas de estrés adversarial sobre balances bancarios (FINANCIAL_BANKING y alias)."""

    def setUp(self):
        # Balance sintético de un mega-banco internacional (JPM / Santander / ICBC-style)
        # Activos: $400,000M, Depósitos: $250,000M, Deuda: $50,000M, Pasivos Totales: $370,000M
        # Patrimonio: $300,000M, Cash: $80,000M, EBIT: $65,000M, Net Income: $50,000M, Net PPE: $15,000M
        # Sin activos corrientes ni pasivos corrientes clasificados (balance bancario no clasificado)
        self.mega_bank_period_metrics = {
            "FY2024": {
                "total_assets": 400000.0,
                "total_liabilities": 370000.0,
                "stockholders_equity": 300000.0,
                "retained_earnings": 200000.0,
                "total_debt": 50000.0,
                "long_term_debt": 40000.0,
                "short_term_debt": 10000.0,
                "cash": 80000.0,
                "operating_income": 65000.0,
                "ebit": 65000.0,
                "net_income": 50000.0,
                "interest_expense": 2500.0,
                "cfo": 60000.0,
                "capex": 5000.0,
                "depreciation_and_amortization": 8000.0,
                "net_ppe": 15000.0,
                "current_assets": None,
                "current_liabilities": None,
                "accounts_receivable": None,
                "inventory": None
            },
            "LTM": {
                "total_assets": 420000.0,
                "total_liabilities": 388000.0,
                "stockholders_equity": 320000.0,
                "retained_earnings": 220000.0,
                "total_debt": 52000.0,
                "long_term_debt": 42000.0,
                "short_term_debt": 10000.0,
                "cash": 85000.0,
                "operating_income": 70000.0,
                "ebit": 70000.0,
                "net_income": 54000.0,
                "interest_expense": 2600.0,
                "cfo": 65000.0,
                "capex": 5500.0,
                "depreciation_and_amortization": 8500.0,
                "net_ppe": 16000.0,
                "current_assets": None,
                "current_liabilities": None,
                "accounts_receivable": None,
                "inventory": None
            }
        }

        # Balance sintético de un neobanco digital / fintech (Nubank-like)
        self.fintech_bank_period_metrics = {
            "FY2024": {
                "total_assets": 45000.0,
                "total_liabilities": 38000.0,
                "stockholders_equity": 7000.0,
                "retained_earnings": 2500.0,
                "total_debt": 5700.0,
                "cash": 9500.0,
                "operating_income": 2800.0,
                "ebit": 2800.0,
                "net_income": 2100.0,
                "interest_expense": 450.0,
                "cfo": 3200.0,
                "capex": 120.0,
                "depreciation_and_amortization": 150.0,
                "net_ppe": 300.0,
                "current_assets": None,
                "current_liabilities": None
            }
        }

    def test_altman_z_inhibited_on_mega_bank(self):
        """Verifica que un mega-banco con billones en pasivos NUNCA reciba score Altman Z'' de quiebra."""
        res = DebtSolvencyEngine.calculate_solvency_series(
            fiscal_years=["FY2024", "LTM"],
            period_metrics=self.mega_bank_period_metrics,
            ticker="MEGA_BANK",
            archetype="FINANCIAL_BANKING"
        )

        # 1. En cada período individual
        for fy in ["FY2024", "LTM"]:
            dist = res["distress_and_credit_models"][fy]
            self.assertFalse(dist["is_applicable"], f"{fy} debe marcar is_applicable=False")
            self.assertEqual(dist["altman_zone"], "NO APLICABLE")
            self.assertEqual(dist["altman_badge"], "NO APLICABLE")
            self.assertIsNone(dist["altman_z_double_prime"])
            self.assertIn("pedagogical_guidance", dist)
            guidance = dist["pedagogical_guidance"]
            self.assertEqual(guidance["status"], "NO APLICABLE")
            self.assertIn("CET1", str(guidance["replacement_metrics"]))

        # 2. En el dictamen consolidado (latest_result)
        latest = res["latest_result"]
        self.assertEqual(latest["distress_models"]["altman_zone"], "NO APLICABLE")
        self.assertFalse(latest["distress_models"]["is_applicable"])
        self.assertIsNone(latest["distress_models"]["altman_z_double_prime"])
        self.assertEqual(latest["global_badge"], "SOLVENCIA REGULATORIA")
        self.assertTrue(latest["solvency_verdict"].startswith("SOLVENCIA INSTITUCIONAL REGULADA"))

        # 3. Nunca debe clasificar como Zona de Distress (< 1.10)
        self.assertNotIn("ZONA DE DISTRESS", latest["distress_models"]["altman_zone"])
        self.assertNotIn("PELIGRO DE QUIEBRA", latest["distress_models"]["altman_badge"])

    def test_altman_z_inhibited_across_all_banking_aliases(self):
        """Verifica que todos los alias institucionales bancarios activen la inhibición de Altman Z''."""
        aliases = ["FINANCIAL_BANKING", "BANKING_FINANCIAL", "BANKING", "banking", "Banking", "financial_banking"]
        for alias in aliases:
            res = DebtSolvencyEngine.calculate_solvency_series(
                fiscal_years=["FY2024"],
                period_metrics=self.mega_bank_period_metrics,
                ticker="TEST_ALIAS",
                archetype=alias
            )
            dist = res["distress_and_credit_models"]["FY2024"]
            self.assertFalse(dist["is_applicable"], f"Alias {alias} falló en inhibir is_applicable")
            self.assertEqual(dist["altman_zone"], "NO APLICABLE", f"Alias {alias} falló en altman_zone")

    def test_altman_z_inhibited_on_distressed_bank_without_false_industrial_bankruptcy(self):
        """Verifica que un banco con pérdidas operativas mantenga Altman Z'' como NO APLICABLE y no arroje quiebra industrial."""
        distressed_bank = {
            "FY2024": {
                "total_assets": 100000.0,
                "total_liabilities": 92000.0,
                "stockholders_equity": 8000.0,
                "retained_earnings": 1000.0,
                "total_debt": 15000.0,
                "operating_income": -3000.0,
                "ebit": -3000.0,
                "net_income": -4000.0,
                "interest_expense": 1200.0,
                "cash": 12000.0
            }
        }
        res = DebtSolvencyEngine.calculate_solvency_series(
            fiscal_years=["FY2024"],
            period_metrics=distressed_bank,
            ticker="STRESSED_BANK",
            archetype="FINANCIAL_BANKING"
        )
        dist = res["distress_and_credit_models"]["FY2024"]
        self.assertEqual(dist["altman_zone"], "NO APLICABLE")
        self.assertFalse(dist["is_applicable"])

    def test_greenblatt_roc_inhibited_on_mega_bank(self):
        """Verifica que el Greenblatt ROC NUNCA arroje retornos astronómicos de miles % en bancos."""
        res = GreenblattROCCalculator.calculate_series(
            fiscal_years=["FY2024", "LTM"],
            period_metrics=self.mega_bank_period_metrics,
            benchmarks={},
            ticker="MEGA_BANK",
            archetype="FINANCIAL_BANKING"
        )

        self.assertFalse(res["is_applicable"])
        self.assertEqual(res["rating"], "NO APLICABLE")
        self.assertEqual(res["roc_rating"], "NO APLICABLE")
        self.assertIsNone(res["latest_roc"])
        self.assertIsNone(res["latest_roc_pct"])

        # Verificar cada año y LTM
        for fy in ["FY2024", "LTM"]:
            annual = res["annual_series"][fy]
            self.assertFalse(annual["is_applicable"])
            self.assertEqual(annual["rating"], "NO APLICABLE")
            self.assertEqual(annual["roc_rating"], "NO APLICABLE")
            self.assertIsNone(annual["roc_avg"])
            self.assertIsNone(annual["roc_pct"])

        # Verificar acceso directo al dict (res["FY2024"])
        self.assertIn("FY2024", res)
        self.assertFalse(res["FY2024"]["is_applicable"])

        # Verificar guía pedagógica
        self.assertIn("pedagogical_guidance", res)
        guidance = res["pedagogical_guidance"]
        self.assertEqual(guidance["status"], "NO APLICABLE")
        self.assertIn("ROTCE", guidance["replacement_metrics"])

    def test_greenblatt_roc_inhibited_across_all_banking_aliases(self):
        """Verifica que todos los alias institucionales bancarios inhiban Greenblatt ROC."""
        aliases = ["FINANCIAL_BANKING", "BANKING_FINANCIAL", "BANKING", "banking", "Banking", "financial_banking"]
        for alias in aliases:
            res = GreenblattROCCalculator.calculate_series(
                fiscal_years=["FY2024"],
                period_metrics=self.mega_bank_period_metrics,
                benchmarks={},
                ticker="TEST_ALIAS",
                archetype=alias
            )
            self.assertFalse(res["is_applicable"], f"Alias {alias} falló en inhibir ROC is_applicable")
            self.assertEqual(res["rating"], "NO APLICABLE", f"Alias {alias} falló en rating")

    def test_wacc_vs_ke_branching_on_banking(self):
        """Verifica que los bancos calculen COST_OF_EQUITY_KE con TBV, ROE, ROTCE y no WACC empresarial."""
        period_data = self.mega_bank_period_metrics["FY2024"]
        period_data["goodwill"] = 30000.0
        period_data["intangibles"] = 10000.0

        res = WACCCalculator.calculate_wacc_and_spread(
            ticker="MEGA_BANK",
            recent_fy="FY2024",
            period_data=period_data,
            roic_adjusted=None,
            roic_traditional=None,
            benchmarks={"archetype": "FINANCIAL_BANKING"}
        )

        self.assertEqual(res["model_type"], "COST_OF_EQUITY_KE")
        self.assertEqual(res["archetype"], "FINANCIAL_BANKING")
        self.assertEqual(res["weight_equity"], 1.0)
        self.assertEqual(res["weight_debt"], 0.0)
        self.assertFalse(res["is_debt_free"])
        self.assertEqual(res["wacc"], res["cost_of_equity_ke"])
        self.assertIsNone(res["cost_of_debt_kd_pre_tax"])

        # TBV = 300,000 - 30,000 - 10,000 = 260,000M
        self.assertAlmostEqual(res["tangible_book_value_usd_m"], 260000.0, places=1)
        # ROE = 50,000 / 300,000 = 16.67%
        self.assertAlmostEqual(res["roe"], 50000.0 / 300000.0, places=4)
        # ROTCE = 50,000 / 260,000 = 19.23%
        self.assertAlmostEqual(res["rotce"], 50000.0 / 260000.0, places=4)
        # Spread = ROTCE - Ke
        self.assertAlmostEqual(res["spread"], res["rotce"] - res["cost_of_equity_ke"], places=4)


class TestInsuranceArchetypeInhibition(unittest.TestCase):
    """Pruebas de estrés adversarial sobre balances de aseguradoras (INSURANCE y alias)."""

    def setUp(self):
        # Balance sintético de aseguradora P&C (Progressive-style / Travelers-style)
        # Activos: $95,000M (inversiones $75,000M, float), Pasivos: $74,000M (reservas siniestros $55,000M)
        # Deuda combinada: $8,400M, Patrimonio: $21,000M, Net Income: $6,500M, EBIT: $8,200M, Net PPE: $900M
        self.insurer_period_metrics = {
            "FY2024": {
                "total_assets": 95000.0,
                "total_liabilities": 74000.0,
                "stockholders_equity": 21000.0,
                "retained_earnings": 15000.0,
                "total_debt": 8400.0,
                "cash": 4500.0,
                "operating_income": 8200.0,
                "ebit": 8200.0,
                "net_income": 6500.0,
                "interest_expense": 380.0,
                "cfo": 8900.0,
                "capex": 350.0,
                "depreciation_and_amortization": 400.0,
                "net_ppe": 900.0,
                "current_assets": None,
                "current_liabilities": None
            },
            "LTM": {
                "total_assets": 102000.0,
                "total_liabilities": 79000.0,
                "stockholders_equity": 23000.0,
                "retained_earnings": 17000.0,
                "total_debt": 8400.0,
                "cash": 5000.0,
                "operating_income": 9000.0,
                "ebit": 9000.0,
                "net_income": 7200.0,
                "interest_expense": 390.0,
                "cfo": 9600.0,
                "capex": 380.0,
                "depreciation_and_amortization": 420.0,
                "net_ppe": 950.0,
                "current_assets": None,
                "current_liabilities": None
            }
        }

    def test_altman_z_inhibited_on_insurer(self):
        """Verifica que una aseguradora con grandes reservas técnicas NUNCA reciba score Altman Z'' de quiebra."""
        res = DebtSolvencyEngine.calculate_solvency_series(
            fiscal_years=["FY2024", "LTM"],
            period_metrics=self.insurer_period_metrics,
            ticker="TEST_INSURER",
            archetype="INSURANCE"
        )

        for fy in ["FY2024", "LTM"]:
            dist = res["distress_and_credit_models"][fy]
            self.assertFalse(dist["is_applicable"])
            self.assertEqual(dist["altman_zone"], "NO APLICABLE")
            self.assertEqual(dist["altman_badge"], "NO APLICABLE")
            self.assertIsNone(dist["altman_z_double_prime"])
            self.assertIn("pedagogical_guidance", dist)
            guidance = dist["pedagogical_guidance"]
            self.assertEqual(guidance["status"], "NO APLICABLE")
            self.assertIn("RBC Ratio", str(guidance["replacement_metrics"]))

        latest = res["latest_result"]
        self.assertEqual(latest["distress_models"]["altman_zone"], "NO APLICABLE")
        self.assertEqual(latest["global_badge"], "SOLVENCIA REGULATORIA")

    def test_altman_z_inhibited_across_insurance_aliases(self):
        """Verifica que todos los alias de aseguradoras activen la inhibición de Altman Z''."""
        aliases = ["INSURANCE", "insurance", "INSURER", "insurer", "Insurance"]
        for alias in aliases:
            res = DebtSolvencyEngine.calculate_solvency_series(
                fiscal_years=["FY2024"],
                period_metrics=self.insurer_period_metrics,
                ticker="TEST_ALIAS",
                archetype=alias
            )
            dist = res["distress_and_credit_models"]["FY2024"]
            self.assertFalse(dist["is_applicable"], f"Alias {alias} falló en inhibir is_applicable")
            self.assertEqual(dist["altman_zone"], "NO APLICABLE")

    def test_greenblatt_roc_inhibited_on_insurer(self):
        """Verifica que el Greenblatt ROC NUNCA arroje retornos astronómicos en aseguradoras."""
        res = GreenblattROCCalculator.calculate_series(
            fiscal_years=["FY2024", "LTM"],
            period_metrics=self.insurer_period_metrics,
            benchmarks={},
            ticker="TEST_INSURER",
            archetype="INSURANCE"
        )

        self.assertFalse(res["is_applicable"])
        self.assertEqual(res["rating"], "NO APLICABLE")
        self.assertEqual(res["roc_rating"], "NO APLICABLE")
        self.assertIsNone(res["latest_roc"])

        for fy in ["FY2024", "LTM"]:
            annual = res["annual_series"][fy]
            self.assertFalse(annual["is_applicable"])
            self.assertEqual(annual["rating"], "NO APLICABLE")
            self.assertIsNone(annual["roc_avg"])

    def test_wacc_vs_ke_branching_on_insurance(self):
        """Verifica que las aseguradoras calculen COST_OF_EQUITY_KE con ROE / ROTCE."""
        period_data = self.insurer_period_metrics["FY2024"]
        res = WACCCalculator.calculate_wacc_and_spread(
            ticker="TEST_INSURER",
            recent_fy="FY2024",
            period_data=period_data,
            roic_adjusted=None,
            roic_traditional=None,
            benchmarks={"archetype": "INSURANCE"}
        )

        self.assertEqual(res["model_type"], "COST_OF_EQUITY_KE")
        self.assertEqual(res["archetype"], "INSURANCE")
        self.assertEqual(res["wacc"], res["cost_of_equity_ke"])
        self.assertEqual(res["weight_equity"], 1.0)
        self.assertEqual(res["weight_debt"], 0.0)
        self.assertAlmostEqual(res["roe"], 6500.0 / 21000.0, places=4)


class TestCorporateArchetypePreservation(unittest.TestCase):
    """Pruebas de preservación absoluta de Altman Z'' y ROC en STANDARD_CORPORATE."""

    def setUp(self):
        # Empresa corporativa apalancada típica (industrial / consumo)
        self.corp_leveraged_metrics = {
            "FY2023": {
                "total_assets": 10000.0,
                "total_liabilities": 6000.0,
                "stockholders_equity": 4000.0,
                "retained_earnings": 3000.0,
                "total_debt": 3500.0,
                "short_term_debt": 500.0,
                "current_assets": 4500.0,
                "current_liabilities": 2500.0,
                "cash": 800.0,
                "ebit": 1500.0,
                "operating_income": 1500.0,
                "net_income": 1000.0,
                "interest_expense": 180.0,
                "cfo": 1400.0,
                "capex": 300.0,
                "depreciation_and_amortization": 250.0,
                "net_ppe": 4000.0,
                "revenue": 12000.0,
                "cost_of_goods_sold": 7000.0,
                "gross_profit": 5000.0
            },
            "FY2024": {
                "total_assets": 11000.0,
                "total_liabilities": 6200.0,
                "stockholders_equity": 4800.0,
                "retained_earnings": 3800.0,
                "total_debt": 3200.0,
                "short_term_debt": 400.0,
                "current_assets": 5000.0,
                "current_liabilities": 2600.0,
                "cash": 1000.0,
                "ebit": 1800.0,
                "operating_income": 1800.0,
                "net_income": 1250.0,
                "interest_expense": 160.0,
                "cfo": 1650.0,
                "capex": 350.0,
                "depreciation_and_amortization": 280.0,
                "net_ppe": 4500.0,
                "revenue": 13500.0,
                "cost_of_goods_sold": 7800.0,
                "gross_profit": 5700.0
            }
        }

        # Empresa corporativa libre de deuda (DECK-like)
        self.corp_debt_free_metrics = {
            "FY2024": {
                "total_assets": 2500.0,
                "total_liabilities": 600.0,
                "stockholders_equity": 1900.0,
                "retained_earnings": 1800.0,
                "total_debt": 0.0,
                "short_term_debt": 0.0,
                "current_assets": 1800.0,
                "current_liabilities": 500.0,
                "cash": 1200.0,
                "ebit": 600.0,
                "operating_income": 600.0,
                "net_income": 480.0,
                "interest_expense": 0.0,
                "cfo": 550.0,
                "capex": 80.0,
                "depreciation_and_amortization": 45.0,
                "net_ppe": 400.0,
                "revenue": 4000.0,
                "cost_of_goods_sold": 2000.0,
                "gross_profit": 2000.0
            }
        }

    def test_corporate_altman_z_normal_execution(self):
        """Verifica que una empresa corporativa calcule Altman Z'' normalmente con valores numéricos y zona válida."""
        res = DebtSolvencyEngine.calculate_solvency_series(
            fiscal_years=["FY2023", "FY2024"],
            period_metrics=self.corp_leveraged_metrics,
            ticker="CORP_TEST",
            archetype="STANDARD_CORPORATE"
        )

        for fy in ["FY2023", "FY2024"]:
            dist = res["distress_and_credit_models"][fy]
            self.assertTrue(dist["is_applicable"])
            self.assertIsNotNone(dist["altman_z_double_prime"])
            self.assertGreater(dist["altman_z_double_prime"], 0.0)
            self.assertNotEqual(dist["altman_zone"], "NO APLICABLE")
            self.assertNotIn("pedagogical_guidance", dist)

        latest = res["latest_result"]
        self.assertNotEqual(latest["distress_models"]["altman_zone"], "NO APLICABLE")
        self.assertTrue(latest["distress_models"]["is_applicable"])
        self.assertIsNotNone(latest["distress_models"]["altman_z_double_prime"])

    def test_corporate_greenblatt_roc_normal_execution(self):
        """Verifica que una empresa corporativa calcule Greenblatt ROC normalmente con valores numéricos y rating."""
        res = GreenblattROCCalculator.calculate_series(
            fiscal_years=["FY2023", "FY2024"],
            period_metrics=self.corp_leveraged_metrics,
            benchmarks={},
            ticker="CORP_TEST",
            archetype="STANDARD_CORPORATE"
        )

        self.assertTrue(res["is_applicable"])
        self.assertNotEqual(res["rating"], "NO APLICABLE")
        self.assertNotEqual(res["roc_rating"], "NO APLICABLE")
        self.assertIsNotNone(res["latest_roc"])
        self.assertGreater(res["latest_roc"], 0.0)

    def test_debt_free_corporate_preservation(self):
        """Verifica que una empresa corporativa libre de deuda (como DECK) conserve total_debt=0 y WACC=Ke."""
        solv = DebtSolvencyEngine.calculate_solvency_series(
            fiscal_years=["FY2024"],
            period_metrics=self.corp_debt_free_metrics,
            ticker="DECK_TEST",
            archetype="STANDARD_CORPORATE"
        )
        latest_solv = solv["latest_result"]
        self.assertTrue(latest_solv["cash_flow_leverage"]["is_debt_free"])
        self.assertEqual(latest_solv["cash_flow_leverage"]["total_debt"], 0.0)
        self.assertEqual(latest_solv["debt_service"]["interest_coverage_str"], "INFINITA (SIN DEUDA)")

        wacc_res = WACCCalculator.calculate_wacc_and_spread(
            ticker="DECK_TEST",
            recent_fy="FY2024",
            period_data=self.corp_debt_free_metrics["FY2024"],
            roic_adjusted=0.25,
            roic_traditional=0.22,
            benchmarks={"archetype": "STANDARD_CORPORATE"}
        )
        self.assertEqual(wacc_res["model_type"], "WACC")
        self.assertTrue(wacc_res["is_debt_free"])
        self.assertEqual(wacc_res["total_debt_usd_m"], 0.0)
        self.assertEqual(wacc_res["weight_debt"], 0.0)
        self.assertEqual(wacc_res["wacc"], wacc_res["cost_of_equity_ke"])

    def test_corporate_boundary_zero_tangible_capital(self):
        """Verifica que cuando el capital tangible operativo es <= 0, Greenblatt ROC no genere ZeroDivisionError."""
        degenerate_metrics = {
            "FY2024": {
                "ebit": 100.0,
                "operating_income": 100.0,
                "current_assets": 500.0,
                "cash": 600.0,  # Cash > CA
                "current_liabilities": 200.0,
                "short_term_debt": 50.0,
                "net_ppe": 20.0
            }
        }
        res = GreenblattROCCalculator.calculate_series(
            fiscal_years=["FY2024"],
            period_metrics=degenerate_metrics,
            benchmarks={},
            ticker="DEGENERATE_CORP",
            archetype="STANDARD_CORPORATE"
        )
        self.assertTrue(res["is_applicable"])
        self.assertIsNotNone(res["latest_roc"])

    def test_corporate_boundary_negative_equity_altman(self):
        """Verifica que cuando el patrimonio contable es negativo (por recompras, como Boeing/Starbucks), Altman Z'' no distorsione negativamente x4."""
        neg_eq_metrics = {
            "FY2024": {
                "total_assets": 10000.0,
                "total_liabilities": 12000.0,
                "stockholders_equity": -2000.0,  # Patrimonio contable negativo
                "retained_earnings": -3000.0,
                "total_debt": 8000.0,
                "current_assets": 4000.0,
                "current_liabilities": 3000.0,
                "ebit": 1200.0
            }
        }
        res = DebtSolvencyEngine.calculate_solvency_series(
            fiscal_years=["FY2024"],
            period_metrics=neg_eq_metrics,
            ticker="NEG_EQ_CORP",
            archetype="STANDARD_CORPORATE"
        )
        dist = res["distress_and_credit_models"]["FY2024"]
        self.assertEqual(dist["altman_x4"], 0.0, "x4 debe acotarse a 0.0 cuando el equity es negativo")
        self.assertIsNotNone(dist["altman_z_double_prime"])

    def test_negative_interest_sanitization(self):
        """Verifica que intereses negativos (compensación por ingresos) se normalicen con abs() y no desactiven la cobertura."""
        neg_int_metrics = {
            "FY2024": {
                "total_debt": 1000.0,
                "cash": 100.0,
                "operating_income": 500.0,
                "interest_expense": -50.0,  # Negativo en XBRL
                "cfo": 400.0,
                "total_assets": 2000.0,
                "total_liabilities": 1200.0,
                "stockholders_equity": 800.0
            }
        }
        res = DebtSolvencyEngine.calculate_solvency_series(
            fiscal_years=["FY2024"],
            period_metrics=neg_int_metrics,
            ticker="NEG_INT_CORP",
            archetype="STANDARD_CORPORATE"
        )
        cov = res["debt_service"]["FY2024"]
        self.assertEqual(cov["interest_expense"], 50.0)
        self.assertAlmostEqual(cov["interest_coverage"], 500.0 / 50.0, places=1)
        self.assertNotEqual(cov["status_service"], "LIBRE DE DEUDA")


class TestEndToEndPipelineDecoupling(unittest.TestCase):
    """Pruebas de integración completa de calculate_fundamental_scores sobre statements sintéticos."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="test_challenger_scoring_")

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_synthetic_bank_end_to_end_scoring(self):
        """Verifica que calculate_fundamental_scores genere fundamental_scores.json con inhibiciones completas para un banco."""
        bank_fs = {
            "cik": "0000000001",
            "company_name": "SYNTHETIC NATIONAL BANK",
            "ticker": "SYNBANK",
            "archetype": "FINANCIAL_BANKING",
            "sic_code": "6021",
            "fiscal_years": ["LTM", "FY2024", "FY2023"],
            "balance_sheet": {
                "FY2023": {"Assets": 1000000000000, "Liabilities": 920000000000, "StockholdersEquity": 80000000000, "CashAndCashEquivalentsAtCarryingValue": 150000000000},
                "FY2024": {"Assets": 1100000000000, "Liabilities": 1010000000000, "StockholdersEquity": 90000000000, "CashAndCashEquivalentsAtCarryingValue": 170000000000},
                "LTM": {"Assets": 1150000000000, "Liabilities": 1050000000000, "StockholdersEquity": 95000000000, "CashAndCashEquivalentsAtCarryingValue": 180000000000}
            },
            "income_statement": {
                "FY2023": {"NetIncomeLoss": 15000000000, "OperatingIncomeLoss": 20000000000, "InterestExpense": 8000000000},
                "FY2024": {"NetIncomeLoss": 18000000000, "OperatingIncomeLoss": 23000000000, "InterestExpense": 9000000000},
                "LTM": {"NetIncomeLoss": 19000000000, "OperatingIncomeLoss": 24000000000, "InterestExpense": 9200000000}
            },
            "cash_flow": {
                "FY2023": {"NetCashProvidedByUsedInOperatingActivities": 22000000000, "PaymentsToAcquirePropertyPlantAndEquipment": 1500000000},
                "FY2024": {"NetCashProvidedByUsedInOperatingActivities": 25000000000, "PaymentsToAcquirePropertyPlantAndEquipment": 1800000000},
                "LTM": {"NetCashProvidedByUsedInOperatingActivities": 26000000000, "PaymentsToAcquirePropertyPlantAndEquipment": 1900000000}
            },
            "canonical_summary": {
                "total_debt": {"FY2023": 120000000000.0, "FY2024": 130000000000.0, "LTM": 135000000000.0},
                "shares_basic": {"FY2023": 2500000000.0, "FY2024": 2450000000.0, "LTM": 2420000000.0}
            }
        }

        fs_path = Path(self.test_dir) / "financial_statements.json"
        with open(fs_path, "w", encoding="utf-8") as f:
            json.dump(bank_fs, f)

        # Cargar mock cache para que market_cap_usd_m no sea None en este test
        from pipeline.market_data_provider import MarketDataExtractor
        import time
        cache = MarketDataExtractor._load_cache()
        cache["SYNBANK"] = {
            "price": 10.0,
            "market_cap_usd_m": 25000.0,
            "diluted_shares": 2500000000.0,
            "timestamp_epoch": time.time() + 999999,
            "is_offline": True
        }
        MarketDataExtractor._save_cache(cache)

        res = calculate_fundamental_scores(
            ticker="SYNBANK",
            financials_json_path=fs_path,
            out_dir=Path(self.test_dir)
        )

        # 1. Persistencia de Arquetipo
        self.assertEqual(res["archetype"], "FINANCIAL_BANKING")
        self.assertEqual(res["scoring_results"]["archetype"], "FINANCIAL_BANKING")

        # 2. Inhibición en latest_diagnosis
        latest_diag = res["latest_diagnosis"]
        self.assertEqual(latest_diag["solvency_credit"]["altman_zone"], "NO APLICABLE")
        self.assertFalse(latest_diag["greenblatt_roc"]["is_applicable"])
        self.assertEqual(latest_diag["greenblatt_roc"]["roc_rating"], "NO APLICABLE")
        self.assertEqual(latest_diag["roic_wacc"]["model_type"], "COST_OF_EQUITY_KE")

        # 3. Archivos en disco
        out_scores = Path(self.test_dir) / "fundamental_scores.json"
        self.assertTrue(out_scores.exists())
        with open(out_scores, "r", encoding="utf-8") as f:
            saved = json.load(f)
        self.assertEqual(saved["archetype"], "FINANCIAL_BANKING")
        self.assertEqual(saved["debt_and_solvency_analysis"]["latest_result"]["distress_models"]["altman_zone"], "NO APLICABLE")


class TestRealCorpusArtifactIntegrity(unittest.TestCase):
    """Auditoría forense sobre los artefactos reales de las 8 compañías procesadas en el proyecto."""

    def test_corpus_8_companies_archetype_and_decoupling_integrity(self):
        """Verifica que los 8 emisores del proyecto cumplan estrictamente sus contratos contables."""
        expected_contracts = {
            "AAPL": {"archetype": "STANDARD_CORPORATE", "altman_inhibited": False, "roc_inhibited": False, "wacc_model": "WACC", "debt_free": False},
            "DECK": {"archetype": "STANDARD_CORPORATE", "altman_inhibited": False, "roc_inhibited": False, "wacc_model": "WACC", "debt_free": True},
            "JPM": {"archetype": "FINANCIAL_BANKING", "altman_inhibited": True, "roc_inhibited": True, "wacc_model": "COST_OF_EQUITY_KE", "debt_free": False},
            "NU": {"archetype": "FINANCIAL_BANKING", "altman_inhibited": True, "roc_inhibited": True, "wacc_model": "COST_OF_EQUITY_KE", "debt_free": False},
            "PGR": {"archetype": "INSURANCE", "altman_inhibited": True, "roc_inhibited": True, "wacc_model": "COST_OF_EQUITY_KE", "debt_free": False},
            "O": {"archetype": "REAL_ESTATE_REIT", "altman_inhibited": False, "roc_inhibited": False, "wacc_model": "WACC", "debt_free": False},
            "MELI": {"archetype": "PLATFORM_ECOSYSTEM", "altman_inhibited": False, "roc_inhibited": False, "wacc_model": "WACC", "debt_free": False},
            "NVDA": {"archetype": "STANDARD_CORPORATE", "altman_inhibited": False, "roc_inhibited": False, "wacc_model": "WACC", "debt_free": False},
        }

        for ticker, contract in expected_contracts.items():
            f_path = PROJECT_ROOT / "data" / "processed" / ticker / "fundamental_scores.json"
            self.assertTrue(f_path.exists(), f"Artefacto fundamental_scores.json no existe para {ticker}")

            with open(f_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Verificar arquetipo canónico en raíz y scoring_results
            self.assertEqual(data.get("archetype"), contract["archetype"], f"{ticker} fallo en arquetipo raiz")
            self.assertEqual(data.get("scoring_results", {}).get("archetype"), contract["archetype"], f"{ticker} fallo en scoring_results.archetype")

            # Verificar inhibición de Altman Z''
            latest_solv = data.get("debt_and_solvency_analysis", {}).get("latest_result", {})
            dist = latest_solv.get("distress_models", {})
            if contract["altman_inhibited"]:
                self.assertEqual(dist.get("altman_zone"), "NO APLICABLE", f"{ticker} debio inhibir Altman Z''")
                self.assertFalse(dist.get("is_applicable"), f"{ticker} debio marcar Altman is_applicable=False")
                self.assertEqual(latest_solv.get("global_badge"), "SOLVENCIA REGULATORIA")
            else:
                self.assertNotEqual(dist.get("altman_zone"), "NO APLICABLE", f"{ticker} no debio inhibir Altman Z''")
                self.assertTrue(dist.get("is_applicable"), f"{ticker} debio marcar Altman is_applicable=True")

            # Verificar inhibición de Greenblatt ROC
            roc = data.get("greenblatt_roc_analysis", {})
            if contract["roc_inhibited"]:
                self.assertFalse(roc.get("is_applicable"), f"{ticker} debio marcar ROC is_applicable=False")
                self.assertEqual(roc.get("rating"), "NO APLICABLE", f"{ticker} debio marcar ROC rating=NO APLICABLE")
                self.assertIsNone(roc.get("latest_roc"), f"{ticker} latest_roc debe ser None")
            else:
                self.assertTrue(roc.get("is_applicable"), f"{ticker} debio marcar ROC is_applicable=True")
                self.assertNotEqual(roc.get("rating"), "NO APLICABLE", f"{ticker} no debio marcar ROC rating=NO APLICABLE")

            # Verificar WACC vs Ke
            wacc_data = data.get("wacc_analysis", {})
            self.assertEqual(wacc_data.get("model_type"), contract["wacc_model"], f"{ticker} fallo en wacc model_type")

            # Verificar deuda y no falsos debt-free
            is_debt_free = latest_solv.get("is_debt_free")
            if contract["debt_free"]:
                self.assertTrue(is_debt_free, f"{ticker} debio ser is_debt_free=True")
            else:
                self.assertFalse(is_debt_free, f"{ticker} no debio ser marcado como is_debt_free=True")


class TestUniversalScaleInvarianceNoTickerHardcoding(unittest.TestCase):
    """Verificación de la Regla 4 de AGENTS.md: Cero hardcoding de tickers en pipeline/financial_scoring_engine.py."""

    def test_no_hardcoded_ticker_branches_in_scoring_engine(self):
        """Verifica que no existan sentencias del tipo 'if ticker == ...' o 'elif ticker == ...' en las decisiones de scoring."""
        engine_path = PROJECT_ROOT / "pipeline" / "financial_scoring_engine.py"
        with open(engine_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        prohibited_tickers = ["AAPL", "DECK", "JPM", "MELI", "NU", "NVDA", "O", "PGR"]
        violations = []

        for idx, line in enumerate(lines, start=1):
            stripped = line.strip()
            # Ignorar comentarios o docstrings
            if stripped.startswith("#") or stripped.startswith('"""') or stripped.startswith("*"):
                continue
            # Ignorar bloque __main__ de testing CLI
            if idx > 3830:
                continue

            for t in prohibited_tickers:
                # Buscar patrones if ticker == "TICKER" o ticker in ["...", "..."]
                if f'ticker == "{t}"' in line or f"ticker == '{t}'" in line or f'ticker.upper() == "{t}"' in line:
                    violations.append(f"Línea {idx}: {line.strip()}")
                if f'if ticker in [' in line and t in line:
                    violations.append(f"Línea {idx}: {line.strip()}")

        self.assertEqual(len(violations), 0, f"Violación de Regla 4 de AGENTS.md detectada en scoring_engine: {violations}")


class TestAdversarialVulnerabilitiesAndEdgeCases(unittest.TestCase):
    """Pruebas de vulnerabilidades adversariales y casos límite en el motor de scoring."""

    def test_forensic_engine_unhandled_typeerror_on_none_montier_score(self):
        """
        [VULNERABILIDAD FORENSE] Verifica si ForensicAccountingEngine falla con TypeError
        cuando se procesa un balance con un solo período fiscal o donde el Montier C-Score total_score es None.
        En líneas 2593 y 2601 de financial_scoring_engine.py:
            elif montier_sc >= 4 or ...
        provoca TypeError: '>=' not supported between instances of 'NoneType' and 'int'.
        """
        from pipeline.financial_scoring_engine import ForensicAccountingEngine
        single_period_metrics = {
            "FY2024": {
                "total_assets": 10000.0,
                "net_income": 1000.0,
                "cfo": 1200.0
            }
        }
        res = ForensicAccountingEngine.calculate_forensic_series(
            fiscal_years=["FY2024"],
            period_metrics=single_period_metrics,
            benchmarks={},
            ticker="VULN_TEST"
        )
        self.assertIsNotNone(res)
        self.assertIn("latest_result", res)
        latest_res = res["latest_result"]
        self.assertIn("forensic_verdict", latest_res)
        self.assertIn("montier_c_score", latest_res)

    def test_bank_altman_inhibition_with_zero_assets_extreme(self):
        """Verifica que un banco con activos 0.0 o balance anómalo no rompa la inhibición de Altman Z''."""
        zero_asset_metrics = {
            "FY2024": {
                "total_assets": 0.0,
                "total_liabilities": 0.0,
                "stockholders_equity": 0.0,
                "total_debt": 0.0
            }
        }
        res = DebtSolvencyEngine.calculate_solvency_series(
            fiscal_years=["FY2024"],
            period_metrics=zero_asset_metrics,
            ticker="ZERO_BANK",
            archetype="FINANCIAL_BANKING"
        )
        dist = res["distress_and_credit_models"]["FY2024"]
        self.assertFalse(dist["is_applicable"])
        self.assertEqual(dist["altman_zone"], "NO APLICABLE")

    def test_scoring_engine_unhandled_typeerror_on_uncached_ticker_market_cap(self):
        """
        [VULNERABILIDAD CRÍTICA LÍNEA 3710] Verifica si calculate_fundamental_scores maneja con seguridad
        tickers sin cotización en caché sin arrojar TypeError.
        """
        import tempfile
        tmp_dir = tempfile.mkdtemp(prefix="test_uncached_mcap_")
        try:
            uncached_fs = {
                "cik": "0000999999",
                "company_name": "UNCACHED TEST CORP",
                "ticker": "UNCACHED_TICKER_XYZ",
                "archetype": "STANDARD_CORPORATE",
                "fiscal_years": ["LTM", "FY2024", "FY2023"],
                "balance_sheet": {
                    "FY2023": {"Assets": 1000000000, "Liabilities": 400000000, "StockholdersEquity": 600000000},
                    "FY2024": {"Assets": 1100000000, "Liabilities": 450000000, "StockholdersEquity": 650000000},
                    "LTM": {"Assets": 1150000000, "Liabilities": 460000000, "StockholdersEquity": 690000000}
                },
                "income_statement": {
                    "FY2023": {"NetIncomeLoss": 100000000, "OperatingIncomeLoss": 150000000},
                    "FY2024": {"NetIncomeLoss": 120000000, "OperatingIncomeLoss": 170000000},
                    "LTM": {"NetIncomeLoss": 130000000, "OperatingIncomeLoss": 180000000}
                },
                "cash_flow": {
                    "FY2023": {"NetCashProvidedByUsedInOperatingActivities": 140000000},
                    "FY2024": {"NetCashProvidedByUsedInOperatingActivities": 160000000},
                    "LTM": {"NetCashProvidedByUsedInOperatingActivities": 170000000}
                },
                "canonical_summary": {
                    "total_debt": {"FY2023": 100000000.0, "FY2024": 110000000.0, "LTM": 115000000.0}
                }
            }
            fs_path = Path(tmp_dir) / "financial_statements.json"
            with open(fs_path, "w", encoding="utf-8") as f:
                json.dump(uncached_fs, f)

            scores = calculate_fundamental_scores(
                ticker="UNCACHED_TICKER_XYZ",
                financials_json_path=fs_path,
                out_dir=Path(tmp_dir)
            )
            self.assertIsNotNone(scores)
            self.assertIn("debt_and_solvency_analysis", scores)
            solv = scores["debt_and_solvency_analysis"]
            self.assertIsNotNone(solv)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
