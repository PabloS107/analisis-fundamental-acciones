# -*- coding: utf-8 -*-
"""
Submódulo de Contabilidad Forense (Sloan & Montier) y Solvencia / Riesgo Crediticio.
Cumple estrictamente con Regla 6 (cero defaults ficticios) y dictámenes coherentes.
"""
from .view_utils import already_m, first_present, fmt_money_m, safe_float, usd_to_m

_SLATE_BADGE = "bg-slate-100 text-slate-700 border-slate-300"
_EMERALD_BADGE = "bg-emerald-100 text-emerald-800 border-emerald-300"
_SKY_BADGE = "bg-sky-100 text-sky-800 border-sky-300"
_AMBER_BADGE = "bg-amber-100 text-amber-800 border-amber-300"
_ORANGE_BADGE = "bg-orange-100 text-orange-800 border-orange-300"
_ROSE_BADGE = "bg-rose-100 text-rose-800 border-rose-300"

_MONTIER_SCORE_STYLES = {
    "low": ("RIESGO MUY BAJO / LIBROS LIMPIOS", "CONTABILIDAD CONSERVADORA", "Ganancias de alta calidad avaladas por caja real.", "< 5% (Mínimo / Limpio)", _EMERALD_BADGE, "text-emerald-700", True),
    2: ("RIESGO MODERADO / ALERTA PREVENTIVA", "ZONA DE VIGILANCIA OPERATIVA", "Se observan 2 señales atípicas de capital de trabajo o partidas secundarias.", "15% - 25% (Moderado)", _AMBER_BADGE, "text-amber-700", False),
    3: ("RIESGO MEDIO-ALTO / VIGILANCIA RIGUROSA", "ZONA DE ATENCIÓN FORENSE", "Se activan 3 señales de advertencia simultáneas en capital de trabajo o balance.", "25% - 40% (Vigilancia)", _ORANGE_BADGE, "text-orange-700", False),
    "high": ("RIESGO ALTO / ALERTA FORENSE", "PELIGRO DE MAQUILLAJE CONTABLE", "Alerta forense crítica. Se activan 4 o más banderas de alarma simultáneas.", "> 70% (Elevado / Alerta Forense)", _ROSE_BADGE, "text-rose-700", False),
}


