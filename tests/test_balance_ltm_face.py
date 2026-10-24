"""Regression tests for LTM balance-sheet values taken from the 10-Q face.

The LTM balance sheet is a point-in-time snapshot: every row must come from the
face of the latest 10-Q filed before the extraction timestamp, including issuer
extension tags (e.g. ``aapl_IntangibleAssetsNetExcludingGoodwillNoncurrent``).
Values that cannot be matched unambiguously must stay ``None`` (Regla 6).
"""
import json
import os
import sys
import unittest
from pathlib import Path

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "web_dashboard"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "web_dashboard.settings")

import django  # noqa: E402

django.setup()

from analytics.views import resolve_canonical_balance_sheet  # noqa: E402
from pipeline.sec_extractor import (  # noqa: E402
    face_concept_token,
    find_face_value,
    merge_quarter_only_face_rows,
    normalize_face_label,
)

DATE_COL = "2026-06-27"
M = 1_000_000.0


def _face_df(rows):
    """Build a 10-Q face dataframe with the columns EDGAR's balance sheet uses."""
    base = [
        {"concept": c, "label": l, "level": lv, "abstract": abs_, "dimension": dim, DATE_COL: v}
        for c, l, lv, abs_, dim, v in rows
    ]
    return pd.DataFrame(base, columns=["concept", "label", "level", "abstract", "dimension", DATE_COL])


class TestFaceHelpers(unittest.TestCase):
    def test_extension_tag_token_is_namespace_and_prefix_agnostic(self):
        self.assertEqual(
            face_concept_token("aapl:IntangibleAssetsNetExcludingGoodwillNoncurrent"),
            "intangibleassetsnetexcludinggoodwillnoncurrent",
        )
        self.assertEqual(
            face_concept_token("us-gaap_IntangibleAssetsNetExcludingGoodwillNoncurrent"),
            "intangibleassetsnetexcludinggoodwillnoncurrent",
        )
        self.assertEqual(face_concept_token(None), "")

    def test_label_normalization_ignores_parentheticals_and_punctuation(self):
        self.assertEqual(
            normalize_face_label("Intangible assets, net (Note 5)"),
            normalize_face_label("Intangible Assets, Net"),
        )
        self.assertNotEqual(
            normalize_face_label("Other non-current assets"),
            normalize_face_label("Total non-current assets"),
        )

    def test_find_face_value_matches_extension_concept(self):
        q = _face_df([
            ("us-gaap_OtherAssetsNoncurrent", "Other non-current assets", 3, False, False, 77_557 * M),
            ("aapl_IntangibleAssetsNetExcludingGoodwillNoncurrent", "Intangible assets, net", 3, False, False, 20_342 * M),
        ])
        value = find_face_value(
            q,
            DATE_COL,
            "IntangibleAssetsNetExcludingGoodwillNoncurrent",
            "Intangible assets, net",
        )
        self.assertEqual(value, 20_342 * M)

    def test_find_face_value_falls_back_to_unique_label(self):
        q = _face_df([
            ("aapl_CustomTag", "Intangible assets, net", 3, False, False, 20_342 * M),
        ])
        value = find_face_value(q, DATE_COL, "IntangibleAssetsNetExcludingGoodwill", "Intangible assets, net")
        self.assertEqual(value, 20_342 * M)

    def test_find_face_value_returns_none_when_duplicate_token_has_no_label_match(self):
        q = _face_df([
            ("aapl_IntangibleAssetsNetExcludingGoodwill", "Intangible assets, net", 3, False, False, 25_417 * M),
            ("aapl_IntangibleAssetsNetExcludingGoodwill", "Intangible assets, gross", 3, False, False, 30_000 * M),
        ])
        value = find_face_value(
            q,
            DATE_COL,
            "IntangibleAssetsNetExcludingGoodwill",
            "Other intangible assets",
        )
        self.assertIsNone(value)

    def test_find_face_value_disambiguates_duplicate_token_by_label(self):
        q = _face_df([
            ("aapl_IntangibleAssetsNetExcludingGoodwill", "Intangible assets, gross", 3, False, False, 30_000 * M),
            ("aapl_IntangibleAssetsNetExcludingGoodwill", "Intangible assets, net", 3, False, False, 20_342 * M),
        ])
        value = find_face_value(
            q,
            DATE_COL,
            "IntangibleAssetsNetExcludingGoodwill",
            "Intangible assets, net",
        )
        self.assertEqual(value, 20_342 * M)

    def test_find_face_value_ignores_dimensional_rows(self):
        q = _face_df([
            ("aapl_IntangibleAssetsNetExcludingGoodwill", "Intangible assets, net", 3, False, True, 25_417 * M),
            ("aapl_IntangibleAssetsNetExcludingGoodwill", "Intangible assets, net", 3, False, False, 20_342 * M),
        ])
        value = find_face_value(
            q,
            DATE_COL,
            "IntangibleAssetsNetExcludingGoodwill",
            "Intangible assets, net",
        )
        self.assertEqual(value, 20_342 * M)

    def test_find_face_value_returns_none_without_date_column(self):
        q = _face_df([
            ("us-gaap_OtherAssetsNoncurrent", "Other non-current assets", 3, False, False, 77_557 * M),
        ])
        self.assertIsNone(find_face_value(q, "2026-09-30", "OtherAssetsNoncurrent", "Other non-current assets"))


