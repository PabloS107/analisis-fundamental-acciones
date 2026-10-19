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

try:
    from pipeline.financial_bilingual_map import get_spanish_clarification
except ImportError:
    try:
        from financial_bilingual_map import get_spanish_clarification
    except ImportError:
        def get_spanish_clarification(label, concept=None):
            return None


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
                        num_val = float(val)
                        # Normalización contable: costos y gastos operativos deben ser magnitudes positivas
                        c_low = concept_str.lower()
                        expense_indicators = (
                            'costof', 'expense', 'expenses', 'charges', 'provisions',
                            'recurringcapitalexpenditures', 'paymentsforcapitalimprovements',
                            'paymentsforpropertyimprovements'
                        )
                        non_expense_exclusions = (
                            'income', 'revenue', 'gain', 'operatingincomeloss',
                            'netincomeloss', 'profitloss'
                        )
                        if any(ind in c_low for ind in expense_indicators) and not any(excl in c_low for excl in non_expense_exclusions):
                            num_val = abs(num_val)
                        values[p] = num_val
                    except (ValueError, TypeError):
                        pass
                        
        depth_val = int(row.get('depth', 0)) if pd.notna(row.get('depth')) else 0
        is_abstract = bool(row.get('is_abstract', False)) if pd.notna(row.get('is_abstract')) else False
        is_total = bool(row.get('is_total', False)) if pd.notna(row.get('is_total')) else False
        section_val = str(row.get('section', '')).strip() if pd.notna(row.get('section')) else ''

        if concept_str not in data_by_concept or len(values) > len(data_by_concept[concept_str].get("values", {})):
            data_by_concept[concept_str] = {
                "label": label,
                "standard_concept": std_concept if std_concept != 'None' else None,
                "values": values,
                "depth": depth_val,
                "is_abstract": is_abstract,
                "is_total": is_total,
                "section": section_val
            }
            
    return data_by_concept


# ==============================================================================
# TAXONOMÍA Y ALIAS RECÍPROCOS DE ARQUETIPOS CONTABLES INSTITUCIONALES
# ==============================================================================
CORPORATE_ARCHETYPE_ALIASES = ("CORPORATE_STANDARD", "STANDARD_CORPORATE")

CANONICAL_ARCHETYPES = {
    "CORPORATE_STANDARD",
    "STANDARD_CORPORATE",
    "FINANCIAL_BANKING",
    "INSURANCE",
    "REAL_ESTATE_REIT",
    "PLATFORM_ECOSYSTEM",
}

ARCHETYPE_ALIASES = {
    "CORPORATE_STANDARD": "STANDARD_CORPORATE",
    "STANDARD_CORPORATE": "STANDARD_CORPORATE",
    "FINANCIAL_BANKING": "FINANCIAL_BANKING",
    "BANKING_FINANCIAL": "FINANCIAL_BANKING",
    "BANKING": "FINANCIAL_BANKING",
    "INSURANCE": "INSURANCE",
    "INSURER": "INSURANCE",
    "REAL_ESTATE_REIT": "REAL_ESTATE_REIT",
    "REIT": "REAL_ESTATE_REIT",
    "REAL_ESTATE": "REAL_ESTATE_REIT",
    "PLATFORM_ECOSYSTEM": "PLATFORM_ECOSYSTEM",
    "ECOSYSTEM_PLATFORM": "PLATFORM_ECOSYSTEM",
}


def normalize_archetype(archetype: str, default: str = "STANDARD_CORPORATE") -> str:
    """
    Normaliza el identificador de arquetipo admitiendo alias canónicos y recíprocos:
    CORPORATE_STANDARD <-> STANDARD_CORPORATE.
    """
    if not archetype:
        return default
    arch_clean = str(archetype).strip().upper()
    if arch_clean in CORPORATE_ARCHETYPE_ALIASES:
        return default
    return ARCHETYPE_ALIASES.get(arch_clean, arch_clean)


try:
    from entity_classifier import detect_company_archetype, is_banking_or_financial
except ImportError:
    from .entity_classifier import detect_company_archetype, is_banking_or_financial



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
        generate_data_integrity_badge,
    )
except ImportError:
    from .financial_taxonomy import (
        CORPORATE_TAXONOMY_MAP,
        BANKING_TAXONOMY_MAP,
        REIT_TAXONOMY_MAP,
        INSURANCE_TAXONOMY_MAP,
        PLATFORM_TAXONOMY_MAP,
        XBRL_TAXONOMY_MAP,
        get_first_matching_value,
        reconcile_accounting_identities,
        generate_data_integrity_badge,
    )


def get_all_matching_sum(data_by_concept, concept_candidates, period):
    """
    Suma acumulativamente partidas independientes de una categoría contable (ej. adquisiciones M&A
    desglosadas o tramos de deuda/inversiones) evitando duplicar conceptos.
    """
    total = 0.0
    matched = False
    matched_tokens = set()
    for cand in concept_candidates:
        cand_lower = cand.lower().split(':')[-1].split('_')[-1]
        for c_key, c_data in data_by_concept.items():
            if 'abstract' in c_key.lower():
                continue
            k_lower = c_key.lower()
            k_token = k_lower.split(':')[-1].split('_')[-1]
            if (k_token == cand_lower or k_lower == cand_lower) and k_token not in matched_tokens:
                val = c_data["values"].get(period)
                if val is not None and not pd.isna(val):
                    try:
                        total += float(val)
                        matched = True
                        matched_tokens.add(k_token)
                    except (ValueError, TypeError):
                        pass
    return total if matched else None


def get_mrq_fact(facts_df, concept_candidates, mrq_date=None):
    """Busca el saldo al cierre del trimestre más reciente (MRQ / LTM Balance Sheet) en Company Facts."""
    if facts_df is None or facts_df.empty:
        return None
    if mrq_date is None:
        asset_matches = facts_df[facts_df['concept'].astype(str).str.endswith(':Assets') | facts_df['concept'].astype(str).str.endswith(':StockholdersEquity')]
        if not asset_matches.empty:
            mrq_date = asset_matches['period_end'].dropna().max()
        else:
            mrq_date = facts_df['period_end'].dropna().max()
            
    concepts_series = facts_df['concept'].astype(str)
    concepts_tokens = concepts_series.str.split(':').str[-1].str.split('_').str[-1].str.lower()
    
    for cand in concept_candidates:
        cand_lower = cand.lower()
        matches = facts_df[(facts_df['period_end'] == mrq_date) & (concepts_tokens == cand_lower)]
        if not matches.empty:
            val = matches.iloc[-1].get('numeric_value')
            if pd.notna(val) and str(val) != 'nan':
                try:
                    return float(val)
                except (ValueError, TypeError):
                    pass
    return None


def get_mrq_fact_sum(facts_df, concept_candidates, mrq_date=None):
    """Suma acumulativamente conceptos en facts_df al cierre de MRQ (ej. deuda corriente + valores negociables)."""
    if facts_df is None or facts_df.empty:
        return None
    if mrq_date is None:
        asset_matches = facts_df[facts_df['concept'].astype(str).str.endswith(':Assets') | facts_df['concept'].astype(str).str.endswith(':StockholdersEquity')]
        if not asset_matches.empty:
            mrq_date = asset_matches['period_end'].dropna().max()
        else:
            mrq_date = facts_df['period_end'].dropna().max()
            
    concepts_series = facts_df['concept'].astype(str)
    concepts_tokens = concepts_series.str.split(':').str[-1].str.split('_').str[-1].str.lower()
    
    total = 0.0
    matched = False
    matched_tokens = set()
    for cand in concept_candidates:
        cand_lower = cand.lower().split(':')[-1].split('_')[-1]
        matches = facts_df[(facts_df['period_end'] == mrq_date) & (concepts_tokens == cand_lower)]
        if not matches.empty and cand_lower not in matched_tokens:
            val = matches.iloc[-1].get('numeric_value')
            if pd.notna(val) and str(val) != 'nan':
                try:
                    total += float(val)
                    matched = True
                    matched_tokens.add(cand_lower)
                except (ValueError, TypeError):
                    pass
    return total if matched else None


def get_ltm_quarterly_metric(facts_df, concept_candidates, mode='sum'):
    """Calcula una métrica LTM (suma o promedio ponderado de 4 trimestres consecutivos) vía Company Facts."""
    if facts_df is None or facts_df.empty:
        return None
    concepts_series = facts_df['concept'].astype(str)
    concepts_tokens = concepts_series.str.split(':').str[-1].str.split('_').str[-1].str.lower()
    
    for cand in concept_candidates:
        cand_lower = cand.lower()
        sub = facts_df[concepts_tokens == cand_lower].copy()
        if sub.empty:
            continue
        
        start_col = 'period_start' if 'period_start' in sub.columns else ('start' if 'start' in sub.columns else None)
        end_col = 'period_end' if 'period_end' in sub.columns else ('end' if 'end' in sub.columns else None)
        if not start_col or not end_col:
            continue
            
        sub['p_start'] = pd.to_datetime(sub[start_col], errors='coerce')
        sub['p_end'] = pd.to_datetime(sub[end_col], errors='coerce')
        sub['days'] = (sub['p_end'] - sub['p_start']).dt.days
        sub['num_val'] = pd.to_numeric(sub['numeric_value'], errors='coerce')
        sub = sub.dropna(subset=['p_end', 'num_val'])
        
        # Trimestres discretos (60 a 115 días)
        q_rows = sub[(sub['days'] >= 60) & (sub['days'] <= 115)].sort_values('p_end')
        q_rows = q_rows.drop_duplicates(subset=['p_end'], keep='last')
        
        # Derivar Q4 = FY - 9M si Q4 no se reporta de forma independiente
        fy_rows = sub[(sub['days'] >= 330) & (sub['days'] <= 380)].sort_values('p_end')
        ytd9_rows = sub[(sub['days'] >= 240) & (sub['days'] <= 300)].sort_values('p_end')
        
        derived_q4s = []
        for _, fy_r in fy_rows.iterrows():
            fy_end = fy_r['p_end']
            fy_val = fy_r['num_val']
            matching_9m = ytd9_rows[(ytd9_rows['p_start'] == fy_r['p_start']) & (ytd9_rows['p_end'] < fy_end)]
            if not matching_9m.empty:
                ytd_val = matching_9m.iloc[-1]['num_val']
                if mode == 'avg':
                    q4_val = 4.0 * fy_val - 3.0 * ytd_val
                else:
                    q4_val = fy_val - ytd_val
                if fy_end not in q_rows['p_end'].values:
                    derived_q4s.append({'p_end': fy_end, 'num_val': q4_val, 'days': 90})
                    
        if derived_q4s:
            q_rows = pd.concat([q_rows, pd.DataFrame(derived_q4s)], ignore_index=True).sort_values('p_end')
            q_rows = q_rows.drop_duplicates(subset=['p_end'], keep='last')
            
        last_4 = q_rows.tail(4)
        if len(last_4) == 4:
            span = (last_4.iloc[-1]['p_end'] - last_4.iloc[0]['p_end']).days
            if 250 <= span <= 300:
                if mode == 'avg':
                    return float(last_4['num_val'].mean())
                else:
                    return round(float(last_4['num_val'].sum()), 2)
    return None


