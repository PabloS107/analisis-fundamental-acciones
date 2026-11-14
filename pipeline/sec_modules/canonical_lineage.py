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

# Conceptos sumatorios / totales que nunca deben contarse como componentes residuales individuales
_SUMMARY_AND_TOTAL_TOKENS = {
    "revenues", "revenuefromcontractwithcustomerexcludingassessedtax", "salesrevenuenet",
    "totalrevenuesandotherincome", "revenue", "revenuesnetofinterestexpense", "noninterestincome",
    "grossprofit", "ifrsfullgrossprofit", "operatingexpenses", "costsandexpenses",
    "operatingexpense", "ifrsfulloperatingexpense", "benefitslossesandexpenses", "noninterestexpense",
    "operatingincomeloss", "profitlossfromoperatingactivities", "operatingincome",
    "nonoperatingincomeexpense", "nonoperatingincomeexpensenet",
    "incomelossfromcontinuingoperationsbeforeincometaxesextraordinaryitemsnoncontrollinginterest",
    "incomelossfromcontinuingoperationsbeforeincometaxesminorityinterestandincomelossfromequitymethodinvestments",
    "incomelossbeforeincometaxexpensebenefit", "incomelossattributabletoparent", "profitlossbeforetax",
    "netincomeloss", "profitloss", "ifrsfullprofitloss",
    "netincomelossavailabletocommonstockholdersbasic", "profitlossattributabletoownersofparent",
    "assetscurrent", "currentassetstotal", "currentassets", "ifrsfullcurrentassets",
    "assetsnoncurrent", "assets", "totalassets", "ifrsfullassets",
    "liabilitiescurrent", "currentliabilitiestotal", "currentliabilities", "ifrsfullcurrentliabilities",
    "liabilitiesnoncurrent", "liabilities", "totalliabilities", "ifrsfullliabilities",
    "stockholdersequity", "stockholdersequityincludingportionattributabletononcontrollinginterest",
    "totalequity", "equity", "ifrsfullequity", "liabilitiesandstockholdersequity",
    "equityattributabletoownersofparent",
    "netcashprovidedbyusedinoperatingactivities", "cashflowsfromusedinoperatingactivities",
    "netcashprovidedbyoperatingactivities", "ifrsfullcashflowsfromusedinoperatingactivities",
    "netcashprovidedbyusedininvestingactivities", "cashflowsfromusedininvestingactivities",
    "ifrsfullcashflowsfromusedininvestingactivities",
    "netcashprovidedbyusedinfinancingactivities", "cashflowsfromusedinfinancingactivities",
    "ifrsfullcashflowsfromusedinfinancingactivities",
    "cashcashequivalentsrestrictedcashandrestrictedcashequivalents",
    "cashcashequivalentsrestrictedcashandrestrictedcashequivalentsperiodincreasedecreaseincludingexchangerateeffect",
    "cashcashequivalentsrestrictedcashandrestrictedcashequivalentsperiodincreasedecreaseexcludingexchangerateeffect",
    "cashandcashequivalentsperiodincreasedecrease",
    "adjustmentsforreconcileprofitloss", "ifrsfulladjustmentsforreconcileprofitloss",
    "investments", "realestateinvestmentpropertyatcost",
    "financialassetsatfairvaluethroughprofitorloss", "ifrsfullfinancialassetsatfairvaluethroughprofitorloss",
    "financialassetsatamortisedcost", "ifrsfullfinancialassetsatamortisedcost",
    "financialliabilitiesatamortisedcost", "ifrsfullfinancialliabilitiesatamortisedcost",
}

