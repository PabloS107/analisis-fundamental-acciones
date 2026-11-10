"""
sec_canonical_builder.py - Constructor del resumen canónico (canonical_summary),
ratios financieros adaptados por arquetipo contable, retornos sobre balances promedio
y detección/ajuste retroactivo de Stock Splits.
"""

import logging
import pandas as pd

try:
    from financial_taxonomy import (
        BANKING_TAXONOMY_MAP,
        REIT_TAXONOMY_MAP,
        INSURANCE_TAXONOMY_MAP,
        XBRL_TAXONOMY_MAP,
        get_first_matching_value,
        reconcile_accounting_identities,
    )
except ImportError:
    try:
        from ..financial_taxonomy import (
            BANKING_TAXONOMY_MAP,
            REIT_TAXONOMY_MAP,
            INSURANCE_TAXONOMY_MAP,
            XBRL_TAXONOMY_MAP,
            get_first_matching_value,
            reconcile_accounting_identities,
        )
    except ImportError:
        from pipeline.financial_taxonomy import (
            BANKING_TAXONOMY_MAP,
            REIT_TAXONOMY_MAP,
            INSURANCE_TAXONOMY_MAP,
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

logger = logging.getLogger(__name__)


def _lookup_metric(stmt_data, concepts, period, facts_df=None, is_flow=False):
    """Obtiene el primer valor disponible en el estado XBRL o recurre a CompanyFacts."""
    val = get_first_matching_value(stmt_data, concepts, period)
    if val is None and facts_df is not None and concepts:
        val = get_fact_fallback(facts_df, concepts, period, is_flow=is_flow)
    return val


def _init_canonical_containers(is_financial, archetype):
    """Inicializa las estructuras vacías canonical y ratios según el arquetipo contable."""
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
        "non_operating_income": {},
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
        "tangible_capital_usd": {},
    }
    return canonical, ratios


def _extract_banking_pnl_period(canonical, inc_data, facts_df, p):
    """Extrae la sección superior del P&L para entidades bancarias."""
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
        rev = _lookup_metric(inc_data, XBRL_TAXONOMY_MAP["revenue"], p, facts_df, is_flow=True)
    canonical["revenue"][p] = rev

    clp = get_first_matching_value(inc_data, BANKING_TAXONOMY_MAP["credit_loss_provisions"], p)
    if clp is not None:
        clp = -abs(clp)
    canonical["credit_loss_provisions"][p] = clp
    canonical["cost_of_goods_sold"][p] = None
    canonical["gross_profit"][p] = None

    op_exp = get_first_matching_value(inc_data, BANKING_TAXONOMY_MAP["operating_expenses"], p)
    if op_exp is not None:
        op_exp = abs(op_exp)
    canonical["operating_expenses"][p] = op_exp


def _extract_reit_pnl_period(canonical, inc_data, cf_data, facts_df, p):
    """Extrae la sección superior del P&L y partidas D&A/CapEx para REITs."""
    tot_rev_cands = REIT_TAXONOMY_MAP.get("total_revenue", XBRL_TAXONOMY_MAP["revenue"])
    tot_rev = _lookup_metric(inc_data, tot_rev_cands, p, facts_df, is_flow=True)
    rent_rev = _lookup_metric(inc_data, REIT_TAXONOMY_MAP["rental_revenue"], p, facts_df, is_flow=True)
    if rent_rev is None:
        rent_rev = tot_rev
    if tot_rev is None:
        tot_rev = rent_rev

    canonical["rental_revenue"][p] = rent_rev
    canonical["revenue"][p] = tot_rev
    canonical["cost_of_goods_sold"][p] = None

    prop_exp = _lookup_metric(inc_data, REIT_TAXONOMY_MAP["property_operating_expenses"], p, facts_df, is_flow=True)
    canonical["property_operating_expenses"][p] = prop_exp

    noi = None
    if rent_rev is not None and prop_exp is not None:
        noi = round(rent_rev - abs(prop_exp), 2)
    elif rent_rev is not None:
        noi = rent_rev
    canonical["noi"][p] = noi
    canonical["gross_profit"][p] = noi

    op_exp = get_first_matching_value(inc_data, XBRL_TAXONOMY_MAP["operating_expenses"], p)
    if op_exp is None:
        op_exp = prop_exp
    if op_exp is not None:
        op_exp = abs(op_exp)
    canonical["operating_expenses"][p] = op_exp

    re_dep = get_first_matching_value(inc_data, REIT_TAXONOMY_MAP["real_estate_depreciation"], p)
    if re_dep is None:
        re_dep = get_first_matching_value(cf_data, REIT_TAXONOMY_MAP["real_estate_depreciation"], p)
    if re_dep is None and facts_df is not None:
        re_dep = get_fact_fallback(facts_df, REIT_TAXONOMY_MAP["real_estate_depreciation"], p, is_flow=True)
    canonical["real_estate_depreciation"][p] = abs(re_dep) if re_dep is not None else None

    gain_sale = _lookup_metric(inc_data, REIT_TAXONOMY_MAP["gain_loss_sale_properties"], p, facts_df, is_flow=True)
    canonical["gain_loss_sale_properties"][p] = gain_sale

    rec_capex = _lookup_metric(cf_data, REIT_TAXONOMY_MAP["recurring_capex_maintenance"], p, facts_df, is_flow=True)
    canonical["recurring_capex_maintenance"][p] = abs(rec_capex) if rec_capex is not None else None


