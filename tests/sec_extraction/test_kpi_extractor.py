"""
test_kpi_extractor.py - Suite de pruebas unitarias para kpi_extractor.py.
Valida la normalización de métricas Non-GAAP y KPIs operativos por arquetipo,
así como la preservación y reconciliación con financial_statements.json.
"""

import sys
import unittest
import tempfile
import json
from pathlib import Path
from unittest.mock import patch

# Asegurar path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
PIPELINE_DIR = PROJECT_ROOT / "pipeline"
for _p in (PROJECT_ROOT, PIPELINE_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import pipeline  # noqa: E402, F401

from kpi_extractor import (
    _score_pdf_recency,
    normalize_banking_kpis,
    normalize_platform_kpis,
    normalize_corporate_kpis,
    build_comparisons_block,
    extract_operational_kpis
)


class TestKpiExtractor(unittest.TestCase):

    def test_normalize_banking_kpis(self):
        sample_text = """
        Operating Highlights:
        - Customer growth: reaching a total of 139 million customers globally.
        - ARPAC reached approximately $17.1 in Q2'26.
        - Efficiency Ratio increased to 19.5% in Q2'26.
        - Leading indicator 15-90 NPL ratio improved to 4.8%.
        - 90+ NPLs increased to 6.9%.
        - ROE closed the quarter at 33%.
        - Total deposits reached $45.3 billion. Brazil closed at $36.4 billion, Mexico at $5.7 billion, Colombia at $3.3 billion.
        - Nu reached almost 118 million customers in Brazil.
        """
        sec_data = {
            "source_doc": "nupr2q26_6k.htm",
            "text": sample_text,
            "lines": [l.strip() for l in sample_text.splitlines() if l.strip()]
        }
        res = normalize_banking_kpis(sec_data, None, {})
        
        self.assertEqual(res.get("archetype"), "FINANCIAL_BANKING")
        self.assertEqual(res.get("return_on_equity_reported"), 33.0)
        self.assertEqual(res.get("efficiency_ratio_pct"), 19.5)
        self.assertEqual(res.get("npl_15_90_pct"), 4.8)
        self.assertEqual(res.get("npl_90_plus_pct"), 6.9)
        self.assertEqual(res.get("monthly_arpac_usd"), 17.1)
        self.assertEqual(res.get("total_customers_m"), 139.0)
        
        deposits = res.get("deposits_by_country_bn", {})
        self.assertEqual(deposits.get("Brazil"), 36.4)
        self.assertEqual(deposits.get("Mexico"), 5.7)
        self.assertEqual(deposits.get("Colombia"), 3.3)
        self.assertEqual(deposits.get("Total_Latam"), 45.3)

    def test_normalize_platform_kpis(self):
        sample_text = """
        Total Payment Volume of $101 billion, up 56% YoY.
        Gross Merchandise Volume of $21.9 billion, up 44% YoY.
        89 million unique active buyers.
        795 million items sold.
        88 million monthly active users in fintech.
        Credit portfolio reached $16.4 billion.
        NIMAL reached 20.7%.
        15-90 NPL was 7.0%.
        90+ NPL was 18.7%.
        """
        sec_data = {
            "source_doc": "meli-20260805xex991.htm",
            "text": sample_text,
            "lines": [l.strip() for l in sample_text.splitlines() if l.strip()]
        }
        base_dict = {
            "marketplace_kpis": {"gmv_three_months_usd_m": 21926.0},
            "fintech_kpis": {"tpv_total_usd_m": 100952.0}
        }
        res = normalize_platform_kpis(sec_data, None, base_dict)
        
        self.assertEqual(res.get("archetype"), "PLATFORM_ECOSYSTEM")
        # Precisión exacta preservada
        self.assertEqual(res["marketplace_kpis"].get("gmv_three_months_usd_m"), 21926.0)
        self.assertEqual(res["marketplace_kpis"].get("unique_active_buyers_m"), 89.0)
        self.assertEqual(res["marketplace_kpis"].get("items_sold_three_months_m"), 795.0)
        self.assertEqual(res["fintech_kpis"].get("tpv_total_usd_m"), 100952.0)
        self.assertEqual(res["fintech_kpis"].get("fintech_mau_m"), 88.0)
        self.assertEqual(res["credit_portfolio_kpis"].get("credit_portfolio_usd_bn"), 16.4)
        self.assertEqual(res["credit_portfolio_kpis"].get("nimal_pct"), 20.7)

    def test_normalize_corporate_kpis(self):
        sample_lines = [
            "HOKA® brand net sales increased 7.7% to $703.5 million compared to $653.1 million.",
            "UGG® brand net sales increased 4.9% to $278.0 million compared to $265.1 million.",
            "Other brands net sales decreased 18.1% to $37.9 million.",
            "Wholesale net sales increased 2.2% to $666.7 million compared to $652.4 million.",
            "Direct-to-Consumer (DTC) net sales increased 13.0% to $352.8 million.",
            "Domestic net sales increased 3.2% to $517.4 million.",
            "International net sales increased 8.4% to $502.1 million.",
            "Gross margin was 56.4% compared to 55.8%.",
            "Diluted earnings per share was $0.94 compared to $0.93.",
            "Income from operations was $155,301 thousand.",
            "Company repurchased approximately 3.3 million shares of its common stock for a total of $338.2 million.",
            "Company had approximately $4.7 billion remaining under its stock repurchase authorization."
        ]
        sec_data = {
            "source_doc": "deckex991.htm",
            "text": "\n".join(sample_lines),
            "lines": sample_lines
        }
        res = normalize_corporate_kpis(sec_data, None, {})
        
        self.assertEqual(res.get("archetype"), "STANDARD_CORPORATE")
        brands = res.get("brand_segmentation", {})
        self.assertEqual(brands.get("HOKA", {}).get("revenue_usd_m"), 703.5)
        self.assertEqual(brands.get("HOKA", {}).get("growth_yoy_pct"), 7.7)
        self.assertEqual(brands.get("UGG", {}).get("revenue_usd_m"), 278.0)
        
        channels = res.get("channel_breakdown", {})
        self.assertEqual(channels.get("Wholesale", {}).get("revenue_usd_m"), 666.7)
        self.assertEqual(channels.get("Direct-to-Consumer (DTC)", {}).get("revenue_usd_m"), 352.8)
        
        geos = res.get("geographic_breakdown", {})
        self.assertEqual(geos.get("Domestic", {}).get("revenue_usd_m"), 517.4)
        self.assertEqual(geos.get("International", {}).get("revenue_usd_m"), 502.1)
        
        ops = res.get("operational_kpis", {})
        self.assertEqual(ops.get("gross_margin_pct"), 56.4)
        self.assertEqual(ops.get("diluted_eps"), 0.94)
        self.assertEqual(ops.get("operating_income_usd_m"), 155.3)
        self.assertEqual(ops.get("share_repurchase_shares_m"), 3.3)
        self.assertEqual(ops.get("share_repurchase_usd_m"), 338.2)
        self.assertEqual(ops.get("remaining_authorization_usd_bn"), 4.7)

    def test_build_comparisons_block(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            fs_data = {
                "fiscal_years": ["FY2025", "FY2024"],
                "canonical_summary": {
                    "total_assets": {"FY2025": 100000000.0, "FY2024": 90000000.0},
                    "stockholders_equity": {"FY2025": 50000000.0, "FY2024": 45000000.0},
                    "cash_and_equivalents": {"FY2025": 20000000.0, "FY2024": 15000000.0}
                }
            }
            with open(tmp_path / "financial_statements.json", "w", encoding="utf-8") as f:
                json.dump(fs_data, f)

            comps = build_comparisons_block("TEST", tmp_path)
            self.assertIn("total_assets", comps)
            self.assertEqual(comps["total_assets"]["sec_value"], 100000000.0)
            self.assertEqual(comps["total_assets"]["status"], "MATCH_EXACTO")
            self.assertEqual(comps["stockholders_equity"]["sec_value"], 50000000.0)
            self.assertEqual(comps["cash_and_equivalents"]["sec_value"], 20000000.0)

    def test_banking_kpis_no_fake_defaults_when_missing(self):
        """Regla 6: Si el texto bancario no reporta métricas, deben quedar en None y nunca con defaults de Nubank."""
        sec_data = {"source_doc": "jpm_ex991.htm", "text": "Quarterly operating summary.", "lines": ["Quarterly operating summary."]}
        res = normalize_banking_kpis(sec_data, None, {})
        self.assertIsNone(res.get("total_customers_m"))
        self.assertIsNone(res.get("monthly_cost_to_serve_usd"))
        self.assertIsNone(res.get("monthly_arpac_usd"))
        self.assertIsNone(res.get("efficiency_ratio_pct"))
        self.assertIsNone(res.get("provision_coverage_pct"))
        self.assertEqual(res.get("deposits_by_country_bn"), {})

    def test_build_comparisons_block_marks_missing_as_unavailable(self):
        """Regla 6: Campos ausentes en financial_statements.json deben reportar None y DATO_NO_DISPONIBLE."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            fs_data = {
                "fiscal_years": ["FY2025"],
                "canonical_summary": {"total_assets": {"FY2025": 1000.0}},
            }
            with open(tmp_path / "financial_statements.json", "w", encoding="utf-8") as f:
                json.dump(fs_data, f)

            comps = build_comparisons_block("TEST", tmp_path)
            self.assertEqual(comps["total_assets"]["status"], "MATCH_EXACTO")
            self.assertIsNone(comps["stockholders_equity"]["sec_value"])
            self.assertEqual(comps["stockholders_equity"]["status"], "DATO_NO_DISPONIBLE")
            self.assertIsNone(comps["cash_and_equivalents"]["sec_value"])
            self.assertEqual(comps["cash_and_equivalents"]["status"], "DATO_NO_DISPONIBLE")

    def test_score_pdf_recency_dynamic_years(self):
        """La puntuación de recencia de PDFs debe ordenar dinámicamente años futuros y trimestres."""
        self.assertGreater(_score_pdf_recency("Q4 2029 Presentation.pdf"), _score_pdf_recency("Q4 2028 Presentation.pdf"))
        self.assertGreater(_score_pdf_recency("Q4 2028 Presentation.pdf"), _score_pdf_recency("Q4 2026 Presentation.pdf"))
        self.assertGreater(_score_pdf_recency("Q3 2027 Deck.pdf"), _score_pdf_recency("Q1 2027 Deck.pdf"))
        self.assertGreater(_score_pdf_recency("Q1 2028 Deck.pdf"), _score_pdf_recency("Q4 2027 Deck.pdf"))

    def test_extract_operational_kpis_uses_normalize_archetype_ssot(self):
        """extract_operational_kpis normaliza alias heredados via SSOT normalize_archetype."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            drive_dir = tmp_path / "drive"
            drive_dir.mkdir()
            (tmp_path / "financial_statements.json").write_text(
                json.dumps({"fiscal_years": ["FY2025"], "canonical_summary": {}}),
                encoding="utf-8",
            )
            with patch("kpi_extractor.extract_from_sec_ex99", return_value=None):
                res = extract_operational_kpis(
                    "MOCK",
                    archetype="BANKING",
                    output_dir=tmp_path,
                    custom_drive_path=drive_dir,
                )
            self.assertEqual(res.get("archetype"), "FINANCIAL_BANKING")


if __name__ == "__main__":
    unittest.main()
