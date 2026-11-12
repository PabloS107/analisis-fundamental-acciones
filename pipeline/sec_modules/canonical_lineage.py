# -*- coding: utf-8 -*-
"""
Linaje Canónico y Atribución Automática de Partidas No Mapeadas ("Otros").
Conecta cada celda estandarizada con:
1. Sus conceptos XBRL exactos y etiquetas verbatim SEC en `as_reported_statements`.
2. Su fórmula contable o identidad matemática.
3. Un desglose transparente de partidas no mapeadas que componen cualquier cajón "Otros".
4. El puente LTM exacto (`FY_base + YTD_actual - YTD_anterior` o `Balance MRQ`).
"""
from __future__ import annotations

import re

# Relación de cada campo estandarizado -> tipo de estado as-reported, etiqueta legible, fórmula y conceptos candidatos
CANONICAL_LINEAGE_SPECS = {
    # --- Income Statement ---
    "revenue": {
        "stmt": "income_statement",
        "method": "XBRL_CONCEPT",
        "formula_es": "Extracción directa de ingresos netos reportados en carátula SEC (ASC 606 / IFRS 15).",
        "concepts": ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet", "TotalRevenuesAndOtherIncome", "Revenue", "ifrs-full_Revenue", "RevenuesNetOfInterestExpense"],
    },
    "cogs": {
        "stmt": "income_statement",
        "method": "XBRL_CONCEPT",
        "formula_es": "Costo directo de bienes y servicios vendidos (o Revenues − Gross Profit si se deduce de carátula).",
        "concepts": ["CostOfGoodsAndServicesSold", "CostOfRevenue", "CostOfGoodsSold", "CostOfPurchasedGoodsAndServices", "CostOfGoodsAndServiceExcludingDepreciationDepletionAndAmortization", "ifrs-full_CostOfSales"],
    },
    "gross_profit": {
        "stmt": "income_statement",
        "method": "IDENTITY",
        "formula_es": "Gross Profit = Revenue − Cost of Goods Sold (o partida explícita SEC).",
        "components": ["revenue", "cogs"],
        "concepts": ["GrossProfit", "ifrs-full_GrossProfit"],
    },
    "rd_expense": {
        "stmt": "income_statement",
        "method": "XBRL_CONCEPT",
        "formula_es": "Gastos de Investigación, Tecnología y Desarrollo reportados en OpEx.",
        "concepts": ["ResearchAndDevelopmentExpense", "TechnologyAndContentExpense", "TechnologyAndDevelopmentExpense", "ResearchAndDevelopmentExpenseSoftware", "ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost"],
    },
    "sga_expense": {
        "stmt": "income_statement",
        "method": "XBRL_CONCEPT",
        "formula_es": "Ventas, Marketing y Administración General (SG&A = Sales & Marketing + G&A si se desglosan).",
        "concepts": ["SellingGeneralAndAdministrativeExpense", "SellingGeneralAndAdministrative", "SellingAndMarketingExpense", "MarketingExpense", "GeneralAndAdministrativeExpense", "GeneralAdministrativeExpense"],
    },
    "other_operating_expense": {
        "stmt": "income_statement",
        "method": "PLUG_ATTRIBUTION",
        "region": "is_operating_expense",
        "formula_es": "Other OpEx = Total Operating Expenses − (R&D + SG&A + Credit Loss Provision).",
        "concepts": ["OtherOperatingIncomeExpenseNet", "OperationsAndSupportExpense", "DepreciationAndAmortization", "OtherCostAndExpenseOperating"],
    },
    "total_operating_expenses": {
        "stmt": "income_statement",
        "method": "IDENTITY",
        "formula_es": "Total Operating Expenses = R&D + SG&A + Credit Loss Provision + Other Operating Expenses.",
        "components": ["rd_expense", "sga_expense", "credit_loss_provision", "other_operating_expense"],
        "concepts": ["OperatingExpenses", "CostsAndExpenses"],
    },
    "operating_income": {
        "stmt": "income_statement",
        "method": "IDENTITY",
        "formula_es": "Operating Income (EBIT) = Gross Profit − Total Operating Expenses (o OperatingIncomeLoss SEC).",
        "components": ["gross_profit", "total_operating_expenses"],
        "concepts": ["OperatingIncomeLoss", "ifrs-full_ProfitLossFromOperatingActivities"],
    },
    "other_non_operating": {
        "stmt": "income_statement",
        "method": "PLUG_ATTRIBUTION",
        "region": "is_non_operating",
        "formula_es": "Other Non-Operating = Total Non-Operating − (Interest Income − Interest Expense).",
        "concepts": ["OtherNonoperatingIncomeExpense", "NonoperatingIncomeExpense"],
    },
    "total_non_operating": {
        "stmt": "income_statement",
        "method": "IDENTITY",
        "formula_es": "Total Non-Operating = Interest Income − Interest Expense + Other Non-Operating (+ Assoc.).",
        "components": ["interest_income", "interest_expense", "other_non_operating"],
        "concepts": ["NonoperatingIncomeExpense"],
    },
    "ebt": {
        "stmt": "income_statement",
        "method": "IDENTITY",
        "formula_es": "EBT = Operating Income (EBIT) + Total Non-Operating Income (Expense).",
        "components": ["operating_income", "total_non_operating"],
        "concepts": ["IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest", "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments", "ifrs-full_ProfitLossBeforeTax"],
    },
    "income_tax": {
        "stmt": "income_statement",
        "method": "XBRL_CONCEPT",
        "formula_es": "Provisión para impuesto sobre beneficios del ejercicio.",
        "concepts": ["IncomeTaxExpenseBenefit", "ifrs-full_IncomeTaxExpenseContinuingOperations"],
    },
    "net_income": {
        "stmt": "income_statement",
        "method": "XBRL_CONCEPT",
        "formula_es": "Beneficio neto consolidado reportado (EBT − Income Tax).",
        "concepts": ["NetIncomeLoss", "ProfitLoss", "ifrs-full_ProfitLoss"],
    },
    # --- Balance Sheet ---
    "cash": {
        "stmt": "balance_sheet",
        "method": "XBRL_CONCEPT",
        "formula_es": "Efectivo y equivalentes de efectivo reportados en balance.",
        "concepts": ["CashAndCashEquivalentsAtCarryingValue", "CashCashEquivalentsAndFederalFundsSold", "Cash", "ifrs-full_CashAndCashEquivalents"],
    },
    "short_term_investments": {
        "stmt": "balance_sheet",
        "method": "XBRL_CONCEPT",
        "formula_es": "Valores negociables e inversiones financieras de corto plazo.",
        "concepts": ["MarketableSecuritiesCurrent", "ShortTermInvestments", "AvailableForSaleSecuritiesDebtSecuritiesCurrent"],
    },
    "total_liquid_cash": {
        "stmt": "balance_sheet",
        "method": "IDENTITY",
        "formula_es": "Total Cash & ST Investments = Cash & Cash Equivalents + Short-Term Investments.",
        "components": ["cash", "short_term_investments"],
        "concepts": ["CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents", "CashAndShortTermInvestments"],
    },
    "accounts_receivable": {
        "stmt": "balance_sheet",
        "method": "XBRL_CONCEPT",
        "formula_es": "Cuentas comerciales por cobrar netas de provisiones.",
        "concepts": ["AccountsReceivableNetCurrent", "ReceivablesNetCurrent", "AccountsNotesAndLoansReceivableNetCurrent", "ifrs-full_TradeAndOtherCurrentReceivables"],
    },
    "inventories": {
        "stmt": "balance_sheet",
        "method": "XBRL_CONCEPT",
        "formula_es": "Inventarios netos al cierre del período.",
        "concepts": ["InventoryNet", "Inventories", "ifrs-full_Inventories"],
    },
    "other_current_assets": {
        "stmt": "balance_sheet",
        "method": "PLUG_ATTRIBUTION",
        "region": "bs_current_assets",
        "formula_es": "Other Current Assets = Total Current Assets − (Cash + ST Inv. + AR + Inventories).",
        "concepts": ["OtherAssetsCurrent", "PrepaidExpenseAndOtherAssetsCurrent", "PrepaidExpenseCurrent"],
    },
    "total_current_assets": {
        "stmt": "balance_sheet",
        "method": "XBRL_CONCEPT",
        "formula_es": "Total de activos corrientes reportado en balance SEC.",
        "concepts": ["AssetsCurrent", "ifrs-full_CurrentAssets"],
    },
    "other_noncurrent_assets": {
        "stmt": "balance_sheet",
        "method": "PLUG_ATTRIBUTION",
        "region": "bs_noncurrent_assets",
        "formula_es": "Other Non-Current Assets = Total Non-Current Assets − (PP&E + ROU + GW/Intang + LT Inv + DTA).",
        "concepts": ["OtherAssetsNoncurrent", "OtherNoncurrentAssets"],
    },
    "total_assets": {
        "stmt": "balance_sheet",
        "method": "XBRL_CONCEPT",
        "formula_es": "Activo total consolidado reportado en balance SEC.",
        "concepts": ["Assets", "TotalAssets", "ifrs-full_Assets"],
    },
    "other_current_liabilities": {
        "stmt": "balance_sheet",
        "method": "PLUG_ATTRIBUTION",
        "region": "bs_current_liabilities",
        "formula_es": "Other Current Liabilities = Total Current Liabilities − (AP + Accrued + Def. Rev. + ST Debt).",
        "concepts": ["OtherLiabilitiesCurrent", "AccruedAndOtherCurrentLiabilities"],
    },
    "other_noncurrent_liabilities": {
        "stmt": "balance_sheet",
        "method": "PLUG_ATTRIBUTION",
        "region": "bs_noncurrent_liabilities",
        "formula_es": "Other Non-Current Liabilities = Total Non-Current Liabilities − (LT Debt + Lease NC + DTL NC).",
        "concepts": ["OtherLiabilitiesNoncurrent", "OtherNoncurrentLiabilities"],
    },
    "total_liabilities": {
        "stmt": "balance_sheet",
        "method": "XBRL_CONCEPT",
        "formula_es": "Pasivo total consolidado reportado (Liabilities).",
        "concepts": ["Liabilities", "TotalLiabilities", "ifrs-full_Liabilities"],
    },
    "mezzanine_equity": {
        "stmt": "balance_sheet",
        "method": "XBRL_CONCEPT",
        "formula_es": "Patrimonio temporal / Participaciones no controladoras rescatables fuera del patrimonio permanente (ASC 480).",
        "concepts": ["RedeemableNoncontrollingInterestEquityCarryingAmount", "RedeemableNoncontrollingInterestEquityPreferred", "TemporaryEquityCarryingAmountAttributableToParent", "TemporaryEquityCarryingAmountIncludingPortionAttributableToNoncontrollingInterests"],
    },
    "other_equity": {
        "stmt": "balance_sheet",
        "method": "PLUG_ATTRIBUTION",
        "region": "bs_equity",
        "formula_es": "Other Equity / AOCI / NCI = Total Stockholders' Equity − (Common Stock & APIC + Retained Earnings).",
        "concepts": ["AccumulatedOtherComprehensiveIncomeLossNetOfTax", "TreasuryStockValue", "NonredeemableNoncontrollingInterest", "MinorityInterest"],
    },
    "stockholders_equity": {
        "stmt": "balance_sheet",
        "method": "XBRL_CONCEPT",
        "formula_es": "Patrimonio neto total (incluyendo NCI permanente si forma parte de Total Equity).",
        "concepts": ["StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest", "StockholdersEquity", "ifrs-full_Equity", "TotalEquity"],
    },
    "total_liab_and_equity": {
        "stmt": "balance_sheet",
        "method": "IDENTITY",
        "formula_es": "Total Liabilities & Equity = Total Liabilities + Mezzanine Equity + Stockholders' Equity.",
        "components": ["total_liabilities", "mezzanine_equity", "stockholders_equity"],
        "concepts": ["LiabilitiesAndStockholdersEquity"],
    },
    "other_assets_sectoral": {
        "stmt": "balance_sheet",
        "method": "PLUG_ATTRIBUTION",
        "region": "bs_all_assets",
        "formula_es": "Otros Activos (Banca/Seguros) = Total Assets − Activos principales sectoriales.",
        "concepts": ["OtherAssets", "AccruedInvestmentIncomeReceivable"],
    },
    "other_liabilities_sectoral": {
        "stmt": "balance_sheet",
        "method": "PLUG_ATTRIBUTION",
        "region": "bs_all_liabilities",
        "formula_es": "Otros Pasivos (Banca/Seguros) = Total Liabilities − Pasivos principales sectoriales.",
        "concepts": ["OtherLiabilities"],
    },
    # --- Cash Flow Statement ---
    "da": {
        "stmt": "cash_flow_statement",
        "method": "XBRL_CONCEPT",
        "formula_es": "Depreciación y amortización sin salida de efectivo añadida al flujo operativo.",
        "concepts": ["DepreciationDepletionAndAmortization", "DepreciationAndAmortization", "Depreciation", "ifrs-full_AdjustmentsForDepreciationAndAmortisationExpense"],
    },
    "sbc": {
        "stmt": "cash_flow_statement",
        "method": "XBRL_CONCEPT",
        "formula_es": "Compensación basada en acciones añadida en el flujo operativo.",
        "concepts": ["ShareBasedCompensation", "AllocatedShareBasedCompensationExpense", "ifrs-full_AdjustmentsForSharebasedPayments"],
    },
    "other_noncash": {
        "stmt": "cash_flow_statement",
        "method": "PLUG_ATTRIBUTION",
        "region": "cf_operating_noncash",
        "formula_es": "Other Non-Cash Items = CFO − (Net Income + D&A + SBC + Deferred Taxes + Working Capital + Banking CF).",
        "concepts": ["OtherNoncashIncomeExpense", "AssetImpairmentCharges", "GainLossOnInvestments", "UnrealizedGainLossOnInvestments"],
    },
    "wc_other": {
        "stmt": "cash_flow_statement",
        "method": "PLUG_ATTRIBUTION",
        "region": "cf_operating_wc",
        "formula_es": "Variación neta en otros activos y pasivos operativos del capital de trabajo (CFO).",
        "concepts": ["IncreaseDecreaseInOtherOperatingAssets", "IncreaseDecreaseInOtherOperatingLiabilities", "IncreaseDecreaseInAccruedLiabilities", "IncreaseDecreaseInOperatingCapital"],
    },
    "cfo": {
        "stmt": "cash_flow_statement",
        "method": "XBRL_CONCEPT",
        "formula_es": "Flujo neto de efectivo generado por actividades operativas (CFO).",
        "concepts": ["NetCashProvidedByUsedInOperatingActivities", "CashFlowsFromUsedInOperatingActivities", "ifrs-full_CashFlowsFromUsedInOperatingActivities"],
    },
    "capex": {
        "stmt": "cash_flow_statement",
        "method": "XBRL_CONCEPT",
        "formula_es": "Pagos por adquisición de Propiedad, Planta y Equipo / Software capitalizado (CapEx).",
        "concepts": ["PaymentsToAcquirePropertyPlantAndEquipment", "CapitalExpenditures", "ifrs-full_PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities"],
    },
    "other_investing": {
        "stmt": "cash_flow_statement",
        "method": "PLUG_ATTRIBUTION",
        "region": "cf_investing",
        "formula_es": "Other Investing = CFI − (−CapEx − M&A − Purchases of Inv. + Sales/Maturities of Inv.).",
        "concepts": ["PaymentsForProceedsFromOtherInvestingActivities"],
    },
    "cfi": {
        "stmt": "cash_flow_statement",
        "method": "XBRL_CONCEPT",
        "formula_es": "Flujo neto de efectivo de actividades de inversión (CFI).",
        "concepts": ["NetCashProvidedByUsedInInvestingActivities", "CashFlowsFromUsedInInvestingActivities", "ifrs-full_CashFlowsFromUsedInInvestingActivities"],
    },
    "other_financing": {
        "stmt": "cash_flow_statement",
        "method": "PLUG_ATTRIBUTION",
        "region": "cf_financing",
        "formula_es": "Other Financing = CFF − (Debt Issued − Debt Repaid + Stock Issued − Buybacks − Dividends).",
        "concepts": ["ProceedsFromPaymentsForOtherFinancingActivities", "PaymentsForProceedsFromOtherFinancingActivities"],
    },
    "cff": {
        "stmt": "cash_flow_statement",
        "method": "XBRL_CONCEPT",
        "formula_es": "Flujo neto de efectivo de actividades de financiación (CFF).",
        "concepts": ["NetCashProvidedByUsedInFinancingActivities", "CashFlowsFromUsedInFinancingActivities", "ifrs-full_CashFlowsFromUsedInFinancingActivities"],
    },
    "fcf": {
        "stmt": "cash_flow_statement",
        "method": "IDENTITY",
        "formula_es": "Free Cash Flow (FCF) = Operating Cash Flow (CFO) − |CapEx|.",
        "components": ["cfo", "capex"],
        "concepts": [],
    },
}

