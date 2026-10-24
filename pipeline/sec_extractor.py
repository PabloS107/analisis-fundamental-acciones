"""
sec_extractor.py - Extractor oficial de estados contables e items narrativos de SEC EDGAR.
Garantiza datos auditados bajo normativa US-GAAP e IFRS sin intermediarios.
Soporta 10 años de historia fiscal completa y cálculo institucional de LTM (Last Twelve Months / TTM).
Actúa como fachada pública y orquestador modular de alto nivel.
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


# --------------------------------------------------------------------------------------
# RE-EXPORTS DE ARQUETIPOS Y CLASIFICACIÓN (desde entity_classifier)
# --------------------------------------------------------------------------------------
try:
    from entity_classifier import (
        CORPORATE_ARCHETYPE_ALIASES,
        CANONICAL_ARCHETYPES,
        ARCHETYPE_ALIASES,
        normalize_archetype,
        detect_company_archetype,
        is_banking_or_financial,
    )
except ImportError:
    try:
        from .entity_classifier import (
            CORPORATE_ARCHETYPE_ALIASES,
            CANONICAL_ARCHETYPES,
            ARCHETYPE_ALIASES,
            normalize_archetype,
            detect_company_archetype,
            is_banking_or_financial,
        )
    except ImportError:
        from pipeline.entity_classifier import (
            CORPORATE_ARCHETYPE_ALIASES,
            CANONICAL_ARCHETYPES,
            ARCHETYPE_ALIASES,
            normalize_archetype,
            detect_company_archetype,
            is_banking_or_financial,
        )


# --------------------------------------------------------------------------------------
# RE-EXPORTS TAXONÓMICOS (desde financial_taxonomy)
# --------------------------------------------------------------------------------------
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
    try:
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
            generate_data_integrity_badge,
        )


# --------------------------------------------------------------------------------------
# SUBMÓDULOS ESPECIALIZADOS DE EXTRACCIÓN Y CONCILIACIÓN (sec_modules)
# --------------------------------------------------------------------------------------
try:
    from .sec_modules import (
        normalize_fiscal_year,
        _clean_concept_token,
        dataframe_to_concept_dict,
        get_all_matching_sum,
        get_mrq_fact,
        get_mrq_fact_sum,
        get_ltm_quarterly_metric,
        get_fact_fallback,
        detect_global_doc_scale,
        get_preceding_html_context,
        detect_table_scale_factor,
        extract_6k_fpi_interim,
        convert_xb_statement_to_df,
        merge_annual_statement_df,
        enrich_annual_statements_with_individual_filings,
        compute_and_inject_ltm_columns,
        extract_canonical_summary,
        build_and_save_segments_data,
        build_10yr_segment_df,
        build_as_reported_statements,
        sanitize_and_validate_statements,
        derive_period_label,
        check_sec_freshness,
        get_local_sec_metadata,
    )
except ImportError:
    try:
        from sec_modules import (
            normalize_fiscal_year,
            _clean_concept_token,
            dataframe_to_concept_dict,
            get_all_matching_sum,
            get_mrq_fact,
            get_mrq_fact_sum,
            get_ltm_quarterly_metric,
            get_fact_fallback,
            detect_global_doc_scale,
            get_preceding_html_context,
            detect_table_scale_factor,
            extract_6k_fpi_interim,
            convert_xb_statement_to_df,
            merge_annual_statement_df,
            enrich_annual_statements_with_individual_filings,
            compute_and_inject_ltm_columns,
            extract_canonical_summary,
            build_and_save_segments_data,
            build_10yr_segment_df,
            build_as_reported_statements,
            sanitize_and_validate_statements,
            derive_period_label,
            check_sec_freshness,
            get_local_sec_metadata,
        )
    except ImportError:
        from pipeline.sec_modules import (
            normalize_fiscal_year,
            _clean_concept_token,
            dataframe_to_concept_dict,
            get_all_matching_sum,
            get_mrq_fact,
            get_mrq_fact_sum,
            get_ltm_quarterly_metric,
            get_fact_fallback,
            detect_global_doc_scale,
            get_preceding_html_context,
            detect_table_scale_factor,
            extract_6k_fpi_interim,
            convert_xb_statement_to_df,
            merge_annual_statement_df,
            enrich_annual_statements_with_individual_filings,
            compute_and_inject_ltm_columns,
            extract_canonical_summary,
            build_and_save_segments_data,
            build_10yr_segment_df,
            build_as_reported_statements,
            sanitize_and_validate_statements,
            derive_period_label,
            check_sec_freshness,
            get_local_sec_metadata,
        )


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
    
    # 1.1. Enriquecer estados contables con formularios anuales individuales (10-K o 20-F)
    annual_fys, latest_fy = enrich_annual_statements_with_individual_filings(
        company=company,
        inc_df=inc_df,
        bal_df=bal_df,
        cf_df=cf_df,
        annual_fys=annual_fys
    )
    
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
        compute_and_inject_ltm_columns(
            inc_df=inc_df,
            bal_df=bal_df,
            cf_df=cf_df,
            q_inc=q_inc,
            q_cf=q_cf,
            inc_ttm_df=inc_ttm_df,
            cf_ttm_df=cf_ttm_df,
            bal_mrq_df=bal_mrq_df,
            facts_df=facts_df,
            latest_fy=latest_fy,
            latest_mrq_date=latest_mrq_date
        )
        
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

    # 2.6 Metadatos canónicos de frescura y periodicidad SEC
    latest_k_filing = latest_k_filings[0] if (latest_k_filings and len(latest_k_filings) > 0) else None
    latest_q_filing = latest_q_filings[0] if (latest_q_filings and len(latest_q_filings) > 0) else None
    
    latest_periodic = None
    if latest_q_filing and latest_k_filing:
        latest_periodic = latest_q_filing if str(latest_q_filing.filing_date) >= str(latest_k_filing.filing_date) else latest_k_filing
    else:
        latest_periodic = latest_q_filing or latest_k_filing

    sec_p_form = str(latest_periodic.form).strip() if latest_periodic else "10-Q"
    sec_p_filed = str(latest_periodic.filing_date).strip() if latest_periodic else None
    sec_p_rep = str(getattr(latest_periodic, "report_date", "") or "").strip() if latest_periodic else None
    sec_p_acc = str(latest_periodic.accession_number).strip() if latest_periodic else None
    sec_ltm_label = derive_period_label(sec_p_form, sec_p_rep, sec_p_filed)

    latest_8k_date = None
    try:
        f_8k = company.get_filings(form=["8-K"])
        for f in f_8k[:6]:
            if "2.02" in str(getattr(f, "items", "")):
                latest_8k_date = str(f.filing_date)
                break
    except Exception:
        latest_8k_date = None

    sec_metadata = {
        "ltm_period": sec_ltm_label,
        "ltm_period_end": sec_p_rep if sec_p_rep and sec_p_rep != "None" else None,
        "latest_periodic_form": sec_p_form,
        "latest_periodic_date": sec_p_filed,
        "latest_periodic_accession": sec_p_acc,
        "latest_8k_earnings_date": latest_8k_date,
        "extraction_timestamp": datetime.now().isoformat()
    }
    
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
        "sec_metadata": sec_metadata,
        "canonical_summary": canonical,
        "key_ratios": ratios,
        "income_statement_detail": inc_data,
        "balance_sheet_detail": bal_data,
        "cash_flow_detail": cf_data,
        "as_reported_statements": as_reported_data
    }
    
    # Guardar JSON
    full_dataset = sanitize_and_validate_statements(full_dataset)
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


__all__ = [
    # Configuración y Orquestador Principal
    "load_sec_config",
    "extract_sec_data",
    # Clasificación y Arquetipos (desde entity_classifier)
    "CORPORATE_ARCHETYPE_ALIASES",
    "CANONICAL_ARCHETYPES",
    "ARCHETYPE_ALIASES",
    "normalize_archetype",
    "detect_company_archetype",
    "is_banking_or_financial",
    # Mapas y Utilidades Taxonómicas (desde financial_taxonomy)
    "CORPORATE_TAXONOMY_MAP",
    "BANKING_TAXONOMY_MAP",
    "REIT_TAXONOMY_MAP",
    "INSURANCE_TAXONOMY_MAP",
    "PLATFORM_TAXONOMY_MAP",
    "XBRL_TAXONOMY_MAP",
    "get_first_matching_value",
    "reconcile_accounting_identities",
    "generate_data_integrity_badge",
    # Extracción Cruda XBRL y LTM/TTM (desde sec_modules.sec_xbrl_ltm)
    "normalize_fiscal_year",
    "_clean_concept_token",
    "dataframe_to_concept_dict",
    "get_all_matching_sum",
    "get_mrq_fact",
    "get_mrq_fact_sum",
    "get_ltm_quarterly_metric",
    "get_fact_fallback",
    "detect_global_doc_scale",
    "get_preceding_html_context",
    "detect_table_scale_factor",
    "extract_6k_fpi_interim",
    "convert_xb_statement_to_df",
    "merge_annual_statement_df",
    "enrich_annual_statements_with_individual_filings",
    "compute_and_inject_ltm_columns",
    # Resumen Canónico y Ratios (desde sec_modules.sec_canonical_builder)
    "extract_canonical_summary",
    # Segmentos ASC 280 / ASC 606 (desde sec_modules.sec_segment_extractor)
    "build_and_save_segments_data",
    "build_10yr_segment_df",
    # Conciliación As-Reported y Candados (desde sec_modules.sec_statement_reconciler)
    "build_as_reported_statements",
    "sanitize_and_validate_statements",
    # Limitador de tasa SEC
    "sec_call_with_retry",
    "default_rate_limiter",
]
