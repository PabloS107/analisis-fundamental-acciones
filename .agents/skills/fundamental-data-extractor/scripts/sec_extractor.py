"""
sec_extractor.py - Extractor oficial de estados contables e items narrativos de SEC EDGAR.
Garantiza datos auditados bajo normativa US-GAAP sin intermediarios.
Soporta 10 años de historia fiscal completa y cálculo institucional de LTM (Last Twelve Months / TTM).
"""

import os
import sys
import json
import re
import argparse
from pathlib import Path
from datetime import datetime
import pandas as pd
import numpy as np
from edgar import set_identity, Company

try:
    from sec_rate_limiter import sec_call_with_retry, default_rate_limiter
except ImportError:
    try:
        from .sec_rate_limiter import sec_call_with_retry, default_rate_limiter
    except ImportError:
        def sec_call_with_retry(fn, *args, **kwargs):
            return fn(*args, **kwargs)
        default_rate_limiter = None


def load_sec_config():
    """Carga la configuración de identidad para SEC EDGAR."""
    possible_paths = [
        Path("config/sec_config.json"),
        Path(__file__).resolve().parents[4] / "config" / "sec_config.json",
        Path(__file__).resolve().parents[3] / "config" / "sec_config.json",
    ]
    for p in possible_paths:
        if p.exists():
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
                
    return {
        "sec_identity": "Pablo Inversiones pablo_inversiones@gmail.com",
        "google_drive_base_path": "G:\\Mi unidad\\analisis fundamental",
        "local_output_path": "data\\processed"
    }


def normalize_fiscal_year(col_name):
    """Convierte '2025-09-27 (FY)' o 'FY 2025' a una etiqueta unificada 'FY2025'."""
    col_str = str(col_name).strip()
    if col_str == "LTM":
        return "LTM"
    m = re.search(r'(\d{4})', col_str)
    if m:
        return f"FY{m.group(1)}"
    return col_str


def dataframe_to_concept_dict(df, periods):
    """Convierte un DataFrame con columnas de períodos a un diccionario indexado por concepto US-GAAP."""
    data_by_concept = {}
    if df is None or df.empty:
        return data_by_concept
        
    for _, row in df.iterrows():
        concept = row.get('concept')
        if not concept or pd.isna(concept) or str(concept) == 'nan':
            continue
            
        concept_str = str(concept).strip()
        label = str(row.get('label', '')).strip()
        std_concept = str(row.get('standard_concept', '')).strip()
        
        values = {}
        for p in periods:
            if p in df.columns:
                val = row.get(p)
                if pd.notna(val) and str(val) != 'nan':
                    try:
                        values[p] = float(val)
                    except (ValueError, TypeError):
                        pass
                        
        if concept_str not in data_by_concept or len(values) > len(data_by_concept[concept_str].get("values", {})):
            data_by_concept[concept_str] = {
                "label": label,
                "standard_concept": std_concept if std_concept != 'None' else None,
                "values": values
            }
            
    return data_by_concept


