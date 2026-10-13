"""
tests/test_challenger_m2_2_adversarial.py
Adversarial Empirical Stress Harness by Challenger M2.2 (Gen 2).

Scope:
1. Multi-Taxonomic Debt Extraction Hierarchy Stress Tests:
   - Missing combined tags with component tags present (GAAP, Banking, IFRS, REIT).
   - Missing component tags with canonical summary fallback.
   - Truly debt-free preservation (DECK and synthetic zero-debt).
2. Interest Expense Sign Guards & Zero-Division Resilience:
   - Negative interest expense normalization via abs().
   - Extreme negative/positive interest values.
   - Zero interest with positive debt (denominator zero handling).
   - Synthetic interest 4.5% guard (only when interest is None and debt > 100M).
3. Tangible Capital & TBV Zero/Negative Guards:
   - Banking & Insurance TBV goodwill/intangibles impairment resulting in zero or negative tangible capital.
   - Negative equity and insolvency handling in WACCCalculator.
   - Greenblatt ROC zero/negative tangible capital denominator bounds (max(1.0, ...)).
4. Full Disk Artifact Verification (8 Companies):
   - JSON integrity, non-emptiness, schema conformance.
   - Archetype propagation at root and nested levels.
   - Metric inhibition for Financials & Insurance (Altman Z'', Greenblatt ROC).
   - WACC vs Ke branching contract.
   - No false $0 debt on leveraged entities (JPM, NU, O, PGR).
   - Absence of NaN/Infinity/corrupted numbers.
5. Control Regressions:
   - AAPL and DECK scoring integrity.
"""

import json
import math
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "pipeline"))

from financial_scoring_engine import (
    DebtSolvencyEngine,
    GreenblattROCCalculator,
    WACCCalculator,
    extract_period_metrics,
    normalize_archetype,
)


