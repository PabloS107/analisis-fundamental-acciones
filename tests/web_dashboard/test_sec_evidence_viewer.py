# -*- coding: utf-8 -*-
"""
Tests para las APIs Click-to-Source de trazabilidad SEC:
- /api/cell-evidence/<ticker>/ (vista estandarizada, as-reported, 404).
- /api/sec-report-proxy/<ticker>/<accession>/<report_file>/ (validaciones 400/404,
  cabecera SAMEORIGIN, <base href>, saneamiento de scripts y resaltado SEC).
"""

import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT_DIR = Path(__file__).resolve().parents[2]
for _p in (ROOT_DIR, ROOT_DIR / "pipeline", ROOT_DIR / "web_dashboard"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import pipeline  # noqa: E402, F401
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "web_dashboard.settings")

import django  # noqa: E402

django.setup()

from django.test import Client  # noqa: E402
from analytics.views import views_sec_viewer  # noqa: E402


class TestSecEvidenceViewerAPIs(unittest.TestCase):
    """Pruebas funcionales y de seguridad para las APIs del SEC Evidence Drawer."""

    def setUp(self):
        self.client = Client()
        views_sec_viewer._SEC_PROXY_CACHE.clear()

    def test_cell_evidence_standardized_and_missing_ticker(self):
        res_ok = self.client.get(
            "/api/cell-evidence/UBER/?stmt=income_statement&metric=other_operating_expense&period=LTM&view=std"
        )
        self.assertEqual(res_ok.status_code, 200)
        data = res_ok.json()
        self.assertEqual(data["ticker"], "UBER")
        self.assertEqual(data["stmt"], "income_statement")
        self.assertEqual(data["metric"], "other_operating_expense")
        self.assertEqual(data["period"], "LTM")
        self.assertIn("filing_links", data)

        res_404 = self.client.get("/api/cell-evidence/ZZZZ99/?stmt=income_statement&metric=revenue&period=LTM")
        self.assertEqual(res_404.status_code, 404)

    def test_cell_evidence_as_reported_exact_concept_lookup(self):
        uber_fs = json.loads((ROOT_DIR / "data" / "processed" / "UBER" / "financial_statements.json").read_text(encoding="utf-8"))
        sample_row = next(
            r for r in uber_fs["as_reported_statements"]["income_statement"]
            if not r.get("is_abstract") and r.get("concept")
        )
        res = self.client.get(
            "/api/cell-evidence/UBER/",
            {
                "stmt": "income_statement",
                "period": uber_fs["fiscal_years"][0],
                "view": "asrep",
                "concept": sample_row["concept"],
                "raw_label": sample_row.get("raw_label") or sample_row["label"],
            },
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn(data["method"], ("SEC_AS_REPORTED", "SEC_EXTENSION_TAG"))
        self.assertEqual(data["highlight_concept"], sample_row["concept"])
        self.assertTrue(data["sources"])
        self.assertEqual(data["sources"][0]["concept"], sample_row["concept"])

    def test_sec_report_proxy_validation_and_html_injection(self):
        self.assertEqual(self.client.get("/api/sec-report-proxy/AAPL/bad-acc/R2.htm/").status_code, 400)
        self.assertEqual(self.client.get("/api/sec-report-proxy/AAPL/0000320193-25-000073/badfile.htm/").status_code, 400)
        self.assertEqual(self.client.get("/api/sec-report-proxy/ZZZZ99/0000320193-25-000073/R2.htm/").status_code, 404)

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.apparent_encoding = "utf-8"
        mock_resp.text = (
            "<html><head><title>R2</title><script src='evil.js'>alert(1)</script></head>"
            "<body><table class='report'><tr>"
            "<td class='pl'><a onclick=\"show('defref_us-gaap_Revenues')\">Revenues</a></td>"
            "<td class='nump'>100</td></tr></table></body></html>"
        )
        with patch("analytics.views.views_sec_viewer.requests.get", return_value=mock_resp) as m_get:
            res = self.client.get(
                "/api/sec-report-proxy/AAPL/0000320193-25-000073/R2.htm/?stmt=income_statement&concept=us-gaap_Revenues&raw_label=Revenues"
            )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.headers.get("X-Frame-Options"), "SAMEORIGIN")
        self.assertTrue(m_get.called)
        body = res.content.decode("utf-8")
        self.assertIn('<base href="https://www.sec.gov/Archives/edgar/data/', body)
        self.assertNotIn("alert(1)", body)
        self.assertIn("agy-sec-highlight", body)
        self.assertIn("us-gaap_Revenues", body)


if __name__ == "__main__":
    unittest.main()