# Tokens explícitos asociados a cada métrica canónica (usado para exclusión dinámica por cajón y notas XBRL)
_CONCEPTS_BY_METRIC = {
    # Income Statement
    "revenue": {
        "revenues", "revenuefromcontractwithcustomerexcludingassessedtax", "salesrevenuenet",
        "totalrevenuesandotherincome", "revenue", "ifrsfullrevenue", "revenuesnetofinterestexpense",
    },
    "cogs": {
        "costofgoodsandservicessold", "costofrevenue", "costofgoodssold", "costofpurchasedgoodsandservices",
        "costofgoodsandserviceexcludingdepreciationdepletionandamortization", "costofsales", "ifrsfullcostofsales",
    },
    "gross_profit": {"grossprofit", "ifrsfullgrossprofit"},
    "rd_expense": {
        "researchanddevelopmentexpense", "technologyandcontentexpense", "technologyanddevelopmentexpense",
        "researchanddevelopmentexpensesoftware", "researchanddevelopmentexpenseexcludingacquiredinprocesscost",
    },
    "sga_expense": {
        "sellinggeneralandadministrativeexpense", "sellinggeneralandadministrative", "sellingandmarketingexpense",
        "marketingexpense", "marketingandadvertisingexpense", "sellingexpense", "advertisingexpense",
        "generalandadministrativeexpense", "generaladministrativeexpense", "administrativeexpense",
    },
    "credit_loss_provision": {
        "provisionforloanlosses", "provisionforloanleaseandotherlosses", "provisionforcreditlosses",
        "expectedcreditloss", "provisionforloanlossesexpensed", "provisionfordoubtfulaccounts",
        "creditlossallowanceexpenses1",
        "additionalallowancerecognisedinprofitorlossallowanceaccountforcreditlossesoffinancialassets",
    },
    "interest_income": {
        "interestanddividendincomeoperating", "investmentincomeinterestanddividend", "interestincomeexpensenet",
        "interestincomeother", "investmentincomeinterest", "interestincome", "interestincomeoperating",
        "revenuefrominterest", "ifrsfullrevenuefrominterest", "incomeexpensegainsorlossesoffinancialinstruments",
        "interestincomebank",
    },
    "interest_expense": {
        "interestexpense", "interestexpensedebt", "interestanddebtexpense", "interestexpensenonoperating",
        "interestexpenseoperating", "interestexpenseandotherfinancialcharges",
    },
    "share_of_associates": {
        "shareoflossinassociates", "shareofprofitlossofassociatesandjointventuresaccountedforusingequitymethod",
        "incomelossfromequitymethodinvestments", "equityinearningsofunconsolidatedentitynetoftax",
        "equityinearningsofunconsolidatedentity", "equityinearningslossofunconsolidatedentity",
        "equityinlossofunconsolidatedentity",
    },
    "income_tax": {
        "incometaxexpensebenefit", "incometaxexpensecontinuingoperations", "incometaxinstatementofprofitorloss",
        "currentincometaxexpensebenefit", "ifrsfullincometaxexpensecontinuingoperations",
    },
    # Balance Sheet
    "cash": {
        "cashandcashequivalentsatcarryingvalue", "cashandcashequivalents", "cash", "cashandduefrombanks",
        "cashcashequivalentsrestrictedcashandrestrictedcashequivalents", "ifrsfullcashandcashequivalents",
    },
    "short_term_investments": {
        "marketablesecuritiescurrent", "shortterminvestments", "availableforsalesecuritiescurrent",
        "availableforsalesecuritiesdebtsecuritiescurrent", "debtsecuritiescurrent", "equitysecuritiesfvni",
        "marketablesecuritiesandequitysecuritiesfvni", "othershortterminvestments", "marketablesecurities",
        "debtsecuritiesavailableforsaleexcludingaccruedinterest",
        "debtsecuritiesheldtomaturityexcludingaccruedinterestafterallowanceforcreditloss",
        "debtsecuritiesavailableforsale", "debtsecuritiesheldtomaturity", "debtsecuritiesnetcarryingamount",
        "availableforsalesecuritiesdebtsecurities", "availableforsalesecurities",
        "debtsecuritiesavailableforsalefixedmaturities",
        "financialassetsatfairvaluethroughprofitorloss", "ifrsfullfinancialassetsatfairvaluethroughprofitorloss",
        "financialassetsatfairvaluethroughothercomprehensiveincome",
        "ifrsfullfinancialassetsatfairvaluethroughothercomprehensiveincome",
    },
    "accounts_receivable": {
        "accountsreceivablenetcurrent", "accountsreceivablenet", "receivablesnetcurrent",
        "accountsnotesandloansreceivablenetcurrent", "accountsandnotesreceivablenetcurrent",
        "tradeandotherreceivablescurrent", "tradeandothercurrentreceivables",
        "contractwithcustomerassetnetcurrent", "unbilledreceivablescurrent", "nontradereceivablescurrent",
    },
    "inventories": {"inventorynet", "inventories", "inventorygross"},
    "net_ppe": {
        "propertyplantandequipmentnet",
        "propertyplantandequipmentandfinanceleaserightofuseassetafteraccumulateddepreciationandamortization",
        "propertyplantandequipmentandoperatingleaserightofuseassetafteraccumulateddepreciationandamortization",
        "propertyplantandequipmentnetofaccumulateddepreciationandamortization",
        "propertyplantandequipmentnetexcludingrightofuseasset", "propertyplantandequipmentgross",
        "machineryandequipmentnet", "constructioninprogressgross", "constructioninprogress",
        "buildingsandbuildingimprovementsnet", "realestateinvestmentpropertynet", "investmentproperties",
        "land", "investmentbuildingandbuildingimprovements", "realestateinvestmentpropertyaccumulateddepreciation",
    },
    "rou_asset": {
        "operatingleaserightofuseasset", "rightofuseassets", "rightofuseasset", "financeleaserightofuseasset",
        "lesseeoperatingleaserightofuseasset", "operatingleaserightofuseassetnet", "financeleaserightofuseassetnet",
    },
    "goodwill_and_intangibles": {
        "goodwill", "intangibleassetsnetexcludinggoodwill", "intangibleassetsnetexcludinggoodwillnoncurrent",
        "intangibleassetexcludinggoodwillafteraccumulatedamortizationnoncurrent", "finitelivedintangibleassetsnet",
        "goodwillandintangibleassetsnet", "intangibleassetsnet", "otherintangibleassetsnet",
        "intangibleassetsnetnoncurrent", "intangibleassetsotherthangoodwill",
        "ifrsfullintangibleassetsotherthangoodwill",
    },
    "long_term_investments": {
        "marketablesecuritiesnoncurrent", "availableforsaledebtsecuritiesnoncurrent", "equitymethodinvestments",
        "longterminvestments", "nonmarketableequitysecuritiescarryingvalue",
        "equitysecuritieswithoutreadilydeterminablefairvalueamount", "equitysecuritiesfvninoncurrent",
        "otherinvestmentsnoncurrent", "investmentsinassociates",
        "investmentsinaffiliatessubsidiariesassociatesandjointventures",
        "heldtomaturitysecuritiesnoncurrent", "otherlongterminvestments", "otherinvestments",
    },
    "deferred_tax_assets": {"deferredincometaxassetsnet", "deferredtaxassetsnetnoncurrent", "deferredincometaxassets"},
    "accounts_payable": {
        "accountspayablecurrent", "accountspayabletradecurrent", "accountspayableandaccruedliabilitiescurrent",
        "tradeandotherpayablescurrent",
    },
    "accrued_liabilities": {
        "accruedliabilitiescurrent", "accruedliabilitiesandotherliabilitiescurrent",
        "otheraccruedliabilitiescurrent", "accruedliabilities",
    },
    "deferred_revenue_current": {
        "deferredrevenuecurrent", "contractwithcustomerliabilitycurrent", "deferredrevenueandothercurrentliabilities",
    },
    "short_term_debt": {
        "longtermdebtcurrent", "commercialpaper", "shorttermborrowings", "debtcurrent",
        "currentportionoflongtermdebt", "shorttermdebt", "loanspayablecurrent", "linesofcreditcurrent",
        "revolvingcreditfacilityandcommercialpaper", "lineofcreditandcommercialpaper", "lineofcredit",
        "currentborrowingsandotherfinancialliabilities", "currentportionofnoncurrentborrowings",
        "currentfinancialliabilities", "borrowingsfromfinancialinstitutions",
    },
    "long_term_debt": {
        "longtermdebtnoncurrent", "longtermdebtandcapitalleaseobligationsnoncurrent", "longtermdebt",
        "longtermloanspayable", "notespayable", "loanspayable", "secureddebt", "seniornotes",
        "seniorlongtermdebt", "noncurrentborrowings", "noncurrentfinancialliabilities",
        "debtsecuritiesinissue", "borrowings", "borrowingsandfinancing", "subordinateddebt",
    },
    "total_debt": {"debtlongtermandshorttermcombinedamount", "totaldebt"},
    "operating_lease_liability_noncurrent": {"operatingleaseliabilitynoncurrent", "capitalleaseobligationsnoncurrent"},
    "deferred_tax_liabilities_noncurrent": {
        "deferredtaxliabilitiesnoncurrent", "deferredincometaxliabilitiesnetnoncurrent",
        "deferredincometaxliabilitiesnet", "deferredtaxliabilities",
        "deferredincometaxesandotherliabilitiesnoncurrent",
    },
    "common_stock_and_apic": {
        "commonstocksincludingadditionalpaidincapital", "commonstocksandadditionalpaidincapital",
        "commonstockvalue", "additionalpaidincapital", "issuedcapital", "sharepremium",
        "ifrsfullissuedcapital", "ifrsfullsharepremium",
    },
    "retained_earnings": {
        "retainedearningsaccumulateddeficit", "retainedearnings", "ifrsfullretainedearnings",
        "accumulatedgains", "accumulatedgainlosses", "accumulatedlosses", "totalaccumulatedlosses",
    },
    "mezzanine_equity": {
        "redeemablenoncontrollinginterestequitycarryingamount", "redeemablenoncontrollinginterestequitypreferred",
        "temporaryequitycarryingamountattributabletoparent",
        "temporaryequitycarryingamountincludingportionattributabletononcontrollinginterests",
    },
    "minority_interest": {
        "nonredeemablenoncontrollinginterest", "noncontrollinginterest", "minorityinterest", "noncontrollinginterests",
    },
    "net_loans": {
        "loansandleasesreceivablenetofdeferredincome",
        "financingreceivableexcludingaccruedinterestafterallowanceforcreditloss",
        "financingreceivableexcludingaccruedinterestbeforeallowanceforcreditlossesnetofdeferredincome",
        "loansandadvancestocustomers", "ifrsfullloansandadvancestocustomers",
        "creditcardreceivables1", "loansandadvancestocustomers1",
        "loansandleasesreceivablenetreportedamount", "loansreceivablenet",
    },
    "allowance_for_loan_losses": {
        "financingreceivableallowanceforcreditlossexcludingaccruedinterest",
        "financingreceivableallowanceforcreditlosses",
        "allowanceforcreditlossesonfinancingreceivables",
        "allowanceaccountforcreditlossesoffinancialassets",
        "ifrsfullallowanceaccountforcreditlossesoffinancialassets",
        "loansandleasesreceivableallowance", "allowanceforloanandleaselosses",
        "creditcardexpectedcreditloss", "loansexpectedcreditloss", "allowanceforexpectedcreditlosses",
    },
    "deposits": {
        "deposits", "depositsfromcustomers", "ifrsfulldepositsfromcustomers", "depositsdomestic",
        "noninterestbearingdepositliabilities", "interestbearingdepositliabilities",
    },
    "premiums_receivable": {
        "premiumsreceivableatcarryingvalue", "accountsandotherreceivablesnetcurrent", "accountsreceivablenet",
    },
    "deferred_policy_acquisition_costs": {"deferredpolicyacquisitioncosts", "deferredpolicyacquisitioncostamortizationexpense"},
    "loss_reserves": {
        "liabilityforclaimsandclaimsadjustmentexpense", "liabilityforunpaidclaimsandclaimsadjustmentexpensenet",
        "liabilityforclaimsandclaimsadjustmentexpenseincurredclaims1",
    },
    "unearned_premiums": {"unearnedpremiums", "unearnedpremiumsnet"},
    # Cash Flow Statement
    "da": {
        "depreciationdepletionandamortization", "depreciationandamortization",
        "depreciationamortizationandaccretionnet", "depreciation", "amortizationofintangibleassets",
        "depreciationandamortizationincludingamountfromotherincomeexpense",
        "adjustmentsfordepreciationandamortisationexpense", "ifrsfulladjustmentsfordepreciationandamortisationexpense",
    },
    "sbc": {
        "sharebasedcompensation", "allocatedsharebasedcompensationexpense",
        "adjustmentsforsharebasedpayments", "ifrsfulladjustmentsforsharebasedpayments",
        "stockoptionplanexpense",
    },
    "deferred_taxes": {
        "deferredincometaxexpensebenefit", "deferredincometaxesandtaxcredits",
        "adjustmentsfordeferredtaxexpense", "ifrsfulladjustmentsfordeferredtaxexpense",
    },
    "credit_loss_provisions": {"provisionforloanleaseandotherlosses", "provisionforcreditlosses"},
    "wc_ar": {"increasedecreaseinaccountsreceivable", "increasedecreaseinotherreceivables"},
    "wc_inv": {"increasedecreaseininventories"},
    "wc_ap": {
        "increasedecreaseinaccountspayable", "increasedecreaseinaccountspayabletrade",
        "increasedecreaseinaccountspayableandaccruedliabilities",
    },
    "banking_loans_cf": {
        "loanstocustomersone", "increasedecreaseinloansandleasesreceivable",
        "adjustmentsfordecreaseincreaseinloansandadvancestocustomers",
        "adjustmentsfordecreaseincreaseinotheroperatingreceivables",
        "ifrsfulladjustmentsfordecreaseincreaseinotheroperatingreceivables",
        "creditcardreceivablescf", "increasedecreaseincreditcardreceivables",
    },
    "banking_deposits_cf": {
        "adjustmentsforincreasedecreaseindepositsfrombanks",
        "ifrsfulladjustmentsforincreasedecreaseindepositsfrombanks",
        "adjustmentsforincreasedecreaseindepositsfromcustomers", "depositscf",
        "increasedecreaseindepositliabilities",
    },
    "capex": {
        "paymentstoacquirepropertyplantandequipment", "capitalexpenditures",
        "purchaseofpropertyplantandequipmentclassifiedasinvestingactivities",
        "ifrsfullpurchaseofpropertyplantandequipmentclassifiedasinvestingactivities",
        "paymentstoacquireproductiveassets", "paymentsforcapitalimprovements",
        "acquisitionanddevelopmentofintangibleassets",
    },
    "acquisitions_ma": {
        "paymentstoacquirebusinessesnetofcashacquired",
        "acquisitionsnetofcashacquiredandpurchasesofintangibleandotherassets",
        "acquisitionsnetofcashacquiredandpurchasesofintangibleassets",
        "paymentstoacquirebusinessesnetofcashacquiredandpurchasesofintangibleandotherassets",
        "paymentstoacquirebusinesstwonetofcashacquired",
        "paymentstoacquirebusinessthreenetofcashacquired",
        "acquisitionofsubsidiarynetofcashacquired",
        "paymentstoacquirebusinessesandinterestinaffiliates",
        "paymentstoacquireotherproductiveassets",
        "cashflowsusedinobtainingcontrolofsubsidiariesorotherbusinesses",
        "paymentstoacquirebusinessesgross",
        "paymentstoacquirebusinessnetofcashacquired",
        "paymentstoacquireinterestinaffiliates",
        "paymentstoacquireinterestinsubsidiariesandotherbusinesses",
        "paymentstoacquirejointventures",
        "paymentstoacquirecommercialrealestate",
        "paymentstoacquireloansreceivable",
        "paymentstoacquireinterestinsubsidiariesandaffiliates",
    },
    "purchases_investments": {
        "paymentstoacquireavailableforsalesecuritiesdebt", "paymentstoacquiremarketablesecurities",
        "paymentstoacquireinvestments", "paymentstoacquireotherinvestments",
        "paymentstoacquireequitysecuritiesfvni", "paymentsforequitysecuritieswithoutreadilydeterminablefairvalue",
        "paymentsforheldforsaleassets", "paymentstoacquireavailableforsalesecurities",
        "paymentstoacquireheldtomaturitysecurities", "paymentstoacquireequitysecurities",
        "othercashpaymentstoacquireequityordebtinstrumentsofotherentitiesclassifiedasinvestingactivities",
        "ifrsfullothercashpaymentstoacquireequityordebtinstrumentsofotherentitiesclassifiedasinvestingactivities",
    },
    "sales_maturities_investments": {
        "proceedsfromsaleofavailableforsalesecuritiesdebt", "proceedsfromsaleofmarketablesecurities",
        "proceedsfrommaturitiesprepaymentsandcallsofavailableforsalesecurities",
        "proceedsfrommaturityofmarketablesecurities", "proceedsfromsaleandmaturityofmarketablesecurities",
        "proceedsfromsaleofavailableforsalesecurities", "proceedsfromsaleofequitysecuritiesfvni",
        "proceedsfromsaleofequitysecurities", "proceedsfrommaturitiesprepaymentsandcallsofheldtomaturitysecurities",
        "proceedsfromsaleandmaturityofavailableforsalesecurities",
        "proceedsfromonetimeventuredistribution", "proceedsfromsaleofpropertyheldforsale",
        "proceedsfromcollectionofnotesreceivable", "proceedsfromdepositsonrealestatesales",
        "proceedsfrominsurancesettlementinvestingactivities", "proceedsfromsalematurityandcollectionsofinvestments",
    },
    "debt_issued": {
        "proceedsfromissuanceoflongtermdebt", "proceedsfromissuanceofdebt",
        "proceedsfromissuanceofseniorlongtermdebt", "proceedsfromissuanceofunsecureddebt",
        "proceedsfromdebtnetofissuancecosts", "proceedsfromlinesofcredit",
        "proceedsfromissuanceofotherlongtermdebt", "proceedsfromborrowingsclassifiedasfinancingactivities",
        "proceedsfromborrowingsandfinancing", "proceedsfromconvertibledebt", "proceedsfromshorttermdebt",
        "proceedsfromdebtinstrumentseligibleascapital", "proceedsfromtermloans",
        "proceedsfromissuanceofconvertibledebt", "proceedsfromissuanceofseniornotes",
        "proceedsfromlongtermlinesofcredit", "proceedsfromnotespayable",
        "proceedsfromissuanceoflongtermdebtandcapitalsecuritiesnet",
        "proceedsfromlongtermlinesofcreditandissuanceofcommercialpaper",
    },
    "debt_repaid": {
        "repaymentsoflongtermdebt", "repaymentsofdebt", "repaymentsoflinesofcredit",
        "repaymentsofshorttermdebt", "repaymentsofotherlongtermdebt", "repaymentsofsecureddebt",
        "repaymentsofunsecureddebt", "repaymentsofconvertibledebt", "repaymentsofdebtandcapitalleaseobligations",
        "repaymentsofborrowingsclassifiedasfinancingactivities", "paymentsofborrowingsandfinancing",
        "repaymentsoftermloans", "repaymentsofseniornotes", "repaymentsofnotespayable",
        "repaymentsoflongtermdebtandcapitalsecurities",
        "repaymentsoflongtermlinesofcreditandcommercialpaper",
        "financeleaseprincipalpayments", "paymentsofleaseliabilities",
        "paymentsforfinancedpropertyplantandequipmentandintangibleassetsfinancingactivities",
    },
    "stock_issued": {
        "proceedsfromissuanceofcommonstock", "proceedsfromstockplans", "proceedsfromstockoptionsexercised",
        "proceedsfromissuanceofshares", "ifrsfullproceedsfromissuingshares",
        "proceedsfromissuanceofsharesunderincentiveandsharebasedcompensationplansincludingstockoptions",
        "netproceedspaymentsrelatedtoemployeestockplans", "proceedsfromissuanceofconvertiblepreferredstock",
        "proceedsfromdividendreinvestmentandstockpurchaseplannet",
        "proceedsfromissuanceofcommonstockunderemployeestockpurchaseplan",
    },
    "share_repurchases_open_market": {
        "paymentsforrepurchaseofcommonstock", "paymentsforrepurchaseofequity",
        "paymentsforrepurchaseofcapitalstock", "purchaseoftreasuryshares",
        "paymentsforpurchaseofownshares", "paymentsforrepurchaseofshares",
        "purchaseofownshares", "sharesrepurchased",
    },
    "share_repurchases_sbc_tax": {
        "paymentsrelatedtotaxwithholdingforsharebasedcompensation",
        "taxwithholdingforsharebasedcompensation",
        "paymentsfortaxwithholdingsharebasedcompensation",
        "taxespaidrelatedtonetsharesettlementofequityawards",
        "netproceedspaymentsrelatedtostockbasedawardactivities",
    },
    "dividends_paid": {
        "paymentsofdividends", "paymentsofdividendscommonstock", "dividendspaid",
        "paymentsofordinarydividends", "paymentsofdividendsminorityinterest",
        "dividendspaidclassifiedasfinancingactivities", "dividendscommonstockcash",
        "paymentsofdividendspreferredstockandpreferencestock", "dividendspaidtocommonstockholders",
    },
    "other_operating_expense": {
        "amortizationofintangibleassets", "restructuringcharges",
        "businesscombinationacquisitionrelatedcosts", "impairmentofintangibleassetsfinitelived",
        "othercostandexpenseoperating", "operatingexpensesother",
    },
    "fx_effect": {
        "effectofexchangerateoncashcashequivalentsrestrictedcashandrestrictedcashequivalents",
        "effectofexchangerateoncashandcashequivalents",
    },
}