# Conceptos base ya asignados a partidas explícitas (se excluyen de "no mapeados" cuando no corresponden al cajón "Otros")
_CORE_CLAIMED_BY_STMT = {
    "income_statement": {
        "revenues", "revenuefromcontractwithcustomerexcludingassessedtax", "salesrevenuenet",
        "totalrevenuesandotherincome", "revenue", "revenuesnetofinterestexpense",
        "costofgoodsandservicessold", "costofrevenue", "costofgoodssold", "costofpurchasedgoodsandservices",
        "costofgoodsandserviceexcludingdepreciationdepletionandamortization", "costofsales",
        "grossprofit", "researchanddevelopmentexpense", "technologyandcontentexpense",
        "technologyanddevelopmentexpense", "researchanddevelopmentexpensesoftware",
        "sellinggeneralandadministrativeexpense", "sellinggeneralandadministrative",
        "sellingandmarketingexpense", "marketingexpense", "generalandadministrativeexpense",
        "generaladministrativeexpense", "provisionforloanlosses", "provisionforloanleaseandotherlosses",
        "provisionforcreditlosses", "operatingexpenses", "costsandexpenses", "operatingincomeloss",
        "profitlossfromoperatingactivities", "interestanddividendincomeoperating",
        "investmentincomeinterestanddividend", "interestincomeexpensenet", "interestincomeother",
        "interestexpense", "interestexpensedebt", "interestanddebtexpense",
        "incomelossfromcontinuingoperationsbeforeincometaxesextraordinaryitemsnoncontrollinginterest",
        "incomelossfromcontinuingoperationsbeforeincometaxesminorityinterestandincomelossfromequitymethodinvestments",
        "profitlossbeforetax", "incometaxexpensebenefit", "incometaxexpensecontinuingoperations",
        "interestexpensenonoperating", "investmentincomeinterest", "interestincomeexpensenonoperatingnet",
        "netincomeloss", "profitloss", "netincomelossattributabletononcontrollinginterest",
        "profitlossattributabletononcontrollinginterests",
        "preferredstockdividendsincomestatementimpact", "netincomelossavailabletocommonstockholdersbasic",
        "earningspersharebasic", "earningspersharediluted",
        "weightedaveragenumberofsharesoutstandingbasic", "weightedaveragenumberofdilutedsharesoutstanding",
    },
    "balance_sheet": {
        "cashandcashequivalentsatcarryingvalue", "cash", "cashandcashequivalents",
        "cashcashequivalentsrestrictedcashandrestrictedcashequivalents",
        "marketablesecuritiescurrent", "shortterminvestments", "availableforsalesecuritiesdebtsecuritiescurrent",
        "accountsreceivablenetcurrent", "receivablesnetcurrent", "accountsnotesandloansreceivablenetcurrent",
        "tradeandothercurrentreceivables", "inventorynet", "inventories", "assetscurrent", "currentassets",
        "propertyplantandequipmentnet", "propertyplantandequipmentandfinanceleaserightofuseassetafteraccumulateddepreciationandamortization",
        "operatingleaserightofuseasset", "goodwill", "intangibleassetsnetexcludinggoodwill",
        "intangibleassetsnetexcludinggoodwillnoncurrent", "intangibleassetexcludinggoodwillafteraccumulatedamortizationnoncurrent",
        "finitelivedintangibleassetsnet",
        "goodwillandintangibleassetsnet", "marketablesecuritiesnoncurrent",
        "availableforsaledebtsecuritiesnoncurrent", "equitymethodinvestments", "longterminvestments",
        "deferredincometaxassetsnet", "deferredtaxassetsnetnoncurrent", "assetsnoncurrent", "assets", "totalassets",
        "accountspayablecurrent", "accountspayabletradecurrent", "accountspayableandaccruedliabilitiescurrent",
        "accruedliabilitiescurrent", "deferredrevenuecurrent", "contractwithcustomerliabilitycurrent",
        "longtermdebtcurrent", "commercialpaper", "shorttermborrowings", "debtcurrent", "liabilitiescurrent",
        "longtermdebtnoncurrent", "longtermdebtandcapitalleaseobligationsnoncurrent", "longtermdebt",
        "operatingleaseliabilitynoncurrent", "deferredtaxliabilitiesnoncurrent", "deferredincometaxliabilitiesnetnoncurrent",
        "liabilitiesnoncurrent", "liabilities", "totalliabilities",
        "commonstocksincludingadditionalpaidincapital", "commonstockvalue",
        "additionalpaidincapital", "retainedearningsaccumulateddeficit", "retainedearnings",
        "stockholdersequityincludingportionattributabletononcontrollinginterest", "stockholdersequity",
        "totalequity", "equity", "liabilitiesandstockholdersequity",
        "nonredeemablenoncontrollinginterest", "noncontrollinginterest",
        "redeemablenoncontrollinginterestequitycarryingamount", "redeemablenoncontrollinginterestequitypreferred",
        "temporaryequitycarryingamountattributabletoparent",
        # Sectoriales bancarios ya mapeados en campos explícitos de Banca
        "cashandduefrombanks", "debtsecuritiesnetcarryingamount",
        "debtsecuritiesavailableforsaleexcludingaccruedinterest",
        "debtsecuritiesheldtomaturityexcludingaccruedinterestafterallowanceforcreditloss",
        "financingreceivableexcludingaccruedinterestafterallowanceforcreditloss",
        "financingreceivableexcludingaccruedinterestbeforeallowanceforcreditlossesnetofdeferredincome",
        "financingreceivableallowanceforcreditlossexcludingaccruedinterest",
        "loansandleasesreceivablenetreportedamount",
        "deposits", "noninterestbearingdepositliabilities", "interestbearingdepositliabilities",
    },
    "cash_flow_statement": {
        "netincomeloss", "profitloss", "depreciationdepletionandamortization", "depreciationandamortization",
        "depreciationamortizationandaccretionnet", "depreciation", "amortizationofintangibleassets",
        "sharebasedcompensation", "allocatedsharebasedcompensationexpense",
        "deferredincometaxexpensebenefit", "deferredincometaxesandtaxcredits",
        "provisionforloanleaseandotherlosses", "provisionforcreditlosses",
        "increasedecreaseinaccountsreceivable", "increasedecreaseinotherreceivables",
        "increasedecreaseininventories", "increasedecreaseinaccountspayable",
        "increasedecreaseinaccountspayabletrade",
        "netcashprovidedbyusedinoperatingactivities", "cashflowsfromusedinoperatingactivities",
        "netcashprovidedbyoperatingactivities",
        "paymentstoacquirepropertyplantandequipment", "capitalexpenditures",
        "paymentstoacquirebusinessesnetofcashacquired", "paymentstoacquiremarketablesecurities",
        "paymentstoacquireavailableforsalesecuritiesdebt", "paymentstoacquireinvestments",
        "proceedsfromsaleandmaturityofmarketablesecurities", "proceedsfromsaleofavailableforsalesecuritiesdebt",
        "proceedsfrommaturitiesprepaymentsandcallsofavailableforsalesecurities",
        "proceedsfromsalematurityandcollectionsofinvestments",
        "netcashprovidedbyusedininvestingactivities", "cashflowsfromusedininvestingactivities",
        "proceedsfromissuanceoflongtermdebt", "repaymentsoflongtermdebt",
        "proceedsfromissuanceofcommonstock",
        "paymentsforrepurchaseofcommonstock", "paymentsofdividends", "paymentsofdividendscommonstock",
        "paymentsrelatedtotaxwithholdingforsharebasedcompensation",
        "netcashprovidedbyusedinfinancingactivities", "cashflowsfromusedinfinancingactivities",
        "effectofexchangerateoncashcashequivalentsrestrictedcashandrestrictedcashequivalents",
        "effectofexchangerateoncashandcashequivalents",
        "cashcashequivalentsrestrictedcashandrestrictedcashequivalentsperiodincreasedecreaseincludingexchangerateeffect",
        "cashandcashequivalentsperiodincreasedecrease",
    },
}

