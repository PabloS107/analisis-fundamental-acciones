# -*- coding: utf-8 -*-
"""
canonical_resolvers.py — Motor Canónico Unificado (SSOT) del Pipeline.
Resuelve e integra el Estado de Resultados, Balance General, Estado de Flujos de Caja
y Flujos de Asignación de Capital en todas las empresas y arquetipos contables.
"""

import logging

logger = logging.getLogger(__name__)

_SECTION_DETAIL_MAP = {
    "income": "income_statement_detail",
    "balance": "balance_sheet_detail",
    "cashflow": "cash_flow_detail",
}

_SECTION_AS_REPORTED_MAP = {
    "income": "income_statement",
    "balance": "balance_sheet",
    "cashflow": "cash_flow_statement",
}

_CAPITAL_FLOW_KEYS = {
    "repurchases": [
        "PaymentsForRepurchaseOfCommonStock",
        "PaymentsForRepurchaseOfEquity",
        "PaymentsForRepurchaseOfCapitalStock",
        "PurchaseOfTreasuryShares",
        "PaymentsForPurchaseOfOwnShares",
        "PaymentsForRepurchaseOfShares",
        "PurchaseOfOwnShares",
        "SharesRepurchased",
        "nu_SharesRepurchased",
    ],
    "stock_plans": [
        "ProceedsFromStockPlans",
        "us-gaap_ProceedsFromStockPlans",
        "ProceedsFromStockOptionsExercised",
        "us-gaap_ProceedsFromStockOptionsExercised",
        "ProceedsFromIssuanceOfCommonStock",
        "us-gaap_ProceedsFromIssuanceOfCommonStock",
        "ProceedsFromIssuanceOfShares",
        "ifrs-full_ProceedsFromIssuingShares",
        "ProceedsFromIssuanceOfSharesUnderIncentiveAndShareBasedCompensationPlansIncludingStockOptions",
        "us-gaap_ProceedsFromIssuanceOfSharesUnderIncentiveAndShareBasedCompensationPlansIncludingStockOptions",
        "Netproceedspaymentsrelatedtoemployeestockplans",
        "nvda_Netproceedspaymentsrelatedtoemployeestockplans",
        "ProceedsFromIssuanceOfConvertiblePreferredStock",
        "us-gaap_ProceedsFromIssuanceOfConvertiblePreferredStock",
        "o_ProceedsFromDividendReinvestmentAndStockPurchasePlanNet",
        "ProceedsFromDividendReinvestmentAndStockPurchasePlanNet",
    ],
    "tax_withholding": [
        "PaymentsRelatedToTaxWithholdingForShareBasedCompensation",
        "TaxWithholdingForShareBasedCompensation",
        "PaymentsForTaxWithholdingShareBasedCompensation",
        "meta_TaxesPaidRelatedToNetShareSettlementOfEquityAwards",
        "us-gaap_PaymentsRelatedToTaxWithholdingForShareBasedCompensation",
    ],
    "dividends": [
        "PaymentsOfDividendsCommonStock",
        "PaymentsOfDividends",
        "DividendsPaid",
        "PaymentsOfOrdinaryDividends",
        "PaymentsOfDividendsMinorityInterest",
        "ifrs-full_DividendsPaidClassifiedAsFinancingActivities",
        "us-gaap_PaymentsOfDividendsCommonStock",
        "DividendsCommonStockCash",
        "us-gaap_DividendsCommonStockCash",
        "PaymentsOfDividendsPreferredStockAndPreferenceStock",
        "o_DividendsPaidToCommonStockholders",
    ],
    "acquisitions_ma": [
        "AcquisitionsNetOfCashAcquiredAndPurchasesOfIntangibleAndOtherAssets",
        "goog_AcquisitionsNetOfCashAcquiredAndPurchasesOfIntangibleAndOtherAssets",
        "goog:AcquisitionsNetOfCashAcquiredAndPurchasesOfIntangibleAndOtherAssets",
        "AcquisitionsNetOfCashAcquiredAndPurchasesOfIntangibleAssets",
        "PaymentsToAcquireBusinessesNetOfCashAcquiredAndPurchasesOfIntangibleAndOtherAssets",
        "PaymentsToAcquireBusinessesNetOfCashAcquired",
        "PaymentsToAcquireBusinessTwoNetOfCashAcquired",
        "us-gaap_PaymentsToAcquireBusinessTwoNetOfCashAcquired",
        "PaymentsToAcquireBusinessThreeNetOfCashAcquired",
        "AcquisitionOfSubsidiaryNetOfCashAcquired",
        "nu_AcquisitionOfSubsidiaryNetOfCashAcquired",
        "PaymentsToAcquireBusinessesAndInterestInAffiliates",
        "PaymentsToAcquireOtherProductiveAssets",
        "CashFlowsUsedInObtainingControlOfSubsidiariesOrOtherBusinesses",
        "PaymentsToAcquireBusinessesGross",
        "meli_PaymentsToAcquireBusinessNetOfCashAcquired",
        "us-gaap_PaymentsToAcquireBusinessesAndInterestInAffiliates",
        "meta_PaymentsToAcquireBusinessesNetOfCashAcquiredAndPurchasesOfIntangibleAndOtherAssets",
        "PaymentsToAcquireInterestInAffiliates",
        "PaymentsToAcquireInterestInSubsidiariesAndOtherBusinesses",
        "PaymentsToAcquireJointVentures",
        "PaymentsToAcquireCommercialRealEstate",
        "us-gaap_PaymentsToAcquireCommercialRealEstate",
        "PaymentsToAcquireLoansReceivable",
        "us-gaap_PaymentsToAcquireLoansReceivable",
        "PaymentsToAcquireInterestInSubsidiariesAndAffiliates",
    ],
    "debt_repayments": [
        "RepaymentsOfLongTermDebt",
        "RepaymentsOfDebt",
        "us-gaap_RepaymentsOfDebt",
        "RepaymentsOfLinesOfCredit",
        "RepaymentsOfShortTermDebt",
        "us-gaap_RepaymentsOfShortTermDebt",
        "RepaymentsOfOtherLongTermDebt",
        "us-gaap_RepaymentsOfOtherLongTermDebt",
        "RepaymentsOfSecuredDebt",
        "us-gaap_RepaymentsOfSecuredDebt",
        "RepaymentsOfUnsecuredDebt",
        "us-gaap_RepaymentsOfUnsecuredDebt",
        "us-gaap_RepaymentsOfConvertibleDebt",
        "RepaymentsOfBorrowingsClassifiedAsFinancingActivities",
        "PaymentsOfBorrowingsAndFinancing",
        "RepaymentsOfTermLoans",
        "RepaymentsOfConvertibleDebt",
        "RepaymentsOfSeniorNotes",
        "RepaymentsOfNotesPayable",
        "us-gaap_RepaymentsOfNotesPayable",
        "RepaymentsOfLongTermDebtAndCapitalSecurities",
        "us-gaap_RepaymentsOfLongTermDebtAndCapitalSecurities",
        "RepaymentsOfLongTermLinesOfCreditAndCommercialPaper",
        "o_RepaymentsOfLongTermLinesOfCreditAndCommercialPaper",
        "FinanceLeasePrincipalPayments",
        "us-gaap_FinanceLeasePrincipalPayments",
        "PaymentsOfLeaseLiabilities",
        "nvda_PaymentsForFinancedPropertyPlantAndEquipmentAndIntangibleAssetsFinancingActivities",
        "PaymentsForFinancedPropertyPlantAndEquipmentAndIntangibleAssetsFinancingActivities",
    ],
    "debt_issuances": [
        "ProceedsFromIssuanceOfLongTermDebt",
        "ProceedsFromIssuanceOfDebt",
        "ProceedsFromIssuanceOfSeniorLongTermDebt",
        "us-gaap_ProceedsFromIssuanceOfSeniorLongTermDebt",
        "ProceedsFromIssuanceOfUnsecuredDebt",
        "us-gaap_ProceedsFromIssuanceOfUnsecuredDebt",
        "us-gaap_ProceedsFromDebtNetOfIssuanceCosts",
        "ProceedsFromLinesOfCredit",
        "ProceedsFromIssuanceOfOtherLongTermDebt",
        "us-gaap_ProceedsFromIssuanceOfOtherLongTermDebt",
        "ProceedsFromBorrowingsClassifiedAsFinancingActivities",
        "ProceedsFromBorrowingsAndFinancing",
        "us-gaap_ProceedsFromConvertibleDebt",
        "us-gaap_ProceedsFromShortTermDebt",
        "nu_ProceedsFromDebtInstrumentsEligibleAsCapital",
        "ProceedsFromTermLoans",
        "ProceedsFromConvertibleDebt",
        "ProceedsFromIssuanceOfConvertibleDebt",
        "ProceedsFromIssuanceOfSeniorNotes",
        "ProceedsFromLongTermLinesOfCredit",
        "ProceedsFromNotesPayable",
        "us-gaap_ProceedsFromNotesPayable",
        "ProceedsFromIssuanceOfLongTermDebtAndCapitalSecuritiesNet",
        "us-gaap_ProceedsFromIssuanceOfLongTermDebtAndCapitalSecuritiesNet",
        "o_ProceedsFromLongTermLinesOfCreditAndIssuanceOfCommercialPaper",
        "ProceedsFromLongTermLinesOfCreditAndIssuanceOfCommercialPaper",
    ],
}

