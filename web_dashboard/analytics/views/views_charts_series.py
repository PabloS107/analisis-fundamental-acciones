# -*- coding: utf-8 -*-
"""
Submódulo de Series Temporales de Rentabilidad, Conversión de Caja, Dinámica del Accionista
y Asignación de Capital (5Y Auditado).
"""
from .view_utils import (
    find_cf_detail_concept,
    pct_from_key_ratio,
    safe_float,
    usd_to_m,
)
from .views_statements import resolve_canonical_capital_flows

_SBC_KEYS = [
    "ShareBasedCompensation",
    "AllocatedShareBasedCompensationExpense",
    "StockOptionPlanExpense",
    "RestrictedStockExpense",
    "us-gaap_AllocatedShareBasedCompensationExpense",
    "stock_based_compensation",
]
_CAPEX_KEYS = [
    "PaymentsToAcquirePropertyPlantAndEquipment",
    "PaymentsToAcquireProductiveAssets",
    "PurchaseOfPropertyPlantAndEquipment",
    "AdditionsToPropertyPlantAndEquipment",
    "PropertyPlantAndEquipment",
    "CapitalExpenditures",
]
_CFO_KEYS = [
    "NetCashProvidedByUsedInOperatingActivities",
    "CashFlowsFromUsedInOperatingActivities",
    "cash_from_operations",
]


def _fmt_usd_dynamic(val: float) -> str:
    abs_v = abs(val)
    if abs_v >= 1e9:
        return f"${val / 1e9:,.1f}B"
    if abs_v >= 1e6:
        return f"${val / 1e6:,.1f}M"
    return f"${val:,.0f}"


def _fmt_alloc_num(val: float) -> str:
    return f"${val / 1e6:,.1f}M" if abs(val) >= 1e6 else f"${val:,.0f}"


def build_profitability_and_cash_series(canonical: dict, key_ratios: dict, chart_periods: list) -> dict:
    """Construye series de P&L, márgenes (sin forzar <=1 a %) y conversión de caja FCF/NI."""
    rev_series = [usd_to_m(canonical.get("revenue", {}).get(p)) for p in chart_periods]
    gp_series = [usd_to_m(canonical.get("gross_profit", {}).get(p)) for p in chart_periods]
    ebit_series = [usd_to_m(canonical.get("operating_income", {}).get(p)) for p in chart_periods]
    ni_series = [usd_to_m(canonical.get("net_income", {}).get(p)) for p in chart_periods]

    gm_series = [pct_from_key_ratio(key_ratios.get("gross_margin_pct", {}).get(p)) for p in chart_periods]
    om_series = [pct_from_key_ratio(key_ratios.get("operating_margin_pct", {}).get(p)) for p in chart_periods]
    nm_series = [pct_from_key_ratio(key_ratios.get("net_margin_pct", {}).get(p)) for p in chart_periods]

    fcf_m_series = []
    cash_conv_rates = []
    for p in chart_periods:
        fcf_val = safe_float(canonical.get("free_cash_flow", {}).get(p))
        rev_val = safe_float(canonical.get("revenue", {}).get(p))
        ni_val = safe_float(canonical.get("net_income", {}).get(p))
        fcf_m_series.append(round((fcf_val / rev_val) * 100.0, 2) if (fcf_val is not None and rev_val and rev_val > 0) else None)
        cash_conv_rates.append(round((fcf_val / ni_val) * 100.0, 1) if (ni_val is not None and ni_val > 0 and fcf_val is not None) else None)

    cfo_series = [usd_to_m(canonical.get("cash_from_operations", {}).get(p)) for p in chart_periods]
    capex_series = [usd_to_m(canonical.get("capital_expenditures", {}).get(p)) for p in chart_periods]
    fcf_series = [usd_to_m(canonical.get("free_cash_flow", {}).get(p)) for p in chart_periods]

    valid_conv_ltm = cash_conv_rates[-1] if cash_conv_rates and cash_conv_rates[-1] is not None else None
    non_ltm_rates = [r for idx, r in enumerate(cash_conv_rates) if chart_periods[idx] != "LTM" and r is not None]
    recent_rates = non_ltm_rates[-5:] if non_ltm_rates else [r for r in cash_conv_rates if r is not None][-5:]
    avg_conv_5y = round(sum(recent_rates) / len(recent_rates), 1) if recent_rates else None

    if avg_conv_5y is None:
        conv_badge, conv_badge_color = "⚪ DATO LIMITADO", "slate"
    elif avg_conv_5y >= 95.0:
        conv_badge, conv_badge_color = "🟢 ALTA CALIDAD (FCF ≥ 95% BENEFICIOS)", "emerald"
    elif avg_conv_5y >= 75.0:
        conv_badge, conv_badge_color = "🟡 CALIDAD SALUDABLE (75% - 94%)", "amber"
    else:
        conv_badge, conv_badge_color = "🔴 ABSORCIÓN DE CAJA / DEVENGOS ALTOS (< 75%)", "rose"

    return {
        "rev_series": rev_series,
        "gp_series": gp_series,
        "ebit_series": ebit_series,
        "ni_series": ni_series,
        "gm_series": gm_series,
        "om_series": om_series,
        "nm_series": nm_series,
        "fcf_m_series": fcf_m_series,
        "cfo_series": cfo_series,
        "capex_series": capex_series,
        "fcf_series": fcf_series,
        "cash_conv_rates": cash_conv_rates,
        "cash_conv_summary": {
            "ltm_str": f"{valid_conv_ltm:.1f}%" if valid_conv_ltm is not None else "N/D",
            "avg_5y_str": f"{avg_conv_5y:.1f}%" if avg_conv_5y is not None else "N/D",
            "badge": conv_badge,
            "badge_color": conv_badge_color,
        },
    }


