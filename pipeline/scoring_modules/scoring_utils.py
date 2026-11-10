"""
scoring_utils.py - Utilidades numéricas, carga de benchmarks sectoriales y extracción
normalizada de métricas contables por período desde financial_statements.json.
"""

import json
import math
import re
import statistics
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:
    from config_loader import CONFIG_DIR
    from entity_classifier import normalize_archetype
except ImportError:
    from pipeline.config_loader import CONFIG_DIR
    from pipeline.entity_classifier import normalize_archetype


_DEFAULT_BROAD_MARKET: Dict[str, Any] = {
    "sic_code": "0000",
    "industry_name": "Broad Market Benchmark (S&P 500 Non-Financials)",
    "median_roa": 0.055,
    "p75_roa": 0.100,
    "median_cfroa": 0.078,
    "median_cv_roa": 0.38,
    "median_sales_growth": 0.060,
    "median_cv_sales_growth": 0.42,
    "median_rd_intensity": 0.035,
    "median_capex_intensity": 0.045,
    "median_total_reinvestment": 0.080,
    "is_asset_light": False,
}

_ARCHETYPE_TO_SIC: Dict[str, str] = {
    "FINANCIAL_BANKING": "SIC_6021",
    "REAL_ESTATE_REIT": "SIC_6798",
    "INSURANCE": "SIC_6331",
    "PLATFORM_ECOSYSTEM": "SIC_7389",
    "ASSET_LIGHT_SERVICES": "SIC_7370",
    "STANDARD_CORPORATE": "SIC_3571",
    "CAPITAL_INTENSIVE": "SIC_3571",
    "UTILITY_INFRASTRUCTURE": "SIC_3571",
}

_COMBINED_DEBT_TAGS = (
    "DebtLongtermAndShorttermCombinedAmount",
    "us-gaap_DebtLongtermAndShorttermCombinedAmount",
)

_LT_DEBT_TAGS = (
    "LongTermDebtNoncurrent",
    "us-gaap_LongTermDebtNoncurrent",
    "LongTermDebt",
    "us-gaap_LongTermDebt",
    "LongTermDebtAndCapitalLeaseObligationsIncludingCurrentMaturities",
    "us-gaap_LongTermDebtAndCapitalLeaseObligationsIncludingCurrentMaturities",
    "NotesPayable",
    "us-gaap_NotesPayable",
    "NotesPayableNet",
    "o_NotesPayableNet",
    "SeniorNotes",
    "us-gaap_SeniorNotes",
    "SecuredDebt",
    "us-gaap_SecuredDebt",
    "LoansPayable",
    "us-gaap_LoansPayable",
    "ifrs-full_Borrowings",
    "Borrowings",
    "ifrs-full:Borrowings",
    "ifrs-full_NoncurrentBorrowings",
)

_ST_DEBT_TAGS = (
    "LongTermDebtCurrent",
    "us-gaap_LongTermDebtCurrent",
    "ShortTermBorrowings",
    "us-gaap_ShortTermBorrowings",
    "DebtCurrent",
    "us-gaap_DebtCurrent",
    "ShortTermDebt",
    "LinesOfCreditCurrent",
    "us-gaap_LinesOfCreditCurrent",
    "RevolvingCreditFacilityAndCommercialPaper",
    "LineOfCreditAndCommercialPaper",
    "ifrs-full_CurrentBorrowingsAndCurrentPortionOfNoncurrentBorrowings",
    "CurrentBorrowings",
    "ifrs-full_CurrentBorrowings",
    "OtherShortTermBorrowings",
    "us-gaap_OtherShortTermBorrowings",
)

_ST_INV_TAGS = (
    "MarketableSecuritiesCurrent",
    "us-gaap_MarketableSecuritiesCurrent",
    "ShortTermInvestments",
    "us-gaap_ShortTermInvestments",
    "AvailableForSaleSecuritiesCurrent",
    "us-gaap_AvailableForSaleSecuritiesCurrent",
    "OtherShortTermInvestments",
    "us-gaap_OtherShortTermInvestments",
    "FinancialAssetsAtFairValueThroughProfitOrLossCurrent",
)

