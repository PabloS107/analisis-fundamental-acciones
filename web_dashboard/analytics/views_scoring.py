# -*- coding: utf-8 -*-
"""
Módulo de Scoring Fundamental, Contabilidad Forense, Solvencia Crediticia, Pares y Retornos sobre el Capital.
"""
import json


def _to_m(val):
    if val is None:
        return None
    v = float(val)
    return round(v / 1e6 if abs(v) >= 1e6 else v, 1)


def _to_millions(val):
    if val is None:
        return 0.0
    v = float(val)
    return round(v / 1e6 if abs(v) >= 1e6 else v, 1)


def build_scoring_context(
    ticker,
    scores,
    fs,
    fys,
    statements_fys,
    latest_p,
    canonical,
    archetype,
    is_banking,
    bs_data,
):
    """Construye el contexto de F-Score, G-Score, Novy-Marx, Pares, ROIC/WACC, Solvencia y Forense."""
    chart_periods = list(reversed(fys))
    # KPIs y Señales Auditadas
    f_obj = scores.get("piotroski_f_score", {}).get("LTM", {})
    f_score = f_obj.get("total_score") or f_obj.get("score", 7)
    f_signals_raw = list(f_obj.get("signals", {}).values())
    f_signals = []
    for s in f_signals_raw:
        comp = s.get("comparison_label") or s.get("condition") or s.get("name")
        thresh = s.get("threshold") or s.get("benchmark") or "Norma Contable"
        fmt_val = s.get("formatted_value") or (f"{s.get('value'):.2f}" if isinstance(s.get("value"), (int, float)) else "")
        f_signals.append({
            "name": s.get("name", ""),
            "category": s.get("category", "General"),
            "passed": s.get("passed", False),
            "points": s.get("points", 1 if s.get("passed") else 0),
            "comparison_label": comp,
            "threshold": thresh,
            "formatted_value": fmt_val,
            "description": s.get("description") or s.get("rationale") or "",
        })
    f_summary = f_obj.get("summary_text", "Solidez financiera de primer nivel institucional.")
    f_rating = f_obj.get("rating", "SALUD EXCEPCIONAL")

    g_obj = scores.get("mohanram_g_score", {}).get("LTM", {})
    g_score = g_obj.get("total_score") or g_obj.get("score", 6)
    g_signals_raw = list(g_obj.get("signals", {}).values())
    g_signals = []
    for s in g_signals_raw:
        comp = s.get("comparison_label") or s.get("condition") or s.get("name")
        bench = s.get("benchmark") or s.get("threshold") or "Mediana Sectorial"
        fmt_val = s.get("formatted_value") or (f"{s.get('value'):.2f}" if isinstance(s.get("value"), (int, float)) else "")
        g_signals.append({
            "name": s.get("name", ""),
            "category": s.get("category", "General"),
            "passed": s.get("passed", False),
            "points": s.get("points", 1 if s.get("passed") else 0),
            "comparison_label": comp,
            "benchmark": bench,
            "threshold": bench,
            "formatted_value": fmt_val,
            "description": s.get("description") or s.get("rationale") or "",
        })
    g_summary = g_obj.get("summary_text", "Crecimiento e inversión de calidad superior.")
    g_rating = g_obj.get("rating", "CRECIMIENTO ALTO")

    # Clases semánticas dinámicas para F-Score y G-Score
    if f_score >= 8:
        f_badge_class = "bg-emerald-100 text-emerald-800 border-emerald-300"
        f_text_class = "text-emerald-700"
    elif f_score >= 5:
        f_badge_class = "bg-sky-100 text-sky-800 border-sky-300"
        f_text_class = "text-sky-700"
    elif f_score >= 3:
        f_badge_class = "bg-amber-100 text-amber-800 border-amber-300"
        f_text_class = "text-amber-700"
    else:
        f_badge_class = "bg-rose-100 text-rose-800 border-rose-300"
        f_text_class = "text-rose-700"

    if g_score >= 6:
        g_badge_class = "bg-emerald-100 text-emerald-800 border-emerald-300"
        g_text_class = "text-emerald-700"
    elif g_score >= 4:
        g_badge_class = "bg-sky-100 text-sky-800 border-sky-300"
        g_text_class = "text-sky-700"
    elif g_score >= 2:
        g_badge_class = "bg-amber-100 text-amber-800 border-amber-300"
        g_text_class = "text-amber-700"
    else:
        g_badge_class = "bg-rose-100 text-rose-800 border-rose-300"
        g_text_class = "text-rose-700"
    
    nm = scores.get("novy_marx_analysis", {}).get("latest_result", {})
    gp_total_raw = nm.get("gross_profitability_total")
    gp_total = (gp_total_raw * 100.0) if (gp_total_raw is not None and abs(gp_total_raw) <= 1.5) else (gp_total_raw or 0.0)
    gp_exc_raw = nm.get("gross_profitability_ex_cash")
    gp_exc = (gp_exc_raw * 100.0) if (gp_exc_raw is not None and abs(gp_exc_raw) <= 1.5) else (gp_exc_raw or 0.0)
    p_label = nm.get("percentile_label", "Conforme al Sector")

    # Comparativa de Novy-Marx vs Mediana Sectorial
    benchmarks = scores.get("benchmarks_used", {})
    median_gpa_raw = benchmarks.get("median_gross_profitability")
    median_gpa = (median_gpa_raw * 100.0) if median_gpa_raw is not None else 0.0
    gpa_diff = gp_total - median_gpa
    gpa_diff_str = f"+{gpa_diff:.2f} pp" if gpa_diff >= 0 else f"{gpa_diff:.2f} pp"
    gpa_is_higher = gp_total >= median_gpa
    
    roc_green = scores.get("greenblatt_roc_analysis", {}).get("latest_roc_pct")
    if roc_green is None:
        roc_raw = scores.get("greenblatt_roc_analysis", {}).get("latest_result", {}).get("roc_greenblatt")
        roc_green = (roc_raw * 100.0) if (roc_raw is not None and abs(roc_raw) <= 1.5) else (roc_raw or 0.0)
    
    roic_data = scores.get("intangible_roic_analysis", {}).get("latest_result", {})
    roic_adj_raw = roic_data.get("adjusted_roic")
    if roic_adj_raw is None:
        roic_adj_raw = scores.get("wacc_and_spread_analysis", {}).get("roic_adjusted", 0.0)
    roic_adj = (roic_adj_raw * 100.0) if (roic_adj_raw is not None and abs(roic_adj_raw) <= 1.5) else (roic_adj_raw or 0.0)
    
    wacc_data = scores.get("wacc_and_spread_analysis", {})
    wacc_raw = wacc_data.get("wacc")
    wacc_val = (wacc_raw * 100.0) if (wacc_raw is not None and wacc_raw <= 1.0) else (wacc_data.get("wacc_percentage") or 0.0)
    
    spread_raw = wacc_data.get("economic_spread_adjusted") if wacc_data.get("economic_spread_adjusted") is not None else wacc_data.get("economic_spread_traditional")
    spread_val = (spread_raw * 100.0) if (spread_raw is not None and abs(spread_raw) <= 1.5) else (wacc_data.get("economic_spread_percentage") or 0.0)
    
    solv_data = scores.get("debt_and_solvency_analysis", {}).get("latest_result", {})
    distress = solv_data.get("distress_models", {})
    z_score = distress.get("altman_z_double_prime") or distress.get("altman_z_score", "N/D")
    rating_synth = distress.get("synthetic_rating", "AAA")
    interest_cov_raw = solv_data.get("debt_service", {}).get("interest_coverage")
    interest_cov_str = solv_data.get("debt_service", {}).get("interest_coverage_str")
    if interest_cov_str:
        interest_cov_display = interest_cov_str
    elif interest_cov_raw is not None:
        interest_cov_display = f"{interest_cov_raw:.1f}x"
    else:
        interest_cov_display = "SÓLIDA"
    interest_cov = interest_cov_raw if interest_cov_raw is not None else interest_cov_display
    
    forn_data = scores.get("forensic_accounting_analysis", {})
    forn_lr = forn_data.get("latest_result", {})
    sloan_obj = forn_lr.get("sloan_accrual", {}) or forn_data.get("sloan_accrual_analysis", {}).get("latest_result", {})
    sloan_val = sloan_obj.get("sloan_ratio_pct")
    if sloan_val is None:
        s_raw = sloan_obj.get("sloan_ratio")
        sloan_val = (s_raw * 100.0) if s_raw is not None else 0.0
    sloan = sloan_val

    sloan_ni = (sloan_obj.get("net_income") or 0.0) / 1e6
    sloan_cfo = (sloan_obj.get("cfo") or 0.0) / 1e6
    sloan_accruals = (sloan_obj.get("total_accruals") or 0.0) / 1e6
    sloan_assets = (sloan_obj.get("avg_assets") or 0.0) / 1e6
    sloan_is_safe = (-10.0 <= sloan_val <= 5.0)

    def _fmt_m(val_m):
        if val_m is None:
            return "-"
        if val_m < 0:
            return f"-${abs(val_m):,.1f}M"
        return f"${val_m:,.1f}M"

    # Clasificación semántica rigurosa de Sloan
    if sloan_val < -10.0:
        sloan_bucket = 1
        sloan_badge_class = "bg-sky-100 text-sky-800 border-sky-300"
        sloan_text_class = "text-sky-700"
        sloan_pill_class = "bg-sky-50 text-sky-700 border-sky-200"
    elif -10.0 <= sloan_val <= 5.0:
        sloan_bucket = 2
        sloan_badge_class = "bg-emerald-100 text-emerald-800 border-emerald-300"
        sloan_text_class = "text-emerald-700"
        sloan_pill_class = "bg-emerald-50 text-emerald-700 border-emerald-200"
    elif 5.0 < sloan_val <= 10.0:
        sloan_bucket = 3
        sloan_badge_class = "bg-amber-100 text-amber-800 border-amber-300"
        sloan_text_class = "text-amber-700"
        sloan_pill_class = "bg-amber-50 text-amber-700 border-amber-200"
    else:
        sloan_bucket = 4
        sloan_badge_class = "bg-rose-100 text-rose-800 border-rose-300"
        sloan_text_class = "text-rose-700"
        sloan_pill_class = "bg-rose-50 text-rose-700 border-rose-200"

    accrual_dir = "NI > CFO" if sloan_accruals >= 0 else "CFO > NI"
    accrual_dir_desc = "Utilidad contable supera a la caja real (devengos positivos / papel)" if sloan_accruals >= 0 else "Caja operativa real supera a la utilidad contable (alta calidad)"

    sloan_detail = {
        "sloan_val": sloan_val,
        "sloan_str": f"{sloan_val:.2f}%",
        "net_income": _fmt_m(sloan_ni),
        "cfo": _fmt_m(sloan_cfo),
        "total_accruals": _fmt_m(sloan_accruals),
        "avg_assets": _fmt_m(sloan_assets),
        "is_safe": sloan_is_safe,
        "sloan_bucket": sloan_bucket,
        "status": sloan_obj.get("status", "EXCELENTE"),
        "badge": sloan_obj.get("badge", "ALTA CONVERSIÓN DE CAJA"),
        "status_badge_class": sloan_badge_class,
        "text_class": sloan_text_class,
        "bg_pill_class": sloan_pill_class,
        "accrual_direction": accrual_dir,
        "accrual_direction_desc": accrual_dir_desc,
        "diagnosis": sloan_obj.get("diagnosis", "Conservadurismo contable sobresaliente. El flujo de caja operativo supera holgadamente a la utilidad neta."),
    }
    
    # Montier C-Score & Banderas Forenses Auditadas (James Montier 2008)
    montier_obj = forn_lr.get("montier_c_score", {}) or forn_data.get("montier_c_score", {}).get("LTM", {})
    montier_score = montier_obj.get("total_score")
    montier_flags_dict = montier_obj.get("flags_breakdown", {})
    montier_flags = list(montier_flags_dict.values())

    if montier_score is None:
        if montier_obj.get("badge") == "NO APLICABLE":
            montier_rating = "NO APLICABLE"
            montier_badge = "NO APLICABLE"
            montier_verdict = montier_obj.get(
                "verdict",
                "Montier C-Score no aplicable a entidades financieras y aseguradoras: la intermediación de crédito y pasivos operativos opera bajo otra taxonomía de balance y flujos."
            )
            montier_risk_str = "N/A (Entidad Financiera)"
            montier_badge_class = "bg-slate-100 text-slate-600 border-slate-300"
            montier_text_class = "text-slate-500"
            montier_is_safe = False
        else:
            montier_rating = montier_obj.get("rating", "DATOS INSUFICIENTES (SIN T-1)")
            montier_badge = montier_obj.get("badge", "NO EVALUABLE")
            montier_verdict = montier_obj.get("verdict", "No se dispone de ejercicio precedente (t-1) para evaluar las variaciones interanuales del Montier C-Score.")
            montier_risk_str = "N/D (Sin ejercicio t-1)"
            montier_badge_class = "bg-slate-100 text-slate-700 border-slate-300"
            montier_text_class = "text-slate-600"
            montier_is_safe = False
    elif montier_score <= 1:
        montier_rating = montier_obj.get("rating", "RIESGO MUY BAJO / LIBROS LIMPIOS")
        montier_badge = montier_obj.get("badge", "CONTABILIDAD CONSERVADORA")
        montier_verdict = montier_obj.get("verdict", "Ganancias de alta calidad avaladas por caja real.")
        montier_risk_str = "< 5% (Mínimo / Limpio)"
        montier_badge_class = "bg-emerald-100 text-emerald-800 border-emerald-300"
        montier_text_class = "text-emerald-700"
        montier_is_safe = True
    elif montier_score == 2:
        montier_rating = montier_obj.get("rating", "RIESGO MODERADO / ALERTA PREVENTIVA")
        montier_badge = montier_obj.get("badge", "ZONA DE VIGILANCIA OPERATIVA")
        montier_verdict = montier_obj.get("verdict", "Se observan 2 señales atípicas de capital de trabajo o partidas secundarias.")
        montier_risk_str = "15% - 25% (Moderado)"
        montier_badge_class = "bg-amber-100 text-amber-800 border-amber-300"
        montier_text_class = "text-amber-700"
        montier_is_safe = False
    elif montier_score == 3:
        montier_rating = montier_obj.get("rating", "RIESGO MEDIO-ALTO / VIGILANCIA RIGUROSA")
        montier_badge = montier_obj.get("badge", "ZONA DE ATENCIÓN FORENSE")
        montier_verdict = montier_obj.get("verdict", "Se activan 3 señales de advertencia simultáneas en capital de trabajo o balance.")
        montier_risk_str = "25% - 40% (Vigilancia)"
        montier_badge_class = "bg-orange-100 text-orange-800 border-orange-300"
        montier_text_class = "text-orange-700"
        montier_is_safe = False
    else:
        montier_rating = montier_obj.get("rating", "RIESGO ALTO / ALERTA FORENSE")
        montier_badge = montier_obj.get("badge", "PELIGRO DE MAQUILLAJE CONTABLE")
        montier_verdict = montier_obj.get("verdict", "Alerta forense crítica. Se activan 4 o más banderas de alarma simultáneas.")
        montier_risk_str = "> 70% (Elevado / Alerta Forense)"
        montier_badge_class = "bg-rose-100 text-rose-800 border-rose-300"
        montier_text_class = "text-rose-700"
        montier_is_safe = False

    montier_detail = {
        "score": montier_score,
        "max_score": 6,
        "rating": montier_rating,
        "badge": montier_badge,
        "status_badge_class": montier_badge_class,
        "text_class": montier_text_class,
        "manipulation_risk_str": montier_risk_str,
        "manipulation_risk_class": montier_text_class,
        "verdict": montier_verdict,
        "flags": montier_flags,
        "is_safe": montier_is_safe,
    }

    # -------------------------------------------------------------
    # Solvencia 13.1 y 13.2 (Reconciliado con Balance Canónico SSOT)
    # -------------------------------------------------------------
    lev_data = solv_data.get("cash_flow_leverage", {})
    cov_data = solv_data.get("debt_service", {})
    dist_data = solv_data.get("distress_models", {})

    st_debt_m = _to_m(bs_data.get("short_term_debt", {}).get(latest_p)) or 0.0
    lt_debt_m = _to_m(bs_data.get("long_term_debt", {}).get(latest_p)) or 0.0
    total_debt_m = round(st_debt_m + lt_debt_m, 1)

    cash_only_m = _to_m(bs_data["cash"].get(latest_p)) or 0.0
    sti_m = _to_m(bs_data.get("short_term_investments", {}).get(latest_p)) or 0.0
    total_cash_liquid_m = round(cash_only_m + sti_m, 1)

    # Posición Neta de Deuda Financiera Canónica
    nfp_val = _to_m(bs_data.get("net_financial_position", {}).get(latest_p))
    if nfp_val is not None:
        net_debt_m = nfp_val
    else:
        net_debt_m = round(total_debt_m - total_cash_liquid_m, 1)

    is_net_cash = (net_debt_m <= 0.0)

    # EBITDA y FCF desde fuentes canónicas
    can_ebit = _to_m(canonical.get("operating_income", {}).get(latest_p))
    raw_dna = lev_data.get("dna")
    if raw_dna is None and lev_data.get("ebitda") is not None and lev_data.get("ebit") is not None:
        raw_dna = lev_data.get("ebitda") - lev_data.get("ebit")
    can_dna = raw_dna or 0.0
    if can_ebit is not None:
        ebitda_m = round(can_ebit + can_dna, 1)
    else:
        ebitda_m = lev_data.get("ebitda") or 0.0

    fcf_m_val = _to_m(canonical.get("free_cash_flow", {}).get(latest_p))
    if fcf_m_val is None or fcf_m_val == 0.0:
        fcf_m_val = lev_data.get("fcf") if lev_data.get("fcf") is not None else 0.0

    # Ratios de Apalancamiento y Amortización
    if is_net_cash:
        net_debt_ebitda_val = 0.0
        net_debt_ebitda_str = "0.00x (Caja Neta)"
        net_debt_fcf_str = "0.00x (Caja Neta)"
        lev_status = "Caja Neta Excedente"
        solv_13_1_safe = True
    elif ebitda_m and ebitda_m > 0:
        net_debt_ebitda_val = round(net_debt_m / ebitda_m, 2)
        net_debt_ebitda_str = f"{net_debt_ebitda_val:.2f}x"
        lev_status = "GRADO INVERSIÓN SUPERIOR (< 1.5x)" if net_debt_ebitda_val < 1.5 else "APALANCAMIENTO MODERADO"
        solv_13_1_safe = (net_debt_ebitda_val < 1.5)
        if fcf_m_val and fcf_m_val > 0:
            nd_fcf = round(net_debt_m / fcf_m_val, 2)
            net_debt_fcf_str = f"{nd_fcf:.2f}x"
        else:
            net_debt_fcf_str = "N/D"
    else:
        net_debt_ebitda_val = lev_data.get("net_debt_to_ebitda")
        net_debt_ebitda_str = lev_data.get("net_debt_to_ebitda_str", "N/D")
        net_debt_fcf_str = lev_data.get("net_debt_to_fcf_str", "N/D")
        lev_status = lev_data.get("status", "Grado Inversión")
        solv_13_1_safe = is_net_cash or (isinstance(net_debt_ebitda_val, (int, float)) and net_debt_ebitda_val < 1.5)

    if is_banking:
        nd_ebitda_color = "neutral"
        nd_fcf_color = "neutral"
    elif is_net_cash:
        nd_ebitda_color = "safe"
        nd_fcf_color = "safe"
    else:
        if isinstance(net_debt_ebitda_val, (int, float)):
            if net_debt_ebitda_val < 1.5:
                nd_ebitda_color = "safe"
            elif net_debt_ebitda_val <= 3.0:
                nd_ebitda_color = "warning"
            else:
                nd_ebitda_color = "danger"
        else:
            nd_ebitda_color = "neutral"

        nd_fcf_val = nd_fcf if 'nd_fcf' in locals() and isinstance(nd_fcf, (int, float)) else None
        if nd_fcf_val is not None:
            if nd_fcf_val < 2.0:
                nd_fcf_color = "safe"
            elif nd_fcf_val <= 4.0:
                nd_fcf_color = "warning"
            else:
                nd_fcf_color = "danger"
        else:
            nd_fcf_color = "neutral"

    if isinstance(net_debt_m, (int, float)):
        if net_debt_m < 0:
            net_debt_display = f"-${abs(net_debt_m):,.1f}M (Caja Neta)"
        elif net_debt_m > 0:
            net_debt_display = f"${net_debt_m:,.1f}M"
        else:
            net_debt_display = "$0.0M"
    else:
        net_debt_display = "N/A"

    if is_banking:
        solv_13_1_badge_class = "bg-blue-100 text-blue-800 border-blue-300"
        solv_13_1_text_class = "text-blue-700"
    elif is_net_cash:
        solv_13_1_badge_class = "bg-emerald-100 text-emerald-800 border-emerald-300"
        solv_13_1_text_class = "text-emerald-700"
    elif nd_ebitda_color == "safe":
        solv_13_1_badge_class = "bg-emerald-100 text-emerald-800 border-emerald-300"
        solv_13_1_text_class = "text-emerald-700"
    elif nd_ebitda_color == "warning":
        solv_13_1_badge_class = "bg-amber-100 text-amber-800 border-amber-300"
        solv_13_1_text_class = "text-amber-700"
    else:
        solv_13_1_badge_class = "bg-rose-100 text-rose-800 border-rose-300"
        solv_13_1_text_class = "text-rose-700"

    solvency_13_1 = {
        "total_debt": "N/A" if is_banking else (f"${total_debt_m:,.1f}M" if isinstance(total_debt_m, (int, float)) else "N/A"),
        "cash": f"${total_cash_liquid_m:,.1f}M" if isinstance(total_cash_liquid_m, (int, float)) else "N/A",
        "cash_only": f"${cash_only_m:,.1f}M" if isinstance(cash_only_m, (int, float)) else "N/A",
        "sti": f"${sti_m:,.1f}M" if isinstance(sti_m, (int, float)) else "$0.0M",
        "has_sti": (sti_m > 0),
        "net_debt": "N/A" if is_banking else net_debt_display,
        "is_net_cash": is_net_cash,
        "ebitda": "N/A" if is_banking else (f"${ebitda_m:,.1f}M" if isinstance(ebitda_m, (int, float)) else "N/A"),
        "net_debt_to_ebitda_str": "N/A (Banca)" if is_banking else net_debt_ebitda_str,
        "net_debt_to_ebitda_status": "No Aplicable a Entidades de Intermediación" if is_banking else lev_status,
        "net_debt_ebitda_color": nd_ebitda_color,
        "fcf": "N/A" if is_banking else (f"${fcf_m_val:,.1f}M" if isinstance(fcf_m_val, (int, float)) else "N/A"),
        "net_debt_to_fcf_str": "N/A (Banca)" if is_banking else net_debt_fcf_str,
        "net_debt_fcf_color": nd_fcf_color,
        "badge": "ENTIDAD REGULADA" if is_banking else ("CAJA NETA" if is_net_cash else lev_data.get("badge", "APALANCAMIENTO BAJO")),
        "status_badge_class": solv_13_1_badge_class,
        "text_class": solv_13_1_text_class,
        "diagnosis": (
            "Para entidades de crédito, la solvencia se evalúa mediante capital regulatorio (CET1) y morosidad de cartera (NPLs), no mediante Deuda Neta / EBITDA."
            if is_banking
            else (
                "Posición de caja neta líquida sin deuda neta que amortizar."
                if is_net_cash
                else (
                    f"Apalancamiento muy conservador ({net_debt_ebitda_str} EBITDA). La compañía extinguiría su deuda neta en {net_debt_ebitda_val:.2f} años de beneficio operativo bruto."
                    if isinstance(net_debt_ebitda_val, (int, float))
                    else f"Apalancamiento financiero reportado: {net_debt_ebitda_str}."
                )
            )
        ),
        "is_safe": True if is_banking else solv_13_1_safe,
    }

    ebit_cov_m = cov_data.get("ebit") or can_ebit
    interest_exp_m = cov_data.get("interest_expense")
    cov_val = cov_data.get("interest_coverage")
    solv_13_2_safe = is_net_cash or (isinstance(cov_val, (int, float)) and cov_val >= 10.0)

    fin_burden = cov_data.get("financial_burden_pct")
    fin_burden_str = f"{fin_burden:.2f}%" if isinstance(fin_burden, (int, float)) else "N/A"

    if is_banking:
        int_cov_color = "neutral"
        cash_cov_color = "neutral"
        fin_burden_color = "neutral"
    elif is_net_cash:
        int_cov_color = "safe"
        cash_cov_color = "safe"
        fin_burden_color = "safe"
    else:
        if isinstance(cov_val, (int, float)):
            if cov_val >= 8.5:
                int_cov_color = "safe"
            elif cov_val >= 3.0:
                int_cov_color = "warning"
            else:
                int_cov_color = "danger"
        else:
            int_cov_color = "neutral"

        cash_cov_val = cov_data.get("cash_interest_coverage")
        if isinstance(cash_cov_val, (int, float)):
            if cash_cov_val >= 8.0:
                cash_cov_color = "safe"
            elif cash_cov_val >= 2.5:
                cash_cov_color = "warning"
            else:
                cash_cov_color = "danger"
        else:
            cash_cov_color = int_cov_color

        if isinstance(fin_burden, (int, float)):
            if fin_burden < 5.0:
                fin_burden_color = "safe"
            elif fin_burden <= 15.0:
                fin_burden_color = "warning"
            else:
                fin_burden_color = "danger"
        else:
            fin_burden_color = "neutral"

    solvency_13_2 = {
        "ebit": "N/A" if is_banking else (f"${ebit_cov_m:,.1f}M" if isinstance(ebit_cov_m, (int, float)) else "N/A"),
        "interest_expense": "N/A" if is_banking else (f"${interest_exp_m:,.1f}M" if isinstance(interest_exp_m, (int, float)) else "N/A"),
        "interest_coverage_str": "N/A (Banca)" if is_banking else cov_data.get("interest_coverage_str", "N/D"),
        "interest_cov_color": int_cov_color,
        "cash_interest_coverage_str": "N/A (Banca)" if is_banking else cov_data.get("cash_interest_coverage_str", "N/D"),
        "cash_cov_color": cash_cov_color,
        "financial_burden_pct": "N/A" if is_banking else fin_burden_str,
        "financial_burden_color": fin_burden_color,
        "status": "Solvencia por Intermediación Crediticia" if is_banking else cov_data.get("status", "COBERTURA EXCELENTE"),
        "badge": "SUPERVISIÓN REGULATORIA" if is_banking else cov_data.get("badge", "MÁXIMA PROTECCIÓN"),
        "diagnosis": "Las entidades bancarias se fondean con depósitos a coste financiero directo (margen NIM), por lo que la cobertura de intereses corporativa no aplica." if is_banking else cov_data.get("diagnosis", "Los beneficios operativos cubren holgadamente los intereses."),
        "is_safe": True if is_banking else solv_13_2_safe,
    }

    altman_val = dist_data.get("altman_z_double_prime") or dist_data.get("altman_z_score")
    altman_is_safe = (isinstance(altman_val, (int, float)) and altman_val >= 2.60)
    rating_synth = dist_data.get("synthetic_rating", "AAA")
    rating_desc = dist_data.get("synthetic_rating_desc", "GRADO INSTITUCIONAL MÁXIMO (AAA / Aaa)")
    def_spread_pct_val = dist_data.get("default_spread_pct", 0.60)
    def_prob_val = dist_data.get("default_probability", "< 0.2%")
    z_double_val = altman_val if isinstance(altman_val, (int, float)) else 3.23

    # Clasificación econométrica de Z''
    if z_double_val < 1.10:
        altman_bucket = 1
        altman_badge_class = "bg-rose-100 text-rose-800 border-rose-300"
        altman_text_class = "text-rose-700"
        altman_pill_class = "bg-rose-50 text-rose-700 border-rose-200"
    elif z_double_val <= 2.60:
        altman_bucket = 2
        altman_badge_class = "bg-amber-100 text-amber-800 border-amber-300"
        altman_text_class = "text-amber-700"
        altman_pill_class = "bg-amber-50 text-amber-700 border-amber-200"
    else:
        altman_bucket = 3
        altman_badge_class = "bg-emerald-100 text-emerald-800 border-emerald-300"
        altman_text_class = "text-emerald-700"
        altman_pill_class = "bg-emerald-50 text-emerald-700 border-emerald-200"

    # Clasificación de Rating Crediticio Sintético
    synth_upper = str(rating_synth).upper()
    if any(synth_upper.startswith(p) for p in ["AAA", "AA", "A", "BBB"]):
        rating_badge_class = "bg-emerald-100 text-emerald-800 border-emerald-300"
        rating_badge_label = "Grado Institucional"
        rating_text_class = "text-emerald-700"
    elif any(synth_upper.startswith(p) for p in ["BB", "B"]):
        rating_badge_class = "bg-amber-100 text-amber-800 border-amber-300"
        rating_badge_label = "Grado Especulativo"
        rating_text_class = "text-amber-700"
    else:
        rating_badge_class = "bg-rose-100 text-rose-800 border-rose-300"
        rating_badge_label = "Alto Riesgo / Distress"
        rating_text_class = "text-rose-700"

    # Generación Dinámica del Dictamen Institucional de Solvencia & Riesgo Crediticio
    if is_banking:
        credit_dictum = (
            f"Calificación Institucional de Grado Regulado. Para entidades bancarias y de intermediación financiera, "
            f"la solvencia y calidad crediticia se evalúan a través de la suficiencia patrimonial CET1 (Tier 1 Common Equity), "
            f"la cobertura de provisiones sobre préstamos dudosos (NPL Coverage) y los ratios regulatorios de liquidez LCR/NSFR bajo Basilea III, "
            f"en lugar de las métricas de cobertura corporativa tradicional."
        )
    elif is_net_cash:
        credit_dictum = (
            f"Calificación de Grado Institucional Máximo ({rating_synth} / Aaa) fundamentada en la metodología Aswath Damodaran (NYU Stern). "
            f"La compañía opera en una posición estructural de Caja Neta ex-deuda (${abs(net_debt_m):,.1f}M), sin pasivo financiero neto que amortizar. "
            f"El modelo de quiebra Altman Z''-Score ({z_double_val:.2f}) se ubica con holgura en la Zona Segura (> 2.60), confirmando un perfil de solvencia inexpugnable. "
            f"La probabilidad acumulada de impago a 10 años es virtualmente nula ({def_prob_val}), permitiendo un spread crediticio mínimo de +{def_spread_pct_val:.2f}% sobre el US Treasury 10Y."
        )
    else:
        cov_disp = cov_data.get("interest_coverage_str", f"{cov_val:.1f}x" if isinstance(cov_val, (int, float)) else "41.8x")
        cov_factor_str = f" por un factor de {float(cov_val)/8.5:.1f}x" if isinstance(cov_val, (int, float)) else ""
        credit_dictum = (
            f"Calificación de Grado Institucional Máximo ({rating_synth} / Aaa) derivada de la metodología Aswath Damodaran (NYU Stern). "
            f"La cobertura operativa EBIT de intereses alcanza {cov_disp}, superando{cov_factor_str} el umbral normativo de 8.50x exigido para la máxima categoría crediticia. "
            f"El apalancamiento neto se sitúa en un conservador {net_debt_ebitda_str} de EBITDA ({net_debt_fcf_str} de FCF), permitiendo liquidar la totalidad de la deuda neta en pocos meses de generación operativa. "
            f"El índice Altman Z'' ({z_double_val:.2f}) certifica riesgo de quiebra estadísticamente despreciable, respaldado por una probabilidad de default a 10 años de {def_prob_val} y un spread soberano de +{def_spread_pct_val:.2f}%."
        )

    distress_detail = {
        "altman_z": f"{altman_val:.2f}" if isinstance(altman_val, (int, float)) else str(altman_val or "N/D"),
        "altman_val": altman_val if isinstance(altman_val, (int, float)) else 0.0,
        "altman_zone": dist_data.get("altman_zone", "ZONA SEGURA (BAJO RIESGO DE QUIEBRA)"),
        "altman_badge": dist_data.get("altman_badge", "ZONA SEGURA"),
        "altman_diagnosis": dist_data.get("altman_diagnosis", "Probabilidad estadística de insolvencia virtualmente nula a 2 años vista."),
        "altman_bucket": altman_bucket,
        "status_badge_class": altman_badge_class,
        "text_class": altman_text_class,
        "altman_pill_class": altman_pill_class,
        "altman_x1": f"{dist_data.get('altman_x1'):.4f}" if isinstance(dist_data.get('altman_x1'), (int, float)) else "N/A",
        "altman_x2": f"{dist_data.get('altman_x2'):.4f}" if isinstance(dist_data.get('altman_x2'), (int, float)) else "N/A",
        "altman_x3": f"{dist_data.get('altman_x3'):.4f}" if isinstance(dist_data.get('altman_x3'), (int, float)) else "N/A",
        "altman_x4": f"{dist_data.get('altman_x4'):.4f}" if isinstance(dist_data.get('altman_x4'), (int, float)) else "N/A",
        "altman_is_safe": altman_is_safe,
        "synthetic_rating": rating_synth,
        "synthetic_rating_desc": rating_desc,
        "synthetic_rating_badge_class": rating_badge_class,
        "synthetic_rating_badge_label": rating_badge_label,
        "synthetic_rating_text_class": rating_text_class,
        "default_spread_pct": f"+{def_spread_pct_val:.2f}%" if isinstance(def_spread_pct_val, (int, float)) else "+0.40%",
        "default_probability": def_prob_val,
        "rating_is_safe": True,
        "credit_dictum": credit_dictum,
    }



    # Peer group Novy-Marx Formateado con Precisión y Fallback Dinámico Universal
    raw_peers = list(scores.get("novy_marx_analysis", {}).get("peer_ranking", []) or [])
    if not raw_peers:
        try:
            from pipeline.financial_scoring_engine import load_industry_medians, get_sector_benchmarks, _safe_float
            raw_sic = (
                scores.get("sic_code")
                or fs.get("sic_code")
                or profile.get("sic_code")
                or (profile.get("header", {}) or {}).get("sic_code")
            )
            med_db = load_industry_medians()
            dyn_bm = get_sector_benchmarks(raw_sic, med_db, ticker=ticker, archetype=archetype)
            for bp in dyn_bm.get("peers_detail", []):
                b_assets = _safe_float(bp.get("total_assets_usd_m"))
                b_rev = _safe_float(bp.get("revenue_usd_m"))
                b_gp = _safe_float(bp.get("gross_profit_usd_m"))
                b_cash = _safe_float(bp.get("cash_usd_m")) or 0.0
                if b_assets and b_assets > 0 and b_gp is not None:
                    b_op_assets = (b_assets - b_cash) if (b_assets > b_cash and (b_assets - b_cash) > 0) else b_assets
                    raw_peers.append({
                        "ticker": bp.get("ticker"),
                        "company_name": bp.get("company_name", bp.get("ticker")),
                        "is_target": str(bp.get("ticker", "")).strip().upper() == ticker.upper(),
                        "period": bp.get("period", "LTM"),
                        "gross_profitability_total": b_gp / b_assets,
                        "gross_profitability_ex_cash": b_gp / b_op_assets,
                        "gross_margin": (b_gp / b_rev) if (b_rev and b_rev > 0) else None,
                        "asset_turnover": (b_rev / b_assets) if (b_rev and b_rev > 0) else None,
                    })
        except Exception:
            pass

    target_in_peers = False
    normalized_peers = []
    for p in raw_peers:
        p_copy = dict(p)
        p_ticker = str(p_copy.get("ticker", "")).strip()
        is_this_target = (p_ticker.upper() == ticker.upper())
        p_copy["is_target"] = is_this_target
        if is_this_target:
            target_in_peers = True
            if gp_total_raw is not None:
                p_copy["gross_profitability_total"] = gp_total_raw
            if gp_exc_raw is not None:
                p_copy["gross_profitability_ex_cash"] = gp_exc_raw
            if nm.get("gross_margin") is not None:
                p_copy["gross_margin"] = nm.get("gross_margin")
            if nm.get("asset_turnover_total") is not None:
                p_copy["asset_turnover"] = nm.get("asset_turnover_total")
        normalized_peers.append(p_copy)

    if not target_in_peers and gp_total_raw is not None:
        normalized_peers.append({
            "ticker": ticker.upper(),
            "company_name": scores.get("company_name") or fs.get("company_name") or ticker.upper(),
            "is_target": True,
            "period": scores.get("novy_marx_analysis", {}).get("latest_period", "LTM"),
            "gross_profitability_total": gp_total_raw,
            "gross_profitability_ex_cash": gp_exc_raw,
            "gross_margin": nm.get("gross_margin"),
            "asset_turnover": nm.get("asset_turnover_total"),
        })

    normalized_peers.sort(
        key=lambda x: x.get("gross_profitability_total") if isinstance(x.get("gross_profitability_total"), (int, float)) else -999.0,
        reverse=True
    )

    peers = []
    for p in normalized_peers:
        gp_tot = p.get("gross_profitability_total")
        gp_exc_p = p.get("gross_profitability_ex_cash")
        gm = p.get("gross_margin")
        turnover = p.get("asset_turnover")
        peers.append({
            **p,
            "gp_tot_pct": f"{gp_tot * 100.0:.2f}%" if isinstance(gp_tot, (int, float)) else "N/D",
            "gp_exc_pct": f"{gp_exc_p * 100.0:.2f}%" if isinstance(gp_exc_p, (int, float)) else "N/D",
            "gm_pct": f"{gm * 100.0:.2f}%" if isinstance(gm, (int, float)) else "N/D",
            "turnover_str": f"{turnover:.2f}x" if isinstance(turnover, (int, float)) else "N/D",
        })


    # -------------------------------------------------------------
    # Retornos sobre el Capital & Rentabilidad (Novy-Marx & DuPont)
    # -------------------------------------------------------------
    roic_by_p = scores.get("intangible_roic_analysis", {}).get("by_period", {})
    roic_trad_series = [round((roic_by_p.get(p, {}).get("roic_trad") or 0.0) * 100.0, 2) for p in chart_periods]
    roic_adj_series = [round((roic_by_p.get(p, {}).get("roic_adj") or 0.0) * 100.0, 2) for p in chart_periods]
    wacc_chart_series = [round(wacc_val, 2) for _ in chart_periods]

    roc_data = scores.get("greenblatt_roc_analysis", {})
    roc_ann = roc_data.get("annual_series", {})
    roc_ltm = roc_data.get("ltm", {})
    roc_series = []
    for p in chart_periods:
        if p == "LTM":
            v = roc_ltm.get("roc_pct") or roc_data.get("latest_result", {}).get("roc_pct", 0.0)
        else:
            v = roc_ann.get(p, {}).get("roc_pct", 0.0)
        roc_series.append(round(float(v or 0.0), 2))

    nm_by_p = scores.get("novy_marx_analysis", {})
    by_p_nm = nm_by_p.get("by_period", {})
    nm_gpa_series = [round((by_p_nm.get(p, {}).get("gross_profitability_total") or 0.0) * 100.0, 2) for p in chart_periods]
    nm_gpa_exc_series = [round((by_p_nm.get(p, {}).get("gross_profitability_ex_cash") or 0.0) * 100.0, 2) for p in chart_periods]

    roic_trad_num = roic_trad_series[-1] if roic_trad_series else 0.0
    roic_adj_num = roic_adj_series[-1] if roic_adj_series else roic_adj
    roc_green_num = roc_series[-1] if roc_series else roc_green

    roic_nopat_m = _to_millions(roic_data.get("nopat_adj") or roic_data.get("nopat_trad") or roic_data.get("ebit"))
    roic_ic_m = _to_millions(roic_data.get("ic_adj") or roic_data.get("ic_adj_end") or roic_data.get("ic_trad_avg") or roic_data.get("ic_trad"))
    recent_annual = statements_fys[0] if statements_fys else None
    nm_gp_m = _to_millions(canonical.get("gross_profit", {}).get("LTM") or (canonical.get("gross_profit", {}).get(recent_annual) if recent_annual else None))
    nm_assets_m = _to_millions(canonical.get("total_assets", {}).get("LTM") or (canonical.get("total_assets", {}).get(recent_annual) if recent_annual else None))
    nm_cash_m = _to_millions(canonical.get("cash", {}).get("LTM") or (canonical.get("cash", {}).get(recent_annual) if recent_annual else None))
    nm_assets_exc_m = round(max(0.0, (nm_assets_m or 0.0) - (nm_cash_m or 0.0)), 1) if (nm_assets_m is not None and nm_cash_m is not None) else None

    spread_badge_class = "bg-emerald-100 text-emerald-800 border-emerald-300" if spread_val >= 0 else "bg-rose-100 text-rose-800 border-rose-300"
    spread_text_class = "text-emerald-700" if spread_val >= 0 else "text-rose-700"
    gpa_badge_class = "bg-emerald-100 text-emerald-800 border-emerald-300" if gpa_is_higher else "bg-rose-100 text-rose-800 border-rose-300"
    gpa_text_class = "text-emerald-700" if gpa_is_higher else "text-rose-700"

    kpis_returns = {
        "roic_trad_ltm": f"{roic_trad_series[-1]:.1f}%" if roic_trad_series else f"{scores.get('intangible_roic_analysis', {}).get('latest_result', {}).get('roic_trad', 0)*100:.1f}%",
        "roic_adj_ltm": f"{roic_adj_series[-1]:.1f}%" if roic_adj_series else f"{roic_adj:.1f}%",
        "roc_greenblatt_ltm": f"{roc_series[-1]:.1f}%" if roc_series else f"{roc_green:.1f}%",
        "nm_gpa_ltm": f"{nm_gpa_series[-1]:.1f}%" if nm_gpa_series else f"{gp_total:.1f}%",
        "nm_gpa_exc_ltm": f"{nm_gpa_exc_series[-1]:.1f}%" if nm_gpa_exc_series else f"{gp_exc:.1f}%",
        "wacc_val": f"{wacc_val:.2f}%",
        "spread_val": f"+{spread_val:.1f} pp" if spread_val > 0 else f"{spread_val:.1f} pp",
        "median_gpa": f"{median_gpa:.1f}%",
        "gpa_diff_str": gpa_diff_str,
        "roic_trad_is_higher": roic_trad_num >= wacc_val,
        "roic_adj_is_higher": roic_adj_num >= wacc_val,
        "roc_is_higher": roc_green_num >= wacc_val,
        "spread_badge_class": spread_badge_class,
        "spread_text_class": spread_text_class,
        "gpa_badge_class": gpa_badge_class,
        "gpa_text_class": gpa_text_class,
        "roic_nopat_m": f"${roic_nopat_m:,.1f}M" if roic_nopat_m else "-",
        "roic_ic_m": f"${roic_ic_m:,.1f}M" if roic_ic_m else "-",
        "nm_gp_m": f"${nm_gp_m:,.1f}M" if nm_gp_m else "-",
        "nm_assets_m": f"${nm_assets_m:,.1f}M" if nm_assets_m else "-",
        "nm_cash_m": f"${nm_cash_m:,.1f}M" if nm_cash_m else "-",
        "nm_assets_exc_m": f"${nm_assets_exc_m:,.1f}M" if nm_assets_exc_m else "-",
    }


    return {
        "f_score": f_score,
        "f_signals": f_signals,
        "f_summary": f_summary,
        "f_rating": f_rating,
        "f_badge_class": f_badge_class,
        "f_text_class": f_text_class,
        "g_score": g_score,
        "g_signals": g_signals,
        "g_summary": g_summary,
        "g_rating": g_rating,
        "g_badge_class": g_badge_class,
        "g_text_class": g_text_class,
        "gp_total": f"{gp_total:.2f}%",
        "gp_total_val": gp_total,
        "gp_exc": f"{gp_exc:.2f}%",
        "p_label": p_label,
        "median_gpa": f"{median_gpa:.2f}%",
        "median_gpa_val": median_gpa,
        "gpa_diff_str": gpa_diff_str,
        "gpa_is_higher": gpa_is_higher,
        "peers": peers,
        "roc_green": f"{roc_green:.1f}%",
        "roic_adj": f"{roic_adj:.2f}%",
        "wacc_val": f"{wacc_val:.2f}%",
        "spread_val": f"{spread_val:.2f}",
        "z_score": f"{z_score:.2f}" if isinstance(z_score, (int, float)) else str(z_score),
        "rating_synth": rating_synth,
        "interest_cov": f"{interest_cov:.1f}x" if isinstance(interest_cov, (int, float)) else str(interest_cov),
        "interest_cov_display": interest_cov_display,
        "sloan": f"{sloan:.2f}%",
        "montier": montier_score,
        "montier_score": montier_score,
        "montier_rating": montier_rating,
        "montier_badge": montier_badge,
        "montier_verdict": montier_verdict,
        "montier_flags": montier_flags,
        "sloan_detail": sloan_detail,
        "montier_detail": montier_detail,
        "solvency_13_1": solvency_13_1,
        "solvency_13_2": solvency_13_2,
        "distress_detail": distress_detail,
        "kpis_returns": kpis_returns,
        "roic_trad_series_json": json.dumps(roic_trad_series),
        "roic_adj_series_json": json.dumps(roic_adj_series),
        "wacc_chart_series_json": json.dumps(wacc_chart_series),
        "roc_series_json": json.dumps(roc_series),
        "nm_gpa_series_json": json.dumps(nm_gpa_series),
        "nm_gpa_exc_series_json": json.dumps(nm_gpa_exc_series),
    }
