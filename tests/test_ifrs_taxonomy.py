"""
tests/test_ifrs_taxonomy.py - Suite de pruebas para soporte de normas internacionales (IFRS / Formularios 20-F y 6-K).
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

# Asegurar importación de scripts del skill
SCRIPTS_DIR = Path(__file__).resolve().parents[1] / ".agents" / "skills" / "fundamental-data-extractor" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from sec_extractor import (
    XBRL_TAXONOMY_MAP,
    extract_canonical_summary
)
from data_verifier import (
    extract_fact_annual_series,
    PEER_CIK_CATALOG
)
from governance_insider_analyzer import (
    check_is_foreign_private_issuer,
    scan_6k_filings
)


class TestIFRSTaxonomyMap(unittest.TestCase):
    """Verifica la integridad de la taxonomía unificada US-GAAP e IFRS."""

    def test_taxonomy_keys_exist(self):
        expected_keys = [
            "revenue", "cost_of_goods_sold", "gross_profit", "operating_income",
            "net_income", "operating_cash_flow", "capital_expenditures", "total_assets",
            "stockholders_equity", "short_term_debt", "long_term_debt",
            "cash_and_equivalents", "shares_diluted", "eps_diluted"
        ]
        for k in expected_keys:
            self.assertIn(k, XBRL_TAXONOMY_MAP, f"Falta clave canónica {k} en XBRL_TAXONOMY_MAP")
            self.assertTrue(len(XBRL_TAXONOMY_MAP[k]) > 0, f"Lista vacía para {k}")

    def test_ifrs_specific_concepts(self):
        """Verifica que conceptos XBRL específicos de IFRS estén presentes en las listas correspondientes."""
        self.assertIn("RevenueFromContractsWithCustomers", XBRL_TAXONOMY_MAP["revenue"])
        self.assertIn("CostOfSales", XBRL_TAXONOMY_MAP["cost_of_goods_sold"])
        self.assertIn("ProfitLossFromOperatingActivities", XBRL_TAXONOMY_MAP["operating_income"])
        self.assertIn("ProfitLoss", XBRL_TAXONOMY_MAP["net_income"])
        self.assertIn("CashFlowsFromUsedInOperatingActivities", XBRL_TAXONOMY_MAP["operating_cash_flow"])
        self.assertIn("PurchaseOfPropertyPlantAndEquipment", XBRL_TAXONOMY_MAP["capital_expenditures"])
        self.assertIn("Equity", XBRL_TAXONOMY_MAP["stockholders_equity"])
        self.assertIn("DilutedEarningsLossPerShare", XBRL_TAXONOMY_MAP["eps_diluted"])


class TestIFRSExtraction(unittest.TestCase):
    """Verifica la extracción de estados financieros con taxonomía IFRS y formularios 20-F."""

    def setUp(self):
        # Mock de estado financiero con conceptos IFRS indexados por concepto
        self.inc_data = {
            "Revenue": {
                "label": "Revenue",
                "standard_concept": None,
                "values": {"FY2024": 2200000000.0, "FY2023": 1700000000.0}
            },
            "CostOfSales": {
                "label": "Cost of Sales",
                "standard_concept": None,
                "values": {"FY2024": 880000000.0, "FY2023": 700000000.0}
            },
            "GrossProfit": {
                "label": "Gross Profit",
                "standard_concept": None,
                "values": {"FY2024": 1320000000.0, "FY2023": 1000000000.0}
            },
            "ProfitLossFromOperatingActivities": {
                "label": "Operating Profit",
                "standard_concept": None,
                "values": {"FY2024": 350000000.0, "FY2023": 240000000.0}
            },
            "ProfitLoss": {
                "label": "Net Profit",
                "standard_concept": None,
                "values": {"FY2024": 280000000.0, "FY2023": 190000000.0}
            },
            "DilutedEarningsLossPerShare": {
                "label": "Diluted EPS",
                "standard_concept": None,
                "values": {"FY2024": 0.90, "FY2023": 0.62}
            }
        }

        self.bal_data = {
            "Assets": {
                "label": "Total Assets",
                "standard_concept": None,
                "values": {"FY2024": 3000000000.0, "FY2023": 2400000000.0}
            },
            "Equity": {
                "label": "Total Equity",
                "standard_concept": None,
                "values": {"FY2024": 1800000000.0, "FY2023": 1400000000.0}
            },
            "CashAndCashEquivalents": {
                "label": "Cash and Cash Equivalents",
                "standard_concept": None,
                "values": {"FY2024": 500000000.0, "FY2023": 400000000.0}
            },
            "NoncurrentBorrowings": {
                "label": "Noncurrent Borrowings",
                "standard_concept": None,
                "values": {"FY2024": 200000000.0, "FY2023": 250000000.0}
            }
        }

        self.cf_data = {
            "CashFlowsFromUsedInOperatingActivities": {
                "label": "Cash Flows from Operating Activities",
                "standard_concept": None,
                "values": {"FY2024": 420000000.0, "FY2023": 310000000.0}
            },
            "PurchaseOfPropertyPlantAndEquipment": {
                "label": "Purchase of PP&E",
                "standard_concept": None,
                "values": {"FY2024": 90000000.0, "FY2023": 75000000.0}
            }
        }

    def test_extract_canonical_summary_ifrs(self):
        """Verifica que extract_canonical_summary extrae correctamente los conceptos IFRS."""
        periods = ["FY2024", "FY2023"]
        summary, ratios = extract_canonical_summary(self.inc_data, self.bal_data, self.cf_data, periods)
        
        self.assertEqual(summary["revenue"]["FY2024"], 2200000000.0)
        self.assertEqual(summary["cost_of_goods_sold"]["FY2024"], 880000000.0)
        self.assertEqual(summary["gross_profit"]["FY2024"], 1320000000.0)
        self.assertEqual(summary["operating_income"]["FY2024"], 350000000.0)
        self.assertEqual(summary["net_income"]["FY2024"], 280000000.0)
        self.assertEqual(summary["eps_diluted"]["FY2024"], 0.90)
        
        self.assertEqual(summary["total_assets"]["FY2024"], 3000000000.0)
        self.assertEqual(summary["stockholders_equity"]["FY2024"], 1800000000.0)
        self.assertEqual(summary["cash_and_equivalents"]["FY2024"], 500000000.0)
        self.assertEqual(summary["total_debt"]["FY2024"], 200000000.0)
        
        self.assertEqual(summary["cash_from_operations"]["FY2024"], 420000000.0)
        self.assertEqual(summary["capital_expenditures"]["FY2024"], 90000000.0)
        self.assertEqual(summary["free_cash_flow"]["FY2024"], 330000000.0)


class TestCompanyFactsIFRS(unittest.TestCase):
    """Verifica que el verifier de facts soporte payloads IFRS de la SEC."""

    def test_extract_fact_annual_series_ifrs_eur(self):
        """Verifica extracción de hechos SEC almacenados bajo ifrs-full con unidad EUR y formulario 20-F."""
        mock_facts_payload = {
            "ifrs-full": {
                "Revenue": {
                    "label": "Revenue",
                    "units": {
                        "EUR": [
                            {
                                "end": "2023-12-31",
                                "val": 27559000000,
                                "fy": 2023,
                                "fp": "FY",
                                "form": "20-F"
                            },
                            {
                                "end": "2024-12-31",
                                "val": 28260000000,
                                "fy": 2024,
                                "fp": "FY",
                                "form": "20-F"
                            }
                        ]
                    }
                }
            }
        }
        
        series = extract_fact_annual_series(mock_facts_payload, ["Revenue"], is_flow=True)
        self.assertIn("FY2023", series)
        self.assertIn("FY2024", series)
        self.assertEqual(series["FY2023"], 27559000000)
        self.assertEqual(series["FY2024"], 28260000000)

    def test_peer_cik_catalog_foreign_peers(self):
        """Verifica que empresas internacionales clave estén en PEER_CIK_CATALOG."""
        self.assertIn("ONON", PEER_CIK_CATALOG)
        self.assertIn("ASML", PEER_CIK_CATALOG)
        self.assertIn("TSM", PEER_CIK_CATALOG)
        self.assertIn("BABA", PEER_CIK_CATALOG)
        self.assertEqual(PEER_CIK_CATALOG["ONON"], "0001858985")
        self.assertEqual(PEER_CIK_CATALOG["ASML"], "0000937966")


class TestGovernanceFPIDetection(unittest.TestCase):
    """Verifica detección de Foreign Private Issuer (FPI) en gobernanza."""

    def test_fpi_detection(self):
        mock_company = MagicMock()
        mock_company.get_filings.side_effect = lambda form: ["20-F filing"] if form == "20-F" else []
        
        is_fpi = check_is_foreign_private_issuer(mock_company)
        self.assertTrue(is_fpi)

    def test_scan_6k_filings(self):
        mock_company = MagicMock()
        mock_f1 = MagicMock()
        mock_f1.filing_date = "2024-05-15"
        mock_f1.accession_number = "0001858985-24-000010"
        mock_f1.description = "Q1 2024 Financial Results Announcement"
        mock_company.get_filings.return_value = [mock_f1]
        
        results = scan_6k_filings(mock_company, max_filings=5)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["filing_date"], "2024-05-15")
        self.assertEqual(results[0]["description"], "Q1 2024 Financial Results Announcement")


if __name__ == "__main__":
    unittest.main()
