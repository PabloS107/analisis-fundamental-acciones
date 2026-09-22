"""
tests/test_valuation_engine.py - Pruebas unitarias para el motor de valoración dual:
- Reverse DCF con Expectations Investing para corporaciones (AAPL, DECK)
- Salvaguarda de FCF normalizado contra float financiero para híbridos (MELI)
- Modelo de Retorno Excedente (Excess Return Model) y P/TBV vs. ROTCE para bancos (NU)
- Generación de secciones en Word (.docx) y Markdown (.md)
"""

import sys
import json
import unittest
from pathlib import Path
import docx

scripts_dir = Path(".agents/skills/fundamental-data-extractor/scripts").resolve()
sys.path.insert(0, str(scripts_dir))

import valuation_report_builder


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
        vp = valuation_report_builder.get_valuation_parameters(deck_scores, "DECK")
        self.assertFalse(vp["is_financial"])
        self.assertAlmostEqual(vp["g_implied_our_pct"], -3.7, delta=1.0)

    def test_02_aapl_reverse_dcf(self):
        """Verifica que el Reverse DCF de AAPL resuelva con precisión."""
        if not self.aapl_scores_path.exists():
            self.skipTest("Datos de AAPL no encontrados.")
        with open(self.aapl_scores_path, "r", encoding="utf-8") as f:
            aapl_scores = json.load(f)
        vp = valuation_report_builder.get_valuation_parameters(aapl_scores, "AAPL")
        self.assertFalse(vp["is_financial"])
        self.assertGreater(vp["g_implied_our_pct"], 15.0)

    def test_03_meli_hybrid_float_protection(self):
        """Verifica que para MELI el margen FCF se normalice contra el float de Mercado Pago."""
        if not self.meli_scores_path.exists():
            self.skipTest("Datos de MELI no encontrados.")
        with open(self.meli_scores_path, "r", encoding="utf-8") as f:
            meli_scores = json.load(f)
        vp = valuation_report_builder.get_valuation_parameters(meli_scores, "MELI")
        self.assertFalse(vp["is_financial"])
        # Margen FCF debe estar contenido entre 8% y 18% (no el 60% inflado por depósitos)
        self.assertLessEqual(vp["fcf_margin_pct"], 20.0)
        self.assertGreaterEqual(vp["fcf_margin_pct"], 5.0)
        # El crecimiento implícito debe ser positivo y realista
        self.assertGreater(vp["g_implied_our_pct"], 10.0)
        self.assertLess(vp["g_implied_our_pct"], 35.0)

    def test_04_nu_banking_excess_return_parameters(self):
        """Verifica que para NU se activen los parámetros de valoración bancaria (P/TBV y ROTCE)."""
        if not self.nu_scores_path.exists():
            self.skipTest("Datos de NU no encontrados.")
        with open(self.nu_scores_path, "r", encoding="utf-8") as f:
            nu_scores = json.load(f)
        vp = valuation_report_builder.get_valuation_parameters(nu_scores, "NU")
        self.assertTrue(vp["is_financial"])
        self.assertGreater(vp["tbv_per_share"], 1.0)
        self.assertGreater(vp["ptbv_current"], 5.0)
        self.assertGreater(vp["rotce_pct"], 20.0)
        self.assertGreater(vp["spread_economic_pct"], 10.0)
        self.assertGreater(vp["ptbv_justified"], 2.5)
        self.assertGreater(vp["fair_value_excess_return"], 3.0)

    def test_05_banking_markdown_and_docx_generation(self):
        """Verifica la generación de la sección 14 en Markdown y Word para entidades de crédito."""
        if not self.nu_scores_path.exists():
            self.skipTest("Datos de NU no encontrados.")
        with open(self.nu_scores_path, "r", encoding="utf-8") as f:
            nu_scores = json.load(f)

        md = valuation_report_builder.generate_valuation_section_md(nu_scores, "NU", "Nu Holdings Ltd.", section_num=14)
        self.assertIn("Excess Return Model", md)
        self.assertIn("P/TBV", md)
        self.assertIn("ROTCE", md)
        self.assertIn("Gordon-Shapiro bancario", md)

        doc = docx.Document()
        valuation_report_builder.add_valuation_section_docx(doc, nu_scores, "NU", "Nu Holdings Ltd.", section_num=14)
        headings = [p.text for p in doc.paragraphs if p.text]
        self.assertTrue(any("Excess Return" in h for h in headings))
        self.assertGreaterEqual(len(doc.tables), 3)


if __name__ == "__main__":
    unittest.main()
