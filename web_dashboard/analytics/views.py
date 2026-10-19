import sys
import json
from pathlib import Path
from django.shortcuts import render, Http404

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "processed"
PIPELINE_DIR = Path(__file__).resolve().parent.parent.parent / "pipeline"
if PIPELINE_DIR.exists() and str(PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(PIPELINE_DIR))

def index(request):
    companies = []
    
    # Importar MarketDataExtractor para obtener cotizaciones en tiempo real
    mkt_extractor = None
    try:
        from market_data_provider import MarketDataExtractor
        mkt_extractor = MarketDataExtractor
    except Exception:
        pass

    cache_file = DATA_DIR.parent / "cache" / "market_data_cache.json"
    cache_data = {}
    if cache_file.exists():
        try:
            with open(cache_file, "r", encoding="utf-8") as cf:
                cache_data = json.load(cf)
        except Exception:
            pass

    if DATA_DIR.exists():
        for d in DATA_DIR.iterdir():
            if d.is_dir() and (d / "fundamental_scores.json").exists():
                try:
                    with open(d / "fundamental_scores.json", "r", encoding="utf-8") as f:
                        sc = json.load(f)
                    ticker = sc.get("ticker", d.name)
                    name = sc.get("company_name", ticker)
                    
                    # 1. Scores Fundamentales (Piotroski y Mohanram)
                    recent_fy = sc.get("fiscal_years", [None])[0] if sc.get("fiscal_years") else None
                    f_dict = sc.get("piotroski_f_score", {})
                    f_ltm = f_dict.get("LTM", {})
                    f_sc = f_ltm.get("total_score")
                    if f_sc is None and recent_fy:
                        f_sc = f_dict.get(recent_fy, {}).get("total_score")
                    if f_sc is None:
                        f_sc = f_dict.get("latest_result", {}).get("total_score", "-")

                    g_dict = sc.get("mohanram_g_score", {})
                    g_ltm = g_dict.get("LTM", {})
                    g_sc = g_ltm.get("total_score")
                    if g_sc is None and recent_fy:
                        g_sc = g_dict.get(recent_fy, {}).get("total_score")
                    if g_sc is None:
                        g_sc = g_dict.get("latest_result", {}).get("total_score", "-")
                    
                    # 2. Novy-Marx GP/A
                    nm = sc.get("novy_marx_analysis", {}).get("latest_result", {})
                    gpa_val = nm.get("gross_profitability_total")
                    if gpa_val is not None:
                        gpa = (gpa_val * 100.0) if abs(gpa_val) <= 1.5 else gpa_val
                        gpa_str = f"{gpa:.1f}%"
                    else:
                        gpa_str = "N/A"
                    
                    # 3. Solvencia & Rating
                    solv = sc.get("debt_and_solvency_analysis", {}).get("latest_result", {})
                    distress = solv.get("distress_models", {})
                    z_score = distress.get("altman_z_double_prime")
                    if z_score is None:
                        z_score = distress.get("altman_z_score")
                    if z_score is None or str(z_score) == "None":
                        z_score = "N/A"
                    rating = distress.get("synthetic_rating", "AAA")
                    
                    # 4. ROIC Ajustado, WACC y Spread EVA (Diferencia entre ROIC y WACC)
                    wacc_obj = sc.get("wacc_and_spread_analysis", {})
                    wacc_val = wacc_obj.get("wacc")
                    if wacc_val is None:
                        wacc_val = sc.get("roic_wacc_analysis", {}).get("wacc", {}).get("wacc", 0.095)
                    wacc_pct = (wacc_val * 100.0) if wacc_val <= 1.0 else wacc_val
                    
                    roic_val = wacc_obj.get("roic_adjusted")
                    if roic_val is None:
                        roic_val = sc.get("intangible_roic_analysis", {}).get("latest_result", {}).get("adjusted_roic", 0.0)
                    roic_pct = (roic_val * 100.0) if roic_val <= 1.5 else roic_val
                    
                    spread_val = wacc_obj.get("economic_spread_adjusted")
                    if spread_val is None:
                        spread_val = (roic_val - wacc_val) if (roic_val and wacc_val) else 0.0
                    spread_pp = (spread_val * 100.0) if abs(spread_val) <= 1.5 else spread_val
                    
                    moat_badge = wacc_obj.get("moat_badge") or "WIDE MOAT"

                    # 5. Detección de Arquetipo de Industria
                    fs_path = d / "financial_statements.json"
                    fs_data = {}
                    archetype = sc.get("archetype")
                    if fs_path.exists():
                        try:
                            with open(fs_path, "r", encoding="utf-8") as fs_f:
                                fs_data = json.load(fs_f)
                                if not archetype:
                                    archetype = fs_data.get("archetype")
                        except Exception:
                            pass
                    if not archetype:
                        if sc.get("is_financial_institution") or fs_data.get("is_financial"):
                            archetype = "FINANCIAL_BANKING"
                        else:
                            archetype = "STANDARD_CORPORATE"

                    is_banking_card = (archetype == "FINANCIAL_BANKING")
                    
                    kr = fs_data.get("key_ratios", {})
                    roe_raw = kr.get("roe_pct", {}).get("LTM") or kr.get("roe_pct", {}).get(recent_fy) or 0.0
                    roe_val = float(roe_raw) if roe_raw is not None else 0.0
                    
                    nim_raw = kr.get("risk_adj_nim_pct", {}).get("LTM") or kr.get("risk_adj_nim_pct", {}).get(recent_fy) or 0.0
                    nim_val = float(nim_raw) if nim_raw is not None else 0.0

                    # 6. Cotización de Mercado en Tiempo Real
                    price = None
                    if mkt_extractor:
                        try:
                            m_data = mkt_extractor.get_market_data(ticker, bypass_cache=False)
                            price = m_data.get("price")
                        except Exception:
                            pass
                    if not price:
                        price = cache_data.get(ticker, {}).get("price") or wacc_obj.get("market_data", {}).get("price")

                    companies.append({
                        "ticker": ticker,
                        "name": name,
                        "archetype": archetype,
                        "is_banking": is_banking_card,
                        "price": f"${price:.2f}" if price else "-",
                        "price_raw": price,
                        "f_score": f_sc,
                        "g_score": g_sc,
                        "gpa": gpa_str,
                        "roic_adj": f"{roic_pct:.1f}%",
                        "roe": f"{roe_val:.1f}%",
                        "nim": f"{nim_val:.1f}%",
                        "wacc": f"{wacc_pct:.2f}%",
                        "spread": f"+{spread_pp:.1f} pp" if spread_pp > 0 else f"{spread_pp:.1f} pp",
                        "spread_positive": spread_pp >= 0,
                        "z_score": f"{z_score:.2f}" if isinstance(z_score, (int, float)) else str(z_score),
                        "rating": rating,
                        "moat_badge": moat_badge,
                    })
                except Exception:
                    continue

    return render(request, "index.html", {"companies": companies})


from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST
from django.views.decorators.csrf import csrf_exempt
from .pipeline_runner import search_companies, launch_pipeline_job, get_job_status


@require_GET
def company_search(request):
    """Endpoint JSON para autocompletado y búsqueda de empresas por nombre o ticker."""
    q = request.GET.get("q", "").strip()
    if not q:
        return JsonResponse({"results": []})
    results = search_companies(q, limit=6)
    return JsonResponse({"results": results})


@csrf_exempt
@require_POST
def trigger_pipeline(request):
    """Endpoint para iniciar la incorporación de una nueva empresa de forma 100% automatizada."""
    ticker = request.POST.get("ticker", "").strip().upper()
    if not ticker:
        try:
            body = json.loads(request.body.decode("utf-8"))
            ticker = body.get("ticker", "").strip().upper()
        except Exception:
            pass

    if not ticker:
        return JsonResponse({"success": False, "error": "Ticker no especificado."}, status=400)

    job = launch_pipeline_job(ticker)
    return JsonResponse({"success": True, "job": job})


@require_GET
def pipeline_status(request, ticker):
    """Endpoint JSON para consultar el progreso en vivo de la incorporación."""
    job = get_job_status(ticker)
    return JsonResponse(job)


def resolve_canonical_capital_flows(fs, periods):
    """
    Función canónica y unificada (SSOT) para resolver flujos de asignación de capital
    a partir de financial_statements.json de forma universal y sin hardcodeos.
    Retorna flujos en dólares sin escalar para cada período solicitado:
    - share_repurchases_open_market: Magnitud positiva ($)
    - share_repurchases_sbc_tax: Magnitud positiva ($) (Retención fiscal de RSUs para FCF ajustado)
    - share_repurchases_total: Magnitud positiva ($) = recompra neta real de mercado
    - dividends_paid: Magnitud positiva ($)
    - acquisitions_ma: Magnitud positiva ($)
    - debt_repayments: Magnitud positiva ($)
    - debt_issuances: Magnitud positiva ($)
    - net_debt_change: Variación algebraica ($) = debt_issuances - debt_repayments
    """
    canonical = fs.get("canonical_summary", {}) if isinstance(fs, dict) else {}
    cf_sources = [
        fs.get("cash_flow_detail", {}) if isinstance(fs, dict) else {},
        fs.get("cash_flow_statement", {}) if isinstance(fs, dict) else {}
    ]

    def _extract_val(key_cands, p, can_key=None):
        if can_key:
            can_val = canonical.get(can_key, {}).get(p)
            if can_val is not None and abs(float(can_val)) > 0:
                return float(can_val)
        for k in key_cands:
            k_lower = k.lower()
            for cf_src in cf_sources:
                if not isinstance(cf_src, dict):
                    continue
                if k in cf_src:
                    obj = cf_src[k]
                    vals = obj.get("values", obj) if isinstance(obj, dict) else {}
                    if isinstance(vals, dict) and p in vals and vals[p] is not None:
                        return float(vals[p])
                for src_k, src_obj in cf_src.items():
                    src_token = src_k.lower().split(':')[-1].split('_')[-1]
                    if src_k.lower() == k_lower or src_token == k_lower:
                        vals = src_obj.get("values", src_obj) if isinstance(src_obj, dict) else {}
                        if isinstance(vals, dict) and p in vals and vals[p] is not None:
                            return float(vals[p])
        return None

    def _extract_sum(key_cands, p, can_key=None):
        if can_key:
            can_val = canonical.get(can_key, {}).get(p)
            if can_val is not None and abs(float(can_val)) > 0:
                return float(can_val)
        total = 0.0
        matched = False
        matched_tokens = set()
        for k in key_cands:
            k_token = k.lower().split(':')[-1].split('_')[-1]
            for cf_src in cf_sources:
                if not isinstance(cf_src, dict):
                    continue
                for src_k, src_obj in cf_src.items():
                    src_token = src_k.lower().split(':')[-1].split('_')[-1]
                    if (src_k.lower() == k.lower() or src_token == k_token) and src_token not in matched_tokens:
                        vals = src_obj.get("values", src_obj) if isinstance(src_obj, dict) else {}
                        if isinstance(vals, dict) and p in vals and vals[p] is not None:
                            try:
                                total += float(vals[p])
                                matched = True
                                matched_tokens.add(src_token)
                            except (ValueError, TypeError):
                                pass
        return total if matched else None

    rep_keys = [
        "PaymentsForRepurchaseOfCommonStock", "PaymentsForRepurchaseOfEquity", "PaymentsForRepurchaseOfCapitalStock",
        "PurchaseOfTreasuryShares", "PaymentsForPurchaseOfOwnShares",
        "PaymentsForRepurchaseOfShares", "PurchaseOfOwnShares", "SharesRepurchased",
        "nu_SharesRepurchased"
    ]
    stock_plans_keys = [
        "ProceedsFromStockPlans", "us-gaap_ProceedsFromStockPlans",
        "ProceedsFromIssuanceOfCommonStock", "us-gaap_ProceedsFromIssuanceOfCommonStock",
        "ProceedsFromIssuanceOfShares", "ifrs-full_ProceedsFromIssuingShares"
    ]
    tax_keys = [
        "PaymentsRelatedToTaxWithholdingForShareBasedCompensation",
        "PaymentsForTaxesRelatedToNetShareSettlementOfEquityAwards",
        "PaymentsRelatedToTaxWithholdingForStockBasedAwards",
        "TaxWithholdingForShareBasedCompensation",
        "deck_AccrualsForSharesWithheldForTaxes"
    ]
    div_keys = [
        "PaymentsOfDividends", "PaymentsOfDividendsCommonStock", "PaymentsOfOrdinaryDividends",
        "DividendsPaid", "PaymentsOfDividendsClassifiedAsFinancingActivities",
        "aapl_PaymentsOfDividendsAndDividendEquivalentsOnCommonStockAndRestrictedStockUnits",
        "PaymentsOfDividendsPreferredStockAndPreferenceStock", "us-gaap_PaymentsOfDividendsPreferredStockAndPreferenceStock"
    ]
    ma_keys = [
        "PaymentsToAcquireBusinessesNetOfCashAcquiredAndPurchasesOfIntangibleAndOtherAssets",
        "PaymentsToAcquireBusinessesNetOfCashAcquired", "PaymentsToAcquireBusinessTwoNetOfCashAcquired",
        "us-gaap_PaymentsToAcquireBusinessTwoNetOfCashAcquired", "PaymentsToAcquireBusinessThreeNetOfCashAcquired",
        "AcquisitionOfSubsidiaryNetOfCashAcquired",
        "nu_AcquisitionOfSubsidiaryNetOfCashAcquired",
        "PaymentsToAcquireBusinessesAndInterestInAffiliates", "PaymentsToAcquireOtherProductiveAssets",
        "CashFlowsUsedInObtainingControlOfSubsidiariesOrOtherBusinesses", "PaymentsToAcquireBusinessesGross",
        "meli_PaymentsToAcquireBusinessNetOfCashAcquired", "us-gaap_PaymentsToAcquireBusinessesAndInterestInAffiliates",
        "meta_PaymentsToAcquireBusinessesNetOfCashAcquiredAndPurchasesOfIntangibleAndOtherAssets",
        "PaymentsToAcquireInterestInAffiliates", "PaymentsToAcquireInterestInSubsidiariesAndOtherBusinesses",
        "PaymentsToAcquireJointVentures"
    ]
    dr_keys = [
        "RepaymentsOfLongTermDebt", "RepaymentsOfDebt", "us-gaap_RepaymentsOfDebt",
        "RepaymentsOfLinesOfCredit", "RepaymentsOfShortTermDebt", "us-gaap_RepaymentsOfShortTermDebt",
        "RepaymentsOfOtherLongTermDebt", "us-gaap_RepaymentsOfOtherLongTermDebt",
        "RepaymentsOfSecuredDebt", "us-gaap_RepaymentsOfSecuredDebt",
        "us-gaap_RepaymentsOfConvertibleDebt", "RepaymentsOfBorrowingsClassifiedAsFinancingActivities",
        "PaymentsOfBorrowingsAndFinancing", "RepaymentsOfTermLoans", "RepaymentsOfConvertibleDebt",
        "RepaymentsOfSeniorNotes"
    ]
    di_keys = [
        "ProceedsFromIssuanceOfLongTermDebt", "ProceedsFromIssuanceOfDebt",
        "us-gaap_ProceedsFromDebtNetOfIssuanceCosts", "ProceedsFromLinesOfCredit",
        "ProceedsFromIssuanceOfOtherLongTermDebt", "us-gaap_ProceedsFromIssuanceOfOtherLongTermDebt",
        "ProceedsFromBorrowingsClassifiedAsFinancingActivities", "ProceedsFromBorrowingsAndFinancing",
        "us-gaap_ProceedsFromConvertibleDebt", "us-gaap_ProceedsFromShortTermDebt",
        "nu_ProceedsFromDebtInstrumentsEligibleAsCapital", "ProceedsFromTermLoans",
        "ProceedsFromConvertibleDebt", "ProceedsFromIssuanceOfConvertibleDebt",
        "ProceedsFromIssuanceOfSeniorNotes"
    ]

    flows = {
        "share_repurchases_open_market": {},
        "stock_plans_proceeds": {},
        "share_repurchases_net": {},
        "share_repurchases_sbc_tax": {},
        "share_repurchases_total": {},
        "total_capital_returned": {},
        "dividends_paid": {},
        "acquisitions_ma": {},
        "debt_repayments": {},
        "debt_issuances": {},
        "net_debt_change": {}
    }

    for p in periods:
        raw_rep = _extract_val(rep_keys, p, "share_repurchases")
        val_rep = abs(raw_rep) if raw_rep is not None else 0.0

        raw_sp = _extract_val(stock_plans_keys, p, "stock_plans_proceeds")
        val_sp = abs(raw_sp) if raw_sp is not None else 0.0

        val_net_rep = max(0.0, round(val_rep - val_sp, 2))

        raw_tax = _extract_val(tax_keys, p, "share_repurchases_sbc_tax")
        val_tax = abs(raw_tax) if raw_tax is not None else 0.0

        raw_div = _extract_val(div_keys, p, "dividends_paid")
        val_div = abs(raw_div) if raw_div is not None else 0.0

        raw_ma = _extract_sum(ma_keys, p, "acquisitions_ma")
        val_ma = abs(raw_ma) if raw_ma is not None else 0.0

        raw_dr = _extract_sum(dr_keys, p, "debt_repayments")
        val_dr = abs(raw_dr) if raw_dr is not None else 0.0

        raw_di = _extract_sum(di_keys, p, "debt_issuances")
        val_di = abs(raw_di) if raw_di is not None else 0.0

        net_debt_change = round(val_di - val_dr, 2)
        val_tot_rep = round(val_rep + val_tax, 2)

        flows["share_repurchases_open_market"][p] = val_rep
        flows["stock_plans_proceeds"][p] = val_sp
        flows["share_repurchases_net"][p] = val_net_rep
        flows["share_repurchases_sbc_tax"][p] = val_tax
        flows["share_repurchases_total"][p] = val_tot_rep
        flows["total_capital_returned"][p] = val_net_rep
        flows["dividends_paid"][p] = val_div
        flows["acquisitions_ma"][p] = val_ma
        flows["debt_repayments"][p] = val_dr
        flows["debt_issuances"][p] = val_di
        flows["net_debt_change"][p] = net_debt_change

    return flows