def build_sloan_detail(forn_data: dict, forn_lr: dict) -> tuple:
    """Construye la tarjeta Sloan Accruals respetando arquetipos no aplicables y datos faltantes."""
    sloan_obj = forn_lr.get("sloan_accrual", {}) or forn_data.get("sloan_accrual_analysis", {}).get("latest_result", {}) or {}
    is_not_applicable = str(sloan_obj.get("status", "")).upper().startswith("NO APLICABLE") or str(sloan_obj.get("badge", "")).upper().startswith("N/A")

    sloan_val = safe_float(sloan_obj.get("sloan_ratio_pct"))
    if sloan_val is None and not is_not_applicable:
        s_raw = safe_float(sloan_obj.get("sloan_ratio"))
        if s_raw is not None:
            sloan_val = s_raw * 100.0

    sloan_ni = usd_to_m(sloan_obj.get("net_income"))
    sloan_cfo = usd_to_m(sloan_obj.get("cfo"))
    sloan_accruals = usd_to_m(sloan_obj.get("total_accruals"))
    sloan_assets = usd_to_m(sloan_obj.get("avg_assets"))

    if is_not_applicable:
        return "N/A", {
            "sloan_val": None,
            "sloan_str": "N/A",
            "net_income": fmt_money_m(sloan_ni),
            "cfo": fmt_money_m(sloan_cfo),
            "total_accruals": "N/A",
            "avg_assets": fmt_money_m(sloan_assets),
            "is_safe": True,
            "sloan_bucket": 0,
            "status": sloan_obj.get("status", "NO APLICABLE (SECTOR FINANCIERO)"),
            "badge": sloan_obj.get("badge", "N/A BANCA Y SEGUROS"),
            "status_badge_class": "bg-slate-100 text-slate-600 border-slate-300",
            "text_class": "text-slate-600",
            "bg_pill_class": "bg-slate-50 text-slate-600 border-slate-200",
            "accrual_direction": "N/A",
            "accrual_direction_desc": "Entidad financiera / aseguradora regulada.",
            "diagnosis": sloan_obj.get("diagnosis", "Ratio de devengos corporativo no aplicable al arquetipo financiero."),
        }

    if sloan_val is None:
        return "N/D", {
            "sloan_val": None,
            "sloan_str": "N/D",
            "net_income": fmt_money_m(sloan_ni),
            "cfo": fmt_money_m(sloan_cfo),
            "total_accruals": fmt_money_m(sloan_accruals),
            "avg_assets": fmt_money_m(sloan_assets),
            "is_safe": False,
            "sloan_bucket": 0,
            "status": sloan_obj.get("status") or "N/D",
            "badge": sloan_obj.get("badge") or "SIN DATOS SUFICIENTES",
            "status_badge_class": _SLATE_BADGE,
            "text_class": "text-slate-600",
            "bg_pill_class": "bg-slate-50 text-slate-600 border-slate-200",
            "accrual_direction": "N/D",
            "accrual_direction_desc": "Faltan componentes para contrastar beneficio neto y flujo operativo.",
            "diagnosis": sloan_obj.get("diagnosis") or "Datos insuficientes de utilidad neta, CFO o activos medios para evaluar devengos.",
        }

    if sloan_val < -10.0:
        bucket, badge_cls, txt_cls, pill_cls = 1, _SKY_BADGE, "text-sky-700", "bg-sky-50 text-sky-700 border-sky-200"
        def_status, def_badge, def_diag = "CONSERVADOR", "FLUJO DE CAJA MUY SUPERIOR A UTILIDAD", "El flujo de caja operativo supera ampliamente la utilidad contable."
    elif sloan_val <= 5.0:
        bucket, badge_cls, txt_cls, pill_cls = 2, _EMERALD_BADGE, "text-emerald-700", "bg-emerald-50 text-emerald-700 border-emerald-200"
        def_status, def_badge, def_diag = "EXCELENTE", "ALTA CONVERSIÓN DE CAJA", "Devengos equilibrados con sólido respaldo de flujo operativo real."
    elif sloan_val <= 10.0:
        bucket, badge_cls, txt_cls, pill_cls = 3, _AMBER_BADGE, "text-amber-700", "bg-amber-50 text-amber-700 border-amber-200"
        def_status, def_badge, def_diag = "PRECAUCIÓN", "DEVENGOS ELEVADOS", "Se observan devengos moderadamente superiores a la generación de caja."
    else:
        bucket, badge_cls, txt_cls, pill_cls = 4, _ROSE_BADGE, "text-rose-700", "bg-rose-50 text-rose-700 border-rose-200"
        def_status, def_badge, def_diag = "ALERTA FORENSE", "DEVENGOS AGRESIVOS (NI >> CFO)", "La utilidad contable supera significativamente la caja operativa real."

    has_accruals = sloan_accruals is not None
    accrual_dir = ("NI > CFO" if sloan_accruals >= 0 else "CFO > NI") if has_accruals else "N/D"
    accrual_dir_desc = (
        ("Utilidad contable supera a la caja real (devengos positivos / papel)" if sloan_accruals >= 0 else "Caja operativa real supera a la utilidad contable (alta calidad)")
        if has_accruals else "Sin desglose de devengos totales."
    )

    return f"{sloan_val:.2f}%", {
        "sloan_val": sloan_val,
        "sloan_str": f"{sloan_val:.2f}%",
        "net_income": fmt_money_m(sloan_ni),
        "cfo": fmt_money_m(sloan_cfo),
        "total_accruals": fmt_money_m(sloan_accruals),
        "avg_assets": fmt_money_m(sloan_assets),
        "is_safe": (-10.0 <= sloan_val <= 5.0),
        "sloan_bucket": bucket,
        "status": sloan_obj.get("status") or def_status,
        "badge": sloan_obj.get("badge") or def_badge,
        "status_badge_class": badge_cls,
        "text_class": txt_cls,
        "bg_pill_class": pill_cls,
        "accrual_direction": accrual_dir,
        "accrual_direction_desc": accrual_dir_desc,
        "diagnosis": sloan_obj.get("diagnosis") or def_diag,
    }


