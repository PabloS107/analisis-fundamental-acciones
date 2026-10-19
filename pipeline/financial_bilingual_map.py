"""
financial_bilingual_map.py - Diccionario institucional y motor de clarificaciones bilingües
para estados financieros oficiales presentados ante la SEC (US-GAAP / IFRS).

Provee la traducción técnica y conceptual al español para las partidas contables
respetando el nombre oficial en inglés de la presentación (Filing Presentation).
"""

import re

# Diccionario exhaustivo de clarificaciones contables oficiales
SPANISH_CLARIFICATIONS = {
    # =========================================================================
    # 1. ESTADO DE RESULTADOS (INCOME STATEMENT / STATEMENT OF OPERATIONS)
    # =========================================================================
    # Ingresos / Ventas
    "net sales": "Ventas netas",
    "total net sales": "Ventas netas totales",
    "revenue": "Ingresos totales",
    "total revenues": "Ingresos totales",
    "total revenue": "Ingresos totales",
    "revenues": "Ingresos totales",
    "sales revenue": "Ingresos por ventas",
    "product revenue": "Ingresos por productos",
    "service revenue": "Ingresos por servicios",
    "subscription revenue": "Ingresos por suscripciones",
    "products": "Productos",
    "services": "Servicios",
    "iphone": "Línea iPhone",
    "mac": "Línea Mac",
    "ipad": "Línea iPad",
    "wearables, home and accessories": "Dispositivos portátiles, hogar y accesorios",
    "data center": "Centro de datos (Data Center)",
    "gaming": "Línea Gaming",
    "professional visualization": "Visualización profesional",
    "automotive": "Sector automotriz",
    "oem and other": "OEM y otros",
    
    # Costos y Margen Bruto
    "cost of sales": "Costo de ventas",
    "total cost of sales": "Costo de ventas total",
    "cost of goods and services sold": "Costo de bienes y servicios vendidos",
    "cost of goods sold": "Costo de bienes vendidos (COGS)",
    "cost of revenue": "Costo de ingresos",
    "total cost of revenue": "Costo total de ingresos",
    "gross margin": "Margen bruto",
    "gross profit": "Utilidad bruta",
    
    # Gastos Operativos (OpEx)
    "operating expenses:": "Gastos operativos:",
    "operating expenses": "Gastos operativos",
    "total operating expenses": "Total gastos operativos",
    "research and development": "Investigación y desarrollo (I+D)",
    "selling, general and administrative": "Gastos de venta, generales y admin. (SG&A)",
    "selling and marketing": "Ventas y marketing",
    "general and administrative": "Gastos generales y administrativos (G&A)",
    "marketing": "Gastos de marketing",
    "restructuring charges": "Cargos por reestructuración",
    "amortization of intangible assets": "Amortización de intangibles",
    "impairment of goodwill": "Deterioro de fondo de comercio",
    "other operating income (expense), net": "Otros ingresos / (gastos) operativos netos",
    
    # Resultados Operativos y Financieros
    "operating income": "Resultado operativo (EBIT)",
    "operating income (loss)": "Resultado operativo (EBIT)",
    "operating profit": "Resultado operativo (EBIT)",
    "income from operations": "Resultado de operaciones (EBIT)",
    "total other income/(expense), net": "Total otros ingresos / (gastos) netos",
    "other income/(expense), net": "Otros ingresos / (gastos) no operativos netos",
    "other income (expense), net": "Otros ingresos / (gastos) no operativos netos",
    "interest income": "Ingresos por intereses",
    "interest expense": "Gastos por intereses",
    "interest expense, net": "Gastos netos por intereses",
    "interest and dividend income": "Ingresos por intereses y dividendos",
    "non-operating income (expense)": "Ingresos / (gastos) no operativos",
    
    # EBT, Impuestos y Utilidad Neta
    "income before provision for income taxes": "Resultado antes de impuestos (EBT)",
    "income before income taxes": "Resultado antes de impuestos (EBT)",
    "income (loss) before income taxes": "Resultado antes de impuestos (EBT)",
    "provision for income taxes": "Provisión para impuesto a las ganancias",
    "income tax expense (benefit)": "Gasto / (beneficio) por impuesto a las ganancias",
    "income tax expense": "Impuesto a las ganancias",
    "net income": "Utilidad neta consolidada",
    "net income (loss)": "Utilidad / (pérdida) neta consolidada",
    "net income attributable to common shareholders": "Utilidad neta para accionistas comunes",
    "net earnings": "Utilidad neta",
    
    # Ratios por Acción
    "earnings per share:": "Ganancia por acción:",
    "earnings per share": "Ganancia por acción:",
    "basic (in dollars per share)": "EPS básico ($/acc)",
    "diluted (in dollars per share)": "EPS diluido ($/acc)",
    "basic": "Básico",
    "diluted": "Diluido",
    "shares used in computing earnings per share:": "Acciones usadas en el cálculo de EPS:",
    "shares used in computing per share amounts:": "Acciones usadas en el cálculo de EPS:",
    "basic (in shares)": "Acciones básicas en circulación",
    "diluted (in shares)": "Acciones diluidas en circulación",
    "weighted average shares outstanding": "Promedio ponderado de acciones",

    # =========================================================================
    # 2. BALANCE GENERAL (BALANCE SHEET / FINANCIAL POSITION)
    # =========================================================================
    # Activos Generales y Corrientes
    "assets:": "ACTIVOS:",
    "assets": "ACTIVOS",
    "current assets:": "Activos corrientes:",
    "current assets": "Activos corrientes",
    "total current assets": "Total activos corrientes",
    "cash and cash equivalents": "Efectivo y equivalentes de efectivo",
    "cash, cash equivalents and restricted cash": "Efectivo, equivalentes y caja restringida",
    "short-term marketable securities": "Inversiones líquidas negociables a corto plazo",
    "marketable securities": "Valores negociables / Inversiones líquidas",
    "accounts receivable, net": "Cuentas por cobrar comerciales netas",
    "accounts receivable": "Cuentas por cobrar comerciales",
    "vendor non-trade receivables": "Cuentas por cobrar no comerciales a proveedores",
    "inventories": "Inventarios / Existencias",
    "inventory": "Inventarios / Existencias",
    "prepaid expenses and other current assets": "Gastos pagados por anticipado y otros activos ctes.",
    "other current assets": "Otros activos corrientes",
    
    # Activos No Corrientes
    "non-current assets:": "Activos no corrientes:",
    "non-current assets": "Activos no corrientes",
    "total non-current assets": "Total activos no corrientes",
    "property, plant and equipment, net": "Propiedad, planta y equipo (PP&E neto)",
    "property, plant and equipment": "Propiedad, planta y equipo (PP&E)",
    "operating lease right-of-use assets": "Activos por derecho de uso de arrendamiento (ROU)",
    "goodwill": "Fondo de comercio (Goodwill)",
    "intangible assets, net": "Activos intangibles netos",
    "deferred income tax assets": "Activos por impuestos diferidos",
    "other non-current assets": "Otros activos no corrientes",
    "total assets": "ACTIVOS TOTALES",
    
    # Pasivos Corrientes
    "liabilities and shareholders’ equity:": "PASIVOS Y PATRIMONIO NETO:",
    "liabilities and stockholders’ equity:": "PASIVOS Y PATRIMONIO NETO:",
    "liabilities and equity:": "PASIVOS Y PATRIMONIO NETO:",
    "current liabilities:": "Pasivos corrientes:",
    "current liabilities": "Pasivos corrientes",
    "total current liabilities": "Total pasivos corrientes",
    "accounts payable": "Cuentas por pagar comerciales (Proveedores)",
    "accrued expenses": "Gastos acumulados por pagar",
    "accrued and other current liabilities": "Pasivos acumulados y otros pasivos corrientes",
    "other current liabilities": "Otros pasivos corrientes",
    "deferred revenue": "Ingresos diferidos / Pasivos contractuales",
    "contract liabilities": "Pasivos por contratos con clientes",
    "commercial paper": "Pagarés comerciales (Deuda CP)",
    "short-term debt": "Deuda financiera a corto plazo",
    "current portion of long-term debt": "Porción corriente de la deuda a largo plazo",
    "operating lease liabilities, current": "Pasivo por arrendamiento operativo corriente",
    "term debt": "Deuda a plazo",
    
    # Pasivos No Corrientes
    "non-current liabilities:": "Pasivos no corrientes:",
    "non-current liabilities": "Pasivos no corrientes",
    "total non-current liabilities": "Total pasivos no corrientes",
    "long-term debt": "Deuda financiera a largo plazo",
    "long-term debt, non-current": "Deuda a largo plazo no corriente",
    "operating lease liabilities, non-current": "Pasivo por arrendamiento operativo no corriente",
    "deferred tax liabilities": "Pasivos por impuestos diferidos",
    "other non-current liabilities": "Otros pasivos no corrientes",
    "total liabilities": "TOTAL PASIVOS",
    "commitments and contingencies": "Compromisos y contingencias",
    
    # Patrimonio Neto (Equity)
    "shareholders’ equity:": "Patrimonio neto:",
    "stockholders’ equity:": "Patrimonio neto:",
    "shareholders' equity": "Patrimonio neto",
    "stockholders' equity": "Patrimonio neto",
    "common stock": "Acciones ordinarias",
    "common stock, shares outstanding (in shares)": "Acciones ordinarias en circulación",
    "common stock, shares issued (in shares)": "Acciones ordinarias emitidas",
    "common stock and additional paid-in capital": "Capital social y prima de emisión (APIC)",
    "additional paid-in capital": "Prima de emisión de acciones (APIC)",
    "retained earnings": "Ganancias retenidas",
    "retained earnings/(accumulated deficit)": "Resultados acumulados / Ganancias retenidas",
    "accumulated deficit": "Déficit acumulado",
    "accumulated other comprehensive income (loss)": "Otros resultados integrales acumulados (AOCI)",
    "accumulated other comprehensive loss": "Otros resultados integrales acumulados (AOCI)",
    "accumulated other comprehensive income/(loss)": "Otros resultados integrales acumulados (AOCI)",
    "treasury stock": "Acciones propias en cartera (Treasury Stock)",
    "total shareholders’ equity": "TOTAL PATRIMONIO NETO",
    "total stockholders’ equity": "TOTAL PATRIMONIO NETO",
    "total equity": "TOTAL PATRIMONIO NETO",
    "total liabilities and shareholders’ equity": "TOTAL PASIVO Y PATRIMONIO NETO",
    "total liabilities and stockholders’ equity": "TOTAL PASIVO Y PATRIMONIO NETO",

    # =========================================================================
    # 3. ESTADO DE FLUJOS DE CAJA (CASH FLOW STATEMENT)
    # =========================================================================
    # Actividades Operativas
    "operating activities:": "ACTIVIDADES OPERATIVAS:",
    "operating activities": "ACTIVIDADES OPERATIVAS",
    "cash flows from operating activities:": "Flujos de caja de actividades operativas:",
    "cash generated by operating activities": "FLUJO DE CAJA OPERATIVO (CFO)",
    "net cash provided by (used in) operating activities": "FLUJO DE CAJA OPERATIVO (CFO)",
    "net cash provided by operating activities": "FLUJO DE CAJA OPERATIVO (CFO)",
    "adjustments to reconcile net income to cash generated by operating activities:": "Ajustes no monetarios a la utilidad:",
    "adjustments to reconcile net income:": "Ajustes no monetarios a la utilidad:",
    "depreciation and amortization": "Depreciación y amortización",
    "share-based compensation expense": "Compensación basada en acciones (SBC)",
    "share-based compensation": "Compensación basada en acciones (SBC)",
    "stock-based compensation": "Compensación basada en acciones (SBC)",
    "deferred income taxes": "Impuestos diferidos",
    "other non-cash items": "Otros conceptos no monetarios",
    "other": "Otros ajustes no monetarios",
    
    # Cambios en Capital de Trabajo
    "changes in operating assets and liabilities:": "Variaciones de capital de trabajo:",
    "changes in assets and liabilities:": "Variaciones de activos y pasivos:",
    "other current and non-current assets": "Otros activos operativos ctes. y no ctes.",
    "other current and non-current liabilities": "Otros pasivos operativos ctes. y no ctes.",
    
    # Actividades de Inversión
    "investing activities:": "ACTIVIDADES DE INVERSIÓN:",
    "investing activities": "ACTIVIDADES DE INVERSIÓN",
    "cash flows from investing activities:": "Flujos de caja de actividades de inversión:",
    "cash generated by investing activities": "FLUJO DE CAJA DE INVERSIÓN (CFI)",
    "cash generated by/(used in) investing activities": "FLUJO DE CAJA DE INVERSIÓN (CFI)",
    "cash used in investing activities": "FLUJO DE CAJA DE INVERSIÓN (CFI)",
    "net cash provided by (used in) investing activities": "FLUJO DE CAJA DE INVERSIÓN (CFI)",
    "net cash used in investing activities": "FLUJO DE CAJA DE INVERSIÓN (CFI)",
    "purchases of marketable securities": "Compras de valores negociables",
    "proceeds from maturities of marketable securities": "Cobros por vencimiento de valores negociables",
    "proceeds from sales of marketable securities": "Cobros por venta de valores negociables",
    "payments for acquisition of property, plant and equipment": "Inversión de capital en PP&E (CapEx)",
    "capital expenditures": "Inversión de capital (CapEx)",
    "purchases of property and equipment": "Compras de propiedad y equipo (CapEx)",
    "payments for acquisitions, net": "Pagos netos por adquisiciones de empresas (M&A)",
    
    # Actividades de Financiación
    "financing activities:": "ACTIVIDADES DE FINANCIACIÓN:",
    "financing activities": "ACTIVIDADES DE FINANCIACIÓN",
    "cash flows from financing activities:": "Flujos de caja de actividades de financiación:",
    "cash used in financing activities": "FLUJO DE CAJA DE FINANCIACIÓN (CFF)",
    "cash generated by financing activities": "FLUJO DE CAJA DE FINANCIACIÓN (CFF)",
    "net cash provided by (used in) financing activities": "FLUJO DE CAJA DE FINANCIACIÓN (CFF)",
    "net cash used in financing activities": "FLUJO DE CAJA DE FINANCIACIÓN (CFF)",
    "payments for taxes related to net share settlement of equity awards": "Retención fiscal por liquidación de acciones (SBC Tax)",
    "payments for dividends and dividend equivalents": "Dividendos y equivalentes pagados en efectivo",
    "dividends paid": "Dividendos pagados",
    "repurchases of common stock": "Recompras de acciones ordinarias",
    "payments for repurchase of common stock": "Recompras de acciones ordinarias",
    "proceeds from issuance of term debt, net": "Emisión neta de deuda a plazo",
    "proceeds from issuance of common stock": "Emisión de acciones ordinarias",
    "repayments of term debt": "Repago / amortización de deuda a plazo",
    "repayments of long-term debt": "Repago de deuda a largo plazo",
    "proceeds from/(repayments of) commercial paper, net": "Emisión / (repago) neto de pagarés comerciales",
    "proceeds from issuance of commercial paper": "Emisión de pagarés comerciales",
    "repayments of commercial paper": "Repago de pagarés comerciales",
    "increase/(decrease) in cash, cash equivalents, and restricted cash and cash equivalents": "Variación neta de efectivo y equivalentes",
    "net increase (decrease) in cash and cash equivalents": "Variación neta de efectivo y equivalentes",
    "cash, cash equivalents, and restricted cash and cash equivalents, ending balances": "Efectivo y equivalentes al cierre",
    "cash and cash equivalents at end of period": "Efectivo y equivalentes al cierre",
    
    # Información suplementaria
    "supplemental cash flow disclosure:": "Información suplementaria de flujo de caja:",
    "supplemental cash flow disclosures:": "Información suplementaria de flujo de caja:",
    "cash paid for income taxes, net": "Impuestos pagados en efectivo",
    "cash paid for interest": "Intereses pagados en efectivo",
    "cash paid for interest, net": "Intereses netos pagados en efectivo",

    # =========================================================================
    # 4. INSTITUCIONES FINANCIERAS / BANCOS (BANKING / FINANCIAL TAXONOMY)
    # =========================================================================
    "interest and dividend income": "Ingresos por intereses y dividendos",
    "total interest income": "Ingreso total por intereses",
    "interest expense": "Gastos por intereses",
    "total interest expense": "Gasto total por intereses",
    "net interest income": "Margen de intereses neto (NII)",
    "noninterest revenue": "Ingresos no financieros (Comisiones/Trading)",
    "total noninterest revenue": "Total ingresos no financieros",
    "principal transactions": "Operaciones por cuenta propia (Trading)",
    "investment banking fees": "Comisiones de banca de inversión",
    "asset management, administration and commissions": "Gestión de activos y comisiones",
    "compensation expense": "Gastos de personal y compensación",
    "occupancy expense": "Gastos de inmuebles y oficinas",
    "technology, communications and equipment": "Tecnología, comunicaciones y equipamiento",
    "provision for credit losses": "Provisión para insolvencias y pérdidas crediticias",
    "deposits": "Depósitos de clientes",
    "total deposits": "Total depósitos",
    "loans": "Préstamos y créditos a clientes",
    "allowance for credit losses": "Fondo de cobertura / provisión crediticia",
    "long-term debt": "Financiación mayorista y deuda a largo plazo",
    
    # =========================================================================
    # 5. BIENES RAÍCES (REITS) Y SEGUROS (INSURANCE)
    # =========================================================================
    "rental revenue": "Ingresos por alquileres",
    "property operating expenses": "Gastos operativos de inmuebles",
    "real estate investments": "Inversiones en propiedades inmobiliarias",
    "premiums earned": "Primas de seguros devengadas",
    "losses and loss adjustment expenses": "Siniestros y gastos de liquidación",
    "policy acquisition costs": "Costos de adquisición de pólizas",
    "unearned premiums": "Primas no devengadas"
}