_BS_CONCEPT_KEYS = {
    "cash": [
        "CashAndCashEquivalentsAtCarryingValue",
        "CashAndCashEquivalents",
        "Cash",
        "CashAndDueFromBanks",
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
        "us-gaap_CashAndCashEquivalentsAtCarryingValue",
        "ifrs-full_CashAndCashEquivalents",
    ],
    "sti": [
        "MarketableSecuritiesCurrent",
        "us-gaap_MarketableSecuritiesCurrent",
        "ShortTermInvestments",
        "AvailableForSaleSecuritiesCurrent",
        "DebtSecuritiesCurrent",
        "us-gaap_DebtSecuritiesCurrent",
        "EquitySecuritiesFvNi",
        "us-gaap_EquitySecuritiesFvNi",
        "nvda_MarketableSecuritiesAndEquitySecuritiesFVNI",
        "OtherShortTermInvestments",
        "MarketableSecurities",
    ],
    "ar": [
        "AccountsReceivableNetCurrent",
        "AccountsReceivableNet",
        "ReceivablesNetCurrent",
        "AccountsAndNotesReceivableNetCurrent",
        "TradeAndOtherReceivablesCurrent",
        "ContractWithCustomerAssetNetCurrent",
        "UnbilledReceivablesCurrent",
        "NontradeReceivablesCurrent",
        "us-gaap_AccountsReceivableNetCurrent",
    ],
    "inv": ["InventoryNet", "Inventories", "InventoryGross", "us-gaap_InventoryNet"],
    "ca": ["AssetsCurrent", "CurrentAssetsTotal", "CurrentAssets", "us-gaap_AssetsCurrent"],
    "other_ca": [
        "PrepaidExpenseAndOtherAssetsCurrent",
        "us-gaap_PrepaidExpenseAndOtherAssetsCurrent",
        "OtherAssetsCurrent",
        "us-gaap_OtherAssetsCurrent",
        "PrepaidExpensesAndOtherCurrentAssets",
        "OtherCurrentAssets",
    ],
    "ppe": [
        "RealEstateInvestmentPropertyNet",
        "us-gaap_RealEstateInvestmentPropertyNet",
        "InvestmentProperties",
        "PropertyPlantAndEquipmentNet",
        "PropertyPlantAndEquipmentAndFinanceLeaseRightOfUseAssetAfterAccumulatedDepreciationAndAmortization",
        "PropertyPlantAndEquipmentNetOfAccumulatedDepreciationAndAmortization",
        "PropertyPlantAndEquipmentNetExcludingRightOfUseAsset",
        "PropertyPlantAndEquipmentGross",
        "MachineryAndEquipmentNet",
        "ConstructionInProgressGross",
        "ConstructionInProgress",
        "BuildingsAndBuildingImprovementsNet",
        "us-gaap_PropertyPlantAndEquipmentNet",
    ],
    "rou": [
        "OperatingLeaseRightOfUseAsset",
        "us-gaap_OperatingLeaseRightOfUseAsset",
        "RightOfUseAssets",
        "RightOfUseAsset",
        "FinanceLeaseRightOfUseAsset",
        "LesseeOperatingLeaseRightOfUseAsset",
        "OperatingLeaseRightOfUseAssetNet",
        "FinanceLeaseRightOfUseAssetNet",
    ],
    "gw": ["Goodwill", "us-gaap_Goodwill"],
    "intang": [
        "IntangibleAssetsNetExcludingGoodwill",
        "IntangibleAssetsNet",
        "OtherIntangibleAssetsNet",
        "us-gaap_IntangibleAssetsNetExcludingGoodwill",
        "IntangibleAssetsNetExcludingGoodwillNoncurrent",
        "us-gaap_IntangibleAssetsNetExcludingGoodwillNoncurrent",
        "IntangibleAssetsNetNoncurrent",
        "us-gaap_IntangibleAssetsNetNoncurrent",
        "IntangibleAssetsOtherThanGoodwill",
        "ifrs-full_IntangibleAssetsOtherThanGoodwill",
    ],
    "lt_inv": [
        "MarketableSecuritiesNoncurrent",
        "us-gaap_MarketableSecuritiesNoncurrent",
        "NonmarketableEquitySecuritiesCarryingValue",
        "meta_NonmarketableEquitySecuritiesCarryingValue",
        "EquitySecuritiesWithoutReadilyDeterminableFairValueAmount",
        "EquitySecuritiesFVNINoncurrent",
        "us-gaap_EquitySecuritiesFVNINoncurrent",
        "LongTermInvestments",
        "us-gaap_LongTermInvestments",
        "OtherInvestmentsNoncurrent",
        "InvestmentsInAssociates",
        "InvestmentsInAffiliatesSubsidiariesAssociatesAndJointVentures",
        "EquityMethodInvestments",
        "AvailableForSaleDebtSecuritiesNoncurrent",
        "HeldToMaturitySecuritiesNoncurrent",
        "OtherLongTermInvestments",
        "OtherInvestments",
    ],
    "other_nca": ["OtherAssetsNoncurrent", "us-gaap_OtherAssetsNoncurrent", "OtherNoncurrentAssets"],
    "dta": [
        "DeferredIncomeTaxAssetsNet",
        "us-gaap_DeferredIncomeTaxAssetsNet",
        "DeferredTaxAssetsNetNoncurrent",
        "us-gaap_DeferredTaxAssetsNetNoncurrent",
        "DeferredIncomeTaxAssets",
        "us-gaap_DeferredIncomeTaxAssets",
    ],
    "ta": ["Assets", "TotalAssets", "us-gaap_Assets"],
    "ap": [
        "AccountsPayableCurrent",
        "us-gaap_AccountsPayableCurrent",
        "us-gaap_AccountsPayableTradeCurrent",
        "AccountsPayableTradeCurrent",
        "us-gaap_AccountsPayableAndAccruedLiabilitiesCurrent",
        "TradeAndOtherPayablesCurrent",
    ],
    "accrued": [
        "AccruedLiabilitiesCurrent",
        "us-gaap_AccruedLiabilitiesCurrent",
        "OtherAccruedLiabilitiesCurrent",
        "AccruedLiabilities",
    ],
    "st_debt": [
        "LongTermDebtCurrent",
        "us-gaap_LongTermDebtCurrent",
        "CommercialPaper",
        "us-gaap_CommercialPaper",
        "CurrentPortionOfLongTermDebt",
        "ShortTermDebt",
        "ShortTermBorrowings",
        "DebtCurrent",
        "us-gaap_DebtCurrent",
        "LoansPayableCurrent",
        "us-gaap_LoansPayableCurrent",
        "LinesOfCreditCurrent",
        "RevolvingCreditFacilityAndCommercialPaper",
        "LineOfCreditAndCommercialPaper",
        "LineOfCredit",
        "CurrentBorrowingsAndOtherFinancialLiabilities",
        "CurrentPortionOfNoncurrentBorrowings",
        "CurrentFinancialLiabilities",
        "BorrowingsFromFinancialInstitutions",
    ],
    "cl": ["LiabilitiesCurrent", "CurrentLiabilitiesTotal", "CurrentLiabilities", "us-gaap_LiabilitiesCurrent"],
    "tot_debt": ["DebtLongtermAndShorttermCombinedAmount", "us-gaap_DebtLongtermAndShorttermCombinedAmount", "TotalDebt"],
    "lt_debt": [
        "LongTermDebtNoncurrent",
        "us-gaap_LongTermDebtNoncurrent",
        "LongTermDebtAndCapitalLeaseObligationsNoncurrent",
        "LongTermDebt",
        "NotesPayable",
        "LoansPayable",
        "SecuredDebt",
        "SeniorNotes",
        "SeniorLongTermDebt",
        "NoncurrentBorrowings",
        "NoncurrentFinancialLiabilities",
        "DebtSecuritiesInIssue",
        "Borrowings",
        "BorrowingsAndFinancing",
        "SubordinatedDebt",
    ],
    "lease_liab_nc": [
        "OperatingLeaseLiabilityNoncurrent",
        "us-gaap_OperatingLeaseLiabilityNoncurrent",
        "CapitalLeaseObligationsNoncurrent",
    ],
    "tl": ["Liabilities", "TotalLiabilities", "us-gaap_Liabilities"],
    "mezz_eq": [
        "RedeemableNoncontrollingInterestEquityCarryingAmount",
        "us-gaap_RedeemableNoncontrollingInterestEquityCarryingAmount",
        "RedeemableNoncontrollingInterestEquityPreferred",
        "us-gaap_RedeemableNoncontrollingInterestEquityPreferred",
        "TemporaryEquityCarryingAmountAttributableToParent",
        "us-gaap_TemporaryEquityCarryingAmountAttributableToParent",
        "TemporaryEquityCarryingAmountIncludingPortionAttributableToNoncontrollingInterests",
        "us-gaap_TemporaryEquityCarryingAmountIncludingPortionAttributableToNoncontrollingInterests",
    ],
    "eq": [
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
        "ifrs-full_Equity",
        "StockholdersEquity",
        "TotalEquity",
        "Equity",
        "us-gaap_StockholdersEquity",
        "EquityAttributableToOwnersOfParent",
    ],
    "apic": [
        "CommonStocksIncludingAdditionalPaidInCapital",
        "us-gaap_CommonStocksIncludingAdditionalPaidInCapital",
        "CommonStocksAndAdditionalPaidInCapital",
    ],
    "re": [
        "RetainedEarningsAccumulatedDeficit",
        "RetainedEarnings",
        "us-gaap_RetainedEarningsAccumulatedDeficit",
        "ifrs-full_RetainedEarnings",
        "nu_AccumulatedGains",
        "nu_AccumulatedGainLosses",
        "AccumulatedLosses",
        "nu_TotalAccumulatedLosses",
    ],
    "def_rev": [
        "DeferredRevenueCurrent",
        "us-gaap_DeferredRevenueCurrent",
        "ContractWithCustomerLiabilityCurrent",
        "us-gaap_ContractWithCustomerLiabilityCurrent",
        "DeferredRevenueAndOtherCurrentLiabilities",
        "us-gaap_DeferredRevenueAndOtherCurrentLiabilities",
    ],
    "def_tax_nc": [
        "DeferredTaxLiabilitiesNoncurrent",
        "us-gaap_DeferredTaxLiabilitiesNoncurrent",
        "DeferredIncomeTaxLiabilitiesNetNoncurrent",
        "us-gaap_DeferredIncomeTaxLiabilitiesNetNoncurrent",
        "DeferredIncomeTaxesAndOtherLiabilitiesNoncurrent",
    ],
    "net_loans": [
        "LoansAndLeasesReceivableNetOfDeferredIncome",
        "us-gaap_LoansAndLeasesReceivableNetOfDeferredIncome",
        "FinancingReceivableExcludingAccruedInterestAfterAllowanceForCreditLoss",
        "FinancingReceivableExcludingAccruedInterestBeforeAllowanceForCreditLossesNetOfDeferredIncome",
        "ifrs-full_LoansAndAdvancesToCustomers",
        "nu_CreditCardReceivables1",
        "nu_LoansAndAdvancesToCustomers1",
        "LoansAndLeasesReceivableNetReportedAmount",
        "LoansReceivableNet",
    ],
    "allow_loss": [
        "FinancingReceivableAllowanceForCreditLossExcludingAccruedInterest",
        "us-gaap_FinancingReceivableAllowanceForCreditLossExcludingAccruedInterest",
        "FinancingReceivableAllowanceForCreditLosses",
        "us-gaap_FinancingReceivableAllowanceForCreditLosses",
        "AllowanceForCreditLossesOnFinancingReceivables",
        "us-gaap_AllowanceForCreditLossesOnFinancingReceivables",
        "AllowanceAccountForCreditLossesOfFinancialAssets",
        "ifrs-full_AllowanceAccountForCreditLossesOfFinancialAssets",
        "LoansAndLeasesReceivableAllowance",
        "AllowanceForLoanAndLeaseLosses",
        "CreditCardExpectedCreditLoss",
        "LoansExpectedCreditLoss",
        "AllowanceForExpectedCreditLosses",
    ],
    "deposit": [
        "Deposits",
        "us-gaap_Deposits",
        "ifrs-full_DepositsFromCustomers",
        "DepositsDomestic",
        "InterestBearingDepositLiabilities",
        "NoninterestBearingDepositLiabilities",
    ],
    "prem_rec": [
        "PremiumsReceivableAtCarryingValue",
        "us-gaap_PremiumsReceivableAtCarryingValue",
        "AccountsAndOtherReceivablesNetCurrent",
        "AccountsReceivableNet",
    ],
    "dac": [
        "DeferredPolicyAcquisitionCosts",
        "us-gaap_DeferredPolicyAcquisitionCosts",
        "DeferredPolicyAcquisitionCostAmortizationExpense",
    ],
    "loss_res": [
        "LiabilityForClaimsAndClaimsAdjustmentExpense",
        "us-gaap_LiabilityForClaimsAndClaimsAdjustmentExpense",
        "LiabilityForUnpaidClaimsAndClaimsAdjustmentExpenseNet",
        "LiabilityForClaimsAndClaimsAdjustmentExpenseIncurredClaims1",
    ],
    "unearn_prem": ["UnearnedPremiums", "us-gaap_UnearnedPremiums", "UnearnedPremiumsNet"],
}


def _to_float(val, context=""):
    """Convierte a float registrando en debug si un concepto XBRL no es numérico."""
    try:
        return float(val)
    except (ValueError, TypeError) as exc:
        logger.debug("Valor no numérico ignorado en %s (%r): %s", context or "canonical_resolver", val, exc)
        return None


def _as_reported_concept_dict(fs, section_key):
    """Construye un mapa {concepto: values_dict} desde as_reported_statements."""
    as_rep_raw = fs.get("as_reported_statements", {}).get(section_key, []) if isinstance(fs, dict) else []
    as_rep_rows = as_rep_raw if isinstance(as_rep_raw, list) else (as_rep_raw.get("rows", []) if isinstance(as_rep_raw, dict) else [])
    concept_dict = {}
    for row in as_rep_rows:
        if isinstance(row, dict) and "concept" in row:
            concept_dict[row["concept"]] = row.get("values", {})
    return concept_dict


def _extract_from_single_source(src, key_cands, period):
    """Busca el primer candidato coincidente en un diccionario fuente para un período."""
    if not isinstance(src, dict):
        return None
    for k in key_cands:
        k_lower = k.lower()
        if k in src:
            obj = src[k]
            vals = obj.get("values", obj) if isinstance(obj, dict) else {}
            if isinstance(vals, dict) and period in vals and vals[period] is not None:
                parsed = _to_float(vals[period], f"{k}:{period}")
                if parsed is not None:
                    return parsed
        for src_k, src_obj in src.items():
            src_token = src_k.lower().split(":")[-1].split("_")[-1]
            if src_k.lower() == k_lower or src_token == k_lower:
                vals = src_obj.get("values", src_obj) if isinstance(src_obj, dict) else {}
                if isinstance(vals, dict) and period in vals and vals[period] is not None:
                    parsed = _to_float(vals[period], f"{src_k}:{period}")
                    if parsed is not None:
                        return parsed
    return None


def _extract_capital_flow_val(canonical, cf_sources, key_cands, p, can_key=None):
    """Extrae un flujo individual priorizando canonical_summary no nulo y no cero."""
    if can_key:
        can_val = _to_float(canonical.get(can_key, {}).get(p), f"canonical.{can_key}:{p}")
        if can_val is not None and abs(can_val) > 0:
            return can_val
    for k in key_cands:
        for cf_src in cf_sources:
            val = _extract_from_single_source(cf_src, [k], p)
            if val is not None:
                return val
    return None


def _extract_capital_flow_sum(canonical, cf_sources, key_cands, p, can_key=None):
    """Suma candidatos deduplicados por token XBRL para adquisiciones o tramos de deuda."""
    if can_key:
        can_val = _to_float(canonical.get(can_key, {}).get(p), f"canonical.{can_key}:{p}")
        if can_val is not None and abs(can_val) > 0:
            return can_val
    total = 0.0
    matched = False
    matched_tokens = set()
    for k in key_cands:
        k_token = k.lower().split(":")[-1].split("_")[-1]
        for cf_src in cf_sources:
            if not isinstance(cf_src, dict):
                continue
            for src_k, src_obj in cf_src.items():
                src_token = src_k.lower().split(":")[-1].split("_")[-1]
                if (src_k.lower() == k.lower() or src_token == k_token) and src_token not in matched_tokens:
                    vals = src_obj.get("values", src_obj) if isinstance(src_obj, dict) else {}
                    if isinstance(vals, dict) and p in vals and vals[p] is not None:
                        num = _to_float(vals[p], f"{src_k}:{p}")
                        if num is not None:
                            total += num
                            matched = True
                            matched_tokens.add(src_token)
    return total if matched else None


def resolve_canonical_capital_flows(fs, periods):
    """
    Función canónica y unificada (SSOT) para resolver flujos de asignación de capital
    a partir de financial_statements.json de forma universal y sin hardcodeos.
    """
    canonical = fs.get("canonical_summary", {}) if isinstance(fs, dict) else {}
    as_rep_cf_dict = _as_reported_concept_dict(fs, "cash_flow_statement")
    cf_sources = [
        as_rep_cf_dict,
        fs.get("cash_flow_detail", {}) if isinstance(fs, dict) else {},
        fs.get("cash_flow_statement", {}) if isinstance(fs, dict) else {},
    ]

    flows = {
        "share_repurchases_open_market": {},
        "stock_plans_proceeds": {},
        "share_repurchases_net": {},
        "share_repurchases_sbc_tax": {},
        "share_repurchases_total": {},
        "total_capital_returned": {},
        "dividends_paid": {},
        "acquisitions_ma": {},
        "debt_repayments": {},
        "debt_issuances": {},
        "net_debt_change": {},
    }

    for p in periods:
        raw_rep = _extract_capital_flow_val(canonical, cf_sources, _CAPITAL_FLOW_KEYS["repurchases"], p, "share_repurchases")
        val_rep = abs(raw_rep) if raw_rep is not None else 0.0

        raw_sp = _extract_capital_flow_val(canonical, cf_sources, _CAPITAL_FLOW_KEYS["stock_plans"], p, "stock_plans_proceeds")
        val_sp = abs(raw_sp) if raw_sp is not None else 0.0
        val_net_rep = max(0.0, round(val_rep - val_sp, 2))

        raw_tax = _extract_capital_flow_val(canonical, cf_sources, _CAPITAL_FLOW_KEYS["tax_withholding"], p, "share_repurchases_sbc_tax")
        val_tax = abs(raw_tax) if raw_tax is not None else 0.0

        raw_div = _extract_capital_flow_val(canonical, cf_sources, _CAPITAL_FLOW_KEYS["dividends"], p, "dividends_paid")
        val_div = abs(raw_div) if raw_div is not None else 0.0

        raw_ma = _extract_capital_flow_sum(canonical, cf_sources, _CAPITAL_FLOW_KEYS["acquisitions_ma"], p, "acquisitions_ma")
        val_ma = abs(raw_ma) if raw_ma is not None else 0.0

        raw_dr = _extract_capital_flow_sum(canonical, cf_sources, _CAPITAL_FLOW_KEYS["debt_repayments"], p, "debt_repayments")
        val_dr = abs(raw_dr) if raw_dr is not None else 0.0

        raw_di = _extract_capital_flow_sum(canonical, cf_sources, _CAPITAL_FLOW_KEYS["debt_issuances"], p, "debt_issuances")
        val_di = abs(raw_di) if raw_di is not None else 0.0

        flows["share_repurchases_open_market"][p] = val_rep
        flows["stock_plans_proceeds"][p] = val_sp
        flows["share_repurchases_net"][p] = val_net_rep
        flows["share_repurchases_sbc_tax"][p] = val_tax
        flows["share_repurchases_total"][p] = round(val_rep + val_tax, 2)
        flows["total_capital_returned"][p] = val_net_rep
        flows["dividends_paid"][p] = val_div
        flows["acquisitions_ma"][p] = val_ma
        flows["debt_repayments"][p] = val_dr
        flows["debt_issuances"][p] = val_di
        flows["net_debt_change"][p] = round(val_di - val_dr, 2)

    return flows