def build_montier_detail(forn_data: dict, forn_lr: dict) -> dict:
    """Construye la tarjeta Montier C-Score (0-6) manejando ausencia de ejercicio previo y arquetipos financieros."""
    montier_obj = forn_lr.get("montier_c_score", {}) or forn_data.get("montier_c_score", {}).get("LTM", {}) or {}
    montier_score = montier_obj.get("total_score")
    montier_flags = list((montier_obj.get("flags_breakdown") or {}).values())

    if montier_score is None:
        if montier_obj.get("badge") == "NO APLICABLE":
            rating = "NO APLICABLE"
            badge = "NO APLICABLE"
            verdict = montier_obj.get(
                "verdict",
                "Montier C-Score no aplicable a entidades financieras y aseguradoras: la intermediación de crédito opera bajo otra taxonomía.",
            )
            risk_str, badge_cls, txt_cls, is_safe = "N/A (Entidad Financiera)", "bg-slate-100 text-slate-600 border-slate-300", "text-slate-500", False
        else:
            rating = montier_obj.get("rating", "DATOS INSUFICIENTES (SIN T-1)")
            badge = montier_obj.get("badge", "NO EVALUABLE")
            verdict = montier_obj.get("verdict", "No se dispone de ejercicio precedente (t-1) para evaluar variaciones interanuales.")
            risk_str, badge_cls, txt_cls, is_safe = "N/D (Sin ejercicio t-1)", _SLATE_BADGE, "text-slate-600", False
    else:
        key = "low" if montier_score <= 1 else (montier_score if montier_score in (2, 3) else "high")
        def_r, def_b, def_v, risk_str, badge_cls, txt_cls, is_safe = _MONTIER_SCORE_STYLES[key]
        rating = montier_obj.get("rating", def_r)
        badge = montier_obj.get("badge", def_b)
        verdict = montier_obj.get("verdict", def_v)

    return {
        "score": montier_score,
        "max_score": 6,
        "rating": rating,
        "badge": badge,
        "status_badge_class": badge_cls,
        "text_class": txt_cls,
        "manipulation_risk_str": risk_str,
        "manipulation_risk_class": txt_cls,
        "verdict": verdict,
        "flags": montier_flags,
        "is_safe": is_safe,
    }


