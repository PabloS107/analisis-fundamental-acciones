"""
tests/test_challenger_m1_2.py - Comprehensive Empirical Stress Harness by Challenger M1.2.
Validates:
1. P&L identities (Gross Profit = Rev - COGS) under extreme and boundary values.
2. REIT AFFO identity & CapEx decoupling.
3. Identified vulnerabilities and edge-case behaviors:
   - Fixed $1000 tolerance fragility under large-cap quarterly sum roundoffs (e.g., NVDA LTM).
   - Missing archetype fallback in audit_free_cash_flow (contrary to Worker M1 changes.md claim).
   - Preferred dividend discrepancy in audit_eps_consistency for banks (JPM).
   - Negative OpEx vulnerability in canonical banking summary (NU).
"""

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "pipeline"))

from audit_engine import (
    audit_gross_profit,
    audit_free_cash_flow,
    audit_sanity_bounds,
    audit_balance_sheet,
    audit_eps_consistency,
    run_full_audit,
)


class TestStressGrossProfitIdentities(unittest.TestCase):
    """Stress testing P&L Gross Profit identities under extreme and edge values."""

    def test_negative_cogs_strictly_rejected(self):
        """Negative COGS must fail audit_gross_profit and audit_sanity_bounds."""
        data = {
            "canonical_summary": {
                "revenue": {"FY2025": 1000000.0},
                "cost_of_goods_sold": {"FY2025": -400000.0},
                "gross_profit": {"FY2025": 600000.0},
                "operating_expenses": {"FY2025": 200000.0},
            },
            "key_ratios": {"gross_margin_pct": {"FY2025": 60.0}}
        }
        gp_res = audit_gross_profit(data, "FY2025")
        self.assertFalse(gp_res["passed"])
        self.assertEqual(gp_res["status"], "FAIL")
        self.assertIn("signo negativo", gp_res["message"])

        sanity_res = audit_sanity_bounds(data, "FY2025")
        self.assertFalse(sanity_res["passed"])
        self.assertEqual(sanity_res["status"], "FAIL")
        self.assertTrue(any("Costo de ventas (COGS) negativo" in a for a in sanity_res["anomalies"]))

    def test_zero_cogs_handled_cleanly(self):
        """Zero COGS (pure software/IP licensing) with 100% margin should PASS."""
        data = {
            "canonical_summary": {
                "revenue": {"FY2025": 500000.0},
                "cost_of_goods_sold": {"FY2025": 0.0},
                "gross_profit": {"FY2025": 500000.0},
                "operating_expenses": {"FY2025": 100000.0},
                "cash_and_equivalents": {"FY2025": 50000.0},
                "shares_diluted": {"FY2025": 10000.0},
            },
            "key_ratios": {"gross_margin_pct": {"FY2025": 100.0}}
        }
        gp_res = audit_gross_profit(data, "FY2025")
        self.assertTrue(gp_res["passed"])
        self.assertEqual(gp_res["status"], "PASS")
        self.assertEqual(gp_res["gross_profit_calculated"], 500000.0)

        sanity_res = audit_sanity_bounds(data, "FY2025")
        self.assertTrue(sanity_res["passed"])

    def test_cogs_greater_than_revenue_negative_gross_profit(self):
        """COGS > Revenue yielding negative Gross Profit (loss leader / deep distress)."""
        data = {
            "canonical_summary": {
                "revenue": {"FY2025": 1000.0},
                "cost_of_goods_sold": {"FY2025": 1500.0},
                "gross_profit": {"FY2025": -500.0},
                "operating_expenses": {"FY2025": 200.0},
                "cash_and_equivalents": {"FY2025": 50.0},
                "shares_diluted": {"FY2025": 100.0},
            },
            "key_ratios": {"gross_margin_pct": {"FY2025": -50.0}}
        }
        gp_res = audit_gross_profit(data, "FY2025")
        self.assertTrue(gp_res["passed"])
        self.assertEqual(gp_res["status"], "PASS")
        self.assertEqual(gp_res["gross_profit_calculated"], -500.0)
        self.assertEqual(gp_res["discrepancy_usd"], 0.0)

        sanity_res = audit_sanity_bounds(data, "FY2025")
        self.assertTrue(sanity_res["passed"])

    def test_missing_or_none_pnl_data_skips_without_exception(self):
        """Missing or None P&L data must return SKIP without raising unhandled exceptions."""
        empty_data = {"canonical_summary": {}}
        res = audit_gross_profit(empty_data, "FY2025")
        self.assertIsNone(res["passed"])
        self.assertEqual(res["status"], "SKIP")

        partial_data = {
            "canonical_summary": {
                "revenue": {"FY2025": 100.0},
                "cost_of_goods_sold": {"FY2025": None},
                "gross_profit": {"FY2025": 100.0},
            }
        }
        res2 = audit_gross_profit(partial_data, "FY2025")
        self.assertIsNone(res2["passed"])
        self.assertEqual(res2["status"], "SKIP")

    def test_fixed_thousand_dollar_tolerance_scale_fragility(self):
        """
        Empirically verifies that fixed $1000.0 tolerance in audit_gross_profit fails on large-cap
        multi-quarter sum rounding ($1M on $300B revenue, as in NVDA LTM), demonstrating lack
        of scale-invariance.
        """
        data = {
            "canonical_summary": {
                "revenue": {"LTM": 302970000000.0},
                "cost_of_goods_sold": {"LTM": 76728000000.0},
                "gross_profit": {"LTM": 226241000000.0},
            }
        }
        res = audit_gross_profit(data, "LTM")
        self.assertEqual(res["discrepancy_usd"], 1000000.0)
        self.assertFalse(res["passed"])
        self.assertEqual(res["status"], "FAIL")


