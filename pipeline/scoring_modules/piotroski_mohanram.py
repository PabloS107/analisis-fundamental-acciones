"""
piotroski_mohanram.py - Calculadores institucionales de Piotroski F-Score (0-9),
Mohanram G-Score (0-8) y Matriz Combinada F/G.
"""

import math
from typing import Any, Dict, List, Optional, Tuple

from .scoring_utils import _safe_float


def _f_signal(
    name: str,
    category: str,
    value: Optional[float],
    formatted_value: str,
    comparison_label: str,
    threshold: str,
    passed: bool,
    description: str,
) -> Dict[str, Any]:
    """Construye una entrada estandarizada de señal para Piotroski F-Score."""
    return {
        "name": name,
        "category": category,
        "value": value,
        "formatted_value": formatted_value,
        "comparison_label": comparison_label,
        "threshold": threshold,
        "passed": passed,
        "points": 1 if passed else 0,
        "description": description,
    }


def _g_signal(
    name: str,
    category: str,
    value: Optional[float],
    formatted_value: str,
    comparison_label: str,
    benchmark: str,
    passed: bool,
    description: str,
) -> Dict[str, Any]:
    """Construye una entrada estandarizada de señal para Mohanram G-Score."""
    return {
        "name": name,
        "category": category,
        "value": value,
        "formatted_value": formatted_value,
        "comparison_label": comparison_label,
        "benchmark": benchmark,
        "passed": passed,
        "points": 1 if passed else 0,
        "description": description,
    }