def _resolve_leverage_context(solv_data: dict, canonical: dict, bs_data: dict, latest_p: str, is_banking: bool) -> dict:
    """Construye la tarjeta 13.1 (Apalancamiento Deuda Neta / EBITDA) desde el Balance Canónico."""
    lev_data = solv_data.get("cash_flow_leverage", {}) or {}
    st_debt_raw = usd_to_m(bs_data.get("short_term_debt", {}).get(latest_p))
    lt_debt_raw = usd_to_m(bs_data.get("long_term_debt", {}).get(latest_p))
    cash_raw = usd_to_m(bs_data.get("cash", {}).get(latest_p))
    sti_raw = usd_to_m(bs_data.get("short_term_investments", {}).get(latest_p))
    nfp_val = usd_to_m(bs_data.get("net_financial_position", {}).get(latest_p))

    has_debt_inputs = st_debt_raw is not None or lt_debt_raw is not None
    has_cash_inputs = cash_raw is not None or sti_raw is not None
    total_debt_m = round((st_debt_raw or 0.0) + (lt_debt_raw or 0.0), 1) if has_debt_inputs else None
    total_cash_liquid_m = round((cash_raw or 0.0) + (sti_raw or 0.0), 1) if has_cash_inputs else None

    if nfp_val is not None:
        net_debt_m = nfp_val
    elif total_debt_m is not None and total_cash_liquid_m is not None:
        net_debt_m = round(total_debt_m - total_cash_liquid_m, 1)
    else:
        net_debt_m = already_m(lev_data.get("net_debt"))

    is_net_cash = (net_debt_m is not None) and (net_debt_m <= 0.0)

    can_ebit = usd_to_m(canonical.get("operating_income", {}).get(latest_p))
    raw_dna = already_m(lev_data.get("dna"))
    if raw_dna is None and lev_data.get("ebitda") is not None and lev_data.get("ebit") is not None:
        raw_dna = already_m(float(lev_data["ebitda"]) - float(lev_data["ebit"]))
    ebitda_m = round(can_ebit + (raw_dna or 0.0), 1) if can_ebit is not None else already_m(lev_data.get("ebitda"))

    fcf_can_m = usd_to_m(canonical.get("free_cash_flow", {}).get(latest_p))
    fcf_m_val = fcf_can_m if (fcf_can_m is not None and fcf_can_m != 0.0) else already_m(lev_data.get("fcf"))

    nd_fcf_val = None
    if is_net_cash:
        net_debt_ebitda_val = 0.0
        net_debt_ebitda_str = "0.00x (Caja Neta)"
        net_debt_fcf_str = "0.00x (Caja Neta)"
        lev_status = "Caja Neta Excedente"
        solv_safe = True
    elif net_debt_m is not None and ebitda_m is not None and ebitda_m > 0:
        net_debt_ebitda_val = round(net_debt_m / ebitda_m, 2)
        net_debt_ebitda_str = f"{net_debt_ebitda_val:.2f}x"
        lev_status = "GRADO INVERSIÓN SUPERIOR (< 1.5x)" if net_debt_ebitda_val < 1.5 else ("APALANCAMIENTO MODERADO" if net_debt_ebitda_val <= 3.0 else "APALANCAMIENTO ELEVADO")
        solv_safe = net_debt_ebitda_val < 1.5
        if fcf_m_val is not None and fcf_m_val > 0:
            nd_fcf_val = round(net_debt_m / fcf_m_val, 2)
            net_debt_fcf_str = f"{nd_fcf_val:.2f}x"
        else:
            net_debt_fcf_str = "N/D"
    else:
        net_debt_ebitda_val = safe_float(lev_data.get("net_debt_to_ebitda"))
        net_debt_ebitda_str = lev_data.get("net_debt_to_ebitda_str", "N/D")
        net_debt_fcf_str = lev_data.get("net_debt_to_fcf_str", "N/D")
        lev_status = lev_data.get("status") or "N/D"
        solv_safe = is_net_cash or (net_debt_ebitda_val is not None and net_debt_ebitda_val < 1.5)

    if is_banking:
        nd_eb_color, nd_fcf_color = "neutral", "neutral"
        badge_cls, txt_cls = "bg-blue-100 text-blue-800 border-blue-300", "text-blue-700"
    elif is_net_cash:
        nd_eb_color, nd_fcf_color = "safe", "safe"
        badge_cls, txt_cls = _EMERALD_BADGE, "text-emerald-700"
    else:
        nd_eb_color = "neutral" if net_debt_ebitda_val is None else ("safe" if net_debt_ebitda_val < 1.5 else ("warning" if net_debt_ebitda_val <= 3.0 else "danger"))
        nd_fcf_color = "neutral" if nd_fcf_val is None else ("safe" if nd_fcf_val < 2.0 else ("warning" if nd_fcf_val <= 4.0 else "danger"))
        badge_cls, txt_cls = (
            (_SLATE_BADGE, "text-slate-600") if nd_eb_color == "neutral"
            else ((_EMERALD_BADGE, "text-emerald-700") if nd_eb_color == "safe"
                  else ((_AMBER_BADGE, "text-amber-700") if nd_eb_color == "warning" else (_ROSE_BADGE, "text-rose-700")))
        )

    net_debt_display = (
        f"-${abs(net_debt_m):,.1f}M (Caja Neta)" if (net_debt_m is not None and net_debt_m < 0)
        else (f"${net_debt_m:,.1f}M" if (net_debt_m is not None and net_debt_m > 0)
              else ("$0.0M" if net_debt_m == 0.0 else "N/D"))
    )

    if is_banking:
        badge_str = "ENTIDAD REGULADA"
        diag = "Para entidades de crédito, la solvencia se evalúa mediante capital regulatorio (CET1) y morosidad de cartera (NPLs), no mediante Deuda Neta / EBITDA."
    elif is_net_cash:
        badge_str = "CAJA NETA"
        diag = "Posición de caja neta líquida sin deuda neta que amortizar."
    elif net_debt_ebitda_val is None:
        badge_str = lev_data.get("badge") or "N/D"
        diag = lev_data.get("diagnosis") or "Datos insuficientes de deuda neta o EBITDA para evaluar apalancamiento."
    elif net_debt_ebitda_val < 1.5:
        badge_str = lev_data.get("badge") or "APALANCAMIENTO BAJO"
        diag = f"Apalancamiento muy conservador ({net_debt_ebitda_str} EBITDA). La compañía extinguiría su deuda neta en {net_debt_ebitda_val:.2f} años de EBITDA."
    elif net_debt_ebitda_val <= 3.0:
        badge_str = lev_data.get("badge") or "APALANCAMIENTO MODERADO"
        diag = f"Apalancamiento moderado ({net_debt_ebitda_str} EBITDA), equivalente a {net_debt_ebitda_val:.2f} años de generación operativa bruta."
    else:
        badge_str = lev_data.get("badge") or "APALANCAMIENTO ELEVADO"
        diag = f"Apalancamiento elevado ({net_debt_ebitda_str} EBITDA), con {net_debt_ebitda_val:.2f} años requeridos de EBITDA para amortizar la deuda neta."

    solvency_13_1 = {
        "total_debt": "N/A" if is_banking else (f"${total_debt_m:,.1f}M" if total_debt_m is not None else "N/D"),
        "cash": f"${total_cash_liquid_m:,.1f}M" if total_cash_liquid_m is not None else "N/D",
        "cash_only": f"${cash_raw:,.1f}M" if cash_raw is not None else "N/D",
        "sti": f"${sti_raw:,.1f}M" if sti_raw is not None else "N/D",
        "has_sti": bool(sti_raw is not None and sti_raw > 0),
        "net_debt": "N/A" if is_banking else net_debt_display,
        "is_net_cash": is_net_cash,
        "ebitda": "N/A" if is_banking else (f"${ebitda_m:,.1f}M" if ebitda_m is not None else "N/D"),
        "net_debt_to_ebitda_str": "N/A (Banca)" if is_banking else net_debt_ebitda_str,
        "net_debt_to_ebitda_status": "No Aplicable a Entidades de Intermediación" if is_banking else lev_status,
        "net_debt_ebitda_color": nd_eb_color,
        "fcf": "N/A" if is_banking else (f"${fcf_m_val:,.1f}M" if fcf_m_val is not None else "N/D"),
        "net_debt_to_fcf_str": "N/A (Banca)" if is_banking else net_debt_fcf_str,
        "net_debt_fcf_color": nd_fcf_color,
        "badge": badge_str,
        "status_badge_class": badge_cls,
        "text_class": txt_cls,
        "diagnosis": diag,
        "is_safe": True if is_banking else solv_safe,
    }
    return {
        "solvency_13_1": solvency_13_1,
        "is_net_cash": is_net_cash,
        "net_debt_m": net_debt_m,
        "can_ebit": can_ebit,
        "net_debt_ebitda_str": net_debt_ebitda_str,
        "net_debt_fcf_str": net_debt_fcf_str,
    }