def get_fact_fallback(facts_df, concept_candidates, fy_str, is_flow=False):
    """Busca una partida en Company Facts como respaldo si no figura en el estado multi-período."""
    if facts_df is None or facts_df.empty:
        return None
    if fy_str == "LTM":
        if is_flow:
            if any("earningspershare" in c.lower() or "eps" in c.lower() for c in concept_candidates):
                return get_ltm_quarterly_metric(facts_df, concept_candidates, mode='sum')
            return None
        # Balance Sheet / Point in Time: MRQ
        if any("shares" in c.lower() for c in concept_candidates):
            avg_sh = get_ltm_quarterly_metric(facts_df, concept_candidates, mode='avg')
            if avg_sh is not None:
                return avg_sh
        return get_mrq_fact(facts_df, concept_candidates)
        
    year_digits = ''.join(filter(str.isdigit, fy_str))
    if not year_digits:
        return None
    fy_int = int(year_digits)
    
    # Extraer token local para todos los conceptos en facts_df (sin namespace)
    concepts_series = facts_df['concept'].astype(str)
    concepts_tokens = concepts_series.str.split(':').str[-1].str.split('_').str[-1].str.lower()
    
    # Matching temporal: primero por period_end (año de balance contable real)
    p_end_year = facts_df['period_end'].astype(str).str[:4]
    
    for cand in concept_candidates:
        cand_lower = cand.lower()
        # 1. Matching exacto por año de period_end
        matches = facts_df[(p_end_year == str(fy_int)) & (concepts_tokens == cand_lower)]
        if matches.empty:
            # 2. Respaldo por fiscal_year
            matches = facts_df[(facts_df['fiscal_year'] == fy_int) & (concepts_tokens == cand_lower)]
            
        if not matches.empty:
            fy_matches = matches[matches['fiscal_period'].astype(str).str.upper() == 'FY']
            chosen_subset = fy_matches if not fy_matches.empty else matches
            
            # Si es flujo contable (Income Statement / Cash Flow), asegurar duración anual (>= 300 días)
            # para evitar trimestres aislados (ej. Q4) erróneamente etiquetados como fiscal_period: FY
            if is_flow:
                start_col = None
                for c in ['period_start', 'start']:
                    if c in chosen_subset.columns:
                        start_col = c
                        break
                end_col = None
                for c in ['period_end', 'end']:
                    if c in chosen_subset.columns:
                        end_col = c
                        break
                if start_col and end_col:
                    try:
                        starts = pd.to_datetime(chosen_subset[start_col], errors='coerce')
                        ends = pd.to_datetime(chosen_subset[end_col], errors='coerce')
                        durations = (ends - starts).dt.days
                        long_subset = chosen_subset[durations >= 300]
                        if not long_subset.empty:
                            chosen_subset = long_subset
                    except Exception:
                        pass

            for f_col in ['filed', 'filing_date']:
                if f_col in chosen_subset.columns:
                    chosen_subset = chosen_subset.sort_values(f_col)
                    break
            chosen = chosen_subset.iloc[-1]
            val = chosen.get('numeric_value')
            if pd.notna(val) and str(val) != 'nan':
                try:
                    return float(val)
                except (ValueError, TypeError):
                    pass
    return None


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
        "tangible_capital_employed": {},
        "dividends_paid": {},
        "share_repurchases": {},
        "stock_plans_proceeds": {},
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
        "interest_expense": {}
    }
    
    if is_financial or archetype in ("FINANCIAL_BANKING", "PLATFORM_ECOSYSTEM"):
        canonical["net_interest_income"] = {}
        canonical["non_interest_income"] = {}
        canonical["credit_loss_provisions"] = {}
        canonical["total_deposits"] = {}
        canonical["net_loans"] = {}
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
            # 1. Ingresos en REIT: Rental Revenue (o fallback a Revenue total)
            rent_rev = get_first_matching_value(inc_data, REIT_TAXONOMY_MAP["rental_revenue"], p)
            if rent_rev is None and facts_df is not None:
                rent_rev = get_fact_fallback(facts_df, REIT_TAXONOMY_MAP["rental_revenue"], p, is_flow=True)
            if rent_rev is None:
                rent_rev = get_first_matching_value(inc_data, XBRL_TAXONOMY_MAP["revenue"], p)
                if rent_rev is None and facts_df is not None:
                    rent_rev = get_fact_fallback(facts_df, XBRL_TAXONOMY_MAP["revenue"], p, is_flow=True)
            canonical["rental_revenue"][p] = rent_rev
            canonical["revenue"][p] = rent_rev
            rev = rent_rev

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
            # 1. Ingresos en Seguros: Net Premiums Earned + Net Investment Income
            prem_earned = get_first_matching_value(inc_data, INSURANCE_TAXONOMY_MAP["net_premiums_earned"], p)
            if prem_earned is None and facts_df is not None:
                prem_earned = get_fact_fallback(facts_df, INSURANCE_TAXONOMY_MAP["net_premiums_earned"], p, is_flow=True)
            canonical["net_premiums_earned"][p] = prem_earned

            inv_inc = get_first_matching_value(inc_data, INSURANCE_TAXONOMY_MAP["net_investment_income"], p)
            if inv_inc is None and facts_df is not None:
                inv_inc = get_fact_fallback(facts_df, INSURANCE_TAXONOMY_MAP["net_investment_income"], p, is_flow=True)
            canonical["net_investment_income"][p] = inv_inc

            if prem_earned is not None and inv_inc is not None:
                rev = round(prem_earned + inv_inc, 2)
            elif prem_earned is not None:
                rev = prem_earned
            else:
                rev = get_first_matching_value(inc_data, XBRL_TAXONOMY_MAP["revenue"], p)
                if rev is None and facts_df is not None:
                    rev = get_fact_fallback(facts_df, XBRL_TAXONOMY_MAP["revenue"], p, is_flow=True)
            canonical["revenue"][p] = rev

            # 2. En aseguradoras no existe COGS comercial ni Margen Bruto
            canonical["cost_of_goods_sold"][p] = None
            cogs = None
            canonical["gross_profit"][p] = None
            gp = None

            # 3. Gastos Operativos y Siniestros
            op_exp = get_first_matching_value(inc_data, XBRL_TAXONOMY_MAP["operating_expenses"], p)
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
        
        ebit_cands = XBRL_TAXONOMY_MAP["operating_income"]
        ebit = get_first_matching_value(inc_data, ebit_cands, p)
        if ebit is None and facts_df is not None:
            ebit = get_fact_fallback(facts_df, ebit_cands, p, is_flow=True)
        if ebit is None and rev is not None and op_exp is not None and abs(op_exp) > 0 and archetype not in ("FINANCIAL_BANKING", "INSURANCE"):
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
            
            comb_debt = get_first_matching_value(bal_data, ["DebtLongtermAndShorttermCombinedAmount", "us-gaap_DebtLongtermAndShorttermCombinedAmount", "TotalDebt"], p)
            if comb_debt is not None:
                tot_debt = round(float(comb_debt), 2)
            else:
                st_debt = get_first_matching_value(bal_data, XBRL_TAXONOMY_MAP["short_term_debt"], p) or 0.0
                lt_debt = get_first_matching_value(bal_data, XBRL_TAXONOMY_MAP["long_term_debt"], p) or 0.0
                tot_debt = round(st_debt + lt_debt, 2)
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
            
            comb_debt = get_first_matching_value(bal_data, ["DebtLongtermAndShorttermCombinedAmount", "us-gaap_DebtLongtermAndShorttermCombinedAmount", "TotalDebt"], p)
            if comb_debt is not None:
                tot_debt = round(float(comb_debt), 2)
            else:
                st_debt = get_first_matching_value(bal_data, XBRL_TAXONOMY_MAP["short_term_debt"], p)
                if st_debt is None and facts_df is not None:
                    st_debt = get_fact_fallback(facts_df, XBRL_TAXONOMY_MAP["short_term_debt"], p)
                st_debt = st_debt or 0.0

                lt_debt = get_first_matching_value(bal_data, XBRL_TAXONOMY_MAP["long_term_debt"], p)
                if lt_debt is None and facts_df is not None:
                    lt_debt = get_fact_fallback(facts_df, XBRL_TAXONOMY_MAP["long_term_debt"], p)
                lt_debt = lt_debt or 0.0

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