def _extract_cf_dict_for_periods(cf_sources, canonical_dict, fallback_keys, chart_periods, take_abs=True, ignore_zero=True):
    """Resuelve valores de flujo por período desde canonical y fallback a detalle SEC."""
    out = {}
    for p in chart_periods:
        val = safe_float((canonical_dict or {}).get(p))
        if val is not None and (not ignore_zero or abs(val) > 0):
            out[p] = abs(val) if take_abs else val
        else:
            found = find_cf_detail_concept(cf_sources, fallback_keys, p, take_abs=take_abs, ignore_zero=ignore_zero)
            out[p] = found if found is not None else 0.0
    return out


def build_shareholder_and_allocation_context(fs: dict, fys: list, canonical: dict, chart_periods: list) -> dict:
    """Construye Dinámica del Accionista (Buybacks - SBC vs Float) y Marco 5Y de Asignación."""
    all_known_periods = list(dict.fromkeys(list(fys) + list(chart_periods) + list(fs.get("fiscal_years", []))))
    capital_flows = resolve_canonical_capital_flows(fs, all_known_periods)
    cf_sources = [fs.get("cash_flow_detail", {}), fs.get("cash_flow_statement", {})]

    buybacks_dict = {p: capital_flows["share_repurchases_open_market"].get(p, 0.0) for p in chart_periods}
    sbc_dict = _extract_cf_dict_for_periods(cf_sources, canonical.get("stock_based_compensation", {}), _SBC_KEYS, chart_periods, take_abs=True, ignore_zero=True)

    scale = 1e6
    buybacks_series = [round((buybacks_dict.get(p) or 0.0) / scale, 1) for p in chart_periods]
    sbc_series = [round((sbc_dict.get(p) or 0.0) / scale, 1) for p in chart_periods]
    net_buybacks_series = [round(((buybacks_dict.get(p) or 0.0) - (sbc_dict.get(p) or 0.0)) / scale, 1) for p in chart_periods]
    net_buyback_colors = ["rgba(16, 185, 129, 0.85)" if val >= 0 else "rgba(244, 63, 94, 0.85)" for val in net_buybacks_series]
    net_buyback_borders = ["#10b981" if val >= 0 else "#f43f5e" for val in net_buybacks_series]

    shares_dict = canonical.get("shares_diluted_adjusted", {}) or canonical.get("shares_diluted", {})
    shares_series = [round(float(shares_dict.get(p, 0) or 0) / scale, 1) for p in chart_periods]
    shares_yoy_pct = [
        round(((shares_series[i] - shares_series[i - 1]) / shares_series[i - 1]) * 100.0, 2)
        if (i > 0 and shares_series[i - 1] > 0 and shares_series[i] > 0) else None
        for i in range(len(chart_periods))
    ]
    eps_dict = canonical.get("eps_diluted_adjusted", {}) or canonical.get("eps_diluted", {})
    eps_series = [round(float(eps_dict.get(p, 0) or 0), 2) for p in chart_periods]

    valid_shares = [(p, float(shares_dict.get(p, 0) or 0)) for p in chart_periods if float(shares_dict.get(p, 0) or 0) > 0]
    float_str = f"{((valid_shares[-1][1] - valid_shares[0][1]) / valid_shares[0][1]) * 100.0:+.1f}%" if len(valid_shares) >= 2 else "-"

    annual_periods = [p for p in chart_periods if p != "LTM"] or list(chart_periods)
    tot_bb_ann = sum(abs(float(buybacks_dict.get(p) or 0.0)) for p in annual_periods)
    tot_sbc_ann = sum(abs(float(sbc_dict.get(p) or 0.0)) for p in annual_periods)

    buybacks_summary = {
        "float_change_pct": float_str,
        "total_buybacks": f"${tot_bb_ann / 1e6:,.1f}M" if tot_bb_ann >= 1e6 else f"${tot_bb_ann:,.0f}",
        "total_sbc": _fmt_usd_dynamic(tot_sbc_ann),
        "total_net_buybacks": _fmt_usd_dynamic(tot_bb_ann - tot_sbc_ann),
        "sbc_coverage_ratio": f"{tot_bb_ann / tot_sbc_ann:.1f}x" if tot_sbc_ann > 0 else "N/A",
    }

    # Asignación de Capital (5Y Auditado)
    alloc_capex_dict = _extract_cf_dict_for_periods(cf_sources, canonical.get("capital_expenditures", {}), _CAPEX_KEYS, chart_periods, take_abs=True, ignore_zero=True)
    alloc_cfo_dict = _extract_cf_dict_for_periods(cf_sources, canonical.get("cash_from_operations", {}), _CFO_KEYS, chart_periods, take_abs=False, ignore_zero=False)
    alloc_bb_dict = buybacks_dict
    alloc_div_dict = {p: capital_flows["dividends_paid"].get(p, 0.0) for p in chart_periods}
    alloc_ma_dict = {p: capital_flows["acquisitions_ma"].get(p, 0.0) for p in chart_periods}
    alloc_dr_dict = {p: capital_flows["debt_repayments"].get(p, 0.0) for p in chart_periods}
    alloc_di_dict = {p: capital_flows["debt_issuances"].get(p, 0.0) for p in chart_periods}

    alloc_periods = [p for p in chart_periods if p != "LTM"][-5:]
    tot_cfo_5y = sum(alloc_cfo_dict.get(p) or 0.0 for p in alloc_periods)
    tot_capex_5y = sum(alloc_capex_dict.get(p) or 0.0 for p in alloc_periods)
    tot_bb_5y = sum(alloc_bb_dict.get(p) or 0.0 for p in alloc_periods)
    tot_div_5y = sum(alloc_div_dict.get(p) or 0.0 for p in alloc_periods)
    tot_ma_5y = sum(alloc_ma_dict.get(p) or 0.0 for p in alloc_periods)
    total_shareholder_return_5y = tot_bb_5y + tot_div_5y
    tot_reinvest_5y = tot_capex_5y + tot_ma_5y

    pct_reinv_capex = round((tot_capex_5y / tot_cfo_5y * 100.0), 1) if tot_cfo_5y > 0 else 0.0
    pct_tot_reinv = round((tot_reinvest_5y / tot_cfo_5y * 100.0), 1) if tot_cfo_5y > 0 else 0.0
    pct_sh_ret = round((total_shareholder_return_5y / tot_cfo_5y * 100.0), 1) if tot_cfo_5y > 0 else 0.0
    pct_bb_5y = round((tot_bb_5y / tot_cfo_5y * 100.0), 1) if tot_cfo_5y > 0 else 0.0
    pct_div_5y = round((tot_div_5y / tot_cfo_5y * 100.0), 1) if tot_cfo_5y > 0 else 0.0
    pct_ma_5y = round((tot_ma_5y / tot_cfo_5y * 100.0), 1) if tot_cfo_5y > 0 else 0.0
    bb_share = round((tot_bb_5y / total_shareholder_return_5y * 100.0), 1) if total_shareholder_return_5y > 0 else 0.0
    div_share = round((tot_div_5y / total_shareholder_return_5y * 100.0), 1) if total_shareholder_return_5y > 0 else 0.0

    if total_shareholder_return_5y > 0 and (tot_bb_5y / total_shareholder_return_5y) > 0.60 and pct_sh_ret >= 45.0:
        cap_prof, prof_badge, prof_desc, prof_col = (
            "Caníbal de Acciones (Buyback Heavy)", "💎 CANÍBAL DE ACCIONES",
            "Prioriza la recompra masiva de acciones reduciendo el float y acelerando el crecimiento del BPA por encima del beneficio neto.", "purple",
        )
    elif pct_reinv_capex >= 45.0 or (pct_reinv_capex + pct_ma_5y >= 55.0):
        cap_prof, prof_badge, prof_desc, prof_col = (
            "Re-inversora de Alto Crecimiento", "🚀 RE-INVERSORA DE CRECIMIENTO",
            "Retiene la mayor parte de su generación operativa para expandir infraestructura, logística y desarrollo orgánico/inorgánico.", "emerald",
        )
    elif tot_div_5y > tot_bb_5y and pct_div_5y >= 35.0:
        cap_prof, prof_badge, prof_desc, prof_col = (
            "Distribuidora de Dividendos", "💰 DISTRIBUIDORA DE DIVIDENDOS",
            "Enfocada en retribuir al accionista mediante flujos directos de dividendos en efectivo constantes y crecientes.", "amber",
        )
    else:
        cap_prof, prof_badge, prof_desc, prof_col = (
            "Equilibrada (Balance Diversificado)", "⚖️ ASIGNACIÓN EQUILIBRADA",
            "Estrategia mixta combinando reinversión prudente, retorno de caja al accionista y fortaleza de balance.", "sky",
        )

    alloc_capex_series = [round(alloc_capex_dict.get(p, 0.0) / scale, 1) for p in chart_periods]
    alloc_buybacks_series = [round(alloc_bb_dict.get(p, 0.0) / scale, 1) for p in chart_periods]
    alloc_dividends_series = [round(alloc_div_dict.get(p, 0.0) / scale, 1) for p in chart_periods]
    alloc_ma_series = [round(alloc_ma_dict.get(p, 0.0) / scale, 1) for p in chart_periods]
    alloc_debt_series = [round(max(0.0, (alloc_dr_dict.get(p) or 0.0) - (alloc_di_dict.get(p) or 0.0)) / scale, 1) for p in chart_periods]
    alloc_cfo_series = [round(alloc_cfo_dict.get(p, 0.0) / scale, 1) for p in chart_periods]

    return {
        "shares_unit": "M",
        "buybacks_unit": "M",
        "alloc_unit": "M",
        "buybacks_series": buybacks_series,
        "sbc_series": sbc_series,
        "net_buybacks_series": net_buybacks_series,
        "net_buyback_colors": net_buyback_colors,
        "net_buyback_borders": net_buyback_borders,
        "shares_series": shares_series,
        "shares_yoy_pct": shares_yoy_pct,
        "eps_series": eps_series,
        "buybacks_summary": buybacks_summary,
        "alloc_kpis": {
            "unit": "M",
            "total_shareholder_return_5y_str": _fmt_alloc_num(total_shareholder_return_5y),
            "total_shareholder_return_5y_num": total_shareholder_return_5y,
            "bb_share_return_pct": f"{bb_share:.1f}%",
            "div_share_return_pct": f"{div_share:.1f}%",
            "tot_reinvest_5y_str": _fmt_alloc_num(tot_reinvest_5y),
            "pct_reinvestment_capex_5y": f"{pct_reinv_capex:.1f}%",
            "pct_total_reinvestment_5y": f"{pct_tot_reinv:.1f}%",
            "pct_shareholder_return_5y": f"{pct_sh_ret:.1f}%",
            "pct_buybacks_5y": f"{pct_bb_5y:.1f}%",
            "pct_dividends_5y": f"{pct_div_5y:.1f}%",
            "pct_ma_5y": f"{pct_ma_5y:.1f}%",
            "capital_allocation_profile": cap_prof,
            "profile_badge": prof_badge,
            "profile_desc": prof_desc,
            "profile_color": prof_col,
            "tot_cfo_5y_str": _fmt_alloc_num(tot_cfo_5y),
            "tot_capex_5y_str": _fmt_alloc_num(tot_capex_5y),
            "tot_bb_5y_str": _fmt_alloc_num(tot_bb_5y),
            "tot_div_5y_str": _fmt_alloc_num(tot_div_5y),
            "tot_ma_5y_str": _fmt_alloc_num(tot_ma_5y),
            "recent_years_label": f"{alloc_periods[0]}-{alloc_periods[-1]} (5Y Auditado)" if alloc_periods else "N/D",
        },
        "alloc_capex_series": alloc_capex_series,
        "alloc_buybacks_series": alloc_buybacks_series,
        "alloc_dividends_series": alloc_dividends_series,
        "alloc_ma_series": alloc_ma_series,
        "alloc_debt_series": alloc_debt_series,
        "alloc_cfo_series": alloc_cfo_series,
        "chart_alloc_data": {
            "labels": chart_periods,
            "unit": "M",
            "capex": alloc_capex_series,
            "buybacks": alloc_buybacks_series,
            "dividends": alloc_dividends_series,
            "ma": alloc_ma_series,
            "debt": alloc_debt_series,
            "cfo": alloc_cfo_series,
            "reinvest_rate_series": [
                round(((alloc_capex_dict.get(p, 0.0) + alloc_ma_dict.get(p, 0.0)) / alloc_cfo_dict.get(p, 1.0)) * 100.0, 1)
                if (alloc_cfo_dict.get(p) or 0) > 0 else 0.0 for p in chart_periods
            ],
            "return_rate_series": [
                round(((alloc_bb_dict.get(p, 0.0) + alloc_div_dict.get(p, 0.0)) / alloc_cfo_dict.get(p, 1.0)) * 100.0, 1)
                if (alloc_cfo_dict.get(p) or 0) > 0 else 0.0 for p in chart_periods
            ],
        },
    }
