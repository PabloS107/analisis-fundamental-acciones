# -*- coding: utf-8 -*-
"""
Módulo de Series para Gráficos (Chart.js), Asignación de Capital, KPIs Sectoriales y Desglose de Segmentos.
"""
import json
import re
from .views_statements import resolve_canonical_capital_flows


def _to_m(val):
    if val is None:
        return None
    v = float(val)
    return round(v / 1e6, 1)


def build_charts_and_segments_context(
    ticker_dir,
    fs,
    fys,
    canonical,
    key_ratios,
    enriched,
):
    """Construye las series temporales de ingresos, flujos, recompras, asignación de capital, segmentos y KPIs por arquetipo."""
    def _to_millions(val):
        if val is None:
            return 0.0
        v = float(val)
        return round(v / 1e6 if abs(v) >= 1e6 else v, 1)

    def _norm_pct(val):
        if val is None:
            return 0.0
        v = float(val)
        return round(v * 100.0 if abs(v) <= 1.0 else v, 2)

    # Series para Gráficos en Millones ($M)
    chart_periods = list(reversed(fys))
    rev_series = [_to_millions(canonical.get("revenue", {}).get(p)) for p in chart_periods]
    gp_series = [_to_millions(canonical.get("gross_profit", {}).get(p)) for p in chart_periods]
    ebit_series = [_to_millions(canonical.get("operating_income", {}).get(p)) for p in chart_periods]
    ni_series = [_to_millions(canonical.get("net_income", {}).get(p)) for p in chart_periods]
    
    gm_series = [_norm_pct(key_ratios.get("gross_margin_pct", {}).get(p)) for p in chart_periods]
    om_series = [_norm_pct(key_ratios.get("operating_margin_pct", {}).get(p)) for p in chart_periods]
    nm_series = [_norm_pct(key_ratios.get("net_margin_pct", {}).get(p)) for p in chart_periods]

    # Margen FCF (%) = (FCF / Revenue) * 100
    fcf_m_series = []
    for p in chart_periods:
        fcf_val = canonical.get("free_cash_flow", {}).get(p)
        rev_val = canonical.get("revenue", {}).get(p)
        if fcf_val is not None and rev_val and rev_val > 0:
            fcf_m_series.append(round((float(fcf_val) / float(rev_val)) * 100.0, 2))
        else:
            fcf_m_series.append(0.0)

    # Flujos de caja ($M): CFO, CapEx y FCF
    cfo_series = [_to_millions(canonical.get("cash_from_operations", {}).get(p)) for p in chart_periods]
    capex_series = [_to_millions(canonical.get("capital_expenditures", {}).get(p)) for p in chart_periods]
    fcf_series = [_to_millions(canonical.get("free_cash_flow", {}).get(p)) for p in chart_periods]

    # Recompras, Acciones y BPA: Ingesta unificada vía Helper Canónico SSOT
    all_known_periods = list(dict.fromkeys(list(fys) + list(chart_periods) + list(fs.get("fiscal_years", []))))
    capital_flows = resolve_canonical_capital_flows(fs, all_known_periods)

    # Recompras de acciones puras en mercado abierto (sin contaminar con retención fiscal de RSUs)
    buybacks_dict = {p: capital_flows["share_repurchases_open_market"].get(p, 0.0) for p in chart_periods}

    # Unidades para recompras en Millones ($M)
    raw_buybacks = [buybacks_dict.get(p, 0.0) for p in chart_periods]
    buybacks_unit = "M"
    bb_scale = 1e6
    buybacks_series = [round(buybacks_dict.get(p, 0.0) / bb_scale, 1) for p in chart_periods]

    # Unidades para acciones en circulación en Millones (M acciones)
    shares_dict = canonical.get("shares_diluted_adjusted", {}) or canonical.get("shares_diluted", {})
    shares_unit = "M"
    shares_scale = 1e6
    shares_series = [round(float(shares_dict.get(p, 0) or 0) / shares_scale, 1) for p in chart_periods]

    eps_dict = canonical.get("eps_diluted_adjusted", {}) or canonical.get("eps_diluted", {})
    eps_series = [round(float(eps_dict.get(p, 0) or 0), 2) for p in chart_periods]

    # Resumen de float y recompras dinámico
    valid_shares = [(p, float(shares_dict.get(p, 0) or 0)) for p in chart_periods if float(shares_dict.get(p, 0) or 0) > 0]
    if len(valid_shares) >= 2:
        sh_start = valid_shares[0][1]
        sh_end = valid_shares[-1][1]
        float_change = ((sh_end - sh_start) / sh_start) * 100.0
        float_str = f"{float_change:+.1f}%"
    else:
        float_str = "-"

    annual_bb_periods = [p for p in chart_periods if p != "LTM"] or list(chart_periods)
    total_bb = sum(abs(float(buybacks_dict.get(p) or 0.0)) for p in annual_bb_periods)
    if total_bb >= 1e6:
        bb_str = f"${total_bb/1e6:,.1f}M"
    else:
        bb_str = f"${total_bb:,.0f}"

    buybacks_summary = {
        "float_change_pct": float_str,
        "total_buybacks": bb_str
    }

    # -------------------------------------------------------------
    # MÓDULO DE ASIGNACIÓN DE CAPITAL (CAPITAL ALLOCATION FRAMEWORK)
    # -------------------------------------------------------------
    cf_sources = [fs.get("cash_flow_detail", {}), fs.get("cash_flow_statement", {})]

    def _get_cf_flow(key_name, cfd_keys):
        res = {}
        can_dict = canonical.get(key_name, {})
        for p_k in chart_periods:
            val = can_dict.get(p_k)
            if val is not None and val != 0.0:
                res[p_k] = abs(float(val))
            else:
                found = None
                for cf_src in cf_sources:
                    if not cf_src:
                        continue
                    for c_k in cfd_keys:
                        c_k_lower = c_k.lower()
                        for src_k, src_obj in cf_src.items():
                            src_k_token = src_k.lower().split(':')[-1].split('_')[-1]
                            if (src_k == c_k or src_k.lower() == c_k_lower or src_k_token == c_k_lower):
                                if isinstance(src_obj, dict) and "values" in src_obj:
                                    v_cand = src_obj["values"].get(p_k)
                                    if v_cand is not None and v_cand != 0:
                                        found = abs(float(v_cand))
                                        break
                                elif isinstance(src_obj, dict):
                                    v_cand = src_obj.get(p_k)
                                    if v_cand is not None and v_cand != 0:
                                        found = abs(float(v_cand))
                                        break
                        if found is not None:
                            break
                    if found is not None:
                        break
                res[p_k] = found or 0.0
        return res

    alloc_capex_dict = _get_cf_flow("capital_expenditures", [
        "PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets",
        "PurchaseOfPropertyPlantAndEquipment", "AdditionsToPropertyPlantAndEquipment",
        "PropertyPlantAndEquipment", "CapitalExpenditures"
    ])
    alloc_bb_dict = {p: capital_flows["share_repurchases_open_market"].get(p, 0.0) for p in chart_periods}
    alloc_div_dict = {p: capital_flows["dividends_paid"].get(p, 0.0) for p in chart_periods}
    alloc_ma_dict = {p: capital_flows["acquisitions_ma"].get(p, 0.0) for p in chart_periods}
    alloc_dr_dict = {p: capital_flows["debt_repayments"].get(p, 0.0) for p in chart_periods}
    alloc_di_dict = {p: capital_flows["debt_issuances"].get(p, 0.0) for p in chart_periods}

    alloc_cfo_dict = {}
    cfo_can = canonical.get("cash_from_operations", {})
    for p_k in chart_periods:
        val = cfo_can.get(p_k)
        if val is not None and val != 0.0:
            alloc_cfo_dict[p_k] = float(val)
        else:
            found = None
            for cf_src in cf_sources:
                if not cf_src:
                    continue
                for c_k in ["NetCashProvidedByUsedInOperatingActivities", "CashFlowsFromUsedInOperatingActivities", "cash_from_operations"]:
                    c_k_lower = c_k.lower()
                    for src_k, src_obj in cf_src.items():
                        src_k_token = src_k.lower().split(':')[-1].split('_')[-1]
                        if (src_k == c_k or src_k.lower() == c_k_lower or src_k_token == c_k_lower):
                            if isinstance(src_obj, dict) and "values" in src_obj:
                                v_cand = src_obj["values"].get(p_k)
                                if v_cand is not None:
                                    found = float(v_cand)
                                    break
                            elif isinstance(src_obj, dict):
                                v_cand = src_obj.get(p_k)
                                if v_cand is not None:
                                    found = float(v_cand)
                                    break
                    if found is not None:
                        break
                if found is not None:
                    break
            alloc_cfo_dict[p_k] = found if found is not None else 0.0

    # Escala estandarizada en Millones ($M)
    alloc_scale = 1e6
    alloc_unit = "M"

    alloc_capex_series = [round(alloc_capex_dict[p] / alloc_scale, 1) if alloc_capex_dict.get(p) is not None else 0.0 for p in chart_periods]
    alloc_buybacks_series = [round(alloc_bb_dict[p] / alloc_scale, 1) if alloc_bb_dict.get(p) is not None else 0.0 for p in chart_periods]
    alloc_dividends_series = [round(alloc_div_dict[p] / alloc_scale, 1) if alloc_div_dict.get(p) is not None else 0.0 for p in chart_periods]
    alloc_ma_series = [round(alloc_ma_dict[p] / alloc_scale, 1) if alloc_ma_dict.get(p) is not None else 0.0 for p in chart_periods]
    alloc_debt_series = [round(max(0.0, (alloc_dr_dict.get(p) or 0.0) - (alloc_di_dict.get(p) or 0.0)) / alloc_scale, 1) for p in chart_periods]
    alloc_cfo_series = [round(alloc_cfo_dict[p] / alloc_scale, 1) if alloc_cfo_dict.get(p) is not None else 0.0 for p in chart_periods]

    # Métricas acumuladas sobre los años fiscales cerrados completos (sin solapar el último FY con LTM)
    alloc_periods = [p for p in chart_periods if p != "LTM"] or list(chart_periods)

    tot_cfo_5y = sum(alloc_cfo_dict.get(p) or 0.0 for p in alloc_periods)
    tot_capex_5y = sum(alloc_capex_dict.get(p) or 0.0 for p in alloc_periods)
    tot_bb_5y = sum(alloc_bb_dict.get(p) or 0.0 for p in alloc_periods)
    tot_div_5y = sum(alloc_div_dict.get(p) or 0.0 for p in alloc_periods)
    tot_ma_5y = sum(alloc_ma_dict.get(p) or 0.0 for p in alloc_periods)
    tot_debt_repay_5y = sum(max(0.0, (alloc_dr_dict.get(p) or 0.0) - (alloc_di_dict.get(p) or 0.0)) for p in alloc_periods)

    total_shareholder_return_5y = tot_bb_5y + tot_div_5y
    pct_reinvestment_capex_5y = round((tot_capex_5y / tot_cfo_5y * 100.0), 1) if tot_cfo_5y > 0 else 0.0
    pct_shareholder_return_5y = round((total_shareholder_return_5y / tot_cfo_5y * 100.0), 1) if tot_cfo_5y > 0 else 0.0
    pct_buybacks_5y = round((tot_bb_5y / tot_cfo_5y * 100.0), 1) if tot_cfo_5y > 0 else 0.0
    pct_dividends_5y = round((tot_div_5y / tot_cfo_5y * 100.0), 1) if tot_cfo_5y > 0 else 0.0
    pct_ma_5y = round((tot_ma_5y / tot_cfo_5y * 100.0), 1) if tot_cfo_5y > 0 else 0.0

    # Diagnóstico de Perfil de Asignación de Capital
    if total_shareholder_return_5y > 0 and (tot_bb_5y / total_shareholder_return_5y) > 0.60 and pct_shareholder_return_5y >= 45.0:
        capital_allocation_profile = "Caníbal de Acciones (Buyback Heavy)"
        profile_badge = "💎 CANÍBAL DE ACCIONES"
        profile_desc = "Prioriza la recompra masiva de acciones reduciendo el float y acelerando el crecimiento del BPA por encima del beneficio neto."
        profile_color = "purple"
    elif pct_reinvestment_capex_5y >= 45.0 or (pct_reinvestment_capex_5y + pct_ma_5y >= 55.0):
        capital_allocation_profile = "Re-inversora de Alto Crecimiento"
        profile_badge = "🚀 RE-INVERSORA DE CRECIMIENTO"
        profile_desc = "Retiene la mayor parte de su generación operativa para expandir infraestructura, logística y desarrollo orgánico/inorgánico."
        profile_color = "emerald"
    elif tot_div_5y > tot_bb_5y and pct_dividends_5y >= 35.0:
        capital_allocation_profile = "Distribuidora de Dividendos"
        profile_badge = "💰 DISTRIBUIDORA DE DIVIDENDOS"
        profile_desc = "Enfocada en retribuir al accionista mediante flujos directos de dividendos en efectivo constantes y crecientes."
        profile_color = "amber"
    else:
        capital_allocation_profile = "Equilibrada (Balance Diversificado)"
        profile_badge = "⚖️ ASIGNACIÓN EQUILIBRADA"
        profile_desc = "Estrategia mixta combinando reinversión prudente, retorno de caja al accionista y fortaleza de balance."
        profile_color = "sky"

    def _fmt_alloc_num(val):
        abs_v = abs(val)
        if abs_v >= 1e6:
            return f"${val/1e6:,.1f}M"
        else:
            return f"${val:,.0f}"

    alloc_kpis = {
        "unit": alloc_unit,
        "total_shareholder_return_5y_str": _fmt_alloc_num(total_shareholder_return_5y),
        "total_shareholder_return_5y_num": total_shareholder_return_5y,
        "pct_reinvestment_capex_5y": f"{pct_reinvestment_capex_5y:.1f}%",
        "pct_shareholder_return_5y": f"{pct_shareholder_return_5y:.1f}%",
        "pct_buybacks_5y": f"{pct_buybacks_5y:.1f}%",
        "pct_dividends_5y": f"{pct_dividends_5y:.1f}%",
        "pct_ma_5y": f"{pct_ma_5y:.1f}%",
        "capital_allocation_profile": capital_allocation_profile,
        "profile_badge": profile_badge,
        "profile_desc": profile_desc,
        "profile_color": profile_color,
        "tot_cfo_5y_str": _fmt_alloc_num(tot_cfo_5y),
        "tot_capex_5y_str": _fmt_alloc_num(tot_capex_5y),
        "tot_bb_5y_str": _fmt_alloc_num(tot_bb_5y),
        "tot_div_5y_str": _fmt_alloc_num(tot_div_5y),
        "tot_ma_5y_str": _fmt_alloc_num(tot_ma_5y),
        "recent_years_label": f"{alloc_periods[0]}-{alloc_periods[-1]}" if alloc_periods else "N/D"
    }

    chart_alloc_data = {
        "labels": chart_periods,
        "unit": alloc_unit,
        "capex": alloc_capex_series,
        "buybacks": alloc_buybacks_series,
        "dividends": alloc_dividends_series,
        "ma": alloc_ma_series,
        "debt": alloc_debt_series,
        "cfo": alloc_cfo_series,
    }

    # -------------------------------------------------------------
    # SERIES Y KPIS ESPECÍFICOS POR ARQUETIPO (BANCA / ECOSISTEMA)
    # -------------------------------------------------------------
    # 1. Series Bancarias (Series temporales en $M y %)
    nii_series = [_to_millions(canonical.get("net_interest_income", {}).get(p)) for p in chart_periods]
    non_ii_series = [_to_millions(canonical.get("non_interest_income", {}).get(p)) for p in chart_periods]
    deposits_series = [_to_millions(canonical.get("total_deposits", {}).get(p)) for p in chart_periods]
    loans_series = [_to_millions(canonical.get("net_loans", {}).get(p)) for p in chart_periods]
    clp_series = [abs(_to_millions(canonical.get("credit_loss_provisions", {}).get(p))) for p in chart_periods]
    cost_of_risk_series = [_norm_pct(key_ratios.get("cost_of_risk_loans_pct", {}).get(p)) for p in chart_periods]

    # Donut de depósitos por país (Banca en $M)
    dep_by_country = enriched.get("deposits_by_country_bn", {})
    donut_dep_labels = [k for k in dep_by_country.keys() if "total" not in k.lower()]
    donut_dep_data = [round(float(dep_by_country[k]) * 1000.0, 1) for k in donut_dep_labels]
    donut_dep_colors = ['#8b5cf6', '#38bdf8', '#10b981', '#f59e0b', '#ec4899'][:len(donut_dep_labels)]

    # Bloque estructurado de KPIs Bancarios (Regla 6: Cero Valores por Defecto Ficticios)
    banking_kpis = {
        "return_on_equity_reported": enriched.get("return_on_equity_reported") if enriched.get("return_on_equity_reported") is not None else key_ratios.get("roe_pct", {}).get("LTM"),
        "risk_adjusted_nim_pct": enriched.get("risk_adjusted_nim_pct") if enriched.get("risk_adjusted_nim_pct") is not None else (key_ratios.get("risk_adj_nim_pct", {}).get("LTM") or key_ratios.get("nim_pct", {}).get("LTM")),
        "efficiency_ratio_pct": enriched.get("efficiency_ratio_pct") if enriched.get("efficiency_ratio_pct") is not None else key_ratios.get("efficiency_ratio_pct", {}).get("LTM"),
        "npl_15_90_pct": enriched.get("npl_15_90_pct"),
        "npl_90_plus_pct": enriched.get("npl_90_plus_pct") if enriched.get("npl_90_plus_pct") is not None else key_ratios.get("npl_ratio_pct", {}).get("LTM"),
        "provision_coverage_pct": enriched.get("provision_coverage_pct") if enriched.get("provision_coverage_pct") is not None else key_ratios.get("provision_coverage_pct", {}).get("LTM"),
        "monthly_arpac_usd": enriched.get("monthly_arpac_usd"),
        "monthly_cost_to_serve_usd": enriched.get("monthly_cost_to_serve_usd"),
        "total_customers_m": enriched.get("total_customers_m"),
        "active_customers_m": enriched.get("active_customers_m"),
        "deposits_by_country_bn": dep_by_country,
        "customers_by_country_m": enriched.get("customers_by_country_m", {}),
        "capital_adequacy": enriched.get("capital_adequacy", {}),
    }

    # 2. KPIs y Series de Plataforma / Ecosistema (Marketplace & Fintech)
    mk_kpis = enriched.get("marketplace_kpis", {})
    fin_kpis = enriched.get("fintech_kpis", {})
    cred_kpis = enriched.get("credit_portfolio_kpis", {})
    credit_portfolio_bn = cred_kpis.get("credit_portfolio_usd_bn", 0.0)
    credit_portfolio_m = (credit_portfolio_bn * 1000.0) if credit_portfolio_bn is not None else 0.0

    platform_kpis = {
        "gmv_3m_m": mk_kpis.get("gmv_three_months_usd_m", 0.0),
        "gmv_6m_m": mk_kpis.get("gmv_six_months_usd_m", 0.0),
        "tpv_3m_m": fin_kpis.get("tpv_total_usd_m", 0.0),
        "tpv_6m_m": fin_kpis.get("tpv_total_six_months_usd_m", 0.0),
        "unique_buyers_m": mk_kpis.get("unique_active_buyers_m", 0.0),
        "fintech_mau_m": fin_kpis.get("fintech_mau_m", 0.0),
        "items_sold_3m_m": mk_kpis.get("items_sold_three_months_m", 0.0),
        "items_sold_6m_m": mk_kpis.get("items_sold_six_months_m", 0.0),
        "credit_portfolio_bn": credit_portfolio_bn,
        "credit_portfolio_m": credit_portfolio_m,
        "credit_portfolio_str": f"${credit_portfolio_m:,.1f}M",
        "gmv_3m_str": f"${mk_kpis.get('gmv_three_months_usd_m', 0.0):,.0f}M",
        "gmv_6m_str": f"${mk_kpis.get('gmv_six_months_usd_m', 0.0):,.0f}M",
        "tpv_3m_str": f"${fin_kpis.get('tpv_total_usd_m', 0.0):,.0f}M",
        "tpv_6m_str": f"${fin_kpis.get('tpv_total_six_months_usd_m', 0.0):,.0f}M",
        "unique_buyers_str": f"{mk_kpis.get('unique_active_buyers_m', 0.0):,.0f}M",
        "items_sold_3m_str": f"{mk_kpis.get('items_sold_three_months_m', 0.0):,.0f}M",
        "fintech_mau_str": f"{fin_kpis.get('fintech_mau_m', 0.0):,.0f}M",
        "npl_15_90_pct": cred_kpis.get("npl_15_90_pct", 7.0),
        "npl_90_plus_pct": cred_kpis.get("npl_90_plus_pct", 18.7),
        "provision_coverage_pct": cred_kpis.get("provision_coverage_15_plus_pct", 105.0),
        "commerce_rev_m": enriched.get("segment_breakdown", {}).get("commerce_revenue_usd_m", 0.0),
        "fintech_rev_m": enriched.get("segment_breakdown", {}).get("fintech_revenue_usd_m", 0.0),
    }

    gmv_tpv_labels = ["Trimestre (3M)", "Semestre (6M)"]
    gmv_series = [platform_kpis["gmv_3m_m"], platform_kpis["gmv_6m_m"]]
    tpv_series = [platform_kpis["tpv_3m_m"], platform_kpis["tpv_6m_m"]]
    buyers_mau_labels = ["Compradores Únicos", "Usuarios Fintech (MAUs)"]
    buyers_mau_data = [platform_kpis["unique_buyers_m"], platform_kpis["fintech_mau_m"]]

    # 3. KPIs Operativos Corporativos / Industriales (STANDARD_CORPORATE)
    recent_fy = fys[0] if fys else "LTM"
    gm_ltm = key_ratios.get("gross_margin_pct", {}).get("LTM")
    om_ltm = key_ratios.get("operating_margin_pct", {}).get("LTM")
    nm_ltm = key_ratios.get("net_margin_pct", {}).get("LTM")
    fcf_conv_ltm = key_ratios.get("fcf_conversion_pct", {}).get("LTM")
    fcf_m_ltm = key_ratios.get("fcf_margin_pct", {}).get("LTM")
    cr_ltm = key_ratios.get("current_ratio", {}).get("LTM")
    de_ltm = key_ratios.get("debt_to_equity", {}).get("LTM")

    corp_kpis = {
        "gross_margin_pct": round(float(gm_ltm), 1) if gm_ltm is not None else None,
        "operating_margin_pct": round(float(om_ltm), 1) if om_ltm is not None else None,
        "net_margin_pct": round(float(nm_ltm), 1) if nm_ltm is not None else None,
        "fcf_conversion_pct": round(float(fcf_conv_ltm), 1) if fcf_conv_ltm is not None else None,
        "fcf_margin_pct": round(float(fcf_m_ltm), 1) if fcf_m_ltm is not None else None,
        "current_ratio": round(float(cr_ltm), 2) if cr_ltm is not None else None,
        "debt_to_equity": round(float(de_ltm), 2) if de_ltm is not None else None,
    }


    # -------------------------------------------------------------
    # Desglose de Segmentos & Regiones Geográficas
    # -------------------------------------------------------------
    seg_file = ticker_dir / "segments_data.json"
    segments_raw = {}
    if seg_file.exists():
        try:
            with open(seg_file, "r", encoding="utf-8") as f:
                segments_raw = json.load(f)
        except Exception:
            pass
    

    raw_seg_periods = segments_raw.get("periods", fys)
    seg_periods = []
    for p in (raw_seg_periods or []):
        if p not in seg_periods:
            seg_periods.append(p)

    prod_items = segments_raw.get("product_segments", [])
    geo_items = segments_raw.get("geographic_segments", [])
    can_rev_dict = canonical.get("revenue", {})

    # Helper para formatear cifras monetarias de segmentos de manera homogénea
    def _fmt_seg_val(val):
        if val is None:
            return "-"
        return f"${val:,.0f}M" if abs(val) >= 10000 else f"${val:,.1f}M"

    # Identificación universal de partidas primarias (excluyendo subtotales, subsegmentos y partidas de conciliación)
    real_prod_items = [
        item for item in prod_items
        if not item.get("is_subtotal") and not item.get("is_subsegment") and not item.get("is_reconciling") and item.get("name", "").lower() not in ["revenue", "products", "total net sales", "total revenues", "total revenue"]
    ]
    if not real_prod_items:
        real_prod_items = [item for item in prod_items if not item.get("is_subtotal") and not item.get("is_subsegment") and not item.get("is_reconciling")]
    if not real_prod_items:
        real_prod_items = [item for item in prod_items if not item.get("is_subtotal") and not item.get("is_reconciling")]
    if not real_prod_items:
        real_prod_items = prod_items

    # Partidas de conciliación explícitas de producto (coberturas, ajustes intersegmentos, etc.)
    reconciling_prod_items = [
        item for item in prod_items
        if item.get("is_reconciling") or any(k in item.get("name", "").lower() for k in ["hedging", "reconciling", "intersegment"])
    ]

    real_geo_items = [
        item for item in geo_items
        if not item.get("is_subtotal") and not item.get("is_subsegment") and not item.get("is_reconciling") and item.get("name", "").lower() not in ["revenue", "total net sales", "total revenues", "total revenue"]
    ]
    if not real_geo_items:
        real_geo_items = [item for item in geo_items if not item.get("is_subtotal") and not item.get("is_reconciling")]
    if not real_geo_items:
        real_geo_items = geo_items

    # Obtener ingresos canónicos oficiales de referencia para cada período
    canonical_rev_m = {}
    for p in seg_periods:
        c_val = can_rev_dict.get(p)
        canonical_rev_m[p] = _to_m(c_val) if c_val is not None else None

    # Totales LTM oficiales / consolidados
    can_ltm_m = canonical_rev_m.get("LTM") or canonical_rev_m.get(seg_periods[0] if seg_periods else None)
    raw_prod_ltm = sum(item["values"].get("LTM") or 0.0 for item in real_prod_items)
    raw_geo_ltm = sum(item["values"].get("LTM") or 0.0 for item in real_geo_items)

    tot_prod_ltm = can_ltm_m if (can_ltm_m is not None and can_ltm_m > 0) else (raw_prod_ltm if raw_prod_ltm > 0 else 1.0)
    tot_geo_ltm = can_ltm_m if (can_ltm_m is not None and can_ltm_m > 0) else (raw_geo_ltm if raw_geo_ltm > 0 else 1.0)

    # Construcción jerárquica ordenada de filas de productos con subsegmentos agrupados
    ordered_prod_items = []
    primary_prods = [item for item in prod_items if not item.get("is_subtotal") and not item.get("is_subsegment") and not item.get("is_reconciling") and item.get("name", "").lower() not in ["revenue", "total revenue", "total revenues", "total net sales"]]
    sub_prods = [item for item in prod_items if item.get("is_subsegment")]
    if primary_prods and sub_prods:
        for prim in primary_prods:
            ordered_prod_items.append(prim)
            for sub in sub_prods:
                if sub.get("parent") and sub.get("parent", "").lower() == prim.get("name", "").lower():
                    ordered_prod_items.append(sub)
        for sub in sub_prods:
            if sub not in ordered_prod_items:
                ordered_prod_items.append(sub)
    elif primary_prods:
        ordered_prod_items = primary_prods
    else:
        ordered_prod_items = [item for item in prod_items if not item.get("is_subtotal") and not item.get("is_reconciling")]

    # Añadir partidas de conciliación explícitas de producto al final del desglose
    for rec_item in reconciling_prod_items:
        if rec_item not in ordered_prod_items:
            ordered_prod_items.append(rec_item)

    # Tabla 1: Segmentos de Producto & Servicios
    table_products = []
    seg_op_income_raw = segments_raw.get("segment_operating_income", [])
    for item in ordered_prod_items:
        is_sub = bool(item.get("is_subtotal"))
        is_subseg = bool(item.get("is_subsegment"))
        v_ltm = item["values"].get("LTM")
        mix_pct = (v_ltm / tot_prod_ltm * 100.0) if (tot_prod_ltm > 0 and not is_sub and v_ltm is not None) else None
        
        # Extracción o cómputo de Margen Operativo por Segmento (ASC 280)
        op_m_val = None
        op_m_dict = item.get("operating_margin_pct", {})
        if op_m_dict:
            op_m_val = op_m_dict.get("LTM")
            if op_m_val is None:
                for p in seg_periods:
                    if p in op_m_dict and op_m_dict[p] is not None:
                        op_m_val = op_m_dict[p]
                        break
        if op_m_val is None and not is_sub:
            item_norm = re.sub(r'\s+', ' ', item["name"].lower().replace('&', 'and')).strip()
            for op_entry in seg_op_income_raw:
                op_norm = re.sub(r'\s+', ' ', op_entry.get("name", "").lower().replace('&', 'and')).strip()
                if op_norm == item_norm or (len(item_norm) > 4 and item_norm in op_norm) or (len(op_norm) > 4 and op_norm in item_norm):
                    op_v = op_entry.get("values", {}).get("LTM")
                    rev_v = item["values"].get("LTM")
                    if op_v is None or rev_v is None:
                        for p in seg_periods:
                            if p in op_entry.get("values", {}) and p in item.get("values", {}):
                                op_v = op_entry["values"][p]
                                rev_v = item["values"][p]
                                break
                    if op_v is not None and rev_v and float(rev_v) != 0.0:
                        op_m_val = (float(op_v) / float(rev_v)) * 100.0
                    break

        op_margin_str = f"{float(op_m_val):.1f}%" if (op_m_val is not None and not is_sub) else "-"

        row_vals = []
        for p in seg_periods:
            val = item["values"].get(p)
            row_vals.append(_fmt_seg_val(val) if val is not None else "-")

        display_name = ("↳ " + item["name"]) if is_subseg else item["name"]
        table_products.append({
            "name": display_name,
            "description": item.get("description", ""),
            "is_subtotal": is_sub,
            "is_subsegment": is_subseg,
            "indent": is_subseg,
            "is_total": False,
            "mix_pct": f"{mix_pct:.1f}%" if (mix_pct is not None and not is_sub) else "-",
            "op_margin_ltm": op_margin_str,
            "values": row_vals
        })

    # Conciliación residual universal de productos para cuadre al 100.0% con el P&L
    has_unreconciled_prod = False
    residual_prod_vals = {}
    for p in seg_periods:
        c_m = canonical_rev_m.get(p)
        s_val = sum((item["values"].get(p) or 0.0) for item in ordered_prod_items if not item.get("is_subsegment") and not item.get("is_subtotal"))
        if c_m is not None and s_val != 0.0 and abs(c_m - s_val) > 1.0:
            has_unreconciled_prod = True
            residual_prod_vals[p] = round(c_m - s_val, 1)
        else:
            residual_prod_vals[p] = None

    if has_unreconciled_prod:
        res_ltm = residual_prod_vals.get("LTM")
        res_mix = (res_ltm / tot_prod_ltm * 100.0) if (tot_prod_ltm > 0 and res_ltm is not None) else None
        res_row_vals = [_fmt_seg_val(residual_prod_vals.get(p)) for p in seg_periods]
        table_products.append({
            "name": "Partidas de Conciliación y Coberturas Corporativas",
            "description": "Ajustes contables, eliminaciones y coberturas que concilian la suma de segmentos con los ingresos netos consolidados.",
            "is_subtotal": False,
            "is_subsegment": False,
            "indent": False,
            "is_total": False,
            "mix_pct": f"{res_mix:.1f}%" if res_mix is not None else "-",
            "op_margin_ltm": "-",
            "values": res_row_vals
        })

    # Fila Institucional de Total Neto Consolidado (100.0%)
    total_prod_vals = []
    for p in seg_periods:
        c_m = canonical_rev_m.get(p)
        if c_m is not None:
            total_prod_vals.append(_fmt_seg_val(c_m))
        else:
            s_val = sum(item["values"].get(p) or 0.0 for item in real_prod_items)
            total_prod_vals.append(_fmt_seg_val(s_val))
    
    tot_om_str = f"{corp_kpis['operating_margin_pct']:.1f}%" if corp_kpis.get("operating_margin_pct") is not None else "-"
    table_products.append({
        "name": "(=) Total Neto Consolidado",
        "description": "",
        "is_subtotal": True,
        "is_total": True,
        "mix_pct": "100.0%",
        "op_margin_ltm": tot_om_str,
        "values": total_prod_vals
    })

    # Construcción jerárquica ordenada de filas geográficas con subregiones agrupadas
    ordered_geo_items = []
    primary_geos = [item for item in geo_items if not item.get("is_subtotal") and not item.get("is_subsegment")]
    sub_geos = [item for item in geo_items if item.get("is_subsegment")]
    if primary_geos and sub_geos:
        for prim in primary_geos:
            ordered_geo_items.append(prim)
            for sub in sub_geos:
                if sub.get("parent") and sub.get("parent", "").lower() == prim.get("name", "").lower():
                    ordered_geo_items.append(sub)
        for sub in sub_geos:
            if sub not in ordered_geo_items:
                ordered_geo_items.append(sub)
    elif primary_geos:
        ordered_geo_items = primary_geos
    else:
        ordered_geo_items = [item for item in geo_items if not item.get("is_subtotal")]

    # Tabla 2: Segmentos Geográficos
    table_geos = []
    for item in ordered_geo_items:
        is_sub = bool(item.get("is_subtotal"))
        is_subseg = bool(item.get("is_subsegment"))
        v_ltm = item["values"].get("LTM")
        mix_pct = (v_ltm / tot_geo_ltm * 100.0) if (tot_geo_ltm > 0 and not is_sub and v_ltm is not None) else None
        row_vals = []
        for p in seg_periods:
            val = item["values"].get(p)
            row_vals.append(_fmt_seg_val(val) if val is not None else "-")

        display_name = ("↳ " + item["name"]) if is_subseg else item["name"]
        table_geos.append({
            "name": display_name,
            "description": item.get("description", ""),
            "is_subtotal": is_sub,
            "is_subsegment": is_subseg,
            "indent": is_subseg,
            "is_total": False,
            "mix_pct": f"{mix_pct:.1f}%" if (mix_pct is not None and not is_sub) else "-",
            "op_margin_ltm": "-",
            "values": row_vals
        })

    # Conciliación residual universal geográfica para cuadre al 100.0% con el P&L
    has_unreconciled_geo = False
    residual_geo_vals = {}
    for p in seg_periods:
        c_m = canonical_rev_m.get(p)
        s_val = sum((item["values"].get(p) or 0.0) for item in ordered_geo_items if not item.get("is_subsegment") and not item.get("is_subtotal"))
        if c_m is not None and s_val != 0.0 and abs(c_m - s_val) > 1.0:
            has_unreconciled_geo = True
            residual_geo_vals[p] = round(c_m - s_val, 1)
        else:
            residual_geo_vals[p] = None

    if has_unreconciled_geo:
        res_ltm = residual_geo_vals.get("LTM")
        res_mix = (res_ltm / tot_geo_ltm * 100.0) if (tot_geo_ltm > 0 and res_ltm is not None) else None
        res_row_vals = [_fmt_seg_val(residual_geo_vals.get(p)) for p in seg_periods]
        table_geos.append({
            "name": "Ajustes no Asignados / Coberturas Corporativas",
            "description": "Partidas corporativas consolidadas, coberturas cambiarias o ingresos no asignados a regiones geográficas individuales.",
            "is_subtotal": False,
            "is_subsegment": False,
            "indent": False,
            "is_total": False,
            "mix_pct": f"{res_mix:.1f}%" if res_mix is not None else "-",
            "op_margin_ltm": "-",
            "values": res_row_vals
        })

    # Fila Institucional de Total Neto Consolidado Geográfico (100.0%)
    total_geo_vals = []
    for p in seg_periods:
        c_m = canonical_rev_m.get(p)
        if c_m is not None:
            total_geo_vals.append(_fmt_seg_val(c_m))
        else:
            s_val = sum(item["values"].get(p) or 0.0 for item in real_geo_items)
            total_geo_vals.append(_fmt_seg_val(s_val))
    table_geos.append({
        "name": "(=) Total Neto Consolidado",
        "description": "",
        "is_subtotal": True,
        "is_total": True,
        "mix_pct": "100.0%",
        "values": total_geo_vals
    })

    # KPIs de resumen de segmentos dinámicos (usando exclusivamente segmentos primarios)
    sorted_prods = sorted(real_prod_items, key=lambda x: x["values"].get("LTM") or 0.0, reverse=True)
    top_prod = sorted_prods[0] if len(sorted_prods) > 0 else {"name": "Línea Principal", "values": {}}
    second_prod = sorted_prods[1] if len(sorted_prods) > 1 else {"name": "Línea Secundaria", "values": {}}

    top_prod_ltm = top_prod["values"].get("LTM") or 0.0
    second_prod_ltm = second_prod["values"].get("LTM") or 0.0

    sorted_geos = sorted(real_geo_items, key=lambda x: x["values"].get("LTM") or 0.0, reverse=True)
    top_geo = sorted_geos[0] if len(sorted_geos) > 0 else {"name": "Mercado Principal", "values": {}}
    top_geo_ltm = top_geo["values"].get("LTM") or 0.0

    intl_item = next((item for item in real_geo_items if "international" in item["name"].lower() or "foreign" in item["name"].lower() or "resto" in item["name"].lower()), None)
    if intl_item:
        intl_ltm = intl_item["values"].get("LTM") or 0.0
    else:
        intl_ltm = max(0.0, tot_geo_ltm - top_geo_ltm)
    intl_pct = (intl_ltm / tot_geo_ltm * 100.0) if tot_geo_ltm > 0 else 0.0

    kpis_segments = {
        "top_product_name": top_prod["name"],
        "top_product_ltm": _fmt_seg_val(top_prod_ltm),
        "top_product_mix": f"{(top_prod_ltm/tot_prod_ltm*100.0):.1f}%" if tot_prod_ltm > 0 else "-",
        "second_product_name": second_prod["name"],
        "second_product_ltm": _fmt_seg_val(second_prod_ltm),
        "second_product_mix": f"{(second_prod_ltm/tot_prod_ltm*100.0):.1f}%" if tot_prod_ltm > 0 else "-",
        "top_geo_name": top_geo["name"],
        "top_geo_ltm": _fmt_seg_val(top_geo_ltm),
        "top_geo_mix": f"{(top_geo_ltm/tot_geo_ltm*100.0):.1f}%" if tot_geo_ltm > 0 else "-",
        "intl_ltm": _fmt_seg_val(intl_ltm),
        "intl_pct": f"{intl_pct:.1f}%"
    }

    # Series para Gráficos de Segmentos en Millones ($M) (orden cronológico, usando exclusivamente partidas primarias)
    seg_chart_periods = list(reversed(seg_periods))
    palette = ["#38bdf8", "#a855f7", "#10b981", "#f59e0b", "#f43f5e", "#ec4899", "#6366f1", "#14b8a6", "#84cc16", "#eab308"]

    products_trend_datasets = []
    for idx, item in enumerate(real_prod_items):
        c = palette[idx % len(palette)]
        data_pts = [
            round(float(item["values"][p]), 1) if (p in item["values"] and item["values"][p] is not None) else None
            for p in seg_chart_periods
        ]
        products_trend_datasets.append({
            "label": item["name"],
            "data": data_pts,
            "borderColor": c,
            "backgroundColor": "transparent",
            "borderWidth": 2.5,
            "tension": 0.2,
            "pointRadius": 4,
            "pointHoverRadius": 7,
            "pointHitRadius": 10
        })

    geos_trend_datasets = []
    for idx, item in enumerate(real_geo_items):
        c = palette[idx % len(palette)]
        data_pts = [
            round(float(item["values"][p]), 1) if (p in item["values"] and item["values"][p] is not None) else None
            for p in seg_chart_periods
        ]
        geos_trend_datasets.append({
            "label": item["name"],
            "data": data_pts,
            "borderColor": c,
            "backgroundColor": "transparent",
            "borderWidth": 2.5,
            "tension": 0.2,
            "pointRadius": 4,
            "pointHoverRadius": 7,
        })

    # Datos para Donut Charts LTM en Millones ($M) usando ítems primarios
    donut_prod_labels = [item["name"] for item in real_prod_items]
    donut_prod_data = [round(float(item["values"].get("LTM") or 0), 1) for item in real_prod_items]
    donut_prod_colors = [palette[idx % len(palette)] for idx in range(len(donut_prod_labels))]

    donut_geo_labels = [item["name"] for item in real_geo_items]
    donut_geo_data = [round(float(item["values"].get("LTM") or 0), 1) for item in real_geo_items]
    donut_geo_colors = [palette[idx % len(palette)] for idx in range(len(donut_geo_labels))]


    return {
        "chart_periods_json": json.dumps(chart_periods),
        "rev_series_json": json.dumps(rev_series),
        "gp_series_json": json.dumps(gp_series),
        "ebit_series_json": json.dumps(ebit_series),
        "ni_series_json": json.dumps(ni_series),
        "cfo_series_json": json.dumps(cfo_series),
        "capex_series_json": json.dumps(capex_series),
        "fcf_series_json": json.dumps(fcf_series),
        "gm_series_json": json.dumps(gm_series),
        "om_series_json": json.dumps(om_series),
        "nm_series_json": json.dumps(nm_series),
        "fcf_m_series_json": json.dumps(fcf_m_series),
        "buybacks_series_json": json.dumps(buybacks_series),
        "shares_series_json": json.dumps(shares_series),
        "eps_series_json": json.dumps(eps_series),
        "shares_unit": shares_unit,
        "buybacks_unit": buybacks_unit,
        "buybacks_summary": buybacks_summary,
        "seg_periods": seg_periods,
        "table_products": table_products,
        "table_geos": table_geos,
        "kpis_segments": kpis_segments,
        "seg_chart_periods_json": json.dumps(seg_chart_periods),
        "products_trend_json": json.dumps(products_trend_datasets),
        "geos_trend_json": json.dumps(geos_trend_datasets),
        "donut_prod_labels_json": json.dumps(donut_prod_labels),
        "donut_prod_data_json": json.dumps(donut_prod_data),
        "donut_prod_colors_json": json.dumps(donut_prod_colors),
        "donut_geo_labels_json": json.dumps(donut_geo_labels),
        "donut_geo_data_json": json.dumps(donut_geo_data),
        "donut_geo_colors_json": json.dumps(donut_geo_colors),
        "banking_kpis": banking_kpis,
        "platform_kpis": platform_kpis,
        "corp_kpis": corp_kpis,
        "nii_series_json": json.dumps(nii_series),
        "non_ii_series_json": json.dumps(non_ii_series),
        "deposits_series_json": json.dumps(deposits_series),
        "loans_series_json": json.dumps(loans_series),
        "clp_series_json": json.dumps(clp_series),
        "cost_of_risk_series_json": json.dumps(cost_of_risk_series),
        "donut_dep_labels_json": json.dumps(donut_dep_labels),
        "donut_dep_data_json": json.dumps(donut_dep_data),
        "donut_dep_colors_json": json.dumps(donut_dep_colors),
        "gmv_tpv_labels_json": json.dumps(gmv_tpv_labels),
        "gmv_series_json": json.dumps(gmv_series),
        "tpv_series_json": json.dumps(tpv_series),
        "buyers_mau_labels_json": json.dumps(buyers_mau_labels),
        "buyers_mau_data_json": json.dumps(buyers_mau_data),
        "alloc_kpis": alloc_kpis,
        "alloc_unit": alloc_unit,
        "alloc_capex_series_json": json.dumps(alloc_capex_series),
        "alloc_buybacks_series_json": json.dumps(alloc_buybacks_series),
        "alloc_dividends_series_json": json.dumps(alloc_dividends_series),
        "alloc_ma_series_json": json.dumps(alloc_ma_series),
        "alloc_debt_series_json": json.dumps(alloc_debt_series),
        "alloc_cfo_series_json": json.dumps(alloc_cfo_series),
        "chart_alloc_data_json": json.dumps(chart_alloc_data),
    }
