"""
test_archetype_classifier.py - Suite de pruebas unitarias para la detección,
extracción canónica y normalización de arquetipos institucionales:
- REAL_ESTATE_REIT (SOCIMIs / REITs Inmobiliarios)
- INSURANCE (Compañías de Seguros y Reaseguros)
- FINANCIAL_BANKING (Intermediación Bancaria / Fintech)
- PLATFORM_ECOSYSTEM (Ecosistemas Híbridos E-Commerce + Crédito)
- STANDARD_CORPORATE (Corporativo e Industrial Tradicional)
"""

import sys
import unittest
import tempfile
import json
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "pipeline"))

from sec_extractor import (
    detect_company_archetype,
    normalize_archetype,
    CORPORATE_ARCHETYPE_ALIASES,
    CANONICAL_ARCHETYPES,
    extract_canonical_summary,
    REIT_TAXONOMY_MAP,
    INSURANCE_TAXONOMY_MAP,
    XBRL_TAXONOMY_MAP,
    BANKING_TAXONOMY_MAP,
)
from kpi_extractor import (
    normalize_reit_kpis,
    normalize_insurance_kpis,
    normalize_banking_kpis,
    normalize_platform_kpis,
    normalize_corporate_kpis,
    extract_operational_kpis,
)


def _wrap_values(raw_dict):
    """Convierte un diccionario {concepto: {period: val}} al formato oficial de XBRL."""
    return {k: {"label": k, "standard_concept": None, "values": v} for k, v in raw_dict.items()}