def _detect_ltm_source_period(canonical, periods):
    """Detecta si LTM duplica el último FY cerrado para dirigir fallbacks as-reported."""
    fy_candidates = [p for p in periods if p != "LTM"]
    if "LTM" not in periods or not fy_candidates:
        return None

    def _fy_year(fp):
        try:
            return int(str(fp).replace("FY", ""))
        except ValueError:
            return -1

    fy_latest = max(fy_candidates, key=_fy_year)

    def _ltm_equals_fy(key):
        d = canonical.get(key, {})
        if not isinstance(d, dict):
            return False
        ltm_v = _to_float(d.get("LTM"), f"canonical.{key}:LTM")
        fy_v = _to_float(d.get(fy_latest), f"canonical.{key}:{fy_latest}")
        if ltm_v is None or fy_v is None:
            return False
        return abs(ltm_v - fy_v) < 1.0

    for probe_key in (
        "total_assets",
        "stockholders_equity",
        "current_assets",
        "current_liabilities",
        "total_debt",
        "revenue",
        "cash_and_equivalents",
    ):
        if _ltm_equals_fy(probe_key):
            return fy_latest
    return None


def _is_any_key_on_face(key_cands, face_dict):
    """Verifica si alguno de los conceptos candidatos figura en la carátula as-reported."""
    face_tokens = {c.lower().split(":")[-1].split("_")[-1] for c in face_dict}
    return any(k.lower().split(":")[-1].split("_")[-1] in face_tokens for k in key_cands)


def _resolve_bs_current_assets(fs, canonical, extract_val, p, archetype, ltm_source_period):
    """Resuelve caja, inversiones corrientes y activos corrientes cerrando sum(hijos) == CA."""
    c_v = extract_val(_BS_CONCEPT_KEYS["cash"], p, "cash_and_equivalents")
    if c_v is None or c_v == 0.0:
        c_cand = extract_val(["CashAndCashEquivalentsAtCarryingValue", "ifrs-full_CashAndCashEquivalents"], p)
        if c_cand and float(c_cand) > 0:
            c_v = float(c_cand)
        else:
            cdue = extract_val(["CashAndDueFromBanks", "us-gaap_CashAndDueFromBanks"], p) or 0.0
            cint = extract_val(["InterestBearingDepositsInBanks", "us-gaap_InterestBearingDepositsInBanks"], p) or 0.0
            if (cdue + cint) > 0:
                c_v = round(cdue + cint, 1)

    sti_v = extract_val(_BS_CONCEPT_KEYS["sti"], p, "short_term_investments")
    ltm_p_src = ltm_source_period if (p == "LTM" and ltm_source_period) else p
    for r_bs in (fs.get("as_reported_statements", {}).get("balance_sheet", []) if isinstance(fs, dict) else []):
        c_tok = str(r_bs.get("concept", "")).split(":")[-1].split("_")[-1].lower()
        if c_tok in ("marketablesecuritiescurrent", "shortterminvestments"):
            bs_val = r_bs.get("values", {}).get(ltm_p_src)
            if bs_val is not None and float(bs_val) > 0:
                if sti_v is None or abs(float(bs_val) - float(sti_v)) > 1000.0:
                    sti_v = float(bs_val)
            break

    if sti_v is None or sti_v == 0.0 or archetype in ("INSURANCE", "FINANCIAL_BANKING"):
        if archetype == "INSURANCE":
            tot_inv = canonical.get("total_investments", {}).get(p)
            if tot_inv is not None and float(tot_inv) > 0:
                sti_v = float(tot_inv)
            else:
                afs_sec = extract_val(["AvailableForSaleSecuritiesDebtSecurities", "us-gaap_AvailableForSaleSecuritiesDebtSecurities"], p) or 0.0
                eq_sec = extract_val(["EquitySecuritiesFvNi", "us-gaap_EquitySecuritiesFvNi"], p) or 0.0
                st_sec = extract_val(["ShortTermInvestments", "us-gaap_ShortTermInvestments"], p) or 0.0
                if (afs_sec + eq_sec + st_sec) > 0:
                    sti_v = round(afs_sec + eq_sec + st_sec, 1)
        elif archetype == "FINANCIAL_BANKING":
            jpm_sec = extract_val(["jpm_DebtSecuritiesNetCarryingAmount"], p)
            if jpm_sec and float(jpm_sec) > 0:
                sti_v = float(jpm_sec)
            else:
                afs_d = extract_val(["DebtSecuritiesAvailableForSaleExcludingAccruedInterest", "us-gaap_DebtSecuritiesAvailableForSaleExcludingAccruedInterest"], p) or 0.0
                htm_d = extract_val(["DebtSecuritiesHeldToMaturityExcludingAccruedInterestAfterAllowanceForCreditLoss", "us-gaap_DebtSecuritiesHeldToMaturityExcludingAccruedInterestAfterAllowanceForCreditLoss"], p) or 0.0
                if (afs_d + htm_d) > 0:
                    sti_v = round(afs_d + htm_d, 1)
                else:
                    nu_pnl = extract_val(["ifrs-full_FinancialAssetsAtFairValueThroughProfitOrLoss", "nu_Securities"], p) or 0.0
                    nu_oci = extract_val(["ifrs-full_FinancialAssetsAtFairValueThroughOtherComprehensiveIncome", "nu_OtherSecurities"], p) or 0.0
                    if (nu_pnl + nu_oci) > 0:
                        sti_v = round(nu_pnl + nu_oci, 1)
        else:
            st_debt_cand = extract_val(["DebtSecuritiesCurrent", "us-gaap_DebtSecuritiesCurrent"], p)
            st_eq_cand = extract_val(["EquitySecuritiesFvNi", "us-gaap_EquitySecuritiesFvNi"], p)
            comb = (st_debt_cand or 0.0) + (st_eq_cand or 0.0)
            if comb > 0:
                sti_v = round(comb, 1)

    ar_v = extract_val(_BS_CONCEPT_KEYS["ar"], p)
    nontrade_ar = extract_val(["NontradeReceivablesCurrent", "us-gaap_NontradeReceivablesCurrent"], p)
    inv_v = extract_val(_BS_CONCEPT_KEYS["inv"], p)
    ca_raw = extract_val(_BS_CONCEPT_KEYS["ca"], p, "current_assets")

    prep_cand = extract_val(["PrepaidExpenseCurrent", "us-gaap_PrepaidExpenseCurrent", "PrepaidExpensesAndOtherCurrentAssets"], p)
    oth_cand = extract_val(["OtherAssetsCurrent", "us-gaap_OtherAssetsCurrent", "OtherCurrentAssets"], p)
    if prep_cand is not None and oth_cand is not None and prep_cand != oth_cand:
        other_ca_rep = round(prep_cand + oth_cand, 1)
    else:
        other_ca_rep = extract_val(_BS_CONCEPT_KEYS["other_ca"], p)
    if nontrade_ar is not None and nontrade_ar > 0:
        other_ca_rep = (other_ca_rep or 0.0) + nontrade_ar

    restr_cash = extract_val(["RestrictedCashAndCashEquivalentsAtCarryingValue", "us-gaap_RestrictedCashAndCashEquivalentsAtCarryingValue", "RestrictedCashAndInvestmentsCurrent"], p)
    fintech_loans = extract_val(["NotesAndLoansReceivableNetCurrent", "us-gaap_NotesAndLoansReceivableNetCurrent", "LoansAndAdvancesToCustomersCurrent"], p)
    broker_rec = extract_val(["meli_ReceivableFromCustomerInBrokerageCurrent", "ReceivableFromCustomerInBrokerageCurrent"], p)
    for add_val in (restr_cash, fintech_loans, broker_rec):
        if add_val:
            other_ca_rep = (other_ca_rep or 0.0) + add_val

    other_ca = round(other_ca_rep, 1) if other_ca_rep is not None else None
    sum_ca = (c_v or 0.0) + (sti_v or 0.0) + (ar_v or 0.0) + (inv_v or 0.0) + (other_ca or 0.0)
    tot_ca = ca_raw if (ca_raw is not None and ca_raw > 0) else (sum_ca if sum_ca > 0 else None)
    if tot_ca is not None:
        diff_ca = round(tot_ca - sum_ca, 1)
        if abs(diff_ca) > 0.01:
            other_ca = round((other_ca or 0.0) + diff_ca, 1)

    tot_liquid = round((c_v or 0.0) + (sti_v or 0.0), 1) if (c_v is not None or sti_v is not None) else None
    return c_v, sti_v, tot_liquid, ar_v, inv_v, other_ca, tot_ca


def _resolve_bs_noncurrent_assets(extract_val, as_rep_bs_dict, tot_ca, p, periods):
    """Resuelve activos no corrientes y total activos cerrando sum(hijos) == NCA."""
    ppe_v = extract_val(_BS_CONCEPT_KEYS["ppe"], p, "net_ppe")
    rou_v = extract_val(_BS_CONCEPT_KEYS["rou"], p, "operating_lease_rou_asset")
    gw_v = extract_val(_BS_CONCEPT_KEYS["gw"], p)
    int_v = extract_val(_BS_CONCEPT_KEYS["intang"], p)

    is_rou_on_face = _is_any_key_on_face(_BS_CONCEPT_KEYS["rou"], as_rep_bs_dict)
    is_gw_on_face = _is_any_key_on_face(_BS_CONCEPT_KEYS["gw"], as_rep_bs_dict)
    is_int_on_face = _is_any_key_on_face(_BS_CONCEPT_KEYS["intang"], as_rep_bs_dict)

    if not is_rou_on_face:
        rou_v = None

    if p == "LTM" and len(periods) > 1:
        prev_p = periods[1]
        ltm_ma = extract_val(["PaymentsToAcquireBusinessesNetOfCashAcquired", "PaymentsToAcquireBusinessesGross"], "LTM") or 0.0
        if gw_v and not is_gw_on_face:
            prev_gw = extract_val(_BS_CONCEPT_KEYS["gw"], prev_p)
            if (not prev_gw or prev_gw == 0.0) and abs(ltm_ma) < 5000.0:
                gw_v = None
        if int_v and not is_int_on_face:
            prev_int = extract_val(_BS_CONCEPT_KEYS["intang"], prev_p)
            if (not prev_int or prev_int == 0.0) and abs(ltm_ma) < 5000.0:
                int_v = None

    if gw_v is not None and int_v is not None and gw_v == int_v:
        gw_int_v = gw_v
    elif is_int_on_face:
        gw_int_v = round((gw_v or 0.0) + (int_v or 0.0), 1) if (gw_v is not None or int_v is not None) else None
    else:
        gw_int_v = gw_v

    lt_inv_v = extract_val(_BS_CONCEPT_KEYS["lt_inv"], p)
    if not _is_any_key_on_face(_BS_CONCEPT_KEYS["lt_inv"], as_rep_bs_dict):
        eq_method = extract_val(["EquityMethodInvestments", "InvestmentsInAssociates", "InvestmentsInAffiliatesSubsidiariesAssociatesAndJointVentures"], p)
        non_mkt_eq = extract_val(["EquitySecuritiesWithoutReadilyDeterminableFairValueAmount"], p)
        if eq_method is not None and non_mkt_eq is not None:
            lt_inv_v = round(eq_method + non_mkt_eq, 1)

    ta_raw = extract_val(_BS_CONCEPT_KEYS["ta"], p, "total_assets")
    sum_ast = (tot_ca or 0.0) + (ppe_v or 0.0) + (rou_v or 0.0) + (gw_int_v or 0.0) + (lt_inv_v or 0.0)
    tot_ast = ta_raw if (ta_raw is not None and ta_raw > 0) else (sum_ast if sum_ast > 0 else None)
    tot_nca = max(0.0, round((tot_ast or 0.0) - (tot_ca or 0.0), 1)) if tot_ast is not None else None

    other_nca_rep = extract_val(_BS_CONCEPT_KEYS["other_nca"], p)
    other_nca = round(other_nca_rep, 1) if other_nca_rep is not None else None
    dta_v = extract_val(_BS_CONCEPT_KEYS["dta"], p)

    sum_nca = (ppe_v or 0.0) + (rou_v or 0.0) + (gw_int_v or 0.0) + (lt_inv_v or 0.0) + (dta_v or 0.0) + (other_nca or 0.0)
    if tot_nca is not None:
        diff_nca = round(tot_nca - sum_nca, 1)
        if abs(diff_nca) > 0.01:
            other_nca = round((other_nca or 0.0) + diff_nca, 1)

    return ppe_v, rou_v, gw_int_v, lt_inv_v, dta_v, other_nca, tot_nca, tot_ast


