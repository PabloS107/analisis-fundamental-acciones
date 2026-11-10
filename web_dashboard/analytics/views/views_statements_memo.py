# -*- coding: utf-8 -*-
"""
Submódulo de Métricas Analíticas (MEMO), Highlights de Cabecera por Arquetipo y P&L resumido.
"""
from pipeline.canonical_resolvers import _extract_multi_source_val

from .view_utils import fmt_money_m, usd_to_m
from .views_statements_cells import detail_num

_SBC_KEYS = [
    "ShareBasedCompensation",
    "AllocatedShareBasedCompensationExpense",
    "StockOptionPlanExpense",
    "AdjustmentsForSharebasedPayments",
    "ExpenseFromSharebasedPaymentTransactionsWithEmployees",
    "RestrictedStockExpense",
    "us-gaap_RestrictedStockExpense",
    "ShareBasedCompensationArrangementByShareBasedPaymentAwardExpense",
    "meli_StockBasedCompensation",
]


def _compute_banking_rotce_or_cet1(p: str, ratio_type: str, key_ratios: dict, pnl_data: dict, bs_data: dict, canonical: dict, bs_det: dict, roe_fallback=None):
    """Calcula ROTCE o CET1 bancario con fallback único compartido entre tabla MEMO y cabecera."""
    eq = bs_data.get("stockholders_equity", {}).get(p) or canonical.get("stockholders_equity", {}).get(p)
    pref = detail_num(bs_det, "PreferredStockValue", p) or detail_num(bs_det, "us-gaap_PreferredStockIncludingAdditionalPaidInCapitalNetOfDiscount", p) or 0.0
    gw_int = bs_data.get("goodwill_and_intangibles", {}).get(p) or 0.0
    tce = (eq - pref - gw_int) if eq else 0.0

    if ratio_type == "rotce":
        val = key_ratios.get("rotce_pct", {}).get(p)
        if val is not None:
            return val
        ni_comm = pnl_data.get("net_income_common", {}).get(p) or canonical.get("net_income_common", {}).get(p) or canonical.get("net_income", {}).get(p)
        if tce > 0 and ni_comm is not None:
            return round(ni_comm / tce * 100.0, 1)
        roe_p = roe_fallback if roe_fallback is not None else key_ratios.get("roe_pct", {}).get(p)
        return round(float(roe_p), 1) if roe_p is not None else None

    val = key_ratios.get("cet1_ratio_pct", {}).get(p)
    if val is not None:
        return val
    tot_ast = bs_data.get("total_assets", {}).get(p) or canonical.get("total_assets", {}).get(p)
    if tce > 0 and tot_ast and tot_ast > 0:
        return round(tce / tot_ast * 100.0, 1)
    if eq and tot_ast and tot_ast > 0:
        return round(eq / tot_ast * 100.0, 1)
    return None


def _compute_npl_coverage(p: str, key_ratios: dict, enriched: dict, bs_data: dict, pnl_data: dict, canonical: dict, bs_det: dict):
    cov_val = key_ratios.get("provision_coverage_pct", {}).get(p) or (enriched.get("provision_coverage_pct") if p == "LTM" else None)
    if cov_val is not None:
        return cov_val
    allowance = (
        bs_data.get("allowance_for_loan_losses", {}).get(p)
        or detail_num(bs_det, "FinancingReceivableAllowanceForCreditLosses", p)
        or detail_num(bs_det, "us-gaap_FinancingReceivableAllowanceForCreditLossExcludingAccruedInterest", p)
    )
    clp = pnl_data.get("credit_loss_provision", {}).get(p) or canonical.get("credit_loss_provisions", {}).get(p)
    if allowance and clp and clp != 0:
        return round(abs(allowance) / abs(clp) * 100.0, 1)
    return None


def _compute_insurance_inv_yield(p: str, key_ratios: dict, canonical: dict, pnl_data: dict, bs_data: dict):
    y_val = key_ratios.get("investment_yield_pct", {}).get(p)
    if y_val is not None:
        return y_val
    nii_v = canonical.get("net_investment_income", {}).get(p) or pnl_data.get("net_investment_income", {}).get(p)
    tot_inv = canonical.get("total_investments", {}).get(p) or bs_data.get("short_term_investments", {}).get(p)
    return round(float(nii_v) / float(tot_inv) * 100.0, 1) if (nii_v and tot_inv and tot_inv > 0) else None


def _find_dna_m(period: str, cf_det: dict, canonical: dict, as_rep_cf: list):
    v = (
        detail_num(cf_det, "DepreciationAndAmortization", period)
        or detail_num(cf_det, "us-gaap_DepreciationAndAmortization", period)
        or detail_num(cf_det, "DepreciationDepletionAndAmortization", period)
        or detail_num(cf_det, "DepreciationAmortizationAndAccretionNet", period)
        or detail_num(cf_det, "Depreciation", period)
        or canonical.get("depreciation_and_amortization", {}).get(period)
    )
    if v is not None:
        return usd_to_m(v)
    for r_cf in (as_rep_cf or []):
        if "depreciation" in str(r_cf.get("concept", "")).lower() or "depreciation" in str(r_cf.get("label", "")).lower():
            cf_v = r_cf.get("values", {}).get(period)
            if cf_v is not None:
                return usd_to_m(float(cf_v))
    return None


