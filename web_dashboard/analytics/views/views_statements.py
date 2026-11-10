# -*- coding: utf-8 -*-
"""
Fachada del Módulo de Estados Financieros (Vista Estandarizada 10Y + LTM y SEC As-Reported 3Y + LTM).
Re-exporta resolvers canónicos y delega a views_statements_schemas, views_statements_cells y views_statements_memo.
"""
from pipeline.canonical_resolvers import (
    _extract_multi_source_sum,
    _extract_multi_source_val,
    resolve_canonical_balance_sheet,
    resolve_canonical_capital_flows,
    resolve_canonical_cash_flow,
    resolve_canonical_income_statement,
)

from .view_utils import usd_to_m
from .views_statements_cells import build_standardized_section, build_statement_cells, format_as_reported_row
from .views_statements_memo import build_legacy_table_pnl, build_memo_rows, build_statements_summary
from .views_statements_schemas import get_balance_sheet_sections, get_cashflow_sections, get_pnl_sections


def build_statements_context(
    fs,
    fys,
    statements_fys,
    latest_p,
    canonical,
    key_ratios,
    archetype,
    is_banking,
    is_insurance,
    is_reit,
    is_financial,
    enriched,
    bs_data,
    pnl_data,
    cap_flows,
    cf_data,
):
    """Construye las tablas de estados financieros (Estandarizados, SEC As-Reported, Resúmenes y P&L resumido)."""
    statements_fys = [p for p in fs.get("fiscal_years", [])[:11]]
    as_rep_fys = [p for p in statements_fys[:4]]
    as_reported = fs.get("as_reported_statements", {})
    as_rep_inc = as_reported.get("income_statement", [])
    as_rep_cf = as_reported.get("cash_flow_statement", []) or as_reported.get("cash_flow", [])
    as_rep_bs = as_reported.get("balance_sheet", [])

    ebt_dict_std = {p: usd_to_m(pnl_data["ebt"].get(p)) for p in statements_fys}
    ebt_dict_asrep = {p: ebt_dict_std.get(p) for p in as_rep_fys}
    bs_tot_assets_std = {p: usd_to_m(bs_data.get("total_assets", {}).get(p)) for p in statements_fys}
    bs_tot_assets_asrep = {p: bs_tot_assets_std.get(p) for p in as_rep_fys}

    memo_args = (fs, archetype, canonical, key_ratios, enriched, bs_data, pnl_data, cap_flows, cf_data, as_rep_cf)

    # 1. Vista Estandarizada (10Y + LTM)
    std_inc_rows = build_standardized_section(get_pnl_sections(archetype), pnl_data, statements_fys, canonical, default_pct_mode="rev")
    std_inc_rows.extend(build_memo_rows(statements_fys, "pnl", *memo_args))
    std_pnl = [build_statement_cells(r, statements_fys, canonical, ebt_dict=ebt_dict_std) for r in std_inc_rows]

    std_cf_rows = build_standardized_section(get_cashflow_sections(archetype, cf_data), cf_data, statements_fys, canonical, default_pct_mode="ni")
    std_cf_rows.extend(build_memo_rows(statements_fys, "cashflow", *memo_args))
    std_cashflow = [build_statement_cells(r, statements_fys, canonical) for r in std_cf_rows]

    std_bs_rows = build_standardized_section(get_balance_sheet_sections(archetype), bs_data, statements_fys, canonical, default_pct_mode="assets")
    std_bs_rows.extend(build_memo_rows(statements_fys, "balancesheet", *memo_args))
    std_balancesheet = [build_statement_cells(r, statements_fys, canonical, bs_tot_assets=bs_tot_assets_std) for r in std_bs_rows]

    # 2. Vista Oficial SEC (As-Reported 3Y + LTM)
    if as_rep_inc:
        as_rep_inc_rows = [format_as_reported_row(r_raw, as_rep_fys, fs, pct_mode="rev") for r_raw in as_rep_inc]
        as_rep_inc_rows.extend(build_memo_rows(as_rep_fys, "pnl", *memo_args))
        as_rep_pnl = [build_statement_cells(r, as_rep_fys, canonical, ebt_dict=ebt_dict_asrep) for r in as_rep_inc_rows]
    else:
        as_rep_pnl = std_pnl

    if as_rep_cf:
        as_rep_cf_rows = [format_as_reported_row(r_raw, as_rep_fys, fs, pct_mode="ni") for r_raw in as_rep_cf]
        as_rep_cf_rows.extend(build_memo_rows(as_rep_fys, "cashflow", *memo_args))
        as_rep_cashflow = [build_statement_cells(r, as_rep_fys, canonical) for r in as_rep_cf_rows]
    else:
        as_rep_cashflow = std_cashflow

    if as_rep_bs:
        as_rep_bs_rows = [format_as_reported_row(r_raw, as_rep_fys, fs, pct_mode="assets") for r_raw in as_rep_bs]
        as_rep_bs_rows.extend(build_memo_rows(as_rep_fys, "balancesheet", *memo_args))
        as_rep_balancesheet = [build_statement_cells(r, as_rep_fys, canonical, bs_tot_assets=bs_tot_assets_asrep) for r in as_rep_bs_rows]
    else:
        as_rep_balancesheet = std_balancesheet

    statements_summary = build_statements_summary(
        statements_fys, fs, canonical, key_ratios, archetype, is_banking, is_insurance, is_reit, is_financial, enriched, bs_data, pnl_data,
    )
    table_pnl = build_legacy_table_pnl(fys, canonical)

    return {
        "table_pnl": table_pnl,
        "statements_pnl": std_pnl,
        "statements_cashflow": std_cashflow,
        "statements_balancesheet": std_balancesheet,
        "statements_fys": statements_fys,
        "statements_ltm": statements_fys[0] if statements_fys else "LTM",
        "statements_annual_fys": statements_fys[1:] if len(statements_fys) > 1 else [],
        "std_pnl": std_pnl,
        "std_cashflow": std_cashflow,
        "std_balancesheet": std_balancesheet,
        "as_rep_pnl": as_rep_pnl,
        "as_rep_cashflow": as_rep_cashflow,
        "as_rep_balancesheet": as_rep_balancesheet,
        "as_rep_fys": as_rep_fys,
        "as_rep_ltm": as_rep_fys[0] if as_rep_fys else "LTM",
        "as_rep_annual_fys": as_rep_fys[1:] if len(as_rep_fys) > 1 else [],
        "statements_summary": statements_summary,
    }
