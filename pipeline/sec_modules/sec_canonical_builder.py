"""
sec_canonical_builder.py - Constructor del resumen canónico (canonical_summary),
ratios financieros adaptados por arquetipo contable, retornos sobre balances promedio
y detección/ajuste retroactivo de Stock Splits.
"""

import pandas as pd
import numpy as np

try:
    from financial_taxonomy import (
        CORPORATE_TAXONOMY_MAP,
        BANKING_TAXONOMY_MAP,
        REIT_TAXONOMY_MAP,
        INSURANCE_TAXONOMY_MAP,
        PLATFORM_TAXONOMY_MAP,
        XBRL_TAXONOMY_MAP,
        get_first_matching_value,
        reconcile_accounting_identities,
    )
except ImportError:
    try:
        from ..financial_taxonomy import (
            CORPORATE_TAXONOMY_MAP,
            BANKING_TAXONOMY_MAP,
            REIT_TAXONOMY_MAP,
            INSURANCE_TAXONOMY_MAP,
            PLATFORM_TAXONOMY_MAP,
            XBRL_TAXONOMY_MAP,
            get_first_matching_value,
            reconcile_accounting_identities,
        )
    except ImportError:
        from pipeline.financial_taxonomy import (
            CORPORATE_TAXONOMY_MAP,
            BANKING_TAXONOMY_MAP,
            REIT_TAXONOMY_MAP,
            INSURANCE_TAXONOMY_MAP,
            PLATFORM_TAXONOMY_MAP,
            XBRL_TAXONOMY_MAP,
            get_first_matching_value,
            reconcile_accounting_identities,
        )

try:
    from .sec_xbrl_ltm import (
        get_all_matching_sum,
        get_mrq_fact_sum,
        get_ltm_quarterly_metric,
        get_fact_fallback,
    )
except ImportError:
    try:
        from sec_modules.sec_xbrl_ltm import (
            get_all_matching_sum,
            get_mrq_fact_sum,
            get_ltm_quarterly_metric,
            get_fact_fallback,
        )
    except ImportError:
        from pipeline.sec_modules.sec_xbrl_ltm import (
            get_all_matching_sum,
            get_mrq_fact_sum,
            get_ltm_quarterly_metric,
            get_fact_fallback,
        )