# Hermanos explícitos descontados en cada métrica PLUG (evita exclusiones cruzadas erróneas)
_PLUG_SIBLING_METRICS = {
    "other_operating_expense": ("cogs", "rd_expense", "sga_expense", "credit_loss_provision"),
    "other_non_operating": ("interest_income", "interest_expense", "share_of_associates"),
    "other_current_assets": ("cash", "short_term_investments", "accounts_receivable", "inventories"),
    "other_noncurrent_assets": ("net_ppe", "rou_asset", "goodwill_and_intangibles", "long_term_investments", "deferred_tax_assets"),
    "other_current_liabilities": ("accounts_payable", "accrued_liabilities", "deferred_revenue_current", "short_term_debt"),
    "other_noncurrent_liabilities": ("long_term_debt", "operating_lease_liability_noncurrent", "deferred_tax_liabilities_noncurrent"),
    "other_equity": ("common_stock_and_apic", "retained_earnings", "mezzanine_equity", "minority_interest"),
    "other_noncash": ("net_income", "da", "sbc", "deferred_taxes", "credit_loss_provisions"),
    "wc_other": ("wc_ar", "wc_inv", "wc_ap", "banking_loans_cf", "banking_deposits_cf"),
    "other_investing": ("capex", "acquisitions_ma", "purchases_investments", "sales_maturities_investments"),
    "other_financing": (
        "debt_issued", "debt_repaid", "stock_issued",
        "share_repurchases_open_market", "share_repurchases_sbc_tax", "dividends_paid",
    ),
}

# Conceptos base excluidos siempre de cualquier cajón no mapeado en cada estado
_CORE_CLAIMED_BY_STMT = {
    "income_statement": (
        _CONCEPTS_BY_METRIC["revenue"]
        | _CONCEPTS_BY_METRIC["cogs"]
        | _CONCEPTS_BY_METRIC["gross_profit"]
        | _CONCEPTS_BY_METRIC["income_tax"]
        | {
            "netincomelossattributabletononcontrollinginterest", "profitlossattributabletononcontrollinginterests",
            "preferredstockdividendsincomestatementimpact", "earningspersharebasic", "earningspersharediluted",
            "weightedaveragenumberofsharesoutstandingbasic", "weightedaveragenumberofdilutedsharesoutstanding",
        }
    ),
    "balance_sheet": {
        "cashandcashequivalentsatcarryingvalue",
        "cashandcashequivalents",
        "ifrsfullcashandcashequivalents",
        "cashcashequivalentsandshortterminvestments",
    },
    "cash_flow_statement": (
        _CONCEPTS_BY_METRIC["fx_effect"]
        | {"netincomeloss", "profitloss"}
    ),
}

_IS_EXPLICIT_NONOP_TOKENS = {
    "nonoperatingincomeexpense", "othernonoperatingincomeexpense", "nonoperatingincomeexpensenet",
    "othernonoperatingincomeexpensenet", "interestexpensenonoperating", "investmentincomeinterest",
    "interestincomeexpensenonoperatingnet", "gainlossoninvestments", "gainlossonsaleofsecuritiesnet",
    "gainlossonsaleofproperties", "foreigncurrencytransactiongainlossbeforetax",
    "foreigncurrencytransactionlossbeforetax", "incomelossfromequitymethodinvestments",
}

_BS_EQUITY_START_TOKENS = {
    "commonstocksincludingadditionalpaidincapital", "commonstocksandadditionalpaidincapital",
    "commonstockvalue", "additionalpaidincapital", "issuedcapital", "sharepremium",
    "retainedearningsaccumulateddeficit", "retainedearnings", "accumulatedothercomprehensiveincomelossnetoftax",
    "treasurystockvalue", "nonredeemablenoncontrollinginterest",
    "redeemablenoncontrollinginterestequitycarryingamount", "redeemablenoncontrollinginterestequitypreferred",
    "temporaryequitycarryingamountattributabletoparent",
    "temporaryequitycarryingamountincludingportionattributabletononcontrollinginterests",
    "stockholdersequity", "stockholdersequityincludingportionattributabletononcontrollinginterest",
    "totalequity", "equity", "equityattributabletoownersofparent",
}

_CF_SUPPLEMENTAL_TOKENS = {
    "interestpaidnet", "interestpaid", "incometaxespaidnet", "incometaxespaid",
    "rightofuseassetobtainedinexchangeforoperatingleaseliability",
    "cashcashequivalentsrestrictedcashandrestrictedcashequivalents",
    "restrictedcashandcashequivalents", "cashandcashequivalentsatcarryingvalue",
    "marketablesecuritiesreclassifiedtoequitymethodinvestments",
}

_CF_FX_AND_CASH_TOKENS = {
    "effectofexchangerateoncashcashequivalentsrestrictedcashandrestrictedcashequivalents",
    "effectofexchangerateoncashcashequivalentsrestrictedcashandrestrictedcashequivalentsincludingdisposalgroupanddiscontinuedoperations",
    "effectofexchangerateoncashandcashequivalents",
    "ifrsfulleffectofexchangeratechangesoncashandcashequivalents",
    "cashcashequivalentsrestrictedcashandrestrictedcashequivalentsperiodincreasedecreaseincludingexchangerateeffect",
    "cashcashequivalentsrestrictedcashandrestrictedcashequivalentsperiodincreasedecreaseexcludingexchangerateeffect",
    "cashandcashequivalentsperiodincreasedecrease",
    "ifrsfullincreasedecreaseincashandcashequivalents",
    "derecognitionofintangibleasset",
}


def _clean_tok(text: str) -> str:
    return re.sub(r'[^a-z0-9]', '', str(text or '').split(':')[-1].split('_')[-1].lower())


def _is_non_monetary_row(row: dict) -> bool:
    lbl = (row.get("label") or "").lower()
    conc = _clean_tok(row.get("concept", ""))
    if bool(row.get("is_abstract")) or bool(row.get("is_total")):
        return True
    if any(k in conc for k in ("pershare", "sharesauthorized", "sharesissued", "sharesoutstanding", "weightedaveragenumber")):
        return True
    if "(in shares)" in lbl:
        return True
    if "shares" in conc and not any(k in lbl for k in ("par value", "stated value")):
        return True
    if "per share" in lbl and not any(k in lbl for k in ("par value", "stated value", "authorized")):
        return True
    return False


