"""
test_period_integrity.py - Pruebas de las invariantes de período, vigencia de verificación,
estado SINGLE_SOURCE y eliminación del LTM inventado (Plan P0).
"""
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

from pipeline.period_integrity import (  # noqa: E402
    check_period_integrity,
    check_verification_freshness,
    file_fingerprint,
)
from pipeline.data_verifier import reconcile_item, reconcile_eps_item, reconcile_shares_item  # noqa: E402
from pipeline.sec_modules.sec_freshness import get_local_sec_metadata  # noqa: E402

PROCESSED = PROJECT_ROOT / "data" / "processed"


def _fs(meta=None, rows=None, fys=("LTM", "FY2025", "FY2024")):
    data = {
        "fiscal_years": list(fys),
        "as_reported_statements": {"income_statement": rows or [], "balance_sheet": [], "cash_flow_statement": []},
    }
    if meta is not None:
        data["sec_metadata"] = meta
    return data


def _meta(**kw):
    base = {
        "ltm_period": "FY2025", "ltm_period_end": "2025-09-27", "latest_periodic_form": "10-K",
        "latest_periodic_date": "2025-11-01", "latest_periodic_accession": "0000000000-25-000001",
        "extraction_timestamp": "2025-11-05T10:00:00",
    }
    base.update(kw)
    return base


def _by_check(findings):
    return {f["check"]: f for f in findings}


class TestPeriodInvariants(unittest.TestCase):
    def test_clean_metadata_all_pass(self):
        rows = [{"label": "Rev", "concept": "us-gaap_Revenues", "values": {"LTM": 100.0, "FY2025": 100.0}}]
        res = _by_check(check_period_integrity(_fs(_meta(), rows)))
        self.assertTrue(all(f["severity"] == "PASS" for f in res.values()), res)

    def test_missing_metadata_is_nd_warning(self):
        res = check_period_integrity(_fs(None))
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["severity"], "WARN")

    def test_period_after_filing_is_error(self):
        res = _by_check(check_period_integrity(_fs(_meta(ltm_period_end="2025-12-31"))))
        self.assertEqual(res["PERIODO_NO_POSTERIOR"]["severity"], "ERROR")

    def test_period_in_future_vs_extraction_is_error(self):
        res = _by_check(check_period_integrity(_fs(_meta(ltm_period_end="2025-12-31", latest_periodic_date="2026-01-10"))))
        self.assertEqual(res["PERIODO_NO_FUTURO"]["severity"], "ERROR")

    def test_ltm_differs_from_fy_when_annual_source_is_error(self):
        rows = [{"label": "Products", "concept": "c", "values": {"LTM": 120.0, "FY2025": 100.0}}]
        res = _by_check(check_period_integrity(_fs(_meta(), rows)))
        self.assertEqual(res["LTM_IGUAL_FY"]["severity"], "ERROR")
        self.assertEqual(res["LTM_IGUAL_FY"]["count"], 1)

    def test_ltm_tolerance_and_abstract_rows(self):
        rows = [
            {"label": "A", "concept": "c", "values": {"LTM": 100.05, "FY2025": 100.0}},
            {"label": "Abs", "concept": "d", "is_abstract": True, "values": {"LTM": 1.0, "FY2025": 9.0}},
        ]
        res = _by_check(check_period_integrity(_fs(_meta(), rows)))
        self.assertEqual(res["LTM_IGUAL_FY"]["severity"], "PASS")

    def test_ltm_check_not_applicable_for_quarterly_source(self):
        rows = [{"label": "Rev", "concept": "c", "values": {"LTM": 150.0, "FY2025": 100.0}}]
        meta = _meta(ltm_period="Q2 2026", latest_periodic_form="10-Q", ltm_period_end="2026-06-30", latest_periodic_date="2026-08-01",
                     extraction_timestamp="2026-08-05T00:00:00")
        res = _by_check(check_period_integrity(_fs(_meta(**meta), rows)))
        self.assertEqual(res["LTM_IGUAL_FY"]["severity"], "PASS")


