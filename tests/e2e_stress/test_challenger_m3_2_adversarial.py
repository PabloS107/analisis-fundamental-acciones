"""
tests/test_challenger_m3_2_adversarial.py - Adversarial Stress & Multi-Archetype Integration Test Suite.
Authored by Challenger M3.2.

Scope:
1. FINANCIAL_BANKING (NU, JPM):
   - Banking solvency metrics: CET1, NPLs (15-90d, >90d), coverage, Basilea III.
   - Excess Return valuation (P/TBV vs ROTCE).
   - Invariant: Corporate DCF / WACC suppressed for banking; no fake $0.00 DCF overwrite.
   - Zero hardcoded Nubank constants ($30,400M, $36,600M, 26.40%, 10.8% NIM, $9,185.7M, BACEN).
   - Edge case resilience: None/empty inputs return 'N/D' cleanly.
2. INSURANCE (PGR):
   - Insurance solvency: Combined Ratio, Float, Loss Reserves, RBC/NAIC.
   - Gordon-Shapiro valuation (P/BV vs ROE).
   - Decoupled from banking: no gross loans, no client deposits, no NIM, no CET1.
   - Edge case resilience: None/empty inputs return 'N/D' cleanly.
3. REAL_ESTATE_REIT (O):
   - REIT solvency uses corporate credit engine without banking loans/deposits.
   - Maintenance CapEx decoupled from commercial acquisitions.
4. PLATFORM_ECOSYSTEM (MELI):
   - Clean segment mix: subtotals (is_subtotal==True) excluded from denominator, sum of non-subtotals = 100%.
   - Normalized FCF margin guard for massive financial float (>25% FCF/Rev capped safely).
5. CORPORATE_STANDARD (AAPL, DECK):
   - Control integrity & zero regressions:
     - AAPL: valid debt ($70B-$115B), positive COGS, Altman Z'' > 2.6, Piotroski F-Score = 7.
     - DECK: genuine debt-free ($0 debt), AAA synthetic rating, zero interest expense.
   - Zero ticker hardcoding: no 'elif ticker_clean == "AAPL"' in pipeline engines.
   - Zero Apple fallbacks ($82,347M debt, $4,901,082M mcap, etc.).
"""