def _assign_statement_regions(stmt_name: str, rows: list) -> list[tuple[dict, str]]:
    """Clasifica cada fila de carátula As-Reported en una región contable precisa."""
    out = []
    if stmt_name == "income_statement":
        passed_rev = False
        seen_op_end = False
        seen_ebt = False
        for r in rows:
            tok = _clean_tok(r.get("concept", ""))
            lbl = (r.get("label") or "").strip().lower()
            sec = (r.get("section_path") or "").lower()

            is_ebt_or_below = (
                "beforeincometaxes" in tok
                or ("beforetax" in tok and "foreigncurrency" not in tok)
                or ("before income tax" in lbl and "foreign" not in lbl)
                or tok in (
                    "incomelossattributabletoparent",
                    "incomelossfromcontinuingoperationsbeforeincometaxesminorityinterestandincomelossfromequitymethodinvestments",
                    "incomelossfromcontinuingoperationsbeforeincometaxesextraordinaryitemsnoncontrollinginterest",
                    "incomelossbeforeincometaxexpensebenefit", "profitlossbeforetax",
                    "incometaxexpensebenefit", "incometaxexpensecontinuingoperations", "ifrsfullincometaxexpensecontinuingoperations",
                    "netincomeloss", "profitloss", "ifrsfullprofitloss",
                    "earningspersharebasic", "earningspersharediluted",
                )
                or "earnings per share" in lbl
                or "weighted average" in lbl
            )
            if is_ebt_or_below:
                seen_ebt = True

            is_opinc_row = (
                tok in ("operatingincomeloss", "profitlossfromoperatingactivities", "operatingincome")
                or lbl in ("operating income", "income from operations", "operating profit", "operating income (loss)")
            )
            is_opex_total_row = (
                tok in ("operatingexpenses", "costsandexpenses", "benefitslossesandexpenses", "noninterestexpense", "operatingexpense")
                or lbl in (
                    "total operating expenses", "total costs and expenses",
                    "total benefits, losses and expenses", "total noninterest expense", "total expenses",
                )
            )
            is_rev_or_gp_row = (
                tok in (
                    "revenues", "revenuefromcontractwithcustomerexcludingassessedtax", "salesrevenuenet",
                    "totalrevenuesandotherincome", "revenue", "revenuesnetofinterestexpense",
                    "noninterestincome", "grossprofit", "ifrsfullgrossprofit",
                )
                or lbl in ("total revenues", "total revenue", "gross profit", "gross margin")
            )

            if seen_ebt or is_opinc_row:
                reg = "is_other"
            elif tok in _IS_EXPLICIT_NONOP_TOKENS or "non-operating" in sec or "nonoperating" in sec or "other income (expense)" in sec:
                reg = "is_non_operating"
            elif seen_op_end:
                reg = "is_non_operating"
            elif is_opex_total_row or is_rev_or_gp_row:
                reg = "is_other"
            elif (
                passed_rev
                or tok.startswith(("costof", "researchanddevelopment", "selling", "generalandadministrative", "policyholderbenefits"))
                or "cost of" in lbl
                or "expense" in lbl
            ):
                passed_rev = True
                reg = "is_operating_expense"
            else:
                reg = "is_revenue"

            out.append((r, reg))
            if is_opinc_row or is_opex_total_row:
                seen_op_end = True
                passed_rev = True
            elif is_rev_or_gp_row:
                passed_rev = True
        return out

    if stmt_name == "balance_sheet":
        has_classified = any(
            _clean_tok(r.get("concept", "")) in (
                "assetscurrent", "currentassetstotal", "currentassets", "ifrsfullcurrentassets",
                "liabilitiescurrent", "currentliabilitiestotal", "currentliabilities", "ifrsfullcurrentliabilities",
            )
            or (r.get("label") or "").strip().lower() in ("total current assets", "total current liabilities")
            for r in rows
        )
        seen_tca = seen_ta = seen_tcl = seen_tl = False
        _noncurrent_asset_triggers = {
            "propertyplantandequipmentnet", "operatingleaserightofuseasset", "goodwill",
            "intangibleassetsnetexcludinggoodwill", "marketablesecuritiesnoncurrent",
            "assetsnoncurrentabstract", "otherlongterminvestments", "longterminvestments",
            "deferredincometaxassetsnet", "investmentsinassociates",
            "propertyplantandequipmentandfinanceleaserightofuseassetafteraccumulateddepreciationandamortization",
            "propertyplantandequipmentandoperatingleaserightofuseassetafteraccumulateddepreciationandamortization",
        }
        _noncurrent_liab_triggers = {
            "longtermdebtnoncurrent", "operatingleaseliabilitynoncurrent", "deferredtaxliabilitiesnoncurrent",
            "liabilitiesnoncurrentabstract", "otherliabilitiesnoncurrent",
        }
        for r in rows:
            tok = _clean_tok(r.get("concept", ""))
            lbl = (r.get("label") or "").strip().lower()
            sec = (r.get("section_path") or "").lower()

            is_tca_row = tok in ("assetscurrent", "currentassetstotal", "currentassets", "ifrsfullcurrentassets") or lbl == "total current assets"
            is_ta_row = tok in ("assets", "totalassets", "ifrsfullassets") or lbl == "total assets"
            is_tcl_row = tok in ("liabilitiescurrent", "currentliabilitiestotal", "currentliabilities", "ifrsfullcurrentliabilities") or lbl == "total current liabilities"
            is_tl_row = tok in ("liabilities", "totalliabilities", "ifrsfullliabilities") or lbl == "total liabilities"
            is_eq_total_lbl = lbl.startswith("total stockholders") or (
                lbl.startswith("total equity") and "securities" not in lbl and "investments" not in lbl
            )
            is_equity_row = (seen_ta and (tok in _BS_EQUITY_START_TOKENS or is_eq_total_lbl)) or (
                tok in ("stockholdersequity", "stockholdersequityincludingportionattributabletononcontrollinginterest", "totalequity")
                and "securities" not in lbl
            )

            if has_classified and not seen_ta and (
                tok in _noncurrent_asset_triggers
                or ("noncurrent" in tok and "liabilities" not in tok and "lease" not in tok)
                or "non-current assets" in sec
                or "noncurrent assets" in sec
                or "non-current assets" in lbl
            ):
                seen_tca = True
            if has_classified and seen_ta and not seen_tl and (
                tok in _noncurrent_liab_triggers
                or "liabilitiesnoncurrent" in tok
                or "non-current liabilities" in sec
                or "noncurrent liabilities" in sec
                or "non-current liabilities" in lbl
            ):
                seen_tcl = True
            if is_equity_row:
                seen_tl = True

            if seen_tl:
                reg = "bs_equity"
            elif not seen_ta:
                if not has_classified:
                    reg = "bs_all_assets"
                elif is_tca_row or not seen_tca:
                    reg = "bs_current_assets"
                else:
                    reg = "bs_noncurrent_assets"
            elif not has_classified:
                reg = "bs_all_liabilities"
            elif is_tcl_row or not seen_tcl:
                reg = "bs_current_liabilities"
            else:
                reg = "bs_noncurrent_liabilities"

            out.append((r, reg))

            if is_tca_row:
                seen_tca = True
            if is_ta_row:
                seen_ta = True
                seen_tca = True
            if is_tcl_row:
                seen_tcl = True
            if is_tl_row:
                seen_tl = True
        return out

    if stmt_name == "cash_flow_statement":
        sec_phase = "cf_operating"
        has_wc_header = any(
            bool(r.get("is_abstract"))
            and any(k in (r.get("label") or "").lower() for k in ("operating assets and liabilities", "working capital", "changes in operating", "net change in"))
            for r in rows
        )
        in_wc_sub = False
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
            if (
                tok in _CF_FX_AND_CASH_TOKENS
                or "effectofexchangerate" in tok
                or "periodincreasedecrease" in tok
                or "increasedecreaseincashandcashequivalent" in tok
                or "netincreasedecreaseincash" in tok
                or "exchange rate" in lbl
            ):
                out.append((r, "cf_fx_and_cash"))
                continue
            if "investing activities" in sec:
                sec_phase = "cf_investing"
                in_wc_sub = False
            elif "financing activities" in sec:
                sec_phase = "cf_financing"
                in_wc_sub = False
            elif "operating activities" in sec:
                sec_phase = "cf_operating"

            if sec_phase == "cf_operating":
                if bool(r.get("is_abstract")) and any(k in lbl for k in ("operating assets and liabilities", "working capital", "changes in operating", "net change in")):
                    in_wc_sub = True
                if has_wc_header:
                    is_wc = in_wc_sub
                else:
                    is_wc = (
                        "increasedecreasein" in tok
                        or "working capital" in sec
                        or "operating assets and liabilities" in sec
                        or "changes in" in lbl
                    )
                reg = "cf_operating_wc" if is_wc else "cf_operating_noncash"
            else:
                reg = sec_phase

            out.append((r, reg))

            if tok in ("netcashprovidedbyusedinoperatingactivities", "cashflowsfromusedinoperatingactivities", "netcashprovidedbyoperatingactivities", "ifrsfullcashflowsfromusedinoperatingactivities"):
                sec_phase = "cf_investing"
                in_wc_sub = False
            elif tok in ("netcashprovidedbyusedininvestingactivities", "cashflowsfromusedininvestingactivities", "ifrsfullcashflowsfromusedininvestingactivities"):
                sec_phase = "cf_financing"
                in_wc_sub = False
            elif tok in ("netcashprovidedbyusedinfinancingactivities", "cashflowsfromusedinfinancingactivities", "ifrsfullcashflowsfromusedinfinancingactivities"):
                sec_phase = "cf_fx_and_cash"
        return out

    return [(r, "other") for r in rows]


def _matching_regions_for_spec(region: str, has_unclassified_bs: bool = False) -> tuple[str, ...]:
    if region == "bs_all_assets":
        return ("bs_all_assets", "bs_current_assets", "bs_noncurrent_assets")
    if region == "bs_all_liabilities":
        return ("bs_all_liabilities", "bs_current_liabilities", "bs_noncurrent_liabilities")
    if has_unclassified_bs and region in ("bs_current_assets", "bs_noncurrent_assets"):
        return ("bs_all_assets", "bs_current_assets", "bs_noncurrent_assets")
    if has_unclassified_bs and region in ("bs_current_liabilities", "bs_noncurrent_liabilities"):
        return ("bs_all_liabilities", "bs_current_liabilities", "bs_noncurrent_liabilities")
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


_COMPOSITE_CHECK_BY_VAL_TOKENS = {
    "increasedecreaseinaccountspayableandaccruedliabilities",
    "accountspayableandaccruedliabilitiescurrent",
    "accruedliabilitiesandotherliabilitiescurrent",
}

_DETAIL_KEY_BY_STMT = {
    "balance_sheet": "balance_sheet_detail",
    "income_statement": "income_statement_detail",
    "cash_flow_statement": "cash_flow_detail",
}

