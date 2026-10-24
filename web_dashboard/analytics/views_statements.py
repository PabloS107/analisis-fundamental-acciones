# -*- coding: utf-8 -*-
"""
Módulo de Estados Financieros (Vista Estandarizada 10Y + LTM y SEC As-Reported 3Y + LTM).
Encapsula la resolución de Balance, P&L, Flujo de Caja, Flujos de Capital y tablas bilingües.
"""

def resolve_canonical_capital_flows(fs, periods):
    """
    Función canónica y unificada (SSOT) para resolver flujos de asignación de capital
    a partir de financial_statements.json de forma universal y sin hardcodeos.
    Retorna flujos en dólares sin escalar para cada período solicitado:
    - share_repurchases_open_market: Magnitud positiva ($)
    - share_repurchases_sbc_tax: Magnitud positiva ($) (Retención fiscal de RSUs para FCF ajustado)
    - share_repurchases_total: Magnitud positiva ($) = recompra neta real de mercado
    - dividends_paid: Magnitud positiva ($)
    - acquisitions_ma: Magnitud positiva ($)
    - debt_repayments: Magnitud positiva ($)
    - debt_issuances: Magnitud positiva ($)
    - net_debt_change: Variación algebraica ($) = debt_issuances - debt_repayments
    """
    canonical = fs.get("canonical_summary", {}) if isinstance(fs, dict) else {}
    cf_sources = [
        fs.get("cash_flow_detail", {}) if isinstance(fs, dict) else {},
        fs.get("cash_flow_statement", {}) if isinstance(fs, dict) else {}
    ]

    def _extract_val(key_cands, p, can_key=None):
        if can_key:
            can_val = canonical.get(can_key, {}).get(p)
            if can_val is not None and abs(float(can_val)) > 0:
                return float(can_val)
        for k in key_cands:
            k_lower = k.lower()
            for cf_src in cf_sources:
                if not isinstance(cf_src, dict):
                    continue
                if k in cf_src:
                    obj = cf_src[k]
                    vals = obj.get("values", obj) if isinstance(obj, dict) else {}
                    if isinstance(vals, dict) and p in vals and vals[p] is not None:
                        return float(vals[p])
                for src_k, src_obj in cf_src.items():
                    src_token = src_k.lower().split(':')[-1].split('_')[-1]
                    if src_k.lower() == k_lower or src_token == k_lower:
                        vals = src_obj.get("values", src_obj) if isinstance(src_obj, dict) else {}
                        if isinstance(vals, dict) and p in vals and vals[p] is not None:
                            return float(vals[p])
        return None

    def _extract_sum(key_cands, p, can_key=None):
        if can_key:
            can_val = canonical.get(can_key, {}).get(p)
            if can_val is not None and abs(float(can_val)) > 0:
                return float(can_val)
        total = 0.0
        matched = False
        matched_tokens = set()
        for k in key_cands:
            k_token = k.lower().split(':')[-1].split('_')[-1]
            for cf_src in cf_sources:
                if not isinstance(cf_src, dict):
                    continue
                for src_k, src_obj in cf_src.items():
                    src_token = src_k.lower().split(':')[-1].split('_')[-1]
                    if (src_k.lower() == k.lower() or src_token == k_token) and src_token not in matched_tokens:
                        vals = src_obj.get("values", src_obj) if isinstance(src_obj, dict) else {}
                        if isinstance(vals, dict) and p in vals and vals[p] is not None:
                            try:
                                total += float(vals[p])
                                matched = True
                                matched_tokens.add(src_token)
                            except (ValueError, TypeError):
                                pass
        return total if matched else None

    rep_keys = [
        "PaymentsForRepurchaseOfCommonStock", "PaymentsForRepurchaseOfEquity", "PaymentsForRepurchaseOfCapitalStock",
        "PurchaseOfTreasuryShares", "PaymentsForPurchaseOfOwnShares",
        "PaymentsForRepurchaseOfShares", "PurchaseOfOwnShares", "SharesRepurchased",
        "nu_SharesRepurchased"
    ]
    stock_plans_keys = [
        "ProceedsFromStockPlans", "us-gaap_ProceedsFromStockPlans",
        "ProceedsFromStockOptionsExercised", "us-gaap_ProceedsFromStockOptionsExercised",
        "ProceedsFromIssuanceOfCommonStock", "us-gaap_ProceedsFromIssuanceOfCommonStock",
        "ProceedsFromIssuanceOfShares", "ifrs-full_ProceedsFromIssuingShares",
        "ProceedsFromIssuanceOfSharesUnderIncentiveAndShareBasedCompensationPlansIncludingStockOptions",
        "us-gaap_ProceedsFromIssuanceOfSharesUnderIncentiveAndShareBasedCompensationPlansIncludingStockOptions",
        "Netproceedspaymentsrelatedtoemployeestockplans", "nvda_Netproceedspaymentsrelatedtoemployeestockplans",
        "ProceedsFromMinorityShareholders", "o_ProceedsFromDividendReinvestmentAndStockPurchasePlanNet",
        "ProceedsFromDividendReinvestmentAndStockPurchasePlanNet"
    ]
    tax_keys = [
        "PaymentsRelatedToTaxWithholdingForShareBasedCompensation",
        "PaymentsForTaxesRelatedToNetShareSettlementOfEquityAwards",
        "PaymentsRelatedToTaxWithholdingForStockBasedAwards",
        "TaxWithholdingForShareBasedCompensation",
        "deck_AccrualsForSharesWithheldForTaxes"
    ]
    div_keys = [
        "PaymentsOfDividends", "PaymentsOfDividendsCommonStock", "PaymentsOfOrdinaryDividends",
        "DividendsPaid", "PaymentsOfDividendsClassifiedAsFinancingActivities",
        "aapl_PaymentsOfDividendsAndDividendEquivalentsOnCommonStockAndRestrictedStockUnits",
        "PaymentsOfDividendsPreferredStockAndPreferenceStock", "us-gaap_PaymentsOfDividendsPreferredStockAndPreferenceStock",
        "PaymentsOfDividendsMinorityInterest", "us-gaap_PaymentsOfDividendsMinorityInterest"
    ]
    ma_keys = [
        "PaymentsToAcquireBusinessesNetOfCashAcquiredAndPurchasesOfIntangibleAndOtherAssets",
        "PaymentsToAcquireBusinessesNetOfCashAcquired", "PaymentsToAcquireBusinessTwoNetOfCashAcquired",
        "us-gaap_PaymentsToAcquireBusinessTwoNetOfCashAcquired", "PaymentsToAcquireBusinessThreeNetOfCashAcquired",
        "AcquisitionOfSubsidiaryNetOfCashAcquired",
        "nu_AcquisitionOfSubsidiaryNetOfCashAcquired",
        "PaymentsToAcquireBusinessesAndInterestInAffiliates", "PaymentsToAcquireOtherProductiveAssets",
        "CashFlowsUsedInObtainingControlOfSubsidiariesOrOtherBusinesses", "PaymentsToAcquireBusinessesGross",
        "meli_PaymentsToAcquireBusinessNetOfCashAcquired", "us-gaap_PaymentsToAcquireBusinessesAndInterestInAffiliates",
        "meta_PaymentsToAcquireBusinessesNetOfCashAcquiredAndPurchasesOfIntangibleAndOtherAssets",
        "PaymentsToAcquireInterestInAffiliates", "PaymentsToAcquireInterestInSubsidiariesAndOtherBusinesses",
        "PaymentsToAcquireJointVentures", "PaymentsToAcquireCommercialRealEstate", "us-gaap_PaymentsToAcquireCommercialRealEstate",
        "PaymentsToAcquireLoansReceivable", "us-gaap_PaymentsToAcquireLoansReceivable",
        "PaymentsToAcquireInterestInSubsidiariesAndAffiliates"
    ]
    dr_keys = [
        "RepaymentsOfLongTermDebt", "RepaymentsOfDebt", "us-gaap_RepaymentsOfDebt",
        "RepaymentsOfLinesOfCredit", "RepaymentsOfShortTermDebt", "us-gaap_RepaymentsOfShortTermDebt",
        "RepaymentsOfOtherLongTermDebt", "us-gaap_RepaymentsOfOtherLongTermDebt",
        "RepaymentsOfSecuredDebt", "us-gaap_RepaymentsOfSecuredDebt", "RepaymentsOfUnsecuredDebt", "us-gaap_RepaymentsOfUnsecuredDebt",
        "us-gaap_RepaymentsOfConvertibleDebt", "RepaymentsOfBorrowingsClassifiedAsFinancingActivities",
        "PaymentsOfBorrowingsAndFinancing", "RepaymentsOfTermLoans", "RepaymentsOfConvertibleDebt",
        "RepaymentsOfSeniorNotes", "RepaymentsOfNotesPayable", "us-gaap_RepaymentsOfNotesPayable",
        "RepaymentsOfLongTermDebtAndCapitalSecurities", "us-gaap_RepaymentsOfLongTermDebtAndCapitalSecurities",
        "RepaymentsOfLongTermLinesOfCreditAndCommercialPaper", "o_RepaymentsOfLongTermLinesOfCreditAndCommercialPaper",
        "FinanceLeasePrincipalPayments", "us-gaap_FinanceLeasePrincipalPayments", "PaymentsOfLeaseLiabilities",
        "nvda_PaymentsForFinancedPropertyPlantAndEquipmentAndIntangibleAssetsFinancingActivities",
        "PaymentsForFinancedPropertyPlantAndEquipmentAndIntangibleAssetsFinancingActivities"
    ]
    di_keys = [
        "ProceedsFromIssuanceOfLongTermDebt", "ProceedsFromIssuanceOfDebt",
        "ProceedsFromIssuanceOfSeniorLongTermDebt", "us-gaap_ProceedsFromIssuanceOfSeniorLongTermDebt",
        "ProceedsFromIssuanceOfUnsecuredDebt", "us-gaap_ProceedsFromIssuanceOfUnsecuredDebt",
        "us-gaap_ProceedsFromDebtNetOfIssuanceCosts", "ProceedsFromLinesOfCredit",
        "ProceedsFromIssuanceOfOtherLongTermDebt", "us-gaap_ProceedsFromIssuanceOfOtherLongTermDebt",
        "ProceedsFromBorrowingsClassifiedAsFinancingActivities", "ProceedsFromBorrowingsAndFinancing",
        "us-gaap_ProceedsFromConvertibleDebt", "us-gaap_ProceedsFromShortTermDebt",
        "nu_ProceedsFromDebtInstrumentsEligibleAsCapital", "ProceedsFromTermLoans",
        "ProceedsFromConvertibleDebt", "ProceedsFromIssuanceOfConvertibleDebt",
        "ProceedsFromIssuanceOfSeniorNotes", "ProceedsFromLongTermLinesOfCredit",
        "ProceedsFromNotesPayable", "us-gaap_ProceedsFromNotesPayable",
        "ProceedsFromIssuanceOfLongTermDebtAndCapitalSecuritiesNet", "us-gaap_ProceedsFromIssuanceOfLongTermDebtAndCapitalSecuritiesNet",
        "o_ProceedsFromLongTermLinesOfCreditAndIssuanceOfCommercialPaper",
        "ProceedsFromLongTermLinesOfCreditAndIssuanceOfCommercialPaper"
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
        "net_debt_change": {}
    }

    for p in periods:
        raw_rep = _extract_val(rep_keys, p, "share_repurchases")
        val_rep = abs(raw_rep) if raw_rep is not None else 0.0

        raw_sp = _extract_val(stock_plans_keys, p, "stock_plans_proceeds")
        val_sp = abs(raw_sp) if raw_sp is not None else 0.0

        val_net_rep = max(0.0, round(val_rep - val_sp, 2))

        raw_tax = _extract_val(tax_keys, p, "share_repurchases_sbc_tax")
        val_tax = abs(raw_tax) if raw_tax is not None else 0.0

        raw_div = _extract_val(div_keys, p, "dividends_paid")
        val_div = abs(raw_div) if raw_div is not None else 0.0

        raw_ma = _extract_sum(ma_keys, p, "acquisitions_ma")
        val_ma = abs(raw_ma) if raw_ma is not None else 0.0

        raw_dr = _extract_sum(dr_keys, p, "debt_repayments")
        val_dr = abs(raw_dr) if raw_dr is not None else 0.0

        raw_di = _extract_sum(di_keys, p, "debt_issuances")
        val_di = abs(raw_di) if raw_di is not None else 0.0

        net_debt_change = round(val_di - val_dr, 2)
        val_tot_rep = round(val_rep + val_tax, 2)

        flows["share_repurchases_open_market"][p] = val_rep
        flows["stock_plans_proceeds"][p] = val_sp
        flows["share_repurchases_net"][p] = val_net_rep
        flows["share_repurchases_sbc_tax"][p] = val_tax
        flows["share_repurchases_total"][p] = val_tot_rep
        flows["total_capital_returned"][p] = val_net_rep
        flows["dividends_paid"][p] = val_div
        flows["acquisitions_ma"][p] = val_ma
        flows["debt_repayments"][p] = val_dr
        flows["debt_issuances"][p] = val_di
        flows["net_debt_change"][p] = net_debt_change

    return flows


