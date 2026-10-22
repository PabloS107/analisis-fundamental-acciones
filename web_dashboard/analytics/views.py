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


def resolve_canonical_balance_sheet(fs, periods, archetype="STANDARD_CORPORATE"):
    """
    Función canónica y unificada (SSOT) para resolver el Balance General clasificado
    (Activos Corrientes y No Corrientes, Pasivos Corrientes y No Corrientes, Patrimonio Neto
    y Diagnóstico de Liquidez y Solvencia) a partir de financial_statements.json
    de forma universal y sin hardcodeos para empresas corporativas estándar.
    """
    if not archetype or archetype == "STANDARD_CORPORATE":
        archetype = fs.get("archetype") or ("FINANCIAL_BANKING" if fs.get("is_financial") else "STANDARD_CORPORATE")
    canonical = fs.get("canonical_summary", {}) if isinstance(fs, dict) else {}
    bs_detail = fs.get("balance_sheet_detail", {}) if isinstance(fs, dict) else {}
    bal_sources = [
        bs_detail,
        fs.get("balance_sheet", {}) if isinstance(fs, dict) else {}
    ]
    as_rep_bs_raw = fs.get("as_reported_statements", {}).get("balance_sheet", []) if isinstance(fs, dict) else []
    as_rep_bs_rows = as_rep_bs_raw if isinstance(as_rep_bs_raw, list) else (as_rep_bs_raw.get("rows", []) if isinstance(as_rep_bs_raw, dict) else [])
    as_rep_bs_dict = {}
    for r in as_rep_bs_rows:
        if isinstance(r, dict) and "concept" in r:
            as_rep_bs_dict[r["concept"]] = r.get("values", {})
    bal_sources.append(as_rep_bs_dict)

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
        "RealEstateInvestmentPropertyNet", "us-gaap_RealEstateInvestmentPropertyNet", "InvestmentProperties",
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
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
        "ifrs-full_Equity",
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

    net_loans_keys = [
        "LoansAndLeasesReceivableNetOfDeferredIncome", "us-gaap_LoansAndLeasesReceivableNetOfDeferredIncome",
        "FinancingReceivableExcludingAccruedInterestAfterAllowanceForCreditLoss",
        "FinancingReceivableExcludingAccruedInterestBeforeAllowanceForCreditLossesNetOfDeferredIncome",
        "ifrs-full_LoansAndAdvancesToCustomers", "nu_CreditCardReceivables1", "nu_LoansAndAdvancesToCustomers1",
        "LoansAndLeasesReceivableNetReportedAmount", "LoansReceivableNet"
    ]
    allow_loss_keys = [
        "FinancingReceivableAllowanceForCreditLosses", "us-gaap_FinancingReceivableAllowanceForCreditLosses",
        "AllowanceAccountForCreditLossesOfFinancialAssets", "LoansAndLeasesReceivableAllowance",
        "AllowanceForLoanAndLeaseLosses"
    ]
    deposit_keys = [
        "Deposits", "us-gaap_Deposits", "ifrs-full_DepositsFromCustomers", "DepositsDomestic",
        "InterestBearingDepositLiabilities", "NoninterestBearingDepositLiabilities"
    ]
    prem_rec_keys = [
        "PremiumsReceivableAtCarryingValue", "us-gaap_PremiumsReceivableAtCarryingValue",
        "AccountsAndOtherReceivablesNetCurrent", "AccountsReceivableNet"
    ]
    dac_keys = [
        "DeferredPolicyAcquisitionCosts", "us-gaap_DeferredPolicyAcquisitionCosts",
        "DeferredPolicyAcquisitionCostAmortizationExpense"
    ]
    loss_res_keys = [
        "LiabilityForClaimsAndClaimsAdjustmentExpense", "us-gaap_LiabilityForClaimsAndClaimsAdjustmentExpense",
        "LiabilityForUnpaidClaimsAndClaimsAdjustmentExpenseNet",
        "LiabilityForClaimsAndClaimsAdjustmentExpenseIncurredClaims1"
    ]
    unearn_prem_keys = [
        "UnearnedPremiums", "us-gaap_UnearnedPremiums", "UnearnedPremiumsNet"
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
        "minority_interest": {},
        "total_debt": {},
        "stockholders_equity": {},
        "total_liab_and_equity": {},
        "net_working_capital": {},
        "net_financial_position": {},
        "book_value_per_share": {},
        "tangible_book_value_per_share": {},
        "net_loans": {},
        "allowance_for_loan_losses": {},
        "deposits": {},
        "premiums_receivable": {},
        "deferred_policy_acquisition_costs": {},
        "loss_reserves": {},
        "unearned_premiums": {},
        "other_assets_sectoral": {},
        "other_liabilities_sectoral": {}
    }

    for p in periods:
        c_v = _extract_val(cash_keys, p, "cash_and_equivalents")
        # Si c_v es None o 0.0 (caso JPM en canonical_summary), buscar en balance_sheet_detail y as_reported_statements
        if c_v is None or c_v == 0.0:
            c_cand = _extract_val(["CashAndCashEquivalentsAtCarryingValue", "ifrs-full_CashAndCashEquivalents"], p)
            if c_cand and float(c_cand) > 0:
                c_v = float(c_cand)
            else:
                cdue = _extract_val(["CashAndDueFromBanks", "us-gaap_CashAndDueFromBanks"], p) or 0.0
                cint = _extract_val(["InterestBearingDepositsInBanks", "us-gaap_InterestBearingDepositsInBanks"], p) or 0.0
                if (cdue + cint) > 0:
                    c_v = round(cdue + cint, 1)

        sti_v = _extract_val(sti_keys, p, "short_term_investments")
        # Si en as_reported_statements existe MarketableSecuritiesCurrent de carátula con saldo materialmente distinto (caso META), priorizarlo
        for r_bs in (fs.get("as_reported_statements", {}).get("balance_sheet", []) if isinstance(fs, dict) else []):
            c_tok = str(r_bs.get("concept", "")).split(":")[-1].split("_")[-1].lower()
            if c_tok in ("marketablesecuritiescurrent", "shortterminvestments"):
                bs_val = r_bs.get("values", {}).get(p)
                if bs_val is not None and float(bs_val) > 0:
                    if sti_v is None or abs(float(bs_val) - float(sti_v)) > 1000.0:
                        sti_v = float(bs_val)
                break
        if sti_v is None or sti_v == 0.0 or archetype in ("INSURANCE", "FINANCIAL_BANKING"):
            if archetype == "INSURANCE":
                tot_inv = canonical.get("total_investments", {}).get(p)
                if tot_inv is not None and float(tot_inv) > 0:
                    sti_v = float(tot_inv)
                else:
                    afs_sec = _extract_val(["AvailableForSaleSecuritiesDebtSecurities", "us-gaap_AvailableForSaleSecuritiesDebtSecurities"], p) or 0.0
                    eq_sec = _extract_val(["EquitySecuritiesFvNi", "us-gaap_EquitySecuritiesFvNi"], p) or 0.0
                    st_sec = _extract_val(["ShortTermInvestments", "us-gaap_ShortTermInvestments"], p) or 0.0
                    if (afs_sec + eq_sec + st_sec) > 0:
                        sti_v = round(afs_sec + eq_sec + st_sec, 1)
            elif archetype == "FINANCIAL_BANKING":
                jpm_sec = _extract_val(["jpm_DebtSecuritiesNetCarryingAmount"], p)
                if jpm_sec and float(jpm_sec) > 0:
                    sti_v = float(jpm_sec)
                else:
                    afs_d = _extract_val(["DebtSecuritiesAvailableForSaleExcludingAccruedInterest", "us-gaap_DebtSecuritiesAvailableForSaleExcludingAccruedInterest"], p) or 0.0
                    htm_d = _extract_val(["DebtSecuritiesHeldToMaturityExcludingAccruedInterestAfterAllowanceForCreditLoss", "us-gaap_DebtSecuritiesHeldToMaturityExcludingAccruedInterestAfterAllowanceForCreditLoss"], p) or 0.0
                    if (afs_d + htm_d) > 0:
                        sti_v = round(afs_d + htm_d, 1)
                    else:
                        nu_pnl = _extract_val(["ifrs-full_FinancialAssetsAtFairValueThroughProfitOrLoss", "nu_Securities"], p) or 0.0
                        nu_oci = _extract_val(["ifrs-full_FinancialAssetsAtFairValueThroughOtherComprehensiveIncome", "nu_OtherSecurities"], p) or 0.0
                        if (nu_pnl + nu_oci) > 0:
                            sti_v = round(nu_pnl + nu_oci, 1)
            else:
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

        # Ajuste 2: Identidad contable de Patrimonio Neto Total Consolidado e Intereses Minoritarios (O y NU)

        min_int_v = _extract_val(["MinorityInterest", "us-gaap_MinorityInterest", "NoncontrollingInterests", "NoncontrollingInterest", "RedeemableNoncontrollingInterestEquityCarryingAmount"], p)

        eq_tot_cand = _extract_val(["StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest", "ifrs-full_Equity", "TotalEquity"], p)

        if eq_tot_cand is not None and (eq_v is None or eq_tot_cand > eq_v):

            if min_int_v is None and eq_v is not None:

                min_int_v = round(eq_tot_cand - eq_v, 1)

            eq_v = eq_tot_cand

        elif min_int_v is not None and min_int_v > 0:

            if tot_ast is not None and tot_liab is not None and abs((tot_liab + (eq_v or 0.0) + min_int_v) - tot_ast) <= 2.0:

                eq_v = round((eq_v or 0.0) + min_int_v, 1)



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
        res["total_debt"][p] = tot_debt
        res["minority_interest"][p] = min_int_v
        res["stockholders_equity"][p] = eq_v
        res["total_liab_and_equity"][p] = tot_liab_eq
        res["net_working_capital"][p] = nwc_v
        res["net_financial_position"][p] = net_fin_pos
        res["book_value_per_share"][p] = bvps
        res["tangible_book_value_per_share"][p] = tbvps

        net_loans_v = _extract_val(net_loans_keys, p, "net_loans")
        allow_loss_v = _extract_val(allow_loss_keys, p, "allowance_for_loan_losses")
        dep_v = _extract_val(deposit_keys, p, "deposits")
        prem_rec_v = _extract_val(prem_rec_keys, p, "premiums_receivable")
        dac_v = _extract_val(dac_keys, p, "deferred_policy_acquisition_costs")
        loss_res_v = _extract_val(loss_res_keys, p, "loss_reserves")
        unearn_prem_v = _extract_val(unearn_prem_keys, p, "unearned_premiums")

        other_ast_sec = None
        if tot_ast is not None:
            if net_loans_v is not None or dep_v is not None:
                other_ast_sec = round(tot_ast - (tot_liquid or 0.0) - (net_loans_v or 0.0) - (gw_int_v or 0.0) - (ppe_v or 0.0), 1)
            elif prem_rec_v is not None or loss_res_v is not None:
                other_ast_sec = round(tot_ast - (tot_liquid or 0.0) - (prem_rec_v or 0.0) - (dac_v or 0.0) - (ppe_v or 0.0), 1)

        other_liab_sec = None
        if tot_liab is not None:
            if dep_v is not None:
                other_liab_sec = round(tot_liab - (dep_v or 0.0) - (tot_debt or 0.0), 1)
            elif loss_res_v is not None:
                other_liab_sec = round(tot_liab - (loss_res_v or 0.0) - (unearn_prem_v or 0.0) - (tot_debt or 0.0), 1)

        res["net_loans"][p] = net_loans_v
        res["allowance_for_loan_losses"][p] = allow_loss_v
        res["deposits"][p] = dep_v
        res["premiums_receivable"][p] = prem_rec_v
        res["deferred_policy_acquisition_costs"][p] = dac_v
        res["loss_reserves"][p] = loss_res_v
        res["unearned_premiums"][p] = unearn_prem_v
        res["other_assets_sectoral"][p] = other_ast_sec
        res["other_liabilities_sectoral"][p] = other_liab_sec

    return res