def _resolve_bs_liabilities_and_debt(extract_val, tot_ast, eq_v, p):
    """Resuelve pasivos corrientes, no corrientes, deuda total y total pasivos."""
    ap_v = extract_val(_BS_CONCEPT_KEYS["ap"], p)
    accrued_v = extract_val(_BS_CONCEPT_KEYS["accrued"], p, "accrued_liabilities")
    if accrued_v is None or accrued_v == 0.0:
        emp_acc = extract_val(["EmployeeRelatedLiabilitiesCurrent", "us-gaap_EmployeeRelatedLiabilitiesCurrent"], p) or 0.0
        oth_acc = extract_val(["OtherAccruedLiabilitiesCurrent", "us-gaap_OtherAccruedLiabilitiesCurrent"], p) or 0.0
        tax_acc = extract_val(["AccruedIncomeTaxesCurrent", "us-gaap_AccruedIncomeTaxesCurrent"], p) or 0.0
        sub_acc = emp_acc + oth_acc + tax_acc
        if sub_acc > 0:
            accrued_v = round(sub_acc, 1)

    tot_debt = extract_val(_BS_CONCEPT_KEYS["tot_debt"], p, "total_debt")
    st_debt_v = extract_val(_BS_CONCEPT_KEYS["st_debt"], p, "short_term_debt")
    if tot_debt is not None and tot_debt > 0:
        if st_debt_v is not None and st_debt_v > tot_debt:
            st_debt_v = tot_debt
        lt_debt_v = max(0.0, round(tot_debt - (st_debt_v or 0.0), 1))
        if st_debt_v is None:
            st_debt_v = 0.0
    else:
        lt_debt_v = extract_val(_BS_CONCEPT_KEYS["lt_debt"], p, "long_term_debt")
        if st_debt_v is not None or lt_debt_v is not None:
            tot_debt = round((st_debt_v or 0.0) + (lt_debt_v or 0.0), 1)
            if st_debt_v is None:
                st_debt_v = 0.0

    def_rev_v = extract_val(_BS_CONCEPT_KEYS["def_rev"], p)
    cl_raw = extract_val(_BS_CONCEPT_KEYS["cl"], p, "current_liabilities")
    if cl_raw is not None and def_rev_v is not None:
        pre_def_sum = (ap_v or 0.0) + (st_debt_v or 0.0) + (accrued_v or 0.0)
        if pre_def_sum + def_rev_v > cl_raw:
            def_rev_v = max(0.0, round(cl_raw - pre_def_sum, 1))

    sum_cl = (ap_v or 0.0) + (st_debt_v or 0.0) + (accrued_v or 0.0) + (def_rev_v or 0.0)
    tot_cl = cl_raw if (cl_raw is not None and cl_raw > 0) else (sum_cl if sum_cl > 0 else None)
    other_cl = max(0.0, round((tot_cl or 0.0) - sum_cl, 1)) if tot_cl is not None else None

    lease_nc_v = extract_val(_BS_CONCEPT_KEYS["lease_liab_nc"], p)
    def_tax_nc_v = extract_val(_BS_CONCEPT_KEYS["def_tax_nc"], p)
    tl_raw = extract_val(_BS_CONCEPT_KEYS["tl"], p)
    mezz_pre = extract_val(_BS_CONCEPT_KEYS["mezz_eq"], p) if tl_raw is None else None
    tot_liab = tl_raw if (tl_raw is not None and tl_raw > 0) else (
        max(0.0, round((tot_ast or 0.0) - (eq_v or 0.0) - (mezz_pre or 0.0), 1)) if (tot_ast is not None and eq_v is not None) else None
    )
    tot_ncl = max(0.0, round((tot_liab or 0.0) - (tot_cl or 0.0), 1)) if (tot_liab is not None and tot_cl is not None) else None
    other_ncl = (
        max(0.0, round((tot_ncl or 0.0) - ((lt_debt_v or 0.0) + (lease_nc_v or 0.0) + (def_tax_nc_v or 0.0)), 1))
        if tot_ncl is not None
        else None
    )
    return (
        ap_v,
        accrued_v,
        def_rev_v,
        st_debt_v,
        other_cl,
        tot_cl,
        lt_debt_v,
        lease_nc_v,
        def_tax_nc_v,
        other_ncl,
        tot_ncl,
        tot_liab,
        tot_debt,
    )


def _resolve_bs_equity_and_sectoral(
    extract_val,
    canonical,
    tot_ast,
    tot_liab,
    eq_v,
    tot_ca,
    tot_cl,
    tot_nca,
    tot_ncl,
    tot_debt,
    tot_liquid,
    gw_int_v,
    ppe_v,
    p,
    archetype,
):
    """Resuelve patrimonio neto, intereses minoritarios, métricas por acción y partidas sectoriales."""
    apic_v = extract_val(_BS_CONCEPT_KEYS["apic"], p)
    if apic_v is None or apic_v == 0.0:
        v_cs = extract_val(["CommonStockValue", "us-gaap_CommonStockValue", "IssuedCapital", "ifrs-full_IssuedCapital"], p)
        v_apic = extract_val(["AdditionalPaidInCapital", "us-gaap_AdditionalPaidInCapital", "SharePremium", "ifrs-full_SharePremium"], p)
        if v_cs is not None or v_apic is not None:
            apic_v = round((v_cs or 0.0) + (v_apic or 0.0), 1)

    re_v = extract_val(_BS_CONCEPT_KEYS["re"], p)
    aoci_v = extract_val(
        [
            "AccumulatedOtherComprehensiveIncomeLossNetOfTax",
            "us-gaap_AccumulatedOtherComprehensiveIncomeLossNetOfTax",
            "AccumulatedOtherComprehensiveIncomeLossAvailableForSaleSecuritiesNetOfTax",
            "ifrs-full_AccumulatedOtherComprehensiveIncome",
        ],
        p,
    )
    treas_v = extract_val(["TreasuryStockValue", "TreasuryStockCommonValue", "us-gaap_TreasuryStockValue"], p)

    if (apic_v is None or apic_v == 0.0) and eq_v is not None and re_v is not None:
        derived_apic = round(eq_v - re_v - (aoci_v or 0.0) + abs(treas_v or 0.0), 1)
        if derived_apic > 0:
            apic_v = derived_apic

    other_eq_v = round((eq_v or 0.0) - ((apic_v or 0.0) + (re_v or 0.0)), 1) if eq_v is not None else None

    mezz_v = extract_val(_BS_CONCEPT_KEYS["mezz_eq"], p)

    min_int_v = extract_val(
        [
            "NonredeemableNoncontrollingInterest",
            "us-gaap_NonredeemableNoncontrollingInterest",
            "MinorityInterest",
            "us-gaap_MinorityInterest",
            "NoncontrollingInterests",
            "NoncontrollingInterest",
        ],
        p,
    )
    eq_tot_cand = extract_val(
        ["StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest", "ifrs-full_Equity", "TotalEquity"],
        p,
    )
    if eq_tot_cand is not None and (eq_v is None or eq_tot_cand > eq_v):
        if min_int_v is None and eq_v is not None:
            min_int_v = round(eq_tot_cand - eq_v, 1)
        eq_v = eq_tot_cand
    elif min_int_v is not None and min_int_v > 0:
        if tot_ast is not None and tot_liab is not None and abs((tot_liab + (eq_v or 0.0) + (mezz_v or 0.0) + min_int_v) - tot_ast) <= 2.0:
            eq_v = round((eq_v or 0.0) + min_int_v, 1)

    base_liab_eq = round((tot_liab or 0.0) + (eq_v or 0.0), 1) if (tot_liab is not None or eq_v is not None) else None
    if mezz_v is not None and mezz_v != 0.0 and base_liab_eq is not None:
        with_mezz = round(base_liab_eq + mezz_v, 1)
        if tot_ast is not None and abs(with_mezz - tot_ast) < abs(base_liab_eq - tot_ast):
            tot_liab_eq = with_mezz
        elif tot_ast is not None and abs(base_liab_eq - tot_ast) <= 2.0:
            tot_liab_eq = base_liab_eq
        else:
            tot_liab_eq = with_mezz
    else:
        tot_liab_eq = base_liab_eq
    if archetype == "FINANCIAL_BANKING":
        nwc_v = net_fin_pos = tot_ca = tot_cl = tot_nca = tot_ncl = None
    else:
        nwc_v = round((tot_ca or 0.0) - (tot_cl or 0.0), 1) if (tot_ca is not None and tot_cl is not None) else None
        net_fin_pos = round((tot_debt or 0.0) - (tot_liquid or 0.0), 1) if (tot_debt is not None and tot_liquid is not None) else None

    shares_v = (
        extract_val(
            ["WeightedAverageNumberOfDilutedSharesOutstanding", "us-gaap_WeightedAverageNumberOfDilutedSharesOutstanding", "CommonStockSharesOutstanding"],
            p,
            "shares_diluted_adjusted",
        )
        or canonical.get("shares_diluted", {}).get(p)
    )
    if shares_v and float(shares_v) > 0:
        sh_count = float(shares_v)
        sh_m = sh_count / 1e6 if sh_count >= 1e6 else sh_count
        if eq_v and abs(eq_v) >= 1e6:
            eq_m = eq_v / 1e6
            gw_m = (gw_int_v / 1e6) if gw_int_v else 0.0
        else:
            eq_m = eq_v or 0.0
            gw_m = gw_int_v or 0.0
        bvps = round(eq_m / sh_m, 2) if sh_m > 0 else None
        tbvps = round((eq_m - gw_m) / sh_m, 2) if sh_m > 0 else None
    else:
        bvps, tbvps = None, None

    net_loans_v = extract_val(_BS_CONCEPT_KEYS["net_loans"], p, "net_loans")
    allow_loss_v = extract_val(_BS_CONCEPT_KEYS["allow_loss"], p, ["allowance_for_credit_losses", "allowance_for_loan_losses"])
    if allow_loss_v is not None:
        allow_loss_v = abs(allow_loss_v)
        if allow_loss_v < 1e7 and (net_loans_v or 0.0) > 1e9:
            allow_loss_v = None
    dep_v = extract_val(_BS_CONCEPT_KEYS["deposit"], p, "deposits")
    prem_rec_v = extract_val(_BS_CONCEPT_KEYS["prem_rec"], p, "premiums_receivable")
    dac_v = extract_val(_BS_CONCEPT_KEYS["dac"], p, "deferred_policy_acquisition_costs")
    loss_res_v = extract_val(_BS_CONCEPT_KEYS["loss_res"], p, "loss_reserves")
    unearn_prem_v = extract_val(_BS_CONCEPT_KEYS["unearn_prem"], p, "unearned_premiums")

    other_ast_sec = None
    if tot_ast is not None:
        if net_loans_v is not None or dep_v is not None:
            other_ast_sec = round(tot_ast - (tot_liquid or 0.0) - (net_loans_v or 0.0) - (gw_int_v or 0.0) - (ppe_v or 0.0), 1)
        elif prem_rec_v is not None or loss_res_v is not None:
            other_ast_sec = round(tot_ast - (tot_liquid or 0.0) - (prem_rec_v or 0.0) - (dac_v or 0.0) - (ppe_v or 0.0), 1)

    other_liab_sec = None
    if tot_liab is not None:
        if dep_v is not None:
            other_liab_sec = round(tot_liab - (dep_v or 0.0) - (tot_debt or 0.0), 1)
        elif loss_res_v is not None:
            other_liab_sec = round(tot_liab - (loss_res_v or 0.0) - (unearn_prem_v or 0.0) - (tot_debt or 0.0), 1)

    return {
        "common_stock_and_apic": apic_v,
        "retained_earnings": re_v,
        "other_equity": other_eq_v,
        "mezzanine_equity": mezz_v,
        "minority_interest": min_int_v,
        "stockholders_equity": eq_v,
        "total_liab_and_equity": tot_liab_eq,
        "total_current_assets": tot_ca,
        "total_current_liabilities": tot_cl,
        "total_noncurrent_assets": tot_nca,
        "total_noncurrent_liabilities": tot_ncl,
        "net_working_capital": nwc_v,
        "net_financial_position": net_fin_pos,
        "book_value_per_share": bvps,
        "tangible_book_value_per_share": tbvps,
        "net_loans": net_loans_v,
        "allowance_for_loan_losses": allow_loss_v,
        "deposits": dep_v,
        "premiums_receivable": prem_rec_v,
        "deferred_policy_acquisition_costs": dac_v,
        "loss_reserves": loss_res_v,
        "unearned_premiums": unearn_prem_v,
        "other_assets_sectoral": other_ast_sec,
        "other_liabilities_sectoral": other_liab_sec,
    }