def _extract_insurance_pnl_period(canonical, inc_data, facts_df, p):
    """Extrae ingresos, siniestros y gastos de suscripción para aseguradoras."""
    tot_rev = _lookup_metric(
        inc_data,
        INSURANCE_TAXONOMY_MAP.get("total_revenue", XBRL_TAXONOMY_MAP["revenue"]),
        p,
        facts_df,
        is_flow=True,
    )
    prem_earned = _lookup_metric(inc_data, INSURANCE_TAXONOMY_MAP["net_premiums_earned"], p, facts_df, is_flow=True)
    canonical["net_premiums_earned"][p] = prem_earned

    inv_inc = _lookup_metric(inc_data, INSURANCE_TAXONOMY_MAP["net_investment_income"], p, facts_df, is_flow=True)
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
    canonical["cost_of_goods_sold"][p] = None
    canonical["gross_profit"][p] = None

    op_exp = get_first_matching_value(inc_data, XBRL_TAXONOMY_MAP["operating_expenses"], p)
    if op_exp is None:
        op_exp = get_first_matching_value(
            inc_data,
            ["BenefitsLossesAndExpenses", "us-gaap_BenefitsLossesAndExpenses", "PolicyholderBenefitsAndClaimsAndExpenses"],
            p,
        )
    if op_exp is not None:
        op_exp = abs(op_exp)
    canonical["operating_expenses"][p] = op_exp

    losses = _lookup_metric(inc_data, INSURANCE_TAXONOMY_MAP["losses_and_loss_expenses"], p, facts_df, is_flow=True)
    canonical["losses_and_loss_expenses"][p] = abs(losses) if losses is not None else None

    acq_costs = _lookup_metric(inc_data, INSURANCE_TAXONOMY_MAP["acquisition_costs"], p, facts_df, is_flow=True)
    canonical["acquisition_costs"][p] = abs(acq_costs) if acq_costs is not None else None

    other_und = _lookup_metric(inc_data, INSURANCE_TAXONOMY_MAP["other_underwriting_expenses"], p, facts_df, is_flow=True)
    canonical["other_underwriting_expenses"][p] = abs(other_und) if other_und is not None else None

    tot_und = (abs(acq_costs) if acq_costs else 0.0) + (abs(other_und) if other_und else 0.0)
    if tot_und > 0 and prem_earned is not None and losses is not None:
        canonical["underwriting_profit"][p] = round(prem_earned - abs(losses) - tot_und, 2)
    else:
        canonical["underwriting_profit"][p] = None


def _extract_corporate_pnl_period(canonical, inc_data, facts_df, p, archetype):
    """Extrae la sección superior del P&L para corporativas y plataformas fintech."""
    rev = _lookup_metric(inc_data, XBRL_TAXONOMY_MAP["revenue"], p, facts_df, is_flow=True)
    canonical["revenue"][p] = rev

    cogs = _lookup_metric(inc_data, XBRL_TAXONOMY_MAP["cost_of_goods_sold"], p, facts_df, is_flow=True)
    if cogs is not None:
        cogs = abs(cogs)
    canonical["cost_of_goods_sold"][p] = cogs

    gp = get_first_matching_value(inc_data, XBRL_TAXONOMY_MAP["gross_profit"], p)
    if gp is None and rev is not None and cogs is not None:
        gp = round(rev - cogs, 2)
    canonical["gross_profit"][p] = gp

    op_exp = _lookup_metric(inc_data, XBRL_TAXONOMY_MAP["operating_expenses"], p, facts_df, is_flow=True)
    if op_exp is not None:
        op_exp = abs(op_exp)
    canonical["operating_expenses"][p] = op_exp

    rd_cands = XBRL_TAXONOMY_MAP.get("rd_expense", ["ResearchAndDevelopmentExpense"])
    rd_val = _lookup_metric(inc_data, rd_cands, p, facts_df, is_flow=True)
    canonical["rd_expense"][p] = abs(rd_val) if rd_val is not None else None

    sm_v = _lookup_metric(inc_data, XBRL_TAXONOMY_MAP.get("sm_expense", ["SellingAndMarketingExpense"]), p, facts_df, is_flow=True)
    ga_v = _lookup_metric(inc_data, XBRL_TAXONOMY_MAP.get("ga_expense", ["GeneralAndAdministrativeExpense"]), p, facts_df, is_flow=True)
    canonical["sm_expense"][p] = abs(sm_v) if sm_v is not None else None
    canonical["ga_expense"][p] = abs(ga_v) if ga_v is not None else None

    sga_cands = XBRL_TAXONOMY_MAP.get("sga_expense", ["SellingGeneralAndAdministrativeExpense"])
    sga_val = _lookup_metric(inc_data, sga_cands, p, facts_df, is_flow=True)
    if sga_val is None and (sm_v is not None or ga_v is not None):
        sga_val = (abs(sm_v) if sm_v else 0.0) + (abs(ga_v) if ga_v else 0.0)
    canonical["sga_expense"][p] = abs(sga_val) if sga_val is not None else None

    # Si es PLATFORM_ECOSYSTEM, registrar provisiones de crédito e ingresos financieros sin contaminar margen comercial
    if archetype == "PLATFORM_ECOSYSTEM":
        clp = get_first_matching_value(inc_data, BANKING_TAXONOMY_MAP["credit_loss_provisions"], p)
        canonical["credit_loss_provisions"][p] = -abs(clp) if clp is not None else None
        canonical["interest_income"][p] = get_first_matching_value(inc_data, BANKING_TAXONOMY_MAP["interest_income"], p)
        canonical["interest_expense"][p] = get_first_matching_value(inc_data, BANKING_TAXONOMY_MAP["interest_expense"], p)
        canonical["net_interest_income"][p] = get_first_matching_value(inc_data, BANKING_TAXONOMY_MAP["net_interest_income"], p)
        canonical["non_interest_income"][p] = get_first_matching_value(inc_data, BANKING_TAXONOMY_MAP["non_interest_income"], p)