class TestAdversarialDebtHierarchy(unittest.TestCase):
    """Stress testing the debt extraction hierarchy against edge cases."""

    def test_missing_combined_tags_with_component_tags_present(self):
        """Combined debt tag is absent, but component tags (LT + ST) are present."""
        period = "FY2025"
        financials = {
            "balance_sheet_detail": {
                # No combined tags
                "LongTermDebtNoncurrent": {period: 15000.0},
                "ShortTermBorrowings": {period: 2500.0},
            },
            "income_statement_detail": {},
            "cash_flow_detail": {},
        }
        res = extract_period_metrics(financials, period)
        self.assertEqual(res["total_debt"], 17500.0)
        self.assertEqual(res["long_term_debt"], 15000.0)
        self.assertEqual(res["short_term_debt"], 2500.0)

    def test_banking_gaap_long_term_debt_tag(self):
        """Banking GAAP tag LongTermDebtAndCapitalLeaseObligationsIncludingCurrentMaturities."""
        period = "FY2025"
        financials = {
            "balance_sheet_detail": {
                "LongTermDebtAndCapitalLeaseObligationsIncludingCurrentMaturities": {period: 435206.0},
                "ShortTermBorrowings": {period: 78000.0},
            },
            "income_statement_detail": {},
            "cash_flow_detail": {},
        }
        res = extract_period_metrics(financials, period)
        self.assertEqual(res["total_debt"], 513206.0)
        self.assertEqual(res["long_term_debt"], 435206.0)
        self.assertEqual(res["short_term_debt"], 78000.0)

    def test_reit_notes_payable_and_credit_facility(self):
        """REIT taxonomy: NotesPayableNet and RevolvingCreditFacility."""
        period = "FY2025"
        financials = {
            "balance_sheet_detail": {
                "NotesPayableNet": {period: 24500.0},
                "RevolvingCreditFacilityAndCommercialPaper": {period: 1500.0},
            },
            "income_statement_detail": {},
            "cash_flow_detail": {},
        }
        res = extract_period_metrics(financials, period)
        self.assertEqual(res["total_debt"], 26000.0)
        self.assertEqual(res["long_term_debt"], 24500.0)
        self.assertEqual(res["short_term_debt"], 1500.0)

    def test_ifrs_borrowings_taxonomy(self):
        """IFRS taxonomy: ifrs-full_Borrowings and CurrentBorrowings."""
        period = "FY2025"
        financials = {
            "balance_sheet_detail": {
                "ifrs-full_Borrowings": {period: 4800.0},
                "CurrentBorrowings": {period: 900.0},
            },
            "income_statement_detail": {},
            "cash_flow_detail": {},
        }
        res = extract_period_metrics(financials, period)
        self.assertEqual(res["total_debt"], 5700.0)
        self.assertEqual(res["long_term_debt"], 4800.0)
        self.assertEqual(res["short_term_debt"], 900.0)

    def test_missing_component_tags_with_canonical_summary_fallback(self):
        """Component tags are completely missing, but canonical_summary.total_debt is present."""
        period = "FY2025"
        financials = {
            "balance_sheet_detail": {},
            "income_statement_detail": {},
            "cash_flow_detail": {},
            "canonical_summary": {
                "total_debt": {period: 9876.5},
            },
        }
        res = extract_period_metrics(financials, period)
        self.assertEqual(res["total_debt"], 9876.5)
        self.assertEqual(res["long_term_debt"], 9876.5)
        self.assertEqual(res["short_term_debt"], 0.0)

    def test_zero_parsed_debt_unconditional_canonical_fallback(self):
        """Component tags evaluate to 0.0, but canonical_summary has positive debt."""
        period = "FY2025"
        financials = {
            "balance_sheet_detail": {
                "LongTermDebtNoncurrent": {period: 0.0},
                "ShortTermBorrowings": {period: 0.0},
            },
            "income_statement_detail": {},
            "cash_flow_detail": {},
            "canonical_summary": {
                "total_debt": {period: 4200.0},
            },
        }
        res = extract_period_metrics(financials, period)
        self.assertEqual(res["total_debt"], 4200.0)
        self.assertEqual(res["long_term_debt"], 4200.0)

    def test_genuinely_debt_free_preservation(self):
        """Genuinely debt-free issuer must maintain 0.0 debt without false synthetic assignment."""
        period = "FY2025"
        financials = {
            "balance_sheet_detail": {
                "LongTermDebtNoncurrent": {period: 0.0},
                "ShortTermBorrowings": {period: 0.0},
            },
            "income_statement_detail": {},
            "cash_flow_detail": {},
            "canonical_summary": {
                "total_debt": {period: 0.0},
            },
        }
        res = extract_period_metrics(financials, period)
        self.assertEqual(res["total_debt"], 0.0)

        # Check solvency engine honors debt-free
        metrics = {
            "FY2025": {
                "total_debt": 0.0,
                "cash": 1500.0 * 1e6,
                "ebit": 500.0 * 1e6,
                "operating_income": 500.0 * 1e6,
                "cfo": 450.0 * 1e6,
                "capex": 50.0 * 1e6,
                "interest_expense": None,
                "total_assets": 4000.0 * 1e6,
                "stockholders_equity": 3000.0 * 1e6,
            }
        }
        solv = DebtSolvencyEngine.calculate_solvency_series(["FY2025"], metrics, ticker="TEST_DEBT_FREE")
        fy_res = solv["cash_flow_leverage"]["FY2025"]
        cov_res = solv["debt_service"]["FY2025"]

        self.assertTrue(fy_res["is_debt_free"])
        self.assertTrue(fy_res["is_net_cash"])
        self.assertEqual(cov_res["interest_expense"], 0.0)
        self.assertFalse(cov_res["interest_estimated"])
        self.assertEqual(cov_res["interest_coverage_str"], "INFINITA (SIN DEUDA)")
        self.assertEqual(cov_res["status"], "LIBRE DE DEUDA")