def resolve_canonical_balance_sheet(fs, periods, archetype="STANDARD_CORPORATE"):
    """
    Función canónica y unificada (SSOT) para resolver el Balance General clasificado
    (Activos Corrientes y No Corrientes, Pasivos Corrientes y No Corrientes, Patrimonio Neto
    y Diagnóstico de Liquidez y Solvencia) a partir de financial_statements.json.
    """
    if not archetype or archetype == "STANDARD_CORPORATE":
        archetype = fs.get("archetype") or ("FINANCIAL_BANKING" if fs.get("is_financial") else "STANDARD_CORPORATE")
    canonical = fs.get("canonical_summary", {}) if isinstance(fs, dict) else {}
    as_rep_bs_dict = _as_reported_concept_dict(fs, "balance_sheet")
    bal_sources = [
        as_rep_bs_dict,
        fs.get("balance_sheet", {}) if isinstance(fs, dict) else {},
        fs.get("balance_sheet_detail", {}) if isinstance(fs, dict) else {},
    ]
    ltm_source_period = _detect_ltm_source_period(canonical, periods)

    def _extract_val(key_cands, p, can_key=None):
        src_p = ltm_source_period if (p == "LTM" and ltm_source_period) else p
        period_chain = ["LTM", src_p] if (p == "LTM" and src_p != "LTM") else [p]
        can_keys = [can_key] if isinstance(can_key, str) else (can_key or [])
        for ck in can_keys:
            can_val = _to_float(canonical.get(ck, {}).get(p), f"canonical.{ck}:{p}")
            if can_val is not None and can_val != 0.0:
                return can_val
        for period_try in period_chain:
            for src in bal_sources:
                found = _extract_from_single_source(src, key_cands, period_try)
                if found is not None:
                    return found
        for ck in can_keys:
            can_val = _to_float(canonical.get(ck, {}).get(p), f"canonical.{ck}:{p}")
            if can_val is not None:
                return can_val
        return None

    res = {
        k: {}
        for k in (
            "cash",
            "short_term_investments",
            "total_liquid_cash",
            "accounts_receivable",
            "inventories",
            "other_current_assets",
            "total_current_assets",
            "net_ppe",
            "rou_asset",
            "net_ppe_plus_rou",
            "goodwill_and_intangibles",
            "long_term_investments",
            "deferred_tax_assets",
            "other_noncurrent_assets",
            "total_noncurrent_assets",
            "total_assets",
            "accounts_payable",
            "accrued_liabilities",
            "deferred_revenue_current",
            "short_term_debt",
            "other_current_liabilities",
            "total_current_liabilities",
            "long_term_debt",
            "operating_lease_liability_noncurrent",
            "deferred_tax_liabilities_noncurrent",
            "other_noncurrent_liabilities",
            "total_noncurrent_liabilities",
            "total_liabilities",
            "common_stock_and_apic",
            "retained_earnings",
            "other_equity",
            "mezzanine_equity",
            "minority_interest",
            "total_debt",
            "stockholders_equity",
            "total_liab_and_equity",
            "net_working_capital",
            "net_financial_position",
            "book_value_per_share",
            "tangible_book_value_per_share",
            "net_loans",
            "allowance_for_loan_losses",
            "deposits",
            "premiums_receivable",
            "deferred_policy_acquisition_costs",
            "loss_reserves",
            "unearned_premiums",
            "other_assets_sectoral",
            "other_liabilities_sectoral",
        )
    }

    for p in periods:
        c_v, sti_v, tot_liquid, ar_v, inv_v, other_ca, tot_ca = _resolve_bs_current_assets(
            fs, canonical, _extract_val, p, archetype, ltm_source_period
        )
        ppe_v, rou_v, gw_int_v, lt_inv_v, dta_v, other_nca, tot_nca, tot_ast = _resolve_bs_noncurrent_assets(
            _extract_val, as_rep_bs_dict, tot_ca, p, periods
        )
        eq_v = _extract_val(_BS_CONCEPT_KEYS["eq"], p, "stockholders_equity")
        (
            ap_v,
            accrued_v,
            def_rev_v,
            st_debt_v,
            other_cl,
            tot_cl,
            lt_debt_v,
            lease_nc_v,
            def_tax_nc_v,
            other_ncl,
            tot_ncl,
            tot_liab,
            tot_debt,
        ) = _resolve_bs_liabilities_and_debt(_extract_val, tot_ast, eq_v, p)

        tail = _resolve_bs_equity_and_sectoral(
            _extract_val,
            canonical,
            tot_ast,
            tot_liab,
            eq_v,
            tot_ca,
            tot_cl,
            tot_nca,
            tot_ncl,
            tot_debt,
            tot_liquid,
            gw_int_v,
            ppe_v,
            p,
            archetype,
        )

        res["cash"][p] = c_v
        res["short_term_investments"][p] = sti_v
        res["total_liquid_cash"][p] = tot_liquid
        res["accounts_receivable"][p] = ar_v
        res["inventories"][p] = inv_v
        res["other_current_assets"][p] = other_ca
        res["net_ppe"][p] = ppe_v
        res["rou_asset"][p] = rou_v
        res["net_ppe_plus_rou"][p] = round((ppe_v or 0.0) + (rou_v or 0.0), 1) if (ppe_v is not None or rou_v is not None) else None
        res["goodwill_and_intangibles"][p] = gw_int_v
        res["long_term_investments"][p] = lt_inv_v
        res["deferred_tax_assets"][p] = dta_v
        res["other_noncurrent_assets"][p] = other_nca
        res["total_assets"][p] = tot_ast
        res["accounts_payable"][p] = ap_v
        res["accrued_liabilities"][p] = accrued_v
        res["deferred_revenue_current"][p] = def_rev_v
        res["short_term_debt"][p] = st_debt_v
        res["other_current_liabilities"][p] = other_cl
        res["long_term_debt"][p] = lt_debt_v
        res["operating_lease_liability_noncurrent"][p] = lease_nc_v
        res["deferred_tax_liabilities_noncurrent"][p] = def_tax_nc_v
        res["other_noncurrent_liabilities"][p] = other_ncl
        res["total_liabilities"][p] = tot_liab
        res["total_debt"][p] = tot_debt
        for field_key, field_val in tail.items():
            res[field_key][p] = field_val

    return res


def _iter_as_reported_rows(fs, section_type):
    """Itera de forma segura sobre filas de as_reported_statements."""
    as_reported = fs.get("as_reported_statements", {})
    if not isinstance(as_reported, dict):
        return []
    sec_name = _SECTION_AS_REPORTED_MAP.get(section_type, section_type)
    sec_obj = as_reported.get(sec_name, [])
    rows_list = sec_obj if isinstance(sec_obj, list) else (sec_obj.get("rows", []) if isinstance(sec_obj, dict) else [])
    return [r for r in rows_list if isinstance(r, dict)] if isinstance(rows_list, list) else []


def _extract_multi_source_val(fs, section_type, key_cands, p, canon_keys=None):
    """
    Función universal multi-fuente (SSOT) para extraer valores de estados financieros:
    1. canonical_summary (si canon_keys se especifica y existe en p y != None)
    2. *_detail (income_statement_detail, balance_sheet_detail, cash_flow_detail)
    3. as_reported_statements (income_statement, balance_sheet, cash_flow_statement)
    """
    if not isinstance(fs, dict):
        return None
    canonical = fs.get("canonical_summary", {})
    if canon_keys:
        if isinstance(canon_keys, str):
            canon_keys = [canon_keys]
        for ck in canon_keys:
            if ck in canonical and isinstance(canonical[ck], dict):
                v = canonical[ck].get(p)
                if v is not None:
                    parsed = _to_float(v, f"canonical.{ck}:{p}")
                    if parsed is not None:
                        return parsed

    det_key = _SECTION_DETAIL_MAP.get(section_type, f"{section_type}_detail")
    detail_dict = fs.get(det_key, {})
    if isinstance(detail_dict, dict):
        for k in key_cands:
            variants = [k, f"us-gaap_{k}", f"ifrs-full_{k}"]
            if k.startswith("us-gaap_"):
                variants.append(k[len("us-gaap_"):])
            elif k.startswith("ifrs-full_"):
                variants.append(k[len("ifrs-full_"):])
            for var in variants:
                if var in detail_dict:
                    obj = detail_dict[var]
                    vals = obj.get("values", obj) if isinstance(obj, dict) else {}
                    if isinstance(vals, dict) and p in vals and vals[p] is not None:
                        parsed = _to_float(vals[p], f"{det_key}.{var}:{p}")
                        if parsed is not None:
                            return parsed
            k_token = k.lower().split(":")[-1].split("_")[-1]
            for dk, dobj in detail_dict.items():
                d_token = dk.lower().split(":")[-1].split("_")[-1]
                if dk.lower() == k.lower() or d_token == k_token:
                    vals = dobj.get("values", dobj) if isinstance(dobj, dict) else {}
                    if isinstance(vals, dict) and p in vals and vals[p] is not None:
                        parsed = _to_float(vals[p], f"{det_key}.{dk}:{p}")
                        if parsed is not None:
                            return parsed

    for row in _iter_as_reported_rows(fs, section_type):
        concept = str(row.get("concept", ""))
        c_token = concept.lower().split(":")[-1].split("_")[-1]
        for k in key_cands:
            k_token = k.lower().split(":")[-1].split("_")[-1]
            if concept == k or concept.lower() == k.lower() or c_token == k_token:
                vals = row.get("values", {})
                if isinstance(vals, dict) and p in vals and vals[p] is not None:
                    parsed = _to_float(vals[p], f"as_reported.{concept}:{p}")
                    if parsed is not None:
                        return parsed
    return None


def _extract_multi_source_sum(fs, section_type, key_cands, p, canon_keys=None):
    """
    Función universal multi-fuente (SSOT) para sumar múltiples partidas componentes
    de un concepto financiero evitando duplicidades de tokens idénticos o conceptos abstractos.
    """
    if not isinstance(fs, dict):
        return None
    total = 0.0
    matched = False
    matched_tokens = set()

    det_key = _SECTION_DETAIL_MAP.get(section_type, f"{section_type}_detail")
    detail_dict = fs.get(det_key, {})
    if isinstance(detail_dict, dict):
        for k in key_cands:
            k_token = k.lower().split(":")[-1].split("_")[-1]
            for dk, dobj in detail_dict.items():
                if "abstract" in str(dk).lower():
                    continue
                d_token = str(dk).lower().split(":")[-1].split("_")[-1]
                if (dk.lower() == k.lower() or d_token == k_token) and d_token not in matched_tokens:
                    vals = dobj.get("values", dobj) if isinstance(dobj, dict) else {}
                    if isinstance(vals, dict) and p in vals and vals[p] is not None:
                        parsed = _to_float(vals[p], f"{det_key}.{dk}:{p}")
                        if parsed is not None:
                            total += parsed
                            matched = True
                            matched_tokens.add(d_token)

    for row in _iter_as_reported_rows(fs, section_type):
        if row.get("is_abstract"):
            continue
        concept = str(row.get("concept", ""))
        c_token = concept.lower().split(":")[-1].split("_")[-1]
        for k in key_cands:
            k_token = k.lower().split(":")[-1].split("_")[-1]
            if (concept.lower() == k.lower() or c_token == k_token) and c_token not in matched_tokens:
                vals = row.get("values", {})
                if isinstance(vals, dict) and p in vals and vals[p] is not None:
                    parsed = _to_float(vals[p], f"as_reported.{concept}:{p}")
                    if parsed is not None:
                        total += parsed
                        matched = True
                        matched_tokens.add(c_token)

    if not matched and canon_keys:
        canonical = fs.get("canonical_summary", {})
        if isinstance(canon_keys, str):
            canon_keys = [canon_keys]
        for ck in canon_keys:
            if ck in canonical and isinstance(canonical[ck], dict):
                v = canonical[ck].get(p)
                if v is not None:
                    parsed = _to_float(v, f"canonical.{ck}:{p}")
                    if parsed is not None:
                        return parsed

    return total if matched else None


def _resolve_is_operating_section(fs, p, archetype):
    """Resuelve ingresos, costos directos, OpEx y EBIT para un período."""
    rev = _extract_multi_source_val(
        fs,
        "income",
        [
            "Revenues",
            "RevenueFromContractWithCustomerExcludingAssessedTax",
            "SalesRevenueNet",
            "TotalRevenuesAndOtherIncome",
            "Revenue",
            "ifrs-full_Revenue",
            "RevenuesNetOfInterestExpense",
        ],
        p,
        "revenue",
    )
    cogs = _extract_multi_source_val(
        fs,
        "income",
        ["CostOfGoodsAndServicesSold", "CostOfRevenue", "CostOfGoodsSold", "CostOfPurchasedGoodsAndServices", "ifrs-full_CostOfSales"],
        p,
        "cost_of_goods_sold",
    )
    if cogs is not None:
        cogs = abs(cogs)

    gp = _extract_multi_source_val(fs, "income", ["GrossProfit", "ifrs-full_GrossProfit"], p, "gross_profit")
    if gp is None and rev is not None and cogs is not None and archetype not in ("FINANCIAL_BANKING", "INSURANCE"):
        gp = round(rev - cogs, 2)
    if cogs is None and rev is not None and gp is not None and archetype not in ("FINANCIAL_BANKING", "INSURANCE"):
        cogs = round(rev - gp, 2)

    rd = _extract_multi_source_val(
        fs,
        "income",
        [
            "ResearchAndDevelopmentExpense",
            "TechnologyAndContentExpense",
            "TechnologyAndDevelopmentExpense",
            "ResearchAndDevelopmentExpenseSoftware",
            "ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost",
        ],
        p,
        ["rd_expense", "research_and_development"],
    )
    if rd is not None:
        rd = abs(rd)

    sga = _extract_multi_source_val(
        fs,
        "income",
        ["SellingGeneralAndAdministrativeExpense", "SellingGeneralAndAdministrative"],
        p,
        ["sga_expense", "selling_general_and_administrative"],
    )
    if sga is None:
        sm = _extract_multi_source_val(
            fs, "income", ["SellingAndMarketingExpense", "MarketingAndAdvertisingExpense", "SellingExpense", "AdvertisingExpense"], p, "sm_expense"
        )
        ga = _extract_multi_source_val(fs, "income", ["GeneralAndAdministrativeExpense", "AdministrativeExpense"], p, "ga_expense")
        if sm is not None or ga is not None:
            sga = (abs(sm) if sm else 0.0) + (abs(ga) if ga else 0.0)
        else:
            ga_only = _extract_multi_source_val(fs, "income", ["GeneralAndAdministrativeExpense"], p)
            if ga_only is not None:
                sga = abs(ga_only)
    if sga is not None:
        sga = abs(sga)

    credit_loss = _extract_multi_source_val(
        fs,
        "income",
        [
            "nu_ExpectedCreditLoss",
            "ExpectedCreditLoss",
            "ProvisionForLoanLeaseAndOtherLosses",
            "ProvisionForLoanLossesExpensed",
            "ProvisionForDoubtfulAccounts",
            "nu_CreditLossAllowanceExpenses",
            "CreditLossAllowanceExpenses1",
            "ifrs-full_AdditionalAllowanceRecognisedInProfitOrLossAllowanceAccountForCreditLossesOfFinancialAssets",
        ],
        p,
        ["credit_loss_provisions", "provision_for_credit_losses"],
    )
    if credit_loss is not None:
        credit_loss = abs(credit_loss)

    ebit = (
        None
        if archetype == "FINANCIAL_BANKING"
        else _extract_multi_source_val(
            fs, "income", ["OperatingIncomeLoss", "ifrs-full_ProfitLossFromOperatingActivities", "OperatingIncome"], p, "operating_income"
        )
    )

    tot_opex = _extract_multi_source_val(
        fs, "income", ["OperatingExpenses", "CostsAndExpenses", "ifrs-full_OperatingExpense"], p, "operating_expenses"
    )
    if tot_opex is None and gp is not None and ebit is not None and archetype not in ("FINANCIAL_BANKING", "INSURANCE"):
        tot_opex = round(gp - ebit, 2)
    if tot_opex is not None:
        tot_opex = abs(tot_opex)

    if tot_opex is not None and sga is not None and rd is not None:
        if abs(tot_opex - sga) <= 1.0 or (sga >= tot_opex - 1.0):
            rd = None

    other_opex_raw = _extract_multi_source_val(
        fs,
        "income",
        [
            "RestructuringCharges",
            "OtherCostAndExpenseOperating",
            "BusinessCombinationAcquisitionRelatedCosts",
            "AmortizationOfIntangibleAssets",
            "OperatingExpensesOther",
            "ImpairmentOfIntangibleAssetsFinitelived",
        ],
        p,
    )
    if tot_opex is not None and archetype not in ("FINANCIAL_BANKING", "INSURANCE"):
        implied_other = max(0.0, round(tot_opex - (rd or 0.0) - (sga or 0.0) - (credit_loss or 0.0), 2))
        other_opex = implied_other if implied_other > 0.01 else None
    else:
        other_opex = abs(other_opex_raw) if other_opex_raw is not None else None

    return rev, cogs, gp, rd, sga, credit_loss, other_opex, tot_opex, ebit


