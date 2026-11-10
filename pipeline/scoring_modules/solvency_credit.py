"""
solvency_credit.py - Motor Institucional de Solvencia, Liquidez, Cobertura y Riesgo de Crédito:
Deuda Neta / EBITDA, Deuda Neta / FCF, Cobertura de Intereses, Altman Z'' y Rating Sintético Damodaran.
"""

from typing import Any, Dict, List, Optional, Tuple

from .scoring_utils import _first_present, _safe_float, _to_millions, normalize_archetype


_SYNTHETIC_RATING_TABLE = (
    (8.5, "AAA", "GRADO INSTITUCIONAL MÁXIMO (AAA / Aaa)", 0.0060, 0.60, "< 0.2%", "#2E7D32"),
    (6.5, "AA", "SOLVENCIA MUY FUERTE (AA / Aa2)", 0.0080, 0.80, "0.3%", "#2E7D32"),
    (5.5, "A+", "SOLVENCIA ROBUSTA (A+ / A1)", 0.0110, 1.10, "0.5%", "#1976D2"),
    (4.25, "A", "SOLVENCIA BUENA (A / A2)", 0.0130, 1.30, "0.7%", "#1976D2"),
    (3.0, "A-", "SOLVENCIA SATISFACTORIA (A- / A3)", 0.0150, 1.50, "1.0%", "#1976D2"),
    (2.5, "BBB", "GRADO DE INVERSIÓN LÍMITE (BBB / Baa2)", 0.0200, 2.00, "2.2%", "#F57C00"),
    (2.25, "BB+", "GRADO ESPECULATIVO (BB+ / Ba1 - HIGH YIELD)", 0.0250, 2.50, "3.5%", "#F57C00"),
    (2.0, "BB", "GRADO ESPECULATIVO MODERADO (BB / Ba2)", 0.0300, 3.00, "5.0%", "#D32F2F"),
    (1.5, "B", "ALTA VULNERABILIDAD FINANCIERA (B / B2)", 0.0450, 4.50, "10.0%", "#D32F2F"),
    (1.0, "CCC", "RIESGO SUSTANCIAL DE IMPAGO (CCC / Caa)", 0.0800, 8.00, "25.0%", "#D32F2F"),
)