def build_and_save_segments_data(company, all_fys, output_dir=None, canonical_rev=None, latest_10q_inc=None):
    """
    Extractor Dinámico y Universal de Segmentos Contables Oficiales desde SEC EDGAR (XBRL).
    Bajo normativas contables ASC 280 (Segment Reporting) y ASC 606 (Disaggregation of Revenue).
    
    1. Escanea dinámicamente los formularios 10-K y 10-Q de SEC EDGAR en búsqueda de notas XBRL
       dimensionales de segmentos operativos, productos, líneas de negocio y regiones geográficas.
    2. Identifica jerarquías, subtotales y reclasificaciones sin hardcoding de nombres de marcas ni tickers.
    3. Normaliza las series anuales (FY2024, FY2025...) y computa el LTM oficial sincronizado con ingresos canónicos.
    4. Genera y persiste 'data/processed/{TICKER}/segments_data.json' y retorna el DataFrame auditado.
    """
    output_path = Path(output_dir) if output_dir else Path("data/processed")
    seg_json_path = output_path / "segments_data.json"
    ticker_str = str(getattr(company, "ticker", getattr(company, "tickers", [output_path.name])[0]))

    # Deduplicación canónica de períodos para evitar columnas 'LTM' repetidas
    clean_fys = []
    for p in (all_fys or []):
        if p not in clean_fys:
            clean_fys.append(p)
    all_fys = clean_fys
    annual_fys = [p for p in all_fys if p != "LTM"]
    latest_fy = annual_fys[0] if annual_fys else "FY2025"

    print(f"[SEC Extractor] Extracción dinámica de segmentos XBRL para {ticker_str}...")

    product_segments = []
    geographic_segments = []
    segment_op_income = []
    detected_prod_names = set()
    detected_geo_names = set()

    def _norm_seg_key(name_str):
        return re.sub(r'\s+', ' ', str(name_str).lower().replace('&', 'and')).strip()

    def _scale_to_millions(num):
        if abs(num) > 1e7:
            return num / 1e6
        elif abs(num) > 1e4 and canonical_rev and abs(num) < (canonical_rev.get("LTM", 1e9) / 100.0):
            return num / 1000.0
        elif abs(num) > 5e5 and not canonical_rev:
            return num / 1000.0
        return num

    # Función auxiliar para mapear columnas XBRL a etiquetas canónicas FY
    def _map_col_to_fy(col_name):
        c_str = str(col_name).strip()
        m = re.search(r'(\d{4})', c_str)
        if m:
            return f"FY{m.group(1)}"
        return c_str

    geo_keywords = {
        "americas", "europe", "greater china", "china", "japan", "asia", "pacific",
        "international", "domestic", "united states", "u.s.", "non-us", "taiwan",
        "latin america", "brazil", "mexico", "other countries", "rest of world",
        "emea", "apac", "ireland", "other regions", "rest of asia pacific"
    }

    try:
        f10k_list = company.get_filings(form="10-K")
        if not f10k_list:
            f10k_list = company.get_filings(form="20-F")
        f10q_list = company.get_filings(form="10-Q")
        if not f10q_list:
            f10q_list = company.get_filings(form="6-K")

        if f10k_list:
            x_10k = f10k_list[0].xbrl()
            statements_to_scan = []
            if x_10k and hasattr(x_10k, "statements"):
                for s in x_10k.statements:
                    r = str(getattr(s, "role_or_type", ""))
                    r_low = r.lower()
                    if any(bad in r_low for bad in [
                        "marketable", "fairvalue", "cash", "receivable", "deferredrevenue",
                        "performanceobligation", "debt", "concentration", "accumulatedothercomprehensive"
                    ]):
                        continue
                    if any(k in r_low for k in ["segment", "disaggregation", "brand", "market", "channel", "geographic"]) and "details" in r_low:
                        statements_to_scan.append(s)

            for s in statements_to_scan:
                try:
                    df = s.to_dataframe()
                    fy_cols = {}
                    for c in df.columns:
                        c_str = str(c)
                        if "(FY)" in c_str or re.search(r'\b202\d\b', c_str):
                            fy_cols[c] = _map_col_to_fy(c_str)

                    for _, row in df.iterrows():
                        lbl = str(row.get("label", "")).strip()
                        conc = str(row.get("concept", "")).lower()

                        if not lbl or len(lbl) < 2:
                            continue
                        # Filtrar filas irrelevantes o de costos no operacionales
                        if any(bad in lbl.lower() for bad in [
                            "reclassifications, net of tax", "hedges", "pension and other postretirement",
                            "payroll", "advertising expense", "rent and occupancy", "depreciation", "sg&a", "impairment"
                        ]):
                            continue

                        # Extracción de ingresos
                        is_rev = any(k in conc for k in ["revenue", "sales"])
                        is_op_inc = any(k in conc for k in ["operatingincome", "incomelossfromcontinuingoperations"])

                        if not (is_rev or is_op_inc):
                            continue

                        v_dict = {}
                        has_val = False
                        for raw_col, fy_norm in fy_cols.items():
                            val = row.get(raw_col)
                            if pd.notna(val) and val != "":
                                try:
                                    num = _scale_to_millions(float(val))
                                    v_dict[fy_norm] = round(num, 1)
                                    has_val = True
                                except Exception:
                                    pass

                        if not has_val:
                            continue

                        clean_name = re.sub(r'^(Reportable segments - |Operating segments - )', '', lbl).strip()
                        parent_segment = None
                        is_subsegment = False

                        # Detección de subsegmentos jerárquicos ("Advertising - Family of Apps", etc.)
                        if " - " in clean_name and not any(g in clean_name.lower() for g in geo_keywords):
                            parts = clean_name.split(" - ")
                            if len(parts) == 2:
                                clean_name = parts[0].strip()
                                parent_segment = parts[1].strip()
                                is_subsegment = True
                            else:
                                clean_name = parts[-1].strip()

                        is_geo = any(g in clean_name.lower() for g in geo_keywords) or any(g in lbl.lower() for g in geo_keywords)

                        # Detección de totales consolidados para no mezclarlos con segmentos de producto
                        is_consolidated_total = clean_name.lower() in [
                            "revenue", "total revenue", "total revenues", "total net sales",
                            "total net revenue", "consolidated revenue", "net sales", "total"
                        ]
                        is_sub = is_consolidated_total or any(k in clean_name.lower() for k in ["total", "products", "operating segments", "wholesale", "direct-to-consumer", "direct to consumer", "dtc"])

                        # Detección de subregiones geográficas (ej. "United States" dentro de "United States & Canada")
                        if is_geo and clean_name.lower() == "united states":
                            is_subsegment = True
                            parent_segment = "United States & Canada"

                        norm_key = _norm_seg_key(clean_name)
                        if is_op_inc:
                            segment_op_income.append({"name": clean_name, "values": v_dict})
                        elif is_geo:
                            seg_entry = {
                                "name": clean_name,
                                "is_subtotal": is_sub,
                                "is_subsegment": is_subsegment,
                                "parent": parent_segment,
                                "values": v_dict
                            }
                            if norm_key not in detected_geo_names:
                                geographic_segments.append(seg_entry)
                                detected_geo_names.add(norm_key)
                        elif not is_geo and not is_consolidated_total:
                            seg_entry = {
                                "name": clean_name,
                                "is_subtotal": is_sub,
                                "is_subsegment": is_subsegment,
                                "parent": parent_segment,
                                "values": v_dict
                            }
                            if norm_key not in detected_prod_names:
                                product_segments.append(seg_entry)
                                detected_prod_names.add(norm_key)

                except Exception as s_err:
                    print(f"[SEC Extractor] Aviso analizando tabla de segmentos 10-K: {s_err}")

        # Escaneo de Formulario 10-Q para cálculo exacto de LTM (FY_latest + YTD_actual - YTD_anterior)
        if f10q_list and (product_segments or geographic_segments):
            try:
                k_rep_date = str(getattr(f10k_list[0], "period_of_report", "")) if f10k_list else ""
                q_rep_date = str(getattr(f10q_list[0], "period_of_report", ""))
                if not k_rep_date or q_rep_date > k_rep_date:
                    x_10q = f10q_list[0].xbrl()
                    q_stmts = []
                    if x_10q and hasattr(x_10q, "statements"):
                        for s in x_10q.statements:
                            r_low = str(getattr(s, "role_or_type", "")).lower()
                            if any(bad in r_low for bad in [
                                "marketable", "fairvalue", "cash", "receivable", "deferredrevenue",
                                "performanceobligation", "debt", "concentration", "accumulatedothercomprehensive"
                            ]):
                                continue
                            if any(k in r_low for k in ["segment", "disaggregation", "brand", "market", "channel", "geographic"]) and "details" in r_low:
                                q_stmts.append(s)

                    for s in q_stmts:
                        try:
                            q_df = s.to_dataframe()
                            ytd_cols = [c for c in q_df.columns if "YTD" in str(c) and any(ch.isdigit() for ch in str(c))]
                            if not ytd_cols:
                                ytd_cols = [c for c in q_df.columns if any(ch.isdigit() for ch in str(c)) and ("Q" in str(c) or "202" in str(c))]
                            ytd_sorted = sorted(ytd_cols, key=lambda x: str(x), reverse=True)
                            ytd_curr = ytd_sorted[0] if len(ytd_sorted) >= 1 else None
                            ytd_prev = ytd_sorted[1] if len(ytd_sorted) >= 2 else None

                            if not (ytd_curr and ytd_prev):
                                continue

                            for _, row in q_df.iterrows():
                                lbl = str(row.get("label", "")).strip()
                                conc = str(row.get("concept", "")).lower()
                                if not lbl or len(lbl) < 2:
                                    continue
                                is_rev = any(k in conc for k in ["revenue", "sales"])
                                is_op_inc = any(k in conc for k in ["operatingincome", "incomelossfromcontinuingoperations"])
                                if not (is_rev or is_op_inc):
                                    continue

                                v_curr_raw = row.get(ytd_curr)
                                v_prev_raw = row.get(ytd_prev)
                                if pd.isna(v_curr_raw) or pd.isna(v_prev_raw) or v_curr_raw == "" or v_prev_raw == "":
                                    continue
                                try:
                                    v_curr_m = _scale_to_millions(float(v_curr_raw))
                                    v_prev_m = _scale_to_millions(float(v_prev_raw))
                                except Exception:
                                    continue

                                q_clean_name = re.sub(r'^(Reportable segments - |Operating segments - )', '', lbl).strip()
                                if " - " in q_clean_name and not any(g in q_clean_name.lower() for g in geo_keywords):
                                    parts = q_clean_name.split(" - ")
                                    q_clean_name = parts[0].strip() if len(parts) == 2 else parts[-1].strip()
                                q_norm = _norm_seg_key(q_clean_name)

                                target_lists = [segment_op_income] if is_op_inc else [product_segments, geographic_segments]
                                for t_list in target_lists:
                                    for item in t_list:
                                        if _norm_seg_key(item.get("name", "")) == q_norm:
                                            v_fy = item.get("values", {}).get(latest_fy)
                                            if v_fy is not None and "LTM" not in item["values"]:
                                                item["values"]["LTM"] = round(v_fy + v_curr_m - v_prev_m, 1)
                        except Exception as q_s_err:
                            print(f"[SEC Extractor] Aviso analizando tabla de segmentos 10-Q: {q_s_err}")
            except Exception as q_err:
                print(f"[SEC Extractor] Aviso en escaneo 10-Q de segmentos: {q_err}")

    except Exception as e:
        print(f"[SEC Extractor] Aviso escaneando XBRL de segmentos: {e}")

    # Si no se extrajeron elementos por XBRL, cargar segments_data.json preexistente si está disponible
    if not product_segments and not geographic_segments and seg_json_path.exists():
        try:
            with open(seg_json_path, "r", encoding="utf-8") as f:
                cached = json.load(f)
            product_segments = cached.get("product_segments", [])
            geographic_segments = cached.get("geographic_segments", [])
            segment_op_income = cached.get("segment_operating_income", [])
        except Exception:
            pass

    # Reconciliación de segmentos primarios sin nota 10-Q explícita (respetando Regla 6 para subsegmentos anuales)
    can_ltm_m = None
    if canonical_rev and canonical_rev.get("LTM"):
        can_ltm = canonical_rev.get("LTM")
        can_ltm_m = can_ltm / 1e6 if can_ltm > 1e6 else can_ltm

    for seg_list in [product_segments, geographic_segments]:
        for item in seg_list:
            vals = item.get("values", {})
            if "LTM" not in vals and not item.get("is_subsegment"):
                v_lat = vals.get(latest_fy)
                if v_lat is not None and can_ltm_m:
                    c_lat = canonical_rev.get(latest_fy)
                    if c_lat:
                        c_lat_m = c_lat / 1e6 if c_lat > 1e6 else c_lat
                        ratio = can_ltm_m / c_lat_m if c_lat_m > 0 else 1.0
                        vals["LTM"] = round(v_lat * ratio, 1)

    # Construir y persistir segments_data.json
    seg_dict = {
        "periods": all_fys,
        "product_segments": product_segments,
        "geographic_segments": geographic_segments,
        "segment_operating_income": segment_op_income,
        "extraction_method": "SEC_EDGAR_XBRL_ASC280_ASC606",
        "ticker": ticker_str
    }

    try:
        with open(seg_json_path, "w", encoding="utf-8") as f:
            json.dump(seg_dict, f, indent=2, ensure_ascii=False)
        print(f"[SEC Extractor] segments_data.json generado dinámicamente y guardado: {seg_json_path}")
    except Exception as w_err:
        print(f"[SEC Extractor] Error guardando segments_data.json: {w_err}")

    # Generar DataFrame para retorno
    rows = []
    for p in product_segments:
        r = {"concept": "RevenueByProduct", "dimension_member_label": p.get("name"), "label": p.get("name")}
        r.update(p.get("values", {}))
        rows.append(r)
    for g in geographic_segments:
        r = {"concept": "RevenueByRegion", "dimension_member_label": g.get("name"), "label": g.get("name")}
        r.update(g.get("values", {}))
        rows.append(r)

    return pd.DataFrame(rows) if rows else None


def build_10yr_segment_df(company, all_fys, latest_10q_inc=None, output_dir=None, canonical_rev=None):
    """Enlace retrocompatible para extracción de segmentos."""
    return build_and_save_segments_data(company, all_fys, output_dir=output_dir, canonical_rev=canonical_rev, latest_10q_inc=latest_10q_inc)


def detect_global_doc_scale(html_content):
    """
    Nivel 2: Salvaguarda Global del Documento.
    Detecta si los estados financieros declaran a nivel general que las cifras
    están expresadas en miles ('in thousands of u.s. dollars') o millones.
    """
    if not html_content:
        return 1.0
    doc_sample = str(html_content)[:150000].lower()
    clean_sample = re.sub(r'\s+', ' ', doc_sample)
    
    millions_patterns = [
        "in millions of u.s. dollars", "(in millions of u.s. dollars",
        "in millions of us dollars", "(in millions of us dollars",
        "in millions of dollars", "(in millions of dollars",
        "amounts in millions", "(in millions)", "stated in millions"
    ]
    thousands_patterns = [
        "in thousands of u.s. dollars", "(in thousands of u.s. dollars",
        "in thousands of us dollars", "(in thousands of us dollars",
        "in thousands of dollars", "(in thousands of dollars",
        "amounts in thousands", "(in thousands)", "stated in thousands"
    ]
    
    for m in millions_patterns:
        if m in clean_sample:
            return 1_000_000.0
    for t in thousands_patterns:
        if t in clean_sample:
            return 1_000.0
            
    return 1.0


def get_preceding_html_context(html_content, table, window_size=2500):
    """
    Nivel 1: Contexto Precedente a Cada Tabla.
    Extrae el bloque de texto HTML (hasta window_size caracteres) inmediatamente anterior
    a la apertura de la etiqueta <table> correspondiente a la tabla dada.
    """
    if not html_content or table is None:
        return ""
    try:
        lower_html = html_content.lower()
        for r_idx in range(min(6, len(table))):
            for c_idx in range(min(3, table.shape[1])):
                cell_val = str(table.iloc[r_idx, c_idx]).strip()
                if len(cell_val) >= 5 and cell_val.lower() not in ['none', 'nan', 'null', 'total', 'assets', 'equity', 'period', 'three', 'six', 'nine']:
                    pos = lower_html.find(cell_val.lower())
                    if pos != -1:
                        tbl_tag_pos = lower_html.rfind('<table', max(0, pos - 6000), pos)
                        target_pos = tbl_tag_pos if tbl_tag_pos != -1 else pos
                        start_pos = max(0, target_pos - window_size)
                        return html_content[start_pos:target_pos]
    except Exception:
        pass
    return ""


def detect_table_scale_factor(table, doc_context="", preceding_html=""):
    """
    Detecta dinámicamente si los números en una tabla de reporte financiero (ej. 6-K HTML)
    están expresados en miles ('in thousands'), millones ('in millions') o unidades directas/base.
    Prioriza el contexto HTML inmediatamente precedente a la apertura de la tabla.
    """
    sample_text = ""
    if preceding_html:
        sample_text += " " + str(preceding_html).lower()
    if table is not None:
        try:
            sample_text += ' ' + ' '.join(table.iloc[:5, :].astype(str).values.flatten()).lower()
        except Exception:
            pass
    if doc_context:
        sample_text += " " + str(doc_context)[:25000].lower()
        
    clean_sample = re.sub(r'\s+', ' ', sample_text)
    
    if any(k in clean_sample for k in [
        "in millions", "in million", "$ in millions", "$ in million",
        "(in millions", "(in million", "stated in millions", "amounts in millions"
    ]):
        return 1_000_000.0
    elif any(k in clean_sample for k in [
        "in thousands", "in thousand", "$ in thousands", "$ in thousand",
        "(in thousands", "(in thousand", "stated in thousands", "amounts in thousands"
    ]):
        return 1_000.0
    elif any(k in clean_sample for k in [
        "in billions", "in billion", "(in billions"
    ]):
        return 1_000_000_000.0
        
    return 1.0