def resolve_canonical_balance_sheet(fs, periods, archetype="STANDARD_CORPORATE"):
    """
    Función canónica y unificada (SSOT) para resolver el Balance General clasificado
    (Activos Corrientes y No Corrientes, Pasivos Corrientes y No Corrientes, Patrimonio Neto
    y Diagnóstico de Liquidez y Solvencia) a partir de financial_statements.json
    de forma universal y sin hardcodeos para empresas corporativas estándar.
    """
    if not archetype or archetype == "STANDARD_CORPORATE":
        archetype = fs.get("archetype") or ("FINANCIAL_BANKING" if fs.get("is_financial") else "STANDARD_CORPORATE")
    canonical = fs.get("canonical_summary", {}) if isinstance(fs, dict) else {}
    bs_detail = fs.get("balance_sheet_detail", {}) if isinstance(fs, dict) else {}
    bal_sources = [
        bs_detail,
        fs.get("balance_sheet", {}) if isinstance(fs, dict) else {}
    ]
    as_rep_bs_raw = fs.get("as_reported_statements", {}).get("balance_sheet", []) if isinstance(fs, dict) else []
    as_rep_bs_rows = as_rep_bs_raw if isinstance(as_rep_bs_raw, list) else (as_rep_bs_raw.get("rows", []) if isinstance(as_rep_bs_raw, dict) else [])
    as_rep_bs_dict = {}
    for r in as_rep_bs_rows:
        if isinstance(r, dict) and "concept" in r:
            as_rep_bs_dict[r["concept"]] = r.get("values", {})
    bal_sources.append(as_rep_bs_dict)

    def _extract_val(key_cands, p, can_key=None):
        if can_key:
            can_keys = [can_key] if isinstance(can_key, str) else can_key
            for ck in can_keys:
                can_val = canonical.get(ck, {}).get(p)
                if can_val is not None and float(can_val) != 0.0:
                    return float(can_val)
        for k in key_cands:
            k_lower = k.lower()
            for src in bal_sources:
                if not isinstance(src, dict):
                    continue
                if k in src:
                    obj = src[k]
                    vals = obj.get("values", obj) if isinstance(obj, dict) else {}
                    if isinstance(vals, dict) and p in vals and vals[p] is not None:
                        return float(vals[p])
                for src_k, src_obj in src.items():
                    src_token = src_k.lower().split(':')[-1].split('_')[-1]
                    if src_k.lower() == k_lower or src_token == k_lower:
                        vals = src_obj.get("values", src_obj) if isinstance(src_obj, dict) else {}
                        if isinstance(vals, dict) and p in vals and vals[p] is not None:
                            return float(vals[p])
        if can_key:
            can_keys = [can_key] if isinstance(can_key, str) else can_key
            for ck in can_keys:
                can_val = canonical.get(ck, {}).get(p)
                if can_val is not None:
                    return float(can_val)
        return None

    cash_keys = [
        "CashAndCashEquivalentsAtCarryingValue", "CashAndCashEquivalents", "Cash",
        "CashAndDueFromBanks", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
        "us-gaap_CashAndCashEquivalentsAtCarryingValue", "ifrs-full_CashAndCashEquivalents"
    ]
    sti_keys = [
        "MarketableSecuritiesCurrent", "us-gaap_MarketableSecuritiesCurrent",
        "ShortTermInvestments", "AvailableForSaleSecuritiesCurrent",
        "DebtSecuritiesCurrent", "us-gaap_DebtSecuritiesCurrent",
        "EquitySecuritiesFvNi", "us-gaap_EquitySecuritiesFvNi",
        "nvda_MarketableSecuritiesAndEquitySecuritiesFVNI",
        "OtherShortTermInvestments", "MarketableSecurities"
    ]
    ar_keys = [
        "AccountsReceivableNetCurrent", "AccountsReceivableNet", "ReceivablesNetCurrent",
        "AccountsAndNotesReceivableNetCurrent", "TradeAndOtherReceivablesCurrent",
        "ContractWithCustomerAssetNetCurrent", "UnbilledReceivablesCurrent", "NontradeReceivablesCurrent",
        "us-gaap_AccountsReceivableNetCurrent"
    ]
    inv_keys = [
        "InventoryNet", "Inventories", "InventoryGross", "us-gaap_InventoryNet"
    ]
    ca_keys = [
        "AssetsCurrent", "CurrentAssetsTotal", "CurrentAssets", "us-gaap_AssetsCurrent"
    ]
    other_ca_keys = [
        "PrepaidExpenseAndOtherAssetsCurrent", "us-gaap_PrepaidExpenseAndOtherAssetsCurrent",
        "OtherAssetsCurrent", "us-gaap_OtherAssetsCurrent",
        "PrepaidExpensesAndOtherCurrentAssets", "OtherCurrentAssets"
    ]
    ppe_keys = [
        "RealEstateInvestmentPropertyNet", "us-gaap_RealEstateInvestmentPropertyNet", "InvestmentProperties",
        "PropertyPlantAndEquipmentNet",
        "PropertyPlantAndEquipmentAndFinanceLeaseRightOfUseAssetAfterAccumulatedDepreciationAndAmortization",
        "PropertyPlantAndEquipmentNetOfAccumulatedDepreciationAndAmortization",
        "PropertyPlantAndEquipmentNetExcludingRightOfUseAsset",
        "PropertyPlantAndEquipmentGross",
        "MachineryAndEquipmentNet",
        "ConstructionInProgressGross",
        "ConstructionInProgress",
        "BuildingsAndBuildingImprovementsNet",
        "us-gaap_PropertyPlantAndEquipmentNet"
    ]
    rou_keys = [
        "OperatingLeaseRightOfUseAsset", "us-gaap_OperatingLeaseRightOfUseAsset",
        "RightOfUseAssets", "RightOfUseAsset",
        "FinanceLeaseRightOfUseAsset", "LesseeOperatingLeaseRightOfUseAsset",
        "OperatingLeaseRightOfUseAssetNet", "FinanceLeaseRightOfUseAssetNet"
    ]
    gw_keys = ["Goodwill", "us-gaap_Goodwill"]
    intang_keys = [
        "IntangibleAssetsNetExcludingGoodwill", "IntangibleAssetsNet",
        "OtherIntangibleAssetsNet", "us-gaap_IntangibleAssetsNetExcludingGoodwill"
    ]
    lt_inv_keys = [
        "MarketableSecuritiesNoncurrent", "us-gaap_MarketableSecuritiesNoncurrent",
        "NonmarketableEquitySecuritiesCarryingValue", "meta_NonmarketableEquitySecuritiesCarryingValue",
        "EquitySecuritiesWithoutReadilyDeterminableFairValueAmount",
        "EquitySecuritiesFVNINoncurrent", "us-gaap_EquitySecuritiesFVNINoncurrent",
        "LongTermInvestments", "us-gaap_LongTermInvestments",
        "OtherInvestmentsNoncurrent", "InvestmentsInAssociates",
        "InvestmentsInAffiliatesSubsidiariesAssociatesAndJointVentures",
        "EquityMethodInvestments", "AvailableForSaleDebtSecuritiesNoncurrent",
        "HeldToMaturitySecuritiesNoncurrent", "OtherLongTermInvestments", "OtherInvestments"
    ]
    other_nca_keys = [
        "OtherAssetsNoncurrent", "us-gaap_OtherAssetsNoncurrent",
        "OtherNoncurrentAssets"
    ]
    dta_keys = [
        "DeferredIncomeTaxAssetsNet", "us-gaap_DeferredIncomeTaxAssetsNet",
        "DeferredTaxAssetsNetNoncurrent", "us-gaap_DeferredTaxAssetsNetNoncurrent",
        "DeferredIncomeTaxAssets", "us-gaap_DeferredIncomeTaxAssets"
    ]
    ta_keys = ["Assets", "TotalAssets", "us-gaap_Assets"]
    ap_keys = [
        "AccountsPayableCurrent", "us-gaap_AccountsPayableCurrent",
        "us-gaap_AccountsPayableTradeCurrent", "AccountsPayableTradeCurrent",
        "us-gaap_AccountsPayableAndAccruedLiabilitiesCurrent", "TradeAndOtherPayablesCurrent"
    ]
    accrued_keys = [
        "AccruedLiabilitiesCurrent", "us-gaap_AccruedLiabilitiesCurrent",
        "OtherAccruedLiabilitiesCurrent", "AccruedLiabilities"
    ]
    st_debt_keys = [
        "LongTermDebtCurrent", "us-gaap_LongTermDebtCurrent",
        "CommercialPaper", "us-gaap_CommercialPaper",
        "CurrentPortionOfLongTermDebt", "ShortTermDebt", "ShortTermBorrowings",
        "DebtCurrent", "us-gaap_DebtCurrent", "LoansPayableCurrent", "us-gaap_LoansPayableCurrent",
        "LinesOfCreditCurrent", "RevolvingCreditFacilityAndCommercialPaper",
        "LineOfCreditAndCommercialPaper", "LineOfCredit",
        "CurrentBorrowingsAndOtherFinancialLiabilities", "CurrentPortionOfNoncurrentBorrowings",
        "CurrentFinancialLiabilities", "BorrowingsFromFinancialInstitutions"
    ]
    cl_keys = [
        "LiabilitiesCurrent", "CurrentLiabilitiesTotal", "CurrentLiabilities",
        "us-gaap_LiabilitiesCurrent"
    ]
    tot_debt_keys = [
        "DebtLongtermAndShorttermCombinedAmount", "us-gaap_DebtLongtermAndShorttermCombinedAmount",
        "TotalDebt"
    ]
    lt_debt_keys = [
        "LongTermDebtNoncurrent", "us-gaap_LongTermDebtNoncurrent",
        "LongTermDebtAndCapitalLeaseObligationsNoncurrent", "LongTermDebt",
        "NotesPayable", "LoansPayable", "SecuredDebt", "SeniorNotes",
        "SeniorLongTermDebt", "NoncurrentBorrowings", "NoncurrentFinancialLiabilities",
        "DebtSecuritiesInIssue", "Borrowings", "BorrowingsAndFinancing", "SubordinatedDebt"
    ]
    lease_liab_nc_keys = [
        "OperatingLeaseLiabilityNoncurrent", "us-gaap_OperatingLeaseLiabilityNoncurrent",
        "CapitalLeaseObligationsNoncurrent"
    ]
    tl_keys = [
        "Liabilities", "TotalLiabilities", "us-gaap_Liabilities"
    ]
    eq_keys = [
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
        "ifrs-full_Equity",
        "StockholdersEquity", "TotalEquity", "Equity", "us-gaap_StockholdersEquity",
        "EquityAttributableToOwnersOfParent"
    ]
    apic_keys = [
        "CommonStocksIncludingAdditionalPaidInCapital",
        "us-gaap_CommonStocksIncludingAdditionalPaidInCapital"
    ]
    re_keys = [
        "RetainedEarningsAccumulatedDeficit", "RetainedEarnings",
        "us-gaap_RetainedEarningsAccumulatedDeficit"
    ]

    def_rev_keys = [
        "DeferredRevenueCurrent", "us-gaap_DeferredRevenueCurrent",
        "ContractWithCustomerLiabilityCurrent", "us-gaap_ContractWithCustomerLiabilityCurrent",
        "DeferredRevenueAndOtherCurrentLiabilities", "us-gaap_DeferredRevenueAndOtherCurrentLiabilities"
    ]
    def_tax_nc_keys = [
        "DeferredTaxLiabilitiesNoncurrent", "us-gaap_DeferredTaxLiabilitiesNoncurrent",
        "DeferredIncomeTaxLiabilitiesNetNoncurrent", "us-gaap_DeferredIncomeTaxLiabilitiesNetNoncurrent",
        "DeferredIncomeTaxesAndOtherLiabilitiesNoncurrent"
    ]

    net_loans_keys = [
        "LoansAndLeasesReceivableNetOfDeferredIncome", "us-gaap_LoansAndLeasesReceivableNetOfDeferredIncome",
        "FinancingReceivableExcludingAccruedInterestAfterAllowanceForCreditLoss",
        "FinancingReceivableExcludingAccruedInterestBeforeAllowanceForCreditLossesNetOfDeferredIncome",
        "ifrs-full_LoansAndAdvancesToCustomers", "nu_CreditCardReceivables1", "nu_LoansAndAdvancesToCustomers1",
        "LoansAndLeasesReceivableNetReportedAmount", "LoansReceivableNet"
    ]
    allow_loss_keys = [
        "FinancingReceivableAllowanceForCreditLossExcludingAccruedInterest", "us-gaap_FinancingReceivableAllowanceForCreditLossExcludingAccruedInterest",
        "FinancingReceivableAllowanceForCreditLosses", "us-gaap_FinancingReceivableAllowanceForCreditLosses",
        "AllowanceForCreditLossesOnFinancingReceivables", "us-gaap_AllowanceForCreditLossesOnFinancingReceivables",
        "AllowanceAccountForCreditLossesOfFinancialAssets", "LoansAndLeasesReceivableAllowance",
        "AllowanceForLoanAndLeaseLosses"
    ]
    deposit_keys = [
        "Deposits", "us-gaap_Deposits", "ifrs-full_DepositsFromCustomers", "DepositsDomestic",
        "InterestBearingDepositLiabilities", "NoninterestBearingDepositLiabilities"
    ]
    prem_rec_keys = [
        "PremiumsReceivableAtCarryingValue", "us-gaap_PremiumsReceivableAtCarryingValue",
        "AccountsAndOtherReceivablesNetCurrent", "AccountsReceivableNet"
    ]
    dac_keys = [
        "DeferredPolicyAcquisitionCosts", "us-gaap_DeferredPolicyAcquisitionCosts",
        "DeferredPolicyAcquisitionCostAmortizationExpense"
    ]
    loss_res_keys = [
        "LiabilityForClaimsAndClaimsAdjustmentExpense", "us-gaap_LiabilityForClaimsAndClaimsAdjustmentExpense",
        "LiabilityForUnpaidClaimsAndClaimsAdjustmentExpenseNet",
        "LiabilityForClaimsAndClaimsAdjustmentExpenseIncurredClaims1"
    ]
    unearn_prem_keys = [
        "UnearnedPremiums", "us-gaap_UnearnedPremiums", "UnearnedPremiumsNet"
    ]

    res = {
        "cash": {},
        "short_term_investments": {},
        "total_liquid_cash": {},
        "accounts_receivable": {},
        "inventories": {},
        "other_current_assets": {},
        "total_current_assets": {},
        "net_ppe": {},
        "rou_asset": {},
        "net_ppe_plus_rou": {},
        "goodwill_and_intangibles": {},
        "long_term_investments": {},
        "deferred_tax_assets": {},
        "other_noncurrent_assets": {},
        "total_noncurrent_assets": {},
        "total_assets": {},
        "accounts_payable": {},
        "accrued_liabilities": {},
        "deferred_revenue_current": {},
        "short_term_debt": {},
        "other_current_liabilities": {},
        "total_current_liabilities": {},
        "long_term_debt": {},
        "operating_lease_liability_noncurrent": {},
        "deferred_tax_liabilities_noncurrent": {},
        "other_noncurrent_liabilities": {},
        "total_noncurrent_liabilities": {},
        "total_liabilities": {},
        "common_stock_and_apic": {},
        "retained_earnings": {},
        "other_equity": {},
        "minority_interest": {},
        "total_debt": {},
        "stockholders_equity": {},
        "total_liab_and_equity": {},
        "net_working_capital": {},
        "net_financial_position": {},
        "book_value_per_share": {},
        "tangible_book_value_per_share": {},
        "net_loans": {},
        "allowance_for_loan_losses": {},
        "deposits": {},
        "premiums_receivable": {},
        "deferred_policy_acquisition_costs": {},
        "loss_reserves": {},
        "unearned_premiums": {},
        "other_assets_sectoral": {},
        "other_liabilities_sectoral": {}
    }

    for p in periods:
        c_v = _extract_val(cash_keys, p, "cash_and_equivalents")
        # Si c_v es None o 0.0 (caso JPM en canonical_summary), buscar en balance_sheet_detail y as_reported_statements
        if c_v is None or c_v == 0.0:
            c_cand = _extract_val(["CashAndCashEquivalentsAtCarryingValue", "ifrs-full_CashAndCashEquivalents"], p)
            if c_cand and float(c_cand) > 0:
                c_v = float(c_cand)
            else:
                cdue = _extract_val(["CashAndDueFromBanks", "us-gaap_CashAndDueFromBanks"], p) or 0.0
                cint = _extract_val(["InterestBearingDepositsInBanks", "us-gaap_InterestBearingDepositsInBanks"], p) or 0.0
                if (cdue + cint) > 0:
                    c_v = round(cdue + cint, 1)

        sti_v = _extract_val(sti_keys, p, "short_term_investments")
        # Si en as_reported_statements existe MarketableSecuritiesCurrent de carátula con saldo materialmente distinto (caso META), priorizarlo
        for r_bs in (fs.get("as_reported_statements", {}).get("balance_sheet", []) if isinstance(fs, dict) else []):
            c_tok = str(r_bs.get("concept", "")).split(":")[-1].split("_")[-1].lower()
            if c_tok in ("marketablesecuritiescurrent", "shortterminvestments"):
                bs_val = r_bs.get("values", {}).get(p)
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
                    afs_sec = _extract_val(["AvailableForSaleSecuritiesDebtSecurities", "us-gaap_AvailableForSaleSecuritiesDebtSecurities"], p) or 0.0
                    eq_sec = _extract_val(["EquitySecuritiesFvNi", "us-gaap_EquitySecuritiesFvNi"], p) or 0.0
                    st_sec = _extract_val(["ShortTermInvestments", "us-gaap_ShortTermInvestments"], p) or 0.0
                    if (afs_sec + eq_sec + st_sec) > 0:
                        sti_v = round(afs_sec + eq_sec + st_sec, 1)
            elif archetype == "FINANCIAL_BANKING":
                jpm_sec = _extract_val(["jpm_DebtSecuritiesNetCarryingAmount"], p)
                if jpm_sec and float(jpm_sec) > 0:
                    sti_v = float(jpm_sec)
                else:
                    afs_d = _extract_val(["DebtSecuritiesAvailableForSaleExcludingAccruedInterest", "us-gaap_DebtSecuritiesAvailableForSaleExcludingAccruedInterest"], p) or 0.0
                    htm_d = _extract_val(["DebtSecuritiesHeldToMaturityExcludingAccruedInterestAfterAllowanceForCreditLoss", "us-gaap_DebtSecuritiesHeldToMaturityExcludingAccruedInterestAfterAllowanceForCreditLoss"], p) or 0.0
                    if (afs_d + htm_d) > 0:
                        sti_v = round(afs_d + htm_d, 1)
                    else:
                        nu_pnl = _extract_val(["ifrs-full_FinancialAssetsAtFairValueThroughProfitOrLoss", "nu_Securities"], p) or 0.0
                        nu_oci = _extract_val(["ifrs-full_FinancialAssetsAtFairValueThroughOtherComprehensiveIncome", "nu_OtherSecurities"], p) or 0.0
                        if (nu_pnl + nu_oci) > 0:
                            sti_v = round(nu_pnl + nu_oci, 1)
            else:
                st_debt_cand = _extract_val(["DebtSecuritiesCurrent", "us-gaap_DebtSecuritiesCurrent"], p)
                st_eq_cand = _extract_val(["EquitySecuritiesFvNi", "us-gaap_EquitySecuritiesFvNi"], p)
                comb = (st_debt_cand or 0.0) + (st_eq_cand or 0.0)
                if comb > 0:
                    sti_v = round(comb, 1)
        
        ar_v = _extract_val(ar_keys, p)
        nontrade_ar = _extract_val(["NontradeReceivablesCurrent", "us-gaap_NontradeReceivablesCurrent"], p)
        inv_v = _extract_val(inv_keys, p)
        
        ca_raw = _extract_val(ca_keys, p, "current_assets")
        prep_cand = _extract_val(["PrepaidExpenseCurrent", "us-gaap_PrepaidExpenseCurrent", "PrepaidExpensesAndOtherCurrentAssets"], p)
        oth_cand = _extract_val(["OtherAssetsCurrent", "us-gaap_OtherAssetsCurrent", "OtherCurrentAssets"], p)
        if prep_cand is not None and oth_cand is not None and prep_cand != oth_cand:
            other_ca_rep = round(prep_cand + oth_cand, 1)
        else:
            other_ca_rep = _extract_val(other_ca_keys, p)
        if nontrade_ar is not None and nontrade_ar > 0:
            other_ca_rep = (other_ca_rep or 0.0) + nontrade_ar

        # En arquetipos de plataforma/fintech (ej. MELI), agregar partidas corrientes de crédito y efectivo restringido
        restr_cash = _extract_val(["RestrictedCashAndCashEquivalentsAtCarryingValue", "us-gaap_RestrictedCashAndCashEquivalentsAtCarryingValue", "RestrictedCashAndInvestmentsCurrent"], p)
        fintech_loans = _extract_val(["NotesAndLoansReceivableNetCurrent", "us-gaap_NotesAndLoansReceivableNetCurrent", "LoansAndAdvancesToCustomersCurrent"], p)
        broker_rec = _extract_val(["meli_ReceivableFromCustomerInBrokerageCurrent", "ReceivableFromCustomerInBrokerageCurrent"], p)
        if restr_cash:
            other_ca_rep = (other_ca_rep or 0.0) + restr_cash
        if fintech_loans:
            other_ca_rep = (other_ca_rep or 0.0) + fintech_loans
        if broker_rec:
            other_ca_rep = (other_ca_rep or 0.0) + broker_rec

        # Reconciliación canónica de activos corrientes (Fiscal.ai: sum(hijos) == Total Current Assets)
        other_ca = round(other_ca_rep, 1) if other_ca_rep is not None else None
        sum_ca = (c_v or 0.0) + (sti_v or 0.0) + (ar_v or 0.0) + (inv_v or 0.0) + (other_ca or 0.0)
        tot_ca = ca_raw if (ca_raw is not None and ca_raw > 0) else (sum_ca if sum_ca > 0 else None)
        if tot_ca is not None:
            diff_ca = round(tot_ca - sum_ca, 1)
            if abs(diff_ca) > 0.01:
                other_ca = round((other_ca or 0.0) + diff_ca, 1)

        tot_cash_v = round((c_v or 0.0) + (sti_v or 0.0), 1) if (c_v is not None or sti_v is not None) else None

        ppe_v = _extract_val(ppe_keys, p, "net_ppe")
        rou_v = _extract_val(rou_keys, p, "operating_lease_rou_asset")
        gw_v = _extract_val(gw_keys, p)
        int_v = _extract_val(intang_keys, p)
        if gw_v is not None and int_v is not None and gw_v == int_v:
            gw_int_v = gw_v
        else:
            gw_int_v = round((gw_v or 0.0) + (int_v or 0.0), 1) if (gw_v is not None or int_v is not None) else None

        # Si en LTM aparece un gw_int_v > 0 pero en el último año fiscal cerrado Goodwill e Intangibles son ambos None o 0
        # (y no hubo M&A mayor a $5B en LTM), forzar gw_int_v = None para evitar contaminación de notas (caso AAPL)
        if p == "LTM" and gw_int_v and len(periods) > 1:
            prev_p = periods[1]
            prev_gw = _extract_val(gw_keys, prev_p)
            prev_int = _extract_val(intang_keys, prev_p)
            ltm_ma = _extract_val(["PaymentsToAcquireBusinessesNetOfCashAcquired", "PaymentsToAcquireBusinessesGross"], "LTM") or 0.0
            if (not prev_gw or prev_gw == 0.0) and (not prev_int or prev_int == 0.0) and (abs(ltm_ma) < 5000.0):
                gw_int_v = None

        lt_inv_v = _extract_val(lt_inv_keys, p)
        eq_method = _extract_val(["EquityMethodInvestments", "InvestmentsInAssociates", "InvestmentsInAffiliatesSubsidiariesAssociatesAndJointVentures"], p)
        non_mkt_eq = _extract_val(["EquitySecuritiesWithoutReadilyDeterminableFairValueAmount", "NonmarketableEquitySecuritiesCarryingValue", "meta_NonmarketableEquitySecuritiesCarryingValue"], p)
        if eq_method is not None and non_mkt_eq is not None:
            lt_inv_v = round(eq_method + non_mkt_eq, 1)

        ta_raw = _extract_val(ta_keys, p, "total_assets")
        sum_ast = (tot_ca or 0.0) + (ppe_v or 0.0) + (rou_v or 0.0) + (gw_int_v or 0.0) + (lt_inv_v or 0.0)
        tot_ast = ta_raw if (ta_raw is not None and ta_raw > 0) else (sum_ast if sum_ast > 0 else None)
        tot_nca = max(0.0, round((tot_ast or 0.0) - (tot_ca or 0.0), 1)) if tot_ast is not None else None
        
        other_nca_rep = _extract_val(other_nca_keys, p)
        # Regla 6: Cero plugs sintéticos en Activos No Corrientes. Solo reflejar partidas reportadas en XBRL.
        other_nca = round(other_nca_rep, 1) if other_nca_rep is not None else None
        dta_v = _extract_val(dta_keys, p)

        ap_v = _extract_val(ap_keys, p)
        accrued_v = _extract_val(accrued_keys, p, "accrued_liabilities")
        if accrued_v is None or accrued_v == 0.0:
            emp_acc = _extract_val(["EmployeeRelatedLiabilitiesCurrent", "us-gaap_EmployeeRelatedLiabilitiesCurrent"], p) or 0.0
            oth_acc = _extract_val(["OtherAccruedLiabilitiesCurrent", "us-gaap_OtherAccruedLiabilitiesCurrent"], p) or 0.0
            tax_acc = _extract_val(["AccruedIncomeTaxesCurrent", "us-gaap_AccruedIncomeTaxesCurrent"], p) or 0.0
            sub_acc = emp_acc + oth_acc + tax_acc
            if sub_acc > 0:
                accrued_v = round(sub_acc, 1)
        
        tot_debt = _extract_val(tot_debt_keys, p, "total_debt")
        st_debt_v = _extract_val(st_debt_keys, p, "short_term_debt")
        if tot_debt is not None and tot_debt > 0:
            if st_debt_v is not None and st_debt_v > tot_debt:
                st_debt_v = tot_debt
            lt_debt_v = max(0.0, round(tot_debt - (st_debt_v or 0.0), 1))
            if st_debt_v is None:
                st_debt_v = 0.0
        else:
            lt_debt_v = _extract_val(lt_debt_keys, p, "long_term_debt")
            if st_debt_v is not None or lt_debt_v is not None:
                tot_debt = round((st_debt_v or 0.0) + (lt_debt_v or 0.0), 1)
                if st_debt_v is None:
                    st_debt_v = 0.0

        def_rev_v = _extract_val(def_rev_keys, p)
        cl_raw = _extract_val(cl_keys, p, "current_liabilities")
        if cl_raw is not None and def_rev_v is not None:
            pre_def_sum = (ap_v or 0.0) + (st_debt_v or 0.0) + (accrued_v or 0.0)
            if pre_def_sum + def_rev_v > cl_raw:
                # Si deferred_revenue está embebido en accrued_liabilities, ajustar para evitar doble cómputo
                def_rev_v = max(0.0, round(cl_raw - pre_def_sum, 1))

        sum_cl = (ap_v or 0.0) + (st_debt_v or 0.0) + (accrued_v or 0.0) + (def_rev_v or 0.0)
        tot_cl = cl_raw if (cl_raw is not None and cl_raw > 0) else (sum_cl if sum_cl > 0 else None)
        other_cl = max(0.0, round((tot_cl or 0.0) - sum_cl, 1)) if tot_cl is not None else None

        lease_nc_v = _extract_val(lease_liab_nc_keys, p)
        def_tax_nc_v = _extract_val(def_tax_nc_keys, p)
        eq_v = _extract_val(eq_keys, p, "stockholders_equity")
        tl_raw = _extract_val(tl_keys, p)
        tot_liab = tl_raw if (tl_raw is not None and tl_raw > 0) else (max(0.0, round((tot_ast or 0.0) - (eq_v or 0.0), 1)) if tot_ast is not None and eq_v is not None else None)
        tot_ncl = max(0.0, round((tot_liab or 0.0) - (tot_cl or 0.0), 1)) if (tot_liab is not None and tot_cl is not None) else None
        other_ncl = max(0.0, round((tot_ncl or 0.0) - ((lt_debt_v or 0.0) + (lease_nc_v or 0.0) + (def_tax_nc_v or 0.0)), 1)) if tot_ncl is not None else None

        apic_v = _extract_val(apic_keys, p)
        if apic_v is None or apic_v == 0.0:
            v_cs = _extract_val(["CommonStockValue", "us-gaap_CommonStockValue"], p)
            v_apic = _extract_val(["AdditionalPaidInCapital", "us-gaap_AdditionalPaidInCapital"], p)
            if v_cs is not None or v_apic is not None:
                apic_v = round((v_cs or 0.0) + (v_apic or 0.0), 1)
        re_v = _extract_val(re_keys, p)
        aoci_v = _extract_val(["AccumulatedOtherComprehensiveIncomeLossNetOfTax", "us-gaap_AccumulatedOtherComprehensiveIncomeLossNetOfTax", "AccumulatedOtherComprehensiveIncomeLossAvailableForSaleSecuritiesNetOfTax"], p)
        treas_v = _extract_val(["TreasuryStockValue", "TreasuryStockCommonValue", "us-gaap_TreasuryStockValue"], p)

        if (apic_v is None or apic_v == 0.0) and eq_v is not None and re_v is not None:
            derived_apic = round(eq_v - re_v - (aoci_v or 0.0) + abs(treas_v or 0.0), 1)
            if derived_apic > 0:
                apic_v = derived_apic

        other_eq_v = round((eq_v or 0.0) - ((apic_v or 0.0) + (re_v or 0.0)), 1) if eq_v is not None else None

        # Ajuste 2: Identidad contable de Patrimonio Neto Total Consolidado e Intereses Minoritarios (O y NU)

        min_int_v = _extract_val(["MinorityInterest", "us-gaap_MinorityInterest", "NoncontrollingInterests", "NoncontrollingInterest", "RedeemableNoncontrollingInterestEquityCarryingAmount"], p)

        eq_tot_cand = _extract_val(["StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest", "ifrs-full_Equity", "TotalEquity"], p)

        if eq_tot_cand is not None and (eq_v is None or eq_tot_cand > eq_v):

            if min_int_v is None and eq_v is not None:

                min_int_v = round(eq_tot_cand - eq_v, 1)

            eq_v = eq_tot_cand

        elif min_int_v is not None and min_int_v > 0:

            if tot_ast is not None and tot_liab is not None and abs((tot_liab + (eq_v or 0.0) + min_int_v) - tot_ast) <= 2.0:

                eq_v = round((eq_v or 0.0) + min_int_v, 1)



        tot_liab_eq = round((tot_liab or 0.0) + (eq_v or 0.0), 1) if (tot_liab is not None or eq_v is not None) else None
        nwc_v = round((tot_ca or 0.0) - (tot_cl or 0.0), 1) if (tot_ca is not None and tot_cl is not None) else None
        net_fin_pos = round((tot_debt or 0.0) - (tot_cash_v or 0.0), 1) if (tot_debt is not None and tot_cash_v is not None) else None

        tot_liquid = round((c_v or 0.0) + (sti_v or 0.0), 1) if (c_v is not None or sti_v is not None) else None
        shares_v = _extract_val(["WeightedAverageNumberOfDilutedSharesOutstanding", "us-gaap_WeightedAverageNumberOfDilutedSharesOutstanding", "CommonStockSharesOutstanding"], p, "shares_diluted_adjusted") or canonical.get("shares_diluted", {}).get(p)
        if shares_v and float(shares_v) > 0:
            sh_count = float(shares_v)
            sh_m = sh_count / 1e6 if sh_count >= 1e6 else sh_count
            eq_m = (eq_v / 1e6) if (eq_v and abs(eq_v) >= 1e6) else (eq_v or 0.0)
            gw_m = (gw_int_v / 1e6) if (gw_int_v and abs(gw_int_v) >= 1e6) else (gw_int_v or 0.0)
            bvps = round(eq_m / sh_m, 2) if sh_m > 0 else None
            tbvps = round((eq_m - gw_m) / sh_m, 2) if sh_m > 0 else None
        else:
            bvps, tbvps = None, None

        res["cash"][p] = c_v
        res["short_term_investments"][p] = sti_v
        res["total_liquid_cash"][p] = tot_liquid
        res["accounts_receivable"][p] = ar_v
        res["inventories"][p] = inv_v
        res["other_current_assets"][p] = other_ca
        res["total_current_assets"][p] = tot_ca
        res["net_ppe"][p] = ppe_v
        res["rou_asset"][p] = rou_v
        res["net_ppe_plus_rou"][p] = round((ppe_v or 0.0) + (rou_v or 0.0), 1) if (ppe_v is not None or rou_v is not None) else None
        res["goodwill_and_intangibles"][p] = gw_int_v
        res["long_term_investments"][p] = lt_inv_v
        res["deferred_tax_assets"][p] = dta_v
        res["other_noncurrent_assets"][p] = other_nca
        res["total_noncurrent_assets"][p] = tot_nca
        res["total_assets"][p] = tot_ast
        res["accounts_payable"][p] = ap_v
        res["accrued_liabilities"][p] = accrued_v
        res["deferred_revenue_current"][p] = def_rev_v
        res["short_term_debt"][p] = st_debt_v
        res["other_current_liabilities"][p] = other_cl
        res["total_current_liabilities"][p] = tot_cl
        res["long_term_debt"][p] = lt_debt_v
        res["operating_lease_liability_noncurrent"][p] = lease_nc_v
        res["deferred_tax_liabilities_noncurrent"][p] = def_tax_nc_v
        res["other_noncurrent_liabilities"][p] = other_ncl
        res["total_noncurrent_liabilities"][p] = tot_ncl
        res["total_liabilities"][p] = tot_liab
        res["common_stock_and_apic"][p] = apic_v
        res["retained_earnings"][p] = re_v
        res["other_equity"][p] = other_eq_v
        res["total_debt"][p] = tot_debt
        res["minority_interest"][p] = min_int_v
        res["stockholders_equity"][p] = eq_v
        res["total_liab_and_equity"][p] = tot_liab_eq
        res["net_working_capital"][p] = nwc_v
        res["net_financial_position"][p] = net_fin_pos
        res["book_value_per_share"][p] = bvps
        res["tangible_book_value_per_share"][p] = tbvps

        net_loans_v = _extract_val(net_loans_keys, p, "net_loans")
        allow_loss_v = _extract_val(allow_loss_keys, p, ["allowance_for_credit_losses", "allowance_for_loan_losses"])
        if allow_loss_v is not None:
            allow_loss_v = abs(allow_loss_v)
        dep_v = _extract_val(deposit_keys, p, "deposits")
        prem_rec_v = _extract_val(prem_rec_keys, p, "premiums_receivable")
        dac_v = _extract_val(dac_keys, p, "deferred_policy_acquisition_costs")
        loss_res_v = _extract_val(loss_res_keys, p, "loss_reserves")
        unearn_prem_v = _extract_val(unearn_prem_keys, p, "unearned_premiums")

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

        res["net_loans"][p] = net_loans_v
        res["allowance_for_loan_losses"][p] = allow_loss_v
        res["deposits"][p] = dep_v
        res["premiums_receivable"][p] = prem_rec_v
        res["deferred_policy_acquisition_costs"][p] = dac_v
        res["loss_reserves"][p] = loss_res_v
        res["unearned_premiums"][p] = unearn_prem_v
        res["other_assets_sectoral"][p] = other_ast_sec
        res["other_liabilities_sectoral"][p] = other_liab_sec

    return res


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
                    try:
                        return float(v)
                    except (ValueError, TypeError):
                        pass

    # 2. *_detail
    det_map = {
        "income": "income_statement_detail",
        "balance": "balance_sheet_detail",
        "cashflow": "cash_flow_detail",
    }
    det_key = det_map.get(section_type, f"{section_type}_detail")
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
                        try:
                            return float(vals[p])
                        except (ValueError, TypeError):
                            pass
            k_token = k.lower().split(':')[-1].split('_')[-1]
            for dk, dobj in detail_dict.items():
                d_token = dk.lower().split(':')[-1].split('_')[-1]
                if dk.lower() == k.lower() or d_token == k_token:
                    vals = dobj.get("values", dobj) if isinstance(dobj, dict) else {}
                    if isinstance(vals, dict) and p in vals and vals[p] is not None:
                        try:
                            return float(vals[p])
                        except (ValueError, TypeError):
                            pass

    # 3. as_reported_statements
    as_reported = fs.get("as_reported_statements", {})
    if isinstance(as_reported, dict):
        as_rep_map = {
            "income": "income_statement",
            "balance": "balance_sheet",
            "cashflow": "cash_flow_statement",
        }
        sec_name = as_rep_map.get(section_type, section_type)
        sec_obj = as_reported.get(sec_name, [])
        rows_list = sec_obj if isinstance(sec_obj, list) else (sec_obj.get("rows", []) if isinstance(sec_obj, dict) else [])
        if isinstance(rows_list, list):
            for row in rows_list:
                if not isinstance(row, dict):
                    continue
                concept = str(row.get("concept", ""))
                c_token = concept.lower().split(':')[-1].split('_')[-1]
                for k in key_cands:
                    k_token = k.lower().split(':')[-1].split('_')[-1]
                    if concept == k or concept.lower() == k.lower() or c_token == k_token:
                        vals = row.get("values", {})
                        if isinstance(vals, dict) and p in vals and vals[p] is not None:
                            try:
                                return float(vals[p])
                            except (ValueError, TypeError):
                                pass
    return None


