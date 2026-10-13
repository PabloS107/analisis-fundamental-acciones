"""
tests/test_ifrs_taxonomy.py - Suite de pruebas para soporte de normas internacionales (IFRS / Formularios 20-F y 6-K).
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

# Asegurar importación de scripts del skill
SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "pipeline"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from sec_extractor import (
    XBRL_TAXONOMY_MAP,
    BANKING_TAXONOMY_MAP,
    extract_canonical_summary,
    detect_company_archetype,
    is_banking_or_financial,
    detect_table_scale_factor,
    detect_global_doc_scale,
    get_preceding_html_context
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


class TestArchetypeDetection(unittest.TestCase):
    """Verifica la detección dinámica e invariante de escala de los 3 arquetipos de industria."""

    def test_standard_corporate_detection(self):
        # Industrial / Tecnología pura sin conceptos bancarios
        arch_aapl = detect_company_archetype(sic_code=3571, profile_data={"industry": "Consumer Electronics"})
        self.assertEqual(arch_aapl, "STANDARD_CORPORATE")
        self.assertFalse(is_banking_or_financial(sic_code=3571))

        arch_deck = detect_company_archetype(sic_code=3021, profile_data={"industry": "Footwear Manufacturing"})
        self.assertEqual(arch_deck, "STANDARD_CORPORATE")
        self.assertFalse(is_banking_or_financial(sic_code=3021))

    def test_financial_banking_detection(self):
        # Bancos comerciales y de inversión (División H: 6000-6199)
        arch_nu = detect_company_archetype(sic_code=6199, profile_data={"industry": "Digital Financial Services / Neobanks"})
        self.assertEqual(arch_nu, "FINANCIAL_BANKING")
        self.assertTrue(is_banking_or_financial(sic_code=6199))

        # Detección por huella XBRL pura (depósitos de clientes sin inventario ni COGS comercial)
        concepts = ["depositsfromcustomers", "interestincomeoperating", "expectedcreditloss"]
        arch_xbrl = detect_company_archetype(detected_concepts=concepts)
        self.assertEqual(arch_xbrl, "FINANCIAL_BANKING")
        self.assertTrue(is_banking_or_financial(detected_concepts=concepts))

    def test_platform_ecosystem_detection(self):
        # Ecosistema híbrido comercio + fintech (ej. SIC 7389 con retail marketplace y crédito)
        prof_meli = {
            "sic_code": 7389,
            "industry": "E-Commerce Marketplaces & Platform Services / FinTech",
            "business_model": "PLATFORM_ECOSYSTEM"
        }
        concepts_hybrid = [
            "CostOfGoodsAndServicesSold", "RevenueFromContractWithCustomerExcludingAssessedTax",
            "us-gaap_NotesAndLoansReceivableNetCurrent", "us-gaap_ProvisionForDoubtfulAccounts"
        ]
        arch_meli = detect_company_archetype(sic_code=7389, profile_data=prof_meli, detected_concepts=concepts_hybrid)
        self.assertEqual(arch_meli, "PLATFORM_ECOSYSTEM")
        # Un ecosistema híbrido NO debe tratarse como un banco puro
        self.assertFalse(is_banking_or_financial(profile_data=prof_meli, detected_concepts=concepts_hybrid))


class TestBankingCanonicalAccounting(unittest.TestCase):
    """Verifica el cumplimiento estricto de las reglas contables de banca en extract_canonical_summary."""

    def setUp(self):
        self.inc_data = {
            "NetInterestIncome": {
                "label": "Net Interest Income",
                "standard_concept": None,
                "values": {"FY2024": 1500000000.0}
            },
            "FeeAndCommissionIncome": {
                "label": "Non Interest Income",
                "standard_concept": None,
                "values": {"FY2024": 500000000.0}
            },
            "ExpectedCreditLoss": {
                "label": "Credit Loss Allowance",
                "standard_concept": None,
                "values": {"FY2024": 300000000.0}
            },
            "OperatingExpense": {
                "label": "Operating Expenses",
                "standard_concept": None,
                "values": {"FY2024": 700000000.0}
            },
            "OperatingIncomeLoss": {
                "label": "Operating Profit",
                "standard_concept": None,
                "values": {"FY2024": 1000000000.0}
            },
            "NetIncomeLoss": {
                "label": "Net Income",
                "standard_concept": None,
                "values": {"FY2024": 800000000.0}
            }
        }
        self.bal_data = {
            "Assets": {
                "label": "Total Assets",
                "standard_concept": None,
                "values": {"FY2024": 20000000000.0}
            },
            "Equity": {
                "label": "Stockholders Equity",
                "standard_concept": None,
                "values": {"FY2024": 3000000000.0}
            },
            "DepositsFromCustomers": {
                "label": "Total Deposits",
                "standard_concept": None,
                "values": {"FY2024": 15000000000.0}
            },
            "TotalLoansAndAdvancesToCustomers": {
                "label": "Net Loans",
                "standard_concept": None,
                "values": {"FY2024": 12000000000.0}
            }
        }
        self.cf_data = {
            "CashFlowsFromUsedInOperatingActivities": {
                "label": "Cash from Operations",
                "standard_concept": None,
                "values": {"FY2024": 2500000000.0}
            },
            "PurchaseOfPropertyPlantAndEquipment": {
                "label": "CapEx",
                "standard_concept": None,
                "values": {"FY2024": 50000000.0}
            }
        }

    def test_banking_eliminates_artificial_gross_profit_and_fcf(self):
        """Verifica que para entidades bancarias Gross Profit, COGS y FCF sean estrictamente None."""
        summary, ratios = extract_canonical_summary(
            self.inc_data, self.bal_data, self.cf_data, ["FY2024"],
            archetype="FINANCIAL_BANKING"
        )
        # Regla 1: Gross Profit y COGS deben ser None
        self.assertIsNone(summary["gross_profit"]["FY2024"])
        self.assertIsNone(summary["cost_of_goods_sold"]["FY2024"])
        self.assertIsNone(ratios["gross_margin_pct"]["FY2024"])

        # Regla 2: FCF convencional debe ser None para bancos
        self.assertIsNone(summary["free_cash_flow"]["FY2024"])
        self.assertIsNone(ratios["fcf_margin_pct"]["FY2024"])
        self.assertIsNone(ratios["fcf_conversion_pct"]["FY2024"])

        # Regla 3: Métricas bancarias debidamente pobladas
        self.assertEqual(summary["revenue"]["FY2024"], 2000000000.0)
        self.assertEqual(summary["net_interest_income"]["FY2024"], 1500000000.0)
        self.assertEqual(summary["non_interest_income"]["FY2024"], 500000000.0)
        self.assertEqual(summary["credit_loss_provisions"]["FY2024"], -300000000.0)
        self.assertEqual(summary["total_deposits"]["FY2024"], 15000000000.0)
        self.assertEqual(summary["net_loans"]["FY2024"], 12000000000.0)

        # Regla 4: Unidades base estrictas (floats absolutos o None)
        for field, series in summary.items():
            val = series.get("FY2024")
            self.assertTrue(val is None or isinstance(val, float), f"{field} no es float ni None: {type(val)}")

    def test_banking_long_term_debt_taxonomy_and_jpm_extraction(self):
        """Verifica que BANKING_TAXONOMY_MAP incluya LongTermDebtAndCapitalLeaseObligationsIncludingCurrentMaturities
        y que para entidades bancarias US-GAAP se extraiga la deuda total correcta."""
        self.assertIn(
            "LongTermDebtAndCapitalLeaseObligationsIncludingCurrentMaturities",
            BANKING_TAXONOMY_MAP["long_term_debt"]
        )

        bal_with_debt = dict(self.bal_data)
        bal_with_debt["LongTermDebtAndCapitalLeaseObligationsIncludingCurrentMaturities"] = {
            "label": "Long-term debt",
            "standard_concept": None,
            "values": {"FY2024": 401418000000.0}
        }
        bal_with_debt["ShortTermBorrowings"] = {
            "label": "Short-term borrowings",
            "standard_concept": None,
            "values": {"FY2024": 52893000000.0}
        }
        summary, _ = extract_canonical_summary(
            self.inc_data, bal_with_debt, self.cf_data, ["FY2024"],
            archetype="FINANCIAL_BANKING"
        )
        self.assertEqual(summary["borrowings"]["FY2024"], 401418000000.0)
        self.assertEqual(summary["repurchase_agreements"]["FY2024"], 52893000000.0)
        self.assertEqual(summary["total_debt"]["FY2024"], 454311000000.0)

    def test_jpm_processed_debt_verification(self):
        """Verifica que los datos procesados de JPM reflejen ~$500.000M ($435.206M LT + $64.776M ST en FY2025)."""
        import json
        jpm_path = Path(__file__).resolve().parent.parent / "data" / "processed" / "JPM" / "financial_statements.json"
        if not jpm_path.exists():
            self.skipTest("JPM processed data not found")
        with open(jpm_path, "r", encoding="utf-8") as f:
            jpm_data = json.load(f)
        summary = jpm_data.get("canonical_summary", {})
        self.assertEqual(summary["borrowings"]["FY2025"], 435206000000.0)
        self.assertEqual(summary["repurchase_agreements"]["FY2025"], 64776000000.0)
        self.assertEqual(summary["total_debt"]["FY2025"], 499982000000.0)
        self.assertEqual(summary["borrowings"]["LTM"], 460523000000.0)
        self.assertEqual(summary["repurchase_agreements"]["LTM"], 72430000000.0)
        self.assertEqual(summary["total_debt"]["LTM"], 532953000000.0)


class TestPlatformEcosystemCanonicalAccounting(unittest.TestCase):
    """Verifica que los ecosistemas de plataforma conserven P&L comercial y registren la pata fintech en campos dedicados."""

    def test_platform_ecosystem_retains_commercial_pnl_and_records_credit(self):
        inc_data = {
            "Revenue": {
                "label": "Marketplace & Fintech Revenues",
                "standard_concept": None,
                "values": {"FY2024": 15000000000.0}
            },
            "CostOfGoodsAndServicesSold": {
                "label": "Cost of Sales",
                "standard_concept": None,
                "values": {"FY2024": 7500000000.0}
            },
            "GrossProfit": {
                "label": "Gross Profit",
                "standard_concept": None,
                "values": {"FY2024": 7500000000.0}
            },
            "OperatingExpense": {
                "label": "Operating Expenses",
                "standard_concept": None,
                "values": {"FY2024": 5000000000.0}
            },
            "ProvisionForDoubtfulAccounts": {
                "label": "Credit Loss Provision",
                "standard_concept": None,
                "values": {"FY2024": 600000000.0}
            },
            "NetIncomeLoss": {
                "label": "Net Income",
                "standard_concept": None,
                "values": {"FY2024": 1200000000.0}
            }
        }
        bal_data = {
            "Assets": {"label": "Total Assets", "standard_concept": None, "values": {"FY2024": 18000000000.0}},
            "StockholdersEquity": {"label": "Equity", "standard_concept": None, "values": {"FY2024": 4000000000.0}},
            "NotesAndLoansReceivableNetCurrent": {"label": "Loans Receivable", "standard_concept": None, "values": {"FY2024": 3500000000.0}}
        }
        cf_data = {
            "NetCashProvidedByOperatingActivities": {"label": "CFO", "standard_concept": None, "values": {"FY2024": 2000000000.0}},
            "PaymentsToAcquirePropertyPlantAndEquipment": {"label": "CapEx", "standard_concept": None, "values": {"FY2024": 500000000.0}}
        }

        summary, ratios = extract_canonical_summary(
            inc_data, bal_data, cf_data, ["FY2024"],
            archetype="PLATFORM_ECOSYSTEM"
        )

        # Margen comercial intacto sin contaminar
        self.assertEqual(summary["revenue"]["FY2024"], 15000000000.0)
        self.assertEqual(summary["cost_of_goods_sold"]["FY2024"], 7500000000.0)
        self.assertEqual(summary["gross_profit"]["FY2024"], 7500000000.0)
        self.assertEqual(ratios["gross_margin_pct"]["FY2024"], 50.0)

        # FCF comercial calculado normalmente
        self.assertEqual(summary["free_cash_flow"]["FY2024"], 1500000000.0)

        # Provisiones crediticias y cartera registradas en campos dedicados
        self.assertEqual(summary["credit_loss_provisions"]["FY2024"], -600000000.0)
        self.assertEqual(summary["net_loans"]["FY2024"], 3500000000.0)


class TestTableScaleFactorDetection(unittest.TestCase):
    """Verifica la detección dinámica de escalas en tablas 6-K/HTML (Niveles 1, 2 y 3)."""

    def test_detect_thousands_and_millions(self):
        import pandas as pd
        tbl_thousands = pd.DataFrame([["(In thousands of U.S. Dollars)", ""], ["Interest Income", "1,200"]])
        tbl_millions = pd.DataFrame([["Amounts in millions of USD", ""], ["Net Revenue", "5,400"]])
        tbl_base = pd.DataFrame([["Balance Sheet", "December 31"], ["Cash", "150000000"]])

        self.assertEqual(detect_table_scale_factor(tbl_thousands), 1000.0)
        self.assertEqual(detect_table_scale_factor(tbl_millions), 1000000.0)
        self.assertEqual(detect_table_scale_factor(tbl_base), 1.0)

    def test_level1_preceding_html_context(self):
        """Nivel 1: Verifica extracción de contexto previo e inferencia de escala."""
        import pandas as pd
        html = "<div><p><i>(In thousands of U.S. Dollars)</i></p><table><tr><td>Cash and cash equivalents</td><td>100</td></tr></table></div>"
        tbl = pd.DataFrame([["Cash and cash equivalents", "100"]])
        pre_ctx = get_preceding_html_context(html, tbl)
        self.assertIn("in thousands", pre_ctx.lower())
        self.assertEqual(detect_table_scale_factor(tbl, preceding_html=pre_ctx), 1000.0)

    def test_level2_global_doc_scale(self):
        """Nivel 2: Verifica detección de escala declarada a nivel global del documento."""
        html_thousands = "<html><body><h1>Financial Statements</h1><p>(in thousands of U.S. Dollars)</p></body></html>"
        html_millions = "<html><body><h1>Financial Statements</h1><p>Amounts in millions of U.S. Dollars</p></body></html>"
        html_plain = "<html><body><h1>Financial Statements</h1><p>Amounts in USD</p></body></html>"

        self.assertEqual(detect_global_doc_scale(html_thousands), 1000.0)
        self.assertEqual(detect_global_doc_scale(html_millions), 1000000.0)
        self.assertEqual(detect_global_doc_scale(html_plain), 1.0)

    def test_level3_cross_period_ratio_calibration(self):
        """Nivel 3: Verifica lógica de ratio cruzado para calibración matemática."""
        fy_assets = 74893877000.0
        interim_assets_unscaled = 82753414.0
        ratio = fy_assets / interim_assets_unscaled
        self.assertTrue(700.0 <= ratio <= 1300.0)
        calib_factor = 1000.0 if (700.0 <= ratio <= 1300.0) else 1.0
        self.assertEqual(calib_factor, 1000.0)
        self.assertAlmostEqual(interim_assets_unscaled * calib_factor, 82753414000.0)


if __name__ == "__main__":
    unittest.main()