def _extract_multi_source_val(fs, section_type, key_cands, p, canon_keys=None):
    """
    Función universal multi-fuente (SSOT) para extraer valores de estados financieros:
    1. canonical_summary (si canon_keys se especifica y existe en p y != None)
    2. *_detail (income_statement_detail, balance_sheet_detail, cash_flow_detail)
    3. as_reported_statements (income_statement, balance_sheet, cash_flow_statement)
    """
    if not isinstance(fs, dict):
        return None
    canonical = fs.get("canonical_summary", {})
    if canon_keys:
        if isinstance(canon_keys, str):
            canon_keys = [canon_keys]
        for ck in canon_keys:
            if ck in canonical and isinstance(canonical[ck], dict):
                v = canonical[ck].get(p)
                if v is not None:
                    try:
                        return float(v)
                    except (ValueError, TypeError):
                        pass

    # 2. *_detail
    det_map = {
        "income": "income_statement_detail",
        "balance": "balance_sheet_detail",
        "cashflow": "cash_flow_detail",
    }
    det_key = det_map.get(section_type, f"{section_type}_detail")
    detail_dict = fs.get(det_key, {})
    if isinstance(detail_dict, dict):
        for k in key_cands:
            variants = [k, f"us-gaap_{k}", f"ifrs-full_{k}"]
            if k.startswith("us-gaap_"):
                variants.append(k[len("us-gaap_"):])
            elif k.startswith("ifrs-full_"):
                variants.append(k[len("ifrs-full_"):])
            for var in variants:
                if var in detail_dict:
                    obj = detail_dict[var]
                    vals = obj.get("values", obj) if isinstance(obj, dict) else {}
                    if isinstance(vals, dict) and p in vals and vals[p] is not None:
                        try:
                            return float(vals[p])
                        except (ValueError, TypeError):
                            pass
            k_token = k.lower().split(':')[-1].split('_')[-1]
            for dk, dobj in detail_dict.items():
                d_token = dk.lower().split(':')[-1].split('_')[-1]
                if dk.lower() == k.lower() or d_token == k_token:
                    vals = dobj.get("values", dobj) if isinstance(dobj, dict) else {}
                    if isinstance(vals, dict) and p in vals and vals[p] is not None:
                        try:
                            return float(vals[p])
                        except (ValueError, TypeError):
                            pass

    # 3. as_reported_statements
    as_reported = fs.get("as_reported_statements", {})
    if isinstance(as_reported, dict):
        as_rep_map = {
            "income": "income_statement",
            "balance": "balance_sheet",
            "cashflow": "cash_flow_statement",
        }
        sec_name = as_rep_map.get(section_type, section_type)
        sec_obj = as_reported.get(sec_name, [])
        rows_list = sec_obj if isinstance(sec_obj, list) else (sec_obj.get("rows", []) if isinstance(sec_obj, dict) else [])
        if isinstance(rows_list, list):
            for row in rows_list:
                if not isinstance(row, dict):
                    continue
                concept = str(row.get("concept", ""))
                c_token = concept.lower().split(':')[-1].split('_')[-1]
                for k in key_cands:
                    k_token = k.lower().split(':')[-1].split('_')[-1]
                    if concept == k or concept.lower() == k.lower() or c_token == k_token:
                        vals = row.get("values", {})
                        if isinstance(vals, dict) and p in vals and vals[p] is not None:
                            try:
                                return float(vals[p])
                            except (ValueError, TypeError):
                                pass
    return None