class DebtSolvencyEngine:
    """
    Motor Institucional de Análisis de Deuda, Solvencia y Estrés Financiero:
    1. Cash Flow Leverage (Net Debt / EBITDA & FCF)
    2. Debt Service Coverage (Interest Coverage & Financial Burden)
    3. Liquidity & Rollover Risk
    4. Altman Z''-Score & Damodaran Synthetic Rating
    """

    @classmethod
    def _get_synthetic_rating(cls, int_cov: Optional[float], is_debt_free: bool = False) -> Dict[str, Any]:
        """Asigna el rating sintético, spread de default y probabilidad empírica según Damodaran."""
        if is_debt_free:
            return {
                "rating": "AAA",
                "desc": "MÁXIMA CALIDAD CREDITICIA (LIBRE DE DEUDA)",
                "default_spread": 0.0040,
                "default_spread_pct": 0.40,
                "default_probability": "< 0.1%",
                "color": "#2E7D32",
            }
        if int_cov is None:
            threshold, rating, desc, spread, spread_pct, prob, color = _SYNTHETIC_RATING_TABLE[0]
            return {
                "rating": rating,
                "desc": desc,
                "default_spread": spread,
                "default_spread_pct": spread_pct,
                "default_probability": prob,
                "color": color,
            }
        for threshold, rating, desc, spread, spread_pct, prob, color in _SYNTHETIC_RATING_TABLE:
            if int_cov >= threshold:
                return {
                    "rating": rating,
                    "desc": desc,
                    "default_spread": spread,
                    "default_spread_pct": spread_pct,
                    "default_probability": prob,
                    "color": color,
                }
        return {
            "rating": "D",
            "desc": "DEFAULT INMINENTE O TÉCNICO (D / Default)",
            "default_spread": 0.1500,
            "default_spread_pct": 15.00,
            "default_probability": "> 50.0%",
            "color": "#D32F2F",
        }

    @staticmethod
    def _extract_solvency_vars(curr: Dict[str, Any]) -> Dict[str, Any]:
        """Normaliza variables de balance y flujo en $M para un período."""
        debt = _to_millions(_safe_float(curr.get("total_debt")) or 0.0) or 0.0
        raw_cash = _first_present(_safe_float(curr.get("total_liquid_cash")), _safe_float(curr.get("cash")), 0.0) or 0.0
        cash = _to_millions(raw_cash) or 0.0
        net_debt = debt - cash

        ebit = _to_millions(_first_present(_safe_float(curr.get("operating_income")), _safe_float(curr.get("ebit"))))
        dna = _to_millions(_safe_float(curr.get("depreciation_and_amortization")) or 0.0) or 0.0
        ebitda = (ebit + dna) if ebit is not None else None

        cfo = _to_millions(_first_present(_safe_float(curr.get("cfo")), _safe_float(curr.get("operating_cash_flow"))))
        capex = _to_millions(_safe_float(curr.get("capex")) or 0.0) or 0.0
        fcf = (cfo - capex) if cfo is not None else None

        st_debt = _to_millions(_safe_float(curr.get("short_term_debt")) or 0.0) or 0.0
        lt_debt = _to_millions(_safe_float(curr.get("long_term_debt")) or 0.0) or 0.0

        raw_interest = _safe_float(curr.get("interest_expense"))
        if raw_interest is not None:
            interest = abs(_to_millions(raw_interest) or 0.0)
            interest_estimated = False
        elif debt > 100.0:
            interest = debt * 0.045
            interest_estimated = True
        else:
            interest = 0.0
            interest_estimated = False

        ca = _to_millions(_safe_float(curr.get("current_assets")))
        cl = _to_millions(_safe_float(curr.get("current_liabilities")))
        ar = _to_millions(_safe_float(curr.get("accounts_receivable")) or 0.0) or 0.0
        inv = _to_millions(_safe_float(curr.get("inventory")) or 0.0) or 0.0
        assets = _to_millions(_safe_float(curr.get("total_assets")))
        raw_eq = _safe_float(curr.get("stockholders_equity"))
        equity = (_to_millions(raw_eq) or 0.0) if raw_eq is not None else 0.0
        raw_re = _safe_float(curr.get("retained_earnings"))
        re = (_to_millions(raw_re) or 0.0) if raw_re is not None else 0.0
        raw_liab = _safe_float(curr.get("total_liabilities"))
        liab = _to_millions(raw_liab) if raw_liab is not None else ((assets - equity) if assets is not None else None)

        return {
            "debt": debt,
            "cash": cash,
            "net_debt": net_debt,
            "ebit": ebit,
            "dna": dna,
            "ebitda": ebitda,
            "cfo": cfo,
            "capex": capex,
            "fcf": fcf,
            "st_debt": st_debt,
            "lt_debt": lt_debt,
            "interest": interest,
            "interest_estimated": interest_estimated,
            "ca": ca,
            "cl": cl,
            "ar": ar,
            "inv": inv,
            "assets": assets,
            "equity": equity,
            "re": re,
            "liab": liab,
        }

    @staticmethod
    def _compute_leverage_block(fy: str, v: Dict[str, Any]) -> Tuple[Dict[str, Any], bool]:
        """Calcula apalancamiento sobre EBITDA/FCF/CFO para un período."""
        debt, cash, net_debt = v["debt"], v["cash"], v["net_debt"]
        ebit, dna, ebitda = v["ebit"], v["dna"], v["ebitda"]
        cfo, capex, fcf = v["cfo"], v["capex"], v["fcf"]

        is_debt_free = debt <= 1.0
        is_net_cash = net_debt <= 0.0

        nd_to_ebitda = None
        nd_to_ebitda_str = "N/D"
        if is_debt_free or is_net_cash:
            nd_to_ebitda = round(net_debt / ebitda, 2) if (ebitda and ebitda > 0) else 0.0
            nd_to_ebitda_str = "CAJA NETA"
            status_lev, color_lev, badge_lev = "EXCELENTE (POSICIÓN DE CAJA NETA)", "#2E7D32", "CAJA NETA"
            diag_lev = f"Estructura ultra sólida sin deuda neta ({round(net_debt, 1):+,.1f}$M). La liquidez disponible excede a la deuda total."
        elif ebitda and ebitda > 0:
            ratio = net_debt / ebitda
            nd_to_ebitda = round(ratio, 2)
            nd_to_ebitda_str = f"{ratio:.2f}x"
            if ratio < 1.5:
                status_lev, color_lev, badge_lev = "GRADO INVERSIÓN SUPERIOR (< 1.5x)", "#2E7D32", "APALANCAMIENTO BAJO"
                diag_lev = f"Apalancamiento muy conservador ({ratio:.2f}x EBITDA). La empresa extinguiría su deuda neta en {ratio:.1f} años de beneficio operativo bruto."
            elif ratio <= 3.0:
                status_lev, color_lev, badge_lev = "APALANCAMIENTO MODERADO (1.5x - 3.0x)", "#1976D2", "APALANCAMIENTO SALUDABLE"
                diag_lev = f"Apalancamiento equilibrado y controlado ({ratio:.2f}x EBITDA), común en empresas con flujos de caja predecibles."
            elif ratio <= 4.0:
                status_lev, color_lev, badge_lev = "VULNERABILIDAD FINANCIERA (3.0x - 4.0x)", "#F57C00", "ZONA DE VIGILANCIA"
                diag_lev = f"Apalancamiento elevado ({ratio:.2f}x EBITDA). Requiere seguimiento de covenants y tipos de interés."
            else:
                status_lev, color_lev, badge_lev = "GRADO ESPECULATIVO / ALTO APALANCAMIENTO (> 4.0x)", "#D32F2F", "ALERTA COVENANTS"
                diag_lev = f"Alto riesgo de sobreendeudamiento ({ratio:.2f}x EBITDA). Vulnerabilidad crítica ante caídas en demanda."
        else:
            status_lev, color_lev, badge_lev = "EBITDA NEGATIVO O NULO", "#D32F2F", "DÉFICIT OPERATIVO"
            diag_lev = "EBITDA insuficiente para calcular el ratio de amortización."

        if is_debt_free or is_net_cash:
            nd_to_fcf = round(net_debt / fcf, 2) if (fcf and fcf > 0) else 0.0
            nd_to_fcf_str = "CAJA NETA"
        elif fcf and fcf > 0:
            r_fcf = net_debt / fcf
            nd_to_fcf = round(r_fcf, 2)
            nd_to_fcf_str = f"{r_fcf:.2f}x"
        else:
            nd_to_fcf, nd_to_fcf_str = None, "N/D"

        return {
            "period": fy,
            "total_debt": round(debt, 1),
            "cash": round(cash, 1),
            "net_debt": round(net_debt, 1),
            "ebit": round(ebit, 1) if ebit is not None else None,
            "dna": round(dna, 1),
            "ebitda": round(ebitda, 1) if ebitda is not None else None,
            "cfo": round(cfo, 1) if cfo is not None else None,
            "capex": round(capex, 1),
            "fcf": round(fcf, 1) if fcf is not None else None,
            "net_debt_to_ebitda": nd_to_ebitda,
            "net_debt_to_ebitda_str": nd_to_ebitda_str,
            "net_debt_to_fcf": nd_to_fcf,
            "net_debt_to_fcf_str": nd_to_fcf_str,
            "debt_to_cfo": round(debt / cfo, 2) if (cfo and cfo > 0) else None,
            "is_debt_free": is_debt_free,
            "is_net_cash": is_net_cash,
            "status": status_lev,
            "badge": badge_lev,
            "color": color_lev,
            "diagnosis": diag_lev,
        }, is_debt_free

    @staticmethod
    def _compute_coverage_block(
        fy: str,
        curr: Dict[str, Any],
        v: Dict[str, Any],
        is_financial: bool,
        is_reit: bool,
        is_debt_free: bool,
    ) -> Tuple[Dict[str, Any], Optional[float]]:
        """Calcula la cobertura de carga financiera segmentada por arquetipo."""
        ebit, ebitda, cfo, interest = v["ebit"], v["ebitda"], v["cfo"], v["interest"]
        int_cov: Optional[float] = None
        if is_financial:
            raw_eq = _safe_float(curr.get("stockholders_equity")) or 0.0
            raw_ass = _safe_float(curr.get("total_assets")) or 0.0
            eq_to_assets = (raw_eq / raw_ass * 100.0) if (raw_ass and raw_ass > 0) else 0.0
            int_cov_str = f"Cap. {eq_to_assets:.1f}% Activos"
            cash_cov, cash_cov_str, burden_pct = None, "N/A (BANCA / SEGUROS)", 0.0
            status_srv, badge_srv, color_srv = "FONDEO BANCARIO / RESERVAS TÉCNICAS", "SOLVENCIA REGULATORIA", "#1976D2"
            diag_srv = f"En intermediación bancaria y seguros, el gasto por intereses (${interest:.1f}M) remunera a los depositantes y fondos de clientes, constituyendo un coste de ventas operativo y no una carga de deuda financiera corporativa. La solvencia se mide por adecuación de capital patrimonial ({eq_to_assets:.1f}% de los activos) y ratios regulatorios (CET1/RBC)."
        elif is_reit:
            re_dep = _to_millions(_safe_float(curr.get("real_estate_depreciation")) or 0.0) or 0.0
            reit_ebitda = ebitda if (ebitda is not None and ebitda > (ebit or 0)) else ((ebit or 0.0) + re_dep)
            cov = (reit_ebitda / interest) if interest > 0 else 99.0
            int_cov, int_cov_str = round(cov, 2), f"{cov:.1f}x (EBITDAre/Int)"
            raw_cc = (cfo / interest) if (cfo and cfo > 0 and interest > 0) else None
            cash_cov, cash_cov_str = (round(raw_cc, 2) if raw_cc is not None else None), (f"{raw_cc:.1f}x" if raw_cc is not None else "N/D")
            burden_pct = round((interest / cfo * 100.0) if (cfo and cfo > 0) else 0.0, 2)
            if cov >= 4.5:
                status_srv, color_srv, badge_srv = "COBERTURA INMOBILIARIA EXCELENTE (> 4.5x)", "#2E7D32", "MÁXIMA PROTECCIÓN REIT"
                diag_srv = f"Los flujos operativos inmobiliarios (EBITDAre) cubren {cov:.1f} veces los intereses de la deuda. Excelente solvencia para soportar ciclos de tipos."
            elif cov >= 3.2:
                status_srv, color_srv, badge_srv = "COBERTURA SALUDABLE REIT (3.2x - 4.5x)", "#1976D2", "COBERTURA ROBUSTA"
                diag_srv = f"Cobertura cómoda ({cov:.1f}x EBITDAre/Intereses). Margen operativo holgado propio de REITs con Grado de Inversión institucional."
            elif cov >= 2.2:
                status_srv, color_srv, badge_srv = "VULNERABILIDAD A TIPOS (2.2x - 3.2x)", "#F57C00", "VIGILANCIA DE APALANCAMIENTO"
                diag_srv = f"Cobertura ajustada ({cov:.1f}x EBITDAre/Intereses). Sensibilidad ante incrementos en costes de refinanciación hipotecaria o bonos."
            else:
                status_srv, color_srv, badge_srv = "ESTRÉS FINANCIERO INMOBILIARIO (< 2.2x)", "#D32F2F", "RIESGO DE REFINANCIACIÓN"
                diag_srv = f"Cobertura de intereses precaria ({cov:.1f}x EBITDAre/Intereses). Alto riesgo de refinanciación forzada o recorte de dividendo."
        elif is_debt_free:
            int_cov_str, cash_cov, cash_cov_str, burden_pct = "INFINITA (SIN DEUDA)", None, "INFINITA (SIN DEUDA)", 0.0
            status_srv, color_srv, badge_srv = "LIBRE DE DEUDA", "#2E7D32", "SERVICIO BLINDADO"
            diag_srv = "La compañía opera sin deuda financiera, por lo que carece de gasto financiero que comprometa sus resultados."
        elif interest > 0 and ebit is not None:
            cov = ebit / interest
            int_cov, int_cov_str = round(cov, 2), f"{cov:.1f}x"
            raw_cc = (cfo / interest) if (cfo and cfo > 0) else None
            cash_cov, cash_cov_str = (round(raw_cc, 2) if raw_cc is not None else None), (f"{raw_cc:.1f}x" if raw_cc is not None else "N/D")
            burden_pct = round((interest / cfo * 100.0) if (cfo and cfo > 0) else 0.0, 2)
            if cov >= 10.0:
                status_srv, color_srv, badge_srv = "COBERTURA EXCELENTE (> 10.0x)", "#2E7D32", "MÁXIMA PROTECCIÓN"
                diag_srv = f"Los beneficios operativos cubren {cov:.1f} veces los intereses. Carga financiera insignificante ({burden_pct:.1f}% del CFO)."
            elif cov >= 5.0:
                status_srv, color_srv, badge_srv = "COBERTURA SALUDABLE (5.0x - 10.0x)", "#1976D2", "COBERTURA ROBUSTA"
                diag_srv = f"Cobertura cómoda ({cov:.1f}x). Margen operativo holgado para resistir incrementos en el coste de financiación."
            elif cov >= 2.5:
                status_srv, color_srv, badge_srv = "VULNERABILIDAD A CICLOS (2.5x - 5.0x)", "#F57C00", "VIGILANCIA DE INTERESES"
                diag_srv = f"Cobertura ajustada ({cov:.1f}x). Sensibilidad ante caídas de margen o subidas de tipos."
            else:
                status_srv, color_srv, badge_srv = "PELIGRO DE DEFAULT (< 2.5x)", "#D32F2F", "ESTRÉS FINANCIERO"
                diag_srv = f"Carga de intereses asfixiante ({cov:.1f}x). Alto riesgo de refinanciación forzada o impago."
        else:
            int_cov_str, cash_cov, cash_cov_str, burden_pct = "N/D", None, "N/D", 0.0
            status_srv, color_srv, badge_srv = "GASTO FINANCIERO MÍNIMO", "#2E7D32", "SIN CARGA FINANCIERA"
            diag_srv = "Gasto financiero reportado mínimo o absorbido por ingresos financieros."

        return {
            "period": fy,
            "ebit": round(ebit, 1) if ebit is not None else None,
            "interest_expense": round(interest, 1),
            "interest_estimated": v["interest_estimated"],
            "interest_coverage": int_cov,
            "interest_coverage_str": int_cov_str,
            "cash_interest_coverage": cash_cov,
            "cash_interest_coverage_str": cash_cov_str,
            "financial_burden_pct": burden_pct,
            "status": status_srv,
            "status_service": status_srv,
            "badge": badge_srv,
            "color": color_srv,
            "diagnosis": diag_srv,
        }, int_cov

    @staticmethod
    def _compute_liquidity_block(fy: str, v: Dict[str, Any]) -> Dict[str, Any]:
        """Calcula ratios de liquidez ácida, corriente y perfil de vencimientos."""
        ca, cl, cash, ar, inv, st_debt, lt_debt, debt, equity = (
            v["ca"], v["cl"], v["cash"], v["ar"], v["inv"], v["st_debt"], v["lt_debt"], v["debt"], v["equity"]
        )
        cr = round(ca / cl, 2) if (ca is not None and cl and cl > 0) else None
        qr = round((cash + ar) / cl, 2) if (cl and cl > 0) else None
        cash_r = round(cash / cl, 2) if (cl and cl > 0) else None
        rollover_pct = round((st_debt / debt) * 100.0, 2) if debt > 0 else 0.0
        tot_cap = debt + max(0.0, equity)
        debt_to_cap_pct = round((debt / tot_cap) * 100.0, 2) if tot_cap > 0 else 0.0

        if qr is not None and qr >= 1.2:
            st_l, col_l, bdg_l = "LIQUIDEZ EXCELENTE (QUICK RATIO > 1.2x)", "#2E7D32", "COLCHÓN DE LIQUIDEZ"
            diag_l = f"La liquidez ácida ({qr:.2f}x) cubre sobradamente los pasivos inmediatos sin depender de vender inventario."
        elif qr is not None and qr >= 0.8:
            st_l, col_l, bdg_l = "LIQUIDEZ EQUILIBRADA (0.8x - 1.2x)", "#1976D2", "EQUILIBRADA"
            diag_l = f"Liquidez operativa dentro de la media ({qr:.2f}x). Gestión estándar de cobros y caja."
        elif qr is not None:
            st_l, col_l, bdg_l = "GESTIÓN DE CAPITAL DE TRABAJO AGRESIVA (< 0.8x)", "#F57C00", "LIQUIDEZ AJUSTADA"
            diag_l = f"Quick ratio de {qr:.2f}x. Típico en empresas con poder de negociación que financian operaciones con proveedores (Working Capital negativo)."
        else:
            st_l, col_l, bdg_l = "NO APLICABLE (ENTIDAD FINANCIERA / MODELO SIN BALANCE CORRIENTE)", "#607D8B", "N/A FINANCIERA"
            diag_l = "Estructura de balance sin clasificación corriente/no corriente (bancos y aseguradoras operan con activos/pasivos financieros directos)."

        return {
            "period": fy,
            "current_assets": round(ca, 1) if ca is not None else None,
            "current_liabilities": round(cl, 1) if cl is not None else None,
            "accounts_receivable": round(ar, 1),
            "inventory": round(inv, 1),
            "cash": round(cash, 1),
            "current_ratio": cr,
            "quick_ratio": qr,
            "cash_ratio": cash_r,
            "short_term_debt": round(st_debt, 1),
            "long_term_debt": round(lt_debt, 1),
            "total_debt": round(debt, 1),
            "rollover_risk_pct": rollover_pct,
            "debt_to_capital_pct": debt_to_cap_pct,
            "status": st_l,
            "badge": bdg_l,
            "color": col_l,
            "diagnosis": diag_l,
        }

    @classmethod
    def _compute_distress_block(
        cls,
        fy: str,
        curr: Dict[str, Any],
        v: Dict[str, Any],
        arch_norm: str,
        is_financial: bool,
        is_reit: bool,
        is_debt_free: bool,
        int_cov: Optional[float],
    ) -> Dict[str, Any]:
        """Calcula Altman Z''-Score y rating sintético de Damodaran por arquetipo."""
        is_altman_applicable = not (is_financial or is_reit)
        assets, liab, ca, cl, re, ebit, equity = v["assets"], v["liab"], v["ca"], v["cl"], v["re"], v["ebit"], v["equity"]
        z_score = x1 = x2 = x3 = x4 = None

        if is_financial:
            zone, badge, color = "NO APLICABLE", "NO APLICABLE", "#607D8B"
            diag_alt = f"Altman Z''-Score NO APLICABLE para entidades del arquetipo '{arch_norm}'. El modelo econométrico de Altman fue diseñado y calibrado exclusivamente para corporaciones industriales y de servicios no financieras. En intermediación bancaria y seguros, los activos corrientes/no corrientes no están segmentados y el apalancamiento operativo del balance provocaría una falsa alarma de quiebra inminente."
        elif is_reit:
            zone, badge, color = "NO APLICABLE", "NO APLICABLE", "#607D8B"
            diag_alt = "Altman Z''-Score NO APLICABLE para sociedades de inversión inmobiliaria (REITs). El modelo castiga severamente la ausencia de capital de trabajo circulante y la deuda hipotecaria a largo plazo. La solvencia de un REIT se mide por Deuda Neta / EBITDAre, Cobertura EBITDAre / Intereses y FFO Payout Ratio."
        elif assets and assets > 0 and liab and liab > 0:
            nwc = (ca - cl) if (ca is not None and cl is not None) else 0.0
            x1, x2 = round(nwc / assets, 4), round(re / assets, 4)
            x3, x4 = round((ebit / assets), 4) if ebit is not None else 0.0, round(max(0.0, equity) / liab, 4)
            z_score = round(6.56 * x1 + 3.26 * x2 + 6.72 * x3 + 1.05 * x4, 2)
            if z_score > 2.60:
                zone, badge, color = "ZONA SEGURA (BAJO RIESGO DE QUIEBRA)", "ZONA SEGURA", "#2E7D32"
                diag_alt = f"Altman Z''-Score de {z_score:.2f} (> 2.60). Probabilidad estadística de insolvencia virtualmente nula a 2 años vista."
            elif z_score >= 1.10:
                zone, badge, color = "ZONA GRIS (PRECAUCIÓN Y SEGUIMIENTO)", "ZONA GRIS", "#F57C00"
                diag_alt = f"Altman Z''-Score de {z_score:.2f} (entre 1.10 y 2.60). Requiere seguimiento de márgenes y apalancamiento."
            else:
                zone, badge, color = "ZONA DE DISTRESS (ALTO RIESGO DE INSOLVENCIA)", "PELIGRO DE QUIEBRA", "#D32F2F"
                diag_alt = f"Altman Z''-Score crítico de {z_score:.2f} (< 1.10). Severo estrés financiero y riesgo de default."
        else:
            zone, badge, color, diag_alt = "DATOS INSUFICIENTES", "N/D", "#757575", "Estructura de balance incompleta para calcular Altman Z''-Score."

        if is_financial:
            raw_eq = _safe_float(curr.get("stockholders_equity")) or 0.0
            raw_ass = _safe_float(curr.get("total_assets")) or 0.0
            raw_ni = _safe_float(curr.get("net_income")) or 0.0
            eq_ratio = (raw_eq / raw_ass) if (raw_ass and raw_ass > 0) else 0.0
            roe_val = (raw_ni / raw_eq) if (raw_eq and raw_eq > 0) else 0.0
            if eq_ratio >= 0.12 and roe_val >= 0.12:
                s_rat, s_desc, d_spread, d_prob, r_col = "AA-", "SOLVENCIA BANCARIA DE PRIMER NIVEL (AA-)", 0.0090, "0.4%", "#2E7D32"
            elif eq_ratio >= 0.08 and roe_val >= 0.08:
                s_rat, s_desc, d_spread, d_prob, r_col = "A+", "SOLVENCIA ROBUSTA BANCARIA (A+)", 0.0110, "0.5%", "#1976D2"
            elif eq_ratio >= 0.06:
                s_rat, s_desc, d_spread, d_prob, r_col = "BBB+", "GRADO DE INVERSIÓN BANCARIO (BBB+)", 0.0180, "1.8%", "#F57C00"
            else:
                s_rat, s_desc, d_spread, d_prob, r_col = "BB", "CAPITALIZACIÓN AJUSTADA (BB)", 0.0300, "5.0%", "#D32F2F"
        else:
            cov_arg = (int_cov * 1.25) if (is_reit and int_cov is not None) else int_cov
            sd = cls._get_synthetic_rating(cov_arg, is_debt_free=is_debt_free)
            s_rat, s_desc = sd["rating"], f"{sd['desc']} [REIT EBITDAre adj]" if is_reit else sd["desc"]
            d_spread, d_prob, r_col = sd["default_spread"], sd["default_probability"], sd["color"]

        entry: Dict[str, Any] = {
            "period": fy,
            "is_applicable": is_altman_applicable,
            "altman_x1": x1,
            "altman_x2": x2,
            "altman_x3": x3,
            "altman_x4": x4,
            "altman_z_double_prime": z_score,
            "altman_zone": zone,
            "altman_badge": badge,
            "altman_color": color,
            "altman_diagnosis": diag_alt,
            "synthetic_rating": s_rat,
            "synthetic_rating_desc": s_desc,
            "default_spread": d_spread,
            "default_spread_pct": round(d_spread * 100.0, 2),
            "default_probability": d_prob,
            "rating_color": r_col,
        }
        if not is_altman_applicable:
            entry["pedagogical_guidance"] = {
                "model": "Altman Z''-Score (4 Variables)",
                "status": "NO APLICABLE",
                "archetype": arch_norm,
                "what_it_measures": "Modelo econométrico multivariante de predicción de insolvencia y quiebra a 2 años para corporaciones industriales y de servicios.",
                "formula": "Z'' = 6.56*X1 (NWC/Assets) + 3.26*X2 (RE/Assets) + 6.72*X3 (EBIT/Assets) + 1.05*X4 (Book Equity/Liabilities)",
                "why_not_applicable": (
                    f"Inhibido por diseño metodológico institucional para arquetipos '{arch_norm}'. "
                    + (
                        "En sociedades de inversión inmobiliaria (REITs), los activos son inmuebles generadores de rentas financiados con deuda a largo plazo y el flujo libre se distribuye en dividendos (> 90%), haciendo que el concepto de capital circulante (NWC) carezca de relevancia económica."
                        if is_reit else
                        "Altman Z'' fue calibrado exclusivamente para firmas no financieras. En bancos y aseguradoras, los depósitos y reservas técnicas constituyen pasivos operativos de intermediación, provocando ratios de capital de trabajo nulo y deuda aparente masiva que disparan falsas alarmas de quiebra inminente (< 1.10). La solvencia se evalúa mediante marcos de capital regulatorio (CET1 para banca y RBC / Solvencia II para aseguradoras)."
                    )
                ),
                "replacement_metrics": (
                    ["Deuda Neta / EBITDAre", "Cobertura EBITDAre / Intereses", "FFO / Deuda Total", "AFFO Payout Ratio"]
                    if is_reit else
                    ["Ratio CET1", "Tier 1 Capital", "Total Capital Ratio", "LCR (Liquidity Coverage Ratio)", "RBC Ratio (Seguros)"]
                ),
            }
        return entry

    @staticmethod
    def _build_global_solvency_verdict(
        arch_norm: str,
        is_financial: bool,
        is_reit: bool,
        latest_lev: Dict[str, Any],
        latest_cov: Dict[str, Any],
        latest_dist: Dict[str, Any],
    ) -> Tuple[str, str, str]:
        """Genera el dictamen global consolidado de solvencia y riesgo crediticio."""
        if is_financial:
            return (
                f"SOLVENCIA INSTITUCIONAL REGULADA ({arch_norm}): Los modelos econométricos predictivos de quiebra corporativa (Altman Z'') no aplican a entidades de balance financiero. La solvencia, liquidez y adecuación de capital se evalúan mediante ratios regulatorios (Ratio CET1, Tier 1 Capital, Ratio de Cobertura de Liquidez LCR y Cobertura de Provisiones / NPLs).",
                "SOLVENCIA REGULATORIA",
                "#1976D2",
            )
        if is_reit:
            return (
                f"ESTRUCTURA DE CAPITAL INMOBILIARIA ({arch_norm}): Cobertura EBITDAre/Intereses de {latest_cov.get('interest_coverage_str')} con rating sintético {latest_dist.get('synthetic_rating')}. Altman Z'' inhibido metodológicamente por no aplicar a carteras de inmuebles comerciales en renta.",
                "SOLVENCIA INMOBILIARIA",
                latest_cov.get("color", "#1976D2"),
            )
        z_val = latest_dist.get("altman_z_double_prime")
        nd_eb = latest_lev.get("net_debt_to_ebitda")
        if (latest_lev.get("is_net_cash") or (nd_eb is not None and nd_eb < 1.5)) and (z_val is not None and z_val > 2.60):
            return (
                f"FORTALEZA FINANCIERA INQUEBRANTABLE (GRADO INSTITUCIONAL AAA/AA): Apalancamiento óptimo ({latest_lev.get('net_debt_to_ebitda_str')}), cobertura de intereses de {latest_cov.get('interest_coverage_str')} y Altman Z''-Score de {latest_dist.get('altman_z_double_prime', 'N/D')} en Zona Segura. Cero estrés crediticio, con capacidad excepcional de financiación en cualquier ciclo macroeconómico.",
                "MÁXIMA SOLVENCIA INSTITUCIONAL",
                "#2E7D32",
            )
        if z_val is not None and z_val < 1.10:
            return (
                f"ALERTA CRÍTICA DE SOLVENCIA Y ESTRÉS FINANCIERO: Altman Z''-Score de {z_val} en Zona de Distress. Apalancamiento de {latest_lev.get('net_debt_to_ebitda_str')} y cobertura de {latest_cov.get('interest_coverage_str')}. Alto riesgo de incumplimiento de covenants y vulnerabilidad ante vencimientos de deuda.",
                "ALERTA DE INSOLVENCIA",
                "#D32F2F",
            )
        return (
            f"SOLVENCIA EQUILIBRADA BAJO MONITOREO: Apalancamiento controlado ({latest_lev.get('net_debt_to_ebitda_str')}), cobertura de {latest_cov.get('interest_coverage_str')} y Altman Z''-Score de {latest_dist.get('altman_z_double_prime', 'N/D')}. Estructura de capital adecuada sin riesgos inminentes de impago.",
            "SOLVENCIA MODERADA",
            "#1976D2",
        )

    @classmethod
    def calculate_solvency_series(
        cls,
        fiscal_years: List[str],
        period_metrics: Dict[str, Dict[str, Any]],
        benchmarks: Optional[Dict[str, Any]] = None,
        ticker: str = "",
        market_cap: Optional[float] = None,
        archetype: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Calcula la serie histórica completa y LTM de solvencia, liquidez y riesgo de quiebra."""
        raw_arch = archetype or (benchmarks.get("archetype") if benchmarks else None) or "STANDARD_CORPORATE"
        arch_norm = normalize_archetype(raw_arch, default="STANDARD_CORPORATE")
        is_financial = arch_norm in ("FINANCIAL_BANKING", "INSURANCE")
        is_reit = arch_norm == "REAL_ESTATE_REIT"

        leverage_series: Dict[str, Any] = {}
        coverage_series: Dict[str, Any] = {}
        liquidity_series: Dict[str, Any] = {}
        distress_series: Dict[str, Any] = {}

        for fy in fiscal_years:
            curr = period_metrics.get(fy, {})
            v = cls._extract_solvency_vars(curr)
            lev_entry, is_debt_free = cls._compute_leverage_block(fy, v)
            cov_entry, int_cov = cls._compute_coverage_block(fy, curr, v, is_financial, is_reit, is_debt_free)
            leverage_series[fy] = lev_entry
            coverage_series[fy] = cov_entry
            liquidity_series[fy] = cls._compute_liquidity_block(fy, v)
            distress_series[fy] = cls._compute_distress_block(
                fy, curr, v, arch_norm, is_financial, is_reit, is_debt_free, int_cov
            )

        recent_period = "LTM" if "LTM" in fiscal_years else (fiscal_years[0] if fiscal_years else "N/A")
        latest_lev = leverage_series.get(recent_period, {})
        latest_cov = coverage_series.get(recent_period, {})
        latest_liq = liquidity_series.get(recent_period, {})
        latest_dist = distress_series.get(recent_period, {})
        verdict, badge, color = cls._build_global_solvency_verdict(arch_norm, is_financial, is_reit, latest_lev, latest_cov, latest_dist)

        return {
            "available": True,
            "archetype": arch_norm,
            "is_financial": is_financial,
            "ticker": ticker.upper(),
            "periods": fiscal_years,
            "recent_period": recent_period,
            "cash_flow_leverage": leverage_series,
            "debt_service": coverage_series,
            "liquidity_and_refinancing": liquidity_series,
            "distress_and_credit_models": distress_series,
            "latest_result": {
                "period": recent_period,
                "is_financial": is_financial,
                "is_debt_free": latest_lev.get("is_debt_free"),
                "cash_flow_leverage": latest_lev,
                "debt_service": latest_cov,
                "liquidity": latest_liq,
                "distress_models": latest_dist,
                "solvency_verdict": verdict,
                "global_color": color,
                "global_badge": badge,
            },
        }