def _resolve_is_nonop_tax_ni(fs, p, ebit, archetype):
    """Resuelve partidas no operativas, EBT, impuesto reconciliado, beneficio neto y neto común."""
    int_inc = _extract_multi_source_val(
        fs,
        "income",
        [
            "InvestmentIncomeInterest",
            "InterestIncomeOperating",
            "InterestAndDividendIncomeOperating",
            "InterestIncome",
            "ifrs-full_RevenueFromInterest",
            "nu_IncomeExpenseGainsOrLossesOfFinancialInstruments",
            "IncomeExpenseGainsOrLossesOfFinancialInstruments",
            "InterestIncomeBank",
        ],
        p,
        "interest_income",
    )
    if int_inc is not None:
        int_inc = abs(int_inc)

    int_exp = _extract_multi_source_val(
        fs,
        "income",
        [
            "InterestExpense",
            "InterestExpenseNonoperating",
            "InterestExpenseDebt",
            "InterestExpenseOperating",
            "meli_InterestExpenseAndOtherFinancialCharges",
        ],
        p,
    )
    if int_exp is None:
        int_exp = _extract_multi_source_val(fs, "income", [], p, "interest_expense")
    if int_exp is not None:
        int_exp = abs(int_exp)

    share_assoc = _extract_multi_source_val(
        fs,
        "income",
        [
            "nu_ShareOfLossInAssociates",
            "ShareOfProfitLossOfAssociatesAndJointVenturesAccountedForUsingEquityMethod",
            "IncomeLossFromEquityMethodInvestments",
            "ShareOfLossInAssociates",
            "meli_EquityInEarningsOfUnconsolidatedEntityNetOfTax",
            "EquityInEarningsOfUnconsolidatedEntity",
            "EquityInEarningsLossOfUnconsolidatedEntity",
            "EquityInLossOfUnconsolidatedEntity",
        ],
        p,
        "share_of_associates",
    )

    tax_raw = _extract_multi_source_val(
        fs,
        "income",
        [
            "IncomeTaxExpenseBenefit",
            "IncomeTaxExpenseContinuingOperations",
            "nu_IncomeTaxInStatementOfProfitOrLoss",
            "CurrentIncomeTaxExpenseBenefit",
            "ifrs-full_IncomeTaxExpenseContinuingOperations",
        ],
        p,
        ["income_tax", "income_tax_expense"],
    )
    if tax_raw is None:
        c_tax = _extract_multi_source_val(fs, "income", ["CurrentTaxExpenseIncome"], p)
        d_tax = _extract_multi_source_val(fs, "income", ["DeferredTaxExpenseIncome"], p)
        if c_tax is not None or d_tax is not None:
            tax_raw = (c_tax or 0.0) + (d_tax or 0.0)

    ni = _extract_multi_source_val(fs, "income", ["NetIncomeLoss", "ProfitLoss", "NetIncome", "ifrs-full_ProfitLoss"], p, "net_income")
    ebt = _extract_multi_source_val(
        fs,
        "income",
        [
            "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
            "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
            "IncomeLossAttributableToParent",
            "us-gaap_IncomeLossAttributableToParent",
            "IncomeLossBeforeIncomeTaxExpenseBenefit",
            "ProfitLossBeforeTax",
        ],
        p,
        "ebt",
    )

    tax = tax_raw
    if ebt is not None and ni is not None:
        pre_assoc_ni = round(ni - (share_assoc or 0.0), 2)
        diff = round(ebt - pre_assoc_ni, 2)
        if tax is None:
            tax = diff
        elif diff < -1.0 and tax > 0:
            tax = -abs(tax)
        elif diff > 1.0 and tax < 0:
            tax = abs(tax)

    if ebt is None and ni is not None and tax is not None:
        ebt = round(ni - (share_assoc or 0.0) + tax, 2)

    tot_non_op_raw = _extract_multi_source_val(
        fs,
        "income",
        ["NonoperatingIncomeExpense", "InterestRevenueExpenseNet", "deck_InterestAndOtherExpense", "NonoperatingIncomeExpenseNet"],
        p,
        "non_operating_income",
    )
    if ebt is not None and ebit is not None and archetype != "FINANCIAL_BANKING":
        tot_non_op = round(ebt - ebit, 2)
    elif tot_non_op_raw is not None:
        tot_non_op = tot_non_op_raw
    elif int_inc is not None or int_exp is not None:
        tot_non_op = round((int_inc or 0.0) - (int_exp or 0.0), 2)
    else:
        tot_non_op = None

    if ebt is None and ebit is not None and tot_non_op is not None:
        ebt = round(ebit + tot_non_op, 2)
    if ni is None and ebt is not None and tax is not None:
        ni = round(ebt - tax + (share_assoc or 0.0), 2)

    other_non_op = _extract_multi_source_val(
        fs,
        "income",
        [
            "OtherNonoperatingIncomeExpense",
            "GainLossOnInvestments",
            "ForeignCurrencyTransactionGainLossBeforeTax",
            "GainLossOnSaleOfSecuritiesNet",
            "OtherNonoperatingIncomeExpenseNet",
        ],
        p,
        "other_non_operating",
    )
    if tot_non_op is not None and (int_inc is not None or int_exp is not None):
        implied_other_non_op = round(tot_non_op - (int_inc or 0.0) + (int_exp or 0.0), 2)
        other_non_op = implied_other_non_op if abs(implied_other_non_op) > 0.01 else None

    min_int_pnl = _extract_multi_source_val(
        fs, "income", ["NetIncomeLossAttributableToNoncontrollingInterest", "ProfitLossAttributableToNoncontrollingInterests"], p
    )
    if min_int_pnl is not None:
        min_int_pnl = abs(min_int_pnl)

    pref_div = _extract_multi_source_val(
        fs,
        "income",
        ["PreferredStockDividendsIncomeStatementImpact", "RedeemablePreferredStockDividends", "PreferredStockDividendsAndOtherAdjustments"],
        p,
    )
    if pref_div is not None:
        pref_div = abs(pref_div)

    ni_comm = _extract_multi_source_val(
        fs, "income", ["NetIncomeLossAvailableToCommonStockholdersBasic", "ProfitLossAttributableToOwnersOfParent"], p
    )
    if ((min_int_pnl or pref_div) and ni is not None) or (ni_comm is None and ni is not None):
        ni_comm = round(ni - (min_int_pnl or 0.0) - (pref_div or 0.0), 2)

    return int_inc, int_exp, share_assoc, tax, ebt, ni, tot_non_op, other_non_op, min_int_pnl, pref_div, ni_comm


def _resolve_is_per_share_and_sectors(fs, canonical, periods, p, rev, ebt, credit_loss, int_inc, int_exp, ebit, gp, cogs, ni_comm, archetype):
    """Resuelve EPS/acciones/DPS y líneas sectoriales específicas por arquetipo."""
    eps_b = _extract_multi_source_val(
        fs, "income", ["EarningsPerShareBasic", "BasicEarningsLossPerShare", "ifrs-full_BasicEarningsLossPerShare"], p, ["eps_basic_adjusted", "eps_basic"]
    )
    eps_d = _extract_multi_source_val(
        fs,
        "income",
        ["EarningsPerShareDiluted", "DilutedEarningsLossPerShare", "ifrs-full_DilutedEarningsLossPerShare"],
        p,
        ["eps_diluted_adjusted", "eps_diluted"],
    )
    sh_b = _extract_multi_source_val(
        fs, "income", ["WeightedAverageNumberOfSharesOutstandingBasic", "ifrs-full_WeightedAverageShares"], p, ["shares_basic_adjusted", "shares_basic"]
    )
    sh_d = _extract_multi_source_val(
        fs,
        "income",
        ["WeightedAverageNumberOfDilutedSharesOutstanding", "ifrs-full_AdjustedWeightedAverageShares"],
        p,
        ["shares_diluted_adjusted", "shares_diluted"],
    )

    if sh_b is None and p == "LTM" and sh_d is not None and sh_d > 0:
        prior_p = next((x for x in periods if x != "LTM"), None)
        if prior_p:
            prior_sb = _extract_multi_source_val(
                fs,
                "income",
                ["WeightedAverageNumberOfSharesOutstandingBasic", "ifrs-full_WeightedAverageShares"],
                prior_p,
                ["shares_basic_adjusted", "shares_basic"],
            )
            prior_sd = _extract_multi_source_val(
                fs,
                "income",
                ["WeightedAverageNumberOfDilutedSharesOutstanding", "ifrs-full_AdjustedWeightedAverageShares"],
                prior_p,
                ["shares_diluted_adjusted", "shares_diluted"],
            )
            sh_b = round(sh_d * min(1.0, prior_sb / prior_sd)) if (prior_sb and prior_sd and prior_sd > 0) else sh_d
        else:
            sh_b = sh_d

    if eps_b is None and p == "LTM" and ni_comm is not None and sh_b and sh_b > 0:
        eps_b = round(ni_comm / sh_b, 2)

    dps_val = _extract_multi_source_val(
        fs,
        "income",
        ["CommonStockDividendsPerShareDeclared", "CommonStockDividendsPerShareCashPaid", "DividendsPerShareDeclared"],
        p,
        ["dps_adjusted", "dps"],
    )
    split_fac = canonical.get("split_adjustment_factor", {}).get(p, 1.0)
    if split_fac and split_fac > 1.0 and dps_val is not None:
        if "dps_adjusted" not in canonical or canonical.get("dps_adjusted", {}).get(p) is None:
            dps_val = round(dps_val / split_fac, 4)

    if dps_val is None:
        div_paid = _extract_multi_source_val(
            fs, "cashflow", ["PaymentsOfDividendsCommonStock", "PaymentsOfDividends", "DividendsPaid"], p, "dividends_paid"
        )
        if div_paid is not None and abs(div_paid) > 0 and sh_b and sh_b > 0:
            raw_dps = abs(div_paid) / sh_b
            dps_val = round(raw_dps / split_fac, 4) if (split_fac and split_fac > 1.0) else round(raw_dps, 4)

    nii = _extract_multi_source_val(fs, "income", ["InterestIncomeExpenseNet", "NetInterestIncome"], p, "net_interest_income")
    if nii is None and int_inc is not None and int_exp is not None:
        nii = round(int_inc - int_exp, 2)
    if int_inc is None and nii is not None and int_exp is not None and archetype == "FINANCIAL_BANKING":
        int_inc = round(nii + int_exp, 2)

    non_int_inc = _extract_multi_source_val(
        fs, "income", ["NoninterestIncome", "ifrs-full_FeeAndCommissionIncome", "jpm_FeesAndCommissions1"], p, "non_interest_income"
    )
    if non_int_inc is None and rev is not None and nii is not None:
        non_int_inc = round(rev - nii, 2)

    non_int_exp = _extract_multi_source_val(
        fs,
        "income",
        ["NoninterestExpense", "GeneralAndAdministrativeExpense", "SellingExpense", "nu_CustomerSupportAndOperations"],
        p,
        ["operating_expenses", "non_interest_expense"],
    )
    if non_int_exp is None and rev is not None and credit_loss is not None and ebt is not None:
        non_int_exp = round(rev - credit_loss - ebt, 2)
    if non_int_exp is not None:
        non_int_exp = abs(non_int_exp)

    trans_exp = _extract_multi_source_val(
        fs, "income", ["nu_TransactionalExpenses", "TransactionalExpenses", "TransactionExpenses", "CostOfTransactionalServices"], p, "transactional_expenses"
    )
    if trans_exp is not None:
        trans_exp = abs(trans_exp)

    prem_earned = _extract_multi_source_val(fs, "income", ["PremiumsEarnedNet", "PremiumsEarnedNetPropertyAndCasualty"], p, "net_premiums_earned")
    net_inv_inc = _extract_multi_source_val(fs, "income", ["NetInvestmentIncome", "InvestmentIncomeNet", "InterestAndDividendIncomeOperating"], p, "net_investment_income")
    inv_gains = _extract_multi_source_val(fs, "income", ["DebtAndEquitySecuritiesGainLoss", "RealizedInvestmentGainsLosses", "GainLossOnInvestments"], p)
    fees_other = _extract_multi_source_val(fs, "income", ["pgr_FeesAndOtherRevenues", "pgr_NonInsuranceServiceRevenues"], p)
    losses_lae = _extract_multi_source_val(
        fs,
        "income",
        ["PolicyholderBenefitsAndClaimsIncurredNet", "LiabilityForUnpaidClaimsAndClaimsAdjustmentExpenseIncurredClaims1", "IncurredClaimsPropertyCasualtyAndLiability"],
        p,
        ["losses_and_loss_expenses", "losses_and_lae"],
    )
    if losses_lae is not None:
        losses_lae = abs(losses_lae)
    dac_amort = _extract_multi_source_val(fs, "income", ["DeferredPolicyAcquisitionCostAmortizationExpense"], p)
    if dac_amort is not None:
        dac_amort = abs(dac_amort)
    other_uw_exp = _extract_multi_source_val(fs, "income", ["OtherUnderwritingExpense", "pgr_NonInsuranceServiceExpenses"], p, "other_underwriting_expenses")
    if other_uw_exp is not None:
        other_uw_exp = abs(other_uw_exp)
    tot_ben_exp = _extract_multi_source_val(fs, "income", ["BenefitsLossesAndExpenses"], p, "operating_expenses")
    if tot_ben_exp is None and losses_lae is not None:
        tot_ben_exp = round(losses_lae + (dac_amort or 0.0) + (other_uw_exp or 0.0), 2)
    if tot_ben_exp is not None:
        tot_ben_exp = abs(tot_ben_exp)

    rental_rev = _extract_multi_source_val(fs, "income", ["LeaseIncome", "OperatingLeasesIncomeStatementLeaseRevenue", "RealEstateRevenueNet"], p, "revenue")
    tenant_reimb = _extract_multi_source_val(fs, "income", ["TenantReimbursements", "OtherRealEstateRevenue", "OtherIncome"], p)
    prop_exp = _extract_multi_source_val(
        fs,
        "income",
        ["DirectCostsOfLeasedAndRentedPropertyOrEquipment", "o_DirectCostsOfLeasedAndRentedPropertyOrEquipmentIncludingReimbursableExpense"],
        p,
        ["property_operating_expenses", "cost_of_goods_sold"],
    )
    if prop_exp is not None:
        prop_exp = abs(prop_exp)
    noi = round(rev - prop_exp, 2) if (rev is not None and prop_exp is not None) else _extract_multi_source_val(fs, "income", [], p, ["noi", "gross_profit"])

    reit_da = _extract_multi_source_val(fs, "income", ["DepreciationDepletionAndAmortization", "DepreciationAndAmortization"], p, "depreciation_and_amortization")
    if reit_da is not None:
        reit_da = abs(reit_da)
    reit_ga = _extract_multi_source_val(fs, "income", ["GeneralAndAdministrativeExpense", "SellingGeneralAndAdministrativeExpense"], p, "ga_expense")
    if reit_ga is not None:
        reit_ga = abs(reit_ga)
    reit_imp = _extract_multi_source_val(fs, "income", ["ImpairmentOfRealEstate", "AssetImpairmentCharges"], p)
    if reit_imp is not None:
        reit_imp = abs(reit_imp)
    gain_sale = _extract_multi_source_val(fs, "income", ["GainLossOnSaleOfProperties", "o_GainOnSaleOfPropertiesContinuingOperations"], p)

    if archetype == "REAL_ESTATE_REIT" and noi is not None and reit_da is not None:
        ebit = round(noi - reit_da - (reit_ga or 0.0) - (reit_imp or 0.0), 2)
    elif archetype == "INSURANCE" and rev is not None and tot_ben_exp is not None:
        ebit = round(rev - tot_ben_exp, 2)

    if archetype == "FINANCIAL_BANKING":
        gp = cogs = ebit = None
    if archetype != "REAL_ESTATE_REIT":
        rental_rev = tenant_reimb = prop_exp = noi = reit_da = reit_ga = reit_imp = gain_sale = None
    if archetype != "INSURANCE":
        losses_lae = dac_amort = other_uw_exp = tot_ben_exp = prem_earned = net_inv_inc = inv_gains = fees_other = None

    return {
        "cogs": cogs,
        "gross_profit": gp,
        "operating_income": ebit,
        "interest_income": int_inc,
        "eps_basic": eps_b,
        "eps_diluted": eps_d,
        "shares_basic": sh_b,
        "shares_diluted": sh_d,
        "dps": dps_val,
        "net_interest_income": nii,
        "non_interest_income": non_int_inc,
        "non_interest_expense": non_int_exp,
        "transactional_expenses": trans_exp,
        "net_premiums_earned": prem_earned,
        "net_investment_income": net_inv_inc,
        "investment_gains_losses": inv_gains,
        "fees_and_other_revenues": fees_other,
        "losses_and_lae": losses_lae,
        "dac_amortization": dac_amort,
        "other_underwriting_expenses": other_uw_exp,
        "total_benefits_and_expenses": tot_ben_exp,
        "rental_revenue": rental_rev,
        "tenant_reimbursements_other": tenant_reimb,
        "property_operating_expenses": prop_exp,
        "noi": noi,
        "reit_da": reit_da,
        "reit_ga": reit_ga,
        "reit_impairment": reit_imp,
        "gain_on_sale_properties": gain_sale,
    }


