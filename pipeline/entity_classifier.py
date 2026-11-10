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
import logging
import re

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------------------
# 0. TAXONOMÍA Y ALIAS RECÍPROCOS DE ARQUETIPOS CONTABLES INSTITUCIONALES
# --------------------------------------------------------------------------------------
CORPORATE_ARCHETYPE_ALIASES = ("CORPORATE_STANDARD", "STANDARD_CORPORATE")

CANONICAL_ARCHETYPES = {
    "CORPORATE_STANDARD",
    "STANDARD_CORPORATE",
    "FINANCIAL_BANKING",
    "INSURANCE",
    "REAL_ESTATE_REIT",
    "PLATFORM_ECOSYSTEM",
}

ARCHETYPE_ALIASES = {
    "CORPORATE_STANDARD": "STANDARD_CORPORATE",
    "STANDARD_CORPORATE": "STANDARD_CORPORATE",
    "FINANCIAL_BANKING": "FINANCIAL_BANKING",
    "BANKING_FINANCIAL": "FINANCIAL_BANKING",
    "BANKING": "FINANCIAL_BANKING",
    "INSURANCE": "INSURANCE",
    "INSURER": "INSURANCE",
    "REAL_ESTATE_REIT": "REAL_ESTATE_REIT",
    "REIT": "REAL_ESTATE_REIT",
    "REAL_ESTATE": "REAL_ESTATE_REIT",
    "PLATFORM_ECOSYSTEM": "PLATFORM_ECOSYSTEM",
    "ECOSYSTEM_PLATFORM": "PLATFORM_ECOSYSTEM",
}


def normalize_archetype(archetype: str, default: str = "STANDARD_CORPORATE") -> str:
    """
    Normaliza el identificador de arquetipo admitiendo alias canónicos y recíprocos:
    CORPORATE_STANDARD <-> STANDARD_CORPORATE.
    """
    if not archetype:
        return default
    arch_clean = str(archetype).strip().upper()
    if arch_clean in CORPORATE_ARCHETYPE_ALIASES:
        # Preservar la reciprocidad cuando `default` pide expresamente uno de los alias corporativos,
        # evitando devolver un fallback ajeno (p. ej. FINANCIAL_BANKING) para un emisor corporativo.
        return default if default in CORPORATE_ARCHETYPE_ALIASES else "STANDARD_CORPORATE"
    return ARCHETYPE_ALIASES.get(arch_clean, arch_clean)


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
        m_any = re.search(r"(\d+)", s)
        if m_any:
            return int(m_any.group(1))
    except (ValueError, TypeError, AttributeError) as exc:
        logger.debug("No se pudo parsear código SIC %r: %s", raw_sic, exc)
    return None


def _has_concept_match(
    concept_set: Set[str],
    vocabulary: Set[str],
    exclusions: Optional[Set[str]] = None,
) -> bool:
    """Verifica si algún concepto limpio coincide con un vocabulario, aplicando exclusiones."""
    for c in concept_set:
        if exclusions and any(exc in c for exc in exclusions):
            continue
        if c in vocabulary or any(term in c for term in vocabulary):
            return True
    return False


def _extract_concept_fingerprint(
    detected_concepts: Optional[Iterable[Any]],
    income_data: Optional[Dict[str, Any]],
    balance_data: Optional[Dict[str, Any]],
) -> Dict[str, bool]:
    """Construye la huella XBRL booleana sobre conceptos de balance y resultados."""
    concept_set: Set[str] = set()
    for items in (detected_concepts or ()):
        concept_set.add(clean_concept_name(items))
    for mapping in (income_data, balance_data):
        if mapping:
            for c in mapping.keys():
                concept_set.add(clean_concept_name(c))

    if not concept_set:
        return {
            "has_customer_deposits": False,
            "has_loans": False,
            "has_credit_loss": False,
            "has_commercial_cogs": False,
            "has_inventory": False,
            "has_reit_concepts": False,
            "has_insurance_concepts": False,
        }

    return {
        "has_commercial_cogs": _has_concept_match(concept_set, COMMERCIAL_COGS_CONCEPTS),
        "has_inventory": _has_concept_match(concept_set, INVENTORY_CONCEPTS),
        "has_customer_deposits": _has_concept_match(concept_set, BANKING_DEPOSIT_CONCEPTS, ASC_606_EXCLUSIONS),
        "has_loans": _has_concept_match(concept_set, BANKING_LOAN_CONCEPTS),
        "has_credit_loss": _has_concept_match(concept_set, BANKING_CREDIT_LOSS_CONCEPTS),
        "has_reit_concepts": _has_concept_match(concept_set, REIT_CONCEPTS),
        "has_insurance_concepts": _has_concept_match(concept_set, INSURANCE_CONCEPTS),
    }