def _build_pnl_memo(target_fys, fs, archetype, canonical, key_ratios, enriched, bs_data, pnl_data, as_rep_cf, rev_d, gp_d, ebit_d, ni_d):
    bs_det, cf_det = fs.get("balance_sheet_detail", {}), fs.get("cash_flow_detail", {})
    if archetype == "FINANCIAL_BANKING":
        nim_d = {p: (key_ratios.get("nim_pct", {}).get(p) or key_ratios.get("risk_adj_nim_pct", {}).get(p) or (enriched.get("risk_adjusted_nim_pct") if p == "LTM" else None)) for p in target_fys}
        eff_d = {p: key_ratios.get("efficiency_ratio_pct", {}).get(p) for p in target_fys}
        roe_d = {p: key_ratios.get("roe_pct", {}).get(p) for p in target_fys}
        rotce_d = {p: _compute_banking_rotce_or_cet1(p, "rotce", key_ratios, pnl_data, bs_data, canonical, bs_det) for p in target_fys}
        npl_cov_d = {p: _compute_npl_coverage(p, key_ratios, enriched, bs_data, pnl_data, canonical, bs_det) for p in target_fys}
        return [
            {"label": "MARGEN NETO DE INTERÉS (NIM %)", "orig_tooltip": "Net Interest Margin (%)", "clarification": "Ingresos Netos por Intereses / Activos Rentables Promedio", "operator": "[%]", "row_type": "metric_pct", "indent": True, "is_bold": False, "data": nim_d, "pct_mode": None},
            {"label": "RATIO DE EFICIENCIA (COST-TO-INCOME %)", "orig_tooltip": "Efficiency Ratio (%)", "clarification": "Gastos No Financieros / Ingresos Netos de Explotación", "operator": "[%]", "row_type": "metric_pct", "indent": True, "is_bold": False, "data": eff_d, "pct_mode": None},
            {"label": "RENTABILIDAD SOBRE EQUITY (ROE %)", "orig_tooltip": "Return on Equity (%)", "clarification": "Beneficio Neto / Patrimonio Neto Promedio", "operator": "[%]", "row_type": "metric_pct", "indent": True, "is_bold": False, "data": roe_d, "pct_mode": None},
            {"label": "RENTABILIDAD SOBRE EQUITY TANGIBLE (ROTCE %)", "orig_tooltip": "Return on Tangible Common Equity (%)", "clarification": "Beneficio Neto / Patrimonio Neto Tangible Promedio", "operator": "[%]", "row_type": "metric_pct", "indent": True, "is_bold": False, "data": rotce_d, "pct_mode": None},
            {"label": "COBERTURA DE PROVISIONES (%)", "orig_tooltip": "Provision Coverage Ratio (%)", "clarification": "Fondo de Provisiones / Total Préstamos Dudosos (NPLs)", "operator": "[%]", "row_type": "metric_pct", "indent": True, "is_bold": False, "data": npl_cov_d, "pct_mode": None},
        ]
    if archetype == "INSURANCE":
        comb_d = {p: key_ratios.get("combined_ratio_pct", {}).get(p) for p in target_fys}
        loss_d = {p: key_ratios.get("loss_ratio_pct", {}).get(p) for p in target_fys}
        exp_d = {p: key_ratios.get("expense_ratio_pct", {}).get(p) for p in target_fys}
        float_d = {p: usd_to_m(canonical.get("float_usd", {}).get(p)) for p in target_fys}
        inv_y_d = {p: _compute_insurance_inv_yield(p, key_ratios, canonical, pnl_data, bs_data) for p in target_fys}
        return [
            {"label": "RATIO COMBINADO (%)", "orig_tooltip": "Combined Ratio (%)", "clarification": "Suma de Siniestralidad y Gastos de Adquisición (<100% = beneficio técnico)", "operator": "[%]", "row_type": "metric_pct", "indent": False, "is_bold": True, "data": comb_d, "pct_mode": None},
            {"label": "RATIO DE SINIESTRALIDAD (LOSS RATIO %)", "orig_tooltip": "Loss Ratio (%)", "clarification": "Costes de Siniestros Incurridos / Primas Devengadas", "operator": "[%]", "row_type": "metric_pct", "indent": True, "is_bold": False, "data": loss_d, "pct_mode": None},
            {"label": "RATIO DE GASTOS DE SUSCRIPCIÓN (%)", "orig_tooltip": "Expense Ratio (%)", "clarification": "Gastos de Comercialización y Administración / Primas Devengadas", "operator": "[%]", "row_type": "metric_pct", "indent": True, "is_bold": False, "data": exp_d, "pct_mode": None},
            {"label": "FLOAT ASEGURADOR DISPONIBLE", "orig_tooltip": "Insurance Float ($M)", "clarification": "Fondos de Prima Cobrados Pendientes de Liquidación", "operator": "[⚡]", "row_type": "metric", "indent": False, "is_bold": True, "data": float_d, "pct_mode": "rev"},
            {"label": "RENDIMIENTO DE CARTERA INVERTIDA (%)", "orig_tooltip": "Investment Portfolio Yield (%)", "clarification": "Rendimiento Neto de Inversiones / Cartera Promedio", "operator": "[%]", "row_type": "metric_pct", "indent": True, "is_bold": False, "data": inv_y_d, "pct_mode": None},
        ]
    if archetype == "REAL_ESTATE_REIT":
        noi_d = {p: usd_to_m(canonical.get("noi", {}).get(p)) for p in target_fys}
        ffo_d = {p: usd_to_m(canonical.get("ffo", {}).get(p)) for p in target_fys}
        affo_d = {p: usd_to_m(canonical.get("affo", {}).get(p)) for p in target_fys}
        ffo_sh_d = {p: (key_ratios.get("ffo_per_share", {}).get(p) or (round(float(canonical.get("ffo", {}).get(p)) / float(canonical.get("shares_diluted", {}).get(p)), 2) if (canonical.get("ffo", {}).get(p) and canonical.get("shares_diluted", {}).get(p)) else None)) for p in target_fys}
        affo_sh_d = {p: (key_ratios.get("affo_per_share", {}).get(p) or (round(float(canonical.get("affo", {}).get(p)) / float(canonical.get("shares_diluted", {}).get(p)), 2) if (canonical.get("affo", {}).get(p) and canonical.get("shares_diluted", {}).get(p)) else None)) for p in target_fys}
        payout_affo_d = {
            p: round(dp / af * 100.0, 1) if (dp > 0 and af > 0) else None
            for p in target_fys
            for dp in (abs(canonical.get("dividends_paid", {}).get(p) or detail_num(cf_det, "PaymentsOfDividendsCommonStock", p) or detail_num(cf_det, "PaymentsOfDividends", p) or 0.0),)
            for af in (float(canonical.get("affo", {}).get(p) or 0.0),)
        }
        return [
            {"label": "NET OPERATING INCOME (NOI)", "orig_tooltip": "Net Operating Income ($M)", "clarification": "Ingresos por Alquileres − Gastos Operativos de Inmuebles", "operator": "[⚡]", "row_type": "metric", "indent": False, "is_bold": True, "data": noi_d, "pct_mode": "rev"},
            {"label": "MARGEN NOI (%)", "orig_tooltip": "NOI Margin (%)", "clarification": "NOI Inmobiliario / Ingresos por Rentas", "operator": "[%]", "row_type": "metric_pct", "indent": True, "is_bold": False, "data": {p: round(noi_d[p] / rev_d[p] * 100.0, 1) if (noi_d.get(p) is not None and rev_d.get(p) and rev_d[p] > 0) else None for p in target_fys}, "pct_mode": None},
            {"label": "FUNDS FROM OPERATIONS (FFO)", "orig_tooltip": "Funds From Operations ($M)", "clarification": "Beneficio Neto + D&A Inmobiliaria − Ganancias por Venta", "operator": "[⚡]", "row_type": "metric", "indent": False, "is_bold": True, "data": ffo_d, "pct_mode": "rev"},
            {"label": "MARGEN FFO (%)", "orig_tooltip": "FFO Margin (%)", "clarification": "FFO / Ingresos Totales por Rentas", "operator": "[%]", "row_type": "metric_pct", "indent": True, "is_bold": False, "data": {p: round(ffo_d[p] / rev_d[p] * 100.0, 1) if (ffo_d.get(p) is not None and rev_d.get(p) and rev_d[p] > 0) else None for p in target_fys}, "pct_mode": None},
            {"label": "AFFO NORMALIZADO", "orig_tooltip": "Adjusted Funds From Operations ($M)", "clarification": "FFO − CapEx de Mantenimiento / Mejoras Inmobiliarias", "operator": "[⚡]", "row_type": "metric", "indent": False, "is_bold": True, "data": affo_d, "pct_mode": "rev"},
            {"label": "PAYOUT RATIO S/ AFFO (%)", "orig_tooltip": "AFFO Payout Ratio (%)", "clarification": "Dividendos Totales Pagados / AFFO Generado (<90% sostenible)", "operator": "[%]", "row_type": "metric_pct", "indent": True, "is_bold": False, "data": payout_affo_d, "pct_mode": None},
            {"label": "FFO POR ACCIÓN (FFO / SHARE $)", "orig_tooltip": "FFO Per Share ($/acción)", "clarification": "Funds From Operations / Acciones Diluidas", "operator": "[$]", "row_type": "eps", "indent": True, "is_bold": False, "data": ffo_sh_d, "pct_mode": None},
            {"label": "AFFO POR ACCIÓN (AFFO / SHARE $)", "orig_tooltip": "AFFO Per Share ($/acción)", "clarification": "Adjusted Funds From Operations / Acciones Diluidas", "operator": "[$]", "row_type": "eps", "indent": True, "is_bold": False, "data": affo_sh_d, "pct_mode": None},
        ]

    dna_dict = {p: _find_dna_m(p, cf_det, canonical, as_rep_cf) for p in target_fys}
    ebitda_dict = {p: (round(ebit_d[p] + (dna_dict[p] or 0.0), 1) if ebit_d[p] is not None else None) for p in target_fys}
    ebitda_m_dict = {p: (round(ebitda_dict[p] / rev_d[p] * 100.0, 1) if (ebitda_dict.get(p) is not None and rev_d.get(p) and rev_d[p] > 0) else None) for p in target_fys}
    sbc_dict = {p: usd_to_m(_extract_multi_source_val(fs, "cashflow", _SBC_KEYS, p, "stock_based_compensation")) for p in target_fys}
    sbc_int_dict = {p: (round(sbc_dict[p] / rev_d[p] * 100.0, 1) if (sbc_dict.get(p) is not None and rev_d.get(p) and rev_d[p] > 0) else None) for p in target_fys}
    ebit_adj_sbc = {p: (round(ebit_d[p] - (sbc_dict[p] or 0.0), 1) if ebit_d.get(p) is not None else None) for p in target_fys}
    ni_adj_sbc = {p: (round(ni_d[p] - (sbc_dict[p] or 0.0), 1) if ni_d.get(p) is not None else None) for p in target_fys}
    ebit_adj_m = {p: (round(ebit_adj_sbc[p] / rev_d[p] * 100.0, 1) if (ebit_adj_sbc.get(p) is not None and rev_d.get(p) and rev_d[p] > 0) else None) for p in target_fys}
    ni_adj_m = {p: (round(ni_adj_sbc[p] / rev_d[p] * 100.0, 1) if (ni_adj_sbc.get(p) is not None and rev_d.get(p) and rev_d[p] > 0) else None) for p in target_fys}
    return [
        {"label": "EBITDA NORMALIZADO", "orig_tooltip": "Normalized EBITDA ($M)", "clarification": "Beneficio Operativo (EBIT) + Depreciación y Amortización", "operator": "[⚡]", "row_type": "metric", "indent": False, "is_bold": True, "data": ebitda_dict, "pct_mode": "rev"},
        {"label": "MARGEN EBITDA (%)", "orig_tooltip": "EBITDA Margin (%)", "clarification": "EBITDA Normalizado / Ingresos Totales", "operator": "[%]", "row_type": "metric_pct", "indent": True, "is_bold": False, "data": ebitda_m_dict, "pct_mode": None},
        {"label": "MARGEN BRUTO (%)", "orig_tooltip": "Gross Margin (%)", "clarification": "Beneficio Bruto / Ingresos Totales", "operator": "[%]", "row_type": "metric_pct", "indent": True, "is_bold": False, "data": {p: round(gp_d[p] / rev_d[p] * 100.0, 1) if (gp_d.get(p) is not None and rev_d.get(p) and rev_d[p] > 0) else None for p in target_fys}, "pct_mode": None},
        {"label": "MARGEN OPERATIVO (%)", "orig_tooltip": "Operating Margin EBIT (%)", "clarification": "Beneficio Operativo (EBIT) / Ingresos Totales", "operator": "[%]", "row_type": "metric_pct", "indent": True, "is_bold": False, "data": {p: round(ebit_d[p] / rev_d[p] * 100.0, 1) if (ebit_d.get(p) is not None and rev_d.get(p) and rev_d[p] > 0) else None for p in target_fys}, "pct_mode": None},
        {"label": "MARGEN NETO (%)", "orig_tooltip": "Net Profit Margin (%)", "clarification": "Beneficio Neto / Ingresos Totales", "operator": "[%]", "row_type": "metric_pct", "indent": True, "is_bold": False, "data": {p: round(ni_d[p] / rev_d[p] * 100.0, 1) if (ni_d.get(p) is not None and rev_d.get(p) and rev_d[p] > 0) else None for p in target_fys}, "pct_mode": None},
        {"label": "COMPENSACIÓN BASADA EN ACCIONES (SBC)", "orig_tooltip": "Stock-Based Compensation ($M)", "clarification": "Gasto no monetario por remuneración en acciones a empleados", "operator": "[⚡]", "row_type": "metric", "indent": False, "is_bold": False, "data": sbc_dict, "pct_mode": "rev"},
        {"label": "BENEFICIO OPERATIVO ADJ. SBC (EBIT - SBC)", "orig_tooltip": "Operating Income adjusted for SBC ($M)", "clarification": "EBIT − Compensación Basada en Acciones", "operator": "[⚡]", "row_type": "metric", "indent": True, "is_bold": True, "data": ebit_adj_sbc, "pct_mode": "rev"},
        {"label": "BENEFICIO NETO ADJ. SBC (NET INCOME - SBC)", "orig_tooltip": "Net Income adjusted for SBC ($M)", "clarification": "Beneficio Neto − Compensación Basada en Acciones", "operator": "[⚡]", "row_type": "metric", "indent": True, "is_bold": True, "data": ni_adj_sbc, "pct_mode": "rev"},
        {"label": "INTENSIDAD DE SBC (% S/ VENTAS)", "orig_tooltip": "SBC Intensity (% of Revenue)", "clarification": "Compensación en Acciones (SBC) / Ingresos Totales", "operator": "[%]", "row_type": "metric_pct", "indent": True, "is_bold": False, "data": sbc_int_dict, "pct_mode": None},
        {"label": "MARGEN EBIT ADJ. SBC (%)", "orig_tooltip": "EBIT Margin adjusted for SBC (%)", "clarification": "(EBIT − SBC) / Ingresos Totales", "operator": "[%]", "row_type": "metric_pct", "indent": True, "is_bold": False, "data": ebit_adj_m, "pct_mode": None},
        {"label": "MARGEN NETO ADJ. SBC (%)", "orig_tooltip": "Net Margin adjusted for SBC (%)", "clarification": "(Net Income − SBC) / Ingresos Totales", "operator": "[%]", "row_type": "metric_pct", "indent": True, "is_bold": False, "data": ni_adj_m, "pct_mode": None},
    ]