def _extract_ebit_and_non_op_period(canonical, inc_data, cf_data, facts_df, p, archetype):
    """Extrae EBIT, gasto por intereses, EBT, impuesto, beneficio neto y neto común."""
    rev = canonical["revenue"].get(p)
    gp = canonical["gross_profit"].get(p)
    op_exp = canonical["operating_expenses"].get(p)

    if archetype == "FINANCIAL_BANKING":
        ebit = None
    elif archetype == "REAL_ESTATE_REIT":
        da_val = get_first_matching_value(cf_data, ["DepreciationDepletionAndAmortization", "DepreciationAndAmortization"], p) or 0.0
        ga_val = get_first_matching_value(inc_data, ["GeneralAndAdministrativeExpense", "SellingGeneralAndAdministrativeExpense"], p) or 0.0
        imp_val = get_first_matching_value(inc_data, ["ImpairmentOfRealEstate", "AssetImpairmentCharges"], p) or 0.0
        prop_exp_val = get_first_matching_value(
            inc_data,
            [
                "DirectCostsOfLeasedAndRentedPropertyOrEquipment",
                "o_DirectCostsOfLeasedAndRentedPropertyOrEquipmentIncludingReimbursableExpense",
            ],
            p,
        ) or 0.0
        if rev is not None:
            noi_val = round(rev - abs(prop_exp_val), 2)
            ebit = round(noi_val - abs(da_val) - abs(ga_val) - abs(imp_val), 2)
        else:
            ebit = None
    else:
        ebit = _lookup_metric(inc_data, XBRL_TAXONOMY_MAP["operating_income"], p, facts_df, is_flow=True)
        if ebit is None and rev is not None and op_exp is not None and abs(op_exp) > 0:
            ebit = round(rev - abs(op_exp), 2)
    canonical["operating_income"][p] = ebit

    if gp is not None and ebit is not None and archetype not in ("FINANCIAL_BANKING", "INSURANCE", "REAL_ESTATE_REIT"):
        expected_opex = round(gp - ebit, 2)
        cur_opex = canonical["operating_expenses"].get(p)
        if expected_opex > 0 and (cur_opex is None or abs(cur_opex - expected_opex) > max(expected_opex * 0.01, 5.0)):
            canonical["operating_expenses"][p] = expected_opex

    if archetype not in ("FINANCIAL_BANKING", "PLATFORM_ECOSYSTEM"):
        ie_val = _lookup_metric(inc_data, XBRL_TAXONOMY_MAP.get("interest_expense", ["InterestExpense"]), p, facts_df, is_flow=True)
        if ie_val is None:
            ie_val = get_first_matching_value(cf_data, ["InterestPaidNet", "InterestPaid", "us-gaap_InterestPaidNet"], p)
        canonical["interest_expense"][p] = abs(ie_val) if ie_val is not None else None

    ni = _lookup_metric(inc_data, XBRL_TAXONOMY_MAP["net_income"], p, facts_df, is_flow=True)
    canonical["net_income"][p] = ni

    tax_val = _lookup_metric(
        inc_data,
        XBRL_TAXONOMY_MAP.get("income_tax", ["IncomeTaxExpenseBenefit", "IncomeTaxExpenseContinuingOperations"]),
        p,
        facts_df,
        is_flow=True,
    )
    canonical["income_tax"][p] = abs(tax_val) if tax_val is not None else None

    ebt_cands = XBRL_TAXONOMY_MAP.get(
        "ebt",
        [
            "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
            "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
            "IncomeLossAttributableToParent",
            "us-gaap_IncomeLossAttributableToParent",
            "IncomeLossBeforeIncomeTaxExpenseBenefit",
            "ProfitLossBeforeTax",
        ],
    )
    ebt_val = _lookup_metric(inc_data, ebt_cands, p, facts_df, is_flow=True)
    if ebt_val is None and ni is not None and tax_val is not None:
        ebt_val = round(ni + abs(tax_val), 2)
    canonical["ebt"][p] = ebt_val

    ii_cands = XBRL_TAXONOMY_MAP.get("interest_income", ["InvestmentIncomeInterest", "InterestIncomeOperating", "InterestIncome"])
    ii_val = _lookup_metric(inc_data, ii_cands, p, facts_df, is_flow=True)
    canonical["interest_income"][p] = abs(ii_val) if ii_val is not None else None

    if ebt_val is not None and ebit is not None and archetype not in ("FINANCIAL_BANKING", "INSURANCE", "REAL_ESTATE_REIT"):
        canonical["non_operating_income"][p] = round(ebt_val - ebit, 2)
    else:
        noi_cands = XBRL_TAXONOMY_MAP.get("non_operating_income", ["NonoperatingIncomeExpense", "InterestRevenueExpenseNet"])
        canonical["non_operating_income"][p] = _lookup_metric(inc_data, noi_cands, p, facts_df, is_flow=True)

    ni_comm_cands = XBRL_TAXONOMY_MAP.get("net_income_common", [])
    ni_comm = _lookup_metric(inc_data, ni_comm_cands, p, facts_df, is_flow=True)
    canonical["net_income_common"][p] = ni_comm if ni_comm is not None else ni


