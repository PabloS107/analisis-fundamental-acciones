# -*- coding: utf-8 -*-
"""
Módulo de Estados Financieros (Vista Estandarizada 10Y + LTM y SEC As-Reported 3Y + LTM).
Consume los estados canónicos desde pipeline.canonical_resolvers y construye las celdas de tabla para Django.
"""
from pipeline.canonical_resolvers import (
    resolve_canonical_capital_flows,
    resolve_canonical_balance_sheet,
    resolve_canonical_income_statement,
    resolve_canonical_cash_flow,
    _extract_multi_source_val,
    _extract_multi_source_sum,
)


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
    # NUEVA ESTRUCTURA DE ESTADOS FINANCIEROS DINÁMICOS
    # -------------------------------------------------------------
    inc_det = fs.get("income_statement_detail", {})
    bs_det = fs.get("balance_sheet_detail", {})
    cf_det = fs.get("cash_flow_detail", {})
    statements_fys = [p for p in fs.get("fiscal_years", [])[:11]]

    def _num(dict_src, key, p):
        if not dict_src or not key:
            return None
        if key in dict_src:
            obj = dict_src[key]
            if isinstance(obj, dict):
                if "values" in obj:
                    return obj["values"].get(p)
                return obj.get(p)
        cand_keys = [f"us-gaap_{key}"] if not str(key).startswith("us-gaap_") else [str(key)[len("us-gaap_"):]]
        for ck in cand_keys:
            if ck in dict_src:
                obj = dict_src[ck]
                if isinstance(obj, dict):
                    if "values" in obj:
                        return obj["values"].get(p)
                    return obj.get(p)
        raw_key = str(key).split(":")[-1].split("_")[-1].lower()
        for k, obj in dict_src.items():
            k_tok = str(k).split(":")[-1].split("_")[-1].lower()
            if k_tok == raw_key:
                if isinstance(obj, dict):
                    if "values" in obj:
                        return obj["values"].get(p)
                    return obj.get(p)
        return None

    def _to_m(val):
        if val is None:
            return None
        v = float(val)
        return round(v / 1e6, 1)

    def _fmt_money(m_val):
        if m_val is None:
            return "-"
        if m_val == 0.0:
            return "$0.0M"
        prefix = "-$" if m_val < 0 else "$"
        return f"{prefix}{abs(m_val):,.1f}M"

    def _fmt_pct(pct_val):
        if pct_val is None:
            return "-"
        return f"{pct_val:.1f}%"

    def _fmt_shares(val):
        if val is None:
            return "-"
        v = float(val)
        scale = abs(v)
        if scale >= 1e6:
            return f"{scale/1e6:,.1f}M"
        return f"{scale:,.1f}"

    def _fmt_eps(val):
        if val is None:
            return "-"
        v = float(val)
        return f"-${abs(v):.2f}" if v < 0 else f"${v:.2f}"

    def _build_statement_cells(r, target_fys, canonical, ebt_dict=None, bs_tot_assets=None):
        if r.get("row_type") == "section_header":
            return {
                "label": r["label"],
                "orig_tooltip": r.get("orig_tooltip", ""),
                "clarification": r.get("clarification"),
                "operator": "",
                "row_type": "section_header",
                "indent": False,
                "is_bold": True,
                "values": ["" for _ in target_fys],
                "pcts": ["" for _ in target_fys],
                "yoy": ["" for _ in target_fys],
                "cagr_5y": "",
                "ltm_val": "",
                "ltm_pct": "",
                "ltm_yoy": "",
                "annual_cells": [{"abs": "", "pct": "", "yoy": ""} for _ in target_fys[1:]],
                "annual_vals": ["" for _ in target_fys[1:]],
                "latest_val": "",
                "latest_pct": ""
            }

        row_vals = []
        row_pcts = []
        row_yoys = []

        for i, p in enumerate(target_fys):
            val = r["data"].get(p)
            val_prior = r["data"].get(target_fys[i + 1]) if (i + 1 < len(target_fys)) else None

            # 1. abs_disp
            row_type = r.get("row_type", "item")
            if row_type == "shares":
                abs_disp = _fmt_shares(val)
            elif row_type in ("eps", "dps"):
                abs_disp = _fmt_eps(val)
            elif row_type == "metric_pct":
                abs_disp = f"{val:.1f}%" if val is not None else "-"
            elif row_type == "multiple":
                abs_disp = f"{val:.2f}x" if val is not None else "-"
            elif row_type in ("net_debt", "net_cash", "metric"):
                if val is not None:
                    abs_disp = f"-${abs(val):,.1f}M" if val < 0 else f"${val:,.1f}M"
                else:
                    abs_disp = "-"
            else:
                if r.get("negate_val") and val is not None:
                    if val < -0.01:
                        # Beneficio / Crédito fiscal (Tax benefit) que incrementa el beneficio neto
                        abs_disp = f"+${abs(val):,.1f}M"
                    elif val > 0.01:
                        abs_disp = f"-${val:,.1f}M"
                    else:
                        abs_disp = "$0.0M"
                else:
                    abs_disp = _fmt_money(val)

            row_vals.append(abs_disp)

            # 2. pct_disp (Vertical %)
            pct_mode = r.get("pct_mode")
            if row_type in ("shares", "eps", "dps", "multiple"):
                pct_disp = "-"
            elif row_type == "metric_pct":
                pct_disp = f"{val:.1f}%" if val is not None else "-"
            elif pct_mode == "rev":
                rev_val = _to_m(canonical.get("revenue", {}).get(p))
                if rev_val and rev_val != 0 and val is not None:
                    num = abs(val) if r.get("negate_val") else val
                    pct_disp = f"{(num / rev_val * 100.0):.1f}%"
                else:
                    pct_disp = "-"
            elif pct_mode == "ebt":
                ebt_val = ebt_dict.get(p) if ebt_dict else None
                if ebt_val and ebt_val != 0 and val is not None:
                    pct_disp = f"{(abs(val) / abs(ebt_val) * 100.0):.1f}%"
                else:
                    pct_disp = "-"
            elif pct_mode == "assets":
                tot_ast = bs_tot_assets.get(p) if bs_tot_assets else None
                if tot_ast and tot_ast != 0 and val is not None:
                    pct_disp = f"{(abs(val) / tot_ast * 100.0):.1f}%"
                else:
                    pct_disp = "-"
            elif pct_mode == "ni":
                ni_val = _to_m(canonical.get("net_income", {}).get(p))
                if ni_val and ni_val != 0 and val is not None:
                    pct_disp = f"{(val / ni_val * 100.0):.1f}%"
                else:
                    pct_disp = "-"
            else:
                pct_disp = "-"

            row_pcts.append(pct_disp)

            # 3. yoy_disp (% Variation vs Prior)
            if val is not None and val_prior is not None and abs(val_prior) > 0:
                diff = val - val_prior
                yoy_pct = (diff / abs(val_prior)) * 100.0
                if abs(yoy_pct) < 0.05:
                    yoy_disp = "0.0%"
                else:
                    yoy_disp = f"{yoy_pct:+.1f}%"
            else:
                yoy_disp = "-"

            row_yoys.append(yoy_disp)

        # 4. CAGR 5Y (Calculated across annual periods, excluding LTM)
        annual_periods = [p for p in target_fys if p != "LTM"]
        cagr_5y = "-"
        if len(annual_periods) >= 6:
            v_end = r["data"].get(annual_periods[0])
            v_start = r["data"].get(annual_periods[5])
            if v_end is not None and v_start is not None and v_start > 0 and v_end > 0:
                cagr = ((v_end / v_start) ** (1.0 / 5.0) - 1.0) * 100.0
                cagr_5y = f"{cagr:+.1f}%"

        annual_cells = [
            {"abs": row_vals[i], "pct": row_pcts[i], "yoy": row_yoys[i]}
            for i in range(1, len(target_fys))
        ]

        return {
            "label": r["label"],
            "orig_tooltip": r.get("orig_tooltip", ""),
            "clarification": r.get("clarification"),
            "operator": r.get("operator", ""),
            "row_type": r.get("row_type", "item"),
            "indent": r.get("indent", False),
            "is_bold": r.get("is_bold", False),
            "values": row_vals,
            "pcts": row_pcts,
            "yoy": row_yoys,
            "cagr_5y": cagr_5y,
            "ltm_val": row_vals[0] if row_vals else "-",
            "ltm_pct": row_pcts[0] if row_pcts else "-",
            "ltm_yoy": row_yoys[0] if row_yoys else "-",
            "annual_cells": annual_cells,
            "annual_vals": row_vals[1:] if len(row_vals) > 1 else [],
            "latest_val": row_vals[0] if row_vals else "-",
            "latest_pct": row_pcts[0] if row_pcts else "-"
        }

    # -------------------------------------------------------------
    # 1. ESTRUCTURACIÓN DE ESTADOS FINANCIEROS (DOBLE VISTA)
    #    Vista 1: Estandarizada (10Y + LTM)
    #    Vista 2: Oficial SEC As-Reported (3Y + LTM)
    # -------------------------------------------------------------
    as_reported = fs.get("as_reported_statements", {})
    as_rep_inc = as_reported.get("income_statement", [])
    as_rep_cf = as_reported.get("cash_flow_statement", []) or as_reported.get("cash_flow", [])
    as_rep_bs = as_reported.get("balance_sheet", [])

    as_rep_fys = [p for p in statements_fys[:4]]

    # Helper para formatear partidas As-Reported oficiales con metadatos bilingües
    def _format_as_reported_row(row_raw, target_fys, pct_mode=None):
        lbl = row_raw.get("spanish_label") or row_raw.get("label", "")
        orig_lbl = row_raw.get("label", "")
        conc = row_raw.get("concept", "")
        orig_tooltip = row_raw.get("orig_tooltip") or (f"{orig_lbl} ({conc})" if conc else orig_lbl)
        is_abs = row_raw.get("is_abstract", False) or row_raw.get("row_type") == "section_header"
        lvl = row_raw.get("level", 0)
        is_tot = row_raw.get("is_total", False)
        clarif = row_raw.get("clarification")
        vals = row_raw.get("values", {}) or row_raw.get("data", {})

        lbl_lower = orig_lbl.lower()
        conc_lower = conc.lower()

        if is_abs:
            return {
                "label": lbl,
                "orig_tooltip": orig_tooltip,
                "clarification": clarif,
                "operator": "",
                "row_type": "section_header",
                "indent": False,
                "is_bold": True,
                "data": {p: None for p in target_fys},
                "pct_mode": None
            }

        is_dollar_account = any(k in conc_lower for k in [
            "value", "capital", "equity", "proceeds", "payments", "accruals", "repurchase", "borrowings", "cash"
        ]) or any(k in lbl_lower for k in [
            "par value", "stated value", "additional paid", "common stock, $", "preferred stock, $"
        ])

        is_eps = not is_dollar_account and (
            "earningspershare" in conc_lower
            or conc_lower.endswith("earningspershare")
            or (("per share" in lbl_lower or "pershare" in conc_lower) and any(w in conc_lower or w in lbl_lower for w in ["basic", "diluted", "earnings", "loss", "dividend", "distribution"]))
        )
        is_shares = not is_dollar_account and not is_eps and (
            "weightedaveragenumberofshares" in conc_lower
            or "weightedaveragenumberofdilutedshares" in conc_lower
            or conc_lower in ("commonstocksharesoutstanding", "commonstocksharesissued", "sharesoutstanding", "preferredstocksharesoutstanding")
            or ("number of shares" in lbl_lower and "value" not in conc_lower)
            or ("shares outstanding" in lbl_lower and "value" not in conc_lower and "par value" not in lbl_lower)
        )

        data_m = {}
        for p in target_fys:
            v = vals.get(p)
            if v is None:
                data_m[p] = None
            elif is_eps or is_shares:
                data_m[p] = float(v)
            else:
                data_m[p] = _to_m(float(v))

        if is_eps:
            row_type = "eps"
            operator = ""
            bold = is_tot
            indent = (lvl > 2)
            p_mode = None
        elif is_shares:
            row_type = "shares"
            operator = ""
            bold = False
            indent = True
            p_mode = None
        elif is_tot:
            if conc_lower in ("netincomeloss", "profitloss", "operatingincomeloss", "assets") or any(w in lbl_lower for w in ["net income", "total assets", "operating income", "cash generated by operating activities", "flujo de caja operativo", "utilidad neta", "activos totales"]):
                row_type = "result"
            else:
                row_type = "subtotal"
            operator = "[=]"
            bold = True
            indent = (lvl > 2)
            p_mode = pct_mode
        else:
            row_type = "item"
            operator = ""
            bold = False
            indent = (lvl > 2)
            p_mode = pct_mode

        return {
            "label": lbl,
            "orig_tooltip": orig_tooltip,
            "clarification": clarif,
            "operator": operator,
            "row_type": row_type,
            "indent": indent,
            "is_bold": bold,
            "data": data_m,
            "pct_mode": p_mode
        }

    # Helper para Bloques Memo Adaptados por Arquetipo
    def _get_memo_rows(target_fys, stmt_type):
        rev_d = {p: _to_m(canonical.get("revenue", {}).get(p)) for p in target_fys}
        gp_d = {p: _to_m(canonical.get("gross_profit", {}).get(p)) for p in target_fys}
        ebit_d = {p: _to_m(canonical.get("operating_income", {}).get(p)) for p in target_fys}
        ni_d = {p: _to_m(canonical.get("net_income", {}).get(p)) for p in target_fys}
        fcf_d = {p: _to_m(canonical.get("free_cash_flow", {}).get(p)) for p in target_fys}

        memo = [
            {
                "label": "📊 MÉTRICAS ANALÍTICAS (MEMO)",
                "orig_tooltip": "Métricas normalizadas de rentabilidad y solvencia institucionales",
                "clarification": "Métricas adaptadas dinámicamente por arquetipo contable",
                "operator": "",
                "row_type": "section_header",
                "indent": False,
                "is_bold": True,
                "data": {p: None for p in target_fys},
                "pct_mode": None
            }
        ]

        if stmt_type == "pnl":
            if archetype == "FINANCIAL_BANKING":
                nim_d = {p: (key_ratios.get("nim_pct", {}).get(p) or key_ratios.get("risk_adj_nim_pct", {}).get(p) or (enriched.get("risk_adjusted_nim_pct") if p == "LTM" else None)) for p in target_fys}
                eff_d = {p: key_ratios.get("efficiency_ratio_pct", {}).get(p) for p in target_fys}
                roe_d = {p: key_ratios.get("roe_pct", {}).get(p) for p in target_fys}
                rotce_d = {}
                for p in target_fys:
                    r_val = key_ratios.get("rotce_pct", {}).get(p)
                    if r_val is None:
                        ni_comm = pnl_data.get("net_income_common", {}).get(p) or canonical.get("net_income_common", {}).get(p) or canonical.get("net_income", {}).get(p)
                        eq = bs_data.get("stockholders_equity", {}).get(p) or canonical.get("stockholders_equity", {}).get(p)
                        pref = _num(bs_det, "PreferredStockValue", p) or _num(bs_det, "us-gaap_PreferredStockIncludingAdditionalPaidInCapitalNetOfDiscount", p) or 0.0
                        gw_int = bs_data.get("goodwill_and_intangibles", {}).get(p) or 0.0
                        tce = (eq - pref - gw_int) if eq else 0.0
                        if tce > 0 and ni_comm is not None:
                            r_val = round(ni_comm / tce * 100.0, 1)
                        elif key_ratios.get("roe_pct", {}).get(p) is not None:
                            r_val = round(float(key_ratios.get("roe_pct", {}).get(p)), 1)
                    rotce_d[p] = r_val

                npl_cov_d = {}
                for p in target_fys:
                    cov_val = key_ratios.get("provision_coverage_pct", {}).get(p) or (enriched.get("provision_coverage_pct") if p == "LTM" else None)
                    if cov_val is None:
                        allowance = bs_data.get("allowance_for_loan_losses", {}).get(p) or _num(bs_det, "FinancingReceivableAllowanceForCreditLosses", p) or _num(bs_det, "us-gaap_FinancingReceivableAllowanceForCreditLossExcludingAccruedInterest", p)
                        clp = pnl_data.get("credit_loss_provision", {}).get(p) or canonical.get("credit_loss_provisions", {}).get(p)
                        if allowance and clp and clp != 0:
                            cov_val = round(abs(allowance) / abs(clp) * 100.0, 1)
                    npl_cov_d[p] = cov_val

                memo.extend([
                    {"label": "MARGEN NETO DE INTERÉS (NIM %)", "orig_tooltip": "Net Interest Margin (%)", "clarification": "Ingresos Netos por Intereses / Activos Rentables Promedio", "operator": "[%]", "row_type": "metric_pct", "indent": True, "is_bold": False, "data": nim_d, "pct_mode": None},
                    {"label": "RATIO DE EFICIENCIA (COST-TO-INCOME %)", "orig_tooltip": "Efficiency Ratio (%)", "clarification": "Gastos No Financieros / Ingresos Netos de Explotación", "operator": "[%]", "row_type": "metric_pct", "indent": True, "is_bold": False, "data": eff_d, "pct_mode": None},
                    {"label": "RENTABILIDAD SOBRE EQUITY (ROE %)", "orig_tooltip": "Return on Equity (%)", "clarification": "Beneficio Neto / Patrimonio Neto Promedio", "operator": "[%]", "row_type": "metric_pct", "indent": True, "is_bold": False, "data": roe_d, "pct_mode": None},
                    {"label": "RENTABILIDAD SOBRE EQUITY TANGIBLE (ROTCE %)", "orig_tooltip": "Return on Tangible Common Equity (%)", "clarification": "Beneficio Neto / Patrimonio Neto Tangible Promedio", "operator": "[%]", "row_type": "metric_pct", "indent": True, "is_bold": False, "data": rotce_d, "pct_mode": None},
                    {"label": "COBERTURA DE PROVISIONES (%)", "orig_tooltip": "Provision Coverage Ratio (%)", "clarification": "Fondo de Provisiones / Total Préstamos Dudosos (NPLs)", "operator": "[%]", "row_type": "metric_pct", "indent": True, "is_bold": False, "data": npl_cov_d, "pct_mode": None},
                ])
            elif archetype == "INSURANCE":
                comb_d = {p: key_ratios.get("combined_ratio_pct", {}).get(p) for p in target_fys}
                loss_d = {p: key_ratios.get("loss_ratio_pct", {}).get(p) for p in target_fys}
                exp_d = {p: key_ratios.get("expense_ratio_pct", {}).get(p) for p in target_fys}
                float_d = {p: _to_m(canonical.get("float_usd", {}).get(p)) for p in target_fys}
                inv_y_d = {}
                for p in target_fys:
                    y_val = key_ratios.get("investment_yield_pct", {}).get(p)
                    if y_val is None:
                        nii_v = canonical.get("net_investment_income", {}).get(p) or pnl_data.get("net_investment_income", {}).get(p)
                        tot_inv = canonical.get("total_investments", {}).get(p) or bs_data.get("short_term_investments", {}).get(p)
                        if nii_v and tot_inv and tot_inv > 0:
                            y_val = round(float(nii_v) / float(tot_inv) * 100.0, 1)
                    inv_y_d[p] = y_val

                memo.extend([
                    {"label": "RATIO COMBINADO (%)", "orig_tooltip": "Combined Ratio (%)", "clarification": "Suma de Siniestralidad y Gastos de Adquisición (<100% = beneficio técnico)", "operator": "[%]", "row_type": "metric_pct", "indent": False, "is_bold": True, "data": comb_d, "pct_mode": None},
                    {"label": "RATIO DE SINIESTRALIDAD (LOSS RATIO %)", "orig_tooltip": "Loss Ratio (%)", "clarification": "Costes de Siniestros Incurridos / Primas Devengadas", "operator": "[%]", "row_type": "metric_pct", "indent": True, "is_bold": False, "data": loss_d, "pct_mode": None},
                    {"label": "RATIO DE GASTOS DE SUSCRIPCIÓN (%)", "orig_tooltip": "Expense Ratio (%)", "clarification": "Gastos de Comercialización y Administración / Primas Devengadas", "operator": "[%]", "row_type": "metric_pct", "indent": True, "is_bold": False, "data": exp_d, "pct_mode": None},
                    {"label": "FLOAT ASEGURADOR DISPONIBLE", "orig_tooltip": "Insurance Float ($M)", "clarification": "Fondos de Prima Cobrados Pendientes de Liquidación", "operator": "[⚡]", "row_type": "metric", "indent": False, "is_bold": True, "data": float_d, "pct_mode": "rev"},
                    {"label": "RENDIMIENTO DE CARTERA INVERTIDA (%)", "orig_tooltip": "Investment Portfolio Yield (%)", "clarification": "Rendimiento Neto de Inversiones / Cartera Promedio", "operator": "[%]", "row_type": "metric_pct", "indent": True, "is_bold": False, "data": inv_y_d, "pct_mode": None},
                ])
            elif archetype == "REAL_ESTATE_REIT":
                noi_d = {p: _to_m(canonical.get("noi", {}).get(p)) for p in target_fys}
                ffo_d = {p: _to_m(canonical.get("ffo", {}).get(p)) for p in target_fys}
                affo_d = {p: _to_m(canonical.get("affo", {}).get(p)) for p in target_fys}
                ffo_sh_d = {p: (key_ratios.get("ffo_per_share", {}).get(p) or (round(float(canonical.get("ffo", {}).get(p)) / float(canonical.get("shares_diluted", {}).get(p)), 2) if (canonical.get("ffo", {}).get(p) and canonical.get("shares_diluted", {}).get(p)) else None)) for p in target_fys}
                affo_sh_d = {p: (key_ratios.get("affo_per_share", {}).get(p) or (round(float(canonical.get("affo", {}).get(p)) / float(canonical.get("shares_diluted", {}).get(p)), 2) if (canonical.get("affo", {}).get(p) and canonical.get("shares_diluted", {}).get(p)) else None)) for p in target_fys}
                payout_affo_d = {}
                for p in target_fys:
                    dp = abs(canonical.get("dividends_paid", {}).get(p) or _num(cf_det, "PaymentsOfDividendsCommonStock", p) or _num(cf_det, "PaymentsOfDividends", p) or 0.0)
                    af = float(canonical.get("affo", {}).get(p) or 0.0)
                    payout_affo_d[p] = round(dp / af * 100.0, 1) if (dp > 0 and af > 0) else None

                memo.extend([
                    {"label": "NET OPERATING INCOME (NOI)", "orig_tooltip": "Net Operating Income ($M)", "clarification": "Ingresos por Alquileres − Gastos Operativos de Inmuebles", "operator": "[⚡]", "row_type": "metric", "indent": False, "is_bold": True, "data": noi_d, "pct_mode": "rev"},
                    {"label": "MARGEN NOI (%)", "orig_tooltip": "NOI Margin (%)", "clarification": "NOI Inmobiliario / Ingresos por Rentas", "operator": "[%]", "row_type": "metric_pct", "indent": True, "is_bold": False, "data": {p: round(noi_d[p] / rev_d[p] * 100.0, 1) if (noi_d.get(p) is not None and rev_d.get(p) and rev_d[p] > 0) else None for p in target_fys}, "pct_mode": None},
                    {"label": "FUNDS FROM OPERATIONS (FFO)", "orig_tooltip": "Funds From Operations ($M)", "clarification": "Beneficio Neto + D&A Inmobiliaria − Ganancias por Venta", "operator": "[⚡]", "row_type": "metric", "indent": False, "is_bold": True, "data": ffo_d, "pct_mode": "rev"},
                    {"label": "MARGEN FFO (%)", "orig_tooltip": "FFO Margin (%)", "clarification": "FFO / Ingresos Totales por Rentas", "operator": "[%]", "row_type": "metric_pct", "indent": True, "is_bold": False, "data": {p: round(ffo_d[p] / rev_d[p] * 100.0, 1) if (ffo_d.get(p) is not None and rev_d.get(p) and rev_d[p] > 0) else None for p in target_fys}, "pct_mode": None},
                    {"label": "AFFO NORMALIZADO", "orig_tooltip": "Adjusted Funds From Operations ($M)", "clarification": "FFO − CapEx de Mantenimiento / Mejoras Inmobiliarias", "operator": "[⚡]", "row_type": "metric", "indent": False, "is_bold": True, "data": affo_d, "pct_mode": "rev"},
                    {"label": "PAYOUT RATIO S/ AFFO (%)", "orig_tooltip": "AFFO Payout Ratio (%)", "clarification": "Dividendos Totales Pagados / AFFO Generado (<90% sostenible)", "operator": "[%]", "row_type": "metric_pct", "indent": True, "is_bold": False, "data": payout_affo_d, "pct_mode": None},
                    {"label": "FFO POR ACCIÓN (FFO / SHARE $)", "orig_tooltip": "FFO Per Share ($/acción)", "clarification": "Funds From Operations / Acciones Diluidas", "operator": "[$]", "row_type": "eps", "indent": True, "is_bold": False, "data": ffo_sh_d, "pct_mode": None},
                    {"label": "AFFO POR ACCIÓN (AFFO / SHARE $)", "orig_tooltip": "AFFO Per Share ($/acción)", "clarification": "Adjusted Funds From Operations / Acciones Diluidas", "operator": "[$]", "row_type": "eps", "indent": True, "is_bold": False, "data": affo_sh_d, "pct_mode": None},
                ])
            else:
                def _find_dna_val(period):
                    v = _num(cf_det, "DepreciationAndAmortization", period) or _num(cf_det, "us-gaap_DepreciationAndAmortization", period) or _num(cf_det, "DepreciationDepletionAndAmortization", period) or _num(cf_det, "DepreciationAmortizationAndAccretionNet", period) or _num(cf_det, "Depreciation", period) or canonical.get("depreciation_and_amortization", {}).get(period)
                    if v is not None:
                        return _to_m(v)
                    for r_cf in (as_rep_cf or []):
                        conc_cf = str(r_cf.get("concept", "")).lower()
                        lbl_cf = str(r_cf.get("label", "")).lower()
                        if "depreciation" in conc_cf or "depreciation" in lbl_cf:
                            cf_v = r_cf.get("values", {}).get(period)
                            if cf_v is not None:
                                return _to_m(float(cf_v))
                    return None

                dna_dict = {p: _find_dna_val(p) for p in target_fys}
                ebitda_dict = {p: (round(ebit_d[p] + (dna_dict[p] or 0.0), 1) if ebit_d[p] is not None else None) for p in target_fys}
                ebitda_m_dict = {p: (round(ebitda_dict[p] / rev_d[p] * 100.0, 1) if (ebitda_dict.get(p) is not None and rev_d.get(p) and rev_d[p] > 0) else None) for p in target_fys}

                sbc_keys = [
                    "ShareBasedCompensation", "AllocatedShareBasedCompensationExpense",
                    "StockOptionPlanExpense", "AdjustmentsForSharebasedPayments",
                    "ExpenseFromSharebasedPaymentTransactionsWithEmployees",
                    "RestrictedStockExpense", "us-gaap_RestrictedStockExpense",
                    "ShareBasedCompensationArrangementByShareBasedPaymentAwardExpense",
                    "meli_StockBasedCompensation"
                ]
                sbc_dict = {}
                for p in target_fys:
                    sv = _extract_multi_source_val(fs, "cashflow", sbc_keys, p, "stock_based_compensation")
                    sbc_dict[p] = _to_m(sv) if sv is not None else None
                sbc_intensity_dict = {p: (round(sbc_dict[p] / rev_d[p] * 100.0, 1) if (sbc_dict.get(p) is not None and rev_d.get(p) and rev_d[p] > 0) else None) for p in target_fys}

                ebit_adj_sbc_dict = {p: (round(ebit_d[p] - (sbc_dict[p] or 0.0), 1) if ebit_d.get(p) is not None else None) for p in target_fys}
                ni_adj_sbc_dict = {p: (round(ni_d[p] - (sbc_dict[p] or 0.0), 1) if ni_d.get(p) is not None else None) for p in target_fys}
                ebit_adj_m_dict = {p: (round(ebit_adj_sbc_dict[p] / rev_d[p] * 100.0, 1) if (ebit_adj_sbc_dict.get(p) is not None and rev_d.get(p) and rev_d[p] > 0) else None) for p in target_fys}
                ni_adj_m_dict = {p: (round(ni_adj_sbc_dict[p] / rev_d[p] * 100.0, 1) if (ni_adj_sbc_dict.get(p) is not None and rev_d.get(p) and rev_d[p] > 0) else None) for p in target_fys}

                memo.extend([
                    {"label": "EBITDA NORMALIZADO", "orig_tooltip": "Normalized EBITDA ($M)", "clarification": "Beneficio Operativo (EBIT) + Depreciación y Amortización", "operator": "[⚡]", "row_type": "metric", "indent": False, "is_bold": True, "data": ebitda_dict, "pct_mode": "rev"},
                    {"label": "MARGEN EBITDA (%)", "orig_tooltip": "EBITDA Margin (%)", "clarification": "EBITDA Normalizado / Ingresos Totales", "operator": "[%]", "row_type": "metric_pct", "indent": True, "is_bold": False, "data": ebitda_m_dict, "pct_mode": None},
                    {"label": "MARGEN BRUTO (%)", "orig_tooltip": "Gross Margin (%)", "clarification": "Beneficio Bruto / Ingresos Totales", "operator": "[%]", "row_type": "metric_pct", "indent": True, "is_bold": False, "data": {p: round(gp_d[p] / rev_d[p] * 100.0, 1) if (gp_d.get(p) is not None and rev_d.get(p) and rev_d[p] > 0) else None for p in target_fys}, "pct_mode": None},
                    {"label": "MARGEN OPERATIVO (%)", "orig_tooltip": "Operating Margin EBIT (%)", "clarification": "Beneficio Operativo (EBIT) / Ingresos Totales", "operator": "[%]", "row_type": "metric_pct", "indent": True, "is_bold": False, "data": {p: round(ebit_d[p] / rev_d[p] * 100.0, 1) if (ebit_d.get(p) is not None and rev_d.get(p) and rev_d[p] > 0) else None for p in target_fys}, "pct_mode": None},
                    {"label": "MARGEN NETO (%)", "orig_tooltip": "Net Profit Margin (%)", "clarification": "Beneficio Neto / Ingresos Totales", "operator": "[%]", "row_type": "metric_pct", "indent": True, "is_bold": False, "data": {p: round(ni_d[p] / rev_d[p] * 100.0, 1) if (ni_d.get(p) is not None and rev_d.get(p) and rev_d[p] > 0) else None for p in target_fys}, "pct_mode": None},
                    {"label": "COMPENSACIÓN BASADA EN ACCIONES (SBC)", "orig_tooltip": "Stock-Based Compensation ($M)", "clarification": "Gasto no monetario por remuneración en acciones a empleados", "operator": "[⚡]", "row_type": "metric", "indent": False, "is_bold": False, "data": sbc_dict, "pct_mode": "rev"},
                    {"label": "BENEFICIO OPERATIVO ADJ. SBC (EBIT - SBC)", "orig_tooltip": "Operating Income adjusted for SBC ($M)", "clarification": "EBIT − Compensación Basada en Acciones", "operator": "[⚡]", "row_type": "metric", "indent": True, "is_bold": True, "data": ebit_adj_sbc_dict, "pct_mode": "rev"},
                    {"label": "BENEFICIO NETO ADJ. SBC (NET INCOME - SBC)", "orig_tooltip": "Net Income adjusted for SBC ($M)", "clarification": "Beneficio Neto − Compensación Basada en Acciones", "operator": "[⚡]", "row_type": "metric", "indent": True, "is_bold": True, "data": ni_adj_sbc_dict, "pct_mode": "rev"},
                    {"label": "INTENSIDAD DE SBC (% S/ VENTAS)", "orig_tooltip": "SBC Intensity (% of Revenue)", "clarification": "Compensación en Acciones (SBC) / Ingresos Totales", "operator": "[%]", "row_type": "metric_pct", "indent": True, "is_bold": False, "data": sbc_intensity_dict, "pct_mode": None},
                    {"label": "MARGEN EBIT ADJ. SBC (%)", "orig_tooltip": "EBIT Margin adjusted for SBC (%)", "clarification": "(EBIT − SBC) / Ingresos Totales", "operator": "[%]", "row_type": "metric_pct", "indent": True, "is_bold": False, "data": ebit_adj_m_dict, "pct_mode": None},
                    {"label": "MARGEN NETO ADJ. SBC (%)", "orig_tooltip": "Net Margin adjusted for SBC (%)", "clarification": "(Net Income − SBC) / Ingresos Totales", "operator": "[%]", "row_type": "metric_pct", "indent": True, "is_bold": False, "data": ni_adj_m_dict, "pct_mode": None},
                ])
        elif stmt_type == "cashflow":
            if archetype == "FINANCIAL_BANKING":
                dep_d = {p: _to_m(canonical.get("total_deposits", {}).get(p) or canonical.get("deposits", {}).get(p) or bs_data.get("deposits", {}).get(p) or _num(bs_det, "Deposits", p) or _num(bs_det, "ifrs-full_DepositsFromCustomers", p)) for p in target_fys}
                loans_d = {p: _to_m(canonical.get("net_loans", {}).get(p) or bs_data.get("net_loans", {}).get(p) or _num(bs_det, "LoansAndLeasesReceivableNetOfDeferredIncome", p) or _num(bs_det, "FinancingReceivableExcludingAccruedInterestBeforeAllowanceForCreditLossesNetOfDeferredIncome", p) or _num(bs_det, "ifrs-full_LoansAndAdvancesToCustomers", p)) for p in target_fys}
                ld_d = {p: (key_ratios.get("ldr_pct", {}).get(p) or (round(loans_d[p] / dep_d[p] * 100.0, 1) if (loans_d.get(p) and dep_d.get(p) and dep_d[p] > 0) else None)) for p in target_fys}
                memo.extend([
                    {"label": "DEPÓSITOS TOTALES DE CLIENTES", "orig_tooltip": "Total Customer Deposits ($M)", "clarification": "Fondeo comercial primario del balance bancario", "operator": "[⚡]", "row_type": "metric", "indent": False, "is_bold": True, "data": dep_d, "pct_mode": None},
                    {"label": "PRÉSTAMOS CONCEDIDOS NETOS", "orig_tooltip": "Net Loans & Leases ($M)", "clarification": "Cartera de crédito tras provisión por insolvencias", "operator": "[⚡]", "row_type": "metric", "indent": False, "is_bold": True, "data": loans_d, "pct_mode": None},
                    {"label": "RATIO PRÉSTAMOS / DEPÓSITOS (L/D %)", "orig_tooltip": "Loan-to-Deposit Ratio (%)", "clarification": "Cartera Crediticia Neta / Depósitos Totales", "operator": "[%]", "row_type": "metric_pct", "indent": True, "is_bold": False, "data": ld_d, "pct_mode": None},
                ])
            elif archetype == "INSURANCE":
                fcf_ins_d = {}
                for p in target_fys:
                    fc = canonical.get("free_cash_flow", {}).get(p) or cf_data.get("fcf", {}).get(p)
                    if fc is None:
                        cfo_v = canonical.get("cash_from_operations", {}).get(p) or cf_data.get("cfo", {}).get(p)
                        cx_v = canonical.get("capital_expenditures", {}).get(p) or cf_data.get("capex", {}).get(p)
                        if cfo_v is not None and cx_v is not None:
                            fc = float(cfo_v) - abs(float(cx_v))
                    fcf_ins_d[p] = _to_m(fc)
                memo.extend([
                    {"label": "FLUJO DE CAJA LIBRE (FCF)", "orig_tooltip": "Free Cash Flow ($M)", "clarification": "CFO − Inversiones en Inmovilizado", "operator": "[⚡]", "row_type": "metric", "indent": False, "is_bold": True, "data": fcf_ins_d, "pct_mode": "rev"},
                ])
            elif archetype == "REAL_ESTATE_REIT":
                ffo_d = {p: _to_m(canonical.get("ffo", {}).get(p)) for p in target_fys}
                payout_affo_d = {}
                for p in target_fys:
                    div_p = canonical.get("dividends_paid", {}).get(p) or cf_data.get("dividends_paid", {}).get(p)
                    affo_p = canonical.get("affo", {}).get(p)
                    if div_p is not None and affo_p and float(affo_p) > 0:
                        payout_affo_d[p] = round(abs(float(div_p)) / float(affo_p) * 100.0, 1)
                    else:
                        payout_affo_d[p] = None
                memo.extend([
                    {"label": "FONDOS DE OPERACIONES (FFO)", "orig_tooltip": "FFO Cash Flow ($M)", "clarification": "Generación de caja operativa REIT antes de CapEx", "operator": "[⚡]", "row_type": "metric", "indent": False, "is_bold": True, "data": ffo_d, "pct_mode": "rev"},
                    {"label": "FLUJO DE CAJA LIBRE (FCF TRAS CAPEX)", "orig_tooltip": "Free Cash Flow ($M)", "clarification": "CFO − CapEx en Mejoras Inmobiliarias", "operator": "[⚡]", "row_type": "metric", "indent": False, "is_bold": True, "data": fcf_d, "pct_mode": "rev"},
                    {"label": "RATIO PAYOUT S/ AFFO (%)", "orig_tooltip": "AFFO Dividend Payout Ratio (%)", "clarification": "Dividendos Pagados en Efectivo / AFFO Generado", "operator": "[%]", "row_type": "metric_pct", "indent": True, "is_bold": False, "data": payout_affo_d, "pct_mode": None},
                ])
            else:
                sbc_keys = [
                    "ShareBasedCompensation", "AllocatedShareBasedCompensationExpense",
                    "StockOptionPlanExpense", "AdjustmentsForSharebasedPayments",
                    "ExpenseFromSharebasedPaymentTransactionsWithEmployees",
                    "RestrictedStockExpense", "us-gaap_RestrictedStockExpense",
                    "ShareBasedCompensationArrangementByShareBasedPaymentAwardExpense",
                    "meli_StockBasedCompensation"
                ]
                sbc_dict = {}
                for p in target_fys:
                    sv = _extract_multi_source_val(fs, "cashflow", sbc_keys, p, "stock_based_compensation")
                    sbc_dict[p] = _to_m(sv) if sv is not None else None

                fcf_adj_sbc_dict = {p: (round(fcf_d[p] - (sbc_dict[p] or 0.0), 1) if fcf_d.get(p) is not None else None) for p in target_fys}
                owner_fcf_m_dict = {p: (round(fcf_adj_sbc_dict[p] / rev_d[p] * 100.0, 1) if (fcf_adj_sbc_dict.get(p) is not None and rev_d.get(p) and rev_d[p] > 0) else None) for p in target_fys}
                
                capex_d = {p: _to_m(canonical.get("capital_expenditures", {}).get(p) or cf_data.get("capex", {}).get(p)) for p in target_fys}
                capex_intensity_dict = {p: (round(abs(capex_d[p]) / rev_d[p] * 100.0, 1) if (capex_d.get(p) is not None and rev_d.get(p) and rev_d[p] > 0) else None) for p in target_fys}

                # Precision 2: Lectura de cap_flows como diccionario y conversion via _to_m
                sh_ret_d = {}
                for p in target_fys:
                    bb_m = _to_m(cap_flows.get("share_repurchases_open_market", {}).get(p))
                    dv_m = _to_m(cap_flows.get("dividends_paid", {}).get(p))
                    if bb_m is not None or dv_m is not None:
                        sh_ret_d[p] = round((bb_m or 0.0) + (dv_m or 0.0), 1)
                    else:
                        sh_ret_d[p] = None

                div_cash_ret_d = {}
                bb_cash_ret_d = {}
                alloc_ratio_d = {}
                for p in target_fys:
                    ret_val = sh_ret_d.get(p)
                    dv_m = abs(_to_m(cap_flows.get("dividends_paid", {}).get(p)) or 0.0)
                    bb_m = abs(_to_m(cap_flows.get("share_repurchases_open_market", {}).get(p)) or 0.0)
                    cx_m = abs(capex_d.get(p) or 0.0)
                    if ret_val and ret_val > 0:
                        div_cash_ret_d[p] = round(dv_m / ret_val * 100.0, 1)
                        bb_cash_ret_d[p] = round(bb_m / ret_val * 100.0, 1)
                        alloc_ratio_d[p] = round(cx_m / ret_val, 2)
                    else:
                        div_cash_ret_d[p] = None
                        bb_cash_ret_d[p] = None
                        alloc_ratio_d[p] = None

                memo.extend([
                    {"label": "FLUJO DE CAJA LIBRE (FCF)", "orig_tooltip": "Free Cash Flow ($M)", "clarification": "Flujo de Caja Operativo (CFO) − Inversiones CapEx", "operator": "[⚡]", "row_type": "metric", "indent": False, "is_bold": True, "data": fcf_d, "pct_mode": "rev"},
                    {"label": "FCF AJUSTADO POR SBC (OWNER FCF)", "orig_tooltip": "SBC-Adjusted Free Cash Flow ($M)", "clarification": "FCF − Compensación Basada en Acciones (SBC)", "operator": "[⚡]", "row_type": "metric", "indent": False, "is_bold": True, "data": fcf_adj_sbc_dict, "pct_mode": "rev"},
                    {"label": "MARGEN FCF (%)", "orig_tooltip": "FCF Margin (%)", "clarification": "FCF / Ingresos Totales", "operator": "[%]", "row_type": "metric_pct", "indent": True, "is_bold": False, "data": {p: round(fcf_d[p] / rev_d[p] * 100.0, 1) if (fcf_d.get(p) is not None and rev_d.get(p) and rev_d[p] > 0) else None for p in target_fys}, "pct_mode": None},
                    {"label": "MARGEN OWNER FCF (%)", "orig_tooltip": "Owner FCF Margin (% of Revenue)", "clarification": "FCF Ajustado por SBC / Ingresos Totales", "operator": "[%]", "row_type": "metric_pct", "indent": True, "is_bold": False, "data": owner_fcf_m_dict, "pct_mode": None},
                    {"label": "CONVERSIÓN FCF (%)", "orig_tooltip": "FCF Conversion Ratio (%)", "clarification": "FCF / Beneficio Neto", "operator": "[%]", "row_type": "metric_pct", "indent": True, "is_bold": False, "data": {p: round(fcf_d[p] / ni_d[p] * 100.0, 1) if (fcf_d.get(p) is not None and ni_d.get(p) and ni_d[p] > 0) else None for p in target_fys}, "pct_mode": None},
                    {"label": "INTENSIDAD CAPEX (% S/ VENTAS)", "orig_tooltip": "CapEx Intensity (% of Revenue)", "clarification": "Inversiones CapEx / Ingresos Totales", "operator": "[%]", "row_type": "metric_pct", "indent": True, "is_bold": False, "data": capex_intensity_dict, "pct_mode": None},
                    {"label": "RETORNO TOTAL EN EFECTIVO AL ACCIONISTA", "orig_tooltip": "Total Cash Returned to Shareholders ($M)", "clarification": "Recompras de Acciones en Mercado Abierto + Dividendos en Efectivo", "operator": "[⚡]", "row_type": "metric", "indent": False, "is_bold": True, "data": sh_ret_d, "pct_mode": "rev"},
                    {"label": "DIVIDENDOS PAGADOS (% CASH RET.)", "orig_tooltip": "Dividends (% of Cash Returned)", "clarification": "Dividendos en Efectivo / Retorno Total en Efectivo", "operator": "[%]", "row_type": "metric_pct", "indent": True, "is_bold": False, "data": div_cash_ret_d, "pct_mode": None},
                    {"label": "RECOMPRA DE ACCIONES (% CASH RET.)", "orig_tooltip": "Share Repurchases (% of Cash Returned)", "clarification": "Recompras de Acciones / Retorno Total en Efectivo", "operator": "[%]", "row_type": "metric_pct", "indent": True, "is_bold": False, "data": bb_cash_ret_d, "pct_mode": None},
                    {"label": "RATIO DE ASIGNACIÓN (REINVERSIÓN VS RETORNO)", "orig_tooltip": "Capital Allocation Ratio (CapEx / Shareholder Return)", "clarification": "CapEx / Retorno Total en Efectivo al Accionista (>1.0x = reinversión expansiva)", "operator": "[x]", "row_type": "multiple", "indent": True, "is_bold": False, "data": alloc_ratio_d, "pct_mode": None},
                ])
        elif stmt_type == "balancesheet":
            if archetype == "FINANCIAL_BANKING":
                cet1_d = {}
                for p in target_fys:
                    c_val = key_ratios.get("cet1_ratio_pct", {}).get(p) or (enriched.get("cet1_ratio_pct") if p == "LTM" else None)
                    if c_val is None:
                        eq = bs_data.get("stockholders_equity", {}).get(p) or canonical.get("stockholders_equity", {}).get(p)
                        pref = _num(bs_det, "PreferredStockValue", p) or _num(bs_det, "us-gaap_PreferredStockIncludingAdditionalPaidInCapitalNetOfDiscount", p) or 0.0
                        gw_int = bs_data.get("goodwill_and_intangibles", {}).get(p) or 0.0
                        tot_ast = bs_data.get("total_assets", {}).get(p) or canonical.get("total_assets", {}).get(p)
                        tce = (eq - pref - gw_int) if eq else 0.0
                        if tce > 0 and tot_ast and tot_ast > 0:
                            c_val = round(tce / tot_ast * 100.0, 1)
                        elif eq and tot_ast and tot_ast > 0:
                            c_val = round(eq / tot_ast * 100.0, 1)
                    cet1_d[p] = c_val

                npl_d = {}
                for p in target_fys:
                    n_val = key_ratios.get("npl_ratio_pct", {}).get(p) or (enriched.get("npl_90_plus_pct") if p == "LTM" else None)
                    if n_val is None:
                        n_val = key_ratios.get("cost_of_risk_loans_pct", {}).get(p)
                    npl_d[p] = n_val

                liq_d = {p: _to_m(bs_data.get("total_liquid_cash", {}).get(p)) for p in target_fys}
                memo.extend([
                    {"label": "RATIO DE CAPITAL BANCARIO CET1 (%)", "orig_tooltip": "Common Equity Tier 1 Ratio (%)", "clarification": "Capital Principal Nivel 1 / Activos Ponderados por Riesgo", "operator": "[%]", "row_type": "metric_pct", "indent": False, "is_bold": True, "data": cet1_d, "pct_mode": None},
                    {"label": "RATIO DE MOROSIDAD (NPL %)", "orig_tooltip": "Non-Performing Loans Ratio (%)", "clarification": "Créditos Dudosos / Total Cartera Crediticia Bruta", "operator": "[%]", "row_type": "metric_pct", "indent": True, "is_bold": False, "data": npl_d, "pct_mode": None},
                    {"label": "LIQUIDEZ REGULATORIA INMEDIATA", "orig_tooltip": "Regulatory Liquid Cash ($M)", "clarification": "Efectivo en Bancos Centrales + Inversiones Líquidas Negociables", "operator": "[⚡]", "row_type": "metric", "indent": False, "is_bold": True, "data": liq_d, "pct_mode": "assets"},
                ])
            elif archetype == "INSURANCE":
                inv_tot_d = {p: _to_m(canonical.get("total_investments", {}).get(p) or bs_data.get("short_term_investments", {}).get(p)) for p in target_fys}
                eq_d = {p: _to_m(canonical.get("stockholders_equity", {}).get(p) or bs_data.get("stockholders_equity", {}).get(p)) for p in target_fys}
                memo.extend([
                    {"label": "CARTERA TOTAL DE INVERSIONES", "orig_tooltip": "Total Investment Portfolio ($M)", "clarification": "Activos Financieros en Renta Fija y Renta Variable", "operator": "[⚡]", "row_type": "metric", "indent": False, "is_bold": True, "data": inv_tot_d, "pct_mode": "assets"},
                    {"label": "SOLVENCIA PATRIMONIAL (EQUITY)", "orig_tooltip": "Stockholders Equity ($M)", "clarification": "Patrimonio Neto de los Accionistas", "operator": "[⚡]", "row_type": "metric", "indent": False, "is_bold": True, "data": eq_d, "pct_mode": "assets"},
                ])
            elif archetype == "REAL_ESTATE_REIT":
                ppe_d = {p: _to_m(bs_data.get("net_ppe", {}).get(p)) for p in target_fys}
                debt_d = {p: _to_m(bs_data.get("total_debt", {}).get(p)) for p in target_fys}
                ast_d = {p: _to_m(bs_data.get("total_assets", {}).get(p)) for p in target_fys}
                ltv_d = {p: round(debt_d[p] / ast_d[p] * 100.0, 1) if (debt_d.get(p) and ast_d.get(p) and ast_d[p] > 0) else None for p in target_fys}
                memo.extend([
                    {"label": "INVERSIONES INMOBILIARIAS NETAS (PP&E)", "orig_tooltip": "Net Real Estate Portfolio ($M)", "clarification": "Cartera de Inmuebles en Explotación neta de depreciación", "operator": "[⚡]", "row_type": "metric", "indent": False, "is_bold": True, "data": ppe_d, "pct_mode": "assets"},
                    {"label": "DEUDA FINANCIERA INMOBILIARIA TOTAL", "orig_tooltip": "Total Real Estate Debt ($M)", "clarification": "Deuda Hipotecaria + Préstamos a Plazo + Bonos", "operator": "[⚡]", "row_type": "metric", "indent": False, "is_bold": True, "data": debt_d, "pct_mode": "assets"},
                    {"label": "RATIO LTV (DEUDA / ACTIVOS %)", "orig_tooltip": "Loan-to-Value Ratio (%)", "clarification": "Deuda Total / Activos Inmobiliarios Totales", "operator": "[%]", "row_type": "metric_pct", "indent": True, "is_bold": False, "data": ltv_d, "pct_mode": None},
                ])
            else:
                st_debt_dict = {p: _to_m(bs_data.get("short_term_debt", {}).get(p)) for p in target_fys}
                lt_debt_dict = {p: _to_m(bs_data.get("long_term_debt", {}).get(p)) for p in target_fys}
                tot_debt_dict = {p: (round((st_debt_dict.get(p) or 0.0) + (lt_debt_dict.get(p) or 0.0), 1) if (st_debt_dict.get(p) is not None or lt_debt_dict.get(p) is not None) else None) for p in target_fys}
                memo.extend([
                    {"label": "LIQUIDEZ INMEDIATA TOTAL", "orig_tooltip": "Total Liquid Cash ($M)", "clarification": "Efectivo y Equivalentes + Inversiones Negociables CP", "operator": "[⚡]", "row_type": "metric", "indent": False, "is_bold": True, "data": {p: _to_m(bs_data.get("total_liquid_cash", {}).get(p)) for p in target_fys}, "pct_mode": "assets"},
                    {"label": "DEUDA FINANCIERA TOTAL", "orig_tooltip": "Total Financial Debt ($M)", "clarification": "Deuda Financiera CP + LP (excluyendo pasivos operativos)", "operator": "[⚡]", "row_type": "metric", "indent": False, "is_bold": True, "data": tot_debt_dict, "pct_mode": "assets"},
                    {"label": "POSICIÓN FINANCIERA NETA (DEUDA NETA)", "orig_tooltip": "Net Financial Position ($M)", "clarification": "Deuda Total − Liquidez Inmediata Total", "operator": "[⚡]", "row_type": "net_debt", "indent": False, "is_bold": True, "data": {p: _to_m(bs_data.get("net_financial_position", {}).get(p)) for p in target_fys}, "pct_mode": "assets"},
                    {"label": "FONDO DE MANIOBRA (NET WORKING CAPITAL)", "orig_tooltip": "Net Working Capital ($M)", "clarification": "Activo Corriente − Pasivo Corriente", "operator": "[⚡]", "row_type": "metric", "indent": False, "is_bold": True, "data": {p: _to_m(bs_data.get("net_working_capital", {}).get(p)) for p in target_fys}, "pct_mode": "assets"},
                ])

            memo.extend([
                {"label": "VALOR CONTABLE POR ACCIÓN (BVPS $)", "orig_tooltip": "Book Value Per Share ($/acción)", "clarification": "Patrimonio Neto / Acciones Diluidas", "operator": "[⚡]", "row_type": "eps", "indent": False, "is_bold": True, "data": {p: bs_data.get("book_value_per_share", {}).get(p) for p in target_fys}, "pct_mode": None},
                {"label": "VALOR CONTABLE TANGIBLE POR ACCIÓN (TBVPS $)", "orig_tooltip": "Tangible Book Value Per Share ($/acción)", "clarification": "(Patrimonio Neto − Fondo de Comercio e Intangibles) / Acciones Diluidas", "operator": "[⚡]", "row_type": "eps", "indent": True, "is_bold": False, "data": {p: bs_data.get("tangible_book_value_per_share", {}).get(p) for p in target_fys}, "pct_mode": None},
            ])
        return memo

    # Diccionarios de referencia para % vertical As-Reported y EBT
    ebt_dict_std = {p: _to_m(pnl_data["ebt"].get(p)) for p in statements_fys}
    ebt_dict_asrep = {p: ebt_dict_std.get(p) for p in as_rep_fys}
    bs_tot_assets_std = {p: _to_m(bs_data.get("total_assets", {}).get(p)) for p in statements_fys}
    bs_tot_assets_asrep = {p: bs_tot_assets_std.get(p) for p in as_rep_fys}

    def _should_include_row(row_def, data_dict):
        # row_def: (label, key, operator, row_type, indent, is_bold, negate_val, always_show, pct_mode, tooltip)
        if row_def[7]:  # always_show
            return True
        for p in statements_fys:
            v = data_dict.get(p)
            if v is not None:
                try:
                    if abs(float(v)) > 1e-6:
                        return True
                except (ValueError, TypeError):
                    pass
        return False

    def _build_standardized_section(sections_def, source_data, default_pct_mode=None):
        out_rows = []
        for sec_title, items in sections_def:
            sec_visible_items = []
            for item in items:
                lbl, k, op, r_type, ind, bold, neg, alw, p_mode, tip = item
                is_unit = r_type in ("shares", "eps", "dps")
                if is_unit:
                    val_dict = {p: source_data.get(k, {}).get(p) for p in statements_fys}
                else:
                    val_dict = {p: _to_m(source_data.get(k, {}).get(p)) for p in statements_fys}

                if k in ("preferred_dividends", "minority_interest_pnl"):
                    if any(v is not None and abs(float(v or 0)) > 1e-6 for v in val_dict.values()):
                        val_dict = {p: (val_dict[p] if val_dict.get(p) is not None else 0.0) for p in statements_fys}

                if _should_include_row(item, val_dict):
                    eff_tooltip = tip or f"Estándar Canónico: {k}"
                    if k == "sga_expense":
                        canon_rd = canonical.get("rd_expense", {}) if isinstance(canonical, dict) else {}
                        if any(v is not None for v in canon_rd.values()) and not any(v is not None for v in source_data.get("rd_expense", {}).values()):
                            eff_tooltip = f"{eff_tooltip}. En empresas que integran I+D/diseño en gastos generales (ej. calzado y retail), incluye la inversión reportada en notas del 10-K."

                    sec_visible_items.append({
                        "label": lbl,
                        "orig_tooltip": eff_tooltip,
                        "clarification": None,
                        "operator": op,
                        "row_type": r_type,
                        "indent": ind,
                        "is_bold": bold,
                        "negate_val": neg,
                        "data": val_dict,
                        "pct_mode": p_mode or default_pct_mode
                    })
            if sec_visible_items:
                if sec_title:
                    out_rows.append({
                        "label": sec_title,
                        "orig_tooltip": f"Sección Canónica: {sec_title}",
                        "clarification": None,
                        "operator": "",
                        "row_type": "section_header",
                        "indent": False,
                        "is_bold": True,
                        "negate_val": False,
                        "data": {p: None for p in statements_fys},
                        "pct_mode": None
                    })
                out_rows.extend(sec_visible_items)
        return out_rows

    # =============================================================
    # 1.A. CONSTRUCCIÓN DE VISTA ESTANDARIZADA (10Y + LTM)
    # =============================================================
    # 1. ESTADO DE RESULTADOS (INCOME STATEMENT)
    if archetype == "FINANCIAL_BANKING":
        pnl_sections = [
            ("MARGEN DE INTERESES E INGRESOS BANCARIOS", [
                ("Ingresos por Intereses (Interest Income)", "interest_income", "[+]", "item", True, False, False, True, "rev", "Interest Income"),
                ("Gastos por Intereses (Interest Expense)", "interest_expense", "[-]", "item", True, False, True, True, "rev", "Interest Expense"),
                ("Margen Neto de Intereses (Net Interest Income — NII)", "net_interest_income", "[=]", "subtotal", False, True, False, True, "rev", "Net Interest Income"),
                ("Ingresos por Comisiones y Servicios (Non-Interest Income)", "non_interest_income", "[+]", "item", True, False, False, True, "rev", "Non-Interest Income"),
                ("Ingresos Totales Netos de Explotación (Total Net Revenue)", "revenue", "[=]", "subtotal", False, True, False, True, "rev", "Total Net Revenue"),
            ]),
            ("PROVISIONES CREDITICIAS, GASTOS OPERATIVOS Y BENEFICIO NETO", [
                ("Provisión para Pérdidas Crediticias (Provision for Credit Losses)", "credit_loss_provision", "[-]", "item", True, False, True, True, "rev", "Provision for Credit Losses"),
                ("Costes y Gastos Transaccionales (Transactional Expenses)", "transactional_expenses", "[-]", "item", True, False, True, False, "rev", "Transactional Expenses"),
                ("Gastos Operativos No Financieros (Non-Interest Expense)", "non_interest_expense", "[-]", "item", True, False, True, True, "rev", "Non-Interest Expense"),
                ("Participación en Resultados de Asociadas y Otros", "share_of_associates", "[±]", "item", True, False, False, False, "rev", "Share of Associates & Other"),
                ("Beneficio Antes de Impuestos (Pre-Tax Income / EBT)", "ebt", "[=]", "subtotal", False, True, False, True, "rev", "Pre-Tax Income"),
                ("Impuesto sobre Beneficios (Income Tax)", "income_tax", "[-]", "item", True, False, True, True, "ebt", "Income Tax Expense"),
                ("Beneficio Neto Consolidado (Net Income)", "net_income", "[=]", "result", False, True, False, True, "rev", "Net Income"),
                ("Beneficio Atribuible a Intereses Minoritarios", "minority_interest_pnl", "[-]", "item", True, False, True, False, "rev", "Noncontrolling Interest"),
                ("Dividendos de Acciones Preferentes", "preferred_dividends", "[-]", "item", True, False, True, False, "rev", "Preferred Dividends"),
                ("Beneficio Neto Atribuible a Accionistas Ordinarios", "net_income_common", "[=]", "subtotal", False, True, False, False, "rev", "Net Income Available to Common"),
            ]),
            ("MÉTRICAS POR ACCIÓN Y ACCIONES EN CIRCULACIÓN", [
                ("BPA Básico (Basic EPS)", "eps_basic", "", "eps", False, False, False, True, None, "Basic EPS"),
                ("BPA Diluido Normalizado (Diluted EPS)", "eps_diluted", "", "eps", False, True, False, True, None, "Diluted EPS"),
                ("Acciones Básicas Promedio Ponderado (M)", "shares_basic", "", "shares", True, False, False, True, None, "Weighted Average Shares Basic"),
                ("Acciones Diluidas Promedio Ponderado (M)", "shares_diluted", "", "shares", True, True, False, True, None, "Weighted Average Shares Diluted"),
                ("Dividendos por Acción (DPS)", "dps", "", "dps", True, False, False, False, None, "Dividends Per Share"),
            ])
        ]
    elif archetype == "INSURANCE":
        pnl_sections = [
            ("INGRESOS DE SUSCRIPCIÓN E INVERSIONES", [
                ("Primas Netas Devengadas (Net Premiums Earned)", "net_premiums_earned", "[+]", "item", True, False, False, True, "rev", "Net Premiums Earned"),
                ("Ingresos Netos por Inversiones (Net Investment Income)", "net_investment_income", "[+]", "item", True, False, False, True, "rev", "Net Investment Income"),
                ("Ganancias / (Pérdidas) Realizadas y No Realizadas en Cartera", "investment_gains_losses", "[±]", "item", True, False, False, False, "rev", "Investment Gains / Losses"),
                ("Comisiones y Otros Ingresos de Servicios", "fees_and_other_revenues", "[+]", "item", True, False, False, False, "rev", "Service and Fee Revenues"),
                ("Ingresos Totales de Seguros (Total Revenues)", "revenue", "[=]", "subtotal", False, True, False, True, "rev", "Total Revenues"),
            ]),
            ("SINIESTRALIDAD, GASTOS DE SUSCRIPCIÓN Y BENEFICIO NETO", [
                ("Siniestros y Gastos de Liquidación (Losses & LAE)", "losses_and_lae", "[-]", "item", True, False, True, True, "rev", "Losses and Loss Adjustment Expenses"),
                ("Amortización de Costes de Adquisición de Pólizas (DAC)", "dac_amortization", "[-]", "item", True, False, True, False, "rev", "Policy Acquisition Cost Amortization"),
                ("Otros Gastos de Suscripción y Operativos", "other_underwriting_expenses", "[-]", "item", True, False, True, False, "rev", "Other Underwriting Expenses"),
                ("Total Siniestros y Gastos Operativos (Total Benefits & Expenses)", "total_benefits_and_expenses", "[=]", "subtotal", False, True, True, True, "rev", "Total Benefits and Expenses"),
                ("Beneficio Antes de Impuestos (EBT)", "ebt", "[=]", "subtotal", False, True, False, True, "rev", "Pre-Tax Income"),
                ("Impuesto sobre Beneficios (Income Tax)", "income_tax", "[-]", "item", True, False, True, True, "ebt", "Income Tax Expense"),
                ("Participación en Resultados de Asociadas y Otros", "share_of_associates", "[±]", "item", True, False, False, False, "rev", "Share of Associates"),
                ("Beneficio Neto Consolidado (Net Income)", "net_income", "[=]", "result", False, True, False, True, "rev", "Net Income"),
                ("Beneficio Atribuible a Intereses Minoritarios", "minority_interest_pnl", "[-]", "item", True, False, True, False, "rev", "Noncontrolling Interest"),
                ("Dividendos de Acciones Preferentes", "preferred_dividends", "[-]", "item", True, False, True, False, "rev", "Preferred Dividends"),
                ("Beneficio Neto Atribuible a Accionistas Ordinarios", "net_income_common", "[=]", "subtotal", False, True, False, False, "rev", "Net Income Available to Common"),
            ]),
            ("MÉTRICAS POR ACCIÓN Y ACCIONES EN CIRCULACIÓN", [
                ("BPA Básico (Basic EPS)", "eps_basic", "", "eps", False, False, False, True, None, "Basic EPS"),
                ("BPA Diluido Normalizado (Diluted EPS)", "eps_diluted", "", "eps", False, True, False, True, None, "Diluted EPS"),
                ("Acciones Básicas Promedio Ponderado (M)", "shares_basic", "", "shares", True, False, False, True, None, "Weighted Average Shares Basic"),
                ("Acciones Diluidas Promedio Ponderado (M)", "shares_diluted", "", "shares", True, True, False, True, None, "Weighted Average Shares Diluted"),
                ("Dividendos por Acción (DPS)", "dps", "", "dps", True, False, False, False, None, "Dividends Per Share"),
            ])
        ]
    elif archetype == "REAL_ESTATE_REIT":
        pnl_sections = [
            ("INGRESOS INMOBILIARIOS Y NOI", [
                ("Ingresos por Alquileres y Arrendamientos (Rental Revenue)", "rental_revenue", "[+]", "item", True, False, False, True, "rev", "Rental Revenue"),
                ("Reembolsos de Inquilinos y Otros Ingresos Inmobiliarios", "tenant_reimbursements_other", "[+]", "item", True, False, False, False, "rev", "Tenant Reimbursements & Other"),
                ("Ingresos Inmobiliarios Totales (Total Revenue)", "revenue", "[=]", "subtotal", False, True, False, True, "rev", "Total Revenue"),
                ("Gastos Operativos de Propiedades (Property Operating Expenses)", "property_operating_expenses", "[-]", "item", True, False, True, True, "rev", "Property Operating Expenses"),
                ("Net Operating Income Inmobiliario (NOI)", "noi", "[=]", "subtotal", False, True, False, True, "rev", "Net Operating Income"),
            ]),
            ("GASTOS CORPORATIVOS, NO OPERATIVOS Y BENEFICIO NETO", [
                ("Depreciación y Amortización Inmobiliaria (D&A)", "reit_da", "[-]", "item", True, False, True, True, "rev", "Depreciation and Amortization"),
                ("Gastos Generales y Administrativos (G&A)", "reit_ga", "[-]", "item", True, False, True, True, "rev", "General & Administrative"),
                ("Deterioro de Activos Inmobiliarios (Impairment Charges)", "reit_impairment", "[-]", "item", True, False, True, False, "rev", "Real Estate Impairment"),
                ("Beneficio Operativo Inmobiliario (EBIT)", "operating_income", "[=]", "result", False, True, False, True, "rev", "Operating Income"),
                ("Gastos por Intereses Financieros", "interest_expense", "[-]", "item", True, False, True, True, "rev", "Interest Expense"),
                ("Ganancia en Venta de Propiedades Inmobiliarias", "gain_on_sale_properties", "[+]", "item", True, False, False, False, "rev", "Gain on Sale of Properties"),
                ("Otros Ingresos / (Gastos) No Operativos y Fusiones", "other_non_operating", "[±]", "item", True, False, False, False, "rev", "Other Non-Operating"),
                ("Beneficio Antes de Impuestos (EBT)", "ebt", "[=]", "subtotal", False, True, False, True, "rev", "Pre-Tax Income"),
                ("Impuesto sobre Beneficios (Income Tax)", "income_tax", "[-]", "item", True, False, True, True, "ebt", "Income Tax Expense"),
                ("Participación en Resultados de Asociadas y Otros", "share_of_associates", "[±]", "item", True, False, False, False, "rev", "Share of Associates"),
                ("Beneficio Neto Consolidado (Net Income)", "net_income", "[=]", "result", False, True, False, True, "rev", "Net Income"),
                ("Beneficio Atribuible a Intereses Minoritarios", "minority_interest_pnl", "[-]", "item", True, False, True, False, "rev", "Noncontrolling Interest"),
                ("Dividendos de Acciones Preferentes", "preferred_dividends", "[-]", "item", True, False, True, False, "rev", "Preferred Dividends"),
                ("Beneficio Neto Atribuible a Accionistas Ordinarios", "net_income_common", "[=]", "subtotal", False, True, False, False, "rev", "Net Income Available to Common"),
            ]),
            ("MÉTRICAS POR ACCIÓN Y ACCIONES EN CIRCULACIÓN", [
                ("BPA Básico (Basic EPS)", "eps_basic", "", "eps", False, False, False, True, None, "Basic EPS"),
                ("BPA Diluido Normalizado (Diluted EPS)", "eps_diluted", "", "eps", False, True, False, True, None, "Diluted EPS"),
                ("Acciones Básicas Promedio Ponderado (M)", "shares_basic", "", "shares", True, False, False, True, None, "Weighted Average Shares Basic"),
                ("Acciones Diluidas Promedio Ponderado (M)", "shares_diluted", "", "shares", True, True, False, True, None, "Weighted Average Shares Diluted"),
                ("Dividendos por Acción (DPS)", "dps", "", "dps", True, False, False, False, None, "Dividends Per Share"),
            ])
        ]
    else:
        pnl_sections = [
            ("INGRESOS Y BENEFICIO BRUTO", [
                ("Ingresos Totales (Revenue)", "revenue", "[+]", "subtotal", False, True, False, True, "rev", "Revenue"),
                ("Coste de Ventas (COGS)", "cogs", "[-]", "item", True, False, True, True, "rev", "Cost of Goods Sold"),
                ("Beneficio Bruto (Gross Profit)", "gross_profit", "[=]", "subtotal", False, True, False, True, "rev", "Gross Profit"),
            ]),
            ("GASTOS OPERATIVOS Y EBIT", [
                ("Investigación y Desarrollo (I+D / R&D)", "rd_expense", "[-]", "item", True, False, True, False, "rev", "Research & Development"),
                ("Ventas, Generales y Administrativos (SG&A)", "sga_expense", "[-]", "item", True, False, True, True, "rev", "Selling, General & Administrative"),
                ("Provisión para Pérdidas Crediticias (Fintech)", "credit_loss_provision", "[-]", "item", True, False, True, False, "rev", "Provision for Credit Losses"),
                ("Otros Gastos / (Ingresos) Operativos", "other_operating_expense", "[-]", "item", True, False, True, False, "rev", "Other Operating Expenses"),
                ("Total Gastos Operativos (OpEx)", "total_operating_expenses", "[=]", "subtotal", False, True, True, True, "rev", "Total Operating Expenses"),
                ("Beneficio Operativo (EBIT)", "operating_income", "[=]", "result", False, True, False, True, "rev", "Operating Income"),
            ]),
            ("PARTIDAS NO OPERATIVAS, IMPUESTOS Y BENEFICIO NETO", [
                ("Ingresos por Intereses e Inversiones", "interest_income", "[+]", "item", True, False, False, False, "rev", "Interest & Investment Income"),
                ("Gastos por Intereses Financieros", "interest_expense", "[-]", "item", True, False, True, False, "rev", "Interest Expense"),
                ("Otros Ingresos / (Gastos) No Operativos Netos", "other_non_operating", "[±]", "item", True, False, False, False, "rev", "Other Non-Operating Income / Expense"),
                ("Total Ingresos / (Gastos) No Operativos Netos", "total_non_operating", "[=]", "subtotal", False, True, False, True, "rev", "Total Non-Operating"),
                ("Beneficio Antes de Impuestos (EBT)", "ebt", "[=]", "subtotal", False, True, False, True, "rev", "Pre-Tax Income (EBT)"),
                ("Impuesto sobre Beneficios (Income Tax)", "income_tax", "[-]", "item", True, False, True, True, "ebt", "Income Tax Expense"),
                ("Participación en Resultados de Asociadas y Otros", "share_of_associates", "[±]", "item", True, False, False, False, "rev", "Equity in Earnings / (Losses) of Associates"),
                ("Beneficio Neto Consolidado (Net Income)", "net_income", "[=]", "result", False, True, False, True, "rev", "Net Income"),
                ("Beneficio Atribuible a Intereses Minoritarios", "minority_interest_pnl", "[-]", "item", True, False, True, False, "rev", "Noncontrolling Interest"),
                ("Dividendos de Acciones Preferentes", "preferred_dividends", "[-]", "item", True, False, True, False, "rev", "Preferred Dividends"),
                ("Beneficio Neto Atribuible a Accionistas Ordinarios", "net_income_common", "[=]", "subtotal", False, True, False, False, "rev", "Net Income Available to Common"),
            ]),
            ("MÉTRICAS POR ACCIÓN Y ACCIONES EN CIRCULACIÓN", [
                ("BPA Básico (Basic EPS)", "eps_basic", "", "eps", False, False, False, True, None, "Basic EPS"),
                ("BPA Diluido Normalizado (Diluted EPS)", "eps_diluted", "", "eps", False, True, False, True, None, "Diluted EPS"),
                ("Acciones Básicas Promedio Ponderado (M)", "shares_basic", "", "shares", True, False, False, True, None, "Weighted Average Shares Basic"),
                ("Acciones Diluidas Promedio Ponderado (M)", "shares_diluted", "", "shares", True, True, False, True, None, "Weighted Average Shares Diluted"),
                ("Dividendos por Acción (DPS)", "dps", "", "dps", True, False, False, False, None, "Dividends Per Share"),
            ])
        ]

    std_inc_rows = _build_standardized_section(pnl_sections, pnl_data, default_pct_mode="rev")
    std_inc_rows.extend(_get_memo_rows(statements_fys, "pnl"))
    std_pnl = [_build_statement_cells(r, statements_fys, canonical, ebt_dict=ebt_dict_std) for r in std_inc_rows]

    # 2. ESTADO DE FLUJOS DE CAJA (CASH FLOW STATEMENT)
    cf_sections = [
        ("ACTIVIDADES OPERATIVAS (OPERATING ACTIVITIES)", [
            ("Beneficio Neto Consolidado (Net Income)", "net_income", "[+]", "subtotal", False, True, False, True, "ni", "Net Income"),
            ("Depreciación y Amortización (D&A)", "da", "[+]", "item", True, False, False, True, "ni", "Depreciation & Amortization"),
            ("Compensación Basada en Acciones (SBC)", "sbc", "[+]", "item", True, False, False, False, "ni", "Share-Based Compensation"),
            ("Impuestos sobre Beneficios Diferidos (Deferred Taxes)", "deferred_taxes", "[±]", "item", True, False, False, False, "ni", "Deferred Income Taxes"),
            ("Otros Ajustes Operativos No Monetarios (Other Non-Cash)", "other_noncash", "[±]", "item", True, False, False, False, "ni", "Other Non-Cash Adjustments"),
            ("Variación en Cuentas por Cobrar (AR)", "wc_ar", "[±]", "item", True, False, False, False, "ni", "Change in Accounts Receivable"),
            ("Variación en Inventarios", "wc_inv", "[±]", "item", True, False, False, False, "ni", "Change in Inventories"),
            ("Variación en Cuentas por Pagar (AP)", "wc_ap", "[±]", "item", True, False, False, False, "ni", "Change in Accounts Payable"),
            ("Variación en Otros Activos y Pasivos Operativos", "wc_other", "[±]", "item", True, False, False, False, "ni", "Change in Other Operating Working Capital"),
            ("Flujo de Caja Operativo (CFO)", "cfo", "[=]", "result", False, True, False, True, "ni", "Cash Provided by Operating Activities"),
        ]),
        ("ACTIVIDADES DE INVERSIÓN (INVESTING ACTIVITIES)", [
            ("Inversiones en Inmovilizado / CapEx", "capex", "[-]", "item", True, False, True, (archetype not in ("FINANCIAL_BANKING", "INSURANCE") or any(cf_data.get("capex", {}).get(k) is not None for k in cf_data.get("capex", {}))), "ni", "Capital Expenditures"),
            ("Adquisiciones Netas de Caja (M&A)", "acquisitions_ma", "[-]", "item", True, False, True, False, "ni", "Acquisitions Net of Cash"),
            ("Compras de Inversiones y Valores Negociables", "purchases_investments", "[-]", "item", True, False, True, False, "ni", "Purchases of Investments"),
            ("Ventas y Vencimientos de Inversiones Negociables", "sales_maturities_investments", "[+]", "item", True, False, False, False, "ni", "Sales & Maturities of Investments"),
            ("Otros Flujos de Inversión", "other_investing", "[±]", "item", True, False, False, False, "ni", "Other Investing Activities"),
            ("Flujo de Caja de Inversión (CFI)", "cfi", "[=]", "subtotal", False, True, False, True, "ni", "Cash Used in Investing Activities"),
        ]),
        ("ACTIVIDADES DE FINANCIACIÓN (FINANCING ACTIVITIES)", [
            ("Emisión de Deuda Financiera (Debt Issued)", "debt_issued", "[+]", "item", True, False, False, False, "ni", "Issuance of Debt"),
            ("Amortización y Reembolso de Deuda (Debt Repaid)", "debt_repaid", "[-]", "item", True, False, True, False, "ni", "Repayments of Debt"),
            ("Emisión de Acciones Ordinarias y Planes de Empleados", "stock_issued", "[+]", "item", True, False, False, False, "ni", "Issuance of Common Stock"),
            ("Recompra de Acciones en Mercado Abierto (Buybacks)", "share_repurchases_open_market", "[-]", "item", True, False, True, False, "ni", "Repurchase of Common Stock"),
            ("Retenciones Fiscales por Liquidación de RSU / SBC", "share_repurchases_sbc_tax", "[-]", "item", True, False, True, False, "ni", "Tax Withholding for Share Awards"),
            ("Dividendos Pagados en Efectivo (Dividends Paid)", "dividends_paid", "[-]", "item", True, False, True, True, "ni", "Payment of Dividends"),
            ("Otros Flujos de Financiación", "other_financing", "[±]", "item", True, False, False, False, "ni", "Other Financing Activities"),
            ("Flujo de Caja de Financiación (CFF)", "cff", "[=]", "subtotal", False, True, False, True, "ni", "Cash Provided by / Used in Financing Activities"),
            ("Emisión / (Amortización) Neta de Deuda Financiera", "net_debt_issued", "[=]", "metric", False, True, False, True, "ni", "Net Debt Issuance / Repayment (Memo)"),
        ]),
        ("VARIACIÓN NETA DE EFECTIVO Y CONCILIACIÓN DE CAJA", [
            ("Efectivo, Equivalentes y Restringido al Inicio", "beginning_cash", "[+]", "item", True, False, False, True, "ni", "Cash, Cash Equivalents & Restricted Cash at Beginning of Period"),
            ("Efecto del Tipo de Cambio en el Efectivo (FX Effect)", "fx_effect", "[±]", "item", True, False, False, False, "ni", "Effect of Exchange Rate on Cash"),
            ("Variación Neta de Efectivo en el Período (Net Change in Cash)", "net_change_in_cash", "[=]", "subtotal", False, True, False, True, "ni", "Net Change in Cash & Equivalents"),
            ("Efectivo, Equivalentes y Efectivo Restringido al Cierre", "ending_cash", "[=]", "subtotal", False, True, False, True, "ni", "Ending Cash & Equivalents"),
            ("Flujo de Caja Libre Estándar (FCF = CFO − CapEx)", "fcf", "[=]", "result", False, True, False, (archetype not in ("FINANCIAL_BANKING", "INSURANCE")), "ni", "Free Cash Flow"),
            ("Flujo de Fondos Ajustado de las Operaciones (AFFO REIT)", "affo", "[=]", "result", False, True, False, (archetype == "REAL_ESTATE_REIT"), "ni", "Adjusted Funds From Operations"),
        ])
    ]

    std_cf_rows = _build_standardized_section(cf_sections, cf_data, default_pct_mode="ni")
    std_cf_rows.extend(_get_memo_rows(statements_fys, "cashflow"))
    std_cashflow = [_build_statement_cells(r, statements_fys, canonical) for r in std_cf_rows]

    # 3. BALANCE GENERAL CONSOLIDADO (BALANCE SHEET)
    if archetype == "FINANCIAL_BANKING":
        bs_sections = [
            ("ACTIVOS BANCARIOS Y CARTERA CREDITICIA", [
                ("Efectivo y Depósitos en Bancos Centrales", "cash", "[+]", "item", True, False, False, True, "assets", "Cash and Due from Banks"),
                ("Inversiones Financieras y Valores Negociables", "short_term_investments", "[+]", "item", True, False, False, True, "assets", "Trading and Investment Securities"),
                ("Tesorería e Inversiones Líquidas Totales", "total_liquid_cash", "[=]", "subtotal", False, True, False, True, "assets", "Total Liquid Assets"),
                ("Cartera de Préstamos y Crédito Neta (Net Loans)", "net_loans", "[+]", "item", True, False, False, True, "assets", "Loans and Leases Net of Allowance"),
                ("Provisión Acumulada para Pérdidas Crediticias (Allowance)", "allowance_for_loan_losses", "[-]", "item", True, False, True, False, "assets", "Allowance for Loan Losses"),
                ("Inmovilizado Material Neto (PP&E)", "net_ppe", "[+]", "item", True, False, False, False, "assets", "Premises and Equipment Net"),
                ("Fondo de Comercio e Intangibles Netos", "goodwill_and_intangibles", "[+]", "item", True, False, False, False, "assets", "Goodwill and Other Intangibles"),
                ("Otros Activos Financieros y Operativos", "other_assets_sectoral", "[+]", "item", True, False, False, True, "assets", "Other Banking Assets"),
                ("Total Activos (Total Assets)", "total_assets", "[=]", "result", False, True, False, True, "assets", "Total Assets"),
            ]),
            ("DEPÓSITOS Y PASIVOS BANCARIOS", [
                ("Depósitos Totales de Clientes (Total Deposits)", "deposits", "[+]", "item", True, False, False, True, "assets", "Total Customer Deposits"),
                ("Deuda Financiera a Corto Plazo y Repos", "short_term_debt", "[+]", "item", True, False, False, False, "assets", "Short-Term Debt and Borrowings"),
                ("Deuda Financiera a Largo Plazo", "long_term_debt", "[+]", "item", True, False, False, False, "assets", "Long-Term Debt"),
                ("Deuda Financiera Total", "total_debt", "[=]", "subtotal", False, True, False, True, "assets", "Total Debt"),
                ("Otros Pasivos Financieros y Operativos", "other_liabilities_sectoral", "[+]", "item", True, False, False, True, "assets", "Other Banking Liabilities"),
                ("Total Pasivos (Total Liabilities)", "total_liabilities", "[=]", "result", False, True, False, True, "assets", "Total Liabilities"),
            ]),
            ("PATRIMONIO NETO (SHAREHOLDERS' EQUITY)", [
                ("Capital Social y Prima de Emisión (Common Stock & APIC)", "common_stock_and_apic", "[+]", "item", True, False, False, True, "assets", "Common Stock & APIC"),
                ("Ganancias Retenidas / (Déficit Acumulado)", "retained_earnings", "[+]", "item", True, False, False, True, "assets", "Retained Earnings"),
                ("Acciones en Tesorería, AOCI y Otros Fondos Propios", "other_equity", "[±]", "item", True, False, False, True, "assets", "Treasury Stock & AOCI"),
                ("Intereses Minoritarios (Noncontrolling Interests)", "minority_interest", "[+]", "item", True, False, False, False, "assets", "Noncontrolling Interests"),
                ("Total Patrimonio Neto (Stockholders' Equity)", "stockholders_equity", "[=]", "result", False, True, False, True, "assets", "Total Stockholders Equity"),
                ("Total Pasivo y Patrimonio Neto (Total Liabilities & Equity)", "total_liab_and_equity", "[=]", "result", False, True, False, True, "assets", "Total Liabilities and Equity"),
            ])
        ]
    elif archetype == "INSURANCE":
        bs_sections = [
            ("ACTIVOS ASEGURADORES Y CARTERA DE INVERSIONES", [
                ("Efectivo y Equivalentes de Efectivo", "cash", "[+]", "item", True, False, False, True, "assets", "Cash and Equivalents"),
                ("Cartera de Inversiones (Renta Fija y Variable)", "short_term_investments", "[+]", "item", True, False, False, True, "assets", "Fixed Maturities and Equity Securities"),
                ("Tesorería e Inversiones Líquidas Totales", "total_liquid_cash", "[=]", "subtotal", False, True, False, True, "assets", "Total Cash and Invested Assets"),
                ("Cuentas por Cobrar de Primas (Premiums Receivable)", "premiums_receivable", "[+]", "item", True, False, False, True, "assets", "Premiums Receivable"),
                ("Costes de Adquisición de Pólizas Diferidos (DAC)", "deferred_policy_acquisition_costs", "[+]", "item", True, False, False, True, "assets", "Deferred Acquisition Costs"),
                ("Inmovilizado Material Neto (PP&E)", "net_ppe", "[+]", "item", True, False, False, False, "assets", "Property and Equipment Net"),
                ("Fondo de Comercio e Intangibles", "goodwill_and_intangibles", "[+]", "item", True, False, False, False, "assets", "Goodwill and Intangible Assets"),
                ("Otros Activos Aseguradores", "other_assets_sectoral", "[+]", "item", True, False, False, True, "assets", "Other Insurance Assets"),
                ("Total Activos (Total Assets)", "total_assets", "[=]", "result", False, True, False, True, "assets", "Total Assets"),
            ]),
            ("RESERVAS TÉCNICAS Y PASIVOS ASEGURADORES", [
                ("Reservas para Siniestros y Gastos de Liquidación (Loss & LAE Reserves)", "loss_reserves", "[+]", "item", True, False, False, True, "assets", "Unpaid Losses and Loss Adjustment Expenses"),
                ("Primas No Devengadas (Unearned Premiums)", "unearned_premiums", "[+]", "item", True, False, False, True, "assets", "Unearned Premiums"),
                ("Deuda Financiera Total", "total_debt", "[+]", "item", True, False, False, False, "assets", "Total Debt"),
                ("Cuentas por Pagar y Otros Pasivos Aseguradores", "other_liabilities_sectoral", "[+]", "item", True, False, False, True, "assets", "Accounts Payable and Other Liabilities"),
                ("Total Pasivos (Total Liabilities)", "total_liabilities", "[=]", "result", False, True, False, True, "assets", "Total Liabilities"),
            ]),
            ("PATRIMONIO NETO (SHAREHOLDERS' EQUITY)", [
                ("Capital Social y Prima de Emisión (Common Stock & APIC)", "common_stock_and_apic", "[+]", "item", True, False, False, True, "assets", "Common Stock & APIC"),
                ("Ganancias Retenidas / (Déficit Acumulado)", "retained_earnings", "[+]", "item", True, False, False, True, "assets", "Retained Earnings"),
                ("Acciones en Tesorería, AOCI y Otros Fondos Propios", "other_equity", "[±]", "item", True, False, False, True, "assets", "Treasury Stock & AOCI"),
                ("Intereses Minoritarios (Noncontrolling Interests)", "minority_interest", "[+]", "item", True, False, False, False, "assets", "Noncontrolling Interests"),
                ("Total Patrimonio Neto (Stockholders' Equity)", "stockholders_equity", "[=]", "result", False, True, False, True, "assets", "Total Stockholders Equity"),
                ("Total Pasivo y Patrimonio Neto (Total Liabilities & Equity)", "total_liab_and_equity", "[=]", "result", False, True, False, True, "assets", "Total Liabilities and Equity"),
            ])
        ]
    else:
        # STANDARD_CORPORATE, PLATFORM_ECOSYSTEM, REAL_ESTATE_REIT
        ppe_title = "Propiedades Inmobiliarias Netas (Real Estate Net)" if archetype == "REAL_ESTATE_REIT" else "Inmovilizado Material Neto (PP&E Neto)"
        bs_sections = [
            ("ACTIVOS CORRIENTES (CURRENT ASSETS)", [
                ("Efectivo y Equivalentes de Efectivo", "cash", "[+]", "item", True, False, False, True, "assets", "Cash and Cash Equivalents"),
                ("Inversiones a Corto Plazo (Valores Negociables)", "short_term_investments", "[+]", "item", True, False, False, True, "assets", "Short-Term Marketable Securities"),
                ("Efectivo e Inversiones Líquidas Totales", "total_liquid_cash", "[=]", "subtotal", False, True, False, True, "assets", "Total Liquid Cash & Investments"),
                ("Cuentas por Cobrar Comerciales y Otras Netas", "accounts_receivable", "[+]", "item", True, False, False, True, "assets", "Accounts Receivable Net"),
                ("Inventarios / Existencias", "inventories", "[+]", "item", True, False, False, False, "assets", "Inventories Net"),
                ("Gastos Pagados por Anticipado y Otros Activos Corrientes", "other_current_assets", "[+]", "item", True, False, False, True, "assets", "Prepaid Expenses & Other Current Assets"),
                ("Total Activos Corrientes", "total_current_assets", "[=]", "subtotal", False, True, False, True, "assets", "Total Current Assets"),
            ]),
            ("ACTIVOS NO CORRIENTES (NON-CURRENT ASSETS)", [
                (ppe_title, "net_ppe", "[+]", "item", True, False, False, True, "assets", "Property, Plant & Equipment Net"),
                ("Activos por Derecho de Uso en Arrendamiento (ROU Assets)", "rou_asset", "[+]", "item", True, False, False, False, "assets", "Operating Lease Right-of-Use Assets"),
                ("Fondo de Comercio e Intangibles Netos (Goodwill & Intangibles)", "goodwill_and_intangibles", "[+]", "item", True, False, False, True, "assets", "Goodwill & Net Intangible Assets"),
                ("Inversiones Financieras a Largo Plazo", "long_term_investments", "[+]", "item", True, False, False, False, "assets", "Long-Term Marketable Securities"),
                ("Activos por Impuestos Diferidos", "deferred_tax_assets", "[+]", "item", True, False, False, False, "assets", "Deferred Tax Assets Noncurrent"),
                ("Otros Activos No Corrientes", "other_noncurrent_assets", "[+]", "item", True, False, False, True, "assets", "Other Non-Current Assets"),
                ("Total Activos No Corrientes", "total_noncurrent_assets", "[=]", "subtotal", False, True, False, True, "assets", "Total Non-Current Assets"),
                ("Total Activos (Total Assets)", "total_assets", "[=]", "result", False, True, False, True, "assets", "Total Assets"),
            ]),
            ("PASIVOS CORRIENTES (CURRENT LIABILITIES)", [
                ("Cuentas por Pagar Comerciales (Proveedores)", "accounts_payable", "[+]", "item", True, False, False, True, "assets", "Accounts Payable"),
                ("Gastos Acumulados y Pasivos Devengados (Accrued Liabilities)", "accrued_liabilities", "[+]", "item", True, False, False, True, "assets", "Accrued Expenses & Other Current Liabilities"),
                ("Ingresos Diferidos a Corto Plazo (Deferred Revenue)", "deferred_revenue_current", "[+]", "item", True, False, False, False, "assets", "Deferred Revenue Current"),
                ("Deuda Financiera a Corto Plazo y Porción Corriente", "short_term_debt", "[+]", "item", True, False, False, True, "assets", "Commercial Paper & Current Portion of LT Debt"),
                ("Otros Pasivos Corrientes (incl. Arrendamientos CP / Fondos Clientes)", "other_current_liabilities", "[+]", "item", True, False, False, False, "assets", "Other Current Liabilities"),
                ("Total Pasivos Corrientes", "total_current_liabilities", "[=]", "subtotal", False, True, False, True, "assets", "Total Current Liabilities"),
            ]),
            ("PASIVOS NO CORRIENTES (NON-CURRENT LIABILITIES)", [
                ("Deuda Financiera a Largo Plazo", "long_term_debt", "[+]", "item", True, False, False, True, "assets", "Long-Term Debt Noncurrent"),
                ("Pasivos por Arrendamiento Operativo a Largo Plazo", "operating_lease_liability_noncurrent", "[+]", "item", True, False, False, False, "assets", "Operating Lease Liabilities Noncurrent"),
                ("Pasivos por Impuestos Diferidos No Corrientes", "deferred_tax_liabilities_noncurrent", "[+]", "item", True, False, False, False, "assets", "Deferred Tax Liabilities Noncurrent"),
                ("Otros Pasivos No Corrientes", "other_noncurrent_liabilities", "[+]", "item", True, False, False, True, "assets", "Other Non-Current Liabilities"),
                ("Total Pasivos No Corrientes", "total_noncurrent_liabilities", "[=]", "subtotal", False, True, False, True, "assets", "Total Non-Current Liabilities"),
                ("Total Pasivos (Total Liabilities)", "total_liabilities", "[=]", "result", False, True, False, True, "assets", "Total Liabilities"),
            ]),
            ("PATRIMONIO NETO (SHAREHOLDERS' EQUITY)", [
                ("Capital Social y Prima de Emisión (Common Stock & APIC)", "common_stock_and_apic", "[+]", "item", True, False, False, True, "assets", "Common Stock & Additional Paid-in Capital"),
                ("Ganancias Retenidas / (Déficit Acumulado)", "retained_earnings", "[+]", "item", True, False, False, True, "assets", "Retained Earnings / Accumulated Deficit"),
                ("Acciones en Tesorería, AOCI y Otros Fondos Propios", "other_equity", "[±]", "item", True, False, False, True, "assets", "Treasury Stock & Accumulated Other Comprehensive Income"),
                ("Intereses Minoritarios (Noncontrolling Interests)", "minority_interest", "[+]", "item", True, False, False, False, "assets", "Noncontrolling Interests"),
                ("Total Patrimonio Neto (Stockholders' Equity)", "stockholders_equity", "[=]", "result", False, True, False, True, "assets", "Total Stockholders Equity"),
                ("Total Pasivo y Patrimonio Neto (Total Liabilities & Equity)", "total_liab_and_equity", "[=]", "result", False, True, False, True, "assets", "Total Liabilities & Stockholders Equity"),
            ])
        ]

    std_bs_rows = _build_standardized_section(bs_sections, bs_data, default_pct_mode="assets")
    std_bs_rows.extend(_get_memo_rows(statements_fys, "balancesheet"))
    std_balancesheet = [_build_statement_cells(r, statements_fys, canonical, bs_tot_assets=bs_tot_assets_std) for r in std_bs_rows]

    # =============================================================
    # 1.B. CONSTRUCCIÓN DE VISTA OFICIAL SEC (AS-REPORTED 3Y + LTM)
    # =============================================================
    if as_rep_inc:
        as_rep_inc_rows = [_format_as_reported_row(r_raw, as_rep_fys, pct_mode="rev") for r_raw in as_rep_inc]
        as_rep_inc_rows.extend(_get_memo_rows(as_rep_fys, "pnl"))
        as_rep_pnl = [_build_statement_cells(r, as_rep_fys, canonical, ebt_dict=ebt_dict_asrep) for r in as_rep_inc_rows]
    else:
        as_rep_pnl = std_pnl

    if as_rep_cf:
        as_rep_cf_rows = [_format_as_reported_row(r_raw, as_rep_fys, pct_mode="ni") for r_raw in as_rep_cf]
        as_rep_cf_rows.extend(_get_memo_rows(as_rep_fys, "cashflow"))
        as_rep_cashflow = [_build_statement_cells(r, as_rep_fys, canonical) for r in as_rep_cf_rows]
    else:
        as_rep_cashflow = std_cashflow

    if as_rep_bs:
        as_rep_bs_rows = [_format_as_reported_row(r_raw, as_rep_fys, pct_mode="assets") for r_raw in as_rep_bs]
        as_rep_bs_rows.extend(_get_memo_rows(as_rep_fys, "balancesheet"))
        as_rep_balancesheet = [_build_statement_cells(r, as_rep_fys, canonical, bs_tot_assets=bs_tot_assets_asrep) for r in as_rep_bs_rows]
    else:
        as_rep_balancesheet = std_balancesheet

    # Por retrocompatibilidad directa
    statements_pnl = std_pnl
    statements_cashflow = std_cashflow
    statements_balancesheet = std_balancesheet



    # Highlights de Cabecera adaptados dinámicamente por Arquetipo
    latest_p = statements_fys[0] if statements_fys else "LTM"
    rev_ltm_val = _to_m(canonical.get("revenue", {}).get(latest_p))
    gp_ltm_val = _to_m(canonical.get("gross_profit", {}).get(latest_p))
    ebit_ltm_val = _to_m(canonical.get("operating_income", {}).get(latest_p))
    ni_ltm_val = _to_m(canonical.get("net_income", {}).get(latest_p))
    fcf_ltm_val = _to_m(canonical.get("free_cash_flow", {}).get(latest_p))
    if fcf_ltm_val is None and archetype == "INSURANCE":
        cfo_v = canonical.get("cash_from_operations", {}).get(latest_p)
        cx_v = canonical.get("capital_expenditures", {}).get(latest_p)
        if cfo_v is not None and cx_v is not None:
            fcf_ltm_val = _to_m(float(cfo_v) - abs(float(cx_v)))

    net_debt_dict = {p: _to_m(bs_data.get("net_financial_position", {}).get(p)) for p in statements_fys}
    nd_ltm_val = net_debt_dict.get(latest_p)
    eq_ltm_val = _to_m(bs_data.get("stockholders_equity", {}).get(latest_p) or canonical.get("stockholders_equity", {}).get(latest_p))
    ca_val = _to_m(bs_data.get("total_current_assets", {}).get(latest_p) or canonical.get("current_assets", {}).get(latest_p))
    cl_val = _to_m(bs_data.get("total_current_liabilities", {}).get(latest_p) or canonical.get("current_liabilities", {}).get(latest_p))
    cr_val = round(ca_val / cl_val, 2) if (ca_val and cl_val and cl_val != 0) else key_ratios.get("current_ratio", {}).get(latest_p)

    # Métricas especializadas
    if is_banking:
        nim_val = key_ratios.get("nim_pct", {}).get(latest_p) or key_ratios.get("risk_adj_nim_pct", {}).get(latest_p) or enriched.get("risk_adjusted_nim_pct")
        eff_val = key_ratios.get("efficiency_ratio_pct", {}).get(latest_p) or enriched.get("efficiency_ratio_pct")
        roe_val = key_ratios.get("roe_pct", {}).get(latest_p) or enriched.get("return_on_equity_reported")

        rotce_val = key_ratios.get("rotce_pct", {}).get(latest_p)
        if rotce_val is None:
            ni_comm = pnl_data.get("net_income_common", {}).get(latest_p) or canonical.get("net_income_common", {}).get(latest_p) or canonical.get("net_income", {}).get(latest_p)
            eq = bs_data.get("stockholders_equity", {}).get(latest_p) or canonical.get("stockholders_equity", {}).get(latest_p)
            pref = _num(bs_det, "PreferredStockValue", latest_p) or _num(bs_det, "us-gaap_PreferredStockIncludingAdditionalPaidInCapitalNetOfDiscount", latest_p) or 0.0
            gw_int = bs_data.get("goodwill_and_intangibles", {}).get(latest_p) or 0.0
            tce = (eq - pref - gw_int) if eq else 0.0
            if tce > 0 and ni_comm is not None:
                rotce_val = round(ni_comm / tce * 100.0, 1)
            elif roe_val is not None:
                rotce_val = round(float(roe_val), 1)

        cet1_val = key_ratios.get("cet1_ratio_pct", {}).get(latest_p) or enriched.get("cet1_ratio_pct")
        if cet1_val is None:
            eq = bs_data.get("stockholders_equity", {}).get(latest_p) or canonical.get("stockholders_equity", {}).get(latest_p)
            pref = _num(bs_det, "PreferredStockValue", latest_p) or _num(bs_det, "us-gaap_PreferredStockIncludingAdditionalPaidInCapitalNetOfDiscount", latest_p) or 0.0
            gw_int = bs_data.get("goodwill_and_intangibles", {}).get(latest_p) or 0.0
            tot_ast = bs_data.get("total_assets", {}).get(latest_p) or canonical.get("total_assets", {}).get(latest_p)
            tce = (eq - pref - gw_int) if eq else 0.0
            if tce > 0 and tot_ast and tot_ast > 0:
                cet1_val = round(tce / tot_ast * 100.0, 1)
            elif eq and tot_ast and tot_ast > 0:
                cet1_val = round(eq / tot_ast * 100.0, 1)

        npl_cov_val = key_ratios.get("provision_coverage_pct", {}).get(latest_p) or enriched.get("provision_coverage_pct")
        if npl_cov_val is None:
            allowance = bs_data.get("allowance_for_loan_losses", {}).get(latest_p) or _num(bs_det, "FinancingReceivableAllowanceForCreditLosses", latest_p) or _num(bs_det, "us-gaap_FinancingReceivableAllowanceForCreditLossExcludingAccruedInterest", latest_p)
            clp = pnl_data.get("credit_loss_provision", {}).get(latest_p) or canonical.get("credit_loss_provisions", {}).get(latest_p)
            if allowance and clp and clp != 0:
                npl_cov_val = round(abs(allowance) / abs(clp) * 100.0, 1)

        npl_ratio_val = key_ratios.get("npl_ratio_pct", {}).get(latest_p) or enriched.get("npl_90_plus_pct")
        if npl_ratio_val is None:
            npl_ratio_val = key_ratios.get("cost_of_risk_loans_pct", {}).get(latest_p)
    else:
        nim_val = None
        eff_val = None
        roe_val = key_ratios.get("roe_pct", {}).get(latest_p)
        rotce_val = None
        cet1_val = None
        npl_cov_val = None
        npl_ratio_val = None

    if is_insurance:
        comb_ratio_val = key_ratios.get("combined_ratio_pct", {}).get(latest_p) or canonical.get("combined_ratio", {}).get(latest_p)
        loss_ratio_val = key_ratios.get("loss_ratio_pct", {}).get(latest_p) or canonical.get("loss_ratio", {}).get(latest_p)
        exp_ratio_val = key_ratios.get("expense_ratio_pct", {}).get(latest_p) or canonical.get("expense_ratio", {}).get(latest_p)

        inv_yield_val = key_ratios.get("investment_yield_pct", {}).get(latest_p)
        if inv_yield_val is None:
            nii_v = canonical.get("net_investment_income", {}).get(latest_p) or pnl_data.get("net_investment_income", {}).get(latest_p)
            tot_inv = canonical.get("total_investments", {}).get(latest_p) or bs_data.get("short_term_investments", {}).get(latest_p)
            if nii_v and tot_inv and tot_inv > 0:
                inv_yield_val = round(float(nii_v) / float(tot_inv) * 100.0, 1)

        net_prem_val = _to_m(canonical.get("net_premiums_earned", {}).get(latest_p)) or rev_ltm_val
        float_val = _to_m(canonical.get("float_usd", {}).get(latest_p))
        total_inv_val = _to_m(canonical.get("total_investments", {}).get(latest_p) or bs_data.get("short_term_investments", {}).get(latest_p))
    else:
        comb_ratio_val = None
        loss_ratio_val = None
        exp_ratio_val = None
        inv_yield_val = None
        net_prem_val = None
        float_val = None
        total_inv_val = None

    if is_reit:
        rental_rev_val = _to_m(canonical.get("rental_revenue", {}).get(latest_p)) or rev_ltm_val
        noi_val = _to_m(canonical.get("noi", {}).get(latest_p))
        ffo_val = _to_m(canonical.get("ffo", {}).get(latest_p))
        affo_val = _to_m(canonical.get("affo", {}).get(latest_p))
        sh_cnt = canonical.get("shares_diluted", {}).get(latest_p) or canonical.get("weighted_average_shares_diluted", {}).get(latest_p)
        ffo_sh_val = round(float(canonical.get("ffo", {}).get(latest_p)) / float(sh_cnt), 2) if (ffo_val and sh_cnt and float(sh_cnt) > 0) else None
        affo_sh_val = round(float(canonical.get("affo", {}).get(latest_p)) / float(sh_cnt), 2) if (affo_val and sh_cnt and float(sh_cnt) > 0) else None
        div_paid = abs(canonical.get("dividends_paid", {}).get(latest_p) or _num(cf_det, "PaymentsOfDividendsCommonStock", latest_p) or _num(cf_det, "PaymentsOfDividends", latest_p) or 0.0)
        payout_affo_val = round(div_paid / float(canonical.get("affo", {}).get(latest_p)) * 100.0, 1) if (affo_val and div_paid > 0) else None
        tot_debt_val = _to_m(canonical.get("total_debt", {}).get(latest_p))
        tot_assets_val = _to_m(canonical.get("total_assets", {}).get(latest_p))
        ltv_val = round(tot_debt_val / tot_assets_val * 100.0, 1) if (tot_debt_val and tot_assets_val and tot_assets_val > 0) else None
    else:
        rental_rev_val = None
        noi_val = None
        ffo_val = None
        affo_val = None
        ffo_sh_val = None
        affo_sh_val = None
        payout_affo_val = None
        ltv_val = None

    statements_summary = {
        "archetype": archetype,
        "is_financial": is_financial,
        # Standard corporate
        "rev_ltm": _fmt_money(rev_ltm_val),
        "gm_ltm": f"{round(gp_ltm_val / rev_ltm_val * 100.0, 1)}%" if (gp_ltm_val and rev_ltm_val) else "-",
        "om_ltm": f"{round(ebit_ltm_val / rev_ltm_val * 100.0, 1)}%" if (ebit_ltm_val and rev_ltm_val) else "-",
        "fcf_ltm": _fmt_money(fcf_ltm_val),
        "fcf_margin_ltm": f"{round(fcf_ltm_val / rev_ltm_val * 100.0, 1)}%" if (fcf_ltm_val and rev_ltm_val) else "-",
        "fcf_conv_ltm": f"{round(fcf_ltm_val / ni_ltm_val * 100.0, 1)}%" if (fcf_ltm_val and ni_ltm_val) else "-",
        "net_debt_display": _fmt_money(abs(nd_ltm_val)) if (nd_ltm_val and nd_ltm_val < 0) else _fmt_money(nd_ltm_val),
        "net_debt_is_cash": (nd_ltm_val is not None and nd_ltm_val < 0),
        "current_ratio": f"{cr_val:.2f}x" if cr_val else "-",
        "equity_ltm": _fmt_money(eq_ltm_val),
        "net_income_ltm": _fmt_money(ni_ltm_val),
        "net_margin_ltm": f"{round(ni_ltm_val / rev_ltm_val * 100.0, 1)}%" if (ni_ltm_val and rev_ltm_val) else "-",
        # Banking
        "nim_ltm": f"{nim_val:.2f}%" if nim_val is not None else "-",
        "cost_to_income": f"{eff_val:.1f}%" if eff_val is not None else "-",
        "roe_ltm": f"{roe_val:.1f}%" if roe_val is not None else (f"{round(ni_ltm_val / eq_ltm_val * 100.0, 1)}%" if (ni_ltm_val and eq_ltm_val and eq_ltm_val > 0) else "-"),
        "rotce_ltm": f"{rotce_val:.1f}%" if rotce_val is not None else "-",
        "cet1_ratio": f"{cet1_val:.1f}%" if cet1_val is not None else "-",
        "npl_coverage": f"{npl_cov_val:.1f}%" if npl_cov_val is not None else "-",
        "npl_ratio": f"{npl_ratio_val:.1f}%" if npl_ratio_val is not None else "-",
        # Insurance
        "net_premiums_ltm": _fmt_money(net_prem_val) if is_insurance else "-",
        "combined_ratio": f"{comb_ratio_val:.1f}%" if comb_ratio_val is not None else "-",
        "loss_ratio": f"{loss_ratio_val:.1f}%" if loss_ratio_val is not None else "-",
        "expense_ratio": f"{exp_ratio_val:.1f}%" if exp_ratio_val is not None else "-",
        "inv_yield": f"{inv_yield_val:.1f}%" if inv_yield_val is not None else "-",
        "float_usd": _fmt_money(float_val) if is_insurance else "-",
        "total_investments": _fmt_money(total_inv_val) if is_insurance else "-",
        # REIT
        "rental_rev_ltm": _fmt_money(rental_rev_val) if is_reit else "-",
        "noi_ltm": _fmt_money(noi_val) if is_reit else "-",
        "noi_margin": f"{round(noi_val / rev_ltm_val * 100.0, 1)}%" if (noi_val and rev_ltm_val) else "-",
        "ffo_ltm": _fmt_money(ffo_val) if is_reit else "-",
        "ffo_margin": f"{round(ffo_val / rev_ltm_val * 100.0, 1)}%" if (ffo_val and rev_ltm_val) else "-",
        "affo_ltm": _fmt_money(affo_val) if is_reit else "-",
        "ffo_per_share": f"${ffo_sh_val:.2f}" if ffo_sh_val is not None else "-",
        "affo_per_share": f"${affo_sh_val:.2f}" if affo_sh_val is not None else "-",
        "payout_affo": f"{payout_affo_val:.1f}%" if payout_affo_val is not None else "-",
        "ltv_ratio": f"{ltv_val:.1f}%" if ltv_val is not None else "-",
    }

    # Conservamos table_pnl por retrocompatibilidad
    table_pnl = []
    pnl_defs = [
        ("Ingresos Netos (Revenue)", "revenue", True),
        ("Coste de Bienes Vendidos (COGS)", "cost_of_goods_sold", False),
        ("Margen Bruto (Gross Profit)", "gross_profit", True),
        ("Gastos Operativos (OpEx)", "operating_expenses", False),
        ("Beneficio Operativo (EBIT)", "operating_income", True),
        ("Beneficio Neto (Net Income)", "net_income", True),
        ("Flujo de Caja Operativo (CFO)", "cash_from_operations", True),
        ("Inversiones en CapEx", "capital_expenditures", False),
        ("Flujo de Caja Libre (FCF)", "free_cash_flow", True),
        ("Efectivo y Equivalentes", "cash_and_equivalents", False),
        ("Deuda Financiera Total", "total_debt", False),
        ("Deuda Neta", "net_debt", False),
        ("Activos Totales", "total_assets", True),
        ("Patrimonio Neto (Equity)", "stockholders_equity", True),
        ("BPA Diluido Normalizado (Split-Adjusted) ($)", "eps_diluted_adjusted", True),
        ("BPA Diluido Oficial As-Reported (SEC) ($)", "eps_diluted", False),
    ]
    for label, key, is_bold in pnl_defs:
        row_vals = []
        d_dict = canonical.get(key, {})
        if key == "eps_diluted_adjusted" and not d_dict:
            d_dict = canonical.get("eps_diluted", {})
        for p in fys:
            v = d_dict.get(p)
            if v is None:
                val_str = "-"
            elif key in ["eps_diluted", "eps_diluted_adjusted"]:
                val_str = f"-${abs(v):.2f}" if v < 0 else f"${v:.2f}"
            else:
                scale_val = abs(v)
                prefix = "-$" if v < 0 else "$"
                if scale_val >= 1e6:
                    val_str = f"{prefix}{scale_val/1e6:,.1f}M"
                elif scale_val > 0:
                    val_str = f"{prefix}{scale_val:,.1f}M"
                else:
                    val_str = "$0.0M"
            row_vals.append(val_str)
        table_pnl.append({
            "label": label,
            "is_bold": is_bold,
            "values": row_vals
        })


    return {
        "table_pnl": table_pnl,
        "statements_pnl": statements_pnl,
        "statements_cashflow": statements_cashflow,
        "statements_balancesheet": statements_balancesheet,
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
