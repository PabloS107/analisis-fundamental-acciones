"""
test_m1_empirical_stress.py - Empirical Adversarial Stress Test Suite for Milestone 1.

Author: Challenger M1.1 (Taxonomy & Archetypes Stress Challenger)
Targets:
1. Dynamic archetype classification across SIC boundary codes and edge cases (detect_company_archetype).
2. Archetype normalization and reciprocal corporate aliases (normalize_archetype).
3. Banking debt taxonomy map and extraction under edge conditions (BANKING_TAXONOMY_MAP["long_term_debt"]).
4. Empirical verification of control companies (AAPL, DECK) and milestone targets (JPM, MELI, O).
5. Forensic reproduction of discovered edge cases (whitespace truthiness in normalize_archetype, float SIC codes, and negative debt pass-through).
"""

import sys
import unittest
import json
from pathlib import Path
from unittest.mock import MagicMock

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "pipeline"))

from sec_extractor import (
    detect_company_archetype,
    normalize_archetype,
    extract_canonical_summary,
    BANKING_TAXONOMY_MAP,
    REIT_TAXONOMY_MAP,
    INSURANCE_TAXONOMY_MAP,
    XBRL_TAXONOMY_MAP,
    CORPORATE_ARCHETYPE_ALIASES,
    CANONICAL_ARCHETYPES,
    ARCHETYPE_ALIASES,
)
from audit_engine import run_full_audit


def _wrap_concept_data(raw_dict):
    """Auxiliary helper to convert {concept: {period: value}} to SEC extractor concept dict."""
    return {
        concept: {
            "label": concept,
            "standard_concept": f"us-gaap:{concept}",
            "values": {str(p): val for p, val in p_dict.items()}
        }
        for concept, p_dict in raw_dict.items()
    }