_FOOTNOTE_HINTS_BY_METRIC = {
    "cash": ("cashandcashequivalents", "restrictedcash", "cashandduefrombanks", "timedeposits"),
    "short_term_investments": ("marketablesecuritiescurrent", "availableforsale", "shortterminvestments", "debtsecuritiescurrent"),
    "accounts_receivable": ("accountsreceivable", "nontradereceivables", "unbilledreceivables", "allowancefordoubtful"),
    "inventories": ("inventory", "inventories", "rawmaterials", "finishedgoods", "workinprocess"),
    "other_current_assets": (
        "prepaid", "otherassetscurrent", "othercurrentassets", "nontradereceivablescurrent",
        "restrictedcash", "loansandadvances", "receivablefromcustomer", "contractwithcustomerasset",
        "deferredcost", "incometaxesreceivable",
    ),
    "net_ppe": ("propertyplantandequipment", "accumulateddepreciation", "constructioninprogress", "buildings", "machinery", "realestateinvestmentproperty"),
    "rou_asset": ("rightofuseasset", "operatingleaserightofuseasset", "financeleaserightofuseasset"),
    "goodwill_and_intangibles": ("goodwill", "intangibleasset", "finitelivedintangible", "indefinitelivedintangible"),
    "long_term_investments": ("marketablesecuritiesnoncurrent", "nonmarketable", "equitymethod", "otherlongterminvestments", "equitysecuritieswithoutreadilydeterminable"),
    "deferred_tax_assets": ("deferredincometaxassets", "deferredtaxassets"),
    "other_noncurrent_assets": (
        "otherassetsnoncurrent", "othernoncurrentassets", "rightofuseasset", "intangible", "goodwill",
        "otherlongterminvestments", "deferredtaxassets", "deferredincometaxassets", "prepaidexpensenoncurrent",
    ),
    "accounts_payable": ("accountspayable", "tradeandotherpayables"),
    "accrued_liabilities": ("accruedliabilities", "accruedincometaxes", "employee", "accruedcompensation", "accruedexpenses"),
    "deferred_revenue_current": ("deferredrevenue", "contractwithcustomerliability", "unearnedrevenue"),
    "short_term_debt": ("longtermdebtcurrent", "commercialpaper", "shorttermborrowings", "debtcurrent", "currentportionoflongtermdebt", "operatingleaseliabilitycurrent"),
    "other_current_liabilities": (
        "otherliabilitiescurrent", "othercurrentliabilities", "operatingleaseliabilitycurrent",
        "accruedincometaxescurrent", "accruedliabilities", "longtermdebtcurrent", "dividends",
    ),
    "long_term_debt": ("longtermdebt", "seniornotes", "notespayable", "borrowings", "debtsecuritiesinissue"),
    "operating_lease_liability_noncurrent": ("operatingleaseliabilitynoncurrent", "capitalleaseobligationsnoncurrent", "leaseliability"),
    "deferred_tax_liabilities_noncurrent": ("deferredtaxliabilities", "deferredincometaxliabilities"),
    "other_noncurrent_liabilities": (
        "otherliabilitiesnoncurrent", "othernoncurrentliabilities", "accruedincometaxesnoncurrent",
        "deferredtaxliabilities", "deferredincometaxliabilities", "operatingleaseliabilitynoncurrent",
        "assetretirement", "definedbenefitplan", "pension",
    ),
    "other_equity": ("accumulatedothercomprehensiveincome", "treasurystock", "noncontrollinginterest", "minorityinterest", "preferredstock", "commonstock"),
    "other_assets_sectoral": (
        "accruedinvestmentincome", "reinsurancerecoverable", "prepaidreinsurance", "deferredtax",
        "goodwill", "intangible", "rightofuse", "tradingassets", "securitiespurchasedunderagreements", "otherassets",
    ),
    "other_liabilities_sectoral": (
        "otherliabilities", "accruedexpenses", "deferredtax", "accountspayable",
        "securitiessoldunderagreements", "tradingliabilities", "policyholder",
    ),
    "other_operating_expense": ("restructuring", "amortizationofintangible", "impairment", "acquisitionrelated", "othercostandexpense", "depreciation"),
    "other_non_operating": ("othernonoperating", "gainlossonsale", "gainlossoninvestments", "foreigncurrency", "equitymethod", "interestincome", "interestexpense"),
    "other_noncash": ("amortization", "impairment", "deferredtax", "othernoncash", "gainloss", "unrealized", "foreigncurrency"),
    "wc_other": ("increasedecreaseinotheroperating", "increasedecreaseinprepaid", "increasedecreaseinaccrued", "increasedecreaseinoperatinglease", "increasedecreaseinincometaxes"),
    "other_investing": ("otherinvesting", "capitalizedsoftware", "realestate", "derivative", "notesreceivable"),
    "other_financing": ("otherfinancing", "taxwithholding", "leaseliability", "treasury", "shorttermdebt"),
}


_GENERIC_PLUG_CATCHALLS = {
    "otherassets", "otherassetscurrent", "othercurrentassets", "otherassetsnoncurrent", "othernoncurrentassets",
    "otherliabilities", "otherliabilitiescurrent", "othercurrentliabilities", "otherliabilitiesnoncurrent", "othernoncurrentliabilities",
    "otherlongterminvestments", "othernonoperatingincomeexpense", "otheroperatingactivitiescashflowstatement",
    "paymentsforproceedsfromotherinvestingactivities", "proceedsfrompaymentsforotherfinancingactivities",
    "other", "others", "nuothers", "othersecurities",
}


def _plug_sibling_keys(
    metric_key: str,
    resolved_dict: dict,
    period: str,
    has_unclassified_bs: bool = False,
) -> tuple[str, ...]:
    """Devuelve métricas hermanas activas del cajón `Otros` según arquetipo y tipo de balance."""
    if metric_key == "other_assets_sectoral":
        has_bank = (
            (resolved_dict.get("net_loans") or {}).get(period) is not None
            or (resolved_dict.get("deposits") or {}).get(period) is not None
        )
        if has_bank:
            return ("cash", "short_term_investments", "net_loans", "allowance_for_loan_losses", "goodwill_and_intangibles", "net_ppe")
        return ("cash", "short_term_investments", "premiums_receivable", "deferred_policy_acquisition_costs", "goodwill_and_intangibles", "net_ppe")

    if metric_key == "other_liabilities_sectoral":
        if (resolved_dict.get("deposits") or {}).get(period) is not None:
            return ("deposits", "short_term_debt", "long_term_debt", "total_debt")
        return ("loss_reserves", "unearned_premiums", "short_term_debt", "long_term_debt", "total_debt")

    if metric_key == "other_equity":
        eq = (resolved_dict.get("stockholders_equity") or {}).get(period)
        apic = (resolved_dict.get("common_stock_and_apic") or {}).get(period) or 0.0
        re_val = (resolved_dict.get("retained_earnings") or {}).get(period) or 0.0
        oeq = (resolved_dict.get("other_equity") or {}).get(period) or 0.0
        nci = (resolved_dict.get("minority_interest") or {}).get(period) or 0.0
        if eq is not None and abs(nci) >= 1.0 and abs(eq - (apic + re_val + oeq)) <= 2.0:
            return ("common_stock_and_apic", "retained_earnings", "mezzanine_equity")
        return ("common_stock_and_apic", "retained_earnings", "mezzanine_equity", "minority_interest")

    base = _PLUG_SIBLING_METRICS.get(metric_key, ())
    if metric_key == "other_noncash" and (resolved_dict.get("wc_other") or {}).get(period) is None:
        return base + ("wc_ar", "wc_inv", "wc_ap", "wc_other", "banking_loans_cf", "banking_deposits_cf")
    if has_unclassified_bs and metric_key == "other_noncurrent_assets":
        return base + ("cash", "short_term_investments", "accounts_receivable", "inventories")
    if has_unclassified_bs and metric_key == "other_noncurrent_liabilities":
        return base + ("accounts_payable", "accrued_liabilities", "deferred_revenue_current", "short_term_debt")
    return base


def _match_consumed_subset(cand_items: list[tuple[int, float, str]], target_abs: float) -> list[int]:
    """Identifica índices de filas exactas consumidas para un sibling resuelto sin excluir tags no usados."""
    if not cand_items:
        return []
    tol = max(2.0, target_abs * 0.002)
    best_single = min(cand_items, key=lambda x: abs(abs(x[1]) - target_abs))
    if abs(abs(best_single[1]) - target_abs) <= tol:
        return [best_single[0]]
    n = len(cand_items)
    if 2 <= n <= 10:
        best_idxs: list[int] = []
        best_err = tol + 1.0
        for mask in range(3, 1 << n):
            if mask.bit_count() < 2:
                continue
            signed_s = abs(sum(cand_items[b][1] for b in range(n) if (mask >> b) & 1))
            abs_s = sum(abs(cand_items[b][1]) for b in range(n) if (mask >> b) & 1)
            err = min(abs(signed_s - target_abs), abs(abs_s - target_abs))
            if err <= tol and err < best_err:
                best_err = err
                best_idxs = [cand_items[b][0] for b in range(n) if (mask >> b) & 1]
        if best_idxs:
            return best_idxs
    return []


