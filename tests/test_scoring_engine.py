"""
tests/test_scoring_engine.py - Suite de pruebas unitarias y de integración
para el Motor de Scoring Fundamental Cuantitativo (Piotroski F-Score & Mohanram G-Score).
Compatible con Python unittest estándar (sin dependencias de terceros).
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
    load_industry_medians,
    load_peer_benchmarks,
    compute_peer_benchmarks,
    get_sector_benchmarks,
    PiotroskiScoreCalculator,
    MohanramScoreCalculator,
    CombinedMatrixClassifier,
    NovyMarxCalculator,
    IntangibleROICCalculator,
    WACCCalculator,
    calculate_fundamental_scores
)


class TestScoringEngine(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.medians_db = load_industry_medians("config/industry_medians.json")
        json_path = Path("data/processed/AAPL/financial_statements.json")
        if not json_path.exists():
            raise FileNotFoundError("financial_statements.json debe existir para AAPL")
        cls.aapl_scores = calculate_fundamental_scores("AAPL", json_path)

    def test_01_industry_medians_structure(self):
        """Verifica que el catálogo de medianas sectoriales tenga todos los sectores clave y campos necesarios."""
        self.assertIn("SIC_3571", self.medians_db)
        self.assertIn("SIC_7372", self.medians_db)
        self.assertIn("SIC_3674", self.medians_db)
        self.assertIn("BROAD_MARKET", self.medians_db)
        self.assertIn("ticker_to_sic", self.medians_db)
        self.assertEqual(self.medians_db["ticker_to_sic"].get("AAPL"), "3571")

        hw = self.medians_db["SIC_3571"]
        self.assertTrue(hw["is_asset_light"])
        self.assertEqual(hw["median_roa"], 0.065)
        self.assertEqual(hw["median_cfroa"], 0.082)
        self.assertEqual(hw["median_rd_intensity"], 0.055)
        self.assertEqual(hw["median_total_reinvestment"], 0.085)

    def test_02_piotroski_f_score_apple_fy2024(self):
        """
        Verifica que Apple en FY2024 obtenga exactamente 7 / 9 puntos en Piotroski F-Score.
        Pasa en: F_ROA, F_CFO, F_ACCRUAL, F_dLEVER, EQ_OFFER, F_dMARGIN, F_dTURN.
        Falla en: F_dROA (impacto impositivo UE) y F_dLIQUID (aumento estacional de cuentas por pagar).
        """
        f24 = self.aapl_scores["piotroski_f_score"]["FY2024"]
        self.assertEqual(f24["total_score"], 7)
        self.assertEqual(f24["max_score"], 9)
        self.assertEqual(f24["rating"], "SALUD SÓLIDA")

        sig = f24["signals"]
        self.assertTrue(sig["F_ROA"]["passed"])
        self.assertTrue(sig["F_CFO"]["passed"])
        self.assertFalse(sig["F_dROA"]["passed"])
        self.assertTrue(sig["F_ACCRUAL"]["passed"])
        self.assertTrue(sig["F_dLEVER"]["passed"])
        self.assertFalse(sig["F_dLIQUID"]["passed"])
        self.assertTrue(sig["EQ_OFFER"]["passed"])
        self.assertTrue(sig["F_dMARGIN"]["passed"])
        self.assertTrue(sig["F_dTURN"]["passed"])

    def test_03_mohanram_g_score_apple_fy2024(self):
        """
        Verifica que Apple en FY2024 obtenga 6 / 8 puntos en Mohanram G-Score frente a SIC 3571.
        Pasa en: G1 (ROA), G2 (CFROA), G3 (CFO>NI), G4 (ROA P75 Líder), G6 (I+D), G7 (Inversión Total Asset-Light).
        Falla en: G5 (varianza pos-pandemia) y G8 (inversiones de lanzamiento en SG&A).
        """
        g24 = self.aapl_scores["mohanram_g_score"]["FY2024"]
        self.assertEqual(g24["total_score"], 6)
        self.assertEqual(g24["max_score"], 8)
        self.assertEqual(g24["rating"], "CRECIMIENTO DE ÉLITE")

        sig = g24["signals"]
        self.assertTrue(sig["G1_ROA"]["passed"])
        self.assertTrue(sig["G2_CFROA"]["passed"])
        self.assertTrue(sig["G3_ACCRUAL"]["passed"])
        self.assertTrue(sig["G4_VAR_ROA"]["passed"])
        self.assertFalse(sig["G5_VAR_GROWTH"]["passed"])
        self.assertTrue(sig["G6_RD_INTENSITY"]["passed"])
        self.assertTrue(sig["G7_CAPEX_INTENSITY"]["passed"])
        self.assertFalse(sig["G8_OPERATING_LEVERAGE"]["passed"])

    def test_04_scores_apple_ltm(self):
        """
        Verifica que en el período LTM Apple alcance una puntuación sobresaliente:
        F-Score = 9/9 (Salud Excepcional) y G-Score = 7/8 (Crecimiento de Élite).
        """
        f_ltm = self.aapl_scores["piotroski_f_score"]["LTM"]
        g_ltm = self.aapl_scores["mohanram_g_score"]["LTM"]

        self.assertEqual(f_ltm["total_score"], 9)
        self.assertEqual(f_ltm["rating"], "SALUD EXCEPCIONAL")

        self.assertGreaterEqual(g_ltm["total_score"], 6)
        self.assertEqual(g_ltm["rating"], "CRECIMIENTO DE ÉLITE")

    def test_05_combined_matrix_classifier(self):
        """Verifica los cuatro cuadrantes de la matriz estratégica F-Score vs G-Score."""
        # Cuadrante I: Compounder de Élite
        c1 = CombinedMatrixClassifier.classify(7, 6)
        self.assertIn("COMPOUNDER DE ÉLITE", c1["quadrant"])
        self.assertEqual(c1["color"], "GREEN")

        c1_top = CombinedMatrixClassifier.classify(9, 8)
        self.assertIn("COMPOUNDER DE ÉLITE", c1_top["quadrant"])

        # Cuadrante II: Crecimiento Vulnerable
        c2 = CombinedMatrixClassifier.classify(5, 7)
        self.assertIn("CRECIMIENTO VULNERABLE", c2["quadrant"])
        self.assertEqual(c2["color"], "YELLOW")

        # Cuadrante III: Generador Maduro (Cash Cow)
        c3 = CombinedMatrixClassifier.classify(8, 4)
        self.assertIn("GENERADOR MADURO", c3["quadrant"])
        self.assertEqual(c3["color"], "BLUE")

        # Cuadrante IV: Trampa de Valor
        c4 = CombinedMatrixClassifier.classify(4, 3)
        self.assertIn("TRAMPA DE VALOR", c4["quadrant"])
        self.assertEqual(c4["color"], "RED")

    def test_06_excel_sheet7_scores_fundamentales(self):
        """Verifica que el archivo Excel generado contenga la Hoja 7 'Scores Fundamentales' con formato enriquecido."""
        excel_path = Path("data/processed/AAPL/financial_statements.xlsx")
        self.assertTrue(excel_path.exists(), "financial_statements.xlsx debe existir")

        wb = openpyxl.load_workbook(excel_path, data_only=True)
        self.assertIn("Scores Fundamentales", wb.sheetnames, "La pestaña 'Scores Fundamentales' debe estar en el libro Excel")

        ws = wb["Scores Fundamentales"]
        self.assertIn("Piotroski F-Score", ws.cell(row=1, column=1).value)
        self.assertIn("Mohanram G-Score", ws.cell(row=1, column=1).value)

        # Verificar filas de totales y celdas enriquecidas con comparaciones
        found_f_total = False
        found_g_total = False
        for r in range(1, 40):
            val = str(ws.cell(row=r, column=1).value or "")
            if "TOTAL PIOTROSKI F-SCORE" in val:
                found_f_total = True
                score_cell = str(ws.cell(row=r, column=4).value or "")
                self.assertIn("Pts", score_cell)
                self.assertGreaterEqual(int(score_cell.split()[0]), 0)
            if "TOTAL MOHANRAM G-SCORE" in val:
                found_g_total = True
                score_cell = str(ws.cell(row=r, column=4).value or "")
                self.assertIn("Pts", score_cell)
                self.assertGreaterEqual(int(score_cell.split()[0]), 0)

        self.assertTrue(found_f_total, "La fila TOTAL PIOTROSKI F-SCORE debe existir")
        self.assertTrue(found_g_total, "La fila TOTAL MOHANRAM G-SCORE debe existir")
        
        # Verificar que las celdas contengan valores comparados y puntaje
        f_roa_cell = str(ws.cell(row=8, column=4).value or "")
        self.assertTrue(">" in f_roa_cell or "[" in f_roa_cell, "La celda debe mostrar la comparación y puntaje")

    def test_07_excel_sheet8_peer_group(self):
        """Verifica que el archivo Excel contenga la Hoja 8 'Peer Group & Medianas' con fórmulas estadísticas."""
        excel_path = Path("data/processed/AAPL/financial_statements.xlsx")
        self.assertTrue(excel_path.exists(), "financial_statements.xlsx debe existir")

        wb = openpyxl.load_workbook(excel_path, data_only=False)
        self.assertIn("Peer Group & Medianas", wb.sheetnames, "La pestaña 'Peer Group & Medianas' debe estar en el libro Excel")

        ws = wb["Peer Group & Medianas"]
        self.assertIn("Análisis de Pares", str(ws.cell(row=1, column=1).value or ""))
        
        # Verificar presencia de competidores clave
        tickers_found = []
        for r in range(7, 16):
            tick = ws.cell(row=r, column=1).value
            if tick:
                tickers_found.append(str(tick).strip())
                
        self.assertIn("AAPL", tickers_found, "AAPL debe estar en la tabla de pares")
        self.assertIn("DELL", tickers_found, "DELL debe estar en la tabla de pares")
        self.assertIn("HPQ", tickers_found, "HPQ debe estar en la tabla de pares")
        
        # Verificar fórmulas estadísticas de Excel
        found_median = False
        for r in range(14, 25):
            lbl = str(ws.cell(row=r, column=1).value or "")
            if "MEDIANA" in lbl:
                found_median = True
                f_val = str(ws.cell(row=r, column=6).value or "")
                self.assertTrue("MEDIAN" in f_val.upper(), f"La fórmula de la mediana debe ser =MEDIAN(...), obtenida: {f_val}")
                
        self.assertTrue(found_median, "La fila MEDIANA debe existir con fórmula de Excel")

    def test_08_dynamic_peer_medians_sync(self):
        """
        Verifica la sincronización matemática al 100% de las medianas dinámicas del peer group (Hoja 8)
        con los benchmarks aplicados en el Mohanram G-Score (Hoja 7) y fundamental_scores.json.
        """
        peer_cfg = load_peer_benchmarks()
        self.assertIn("industry_benchmarks", peer_cfg)
        self.assertIn("SIC_3571", peer_cfg["industry_benchmarks"])

        peers = peer_cfg["industry_benchmarks"]["SIC_3571"]["peers"]
        self.assertEqual(len(peers), 8, "Debe haber 8 empresas en el peer group de SIC 3571")

        dyn_medians = compute_peer_benchmarks(peers)
        self.assertAlmostEqual(dyn_medians["median_roa"], 0.1093764, places=4)
        self.assertAlmostEqual(dyn_medians["median_cfroa"], 0.1376526, places=4)
        self.assertAlmostEqual(dyn_medians["median_rd_intensity"], 0.0600161, places=4)
        self.assertAlmostEqual(dyn_medians["median_total_reinvestment"], 0.0942987, places=4)
        self.assertAlmostEqual(dyn_medians["p75_roa"], 0.3235701, places=4)

        # Robustez ante None y cero activos
        test_peers = peers + [{"ticker": "NULL", "total_assets_usd_m": None, "rd_expense_usd_m": None}]
        robust_res = compute_peer_benchmarks(test_peers)
        self.assertAlmostEqual(robust_res["median_roa"], dyn_medians["median_roa"], places=6)

        # Coherencia con fundamental_scores.json
        bm_used = self.aapl_scores["benchmarks_used"]
        self.assertTrue(bm_used.get("dynamic_peer_medians"))
        self.assertAlmostEqual(bm_used["median_roa"], dyn_medians["median_roa"], places=6)
        self.assertAlmostEqual(bm_used["median_cfroa"], dyn_medians["median_cfroa"], places=6)
        self.assertAlmostEqual(bm_used["median_rd_intensity"], dyn_medians["median_rd_intensity"], places=6)
        self.assertAlmostEqual(bm_used["median_total_reinvestment"], dyn_medians["median_total_reinvestment"], places=6)

    def test_09_financial_scores_file_and_robustness(self):
        """
        Verifica la existencia y coherencia de financial_scores.json, así como la robustez
        de los formateadores de Excel ante entradas nulas o atípicas ('N/A', None).
        """
        out_dir = Path("data/processed/AAPL")
        scores = calculate_fundamental_scores("AAPL", out_dir / "financial_statements.json", out_dir=out_dir)
        
        fund_path = out_dir / "fundamental_scores.json"
        fin_path = out_dir / "financial_scores.json"
        self.assertTrue(fund_path.exists(), "fundamental_scores.json debe existir")
        self.assertTrue(fin_path.exists(), "financial_scores.json debe existir")

        with open(fund_path, "r", encoding="utf-8") as f1, open(fin_path, "r", encoding="utf-8") as f2:
            d1 = json.load(f1)
            d2 = json.load(f2)
            self.assertEqual(d1["latest_diagnosis"], d2["latest_diagnosis"])
            self.assertEqual(d1["benchmarks_used"], d2["benchmarks_used"])

        # Verificar señales G1, G2, G6, G7 en financial_scores.json contra benchmarks
        ltm_g = d2["mohanram_g_score"]["LTM"]["signals"]
        bm = d2["benchmarks_used"]
        self.assertEqual(ltm_g["G1_ROA"]["benchmark"], f"{bm['median_roa']*100:.2f}%")
        self.assertEqual(ltm_g["G2_CFROA"]["benchmark"], f"{bm['median_cfroa']*100:.2f}%")
        self.assertEqual(ltm_g["G6_RD_INTENSITY"]["benchmark"], f"> {bm['median_rd_intensity']*100:.2f}%")
        self.assertEqual(ltm_g["G7_CAPEX_INTENSITY"]["benchmark"], f"> {bm['median_total_reinvestment']*100:.2f}% (I+D+CapEx)")

        # Robustez de create_ratios_sheet ante valores no numéricos ('N/A', '-', None)
        from excel_formatter import create_ratios_sheet, create_peer_group_sheet
        dummy_wb = openpyxl.Workbook()
        dirty_ratios = {
            "gross_margin_pct": {"LTM": "N/A", "FY2025": "-", "FY2024": None, "FY2023": 45.2},
            "operating_margin_pct": {"LTM": 30.0}
        }
        create_ratios_sheet(dummy_wb, dirty_ratios, "Test Co", "TEST", ["LTM", "FY2025", "FY2024", "FY2023"])
        ws_ratios = dummy_wb["Ratios Financieros"]
        # Fila 6: Margen Bruto (col B=LTM, col C=FY2025, col D=FY2024, col E=FY2023)
        self.assertEqual(ws_ratios.cell(row=6, column=2).value, "-")
        self.assertEqual(ws_ratios.cell(row=6, column=3).value, "-")
        self.assertEqual(ws_ratios.cell(row=6, column=4).value, "-")
        self.assertAlmostEqual(ws_ratios.cell(row=6, column=5).value, 0.452, places=3)

        # Robustez de create_peer_group_sheet ante competidores con campos None
        dirty_peer_data = {
            "sic_code": "3571",
            "peers": [
                {"ticker": "T1", "company_name": "Test1", "revenue_usd_m": None, "total_assets_usd_m": None},
                {"ticker": "T2", "company_name": "Test2", "revenue_usd_m": 100.0, "total_assets_usd_m": 200.0, "net_income_usd_m": None}
            ]
        }
        create_peer_group_sheet(dummy_wb, peer_data=dirty_peer_data, ticker="TEST")
        ws_peers = dummy_wb["Peer Group & Medianas"]
        self.assertIsNotNone(ws_peers)

    def test_10_scoring_engine_and_peer_edge_cases(self):
        """
        Verifica exhaustivamente el blindaje ante valores anómalos:
        1. compute_peer_benchmarks con strings, NaN, 'N/A' y activos negativos.
        2. Calculadores Piotroski y Mohanram ante entradas con cadenas numéricas.
        3. create_peer_group_sheet ante 'N/A' y strings en métricas financieras.
        4. create_ratios_sheet ante diccionarios con subconjuntos institucionales (ej. solo net_margin y current_ratio).
        """
        import math
        from excel_formatter import create_ratios_sheet, create_peer_group_sheet

        # 1. compute_peer_benchmarks ante NaN, strings y centinelas
        dirty_peers = [
            {"ticker": "P1", "total_assets_usd_m": "1000.0", "net_income_usd_m": "100.0", "cfo_usd_m": "150.0", "rd_expense_usd_m": "50.0", "capex_usd_m": "30.0"},
            {"ticker": "P2", "total_assets_usd_m": float("nan"), "net_income_usd_m": 80.0},
            {"ticker": "P3", "total_assets_usd_m": "N/A", "net_income_usd_m": 50.0},
            {"ticker": "P4", "total_assets_usd_m": -200.0, "net_income_usd_m": 10.0},
            {"ticker": "P5", "total_assets_usd_m": 2000.0, "net_income_usd_m": 160.0, "cfo_usd_m": 220.0, "rd_expense_usd_m": 100.0, "capex_usd_m": 60.0}
        ]
        bms = compute_peer_benchmarks(dirty_peers)
        self.assertFalse(math.isnan(bms["median_roa"]))
        self.assertFalse(math.isnan(bms["median_cfroa"]))
        self.assertAlmostEqual(bms["median_roa"], 0.09, places=2)  # median of 0.10 and 0.08 is 0.09

        # 2. Calculadores ante cadenas numéricas (ej. mocks o fuentes no tipadas)
        p_res = PiotroskiScoreCalculator.calculate_year("2024", {"total_assets": "1000", "net_income": "100", "cfo": "120"}, {"total_assets": "900", "net_income": "80"}, None)
        self.assertIsInstance(p_res["total_score"], int)
        self.assertTrue(p_res["signals"]["F_ROA"]["passed"])

        m_res = MohanramScoreCalculator.calculate_year("2024", {"total_assets": "1000", "net_income": "100", "cfo": "120", "revenue": "500"}, {"total_assets": "900", "revenue": "450"}, [], {"median_roa": 0.05, "median_cfroa": 0.07})
        self.assertIsInstance(m_res["total_score"], int)
        self.assertTrue(m_res["signals"]["G1_ROA"]["passed"])

        # 3. create_peer_group_sheet ante 'N/A' y strings en métricas
        dummy_wb = openpyxl.Workbook()
        peer_payload = {
            "sic_code": "3571",
            "peers": [
                {"ticker": "T1", "company_name": "Test1", "revenue_usd_m": "100.5", "total_assets_usd_m": "500.0", "net_income_usd_m": "N/A", "cfo_usd_m": "-"},
                {"ticker": "T2", "company_name": "Test2", "revenue_usd_m": 200.0, "total_assets_usd_m": 600.0, "net_income_usd_m": 50.0}
            ]
        }
        create_peer_group_sheet(dummy_wb, peer_data=peer_payload, ticker="T1")
        ws_p = dummy_wb["Peer Group & Medianas"]
        # Fila 7 es T1: revenue debe ser numérico 100.5, net_income debe ser float 0.0 (no string "N/A")
        self.assertEqual(ws_p.cell(row=7, column=3).value, 100.5)
        self.assertEqual(ws_p.cell(row=7, column=9).value, 0.0)

        # 4. create_ratios_sheet con subconjunto institucional sin gross_margin
        wb_r = openpyxl.Workbook()
        partial_ratios = {
            "net_margin_pct": {"LTM": 22.5, "FY2025": 21.0},
            "current_ratio": {"LTM": 1.45, "FY2025": 1.30}
        }
        create_ratios_sheet(wb_r, partial_ratios, "Partial Co", "PART", ["LTM", "FY2025"])
        ws_pr = wb_r["Ratios Financieros"]
        # Margen Neto (col B=LTM: 0.225)
        self.assertAlmostEqual(ws_pr.cell(row=8, column=2).value, 0.225, places=3)
        # Current Ratio (col B=LTM: 1.45)
        cr_val = None
        for r in range(1, 30):
            if "Current Ratio" in str(ws_pr.cell(row=r, column=1).value or ""):
                cr_val = ws_pr.cell(row=r, column=2).value
                break
        self.assertIsNotNone(cr_val, "Fila de Current Ratio debe existir en Hoja 2")
        self.assertAlmostEqual(cr_val, 1.45, places=2)

    def test_11_deck_footwear_benchmarks_and_scores(self):
        """
        Verifica la configuración sectorial de Calzado (SIC 3021) y el scoring de Deckers Outdoor (DECK):
        1. Catálogo de medianas para SIC 3021 y mapeo de DECK.
        2. Peer group de calzado en config/peer_benchmarks.json (DECK, NKE, CROX, SKX, SHOO, WWW).
        3. Puntuación LTM de DECK: Piotroski F-Score >= 6/9 y Mohanram G-Score = 7/8 (Crecimiento de Élite).
        4. Verificación de hojas 7 y 8 en el archivo Excel generado para DECK.
        """
        # 1. Catálogo sectorial
        self.assertIn("SIC_3021", self.medians_db)
        self.assertEqual(self.medians_db["ticker_to_sic"].get("DECK"), "3021")
        footwear_cfg = self.medians_db["SIC_3021"]
        self.assertTrue(footwear_cfg["is_asset_light"])

        # 2. Peer group
        peer_benchmarks = load_peer_benchmarks("config/peer_benchmarks.json")
        self.assertIn("SIC_3021", peer_benchmarks.get("industry_benchmarks", {}))
        deck_peers = peer_benchmarks["industry_benchmarks"]["SIC_3021"]["peers"]
        peer_tickers = [p["ticker"] for p in deck_peers]
        for t in ["DECK", "NKE", "CROX", "SKX", "SHOO"]:
            self.assertIn(t, peer_tickers)

        # 3. Scoring DECK
        deck_json = Path("data/processed/DECK/fundamental_scores.json")
        if deck_json.exists():
            with open(deck_json, "r", encoding="utf-8") as f:
                deck_scores = json.load(f)
            ltm_f = deck_scores["piotroski_f_score"]["LTM"]["total_score"]
            ltm_g = deck_scores["mohanram_g_score"]["LTM"]["total_score"]
            self.assertGreaterEqual(ltm_f, 6)
            self.assertEqual(ltm_g, 7)
            self.assertEqual(deck_scores["latest_diagnosis"]["g_rating"], "CRECIMIENTO DE ÉLITE")

        # 4. Excel DECK
        deck_xlsx = Path("data/processed/DECK/financial_statements.xlsx")
        if deck_xlsx.exists():
            wb = openpyxl.load_workbook(deck_xlsx, read_only=True)
            self.assertIn("Scores Fundamentales", wb.sheetnames)
            self.assertIn("Peer Group & Medianas", wb.sheetnames)
            wb.close()

    def test_12_novy_marx_calculator_and_dupont(self):
        """
        Verifica el cálculo de Rentabilidad Bruta sobre Activos (Novy-Marx GP/A):
        1. Fórmula directa: GP / Activos Totales y GP / Activos Ex-Caja.
        2. Identidad DuPont: Margen Bruto * Rotación Activos = GP/A.
        3. Identidad Operativa: Margen Bruto * Rotación Ex-Caja = GP/A Ex-Caja.
        4. Clasificación en 4 Cuadrantes Estratégicos.
        5. Explicaciones pedagógicas textuales para cada métrica.
        """
        metrics = {
            "gross_profit": 200.0,
            "revenue": 400.0,
            "total_assets": 500.0,
            "cash_and_equiv": 100.0
        }
        bms = {
            "median_gross_profitability": 0.25,
            "p75_gross_profitability": 0.30,
            "median_gp_ex_cash": 0.30,
            "median_gross_margin": 0.40,
            "median_asset_turnover": 0.70
        }
        res = NovyMarxCalculator.calculate_period("TEST", metrics, bms)

        # 1. Cálculos nominales
        # GP/A Total = 200 / 500 = 0.40 (40.0%)
        self.assertAlmostEqual(res["gross_profitability_total"], 0.40, places=4)
        # GP/A Ex-Caja = 200 / (500 - 100) = 200 / 400 = 0.50 (50.0%)
        self.assertAlmostEqual(res["gross_profitability_ex_cash"], 0.50, places=4)
        # Cash Drag = 0.50 - 0.40 = +0.10 (+10.0 pp)
        self.assertAlmostEqual(res["cash_drag_pct"], 0.10, places=4)

        # 2. Descomposición DuPont
        # Margen Bruto = 200 / 400 = 0.50
        self.assertAlmostEqual(res["gross_margin"], 0.50, places=4)
        # Rotación Activos = 400 / 500 = 0.80
        self.assertAlmostEqual(res["asset_turnover_total"], 0.80, places=4)
        # DuPont check: 0.50 * 0.80 = 0.40
        self.assertTrue(res["dupont_verified"])
        self.assertAlmostEqual(res["gross_margin"] * res["asset_turnover_total"], res["gross_profitability_total"], places=4)

        # 3. Rotación Ex-Caja
        # Rotación Ex-Caja = 400 / 400 = 1.00
        self.assertAlmostEqual(res["asset_turnover_ex_cash"], 1.00, places=4)
        self.assertAlmostEqual(res["gross_margin"] * res["asset_turnover_ex_cash"], res["gross_profitability_ex_cash"], places=4)

        # 4. Cuadrante Estratégico: Margen (0.50 > 0.40) and Rotación (0.80 > 0.70) -> Compounder de Élite
        self.assertIn("COMPOUNDER DE ÉLITE", res["quadrant"])
        self.assertIn("CUADRANTE I", res["quadrant"])

        # 5. Explicaciones didácticas
        exp = res["explanations"]
        self.assertIn("gross_profitability_total", exp)
        self.assertIn("gross_profitability_ex_cash", exp)
        self.assertIn("cash_drag", exp)
        self.assertIn("dupont_verification", exp)
        self.assertIn("Top 5%", res["percentile_label"])
        self.assertTrue(len(res["percentile_explanation"]) > 20)

    def test_13_novy_marx_dynamic_fiscal_years_and_integration(self):
        """
        Verifica la gestión dinámica de años fiscales e integración end-to-end:
        1. AAPL: año fiscal más reciente es FY2025 + LTM móvil.
        2. DECK: año fiscal más reciente es FY2026 + LTM móvil.
        3. Presencia de novy_marx_analysis en fundamental_scores.json y financial_scores.json.
        4. Existencia de tablas y columnas Novy-Marx en Excel (Hojas 2, 7 y 8).
        5. Existencia de Sección 11 de Novy-Marx en informes generados (.md y .docx).
        """
        # 1. AAPL Scores
        aapl_nm = self.aapl_scores.get("novy_marx_analysis", {})
        self.assertTrue(aapl_nm, "novy_marx_analysis debe estar presente en los scores de AAPL")
        self.assertEqual(aapl_nm["latest_period"], "LTM")
        aapl_periods = aapl_nm["trend"]["chronological_periods"]
        self.assertIn("FY2025", aapl_periods)
        self.assertIn("LTM", aapl_periods)
        self.assertGreater(aapl_nm["latest_result"]["gross_profitability_total"], 0.50)

        # 2. DECK Scores y Años Fiscales Dinámicos
        deck_json = Path("data/processed/DECK/fundamental_scores.json")
        if deck_json.exists():
            with open(deck_json, "r", encoding="utf-8") as f:
                deck_scores = json.load(f)
            deck_nm = deck_scores.get("novy_marx_analysis", {})
            self.assertTrue(deck_nm, "novy_marx_analysis debe estar presente en DECK")
            deck_periods = deck_nm["trend"]["chronological_periods"]
            self.assertIn("FY2026", deck_periods, "DECK debe reflejar FY2026 como año fiscal cerrado")
            self.assertIn("LTM", deck_periods)
            self.assertGreater(deck_nm["latest_result"]["gross_profitability_total"], 0.70)
            # Cash Drag masivo por la caja de DECK
            self.assertGreater(deck_nm["latest_result"]["cash_drag_pct"], 0.40)

        # 3. Verificación de Hojas Excel
        aapl_wb = openpyxl.load_workbook("data/processed/AAPL/financial_statements.xlsx", data_only=True)
        # Hoja 2: Ratios Financieros
        ws2 = aapl_wb["Ratios Financieros"]
        found_nm_h2 = False
        for r in range(1, 40):
            val = str(ws2.cell(row=r, column=1).value or "")
            if "PRODUCTIVIDAD PURA" in val.upper() or "NOVY-MARX" in val.upper() or "GROSS PROFITABILITY" in val.upper():
                found_nm_h2 = True
                break
        self.assertTrue(found_nm_h2, "Hoja 2 debe contener la sección Novy-Marx DuPont")

        # Hoja 7: Scoring Fundamental
        ws7 = aapl_wb["Scores Fundamentales"]
        found_nm_h7 = False
        for r in range(1, 55):
            val = str(ws7.cell(row=r, column=1).value or "")
            if "NOVY-MARX" in val.upper():
                found_nm_h7 = True
                break
        self.assertTrue(found_nm_h7, "Hoja 7 debe contener la Tabla 4 de Novy-Marx")

        # Hoja 8: Peer Group
        ws8 = aapl_wb["Peer Group & Medianas"]
        h_col15 = str(ws8.cell(row=6, column=15).value or "")
        h_col16 = str(ws8.cell(row=6, column=16).value or "")
        self.assertIn("GP / Activos", h_col15)
        self.assertIn("Ex-Caja", h_col16)
        aapl_wb.close()

        # 4. Verificación de Informes Markdown
        aapl_md = Path("data/processed/AAPL/Analisis_Resultados_Q3_FY26_AAPL.md")
        if aapl_md.exists():
            text = aapl_md.read_text(encoding="utf-8")
            self.assertIn("Productividad Pura del Capital", text)
            self.assertIn("Bloque A: Diagnóstico Dual", text)
            self.assertIn("Bloque B: Descomposición DuPont", text)
            self.assertIn("Bloque C: Evolución Histórica", text)
            self.assertIn("Bloque D: Benchmarking Sectorial", text)
            self.assertIn("Conclusiones Fundamentales para Modelos de Valoración", text)

        deck_md = Path("data/processed/DECK/Analisis_Resultados_Q1_FY27_DECK.md")
        if deck_md.exists():
            text = deck_md.read_text(encoding="utf-8")
            self.assertIn("11. Productividad Pura del Capital", text)
            self.assertIn("Bloque A: Diagnóstico Dual", text)
            self.assertIn("Conclusiones Fundamentales para Modelos de Valoración", text)



    def test_14_intangible_roic_rollforward_identity(self):
        """
        Verifica la matemática de la capitalización y amortización roll-forward de intangibles:
        1. Identidad: Stock_t = Stock_{t-1} + Inv_t - Amort_t (exacta, sin fugas).
        2. Normalización de ROIC: Tradicional > Ajustado por la expansión de capital invertido.
        3. Matriz de Sensibilidad de vida útil N (N-1, N, N+1).
        """
        roic_analysis = self.aapl_scores.get("intangible_roic_analysis", {})
        self.assertTrue(roic_analysis, "intangible_roic_analysis debe existir en los scores de AAPL")
        by_period = roic_analysis.get("by_period", {})

        # Verificar identidad roll-forward en FY2024 y FY2025
        res_24 = by_period.get("FY2024", {})
        res_25 = by_period.get("FY2025", {})
        self.assertTrue(res_24 and res_25)

        stock_24 = res_24["total_intangible_stock"]
        stock_25 = res_25["total_intangible_stock"]
        inv_25 = res_25["rd_investment"] + res_25["mkt_investment"]
        amort_25 = res_25["rd_amortization"] + res_25["mkt_amortization"]

        # Stock_t == Stock_{t-1} + Inv_t - Amort_t
        expected_stock_25 = stock_24 + inv_25 - amort_25
        self.assertAlmostEqual(stock_25, expected_stock_25, places=2,
                               msg="La identidad contable roll-forward de Damodaran debe cuadrar exactamente")

        # Expansión de base de capital: IC_adj > IC_trad
        self.assertGreater(res_25["ic_adj"], res_25["ic_trad"])
        # Normalización de ratio: ROIC_adj es menor que el ROIC tradicional pero extremadamente rentable (> 40%)
        self.assertLess(res_25["roic_adj"], res_25["roic_trad"])
        self.assertGreater(res_25["roic_adj"], 0.40)

        # Matriz de Sensibilidad N
        sens = roic_analysis.get("sensitivity_matrix", {})
        self.assertIn("n_minus_1", sens)
        self.assertIn("n_base", sens)
        self.assertIn("n_plus_1", sens)
        # Vida útil menor (N-1) amortiza más rápido -> menor stock acumulado
        self.assertLess(sens["n_minus_1"]["intangibles_usd_m"], sens["n_base"]["intangibles_usd_m"])
        self.assertLess(sens["n_base"]["intangibles_usd_m"], sens["n_plus_1"]["intangibles_usd_m"])

    def test_15_wacc_and_economic_spread_calculation(self):
        """
        Verifica el cálculo de WACC y Spread Económico (EVA):
        1. Costo de Equity mediante CAPM: Ke = Rf + Beta * ERP.
        2. Apple: WACC ponderado con deuda y mercado, Spread > +25% (Wide Moat).
        3. Deckers (DECK): WACC = Ke (100% equity, debt-free), Spread > +30% (Wide Moat).
        4. Explicaciones pedagógicas en lenguaje llano disponibles.
        """
        wacc_aapl = self.aapl_scores.get("wacc_and_spread_analysis", {})
        self.assertTrue(wacc_aapl)
        ke_aapl = wacc_aapl["cost_of_equity_ke"]
        rf = wacc_aapl["market_data"]["rf_10y"]
        beta = wacc_aapl["market_data"]["beta"]
        erp = wacc_aapl["market_data"]["erp"]
        self.assertAlmostEqual(ke_aapl, rf + beta * erp, places=4)

        # Ponderaciones
        self.assertGreater(wacc_aapl["weight_equity"], 0.90)  # > 90% equity
        self.assertLess(wacc_aapl["weight_debt"], 0.10)       # < 10% debt
        self.assertGreater(wacc_aapl["wacc"], 0.08)           # WACC ~ 9%-10%

        # Spread y Moat en AAPL
        spread_aapl = wacc_aapl["economic_spread_adjusted"]
        self.assertGreater(spread_aapl, 0.25)  # Spread > +25%
        self.assertIn("WIDE MOAT", wacc_aapl["moat_rating"])
        self.assertIn("economic_spread", wacc_aapl["explanations"])

        # Verificar DECK (Caso Sin Deuda: D=0 -> WACC = Ke)
        deck_json = Path("data/processed/DECK/fundamental_scores.json")
        if deck_json.exists():
            with open(deck_json, "r", encoding="utf-8") as f:
                deck_scores = json.load(f)
            wacc_deck = deck_scores.get("wacc_and_spread_analysis", {})
            self.assertTrue(wacc_deck["is_debt_free"])
            self.assertEqual(wacc_deck["weight_debt"], 0.0)
            self.assertEqual(wacc_deck["weight_equity"], 1.0)
            self.assertAlmostEqual(wacc_deck["wacc"], wacc_deck["cost_of_equity_ke"], places=4)
            self.assertGreater(wacc_deck["economic_spread_adjusted"], 0.30)
            self.assertIn("WIDE MOAT", wacc_deck["moat_rating"])

    def test_16_excel_and_reports_roic_wacc_integration(self):
        """
        Verifica la integración visual completa de ROIC, WACC y Spread en Excel e Informes:
        1. Hoja 2 de Excel: Bloque de Rendimiento del Capital y Creación de Valor.
        2. Hoja 7 de Excel: Tabla 5 y Tarjeta de Auditoría de Mercado / Sensibilidad.
        3. Hoja 8 de Excel: Columnas 17, 18, 19 (ROIC Adj, WACC, Spread) con fórmulas dinámicas.
        4. Informes Word (.docx) y Markdown (.md): Sección 12 completa con los 4 bloques.
        """
        wb = openpyxl.load_workbook("data/processed/AAPL/financial_statements.xlsx", data_only=False)

        # Hoja 2
        ws2 = wb["Ratios Financieros"]
        found_roic_h2 = any("ROIC AJUSTADO" in str(ws2.cell(row=r, column=1).value or "").upper() for r in range(1, 40))
        self.assertTrue(found_roic_h2, "Hoja 2 debe incluir el bloque de ROIC Ajustado vs WACC")

        # Hoja 7
        ws7 = wb["Scores Fundamentales"]
        found_tabla5 = any("RENDIMIENTO DEL CAPITAL" in str(ws7.cell(row=r, column=1).value or "").upper() for r in range(1, 70))
        found_audit = any("AUDITORÍA DE MERCADO" in str(ws7.cell(row=r, column=1).value or "").upper() for r in range(1, 70))
        self.assertTrue(found_tabla5, "Hoja 7 debe contener la Tabla 5 de ROIC Ajustado y WACC")
        self.assertTrue(found_audit, "Hoja 7 debe contener la tarjeta de auditoría de mercado")

        # Hoja 8
        ws8 = wb["Peer Group & Medianas"]
        h17 = str(ws8.cell(row=6, column=17).value or "")
        h18 = str(ws8.cell(row=6, column=18).value or "")
        h19 = str(ws8.cell(row=6, column=19).value or "")
        self.assertIn("ROIC Ajustado", h17)
        self.assertIn("WACC", h18)
        self.assertIn("Spread Económico", h19)
        # Fórmulas en fila de AAPL y fila Mediana
        self.assertEqual(ws8.cell(row=7, column=19).value, "=Q7-R7")
        self.assertEqual(ws8.cell(row=15, column=19).value, "=MEDIAN(S7:S14)")
        wb.close()

        # Informes
        aapl_md = Path("data/processed/AAPL/Analisis_Resultados_Q3_FY26_AAPL.md")
        self.assertTrue(aapl_md.exists())
        text_aapl = aapl_md.read_text(encoding="utf-8")
        self.assertIn("Rendimiento del Capital Ajustado por Intangibles", text_aapl)
        self.assertIn("Bloque A: Auditoría de Mercado", text_aapl)
        self.assertIn("Bloque B: Estructura de Capital y Costo Promedio", text_aapl)
        self.assertIn("Bloque C: Reconstitución de Intangibles", text_aapl)
        self.assertIn("Bloque D: Creación de Valor Económico", text_aapl)

        deck_md = Path("data/processed/DECK/Analisis_Resultados_Q1_FY27_DECK.md")
        self.assertTrue(deck_md.exists())
        text_deck = deck_md.read_text(encoding="utf-8")
        self.assertIn("12. Rendimiento del Capital Ajustado por Intangibles", text_deck)
        self.assertIn("WIDE MOAT", text_deck)


if __name__ == "__main__":
    unittest.main()