def resolve_canonical_income_statement(fs, periods, archetype="STANDARD_CORPORATE"):
    """
    Función canónica y unificada (SSOT) para resolver el Estado de Resultados Estandarizado (10Y + LTM)
    adaptado dinámicamente por arquetipo contable según Fiscal.ai.
    """
    keys = (
        "revenue",
        "cogs",
        "gross_profit",
        "rd_expense",
        "sga_expense",
        "credit_loss_provision",
        "other_operating_expense",
        "total_operating_expenses",
        "operating_income",
        "interest_income",
        "interest_expense",
        "other_non_operating",
        "total_non_operating",
        "ebt",
        "income_tax",
        "net_income",
        "minority_interest_pnl",
        "preferred_dividends",
        "net_income_common",
        "eps_basic",
        "eps_diluted",
        "shares_basic",
        "shares_diluted",
        "dps",
        "net_interest_income",
        "non_interest_income",
        "non_interest_expense",
        "transactional_expenses",
        "share_of_associates",
        "net_premiums_earned",
        "net_investment_income",
        "investment_gains_losses",
        "fees_and_other_revenues",
        "losses_and_lae",
        "dac_amortization",
        "other_underwriting_expenses",
        "total_benefits_and_expenses",
        "rental_revenue",
        "tenant_reimbursements_other",
        "property_operating_expenses",
        "noi",
        "reit_da",
        "reit_ga",
        "reit_impairment",
        "gain_on_sale_properties",
    )
    res = {k: {} for k in keys}
    canonical = fs.get("canonical_summary", {}) if isinstance(fs, dict) else {}

    for p in periods:
        rev, cogs, gp, rd, sga, credit_loss, other_opex, tot_opex, ebit = _resolve_is_operating_section(fs, p, archetype)
        int_inc, int_exp, share_assoc, tax, ebt, ni, tot_non_op, other_non_op, min_int_pnl, pref_div, ni_comm = _resolve_is_nonop_tax_ni(
            fs, p, ebit, archetype
        )
        tail = _resolve_is_per_share_and_sectors(
            fs, canonical, periods, p, rev, ebt, credit_loss, int_inc, int_exp, ebit, gp, cogs, ni_comm, archetype
        )

        res["revenue"][p] = rev
        res["rd_expense"][p] = rd
        res["sga_expense"][p] = sga
        res["credit_loss_provision"][p] = credit_loss
        res["other_operating_expense"][p] = other_opex
        res["total_operating_expenses"][p] = tot_opex
        res["interest_expense"][p] = int_exp
        res["other_non_operating"][p] = other_non_op
        res["total_non_operating"][p] = tot_non_op
        res["ebt"][p] = ebt
        res["income_tax"][p] = tax
        res["net_income"][p] = ni
        res["minority_interest_pnl"][p] = min_int_pnl
        res["preferred_dividends"][p] = pref_div
        res["net_income_common"][p] = ni_comm
        res["share_of_associates"][p] = share_assoc
        for field_key, field_val in tail.items():
            res[field_key][p] = field_val

    return res


def _resolve_cf_operating(fs, p, archetype):
    """Resuelve partidas operativas del flujo de caja cerrando sum(hijos) == CFO."""
    ni = _extract_multi_source_val(fs, "cashflow", ["NetIncomeLoss", "ProfitLoss", "ProfitLossFromContinuingOperations"], p, "net_income")
    da = _extract_multi_source_val(
        fs,
        "cashflow",
        [
            "DepreciationDepletionAndAmortization",
            "DepreciationAmortizationAndAccretionNet",
            "Depreciation",
            "ifrs-full_AdjustmentsForDepreciationAndAmortisationExpense",
            "DepreciationAndAmortization",
        ],
        p,
        "depreciation_and_amortization",
    )
    if da is not None:
        da = abs(da)

    sbc = _extract_multi_source_val(
        fs,
        "cashflow",
        [
            "ShareBasedCompensation",
            "AllocatedShareBasedCompensationExpense",
            "AdjustmentsForSharebasedPayments",
            "ExpenseFromSharebasedPaymentTransactionsWithEmployees",
            "RestrictedStockExpense",
            "us-gaap_RestrictedStockExpense",
            "ShareBasedCompensationArrangementByShareBasedPaymentAwardExpense",
            "us-gaap_ShareBasedCompensationArrangementByShareBasedPaymentAwardExpense",
            "StockOptionPlanExpense",
            "us-gaap_StockOptionPlanExpense",
            "StockBasedCompensation",
            "meli_StockBasedCompensation",
        ],
        p,
        "stock_based_compensation",
    )
    if sbc is not None:
        sbc = abs(sbc)

    def_taxes = _extract_multi_source_val(
        fs,
        "cashflow",
        ["DeferredIncomeTaxExpenseBenefit", "DeferredIncomeTaxesAndTaxCredits", "ifrs-full_AdjustmentsForDeferredTaxExpense", "us-gaap_DeferredIncomeTaxesAndTaxCredits"],
        p,
    )
    other_nc = _extract_multi_source_sum(
        fs,
        "cashflow",
        [
            "OtherNoncashIncomeExpense",
            "ProvisionForLoanLeaseAndOtherLosses",
            "ProvisionForDoubtfulAccounts",
            "GainLossOnInvestments",
            "CreditLossAllowanceExpenses1",
            "UnrealizedGainLossOnInvestments",
            "ImpairmentOfRealEstate",
            "ImpairmentOfLongLivedAssetsHeldForUse",
            "GainLossOnSaleOfProperties",
            "us-gaap_OtherNoncashIncome",
            "meta_UnrealizedGainLossOnMarketableAndNonmarketableEquityInvestments",
            "o_OtherNoncashInterestIncomeExpenseOperating",
            "AmortizationOfFinancingCosts",
            "AdjustmentsNoncashItemsToReconcileNetIncomeLossToCashProvidedByUsedInOperatingActivities",
            "GainsLossesOnExtinguishmentOfDebt",
        ],
        p,
    )
    wc_ar = _extract_multi_source_sum(
        fs,
        "cashflow",
        [
            "IncreaseDecreaseInAccountsReceivable",
            "IncreaseDecreaseInOtherReceivables",
            "TradeAndOtherReceivablesNetCurrent",
            "meli_IncreaseDecreaseInFundsReceivableFromCustomers",
            "us-gaap_IncreaseDecreaseInAccountsReceivable",
        ],
        p,
    )
    wc_inv = _extract_multi_source_val(fs, "cashflow", ["IncreaseDecreaseInInventories"], p)
    wc_ap = _extract_multi_source_val(
        fs,
        "cashflow",
        [
            "IncreaseDecreaseInAccountsPayable",
            "IncreaseDecreaseInAccountsPayableTrade",
            "us-gaap_IncreaseDecreaseInAccountsPayableTrade",
            "IncreaseDecreaseInAccountsPayableAndAccruedLiabilities",
        ],
        p,
    )
    wc_other = _extract_multi_source_sum(
        fs,
        "cashflow",
        [
            "IncreaseDecreaseInOtherOperatingAssets",
            "IncreaseDecreaseInPrepaidDeferredExpenseAndOtherAssets",
            "IncreaseDecreaseInOtherOperatingLiabilities",
            "IncreaseDecreaseInOtherNoncurrentLiabilities",
            "IncreaseDecreaseInAccruedLiabilities",
            "IncreaseDecreaseInAccruedLiabilitiesAndOtherOperatingLiabilities",
            "IncreaseDecreaseInContractWithCustomerLiability",
            "IncreaseDecreaseInDeferredRevenue",
            "IncreaseDecreaseInOperatingLeaseLiability",
            "meli_IncreaseDecreaseInFundsPayableToCustomers",
            "meli_IncreaseDecreaseInAmountsPayableDueToCreditAndDebitCardTransactions",
            "IncreaseDecreaseInOperatingCapital",
        ],
        p,
    )

    banking_loans_cf = None
    banking_deposits_cf = None
    if archetype == "FINANCIAL_BANKING":
        loans_cf_cand = _extract_multi_source_sum(
            fs,
            "cashflow",
            ["nu_LoansToCustomersOne", "LoansToCustomersOne", "IncreaseDecreaseInLoansAndLeasesReceivable", "AdjustmentsForDecreaseIncreaseInLoansAndAdvancesToCustomers"],
            p,
        )
        cc_cf_cand = _extract_multi_source_sum(
            fs,
            "cashflow",
            [
                "ifrs-full_AdjustmentsForDecreaseIncreaseInOtherOperatingReceivables",
                "AdjustmentsForDecreaseIncreaseInOtherOperatingReceivables",
                "nu_CreditCardReceivablesCF",
                "IncreaseDecreaseInCreditCardReceivables",
            ],
            p,
        )
        banking_loans_cf = round((loans_cf_cand or 0.0) + (cc_cf_cand or 0.0), 2) if (loans_cf_cand or cc_cf_cand) else None
        banking_deposits_cf = _extract_multi_source_sum(
            fs,
            "cashflow",
            [
                "ifrs-full_AdjustmentsForIncreaseDecreaseInDepositsFromBanks",
                "AdjustmentsForIncreaseDecreaseInDepositsFromBanks",
                "AdjustmentsForIncreaseDecreaseInDepositsFromCustomers",
                "nu_DepositsCF",
                "IncreaseDecreaseInDepositLiabilities",
            ],
            p,
        )

    cfo = _extract_multi_source_val(
        fs,
        "cashflow",
        ["NetCashProvidedByUsedInOperatingActivities", "CashFlowsFromUsedInOperatingActivities", "NetCashProvidedByOperatingActivities", "ifrs-full_CashFlowsFromUsedInOperatingActivities"],
        p,
        "cash_from_operations",
    )
    if cfo is not None:
        sub_cfo = (
            (ni or 0.0)
            + (da or 0.0)
            + (sbc or 0.0)
            + (def_taxes or 0.0)
            + (wc_ar or 0.0)
            + (wc_inv or 0.0)
            + (wc_ap or 0.0)
            + (wc_other or 0.0)
            + (banking_loans_cf or 0.0)
            + (banking_deposits_cf or 0.0)
            + (other_nc or 0.0)
        )
        diff_cfo = round(cfo - sub_cfo, 2)
        if abs(diff_cfo) > 0.01:
            other_nc = round((other_nc or 0.0) + diff_cfo, 2)

    return ni, da, sbc, def_taxes, other_nc, wc_ar, wc_inv, wc_ap, wc_other, banking_loans_cf, banking_deposits_cf, cfo