def _extract_shares_and_eps_period(canonical, inc_data, facts_df, periods, p):
    """Extrae acciones ponderadas y BPA básico/diluido, con calibración LTM."""
    ni = canonical["net_income"].get(p)
    sh_basic_cands = XBRL_TAXONOMY_MAP["shares_basic"]
    sh_diluted_cands = XBRL_TAXONOMY_MAP["shares_diluted"]
    sh_basic = _lookup_metric(inc_data, sh_basic_cands, p, facts_df, is_flow=False)
    sh = _lookup_metric(inc_data, sh_diluted_cands, p, facts_df, is_flow=False)
    canonical["shares_basic"][p] = sh_basic
    canonical["shares_diluted"][p] = sh

    eps_b_cands = XBRL_TAXONOMY_MAP["eps_basic"]
    eps_d_cands = XBRL_TAXONOMY_MAP["eps_diluted"]
    eps_b = _lookup_metric(inc_data, eps_b_cands, p, facts_df, is_flow=True)
    eps_d = _lookup_metric(inc_data, eps_d_cands, p, facts_df, is_flow=True)

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
        q4_eps_d = get_ltm_quarterly_metric(facts_df, eps_d_cands, mode="sum") if facts_df is not None else None
        q4_eps_b = get_ltm_quarterly_metric(facts_df, eps_b_cands, mode="sum") if facts_df is not None else None

        ni_for_eps = canonical["net_income_common"].get(p) or ni
        if q4_eps_d is not None and q4_eps_d > 0:
            eps_d = q4_eps_d
        elif ni_for_eps is not None and sh and sh > 0:
            eps_d = round(ni_for_eps / sh, 2)

        if q4_eps_b is not None and q4_eps_b > 0:
            eps_b = q4_eps_b
        elif ni_for_eps is not None and sh_basic and sh_basic > 0:
            eps_b = round(ni_for_eps / sh_basic, 2)

        q4_sh = get_ltm_quarterly_metric(facts_df, sh_diluted_cands, mode="avg") if facts_df is not None else None
        if q4_sh is not None and q4_sh > 0:
            sh = q4_sh
            canonical["shares_diluted"][p] = sh
        elif eps_d is not None and eps_d > 0 and ni_for_eps is not None and ni_for_eps > 0:
            implied_sh = round(ni_for_eps / eps_d)
            if not sh or sh <= 0 or abs(implied_sh - sh) / sh > 0.005:
                sh = float(implied_sh)
                canonical["shares_diluted"][p] = sh

        q4_sh_b = get_ltm_quarterly_metric(facts_df, sh_basic_cands, mode="avg") if facts_df is not None else None
        if q4_sh_b is not None and q4_sh_b > 0:
            sh_basic = q4_sh_b
            canonical["shares_basic"][p] = sh_basic
        elif eps_b is not None and eps_b > 0 and ni_for_eps is not None and ni_for_eps > 0:
            implied_sh_b = round(ni_for_eps / eps_b)
            if not sh_basic or sh_basic <= 0 or abs(implied_sh_b - sh_basic) / sh_basic > 0.005:
                sh_basic = float(implied_sh_b)
                canonical["shares_basic"][p] = sh_basic
        elif sh_basic is None and sh is not None and sh > 0:
            prev_fys = [f for f in periods if f != "LTM"]
            if prev_fys:
                p_prior = prev_fys[0]
                prior_sb = canonical["shares_basic"].get(p_prior)
                prior_sd = canonical["shares_diluted"].get(p_prior)
                if prior_sb and prior_sd and prior_sd > 0:
                    sh_basic = round(sh * min(1.0, prior_sb / prior_sd))
                else:
                    sh_basic = sh
            else:
                sh_basic = sh
            canonical["shares_basic"][p] = sh_basic

        if eps_b is None and ni_for_eps is not None and sh_basic and sh_basic > 0:
            eps_b = round(ni_for_eps / sh_basic, 2)

    canonical["eps_basic"][p] = eps_b
    canonical["eps_diluted"][p] = eps_d


def _sync_net_repurchases(canonical, period):
    """Sincroniza share_repurchases_gross y share_repurchases_net para un período."""
    gross = canonical["share_repurchases"][period]
    proceeds = canonical["stock_plans_proceeds"][period]
    canonical["share_repurchases_gross"][period] = gross
    if gross is not None and proceeds is not None:
        canonical["share_repurchases_net"][period] = max(0.0, round(gross - proceeds, 2))
    elif gross is not None:
        canonical["share_repurchases_net"][period] = gross
    else:
        canonical["share_repurchases_net"][period] = None


def _populate_insurance_underwriting_ratios(canonical, ratios, p):
    """Calcula loss ratio, expense ratio y combined ratio para aseguradoras."""
    prem_e = canonical["net_premiums_earned"].get(p)
    loss_v = canonical["losses_and_loss_expenses"].get(p)
    acq_v = canonical["acquisition_costs"].get(p)
    other_u = canonical["other_underwriting_expenses"].get(p)
    op_exp = canonical["operating_expenses"].get(p)

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
    ratios.setdefault("loss_ratio_pct", {})[p] = loss_r
    ratios.setdefault("expense_ratio_pct", {})[p] = exp_r
    ratios.setdefault("combined_ratio_pct", {})[p] = comb_r