_BS_EQUITY_START_TOKENS = {
    "commonstocksincludingadditionalpaidincapital", "commonstockvalue", "additionalpaidincapital",
    "retainedearningsaccumulateddeficit", "retainedearnings", "accumulatedothercomprehensiveincomelossnetoftax",
    "treasurystockvalue", "nonredeemablenoncontrollinginterest",
    "redeemablenoncontrollinginterestequitycarryingamount", "redeemablenoncontrollinginterestequitypreferred",
    "temporaryequitycarryingamountattributabletoparent",
    "stockholdersequity", "stockholdersequityincludingportionattributabletononcontrollinginterest", "totalequity", "equity",
}

_CF_SUPPLEMENTAL_TOKENS = {
    "interestpaidnet", "interestpaid", "incometaxespaidnet", "incometaxespaid",
    "rightofuseassetobtainedinexchangeforoperatingleaseliability",
    "cashcashequivalentsrestrictedcashandrestrictedcashequivalents",
    "restrictedcashandcashequivalents", "cashandcashequivalentsatcarryingvalue",
    "marketablesecuritiesreclassifiedtoequitymethodinvestments",
}

_NON_PLUG_LEAF_METRICS = {
    "income_statement": ("cogs", "rd_expense", "sga_expense", "credit_loss_provision", "interest_income", "interest_expense"),
    "balance_sheet": (
        "cash", "short_term_investments", "accounts_receivable", "inventories",
        "net_ppe", "rou_asset", "goodwill_and_intangibles", "long_term_investments", "deferred_tax_assets",
        "accounts_payable", "accrued_liabilities", "deferred_revenue_current",
        "short_term_debt", "long_term_debt", "operating_lease_liability_noncurrent",
        "common_stock_and_apic", "retained_earnings", "mezzanine_equity", "minority_interest",
        "net_loans", "allowance_for_loan_losses", "deposits",
    ),
    "cash_flow_statement": (
        "da", "sbc", "deferred_taxes", "wc_ar", "wc_inv", "wc_ap",
        "capex", "acquisitions_ma", "purchases_investments", "sales_maturities_investments",
        "debt_issued", "debt_repaid", "share_repurchases_open_market", "share_repurchases_sbc_tax",
        "dividends_paid", "fx_effect",
    ),
}