def extract_6k_fpi_interim(company, annual_fys, latest_fy, inc_df, bal_df, cf_df=None):
    """
    Parsea los estados financieros interinos de Form 6-K para Foreign Private Issuers
    y calcula el período LTM acumulado mediante la identidad móvil:
    LTM = FY_latest - Interino_prev + Interino_curr
    """
    try:
        import io, re
        f_list = company.get_filings(form='6-K')
        cand_filings = [f for f in f_list if any(k in str(getattr(f, 'primary_document', '')).lower() for k in ['nufs', 'financial', 'statement', 'interim'])]
        if not cand_filings:
            cand_filings = f_list[:8]

        def _clean_val(v):
            if pd.isna(v): return None
            s = str(v).replace('$', '').replace(',', '').replace(' ', '').replace('(', '-').replace(')', '').strip()
            try: return float(s)
            except: return None

        def clean_txt(s):
            s = re.sub(r'[^a-zA-Z0-9\s]', ' ', str(s).lower())
            s = re.sub(r'\s+', ' ', s).strip()
            return s

        for filing in cand_filings:
            try:
                html_content = filing.html()
                if not html_content or len(html_content) < 50000:
                    continue
                tables = pd.read_html(io.StringIO(html_content))
                is_tbl, bs_a_tbl, bs_l_tbl = None, None, None
                cf_o_tbl, cf_i_tbl, cf_f_tbl = None, None, None
                for t in tables[:35]:
                    t_str = re.sub(r'\s+', ' ', ' '.join(t.astype(str).values.flatten()).lower())
                    if 'fee and commission income' in t_str and 'gross profit' in t_str and is_tbl is None:
                        is_tbl = t
                    if 'cash and cash equivalents' in t_str and 'total assets' in t_str and bs_a_tbl is None:
                        bs_a_tbl = t
                    if 'deposits' in t_str and 'total liabilities and equity' in t_str and bs_l_tbl is None:
                        bs_l_tbl = t
                    if 'cash flows from operating activities' in t_str and cf_o_tbl is None:
                        cf_o_tbl = t
                    if ('cash flows in investing activities' in t_str or 'investing activities' in t_str) and cf_i_tbl is None:
                        cf_i_tbl = t
                    if ('cash flows from financing activities' in t_str or 'financing activities' in t_str) and cf_f_tbl is None:
                        cf_f_tbl = t

                if is_tbl is not None and bs_a_tbl is not None and bs_l_tbl is not None:
                    # Nivel 2: Detección global de escala
                    doc_scale = detect_global_doc_scale(html_content)

                    # Nivel 1: Detección local en contexto precedente a cada tabla
                    is_pre = get_preceding_html_context(html_content, is_tbl)
                    bs_pre = get_preceding_html_context(html_content, bs_a_tbl)
                    cf_tbl_ref = cf_o_tbl if cf_o_tbl is not None else (cf_i_tbl if cf_i_tbl is not None else cf_f_tbl)
                    cf_pre = get_preceding_html_context(html_content, cf_tbl_ref)

                    is_scale = detect_table_scale_factor(is_tbl, doc_context="", preceding_html=is_pre)
                    bs_scale = detect_table_scale_factor(bs_a_tbl, doc_context="", preceding_html=bs_pre)
                    cf_scale = detect_table_scale_factor(cf_tbl_ref, doc_context="", preceding_html=cf_pre)

                    # Si la escala local dio 1.0, aplicar salvaguarda global del documento
                    if is_scale == 1.0 and doc_scale > 1.0:
                        is_scale = doc_scale
                    if bs_scale == 1.0 and doc_scale > 1.0:
                        bs_scale = doc_scale
                    if cf_scale == 1.0 and doc_scale > 1.0:
                        cf_scale = doc_scale

                    print(f"[SEC Extractor] Escalas 6-K detectadas: IS={is_scale}, BS={bs_scale}, CF={cf_scale} (Doc Global={doc_scale})")

                    # Encontrar dinámicamente los años reportados en las cabeceras
                    all_years_is = []
                    for c_idx in range(is_tbl.shape[1]):
                        hdr_text = ' '.join(is_tbl.iloc[:4, c_idx].astype(str).tolist())
                        yrs = [int(y) for y in re.findall(r'\b(20\d\d)\b', hdr_text)]
                        all_years_is.extend(yrs)
                    
                    if all_years_is:
                        curr_yr = max(all_years_is)
                        prev_yr = curr_yr - 1
                    else:
                        curr_yr = datetime.now().year
                        prev_yr = curr_yr - 1

                    # Priorizar período acumulado YTD (nueve meses > seis meses > tres meses)
                    col_curr_is, col_prev_is = None, None
                    for dur_kw in ['nine', '9', 'six', '6', 'three', '3']:
                        c_curr, c_prev = None, None
                        for c_idx in range(is_tbl.shape[1]):
                            col_hdr = ' '.join(is_tbl.iloc[:4, c_idx].astype(str).tolist()).lower()
                            if dur_kw in col_hdr:
                                if str(curr_yr) in col_hdr and c_curr is None:
                                    c_curr = c_idx
                                elif str(prev_yr) in col_hdr and c_prev is None:
                                    c_prev = c_idx
                        if c_curr is not None and c_prev is not None:
                            col_curr_is, col_prev_is = c_curr, c_prev
                            break

                    if col_curr_is is None:
                        for c_idx in range(is_tbl.shape[1]):
                            col_hdr = ' '.join(is_tbl.iloc[:4, c_idx].astype(str).tolist()).lower()
                            if str(curr_yr) in col_hdr and col_curr_is is None:
                                col_curr_is = c_idx
                            elif str(prev_yr) in col_hdr and col_prev_is is None:
                                col_prev_is = c_idx

                    if col_curr_is is None:
                        col_curr_is = 7 if is_tbl.shape[1] > 7 else 3
                        col_prev_is = 9 if is_tbl.shape[1] > 9 else (col_curr_is + 1 if is_tbl.shape[1] > col_curr_is + 1 else None)

                    interim_is = []
                    for _, r in is_tbl.iterrows():
                        lbl = clean_txt(r[0])
                        vc = _clean_val(r[col_curr_is])
                        vp = _clean_val(r[col_prev_is]) if col_prev_is is not None else None
                        if vc is not None:
                            interim_is.append((lbl, vc * is_scale, (vp * is_scale) if vp is not None else 0.0))

                    def find_is_match(c_name, l_name):
                        c_clean = clean_txt(c_name)
                        l_clean = clean_txt(l_name)
                        for lbl, vc, vp in interim_is:
                            if l_clean == lbl:
                                return lbl, vc, vp
                        if 'incometax' in c_clean and 'before' not in c_clean and 'before' not in l_clean:
                            for lbl, vc, vp in interim_is:
                                if lbl == 'income taxes': return lbl, vc, vp
                        if 'interest' in c_clean and 'expense' in c_clean:
                            for lbl, vc, vp in interim_is:
                                if 'interest' in lbl and 'expense' in lbl:
                                    return lbl, vc, vp
                        if 'profitlossbeforetax' in c_clean or 'before income taxes' in l_clean:
                            for lbl, vc, vp in interim_is:
                                if 'before income taxes' in lbl: return lbl, vc, vp
                        if ('netincome' in c_clean or 'profitloss' in c_clean) and 'attributable' not in c_clean and 'noncontrolling' not in c_clean:
                            if 'period' in l_clean or 'year' in l_clean or l_clean == 'net income':
                                for lbl, vc, vp in interim_is:
                                    if 'net income for the period' in lbl: return lbl, vc, vp
                        if 'adjustedaverageweightedshares' in c_clean or ('diluted' in l_clean and 'share' in l_clean):
                            for lbl, vc, vp in interim_is:
                                if 'weighted average' in lbl and vc > 4.9e9: return lbl, vc, vp
                        if 'weightedaverageshares' in c_clean and 'adjusted' not in c_clean and 'basic' in l_clean:
                            for lbl, vc, vp in interim_is:
                                if 'weighted average' in lbl and vc < 4.9e9: return lbl, vc, vp
                        for lbl, vc, vp in interim_is:
                            if len(lbl) > 8 and (lbl in l_clean or l_clean in lbl):
                                return lbl, vc, vp
                        return None, None, None

                    # Población de LTM en inc_df
                    if 'LTM' not in inc_df.columns and latest_fy in inc_df.columns:
                        ltm_col = []
                        for _, row in inc_df.iterrows():
                            concept = str(row.get('concept', ''))
                            label = str(row.get('label', ''))
                            fy_val = row.get(latest_fy)
                            val = None
                            
                            m_lbl, vc, vp = find_is_match(concept, label)
                            if m_lbl and pd.notna(fy_val):
                                if 'earnings per share' in m_lbl or 'pershare' in concept.lower():
                                    val = float(fy_val)
                                elif 'weighted average' in m_lbl or 'shares' in concept.lower():
                                    val = vc
                                else:
                                    val = float(fy_val) - vp + vc
                            elif pd.notna(fy_val):
                                val = float(fy_val)
                            ltm_col.append(val)
                        inc_df.insert(inc_df.columns.get_loc(latest_fy), 'LTM', ltm_col)

                    # Población de LTM en bal_df
                    interim_bs = []
                    for b_tbl in [bs_a_tbl, bs_l_tbl]:
                        col_bs_date = None
                        for c_idx in range(b_tbl.shape[1]):
                            hdr_txt = ' '.join(b_tbl.iloc[:3, c_idx].astype(str).tolist()).lower()
                            if str(curr_yr) in hdr_txt:
                                col_bs_date = c_idx
                                break
                        if col_bs_date is None:
                            col_bs_date = 3 if b_tbl.shape[1] > 3 else (1 if b_tbl.shape[1] > 1 else 0)
                        for _, r in b_tbl.iterrows():
                            lbl = clean_txt(r[0])
                            v = _clean_val(r[col_bs_date])
                            if v is not None:
                                interim_bs.append((lbl, v * bs_scale))

                    # Nivel 3: Calibración Triangulada de Sanidad Contable (Cross-Period Ratio Validation)
                    fy_assets = None
                    for _, r in bal_df.iterrows():
                        c_cn = str(r.get('concept', '')).lower()
                        l_lb = str(r.get('label', '')).lower()
                        if 'abstract' in c_cn:
                            continue
                        if c_cn.endswith('assets') or l_lb in ['assets', 'total assets']:
                            val = r.get(latest_fy)
                            if pd.notna(val) and float(val) > 0:
                                fy_assets = float(val)
                                break
                    interim_assets = None
                    for lbl, v in interim_bs:
                        if lbl in ['total assets', 'assets'] and v is not None and v > 0:
                            interim_assets = float(v)
                            break

                    calib_factor = 1.0
                    if fy_assets and interim_assets:
                        ratio = fy_assets / interim_assets
                        if 700.0 <= ratio <= 1300.0:
                            calib_factor = 1000.0
                        elif 700_000.0 <= ratio <= 1_300_000.0:
                            calib_factor = 1_000_000.0

                        if calib_factor > 1.0:
                            print(f"[SEC Extractor] Calibración de escala 6-K aplicada (ratio FY_latest/interino = {ratio:.1f}): multiplicando balance interino por {calib_factor:.0f}x")
                            interim_bs = [(lbl, v * calib_factor) for lbl, v in interim_bs]
                            if cf_scale < calib_factor:
                                cf_scale = calib_factor

                    def find_bs_match(c_name, l_name):
                        if 'abstract' in c_name.lower():
                            return None, None
                        c_clean = clean_txt(c_name)
                        l_clean = clean_txt(l_name)
                        for lbl, v in interim_bs:
                            if l_clean == lbl:
                                return lbl, v
                        if 'cash' in c_clean and 'cash' in l_clean and 'central' not in l_clean:
                            for lbl, v in interim_bs:
                                if lbl == 'cash and cash equivalents': return lbl, v
                        if 'central' in c_clean or 'central' in l_clean:
                            for lbl, v in interim_bs:
                                if 'central' in lbl: return lbl, v
                        if 'creditcard' in c_clean or 'credit card' in l_clean:
                            for lbl, v in interim_bs:
                                if 'credit card' in lbl: return lbl, v
                        if 'loansandadvances' in c_clean or 'loans to customers' in l_clean:
                            for lbl, v in interim_bs:
                                if 'loans to customers' in lbl: return lbl, v
                        if 'depositsfromcustomers' in c_clean or l_clean == 'deposits':
                            for lbl, v in interim_bs:
                                if lbl == 'deposits': return lbl, v
                        if 'borrowings' in c_clean or 'borrowing' in l_clean:
                            for lbl, v in interim_bs:
                                if 'borrowing' in lbl: return lbl, v
                        if 'repurchase' in c_clean or 'repurchase' in l_clean:
                            for lbl, v in interim_bs:
                                if 'repurchase' in lbl: return lbl, v
                        if c_clean.endswith('assets') or l_clean in ['assets', 'total assets']:
                            for lbl, v in interim_bs:
                                if lbl == 'total assets': return lbl, v
                        if 'total' in l_clean and 'equity' in l_clean:
                            for lbl, v in interim_bs:
                                if lbl == 'total equity': return lbl, v
                        for lbl, v in interim_bs:
                            if len(lbl) > 8 and (lbl in l_clean or l_clean in lbl):
                                return lbl, v
                        return None, None

                    if 'LTM' not in bal_df.columns and latest_fy in bal_df.columns:
                        ltm_bal_col = []
                        for _, row in bal_df.iterrows():
                            concept = str(row.get('concept', ''))
                            label = str(row.get('label', ''))
                            fy_val = row.get(latest_fy)
                            val = None
                            m_lbl, v_match = find_bs_match(concept, label)
                            if m_lbl:
                                val = v_match
                            elif pd.notna(fy_val):
                                val = float(fy_val)
                            ltm_bal_col.append(val)
                        bal_df.insert(bal_df.columns.get_loc(latest_fy), 'LTM', ltm_bal_col)

                    # Población de LTM en cf_df
                    if cf_df is not None and 'LTM' not in cf_df.columns and latest_fy in cf_df.columns:
                        cfo_ltm, capex_ltm = None, None
                        
                        col_curr_cf, col_prev_cf = None, None
                        active_cf_tbl = cf_o_tbl if cf_o_tbl is not None else cf_i_tbl
                        if active_cf_tbl is not None:
                            for dur_kw in ['nine', '9', 'six', '6', 'three', '3']:
                                c_curr, c_prev = None, None
                                for c_idx in range(active_cf_tbl.shape[1]):
                                    hdr = ' '.join(active_cf_tbl.iloc[:4, c_idx].astype(str).tolist()).lower()
                                    if dur_kw in hdr:
                                        if str(curr_yr) in hdr and c_curr is None: c_curr = c_idx
                                        elif str(prev_yr) in hdr and c_prev is None: c_prev = c_idx
                                if c_curr is not None and c_prev is not None:
                                    col_curr_cf, col_prev_cf = c_curr, c_prev
                                    break
                            if col_curr_cf is None:
                                for c_idx in range(active_cf_tbl.shape[1]):
                                    hdr = ' '.join(active_cf_tbl.iloc[:4, c_idx].astype(str).tolist()).lower()
                                    if str(curr_yr) in hdr and col_curr_cf is None: col_curr_cf = c_idx
                                    elif str(prev_yr) in hdr and col_prev_cf is None: col_prev_cf = c_idx
                        if col_curr_cf is None:
                            col_curr_cf = 3 if (active_cf_tbl is not None and active_cf_tbl.shape[1] > 3) else 1
                            col_prev_cf = 5 if (active_cf_tbl is not None and active_cf_tbl.shape[1] > 5) else (col_curr_cf + 1 if active_cf_tbl is not None and active_cf_tbl.shape[1] > col_curr_cf + 1 else None)

                        if cf_o_tbl is not None:
                            for _, r in cf_o_tbl.iterrows():
                                r_lbl = clean_txt(r[0])
                                if 'cash flows generated from' in r_lbl or 'used in operating activities' in r_lbl:
                                    vc = _clean_val(r[col_curr_cf])
                                    vp = _clean_val(r[col_prev_cf]) if col_prev_cf is not None else None
                                    if vc is not None and vp is not None:
                                        fy_cfo = None
                                        for _, cr in cf_df.iterrows():
                                            c_cn = str(cr.get('concept', '')).lower()
                                            if 'abstract' in c_cn:
                                                continue
                                            if 'operatingactivities' in c_cn or 'cashflowsfromusedinoperatingactivities' in c_cn:
                                                val_chk = cr.get(latest_fy)
                                                if pd.notna(val_chk):
                                                    fy_cfo = val_chk
                                                    break
                                        if pd.notna(fy_cfo):
                                            cfo_ltm = float(fy_cfo) - (vp * cf_scale) + (vc * cf_scale)
                        if cf_i_tbl is not None:
                            capex_c, capex_p = 0.0, 0.0
                            for _, r in cf_i_tbl.iterrows():
                                r_lbl = clean_txt(r[0])
                                if any(k in r_lbl for k in ['acquisition of property', 'purchase of property', 'acquisition and development of intangible', 'additions to property']):
                                    vc = _clean_val(r[col_curr_cf])
                                    vp = _clean_val(r[col_prev_cf]) if col_prev_cf is not None else None
                                    if vc is not None: capex_c += abs(vc * cf_scale)
                                    if vp is not None: capex_p += abs(vp * cf_scale)
                            fy_capex = 0.0
                            for _, cr in cf_df.iterrows():
                                c_cn = str(cr.get('concept', '')).lower()
                                if 'abstract' in c_cn:
                                    continue
                                if any(k in c_cn for k in ['intangibleassets', 'productiveassets', 'propertyplantandequipment', 'propertyplantequipment']):
                                    val_chk = cr.get(latest_fy)
                                    if pd.notna(val_chk):
                                        fy_capex += abs(float(val_chk))
                            if fy_capex > 0:
                                capex_ltm = fy_capex - capex_p + capex_c

                        # Parser de recompras de acciones en tabla de financiación 6-K (cf_f_tbl)
                        rep_ltm = None
                        if cf_f_tbl is not None:
                            rep_c, rep_p = None, None
                            for _, r in cf_f_tbl.iterrows():
                                r_lbl = clean_txt(r[0])
                                if any(k in r_lbl for k in ['share repurchase', 'repurchase of common stock', 'purchase of treasury shares', 'nu_sharesrepurchased', 'purchase of own shares', 'repurchase of shares']):
                                    vc = _clean_val(r[col_curr_cf])
                                    vp = _clean_val(r[col_prev_cf]) if col_prev_cf is not None else None
                                    if vc is not None:
                                        rep_c = abs(vc * cf_scale)
                                    if vp is not None:
                                        rep_p = abs(vp * cf_scale)
                                    break

                            if rep_c is not None:
                                # Buscar si el concepto tenía valor en latest_fy
                                fy_rep = None
                                for _, cr in cf_df.iterrows():
                                    c_cn = str(cr.get('concept', '')).lower()
                                    if 'abstract' in c_cn:
                                        continue
                                    if any(k in c_cn for k in ['sharesrepurchased', 'paymentsforpurchaseofownshares', 'repurchaseofcommonstock', 'purchaseoftreasuryshares', 'paymentstorepurchasecommonstock']):
                                        val_chk = cr.get(latest_fy)
                                        if pd.notna(val_chk) and float(val_chk) != 0.0:
                                            fy_rep = abs(float(val_chk))
                                        break

                                # Cálculo dinámico de LTM para recompras sin año base:
                                # Si el concepto tenía valor nulo o cero en latest_fy, asignar directamente el valor interino actual
                                if fy_rep is not None and fy_rep > 0:
                                    rep_ltm = fy_rep - (rep_p or 0.0) + rep_c
                                else:
                                    rep_ltm = rep_c

                        ltm_cf_col = []
                        rep_matched_in_cf = False
                        for _, row in cf_df.iterrows():
                            c_name = str(row.get('concept', '')).lower()
                            fy_val = row.get(latest_fy)
                            val = None
                            if 'abstract' in c_name:
                                val = None
                            elif ('operatingactivities' in c_name or 'cashflowsfromusedinoperatingactivities' in c_name) and cfo_ltm is not None:
                                val = cfo_ltm
                            elif any(k in c_name for k in ['intangibleassets', 'productiveassets', 'propertyplantandequipment', 'propertyplantequipment']) and capex_ltm is not None:
                                val = capex_ltm
                            elif any(k in c_name for k in ['sharesrepurchased', 'paymentsforpurchaseofownshares', 'repurchaseofcommonstock', 'purchaseoftreasuryshares', 'paymentstorepurchasecommonstock']) and rep_ltm is not None:
                                val = rep_ltm
                                rep_matched_in_cf = True
                            elif pd.notna(fy_val):
                                val = float(fy_val)
                            ltm_cf_col.append(val)
                        cf_df.insert(cf_df.columns.get_loc(latest_fy), 'LTM', ltm_cf_col)

                        # Incorporar la fila extraída a cf_df si no existía el concepto para que se exporte a cash_flow_detail
                        if rep_ltm is not None and not rep_matched_in_cf:
                            prefix = str(cf_df['concept'].iloc[0]).split('_')[0] if (len(cf_df) > 0 and '_' in str(cf_df['concept'].iloc[0])) else None
                            cand_concept = f"{prefix}_SharesRepurchased" if prefix else 'PaymentsForPurchaseOfOwnShares'
                            new_row = {col: None for col in cf_df.columns}
                            new_row['concept'] = cand_concept
                            new_row['label'] = 'Repurchase of shares'
                            new_row['standard_concept'] = 'PaymentsForPurchaseOfOwnShares'
                            new_row['LTM'] = rep_ltm
                            cf_df.loc[len(cf_df)] = new_row

                    print(f"[SEC Extractor] Parser 6-K exitoso: {filing.primary_document} incorporado a LTM con estados IS, BS y CF.")
                    return True
            except Exception as e:
                continue
    except Exception as e:
        print(f"[SEC Extractor] Nota en parser 6-K: {e}")
    return False