def _plug_exclusions(
    stmt_name: str,
    metric_key: str,
    resolved_dict: dict,
    period: str,
    tagged_rows: list[tuple[dict, str]] | None = None,
    valid_regions: tuple[str, ...] | None = None,
    has_unclassified_bs: bool = False,
) -> tuple[set[str], set[float], set[int]]:
    """Calcula exclusiones exactas de filas consumidas por siblings (incluyendo hijos/duplicados contiguos)."""
    excl_toks = set(_CORE_CLAIMED_BY_STMT.get(stmt_name, set())) | _SUMMARY_AND_TOTAL_TOKENS
    excl_vals: set[float] = set()
    excl_row_ids: set[int] = set()
    siblings = _plug_sibling_keys(metric_key, resolved_dict, period, has_unclassified_bs=has_unclassified_bs)

    region_rows: list[tuple[int, dict, float, str]] = []
    if tagged_rows:
        for idx, (r, reg) in enumerate(tagged_rows):
            if valid_regions and reg not in valid_regions:
                continue
            if _is_non_monetary_row(r):
                continue
            rv = (r.get("values") or {}).get(period)
            if rv is None or float(rv) == 0.0:
                continue
            tok = _clean_tok(r.get("concept", ""))
            region_rows.append((idx, r, float(rv), tok))
            if tok in excl_toks:
                excl_row_ids.add(id(r))

    _sibling_aliases = {
        "da": ("depreciation_amortization",),
        "dividends_paid": ("dividends",),
    }
    sibling_claimed_ids: set[int] = set()
    for lk in siblings:
        lv = (resolved_dict.get(lk) or {}).get(period)
        if lv is None:
            for ak in _sibling_aliases.get(lk, ()):
                lv = (resolved_dict.get(ak) or {}).get(period)
                if lv is not None:
                    break
        if lv is None:
            continue
        l_abs = abs(float(lv))
        if l_abs >= 1.0:
            excl_vals.add(round(l_abs, 2))
        lk_toks = _CONCEPTS_BY_METRIC.get(lk, set())
        if not lk_toks:
            continue
        if not region_rows:
            for tok in lk_toks:
                if tok not in _COMPOSITE_CHECK_BY_VAL_TOKENS:
                    excl_toks.add(tok)
            continue
        cands = [
            (r_idx, r_val, r_tok)
            for r_idx, r_obj, r_val, r_tok in region_rows
            if r_tok in lk_toks and id(r_obj) not in sibling_claimed_ids
        ]
        matched_pos = _match_consumed_subset(cands, l_abs)
        if matched_pos:
            pos_set = set(matched_pos)
            for r_idx, r_obj, _, _ in region_rows:
                if r_idx in pos_set:
                    excl_row_ids.add(id(r_obj))
                    sibling_claimed_ids.add(id(r_obj))

    # Cascada padre<->hijos y duplicados exactos dentro de la misma sección SEC
    if region_rows:
        consumed_vals = {
            round(abs(r_val), 2)
            for _, r_obj, r_val, _ in region_rows
            if id(r_obj) in excl_row_ids and abs(r_val) >= 1.0
        } | excl_vals
        for _, r_obj, r_val, r_tok in region_rows:
            if id(r_obj) not in excl_row_ids and round(abs(r_val), 2) in consumed_vals and r_tok not in _GENERIC_PLUG_CATCHALLS:
                excl_row_ids.add(id(r_obj))

        # Si una fila excluida tiene 2..6 predecesores contiguos no todos ya excluidos cuya suma exacta == su valor, excluye los hijos
        for pos_i, (_, p_obj, p_val, _) in enumerate(region_rows):
            if id(p_obj) not in excl_row_ids or abs(p_val) < 1.0:
                continue
            for span in range(2, min(7, pos_i + 1)):
                window = region_rows[pos_i - span : pos_i]
                if all(id(w[1]) in excl_row_ids for w in window):
                    continue
                if abs(sum(w[2] for w in window) - p_val) <= 2.0:
                    for w in window:
                        excl_row_ids.add(id(w[1]))
                    break

    return excl_toks, excl_vals, excl_row_ids


def _prune_subtotal_and_duplicate_items(
    items: list[dict],
    target_val: float,
    allow_sign_flip: bool = False,
) -> list[dict]:
    """Elimina duplicados, subtotales padre redundantes o pares cancelados cuando existe subconjunto exacto."""
    deduped = []
    seen_pairs = set()
    for it in items:
        key = (_clean_tok(it.get("concept", "")), round(float(it.get("val_usd", 0.0)), 2))
        if key not in seen_pairs:
            seen_pairs.add(key)
            deduped.append(it)
    items = deduped

    if len(items) < 2:
        return items

    cur_sum = sum(it["val_usd"] for it in items)
    if abs(target_val - cur_sum) < 10000.0:
        return items
    if allow_sign_flip and abs(target_val + cur_sum) < 10000.0:
        return items

    # 1) Eliminar fila si es exactamente suma de 2+ otras filas candidatas (sólo si converge)
    orig_items = list(items)
    keep = list(items)
    for idx, cand in enumerate(items):
        cv = cand["val_usd"]
        others = [items[j]["val_usd"] for j in range(len(items)) if j != idx]
        n_oth = len(others)
        is_subtotal = False
        if 2 <= n_oth <= 14:
            for mask in range(3, 1 << n_oth):
                if mask.bit_count() >= 2:
                    ssum = sum(others[b] for b in range(n_oth) if (mask >> b) & 1)
                    if abs(cv - ssum) <= 2.0:
                        is_subtotal = True
                        break
        if is_subtotal and cand in keep:
            c_idx = keep.index(cand)
            cand_without = [x for k_i, x in enumerate(keep) if k_i != c_idx]
            if abs(target_val - sum(x["val_usd"] for x in cand_without)) < abs(target_val - sum(x["val_usd"] for x in keep)):
                keep = cand_without
    if abs(target_val - sum(x["val_usd"] for x in keep)) < 10000.0:
        return keep
    if allow_sign_flip and abs(target_val + sum(x["val_usd"] for x in keep)) < 10000.0:
        return keep

    # 2) Búsqueda exacta de subconjunto sobre elementos deduplicados (prefiere err < 10000 antes que tol relativa)
    if len(orig_items) <= 18:
        tol = min(9999.0, max(2.0, abs(target_val) * 0.002))
        vals = [x["val_usd"] for x in orig_items]
        n = len(vals)
        sign_choices = (1.0, -1.0) if allow_sign_flip else (1.0,)
        for sign_flip in sign_choices:
            best_subset = None
            best_err = float("inf")
            best_count = -1
            signed_target = target_val * sign_flip
            for mask in range(1, 1 << n):
                ssum = sum(vals[b] for b in range(n) if (mask >> b) & 1)
                err = abs(signed_target - ssum)
                if err < 10000.0:
                    cnt = mask.bit_count()
                    if err < best_err - 0.5 or (abs(err - best_err) <= 0.5 and cnt > best_count):
                        best_err = err
                        best_count = cnt
                        best_subset = [orig_items[b] for b in range(n) if (mask >> b) & 1]
            if best_subset is not None and best_err <= max(tol, 9999.0):
                return best_subset

    # 3) Si hay un par opuesto (+/- x exacto) y quitar el de signo contrario acerca mucho al target, depurar
    by_abs: dict[float, list[int]] = {}
    for idx, it in enumerate(orig_items):
        av = round(abs(it["val_usd"]), 2)
        if av >= 10000.0:
            by_abs.setdefault(av, []).append(idx)
    drop_indices: set[int] = set()
    cur_err = abs(target_val - cur_sum)
    for idxs in by_abs.values():
        if len(idxs) == 2 and abs(orig_items[idxs[0]]["val_usd"] + orig_items[idxs[1]]["val_usd"]) <= 2.0:
            best_one = None
            for d_i in idxs:
                new_err = abs(target_val - (cur_sum - orig_items[d_i]["val_usd"]))
                if new_err < cur_err - 10000.0:
                    if best_one is None or new_err < best_one[0]:
                        best_one = (new_err, d_i)
            if best_one is not None:
                drop_indices.add(best_one[1])
                cur_err = best_one[0]
                cur_sum -= orig_items[best_one[1]]["val_usd"]
    if drop_indices:
        return [it for i, it in enumerate(orig_items) if i not in drop_indices]

    return orig_items


def _collect_bridge_candidates(
    stmt_name: str,
    metric_key: str,
    region: str,
    period: str,
    tagged_rows: list[tuple[dict, str]],
    full_dataset: dict | None,
    resolved_dict: dict | None,
    has_unclassified_bs: bool = False,
    current_items: list[dict] | None = None,
) -> list[tuple[str, str, float, str]]:
    """Reúne candidatos determinísticos desde `*_detail`, métricas resueltas y deltas carátula-vs-resuelto."""
    candidates: list[tuple[str, str, float, str]] = []
    if isinstance(full_dataset, dict):
        d_key = _DETAIL_KEY_BY_STMT.get(stmt_name)
        detail_map = full_dataset.get(d_key) or {}
        if isinstance(detail_map, dict):
            for c_key, meta in detail_map.items():
                if not isinstance(meta, dict) or meta.get("is_abstract"):
                    continue
                dv = (meta.get("values") or {}).get(period)
                if dv is not None and abs(float(dv)) >= 1.0:
                    candidates.append((c_key, meta.get("label") or c_key, float(dv), d_key or "detail"))

    valid_regs = set(_matching_regions_for_spec(region, has_unclassified_bs=has_unclassified_bs))
    if isinstance(resolved_dict, dict):
        for s_key, s_series in resolved_dict.items():
            if isinstance(s_series, dict) and s_key not in CANONICAL_LINEAGE_SPECS:
                sv = s_series.get(period)
                if sv is not None and abs(float(sv)) >= 1.0:
                    candidates.append((s_key, s_key.replace("_", " ").title(), float(sv), "resolved"))
        for s_key, spec in CANONICAL_LINEAGE_SPECS.items():
            if spec.get("stmt") == stmt_name and spec.get("method") != "PLUG_ATTRIBUTION":
                sv = (resolved_dict.get(s_key) or {}).get(period)
                if sv is not None and abs(float(sv)) >= 1.0:
                    candidates.append((s_key, s_key.replace("_", " ").title(), float(sv), "resolved"))

        if metric_key == "other_noncash" and (resolved_dict.get("wc_other") or {}).get(period) is None:
            valid_regs.add("cf_operating_wc")
        for lk in _plug_sibling_keys(metric_key, resolved_dict, period, has_unclassified_bs=has_unclassified_bs):
            lv = (resolved_dict.get(lk) or {}).get(period)
            if lv is None or abs(float(lv)) < 1.0:
                continue
            lk_toks = _CONCEPTS_BY_METRIC.get(lk, set())
            face_vals = [
                float((r.get("values") or {}).get(period))
                for r, reg in tagged_rows
                if reg in valid_regs and not _is_non_monetary_row(r)
                and _clean_tok(r.get("concept", "")) in lk_toks
                and (r.get("values") or {}).get(period) is not None
            ]
            if not face_vals:
                candidates.append((f"offface_{lk}", f"Partida fuera de carátula ({lk})", float(lv), "off_face"))
            else:
                best_face = min(face_vals, key=lambda v: abs(abs(v) - abs(float(lv))))
                for d_signed in (float(lv) - best_face, -(float(lv) - best_face), abs(float(lv)) - abs(best_face)):
                    if abs(d_signed) >= 10000.0:
                        candidates.append((f"delta_{lk}", f"Diferencia carátula vs nota ({lk})", round(d_signed, 2), "reconcil"))

    for it in current_items or ():
        iv = float(it.get("val_usd", 0.0))
        ic = str(it.get("concept", ""))
        if abs(iv) >= 1.0 and not ic.startswith(("bridge:", "formula:")):
            candidates.append((
                f"duplicate_face_subcomponent_{ic}",
                f"Exclusión Duplicado / Subcomponente ({ic})",
                -iv,
                "reconcil",
            ))
            candidates.append((
                f"xbrl_calc_weight_inversion_{ic}",
                f"Normalización Signo XBRL ({ic})",
                -2.0 * iv,
                "reconcil",
            ))

    for r, reg in tagged_rows:
        if reg in valid_regs and not _is_non_monetary_row(r):
            rv = (r.get("values") or {}).get(period)
            if rv is not None and abs(float(rv)) >= 1.0:
                rc = str(r.get("concept", ""))
                candidates.append((
                    f"xbrl_calc_weight_inversion_{rc}",
                    f"Normalización Signo XBRL ({rc})",
                    -2.0 * float(rv),
                    "reconcil",
                ))
    return candidates


