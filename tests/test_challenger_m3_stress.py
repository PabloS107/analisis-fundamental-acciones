"""
test_challenger_m3_stress.py - Empirical stress test suite for calculation engines.
Adversarial challenge covering:
1. Static AST and Regex scans for hardcoded fallbacks and ticker branches in calculation engines.
2. Synthetic boundary resilience (empty dicts, all-None, negative earnings, zero division).
3. Control issuers AAPL & DECK zero-regression execution.
"""

import unittest
import ast
import re
import math
import os
import sys
import json
from pathlib import Path
from typing import Dict, Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PIPELINE_DIR = PROJECT_ROOT / "pipeline"
if str(PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(PIPELINE_DIR))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from financial_scoring_engine import (
    DebtSolvencyEngine,
    WACCCalculator,
    GreenblattROCCalculator,
    calculate_fundamental_scores,
)
from valuation_engine import (
    get_valuation_parameters,
    _generate_sensitivity_grid,
    get_report_archetype,
    get_solvency_archetype,
)


class TestM3ASTAndRegexScans(unittest.TestCase):
    """AST and Regex stress tests against hardcoded constants and ticker branches in calculation engines."""

    ENGINE_FILES = {
        "valuation": PIPELINE_DIR / "valuation_engine.py",
        "scoring": PIPELINE_DIR / "financial_scoring_engine.py",
        "extractor": PIPELINE_DIR / "sec_extractor.py",
        "audit": PIPELINE_DIR / "audit_engine.py",
    }

    def setUp(self):
        for name, path in self.ENGINE_FILES.items():
            self.assertTrue(path.exists(), f"File {path} does not exist")

    def test_valuation_engine_zero_nubank_constants(self):
        """Verify valuation_engine.py has zero hardcoded Nubank TBV or fallback revenue."""
        content = self.ENGINE_FILES["valuation"].read_text(encoding="utf-8")
        banned = [
            "7646.3", "1.60 TBV", "9.0x P/TBV", "3.54x P/TBV", "Wide Moat Fintech"
        ]
        for term in banned:
            self.assertNotIn(term, content, f"Valuation engine contains banned hardcoded term: {term}")

        # AST scan: ensure 1000 is not assigned as fallback revenue
        tree = ast.parse(content, filename="valuation_engine.py")
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and "rev" in target.id.lower():
                        if isinstance(node.value, ast.Constant) and node.value in (1000.0, 1000, 1e3):
                            self.fail(f"valuation_engine.py assigns 1000 fallback to {target.id}")

    def test_scoring_engine_zero_apple_constants(self):
        """Verify financial_scoring_engine.py has zero Apple hardcoded fallbacks."""
        content = self.ENGINE_FILES["scoring"].read_text(encoding="utf-8")
        banned = [
            "82347.0", "79597.8", "4901082.8",
            "capital de trabajo negativo estructural de Apple"
        ]
        for term in banned:
            self.assertNotIn(term, content, f"Scoring engine contains banned hardcoded term: {term}")

    def test_ast_scan_no_ticker_comparison_branches(self):
        """AST check: ensure calculation engines don't have hardcoded `ticker == '<COMPANY>'` branches."""
        known_tickers = {"AAPL", "DECK", "NU", "JPM", "PGR", "O", "MELI", "NVDA"}

        for name, path in self.ENGINE_FILES.items():
            content = path.read_text(encoding="utf-8")
            tree = ast.parse(content, filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Compare):
                    is_ticker_compare = False
                    if isinstance(node.left, ast.Name) and "ticker" in node.left.id.lower():
                        is_ticker_compare = True
                    for comp in node.comparators:
                        if isinstance(comp, ast.Constant) and isinstance(comp.value, str):
                            if comp.value.upper() in known_tickers:
                                for op in node.ops:
                                    if isinstance(op, (ast.Eq, ast.NotEq)):
                                        self.fail(
                                            f"Forbidden ticker branch in {name}: comparing to '{comp.value}' at line {node.lineno}"
                                        )


