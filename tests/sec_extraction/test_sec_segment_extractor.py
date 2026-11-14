# -*- coding: utf-8 -*-
"""
Unit tests for universal segment & geography XBRL extraction, LTM cutover handling,
competing ASC 280 partition isolation, strict op-margin matching, and UI N/D integrity.
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[2]
for _p in (ROOT_DIR, ROOT_DIR / "pipeline", ROOT_DIR / "web_dashboard"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import pipeline  # noqa: E402, F401
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "web_dashboard.settings")
import django  # noqa: E402
django.setup()

from pipeline.sec_modules.sec_segment_extractor import (  # noqa: E402
    _attach_segment_operating_income,
    _canon_match_key,
    _clean_segment_label_and_parent,
    _detect_statement_divisor,
    _extract_10q_period_pair,
    _filter_segment_statements,
    _is_valid_segment_concept,
    _resolve_competing_geo_partitions,
    _scale_with_divisor,
    build_and_save_segments_data,
)
from pipeline.sec_modules.kpi_extractor import _update_channel_metric, normalize_corporate_kpis  # noqa: E402
from analytics.views.views_charts_segments import build_segments_context  # noqa: E402


class _MockStmt:
    def __init__(self, role_or_type: str, df: pd.DataFrame):
        self.role_or_type = role_or_type
        self._df = df

    def to_dataframe(self):
        return self._df


class _MockXBRL:
    def __init__(self, stmts):
        self.statements = stmts


class _MockFiling:
    def __init__(self, form: str, period_of_report: str, xbrl_doc: _MockXBRL):
        self.form = form
        self.period_of_report = period_of_report
        self._xbrl = xbrl_doc

    def xbrl(self):
        return self._xbrl


class _MockCompany:
    def __init__(self, ticker: str, f10k_list, f10q_list):
        self.ticker = ticker
        self._k = f10k_list
        self._q = f10q_list

    def get_filings(self, form=None):
        if form == "10-K":
            return self._k
        if form == "10-Q":
            return self._q
        return []


class TestSecSegmentExtractorUniversal(unittest.TestCase):
    def test_statement_divisor_and_negative_zero(self):
        df = pd.DataFrame([
            {"concept": "us-gaap:Revenues", "dimension_axis": "", "label": "Revenues", "2025-12-31 (FY)": 100000000000.0},
            {"concept": "us-gaap:Revenues", "dimension_axis": "", "label": "Reconciling", "2025-12-31 (FY)": -5000.0},
        ])
        divisor = _detect_statement_divisor(df, ["2025-12-31 (FY)"])
        self.assertEqual(divisor, 1e6)
        self.assertEqual(_scale_with_divisor(-5000.0, divisor), 0.0)
        self.assertNotIn("-", str(_scale_with_divisor(-5000.0, divisor)))

    def test_10q_skips_empty_intermediate_ytd_column_and_matches_52week_prior(self):
        # Pattern seen in Q3 10-Q (UBER/O): empty 2026-06-30 (YTD) sits between 2026-09-30 (YTD) and 2025-09-30 (YTD)
        df_q3 = pd.DataFrame([
            {
                "concept": "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
                "label": "Mobility",
                "2026-09-30 (YTD)": 21000000000.0,
                "2026-06-30 (YTD)": float("nan"),
                "2025-09-30 (YTD)": 18000000000.0,
            }
        ])
        pair = _extract_10q_period_pair(df_q3, k_rep_date="2025-12-31")
        self.assertIsNotNone(pair)
        self.assertEqual(pair["curr_col"], "2026-09-30 (YTD)")
        self.assertEqual(pair["prev_col"], "2025-09-30 (YTD)")

        # 52/53-week fiscal year shift pattern (NVDA): 2026-07-26 pairs with 2025-07-27
        df_52w = pd.DataFrame([
            {
                "concept": "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
                "label": "Data Center",
                "2026-07-26 (YTD)": 164269000000.0,
                "2025-07-27 (YTD)": 80208000000.0,
            }
        ])
        pair_52 = _extract_10q_period_pair(df_52w, k_rep_date="2026-01-25")
        self.assertIsNotNone(pair_52)
        self.assertEqual(pair_52["curr_col"], "2026-07-26 (YTD)")
        self.assertEqual(pair_52["prev_col"], "2025-07-27 (YTD)")
        self.assertIn("6M YTD", pair_52["period_label"])

    def test_channel_classifier_excludes_reit_retail_sector(self):
        parsed_reit = _clean_segment_label_and_parent("Retail", "srt:ProductOrServiceAxis")
        self.assertFalse(parsed_reit["is_channel"])
        self.assertFalse(parsed_reit["is_geo"])

        parsed_prod_geo = _clean_segment_label_and_parent("Retail - U.S.", "srt:ProductOrServiceAxis")
        self.assertEqual(parsed_prod_geo["clean_name"], "Retail (U.S.)")
        self.assertEqual(parsed_prod_geo["parent_segment"], "Retail")
        self.assertFalse(parsed_prod_geo["is_geo"])

        parsed_sales_chan = _clean_segment_label_and_parent("Wholesale", "us-gaap:SalesChannelAxis")
        self.assertTrue(parsed_sales_chan["is_channel"])

    def test_resegmentation_cutover_and_precedent_table_flow(self):
        # Simulates NVDA re-segmentation in Q2 FY27 10-Q
        df_10k_seg = pd.DataFrame([
            {"concept": "us-gaap:Revenues", "dimension_axis": "us-gaap:StatementBusinessSegmentsAxis", "level": 0, "label": "Compute", "2026-01-25 (FY)": 162361e6, "2025-01-26 (FY)": 102000e6},
            {"concept": "us-gaap:Revenues", "dimension_axis": "us-gaap:StatementBusinessSegmentsAxis", "level": 0, "label": "Networking", "2026-01-25 (FY)": 31376e6, "2025-01-26 (FY)": 13000e6},
            {"concept": "us-gaap:Revenues", "dimension_axis": "us-gaap:StatementBusinessSegmentsAxis", "level": 0, "label": "Data Center", "2026-01-25 (FY)": 193737e6, "2025-01-26 (FY)": 115000e6},
            {"concept": "us-gaap:Revenues", "dimension_axis": "us-gaap:StatementBusinessSegmentsAxis", "level": 0, "label": "Gaming", "2026-01-25 (FY)": 16042e6, "2025-01-26 (FY)": 11350e6},
            {"concept": "us-gaap:Revenues", "dimension_axis": "us-gaap:StatementBusinessSegmentsAxis", "level": 0, "label": "Automotive", "2026-01-25 (FY)": 2349e6, "2025-01-26 (FY)": 1700e6},
        ])
        df_10k_geo = pd.DataFrame([
            {"concept": "us-gaap:Revenues", "dimension_axis": "srt:StatementGeographicalAxis", "level": 0, "label": "United States", "2026-01-25 (FY)": 150000e6, "2025-01-26 (FY)": 61000e6},
            {"concept": "us-gaap:Revenues", "dimension_axis": "srt:StatementGeographicalAxis", "level": 0, "label": "Taiwan", "2026-01-25 (FY)": 35000e6, "2025-01-26 (FY)": 22000e6},
            {"concept": "us-gaap:Revenues", "dimension_axis": "srt:StatementGeographicalAxis", "level": 0, "label": "Singapore", "2026-01-25 (FY)": float("nan"), "2025-01-26 (FY)": 23000e6},
        ])
        df_10q_seg = pd.DataFrame([
            {"concept": "us-gaap:Revenues", "dimension_axis": "", "level": 0, "label": "Total Revenue", "2026-07-26 (YTD)": 177837e6, "2025-07-27 (YTD)": 90805e6},
            {"concept": "us-gaap:Revenues", "dimension_axis": "us-gaap:StatementBusinessSegmentsAxis", "level": 0, "label": "Data Center", "2026-07-26 (YTD)": 164269e6, "2025-07-27 (YTD)": 80208e6},
            {"concept": "us-gaap:Revenues", "dimension_axis": "us-gaap:StatementBusinessSegmentsAxis", "level": 1, "label": "Hyperscale", "2026-07-26 (YTD)": 91761e6, "2025-07-27 (YTD)": 46428e6},
            {"concept": "us-gaap:Revenues", "dimension_axis": "us-gaap:StatementBusinessSegmentsAxis", "level": 1, "label": "AI Clouds, Industrial, & Enterprise", "2026-07-26 (YTD)": 72508e6, "2025-07-27 (YTD)": 33780e6},
            {"concept": "us-gaap:Revenues", "dimension_axis": "us-gaap:StatementBusinessSegmentsAxis", "level": 0, "label": "Edge Computing", "2026-07-26 (YTD)": 13568e6, "2025-07-27 (YTD)": 10597e6},
        ])

        f10k = _MockFiling("10-K", "2026-01-25", _MockXBRL([
            _MockStmt("SegmentInformationDetails", df_10k_seg),
            _MockStmt("GeographicAreasDetails", df_10k_geo),
        ]))
        f10q = _MockFiling("10-Q", "2026-07-26", _MockXBRL([
            _MockStmt("SegmentInformationDetails", df_10q_seg),
        ]))
        comp = _MockCompany("TESTCO", [f10k], [f10q])

        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            all_fys = ["LTM", "FY2026", "FY2025"]
            can_rev = {"LTM": 302970.0, "FY2026": 212128.0, "FY2025": 130000.0}
            build_and_save_segments_data(comp, all_fys, output_dir=tmp_dir, canonical_rev=can_rev)

            with open(tmp_dir / "segments_data.json", "r", encoding="utf-8") as f:
                seg_json = json.load(f)

            prods = {p["name"]: p for p in seg_json["product_segments"]}
            self.assertEqual(prods["Data Center"]["status"], "active")
            self.assertEqual(prods["Data Center"]["values"]["LTM"], 277798.0)
            self.assertEqual(prods["Edge Computing"]["status"], "active")
            self.assertNotIn("LTM", prods["Edge Computing"]["values"])
            self.assertEqual(prods["Edge Computing"]["interim_disclosure"]["current_ytd"], 13568.0)

            for old_name in ("Compute", "Networking", "Gaming", "Automotive"):
                self.assertEqual(prods[old_name]["status"], "discontinued")
                self.assertEqual(prods[old_name]["discontinued_reason"], "superseded_in_latest_10q")
                self.assertNotIn("LTM", prods[old_name]["values"])

            # Geo wasn't in 10-Q -> annual_only, zero LTM fabrication for United States/Taiwan; Singapore discontinued
            geos = {g["name"]: g for g in seg_json["geographic_segments"]}
            self.assertEqual(geos["United States"]["status"], "active")
            self.assertNotIn("LTM", geos["United States"]["values"])
            self.assertEqual(geos["Singapore"]["status"], "discontinued")

            # Verify UI context renders cutover notice, interim donut mix, historical chart & precedent table
            ctx = build_segments_context(
                ticker_dir=tmp_dir,
                fys=all_fys,
                canonical={"revenue": can_rev},
                corp_kpis={"operating_margin_pct": 60.0},
                is_ltm_equal_latest_fy=False,
                first_fy="FY2026",
            )
            self.assertTrue(ctx["has_discontinued_products"])
            self.assertIsNotNone(ctx["product_cutover_notice"])
            self.assertEqual(ctx["kpis_segments"]["top_product_name"], "Data Center")
            self.assertEqual(ctx["kpis_segments"]["second_product_name"], "Edge Computing")
            self.assertEqual(ctx["donut_prod_labels"], ["Data Center", "Edge Computing"])
            self.assertEqual(ctx["donut_prod_data"], [164269.0, 13568.0])
            self.assertIn("Singapore", [r["raw_name"] for r in ctx["table_geos_discontinued"]])

    def test_competing_geo_partitions_isolated_cleanly(self):
        geos = [
            {"name": "United States & Canada", "is_subsegment": False, "is_subtotal": False, "values": {"LTM": 28000.0}},
            {"name": "Latin America", "is_subsegment": False, "is_subtotal": False, "values": {"LTM": 4000.0}},
            {"name": "Europe, Middle East and Africa", "is_subsegment": False, "is_subtotal": False, "values": {"LTM": 18000.0}},
            {"name": "Asia Pacific", "is_subsegment": False, "is_subtotal": False, "values": {"LTM": 6500.0}},
            {"name": "United States", "is_subsegment": False, "is_subtotal": False, "values": {"LTM": 27000.0}},
            {"name": "United Kingdom", "is_subsegment": False, "is_subtotal": False, "values": {"LTM": 7000.0}},
            {"name": "All other countries", "is_subsegment": False, "is_subtotal": False, "values": {"LTM": 22500.0}},
        ]
        _resolve_competing_geo_partitions(geos, "FY2025", {"LTM": 56500.0})
        by_name = {g["name"]: g for g in geos}
        self.assertFalse(by_name["United States & Canada"].get("is_country_breakdown", False))
        self.assertTrue(by_name["United States"].get("is_country_breakdown"))
        self.assertTrue(by_name["United Kingdom"].get("is_country_breakdown"))
        self.assertTrue(by_name["All other countries"].get("is_country_breakdown"))

    def test_strict_op_margin_matching_blocks_substring_and_missing_geo_shows_nd(self):
        prods = [
            {"name": "Google Network", "is_subsegment": False, "is_subtotal": False, "is_reconciling": False, "values": {"LTM": 30000.0}},
            {"name": "Google Services", "is_subsegment": False, "is_subtotal": False, "is_reconciling": False, "values": {"LTM": 300000.0}},
        ]
        op_inc = [{"name": "Google Services", "values": {"LTM": 120000.0}}]
        _attach_segment_operating_income(prods, [], [], op_inc)
        self.assertNotIn("operating_margin_pct", prods[0])
        self.assertEqual(prods[1]["operating_margin_pct"]["LTM"], 40.0)

        # Missing geography must show N/D instead of fake 100% international
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            with open(tmp_dir / "segments_data.json", "w", encoding="utf-8") as f:
                json.dump({
                    "periods": ["LTM", "FY2025"],
                    "product_segments": [{"name": "Personal Lines", "status": "active", "values": {"FY2025": 50000.0}}],
                    "geographic_segments": [],
                    "metadata": {"geo_reported": False},
                }, f)
            ctx = build_segments_context(tmp_dir, ["LTM", "FY2025"], {"revenue": {"FY2025": 50000.0}}, {}, False, "FY2025")
            self.assertFalse(ctx["geo_reported"])
            self.assertEqual(ctx["kpis_segments"]["top_geo_ltm"], "N/D")
            self.assertEqual(ctx["kpis_segments"]["intl_pct"], "N/D")

    def test_kpi_channel_billion_normalization_and_active_segment_sync(self):
        chans = {}
        _update_channel_metric(
            chans,
            "Wholesale",
            "Wholesale net sales increased 15.0% to $1.093 billion compared to $950 million",
            "wholesale net sales increased 15.0% to $1.093 billion compared to $950 million",
        )
        self.assertEqual(chans["Wholesale"]["revenue_usd_m"], 1093.0)
        self.assertEqual(chans["Wholesale"]["growth_yoy_pct"], 15.0)

        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            with open(tmp_dir / "segments_data.json", "w", encoding="utf-8") as f:
                json.dump({
                    "product_segments": [
                        {"name": "Data Center", "status": "active", "values": {"LTM": 277798.0}},
                        {"name": "Gaming", "status": "discontinued", "values": {"FY2026": 16042.0}},
                    ],
                    "geographic_segments": [
                        {"name": "United States", "status": "active", "values": {"FY2026": 150000.0}},
                        {"name": "United States (Country)", "status": "active", "is_country_breakdown": True, "values": {"FY2026": 150000.0}},
                    ],
                }, f)
            res = normalize_corporate_kpis({}, {}, {"brand_segmentation": {"StaleBrand": {"revenue_usd_m": 1.0}}}, output_dir=tmp_dir)
            self.assertIn("Data Center", res["brand_segmentation"])
            self.assertNotIn("Gaming", res["brand_segmentation"])
            self.assertNotIn("StaleBrand", res["brand_segmentation"])
            self.assertNotIn("United States (Country)", res["geographic_breakdown"])

    def test_root_fixes_for_asc606_banking_reit_fx_and_uppercase_countries(self):
        # 1. ASC 606 ExcludingAssessedTax and banking RevenuesNetOfInterestExpense must be accepted
        self.assertEqual(
            _is_valid_segment_concept("us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax"),
            (True, True, False, 1),
        )
        self.assertEqual(
            _is_valid_segment_concept("us-gaap:RevenuesNetOfInterestExpense"),
            (True, True, False, 1),
        )
        # Non-revenue tax/asset concepts remain rejected
        self.assertFalse(_is_valid_segment_concept("us-gaap:DeferredTaxAssetsNet")[0])

        # 2. Lease-intangible / delinquency schedules must be filtered out of segment statements
        bad_stmt = _MockStmt(
            "InvestmentsinRealEstateScheduleofFutureImpactRelatedtoAmortizationofAboveMarketBelowMarketandinplaceLeaseIntangiblesDetails",
            pd.DataFrame(),
        )
        good_stmt = _MockStmt("SegmentandGeographicInformationScheduleofDisaggregationofRevenuebySegmentDetails", pd.DataFrame())
        self.assertEqual(_filter_segment_statements(_MockXBRL([bad_stmt, good_stmt])), [good_stmt])

        # 3. REIT 'Retail - Other' nests cleanly under 'Retail' rather than parent='Other'
        parsed_reit_other = _clean_segment_label_and_parent("Retail - Other", "srt:ProductOrServiceAxis")
        self.assertEqual(parsed_reit_other["clean_name"], "Retail (Other)")
        self.assertEqual(parsed_reit_other["parent_segment"], "Retail")
        self.assertTrue(parsed_reit_other["is_subsegment"])

        # 4. FX derivatives classify as reconciling items rather than top product KPIs
        parsed_fx = _clean_segment_label_and_parent("Foreign exchange derivatives", "us-gaap:ProductOrServiceAxis")
        self.assertTrue(parsed_fx["is_reconciling"])

        # 5. Pure country names on legacy business segment axes classify as geography, not products
        for country in ("CHINA", "TAIWAN", "UNITED STATES"):
            parsed_country = _clean_segment_label_and_parent(country, "us-gaap:StatementBusinessSegmentsAxis")
            self.assertTrue(parsed_country["is_geo"])

        # 6. Trailing footnote markers like '(2)' are stripped cleanly from segment & parent names
        parsed_fn = _clean_segment_label_and_parent("Other (2) - U.S.", "srt:ProductOrServiceAxis")
        self.assertEqual(parsed_fn["clean_name"], "Other (U.S.)")
        self.assertEqual(parsed_fn["parent_segment"], "Other")
        self.assertTrue(parsed_fn["is_subsegment"])

        # 7. Country that belongs to primary regional segments (AAPL Japan pattern) stays primary
        aapl_geos = [
            {"name": "Americas", "is_subsegment": False, "is_subtotal": False, "values": {"FY2026": 198083.0}},
            {"name": "Europe", "is_subsegment": False, "is_subtotal": False, "values": {"FY2026": 127604.0}},
            {"name": "Greater China", "is_subsegment": False, "is_subtotal": False, "values": {"FY2026": 82378.0}},
            {"name": "Japan", "is_subsegment": False, "is_subtotal": False, "values": {"FY2026": 30908.0}},
            {"name": "Rest of Asia Pacific", "is_subsegment": False, "is_subtotal": False, "values": {"FY2026": 39861.0}},
            {"name": "U.S.", "is_subsegment": False, "is_subtotal": False, "values": {"FY2026": 167746.0}},
            {"name": "China", "is_subsegment": False, "is_subtotal": False, "values": {"FY2026": 82378.0}},
            {"name": "Other countries", "is_subsegment": False, "is_subtotal": False, "values": {"FY2026": 228710.0}},
        ]
        _resolve_competing_geo_partitions(aapl_geos, "FY2026", {"FY2026": 478834.0})
        aapl_by_name = {g["name"]: g for g in aapl_geos}
        self.assertFalse(aapl_by_name["Japan"].get("is_country_breakdown", False))
        self.assertTrue(aapl_by_name["U.S."].get("is_country_breakdown"))
        self.assertTrue(aapl_by_name["China"].get("is_country_breakdown"))
        self.assertTrue(aapl_by_name["Other countries"].get("is_country_breakdown"))

        # 8. Canonical key preserves geographic sub-qualifiers like (U.S.) while still stripping acronyms like (CCB)
        self.assertNotEqual(_canon_match_key("Other (U.S.)"), _canon_match_key("Other"))
        self.assertNotEqual(_canon_match_key("Retail (U.S.)"), _canon_match_key("Retail"))
        self.assertEqual(_canon_match_key("Consumer & Community Banking (CCB)"), _canon_match_key("Consumer & Community Banking"))


if __name__ == "__main__":
    unittest.main()