def extract_canonical_summary(inc_data, bal_data, cf_data, periods, facts_df=None, is_financial=False, archetype=None):
    """Genera la tabla canónica normalizada para análisis fundamental unificada por período (LTM y FYs)."""
    if archetype is None:
        archetype = "FINANCIAL_BANKING" if is_financial else "STANDARD_CORPORATE"
    else:
        is_financial = (archetype in ("FINANCIAL_BANKING", "INSURANCE"))

    canonical = {
        "revenue": {},
        "cost_of_goods_sold": {},
        "gross_profit": {},
        "operating_expenses": {},
        "operating_income": {},
        "net_income": {},
        "net_income_common": {},
        "cash_from_operations": {},
        "cash_from_investing": {},
        "cash_from_financing": {},
        "capital_expenditures": {},
        "free_cash_flow": {},
        "cash_and_equivalents": {},
        "short_term_investments": {},
        "total_liquid_cash": {},
        "short_term_debt": {},
        "long_term_debt": {},
        "total_debt": {},
        "net_debt": {},
        "total_assets": {},
        "stockholders_equity": {},
        "shares_basic": {},
        "shares_diluted": {},
        "eps_basic": {},
        "eps_diluted": {},
        "shares_basic_adjusted": {},
        "shares_diluted_adjusted": {},
        "eps_basic_adjusted": {},
        "eps_diluted_adjusted": {},
        "dps_adjusted": {},
        "split_adjustment_factor": {},
        "current_assets": {},
        "current_liabilities": {},
        "net_ppe": {},
        "net_working_capital": {},
        "tangible_capital_employed": {},
        "dividends_paid": {},
        "share_repurchases": {},
        "stock_plans_proceeds": {},
        "stock_based_compensation": {},
        "share_repurchases_gross": {},
        "share_repurchases_net": {},
        "share_repurchases_sbc_tax": {},
        "acquisitions_ma": {},
        "debt_repayments": {},
        "debt_issuances": {},
        "operating_lease_rou_asset": {},
        "accrued_liabilities": {},
        "rd_expense": {},
        "sga_expense": {},
        "sm_expense": {},
        "ga_expense": {},
        "interest_expense": {},
        "interest_income": {},
        "ebt": {},
        "income_tax": {},
        "non_operating_income": {}
    }
    
    if is_financial or archetype in ("FINANCIAL_BANKING", "PLATFORM_ECOSYSTEM"):
        canonical["net_interest_income"] = {}
        canonical["non_interest_income"] = {}
        canonical["credit_loss_provisions"] = {}
        canonical["total_deposits"] = {}
        canonical["net_loans"] = {}
        canonical["allowance_for_credit_losses"] = {}
        canonical["borrowings"] = {}
        canonical["repurchase_agreements"] = {}
        canonical["interest_income"] = {}
        canonical["interest_expense"] = {}

    # Claves canónicas específicas para REAL_ESTATE_REIT
    canonical["rental_revenue"] = {}
    canonical["property_operating_expenses"] = {}
    canonical["real_estate_depreciation"] = {}
    canonical["gain_loss_sale_properties"] = {}
    canonical["recurring_capex_maintenance"] = {}
    canonical["real_estate_acquisitions"] = {}
    canonical["noi"] = {}
    canonical["ffo"] = {}
    canonical["affo"] = {}

    # Claves canónicas específicas para INSURANCE
    canonical["net_premiums_earned"] = {}
    canonical["net_investment_income"] = {}
    canonical["losses_and_loss_expenses"] = {}
    canonical["acquisition_costs"] = {}
    canonical["other_underwriting_expenses"] = {}
    canonical["underwriting_profit"] = {}
    canonical["loss_reserves"] = {}
    canonical["unearned_premiums"] = {}
    canonical["reinsurance_receivables"] = {}
    canonical["total_investments"] = {}
    canonical["float_usd"] = {}
    canonical["loss_ratio"] = {}
    canonical["expense_ratio"] = {}
    canonical["combined_ratio"] = {}
    canonical["tangible_book_value"] = {}
    
    ratios = {
        "gross_margin_pct": {},
        "operating_margin_pct": {},
        "net_margin_pct": {},
        "fcf_margin_pct": {},
        "fcf_conversion_pct": {},
        "roe_pct": {},
        "roa_pct": {},
        "current_ratio": {},
        "debt_to_equity": {},
        "roc_greenblatt_pct": {},
        "tangible_capital_usd": {}
    }
    
    for p in periods:
        if archetype == "FINANCIAL_BANKING":
            # 1. Ingresos en Banca: Margen de Intereses Neto + Comisiones / No intereses
            ii = get_first_matching_value(inc_data, BANKING_TAXONOMY_MAP["interest_income"], p)
            ie = get_first_matching_value(inc_data, BANKING_TAXONOMY_MAP["interest_expense"], p)
            canonical["interest_income"][p] = ii
            canonical["interest_expense"][p] = ie
            
            nii = get_first_matching_value(inc_data, BANKING_TAXONOMY_MAP["net_interest_income"], p)
            if nii is None and ii is not None and ie is not None:
                nii = round(ii - abs(ie), 2)
            canonical["net_interest_income"][p] = nii
            
            non_ii = get_first_matching_value(inc_data, BANKING_TAXONOMY_MAP["non_interest_income"], p)
            canonical["non_interest_income"][p] = non_ii
            
            if nii is not None and non_ii is not None:
                rev = round(nii + non_ii, 2)
            elif nii is not None:
                rev = nii
            else:
                rev_cands = XBRL_TAXONOMY_MAP["revenue"]
                rev = get_first_matching_value(inc_data, rev_cands, p)
                if rev is None and facts_df is not None:
                    rev = get_fact_fallback(facts_df, rev_cands, p, is_flow=True)
            canonical["revenue"][p] = rev

            # 2. Provisiones y Costo de Ventas (en banca COGS = None, Gross Profit = None)
            clp = get_first_matching_value(inc_data, BANKING_TAXONOMY_MAP["credit_loss_provisions"], p)
            if clp is not None:
                clp = -abs(clp)
            canonical["credit_loss_provisions"][p] = clp
            canonical["cost_of_goods_sold"][p] = None

            # 3. Margen Bruto: Para un banco DEBE ser None (no existe COGS ni GP industrial)
            canonical["gross_profit"][p] = None
            gp = None

            # 4. Gastos no relacionados con intereses (OpEx)
            op_exp = get_first_matching_value(inc_data, BANKING_TAXONOMY_MAP["operating_expenses"], p)
            if op_exp is not None:
                op_exp = abs(op_exp)
            canonical["operating_expenses"][p] = op_exp
        elif archetype == "REAL_ESTATE_REIT":
            # 1. Ingresos en REIT: Total Revenue consolidado (Revenues) y Rental Revenue
            tot_rev = get_first_matching_value(inc_data, REIT_TAXONOMY_MAP.get("total_revenue", XBRL_TAXONOMY_MAP["revenue"]), p)
            if tot_rev is None and facts_df is not None:
                tot_rev = get_fact_fallback(facts_df, REIT_TAXONOMY_MAP.get("total_revenue", XBRL_TAXONOMY_MAP["revenue"]), p, is_flow=True)

            rent_rev = get_first_matching_value(inc_data, REIT_TAXONOMY_MAP["rental_revenue"], p)
            if rent_rev is None and facts_df is not None:
                rent_rev = get_fact_fallback(facts_df, REIT_TAXONOMY_MAP["rental_revenue"], p, is_flow=True)
            if rent_rev is None:
                rent_rev = tot_rev
            if tot_rev is None:
                tot_rev = rent_rev

            canonical["rental_revenue"][p] = rent_rev
            canonical["revenue"][p] = tot_rev
            rev = tot_rev

            # 2. En REIT no aplica COGS comercial/industrial tradicional
            canonical["cost_of_goods_sold"][p] = None
            cogs = None

            # 3. Gastos operativos de las propiedades (Property Operating Expenses)
            prop_exp = get_first_matching_value(inc_data, REIT_TAXONOMY_MAP["property_operating_expenses"], p)
            if prop_exp is None and facts_df is not None:
                prop_exp = get_fact_fallback(facts_df, REIT_TAXONOMY_MAP["property_operating_expenses"], p, is_flow=True)
            canonical["property_operating_expenses"][p] = prop_exp

            # 4. Margen Bruto Inmobiliario: Net Operating Income (NOI = Rental Revenue - Property OpEx)
            noi = None
            if rent_rev is not None and prop_exp is not None:
                noi = round(rent_rev - abs(prop_exp), 2)
            elif rent_rev is not None:
                noi = rent_rev
            canonical["noi"][p] = noi
            canonical["gross_profit"][p] = noi
            gp = noi

            # 5. Gastos Operativos Totales
            op_exp = get_first_matching_value(inc_data, XBRL_TAXONOMY_MAP["operating_expenses"], p)
            if op_exp is None:
                op_exp = prop_exp
            if op_exp is not None:
                op_exp = abs(op_exp)
            canonical["operating_expenses"][p] = op_exp

            # 6. D&A Inmobiliaria, Ganancias por Venta y CapEx Recurrente
            re_dep = get_first_matching_value(inc_data, REIT_TAXONOMY_MAP["real_estate_depreciation"], p)
            if re_dep is None:
                re_dep = get_first_matching_value(cf_data, REIT_TAXONOMY_MAP["real_estate_depreciation"], p)
            if re_dep is None and facts_df is not None:
                re_dep = get_fact_fallback(facts_df, REIT_TAXONOMY_MAP["real_estate_depreciation"], p, is_flow=True)
            canonical["real_estate_depreciation"][p] = abs(re_dep) if re_dep is not None else None

            gain_sale = get_first_matching_value(inc_data, REIT_TAXONOMY_MAP["gain_loss_sale_properties"], p)
            if gain_sale is None and facts_df is not None:
                gain_sale = get_fact_fallback(facts_df, REIT_TAXONOMY_MAP["gain_loss_sale_properties"], p, is_flow=True)
            canonical["gain_loss_sale_properties"][p] = gain_sale

            rec_capex = get_first_matching_value(cf_data, REIT_TAXONOMY_MAP["recurring_capex_maintenance"], p)
            if rec_capex is None and facts_df is not None:
                rec_capex = get_fact_fallback(facts_df, REIT_TAXONOMY_MAP["recurring_capex_maintenance"], p, is_flow=True)
            canonical["recurring_capex_maintenance"][p] = abs(rec_capex) if rec_capex is not None else None

        elif archetype == "INSURANCE":
            # 1. Ingresos en Seguros: Total Revenues oficial auditado de carátula
            tot_rev = get_first_matching_value(inc_data, INSURANCE_TAXONOMY_MAP.get("total_revenue", XBRL_TAXONOMY_MAP["revenue"]), p)
            if tot_rev is None and facts_df is not None:
                tot_rev = get_fact_fallback(facts_df, INSURANCE_TAXONOMY_MAP.get("total_revenue", XBRL_TAXONOMY_MAP["revenue"]), p, is_flow=True)

            prem_earned = get_first_matching_value(inc_data, INSURANCE_TAXONOMY_MAP["net_premiums_earned"], p)
            if prem_earned is None and facts_df is not None:
                prem_earned = get_fact_fallback(facts_df, INSURANCE_TAXONOMY_MAP["net_premiums_earned"], p, is_flow=True)
            canonical["net_premiums_earned"][p] = prem_earned

            inv_inc = get_first_matching_value(inc_data, INSURANCE_TAXONOMY_MAP["net_investment_income"], p)
            if inv_inc is None and facts_df is not None:
                inv_inc = get_fact_fallback(facts_df, INSURANCE_TAXONOMY_MAP["net_investment_income"], p, is_flow=True)
            canonical["net_investment_income"][p] = inv_inc

            if tot_rev is not None:
                rev = tot_rev
            elif prem_earned is not None and inv_inc is not None:
                rev = round(prem_earned + inv_inc, 2)
            elif prem_earned is not None:
                rev = prem_earned
            else:
                rev = None
            canonical["revenue"][p] = rev

            # 2. En aseguradoras no existe COGS comercial ni Margen Bruto
            canonical["cost_of_goods_sold"][p] = None
            cogs = None
            canonical["gross_profit"][p] = None
            gp = None

            # 3. Gastos Operativos y Siniestros
            op_exp = get_first_matching_value(inc_data, XBRL_TAXONOMY_MAP["operating_expenses"], p)
            if op_exp is None:
                op_exp = get_first_matching_value(inc_data, ["BenefitsLossesAndExpenses", "us-gaap_BenefitsLossesAndExpenses", "PolicyholderBenefitsAndClaimsAndExpenses"], p)
            if op_exp is not None:
                op_exp = abs(op_exp)
            canonical["operating_expenses"][p] = op_exp

            losses = get_first_matching_value(inc_data, INSURANCE_TAXONOMY_MAP["losses_and_loss_expenses"], p)
            if losses is None and facts_df is not None:
                losses = get_fact_fallback(facts_df, INSURANCE_TAXONOMY_MAP["losses_and_loss_expenses"], p, is_flow=True)
            canonical["losses_and_loss_expenses"][p] = abs(losses) if losses is not None else None

            acq_costs = get_first_matching_value(inc_data, INSURANCE_TAXONOMY_MAP["acquisition_costs"], p)
            if acq_costs is None and facts_df is not None:
                acq_costs = get_fact_fallback(facts_df, INSURANCE_TAXONOMY_MAP["acquisition_costs"], p, is_flow=True)
            canonical["acquisition_costs"][p] = abs(acq_costs) if acq_costs is not None else None

            other_und = get_first_matching_value(inc_data, INSURANCE_TAXONOMY_MAP["other_underwriting_expenses"], p)
            if other_und is None and facts_df is not None:
                other_und = get_fact_fallback(facts_df, INSURANCE_TAXONOMY_MAP["other_underwriting_expenses"], p, is_flow=True)
            canonical["other_underwriting_expenses"][p] = abs(other_und) if other_und is not None else None

            tot_und = (abs(acq_costs) if acq_costs else 0.0) + (abs(other_und) if other_und else 0.0)
            if tot_und > 0 and prem_earned is not None and losses is not None:
                canonical["underwriting_profit"][p] = round(prem_earned - abs(losses) - tot_und, 2)
            else:
                canonical["underwriting_profit"][p] = None

        else:
            # 1. Ingresos Corporativos Tradicionales y de Plataforma
            rev_cands = XBRL_TAXONOMY_MAP["revenue"]
            rev = get_first_matching_value(inc_data, rev_cands, p)
            if rev is None and facts_df is not None:
                rev = get_fact_fallback(facts_df, rev_cands, p, is_flow=True)
            canonical["revenue"][p] = rev
            
            # 2. Costo de Ventas
            cogs_cands = XBRL_TAXONOMY_MAP["cost_of_goods_sold"]
            cogs = get_first_matching_value(inc_data, cogs_cands, p)
            if cogs is None and facts_df is not None:
                cogs = get_fact_fallback(facts_df, cogs_cands, p, is_flow=True)
            if cogs is not None:
                cogs = abs(cogs)
            canonical["cost_of_goods_sold"][p] = cogs
            
            # 3. Margen Bruto
            gp = get_first_matching_value(inc_data, XBRL_TAXONOMY_MAP["gross_profit"], p)
            if gp is None and rev is not None and cogs is not None:
                gp = round(rev - cogs, 2)
            canonical["gross_profit"][p] = gp
            
            # 4. Gastos Operativos
            op_exp = get_first_matching_value(inc_data, XBRL_TAXONOMY_MAP["operating_expenses"], p)
            if op_exp is None and facts_df is not None:
                op_exp = get_fact_fallback(facts_df, XBRL_TAXONOMY_MAP["operating_expenses"], p, is_flow=True)
            if op_exp is not None:
                op_exp = abs(op_exp)
            canonical["operating_expenses"][p] = op_exp

            # 4b. Partidas Específicas de I+D y SG&A Canónicas
            rd_cands = XBRL_TAXONOMY_MAP.get("rd_expense", ["ResearchAndDevelopmentExpense"])
            rd_val = get_first_matching_value(inc_data, rd_cands, p)
            if rd_val is None and facts_df is not None:
                rd_val = get_fact_fallback(facts_df, rd_cands, p, is_flow=True)
            canonical["rd_expense"][p] = abs(rd_val) if rd_val is not None else None

            # Subpartidas explícitas S&M y G&A
            sm_cands = XBRL_TAXONOMY_MAP.get("sm_expense", ["SellingAndMarketingExpense"])
            ga_cands = XBRL_TAXONOMY_MAP.get("ga_expense", ["GeneralAndAdministrativeExpense"])
            sm_v = get_first_matching_value(inc_data, sm_cands, p)
            if sm_v is None and facts_df is not None:
                sm_v = get_fact_fallback(facts_df, sm_cands, p, is_flow=True)
            ga_v = get_first_matching_value(inc_data, ga_cands, p)
            if ga_v is None and facts_df is not None:
                ga_v = get_fact_fallback(facts_df, ga_cands, p, is_flow=True)
            canonical["sm_expense"][p] = abs(sm_v) if sm_v is not None else None
            canonical["ga_expense"][p] = abs(ga_v) if ga_v is not None else None

            sga_cands = XBRL_TAXONOMY_MAP.get("sga_expense", ["SellingGeneralAndAdministrativeExpense"])
            sga_val = get_first_matching_value(inc_data, sga_cands, p)
            if sga_val is None and facts_df is not None:
                sga_val = get_fact_fallback(facts_df, sga_cands, p, is_flow=True)
            if sga_val is None and (sm_v is not None or ga_v is not None):
                sga_val = (abs(sm_v) if sm_v else 0.0) + (abs(ga_v) if ga_v else 0.0)
            canonical["sga_expense"][p] = abs(sga_val) if sga_val is not None else None

            # Si es PLATFORM_ECOSYSTEM, registrar provisiones de crédito e ingresos financieros en campos dedicados sin contaminar margen comercial
            if archetype == "PLATFORM_ECOSYSTEM":
                clp = get_first_matching_value(inc_data, BANKING_TAXONOMY_MAP["credit_loss_provisions"], p)
                if clp is not None:
                    clp = -abs(clp)
                canonical["credit_loss_provisions"][p] = clp

                ii = get_first_matching_value(inc_data, BANKING_TAXONOMY_MAP["interest_income"], p)
                ie = get_first_matching_value(inc_data, BANKING_TAXONOMY_MAP["interest_expense"], p)
                canonical["interest_income"][p] = ii
                canonical["interest_expense"][p] = ie
                nii = get_first_matching_value(inc_data, BANKING_TAXONOMY_MAP["net_interest_income"], p)
                canonical["net_interest_income"][p] = nii
                non_ii = get_first_matching_value(inc_data, BANKING_TAXONOMY_MAP["non_interest_income"], p)
                canonical["non_interest_income"][p] = non_ii
        
        if archetype == "FINANCIAL_BANKING":
            ebit = None
        elif archetype == "REAL_ESTATE_REIT":
            # Para REITs, el beneficio operativo (EBIT) se calcula formalmente deduciendo D&A y G&A del NOI
            da_val = get_first_matching_value(cf_data, ["DepreciationDepletionAndAmortization", "DepreciationAndAmortization"], p) or 0.0
            ga_val = get_first_matching_value(inc_data, ["GeneralAndAdministrativeExpense", "SellingGeneralAndAdministrativeExpense"], p) or 0.0
            imp_val = get_first_matching_value(inc_data, ["ImpairmentOfRealEstate", "AssetImpairmentCharges"], p) or 0.0
            prop_exp_val = get_first_matching_value(inc_data, ["DirectCostsOfLeasedAndRentedPropertyOrEquipment", "o_DirectCostsOfLeasedAndRentedPropertyOrEquipmentIncludingReimbursableExpense"], p) or 0.0
            if rev is not None:
                noi_val = round(rev - abs(prop_exp_val), 2)
                ebit = round(noi_val - abs(da_val) - abs(ga_val) - abs(imp_val), 2)
            else:
                ebit = None
        else:
            ebit_cands = XBRL_TAXONOMY_MAP["operating_income"]
            ebit = get_first_matching_value(inc_data, ebit_cands, p)
            if ebit is None and facts_df is not None:
                ebit = get_fact_fallback(facts_df, ebit_cands, p, is_flow=True)
            if ebit is None and rev is not None and op_exp is not None and abs(op_exp) > 0:
                ebit = round(rev - abs(op_exp), 2)
        canonical["operating_income"][p] = ebit

        if gp is not None and ebit is not None and archetype not in ("FINANCIAL_BANKING", "INSURANCE", "REAL_ESTATE_REIT"):
            expected_opex = round(gp - ebit, 2)
            cur_opex = canonical["operating_expenses"].get(p)
            if expected_opex > 0 and (cur_opex is None or abs(cur_opex - expected_opex) > max(expected_opex * 0.01, 5.0)):
                canonical["operating_expenses"][p] = expected_opex

        # 4.b Gastos por Intereses (Interest Expense)
        if archetype not in ("FINANCIAL_BANKING", "PLATFORM_ECOSYSTEM"):
            ie_cands = XBRL_TAXONOMY_MAP.get("interest_expense", ["InterestExpense"])
            ie_val = get_first_matching_value(inc_data, ie_cands, p)
            if ie_val is None and facts_df is not None:
                ie_val = get_fact_fallback(facts_df, ie_cands, p, is_flow=True)
            if ie_val is None:
                ie_val = get_first_matching_value(cf_data, ["InterestPaidNet", "InterestPaid", "us-gaap_InterestPaidNet"], p)
            canonical["interest_expense"][p] = abs(ie_val) if ie_val is not None else None
        
        # 5. Beneficio Neto
        ni_cands = XBRL_TAXONOMY_MAP["net_income"]
        ni = get_first_matching_value(inc_data, ni_cands, p)
        if ni is None and facts_df is not None:
            ni = get_fact_fallback(facts_df, ni_cands, p, is_flow=True)
        canonical["net_income"][p] = ni

        # 5.b Impuesto sobre Beneficios (Income Tax)
        tax_cands = XBRL_TAXONOMY_MAP.get("income_tax", ["IncomeTaxExpenseBenefit", "IncomeTaxExpenseContinuingOperations"])
        tax_val = get_first_matching_value(inc_data, tax_cands, p)
        if tax_val is None and facts_df is not None:
            tax_val = get_fact_fallback(facts_df, tax_cands, p, is_flow=True)
        canonical["income_tax"][p] = abs(tax_val) if tax_val is not None else None

        # 5.c Beneficio Antes de Impuestos (EBT)
        ebt_cands = XBRL_TAXONOMY_MAP.get("ebt", [
            "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
            "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
            "IncomeLossAttributableToParent", "us-gaap_IncomeLossAttributableToParent",
            "IncomeLossBeforeIncomeTaxExpenseBenefit", "ProfitLossBeforeTax"
        ])
        ebt_val = get_first_matching_value(inc_data, ebt_cands, p)
        if ebt_val is None and facts_df is not None:
            ebt_val = get_fact_fallback(facts_df, ebt_cands, p, is_flow=True)
        if ebt_val is None and ni is not None and tax_val is not None:
            ebt_val = round(ni + abs(tax_val), 2)
        canonical["ebt"][p] = ebt_val

        # 5.d Ingresos por Intereses (Interest Income)
        ii_cands = XBRL_TAXONOMY_MAP.get("interest_income", ["InvestmentIncomeInterest", "InterestIncomeOperating", "InterestIncome"])
        ii_val = get_first_matching_value(inc_data, ii_cands, p)
        if ii_val is None and facts_df is not None:
            ii_val = get_fact_fallback(facts_df, ii_cands, p, is_flow=True)
        canonical["interest_income"][p] = abs(ii_val) if ii_val is not None else None

        # 5.e Total No Operativo (Non-Operating Income / Expense Net)
        if ebt_val is not None and ebit is not None and archetype not in ("FINANCIAL_BANKING", "INSURANCE", "REAL_ESTATE_REIT"):
            canonical["non_operating_income"][p] = round(ebt_val - ebit, 2)
        else:
            noi_cands = XBRL_TAXONOMY_MAP.get("non_operating_income", ["NonoperatingIncomeExpense", "InterestRevenueExpenseNet"])
            noi_val = get_first_matching_value(inc_data, noi_cands, p)
            if noi_val is None and facts_df is not None:
                noi_val = get_fact_fallback(facts_df, noi_cands, p, is_flow=True)
            canonical["non_operating_income"][p] = noi_val

        ni_comm_cands = XBRL_TAXONOMY_MAP.get("net_income_common", [])
        ni_comm = get_first_matching_value(inc_data, ni_comm_cands, p)
        if ni_comm is None and facts_df is not None and ni_comm_cands:
            ni_comm = get_fact_fallback(facts_df, ni_comm_cands, p, is_flow=True)
        canonical["net_income_common"][p] = ni_comm if ni_comm is not None else ni
        
        # 6. Acciones básicas y diluidas
        sh_basic_cands = XBRL_TAXONOMY_MAP["shares_basic"]
        sh_basic = get_first_matching_value(inc_data, sh_basic_cands, p)
        if sh_basic is None and facts_df is not None:
            sh_basic = get_fact_fallback(facts_df, sh_basic_cands, p, is_flow=False)
        canonical["shares_basic"][p] = sh_basic

        sh_diluted_cands = XBRL_TAXONOMY_MAP["shares_diluted"]
        sh = get_first_matching_value(inc_data, sh_diluted_cands, p)
        if sh is None and facts_df is not None:
            sh = get_fact_fallback(facts_df, sh_diluted_cands, p, is_flow=False)
        canonical["shares_diluted"][p] = sh
        
        # 6b. Beneficio Por Acción (BPA / EPS)
        eps_b_cands = XBRL_TAXONOMY_MAP["eps_basic"]
        eps_b = get_first_matching_value(inc_data, eps_b_cands, p)
        if eps_b is None and facts_df is not None:
            eps_b = get_fact_fallback(facts_df, eps_b_cands, p, is_flow=True)
        
        eps_d_cands = XBRL_TAXONOMY_MAP["eps_diluted"]
        eps_d = get_first_matching_value(inc_data, eps_d_cands, p)
        if eps_d is None and facts_df is not None:
            eps_d = get_fact_fallback(facts_df, eps_d_cands, p, is_flow=True)
            
        misplaced_shares_k = None
        if eps_d is not None and abs(eps_d) > 100:
            misplaced_shares_k = abs(float(eps_d))
            eps_d = eps_b
        if eps_b is not None and (eps_d is None or (ni is not None and ni < 0)):
            eps_d = eps_b

        ni_ref = canonical["net_income_common"].get(p) if canonical.get("net_income_common", {}).get(p) is not None else ni
        if ni_ref is not None and eps_d is not None and abs(eps_d) > 1e-4:
            implied_shares = abs(ni_ref / eps_d)
            if sh is None or (sh > 0 and abs((ni_ref / sh) - eps_d) > 1.0):
                if misplaced_shares_k and abs((misplaced_shares_k * 1000.0) - implied_shares) / implied_shares < 0.02:
                    sh = round(misplaced_shares_k * 1000.0, 0)
                    sh_basic = sh
                elif sh and sh > 0 and 250.0 <= (implied_shares / sh) <= 4000.0:
                    sh = round(implied_shares, 0)
                    if sh_basic is None or sh_basic < sh * 0.1:
                        sh_basic = sh
                canonical["shares_diluted"][p] = sh
                canonical["shares_basic"][p] = sh_basic
            
        if p == "LTM":
            # Para LTM, verificar primero si podemos calcular el BPA con la suma exacta de los 4 trimestres reportados (GAAP/Fiscal.ai)
            q4_eps_d = get_ltm_quarterly_metric(facts_df, eps_d_cands, mode='sum') if facts_df is not None else None
            q4_eps_b = get_ltm_quarterly_metric(facts_df, eps_b_cands, mode='sum') if facts_df is not None else None
            
            ni_for_eps = canonical["net_income_common"].get(p) or ni
            if q4_eps_d is not None and q4_eps_d > 0:
                eps_d = q4_eps_d
            elif ni_for_eps is not None and sh and sh > 0:
                eps_d = round(ni_for_eps / sh, 2)

            if q4_eps_b is not None and q4_eps_b > 0:
                eps_b = q4_eps_b
            elif ni_for_eps is not None and sh_basic and sh_basic > 0:
                eps_b = round(ni_for_eps / sh_basic, 2)
                
            # Calibrar las acciones diluidas promedio ponderadas LTM (promedio de los 4 trimestres o identidad GAAP NI/EPS)
            q4_sh = get_ltm_quarterly_metric(facts_df, sh_diluted_cands, mode='avg') if facts_df is not None else None
            if q4_sh is not None and q4_sh > 0:
                sh = q4_sh
                canonical["shares_diluted"][p] = sh
            elif eps_d is not None and eps_d > 0 and ni_for_eps is not None and ni_for_eps > 0:
                implied_sh = round(ni_for_eps / eps_d)
                if sh is None or abs(implied_sh - sh) / sh > 0.005:
                    sh = float(implied_sh)
                    canonical["shares_diluted"][p] = sh

            q4_sh_b = get_ltm_quarterly_metric(facts_df, sh_basic_cands, mode='avg') if facts_df is not None else None
            if q4_sh_b is not None and q4_sh_b > 0:
                sh_basic = q4_sh_b
                canonical["shares_basic"][p] = sh_basic
            elif eps_b is not None and eps_b > 0 and ni_for_eps is not None and ni_for_eps > 0:
                implied_sh_b = round(ni_for_eps / eps_b)
                if sh_basic is None or abs(implied_sh_b - sh_basic) / sh_basic > 0.005:
                    sh_basic = float(implied_sh_b)
                    canonical["shares_basic"][p] = sh_basic
            elif sh_basic is None and sh is not None and sh > 0:
                # Reconciliación canónica institucional invariante de escala si sh_basic no vino en hechos trimestrales
                prev_fys = [f for f in periods if f != "LTM"]
                if prev_fys:
                    p_prior = prev_fys[0]
                    prior_sb = canonical["shares_basic"].get(p_prior)
                    prior_sd = canonical["shares_diluted"].get(p_prior)
                    if prior_sb and prior_sd and prior_sd > 0:
                        ratio = min(1.0, prior_sb / prior_sd)
                        sh_basic = round(sh * ratio)
                    else:
                        sh_basic = sh
                else:
                    sh_basic = sh
                canonical["shares_basic"][p] = sh_basic

            if eps_b is None and ni_for_eps is not None and sh_basic and sh_basic > 0:
                eps_b = round(ni_for_eps / sh_basic, 2)
                    
        canonical["eps_basic"][p] = eps_b
        canonical["eps_diluted"][p] = eps_d
        
        # 7. Flujo de Caja Operativo
        cfo_cands = XBRL_TAXONOMY_MAP["cash_from_operations"]
        cfo = get_first_matching_value(cf_data, cfo_cands, p)
        if cfo is None and facts_df is not None:
            cfo = get_fact_fallback(facts_df, cfo_cands, p, is_flow=True)
        canonical["cash_from_operations"][p] = cfo
        
        # 8. CapEx
        capex_cands = XBRL_TAXONOMY_MAP["capital_expenditures"]
        capex_raw = get_first_matching_value(cf_data, capex_cands, p)
        if capex_raw is None and facts_df is not None:
            capex_raw = get_fact_fallback(facts_df, capex_cands, p, is_flow=True)
        if (capex_raw is None or capex_raw == 0.0) and p == "LTM":
            for cand in capex_cands:
                alt_c = get_first_matching_value(cf_data, [cand], p)
                if alt_c is not None and alt_c != 0.0:
                    capex_raw = alt_c
                    break
        if archetype == "REAL_ESTATE_REIT":
            re_acq = get_first_matching_value(cf_data, REIT_TAXONOMY_MAP["real_estate_acquisitions"], p)
            if re_acq is None and facts_df is not None:
                re_acq = get_fact_fallback(facts_df, REIT_TAXONOMY_MAP["real_estate_acquisitions"], p, is_flow=True)
            canonical["real_estate_acquisitions"][p] = abs(re_acq) if re_acq is not None else None

            rec_maint = canonical["recurring_capex_maintenance"].get(p)
            if rec_maint is not None and rec_maint > 0:
                capex = float(rec_maint)
            else:
                capex = abs(capex_raw) if capex_raw is not None else None
        else:
            capex = abs(capex_raw) if capex_raw is not None else None

        canonical["capital_expenditures"][p] = capex
        
        # 9. Free Cash Flow
        if archetype in ("FINANCIAL_BANKING", "INSURANCE"):
            # Para bancos y aseguradoras el FCF convencional no aplica debido a variaciones de cartera/depósitos/float en CFO
            canonical["free_cash_flow"][p] = None
            fcf = None
        elif archetype == "REAL_ESTATE_REIT":
            # Cálculo de FFO: Net_Income + D&A Inmobiliaria - Ganancias por Venta
            ffo = None
            if ni is not None:
                re_dep_val = float(canonical["real_estate_depreciation"].get(p) or 0.0)
                gain_sale_val = float(canonical["gain_loss_sale_properties"].get(p) or 0.0)
                ffo = round(float(ni) + re_dep_val - gain_sale_val, 2)
            canonical["ffo"][p] = ffo

            # Cálculo de AFFO: FFO - CapEx Recurrente de Mantenimiento
            affo = None
            if ffo is not None:
                rec_c = canonical["recurring_capex_maintenance"].get(p)
                deduct_c = float(rec_c) if rec_c is not None else (float(capex) if capex is not None else 0.0)
                affo = round(ffo - deduct_c, 2)
            canonical["affo"][p] = affo

            # Equivalencia para interoperabilidad: FCF = AFFO
            canonical["free_cash_flow"][p] = affo
            fcf = affo
        else:
            fcf = None
            if cfo is not None and capex is not None:
                fcf = round(cfo - capex, 2)
            canonical["free_cash_flow"][p] = fcf

        if archetype == "INSURANCE":
            prem_e = canonical["net_premiums_earned"].get(p)
            loss_v = canonical["losses_and_loss_expenses"].get(p)
            acq_v = canonical["acquisition_costs"].get(p)
            other_u = canonical["other_underwriting_expenses"].get(p)
            
            loss_r = None
            exp_r = None
            comb_r = None
            if prem_e and prem_e > 0:
                if loss_v is not None:
                    loss_r = round((abs(loss_v) / prem_e) * 100, 2)
                
                und_exp = (abs(acq_v) if acq_v else 0.0) + (abs(other_u) if other_u else 0.0)
                if und_exp == 0.0 and op_exp is not None and abs(op_exp) > 0:
                    und_exp = abs(op_exp)
                
                if und_exp > 0:
                    exp_r = round((und_exp / prem_e) * 100, 2)
                
                if loss_r is not None and exp_r is not None:
                    comb_r = round(loss_r + exp_r, 2)
                elif loss_r is not None:
                    comb_r = loss_r

            canonical["loss_ratio"][p] = loss_r
            canonical["expense_ratio"][p] = exp_r
            canonical["combined_ratio"][p] = comb_r
            ratios["loss_ratio_pct"] = ratios.get("loss_ratio_pct", {})
            ratios["loss_ratio_pct"][p] = loss_r
            ratios["expense_ratio_pct"] = ratios.get("expense_ratio_pct", {})
            ratios["expense_ratio_pct"][p] = exp_r
            ratios["combined_ratio_pct"] = ratios.get("combined_ratio_pct", {})
            ratios["combined_ratio_pct"][p] = comb_r

        # 9b. Asignación de Capital (Flujos de Financiación e Inversión)
        div_raw = get_first_matching_value(cf_data, XBRL_TAXONOMY_MAP["dividends_paid"], p)
        if div_raw is None and facts_df is not None:
            div_raw = get_fact_fallback(facts_df, XBRL_TAXONOMY_MAP["dividends_paid"], p, is_flow=True)
        canonical["dividends_paid"][p] = abs(float(div_raw)) if div_raw is not None else None

        rep_raw = get_first_matching_value(cf_data, XBRL_TAXONOMY_MAP["share_repurchases"], p)
        if rep_raw is None and facts_df is not None:
            rep_raw = get_fact_fallback(facts_df, XBRL_TAXONOMY_MAP["share_repurchases"], p, is_flow=True)
        canonical["share_repurchases"][p] = abs(float(rep_raw)) if rep_raw is not None else None

        stock_plans_raw = get_first_matching_value(cf_data, XBRL_TAXONOMY_MAP["stock_plans_proceeds"], p)
        if stock_plans_raw is None and facts_df is not None:
            stock_plans_raw = get_fact_fallback(facts_df, XBRL_TAXONOMY_MAP["stock_plans_proceeds"], p, is_flow=True)
        canonical["stock_plans_proceeds"][p] = abs(float(stock_plans_raw)) if stock_plans_raw is not None else None

        sbc_tax_raw = get_first_matching_value(cf_data, XBRL_TAXONOMY_MAP["share_repurchases_sbc_tax"], p)
        if sbc_tax_raw is None and facts_df is not None:
            sbc_tax_raw = get_fact_fallback(facts_df, XBRL_TAXONOMY_MAP["share_repurchases_sbc_tax"], p, is_flow=True)
        canonical["share_repurchases_sbc_tax"][p] = abs(float(sbc_tax_raw)) if sbc_tax_raw is not None else None

        sbc_raw = get_first_matching_value(cf_data, XBRL_TAXONOMY_MAP["stock_based_compensation"], p)
        if sbc_raw is None and facts_df is not None:
            sbc_raw = get_fact_fallback(facts_df, XBRL_TAXONOMY_MAP["stock_based_compensation"], p, is_flow=True)
        canonical["stock_based_compensation"][p] = abs(float(sbc_raw)) if sbc_raw is not None else None

        canonical["share_repurchases_gross"][p] = canonical["share_repurchases"][p]
        if canonical["share_repurchases"][p] is not None and canonical["stock_plans_proceeds"][p] is not None:
            canonical["share_repurchases_net"][p] = max(0.0, round(canonical["share_repurchases"][p] - canonical["stock_plans_proceeds"][p], 2))
        elif canonical["share_repurchases"][p] is not None:
            canonical["share_repurchases_net"][p] = canonical["share_repurchases"][p]
        else:
            canonical["share_repurchases_net"][p] = None

        ma_raw = get_all_matching_sum(cf_data, XBRL_TAXONOMY_MAP["acquisitions_ma"], p)
        if ma_raw is None and facts_df is not None:
            ma_raw = get_fact_fallback(facts_df, XBRL_TAXONOMY_MAP["acquisitions_ma"], p, is_flow=True)
        canonical["acquisitions_ma"][p] = abs(float(ma_raw)) if ma_raw is not None else None

        dr_raw = get_all_matching_sum(cf_data, XBRL_TAXONOMY_MAP["debt_repayments"], p)
        if dr_raw is None:
            dr_raw = get_first_matching_value(cf_data, XBRL_TAXONOMY_MAP["debt_repayments"], p)
        if dr_raw is None and facts_df is not None:
            dr_raw = get_fact_fallback(facts_df, XBRL_TAXONOMY_MAP["debt_repayments"], p, is_flow=True)
        canonical["debt_repayments"][p] = abs(float(dr_raw)) if dr_raw is not None else None

        di_raw = get_first_matching_value(cf_data, XBRL_TAXONOMY_MAP["debt_issuances"], p)
        if di_raw is None and facts_df is not None:
            di_raw = get_fact_fallback(facts_df, XBRL_TAXONOMY_MAP["debt_issuances"], p, is_flow=True)
        canonical["debt_issuances"][p] = abs(float(di_raw)) if di_raw is not None else None

        # 9c. Flujos Totales de Inversión y Financiación Canónicos
        cfi_cands = ["NetCashProvidedByUsedInInvestingActivities", "us-gaap_NetCashProvidedByUsedInInvestingActivities"]
        cfi_val = get_first_matching_value(cf_data, cfi_cands, p)
        if cfi_val is None and facts_df is not None:
            cfi_val = get_fact_fallback(facts_df, cfi_cands, p, is_flow=True)
        canonical["cash_from_investing"][p] = float(cfi_val) if cfi_val is not None else None

        cff_cands = ["NetCashProvidedByUsedInFinancingActivities", "us-gaap_NetCashProvidedByUsedInFinancingActivities"]
        cff_val = get_first_matching_value(cf_data, cff_cands, p)
        if cff_val is None and facts_df is not None:
            cff_val = get_fact_fallback(facts_df, cff_cands, p, is_flow=True)
        canonical["cash_from_financing"][p] = float(cff_val) if cff_val is not None else None

        if p == "LTM" and facts_df is not None:
            for flow_key, cands, keep_sign in [
                ("dividends_paid", XBRL_TAXONOMY_MAP["dividends_paid"], False),
                ("share_repurchases", XBRL_TAXONOMY_MAP["share_repurchases"], False),
                ("stock_plans_proceeds", XBRL_TAXONOMY_MAP["stock_plans_proceeds"], False),
                ("share_repurchases_sbc_tax", XBRL_TAXONOMY_MAP["share_repurchases_sbc_tax"], False),
                ("stock_based_compensation", XBRL_TAXONOMY_MAP["stock_based_compensation"], False),
                ("acquisitions_ma", XBRL_TAXONOMY_MAP["acquisitions_ma"], False),
                ("debt_repayments", XBRL_TAXONOMY_MAP["debt_repayments"], False),
                ("debt_issuances", XBRL_TAXONOMY_MAP["debt_issuances"], False),
                ("cash_from_investing", ["NetCashProvidedByUsedInInvestingActivities", "us-gaap_NetCashProvidedByUsedInInvestingActivities"], True),
                ("cash_from_financing", ["NetCashProvidedByUsedInFinancingActivities", "us-gaap_NetCashProvidedByUsedInFinancingActivities"], True),
            ]:
                if canonical[flow_key][p] is None:
                    q4_sum = get_ltm_quarterly_metric(facts_df, cands, mode='sum')
                    if q4_sum is not None:
                        canonical[flow_key][p] = float(q4_sum) if keep_sign else abs(float(q4_sum))
            canonical["share_repurchases_gross"][p] = canonical["share_repurchases"][p]
            if canonical["share_repurchases"][p] is not None and canonical["stock_plans_proceeds"][p] is not None:
                canonical["share_repurchases_net"][p] = max(0.0, round(canonical["share_repurchases"][p] - canonical["stock_plans_proceeds"][p], 2))
            elif canonical["share_repurchases"][p] is not None:
                canonical["share_repurchases_net"][p] = canonical["share_repurchases"][p]
            else:
                canonical["share_repurchases_net"][p] = None
            
        # 10. Balance Patrimonial
        asset_cands = XBRL_TAXONOMY_MAP["total_assets"]
        assets = get_first_matching_value(bal_data, asset_cands, p)
        if assets is None and facts_df is not None:
            assets = get_fact_fallback(facts_df, asset_cands, p)
        canonical["total_assets"][p] = assets
        
        equity_cands = XBRL_TAXONOMY_MAP["stockholders_equity"]
        equity = get_first_matching_value(bal_data, equity_cands, p)
        if equity is None and facts_df is not None:
            equity = get_fact_fallback(facts_df, equity_cands, p)
        canonical["stockholders_equity"][p] = equity
        
        if archetype == "FINANCIAL_BANKING":
            cash_pure = get_first_matching_value(bal_data, BANKING_TAXONOMY_MAP["cash_and_liquidity"], p) or 0.0
            cb_dep = get_first_matching_value(bal_data, BANKING_TAXONOMY_MAP["central_bank_deposits"], p) or 0.0
            cash = round(cash_pure + cb_dep, 2) if (cash_pure + cb_dep) > 0 else (cash_pure or 0.0)
            canonical["cash_and_equivalents"][p] = cash
            
            lt_debt = get_first_matching_value(bal_data, BANKING_TAXONOMY_MAP["long_term_debt"], p)
            if lt_debt is None and facts_df is not None:
                lt_debt = get_fact_fallback(facts_df, BANKING_TAXONOMY_MAP["long_term_debt"], p, is_flow=False)
            lt_debt = lt_debt or 0.0

            st_debt = get_first_matching_value(bal_data, BANKING_TAXONOMY_MAP["short_term_interbank"], p)
            if st_debt is None and facts_df is not None:
                st_debt = get_fact_fallback(facts_df, BANKING_TAXONOMY_MAP["short_term_interbank"], p, is_flow=False)
            st_debt = st_debt or 0.0

            tot_debt = round(lt_debt + st_debt, 2)
            canonical["borrowings"][p] = lt_debt
            canonical["repurchase_agreements"][p] = st_debt
            canonical["short_term_debt"][p] = st_debt
            canonical["long_term_debt"][p] = lt_debt
            canonical["total_debt"][p] = tot_debt
            canonical["net_debt"][p] = round(tot_debt - cash, 2)

            dep = get_first_matching_value(bal_data, BANKING_TAXONOMY_MAP["total_deposits"], p)
            if dep is None and facts_df is not None:
                dep = get_fact_fallback(facts_df, BANKING_TAXONOMY_MAP["total_deposits"], p, is_flow=False)
            canonical["total_deposits"][p] = dep

            l1 = get_first_matching_value(bal_data, ["CreditCardReceivables1", "CreditCardReceivables", "CreditCardReceivablesNet"], p) or 0.0
            l2 = get_first_matching_value(bal_data, ["LoansAndAdvancesToCustomers", "TotalLoansAndAdvancesToCustomers", "LoansAndLeasesReceivableNetOfDeferredIncome"], p) or 0.0
            tot_l = round(l1 + l2, 2) if (l1 + l2) > 0 else get_first_matching_value(bal_data, BANKING_TAXONOMY_MAP["net_loans"], p)
            if tot_l is None and facts_df is not None:
                tot_l = get_fact_fallback(facts_df, BANKING_TAXONOMY_MAP["net_loans"], p, is_flow=False)
            canonical["net_loans"][p] = tot_l

            allow_l = get_first_matching_value(bal_data, BANKING_TAXONOMY_MAP["allowance_for_credit_losses"], p)
            if allow_l is None and facts_df is not None:
                allow_l = get_fact_fallback(facts_df, BANKING_TAXONOMY_MAP["allowance_for_credit_losses"], p, is_flow=False)
            canonical["allowance_for_credit_losses"][p] = abs(allow_l) if allow_l is not None else None

            canonical["current_assets"][p] = None
            canonical["current_liabilities"][p] = None
            canonical["net_ppe"][p] = get_first_matching_value(bal_data, XBRL_TAXONOMY_MAP["net_ppe"], p)
            canonical["net_working_capital"][p] = None
            canonical["tangible_capital_employed"][p] = None
        elif archetype == "INSURANCE":
            cash = get_first_matching_value(bal_data, XBRL_TAXONOMY_MAP["cash_and_equivalents"], p)
            if cash is None and facts_df is not None:
                cash = get_fact_fallback(facts_df, XBRL_TAXONOMY_MAP["cash_and_equivalents"], p)
            cash = cash or 0.0
            canonical["cash_and_equivalents"][p] = cash
            
            st_debt = get_first_matching_value(bal_data, XBRL_TAXONOMY_MAP["short_term_debt"], p) or 0.0
            lt_debt = get_first_matching_value(bal_data, XBRL_TAXONOMY_MAP["long_term_debt"], p) or 0.0
            comb_debt = get_first_matching_value(bal_data, ["DebtLongtermAndShorttermCombinedAmount", "us-gaap_DebtLongtermAndShorttermCombinedAmount", "TotalDebt"], p)
            if comb_debt is not None:
                tot_debt = round(float(comb_debt), 2)
                if lt_debt == 0.0 and tot_debt > st_debt:
                    lt_debt = round(tot_debt - st_debt, 2)
            else:
                tot_debt = round(st_debt + lt_debt, 2)
            canonical["short_term_debt"][p] = st_debt
            canonical["long_term_debt"][p] = lt_debt
            canonical["total_debt"][p] = tot_debt
            canonical["net_debt"][p] = round(tot_debt - cash, 2)

            loss_res = get_first_matching_value(bal_data, INSURANCE_TAXONOMY_MAP["loss_reserves"], p)
            if loss_res is None and facts_df is not None:
                loss_res = get_fact_fallback(facts_df, INSURANCE_TAXONOMY_MAP["loss_reserves"], p)
            canonical["loss_reserves"][p] = abs(loss_res) if loss_res is not None else None

            unearned_prem = get_first_matching_value(bal_data, INSURANCE_TAXONOMY_MAP["unearned_premiums"], p)
            if unearned_prem is None and facts_df is not None:
                unearned_prem = get_fact_fallback(facts_df, INSURANCE_TAXONOMY_MAP["unearned_premiums"], p)
            canonical["unearned_premiums"][p] = abs(unearned_prem) if unearned_prem is not None else None

            reins_rec = get_first_matching_value(bal_data, INSURANCE_TAXONOMY_MAP["reinsurance_receivables"], p)
            if reins_rec is None and facts_df is not None:
                reins_rec = get_fact_fallback(facts_df, INSURANCE_TAXONOMY_MAP["reinsurance_receivables"], p)
            canonical["reinsurance_receivables"][p] = abs(reins_rec) if reins_rec is not None else None

            tot_inv = get_first_matching_value(bal_data, INSURANCE_TAXONOMY_MAP["total_investments"], p)
            if tot_inv is None and facts_df is not None:
                tot_inv = get_fact_fallback(facts_df, INSURANCE_TAXONOMY_MAP["total_investments"], p)
            canonical["total_investments"][p] = tot_inv

            # Cálculo del Float: Loss_Reserves + Unearned_Premiums - Reinsurance_Receivables
            ins_float = None
            if loss_res is not None or unearned_prem is not None:
                ins_float = (abs(loss_res) if loss_res else 0.0) + (abs(unearned_prem) if unearned_prem else 0.0) - (abs(reins_rec) if reins_rec else 0.0)
                ins_float = round(ins_float, 2)
            canonical["float_usd"][p] = ins_float

            canonical["current_assets"][p] = None
            canonical["current_liabilities"][p] = None
            canonical["net_ppe"][p] = None
            canonical["net_working_capital"][p] = None
            canonical["tangible_capital_employed"][p] = None

            if equity is not None:
                canonical["tangible_book_value"][p] = float(equity)
        else:
            cash = get_first_matching_value(bal_data, XBRL_TAXONOMY_MAP["cash_and_equivalents"], p)
            if cash is None and facts_df is not None:
                cash = get_fact_fallback(facts_df, XBRL_TAXONOMY_MAP["cash_and_equivalents"], p)
            cash = cash or 0.0
            canonical["cash_and_equivalents"][p] = cash

            # Inversiones a corto plazo / Valores negociables (componentes desagregados o consolidado)
            st_debt_sec = get_first_matching_value(bal_data, ["DebtSecuritiesCurrent", "us-gaap_DebtSecuritiesCurrent"], p) or 0.0
            st_eq_sec = get_first_matching_value(bal_data, ["EquitySecuritiesFvNi", "us-gaap_EquitySecuritiesFvNi"], p) or 0.0
            if (st_debt_sec + st_eq_sec) > 0:
                st_inv = round(st_debt_sec + st_eq_sec, 2)
            else:
                st_inv = get_first_matching_value(bal_data, XBRL_TAXONOMY_MAP["marketable_securities_current"], p)
                if st_inv is None and facts_df is not None:
                    if p == "LTM":
                        mrq_sum = get_mrq_fact_sum(facts_df, ["DebtSecuritiesCurrent", "EquitySecuritiesFvNi"])
                        if mrq_sum is not None and mrq_sum > 0:
                            st_inv = mrq_sum
                    if st_inv is None:
                        st_inv = get_fact_fallback(facts_df, XBRL_TAXONOMY_MAP["marketable_securities_current"], p)
            st_inv = st_inv or 0.0
            canonical["short_term_investments"][p] = st_inv
            tot_liquid_cash = round(cash + st_inv, 2)
            canonical["total_liquid_cash"][p] = tot_liquid_cash
            
            # Agregación universal de deuda financiera (SSOT y preservación de tramos)
            cp_val = get_first_matching_value(bal_data, ["CommercialPaper", "us-gaap_CommercialPaper", "ShortTermBorrowings", "us-gaap_ShortTermBorrowings"], p)
            ltd_curr = get_first_matching_value(bal_data, ["LongTermDebtCurrent", "us-gaap_LongTermDebtCurrent", "CurrentPortionOfLongTermDebt", "us-gaap_CurrentPortionOfLongTermDebt"], p)
            ltd_tot = get_first_matching_value(bal_data, ["LongTermDebt", "us-gaap_LongTermDebt"], p)
            ltd_noncurr = get_first_matching_value(bal_data, ["LongTermDebtNoncurrent", "us-gaap_LongTermDebtNoncurrent"], p)

            comb_debt = get_first_matching_value(bal_data, ["DebtLongtermAndShorttermCombinedAmount", "us-gaap_DebtLongtermAndShorttermCombinedAmount", "TotalDebt"], p)
            if comb_debt is not None:
                tot_debt = round(float(comb_debt), 2)
                st_debt = get_first_matching_value(bal_data, XBRL_TAXONOMY_MAP["short_term_debt"], p) or 0.0
                lt_debt = round(tot_debt - st_debt, 2) if tot_debt > st_debt else (tot_debt if lt_debt == 0.0 else lt_debt)
            elif cp_val is not None and ltd_tot is not None:
                # Caso corporativo con pagarés comerciales y deuda a plazo total (ej. AAPL)
                tot_debt = round(float(cp_val) + float(ltd_tot), 2)
                lt_debt = round(float(ltd_noncurr), 2) if ltd_noncurr is not None else round(float(ltd_tot), 2)
                st_debt = round(tot_debt - lt_debt, 2)
            else:
                st_debt = get_first_matching_value(bal_data, XBRL_TAXONOMY_MAP["short_term_debt"], p)
                if st_debt is None and facts_df is not None:
                    st_debt = get_fact_fallback(facts_df, XBRL_TAXONOMY_MAP["short_term_debt"], p)
                st_debt = st_debt or 0.0

                lt_debt = get_first_matching_value(bal_data, XBRL_TAXONOMY_MAP["long_term_debt"], p)
                if lt_debt is None and facts_df is not None:
                    lt_debt = get_fact_fallback(facts_df, XBRL_TAXONOMY_MAP["long_term_debt"], p)
                lt_debt = lt_debt or 0.0

                if cp_val is not None and ltd_curr is not None:
                    combined_st = round(float(cp_val) + float(ltd_curr), 2)
                    if combined_st > st_debt:
                        st_debt = combined_st

                # Para empresas con tramos específicos de pagarés, notas y préstamos (ej. REITs)
                # que presentan NotesPayable + LoansPayable + SecuredDebt por separado sin un total consolidado
                notes_p = get_first_matching_value(bal_data, ["NotesPayable", "us-gaap_NotesPayable", "SeniorNotes"], p) or 0.0
                loans_p = get_first_matching_value(bal_data, ["LoansPayable", "us-gaap_LoansPayable", "TermLoans"], p) or 0.0
                sec_debt = get_first_matching_value(bal_data, ["SecuredDebt", "us-gaap_SecuredDebt", "MortgageLoansPayable", "MortgagesPayable"], p) or 0.0
                revolving_p = get_first_matching_value(bal_data, ["RevolvingCreditFacilityAndCommercialPaper", "LinesOfCreditCurrent", "LineOfCreditAndCommercialPaper"], p) or 0.0

                tranche_sum = notes_p + loans_p + sec_debt
                if tranche_sum > lt_debt:
                    lt_debt = round(tranche_sum, 2)
                if revolving_p > st_debt:
                    st_debt = round(revolving_p, 2)

                tot_debt = round(st_debt + lt_debt, 2)
            canonical["short_term_debt"][p] = st_debt
            canonical["long_term_debt"][p] = lt_debt
            canonical["total_debt"][p] = tot_debt
            canonical["net_debt"][p] = round(tot_debt - tot_liquid_cash, 2)
            
            # Activos y pasivos corrientes y PP&E neto
            curr_assets = get_first_matching_value(bal_data, XBRL_TAXONOMY_MAP["current_assets"], p)
            if curr_assets is None and facts_df is not None:
                curr_assets = get_fact_fallback(facts_df, XBRL_TAXONOMY_MAP["current_assets"], p)
            canonical["current_assets"][p] = curr_assets

            curr_liab = get_first_matching_value(bal_data, XBRL_TAXONOMY_MAP["current_liabilities"], p)
            if curr_liab is None and facts_df is not None:
                curr_liab = get_fact_fallback(facts_df, XBRL_TAXONOMY_MAP["current_liabilities"], p)
            canonical["current_liabilities"][p] = curr_liab

            rou_asset = get_first_matching_value(bal_data, XBRL_TAXONOMY_MAP["operating_lease_rou_asset"], p)
            if rou_asset is None and facts_df is not None:
                rou_asset = get_fact_fallback(facts_df, XBRL_TAXONOMY_MAP["operating_lease_rou_asset"], p)
            canonical["operating_lease_rou_asset"][p] = rou_asset

            accrued_liab = get_first_matching_value(bal_data, XBRL_TAXONOMY_MAP["accrued_liabilities"], p)
            if accrued_liab is None and facts_df is not None:
                accrued_liab = get_fact_fallback(facts_df, XBRL_TAXONOMY_MAP["accrued_liabilities"], p)
            canonical["accrued_liabilities"][p] = accrued_liab

            net_ppe = get_first_matching_value(bal_data, XBRL_TAXONOMY_MAP["net_ppe"], p)
            if net_ppe is None and facts_df is not None:
                net_ppe = get_fact_fallback(facts_df, XBRL_TAXONOMY_MAP["net_ppe"], p)
            canonical["net_ppe"][p] = net_ppe

            # Capital de Trabajo Operativo Neto (NWC)
            op_ca = max(0.0, (curr_assets or 0.0) - cash) if curr_assets is not None else None
            op_cl = max(0.0, (curr_liab or 0.0) - st_debt) if curr_liab is not None else None
            op_nwc = (op_ca - op_cl) if (op_ca is not None and op_cl is not None) else None
            canonical["net_working_capital"][p] = op_nwc

            # Capital Tangible Operativo (Greenblatt) = NWC + Net PP&E
            tangible_cap = None
            if net_ppe is not None:
                if op_nwc is not None:
                    tangible_cap = max(net_ppe, op_nwc + net_ppe) if op_nwc < 0 else (op_nwc + net_ppe)
                else:
                    tangible_cap = net_ppe
            elif op_nwc is not None and op_nwc > 0:
                tangible_cap = op_nwc
            canonical["tangible_capital_employed"][p] = tangible_cap

            if archetype == "PLATFORM_ECOSYSTEM":
                dep = get_first_matching_value(bal_data, BANKING_TAXONOMY_MAP["total_deposits"], p)
                canonical["total_deposits"][p] = dep
                tot_l = get_first_matching_value(bal_data, BANKING_TAXONOMY_MAP["net_loans"], p)
                if tot_l is None:
                    nl_c = get_first_matching_value(bal_data, ["NotesAndLoansReceivableNetCurrent", "us-gaap_NotesAndLoansReceivableNetCurrent"], p) or 0.0
                    nl_nc = get_first_matching_value(bal_data, ["NotesAndLoansReceivableNetNoncurrent", "us-gaap_NotesAndLoansReceivableNetNoncurrent"], p) or 0.0
                    if (nl_c + nl_nc) > 0:
                        tot_l = round(nl_c + nl_nc, 2)
                canonical["net_loans"][p] = tot_l

                allow_l = get_first_matching_value(bal_data, BANKING_TAXONOMY_MAP["allowance_for_credit_losses"], p)
                if allow_l is None and facts_df is not None:
                    allow_l = get_fact_fallback(facts_df, BANKING_TAXONOMY_MAP["allowance_for_credit_losses"], p, is_flow=False)
                canonical["allowance_for_credit_losses"][p] = abs(allow_l) if allow_l is not None else None
                canonical["borrowings"][p] = get_first_matching_value(bal_data, BANKING_TAXONOMY_MAP["long_term_debt"], p)

        # --- Ratios Financieros ---
        if rev and rev > 0:
            if gp is not None:
                ratios["gross_margin_pct"][p] = round((gp / rev) * 100, 2)
            else:
                ratios["gross_margin_pct"][p] = None

            if ebit is not None:
                ratios["operating_margin_pct"][p] = round((ebit / rev) * 100, 2)
            if ni is not None:
                ratios["net_margin_pct"][p] = round((ni / rev) * 100, 2)
            if fcf is not None:
                ratios["fcf_margin_pct"][p] = round((fcf / rev) * 100, 2)
            else:
                ratios["fcf_margin_pct"][p] = None
        else:
            ratios["gross_margin_pct"][p] = None
            ratios["fcf_margin_pct"][p] = None
                
        if ni is not None and ni != 0 and fcf is not None:
            ratios["fcf_conversion_pct"][p] = round((fcf / ni) * 100, 2)
        else:
            ratios["fcf_conversion_pct"][p] = None
            
        if ni is not None and equity and equity > 0:
            ratios["roe_pct"][p] = round((ni / equity) * 100, 2)
            
        if ni is not None and assets and assets > 0:
            ratios["roa_pct"][p] = round((ni / assets) * 100, 2)
            
        if archetype in ("FINANCIAL_BANKING", "INSURANCE"):
            ratios["gross_margin_pct"][p] = None
            ratios["fcf_margin_pct"][p] = None
            ratios["fcf_conversion_pct"][p] = None
            ratios["roc_greenblatt_pct"][p] = None
            ratios["current_ratio"][p] = None
            if archetype == "FINANCIAL_BANKING":
                if rev and rev > 0 and op_exp is not None:
                    ratios["efficiency_ratio_pct"] = ratios.get("efficiency_ratio_pct", {})
                    ratios["efficiency_ratio_pct"][p] = round((abs(op_exp) / rev) * 100, 2)
                if rev and rev > 0 and clp is not None:
                    ratios["cost_of_risk_pct"] = ratios.get("cost_of_risk_pct", {})
                    ratios["cost_of_risk_pct"][p] = round((abs(clp) / rev) * 100, 2)
                if nii is not None and assets and assets > 0:
                    clp_val = abs(clp) if clp is not None else 0.0
                    ratios["risk_adj_nim_pct"] = ratios.get("risk_adj_nim_pct", {})
                    ratios["risk_adj_nim_pct"][p] = round(((nii - clp_val) / assets) * 100, 2)
                if tot_l and dep and dep > 0:
                    ratios["ldr_pct"] = ratios.get("ldr_pct", {})
                    ratios["ldr_pct"][p] = round((tot_l / dep) * 100, 2)
                if non_ii is not None and rev and rev > 0:
                    ratios["fee_share_pct"] = ratios.get("fee_share_pct", {})
                    ratios["fee_share_pct"][p] = round((non_ii / rev) * 100, 2)
                if clp is not None and tot_l and tot_l > 0:
                    ratios["cost_of_risk_loans_pct"] = ratios.get("cost_of_risk_loans_pct", {})
                    ratios["cost_of_risk_loans_pct"][p] = round((abs(clp) / tot_l) * 100, 2)
                if assets and equity and equity > 0:
                    ratios["financial_leverage"] = ratios.get("financial_leverage", {})
                    ratios["financial_leverage"][p] = round(assets / equity, 2)
                if rev and assets and assets > 0:
                    ratios["asset_turnover"] = ratios.get("asset_turnover", {})
                    ratios["asset_turnover"][p] = round(rev / assets, 4)
        else:
            if curr_assets is not None and curr_liab and curr_liab > 0:
                ratios["current_ratio"][p] = round(curr_assets / curr_liab, 2)
            if archetype == "REAL_ESTATE_REIT":
                if rev and rev > 0 and noi is not None:
                    ratios["noi_margin_pct"] = ratios.get("noi_margin_pct", {})
                    ratios["noi_margin_pct"][p] = round((noi / rev) * 100, 2)
                sh_d = canonical["shares_diluted"].get(p)
                if sh_d and sh_d > 0:
                    if ffo is not None:
                        ratios["ffo_per_share"] = ratios.get("ffo_per_share", {})
                        ratios["ffo_per_share"][p] = round(ffo / sh_d, 2)
                    if affo is not None:
                        ratios["affo_per_share"] = ratios.get("affo_per_share", {})
                        ratios["affo_per_share"][p] = round(affo / sh_d, 2)
            
        if tot_debt is not None and equity and equity > 0:
            ratios["debt_to_equity"][p] = round(tot_debt / equity, 2)
            
    # -------------------------------------------------------------
    # CÁLCULO INSTITUCIONAL DE RETORNOS CON BALANCES PROMEDIO ((t + t-1) / 2)
    # Estándar de correspondencia temporal institucional (FactSet / Bloomberg)
    # -------------------------------------------------------------
    annual_periods = [p for p in periods if p != "LTM"]
    ratios["roa_ending_pct"] = dict(ratios["roa_pct"])
    ratios["roe_ending_pct"] = dict(ratios["roe_pct"])
    ratios["roa_avg_pct"] = {}
    ratios["roe_avg_pct"] = {}

    for p in periods:
        ni = canonical["net_income"].get(p)
        a_curr = canonical["total_assets"].get(p)
        e_curr = canonical["stockholders_equity"].get(p)

        a_prev = None
        e_prev = None
        if p == "LTM":
            if annual_periods:
                a_prev = canonical["total_assets"].get(annual_periods[0])
                e_prev = canonical["stockholders_equity"].get(annual_periods[0])
        else:
            if p in annual_periods:
                idx = annual_periods.index(p)
                if idx + 1 < len(annual_periods):
                    a_prev = canonical["total_assets"].get(annual_periods[idx + 1])
                    e_prev = canonical["stockholders_equity"].get(annual_periods[idx + 1])

        a_avg = (a_curr + a_prev) / 2.0 if (a_curr and a_prev and a_prev > 0) else a_curr
        e_avg = (e_curr + e_prev) / 2.0 if (e_curr and e_prev and e_prev > 0) else e_curr

        if ni is not None:
            if a_avg and a_avg > 0:
                calc_roa_avg = round((ni / a_avg) * 100, 2)
                ratios["roa_avg_pct"][p] = calc_roa_avg
                ratios["roa_pct"][p] = calc_roa_avg
            if e_avg and e_avg > 0:
                calc_roe_avg = round((ni / e_avg) * 100, 2)
                ratios["roe_avg_pct"][p] = calc_roe_avg
                ratios["roe_pct"][p] = calc_roe_avg

        # ROC Greenblatt (EBIT / Capital Tangible Operativo Promedio)
        ebit = canonical["operating_income"].get(p)
        tc_curr = canonical["tangible_capital_employed"].get(p)
        tc_prev = None
        if p == "LTM":
            if annual_periods:
                tc_prev = canonical["tangible_capital_employed"].get(annual_periods[0])
        else:
            if p in annual_periods:
                idx = annual_periods.index(p)
                if idx + 1 < len(annual_periods):
                    tc_prev = canonical["tangible_capital_employed"].get(annual_periods[idx + 1])

        tc_avg = (tc_curr + tc_prev) / 2.0 if (tc_curr and tc_prev and tc_prev > 0) else tc_curr
        ratios["tangible_capital_usd"][p] = tc_avg

        if not is_financial:
            if ebit is not None and tc_avg and tc_avg > 0:
                ratios["roc_greenblatt_pct"][p] = round((ebit / tc_avg) * 100, 2)
            elif ebit is not None and tc_curr and tc_curr > 0:
                ratios["roc_greenblatt_pct"][p] = round((ebit / tc_curr) * 100, 2)
            else:
                ratios["roc_greenblatt_pct"][p] = None
        else:
            ratios["roc_greenblatt_pct"][p] = None
            
    # -------------------------------------------------------------
    # DETECCIÓN Y NORMALIZACIÓN AUTOMÁTICA DE STOCK SPLITS
    # -------------------------------------------------------------
    annual_periods = [p for p in periods if p != "LTM"]
    split_factors = {p: 1.0 for p in periods}
    current_factor = 1.0
    
    for i in range(len(annual_periods) - 1):
        p_now = annual_periods[i]
        p_prev = annual_periods[i + 1]
        
        sh_now = canonical["shares_diluted"].get(p_now)
        sh_prev = canonical["shares_diluted"].get(p_prev)
        
        if sh_now and sh_prev and sh_prev > 0:
            ratio = sh_now / sh_prev
            split_cand = None
            for s_int in [2, 3, 4, 5, 6, 7, 10, 20]:
                if (s_int * 0.85) <= ratio <= (s_int * 1.15):
                    split_cand = float(s_int)
                    break
            if split_cand is None:
                for s_rev in [2, 3, 4, 5, 10]:
                    if ((1.0 / s_rev) * 0.85) <= ratio <= ((1.0 / s_rev) * 1.15):
                        split_cand = 1.0 / s_rev
                        break
                        
            if split_cand is not None:
                current_factor *= split_cand
                print(f"[SEC Extractor] Evento de Stock Split detectado entre {p_prev} y {p_now}: Factor {split_cand}:1 (Factor acumulado retroactivo para ejercicios <= {p_prev}: {current_factor}x)")
                
        split_factors[p_prev] = current_factor
        
    canonical["split_adjustment_factor"] = split_factors
    canonical["shares_basic_adjusted"] = {}
    canonical["shares_diluted_adjusted"] = {}
    canonical["eps_basic_adjusted"] = {}
    canonical["eps_diluted_adjusted"] = {}
    canonical["dps_adjusted"] = {}
    
    for p in periods:
        fac = split_factors.get(p, 1.0)
        
        sb = canonical["shares_basic"].get(p)
        sd = canonical["shares_diluted"].get(p)
        canonical["shares_basic_adjusted"][p] = round(sb * fac, 0) if sb is not None else None
        canonical["shares_diluted_adjusted"][p] = round(sd * fac, 0) if sd is not None else None
        
        ni_val = canonical["net_income"].get(p)
        adj_sd = canonical["shares_diluted_adjusted"].get(p)
        adj_sb = canonical["shares_basic_adjusted"].get(p)
        
        if canonical["eps_diluted"].get(p) is not None:
            canonical["eps_diluted_adjusted"][p] = round(canonical["eps_diluted"][p] / fac, 2)
        elif ni_val is not None and adj_sd and adj_sd > 0:
            canonical["eps_diluted_adjusted"][p] = round(ni_val / adj_sd, 2)
        else:
            canonical["eps_diluted_adjusted"][p] = None
            
        if canonical["eps_basic"].get(p) is not None:
            canonical["eps_basic_adjusted"][p] = round(canonical["eps_basic"][p] / fac, 2)
        elif ni_val is not None and adj_sb and adj_sb > 0:
            canonical["eps_basic_adjusted"][p] = round(ni_val / adj_sb, 2)
        else:
            canonical["eps_basic_adjusted"][p] = None

        dps_raw = canonical.get("dps", {}).get(p)
        if dps_raw is not None:
            canonical["dps_adjusted"][p] = round(dps_raw / fac, 4)
        else:
            canonical["dps_adjusted"][p] = None

        # Reconciliación institucional de identidades contables universales (Gross Profit, OpEx, FCF, Net Debt)
        reconcile_accounting_identities(canonical, p, archetype)

    # -------------------------------------------------------------
    # UNIDADES BASE ESTRICTAS Y SANITIZACIÓN NUMÉRICA
    # Garantizar que todos los valores en canonical_summary sean floats en
    # unidades base absolutas (sin prefijos) o None.
    # -------------------------------------------------------------
    for k in list(canonical.keys()):
        for p in periods:
            v = canonical[k].get(p)
            if v is not None and not pd.isna(v) and str(v).lower() != 'nan':
                try:
                    canonical[k][p] = float(v)
                except (ValueError, TypeError):
                    canonical[k][p] = None
            else:
                canonical[k][p] = None

    return canonical, ratios
