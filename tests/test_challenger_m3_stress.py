"""
test_challenger_m3_stress.py - Empirical stress test suite for Milestone 3 report builders.
Adversarial challenge covering:
1. Static AST and Regex scans for hardcoded fallbacks and ticker branches.
2. Synthetic boundary resilience (empty dicts, all-None, negative earnings, zero division).
3. Control issuers AAPL & DECK zero-regression execution.
"""

import unittest
import ast
import re
import math
import os
import sys
from pathlib import Path
from typing import Dict, Any

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
PIPELINE_DIR = PROJECT_ROOT / "pipeline"
if str(PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(PIPELINE_DIR))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import docx


class TestM3ASTAndRegexScans(unittest.TestCase):
    """AST and Regex stress tests against hardcoded constants and ticker branches."""

    BUILDER_FILES = {
        "solvency": PIPELINE_DIR / "solvency_report_builder.py",
        "valuation": PIPELINE_DIR / "valuation_report_builder.py",
        "roic_wacc": PIPELINE_DIR / "roic_wacc_report_builder.py",
        "earnings": PIPELINE_DIR / "generate_earnings_report.py",
    }

    def setUp(self):
        for name, path in self.BUILDER_FILES.items():
            self.assertTrue(path.exists(), f"File {path} does not exist")

    def test_solvency_builder_zero_nubank_constants(self):
        """Verify solvency_report_builder.py has zero Nubank constants or BACEN narratives."""
        content = self.BUILDER_FILES["solvency"].read_text(encoding="utf-8")
        banned = [
            "$30,400.0 M", "30,400", "30400.0", "$36,600.0 M", "36,600", "36600.0",
            "26.40%", "9185.7", "$9,185.7 M", "BACEN"
        ]
        for term in banned:
            self.assertNotIn(term, content, f"Solvency builder contains banned hardcoded term: {term}")

    def test_valuation_builder_zero_nubank_constants(self):
        """Verify valuation_report_builder.py has zero Nubank TBV, 1000.0 float, or Wide Moat texts."""
        content = self.BUILDER_FILES["valuation"].read_text(encoding="utf-8")
        banned = [
            "7646.3", "1.60 TBV", "9.0x P/TBV", "3.54x P/TBV", "Wide Moat Fintech",
            "1000.0"
        ]
        for term in banned:
            self.assertNotIn(term, content, f"Valuation builder contains banned hardcoded term: {term}")

        # AST scan: ensure 1000 is not assigned as fallback revenue
        tree = ast.parse(content, filename="valuation_report_builder.py")
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and "rev" in target.id.lower():
                        if isinstance(node.value, ast.Constant) and node.value in (1000.0, 1000, 1e3):
                            self.fail(f"valuation_report_builder.py assigns 1000 fallback to {target.id}")

    def test_roic_wacc_builder_zero_apple_constants(self):
        """Verify roic_wacc_report_builder.py has zero Apple debt, market cap, or fixed text."""
        content = self.BUILDER_FILES["roic_wacc"].read_text(encoding="utf-8")
        banned = [
            "82347.0", "79597.8", "4901082.8", "188988.0", "267312.2",
            "3.0585", "0.6822", "0.5272", "50632.5",
            "capital de trabajo negativo estructural de Apple"
        ]
        for term in banned:
            self.assertNotIn(term, content, f"ROIC/WACC builder contains banned hardcoded term: {term}")

    def test_earnings_report_zero_ticker_hardcoding(self):
        """Verify generate_earnings_report.py contains no ticker branches or fixed brand names."""
        content = self.BUILDER_FILES["earnings"].read_text(encoding="utf-8")
        banned_branches = [
            'ticker_clean == "AAPL"',
            'ticker_clean == "DECK"',
            'ticker == "AAPL"',
            'ticker == "DECK"',
            'ticker_clean == \'AAPL\'',
            'ticker_clean == \'DECK\'',
        ]
        for term in banned_branches:
            self.assertNotIn(term, content, f"Earnings report contains ticker branch: {term}")

        # Check brand name literals
        banned_brands = ['"iPhone"', '"HOKA"', '"UGG"', '"Teva"']
        for term in banned_brands:
            self.assertNotIn(term, content, f"Earnings report contains hardcoded brand name: {term}")

    def test_ast_scan_no_ticker_comparison_branches(self):
        """AST check: ensure builders don't have hardcoded `ticker == '<COMPANY>'` branches."""
        known_tickers = {"AAPL", "DECK", "NU", "JPM", "PGR", "O", "MELI", "NVDA"}

        for name, path in self.BUILDER_FILES.items():
            content = path.read_text(encoding="utf-8")
            tree = ast.parse(content, filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Compare):
                    # Check if any comparator or left operand is a string matching known tickers
                    is_ticker_compare = False
                    # Check left
                    if isinstance(node.left, ast.Name) and "ticker" in node.left.id.lower():
                        is_ticker_compare = True
                    for comp in node.comparators:
                        if isinstance(comp, ast.Constant) and isinstance(comp.value, str):
                            if comp.value.upper() in known_tickers:
                                # Ensure this is not a comparison for branching logic
                                for op in node.ops:
                                    if isinstance(op, (ast.Eq, ast.NotEq, ast.In, ast.NotIn)):
                                        self.fail(
                                            f"Forbidden ticker branch in {name}: comparing to '{comp.value}' at line {node.lineno}"
                                        )