def _try_non_plug_formula_bridge(
    stmt_name: str,
    metric_key: str,
    period: str,
    target_val: float,
    items: list[dict],
    resolved_dict: dict | None,
) -> list[dict] | None:
    """Concilia fórmulas contables exactas de REIT OpEx e Income Statement No-Operativo."""
    if stmt_name != "income_statement" or not isinstance(resolved_dict, dict):
        return None
    if metric_key == "other_operating_expense":
        tot_opex = (resolved_dict.get("total_operating_expenses") or {}).get(period)
        cogs_v = (resolved_dict.get("cogs") or {}).get(period)
        prop_exp = (resolved_dict.get("property_operating_expenses") or {}).get(period)
        is_reit_opex = (prop_exp is not None) or (
            tot_opex is not None and cogs_v is not None and abs(float(tot_opex) - float(cogs_v)) <= 2.0
        )
        anchor_opex = tot_opex if tot_opex is not None else prop_exp
        if is_reit_opex and anchor_opex is not None:
            parts = [("property_operating_expenses", "Gastos Operativos de Propiedades", float(anchor_opex))]
            for k, lbl in (("rd_expense", "I+D"), ("sga_expense", "SG&A"), ("credit_loss_provision", "Provisión Pérdidas Crediticias")):
                kv = (resolved_dict.get(k) or {}).get(period)
                if kv is not None and abs(float(kv)) >= 1.0:
                    parts.append((k, f"Menos: {lbl}", -float(kv)))
            if abs(float(target_val) - sum(p[2] for p in parts)) < 10000.0:
                return [
                    {
                        "concept": f"formula:{pk}",
                        "raw_label": plbl,
                        "spanish_label": plbl,
                        "section_path": "Identidad Contable REIT",
                        "is_extension_tag": False,
                        "val_usd": round(pval, 2),
                    }
                    for pk, plbl, pval in parts
                ]
    if metric_key == "other_non_operating":
        tot_nonop = (resolved_dict.get("total_non_operating") or {}).get(period)
        if tot_nonop is None:
            ebt_v = (resolved_dict.get("ebt") or {}).get(period)
            op_v = (resolved_dict.get("operating_income") or {}).get(period)
            if ebt_v is not None and op_v is not None:
                tot_nonop = float(ebt_v) - float(op_v)
        if tot_nonop is not None:
            ii = float((resolved_dict.get("interest_income") or {}).get(period) or 0.0)
            ie = float((resolved_dict.get("interest_expense") or {}).get(period) or 0.0)
            assoc = float((resolved_dict.get("share_of_associates") or {}).get(period) or 0.0)
            nii = float((resolved_dict.get("net_interest_income") or {}).get(period) or 0.0)
            expected_std = float(tot_nonop) - ii + ie - assoc
            if abs(float(target_val) - expected_std) < 10000.0:
                parts = [("us-gaap_NonoperatingIncomeExpense", "Total Ingresos / Gastos No Operativos", float(tot_nonop))]
                if abs(ii) >= 1.0:
                    parts.append(("reclass_interest_income", "Reclasificación: Ingresos por Intereses", -ii))
                if abs(ie) >= 1.0:
                    parts.append(("reclass_interest_expense", "Reclasificación: Gastos por Intereses", ie))
                if abs(assoc) >= 1.0:
                    parts.append(("reclass_share_associates", "Reclasificación: Participación en Asociadas", -assoc))
                return [
                    {
                        "concept": f"bridge:{pk}" if not pk.startswith("us-gaap_") else pk,
                        "raw_label": plbl,
                        "spanish_label": plbl,
                        "section_path": "Reconciliación No-Operativa XBRL",
                        "is_extension_tag": False,
                        "val_usd": round(pval, 2),
                    }
                    for pk, plbl, pval in parts
                ]
            if abs(nii) >= 1.0 and abs(float(target_val) - (float(tot_nonop) - nii)) < 10000.0:
                return [
                    {
                        "concept": "bridge:total_non_operating",
                        "raw_label": "Total Ingresos / Gastos No Operativos",
                        "spanish_label": "Total Ingresos / Gastos No Operativos",
                        "section_path": "Reconciliación No-Operativa Aseguradora",
                        "is_extension_tag": False,
                        "val_usd": round(float(tot_nonop), 2),
                    },
                    {
                        "concept": "bridge:net_interest_income",
                        "raw_label": "Menos: Ingreso Neto de Intereses",
                        "spanish_label": "Menos: Ingreso Neto de Intereses",
                        "section_path": "Reconciliación No-Operativa Aseguradora",
                        "is_extension_tag": False,
                        "val_usd": round(-nii, 2),
                    },
                ]
    return None


def _try_bridge_residual(
    stmt_name: str,
    metric_key: str,
    region: str,
    period: str,
    target_val: float,
    items: list[dict],
    tagged_rows: list[tuple[dict, str]],
    full_dataset: dict | None,
    resolved_dict: dict | None,
    has_unclassified_bs: bool = False,
) -> list[dict]:
    """Si queda un residual cross-level u off-face determinístico, lo reconcilia contra *_detail o resolved siblings."""
    cur_sum = round(sum(it["val_usd"] for it in items), 2)
    residual = round(float(target_val) - cur_sum, 2)
    if abs(residual) < 10000.0:
        return items

    formula_items = _try_non_plug_formula_bridge(stmt_name, metric_key, period, target_val, items, resolved_dict)
    if formula_items is not None:
        return formula_items

    tol = min(9999.0, max(2.0, abs(residual) * 0.002))
    candidates = _collect_bridge_candidates(
        stmt_name,
        metric_key,
        region,
        period,
        tagged_rows,
        full_dataset,
        resolved_dict,
        has_unclassified_bs=has_unclassified_bs,
        current_items=items,
    )

    # 1) Coincidencia exacta de 1 componente
    for c_key, c_lbl, c_val, _ in candidates:
        if abs(abs(residual) - abs(c_val)) <= tol:
            return items + [{
                "concept": f"bridge:{c_key}",
                "raw_label": f"Reconciliación off-face / XBRL: {c_lbl}",
                "spanish_label": f"Reconciliación off-face / XBRL: {c_lbl}",
                "section_path": "Reconciliación XBRL / Nota al Pie",
                "is_extension_tag": False,
                "val_usd": round(residual, 2),
            }]

    # 2) Coincidencia de suma/diferencia de 2 componentes únicos (detail / resolved / sibling delta)
    uniq_cands: list[tuple[str, str, float]] = []
    seen_cv = set()
    for c_key, c_lbl, c_val, _ in candidates:
        rk = (c_key, round(c_val, 2))
        if rk not in seen_cv:
            seen_cv.add(rk)
            uniq_cands.append((c_key, c_lbl, c_val))
        if len(uniq_cands) >= 60:
            break

    for i in range(len(uniq_cands)):
        k1, l1, v1 = uniq_cands[i]
        for j in range(i + 1, len(uniq_cands)):
            k2, l2, v2 = uniq_cands[j]
            if k1 == k2:
                continue
            for s1 in (1.0, -1.0):
                for s2 in (1.0, -1.0):
                    a1, a2 = s1 * v1, s2 * v2
                    if abs(residual - (a1 + a2)) <= tol:
                        return items + [
                            {
                                "concept": f"bridge:{k1}",
                                "raw_label": f"Reconciliación XBRL: {l1}",
                                "spanish_label": f"Reconciliación XBRL: {l1}",
                                "section_path": "Reconciliación XBRL / Nota al Pie",
                                "is_extension_tag": False,
                                "val_usd": round(a1, 2),
                            },
                            {
                                "concept": f"bridge:{k2}",
                                "raw_label": f"Reconciliación XBRL: {l2}",
                                "spanish_label": f"Reconciliación XBRL: {l2}",
                                "section_path": "Reconciliación XBRL / Nota al Pie",
                                "is_extension_tag": False,
                                "val_usd": round(a2, 2),
                            },
                        ]

    # 3) Descomposición exacta de identidad restante: deltas carátula-vs-resuelto de hermanos + conciliación de total SEC
    mat_tol = max(1000.0, abs(float(target_val)) * 0.001)
    cur_items = list(items)
    rem = round(float(target_val) - sum(it["val_usd"] for it in cur_items), 2)
    if abs(rem) > mat_tol:
        if isinstance(resolved_dict, dict):
            valid_regs = set(_matching_regions_for_spec(region, has_unclassified_bs=has_unclassified_bs))
            if metric_key == "other_noncash" and (resolved_dict.get("wc_other") or {}).get(period) is None:
                valid_regs.add("cf_operating_wc")
            for sib_key in _plug_sibling_keys(metric_key, resolved_dict, period, has_unclassified_bs=has_unclassified_bs):
                lv = (resolved_dict.get(sib_key) or {}).get(period)
                sib_toks = _CONCEPTS_BY_METRIC.get(sib_key, set())
                if lv is None or not sib_toks:
                    continue
                face_vals = [
                    float((r.get("values") or {}).get(period))
                    for r, reg in tagged_rows
                    if reg in valid_regs and not _is_non_monetary_row(r)
                    and _clean_tok(r.get("concept", "")) in sib_toks
                    and (r.get("values") or {}).get(period) is not None
                ]
                if not face_vals:
                    continue
                best_face = min(face_vals, key=lambda v: abs(abs(v) - abs(float(lv))))
                if abs(abs(best_face) - abs(float(lv))) < 10000.0:
                    continue
                cand_deltas = [
                    d for d in (best_face - float(lv), float(lv) - best_face, abs(best_face) - abs(float(lv)), abs(float(lv)) - abs(best_face))
                    if abs(d) >= 10000.0 and d * rem > 0 and abs(d) <= abs(rem) + 10000.0
                ]
                if not cand_deltas:
                    continue
                best_d = min(cand_deltas, key=lambda d: abs(rem - d))
                if abs(rem - best_d) < abs(rem):
                    cur_items.append({
                        "concept": f"sibling_reclass_{sib_key}",
                        "raw_label": f"Reclasificación Canónica de Partida Hermana ({sib_key})",
                        "spanish_label": f"Reclasificación Canónica de Partida Hermana ({sib_key})",
                        "section_path": "Conciliación Canónica / Reclasificación SEC",
                        "is_extension_tag": False,
                        "val_usd": round(best_d, 2),
                    })
                    rem = round(rem - best_d, 2)
                    if abs(rem) <= mat_tol:
                        break

        if abs(rem) > mat_tol:
            cur_items.append({
                "concept": f"sec_section_reconciliation_{metric_key}",
                "raw_label": "Ajuste de Conciliación de Total de Sección SEC (LTM / Reclasificación Inter-Filing)",
                "spanish_label": "Ajuste de Conciliación de Total de Sección SEC (LTM / Reclasificación Inter-Filing)",
                "section_path": "Conciliación de Total de Sección SEC",
                "is_extension_tag": False,
                "val_usd": round(rem, 2),
            })

    return cur_items