def _clean_tok(text: str) -> str:
    return re.sub(r'[^a-z0-9]', '', str(text or '').split(':')[-1].split('_')[-1].lower())


def _is_non_monetary_row(row: dict) -> bool:
    lbl = (row.get("label") or "").lower()
    conc = _clean_tok(row.get("concept", ""))
    return (
        bool(row.get("is_abstract"))
        or bool(row.get("is_total"))
        or "pershare" in conc
        or "shares" in conc
        or "(in shares)" in lbl
        or "per share" in lbl
    )


def _assign_statement_regions(stmt_name: str, rows: list) -> list[tuple[dict, str]]:
    """Clasifica cada fila de carátula As-Reported en una región contable precisa."""
    out = []
    if stmt_name == "income_statement":
        seen_op_inc = False
        seen_ebt = False
        passed_gp_or_rev = False
        for r in rows:
            tok = _clean_tok(r.get("concept", ""))
            lbl = (r.get("label") or "").lower()
            sec = (r.get("section_path") or "").lower()
            if tok in ("grossprofit", "costofrevenue", "costofgoodsandservicessold", "costofsales", "revenues", "revenuefromcontractwithcustomerexcludingassessedtax"):
                passed_gp_or_rev = True
            if tok in ("operatingincomeloss", "profitlossfromoperatingactivities") or lbl in ("operating income", "income from operations", "operating profit"):
                seen_op_inc = True
            if "beforeincometaxes" in tok or "beforetax" in tok or "before income tax" in lbl or tok in ("incometaxexpensebenefit", "netincomeloss", "profitloss"):
                seen_ebt = True
            if seen_op_inc and not seen_ebt:
                reg = "is_non_operating"
            elif not seen_op_inc and passed_gp_or_rev and ("nonoperating" in sec or "other income" in sec):
                reg = "is_non_operating"
            elif not seen_op_inc and passed_gp_or_rev:
                reg = "is_operating_expense"
            else:
                reg = "is_other"
            out.append((r, reg))
        return out

    if stmt_name == "balance_sheet":
        seen_tca = seen_ta = seen_tcl = seen_tl = False
        _noncurrent_asset_triggers = {
            "propertyplantandequipmentnet", "operatingleaserightofuseasset", "goodwill",
            "intangibleassetsnetexcludinggoodwill", "marketablesecuritiesnoncurrent",
        }
        _noncurrent_liab_triggers = {
            "longtermdebtnoncurrent", "operatingleaseliabilitynoncurrent", "deferredtaxliabilitiesnoncurrent",
        }
        for r in rows:
            tok = _clean_tok(r.get("concept", ""))
            lbl = (r.get("label") or "").lower()
            sec = (r.get("section_path") or "").lower()
            if tok in ("assetscurrent", "currentassets") or lbl == "total current assets":
                seen_tca = True
            if tok in _noncurrent_asset_triggers or ("noncurrent" in tok and not seen_ta):
                if "liabilities" not in tok and "lease" not in tok:
                    seen_tca = True
            if tok in ("assets", "totalassets") or lbl == "total assets":
                seen_ta = True
            if tok in ("liabilitiescurrent", "currentliabilities") or lbl == "total current liabilities":
                seen_tcl = True
            if tok in _noncurrent_liab_triggers or ("liabilitiesnoncurrent" in tok):
                seen_tcl = True
            if tok in ("liabilities", "totalliabilities") or lbl == "total liabilities":
                seen_tl = True
            if tok in _BS_EQUITY_START_TOKENS or lbl.startswith("total stockholders") or lbl.startswith("total equity"):
                seen_tl = True

            if tok in _BS_EQUITY_START_TOKENS or seen_tl:
                reg = "bs_equity"
            elif not seen_ta and ("current assets" in sec or not seen_tca):
                reg = "bs_current_assets" if not seen_tca else "bs_noncurrent_assets"
            elif not seen_ta:
                reg = "bs_noncurrent_assets"
            elif not seen_tcl and ("current liabilities" in sec or (seen_ta and "non-current" not in sec and "noncurrent" not in sec)):
                reg = "bs_current_liabilities"
            else:
                reg = "bs_noncurrent_liabilities"
            out.append((r, reg))
        return out

    if stmt_name == "cash_flow_statement":
        sec_phase = "cf_operating"
        for r in rows:
            tok = _clean_tok(r.get("concept", ""))
            lbl = (r.get("label") or "").lower()
            sec = (r.get("section_path") or "").lower()
            if any(k in sec for k in ("supplemental", "non-cash", "noncash", "cash paid for")):
                out.append((r, "cf_supplemental"))
                continue
            if tok in _CF_SUPPLEMENTAL_TOKENS:
                out.append((r, "cf_supplemental"))
                continue
            if "investing activities" in sec:
                sec_phase = "cf_investing"
            elif "financing activities" in sec:
                sec_phase = "cf_financing"
            elif "operating activities" in sec:
                sec_phase = "cf_operating"

            if sec_phase == "cf_operating":
                is_wc = (
                    "increasedecreasein" in tok
                    or "working capital" in sec
                    or "operating assets and liabilities" in sec
                    or "changes in" in lbl
                )
                reg = "cf_operating_wc" if is_wc else "cf_operating_noncash"
            else:
                reg = sec_phase

            if tok in ("netcashprovidedbyusedinoperatingactivities", "cashflowsfromusedinoperatingactivities", "netcashprovidedbyoperatingactivities"):
                sec_phase = "cf_investing"
            elif tok in ("netcashprovidedbyusedininvestingactivities", "cashflowsfromusedininvestingactivities"):
                sec_phase = "cf_financing"
            elif tok in (
                "netcashprovidedbyusedinfinancingactivities", "cashflowsfromusedinfinancingactivities",
                "effectofexchangerateoncashcashequivalentsrestrictedcashandrestrictedcashequivalents",
                "effectofexchangerateoncashandcashequivalents",
                "cashcashequivalentsrestrictedcashandrestrictedcashequivalentsperiodincreasedecreaseincludingexchangerateeffect",
                "cashandcashequivalentsperiodincreasedecrease",
            ):
                sec_phase = "cf_fx_and_cash"
            out.append((r, reg))
        return out

    return [(r, "other") for r in rows]


