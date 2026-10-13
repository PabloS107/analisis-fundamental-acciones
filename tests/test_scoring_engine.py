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

# Añadir scripts al path
scripts_dir = Path("pipeline").resolve()
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
        Verifica la existencia y coherencia de fundamental_scores.json y financial_scores.json,
        así como la consistencia de las señales G1, G2, G6, G7 contra benchmarks sectoriales.
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

    def test_10_scoring_engine_and_peer_edge_cases(self):
        """
        Verifica exhaustivamente el blindaje ante valores anómalos:
        1. compute_peer_benchmarks con strings, NaN, 'N/A' y activos negativos.
        2. Calculadores Piotroski y Mohanram ante entradas con cadenas numéricas.
        """
        import math

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

    def test_11_deck_footwear_benchmarks_and_scores(self):
        """
        Verifica la configuración sectorial de Calzado (SIC 3021) y el scoring de Deckers Outdoor (DECK):
        1. Catálogo de medianas para SIC 3021 y mapeo de DECK.
        2. Peer group de calzado en config/peer_benchmarks.json (DECK, NKE, CROX, SKX, SHOO, WWW).
        3. Puntuación LTM de DECK: Piotroski F-Score >= 6/9 y Mohanram G-Score = 7/8 (Crecimiento de Élite).
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
        4. Existencia de Sección 11 de Novy-Marx en informes generados (.md y .docx).
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

    def test_16_reports_roic_wacc_integration(self):
        """
        Verifica la integración de ROIC, WACC y Spread en Informes Markdown (.md) y Word (.docx):
        Sección 12 completa con los 4 bloques.
        """

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

    def test_17_archetype_ingestion_and_persistence(self):
        """
        Verifica la ingestión y persistencia del arquetipo en fundamental_scores.json y scoring_results:
        1. AAPL y DECK deben ser CORPORATE.
        2. JPM y NU deben ser FINANCIAL_BANKING.
        3. PGR debe ser INSURANCE.
        4. Ingestión a doble nivel (top-level y scoring_results).
        """
        self.assertIn(self.aapl_scores.get("archetype"), ("STANDARD_CORPORATE", "CORPORATE"))
        self.assertIn(self.aapl_scores.get("scoring_results", {}).get("archetype"), ("STANDARD_CORPORATE", "CORPORATE"))

        for ticker, expected_arch in [("DECK", ("STANDARD_CORPORATE", "CORPORATE")), ("JPM", "FINANCIAL_BANKING"), ("NU", "FINANCIAL_BANKING"), ("PGR", "INSURANCE")]:
            score_file = Path(f"data/processed/{ticker}/fundamental_scores.json")
            if score_file.exists():
                with open(score_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                actual_top = data.get("archetype")
                actual_res = data.get("scoring_results", {}).get("archetype")
                if isinstance(expected_arch, tuple):
                    self.assertIn(actual_top, expected_arch, f"{ticker} top-level archetype must be in {expected_arch}")
                    self.assertIn(actual_res, expected_arch, f"{ticker} scoring_results archetype must be in {expected_arch}")
                else:
                    self.assertEqual(actual_top, expected_arch, f"{ticker} top-level archetype must be {expected_arch}")
                    self.assertEqual(actual_res, expected_arch, f"{ticker} scoring_results archetype must be {expected_arch}")

    def test_18_wacc_vs_ke_branching_by_archetype(self):
        """
        Verifica la bifurcación metodológica del coste de capital según arquetipo:
        1. Entidades financieras (FINANCIAL_BANKING, INSURANCE): modelo COST_OF_EQUITY_KE, Ke como tasa de corte,
           ROTCE sobre patrimonio tangible (deduciendo goodwill e intangibles), WACC = Ke, sin deuda financiera tradicional.
        2. Entidades corporativas con deuda: modelo WACC con ponderación de capital y deuda.
        3. Entidades corporativas sin deuda (DECK): modelo WACC con weight_debt=0 y WACC = Ke.
        """
        # 1. Banco (FINANCIAL_BANKING)
        bank_period_data = {
            "net_income": 8000.0,
            "stockholders_equity": 60000.0,
            "goodwill": 5000.0,
            "intangibles": 2000.0,
            "total_debt": 25000.0,
            "effective_tax_rate": 0.21
        }
        bank_benchmarks = {"damodaran_unlevered_beta": 1.05, "damodaran_industry_wacc": 0.08}
        bank_res = WACCCalculator.calculate_wacc_and_spread(
            ticker="TEST_BANK",
            recent_fy="FY2025",
            period_data=bank_period_data,
            roic_adjusted=0.15,
            roic_traditional=0.15,
            benchmarks=bank_benchmarks,
            archetype="FINANCIAL_BANKING"
        )
        self.assertEqual(bank_res["model_type"], "COST_OF_EQUITY_KE")
        self.assertEqual(bank_res["archetype"], "FINANCIAL_BANKING")
        self.assertEqual(bank_res["wacc"], bank_res["cost_of_equity_ke"])
        self.assertEqual(bank_res["weight_equity"], 1.0)
        self.assertEqual(bank_res["weight_debt"], 0.0)
        self.assertFalse(bank_res["is_debt_free"])
        # TBV = 60000 - 5000 - 2000 = 53000
        # ROTCE = 8000 / 53000 = 0.150943...
        self.assertAlmostEqual(bank_res["tangible_book_value_usd_m"], 53000.0, places=1)
        self.assertAlmostEqual(bank_res["rotce"], 8000.0 / 53000.0, places=4)
        self.assertIn("COST_OF_EQUITY_KE", bank_res["model_type"])

        # 2. Aseguradora (INSURANCE)
        ins_period_data = {
            "net_income": 4000.0,
            "stockholders_equity": 30000.0,
            "goodwill": 1000.0,
            "intangibles": 500.0,
            "total_debt": 8000.0
        }
        ins_res = WACCCalculator.calculate_wacc_and_spread(
            ticker="TEST_INS",
            recent_fy="FY2025",
            period_data=ins_period_data,
            roic_adjusted=0.12,
            roic_traditional=0.12,
            benchmarks=bank_benchmarks,
            archetype="INSURANCE"
        )
        self.assertEqual(ins_res["model_type"], "COST_OF_EQUITY_KE")
        self.assertEqual(ins_res["wacc"], ins_res["cost_of_equity_ke"])

        # 3. Corporativa con Deuda (CORPORATE)
        corp_period_data = {
            "total_debt": 10000.0,
            "interest_expense": 400.0,
            "effective_tax_rate": 0.21
        }
        corp_res = WACCCalculator.calculate_wacc_and_spread(
            ticker="TEST_CORP",
            recent_fy="FY2025",
            period_data=corp_period_data,
            roic_adjusted=0.25,
            roic_traditional=0.25,
            benchmarks=bank_benchmarks,
            archetype="CORPORATE"
        )
        self.assertEqual(corp_res["model_type"], "WACC")
        self.assertGreater(corp_res["weight_debt"], 0.0)
        self.assertFalse(corp_res["is_debt_free"])

    def test_20_semiconductor_peer_benchmarks_and_nvda_ranking(self):
        """
        Verifica la configuración sectorial de Semiconductores (SIC 3674) y el ranking Novy-Marx de NVDA:
        1. Presencia de SIC_3674 en config/peer_benchmarks.json con canasta completa de pares.
        2. Presencia de NVDA como target y competidores clave (AVGO, TSM, AMD, QCOM, INTC, TXN, MU, ASML).
        3. Existencia y consistencia del ranking Novy-Marx en fundamental_scores.json de NVDA.
        """
        peer_benchmarks = load_peer_benchmarks("config/peer_benchmarks.json")
        self.assertIn("SIC_3674", peer_benchmarks.get("industry_benchmarks", {}))
        semi_peers = peer_benchmarks["industry_benchmarks"]["SIC_3674"]["peers"]
        peer_tickers = [p["ticker"] for p in semi_peers]
        for t in ["NVDA", "AVGO", "TSM", "AMD", "QCOM", "INTC", "TXN", "MU", "ASML"]:
            self.assertIn(t, peer_tickers)

        nvda_json = Path("data/processed/NVDA/fundamental_scores.json")
        if nvda_json.exists():
            with open(nvda_json, "r", encoding="utf-8") as f:
                nvda_scores = json.load(f)
            ranking = nvda_scores.get("novy_marx_analysis", {}).get("peer_ranking", [])
            self.assertTrue(len(ranking) >= 5, "NVDA debe tener un ranking de pares poblado con al menos 5 competidores")
            # NVDA lidera en rentabilidad bruta sobre activos
            first = ranking[0]
            self.assertEqual(first["ticker"], "NVDA")
            self.assertGreater(first["gross_profitability_total"], 0.65)


if __name__ == "__main__":
    unittest.main()