class TestAdversarialInterestGuards(unittest.TestCase):
    """Stress testing interest expense sign guards, extreme values, and zero division."""

    def test_negative_interest_sign_normalization(self):
        """Negative interest expense in raw financials must be converted via abs()."""
        period = "FY2025"
        financials = {
            "balance_sheet_detail": {},
            "income_statement_detail": {
                "InterestExpense": {period: -350.0},
            },
            "cash_flow_detail": {},
        }
        res = extract_period_metrics(financials, period)
        self.assertEqual(res["interest_expense"], 350.0)

    def test_negative_interest_coverage_positive_icr(self):
        """Negative raw interest must produce positive ICR, preventing negative coverage artifacts."""
        metrics = {
            "FY2025": {
                "total_debt": 2000.0 * 1e6,
                "cash": 300.0 * 1e6,
                "ebit": 1000.0 * 1e6,
                "cfo": 800.0 * 1e6,
                "interest_expense": -200.0 * 1e6,
            }
        }
        solv = DebtSolvencyEngine.calculate_solvency_series(["FY2025"], metrics, ticker="TEST_NEG_INT")
        cov = solv["debt_service"]["FY2025"]

        self.assertEqual(cov["interest_expense"], 200.0)
        self.assertFalse(cov["interest_estimated"])
        # Coverage must be ebit / 200 = 5.0x, NOT -5.0x
        self.assertEqual(cov["interest_coverage"], 5.0)
        self.assertEqual(cov["interest_coverage_str"], "5.0x")
        self.assertIn("COBERTURA SALUDABLE", cov["status"])

    def test_zero_interest_with_positive_debt_no_crash(self):
        """Zero interest expense with positive debt must handle denominator zero safely."""
        metrics = {
            "FY2025": {
                "total_debt": 5000.0 * 1e6,
                "cash": 200.0 * 1e6,
                "ebit": 1200.0 * 1e6,
                "cfo": 900.0 * 1e6,
                "interest_expense": 0.0,  # Zero interest explicitly
            }
        }
        solv = DebtSolvencyEngine.calculate_solvency_series(["FY2025"], metrics, ticker="TEST_ZERO_INT")
        cov = solv["debt_service"]["FY2025"]

        self.assertEqual(cov["interest_expense"], 0.0)
        self.assertFalse(cov["interest_estimated"])
        self.assertIsNone(cov["interest_coverage"])
        self.assertEqual(cov["interest_coverage_str"], "N/D")
        self.assertEqual(cov["status"], "GASTO FINANCIERO MÍNIMO")
        self.assertEqual(cov["badge"], "SIN CARGA FINANCIERA")

    def test_none_interest_with_large_debt_synthesizes_interest(self):
        """None interest with debt > 100M must estimate 4.5% and flag interest_estimated."""
        metrics = {
            "FY2025": {
                "total_debt": 1000.0 * 1e6,  # 1000M > 100M
                "cash": 100.0 * 1e6,
                "ebit": 300.0 * 1e6,
                "cfo": 250.0 * 1e6,
                "interest_expense": None,
            }
        }
        solv = DebtSolvencyEngine.calculate_solvency_series(["FY2025"], metrics, ticker="TEST_EST_INT")
        cov = solv["debt_service"]["FY2025"]

        self.assertEqual(cov["interest_expense"], 45.0)  # 1000 * 0.045
        self.assertTrue(cov["interest_estimated"])
        self.assertAlmostEqual(cov["interest_coverage"], 300.0 / 45.0, places=2)

    def test_extreme_interest_values(self):
        """Extreme interest values (e.g. 1e12) must flag default risk without numerical overflow."""
        metrics = {
            "FY2025": {
                "total_debt": 5000.0 * 1e6,
                "cash": 10.0 * 1e6,
                "ebit": 50.0 * 1e6,
                "cfo": 30.0 * 1e6,
                "interest_expense": 1e9 * 1e6,  # Extreme interest
            }
        }
        solv = DebtSolvencyEngine.calculate_solvency_series(["FY2025"], metrics, ticker="TEST_EXTREME")
        cov = solv["debt_service"]["FY2025"]
        self.assertEqual(cov["status"], "PELIGRO DE DEFAULT (< 2.5x)")