def _build_cashflow_memo(target_fys, fs, archetype, canonical, key_ratios, bs_data, cf_data, cap_flows, rev_d, ni_d, fcf_d):
    bs_det = fs.get("balance_sheet_detail", {})
    if archetype == "FINANCIAL_BANKING":
        dep_d = {p: usd_to_m(canonical.get("total_deposits", {}).get(p) or canonical.get("deposits", {}).get(p) or bs_data.get("deposits", {}).get(p) or detail_num(bs_det, "Deposits", p) or detail_num(bs_det, "ifrs-full_DepositsFromCustomers", p)) for p in target_fys}
        loans_d = {p: usd_to_m(canonical.get("net_loans", {}).get(p) or bs_data.get("net_loans", {}).get(p) or detail_num(bs_det, "LoansAndLeasesReceivableNetOfDeferredIncome", p) or detail_num(bs_det, "FinancingReceivableExcludingAccruedInterestBeforeAllowanceForCreditLossesNetOfDeferredIncome", p) or detail_num(bs_det, "ifrs-full_LoansAndAdvancesToCustomers", p)) for p in target_fys}
        ld_d = {p: (key_ratios.get("ldr_pct", {}).get(p) or (round(loans_d[p] / dep_d[p] * 100.0, 1) if (loans_d.get(p) and dep_d.get(p) and dep_d[p] > 0) else None)) for p in target_fys}
        return [
            {"label": "DEPÓSITOS TOTALES DE CLIENTES", "orig_tooltip": "Total Customer Deposits ($M)", "clarification": "Fondeo comercial primario del balance bancario", "operator": "[⚡]", "row_type": "metric", "indent": False, "is_bold": True, "data": dep_d, "pct_mode": None},
            {"label": "PRÉSTAMOS CONCEDIDOS NETOS", "orig_tooltip": "Net Loans & Leases ($M)", "clarification": "Cartera de crédito tras provisión por insolvencias", "operator": "[⚡]", "row_type": "metric", "indent": False, "is_bold": True, "data": loans_d, "pct_mode": None},
            {"label": "RATIO PRÉSTAMOS / DEPÓSITOS (L/D %)", "orig_tooltip": "Loan-to-Deposit Ratio (%)", "clarification": "Cartera Crediticia Neta / Depósitos Totales", "operator": "[%]", "row_type": "metric_pct", "indent": True, "is_bold": False, "data": ld_d, "pct_mode": None},
        ]
    if archetype == "INSURANCE":
        fcf_ins_d = {}
        for p in target_fys:
            fc = canonical.get("free_cash_flow", {}).get(p) or cf_data.get("fcf", {}).get(p)
            if fc is None:
                cfo_v, cx_v = canonical.get("cash_from_operations", {}).get(p) or cf_data.get("cfo", {}).get(p), canonical.get("capital_expenditures", {}).get(p) or cf_data.get("capex", {}).get(p)
                if cfo_v is not None and cx_v is not None:
                    fc = float(cfo_v) - abs(float(cx_v))
            fcf_ins_d[p] = usd_to_m(fc)
        return [{"label": "FLUJO DE CAJA LIBRE (FCF)", "orig_tooltip": "Free Cash Flow ($M)", "clarification": "CFO − Inversiones en Inmovilizado", "operator": "[⚡]", "row_type": "metric", "indent": False, "is_bold": True, "data": fcf_ins_d, "pct_mode": "rev"}]
    if archetype == "REAL_ESTATE_REIT":
        ffo_d = {p: usd_to_m(canonical.get("ffo", {}).get(p)) for p in target_fys}
        payout_affo_d = {
            p: (round(abs(float(div_p)) / float(affo_p) * 100.0, 1) if (div_p is not None and affo_p and float(affo_p) > 0) else None)
            for p in target_fys
            for div_p in (canonical.get("dividends_paid", {}).get(p) or cf_data.get("dividends_paid", {}).get(p),)
            for affo_p in (canonical.get("affo", {}).get(p),)
        }
        return [
            {"label": "FONDOS DE OPERACIONES (FFO)", "orig_tooltip": "FFO Cash Flow ($M)", "clarification": "Generación de caja operativa REIT antes de CapEx", "operator": "[⚡]", "row_type": "metric", "indent": False, "is_bold": True, "data": ffo_d, "pct_mode": "rev"},
            {"label": "FLUJO DE CAJA LIBRE (FCF TRAS CAPEX)", "orig_tooltip": "Free Cash Flow ($M)", "clarification": "CFO − CapEx en Mejoras Inmobiliarias", "operator": "[⚡]", "row_type": "metric", "indent": False, "is_bold": True, "data": fcf_d, "pct_mode": "rev"},
            {"label": "RATIO PAYOUT S/ AFFO (%)", "orig_tooltip": "AFFO Dividend Payout Ratio (%)", "clarification": "Dividendos Pagados en Efectivo / AFFO Generado", "operator": "[%]", "row_type": "metric_pct", "indent": True, "is_bold": False, "data": payout_affo_d, "pct_mode": None},
        ]

    sbc_dict = {p: usd_to_m(_extract_multi_source_val(fs, "cashflow", _SBC_KEYS, p, "stock_based_compensation")) for p in target_fys}
    fcf_adj_sbc = {p: (round(fcf_d[p] - (sbc_dict[p] or 0.0), 1) if fcf_d.get(p) is not None else None) for p in target_fys}
    owner_fcf_m = {p: (round(fcf_adj_sbc[p] / rev_d[p] * 100.0, 1) if (fcf_adj_sbc.get(p) is not None and rev_d.get(p) and rev_d[p] > 0) else None) for p in target_fys}
    capex_d = {p: usd_to_m(canonical.get("capital_expenditures", {}).get(p) or cf_data.get("capex", {}).get(p)) for p in target_fys}
    capex_int = {p: (round(abs(capex_d[p]) / rev_d[p] * 100.0, 1) if (capex_d.get(p) is not None and rev_d.get(p) and rev_d[p] > 0) else None) for p in target_fys}

    sh_ret_d, div_ret_d, bb_ret_d, alloc_r_d = {}, {}, {}, {}
    for p in target_fys:
        bb_m = usd_to_m(cap_flows.get("share_repurchases_open_market", {}).get(p))
        dv_m = usd_to_m(cap_flows.get("dividends_paid", {}).get(p))
        sh_ret_d[p] = round((bb_m or 0.0) + (dv_m or 0.0), 1) if (bb_m is not None or dv_m is not None) else None
        ret_v = sh_ret_d[p]
        if ret_v and ret_v > 0:
            div_ret_d[p] = round(abs(dv_m or 0.0) / ret_v * 100.0, 1)
            bb_ret_d[p] = round(abs(bb_m or 0.0) / ret_v * 100.0, 1)
            alloc_r_d[p] = round(abs(capex_d.get(p) or 0.0) / ret_v, 2)
        else:
            div_ret_d[p] = bb_ret_d[p] = alloc_r_d[p] = None

    return [
        {"label": "FLUJO DE CAJA LIBRE (FCF)", "orig_tooltip": "Free Cash Flow ($M)", "clarification": "Flujo de Caja Operativo (CFO) − Inversiones CapEx", "operator": "[⚡]", "row_type": "metric", "indent": False, "is_bold": True, "data": fcf_d, "pct_mode": "rev"},
        {"label": "FCF AJUSTADO POR SBC (OWNER FCF)", "orig_tooltip": "SBC-Adjusted Free Cash Flow ($M)", "clarification": "FCF − Compensación Basada en Acciones (SBC)", "operator": "[⚡]", "row_type": "metric", "indent": False, "is_bold": True, "data": fcf_adj_sbc, "pct_mode": "rev"},
        {"label": "MARGEN FCF (%)", "orig_tooltip": "FCF Margin (%)", "clarification": "FCF / Ingresos Totales", "operator": "[%]", "row_type": "metric_pct", "indent": True, "is_bold": False, "data": {p: round(fcf_d[p] / rev_d[p] * 100.0, 1) if (fcf_d.get(p) is not None and rev_d.get(p) and rev_d[p] > 0) else None for p in target_fys}, "pct_mode": None},
        {"label": "MARGEN OWNER FCF (%)", "orig_tooltip": "Owner FCF Margin (% of Revenue)", "clarification": "FCF Ajustado por SBC / Ingresos Totales", "operator": "[%]", "row_type": "metric_pct", "indent": True, "is_bold": False, "data": owner_fcf_m, "pct_mode": None},
        {"label": "CONVERSIÓN FCF (%)", "orig_tooltip": "FCF Conversion Ratio (%)", "clarification": "FCF / Beneficio Neto", "operator": "[%]", "row_type": "metric_pct", "indent": True, "is_bold": False, "data": {p: round(fcf_d[p] / ni_d[p] * 100.0, 1) if (fcf_d.get(p) is not None and ni_d.get(p) and ni_d[p] > 0) else None for p in target_fys}, "pct_mode": None},
        {"label": "INTENSIDAD CAPEX (% S/ VENTAS)", "orig_tooltip": "CapEx Intensity (% of Revenue)", "clarification": "Inversiones CapEx / Ingresos Totales", "operator": "[%]", "row_type": "metric_pct", "indent": True, "is_bold": False, "data": capex_int, "pct_mode": None},
        {"label": "RETORNO TOTAL EN EFECTIVO AL ACCIONISTA", "orig_tooltip": "Total Cash Returned to Shareholders ($M)", "clarification": "Recompras de Acciones en Mercado Abierto + Dividendos en Efectivo", "operator": "[⚡]", "row_type": "metric", "indent": False, "is_bold": True, "data": sh_ret_d, "pct_mode": "rev"},
        {"label": "DIVIDENDOS PAGADOS (% CASH RET.)", "orig_tooltip": "Dividends (% of Cash Returned)", "clarification": "Dividendos en Efectivo / Retorno Total en Efectivo", "operator": "[%]", "row_type": "metric_pct", "indent": True, "is_bold": False, "data": div_ret_d, "pct_mode": None},
        {"label": "RECOMPRA DE ACCIONES (% CASH RET.)", "orig_tooltip": "Share Repurchases (% of Cash Returned)", "clarification": "Recompras de Acciones / Retorno Total en Efectivo", "operator": "[%]", "row_type": "metric_pct", "indent": True, "is_bold": False, "data": bb_ret_d, "pct_mode": None},
        {"label": "RATIO DE ASIGNACIÓN (REINVERSIÓN VS RETORNO)", "orig_tooltip": "Capital Allocation Ratio (CapEx / Shareholder Return)", "clarification": "CapEx / Retorno Total en Efectivo al Accionista (>1.0x = reinversión expansiva)", "operator": "[x]", "row_type": "multiple", "indent": True, "is_bold": False, "data": alloc_r_d, "pct_mode": None},
    ]


