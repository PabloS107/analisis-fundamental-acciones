"""
========================================================================================
ORQUESTADOR UNIVERSAL DE ANÁLISIS FUNDAMENTAL - ONTOLOGÍA Y TAXONOMÍA FINANCIERA CANÓNICA
========================================================================================
Módulo centralizado de normalización contable según los estándares FASB US-GAAP e IFRS.
Define las jerarquías de conceptos oficiales, las identidades contables algebraicas y
el motor de reconciliación de estados financieros para los 5 arquetipos institucionales:
- STANDARD_CORPORATE
- FINANCIAL_BANKING
- PLATFORM_ECOSYSTEM
- REAL_ESTATE_REIT
- INSURANCE
"""

from typing import Any, Dict, List, Optional, Tuple, Union
import math
import pandas as pd


# --------------------------------------------------------------------------------------
# 1. TAXONOMÍAS CANÓNICAS JERÁRQUICAS POR ARQUETIPO
# --------------------------------------------------------------------------------------

# --- A. ARQUETIPO CORPORATIVO / INDUSTRIAL UNIVERSAL (C&I: Article 5 S-X) ---
CORPORATE_TAXONOMY_MAP: Dict[str, List[str]] = {
    "revenue": [
        # US-GAAP (Priorizar consolidado Revenues total sobre ASC 606 granular)
        "Revenues",
        "SalesRevenueNet",
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenue",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
        "SalesRevenueGoodsNet",
        "SalesRevenueServicesNet",
        # IFRS (ifrs-full)
        "Revenue",
        "RevenueFromContractsWithCustomers",
        "GrossRevenue",
        "OperatingRevenue",
    ],
    "cost_of_goods_sold": [
        # US-GAAP (Incluyendo CostOfRevenue para Big Tech, Software, SaaS y Cloud)
        "CostOfGoodsAndServicesSold",
        "CostOfRevenue",
        "CostOfSales",
        "CostOfGoodsSold",
        "CostOfServices",
        "CostOfMerchandiseSold",
        "TotalCostOfGoodsSold",
        "CostOfProductsSold",
        "CostOfGoodsAndServiceExcludingDepreciationDepletionAndAmortization",
        "CostOfServicesExcludingDepreciationDepletionAndAmortization",
        "CostOfGoodsSoldExcludingDepreciationDepletionAndAmortization",
        "CostOfRealEstateRevenue",
        "CostOfRevenues",
        "ProductionCosts",
        # IFRS (ifrs-full)
        "CostOfSales",
        "CostOfMerchandiseSold",
    ],
    "gross_profit": [
        "GrossProfit",
        "GrossProfitLoss",
    ],
    "operating_expenses": [
        "OperatingExpenses",
        "TotalOperatingExpenses",
        "OperatingExpense",
        "AdministrativeExpense",
        "DistributionCosts",
        "SellingGeneralAndAdministrativeExpense",
        "CostsAndExpensesOperating",
        "OperatingCosts",
        "TotalOperatingCosts",
    ],
    "costs_and_expenses": [
        "CostsAndExpenses",
        "TotalCostsAndExpenses",
        "OperatingCostsAndExpenses",
        "TotalOperatingCostAndExpense",
        "TotalOperatingCostsAndExpenses",
    ],
    "rd_expense": [
        "ResearchAndDevelopmentExpense",
        "ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost",
        "ResearchAndDevelopmentExpenses",
        "ResearchAndDevelopmentExpenseSoftwareExcludingAcquiredInProcessCost",
        "TechnologyAndContentExpense",
        "TechnologyAndDevelopmentExpense",
        "ResearchAndDevelopmentExpenseSoftware",
        "EngineeringExpense",
        "DevelopmentExpense",
        "ResearchExpense",
        "ResearchAndDevelopmentExpenseNet",
    ],
    "sga_expense": [
        "SellingGeneralAndAdministrativeExpense",
        "SellingGeneralAndAdministrativeExpenses",
        "SellingGeneralAndAdministrative",
    ],
    "sm_expense": [
        "SellingAndMarketingExpense",
        "SellingAndMarketingExpenses",
        "SalesAndMarketingExpense",
        "MarketingAndSalesExpense",
        "SellingExpense",
        "MarketingExpense",
        "SellingAndDistributionExpenses",
        "CustomerServiceAndMarketingExpense",
    ],
    "ga_expense": [
        "GeneralAndAdministrativeExpense",
        "GeneralAndAdministrativeExpenses",
        "AdministrativeExpense",
        "GeneralAdministrativeAndOtherExpense",
    ],
    "operating_income": [
        "OperatingIncomeLoss",
        "OperatingIncome",
        "ProfitLossFromOperatingActivities",
        "OperatingProfitLoss",
    ],
    "net_income": [
        "NetIncomeLoss",
        "NetIncome",
        "ProfitLoss",
        "ProfitLossAttributableToOwnersOfParent",
        "ProfitLossFromContinuingOperations",
    ],
    "net_income_common": [
        "NetIncomeLossAvailableToCommonStockholdersDiluted",
        "us-gaap_NetIncomeLossAvailableToCommonStockholdersDiluted",
        "NetIncomeLossAvailableToCommonStockholdersBasic",
        "us-gaap_NetIncomeLossAvailableToCommonStockholdersBasic",
        "ProfitLossAttributableToOrdinaryEquityHoldersOfParentEntity",
        "ifrs-full_ProfitLossAttributableToOrdinaryEquityHoldersOfParentEntity",
        "ifrs-full_ProfitLossFromContinuingOperationsAttributableToOrdinaryEquityHoldersOfParentEntity",
        "ProfitLossAttributableToOwnersOfParent",
        "ifrs-full_ProfitLossAttributableToOwnersOfParent",
    ],
    "ebt": [
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
        "IncomeLossAttributableToParent",
        "us-gaap_IncomeLossAttributableToParent",
        "IncomeLossBeforeIncomeTaxExpenseBenefit",
        "ProfitLossBeforeTax",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxes",
        "ifrs-full_ProfitLossBeforeTax",
    ],
    "income_tax": [
        "IncomeTaxExpenseBenefit",
        "IncomeTaxExpenseContinuingOperations",
        "nu_IncomeTaxInStatementOfProfitOrLoss",
        "CurrentIncomeTaxExpenseBenefit",
        "ifrs-full_IncomeTaxExpenseContinuingOperations",
        "us-gaap_IncomeTaxExpenseBenefit",
    ],
    "interest_income": [
        "InvestmentIncomeInterest",
        "InterestIncomeOperating",
        "InterestAndDividendIncomeOperating",
        "InterestIncome",
        "ifrs-full_RevenueFromInterest",
        "nu_InterestIncomeAndGainsLossesOnFinancialInstruments",
        "us-gaap_InvestmentIncomeInterest",
    ],
    "interest_expense": [
        "InterestExpense",
        "InterestExpenseNonoperating",
        "InterestExpenseDebt",
        "InterestExpenseOperating",
        "meli_InterestExpenseAndOtherFinancialCharges",
        "deck_InterestAndOtherExpense",
        "us-gaap_InterestExpense",
        "us-gaap_InterestExpenseNonoperating",
    ],
    "non_operating_income": [
        "NonoperatingIncomeExpense",
        "InterestRevenueExpenseNet",
        "deck_InterestAndOtherExpense",
        "NonoperatingIncomeExpenseNet",
        "us-gaap_NonoperatingIncomeExpense",
    ],
    "shares_basic": [
        "WeightedAverageNumberOfSharesOutstandingBasic",
        "CommonStockSharesOutstanding",
        "WeightedAverageShares",
        "WeightedAverageNumberOfOrdinarySharesOutstandingBasic",
        "NumberOfSharesOutstanding",
    ],
    "shares_diluted": [
        "WeightedAverageNumberOfDilutedSharesOutstanding",
        "WeightedAverageNumberOfSharesOutstandingDiluted",
        "DilutedWeightedAverageShares",
        "WeightedAverageNumberOfOrdinarySharesOutstandingDiluted",
        "AdjustedWeightedAverageShares",
        "CommonStockSharesOutstanding",
    ],
    "eps_basic": [
        "EarningsPerShareBasic",
        "EarningsPerShareBasicAndDiluted",
        "BasicEarningsPerShare",
        "BasicEarningsLossPerShare",
        "BasicEarningsLossPerShareFromContinuingOperations",
    ],
    "eps_diluted": [
        "EarningsPerShareDiluted",
        "EarningsPerShareBasicAndDiluted",
        "DilutedEarningsPerShare",
        "DilutedEarningsLossPerShare",
        "DilutedEarningsLossPerShareFromContinuingOperations",
    ],
    "cash_from_operations": [
        "NetCashProvidedByUsedInOperatingActivities",
        "NetCashProvidedByOperatingActivities",
        "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
        "CashFlowsFromUsedInOperatingActivities",
    ],
    "capital_expenditures": [
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "PaymentsForCapitalImprovements",
        "PaymentsToAcquireProductiveAssets",
        "PurchaseOfPropertyPlantAndEquipment",
        "PaymentsForPropertyPlantAndEquipmentAndIntangibleAssets",
        "AdditionsToPropertyPlantAndEquipment",
        "PaymentsToAcquireOtherProductiveAssets",
        "CapitalExpendituresIncurredButNotYetPaid",
        "PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities",
        "PurchaseOfPropertyPlantAndEquipmentIntangibleAssetsOtherThanGoodwillInvestmentPropertyAndOtherNoncurrentAssets",
        "AcquisitionAndDevelopmentOfIntangibleAssets",
        "PaymentsToAcquireCapitalAssets",
        "PaymentsForSoftware",
        "PaymentsToDevelopSoftware",
        "PaymentsToAcquireIntangibleAssets",
        "AdditionsToSoftware",
        "AdditionsToProductiveAssets",
    ],
    "total_assets": [
        "Assets",
        "TotalAssets",
    ],
    "stockholders_equity": [
        "StockholdersEquity",
        "EquityAttributableToOwnersOfParent",
        "Equity",
        "TotalEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
        "CommonEquity",
        "AllEquityBalance",
    ],
    "cash_and_equivalents": [
        "CashAndCashEquivalentsAtCarryingValue",
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
        "CashAndCashEquivalents",
        "Cash",
    ],
    "marketable_securities_current": [
        "MarketableSecuritiesCurrent",
        "ShortTermInvestments",
        "AvailableForSaleSecuritiesCurrent",
        "DebtSecuritiesCurrent",
        "EquitySecuritiesFvNi",
        "MarketableSecurities",
        "OtherShortTermInvestments",
        "FinancialAssetsAtFairValueThroughProfitOrLossCurrent",
        "OtherCurrentFinancialAssets",
    ],
    "short_term_debt": [
        "DebtCurrent",
        "us-gaap_DebtCurrent",
        "ShortTermDebt",
        "CurrentPortionOfLongTermDebt",
        "CommercialPaper",
        "RevolvingCreditFacilityAndCommercialPaper",
        "LineOfCreditAndCommercialPaper",
        "LinesOfCreditCurrent",
        "LineOfCredit",
        "CurrentBorrowingsAndOtherFinancialLiabilities",
        "CurrentPortionOfNoncurrentBorrowings",
        "CurrentFinancialLiabilities",
        "BorrowingsFromFinancialInstitutions",
        "ShortTermBorrowings",
    ],
    "long_term_debt": [
        "LongTermDebtNoncurrent",
        "LongTermDebt",
        "DebtLongtermAndShorttermCombinedAmount",
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
    "current_assets": [
        "AssetsCurrent",
        "CurrentAssetsTotal",
        "CurrentAssets",
    ],
    "current_liabilities": [
        "LiabilitiesCurrent",
        "CurrentLiabilitiesTotal",
        "CurrentLiabilities",
    ],
    "accounts_receivable": [
        "AccountsReceivableNetCurrent",
        "AccountsNotesAndLoansReceivableNetCurrent",
        "ReceivablesNetCurrent",
        "TradeAndOtherCurrentReceivables",
        "ContractWithCustomerAssetNetCurrent",
        "UnbilledReceivablesCurrent",
        "NontradeReceivablesCurrent",
        "AccountsAndNotesReceivableNetCurrent",
        "TradeAndOtherReceivablesCurrent",
    ],
    "inventories": [
        "InventoryNet",
        "Inventories",
        "MerchandiseInventories",
    ],
    "other_current_assets": [
        "OtherAssetsCurrent",
        "us-gaap_OtherAssetsCurrent",
        "PrepaidExpenseAndOtherAssetsCurrent",
        "us-gaap_PrepaidExpenseAndOtherAssetsCurrent",
        "OtherCurrentAssets",
        "us-gaap_OtherCurrentAssets",
        "PrepaidExpensesAndOtherCurrentAssets",
        "PrepaidExpenseCurrent",
        "us-gaap_PrepaidExpenseCurrent",
    ],
    "net_ppe": [
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
    ],
    "gross_ppe": [
        "PropertyPlantAndEquipmentGross",
        "us-gaap_PropertyPlantAndEquipmentGross",
        "PropertyPlantAndEquipmentGrossExcludingRightOfUseAsset",
        "PropertyPlantAndEquipmentAndFinanceLeaseRightOfUseAssetBeforeAccumulatedDepreciationAndAmortization",
    ],
    "accumulated_depreciation": [
        "AccumulatedDepreciationDepletionAndAmortizationPropertyPlantAndEquipment",
        "us-gaap_AccumulatedDepreciationDepletionAndAmortizationPropertyPlantAndEquipment",
        "PropertyPlantAndEquipmentAccumulatedDepreciation",
    ],
    "operating_lease_rou_asset": [
        "OperatingLeaseRightOfUseAsset",
        "RightOfUseAssets",
        "RightOfUseAsset",
        "FinanceLeaseRightOfUseAsset",
        "LesseeOperatingLeaseRightOfUseAsset",
        "OperatingLeaseRightOfUseAssetNet",
        "FinanceLeaseRightOfUseAssetNet",
    ],
    "long_term_investments": [
        "MarketableSecuritiesNoncurrent",
        "NonmarketableEquitySecuritiesCarryingValue",
        "EquitySecuritiesWithoutReadilyDeterminableFairValueAmount",
        "EquitySecuritiesFVNINoncurrent",
        "LongTermInvestments",
        "OtherInvestmentsNoncurrent",
        "InvestmentsInAffiliatesSubsidiariesAssociatesAndJointVentures",
        "InvestmentsInAssociates",
        "EquityMethodInvestments",
        "AvailableForSaleDebtSecuritiesNoncurrent",
        "HeldToMaturitySecuritiesNoncurrent",
        "OtherLongTermInvestments",
        "OtherInvestments",
    ],
    "accrued_liabilities": [
        "AccruedLiabilitiesCurrent",
        "OtherAccruedLiabilitiesCurrent",
        "AccruedLiabilities",
    ],
    "dividends_paid": [
        "PaymentsOfDividends",
        "PaymentsOfDividendsCommonStock",
        "DividendsPaid",
        "Dividends",
    ],
    "share_repurchases": [
        "PaymentsForRepurchaseOfCommonStock",
        "PaymentsForRepurchaseOfEquity",
        "PaymentsForRepurchaseOfStock",
        "RepurchaseOfCommonStock",
        "SharesRepurchased",
        "PaymentsForRepurchaseOfCapitalStock",
        "PurchaseOfTreasuryShares",
        "PaymentsForPurchaseOfOwnShares",
        "PurchaseOfOwnShares",
    ],
    "stock_plans_proceeds": [
        "ProceedsFromStockPlans",
        "ProceedsFromIssuanceOfCommonStock",
        "ProceedsFromIssuanceOfShares",
        "ProceedsFromPaymentsForIssuanceOfCommonStock",
        "ProceedsFromIssuingShares",
    ],
    "share_repurchases_sbc_tax": [
        "PaymentsRelatedToTaxWithholdingForShareBasedCompensation",
        "PaymentsForTaxesRelatedToNetShareSettlementOfEquityAwards",
        "PaymentsRelatedToTaxWithholdingForStockBasedAwards",
        "TaxWithholdingForShareBasedCompensation",
    ],
    "acquisitions_ma": [
        "PaymentsToAcquireBusinessesNetOfCashAcquiredAndPurchasesOfIntangibleAndOtherAssets",
        "PaymentsToAcquireBusinessesNetOfCashAcquired",
        "PaymentsToAcquireBusinessTwoNetOfCashAcquired",
        "PaymentsToAcquireBusinessThreeNetOfCashAcquired",
        "PaymentsToAcquireBusinessesAndInterestInAffiliates",
        "PaymentsToAcquireOtherProductiveAssets",
        "CashFlowsUsedInObtainingControlOfSubsidiariesOrOtherBusinesses",
        "PaymentsToAcquireInterestInAffiliates",
        "PaymentsToAcquireInterestInSubsidiariesAndOtherBusinesses",
        "PaymentsToAcquireJointVentures",
        "PaymentsToAcquireBusinessesGross",
        "AcquisitionOfSubsidiaryNetOfCashAcquired",
    ],
    "debt_repayments": [
        "RepaymentsOfLongTermDebt",
        "RepaymentsOfDebt",
        "FinanceLeasePrincipalPayments",
        "PrincipalPaymentsOfFinanceLeases",
        "RepaymentsOfLinesOfCredit",
        "RepaymentsOfShortTermDebt",
        "RepaymentsOfLongTermCapitalLeaseObligations",
        "PaymentsOfBorrowingsAndFinancing",
        "RepaymentsOfTermLoans",
        "RepaymentsOfConvertibleDebt",
        "RepaymentsOfSeniorNotes",
        "RepaymentsOfOtherLongTermDebt",
        "RepaymentsOfSecuredDebt",
        "PaymentsOfLeaseLiabilities",
        "RepaymentsOfBorrowingsClassifiedAsFinancingActivities",
    ],
    "debt_issuances": [
        "ProceedsFromIssuanceOfLongTermDebt",
        "ProceedsFromIssuanceOfDebt",
        "ProceedsFromLinesOfCredit",
        "ProceedsFromIssuanceOfShortTermDebt",
        "ProceedsFromBorrowingsAndFinancing",
        "ProceedsFromTermLoans",
        "ProceedsFromConvertibleDebt",
        "ProceedsFromIssuanceOfConvertibleDebt",
        "ProceedsFromIssuanceOfSeniorNotes",
        "ProceedsFromDebtNetOfIssuanceCosts",
        "ProceedsFromIssuanceOfOtherLongTermDebt",
        "ProceedsFromBorrowingsClassifiedAsFinancingActivities",
    ],
}


# --- B. ARQUETIPO BANCARIO / FINTECH (Article 9 S-X) ---
BANKING_TAXONOMY_MAP: Dict[str, List[str]] = {
    "net_interest_income": [
        "NetInterestIncome",
        "InterestIncomeExpenseNet",
    ],
    "non_interest_income": [
        "FeeAndCommissionIncome",
        "NoninterestIncome",
        "FeesAndCommissionsIncome",
        "NonInterestIncome",
        "CardAndPaymentProcessingFees",
        "InterchangeAndNetworkFees",
        "CreditCardFees",
        "PaymentProcessingRevenue",
        "ServiceChargesOnDepositAccounts",
        "BankAndServiceCharges",
        "InvestmentBankingFees",
        "FiduciaryAndAssetManagementFees",
        "TradingGainsLossesNet",
        "OtherNoninterestIncome",
    ],
    "interest_income": [
        "IncomeExpenseGainsOrLossesOfFinancialInstruments",
        "InterestIncomeOperating",
        "InterestAndDividendIncomeOperating",
        "InterestIncome",
        "InterestAndFeeIncomeOnLoans",
        "InterestAndFeesOnLoans",
        "InterestIncomeOnLoansAndLeases",
        "InterestIncomeOnSecurities",
        "InterestAndDividendIncomeSecurities",
        "InterestIncomeFederalFundsSoldAndSecuritiesPurchasedUnderAgreementsToResell",
        "InterestAndDividendIncome",
    ],
    "interest_expense": [
        "InterestExpense",
        "InterestAndOtherFinancialExpenses",
        "InterestExpenseOperating",
        "InterestExpenseDeposits",
        "InterestExpenseDomesticDeposits",
        "InterestExpenseForeignDeposits",
        "InterestExpenseBorrowings",
        "InterestExpenseFederalFundsPurchasedAndSecuritiesSoldUnderAgreementsToRepurchase",
        "InterestExpenseDepositsAndBorrowings",
    ],
    "credit_loss_provisions": [
        "ExpectedCreditLoss",
        "CreditLossAllowanceExpenses",
        "CreditLossExpense",
        "CreditLossAllowance",
        "ProvisionForLoanAndLeaseLosses",
        "ProvisionForCreditLosses",
        "ProvisionForDoubtfulAccounts",
        "LossContingencyAccrualProvision",
        "CreditCardLossProvision",
        "ProvisionForLoanLeaseAndOtherLosses",
        "AllowanceForCreditLossesProvision",
    ],
    "operating_expenses": [
        "OperatingExpense",
        "TotalOperatingExpenses",
        "NoninterestExpense",
        "GeneralAndAdministrativeExpense",
        "AdministrativeExpense",
    ],
    "transactional_expenses": [
        "nu_TransactionalExpenses",
        "TransactionalExpenses",
        "TransactionExpenses",
        "CostOfTransactionalServices",
    ],
    "share_of_associates": [
        "nu_ShareOfLossInAssociates",
        "ShareOfProfitLossOfAssociatesAndJointVenturesAccountedForUsingEquityMethod",
        "IncomeLossFromEquityMethodInvestments",
        "ShareOfLossInAssociates",
    ],
    "cash_and_liquidity": [
        "CashAndCashEquivalents",
        "CashAndBalancesWithCentralBanks",
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
    ],
    "central_bank_deposits": [
        "CompulsoryAndOtherDepositsAtCentralBanks",
        "CompulsoryDepositsWithCentralBanks",
    ],
    "net_loans": [
        "FinancingReceivableExcludingAccruedInterestAfterAllowanceForCreditLoss",
        "FinancingReceivableAfterAllowanceForCreditLoss",
        "TotalLoansAndAdvancesToCustomers",
        "LoansAndAdvancesToCustomers",
        "LoansAndLeasesReceivableNetOfDeferredIncome",
        "LoansReceivableNetofDeferredIncome",
        "LoansReceivableNet",
        "LoansReceivable",
        "CreditCardReceivables1",
        "NotesAndLoansReceivableNetCurrent",
        "NotesAndLoansReceivableNetNoncurrent",
        "NotesAndLoansReceivableNet",
        "CommercialLoansReceivableNet",
        "ConsumerLoansReceivableNet",
        "CreditCardReceivablesNet",
        "CreditCardReceivables",
        "PersonalLoansReceivableNet",
        "AllowanceForCreditLossesOnFinancingReceivables",
        "LoansAndAdvancesToCustomersNetOfAllowances",
    ],
    "total_deposits": [
        "DepositsFromCustomers",
        "Deposits",
        "InterestBearingDepositLiabilities",
        "CustomerAccounts",
        "NoninterestBearingDepositLiabilities",
        "CustomerAccountBalances",
        "SavingsAndInterestCheckingDeposits",
        "TimeDepositsAtCarryingValue",
        "DemandDeposits",
        "TotalDeposits",
    ],
    "long_term_debt": [
        "Borrowings",
        "BorrowingsAndFinancing",
        "SubordinatedDebt",
        "DebtSecuritiesIssued",
        "NoncurrentBorrowings",
        "LongTermDebtNoncurrent",
        "LongTermDebtAndCapitalLeaseObligationsIncludingCurrentMaturities",
        "LongTermDebt",
    ],
    "short_term_interbank": [
        "ShortTermBorrowings",
        "MoneyMarketRepurchaseAgreements",
        "InterbankTransactionsAndRepurchaseAgreements",
        "RepurchaseAgreements",
        "FederalFundsPurchasedAndSecuritiesSoldUnderAgreementsToRepurchase",
    ],
    "accounts_payable": [
        "OtherPayables",
        "PayablesToNetwork",
        "AccountsPayable",
    ],
    "investment_securities": [
        "Securities",
        "OtherSecurities",
    ],
    "allowance_for_credit_losses": [
        "FinancingReceivableAllowanceForCreditLossExcludingAccruedInterest",
        "FinancingReceivableAllowanceForCreditLosses",
        "LoansAndLeasesReceivableAllowance",
        "AllowanceForLoanAndLeaseLosses",
        "AllowanceAccountForCreditLossesOfFinancialAssets",
        "AllowanceForCreditLossesOnFinancingReceivables",
    ],
}


# --- C. ARQUETIPO REIT INMOBILIARIO (Article 6 S-X / SIC 6798) ---
REIT_TAXONOMY_MAP: Dict[str, List[str]] = {
    "total_revenue": [
        "Revenues",
        "TotalRevenuesAndOtherIncome",
        "Revenue",
        "SalesRevenueNet",
        "OperatingRevenues",
    ],
    "rental_revenue": [
        "RentalRevenue",
        "OperatingLeaseRevenue",
        "RealEstateRevenueNet",
        "LeaseIncome",
        "RealEstateRentalRevenue",
        "OperatingLeasesIncomeStatementLeaseRevenue",
        "PropertyManagementFeeRevenue",
    ],
    "property_operating_expenses": [
        "DirectCostsOfLeasedAndRentedPropertyOrEquipment",
        "DirectCostsOfLeasedAndRentedPropertyOrEquipmentIncludingReimbursableExpense",
        "RealEstateExpense",
        "PropertyOperatingExpenses",
        "DirectOperatingExpensesFromRentalProperty",
        "RealEstateOperatingExpense",
        "OperatingExpenses",
        "RealEstateTaxes",
        "PropertyOperatingExpensesExcludingRealEstateTaxes",
        "PropertyManagementExpenses",
        "RepairsAndMaintenanceExpense",
        "GroundRentExpense",
    ],
    "real_estate_depreciation": [
        "DepreciationDepletionAndAmortization",
        "DepreciationAndAmortizationRealEstate",
        "RealEstateDepreciationAndAmortization",
        "RealEstateDepreciation",
        "DepreciationExpenseRealEstate",
        "DepreciationAndAmortization",
        "Depreciation",
    ],
    "gain_loss_sale_properties": [
        "GainLossOnSaleOfRealEstateOperatingProperties",
        "GainLossOnSaleOfPropertiesNet",
        "GainLossOnSaleOfProperties",
        "DisposalGroupNotDiscontinuedOperationGainLossOnDisposal",
        "GainLossOnSaleOfRealEstate",
        "GainLossOnDispositionOfAssets",
    ],
    "recurring_capex_maintenance": [
        "PaymentsForCapitalImprovements",
        "PaymentsForPropertyImprovements",
        "RecurringCapitalExpendituresMaintenance",
        "RecurringCapitalExpenditures",
        "CapitalExpendituresIncurredButNotYetPaid",
        "MaintenanceCapitalExpenditures",
        "PaymentsToAcquireProductiveAssets",
        "PaymentsForTenantImprovementsAndLeasingCommissions",
        "PaymentsForBuildingImprovements",
        "PaymentsForTenantImprovements",
        "CapitalizedLeasingCommissions",
    ],
    "real_estate_acquisitions": [
        "PaymentsToAcquireRealEstate",
        "PaymentsToAcquireRealEstateHeldForInvestment",
        "PaymentsToAcquireOtherRealEstate",
        "PaymentsToDevelopRealEstate",
        "RealEstateInvestmentPropertyAtCost",
        "RealEstateInvestmentPropertyAccumulatedDepreciation",
        "RealEstateInvestmentPropertyNet",
        "InvestmentProperties",
        "ConstructionInProgressRealEstate",
    ],
}


# --- D. ARQUETIPO DE SEGUROS (Article 7 S-X / SIC 6300-6499) ---
INSURANCE_TAXONOMY_MAP: Dict[str, List[str]] = {
    "total_revenue": [
        "Revenues",
        "TotalRevenuesAndOtherIncome",
        "Revenue",
        "PremiumsAndOtherRevenues",
    ],
    "net_premiums_earned": [
        "PremiumsEarnedNet",
        "PremiumsEarnedNetPropertyAndCasualty",
        "NetPremiumsEarned",
        "InsurancePremiumsEarnedNet",
        "PremiumsEarned",
        "PremiumsWrittenNet",
        "PremiumsWrittenGross",
        "DirectPremiumsWritten",
        "CededPremiumsWritten",
        "CededPremiumsEarned",
        "NetPremiumsWritten",
    ],
    "net_investment_income": [
        "NetInvestmentIncome",
        "InvestmentIncomeNet",
        "InterestAndDividendIncomeOperatingNet",
        "NetInvestmentIncomeExpense",
    ],
    "losses_and_loss_expenses": [
        "IncurredClaimsAndLossAdjustmentExpensesNet",
        "PolicyholderBenefitsAndClaimsIncurredNet",
        "LossesAndLossAdjustmentExpensesNet",
        "BenefitsLossesAndExpenses",
        "PolicyholderBenefitsAndClaims",
        "LossAdjustmentExpenses",
        "ClaimsAndLossAdjustmentExpenses",
    ],
    "acquisition_costs": [
        "DeferredPolicyAcquisitionCostAmortizationExpense",
        "PolicyAcquisitionCosts",
        "AmortizationOfDeferredPolicyAcquisitionCosts",
        "DeferredPolicyAcquisitionCostsNet",
        "AmortizationOfDeferredPolicyAcquisitionCostsAndOther",
    ],
    "other_underwriting_expenses": [
        "OtherUnderwritingExpense",
        "OtherUnderwritingExpenses",
        "UnderwritingExpenses",
        "OtherInsuranceExpenses",
    ],
    "loss_reserves": [
        "LiabilityForClaimsAndClaimsAdjustmentExpense",
        "LossAndLossAdjustmentExpenseReserve",
        "ReserveForUnpaidClaimsNet",
        "LiabilityForFuturePolicyBenefits",
        "UnpaidClaimsAndClaimAdjustmentExpenses",
        "LossAndLossAdjustmentExpenseReserves",
    ],
    "unearned_premiums": [
        "UnearnedPremiums",
        "LiabilityForUnearnedPremiumsNet",
        "UnearnedPremiumsNet",
    ],
    "reinsurance_receivables": [
        "ReinsuranceRecoverablesOnPaidAndUnpaidLosses",
        "ReinsuranceRecoverables",
        "ReinsuranceReceivablesNet",
        "ReinsuranceRecoverableForPaidAndUnpaidLosses",
        "PrepaidReinsurancePremiums",
    ],
    "total_investments": [
        "AvailableForSaleSecuritiesDebtSecurities",
        "Investments",
        "InvestmentSecuritiesNet",
        "InvestmentsAndOtherAssets",
    ],
}


# --- E. ARQUETIPO DE PLATAFORMA / ECOSISTEMA MULTI-LADO ---
PLATFORM_TAXONOMY_MAP: Dict[str, List[str]] = dict(CORPORATE_TAXONOMY_MAP)
PLATFORM_TAXONOMY_MAP.update({
    "credit_loss_provisions": BANKING_TAXONOMY_MAP["credit_loss_provisions"],
    "net_loans": BANKING_TAXONOMY_MAP["net_loans"],
    "total_deposits": BANKING_TAXONOMY_MAP["total_deposits"],
    "net_interest_income": BANKING_TAXONOMY_MAP["net_interest_income"],
    "commerce_revenue": [
        "CommerceRevenue",
        "MarketplaceRevenue",
        "RetailRevenueNet",
        "OnlineStoresRevenue",
        "ThirdPartySellerServicesRevenue",
    ],
    "fintech_revenue": [
        "FintechRevenue",
        "FinancialServicesRevenue",
        "PaymentServicesRevenue",
        "CreditAndPaymentProcessingRevenue",
    ],
    "shipping_revenue": [
        "ShippingRevenue",
        "LogisticsRevenue",
        "FulfillmentRevenue",
    ],
    "advertising_revenue": [
        "AdvertisingRevenue",
        "AdRevenue",
        "MarketingServicesRevenue",
    ],
    "platform_cost_of_services": [
        "ShippingAndFulfillmentCost",
        "PaymentProcessingCosts",
        "NetworkTransactionFees",
        "CustomerServiceAndFulfillmentCost",
    ],
    "customer_account_liabilities": [
        "CustomerAccountBalances",
        "PayablesToMerchantsAndUsers",
        "FundsPayableToCustomers",
        "CustomerFundsLiabilities",
    ],
})


# Master Map Unificado (Compatibilidad universal con código existente)
XBRL_TAXONOMY_MAP: Dict[str, List[str]] = dict(CORPORATE_TAXONOMY_MAP)
XBRL_TAXONOMY_MAP["operating_cash_flow"] = XBRL_TAXONOMY_MAP["cash_from_operations"]
XBRL_TAXONOMY_MAP["capex"] = XBRL_TAXONOMY_MAP["capital_expenditures"]
XBRL_TAXONOMY_MAP["ppe_net"] = XBRL_TAXONOMY_MAP["net_ppe"]
XBRL_TAXONOMY_MAP["buybacks"] = XBRL_TAXONOMY_MAP["share_repurchases"]
XBRL_TAXONOMY_MAP["dividends"] = XBRL_TAXONOMY_MAP["dividends_paid"]


# --------------------------------------------------------------------------------------
# 2. MOTOR DE EXTRACCIÓN Y BÚSQUEDA CONCEPTUAL NORMALIZADA
# --------------------------------------------------------------------------------------

def get_first_matching_value(
    data_by_concept: Dict[str, Any],
    concept_candidates: List[str],
    period: str,
) -> Optional[float]:
    """
    Busca de manera jerárquica y con tolerancia sintáctica el primer valor contable
    disponible para un período dado, respetando la precedencia ontológica oficial.
    """
    if not data_by_concept or not concept_candidates:
        return None

    for cand in concept_candidates:
        cand_lower = cand.lower().replace("-", "").replace("_", "")
        cand_token = cand.lower().split(":")[-1].split("_")[-1].replace("-", "")
        for c_key, c_data in data_by_concept.items():
            if "abstract" in str(c_key).lower():
                continue

            raw_k = str(c_key).lower()
            k_token = raw_k.split(":")[-1].split("_")[-1].replace("-", "")
            k_lower = raw_k.replace("-", "").replace("_", "")

            raw_std = str(c_data.get("standard_concept") or "").lower()
            if "abstract" in raw_std:
                continue
            std_token = raw_std.split(":")[-1].split("_")[-1].replace("-", "")
            std_concept = raw_std.replace("-", "").replace("_", "")

            lbl = str(c_data.get("label") or "").lower().replace("-", "").replace("_", "")

            if (
                k_token == cand_lower
                or k_token == cand_token
                or k_lower == cand_lower
                or std_token == cand_lower
                or std_token == cand_token
                or std_concept == cand_lower
                or (lbl == cand_lower and len(lbl) > 6)
            ):
                vals = c_data.get("values", {})
                if isinstance(vals, dict):
                    val = vals.get(period)
                    if val is not None and not pd.isna(val):
                        try:
                            return float(val)
                        except (ValueError, TypeError):
                            pass
    return None


# --------------------------------------------------------------------------------------
# 3. MOTOR DE IDENTIDADES CONTABLES Y DERIVACIÓN ALGEBRAICA (ACCOUNTING IDENTITIES)
# --------------------------------------------------------------------------------------

def reconcile_accounting_identities(
    canonical: Dict[str, Dict[str, Optional[float]]],
    period: str,
    archetype: str = "STANDARD_CORPORATE",
) -> Dict[str, Any]:
    """
    Aplica las identidades contables universales de GAAP e IFRS para reconciliar
    partidas no reportadas explícitamente (ej. Gross Profit en empresas de software/tech).

    Retorna un diccionario de metadatos con el estatus de cada partida reconciliada:
    {
      "metric": "gross_profit",
      "status": "DERIVED" | "REPORTED" | "NOT_APPLICABLE",
      "formula": "Revenue - CostOfRevenue",
      "confidence": 1.0
    }
    """
    audit_trail: Dict[str, Dict[str, Any]] = {}

    rev = canonical.get("revenue", {}).get(period)
    cogs = canonical.get("cost_of_goods_sold", {}).get(period)
    gp = canonical.get("gross_profit", {}).get(period)
    op_inc = canonical.get("operating_income", {}).get(period)
    op_exp = canonical.get("operating_expenses", {}).get(period)
    rd = canonical.get("rd_expense", {}).get(period)
    sga = canonical.get("sga_expense", {}).get(period)

    cf_ops = canonical.get("cash_from_operations", {}).get(period)
    capex = canonical.get("capital_expenditures", {}).get(period)
    fcf = canonical.get("free_cash_flow", {}).get(period)

    cash = canonical.get("cash_and_equivalents", {}).get(period)
    st_inv = canonical.get("short_term_investments", {}).get(period)
    liquid_cash = canonical.get("total_liquid_cash", {}).get(period)

    st_debt = canonical.get("short_term_debt", {}).get(period)
    lt_debt = canonical.get("long_term_debt", {}).get(period)
    total_debt = canonical.get("total_debt", {}).get(period)

    ca = canonical.get("current_assets", {}).get(period)
    cl = canonical.get("current_liabilities", {}).get(period)

    # 1. Reconciliación de Margen Bruto y Costo de Ventas (Big Tech / Software)
    if archetype in ("STANDARD_CORPORATE", "PLATFORM_ECOSYSTEM"):
        if gp is None and rev is not None and cogs is not None:
            derived_gp = round(rev - abs(cogs), 2)
            canonical["gross_profit"][period] = derived_gp
            audit_trail["gross_profit"] = {
                "status": "DERIVED",
                "formula": "Revenue - CostOfRevenue",
                "note": "Reconciliado algebraicamente ante omisión de Gross Profit explícito en SEC 10-K",
            }
        elif cogs is None and rev is not None and gp is not None:
            derived_cogs = round(rev - gp, 2)
            canonical["cost_of_goods_sold"][period] = abs(derived_cogs)
            audit_trail["cost_of_goods_sold"] = {
                "status": "DERIVED",
                "formula": "Revenue - GrossProfit",
                "note": "Deducido de Revenue menos Gross Profit reportado",
            }

        # Reconciliación de OpEx
        expected_opex = round(gp - op_inc, 2) if (gp is not None and op_inc is not None) else None
        if op_exp is None and expected_opex is not None:
            canonical["operating_expenses"][period] = expected_opex
            audit_trail["operating_expenses"] = {
                "status": "DERIVED",
                "formula": "GrossProfit - OperatingIncome",
                "note": "Deducido por identidad contable canónica",
            }
        elif op_exp is None and (rd is not None or sga is not None):
            derived_opex = round((abs(rd) if rd else 0.0) + (abs(sga) if sga else 0.0), 2)
            canonical["operating_expenses"][period] = derived_opex
            audit_trail["operating_expenses"] = {
                "status": "DERIVED",
                "formula": "R&D + SG&A",
                "note": "Reconciliado a partir de componentes operativos reportados",
            }
        elif op_exp is not None and expected_opex is not None and expected_opex > 0:
            if abs(op_exp - expected_opex) > 1.0:
                canonical["operating_expenses"][period] = expected_opex
                audit_trail["operating_expenses"] = {
                    "status": "RECONCILED",
                    "formula": "GrossProfit - OperatingIncome",
                    "note": f"Ajustado OpEx canónico (reportado {op_exp} difería de la identidad contable)",
                }

        # Reconciliación de Operating Income si falta y tenemos GP y OpEx
        if op_inc is None and gp is not None and canonical["operating_expenses"].get(period) is not None:
            canonical["operating_income"][period] = round(gp - canonical["operating_expenses"][period], 2)
            audit_trail["operating_income"] = {
                "status": "DERIVED",
                "formula": "GrossProfit - OperatingExpenses",
                "note": "Calculado por identidad contable",
            }

    # 2. Reconciliación de Caja Líquida y Deuda Total
    if liquid_cash is None:
        c_val = cash if cash is not None else 0.0
        st_val = st_inv if st_inv is not None else 0.0
        if cash is not None or st_inv is not None:
            tot_liq = round(c_val + st_val, 2)
            canonical["total_liquid_cash"][period] = tot_liq
            audit_trail["total_liquid_cash"] = {
                "status": "DERIVED",
                "formula": "Cash & Equivalents + Marketable Securities",
                "note": "Agregación de liquidez inmediata",
            }

    if total_debt is None:
        sd_val = st_debt if st_debt is not None else 0.0
        ld_val = lt_debt if lt_debt is not None else 0.0
        if st_debt is not None or lt_debt is not None:
            tot_d = round(sd_val + ld_val, 2)
            canonical["total_debt"][period] = tot_d
            audit_trail["total_debt"] = {
                "status": "DERIVED",
                "formula": "ShortTermDebt + LongTermDebt",
                "note": "Deuda financiera consolidada",
            }

    # Reconciliación de Deuda Neta
    t_debt_cur = canonical.get("total_debt", {}).get(period)
    t_liq_cur = canonical.get("total_liquid_cash", {}).get(period)
    if t_debt_cur is not None and t_liq_cur is not None:
        canonical["net_debt"][period] = round(t_debt_cur - t_liq_cur, 2)

    # 3. Reconciliación de Free Cash Flow (FCF)
    if archetype in ("FINANCIAL_BANKING", "INSURANCE"):
        canonical["free_cash_flow"][period] = None
        canonical["gross_profit"][period] = None
        canonical["cost_of_goods_sold"][period] = None
    elif fcf is None and cf_ops is not None and capex is not None:
        fcf_val = round(cf_ops - abs(capex), 2)
        canonical["free_cash_flow"][period] = fcf_val
        audit_trail["free_cash_flow"] = {
            "status": "DERIVED",
            "formula": "CashFromOperations - CapEx",
            "note": "Reconciliación canónica de flujo de caja libre institucional",
        }

    # 4. Reconciliación de Capital de Trabajo Neto (Net Working Capital)
    if ca is not None and cl is not None:
        canonical["net_working_capital"][period] = round(ca - cl, 2)

    return audit_trail


# --------------------------------------------------------------------------------------
# 4. GENERADOR DE BANDERAS Y BADGES INSTITUCIONALES DE INTEGRIDAD
# --------------------------------------------------------------------------------------

def generate_data_integrity_badge(
    metric_name: str,
    value: Optional[float],
    status: str = "REPORTED",
    formula: Optional[str] = None,
    warning: Optional[str] = None,
) -> Dict[str, Any]:
    """Genera la estructura de trazabilidad y advertencia institucional para un dato normalizado."""
    is_nd = (value is None or (isinstance(value, float) and (math.isnan(value) or math.isinf(value))))
    return {
        "metric": metric_name,
        "value": value if not is_nd else None,
        "status": "NOT_AVAILABLE" if is_nd else status,
        "is_derived": (status == "DERIVED"),
        "formula_used": formula,
        "warning": warning,
        "badge_label": "N/D" if is_nd else ("DERIVADO" if status == "DERIVED" else "AUDITADO"),
        "badge_color": "gray" if is_nd else ("blue" if status == "DERIVED" else "green"),
    }