def _build_credit_dictum(
    is_banking: bool,
    is_net_cash: bool,
    net_debt_m,
    rating_synth: str,
    cov_val,
    cov_disp: str,
    net_debt_ebitda_str: str,
    net_debt_fcf_str: str,
    altman_val,
    def_prob_val: str,
    def_spread_pct_val,
) -> str:
    """Redacta un dictamen crediticio veraz alineado con el rating real y métricas disponibles."""
    if is_banking:
        return (
            "Calificación Institucional de Grado Regulado. Para entidades bancarias y de intermediación financiera, "
            "la solvencia y calidad crediticia se evalúan a través de la suficiencia patrimonial CET1 (Tier 1 Common Equity), "
            "la cobertura de provisiones sobre préstamos dudosos (NPL Coverage) y los ratios regulatorios LCR/NSFR bajo Basilea III, "
            "en lugar de las métricas de cobertura corporativa tradicional."
        )

    if rating_synth in ("N/D", "N/A", ""):
        return "Datos financieros insuficientes para emitir una calificación crediticia sintética ni dictamen de cobertura."

    spread_str = f"+{def_spread_pct_val:.2f}%" if isinstance(def_spread_pct_val, (int, float)) else "N/D"
    altman_phrase = (
        f"El índice Altman Z'' ({altman_val:.2f}) sitúa el riesgo de quiebra en nivel estadísticamente acotado"
        if isinstance(altman_val, (int, float)) and altman_val >= 2.60
        else (f"El índice Altman Z'' se ubica en {altman_val:.2f}" if isinstance(altman_val, (int, float))
              else "El modelo Altman Z'' no aplica o carece de insumos completos para esta estructura patrimonial")
    )

    if is_net_cash and net_debt_m is not None:
        return (
            f"Calificación de Grado Institucional Máximo ({rating_synth} / Aaa) fundamentada en la metodología Aswath Damodaran (NYU Stern). "
            f"La compañía opera en una posición estructural de Caja Neta ex-deuda (${abs(net_debt_m):,.1f}M), sin pasivo financiero neto que amortizar. "
            f"{altman_phrase}, con probabilidad acumulada de impago a 10 años de {def_prob_val} y spread crediticio de {spread_str} sobre el US Treasury 10Y."
        )

    is_top_tier = str(rating_synth).upper().startswith("AAA") and isinstance(cov_val, (int, float)) and cov_val >= 8.5
    if is_top_tier:
        return (
            f"Calificación de Grado Institucional Máximo ({rating_synth} / Aaa) derivada de la metodología Aswath Damodaran (NYU Stern). "
            f"La cobertura operativa EBIT de intereses alcanza {cov_disp}, superando por un factor de {float(cov_val) / 8.5:.1f}x el umbral normativo de 8.50x exigido para la máxima categoría. "
            f"El apalancamiento neto se sitúa en {net_debt_ebitda_str} de EBITDA ({net_debt_fcf_str} de FCF). "
            f"{altman_phrase}, con probabilidad de default a 10 años de {def_prob_val} y spread crediticio de {spread_str}."
        )

    cov_clause = (
        f"La cobertura operativa de intereses se sitúa en {cov_disp} "
        + ("(superando el umbral de 8.50x)." if cov_val >= 8.5 else "(por debajo del umbral de 8.50x exigido para AAA).")
        if isinstance(cov_val, (int, float))
        else f"Cobertura registrada: {cov_disp}."
    )
    return (
        f"Calificación Crediticia Sintética {rating_synth} derivada de la metodología Aswath Damodaran (NYU Stern). "
        f"{cov_clause} El apalancamiento neto es {net_debt_ebitda_str} de EBITDA ({net_debt_fcf_str} de FCF). "
        f"{altman_phrase}; probabilidad estimada de default a 10 años: {def_prob_val} (spread: {spread_str})."
    )