class TestM1ArchetypeClassificationStress(unittest.TestCase):
    """Stress tests for detect_company_archetype and normalize_archetype."""

    # --------------------------------------------------------------------------
    # 1. SIC Boundary Tests
    # --------------------------------------------------------------------------
    def test_insurance_sic_exact_boundaries(self):
        """Stress-test exact lower and upper boundaries of Insurance SIC range (6300-6499)."""
        # Outer bounds (should NOT classify as INSURANCE)
        self.assertEqual(detect_company_archetype(sic_code=6298), "STANDARD_CORPORATE")
        self.assertEqual(detect_company_archetype(sic_code=6299), "STANDARD_CORPORATE")
        self.assertEqual(detect_company_archetype(sic_code=6500), "STANDARD_CORPORATE")
        self.assertEqual(detect_company_archetype(sic_code=6501), "STANDARD_CORPORATE")

        # Inner bounds (MUST classify as INSURANCE)
        self.assertEqual(detect_company_archetype(sic_code=6300), "INSURANCE")
        self.assertEqual(detect_company_archetype(sic_code=6301), "INSURANCE")
        self.assertEqual(detect_company_archetype(sic_code=6498), "INSURANCE")
        self.assertEqual(detect_company_archetype(sic_code=6499), "INSURANCE")

        # Representative SIC codes within range
        self.assertEqual(detect_company_archetype(sic_code=6311), "INSURANCE")  # Life Insurance
        self.assertEqual(detect_company_archetype(sic_code=6321), "INSURANCE")  # Accident & Health
        self.assertEqual(detect_company_archetype(sic_code=6331), "INSURANCE")  # Fire, Marine & Casualty
        self.assertEqual(detect_company_archetype(sic_code=6351), "INSURANCE")  # Surety Insurance
        self.assertEqual(detect_company_archetype(sic_code=6411), "INSURANCE")  # Insurance Agents & Brokers

    def test_banking_sic_exact_boundaries(self):
        """Stress-test exact lower and upper boundaries of Banking SIC range (6000-6199)."""
        # Outer bounds (should NOT classify as FINANCIAL_BANKING)
        self.assertEqual(detect_company_archetype(sic_code=5998), "STANDARD_CORPORATE")
        self.assertEqual(detect_company_archetype(sic_code=5999), "STANDARD_CORPORATE")
        self.assertEqual(detect_company_archetype(sic_code=6200), "STANDARD_CORPORATE")
        self.assertEqual(detect_company_archetype(sic_code=6211), "STANDARD_CORPORATE")
        self.assertEqual(detect_company_archetype(sic_code=6299), "STANDARD_CORPORATE")

        # Inner bounds (MUST classify as FINANCIAL_BANKING)
        self.assertEqual(detect_company_archetype(sic_code=6000), "FINANCIAL_BANKING")
        self.assertEqual(detect_company_archetype(sic_code=6001), "FINANCIAL_BANKING")
        self.assertEqual(detect_company_archetype(sic_code=6198), "FINANCIAL_BANKING")
        self.assertEqual(detect_company_archetype(sic_code=6199), "FINANCIAL_BANKING")

        # Representative banking codes
        self.assertEqual(detect_company_archetype(sic_code=6020), "FINANCIAL_BANKING")  # Commercial Banks
        self.assertEqual(detect_company_archetype(sic_code=6021), "FINANCIAL_BANKING")  # National Commercial Banks
        self.assertEqual(detect_company_archetype(sic_code=6022), "FINANCIAL_BANKING")  # State Commercial Banks
        self.assertEqual(detect_company_archetype(sic_code=6035), "FINANCIAL_BANKING")  # Savings Institutions
        self.assertEqual(detect_company_archetype(sic_code=6141), "FINANCIAL_BANKING")  # Personal Credit Institutions

    def test_reit_sic_exact_boundaries(self):
        """Stress-test REIT SIC code 6798 boundaries."""
        self.assertEqual(detect_company_archetype(sic_code=6797), "STANDARD_CORPORATE")
        self.assertEqual(detect_company_archetype(sic_code=6798), "REAL_ESTATE_REIT")
        self.assertEqual(detect_company_archetype(sic_code=6799), "STANDARD_CORPORATE")

    def test_platform_ecosystem_sic_and_balance_signals(self):
        """Stress-test PLATFORM_ECOSYSTEM SIC codes (7389, 5961, 5990) with and without loan/fintech signals."""
        # SIC 7389 with loan/fintech signals -> PLATFORM_ECOSYSTEM
        self.assertEqual(
            detect_company_archetype(sic_code=7389, detected_concepts=["LoansAndAdvancesToCustomers"]),
            "PLATFORM_ECOSYSTEM"
        )
        self.assertEqual(
            detect_company_archetype(sic_code=7389, detected_concepts=["ExpectedCreditLoss"]),
            "PLATFORM_ECOSYSTEM"
        )
        self.assertEqual(
            detect_company_archetype(sic_code=7389, profile_data={"industry": "Fintech Platform"}),
            "PLATFORM_ECOSYSTEM"
        )
        # SIC 7389 without any credit or fintech profile -> should fall through to STANDARD_CORPORATE
        self.assertEqual(detect_company_archetype(sic_code=7389), "STANDARD_CORPORATE")

        # SIC 5961 (Catalog/Mail-Order/E-Commerce) with loans
        self.assertEqual(
            detect_company_archetype(sic_code=5961, detected_concepts=["CreditCardReceivables1"]),
            "PLATFORM_ECOSYSTEM"
        )
        self.assertEqual(detect_company_archetype(sic_code=5961), "STANDARD_CORPORATE")

    # --------------------------------------------------------------------------
    # 2. Malformed, String & Edge Input Variations
    # --------------------------------------------------------------------------
    def test_sic_input_type_variations(self):
        """Stress-test diverse input types and formats for sic_code parameter."""
        # None, empty, whitespace
        self.assertEqual(detect_company_archetype(sic_code=None), "STANDARD_CORPORATE")
        self.assertEqual(detect_company_archetype(sic_code=""), "STANDARD_CORPORATE")
        self.assertEqual(detect_company_archetype(sic_code="   "), "STANDARD_CORPORATE")
        self.assertEqual(detect_company_archetype(sic_code="N/A"), "STANDARD_CORPORATE")
        self.assertEqual(detect_company_archetype(sic_code="NONE"), "STANDARD_CORPORATE")
        self.assertEqual(detect_company_archetype(sic_code="INVALID_SIC"), "STANDARD_CORPORATE")

        # Integer formats
        self.assertEqual(detect_company_archetype(sic_code=6021), "FINANCIAL_BANKING")
        self.assertEqual(detect_company_archetype(sic_code="6021"), "FINANCIAL_BANKING")
        self.assertEqual(detect_company_archetype(sic_code=" 6021 \n"), "FINANCIAL_BANKING")

        # SEC EDGAR composite string format: '6021 / National Commercial Banks'
        self.assertEqual(
            detect_company_archetype(sic_code="6021 / National Commercial Banks"),
            "FINANCIAL_BANKING"
        )
        self.assertEqual(
            detect_company_archetype(sic_code=" 6331 / Fire, Marine & Casualty Insurance "),
            "INSURANCE"
        )
        self.assertEqual(
            detect_company_archetype(sic_code="6798 / Real Estate Investment Trusts"),
            "REAL_ESTATE_REIT"
        )

        # Company object mock
        mock_co_bank = MagicMock()
        mock_co_bank.sic = "6020 / Commercial Banks"
        self.assertEqual(detect_company_archetype(company=mock_co_bank), "FINANCIAL_BANKING")

        mock_co_none = MagicMock()
        mock_co_none.sic = None
        self.assertEqual(detect_company_archetype(company=mock_co_none), "STANDARD_CORPORATE")

        mock_co_no_attr = object()
        self.assertEqual(detect_company_archetype(company=mock_co_no_attr), "STANDARD_CORPORATE")

    def test_detect_company_archetype_float_sic_anomaly(self):
        """
        Adversarial Edge Case: A float SIC code (e.g. 6021.0 from pandas float column with NaNs)
        fails to parse with int(str(6021.0)) because int('6021.0') raises ValueError.
        Verifies that it gracefully catches the ValueError without crashing, but documents
        that it falls through to STANDARD_CORPORATE.
        """
        # Floats fall through to default without crashing
        res_float = detect_company_archetype(sic_code=6021.0)
        self.assertEqual(res_float, "STANDARD_CORPORATE")
        # Whereas integer successfully detects FINANCIAL_BANKING
        res_int = detect_company_archetype(sic_code=6021)
        self.assertEqual(res_int, "FINANCIAL_BANKING")

    def test_profile_data_precedence_and_overrides(self):
        """Stress-test profile_data declared archetype, business model, and sector overrides."""
        # Declared archetype in canonical set takes immediate precedence
        for arch in CANONICAL_ARCHETYPES:
            res = detect_company_archetype(sic_code=6021, profile_data={"archetype": arch})
            self.assertEqual(res, arch)

        # Lowercase declared archetype should also be accepted
        res_lower = detect_company_archetype(profile_data={"archetype": "financial_banking"})
        self.assertEqual(res_lower, "FINANCIAL_BANKING")

        # Invalid declared archetype falls back to SIC or default
        res_invalid = detect_company_archetype(sic_code=6021, profile_data={"archetype": "UNKNOWN_ARCH"})
        self.assertEqual(res_invalid, "FINANCIAL_BANKING")

        # Text-based business model overrides without SIC code
        self.assertEqual(
            detect_company_archetype(profile_data={"business_model": "Equity REIT", "industry": "Real Estate"}),
            "REAL_ESTATE_REIT"
        )
        self.assertEqual(
            detect_company_archetype(profile_data={"business_model": "P&C Insurance Underwriting", "industry": "Insurance"}),
            "INSURANCE"
        )
        self.assertEqual(
            detect_company_archetype(profile_data={"business_model": "BANKING", "industry": "Commercial Banking"}),
            "FINANCIAL_BANKING"
        )

    # --------------------------------------------------------------------------
    # 3. Archetype Normalization Stress Tests
    # --------------------------------------------------------------------------
    def test_normalize_archetype_exhaustive_stress(self):
        """Stress-test normalize_archetype across all aliases, casing, whitespace, and defaults."""
        # Reciprocal corporate aliases
        self.assertEqual(normalize_archetype("CORPORATE_STANDARD"), "STANDARD_CORPORATE")
        self.assertEqual(normalize_archetype("STANDARD_CORPORATE"), "STANDARD_CORPORATE")
        self.assertEqual(normalize_archetype("corporate_standard"), "STANDARD_CORPORATE")
        self.assertEqual(normalize_archetype("standard_corporate"), "STANDARD_CORPORATE")
        self.assertEqual(normalize_archetype("  CORPORATE_STANDARD  "), "STANDARD_CORPORATE")
        self.assertEqual(normalize_archetype("  STANDARD_CORPORATE  "), "STANDARD_CORPORATE")

        # Custom default parameter test
        self.assertEqual(
            normalize_archetype("CORPORATE_STANDARD", default="CORPORATE_STANDARD"),
            "CORPORATE_STANDARD"
        )
        self.assertEqual(
            normalize_archetype("STANDARD_CORPORATE", default="CORPORATE_STANDARD"),
            "CORPORATE_STANDARD"
        )

        # Canonical aliases mapping
        self.assertEqual(normalize_archetype("BANKING"), "FINANCIAL_BANKING")
        self.assertEqual(normalize_archetype("BANKING_FINANCIAL"), "FINANCIAL_BANKING")
        self.assertEqual(normalize_archetype("financial_banking"), "FINANCIAL_BANKING")
        self.assertEqual(normalize_archetype("INSURER"), "INSURANCE")
        self.assertEqual(normalize_archetype("insurance"), "INSURANCE")
        self.assertEqual(normalize_archetype("REIT"), "REAL_ESTATE_REIT")
        self.assertEqual(normalize_archetype("REAL_ESTATE"), "REAL_ESTATE_REIT")
        self.assertEqual(normalize_archetype("real_estate_reit"), "REAL_ESTATE_REIT")
        self.assertEqual(normalize_archetype("ECOSYSTEM_PLATFORM"), "PLATFORM_ECOSYSTEM")
        self.assertEqual(normalize_archetype("platform_ecosystem"), "PLATFORM_ECOSYSTEM")

        # Empty / None handling
        self.assertEqual(normalize_archetype(None), "STANDARD_CORPORATE")
        self.assertEqual(normalize_archetype(""), "STANDARD_CORPORATE")
        self.assertEqual(normalize_archetype(None, default="CUSTOM_DEFAULT"), "CUSTOM_DEFAULT")

        # Unknown / pass-through
        self.assertEqual(normalize_archetype("UNKNOWN_NEW_ARCHETYPE"), "UNKNOWN_NEW_ARCHETYPE")

    def test_normalize_archetype_whitespace_truthiness_anomaly(self):
        """
        Adversarial Edge Case: normalize_archetype('   ')
        Because bool('   ') is True, it bypasses 'if not archetype: return default'.
        After strip(), arch_clean is '', which is not in CORPORATE_ARCHETYPE_ALIASES,
        causing it to return '' instead of the default.
        """
        res_whitespace = normalize_archetype("   ")
        # Empirical finding: returns empty string '' rather than default 'STANDARD_CORPORATE'
        self.assertEqual(res_whitespace, "")
        self.assertNotEqual(res_whitespace, "STANDARD_CORPORATE")