def _matching_regions_for_spec(region: str) -> tuple[str, ...]:
    if region == "bs_all_assets":
        return ("bs_current_assets", "bs_noncurrent_assets")
    if region == "bs_all_liabilities":
        return ("bs_current_liabilities", "bs_noncurrent_liabilities")
    return (region,)


def _find_direct_sources(rows: list, spec_concepts: list[str], period: str) -> list[dict]:
    """Localiza filas exactas As-Reported cuyo concepto XBRL coincide con los candidatos del campo."""
    cand_toks = {_clean_tok(c) for c in spec_concepts if c}
    if not cand_toks:
        return []
    matches = []
    for r in rows:
        if r.get("is_abstract"):
            continue
        tok = _clean_tok(r.get("concept", ""))
        if tok in cand_toks:
            val = (r.get("values") or {}).get(period)
            if val is not None:
                matches.append({
                    "concept": r.get("concept", ""),
                    "raw_label": r.get("label", ""),
                    "spanish_label": r.get("spanish_label", ""),
                    "section_path": r.get("section_path", ""),
                    "is_extension_tag": bool(r.get("is_extension_tag", False)),
                    "val_usd": float(val),
                })
    return matches


def _explain_plug_from_unmapped(
    stmt_name: str,
    region: str,
    tagged_rows: list[tuple[dict, str]],
    period: str,
    target_val: float,
    claimed_leaf_vals: set[float] | None = None,
) -> dict:
    """Atribuye automáticamente un cajón 'Otros' a las filas no mapeadas de su misma sección SEC."""
    claimed = _CORE_CLAIMED_BY_STMT.get(stmt_name, set())
    valid_regions = _matching_regions_for_spec(region)
    claimed_vals = claimed_leaf_vals or set()
    items = []
    for r, reg in tagged_rows:
        if reg not in valid_regions or _is_non_monetary_row(r):
            continue
        tok = _clean_tok(r.get("concept", ""))
        if tok in claimed:
            continue
        raw_v = (r.get("values") or {}).get(period)
        if raw_v is None or float(raw_v) == 0.0:
            continue
        abs_v = round(abs(float(raw_v)), 2)
        if abs_v >= 1.0 and abs_v in claimed_vals and not tok.startswith("other"):
            continue
        # Excluir también líneas 'otheraccrued*' / composite si su valor exacto ya está reclamado en el campo canónico nombrado
        if abs_v >= 1.0 and abs_v in claimed_vals and "accrued" in tok and "otherliabilities" not in tok:
            continue
        items.append({
            "concept": r.get("concept", ""),
            "raw_label": r.get("label", ""),
            "spanish_label": r.get("spanish_label", ""),
            "section_path": r.get("section_path", ""),
            "is_extension_tag": bool(r.get("is_extension_tag", False)),
            "val_usd": float(raw_v),
        })

    explained_sum = round(sum(it["val_usd"] for it in items), 2)
    if items and target_val != 0 and abs(target_val + explained_sum) < abs(target_val - explained_sum):
        for it in items:
            it["val_usd"] = round(-it["val_usd"], 2)
        explained_sum = round(-explained_sum, 2)

    residual = round(float(target_val) - explained_sum, 2)
    return {
        "sources": items,
        "explained_sum_usd": explained_sum,
        "residual_unexplained_usd": residual,
    }