def convert_xb_statement_to_df(stmt_rows):
    """Convierte la lista de diccionarios de un rol XBRL en DataFrame con columnas FYxxxx."""
    data = []
    for r in stmt_rows:
        row_dict = {
            'concept': str(r.get('concept', '')).strip(),
            'label': str(r.get('label', '')).strip()
        }
        vals = r.get('values', {})
        if isinstance(vals, dict):
            for p_k, v in vals.items():
                m = re.search(r'(\d{4})', str(p_k))
                if m and v != '' and pd.notna(v):
                    try:
                        row_dict[f"FY{m.group(1)}"] = float(v)
                    except (ValueError, TypeError):
                        pass
        data.append(row_dict)
    return pd.DataFrame(data)


def merge_annual_statement_df(source_df, target_df, annual_fys, updated_cells=None, overwrite_if_newer=False):
    """
    Fusiona conceptos y valores de source_df en target_df.
    Aplica Latest Filed Priority: si overwrite_if_newer=True o si se suministra updated_cells,
    los reportes anuales más recientes tienen precedencia y actualizan reexpresiones / reformulaciones
    de ejercicios comparativos (ej. FY2023 restated en FY2024/FY2025).
    """
    if source_df is None or source_df.empty:
        return
    if updated_cells is None:
        updated_cells = set()

    for _, s_row in source_df.iterrows():
        c_concept = str(s_row.get('concept', '')).strip()
        if not c_concept or c_concept == 'nan':
            continue
        c_token = c_concept.split(':')[-1].split('_')[-1].lower()
        
        match_idx = -1
        for t_idx, t_row in target_df.iterrows():
            t_concept = str(t_row.get('concept', '')).strip()
            t_token = t_concept.split(':')[-1].split('_')[-1].lower()
            if t_token == c_token:
                match_idx = t_idx
                break
                
        if match_idx >= 0:
            for fy in annual_fys:
                if fy in source_df.columns and fy in target_df.columns:
                    sv = s_row.get(fy)
                    cell_key = (c_token, fy)
                    if pd.notna(sv) and sv != '':
                        try:
                            f_sv = float(sv)
                            tv = target_df.at[match_idx, fy]
                            if overwrite_if_newer:
                                if cell_key not in updated_cells:
                                    target_df.at[match_idx, fy] = f_sv
                                    updated_cells.add(cell_key)
                            else:
                                if (tv is None or pd.isna(tv)) and cell_key not in updated_cells:
                                    target_df.at[match_idx, fy] = f_sv
                                    updated_cells.add(cell_key)
                        except (ValueError, TypeError):
                            pass
        else:
            new_row_dict = {"concept": c_concept, "label": str(s_row.get('label', c_concept))}
            has_any = False
            for fy in annual_fys:
                if fy in source_df.columns:
                    val = s_row.get(fy)
                    if pd.notna(val) and val != '':
                        try:
                            f_val = float(val)
                            new_row_dict[fy] = f_val
                            has_any = True
                            if overwrite_if_newer:
                                updated_cells.add((c_token, fy))
                        except (ValueError, TypeError):
                            new_row_dict[fy] = None
                    else:
                        new_row_dict[fy] = None
                else:
                    new_row_dict[fy] = None
            if has_any:
                target_df.loc[len(target_df)] = new_row_dict