class TestStressReitAffoIdentities(unittest.TestCase):
    """Stress testing REIT AFFO and CapEx decoupling under boundary conditions."""

    def test_reit_affo_zero_acquisitions_scenario(self):
        """REIT year with zero acquisitions: maintenance CapEx is purely deducted."""
        data = {
            "archetype": "REAL_ESTATE_REIT",
            "canonical_summary": {
                "ffo": {"FY2020": 2000.0},
                "recurring_capex_maintenance": {"FY2020": 150.0},
                "real_estate_acquisitions": {"FY2020": 0.0},
                "free_cash_flow": {"FY2020": 1850.0},
            }
        }
        res = audit_free_cash_flow(data, "FY2020")
        self.assertTrue(res["passed"])
        self.assertEqual(res["status"], "PASS")
        self.assertEqual(res["fcf_calculated"], 1850.0)
        self.assertEqual(res["discrepancy_usd"], 0.0)

    def test_reit_affo_negative_ffo_distress(self):
        """Distressed REIT with negative FFO: AFFO = (-FFO) - CapEx."""
        data = {
            "archetype": "REAL_ESTATE_REIT",
            "canonical_summary": {
                "ffo": {"FY2020": -500.0},
                "recurring_capex_maintenance": {"FY2020": 80.0},
                "free_cash_flow": {"FY2020": -580.0},
            }
        }
        res = audit_free_cash_flow(data, "FY2020")
        self.assertTrue(res["passed"])
        self.assertEqual(res["status"], "PASS")
        self.assertEqual(res["fcf_calculated"], -580.0)
        self.assertEqual(res["discrepancy_usd"], 0.0)

    def test_reit_affo_tolerance_exact_boundaries(self):
        """Tolerance boundary testing for REIT AFFO (diff <= 1000.0 passes, diff > 1000.0 fails)."""
        data_pass = {
            "archetype": "REAL_ESTATE_REIT",
            "canonical_summary": {
                "ffo": {"FY2025": 10000.0},
                "recurring_capex_maintenance": {"FY2025": 1000.0},
                "free_cash_flow": {"FY2025": 8001.0},  # diff = 999.0 <= 1000.0
            }
        }
        res_pass = audit_free_cash_flow(data_pass, "FY2025")
        self.assertTrue(res_pass["passed"])
        self.assertEqual(res_pass["status"], "PASS")

        data_fail = {
            "archetype": "REAL_ESTATE_REIT",
            "canonical_summary": {
                "ffo": {"FY2025": 10000.0},
                "recurring_capex_maintenance": {"FY2025": 1000.0},
                "free_cash_flow": {"FY2025": 7999.0},  # diff = 1001.0 > 1000.0
            }
        }
        res_fail = audit_free_cash_flow(data_fail, "FY2025")
        self.assertFalse(res_fail["passed"])
        self.assertEqual(res_fail["status"], "FAIL")

    def test_reit_affo_fallback_to_capital_expenditures(self):
        """When recurring_capex_maintenance is missing, fallback to capital_expenditures."""
        data = {
            "archetype": "REAL_ESTATE_REIT",
            "canonical_summary": {
                "ffo": {"FY2025": 5000.0},
                "capital_expenditures": {"FY2025": 200.0},
                "free_cash_flow": {"FY2025": 4800.0},
            }
        }
        res = audit_free_cash_flow(data, "FY2025")
        self.assertTrue(res["passed"])
        self.assertEqual(res["status"], "PASS")
        self.assertEqual(res["fcf_calculated"], 4800.0)

    def test_reit_affo_missing_metrics_skips_cleanly(self):
        """Missing FFO or CapEx in REIT returns SKIP."""
        data = {
            "archetype": "REAL_ESTATE_REIT",
            "canonical_summary": {
                "ffo": {"FY2025": None},
                "recurring_capex_maintenance": {"FY2025": 100.0},
                "free_cash_flow": {"FY2025": 500.0},
            }
        }
        res = audit_free_cash_flow(data, "FY2025")
        self.assertIsNone(res["passed"])
        self.assertEqual(res["status"], "SKIP")

    def test_archetype_lookup_missing_fallback_vulnerability(self):
        """
        Empirically demonstrates vulnerability: if archetype is only in canonical_summary
        or company_profile, audit_free_cash_flow fails to detect REIT and executes
        corporate CFO - CapEx identity.
        """
        data = {
            "canonical_summary": {
                "archetype": "REAL_ESTATE_REIT",
                "ffo": {"FY2025": 3000.0},
                "recurring_capex_maintenance": {"FY2025": 100.0},
                "free_cash_flow": {"FY2025": 2900.0},
                "cash_from_operations": {"FY2025": 1000.0},
                "capital_expenditures": {"FY2025": 100.0}
            }
        }
        res = audit_free_cash_flow(data, "FY2025")
        # Should have executed REIT AFFO (which would pass with 2900 == 3000 - 100)
        # But because data.get("archetype") is None, it executed corporate FCF and failed!
        self.assertEqual(res["test_name"], "Identidad de Free Cash Flow (FCF = CFO - CapEx)")
        self.assertFalse(res["passed"])
        self.assertEqual(res["status"], "FAIL")


