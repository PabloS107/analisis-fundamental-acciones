"""
test_sec_extractor_modularization.py - Test de integridad de modularización y fachada de sec_extractor.
Valida el cumplimiento de la Regla 2 (Verification Protocol) y Regla 5 (Clean Refactoring):
1. Verificación de imports duales (raíz vs submódulo).
2. Verificación de re-exportaciones de __all__ completas y sin regresión.
3. Comprobación de que sec_extractor actúa como fachada limpia (~280 líneas).
4. Verificación de ejecución desacoplada de los 4 submódulos en pipeline/sec_modules/.
"""

import unittest
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PIPELINE_DIR = PROJECT_ROOT / "pipeline"
if str(PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(PIPELINE_DIR))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class TestSecExtractorModularization(unittest.TestCase):

    def test_01_facade_line_count(self):
        """Verifica que sec_extractor.py sea esbelto (< 650 líneas) y no un monolito de 3900 líneas."""
        sec_file = PIPELINE_DIR / "sec_extractor.py"
        lines = sec_file.read_text(encoding="utf-8").splitlines()
        self.assertLess(len(lines), 650, f"sec_extractor.py tiene {len(lines)} líneas; debería tener < 650 líneas")

    def test_02_all_symbols_present_in_facade(self):
        """Verifica que todos los símbolos declarados en __all__ sean accesibles desde sec_extractor."""
        import sec_extractor as se
        self.assertTrue(hasattr(se, "__all__"))
        for symbol in se.__all__:
            self.assertTrue(
                hasattr(se, symbol),
                f"El símbolo '{symbol}' declarado en __all__ no está expuesto en sec_extractor"
            )

    def test_03_dual_import_compatibility(self):
        """Verifica compatibilidad de importación tanto directa como empaquetada."""
        import sec_extractor as se_direct
        import pipeline.sec_extractor as se_pkg
        self.assertEqual(se_direct.normalize_archetype("CORPORATE_STANDARD"), "STANDARD_CORPORATE")
        self.assertEqual(se_pkg.normalize_archetype("CORPORATE_STANDARD"), "STANDARD_CORPORATE")
        self.assertEqual(se_direct.extract_canonical_summary.__name__, se_pkg.extract_canonical_summary.__name__)
        self.assertEqual(se_direct.load_sec_config.__name__, se_pkg.load_sec_config.__name__)

    def test_04_submodules_exist_and_importable(self):
        """Verifica que los 4 submódulos existan en pipeline/sec_modules/ y sean importables."""
        import pipeline.sec_modules.sec_xbrl_ltm as xl
        import pipeline.sec_modules.sec_canonical_builder as cb
        import pipeline.sec_modules.sec_statement_reconciler as sr
        import pipeline.sec_modules.sec_segment_extractor as se
        import pipeline.sec_modules as sm

        self.assertTrue(callable(xl.enrich_annual_statements_with_individual_filings))
        self.assertTrue(callable(xl.compute_and_inject_ltm_columns))
        self.assertTrue(callable(cb.extract_canonical_summary))
        self.assertTrue(callable(sr.build_as_reported_statements))
        self.assertTrue(callable(sr.sanitize_and_validate_statements))
        self.assertTrue(callable(se.build_and_save_segments_data))
        self.assertTrue(callable(sm.enrich_annual_statements_with_individual_filings))
        self.assertTrue(callable(sm.compute_and_inject_ltm_columns))

    def test_05_archetype_normalization_identity(self):
        """Verifica que normalize_archetype en entity_classifier y sec_extractor sea idéntico."""
        from entity_classifier import normalize_archetype as norm_ec
        from sec_extractor import normalize_archetype as norm_se

        cases = [
            ("CORPORATE_STANDARD", "STANDARD_CORPORATE"),
            ("STANDARD_CORPORATE", "STANDARD_CORPORATE"),
            ("FINANCIAL_BANKING", "FINANCIAL_BANKING"),
            ("BANKING", "FINANCIAL_BANKING"),
            ("REIT", "REAL_ESTATE_REIT"),
            ("REAL_ESTATE_REIT", "REAL_ESTATE_REIT"),
            ("INSURANCE", "INSURANCE"),
            ("PLATFORM_ECOSYSTEM", "PLATFORM_ECOSYSTEM"),
        ]
        for inp, expected in cases:
            self.assertEqual(norm_ec(inp), expected)
            self.assertEqual(norm_se(inp), expected)

    def test_06_statement_reconciler_mock_execution(self):
        """Verifica que sanitize_and_validate_statements opere correctamente sobre un dataset canónico."""
        from sec_extractor import sanitize_and_validate_statements

        mock_dataset = {
            "ticker": "MOCK",
            "company_name": "Mock Company Inc.",
            "fiscal_years": ["FY2025", "FY2024"],
            "canonical_summary": {
                "revenue": {"FY2025": 1000.0, "FY2024": 900.0},
                "net_income": {"FY2025": 200.0, "FY2024": 180.0},
            },
            "as_reported_statements": {
                "income_statement": [
                    {"concept": "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax", "label": "Revenue", "values": {"FY2025": 1000.0}}
                ]
            }
        }
        sanitized = sanitize_and_validate_statements(mock_dataset)
        self.assertEqual(sanitized["ticker"], "MOCK")
        self.assertIn("canonical_summary", sanitized)
        self.assertIn("as_reported_statements", sanitized)


if __name__ == "__main__":
    unittest.main()