def _extract_cash_flow_and_cap_alloc_period(canonical, ratios, cf_data, facts_df, p, archetype):
    """Extrae CFO, CapEx, FCF/FFO/AFFO y asignación de capital de financiamiento/M&A."""
    ni = canonical["net_income"].get(p)
    cfo = _lookup_metric(cf_data, XBRL_TAXONOMY_MAP["cash_from_operations"], p, facts_df, is_flow=True)
    canonical["cash_from_operations"][p] = cfo

    capex_cands = XBRL_TAXONOMY_MAP["capital_expenditures"]
    capex_raw = _lookup_metric(cf_data, capex_cands, p, facts_df, is_flow=True)
    if (capex_raw is None or capex_raw == 0.0) and p == "LTM":
        for cand in capex_cands:
            alt_c = get_first_matching_value(cf_data, [cand], p)
            if alt_c is not None and alt_c != 0.0:
                capex_raw = alt_c
                break

    if archetype == "REAL_ESTATE_REIT":
        re_acq = _lookup_metric(cf_data, REIT_TAXONOMY_MAP["real_estate_acquisitions"], p, facts_df, is_flow=True)
        canonical["real_estate_acquisitions"][p] = abs(re_acq) if re_acq is not None else None
        rec_maint = canonical["recurring_capex_maintenance"].get(p)
        if rec_maint is not None and rec_maint > 0:
            capex = float(rec_maint)
        else:
            capex = abs(capex_raw) if capex_raw is not None else None
    else:
        capex = abs(capex_raw) if capex_raw is not None else None
    canonical["capital_expenditures"][p] = capex

    if archetype in ("FINANCIAL_BANKING", "INSURANCE"):
        canonical["free_cash_flow"][p] = None
    elif archetype == "REAL_ESTATE_REIT":
        ffo = None
        if ni is not None:
            re_dep_val = float(canonical["real_estate_depreciation"].get(p) or 0.0)
            gain_sale_val = float(canonical["gain_loss_sale_properties"].get(p) or 0.0)
            ffo = round(float(ni) + re_dep_val - gain_sale_val, 2)
        canonical["ffo"][p] = ffo

        affo = None
        if ffo is not None:
            rec_c = canonical["recurring_capex_maintenance"].get(p)
            deduct_c = float(rec_c) if rec_c is not None else (float(capex) if capex is not None else 0.0)
            affo = round(ffo - deduct_c, 2)
        canonical["affo"][p] = affo
        canonical["free_cash_flow"][p] = affo
    else:
        canonical["free_cash_flow"][p] = round(cfo - capex, 2) if (cfo is not None and capex is not None) else None

    if archetype == "INSURANCE":
        _populate_insurance_underwriting_ratios(canonical, ratios, p)

    for flow_key in ("dividends_paid", "share_repurchases", "stock_plans_proceeds", "share_repurchases_sbc_tax", "stock_based_compensation"):
        raw = _lookup_metric(cf_data, XBRL_TAXONOMY_MAP[flow_key], p, facts_df, is_flow=True)
        canonical[flow_key][p] = abs(float(raw)) if raw is not None else None
    _sync_net_repurchases(canonical, p)

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

    di_raw = _lookup_metric(cf_data, XBRL_TAXONOMY_MAP["debt_issuances"], p, facts_df, is_flow=True)
    canonical["debt_issuances"][p] = abs(float(di_raw)) if di_raw is not None else None

    cfi_cands = ["NetCashProvidedByUsedInInvestingActivities", "us-gaap_NetCashProvidedByUsedInInvestingActivities"]
    cff_cands = ["NetCashProvidedByUsedInFinancingActivities", "us-gaap_NetCashProvidedByUsedInFinancingActivities"]
    cfi_val = _lookup_metric(cf_data, cfi_cands, p, facts_df, is_flow=True)
    cff_val = _lookup_metric(cf_data, cff_cands, p, facts_df, is_flow=True)
    canonical["cash_from_investing"][p] = float(cfi_val) if cfi_val is not None else None
    canonical["cash_from_financing"][p] = float(cff_val) if cff_val is not None else None

    if p == "LTM" and facts_df is not None:
        ltm_specs = [
            ("dividends_paid", XBRL_TAXONOMY_MAP["dividends_paid"], False),
            ("share_repurchases", XBRL_TAXONOMY_MAP["share_repurchases"], False),
            ("stock_plans_proceeds", XBRL_TAXONOMY_MAP["stock_plans_proceeds"], False),
            ("share_repurchases_sbc_tax", XBRL_TAXONOMY_MAP["share_repurchases_sbc_tax"], False),
            ("stock_based_compensation", XBRL_TAXONOMY_MAP["stock_based_compensation"], False),
            ("acquisitions_ma", XBRL_TAXONOMY_MAP["acquisitions_ma"], False),
            ("debt_repayments", XBRL_TAXONOMY_MAP["debt_repayments"], False),
            ("debt_issuances", XBRL_TAXONOMY_MAP["debt_issuances"], False),
            ("cash_from_investing", cfi_cands, True),
            ("cash_from_financing", cff_cands, True),
        ]
        for flow_key, cands, keep_sign in ltm_specs:
            if canonical[flow_key][p] is None:
                q4_sum = get_ltm_quarterly_metric(facts_df, cands, mode="sum")
                if q4_sum is not None:
                    canonical[flow_key][p] = float(q4_sum) if keep_sign else abs(float(q4_sum))
        _sync_net_repurchases(canonical, p)


def _extract_banking_bs_period(canonical, bal_data, facts_df, p):
    """Extrae partidas de balance específicas del arquetipo bancario."""
    cash_pure = get_first_matching_value(bal_data, BANKING_TAXONOMY_MAP["cash_and_liquidity"], p) or 0.0
    cb_dep = get_first_matching_value(bal_data, BANKING_TAXONOMY_MAP["central_bank_deposits"], p) or 0.0
    cash = round(cash_pure + cb_dep, 2) if (cash_pure + cb_dep) > 0 else (cash_pure or 0.0)
    canonical["cash_and_equivalents"][p] = cash

    lt_debt = _lookup_metric(bal_data, BANKING_TAXONOMY_MAP["long_term_debt"], p, facts_df, is_flow=False) or 0.0
    st_debt = _lookup_metric(bal_data, BANKING_TAXONOMY_MAP["short_term_interbank"], p, facts_df, is_flow=False) or 0.0
    tot_debt = round(lt_debt + st_debt, 2)

    canonical["borrowings"][p] = lt_debt
    canonical["repurchase_agreements"][p] = st_debt
    canonical["short_term_debt"][p] = st_debt
    canonical["long_term_debt"][p] = lt_debt
    canonical["total_debt"][p] = tot_debt
    canonical["net_debt"][p] = round(tot_debt - cash, 2)

    canonical["total_deposits"][p] = _lookup_metric(bal_data, BANKING_TAXONOMY_MAP["total_deposits"], p, facts_df, is_flow=False)

    l1 = get_first_matching_value(bal_data, ["CreditCardReceivables1", "CreditCardReceivables", "CreditCardReceivablesNet"], p) or 0.0
    l2 = get_first_matching_value(
        bal_data,
        ["LoansAndAdvancesToCustomers", "TotalLoansAndAdvancesToCustomers", "LoansAndLeasesReceivableNetOfDeferredIncome"],
        p,
    ) or 0.0
    tot_l = round(l1 + l2, 2) if (l1 + l2) > 0 else get_first_matching_value(bal_data, BANKING_TAXONOMY_MAP["net_loans"], p)
    if tot_l is None and facts_df is not None:
        tot_l = get_fact_fallback(facts_df, BANKING_TAXONOMY_MAP["net_loans"], p, is_flow=False)
    canonical["net_loans"][p] = tot_l

    allow_l = _lookup_metric(bal_data, BANKING_TAXONOMY_MAP["allowance_for_credit_losses"], p, facts_df, is_flow=False)
    if allow_l is not None and allow_l < 1e7 and (tot_l or 0.0) > 1e9:
        allow_l = None
    canonical["allowance_for_credit_losses"][p] = abs(allow_l) if allow_l is not None else None

    canonical["current_assets"][p] = None
    canonical["current_liabilities"][p] = None
    canonical["net_ppe"][p] = get_first_matching_value(bal_data, XBRL_TAXONOMY_MAP["net_ppe"], p)
    canonical["net_working_capital"][p] = None
    canonical["tangible_capital_employed"][p] = None