def build_as_reported_statements(
    company,
    annual_fys,
    latest_fy,
    inc_df,
    bal_df,
    cf_df,
    latest_10k_obj=None,
    latest_10q_obj=None,
    q_inc=None,
    q_bal=None,
    q_cf=None,
    facts_df=None
):
    """
    Construye los tres estados financieros principales bajo formato As-Reported (Filing Presentation fiel a la SEC).
    Preserva jerarquía, líneas oficiales, notas anuales y reconciliación de 10 años + LTM mediante emparejamiento de 3 niveles.
    """
    def _clean_concept_token(c):
        if not c or pd.isna(c):
            return ""
        s = str(c).strip()
        if ":" in s:
            s = s.split(":")[-1]
        if "_" in s:
            s = s.split("_")[-1]
        return s.lower()

    all_tax_maps = [XBRL_TAXONOMY_MAP, BANKING_TAXONOMY_MAP, REIT_TAXONOMY_MAP, INSURANCE_TAXONOMY_MAP, PLATFORM_TAXONOMY_MAP]

    as_reported = {}
    
    statements_meta = [
        ("income_statement", "income_statement", "income_statement", inc_df, True),
        ("balance_sheet", "balance_sheet", "balance_sheet", bal_df, False),
        ("cash_flow_statement", "cash_flow_statement", "cash_flow_statement", cf_df, True)
    ]
    
    for s_name, k_attr, q_attr, hist_df, is_flow in statements_meta:
        k_stmt = None
        if latest_10k_obj:
            k_stmt = getattr(latest_10k_obj, k_attr, None)
            if not k_stmt and hasattr(latest_10k_obj, 'financials') and latest_10k_obj.financials:
                k_fn = getattr(latest_10k_obj.financials, k_attr, None)
                if k_fn:
                    k_stmt = k_fn()
        
        if not k_stmt:
            if hist_df is not None and not hist_df.empty:
                fallback_rows = []
                for _, r in hist_df.iterrows():
                    lbl = str(r.get("label", "")).strip()
                    conc = str(r.get("concept", "")).strip()
                    if not lbl and not conc:
                        continue
                    row_vals = {}
                    for p in (["LTM"] + annual_fys):
                        if p in hist_df.columns:
                            v = r.get(p)
                            row_vals[p] = float(v) if pd.notna(v) else None
                    fallback_rows.append({
                        "label": lbl or conc,
                        "clarification": get_spanish_clarification(lbl, conc),
                        "concept": conc,
                        "level": int(r.get("depth", 0)) if pd.notna(r.get("depth")) else 0,
                        "is_abstract": bool(r.get("is_abstract", False)),
                        "is_total": bool(r.get("is_total", False)),
                        "values": row_vals
                    })
                as_reported[s_name] = fallback_rows
            continue

        try:
            k_df = k_stmt.to_dataframe()
        except Exception:
            k_df = None

        if k_df is None or k_df.empty:
            continue

        # Filtrado de líneas puras de carátula (Face-only items)
        if "dimension" in k_df.columns:
            if s_name == "income_statement":
                # En Income Statement, permitir la apertura oficial de carátula Product / Service (ej. AAPL, MELI)
                is_prod_serv = k_df["dimension_member"].astype(str).str.contains(r'ProductMember|ServiceMember', case=False, na=False) if "dimension_member" in k_df.columns else False
                if not is_prod_serv.any() and "label" in k_df.columns:
                    is_prod_serv = k_df["label"].astype(str).str.strip().str.lower().isin(["products", "services"]) & (k_df["dimension"] == True)
                is_pure_face = (k_df["dimension"] == False) | k_df["dimension"].isna() | (k_df["dimension"].astype(str).isin(["", "nan", "None"]))
                face_df = k_df[is_pure_face | is_prod_serv].copy()
            else:
                is_pure_face = (k_df["dimension"] == False) | k_df["dimension"].isna() | (k_df["dimension"].astype(str).isin(["", "nan", "None"]))
                face_df = k_df[is_pure_face].copy()
        elif "is_breakdown" in k_df.columns:
            face_df = k_df[k_df["is_breakdown"] == False].copy()
        else:
            face_df = k_df.copy()

        # Obtener 10-Q correspondiente
        q_stmt = None
        if latest_10q_obj:
            q_stmt = getattr(latest_10q_obj, q_attr, None)
            if not q_stmt and hasattr(latest_10q_obj, 'financials') and latest_10q_obj.financials:
                q_fn = getattr(latest_10q_obj.financials, q_attr, None)
                if q_fn:
                    q_stmt = q_fn()

        q_df = None
        if q_stmt:
            try:
                q_df = q_stmt.to_dataframe()
            except Exception:
                q_df = None
        elif s_name == "income_statement" and q_inc is not None:
            q_df = q_inc
        elif s_name == "balance_sheet" and q_bal is not None:
            q_df = q_bal
        elif s_name == "cash_flow_statement" and q_cf is not None:
            q_df = q_cf

        if q_df is not None and not q_df.empty:
            if "dimension" in q_df.columns:
                if s_name == "income_statement":
                    is_prod_serv_q = q_df["dimension_member"].astype(str).str.contains(r'ProductMember|ServiceMember', case=False, na=False) if "dimension_member" in q_df.columns else False
                    if not is_prod_serv_q.any() and "label" in q_df.columns:
                        is_prod_serv_q = q_df["label"].astype(str).str.strip().str.lower().isin(["products", "services"]) & (q_df["dimension"] == True)
                    is_pure_q = (q_df["dimension"] == False) | q_df["dimension"].isna() | (q_df["dimension"].astype(str).isin(["", "nan", "None"]))
                    q_face = q_df[is_pure_q | is_prod_serv_q].copy()
                else:
                    is_pure_q = (q_df["dimension"] == False) | q_df["dimension"].isna() | (q_df["dimension"].astype(str).isin(["", "nan", "None"]))
                    q_face = q_df[is_pure_q].copy()
            elif "is_breakdown" in q_df.columns:
                q_face = q_df[q_df["is_breakdown"] == False].copy()
            else:
                q_face = q_df.copy()
        else:
            q_face = pd.DataFrame()

        # Mapear columnas anuales del 10-K a FYxxxx
        fy_cols_map = {}
        for c in face_df.columns:
            norm_c = normalize_fiscal_year(c)
            if norm_c.startswith("FY"):
                fy_cols_map[norm_c] = c

        # Detectar columnas relevantes en el 10-Q para LTM
        q_mrq_col = None
        ytd_curr = None
        ytd_prev = None
        q_curr = None
        if not q_face.empty:
            if not is_flow:
                mrq_cols = sorted([col for col in q_face.columns if re.match(r'^\d{4}-\d{2}-\d{2}$', str(col))], reverse=True)
                q_mrq_col = mrq_cols[0] if mrq_cols else None
            else:
                ytd_cols = [c for c in q_face.columns if 'YTD' in str(c)]
                if not ytd_cols:
                    ytd_cols = [c for c in q_face.columns if any(ch.isdigit() for ch in str(c)) and ('Q' in str(c) or '202' in str(c))]
                ytd_curr = sorted(ytd_cols, reverse=True)[0] if len(ytd_cols) >= 1 else None
                ytd_prev = sorted(ytd_cols, reverse=True)[1] if len(ytd_cols) >= 2 else None
                q_cols = [c for c in q_face.columns if re.search(r'\(Q\d\)', str(c))]
                q_curr = sorted(q_cols, reverse=True)[0] if q_cols else None

        # Preparar índices de búsqueda en hist_df
        hist_concept_toks = None
        hist_labels_clean = None
        hist_cols_norm = {}
        if hist_df is not None and not hist_df.empty:
            if "concept" in hist_df.columns:
                hist_concept_toks = hist_df["concept"].apply(_clean_concept_token)
            else:
                hist_concept_toks = pd.Series([""] * len(hist_df), index=hist_df.index)
            if "label" in hist_df.columns:
                hist_labels_clean = hist_df["label"].astype(str).apply(lambda x: re.sub(r'[^a-zA-Z0-9]', '', x.lower()))
            else:
                hist_labels_clean = pd.Series([""] * len(hist_df), index=hist_df.index)
            for col_h in hist_df.columns:
                norm_h = normalize_fiscal_year(col_h)
                if norm_h.startswith("FY") or norm_h == "LTM":
                    hist_cols_norm[norm_h] = col_h

        rows = []
        seen_cash_flow_ending_cash = False
        for _, r in face_df.iterrows():
            lbl = str(r.get("label", "")).strip()
            conc = str(r.get("concept", "")).strip()
            is_abs = bool(r.get("abstract", False))
            lvl = int(r.get("level", 0)) if pd.notna(r.get("level")) else 0
            is_tot = ("total" in lbl.lower()) or bool(r.get("is_total", False))
            conc_tok = _clean_concept_token(conc)

            # Limpiar etiquetas excesivamente extensas (par value, shares authorized)
            clean_lbl = lbl
            clean_detail = None
            if ";" in lbl and len(lbl) > 50:
                parts = [p.strip() for p in lbl.split(";") if p.strip()]
                clean_lbl = parts[0]
                clean_detail = "; ".join(parts[1:])
            elif "(" in lbl and ")" in lbl and len(lbl) > 80:
                m_par = re.search(r'\(([^)]+)\)', lbl)
                if m_par and len(m_par.group(1)) > 30 and any(w in m_par.group(1).lower() for w in ["share", "par value", "note", "class"]):
                    clean_detail = m_par.group(1)
                    clean_lbl = re.sub(r'\s*\([^)]+\)', '', lbl).strip()

            base_clarif = get_spanish_clarification(clean_lbl, conc)
            if clean_detail:
                clarif = f"{base_clarif} · {clean_detail}" if base_clarif else clean_detail
            else:
                clarif = base_clarif

            # En Flujo de Efectivo, evitar duplicados del saldo final de caja
            is_cf_cash = (s_name == "cash_flow_statement") and ("cash" in conc_tok and "equivalents" in conc_tok)
            if is_cf_cash:
                if "beginning" in clean_lbl.lower() or "start" in clean_lbl.lower():
                    clean_lbl = "Cash, cash equivalents and restricted cash, beginning of period"
                elif seen_cash_flow_ending_cash:
                    continue
                else:
                    seen_cash_flow_ending_cash = True

            # Reconciliación Histórica de 3 Niveles en hist_df
            matched_h_row = None
            if hist_df is not None and not hist_df.empty:
                # Nivel 1: Coincidencia por token de concepto (sin prefijo us-gaap_)
                if conc_tok:
                    m1 = hist_df[hist_concept_toks == conc_tok]
                    if len(m1) == 1:
                        matched_h_row = m1.iloc[0]
                    elif len(m1) > 1:
                        lbl_clean_val = re.sub(r'[^a-zA-Z0-9]', '', clean_lbl.lower())
                        m1_lbl = m1[hist_labels_clean.loc[m1.index] == lbl_clean_val]
                        matched_h_row = m1_lbl.iloc[0] if not m1_lbl.empty else m1.iloc[0]

                # Nivel 2: Coincidencia por nombre de cuenta en carátula limpia
                if matched_h_row is None and clean_lbl:
                    lbl_clean_val = re.sub(r'[^a-zA-Z0-9]', '', clean_lbl.lower())
                    if lbl_clean_val:
                        m2 = hist_df[hist_labels_clean == lbl_clean_val]
                        if not m2.empty:
                            matched_h_row = m2.iloc[0]

                # Nivel 3: Grupo sinónimo de taxonomía canónica
                if matched_h_row is None and conc_tok:
                    for tmap in all_tax_maps:
                        for syn_group, cands in tmap.items():
                            tok_cands = [_clean_concept_token(c_item) for c_item in cands]
                            if conc_tok in tok_cands:
                                m3 = hist_df[hist_concept_toks.isin(tok_cands)]
                                if not m3.empty:
                                    matched_h_row = m3.iloc[0]
                                    break
                        if matched_h_row is not None:
                            break

            # Extracción de importes anuales
            row_vals = {}
            for p in annual_fys:
                val = None
                # 1. Filing actual 10-K
                if p in fy_cols_map:
                    v_raw = r.get(fy_cols_map[p])
                    if pd.notna(v_raw):
                        try:
                            val = float(v_raw)
                        except (ValueError, TypeError):
                            val = None
                # 2. Histórico 10 años (hist_df)
                if val is None and matched_h_row is not None:
                    h_col = hist_cols_norm.get(p)
                    if h_col:
                        v_h = matched_h_row.get(h_col)
                        if pd.notna(v_h):
                            try:
                                val = float(v_h)
                            except (ValueError, TypeError):
                                val = None
                # 3. Respaldo por grupo sinónimo para año específico
                if val is None and conc_tok and hist_df is not None and not hist_df.empty:
                    for tmap in all_tax_maps:
                        for syn_group, cands in tmap.items():
                            tok_cands = [_clean_concept_token(c_item) for c_item in cands]
                            if conc_tok in tok_cands:
                                syn_matches = hist_df[hist_concept_toks.isin(tok_cands)]
                                h_col = hist_cols_norm.get(p)
                                if h_col and not syn_matches.empty:
                                    for _, syn_r in syn_matches.iterrows():
                                        v_syn = syn_r.get(h_col)
                                        if pd.notna(v_syn):
                                            try:
                                                val = float(v_syn)
                                                break
                                            except (ValueError, TypeError):
                                                pass
                                if val is not None:
                                    break
                        if val is not None:
                            break

                row_vals[p] = val

            # Cálculo de LTM bajo integridad temporal
            if is_abs:
                row_vals["LTM"] = None
            else:
                ltm_val = None
                # 1. Para Balance Sheet (point-in-time), consultar el 10-Q trimestral oficial al cierre de MRQ
                if not is_flow and not q_face.empty and q_mrq_col:
                    q_toks = q_face["concept"].astype(str).apply(_clean_concept_token)
                    q_match = q_face[(q_toks == conc_tok) & (q_face["label"].astype(str).str.strip().str.lower() == clean_lbl.lower())]
                    if q_match.empty:
                        q_match = q_face[q_toks == conc_tok]
                    if not q_match.empty:
                        v_q = q_match.iloc[0].get(q_mrq_col)
                        if pd.notna(v_q):
                            try:
                                ltm_val = float(v_q)
                            except (ValueError, TypeError):
                                pass

                # 2. Consultar LTM calibrado en hist_df (4Q sum EPS, flujo acumulado TTM)
                if ltm_val is None and matched_h_row is not None and "LTM" in hist_cols_norm:
                    cand_ltm = matched_h_row.get(hist_cols_norm["LTM"])
                    if pd.notna(cand_ltm):
                        try:
                            ltm_val = float(cand_ltm)
                        except (ValueError, TypeError):
                            ltm_val = None

                # 3. Respaldo de flujo (YTD delta) si no figuraba en hist_df
                if ltm_val is None and is_flow and not q_face.empty:
                    q_toks = q_face["concept"].astype(str).apply(_clean_concept_token)
                    q_match = q_face[(q_toks == conc_tok) & (q_face["label"].astype(str).str.strip().str.lower() == clean_lbl.lower())]
                    if q_match.empty:
                        q_match = q_face[q_toks == conc_tok]
                    if not q_match.empty and ytd_curr and ytd_prev and latest_fy in row_vals and row_vals[latest_fy] is not None:
                        v_curr = q_match.iloc[0].get(ytd_curr)
                        v_prev = q_match.iloc[0].get(ytd_prev)
                        if pd.notna(v_curr) and pd.notna(v_prev):
                            try:
                                ltm_val = row_vals[latest_fy] + float(v_curr) - float(v_prev)
                            except (ValueError, TypeError):
                                pass

                row_vals["LTM"] = ltm_val

            rows.append({
                "label": clean_lbl,
                "clarification": clarif,
                "concept": conc,
                "level": lvl,
                "is_abstract": is_abs,
                "is_total": is_tot,
                "values": row_vals
            })

        as_reported[s_name] = rows
        print(f"[SEC Extractor] {s_name}: {len(rows)} partidas As-Reported extraídas fielmente de la SEC.")

    return as_reported


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
    
    # 1.1. Enriquecer estados contables con el último formulario anual oficial (10-K o 20-F)
    # Permite capturar conceptos contables modernos o extensiones que no figuran en la agregación de 10 años
    try:
        ann_filings = company.get_filings(form="10-K")
        if not ann_filings:
            ann_filings = company.get_filings(form="20-F")
        if ann_filings and len(ann_filings) > 0:
            updated_cells_inc = set()
            updated_cells_bal = set()
            updated_cells_cf = set()
            for doc_filing in ann_filings[:10]:
                doc_single = doc_filing.obj()
                if not doc_single or not doc_single.financials:
                    continue
                # 1. Detectar si el reporte anual individual contiene ejercicios fiscales más recientes (ej. FY2025)
                new_fys_detected = []
                for stmt_name in ['income_statement', 'balance_sheet', 'cash_flow_statement']:
                    s_check = getattr(doc_single.financials, stmt_name, None)
                    if s_check:
                        s_chk_obj = s_check()
                        if s_chk_obj is not None:
                            chk_df = s_chk_obj.to_dataframe()
                            if chk_df is not None and not chk_df.empty:
                                for c in chk_df.columns:
                                    m = re.search(r'(\d{4})', str(c))
                                    if m and not str(c).startswith('level') and not str(c).startswith('dim'):
                                        tag = f"FY{m.group(1)}"
                                        if tag not in annual_fys and tag not in new_fys_detected:
                                            new_fys_detected.append(tag)
                if new_fys_detected:
                    print(f"[SEC Extractor] ¡Nuevos ejercicios anuales detectados en filing ({doc_filing.form})!: {new_fys_detected}")
                    annual_fys = sorted(list(dict.fromkeys(new_fys_detected + annual_fys)), key=lambda x: int(re.search(r'\d+', x).group(0)) if re.search(r'\d+', x) else 0, reverse=True)
                    latest_fy = annual_fys[0]
                    for nfy in new_fys_detected:
                        for target_d in [inc_df, bal_df, cf_df]:
                            if nfy not in target_d.columns:
                                target_d[nfy] = None

                stmts_to_merge = [
                    ('cash_flow_statement', cf_df, updated_cells_cf),
                    ('income_statement', inc_df, updated_cells_inc),
                    ('balance_sheet', bal_df, updated_cells_bal)
                ]
                for stmt_attr, target_df, up_cells in stmts_to_merge:
                    stmt_fn = getattr(doc_single.financials, stmt_attr, None)
                    if stmt_fn:
                        s_obj = stmt_fn()
                        if s_obj is not None:
                            s_raw_df = s_obj.to_dataframe()
                            if s_raw_df is not None and not s_raw_df.empty:
                                s_ren = {}
                                for c in s_raw_df.columns:
                                    m = re.search(r'(\d{4})', str(c))
                                    if m and not str(c).startswith('level') and not str(c).startswith('dim'):
                                        s_ren[c] = f"FY{m.group(1)}"
                                s_df = s_raw_df.rename(columns=s_ren)
                                merge_annual_statement_df(s_df, target_df, annual_fys, updated_cells=up_cells, overwrite_if_newer=True)

                # También verificar roles de XBRL para StatementsOfProfitOrLoss si income_statement no trajo las partidas
                xb = getattr(doc_single.financials, 'xb', None)
                if xb:
                    try:
                        all_stmts = xb.get_all_statements()
                        for s_meta in all_stmts:
                            rn = str(s_meta.get('role_name', '')).lower()
                            defi = str(s_meta.get('definition', '')).lower()
                            if ('profit' in rn or 'profit' in defi or 'loss' in rn) and 'comprehensive' not in rn and 'comprehensive' not in defi:
                                xb_rows = xb.get_statement(s_meta.get('role'))
                                if xb_rows and isinstance(xb_rows, list):
                                    xb_df = convert_xb_statement_to_df(xb_rows)
                                    if not xb_df.empty:
                                        merge_annual_statement_df(xb_df, inc_df, annual_fys, updated_cells=updated_cells_inc, overwrite_if_newer=True)
                    except Exception:
                        pass
    except Exception as e:
        print(f"[SEC Extractor] Nota al enriquecer con reportes anuales individuales: {e}")
    
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
        
    # Cargar facts_df tempranamente para calibración de LTM (MRQ Balance Sheet y 4Q EPS/Shares)
    facts_df = None
    try:
        facts_obj = sec_call_with_retry(company.get_facts)
        if hasattr(facts_obj, 'to_dataframe'):
            facts_df = facts_obj.to_dataframe()
    except Exception as e:
        print(f"[SEC Extractor] Nota al obtener facts_df temprano: {e}")

    latest_mrq_date = None
    if facts_df is not None and not facts_df.empty and 'period_end' in facts_df.columns:
        asset_matches = facts_df[facts_df['concept'].astype(str).str.endswith(':Assets') | facts_df['concept'].astype(str).str.endswith(':StockholdersEquity')]
        if not asset_matches.empty:
            latest_mrq_date = asset_matches['period_end'].dropna().max()
        else:
            latest_mrq_date = facts_df['period_end'].dropna().max()
    
    # 2.1. Clasificación dinámica de sector y modelo contable (Banca/Fintech vs Corporativa)
    profile_path = output_dir / "company_profile.json"
    if not profile_path.exists():
        cand_p = Path("data/processed") / ticker.upper() / "company_profile.json"
        if cand_p.exists():
            profile_path = cand_p

    profile_data_obj = None
    if profile_path.exists():
        try:
            with open(profile_path, "r", encoding="utf-8") as pf:
                profile_data_obj = json.load(pf)
        except Exception as e:
            print(f"[SEC Extractor] Nota al leer company_profile: {e}")

    detected_concepts = set()
    for df_chk in [inc_df, bal_df]:
        if not df_chk.empty and 'concept' in df_chk.columns:
            detected_concepts.update(df_chk['concept'].dropna().astype(str).tolist())

    sic_code = getattr(company, 'sic', None)
    archetype = detect_company_archetype(company=company, profile_data=profile_data_obj, detected_concepts=detected_concepts, sic_code=sic_code)
    is_financial = (archetype in ("FINANCIAL_BANKING", "INSURANCE"))
    print(f"[SEC Extractor] Clasificación de modelo contable y arquetipo: {archetype} (Financiera={is_financial})")

    has_ltm = (q_inc is not None and not q_inc.empty) or (inc_ttm_df is not None and not inc_ttm_df.empty)

    # Si no hay 10-Q trimestral directo (Foreign Private Issuers bajo IFRS/6-K), consultar Form 6-K
    if not has_ltm:
        print("[SEC Extractor] Consultando reportes interinos 6-K para Foreign Private Issuer...")
        ltm_6k_ok = extract_6k_fpi_interim(company, annual_fys, latest_fy, inc_df, bal_df, cf_df)
        if ltm_6k_ok:
            has_ltm = True

    all_fys = (["LTM"] + annual_fys) if has_ltm else annual_fys
    
    if has_ltm and latest_fy and 'LTM' not in inc_df.columns:
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
            
            c_tok = c_name.split(':')[-1].split('_')[-1].lower()
            if is_share_count and q_inc is not None and ytd_curr_inc:
                q_toks = q_inc['concept'].astype(str).apply(lambda x: x.split(':')[-1].split('_')[-1].lower())
                match_q = q_inc[(q_toks == c_tok) | q_inc['concept'].astype(str).str.lower().str.endswith(c_name.lower()) | (q_inc['concept'].astype(str).str.lower() == c_name.lower())]
                if not match_q.empty:
                    v_curr = match_q.iloc[0].get(ytd_curr_inc)
                    if pd.notna(v_curr):
                        try:
                            val = float(v_curr)
                        except (ValueError, TypeError):
                            pass
            elif q_inc is not None and ytd_curr_inc and ytd_prev_inc and pd.notna(fy_val):
                q_toks = q_inc['concept'].astype(str).apply(lambda x: x.split(':')[-1].split('_')[-1].lower())
                match_q = q_inc[(q_toks == c_tok) | q_inc['concept'].astype(str).str.lower().str.endswith(c_name.lower()) | (q_inc['concept'].astype(str).str.lower() == c_name.lower())]
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
            ltm_vals_inc.append(val)
            
        inc_df.insert(inc_df.columns.get_loc(latest_fy), 'LTM', ltm_vals_inc)
        
        # Corroborar y calibrar que EPS y acciones en LTM reflejen el estándar GAAP institucional (suma/promedio 4 trimestres)
        try:
            q4_eps_d = get_ltm_quarterly_metric(facts_df, XBRL_TAXONOMY_MAP["eps_diluted"], mode='sum') if facts_df is not None else None
            q4_eps_b = get_ltm_quarterly_metric(facts_df, XBRL_TAXONOMY_MAP["eps_basic"], mode='sum') if facts_df is not None else None
            q4_sh_d = get_ltm_quarterly_metric(facts_df, XBRL_TAXONOMY_MAP["shares_diluted"], mode='avg') if facts_df is not None else None
            q4_sh_b = get_ltm_quarterly_metric(facts_df, XBRL_TAXONOMY_MAP["shares_basic"], mode='avg') if facts_df is not None else None
            
            for idx_r, r in inc_df.iterrows():
                cn = str(r.get('concept', '')).lower()
                if 'earningspersharediluted' in cn or 'dilutedearningspershare' in cn:
                    if q4_eps_d is not None and q4_eps_d > 0:
                        inc_df.at[idx_r, 'LTM'] = q4_eps_d
                        print(f"[SEC Extractor] LTM Diluted EPS calibrado por suma de 4 trimestres: ${q4_eps_d}")
                elif 'earningspersharebasic' in cn or 'basicearningspershare' in cn:
                    if q4_eps_b is not None and q4_eps_b > 0:
                        inc_df.at[idx_r, 'LTM'] = q4_eps_b
                        print(f"[SEC Extractor] LTM Basic EPS calibrado por suma de 4 trimestres: ${q4_eps_b}")
                elif 'dilutedshares' in cn or 'sharesoutstandingdiluted' in cn or 'weightedaveragenumberofdilutedshares' in cn:
                    if q4_sh_d is not None and q4_sh_d > 0:
                        inc_df.at[idx_r, 'LTM'] = q4_sh_d
                        print(f"[SEC Extractor] LTM Diluted Shares calibrado por promedio de 4 trimestres: {q4_sh_d:,.0f}")
                elif 'basicshares' in cn or 'sharesoutstandingbasic' in cn or 'weightedaveragenumberofsharesoutstandingbasic' in cn:
                    if q4_sh_b is not None and q4_sh_b > 0:
                        inc_df.at[idx_r, 'LTM'] = q4_sh_b
                        print(f"[SEC Extractor] LTM Basic Shares calibrado por promedio de 4 trimestres: {q4_sh_b:,.0f}")

            # Respaldo por identidad contable NI / Shares si no se detectaron trimestres
            if q4_eps_d is None:
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
                                    print(f"[SEC Extractor] LTM Diluted EPS calibrado a 12 meses acumulados (NI/sh): ${exp_ltm_eps} (en vez de ${cur_v})")
        except Exception as e:
            print(f"[SEC Extractor] Nota sobre calibración de EPS y Acciones LTM: {e}")
        
        # --- Balance Sheet MRQ for LTM ---
        mrq_cols = [c for c in bal_mrq_df.columns if c.startswith('Q')] if bal_mrq_df is not None else []
        latest_mrq_col = mrq_cols[0] if mrq_cols else None
        
        # Determinar fecha MRQ para rescate en Company Facts si bal_mrq_df viene condensado
        if latest_mrq_date is None and facts_df is not None and not facts_df.empty and 'period_end' in facts_df.columns:
            asset_matches = facts_df[facts_df['concept'].astype(str).str.endswith(':Assets') | facts_df['concept'].astype(str).str.endswith(':StockholdersEquity')]
            if not asset_matches.empty:
                latest_mrq_date = asset_matches['period_end'].dropna().max()
            else:
                latest_mrq_date = facts_df['period_end'].dropna().max()

        ltm_vals_bal = []
        for _, row in bal_df.iterrows():
            c_name = str(row.get('concept', '')).strip()
            fy_val = row.get(latest_fy)
            val = None

            # Conceptos abstractos de balance (encabezados de sección) no llevan importe
            if c_name.lower().endswith('abstract') or str(row.get('label', '')).lower().endswith('[abstract]'):
                ltm_vals_bal.append(None)
                continue

            if bal_mrq_df is not None and latest_mrq_col:
                c_tok = c_name.split(':')[-1].split('_')[-1].lower()
                b_toks = bal_mrq_df['concept'].astype(str).apply(lambda x: x.split(':')[-1].split('_')[-1].lower())
                match_b = bal_mrq_df[(b_toks == c_tok) | bal_mrq_df['concept'].astype(str).str.lower().str.endswith(c_name.lower()) | (bal_mrq_df['concept'].astype(str).str.lower() == c_name.lower())]
                if not match_b.empty:
                    v = match_b.iloc[0].get(latest_mrq_col)
                    if pd.notna(v):
                        try:
                            val = float(v)
                        except (ValueError, TypeError):
                            pass
            # Si no está en el balance condensado del 10-Q, buscar en facts_df al cierre de MRQ
            if val is None and facts_df is not None and not facts_df.empty:
                c_tok = c_name.split(':')[-1].split('_')[-1]
                cand_search = [c_name, c_tok]
                is_sti_row = any(w in c_tok.lower() for w in ['marketablesecurities', 'shortterminvestments', 'securitiescurrent'])
                for k_tax, cands_tax in {**XBRL_TAXONOMY_MAP, **BANKING_TAXONOMY_MAP}.items():
                    if any(cand.lower() == c_tok.lower() for cand in cands_tax):
                        cand_search.extend(cands_tax)
                if is_sti_row:
                    cand_search.extend(XBRL_TAXONOMY_MAP["marketable_securities_current"])
                    val = get_mrq_fact_sum(facts_df, ["DebtSecuritiesCurrent", "EquitySecuritiesFvNi"], mrq_date=latest_mrq_date)
                    if val is None:
                        val = get_mrq_fact(facts_df, cand_search, mrq_date=latest_mrq_date)
                else:
                    val = get_mrq_fact(facts_df, cand_search, mrq_date=latest_mrq_date)
            ltm_vals_bal.append(val)
            
        bal_df.insert(bal_df.columns.get_loc(latest_fy), 'LTM', ltm_vals_bal)
        
        # --- Cash Flow Statement LTM ---
        all_q_cols_cf = [c for c in q_cf.columns if any(ch.isdigit() for ch in str(c)) and ('Q' in str(c) or 'YTD' in str(c) or '202' in str(c))] if q_cf is not None else []
        ytd_cols_cf = [c for c in all_q_cols_cf if 'YTD' in str(c)]
        if not ytd_cols_cf:
            ytd_cols_cf = all_q_cols_cf
        ytd_curr_cf = sorted(ytd_cols_cf, reverse=True)[0] if len(ytd_cols_cf) >= 1 else None
        ytd_prev_cf = sorted(ytd_cols_cf, reverse=True)[1] if len(ytd_cols_cf) >= 2 else None
        # Detectar datos directos de TTM para Cash Flow si están disponibles
        q_cols_cf_ttm = [col for col in cf_ttm_df.columns if col.startswith('Q')] if cf_ttm_df is not None else []
        latest_q_cf_ttm = q_cols_cf_ttm[0] if q_cols_cf_ttm else None
        ltm_cf_map = {}
        if cf_ttm_df is not None and latest_q_cf_ttm:
            for _, row_cf in cf_ttm_df.iterrows():
                lbl_cf = str(row_cf.get('label', '')).strip().lower()
                c_cf = str(row_cf.get('concept', '')).strip()
                val_cf = row_cf.get(latest_q_cf_ttm)
                if pd.notna(val_cf):
                    try:
                        ltm_cf_map[lbl_cf] = float(val_cf)
                        if c_cf:
                            ltm_cf_map[c_cf.split(':')[-1].split('_')[-1].lower()] = float(val_cf)
                    except (ValueError, TypeError):
                        pass

        ltm_vals_cf = []
        for _, row in cf_df.iterrows():
            c_name = str(row.get('concept', '')).strip()
            fy_val = row.get(latest_fy)
            val = None
            if q_cf is not None and ytd_curr_cf and ytd_prev_cf and pd.notna(fy_val):
                c_tok = c_name.split(':')[-1].split('_')[-1].lower()
                q_toks = q_cf['concept'].astype(str).apply(lambda x: x.split(':')[-1].split('_')[-1].lower())
                match_cf = q_cf[(q_toks == c_tok) | q_cf['concept'].astype(str).str.lower().str.endswith(c_name.lower()) | (q_cf['concept'].astype(str).str.lower() == c_name.lower())]
                # Si no encuentra coincidencia exacta pero es un concepto de CapEx, buscar variantes en la taxonomía
                if match_cf.empty and any(cand.lower() in c_name.lower() for cand in XBRL_TAXONOMY_MAP["capital_expenditures"]):
                    for cand in XBRL_TAXONOMY_MAP["capital_expenditures"]:
                        cand_match = q_cf[q_cf['concept'].astype(str).str.lower().str.endswith(cand.lower()) | (q_cf['concept'].astype(str).str.lower() == cand.lower())]
                        if not cand_match.empty:
                            match_cf = cand_match
                            break
                if not match_cf.empty:
                    q_row = match_cf.iloc[0]
                    v_curr = q_row.get(ytd_curr_cf)
                    v_prev = q_row.get(ytd_prev_cf)
                    if pd.notna(v_curr) and pd.notna(v_prev):
                        try:
                            f_fy = float(fy_val)
                            f_curr = float(v_curr)
                            f_prev = float(v_prev)
                            val = f_fy + f_curr - f_prev
                        except (ValueError, TypeError):
                            pass
            if val is None and ltm_cf_map:
                c_tok = c_name.split(':')[-1].split('_')[-1].lower()
                if c_tok in ltm_cf_map:
                    val = ltm_cf_map[c_tok]
                elif str(row.get('label', '')).strip().lower() in ltm_cf_map:
                    val = ltm_cf_map[str(row.get('label', '')).strip().lower()]
            if val is None and pd.notna(fy_val) and any(cand.lower() in c_name.lower() for cand in XBRL_TAXONOMY_MAP["acquisitions_ma"]):
                try:
                    val = float(fy_val)
                except (ValueError, TypeError):
                    pass
            ltm_vals_cf.append(val)
            
        cf_df.insert(cf_df.columns.get_loc(latest_fy), 'LTM', ltm_vals_cf)
        
    # Convertir a diccionarios conceptuales para JSON
    inc_data = dataframe_to_concept_dict(inc_df, all_fys)
    bal_data = dataframe_to_concept_dict(bal_df, all_fys)
    cf_data = dataframe_to_concept_dict(cf_df, all_fys)
    
    # Cargar facts como respaldo para años antiguos si no se cargó previamente
    if facts_df is None:
        try:
            facts_obj = sec_call_with_retry(company.get_facts)
            if hasattr(facts_obj, 'to_dataframe'):
                facts_df = facts_obj.to_dataframe()
        except Exception:
            pass

    # Enriquecer notas a los estados contables para inversiones no corrientes (ej. EquityMethodInvestments)
    if facts_df is not None and not facts_df.empty:
        for disc_concept in ["EquityMethodInvestments", "InvestmentsInAssociates"]:
            if disc_concept not in bal_data and f"us-gaap_{disc_concept}" not in bal_data:
                disc_vals = {}
                for p_cur in all_fys:
                    if p_cur == "LTM":
                        v_disc = get_mrq_fact(facts_df, [disc_concept], mrq_date=latest_mrq_date)
                    else:
                        v_disc = get_fact_fallback(facts_df, [disc_concept], p_cur, is_flow=False)
                    if v_disc is not None:
                        disc_vals[p_cur] = v_disc
                if disc_vals:
                    bal_data[disc_concept] = {"label": "Equity Method Investments", "values": disc_vals}
        
    print(f"[SEC Extractor] Generando resumen canónico y ratios para períodos: {all_fys}")
    canonical, ratios = extract_canonical_summary(
        inc_data, bal_data, cf_data, all_fys,
        facts_df=facts_df,
        is_financial=is_financial,
        archetype=archetype
    )
    
    # 3. Datos de Segmentos (10 Años + LTM de Productos y Geografías)
    print("[SEC Extractor] Extrayendo desglose de segmentos histórico de 10 años + LTM...")
    segment_df = build_and_save_segments_data(company, all_fys, output_dir=output_dir, canonical_rev=canonical.get("revenue"), latest_10q_inc=q_inc)
    if segment_df is None or segment_df.empty:
        try:
            single_fins = sec_call_with_retry(company.get_financials)
            if single_fins and single_fins.income_statement():
                segment_df = single_fins.income_statement().to_dataframe()
        except Exception:
            segment_df = None

    # 2.5 Estados Financieros Oficiales As-Reported (Filing Presentation fiel a la SEC)
    print("[SEC Extractor] Extrayendo estados contables As-Reported oficiales...")
    try:
        latest_k_filings = company.get_filings(form=["10-K", "20-F"])
        latest_10k_obj = latest_k_filings.latest().obj() if latest_k_filings else None
    except Exception:
        latest_10k_obj = None

    try:
        latest_q_filings = company.get_filings(form=["10-Q", "6-K"])
        latest_10q_obj = latest_q_filings.latest().obj() if latest_q_filings else None
    except Exception:
        latest_10q_obj = None

    as_reported_data = build_as_reported_statements(
        company=company,
        annual_fys=annual_fys,
        latest_fy=latest_fy,
        inc_df=inc_df,
        bal_df=bal_df,
        cf_df=cf_df,
        latest_10k_obj=latest_10k_obj,
        latest_10q_obj=latest_10q_obj,
        q_inc=q_inc,
        q_bal=q_bal,
        q_cf=q_cf,
        facts_df=facts_df
    )
    
    full_dataset = {
        "ticker": ticker.upper(),
        "company_name": name,
        "cik": cik,
        "sic_code": str(sic_code) if sic_code is not None else None,
        "accounting_standard": accounting_std,
        "archetype": archetype,
        "is_financial": is_financial,
        "business_model": archetype if archetype in ("REAL_ESTATE_REIT", "INSURANCE", "PLATFORM_ECOSYSTEM") else ("BANKING_FINTECH" if is_financial else "CORPORATE_TRADITIONAL"),
        "source": f"SEC EDGAR ({accounting_std} Oficial)",
        "extraction_timestamp": datetime.now().isoformat(),
        "fiscal_years": all_fys,
        "canonical_summary": canonical,
        "key_ratios": ratios,
        "income_statement_detail": inc_data,
        "balance_sheet_detail": bal_data,
        "cash_flow_detail": cf_data,
        "as_reported_statements": as_reported_data
    }
    
    # Guardar JSON
    json_path = output_dir / "financial_statements.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(full_dataset, f, indent=2, ensure_ascii=False)
    print(f"[SEC Extractor] JSON canónico generado: {json_path}")
    
    # 4. Narrativas 10-K
    print("[SEC Extractor] Extrayendo secciones cualitativas del último 10-K...")
    filings = company.get_filings(form="10-K")
    narratives = {
        "ticker": ticker.upper(),
        "company_name": name,
        "sic_code": str(sic_code) if sic_code is not None else None,
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