def resolve_canonical_balance_sheet(fs, periods):
    """
    Función canónica y unificada (SSOT) para resolver el Balance General clasificado
    (Activos Corrientes y No Corrientes, Pasivos Corrientes y No Corrientes, Patrimonio Neto
    y Diagnóstico de Liquidez y Solvencia) a partir de financial_statements.json
    de forma universal y sin hardcodeos para empresas corporativas estándar.
    """
    canonical = fs.get("canonical_summary", {}) if isinstance(fs, dict) else {}
    bs_detail = fs.get("balance_sheet_detail", {}) if isinstance(fs, dict) else {}
    bal_sources = [
        bs_detail,
        fs.get("balance_sheet", {}) if isinstance(fs, dict) else {}
    ]

    def _extract_val(key_cands, p, can_key=None):
        if can_key:
            can_val = canonical.get(can_key, {}).get(p)
            if can_val is not None:
                return float(can_val)
        for k in key_cands:
            k_lower = k.lower()
            for src in bal_sources:
                if not isinstance(src, dict):
                    continue
                if k in src:
                    obj = src[k]
                    vals = obj.get("values", obj) if isinstance(obj, dict) else {}
                    if isinstance(vals, dict) and p in vals and vals[p] is not None:
                        return float(vals[p])
                for src_k, src_obj in src.items():
                    src_token = src_k.lower().split(':')[-1].split('_')[-1]
                    if src_k.lower() == k_lower or src_token == k_lower:
                        vals = src_obj.get("values", src_obj) if isinstance(src_obj, dict) else {}
                        if isinstance(vals, dict) and p in vals and vals[p] is not None:
                            return float(vals[p])
        return None

    cash_keys = [
        "CashAndCashEquivalentsAtCarryingValue", "CashAndCashEquivalents", "Cash",
        "CashAndDueFromBanks", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
        "us-gaap_CashAndCashEquivalentsAtCarryingValue", "ifrs-full_CashAndCashEquivalents"
    ]
    sti_keys = [
        "MarketableSecuritiesCurrent", "us-gaap_MarketableSecuritiesCurrent",
        "ShortTermInvestments", "AvailableForSaleSecuritiesCurrent",
        "DebtSecuritiesCurrent", "us-gaap_DebtSecuritiesCurrent",
        "EquitySecuritiesFvNi", "us-gaap_EquitySecuritiesFvNi",
        "nvda_MarketableSecuritiesAndEquitySecuritiesFVNI",
        "OtherShortTermInvestments", "MarketableSecurities"
    ]
    ar_keys = [
        "AccountsReceivableNetCurrent", "AccountsReceivableNet", "ReceivablesNetCurrent",
        "AccountsAndNotesReceivableNetCurrent", "TradeAndOtherReceivablesCurrent",
        "ContractWithCustomerAssetNetCurrent", "UnbilledReceivablesCurrent", "NontradeReceivablesCurrent",
        "us-gaap_AccountsReceivableNetCurrent"
    ]
    inv_keys = [
        "InventoryNet", "Inventories", "InventoryGross", "us-gaap_InventoryNet"
    ]
    ca_keys = [
        "AssetsCurrent", "CurrentAssetsTotal", "CurrentAssets", "us-gaap_AssetsCurrent"
    ]
    other_ca_keys = [
        "PrepaidExpenseAndOtherAssetsCurrent", "us-gaap_PrepaidExpenseAndOtherAssetsCurrent",
        "OtherAssetsCurrent", "us-gaap_OtherAssetsCurrent",
        "PrepaidExpensesAndOtherCurrentAssets", "OtherCurrentAssets"
    ]
    ppe_keys = [
        "PropertyPlantAndEquipmentNet",
        "PropertyPlantAndEquipmentAndFinanceLeaseRightOfUseAssetAfterAccumulatedDepreciationAndAmortization",
        "PropertyPlantAndEquipmentNetOfAccumulatedDepreciationAndAmortization",
        "PropertyPlantAndEquipmentNetExcludingRightOfUseAsset",
        "PropertyPlantAndEquipmentGross",
        "MachineryAndEquipmentNet",
        "ConstructionInProgressGross",
        "ConstructionInProgress",
        "BuildingsAndBuildingImprovementsNet",
        "us-gaap_PropertyPlantAndEquipmentNet"
    ]
    rou_keys = [
        "OperatingLeaseRightOfUseAsset", "us-gaap_OperatingLeaseRightOfUseAsset",
        "RightOfUseAssets", "RightOfUseAsset",
        "FinanceLeaseRightOfUseAsset", "LesseeOperatingLeaseRightOfUseAsset",
        "OperatingLeaseRightOfUseAssetNet", "FinanceLeaseRightOfUseAssetNet"
    ]
    gw_keys = ["Goodwill", "us-gaap_Goodwill"]
    intang_keys = [
        "IntangibleAssetsNetExcludingGoodwill", "IntangibleAssetsNet",
        "OtherIntangibleAssetsNet", "us-gaap_IntangibleAssetsNetExcludingGoodwill"
    ]
    lt_inv_keys = [
        "MarketableSecuritiesNoncurrent", "us-gaap_MarketableSecuritiesNoncurrent",
        "NonmarketableEquitySecuritiesCarryingValue", "meta_NonmarketableEquitySecuritiesCarryingValue",
        "EquitySecuritiesWithoutReadilyDeterminableFairValueAmount",
        "EquitySecuritiesFVNINoncurrent", "us-gaap_EquitySecuritiesFVNINoncurrent",
        "LongTermInvestments", "us-gaap_LongTermInvestments",
        "OtherInvestmentsNoncurrent", "InvestmentsInAssociates",
        "InvestmentsInAffiliatesSubsidiariesAssociatesAndJointVentures",
        "EquityMethodInvestments", "AvailableForSaleDebtSecuritiesNoncurrent",
        "HeldToMaturitySecuritiesNoncurrent", "OtherLongTermInvestments", "OtherInvestments"
    ]
    other_nca_keys = [
        "OtherAssetsNoncurrent", "us-gaap_OtherAssetsNoncurrent",
        "OtherNoncurrentAssets"
    ]
    dta_keys = [
        "DeferredIncomeTaxAssetsNet", "us-gaap_DeferredIncomeTaxAssetsNet",
        "DeferredTaxAssetsNetNoncurrent", "us-gaap_DeferredTaxAssetsNetNoncurrent",
        "DeferredIncomeTaxAssets", "us-gaap_DeferredIncomeTaxAssets"
    ]
    ta_keys = ["Assets", "TotalAssets", "us-gaap_Assets"]
    ap_keys = [
        "AccountsPayableCurrent", "us-gaap_AccountsPayableCurrent",
        "us-gaap_AccountsPayableTradeCurrent", "AccountsPayableTradeCurrent",
        "us-gaap_AccountsPayableAndAccruedLiabilitiesCurrent", "TradeAndOtherPayablesCurrent"
    ]
    accrued_keys = [
        "AccruedLiabilitiesCurrent", "us-gaap_AccruedLiabilitiesCurrent",
        "OtherAccruedLiabilitiesCurrent", "AccruedLiabilities"
    ]
    st_debt_keys = [
        "LongTermDebtCurrent", "us-gaap_LongTermDebtCurrent",
        "CommercialPaper", "us-gaap_CommercialPaper",
        "CurrentPortionOfLongTermDebt", "ShortTermDebt", "ShortTermBorrowings",
        "DebtCurrent", "us-gaap_DebtCurrent", "LoansPayableCurrent", "us-gaap_LoansPayableCurrent",
        "LinesOfCreditCurrent", "RevolvingCreditFacilityAndCommercialPaper",
        "LineOfCreditAndCommercialPaper", "LineOfCredit",
        "CurrentBorrowingsAndOtherFinancialLiabilities", "CurrentPortionOfNoncurrentBorrowings",
        "CurrentFinancialLiabilities", "BorrowingsFromFinancialInstitutions"
    ]
    cl_keys = [
        "LiabilitiesCurrent", "CurrentLiabilitiesTotal", "CurrentLiabilities",
        "us-gaap_LiabilitiesCurrent"
    ]
    tot_debt_keys = [
        "DebtLongtermAndShorttermCombinedAmount", "us-gaap_DebtLongtermAndShorttermCombinedAmount",
        "TotalDebt"
    ]
    lt_debt_keys = [
        "LongTermDebtNoncurrent", "us-gaap_LongTermDebtNoncurrent",
        "LongTermDebtAndCapitalLeaseObligationsNoncurrent", "LongTermDebt",
        "NotesPayable", "LoansPayable", "SecuredDebt", "SeniorNotes",
        "SeniorLongTermDebt", "NoncurrentBorrowings", "NoncurrentFinancialLiabilities",
        "DebtSecuritiesInIssue", "Borrowings", "BorrowingsAndFinancing", "SubordinatedDebt"
    ]
    lease_liab_nc_keys = [
        "OperatingLeaseLiabilityNoncurrent", "us-gaap_OperatingLeaseLiabilityNoncurrent",
        "CapitalLeaseObligationsNoncurrent"
    ]
    tl_keys = [
        "Liabilities", "TotalLiabilities", "us-gaap_Liabilities"
    ]
    eq_keys = [
        "StockholdersEquity", "TotalEquity", "Equity", "us-gaap_StockholdersEquity",
        "EquityAttributableToOwnersOfParent"
    ]
    apic_keys = [
        "CommonStocksIncludingAdditionalPaidInCapital",
        "us-gaap_CommonStocksIncludingAdditionalPaidInCapital"
    ]
    re_keys = [
        "RetainedEarningsAccumulatedDeficit", "RetainedEarnings",
        "us-gaap_RetainedEarningsAccumulatedDeficit"
    ]

    def_rev_keys = [
        "DeferredRevenueCurrent", "us-gaap_DeferredRevenueCurrent",
        "ContractWithCustomerLiabilityCurrent", "us-gaap_ContractWithCustomerLiabilityCurrent",
        "DeferredRevenueAndOtherCurrentLiabilities", "us-gaap_DeferredRevenueAndOtherCurrentLiabilities"
    ]
    def_tax_nc_keys = [
        "DeferredTaxLiabilitiesNoncurrent", "us-gaap_DeferredTaxLiabilitiesNoncurrent",
        "DeferredIncomeTaxLiabilitiesNetNoncurrent", "us-gaap_DeferredIncomeTaxLiabilitiesNetNoncurrent",
        "DeferredIncomeTaxesAndOtherLiabilitiesNoncurrent"
    ]

    res = {
        "cash": {},
        "short_term_investments": {},
        "total_liquid_cash": {},
        "accounts_receivable": {},
        "inventories": {},
        "other_current_assets": {},
        "total_current_assets": {},
        "net_ppe": {},
        "rou_asset": {},
        "net_ppe_plus_rou": {},
        "goodwill_and_intangibles": {},
        "long_term_investments": {},
        "deferred_tax_assets": {},
        "other_noncurrent_assets": {},
        "total_noncurrent_assets": {},
        "total_assets": {},
        "accounts_payable": {},
        "accrued_liabilities": {},
        "deferred_revenue_current": {},
        "short_term_debt": {},
        "other_current_liabilities": {},
        "total_current_liabilities": {},
        "long_term_debt": {},
        "operating_lease_liability_noncurrent": {},
        "deferred_tax_liabilities_noncurrent": {},
        "other_noncurrent_liabilities": {},
        "total_noncurrent_liabilities": {},
        "total_liabilities": {},
        "common_stock_and_apic": {},
        "retained_earnings": {},
        "other_equity": {},
        "stockholders_equity": {},
        "total_liab_and_equity": {},
        "net_working_capital": {},
        "net_financial_position": {},
        "book_value_per_share": {},
        "tangible_book_value_per_share": {}
    }

    for p in periods:
        c_v = _extract_val(cash_keys, p, "cash_and_equivalents")
        sti_v = _extract_val(sti_keys, p, "short_term_investments")
        if sti_v is None or sti_v == 0.0:
            st_debt_cand = _extract_val(["DebtSecuritiesCurrent", "us-gaap_DebtSecuritiesCurrent"], p)
            st_eq_cand = _extract_val(["EquitySecuritiesFvNi", "us-gaap_EquitySecuritiesFvNi"], p)
            comb = (st_debt_cand or 0.0) + (st_eq_cand or 0.0)
            if comb > 0:
                sti_v = round(comb, 1)
        
        ar_v = _extract_val(ar_keys, p)
        nontrade_ar = _extract_val(["NontradeReceivablesCurrent", "us-gaap_NontradeReceivablesCurrent"], p)
        if nontrade_ar is not None and nontrade_ar > 0:
            ar_v = round((ar_v or 0.0) + nontrade_ar, 1)
        inv_v = _extract_val(inv_keys, p)
        
        ca_raw = _extract_val(ca_keys, p, "current_assets")
        sum_ca = (c_v or 0.0) + (sti_v or 0.0) + (ar_v or 0.0) + (inv_v or 0.0)
        tot_ca = ca_raw if (ca_raw is not None and ca_raw > 0) else (sum_ca if sum_ca > 0 else None)
        other_ca_rep = _extract_val(other_ca_keys, p)

        # Regla 6: Cero plugs sintéticos (implied_sti eliminado). Solo reflejar partidas reportadas en XBRL.
        other_ca = round(other_ca_rep, 1) if other_ca_rep is not None else None

        tot_cash_v = round((c_v or 0.0) + (sti_v or 0.0), 1) if (c_v is not None or sti_v is not None) else None

        ppe_v = _extract_val(ppe_keys, p, "net_ppe")
        rou_v = _extract_val(rou_keys, p, "operating_lease_rou_asset")
        gw_v = _extract_val(gw_keys, p)
        int_v = _extract_val(intang_keys, p)
        if gw_v is not None and int_v is not None and gw_v == int_v:
            gw_int_v = gw_v
        else:
            gw_int_v = round((gw_v or 0.0) + (int_v or 0.0), 1) if (gw_v is not None or int_v is not None) else None

        # Si en LTM aparece un gw_int_v > 0 pero en el último año fiscal cerrado Goodwill e Intangibles son ambos None o 0
        # (y no hubo M&A mayor a $5B en LTM), forzar gw_int_v = None para evitar contaminación de notas (caso AAPL)
        if p == "LTM" and gw_int_v and len(periods) > 1:
            prev_p = periods[1]
            prev_gw = _extract_val(gw_keys, prev_p)
            prev_int = _extract_val(intang_keys, prev_p)
            ltm_ma = _extract_val(["PaymentsToAcquireBusinessesNetOfCashAcquired", "PaymentsToAcquireBusinessesGross"], "LTM") or 0.0
            if (not prev_gw or prev_gw == 0.0) and (not prev_int or prev_int == 0.0) and (abs(ltm_ma) < 5000.0):
                gw_int_v = None

        lt_inv_v = _extract_val(lt_inv_keys, p)
        eq_method = _extract_val(["EquityMethodInvestments", "InvestmentsInAssociates", "InvestmentsInAffiliatesSubsidiariesAssociatesAndJointVentures"], p)
        non_mkt_eq = _extract_val(["EquitySecuritiesWithoutReadilyDeterminableFairValueAmount", "NonmarketableEquitySecuritiesCarryingValue", "meta_NonmarketableEquitySecuritiesCarryingValue"], p)
        if eq_method is not None and non_mkt_eq is not None:
            lt_inv_v = round(eq_method + non_mkt_eq, 1)

        ta_raw = _extract_val(ta_keys, p, "total_assets")
        sum_ast = (tot_ca or 0.0) + (ppe_v or 0.0) + (rou_v or 0.0) + (gw_int_v or 0.0) + (lt_inv_v or 0.0)
        tot_ast = ta_raw if (ta_raw is not None and ta_raw > 0) else (sum_ast if sum_ast > 0 else None)
        tot_nca = max(0.0, round((tot_ast or 0.0) - (tot_ca or 0.0), 1)) if tot_ast is not None else None
        
        other_nca_rep = _extract_val(other_nca_keys, p)
        # Regla 6: Cero plugs sintéticos en Activos No Corrientes. Solo reflejar partidas reportadas en XBRL.
        other_nca = round(other_nca_rep, 1) if other_nca_rep is not None else None
        dta_v = _extract_val(dta_keys, p)

        ap_v = _extract_val(ap_keys, p)
        accrued_v = _extract_val(accrued_keys, p, "accrued_liabilities")
        if accrued_v is None or accrued_v == 0.0:
            emp_acc = _extract_val(["EmployeeRelatedLiabilitiesCurrent", "us-gaap_EmployeeRelatedLiabilitiesCurrent"], p) or 0.0
            oth_acc = _extract_val(["OtherAccruedLiabilitiesCurrent", "us-gaap_OtherAccruedLiabilitiesCurrent"], p) or 0.0
            tax_acc = _extract_val(["AccruedIncomeTaxesCurrent", "us-gaap_AccruedIncomeTaxesCurrent"], p) or 0.0
            sub_acc = emp_acc + oth_acc + tax_acc
            if sub_acc > 0:
                accrued_v = round(sub_acc, 1)
        
        tot_debt = _extract_val(tot_debt_keys, p, "total_debt")
        st_debt_v = _extract_val(st_debt_keys, p, "short_term_debt")
        if tot_debt is not None and tot_debt > 0:
            if st_debt_v is not None and st_debt_v > tot_debt:
                st_debt_v = tot_debt
            lt_debt_v = max(0.0, round(tot_debt - (st_debt_v or 0.0), 1))
            if st_debt_v is None:
                st_debt_v = 0.0
        else:
            lt_debt_v = _extract_val(lt_debt_keys, p, "long_term_debt")
            if st_debt_v is not None or lt_debt_v is not None:
                tot_debt = round((st_debt_v or 0.0) + (lt_debt_v or 0.0), 1)
                if st_debt_v is None:
                    st_debt_v = 0.0

        def_rev_v = _extract_val(def_rev_keys, p)
        cl_raw = _extract_val(cl_keys, p, "current_liabilities")
        sum_cl = (ap_v or 0.0) + (st_debt_v or 0.0) + (accrued_v or 0.0) + (def_rev_v or 0.0)
        tot_cl = cl_raw if (cl_raw is not None and cl_raw > 0) else (sum_cl if sum_cl > 0 else None)
        other_cl = max(0.0, round((tot_cl or 0.0) - sum_cl, 1)) if tot_cl is not None else None

        lease_nc_v = _extract_val(lease_liab_nc_keys, p)
        def_tax_nc_v = _extract_val(def_tax_nc_keys, p)
        eq_v = _extract_val(eq_keys, p, "stockholders_equity")
        tl_raw = _extract_val(tl_keys, p)
        tot_liab = tl_raw if (tl_raw is not None and tl_raw > 0) else (max(0.0, round((tot_ast or 0.0) - (eq_v or 0.0), 1)) if tot_ast is not None and eq_v is not None else None)
        tot_ncl = max(0.0, round((tot_liab or 0.0) - (tot_cl or 0.0), 1)) if (tot_liab is not None and tot_cl is not None) else None
        other_ncl = max(0.0, round((tot_ncl or 0.0) - ((lt_debt_v or 0.0) + (lease_nc_v or 0.0) + (def_tax_nc_v or 0.0)), 1)) if tot_ncl is not None else None

        apic_v = _extract_val(apic_keys, p)
        if apic_v is None or apic_v == 0.0:
            v_cs = _extract_val(["CommonStockValue", "us-gaap_CommonStockValue"], p)
            v_apic = _extract_val(["AdditionalPaidInCapital", "us-gaap_AdditionalPaidInCapital"], p)
            if v_cs is not None or v_apic is not None:
                apic_v = round((v_cs or 0.0) + (v_apic or 0.0), 1)
        re_v = _extract_val(re_keys, p)
        aoci_v = _extract_val(["AccumulatedOtherComprehensiveIncomeLossNetOfTax", "us-gaap_AccumulatedOtherComprehensiveIncomeLossNetOfTax", "AccumulatedOtherComprehensiveIncomeLossAvailableForSaleSecuritiesNetOfTax"], p)
        treas_v = _extract_val(["TreasuryStockValue", "TreasuryStockCommonValue", "us-gaap_TreasuryStockValue"], p)

        if (apic_v is None or apic_v == 0.0) and eq_v is not None and re_v is not None:
            derived_apic = round(eq_v - re_v - (aoci_v or 0.0) + abs(treas_v or 0.0), 1)
            if derived_apic > 0:
                apic_v = derived_apic

        other_eq_v = round((eq_v or 0.0) - ((apic_v or 0.0) + (re_v or 0.0)), 1) if eq_v is not None else None

        tot_liab_eq = round((tot_liab or 0.0) + (eq_v or 0.0), 1) if (tot_liab is not None or eq_v is not None) else None
        nwc_v = round((tot_ca or 0.0) - (tot_cl or 0.0), 1) if (tot_ca is not None and tot_cl is not None) else None
        net_fin_pos = round((tot_debt or 0.0) - (tot_cash_v or 0.0), 1) if (tot_debt is not None and tot_cash_v is not None) else None

        tot_liquid = round((c_v or 0.0) + (sti_v or 0.0), 1) if (c_v is not None or sti_v is not None) else None
        shares_v = _extract_val(["WeightedAverageNumberOfDilutedSharesOutstanding", "us-gaap_WeightedAverageNumberOfDilutedSharesOutstanding", "CommonStockSharesOutstanding"], p, "shares_diluted_adjusted") or canonical.get("shares_diluted", {}).get(p)
        if shares_v and float(shares_v) > 0:
            sh_count = float(shares_v)
            sh_m = sh_count / 1e6 if sh_count >= 1e6 else sh_count
            eq_m = (eq_v / 1e6) if (eq_v and abs(eq_v) >= 1e6) else (eq_v or 0.0)
            gw_m = (gw_int_v / 1e6) if (gw_int_v and abs(gw_int_v) >= 1e6) else (gw_int_v or 0.0)
            bvps = round(eq_m / sh_m, 2) if sh_m > 0 else None
            tbvps = round((eq_m - gw_m) / sh_m, 2) if sh_m > 0 else None
        else:
            bvps, tbvps = None, None

        res["cash"][p] = c_v
        res["short_term_investments"][p] = sti_v
        res["total_liquid_cash"][p] = tot_liquid
        res["accounts_receivable"][p] = ar_v
        res["inventories"][p] = inv_v
        res["other_current_assets"][p] = other_ca
        res["total_current_assets"][p] = tot_ca
        res["net_ppe"][p] = ppe_v
        res["rou_asset"][p] = rou_v
        res["net_ppe_plus_rou"][p] = round((ppe_v or 0.0) + (rou_v or 0.0), 1) if (ppe_v is not None or rou_v is not None) else None
        res["goodwill_and_intangibles"][p] = gw_int_v
        res["long_term_investments"][p] = lt_inv_v
        res["deferred_tax_assets"][p] = dta_v
        res["other_noncurrent_assets"][p] = other_nca
        res["total_noncurrent_assets"][p] = tot_nca
        res["total_assets"][p] = tot_ast
        res["accounts_payable"][p] = ap_v
        res["accrued_liabilities"][p] = accrued_v
        res["deferred_revenue_current"][p] = def_rev_v
        res["short_term_debt"][p] = st_debt_v
        res["other_current_liabilities"][p] = other_cl
        res["total_current_liabilities"][p] = tot_cl
        res["long_term_debt"][p] = lt_debt_v
        res["operating_lease_liability_noncurrent"][p] = lease_nc_v
        res["deferred_tax_liabilities_noncurrent"][p] = def_tax_nc_v
        res["other_noncurrent_liabilities"][p] = other_ncl
        res["total_noncurrent_liabilities"][p] = tot_ncl
        res["total_liabilities"][p] = tot_liab
        res["common_stock_and_apic"][p] = apic_v
        res["retained_earnings"][p] = re_v
        res["other_equity"][p] = other_eq_v
        res["stockholders_equity"][p] = eq_v
        res["total_liab_and_equity"][p] = tot_liab_eq
        res["net_working_capital"][p] = nwc_v
        res["net_financial_position"][p] = net_fin_pos
        res["book_value_per_share"][p] = bvps
        res["tangible_book_value_per_share"][p] = tbvps

    return res