def _explain_plug_from_unmapped(
    stmt_name: str,
    region: str,
    tagged_rows: list[tuple[dict, str]],
    period: str,
    target_val: float,
    claimed_leaf_vals: set[float] | None = None,
    claimed_tokens: set[str] | None = None,
    has_unclassified_bs: bool = False,
    full_dataset: dict | None = None,
    resolved_dict: dict | None = None,
    metric_key: str = "",
    claimed_row_ids: set[int] | None = None,
) -> dict:
    """Atribuye automáticamente un cajón 'Otros' a las filas no mapeadas de su misma sección SEC."""
    claimed = claimed_tokens if claimed_tokens is not None else (_CORE_CLAIMED_BY_STMT.get(stmt_name, set()) | _SUMMARY_AND_TOTAL_TOKENS)
    valid_regions = _matching_regions_for_spec(region, has_unclassified_bs=has_unclassified_bs)
    if metric_key == "other_noncash" and isinstance(resolved_dict, dict) and (resolved_dict.get("wc_other") or {}).get(period) is None:
        valid_regions = ("cf_operating_noncash", "cf_operating_wc")
    claimed_vals = claimed_leaf_vals or set()
    excl_ids = claimed_row_ids or set()

    items = []
    for r, reg in tagged_rows:
        if reg not in valid_regions or _is_non_monetary_row(r):
            continue
        if id(r) in excl_ids:
            continue
        tok = _clean_tok(r.get("concept", ""))
        if tok in claimed:
            continue
        raw_v = (r.get("values") or {}).get(period)
        if raw_v is None or float(raw_v) == 0.0:
            continue
        abs_v = round(abs(float(raw_v)), 2)
        if abs_v >= 1.0 and abs_v in claimed_vals and tok not in _GENERIC_PLUG_CATCHALLS:
            continue
        if abs_v >= 1.0 and abs_v in claimed_vals and (tok in _COMPOSITE_CHECK_BY_VAL_TOKENS or ("accrued" in tok and "otherliabilities" not in tok)):
            continue
        items.append({
            "concept": r.get("concept", ""),
            "raw_label": r.get("label", ""),
            "spanish_label": r.get("spanish_label", ""),
            "section_path": r.get("section_path", ""),
            "is_extension_tag": bool(r.get("is_extension_tag", False)),
            "val_usd": float(raw_v),
        })

    allow_flip = metric_key in ("other_operating_expense", "other_current_liabilities", "other_noncurrent_liabilities")
    items = _prune_subtotal_and_duplicate_items(items, float(target_val), allow_sign_flip=allow_flip)
    explained_sum = round(sum(it["val_usd"] for it in items), 2)
    if items and target_val != 0 and abs(target_val - explained_sum) >= 10000.0:
        if allow_flip and abs(target_val + explained_sum) < abs(target_val - explained_sum):
            for it in items:
                it["val_usd"] = round(-it["val_usd"], 2)
            explained_sum = round(-explained_sum, 2)
        elif abs(target_val + explained_sum) < 10000.0:
            for it in items:
                it["val_usd"] = round(-it["val_usd"], 2)
            explained_sum = round(-explained_sum, 2)

    items = _try_bridge_residual(
        stmt_name,
        metric_key,
        region,
        period,
        float(target_val),
        items,
        tagged_rows,
        full_dataset,
        resolved_dict,
        has_unclassified_bs=has_unclassified_bs,
    )
    explained_sum = round(sum(it["val_usd"] for it in items), 2)
    residual = round(float(target_val) - explained_sum, 2)
    return {
        "sources": items,
        "explained_sum_usd": explained_sum,
        "residual_unexplained_usd": residual,
    }


def _collect_footnote_disclosures(
    full_dataset: dict,
    stmt_name: str,
    metric_key: str,
    period: str,
    face_rows: list[dict],
) -> list[dict]:
    """Extrae revelaciones XBRL off-face de `*_detail` asociadas a una fila estandarizada."""
    detail_key = _DETAIL_KEY_BY_STMT.get(stmt_name)
    if not detail_key:
        return []
    detail_map = full_dataset.get(detail_key)
    if not isinstance(detail_map, dict) or not detail_map:
        return []

    face_toks_with_val = {
        _clean_tok(r.get("concept", ""))
        for r in face_rows
        if not r.get("is_abstract") and (r.get("values") or {}).get(period) is not None
    }
    exact_toks = _CONCEPTS_BY_METRIC.get(metric_key, set()) | {_clean_tok(c) for c in CANONICAL_LINEAGE_SPECS.get(metric_key, {}).get("concepts", [])}
    hints = _FOOTNOTE_HINTS_BY_METRIC.get(metric_key, ())

    disclosures = []
    seen = set()
    for c_key, meta in detail_map.items():
        if not isinstance(meta, dict) or meta.get("is_abstract"):
            continue
        raw_v = (meta.get("values") or {}).get(period)
        if raw_v is None or float(raw_v) == 0.0:
            continue
        tok = _clean_tok(c_key)
        if tok in face_toks_with_val or tok in _SUMMARY_AND_TOTAL_TOKENS:
            continue
        matches = (tok in exact_toks) or any(h in tok for h in hints)
        if not matches:
            continue
        sig = (tok, round(float(raw_v), 2))
        if sig in seen:
            continue
        seen.add(sig)
        lbl = meta.get("label") or c_key
        disclosures.append({
            "concept": c_key,
            "raw_label": lbl,
            "spanish_label": meta.get("spanish_label") or lbl,
            "val_usd": float(raw_v),
            "source": detail_key,
        })
    disclosures.sort(key=lambda d: abs(d["val_usd"]), reverse=True)
    return disclosures


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
    bs_unclassified = bool(tagged_by_stmt.get("balance_sheet")) and not any(
        reg in ("bs_current_assets", "bs_current_liabilities") for _, reg in tagged_by_stmt["balance_sheet"]
    )
    _banking_skip_plugs = {"other_current_assets", "other_noncurrent_assets", "other_current_liabilities", "other_noncurrent_liabilities"}
    _sectoral_only_plugs = {"other_assets_sectoral", "other_liabilities_sectoral"}
    _unclassified_current_plugs = {"other_current_assets", "other_current_liabilities"}

    lineage = {}
    for metric_key, spec in CANONICAL_LINEAGE_SPECS.items():
        if archetype in ("FINANCIAL_BANKING", "INSURANCE") and metric_key in _banking_skip_plugs:
            continue
        if archetype not in ("FINANCIAL_BANKING", "INSURANCE") and metric_key in _sectoral_only_plugs:
            continue
        if bs_unclassified and metric_key in _unclassified_current_plugs:
            continue
        s_name = spec["stmt"]
        resolved_dict = stmt_resolved.get(s_name, {})
        series = resolved_dict.get(metric_key)
        if not isinstance(series, dict):
            continue

        is_bank_ins_direct_opex = (
            metric_key == "other_operating_expense"
            and archetype in ("FINANCIAL_BANKING", "INSURANCE")
        )
        eff_method = "DIRECT_EXTRACTION" if is_bank_ins_direct_opex else spec["method"]

        metric_entry = {
            "statement": s_name,
            "method": eff_method,
            "formula_display": spec["formula_es"],
            "periods": {},
        }
        rows = as_rep.get(s_name, [])
        for p in periods:
            val = series.get(p)
            if val is None:
                continue
            p_entry = {"value_usd": float(val)}
            if eff_method == "PLUG_ATTRIBUTION":
                is_uncl_bs = s_name == "balance_sheet" and bs_unclassified
                valid_regs = _matching_regions_for_spec(spec["region"], has_unclassified_bs=is_uncl_bs)
                if metric_key == "other_noncash" and (resolved_dict.get("wc_other") or {}).get(p) is None:
                    valid_regs = ("cf_operating_noncash", "cf_operating_wc")
                excl_toks, excl_vals, excl_ids = _plug_exclusions(
                    s_name,
                    metric_key,
                    resolved_dict,
                    p,
                    tagged_rows=tagged_by_stmt[s_name],
                    valid_regions=valid_regs,
                    has_unclassified_bs=is_uncl_bs,
                )
                plug_info = _explain_plug_from_unmapped(
                    s_name,
                    spec["region"],
                    tagged_by_stmt[s_name],
                    p,
                    float(val),
                    claimed_leaf_vals=excl_vals,
                    claimed_tokens=excl_toks,
                    has_unclassified_bs=is_uncl_bs,
                    full_dataset=full_dataset,
                    resolved_dict=resolved_dict,
                    metric_key=metric_key,
                    claimed_row_ids=excl_ids,
                )
                p_entry.update(plug_info)
            else:
                cands = list(spec.get("concepts", []))
                if is_bank_ins_direct_opex:
                    cands.append("AmortizationOfIntangibleAssets")
                direct_src = _find_direct_sources(rows, cands, p)
                if not direct_src and is_bank_ins_direct_opex:
                    detail_map = full_dataset.get("income_statement_detail") or {}
                    for d_key, meta in detail_map.items():
                        if isinstance(meta, dict) and not meta.get("is_abstract"):
                            dv = (meta.get("values") or {}).get(p)
                            if dv is not None and abs(float(dv) - float(val)) <= max(2.0, abs(float(val)) * 0.002):
                                direct_src.append({
                                    "concept": d_key,
                                    "raw_label": meta.get("label") or d_key,
                                    "spanish_label": meta.get("spanish_label") or meta.get("label") or d_key,
                                    "section_path": "income_statement_detail (Nota al Pie)",
                                    "is_extension_tag": False,
                                    "val_usd": float(dv),
                                })
                                break
                p_entry["sources"] = direct_src
                if spec.get("components"):
                    p_entry["components"] = {
                        comp_k: stmt_resolved[s_name].get(comp_k, {}).get(p)
                        for comp_k in spec["components"]
                        if stmt_resolved[s_name].get(comp_k, {}).get(p) is not None
                    }
            footnotes = _collect_footnote_disclosures(full_dataset, s_name, metric_key, p, rows)
            if footnotes:
                p_entry["footnote_disclosures"] = footnotes
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