def _extract_insurance_bs_period(canonical, bal_data, facts_df, p, equity):
    """Extrae reservas técnicas, inversiones, deuda y float para aseguradoras."""
    cash = _lookup_metric(bal_data, XBRL_TAXONOMY_MAP["cash_and_equivalents"], p, facts_df) or 0.0
    canonical["cash_and_equivalents"][p] = cash

    st_debt = get_first_matching_value(bal_data, XBRL_TAXONOMY_MAP["short_term_debt"], p) or 0.0
    lt_debt = get_first_matching_value(bal_data, XBRL_TAXONOMY_MAP["long_term_debt"], p) or 0.0
    comb_debt = get_first_matching_value(
        bal_data,
        ["DebtLongtermAndShorttermCombinedAmount", "us-gaap_DebtLongtermAndShorttermCombinedAmount", "TotalDebt"],
        p,
    )
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

    loss_res = _lookup_metric(bal_data, INSURANCE_TAXONOMY_MAP["loss_reserves"], p, facts_df)
    unearned_prem = _lookup_metric(bal_data, INSURANCE_TAXONOMY_MAP["unearned_premiums"], p, facts_df)
    reins_rec = _lookup_metric(bal_data, INSURANCE_TAXONOMY_MAP["reinsurance_receivables"], p, facts_df)
    tot_inv = _lookup_metric(bal_data, INSURANCE_TAXONOMY_MAP["total_investments"], p, facts_df)

    canonical["loss_reserves"][p] = abs(loss_res) if loss_res is not None else None
    canonical["unearned_premiums"][p] = abs(unearned_prem) if unearned_prem is not None else None
    canonical["reinsurance_receivables"][p] = abs(reins_rec) if reins_rec is not None else None
    canonical["total_investments"][p] = tot_inv

    ins_float = None
    if loss_res is not None or unearned_prem is not None:
        ins_float = (
            (abs(loss_res) if loss_res else 0.0)
            + (abs(unearned_prem) if unearned_prem else 0.0)
            - (abs(reins_rec) if reins_rec else 0.0)
        )
        ins_float = round(ins_float, 2)
    canonical["float_usd"][p] = ins_float

    canonical["current_assets"][p] = None
    canonical["current_liabilities"][p] = None
    canonical["net_ppe"][p] = None
    canonical["net_working_capital"][p] = None
    canonical["tangible_capital_employed"][p] = None
    if equity is not None:
        canonical["tangible_book_value"][p] = float(equity)


def _extract_corporate_bs_period(canonical, bal_data, facts_df, p, archetype):
    """Extrae liquidez, deuda multi-tramo, capital de trabajo y PP&E para no financieras."""
    cash = _lookup_metric(bal_data, XBRL_TAXONOMY_MAP["cash_and_equivalents"], p, facts_df) or 0.0
    canonical["cash_and_equivalents"][p] = cash

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

    cp_val = get_first_matching_value(bal_data, ["CommercialPaper", "us-gaap_CommercialPaper", "ShortTermBorrowings", "us-gaap_ShortTermBorrowings"], p)
    ltd_curr = get_first_matching_value(bal_data, ["LongTermDebtCurrent", "us-gaap_LongTermDebtCurrent", "CurrentPortionOfLongTermDebt", "us-gaap_CurrentPortionOfLongTermDebt"], p)
    ltd_tot = get_first_matching_value(bal_data, ["LongTermDebt", "us-gaap_LongTermDebt"], p)
    ltd_noncurr = get_first_matching_value(bal_data, ["LongTermDebtNoncurrent", "us-gaap_LongTermDebtNoncurrent"], p)
    comb_debt = get_first_matching_value(bal_data, ["DebtLongtermAndShorttermCombinedAmount", "us-gaap_DebtLongtermAndShorttermCombinedAmount", "TotalDebt"], p)

    if comb_debt is not None:
        tot_debt = round(float(comb_debt), 2)
        st_debt = get_first_matching_value(bal_data, XBRL_TAXONOMY_MAP["short_term_debt"], p) or 0.0
        lt_debt_base = get_first_matching_value(bal_data, XBRL_TAXONOMY_MAP["long_term_debt"], p) or 0.0
        lt_debt = round(tot_debt - st_debt, 2) if tot_debt > st_debt else (tot_debt if lt_debt_base == 0.0 else lt_debt_base)
    elif cp_val is not None and ltd_tot is not None:
        tot_debt = round(float(cp_val) + float(ltd_tot), 2)
        lt_debt = round(float(ltd_noncurr), 2) if ltd_noncurr is not None else round(float(ltd_tot), 2)
        st_debt = round(tot_debt - lt_debt, 2)
    else:
        st_debt = _lookup_metric(bal_data, XBRL_TAXONOMY_MAP["short_term_debt"], p, facts_df) or 0.0
        lt_debt = _lookup_metric(bal_data, XBRL_TAXONOMY_MAP["long_term_debt"], p, facts_df) or 0.0
        if cp_val is not None and ltd_curr is not None:
            combined_st = round(float(cp_val) + float(ltd_curr), 2)
            if combined_st > st_debt:
                st_debt = combined_st

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

    curr_assets = _lookup_metric(bal_data, XBRL_TAXONOMY_MAP["current_assets"], p, facts_df)
    curr_liab = _lookup_metric(bal_data, XBRL_TAXONOMY_MAP["current_liabilities"], p, facts_df)
    rou_asset = _lookup_metric(bal_data, XBRL_TAXONOMY_MAP["operating_lease_rou_asset"], p, facts_df)
    accrued_liab = _lookup_metric(bal_data, XBRL_TAXONOMY_MAP["accrued_liabilities"], p, facts_df)
    net_ppe = _lookup_metric(bal_data, XBRL_TAXONOMY_MAP["net_ppe"], p, facts_df)

    canonical["current_assets"][p] = curr_assets
    canonical["current_liabilities"][p] = curr_liab
    canonical["operating_lease_rou_asset"][p] = rou_asset
    canonical["accrued_liabilities"][p] = accrued_liab
    canonical["net_ppe"][p] = net_ppe

    op_ca = max(0.0, (curr_assets or 0.0) - cash) if curr_assets is not None else None
    op_cl = max(0.0, (curr_liab or 0.0) - st_debt) if curr_liab is not None else None
    op_nwc = (op_ca - op_cl) if (op_ca is not None and op_cl is not None) else None
    canonical["net_working_capital"][p] = op_nwc

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
        canonical["total_deposits"][p] = get_first_matching_value(bal_data, BANKING_TAXONOMY_MAP["total_deposits"], p)
        tot_l = get_first_matching_value(bal_data, BANKING_TAXONOMY_MAP["net_loans"], p)
        if tot_l is None:
            nl_c = get_first_matching_value(bal_data, ["NotesAndLoansReceivableNetCurrent", "us-gaap_NotesAndLoansReceivableNetCurrent"], p) or 0.0
            nl_nc = get_first_matching_value(bal_data, ["NotesAndLoansReceivableNetNoncurrent", "us-gaap_NotesAndLoansReceivableNetNoncurrent"], p) or 0.0
            if (nl_c + nl_nc) > 0:
                tot_l = round(nl_c + nl_nc, 2)
        canonical["net_loans"][p] = tot_l

        allow_l = _lookup_metric(bal_data, BANKING_TAXONOMY_MAP["allowance_for_credit_losses"], p, facts_df, is_flow=False)
        if allow_l is not None and allow_l < 1e7 and (tot_l or 0.0) > 1e9:
            allow_l = None
        canonical["allowance_for_credit_losses"][p] = abs(allow_l) if allow_l is not None else None
        canonical["borrowings"][p] = get_first_matching_value(bal_data, BANKING_TAXONOMY_MAP["long_term_debt"], p)