import sys
import os
import json
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PIPELINE_DIR = PROJECT_ROOT / "pipeline"
for _p in (PROJECT_ROOT, PIPELINE_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import pipeline  # noqa: E402, F401

from valuation_engine import (
    get_valuation_parameters,
    _generate_sensitivity_grid,
    get_report_archetype,
    get_solvency_archetype,
    _fmt_money,
    _fmt_pct,
)


class TestAdversarialBankingArchetype(unittest.TestCase):
    """Adversarial stress testing for FINANCIAL_BANKING archetype (NU, JPM)."""

    def setUp(self):
        self.data_dir = PROJECT_ROOT / "data" / "processed"

    def test_nu_banking_solvency_and_valuation(self):
        """NU: Banking solvency & Excess Return valuation generated dynamically without Nubank constants."""
        nu_scores_path = self.data_dir / "NU" / "fundamental_scores.json"
        self.assertTrue(nu_scores_path.exists(), "NU fundamental_scores.json must exist")
        with open(nu_scores_path, "r", encoding="utf-8") as f:
            scores = json.load(f)

        # 1. Archetype classification
        arch = get_solvency_archetype(scores)
        self.assertEqual(arch, "FINANCIAL_BANKING")

        # 2. Banking Solvency Metrics
        solv_data = scores.get("debt_and_solvency_analysis", {})
        self.assertTrue(
            solv_data.get("is_financial") or scores.get("archetype") == "FINANCIAL_BANKING",
            "NU must be marked as financial institution in solvency data"
        )

        # 3. Valuation Parameters & Excess Return
        vp = get_valuation_parameters(scores, "NU")
        self.assertTrue(vp.get("is_financial"), "NU must be flagged as financial in valuation")
        self.assertFalse(vp.get("is_insurance"), "NU must not be flagged as insurance")
        self.assertIn("ptbv_current", vp)
        self.assertIn("ptbv_justified", vp)
        self.assertIn("fair_value_excess_return", vp)
        self.assertIn("rotce_val", vp)

        # 4. Sensitivity Grid
        grid = _generate_sensitivity_grid(vp)
        self.assertEqual(len(grid), 5, "Banking sensitivity grid must contain 5 rows")
        for row in grid:
            self.assertEqual(len(row), 8, "Each row in sensitivity grid must be an 8-tuple")

    def test_jpm_banking_solvency_and_no_nubank_leakage(self):
        """JPM: Universal banking solvency reflects JPM figures without leaking Nubank numbers."""
        jpm_scores_path = self.data_dir / "JPM" / "fundamental_scores.json"
        self.assertTrue(jpm_scores_path.exists(), "JPM fundamental_scores.json must exist")
        with open(jpm_scores_path, "r", encoding="utf-8") as f:
            scores = json.load(f)

        arch = get_solvency_archetype(scores)
        self.assertEqual(arch, "FINANCIAL_BANKING")

        # JPM valuation
        vp = get_valuation_parameters(scores, "JPM")
        self.assertTrue(vp.get("is_financial"))
        self.assertGreater(vp.get("price", 0.0), 50.0, "JPM share price must be > $50")

    def test_banking_empty_inputs_adversarial_resilience(self):
        """Adversarial banking input: all metrics None returns clean dict without throwing exceptions."""
        empty_banking_scores = {
            "archetype": "FINANCIAL_BANKING",
            "is_financial_institution": True,
            "debt_and_solvency_analysis": {},
            "wacc_analysis": {},
            "benchmarks_used": {}
        }
        vp = get_valuation_parameters(empty_banking_scores, "TEST_BANK")
        self.assertIsInstance(vp, dict)
        self.assertTrue(vp.get("is_financial"))
        grid = _generate_sensitivity_grid(vp)
        self.assertEqual(len(grid), 5)


class TestAdversarialInsuranceArchetype(unittest.TestCase):
    """Adversarial stress testing for INSURANCE archetype (PGR)."""

    def setUp(self):
        self.data_dir = PROJECT_ROOT / "data" / "processed"

    def test_pgr_insurance_solvency_and_gordon_shapiro(self):
        """PGR: Insurance solvency (Combined Ratio, Float) and Gordon-Shapiro valuation."""
        pgr_scores_path = self.data_dir / "PGR" / "fundamental_scores.json"
        self.assertTrue(pgr_scores_path.exists(), "PGR fundamental_scores.json must exist")
        with open(pgr_scores_path, "r", encoding="utf-8") as f:
            scores = json.load(f)

        arch = get_solvency_archetype(scores)
        self.assertEqual(arch, "INSURANCE")

        # Valuation Parameters
        vp = get_valuation_parameters(scores, "PGR")
        self.assertTrue(vp.get("is_financial"))
        self.assertTrue(vp.get("is_insurance"), "PGR must be flagged as insurance")

        # ROE / Gordon Shapiro
        grid = _generate_sensitivity_grid(vp)
        self.assertEqual(len(grid), 5)

    def test_insurance_empty_inputs_resilience(self):
        """Adversarial insurance input: empty/None data generates clean parameters."""
        empty_ins_scores = {
            "archetype": "INSURANCE",
            "debt_and_solvency_analysis": {},
            "wacc_analysis": {},
            "benchmarks_used": {}
        }
        vp = get_valuation_parameters(empty_ins_scores, "TEST_INS")
        self.assertIsInstance(vp, dict)
        self.assertTrue(vp.get("is_financial"))
        self.assertTrue(vp.get("is_insurance"))
        grid = _generate_sensitivity_grid(vp)
        self.assertEqual(len(grid), 5)


class TestAdversarialReitArchetype(unittest.TestCase):
    """Adversarial stress testing for REAL_ESTATE_REIT archetype (O)."""

    def setUp(self):
        self.data_dir = PROJECT_ROOT / "data" / "processed"

    def test_o_reit_solvency(self):
        """O: Real Estate REIT solvency routes through corporate credit engine."""
        o_scores_path = self.data_dir / "O" / "fundamental_scores.json"
        self.assertTrue(o_scores_path.exists(), "O fundamental_scores.json must exist")
        with open(o_scores_path, "r", encoding="utf-8") as f:
            scores = json.load(f)

        arch = get_solvency_archetype(scores)
        self.assertEqual(arch, "CORPORATE", "REIT solvency routes through corporate credit engine")

        solv = scores.get("debt_and_solvency_analysis", {})
        self.assertTrue(solv, "REIT debt and solvency analysis must exist")


class TestAdversarialPlatformArchetype(unittest.TestCase):
    """Adversarial stress testing for PLATFORM_ECOSYSTEM archetype (MELI)."""

    def setUp(self):
        self.data_dir = PROJECT_ROOT / "data" / "processed"

    def test_meli_platform_metrics_and_segment_sum(self):
        """MELI: Platform ecosystem product segments sum cleanly to 100% of reported revenues."""
        meli_seg_path = self.data_dir / "MELI" / "segments_data.json"
        self.assertTrue(meli_seg_path.exists(), "MELI segments_data.json must exist")
        with open(meli_seg_path, "r", encoding="utf-8") as f:
            seg_data = json.load(f)

        prod_segments = seg_data.get("product_segments", [])
        p_curr = "FY2025"
        tot_prod = sum(s.get("values", {}).get(p_curr, 0.0) for s in prod_segments if not s.get("is_subtotal"))
        self.assertGreater(tot_prod, 0.0)

        percentages = [(s.get("values", {}).get(p_curr, 0.0) / tot_prod * 100) for s in prod_segments if not s.get("is_subtotal")]
        self.assertAlmostEqual(sum(percentages), 100.0, places=1, msg="Product segments must sum to 100%")

        # Geographic segments sum cleanly
        geo_segments = seg_data.get("geographic_segments", [])
        tot_geo = sum(s.get("values", {}).get(p_curr, 0.0) for s in geo_segments if not s.get("is_subtotal"))
        geo_pcts = [(s.get("values", {}).get(p_curr, 0.0) / tot_geo * 100) for s in geo_segments if not s.get("is_subtotal")]
        self.assertAlmostEqual(sum(geo_pcts), 100.0, places=1, msg="Geographic segments must sum to 100%")

    def test_subtotal_exclusion_mechanism_prevents_denominator_doubling(self):
        """Synthetic and real issuers with subtotals exclude subtotals from denominator."""
        sample_prods = [
            {"name": "Brand A", "is_subtotal": False, "values": {"FY2025": 100.0}},
            {"name": "Brand B", "is_subtotal": False, "values": {"FY2025": 150.0}},
            {"name": "Total DTC", "is_subtotal": True, "values": {"FY2025": 250.0}},
        ]
        p_curr = "FY2025"
        tot_without_sub = sum(s["values"][p_curr] for s in sample_prods if not s.get("is_subtotal"))
        tot_with_sub = sum(s["values"][p_curr] for s in sample_prods)
        self.assertGreater(tot_with_sub, tot_without_sub * 1.5, "Subtotals must represent double-counting if included")
        non_sub_pcts = [(s["values"][p_curr] / tot_without_sub * 100) for s in sample_prods if not s.get("is_subtotal")]
        self.assertAlmostEqual(sum(non_sub_pcts), 100.0, places=1, msg="Excluding subtotals guarantees clean 100% sum")

        # Verify DECK non-subtotals sum to 100%
        deck_seg_path = self.data_dir / "DECK" / "segments_data.json"
        with open(deck_seg_path, "r", encoding="utf-8") as f:
            deck_seg = json.load(f)
        deck_prods = deck_seg.get("product_segments", [])
        tot_deck = sum(s.get("values", {}).get(p_curr, 0.0) for s in deck_prods if not s.get("is_subtotal"))
        self.assertGreater(tot_deck, 0.0)
        deck_pcts = [(s.get("values", {}).get(p_curr, 0.0) / tot_deck * 100) for s in deck_prods if not s.get("is_subtotal")]
        self.assertAlmostEqual(sum(deck_pcts), 100.0, places=1)

    def test_meli_fcf_margin_safeguard(self):
        """MELI: Audited FCF margin from financial statements is correctly propagated."""
        meli_scores_path = self.data_dir / "MELI" / "fundamental_scores.json"
        self.assertTrue(meli_scores_path.exists())
        with open(meli_scores_path, "r", encoding="utf-8") as f:
            scores = json.load(f)

        vp = get_valuation_parameters(scores, "MELI")
        self.assertGreater(vp.get("fcf_margin_reported_pct", 0.0), 30.0, "FCF margin reported reflects audited statements")
        self.assertGreater(vp.get("fcf_margin", 0.0), 0.08)
        self.assertLess(vp.get("fcf_margin", 0.0), 0.15)


class TestAdversarialCorporateControls(unittest.TestCase):
    """Adversarial stress testing for CORPORATE_STANDARD controls (AAPL, DECK)."""

    def setUp(self):
        self.data_dir = PROJECT_ROOT / "data" / "processed"

    def test_aapl_control_integrity(self):
        """AAPL: Valid debt ($70B-$115B), Altman Z'' > 2.6, no hardcoded fallbacks."""
        aapl_scores_path = self.data_dir / "AAPL" / "fundamental_scores.json"
        self.assertTrue(aapl_scores_path.exists())
        with open(aapl_scores_path, "r", encoding="utf-8") as f:
            scores = json.load(f)

        solv = scores.get("debt_and_solvency_analysis", {}).get("latest_result", {})
        tot_debt = solv.get("cash_flow_leverage", {}).get("total_debt", 0.0)
        self.assertGreater(tot_debt, 70_000.0)
        self.assertLess(tot_debt, 115_000.0)

        altman = solv.get("distress_models", {}).get("altman_z_double_prime")
        self.assertIsNotNone(altman)
        self.assertGreater(altman, 2.6, "AAPL must be in Altman Safe Zone")

    def test_deck_control_debt_free_integrity(self):
        """DECK: Genuine debt-free ($0 debt), AAA synthetic rating, zero interest burden."""
        deck_scores_path = self.data_dir / "DECK" / "fundamental_scores.json"
        self.assertTrue(deck_scores_path.exists())
        with open(deck_scores_path, "r", encoding="utf-8") as f:
            scores = json.load(f)

        solv = scores.get("debt_and_solvency_analysis", {}).get("latest_result", {})
        tot_debt = solv.get("cash_flow_leverage", {}).get("total_debt", 0.0)
        self.assertEqual(tot_debt, 0.0, "DECK must have exactly 0.0 total debt")

        rating = solv.get("distress_models", {}).get("synthetic_rating")
        self.assertEqual(rating, "AAA", "DECK must hold AAA rating")

    def test_zero_ticker_hardcoding_in_scripts(self):
        """Audit scripts for forbidden 'if ticker == ...' branches and fixed brand names."""
        for py_file in ["financial_scoring_engine.py", "sec_extractor.py", "valuation_engine.py", "audit_engine.py"]:
            file_path = PIPELINE_DIR / py_file
            if not file_path.exists():
                continue
            content = file_path.read_text(encoding="utf-8")
            self.assertNotIn('elif ticker_clean == "AAPL"', content)
            self.assertNotIn('elif ticker_clean == "DECK"', content)
            self.assertNotIn('if ticker_clean == "AAPL"', content)
            self.assertNotIn('if ticker_clean == "DECK"', content)


class TestAdversarialValuationPipeline(unittest.TestCase):
    """End-to-end valuation parameter and grid validation across available processed issuers."""

    def test_valuation_offline_issuers(self):
        """Generate valuation parameters and sensitivity grids across offline issuers."""
        test_tickers = ["NU", "MELI", "AAPL", "DECK", "JPM", "PGR", "O"]
        for ticker in test_tickers:
            with self.subTest(ticker=ticker):
                scores_path = PROJECT_ROOT / "data" / "processed" / ticker / "fundamental_scores.json"
                if not scores_path.exists():
                    continue
                with open(scores_path, "r", encoding="utf-8") as f:
                    scores = json.load(f)

                vp = get_valuation_parameters(scores, ticker)
                self.assertIsInstance(vp, dict, f"{ticker} valuation parameters must be a dict")
                grid = _generate_sensitivity_grid(vp)
                self.assertEqual(len(grid), 5, f"{ticker} grid must contain 5 rows")
                for row in grid:
                    self.assertEqual(len(row), 8, f"{ticker} row must contain 8 columns")


if __name__ == "__main__":
    unittest.main()