def _build_balancesheet_memo(target_fys, fs, archetype, canonical, key_ratios, enriched, bs_data, pnl_data):
    bs_det = fs.get("balance_sheet_detail", {})
    if archetype == "FINANCIAL_BANKING":
        cet1_d = {p: _compute_banking_rotce_or_cet1(p, "cet1", key_ratios, pnl_data, bs_data, canonical, bs_det) for p in target_fys}
        npl_d = {p: (key_ratios.get("npl_ratio_pct", {}).get(p) or (enriched.get("npl_90_plus_pct") if p == "LTM" else None) or key_ratios.get("cost_of_risk_loans_pct", {}).get(p)) for p in target_fys}
        liq_d = {p: usd_to_m(bs_data.get("total_liquid_cash", {}).get(p)) for p in target_fys}
        rows = [
            {"label": "RATIO DE CAPITAL BANCARIO CET1 (%)", "orig_tooltip": "Common Equity Tier 1 Ratio (%)", "clarification": "Capital Principal Nivel 1 / Activos Ponderados por Riesgo", "operator": "[%]", "row_type": "metric_pct", "indent": False, "is_bold": True, "data": cet1_d, "pct_mode": None},
            {"label": "RATIO DE MOROSIDAD (NPL %)", "orig_tooltip": "Non-Performing Loans Ratio (%)", "clarification": "Créditos Dudosos / Total Cartera Crediticia Bruta", "operator": "[%]", "row_type": "metric_pct", "indent": True, "is_bold": False, "data": npl_d, "pct_mode": None},
            {"label": "LIQUIDEZ REGULATORIA INMEDIATA", "orig_tooltip": "Regulatory Liquid Cash ($M)", "clarification": "Efectivo en Bancos Centrales + Inversiones Líquidas Negociables", "operator": "[⚡]", "row_type": "metric", "indent": False, "is_bold": True, "data": liq_d, "pct_mode": "assets"},
        ]
    elif archetype == "INSURANCE":
        inv_tot_d = {p: usd_to_m(canonical.get("total_investments", {}).get(p) or bs_data.get("short_term_investments", {}).get(p)) for p in target_fys}
        eq_d = {p: usd_to_m(canonical.get("stockholders_equity", {}).get(p) or bs_data.get("stockholders_equity", {}).get(p)) for p in target_fys}
        rows = [
            {"label": "CARTERA TOTAL DE INVERSIONES", "orig_tooltip": "Total Investment Portfolio ($M)", "clarification": "Activos Financieros en Renta Fija y Renta Variable", "operator": "[⚡]", "row_type": "metric", "indent": False, "is_bold": True, "data": inv_tot_d, "pct_mode": "assets"},
            {"label": "SOLVENCIA PATRIMONIAL (EQUITY)", "orig_tooltip": "Stockholders Equity ($M)", "clarification": "Patrimonio Neto de los Accionistas", "operator": "[⚡]", "row_type": "metric", "indent": False, "is_bold": True, "data": eq_d, "pct_mode": "assets"},
        ]
    elif archetype == "REAL_ESTATE_REIT":
        ppe_d = {p: usd_to_m(bs_data.get("net_ppe", {}).get(p)) for p in target_fys}
        debt_d = {p: usd_to_m(bs_data.get("total_debt", {}).get(p)) for p in target_fys}
        ast_d = {p: usd_to_m(bs_data.get("total_assets", {}).get(p)) for p in target_fys}
        ltv_d = {p: round(debt_d[p] / ast_d[p] * 100.0, 1) if (debt_d.get(p) and ast_d.get(p) and ast_d[p] > 0) else None for p in target_fys}
        rows = [
            {"label": "INVERSIONES INMOBILIARIAS NETAS (PP&E)", "orig_tooltip": "Net Real Estate Portfolio ($M)", "clarification": "Cartera de Inmuebles en Explotación neta de depreciación", "operator": "[⚡]", "row_type": "metric", "indent": False, "is_bold": True, "data": ppe_d, "pct_mode": "assets"},
            {"label": "DEUDA FINANCIERA INMOBILIARIA TOTAL", "orig_tooltip": "Total Real Estate Debt ($M)", "clarification": "Deuda Hipotecaria + Préstamos a Plazo + Bonos", "operator": "[⚡]", "row_type": "metric", "indent": False, "is_bold": True, "data": debt_d, "pct_mode": "assets"},
            {"label": "RATIO LTV (DEUDA / ACTIVOS %)", "orig_tooltip": "Loan-to-Value Ratio (%)", "clarification": "Deuda Total / Activos Inmobiliarios Totales", "operator": "[%]", "row_type": "metric_pct", "indent": True, "is_bold": False, "data": ltv_d, "pct_mode": None},
        ]
    else:
        st_d = {p: usd_to_m(bs_data.get("short_term_debt", {}).get(p)) for p in target_fys}
        lt_d = {p: usd_to_m(bs_data.get("long_term_debt", {}).get(p)) for p in target_fys}
        tot_d = {p: (round((st_d.get(p) or 0.0) + (lt_d.get(p) or 0.0), 1) if (st_d.get(p) is not None or lt_d.get(p) is not None) else None) for p in target_fys}
        rows = [
            {"label": "LIQUIDEZ INMEDIATA TOTAL", "orig_tooltip": "Total Liquid Cash ($M)", "clarification": "Efectivo y Equivalentes + Inversiones Negociables CP", "operator": "[⚡]", "row_type": "metric", "indent": False, "is_bold": True, "data": {p: usd_to_m(bs_data.get("total_liquid_cash", {}).get(p)) for p in target_fys}, "pct_mode": "assets"},
            {"label": "DEUDA FINANCIERA TOTAL", "orig_tooltip": "Total Financial Debt ($M)", "clarification": "Deuda Financiera CP + LP (excluyendo pasivos operativos)", "operator": "[⚡]", "row_type": "metric", "indent": False, "is_bold": True, "data": tot_d, "pct_mode": "assets"},
            {"label": "POSICIÓN FINANCIERA NETA (DEUDA NETA)", "orig_tooltip": "Net Financial Position ($M)", "clarification": "Deuda Total − Liquidez Inmediata Total", "operator": "[⚡]", "row_type": "net_debt", "indent": False, "is_bold": True, "data": {p: usd_to_m(bs_data.get("net_financial_position", {}).get(p)) for p in target_fys}, "pct_mode": "assets"},
            {"label": "FONDO DE MANIOBRA (NET WORKING CAPITAL)", "orig_tooltip": "Net Working Capital ($M)", "clarification": "Activo Corriente − Pasivo Corriente", "operator": "[⚡]", "row_type": "metric", "indent": False, "is_bold": True, "data": {p: usd_to_m(bs_data.get("net_working_capital", {}).get(p)) for p in target_fys}, "pct_mode": "assets"},
        ]
    rows.extend([
        {"label": "VALOR CONTABLE POR ACCIÓN (BVPS $)", "orig_tooltip": "Book Value Per Share ($/acción)", "clarification": "Patrimonio Neto / Acciones Diluidas", "operator": "[⚡]", "row_type": "eps", "indent": False, "is_bold": True, "data": {p: bs_data.get("book_value_per_share", {}).get(p) for p in target_fys}, "pct_mode": None},
        {"label": "VALOR CONTABLE TANGIBLE POR ACCIÓN (TBVPS $)", "orig_tooltip": "Tangible Book Value Per Share ($/acción)", "clarification": "(Patrimonio Neto − Fondo de Comercio e Intangibles) / Acciones Diluidas", "operator": "[⚡]", "row_type": "eps", "indent": True, "is_bold": False, "data": {p: bs_data.get("tangible_book_value_per_share", {}).get(p) for p in target_fys}, "pct_mode": None},
    ])
    return rows


