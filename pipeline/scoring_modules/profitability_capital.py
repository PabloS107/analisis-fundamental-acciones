"""
profitability_capital.py - Motores de productividad y retorno del capital:
Novy-Marx GP/A, ROIC Ajustado por Intangibles (Damodaran/Mauboussin),
ROC Tangible de Greenblatt y Coste de Capital (WACC / Ke CAPM).
"""

import statistics
from typing import Any, Dict, List, Optional, Tuple

try:
    from market_data_provider import MarketDataExtractor
except ImportError:
    try:
        from .market_data_provider import MarketDataExtractor
    except ImportError:
        try:
            from pipeline.market_data_provider import MarketDataExtractor
        except ImportError:
            MarketDataExtractor = None

from .scoring_utils import (
    _chronological_annual_fys,
    _first_present,
    _safe_float,
    _to_millions,
    normalize_archetype,
)


def _is_financial_archetype(benchmarks: Optional[Dict[str, Any]], archetype: Optional[str] = None) -> Tuple[str, bool]:
    """Determina canónicamente el arquetipo normalizado y si corresponde a entidad financiera."""
    raw_arch = archetype or (benchmarks.get("archetype") if benchmarks else None) or "STANDARD_CORPORATE"
    arch_norm = normalize_archetype(raw_arch, default="STANDARD_CORPORATE")
    sic_code = str((benchmarks or {}).get("sic_code", "0000")).strip()
    is_financial = (arch_norm in ("FINANCIAL_BANKING", "INSURANCE")) or sic_code.startswith("60") or sic_code.startswith("63")
    return arch_norm, is_financial


def _compute_ebit_m(
    m: Dict[str, Any],
    sga_exp: float,
    rd_exp: float,
    fallback_ni_zero: bool = False,
) -> Optional[float]:
    """Resuelve EBIT en millones con fallback contable GP - SG&A - I+D o Net Income."""
    raw_ebit = _safe_float(m.get("operating_income"))
    if raw_ebit is not None:
        return _to_millions(raw_ebit)
    raw_gp = _safe_float(m.get("gross_profit"))
    gp = _to_millions(raw_gp) if raw_gp is not None else None
    raw_sga = _safe_float(m.get("sga_expense"))
    if gp and (fallback_ni_zero or raw_sga is not None):
        return gp - sga_exp - rd_exp
    raw_ni = _safe_float(m.get("net_income"))
    if raw_ni is not None:
        return _to_millions(raw_ni)
    return 0.0 if fallback_ni_zero else None


