# -*- coding: utf-8 -*-
"""
Paquete modular de vistas de analytics.
Re-exporta todo desde views.py para mantener 100% de compatibilidad con urls.py y tests.
"""
from .views import (
    index,
    company_detail,
    company_search,
    trigger_pipeline,
    pipeline_status,
    sec_freshness_view,
    get_cached_sec_freshness,
    clear_freshness_cache,
    resolve_canonical_capital_flows,
    resolve_canonical_balance_sheet,
    resolve_canonical_income_statement,
    resolve_canonical_cash_flow,
    _extract_multi_source_val,
    _extract_multi_source_sum,
    DATA_DIR,
    PIPELINE_DIR,
)