def build_memo_rows(target_fys, stmt_type, fs, archetype, canonical, key_ratios, enriched, bs_data, pnl_data, cap_flows, cf_data, as_rep_cf) -> list:
    """Construye el bloque de métricas analíticas MEMO para P&L, Flujo o Balance."""
    rev_d = {p: usd_to_m(canonical.get("revenue", {}).get(p)) for p in target_fys}
    gp_d = {p: usd_to_m(canonical.get("gross_profit", {}).get(p)) for p in target_fys}
    ebit_d = {p: usd_to_m(canonical.get("operating_income", {}).get(p)) for p in target_fys}
    ni_d = {p: usd_to_m(canonical.get("net_income", {}).get(p)) for p in target_fys}
    fcf_d = {p: usd_to_m(canonical.get("free_cash_flow", {}).get(p)) for p in target_fys}

    memo = [{
        "label": "📊 MÉTRICAS ANALÍTICAS (MEMO)", "orig_tooltip": "Métricas normalizadas de rentabilidad y solvencia institucionales",
        "clarification": "Métricas adaptadas dinámicamente por arquetipo contable", "operator": "",
        "row_type": "section_header", "indent": False, "is_bold": True, "data": {p: None for p in target_fys}, "pct_mode": None,
    }]
    if stmt_type == "pnl":
        memo.extend(_build_pnl_memo(target_fys, fs, archetype, canonical, key_ratios, enriched, bs_data, pnl_data, as_rep_cf, rev_d, gp_d, ebit_d, ni_d))
    elif stmt_type == "cashflow":
        memo.extend(_build_cashflow_memo(target_fys, fs, archetype, canonical, key_ratios, bs_data, cf_data, cap_flows, rev_d, ni_d, fcf_d))
    elif stmt_type == "balancesheet":
        memo.extend(_build_balancesheet_memo(target_fys, fs, archetype, canonical, key_ratios, enriched, bs_data, pnl_data))
    return memo