XBRL_TAXONOMY_MAP = {
    "revenue": [
        # US-GAAP - Priorizar Revenues consolidado total sobre ASC 606 granular
        "Revenues",
        "SalesRevenueNet",
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenue",
        # IFRS (ifrs-full)
        "Revenue",
        "RevenueFromContractsWithCustomers",
        "GrossRevenue",
        "OperatingRevenue"
    ],
    "cost_of_goods_sold": [
        # US-GAAP
        "CostOfGoodsAndServicesSold",
        "CostOfRevenue",
        # IFRS (ifrs-full)
        "CostOfSales",
        "CostOfMerchandiseSold"
    ],
    "gross_profit": [
        "GrossProfit"
    ],
    "operating_expenses": [
        # US-GAAP
        "OperatingExpenses",
        "TotalOperatingExpenses",
        # IFRS (ifrs-full)
        "AdministrativeExpense",
        "DistributionCosts"
    ],
    "operating_income": [
        # US-GAAP
        "OperatingIncomeLoss",
        "OperatingIncome",
        # IFRS (ifrs-full)
        "ProfitLossFromOperatingActivities",
        "OperatingProfitLoss",
        "OperatingIncomeLoss"
    ],
    "net_income": [
        # US-GAAP
        "NetIncomeLoss",
        "NetIncome",
        # IFRS (ifrs-full)
        "ProfitLoss",
        "ProfitLossAttributableToOwnersOfParent",
        "ProfitLossFromContinuingOperations"
    ],
    "shares_basic": [
        # US-GAAP
        "WeightedAverageNumberOfSharesOutstandingBasic",
        "CommonStockSharesOutstanding",
        # IFRS (ifrs-full)
        "WeightedAverageShares",
        "WeightedAverageNumberOfOrdinarySharesOutstandingBasic",
        "NumberOfSharesOutstanding"
    ],
    "shares_diluted": [
        # US-GAAP
        "WeightedAverageNumberOfDilutedSharesOutstanding",
        "WeightedAverageNumberOfSharesOutstandingDiluted",
        "CommonStockSharesOutstanding",
        # IFRS (ifrs-full)
        "DilutedWeightedAverageShares",
        "WeightedAverageNumberOfOrdinarySharesOutstandingDiluted"
    ],
    "eps_basic": [
        # US-GAAP
        "EarningsPerShareBasic",
        "BasicEarningsPerShare",
        # IFRS (ifrs-full)
        "BasicEarningsLossPerShare",
        "BasicEarningsLossPerShareFromContinuingOperations"
    ],
    "eps_diluted": [
        # US-GAAP
        "EarningsPerShareDiluted",
        "DilutedEarningsPerShare",
        # IFRS (ifrs-full)
        "DilutedEarningsLossPerShare",
        "DilutedEarningsLossPerShareFromContinuingOperations"
    ],
    "cash_from_operations": [
        # US-GAAP
        "NetCashProvidedByUsedInOperatingActivities",
        "NetCashProvidedByOperatingActivities",
        "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
        # IFRS (ifrs-full)
        "CashFlowsFromUsedInOperatingActivities"
    ],
    "capital_expenditures": [
        # US-GAAP
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "PaymentsToAcquireProductiveAssets",
        "CapitalExpendituresIncurredButNotYetPaid",
        # IFRS (ifrs-full)
        "PurchaseOfPropertyPlantAndEquipment",
        "PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities",
        "PurchaseOfPropertyPlantAndEquipmentIntangibleAssetsOtherThanGoodwillInvestmentPropertyAndOtherNoncurrentAssets"
    ],
    "total_assets": [
        "Assets",
        "TotalAssets"
    ],
    "stockholders_equity": [
        # US-GAAP
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
        "CommonEquity",
        "AllEquityBalance",
        # IFRS (ifrs-full)
        "Equity",
        "EquityAttributableToOwnersOfParent",
        "TotalEquity"
    ],
    "cash_and_equivalents": [
        # US-GAAP
        "CashAndCashEquivalentsAtCarryingValue",
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
        "CashAndMarketableSecurities",
        # IFRS (ifrs-full)
        "CashAndCashEquivalents"
    ],
    "short_term_debt": [
        # US-GAAP
        "ShortTermDebt",
        "CurrentPortionOfLongTermDebt",
        "CommercialPaper",
        # IFRS (ifrs-full)
        "CurrentBorrowingsAndOtherFinancialLiabilities",
        "CurrentPortionOfNoncurrentBorrowings",
        "CurrentFinancialLiabilities"
    ],
    "long_term_debt": [
        # US-GAAP
        "LongTermDebt",
        "LongTermDebtNoncurrent",
        # IFRS (ifrs-full)
        "NoncurrentBorrowings",
        "NoncurrentFinancialLiabilities"
    ],
    "current_assets": [
        "AssetsCurrent",
        "CurrentAssetsTotal",
        "CurrentAssets"
    ],
    "current_liabilities": [
        "LiabilitiesCurrent",
        "CurrentLiabilitiesTotal",
        "CurrentLiabilities"
    ],
    "rd_expense": [
        "ResearchAndDevelopmentExpense",
        "ResearchAndDevelopmentExpenseSoftwareExcludingAcquiredInProcessCost"
    ],
    "net_ppe": [
        # US-GAAP
        "PropertyPlantAndEquipmentNet",
        "PropertyPlantAndEquipmentAndFinanceLeaseRightOfUseAssetAfterAccumulatedDepreciationAndAmortization",
        "PropertyPlantAndEquipmentGross",
        # IFRS (ifrs-full)
        "PropertyPlantAndEquipment",
        "PropertyPlantAndEquipmentNet"
    ]
}

# Alias comunes para compatibilidad canónica
XBRL_TAXONOMY_MAP["operating_cash_flow"] = XBRL_TAXONOMY_MAP["cash_from_operations"]
XBRL_TAXONOMY_MAP["capex"] = XBRL_TAXONOMY_MAP["capital_expenditures"]
XBRL_TAXONOMY_MAP["ppe_net"] = XBRL_TAXONOMY_MAP["net_ppe"]




def get_first_matching_value(data_by_concept, concept_candidates, period):
    """Busca en orden de prioridad un concepto contable y devuelve su valor para un período."""
    for cand in concept_candidates:
        cand_lower = cand.lower()
        for c_key, c_data in data_by_concept.items():
            k_lower = c_key.lower()
            std_concept = str(c_data.get("standard_concept") or "").lower()
            lbl = str(c_data.get("label") or "").lower()
            if (k_lower == cand_lower or k_lower.endswith(f"_{cand_lower}") or k_lower.endswith(cand_lower)
                or std_concept == cand_lower or std_concept.endswith(f"_{cand_lower}") or std_concept.endswith(cand_lower)
                or lbl == cand_lower):
                val = c_data["values"].get(period)
                if val is not None and not pd.isna(val):
                    try:
                        return float(val)
                    except (ValueError, TypeError):
                        pass
    return None


def get_fact_fallback(facts_df, concept_candidates, fy_str):
    """Busca una partida en Company Facts como respaldo si no figura en el estado multi-período."""
    if facts_df is None or facts_df.empty or fy_str == "LTM":
        return None
    year_digits = ''.join(filter(str.isdigit, fy_str))
    if not year_digits:
        return None
    fy_int = int(year_digits)
    for cand in concept_candidates:
        matches = facts_df[(facts_df['fiscal_year'] == fy_int) & 
                           (facts_df['concept'].astype(str).str.contains(cand, case=False, na=False))]
        if not matches.empty:
            fy_matches = matches[matches['fiscal_period'].astype(str).str.upper() == 'FY']
            chosen = fy_matches.iloc[0] if not fy_matches.empty else matches.iloc[0]
            val = chosen.get('numeric_value')
            if pd.notna(val) and str(val) != 'nan':
                try:
                    return float(val)
                except (ValueError, TypeError):
                    pass
    return None