_OTHER_CURRENT_ASSETS_TAGS = (
    "OtherAssetsCurrent",
    "us-gaap_OtherAssetsCurrent",
    "PrepaidExpenseAndOtherAssetsCurrent",
    "us-gaap_PrepaidExpenseAndOtherAssetsCurrent",
    "OtherCurrentAssets",
    "us-gaap_OtherCurrentAssets",
    "PrepaidExpensesAndOtherCurrentAssets",
)

_GROSS_PPE_TAGS = (
    "PropertyPlantAndEquipmentGross",
    "us-gaap_PropertyPlantAndEquipmentGross",
    "PropertyPlantAndEquipmentGrossExcludingRightOfUseAsset",
    "PropertyPlantAndEquipmentAndFinanceLeaseRightOfUseAssetBeforeAccumulatedDepreciationAndAmortization",
)


def _safe_float(val: Any) -> Optional[float]:
    """Convierte con seguridad un valor numérico o string a float, filtrando NaN y cadenas no numéricas."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val) if not math.isnan(val) else None
    try:
        s = str(val).strip().replace(",", "")
        if s.lower() in ("none", "nan", "n/a", "-", ""):
            return None
        f = float(s)
        return f if not math.isnan(f) else None
    except (ValueError, TypeError):
        return None


def _to_millions(val: Optional[float]) -> Optional[float]:
    """Escala a millones si la magnitud absoluta excede $1M, soportando valores negativos."""
    if val is None:
        return None
    return val / 1e6 if abs(val) > 1e6 else val


def _clean_sic_code(raw_sic: Optional[str]) -> Optional[str]:
    """Extrae el código SIC canónico de 4 dígitos desde cadenas simples o compuestas (ej. '3021 / 3140')."""
    if raw_sic is None:
        return None
    s = str(raw_sic).strip()
    if not s or s.lower() in ("none", "n/a", "0000", "0"):
        return None
    m = re.search(r"\b(\d{4})\b", s)
    if m and m.group(1) != "0000":
        return m.group(1)
    return None


def _chronological_annual_fys(fiscal_years: Iterable[str]) -> List[str]:
    """Ordena los períodos fiscales anuales cerrados cronológicamente (excluyendo LTM)."""
    annual = [y for y in fiscal_years if y != "LTM"]
    return sorted(
        annual,
        key=lambda x: int(re.search(r"(\d{4})", str(x)).group(1)) if re.search(r"(\d{4})", str(x)) else 0,
    )


def _linear_percentile(data: List[float], p: float) -> float:
    """Calcula un percentil lineal continuo sobre una lista numérica."""
    sorted_data = sorted(data)
    n = len(sorted_data)
    if n == 0:
        return 0.0
    if n == 1:
        return sorted_data[0]
    rank = (n - 1) * p
    lower_idx = int(rank)
    upper_idx = min(lower_idx + 1, n - 1)
    weight = rank - lower_idx
    return sorted_data[lower_idx] + weight * (sorted_data[upper_idx] - sorted_data[lower_idx])


def load_industry_medians(config_path: Optional[str] = None) -> Dict[str, Any]:
    """Carga el catálogo de medianas sectoriales por código SIC/GICS desde config SSOT."""
    p = Path(config_path) if (config_path and Path(config_path).exists()) else (CONFIG_DIR / "industry_medians.json")
    if p.exists():
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"BROAD_MARKET": dict(_DEFAULT_BROAD_MARKET)}


def load_peer_benchmarks(config_path: Optional[str] = None) -> Dict[str, Any]:
    """Carga los benchmarks y cifras LTM del grupo de pares desde config/peer_benchmarks.json."""
    p = Path(config_path) if (config_path and Path(config_path).exists()) else (CONFIG_DIR / "peer_benchmarks.json")
    if p.exists():
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def compute_peer_benchmarks(peers: Any) -> Dict[str, Any]:
    """Calcula dinámicamente las medianas sectoriales y percentil 75 a partir de los pares de la industria."""
    if isinstance(peers, dict):
        peers = peers.get("peers", [])
    roas: List[float] = []
    cfroas: List[float] = []
    rds: List[float] = []
    reinvs: List[float] = []
    capexs: List[float] = []
    gps: List[float] = []
    gp_ex_cashs: List[float] = []
    gms: List[float] = []
    turns: List[float] = []

    for p in peers:
        assets = _safe_float(p.get("total_assets_usd_m"))
        if not assets or assets <= 0:
            continue
        rd = _safe_float(p.get("rd_expense_usd_m")) or 0.0
        capex = _safe_float(p.get("capex_usd_m")) or 0.0
        ni = _safe_float(p.get("net_income_usd_m")) or 0.0
        cfo = _safe_float(p.get("cfo_usd_m")) or 0.0
        rev = _safe_float(p.get("revenue_usd_m"))
        gp = _safe_float(p.get("gross_profit_usd_m"))
        cash = _safe_float(p.get("cash_usd_m")) or 0.0

        roas.append(ni / assets)
        cfroas.append(cfo / assets)
        rds.append(rd / assets)
        reinvs.append((rd + capex) / assets)
        capexs.append(capex / assets)

        if gp is not None:
            gps.append(gp / assets)
            op_assets = (assets - cash) if (assets > cash and (assets - cash) > 0) else assets
            gp_ex_cashs.append(gp / op_assets)
            if rev and rev > 0:
                gms.append(gp / rev)
        if rev and rev > 0:
            turns.append(rev / assets)

    trad_roics = [v for v in (_safe_float(p.get("traditional_roic")) for p in peers) if v is not None]
    adj_roics = [v for v in (_safe_float(p.get("adjusted_roic")) for p in peers) if v is not None]
    waccs = [v for v in (_safe_float(p.get("wacc")) for p in peers) if v is not None]
    spreads = [v for v in (_safe_float(p.get("economic_spread")) for p in peers) if v is not None]
    rocs = [
        v
        for v in (_safe_float(p.get("greenblatt_roc", p.get("roc"))) for p in peers)
        if v is not None
    ]

    med_roc = statistics.median(rocs) if rocs else 0.350
    return {
        "median_roa": statistics.median(roas) if roas else 0.055,
        "median_cfroa": statistics.median(cfroas) if cfroas else 0.078,
        "median_rd_intensity": statistics.median(rds) if rds else 0.035,
        "median_total_reinvestment": statistics.median(reinvs) if reinvs else 0.080,
        "median_capex_intensity": statistics.median(capexs) if capexs else 0.045,
        "p75_roa": _linear_percentile(roas, 0.75) if roas else 0.100,
        "median_gross_profitability": statistics.median(gps) if gps else 0.280,
        "p75_gross_profitability": _linear_percentile(gps, 0.75) if gps else 0.400,
        "median_gp_ex_cash": statistics.median(gp_ex_cashs) if gp_ex_cashs else 0.320,
        "median_gross_margin": statistics.median(gms) if gms else 0.380,
        "median_asset_turnover": statistics.median(turns) if turns else 0.75,
        "median_traditional_roic": statistics.median(trad_roics) if trad_roics else 0.185,
        "median_adjusted_roic": statistics.median(adj_roics) if adj_roics else 0.165,
        "median_wacc": statistics.median(waccs) if waccs else 0.088,
        "median_economic_spread": statistics.median(spreads) if spreads else 0.077,
        "median_greenblatt_roc": med_roc,
        "peer_greenblatt_roc_median": med_roc,
    }


def _find_peer_group(
    ind_peers: Dict[str, Any],
    sic_clean: Optional[str],
    ticker: Optional[str],
    archetype: Optional[str],
) -> Optional[Dict[str, Any]]:
    """Localiza el grupo de pares sectoriales por SIC exacto, ticker, prefijo SIC o arquetipo SSOT."""
    if sic_clean and f"SIC_{sic_clean}" in ind_peers:
        return ind_peers[f"SIC_{sic_clean}"]

    if ticker:
        t_upper = ticker.upper()
        for v in ind_peers.values():
            if any(p.get("ticker", "").upper() == t_upper for p in v.get("peers", [])):
                return v

    if sic_clean and len(sic_clean) == 4:
        for prefix_len in (3, 2):
            prefix = sic_clean[:prefix_len]
            for k, v in ind_peers.items():
                cand_sic = str(v.get("sic_code") or k.replace("SIC_", "")).strip()
                if cand_sic.startswith(prefix):
                    return v

    if archetype:
        arch_norm = normalize_archetype(archetype)
        fallback_key = _ARCHETYPE_TO_SIC.get(arch_norm)
        if fallback_key and fallback_key in ind_peers:
            return ind_peers[fallback_key]
    return None


def get_sector_benchmarks(
    sic_code: Optional[str],
    medians_db: Dict[str, Any],
    ticker: Optional[str] = None,
    peer_benchmarks_db: Optional[Dict[str, Any]] = None,
    archetype: Optional[str] = None,
) -> Dict[str, Any]:
    """Obtiene los benchmarks de la industria para un SIC o ticker integrando las medianas de los pares."""
    if peer_benchmarks_db is None:
        peer_benchmarks_db = load_peer_benchmarks()
    ind_peers = peer_benchmarks_db.get("industry_benchmarks", {})

    sic_clean = _clean_sic_code(sic_code)
    if not sic_clean and ticker:
        sic_clean = _clean_sic_code(medians_db.get("ticker_to_sic", {}).get(ticker.upper()))
    if not sic_clean and ticker:
        t_upper = ticker.upper()
        for k, v in ind_peers.items():
            if any(p.get("ticker", "").upper() == t_upper for p in v.get("peers", [])):
                sic_clean = _clean_sic_code(v.get("sic_code") or k.replace("SIC_", ""))
                break

    base_bm = None
    if sic_clean:
        base_bm = medians_db.get(f"SIC_{sic_clean}")
        if base_bm is None:
            base_bm = next(
                (v for v in medians_db.values() if isinstance(v, dict) and str(v.get("sic_code", "")).strip() == sic_clean),
                None,
            )

    if not base_bm:
        fallback_bm = dict(_DEFAULT_BROAD_MARKET)
        fallback_bm["sic_code"] = sic_clean or "0000"
        fallback_bm["industry_name"] = "Broad Market Benchmark"
        base_bm = medians_db.get("BROAD_MARKET", fallback_bm)

    benchmarks = dict(base_bm)
    if sic_clean and str(benchmarks.get("sic_code", "0000")) == "0000":
        benchmarks["sic_code"] = sic_clean

    peer_group = _find_peer_group(ind_peers, sic_clean, ticker, archetype)
    if peer_group and "peers" in peer_group:
        benchmarks.update(compute_peer_benchmarks(peer_group["peers"]))
        if str(benchmarks.get("sic_code", "0000")) == "0000" and peer_group.get("sic_code"):
            benchmarks["sic_code"] = str(peer_group.get("sic_code"))
        if benchmarks.get("industry_name") in (
            None,
            "",
            "Broad Market Benchmark",
            "Broad Market Benchmark (S&P 500 Non-Financials)",
        ):
            benchmarks["industry_name"] = peer_group.get("industry_name", benchmarks.get("industry_name"))
        benchmarks["peers_detail"] = peer_group.get("peers", [])
        benchmarks["peer_group_name"] = peer_group.get("industry_name", benchmarks.get("industry_name"))
        benchmarks["peer_count"] = len(peer_group.get("peers", []))
        benchmarks["peer_source"] = peer_group.get("source", "SEC EDGAR Form 10-K & 10-Q Audited Reports")
        benchmarks["dynamic_peer_medians"] = True

    return benchmarks


def _get_period_val(container: Dict[str, Any], key: str, period: str) -> Optional[float]:
    """Extrae un valor numérico de un diccionario de partidas para un período dado."""
    v = container.get(key)
    if isinstance(v, dict):
        vals = v.get("values", v)
        res = vals.get(period)
        if res is not None and not (isinstance(res, float) and math.isnan(res)):
            return float(res)
    return None


def _first_non_none(container: Dict[str, Any], keys: Iterable[str], period: str, positive_only: bool = False) -> Optional[float]:
    """Retorna la primera etiqueta XBRL con dato válido dentro del contenedor."""
    for key in keys:
        val = _get_period_val(container, key, period)
        if val is not None and (not positive_only or val > 0):
            return val
    return None


def _resolve_debt_components(
    summary: Dict[str, Any],
    bal_detail: Dict[str, Any],
    period: str,
) -> Tuple[float, float, float]:
    """Resuelve jerárquicamente deuda total, deuda de corto plazo y deuda de largo plazo."""
    tot_debt_canonical = _get_period_val(summary, "total_debt", period)
    combined_debt = _first_non_none(bal_detail, _COMBINED_DEBT_TAGS, period)
    lt_debt = _first_non_none(bal_detail, _LT_DEBT_TAGS, period)
    st_debt = _first_non_none(bal_detail, _ST_DEBT_TAGS, period)

    if combined_debt is not None:
        debt = combined_debt
        if lt_debt is None:
            lt_debt = debt - (st_debt or 0.0)
    elif lt_debt is not None and st_debt is not None:
        debt = lt_debt + st_debt
    elif tot_debt_canonical is not None and tot_debt_canonical > 0:
        debt = tot_debt_canonical
    elif lt_debt is not None:
        debt = lt_debt
    elif st_debt is not None:
        debt = st_debt
    elif tot_debt_canonical is not None:
        debt = tot_debt_canonical
    else:
        debt = 0.0

    if debt <= 0.0 and tot_debt_canonical is not None and tot_debt_canonical > 0.0:
        debt = tot_debt_canonical

    if tot_debt_canonical is not None and debt == tot_debt_canonical and tot_debt_canonical > 0:
        if (lt_debt or 0.0) + (st_debt or 0.0) == 0.0:
            lt_debt, st_debt = debt, 0.0
        elif lt_debt is None and st_debt is not None:
            lt_debt = max(0.0, debt - st_debt)
        elif st_debt is None and lt_debt is not None:
            st_debt = max(0.0, debt - lt_debt)

    return debt, (st_debt or 0.0), (lt_debt or 0.0)


def _first_present(*values: Optional[float]) -> Optional[float]:
    """Retorna el primer valor no nulo conservando el cero contable (0.0)."""
    for v in values:
        if v is not None:
            return v
    return None


def _extract_working_capital_and_ppe(
    summary: Dict[str, Any],
    inc_detail: Dict[str, Any],
    bal_detail: Dict[str, Any],
    cf_detail: Dict[str, Any],
    period: str,
    total_liquid_cash: float,
    ca: Optional[float],
    net_ppe: Optional[float],
    rev: Optional[float],
    gp: Optional[float],
) -> Dict[str, Optional[float]]:
    """Extrae cuentas por cobrar, inventarios, COGS, D&A, otros activos corrientes y PP&E bruto."""
    ar = _first_non_none(
        bal_detail,
        ("AccountsReceivableNetCurrent", "AccountsReceivableNet", "ReceivablesNetCurrent", "AccountsAndOtherReceivablesNetCurrent"),
        period,
    )
    inv = _first_non_none(bal_detail, ("InventoryNet", "Inventories", "InventoryGross"), period)
    cogs = _get_period_val(summary, "cost_of_goods_sold", period)
    if cogs is None:
        cogs = _first_non_none(inc_detail, ("CostOfGoodsAndServicesSold", "CostOfGoodsSold", "CostOfRevenue"), period)
    if cogs is None and rev is not None and gp is not None:
        cogs = rev - gp

    dna = _first_non_none(
        cf_detail,
        ("DepreciationDepletionAndAmortization", "DepreciationAmortizationAndAccretionNet", "DepreciationAndAmortization"),
        period,
    )
    if dna is None:
        depr = _get_period_val(cf_detail, "Depreciation", period)
        if depr is not None:
            dna = depr + (_get_period_val(cf_detail, "AmortizationOfIntangibleAssets", period) or 0.0)
    if dna is None:
        dna = _first_non_none(inc_detail, ("DepreciationAndAmortization", "Depreciation"), period)

    oac_val = _get_period_val(summary, "other_current_assets", period)
    if oac_val is None:
        oac_val = _first_non_none(bal_detail, _OTHER_CURRENT_ASSETS_TAGS, period)
    prepaid_val = _first_present(
        _get_period_val(bal_detail, "PrepaidExpenseCurrent", period),
        _get_period_val(bal_detail, "us-gaap_PrepaidExpenseCurrent", period),
        0.0,
    )
    if oac_val is not None:
        other_current_assets = oac_val + (prepaid_val or 0.0)
    elif ca is not None and ar is not None:
        residual_oca = ca - (total_liquid_cash + ar + (inv or 0.0))
        other_current_assets = max(0.0, residual_oca) if residual_oca > 0 else None
    else:
        other_current_assets = None

    gross_ppe = _get_period_val(summary, "gross_ppe", period)
    if gross_ppe is None:
        gross_ppe = _first_non_none(bal_detail, _GROSS_PPE_TAGS, period)
    accum_depr = _first_non_none(
        bal_detail,
        (
            "AccumulatedDepreciationDepletionAndAmortizationPropertyPlantAndEquipment",
            "us-gaap_AccumulatedDepreciationDepletionAndAmortizationPropertyPlantAndEquipment",
            "PropertyPlantAndEquipmentAccumulatedDepreciation",
        ),
        period,
    )
    accum_depr = abs(accum_depr) if accum_depr is not None else None
    if gross_ppe is None and net_ppe is not None and accum_depr is not None:
        gross_ppe = net_ppe + accum_depr

    return {
        "ar": ar,
        "inv": inv,
        "cogs": cogs,
        "dna": dna,
        "other_current_assets": other_current_assets,
        "gross_ppe": gross_ppe,
        "accum_depr": accum_depr,
    }


def extract_period_metrics(financials: Dict[str, Any], period: str) -> Dict[str, Any]:
    """Extrae las variables contables estandarizadas de un período desde financial_statements.json."""
    summary = financials.get("canonical_summary", {})
    inc_detail = financials.get("income_statement_detail", {})
    bal_detail = financials.get("balance_sheet_detail", {})
    cf_detail = financials.get("cash_flow_detail", {})
    arch_norm = normalize_archetype(
        financials.get("archetype") or financials.get("company_archetype"),
        default="STANDARD_CORPORATE",
    )

    ni = _first_present(_get_period_val(summary, "net_income", period), _get_period_val(inc_detail, "NetIncomeLoss", period))
    cfo = _first_present(
        _get_period_val(summary, "cash_from_operations", period),
        _get_period_val(cf_detail, "NetCashProvidedByUsedInOperatingActivities", period),
    )
    assets = _first_present(_get_period_val(summary, "total_assets", period), _get_period_val(bal_detail, "Assets", period))
    debt, st_debt, lt_debt = _resolve_debt_components(summary, bal_detail, period)
    ca = _get_period_val(bal_detail, "AssetsCurrent", period)
    cl = _get_period_val(bal_detail, "LiabilitiesCurrent", period)

    basic_shares = _first_present(
        _get_period_val(summary, "shares_basic", period),
        _get_period_val(inc_detail, "WeightedAverageNumberOfSharesOutstandingBasic", period),
        _get_period_val(summary, "shares_diluted", period),
        _get_period_val(inc_detail, "WeightedAverageNumberOfDilutedSharesOutstanding", period),
        _get_period_val(bal_detail, "CommonStockSharesOutstanding", period),
    )
    diluted_shares = _first_present(
        _get_period_val(summary, "shares_diluted", period),
        _get_period_val(inc_detail, "WeightedAverageNumberOfDilutedSharesOutstanding", period),
        basic_shares,
    )

    rev = _first_present(
        _get_period_val(summary, "revenue", period),
        _first_non_none(inc_detail, ("RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues"), period),
    )
    gp = None
    if arch_norm not in ("FINANCIAL_BANKING", "INSURANCE"):
        gp = _first_present(_get_period_val(summary, "gross_profit", period), _get_period_val(inc_detail, "GrossProfit", period))
        if gp is None and arch_norm == "REAL_ESTATE_REIT":
            gp = _get_period_val(summary, "noi", period)

    rd = _get_period_val(inc_detail, "ResearchAndDevelopmentExpense", period) or 0.0
    capex = _first_present(
        _get_period_val(summary, "capital_expenditures", period),
        _get_period_val(cf_detail, "PaymentsToAcquirePropertyPlantAndEquipment", period),
        0.0,
    )
    sga = _first_present(
        _get_period_val(inc_detail, "SellingGeneralAndAdministrativeExpense", period),
        _get_period_val(inc_detail, "OperatingExpenses", period),
    )

    cash = _first_present(
        _get_period_val(summary, "cash_and_equivalents", period),
        _first_non_none(
            bal_detail,
            ("CashAndCashEquivalentsAtCarryingValue", "CashAndCashEquivalents", "CashCashEquivalentsAndShortTermInvestments"),
            period,
        ),
        0.0,
    )
    st_inv = _first_present(
        _get_period_val(summary, "short_term_investments", period),
        _first_non_none(bal_detail, _ST_INV_TAGS, period, positive_only=True),
        0.0,
    )
    total_liquid_cash = (cash or 0.0) + (st_inv or 0.0)

    ebit = _first_present(_get_period_val(summary, "operating_income", period), _get_period_val(inc_detail, "OperatingIncomeLoss", period))
    net_ppe = _first_present(
        _get_period_val(summary, "net_ppe", period),
        _first_non_none(
            bal_detail,
            (
                "PropertyPlantAndEquipmentNet",
                "PropertyPlantAndEquipmentAndFinanceLeaseRightOfUseAssetAfterAccumulatedDepreciationAndAmortization",
                "PropertyPlantAndEquipment",
            ),
            period,
        ),
    )

    raw_interest = _first_present(
        _get_period_val(summary, "interest_expense", period),
        _first_non_none(
            inc_detail,
            (
                "InterestExpense",
                "InterestExpenseOperating",
                "meli_InterestExpenseAndOtherFinancialCharges",
                "InterestExpenseDebt",
                "InterestExpenseNonoperating",
                "InterestAndDebtExpense",
            ),
            period,
        ),
        _get_period_val(cf_detail, "InterestPaidNet", period),
    )
    interest = abs(float(raw_interest)) if raw_interest is not None else None

    goodwill = _get_period_val(bal_detail, "Goodwill", period) or 0.0
    intangibles = _first_present(
        _get_period_val(bal_detail, "IntangibleAssetsNetExcludingGoodwill", period),
        _get_period_val(bal_detail, "IntangibleAssetsNet", period),
        0.0,
    )
    tax_exp = _first_present(_get_period_val(summary, "income_tax_expense", period), _get_period_val(inc_detail, "IncomeTaxExpenseBenefit", period))
    ebt = _first_present(
        _get_period_val(summary, "income_before_tax", period),
        _first_non_none(
            inc_detail,
            (
                "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
                "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
            ),
            period,
        ),
    )
    eff_tax_rate = max(0.05, min(0.35, tax_exp / ebt)) if (tax_exp is not None and ebt is not None and ebt > 0) else 0.21

    equity = _first_present(
        _get_period_val(summary, "stockholders_equity", period),
        _first_non_none(bal_detail, ("StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"), period),
    )
    retained_earnings = _first_non_none(bal_detail, ("RetainedEarningsAccumulatedDeficit", "RetainedEarnings"), period)
    total_liabilities = _first_present(_get_period_val(summary, "total_liabilities", period), _get_period_val(bal_detail, "Liabilities", period))
    if total_liabilities is None and assets is not None and equity is not None:
        total_liabilities = assets - equity

    wc_ppe = _extract_working_capital_and_ppe(
        summary, inc_detail, bal_detail, cf_detail, period, total_liquid_cash, ca, net_ppe, rev, gp
    )

    return {
        "net_income": ni,
        "cfo": cfo,
        "total_assets": assets,
        "total_debt": debt,
        "short_term_debt": st_debt,
        "long_term_debt": lt_debt,
        "current_assets": ca,
        "current_liabilities": cl,
        "stockholders_equity": equity,
        "retained_earnings": retained_earnings,
        "total_liabilities": total_liabilities,
        "basic_shares": basic_shares,
        "diluted_shares": diluted_shares,
        "gross_profit": gp,
        "revenue": rev,
        "rd_expense": rd,
        "capex": abs(capex) if capex is not None else 0.0,
        "sga_expense": sga,
        "cash": cash,
        "short_term_investments": st_inv,
        "total_liquid_cash": total_liquid_cash,
        "operating_income": ebit,
        "net_ppe": net_ppe,
        "gross_ppe": wc_ppe["gross_ppe"],
        "accumulated_depreciation": wc_ppe["accum_depr"],
        "other_current_assets": wc_ppe["other_current_assets"],
        "interest_expense": interest,
        "goodwill": goodwill,
        "intangible_assets": intangibles,
        "effective_tax_rate": eff_tax_rate,
        "accounts_receivable": wc_ppe["ar"],
        "inventory": wc_ppe["inv"],
        "cost_of_goods_sold": wc_ppe["cogs"],
        "depreciation_and_amortization": wc_ppe["dna"],
        "ffo": _get_period_val(summary, "ffo", period),
        "affo": _get_period_val(summary, "affo", period),
        "real_estate_depreciation": _get_period_val(summary, "real_estate_depreciation", period),
    }