class TestM3BoundaryInputsAndResilience(unittest.TestCase):
    """Stress tests on boundary conditions, empty dictionaries, None values, and negative numbers."""

    def test_solvency_builder_empty_and_none_resilience(self):
        """Solvency builder handles empty and completely None dictionaries gracefully."""
        from solvency_report_builder import generate_solvency_section_md, add_solvency_section_docx

        test_cases = [
            ({}, "EMPTY"),
            ({"archetype": "CORPORATE_STANDARD"}, "CORP_EMPTY"),
            ({"archetype": "FINANCIAL_BANKING"}, "BANK_EMPTY"),
            ({"archetype": "INSURANCE"}, "INS_EMPTY"),
            ({"archetype": "REAL_ESTATE_REIT"}, "REIT_EMPTY"),
            ({"archetype": "UNKNOWN_ARCHETYPE_XYZ"}, "UNKNOWN_ARCH"),
            ({
                "archetype": "CORPORATE_STANDARD",
                "debt_and_solvency_analysis": None,
                "scoring_results": None,
            }, "ALL_NONE"),
        ]

        for scoring_data, label in test_cases:
            # Markdown generation
            md = generate_solvency_section_md(scoring_data, ticker="SYNTH", company_name="Synthetic Inc.")
            self.assertIsInstance(md, str, f"Markdown generation failed for {label}")
            self.assertNotIn("NoneM", md, f"Found unformatted 'NoneM' in {label}")
            self.assertNotIn("$None", md, f"Found unformatted '$None' in {label}")
            self.assertNotIn("$30,400.0 M", md, f"Found Nubank fallback in {label}")

            # DOCX generation
            doc = docx.Document()
            try:
                add_solvency_section_docx(doc, scoring_data, ticker="SYNTH", company_name="Synthetic Inc.")
            except Exception as e:
                self.fail(f"add_solvency_section_docx crashed on {label} with exception: {e}")

    def test_solvency_builder_negative_and_zero_division(self):
        """Solvency builder handles negative equity, zero revenue, zero debt, and extreme ratios."""
        from solvency_report_builder import generate_solvency_section_md, add_solvency_section_docx

        extreme_corp = {
            "archetype": "CORPORATE_STANDARD",
            "scoring_results": {
                "latest_year": "FY2025",
                "ebit": -1000.0,
                "revenue": 0.0,
                "total_debt": 0.0,
                "net_debt": -500.0,
                "cash": 500.0,
                "equity": -200.0,
            },
            "debt_and_solvency_analysis": {
                "latest_result": {
                    "distress_models": {"altman_z_double_prime": -5.2, "altman_zone": "ZONA DE PELIGRO"},
                    "debt_service": {"interest_coverage": -0.5, "status_service": "DÉFICIT OPERATIVO"},
                    "is_debt_free": True,
                }
            }
        }
        md = generate_solvency_section_md(extreme_corp, ticker="DISTRESS", company_name="Distressed Corp.")
        self.assertIsInstance(md, str)
        doc = docx.Document()
        add_solvency_section_docx(doc, extreme_corp, ticker="DISTRESS", company_name="Distressed Corp.")
        self.assertGreater(len(doc.paragraphs) + len(doc.tables), 0)

    def test_valuation_builder_negative_earnings_and_empty(self):
        """Valuation builder handles negative earnings, missing market data, and empty structures."""
        from valuation_report_builder import (
            get_valuation_parameters,
            _generate_sensitivity_grid,
            generate_valuation_section_md,
            add_valuation_section_docx,
        )

        test_cases = [
            ({}, "EMPTY"),
            ({
                "ticker": "NEG_EARN",
                "canonical_summary": {
                    "free_cash_flow": {"LTM": -1500.0, "FY2025": -1200.0},
                    "net_income": {"LTM": -800.0, "FY2025": -700.0},
                },
                "market_data": {"price": 15.0, "shares_m": 100.0},
                "archetype": "CORPORATE_STANDARD",
            }, "CORP_NEG_FCF"),
            ({
                "ticker": "NEG_BANK",
                "canonical_summary": {
                    "net_income": {"LTM": -300.0},
                    "stockholders_equity": {"LTM": -100.0},
                },
                "market_data": {"price": 5.0, "shares_m": 50.0},
                "archetype": "FINANCIAL_BANKING",
            }, "BANK_NEG_EQUITY"),
            ({
                "ticker": "ZERO_SHARES",
                "canonical_summary": {"free_cash_flow": {"LTM": 100.0}},
                "market_data": {"price": 0.0, "shares_m": 0.0},
                "archetype": "CORPORATE_STANDARD",
            }, "ZERO_PRICE_SHARES"),
        ]

        for scoring_data, label in test_cases:
            vp = get_valuation_parameters(scoring_data, scoring_data.get("ticker", "SYNTH"))
            self.assertIsInstance(vp, dict, f"get_valuation_parameters failed for {label}")

            grid = _generate_sensitivity_grid(vp)
            self.assertIsInstance(grid, list, f"Grid generation failed for {label}")
            self.assertEqual(len(grid), 5, f"Grid must have exactly 5 rows for {label}")
            for row in grid:
                self.assertEqual(len(row), 8, f"Each grid row must have 8 columns for {label}")

            md = generate_valuation_section_md(scoring_data, scoring_data.get("ticker", "SYNTH"), "Synth Co")
            self.assertIsInstance(md, str, f"Valuation markdown failed for {label}")
            self.assertNotIn("7646.3", md)

            doc = docx.Document()
            try:
                add_valuation_section_docx(doc, scoring_data, scoring_data.get("ticker", "SYNTH"), "Synth Co")
            except Exception as e:
                self.fail(f"add_valuation_section_docx crashed on {label} with exception: {e}")

    def test_roic_wacc_builder_empty_and_financial_entities(self):
        """ROIC/WACC builder handles empty dicts, financial entities without WACC, and extreme data."""
        from roic_wacc_report_builder import (
            build_roic_wacc_markdown_section,
            generate_roic_wacc_section_md,
            add_roic_wacc_section_docx,
        )

        test_cases = [
            ({}, "EMPTY"),
            ({"archetype": "FINANCIAL_BANKING", "wacc_analysis": {"model_type": "COST_OF_EQUITY_KE", "ke": 0.12}}, "BANK"),
            ({"archetype": "INSURANCE", "wacc_analysis": {"model_type": "COST_OF_EQUITY_KE", "ke": 0.10}}, "INSURANCE"),
            ({"archetype": "CORPORATE_STANDARD", "wacc_analysis": {}}, "CORP_EMPTY_WACC"),
        ]

        for scoring_data, label in test_cases:
            md = generate_roic_wacc_section_md(scoring_data, ticker="SYNTH", company_name="Synth Co")
            self.assertIsInstance(md, str, f"ROIC/WACC markdown failed for {label}")
            self.assertNotIn("4901082.8", md)
            self.assertNotIn("82347.0", md)

            if label in ("BANK", "INSURANCE"):
                # Must contain pedagogical note explaining WACC inapplicability
                self.assertTrue(
                    "No Aplica" in md or "Inaplicable" in md or "no aplica" in md.lower() or "fondos propios" in md.lower(),
                    f"Pedagogical note missing in financial entity {label}"
                )

            doc = docx.Document()
            try:
                add_roic_wacc_section_docx(doc, scoring_data, ticker="SYNTH", company_name="Synth Co")
            except Exception as e:
                self.fail(f"add_roic_wacc_section_docx crashed on {label} with exception: {e}")

    def test_catalyst_and_pedagogical_guide_boundaries(self):
        """Dynamic catalysts and pedagogical guides handle edge values cleanly."""
        from generate_earnings_report import (
            derive_segment_catalyst,
            derive_geo_catalyst,
            get_scorecard_pedagogical_guide,
        )

        # Catalyst tests
        cat_sub = derive_segment_catalyst("Subtotal Segment", 15.0, is_subtotal=True)
        self.assertIn("Subtotal consolidado", cat_sub)
        self.assertIn("+15.0% YoY", cat_sub)

        geo_sub = derive_geo_catalyst("Subtotal Geo", 15.0, 50.0, is_subtotal=True)
        self.assertIn("Subtotal consolidado", geo_sub)
        self.assertIn("+15.0% YoY", geo_sub)

        # Extreme YoY
        cat_high = derive_segment_catalyst("Tech Division", 50.0)
        self.assertIn("Aceleración comercial", cat_high)
        cat_drop = derive_segment_catalyst("Legacy Division", -25.0)
        self.assertIn("Contracción", cat_drop)
        cat_flat = derive_segment_catalyst("Stable Division", 1.0)
        self.assertIn("Desempeño estable", cat_flat)

        # Pedagogical guides
        for arch in ["FINANCIAL_BANKING", "INSURANCE", "REAL_ESTATE_REIT", "STANDARD_CORPORATE", "CORPORATE_STANDARD", "UNKNOWN", None]:
            guide = get_scorecard_pedagogical_guide(arch)
            self.assertIsInstance(guide, tuple)
            self.assertEqual(len(guide), 2)
            title, paragraphs = guide
            self.assertIsInstance(title, str)
            self.assertIsInstance(paragraphs, list)
            self.assertGreater(len(paragraphs), 0)