def extract_canonical_summary(inc_data, bal_data, cf_data, periods, facts_df=None):
    """Genera la tabla canónica normalizada para análisis fundamental unificada por período (LTM y FYs)."""
    canonical = {
        "revenue": {},
        "cost_of_goods_sold": {},
        "gross_profit": {},
        "operating_expenses": {},
        "operating_income": {},
        "net_income": {},
        "cash_from_operations": {},
        "capital_expenditures": {},
        "free_cash_flow": {},
        "cash_and_equivalents": {},
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
        "split_adjustment_factor": {},
        "current_assets": {},
        "current_liabilities": {},
        "net_ppe": {},
        "net_working_capital": {},
        "tangible_capital_employed": {}
    }
    
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
        # 1. Ingresos
        rev_cands = XBRL_TAXONOMY_MAP["revenue"]
        rev = get_first_matching_value(inc_data, rev_cands, p)
        if rev is None and facts_df is not None:
            rev = get_fact_fallback(facts_df, rev_cands, p)
        canonical["revenue"][p] = rev
        
        # 2. Costo de Ventas
        cogs_cands = XBRL_TAXONOMY_MAP["cost_of_goods_sold"]
        cogs = get_first_matching_value(inc_data, cogs_cands, p)
        if cogs is None and facts_df is not None:
            cogs = get_fact_fallback(facts_df, cogs_cands, p)
        canonical["cost_of_goods_sold"][p] = cogs
        
        # 3. Margen Bruto
        gp = get_first_matching_value(inc_data, XBRL_TAXONOMY_MAP["gross_profit"], p)
        if gp is None and rev is not None and cogs is not None:
            gp = rev - cogs
        canonical["gross_profit"][p] = gp
        
        # 4. Gastos Operativos y EBIT
        op_exp = get_first_matching_value(inc_data, XBRL_TAXONOMY_MAP["operating_expenses"], p)
        canonical["operating_expenses"][p] = op_exp
        
        ebit_cands = XBRL_TAXONOMY_MAP["operating_income"]
        ebit = get_first_matching_value(inc_data, ebit_cands, p)
        if ebit is None and facts_df is not None:
            ebit = get_fact_fallback(facts_df, ebit_cands, p)
        canonical["operating_income"][p] = ebit
        
        # 5. Beneficio Neto
        ni_cands = XBRL_TAXONOMY_MAP["net_income"]
        ni = get_first_matching_value(inc_data, ni_cands, p)
        if ni is None and facts_df is not None:
            ni = get_fact_fallback(facts_df, ni_cands, p)
        canonical["net_income"][p] = ni
        
        # 6. Acciones básicas y diluidas
        sh_basic_cands = XBRL_TAXONOMY_MAP["shares_basic"]
        sh_basic = get_first_matching_value(inc_data, sh_basic_cands, p)
        if sh_basic is None and facts_df is not None:
            sh_basic = get_fact_fallback(facts_df, sh_basic_cands, p)
        canonical["shares_basic"][p] = sh_basic

        sh_diluted_cands = XBRL_TAXONOMY_MAP["shares_diluted"]
        sh = get_first_matching_value(inc_data, sh_diluted_cands, p)
        if sh is None and facts_df is not None:
            sh = get_fact_fallback(facts_df, sh_diluted_cands, p)
        canonical["shares_diluted"][p] = sh
        
        # 6b. Beneficio Por Acción (BPA / EPS)
        eps_b_cands = XBRL_TAXONOMY_MAP["eps_basic"]
        eps_b = get_first_matching_value(inc_data, eps_b_cands, p)
        if eps_b is None and facts_df is not None:
            eps_b = get_fact_fallback(facts_df, eps_b_cands, p)
        
        eps_d_cands = XBRL_TAXONOMY_MAP["eps_diluted"]
        eps_d = get_first_matching_value(inc_data, eps_d_cands, p)
        if eps_d is None and facts_df is not None:
            eps_d = get_fact_fallback(facts_df, eps_d_cands, p)
            
        if p == "LTM":
            # Si ya se dedujo el EPS por flujo trimestral acumulado oficial (US-GAAP ASC 260), preservarlo
            if eps_d is None and ni is not None and sh and sh > 0:
                calc_ltm_eps = round(ni / sh, 2)
                eps_d = calc_ltm_eps
            if eps_b is None and ni is not None and sh_basic and sh_basic > 0:
                calc_ltm_b_eps = round(ni / sh_basic, 2)
                eps_b = calc_ltm_b_eps
                    
        canonical["eps_basic"][p] = eps_b
        canonical["eps_diluted"][p] = eps_d
        
        # 7. Flujo de Caja Operativo
        cfo_cands = XBRL_TAXONOMY_MAP["cash_from_operations"]
        cfo = get_first_matching_value(cf_data, cfo_cands, p)
        if cfo is None and facts_df is not None:
            cfo = get_fact_fallback(facts_df, cfo_cands, p)
        canonical["cash_from_operations"][p] = cfo
        
        # 8. CapEx
        capex_cands = XBRL_TAXONOMY_MAP["capital_expenditures"]
        capex_raw = get_first_matching_value(cf_data, capex_cands, p)
        if capex_raw is None and facts_df is not None:
            capex_raw = get_fact_fallback(facts_df, capex_cands, p)
        capex = abs(capex_raw) if capex_raw is not None else 0.0
        canonical["capital_expenditures"][p] = capex
        
        # 9. Free Cash Flow
        fcf = None
        if cfo is not None:
            fcf = cfo - capex
            canonical["free_cash_flow"][p] = round(fcf, 2)
        else:
            canonical["free_cash_flow"][p] = None
            
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
        
        cash = get_first_matching_value(bal_data, XBRL_TAXONOMY_MAP["cash_and_equivalents"], p) or 0.0
        canonical["cash_and_equivalents"][p] = cash
        
        st_debt = get_first_matching_value(bal_data, XBRL_TAXONOMY_MAP["short_term_debt"], p) or 0.0
        lt_debt = get_first_matching_value(bal_data, XBRL_TAXONOMY_MAP["long_term_debt"], p) or 0.0
        tot_debt = st_debt + lt_debt
        canonical["total_debt"][p] = tot_debt
        canonical["net_debt"][p] = round(tot_debt - cash, 2)
        
        # Activos y pasivos corrientes y PP&E neto
        curr_assets = get_first_matching_value(bal_data, XBRL_TAXONOMY_MAP["current_assets"], p)
        if curr_assets is None and facts_df is not None:
            curr_assets = get_fact_fallback(facts_df, XBRL_TAXONOMY_MAP["current_assets"], p)
        canonical["current_assets"][p] = curr_assets

        curr_liab = get_first_matching_value(bal_data, XBRL_TAXONOMY_MAP["current_liabilities"], p)
        if curr_liab is None and facts_df is not None:
            curr_liab = get_fact_fallback(facts_df, XBRL_TAXONOMY_MAP["current_liabilities"], p)
        canonical["current_liabilities"][p] = curr_liab

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
        # Salvaguarda institucional: si el NWC es negativo, se acota inferiormente a Net PP&E
        tangible_cap = None
        if net_ppe is not None:
            if op_nwc is not None:
                tangible_cap = max(net_ppe, op_nwc + net_ppe) if op_nwc < 0 else (op_nwc + net_ppe)
            else:
                tangible_cap = net_ppe
        elif op_nwc is not None and op_nwc > 0:
            tangible_cap = op_nwc
        canonical["tangible_capital_employed"][p] = tangible_cap

        # --- Ratios Financieros ---
        if rev and rev > 0:
            if gp is not None:
                ratios["gross_margin_pct"][p] = round((gp / rev) * 100, 2)
            if ebit is not None:
                ratios["operating_margin_pct"][p] = round((ebit / rev) * 100, 2)
            if ni is not None:
                ratios["net_margin_pct"][p] = round((ni / rev) * 100, 2)
            if fcf is not None:
                ratios["fcf_margin_pct"][p] = round((fcf / rev) * 100, 2)
                
        if ni is not None and ni != 0 and fcf is not None:
            ratios["fcf_conversion_pct"][p] = round((fcf / ni) * 100, 2)
            
        if ni is not None and equity and equity > 0:
            ratios["roe_pct"][p] = round((ni / equity) * 100, 2)
            
        if ni is not None and assets and assets > 0:
            ratios["roa_pct"][p] = round((ni / assets) * 100, 2)
            
        if curr_assets is not None and curr_liab and curr_liab > 0:
            ratios["current_ratio"][p] = round(curr_assets / curr_liab, 2)
            
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

        if ebit is not None and tc_avg and tc_avg > 0:
            ratios["roc_greenblatt_pct"][p] = round((ebit / tc_avg) * 100, 2)
        elif ebit is not None and tc_curr and tc_curr > 0:
            ratios["roc_greenblatt_pct"][p] = round((ebit / tc_curr) * 100, 2)
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

    return canonical, ratios


