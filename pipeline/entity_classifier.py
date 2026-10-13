"""
========================================================================================
ORQUESTADOR UNIVERSAL DE ANÁLISIS FUNDAMENTAL - CLASIFICADOR INSTITUCIONAL DE ENTIDADES
========================================================================================
Módulo de clasificación formal de entidades y arquetipos contables según estándares
regulatorios internacionales (SEC Regulation S-X, SEC SIC Hierarchy y topología de balance).

Arquetipos soportados:
- 'STANDARD_CORPORATE': Modelo corporativo universal (C&I: Commercial & Industrial bajo Article 5 S-X).
                        Aplica a empresas de tecnología, software, manufactura, retail, consumo y salud (ej. AAPL, DECK, META).
- 'FINANCIAL_BANKING':  Instituciones de depósito e intermediación crediticia (Banca bajo Article 9 S-X).
                        Bancos comerciales, bancos de inversión y neobancos digitales (ej. JPM, BAC, NU).
- 'PLATFORM_ECOSYSTEM': Ecosistemas híbridos multi-lado que integran comercio/marketplace con servicios
                        financieros y crédito integrado (ej. MELI, SE).
- 'REAL_ESTATE_REIT':   Sociedades y fondos de inversión inmobiliaria cotizados (REITs / SOCIMIs bajo Article 6 S-X / SIC 6798).
- 'INSURANCE':          Aseguradoras y reaseguradoras de vida, salud, o propiedad/casualty (Article 7 S-X / SIC 6300-6499).
"""

from typing import Any, Dict, Iterable, Optional, Set
import re


# --------------------------------------------------------------------------------------
# 1. TAXONOMÍA OFICIAL DE DIVISIONES SIC DE LA SEC (Standard Industrial Classification)
# --------------------------------------------------------------------------------------
# SEC Division H (Codes 6000-6799): Único recinto regulatorio de entidades financieras (FIRE).
SIC_FIRE_BANKING_MIN = 6000
SIC_FIRE_BANKING_MAX = 6199
SIC_FIRE_BROKER_MIN = 6200
SIC_FIRE_BROKER_MAX = 6299
SIC_FIRE_INSURANCE_MIN = 6300
SIC_FIRE_INSURANCE_MAX = 6499
SIC_FIRE_REIT_CODE = 6798

# Códigos SIC de plataformas y comercio electrónico híbrido
SIC_PLATFORM_CODES = {5961, 7389, 5990}


# --------------------------------------------------------------------------------------
# 2. HUELLAS CONCEPTUALES XBRL PARA DETECCIÓN TOPOLÓGICA DE BALANCE Y P&L
# --------------------------------------------------------------------------------------

# Partidas de costo comercial / servicios (excluyentes de banca pura)
COMMERCIAL_COGS_CONCEPTS = {
    "costofgoodsandservicessold",
    "costofgoodssold",
    "costofrevenue",
    "costofsales",
    "costofservices",
    "costofmerchandisesold",
    "totalcostofgoodssold",
    "costofproductssold",
    "costofgoodsandserviceexcludingdepreciationdepletionandamortization",
    "costofservicesexcludingdepreciationdepletionandamortization",
    "costofgoodssoldexcludingdepreciationdepletionandamortization",
    "costofrealestaterevenue",
    "costofrevenues",
    "productioncosts",
}

# Partidas de inventarios físicos
INVENTORY_CONCEPTS = {
    "inventorynet",
    "inventories",
    "merchandiseinventories",
    "finishedgoods",
    "rawmaterialsandsupplies",
}

# Conceptos de captación de depósitos BANCARIOS de intermediación (NO depósitos de clientes ASC 606)
BANKING_DEPOSIT_CONCEPTS = {
    "depositsfromcustomers",
    "interestbearingdepositliabilities",
    "noninterestbearingdepositliabilities",
    "customeraccounts",
    "depositsfairvaluedisclosure",
    "timedeposits",
    "demanddeposits",
    "certificatesofdeposit",
    "depositsliabilities",
    "customeraccountbalances",
    "savingsandinterestcheckingdeposits",
    "timedepositsatcarryingvalue",
    "totaldeposits",
}

# Exclusiones explícitas de ASC 606 (Contratos con Clientes) y depósitos operativos en garantía
ASC_606_EXCLUSIONS = {
    "contractwithcustomerliability",
    "contractwithcustomerliabilityandunuseddeposits",
    "unuseddeposits",
    "deferredrevenue",
    "customeradvances",
    "securitydeposits",
    "escrowdeposits",
    "leaseguarantees",
}