def build_statements_summary(statements_fys, fs, canonical, key_ratios, archetype, is_banking, is_insurance, is_reit, is_financial, enriched, bs_data, pnl_data) -> dict:
    """Construye las tarjetas de resumen de cabecera adaptadas por arquetipo."""
    latest_p = statements_fys[0] if statements_fys else "LTM"
    bs_det, cf_det = fs.get("balance_sheet_detail", {}), fs.get("cash_flow_detail", {})

    rev_ltm_val = usd_to_m(canonical.get("revenue", {}).get(latest_p))
    gp_ltm_val = usd_to_m(canonical.get("gross_profit", {}).get(latest_p))
    ebit_ltm_val = usd_to_m(canonical.get("operating_income", {}).get(latest_p))
    ni_ltm_val = usd_to_m(canonical.get("net_income", {}).get(latest_p))
    fcf_ltm_val = usd_to_m(canonical.get("free_cash_flow", {}).get(latest_p))
    if fcf_ltm_val is None and archetype == "INSURANCE":
        cfo_v, cx_v = canonical.get("cash_from_operations", {}).get(latest_p), canonical.get("capital_expenditures", {}).get(latest_p)
        if cfo_v is not None and cx_v is not None:
            fcf_ltm_val = usd_to_m(float(cfo_v) - abs(float(cx_v)))

    if is_banking:
        nd_ltm_val = cr_val = None
    else:
        nd_ltm_val = usd_to_m(bs_data.get("net_financial_position", {}).get(latest_p))
        ca_val = usd_to_m(bs_data.get("total_current_assets", {}).get(latest_p) or canonical.get("current_assets", {}).get(latest_p))
        cl_val = usd_to_m(bs_data.get("total_current_liabilities", {}).get(latest_p) or canonical.get("current_liabilities", {}).get(latest_p))
        cr_val = round(ca_val / cl_val, 2) if (ca_val and cl_val and cl_val != 0) else key_ratios.get("current_ratio", {}).get(latest_p)
    eq_ltm_val = usd_to_m(bs_data.get("stockholders_equity", {}).get(latest_p) or canonical.get("stockholders_equity", {}).get(latest_p))

    if is_banking:
        nim_val = key_ratios.get("nim_pct", {}).get(latest_p) or key_ratios.get("risk_adj_nim_pct", {}).get(latest_p) or enriched.get("risk_adjusted_nim_pct")
        eff_val = key_ratios.get("efficiency_ratio_pct", {}).get(latest_p) or enriched.get("efficiency_ratio_pct")
        roe_val = key_ratios.get("roe_pct", {}).get(latest_p) or enriched.get("return_on_equity_reported")
        rotce_val = _compute_banking_rotce_or_cet1(latest_p, "rotce", key_ratios, pnl_data, bs_data, canonical, bs_det, roe_fallback=roe_val)
        cet1_val = enriched.get("cet1_ratio_pct") or _compute_banking_rotce_or_cet1(latest_p, "cet1", key_ratios, pnl_data, bs_data, canonical, bs_det)
        npl_cov_val = _compute_npl_coverage(latest_p, key_ratios, enriched, bs_data, pnl_data, canonical, bs_det)
        npl_ratio_val = key_ratios.get("npl_ratio_pct", {}).get(latest_p) or enriched.get("npl_90_plus_pct") or key_ratios.get("cost_of_risk_loans_pct", {}).get(latest_p)
    else:
        nim_val = eff_val = rotce_val = cet1_val = npl_cov_val = npl_ratio_val = None
        roe_val = key_ratios.get("roe_pct", {}).get(latest_p)

    if is_insurance:
        comb_val = key_ratios.get("combined_ratio_pct", {}).get(latest_p) or canonical.get("combined_ratio", {}).get(latest_p)
        loss_val = key_ratios.get("loss_ratio_pct", {}).get(latest_p) or canonical.get("loss_ratio", {}).get(latest_p)
        exp_val = key_ratios.get("expense_ratio_pct", {}).get(latest_p) or canonical.get("expense_ratio", {}).get(latest_p)
        inv_y_val = _compute_insurance_inv_yield(latest_p, key_ratios, canonical, pnl_data, bs_data)
        net_prem_val = usd_to_m(canonical.get("net_premiums_earned", {}).get(latest_p)) or rev_ltm_val
        float_val = usd_to_m(canonical.get("float_usd", {}).get(latest_p))
        tot_inv_val = usd_to_m(canonical.get("total_investments", {}).get(latest_p) or bs_data.get("short_term_investments", {}).get(latest_p))
    else:
        comb_val = loss_val = exp_val = inv_y_val = net_prem_val = float_val = tot_inv_val = None

    if is_reit:
        rental_val = usd_to_m(canonical.get("rental_revenue", {}).get(latest_p)) or rev_ltm_val
        noi_val = usd_to_m(canonical.get("noi", {}).get(latest_p))
        ffo_val = usd_to_m(canonical.get("ffo", {}).get(latest_p))
        affo_val = usd_to_m(canonical.get("affo", {}).get(latest_p))
        sh_cnt = canonical.get("shares_diluted", {}).get(latest_p) or canonical.get("weighted_average_shares_diluted", {}).get(latest_p)
        ffo_sh_val = round(float(canonical.get("ffo", {}).get(latest_p)) / float(sh_cnt), 2) if (ffo_val and sh_cnt and float(sh_cnt) > 0) else None
        affo_sh_val = round(float(canonical.get("affo", {}).get(latest_p)) / float(sh_cnt), 2) if (affo_val and sh_cnt and float(sh_cnt) > 0) else None
        div_paid = abs(canonical.get("dividends_paid", {}).get(latest_p) or detail_num(cf_det, "PaymentsOfDividendsCommonStock", latest_p) or detail_num(cf_det, "PaymentsOfDividends", latest_p) or 0.0)
        payout_affo_val = round(div_paid / float(canonical.get("affo", {}).get(latest_p)) * 100.0, 1) if (affo_val and div_paid > 0) else None
        tot_debt_val = usd_to_m(canonical.get("total_debt", {}).get(latest_p))
        tot_assets_val = usd_to_m(canonical.get("total_assets", {}).get(latest_p))
        ltv_val = round(tot_debt_val / tot_assets_val * 100.0, 1) if (tot_debt_val and tot_assets_val and tot_assets_val > 0) else None
    else:
        rental_val = noi_val = ffo_val = affo_val = ffo_sh_val = affo_sh_val = payout_affo_val = ltv_val = None

    return {
        "archetype": archetype, "is_financial": is_financial,
        "rev_ltm": fmt_money_m(rev_ltm_val),
        "gm_ltm": f"{round(gp_ltm_val / rev_ltm_val * 100.0, 1)}%" if (gp_ltm_val and rev_ltm_val) else "-",
        "om_ltm": f"{round(ebit_ltm_val / rev_ltm_val * 100.0, 1)}%" if (ebit_ltm_val and rev_ltm_val) else "-",
        "fcf_ltm": fmt_money_m(fcf_ltm_val),
        "fcf_margin_ltm": f"{round(fcf_ltm_val / rev_ltm_val * 100.0, 1)}%" if (fcf_ltm_val and rev_ltm_val) else "-",
        "fcf_conv_ltm": f"{round(fcf_ltm_val / ni_ltm_val * 100.0, 1)}%" if (fcf_ltm_val and ni_ltm_val) else "-",
        "net_debt_display": fmt_money_m(abs(nd_ltm_val)) if (nd_ltm_val and nd_ltm_val < 0) else fmt_money_m(nd_ltm_val),
        "net_debt_is_cash": (nd_ltm_val is not None and nd_ltm_val < 0),
        "current_ratio": f"{cr_val:.2f}x" if cr_val else "-",
        "equity_ltm": fmt_money_m(eq_ltm_val), "net_income_ltm": fmt_money_m(ni_ltm_val),
        "net_margin_ltm": f"{round(ni_ltm_val / rev_ltm_val * 100.0, 1)}%" if (ni_ltm_val and rev_ltm_val) else "-",
        "nim_ltm": f"{nim_val:.2f}%" if nim_val is not None else "-",
        "cost_to_income": f"{eff_val:.1f}%" if eff_val is not None else "-",
        "roe_ltm": f"{roe_val:.1f}%" if roe_val is not None else (f"{round(ni_ltm_val / eq_ltm_val * 100.0, 1)}%" if (ni_ltm_val and eq_ltm_val and eq_ltm_val > 0) else "-"),
        "rotce_ltm": f"{rotce_val:.1f}%" if rotce_val is not None else "-",
        "cet1_ratio": f"{cet1_val:.1f}%" if cet1_val is not None else "-",
        "npl_coverage": f"{npl_cov_val:.1f}%" if npl_cov_val is not None else "-",
        "npl_ratio": f"{npl_ratio_val:.1f}%" if npl_ratio_val is not None else "-",
        "net_premiums_ltm": fmt_money_m(net_prem_val) if is_insurance else "-",
        "combined_ratio": f"{comb_val:.1f}%" if comb_val is not None else "-",
        "loss_ratio": f"{loss_val:.1f}%" if loss_val is not None else "-",
        "expense_ratio": f"{exp_val:.1f}%" if exp_val is not None else "-",
        "inv_yield": f"{inv_y_val:.1f}%" if inv_y_val is not None else "-",
        "float_usd": fmt_money_m(float_val) if is_insurance else "-",
        "total_investments": fmt_money_m(tot_inv_val) if is_insurance else "-",
        "rental_rev_ltm": fmt_money_m(rental_val) if is_reit else "-",
        "noi_ltm": fmt_money_m(noi_val) if is_reit else "-",
        "noi_margin": f"{round(noi_val / rev_ltm_val * 100.0, 1)}%" if (noi_val and rev_ltm_val) else "-",
        "ffo_ltm": fmt_money_m(ffo_val) if is_reit else "-",
        "ffo_margin": f"{round(ffo_val / rev_ltm_val * 100.0, 1)}%" if (ffo_val and rev_ltm_val) else "-",
        "affo_ltm": fmt_money_m(affo_val) if is_reit else "-",
        "ffo_per_share": f"${ffo_sh_val:.2f}" if ffo_sh_val is not None else "-",
        "affo_per_share": f"${affo_sh_val:.2f}" if affo_sh_val is not None else "-",
        "payout_affo": f"{payout_affo_val:.1f}%" if payout_affo_val is not None else "-",
        "ltv_ratio": f"{ltv_val:.1f}%" if ltv_val is not None else "-",
    }


