# -*- coding: utf-8 -*-
"""
Esquemas declarativos de Estados Financieros Estandarizados por arquetipo contable:
Banca (FINANCIAL_BANKING), Aseguradoras (INSURANCE), REIT (REAL_ESTATE_REIT) y Corporativo/Plataforma.
"""

_EPS_AND_SHARES_SECTION = (
    "MÉTRICAS POR ACCIÓN Y ACCIONES EN CIRCULACIÓN",
    [
        ("BPA Básico (Basic EPS)", "eps_basic", "", "eps", False, False, False, True, None, "Basic EPS"),
        ("BPA Diluido Normalizado (Diluted EPS)", "eps_diluted", "", "eps", False, True, False, True, None, "Diluted EPS"),
        ("Acciones Básicas Promedio Ponderado (M)", "shares_basic", "", "shares", True, False, False, True, None, "Weighted Average Shares Basic"),
        ("Acciones Diluidas Promedio Ponderado (M)", "shares_diluted", "", "shares", True, True, False, True, None, "Weighted Average Shares Diluted"),
        ("Dividendos por Acción (DPS)", "dps", "", "dps", True, False, False, False, None, "Dividends Per Share"),
    ],
)

_FINANCIAL_EQUITY_BS_SECTION = (
    "PATRIMONIO NETO (SHAREHOLDERS' EQUITY)",
    [
        ("Capital Social y Prima de Emisión (Common Stock & APIC)", "common_stock_and_apic", "[+]", "item", True, False, False, True, "assets", "Common Stock & APIC"),
        ("Ganancias Retenidas / (Déficit Acumulado)", "retained_earnings", "[+]", "item", True, False, False, True, "assets", "Retained Earnings"),
        ("Acciones en Tesorería, AOCI y Otros Fondos Propios", "other_equity", "[±]", "item", True, False, False, True, "assets", "Treasury Stock & AOCI"),
        ("Intereses Minoritarios (Noncontrolling Interests)", "minority_interest", "[+]", "item", True, False, False, False, "assets", "Noncontrolling Interests"),
        ("Patrimonio Temporal / Mezzanine (Redeemable NCI)", "mezzanine_equity", "[+]", "item", True, False, False, False, "assets", "Mezzanine Equity (Redeemable NCI)"),
        ("Total Patrimonio Neto (Stockholders' Equity)", "stockholders_equity", "[=]", "result", False, True, False, True, "assets", "Total Stockholders Equity"),
        ("Total Pasivo y Patrimonio Neto (Total Liabilities & Equity)", "total_liab_and_equity", "[=]", "result", False, True, False, True, "assets", "Total Liabilities and Equity"),
    ],
)


def get_pnl_sections(archetype: str) -> list:
    """Retorna la definición de filas del Estado de Resultados para el arquetipo indicado."""
    if archetype == "FINANCIAL_BANKING":
        return [
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
            _EPS_AND_SHARES_SECTION,
        ]
    if archetype == "INSURANCE":
        return [
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
            _EPS_AND_SHARES_SECTION,
        ]
    if archetype == "REAL_ESTATE_REIT":
        return [
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
            _EPS_AND_SHARES_SECTION,
        ]
    return [
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
        _EPS_AND_SHARES_SECTION,
    ]


def get_cashflow_sections(archetype: str, cf_data: dict) -> list:
    """Retorna la definición de filas del Estado de Flujos de Caja para el arquetipo."""
    if archetype == "FINANCIAL_BANKING":
        cf_op_items = [
            ("Beneficio Neto Consolidado (Net Income)", "net_income", "[+]", "subtotal", False, True, False, True, "ni", "Net Income"),
            ("Depreciación y Amortización (D&A)", "da", "[+]", "item", True, False, False, True, "ni", "Depreciation & Amortization"),
            ("Compensación Basada en Acciones (SBC)", "sbc", "[+]", "item", True, False, False, False, "ni", "Share-Based Compensation"),
            ("Impuestos sobre Beneficios Diferidos (Deferred Taxes)", "deferred_taxes", "[±]", "item", True, False, False, False, "ni", "Deferred Income Taxes"),
            ("Variación Neta en Depósitos de Clientes", "banking_deposits_cf", "[±]", "item", True, False, False, True, "ni", "Net Change in Customer Deposits"),
            ("Variación Neta en Préstamos y Cartera de Crédito", "banking_loans_cf", "[±]", "item", True, False, False, True, "ni", "Net Change in Customer Loans & Receivables"),
            ("Otros Ajustes Operativos No Monetarios", "other_noncash", "[±]", "item", True, False, False, False, "ni", "Other Banking Operating and Non-Cash Adjustments"),
            ("Flujo de Caja Operativo (CFO)", "cfo", "[=]", "result", False, True, False, True, "ni", "Cash Provided by Operating Activities"),
        ]
    else:
        cf_op_items = [
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
        ]

    has_capex = any(cf_data.get("capex", {}).get(k) is not None for k in cf_data.get("capex", {}))
    return [
        ("ACTIVIDADES OPERATIVAS (OPERATING ACTIVITIES)", cf_op_items),
        ("ACTIVIDADES DE INVERSIÓN (INVESTING ACTIVITIES)", [
            ("Inversiones en Inmovilizado / CapEx", "capex", "[-]", "item", True, False, True, (archetype not in ("FINANCIAL_BANKING", "INSURANCE") or has_capex), "ni", "Capital Expenditures"),
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
        ]),
    ]


def get_balance_sheet_sections(archetype: str) -> list:
    """Retorna la definición de filas del Balance General para el arquetipo indicado."""
    if archetype == "FINANCIAL_BANKING":
        return [
            ("ACTIVOS BANCARIOS Y CARTERA CREDITICIA", [
                ("Efectivo y Depósitos en Bancos Centrales", "cash", "[+]", "item", True, False, False, True, "assets", "Cash and Due from Banks"),
                ("Inversiones Financieras y Valores Negociables", "short_term_investments", "[+]", "item", True, False, False, True, "assets", "Trading and Investment Securities"),
                ("Tesorería e Inversiones Líquidas Totales", "total_liquid_cash", "[=]", "subtotal", False, True, False, True, "assets", "Total Liquid Assets"),
                ("Cartera de Préstamos y Crédito Neta (Net Loans)", "net_loans", "[+]", "item", True, False, False, True, "assets", "Loans and Leases Net of Allowance"),
                ("Provisión Acumulada para Pérdidas Crediticias (Allowance)", "allowance_for_loan_losses", "[-]", "item", True, False, True, True, "assets", "Allowance for Loan Losses"),
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
            _FINANCIAL_EQUITY_BS_SECTION,
        ]
    if archetype == "INSURANCE":
        return [
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
            _FINANCIAL_EQUITY_BS_SECTION,
        ]

    ppe_title = (
        "Propiedades Inmobiliarias Netas (Real Estate Net)" if archetype == "REAL_ESTATE_REIT"
        else "Inmovilizado Material Neto (PP&E Neto)"
    )
    return [
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
            ("Patrimonio Temporal / Mezzanine (Redeemable NCI)", "mezzanine_equity", "[+]", "item", True, False, False, False, "assets", "Mezzanine Equity (Redeemable NCI)"),
            ("Total Patrimonio Neto (Stockholders' Equity)", "stockholders_equity", "[=]", "result", False, True, False, True, "assets", "Total Stockholders Equity"),
            ("Total Pasivo y Patrimonio Neto (Total Liabilities & Equity)", "total_liab_and_equity", "[=]", "result", False, True, False, True, "assets", "Total Liabilities & Stockholders Equity"),
        ]),
    ]
