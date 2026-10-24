"""
sec_modules - Submódulos especializados del extractor oficial de SEC EDGAR.
Garantiza datos auditados bajo normativa US-GAAP e IFRS, cálculo de LTM,
construcción del resumen canónico, conciliación As-Reported y segmentos ASC 280 / ASC 606.
"""

from .sec_xbrl_ltm import (
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
)
from .sec_canonical_builder import extract_canonical_summary
from .sec_statement_reconciler import (
    build_as_reported_statements,
    sanitize_and_validate_statements,
)
from .sec_segment_extractor import (
    build_and_save_segments_data,
    build_10yr_segment_df,
)
from .sec_freshness import (
    check_sec_freshness,
    get_local_sec_metadata,
    derive_period_label,
)

__all__ = [
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
    "extract_canonical_summary",
    "build_as_reported_statements",
    "sanitize_and_validate_statements",
    "build_and_save_segments_data",
    "build_10yr_segment_df",
    "check_sec_freshness",
    "get_local_sec_metadata",
    "derive_period_label",
]