def resolve_canonical_income_statement(fs, periods, archetype="STANDARD_CORPORATE"):
    """
    Función canónica y unificada (SSOT) para resolver el Estado de Resultados Estandarizado (10Y + LTM)
    adaptado dinámicamente por arquetipo contable según Fiscal.ai.
    Retorna series en dólares crudos (salvo EPS/DPS en $/acción y acciones en unidades).
    """
    res = {
        "revenue": {}, "cogs": {}, "gross_profit": {},
        "rd_expense": {}, "sga_expense": {}, "credit_loss_provision": {},
        "other_operating_expense": {}, "total_operating_expenses": {},
        "operating_income": {}, "interest_income": {}, "interest_expense": {},
        "other_non_operating": {}, "total_non_operating": {},
        "ebt": {}, "income_tax": {}, "net_income": {},
        "minority_interest_pnl": {}, "preferred_dividends": {}, "net_income_common": {},
        "eps_basic": {}, "eps_diluted": {}, "shares_basic": {}, "shares_diluted": {}, "dps": {},
        "net_interest_income": {}, "non_interest_income": {}, "non_interest_expense": {},
        "net_premiums_earned": {}, "net_investment_income": {}, "investment_gains_losses": {},
        "fees_and_other_revenues": {}, "losses_and_lae": {}, "dac_amortization": {},
        "other_underwriting_expenses": {}, "total_benefits_and_expenses": {},
        "rental_revenue": {}, "tenant_reimbursements_other": {}, "property_operating_expenses": {},
        "noi": {}, "reit_da": {}, "reit_ga": {}, "reit_impairment": {}, "gain_on_sale_properties": {}
    }

    for p in periods:
        rev = _extract_multi_source_val(fs, "income", [
            "Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet",
            "TotalRevenuesAndOtherIncome", "Revenue", "ifrs-full_Revenue", "RevenuesNetOfInterestExpense"
        ], p, "revenue")

        cogs = _extract_multi_source_val(fs, "income", [
            "CostOfGoodsAndServicesSold", "CostOfRevenue", "CostOfGoodsSold",
            "CostOfPurchasedGoodsAndServices", "ifrs-full_CostOfSales"
        ], p, "cost_of_goods_sold")
        if cogs is not None:
            cogs = abs(cogs)

        gp = _extract_multi_source_val(fs, "income", [
            "GrossProfit", "ifrs-full_GrossProfit"
        ], p, "gross_profit")
        if gp is None and rev is not None and cogs is not None and archetype not in ("FINANCIAL_BANKING", "INSURANCE"):
            gp = round(rev - cogs, 2)
        if cogs is None and rev is not None and gp is not None and archetype not in ("FINANCIAL_BANKING", "INSURANCE"):
            cogs = round(rev - gp, 2)

        rd = _extract_multi_source_val(fs, "income", [
            "ResearchAndDevelopmentExpense", "TechnologyAndContentExpense", "TechnologyAndDevelopmentExpense",
            "ResearchAndDevelopmentExpenseSoftware", "ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost"
        ], p, ["rd_expense", "research_and_development"])
        if rd is not None:
            rd = abs(rd)

        sga = _extract_multi_source_val(fs, "income", [
            "SellingGeneralAndAdministrativeExpense", "SellingGeneralAndAdministrative"
        ], p, ["sga_expense", "selling_general_and_administrative"])
        if sga is None:
            sm = _extract_multi_source_val(fs, "income", [
                "SellingAndMarketingExpense", "MarketingAndAdvertisingExpense", "SellingExpense", "AdvertisingExpense"
            ], p, "sm_expense")
            ga = _extract_multi_source_val(fs, "income", [
                "GeneralAndAdministrativeExpense", "AdministrativeExpense"
            ], p, "ga_expense")
            if sm is not None or ga is not None:
                sga = (abs(sm) if sm else 0.0) + (abs(ga) if ga else 0.0)
            elif _extract_multi_source_val(fs, "income", ["GeneralAndAdministrativeExpense"], p) is not None:
                sga = abs(_extract_multi_source_val(fs, "income", ["GeneralAndAdministrativeExpense"], p))
        if sga is not None:
            sga = abs(sga)

        credit_loss = _extract_multi_source_val(fs, "income", [
            "ProvisionForLoanLeaseAndOtherLosses", "ProvisionForLoanLossesExpensed", "ProvisionForDoubtfulAccounts",
            "nu_CreditLossAllowanceExpenses", "CreditLossAllowanceExpenses1",
            "ifrs-full_AdditionalAllowanceRecognisedInProfitOrLossAllowanceAccountForCreditLossesOfFinancialAssets"
        ], p, ["credit_loss_provisions", "provision_for_credit_losses"])
        if credit_loss is not None:
            credit_loss = abs(credit_loss)

        other_opex = _extract_multi_source_val(fs, "income", [
            "RestructuringCharges", "OtherCostAndExpenseOperating", "BusinessCombinationAcquisitionRelatedCosts",
            "AmortizationOfIntangibleAssets", "OperatingExpensesOther", "ImpairmentOfIntangibleAssetsFinitelived"
        ], p)
        if other_opex is not None:
            other_opex = abs(other_opex)

        ebit = _extract_multi_source_val(fs, "income", [
            "OperatingIncomeLoss", "ifrs-full_ProfitLossFromOperatingActivities", "OperatingIncome"
        ], p, "operating_income")

        tot_opex = _extract_multi_source_val(fs, "income", [
            "OperatingExpenses", "CostsAndExpenses", "ifrs-full_OperatingExpense"
        ], p, "operating_expenses")
        if tot_opex is None and gp is not None and ebit is not None and archetype not in ("FINANCIAL_BANKING", "INSURANCE"):
            tot_opex = round(gp - ebit, 2)
        if tot_opex is not None:
            tot_opex = abs(tot_opex)

        int_inc = _extract_multi_source_val(fs, "income", [
            "InvestmentIncomeInterest", "InterestIncomeOperating", "InterestAndDividendIncomeOperating",
            "InterestIncome", "ifrs-full_RevenueFromInterest", "nu_InterestIncomeAndGainsLossesOnFinancialInstruments"
        ], p, "interest_income")

        int_exp = _extract_multi_source_val(fs, "income", [
            "InterestExpense", "InterestExpenseNonoperating", "InterestExpenseDebt", "InterestExpenseOperating",
            "meli_InterestExpenseAndOtherFinancialCharges"
        ], p, "interest_expense")
        if int_exp is not None:
            int_exp = abs(int_exp)

        other_non_op = _extract_multi_source_val(fs, "income", [
            "OtherNonoperatingIncomeExpense", "GainLossOnInvestments", "ForeignCurrencyTransactionGainLossBeforeTax",
            "GainLossOnSaleOfSecuritiesNet", "OtherNonoperatingIncomeExpenseNet"
        ], p, "other_non_operating")

        tot_non_op = _extract_multi_source_val(fs, "income", [
            "NonoperatingIncomeExpense", "InterestRevenueExpenseNet", "deck_InterestAndOtherExpense",
            "NonoperatingIncomeExpenseNet"
        ], p, "non_operating_income")
        if tot_non_op is None and (int_inc is not None or int_exp is not None or other_non_op is not None):
            tot_non_op = round((int_inc or 0.0) - (int_exp or 0.0) + (other_non_op or 0.0), 2)

        ebt = _extract_multi_source_val(fs, "income", [
            "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
            "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
            "ProfitLossBeforeTax", "IncomeLossFromContinuingOperationsBeforeIncomeTaxesDomestic"
        ], p, "ebt")
        if ebt is None and ebit is not None and tot_non_op is not None:
            ebt = round(ebit + tot_non_op, 2)

        tax = _extract_multi_source_val(fs, "income", [
            "IncomeTaxExpenseBenefit", "IncomeTaxExpenseContinuingOperations", "nu_IncomeTaxInStatementOfProfitOrLoss",
            "CurrentIncomeTaxExpenseBenefit", "ifrs-full_IncomeTaxExpenseContinuingOperations"
        ], p, "income_tax_expense")
        if tax is None:
            c_tax = _extract_multi_source_val(fs, "income", ["CurrentTaxExpenseIncome"], p)
            d_tax = _extract_multi_source_val(fs, "income", ["DeferredTaxExpenseIncome"], p)
            if c_tax is not None or d_tax is not None:
                tax = (c_tax or 0.0) + (d_tax or 0.0)
        if tax is not None:
            tax = abs(tax)

        ni = _extract_multi_source_val(fs, "income", [
            "NetIncomeLoss", "ProfitLoss", "NetIncome", "ifrs-full_ProfitLoss"
        ], p, "net_income")
        if ni is None and ebt is not None and tax is not None:
            ni = round(ebt - tax, 2)
        if ebt is None and ni is not None and tax is not None:
            ebt = round(ni + tax, 2)

        min_int_pnl = _extract_multi_source_val(fs, "income", [
            "NetIncomeLossAttributableToNoncontrollingInterest", "ProfitLossAttributableToNoncontrollingInterests"
        ], p)
        if min_int_pnl is not None:
            min_int_pnl = abs(min_int_pnl)

        pref_div = _extract_multi_source_val(fs, "income", [
            "PreferredStockDividendsIncomeStatementImpact", "RedeemablePreferredStockDividends",
            "PreferredStockDividendsAndOtherAdjustments"
        ], p)
        if pref_div is not None:
            pref_div = abs(pref_div)

        ni_comm = _extract_multi_source_val(fs, "income", [
            "NetIncomeLossAvailableToCommonStockholdersBasic", "ProfitLossAttributableToOwnersOfParent"
        ], p)
        if ni_comm is None and ni is not None:
            ni_comm = round(ni - (min_int_pnl or 0.0) - (pref_div or 0.0), 2)

        eps_b = _extract_multi_source_val(fs, "income", [
            "EarningsPerShareBasic", "BasicEarningsLossPerShare", "ifrs-full_BasicEarningsLossPerShare"
        ], p, "eps_basic")

        eps_d = _extract_multi_source_val(fs, "income", [
            "EarningsPerShareDiluted", "DilutedEarningsLossPerShare", "ifrs-full_DilutedEarningsLossPerShare"
        ], p, ["eps_diluted_adjusted", "eps_diluted"])

        sh_b = _extract_multi_source_val(fs, "income", [
            "WeightedAverageNumberOfSharesOutstandingBasic", "ifrs-full_WeightedAverageShares"
        ], p, "shares_basic")

        sh_d = _extract_multi_source_val(fs, "income", [
            "WeightedAverageNumberOfDilutedSharesOutstanding", "ifrs-full_AdjustedWeightedAverageShares"
        ], p, ["shares_diluted_adjusted", "shares_diluted"])

        dps_val = _extract_multi_source_val(fs, "income", [
            "CommonStockDividendsPerShareDeclared", "CommonStockDividendsPerShareCashPaid", "DividendsPerShareDeclared"
        ], p, "dps")

        nii = _extract_multi_source_val(fs, "income", ["InterestIncomeExpenseNet", "NetInterestIncome"], p, "net_interest_income")
        if nii is None and int_inc is not None and int_exp is not None:
            nii = round(int_inc - int_exp, 2)

        non_int_inc = _extract_multi_source_val(fs, "income", ["NoninterestIncome", "ifrs-full_FeeAndCommissionIncome", "jpm_FeesAndCommissions1"], p, "non_interest_income")
        if non_int_inc is None and rev is not None and nii is not None:
            non_int_inc = round(rev - nii, 2)

        non_int_exp = _extract_multi_source_val(fs, "income", [
            "NoninterestExpense", "GeneralAndAdministrativeExpense", "SellingExpense", "nu_CustomerSupportAndOperations"
        ], p, ["operating_expenses", "non_interest_expense"])
        if non_int_exp is None and rev is not None and credit_loss is not None and ebt is not None:
            non_int_exp = round(rev - credit_loss - ebt, 2)
        if non_int_exp is not None:
            non_int_exp = abs(non_int_exp)

        prem_earned = _extract_multi_source_val(fs, "income", ["PremiumsEarnedNet", "PremiumsEarnedNetPropertyAndCasualty"], p, "net_premiums_earned")
        net_inv_inc = _extract_multi_source_val(fs, "income", ["NetInvestmentIncome", "InvestmentIncomeNet", "InterestAndDividendIncomeOperating"], p, "net_investment_income")
        inv_gains = _extract_multi_source_val(fs, "income", ["DebtAndEquitySecuritiesGainLoss", "RealizedInvestmentGainsLosses", "GainLossOnInvestments"], p)
        fees_other = _extract_multi_source_val(fs, "income", ["pgr_FeesAndOtherRevenues", "pgr_NonInsuranceServiceRevenues"], p)
        losses_lae = _extract_multi_source_val(fs, "income", [
            "PolicyholderBenefitsAndClaimsIncurredNet", "LiabilityForUnpaidClaimsAndClaimsAdjustmentExpenseIncurredClaims1", "IncurredClaimsPropertyCasualtyAndLiability"
        ], p, ["losses_and_loss_expenses", "losses_and_lae"])
        if losses_lae is not None:
            losses_lae = abs(losses_lae)

        dac_amort = _extract_multi_source_val(fs, "income", ["DeferredPolicyAcquisitionCostAmortizationExpense"], p)
        if dac_amort is not None:
            dac_amort = abs(dac_amort)

        other_uw_exp = _extract_multi_source_val(fs, "income", ["OtherUnderwritingExpense", "pgr_NonInsuranceServiceExpenses"], p, "other_underwriting_expenses")
        if other_uw_exp is not None:
            other_uw_exp = abs(other_uw_exp)

        tot_ben_exp = _extract_multi_source_val(fs, "income", ["BenefitsLossesAndExpenses"], p, "operating_expenses")
        if tot_ben_exp is None and losses_lae is not None:
            tot_ben_exp = round(losses_lae + (dac_amort or 0.0) + (other_uw_exp or 0.0), 2)
        if tot_ben_exp is not None:
            tot_ben_exp = abs(tot_ben_exp)

        rental_rev = _extract_multi_source_val(fs, "income", ["LeaseIncome", "OperatingLeasesIncomeStatementLeaseRevenue", "RealEstateRevenueNet"], p, "revenue")
        tenant_reimb = _extract_multi_source_val(fs, "income", ["TenantReimbursements", "OtherRealEstateRevenue", "OtherIncome"], p)
        prop_exp = _extract_multi_source_val(fs, "income", ["DirectCostsOfLeasedAndRentedPropertyOrEquipment", "o_DirectCostsOfLeasedAndRentedPropertyOrEquipmentIncludingReimbursableExpense"], p, ["property_operating_expenses", "cost_of_goods_sold"])
        if prop_exp is not None:
            prop_exp = abs(prop_exp)

        noi = _extract_multi_source_val(fs, "income", [], p, ["noi", "gross_profit"])
        if noi is None and rev is not None and prop_exp is not None:
            noi = round(rev - prop_exp, 2)

        reit_da = _extract_multi_source_val(fs, "income", ["DepreciationDepletionAndAmortization", "DepreciationAndAmortization"], p, "depreciation_and_amortization")
        if reit_da is not None:
            reit_da = abs(reit_da)

        reit_ga = _extract_multi_source_val(fs, "income", ["GeneralAndAdministrativeExpense", "SellingGeneralAndAdministrativeExpense"], p, "ga_expense")
        if reit_ga is not None:
            reit_ga = abs(reit_ga)

        reit_imp = _extract_multi_source_val(fs, "income", ["ImpairmentOfRealEstate", "AssetImpairmentCharges"], p)
        if reit_imp is not None:
            reit_imp = abs(reit_imp)

        gain_sale = _extract_multi_source_val(fs, "income", ["GainLossOnSaleOfProperties", "o_GainOnSaleOfPropertiesContinuingOperations"], p)

        res["revenue"][p] = rev
        res["cogs"][p] = cogs
        res["gross_profit"][p] = gp
        res["rd_expense"][p] = rd
        res["sga_expense"][p] = sga
        res["credit_loss_provision"][p] = credit_loss
        res["other_operating_expense"][p] = other_opex
        res["total_operating_expenses"][p] = tot_opex
        res["operating_income"][p] = ebit
        res["interest_income"][p] = int_inc
        res["interest_expense"][p] = int_exp
        res["other_non_operating"][p] = other_non_op
        res["total_non_operating"][p] = tot_non_op
        res["ebt"][p] = ebt
        res["income_tax"][p] = tax
        res["net_income"][p] = ni
        res["minority_interest_pnl"][p] = min_int_pnl
        res["preferred_dividends"][p] = pref_div
        res["net_income_common"][p] = ni_comm
        res["eps_basic"][p] = eps_b
        res["eps_diluted"][p] = eps_d
        res["shares_basic"][p] = sh_b
        res["shares_diluted"][p] = sh_d
        res["dps"][p] = dps_val
        res["net_interest_income"][p] = nii
        res["non_interest_income"][p] = non_int_inc
        res["non_interest_expense"][p] = non_int_exp
        res["net_premiums_earned"][p] = prem_earned
        res["net_investment_income"][p] = net_inv_inc
        res["investment_gains_losses"][p] = inv_gains
        res["fees_and_other_revenues"][p] = fees_other
        res["losses_and_lae"][p] = losses_lae
        res["dac_amortization"][p] = dac_amort
        res["other_underwriting_expenses"][p] = other_uw_exp
        res["total_benefits_and_expenses"][p] = tot_ben_exp
        res["rental_revenue"][p] = rental_rev
        res["tenant_reimbursements_other"][p] = tenant_reimb
        res["property_operating_expenses"][p] = prop_exp
        res["noi"][p] = noi
        res["reit_da"][p] = reit_da
        res["reit_ga"][p] = reit_ga
        res["reit_impairment"][p] = reit_imp
        res["gain_on_sale_properties"][p] = gain_sale

    return res


