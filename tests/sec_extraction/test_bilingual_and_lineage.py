# -*- coding: utf-8 -*-
"""
Tests unitarios para traducción SEC sin colisiones, detección de totales reales,
paridad de balance con Mezzanine Equity y linaje/atribución de cajones "Otros".
"""

import json
import sys
import unittest
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PIPELINE_DIR = PROJECT_ROOT / "pipeline"
for _p in (PROJECT_ROOT, PIPELINE_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import pipeline  # noqa: E402, F401
from pipeline.sec_modules.canonical_lineage import build_resolved_canonical_lineage  # noqa: E402
from pipeline.sec_modules.canonical_resolvers import resolve_canonical_balance_sheet  # noqa: E402
from pipeline.sec_modules.financial_bilingual_map import get_spanish_label  # noqa: E402
from pipeline.sec_modules.sec_statement_reconciler import (  # noqa: E402
    _disambiguate_as_reported_labels,
    _is_true_statement_total,
)
from pipeline.sec_modules.sec_segment_extractor import _resolve_segment_hierarchies  # noqa: E402
from pipeline.sec_modules.sec_xbrl_ltm import compute_and_inject_ltm_columns  # noqa: E402


class TestBilingualMapAndTotalGuard(unittest.TestCase):
    """Valida reglas semánticas del traductor bilingüe y guardas de totales/colisiones."""

    def test_compound_clauses_avoid_spanglish_leaks(self):
        cases = (
            ("Net income attributable to Uber Technologies, Inc.", "us-gaap_NetIncomeLoss"),
            ("Cost of revenue, exclusive of depreciation and amortization", "us-gaap_CostOfGoodsAndServicesSold"),
            ("Total stockholders' equity", "us-gaap_StockholdersEquity"),
            ("Revenues", "us-gaap_Revenues"),
        )
        for raw_lbl, concept in cases:
            sp = get_spanish_label(raw_lbl, concept=concept)
            sp_low = sp.lower()
            self.assertTrue(sp and sp != "N/D", f"Traducción vacía para {raw_lbl!r}")
            self.assertNotIn("attributable to", sp_low)
            self.assertNotIn("exclusive of", sp_low)
            self.assertNotIn("stockholders", sp_low)

        cost_excl = get_spanish_label(
            "Cost of revenue, exclusive of depreciation and amortization",
            concept="us-gaap_CostOfGoodsAndServicesSold",
        ).lower()
        self.assertIn("excluyendo", cost_excl)

    def test_true_statement_total_guard_rejects_swap_line(self):
        self.assertFalse(_is_true_statement_total("Purchase of total return swaps", False))
        self.assertFalse(_is_true_statement_total("Other operating expenses", False))
        self.assertTrue(_is_true_statement_total("Total assets", False))
        self.assertTrue(_is_true_statement_total("Operating expenses, total", False))
        self.assertTrue(_is_true_statement_total("Custom total", True))

    def test_disambiguate_as_reported_labels_resolves_cross_and_same_section_collisions(self):
        rows = [
            {
                "label": "Operating Expenses:",
                "spanish_label": "Gastos Operativos",
                "concept": "us-gaap_OperatingExpensesAbstract",
                "is_abstract": True,
                "section_path": "Operating Expenses",
            },
            {
                "label": "Depreciation and amortization",
                "spanish_label": "Depreciación y amortización",
                "concept": "us-gaap_DepreciationDepletionAndAmortization",
                "is_abstract": False,
                "section_path": "Costs and expenses",
            },
            {
                "label": "Depreciation and amortization",
                "spanish_label": "Depreciación y amortización",
                "concept": "uber_DepreciationAndAmortizationOther",
                "is_abstract": False,
                "section_path": "Other income (expense)",
            },
            {
                "label": "Other intangible amortization",
                "spanish_label": "Depreciación y amortización",
                "concept": "us-gaap_AmortizationOfIntangibleAssets",
                "is_abstract": False,
                "section_path": "Costs and expenses",
            },
        ]
        _disambiguate_as_reported_labels(rows, lambda txt, _c: f"[ES] {txt}")
        non_abs = [r["spanish_label"].lower() for r in rows if not r["is_abstract"]]
        self.assertEqual(len(non_abs), len(set(non_abs)), f"Colisiones restantes: {non_abs}")


class TestMezzanineParityAndLineage(unittest.TestCase):
    """Valida Mezzanine Equity en Balance y atribución regional/sectorial en Linaje."""

    def test_mezzanine_equity_restores_balance_sheet_parity(self):
        bs_rows = [
            {"concept": "us-gaap_Assets", "label": "Total assets", "is_abstract": False, "is_total": True, "values": {"FY2025": 1000.0}},
            {"concept": "us-gaap_Liabilities", "label": "Total liabilities", "is_abstract": False, "is_total": True, "values": {"FY2025": 600.0}},
            {"concept": "us-gaap_TemporaryEquityCarryingAmountAttributableToParent", "label": "Redeemable non-controlling interests", "is_abstract": False, "is_total": False, "values": {"FY2025": 120.0}},
            {"concept": "us-gaap_StockholdersEquity", "label": "Total stockholders' equity", "is_abstract": False, "is_total": True, "values": {"FY2025": 280.0}},
        ]
        fs = {
            "archetype": "STANDARD_CORPORATE",
            "canonical_summary": {},
            "as_reported_statements": {"balance_sheet": bs_rows},
            "balance_sheet": {},
            "balance_sheet_detail": {},
        }
        res = resolve_canonical_balance_sheet(fs, ["FY2025"], archetype="STANDARD_CORPORATE")
        self.assertEqual(res["mezzanine_equity"]["FY2025"], 120.0)
        self.assertEqual(res["total_liab_and_equity"]["FY2025"], 1000.0)
        self.assertEqual(res["total_assets"]["FY2025"], 1000.0)

    def test_lineage_plug_attribution_cf_supplemental_stop_and_banking_scope(self):
        periods = ["FY2025"]
        as_rep_cf = [
            {"concept": "us-gaap_NetIncomeLoss", "label": "Net income", "is_abstract": False, "is_total": False, "values": {"FY2025": 100.0}},
            {"concept": "us-gaap_Depreciation", "label": "Depreciation", "is_abstract": False, "is_total": False, "values": {"FY2025": 20.0}},
            {"concept": "us-gaap_CustomSpecialNonCashAdjustment", "label": "Legal settlement reserve", "is_abstract": False, "is_total": False, "values": {"FY2025": 15.0}},
            {"concept": "us-gaap_NetCashProvidedByUsedInOperatingActivities", "label": "Net cash from operating activities", "is_abstract": False, "is_total": True, "values": {"FY2025": 135.0}},
            {"concept": "us-gaap_PaymentsToAcquirePropertyPlantAndEquipment", "label": "Purchases of property and equipment", "is_abstract": False, "is_total": False, "values": {"FY2025": -30.0}},
            {"concept": "us-gaap_NetCashProvidedByUsedInInvestingActivities", "label": "Net cash used in investing activities", "is_abstract": False, "is_total": True, "values": {"FY2025": -30.0}},
            {"concept": "us-gaap_PaymentsOfDividends", "label": "Dividends paid", "is_abstract": False, "is_total": False, "values": {"FY2025": -10.0}},
            {"concept": "us-gaap_NetCashProvidedByUsedInFinancingActivities", "label": "Net cash used in financing activities", "is_abstract": False, "is_total": True, "values": {"FY2025": -10.0}},
            {"concept": "us-gaap_InterestPaidNet", "label": "Cash paid for interest", "is_abstract": False, "is_total": False, "values": {"FY2025": 45.0}, "section_path": "Supplemental cash flow disclosures"},
        ]
        full_dataset = {
            "archetype": "STANDARD_CORPORATE",
            "canonical_summary": {"operating_cash_flow": {"FY2025": 135.0}},
            "as_reported_statements": {"income_statement": [], "balance_sheet": [], "cash_flow_statement": as_rep_cf},
        }
        cf_resolved = {
            "net_income": {"FY2025": 100.0},
            "depreciation_amortization": {"FY2025": 20.0},
            "other_noncash": {"FY2025": 15.0},
            "operating_cash_flow": {"FY2025": 135.0},
            "capex": {"FY2025": -30.0},
            "investing_cash_flow": {"FY2025": -30.0},
            "dividends": {"FY2025": -10.0},
            "financing_cash_flow": {"FY2025": -10.0},
            "other_financing": {"FY2025": 0.0},
        }
        lin = build_resolved_canonical_lineage(full_dataset, {}, {}, cf_resolved, periods)
        noncash_p = lin["other_noncash"]["periods"]["FY2025"]
        self.assertEqual(noncash_p["explained_sum_usd"], 15.0)
        self.assertEqual(noncash_p["residual_unexplained_usd"], 0.0)
        fin_sources = [s["concept"] for s in lin["other_financing"]["periods"]["FY2025"]["sources"]]
        self.assertNotIn("us-gaap_InterestPaidNet", fin_sources)

        jpm_path = PROJECT_ROOT / "data" / "processed" / "JPM" / "financial_statements.json"
        if jpm_path.exists():
            jpm_fs = json.loads(jpm_path.read_text(encoding="utf-8"))
            jpm_periods = (jpm_fs.get("fiscal_years") or [])[:2]
            jpm_lin = build_resolved_canonical_lineage(jpm_fs, {"other_current_assets": {p: 100.0 for p in jpm_periods}}, {}, {}, jpm_periods)
            self.assertNotIn("other_current_assets", jpm_lin)


class TestLtmCashFlowIsolation(unittest.TestCase):
    """Valida que la inyección LTM no clone ni trunque filas retiradas o con etiquetas repetidas."""

    def test_retired_and_colliding_cf_rows_do_not_clone_or_truncate_ltm(self):
        inc_df = pd.DataFrame([{"concept": "us-gaap_Revenues", "label": "Revenues", "FY2025": 1000.0}])
        bal_df = pd.DataFrame([{"concept": "us-gaap_Assets", "label": "Total assets", "FY2025": 5000.0}])
        cf_df = pd.DataFrame([
            {"concept": "us-gaap_PaymentsToAcquirePropertyPlantAndEquipment", "label": "Purchases of property and equipment", "FY2025": None},
            {"concept": "us-gaap_PaymentsToAcquireProductiveAssets", "label": "Purchases of property and equipment and intangible assets", "FY2025": -1343.0},
            {"concept": "us-gaap_ProceedsFromSaleOfEquitySecurities", "label": "Equity securities", "FY2025": None},
            {"concept": "us-gaap_PaymentsToAcquireEquitySecurities", "label": "Equity securities", "FY2025": -62.0},
        ])
        q_inc = pd.DataFrame([{"concept": "us-gaap_Revenues", "label": "Revenues", "YTD 2026-09-30": 800.0, "YTD 2025-09-30": 700.0}])
        q_cf = pd.DataFrame([
            {"concept": "us-gaap_PaymentsToAcquireProductiveAssets", "label": "Purchases of property and equipment and intangible assets", "YTD 2026-09-30": -1215.0, "YTD 2025-09-30": -916.0},
            {"concept": "us-gaap_PaymentsToAcquireEquitySecurities", "label": "Equity securities", "YTD 2026-09-30": -80.0, "YTD 2025-09-30": -50.0},
        ])

        compute_and_inject_ltm_columns(
            inc_df, bal_df, cf_df,
            q_inc, q_cf,
            None, None, None,
            pd.DataFrame(), "FY2025",
        )

        self.assertTrue(pd.isna(cf_df.iloc[0]["LTM"]))
        self.assertEqual(cf_df.iloc[1]["LTM"], -1642.0)
        self.assertTrue(pd.isna(cf_df.iloc[2]["LTM"]))
        self.assertEqual(cf_df.iloc[3]["LTM"], -92.0)

    def test_not_newer_10q_preserves_none_on_retired_rows(self):
        inc_df = pd.DataFrame([
            {"concept": "us-gaap_Revenues", "label": "Revenues", "FY2025": 1000.0},
            {"concept": "us-gaap_RetiredIncItem", "label": "Retired inc item", "FY2025": None},
        ])
        bal_df = pd.DataFrame([
            {"concept": "us-gaap_Assets", "label": "Total assets", "FY2025": 5000.0},
            {"concept": "us-gaap_RetiredBalItem", "label": "Retired bal item", "FY2025": None},
        ])
        cf_df = pd.DataFrame([
            {"concept": "us-gaap_PaymentsToAcquireProductiveAssets", "label": "CapEx", "FY2025": -200.0},
            {"concept": "us-gaap_PaymentsToAcquireIntangibleAssets", "label": "Intangibles", "FY2025": None},
        ])
        q_inc = pd.DataFrame([{"concept": "us-gaap_Revenues", "label": "Revenues", "YTD 2025-09-30": 750.0, "YTD 2024-09-30": 650.0}])
        q_cf = pd.DataFrame([{"concept": "us-gaap_PaymentsToAcquireProductiveAssets", "label": "CapEx", "YTD 2025-09-30": -140.0, "YTD 2024-09-30": -120.0}])
        cf_ttm_df = pd.DataFrame([{"concept": "us-gaap_PaymentsToAcquireIntangibleAssets", "label": "Intangibles", "2025-09-30": 2674.0}])
        facts_df = pd.DataFrame([
            {"concept": "us-gaap:Assets", "fiscal_year": 2025, "fiscal_period": "FY", "period_end": "2025-12-31"},
        ])

        compute_and_inject_ltm_columns(
            inc_df, bal_df, cf_df,
            q_inc, q_cf,
            None, cf_ttm_df, None,
            facts_df, "FY2025",
        )

        self.assertEqual(inc_df.iloc[0]["LTM"], 1000.0)
        self.assertTrue(pd.isna(inc_df.iloc[1]["LTM"]))
        self.assertEqual(bal_df.iloc[0]["LTM"], 5000.0)
        self.assertTrue(pd.isna(bal_df.iloc[1]["LTM"]))
        self.assertEqual(cf_df.iloc[0]["LTM"], -200.0)
        self.assertTrue(pd.isna(cf_df.iloc[1]["LTM"]))

    def test_geo_hierarchy_does_not_subordinate_active_us_to_discontinued_other_countries(self):
        # Caso NVDA: United States activo vs Europe y Other countries discontinuados y menores
        nvda_geo = [
            {"name": "United States", "is_subtotal": False, "is_subsegment": False, "parent": None, "values": {"FY2026": 149617.0, "FY2024": 31533.0}},
            {"name": "Taiwan", "is_subtotal": False, "is_subsegment": False, "parent": None, "values": {"FY2026": 42345.0}},
            {"name": "Other countries", "is_subtotal": False, "is_subsegment": False, "parent": None, "values": {"FY2024": 10245.0}},
            {"name": "Europe", "is_subtotal": False, "is_subsegment": False, "parent": None, "values": {"FY2021": 1118.0}},
        ]
        _resolve_segment_hierarchies([], nvda_geo, "FY2026")
        us_row = next(g for g in nvda_geo if g["name"] == "United States")
        self.assertFalse(us_row["is_subsegment"])
        self.assertIsNone(us_row["parent"])

        # Caso MELI: Brazil/Mexico activos y Other Countries mayor que U.S.
        meli_geo = [
            {"name": "Brazil", "is_subtotal": False, "is_subsegment": False, "parent": None, "values": {"FY2025": 19000.0}},
            {"name": "Mexico", "is_subtotal": False, "is_subsegment": False, "parent": None, "values": {"FY2025": 7500.0}},
            {"name": "Other Countries", "is_subtotal": False, "is_subsegment": False, "parent": None, "values": {"FY2025": 1600.0}},
            {"name": "U.S.", "is_subtotal": False, "is_subsegment": False, "parent": None, "values": {"FY2025": 70.0}},
        ]
        _resolve_segment_hierarchies([], meli_geo, "FY2025")
        meli_us = next(g for g in meli_geo if g["name"] == "U.S.")
        self.assertTrue(meli_us["is_subsegment"])
        self.assertEqual(meli_us["parent"], "Other Countries")


if __name__ == "__main__":
    unittest.main()