def build_10yr_segment_df(company, all_fys, latest_10q_inc=None):
    """Extrae el desglose completo de 10 años de segmentos enlazando los 10-K históricos."""
    try:
        filings_10k = company.get_filings(form="10-K")
        if not filings_10k or len(filings_10k) == 0:
            return None
        target_filings = [filings_10k[i] for i in [0, 3, 6, 9] if i < len(filings_10k)]
        
        products = {}
        geos = {}
        prod_keys = ["Products", "iPhone", "Mac", "iPad", "Wearables, Home and Accessories", "Other Products", "Services"]
        geo_keys = ["Americas", "Europe", "Greater China", "Japan", "Rest of Asia Pacific"]
        
        for f in target_filings:
            try:
                doc = f.obj()
                fins = doc.financials
                if not fins or not fins.income_statement():
                    continue
                df = fins.income_statement().to_dataframe()
                
                year_cols = {}
                for col in df.columns:
                    m = re.search(r'(\d{4})', str(col))
                    if m and not str(col).startswith('level') and not str(col).startswith('dim'):
                        year_cols[col] = f"FY{m.group(1)}"
                        
                for _, row in df.iterrows():
                    concept = str(row.get('concept', ''))
                    dim = str(row.get('dimension_member_label', '')).strip()
                    lbl = str(row.get('label', '')).strip()
                    
                    if 'Revenue' in concept or 'Sales' in concept:
                        for pk in prod_keys:
                            if pk.lower() == dim.lower() or pk.lower() == lbl.lower():
                                if pk not in products:
                                    products[pk] = {"concept": "RevenueByProduct", "dimension_member_label": pk, "label": pk}
                                for c_col, fy in year_cols.items():
                                    val = row.get(c_col)
                                    if pd.notna(val) and str(val) != 'nan' and fy not in products[pk]:
                                        try:
                                            products[pk][fy] = float(val)
                                        except:
                                            pass
                                            
                        for gk in geo_keys:
                            if gk.lower() == dim.lower() or gk.lower() in lbl.lower():
                                if gk not in geos:
                                    geos[gk] = {"concept": "RevenueByRegion", "dimension_member_label": gk, "label": gk}
                                for c_col, fy in year_cols.items():
                                    val = row.get(c_col)
                                    if pd.notna(val) and str(val) != 'nan' and fy not in geos[gk]:
                                        try:
                                            geos[gk][fy] = float(val)
                                        except:
                                            pass
            except Exception:
                pass
                
        # Unificar 'Other Products' en 'Wearables, Home and Accessories'
        if "Wearables, Home and Accessories" in products and "Other Products" in products:
            for col, val in products["Other Products"].items():
                if col.startswith("FY") and pd.notna(val):
                    if col not in products["Wearables, Home and Accessories"] or pd.isna(products["Wearables, Home and Accessories"].get(col)):
                        products["Wearables, Home and Accessories"][col] = val
            del products["Other Products"]

        # Asegurar total de 'Products' en ejercicios antiguos donde no venía como subtotal
        if "Products" in products:
            for col in all_fys:
                if col.startswith("FY") and (col not in products["Products"] or pd.isna(products["Products"].get(col))):
                    sub_sum = 0.0
                    has_val = False
                    for pk in ["iPhone", "Mac", "iPad", "Wearables, Home and Accessories"]:
                        if pk in products and col in products[pk] and pd.notna(products[pk].get(col)):
                            sub_sum += float(products[pk][col])
                            has_val = True
                    if has_val:
                        products["Products"][col] = sub_sum

        # Cálculo LTM si 10-Q está disponible
        if latest_10q_inc is not None and not latest_10q_inc.empty:
            ytd_cols = [c for c in latest_10q_inc.columns if 'YTD' in str(c)]
            if len(ytd_cols) >= 2:
                ytd_curr = sorted(ytd_cols, reverse=True)[0]
                ytd_prev = sorted(ytd_cols, reverse=True)[1]
                annual_list = [fy for fy in all_fys if fy != 'LTM']
                if annual_list:
                    latest_fy = annual_list[0]
                    for pk in list(products.keys()):
                        if pk in products and latest_fy in products[pk]:
                            fy_val = products[pk][latest_fy]
                            q_match = latest_10q_inc[latest_10q_inc['dimension_member_label'] == pk]
                            if not q_match.empty:
                                vc = q_match.iloc[0].get(ytd_curr)
                                vp = q_match.iloc[0].get(ytd_prev)
                                if pd.notna(vc) and pd.notna(vp):
                                    products[pk]['LTM'] = fy_val + float(vc) - float(vp)
                                    
                    for gk in geo_keys:
                        if gk in geos and latest_fy in geos[gk]:
                            fy_val = geos[gk][latest_fy]
                            q_match = latest_10q_inc[latest_10q_inc['label'].str.contains(gk, case=False, na=False)]
                            if not q_match.empty:
                                vc = q_match.iloc[0].get(ytd_curr)
                                vp = q_match.iloc[0].get(ytd_prev)
                                if pd.notna(vc) and pd.notna(vp):
                                    geos[gk]['LTM'] = fy_val + float(vc) - float(vp)
                                    
        rows = list(products.values()) + list(geos.values())
        if rows:
            return pd.DataFrame(rows)
    except Exception as e:
        print(f"[SEC Extractor] Nota sobre desglose de segmentos: {e}")
    return None