def build_legacy_table_pnl(fys: list, canonical: dict) -> list:
    """Conserva table_pnl por retrocompatibilidad con vistas previas."""
    pnl_defs = [
        ("Ingresos Netos (Revenue)", "revenue", True), ("Coste de Bienes Vendidos (COGS)", "cost_of_goods_sold", False),
        ("Margen Bruto (Gross Profit)", "gross_profit", True), ("Gastos Operativos (OpEx)", "operating_expenses", False),
        ("Beneficio Operativo (EBIT)", "operating_income", True), ("Beneficio Neto (Net Income)", "net_income", True),
        ("Flujo de Caja Operativo (CFO)", "cash_from_operations", True), ("Inversiones en CapEx", "capital_expenditures", False),
        ("Flujo de Caja Libre (FCF)", "free_cash_flow", True), ("Efectivo y Equivalentes", "cash_and_equivalents", False),
        ("Deuda Financiera Total", "total_debt", False), ("Deuda Neta", "net_debt", False),
        ("Activos Totales", "total_assets", True), ("Patrimonio Neto (Equity)", "stockholders_equity", True),
        ("BPA Diluido Normalizado (Split-Adjusted) ($)", "eps_diluted_adjusted", True),
        ("BPA Diluido Oficial As-Reported (SEC) ($)", "eps_diluted", False),
    ]
    out = []
    for label, key, is_bold in pnl_defs:
        d_dict = canonical.get(key, {})
        if key == "eps_diluted_adjusted" and not d_dict:
            d_dict = canonical.get("eps_diluted", {})
        row_vals = []
        for p in fys:
            v = d_dict.get(p)
            if v is None:
                val_str = "-"
            elif key in ("eps_diluted", "eps_diluted_adjusted"):
                val_str = f"-${abs(v):.2f}" if v < 0 else f"${v:.2f}"
            else:
                prefix = "-$" if v < 0 else "$"
                scale_val = abs(v)
                val_str = f"{prefix}{scale_val / 1e6:,.1f}M" if scale_val >= 1e6 else (f"{prefix}{scale_val:,.1f}M" if scale_val > 0 else "$0.0M")
            row_vals.append(val_str)
        out.append({"label": label, "is_bold": is_bold, "values": row_vals})
    return out
