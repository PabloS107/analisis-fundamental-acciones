"""
tests/test_valuation_engine.py - Pruebas unitarias para el motor de valoración dual:
- Reverse DCF con Expectations Investing para corporaciones (AAPL, DECK)
- Salvaguarda de FCF normalizado contra float financiero para híbridos (MELI)
- Modelo de Retorno Excedente (Excess Return Model) y P/TBV vs. ROTCE para bancos (NU)
- Matriz de sensibilidad bidimensional dinámica para el Dashboard Web
"""

import sys
import json
import unittest
from pathlib import Path

scripts_dir = Path("pipeline").resolve()
sys.path.insert(0, str(scripts_dir))

import valuation_engine


class TestValuationEngine(unittest.TestCase):

    def setUp(self):
        self.nu_scores_path = Path("data/processed/NU/financial_scores.json")
        self.meli_scores_path = Path("data/processed/MELI/financial_scores.json")
        self.deck_scores_path = Path("data/processed/DECK/financial_scores.json")
        self.aapl_scores_path = Path("data/processed/AAPL/financial_scores.json")

    def test_01_deck_reverse_dcf(self):
        """Verifica que el Reverse DCF de DECK resuelva en el crecimiento implícito esperado."""
        if not self.deck_scores_path.exists():
            self.skipTest("Datos de DECK no encontrados.")
        with open(self.deck_scores_path, "r", encoding="utf-8") as f:
            deck_scores = json.load(f)
        vp = valuation_engine.get_valuation_parameters(deck_scores, "DECK")
        self.assertAlmostEqual(vp["g_implied_our_pct"], -2.0, delta=2.5)
        self.assertLess(vp["g_implied_our_pct"], 5.0)

    def test_02_aapl_reverse_dcf(self):
        """Verifica que el Reverse DCF de AAPL resuelva con precisión."""
        if not self.aapl_scores_path.exists():
            self.skipTest("Datos de AAPL no encontrados.")
        with open(self.aapl_scores_path, "r", encoding="utf-8") as f:
            aapl_scores = json.load(f)
        vp = valuation_engine.get_valuation_parameters(aapl_scores, "AAPL")
        self.assertFalse(vp["is_financial"])
        self.assertGreater(vp["g_implied_our_pct"], 15.0)

    def test_03_meli_valuation_parameters(self):
        """Verifica que para MELI el margen FCF y la facturación reflejen las cifras auditadas de los estados financieros."""
        if not self.meli_scores_path.exists():
            self.skipTest("Datos de MELI no encontrados.")
        with open(self.meli_scores_path, "r", encoding="utf-8") as f:
            meli_scores = json.load(f)
        vp = valuation_engine.get_valuation_parameters(meli_scores, "MELI")
        self.assertFalse(vp["is_financial"])
        # Margen FCF reportado de estados financieros (>= 30.0%)
        self.assertGreaterEqual(vp["fcf_margin_reported_pct"], 30.0)
        self.assertLessEqual(vp["fcf_margin_reported_pct"], 45.0)
        # Margen FCF operativo normalizado para plataformas (8.0% - 15.0%)
        self.assertGreaterEqual(vp["fcf_margin_pct"], 8.0)
        self.assertLessEqual(vp["fcf_margin_pct"], 15.0)
        # Ingresos base derivados de canonical_summary (35.2B)
        self.assertGreaterEqual(vp["base_rev_m"], 30000.0)

    def test_04_nu_banking_excess_return_parameters(self):
        """Verifica que para NU se activen los parámetros de valoración bancaria (P/TBV y ROTCE)."""
        if not self.nu_scores_path.exists():
            self.skipTest("Datos de NU no encontrados.")
        with open(self.nu_scores_path, "r", encoding="utf-8") as f:
            nu_scores = json.load(f)
        vp = valuation_engine.get_valuation_parameters(nu_scores, "NU")
        self.assertTrue(vp["is_financial"])
        self.assertGreater(vp["tbv_per_share"], 1.0)
        self.assertGreaterEqual(vp["ptbv_current"], 4.5)
        self.assertGreater(vp["rotce_pct"], 20.0)
        self.assertGreater(vp["spread_economic_pct"], 10.0)
        self.assertGreater(vp["ptbv_justified"], 2.5)
        self.assertGreater(vp["fair_value_excess_return"], 3.0)

    def test_05_banking_sensitivity_grid_generation(self):
        """Verifica la generación de la matriz de sensibilidad 5x6 para entidades de crédito."""
        if not self.nu_scores_path.exists():
            self.skipTest("Datos de NU no encontrados.")
        with open(self.nu_scores_path, "r", encoding="utf-8") as f:
            nu_scores = json.load(f)

        vp = valuation_engine.get_valuation_parameters(nu_scores, "NU")
        grid = valuation_engine._generate_sensitivity_grid(vp)
        self.assertEqual(len(grid), 5)
        # Cada fila debe tener 8 elementos (label, 6 pasos rotce, diagnóstico)
        for row in grid:
            self.assertEqual(len(row), 8)
        # Fila central es la base
        self.assertIn("Base", grid[2][0])

    def test_06_corporate_sensitivity_grid_generation(self):
        """Verifica la generación de la matriz de sensibilidad WACC vs gn para corporaciones."""
        meta_scores_path = Path("data/processed/META/financial_scores.json")
        if not meta_scores_path.exists():
            self.skipTest("Datos de META no encontrados.")
        with open(meta_scores_path, "r", encoding="utf-8") as f:
            meta_scores = json.load(f)
        meta_prof_path = Path("data/processed/META/company_profile.json")
        meta_prof = json.load(open(meta_prof_path, "r", encoding="utf-8")) if meta_prof_path.exists() else {}

        vp = valuation_engine.get_valuation_parameters(meta_scores, "META", profile_data=meta_prof)
        grid = valuation_engine._generate_sensitivity_grid(vp)
        self.assertEqual(len(grid), 5)
        for row in grid:
            self.assertEqual(len(row), 8)
        self.assertIn("Base", grid[2][0])

    def test_07_aapl_super_valuation_modules(self):
        """Verifica que para AAPL se generen todos los módulos de la Super Pestaña de Valoración."""
        if not self.aapl_scores_path.exists():
            self.skipTest("Datos de AAPL no encontrados.")
        with open(self.aapl_scores_path, "r", encoding="utf-8") as f:
            aapl_scores = json.load(f)
        aapl_fs_path = Path("data/processed/AAPL/financial_statements.json")
        aapl_fs = None
        if aapl_fs_path.exists():
            with open(aapl_fs_path, "r", encoding="utf-8") as f_fs:
                aapl_fs = json.load(f_fs)

        vp = valuation_engine.get_valuation_parameters(aapl_scores, "AAPL", fs_data=aapl_fs)
        
        # 1. Reverse DCF 3-Stage & SBC
        self.assertIn("g_implied_3stage_pct", vp)
        self.assertGreater(vp["g_implied_3stage_pct"], vp["g_implied_our_pct"])
        self.assertIn("fcf_margin_true_pct", vp)
        self.assertLess(vp["fcf_margin_true_pct"], vp["fcf_margin_pct"])

        # 2. Múltiplos & PEG
        self.assertIn("multiples_analysis", vp)
        m = vp["multiples_analysis"]
        self.assertGreater(m["pe_current"], 15.0)
        self.assertIn("imputed_prices", m)
        self.assertGreater(m["imputed_prices"]["composite"], 0.0)

        # 3. EPV & PVGO
        self.assertIn("epv_analysis", vp)
        epv = vp["epv_analysis"]
        self.assertGreater(epv["epv_per_share"], 30.0)
        self.assertGreater(epv["pvgo_per_share"], 50.0)
        self.assertAlmostEqual(epv["epv_pct"] + epv["pvgo_pct"], 100.0, delta=0.5)

        # 4. EVA
        self.assertIn("eva_analysis", vp)
        eva = vp["eva_analysis"]
        self.assertGreater(eva["fair_price_eva"], 50.0)
        self.assertGreater(eva["spread_pct"], 10.0)

        # 5. Forward 5Y IRR
        self.assertIn("forward_5y_analysis", vp)
        f5y = vp["forward_5y_analysis"]
        self.assertGreater(f5y["target_price_5y"], 100.0)
        self.assertIn("bridge", f5y)
        self.assertGreater(vp["buyback_rate_pct"], 1.0)

        # 6. Football Field
        self.assertIn("football_field", vp)
        ff = vp["football_field"]
        self.assertEqual(len(ff["methods"]), 5)
        self.assertGreater(ff["consensus_price"], 50.0)

    def test_08_banking_super_valuation_modules(self):
        """Verifica que para entidades bancarias (NU) se adapten los módulos institucionales."""
        if not self.nu_scores_path.exists():
            self.skipTest("Datos de NU no encontrados.")
        with open(self.nu_scores_path, "r", encoding="utf-8") as f:
            nu_scores = json.load(f)
        nu_fs_path = Path("data/processed/NU/financial_statements.json")
        nu_fs = None
        if nu_fs_path.exists():
            with open(nu_fs_path, "r", encoding="utf-8") as f_nu:
                nu_fs = json.load(f_nu)

        vp = valuation_engine.get_valuation_parameters(nu_scores, "NU", fs_data=nu_fs)
        self.assertTrue(vp["is_financial"])
        self.assertIn("multiples_analysis", vp)
        self.assertIn("epv_analysis", vp)
        self.assertGreater(vp["epv_analysis"]["epv_per_share"], 0.0)
        self.assertIn("eva_analysis", vp)
        self.assertGreater(vp["eva_analysis"]["fair_price_eva"], 0.0)
        self.assertIn("forward_5y_analysis", vp)
        self.assertGreater(vp["forward_5y_analysis"]["target_price_5y"], 0.0)
        self.assertIn("football_field", vp)
        self.assertEqual(len(vp["football_field"]["methods"]), 5)

    def test_09_owner_earnings_and_zscore_modules(self):
        """Verifica los módulos de Owner Earnings, Bandas Z-Score y Trazabilidad Caja Blanca para AAPL."""
        if not self.aapl_scores_path.exists():
            self.skipTest("Datos de AAPL no encontrados.")
        with open(self.aapl_scores_path, "r", encoding="utf-8") as f:
            aapl_scores = json.load(f)
        aapl_fs_path = Path("data/processed/AAPL/financial_statements.json")
        aapl_fs = None
        if aapl_fs_path.exists():
            with open(aapl_fs_path, "r", encoding="utf-8") as f_fs:
                aapl_fs = json.load(f_fs)

        vp = valuation_engine.get_valuation_parameters(aapl_scores, "AAPL", fs_data=aapl_fs)
        
        # 1. Owner Earnings Analysis
        self.assertIn("owner_earnings_analysis", vp)
        oe = vp["owner_earnings_analysis"]
        self.assertFalse(oe.get("is_financial"))
        self.assertGreater(oe["owner_earnings_m"], 0.0)
        self.assertGreater(oe["oe_margin_pct"], 20.0)
        self.assertGreater(oe["maint_capex_m"], 0.0)
        self.assertGreaterEqual(oe["growth_capex_m"], 0.0)
        self.assertAlmostEqual(oe["capex_total_m"], oe["maint_capex_m"] + oe["growth_capex_m"], delta=0.2)
        self.assertIn("g_implied_oe_pct", vp)
        self.assertIn("fair_price_oe", vp)
        self.assertGreater(vp["fair_price_oe"], 0.0)

        # 2. Z-Score Valuation Bands
        self.assertIn("z_score_analysis", vp)
        zs = vp["z_score_analysis"]
        self.assertIsNotNone(zs["current_multiple"])
        self.assertIn("bands", zs)
        self.assertIn("minus_2sigma", zs["bands"])
        self.assertIn("plus_2sigma", zs["bands"])

        # 3. White-Box Audit Traceability
        self.assertIn("audit_traceability", vp)
        audit = vp["audit_traceability"]
        self.assertFalse(audit.get("is_financial"))
        self.assertIn("steps_nopat", audit)
        self.assertIn("steps_capex", audit)
        self.assertIn("multiyear_table", audit)
        self.assertGreater(len(audit["multiyear_table"]), 0)

    def test_10_financial_owner_earnings_safeguard(self):
        """Verifica que para bancos (NU) Owner Earnings y Z-Score se aíslen limpiamente respetando la taxonomía."""
        if not self.nu_scores_path.exists():
            self.skipTest("Datos de NU no encontrados.")
        with open(self.nu_scores_path, "r", encoding="utf-8") as f:
            nu_scores = json.load(f)
        nu_fs_path = Path("data/processed/NU/financial_statements.json")
        nu_fs = None
        if nu_fs_path.exists():
            with open(nu_fs_path, "r", encoding="utf-8") as f_nu:
                nu_fs = json.load(f_nu)

        vp = valuation_engine.get_valuation_parameters(nu_scores, "NU", fs_data=nu_fs)
        self.assertTrue(vp["is_financial"])
        self.assertTrue(vp["owner_earnings_analysis"].get("is_financial"))
        self.assertIn("NO APLICA", vp["owner_earnings_analysis"].get("status", ""))
        self.assertIn("N/D", vp["z_score_analysis"].get("status", ""))
        self.assertTrue(vp["audit_traceability"].get("is_financial"))

    def test_11_historical_multiples_and_audit_math(self):
        """Verifica que historical_multiples y math_formulas se computen con precisión para AAPL y NU."""
        if not self.aapl_scores_path.exists():
            self.skipTest("Datos de AAPL no encontrados.")
        with open(self.aapl_scores_path, "r", encoding="utf-8") as f:
            aapl_scores = json.load(f)
        aapl_fs_path = Path("data/processed/AAPL/financial_statements.json")
        aapl_fs = json.load(open(aapl_fs_path, "r", encoding="utf-8")) if aapl_fs_path.exists() else None

        vp_aapl = valuation_engine.get_valuation_parameters(aapl_scores, "AAPL", fs_data=aapl_fs)
        self.assertIn("historical_multiples", vp_aapl)
        hm = vp_aapl["historical_multiples"]
        self.assertFalse(hm["is_financial"])
        self.assertGreaterEqual(len(hm["periods"]), 5)
        self.assertIn("ev_nopat_adj", hm["series"])
        self.assertIn("p_oe", hm["series"])
        self.assertIn("ev_nopat_adj", hm["stats"])
        self.assertGreater(hm["stats"]["ev_nopat_adj"]["median"], 0.0)
        self.assertGreater(hm["stats"]["ev_nopat_adj"]["imputed_price"], 0.0)

        # Fórmulas matemáticas con sustitución numérica real
        audit = vp_aapl["audit_traceability"]
        self.assertIn("math_formulas", audit)
        self.assertIn("nopat", audit["math_formulas"])
        self.assertIn("owner_earnings", audit["math_formulas"])
        self.assertIn("roic", audit["math_formulas"])
        self.assertIn("reverse_dcf", audit["math_formulas"])
        self.assertIn("$", audit["math_formulas"]["nopat"]["latex_substituted"])
        self.assertIn("M", audit["math_formulas"]["nopat"]["latex_substituted"])

        # Arquetipo bancario (NU)
        if self.nu_scores_path.exists():
            with open(self.nu_scores_path, "r", encoding="utf-8") as f:
                nu_scores = json.load(f)
            nu_fs_path = Path("data/processed/NU/financial_statements.json")
            nu_fs = json.load(open(nu_fs_path, "r", encoding="utf-8")) if nu_fs_path.exists() else None
            vp_nu = valuation_engine.get_valuation_parameters(nu_scores, "NU", fs_data=nu_fs)
            self.assertIn("historical_multiples", vp_nu)
            hm_nu = vp_nu["historical_multiples"]
            self.assertTrue(hm_nu["is_financial"])
            self.assertIn("p_tbv", hm_nu["series"])
            self.assertGreater(hm_nu["stats"]["p_tbv"]["median"], 0.0)


if __name__ == "__main__":
    unittest.main()