class TestArchetypeClassifier(unittest.TestCase):

    # ==========================================================================
    # 1. TEST DE DETECCIÓN DINÁMICA DE ARQUETIPOS (DYNAMIC CLASSIFICATION)
    # ==========================================================================

    def test_detect_realty_income_reit(self):
        """O (Realty Income): SIC 6798 / Perfil REIT debe clasificarse como REAL_ESTATE_REIT."""
        profile = {
            "sic_code": "6798",
            "industry": "Real Estate Investment Trusts",
            "sector": "Real Estate",
            "business_model": "Equity REIT"
        }
        arch = detect_company_archetype(sic_code="6798", profile_data=profile)
        self.assertEqual(arch, "REAL_ESTATE_REIT")

        # Prueba por conceptos XBRL sin SIC explícito
        xbrl_concepts = ["RealEstateInvestmentPropertyAtCost", "RentalRevenue", "RealEstateExpense"]
        arch_xbrl = detect_company_archetype(detected_concepts=xbrl_concepts)
        self.assertEqual(arch_xbrl, "REAL_ESTATE_REIT")

    def test_detect_progressive_insurance(self):
        """PGR / TRV: SIC 6331 / Perfil Seguros debe clasificarse como INSURANCE."""
        profile = {
            "sic_code": "6331",
            "industry": "Property & Casualty Insurance",
            "sector": "Financial Services",
            "business_model": "P&C Insurance Underwriting"
        }
        arch = detect_company_archetype(sic_code="6331", profile_data=profile)
        self.assertEqual(arch, "INSURANCE")

        # Prueba por conceptos XBRL sin SIC explícito
        xbrl_concepts = ["PremiumsEarnedNet", "LiabilityForClaimsAndClaimsAdjustmentExpense", "UnearnedPremiums"]
        arch_xbrl = detect_company_archetype(detected_concepts=xbrl_concepts)
        self.assertEqual(arch_xbrl, "INSURANCE")

    def test_detect_insurance_sic_expanded_range(self):
        """
        Verifica la cobertura expandida de SIC para INSURANCE (6300 <= SIC <= 6499):
        - 63xx: Aseguradoras directas / Carriers (ej. 6311 Vida, 6331 P&C).
        - 64xx: Agencias, brokers y servicios de seguros (ej. 6411 Brokers de Seguros).
        - Límites exactos: 6300 y 6499 deben clasificar como INSURANCE.
        - Fuera de rango: 6299 y 6500 no deben clasificar como INSURANCE sin XBRL específico.
        """
        # Brokers de seguros (SIC 6411)
        self.assertEqual(detect_company_archetype(sic_code="6411"), "INSURANCE")
        # Aseguradoras directas (SIC 6321)
        self.assertEqual(detect_company_archetype(sic_code="6321"), "INSURANCE")
        # Límites de intervalo
        self.assertEqual(detect_company_archetype(sic_code=6300), "INSURANCE")
        self.assertEqual(detect_company_archetype(sic_code=6499), "INSURANCE")
        # Fuera de rango
        self.assertNotEqual(detect_company_archetype(sic_code=6299), "INSURANCE")
        self.assertNotEqual(detect_company_archetype(sic_code=6500), "INSURANCE")

    def test_canonical_corporate_alias_reciprocity(self):
        """
        Verifica la reciprocidad canónica de alias CORPORATE_STANDARD <-> STANDARD_CORPORATE:
        - Declaración explícita de CORPORATE_STANDARD es respetada.
        - Declaración explícita de STANDARD_CORPORATE es respetada.
        - normalize_archetype unifica ambos alias recíprocos.
        - Detección por defecto satisface pertenencia a CORPORATE_ARCHETYPE_ALIASES.
        """
        # Declaración como CORPORATE_STANDARD
        arch_cs = detect_company_archetype(profile_data={"archetype": "CORPORATE_STANDARD"})
        self.assertEqual(arch_cs, "CORPORATE_STANDARD")

        # Declaración como STANDARD_CORPORATE
        arch_sc = detect_company_archetype(profile_data={"archetype": "STANDARD_CORPORATE"})
        self.assertEqual(arch_sc, "STANDARD_CORPORATE")

        # Normalizador recíproco
        self.assertEqual(normalize_archetype("CORPORATE_STANDARD"), "STANDARD_CORPORATE")
        self.assertEqual(normalize_archetype("STANDARD_CORPORATE"), "STANDARD_CORPORATE")
        self.assertEqual(normalize_archetype("CORPORATE_STANDARD", default="CORPORATE_STANDARD"), "CORPORATE_STANDARD")

        # Pertenencia a la tupla de alias corporativos
        self.assertIn(arch_cs, CORPORATE_ARCHETYPE_ALIASES)
        self.assertIn(arch_sc, CORPORATE_ARCHETYPE_ALIASES)

    def test_detect_control_companies_zero_regressions(self):
        """Validar preservación de arquetipos en empresas de control previas."""
        # 1. NU -> FINANCIAL_BANKING
        nu_profile = {
            "sic_code": "6020",
            "industry": "Financial Services / Neobank",
            "sector": "Financials",
            "business_model": "BANKING"
        }
        nu_concepts = ["DepositsFromCustomers", "LoansAndAdvancesToCustomers", "ExpectedCreditLoss"]
        arch_nu = detect_company_archetype(sic_code="6020", profile_data=nu_profile, detected_concepts=nu_concepts)
        self.assertEqual(arch_nu, "FINANCIAL_BANKING")

        # 2. MELI -> PLATFORM_ECOSYSTEM
        meli_profile = {
            "sic_code": "7389",
            "industry": "E-Commerce & Digital Payments Platform",
            "sector": "Consumer Cyclical",
            "business_model": "PLATFORM"
        }
        meli_concepts = ["CostOfGoodsSold", "InventoryNet", "CreditCardReceivables1", "ExpectedCreditLoss"]
        arch_meli = detect_company_archetype(sic_code="7389", profile_data=meli_profile, detected_concepts=meli_concepts)
        self.assertEqual(arch_meli, "PLATFORM_ECOSYSTEM")

        # 3. DECK -> STANDARD_CORPORATE
        deck_profile = {
            "sic_code": "3021",
            "industry": "Footwear & Accessories",
            "sector": "Consumer Cyclical",
            "business_model": "CORPORATE"
        }
        deck_concepts = ["CostOfGoodsSold", "InventoryNet"]
        arch_deck = detect_company_archetype(sic_code="3021", profile_data=deck_profile, detected_concepts=deck_concepts)
        self.assertEqual(arch_deck, "STANDARD_CORPORATE")

        # 4. AAPL -> STANDARD_CORPORATE
        aapl_profile = {
            "sic_code": "3571",
            "industry": "Consumer Electronics",
            "sector": "Technology",
            "business_model": "CORPORATE"
        }
        aapl_concepts = ["CostOfGoodsSold", "InventoryNet"]
        arch_aapl = detect_company_archetype(sic_code="3571", profile_data=aapl_profile, detected_concepts=aapl_concepts)
        self.assertEqual(arch_aapl, "STANDARD_CORPORATE")

    # ==========================================================================
    # 2. TEST DE EXTRACCIÓN CANÓNICA: REAL_ESTATE_REIT
    # ==========================================================================

    def test_canonical_reit_extraction(self):
        """
        Verifica el tratamiento contable de REAL_ESTATE_REIT:
        - COGS = None
        - Gross Profit = NOI (Rental Revenue - Property OpEx)
        - FFO = Net Income + Real Estate D&A - Gains on Sale
        - AFFO = FFO - Recurring CapEx
        - FCF = AFFO (Interoperabilidad de valoración)
        """
        inc_data = _wrap_values({
            "RentalRevenue": {"2025": 5000.0, "2024": 4600.0},
            "PropertyOperatingExpenses": {"2025": 400.0, "2024": 380.0},
            "OperatingExpenses": {"2025": 600.0, "2024": 550.0},
            "OperatingIncomeLoss": {"2025": 2400.0, "2024": 2200.0},
            "NetIncomeLoss": {"2025": 1800.0, "2024": 1600.0},
            "RealEstateDepreciation": {"2025": 1200.0, "2024": 1100.0},
            "GainLossOnSaleOfProperties": {"2025": 100.0, "2024": 50.0},
            "WeightedAverageNumberOfDilutedSharesOutstanding": {"2025": 600.0, "2024": 580.0},
            "EarningsPerShareDiluted": {"2025": 3.0, "2024": 2.76},
        })
        bal_data = _wrap_values({
            "RealEstateInvestmentPropertyAtCost": {"2025": 38000.0, "2024": 35000.0},
            "RealEstateInvestmentPropertyNet": {"2025": 30000.0, "2024": 28000.0},
            "CashAndCashEquivalentsAtCarryingValue": {"2025": 800.0, "2024": 700.0},
            "ShortTermBorrowings": {"2025": 500.0, "2024": 400.0},
            "LongTermDebtNoncurrent": {"2025": 12000.0, "2024": 11000.0},
            "StockholdersEquity": {"2025": 18000.0, "2024": 17000.0},
        })
        cf_data = _wrap_values({
            "NetCashProvidedByUsedInOperatingActivities": {"2025": 2800.0, "2024": 2600.0},
            "RecurringCapitalExpendituresMaintenance": {"2025": 250.0, "2024": 220.0},
            "PaymentsToAcquireProductiveAssets": {"2025": 300.0, "2024": 250.0},
        })
        periods = ["2025", "2024"]

        canonical, ratios = extract_canonical_summary(
            inc_data=inc_data,
            bal_data=bal_data,
            cf_data=cf_data,
            periods=periods,
            facts_df=None,
            archetype="REAL_ESTATE_REIT"
        )

        p = "2025"
        # 1. COGS debe ser None
        self.assertIsNone(canonical["cost_of_goods_sold"][p])

        # 2. Rental Revenue y NOI
        self.assertEqual(canonical["rental_revenue"][p], 5000.0)
        self.assertEqual(canonical["revenue"][p], 5000.0)
        expected_noi = 5000.0 - 400.0  # 4600.0
        self.assertEqual(canonical["noi"][p], expected_noi)
        self.assertEqual(canonical["gross_profit"][p], expected_noi)

        # 3. FFO = Net Income (1800) + D&A RE (1200) - Gain on Sale (100) = 2900.0
        expected_ffo = 1800.0 + 1200.0 - 100.0
        self.assertEqual(canonical["ffo"][p], expected_ffo)

        # 4. AFFO = FFO (2900) - Recurring CapEx (250) = 2650.0
        expected_affo = expected_ffo - 250.0
        self.assertEqual(canonical["affo"][p], expected_affo)

        # 5. Equivalencia institucional: FCF == AFFO
        self.assertEqual(canonical["free_cash_flow"][p], expected_affo)

        # 6. Ratios específicos de REIT
        self.assertEqual(ratios["noi_margin_pct"][p], round((expected_noi / 5000.0) * 100, 2))
        self.assertEqual(ratios["ffo_per_share"][p], round(expected_ffo / 600.0, 2))
        self.assertEqual(ratios["affo_per_share"][p], round(expected_affo / 600.0, 2))

    # ==========================================================================
    # 3. TEST DE EXTRACCIÓN CANÓNICA: INSURANCE
    # ==========================================================================

    def test_canonical_insurance_extraction(self):
        """
        Verifica el tratamiento contable de INSURANCE:
        - COGS = None, Gross Profit = None, FCF = None
        - Combined Ratio = Loss Ratio + Expense Ratio
        - Float = Loss Reserves + Unearned Premiums - Reinsurance Receivables
        - Current Assets / Current Liabilities = None (Balance no clasificado)
        """
        inc_data = _wrap_values({
            "PremiumsEarnedNet": {"2025": 12000.0, "2024": 10500.0},
            "NetInvestmentIncome": {"2025": 1800.0, "2024": 1500.0},
            "IncurredClaimsAndLossAdjustmentExpensesNet": {"2025": 8400.0, "2024": 7350.0},
            "DeferredPolicyAcquisitionCostAmortizationExpense": {"2025": 2400.0, "2024": 2100.0},
            "OperatingExpenses": {"2025": 2400.0, "2024": 2100.0},
            "OperatingIncomeLoss": {"2025": 2200.0, "2024": 1800.0},
            "NetIncomeLoss": {"2025": 1700.0, "2024": 1400.0},
        })
        bal_data = _wrap_values({
            "LiabilityForClaimsAndClaimsAdjustmentExpense": {"2025": 25000.0, "2024": 22000.0},
            "UnearnedPremiums": {"2025": 8000.0, "2024": 7000.0},
            "ReinsuranceRecoverables": {"2025": 3000.0, "2024": 2500.0},
            "Investments": {"2025": 35000.0, "2024": 31000.0},
            "CashAndCashEquivalentsAtCarryingValue": {"2025": 2000.0, "2024": 1800.0},
            "StockholdersEquity": {"2025": 9000.0, "2024": 8000.0},
        })
        cf_data = _wrap_values({
            "NetCashProvidedByUsedInOperatingActivities": {"2025": 3500.0, "2024": 3000.0},
            "PaymentsToAcquirePropertyPlantAndEquipment": {"2025": 150.0, "2024": 120.0},
        })
        periods = ["2025", "2024"]

        canonical, ratios = extract_canonical_summary(
            inc_data=inc_data,
            bal_data=bal_data,
            cf_data=cf_data,
            periods=periods,
            facts_df=None,
            archetype="INSURANCE"
        )

        p = "2025"
        # 1. Partidas comerciales e industriales anuladas
        self.assertIsNone(canonical["cost_of_goods_sold"][p])
        self.assertIsNone(canonical["gross_profit"][p])
        self.assertIsNone(canonical["free_cash_flow"][p])
        self.assertIsNone(canonical["current_assets"][p])
        self.assertIsNone(canonical["current_liabilities"][p])
        self.assertIsNone(canonical["net_working_capital"][p])

        # 2. Revenue = Net Premiums Earned (12000) + Net Investment Income (1800) = 13800.0
        self.assertEqual(canonical["revenue"][p], 13800.0)

        # 3. Ratios Técnicos Aseguradores
        # Loss Ratio = 8400 / 12000 = 70.0%
        # Expense Ratio = 2400 / 12000 = 20.0%
        # Combined Ratio = 70.0 + 20.0 = 90.0%
        self.assertEqual(canonical["loss_ratio"][p], 70.0)
        self.assertEqual(canonical["expense_ratio"][p], 20.0)
        self.assertEqual(canonical["combined_ratio"][p], 90.0)
        self.assertEqual(ratios["combined_ratio_pct"][p], 90.0)

        # 4. Float Asegurador: Loss Reserves (25000) + Unearned Premiums (8000) - Reinsurance Rec (3000) = 30000.0
        expected_float = 25000.0 + 8000.0 - 3000.0
        self.assertEqual(canonical["float_usd"][p], expected_float)
        self.assertEqual(canonical["total_investments"][p], 35000.0)

    # ==========================================================================
    # 4. TEST DE NORMALIZACIÓN DE KPIS OPERATIVOS EN KPI_EXTRACTOR
    # ==========================================================================

    def test_normalize_reit_kpis(self):
        """Verifica la extracción y estructuración de KPIs operativos de REIT."""
        sample_text = """
        Operational Highlights:
        - Portfolio occupancy remained exceptionally strong at 98.6% across our real estate holdings.
        - Weighted Average Lease Term (WALT) was 9.4 years.
        - Dividend payout ratio based on AFFO was 75.2%.
        - Acquisition cap rate averaged 7.1% during the quarter.
        - Total properties reached 15,450 commercial units.
        - Same-store NOI grew 2.8% year-over-year.
        """
        sec_data = {
            "source_doc": "reit_ex99.htm",
            "text": sample_text,
            "lines": [l.strip() for l in sample_text.splitlines() if l.strip()]
        }
        res = normalize_reit_kpis(sec_data, None, {})

        self.assertEqual(res.get("archetype"), "REAL_ESTATE_REIT")
        self.assertEqual(res.get("occupancy_rate_pct"), 98.6)
        self.assertEqual(res.get("weighted_average_lease_term_years"), 9.4)
        self.assertEqual(res.get("payout_ratio_affo_pct"), 75.2)
        self.assertEqual(res.get("cap_rate_pct"), 7.1)
        self.assertEqual(res.get("total_properties"), 15450)
        self.assertEqual(res.get("same_store_noi_growth_pct"), 2.8)

        # Verificar anidamiento en bloque reit_operational_kpis
        reit_ops = res.get("reit_operational_kpis", {})
        self.assertEqual(reit_ops.get("occupancy_rate_pct"), 98.6)
        self.assertEqual(reit_ops.get("walt_years"), 9.4)

    def test_normalize_insurance_kpis(self):
        """Verifica la extracción y estructuración de KPIs operativos de Seguros."""
        sample_text = """
        Insurance Highlights:
        - Personal lines combined ratio of 88.5% and commercial lines combined ratio of 92.1%.
        - Annualized net investment yield of 4.3% on the fixed income and equity portfolio.
        - Total policies in force reached 31.2 million policies.
        - Net written premiums grew 18.4% compared to the prior-year quarter.
        """
        sec_data = {
            "source_doc": "pgr_ex99.htm",
            "text": sample_text,
            "lines": [l.strip() for l in sample_text.splitlines() if l.strip()]
        }
        res = normalize_insurance_kpis(sec_data, None, {})

        self.assertEqual(res.get("archetype"), "INSURANCE")
        self.assertEqual(res.get("investment_yield_pct"), 4.3)
        self.assertEqual(res.get("policies_in_force_m"), 31.2)
        self.assertEqual(res.get("net_written_premiums_growth_pct"), 18.4)

        # Verificar desglose de combined ratio por línea
        by_line = res.get("combined_ratio_by_line", {})
        self.assertEqual(by_line.get("personal_lines"), 88.5)
        self.assertEqual(by_line.get("commercial_lines"), 92.1)

        # Verificar anidamiento en insurance_operational_kpis
        ins_ops = res.get("insurance_operational_kpis", {})
        self.assertEqual(ins_ops.get("investment_yield_pct"), 4.3)
        self.assertEqual(ins_ops.get("policies_in_force_m"), 31.2)

    @patch("kpi_extractor.extract_from_sec_ex99")
    @patch("kpi_extractor.extract_from_presentation_pdf")
    def test_dispatcher_reit_and_insurance(self, mock_pdf, mock_sec):
        """Verifica que extract_operational_kpis despache correctamente a REIT y Seguros."""
        mock_sec.return_value = {"source_doc": "mock.htm", "text": "", "lines": []}
        mock_pdf.return_value = {"source_presentation": "mock.pdf", "text": "", "total_slides": 0}

        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = Path(tmpdir)

            # 1. Despacho para REIT
            reit_recon = extract_operational_kpis(
                ticker="MOCK_REIT",
                archetype="REAL_ESTATE_REIT",
                output_dir=out_path
            )
            recon_file = out_path / "presentation_reconciliation.json"
            self.assertTrue(recon_file.exists())
            with open(recon_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.assertEqual(data.get("archetype"), "REAL_ESTATE_REIT")

            # 2. Despacho para Seguros
            ins_recon = extract_operational_kpis(
                ticker="MOCK_INS",
                archetype="INSURANCE",
                output_dir=out_path
            )
            with open(recon_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.assertEqual(data.get("archetype"), "INSURANCE")


if __name__ == "__main__":
    unittest.main()