class TestM3ControlIssuersZeroRegression(unittest.TestCase):
    """Zero regression tests for control companies AAPL and DECK."""

    def test_control_aapl_full_report_generation(self):
        """AAPL end-to-end full report generation succeeds without errors or regressions."""
        from generate_earnings_report import generate_full_report

        aapl_processed = PROJECT_ROOT / "data" / "processed" / "AAPL"
        if not (aapl_processed / "financial_statements.json").exists():
            self.skipTest("AAPL processed data not found")

        doc_path, md_path = generate_full_report(ticker="AAPL")
        self.assertTrue(Path(doc_path).exists(), f"AAPL docx not created at {doc_path}")
        self.assertTrue(Path(md_path).exists(), f"AAPL md not created at {md_path}")

        md_content = Path(md_path).read_text(encoding="utf-8")
        self.assertGreater(len(md_content), 1000, "AAPL md report is unexpectedly short")
        # Ensure Apple report does NOT contain banking metrics
        self.assertNotIn("CET1", md_content)
        self.assertNotIn("Loan-to-Deposit", md_content)
        self.assertNotIn("Combined Ratio", md_content)

    def test_control_deck_full_report_generation(self):
        """DECK end-to-end full report generation succeeds without errors or regressions."""
        from generate_earnings_report import generate_full_report

        deck_processed = PROJECT_ROOT / "data" / "processed" / "DECK"
        if not (deck_processed / "financial_statements.json").exists():
            self.skipTest("DECK processed data not found")

        doc_path, md_path = generate_full_report(ticker="DECK")
        self.assertTrue(Path(doc_path).exists(), f"DECK docx not created at {doc_path}")
        self.assertTrue(Path(md_path).exists(), f"DECK md not created at {md_path}")

        md_content = Path(md_path).read_text(encoding="utf-8")
        self.assertGreater(len(md_content), 1000, "DECK md report is unexpectedly short")
        # Ensure DECK report does NOT contain banking metrics
        self.assertNotIn("CET1", md_content)
        self.assertNotIn("Loan-to-Deposit", md_content)
        self.assertNotIn("Combined Ratio", md_content)


if __name__ == "__main__":
    unittest.main()