def export_to_excel(filepath, summary_dict, ratios_dict, inc_df, bal_df, cf_df, ticker, company_name, fiscal_years, segment_df=None):
    """Exporta el modelo financiero con diseño institucional en 6 pestañas."""
    try:
        from excel_formatter import build_financial_excel
    except ImportError:
        from .excel_formatter import build_financial_excel
        
    build_financial_excel(filepath, summary_dict, ratios_dict, inc_df, bal_df, cf_df, ticker, company_name, fiscal_years, segment_df=segment_df)


def extract_sec_data(ticker, output_dir=None):
    """Extrae datos 100% oficiales y auditados desde SEC EDGAR (10 Años + LTM)."""
    cfg = load_sec_config()
    set_identity(cfg.get("sec_identity", "Pablo Inversiones pablo_inversiones@gmail.com"))
    
    print(f"\n[SEC Extractor] Conectando a SEC EDGAR para {ticker.upper()}...")
    company = sec_call_with_retry(Company, ticker.upper())
    cik = str(company.cik).zfill(10)
    name = company.name
    print(f"[SEC Extractor] Empresa verificada: {name} (CIK: {cik})")
    
    # Detectar estándar contable oficial (US-GAAP vs IFRS / Form 20-F o 40-F)
    accounting_std = "US-GAAP"
    try:
        latest_filings = company.get_filings(form=["10-K", "20-F", "40-F"])
        if latest_filings and len(latest_filings) > 0:
            top_form = str(latest_filings[0].form).upper()
            if "20-F" in top_form or "40-F" in top_form:
                accounting_std = "IFRS"
    except Exception:
        pass
    print(f"[SEC Extractor] Estándar contable detectado: {accounting_std}")
    
    if output_dir is None:
        output_dir = Path(cfg.get("local_output_path", "data/processed")) / ticker.upper()
    else:
        output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 1. Estados Financieros Anuales (10 Años)
    print("[SEC Extractor] Obteniendo estados contables auditados de los últimos 10 años...")
    inc_10_obj = sec_call_with_retry(company.income_statement, periods=10)
    bal_10_obj = sec_call_with_retry(company.balance_sheet, periods=10)
    cf_fn = getattr(company, 'cash_flow_statement', None) or getattr(company, 'cashflow_statement', None)
    cf_10_obj = sec_call_with_retry(cf_fn, periods=10) if cf_fn else None
    
    inc_df = inc_10_obj.to_dataframe().reset_index() if inc_10_obj is not None else pd.DataFrame()
    bal_df = bal_10_obj.to_dataframe().reset_index() if bal_10_obj is not None else pd.DataFrame()
    cf_df = cf_10_obj.to_dataframe().reset_index() if cf_10_obj is not None else pd.DataFrame()
    
    # Normalizar columnas de años fiscales
    def get_annual_cols(df):
        fys = []
        for col in df.columns:
            s = str(col)
            if s.startswith('FY ') or (s.startswith('FY') and any(ch.isdigit() for ch in s)):
                fys.append(col)
            elif any(s.startswith(str(yr)) for yr in range(2010, 2035)):
                fys.append(col)
        return sorted(fys, key=lambda x: [int(s) for s in str(x).replace('FY', '').split() if s.isdigit()][0] if any(ch.isdigit() for ch in str(x)) else 0, reverse=True)

    annual_cols_raw = get_annual_cols(inc_df)
    rename_map = {}
    for col in annual_cols_raw:
        m = re.search(r'(\d{4})', str(col))
        if m:
            rename_map[col] = f"FY{m.group(1)}"
        else:
            rename_map[col] = str(col)
    inc_df.rename(columns=rename_map, inplace=True)
    bal_df.rename(columns=rename_map, inplace=True)
    cf_df.rename(columns=rename_map, inplace=True)
    
    annual_fys = [rename_map[col] for col in annual_cols_raw if col in rename_map]
    annual_fys = list(dict.fromkeys(annual_fys))
    latest_fy = annual_fys[0] if annual_fys else None
    print(f"[SEC Extractor] Ejercicios fiscales anuales detectados ({len(annual_fys)}): {annual_fys}")
    
    # 2. Obtener Estados Trimestrales para cálculo de LTM
    print("[SEC Extractor] Consultando formularios trimestrales (10-Q / 6-K) para cálculo de LTM...")
    try:
        q_fins = sec_call_with_retry(company.get_quarterly_financials)
    except Exception:
        q_fins = None
    q_inc = q_fins.income_statement().to_dataframe() if q_fins and q_fins.income_statement() else None
    q_bal = q_fins.balance_sheet().to_dataframe() if q_fins and q_fins.balance_sheet() else None
    q_cf = q_fins.cash_flow_statement().to_dataframe() if q_fins and q_fins.cash_flow_statement() else None
    
    try:
        inc_ttm_obj = sec_call_with_retry(company.income_statement, period='ttm')
        inc_ttm_df = inc_ttm_obj.to_dataframe() if inc_ttm_obj else None
    except Exception:
        inc_ttm_df = None
    try:
        cf_ttm_obj = sec_call_with_retry(cf_fn, period='ttm') if cf_fn else None
        cf_ttm_df = cf_ttm_obj.to_dataframe() if cf_ttm_obj else None
    except Exception:
        cf_ttm_df = None
    try:
        bal_mrq_obj = sec_call_with_retry(company.balance_sheet, period='quarterly', periods=1)
        bal_mrq_df = bal_mrq_obj.to_dataframe().reset_index() if bal_mrq_obj else None
    except Exception:
        bal_mrq_df = None
    
    has_ltm = (q_inc is not None and not q_inc.empty) or (inc_ttm_df is not None and not inc_ttm_df.empty)
    all_fys = (["LTM"] + annual_fys) if has_ltm else annual_fys
    
    if has_ltm and latest_fy:
        print("[SEC Extractor] Calculando métricas LTM (Trailing Twelve Months)...")
        # --- Income Statement LTM ---
        # Detectar columnas trimestrales y YTD
        all_q_cols = [c for c in q_inc.columns if any(ch.isdigit() for ch in str(c)) and ('Q' in str(c) or 'YTD' in str(c) or '202' in str(c))] if q_inc is not None else []
        ytd_cols_inc = [c for c in all_q_cols if 'YTD' in str(c)]
        if not ytd_cols_inc:
            ytd_cols_inc = all_q_cols
        ytd_curr_inc = sorted(ytd_cols_inc, reverse=True)[0] if len(ytd_cols_inc) >= 1 else None
        ytd_prev_inc = sorted(ytd_cols_inc, reverse=True)[1] if len(ytd_cols_inc) >= 2 else None
        
        q_cols_ttm = [col for col in inc_ttm_df.columns if col.startswith('Q')] if inc_ttm_df is not None else []
        latest_q_ttm = q_cols_ttm[0] if q_cols_ttm else None
        ltm_inc_map = {}
        if inc_ttm_df is not None and latest_q_ttm:
            for _, row in inc_ttm_df.iterrows():
                lbl = str(row.get('label', '')).strip()
                val = row.get(latest_q_ttm)
                if pd.notna(val):
                    ltm_inc_map[lbl.lower()] = float(val)
                    
        ltm_vals_inc = []
        for _, row in inc_df.iterrows():
            c_name = str(row.get('concept', '')).strip()
            lbl = str(row.get('label', '')).strip()
            fy_val = row.get(latest_fy)
            val = None
            
            # Conceptos de acciones (point in time: saldo al cierre del trimestre) vs EPS (flujo acumulado 12M)
            is_share_count = any(k in c_name.lower() or k in lbl.lower() for k in ['sharesoutstanding', 'numberofshares'])
            is_per_share = any(k in c_name.lower() or k in lbl.lower() for k in ['pershare', 'per_share', 'per share'])
            
            if is_share_count and q_inc is not None and ytd_curr_inc:
                match_q = q_inc[q_inc['concept'].astype(str).str.lower().str.endswith(c_name.lower()) | (q_inc['concept'].astype(str).str.lower() == c_name.lower())]
                if not match_q.empty:
                    v_curr = match_q.iloc[0].get(ytd_curr_inc)
                    if pd.notna(v_curr):
                        try:
                            val = float(v_curr)
                        except (ValueError, TypeError):
                            pass
            elif q_inc is not None and ytd_curr_inc and ytd_prev_inc and pd.notna(fy_val):
                match_q = q_inc[q_inc['concept'].astype(str).str.lower().str.endswith(c_name.lower()) | (q_inc['concept'].astype(str).str.lower() == c_name.lower())]
                if not match_q.empty:
                    q_row = match_q.iloc[0]
                    v_curr = q_row.get(ytd_curr_inc)
                    v_prev = q_row.get(ytd_prev_inc)
                    if pd.notna(v_curr) and pd.notna(v_prev):
                        try:
                            val = float(fy_val) + float(v_curr) - float(v_prev)
                        except (ValueError, TypeError):
                            pass
            if val is None and not is_share_count and lbl.lower() in ltm_inc_map:
                val = ltm_inc_map[lbl.lower()]
            if val is None and pd.notna(fy_val):
                val = float(fy_val)
            ltm_vals_inc.append(val)
            
        inc_df.insert(inc_df.columns.get_loc(latest_fy), 'LTM', ltm_vals_inc)
        
        # Corroborar y calibrar que EPS en LTM refleje los 12 meses acumulados
        try:
            ni_match = inc_df[inc_df['concept'].astype(str).str.lower().str.contains('netincome', na=False)]
            sh_match = inc_df[inc_df['concept'].astype(str).str.lower().str.contains('dilutedshares', na=False) | inc_df['concept'].astype(str).str.lower().str.contains('sharesoutstandingdiluted', na=False)]
            if not ni_match.empty and not sh_match.empty:
                ni_val_ltm = float(ni_match.iloc[0].get('LTM', 0))
                sh_val_ltm = float(sh_match.iloc[0].get('LTM', 0))
                if ni_val_ltm > 0 and sh_val_ltm > 0:
                    exp_ltm_eps = round(ni_val_ltm / sh_val_ltm, 2)
                    for idx_r, r in inc_df.iterrows():
                        cn = str(r.get('concept', '')).lower()
                        if 'earningspersharediluted' in cn or 'dilutedearningspershare' in cn:
                            cur_v = r.get('LTM')
                            if cur_v is None or (exp_ltm_eps > 0 and cur_v < exp_ltm_eps * 0.4):
                                inc_df.at[idx_r, 'LTM'] = exp_ltm_eps
                                print(f"[SEC Extractor] LTM Diluted EPS calibrado a 12 meses acumulados: ${exp_ltm_eps} (en vez de ${cur_v})")
        except Exception as e:
            print(f"[SEC Extractor] Nota sobre calibración de EPS LTM: {e}")
        
        # --- Balance Sheet MRQ for LTM ---
        mrq_cols = [c for c in bal_mrq_df.columns if c.startswith('Q')] if bal_mrq_df is not None else []
        latest_mrq_col = mrq_cols[0] if mrq_cols else None
        ltm_vals_bal = []
        for _, row in bal_df.iterrows():
            c_name = str(row.get('concept', '')).strip()
            fy_val = row.get(latest_fy)
            val = None
            if bal_mrq_df is not None and latest_mrq_col:
                match_b = bal_mrq_df[bal_mrq_df['concept'].astype(str).str.lower().str.endswith(c_name.lower()) | (bal_mrq_df['concept'].astype(str).str.lower() == c_name.lower())]
                if not match_b.empty:
                    v = match_b.iloc[0].get(latest_mrq_col)
                    if pd.notna(v):
                        try:
                            val = float(v)
                        except (ValueError, TypeError):
                            pass
            if val is None and pd.notna(fy_val):
                val = float(fy_val)
            ltm_vals_bal.append(val)
            
        bal_df.insert(bal_df.columns.get_loc(latest_fy), 'LTM', ltm_vals_bal)
        
        # --- Cash Flow Statement LTM ---
        all_q_cols_cf = [c for c in q_cf.columns if any(ch.isdigit() for ch in str(c)) and ('Q' in str(c) or 'YTD' in str(c) or '202' in str(c))] if q_cf is not None else []
        ytd_cols_cf = [c for c in all_q_cols_cf if 'YTD' in str(c)]
        if not ytd_cols_cf:
            ytd_cols_cf = all_q_cols_cf
        ytd_curr_cf = sorted(ytd_cols_cf, reverse=True)[0] if len(ytd_cols_cf) >= 1 else None
        ytd_prev_cf = sorted(ytd_cols_cf, reverse=True)[1] if len(ytd_cols_cf) >= 2 else None
        ltm_vals_cf = []
        for _, row in cf_df.iterrows():
            c_name = str(row.get('concept', '')).strip()
            fy_val = row.get(latest_fy)
            val = None
            if q_cf is not None and ytd_curr_cf and ytd_prev_cf and pd.notna(fy_val):
                match_cf = q_cf[q_cf['concept'].astype(str).str.lower().str.endswith(c_name.lower()) | (q_cf['concept'].astype(str).str.lower() == c_name.lower())]
                if not match_cf.empty:
                    q_row = match_cf.iloc[0]
                    v_curr = q_row.get(ytd_curr_cf)
                    v_prev = q_row.get(ytd_prev_cf)
                    if pd.notna(v_curr) and pd.notna(v_prev):
                        try:
                            f_fy = float(fy_val)
                            f_curr = float(v_curr)
                            f_prev = float(v_prev)
                            # Alinear signos entre estados trimestrales y anuales si difieren por convención contable
                            if (f_fy > 0 and f_curr < 0) or (f_fy < 0 and f_curr > 0):
                                f_curr = -f_curr
                                f_prev = -f_prev
                            val = f_fy + f_curr - f_prev
                        except (ValueError, TypeError):
                            pass
            if val is None and pd.notna(fy_val):
                val = float(fy_val)
            ltm_vals_cf.append(val)
            
        cf_df.insert(cf_df.columns.get_loc(latest_fy), 'LTM', ltm_vals_cf)
        
    # 3. Datos de Segmentos (10 Años + LTM de Productos y Geografías)
    print("[SEC Extractor] Extrayendo desglose de segmentos histórico de 10 años + LTM...")
    segment_df = sec_call_with_retry(build_10yr_segment_df, company, all_fys, q_inc)
    if segment_df is None or segment_df.empty:
        try:
            single_fins = sec_call_with_retry(company.get_financials)
            if single_fins and single_fins.income_statement():
                segment_df = single_fins.income_statement().to_dataframe()
        except Exception:
            segment_df = None
        
    # Convertir a diccionarios conceptuales para JSON
    inc_data = dataframe_to_concept_dict(inc_df, all_fys)
    bal_data = dataframe_to_concept_dict(bal_df, all_fys)
    cf_data = dataframe_to_concept_dict(cf_df, all_fys)
    
    # Cargar facts como respaldo para años antiguos
    facts_df = None
    try:
        facts_obj = sec_call_with_retry(company.get_facts)
        if hasattr(facts_obj, 'to_dataframe'):
            facts_df = facts_obj.to_dataframe()
    except Exception:
        pass
        
    print(f"[SEC Extractor] Generando resumen canónico y ratios para períodos: {all_fys}")
    canonical, ratios = extract_canonical_summary(inc_data, bal_data, cf_data, all_fys, facts_df=facts_df)
    
    full_dataset = {
        "ticker": ticker.upper(),
        "company_name": name,
        "cik": cik,
        "accounting_standard": accounting_std,
        "source": f"SEC EDGAR ({accounting_std} Oficial)",
        "extraction_timestamp": datetime.now().isoformat(),
        "fiscal_years": all_fys,
        "canonical_summary": canonical,
        "key_ratios": ratios,
        "income_statement_detail": inc_data,
        "balance_sheet_detail": bal_data,
        "cash_flow_detail": cf_data
    }
    
    # Guardar JSON
    json_path = output_dir / "financial_statements.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(full_dataset, f, indent=2, ensure_ascii=False)
    print(f"[SEC Extractor] JSON canónico generado: {json_path}")
    
    # Guardar Excel de 6 pestañas
    excel_path = output_dir / "financial_statements.xlsx"
    export_to_excel(excel_path, canonical, ratios, inc_df, bal_df, cf_df, ticker, name, all_fys, segment_df=segment_df)
    print(f"[SEC Extractor] Excel institucional de 6 pestañas generado: {excel_path}")
    
    # 4. Narrativas 10-K
    print("[SEC Extractor] Extrayendo secciones cualitativas del último 10-K...")
    filings = company.get_filings(form="10-K")
    narratives = {
        "ticker": ticker.upper(),
        "company_name": name,
        "filing_date": None,
        "accession_number": None,
        "item_1_business": "",
        "item_1a_risk_factors": "",
        "item_7_mda": ""
    }
    
    if len(filings) > 0:
        latest_10k = filings[0]
        narratives["filing_date"] = str(latest_10k.filing_date)
        narratives["accession_number"] = str(latest_10k.accession_number)
        
        try:
            doc_10k = latest_10k.obj()
            if hasattr(doc_10k, 'items'):
                if 'Item 1' in doc_10k.items:
                    narratives["item_1_business"] = str(doc_10k['Item 1'])
                if 'Item 1A' in doc_10k.items:
                    narratives["item_1a_risk_factors"] = str(doc_10k['Item 1A'])
                if 'Item 7' in doc_10k.items:
                    narratives["item_7_mda"] = str(doc_10k['Item 7'])
        except Exception as e:
            print(f"[SEC Extractor] Nota sobre items narrativos: {e}")
            
    narrative_path = output_dir / "sec_narrative.json"
    with open(narrative_path, "w", encoding="utf-8") as f:
        json.dump(narratives, f, indent=2, ensure_ascii=False)
    print(f"[SEC Extractor] Narrativas guardadas: {narrative_path}")
    
    return full_dataset, narratives


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--out-dir", default=None)
    args = parser.parse_args()
    
    extract_sec_data(args.ticker, args.out_dir)