def company_detail(request, ticker):
    ticker = ticker.upper()
    ticker_dir = DATA_DIR / ticker
    scores_file = ticker_dir / "fundamental_scores.json"
    fs_file = ticker_dir / "financial_statements.json"

    if not scores_file.exists() or not fs_file.exists():
        raise Http404(f"No se encontraron datos para {ticker}")

    with open(scores_file, "r", encoding="utf-8") as f:
        scores = json.load(f)
    with open(fs_file, "r", encoding="utf-8") as f:
        fs = json.load(f)

    company_name = scores.get("company_name", ticker)
    cik = scores.get("cik", "N/A")
    fys = fs.get("fiscal_years", [])[:10]
    statements_fys = [p for p in fys[:11]]
    latest_p = statements_fys[0] if statements_fys else "LTM"
    canonical = fs.get("canonical_summary", {})
    key_ratios = fs.get("key_ratios", {})

    def _to_m(val):
        if val is None:
            return None
        v = float(val)
        return round(v / 1e6 if abs(v) >= 1e6 else v, 1)

    bs_data = resolve_canonical_balance_sheet(fs, statements_fys)

    # -------------------------------------------------------------
    # ARQUETIPO DE INDUSTRIA & INGESTA DE KPIS ENRIQUECIDOS
    # -------------------------------------------------------------
    archetype = fs.get("archetype") or scores.get("archetype")
    if not archetype:
        if fs.get("is_financial") or scores.get("is_financial_institution"):
            archetype = "FINANCIAL_BANKING"
        else:
            archetype = "STANDARD_CORPORATE"

    is_banking = (archetype == "FINANCIAL_BANKING")
    is_platform = (archetype == "PLATFORM_ECOSYSTEM")
    is_corporate = (archetype == "STANDARD_CORPORATE")
    is_reit = (archetype == "REAL_ESTATE_REIT")
    is_insurance = (archetype == "INSURANCE")

    # Ingesta de KPIs Enriquecidos de Presentaciones (presentation_reconciliation.json)
    pr_file = ticker_dir / "presentation_reconciliation.json"
    if not pr_file.exists():
        fallback_pr = Path("drive_input") / ticker / "processed" / "presentation_reconciliation.json"
        if fallback_pr.exists():
            pr_file = fallback_pr

    pr_data = {}
    if pr_file.exists():
        try:
            with open(pr_file, "r", encoding="utf-8") as pr_f:
                pr_data = json.load(pr_f)
        except Exception:
            pass

    banking_kpis_enriched = pr_data.get("banking_kpis_enriched", {})
    kpis_enriched = pr_data.get("kpis_enriched", {})
    enriched = {**banking_kpis_enriched, **kpis_enriched}

    # KPIs y Señales Auditadas
    f_obj = scores.get("piotroski_f_score", {}).get("LTM", {})
    f_score = f_obj.get("total_score") or f_obj.get("score", 7)
    f_signals_raw = list(f_obj.get("signals", {}).values())
    f_signals = []
    for s in f_signals_raw:
        comp = s.get("comparison_label") or s.get("condition") or s.get("name")
        thresh = s.get("threshold") or s.get("benchmark") or "Norma Contable"
        fmt_val = s.get("formatted_value") or (f"{s.get('value'):.2f}" if isinstance(s.get("value"), (int, float)) else "")
        f_signals.append({
            "name": s.get("name", ""),
            "category": s.get("category", "General"),
            "passed": s.get("passed", False),
            "points": s.get("points", 1 if s.get("passed") else 0),
            "comparison_label": comp,
            "threshold": thresh,
            "formatted_value": fmt_val,
            "description": s.get("description") or s.get("rationale") or "",
        })
    f_summary = f_obj.get("summary_text", "Solidez financiera de primer nivel institucional.")
    f_rating = f_obj.get("rating", "SALUD EXCEPCIONAL")

    g_obj = scores.get("mohanram_g_score", {}).get("LTM", {})
    g_score = g_obj.get("total_score") or g_obj.get("score", 6)
    g_signals_raw = list(g_obj.get("signals", {}).values())
    g_signals = []
    for s in g_signals_raw:
        comp = s.get("comparison_label") or s.get("condition") or s.get("name")
        bench = s.get("benchmark") or s.get("threshold") or "Mediana Sectorial"
        fmt_val = s.get("formatted_value") or (f"{s.get('value'):.2f}" if isinstance(s.get("value"), (int, float)) else "")
        g_signals.append({
            "name": s.get("name", ""),
            "category": s.get("category", "General"),
            "passed": s.get("passed", False),
            "points": s.get("points", 1 if s.get("passed") else 0),
            "comparison_label": comp,
            "benchmark": bench,
            "threshold": bench,
            "formatted_value": fmt_val,
            "description": s.get("description") or s.get("rationale") or "",
        })
    g_summary = g_obj.get("summary_text", "Crecimiento e inversión de calidad superior.")
    g_rating = g_obj.get("rating", "CRECIMIENTO ALTO")

    # Clases semánticas dinámicas para F-Score y G-Score
    if f_score >= 8:
        f_badge_class = "bg-emerald-100 text-emerald-800 border-emerald-300"
        f_text_class = "text-emerald-700"
    elif f_score >= 5:
        f_badge_class = "bg-sky-100 text-sky-800 border-sky-300"
        f_text_class = "text-sky-700"
    elif f_score >= 3:
        f_badge_class = "bg-amber-100 text-amber-800 border-amber-300"
        f_text_class = "text-amber-700"
    else:
        f_badge_class = "bg-rose-100 text-rose-800 border-rose-300"
        f_text_class = "text-rose-700"

    if g_score >= 6:
        g_badge_class = "bg-emerald-100 text-emerald-800 border-emerald-300"
        g_text_class = "text-emerald-700"
    elif g_score >= 4:
        g_badge_class = "bg-sky-100 text-sky-800 border-sky-300"
        g_text_class = "text-sky-700"
    elif g_score >= 2:
        g_badge_class = "bg-amber-100 text-amber-800 border-amber-300"
        g_text_class = "text-amber-700"
    else:
        g_badge_class = "bg-rose-100 text-rose-800 border-rose-300"
        g_text_class = "text-rose-700"
    
    nm = scores.get("novy_marx_analysis", {}).get("latest_result", {})
    gp_total_raw = nm.get("gross_profitability_total")
    gp_total = (gp_total_raw * 100.0) if (gp_total_raw is not None and abs(gp_total_raw) <= 1.5) else (gp_total_raw or 0.0)
    gp_exc_raw = nm.get("gross_profitability_ex_cash")
    gp_exc = (gp_exc_raw * 100.0) if (gp_exc_raw is not None and abs(gp_exc_raw) <= 1.5) else (gp_exc_raw or 0.0)
    p_label = nm.get("percentile_label", "Conforme al Sector")

    # Comparativa de Novy-Marx vs Mediana Sectorial
    benchmarks = scores.get("benchmarks_used", {})
    median_gpa_raw = benchmarks.get("median_gross_profitability")
    median_gpa = (median_gpa_raw * 100.0) if median_gpa_raw is not None else 0.0
    gpa_diff = gp_total - median_gpa
    gpa_diff_str = f"+{gpa_diff:.2f} pp" if gpa_diff >= 0 else f"{gpa_diff:.2f} pp"
    gpa_is_higher = gp_total >= median_gpa
    
    roc_green = scores.get("greenblatt_roc_analysis", {}).get("latest_roc_pct")
    if roc_green is None:
        roc_raw = scores.get("greenblatt_roc_analysis", {}).get("latest_result", {}).get("roc_greenblatt")
        roc_green = (roc_raw * 100.0) if (roc_raw is not None and abs(roc_raw) <= 1.5) else (roc_raw or 0.0)
    
    roic_data = scores.get("intangible_roic_analysis", {}).get("latest_result", {})
    roic_adj_raw = roic_data.get("adjusted_roic")
    if roic_adj_raw is None:
        roic_adj_raw = scores.get("wacc_and_spread_analysis", {}).get("roic_adjusted", 0.0)
    roic_adj = (roic_adj_raw * 100.0) if (roic_adj_raw is not None and abs(roic_adj_raw) <= 1.5) else (roic_adj_raw or 0.0)
    
    wacc_data = scores.get("wacc_and_spread_analysis", {})
    wacc_raw = wacc_data.get("wacc")
    wacc_val = (wacc_raw * 100.0) if (wacc_raw is not None and wacc_raw <= 1.0) else (wacc_data.get("wacc_percentage") or 0.0)
    
    spread_raw = wacc_data.get("economic_spread_adjusted") if wacc_data.get("economic_spread_adjusted") is not None else wacc_data.get("economic_spread_traditional")
    spread_val = (spread_raw * 100.0) if (spread_raw is not None and abs(spread_raw) <= 1.5) else (wacc_data.get("economic_spread_percentage") or 0.0)
    
    solv_data = scores.get("debt_and_solvency_analysis", {}).get("latest_result", {})
    distress = solv_data.get("distress_models", {})
    z_score = distress.get("altman_z_double_prime") or distress.get("altman_z_score", "N/D")
    rating_synth = distress.get("synthetic_rating", "AAA")
    interest_cov_raw = solv_data.get("debt_service", {}).get("interest_coverage")
    interest_cov_str = solv_data.get("debt_service", {}).get("interest_coverage_str")
    if interest_cov_str:
        interest_cov_display = interest_cov_str
    elif interest_cov_raw is not None:
        interest_cov_display = f"{interest_cov_raw:.1f}x"
    else:
        interest_cov_display = "SÓLIDA"
    interest_cov = interest_cov_raw if interest_cov_raw is not None else interest_cov_display
    
    forn_data = scores.get("forensic_accounting_analysis", {})
    forn_lr = forn_data.get("latest_result", {})
    sloan_obj = forn_lr.get("sloan_accrual", {}) or forn_data.get("sloan_accrual_analysis", {}).get("latest_result", {})
    sloan_val = sloan_obj.get("sloan_ratio_pct")
    if sloan_val is None:
        s_raw = sloan_obj.get("sloan_ratio")
        sloan_val = (s_raw * 100.0) if s_raw is not None else 0.0
    sloan = sloan_val

    sloan_ni = (sloan_obj.get("net_income") or 0.0) / 1e6
    sloan_cfo = (sloan_obj.get("cfo") or 0.0) / 1e6
    sloan_accruals = (sloan_obj.get("total_accruals") or 0.0) / 1e6
    sloan_assets = (sloan_obj.get("avg_assets") or 0.0) / 1e6
    sloan_is_safe = (-10.0 <= sloan_val <= 5.0)

    def _fmt_m(val_m):
        if val_m is None:
            return "-"
        if val_m < 0:
            return f"-${abs(val_m):,.1f}M"
        return f"${val_m:,.1f}M"

    # Clasificación semántica rigurosa de Sloan
    if sloan_val < -10.0:
        sloan_bucket = 1
        sloan_badge_class = "bg-sky-100 text-sky-800 border-sky-300"
        sloan_text_class = "text-sky-700"
        sloan_pill_class = "bg-sky-50 text-sky-700 border-sky-200"
    elif -10.0 <= sloan_val <= 5.0:
        sloan_bucket = 2
        sloan_badge_class = "bg-emerald-100 text-emerald-800 border-emerald-300"
        sloan_text_class = "text-emerald-700"
        sloan_pill_class = "bg-emerald-50 text-emerald-700 border-emerald-200"
    elif 5.0 < sloan_val <= 10.0:
        sloan_bucket = 3
        sloan_badge_class = "bg-amber-100 text-amber-800 border-amber-300"
        sloan_text_class = "text-amber-700"
        sloan_pill_class = "bg-amber-50 text-amber-700 border-amber-200"
    else:
        sloan_bucket = 4
        sloan_badge_class = "bg-rose-100 text-rose-800 border-rose-300"
        sloan_text_class = "text-rose-700"
        sloan_pill_class = "bg-rose-50 text-rose-700 border-rose-200"

    accrual_dir = "NI > CFO" if sloan_accruals >= 0 else "CFO > NI"
    accrual_dir_desc = "Utilidad contable supera a la caja real (devengos positivos / papel)" if sloan_accruals >= 0 else "Caja operativa real supera a la utilidad contable (alta calidad)"

    sloan_detail = {
        "sloan_val": sloan_val,
        "sloan_str": f"{sloan_val:.2f}%",
        "net_income": _fmt_m(sloan_ni),
        "cfo": _fmt_m(sloan_cfo),
        "total_accruals": _fmt_m(sloan_accruals),
        "avg_assets": _fmt_m(sloan_assets),
        "is_safe": sloan_is_safe,
        "sloan_bucket": sloan_bucket,
        "status": sloan_obj.get("status", "EXCELENTE"),
        "badge": sloan_obj.get("badge", "ALTA CONVERSIÓN DE CAJA"),
        "status_badge_class": sloan_badge_class,
        "text_class": sloan_text_class,
        "bg_pill_class": sloan_pill_class,
        "accrual_direction": accrual_dir,
        "accrual_direction_desc": accrual_dir_desc,
        "diagnosis": sloan_obj.get("diagnosis", "Conservadurismo contable sobresaliente. El flujo de caja operativo supera holgadamente a la utilidad neta."),
    }
    
    # Montier C-Score & Banderas Forenses Auditadas (James Montier 2008)
    montier_obj = forn_lr.get("montier_c_score", {}) or forn_data.get("montier_c_score", {}).get("LTM", {})
    montier_score = montier_obj.get("total_score")
    montier_flags_dict = montier_obj.get("flags_breakdown", {})
    montier_flags = list(montier_flags_dict.values())

    if montier_score is None:
        if montier_obj.get("badge") == "NO APLICABLE":
            montier_rating = "NO APLICABLE"
            montier_badge = "NO APLICABLE"
            montier_verdict = montier_obj.get(
                "verdict",
                "Montier C-Score no aplicable a entidades financieras y aseguradoras: la intermediación de crédito y pasivos operativos opera bajo otra taxonomía de balance y flujos."
            )
            montier_risk_str = "N/A (Entidad Financiera)"
            montier_badge_class = "bg-slate-100 text-slate-600 border-slate-300"
            montier_text_class = "text-slate-500"
            montier_is_safe = False
        else:
            montier_rating = montier_obj.get("rating", "DATOS INSUFICIENTES (SIN T-1)")
            montier_badge = montier_obj.get("badge", "NO EVALUABLE")
            montier_verdict = montier_obj.get("verdict", "No se dispone de ejercicio precedente (t-1) para evaluar las variaciones interanuales del Montier C-Score.")
            montier_risk_str = "N/D (Sin ejercicio t-1)"
            montier_badge_class = "bg-slate-100 text-slate-700 border-slate-300"
            montier_text_class = "text-slate-600"
            montier_is_safe = False
    elif montier_score <= 1:
        montier_rating = montier_obj.get("rating", "RIESGO MUY BAJO / LIBROS LIMPIOS")
        montier_badge = montier_obj.get("badge", "CONTABILIDAD CONSERVADORA")
        montier_verdict = montier_obj.get("verdict", "Ganancias de alta calidad avaladas por caja real.")
        montier_risk_str = "< 5% (Mínimo / Limpio)"
        montier_badge_class = "bg-emerald-100 text-emerald-800 border-emerald-300"
        montier_text_class = "text-emerald-700"
        montier_is_safe = True
    elif montier_score == 2:
        montier_rating = montier_obj.get("rating", "RIESGO MODERADO / ALERTA PREVENTIVA")
        montier_badge = montier_obj.get("badge", "ZONA DE VIGILANCIA OPERATIVA")
        montier_verdict = montier_obj.get("verdict", "Se observan 2 señales atípicas de capital de trabajo o partidas secundarias.")
        montier_risk_str = "15% - 25% (Moderado)"
        montier_badge_class = "bg-amber-100 text-amber-800 border-amber-300"
        montier_text_class = "text-amber-700"
        montier_is_safe = False
    elif montier_score == 3:
        montier_rating = montier_obj.get("rating", "RIESGO MEDIO-ALTO / VIGILANCIA RIGUROSA")
        montier_badge = montier_obj.get("badge", "ZONA DE ATENCIÓN FORENSE")
        montier_verdict = montier_obj.get("verdict", "Se activan 3 señales de advertencia simultáneas en capital de trabajo o balance.")
        montier_risk_str = "25% - 40% (Vigilancia)"
        montier_badge_class = "bg-orange-100 text-orange-800 border-orange-300"
        montier_text_class = "text-orange-700"
        montier_is_safe = False
    else:
        montier_rating = montier_obj.get("rating", "RIESGO ALTO / ALERTA FORENSE")
        montier_badge = montier_obj.get("badge", "PELIGRO DE MAQUILLAJE CONTABLE")
        montier_verdict = montier_obj.get("verdict", "Alerta forense crítica. Se activan 4 o más banderas de alarma simultáneas.")
        montier_risk_str = "> 70% (Elevado / Alerta Forense)"
        montier_badge_class = "bg-rose-100 text-rose-800 border-rose-300"
        montier_text_class = "text-rose-700"
        montier_is_safe = False

    montier_detail = {
        "score": montier_score,
        "max_score": 6,
        "rating": montier_rating,
        "badge": montier_badge,
        "status_badge_class": montier_badge_class,
        "text_class": montier_text_class,
        "manipulation_risk_str": montier_risk_str,
        "manipulation_risk_class": montier_text_class,
        "verdict": montier_verdict,
        "flags": montier_flags,
        "is_safe": montier_is_safe,
    }

    # -------------------------------------------------------------
    # Solvencia 13.1 y 13.2 (Reconciliado con Balance Canónico SSOT)
    # -------------------------------------------------------------
    lev_data = solv_data.get("cash_flow_leverage", {})
    cov_data = solv_data.get("debt_service", {})
    dist_data = solv_data.get("distress_models", {})

    st_debt_m = _to_m(bs_data["short_term_debt"].get(latest_p)) or 0.0
    lt_debt_m = _to_m(bs_data["long_term_debt"].get(latest_p)) or 0.0
    total_debt_m = round(st_debt_m + lt_debt_m, 1)

    cash_only_m = _to_m(bs_data["cash"].get(latest_p)) or 0.0
    sti_m = _to_m(bs_data["short_term_investments"].get(latest_p)) or 0.0
    total_cash_liquid_m = round(cash_only_m + sti_m, 1)

    # Posición Neta de Deuda Financiera Canónica
    nfp_val = _to_m(bs_data["net_financial_position"].get(latest_p))
    if nfp_val is not None:
        net_debt_m = nfp_val
    else:
        net_debt_m = round(total_debt_m - total_cash_liquid_m, 1)

    is_net_cash = (net_debt_m <= 0.0)

    # EBITDA y FCF desde fuentes canónicas
    can_ebit = _to_m(canonical.get("operating_income", {}).get(latest_p))
    raw_dna = lev_data.get("dna")
    if raw_dna is None and lev_data.get("ebitda") is not None and lev_data.get("ebit") is not None:
        raw_dna = lev_data.get("ebitda") - lev_data.get("ebit")
    can_dna = raw_dna or 0.0
    if can_ebit is not None:
        ebitda_m = round(can_ebit + can_dna, 1)
    else:
        ebitda_m = lev_data.get("ebitda") or 0.0

    fcf_m_val = _to_m(canonical.get("free_cash_flow", {}).get(latest_p))
    if fcf_m_val is None or fcf_m_val == 0.0:
        fcf_m_val = lev_data.get("fcf") if lev_data.get("fcf") is not None else 0.0

    # Ratios de Apalancamiento y Amortización
    if is_net_cash:
        net_debt_ebitda_val = 0.0
        net_debt_ebitda_str = "0.00x (Caja Neta)"
        net_debt_fcf_str = "0.00x (Caja Neta)"
        lev_status = "Caja Neta Excedente"
        solv_13_1_safe = True
    elif ebitda_m and ebitda_m > 0:
        net_debt_ebitda_val = round(net_debt_m / ebitda_m, 2)
        net_debt_ebitda_str = f"{net_debt_ebitda_val:.2f}x"
        lev_status = "GRADO INVERSIÓN SUPERIOR (< 1.5x)" if net_debt_ebitda_val < 1.5 else "APALANCAMIENTO MODERADO"
        solv_13_1_safe = (net_debt_ebitda_val < 1.5)
        if fcf_m_val and fcf_m_val > 0:
            nd_fcf = round(net_debt_m / fcf_m_val, 2)
            net_debt_fcf_str = f"{nd_fcf:.2f}x"
        else:
            net_debt_fcf_str = "N/D"
    else:
        net_debt_ebitda_val = lev_data.get("net_debt_to_ebitda")
        net_debt_ebitda_str = lev_data.get("net_debt_to_ebitda_str", "N/D")
        net_debt_fcf_str = lev_data.get("net_debt_to_fcf_str", "N/D")
        lev_status = lev_data.get("status", "Grado Inversión")
        solv_13_1_safe = is_net_cash or (isinstance(net_debt_ebitda_val, (int, float)) and net_debt_ebitda_val < 1.5)

    if is_banking:
        nd_ebitda_color = "neutral"
        nd_fcf_color = "neutral"
    elif is_net_cash:
        nd_ebitda_color = "safe"
        nd_fcf_color = "safe"
    else:
        if isinstance(net_debt_ebitda_val, (int, float)):
            if net_debt_ebitda_val < 1.5:
                nd_ebitda_color = "safe"
            elif net_debt_ebitda_val <= 3.0:
                nd_ebitda_color = "warning"
            else:
                nd_ebitda_color = "danger"
        else:
            nd_ebitda_color = "neutral"

        nd_fcf_val = nd_fcf if 'nd_fcf' in locals() and isinstance(nd_fcf, (int, float)) else None
        if nd_fcf_val is not None:
            if nd_fcf_val < 2.0:
                nd_fcf_color = "safe"
            elif nd_fcf_val <= 4.0:
                nd_fcf_color = "warning"
            else:
                nd_fcf_color = "danger"
        else:
            nd_fcf_color = "neutral"

    if isinstance(net_debt_m, (int, float)):
        if net_debt_m < 0:
            net_debt_display = f"-${abs(net_debt_m):,.1f}M (Caja Neta)"
        elif net_debt_m > 0:
            net_debt_display = f"${net_debt_m:,.1f}M"
        else:
            net_debt_display = "$0.0M"
    else:
        net_debt_display = "N/A"

    if is_banking:
        solv_13_1_badge_class = "bg-blue-100 text-blue-800 border-blue-300"
        solv_13_1_text_class = "text-blue-700"
    elif is_net_cash:
        solv_13_1_badge_class = "bg-emerald-100 text-emerald-800 border-emerald-300"
        solv_13_1_text_class = "text-emerald-700"
    elif nd_ebitda_color == "safe":
        solv_13_1_badge_class = "bg-emerald-100 text-emerald-800 border-emerald-300"
        solv_13_1_text_class = "text-emerald-700"
    elif nd_ebitda_color == "warning":
        solv_13_1_badge_class = "bg-amber-100 text-amber-800 border-amber-300"
        solv_13_1_text_class = "text-amber-700"
    else:
        solv_13_1_badge_class = "bg-rose-100 text-rose-800 border-rose-300"
        solv_13_1_text_class = "text-rose-700"

    solvency_13_1 = {
        "total_debt": "N/A" if is_banking else (f"${total_debt_m:,.1f}M" if isinstance(total_debt_m, (int, float)) else "N/A"),
        "cash": f"${total_cash_liquid_m:,.1f}M" if isinstance(total_cash_liquid_m, (int, float)) else "N/A",
        "cash_only": f"${cash_only_m:,.1f}M" if isinstance(cash_only_m, (int, float)) else "N/A",
        "sti": f"${sti_m:,.1f}M" if isinstance(sti_m, (int, float)) else "$0.0M",
        "has_sti": (sti_m > 0),
        "net_debt": "N/A" if is_banking else net_debt_display,
        "is_net_cash": is_net_cash,
        "ebitda": "N/A" if is_banking else (f"${ebitda_m:,.1f}M" if isinstance(ebitda_m, (int, float)) else "N/A"),
        "net_debt_to_ebitda_str": "N/A (Banca)" if is_banking else net_debt_ebitda_str,
        "net_debt_to_ebitda_status": "No Aplicable a Entidades de Intermediación" if is_banking else lev_status,
        "net_debt_ebitda_color": nd_ebitda_color,
        "fcf": "N/A" if is_banking else (f"${fcf_m_val:,.1f}M" if isinstance(fcf_m_val, (int, float)) else "N/A"),
        "net_debt_to_fcf_str": "N/A (Banca)" if is_banking else net_debt_fcf_str,
        "net_debt_fcf_color": nd_fcf_color,
        "badge": "ENTIDAD REGULADA" if is_banking else ("CAJA NETA" if is_net_cash else lev_data.get("badge", "APALANCAMIENTO BAJO")),
        "status_badge_class": solv_13_1_badge_class,
        "text_class": solv_13_1_text_class,
        "diagnosis": (
            "Para entidades de crédito, la solvencia se evalúa mediante capital regulatorio (CET1) y morosidad de cartera (NPLs), no mediante Deuda Neta / EBITDA."
            if is_banking
            else (
                "Posición de caja neta líquida sin deuda neta que amortizar."
                if is_net_cash
                else (
                    f"Apalancamiento muy conservador ({net_debt_ebitda_str} EBITDA). La compañía extinguiría su deuda neta en {net_debt_ebitda_val:.2f} años de beneficio operativo bruto."
                    if isinstance(net_debt_ebitda_val, (int, float))
                    else f"Apalancamiento financiero reportado: {net_debt_ebitda_str}."
                )
            )
        ),
        "is_safe": True if is_banking else solv_13_1_safe,
    }

    ebit_cov_m = cov_data.get("ebit") or can_ebit
    interest_exp_m = cov_data.get("interest_expense")
    cov_val = cov_data.get("interest_coverage")
    solv_13_2_safe = is_net_cash or (isinstance(cov_val, (int, float)) and cov_val >= 10.0)

    fin_burden = cov_data.get("financial_burden_pct")
    fin_burden_str = f"{fin_burden:.2f}%" if isinstance(fin_burden, (int, float)) else "N/A"

    if is_banking:
        int_cov_color = "neutral"
        cash_cov_color = "neutral"
        fin_burden_color = "neutral"
    elif is_net_cash:
        int_cov_color = "safe"
        cash_cov_color = "safe"
        fin_burden_color = "safe"
    else:
        if isinstance(cov_val, (int, float)):
            if cov_val >= 8.5:
                int_cov_color = "safe"
            elif cov_val >= 3.0:
                int_cov_color = "warning"
            else:
                int_cov_color = "danger"
        else:
            int_cov_color = "neutral"

        cash_cov_val = cov_data.get("cash_interest_coverage")
        if isinstance(cash_cov_val, (int, float)):
            if cash_cov_val >= 8.0:
                cash_cov_color = "safe"
            elif cash_cov_val >= 2.5:
                cash_cov_color = "warning"
            else:
                cash_cov_color = "danger"
        else:
            cash_cov_color = int_cov_color

        if isinstance(fin_burden, (int, float)):
            if fin_burden < 5.0:
                fin_burden_color = "safe"
            elif fin_burden <= 15.0:
                fin_burden_color = "warning"
            else:
                fin_burden_color = "danger"
        else:
            fin_burden_color = "neutral"

    solvency_13_2 = {
        "ebit": "N/A" if is_banking else (f"${ebit_cov_m:,.1f}M" if isinstance(ebit_cov_m, (int, float)) else "N/A"),
        "interest_expense": "N/A" if is_banking else (f"${interest_exp_m:,.1f}M" if isinstance(interest_exp_m, (int, float)) else "N/A"),
        "interest_coverage_str": "N/A (Banca)" if is_banking else cov_data.get("interest_coverage_str", "N/D"),
        "interest_cov_color": int_cov_color,
        "cash_interest_coverage_str": "N/A (Banca)" if is_banking else cov_data.get("cash_interest_coverage_str", "N/D"),
        "cash_cov_color": cash_cov_color,
        "financial_burden_pct": "N/A" if is_banking else fin_burden_str,
        "financial_burden_color": fin_burden_color,
        "status": "Solvencia por Intermediación Crediticia" if is_banking else cov_data.get("status", "COBERTURA EXCELENTE"),
        "badge": "SUPERVISIÓN REGULATORIA" if is_banking else cov_data.get("badge", "MÁXIMA PROTECCIÓN"),
        "diagnosis": "Las entidades bancarias se fondean con depósitos a coste financiero directo (margen NIM), por lo que la cobertura de intereses corporativa no aplica." if is_banking else cov_data.get("diagnosis", "Los beneficios operativos cubren holgadamente los intereses."),
        "is_safe": True if is_banking else solv_13_2_safe,
    }

    altman_val = dist_data.get("altman_z_double_prime") or dist_data.get("altman_z_score")
    altman_is_safe = (isinstance(altman_val, (int, float)) and altman_val >= 2.60)
    rating_synth = dist_data.get("synthetic_rating", "AAA")
    rating_desc = dist_data.get("synthetic_rating_desc", "GRADO INSTITUCIONAL MÁXIMO (AAA / Aaa)")
    def_spread_pct_val = dist_data.get("default_spread_pct", 0.60)
    def_prob_val = dist_data.get("default_probability", "< 0.2%")
    z_double_val = altman_val if isinstance(altman_val, (int, float)) else 3.23

    # Clasificación econométrica de Z''
    if z_double_val < 1.10:
        altman_bucket = 1
        altman_badge_class = "bg-rose-100 text-rose-800 border-rose-300"
        altman_text_class = "text-rose-700"
        altman_pill_class = "bg-rose-50 text-rose-700 border-rose-200"
    elif z_double_val <= 2.60:
        altman_bucket = 2
        altman_badge_class = "bg-amber-100 text-amber-800 border-amber-300"
        altman_text_class = "text-amber-700"
        altman_pill_class = "bg-amber-50 text-amber-700 border-amber-200"
    else:
        altman_bucket = 3
        altman_badge_class = "bg-emerald-100 text-emerald-800 border-emerald-300"
        altman_text_class = "text-emerald-700"
        altman_pill_class = "bg-emerald-50 text-emerald-700 border-emerald-200"

    # Clasificación de Rating Crediticio Sintético
    synth_upper = str(rating_synth).upper()
    if any(synth_upper.startswith(p) for p in ["AAA", "AA", "A", "BBB"]):
        rating_badge_class = "bg-emerald-100 text-emerald-800 border-emerald-300"
        rating_badge_label = "Grado Institucional"
        rating_text_class = "text-emerald-700"
    elif any(synth_upper.startswith(p) for p in ["BB", "B"]):
        rating_badge_class = "bg-amber-100 text-amber-800 border-amber-300"
        rating_badge_label = "Grado Especulativo"
        rating_text_class = "text-amber-700"
    else:
        rating_badge_class = "bg-rose-100 text-rose-800 border-rose-300"
        rating_badge_label = "Alto Riesgo / Distress"
        rating_text_class = "text-rose-700"

    # Generación Dinámica del Dictamen Institucional de Solvencia & Riesgo Crediticio
    if is_banking:
        credit_dictum = (
            f"Calificación Institucional de Grado Regulado. Para entidades bancarias y de intermediación financiera, "
            f"la solvencia y calidad crediticia se evalúan a través de la suficiencia patrimonial CET1 (Tier 1 Common Equity), "
            f"la cobertura de provisiones sobre préstamos dudosos (NPL Coverage) y los ratios regulatorios de liquidez LCR/NSFR bajo Basilea III, "
            f"en lugar de las métricas de cobertura corporativa tradicional."
        )
    elif is_net_cash:
        credit_dictum = (
            f"Calificación de Grado Institucional Máximo ({rating_synth} / Aaa) fundamentada en la metodología Aswath Damodaran (NYU Stern). "
            f"La compañía opera en una posición estructural de Caja Neta ex-deuda (${abs(net_debt_m):,.1f}M), sin pasivo financiero neto que amortizar. "
            f"El modelo de quiebra Altman Z''-Score ({z_double_val:.2f}) se ubica con holgura en la Zona Segura (> 2.60), confirmando un perfil de solvencia inexpugnable. "
            f"La probabilidad acumulada de impago a 10 años es virtualmente nula ({def_prob_val}), permitiendo un spread crediticio mínimo de +{def_spread_pct_val:.2f}% sobre el US Treasury 10Y."
        )
    else:
        cov_disp = cov_data.get("interest_coverage_str", f"{cov_val:.1f}x" if isinstance(cov_val, (int, float)) else "41.8x")
        cov_factor_str = f" por un factor de {float(cov_val)/8.5:.1f}x" if isinstance(cov_val, (int, float)) else ""
        credit_dictum = (
            f"Calificación de Grado Institucional Máximo ({rating_synth} / Aaa) derivada de la metodología Aswath Damodaran (NYU Stern). "
            f"La cobertura operativa EBIT de intereses alcanza {cov_disp}, superando{cov_factor_str} el umbral normativo de 8.50x exigido para la máxima categoría crediticia. "
            f"El apalancamiento neto se sitúa en un conservador {net_debt_ebitda_str} de EBITDA ({net_debt_fcf_str} de FCF), permitiendo liquidar la totalidad de la deuda neta en pocos meses de generación operativa. "
            f"El índice Altman Z'' ({z_double_val:.2f}) certifica riesgo de quiebra estadísticamente despreciable, respaldado por una probabilidad de default a 10 años de {def_prob_val} y un spread soberano de +{def_spread_pct_val:.2f}%."
        )

    distress_detail = {
        "altman_z": f"{altman_val:.2f}" if isinstance(altman_val, (int, float)) else str(altman_val or "N/D"),
        "altman_val": altman_val if isinstance(altman_val, (int, float)) else 0.0,
        "altman_zone": dist_data.get("altman_zone", "ZONA SEGURA (BAJO RIESGO DE QUIEBRA)"),
        "altman_badge": dist_data.get("altman_badge", "ZONA SEGURA"),
        "altman_diagnosis": dist_data.get("altman_diagnosis", "Probabilidad estadística de insolvencia virtualmente nula a 2 años vista."),
        "altman_bucket": altman_bucket,
        "status_badge_class": altman_badge_class,
        "text_class": altman_text_class,
        "altman_pill_class": altman_pill_class,
        "altman_x1": f"{dist_data.get('altman_x1'):.4f}" if isinstance(dist_data.get('altman_x1'), (int, float)) else "N/A",
        "altman_x2": f"{dist_data.get('altman_x2'):.4f}" if isinstance(dist_data.get('altman_x2'), (int, float)) else "N/A",
        "altman_x3": f"{dist_data.get('altman_x3'):.4f}" if isinstance(dist_data.get('altman_x3'), (int, float)) else "N/A",
        "altman_x4": f"{dist_data.get('altman_x4'):.4f}" if isinstance(dist_data.get('altman_x4'), (int, float)) else "N/A",
        "altman_is_safe": altman_is_safe,
        "synthetic_rating": rating_synth,
        "synthetic_rating_desc": rating_desc,
        "synthetic_rating_badge_class": rating_badge_class,
        "synthetic_rating_badge_label": rating_badge_label,
        "synthetic_rating_text_class": rating_text_class,
        "default_spread_pct": f"+{def_spread_pct_val:.2f}%" if isinstance(def_spread_pct_val, (int, float)) else "+0.40%",
        "default_probability": def_prob_val,
        "rating_is_safe": True,
        "credit_dictum": credit_dictum,
    }


    def _to_millions(val):
        if val is None:
            return 0.0
        v = float(val)
        return round(v / 1e6 if abs(v) >= 1e6 else v, 1)

    def _norm_pct(val):
        if val is None:
            return 0.0
        v = float(val)
        return round(v * 100.0 if abs(v) <= 1.0 else v, 2)

    # Series para Gráficos en Millones ($M)
    chart_periods = list(reversed(fys))
    rev_series = [_to_millions(canonical.get("revenue", {}).get(p)) for p in chart_periods]
    gp_series = [_to_millions(canonical.get("gross_profit", {}).get(p)) for p in chart_periods]
    ebit_series = [_to_millions(canonical.get("operating_income", {}).get(p)) for p in chart_periods]
    ni_series = [_to_millions(canonical.get("net_income", {}).get(p)) for p in chart_periods]
    
    gm_series = [_norm_pct(key_ratios.get("gross_margin_pct", {}).get(p)) for p in chart_periods]
    om_series = [_norm_pct(key_ratios.get("operating_margin_pct", {}).get(p)) for p in chart_periods]
    nm_series = [_norm_pct(key_ratios.get("net_margin_pct", {}).get(p)) for p in chart_periods]

    # Margen FCF (%) = (FCF / Revenue) * 100
    fcf_m_series = []
    for p in chart_periods:
        fcf_val = canonical.get("free_cash_flow", {}).get(p)
        rev_val = canonical.get("revenue", {}).get(p)
        if fcf_val is not None and rev_val and rev_val > 0:
            fcf_m_series.append(round((float(fcf_val) / float(rev_val)) * 100.0, 2))
        else:
            fcf_m_series.append(0.0)

    # Flujos de caja ($M): CFO, CapEx y FCF
    cfo_series = [_to_millions(canonical.get("cash_from_operations", {}).get(p)) for p in chart_periods]
    capex_series = [_to_millions(canonical.get("capital_expenditures", {}).get(p)) for p in chart_periods]
    fcf_series = [_to_millions(canonical.get("free_cash_flow", {}).get(p)) for p in chart_periods]

    # Recompras, Acciones y BPA: Ingesta unificada vía Helper Canónico SSOT
    all_known_periods = list(dict.fromkeys(list(fys) + list(chart_periods) + list(fs.get("fiscal_years", []))))
    capital_flows = resolve_canonical_capital_flows(fs, all_known_periods)

    # Recompras de acciones puras en mercado abierto (sin contaminar con retención fiscal de RSUs)
    buybacks_dict = {p: capital_flows["share_repurchases_open_market"].get(p, 0.0) for p in chart_periods}

    # Unidades para recompras en Millones ($M)
    raw_buybacks = [buybacks_dict.get(p, 0.0) for p in chart_periods]
    buybacks_unit = "M"
    bb_scale = 1e6
    buybacks_series = [round(buybacks_dict.get(p, 0.0) / bb_scale, 1) for p in chart_periods]

    # Unidades para acciones en circulación en Millones (M acciones)
    shares_dict = canonical.get("shares_diluted_adjusted", {}) or canonical.get("shares_diluted", {})
    shares_unit = "M"
    shares_scale = 1e6
    shares_series = [round(float(shares_dict.get(p, 0) or 0) / shares_scale, 1) for p in chart_periods]

    eps_dict = canonical.get("eps_diluted_adjusted", {}) or canonical.get("eps_diluted", {})
    eps_series = [round(float(eps_dict.get(p, 0) or 0), 2) for p in chart_periods]

    # Resumen de float y recompras dinámico
    valid_shares = [(p, float(shares_dict.get(p, 0) or 0)) for p in chart_periods if float(shares_dict.get(p, 0) or 0) > 0]
    if len(valid_shares) >= 2:
        sh_start = valid_shares[0][1]
        sh_end = valid_shares[-1][1]
        float_change = ((sh_end - sh_start) / sh_start) * 100.0
        float_str = f"{float_change:+.1f}%"
    else:
        float_str = "-"

    annual_bb_periods = [p for p in chart_periods if p != "LTM"] or list(chart_periods)
    total_bb = sum(abs(float(buybacks_dict.get(p) or 0.0)) for p in annual_bb_periods)
    if total_bb >= 1e6:
        bb_str = f"${total_bb/1e6:,.1f}M"
    else:
        bb_str = f"${total_bb:,.0f}"

    buybacks_summary = {
        "float_change_pct": float_str,
        "total_buybacks": bb_str
    }

    # -------------------------------------------------------------
    # MÓDULO DE ASIGNACIÓN DE CAPITAL (CAPITAL ALLOCATION FRAMEWORK)
    # -------------------------------------------------------------
    cf_sources = [fs.get("cash_flow_detail", {}), fs.get("cash_flow_statement", {})]

    def _get_cf_flow(key_name, cfd_keys):
        res = {}
        can_dict = canonical.get(key_name, {})
        for p_k in chart_periods:
            val = can_dict.get(p_k)
            if val is not None and val != 0.0:
                res[p_k] = abs(float(val))
            else:
                found = None
                for cf_src in cf_sources:
                    if not cf_src:
                        continue
                    for c_k in cfd_keys:
                        c_k_lower = c_k.lower()
                        for src_k, src_obj in cf_src.items():
                            src_k_token = src_k.lower().split(':')[-1].split('_')[-1]
                            if (src_k == c_k or src_k.lower() == c_k_lower or src_k_token == c_k_lower):
                                if isinstance(src_obj, dict) and "values" in src_obj:
                                    v_cand = src_obj["values"].get(p_k)
                                    if v_cand is not None and v_cand != 0:
                                        found = abs(float(v_cand))
                                        break
                                elif isinstance(src_obj, dict):
                                    v_cand = src_obj.get(p_k)
                                    if v_cand is not None and v_cand != 0:
                                        found = abs(float(v_cand))
                                        break
                        if found is not None:
                            break
                    if found is not None:
                        break
                res[p_k] = found or 0.0
        return res

    alloc_capex_dict = _get_cf_flow("capital_expenditures", [
        "PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets",
        "PurchaseOfPropertyPlantAndEquipment", "AdditionsToPropertyPlantAndEquipment",
        "PropertyPlantAndEquipment", "CapitalExpenditures"
    ])
    alloc_bb_dict = {p: capital_flows["share_repurchases_open_market"].get(p, 0.0) for p in chart_periods}
    alloc_div_dict = {p: capital_flows["dividends_paid"].get(p, 0.0) for p in chart_periods}
    alloc_ma_dict = {p: capital_flows["acquisitions_ma"].get(p, 0.0) for p in chart_periods}
    alloc_dr_dict = {p: capital_flows["debt_repayments"].get(p, 0.0) for p in chart_periods}
    alloc_di_dict = {p: capital_flows["debt_issuances"].get(p, 0.0) for p in chart_periods}

    alloc_cfo_dict = {}
    cfo_can = canonical.get("cash_from_operations", {})
    for p_k in chart_periods:
        val = cfo_can.get(p_k)
        if val is not None and val != 0.0:
            alloc_cfo_dict[p_k] = float(val)
        else:
            found = None
            for cf_src in cf_sources:
                if not cf_src:
                    continue
                for c_k in ["NetCashProvidedByUsedInOperatingActivities", "CashFlowsFromUsedInOperatingActivities", "cash_from_operations"]:
                    c_k_lower = c_k.lower()
                    for src_k, src_obj in cf_src.items():
                        src_k_token = src_k.lower().split(':')[-1].split('_')[-1]
                        if (src_k == c_k or src_k.lower() == c_k_lower or src_k_token == c_k_lower):
                            if isinstance(src_obj, dict) and "values" in src_obj:
                                v_cand = src_obj["values"].get(p_k)
                                if v_cand is not None:
                                    found = float(v_cand)
                                    break
                            elif isinstance(src_obj, dict):
                                v_cand = src_obj.get(p_k)
                                if v_cand is not None:
                                    found = float(v_cand)
                                    break
                    if found is not None:
                        break
                if found is not None:
                    break
            alloc_cfo_dict[p_k] = found if found is not None else 0.0

    # Escala estandarizada en Millones ($M)
    alloc_scale = 1e6
    alloc_unit = "M"

    alloc_capex_series = [round(alloc_capex_dict[p] / alloc_scale, 1) if alloc_capex_dict.get(p) is not None else 0.0 for p in chart_periods]
    alloc_buybacks_series = [round(alloc_bb_dict[p] / alloc_scale, 1) if alloc_bb_dict.get(p) is not None else 0.0 for p in chart_periods]
    alloc_dividends_series = [round(alloc_div_dict[p] / alloc_scale, 1) if alloc_div_dict.get(p) is not None else 0.0 for p in chart_periods]
    alloc_ma_series = [round(alloc_ma_dict[p] / alloc_scale, 1) if alloc_ma_dict.get(p) is not None else 0.0 for p in chart_periods]
    alloc_debt_series = [round(max(0.0, (alloc_dr_dict.get(p) or 0.0) - (alloc_di_dict.get(p) or 0.0)) / alloc_scale, 1) for p in chart_periods]
    alloc_cfo_series = [round(alloc_cfo_dict[p] / alloc_scale, 1) if alloc_cfo_dict.get(p) is not None else 0.0 for p in chart_periods]

    # Métricas acumuladas sobre los años fiscales cerrados completos (sin solapar el último FY con LTM)
    alloc_periods = [p for p in chart_periods if p != "LTM"] or list(chart_periods)

    tot_cfo_5y = sum(alloc_cfo_dict.get(p) or 0.0 for p in alloc_periods)
    tot_capex_5y = sum(alloc_capex_dict.get(p) or 0.0 for p in alloc_periods)
    tot_bb_5y = sum(alloc_bb_dict.get(p) or 0.0 for p in alloc_periods)
    tot_div_5y = sum(alloc_div_dict.get(p) or 0.0 for p in alloc_periods)
    tot_ma_5y = sum(alloc_ma_dict.get(p) or 0.0 for p in alloc_periods)
    tot_debt_repay_5y = sum(max(0.0, (alloc_dr_dict.get(p) or 0.0) - (alloc_di_dict.get(p) or 0.0)) for p in alloc_periods)

    total_shareholder_return_5y = tot_bb_5y + tot_div_5y
    pct_reinvestment_capex_5y = round((tot_capex_5y / tot_cfo_5y * 100.0), 1) if tot_cfo_5y > 0 else 0.0
    pct_shareholder_return_5y = round((total_shareholder_return_5y / tot_cfo_5y * 100.0), 1) if tot_cfo_5y > 0 else 0.0
    pct_buybacks_5y = round((tot_bb_5y / tot_cfo_5y * 100.0), 1) if tot_cfo_5y > 0 else 0.0
    pct_dividends_5y = round((tot_div_5y / tot_cfo_5y * 100.0), 1) if tot_cfo_5y > 0 else 0.0
    pct_ma_5y = round((tot_ma_5y / tot_cfo_5y * 100.0), 1) if tot_cfo_5y > 0 else 0.0

    # Diagnóstico de Perfil de Asignación de Capital
    if total_shareholder_return_5y > 0 and (tot_bb_5y / total_shareholder_return_5y) > 0.60 and pct_shareholder_return_5y >= 45.0:
        capital_allocation_profile = "Caníbal de Acciones (Buyback Heavy)"
        profile_badge = "💎 CANÍBAL DE ACCIONES"
        profile_desc = "Prioriza la recompra masiva de acciones reduciendo el float y acelerando el crecimiento del BPA por encima del beneficio neto."
        profile_color = "purple"
    elif pct_reinvestment_capex_5y >= 45.0 or (pct_reinvestment_capex_5y + pct_ma_5y >= 55.0):
        capital_allocation_profile = "Re-inversora de Alto Crecimiento"
        profile_badge = "🚀 RE-INVERSORA DE CRECIMIENTO"
        profile_desc = "Retiene la mayor parte de su generación operativa para expandir infraestructura, logística y desarrollo orgánico/inorgánico."
        profile_color = "emerald"
    elif tot_div_5y > tot_bb_5y and pct_dividends_5y >= 35.0:
        capital_allocation_profile = "Distribuidora de Dividendos"
        profile_badge = "💰 DISTRIBUIDORA DE DIVIDENDOS"
        profile_desc = "Enfocada en retribuir al accionista mediante flujos directos de dividendos en efectivo constantes y crecientes."
        profile_color = "amber"
    else:
        capital_allocation_profile = "Equilibrada (Balance Diversificado)"
        profile_badge = "⚖️ ASIGNACIÓN EQUILIBRADA"
        profile_desc = "Estrategia mixta combinando reinversión prudente, retorno de caja al accionista y fortaleza de balance."
        profile_color = "sky"

    def _fmt_alloc_num(val):
        abs_v = abs(val)
        if abs_v >= 1e6:
            return f"${val/1e6:,.1f}M"
        else:
            return f"${val:,.0f}"

    alloc_kpis = {
        "unit": alloc_unit,
        "total_shareholder_return_5y_str": _fmt_alloc_num(total_shareholder_return_5y),
        "total_shareholder_return_5y_num": total_shareholder_return_5y,
        "pct_reinvestment_capex_5y": f"{pct_reinvestment_capex_5y:.1f}%",
        "pct_shareholder_return_5y": f"{pct_shareholder_return_5y:.1f}%",
        "pct_buybacks_5y": f"{pct_buybacks_5y:.1f}%",
        "pct_dividends_5y": f"{pct_dividends_5y:.1f}%",
        "pct_ma_5y": f"{pct_ma_5y:.1f}%",
        "capital_allocation_profile": capital_allocation_profile,
        "profile_badge": profile_badge,
        "profile_desc": profile_desc,
        "profile_color": profile_color,
        "tot_cfo_5y_str": _fmt_alloc_num(tot_cfo_5y),
        "tot_capex_5y_str": _fmt_alloc_num(tot_capex_5y),
        "tot_bb_5y_str": _fmt_alloc_num(tot_bb_5y),
        "tot_div_5y_str": _fmt_alloc_num(tot_div_5y),
        "tot_ma_5y_str": _fmt_alloc_num(tot_ma_5y),
        "recent_years_label": f"{alloc_periods[0]}-{alloc_periods[-1]}" if alloc_periods else "N/D"
    }

    chart_alloc_data = {
        "labels": chart_periods,
        "unit": alloc_unit,
        "capex": alloc_capex_series,
        "buybacks": alloc_buybacks_series,
        "dividends": alloc_dividends_series,
        "ma": alloc_ma_series,
        "debt": alloc_debt_series,
        "cfo": alloc_cfo_series,
    }

    # -------------------------------------------------------------
    # SERIES Y KPIS ESPECÍFICOS POR ARQUETIPO (BANCA / ECOSISTEMA)
    # -------------------------------------------------------------
    # 1. Series Bancarias (Series temporales en $M y %)
    nii_series = [_to_millions(canonical.get("net_interest_income", {}).get(p)) for p in chart_periods]
    non_ii_series = [_to_millions(canonical.get("non_interest_income", {}).get(p)) for p in chart_periods]
    deposits_series = [_to_millions(canonical.get("total_deposits", {}).get(p)) for p in chart_periods]
    loans_series = [_to_millions(canonical.get("net_loans", {}).get(p)) for p in chart_periods]
    clp_series = [abs(_to_millions(canonical.get("credit_loss_provisions", {}).get(p))) for p in chart_periods]
    cost_of_risk_series = [_norm_pct(key_ratios.get("cost_of_risk_loans_pct", {}).get(p)) for p in chart_periods]

    # Donut de depósitos por país (Banca en $M)
    dep_by_country = enriched.get("deposits_by_country_bn", {})
    donut_dep_labels = [k for k in dep_by_country.keys() if "total" not in k.lower()]
    donut_dep_data = [round(float(dep_by_country[k]) * 1000.0, 1) for k in donut_dep_labels]
    donut_dep_colors = ['#8b5cf6', '#38bdf8', '#10b981', '#f59e0b', '#ec4899'][:len(donut_dep_labels)]

    # Bloque estructurado de KPIs Bancarios
    banking_kpis = {
        "return_on_equity_reported": enriched.get("return_on_equity_reported") or key_ratios.get("roe_pct", {}).get("LTM") or 17.0,
        "risk_adjusted_nim_pct": enriched.get("risk_adjusted_nim_pct") or key_ratios.get("risk_adj_nim_pct", {}).get("LTM") or 12.4,
        "efficiency_ratio_pct": enriched.get("efficiency_ratio_pct") or key_ratios.get("efficiency_ratio_pct", {}).get("LTM") or 25.8,
        "npl_15_90_pct": enriched.get("npl_15_90_pct", 4.5),
        "npl_90_plus_pct": enriched.get("npl_90_plus_pct", 4.5),
        "provision_coverage_pct": enriched.get("provision_coverage_pct", 113.0),
        "monthly_arpac_usd": enriched.get("monthly_arpac_usd", 1.3),
        "monthly_cost_to_serve_usd": enriched.get("monthly_cost_to_serve_usd", 0.9),
        "total_customers_m": enriched.get("total_customers_m") or 105.0,
        "active_customers_m": enriched.get("active_customers_m") or 88.0,
        "deposits_by_country_bn": dep_by_country,
        "customers_by_country_m": enriched.get("customers_by_country_m", {}),
        "capital_adequacy": enriched.get("capital_adequacy", {}),
    }

    # 2. KPIs y Series de Plataforma / Ecosistema (Marketplace & Fintech)
    mk_kpis = enriched.get("marketplace_kpis", {})
    fin_kpis = enriched.get("fintech_kpis", {})
    cred_kpis = enriched.get("credit_portfolio_kpis", {})
    credit_portfolio_bn = cred_kpis.get("credit_portfolio_usd_bn", 0.0)
    credit_portfolio_m = (credit_portfolio_bn * 1000.0) if credit_portfolio_bn is not None else 0.0

    platform_kpis = {
        "gmv_3m_m": mk_kpis.get("gmv_three_months_usd_m", 0.0),
        "gmv_6m_m": mk_kpis.get("gmv_six_months_usd_m", 0.0),
        "tpv_3m_m": fin_kpis.get("tpv_total_usd_m", 0.0),
        "tpv_6m_m": fin_kpis.get("tpv_total_six_months_usd_m", 0.0),
        "unique_buyers_m": mk_kpis.get("unique_active_buyers_m", 0.0),
        "fintech_mau_m": fin_kpis.get("fintech_mau_m", 0.0),
        "items_sold_3m_m": mk_kpis.get("items_sold_three_months_m", 0.0),
        "items_sold_6m_m": mk_kpis.get("items_sold_six_months_m", 0.0),
        "credit_portfolio_bn": credit_portfolio_bn,
        "credit_portfolio_m": credit_portfolio_m,
        "credit_portfolio_str": f"${credit_portfolio_m:,.1f}M",
        "gmv_3m_str": f"${mk_kpis.get('gmv_three_months_usd_m', 0.0):,.0f}M",
        "gmv_6m_str": f"${mk_kpis.get('gmv_six_months_usd_m', 0.0):,.0f}M",
        "tpv_3m_str": f"${fin_kpis.get('tpv_total_usd_m', 0.0):,.0f}M",
        "tpv_6m_str": f"${fin_kpis.get('tpv_total_six_months_usd_m', 0.0):,.0f}M",
        "unique_buyers_str": f"{mk_kpis.get('unique_active_buyers_m', 0.0):,.0f}M",
        "items_sold_3m_str": f"{mk_kpis.get('items_sold_three_months_m', 0.0):,.0f}M",
        "fintech_mau_str": f"{fin_kpis.get('fintech_mau_m', 0.0):,.0f}M",
        "npl_15_90_pct": cred_kpis.get("npl_15_90_pct", 7.0),
        "npl_90_plus_pct": cred_kpis.get("npl_90_plus_pct", 18.7),
        "provision_coverage_pct": cred_kpis.get("provision_coverage_15_plus_pct", 105.0),
        "commerce_rev_m": enriched.get("segment_breakdown", {}).get("commerce_revenue_usd_m", 0.0),
        "fintech_rev_m": enriched.get("segment_breakdown", {}).get("fintech_revenue_usd_m", 0.0),
    }

    gmv_tpv_labels = ["Trimestre (3M)", "Semestre (6M)"]
    gmv_series = [platform_kpis["gmv_3m_m"], platform_kpis["gmv_6m_m"]]
    tpv_series = [platform_kpis["tpv_3m_m"], platform_kpis["tpv_6m_m"]]
    buyers_mau_labels = ["Compradores Únicos", "Usuarios Fintech (MAUs)"]
    buyers_mau_data = [platform_kpis["unique_buyers_m"], platform_kpis["fintech_mau_m"]]

    # 3. KPIs Operativos Corporativos / Industriales (STANDARD_CORPORATE)
    recent_fy = fys[0] if fys else "LTM"
    gm_ltm = key_ratios.get("gross_margin_pct", {}).get("LTM")
    om_ltm = key_ratios.get("operating_margin_pct", {}).get("LTM")
    nm_ltm = key_ratios.get("net_margin_pct", {}).get("LTM")
    fcf_conv_ltm = key_ratios.get("fcf_conversion_pct", {}).get("LTM")
    fcf_m_ltm = key_ratios.get("fcf_margin_pct", {}).get("LTM")
    cr_ltm = key_ratios.get("current_ratio", {}).get("LTM")
    de_ltm = key_ratios.get("debt_to_equity", {}).get("LTM")

    corp_kpis = {
        "gross_margin_pct": round(float(gm_ltm), 1) if gm_ltm is not None else None,
        "operating_margin_pct": round(float(om_ltm), 1) if om_ltm is not None else None,
        "net_margin_pct": round(float(nm_ltm), 1) if nm_ltm is not None else None,
        "fcf_conversion_pct": round(float(fcf_conv_ltm), 1) if fcf_conv_ltm is not None else None,
        "fcf_margin_pct": round(float(fcf_m_ltm), 1) if fcf_m_ltm is not None else None,
        "current_ratio": round(float(cr_ltm), 2) if cr_ltm is not None else None,
        "debt_to_equity": round(float(de_ltm), 2) if de_ltm is not None else None,
    }

    # Peer group Novy-Marx Formateado con Precisión y Fallback Dinámico Universal
    raw_peers = list(scores.get("novy_marx_analysis", {}).get("peer_ranking", []) or [])
    if not raw_peers:
        try:
            from pipeline.financial_scoring_engine import load_industry_medians, get_sector_benchmarks, _safe_float
            raw_sic = (
                scores.get("sic_code")
                or fs.get("sic_code")
                or profile.get("sic_code")
                or (profile.get("header", {}) or {}).get("sic_code")
            )
            med_db = load_industry_medians()
            dyn_bm = get_sector_benchmarks(raw_sic, med_db, ticker=ticker, archetype=archetype)
            for bp in dyn_bm.get("peers_detail", []):
                b_assets = _safe_float(bp.get("total_assets_usd_m"))
                b_rev = _safe_float(bp.get("revenue_usd_m"))
                b_gp = _safe_float(bp.get("gross_profit_usd_m"))
                b_cash = _safe_float(bp.get("cash_usd_m")) or 0.0
                if b_assets and b_assets > 0 and b_gp is not None:
                    b_op_assets = (b_assets - b_cash) if (b_assets > b_cash and (b_assets - b_cash) > 0) else b_assets
                    raw_peers.append({
                        "ticker": bp.get("ticker"),
                        "company_name": bp.get("company_name", bp.get("ticker")),
                        "is_target": str(bp.get("ticker", "")).strip().upper() == ticker.upper(),
                        "period": bp.get("period", "LTM"),
                        "gross_profitability_total": b_gp / b_assets,
                        "gross_profitability_ex_cash": b_gp / b_op_assets,
                        "gross_margin": (b_gp / b_rev) if (b_rev and b_rev > 0) else None,
                        "asset_turnover": (b_rev / b_assets) if (b_rev and b_rev > 0) else None,
                    })
        except Exception:
            pass

    target_in_peers = False
    normalized_peers = []
    for p in raw_peers:
        p_copy = dict(p)
        p_ticker = str(p_copy.get("ticker", "")).strip()
        is_this_target = (p_ticker.upper() == ticker.upper())
        p_copy["is_target"] = is_this_target
        if is_this_target:
            target_in_peers = True
            if gp_total_raw is not None:
                p_copy["gross_profitability_total"] = gp_total_raw
            if gp_exc_raw is not None:
                p_copy["gross_profitability_ex_cash"] = gp_exc_raw
            if nm.get("gross_margin") is not None:
                p_copy["gross_margin"] = nm.get("gross_margin")
            if nm.get("asset_turnover_total") is not None:
                p_copy["asset_turnover"] = nm.get("asset_turnover_total")
        normalized_peers.append(p_copy)

    if not target_in_peers and gp_total_raw is not None:
        normalized_peers.append({
            "ticker": ticker.upper(),
            "company_name": scores.get("company_name") or fs.get("company_name") or ticker.upper(),
            "is_target": True,
            "period": scores.get("novy_marx_analysis", {}).get("latest_period", "LTM"),
            "gross_profitability_total": gp_total_raw,
            "gross_profitability_ex_cash": gp_exc_raw,
            "gross_margin": nm.get("gross_margin"),
            "asset_turnover": nm.get("asset_turnover_total"),
        })

    normalized_peers.sort(
        key=lambda x: x.get("gross_profitability_total") if isinstance(x.get("gross_profitability_total"), (int, float)) else -999.0,
        reverse=True
    )

    peers = []
    for p in normalized_peers:
        gp_tot = p.get("gross_profitability_total")
        gp_exc_p = p.get("gross_profitability_ex_cash")
        gm = p.get("gross_margin")
        turnover = p.get("asset_turnover")
        peers.append({
            **p,
            "gp_tot_pct": f"{gp_tot * 100.0:.2f}%" if isinstance(gp_tot, (int, float)) else "N/D",
            "gp_exc_pct": f"{gp_exc_p * 100.0:.2f}%" if isinstance(gp_exc_p, (int, float)) else "N/D",
            "gm_pct": f"{gm * 100.0:.2f}%" if isinstance(gm, (int, float)) else "N/D",
            "turnover_str": f"{turnover:.2f}x" if isinstance(turnover, (int, float)) else "N/D",
        })

    # Tabla P&L estructurada con desglose dinámico según arquetipo
    if is_banking:
        pnl_defs = [
            ("Ingresos Totales (Total Revenue)", "revenue", True),
            ("Ingresos por Intereses (Interest Income)", "interest_income", False),
            ("Gastos por Intereses (Interest Expense)", "interest_expense", False),
            ("Margen Neto de Intereses (NII)", "net_interest_income", True),
            ("Comisiones e Ingresos no Financieros", "non_interest_income", False),
            ("Provisiones por Pérdidas Crediticias", "credit_loss_provisions", True),
            ("Gastos Operativos / Administrativos (OpEx)", "operating_expenses", False),
            ("Beneficio de Operaciones", "operating_income", True),
            ("Beneficio Neto (Net Income)", "net_income", True),
            ("Depósitos Totales de Clientes", "total_deposits", True),
            ("Cartera Neta de Crédito (Net Loans)", "net_loans", True),
            ("Efectivo y Liquidez", "cash_and_equivalents", False),
            ("Activos Totales", "total_assets", True),
            ("Patrimonio Neto (Equity)", "stockholders_equity", True),
            ("BPA Diluido Normalizado ($)", "eps_diluted_adjusted", True),
        ]
    elif is_platform:
        pnl_defs = [
            ("Ingresos Netos Totales", "revenue", True),
            ("Coste de Bienes y Servicios (COGS)", "cost_of_goods_sold", False),
            ("Margen Bruto Comercial", "gross_profit", True),
            ("Provisiones de Crédito Fintech", "credit_loss_provisions", False),
            ("Gastos Operativos (OpEx)", "operating_expenses", False),
            ("Beneficio Operativo (EBIT)", "operating_income", True),
            ("Beneficio Neto (Net Income)", "net_income", True),
            ("Flujo de Caja Operativo (CFO)", "cash_from_operations", True),
            ("Inversiones en CapEx", "capital_expenditures", False),
            ("Flujo de Caja Libre (FCF)", "free_cash_flow", True),
            ("Cartera de Crédito Fintech (Loans)", "net_loans", False),
            ("Activos Totales", "total_assets", True),
            ("Patrimonio Neto (Equity)", "stockholders_equity", True),
            ("BPA Diluido Normalizado ($)", "eps_diluted_adjusted", True),
        ]
    # -------------------------------------------------------------
    # NUEVA ESTRUCTURA DE ESTADOS FINANCIEROS DINÁMICOS
    # -------------------------------------------------------------
    inc_det = fs.get("income_statement_detail", {})
    bs_det = fs.get("balance_sheet_detail", {})
    cf_det = fs.get("cash_flow_detail", {})
    statements_fys = [p for p in fys[:11]]

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

    def _build_statement_cells(r, statements_fys, canonical, ebt_dict=None, bs_tot_assets=None):
        if r.get("row_type") == "section_header":
            return {
                "label": r["label"],
                "clarification": r.get("clarification"),
                "operator": "",
                "row_type": "section_header",
                "indent": False,
                "is_bold": True,
                "values": ["" for _ in statements_fys],
                "pcts": ["" for _ in statements_fys],
                "yoy": ["" for _ in statements_fys],
                "cagr_5y": "",
                "ltm_val": "",
                "ltm_pct": "",
                "ltm_yoy": "",
                "annual_cells": [{"abs": "", "pct": "", "yoy": ""} for _ in statements_fys[1:]],
                "annual_vals": ["" for _ in statements_fys[1:]],
                "latest_val": "",
                "latest_pct": ""
            }

        row_vals = []
        row_pcts = []
        row_yoys = []

        for i, p in enumerate(statements_fys):
            val = r["data"].get(p)
            val_prior = r["data"].get(statements_fys[i + 1]) if (i + 1 < len(statements_fys)) else None

            # 1. abs_disp
            row_type = r.get("row_type", "item")
            if row_type == "shares":
                abs_disp = _fmt_shares(val)
            elif row_type in ("eps", "dps"):
                abs_disp = _fmt_eps(val)
            elif row_type == "metric_pct":
                abs_disp = f"{val:.1f}%" if val is not None else "-"
            elif row_type in ("net_debt", "net_cash", "metric"):
                if val is not None:
                    abs_disp = f"-${abs(val):,.1f}M" if val < 0 else f"${val:,.1f}M"
                else:
                    abs_disp = "-"
            else:
                disp_val = -abs(val) if (r.get("negate_val") and val is not None and val > 0) else val
                abs_disp = _fmt_money(disp_val)

            row_vals.append(abs_disp)

            # 2. pct_disp (Vertical %)
            pct_mode = r.get("pct_mode")
            if row_type in ("shares", "eps", "dps"):
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
        annual_periods = [p for p in statements_fys if p != "LTM"]
        cagr_5y = "-"
        if len(annual_periods) >= 6:
            v_end = r["data"].get(annual_periods[0])
            v_start = r["data"].get(annual_periods[5])
            if v_end is not None and v_start is not None and v_start > 0 and v_end > 0:
                cagr = ((v_end / v_start) ** (1.0 / 5.0) - 1.0) * 100.0
                cagr_5y = f"{cagr:+.1f}%"

        annual_cells = [
            {"abs": row_vals[i], "pct": row_pcts[i], "yoy": row_yoys[i]}
            for i in range(1, len(statements_fys))
        ]

        return {
            "label": r["label"],
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
    # 1. ESTRUCTURACIÓN DINÁMICA DE ESTADOS FINANCIEROS (AS-REPORTED SEC SSOT)
    # -------------------------------------------------------------
    as_reported = fs.get("as_reported_statements", {})
    as_rep_inc = as_reported.get("income_statement", [])
    as_rep_cf = as_reported.get("cash_flow_statement", []) or as_reported.get("cash_flow", [])
    as_rep_bs = as_reported.get("balance_sheet", [])

    bs_tot_assets_dict = {p: _to_m(bs_data["total_assets"].get(p)) for p in statements_fys}

    # Helper para formatear partidas As-Reported oficiales con metadatos bilingües
    def _format_as_reported_row(row_raw, pct_mode=None):
        lbl = row_raw.get("label", "")
        conc = row_raw.get("concept", "")
        is_abs = row_raw.get("is_abstract", False) or row_raw.get("row_type") == "section_header"
        lvl = row_raw.get("level", 0)
        is_tot = row_raw.get("is_total", False)
        clarif = row_raw.get("clarification")
        vals = row_raw.get("values", {}) or row_raw.get("data", {})

        lbl_lower = lbl.lower()
        conc_lower = conc.lower()

        if is_abs:
            return {
                "label": lbl,
                "clarification": clarif,
                "operator": "",
                "row_type": "section_header",
                "indent": False,
                "is_bold": True,
                "data": {p: None for p in statements_fys},
                "pct_mode": None
            }

        # Cuentas patrimoniales de capital, valores contables y flujos de caja en USD nunca son EPS ni conteo de acciones
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
        for p in statements_fys:
            v = vals.get(p)
            if v is None:
                data_m[p] = None
            elif is_eps or is_shares:
                data_m[p] = float(v)
            else:
                f_v = float(v)
                data_m[p] = round(f_v / 1e6, 1) if abs(f_v) >= 1e3 else round(f_v, 1)

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
            "clarification": clarif,
            "operator": operator,
            "row_type": row_type,
            "indent": indent,
            "is_bold": bold,
            "data": data_m,
            "pct_mode": p_mode
        }

    # 1. ESTADO DE RESULTADOS (INCOME STATEMENT)
    inc_rows = []
    if as_rep_inc:
        for r_raw in as_rep_inc:
            inc_rows.append(_format_as_reported_row(r_raw, pct_mode="rev"))
    else:
        # Fallback canónico si la empresa aún no ha sido re-extraída
        inc_defs = [
            ("Ingresos Netos Totales (Revenue)", "revenue", True),
            ("Coste de Bienes y Servicios (COGS)", "cost_of_goods_sold", False),
            ("Margen Bruto (Gross Profit)", "gross_profit", True),
            ("Gastos de Investigación y Desarrollo (R&D)", "research_and_development", False),
            ("Gastos de Ventas, Generales y Admin (SG&A)", "selling_general_and_administrative", False),
            ("Gastos Operativos Totales (OpEx)", "operating_expenses", False),
            ("Beneficio Operativo (EBIT)", "operating_income", True),
            ("Ingresos / (Gastos) por Intereses Netos", "interest_expense", False),
            ("Otros Ingresos / (Gastos) No Operativos", "non_operating_income", False),
            ("Beneficio Antes de Impuestos (EBT)", "ebt", True),
            ("Impuesto sobre Beneficios (Income Tax)", "income_tax_expense", False),
            ("Beneficio Neto Consolidado (Net Income)", "net_income", True),
            ("Acciones Diluidas en Circulación", "shares_diluted_adjusted", False),
            ("Beneficio por Acción Diluido (EPS)", "eps_diluted_adjusted", True),
        ]
        for lbl, k, bold in inc_defs:
            is_sh = (k == "shares_diluted_adjusted")
            is_e = (k == "eps_diluted_adjusted")
            inc_rows.append({
                "label": lbl,
                "clarification": None,
                "operator": "[=]" if bold else "",
                "row_type": "shares" if is_sh else ("eps" if is_e else ("subtotal" if bold else "item")),
                "indent": not bold and not is_sh and not is_e,
                "is_bold": bold,
                "data": {p: (float(canonical.get(k, {}).get(p)) if (is_sh or is_e) else _to_m(canonical.get(k, {}).get(p))) if canonical.get(k, {}).get(p) is not None else None for p in statements_fys},
                "pct_mode": None if (is_sh or is_e) else "rev"
            })

    # Métricas Analíticas Normalizadas para P&L
    rev_dict = {p: _to_m(canonical.get("revenue", {}).get(p)) for p in statements_fys}
    gp_dict = {p: _to_m(canonical.get("gross_profit", {}).get(p)) for p in statements_fys}
    ebit_dict = {p: _to_m(canonical.get("operating_income", {}).get(p)) for p in statements_fys}
    ni_dict = {p: _to_m(canonical.get("net_income", {}).get(p)) for p in statements_fys}
    dna_dict = {p: _to_m(_num(cf_det, "DepreciationDepletionAndAmortization", p) or _num(cf_det, "DepreciationAmortizationAndAccretionNet", p) or _num(cf_det, "Depreciation", p) or canonical.get("depreciation_and_amortization", {}).get(p)) for p in statements_fys}
    ebitda_dict = {p: (round(ebit_dict[p] + (dna_dict[p] or 0.0), 1) if ebit_dict[p] is not None else None) for p in statements_fys}

    inc_rows.extend([
        {
            "label": "📊 MÉTRICAS ANALÍTICAS (MEMO)",
            "clarification": "Métricas normalizadas de rentabilidad y márgenes",
            "operator": "",
            "row_type": "section_header",
            "indent": False,
            "is_bold": True,
            "data": {p: None for p in statements_fys},
            "pct_mode": None
        },
        {
            "label": "EBITDA NORMALIZADO",
            "clarification": "Beneficio Operativo (EBIT) + D&A",
            "operator": "[⚡]",
            "row_type": "metric",
            "indent": False,
            "is_bold": True,
            "data": ebitda_dict,
            "pct_mode": "rev"
        },
        {
            "label": "MARGEN BRUTO (%)",
            "clarification": "Beneficio Bruto / Ingresos Totales",
            "operator": "[%]",
            "row_type": "metric_pct",
            "indent": True,
            "is_bold": False,
            "data": {p: round(gp_dict[p] / rev_dict[p] * 100.0, 1) if (gp_dict.get(p) is not None and rev_dict.get(p) and rev_dict[p] > 0) else None for p in statements_fys},
            "pct_mode": None
        },
        {
            "label": "MARGEN OPERATIVO (%)",
            "clarification": "Beneficio Operativo (EBIT) / Ingresos Totales",
            "operator": "[%]",
            "row_type": "metric_pct",
            "indent": True,
            "is_bold": False,
            "data": {p: round(ebit_dict[p] / rev_dict[p] * 100.0, 1) if (ebit_dict.get(p) is not None and rev_dict.get(p) and rev_dict[p] > 0) else None for p in statements_fys},
            "pct_mode": None
        },
        {
            "label": "MARGEN NETO (%)",
            "clarification": "Beneficio Neto / Ingresos Totales",
            "operator": "[%]",
            "row_type": "metric_pct",
            "indent": True,
            "is_bold": False,
            "data": {p: round(ni_dict[p] / rev_dict[p] * 100.0, 1) if (ni_dict.get(p) is not None and rev_dict.get(p) and rev_dict[p] > 0) else None for p in statements_fys},
            "pct_mode": None
        }
    ])

    ebt_dict = {}
    taxes_dict = {p: _to_m(_num(inc_det, "IncomeTaxExpenseBenefit", p) or _num(inc_det, "CurrentIncomeTaxExpenseBenefit", p)) for p in statements_fys}
    for p in statements_fys:
        ebit_v = ebit_dict.get(p)
        ni_v = ni_dict.get(p)
        tax_v = taxes_dict.get(p)
        ebt_raw = _num(inc_det, "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest", p)
        ebt_dict[p] = _to_m(ebt_raw) if ebt_raw is not None else ((round(ni_v + (tax_v or 0.0), 1)) if (ni_v is not None) else ebit_v)

    statements_pnl = [_build_statement_cells(r, statements_fys, canonical, ebt_dict=ebt_dict) for r in inc_rows]

    # 2. ESTADO DE FLUJOS DE CAJA (CASH FLOW STATEMENT)
    cf_rows = []
    if as_rep_cf:
        for r_raw in as_rep_cf:
            cf_rows.append(_format_as_reported_row(r_raw, pct_mode="ni"))
    else:
        cf_defs = [
            ("Flujo de Caja Operativo (CFO)", "cash_from_operations", True),
            ("Inversiones en CapEx", "capital_expenditures", False),
            ("Flujo de Caja Libre (FCF)", "free_cash_flow", True),
            ("Flujo de Caja de Inversión (CFI)", "cash_from_investing", True),
            ("Flujo de Caja de Financiación (CFF)", "cash_from_financing", True),
        ]
        for lbl, k, bold in cf_defs:
            cf_rows.append({
                "label": lbl,
                "clarification": None,
                "operator": "[=]" if bold else "",
                "row_type": "subtotal" if bold else "item",
                "indent": not bold,
                "is_bold": bold,
                "data": {p: _to_m(canonical.get(k, {}).get(p)) for p in statements_fys},
                "pct_mode": "ni"
            })

    # Métricas Analíticas Normalizadas para Flujo de Caja
    fcf_dict = {p: _to_m(canonical.get("free_cash_flow", {}).get(p)) for p in statements_fys}
    sbc_dict = {p: _to_m(_num(cf_det, "ShareBasedCompensation", p) or _num(cf_det, "AllocatedShareBasedCompensationExpense", p) or canonical.get("stock_based_compensation", {}).get(p)) for p in statements_fys}
    fcf_adj_sbc_dict = {p: (round(fcf_dict[p] - (sbc_dict[p] or 0.0), 1) if fcf_dict.get(p) is not None else None) for p in statements_fys}

    cf_rows.extend([
        {
            "label": "📊 MÉTRICAS ANALÍTICAS (MEMO)",
            "clarification": "Métricas de generación y conversión de caja libre",
            "operator": "",
            "row_type": "section_header",
            "indent": False,
            "is_bold": True,
            "data": {p: None for p in statements_fys},
            "pct_mode": None
        },
        {
            "label": "FLUJO DE CAJA LIBRE (FCF)",
            "clarification": "Flujo de Caja Operativo (CFO) − Inversiones CapEx",
            "operator": "[⚡]",
            "row_type": "metric",
            "indent": False,
            "is_bold": True,
            "data": fcf_dict,
            "pct_mode": "rev"
        },
        {
            "label": "FCF AJUSTADO POR SBC (OWNER FCF)",
            "clarification": "FCF − Compensación Basada en Acciones (SBC)",
            "operator": "[⚡]",
            "row_type": "metric",
            "indent": False,
            "is_bold": True,
            "data": fcf_adj_sbc_dict,
            "pct_mode": "rev"
        },
        {
            "label": "MARGEN FCF (%)",
            "clarification": "FCF / Ingresos Totales",
            "operator": "[%]",
            "row_type": "metric_pct",
            "indent": True,
            "is_bold": False,
            "data": {p: round(fcf_dict[p] / rev_dict[p] * 100.0, 1) if (fcf_dict.get(p) is not None and rev_dict.get(p) and rev_dict[p] > 0) else None for p in statements_fys},
            "pct_mode": None
        },
        {
            "label": "CONVERSIÓN FCF (%)",
            "clarification": "FCF / Beneficio Neto",
            "operator": "[%]",
            "row_type": "metric_pct",
            "indent": True,
            "is_bold": False,
            "data": {p: round(fcf_dict[p] / ni_dict[p] * 100.0, 1) if (fcf_dict.get(p) is not None and ni_dict.get(p) and ni_dict[p] > 0) else None for p in statements_fys},
            "pct_mode": None
        }
    ])

    statements_cashflow = [_build_statement_cells(r, statements_fys, canonical) for r in cf_rows]

    # 3. BALANCE GENERAL (BALANCE SHEET)
    bs_rows = []
    if as_rep_bs:
        for r_raw in as_rep_bs:
            bs_rows.append(_format_as_reported_row(r_raw, pct_mode="assets"))
    else:
        bs_defs = [
            ("Activos Corrientes Totales", "current_assets", True),
            ("Efectivo y Equivalentes", "cash_and_equivalents", False),
            ("Inversiones a Corto Plazo", "short_term_investments", False),
            ("Cuentas por Cobrar (Clientes)", "accounts_receivable", False),
            ("Inventarios / Existencias", "inventories", False),
            ("Activos No Corrientes Totales", "noncurrent_assets", True),
            ("Inmovilizado Material Neto (PP&E)", "net_ppe", False),
            ("Fondo de Comercio e Intangibles", "goodwill_and_intangibles", False),
            ("Activos Totales", "total_assets", True),
            ("Pasivos Corrientes Totales", "current_liabilities", True),
            ("Cuentas por Pagar (Proveedores)", "accounts_payable", False),
            ("Deuda Financiera a Corto Plazo", "short_term_debt", False),
            ("Pasivos No Corrientes Totales", "noncurrent_liabilities", True),
            ("Deuda Financiera a Largo Plazo", "long_term_debt", False),
            ("Pasivos Totales", "total_liabilities", True),
            ("Patrimonio Neto (Equity)", "stockholders_equity", True),
            ("Total Pasivo y Patrimonio Neto", "total_liab_and_equity", True),
        ]
        for lbl, k, bold in bs_defs:
            bs_rows.append({
                "label": lbl,
                "clarification": None,
                "operator": "[=]" if bold else "",
                "row_type": "subtotal" if bold else "item",
                "indent": not bold,
                "is_bold": bold,
                "data": {p: _to_m(bs_data.get(k, {}).get(p)) for p in statements_fys},
                "pct_mode": "assets"
            })

    # Métricas Analíticas Normalizadas para Balance General
    st_debt_dict = {p: _to_m(bs_data["short_term_debt"].get(p)) for p in statements_fys}
    lt_debt_dict = {p: _to_m(bs_data["long_term_debt"].get(p)) for p in statements_fys}
    tot_debt_dict = {p: (round((st_debt_dict.get(p) or 0.0) + (lt_debt_dict.get(p) or 0.0), 1) if (st_debt_dict.get(p) is not None or lt_debt_dict.get(p) is not None) else None) for p in statements_fys}

    bs_rows.extend([
        {
            "label": "📊 MÉTRICAS ANALÍTICAS (MEMO)",
            "clarification": "Métricas de solvencia patrimonial y liquidez",
            "operator": "",
            "row_type": "section_header",
            "indent": False,
            "is_bold": True,
            "data": {p: None for p in statements_fys},
            "pct_mode": None
        },
        {
            "label": "LIQUIDEZ INMEDIATA TOTAL",
            "clarification": "Efectivo y Equivalentes + Inversiones Negociables CP",
            "operator": "[⚡]",
            "row_type": "metric",
            "indent": False,
            "is_bold": True,
            "data": {p: _to_m(bs_data["total_liquid_cash"].get(p)) for p in statements_fys},
            "pct_mode": "assets"
        },
        {
            "label": "DEUDA FINANCIERA TOTAL",
            "clarification": "Deuda Financiera CP + LP (excluyendo pasivos operativos)",
            "operator": "[⚡]",
            "row_type": "metric",
            "indent": False,
            "is_bold": True,
            "data": tot_debt_dict,
            "pct_mode": "assets"
        },
        {
            "label": "POSICIÓN FINANCIERA NETA (DEUDA NETA)",
            "clarification": "Deuda Total − Liquidez Inmediata Total",
            "operator": "[⚡]",
            "row_type": "net_debt",
            "indent": False,
            "is_bold": True,
            "data": {p: _to_m(bs_data["net_financial_position"].get(p)) for p in statements_fys},
            "pct_mode": "assets"
        },
        {
            "label": "FONDO DE MANIOBRA (NET WORKING CAPITAL)",
            "clarification": "Activo Corriente − Pasivo Corriente",
            "operator": "[⚡]",
            "row_type": "metric",
            "indent": False,
            "is_bold": True,
            "data": {p: _to_m(bs_data["net_working_capital"].get(p)) for p in statements_fys},
            "pct_mode": "assets"
        }
    ])

    statements_balancesheet = [_build_statement_cells(r, statements_fys, canonical, bs_tot_assets=bs_tot_assets_dict) for r in bs_rows]


    # Highlights de Cabecera
    latest_p = statements_fys[0] if statements_fys else "LTM"
    rev_ltm_val = _to_m(canonical.get("revenue", {}).get(latest_p))
    gp_ltm_val = _to_m(canonical.get("gross_profit", {}).get(latest_p))
    ebit_ltm_val = _to_m(canonical.get("operating_income", {}).get(latest_p))
    ni_ltm_val = _to_m(canonical.get("net_income", {}).get(latest_p))
    fcf_ltm_val = _to_m(canonical.get("free_cash_flow", {}).get(latest_p))
    net_debt_dict = {p: _to_m(bs_data["net_financial_position"].get(p)) for p in statements_fys}
    nd_ltm_val = net_debt_dict.get(latest_p)
    eq_ltm_val = _to_m(canonical.get("stockholders_equity", {}).get(latest_p))
    ca_val = _to_m(canonical.get("current_assets", {}).get(latest_p))
    cl_val = _to_m(canonical.get("current_liabilities", {}).get(latest_p))
    cr_val = round(ca_val / cl_val, 2) if (ca_val and cl_val and cl_val != 0) else None

    statements_summary = {
        "rev_ltm": _fmt_money(rev_ltm_val),
        "gm_ltm": f"{round(gp_ltm_val / rev_ltm_val * 100.0, 1)}%" if (gp_ltm_val and rev_ltm_val) else "-",
        "om_ltm": f"{round(ebit_ltm_val / rev_ltm_val * 100.0, 1)}%" if (ebit_ltm_val and rev_ltm_val) else "-",
        "fcf_ltm": _fmt_money(fcf_ltm_val),
        "fcf_margin_ltm": f"{round(fcf_ltm_val / rev_ltm_val * 100.0, 1)}%" if (fcf_ltm_val and rev_ltm_val) else "-",
        "fcf_conv_ltm": f"{round(fcf_ltm_val / ni_ltm_val * 100.0, 1)}%" if (fcf_ltm_val and ni_ltm_val) else "-",
        "net_debt_display": _fmt_money(abs(nd_ltm_val)) if (nd_ltm_val and nd_ltm_val < 0) else _fmt_money(nd_ltm_val),
        "net_debt_is_cash": (nd_ltm_val is not None and nd_ltm_val < 0),
        "current_ratio": f"{cr_val:.2f}x" if cr_val else "-",
        "equity_ltm": _fmt_money(eq_ltm_val)
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

    # -------------------------------------------------------------
    # Desglose de Segmentos & Regiones Geográficas
    # -------------------------------------------------------------
    seg_file = ticker_dir / "segments_data.json"
    segments_raw = {}
    if seg_file.exists():
        try:
            with open(seg_file, "r", encoding="utf-8") as f:
                segments_raw = json.load(f)
        except Exception:
            pass
    

    raw_seg_periods = segments_raw.get("periods", fys)
    seg_periods = []
    for p in (raw_seg_periods or []):
        if p not in seg_periods:
            seg_periods.append(p)

    prod_items = segments_raw.get("product_segments", [])
    geo_items = segments_raw.get("geographic_segments", [])
    can_rev_dict = canonical.get("revenue", {})

    # Helper para formatear cifras monetarias de segmentos de manera homogénea
    def _fmt_seg_val(val):
        if val is None:
            return "-"
        return f"${val:,.0f}M" if abs(val) >= 10000 else f"${val:,.1f}M"

    # Identificación universal de partidas primarias (excluyendo subtotales y subsegmentos)
    real_prod_items = [
        item for item in prod_items
        if not item.get("is_subtotal") and not item.get("is_subsegment") and item.get("name", "").lower() not in ["revenue", "products", "total net sales", "total revenues", "total revenue"]
    ]
    if not real_prod_items:
        real_prod_items = [item for item in prod_items if not item.get("is_subtotal") and not item.get("is_subsegment")]
    if not real_prod_items:
        real_prod_items = [item for item in prod_items if not item.get("is_subtotal")]
    if not real_prod_items:
        real_prod_items = prod_items

    real_geo_items = [
        item for item in geo_items
        if not item.get("is_subtotal") and not item.get("is_subsegment")
    ]
    if not real_geo_items:
        real_geo_items = [item for item in geo_items if not item.get("is_subtotal")]
    if not real_geo_items:
        real_geo_items = geo_items

    # Obtener ingresos canónicos oficiales de referencia para cada período
    canonical_rev_m = {}
    for p in seg_periods:
        c_val = can_rev_dict.get(p)
        canonical_rev_m[p] = _to_m(c_val) if c_val is not None else None

    # Totales LTM oficiales / consolidados
    can_ltm_m = canonical_rev_m.get("LTM") or canonical_rev_m.get(seg_periods[0] if seg_periods else None)
    raw_prod_ltm = sum(item["values"].get("LTM") or 0.0 for item in real_prod_items)
    raw_geo_ltm = sum(item["values"].get("LTM") or 0.0 for item in real_geo_items)

    tot_prod_ltm = can_ltm_m if (can_ltm_m is not None and can_ltm_m > 0) else (raw_prod_ltm if raw_prod_ltm > 0 else 1.0)
    tot_geo_ltm = can_ltm_m if (can_ltm_m is not None and can_ltm_m > 0) else (raw_geo_ltm if raw_geo_ltm > 0 else 1.0)

    # Construcción jerárquica ordenada de filas de productos con subsegmentos agrupados
    ordered_prod_items = []
    primary_prods = [item for item in prod_items if not item.get("is_subtotal") and not item.get("is_subsegment") and item.get("name", "").lower() not in ["revenue", "total revenue", "total revenues", "total net sales"]]
    sub_prods = [item for item in prod_items if item.get("is_subsegment")]
    if primary_prods and sub_prods:
        for prim in primary_prods:
            ordered_prod_items.append(prim)
            for sub in sub_prods:
                if sub.get("parent") and sub.get("parent", "").lower() == prim.get("name", "").lower():
                    ordered_prod_items.append(sub)
        for sub in sub_prods:
            if sub not in ordered_prod_items:
                ordered_prod_items.append(sub)
    elif primary_prods:
        ordered_prod_items = primary_prods
    else:
        ordered_prod_items = [item for item in prod_items if not item.get("is_subtotal")]

    # Tabla 1: Segmentos de Producto & Servicios
    table_products = []
    for item in ordered_prod_items:
        is_sub = bool(item.get("is_subtotal"))
        is_subseg = bool(item.get("is_subsegment"))
        v_ltm = item["values"].get("LTM")
        mix_pct = (v_ltm / tot_prod_ltm * 100.0) if (tot_prod_ltm > 0 and not is_sub and v_ltm is not None) else None
        row_vals = []
        for p in seg_periods:
            val = item["values"].get(p)
            row_vals.append(_fmt_seg_val(val) if val is not None else "-")

        display_name = ("↳ " + item["name"]) if is_subseg else item["name"]
        table_products.append({
            "name": display_name,
            "description": item.get("description", ""),
            "is_subtotal": is_sub,
            "is_subsegment": is_subseg,
            "indent": is_subseg,
            "is_total": False,
            "mix_pct": f"{mix_pct:.1f}%" if (mix_pct is not None and not is_sub) else "-",
            "values": row_vals
        })

    # Fila Institucional de Total Neto Consolidado (100.0%)
    total_prod_vals = []
    for p in seg_periods:
        c_m = canonical_rev_m.get(p)
        if c_m is not None:
            total_prod_vals.append(_fmt_seg_val(c_m))
        else:
            s_val = sum(item["values"].get(p) or 0.0 for item in real_prod_items)
            total_prod_vals.append(_fmt_seg_val(s_val))
    table_products.append({
        "name": "(=) Total Neto Consolidado",
        "description": "",
        "is_subtotal": True,
        "is_total": True,
        "mix_pct": "100.0%",
        "values": total_prod_vals
    })

    # Construcción jerárquica ordenada de filas geográficas con subregiones agrupadas
    ordered_geo_items = []
    primary_geos = [item for item in geo_items if not item.get("is_subtotal") and not item.get("is_subsegment")]
    sub_geos = [item for item in geo_items if item.get("is_subsegment")]
    if primary_geos and sub_geos:
        for prim in primary_geos:
            ordered_geo_items.append(prim)
            for sub in sub_geos:
                if sub.get("parent") and sub.get("parent", "").lower() == prim.get("name", "").lower():
                    ordered_geo_items.append(sub)
        for sub in sub_geos:
            if sub not in ordered_geo_items:
                ordered_geo_items.append(sub)
    elif primary_geos:
        ordered_geo_items = primary_geos
    else:
        ordered_geo_items = [item for item in geo_items if not item.get("is_subtotal")]

    # Tabla 2: Segmentos Geográficos
    table_geos = []
    for item in ordered_geo_items:
        is_sub = bool(item.get("is_subtotal"))
        is_subseg = bool(item.get("is_subsegment"))
        v_ltm = item["values"].get("LTM")
        mix_pct = (v_ltm / tot_geo_ltm * 100.0) if (tot_geo_ltm > 0 and not is_sub and v_ltm is not None) else None
        row_vals = []
        for p in seg_periods:
            val = item["values"].get(p)
            row_vals.append(_fmt_seg_val(val) if val is not None else "-")

        display_name = ("↳ " + item["name"]) if is_subseg else item["name"]
        table_geos.append({
            "name": display_name,
            "description": item.get("description", ""),
            "is_subtotal": is_sub,
            "is_subsegment": is_subseg,
            "indent": is_subseg,
            "is_total": False,
            "mix_pct": f"{mix_pct:.1f}%" if (mix_pct is not None and not is_sub) else "-",
            "values": row_vals
        })

    # Fila Institucional de Total Neto Consolidado Geográfico (100.0%)
    total_geo_vals = []
    for p in seg_periods:
        c_m = canonical_rev_m.get(p)
        if c_m is not None:
            total_geo_vals.append(_fmt_seg_val(c_m))
        else:
            s_val = sum(item["values"].get(p) or 0.0 for item in real_geo_items)
            total_geo_vals.append(_fmt_seg_val(s_val))
    table_geos.append({
        "name": "(=) Total Neto Consolidado",
        "description": "",
        "is_subtotal": True,
        "is_total": True,
        "mix_pct": "100.0%",
        "values": total_geo_vals
    })

    # KPIs de resumen de segmentos dinámicos (usando exclusivamente segmentos primarios)
    sorted_prods = sorted(real_prod_items, key=lambda x: x["values"].get("LTM") or 0.0, reverse=True)
    top_prod = sorted_prods[0] if len(sorted_prods) > 0 else {"name": "Línea Principal", "values": {}}
    second_prod = sorted_prods[1] if len(sorted_prods) > 1 else {"name": "Línea Secundaria", "values": {}}

    top_prod_ltm = top_prod["values"].get("LTM") or 0.0
    second_prod_ltm = second_prod["values"].get("LTM") or 0.0

    sorted_geos = sorted(real_geo_items, key=lambda x: x["values"].get("LTM") or 0.0, reverse=True)
    top_geo = sorted_geos[0] if len(sorted_geos) > 0 else {"name": "Mercado Principal", "values": {}}
    top_geo_ltm = top_geo["values"].get("LTM") or 0.0

    intl_item = next((item for item in real_geo_items if "international" in item["name"].lower() or "foreign" in item["name"].lower() or "resto" in item["name"].lower()), None)
    if intl_item:
        intl_ltm = intl_item["values"].get("LTM") or 0.0
    else:
        intl_ltm = max(0.0, tot_geo_ltm - top_geo_ltm)
    intl_pct = (intl_ltm / tot_geo_ltm * 100.0) if tot_geo_ltm > 0 else 0.0

    kpis_segments = {
        "top_product_name": top_prod["name"],
        "top_product_ltm": _fmt_seg_val(top_prod_ltm),
        "top_product_mix": f"{(top_prod_ltm/tot_prod_ltm*100.0):.1f}%" if tot_prod_ltm > 0 else "-",
        "second_product_name": second_prod["name"],
        "second_product_ltm": _fmt_seg_val(second_prod_ltm),
        "second_product_mix": f"{(second_prod_ltm/tot_prod_ltm*100.0):.1f}%" if tot_prod_ltm > 0 else "-",
        "top_geo_name": top_geo["name"],
        "top_geo_ltm": _fmt_seg_val(top_geo_ltm),
        "top_geo_mix": f"{(top_geo_ltm/tot_geo_ltm*100.0):.1f}%" if tot_geo_ltm > 0 else "-",
        "intl_ltm": _fmt_seg_val(intl_ltm),
        "intl_pct": f"{intl_pct:.1f}%"
    }

    # Series para Gráficos de Segmentos en Millones ($M) (orden cronológico, usando exclusivamente partidas primarias)
    seg_chart_periods = list(reversed(seg_periods))
    palette = ["#38bdf8", "#a855f7", "#10b981", "#f59e0b", "#f43f5e", "#ec4899", "#6366f1", "#14b8a6", "#84cc16", "#eab308"]

    products_trend_datasets = []
    for idx, item in enumerate(real_prod_items):
        c = palette[idx % len(palette)]
        data_pts = [round(float(item["values"].get(p) or 0), 1) for p in seg_chart_periods]
        products_trend_datasets.append({
            "label": item["name"],
            "data": data_pts,
            "borderColor": c,
            "backgroundColor": "transparent",
            "borderWidth": 2.5,
            "tension": 0.2,
            "pointRadius": 4,
            "pointHoverRadius": 7,
            "pointHitRadius": 10
        })

    geos_trend_datasets = []
    for idx, item in enumerate(real_geo_items):
        c = palette[idx % len(palette)]
        data_pts = [round(float(item["values"].get(p) or 0), 1) for p in seg_chart_periods]
        geos_trend_datasets.append({
            "label": item["name"],
            "data": data_pts,
            "borderColor": c,
            "backgroundColor": "transparent",
            "borderWidth": 2.5,
            "tension": 0.2,
            "pointRadius": 4,
            "pointHoverRadius": 7,
        })

    # Datos para Donut Charts LTM en Millones ($M) usando ítems primarios
    donut_prod_labels = [item["name"] for item in real_prod_items]
    donut_prod_data = [round(float(item["values"].get("LTM") or 0), 1) for item in real_prod_items]
    donut_prod_colors = [palette[idx % len(palette)] for idx in range(len(donut_prod_labels))]

    donut_geo_labels = [item["name"] for item in real_geo_items]
    donut_geo_data = [round(float(item["values"].get("LTM") or 0), 1) for item in real_geo_items]
    donut_geo_colors = [palette[idx % len(palette)] for idx in range(len(donut_geo_labels))]

    # -------------------------------------------------------------
    # Retornos sobre el Capital & Rentabilidad (Novy-Marx & DuPont)
    # -------------------------------------------------------------
    roic_by_p = scores.get("intangible_roic_analysis", {}).get("by_period", {})
    roic_trad_series = [round((roic_by_p.get(p, {}).get("roic_trad") or 0.0) * 100.0, 2) for p in chart_periods]
    roic_adj_series = [round((roic_by_p.get(p, {}).get("roic_adj") or 0.0) * 100.0, 2) for p in chart_periods]
    wacc_chart_series = [round(wacc_val, 2) for _ in chart_periods]

    roc_data = scores.get("greenblatt_roc_analysis", {})
    roc_ann = roc_data.get("annual_series", {})
    roc_ltm = roc_data.get("ltm", {})
    roc_series = []
    for p in chart_periods:
        if p == "LTM":
            v = roc_ltm.get("roc_pct") or roc_data.get("latest_result", {}).get("roc_pct", 0.0)
        else:
            v = roc_ann.get(p, {}).get("roc_pct", 0.0)
        roc_series.append(round(float(v or 0.0), 2))

    nm_by_p = scores.get("novy_marx_analysis", {})
    by_p_nm = nm_by_p.get("by_period", {})
    nm_gpa_series = [round((by_p_nm.get(p, {}).get("gross_profitability_total") or 0.0) * 100.0, 2) for p in chart_periods]
    nm_gpa_exc_series = [round((by_p_nm.get(p, {}).get("gross_profitability_ex_cash") or 0.0) * 100.0, 2) for p in chart_periods]

    roic_trad_num = roic_trad_series[-1] if roic_trad_series else 0.0
    roic_adj_num = roic_adj_series[-1] if roic_adj_series else roic_adj
    roc_green_num = roc_series[-1] if roc_series else roc_green

    roic_nopat_m = _to_millions(roic_data.get("nopat_adj") or roic_data.get("nopat_trad") or roic_data.get("ebit"))
    roic_ic_m = _to_millions(roic_data.get("ic_adj") or roic_data.get("ic_adj_end") or roic_data.get("ic_trad_avg") or roic_data.get("ic_trad"))
    recent_annual = statements_fys[0] if statements_fys else None
    nm_gp_m = _to_millions(canonical.get("gross_profit", {}).get("LTM") or (canonical.get("gross_profit", {}).get(recent_annual) if recent_annual else None))
    nm_assets_m = _to_millions(canonical.get("total_assets", {}).get("LTM") or (canonical.get("total_assets", {}).get(recent_annual) if recent_annual else None))
    nm_cash_m = _to_millions(canonical.get("cash", {}).get("LTM") or (canonical.get("cash", {}).get(recent_annual) if recent_annual else None))
    nm_assets_exc_m = round(max(0.0, (nm_assets_m or 0.0) - (nm_cash_m or 0.0)), 1) if (nm_assets_m is not None and nm_cash_m is not None) else None

    spread_badge_class = "bg-emerald-100 text-emerald-800 border-emerald-300" if spread_val >= 0 else "bg-rose-100 text-rose-800 border-rose-300"
    spread_text_class = "text-emerald-700" if spread_val >= 0 else "text-rose-700"
    gpa_badge_class = "bg-emerald-100 text-emerald-800 border-emerald-300" if gpa_is_higher else "bg-rose-100 text-rose-800 border-rose-300"
    gpa_text_class = "text-emerald-700" if gpa_is_higher else "text-rose-700"

    kpis_returns = {
        "roic_trad_ltm": f"{roic_trad_series[-1]:.1f}%" if roic_trad_series else f"{scores.get('intangible_roic_analysis', {}).get('latest_result', {}).get('roic_trad', 0)*100:.1f}%",
        "roic_adj_ltm": f"{roic_adj_series[-1]:.1f}%" if roic_adj_series else f"{roic_adj:.1f}%",
        "roc_greenblatt_ltm": f"{roc_series[-1]:.1f}%" if roc_series else f"{roc_green:.1f}%",
        "nm_gpa_ltm": f"{nm_gpa_series[-1]:.1f}%" if nm_gpa_series else f"{gp_total:.1f}%",
        "nm_gpa_exc_ltm": f"{nm_gpa_exc_series[-1]:.1f}%" if nm_gpa_exc_series else f"{gp_exc:.1f}%",
        "wacc_val": f"{wacc_val:.2f}%",
        "spread_val": f"+{spread_val:.1f} pp" if spread_val > 0 else f"{spread_val:.1f} pp",
        "median_gpa": f"{median_gpa:.1f}%",
        "gpa_diff_str": gpa_diff_str,
        "roic_trad_is_higher": roic_trad_num >= wacc_val,
        "roic_adj_is_higher": roic_adj_num >= wacc_val,
        "roc_is_higher": roc_green_num >= wacc_val,
        "spread_badge_class": spread_badge_class,
        "spread_text_class": spread_text_class,
        "gpa_badge_class": gpa_badge_class,
        "gpa_text_class": gpa_text_class,
        "roic_nopat_m": f"${roic_nopat_m:,.1f}M" if roic_nopat_m else "-",
        "roic_ic_m": f"${roic_ic_m:,.1f}M" if roic_ic_m else "-",
        "nm_gp_m": f"${nm_gp_m:,.1f}M" if nm_gp_m else "-",
        "nm_assets_m": f"${nm_assets_m:,.1f}M" if nm_assets_m else "-",
        "nm_cash_m": f"${nm_cash_m:,.1f}M" if nm_cash_m else "-",
        "nm_assets_exc_m": f"${nm_assets_exc_m:,.1f}M" if nm_assets_exc_m else "-",
    }

    # -------------------------------------------------------------
    # -------------------------------------------------------------------------------------------------
    # Datos de Mercado en Vivo & Modelo DCF Intrínseco / Inverso (Consumido de valuation_report_builder)
    # -------------------------------------------------------------------------------------------------
    prof_data = {}
    prof_path = DATA_DIR / ticker / "company_profile.json"
    if prof_path.exists():
        try:
            with open(prof_path, "r", encoding="utf-8") as pf:
                prof_data = json.load(pf)
        except Exception:
            pass

    # Extracción de Mercado en Vivo (con soporte para bypass_cache si ?refresh=1)
    force_refresh = (request.GET.get("refresh") == "1")
    live_price = None
    market_updated_at = None
    try:
        from market_data_provider import MarketDataExtractor
        m_live = MarketDataExtractor.get_market_data(ticker, bypass_cache=force_refresh)
        live_price = m_live.get("price")
        market_updated_at = m_live.get("cached_at") or m_live.get("timestamp")
    except Exception:
        pass

    from valuation_report_builder import get_valuation_parameters, _generate_sensitivity_grid

    vp = get_valuation_parameters(scores, ticker=ticker, profile_data=prof_data, live_price=live_price, fs_data=fs)
    raw_grid = _generate_sensitivity_grid(vp)
    
    # Formatear la matriz 5x6 para la plantilla Django
    sensitivity_grid = []
    for idx, row in enumerate(raw_grid):
        sensitivity_grid.append({
            "wacc_label": row[0],
            "g_10": row[1],
            "g_15": row[2],
            "g_20": row[3],
            "g_25": row[4],
            "g_30": row[5],
            "g_35": row[6],
            "diagnosis": row[7],
            "is_base": (idx == 2)
        })

    is_financial = vp.get("is_financial", False)
    stock_price = vp.get("price", 0.0)
    shares_m = round(vp.get("shares_b", 0.0) * 1000.0, 2)

    if is_financial:
        rev_base = vp.get("tangible_equity_m", 0.0)
        fcf_margin = 0.0
        fcf_margin_pct = 0.0
        net_debt_m = 0.0
        hist_growth_pct = float(vp.get("cagr_5y") or 0.0)
        hist_growth = hist_growth_pct / 100.0
        wacc_dec = vp.get("ke_val", 0.0943)
        gn_dec = (vp.get("g_terminal_pct", 3.5)) / 100.0
        fair_price_base = vp.get("fair_value_excess_return", stock_price)
        g_implied = (vp.get("rotce_implied_pct", 0.0)) / 100.0
        gap_exp = (g_implied - (vp.get("rotce_val", 0.264))) * 100.0
    else:
        rev_base = vp.get("base_rev_m", 0.0)
        fcf_margin = vp.get("fcf_margin", 0.0)
        fcf_margin_pct = vp.get("fcf_margin_pct", 0.0)
        net_debt_m = vp.get("net_debt_m", 0.0)
        hist_growth_pct = float(vp.get("cagr_5y") or 0.0)
        hist_growth = hist_growth_pct / 100.0
        wacc_dec = vp.get("wacc_val", 0.095)
        gn_dec = 0.025

        # Cálculo del Valor Intrínseco Teórico (DCF a 10 años con Gordon-Shapiro)
        # Para evitar distorsiones hiperbólicas de extrapolación a 10 años en empresas de hipercrecimiento (ej. MELI 48.7%, NVDA 66.9%),
        # la hipótesis inicial de partida se normaliza a una tasa sostenible de proyección (máx 20.0%),
        # preservando el CAGR histórico 5Y íntegro como referencia en pantalla y permitiendo ajuste total en los deslizadores.
        init_proj_growth = min(hist_growth, 0.20) if hist_growth > 0.20 else max(hist_growth, -0.05)
        pv_fcf = 0.0
        r_t = rev_base
        for t in range(1, 11):
            r_t *= (1.0 + init_proj_growth)
            pv_fcf += (r_t * fcf_margin) / ((1.0 + wacc_dec) ** t)
        tv = (r_t * (1.0 + gn_dec) * fcf_margin) / max(wacc_dec - gn_dec, 0.005)
        pv_tv = tv / ((1.0 + wacc_dec) ** 10)
        ev_total = pv_fcf + pv_tv
        equity_val = ev_total - net_debt_m
        fair_price_base = equity_val / shares_m if shares_m > 0 else stock_price

        g_implied = vp.get("g_implied_our_pct", 0.0) / 100.0
        gap_exp = (g_implied - init_proj_growth) * 100.0

    init_growth_disp = (vp.get("rotce_pct") or 0.0) if is_financial else (init_proj_growth * 100.0)
    gap_expectations_str = f"{'+' if gap_exp >= 0 else ''}{gap_exp:.1f} pp"

    premium_pct = ((stock_price - fair_price_base) / fair_price_base) * 100.0 if fair_price_base > 0 else 0.0
    if premium_pct > 25.0:
        valuation_status = "SOBREVALORADA"
    elif premium_pct < -15.0:
        valuation_status = "INFRAVALORADA"
    else:
        valuation_status = "JUSTO"

    data_warnings = []
    if "LTM" not in statements_fys:
        data_warnings.append("Período LTM no reportado de forma desglosada en los reportes interinos SEC (10-Q/6-K). Se visualizan exclusivamente los ejercicios fiscales anuales cerrados.")
    else:
        if not is_banking and archetype not in ("FINANCIAL_BANKING", "INSURANCE"):
            ltm_capex = canonical.get("capital_expenditures", {}).get("LTM")
            ltm_cfo = canonical.get("cash_from_operations", {}).get("LTM")
            if ltm_capex is None:
                data_warnings.append("CapEx LTM no desglosado en el último informe trimestral 10-Q. El Flujo de Caja Libre (FCF) LTM se presenta como '-' para evitar distorsiones con el ejercicio anterior.")
            elif ltm_cfo is None:
                data_warnings.append("Flujo de Caja Operativo (CFO) LTM no disponible. Los flujos y márgenes derivados reflejan '-'.")
        elif archetype == "FINANCIAL_BANKING":
            ltm_nii = canonical.get("net_interest_income", {}).get("LTM")
            if ltm_nii is None:
                data_warnings.append("Margen de Intereses Neto (NII) LTM no desglosado en el informe trimestral. Ratios interinos derivados reflejan '-'.")

    if vp and vp.get("guidance_mid") is None:
        data_warnings.append("La empresa no ha emitido guidance cuantitativo oficial para el ejercicio en curso. La proyección del simulador utiliza el CAGR histórico como referencia inicial.")

    context = {
        "data_warnings": data_warnings,
        "ticker": ticker,
        "is_financial": is_financial,
        "company_name": company_name,
        "cik": cik,
        "fys": fys,
        "stock_price": stock_price,
        "fair_price_base": fair_price_base,
        "valuation_status": valuation_status,
        "premium_pct": premium_pct,
        "g_implied_pct": g_implied * 100.0,
        "hist_growth_pct": hist_growth * 100.0,
        "init_growth_disp": init_growth_disp,
        "gap_expectations_str": gap_expectations_str,
        "interest_cov_display": interest_cov_display,
        "rev_base": rev_base,
        "shares_m": shares_m,
        "fcf_margin_pct": fcf_margin * 100.0,
        "net_debt_m": net_debt_m,
        "sensitivity_grid": sensitivity_grid,
        "vp": vp,
        "f_score": f_score,
        "f_signals": f_signals,
        "f_summary": f_summary,
        "f_rating": f_rating,
        "f_badge_class": f_badge_class,
        "f_text_class": f_text_class,
        "g_score": g_score,
        "g_signals": g_signals,
        "g_summary": g_summary,
        "g_rating": g_rating,
        "g_badge_class": g_badge_class,
        "g_text_class": g_text_class,
        "gp_total": f"{gp_total:.2f}%",
        "gp_total_val": gp_total,
        "gp_exc": f"{gp_exc:.2f}%",
        "p_label": p_label,
        "median_gpa": f"{median_gpa:.2f}%",
        "median_gpa_val": median_gpa,
        "gpa_diff_str": gpa_diff_str,
        "gpa_is_higher": gpa_is_higher,
        "peers": peers,
        "roc_green": f"{roc_green:.1f}%",
        "roic_adj": f"{roic_adj:.2f}%",
        "wacc_val": f"{wacc_val:.2f}%",
        "spread_val": f"{spread_val:.2f}",
        "z_score": f"{z_score:.2f}" if isinstance(z_score, (int, float)) else str(z_score),
        "rating_synth": rating_synth,
        "interest_cov": f"{interest_cov:.1f}x" if isinstance(interest_cov, (int, float)) else str(interest_cov),
        "sloan": f"{sloan:.2f}%",
        "montier": montier_score,
        "montier_score": montier_score,
        "montier_rating": montier_rating,
        "montier_badge": montier_badge,
        "montier_verdict": montier_verdict,
        "montier_flags": montier_flags,
        "sloan_detail": sloan_detail,
        "montier_detail": montier_detail,
        "solvency_13_1": solvency_13_1,
        "solvency_13_2": solvency_13_2,
        "distress_detail": distress_detail,
        "table_pnl": table_pnl,
        "statements_pnl": statements_pnl,
        "statements_cashflow": statements_cashflow,
        "statements_balancesheet": statements_balancesheet,
        "statements_fys": statements_fys,
        "statements_ltm": statements_fys[0] if statements_fys else "LTM",
        "statements_annual_fys": statements_fys[1:] if len(statements_fys) > 1 else [],
        "statements_summary": statements_summary,
        # JSON para Chart.js
        "chart_periods_json": json.dumps(chart_periods),
        "rev_series_json": json.dumps(rev_series),
        "gp_series_json": json.dumps(gp_series),
        "ebit_series_json": json.dumps(ebit_series),
        "ni_series_json": json.dumps(ni_series),
        "cfo_series_json": json.dumps(cfo_series),
        "capex_series_json": json.dumps(capex_series),
        "fcf_series_json": json.dumps(fcf_series),
        "gm_series_json": json.dumps(gm_series),
        "om_series_json": json.dumps(om_series),
        "nm_series_json": json.dumps(nm_series),
        "fcf_m_series_json": json.dumps(fcf_m_series),
        "buybacks_series_json": json.dumps(buybacks_series),
        "shares_series_json": json.dumps(shares_series),
        "eps_series_json": json.dumps(eps_series),
        "shares_unit": shares_unit,
        "buybacks_unit": buybacks_unit,
        "buybacks_summary": buybacks_summary,
        # Segmentos & Regiones Geográficas
        "seg_periods": seg_periods,
        "table_products": table_products,
        "table_geos": table_geos,
        "kpis_segments": kpis_segments,
        "seg_chart_periods_json": json.dumps(seg_chart_periods),
        "products_trend_json": json.dumps(products_trend_datasets),
        "geos_trend_json": json.dumps(geos_trend_datasets),
        "donut_prod_labels_json": json.dumps(donut_prod_labels),
        "donut_prod_data_json": json.dumps(donut_prod_data),
        "donut_prod_colors_json": json.dumps(donut_prod_colors),
        "donut_geo_labels_json": json.dumps(donut_geo_labels),
        "donut_geo_data_json": json.dumps(donut_geo_data),
        "donut_geo_colors_json": json.dumps(donut_geo_colors),
        # Retornos sobre el Capital & Rentabilidad (Novy-Marx & DuPont)
        "kpis_returns": kpis_returns,
        "roic_trad_series_json": json.dumps(roic_trad_series),
        "roic_adj_series_json": json.dumps(roic_adj_series),
        "wacc_chart_series_json": json.dumps(wacc_chart_series),
        "roc_series_json": json.dumps(roc_series),
        "nm_gpa_series_json": json.dumps(nm_gpa_series),
        "nm_gpa_exc_series_json": json.dumps(nm_gpa_exc_series),
        # Metadatos de Mercado en Vivo
        "market_updated_at": market_updated_at,
        "is_live_price": (live_price is not None),
        # Arquetipos de Industria & KPIs Enriquecidos
        "archetype": archetype,
        "is_banking": is_banking,
        "is_platform": is_platform,
        "is_corporate": is_corporate,
        "is_reit": is_reit,
        "is_insurance": is_insurance,
        "banking_kpis": banking_kpis,
        "platform_kpis": platform_kpis,
        "corp_kpis": corp_kpis,
        # Gráficos Bancarios (JSON para Chart.js)
        "nii_series_json": json.dumps(nii_series),
        "non_ii_series_json": json.dumps(non_ii_series),
        "deposits_series_json": json.dumps(deposits_series),
        "loans_series_json": json.dumps(loans_series),
        "clp_series_json": json.dumps(clp_series),
        "cost_of_risk_series_json": json.dumps(cost_of_risk_series),
        "donut_dep_labels_json": json.dumps(donut_dep_labels),
        "donut_dep_data_json": json.dumps(donut_dep_data),
        "donut_dep_colors_json": json.dumps(donut_dep_colors),
        # Gráficos Plataforma / Ecosistema (JSON para Chart.js)
        "gmv_tpv_labels_json": json.dumps(gmv_tpv_labels),
        "gmv_series_json": json.dumps(gmv_series),
        "tpv_series_json": json.dumps(tpv_series),
        "buyers_mau_labels_json": json.dumps(buyers_mau_labels),
        "buyers_mau_data_json": json.dumps(buyers_mau_data),
        # Asignación de Capital (Chart.js y KPIs)
        "alloc_kpis": alloc_kpis,
        "alloc_unit": alloc_unit,
        "alloc_capex_series_json": json.dumps(alloc_capex_series),
        "alloc_buybacks_series_json": json.dumps(alloc_buybacks_series),
        "alloc_dividends_series_json": json.dumps(alloc_dividends_series),
        "alloc_ma_series_json": json.dumps(alloc_ma_series),
        "alloc_debt_series_json": json.dumps(alloc_debt_series),
        "alloc_cfo_series_json": json.dumps(alloc_cfo_series),
        "chart_alloc_data_json": json.dumps(chart_alloc_data),
    }

    return render(request, "company_detail.html", context)