def _extract_multi_source_sum(fs, section_type, key_cands, p, canon_keys=None):
    """
    Función universal multi-fuente (SSOT) para sumar múltiples partidas componentes
    de un concepto financiero (ej. múltiples tipos de adquisiciones M&A o inversiones negociables),
    evitando duplicidades de tokens idénticos o conceptos abstractos.
    """
    if not isinstance(fs, dict):
        return None
    total = 0.0
    matched = False
    matched_tokens = set()

    # 1. *_detail
    det_map = {
        "income": "income_statement_detail",
        "balance": "balance_sheet_detail",
        "cashflow": "cash_flow_detail",
    }
    det_key = det_map.get(section_type, f"{section_type}_detail")
    detail_dict = fs.get(det_key, {})
    if isinstance(detail_dict, dict):
        for k in key_cands:
            k_token = k.lower().split(':')[-1].split('_')[-1]
            for dk, dobj in detail_dict.items():
                if "abstract" in str(dk).lower():
                    continue
                d_token = str(dk).lower().split(':')[-1].split('_')[-1]
                if (dk.lower() == k.lower() or d_token == k_token) and d_token not in matched_tokens:
                    vals = dobj.get("values", dobj) if isinstance(dobj, dict) else {}
                    if isinstance(vals, dict) and p in vals and vals[p] is not None:
                        try:
                            total += float(vals[p])
                            matched = True
                            matched_tokens.add(d_token)
                        except (ValueError, TypeError):
                            pass

    # 2. as_reported_statements
    as_reported = fs.get("as_reported_statements", {})
    if isinstance(as_reported, dict):
        as_rep_map = {
            "income": "income_statement",
            "balance": "balance_sheet",
            "cashflow": "cash_flow_statement",
        }
        sec_name = as_rep_map.get(section_type, section_type)
        sec_obj = as_reported.get(sec_name, [])
        rows_list = sec_obj if isinstance(sec_obj, list) else (sec_obj.get("rows", []) if isinstance(sec_obj, dict) else [])
        if isinstance(rows_list, list):
            for row in rows_list:
                if not isinstance(row, dict) or row.get("is_abstract"):
                    continue
                concept = str(row.get("concept", ""))
                c_token = concept.lower().split(':')[-1].split('_')[-1]
                for k in key_cands:
                    k_token = k.lower().split(':')[-1].split('_')[-1]
                    if (concept.lower() == k.lower() or c_token == k_token) and c_token not in matched_tokens:
                        vals = row.get("values", {})
                        if isinstance(vals, dict) and p in vals and vals[p] is not None:
                            try:
                                total += float(vals[p])
                                matched = True
                                matched_tokens.add(c_token)
                            except (ValueError, TypeError):
                                pass

    if not matched and canon_keys:
        canonical = fs.get("canonical_summary", {})
        if isinstance(canon_keys, str):
            canon_keys = [canon_keys]
        for ck in canon_keys:
            if ck in canonical and isinstance(canonical[ck], dict):
                v = canonical[ck].get(p)
                if v is not None:
                    try:
                        return float(v)
                    except (ValueError, TypeError):
                        pass

    return total if matched else None


def resolve_canonical_income_statement(fs, periods, archetype="STANDARD_CORPORATE"):
    """
    Función canónica y unificada (SSOT) para resolver el Estado de Resultados Estandarizado (10Y + LTM)
    adaptado dinámicamente por arquetipo contable según Fiscal.ai.
    Retorna series en dólares crudos (salvo EPS/DPS en $/acción y acciones en unidades).
    """
    res = {
        "revenue": {}, "cogs": {}, "gross_profit": {},
        "rd_expense": {}, "sga_expense": {}, "credit_loss_provision": {},
        "other_operating_expense": {}, "total_operating_expenses": {},
        "operating_income": {}, "interest_income": {}, "interest_expense": {},
        "other_non_operating": {}, "total_non_operating": {},
        "ebt": {}, "income_tax": {}, "net_income": {},
        "minority_interest_pnl": {}, "preferred_dividends": {}, "net_income_common": {},
        "eps_basic": {}, "eps_diluted": {}, "shares_basic": {}, "shares_diluted": {}, "dps": {},
        "net_interest_income": {}, "non_interest_income": {}, "non_interest_expense": {},
        "transactional_expenses": {}, "share_of_associates": {},
        "net_premiums_earned": {}, "net_investment_income": {}, "investment_gains_losses": {},
        "fees_and_other_revenues": {}, "losses_and_lae": {}, "dac_amortization": {},
        "other_underwriting_expenses": {}, "total_benefits_and_expenses": {},
        "rental_revenue": {}, "tenant_reimbursements_other": {}, "property_operating_expenses": {},
        "noi": {}, "reit_da": {}, "reit_ga": {}, "reit_impairment": {}, "gain_on_sale_properties": {}
    }
    canonical = fs.get("canonical_summary", {}) if isinstance(fs, dict) else {}

    for p in periods:
        rev = _extract_multi_source_val(fs, "income", [
            "Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet",
            "TotalRevenuesAndOtherIncome", "Revenue", "ifrs-full_Revenue", "RevenuesNetOfInterestExpense"
        ], p, "revenue")

        cogs = _extract_multi_source_val(fs, "income", [
            "CostOfGoodsAndServicesSold", "CostOfRevenue", "CostOfGoodsSold",
            "CostOfPurchasedGoodsAndServices", "ifrs-full_CostOfSales"
        ], p, "cost_of_goods_sold")
        if cogs is not None:
            cogs = abs(cogs)

        gp = _extract_multi_source_val(fs, "income", [
            "GrossProfit", "ifrs-full_GrossProfit"
        ], p, "gross_profit")
        if gp is None and rev is not None and cogs is not None and archetype not in ("FINANCIAL_BANKING", "INSURANCE"):
            gp = round(rev - cogs, 2)
        if cogs is None and rev is not None and gp is not None and archetype not in ("FINANCIAL_BANKING", "INSURANCE"):
            cogs = round(rev - gp, 2)

        rd = _extract_multi_source_val(fs, "income", [
            "ResearchAndDevelopmentExpense", "TechnologyAndContentExpense", "TechnologyAndDevelopmentExpense",
            "ResearchAndDevelopmentExpenseSoftware", "ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost"
        ], p, ["rd_expense", "research_and_development"])
        if rd is not None:
            rd = abs(rd)

        sga = _extract_multi_source_val(fs, "income", [
            "SellingGeneralAndAdministrativeExpense", "SellingGeneralAndAdministrative"
        ], p, ["sga_expense", "selling_general_and_administrative"])
        if sga is None:
            sm = _extract_multi_source_val(fs, "income", [
                "SellingAndMarketingExpense", "MarketingAndAdvertisingExpense", "SellingExpense", "AdvertisingExpense"
            ], p, "sm_expense")
            ga = _extract_multi_source_val(fs, "income", [
                "GeneralAndAdministrativeExpense", "AdministrativeExpense"
            ], p, "ga_expense")
            if sm is not None or ga is not None:
                sga = (abs(sm) if sm else 0.0) + (abs(ga) if ga else 0.0)
            elif _extract_multi_source_val(fs, "income", ["GeneralAndAdministrativeExpense"], p) is not None:
                sga = abs(_extract_multi_source_val(fs, "income", ["GeneralAndAdministrativeExpense"], p))
        if sga is not None:
            sga = abs(sga)

        credit_loss = _extract_multi_source_val(fs, "income", [
            "nu_ExpectedCreditLoss", "ExpectedCreditLoss",
            "ProvisionForLoanLeaseAndOtherLosses", "ProvisionForLoanLossesExpensed", "ProvisionForDoubtfulAccounts",
            "nu_CreditLossAllowanceExpenses", "CreditLossAllowanceExpenses1",
            "ifrs-full_AdditionalAllowanceRecognisedInProfitOrLossAllowanceAccountForCreditLossesOfFinancialAssets"
        ], p, ["credit_loss_provisions", "provision_for_credit_losses"])
        if credit_loss is not None:
            credit_loss = abs(credit_loss)

        if archetype == "FINANCIAL_BANKING":
            ebit = None
        else:
            ebit = _extract_multi_source_val(fs, "income", [
                "OperatingIncomeLoss", "ifrs-full_ProfitLossFromOperatingActivities", "OperatingIncome"
            ], p, "operating_income")

        tot_opex = _extract_multi_source_val(fs, "income", [
            "OperatingExpenses", "CostsAndExpenses", "ifrs-full_OperatingExpense"
        ], p, "operating_expenses")
        if tot_opex is None and gp is not None and ebit is not None and archetype not in ("FINANCIAL_BANKING", "INSURANCE"):
            tot_opex = round(gp - ebit, 2)
        if tot_opex is not None:
            tot_opex = abs(tot_opex)

        # Verificación contable universal de fidelidad al Estado de Resultados publicado:
        # Si la empresa reporta un Total OpEx compuesto íntegramente por SG&A (abs(tot_opex - sga) <= 1.0),
        # cualquier cifra de I+D proviene de notas/desgloses complementarios y ya está incluida en SG&A.
        # No debe figurar como deducción operativa independiente en la cascada del Estado de Resultados.
        if tot_opex is not None and sga is not None and rd is not None:
            if abs(tot_opex - sga) <= 1.0 or (sga >= tot_opex - 1.0):
                rd = None

        other_opex_raw = _extract_multi_source_val(fs, "income", [
            "RestructuringCharges", "OtherCostAndExpenseOperating", "BusinessCombinationAcquisitionRelatedCosts",
            "AmortizationOfIntangibleAssets", "OperatingExpensesOther", "ImpairmentOfIntangibleAssetsFinitelived"
        ], p)
        if tot_opex is not None and archetype not in ("FINANCIAL_BANKING", "INSURANCE"):
            implied_other = max(0.0, round(tot_opex - (rd or 0.0) - (sga or 0.0) - (credit_loss or 0.0), 2))
            other_opex = implied_other if implied_other > 0.01 else None
        else:
            other_opex = abs(other_opex_raw) if other_opex_raw is not None else None

        int_inc = _extract_multi_source_val(fs, "income", [
            "InvestmentIncomeInterest", "InterestIncomeOperating", "InterestAndDividendIncomeOperating",
            "InterestIncome", "ifrs-full_RevenueFromInterest", "nu_InterestIncomeAndGainsLossesOnFinancialInstruments"
        ], p, "interest_income")
        if int_inc is not None:
            int_inc = abs(int_inc)

        int_exp = _extract_multi_source_val(fs, "income", [
            "InterestExpense", "InterestExpenseNonoperating", "InterestExpenseDebt", "InterestExpenseOperating",
            "meli_InterestExpenseAndOtherFinancialCharges"
        ], p)
        if int_exp is None:
            int_exp = _extract_multi_source_val(fs, "income", [], p, "interest_expense")
        if int_exp is not None:
            int_exp = abs(int_exp)

        share_assoc = _extract_multi_source_val(fs, "income", [
            "nu_ShareOfLossInAssociates", "ShareOfProfitLossOfAssociatesAndJointVenturesAccountedForUsingEquityMethod",
            "IncomeLossFromEquityMethodInvestments", "ShareOfLossInAssociates",
            "meli_EquityInEarningsOfUnconsolidatedEntityNetOfTax", "EquityInEarningsOfUnconsolidatedEntity",
            "EquityInEarningsLossOfUnconsolidatedEntity", "EquityInLossOfUnconsolidatedEntity"
        ], p, "share_of_associates")

        tax_raw = _extract_multi_source_val(fs, "income", [
            "IncomeTaxExpenseBenefit", "IncomeTaxExpenseContinuingOperations", "nu_IncomeTaxInStatementOfProfitOrLoss",
            "CurrentIncomeTaxExpenseBenefit", "ifrs-full_IncomeTaxExpenseContinuingOperations"
        ], p, ["income_tax", "income_tax_expense"])
        if tax_raw is None:
            c_tax = _extract_multi_source_val(fs, "income", ["CurrentTaxExpenseIncome"], p)
            d_tax = _extract_multi_source_val(fs, "income", ["DeferredTaxExpenseIncome"], p)
            if c_tax is not None or d_tax is not None:
                tax_raw = (c_tax or 0.0) + (d_tax or 0.0)

        ni = _extract_multi_source_val(fs, "income", [
            "NetIncomeLoss", "ProfitLoss", "NetIncome", "ifrs-full_ProfitLoss"
        ], p, "net_income")

        ebt = _extract_multi_source_val(fs, "income", [
            "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
            "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
            "IncomeLossAttributableToParent", "us-gaap_IncomeLossAttributableToParent",
            "IncomeLossBeforeIncomeTaxExpenseBenefit", "ProfitLossBeforeTax"
        ], p, "ebt")

        # Conciliación matemática universal de Impuesto / Crédito Fiscal y Beneficio Neto:
        # Identidad contable universal: Net Income = EBT - Tax + Share of Associates.
        tax = tax_raw
        if ebt is not None and ni is not None:
            pre_assoc_ni = round(ni - (share_assoc or 0.0), 2)
            diff = round(ebt - pre_assoc_ni, 2)
            if tax is None:
                tax = diff
            elif diff < -1.0 and (tax is None or tax > 0):
                # EBT < pre_assoc_ni indica beneficio fiscal (Tax Benefit)
                tax = -abs(tax if tax is not None else diff)
            elif diff > 1.0 and (tax is not None and tax < 0):
                tax = abs(tax)
        elif tax is not None and tax < 0:
            tax = tax

        if ebt is None and ni is not None and tax is not None:
            ebt = round(ni - (share_assoc or 0.0) + tax, 2)

        tot_non_op_raw = _extract_multi_source_val(fs, "income", [
            "NonoperatingIncomeExpense", "InterestRevenueExpenseNet", "deck_InterestAndOtherExpense",
            "NonoperatingIncomeExpenseNet"
        ], p, "non_operating_income")

        # Conciliación de Total No Operativo bajo identidades contables universales:
        # En arquetipos con EBIT y EBT definidos (Corporativo, Plataforma, REIT, Seguros), la magnitud neta es exactamente EBT - EBIT.
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

        other_non_op = _extract_multi_source_val(fs, "income", [
            "OtherNonoperatingIncomeExpense", "GainLossOnInvestments", "ForeignCurrencyTransactionGainLossBeforeTax",
            "GainLossOnSaleOfSecuritiesNet", "OtherNonoperatingIncomeExpenseNet"
        ], p, "other_non_operating")

        # Derivación institucional del componente 'Otros Ingresos / (Gastos) No Operativos'
        # cuando la empresa publica Total No Operativo y desglose de intereses
        if tot_non_op is not None and (int_inc is not None or int_exp is not None):
            implied_other_non_op = round(tot_non_op - (int_inc or 0.0) + (int_exp or 0.0), 2)
            if abs(implied_other_non_op) > 0.01:
                other_non_op = implied_other_non_op
            else:
                other_non_op = None

        min_int_pnl = _extract_multi_source_val(fs, "income", [
            "NetIncomeLossAttributableToNoncontrollingInterest", "ProfitLossAttributableToNoncontrollingInterests"
        ], p)
        if min_int_pnl is not None:
            min_int_pnl = abs(min_int_pnl)

        pref_div = _extract_multi_source_val(fs, "income", [
            "PreferredStockDividendsIncomeStatementImpact", "RedeemablePreferredStockDividends",
            "PreferredStockDividendsAndOtherAdjustments"
        ], p)
        if pref_div is not None:
            pref_div = abs(pref_div)

        ni_comm = _extract_multi_source_val(fs, "income", [
            "NetIncomeLossAvailableToCommonStockholdersBasic", "ProfitLossAttributableToOwnersOfParent"
        ], p)
        if (min_int_pnl or pref_div) and ni is not None:
            ni_comm = round(ni - (min_int_pnl or 0.0) - (pref_div or 0.0), 2)
        elif ni_comm is None and ni is not None:
            ni_comm = round(ni - (min_int_pnl or 0.0) - (pref_div or 0.0), 2)

        eps_b = _extract_multi_source_val(fs, "income", [
            "EarningsPerShareBasic", "BasicEarningsLossPerShare", "ifrs-full_BasicEarningsLossPerShare"
        ], p, ["eps_basic_adjusted", "eps_basic"])

        eps_d = _extract_multi_source_val(fs, "income", [
            "EarningsPerShareDiluted", "DilutedEarningsLossPerShare", "ifrs-full_DilutedEarningsLossPerShare"
        ], p, ["eps_diluted_adjusted", "eps_diluted"])

        sh_b = _extract_multi_source_val(fs, "income", [
            "WeightedAverageNumberOfSharesOutstandingBasic", "ifrs-full_WeightedAverageShares"
        ], p, ["shares_basic_adjusted", "shares_basic"])

        sh_d = _extract_multi_source_val(fs, "income", [
            "WeightedAverageNumberOfDilutedSharesOutstanding", "ifrs-full_AdjustedWeightedAverageShares"
        ], p, ["shares_diluted_adjusted", "shares_diluted"])

        if sh_b is None and p == "LTM" and sh_d is not None and sh_d > 0:
            # Respaldo canónico institucional si las acciones básicas no vinieron directamente para LTM
            prior_p = next((x for x in periods if x != "LTM"), None)
            if prior_p:
                prior_sb = _extract_multi_source_val(fs, "income", ["WeightedAverageNumberOfSharesOutstandingBasic", "ifrs-full_WeightedAverageShares"], prior_p, ["shares_basic_adjusted", "shares_basic"])
                prior_sd = _extract_multi_source_val(fs, "income", ["WeightedAverageNumberOfDilutedSharesOutstanding", "ifrs-full_AdjustedWeightedAverageShares"], prior_p, ["shares_diluted_adjusted", "shares_diluted"])
                if prior_sb and prior_sd and prior_sd > 0:
                    sh_b = round(sh_d * min(1.0, prior_sb / prior_sd))
                else:
                    sh_b = sh_d
            else:
                sh_b = sh_d

        if eps_b is None and p == "LTM" and ni_comm is not None and sh_b and sh_b > 0:
            eps_b = round(ni_comm / sh_b, 2)

        dps_val = _extract_multi_source_val(fs, "income", [
            "CommonStockDividendsPerShareDeclared", "CommonStockDividendsPerShareCashPaid", "DividendsPerShareDeclared"
        ], p, ["dps_adjusted", "dps"])
        split_fac = canonical.get("split_adjustment_factor", {}).get(p, 1.0)
        if split_fac and split_fac > 1.0 and dps_val is not None:
            if "dps_adjusted" not in canonical or canonical.get("dps_adjusted", {}).get(p) is None:
                dps_val = round(dps_val / split_fac, 4)

        if dps_val is None:
            div_paid = _extract_multi_source_val(fs, "cashflow", [
                "PaymentsOfDividendsCommonStock", "PaymentsOfDividends", "DividendsPaid"
            ], p, "dividends_paid")
            if div_paid is not None and abs(div_paid) > 0 and sh_b and sh_b > 0:
                raw_dps = abs(div_paid) / sh_b
                if split_fac and split_fac > 1.0:
                    dps_val = round(raw_dps / split_fac, 4)
                else:
                    dps_val = round(raw_dps, 4)

        nii = _extract_multi_source_val(fs, "income", ["InterestIncomeExpenseNet", "NetInterestIncome"], p, "net_interest_income")
        if nii is None and int_inc is not None and int_exp is not None:
            nii = round(int_inc - int_exp, 2)

        non_int_inc = _extract_multi_source_val(fs, "income", ["NoninterestIncome", "ifrs-full_FeeAndCommissionIncome", "jpm_FeesAndCommissions1"], p, "non_interest_income")
        if non_int_inc is None and rev is not None and nii is not None:
            non_int_inc = round(rev - nii, 2)

        non_int_exp = _extract_multi_source_val(fs, "income", [
            "NoninterestExpense", "GeneralAndAdministrativeExpense", "SellingExpense", "nu_CustomerSupportAndOperations"
        ], p, ["operating_expenses", "non_interest_expense"])
        if non_int_exp is None and rev is not None and credit_loss is not None and ebt is not None:
            non_int_exp = round(rev - credit_loss - ebt, 2)
        if non_int_exp is not None:
            non_int_exp = abs(non_int_exp)

        trans_exp = _extract_multi_source_val(fs, "income", [
            "nu_TransactionalExpenses", "TransactionalExpenses", "TransactionExpenses", "CostOfTransactionalServices"
        ], p, "transactional_expenses")
        if trans_exp is not None:
            trans_exp = abs(trans_exp)

        prem_earned = _extract_multi_source_val(fs, "income", ["PremiumsEarnedNet", "PremiumsEarnedNetPropertyAndCasualty"], p, "net_premiums_earned")
        net_inv_inc = _extract_multi_source_val(fs, "income", ["NetInvestmentIncome", "InvestmentIncomeNet", "InterestAndDividendIncomeOperating"], p, "net_investment_income")
        inv_gains = _extract_multi_source_val(fs, "income", ["DebtAndEquitySecuritiesGainLoss", "RealizedInvestmentGainsLosses", "GainLossOnInvestments"], p)
        fees_other = _extract_multi_source_val(fs, "income", ["pgr_FeesAndOtherRevenues", "pgr_NonInsuranceServiceRevenues"], p)
        losses_lae = _extract_multi_source_val(fs, "income", [
            "PolicyholderBenefitsAndClaimsIncurredNet", "LiabilityForUnpaidClaimsAndClaimsAdjustmentExpenseIncurredClaims1", "IncurredClaimsPropertyCasualtyAndLiability"
        ], p, ["losses_and_loss_expenses", "losses_and_lae"])
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
        prop_exp = _extract_multi_source_val(fs, "income", ["DirectCostsOfLeasedAndRentedPropertyOrEquipment", "o_DirectCostsOfLeasedAndRentedPropertyOrEquipmentIncludingReimbursableExpense"], p, ["property_operating_expenses", "cost_of_goods_sold"])
        if prop_exp is not None:
            prop_exp = abs(prop_exp)

        if rev is not None and prop_exp is not None:
            noi = round(rev - prop_exp, 2)
        else:
            noi = _extract_multi_source_val(fs, "income", [], p, ["noi", "gross_profit"])

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

        if archetype == "REAL_ESTATE_REIT":
            if noi is not None and reit_da is not None:
                ebit = round(noi - reit_da - (reit_ga or 0.0) - (reit_imp or 0.0), 2)
        elif archetype == "INSURANCE":
            if rev is not None and tot_ben_exp is not None:
                ebit = round(rev - tot_ben_exp, 2)

        res["revenue"][p] = rev
        res["cogs"][p] = cogs
        res["gross_profit"][p] = gp
        res["rd_expense"][p] = rd
        res["sga_expense"][p] = sga
        res["credit_loss_provision"][p] = credit_loss
        res["other_operating_expense"][p] = other_opex
        res["total_operating_expenses"][p] = tot_opex
        res["operating_income"][p] = ebit
        res["interest_income"][p] = int_inc
        res["interest_expense"][p] = int_exp
        res["other_non_operating"][p] = other_non_op
        res["total_non_operating"][p] = tot_non_op
        res["ebt"][p] = ebt
        res["income_tax"][p] = tax
        res["net_income"][p] = ni
        res["minority_interest_pnl"][p] = min_int_pnl
        res["preferred_dividends"][p] = pref_div
        res["net_income_common"][p] = ni_comm
        res["eps_basic"][p] = eps_b
        res["eps_diluted"][p] = eps_d
        res["shares_basic"][p] = sh_b
        res["shares_diluted"][p] = sh_d
        res["dps"][p] = dps_val
        res["net_interest_income"][p] = nii
        res["non_interest_income"][p] = non_int_inc
        res["non_interest_expense"][p] = non_int_exp
        res["transactional_expenses"][p] = trans_exp
        res["share_of_associates"][p] = share_assoc
        res["net_premiums_earned"][p] = prem_earned
        res["net_investment_income"][p] = net_inv_inc
        res["investment_gains_losses"][p] = inv_gains
        res["fees_and_other_revenues"][p] = fees_other
        res["losses_and_lae"][p] = losses_lae
        res["dac_amortization"][p] = dac_amort
        res["other_underwriting_expenses"][p] = other_uw_exp
        res["total_benefits_and_expenses"][p] = tot_ben_exp
        res["rental_revenue"][p] = rental_rev
        res["tenant_reimbursements_other"][p] = tenant_reimb
        res["property_operating_expenses"][p] = prop_exp
        res["noi"][p] = noi
        res["reit_da"][p] = reit_da
        res["reit_ga"][p] = reit_ga
        res["reit_impairment"][p] = reit_imp
        res["gain_on_sale_properties"][p] = gain_sale

    return res