def _resolve_declared_archetype(profile_data: Optional[Dict[str, Any]]) -> Optional[str]:
    """Retorna el arquetipo pre-declarado en `company_profile` si pertenece al conjunto canónico."""
    if not isinstance(profile_data, dict):
        return None
    declared = str(profile_data.get("archetype", "")).strip().upper()
    return declared if declared in CANONICAL_ARCHETYPES else None


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
    entidad en uno de los 5 arquetipos contables fundamentales:
    1. Clasificación regulatoria primaria (SEC SIC Hierarchy).
    2. Perfil de negocio formal y taxonomía de industria (GICS / NAICS).
    3. Verificación topológica de balance y cuenta de resultados (Dual Intermediation Check).
    """
    declared = _resolve_declared_archetype(profile_data)
    if declared:
        return declared

    sic_val = parse_sic_code(sic_code)
    if sic_val is None and company is not None:
        sic_val = parse_sic_code(getattr(company, "sic", None))
    if sic_val is None and isinstance(profile_data, dict):
        sic_val = parse_sic_code(profile_data.get("sic_code"))

    ind = str(profile_data.get("industry", "")).lower() if isinstance(profile_data, dict) else ""
    sec = str(profile_data.get("sector", "")).lower() if isinstance(profile_data, dict) else ""
    bm_raw = str(profile_data.get("business_model", "")) if isinstance(profile_data, dict) else ""
    bm = bm_raw.upper()

    fp = _extract_concept_fingerprint(detected_concepts, income_data, balance_data)
    has_commercial_ops = fp["has_commercial_cogs"] or fp["has_inventory"]
    is_pure_tech_or_services_sic = sic_val is not None and 7370 <= sic_val <= 7379
    is_non_financial_sic = sic_val is not None and (sic_val < SIC_FIRE_BANKING_MIN or sic_val > 6799)

    # 1. REAL_ESTATE_REIT
    is_reit_sic = sic_val == SIC_FIRE_REIT_CODE if sic_val else False
    is_reit_profile = any(k in ind or k in sec for k in ("reit", "real estate investment trust", "equity reit")) or ("REIT" in bm)
    if is_reit_sic or is_reit_profile or (fp["has_reit_concepts"] and not has_commercial_ops):
        return "REAL_ESTATE_REIT"

    # 2. INSURANCE
    is_insurance_sic = SIC_FIRE_INSURANCE_MIN <= sic_val <= SIC_FIRE_INSURANCE_MAX if sic_val else False
    is_insurance_profile = (
        any(k in ind or k in sec for k in ("insurance", "property & casualty", "property and casualty", "life insurance", "reinsurance"))
        or ("INSURANCE" in bm)
        or ("underwriting" in bm_raw.lower())
    )
    if is_insurance_sic or is_insurance_profile or (fp["has_insurance_concepts"] and not has_commercial_ops):
        return "INSURANCE"

    # 3. PLATFORM_ECOSYSTEM
    is_platform_sic = sic_val in SIC_PLATFORM_CODES if sic_val else False
    is_platform_profile = (
        any(k in ind for k in ("marketplace", "platform", "e-commerce", "retail"))
        and any(k in ind for k in ("fintech", "financial", "credit", "banking", "payments"))
    ) or ("PLATFORM" in bm or "ECOSYSTEM" in bm)
    has_hybrid_balance = has_commercial_ops and (fp["has_loans"] or fp["has_credit_loss"])
    if (
        (is_platform_sic and (fp["has_loans"] or fp["has_credit_loss"] or "fintech" in ind or "credit" in ind))
        or is_platform_profile
        or (has_hybrid_balance and not is_pure_tech_or_services_sic)
    ):
        return "PLATFORM_ECOSYSTEM"

    # 4. FINANCIAL_BANKING
    is_banking_sic = SIC_FIRE_BANKING_MIN <= sic_val <= SIC_FIRE_BANKING_MAX if sic_val else False
    is_banking_profile = (
        any(k in ind for k in ("banking", "neobank", "bank", "commercial banking"))
        and not any(k in ind for k in ("marketplace", "e-commerce", "retail", "insurance", "software", "cloud"))
    ) or ("BANKING" in bm)
    has_pure_deposit_xbrl = fp["has_customer_deposits"] and not has_commercial_ops
    has_dual_intermediation_xbrl = has_pure_deposit_xbrl and (fp["has_loans"] or fp["has_credit_loss"])

    if not is_non_financial_sic:
        if is_banking_sic or is_banking_profile or has_dual_intermediation_xbrl or has_pure_deposit_xbrl:
            return "FINANCIAL_BANKING"
    elif is_banking_sic or has_pure_deposit_xbrl:
        return "FINANCIAL_BANKING"

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