class PiotroskiScoreCalculator:
    """Calculador canónico del Piotroski F-Score (2000) con mejoras de deuda total y acciones básicas."""

    @staticmethod
    def _profitability_signals(
        ni_t: Optional[float],
        cfo_t: Optional[float],
        assets_t: Optional[float],
        ni_prev: Optional[float],
        assets_prev: Optional[float],
        assets_prev2: Optional[float],
    ) -> Tuple[Dict[str, Any], int, Optional[float], Optional[float]]:
        """Calcula las 4 señales de rentabilidad (F_ROA, F_CFO, F_dROA, F_ACCRUAL)."""
        avg_assets_t = (
            ((assets_t + assets_prev) / 2.0)
            if (assets_t and assets_prev and assets_prev > 0)
            else (assets_t or assets_prev)
        )
        avg_assets_prev = (
            ((assets_prev + assets_prev2) / 2.0)
            if (assets_prev and assets_prev2 and assets_prev2 > 0)
            else assets_prev
        )

        roa_denom = avg_assets_t if (avg_assets_t and avg_assets_t > 0) else (assets_prev if assets_prev and assets_prev > 0 else assets_t)
        roa_t = (ni_t / roa_denom) if (ni_t is not None and roa_denom and roa_denom > 0) else None
        pass_roa = bool(roa_t is not None and roa_t > 0)

        pass_cfo = bool(cfo_t is not None and cfo_t > 0)

        roa_prev_denom = avg_assets_prev if (avg_assets_prev and avg_assets_prev > 0) else (assets_prev2 if assets_prev2 and assets_prev2 > 0 else assets_prev)
        roa_prev = (ni_prev / roa_prev_denom) if (ni_prev is not None and roa_prev_denom and roa_prev_denom > 0) else None
        delta_roa = (roa_t - roa_prev) if (roa_t is not None and roa_prev is not None) else None
        pass_droa = bool(delta_roa is not None and delta_roa > 0)

        pass_accrual = bool(cfo_t is not None and ni_t is not None and cfo_t > ni_t)
        accrual_diff = (cfo_t - ni_t) if (cfo_t is not None and ni_t is not None) else None

        signals = {
            "F_ROA": _f_signal(
                "ROA Positivo",
                "Rentabilidad",
                roa_t,
                f"{roa_t*100:.2f}%" if roa_t is not None else "N/A",
                f"{roa_t*100:.2f}% > 0%" if roa_t is not None else "N/A",
                "> 0.00%",
                pass_roa,
                "Utilidad neta positiva sobre la base de activos promedio instalados.",
            ),
            "F_CFO": _f_signal(
                "CFO Positivo",
                "Rentabilidad",
                cfo_t,
                f"${cfo_t/1e6:,.1f}M" if cfo_t is not None else "N/A",
                f"${cfo_t/1e6:,.1f}M > $0" if cfo_t is not None else "N/A",
                "> $0M",
                pass_cfo,
                "Flujo de caja operativo neto positivo.",
            ),
            "F_dROA": _f_signal(
                "Mejora de ROA (Delta ROA)",
                "Rentabilidad",
                delta_roa,
                f"{delta_roa*100:+.2f}%" if delta_roa is not None else "N/A",
                (
                    f"{roa_t*100:.1f}% vs {roa_prev*100:.1f}% ({delta_roa*100:+.2f}%)"
                    if (roa_t is not None and roa_prev is not None)
                    else (f"{delta_roa*100:+.2f}%" if delta_roa is not None else "N/A")
                ),
                "> 0.00%",
                pass_droa,
                "Aceleración de la rentabilidad sobre activos frente al año previo.",
            ),
            "F_ACCRUAL": _f_signal(
                "Calidad Contable (CFO > NI)",
                "Rentabilidad",
                accrual_diff,
                f"${accrual_diff/1e6:+,.1f}M" if accrual_diff is not None else "N/A",
                f"CFO ${cfo_t/1e6:,.1f}M > NI ${ni_t/1e6:,.1f}M" if (cfo_t is not None and ni_t is not None) else "N/A",
                "CFO > Utilidad Neta",
                pass_accrual,
                "Beneficios respaldados por efectivo contante (bajos devengos contables).",
            ),
        }
        pts = sum(s["points"] for s in signals.values())
        return signals, pts, avg_assets_t, avg_assets_prev

    @staticmethod
    def _leverage_and_liquidity_signals(
        debt_t: Optional[float],
        assets_t: Optional[float],
        debt_prev: Optional[float],
        assets_prev: Optional[float],
        ca_t: Optional[float],
        cl_t: Optional[float],
        ca_prev: Optional[float],
        cl_prev: Optional[float],
        shares_t: Optional[float],
        shares_prev: Optional[float],
    ) -> Tuple[Dict[str, Any], int]:
        """Calcula las 3 señales de capital, deuda y liquidez (F_dLEVER, F_dLIQUID, EQ_OFFER)."""
        lev_t = (debt_t / assets_t) if (debt_t is not None and assets_t and assets_t > 0) else None
        lev_prev = (debt_prev / assets_prev) if (debt_prev is not None and assets_prev and assets_prev > 0) else None
        delta_lev = (lev_t - lev_prev) if (lev_t is not None and lev_prev is not None) else None
        pass_dlever = bool(delta_lev is not None and delta_lev <= 0.0001)

        cr_t = (ca_t / cl_t) if (ca_t is not None and cl_t and cl_t > 0) else None
        cr_prev = (ca_prev / cl_prev) if (ca_prev is not None and cl_prev and cl_prev > 0) else None
        delta_cr = (cr_t - cr_prev) if (cr_t is not None and cr_prev is not None) else None
        pass_dliquid = bool(delta_cr is not None and delta_cr > 0)

        delta_shares = (shares_t - shares_prev) if (shares_t is not None and shares_prev is not None) else None
        shares_base = shares_prev if (shares_prev is not None and shares_prev > 0) else (shares_t or 0.0)
        pass_eq_offer = bool(delta_shares is not None and delta_shares <= 0.0001 * shares_base)

        signals = {
            "F_dLEVER": _f_signal(
                "Desendeudamiento Total",
                "Apalancamiento y Liquidez",
                delta_lev,
                f"{delta_lev*100:+.2f}%" if delta_lev is not None else "N/A",
                (
                    f"Deuda {lev_t*100:.1f}% vs {lev_prev*100:.1f}% ({delta_lev*100:+.2f}%)"
                    if (lev_t is not None and lev_prev is not None)
                    else (f"{delta_lev*100:+.2f}%" if delta_lev is not None else "N/A")
                ),
                "Delta Deuda Total <= 0%",
                pass_dlever,
                "Reducción o estabilidad del apalancamiento financiero total sobre activos.",
            ),
            "F_dLIQUID": _f_signal(
                "Mejora de Razón Corriente",
                "Apalancamiento y Liquidez",
                delta_cr,
                f"{delta_cr:+.3f}x" if delta_cr is not None else "N/A",
                (
                    f"CR {cr_t:.2f}x vs {cr_prev:.2f}x ({delta_cr:+.2f}x)"
                    if (cr_t is not None and cr_prev is not None)
                    else (f"{delta_cr:+.2f}x" if delta_cr is not None else "N/A")
                ),
                "Delta Current Ratio > 0x",
                pass_dliquid,
                "Mayor cobertura de pasivos a corto plazo con activos corrientes.",
            ),
            "EQ_OFFER": _f_signal(
                "Cero Dilución (Acciones Básicas)",
                "Apalancamiento y Liquidez",
                delta_shares,
                f"{delta_shares/1e6:+,.1f}M acciones" if delta_shares is not None else "N/A",
                (
                    f"Acc {shares_t/1e6:,.0f}M vs {shares_prev/1e6:,.0f}M ({delta_shares/1e6:+,.0f}M)"
                    if (shares_t is not None and shares_prev is not None)
                    else (f"{delta_shares/1e6:+,.0f}M" if delta_shares is not None else "N/A")
                ),
                "Delta Acciones Básicas <= 0.01% del capital previo",
                pass_eq_offer,
                "Sin emisión neta dilutiva de capital; recompra de acciones o estabilidad.",
            ),
        }
        return signals, sum(s["points"] for s in signals.values())

    @staticmethod
    def _efficiency_signals(
        gp_t: Optional[float],
        rev_t: Optional[float],
        gp_prev: Optional[float],
        rev_prev: Optional[float],
        assets_t: Optional[float],
        assets_prev: Optional[float],
        assets_prev2: Optional[float],
        avg_assets_t: Optional[float],
        avg_assets_prev: Optional[float],
    ) -> Tuple[Dict[str, Any], int]:
        """Calcula las 2 señales de eficiencia operativa (F_dMARGIN, F_dTURN)."""
        gm_t = (gp_t / rev_t) if (gp_t is not None and rev_t and rev_t > 0) else None
        gm_prev = (gp_prev / rev_prev) if (gp_prev is not None and rev_prev and rev_prev > 0) else None
        delta_gm = (gm_t - gm_prev) if (gm_t is not None and gm_prev is not None) else None
        pass_dmargin = bool(delta_gm is not None and delta_gm > 0)

        turn_t_denom = avg_assets_t if (avg_assets_t and avg_assets_t > 0) else (assets_prev if assets_prev and assets_prev > 0 else assets_t)
        turn_t = (rev_t / turn_t_denom) if (rev_t is not None and turn_t_denom and turn_t_denom > 0) else None
        turn_prev_denom = avg_assets_prev if (avg_assets_prev and avg_assets_prev > 0) else (assets_prev2 if assets_prev2 and assets_prev2 > 0 else assets_prev)
        turn_prev = (rev_prev / turn_prev_denom) if (rev_prev is not None and turn_prev_denom and turn_prev_denom > 0) else None
        delta_turn = (turn_t - turn_prev) if (turn_t is not None and turn_prev is not None) else None
        pass_dturn = bool(delta_turn is not None and delta_turn > 0)

        signals = {
            "F_dMARGIN": _f_signal(
                "Expansión de Margen Bruto",
                "Eficiencia Operativa",
                delta_gm,
                f"{delta_gm*100:+.2f}%" if delta_gm is not None else "N/A",
                (
                    f"MB {gm_t*100:.1f}% vs {gm_prev*100:.1f}% ({delta_gm*100:+.2f}%)"
                    if (gm_t is not None and gm_prev is not None)
                    else (f"{delta_gm*100:+.2f}%" if delta_gm is not None else "N/A")
                ),
                "Delta Margen Bruto > 0%",
                pass_dmargin,
                "Mayor poder de fijación de precios o menor coste unitario de ventas.",
            ),
            "F_dTURN": _f_signal(
                "Expansión Rotación de Activos",
                "Eficiencia Operativa",
                delta_turn,
                f"{delta_turn:+.3f}x" if delta_turn is not None else "N/A",
                (
                    f"Rot {turn_t:.2f}x vs {turn_prev:.2f}x ({delta_turn:+.2f}x)"
                    if (turn_t is not None and turn_prev is not None)
                    else (f"{delta_turn:+.2f}x" if delta_turn is not None else "N/A")
                ),
                "Delta Rotación > 0x",
                pass_dturn,
                "Mayor volumen de ingresos generado por cada dólar de activo instalado.",
            ),
        }
        return signals, sum(s["points"] for s in signals.values())

    @classmethod
    def calculate_year(
        cls,
        period: str,
        current_data: Dict[str, float],
        prev_data: Optional[Dict[str, float]],
        prev2_data: Optional[Dict[str, float]],
    ) -> Dict[str, Any]:
        """Calcula los 9 criterios del Piotroski F-Score para un período dado."""
        ni_t = _safe_float(current_data.get("net_income"))
        cfo_t = _safe_float(current_data.get("cfo"))
        assets_t = _safe_float(current_data.get("total_assets"))
        debt_t = _safe_float(current_data.get("total_debt"))
        ca_t = _safe_float(current_data.get("current_assets"))
        cl_t = _safe_float(current_data.get("current_liabilities"))
        shares_t = _safe_float(current_data.get("basic_shares"))
        gp_t = _safe_float(current_data.get("gross_profit"))
        rev_t = _safe_float(current_data.get("revenue"))

        ni_prev = _safe_float(prev_data.get("net_income")) if prev_data else None
        assets_prev = _safe_float(prev_data.get("total_assets")) if prev_data else None
        debt_prev = _safe_float(prev_data.get("total_debt")) if prev_data else None
        ca_prev = _safe_float(prev_data.get("current_assets")) if prev_data else None
        cl_prev = _safe_float(prev_data.get("current_liabilities")) if prev_data else None
        shares_prev = _safe_float(prev_data.get("basic_shares")) if prev_data else None
        gp_prev = _safe_float(prev_data.get("gross_profit")) if prev_data else None
        rev_prev = _safe_float(prev_data.get("revenue")) if prev_data else None
        assets_prev2 = _safe_float(prev2_data.get("total_assets")) if prev2_data else None

        s_prof, p1, avg_t, avg_prev = cls._profitability_signals(ni_t, cfo_t, assets_t, ni_prev, assets_prev, assets_prev2)
        s_lev, p2 = cls._leverage_and_liquidity_signals(
            debt_t, assets_t, debt_prev, assets_prev, ca_t, cl_t, ca_prev, cl_prev, shares_t, shares_prev
        )
        s_eff, p3 = cls._efficiency_signals(gp_t, rev_t, gp_prev, rev_prev, assets_t, assets_prev, assets_prev2, avg_t, avg_prev)

        score = p1 + p2 + p3
        if score >= 8:
            rating, color, summary = "SALUD EXCEPCIONAL", "GREEN", "Solidez financiera de primer nivel institucional. Calidad de balance óptima."
        elif score >= 6:
            rating, color, summary = "SALUD SÓLIDA", "GREEN_LIGHT", "Finanzas saludables y balance robusto con áreas menores de optimización."
        elif score >= 5:
            rating, color, summary = "SALUD MODERADA", "YELLOW", "Desempeño financiero equilibrado, monitorear márgenes o apalancamiento."
        else:
            rating, color, summary = "VULNERABILIDAD FINANCIERA", "RED", "Alerta de estrés operativo, dilución o deterioro de liquidez."

        return {
            "period": period,
            "signals": {**s_prof, **s_lev, **s_eff},
            "total_score": score,
            "max_score": 9,
            "rating": rating,
            "status_color": color,
            "summary_text": summary,
        }


