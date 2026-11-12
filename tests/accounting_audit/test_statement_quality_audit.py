# -*- coding: utf-8 -*-
"""
Tests unitarios para la auditoría de calidad de estados financieros (Q1-Q5).
"""

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PIPELINE_DIR = PROJECT_ROOT / "pipeline"
for _p in (PROJECT_ROOT, PIPELINE_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import pipeline  # noqa: E402, F401
from pipeline.audit_modules.statement_quality_audit import (  # noqa: E402
    evaluate_statement_quality,
    run_statement_quality_audit,
)


def _clean_fixture() -> dict:
    return {
        "archetype": "STANDARD_CORPORATE",
        "fiscal_years": ["LTM", "FY2025", "FY2024"],
        "sec_filings_index": {"000000-25-000001": {"form": "10-K"}},
        "period_filing_map": {"FY2025": {"accession": "000000-25-000001"}},
        "as_reported_statements": {
            "income_statement": [
                {"label": "Operating Expenses:", "spanish_label": "Gastos Operativos", "orig_tooltip": "Operating Expenses:", "is_abstract": True, "is_total": False},
                {"label": "Revenues", "spanish_label": "Ingresos totales", "orig_tooltip": "Revenues", "concept": "us-gaap_Revenues", "is_abstract": False, "is_total": False},
                {"label": "Cost of revenue", "spanish_label": "Costo de ingresos", "orig_tooltip": "Cost of revenue", "concept": "us-gaap_CostOfRevenue", "is_abstract": False, "is_total": False},
            ],
            "balance_sheet": [
                {"label": "Total assets", "spanish_label": "Total de activos", "orig_tooltip": "Total assets", "concept": "us-gaap_Assets", "is_abstract": False, "is_total": True},
            ],
            "cash_flow_statement": [
                {"label": "Net income", "spanish_label": "Utilidad neta", "orig_tooltip": "Net income", "concept": "us-gaap_NetIncomeLoss", "is_abstract": False, "is_total": False},
            ],
        },
        "resolved_canonical_statements": {
            "balance_sheet": {
                "total_assets": {"LTM": 1000e6, "FY2025": 950e6, "FY2024": 900e6},
                "total_liab_and_equity": {"LTM": 1000e6, "FY2025": 950e6, "FY2024": 900e6},
            }
        },
        "resolved_canonical_lineage": {
            "other_operating_expense": {
                "method": "PLUG_ATTRIBUTION",
                "periods": {
                    "LTM": {"value_usd": 50e6, "explained_sum_usd": 50e6, "residual_unexplained_usd": 0.0},
                },
            }
        },
    }


def _checks_by_id(report: dict) -> dict:
    return {c["check"]: c for c in report["checks"]}


class TestStatementQualityAudit(unittest.TestCase):
    """Cubre los 5 invariantes Q1-Q5 ante escenarios PASS, WARN y ERROR."""

    def test_clean_fixture_passes_all_five_checks(self):
        rep = evaluate_statement_quality(_clean_fixture())
        self.assertEqual(rep["status"], "PASS")
        self.assertEqual(rep["error_count"], 0)
        self.assertEqual(rep["warn_count"], 0)
        self.assertEqual(rep["pass_count"], 5)

    def test_q1_duplicate_asrep_labels_flags_error_and_ignores_abstract(self):
        data = _clean_fixture()
        data["as_reported_statements"]["income_statement"].append(
            {"label": "Other expenses:", "spanish_label": "Gastos Operativos", "orig_tooltip": "Other expenses:", "is_abstract": True, "is_total": False}
        )
        self.assertEqual(_checks_by_id(evaluate_statement_quality(data))["ZERO_DUPLICATE_ASREP_LABELS"]["severity"], "PASS")

        data["as_reported_statements"]["income_statement"].append(
            {"label": "Product revenue", "spanish_label": "Ingresos totales", "orig_tooltip": "Product revenue", "concept": "us-gaap_Sales", "is_abstract": False, "is_total": False}
        )
        q1 = _checks_by_id(evaluate_statement_quality(data))["ZERO_DUPLICATE_ASREP_LABELS"]
        self.assertEqual(q1["severity"], "ERROR")
        self.assertEqual(q1["count"], 1)

    def test_q2_translation_spanglish_leak_flags_error(self):
        data = _clean_fixture()
        data["as_reported_statements"]["income_statement"][1]["spanish_label"] = "Net income attributable to parent"
        q2 = _checks_by_id(evaluate_statement_quality(data))["TRANSLATION_SEMANTIC_INTEGRITY"]
        self.assertEqual(q2["severity"], "ERROR")
        self.assertEqual(q2["samples"][0]["reason"], "SPANGLISH_LEAK")

    def test_q3_balance_mezzanine_parity_error_and_warn(self):
        data = _clean_fixture()
        data["resolved_canonical_statements"]["balance_sheet"]["total_liab_and_equity"]["LTM"] = 850e6
        self.assertEqual(_checks_by_id(evaluate_statement_quality(data))["BALANCE_MEZZANINE_PARITY"]["severity"], "ERROR")

        data_no_res = copy.deepcopy(_clean_fixture())
        data_no_res.pop("resolved_canonical_statements")
        self.assertEqual(_checks_by_id(evaluate_statement_quality(data_no_res))["BALANCE_MEZZANINE_PARITY"]["severity"], "WARN")

    def test_q4_plug_residual_and_q5_false_total_and_runner(self):
        data = _clean_fixture()
        data["resolved_canonical_lineage"]["other_operating_expense"]["periods"]["LTM"]["residual_unexplained_usd"] = 20e6
        data["as_reported_statements"]["cash_flow_statement"].append(
            {"label": "Purchase of total return swaps", "spanish_label": "Compra de swaps", "orig_tooltip": "Purchase of total return swaps", "is_abstract": False, "is_total": True}
        )
        by_id = _checks_by_id(evaluate_statement_quality(data))
        self.assertEqual(by_id["UNEXPLAINED_PLUG_THRESHOLD"]["severity"], "WARN")
        self.assertEqual(by_id["IS_FALSE_TOTAL_AND_PROVENANCE"]["severity"], "ERROR")

        data_warn_prov = _clean_fixture()
        data_warn_prov["sec_filings_index"] = {}
        self.assertEqual(_checks_by_id(evaluate_statement_quality(data_warn_prov))["IS_FALSE_TOTAL_AND_PROVENANCE"]["severity"], "WARN")

        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "financial_statements.json"
            p.write_text(json.dumps(_clean_fixture()), encoding="utf-8")
            checks = run_statement_quality_audit(tmp)
            self.assertEqual(len(checks), 5)
            self.assertTrue(all(c["severity"] == "PASS" for c in checks))


if __name__ == "__main__":
    unittest.main()