class TestQuarterOnlyFaceRows(unittest.TestCase):
    def _annual(self):
        return pd.DataFrame([
            {"concept": "us-gaap_CashAndCashEquivalentsAtCarryingValue", "label": "Cash and cash equivalents", "level": 3, "abstract": False, DATE_COL: None},
            {"concept": "us-gaap_OtherAssetsNoncurrent", "label": "Other non-current assets", "level": 3, "abstract": False, DATE_COL: None},
            {"concept": "us-gaap_AssetsNoncurrent", "label": "Total non-current assets", "level": 3, "abstract": False, DATE_COL: 211_284 * M},
        ])

    def _quarter(self):
        return _face_df([
            ("us-gaap_CashAndCashEquivalentsAtCarryingValue", "Cash and cash equivalents", 3, False, False, 39_544 * M),
            ("us-gaap_OtherAssetsNoncurrent", "Other non-current assets", 3, False, False, 77_557 * M),
            ("aapl_IntangibleAssetsNetExcludingGoodwillNoncurrent", "Intangible assets, net", 3, False, False, 20_342 * M),
            ("us-gaap_AssetsNoncurrent", "Total non-current assets", 3, False, False, 233_448 * M),
        ])

    def test_new_quarter_line_is_inserted_after_its_anchor(self):
        merged = merge_quarter_only_face_rows(self._annual(), self._quarter())
        self.assertEqual(list(merged["concept"]), [
            "us-gaap_CashAndCashEquivalentsAtCarryingValue",
            "us-gaap_OtherAssetsNoncurrent",
            "aapl_IntangibleAssetsNetExcludingGoodwillNoncurrent",
            "us-gaap_AssetsNoncurrent",
        ])
        new_row = merged.iloc[2]
        self.assertEqual(new_row["label"], "Intangible assets, net")
        # Annual amounts stay unknown; LTM is filled from the 10-Q face later.
        self.assertTrue(pd.isna(new_row[DATE_COL]))

    def test_existing_quarter_lines_are_not_duplicated(self):
        merged = merge_quarter_only_face_rows(self._annual(), self._quarter())
        self.assertEqual(len(merged), 4)
        self.assertEqual(merged["concept"].duplicated().sum(), 0)

    def test_label_match_anchors_rows_with_different_tags(self):
        annual = self._annual()
        quarter = self._quarter()
        quarter.loc[quarter["concept"] == "us-gaap_OtherAssetsNoncurrent", "concept"] = "aapl_OtherAssetsNoncurrent"
        merged = merge_quarter_only_face_rows(annual, quarter)
        self.assertEqual(len(merged), 4)
        self.assertEqual(merged.iloc[2]["concept"], "aapl_IntangibleAssetsNetExcludingGoodwillNoncurrent")

    def test_leading_quarter_line_without_anchor_is_ignored(self):
        annual = self._annual()
        quarter = _face_df([
            ("aapl_NewFirstLine", "New first line", 3, False, False, 1 * M),
            ("us-gaap_CashAndCashEquivalentsAtCarryingValue", "Cash and cash equivalents", 3, False, False, 39_544 * M),
        ])
        merged = merge_quarter_only_face_rows(annual, quarter)
        self.assertEqual(len(merged), 3)
        self.assertNotIn("aapl_NewFirstLine", list(merged["concept"]))


class TestAaplLtmBalanceFace(unittest.TestCase):
    """AAPL Q3 FY2026 10-Q face: intangibles were tagged with an issuer extension."""

    @classmethod
    def setUpClass(cls):
        path = ROOT_DIR / "data" / "processed" / "AAPL" / "financial_statements.json"
        with open(path, encoding="utf-8") as fh:
            cls.fs = json.load(fh)
        cls.bs = resolve_canonical_balance_sheet(cls.fs, ["LTM", "FY2025"])

    def test_ltm_intangibles_come_from_the_10q_face(self):
        values = self.fs["balance_sheet_detail"]["IntangibleAssetsNetExcludingGoodwill"]["values"]
        self.assertEqual(values["LTM"], 20_342 * M)

    def test_goodwill_has_no_ltm_value_on_the_face(self):
        values = self.fs["balance_sheet_detail"]["Goodwill"]["values"]
        self.assertNotIn("LTM", values)

    def test_as_reported_contains_the_issuer_extension_row(self):
        rows = [
            r for r in self.fs["as_reported_statements"]["balance_sheet"]
            if r.get("concept") == "aapl_IntangibleAssetsNetExcludingGoodwillNoncurrent"
        ]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["values"]["LTM"], 20_342 * M)
        self.assertIsNone(rows[0]["values"]["FY2025"])

    def test_rendered_ltm_balance_reconciles_with_the_10q_face(self):
        self.assertEqual(self.bs["goodwill_and_intangibles"]["LTM"], 20_342 * M)
        self.assertEqual(self.bs["total_noncurrent_assets"]["LTM"], 233_448 * M)
        self.assertEqual(self.bs["total_assets"]["LTM"], 383_266 * M)
        components = (
            self.bs["net_ppe_plus_rou"]["LTM"]
            + self.bs["goodwill_and_intangibles"]["LTM"]
            + self.bs["long_term_investments"]["LTM"]
            + self.bs["other_noncurrent_assets"]["LTM"]
        )
        self.assertEqual(components, self.bs["total_noncurrent_assets"]["LTM"])

    def test_fy2025_rou_is_not_double_counted(self):
        # AAPL embeds the ROU asset in "Other non-current assets"; showing it
        # separately would overstate FY2025 non-current assets by 11,551M.
        self.assertIsNone(self.bs["rou_asset"]["FY2025"])
        self.assertEqual(self.bs["total_noncurrent_assets"]["FY2025"], 211_284 * M)
        components = (
            self.bs["net_ppe_plus_rou"]["FY2025"]
            + (self.bs["goodwill_and_intangibles"]["FY2025"] or 0.0)
            + self.bs["long_term_investments"]["FY2025"]
            + self.bs["other_noncurrent_assets"]["FY2025"]
        )
        self.assertEqual(components, self.bs["total_noncurrent_assets"]["FY2025"])


if __name__ == "__main__":
    unittest.main()