class TestVerificationFreshness(unittest.TestCase):
    def _write(self, d, report):
        (d / "financial_statements.json").write_text(json.dumps({"fiscal_years": ["FY2025"]}), encoding="utf-8")
        (d / "cross_verification_report.json").write_text(json.dumps(report), encoding="utf-8")

    def test_matching_fingerprint_is_current(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            self._write(d, {})
            report = {"source_fingerprint": file_fingerprint(d / "financial_statements.json")}
            (d / "cross_verification_report.json").write_text(json.dumps(report), encoding="utf-8")
            self.assertEqual(check_verification_freshness(d)["state"], "CURRENT")

    def test_changed_statements_make_report_stale(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            self._write(d, {"source_fingerprint": "deadbeef"})
            res = check_verification_freshness(d)
            self.assertEqual(res["state"], "STALE")
            self.assertEqual(res["severity"], "WARN")

    def test_legacy_report_older_than_extraction_is_stale(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            self._write(d, {"verification_timestamp": "2026-09-27T10:00:00"})
            fs = {"fiscal_years": ["FY2025"], "extraction_timestamp": "2026-11-06T10:00:00"}
            (d / "financial_statements.json").write_text(json.dumps(fs), encoding="utf-8")
            self.assertEqual(check_verification_freshness(d)["state"], "STALE")

    def test_missing_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "financial_statements.json").write_text("{}", encoding="utf-8")
            self.assertEqual(check_verification_freshness(d)["state"], "MISSING")


class TestSingleSourceStatus(unittest.TestCase):
    def test_no_second_source_is_single_source(self):
        self.assertEqual(reconcile_item("Rev", "FY2025", 100.0, None, None)["status"], "SINGLE_SOURCE")
        self.assertEqual(reconcile_item("Rev", "FY2025", 100.0, None, 100.0)["status"], "SINGLE_SOURCE")
        self.assertEqual(reconcile_eps_item("EPS", "FY2025", 1.0, 1.0, 1.0, None)["status"], "SINGLE_SOURCE")
        self.assertEqual(reconcile_shares_item("Sh", "FY2025", 1e9, 1e9, 1.0, None)["status"], "SINGLE_SOURCE")

    def test_with_sec_facts_still_exact_or_flagged(self):
        self.assertEqual(reconcile_item("Rev", "FY2025", 100.0, 100.0)["status"], "EXACT_MATCH")
        self.assertEqual(reconcile_item("Rev", "FY2025", 100.0, 150.0)["status"], "FLAGGED")
        self.assertEqual(reconcile_item("Rev", "FY2025", None, 150.0)["status"], "INCOMPLETE")


class TestNoInventedLtmPeriod(unittest.TestCase):
    def test_legacy_file_without_sec_metadata_yields_nd(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            fs = {"fiscal_years": ["LTM", "FY2025"], "extraction_timestamp": "2026-11-06T10:00:00"}
            (d / "financial_statements.json").write_text(json.dumps(fs), encoding="utf-8")
            meta = get_local_sec_metadata("ZZZ", processed_dir=d)
            self.assertEqual(meta["ltm_period"], "N/D")
            self.assertTrue(meta["is_fallback"])
            self.assertIsNone(meta["latest_periodic_form"])


@unittest.skipUnless((PROCESSED / "AAPL" / "financial_statements.json").exists(), "sin datos procesados")
class TestRealDatasets(unittest.TestCase):
    def _run(self, ticker):
        fs = json.loads((PROCESSED / ticker / "financial_statements.json").read_text(encoding="utf-8"))
        return _by_check(check_period_integrity(fs))

    def test_aapl_ltm_equals_fy_after_annual_sync(self):
        self.assertEqual(self._run("AAPL")["LTM_IGUAL_FY"]["severity"], "PASS")

    def test_nu_period_integrity_pass_after_6k_filter(self):
        res = self._run("NU")
        self.assertEqual(res["PERIODO_NO_POSTERIOR"]["severity"], "PASS")
        self.assertEqual(res["PERIODO_NO_FUTURO"]["severity"], "PASS")
        self.assertFalse([c for c, f in res.items() if f["severity"] == "ERROR"], res)

    def test_control_company_deck_has_no_period_errors(self):
        res = self._run("DECK")
        self.assertFalse([c for c, f in res.items() if f["severity"] == "ERROR"], res)


if __name__ == "__main__":
    unittest.main()