class TestAdversarialCrossTickerBehaviors(unittest.TestCase):
    """Empirical investigation of cross-ticker failure modes in audit_engine."""

    def test_banking_preferred_dividend_gap_in_eps(self):
        """
        JPM has $1.36B in preferred dividends, so Net Income ($57.05B) / Shares (2.78B)
        yields $20.51, but audited reported EPS is $20.02.
        audit_eps_consistency flags diff=$0.49 > $0.20 as FAIL.
        """
        data = {
            "canonical_summary": {
                "net_income": {"FY2025": 57048000000.0},
                "shares_diluted": {"FY2025": 2781500000.0},
                "eps_diluted": {"FY2025": 20.02},
            }
        }
        res = audit_eps_consistency(data, "FY2025")
        self.assertFalse(res["passed"])
        self.assertEqual(res["status"], "FAIL")
        self.assertEqual(res["discrepancy"], 0.49)

    def test_nubank_negative_opex_flagged_by_sanity_bounds(self):
        """
        NU financial_statements.json has negative OpEx in canonical_summary
        (-$2,752.89M in FY2025), which is flagged as FAIL by audit_sanity_bounds.
        """
        data = {
            "canonical_summary": {
                "revenue": {"FY2025": 3816503000.0},
                "cost_of_goods_sold": {"FY2025": None},
                "operating_expenses": {"FY2025": -2752894000.0},
                "cash_and_equivalents": {"FY2025": 3433580000.0},
                "shares_diluted": {"FY2025": 4799000000.0},
            },
            "key_ratios": {}
        }
        res = audit_sanity_bounds(data, "FY2025")
        self.assertFalse(res["passed"])
        self.assertEqual(res["status"], "FAIL")
        self.assertTrue(any("Gastos operativos (OpEx) negativos" in a for a in res["anomalies"]))


if __name__ == "__main__":
    unittest.main()