class TestM1BankingDebtExtractionStress(unittest.TestCase):
    """Stress tests for BANKING_TAXONOMY_MAP['long_term_debt'] and debt extraction."""

    def test_banking_debt_tag_presence(self):
        """Assert all required tags exist in BANKING_TAXONOMY_MAP."""
        lt_tags = BANKING_TAXONOMY_MAP.get("long_term_debt", [])
        st_tags = BANKING_TAXONOMY_MAP.get("short_term_interbank", [])

        # Critical JPM tag
        self.assertIn("LongTermDebtAndCapitalLeaseObligationsIncludingCurrentMaturities", lt_tags)
        self.assertIn("Borrowings", lt_tags)
        self.assertIn("LongTermDebtNoncurrent", lt_tags)
        self.assertIn("LongTermDebt", lt_tags)

        # ST interbank / repo tags
        self.assertIn("RepurchaseAgreements", st_tags)
        self.assertIn("FederalFundsPurchasedAndSecuritiesSoldUnderAgreementsToRepurchase", st_tags)

    def test_extract_canonical_summary_banking_debt_scenarios(self):
        """
        Stress-test extract_canonical_summary under diverse debt configurations:
        - Scenario 1: Only LT debt present (no ST repo).
        - Scenario 2: Only ST repo present (no LT debt).
        - Scenario 3: Both LT debt and ST repo present.
        - Scenario 4: Both LT and ST debt are zero.
        - Scenario 5: Missing debt tags completely (None).
        """
        periods = ["FY2025"]

        # Base financial components (minimal balance sheet and P&L)
        base_bal = {
            "Assets": {"FY2025": 10000.0},
            "Liabilities": {"FY2025": 8000.0},
            "StockholdersEquity": {"FY2025": 2000.0},
            "CashAndCashEquivalents": {"FY2025": 500.0},
            "DepositsFromCustomers": {"FY2025": 6000.0},
            "LoansAndAdvancesToCustomers": {"FY2025": 7000.0},
        }
        base_inc = {
            "NetInterestIncome": {"FY2025": 400.0},
            "NoninterestIncome": {"FY2025": 200.0},
            "TotalOperatingExpenses": {"FY2025": 300.0},
            "NetIncomeLoss": {"FY2025": 250.0},
        }
        base_cf = {
            "NetCashProvidedByUsedInOperatingActivities": {"FY2025": 350.0},
        }

        # --- Scenario 1: Only LT debt present ---
        bal_sc1 = {**base_bal, "LongTermDebtAndCapitalLeaseObligationsIncludingCurrentMaturities": {"FY2025": 435206.0}}
        canon_sc1, _ = extract_canonical_summary(
            _wrap_concept_data(base_inc),
            _wrap_concept_data(bal_sc1),
            _wrap_concept_data(base_cf),
            periods,
            archetype="FINANCIAL_BANKING"
        )
        self.assertEqual(canon_sc1["borrowings"]["FY2025"], 435206.0)
        self.assertEqual(canon_sc1["repurchase_agreements"]["FY2025"], 0.0)
        self.assertEqual(canon_sc1["total_debt"]["FY2025"], 435206.0)
        self.assertEqual(canon_sc1["net_debt"]["FY2025"], round(435206.0 - 500.0, 2))

        # --- Scenario 2: Only ST repo present ---
        bal_sc2 = {**base_bal, "RepurchaseAgreements": {"FY2025": 64776.0}}
        canon_sc2, _ = extract_canonical_summary(
            _wrap_concept_data(base_inc),
            _wrap_concept_data(bal_sc2),
            _wrap_concept_data(base_cf),
            periods,
            archetype="FINANCIAL_BANKING"
        )
        self.assertEqual(canon_sc2["borrowings"]["FY2025"], 0.0)
        self.assertEqual(canon_sc2["repurchase_agreements"]["FY2025"], 64776.0)
        self.assertEqual(canon_sc2["total_debt"]["FY2025"], 64776.0)

        # --- Scenario 3: Both LT and ST debt present ---
        bal_sc3 = {
            **base_bal,
            "LongTermDebtAndCapitalLeaseObligationsIncludingCurrentMaturities": {"FY2025": 435206.0},
            "RepurchaseAgreements": {"FY2025": 64776.0}
        }
        canon_sc3, _ = extract_canonical_summary(
            _wrap_concept_data(base_inc),
            _wrap_concept_data(bal_sc3),
            _wrap_concept_data(base_cf),
            periods,
            archetype="FINANCIAL_BANKING"
        )
        self.assertEqual(canon_sc3["borrowings"]["FY2025"], 435206.0)
        self.assertEqual(canon_sc3["repurchase_agreements"]["FY2025"], 64776.0)
        self.assertEqual(canon_sc3["total_debt"]["FY2025"], 499982.0)

        # --- Scenario 4: Both LT and ST debt are zero ---
        bal_sc4 = {
            **base_bal,
            "Borrowings": {"FY2025": 0.0},
            "RepurchaseAgreements": {"FY2025": 0.0}
        }
        canon_sc4, _ = extract_canonical_summary(
            _wrap_concept_data(base_inc),
            _wrap_concept_data(bal_sc4),
            _wrap_concept_data(base_cf),
            periods,
            archetype="FINANCIAL_BANKING"
        )
        self.assertEqual(canon_sc4["borrowings"]["FY2025"], 0.0)
        self.assertEqual(canon_sc4["repurchase_agreements"]["FY2025"], 0.0)
        self.assertEqual(canon_sc4["total_debt"]["FY2025"], 0.0)

        # --- Scenario 5: Missing debt tags completely ---
        canon_sc5, _ = extract_canonical_summary(
            _wrap_concept_data(base_inc),
            _wrap_concept_data(base_bal),
            _wrap_concept_data(base_cf),
            periods,
            archetype="FINANCIAL_BANKING"
        )
        self.assertEqual(canon_sc5["borrowings"]["FY2025"], 0.0)
        self.assertEqual(canon_sc5["repurchase_agreements"]["FY2025"], 0.0)
        self.assertEqual(canon_sc5["total_debt"]["FY2025"], 0.0)

    def test_banking_negative_debt_propagation_anomaly(self):
        """
        Adversarial Edge Case: Negative debt in banking balance sheet.
        In extract_canonical_summary, unlike expenses, debt items are not normalized with abs().
        Verifies that negative debt propagates directly into total_debt.
        """
        periods = ["FY2025"]
        base_bal = {
            "Assets": {"FY2025": 5000.0},
            "Liabilities": {"FY2025": 4000.0},
            "StockholdersEquity": {"FY2025": 1000.0},
            "Borrowings": {"FY2025": -500.0}
        }
        base_inc = {"NetIncomeLoss": {"FY2025": 100.0}}
        base_cf = {"NetCashProvidedByUsedInOperatingActivities": {"FY2025": 100.0}}

        canon, _ = extract_canonical_summary(
            _wrap_concept_data(base_inc),
            _wrap_concept_data(base_bal),
            _wrap_concept_data(base_cf),
            periods,
            archetype="FINANCIAL_BANKING"
        )
        # Empirical finding: negative debt is not clamped to 0 or absolute-valued
        self.assertEqual(canon["borrowings"]["FY2025"], -500.0)
        self.assertEqual(canon["total_debt"]["FY2025"], -500.0)

    def test_each_individual_banking_lt_debt_candidate(self):
        """Stress-test that EVERY tag in BANKING_TAXONOMY_MAP['long_term_debt'] successfully extracts debt."""
        periods = ["FY2025"]
        base_bal = {
            "Assets": {"FY2025": 5000.0},
            "Liabilities": {"FY2025": 4000.0},
            "StockholdersEquity": {"FY2025": 1000.0},
        }
        base_inc = {"NetIncomeLoss": {"FY2025": 100.0}}
        base_cf = {"NetCashProvidedByUsedInOperatingActivities": {"FY2025": 100.0}}

        test_val = 12345.67
        for tag in BANKING_TAXONOMY_MAP["long_term_debt"]:
            bal_data = {**base_bal, tag: {"FY2025": test_val}}
            canon, _ = extract_canonical_summary(
                _wrap_concept_data(base_inc),
                _wrap_concept_data(bal_data),
                _wrap_concept_data(base_cf),
                periods,
                archetype="FINANCIAL_BANKING"
            )
            self.assertEqual(
                canon["borrowings"]["FY2025"],
                test_val,
                f"Failed to extract long-term debt via tag: {tag}"
            )
            self.assertEqual(
                canon["total_debt"]["FY2025"],
                test_val,
                f"Failed to propagate total debt via tag: {tag}"
            )

    def test_each_individual_banking_st_debt_candidate(self):
        """Stress-test that EVERY tag in BANKING_TAXONOMY_MAP['short_term_interbank'] successfully extracts debt."""
        periods = ["FY2025"]
        base_bal = {
            "Assets": {"FY2025": 5000.0},
            "Liabilities": {"FY2025": 4000.0},
            "StockholdersEquity": {"FY2025": 1000.0},
        }
        base_inc = {"NetIncomeLoss": {"FY2025": 100.0}}
        base_cf = {"NetCashProvidedByUsedInOperatingActivities": {"FY2025": 100.0}}

        test_val = 7890.12
        for tag in BANKING_TAXONOMY_MAP["short_term_interbank"]:
            bal_data = {**base_bal, tag: {"FY2025": test_val}}
            canon, _ = extract_canonical_summary(
                _wrap_concept_data(base_inc),
                _wrap_concept_data(bal_data),
                _wrap_concept_data(base_cf),
                periods,
                archetype="FINANCIAL_BANKING"
            )
            self.assertEqual(
                canon["repurchase_agreements"]["FY2025"],
                test_val,
                f"Failed to extract repo/interbank debt via tag: {tag}"
            )
            self.assertEqual(
                canon["total_debt"]["FY2025"],
                test_val,
                f"Failed to propagate total debt via tag: {tag}"
            )