def _compute_period_ratios(canonical, ratios, p, archetype):
    """Calcula ratios puntuales por período y arquetipo antes del promedio interanual."""
    rev = canonical["revenue"].get(p)
    gp = canonical["gross_profit"].get(p)
    ebit = canonical["operating_income"].get(p)
    ni = canonical["net_income"].get(p)
    fcf = canonical["free_cash_flow"].get(p)
    equity = canonical["stockholders_equity"].get(p)
    assets = canonical["total_assets"].get(p)
    tot_debt = canonical["total_debt"].get(p)

    if rev and rev > 0:
        ratios["gross_margin_pct"][p] = round((gp / rev) * 100, 2) if gp is not None else None
        if ebit is not None:
            ratios["operating_margin_pct"][p] = round((ebit / rev) * 100, 2)
        if ni is not None:
            ratios["net_margin_pct"][p] = round((ni / rev) * 100, 2)
        ratios["fcf_margin_pct"][p] = round((fcf / rev) * 100, 2) if fcf is not None else None
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
        for rkey in ("gross_margin_pct", "fcf_margin_pct", "fcf_conversion_pct", "roc_greenblatt_pct", "current_ratio"):
            ratios[rkey][p] = None
        if archetype == "FINANCIAL_BANKING":
            op_exp = canonical["operating_expenses"].get(p)
            clp = canonical["credit_loss_provisions"].get(p)
            nii = canonical["net_interest_income"].get(p)
            tot_l = canonical["net_loans"].get(p)
            dep = canonical["total_deposits"].get(p)
            non_ii = canonical["non_interest_income"].get(p)

            if rev and rev > 0 and op_exp is not None:
                ratios.setdefault("efficiency_ratio_pct", {})[p] = round((abs(op_exp) / rev) * 100, 2)
            if rev and rev > 0 and clp is not None:
                ratios.setdefault("cost_of_risk_pct", {})[p] = round((abs(clp) / rev) * 100, 2)
            if nii is not None and assets and assets > 0:
                clp_val = abs(clp) if clp is not None else 0.0
                ratios.setdefault("risk_adj_nim_pct", {})[p] = round(((nii - clp_val) / assets) * 100, 2)
            if tot_l and dep and dep > 0:
                ratios.setdefault("ldr_pct", {})[p] = round((tot_l / dep) * 100, 2)
            if non_ii is not None and rev and rev > 0:
                ratios.setdefault("fee_share_pct", {})[p] = round((non_ii / rev) * 100, 2)
            if clp is not None and tot_l and tot_l > 0:
                ratios.setdefault("cost_of_risk_loans_pct", {})[p] = round((abs(clp) / tot_l) * 100, 2)
            if assets and equity and equity > 0:
                ratios.setdefault("financial_leverage", {})[p] = round(assets / equity, 2)
            if rev and assets and assets > 0:
                ratios.setdefault("asset_turnover", {})[p] = round(rev / assets, 4)
    else:
        curr_assets = canonical["current_assets"].get(p)
        curr_liab = canonical["current_liabilities"].get(p)
        if curr_assets is not None and curr_liab and curr_liab > 0:
            ratios["current_ratio"][p] = round(curr_assets / curr_liab, 2)
        if archetype == "REAL_ESTATE_REIT":
            noi = canonical["noi"].get(p)
            ffo = canonical["ffo"].get(p)
            affo = canonical["affo"].get(p)
            if rev and rev > 0 and noi is not None:
                ratios.setdefault("noi_margin_pct", {})[p] = round((noi / rev) * 100, 2)
            sh_d = canonical["shares_diluted"].get(p)
            if sh_d and sh_d > 0:
                if ffo is not None:
                    ratios.setdefault("ffo_per_share", {})[p] = round(ffo / sh_d, 2)
                if affo is not None:
                    ratios.setdefault("affo_per_share", {})[p] = round(affo / sh_d, 2)

    if tot_debt is not None and equity and equity > 0:
        ratios["debt_to_equity"][p] = round(tot_debt / equity, 2)


