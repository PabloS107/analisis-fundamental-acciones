# -*- coding: utf-8 -*-
"""
Submódulo de Series y KPIs Sectoriales por Arquetipo (Banca, Plataforma/Ecosistema, Corporativo).
Cumple estrictamente con Regla 6 (cero valores MELI/ficticios por defecto).
"""
from .view_utils import first_present, pct_from_key_ratio, safe_float, usd_to_m


def _fmt_platform_str(val, prefix: str = "", suffix: str = "", decimals: int = 0) -> str:
    num = safe_float(val)
    if num is None:
        return "N/D"
    return f"{prefix}{num:,.{decimals}f}{suffix}"


def build_sector_kpis_and_series(canonical: dict, key_ratios: dict, enriched: dict, chart_periods: list) -> dict:
    """Construye series bancarias, platform_kpis sin defaults de MELI y corp_kpis."""
    nii_series = [usd_to_m(canonical.get("net_interest_income", {}).get(p)) for p in chart_periods]
    non_ii_series = [usd_to_m(canonical.get("non_interest_income", {}).get(p)) for p in chart_periods]
    deposits_series = [usd_to_m(canonical.get("total_deposits", {}).get(p)) for p in chart_periods]
    loans_series = [usd_to_m(canonical.get("net_loans", {}).get(p)) for p in chart_periods]
    clp_series = [
        abs(v) if v is not None else None
        for v in (usd_to_m(canonical.get("credit_loss_provisions", {}).get(p)) for p in chart_periods)
    ]
    cost_of_risk_series = [pct_from_key_ratio(key_ratios.get("cost_of_risk_loans_pct", {}).get(p)) for p in chart_periods]

    dep_by_country = enriched.get("deposits_by_country_bn", {}) or {}
    donut_dep_labels = [k for k in dep_by_country.keys() if "total" not in k.lower()]
    donut_dep_data = [round(float(dep_by_country[k]) * 1000.0, 1) for k in donut_dep_labels]
    donut_dep_colors = ["#8b5cf6", "#38bdf8", "#10b981", "#f59e0b", "#ec4899"][:len(donut_dep_labels)]

    banking_kpis = {
        "return_on_equity_reported": first_present(enriched.get("return_on_equity_reported"), key_ratios.get("roe_pct", {}).get("LTM")),
        "risk_adjusted_nim_pct": first_present(enriched.get("risk_adjusted_nim_pct"), key_ratios.get("risk_adj_nim_pct", {}).get("LTM"), key_ratios.get("nim_pct", {}).get("LTM")),
        "efficiency_ratio_pct": first_present(enriched.get("efficiency_ratio_pct"), key_ratios.get("efficiency_ratio_pct", {}).get("LTM")),
        "npl_15_90_pct": enriched.get("npl_15_90_pct"),
        "npl_90_plus_pct": first_present(enriched.get("npl_90_plus_pct"), key_ratios.get("npl_ratio_pct", {}).get("LTM")),
        "provision_coverage_pct": first_present(enriched.get("provision_coverage_pct"), key_ratios.get("provision_coverage_pct", {}).get("LTM")),
        "monthly_arpac_usd": enriched.get("monthly_arpac_usd"),
        "monthly_cost_to_serve_usd": enriched.get("monthly_cost_to_serve_usd"),
        "total_customers_m": enriched.get("total_customers_m"),
        "active_customers_m": enriched.get("active_customers_m"),
        "deposits_by_country_bn": dep_by_country,
        "customers_by_country_m": enriched.get("customers_by_country_m", {}),
        "capital_adequacy": enriched.get("capital_adequacy", {}),
    }

    mk_kpis = enriched.get("marketplace_kpis", {}) or {}
    fin_kpis = enriched.get("fintech_kpis", {}) or {}
    cred_kpis = enriched.get("credit_portfolio_kpis", {}) or {}
    seg_brk = enriched.get("segment_breakdown", {}) or {}

    credit_portfolio_bn = safe_float(cred_kpis.get("credit_portfolio_usd_bn"))
    credit_portfolio_m = round(credit_portfolio_bn * 1000.0, 1) if credit_portfolio_bn is not None else None

    gmv_3m_m = safe_float(mk_kpis.get("gmv_three_months_usd_m"))
    gmv_6m_m = safe_float(mk_kpis.get("gmv_six_months_usd_m"))
    tpv_3m_m = safe_float(fin_kpis.get("tpv_total_usd_m"))
    tpv_6m_m = safe_float(fin_kpis.get("tpv_total_six_months_usd_m"))
    unique_buyers_m = safe_float(mk_kpis.get("unique_active_buyers_m"))
    fintech_mau_m = safe_float(fin_kpis.get("fintech_mau_m"))
    items_sold_3m_m = safe_float(mk_kpis.get("items_sold_three_months_m"))
    items_sold_6m_m = safe_float(mk_kpis.get("items_sold_six_months_m"))

    platform_kpis = {
        "gmv_3m_m": gmv_3m_m,
        "gmv_6m_m": gmv_6m_m,
        "tpv_3m_m": tpv_3m_m,
        "tpv_6m_m": tpv_6m_m,
        "unique_buyers_m": unique_buyers_m,
        "fintech_mau_m": fintech_mau_m,
        "items_sold_3m_m": items_sold_3m_m,
        "items_sold_6m_m": items_sold_6m_m,
        "credit_portfolio_bn": credit_portfolio_bn,
        "credit_portfolio_m": credit_portfolio_m,
        "credit_portfolio_str": _fmt_platform_str(credit_portfolio_m, "$", "M", decimals=1),
        "gmv_3m_str": _fmt_platform_str(gmv_3m_m, "$", "M", decimals=0),
        "gmv_6m_str": _fmt_platform_str(gmv_6m_m, "$", "M", decimals=0),
        "tpv_3m_str": _fmt_platform_str(tpv_3m_m, "$", "M", decimals=0),
        "tpv_6m_str": _fmt_platform_str(tpv_6m_m, "$", "M", decimals=0),
        "unique_buyers_str": _fmt_platform_str(unique_buyers_m, "", "M", decimals=0),
        "items_sold_3m_str": _fmt_platform_str(items_sold_3m_m, "", "M", decimals=0),
        "fintech_mau_str": _fmt_platform_str(fintech_mau_m, "", "M", decimals=0),
        "npl_15_90_pct": safe_float(cred_kpis.get("npl_15_90_pct")),
        "npl_90_plus_pct": safe_float(cred_kpis.get("npl_90_plus_pct")),
        "provision_coverage_pct": safe_float(cred_kpis.get("provision_coverage_15_plus_pct")),
        "commerce_rev_m": safe_float(seg_brk.get("commerce_revenue_usd_m")),
        "fintech_rev_m": safe_float(seg_brk.get("fintech_revenue_usd_m")),
    }

    corp_kpis = {
        "gross_margin_pct": round(float(v), 1) if (v := key_ratios.get("gross_margin_pct", {}).get("LTM")) is not None else None,
        "operating_margin_pct": round(float(v), 1) if (v := key_ratios.get("operating_margin_pct", {}).get("LTM")) is not None else None,
        "net_margin_pct": round(float(v), 1) if (v := key_ratios.get("net_margin_pct", {}).get("LTM")) is not None else None,
        "fcf_conversion_pct": round(float(v), 1) if (v := key_ratios.get("fcf_conversion_pct", {}).get("LTM")) is not None else None,
        "fcf_margin_pct": round(float(v), 1) if (v := key_ratios.get("fcf_margin_pct", {}).get("LTM")) is not None else None,
        "current_ratio": round(float(v), 2) if (v := key_ratios.get("current_ratio", {}).get("LTM")) is not None else None,
        "debt_to_equity": round(float(v), 2) if (v := key_ratios.get("debt_to_equity", {}).get("LTM")) is not None else None,
    }

    return {
        "banking_kpis": banking_kpis,
        "platform_kpis": platform_kpis,
        "corp_kpis": corp_kpis,
        "nii_series": nii_series,
        "non_ii_series": non_ii_series,
        "deposits_series": deposits_series,
        "loans_series": loans_series,
        "clp_series": clp_series,
        "cost_of_risk_series": cost_of_risk_series,
        "donut_dep_labels": donut_dep_labels,
        "donut_dep_data": donut_dep_data,
        "donut_dep_colors": donut_dep_colors,
        "gmv_tpv_labels": ["Trimestre (3M)", "Semestre (6M)"],
        "gmv_series": [gmv_3m_m, gmv_6m_m],
        "tpv_series": [tpv_3m_m, tpv_6m_m],
        "buyers_mau_labels": ["Compradores Únicos", "Usuarios Fintech (MAUs)"],
        "buyers_mau_data": [unique_buyers_m, fintech_mau_m],
    }