class TestAdversarialTangibleCapitalGuards(unittest.TestCase):
    """Stress testing tangible capital and tangible book value zero / negative bounds."""

    def test_banking_tbv_goodwill_impairment_negative_tangible_equity(self):
        """Banking entity with Goodwill + Intangibles > Equity must bound TBV to >= 1.0."""
        period_data = {
            "net_income": 500.0 * 1e6,
            "stockholders_equity": 3000.0 * 1e6,
            "goodwill": 2500.0 * 1e6,
            "intangibles": 1500.0 * 1e6,  # Total GW+Int = 4000M > 3000M Equity -> negative tangible equity
            "total_debt": 20000.0 * 1e6,
        }
        benchmarks = {"archetype": "FINANCIAL_BANKING"}

        wacc_res = WACCCalculator.calculate_wacc_and_spread(
            ticker="TEST_BANK_IMPAIR",
            recent_fy="FY2025",
            period_data=period_data,
            roic_adjusted=None,
            roic_traditional=None,
            benchmarks=benchmarks,
            archetype="FINANCIAL_BANKING",
        )

        self.assertEqual(wacc_res["model_type"], "COST_OF_EQUITY_KE")
        # TBV must be bounded by max(1.0, 3000 - 4000) = 1.0
        self.assertEqual(wacc_res["tangible_book_value_usd_m"], 1.0)
        # ROTCE = 500 / 1.0 = 500.0
        self.assertEqual(wacc_res["rotce"], 500.0)
        self.assertIsNotNone(wacc_res["spread"])

    def test_banking_zero_or_negative_equity_insolvency(self):
        """Banking entity with zero or negative equity must not crash with ZeroDivisionError."""
        period_data = {
            "net_income": -100.0 * 1e6,
            "stockholders_equity": -500.0 * 1e6,  # Negative book equity
            "goodwill": 0.0,
            "intangibles": 0.0,
            "total_debt": 10000.0 * 1e6,
        }
        benchmarks = {"archetype": "FINANCIAL_BANKING"}

        wacc_res = WACCCalculator.calculate_wacc_and_spread(
            ticker="TEST_BANK_INSOLVENT",
            recent_fy="FY2025",
            period_data=period_data,
            roic_adjusted=None,
            roic_traditional=None,
            benchmarks=benchmarks,
            archetype="FINANCIAL_BANKING",
        )

        self.assertEqual(wacc_res["tangible_book_value_usd_m"], 0.0)
        self.assertIsNone(wacc_res["roe"])
        self.assertIsNone(wacc_res["rotce"])
        self.assertIsNone(wacc_res["spread"])

    def test_corporate_greenblatt_negative_working_capital_and_zero_ppe(self):
        """Greenblatt ROC with op_nwc < 0 and net_ppe = 0 must bound tangible capital to >= 1.0."""
        period_metrics = {
            "FY2024": {
                "operating_income": 100.0 * 1e6,
                "current_assets": 50.0 * 1e6,
                "cash": 50.0 * 1e6,  # op_ca = 0
                "current_liabilities": 500.0 * 1e6,  # op_cl = 500 -> op_nwc = -500
                "short_term_debt": 0.0,
                "net_ppe": 0.0,  # Zero PP&E
            },
            "FY2025": {
                "operating_income": 150.0 * 1e6,
                "current_assets": 60.0 * 1e6,
                "cash": 60.0 * 1e6,  # op_ca = 0
                "current_liabilities": 600.0 * 1e6,  # op_cl = 600 -> op_nwc = -600
                "short_term_debt": 0.0,
                "net_ppe": 0.0,  # Zero PP&E
            },
        }

        roc_res = GreenblattROCCalculator.calculate_series(
            fiscal_years=["FY2024", "FY2025"],
            period_metrics=period_metrics,
            benchmarks={"archetype": "STANDARD_CORPORATE"},
            archetype="STANDARD_CORPORATE",
        )

        self.assertTrue(roc_res["is_applicable"])
        fy25 = roc_res["FY2025"]
        self.assertGreaterEqual(fy25["tangible_capital_end"], 1.0)
        self.assertGreaterEqual(fy25["tangible_capital_avg"], 1.0)
        self.assertIsNotNone(fy25["roc_avg"])


