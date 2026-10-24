"""Regression tests for LTM cash balances and the cash-flow bridge (C1/C2).

C1: cash balances inside the cash-flow statement are point-in-time rows.  Their
LTM value must be the current quarter-end balance, never the flow identity
FY + YTD_current - YTD_previous.

C2: beginning cash is derived from the cash-flow identity
(ending cash - net change), not from whichever tag happens to be found first.
"""
import json
import os
import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "web_dashboard"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "web_dashboard.settings")

import django  # noqa: E402

django.setup()

from analytics.views import resolve_canonical_cash_flow  # noqa: E402
from pipeline.sec_extractor import is_point_in_time_cash_concept  # noqa: E402

TOL = 1.0

# Audited quarter-end balances from the 10-Q filed before each extraction.
EXPECTED_LTM = {
    "DECK": {"ending": 1_602_589_000.0, "net": -117_827_000.0, "beginning": 1_720_416_000.0},
    "META": {"ending": 29_271_000_000.0, "net": 15_443_000_000.0, "beginning": 13_828_000_000.0},
    "AAPL": {"ending": 39_544_000_000.0, "net": 3_275_000_000.0, "beginning": 36_269_000_000.0},
    "JPM": {"ending": 309_811_000_000.0, "net": -110_516_000_000.0, "beginning": 420_327_000_000.0},
    "MELI": {"ending": 16_763_000_000.0, "net": 9_875_000_000.0, "beginning": 6_888_000_000.0},
    "NVDA": {"ending": 22_443_000_000.0, "net": 10_804_000_000.0, "beginning": 11_639_000_000.0},
    "O": {"ending": 615_362_000.0, "net": -226_374_000.0, "beginning": 841_736_000.0},
    "PGR": {"ending": 193_000_000.0, "net": 58_000_000.0, "beginning": 135_000_000.0},
}

# Annual control values (AAPL/DECK zero-regression anchors).
EXPECTED_ANNUAL = {
    "DECK": {"FY2026": 1_907_249_000.0, "FY2025": 1_889_188_000.0},
    "AAPL": {"FY2025": 35_934_000_000.0, "FY2024": 29_943_000_000.0},
}


def load_fs(ticker):
    path = ROOT_DIR / "data" / "processed" / ticker / "financial_statements.json"
    return json.loads(path.read_text(encoding="utf-8"))


def canonical_cf(fs, periods):
    return resolve_canonical_cash_flow(
        fs, periods, archetype=fs.get("archetype", "STANDARD_CORPORATE")
    )


class TestLtmCashBalance(unittest.TestCase):
    def test_point_in_time_cash_classification(self):
        balances = [
            ("CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents", ""),
            ("us-gaap_CashAndCashEquivalentsAtCarryingValue", "Cash and cash equivalents at end of period"),
            ("us-gaap_RestrictedCashAndCashEquivalentsNoncurrent", ""),
            ("us-gaap_RestrictedCashAndCashEquivalentsAtCarryingValue", ""),
            ("us-gaap_CashAndDueFromBanks", ""),
            ("CashCashEquivalentsAndShortTermInvestments", ""),
            ("company_CustomCashBalance", "Cash and cash equivalents, ending balances"),
        ]
        for concept, label in balances:
            with self.subTest(concept=concept):
                self.assertTrue(is_point_in_time_cash_concept(concept, label))

        flows = [
            "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsPeriodIncreaseDecreaseIncludingExchangeRateEffect",
            "CashAndCashEquivalentsPeriodIncreaseDecrease",
            "us-gaap_EffectOfExchangeRateOnCashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
        ]
        for concept in flows:
            with self.subTest(concept=concept):
                self.assertFalse(is_point_in_time_cash_concept(concept, "Net change in cash"))

        with self.subTest(concept="beginning of period"):
            self.assertFalse(
                is_point_in_time_cash_concept(
                    "us-gaap_CashAndCashEquivalentsAtCarryingValueBeginningOfPeriod",
                    "Cash and cash equivalents at beginning of period",
                )
            )

    def test_ltm_cash_bridge_matches_10q_for_all_tickers(self):
        for ticker, expected in EXPECTED_LTM.items():
            with self.subTest(ticker=ticker):
                cf = canonical_cf(load_fs(ticker), ["LTM"])
                self.assertAlmostEqual(cf["ending_cash"]["LTM"], expected["ending"], delta=TOL)
                self.assertAlmostEqual(cf["net_change_in_cash"]["LTM"], expected["net"], delta=TOL)
                self.assertAlmostEqual(cf["beginning_cash"]["LTM"], expected["beginning"], delta=TOL)
                self.assertAlmostEqual(
                    cf["ending_cash"]["LTM"] - cf["net_change_in_cash"]["LTM"],
                    cf["beginning_cash"]["LTM"],
                    delta=TOL,
                )

    def test_cash_balance_rows_store_the_quarter_end_balance(self):
        for ticker, expected in EXPECTED_LTM.items():
            with self.subTest(ticker=ticker):
                fs = load_fs(ticker)
                row = fs["cash_flow_detail"]["CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"]
                self.assertAlmostEqual(row["values"]["LTM"], expected["ending"], delta=TOL)

        meta = load_fs("META")
        components = {
            "us-gaap_CashAndCashEquivalentsAtCarryingValue": 15_462_000_000.0,
            "us-gaap_RestrictedCashAndCashEquivalentsAtCarryingValue": 702_000_000.0,
            "us-gaap_RestrictedCashAndCashEquivalentsNoncurrent": 13_107_000_000.0,
        }
        for concept, expected in components.items():
            with self.subTest(ticker="META", concept=concept):
                self.assertAlmostEqual(
                    meta["cash_flow_detail"][concept]["values"]["LTM"], expected, delta=TOL
                )

        aapl = load_fs("AAPL")
        ending_row = next(
            row
            for row in aapl["as_reported_statements"]["cash_flow_statement"]
            if row.get("concept", "").endswith(
                "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"
            )
        )
        self.assertAlmostEqual(ending_row["values"]["LTM"], 39_544_000_000.0, delta=TOL)

    def test_annual_cash_bridge_zero_regression(self):
        for ticker, expected_by_year in EXPECTED_ANNUAL.items():
            fs = load_fs(ticker)
            periods = list(expected_by_year)
            cf = canonical_cf(fs, periods)
            for period, expected_ending in expected_by_year.items():
                with self.subTest(ticker=ticker, period=period):
                    self.assertAlmostEqual(cf["ending_cash"][period], expected_ending, delta=TOL)
                    self.assertAlmostEqual(
                        cf["ending_cash"][period] - cf["net_change_in_cash"][period],
                        cf["beginning_cash"][period],
                        delta=TOL,
                    )

    def test_nu_ltm_cash_stays_not_available(self):
        cf = canonical_cf(load_fs("NU"), ["LTM"])
        self.assertIsNone(cf["ending_cash"]["LTM"])
        self.assertIsNone(cf["net_change_in_cash"]["LTM"])
        self.assertIsNone(cf["beginning_cash"]["LTM"])


if __name__ == "__main__":
    unittest.main()