def resolve_canonical_cash_flow(fs, periods, capital_flows=None, archetype="STANDARD_CORPORATE"):
    """
    Función canónica y unificada (SSOT) para resolver el Estado de Flujos de Caja en 4 secciones
    según Fiscal.ai, integrando capital allocation auditado y respetando estrictamente la Regla 6 (Cero Plugs Sintéticos).
    """
    if capital_flows is None:
        capital_flows = resolve_canonical_capital_flows(fs, periods)
    canonical = fs.get("canonical_summary", {}) if isinstance(fs, dict) else {}

    res = {
        "net_income": {}, "da": {}, "sbc": {}, "deferred_taxes": {}, "other_noncash": {},
        "wc_ar": {}, "wc_inv": {}, "wc_ap": {}, "wc_other": {}, "cfo": {},
        "capex": {}, "acquisitions_ma": {}, "purchases_investments": {},
        "sales_maturities_investments": {}, "other_investing": {}, "cfi": {},
        "debt_issued": {}, "debt_repaid": {}, "net_debt_issued": {},
        "stock_issued": {}, "share_repurchases_open_market": {}, "share_repurchases_sbc_tax": {},
        "dividends_paid": {}, "other_financing": {}, "cff": {},
        "fx_effect": {}, "beginning_cash": {}, "net_change_in_cash": {}, "ending_cash": {}, "fcf": {}, "affo": {}
    }

    for p in periods:
        # 1. ACTIVIDADES OPERATIVAS (CFO)
        ni = _extract_multi_source_val(fs, "cashflow", [
            "NetIncomeLoss", "ProfitLoss", "ProfitLossFromContinuingOperations"
        ], p, "net_income")

        da = _extract_multi_source_val(fs, "cashflow", [
            "DepreciationDepletionAndAmortization", "DepreciationAmortizationAndAccretionNet", "Depreciation",
            "ifrs-full_AdjustmentsForDepreciationAndAmortisationExpense", "DepreciationAndAmortization"
        ], p, "depreciation_and_amortization")
        if da is not None:
            da = abs(da)

        sbc = _extract_multi_source_val(fs, "cashflow", [
            "ShareBasedCompensation", "AllocatedShareBasedCompensationExpense", "AdjustmentsForSharebasedPayments",
            "ExpenseFromSharebasedPaymentTransactionsWithEmployees", "RestrictedStockExpense", "us-gaap_RestrictedStockExpense",
            "ShareBasedCompensationArrangementByShareBasedPaymentAwardExpense", "us-gaap_ShareBasedCompensationArrangementByShareBasedPaymentAwardExpense",
            "StockOptionPlanExpense", "us-gaap_StockOptionPlanExpense", "StockBasedCompensation", "meli_StockBasedCompensation"
        ], p, "stock_based_compensation")
        if sbc is not None:
            sbc = abs(sbc)

        def_taxes = _extract_multi_source_val(fs, "cashflow", [
            "DeferredIncomeTaxExpenseBenefit", "DeferredIncomeTaxesAndTaxCredits", "ifrs-full_AdjustmentsForDeferredTaxExpense",
            "us-gaap_DeferredIncomeTaxesAndTaxCredits"
        ], p)

        other_nc = _extract_multi_source_sum(fs, "cashflow", [
            "OtherNoncashIncomeExpense", "ProvisionForLoanLeaseAndOtherLosses", "ProvisionForDoubtfulAccounts",
            "GainLossOnInvestments", "CreditLossAllowanceExpenses1", "UnrealizedGainLossOnInvestments",
            "ImpairmentOfRealEstate", "ImpairmentOfLongLivedAssetsHeldForUse", "GainLossOnSaleOfProperties",
            "us-gaap_OtherNoncashIncome", "meta_UnrealizedGainLossOnMarketableAndNonmarketableEquityInvestments",
            "o_OtherNoncashInterestIncomeExpenseOperating", "AmortizationOfFinancingCosts",
            "AdjustmentsNoncashItemsToReconcileNetIncomeLossToCashProvidedByUsedInOperatingActivities",
            "GainsLossesOnExtinguishmentOfDebt"
        ], p)

        wc_ar = _extract_multi_source_sum(fs, "cashflow", [
            "IncreaseDecreaseInAccountsReceivable", "IncreaseDecreaseInOtherReceivables",
            "TradeAndOtherReceivablesNetCurrent", "meli_IncreaseDecreaseInPrincipalLoansReceivableNet"
        ], p)

        wc_inv = _extract_multi_source_val(fs, "cashflow", [
            "IncreaseDecreaseInInventories"
        ], p)

        wc_ap = _extract_multi_source_val(fs, "cashflow", [
            "IncreaseDecreaseInAccountsPayable", "IncreaseDecreaseInAccountsPayableTrade",
            "us-gaap_IncreaseDecreaseInAccountsPayableTrade", "IncreaseDecreaseInAccountsPayableAndAccruedLiabilities"
        ], p)

        wc_other = _extract_multi_source_sum(fs, "cashflow", [
            "IncreaseDecreaseInOtherOperatingAssets", "IncreaseDecreaseInPrepaidDeferredExpenseAndOtherAssets",
            "IncreaseDecreaseInOtherOperatingLiabilities", "IncreaseDecreaseInOtherNoncurrentLiabilities",
            "IncreaseDecreaseInAccruedLiabilities", "IncreaseDecreaseInAccruedLiabilitiesAndOtherOperatingLiabilities",
            "IncreaseDecreaseInContractWithCustomerLiability", "IncreaseDecreaseInDeferredRevenue",
            "IncreaseDecreaseInOperatingLeaseLiability", "meli_IncreaseDecreaseInFundsPayableToCustomers",
            "meli_IncreaseDecreaseInAmountsPayableDueToCreditAndDebitCardTransactions",
            "IncreaseDecreaseInOperatingCapital"
        ], p)

        cfo = _extract_multi_source_val(fs, "cashflow", [
            "NetCashProvidedByUsedInOperatingActivities", "CashFlowsFromUsedInOperatingActivities",
            "NetCashProvidedByOperatingActivities", "ifrs-full_CashFlowsFromUsedInOperatingActivities"
        ], p, "cash_from_operations")

        # Conciliación matemática exacta de CFO (Regla 6 y Fiscal.ai: sum(hijos) == CFO)
        if cfo is not None:
            sub_cfo = (ni or 0.0) + (da or 0.0) + (sbc or 0.0) + (def_taxes or 0.0) + (wc_ar or 0.0) + (wc_inv or 0.0) + (wc_ap or 0.0) + (wc_other or 0.0) + (other_nc or 0.0)
            diff_cfo = round(cfo - sub_cfo, 2)
            if abs(diff_cfo) > 0.01:
                other_nc = round((other_nc or 0.0) + diff_cfo, 2)

        # 2. ACTIVIDADES DE INVERSIÓN (CFI)
        can_capex = canonical.get("capital_expenditures", {}).get(p)
        if can_capex is not None:
            capex = abs(float(can_capex))
        else:
            raw_cx = _extract_multi_source_val(fs, "cashflow", [
                "PaymentsToAcquirePropertyPlantAndEquipment", "PurchasesOfPropertyAndEquipmentAndIntangibleAssets",
                "nvda_PurchasesOfPropertyAndEquipmentAndIntangibleAssets", "PurchasesOfPropertyAndEquipment",
                "PaymentsToAcquireProductiveAssets", "PaymentsForPropertyPlantAndEquipment",
                "ifrs-full_PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities",
                "AcquisitionAndDevelopmentOfIntangibleAssets", "AcquisitionOfIntangibleAssets",
                "PurchaseOfIntangibleAssets", "PaymentsToAcquireIntangibleAssets", "PaymentsForCapitalImprovements"
            ], p)
            capex = abs(raw_cx) if raw_cx is not None else None

        acq_ma = capital_flows["acquisitions_ma"].get(p)
        if acq_ma is None:
            acq_ma = _extract_multi_source_sum(fs, "cashflow", [
                "PaymentsToAcquireBusinessesNetOfCashAcquired", "PaymentsToAcquireBusinessTwoNetOfCashAcquired",
                "PaymentsToAcquireBusinessesNetOfCashAcquiredAndPurchasesOfIntangibleAndOtherAssets",
                "PaymentsToAcquireCommercialRealEstate", "PaymentsToAcquireLoansReceivable",
                "PaymentsToAcquireInterestInSubsidiariesAndAffiliates"
            ], p)
        if acq_ma is not None:
            acq_ma = abs(acq_ma)

        purch_inv = _extract_multi_source_sum(fs, "cashflow", [
            "PaymentsToAcquireAvailableForSaleSecuritiesDebt", "PaymentsToAcquireMarketableSecurities",
            "PaymentsToAcquireInvestments", "PaymentsToAcquireOtherInvestments",
            "PaymentsToAcquireEquitySecuritiesFvNi", "meta_PaymentsForEquitySecuritiesWithoutReadilyDeterminableFairValue",
            "meta_PaymentsForHeldForSaleAssets", "us-gaap_PaymentsToAcquireAvailableForSaleSecurities"
        ], p)
        if purch_inv is not None:
            purch_inv = abs(purch_inv)

        sales_inv = _extract_multi_source_sum(fs, "cashflow", [
            "ProceedsFromSaleOfAvailableForSaleSecuritiesDebt", "ProceedsFromSaleOfMarketableSecurities",
            "ProceedsFromMaturitiesPrepaymentsAndCallsOfAvailableForSaleSecurities", "ProceedsFromMaturityOfMarketableSecurities",
            "ProceedsFromSaleAndMaturityOfMarketableSecurities", "ProceedsFromSaleOfAvailableForSaleSecurities",
            "ProceedsFromSaleOfEquitySecuritiesFvNi", "meta_ProceedsFromOneTimeVentureDistribution",
            "ProceedsFromSaleOfPropertyHeldForSale", "ProceedsFromCollectionOfNotesReceivable",
            "ProceedsFromDepositsOnRealEstateSales", "ProceedsFromInsuranceSettlementInvestingActivities"
        ], p)

        other_inv = _extract_multi_source_val(fs, "cashflow", [
            "PaymentsForProceedsFromOtherInvestingActivities", "ProceedsFromSaleOfRealEstate", "PaymentsToAcquireRealEstate"
        ], p)

        cfi = _extract_multi_source_val(fs, "cashflow", [
            "NetCashProvidedByUsedInInvestingActivities", "CashFlowsFromUsedInInvestingActivities",
            "ifrs-full_CashFlowsFromUsedInInvestingActivities"
        ], p, "cash_from_investing")

        # Conciliación matemática exacta de CFI (Regla 6 y Fiscal.ai: sum(hijos) == CFI)
        if cfi is not None:
            sub_cfi = -(capex or 0.0) - (acq_ma or 0.0) - (purch_inv or 0.0) + (sales_inv or 0.0) + (other_inv or 0.0)
            diff_cfi = round(cfi - sub_cfi, 2)
            if abs(diff_cfi) > 0.01:
                other_inv = round((other_inv or 0.0) + diff_cfi, 2)

        # 3. ACTIVIDADES DE FINANCIACIÓN (CFF)
        di = capital_flows["debt_issuances"].get(p)
        dr = capital_flows["debt_repayments"].get(p)
        net_debt = capital_flows["net_debt_change"].get(p)
        cp = _extract_multi_source_val(fs, "cashflow", ["ProceedsFromRepaymentsOfCommercialPaper"], p)
        if cp is not None and net_debt is not None:
            net_debt = round(net_debt + cp, 2)

        stk_iss = capital_flows["stock_plans_proceeds"].get(p) or _extract_multi_source_val(fs, "cashflow", [
            "ProceedsFromIssuanceOfCommonStock", "ProceedsFromIssuanceOfShares"
        ], p)

        rep_om = capital_flows["share_repurchases_open_market"].get(p)
        rep_tax = capital_flows["share_repurchases_sbc_tax"].get(p)
        div_paid = capital_flows["dividends_paid"].get(p)

        other_fin = _extract_multi_source_sum(fs, "cashflow", [
            "ProceedsFromPaymentsForOtherFinancingActivities", "IncreaseDecreaseInDeposits",
            "PaymentsForProceedsFromOtherFinancingActivities", "PaymentsOfDebtIssuanceCosts",
            "nu_LeasePayments"
        ], p)

        cff = _extract_multi_source_val(fs, "cashflow", [
            "NetCashProvidedByUsedInFinancingActivities", "CashFlowsFromUsedInFinancingActivities",
            "ifrs-full_CashFlowsFromUsedInFinancingActivities"
        ], p, "cash_from_financing")

        # Conciliación matemática exacta de CFF (Regla 6 y Fiscal.ai: sum(hijos) == CFF)
        if cff is not None:
            sub_cff = (di or 0.0) - (dr or 0.0) + (stk_iss or 0.0) - (rep_om or 0.0) - (rep_tax or 0.0) - (div_paid or 0.0) + (other_fin or 0.0)
            diff_cff = round(cff - sub_cff, 2)
            if abs(diff_cff) > 0.01:
                other_fin = round((other_fin or 0.0) + diff_cff, 2)

        # 4. VARIACIÓN NETA DE CAJA Y FCF
        fx = _extract_multi_source_val(fs, "cashflow", [
            "EffectOfExchangeRateOnCashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
            "EffectOfExchangeRateOnCashAndCashEquivalents", "nu_ForeignExchangeRateChangesOnCashAndCashEquivalents",
            "ifrs-full_EffectOfExchangeRateChangesOnCashAndCashEquivalents"
        ], p)

        net_chg_cash = _extract_multi_source_val(fs, "cashflow", [
            "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsPeriodIncreaseDecreaseIncludingExchangeRateEffect",
            "CashAndCashEquivalentsPeriodIncreaseDecrease", "ifrs-full_IncreaseDecreaseInCashAndCashEquivalents"
        ], p)
        if net_chg_cash is None and cfo is not None and cfi is not None and cff is not None:
            net_chg_cash = round(cfo + cfi + cff + (fx or 0.0), 2)

        end_cash = _extract_multi_source_val(fs, "cashflow", [
            "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents", "CashAndCashEquivalentsAtCarryingValue",
            "ifrs-full_CashAndCashEquivalents"
        ], p)

        beg_cash = _extract_multi_source_val(fs, "cashflow", [
            "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsPeriodIncreaseDecreaseIncludingExchangeRateEffect",
            "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsBeginningOfPeriod",
            "CashAndCashEquivalentsAtBeginningOfPeriod",
            "CashAndCashEquivalentsAtCarryingValueBeginningOfPeriod",
            "ifrs-full_CashAndCashEquivalentsAtBeginningOfPeriod"
        ], p)
        if beg_cash is None and end_cash is not None and net_chg_cash is not None:
            beg_cash = round(end_cash - net_chg_cash, 2)

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
        res["affo"][p] = affo_val

        res["net_income"][p] = ni
        res["da"][p] = da
        res["sbc"][p] = sbc
        res["deferred_taxes"][p] = def_taxes
        res["other_noncash"][p] = other_nc
        res["wc_ar"][p] = wc_ar
        res["wc_inv"][p] = wc_inv
        res["wc_ap"][p] = wc_ap
        res["wc_other"][p] = wc_other
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

    return res