class TestDiskArtifactIntegrityAndConformance(unittest.TestCase):
    """Deep inspection of all 8 fundamental_scores.json artifacts on disk."""

    TICKERS = ["AAPL", "DECK", "JPM", "MELI", "NU", "NVDA", "O", "PGR"]

    EXPECTED_ARCHETYPES = {
        "AAPL": ["CORPORATE_STANDARD", "STANDARD_CORPORATE"],
        "DECK": ["CORPORATE_STANDARD", "STANDARD_CORPORATE"],
        "JPM": ["FINANCIAL_BANKING"],
        "MELI": ["PLATFORM_ECOSYSTEM"],
        "NU": ["FINANCIAL_BANKING"],
        "NVDA": ["CORPORATE_STANDARD", "STANDARD_CORPORATE"],
        "O": ["REAL_ESTATE_REIT"],
        "PGR": ["INSURANCE"],
    }

    def _check_no_corrupt_values(self, data, path=""):
        """Recursively ensure there are no NaN or Infinity values."""
        if isinstance(data, dict):
            for k, v in data.items():
                self._check_no_corrupt_values(v, f"{path}.{k}")
        elif isinstance(data, list):
            for i, v in enumerate(data):
                self._check_no_corrupt_values(v, f"{path}[{i}]")
        elif isinstance(data, float):
            self.assertFalse(math.isnan(data), f"NaN float found at {path}")
            self.assertFalse(math.isinf(data), f"Infinite float found at {path}")
        elif isinstance(data, str):
            self.assertNotIn("NaN", data, f"NaN string token found at {path}")
            self.assertNotIn("Infinity", data, f"Infinity token found at {path}")

    def test_all_8_fundamental_scores_exist_and_parseable(self):
        """All 8 companies must have non-empty, parseable fundamental_scores.json and financial_scores.json."""
        for ticker in self.TICKERS:
            fpath = PROJECT_ROOT / "data" / "processed" / ticker / "fundamental_scores.json"
            fpath_sync = PROJECT_ROOT / "data" / "processed" / ticker / "financial_scores.json"

            self.assertTrue(fpath.exists(), f"Missing fundamental_scores.json for {ticker}")
            self.assertTrue(fpath_sync.exists(), f"Missing financial_scores.json for {ticker}")

            self.assertGreater(fpath.stat().st_size, 50000, f"File unexpectedly small for {ticker}")
            self.assertEqual(fpath.stat().st_size, fpath_sync.stat().st_size, f"Sync file size mismatch for {ticker}")

            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)

            with open(fpath_sync, "r", encoding="utf-8") as f:
                data_sync = json.load(f)

            self.assertIsInstance(data, dict)
            self._check_no_corrupt_values(data, ticker)

    def test_archetype_persistence_and_propagation(self):
        """Root level archetype and scoring_results.archetype must be present and match."""
        for ticker in self.TICKERS:
            fpath = PROJECT_ROOT / "data" / "processed" / ticker / "fundamental_scores.json"
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)

            root_arch = data.get("archetype")
            self.assertIsNotNone(root_arch, f"Missing root archetype in {ticker}")
            self.assertIn(root_arch, self.EXPECTED_ARCHETYPES[ticker], f"Incorrect root archetype for {ticker}: {root_arch}")

            nested_arch = data.get("scoring_results", {}).get("archetype")
            self.assertEqual(root_arch, nested_arch, f"Mismatch between root and nested archetype in {ticker}")

    def test_inhibition_of_corporate_metrics_for_financials_and_insurance(self):
        """Altman Z'' and Greenblatt ROC must be inhibited for JPM, NU, and PGR."""
        financial_tickers = ["JPM", "NU", "PGR"]
        for ticker in financial_tickers:
            fpath = PROJECT_ROOT / "data" / "processed" / ticker / "fundamental_scores.json"
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Check Altman Z''
            solv = data.get("debt_and_solvency_analysis", {})
            latest_solv = solv.get("latest_result", {})
            distress = latest_solv.get("distress_models", {})
            self.assertEqual(distress.get("altman_zone"), "NO APLICABLE", f"Altman zone not inhibited for {ticker}")
            self.assertEqual(distress.get("altman_badge"), "NO APLICABLE", f"Altman badge not inhibited for {ticker}")
            self.assertFalse(distress.get("is_applicable"), f"Altman is_applicable not False for {ticker}")

            # Check Greenblatt ROC
            roc = data.get("greenblatt_roc_analysis", {})
            self.assertFalse(roc.get("is_applicable"), f"Greenblatt ROC is_applicable not False for {ticker}")
            self.assertEqual(roc.get("rating"), "NO APLICABLE", f"ROC rating not NO APLICABLE for {ticker}")
            self.assertIn("pedagogical_guidance", roc, f"Missing pedagogical guidance in ROC for {ticker}")

            # Check WACC/Ke Model Type
            wacc = data.get("wacc_analysis", {})
            self.assertEqual(wacc.get("model_type"), "COST_OF_EQUITY_KE", f"WACC model_type not COST_OF_EQUITY_KE for {ticker}")
            self.assertEqual(wacc.get("weight_equity"), 1.0, f"Weight equity not 1.0 for {ticker}")
            self.assertEqual(wacc.get("weight_debt"), 0.0, f"Weight debt not 0.0 for {ticker}")

    def test_corporate_entities_preserve_full_wacc_and_metrics(self):
        """Corporate and REIT entities must execute full WACC and applicable metrics."""
        corporate_tickers = ["AAPL", "DECK", "MELI", "NVDA", "O"]
        for ticker in corporate_tickers:
            fpath = PROJECT_ROOT / "data" / "processed" / ticker / "fundamental_scores.json"
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)

            roc = data.get("greenblatt_roc_analysis", {})
            self.assertTrue(roc.get("is_applicable"), f"ROC should be applicable for {ticker}")

            wacc = data.get("wacc_analysis", {})
            self.assertEqual(wacc.get("model_type"), "WACC", f"Model type should be WACC for {ticker}")

    def test_debt_extraction_positive_for_leveraged_entities(self):
        """JPM (~$500B), NU (~$5.7B), O (~$29B), PGR (~$8.4B) must never have 0 debt."""
        thresholds = {
            "JPM": 100000.0,  # > 100B
            "NU": 1000.0,     # > 1B
            "O": 10000.0,     # > 10B
            "PGR": 5000.0,    # > 5B
        }
        for ticker, min_debt in thresholds.items():
            fpath = PROJECT_ROOT / "data" / "processed" / ticker / "fundamental_scores.json"
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)

            solv = data.get("debt_and_solvency_analysis", {})
            lev = solv.get("latest_result", {}).get("cash_flow_leverage", {})
            debt = lev.get("total_debt", 0.0)
            self.assertGreater(debt, min_debt, f"Solvency Debt for {ticker} is {debt}, expected > {min_debt}")

            wacc = data.get("wacc_analysis", {})
            wacc_debt = wacc.get("total_debt_usd_m", 0.0)
            self.assertGreater(wacc_debt, min_debt, f"WACC debt for {ticker} is {wacc_debt}, expected > {min_debt}")

    def test_deck_debt_free_preservation_on_disk(self):
        """DECK must be debt-free (0 debt or <= 1.0M) with is_debt_free = True."""
        fpath = PROJECT_ROOT / "data" / "processed" / "DECK" / "fundamental_scores.json"
        with open(fpath, "r", encoding="utf-8") as f:
            data = json.load(f)

        solv = data.get("debt_and_solvency_analysis", {})
        latest = solv.get("latest_result", {})
        debt = latest.get("cash_flow_leverage", {}).get("total_debt", 999.0)
        self.assertLessEqual(debt, 1.0)
        self.assertTrue(latest.get("is_debt_free"))

        wacc = data.get("wacc_analysis", {})
        self.assertTrue(wacc.get("is_debt_free"))
        self.assertEqual(wacc.get("weight_debt"), 0.0)
        self.assertEqual(wacc.get("wacc"), wacc.get("cost_of_equity_ke"))


if __name__ == "__main__":
    unittest.main()
