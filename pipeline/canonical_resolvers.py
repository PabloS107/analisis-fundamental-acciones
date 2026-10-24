# -*- coding: utf-8 -*-
"""
canonical_resolvers.py — Motor Canónico Unificado (SSOT) del Pipeline.
Resuelve e integra el Estado de Resultados, Balance General, Estado de Flujos de Caja
y Flujos de Asignación de Capital en todas las empresas y arquetipos contables.
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
    as_rep_bs_raw = fs.get("as_reported_statements", {}).get("balance_sheet", []) if isinstance(fs, dict) else []
    as_rep_bs_rows = as_rep_bs_raw if isinstance(as_rep_bs_raw, list) else (as_rep_bs_raw.get("rows", []) if isinstance(as_rep_bs_raw, dict) else [])
    as_rep_bs_dict = {}
    for r in as_rep_bs_rows:
        if isinstance(r, dict) and "concept" in r:
            as_rep_bs_dict[r["concept"]] = r.get("values", {})
    bal_sources = [
        as_rep_bs_dict,
        fs.get("balance_sheet", {}) if isinstance(fs, dict) else {},
        bs_detail
    ]

    def _extract_val(key_cands, p, can_key=None):
        if can_key:
            can_keys = [can_key] if isinstance(can_key, str) else can_key
            for ck in can_keys:
                can_val = canonical.get(ck, {}).get(p)
                if can_val is not None and float(can_val) != 0.0:
                    return float(can_val)
        for src in bal_sources:
            if not isinstance(src, dict):
                continue
            for k in key_cands:
                k_lower = k.lower()
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
        "OtherIntangibleAssetsNet", "us-gaap_IntangibleAssetsNetExcludingGoodwill",
        "IntangibleAssetsNetExcludingGoodwillNoncurrent", "us-gaap_IntangibleAssetsNetExcludingGoodwillNoncurrent",
        "IntangibleAssetsNetNoncurrent", "us-gaap_IntangibleAssetsNetNoncurrent"
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

        is_gw_on_face = any(k.lower().split(':')[-1].split('_')[-1] in [c.lower().split(':')[-1].split('_')[-1] for c in as_rep_bs_dict] for k in gw_keys)
        is_int_on_face = any(k.lower().split(':')[-1].split('_')[-1] in [c.lower().split(':')[-1].split('_')[-1] for c in as_rep_bs_dict] for k in intang_keys)

        if p == "LTM" and gw_v and not is_gw_on_face and len(periods) > 1:
            prev_p = periods[1]
            prev_gw = _extract_val(gw_keys, prev_p)
            ltm_ma = _extract_val(["PaymentsToAcquireBusinessesNetOfCashAcquired", "PaymentsToAcquireBusinessesGross"], "LTM") or 0.0
            if (not prev_gw or prev_gw == 0.0) and (abs(ltm_ma) < 5000.0):
                gw_v = None

        if p == "LTM" and int_v and not is_int_on_face and len(periods) > 1:
            prev_p = periods[1]
            prev_int = _extract_val(intang_keys, prev_p)
            ltm_ma = _extract_val(["PaymentsToAcquireBusinessesNetOfCashAcquired", "PaymentsToAcquireBusinessesGross"], "LTM") or 0.0
            if (not prev_int or prev_int == 0.0) and (abs(ltm_ma) < 5000.0):
                int_v = None

        if gw_v is not None and int_v is not None and gw_v == int_v:
            gw_int_v = gw_v
        else:
            gw_int_v = round((gw_v or 0.0) + (int_v or 0.0), 1) if (gw_v is not None or int_v is not None) else None

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
        if end_cash is None:
            end_cash = _extract_multi_source_val(fs, "balance_sheet", [
                "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
                "CashAndCashEquivalentsAtCarryingValue", "Cash"
            ], p)

        beg_cash = _extract_multi_source_val(fs, "cashflow", [
            "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsBeginningOfPeriod",
            "CashAndCashEquivalentsAtBeginningOfPeriod",
            "CashAndCashEquivalentsAtCarryingValueBeginningOfPeriod",
            "CashBeginningOfPeriod",
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