# Conceptos de colocación crediticia / préstamos bancarios
BANKING_LOAN_CONCEPTS = {
    "loansandadvancestocustomers",
    "loansandleasesreceivablenetofdeferredincome",
    "creditcardreceivables1",
    "notesandloansreceivablenetcurrent",
    "notesandloansreceivablenetnoncurrent",
    "loansreceivable",
    "financingreceivableafterallowanceforcreditloss",
    "financingreceivableexcludingaccruedinterestafterallowanceforcreditloss",
    "totalloansandadvancestocustomers",
    "commercialloansreceivablenet",
    "consumerloansreceivablenet",
    "creditcardreceivablesnet",
    "creditcardreceivables",
    "personalloansreceivablenet",
    "allowanceforcreditlossesonfinancingreceivables",
    "loansandadvancestocustomersnetofallowances",
}

# Provisiones y pérdidas crediticias bancarias
BANKING_CREDIT_LOSS_CONCEPTS = {
    "expectedcreditloss",
    "creditlossallowanceexpenses",
    "creditlossexpense",
    "provisionforloanandleaselosses",
    "provisionforcreditlosses",
    "provisionfordoubtfulaccounts",
    "impairmentlossonfinancialassets",
    "creditcardlossprovision",
    "provisionforloanleaseandotherlosses",
    "allowanceforcreditlossesprovision",
}

# Conceptos inmobiliarios REIT
REIT_CONCEPTS = {
    "realestateinvestmentpropertyatcost",
    "rentalrevenue",
    "operatingleaserevenue",
    "realestaterevenuenet",
    "realestateexpense",
    "propertyoperatingexpenses",
    "depreciationandamortizationrealestate",
    "tenantreimbursements",
    "operatingleasereimbursementrevenue",
    "propertymanagementfeerevenue",
    "realestaterentalrevenue",
    "realestatetaxes",
    "propertymanagementexpenses",
}

# Conceptos de seguros
INSURANCE_CONCEPTS = {
    "premiumsearnednet",
    "netpremiumsearned",
    "insurancepremiumsearnednet",
    "liabilityforclaimsandclaimsadjustmentexpense",
    "unearnedpremiums",
    "incurredclaimsandlossadjustmentexpensesnet",
    "policyholderbenefitsandclaimsincurrednet",
    "deferredpolicyacquisitioncost",
    "premiumswrittengross",
    "directpremiumswritten",
    "premiumswrittennet",
    "cededpremiumswritten",
    "cededpremiumsearned",
    "lossesandlossadjustmentexpensesnet",
    "lossadjustmentexpenses",
    "reserveforunpaidclaimsnet",
}


def clean_concept_name(concept: Any) -> str:
    """Limpia el nombre del concepto removiendo prefijos, namespaces y separadores."""
    s = str(concept or "").strip().lower()
    s = s.split(":")[-1].split("_")[-1]
    return s.replace("-", "").replace("_", "")


def parse_sic_code(raw_sic: Any) -> Optional[int]:
    """Extrae de forma robusta el código SIC de 4 dígitos."""
    if raw_sic is None:
        return None
    try:
        s = str(raw_sic).strip()
        if isinstance(raw_sic, float) or "." in s:
            return None
        m = re.search(r"\b(\d{4})\b", s)
        if m:
            return int(m.group(1))
        # Intento de extracción de número general
        m_any = re.search(r"(\d+)", s)
        if m_any:
            return int(m_any.group(1))
    except Exception:
        pass
    return None