class TestM1ControlCompaniesAndTargets(unittest.TestCase):
    """Zero regression verification on control issuers (AAPL, DECK) and milestone targets (JPM, MELI, O)."""

    def test_control_company_aapl_integrity(self):
        """Verify AAPL processed dataset has valid corporate archetype and debt figures."""
        aapl_path = PROJECT_ROOT / "data" / "processed" / "AAPL" / "financial_statements.json"
        self.assertTrue(aapl_path.exists(), "AAPL financial_statements.json must exist")
        with open(aapl_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        archetype = data.get("archetype") or data.get("company_profile", {}).get("archetype")
        self.assertIn(archetype, CORPORATE_ARCHETYPE_ALIASES)
        self.assertEqual(normalize_archetype(archetype), "STANDARD_CORPORATE")

        canon = data.get("canonical_summary", {})
        self.assertIn("total_debt", canon)
        fy25_debt = canon["total_debt"].get("FY2025")
        self.assertIsNotNone(fy25_debt)
        self.assertGreater(fy25_debt, 50000000000.0, "AAPL FY2025 debt should be > $50B in base dollars")

        # Verify audit engine pass rate
        report = run_full_audit("AAPL")
        self.assertEqual(report.get("overall_status"), "PASS")
        self.assertEqual(report.get("failed_tests"), 0)
        self.assertEqual(report.get("compliance_score_pct"), 100.0)

    def test_control_company_deck_integrity(self):
        """Verify DECK processed dataset has valid corporate archetype and zero debt / pristine balance sheet."""
        deck_path = PROJECT_ROOT / "data" / "processed" / "DECK" / "financial_statements.json"
        self.assertTrue(deck_path.exists(), "DECK financial_statements.json must exist")
        with open(deck_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        archetype = data.get("archetype") or data.get("company_profile", {}).get("archetype")
        self.assertIn(archetype, CORPORATE_ARCHETYPE_ALIASES)
        self.assertEqual(normalize_archetype(archetype), "STANDARD_CORPORATE")

        # Verify audit engine pass rate
        report = run_full_audit("DECK")
        self.assertEqual(report.get("overall_status"), "PASS")
        self.assertEqual(report.get("failed_tests"), 0)
        self.assertEqual(report.get("compliance_score_pct"), 100.0)

    def test_target_company_jpm_debt_integrity(self):
        """Verify JPM banking debt is extracted at audited ~$500,000M level ($499.982B base USD)."""
        jpm_path = PROJECT_ROOT / "data" / "processed" / "JPM" / "financial_statements.json"
        self.assertTrue(jpm_path.exists(), "JPM financial_statements.json must exist")
        with open(jpm_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        archetype = data.get("archetype") or data.get("company_profile", {}).get("archetype")
        self.assertEqual(archetype, "FINANCIAL_BANKING")

        canon = data.get("canonical_summary", {})
        fy25_debt = canon.get("total_debt", {}).get("FY2025")
        fy25_borrowings = canon.get("borrowings", {}).get("FY2025")
        fy25_repo = canon.get("repurchase_agreements", {}).get("FY2025")

        self.assertIsNotNone(fy25_debt)
        # $499,982,000,000.0 (~$500B / ~$500,000M)
        self.assertAlmostEqual(fy25_debt, 499982000000.0, delta=100000000.0)
        self.assertAlmostEqual(fy25_borrowings, 435206000000.0, delta=100000000.0)
        self.assertAlmostEqual(fy25_repo, 64776000000.0, delta=100000000.0)

        # LTM debt check ($532,953,000,000.0)
        ltm_debt = canon.get("total_debt", {}).get("LTM")
        self.assertIsNotNone(ltm_debt)
        self.assertGreater(ltm_debt, 500000000000.0)

    def test_target_company_meli_pnl_sign_integrity(self):
        """Verify MELI P&L magnitudes are positive and Gross Profit identity holds purely."""
        meli_path = PROJECT_ROOT / "data" / "processed" / "MELI" / "financial_statements.json"
        self.assertTrue(meli_path.exists(), "MELI financial_statements.json must exist")
        with open(meli_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        archetype = data.get("archetype") or data.get("company_profile", {}).get("archetype")
        self.assertEqual(archetype, "PLATFORM_ECOSYSTEM")

        canon = data.get("canonical_summary", {})
        rev_fy25 = canon.get("revenue", {}).get("FY2025")
        cogs_fy25 = canon.get("cost_of_goods_sold", {}).get("FY2025")
        gp_fy25 = canon.get("gross_profit", {}).get("FY2025")

        self.assertIsNotNone(rev_fy25)
        self.assertIsNotNone(cogs_fy25)
        self.assertIsNotNone(gp_fy25)

        # All must be strictly positive ($28.893B, $16.035B, $12.858B)
        self.assertGreater(rev_fy25, 0.0)
        self.assertGreater(cogs_fy25, 0.0)
        self.assertGreater(gp_fy25, 0.0)

        # Pure identity check
        self.assertEqual(round(rev_fy25 - cogs_fy25, 2), round(gp_fy25, 2))

        # Audit engine check: 100% compliance
        report = run_full_audit("MELI")
        self.assertEqual(report.get("overall_status"), "PASS")
        self.assertEqual(report.get("failed_tests"), 0)
        self.assertEqual(report.get("compliance_score_pct"), 100.0)

    def test_target_company_realty_income_capex_decoupling(self):
        """Verify Realty Income (O) maintenance CapEx is decoupled from real estate acquisitions."""
        o_path = PROJECT_ROOT / "data" / "processed" / "O" / "financial_statements.json"
        self.assertTrue(o_path.exists(), "O financial_statements.json must exist")
        with open(o_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        archetype = data.get("archetype") or data.get("company_profile", {}).get("archetype")
        self.assertEqual(archetype, "REAL_ESTATE_REIT")

        canon = data.get("canonical_summary", {})
        fy25_capex = canon.get("capital_expenditures", {}).get("FY2025")
        fy25_acq = canon.get("real_estate_acquisitions", {}).get("FY2025")
        fy25_ffo = canon.get("ffo", {}).get("FY2025")
        fy25_affo = canon.get("affo", {}).get("FY2025")

        self.assertIsNotNone(fy25_capex)
        self.assertIsNotNone(fy25_acq)
        self.assertIsNotNone(fy25_ffo)
        self.assertIsNotNone(fy25_affo)

        # Maintenance CapEx should be around $131.8M ($131,800,000), acquisitions around $4,647M ($4,647,450,000)
        self.assertAlmostEqual(fy25_capex, 131800000.0, delta=100000.0)
        self.assertGreater(fy25_acq, 4000000000.0)

        # AFFO = FFO - CapEx
        self.assertEqual(round(fy25_ffo - fy25_capex, 2), round(fy25_affo, 2))

        # Audit engine check: 100% compliance
        report = run_full_audit("O")
        self.assertEqual(report.get("overall_status"), "PASS")
        self.assertEqual(report.get("failed_tests"), 0)
        self.assertEqual(report.get("compliance_score_pct"), 100.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
