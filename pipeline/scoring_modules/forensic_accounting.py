"""
forensic_accounting.py - Motor de Auditoría Forense Contable y Calidad de Beneficios:
Ratio de Devengos de Sloan, Divergencias AR/Inventarios/Activos Blandos y Montier C-Score (0-6).
"""

from typing import Any, Dict, List, Optional, Tuple

from .scoring_utils import _chronological_annual_fys, _safe_float, normalize_archetype


_MONTIER_FIN_FLAGS = {
    "f1_cfo_divergence": ("1. Divergencia Beneficio vs. Flujo de Caja", "NI > CFO", "No aplicable a intermediación financiera."),
    "f2_ar_vs_sales": ("2. Cuentas por Cobrar vs. Ventas (DSO)", "Δ DSO > 0 (o %Δ AR > %Δ Ventas)", "Entidades financieras no operan con cuentas comerciales a cobrar."),
    "f3_inv_vs_cogs": ("3. Inventarios vs. Coste de Ventas (DIO)", "Δ DIO > 0 (o %Δ Inv > %Δ COGS)", "Entidades financieras no mantienen existencias de mercancía ni COGS."),
    "f4_other_current_assets": ("4. Otros Activos Corrientes vs. Ventas", "Ratio Otros Act. Ctes/Ventas_t > Ratio Otros Act. Ctes/Ventas_t-1", "Estructura de balance sin clasificación corriente/no corriente."),
    "f5_depreciation_rate": ("5. Reducción de la Tasa de Depreciación", "Tasa Depreciación_t < Tasa Depreciación_t-1", "PP&E tangible inmaterial frente al activo financiero total."),
    "f6_asset_growth": ("6. Crecimiento Excesivo de Activos Totales", "%Δ Activos Totales > 10.0%", "La expansión de balance bancario responde a depósitos y política monetaria."),
}