class TestM3BoundaryInputsAndResilience(unittest.TestCase):
    """Stress tests on boundary conditions, empty dictionaries, None values, and negative numbers."""

    def test_solvency_engine_empty_and_none_resilience(self):
        """Solvency engine handles empty and completely None dictionaries gracefully."""
        test_cases = [
            ({}, "EMPTY", "CORPORATE_STANDARD"),
            ({"FY2025": {}}, "EMPTY_PERIOD", "CORPORATE_STANDARD"),
            ({"FY2025": {"ebit": None, "total_debt": None}}, "NONE_VALUES", "CORPORATE_STANDARD"),
            ({}, "BANK_EMPTY", "FINANCIAL_BANKING"),
            ({}, "INS_EMPTY", "INSURANCE"),
        ]

        for period_metrics, label, arch in test_cases:
            res = DebtSolvencyEngine.calculate_solvency_series(
                ["FY2025"],
                period_metrics,
                archetype=arch,
                ticker="SYNTH"
            )
            self.assertIsInstance(res, dict, f"Solvency series failed for {label}")
            self.assertIn("latest_result", res)

    def test_solvency_engine_negative_and_zero_division(self):
        """Solvency engine handles negative equity, zero revenue, zero debt, and extreme ratios."""
        extreme_metrics = {
            "FY2025": {
                "ebit": -1000.0,
                "revenue": 0.0,
                "total_debt": 0.0,
                "net_debt": -500.0,
                "cash": 500.0,
                "stockholders_equity": -200.0,
                "interest_expense": 0.0,
                "cfo": -300.0,
                "capex": 50.0,
            }
        }
        res = DebtSolvencyEngine.calculate_solvency_series(
            ["FY2025"],
            extreme_metrics,
            archetype="CORPORATE_STANDARD",
            ticker="DISTRESS"
        )
        self.assertIsInstance(res, dict)
        latest = res.get("latest_result", {})
        self.assertTrue(latest.get("is_debt_free", False))

    def test_valuation_engine_negative_earnings_and_empty(self):
        """Valuation engine handles negative earnings, missing market data, and empty structures."""
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

    def test_wacc_calculator_empty_and_financial_entities(self):
        """WACC calculator handles financial entities and empty data robustly."""
        res = WACCCalculator.calculate_wacc_and_spread(
            ticker="TEST_BANK",
            recent_fy="FY2025",
            period_data={},
            roic_adjusted=0.15,
            roic_traditional=0.14,
            benchmarks={},
            archetype="FINANCIAL_BANKING"
        )
        self.assertIsInstance(res, dict)


class TestM3ControlIssuersZeroRegression(unittest.TestCase):
    """Zero regression tests for control companies AAPL and DECK."""

    def test_control_aapl_valuation_and_scoring(self):
        """AAPL end-to-end valuation and scoring succeeds without errors or regressions."""
        aapl_processed = PROJECT_ROOT / "data" / "processed" / "AAPL"
        if not (aapl_processed / "financial_statements.json").exists():
            self.skipTest("AAPL processed data not found")

        scores = calculate_fundamental_scores("AAPL", aapl_processed / "financial_statements.json")
        self.assertIn("piotroski_f_score", scores)
        self.assertIn("debt_and_solvency_analysis", scores)

        vp = get_valuation_parameters(scores, "AAPL")
        self.assertIsInstance(vp, dict)
        self.assertGreater(vp.get("price", 0.0), 50.0)

        grid = _generate_sensitivity_grid(vp)
        self.assertEqual(len(grid), 5)

    def test_control_deck_valuation_and_scoring(self):
        """DECK end-to-end valuation and scoring succeeds without errors or regressions."""
        deck_processed = PROJECT_ROOT / "data" / "processed" / "DECK"
        if not (deck_processed / "financial_statements.json").exists():
            self.skipTest("DECK processed data not found")

        scores = calculate_fundamental_scores("DECK", deck_processed / "financial_statements.json")
        self.assertIn("piotroski_f_score", scores)
        self.assertIn("debt_and_solvency_analysis", scores)

        vp = get_valuation_parameters(scores, "DECK")
        self.assertIsInstance(vp, dict)
        self.assertGreater(vp.get("price", 0.0), 20.0)

        grid = _generate_sensitivity_grid(vp)
        self.assertEqual(len(grid), 5)


if __name__ == "__main__":
    unittest.main()
