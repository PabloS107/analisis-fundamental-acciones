"""
tests/test_solvency_engine.py - Suite de pruebas unitarias y de integración
para el Motor de Solvencia, Deuda, Cobertura y Estrés Financiero (Credit Risk Engine):
- Apalancamiento frente a Flujos de Caja (Net Debt/EBITDA, Net Debt/FCF)
- Cobertura de Carga Financiera (EBIT/Interest, CFO/Interest, Burden %)
- Liquidez Inmediata y Riesgo de Refinanciación (Current, Quick, Cash Ratio, Rollover Risk)
- Modelos Predictivos de Quiebra (Altman Z''-Score de 4 variables)
- Calificación Sintética Crediticia Damodaran (AAA a D con default spreads y probabilidades)
- Auditoría de la Hoja 11 en los libros Excel (AAPL y DECK)
- Generación de secciones en Word (.docx) y Markdown (.md)
"""

import os
import sys
import json
import unittest
from pathlib import Path
import openpyxl
import docx

# Añadir scripts al path
scripts_dir = Path(".agents/skills/fundamental-data-extractor/scripts").resolve()
sys.path.insert(0, str(scripts_dir))

from financial_scoring_engine import (
    DebtSolvencyEngine,
    calculate_fundamental_scores
)
import excel_formatter
from solvency_report_builder import (
    generate_solvency_section_md,
    add_solvency_section_docx
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
        self.assertIn("INFINITA", cov.get("interest_coverage_str"))
        self.assertIn("AAA", dist.get("synthetic_rating"))
        self.assertGreater(dist.get("altman_z_double_prime", 0), 2.6)
        self.assertIn("ZONA SEGURA", dist.get("altman_zone"))

    def test_02_leveraged_company_aapl(self):
        """Verifica que Apple (AAPL) tenga apalancamiento ultra bajo (< 0.5x), cobertura superior (> 30x) y rating AAA."""
        aapl_scores_path = Path("data/processed/AAPL/fundamental_scores.json")
        if not aapl_scores_path.exists():
            self.skipTest("No se encontró fundamental_scores.json de AAPL")

        with open(aapl_scores_path, "r", encoding="utf-8") as f:
            aapl_scores = json.load(f)

        solv = aapl_scores.get("debt_and_solvency_analysis", {})
        self.assertTrue(solv.get("available"))

        latest = solv.get("latest_result", {})
        lev = latest.get("cash_flow_leverage", {})
        cov = latest.get("debt_service", {})
        dist = latest.get("distress_models", {})

        # Deuda Neta / EBITDA debe ser bajo (~0.25x)
        self.assertLess(lev.get("net_debt_to_ebitda", 99.0), 1.0)
        self.assertIn("0.25x", lev.get("net_debt_to_ebitda_str"))

        # Cobertura de intereses > 30x
        self.assertGreater(cov.get("interest_coverage", 0), 30.0)

        # Rating sintético AAA
        self.assertEqual(dist.get("synthetic_rating"), "AAA")
        self.assertGreater(dist.get("altman_z_double_prime", 0), 2.6)
        self.assertIn("ZONA SEGURA", dist.get("altman_zone"))

    def test_03_distress_scenario(self):
        """Verifica que una firma altamente apalancada con pérdidas o cobertura < 1.0x active banderas de estrés y bajo Z-score."""
        distress_metrics = {
            "FY2025": {
                "ebit": 100.0,
                "depreciation_and_amortization": 50.0,
                "cfo": 50.0,
                "capex": 80.0,
                "fcf": -30.0,
                "total_debt": 3000.0,
                "short_term_debt": 1200.0,  # 40% rollover
                "cash": 50.0,
                "current_assets": 400.0,
                "current_liabilities": 1000.0,  # WC negativo
                "inventory": 250.0,
                "accounts_receivable": 80.0,
                "total_assets": 2000.0,
                "total_liabilities": 3500.0,
                "stockholders_equity": -1500.0,
                "retained_earnings": -1200.0,
                "working_capital": -600.0,
                "interest_expense": 250.0,  # EBIT coverage = 0.40x
            }
        }
        res = DebtSolvencyEngine.calculate_solvency_series(["FY2025"], distress_metrics, ticker="DISTRESS_CORP")
        latest = res.get("latest_result", {})

        lev = latest.get("cash_flow_leverage", {})
        cov = latest.get("debt_service", {})
        liq = latest.get("liquidity", {})
        dist = latest.get("distress_models", {})

        # Apalancamiento desmedido
        self.assertFalse(lev.get("is_net_cash"))
        self.assertGreater(lev.get("net_debt_to_ebitda", 0), 10.0)
        self.assertIn("ESPECULATIVO", lev.get("status"))

        # Cobertura insuficiente (< 1.0x)
        self.assertLess(cov.get("interest_coverage", 99.0), 1.0)
        self.assertIn("PELIGRO", cov.get("status"))

        # Liquidez deteriorada
        self.assertLess(liq.get("current_ratio", 99.0), 1.0)
        self.assertGreater(liq.get("rollover_risk_pct", 0), 30.0)

        # Distress models
        self.assertIn("DISTRESS", dist.get("altman_zone"))
        self.assertIn(dist.get("synthetic_rating"), ["CCC", "B-", "B", "B+", "D", "C"])
        self.assertIn("INSOLVENCIA", latest.get("solvency_verdict") + latest.get("global_badge"))

    def test_04_altman_z_score_math(self):
        """Verifica la fórmula matemática exacta del Altman Z''-Score de 4 variables."""
        # Configuración exacta
        # WC = 200, RE = 400, EBIT = 300, Equity = 800, Liab = 1000, Assets = 2000
        # X1 = 200 / 2000 = 0.10
        # X2 = 400 / 2000 = 0.20
        # X3 = 300 / 2000 = 0.15
        # X4 = 800 / 1000 = 0.80
        # Z'' = 6.56*0.10 + 3.26*0.20 + 6.72*0.15 + 1.05*0.80
        #     = 0.656 + 0.652 + 1.008 + 0.84 = 3.156
        metrics = {
            "FY2025": {
                "operating_income": 300.0,
                "ebit": 300.0,
                "depreciation_and_amortization": 50.0,
                "cfo": 320.0,
                "capex": 50.0,
                "fcf": 270.0,
                "total_debt": 600.0,
                "short_term_debt": 100.0,
                "cash": 400.0,
                "current_assets": 800.0,
                "current_liabilities": 600.0,
                "inventory": 100.0,
                "accounts_receivable": 100.0,
                "total_assets": 2000.0,
                "total_liabilities": 1000.0,
                "stockholders_equity": 800.0,
                "retained_earnings": 400.0,
                "working_capital": 200.0,
                "interest_expense": 30.0,
            }
        }
        res = DebtSolvencyEngine.calculate_solvency_series(["FY2025"], metrics, ticker="MATH_TEST")
        dist = res["latest_result"]["distress_models"]

        expected_z = 6.56 * 0.10 + 3.26 * 0.20 + 6.72 * 0.15 + 1.05 * 0.80
        self.assertAlmostEqual(dist["altman_z_double_prime"], round(expected_z, 2), places=2)
        self.assertIn("SEGURA", dist["altman_zone"])

    def test_05_damodaran_rating_mapping(self):
        """Verifica el mapeo correcto de la cobertura de intereses a las calificaciones de Damodaran."""
        # Cobertura infinita / sin deuda -> AAA
        r_inf = DebtSolvencyEngine._get_synthetic_rating(999.0, is_debt_free=True)
        self.assertEqual(r_inf["rating"], "AAA")
        self.assertEqual(r_inf["default_spread_pct"], 0.40)

        # Cobertura 12.0x -> AAA
        r_12 = DebtSolvencyEngine._get_synthetic_rating(12.0)
        self.assertEqual(r_12["rating"], "AAA")

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

    def test_06_excel_sheet_11_audit(self):
        """Audita que los libros Excel de AAPL y DECK contengan exactamente 11 hojas y la Hoja 11 esté completa."""
        for ticker in ["AAPL", "DECK"]:
            excel_path = Path(f"data/processed/{ticker}/financial_statements.xlsx")
            self.assertTrue(excel_path.exists(), f"El archivo {excel_path} debe existir")

            wb = openpyxl.load_workbook(excel_path, data_only=True)
            self.assertEqual(len(wb.sheetnames), 11, f"{ticker} debe tener exactamente 11 hojas")
            self.assertIn(
                "Solvencia & Estrés Financiero",
                wb.sheetnames,
                f"{ticker} debe tener la hoja 'Solvencia & Estrés Financiero'"
            )

            ws = wb["Solvencia & Estrés Financiero"]
            # Verificar banner
            banner_val = str(ws["A4"].value)
            self.assertIn("DICTAMEN GLOBAL DE SOLVENCIA", banner_val)

            # Verificar que las tablas principales existan
            cells_text = [str(cell.value) for row in ws.iter_rows() for cell in row if cell.value is not None]
            full_text_upper = " ".join(cells_text).upper()
            self.assertIn("APALANCAMIENTO", full_text_upper)
            self.assertIn("COBERTURA DE CARGA FINANCIERA", full_text_upper)
            self.assertIn("LIQUIDEZ ESTRICTA", full_text_upper)
            self.assertIn("MODELOS PREDICTIVOS DE QUIEBRA", full_text_upper)
            self.assertIn("ALTMAN Z''", full_text_upper)
            self.assertIn("RATING", full_text_upper)

    def test_07_solvency_report_builder_integration(self):
        """Verifica que los constructores de reportes Word (.docx) y Markdown (.md) se ejecuten sin errores."""
        mock_scoring = {
            "ticker": "TEST",
            "company_name": "Test Corporation",
            "debt_and_solvency_analysis": {
                "available": True,
                "latest_result": {
                    "period": "LTM",
                    "global_badge": "MÁXIMA SOLVENCIA INSTITUCIONAL",
                    "solvency_verdict": "Solvencia sólida de grado de inversión.",
                    "cash_flow_leverage": {
                        "total_debt": 500.0,
                        "cash": 800.0,
                        "net_debt": -300.0,
                        "ebitda": 1000.0,
                        "fcf": 800.0,
                        "net_debt_to_ebitda": -0.3,
                        "net_debt_to_ebitda_str": "CAJA NETA",
                        "net_debt_to_fcf_str": "CAJA NETA",
                        "is_net_cash": True,
                        "status": "EXCELENTE (CAJA NETA)"
                    },
                    "debt_service": {
                        "ebit": 900.0,
                        "cfo": 1000.0,
                        "interest_expense": 20.0,
                        "interest_coverage": 45.0,
                        "interest_coverage_str": "45.0x",
                        "cash_interest_coverage_str": "50.0x",
                        "financial_burden_pct": 2.0,
                        "status": "COBERTURA EXCELENTE"
                    },
                    "liquidity": {
                        "current_ratio": 2.1,
                        "quick_ratio": 1.7,
                        "cash_ratio": 0.8,
                        "rollover_risk_pct": 10.0,
                        "debt_to_capital_pct": 15.0,
                        "status": "LIQUIDEZ HOLGADA"
                    },
                    "distress_models": {
                        "altman_z_double_prime": 4.5,
                        "altman_zone": "ZONA SEGURA",
                        "altman_badge": "🛡️ ZONA SEGURA",
                        "synthetic_rating": "AAA",
                        "synthetic_rating_desc": "Grado Máximo de Inversión",
                        "default_spread_pct": 0.40,
                        "default_probability": "0.50%"
                    }
                }
            }
        }

        # Prueba Markdown
        md_out = generate_solvency_section_md(mock_scoring, "TEST", "Test Corporation", section_num=14)
        self.assertIn("## 14. Solvencia, Deuda y Estrés Financiero", md_out)
        self.assertIn("Altman Z''-Score", md_out)
        self.assertIn("Rating Crediticio Sintético", md_out)

        # Prueba Word
        doc = docx.Document()
        add_solvency_section_docx(doc, mock_scoring, "TEST", "Test Corporation", section_num=14)
        headings = [p.text for p in doc.paragraphs if p.text]
        self.assertTrue(any("Solvencia, Deuda y Estrés Financiero" in h for h in headings))
        self.assertGreaterEqual(len(doc.tables), 3)


if __name__ == "__main__":
    unittest.main()
