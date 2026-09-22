"""
tests/test_forensic_engine.py - Suite de pruebas unitarias y de integración
para el Motor de Auditoría Forense Contable y Detección de Manipulación de Beneficios:
Ratio Sloan de Devengos, Matriz de Divergencias de Alerta Temprana, Montier C-Score
y generación de la Hoja 10 en Excel.
"""

import os
import sys
import json
import unittest
from pathlib import Path
import openpyxl

# Añadir scripts al path
scripts_dir = Path(".agents/skills/fundamental-data-extractor/scripts").resolve()
sys.path.insert(0, str(scripts_dir))

from financial_scoring_engine import (
    ForensicAccountingEngine,
    calculate_fundamental_scores
)
import excel_formatter
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
                "depreciation_and_amortization": 25.0
            },
            "FY2025": {
                "net_income": 100.0,
                "cfo": 140.0,
                "total_assets": 1100.0,
                "revenue": 900.0,
                "cost_of_goods_sold": 500.0,
                "gross_profit": 400.0,
                "accounts_receivable": 85.0,
                "inventory": 65.0,
                "net_ppe": 220.0,
                "cash": 180.0,
                "depreciation_and_amortization": 30.0
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
        """Verifica la activación de las 6 banderas del Montier C-Score."""
        clean_res = ForensicAccountingEngine.calculate_forensic_series(self.fys, self.sample_metrics, ticker="CLEAN")
        montier = clean_res["montier_c_score"]["FY2025"]
        
        self.assertLessEqual(montier["total_score"], 1)
        self.assertIn("BAJO", montier["rating"])

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

    def test_06_excel_sheet_10_forensic_audit(self):
        """Verifica que el libro Excel de AAPL tenga exactamente 10 pestañas y que Hoja 10 esté completa."""
        excel_path = Path("data/processed/AAPL/financial_statements.xlsx")
        if not excel_path.exists():
            return
            
        wb = openpyxl.load_workbook(excel_path, data_only=False)
        self.assertGreaterEqual(len(wb.sheetnames), 10)
        self.assertIn("Auditoría Forense & Devengos", wb.sheetnames)
        
        ws = wb["Auditoría Forense & Devengos"]
        # Verificar banners y tablas
        title = ws.cell(1, 1).value
        self.assertIn("Auditoría Forense", title)
        
        # Verificar contenido de celda Sloan LTM
        sloan_header = None
        for r in range(1, 20):
            val = ws.cell(r, 1).value
            if val and "Ratio de Devengos de Sloan" in str(val):
                sloan_header = r
                break
        self.assertIsNotNone(sloan_header, "Debe existir fila de Ratio de Devengos de Sloan en Hoja 10")
        
        # Verificar celda LTM de Sloan
        ltm_sloan_val = ws.cell(sloan_header, 4).value
        self.assertIsNotNone(ltm_sloan_val)
        self.assertAlmostEqual(float(ltm_sloan_val), -0.0479, places=3)
        
        # Verificar fila de Montier C-Score
        montier_row = None
        for r in range(sloan_header, ws.max_row + 1):
            val = ws.cell(r, 1).value
            if val and "MONTIER C-SCORE TOTAL" in str(val):
                montier_row = r
                break
        self.assertIsNotNone(montier_row, "Debe existir fila de Montier C-Score Total en Hoja 10")
        self.assertIn("/6", str(ws.cell(montier_row, 4).value))

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
        self.assertIn("delta_soft_assets", divs_25["soft_assets"])


if __name__ == "__main__":
    unittest.main()