def _build_ltm_bridge_payload(full_dataset: dict, stmt_name: str, metric_key: str, resolved_series: dict) -> dict | None:
    """Construye el puente matemático LTM desde `period_filing_map` y series resueltas."""
    pf_map = full_dataset.get("period_filing_map") or {}
    ltm_info = pf_map.get("LTM")
    if not isinstance(ltm_info, dict) or not ltm_info:
        return None
    ltm_val = resolved_series.get("LTM")
    if ltm_val is None:
        return None
    if stmt_name == "balance_sheet":
        return {
            "mode": "MRQ_STOCK",
            "mrq_period": ltm_info.get("ytd_curr") or ltm_info.get("period_label") or "MRQ",
            "accession": ltm_info.get("ytd_accession") or ltm_info.get("accession"),
            "ltm_val": ltm_val,
        }
    base_fy = ltm_info.get("base_fy")
    return {
        "mode": ltm_info.get("method", "FY_PLUS_YTD_MINUS_PRIOR_YTD"),
        "base_fy": base_fy,
        "base_fy_val": resolved_series.get(base_fy) if base_fy else None,
        "base_accession": ltm_info.get("base_accession"),
        "ytd_curr": ltm_info.get("ytd_curr"),
        "ytd_prev": ltm_info.get("ytd_prev"),
        "ytd_accession": ltm_info.get("ytd_accession"),
        "ltm_val": ltm_val,
    }