def detect_company_archetype(
    company: Any = None,
    profile_data: Optional[Dict[str, Any]] = None,
    detected_concepts: Optional[Iterable[Any]] = None,
    sic_code: Any = None,
    income_data: Optional[Dict[str, Any]] = None,
    balance_data: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Clasifica de manera dinámica, invariante de escala y con rigor institucional a la
    entidad en uno de los 5 arquetipos contables fundamentales.

    Sigue una jerarquía de 3 niveles:
    1. Clasificación regulatoria primaria (SEC SIC Hierarchy).
    2. Perfil de negocio formal y taxonomía de industria (GICS / NAICS).
    3. Verificación topológica de balance y cuenta de resultados (Dual Intermediation Check).
    """
    # ----------------------------------------------------------------------------------
    # Nivel 0: Pre-declaración formal auditada en perfil (si existe y es válida)
    # ----------------------------------------------------------------------------------
    if profile_data and isinstance(profile_data, dict):
        declared = str(profile_data.get("archetype", "")).strip().upper()
        if declared in (
            "STANDARD_CORPORATE",
            "CORPORATE_STANDARD",
            "FINANCIAL_BANKING",
            "PLATFORM_ECOSYSTEM",
            "REAL_ESTATE_REIT",
            "INSURANCE",
        ):
            return declared

    # ----------------------------------------------------------------------------------
    # Nivel 1: Identificación y validación del código SIC oficial de la SEC
    # ----------------------------------------------------------------------------------
    sic_val = parse_sic_code(sic_code)
    if sic_val is None and company is not None:
        sic_val = parse_sic_code(getattr(company, "sic", None))
    if sic_val is None and profile_data:
        sic_val = parse_sic_code(profile_data.get("sic_code"))

    # Metadatos auxiliares de perfil
    ind = ""
    sec = ""
    bm = ""
    if profile_data and isinstance(profile_data, dict):
        ind = str(profile_data.get("industry", "")).lower()
        sec = str(profile_data.get("sector", "")).lower()
        bm = str(profile_data.get("business_model", "")).upper()

    # ----------------------------------------------------------------------------------
    # Nivel 2: Huella XBRL de balance y cuentas de resultados
    # ----------------------------------------------------------------------------------
    has_customer_deposits = False
    has_loans = False
    has_credit_loss = False
    has_commercial_cogs = False
    has_inventory = False
    has_reit_concepts = False
    has_insurance_concepts = False

    concept_set: Set[str] = set()
    if detected_concepts:
        for c in detected_concepts:
            concept_set.add(clean_concept_name(c))

    if income_data:
        for c in income_data.keys():
            concept_set.add(clean_concept_name(c))
    if balance_data:
        for c in balance_data.keys():
            concept_set.add(clean_concept_name(c))

    if concept_set:
        # Detección de Costo de Ventas Comercial (incluye CostOfRevenue para Big Tech / SaaS)
        if any(c in COMMERCIAL_COGS_CONCEPTS for c in concept_set) or any(
            any(cog in c for cog in COMMERCIAL_COGS_CONCEPTS) for c in concept_set
        ):
            has_commercial_cogs = True

        # Detección de Inventario Físico
        if any(c in INVENTORY_CONCEPTS for c in concept_set) or any(
            any(inv in c for inv in INVENTORY_CONCEPTS) for c in concept_set
        ):
            has_inventory = True

        # Detección de Depósitos Bancarios (filtrando rigurosamente pasivos de clientes ASC 606)
        for c in concept_set:
            # Exclusión prioritaria de ASC 606 y depósitos de garantía no bancarios
            if any(exc in c for exc in ASC_606_EXCLUSIONS):
                continue
            if c in BANKING_DEPOSIT_CONCEPTS or any(bd in c for bd in BANKING_DEPOSIT_CONCEPTS):
                has_customer_deposits = True
                break

        # Detección de Cartera de Préstamos
        if any(c in BANKING_LOAN_CONCEPTS for c in concept_set) or any(
            any(ln in c for ln in BANKING_LOAN_CONCEPTS) for c in concept_set
        ):
            has_loans = True

        # Detección de Provisiones por Pérdidas Crediticias
        if any(c in BANKING_CREDIT_LOSS_CONCEPTS for c in concept_set) or any(
            any(cl in c for cl in BANKING_CREDIT_LOSS_CONCEPTS) for c in concept_set
        ):
            has_credit_loss = True

        # Detección de Partidas Inmobiliarias REIT
        if any(c in REIT_CONCEPTS for c in concept_set) or any(
            any(rc in c for rc in REIT_CONCEPTS) for c in concept_set
        ):
            has_reit_concepts = True

        # Detección de Seguros
        if any(c in INSURANCE_CONCEPTS for c in concept_set) or any(
            any(ic in c for ic in INSURANCE_CONCEPTS) for c in concept_set
        ):
            has_insurance_concepts = True

    # ----------------------------------------------------------------------------------
    # Nivel 3: Algoritmo Jerárquico de Decisión Institucional
    # ----------------------------------------------------------------------------------

    # --- REGLA PRIMARIA DE EXCLUSIÓN NO-FINANCIERA (SIC 7000-8999, 2000-3999, 0100-5999) ---
    # Si la empresa pertenece a Servicios Informáticos / Big Tech / Software (SIC 7370-7379),
    # Manufactura de Hardware / Computadoras (SIC 3571), o Calzado / Consumo (SIC 3021),
    # es ESTRUCTURALMENTE IMPOSIBLE que sea un banco o aseguradora.
    is_pure_tech_or_services_sic = (sic_val is not None and 7370 <= sic_val <= 7379)
    is_non_financial_sic = (sic_val is not None and (sic_val < SIC_FIRE_BANKING_MIN or sic_val > 6799))

    # 1. Detección de REAL_ESTATE_REIT (SIC 6798 o perfil REIT o conceptos inmobiliarios puros)
    is_reit_sic = (sic_val == SIC_FIRE_REIT_CODE) if sic_val else False
    is_reit_profile = any(k in ind or k in sec for k in ["reit", "real estate investment trust", "equity reit"]) or ("REIT" in bm)
    has_pure_reit_xbrl = has_reit_concepts and not has_commercial_cogs and not has_inventory
    if is_reit_sic or is_reit_profile or has_pure_reit_xbrl:
        return "REAL_ESTATE_REIT"

    # 2. Detección de INSURANCE (SIC 6300-6499 o perfil de seguros o conceptos de seguros puros)
    is_insurance_sic = (SIC_FIRE_INSURANCE_MIN <= sic_val <= SIC_FIRE_INSURANCE_MAX) if sic_val else False
    is_insurance_profile = (
        any(k in ind or k in sec for k in ["insurance", "property & casualty", "property and casualty", "life insurance", "reinsurance"])
        or ("INSURANCE" in bm)
        or ("underwriting" in str(profile_data.get("business_model", "")).lower() if profile_data else False)
    )
    has_pure_insurance_xbrl = has_insurance_concepts and not has_commercial_cogs and not has_inventory
    if is_insurance_sic or is_insurance_profile or has_pure_insurance_xbrl:
        return "INSURANCE"

    # 3. Detección de PLATFORM_ECOSYSTEM (Comercio / Marketplace + Crédito / Fintech Integrado)
    # Ejemplos: Mercado Libre (MELI), Sea Ltd (SE)
    is_platform_sic = (sic_val in SIC_PLATFORM_CODES) if sic_val else False
    is_platform_profile = (
        ("marketplace" in ind or "platform" in ind or "e-commerce" in ind or "retail" in ind) and
        ("fintech" in ind or "financial" in ind or "credit" in ind or "banking" in ind or "payments" in ind)
    ) or ("PLATFORM" in bm or "ECOSYSTEM" in bm)
    has_hybrid_balance = (has_commercial_cogs or has_inventory) and (has_loans or has_credit_loss)

    if (is_platform_sic and (has_loans or has_credit_loss or "fintech" in ind or "credit" in ind)) or is_platform_profile or (has_hybrid_balance and not is_pure_tech_or_services_sic):
        return "PLATFORM_ECOSYSTEM"

    # 4. Detección de FINANCIAL_BANKING (Intermediación Financiera Bancaria Activa)
    # Requiere obligatoriamente pertenecer a la división bancaria FIRE (SIC 6000-6199)
    # O, para Foreign Private Issuers sin SIC formal, demostrar Intermediación Dual de Balance
    # (Captación de depósitos Y colocación de préstamos / pérdidas crediticias).
    is_banking_sic = (SIC_FIRE_BANKING_MIN <= sic_val <= SIC_FIRE_BANKING_MAX) if sic_val else False
    is_banking_profile = (
        ("banking" in ind or "neobank" in ind or "bank" in ind or "commercial banking" in ind) and
        not ("marketplace" in ind or "e-commerce" in ind or "retail" in ind or "insurance" in ind or "software" in ind or "cloud" in ind)
    ) or ("BANKING" in bm)

    # Intermediación dual real: captación y colocación activa
    has_dual_intermediation_xbrl = (
        has_customer_deposits and (has_loans or has_credit_loss) and not has_commercial_cogs and not has_inventory
    )
    has_pure_deposit_xbrl = (
        has_customer_deposits and not has_commercial_cogs and not has_inventory
    )

    if not is_non_financial_sic:
        # Solo consideramos banking si no tiene un SIC no financiero explícito
        if is_banking_sic or is_banking_profile or has_dual_intermediation_xbrl or has_pure_deposit_xbrl:
            return "FINANCIAL_BANKING"
    else:
        # Si tiene un SIC no financiero (como software 7372), solo clasifica como banco si es SIC banking o si tiene firma pura de depósitos bancarios sin costo comercial ni inventario (override T2.R1.4)
        if is_banking_sic or (has_pure_deposit_xbrl and not (has_commercial_cogs or has_inventory)):
            return "FINANCIAL_BANKING"

    # 5. Por defecto: Modelo Corporativo / Industrial Universal (STANDARD_CORPORATE)
    return "STANDARD_CORPORATE"


def is_banking_or_financial(
    company: Any = None,
    profile_data: Optional[Dict[str, Any]] = None,
    detected_concepts: Optional[Iterable[Any]] = None,
    sic_code: Any = None,
) -> bool:
    """Wrapper de conveniencia para verificar si una entidad es de naturaleza financiera/bancaria."""
    archetype = detect_company_archetype(
        company=company,
        profile_data=profile_data,
        detected_concepts=detected_concepts,
        sic_code=sic_code,
    )
    return archetype in ("FINANCIAL_BANKING", "INSURANCE")