def _compute_average_balance_returns(canonical, ratios, periods, is_financial):
    """Calcula ROA, ROE y ROC Greenblatt utilizando balances promedio ((t + t-1) / 2)."""
    annual_periods = [p for p in periods if p != "LTM"]
    ratios["roa_ending_pct"] = dict(ratios["roa_pct"])
    ratios["roe_ending_pct"] = dict(ratios["roe_pct"])
    ratios["roa_avg_pct"] = {}
    ratios["roe_avg_pct"] = {}

    def _prior_period_val(series, period):
        if period == "LTM":
            return series.get(annual_periods[0]) if annual_periods else None
        if period in annual_periods:
            idx = annual_periods.index(period)
            if idx + 1 < len(annual_periods):
                return series.get(annual_periods[idx + 1])
        return None

    for p in periods:
        ni = canonical["net_income"].get(p)
        a_curr = canonical["total_assets"].get(p)
        e_curr = canonical["stockholders_equity"].get(p)
        a_prev = _prior_period_val(canonical["total_assets"], p)
        e_prev = _prior_period_val(canonical["stockholders_equity"], p)

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

        ebit = canonical["operating_income"].get(p)
        tc_curr = canonical["tangible_capital_employed"].get(p)
        tc_prev = _prior_period_val(canonical["tangible_capital_employed"], p)
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


def _apply_split_adjustments_and_reconcile(canonical, periods, archetype):
    """Detecta stock splits retroactivos, concilia identidades y sanitiza floats."""
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
            split_cand = next(
                (float(s_int) for s_int in (2, 3, 4, 5, 6, 7, 10, 20) if (s_int * 0.85) <= ratio <= (s_int * 1.15)),
                None,
            )
            if split_cand is None:
                split_cand = next(
                    (1.0 / s_rev for s_rev in (2, 3, 4, 5, 10) if ((1.0 / s_rev) * 0.85) <= ratio <= ((1.0 / s_rev) * 1.15)),
                    None,
                )
            if split_cand is not None:
                current_factor *= split_cand
                logger.info(
                    "Stock Split detectado entre %s y %s: Factor %s:1 (Acumulado <= %s: %sx)",
                    p_prev,
                    p_now,
                    split_cand,
                    p_prev,
                    current_factor,
                )
        split_factors[p_prev] = current_factor

    canonical["split_adjustment_factor"] = split_factors
    for key in ("shares_basic_adjusted", "shares_diluted_adjusted", "eps_basic_adjusted", "eps_diluted_adjusted", "dps_adjusted"):
        canonical[key] = {}

    for p in periods:
        fac = split_factors.get(p, 1.0)
        sb = canonical["shares_basic"].get(p)
        sd = canonical["shares_diluted"].get(p)
        canonical["shares_basic_adjusted"][p] = round(sb * fac, 0) if sb is not None else None
        canonical["shares_diluted_adjusted"][p] = round(sd * fac, 0) if sd is not None else None

        ni_val = canonical["net_income"].get(p)
        adj_sd = canonical["shares_diluted_adjusted"].get(p)
        adj_sb = canonical["shares_basic_adjusted"].get(p)

        if ni_val is not None and adj_sd and adj_sd > 0:
            canonical["eps_diluted_adjusted"][p] = round(ni_val / adj_sd, 2)
        elif canonical["eps_diluted"].get(p) is not None:
            canonical["eps_diluted_adjusted"][p] = round(canonical["eps_diluted"][p] / fac, 2)
        else:
            canonical["eps_diluted_adjusted"][p] = None

        if ni_val is not None and adj_sb and adj_sb > 0:
            canonical["eps_basic_adjusted"][p] = round(ni_val / adj_sb, 2)
        elif canonical["eps_basic"].get(p) is not None:
            canonical["eps_basic_adjusted"][p] = round(canonical["eps_basic"][p] / fac, 2)
        else:
            canonical["eps_basic_adjusted"][p] = None

        dps_raw = canonical.get("dps", {}).get(p)
        canonical["dps_adjusted"][p] = round(dps_raw / fac, 4) if dps_raw is not None else None

        reconcile_accounting_identities(canonical, p, archetype)

    for k in list(canonical.keys()):
        for p in periods:
            v = canonical[k].get(p)
            if v is not None and not pd.isna(v) and str(v).lower() != "nan":
                try:
                    canonical[k][p] = float(v)
                except (ValueError, TypeError):
                    canonical[k][p] = None
            else:
                canonical[k][p] = None


def extract_canonical_summary(inc_data, bal_data, cf_data, periods, facts_df=None, is_financial=False, archetype=None):
    """Genera la tabla canónica normalizada para análisis fundamental unificada por período (LTM y FYs)."""
    if archetype is None:
        archetype = "FINANCIAL_BANKING" if is_financial else "STANDARD_CORPORATE"
    else:
        is_financial = archetype in ("FINANCIAL_BANKING", "INSURANCE")

    canonical, ratios = _init_canonical_containers(is_financial, archetype)

    for p in periods:
        if archetype == "FINANCIAL_BANKING":
            _extract_banking_pnl_period(canonical, inc_data, facts_df, p)
        elif archetype == "REAL_ESTATE_REIT":
            _extract_reit_pnl_period(canonical, inc_data, cf_data, facts_df, p)
        elif archetype == "INSURANCE":
            _extract_insurance_pnl_period(canonical, inc_data, facts_df, p)
        else:
            _extract_corporate_pnl_period(canonical, inc_data, facts_df, p, archetype)

        _extract_ebit_and_non_op_period(canonical, inc_data, cf_data, facts_df, p, archetype)
        _extract_shares_and_eps_period(canonical, inc_data, facts_df, periods, p)
        _extract_cash_flow_and_cap_alloc_period(canonical, ratios, cf_data, facts_df, p, archetype)

        assets = _lookup_metric(bal_data, XBRL_TAXONOMY_MAP["total_assets"], p, facts_df)
        equity = _lookup_metric(bal_data, XBRL_TAXONOMY_MAP["stockholders_equity"], p, facts_df)
        canonical["total_assets"][p] = assets
        canonical["stockholders_equity"][p] = equity

        if archetype == "FINANCIAL_BANKING":
            _extract_banking_bs_period(canonical, bal_data, facts_df, p)
        elif archetype == "INSURANCE":
            _extract_insurance_bs_period(canonical, bal_data, facts_df, p, equity)
        else:
            _extract_corporate_bs_period(canonical, bal_data, facts_df, p, archetype)

        _compute_period_ratios(canonical, ratios, p, archetype)

    _compute_average_balance_returns(canonical, ratios, periods, is_financial)
    _apply_split_adjustments_and_reconcile(canonical, periods, archetype)

    return canonical, ratios
