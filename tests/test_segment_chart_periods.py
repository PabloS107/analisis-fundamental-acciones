# -*- coding: utf-8 -*-
import os
import sys
import json
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "web_dashboard"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "web_dashboard.settings")
import django
django.setup()

from analytics.views.views_charts import build_charts_and_segments_context
from django.test import Client


class TestSegmentChartPeriods(unittest.TestCase):
    """
    Test suite for dynamic X-axis periods in segment trend charts (Regla 2 & Regla 4).
    Verifies that the X-axis begins dynamically at the earliest year where actual
    quantitative data exists, avoiding leading null gaps.
    """

    def setUp(self):
        self.client = Client()

    def test_aapl_segments_start_at_fy2017(self):
        ticker_dir = ROOT_DIR / "data" / "processed" / "AAPL"
        with open(ticker_dir / "financial_statements.json", "r", encoding="utf-8") as f:
            fs = json.load(f)
        fys = fs.get("fiscal_years", [])[:10]
        canonical = fs.get("canonical_summary", {})
        key_ratios = fs.get("key_ratios", {})

        ctx = build_charts_and_segments_context(
            ticker_dir=ticker_dir,
            fs=fs,
            fys=fys,
            canonical=canonical,
            key_ratios=key_ratios,
            enriched={},
        )

        seg_chart_periods = json.loads(ctx["seg_chart_periods_json"])
        prod_chart_periods = json.loads(ctx["prod_chart_periods_json"])
        geo_chart_periods = json.loads(ctx["geo_chart_periods_json"])
        prod_datasets = json.loads(ctx["products_trend_json"])
        geo_datasets = json.loads(ctx["geos_trend_json"])

        # In AAPL, segment data begins in FY2017
        self.assertEqual(seg_chart_periods[0], "FY2017")
        self.assertEqual(seg_chart_periods[-1], "LTM")
        self.assertEqual(prod_chart_periods[0], "FY2017")
        self.assertEqual(geo_chart_periods[0], "FY2017")

        # Must not contain empty historical periods FY2015 or FY2016
        self.assertNotIn("FY2015", seg_chart_periods)
        self.assertNotIn("FY2016", seg_chart_periods)
        self.assertNotIn("FY2015", prod_chart_periods)
        self.assertNotIn("FY2016", prod_chart_periods)

        # Dataset points must match label length exactly and have no leading None
        for ds in prod_datasets:
            self.assertEqual(len(ds["data"]), len(prod_chart_periods))
            self.assertIsNotNone(ds["data"][0], f"Product {ds['label']} has leading None at start period")

        for ds in geo_datasets:
            self.assertEqual(len(ds["data"]), len(geo_chart_periods))
            self.assertIsNotNone(ds["data"][0], f"Geo {ds['label']} has leading None at start period")

    def test_deck_segments_dynamic_start(self):
        ticker_dir = ROOT_DIR / "data" / "processed" / "DECK"
        with open(ticker_dir / "financial_statements.json", "r", encoding="utf-8") as f:
            fs = json.load(f)
        fys = fs.get("fiscal_years", [])[:10]
        canonical = fs.get("canonical_summary", {})
        key_ratios = fs.get("key_ratios", {})

        ctx = build_charts_and_segments_context(
            ticker_dir=ticker_dir,
            fs=fs,
            fys=fys,
            canonical=canonical,
            key_ratios=key_ratios,
            enriched={},
        )

        prod_chart_periods = json.loads(ctx["prod_chart_periods_json"])
        geo_chart_periods = json.loads(ctx["geo_chart_periods_json"])
        prod_datasets = json.loads(ctx["products_trend_json"])
        geo_datasets = json.loads(ctx["geos_trend_json"])

        # DECK product segments (HOKA, UGG, Other Brands) start at FY2023
        self.assertEqual(prod_chart_periods[0], "FY2023")
        self.assertEqual(prod_chart_periods[-1], "LTM")

        # DECK geo segments (Domestic, International) start at FY2024
        self.assertEqual(geo_chart_periods[0], "FY2024")
        self.assertEqual(geo_chart_periods[-1], "LTM")

        # Zero leading None values
        for ds in prod_datasets:
            self.assertEqual(len(ds["data"]), len(prod_chart_periods))
            self.assertIsNotNone(ds["data"][0], f"Product {ds['label']} has leading None")

        for ds in geo_datasets:
            self.assertEqual(len(ds["data"]), len(geo_chart_periods))
            self.assertIsNotNone(ds["data"][0], f"Geo {ds['label']} has leading None")

    def test_web_endpoint_renders_chart_periods(self):
        # Verify rendered HTML for AAPL contains prodChartPeriods and geoChartPeriods
        resp = self.client.get("/company/AAPL/")
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode("utf-8")
        self.assertIn("const prodChartPeriods = [", content)
        self.assertIn("const geoChartPeriods = [", content)
        self.assertIn('"FY2017"', content)

        # Verify rendered HTML for DECK
        resp_deck = self.client.get("/company/DECK/")
        self.assertEqual(resp_deck.status_code, 200)
        content_deck = resp_deck.content.decode("utf-8")
        self.assertIn("const prodChartPeriods = [", content_deck)
        self.assertIn("const geoChartPeriods = [", content_deck)
        self.assertIn('"FY2023"', content_deck)


    def test_dynamic_trimming_of_leading_empty_periods(self):
        # Universal test (Regla 4): company with leading empty periods in FY2015-FY2018, data starting FY2019
        mock_fs = {
            "fiscal_years": ["LTM", "FY2022", "FY2021", "FY2020", "FY2019", "FY2018", "FY2017", "FY2016", "FY2015"],
            "canonical_summary": {
                "revenue": {"FY2019": 100.0, "FY2020": 110.0, "FY2021": 120.0, "FY2022": 130.0, "LTM": 135.0},
                "net_income": {"FY2019": 20.0, "FY2020": 22.0, "FY2021": 25.0, "FY2022": 28.0, "LTM": 30.0},
            },
            "key_ratios": {},
        }
        mock_dir = ROOT_DIR / "data" / "processed" / "MOCK_EMPTY"
        mock_dir.mkdir(parents=True, exist_ok=True)
        seg_file = mock_dir / "segments_data.json"
        with open(seg_file, "w", encoding="utf-8") as f:
            json.dump({
                "periods": ["LTM", "FY2022", "FY2021", "FY2020", "FY2019"],
                "product_segments": [{
                    "name": "Cloud",
                    "values": {"FY2019": 50.0, "FY2020": 55.0, "FY2021": 60.0, "FY2022": 65.0, "LTM": 70.0}
                }],
                "geographic_segments": [{
                    "name": "US",
                    "values": {"FY2020": 80.0, "FY2021": 90.0, "FY2022": 95.0, "LTM": 100.0}
                }]
            }, f)

        try:
            ctx = build_charts_and_segments_context(
                ticker_dir=mock_dir,
                fs=mock_fs,
                fys=mock_fs["fiscal_years"],
                canonical=mock_fs["canonical_summary"],
                key_ratios={},
                enriched={},
            )
            chart_periods = json.loads(ctx["chart_periods_json"])
            prod_periods = json.loads(ctx["prod_chart_periods_json"])
            geo_periods = json.loads(ctx["geo_chart_periods_json"])

            # Main charts start at earliest year with quantitative data (FY2019)
            self.assertEqual(chart_periods[0], "FY2019")
            self.assertEqual(chart_periods[-1], "LTM")
            self.assertNotIn("FY2015", chart_periods)
            self.assertNotIn("FY2018", chart_periods)

            # Product chart starts at FY2019
            self.assertEqual(prod_periods[0], "FY2019")
            self.assertEqual(prod_periods[-1], "LTM")

            # Geo chart starts at FY2020
            self.assertEqual(geo_periods[0], "FY2020")
            self.assertEqual(geo_periods[-1], "LTM")
        finally:
            if seg_file.exists():
                seg_file.unlink()
            if mock_dir.exists():
                mock_dir.rmdir()


if __name__ == "__main__":
    unittest.main()