class MohanramScoreCalculator:
    """Calculador del Mohanram G-Score (2005) adaptado con benchmarks sectoriales y mejoras modernas."""

    @staticmethod
    def _sector_profitability_signals(
        ni_t: Optional[float],
        cfo_t: Optional[float],
        assets_denom: Optional[float],
        benchmarks: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], Optional[float], int]:
        """Calcula G1_ROA, G2_CFROA y G3_ACCRUAL."""
        roa_t = (ni_t / assets_denom) if (ni_t is not None and assets_denom and assets_denom > 0) else None
        med_roa = benchmarks.get("median_roa", 0.055)
        pass_g1 = bool(roa_t is not None and roa_t > med_roa)

        cfroa_t = (cfo_t / assets_denom) if (cfo_t is not None and assets_denom and assets_denom > 0) else None
        med_cfroa = benchmarks.get("median_cfroa", 0.078)
        pass_g2 = bool(cfroa_t is not None and cfroa_t > med_cfroa)

        pass_g3 = bool(cfo_t is not None and ni_t is not None and cfo_t > ni_t)
        diff_cfo_ni = (cfo_t - ni_t) if (cfo_t is not None and ni_t is not None) else None

        signals = {
            "G1_ROA": _g_signal(
                "ROA > Mediana del Sector",
                "Rentabilidad vs Sector",
                roa_t,
                f"{roa_t*100:.2f}%" if roa_t is not None else "N/A",
                f"ROA {roa_t*100:.2f}% vs Med {med_roa*100:.2f}%" if roa_t is not None else "N/A",
                f"{med_roa*100:.2f}%",
                pass_g1,
                "Rentabilidad sobre activos superior a la mitad del sector.",
            ),
            "G2_CFROA": _g_signal(
                "CFROA > Mediana del Sector",
                "Rentabilidad vs Sector",
                cfroa_t,
                f"{cfroa_t*100:.2f}%" if cfroa_t is not None else "N/A",
                f"CFROA {cfroa_t*100:.2f}% vs Med {med_cfroa*100:.2f}%" if cfroa_t is not None else "N/A",
                f"{med_cfroa*100:.2f}%",
                pass_g2,
                "Generación de caja operativa sobre activos líder en la industria.",
            ),
            "G3_ACCRUAL": _g_signal(
                "Calidad Contable (CFO > NI)",
                "Rentabilidad vs Sector",
                diff_cfo_ni,
                f"${diff_cfo_ni/1e6:+,.1f}M" if diff_cfo_ni is not None else "N/A",
                f"CFO ${cfo_t/1e6:,.1f}M > NI ${ni_t/1e6:,.1f}M" if (cfo_t is not None and ni_t is not None) else "N/A",
                "CFO > Utilidad",
                pass_g3,
                "Flujo de caja operativo superior a las ganancias devengadas.",
            ),
        }
        return signals, roa_t, sum(s["points"] for s in signals.values())

    @staticmethod
    def _stability_signals(
        roa_t: Optional[float],
        rev_t: Optional[float],
        rev_prev: Optional[float],
        historical_series: List[Dict[str, Any]],
        benchmarks: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], int]:
        """Calcula G4_VAR_ROA y G5_VAR_GROWTH."""
        hist_roas = [
            item["net_income"] / item["total_assets"]
            for item in historical_series
            if item.get("net_income") is not None and item.get("total_assets") and item["total_assets"] > 0
        ]
        cv_roa = None
        pass_g4 = False
        p75_roa_bm = benchmarks.get("p75_roa", 0.100)
        med_cv_roa = benchmarks.get("median_cv_roa", 0.38)
        if len(hist_roas) >= 2:
            mean_roa = sum(hist_roas) / len(hist_roas)
            var_roa = sum((x - mean_roa) ** 2 for x in hist_roas) / (len(hist_roas) - 1)
            cv_roa = (math.sqrt(var_roa) / mean_roa) if (mean_roa and mean_roa > 0) else 1.0
            pass_g4 = (cv_roa < med_cv_roa) or (roa_t is not None and roa_t >= p75_roa_bm)
        elif roa_t is not None and roa_t >= p75_roa_bm:
            pass_g4 = True

        hist_growths = [
            (historical_series[i]["revenue"] - historical_series[i - 1]["revenue"]) / historical_series[i - 1]["revenue"]
            for i in range(1, len(historical_series))
            if historical_series[i].get("revenue") and historical_series[i - 1].get("revenue") and historical_series[i - 1]["revenue"] > 0
        ]
        cv_growth = None
        pass_g5 = False
        med_cv_growth = benchmarks.get("median_cv_sales_growth", 0.42)
        if len(hist_growths) >= 2:
            mean_g = sum(hist_growths) / len(hist_growths)
            var_g = sum((x - mean_g) ** 2 for x in hist_growths) / (len(hist_growths) - 1)
            cv_growth = (math.sqrt(var_g) / mean_g) if (mean_g and mean_g > 0) else 1.0
            pass_g5 = (cv_growth < med_cv_growth) or (mean_g >= 0.20)
        elif rev_t and rev_prev and rev_prev > 0 and ((rev_t - rev_prev) / rev_prev) >= 0.20:
            pass_g5 = True

        signals = {
            "G4_VAR_ROA": _g_signal(
                "Estabilidad / Nivel Superior de ROA",
                "Estabilidad y Predictibilidad",
                cv_roa,
                f"CV={cv_roa:.2f}" if cv_roa is not None else ("P75 Líder" if pass_g4 else "N/A"),
                f"CV {cv_roa:.2f} < {med_cv_roa:.2f} (o P75)" if cv_roa is not None else ("P75 Líder" if pass_g4 else "N/A"),
                f"CV < {med_cv_roa:.2f} o ROA >= {p75_roa_bm*100:.2f}%",
                pass_g4,
                "Baja volatilidad en rentabilidad o nivel de retorno permanentemente en percentil 75 superior.",
            ),
            "G5_VAR_GROWTH": _g_signal(
                "Estabilidad / Aceleración de Ventas",
                "Estabilidad y Predictibilidad",
                cv_growth,
                f"CV={cv_growth:.2f}" if cv_growth is not None else ("Hipercrecimiento" if pass_g5 else "N/A"),
                f"CV {cv_growth:.2f} vs {med_cv_growth:.2f}" if cv_growth is not None else ("g >= 20%" if pass_g5 else "N/A"),
                f"CV < {med_cv_growth:.2f} o Crecimiento >= 20%",
                pass_g5,
                "Trayectoria predecible de ingresos o expansión acelerada superior al 20% anual.",
            ),
        }
        return signals, sum(s["points"] for s in signals.values())

    @staticmethod
    def _reinvestment_signals(
        rd_t: float,
        capex_t: float,
        assets_denom: Optional[float],
        rev_t: Optional[float],
        rev_prev: Optional[float],
        sga_t: Optional[float],
        sga_prev: Optional[float],
        benchmarks: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], int]:
        """Calcula G6_RD_INTENSITY, G7_CAPEX_INTENSITY y G8_OPERATING_LEVERAGE."""
        rd_intensity = (rd_t / assets_denom) if (rd_t and assets_denom and assets_denom > 0) else 0.0
        med_rd = benchmarks.get("median_rd_intensity", 0.035)
        pass_g6 = bool(rd_intensity > med_rd)

        capex_intensity = (capex_t / assets_denom) if (capex_t and assets_denom and assets_denom > 0) else 0.0
        total_reinvestment = ((capex_t + rd_t) / assets_denom) if (assets_denom and assets_denom > 0) else 0.0
        if benchmarks.get("is_asset_light", False):
            med_reinv = benchmarks.get("median_total_reinvestment", 0.080)
            pass_g7 = bool(total_reinvestment > med_reinv)
            g7_val = total_reinvestment
            g7_fmt = f"{total_reinvestment*100:.2f}% (Total)"
            g7_bm = f"> {med_reinv*100:.2f}% (I+D+CapEx)"
            g7_desc = "Tasa de Inversión Total en Crecimiento (I+D + CapEx) para modelos ligeros en activos."
            g7_comp = f"Reinv {total_reinvestment*100:.2f}% vs Med {med_reinv*100:.2f}%"
        else:
            med_capex = benchmarks.get("median_capex_intensity", 0.045)
            pass_g7 = bool(capex_intensity > med_capex)
            g7_val = capex_intensity
            g7_fmt = f"{capex_intensity*100:.2f}% (CapEx)"
            g7_bm = f"> {med_capex*100:.2f}%"
            g7_desc = "Reinversión en infraestructura de capital físico (CapEx) sobre activos."
            g7_comp = f"CapEx {capex_intensity*100:.2f}% vs Med {med_capex*100:.2f}%"

        growth_rev = ((rev_t - rev_prev) / rev_prev) if (rev_t is not None and rev_prev is not None and rev_prev > 0) else None
        growth_sga = ((sga_t - sga_prev) / sga_prev) if (sga_t is not None and sga_prev is not None and sga_prev > 0) else None
        pass_g8 = bool(growth_rev > growth_sga) if (growth_rev is not None and growth_sga is not None) else bool(growth_rev is not None and growth_rev > 0)
        diff_growth = (growth_rev - growth_sga) if (growth_rev is not None and growth_sga is not None) else None

        signals = {
            "G6_RD_INTENSITY": _g_signal(
                "Intensidad en I+D vs Sector",
                "Inversión en Futuro e Intangibles",
                rd_intensity,
                f"{rd_intensity*100:.2f}%",
                f"I+D {rd_intensity*100:.2f}% vs Med {med_rd*100:.2f}%",
                f"> {med_rd*100:.2f}%",
                pass_g6,
                "Reinversión en investigación y desarrollo para fortalecer ventajas competitivas (moats).",
            ),
            "G7_CAPEX_INTENSITY": _g_signal(
                "Reinversión de Capital / Asset-Light",
                "Inversión en Futuro e Intangibles",
                g7_val,
                g7_fmt,
                g7_comp,
                g7_bm,
                pass_g7,
                g7_desc,
            ),
            "G8_OPERATING_LEVERAGE": _g_signal(
                "Apalancamiento Comercial (SG&A)",
                "Inversión en Futuro e Intangibles",
                diff_growth,
                f"Ventas: {growth_rev*100:+.1f}% vs SG&A: {growth_sga*100:+.1f}%" if (growth_rev is not None and growth_sga is not None) else "N/A",
                f"Vtas {growth_rev*100:+.1f}% vs SG&A {growth_sga*100:+.1f}%" if (growth_rev is not None and growth_sga is not None) else "N/A",
                "% Delta Ventas > % Delta SG&A",
                pass_g8,
                "Eficiencia comercial: ingresos escalan con mayor dinamismo que los gastos administrativos y de ventas.",
            ),
        }
        return signals, sum(s["points"] for s in signals.values())

    @classmethod
    def calculate_year(
        cls,
        period: str,
        current_data: Dict[str, float],
        prev_data: Optional[Dict[str, float]],
        historical_series: List[Dict[str, Any]],
        benchmarks: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Calcula los 8 criterios del Mohanram G-Score comparados frente a medianas sectoriales."""
        ni_t = _safe_float(current_data.get("net_income"))
        cfo_t = _safe_float(current_data.get("cfo"))
        assets_t = _safe_float(current_data.get("total_assets"))
        assets_prev = _safe_float(prev_data.get("total_assets")) if prev_data else assets_t
        assets_denom = assets_prev if (assets_prev and assets_prev > 0) else assets_t
        rd_t = _safe_float(current_data.get("rd_expense")) or 0.0
        capex_t = _safe_float(current_data.get("capex")) or 0.0
        sga_t = _safe_float(current_data.get("sga_expense"))
        sga_prev = _safe_float(prev_data.get("sga_expense")) if prev_data else None
        rev_t = _safe_float(current_data.get("revenue"))
        rev_prev = _safe_float(prev_data.get("revenue")) if prev_data else None

        s_prof, roa_t, p1 = cls._sector_profitability_signals(ni_t, cfo_t, assets_denom, benchmarks)
        s_stab, p2 = cls._stability_signals(roa_t, rev_t, rev_prev, historical_series, benchmarks)
        s_reinv, p3 = cls._reinvestment_signals(rd_t, capex_t, assets_denom, rev_t, rev_prev, sga_t, sga_prev, benchmarks)

        score = p1 + p2 + p3
        if score >= 6:
            rating, color, summary = "CRECIMIENTO DE ÉLITE", "GREEN", "Liderazgo superior en rentabilidad, alta reinversión y ventajas competitivas sostenibles."
        elif score >= 4:
            rating, color, summary = "CRECIMIENTO PROMEDIO", "YELLOW", "Desempeño en línea con la mediana de la industria; vigilar reinversión o volatilidad."
        else:
            rating, color, summary = "CRECIMIENTO FRÁGIL", "RED", "Retornos rezagados frente a competidores o crecimiento inestable/destructivo de capital."

        return {
            "period": period,
            "signals": {**s_prof, **s_stab, **s_reinv},
            "total_score": score,
            "max_score": 8,
            "rating": rating,
            "status_color": color,
            "benchmark_info": {
                "sic_code": benchmarks.get("sic_code", "0000"),
                "industry_name": benchmarks.get("industry_name", "Broad Market"),
                "is_asset_light": benchmarks.get("is_asset_light", False),
            },
            "summary_text": summary,
        }


class CombinedMatrixClassifier:
    """Clasifica la empresa en la matriz estratégica 2x2 F-Score vs G-Score."""

    @staticmethod
    def classify(f_score: int, g_score: int) -> Dict[str, Any]:
        """Ubica la combinación F-Score / G-Score en los 4 cuadrantes estratégicos."""
        if f_score >= 6 and g_score >= 6:
            quadrant = "CUADRANTE I: COMPOUNDER DE ÉLITE"
            badge = "💎 COMPOUNDER DE ÉLITE"
            color = "GREEN"
            thesis = (
                "Compañía excepcional: Combina sólida salud financiera intrínseca, balance robusto, generación líquida de caja "
                "y desendeudamiento (F-Score sólido >= 6) con superioridad competitiva, disciplina en I+D y crecimiento "
                "por encima de la mediana del sector (G-Score destacado >= 6). Perfil ideal para inversión a largo plazo."
            )
        elif f_score < 6 and g_score >= 6:
            quadrant = "CUADRANTE II: CRECIMIENTO VULNERABLE"
            badge = "⚠️ CRECIMIENTO VULNERABLE"
            color = "YELLOW"
            thesis = (
                "Alto dinamismo comercial y fuerte reinversión frente a la industria, pero con balances internos moderados o frágiles "
                "(presión en capital de trabajo, apalancamiento o dilución accionaria, F-Score < 6). "
                "Riesgo de ejecución si el financiamiento se restringe."
            )
        elif f_score >= 6 and g_score < 6:
            quadrant = "CUADRANTE III: GENERADOR MADURO (CASH COW)"
            badge = "🛡️ GENERADOR MADURO (CASH COW)"
            color = "BLUE"
            thesis = (
                "Excelente salud y disciplina de capital interna: balance desendeudado, márgenes estables y sólida "
                "conversión a flujo de caja libre, pero con menor ritmo de reinversión o crecimiento que el promedio "
                "de su sector. Típica vaca lechera con retornos predecibles pero menor expansión."
            )
        else:
            quadrant = "CUADRANTE IV: TRAMPA DE VALOR / DETERIORO"
            badge = "🚨 TRAMPA DE VALOR / DETERIORO"
            color = "RED"
            thesis = (
                "Alerta roja fundamental: Balances en deterioro, pérdida de margen operativo o desalineación de flujo "
                "de caja combinados con retornos rezagados respecto a sus competidores. Alto riesgo de pérdida permanente."
            )

        return {
            "quadrant": quadrant,
            "badge": badge,
            "color": color,
            "investment_thesis": thesis,
            "f_score": f_score,
            "g_score": g_score,
        }