class NovyMarxCalculator:
    """
    Calculador del ratio de Rentabilidad Bruta sobre Activos de Robert Novy-Marx (2013):
    Gross Profitability to Assets (GP/A) con Descomposición DuPont Dual y ajuste sectorial.
    """

    @staticmethod
    def _financial_not_applicable_period(period: str) -> Dict[str, Any]:
        """Retorna el contrato explícito NO APLICABLE de Novy-Marx para banca y seguros."""
        return {
            "period": period,
            "is_applicable": False,
            "is_financial_institution": True,
            "rating": "NO APLICABLE (BANCA / SEGUROS)",
            "quadrant": "NO APLICABLE A INTERMEDIACIÓN FINANCIERA",
            "quadrant_badge": "🏦 N/A SECTOR FINANCIERO (VER ROTCE / NIM / COMBINED RATIO)",
            "quadrant_description": (
                "El modelo de Novy-Marx evalúa la productividad fabril/comercial pura deduciendo el coste directo de ventas (COGS). "
                "En intermediación financiera y seguros no existe inventario físico ni COGS; los intereses pagados remuneran depósitos de clientes. "
                "La productividad y eficiencia del capital se evalúan mediante Margen de Interés Neto (NIM), Ratio de Eficiencia y ROTCE/ROE."
            ),
            "gross_profitability_total": None,
            "gross_profitability_ex_cash": None,
            "cash_drag": None,
            "gross_margin": None,
            "asset_turnover_total": None,
            "asset_turnover_ex_cash": None,
            "dupont_product": None,
            "dupont_verified": False,
            "percentile_label": "No Aplicable",
            "percentile_explanation": "Inhibido metodológicamente para arquetipos financieros (Regla 3 de AGENTS.md).",
            "adjusted_gp_a": None,
            "adjusted_gp_a_ex_cash": None,
            "benchmarks_used": {},
            "explanations": {
                "gross_profitability_total": "No aplicable a intermediación bancaria ni seguros.",
                "gross_profitability_ex_cash": "No aplicable.",
                "cash_drag": "No aplicable.",
                "gross_margin": "No aplicable (las entidades financieras no tienen COGS industrial).",
                "asset_turnover": "No aplicable.",
                "dupont_verification": "No aplicable.",
            },
        }

    @staticmethod
    def _classify_dupont_and_percentile(
        gp_a: Optional[float],
        gross_margin: Optional[float],
        turnover_total: Optional[float],
        med_gm: float,
        med_turn: float,
        med_gpa: float,
        p75_gpa: float,
    ) -> Tuple[str, str, str, str, str, str]:
        """Clasifica el cuadrante DuPont (Margen × Rotación) y el percentil sectorial GP/A."""
        gm_high = gross_margin is not None and gross_margin >= med_gm
        turn_high = turnover_total is not None and turnover_total >= med_turn
        gm_str = f"{gross_margin*100:.1f}%" if gross_margin is not None else "N/D"
        turn_str = f"{turnover_total:.2f}x" if turnover_total is not None else "N/D"

        if gm_high and turn_high:
            quadrant = "CUADRANTE I: COMPOUNDER DE ÉLITE"
            quad_badge = "💎 COMPOUNDER DE ÉLITE (MARGEN + VELOCIDAD)"
            quad_desc = (
                "Excelente perfil competitivo: combina un margen bruto por encima de la mediana sectorial "
                f"({gm_str} vs {med_gm*100:.1f}%) con una rotación de activos superior a sus competidores "
                f"({turn_str} vs {med_turn:.2f}x). La empresa ejerce simultáneamente poder de marca/precios "
                "y alta velocidad de conversión de capital."
            )
        elif gm_high and not turn_high:
            quadrant = "CUADRANTE II: MONOPOLIO / PODER DE MARCA"
            quad_badge = "👑 MONOPOLIO / PODER DE MARCA"
            quad_desc = (
                f"Ventaja impulsada por precios: margen bruto destacado ({gm_str} vs mediana {med_gm*100:.1f}%), "
                f"pero rotación de capital moderada o baja ({turn_str} vs mediana {med_turn:.2f}x). "
                "Típico de modelos de alto valor unitario, patentes exclusivas o marcas de lujo."
            )
        elif not gm_high and turn_high:
            quadrant = "CUADRANTE III: LÍDER EN VOLUMEN Y ESCALA"
            quad_badge = "⚡ LÍDER EN VOLUMEN Y VELOCIDAD"
            quad_desc = (
                f"Ventaja impulsada por rotación: márgenes ajustados ({gm_str} vs mediana {med_gm*100:.1f}%), "
                f"pero alta velocidad de despliegue de activos ({turn_str} vs mediana {med_turn:.2f}x). "
                "Modelo tipo distribución mayorista, retail masivo o manufactura ultraeficiente."
            )
        else:
            quadrant = "CUADRANTE IV: BAJA PRODUCTIVIDAD DE CAPITAL"
            quad_badge = "⚠️ BAJA PRODUCTIVIDAD DE CAPITAL"
            quad_desc = (
                f"Alerta de eficiencia: tanto el margen bruto ({gm_str}) como la rotación "
                f"({turn_str}) se sitúan por debajo de las medianas de la industria. El capital instalado "
                "no genera suficiente valor económico por unidad de costo."
            )

        if gp_a is None:
            return quadrant, quad_badge, quad_desc, "N/A", "Datos no disponibles o insuficientes.", "SIN CALIFICAR"
        if gp_a >= (p75_gpa * 1.25):
            return (
                quadrant,
                quad_badge,
                quad_desc,
                "Top 5% de la Industria",
                f"Su rentabilidad bruta ({gp_a*100:.2f}%) supera ampliamente al 95% de sus competidores, situándola en el 5% superior más productivo y eficiente de todo el mercado.",
                "PRODUCTIVIDAD EXCEPCIONAL",
            )
        if gp_a >= p75_gpa:
            return (
                quadrant,
                quad_badge,
                quad_desc,
                "Top 25% (Percentil 75+)",
                f"Supera al 75% de las empresas de su sector ({gp_a*100:.2f}% vs P75 {p75_gpa*100:.2f}%), evidenciando una ventaja competitiva neta y sostenida en la generación de margen bruto.",
                "PRODUCTIVIDAD SOBRESALIENTE",
            )
        if gp_a >= med_gpa:
            return (
                quadrant,
                quad_badge,
                quad_desc,
                "Superior a la Mediana (Percentil 50-75)",
                f"Rinde por encima de la empresa típica del sector ({gp_a*100:.2f}% vs mediana {med_gpa*100:.2f}%), generando valor operativo positivo respecto al promedio de la industria.",
                "PRODUCTIVIDAD SÓLIDA",
            )
        return (
            quadrant,
            quad_badge,
            quad_desc,
            "Inferior a la Mediana (< Percentil 50)",
            f"Se encuentra por debajo de la mediana del sector ({gp_a*100:.2f}% vs mediana {med_gpa*100:.2f}%), lo que sugiere una baja productividad de capital o costos directos desfavorables frente a sus pares.",
            "PRODUCTIVIDAD REZAGADA",
        )

    @classmethod
    def calculate_period(
        cls,
        period: str,
        current_data: Dict[str, float],
        benchmarks: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Calcula Novy-Marx GP/A para un período individual (LTM o FY)."""
        _, is_financial = _is_financial_archetype(benchmarks)
        if is_financial:
            return cls._financial_not_applicable_period(period)

        rev = _safe_float(current_data.get("revenue"))
        gp = _safe_float(current_data.get("gross_profit"))
        assets = _safe_float(current_data.get("total_assets"))
        cash = (
            _first_present(
                _safe_float(current_data.get("cash")),
                _safe_float(current_data.get("cash_and_equiv")),
                _safe_float(current_data.get("cash_and_cash_equivalents")),
            )
            or 0.0
        )

        gp_a = (gp / assets) if (gp is not None and assets and assets > 0) else None
        operating_assets = (assets - cash) if (assets is not None and assets > cash and (assets - cash) > 0) else assets
        gp_a_ex_cash = (gp / operating_assets) if (gp is not None and operating_assets and operating_assets > 0) else None
        cash_drag = (gp_a_ex_cash - gp_a) if (gp_a_ex_cash is not None and gp_a is not None) else 0.0

        gross_margin = (gp / rev) if (gp is not None and rev and rev > 0) else None
        turnover_total = (rev / assets) if (rev is not None and assets and assets > 0) else None
        turnover_ex_cash = (rev / operating_assets) if (rev is not None and operating_assets and operating_assets > 0) else None
        dupont_product = (gross_margin * turnover_total) if (gross_margin is not None and turnover_total is not None) else None
        dupont_verified = bool(dupont_product is not None and gp_a is not None and abs(dupont_product - gp_a) < 0.005)

        med_gpa = _safe_float(benchmarks.get("median_gross_profitability")) or 0.280
        p75_gpa = _safe_float(benchmarks.get("p75_gross_profitability")) or 0.400
        med_gp_ex = _safe_float(benchmarks.get("median_gp_ex_cash")) or 0.320
        med_gm = _safe_float(benchmarks.get("median_gross_margin")) or 0.380
        med_turn = _safe_float(benchmarks.get("median_asset_turnover")) or 0.75

        adj_gp_a = (gp_a - med_gpa) if gp_a is not None else None
        adj_gp_a_ex_cash = (gp_a_ex_cash - med_gp_ex) if gp_a_ex_cash is not None else None

        quadrant, quad_badge, quad_desc, pct_label, pct_expl, rating = cls._classify_dupont_and_percentile(
            gp_a, gross_margin, turnover_total, med_gm, med_turn, med_gpa, p75_gpa
        )

        explanations = {
            "gross_profitability_total": (
                f"Gross Profitability (Activos Totales) = {gp_a*100:.2f}%: Por cada $1.00 de activo total en su balance, la empresa genera ${gp_a:.2f} de utilidad bruta anual pura."
                if gp_a is not None else "N/A"
            ),
            "gross_profitability_ex_cash": (
                f"Gross Profitability Operativa (Ex-Caja) = {gp_a_ex_cash*100:.2f}%: Al restar el efectivo e inversiones líquidas ociosas (${cash/1e6:,.1f}M), el capital estrictamente productivo rinde a un {gp_a_ex_cash*100:.2f}% (${gp_a_ex_cash:.2f} de utilidad bruta por cada dólar invertido en activos operativos)."
                if gp_a_ex_cash is not None else "N/A"
            ),
            "cash_drag": (
                f"Efecto Arrastre de Caja (Cash Drag) = {cash_drag*100:+.2f} p.p.: Mantener liquidez acumulada reduce artificialmente el ratio nominal de rentabilidad en {abs(cash_drag*100):.2f} puntos porcentuales. El negocio operativo subyacente es más rentable de lo que refleja el balance general agregado."
            ),
            "gross_margin": (
                f"Margen Bruto = {gross_margin*100:.2f}%: Retiene {gross_margin*100:.1f} centavos de utilidad bruta por cada dólar vendido tras cubrir los costos directos de producción (COGS). Frente a la mediana del sector ({med_gm*100:.1f}%), denota {'un fuerte poder de fijación de precios y foso de marca.' if gross_margin >= med_gm else 'menor margen unitario o mayor intensidad de costos directos.'}"
                if gross_margin is not None else "N/A"
            ),
            "asset_turnover": (
                f"Rotación de Activos Totales = {turnover_total:.2f}x: La compañía rota su base total de activos {turnover_total:.2f} veces al año en ingresos. Frente a la mediana sectorial ({med_turn:.2f}x), refleja {'una velocidad de comercialización y eficiencia logística superior.' if turnover_total >= med_turn else 'un ciclo de rotación de capital más pausado o activos de largo plazo.'}"
                if turnover_total is not None else "N/A"
            ),
            "dupont_verification": (
                f"Descomposición DuPont: Margen Bruto ({gross_margin*100:.2f}%) × Rotación ({turnover_total:.3f}x) = {dupont_product*100:.2f}% (Coincidencia exacta con GP/A de {gp_a*100:.2f}%)."
                if (gross_margin is not None and turnover_total is not None and gp_a is not None) else "N/A"
            ),
            "sector_adjustment": (
                f"Gross Profitability Ajustada por Sector = {adj_gp_a*100:+.2f} p.p.: La empresa supera en {adj_gp_a*100:+.2f} puntos porcentuales a la empresa intermedia (mediana de {med_gpa*100:.1f}%) de su industria. Su rentabilidad de capital es {'estructuralmente superior a sus competidores.' if adj_gp_a > 0 else 'inferior a la media del sector.'}"
                if adj_gp_a is not None else "N/A"
            ),
        }

        return {
            "period": period,
            "gross_profitability_total": gp_a,
            "gross_profitability_ex_cash": gp_a_ex_cash,
            "cash_drag_pct": cash_drag,
            "gross_margin": gross_margin,
            "asset_turnover_total": turnover_total,
            "asset_turnover_ex_cash": turnover_ex_cash,
            "dupont_verified": dupont_verified,
            "rating": rating,
            "percentile_label": pct_label,
            "percentile_explanation": pct_expl,
            "quadrant": quadrant,
            "quadrant_badge": quad_badge,
            "quadrant_description": quad_desc,
            "adjusted_gp_a": adj_gp_a,
            "adjusted_gp_a_ex_cash": adj_gp_a_ex_cash,
            "benchmarks_used": {
                "median_gross_profitability": med_gpa,
                "p75_gross_profitability": p75_gpa,
                "median_gp_ex_cash": med_gp_ex,
                "median_gross_margin": med_gm,
                "median_asset_turnover": med_turn,
            },
            "explanations": explanations,
            "is_financial_institution": False,
        }

    @classmethod
    def _build_peer_ranking(
        cls,
        benchmarks: Dict[str, Any],
        ticker: str,
        company_name: str,
        recent_fy: str,
        recent_res: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Construye la tabla ordenada de GP/A entre la empresa evaluada y sus pares."""
        peer_ranking: List[Dict[str, Any]] = []
        target_upper = ticker.strip().upper() if ticker else ""
        target_found = False

        for p in benchmarks.get("peers_detail", []):
            t = str(p.get("ticker", "")).strip()
            is_this_target = (t.upper() == target_upper) if target_upper else bool(p.get("is_target", False))
            if is_this_target and recent_res.get("gross_profitability_total") is not None:
                target_found = True
                peer_ranking.append({
                    "ticker": target_upper or t,
                    "company_name": company_name or p.get("company_name", t),
                    "is_target": True,
                    "period": recent_fy,
                    "gross_profitability_total": recent_res.get("gross_profitability_total"),
                    "gross_profitability_ex_cash": recent_res.get("gross_profitability_ex_cash"),
                    "gross_margin": recent_res.get("gross_margin"),
                    "asset_turnover": recent_res.get("asset_turnover_total"),
                })
                continue

            t_assets = _safe_float(p.get("total_assets_usd_m"))
            t_rev = _safe_float(p.get("revenue_usd_m"))
            t_gp = _safe_float(p.get("gross_profit_usd_m"))
            t_cash = _safe_float(p.get("cash_usd_m")) or 0.0
            if t_assets and t_assets > 0 and t_gp is not None:
                if is_this_target:
                    target_found = True
                p_op_assets = (t_assets - t_cash) if (t_assets > t_cash and (t_assets - t_cash) > 0) else t_assets
                peer_ranking.append({
                    "ticker": t,
                    "company_name": p.get("company_name", t),
                    "is_target": is_this_target,
                    "period": p.get("period", "LTM"),
                    "gross_profitability_total": t_gp / t_assets,
                    "gross_profitability_ex_cash": t_gp / p_op_assets,
                    "gross_margin": (t_gp / t_rev) if (t_rev and t_rev > 0) else None,
                    "asset_turnover": (t_rev / t_assets) if (t_rev and t_rev > 0) else None,
                })

        if target_upper and not target_found and recent_res.get("gross_profitability_total") is not None:
            peer_ranking.append({
                "ticker": target_upper,
                "company_name": company_name or target_upper,
                "is_target": True,
                "period": recent_fy,
                "gross_profitability_total": recent_res.get("gross_profitability_total"),
                "gross_profitability_ex_cash": recent_res.get("gross_profitability_ex_cash"),
                "gross_margin": recent_res.get("gross_margin"),
                "asset_turnover": recent_res.get("asset_turnover_total"),
            })

        peer_ranking.sort(
            key=lambda x: x["gross_profitability_total"] if x["gross_profitability_total"] is not None else -999,
            reverse=True,
        )
        return peer_ranking

    @classmethod
    def calculate_series(
        cls,
        fiscal_years: List[str],
        period_metrics: Dict[str, Dict[str, float]],
        benchmarks: Dict[str, Any],
        ticker: str = "",
        company_name: str = "",
    ) -> Dict[str, Any]:
        """Calcula la serie histórica completa de Novy-Marx GP/A y su tendencia a 3 y 5 años."""
        period_results = {fy: cls.calculate_period(fy, period_metrics.get(fy, {}), benchmarks) for fy in fiscal_years}
        annual_fys_sorted = _chronological_annual_fys(fiscal_years)
        chronological_keys = list(annual_fys_sorted) + (["LTM"] if "LTM" in fiscal_years else [])
        recent_fy = "LTM" if "LTM" in fiscal_years else (annual_fys_sorted[-1] if annual_fys_sorted else (fiscal_years[0] if fiscal_years else "N/A"))
        recent_res = period_results.get(recent_fy, {})
        recent_gpa = recent_res.get("gross_profitability_total")

        period_3y = annual_fys_sorted[-3] if len(annual_fys_sorted) >= 3 else None
        gpa_3y = period_results.get(period_3y, {}).get("gross_profitability_total") if period_3y else None
        delta_3y = (recent_gpa - gpa_3y) if (recent_gpa is not None and gpa_3y is not None) else None

        period_5y = annual_fys_sorted[-5] if len(annual_fys_sorted) >= 5 else None
        gpa_5y = period_results.get(period_5y, {}).get("gross_profitability_total") if period_5y else None
        delta_5y = (recent_gpa - gpa_5y) if (recent_gpa is not None and gpa_5y is not None) else None

        last_5_keys = annual_fys_sorted[-5:]
        gpa_history = [
            period_results[k]["gross_profitability_total"]
            for k in last_5_keys
            if period_results.get(k, {}).get("gross_profitability_total") is not None
        ]
        cv_gpa = None
        if len(gpa_history) >= 3:
            mean_val = statistics.mean(gpa_history)
            if mean_val > 0:
                cv_gpa = statistics.stdev(gpa_history) / mean_val

        if delta_5y is not None:
            if delta_5y > 0.05:
                trend_diag = f"Expansión estructural acelerada (+{delta_5y*100:.2f} p.p. en 5 años); aumento continuo de la productividad pura de capital."
            elif delta_5y > 0:
                trend_diag = f"Trayectoria constructiva y estable (+{delta_5y*100:.2f} p.p. en 5 años); foso económico protegido."
            else:
                trend_diag = f"Compresión de rentabilidad sobre activos ({delta_5y*100:.2f} p.p. en 5 años); vigilar presión en costos directos o acumulación de activos."
        elif delta_3y is not None:
            trend_diag = f"Variación a 3 años de {delta_3y*100:+.2f} p.p."
        else:
            trend_diag = "Historial insuficiente para evaluar tendencia de 3-5 años."

        arch_norm, is_financial = _is_financial_archetype(benchmarks)
        res_series: Dict[str, Any] = {
            "is_applicable": not is_financial,
            "is_financial_institution": is_financial,
            "by_period": period_results,
            "latest_period": recent_fy,
            "latest_result": recent_res,
            "trend": {
                "period_3y_basis": period_3y,
                "delta_3y": delta_3y,
                "period_5y_basis": period_5y,
                "delta_5y": delta_5y,
                "cv_gpa": cv_gpa,
                "trend_diagnosis": trend_diag,
                "chronological_periods": chronological_keys,
            },
            "peer_ranking": cls._build_peer_ranking(benchmarks, ticker, company_name, recent_fy, recent_res),
        }
        if is_financial:
            res_series["pedagogical_guidance"] = {
                "metric": "Novy-Marx Gross Profitability to Assets (GP/A)",
                "status": "NO APLICABLE",
                "archetype": arch_norm,
                "what_it_measures": "Productividad pura del capital de Novy-Marx (2013): Utilidad Bruta / Activos Totales, aislando la eficiencia fabril/comercial sin distorsiones contables de SG&A o I+D.",
                "formula": "GP/A = Gross Profit / Total Assets",
                "why_not_applicable": (
                    f"Inhibido metodológicamente para arquetipos '{arch_norm}'. "
                    "En intermediación financiera y entidades aseguradoras no existe Costo de Mercancías Vendidas (COGS) industrial. "
                    "Los gastos por intereses constituyen el costo del pasivo operativo (depósitos de clientes), "
                    "por lo que imputar un 'margen bruto' desvirtúa el análisis de rentabilidad y productividad."
                ),
                "replacement_metrics": [
                    "NIM Ajustado por Riesgo (Net Interest Margin tras provisiones)",
                    "Ratio de Eficiencia Bancario (Non-Interest Expense / Total Net Revenue)",
                    "ROTCE (Rentabilidad sobre Fondos Propios Tangibles)",
                    "Ratio Combinado (Combined Ratio en Seguros)",
                ],
            }
        return res_series


class IntangibleROICCalculator:
    """
    Calculador del ROIC Ajustado por Intangibles bajo metodología roll-forward (Damodaran/Mauboussin):
    capitaliza I+D y % sectorial de SG&A, amortizándolos en vidas útiles N.
    """

    @staticmethod
    def _compute_period_roic(
        period: str,
        m: Dict[str, Any],
        is_reit: bool,
        rd_exp: float,
        rd_amort: float,
        rd_stock: float,
        mkt_exp: float,
        mkt_amort: float,
        mkt_stock: float,
        total_intangibles: float,
        prev_res: Optional[Dict[str, Any]],
        default_tax_rate: float = 0.21,
    ) -> Dict[str, Any]:
        """Calcula NOPAT, capital invertido promedio/final y ROIC para un período dado (FY o LTM)."""
        sga_exp = _to_millions(_safe_float(m.get("sga_expense")) or 0.0) or 0.0
        ebit = _compute_ebit_m(m, sga_exp, rd_exp, fallback_ni_zero=True) or 0.0

        raw_tax = _safe_float(m.get("effective_tax_rate"))
        tax_rate = max(0.05, min(0.35, raw_tax)) if raw_tax is not None else default_tax_rate

        assets = _to_millions(_safe_float(m.get("total_assets")) or 0.0) or 0.0
        cash = _to_millions(_safe_float(m.get("cash")) or 0.0) or 0.0
        cl = _to_millions(_safe_float(m.get("current_liabilities")) or 0.0) or 0.0
        st_debt = _to_millions(_safe_float(m.get("short_term_debt")) or 0.0) or 0.0
        nibcl = max(0.0, cl - st_debt)

        if is_reit:
            re_dep = _to_millions(_safe_float(m.get("real_estate_depreciation")) or 0.0) or 0.0
            maint_capex = _to_millions(_safe_float(m.get("capex")) or 0.0) or 0.0
            accum_dep = _to_millions(_safe_float(m.get("accumulated_depreciation")) or 0.0) or 0.0
            ebit_adj = ebit + re_dep - maint_capex
            nopat_trad = max(0.0, ebit_adj * (1.0 - tax_rate))
            nopat_adj = nopat_trad
            ic_trad_end = max(1.0, assets + accum_dep - cash - nibcl)
            ic_adj_end = ic_trad_end
        else:
            nopat_trad = ebit * (1.0 - tax_rate)
            ebit_adj = ebit + (rd_exp - rd_amort) + (mkt_exp - mkt_amort)
            nopat_adj = ebit_adj * (1.0 - tax_rate)
            ic_trad_end = max(1.0, assets - cash - nibcl)
            ic_adj_end = ic_trad_end + total_intangibles

        if prev_res:
            prev_ic_trad = prev_res.get("ic_trad_end", prev_res.get("ic_trad", ic_trad_end))
            prev_ic_adj = prev_res.get("ic_adj_end", prev_res.get("ic_adj", ic_adj_end))
            ic_trad_avg = (ic_trad_end + prev_ic_trad) / 2.0
            ic_adj_avg = (ic_adj_end + prev_ic_adj) / 2.0
        else:
            ic_trad_avg, ic_adj_avg = ic_trad_end, ic_adj_end

        roic_trad_avg = (nopat_trad / ic_trad_avg) if ic_trad_avg > 0 else None
        roic_adj_avg = (nopat_adj / ic_adj_avg) if ic_adj_avg > 0 else None
        return {
            "period": period,
            "ebit": ebit,
            "ebit_adj": ebit_adj,
            "tax_rate": tax_rate,
            "nopat_trad": nopat_trad,
            "nopat_adj": nopat_adj,
            "ic_trad": ic_trad_avg,
            "ic_adj": ic_adj_avg,
            "ic_trad_end": ic_trad_end,
            "ic_adj_end": ic_adj_end,
            "ic_trad_avg": ic_trad_avg,
            "ic_adj_avg": ic_adj_avg,
            "rd_investment": rd_exp,
            "rd_amortization": rd_amort,
            "rd_stock": rd_stock,
            "mkt_investment": mkt_exp,
            "mkt_amortization": mkt_amort,
            "mkt_stock": mkt_stock,
            "total_intangible_stock": total_intangibles,
            "roic_trad": roic_trad_avg,
            "roic_adj": roic_adj_avg,
            "roic_trad_end": (nopat_trad / ic_trad_end) if ic_trad_end > 0 else None,
            "roic_adj_end": (nopat_adj / ic_adj_end) if ic_adj_end > 0 else None,
            "roic_trad_avg": roic_trad_avg,
            "roic_adj_avg": roic_adj_avg,
        }

    @classmethod
    def _compute_for_lifespan(
        cls,
        fiscal_years: List[str],
        annual_fys_sorted: List[str],
        period_metrics: Dict[str, Dict[str, Any]],
        is_reit: bool,
        sga_cap_pct: float,
        n_rd: int,
        n_mkt: int,
    ) -> Dict[str, Any]:
        """Calcula la serie histórica roll-forward completa dada una vida útil de I+D y marketing."""
        rd_stock = 0.0
        mkt_stock = 0.0
        rd_invs: Dict[str, float] = {}
        mkt_invs: Dict[str, float] = {}
        results: Dict[str, Any] = {}

        for idx, fy in enumerate(annual_fys_sorted):
            m = period_metrics.get(fy, {})
            rd_exp = _to_millions(_safe_float(m.get("rd_expense")) or 0.0) or 0.0
            sga_exp = _to_millions(_safe_float(m.get("sga_expense")) or 0.0) or 0.0
            mkt_exp = sga_exp * sga_cap_pct
            rd_invs[fy] = rd_exp
            mkt_invs[fy] = mkt_exp

            rd_amort = sum(rd_invs.get(annual_fys_sorted[idx - k], 0.0) / float(n_rd) for k in range(1, n_rd + 1) if idx - k >= 0)
            mkt_amort = sum(mkt_invs.get(annual_fys_sorted[idx - k], 0.0) / float(n_mkt) for k in range(1, n_mkt + 1) if idx - k >= 0)
            rd_stock = max(0.0, rd_stock + rd_exp - rd_amort)
            mkt_stock = max(0.0, mkt_stock + mkt_exp - mkt_amort)
            prev_res = results.get(annual_fys_sorted[idx - 1]) if idx > 0 else None

            results[fy] = cls._compute_period_roic(
                fy, m, is_reit, rd_exp, rd_amort, rd_stock, mkt_exp, mkt_amort, mkt_stock, rd_stock + mkt_stock, prev_res
            )

        if "LTM" in fiscal_years:
            m_ltm = period_metrics.get("LTM", {})
            last_fy = annual_fys_sorted[-1] if annual_fys_sorted else None
            last_res = results.get(last_fy, {}) if last_fy else {}
            rd_exp_ltm = _to_millions(_safe_float(m_ltm.get("rd_expense")) or 0.0) or 0.0
            sga_exp_ltm = _to_millions(_safe_float(m_ltm.get("sga_expense")) or 0.0) or 0.0
            mkt_exp_ltm = sga_exp_ltm * sga_cap_pct

            if is_reit:
                rd_amort_ltm = mkt_amort_ltm = rd_stock_ltm = mkt_stock_ltm = total_int_ltm = 0.0
            else:
                tail_rd = [rd_invs.get(y, 0.0) for y in annual_fys_sorted[-(n_rd - 1):]] if n_rd > 1 else []
                rd_amort_ltm = sum(tail_rd + [rd_exp_ltm]) / float(n_rd)
                rd_stock_ltm = max(0.0, last_res.get("rd_stock", 0.0) + (rd_exp_ltm - last_res.get("rd_investment", 0.0)) * 0.5)

                tail_mkt = [mkt_invs.get(y, 0.0) for y in annual_fys_sorted[-(n_mkt - 1):]] if n_mkt > 1 else []
                mkt_amort_ltm = sum(tail_mkt + [mkt_exp_ltm]) / float(n_mkt)
                mkt_stock_ltm = max(0.0, last_res.get("mkt_stock", 0.0) + (mkt_exp_ltm - last_res.get("mkt_investment", 0.0)) * 0.5)
                total_int_ltm = rd_stock_ltm + mkt_stock_ltm

            results["LTM"] = cls._compute_period_roic(
                "LTM",
                m_ltm,
                is_reit,
                rd_exp_ltm,
                rd_amort_ltm,
                rd_stock_ltm,
                mkt_exp_ltm,
                mkt_amort_ltm,
                mkt_stock_ltm,
                total_int_ltm,
                last_res or None,
                default_tax_rate=last_res.get("tax_rate", 0.21),
            )
        return results

    @classmethod
    def calculate_series(
        cls,
        fiscal_years: List[str],
        period_metrics: Dict[str, Dict[str, Any]],
        benchmarks: Dict[str, Any],
        ticker: str = "",
    ) -> Dict[str, Any]:
        """Calcula la serie histórica completa de ROIC Tradicional vs Ajustado por Intangibles y sensibilidad N."""
        annual_fys_sorted = _chronological_annual_fys(fiscal_years)
        arch_norm = normalize_archetype(benchmarks.get("archetype") if benchmarks else None, default="STANDARD_CORPORATE")
        is_reit = arch_norm == "REAL_ESTATE_REIT"

        n_rd_base = int(benchmarks.get("rd_useful_life_years", 4))
        n_mkt_base = int(benchmarks.get("sga_useful_life_years", 2))
        sga_cap_pct = float(benchmarks.get("sga_capitalization_pct", 0.0))

        base_results = cls._compute_for_lifespan(fiscal_years, annual_fys_sorted, period_metrics, is_reit, sga_cap_pct, n_rd_base, n_mkt_base)
        n_low, n_high = max(2, n_rd_base - 1), n_rd_base + 1
        sens_low = cls._compute_for_lifespan(fiscal_years, annual_fys_sorted, period_metrics, is_reit, sga_cap_pct, n_low, n_mkt_base)
        sens_high = cls._compute_for_lifespan(fiscal_years, annual_fys_sorted, period_metrics, is_reit, sga_cap_pct, n_high, n_mkt_base)

        recent_fy = "LTM" if "LTM" in fiscal_years else (annual_fys_sorted[-1] if annual_fys_sorted else (fiscal_years[0] if fiscal_years else "N/A"))
        rec_base = base_results.get(recent_fy, {})
        rec_low = sens_low.get(recent_fy, {})
        rec_high = sens_high.get(recent_fy, {})

        roic_trad_val = rec_base.get("roic_trad", 0.0)
        roic_adj_val = rec_base.get("roic_adj", 0.0)
        stock_val = rec_base.get("total_intangible_stock", 0.0)
        ic_trad_val = rec_base.get("ic_trad", 1.0)
        ic_adj_val = rec_base.get("ic_adj", 1.0)

        return {
            "by_period": base_results,
            "latest_period": recent_fy,
            "latest_result": rec_base,
            "sensitivity_matrix": {
                "n_minus_1": {"lifespan_years": n_low, "intangibles_usd_m": rec_low.get("total_intangible_stock", 0.0), "roic_adj": rec_low.get("roic_adj")},
                "n_base": {"lifespan_years": n_rd_base, "intangibles_usd_m": stock_val, "roic_adj": roic_adj_val},
                "n_plus_1": {"lifespan_years": n_high, "intangibles_usd_m": rec_high.get("total_intangible_stock", 0.0), "roic_adj": rec_high.get("roic_adj")},
            },
            "parameters": {
                "rd_useful_life_years": n_rd_base,
                "sga_useful_life_years": n_mkt_base,
                "sga_capitalization_pct": sga_cap_pct,
            },
            "explanations": {
                "roic_traditional": (
                    f"ROIC Tradicional = {roic_trad_val*100:.2f}%: Mide el retorno operativo sobre el capital invertido promedio en libros contables. Al tratar I+D y Marketing como gastos corrientes en lugar de inversiones de capital, distorsiona al alza el ratio en empresas intensivas en activos intangibles."
                    if roic_trad_val else "N/A"
                ),
                "roic_adjusted": (
                    f"ROIC Ajustado por Intangibles = {roic_adj_val*100:.2f}%: Refleja la rentabilidad económica real al capitalizar ${stock_val:,.1f}M en activos de innovación/marca y amortizarlos económicamente a {n_rd_base} años. Calculado sobre el Capital Invertido Promedio (${ic_adj_val:,.1f}M vs. ${ic_trad_val:,.1f}M tradicional), garantizando la correspondencia temporal perfecta entre el flujo anual de NOPAT y el capital desplegado durante el ejercicio."
                    if roic_adj_val else "N/A"
                ),
                "sensitivity": (
                    f"Matriz de Sensibilidad: Acelerando la amortización a {n_low} años el ROIC ajustado promedio es de {(rec_low.get('roic_adj') or 0)*100:.2f}%, y extendiéndola a {n_high} años es de {(rec_high.get('roic_adj') or 0)*100:.2f}%. En todos los escenarios, la rentabilidad se mantiene estructuralmente sólida y supera con holgura el costo de capital."
                ),
            },
        }


class GreenblattROCCalculator:
    """Calculadora de Retorno sobre Capital Tangible Operativo (Joel Greenblatt - Magic Formula)."""

    @staticmethod
    def compute_tangible_capital(
        current_assets: float,
        cash: float,
        current_liabilities: float,
        short_term_debt: float,
        net_ppe: float,
    ) -> float:
        """Calcula el capital tangible operativo con salvaguarda inferior en Net PP&E si NWC < 0."""
        op_ca = max(0.0, current_assets - cash)
        op_cl = max(0.0, current_liabilities - short_term_debt)
        op_nwc = op_ca - op_cl
        tangible_cap = max(net_ppe, op_nwc + net_ppe) if op_nwc < 0 else (op_nwc + net_ppe)
        return max(1.0, tangible_cap)

    @staticmethod
    def rate_roc(roc_val: Optional[float]) -> str:
        """Categoriza el ROC Greenblatt en bandas de calidad institucional."""
        if roc_val is None:
            return "N/A"
        if roc_val >= 0.40:
            return "ELITE (> 40%)"
        if roc_val >= 0.25:
            return "EXCELENTE (25% - 40%)"
        if roc_val >= 0.15:
            return "SÓLIDO (15% - 25%)"
        if roc_val >= 0.10:
            return "MODERADO (10% - 15%)"
        if roc_val >= 0.0:
            return "DEFICIENTE (< 10%)"
        return "DESTRUCTOR (< 0%)"

    @staticmethod
    def _financial_inhibited_payload(fiscal_years: List[str], arch_norm: str) -> Dict[str, Any]:
        """Retorna el dict inhibido para banca/seguros donde Greenblatt ROC no aplica."""
        recent_fy = "LTM" if "LTM" in fiscal_years else (fiscal_years[-1] if fiscal_years else "N/A")
        annual_series = {
            fy: {
                "period": fy,
                "is_applicable": False,
                "ebit_usd_m": None,
                "current_assets_usd_m": None,
                "cash_usd_m": None,
                "current_liabilities_usd_m": None,
                "short_term_debt_usd_m": None,
                "op_current_assets_usd_m": None,
                "op_current_liabilities_usd_m": None,
                "nwc_usd_m": None,
                "net_ppe_usd_m": None,
                "tangible_capital_end": None,
                "tangible_capital_avg": None,
                "roc_avg": None,
                "roc_end": None,
                "roc_pct": None,
                "rating": "NO APLICABLE",
                "roc_rating": "NO APLICABLE",
                "rating_label": f"NO APLICABLE ({arch_norm})",
            }
            for fy in fiscal_years
        }
        empty_summary = lambda p: {
            "period": p,
            "is_applicable": False,
            "roc_avg": None,
            "roc_ltm": None,
            "roc_end": None,
            "roc_pct": None,
            "rating": "NO APLICABLE",
            "roc_rating": "NO APLICABLE",
            "rating_label": "NO APLICABLE",
        }
        ret = {
            "methodology": "Joel Greenblatt Magic Formula - Return on Capital (EBIT / Average Operating Tangible Capital)",
            "archetype": arch_norm,
            "is_applicable": False,
            "recent_period": recent_fy,
            "annual_series": annual_series,
            "ltm": empty_summary("LTM"),
            "latest_result": empty_summary(recent_fy),
            "latest_roc": None,
            "latest_roc_pct": None,
            "peer_roc_median": None,
            "peer_roc_median_pct": None,
            "spread_vs_peer_pct": None,
            "peer_comparison": {"is_applicable": False, "company_roc_ltm": None, "peer_median_roc": None, "spread_vs_peer_median": None},
            "rating": "NO APLICABLE",
            "roc_rating": "NO APLICABLE",
            "rating_label": f"NO APLICABLE ({arch_norm})",
            "explanation": (
                f"Métrica inhibida para el arquetipo '{arch_norm}'. Las instituciones financieras no operan con "
                "capital de trabajo industrial ni activos corrientes/no corrientes tradicionales. Su rentabilidad sobre "
                "capital se evalúa mediante ROTCE y ROE en relación al Coste del Capital Propio (Ke)."
            ),
            "pedagogical_guidance": {
                "metric": "Return on Capital (ROC) de Joel Greenblatt",
                "status": "NO APLICABLE",
                "archetype": arch_norm,
                "what_it_measures": "Mide la rentabilidad operativa pre-impuestos (EBIT) sobre el capital físico tangible operativo desplegado (Capital de Trabajo Neto Operativo + PP&E Neto).",
                "formula": "ROC = EBIT / [ (Activos Corrientes - Caja) - (Pasivos Corrientes - Deuda CP) + Net PP&E ]",
                "why_not_applicable": (
                    f"Inhibido por diseño metodológico institucional para arquetipos '{arch_norm}'. "
                    "Las entidades bancarias y aseguradoras no estructuran su balance en activos y pasivos corrientes vs. no corrientes; "
                    "el 'dinero' es su materia prima y los activos financieros (cartera de créditos, valores de inversión) son el activo productivo central. "
                    "En una institución financiera, el capital tangible operativo tiende a cero o valores residuales de oficinas, "
                    "lo que produce denominadores infinitesimales y arroja tasas de ROC absurdas (de miles o millones por ciento). "
                    "En su lugar, la rentabilidad sobre capital se evalúa mediante ROE (Return on Equity), ROTCE (Return on Tangible Common Equity) "
                    "y RORWA (Return on Risk-Weighted Assets), comparados contra el Coste del Capital Propio (Ke)."
                ),
                "replacement_metrics": ["ROE", "ROTCE", "RORWA", "Spread ROTCE - Ke"],
            },
        }
        ret.update(annual_series)
        return ret

    @classmethod
    def _compute_period_entry(
        cls,
        period: str,
        m: Dict[str, Any],
        prev_cap: Optional[float],
    ) -> Dict[str, Any]:
        """Calcula ROC Greenblatt y descomposición tangible para un período FY o LTM."""
        rd_exp = _to_millions(_safe_float(m.get("rd_expense")) or 0.0) or 0.0
        sga_exp = _to_millions(_safe_float(m.get("sga_expense")) or 0.0) or 0.0
        ebit = _compute_ebit_m(m, sga_exp, rd_exp, fallback_ni_zero=False)

        ca = _to_millions(_safe_float(m.get("current_assets")) or 0.0) or 0.0
        cash = _to_millions(_safe_float(m.get("cash")) or 0.0) or 0.0
        cl = _to_millions(_safe_float(m.get("current_liabilities")) or 0.0) or 0.0
        st_debt = _to_millions(_safe_float(m.get("short_term_debt")) or 0.0) or 0.0
        net_ppe = _to_millions(_safe_float(m.get("net_ppe")) or 0.0) or 0.0

        op_ca = max(0.0, ca - cash)
        op_cl = max(0.0, cl - st_debt)
        op_nwc = op_ca - op_cl
        tangible_cap_end = cls.compute_tangible_capital(ca, cash, cl, st_debt, net_ppe)
        tangible_cap_avg = ((tangible_cap_end + prev_cap) / 2.0) if prev_cap is not None else tangible_cap_end

        roc_avg = (ebit / tangible_cap_avg) if (ebit is not None and tangible_cap_avg > 0) else None
        roc_end = (ebit / tangible_cap_end) if (ebit is not None and tangible_cap_end > 0) else None
        entry: Dict[str, Any] = {
            "period": period,
            "ebit_usd_m": ebit,
            "current_assets_usd_m": ca,
            "cash_usd_m": cash,
            "current_liabilities_usd_m": cl,
            "short_term_debt_usd_m": st_debt,
            "op_current_assets_usd_m": op_ca,
            "op_current_liabilities_usd_m": op_cl,
            "nwc_usd_m": op_nwc,
            "net_ppe_usd_m": net_ppe,
            "tangible_capital_end": tangible_cap_end,
            "tangible_capital_avg": tangible_cap_avg,
            "roc_avg": roc_avg,
            "roc_end": roc_end,
            "roc_pct": round(roc_avg * 100, 2) if roc_avg is not None else None,
        }
        if period == "LTM":
            entry["roc_ltm"] = roc_avg
        return entry

    @classmethod
    def calculate_series(
        cls,
        fiscal_years: List[str],
        period_metrics: Dict[str, Dict[str, Any]],
        benchmarks: Dict[str, Any],
        ticker: str = "",
        archetype: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Calcula la serie histórica completa y LTM de ROC Greenblatt frente a pares."""
        raw_arch = archetype or (benchmarks.get("archetype") if benchmarks else None) or "STANDARD_CORPORATE"
        arch_norm = normalize_archetype(raw_arch, default="STANDARD_CORPORATE")
        if arch_norm in ("FINANCIAL_BANKING", "INSURANCE"):
            return cls._financial_inhibited_payload(fiscal_years, arch_norm)

        annual_fys_sorted = _chronological_annual_fys(fiscal_years)
        results: Dict[str, Any] = {}
        prev_cap: Optional[float] = None
        for fy in annual_fys_sorted:
            entry = cls._compute_period_entry(fy, period_metrics.get(fy, {}), prev_cap)
            results[fy] = entry
            prev_cap = entry["tangible_capital_end"]

        if "LTM" in fiscal_years:
            results["LTM"] = cls._compute_period_entry("LTM", period_metrics.get("LTM", {}), prev_cap)

        peer_roc_median = benchmarks.get("peer_greenblatt_roc_median", benchmarks.get("peer_roc_median", 0.25))
        recent_fy = "LTM" if "LTM" in fiscal_years else (annual_fys_sorted[-1] if annual_fys_sorted else (fiscal_years[0] if fiscal_years else "N/A"))
        latest = results.get(recent_fy, {})
        latest_roc = latest.get("roc_avg", 0.0) or 0.0

        if latest_roc >= 0.50:
            rating, label = "COMPOUNDER_TANGIBLE_ELITE", "Rentabilidad Tangible Excepcional (> 50% ROC - Negocio Asset-Light Dominante)"
        elif latest_roc >= 0.25:
            rating, label = "STRONG_CAPITAL_EFFICIENCY", "Alta Eficiencia de Capital Tangible (25% - 50% ROC - Foso Defensivo Sólido)"
        elif latest_roc >= 0.12:
            rating, label = "MODERATE_EFFICIENCY", "Eficiencia de Capital Adecuada (12% - 25% ROC - Rendimiento en Línea con Mercado)"
        else:
            rating, label = "CAPITAL_INTENSIVE_LOW_RETURN", "Baja Productividad del Capital Tangible (< 12% ROC - Negocio Intensivo en Capital)"

        spread_vs_peer = round((latest_roc - peer_roc_median) * 100, 2)
        ltm_payload = dict(results.get("LTM", latest))
        if "roc_ltm" not in ltm_payload and "roc_avg" in ltm_payload:
            ltm_payload["roc_ltm"] = ltm_payload["roc_avg"]

        ret: Dict[str, Any] = {
            "methodology": "Joel Greenblatt Magic Formula - Return on Capital (EBIT / Average Operating Tangible Capital)",
            "archetype": arch_norm,
            "is_applicable": True,
            "recent_period": recent_fy,
            "annual_series": results,
            "ltm": ltm_payload,
            "latest_result": latest,
            "latest_roc": latest_roc,
            "latest_roc_pct": round(latest_roc * 100, 2),
            "peer_roc_median": peer_roc_median,
            "peer_roc_median_pct": round(peer_roc_median * 100, 2),
            "spread_vs_peer_pct": spread_vs_peer,
            "peer_comparison": {"company_roc_ltm": latest_roc, "peer_median_roc": peer_roc_median, "spread_vs_peer_median": spread_vs_peer},
            "rating": rating,
            "roc_rating": rating,
            "rating_label": label,
            "explanation": (
                f"ROC Greenblatt = {latest_roc*100:.2f}% vs. Mediana Sectorial {peer_roc_median*100:.2f}% "
                f"(Diferencial: {spread_vs_peer:+.2f}%). Mide la productividad operativa pura pre-tax "
                f"sobre el capital tangible operativo desplegado (${latest.get('tangible_capital_avg', 0):,.1f}M promedio)."
            ),
        }
        ret.update(results)
        return ret


class WACCCalculator:
    """Calculador de Coste de Capital (WACC / Ke CAPM) y Spread Económico (EVA / Foso Defensivo)."""

    @staticmethod
    def _moat_classification(spread: Optional[float], ret_pct_label: str, ret_val: Optional[float], rate_val: float, label_rate: str) -> Tuple[str, str, str]:
        """Clasifica el foso defensivo (Wide/Narrow Moat vs destrucción de valor) según spread económico."""
        if spread is None or ret_val is None:
            return "N/A", "N/A", "Datos insuficientes para calcular el spread económico."
        if spread >= 0.15:
            return (
                "FOSO DEFENSIVO EXCEPCIONAL (WIDE MOAT)",
                "🏰 WIDE MOAT / COMPOUNDING MACHINE",
                f"El negocio genera un retorno ajustado ({ret_val*100:.2f}%) que supera a su costo de capital ({rate_val*100:.2f}%) por más de {spread*100:.2f} puntos porcentuales. Por cada $100 de capital empleado, crea más de $15 anuales de valor neto por encima de lo que exigen accionistas y bancos. Posee ventajas competitivas profundas y duraderas.",
            )
        if spread >= 0.05:
            return (
                "FOSO DEFENSIVO SÓLIDO (NARROW MOAT)",
                "🛡️ NARROW MOAT / CREACIÓN DE VALOR SOSTENIBLE",
                f"El negocio genera un Spread positivo de +{spread*100:.2f} p.p. sobre el {label_rate} ({rate_val*100:.2f}%), demostrando capacidad de generar valor económico superior a la media de forma constante frente a sus competidores.",
            )
        if spread >= 0.0:
            return (
                "RENDIMIENTO COMPETITIVO ESTÁNDAR",
                "⚖️ RENDIMIENTO COMPETITIVO ESTÁNDAR",
                f"El retorno ({ret_val*100:.2f}%) apenas cubre el costo de financiamiento ({rate_val*100:.2f}%), dejando un excedente marginal de +{spread*100:.2f} p.p. Opera en un entorno de alta competencia sin poder de fijación de precios.",
            )
        return (
            "DESTRUCCIÓN NETA DE VALOR ECONÓMICO",
            "⚠️ DESTRUCCIÓN DE VALOR ECONÓMICO",
            f"El retorno ({ret_val*100:.2f}%) es inferior al costo de capital exigido ({rate_val*100:.2f}%), destruyendo {abs(spread*100):.2f} puntos porcentuales de valor por cada ciclo operativo.",
        )

    @classmethod
    def calculate_wacc_and_spread(
        cls,
        ticker: str,
        recent_fy: str,
        period_data: Dict[str, Any],
        roic_adjusted: Optional[float],
        roic_traditional: Optional[float],
        benchmarks: Dict[str, Any],
        diluted_shares_10q: Optional[float] = None,
        archetype: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Calcula WACC / Ke institucional y Spread Económico sin constantes hardcodeadas de empresas."""
        raw_arch = archetype or (benchmarks.get("archetype") if benchmarks else None) or "STANDARD_CORPORATE"
        arch_norm = normalize_archetype(raw_arch, default="STANDARD_CORPORATE")

        sector_beta_fb = float((benchmarks or {}).get("damodaran_unlevered_beta", 1.10))
        sector_wacc_fb = float((benchmarks or {}).get("damodaran_industry_wacc", 0.088))

        if MarketDataExtractor is not None:
            mkt = MarketDataExtractor.get_market_data(
                ticker,
                diluted_shares_10q=diluted_shares_10q,
                sector_beta_fallback=sector_beta_fb,
                sector_wacc_fallback=sector_wacc_fb,
            )
        else:
            mkt = {
                "ticker": ticker,
                "price": None,
                "market_cap_usd_m": None,
                "rf_10y": None,
                "beta": None,
                "erp": None,
                "audit": {"status": "UNAVAILABLE_MODULE_MISSING", "notes": "MarketDataExtractor no disponible"},
            }

        rf = _first_present(_safe_float(mkt.get("rf_10y")), 0.0425) or 0.0425
        beta = _first_present(_safe_float(mkt.get("beta")), sector_beta_fb) or sector_beta_fb
        erp = _first_present(_safe_float(mkt.get("erp")), 0.0475) or 0.0475

        is_financial = arch_norm in ("FINANCIAL_BANKING", "INSURANCE")
        if is_financial:
            if beta < 0.80:
                beta = round(0.67 * beta + 0.33 * 1.0, 2)
            ke = max(rf + (beta * erp), rf + 0.0325)
            if "beta" in mkt:
                mkt["beta"] = beta
        else:
            ke = rf + (beta * erp)

        mcap_opt = _safe_float(mkt.get("market_cap_usd_m"))
        mcap_val = mcap_opt or 0.0
        debt = _to_millions(_safe_float(period_data.get("total_debt")) or 0.0) or 0.0

        if is_financial:
            ni_val = _to_millions(_safe_float(period_data.get("net_income")) or 0.0) or 0.0
            eq_val = _to_millions(_safe_float(period_data.get("stockholders_equity")) or 0.0) or 0.0
            gw_val = _to_millions(_safe_float(period_data.get("goodwill")) or 0.0) or 0.0
            raw_inta = period_data.get("intangible_assets") if period_data.get("intangible_assets") is not None else period_data.get("intangibles")
            inta_val = _to_millions(_safe_float(raw_inta) or 0.0) or 0.0

            tbv = max(1.0, eq_val - gw_val - inta_val) if eq_val > 0 else 0.0
            roe = (ni_val / eq_val) if eq_val > 0 else None
            rotce = (ni_val / tbv) if tbv > 0 else roe
            primary_return = rotce if rotce is not None else roe
            spread = (primary_return - ke) if primary_return is not None else None
            spread_trad = (roe - ke) if roe is not None else None

            moat_rating, moat_badge, _ = cls._moat_classification(spread, "ROTCE", primary_return, ke, "Ke")
            metric_name = "ROTCE" if arch_norm == "FINANCIAL_BANKING" else "ROE / ROTCE"
            metric_val = primary_return if primary_return is not None else 0.0
            return {
                "period": recent_fy,
                "model_type": "COST_OF_EQUITY_KE",
                "archetype": arch_norm,
                "market_data": mkt,
                "cost_of_equity_ke": ke,
                "cost_of_debt_kd_pre_tax": None,
                "cost_of_debt_kd_after_tax": None,
                "effective_tax_rate": _safe_float(period_data.get("effective_tax_rate")) or 0.21,
                "market_cap_usd_m": mcap_opt,
                "total_debt_usd_m": debt,
                "enterprise_value_usd_m": mcap_opt,
                "weight_equity": 1.0,
                "weight_debt": 0.0,
                "is_debt_free": False,
                "wacc": ke,
                "hurdle_rate": ke,
                "sector_wacc_benchmark": sector_wacc_fb,
                "roic_traditional": roe,
                "roic_adjusted": rotce,
                "rotce": rotce,
                "roe": roe,
                "tangible_book_value_usd_m": tbv,
                "economic_spread_traditional": spread_trad,
                "economic_spread_adjusted": spread,
                "spread": spread,
                "moat_rating": moat_rating,
                "moat_badge": moat_badge,
                "explanations": {
                    "ke_capm": f"Costo del Equity (Ke) = {ke*100:.2f}%: Tasa de corte institucional para {arch_norm} vía CAPM (Rf: {rf*100:.2f}%, Beta: {beta:.2f}, ERP: {erp*100:.2f}%).",
                    "kd_debt": "No aplicable para entidades bancarias y aseguradoras: la deuda y depósitos son pasivos operativos de intermediación.",
                    "wacc": f"Coste de Capital Aplicable = {ke*100:.2f}% (Cost of Equity Ke): Modelo institucional sobre patrimonio neto ({metric_name}), no WACC empresarial.",
                    "economic_spread": f"Spread de Retorno Excedente ({metric_name} - Ke) = {spread*100:+.2f} p.p. ({metric_name}: {metric_val*100:.2f}% vs Ke: {ke*100:.2f}%)." if spread is not None else "Datos insuficientes.",
                },
            }

        raw_interest = _safe_float(period_data.get("interest_expense"))
        interest = abs(_to_millions(raw_interest) or 0.0) if raw_interest is not None else ((debt * 0.045) if debt > 100.0 else 0.0)
        tax_rate = max(0.05, min(0.35, _safe_float(period_data.get("effective_tax_rate")) or 0.21))
        is_debt_free = debt <= 1.0
        if is_debt_free:
            kd_pre_tax = kd_after_tax = debt = 0.0
        else:
            kd_pre_tax = (interest / debt) if (debt > 0 and interest > 0) else rf
            if kd_pre_tax < 0.02:
                kd_pre_tax = rf + 0.006
            kd_after_tax = kd_pre_tax * (1.0 - tax_rate)

        total_enterprise_val = mcap_val + debt
        if total_enterprise_val > 0:
            we, wd = mcap_val / total_enterprise_val, debt / total_enterprise_val
        else:
            we, wd = 1.0, 0.0

        wacc = ke if is_debt_free else ((we * ke) + (wd * kd_after_tax))
        spread_adj = (roic_adjusted - wacc) if roic_adjusted is not None else None
        spread_trad = (roic_traditional - wacc) if roic_traditional is not None else None
        moat_rating, moat_badge, moat_expl = cls._moat_classification(spread_adj, "ROIC", roic_adjusted, wacc, "WACC")

        return {
            "period": recent_fy,
            "model_type": "WACC",
            "archetype": arch_norm,
            "market_data": mkt,
            "cost_of_equity_ke": ke,
            "cost_of_debt_kd_pre_tax": kd_pre_tax,
            "cost_of_debt_kd_after_tax": kd_after_tax,
            "effective_tax_rate": tax_rate,
            "market_cap_usd_m": mcap_opt,
            "total_debt_usd_m": debt,
            "enterprise_value_usd_m": total_enterprise_val if mcap_opt is not None else None,
            "weight_equity": we,
            "weight_debt": wd,
            "is_debt_free": is_debt_free,
            "wacc": wacc,
            "hurdle_rate": wacc,
            "sector_wacc_benchmark": sector_wacc_fb,
            "roic_traditional": roic_traditional,
            "roic_adjusted": roic_adjusted,
            "economic_spread_traditional": spread_trad,
            "economic_spread_adjusted": spread_adj,
            "spread": spread_adj if spread_adj is not None else spread_trad,
            "moat_rating": moat_rating,
            "moat_badge": moat_badge,
            "explanations": {
                "ke_capm": f"Costo del Equity (Ke) = {ke*100:.2f}%: Tasa mínima que exigen los accionistas por invertir en la empresa. Calculado mediante CAPM: Tasa Libre de Riesgo Rf ({rf*100:.2f}%) + Beta ({beta:.2f}) × Prima de Riesgo ERP ({erp*100:.2f}%).",
                "kd_debt": "Empresa sin deuda financiera: No incurre en gastos de interés ni requiere ponderar deuda." if is_debt_free else f"Costo de la Deuda Neto = {kd_after_tax*100:.2f}% (Tasa antes de impuestos {kd_pre_tax*100:.2f}% con escudo fiscal del {tax_rate*100:.1f}%).",
                "wacc": f"WACC = {wacc*100:.2f}%: Tasa de corte u obstáculo financiero global. Pondera {we*100:.1f}% de Equity y {wd*100:.1f}% de Deuda a valores de mercado. Frente a la mediana del sector ({sector_wacc_fb*100:.2f}%), su costo de financiamiento es {'más bajo y competitivo.' if wacc <= sector_wacc_fb else 'ligeramente superior.'}",
                "economic_spread": moat_expl,
            },
        }