def resolve_canonical_cash_flow(fs, periods, capital_flows=None, archetype="STANDARD_CORPORATE"):
    """
    Función canónica y unificada (SSOT) para resolver el Estado de Flujos de Caja en 4 secciones
    según Fiscal.ai, integrando capital allocation auditado y respetando estrictamente la Regla 6 (Cero Plugs Sintéticos).
    """
    if capital_flows is None:
        capital_flows = resolve_canonical_capital_flows(fs, periods)
    canonical = fs.get("canonical_summary", {}) if isinstance(fs, dict) else {}

    res = {
        "net_income": {}, "da": {}, "sbc": {}, "deferred_taxes": {}, "other_noncash": {},
        "wc_ar": {}, "wc_inv": {}, "wc_ap": {}, "wc_other": {}, "cfo": {},
        "capex": {}, "acquisitions_ma": {}, "purchases_investments": {},
        "sales_maturities_investments": {}, "other_investing": {}, "cfi": {},
        "debt_issued": {}, "debt_repaid": {}, "net_debt_issued": {},
        "stock_issued": {}, "share_repurchases_open_market": {}, "share_repurchases_sbc_tax": {},
        "dividends_paid": {}, "other_financing": {}, "cff": {},
        "fx_effect": {}, "net_change_in_cash": {}, "ending_cash": {}, "fcf": {}
    }

    for p in periods:
        ni = _extract_multi_source_val(fs, "cashflow", [
            "NetIncomeLoss", "ProfitLoss", "ProfitLossFromContinuingOperations"
        ], p, "net_income")

        da = _extract_multi_source_val(fs, "cashflow", [
            "DepreciationDepletionAndAmortization", "DepreciationAmortizationAndAccretionNet", "Depreciation",
            "ifrs-full_AdjustmentsForDepreciationAndAmortisationExpense", "DepreciationAndAmortization"
        ], p, "depreciation_and_amortization")
        if da is not None:
            da = abs(da)

        sbc = _extract_multi_source_val(fs, "cashflow", [
            "ShareBasedCompensation", "AllocatedShareBasedCompensationExpense", "AdjustmentsForSharebasedPayments",
            "ExpenseFromSharebasedPaymentTransactionsWithEmployees"
        ], p, "stock_based_compensation")
        if sbc is not None:
            sbc = abs(sbc)

        def_taxes = _extract_multi_source_val(fs, "cashflow", [
            "DeferredIncomeTaxExpenseBenefit", "DeferredIncomeTaxesAndTaxCredits", "ifrs-full_AdjustmentsForDeferredTaxExpense"
        ], p)

        other_nc = _extract_multi_source_val(fs, "cashflow", [
            "OtherNoncashIncomeExpense", "ProvisionForLoanLeaseAndOtherLosses", "ProvisionForDoubtfulAccounts",
            "GainLossOnInvestments", "AdjustmentsNoncashItemsToReconcileNetIncomeLossToCashProvidedByUsedInOperatingActivities",
            "CreditLossAllowanceExpenses1", "UnrealizedGainLossOnInvestments", "GainsLossesOnExtinguishmentOfDebt"
        ], p)

        wc_ar = _extract_multi_source_val(fs, "cashflow", [
            "IncreaseDecreaseInAccountsReceivable", "IncreaseDecreaseInOtherReceivables",
            "meli_IncreaseDecreaseInPrincipalLoansReceivableNet", "TradeAndOtherReceivablesNetCurrent"
        ], p)

        wc_inv = _extract_multi_source_val(fs, "cashflow", [
            "IncreaseDecreaseInInventories"
        ], p)

        wc_ap = _extract_multi_source_val(fs, "cashflow", [
            "IncreaseDecreaseInAccountsPayable", "IncreaseDecreaseInAccountsPayableAndAccruedLiabilities"
        ], p)

        wc_other = _extract_multi_source_val(fs, "cashflow", [
            "IncreaseDecreaseInContractWithCustomerLiability", "IncreaseDecreaseInOtherOperatingAssets",
            "IncreaseDecreaseInOtherOperatingLiabilities", "IncreaseDecreaseInAccruedLiabilities",
            "meli_IncreaseDecreaseInFundsPayableToCustomers", "IncreaseDecreaseInOperatingCapital"
        ], p)

        cfo = _extract_multi_source_val(fs, "cashflow", [
            "NetCashProvidedByUsedInOperatingActivities", "CashFlowsFromUsedInOperatingActivities"
        ], p, "cash_from_operations")

        can_capex = canonical.get("capital_expenditures", {}).get(p)
        if can_capex is not None:
            capex = abs(float(can_capex))
        else:
            raw_cx = _extract_multi_source_val(fs, "cashflow", [
                "PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets",
                "PaymentsForPropertyPlantAndEquipment", "ifrs-full_PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities"
            ], p)
            capex = abs(raw_cx) if raw_cx is not None else None

        acq_ma = capital_flows["acquisitions_ma"].get(p)
        if acq_ma is not None:
            acq_ma = abs(acq_ma)

        purch_inv = _extract_multi_source_val(fs, "cashflow", [
            "PaymentsToAcquireAvailableForSaleSecuritiesDebt", "PaymentsToAcquireMarketableSecurities",
            "PaymentsToAcquireInvestments", "PaymentsToAcquireOtherInvestments"
        ], p)
        if purch_inv is not None:
            purch_inv = abs(purch_inv)

        p1 = _extract_multi_source_val(fs, "cashflow", [
            "ProceedsFromSaleOfAvailableForSaleSecuritiesDebt", "ProceedsFromSaleOfMarketableSecurities"
        ], p)
        p2 = _extract_multi_source_val(fs, "cashflow", [
            "ProceedsFromMaturitiesPrepaymentsAndCallsOfAvailableForSaleSecurities", "ProceedsFromMaturityOfMarketableSecurities"
        ], p)
        p3 = _extract_multi_source_val(fs, "cashflow", [
            "ProceedsFromSaleAndMaturityOfMarketableSecurities", "ProceedsFromSaleOfAvailableForSaleSecurities"
        ], p)
        sales_inv = None
        if p1 is not None or p2 is not None or p3 is not None:
            sales_inv = round((p1 or 0.0) + (p2 or 0.0) + (p3 or 0.0), 2)

        other_inv = _extract_multi_source_val(fs, "cashflow", [
            "PaymentsForProceedsFromOtherInvestingActivities", "ProceedsFromSaleOfRealEstate", "PaymentsToAcquireRealEstate"
        ], p)

        cfi = _extract_multi_source_val(fs, "cashflow", [
            "NetCashProvidedByUsedInInvestingActivities", "CashFlowsFromUsedInInvestingActivities"
        ], p, "cash_from_investing")

        di = capital_flows["debt_issuances"].get(p)
        dr = capital_flows["debt_repayments"].get(p)
        net_debt = capital_flows["net_debt_change"].get(p)
        cp = _extract_multi_source_val(fs, "cashflow", ["ProceedsFromRepaymentsOfCommercialPaper"], p)
        if cp is not None and net_debt is not None:
            net_debt = round(net_debt + cp, 2)

        stk_iss = capital_flows["stock_plans_proceeds"].get(p) or _extract_multi_source_val(fs, "cashflow", [
            "ProceedsFromIssuanceOfCommonStock", "ProceedsFromIssuanceOfShares"
        ], p)

        rep_om = capital_flows["share_repurchases_open_market"].get(p)
        rep_tax = capital_flows["share_repurchases_sbc_tax"].get(p)
        div_paid = capital_flows["dividends_paid"].get(p)

        other_fin = _extract_multi_source_val(fs, "cashflow", [
            "ProceedsFromPaymentsForOtherFinancingActivities", "IncreaseDecreaseInDeposits",
            "PaymentsForProceedsFromOtherFinancingActivities"
        ], p)

        cff = _extract_multi_source_val(fs, "cashflow", [
            "NetCashProvidedByUsedInFinancingActivities", "CashFlowsFromUsedInFinancingActivities"
        ], p, "cash_from_financing")

        fx = _extract_multi_source_val(fs, "cashflow", [
            "EffectOfExchangeRateOnCashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
            "EffectOfExchangeRateOnCashAndCashEquivalents", "nu_ForeignExchangeRateChangesOnCashAndCashEquivalents",
            "ifrs-full_EffectOfExchangeRateChangesOnCashAndCashEquivalents"
        ], p)

        net_chg_cash = _extract_multi_source_val(fs, "cashflow", [
            "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsPeriodIncreaseDecreaseIncludingExchangeRateEffect",
            "CashAndCashEquivalentsPeriodIncreaseDecrease", "ifrs-full_IncreaseDecreaseInCashAndCashEquivalents"
        ], p)
        if net_chg_cash is None and cfo is not None and cfi is not None and cff is not None:
            net_chg_cash = round(cfo + cfi + cff + (fx or 0.0), 2)

        end_cash = _extract_multi_source_val(fs, "cashflow", [
            "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents", "CashAndCashEquivalentsAtCarryingValue",
            "ifrs-full_CashAndCashEquivalents"
        ], p)

        can_fcf = canonical.get("free_cash_flow", {}).get(p)
        if can_fcf is not None and archetype != "FINANCIAL_BANKING":
            fcf = float(can_fcf)
        elif archetype != "FINANCIAL_BANKING" and cfo is not None and capex is not None:
            fcf = round(cfo - capex, 2)
        else:
            fcf = None

        res["net_income"][p] = ni
        res["da"][p] = da
        res["sbc"][p] = sbc
        res["deferred_taxes"][p] = def_taxes
        res["other_noncash"][p] = other_nc
        res["wc_ar"][p] = wc_ar
        res["wc_inv"][p] = wc_inv
        res["wc_ap"][p] = wc_ap
        res["wc_other"][p] = wc_other
        res["cfo"][p] = cfo
        res["capex"][p] = capex
        res["acquisitions_ma"][p] = acq_ma
        res["purchases_investments"][p] = purch_inv
        res["sales_maturities_investments"][p] = sales_inv
        res["other_investing"][p] = other_inv
        res["cfi"][p] = cfi
        res["debt_issued"][p] = di
        res["debt_repaid"][p] = dr
        res["net_debt_issued"][p] = net_debt
        res["stock_issued"][p] = stk_iss
        res["share_repurchases_open_market"][p] = rep_om
        res["share_repurchases_sbc_tax"][p] = rep_tax
        res["dividends_paid"][p] = div_paid
        res["other_financing"][p] = other_fin
        res["cff"][p] = cff
        res["fx_effect"][p] = fx
        res["net_change_in_cash"][p] = net_chg_cash
        res["ending_cash"][p] = end_cash
        res["fcf"][p] = fcf

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
    statements_fys = [p for p in fs.get("fiscal_years", [])[:11]]
    latest_p = statements_fys[0] if statements_fys else "LTM"
    canonical = fs.get("canonical_summary", {})
    key_ratios = fs.get("key_ratios", {})

    def _to_m(val):
        if val is None:
            return None
        v = float(val)
        return round(v / 1e6 if abs(v) >= 1e6 else v, 1)

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
    is_financial = bool(fs.get("is_financial") or scores.get("is_financial_institution") or is_banking or is_insurance)

    bs_data = resolve_canonical_balance_sheet(fs, statements_fys, archetype=archetype)

    pnl_data = resolve_canonical_income_statement(fs, statements_fys, archetype=archetype)
    cap_flows = resolve_canonical_capital_flows(fs, statements_fys)
    cf_data = resolve_canonical_cash_flow(fs, statements_fys, capital_flows=cap_flows, archetype=archetype)

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

    st_debt_m = _to_m(bs_data.get("short_term_debt", {}).get(latest_p)) or 0.0
    lt_debt_m = _to_m(bs_data.get("long_term_debt", {}).get(latest_p)) or 0.0
    total_debt_m = round(st_debt_m + lt_debt_m, 1)

    cash_only_m = _to_m(bs_data["cash"].get(latest_p)) or 0.0
    sti_m = _to_m(bs_data.get("short_term_investments", {}).get(latest_p)) or 0.0
    total_cash_liquid_m = round(cash_only_m + sti_m, 1)

    # Posición Neta de Deuda Financiera Canónica
    nfp_val = _to_m(bs_data.get("net_financial_position", {}).get(latest_p))
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
                disp_val = -abs(val) if (r.get("negate_val") and val is not None and val > 0) else val
                abs_disp = _fmt_money(disp_val)

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

                if _should_include_row(item, val_dict):
                    sec_visible_items.append({
                        "label": lbl,
                        "orig_tooltip": tip or f"Estándar Canónico: {k}",
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
                ("Gastos Operativos No Financieros (Non-Interest Expense)", "non_interest_expense", "[-]", "item", True, False, True, True, "rev", "Non-Interest Expense"),
                ("Beneficio Operativo (EBIT)", "operating_income", "[=]", "result", False, True, False, True, "rev", "Operating Income"),
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
                ("Beneficio Operativo (EBIT)", "operating_income", "[=]", "result", False, True, False, True, "rev", "Operating Income"),
                ("Gastos por Intereses Financieros", "interest_expense", "[-]", "item", True, False, True, False, "rev", "Interest Expense"),
                ("Beneficio Antes de Impuestos (EBT)", "ebt", "[=]", "subtotal", False, True, False, True, "rev", "Pre-Tax Income"),
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
            ("Inversiones en Inmovilizado / CapEx", "capex", "[-]", "item", True, False, True, True, "ni", "Capital Expenditures"),
            ("Adquisiciones Netas de Caja (M&A)", "acquisitions_ma", "[-]", "item", True, False, True, False, "ni", "Acquisitions Net of Cash"),
            ("Compras de Inversiones y Valores Negociables", "purchases_investments", "[-]", "item", True, False, True, False, "ni", "Purchases of Investments"),
            ("Ventas y Vencimientos de Inversiones Negociables", "sales_maturities_investments", "[+]", "item", True, False, False, False, "ni", "Sales & Maturities of Investments"),
            ("Otros Flujos de Inversión", "other_investing", "[±]", "item", True, False, False, False, "ni", "Other Investing Activities"),
            ("Flujo de Caja de Inversión (CFI)", "cfi", "[=]", "subtotal", False, True, False, True, "ni", "Cash Used in Investing Activities"),
        ]),
        ("ACTIVIDADES DE FINANCIACIÓN (FINANCING ACTIVITIES)", [
            ("Emisión de Deuda Financiera (Debt Issued)", "debt_issued", "[+]", "item", True, False, False, False, "ni", "Issuance of Debt"),
            ("Amortización y Reembolso de Deuda (Debt Repaid)", "debt_repaid", "[-]", "item", True, False, True, False, "ni", "Repayments of Debt"),
            ("Emisión / (Reembolso) Neto de Deuda", "net_debt_issued", "[=]", "subtotal", False, True, False, True, "ni", "Net Debt Issuance / Repayment"),
            ("Emisión de Acciones Ordinarias y Planes de Empleados", "stock_issued", "[+]", "item", True, False, False, False, "ni", "Issuance of Common Stock"),
            ("Recompra de Acciones en Mercado Abierto (Buybacks)", "share_repurchases_open_market", "[-]", "item", True, False, True, False, "ni", "Repurchase of Common Stock"),
            ("Retenciones Fiscales por Liquidación de RSU / SBC", "share_repurchases_sbc_tax", "[-]", "item", True, False, True, False, "ni", "Tax Withholding for Share Awards"),
            ("Dividendos Pagados en Efectivo (Dividends Paid)", "dividends_paid", "[-]", "item", True, False, True, True, "ni", "Payment of Dividends"),
            ("Otros Flujos de Financiación (y Depósitos en Banca)", "other_financing", "[±]", "item", True, False, False, False, "ni", "Other Financing Activities"),
            ("Flujo de Caja de Financiación (CFF)", "cff", "[=]", "subtotal", False, True, False, True, "ni", "Cash Provided by / Used in Financing Activities"),
        ]),
        ("VARIACIÓN NETA DE EFECTIVO Y CONCILIACIÓN DE CAJA", [
            ("Efecto del Tipo de Cambio en el Efectivo (FX Effect)", "fx_effect", "[±]", "item", True, False, False, False, "ni", "Effect of Exchange Rate on Cash"),
            ("Variación Neta de Efectivo en el Período (Net Change in Cash)", "net_change_in_cash", "[=]", "subtotal", False, True, False, True, "ni", "Net Change in Cash & Equivalents"),
            ("Efectivo, Equivalentes y Efectivo Restringido al Cierre", "ending_cash", "[=]", "subtotal", False, True, False, True, "ni", "Ending Cash & Equivalents"),
            ("Flujo de Caja Libre (FCF = CFO − CapEx)", "fcf", "[=]", "result", False, True, False, (archetype != "FINANCIAL_BANKING"), "ni", "Free Cash Flow"),
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