def get_spanish_clarification(label: str, concept: str = None) -> str:
    """
    Retorna la aclaración técnica en español para una partida contable.
    Si no encuentra coincidencia exacta, busca por variantes normalizadas o concepto XBRL.
    """
    if not label:
        return None
        
    lbl_clean = str(label).strip()
    lbl_lower = lbl_clean.lower()
    
    # 1. Búsqueda exacta directa
    if lbl_lower in SPANISH_CLARIFICATIONS:
        return SPANISH_CLARIFICATIONS[lbl_lower]
        
    # 2. Sin dos puntos al final
    lbl_no_colon = lbl_lower.rstrip(":")
    if lbl_no_colon in SPANISH_CLARIFICATIONS:
        return SPANISH_CLARIFICATIONS[lbl_no_colon]
        
    # 3. Limpieza de notas de pie o caracteres especiales (ej. 'shareholders’' vs 'shareholders\'')
    lbl_norm = lbl_lower.replace("’", "'").replace("–", "-")
    if lbl_norm in SPANISH_CLARIFICATIONS:
        return SPANISH_CLARIFICATIONS[lbl_norm]
        
    # 4. Búsqueda por concepto XBRL canónico
    if concept:
        c_clean = str(concept).split(":")[-1].split("_")[-1].lower()
        concept_map = {
            "revenuefromcontractwithcustomerexcludingassessedtax": "Ventas netas",
            "salesrevenuenet": "Ventas netas",
            "costofgoodsandservicessold": "Costo de ventas",
            "grossprofit": "Utilidad bruta",
            "researchanddevelopmentexpense": "Investigación y desarrollo (I+D)",
            "sellinggeneralandadministrativeexpense": "Gastos de venta, generales y admin. (SG&A)",
            "operatingincomeloss": "Resultado operativo (EBIT)",
            "netincomeloss": "Utilidad neta consolidada",
            "cashandcashequivalentsatcarryingvalue": "Efectivo y equivalentes de efectivo",
            "marketablesecuritiescurrent": "Valores negociables / Inversiones líquidas CP",
            "marketablesecuritiesnoncurrent": "Valores negociables no corrientes",
            "accountsreceivablenetcurrent": "Cuentas por cobrar comerciales netas",
            "inventorynet": "Inventarios / Existencias",
            "propertyplantandequipmentnet": "Propiedad, planta y equipo (PP&E neto)",
            "accountspayablecurrent": "Cuentas por pagar comerciales (Proveedores)",
            "commercialpaper": "Pagarés comerciales (Deuda CP)",
            "debtcurrent": "Deuda a corto plazo",
            "longtermdebtnoncurrent": "Deuda a largo plazo no corriente",
            "retainedearningsaccumulateddeficit": "Resultados acumulados / Ganancias retenidas",
            "stockholdersequity": "Patrimonio neto total",
            "netcashprovidedbyusedinoperatingactivities": "Flujo de caja operativo (CFO)",
            "paymentsforacquisitionofpropertyplantandequipment": "Inversión de capital en PP&E (CapEx)",
            "paymentsforrepurchaseofcommonstock": "Recompras de acciones ordinarias"
        }
        if c_clean in concept_map:
            return concept_map[c_clean]
            
    # 5. Búsqueda parcial selectiva (solo si no es ambiguo)
    for k, v in SPANISH_CLARIFICATIONS.items():
        if len(k) >= 8 and k in lbl_lower:
            return v
            
    return None