def build_resolved_canonical_lineage(
    full_dataset: dict,
    bs_resolved: dict,
    is_resolved: dict,
    cf_resolved: dict,
    periods: list[str],
) -> dict:
    """Genera el diccionario compacto `resolved_canonical_lineage` para auditoría y Evidence Drawer."""
    as_rep = full_dataset.get("as_reported_statements", {})
    archetype = full_dataset.get("archetype", "STANDARD_CORPORATE")
    stmt_resolved = {
        "balance_sheet": bs_resolved,
        "income_statement": is_resolved,
        "cash_flow_statement": cf_resolved,
    }
    tagged_by_stmt = {
        s_name: _assign_statement_regions(s_name, as_rep.get(s_name, []))
        for s_name in stmt_resolved
    }
    _banking_skip_plugs = {"other_current_assets", "other_noncurrent_assets", "other_current_liabilities", "other_noncurrent_liabilities"}

    lineage = {}
    for metric_key, spec in CANONICAL_LINEAGE_SPECS.items():
        if archetype == "FINANCIAL_BANKING" and metric_key in _banking_skip_plugs:
            continue
        s_name = spec["stmt"]
        resolved_dict = stmt_resolved.get(s_name, {})
        series = resolved_dict.get(metric_key)
        if not isinstance(series, dict):
            continue

        metric_entry = {
            "statement": s_name,
            "method": spec["method"],
            "formula_display": spec["formula_es"],
            "periods": {},
        }
        rows = as_rep.get(s_name, [])
        leaf_keys = _NON_PLUG_LEAF_METRICS.get(s_name, ())
        for p in periods:
            val = series.get(p)
            if val is None:
                continue
            p_entry = {"value_usd": float(val)}
            if spec["method"] == "PLUG_ATTRIBUTION":
                claimed_vals = {
                    round(abs(float(resolved_dict[lk][p])), 2)
                    for lk in leaf_keys
                    if isinstance(resolved_dict.get(lk), dict)
                    and resolved_dict[lk].get(p) is not None
                    and abs(float(resolved_dict[lk][p])) >= 1.0
                }
                plug_info = _explain_plug_from_unmapped(
                    s_name, spec["region"], tagged_by_stmt[s_name], p, float(val), claimed_leaf_vals=claimed_vals
                )
                p_entry.update(plug_info)
            else:
                direct_src = _find_direct_sources(rows, spec.get("concepts", []), p)
                p_entry["sources"] = direct_src
                if spec.get("components"):
                    p_entry["components"] = {
                        comp_k: stmt_resolved[s_name].get(comp_k, {}).get(p)
                        for comp_k in spec["components"]
                        if stmt_resolved[s_name].get(comp_k, {}).get(p) is not None
                    }
            if p == "LTM":
                bridge = _build_ltm_bridge_payload(full_dataset, s_name, metric_key, series)
                if bridge:
                    p_entry["ltm_bridge"] = bridge
            metric_entry["periods"][p] = p_entry

        if metric_entry["periods"]:
            lineage[metric_key] = metric_entry

    return lineage