def _resolve_cf_investing(fs, canonical, capital_flows, p):
    """Resuelve actividades de inversión cerrando sum(hijos) == CFI."""
    can_capex = canonical.get("capital_expenditures", {}).get(p)
    if can_capex is not None:
        capex = abs(float(can_capex))
    else:
        raw_cx = _extract_multi_source_val(
            fs,
            "cashflow",
            [
                "PaymentsToAcquirePropertyPlantAndEquipment",
                "PurchasesOfPropertyAndEquipmentAndIntangibleAssets",
                "nvda_PurchasesOfPropertyAndEquipmentAndIntangibleAssets",
                "PurchasesOfPropertyAndEquipment",
                "PaymentsToAcquireProductiveAssets",
                "PaymentsForPropertyPlantAndEquipment",
                "ifrs-full_PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities",
                "AcquisitionAndDevelopmentOfIntangibleAssets",
                "AcquisitionOfIntangibleAssets",
                "PurchaseOfIntangibleAssets",
                "PaymentsToAcquireIntangibleAssets",
                "PaymentsForCapitalImprovements",
            ],
            p,
        )
        capex = abs(raw_cx) if raw_cx is not None else None

    acq_ma = capital_flows["acquisitions_ma"].get(p)
    if acq_ma is None:
        acq_ma = _extract_multi_source_sum(
            fs,
            "cashflow",
            [
                "AcquisitionsNetOfCashAcquiredAndPurchasesOfIntangibleAndOtherAssets",
                "goog_AcquisitionsNetOfCashAcquiredAndPurchasesOfIntangibleAndOtherAssets",
                "PaymentsToAcquireBusinessesNetOfCashAcquired",
                "PaymentsToAcquireBusinessTwoNetOfCashAcquired",
                "PaymentsToAcquireBusinessesNetOfCashAcquiredAndPurchasesOfIntangibleAndOtherAssets",
                "PaymentsToAcquireCommercialRealEstate",
                "PaymentsToAcquireLoansReceivable",
                "PaymentsToAcquireInterestInSubsidiariesAndAffiliates",
            ],
            p,
        )
    if acq_ma is not None:
        acq_ma = abs(acq_ma)

    purch_inv = _extract_multi_source_sum(
        fs,
        "cashflow",
        [
            "PaymentsToAcquireAvailableForSaleSecuritiesDebt",
            "PaymentsToAcquireMarketableSecurities",
            "PaymentsToAcquireInvestments",
            "PaymentsToAcquireOtherInvestments",
            "PaymentsToAcquireEquitySecuritiesFvNi",
            "meta_PaymentsForEquitySecuritiesWithoutReadilyDeterminableFairValue",
            "meta_PaymentsForHeldForSaleAssets",
            "us-gaap_PaymentsToAcquireAvailableForSaleSecurities",
        ],
        p,
    )
    if purch_inv is not None:
        purch_inv = abs(purch_inv)

    sales_inv = _extract_multi_source_sum(
        fs,
        "cashflow",
        [
            "ProceedsFromSaleOfAvailableForSaleSecuritiesDebt",
            "ProceedsFromSaleOfMarketableSecurities",
            "ProceedsFromMaturitiesPrepaymentsAndCallsOfAvailableForSaleSecurities",
            "ProceedsFromMaturityOfMarketableSecurities",
            "ProceedsFromSaleAndMaturityOfMarketableSecurities",
            "ProceedsFromSaleOfAvailableForSaleSecurities",
            "ProceedsFromSaleOfEquitySecuritiesFvNi",
            "meta_ProceedsFromOneTimeVentureDistribution",
            "ProceedsFromSaleOfPropertyHeldForSale",
            "ProceedsFromCollectionOfNotesReceivable",
            "ProceedsFromDepositsOnRealEstateSales",
            "ProceedsFromInsuranceSettlementInvestingActivities",
            "ProceedsFromSaleMaturityAndCollectionsOfInvestments",
            "us-gaap_ProceedsFromSaleMaturityAndCollectionsOfInvestments",
        ],
        p,
    )
    other_inv = _extract_multi_source_sum(
        fs,
        "cashflow",
        [
            "PaymentsForProceedsFromOtherInvestingActivities",
            "ProceedsFromSaleOfRealEstate",
            "PaymentsToAcquireRealEstate",
            "IncreaseDecreaseInPrincipalLoansReceivableNet",
            "meli_IncreaseDecreaseInPrincipalLoansReceivableNet",
            "ProceedsFromSaleOfIntangibleAssets",
            "PaymentsForDerivativeInstrumentInvestingActivities",
            "ProceedsFromDerivativeInstrumentInvestingActivities",
        ],
        p,
    )
    cfi = _extract_multi_source_val(
        fs, "cashflow", ["NetCashProvidedByUsedInInvestingActivities", "CashFlowsFromUsedInInvestingActivities", "ifrs-full_CashFlowsFromUsedInInvestingActivities"], p, "cash_from_investing"
    )
    if cfi is not None:
        sub_cfi = -(capex or 0.0) - (acq_ma or 0.0) - (purch_inv or 0.0) + (sales_inv or 0.0) + (other_inv or 0.0)
        diff_cfi = round(cfi - sub_cfi, 2)
        if abs(diff_cfi) > 0.01:
            other_inv = round((other_inv or 0.0) + diff_cfi, 2)

    return capex, acq_ma, purch_inv, sales_inv, other_inv, cfi


def _resolve_cf_financing_and_cash_bridge(fs, canonical, capital_flows, periods, p, archetype, cfo, cfi, capex):
    """Resuelve financiación (CFF), puente de efectivo, FCF y AFFO."""
    di = capital_flows["debt_issuances"].get(p)
    dr = capital_flows["debt_repayments"].get(p)
    net_debt = capital_flows["net_debt_change"].get(p)
    cp = _extract_multi_source_val(fs, "cashflow", ["ProceedsFromRepaymentsOfCommercialPaper"], p)
    if cp is not None and net_debt is not None:
        net_debt = round(net_debt + cp, 2)

    stk_iss = capital_flows["stock_plans_proceeds"].get(p) or _extract_multi_source_val(
        fs, "cashflow", ["ProceedsFromIssuanceOfCommonStock", "ProceedsFromIssuanceOfShares"], p
    )
    rep_om = capital_flows["share_repurchases_open_market"].get(p)
    rep_tax = capital_flows["share_repurchases_sbc_tax"].get(p)
    div_paid = capital_flows["dividends_paid"].get(p)
    other_fin = _extract_multi_source_sum(
        fs,
        "cashflow",
        ["ProceedsFromPaymentsForOtherFinancingActivities", "IncreaseDecreaseInDeposits", "PaymentsForProceedsFromOtherFinancingActivities", "PaymentsOfDebtIssuanceCosts", "nu_LeasePayments"],
        p,
    )
    cff = _extract_multi_source_val(
        fs, "cashflow", ["NetCashProvidedByUsedInFinancingActivities", "CashFlowsFromUsedInFinancingActivities", "ifrs-full_CashFlowsFromUsedInFinancingActivities"], p, "cash_from_financing"
    )
    if cff is not None:
        sub_cff = (di or 0.0) - (dr or 0.0) + (stk_iss or 0.0) - (rep_om or 0.0) - (rep_tax or 0.0) - (div_paid or 0.0) + (other_fin or 0.0)
        diff_cff = round(cff - sub_cff, 2)
        if abs(diff_cff) > 0.01:
            other_fin = round((other_fin or 0.0) + diff_cff, 2)

    fx = _extract_multi_source_val(
        fs,
        "cashflow",
        [
            "EffectOfExchangeRateOnCashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
            "EffectOfExchangeRateOnCashAndCashEquivalents",
            "nu_ForeignExchangeRateChangesOnCashAndCashEquivalents",
            "ifrs-full_EffectOfExchangeRateChangesOnCashAndCashEquivalents",
        ],
        p,
    )
    net_chg_cash = _extract_multi_source_val(
        fs,
        "cashflow",
        [
            "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsPeriodIncreaseDecreaseIncludingExchangeRateEffect",
            "CashAndCashEquivalentsPeriodIncreaseDecrease",
            "ifrs-full_IncreaseDecreaseInCashAndCashEquivalents",
        ],
        p,
    )
    if net_chg_cash is None and cfo is not None and cfi is not None and cff is not None:
        net_chg_cash = round(cfo + cfi + cff + (fx or 0.0), 2)

    end_cash = _extract_multi_source_val(
        fs, "cashflow", ["CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents", "CashAndCashEquivalentsAtCarryingValue", "ifrs-full_CashAndCashEquivalents"], p
    ) or _extract_multi_source_val(
        fs, "balance_sheet", ["CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents", "CashAndCashEquivalentsAtCarryingValue", "Cash"], p
    )
    beg_cash = _extract_multi_source_val(
        fs,
        "cashflow",
        [
            "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsBeginningOfPeriod",
            "CashAndCashEquivalentsAtBeginningOfPeriod",
            "CashAndCashEquivalentsAtCarryingValueBeginningOfPeriod",
            "CashBeginningOfPeriod",
            "ifrs-full_CashAndCashEquivalentsAtBeginningOfPeriod",
        ],
        p,
    )

    if (beg_cash is None or (net_chg_cash is not None and beg_cash == net_chg_cash and end_cash != round(beg_cash * 2, 2))) and end_cash is not None and net_chg_cash is not None:
        beg_cash = round(end_cash - net_chg_cash, 2)

    if beg_cash is None and p != "LTM":
        annual_periods = [yr for yr in periods if yr != "LTM"]
        if p in annual_periods:
            p_idx = annual_periods.index(p)
            if p_idx + 1 < len(annual_periods):
                prior_yr = annual_periods[p_idx + 1]
                prior_end = _extract_multi_source_val(
                    fs,
                    "cashflow",
                    ["CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents", "CashAndCashEquivalentsAtCarryingValue", "ifrs-full_CashAndCashEquivalents"],
                    prior_yr,
                ) or _extract_multi_source_val(
                    fs,
                    "balance_sheet",
                    ["CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents", "CashAndCashEquivalentsAtCarryingValue", "Cash"],
                    prior_yr,
                )
                if prior_end is not None:
                    beg_cash = float(prior_end)

    if net_chg_cash is None and end_cash is not None and beg_cash is not None:
        net_chg_cash = round(end_cash - beg_cash, 2)

    can_fcf = canonical.get("free_cash_flow", {}).get(p)
    if archetype in ("FINANCIAL_BANKING", "INSURANCE"):
        fcf = None
    elif archetype == "REAL_ESTATE_REIT":
        fcf = round(cfo - capex, 2) if (cfo is not None and capex is not None) else None
    elif can_fcf is not None:
        fcf = float(can_fcf)
    elif cfo is not None and capex is not None:
        fcf = round(cfo - capex, 2)
    else:
        fcf = None

    affo_val = canonical.get("affo", {}).get(p)
    if affo_val is None and archetype == "REAL_ESTATE_REIT":
        ffo_val = canonical.get("ffo", {}).get(p)
        if ffo_val is not None:
            rec_c = canonical.get("recurring_capex_maintenance", {}).get(p)
            deduct_c = float(rec_c) if rec_c is not None else (float(capex) if capex is not None else 0.0)
            affo_val = round(float(ffo_val) - deduct_c, 2)
        else:
            affo_val = can_fcf

    return di, dr, net_debt, stk_iss, rep_om, rep_tax, div_paid, other_fin, cff, fx, beg_cash, net_chg_cash, end_cash, fcf, affo_val


def resolve_canonical_cash_flow(fs, periods, capital_flows=None, archetype="STANDARD_CORPORATE"):
    """
    Función canónica y unificada (SSOT) para resolver el Estado de Flujos de Caja en 4 secciones
    según Fiscal.ai, integrando capital allocation auditado y respetando la Regla 6.
    """
    if capital_flows is None:
        capital_flows = resolve_canonical_capital_flows(fs, periods)
    canonical = fs.get("canonical_summary", {}) if isinstance(fs, dict) else {}

    res = {
        k: {}
        for k in (
            "net_income",
            "da",
            "sbc",
            "deferred_taxes",
            "other_noncash",
            "wc_ar",
            "wc_inv",
            "wc_ap",
            "wc_other",
            "banking_loans_cf",
            "banking_deposits_cf",
            "cfo",
            "capex",
            "acquisitions_ma",
            "purchases_investments",
            "sales_maturities_investments",
            "other_investing",
            "cfi",
            "debt_issued",
            "debt_repaid",
            "net_debt_issued",
            "stock_issued",
            "share_repurchases_open_market",
            "share_repurchases_sbc_tax",
            "dividends_paid",
            "other_financing",
            "cff",
            "fx_effect",
            "beginning_cash",
            "net_change_in_cash",
            "ending_cash",
            "fcf",
            "affo",
        )
    }

    for p in periods:
        ni, da, sbc, def_taxes, other_nc, wc_ar, wc_inv, wc_ap, wc_other, banking_loans_cf, banking_deposits_cf, cfo = _resolve_cf_operating(
            fs, p, archetype
        )
        capex, acq_ma, purch_inv, sales_inv, other_inv, cfi = _resolve_cf_investing(fs, canonical, capital_flows, p)
        di, dr, net_debt, stk_iss, rep_om, rep_tax, div_paid, other_fin, cff, fx, beg_cash, net_chg_cash, end_cash, fcf, affo_val = _resolve_cf_financing_and_cash_bridge(
            fs, canonical, capital_flows, periods, p, archetype, cfo, cfi, capex
        )

        res["net_income"][p] = ni
        res["da"][p] = da
        res["sbc"][p] = sbc
        res["deferred_taxes"][p] = def_taxes
        res["other_noncash"][p] = other_nc
        res["wc_ar"][p] = wc_ar
        res["wc_inv"][p] = wc_inv
        res["wc_ap"][p] = wc_ap
        res["wc_other"][p] = wc_other
        res["banking_loans_cf"][p] = banking_loans_cf
        res["banking_deposits_cf"][p] = banking_deposits_cf
        res["cfo"][p] = cfo
        res["capex"][p] = capex
        res["acquisitions_ma"][p] = acq_ma
        res["purchases_investments"][p] = purch_inv
        res["sales_maturities_investments"][p] = sales_inv
        res["other_investing"][p] = other_inv
        res["cfi"][p] = cfi
        res["debt_issued"][p] = di
        res["debt_repaid"][p] = dr
        res["net_debt_issued"][p] = net_debt
        res["stock_issued"][p] = stk_iss
        res["share_repurchases_open_market"][p] = rep_om
        res["share_repurchases_sbc_tax"][p] = rep_tax
        res["dividends_paid"][p] = div_paid
        res["other_financing"][p] = other_fin
        res["cff"][p] = cff
        res["fx_effect"][p] = fx
        res["beginning_cash"][p] = beg_cash
        res["net_change_in_cash"][p] = net_chg_cash
        res["ending_cash"][p] = end_cash
        res["fcf"][p] = fcf
        res["affo"][p] = affo_val

    return res