class ForensicAccountingEngine:
    """
    Motor Especializado de Auditoría Forense y Detección de Manipulación Contable:
    Sloan Accrual Anomaly, Matriz de Divergencias (DSO, DIO, Activos Blandos) y Montier C-Score.
    """

    @staticmethod
    def _compute_sloan_for_period(
        fy: str,
        prev_fy: Optional[str],
        ni: Optional[float],
        cfo: Optional[float],
        assets_t: Optional[float],
        avg_assets: Optional[float],
        is_financial: bool,
    ) -> Dict[str, Any]:
        """Calcula el Ratio de Devengos de Sloan para un período fiscal o LTM."""
        if is_financial:
            return {
                "period": fy,
                "prior_period": prev_fy,
                "net_income": ni,
                "cfo": cfo,
                "total_accruals": None,
                "ending_assets": assets_t,
                "avg_assets": avg_assets,
                "sloan_ratio": None,
                "sloan_ratio_pct": None,
                "status": "NO APLICABLE (SECTOR FINANCIERO)",
                "badge": "N/A BANCA Y SEGUROS",
                "color": "#607D8B",
                "diagnosis": (
                    "El ratio de devengos contables de Sloan (NI - CFO / Activos) no es aplicable a bancos o aseguradoras. "
                    "En estas entidades, la originación de créditos, préstamos y movimientos de carteras de inversión se clasifican "
                    "en el flujo de caja operativo (CFO), creando volatilidades masivas que no reflejan manipulación de beneficios."
                ),
            }

        if ni is None or cfo is None or not avg_assets or avg_assets <= 0:
            return {
                "period": fy,
                "prior_period": prev_fy,
                "net_income": ni,
                "cfo": cfo,
                "total_accruals": None,
                "ending_assets": assets_t,
                "avg_assets": avg_assets,
                "sloan_ratio": None,
                "sloan_ratio_pct": None,
                "status": "N/D",
                "badge": "DATOS INSUFICIENTES",
                "color": "#757575",
                "diagnosis": "Datos contables insuficientes para calcular el ratio de devengos.",
            }

        total_accruals = ni - cfo
        sloan_ratio = total_accruals / avg_assets
        sloan_ratio_pct = round(sloan_ratio * 100.0, 2)
        if sloan_ratio < -0.03:
            status, badge, color = "EXCELENTE", "ALTA CONVERSIÓN DE CAJA (CFO > NI)", "#2E7D32"
            diag = "Conservadurismo contable sobresaliente. El flujo de caja operativo supera holgadamente a la utilidad neta, generando devengos negativos que blindan al accionista de inflaciones artificiales de beneficios."
        elif sloan_ratio <= 0.07:
            status, badge, color = "SALUDABLE", "DEVENGOS EQUILIBRADOS", "#1976D2"
            diag = "Los devengos contables operan en el rango óptimo y equilibrado (-3% a +7%). Existe sólida correspondencia entre ingresos contables y cobros de efectivo."
        elif sloan_ratio <= 0.10:
            status, badge, color = "PRECAUCIÓN", "DEVENGOS ELEVADOS (ZONA DE ALERTA)", "#F57C00"
            diag = "El beneficio devengado supera al flujo de caja operativo en más del 7% de los activos. Se aconseja vigilar la agresividad en reconocimiento de facturación y variaciones en capital de trabajo."
        else:
            status, badge, color = "ALERTA ROJA", "PELIGRO DE MANIPULACIÓN", "#D32F2F"
            diag = "Anomalía severa de devengos (> +10%). Alto riesgo de utilidades contables 'de papel' no respaldadas por efectivo real. Fuerte propensión histórica a deterioros de resultados y ajustes futuros."

        return {
            "period": fy,
            "prior_period": prev_fy,
            "net_income": ni,
            "cfo": cfo,
            "total_accruals": total_accruals,
            "ending_assets": assets_t,
            "avg_assets": avg_assets,
            "sloan_ratio": round(sloan_ratio, 4),
            "sloan_ratio_pct": sloan_ratio_pct,
            "status": status,
            "badge": badge,
            "color": color,
            "diagnosis": diag,
        }

    @staticmethod
    def _compute_divergences_for_period(
        fy: str,
        curr: Dict[str, Any],
        prev: Optional[Dict[str, Any]],
        assets_t: Optional[float],
        assets_prev: Optional[float],
        is_financial: bool,
        arch_norm: str,
    ) -> Tuple[Dict[str, Any], Dict[str, Optional[float]]]:
        """Calcula los spreads de Cuentas por Cobrar vs Ventas, Inventarios vs COGS y Activos Blandos."""
        ar_t = _safe_float(curr.get("accounts_receivable"))
        ar_prev = _safe_float(prev.get("accounts_receivable")) if prev else None
        rev_t = _safe_float(curr.get("revenue"))
        rev_prev = _safe_float(prev.get("revenue")) if prev else None

        d_ar = ((ar_t - ar_prev) / abs(ar_prev)) if (ar_t is not None and ar_prev and ar_prev > 0) else None
        d_rev = ((rev_t - rev_prev) / abs(rev_prev)) if (rev_t is not None and rev_prev and rev_prev > 0) else None
        ar_sales_spread = (d_ar - d_rev) if (d_ar is not None and d_rev is not None) else None
        dso_t = ((ar_t / rev_t) * 365.0) if (ar_t is not None and rev_t and rev_t > 0) else None
        dso_prev = ((ar_prev / rev_prev) * 365.0) if (ar_prev is not None and rev_prev and rev_prev > 0) else None
        delta_dso = (dso_t - dso_prev) if (dso_t is not None and dso_prev is not None) else None

        flag_ar = False
        if is_financial:
            status_ar, trap_ar, color_ar = "NO APLICABLE", "No Aplicable a Entidad Financiera", "#607D8B"
            diag_ar = f"Entidad del arquetipo '{arch_norm}': no opera con cuentas comerciales a cobrar ni facturación de bienes tangibles."
        elif ar_sales_spread is not None and ar_sales_spread > 0.10 and delta_dso is not None and delta_dso > 5.0:
            flag_ar, status_ar, trap_ar, color_ar = True, "ALERTA DE DESCONEXIÓN", "Riesgo de Channel Stuffing / Facturación Agresiva", "#D32F2F"
            diag_ar = f"Cuentas por cobrar crecen {round(ar_sales_spread * 100, 1)}% más rápido que las ventas, dilatando el cobro en +{round(delta_dso, 1)} días (DSO: {round(dso_t, 1)}d). Alerta de facturación acelerada."
        else:
            status_ar, trap_ar, color_ar = "COBRANZA SANA", "Bajo Riesgo Contable", "#2E7D32"
            diag_ar = f"Rotación y cobros armónicos con el ritmo de negocio (Spread: {round(ar_sales_spread * 100, 1) if ar_sales_spread is not None else 0.0}%, DSO: {round(dso_t, 1) if dso_t is not None else 0.0}d). Cobranza disciplinada."

        inv_t = _safe_float(curr.get("inventory"))
        inv_prev = _safe_float(prev.get("inventory")) if prev else None
        cogs_t = _safe_float(curr.get("cost_of_goods_sold"))
        cogs_prev = _safe_float(prev.get("cost_of_goods_sold")) if prev else None

        d_inv = ((inv_t - inv_prev) / abs(inv_prev)) if (inv_t is not None and inv_prev and inv_prev > 0) else None
        d_cogs = ((cogs_t - cogs_prev) / abs(cogs_prev)) if (cogs_t is not None and cogs_prev and cogs_prev > 0) else None
        inv_cogs_spread = (d_inv - d_cogs) if (d_inv is not None and d_cogs is not None) else None
        dio_t = ((inv_t / cogs_t) * 365.0) if (inv_t is not None and cogs_t and cogs_t > 0) else None
        dio_prev = ((inv_prev / cogs_prev) * 365.0) if (inv_prev is not None and cogs_prev and cogs_prev > 0) else None
        delta_dio = (dio_t - dio_prev) if (dio_t is not None and dio_prev is not None) else None

        flag_inv = False
        if is_financial:
            status_inv, trap_inv, color_inv = "NO APLICABLE", "No Aplicable a Entidad Financiera", "#607D8B"
            diag_inv = f"Entidad del arquetipo '{arch_norm}': no mantiene inventario de existencias ni coste de ventas (COGS)."
        elif inv_cogs_spread is not None and inv_cogs_spread > 0.15 and delta_dio is not None and delta_dio > 7.0:
            flag_inv, status_inv, trap_inv, color_inv = True, "REVISIÓN OPERATIVA", "Acumulación de Inventario / Sobreabsorción de Costes", "#F57C00"
            diag_inv = f"Las existencias crecen {round(inv_cogs_spread * 100, 1)}% por encima del coste de ventas, elevando el inventario en +{round(delta_dio, 1)} días (DIO: {round(dio_t, 1)}d). Evaluar si responde a preparación estacional de lanzamientos o acumulación no vendida."
        else:
            status_inv, trap_inv, color_inv = "INVENTARIO CONTROLADO", "Bajo Riesgo Contable", "#2E7D32"
            diag_inv = f"Inventario en sintonía con la cadencia de costes (Spread: {round(inv_cogs_spread * 100, 1) if inv_cogs_spread is not None else 0.0}%, DIO: {round(dio_t, 1) if dio_t is not None else 0.0}d). Existencias optimizadas."

        net_ppe_t = _safe_float(curr.get("net_ppe")) or 0.0
        cash_t = _safe_float(curr.get("cash")) or 0.0
        soft_usd = (assets_t - (net_ppe_t + cash_t)) if assets_t else None
        soft_ratio = (soft_usd / assets_t) if (soft_usd is not None and assets_t and assets_t > 0) else None
        soft_prev = None
        if prev and assets_prev and assets_prev > 0:
            soft_prev = (assets_prev - ((_safe_float(prev.get("net_ppe")) or 0.0) + (_safe_float(prev.get("cash")) or 0.0))) / assets_prev
        delta_soft = (soft_ratio - soft_prev) if (soft_ratio is not None and soft_prev is not None) else None

        flag_soft = bool(soft_ratio is not None and soft_ratio > 0.75 and delta_soft is not None and delta_soft > 0.03)
        if flag_soft:
            status_soft, trap_soft, color_soft = "PESO ELEVADO", "Predominio de Activos Blandos / Intangibles", "#F57C00"
            diag_soft = f"El {round(soft_ratio * 100, 1)}% del balance consiste en activos no respaldados por PP&E físico ni caja inmediata (incremento de +{round(delta_soft * 100, 1)} p.p.). Vigilar la capitalización de partidas diferidas."
        else:
            status_soft, trap_soft, color_soft = "ESTRUCTURA NORMAL", "Patrimonio Equilibrado", "#2E7D32"
            diag_soft = f"El balance conserva solidez estructural (Ratio Activos Blandos: {round(soft_ratio * 100, 1) if soft_ratio is not None else 0.0}%). Adecuado respaldo de activos duros y liquidez."

        matrix_entry = {
            "period": fy,
            "ar_sales_spread": {
                "ar_t": ar_t,
                "ar_prev": ar_prev,
                "delta_ar": round(d_ar, 6) if d_ar is not None else None,
                "delta_ar_pct": round(d_ar * 100, 2) if d_ar is not None else None,
                "rev_t": rev_t,
                "rev_prev": rev_prev,
                "delta_rev": round(d_rev, 6) if d_rev is not None else None,
                "delta_rev_pct": round(d_rev * 100, 2) if d_rev is not None else None,
                "spread": round(ar_sales_spread, 6) if ar_sales_spread is not None else None,
                "spread_pct": round(ar_sales_spread * 100, 2) if ar_sales_spread is not None else None,
                "dso": round(dso_t, 1) if dso_t is not None else None,
                "delta_dso": round(delta_dso, 1) if delta_dso is not None else None,
                "flag": flag_ar,
                "status": status_ar,
                "trap_risk": trap_ar,
                "color": color_ar,
                "diagnosis": diag_ar,
            },
            "inv_cogs_spread": {
                "inv_t": inv_t,
                "inv_prev": inv_prev,
                "delta_inv": round(d_inv, 6) if d_inv is not None else None,
                "delta_inv_pct": round(d_inv * 100, 2) if d_inv is not None else None,
                "cogs_t": cogs_t,
                "cogs_prev": cogs_prev,
                "delta_cogs": round(d_cogs, 6) if d_cogs is not None else None,
                "delta_cogs_pct": round(d_cogs * 100, 2) if d_cogs is not None else None,
                "spread": round(inv_cogs_spread, 6) if inv_cogs_spread is not None else None,
                "spread_pct": round(inv_cogs_spread * 100, 2) if inv_cogs_spread is not None else None,
                "dio": round(dio_t, 1) if dio_t is not None else None,
                "delta_dio": round(delta_dio, 1) if delta_dio is not None else None,
                "flag": flag_inv,
                "status": status_inv,
                "trap_risk": trap_inv,
                "color": color_inv,
                "diagnosis": diag_inv,
            },
            "soft_assets": {
                "total_assets": assets_t,
                "net_ppe": net_ppe_t,
                "cash": cash_t,
                "soft_assets_usd": soft_usd,
                "soft_assets_ratio": round(soft_ratio, 6) if soft_ratio is not None else None,
                "soft_assets_ratio_pct": round(soft_ratio * 100, 2) if soft_ratio is not None else None,
                "delta_soft_assets": round(delta_soft, 6) if delta_soft is not None else None,
                "delta_soft_assets_pct": round(delta_soft * 100, 2) if delta_soft is not None else None,
                "flag": flag_soft,
                "status": status_soft,
                "trap_risk": trap_soft,
                "color": color_soft,
                "diagnosis": diag_soft,
            },
        }
        aux = {
            "d_ar": d_ar,
            "d_rev": d_rev,
            "dso_t": dso_t,
            "delta_dso": delta_dso,
            "d_inv": d_inv,
            "d_cogs": d_cogs,
            "dio_t": dio_t,
            "delta_dio": delta_dio,
            "rev_t": rev_t,
            "rev_prev": rev_prev,
            "net_ppe_t": net_ppe_t,
        }
        return matrix_entry, aux

    @staticmethod
    def _compute_montier_for_period(
        fy: str,
        curr: Dict[str, Any],
        prev: Optional[Dict[str, Any]],
        ni: Optional[float],
        cfo: Optional[float],
        assets_t: Optional[float],
        assets_prev: Optional[float],
        aux: Dict[str, Optional[float]],
        is_financial: bool,
        arch_norm: str,
    ) -> Dict[str, Any]:
        """Calcula las 6 banderas del Montier C-Score (James Montier) para un período."""
        if is_financial:
            flags_bd = {
                k: {"name": nm, "condition": cond, "value_str": "N/A", "flag": None, "status": "N/A", "rationale": rat}
                for k, (nm, cond, rat) in _MONTIER_FIN_FLAGS.items()
            }
            return {
                "period": fy,
                "total_score": None,
                "max_score": 6,
                "rating": "NO APLICABLE",
                "badge": "NO APLICABLE",
                "color": "#607D8B",
                "verdict": (
                    f"Montier C-Score NO APLICABLE para entidades del arquetipo '{arch_norm}'. "
                    "El modelo de James Montier (Cooking the Books) evalúa partidas de capital de trabajo, "
                    "inventarios (DIO), cuentas a cobrar comerciales (DSO), otros activos corrientes y depreciación física de PP&E, "
                    "conceptos ajenos a la estructura operativa de intermediación financiera y balances bancarios/aseguradores."
                ),
                "flags_breakdown": flags_bd,
            }

        if prev is None:
            flags_bd = {
                k: {"name": nm, "condition": cond, "value_str": "N/D", "flag": None, "status": "N/D", "rationale": "Sin ejercicio previo para comparar."}
                for k, (nm, cond, _) in _MONTIER_FIN_FLAGS.items()
            }
            return {
                "period": fy,
                "total_score": None,
                "max_score": 6,
                "rating": "DATOS INSUFICIENTES (SIN T-1)",
                "badge": "NO EVALUABLE",
                "color": "#757575",
                "verdict": "No se dispone de ejercicio precedente (t-1) para evaluar las variaciones interanuales del Montier C-Score.",
                "flags_breakdown": flags_bd,
            }

        f1 = 1 if (ni is not None and cfo is not None and ni > cfo) else 0
        val_f1 = f"NI: ${ni/1e6:,.1f}M vs CFO: ${cfo/1e6:,.1f}M" if (ni is not None and cfo is not None) else "N/D"

        d_ar, d_rev = aux["d_ar"], aux["d_rev"]
        dso_t, delta_dso = aux["dso_t"], aux["delta_dso"]
        f2 = 1 if ((delta_dso is not None and delta_dso > 0.0) or (d_ar is not None and d_rev is not None and d_ar > d_rev)) else 0
        if dso_t is not None and delta_dso is not None:
            val_f2 = f"DSO: {round(dso_t, 1)}d (Δ: {round(delta_dso, 1):+1.1f}d)"
        elif d_ar is not None and d_rev is not None:
            val_f2 = f"ΔAR: {round(d_ar*100, 1):+.1f}% vs ΔVentas: {round(d_rev*100, 1):+.1f}%"
        else:
            val_f2 = "N/D"

        inv_raw = _safe_float(curr.get("inventory"))
        if inv_raw is None or inv_raw == 0.0:
            f3, val_f3, status_f3 = 0, "N/A (Sin Inventario)", "OK"
            rat_f3 = "Modelo de negocio sin inventario físico ni existencias de mercancía."
        else:
            d_inv, d_cogs, dio_t, delta_dio = aux["d_inv"], aux["d_cogs"], aux["dio_t"], aux["delta_dio"]
            f3 = 1 if ((delta_dio is not None and delta_dio > 0.0) or (d_inv is not None and d_cogs is not None and d_inv > d_cogs)) else 0
            if dio_t is not None and delta_dio is not None:
                val_f3 = f"DIO: {round(dio_t, 1)}d (Δ: {round(delta_dio, 1):+1.1f}d)"
            elif d_inv is not None and d_cogs is not None:
                val_f3 = f"ΔInv: {round(d_inv*100, 1):+.1f}% vs ΔCOGS: {round(d_cogs*100, 1):+.1f}%"
            else:
                val_f3 = "N/D"
            status_f3 = "FLAG" if f3 else "OK"
            rat_f3 = "Las existencias rotan más lento o crecen más rápido que los costes. Puede esconder producto no vendido o absorción de costes en inventario para inflar márgenes."

        oca_t = _safe_float(curr.get("other_current_assets"))
        oca_prev = _safe_float(prev.get("other_current_assets"))
        rev_t, rev_prev = aux["rev_t"], aux["rev_prev"]
        oca_r_t = (oca_t / rev_t) if (oca_t is not None and rev_t and rev_t > 0) else None
        oca_r_prev = (oca_prev / rev_prev) if (oca_prev is not None and rev_prev and rev_prev > 0) else None
        f4 = 1 if (oca_r_t is not None and oca_r_prev is not None and oca_r_t > (oca_r_prev + 0.001)) else 0
        val_f4 = f"Otros Act/Ventas: {round(oca_r_t*100, 2)}% vs {round(oca_r_prev*100, 2)}%" if (oca_r_t is not None and oca_r_prev is not None) else (f"{round(oca_r_t*100, 2)}%" if oca_r_t is not None else "N/D")

        dna_t = _safe_float(curr.get("depreciation_and_amortization")) or 0.0
        gross_ppe_t = _safe_float(curr.get("gross_ppe")) or ((aux["net_ppe_t"] or 0.0) + dna_t)
        depr_rate_t = (dna_t / gross_ppe_t) if gross_ppe_t > 0 else 0.0
        dna_prev = _safe_float(prev.get("depreciation_and_amortization")) or 0.0
        net_ppe_p = _safe_float(prev.get("net_ppe")) or 0.0
        gross_ppe_p = _safe_float(prev.get("gross_ppe"))
        if gross_ppe_p is None:
            gross_ppe_p = net_ppe_p + dna_prev
        depr_rate_prev = (dna_prev / gross_ppe_p) if (gross_ppe_p and gross_ppe_p > 0) else 0.0
        f5 = 1 if (depr_rate_prev > 0 and depr_rate_t < (depr_rate_prev - 0.005)) else 0
        val_f5 = f"Tasa Deprec: {round(depr_rate_t*100, 2)}% vs {round(depr_rate_prev*100, 2)}%" if depr_rate_prev > 0 else f"{round(depr_rate_t*100, 2)}%"

        assets_growth = ((assets_t - assets_prev) / abs(assets_prev)) if (assets_t is not None and assets_prev and assets_prev > 0) else None
        f6 = 1 if (assets_growth is not None and assets_growth > 0.15 and (d_rev is None or assets_growth > d_rev * 1.15)) else 0
        val_f6 = f"ΔActivos: {round(assets_growth*100, 1):+.1f}% vs ΔVentas: {round(d_rev*100, 1):+.1f}%" if (assets_growth is not None and d_rev is not None) else (f"ΔActivos: {round(assets_growth*100, 1):+.1f}%" if assets_growth is not None else "N/D")

        total_montier = f1 + f2 + f3 + f4 + f5 + f6
        if total_montier <= 1:
            m_rat, m_badge, m_color = "RIESGO MUY BAJO / LIBROS LIMPIOS", "CONTABILIDAD CONSERVADORA", "#2E7D32"
            m_verd = "La compañía supera con honores la auditoría forense. Con 0-1 banderas aisladas, la probabilidad empírica de manipulación es mínima (< 5%). Ganancias de alta calidad avaladas por caja real."
        elif total_montier == 2:
            m_rat, m_badge, m_color = "RIESGO MODERADO / ALERTA PREVENTIVA", "ZONA DE VIGILANCIA OPERATIVA", "#F57C00"
            m_verd = "Se observan 2 señales atípicas de capital de trabajo o partidas secundarias. Si bien no implica manipulación contable dolosa, amerita verificar la estacionalidad del inventario o los términos comerciales de cobro."
        elif total_montier == 3:
            m_rat, m_badge, m_color = "RIESGO MEDIO-ALTO / VIGILANCIA RIGUROSA", "ZONA DE ATENCIÓN FORENSE", "#E65100"
            m_verd = "Se activan 3 banderas de advertencia simultáneas en capital de trabajo o variaciones patrimoniales. Sugiere desfases operativos significativos que requieren seguimiento minucioso."
        else:
            m_rat, m_badge, m_color = "RIESGO ALTO / ALERTA FORENSE", "PELIGRO DE MAQUILLAJE CONTABLE", "#D32F2F"
            m_verd = "Alerta forense crítica. Se activan 4 o más banderas de alarma simultáneas (beneficios no monetizados, acumulación de balance y presión en partidas operativas). Alto riesgo de contabilidad agresiva."

        return {
            "period": fy,
            "total_score": total_montier,
            "max_score": 6,
            "rating": m_rat,
            "badge": m_badge,
            "color": m_color,
            "verdict": m_verd,
            "flags_breakdown": {
                "f1_cfo_divergence": {"name": "1. Divergencia Beneficio vs. Flujo de Caja", "condition": "Utilidad Neta > Flujo de Caja Operativo (NI > CFO)", "value_str": val_f1, "flag": bool(f1), "status": "FLAG" if f1 else "OK", "rationale": "La utilidad contable no se transforma en liquidez real. Alerta de beneficios de papel."},
                "f2_ar_vs_sales": {"name": "2. Cuentas por Cobrar vs. Ventas (DSO)", "condition": "Δ DSO > 0 (o %Δ Cuentas por Cobrar > %Δ Ventas)", "value_str": val_f2, "flag": bool(f2), "status": "FLAG" if f2 else "OK", "rationale": "El plazo de cobro se dilata o las cuentas a cobrar crecen más rápido que las ventas. Indica relajación de cobros o facturación apresurada (channel stuffing)."},
                "f3_inv_vs_cogs": {"name": "3. Inventarios vs. Coste de Ventas (DIO)", "condition": "Δ DIO > 0 (o %Δ Inventarios > %Δ Coste de Ventas)", "value_str": val_f3, "flag": bool(f3), "status": status_f3, "rationale": rat_f3},
                "f4_other_current_assets": {"name": "4. Otros Activos Corrientes vs. Ventas", "condition": "Ratio Otros Act. Ctes/Ventas_t > Ratio Otros Act. Ctes/Ventas_t-1", "value_str": val_f4, "flag": bool(f4), "status": "FLAG" if f4 else "OK", "rationale": "Incremento del peso relativo de otros activos corrientes. Alerta de partidas dudosas o cargos diferidos ocultos fuera de clientes e inventarios."},
                "f5_depreciation_rate": {"name": "5. Reducción de la Tasa de Depreciación", "condition": "Tasa Depreciación_t < Tasa Depreciación_t-1", "value_str": val_f5, "flag": bool(f5), "status": "FLAG" if f5 else "OK", "rationale": "Reducción de la amortización contable respecto a los activos brutos, inflando el beneficio neto al estirar vidas útiles estimadas."},
                "f6_asset_growth": {"name": "6. Crecimiento Excesivo de Activos Totales", "condition": "Δ Activos > 15.0% y Δ Activos > 1.15 * Δ Ventas", "value_str": val_f6, "flag": bool(f6), "status": "FLAG" if f6 else "OK", "rationale": "Expansión desproporcionada de balance no respaldada por ventas. Montier advierte que suele utilizarse para disimular debilidad orgánica o acumulación de partidas improductivas."},
            },
        }

    @staticmethod
    def _build_global_forensic_verdict(
        arch_norm: str,
        is_financial: bool,
        latest_sloan: Dict[str, Any],
        latest_montier: Dict[str, Any],
    ) -> Tuple[str, str, str]:
        """Consolida el dictamen forense global del período más reciente."""
        if is_financial:
            return (
                f"AUDITORÍA FORENSE ADAPTADA ({arch_norm}): Los modelos cuantitativos de devengos industriales y Montier C-Score no son aplicables a balances bancarios y aseguradores. La solvencia e integridad contable se evalúan mediante la calidad de cartera (NPLs), ratios de cobertura de provisiones, margen de interés neto (NIM) y solidez de capital regulatorio (CET1).",
                "#607D8B",
                "ANÁLISIS SECTORIAL BANCARIO",
            )
        sloan_rat = latest_sloan.get("sloan_ratio")
        raw_montier = latest_montier.get("total_score")
        if raw_montier is None:
            if sloan_rat is not None and sloan_rat < -0.03:
                return (
                    f"CALIDAD DE BENEFICIOS EXCEPCIONAL (GRADO INSTITUCIONAL): Conversión de efectivo sobresaliente (Ratio Sloan: {latest_sloan.get('sloan_ratio_pct')}%, CFO > Utilidad Neta). Montier C-Score pendiente de serie histórica completa (sin ejercicio precedente t-1).",
                    "#2E7D32",
                    "MÁXIMA CALIDAD CONTABLE",
                )
            return (
                f"EVALUACIÓN FORENSE PARCIAL: Ratio Sloan {latest_sloan.get('sloan_ratio_pct')}%. Montier C-Score no disponible por falta de ejercicio precedente (t-1).",
                "#757575",
                "DATOS PARCIALES",
            )
        montier_sc = int(raw_montier)
        if sloan_rat is not None and sloan_rat < -0.03 and montier_sc <= 2:
            return (
                f"CALIDAD DE BENEFICIOS EXCEPCIONAL (GRADO INSTITUCIONAL): Conversión de efectivo sobresaliente (Ratio Sloan: {latest_sloan.get('sloan_ratio_pct')}%, CFO > Utilidad Neta), devengos negativos que suprimen riesgo de inflación contable y Montier C-Score de {montier_sc}/6 que descarta maniobras de manipulación deliberada.",
                "#2E7D32",
                "MÁXIMA CALIDAD CONTABLE",
            )
        if sloan_rat is not None and -0.03 <= sloan_rat <= 0.07 and montier_sc <= 3:
            return (
                f"CONTABILIDAD SALUDABLE Y EQUILIBRADA: Devengos dentro de la banda histórica normal (Ratio Sloan: {latest_sloan.get('sloan_ratio_pct')}%) y Montier C-Score de {montier_sc}/6. Los resultados financieros reflejan razonablemente la realidad económica de las operaciones.",
                "#1976D2",
                "ESTÁNDAR SALUDABLE",
            )
        if montier_sc >= 4 or (sloan_rat is not None and sloan_rat > 0.10):
            return (
                f"ALERTA FORENSE POR CALIDAD DE RESULTADOS: Detección de devengos desproporcionados (Ratio Sloan: {latest_sloan.get('sloan_ratio_pct')}%) o Montier C-Score elevado ({montier_sc}/6). Se recomienda auditoría minuciosa de políticas contables, partidas no monetarias y devengos acumulados.",
                "#D32F2F",
                "ALERTA FORENSE",
            )
        return (
            f"ZONA DE VIGILANCIA POR DESFASES OPERATIVOS: Montier C-Score de {montier_sc}/6 con divergencias puntuales en capital de trabajo. Revisar ciclos estacionales de inventarios y condiciones comerciales de cobro.",
            "#F57C00",
            "ZONA DE VIGILANCIA",
        )

    @classmethod
    def calculate_forensic_series(
        cls,
        fiscal_years: List[str],
        period_metrics: Dict[str, Dict[str, Any]],
        benchmarks: Optional[Dict[str, Any]] = None,
        ticker: str = "",
        archetype: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Calcula la serie histórica completa y LTM para los tres instrumentos forenses."""
        raw_arch = archetype or (benchmarks.get("archetype") if benchmarks else None) or "STANDARD_CORPORATE"
        arch_norm = normalize_archetype(raw_arch, default="STANDARD_CORPORATE")
        is_financial = arch_norm in ("FINANCIAL_BANKING", "INSURANCE")
        annual_fys_sorted = _chronological_annual_fys(fiscal_years)

        sloan_analysis: Dict[str, Any] = {}
        divergence_matrix: Dict[str, Any] = {}
        montier_analysis: Dict[str, Any] = {}

        for fy in fiscal_years:
            curr = period_metrics.get(fy, {})
            if fy == "LTM":
                prev_fy = annual_fys_sorted[-1] if annual_fys_sorted else None
            elif fy in annual_fys_sorted and annual_fys_sorted.index(fy) >= 1:
                prev_fy = annual_fys_sorted[annual_fys_sorted.index(fy) - 1]
            else:
                prev_fy = None
            prev = period_metrics.get(prev_fy) if prev_fy else None

            ni = _safe_float(curr.get("net_income"))
            cfo = _safe_float(curr.get("cfo"))
            assets_t = _safe_float(curr.get("total_assets"))
            assets_prev = _safe_float(prev.get("total_assets")) if prev else None
            avg_assets = ((assets_t + assets_prev) / 2.0) if (assets_t and assets_prev and assets_t > 0 and assets_prev > 0) else assets_t

            sloan_analysis[fy] = cls._compute_sloan_for_period(fy, prev_fy, ni, cfo, assets_t, avg_assets, is_financial)
            div_entry, aux = cls._compute_divergences_for_period(fy, curr, prev, assets_t, assets_prev, is_financial, arch_norm)
            divergence_matrix[fy] = div_entry
            montier_analysis[fy] = cls._compute_montier_for_period(fy, curr, prev, ni, cfo, assets_t, assets_prev, aux, is_financial, arch_norm)

        recent_period = "LTM" if "LTM" in fiscal_years else (fiscal_years[0] if fiscal_years else "N/A")
        latest_sloan = sloan_analysis.get(recent_period, {})
        latest_div = divergence_matrix.get(recent_period, {})
        latest_montier = montier_analysis.get(recent_period, {})
        global_verdict, global_color, global_badge = cls._build_global_forensic_verdict(arch_norm, is_financial, latest_sloan, latest_montier)

        return {
            "ticker": ticker.upper(),
            "periods": fiscal_years,
            "recent_period": recent_period,
            "sloan_accrual_analysis": sloan_analysis,
            "divergence_matrix": divergence_matrix,
            "montier_c_score": montier_analysis,
            "latest_result": {
                "period": recent_period,
                "sloan_accrual": latest_sloan,
                "divergences": latest_div,
                "montier_c_score": latest_montier,
                "forensic_verdict": global_verdict,
                "global_color": global_color,
                "global_badge": global_badge,
            },
        }