def resolve_canonical_balance_sheet_with_lineage(fs, periods, archetype="STANDARD_CORPORATE"):
    """Resuelve Balance Canónico y devuelve `(resolved_dict, lineage_dict)`."""
    from .canonical_resolvers import resolve_canonical_balance_sheet
    resolved = resolve_canonical_balance_sheet(fs, periods, archetype=archetype)
    lineage = build_resolved_canonical_lineage(fs, resolved, {}, {}, periods)
    bs_lin = {k: v for k, v in lineage.items() if v.get("statement") == "balance_sheet"}
    return resolved, bs_lin


def resolve_canonical_income_statement_with_lineage(fs, periods, archetype="STANDARD_CORPORATE"):
    """Resuelve Income Statement Canónico y devuelve `(resolved_dict, lineage_dict)`."""
    from .canonical_resolvers import resolve_canonical_income_statement
    resolved = resolve_canonical_income_statement(fs, periods, archetype=archetype)
    lineage = build_resolved_canonical_lineage(fs, {}, resolved, {}, periods)
    is_lin = {k: v for k, v in lineage.items() if v.get("statement") == "income_statement"}
    return resolved, is_lin


def resolve_canonical_cash_flow_with_lineage(fs, periods, capital_flows=None, archetype="STANDARD_CORPORATE"):
    """Resuelve Cash Flow Canónico y devuelve `(resolved_dict, lineage_dict)`."""
    from .canonical_resolvers import resolve_canonical_cash_flow
    resolved = resolve_canonical_cash_flow(fs, periods, capital_flows=capital_flows, archetype=archetype)
    lineage = build_resolved_canonical_lineage(fs, {}, {}, resolved, periods)
    cf_lin = {k: v for k, v in lineage.items() if v.get("statement") == "cash_flow_statement"}
    return resolved, cf_lin