def build_solvency_and_distress_context(scores: dict, canonical: dict, bs_data: dict, latest_p: str, is_banking: bool) -> dict:
    """Construye tarjetas 13.1, 13.2 y modelo de insolvencia / rating sintético sin defaults falsos."""
    solv_data = scores.get("debt_and_solvency_analysis", {}).get("latest_result", {}) or {}
    lev = _resolve_leverage_context(solv_data, canonical, bs_data, latest_p, is_banking)
    solvency_13_1 = lev["solvency_13_1"]
    is_net_cash = lev["is_net_cash"]

    cov_data = solv_data.get("debt_service", {}) or {}
    dist_data = solv_data.get("distress_models", {}) or {}

    ebit_cov_m = first_present(already_m(cov_data.get("ebit")), lev["can_ebit"])
    interest_exp_m = already_m(cov_data.get("interest_expense"))
    cov_val = safe_float(cov_data.get("interest_coverage"))
    cash_cov_val = safe_float(cov_data.get("cash_interest_coverage"))
    fin_burden = safe_float(cov_data.get("financial_burden_pct"))
    solv_13_2_safe = is_net_cash or (cov_val is not None and cov_val >= 8.5)

    if is_banking:
        int_cov_color, cash_cov_color, fin_burden_color = "neutral", "neutral", "neutral"
    elif is_net_cash:
        int_cov_color, cash_cov_color, fin_burden_color = "safe", "safe", "safe"
    else:
        int_cov_color = "neutral" if cov_val is None else ("safe" if cov_val >= 8.5 else ("warning" if cov_val >= 3.0 else "danger"))
        cash_cov_color = int_cov_color if cash_cov_val is None else ("safe" if cash_cov_val >= 8.0 else ("warning" if cash_cov_val >= 2.5 else "danger"))
        fin_burden_color = "neutral" if fin_burden is None else ("safe" if fin_burden < 5.0 else ("warning" if fin_burden <= 15.0 else "danger"))

    cov_disp = "N/A (Banca)" if is_banking else (cov_data.get("interest_coverage_str") or (f"{cov_val:.1f}x" if cov_val is not None else "N/D"))
    cash_cov_disp = "N/A (Banca)" if is_banking else (cov_data.get("cash_interest_coverage_str") or (f"{cash_cov_val:.1f}x" if cash_cov_val is not None else "N/D"))
    def_cov_status = (
        "Solvencia por Intermediación Crediticia" if is_banking
        else (cov_data.get("status") or ("COBERTURA EXCELENTE" if solv_13_2_safe else ("COBERTURA MODERADA" if (cov_val is not None and cov_val >= 3.0) else ("COBERTURA DÉBIL" if cov_val is not None else "N/D"))))
    )
    def_cov_badge = (
        "SUPERVISIÓN REGULATORIA" if is_banking
        else (cov_data.get("badge") or ("MÁXIMA PROTECCIÓN" if solv_13_2_safe else ("VIGILANCIA" if cov_val is not None else "SIN DATOS")))
    )
    def_cov_diag = (
        "Las entidades bancarias se fondean con depósitos a coste financiero directo (margen NIM), por lo que la cobertura corporativa no aplica."
        if is_banking
        else (cov_data.get("diagnosis") or ("Los beneficios operativos cubren los intereses financieros." if solv_13_2_safe else ("Cobertura operativa ajustada frente a la carga financiera." if cov_val is not None else "No hay datos suficientes de EBIT o gasto por intereses para evaluar cobertura.")))
    )

    solvency_13_2 = {
        "ebit": "N/A" if is_banking else (f"${ebit_cov_m:,.1f}M" if ebit_cov_m is not None else "N/D"),
        "interest_expense": "N/A" if is_banking else (f"${interest_exp_m:,.1f}M" if interest_exp_m is not None else "N/D"),
        "interest_coverage_str": cov_disp,
        "interest_cov_color": int_cov_color,
        "cash_interest_coverage_str": cash_cov_disp,
        "cash_cov_color": cash_cov_color,
        "financial_burden_pct": "N/A" if is_banking else (f"{fin_burden:.2f}%" if fin_burden is not None else "N/D"),
        "financial_burden_color": fin_burden_color,
        "status": def_cov_status,
        "badge": def_cov_badge,
        "diagnosis": def_cov_diag,
        "is_safe": True if is_banking else solv_13_2_safe,
    }

    altman_val = safe_float(first_present(dist_data.get("altman_z_double_prime"), dist_data.get("altman_z_score")))
    altman_is_safe = altman_val is not None and altman_val >= 2.60
    if altman_val is None:
        altman_bucket, altman_badge_cls, altman_txt_cls, altman_pill_cls = 0, _SLATE_BADGE, "text-slate-600", "bg-slate-50 text-slate-600 border-slate-200"
    elif altman_val < 1.10:
        altman_bucket, altman_badge_cls, altman_txt_cls, altman_pill_cls = 1, _ROSE_BADGE, "text-rose-700", "bg-rose-50 text-rose-700 border-rose-200"
    elif altman_val <= 2.60:
        altman_bucket, altman_badge_cls, altman_txt_cls, altman_pill_cls = 2, _AMBER_BADGE, "text-amber-700", "bg-amber-50 text-amber-700 border-amber-200"
    else:
        altman_bucket, altman_badge_cls, altman_txt_cls, altman_pill_cls = 3, _EMERALD_BADGE, "text-emerald-700", "bg-emerald-50 text-emerald-700 border-emerald-200"

    rating_synth = dist_data.get("synthetic_rating") or ("Regulada" if is_banking else "N/D")
    rating_desc = dist_data.get("synthetic_rating_desc") or (
        "Supervisión regulatoria y capital CET1" if is_banking else ("Sin calificación crediticia disponible" if rating_synth == "N/D" else f"Categoría Crediticia Sintética ({rating_synth})")
    )
    def_spread_pct_val = safe_float(dist_data.get("default_spread_pct"))
    def_prob_val = dist_data.get("default_probability") or ("N/A (Regulada)" if is_banking else "N/D")

    synth_upper = str(rating_synth).upper()
    if is_banking:
        r_badge_cls, r_badge_lbl, r_txt_cls, rating_is_safe = "bg-blue-100 text-blue-800 border-blue-300", "Entidad Regulada", "text-blue-700", True
    elif synth_upper in ("N/D", "N/A", ""):
        r_badge_cls, r_badge_lbl, r_txt_cls, rating_is_safe = _SLATE_BADGE, "Sin Datos", "text-slate-600", False
    elif any(synth_upper.startswith(p) for p in ("AAA", "AA", "A", "BBB")):
        r_badge_cls, r_badge_lbl, r_txt_cls, rating_is_safe = _EMERALD_BADGE, "Grado Institucional", "text-emerald-700", True
    elif any(synth_upper.startswith(p) for p in ("BB", "B")):
        r_badge_cls, r_badge_lbl, r_txt_cls, rating_is_safe = _AMBER_BADGE, "Grado Especulativo", "text-amber-700", False
    else:
        r_badge_cls, r_badge_lbl, r_txt_cls, rating_is_safe = _ROSE_BADGE, "Alto Riesgo / Distress", "text-rose-700", False

    credit_dictum = _build_credit_dictum(
        is_banking=is_banking, is_net_cash=is_net_cash, net_debt_m=lev["net_debt_m"],
        rating_synth=rating_synth, cov_val=cov_val, cov_disp=cov_disp,
        net_debt_ebitda_str=lev["net_debt_ebitda_str"], net_debt_fcf_str=lev["net_debt_fcf_str"],
        altman_val=altman_val, def_prob_val=def_prob_val, def_spread_pct_val=def_spread_pct_val,
    )

    distress_detail = {
        "altman_z": f"{altman_val:.2f}" if altman_val is not None else "N/D",
        "altman_val": altman_val,
        "altman_zone": dist_data.get("altman_zone") or ("NO APLICABLE" if is_banking else ("N/D" if altman_val is None else "")),
        "altman_badge": dist_data.get("altman_badge") or ("N/A" if is_banking else ("N/D" if altman_val is None else "")),
        "altman_diagnosis": dist_data.get("altman_diagnosis") or ("No aplica a balances bancarios/financieros." if is_banking else ("Insumos patrimoniales insuficientes para Altman Z''." if altman_val is None else "")),
        "altman_bucket": altman_bucket,
        "status_badge_class": altman_badge_cls,
        "text_class": altman_txt_cls,
        "altman_pill_class": altman_pill_cls,
        "altman_x1": f"{dist_data['altman_x1']:.4f}" if isinstance(dist_data.get("altman_x1"), (int, float)) else "N/A",
        "altman_x2": f"{dist_data['altman_x2']:.4f}" if isinstance(dist_data.get("altman_x2"), (int, float)) else "N/A",
        "altman_x3": f"{dist_data['altman_x3']:.4f}" if isinstance(dist_data.get("altman_x3"), (int, float)) else "N/A",
        "altman_x4": f"{dist_data['altman_x4']:.4f}" if isinstance(dist_data.get("altman_x4"), (int, float)) else "N/A",
        "altman_is_safe": altman_is_safe,
        "synthetic_rating": rating_synth,
        "synthetic_rating_desc": rating_desc,
        "synthetic_rating_badge_class": r_badge_cls,
        "synthetic_rating_badge_label": r_badge_lbl,
        "synthetic_rating_text_class": r_txt_cls,
        "default_spread_pct": f"+{def_spread_pct_val:.2f}%" if def_spread_pct_val is not None else "N/D",
        "default_probability": def_prob_val,
        "rating_is_safe": rating_is_safe,
        "credit_dictum": credit_dictum,
    }
    return {"solvency_13_1": solvency_13_1, "solvency_13_2": solvency_13_2, "distress_detail": distress_detail}