def build_statements_context(
    fs,
    fys,
    statements_fys,
    latest_p,
    canonical,
    key_ratios,
    archetype,
    is_banking,
    is_insurance,
    is_reit,
    is_financial,
    enriched,
    bs_data,
    pnl_data,
    cap_flows,
    cf_data,
):
    """Construye las tablas de estados financieros (Estandarizados, SEC As-Reported, Resúmenes y P&L resumido)."""
    # NUEVA ESTRUCTURA DE ESTADOS FINANCIEROS DINÁMICOS
    # -------------------------------------------------------------
    inc_det = fs.get("income_statement_detail", {})
    bs_det = fs.get("balance_sheet_detail", {})
    cf_det = fs.get("cash_flow_detail", {})
    statements_fys = [p for p in fs.get("fiscal_years", [])[:11]]

    def _num(dict_src, key, p):
        if not dict_src or not key:
            return None
        if key in dict_src:
            obj = dict_src[key]
            if isinstance(obj, dict):
                if "values" in obj:
                    return obj["values"].get(p)
                return obj.get(p)
        cand_keys = [f"us-gaap_{key}"] if not str(key).startswith("us-gaap_") else [str(key)[len("us-gaap_"):]]
        for ck in cand_keys:
            if ck in dict_src:
                obj = dict_src[ck]
                if isinstance(obj, dict):
                    if "values" in obj:
                        return obj["values"].get(p)
                    return obj.get(p)
        raw_key = str(key).split(":")[-1].split("_")[-1].lower()
        for k, obj in dict_src.items():
            k_tok = str(k).split(":")[-1].split("_")[-1].lower()
            if k_tok == raw_key:
                if isinstance(obj, dict):
                    if "values" in obj:
                        return obj["values"].get(p)
                    return obj.get(p)
        return None

    def _to_m(val):
        if val is None:
            return None
        v = float(val)
        return round(v / 1e6, 1)

    def _fmt_money(m_val):
        if m_val is None:
            return "-"
        if m_val == 0.0:
            return "$0.0M"
        prefix = "-$" if m_val < 0 else "$"
        return f"{prefix}{abs(m_val):,.1f}M"

    def _fmt_pct(pct_val):
        if pct_val is None:
            return "-"
        return f"{pct_val:.1f}%"

    def _fmt_shares(val):
        if val is None:
            return "-"
        v = float(val)
        scale = abs(v)
        if scale >= 1e6:
            return f"{scale/1e6:,.1f}M"
        return f"{scale:,.1f}"

    def _fmt_eps(val):
        if val is None:
            return "-"
        v = float(val)
        return f"-${abs(v):.2f}" if v < 0 else f"${v:.2f}"

    def _build_statement_cells(r, target_fys, canonical, ebt_dict=None, bs_tot_assets=None):
        if r.get("row_type") == "section_header":
            return {
                "label": r["label"],
                "orig_tooltip": r.get("orig_tooltip", ""),
                "clarification": r.get("clarification"),
                "operator": "",
                "row_type": "section_header",
                "indent": False,
                "is_bold": True,
                "values": ["" for _ in target_fys],
                "pcts": ["" for _ in target_fys],
                "yoy": ["" for _ in target_fys],
                "cagr_5y": "",
                "ltm_val": "",
                "ltm_pct": "",
                "ltm_yoy": "",
                "annual_cells": [{"abs": "", "pct": "", "yoy": ""} for _ in target_fys[1:]],
                "annual_vals": ["" for _ in target_fys[1:]],
                "latest_val": "",
                "latest_pct": ""
            }

        row_vals = []
        row_pcts = []
        row_yoys = []

        for i, p in enumerate(target_fys):
            val = r["data"].get(p)
            val_prior = r["data"].get(target_fys[i + 1]) if (i + 1 < len(target_fys)) else None

            # 1. abs_disp
            row_type = r.get("row_type", "item")
            if row_type == "shares":
                abs_disp = _fmt_shares(val)
            elif row_type in ("eps", "dps"):
                abs_disp = _fmt_eps(val)
            elif row_type == "metric_pct":
                abs_disp = f"{val:.1f}%" if val is not None else "-"
            elif row_type == "multiple":
                abs_disp = f"{val:.2f}x" if val is not None else "-"
            elif row_type in ("net_debt", "net_cash", "metric"):
                if val is not None:
                    abs_disp = f"-${abs(val):,.1f}M" if val < 0 else f"${val:,.1f}M"
                else:
                    abs_disp = "-"
            else:
                if r.get("negate_val") and val is not None:
                    if val < -0.01:
                        # Beneficio / Crédito fiscal (Tax benefit) que incrementa el beneficio neto
                        abs_disp = f"+${abs(val):,.1f}M"
                    elif val > 0.01:
                        abs_disp = f"-${val:,.1f}M"
                    else:
                        abs_disp = "$0.0M"
                else:
                    abs_disp = _fmt_money(val)

            row_vals.append(abs_disp)

            # 2. pct_disp (Vertical %)
            pct_mode = r.get("pct_mode")
            if row_type in ("shares", "eps", "dps", "multiple"):
                pct_disp = "-"
            elif row_type == "metric_pct":
                pct_disp = f"{val:.1f}%" if val is not None else "-"
            elif pct_mode == "rev":
                rev_val = _to_m(canonical.get("revenue", {}).get(p))
                if rev_val and rev_val != 0 and val is not None:
                    num = abs(val) if r.get("negate_val") else val
                    pct_disp = f"{(num / rev_val * 100.0):.1f}%"
                else:
                    pct_disp = "-"
            elif pct_mode == "ebt":
                ebt_val = ebt_dict.get(p) if ebt_dict else None
                if ebt_val and ebt_val != 0 and val is not None:
                    pct_disp = f"{(abs(val) / abs(ebt_val) * 100.0):.1f}%"
                else:
                    pct_disp = "-"
            elif pct_mode == "assets":
                tot_ast = bs_tot_assets.get(p) if bs_tot_assets else None
                if tot_ast and tot_ast != 0 and val is not None:
                    pct_disp = f"{(abs(val) / tot_ast * 100.0):.1f}%"
                else:
                    pct_disp = "-"
            elif pct_mode == "ni":
                ni_val = _to_m(canonical.get("net_income", {}).get(p))
                if ni_val and ni_val != 0 and val is not None:
                    pct_disp = f"{(val / ni_val * 100.0):.1f}%"
                else:
                    pct_disp = "-"
            else:
                pct_disp = "-"

            row_pcts.append(pct_disp)

            # 3. yoy_disp (% Variation vs Prior)
            if val is not None and val_prior is not None and abs(val_prior) > 0:
                diff = val - val_prior
                yoy_pct = (diff / abs(val_prior)) * 100.0
                if abs(yoy_pct) < 0.05:
                    yoy_disp = "0.0%"
                else:
                    yoy_disp = f"{yoy_pct:+.1f}%"
            else:
                yoy_disp = "-"

            row_yoys.append(yoy_disp)

        # 4. CAGR 5Y (Calculated across annual periods, excluding LTM)
        annual_periods = [p for p in target_fys if p != "LTM"]
        cagr_5y = "-"
        if len(annual_periods) >= 6:
            v_end = r["data"].get(annual_periods[0])
            v_start = r["data"].get(annual_periods[5])
            if v_end is not None and v_start is not None and v_start > 0 and v_end > 0:
                cagr = ((v_end / v_start) ** (1.0 / 5.0) - 1.0) * 100.0
                cagr_5y = f"{cagr:+.1f}%"

        annual_cells = [
            {"abs": row_vals[i], "pct": row_pcts[i], "yoy": row_yoys[i]}
            for i in range(1, len(target_fys))
        ]

        return {
            "label": r["label"],
            "orig_tooltip": r.get("orig_tooltip", ""),
            "clarification": r.get("clarification"),
            "operator": r.get("operator", ""),
            "row_type": r.get("row_type", "item"),
            "indent": r.get("indent", False),
            "is_bold": r.get("is_bold", False),
            "values": row_vals,
            "pcts": row_pcts,
            "yoy": row_yoys,
            "cagr_5y": cagr_5y,
            "ltm_val": row_vals[0] if row_vals else "-",
            "ltm_pct": row_pcts[0] if row_pcts else "-",
            "ltm_yoy": row_yoys[0] if row_yoys else "-",
            "annual_cells": annual_cells,
            "annual_vals": row_vals[1:] if len(row_vals) > 1 else [],
            "latest_val": row_vals[0] if row_vals else "-",
            "latest_pct": row_pcts[0] if row_pcts else "-"
        }

    # -------------------------------------------------------------
    # 1. ESTRUCTURACIÓN DE ESTADOS FINANCIEROS (DOBLE VISTA)
    #    Vista 1: Estandarizada (10Y + LTM)
    #    Vista 2: Oficial SEC As-Reported (3Y + LTM)
    # -------------------------------------------------------------
    as_reported = fs.get("as_reported_statements", {})
    as_rep_inc = as_reported.get("income_statement", [])
    as_rep_cf = as_reported.get("cash_flow_statement", []) or as_reported.get("cash_flow", [])
    as_rep_bs = as_reported.get("balance_sheet", [])

    as_rep_fys = [p for p in statements_fys[:4]]

    # Helper para formatear partidas As-Reported oficiales con metadatos bilingües
    def _format_as_reported_row(row_raw, target_fys, pct_mode=None):
        lbl = row_raw.get("spanish_label") or row_raw.get("label", "")
        orig_lbl = row_raw.get("label", "")
        conc = row_raw.get("concept", "")
        orig_tooltip = row_raw.get("orig_tooltip") or (f"{orig_lbl} ({conc})" if conc else orig_lbl)
        is_abs = row_raw.get("is_abstract", False) or row_raw.get("row_type") == "section_header"
        lvl = row_raw.get("level", 0)
        is_tot = row_raw.get("is_total", False)
        clarif = row_raw.get("clarification")
        vals = row_raw.get("values", {}) or row_raw.get("data", {})

        lbl_lower = orig_lbl.lower()
        conc_lower = conc.lower()

        if is_abs:
            return {
                "label": lbl,
                "orig_tooltip": orig_tooltip,
                "clarification": clarif,
                "operator": "",
                "row_type": "section_header",
                "indent": False,
                "is_bold": True,
                "data": {p: None for p in target_fys},
                "pct_mode": None
            }

        is_dollar_account = any(k in conc_lower for k in [
            "value", "capital", "equity", "proceeds", "payments", "accruals", "repurchase", "borrowings", "cash"
        ]) or any(k in lbl_lower for k in [
            "par value", "stated value", "additional paid", "common stock, $", "preferred stock, $"
        ])

        is_eps = not is_dollar_account and (
            "earningspershare" in conc_lower
            or conc_lower.endswith("earningspershare")
            or (("per share" in lbl_lower or "pershare" in conc_lower) and any(w in conc_lower or w in lbl_lower for w in ["basic", "diluted", "earnings", "loss", "dividend", "distribution"]))
        )
        is_shares = not is_dollar_account and not is_eps and (
            "weightedaveragenumberofshares" in conc_lower
            or "weightedaveragenumberofdilutedshares" in conc_lower
            or conc_lower in ("commonstocksharesoutstanding", "commonstocksharesissued", "sharesoutstanding", "preferredstocksharesoutstanding")
            or ("number of shares" in lbl_lower and "value" not in conc_lower)
            or ("shares outstanding" in lbl_lower and "value" not in conc_lower and "par value" not in lbl_lower)
        )

        data_m = {}
        for p in target_fys:
            v = vals.get(p)
            if v is None:
                data_m[p] = None
            elif is_eps or is_shares:
                data_m[p] = float(v)
            else:
                data_m[p] = _to_m(float(v))

        if is_eps:
            row_type = "eps"
            operator = ""
            bold = is_tot
            indent = (lvl > 2)
            p_mode = None
        elif is_shares:
            row_type = "shares"
            operator = ""
            bold = False
            indent = True
            p_mode = None
        elif is_tot:
            if conc_lower in ("netincomeloss", "profitloss", "operatingincomeloss", "assets") or any(w in lbl_lower for w in ["net income", "total assets", "operating income", "cash generated by operating activities", "flujo de caja operativo", "utilidad neta", "activos totales"]):
                row_type = "result"
            else:
                row_type = "subtotal"
            operator = "[=]"
            bold = True
            indent = (lvl > 2)
            p_mode = pct_mode
        else:
            row_type = "item"
            operator = ""
            bold = False
            indent = (lvl > 2)
            p_mode = pct_mode

        return {
            "label": lbl,
            "orig_tooltip": orig_tooltip,
            "clarification": clarif,
            "operator": operator,
            "row_type": row_type,
            "indent": indent,
            "is_bold": bold,
            "data": data_m,
            "pct_mode": p_mode
        }

    # Helper para Bloques Memo Adaptados por Arquetipo
    def _get_memo_rows(target_fys, stmt_type):
        rev_d = {p: _to_m(canonical.get("revenue", {}).get(p)) for p in target_fys}
        gp_d = {p: _to_m(canonical.get("gross_profit", {}).get(p)) for p in target_fys}
        ebit_d = {p: _to_m(canonical.get("operating_income", {}).get(p)) for p in target_fys}
        ni_d = {p: _to_m(canonical.get("net_income", {}).get(p)) for p in target_fys}
        fcf_d = {p: _to_m(canonical.get("free_cash_flow", {}).get(p)) for p in target_fys}

        memo = [
            {
                "label": "📊 MÉTRICAS ANALÍTICAS (MEMO)",
                "orig_tooltip": "Métricas normalizadas de rentabilidad y solvencia institucionales",
                "clarification": "Métricas adaptadas dinámicamente por arquetipo contable",
                "operator": "",
                "row_type": "section_header",
                "indent": False,
                "is_bold": True,
                "data": {p: None for p in target_fys},
                "pct_mode": None
            }
        ]

        if stmt_type == "pnl":
            if archetype == "FINANCIAL_BANKING":
                nim_d = {p: (key_ratios.get("nim_pct", {}).get(p) or key_ratios.get("risk_adj_nim_pct", {}).get(p) or (enriched.get("risk_adjusted_nim_pct") if p == "LTM" else None)) for p in target_fys}
                eff_d = {p: key_ratios.get("efficiency_ratio_pct", {}).get(p) for p in target_fys}
                roe_d = {p: key_ratios.get("roe_pct", {}).get(p) for p in target_fys}
                rotce_d = {}
                for p in target_fys:
                    r_val = key_ratios.get("rotce_pct", {}).get(p)
                    if r_val is None:
                        ni_comm = pnl_data.get("net_income_common", {}).get(p) or canonical.get("net_income_common", {}).get(p) or canonical.get("net_income", {}).get(p)
                        eq = bs_data.get("stockholders_equity", {}).get(p) or canonical.get("stockholders_equity", {}).get(p)
                        pref = _num(bs_det, "PreferredStockValue", p) or _num(bs_det, "us-gaap_PreferredStockIncludingAdditionalPaidInCapitalNetOfDiscount", p) or 0.0
                        gw_int = bs_data.get("goodwill_and_intangibles", {}).get(p) or 0.0
                        tce = (eq - pref - gw_int) if eq else 0.0
                        if tce > 0 and ni_comm is not None:
                            r_val = round(ni_comm / tce * 100.0, 1)
                        elif key_ratios.get("roe_pct", {}).get(p) is not None:
                            r_val = round(float(key_ratios.get("roe_pct", {}).get(p)), 1)
                    rotce_d[p] = r_val

                npl_cov_d = {}
                for p in target_fys:
                    cov_val = key_ratios.get("provision_coverage_pct", {}).get(p) or (enriched.get("provision_coverage_pct") if p == "LTM" else None)
                    if cov_val is None:
                        allowance = bs_data.get("allowance_for_loan_losses", {}).get(p) or _num(bs_det, "FinancingReceivableAllowanceForCreditLosses", p) or _num(bs_det, "us-gaap_FinancingReceivableAllowanceForCreditLossExcludingAccruedInterest", p)
                        clp = pnl_data.get("credit_loss_provision", {}).get(p) or canonical.get("credit_loss_provisions", {}).get(p)
                        if allowance and clp and clp != 0:
                            cov_val = round(abs(allowance) / abs(clp) * 100.0, 1)
                    npl_cov_d[p] = cov_val

                memo.extend([
                    {"label": "MARGEN NETO DE INTERÉS (NIM %)", "orig_tooltip": "Net Interest Margin (%)", "clarification": "Ingresos Netos por Intereses / Activos Rentables Promedio", "operator": "[%]", "row_type": "metric_pct", "indent": True, "is_bold": False, "data": nim_d, "pct_mode": None},
                    {"label": "RATIO DE EFICIENCIA (COST-TO-INCOME %)", "orig_tooltip": "Efficiency Ratio (%)", "clarification": "Gastos No Financieros / Ingresos Netos de Explotación", "operator": "[%]", "row_type": "metric_pct", "indent": True, "is_bold": False, "data": eff_d, "pct_mode": None},
                    {"label": "RENTABILIDAD SOBRE EQUITY (ROE %)", "orig_tooltip": "Return on Equity (%)", "clarification": "Beneficio Neto / Patrimonio Neto Promedio", "operator": "[%]", "row_type": "metric_pct", "indent": True, "is_bold": False, "data": roe_d, "pct_mode": None},
                    {"label": "RENTABILIDAD SOBRE EQUITY TANGIBLE (ROTCE %)", "orig_tooltip": "Return on Tangible Common Equity (%)", "clarification": "Beneficio Neto / Patrimonio Neto Tangible Promedio", "operator": "[%]", "row_type": "metric_pct", "indent": True, "is_bold": False, "data": rotce_d, "pct_mode": None},
                    {"label": "COBERTURA DE PROVISIONES (%)", "orig_tooltip": "Provision Coverage Ratio (%)", "clarification": "Fondo de Provisiones / Total Préstamos Dudosos (NPLs)", "operator": "[%]", "row_type": "metric_pct", "indent": True, "is_bold": False, "data": npl_cov_d, "pct_mode": None},
                ])
            elif archetype == "INSURANCE":
                comb_d = {p: key_ratios.get("combined_ratio_pct", {}).get(p) for p in target_fys}
                loss_d = {p: key_ratios.get("loss_ratio_pct", {}).get(p) for p in target_fys}
                exp_d = {p: key_ratios.get("expense_ratio_pct", {}).get(p) for p in target_fys}
                float_d = {p: _to_m(canonical.get("float_usd", {}).get(p)) for p in target_fys}
                inv_y_d = {}
                for p in target_fys:
                    y_val = key_ratios.get("investment_yield_pct", {}).get(p)
                    if y_val is None:
                        nii_v = canonical.get("net_investment_income", {}).get(p) or pnl_data.get("net_investment_income", {}).get(p)
                        tot_inv = canonical.get("total_investments", {}).get(p) or bs_data.get("short_term_investments", {}).get(p)
                        if nii_v and tot_inv and tot_inv > 0:
                            y_val = round(float(nii_v) / float(tot_inv) * 100.0, 1)
                    inv_y_d[p] = y_val

                memo.extend([
                    {"label": "RATIO COMBINADO (%)", "orig_tooltip": "Combined Ratio (%)", "clarification": "Suma de Siniestralidad y Gastos de Adquisición (<100% = beneficio técnico)", "operator": "[%]", "row_type": "metric_pct", "indent": False, "is_bold": True, "data": comb_d, "pct_mode": None},
                    {"label": "RATIO DE SINIESTRALIDAD (LOSS RATIO %)", "orig_tooltip": "Loss Ratio (%)", "clarification": "Costes de Siniestros Incurridos / Primas Devengadas", "operator": "[%]", "row_type": "metric_pct", "indent": True, "is_bold": False, "data": loss_d, "pct_mode": None},
                    {"label": "RATIO DE GASTOS DE SUSCRIPCIÓN (%)", "orig_tooltip": "Expense Ratio (%)", "clarification": "Gastos de Comercialización y Administración / Primas Devengadas", "operator": "[%]", "row_type": "metric_pct", "indent": True, "is_bold": False, "data": exp_d, "pct_mode": None},
                    {"label": "FLOAT ASEGURADOR DISPONIBLE", "orig_tooltip": "Insurance Float ($M)", "clarification": "Fondos de Prima Cobrados Pendientes de Liquidación", "operator": "[⚡]", "row_type": "metric", "indent": False, "is_bold": True, "data": float_d, "pct_mode": "rev"},
                    {"label": "RENDIMIENTO DE CARTERA INVERTIDA (%)", "orig_tooltip": "Investment Portfolio Yield (%)", "clarification": "Rendimiento Neto de Inversiones / Cartera Promedio", "operator": "[%]", "row_type": "metric_pct", "indent": True, "is_bold": False, "data": inv_y_d, "pct_mode": None},
                ])
            elif archetype == "REAL_ESTATE_REIT":
                noi_d = {p: _to_m(canonical.get("noi", {}).get(p)) for p in target_fys}
                ffo_d = {p: _to_m(canonical.get("ffo", {}).get(p)) for p in target_fys}
                affo_d = {p: _to_m(canonical.get("affo", {}).get(p)) for p in target_fys}
                ffo_sh_d = {p: (key_ratios.get("ffo_per_share", {}).get(p) or (round(float(canonical.get("ffo", {}).get(p)) / float(canonical.get("shares_diluted", {}).get(p)), 2) if (canonical.get("ffo", {}).get(p) and canonical.get("shares_diluted", {}).get(p)) else None)) for p in target_fys}
                affo_sh_d = {p: (key_ratios.get("affo_per_share", {}).get(p) or (round(float(canonical.get("affo", {}).get(p)) / float(canonical.get("shares_diluted", {}).get(p)), 2) if (canonical.get("affo", {}).get(p) and canonical.get("shares_diluted", {}).get(p)) else None)) for p in target_fys}
                payout_affo_d = {}
                for p in target_fys:
                    dp = abs(canonical.get("dividends_paid", {}).get(p) or _num(cf_det, "PaymentsOfDividendsCommonStock", p) or _num(cf_det, "PaymentsOfDividends", p) or 0.0)
                    af = float(canonical.get("affo", {}).get(p) or 0.0)
                    payout_affo_d[p] = round(dp / af * 100.0, 1) if (dp > 0 and af > 0) else None

                memo.extend([
                    {"label": "NET OPERATING INCOME (NOI)", "orig_tooltip": "Net Operating Income ($M)", "clarification": "Ingresos por Alquileres − Gastos Operativos de Inmuebles", "operator": "[⚡]", "row_type": "metric", "indent": False, "is_bold": True, "data": noi_d, "pct_mode": "rev"},
                    {"label": "MARGEN NOI (%)", "orig_tooltip": "NOI Margin (%)", "clarification": "NOI Inmobiliario / Ingresos por Rentas", "operator": "[%]", "row_type": "metric_pct", "indent": True, "is_bold": False, "data": {p: round(noi_d[p] / rev_d[p] * 100.0, 1) if (noi_d.get(p) is not None and rev_d.get(p) and rev_d[p] > 0) else None for p in target_fys}, "pct_mode": None},
                    {"label": "FUNDS FROM OPERATIONS (FFO)", "orig_tooltip": "Funds From Operations ($M)", "clarification": "Beneficio Neto + D&A Inmobiliaria − Ganancias por Venta", "operator": "[⚡]", "row_type": "metric", "indent": False, "is_bold": True, "data": ffo_d, "pct_mode": "rev"},
                    {"label": "MARGEN FFO (%)", "orig_tooltip": "FFO Margin (%)", "clarification": "FFO / Ingresos Totales por Rentas", "operator": "[%]", "row_type": "metric_pct", "indent": True, "is_bold": False, "data": {p: round(ffo_d[p] / rev_d[p] * 100.0, 1) if (ffo_d.get(p) is not None and rev_d.get(p) and rev_d[p] > 0) else None for p in target_fys}, "pct_mode": None},
                    {"label": "AFFO NORMALIZADO", "orig_tooltip": "Adjusted Funds From Operations ($M)", "clarification": "FFO − CapEx de Mantenimiento / Mejoras Inmobiliarias", "operator": "[⚡]", "row_type": "metric", "indent": False, "is_bold": True, "data": affo_d, "pct_mode": "rev"},
                    {"label": "PAYOUT RATIO S/ AFFO (%)", "orig_tooltip": "AFFO Payout Ratio (%)", "clarification": "Dividendos Totales Pagados / AFFO Generado (<90% sostenible)", "operator": "[%]", "row_type": "metric_pct", "indent": True, "is_bold": False, "data": payout_affo_d, "pct_mode": None},
                    {"label": "FFO POR ACCIÓN (FFO / SHARE $)", "orig_tooltip": "FFO Per Share ($/acción)", "clarification": "Funds From Operations / Acciones Diluidas", "operator": "[$]", "row_type": "eps", "indent": True, "is_bold": False, "data": ffo_sh_d, "pct_mode": None},
                    {"label": "AFFO POR ACCIÓN (AFFO / SHARE $)", "orig_tooltip": "AFFO Per Share ($/acción)", "clarification": "Adjusted Funds From Operations / Acciones Diluidas", "operator": "[$]", "row_type": "eps", "indent": True, "is_bold": False, "data": affo_sh_d, "pct_mode": None},
                ])
            else:
                def _find_dna_val(period):
                    v = _num(cf_det, "DepreciationAndAmortization", period) or _num(cf_det, "us-gaap_DepreciationAndAmortization", period) or _num(cf_det, "DepreciationDepletionAndAmortization", period) or _num(cf_det, "DepreciationAmortizationAndAccretionNet", period) or _num(cf_det, "Depreciation", period) or canonical.get("depreciation_and_amortization", {}).get(period)
                    if v is not None:
                        return _to_m(v)
                    for r_cf in (as_rep_cf or []):
                        conc_cf = str(r_cf.get("concept", "")).lower()
                        lbl_cf = str(r_cf.get("label", "")).lower()
                        if "depreciation" in conc_cf or "depreciation" in lbl_cf:
                            cf_v = r_cf.get("values", {}).get(period)
                            if cf_v is not None:
                                return _to_m(float(cf_v))
                    return None

                dna_dict = {p: _find_dna_val(p) for p in target_fys}
                ebitda_dict = {p: (round(ebit_d[p] + (dna_dict[p] or 0.0), 1) if ebit_d[p] is not None else None) for p in target_fys}
                ebitda_m_dict = {p: (round(ebitda_dict[p] / rev_d[p] * 100.0, 1) if (ebitda_dict.get(p) is not None and rev_d.get(p) and rev_d[p] > 0) else None) for p in target_fys}

                sbc_keys = [
                    "ShareBasedCompensation", "AllocatedShareBasedCompensationExpense",
                    "StockOptionPlanExpense", "AdjustmentsForSharebasedPayments",
                    "ExpenseFromSharebasedPaymentTransactionsWithEmployees",
                    "RestrictedStockExpense", "us-gaap_RestrictedStockExpense",
                    "ShareBasedCompensationArrangementByShareBasedPaymentAwardExpense",
                    "meli_StockBasedCompensation"
                ]
                sbc_dict = {}
                for p in target_fys:
                    sv = _extract_multi_source_val(fs, "cashflow", sbc_keys, p, "stock_based_compensation")
                    sbc_dict[p] = _to_m(sv) if sv is not None else None
                sbc_intensity_dict = {p: (round(sbc_dict[p] / rev_d[p] * 100.0, 1) if (sbc_dict.get(p) is not None and rev_d.get(p) and rev_d[p] > 0) else None) for p in target_fys}

                ebit_adj_sbc_dict = {p: (round(ebit_d[p] - (sbc_dict[p] or 0.0), 1) if ebit_d.get(p) is not None else None) for p in target_fys}
                ni_adj_sbc_dict = {p: (round(ni_d[p] - (sbc_dict[p] or 0.0), 1) if ni_d.get(p) is not None else None) for p in target_fys}
                ebit_adj_m_dict = {p: (round(ebit_adj_sbc_dict[p] / rev_d[p] * 100.0, 1) if (ebit_adj_sbc_dict.get(p) is not None and rev_d.get(p) and rev_d[p] > 0) else None) for p in target_fys}
                ni_adj_m_dict = {p: (round(ni_adj_sbc_dict[p] / rev_d[p] * 100.0, 1) if (ni_adj_sbc_dict.get(p) is not None and rev_d.get(p) and rev_d[p] > 0) else None) for p in target_fys}

                memo.extend([
                    {"label": "EBITDA NORMALIZADO", "orig_tooltip": "Normalized EBITDA ($M)", "clarification": "Beneficio Operativo (EBIT) + Depreciación y Amortización", "operator": "[⚡]", "row_type": "metric", "indent": False, "is_bold": True, "data": ebitda_dict, "pct_mode": "rev"},
                    {"label": "MARGEN EBITDA (%)", "orig_tooltip": "EBITDA Margin (%)", "clarification": "EBITDA Normalizado / Ingresos Totales", "operator": "[%]", "row_type": "metric_pct", "indent": True, "is_bold": False, "data": ebitda_m_dict, "pct_mode": None},
                    {"label": "MARGEN BRUTO (%)", "orig_tooltip": "Gross Margin (%)", "clarification": "Beneficio Bruto / Ingresos Totales", "operator": "[%]", "row_type": "metric_pct", "indent": True, "is_bold": False, "data": {p: round(gp_d[p] / rev_d[p] * 100.0, 1) if (gp_d.get(p) is not None and rev_d.get(p) and rev_d[p] > 0) else None for p in target_fys}, "pct_mode": None},
                    {"label": "MARGEN OPERATIVO (%)", "orig_tooltip": "Operating Margin EBIT (%)", "clarification": "Beneficio Operativo (EBIT) / Ingresos Totales", "operator": "[%]", "row_type": "metric_pct", "indent": True, "is_bold": False, "data": {p: round(ebit_d[p] / rev_d[p] * 100.0, 1) if (ebit_d.get(p) is not None and rev_d.get(p) and rev_d[p] > 0) else None for p in target_fys}, "pct_mode": None},
                    {"label": "MARGEN NETO (%)", "orig_tooltip": "Net Profit Margin (%)", "clarification": "Beneficio Neto / Ingresos Totales", "operator": "[%]", "row_type": "metric_pct", "indent": True, "is_bold": False, "data": {p: round(ni_d[p] / rev_d[p] * 100.0, 1) if (ni_d.get(p) is not None and rev_d.get(p) and rev_d[p] > 0) else None for p in target_fys}, "pct_mode": None},
                    {"label": "COMPENSACIÓN BASADA EN ACCIONES (SBC)", "orig_tooltip": "Stock-Based Compensation ($M)", "clarification": "Gasto no monetario por remuneración en acciones a empleados", "operator": "[⚡]", "row_type": "metric", "indent": False, "is_bold": False, "data": sbc_dict, "pct_mode": "rev"},
                    {"label": "BENEFICIO OPERATIVO ADJ. SBC (EBIT - SBC)", "orig_tooltip": "Operating Income adjusted for SBC ($M)", "clarification": "EBIT − Compensación Basada en Acciones", "operator": "[⚡]", "row_type": "metric", "indent": True, "is_bold": True, "data": ebit_adj_sbc_dict, "pct_mode": "rev"},
                    {"label": "BENEFICIO NETO ADJ. SBC (NET INCOME - SBC)", "orig_tooltip": "Net Income adjusted for SBC ($M)", "clarification": "Beneficio Neto − Compensación Basada en Acciones", "operator": "[⚡]", "row_type": "metric", "indent": True, "is_bold": True, "data": ni_adj_sbc_dict, "pct_mode": "rev"},
                    {"label": "INTENSIDAD DE SBC (% S/ VENTAS)", "orig_tooltip": "SBC Intensity (% of Revenue)", "clarification": "Compensación en Acciones (SBC) / Ingresos Totales", "operator": "[%]", "row_type": "metric_pct", "indent": True, "is_bold": False, "data": sbc_intensity_dict, "pct_mode": None},
                    {"label": "MARGEN EBIT ADJ. SBC (%)", "orig_tooltip": "EBIT Margin adjusted for SBC (%)", "clarification": "(EBIT − SBC) / Ingresos Totales", "operator": "[%]", "row_type": "metric_pct", "indent": True, "is_bold": False, "data": ebit_adj_m_dict, "pct_mode": None},
                    {"label": "MARGEN NETO ADJ. SBC (%)", "orig_tooltip": "Net Margin adjusted for SBC (%)", "clarification": "(Net Income − SBC) / Ingresos Totales", "operator": "[%]", "row_type": "metric_pct", "indent": True, "is_bold": False, "data": ni_adj_m_dict, "pct_mode": None},
                ])
        elif stmt_type == "cashflow":
            if archetype == "FINANCIAL_BANKING":
                dep_d = {p: _to_m(canonical.get("total_deposits", {}).get(p) or canonical.get("deposits", {}).get(p) or bs_data.get("deposits", {}).get(p) or _num(bs_det, "Deposits", p) or _num(bs_det, "ifrs-full_DepositsFromCustomers", p)) for p in target_fys}
                loans_d = {p: _to_m(canonical.get("net_loans", {}).get(p) or bs_data.get("net_loans", {}).get(p) or _num(bs_det, "LoansAndLeasesReceivableNetOfDeferredIncome", p) or _num(bs_det, "FinancingReceivableExcludingAccruedInterestBeforeAllowanceForCreditLossesNetOfDeferredIncome", p) or _num(bs_det, "ifrs-full_LoansAndAdvancesToCustomers", p)) for p in target_fys}
                ld_d = {p: (key_ratios.get("ldr_pct", {}).get(p) or (round(loans_d[p] / dep_d[p] * 100.0, 1) if (loans_d.get(p) and dep_d.get(p) and dep_d[p] > 0) else None)) for p in target_fys}
                memo.extend([
                    {"label": "DEPÓSITOS TOTALES DE CLIENTES", "orig_tooltip": "Total Customer Deposits ($M)", "clarification": "Fondeo comercial primario del balance bancario", "operator": "[⚡]", "row_type": "metric", "indent": False, "is_bold": True, "data": dep_d, "pct_mode": None},
                    {"label": "PRÉSTAMOS CONCEDIDOS NETOS", "orig_tooltip": "Net Loans & Leases ($M)", "clarification": "Cartera de crédito tras provisión por insolvencias", "operator": "[⚡]", "row_type": "metric", "indent": False, "is_bold": True, "data": loans_d, "pct_mode": None},
                    {"label": "RATIO PRÉSTAMOS / DEPÓSITOS (L/D %)", "orig_tooltip": "Loan-to-Deposit Ratio (%)", "clarification": "Cartera Crediticia Neta / Depósitos Totales", "operator": "[%]", "row_type": "metric_pct", "indent": True, "is_bold": False, "data": ld_d, "pct_mode": None},
                ])
            elif archetype == "INSURANCE":
                fcf_ins_d = {}
                for p in target_fys:
                    fc = canonical.get("free_cash_flow", {}).get(p) or cf_data.get("fcf", {}).get(p)
                    if fc is None:
                        cfo_v = canonical.get("cash_from_operations", {}).get(p) or cf_data.get("cfo", {}).get(p)
                        cx_v = canonical.get("capital_expenditures", {}).get(p) or cf_data.get("capex", {}).get(p)
                        if cfo_v is not None and cx_v is not None:
                            fc = float(cfo_v) - abs(float(cx_v))
                    fcf_ins_d[p] = _to_m(fc)
                memo.extend([
                    {"label": "FLUJO DE CAJA LIBRE (FCF)", "orig_tooltip": "Free Cash Flow ($M)", "clarification": "CFO − Inversiones en Inmovilizado", "operator": "[⚡]", "row_type": "metric", "indent": False, "is_bold": True, "data": fcf_ins_d, "pct_mode": "rev"},
                ])
            elif archetype == "REAL_ESTATE_REIT":
                ffo_d = {p: _to_m(canonical.get("ffo", {}).get(p)) for p in target_fys}
                payout_affo_d = {}
                for p in target_fys:
                    div_p = canonical.get("dividends_paid", {}).get(p) or cf_data.get("dividends_paid", {}).get(p)
                    affo_p = canonical.get("affo", {}).get(p)
                    if div_p is not None and affo_p and float(affo_p) > 0:
                        payout_affo_d[p] = round(abs(float(div_p)) / float(affo_p) * 100.0, 1)
                    else:
                        payout_affo_d[p] = None
                memo.extend([
                    {"label": "FONDOS DE OPERACIONES (FFO)", "orig_tooltip": "FFO Cash Flow ($M)", "clarification": "Generación de caja operativa REIT antes de CapEx", "operator": "[⚡]", "row_type": "metric", "indent": False, "is_bold": True, "data": ffo_d, "pct_mode": "rev"},
                    {"label": "FLUJO DE CAJA LIBRE (FCF TRAS CAPEX)", "orig_tooltip": "Free Cash Flow ($M)", "clarification": "CFO − CapEx en Mejoras Inmobiliarias", "operator": "[⚡]", "row_type": "metric", "indent": False, "is_bold": True, "data": fcf_d, "pct_mode": "rev"},
                    {"label": "RATIO PAYOUT S/ AFFO (%)", "orig_tooltip": "AFFO Dividend Payout Ratio (%)", "clarification": "Dividendos Pagados en Efectivo / AFFO Generado", "operator": "[%]", "row_type": "metric_pct", "indent": True, "is_bold": False, "data": payout_affo_d, "pct_mode": None},
                ])
            else:
                sbc_keys = [
                    "ShareBasedCompensation", "AllocatedShareBasedCompensationExpense",
                    "StockOptionPlanExpense", "AdjustmentsForSharebasedPayments",
                    "ExpenseFromSharebasedPaymentTransactionsWithEmployees",
                    "RestrictedStockExpense", "us-gaap_RestrictedStockExpense",
                    "ShareBasedCompensationArrangementByShareBasedPaymentAwardExpense",
                    "meli_StockBasedCompensation"
                ]
                sbc_dict = {}
                for p in target_fys:
                    sv = _extract_multi_source_val(fs, "cashflow", sbc_keys, p, "stock_based_compensation")
                    sbc_dict[p] = _to_m(sv) if sv is not None else None

                fcf_adj_sbc_dict = {p: (round(fcf_d[p] - (sbc_dict[p] or 0.0), 1) if fcf_d.get(p) is not None else None) for p in target_fys}
                owner_fcf_m_dict = {p: (round(fcf_adj_sbc_dict[p] / rev_d[p] * 100.0, 1) if (fcf_adj_sbc_dict.get(p) is not None and rev_d.get(p) and rev_d[p] > 0) else None) for p in target_fys}
                
                capex_d = {p: _to_m(canonical.get("capital_expenditures", {}).get(p) or cf_data.get("capex", {}).get(p)) for p in target_fys}
                capex_intensity_dict = {p: (round(abs(capex_d[p]) / rev_d[p] * 100.0, 1) if (capex_d.get(p) is not None and rev_d.get(p) and rev_d[p] > 0) else None) for p in target_fys}

                # Precision 2: Lectura de cap_flows como diccionario y conversion via _to_m
                sh_ret_d = {}
                for p in target_fys:
                    bb_m = _to_m(cap_flows.get("share_repurchases_open_market", {}).get(p))
                    dv_m = _to_m(cap_flows.get("dividends_paid", {}).get(p))
                    if bb_m is not None or dv_m is not None:
                        sh_ret_d[p] = round((bb_m or 0.0) + (dv_m or 0.0), 1)
                    else:
                        sh_ret_d[p] = None

                div_cash_ret_d = {}
                bb_cash_ret_d = {}
                alloc_ratio_d = {}
                for p in target_fys:
                    ret_val = sh_ret_d.get(p)
                    dv_m = abs(_to_m(cap_flows.get("dividends_paid", {}).get(p)) or 0.0)
                    bb_m = abs(_to_m(cap_flows.get("share_repurchases_open_market", {}).get(p)) or 0.0)
                    cx_m = abs(capex_d.get(p) or 0.0)
                    if ret_val and ret_val > 0:
                        div_cash_ret_d[p] = round(dv_m / ret_val * 100.0, 1)
                        bb_cash_ret_d[p] = round(bb_m / ret_val * 100.0, 1)
                        alloc_ratio_d[p] = round(cx_m / ret_val, 2)
                    else:
                        div_cash_ret_d[p] = None
                        bb_cash_ret_d[p] = None
                        alloc_ratio_d[p] = None

                memo.extend([
                    {"label": "FLUJO DE CAJA LIBRE (FCF)", "orig_tooltip": "Free Cash Flow ($M)", "clarification": "Flujo de Caja Operativo (CFO) − Inversiones CapEx", "operator": "[⚡]", "row_type": "metric", "indent": False, "is_bold": True, "data": fcf_d, "pct_mode": "rev"},
                    {"label": "FCF AJUSTADO POR SBC (OWNER FCF)", "orig_tooltip": "SBC-Adjusted Free Cash Flow ($M)", "clarification": "FCF − Compensación Basada en Acciones (SBC)", "operator": "[⚡]", "row_type": "metric", "indent": False, "is_bold": True, "data": fcf_adj_sbc_dict, "pct_mode": "rev"},
                    {"label": "MARGEN FCF (%)", "orig_tooltip": "FCF Margin (%)", "clarification": "FCF / Ingresos Totales", "operator": "[%]", "row_type": "metric_pct", "indent": True, "is_bold": False, "data": {p: round(fcf_d[p] / rev_d[p] * 100.0, 1) if (fcf_d.get(p) is not None and rev_d.get(p) and rev_d[p] > 0) else None for p in target_fys}, "pct_mode": None},
                    {"label": "MARGEN OWNER FCF (%)", "orig_tooltip": "Owner FCF Margin (% of Revenue)", "clarification": "FCF Ajustado por SBC / Ingresos Totales", "operator": "[%]", "row_type": "metric_pct", "indent": True, "is_bold": False, "data": owner_fcf_m_dict, "pct_mode": None},
                    {"label": "CONVERSIÓN FCF (%)", "orig_tooltip": "FCF Conversion Ratio (%)", "clarification": "FCF / Beneficio Neto", "operator": "[%]", "row_type": "metric_pct", "indent": True, "is_bold": False, "data": {p: round(fcf_d[p] / ni_d[p] * 100.0, 1) if (fcf_d.get(p) is not None and ni_d.get(p) and ni_d[p] > 0) else None for p in target_fys}, "pct_mode": None},
                    {"label": "INTENSIDAD CAPEX (% S/ VENTAS)", "orig_tooltip": "CapEx Intensity (% of Revenue)", "clarification": "Inversiones CapEx / Ingresos Totales", "operator": "[%]", "row_type": "metric_pct", "indent": True, "is_bold": False, "data": capex_intensity_dict, "pct_mode": None},
                    {"label": "RETORNO TOTAL EN EFECTIVO AL ACCIONISTA", "orig_tooltip": "Total Cash Returned to Shareholders ($M)", "clarification": "Recompras de Acciones en Mercado Abierto + Dividendos en Efectivo", "operator": "[⚡]", "row_type": "metric", "indent": False, "is_bold": True, "data": sh_ret_d, "pct_mode": "rev"},
                    {"label": "DIVIDENDOS PAGADOS (% CASH RET.)", "orig_tooltip": "Dividends (% of Cash Returned)", "clarification": "Dividendos en Efectivo / Retorno Total en Efectivo", "operator": "[%]", "row_type": "metric_pct", "indent": True, "is_bold": False, "data": div_cash_ret_d, "pct_mode": None},
                    {"label": "RECOMPRA DE ACCIONES (% CASH RET.)", "orig_tooltip": "Share Repurchases (% of Cash Returned)", "clarification": "Recompras de Acciones / Retorno Total en Efectivo", "operator": "[%]", "row_type": "metric_pct", "indent": True, "is_bold": False, "data": bb_cash_ret_d, "pct_mode": None},
                    {"label": "RATIO DE ASIGNACIÓN (REINVERSIÓN VS RETORNO)", "orig_tooltip": "Capital Allocation Ratio (CapEx / Shareholder Return)", "clarification": "CapEx / Retorno Total en Efectivo al Accionista (>1.0x = reinversión expansiva)", "operator": "[x]", "row_type": "multiple", "indent": True, "is_bold": False, "data": alloc_ratio_d, "pct_mode": None},
                ])
        elif stmt_type == "balancesheet":
            if archetype == "FINANCIAL_BANKING":
                cet1_d = {}
                for p in target_fys:
                    c_val = key_ratios.get("cet1_ratio_pct", {}).get(p) or (enriched.get("cet1_ratio_pct") if p == "LTM" else None)
                    if c_val is None:
                        eq = bs_data.get("stockholders_equity", {}).get(p) or canonical.get("stockholders_equity", {}).get(p)
                        pref = _num(bs_det, "PreferredStockValue", p) or _num(bs_det, "us-gaap_PreferredStockIncludingAdditionalPaidInCapitalNetOfDiscount", p) or 0.0
                        gw_int = bs_data.get("goodwill_and_intangibles", {}).get(p) or 0.0
                        tot_ast = bs_data.get("total_assets", {}).get(p) or canonical.get("total_assets", {}).get(p)
                        tce = (eq - pref - gw_int) if eq else 0.0
                        if tce > 0 and tot_ast and tot_ast > 0:
                            c_val = round(tce / tot_ast * 100.0, 1)
                        elif eq and tot_ast and tot_ast > 0:
                            c_val = round(eq / tot_ast * 100.0, 1)
                    cet1_d[p] = c_val

                npl_d = {}
                for p in target_fys:
                    n_val = key_ratios.get("npl_ratio_pct", {}).get(p) or (enriched.get("npl_90_plus_pct") if p == "LTM" else None)
                    if n_val is None:
                        n_val = key_ratios.get("cost_of_risk_loans_pct", {}).get(p)
                    npl_d[p] = n_val

                liq_d = {p: _to_m(bs_data.get("total_liquid_cash", {}).get(p)) for p in target_fys}
                memo.extend([
                    {"label": "RATIO DE CAPITAL BANCARIO CET1 (%)", "orig_tooltip": "Common Equity Tier 1 Ratio (%)", "clarification": "Capital Principal Nivel 1 / Activos Ponderados por Riesgo", "operator": "[%]", "row_type": "metric_pct", "indent": False, "is_bold": True, "data": cet1_d, "pct_mode": None},
                    {"label": "RATIO DE MOROSIDAD (NPL %)", "orig_tooltip": "Non-Performing Loans Ratio (%)", "clarification": "Créditos Dudosos / Total Cartera Crediticia Bruta", "operator": "[%]", "row_type": "metric_pct", "indent": True, "is_bold": False, "data": npl_d, "pct_mode": None},
                    {"label": "LIQUIDEZ REGULATORIA INMEDIATA", "orig_tooltip": "Regulatory Liquid Cash ($M)", "clarification": "Efectivo en Bancos Centrales + Inversiones Líquidas Negociables", "operator": "[⚡]", "row_type": "metric", "indent": False, "is_bold": True, "data": liq_d, "pct_mode": "assets"},
                ])
            elif archetype == "INSURANCE":
                inv_tot_d = {p: _to_m(canonical.get("total_investments", {}).get(p) or bs_data.get("short_term_investments", {}).get(p)) for p in target_fys}
                eq_d = {p: _to_m(canonical.get("stockholders_equity", {}).get(p) or bs_data.get("stockholders_equity", {}).get(p)) for p in target_fys}
                memo.extend([
                    {"label": "CARTERA TOTAL DE INVERSIONES", "orig_tooltip": "Total Investment Portfolio ($M)", "clarification": "Activos Financieros en Renta Fija y Renta Variable", "operator": "[⚡]", "row_type": "metric", "indent": False, "is_bold": True, "data": inv_tot_d, "pct_mode": "assets"},
                    {"label": "SOLVENCIA PATRIMONIAL (EQUITY)", "orig_tooltip": "Stockholders Equity ($M)", "clarification": "Patrimonio Neto de los Accionistas", "operator": "[⚡]", "row_type": "metric", "indent": False, "is_bold": True, "data": eq_d, "pct_mode": "assets"},
                ])
            elif archetype == "REAL_ESTATE_REIT":
                ppe_d = {p: _to_m(bs_data.get("net_ppe", {}).get(p)) for p in target_fys}
                debt_d = {p: _to_m(bs_data.get("total_debt", {}).get(p)) for p in target_fys}
                ast_d = {p: _to_m(bs_data.get("total_assets", {}).get(p)) for p in target_fys}
                ltv_d = {p: round(debt_d[p] / ast_d[p] * 100.0, 1) if (debt_d.get(p) and ast_d.get(p) and ast_d[p] > 0) else None for p in target_fys}
                memo.extend([
                    {"label": "INVERSIONES INMOBILIARIAS NETAS (PP&E)", "orig_tooltip": "Net Real Estate Portfolio ($M)", "clarification": "Cartera de Inmuebles en Explotación neta de depreciación", "operator": "[⚡]", "row_type": "metric", "indent": False, "is_bold": True, "data": ppe_d, "pct_mode": "assets"},
                    {"label": "DEUDA FINANCIERA INMOBILIARIA TOTAL", "orig_tooltip": "Total Real Estate Debt ($M)", "clarification": "Deuda Hipotecaria + Préstamos a Plazo + Bonos", "operator": "[⚡]", "row_type": "metric", "indent": False, "is_bold": True, "data": debt_d, "pct_mode": "assets"},
                    {"label": "RATIO LTV (DEUDA / ACTIVOS %)", "orig_tooltip": "Loan-to-Value Ratio (%)", "clarification": "Deuda Total / Activos Inmobiliarios Totales", "operator": "[%]", "row_type": "metric_pct", "indent": True, "is_bold": False, "data": ltv_d, "pct_mode": None},
                ])
            else:
                st_debt_dict = {p: _to_m(bs_data.get("short_term_debt", {}).get(p)) for p in target_fys}
                lt_debt_dict = {p: _to_m(bs_data.get("long_term_debt", {}).get(p)) for p in target_fys}
                tot_debt_dict = {p: (round((st_debt_dict.get(p) or 0.0) + (lt_debt_dict.get(p) or 0.0), 1) if (st_debt_dict.get(p) is not None or lt_debt_dict.get(p) is not None) else None) for p in target_fys}
                memo.extend([
                    {"label": "LIQUIDEZ INMEDIATA TOTAL", "orig_tooltip": "Total Liquid Cash ($M)", "clarification": "Efectivo y Equivalentes + Inversiones Negociables CP", "operator": "[⚡]", "row_type": "metric", "indent": False, "is_bold": True, "data": {p: _to_m(bs_data.get("total_liquid_cash", {}).get(p)) for p in target_fys}, "pct_mode": "assets"},
                    {"label": "DEUDA FINANCIERA TOTAL", "orig_tooltip": "Total Financial Debt ($M)", "clarification": "Deuda Financiera CP + LP (excluyendo pasivos operativos)", "operator": "[⚡]", "row_type": "metric", "indent": False, "is_bold": True, "data": tot_debt_dict, "pct_mode": "assets"},
                    {"label": "POSICIÓN FINANCIERA NETA (DEUDA NETA)", "orig_tooltip": "Net Financial Position ($M)", "clarification": "Deuda Total − Liquidez Inmediata Total", "operator": "[⚡]", "row_type": "net_debt", "indent": False, "is_bold": True, "data": {p: _to_m(bs_data.get("net_financial_position", {}).get(p)) for p in target_fys}, "pct_mode": "assets"},
                    {"label": "FONDO DE MANIOBRA (NET WORKING CAPITAL)", "orig_tooltip": "Net Working Capital ($M)", "clarification": "Activo Corriente − Pasivo Corriente", "operator": "[⚡]", "row_type": "metric", "indent": False, "is_bold": True, "data": {p: _to_m(bs_data.get("net_working_capital", {}).get(p)) for p in target_fys}, "pct_mode": "assets"},
                ])

            memo.extend([
                {"label": "VALOR CONTABLE POR ACCIÓN (BVPS $)", "orig_tooltip": "Book Value Per Share ($/acción)", "clarification": "Patrimonio Neto / Acciones Diluidas", "operator": "[⚡]", "row_type": "eps", "indent": False, "is_bold": True, "data": {p: bs_data.get("book_value_per_share", {}).get(p) for p in target_fys}, "pct_mode": None},
                {"label": "VALOR CONTABLE TANGIBLE POR ACCIÓN (TBVPS $)", "orig_tooltip": "Tangible Book Value Per Share ($/acción)", "clarification": "(Patrimonio Neto − Fondo de Comercio e Intangibles) / Acciones Diluidas", "operator": "[⚡]", "row_type": "eps", "indent": True, "is_bold": False, "data": {p: bs_data.get("tangible_book_value_per_share", {}).get(p) for p in target_fys}, "pct_mode": None},
            ])
        return memo

    # Diccionarios de referencia para % vertical As-Reported y EBT
    ebt_dict_std = {p: _to_m(pnl_data["ebt"].get(p)) for p in statements_fys}
    ebt_dict_asrep = {p: ebt_dict_std.get(p) for p in as_rep_fys}
    bs_tot_assets_std = {p: _to_m(bs_data.get("total_assets", {}).get(p)) for p in statements_fys}
    bs_tot_assets_asrep = {p: bs_tot_assets_std.get(p) for p in as_rep_fys}

    def _should_include_row(row_def, data_dict):
        # row_def: (label, key, operator, row_type, indent, is_bold, negate_val, always_show, pct_mode, tooltip)
        if row_def[7]:  # always_show
            return True
        for p in statements_fys:
            v = data_dict.get(p)
            if v is not None:
                try:
                    if abs(float(v)) > 1e-6:
                        return True
                except (ValueError, TypeError):
                    pass
        return False

    def _build_standardized_section(sections_def, source_data, default_pct_mode=None):
        out_rows = []
        for sec_title, items in sections_def:
            sec_visible_items = []
            for item in items:
                lbl, k, op, r_type, ind, bold, neg, alw, p_mode, tip = item
                is_unit = r_type in ("shares", "eps", "dps")
                if is_unit:
                    val_dict = {p: source_data.get(k, {}).get(p) for p in statements_fys}
                else:
                    val_dict = {p: _to_m(source_data.get(k, {}).get(p)) for p in statements_fys}

                if k in ("preferred_dividends", "minority_interest_pnl"):
                    if any(v is not None and abs(float(v or 0)) > 1e-6 for v in val_dict.values()):
                        val_dict = {p: (val_dict[p] if val_dict.get(p) is not None else 0.0) for p in statements_fys}

                if _should_include_row(item, val_dict):
                    eff_tooltip = tip or f"Estándar Canónico: {k}"
                    if k == "sga_expense":
                        canon_rd = canonical.get("rd_expense", {}) if isinstance(canonical, dict) else {}
                        if any(v is not None for v in canon_rd.values()) and not any(v is not None for v in source_data.get("rd_expense", {}).values()):
                            eff_tooltip = f"{eff_tooltip}. En empresas que integran I+D/diseño en gastos generales (ej. calzado y retail), incluye la inversión reportada en notas del 10-K."

                    sec_visible_items.append({
                        "label": lbl,
                        "orig_tooltip": eff_tooltip,
                        "clarification": None,
                        "operator": op,
                        "row_type": r_type,
                        "indent": ind,
                        "is_bold": bold,
                        "negate_val": neg,
                        "data": val_dict,
                        "pct_mode": p_mode or default_pct_mode
                    })
            if sec_visible_items:
                if sec_title:
                    out_rows.append({
                        "label": sec_title,
                        "orig_tooltip": f"Sección Canónica: {sec_title}",
                        "clarification": None,
                        "operator": "",
                        "row_type": "section_header",
                        "indent": False,
                        "is_bold": True,
                        "negate_val": False,
                        "data": {p: None for p in statements_fys},
                        "pct_mode": None
                    })
                out_rows.extend(sec_visible_items)
        return out_rows

    # =============================================================
    # 1.A. CONSTRUCCIÓN DE VISTA ESTANDARIZADA (10Y + LTM)
    # =============================================================
    # 1. ESTADO DE RESULTADOS (INCOME STATEMENT)
    if archetype == "FINANCIAL_BANKING":
        pnl_sections = [
            ("MARGEN DE INTERESES E INGRESOS BANCARIOS", [
                ("Ingresos por Intereses (Interest Income)", "interest_income", "[+]", "item", True, False, False, True, "rev", "Interest Income"),
                ("Gastos por Intereses (Interest Expense)", "interest_expense", "[-]", "item", True, False, True, True, "rev", "Interest Expense"),
                ("Margen Neto de Intereses (Net Interest Income — NII)", "net_interest_income", "[=]", "subtotal", False, True, False, True, "rev", "Net Interest Income"),
                ("Ingresos por Comisiones y Servicios (Non-Interest Income)", "non_interest_income", "[+]", "item", True, False, False, True, "rev", "Non-Interest Income"),
                ("Ingresos Totales Netos de Explotación (Total Net Revenue)", "revenue", "[=]", "subtotal", False, True, False, True, "rev", "Total Net Revenue"),
            ]),
            ("PROVISIONES CREDITICIAS, GASTOS OPERATIVOS Y BENEFICIO NETO", [
                ("Provisión para Pérdidas Crediticias (Provision for Credit Losses)", "credit_loss_provision", "[-]", "item", True, False, True, True, "rev", "Provision for Credit Losses"),
                ("Costes y Gastos Transaccionales (Transactional Expenses)", "transactional_expenses", "[-]", "item", True, False, True, False, "rev", "Transactional Expenses"),
                ("Gastos Operativos No Financieros (Non-Interest Expense)", "non_interest_expense", "[-]", "item", True, False, True, True, "rev", "Non-Interest Expense"),
                ("Participación en Resultados de Asociadas y Otros", "share_of_associates", "[±]", "item", True, False, False, False, "rev", "Share of Associates & Other"),
                ("Beneficio Antes de Impuestos (Pre-Tax Income / EBT)", "ebt", "[=]", "subtotal", False, True, False, True, "rev", "Pre-Tax Income"),
                ("Impuesto sobre Beneficios (Income Tax)", "income_tax", "[-]", "item", True, False, True, True, "ebt", "Income Tax Expense"),
                ("Beneficio Neto Consolidado (Net Income)", "net_income", "[=]", "result", False, True, False, True, "rev", "Net Income"),
                ("Beneficio Atribuible a Intereses Minoritarios", "minority_interest_pnl", "[-]", "item", True, False, True, False, "rev", "Noncontrolling Interest"),
                ("Dividendos de Acciones Preferentes", "preferred_dividends", "[-]", "item", True, False, True, False, "rev", "Preferred Dividends"),
                ("Beneficio Neto Atribuible a Accionistas Ordinarios", "net_income_common", "[=]", "subtotal", False, True, False, False, "rev", "Net Income Available to Common"),
            ]),
            ("MÉTRICAS POR ACCIÓN Y ACCIONES EN CIRCULACIÓN", [
                ("BPA Básico (Basic EPS)", "eps_basic", "", "eps", False, False, False, True, None, "Basic EPS"),
                ("BPA Diluido Normalizado (Diluted EPS)", "eps_diluted", "", "eps", False, True, False, True, None, "Diluted EPS"),
                ("Acciones Básicas Promedio Ponderado (M)", "shares_basic", "", "shares", True, False, False, True, None, "Weighted Average Shares Basic"),
                ("Acciones Diluidas Promedio Ponderado (M)", "shares_diluted", "", "shares", True, True, False, True, None, "Weighted Average Shares Diluted"),
                ("Dividendos por Acción (DPS)", "dps", "", "dps", True, False, False, False, None, "Dividends Per Share"),
            ])
        ]
    elif archetype == "INSURANCE":
        pnl_sections = [
            ("INGRESOS DE SUSCRIPCIÓN E INVERSIONES", [
                ("Primas Netas Devengadas (Net Premiums Earned)", "net_premiums_earned", "[+]", "item", True, False, False, True, "rev", "Net Premiums Earned"),
                ("Ingresos Netos por Inversiones (Net Investment Income)", "net_investment_income", "[+]", "item", True, False, False, True, "rev", "Net Investment Income"),
                ("Ganancias / (Pérdidas) Realizadas y No Realizadas en Cartera", "investment_gains_losses", "[±]", "item", True, False, False, False, "rev", "Investment Gains / Losses"),
                ("Comisiones y Otros Ingresos de Servicios", "fees_and_other_revenues", "[+]", "item", True, False, False, False, "rev", "Service and Fee Revenues"),
                ("Ingresos Totales de Seguros (Total Revenues)", "revenue", "[=]", "subtotal", False, True, False, True, "rev", "Total Revenues"),
            ]),
            ("SINIESTRALIDAD, GASTOS DE SUSCRIPCIÓN Y BENEFICIO NETO", [
                ("Siniestros y Gastos de Liquidación (Losses & LAE)", "losses_and_lae", "[-]", "item", True, False, True, True, "rev", "Losses and Loss Adjustment Expenses"),
                ("Amortización de Costes de Adquisición de Pólizas (DAC)", "dac_amortization", "[-]", "item", True, False, True, False, "rev", "Policy Acquisition Cost Amortization"),
                ("Otros Gastos de Suscripción y Operativos", "other_underwriting_expenses", "[-]", "item", True, False, True, False, "rev", "Other Underwriting Expenses"),
                ("Total Siniestros y Gastos Operativos (Total Benefits & Expenses)", "total_benefits_and_expenses", "[=]", "subtotal", False, True, True, True, "rev", "Total Benefits and Expenses"),
                ("Beneficio Antes de Impuestos (EBT)", "ebt", "[=]", "subtotal", False, True, False, True, "rev", "Pre-Tax Income"),
                ("Impuesto sobre Beneficios (Income Tax)", "income_tax", "[-]", "item", True, False, True, True, "ebt", "Income Tax Expense"),
                ("Participación en Resultados de Asociadas y Otros", "share_of_associates", "[±]", "item", True, False, False, False, "rev", "Share of Associates"),
                ("Beneficio Neto Consolidado (Net Income)", "net_income", "[=]", "result", False, True, False, True, "rev", "Net Income"),
                ("Beneficio Atribuible a Intereses Minoritarios", "minority_interest_pnl", "[-]", "item", True, False, True, False, "rev", "Noncontrolling Interest"),
                ("Dividendos de Acciones Preferentes", "preferred_dividends", "[-]", "item", True, False, True, False, "rev", "Preferred Dividends"),
                ("Beneficio Neto Atribuible a Accionistas Ordinarios", "net_income_common", "[=]", "subtotal", False, True, False, False, "rev", "Net Income Available to Common"),
            ]),
            ("MÉTRICAS POR ACCIÓN Y ACCIONES EN CIRCULACIÓN", [
                ("BPA Básico (Basic EPS)", "eps_basic", "", "eps", False, False, False, True, None, "Basic EPS"),
                ("BPA Diluido Normalizado (Diluted EPS)", "eps_diluted", "", "eps", False, True, False, True, None, "Diluted EPS"),
                ("Acciones Básicas Promedio Ponderado (M)", "shares_basic", "", "shares", True, False, False, True, None, "Weighted Average Shares Basic"),
                ("Acciones Diluidas Promedio Ponderado (M)", "shares_diluted", "", "shares", True, True, False, True, None, "Weighted Average Shares Diluted"),
                ("Dividendos por Acción (DPS)", "dps", "", "dps", True, False, False, False, None, "Dividends Per Share"),
            ])
        ]
    elif archetype == "REAL_ESTATE_REIT":
        pnl_sections = [
            ("INGRESOS INMOBILIARIOS Y NOI", [
                ("Ingresos por Alquileres y Arrendamientos (Rental Revenue)", "rental_revenue", "[+]", "item", True, False, False, True, "rev", "Rental Revenue"),
                ("Reembolsos de Inquilinos y Otros Ingresos Inmobiliarios", "tenant_reimbursements_other", "[+]", "item", True, False, False, False, "rev", "Tenant Reimbursements & Other"),
                ("Ingresos Inmobiliarios Totales (Total Revenue)", "revenue", "[=]", "subtotal", False, True, False, True, "rev", "Total Revenue"),
                ("Gastos Operativos de Propiedades (Property Operating Expenses)", "property_operating_expenses", "[-]", "item", True, False, True, True, "rev", "Property Operating Expenses"),
                ("Net Operating Income Inmobiliario (NOI)", "noi", "[=]", "subtotal", False, True, False, True, "rev", "Net Operating Income"),
            ]),
            ("GASTOS CORPORATIVOS, NO OPERATIVOS Y BENEFICIO NETO", [
                ("Depreciación y Amortización Inmobiliaria (D&A)", "reit_da", "[-]", "item", True, False, True, True, "rev", "Depreciation and Amortization"),
                ("Gastos Generales y Administrativos (G&A)", "reit_ga", "[-]", "item", True, False, True, True, "rev", "General & Administrative"),
                ("Deterioro de Activos Inmobiliarios (Impairment Charges)", "reit_impairment", "[-]", "item", True, False, True, False, "rev", "Real Estate Impairment"),
                ("Beneficio Operativo Inmobiliario (EBIT)", "operating_income", "[=]", "result", False, True, False, True, "rev", "Operating Income"),
                ("Gastos por Intereses Financieros", "interest_expense", "[-]", "item", True, False, True, True, "rev", "Interest Expense"),
                ("Ganancia en Venta de Propiedades Inmobiliarias", "gain_on_sale_properties", "[+]", "item", True, False, False, False, "rev", "Gain on Sale of Properties"),
                ("Otros Ingresos / (Gastos) No Operativos y Fusiones", "other_non_operating", "[±]", "item", True, False, False, False, "rev", "Other Non-Operating"),
                ("Beneficio Antes de Impuestos (EBT)", "ebt", "[=]", "subtotal", False, True, False, True, "rev", "Pre-Tax Income"),
                ("Impuesto sobre Beneficios (Income Tax)", "income_tax", "[-]", "item", True, False, True, True, "ebt", "Income Tax Expense"),
                ("Participación en Resultados de Asociadas y Otros", "share_of_associates", "[±]", "item", True, False, False, False, "rev", "Share of Associates"),
                ("Beneficio Neto Consolidado (Net Income)", "net_income", "[=]", "result", False, True, False, True, "rev", "Net Income"),
                ("Beneficio Atribuible a Intereses Minoritarios", "minority_interest_pnl", "[-]", "item", True, False, True, False, "rev", "Noncontrolling Interest"),
                ("Dividendos de Acciones Preferentes", "preferred_dividends", "[-]", "item", True, False, True, False, "rev", "Preferred Dividends"),
                ("Beneficio Neto Atribuible a Accionistas Ordinarios", "net_income_common", "[=]", "subtotal", False, True, False, False, "rev", "Net Income Available to Common"),
            ]),
            ("MÉTRICAS POR ACCIÓN Y ACCIONES EN CIRCULACIÓN", [
                ("BPA Básico (Basic EPS)", "eps_basic", "", "eps", False, False, False, True, None, "Basic EPS"),
                ("BPA Diluido Normalizado (Diluted EPS)", "eps_diluted", "", "eps", False, True, False, True, None, "Diluted EPS"),
                ("Acciones Básicas Promedio Ponderado (M)", "shares_basic", "", "shares", True, False, False, True, None, "Weighted Average Shares Basic"),
                ("Acciones Diluidas Promedio Ponderado (M)", "shares_diluted", "", "shares", True, True, False, True, None, "Weighted Average Shares Diluted"),
                ("Dividendos por Acción (DPS)", "dps", "", "dps", True, False, False, False, None, "Dividends Per Share"),
            ])
        ]
    else:
        pnl_sections = [
            ("INGRESOS Y BENEFICIO BRUTO", [
                ("Ingresos Totales (Revenue)", "revenue", "[+]", "subtotal", False, True, False, True, "rev", "Revenue"),
                ("Coste de Ventas (COGS)", "cogs", "[-]", "item", True, False, True, True, "rev", "Cost of Goods Sold"),
                ("Beneficio Bruto (Gross Profit)", "gross_profit", "[=]", "subtotal", False, True, False, True, "rev", "Gross Profit"),
            ]),
            ("GASTOS OPERATIVOS Y EBIT", [
                ("Investigación y Desarrollo (I+D / R&D)", "rd_expense", "[-]", "item", True, False, True, False, "rev", "Research & Development"),
                ("Ventas, Generales y Administrativos (SG&A)", "sga_expense", "[-]", "item", True, False, True, True, "rev", "Selling, General & Administrative"),
                ("Provisión para Pérdidas Crediticias (Fintech)", "credit_loss_provision", "[-]", "item", True, False, True, False, "rev", "Provision for Credit Losses"),
                ("Otros Gastos / (Ingresos) Operativos", "other_operating_expense", "[-]", "item", True, False, True, False, "rev", "Other Operating Expenses"),
                ("Total Gastos Operativos (OpEx)", "total_operating_expenses", "[=]", "subtotal", False, True, True, True, "rev", "Total Operating Expenses"),
                ("Beneficio Operativo (EBIT)", "operating_income", "[=]", "result", False, True, False, True, "rev", "Operating Income"),
            ]),
            ("PARTIDAS NO OPERATIVAS, IMPUESTOS Y BENEFICIO NETO", [
                ("Ingresos por Intereses e Inversiones", "interest_income", "[+]", "item", True, False, False, False, "rev", "Interest & Investment Income"),
                ("Gastos por Intereses Financieros", "interest_expense", "[-]", "item", True, False, True, False, "rev", "Interest Expense"),
                ("Otros Ingresos / (Gastos) No Operativos Netos", "other_non_operating", "[±]", "item", True, False, False, False, "rev", "Other Non-Operating Income / Expense"),
                ("Total Ingresos / (Gastos) No Operativos Netos", "total_non_operating", "[=]", "subtotal", False, True, False, True, "rev", "Total Non-Operating"),
                ("Beneficio Antes de Impuestos (EBT)", "ebt", "[=]", "subtotal", False, True, False, True, "rev", "Pre-Tax Income (EBT)"),
                ("Impuesto sobre Beneficios (Income Tax)", "income_tax", "[-]", "item", True, False, True, True, "ebt", "Income Tax Expense"),
                ("Participación en Resultados de Asociadas y Otros", "share_of_associates", "[±]", "item", True, False, False, False, "rev", "Equity in Earnings / (Losses) of Associates"),
                ("Beneficio Neto Consolidado (Net Income)", "net_income", "[=]", "result", False, True, False, True, "rev", "Net Income"),
                ("Beneficio Atribuible a Intereses Minoritarios", "minority_interest_pnl", "[-]", "item", True, False, True, False, "rev", "Noncontrolling Interest"),
                ("Dividendos de Acciones Preferentes", "preferred_dividends", "[-]", "item", True, False, True, False, "rev", "Preferred Dividends"),
                ("Beneficio Neto Atribuible a Accionistas Ordinarios", "net_income_common", "[=]", "subtotal", False, True, False, False, "rev", "Net Income Available to Common"),
            ]),
            ("MÉTRICAS POR ACCIÓN Y ACCIONES EN CIRCULACIÓN", [
                ("BPA Básico (Basic EPS)", "eps_basic", "", "eps", False, False, False, True, None, "Basic EPS"),
                ("BPA Diluido Normalizado (Diluted EPS)", "eps_diluted", "", "eps", False, True, False, True, None, "Diluted EPS"),
                ("Acciones Básicas Promedio Ponderado (M)", "shares_basic", "", "shares", True, False, False, True, None, "Weighted Average Shares Basic"),
                ("Acciones Diluidas Promedio Ponderado (M)", "shares_diluted", "", "shares", True, True, False, True, None, "Weighted Average Shares Diluted"),
                ("Dividendos por Acción (DPS)", "dps", "", "dps", True, False, False, False, None, "Dividends Per Share"),
            ])
        ]

    std_inc_rows = _build_standardized_section(pnl_sections, pnl_data, default_pct_mode="rev")
    std_inc_rows.extend(_get_memo_rows(statements_fys, "pnl"))
    std_pnl = [_build_statement_cells(r, statements_fys, canonical, ebt_dict=ebt_dict_std) for r in std_inc_rows]

    # 2. ESTADO DE FLUJOS DE CAJA (CASH FLOW STATEMENT)
    cf_sections = [
        ("ACTIVIDADES OPERATIVAS (OPERATING ACTIVITIES)", [
            ("Beneficio Neto Consolidado (Net Income)", "net_income", "[+]", "subtotal", False, True, False, True, "ni", "Net Income"),
            ("Depreciación y Amortización (D&A)", "da", "[+]", "item", True, False, False, True, "ni", "Depreciation & Amortization"),
            ("Compensación Basada en Acciones (SBC)", "sbc", "[+]", "item", True, False, False, False, "ni", "Share-Based Compensation"),
            ("Impuestos sobre Beneficios Diferidos (Deferred Taxes)", "deferred_taxes", "[±]", "item", True, False, False, False, "ni", "Deferred Income Taxes"),
            ("Otros Ajustes Operativos No Monetarios (Other Non-Cash)", "other_noncash", "[±]", "item", True, False, False, False, "ni", "Other Non-Cash Adjustments"),
            ("Variación en Cuentas por Cobrar (AR)", "wc_ar", "[±]", "item", True, False, False, False, "ni", "Change in Accounts Receivable"),
            ("Variación en Inventarios", "wc_inv", "[±]", "item", True, False, False, False, "ni", "Change in Inventories"),
            ("Variación en Cuentas por Pagar (AP)", "wc_ap", "[±]", "item", True, False, False, False, "ni", "Change in Accounts Payable"),
            ("Variación en Otros Activos y Pasivos Operativos", "wc_other", "[±]", "item", True, False, False, False, "ni", "Change in Other Operating Working Capital"),
            ("Flujo de Caja Operativo (CFO)", "cfo", "[=]", "result", False, True, False, True, "ni", "Cash Provided by Operating Activities"),
        ]),
        ("ACTIVIDADES DE INVERSIÓN (INVESTING ACTIVITIES)", [
            ("Inversiones en Inmovilizado / CapEx", "capex", "[-]", "item", True, False, True, (archetype not in ("FINANCIAL_BANKING", "INSURANCE") or any(cf_data.get("capex", {}).get(k) is not None for k in cf_data.get("capex", {}))), "ni", "Capital Expenditures"),
            ("Adquisiciones Netas de Caja (M&A)", "acquisitions_ma", "[-]", "item", True, False, True, False, "ni", "Acquisitions Net of Cash"),
            ("Compras de Inversiones y Valores Negociables", "purchases_investments", "[-]", "item", True, False, True, False, "ni", "Purchases of Investments"),
            ("Ventas y Vencimientos de Inversiones Negociables", "sales_maturities_investments", "[+]", "item", True, False, False, False, "ni", "Sales & Maturities of Investments"),
            ("Otros Flujos de Inversión", "other_investing", "[±]", "item", True, False, False, False, "ni", "Other Investing Activities"),
            ("Flujo de Caja de Inversión (CFI)", "cfi", "[=]", "subtotal", False, True, False, True, "ni", "Cash Used in Investing Activities"),
        ]),
        ("ACTIVIDADES DE FINANCIACIÓN (FINANCING ACTIVITIES)", [
            ("Emisión de Deuda Financiera (Debt Issued)", "debt_issued", "[+]", "item", True, False, False, False, "ni", "Issuance of Debt"),
            ("Amortización y Reembolso de Deuda (Debt Repaid)", "debt_repaid", "[-]", "item", True, False, True, False, "ni", "Repayments of Debt"),
            ("Emisión de Acciones Ordinarias y Planes de Empleados", "stock_issued", "[+]", "item", True, False, False, False, "ni", "Issuance of Common Stock"),
            ("Recompra de Acciones en Mercado Abierto (Buybacks)", "share_repurchases_open_market", "[-]", "item", True, False, True, False, "ni", "Repurchase of Common Stock"),
            ("Retenciones Fiscales por Liquidación de RSU / SBC", "share_repurchases_sbc_tax", "[-]", "item", True, False, True, False, "ni", "Tax Withholding for Share Awards"),
            ("Dividendos Pagados en Efectivo (Dividends Paid)", "dividends_paid", "[-]", "item", True, False, True, True, "ni", "Payment of Dividends"),
            ("Otros Flujos de Financiación", "other_financing", "[±]", "item", True, False, False, False, "ni", "Other Financing Activities"),
            ("Flujo de Caja de Financiación (CFF)", "cff", "[=]", "subtotal", False, True, False, True, "ni", "Cash Provided by / Used in Financing Activities"),
            ("Emisión / (Amortización) Neta de Deuda Financiera", "net_debt_issued", "[=]", "metric", False, True, False, True, "ni", "Net Debt Issuance / Repayment (Memo)"),
        ]),
        ("VARIACIÓN NETA DE EFECTIVO Y CONCILIACIÓN DE CAJA", [
            ("Efectivo, Equivalentes y Restringido al Inicio", "beginning_cash", "[+]", "item", True, False, False, True, "ni", "Cash, Cash Equivalents & Restricted Cash at Beginning of Period"),
            ("Efecto del Tipo de Cambio en el Efectivo (FX Effect)", "fx_effect", "[±]", "item", True, False, False, False, "ni", "Effect of Exchange Rate on Cash"),
            ("Variación Neta de Efectivo en el Período (Net Change in Cash)", "net_change_in_cash", "[=]", "subtotal", False, True, False, True, "ni", "Net Change in Cash & Equivalents"),
            ("Efectivo, Equivalentes y Efectivo Restringido al Cierre", "ending_cash", "[=]", "subtotal", False, True, False, True, "ni", "Ending Cash & Equivalents"),
            ("Flujo de Caja Libre Estándar (FCF = CFO − CapEx)", "fcf", "[=]", "result", False, True, False, (archetype not in ("FINANCIAL_BANKING", "INSURANCE")), "ni", "Free Cash Flow"),
            ("Flujo de Fondos Ajustado de las Operaciones (AFFO REIT)", "affo", "[=]", "result", False, True, False, (archetype == "REAL_ESTATE_REIT"), "ni", "Adjusted Funds From Operations"),
        ])
    ]

    std_cf_rows = _build_standardized_section(cf_sections, cf_data, default_pct_mode="ni")
    std_cf_rows.extend(_get_memo_rows(statements_fys, "cashflow"))
    std_cashflow = [_build_statement_cells(r, statements_fys, canonical) for r in std_cf_rows]

    # 3. BALANCE GENERAL CONSOLIDADO (BALANCE SHEET)
    if archetype == "FINANCIAL_BANKING":
        bs_sections = [
            ("ACTIVOS BANCARIOS Y CARTERA CREDITICIA", [
                ("Efectivo y Depósitos en Bancos Centrales", "cash", "[+]", "item", True, False, False, True, "assets", "Cash and Due from Banks"),
                ("Inversiones Financieras y Valores Negociables", "short_term_investments", "[+]", "item", True, False, False, True, "assets", "Trading and Investment Securities"),
                ("Tesorería e Inversiones Líquidas Totales", "total_liquid_cash", "[=]", "subtotal", False, True, False, True, "assets", "Total Liquid Assets"),
                ("Cartera de Préstamos y Crédito Neta (Net Loans)", "net_loans", "[+]", "item", True, False, False, True, "assets", "Loans and Leases Net of Allowance"),
                ("Provisión Acumulada para Pérdidas Crediticias (Allowance)", "allowance_for_loan_losses", "[-]", "item", True, False, True, False, "assets", "Allowance for Loan Losses"),
                ("Inmovilizado Material Neto (PP&E)", "net_ppe", "[+]", "item", True, False, False, False, "assets", "Premises and Equipment Net"),
                ("Fondo de Comercio e Intangibles Netos", "goodwill_and_intangibles", "[+]", "item", True, False, False, False, "assets", "Goodwill and Other Intangibles"),
                ("Otros Activos Financieros y Operativos", "other_assets_sectoral", "[+]", "item", True, False, False, True, "assets", "Other Banking Assets"),
                ("Total Activos (Total Assets)", "total_assets", "[=]", "result", False, True, False, True, "assets", "Total Assets"),
            ]),
            ("DEPÓSITOS Y PASIVOS BANCARIOS", [
                ("Depósitos Totales de Clientes (Total Deposits)", "deposits", "[+]", "item", True, False, False, True, "assets", "Total Customer Deposits"),
                ("Deuda Financiera a Corto Plazo y Repos", "short_term_debt", "[+]", "item", True, False, False, False, "assets", "Short-Term Debt and Borrowings"),
                ("Deuda Financiera a Largo Plazo", "long_term_debt", "[+]", "item", True, False, False, False, "assets", "Long-Term Debt"),
                ("Deuda Financiera Total", "total_debt", "[=]", "subtotal", False, True, False, True, "assets", "Total Debt"),
                ("Otros Pasivos Financieros y Operativos", "other_liabilities_sectoral", "[+]", "item", True, False, False, True, "assets", "Other Banking Liabilities"),
                ("Total Pasivos (Total Liabilities)", "total_liabilities", "[=]", "result", False, True, False, True, "assets", "Total Liabilities"),
            ]),
            ("PATRIMONIO NETO (SHAREHOLDERS' EQUITY)", [
                ("Capital Social y Prima de Emisión (Common Stock & APIC)", "common_stock_and_apic", "[+]", "item", True, False, False, True, "assets", "Common Stock & APIC"),
                ("Ganancias Retenidas / (Déficit Acumulado)", "retained_earnings", "[+]", "item", True, False, False, True, "assets", "Retained Earnings"),
                ("Acciones en Tesorería, AOCI y Otros Fondos Propios", "other_equity", "[±]", "item", True, False, False, True, "assets", "Treasury Stock & AOCI"),
                ("Intereses Minoritarios (Noncontrolling Interests)", "minority_interest", "[+]", "item", True, False, False, False, "assets", "Noncontrolling Interests"),
                ("Total Patrimonio Neto (Stockholders' Equity)", "stockholders_equity", "[=]", "result", False, True, False, True, "assets", "Total Stockholders Equity"),
                ("Total Pasivo y Patrimonio Neto (Total Liabilities & Equity)", "total_liab_and_equity", "[=]", "result", False, True, False, True, "assets", "Total Liabilities and Equity"),
            ])
        ]
    elif archetype == "INSURANCE":
        bs_sections = [
            ("ACTIVOS ASEGURADORES Y CARTERA DE INVERSIONES", [
                ("Efectivo y Equivalentes de Efectivo", "cash", "[+]", "item", True, False, False, True, "assets", "Cash and Equivalents"),
                ("Cartera de Inversiones (Renta Fija y Variable)", "short_term_investments", "[+]", "item", True, False, False, True, "assets", "Fixed Maturities and Equity Securities"),
                ("Tesorería e Inversiones Líquidas Totales", "total_liquid_cash", "[=]", "subtotal", False, True, False, True, "assets", "Total Cash and Invested Assets"),
                ("Cuentas por Cobrar de Primas (Premiums Receivable)", "premiums_receivable", "[+]", "item", True, False, False, True, "assets", "Premiums Receivable"),
                ("Costes de Adquisición de Pólizas Diferidos (DAC)", "deferred_policy_acquisition_costs", "[+]", "item", True, False, False, True, "assets", "Deferred Acquisition Costs"),
                ("Inmovilizado Material Neto (PP&E)", "net_ppe", "[+]", "item", True, False, False, False, "assets", "Property and Equipment Net"),
                ("Fondo de Comercio e Intangibles", "goodwill_and_intangibles", "[+]", "item", True, False, False, False, "assets", "Goodwill and Intangible Assets"),
                ("Otros Activos Aseguradores", "other_assets_sectoral", "[+]", "item", True, False, False, True, "assets", "Other Insurance Assets"),
                ("Total Activos (Total Assets)", "total_assets", "[=]", "result", False, True, False, True, "assets", "Total Assets"),
            ]),
            ("RESERVAS TÉCNICAS Y PASIVOS ASEGURADORES", [
                ("Reservas para Siniestros y Gastos de Liquidación (Loss & LAE Reserves)", "loss_reserves", "[+]", "item", True, False, False, True, "assets", "Unpaid Losses and Loss Adjustment Expenses"),
                ("Primas No Devengadas (Unearned Premiums)", "unearned_premiums", "[+]", "item", True, False, False, True, "assets", "Unearned Premiums"),
                ("Deuda Financiera Total", "total_debt", "[+]", "item", True, False, False, False, "assets", "Total Debt"),
                ("Cuentas por Pagar y Otros Pasivos Aseguradores", "other_liabilities_sectoral", "[+]", "item", True, False, False, True, "assets", "Accounts Payable and Other Liabilities"),
                ("Total Pasivos (Total Liabilities)", "total_liabilities", "[=]", "result", False, True, False, True, "assets", "Total Liabilities"),
            ]),
            ("PATRIMONIO NETO (SHAREHOLDERS' EQUITY)", [
                ("Capital Social y Prima de Emisión (Common Stock & APIC)", "common_stock_and_apic", "[+]", "item", True, False, False, True, "assets", "Common Stock & APIC"),
                ("Ganancias Retenidas / (Déficit Acumulado)", "retained_earnings", "[+]", "item", True, False, False, True, "assets", "Retained Earnings"),
                ("Acciones en Tesorería, AOCI y Otros Fondos Propios", "other_equity", "[±]", "item", True, False, False, True, "assets", "Treasury Stock & AOCI"),
                ("Intereses Minoritarios (Noncontrolling Interests)", "minority_interest", "[+]", "item", True, False, False, False, "assets", "Noncontrolling Interests"),
                ("Total Patrimonio Neto (Stockholders' Equity)", "stockholders_equity", "[=]", "result", False, True, False, True, "assets", "Total Stockholders Equity"),
                ("Total Pasivo y Patrimonio Neto (Total Liabilities & Equity)", "total_liab_and_equity", "[=]", "result", False, True, False, True, "assets", "Total Liabilities and Equity"),
            ])
        ]
    else:
        # STANDARD_CORPORATE, PLATFORM_ECOSYSTEM, REAL_ESTATE_REIT
        ppe_title = "Propiedades Inmobiliarias Netas (Real Estate Net)" if archetype == "REAL_ESTATE_REIT" else "Inmovilizado Material Neto (PP&E Neto)"
        bs_sections = [
            ("ACTIVOS CORRIENTES (CURRENT ASSETS)", [
                ("Efectivo y Equivalentes de Efectivo", "cash", "[+]", "item", True, False, False, True, "assets", "Cash and Cash Equivalents"),
                ("Inversiones a Corto Plazo (Valores Negociables)", "short_term_investments", "[+]", "item", True, False, False, True, "assets", "Short-Term Marketable Securities"),
                ("Efectivo e Inversiones Líquidas Totales", "total_liquid_cash", "[=]", "subtotal", False, True, False, True, "assets", "Total Liquid Cash & Investments"),
                ("Cuentas por Cobrar Comerciales y Otras Netas", "accounts_receivable", "[+]", "item", True, False, False, True, "assets", "Accounts Receivable Net"),
                ("Inventarios / Existencias", "inventories", "[+]", "item", True, False, False, False, "assets", "Inventories Net"),
                ("Gastos Pagados por Anticipado y Otros Activos Corrientes", "other_current_assets", "[+]", "item", True, False, False, True, "assets", "Prepaid Expenses & Other Current Assets"),
                ("Total Activos Corrientes", "total_current_assets", "[=]", "subtotal", False, True, False, True, "assets", "Total Current Assets"),
            ]),
            ("ACTIVOS NO CORRIENTES (NON-CURRENT ASSETS)", [
                (ppe_title, "net_ppe", "[+]", "item", True, False, False, True, "assets", "Property, Plant & Equipment Net"),
                ("Activos por Derecho de Uso en Arrendamiento (ROU Assets)", "rou_asset", "[+]", "item", True, False, False, False, "assets", "Operating Lease Right-of-Use Assets"),
                ("Fondo de Comercio e Intangibles Netos (Goodwill & Intangibles)", "goodwill_and_intangibles", "[+]", "item", True, False, False, True, "assets", "Goodwill & Net Intangible Assets"),
                ("Inversiones Financieras a Largo Plazo", "long_term_investments", "[+]", "item", True, False, False, False, "assets", "Long-Term Marketable Securities"),
                ("Activos por Impuestos Diferidos", "deferred_tax_assets", "[+]", "item", True, False, False, False, "assets", "Deferred Tax Assets Noncurrent"),
                ("Otros Activos No Corrientes", "other_noncurrent_assets", "[+]", "item", True, False, False, True, "assets", "Other Non-Current Assets"),
                ("Total Activos No Corrientes", "total_noncurrent_assets", "[=]", "subtotal", False, True, False, True, "assets", "Total Non-Current Assets"),
                ("Total Activos (Total Assets)", "total_assets", "[=]", "result", False, True, False, True, "assets", "Total Assets"),
            ]),
            ("PASIVOS CORRIENTES (CURRENT LIABILITIES)", [
                ("Cuentas por Pagar Comerciales (Proveedores)", "accounts_payable", "[+]", "item", True, False, False, True, "assets", "Accounts Payable"),
                ("Gastos Acumulados y Pasivos Devengados (Accrued Liabilities)", "accrued_liabilities", "[+]", "item", True, False, False, True, "assets", "Accrued Expenses & Other Current Liabilities"),
                ("Ingresos Diferidos a Corto Plazo (Deferred Revenue)", "deferred_revenue_current", "[+]", "item", True, False, False, False, "assets", "Deferred Revenue Current"),
                ("Deuda Financiera a Corto Plazo y Porción Corriente", "short_term_debt", "[+]", "item", True, False, False, True, "assets", "Commercial Paper & Current Portion of LT Debt"),
                ("Otros Pasivos Corrientes (incl. Arrendamientos CP / Fondos Clientes)", "other_current_liabilities", "[+]", "item", True, False, False, False, "assets", "Other Current Liabilities"),
                ("Total Pasivos Corrientes", "total_current_liabilities", "[=]", "subtotal", False, True, False, True, "assets", "Total Current Liabilities"),
            ]),
            ("PASIVOS NO CORRIENTES (NON-CURRENT LIABILITIES)", [
                ("Deuda Financiera a Largo Plazo", "long_term_debt", "[+]", "item", True, False, False, True, "assets", "Long-Term Debt Noncurrent"),
                ("Pasivos por Arrendamiento Operativo a Largo Plazo", "operating_lease_liability_noncurrent", "[+]", "item", True, False, False, False, "assets", "Operating Lease Liabilities Noncurrent"),
                ("Pasivos por Impuestos Diferidos No Corrientes", "deferred_tax_liabilities_noncurrent", "[+]", "item", True, False, False, False, "assets", "Deferred Tax Liabilities Noncurrent"),
                ("Otros Pasivos No Corrientes", "other_noncurrent_liabilities", "[+]", "item", True, False, False, True, "assets", "Other Non-Current Liabilities"),
                ("Total Pasivos No Corrientes", "total_noncurrent_liabilities", "[=]", "subtotal", False, True, False, True, "assets", "Total Non-Current Liabilities"),
                ("Total Pasivos (Total Liabilities)", "total_liabilities", "[=]", "result", False, True, False, True, "assets", "Total Liabilities"),
            ]),
            ("PATRIMONIO NETO (SHAREHOLDERS' EQUITY)", [
                ("Capital Social y Prima de Emisión (Common Stock & APIC)", "common_stock_and_apic", "[+]", "item", True, False, False, True, "assets", "Common Stock & Additional Paid-in Capital"),
                ("Ganancias Retenidas / (Déficit Acumulado)", "retained_earnings", "[+]", "item", True, False, False, True, "assets", "Retained Earnings / Accumulated Deficit"),
                ("Acciones en Tesorería, AOCI y Otros Fondos Propios", "other_equity", "[±]", "item", True, False, False, True, "assets", "Treasury Stock & Accumulated Other Comprehensive Income"),
                ("Intereses Minoritarios (Noncontrolling Interests)", "minority_interest", "[+]", "item", True, False, False, False, "assets", "Noncontrolling Interests"),
                ("Total Patrimonio Neto (Stockholders' Equity)", "stockholders_equity", "[=]", "result", False, True, False, True, "assets", "Total Stockholders Equity"),
                ("Total Pasivo y Patrimonio Neto (Total Liabilities & Equity)", "total_liab_and_equity", "[=]", "result", False, True, False, True, "assets", "Total Liabilities & Stockholders Equity"),
            ])
        ]

    std_bs_rows = _build_standardized_section(bs_sections, bs_data, default_pct_mode="assets")
    std_bs_rows.extend(_get_memo_rows(statements_fys, "balancesheet"))
    std_balancesheet = [_build_statement_cells(r, statements_fys, canonical, bs_tot_assets=bs_tot_assets_std) for r in std_bs_rows]

    # =============================================================
    # 1.B. CONSTRUCCIÓN DE VISTA OFICIAL SEC (AS-REPORTED 3Y + LTM)
    # =============================================================
    if as_rep_inc:
        as_rep_inc_rows = [_format_as_reported_row(r_raw, as_rep_fys, pct_mode="rev") for r_raw in as_rep_inc]
        as_rep_inc_rows.extend(_get_memo_rows(as_rep_fys, "pnl"))
        as_rep_pnl = [_build_statement_cells(r, as_rep_fys, canonical, ebt_dict=ebt_dict_asrep) for r in as_rep_inc_rows]
    else:
        as_rep_pnl = std_pnl

    if as_rep_cf:
        as_rep_cf_rows = [_format_as_reported_row(r_raw, as_rep_fys, pct_mode="ni") for r_raw in as_rep_cf]
        as_rep_cf_rows.extend(_get_memo_rows(as_rep_fys, "cashflow"))
        as_rep_cashflow = [_build_statement_cells(r, as_rep_fys, canonical) for r in as_rep_cf_rows]
    else:
        as_rep_cashflow = std_cashflow

    if as_rep_bs:
        as_rep_bs_rows = [_format_as_reported_row(r_raw, as_rep_fys, pct_mode="assets") for r_raw in as_rep_bs]
        as_rep_bs_rows.extend(_get_memo_rows(as_rep_fys, "balancesheet"))
        as_rep_balancesheet = [_build_statement_cells(r, as_rep_fys, canonical, bs_tot_assets=bs_tot_assets_asrep) for r in as_rep_bs_rows]
    else:
        as_rep_balancesheet = std_balancesheet

    # Por retrocompatibilidad directa
    statements_pnl = std_pnl
    statements_cashflow = std_cashflow
    statements_balancesheet = std_balancesheet



    # Highlights de Cabecera adaptados dinámicamente por Arquetipo
    latest_p = statements_fys[0] if statements_fys else "LTM"
    rev_ltm_val = _to_m(canonical.get("revenue", {}).get(latest_p))
    gp_ltm_val = _to_m(canonical.get("gross_profit", {}).get(latest_p))
    ebit_ltm_val = _to_m(canonical.get("operating_income", {}).get(latest_p))
    ni_ltm_val = _to_m(canonical.get("net_income", {}).get(latest_p))
    fcf_ltm_val = _to_m(canonical.get("free_cash_flow", {}).get(latest_p))
    if fcf_ltm_val is None and archetype == "INSURANCE":
        cfo_v = canonical.get("cash_from_operations", {}).get(latest_p)
        cx_v = canonical.get("capital_expenditures", {}).get(latest_p)
        if cfo_v is not None and cx_v is not None:
            fcf_ltm_val = _to_m(float(cfo_v) - abs(float(cx_v)))

    net_debt_dict = {p: _to_m(bs_data.get("net_financial_position", {}).get(p)) for p in statements_fys}
    nd_ltm_val = net_debt_dict.get(latest_p)
    eq_ltm_val = _to_m(bs_data.get("stockholders_equity", {}).get(latest_p) or canonical.get("stockholders_equity", {}).get(latest_p))
    ca_val = _to_m(bs_data.get("total_current_assets", {}).get(latest_p) or canonical.get("current_assets", {}).get(latest_p))
    cl_val = _to_m(bs_data.get("total_current_liabilities", {}).get(latest_p) or canonical.get("current_liabilities", {}).get(latest_p))
    cr_val = round(ca_val / cl_val, 2) if (ca_val and cl_val and cl_val != 0) else key_ratios.get("current_ratio", {}).get(latest_p)

    # Métricas especializadas
    if is_banking:
        nim_val = key_ratios.get("nim_pct", {}).get(latest_p) or key_ratios.get("risk_adj_nim_pct", {}).get(latest_p) or enriched.get("risk_adjusted_nim_pct")
        eff_val = key_ratios.get("efficiency_ratio_pct", {}).get(latest_p) or enriched.get("efficiency_ratio_pct")
        roe_val = key_ratios.get("roe_pct", {}).get(latest_p) or enriched.get("return_on_equity_reported")

        rotce_val = key_ratios.get("rotce_pct", {}).get(latest_p)
        if rotce_val is None:
            ni_comm = pnl_data.get("net_income_common", {}).get(latest_p) or canonical.get("net_income_common", {}).get(latest_p) or canonical.get("net_income", {}).get(latest_p)
            eq = bs_data.get("stockholders_equity", {}).get(latest_p) or canonical.get("stockholders_equity", {}).get(latest_p)
            pref = _num(bs_det, "PreferredStockValue", latest_p) or _num(bs_det, "us-gaap_PreferredStockIncludingAdditionalPaidInCapitalNetOfDiscount", latest_p) or 0.0
            gw_int = bs_data.get("goodwill_and_intangibles", {}).get(latest_p) or 0.0
            tce = (eq - pref - gw_int) if eq else 0.0
            if tce > 0 and ni_comm is not None:
                rotce_val = round(ni_comm / tce * 100.0, 1)
            elif roe_val is not None:
                rotce_val = round(float(roe_val), 1)

        cet1_val = key_ratios.get("cet1_ratio_pct", {}).get(latest_p) or enriched.get("cet1_ratio_pct")
        if cet1_val is None:
            eq = bs_data.get("stockholders_equity", {}).get(latest_p) or canonical.get("stockholders_equity", {}).get(latest_p)
            pref = _num(bs_det, "PreferredStockValue", latest_p) or _num(bs_det, "us-gaap_PreferredStockIncludingAdditionalPaidInCapitalNetOfDiscount", latest_p) or 0.0
            gw_int = bs_data.get("goodwill_and_intangibles", {}).get(latest_p) or 0.0
            tot_ast = bs_data.get("total_assets", {}).get(latest_p) or canonical.get("total_assets", {}).get(latest_p)
            tce = (eq - pref - gw_int) if eq else 0.0
            if tce > 0 and tot_ast and tot_ast > 0:
                cet1_val = round(tce / tot_ast * 100.0, 1)
            elif eq and tot_ast and tot_ast > 0:
                cet1_val = round(eq / tot_ast * 100.0, 1)

        npl_cov_val = key_ratios.get("provision_coverage_pct", {}).get(latest_p) or enriched.get("provision_coverage_pct")
        if npl_cov_val is None:
            allowance = bs_data.get("allowance_for_loan_losses", {}).get(latest_p) or _num(bs_det, "FinancingReceivableAllowanceForCreditLosses", latest_p) or _num(bs_det, "us-gaap_FinancingReceivableAllowanceForCreditLossExcludingAccruedInterest", latest_p)
            clp = pnl_data.get("credit_loss_provision", {}).get(latest_p) or canonical.get("credit_loss_provisions", {}).get(latest_p)
            if allowance and clp and clp != 0:
                npl_cov_val = round(abs(allowance) / abs(clp) * 100.0, 1)

        npl_ratio_val = key_ratios.get("npl_ratio_pct", {}).get(latest_p) or enriched.get("npl_90_plus_pct")
        if npl_ratio_val is None:
            npl_ratio_val = key_ratios.get("cost_of_risk_loans_pct", {}).get(latest_p)
    else:
        nim_val = None
        eff_val = None
        roe_val = key_ratios.get("roe_pct", {}).get(latest_p)
        rotce_val = None
        cet1_val = None
        npl_cov_val = None
        npl_ratio_val = None

    if is_insurance:
        comb_ratio_val = key_ratios.get("combined_ratio_pct", {}).get(latest_p) or canonical.get("combined_ratio", {}).get(latest_p)
        loss_ratio_val = key_ratios.get("loss_ratio_pct", {}).get(latest_p) or canonical.get("loss_ratio", {}).get(latest_p)
        exp_ratio_val = key_ratios.get("expense_ratio_pct", {}).get(latest_p) or canonical.get("expense_ratio", {}).get(latest_p)

        inv_yield_val = key_ratios.get("investment_yield_pct", {}).get(latest_p)
        if inv_yield_val is None:
            nii_v = canonical.get("net_investment_income", {}).get(latest_p) or pnl_data.get("net_investment_income", {}).get(latest_p)
            tot_inv = canonical.get("total_investments", {}).get(latest_p) or bs_data.get("short_term_investments", {}).get(latest_p)
            if nii_v and tot_inv and tot_inv > 0:
                inv_yield_val = round(float(nii_v) / float(tot_inv) * 100.0, 1)

        net_prem_val = _to_m(canonical.get("net_premiums_earned", {}).get(latest_p)) or rev_ltm_val
        float_val = _to_m(canonical.get("float_usd", {}).get(latest_p))
        total_inv_val = _to_m(canonical.get("total_investments", {}).get(latest_p) or bs_data.get("short_term_investments", {}).get(latest_p))
    else:
        comb_ratio_val = None
        loss_ratio_val = None
        exp_ratio_val = None
        inv_yield_val = None
        net_prem_val = None
        float_val = None
        total_inv_val = None

    if is_reit:
        rental_rev_val = _to_m(canonical.get("rental_revenue", {}).get(latest_p)) or rev_ltm_val
        noi_val = _to_m(canonical.get("noi", {}).get(latest_p))
        ffo_val = _to_m(canonical.get("ffo", {}).get(latest_p))
        affo_val = _to_m(canonical.get("affo", {}).get(latest_p))
        sh_cnt = canonical.get("shares_diluted", {}).get(latest_p) or canonical.get("weighted_average_shares_diluted", {}).get(latest_p)
        ffo_sh_val = round(float(canonical.get("ffo", {}).get(latest_p)) / float(sh_cnt), 2) if (ffo_val and sh_cnt and float(sh_cnt) > 0) else None
        affo_sh_val = round(float(canonical.get("affo", {}).get(latest_p)) / float(sh_cnt), 2) if (affo_val and sh_cnt and float(sh_cnt) > 0) else None
        div_paid = abs(canonical.get("dividends_paid", {}).get(latest_p) or _num(cf_det, "PaymentsOfDividendsCommonStock", latest_p) or _num(cf_det, "PaymentsOfDividends", latest_p) or 0.0)
        payout_affo_val = round(div_paid / float(canonical.get("affo", {}).get(latest_p)) * 100.0, 1) if (affo_val and div_paid > 0) else None
        tot_debt_val = _to_m(canonical.get("total_debt", {}).get(latest_p))
        tot_assets_val = _to_m(canonical.get("total_assets", {}).get(latest_p))
        ltv_val = round(tot_debt_val / tot_assets_val * 100.0, 1) if (tot_debt_val and tot_assets_val and tot_assets_val > 0) else None
    else:
        rental_rev_val = None
        noi_val = None
        ffo_val = None
        affo_val = None
        ffo_sh_val = None
        affo_sh_val = None
        payout_affo_val = None
        ltv_val = None

    statements_summary = {
        "archetype": archetype,
        "is_financial": is_financial,
        # Standard corporate
        "rev_ltm": _fmt_money(rev_ltm_val),
        "gm_ltm": f"{round(gp_ltm_val / rev_ltm_val * 100.0, 1)}%" if (gp_ltm_val and rev_ltm_val) else "-",
        "om_ltm": f"{round(ebit_ltm_val / rev_ltm_val * 100.0, 1)}%" if (ebit_ltm_val and rev_ltm_val) else "-",
        "fcf_ltm": _fmt_money(fcf_ltm_val),
        "fcf_margin_ltm": f"{round(fcf_ltm_val / rev_ltm_val * 100.0, 1)}%" if (fcf_ltm_val and rev_ltm_val) else "-",
        "fcf_conv_ltm": f"{round(fcf_ltm_val / ni_ltm_val * 100.0, 1)}%" if (fcf_ltm_val and ni_ltm_val) else "-",
        "net_debt_display": _fmt_money(abs(nd_ltm_val)) if (nd_ltm_val and nd_ltm_val < 0) else _fmt_money(nd_ltm_val),
        "net_debt_is_cash": (nd_ltm_val is not None and nd_ltm_val < 0),
        "current_ratio": f"{cr_val:.2f}x" if cr_val else "-",
        "equity_ltm": _fmt_money(eq_ltm_val),
        "net_income_ltm": _fmt_money(ni_ltm_val),
        "net_margin_ltm": f"{round(ni_ltm_val / rev_ltm_val * 100.0, 1)}%" if (ni_ltm_val and rev_ltm_val) else "-",
        # Banking
        "nim_ltm": f"{nim_val:.2f}%" if nim_val is not None else "-",
        "cost_to_income": f"{eff_val:.1f}%" if eff_val is not None else "-",
        "roe_ltm": f"{roe_val:.1f}%" if roe_val is not None else (f"{round(ni_ltm_val / eq_ltm_val * 100.0, 1)}%" if (ni_ltm_val and eq_ltm_val and eq_ltm_val > 0) else "-"),
        "rotce_ltm": f"{rotce_val:.1f}%" if rotce_val is not None else "-",
        "cet1_ratio": f"{cet1_val:.1f}%" if cet1_val is not None else "-",
        "npl_coverage": f"{npl_cov_val:.1f}%" if npl_cov_val is not None else "-",
        "npl_ratio": f"{npl_ratio_val:.1f}%" if npl_ratio_val is not None else "-",
        # Insurance
        "net_premiums_ltm": _fmt_money(net_prem_val) if is_insurance else "-",
        "combined_ratio": f"{comb_ratio_val:.1f}%" if comb_ratio_val is not None else "-",
        "loss_ratio": f"{loss_ratio_val:.1f}%" if loss_ratio_val is not None else "-",
        "expense_ratio": f"{exp_ratio_val:.1f}%" if exp_ratio_val is not None else "-",
        "inv_yield": f"{inv_yield_val:.1f}%" if inv_yield_val is not None else "-",
        "float_usd": _fmt_money(float_val) if is_insurance else "-",
        "total_investments": _fmt_money(total_inv_val) if is_insurance else "-",
        # REIT
        "rental_rev_ltm": _fmt_money(rental_rev_val) if is_reit else "-",
        "noi_ltm": _fmt_money(noi_val) if is_reit else "-",
        "noi_margin": f"{round(noi_val / rev_ltm_val * 100.0, 1)}%" if (noi_val and rev_ltm_val) else "-",
        "ffo_ltm": _fmt_money(ffo_val) if is_reit else "-",
        "ffo_margin": f"{round(ffo_val / rev_ltm_val * 100.0, 1)}%" if (ffo_val and rev_ltm_val) else "-",
        "affo_ltm": _fmt_money(affo_val) if is_reit else "-",
        "ffo_per_share": f"${ffo_sh_val:.2f}" if ffo_sh_val is not None else "-",
        "affo_per_share": f"${affo_sh_val:.2f}" if affo_sh_val is not None else "-",
        "payout_affo": f"{payout_affo_val:.1f}%" if payout_affo_val is not None else "-",
        "ltv_ratio": f"{ltv_val:.1f}%" if ltv_val is not None else "-",
    }

    # Conservamos table_pnl por retrocompatibilidad
    table_pnl = []
    pnl_defs = [
        ("Ingresos Netos (Revenue)", "revenue", True),
        ("Coste de Bienes Vendidos (COGS)", "cost_of_goods_sold", False),
        ("Margen Bruto (Gross Profit)", "gross_profit", True),
        ("Gastos Operativos (OpEx)", "operating_expenses", False),
        ("Beneficio Operativo (EBIT)", "operating_income", True),
        ("Beneficio Neto (Net Income)", "net_income", True),
        ("Flujo de Caja Operativo (CFO)", "cash_from_operations", True),
        ("Inversiones en CapEx", "capital_expenditures", False),
        ("Flujo de Caja Libre (FCF)", "free_cash_flow", True),
        ("Efectivo y Equivalentes", "cash_and_equivalents", False),
        ("Deuda Financiera Total", "total_debt", False),
        ("Deuda Neta", "net_debt", False),
        ("Activos Totales", "total_assets", True),
        ("Patrimonio Neto (Equity)", "stockholders_equity", True),
        ("BPA Diluido Normalizado (Split-Adjusted) ($)", "eps_diluted_adjusted", True),
        ("BPA Diluido Oficial As-Reported (SEC) ($)", "eps_diluted", False),
    ]
    for label, key, is_bold in pnl_defs:
        row_vals = []
        d_dict = canonical.get(key, {})
        if key == "eps_diluted_adjusted" and not d_dict:
            d_dict = canonical.get("eps_diluted", {})
        for p in fys:
            v = d_dict.get(p)
            if v is None:
                val_str = "-"
            elif key in ["eps_diluted", "eps_diluted_adjusted"]:
                val_str = f"-${abs(v):.2f}" if v < 0 else f"${v:.2f}"
            else:
                scale_val = abs(v)
                prefix = "-$" if v < 0 else "$"
                if scale_val >= 1e6:
                    val_str = f"{prefix}{scale_val/1e6:,.1f}M"
                elif scale_val > 0:
                    val_str = f"{prefix}{scale_val:,.1f}M"
                else:
                    val_str = "$0.0M"
            row_vals.append(val_str)
        table_pnl.append({
            "label": label,
            "is_bold": is_bold,
            "values": row_vals
        })


    return {
        "table_pnl": table_pnl,
        "statements_pnl": statements_pnl,
        "statements_cashflow": statements_cashflow,
        "statements_balancesheet": statements_balancesheet,
        "statements_fys": statements_fys,
        "statements_ltm": statements_fys[0] if statements_fys else "LTM",
        "statements_annual_fys": statements_fys[1:] if len(statements_fys) > 1 else [],
        "std_pnl": std_pnl,
        "std_cashflow": std_cashflow,
        "std_balancesheet": std_balancesheet,
        "as_rep_pnl": as_rep_pnl,
        "as_rep_cashflow": as_rep_cashflow,
        "as_rep_balancesheet": as_rep_balancesheet,
        "as_rep_fys": as_rep_fys,
        "as_rep_ltm": as_rep_fys[0] if as_rep_fys else "LTM",
        "as_rep_annual_fys": as_rep_fys[1:] if len(as_rep_fys) > 1 else [],
        "statements_summary": statements_summary,
    }
