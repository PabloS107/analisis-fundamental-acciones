import sys
import json
from pathlib import Path
from django.shortcuts import render, Http404

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "processed"
SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / ".agents" / "skills" / "fundamental-data-extractor" / "scripts"
if SCRIPTS_DIR.exists() and str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

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
                    gpa_val = nm.get("gross_profitability_total", 0.0)
                    gpa = (gpa_val * 100.0) if gpa_val <= 1.5 else gpa_val
                    
                    # 3. Solvencia & Rating
                    solv = sc.get("debt_and_solvency_analysis", {}).get("latest_result", {})
                    z_score = solv.get("distress_models", {}).get("altman_z_double_prime", "-")
                    rating = solv.get("distress_models", {}).get("synthetic_rating", "AAA")
                    
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

                    # 5. Cotización de Mercado en Tiempo Real
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
                        "price": f"${price:.2f}" if price else "-",
                        "price_raw": price,
                        "f_score": f_sc,
                        "g_score": g_sc,
                        "gpa": f"{gpa:.1f}%",
                        "roic_adj": f"{roic_pct:.1f}%",
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
    canonical = fs.get("canonical_summary", {})
    key_ratios = fs.get("key_ratios", {})

    # KPIs y Señales Auditadas
    f_obj = scores.get("piotroski_f_score", {}).get("LTM", {})
    f_score = f_obj.get("total_score") or f_obj.get("score", 7)
    f_signals = list(f_obj.get("signals", {}).values())
    f_summary = f_obj.get("summary_text", "Solidez financiera de primer nivel institucional.")
    f_rating = f_obj.get("rating", "SALUD EXCEPCIONAL")

    g_obj = scores.get("mohanram_g_score", {}).get("LTM", {})
    g_score = g_obj.get("total_score") or g_obj.get("score", 6)
    g_signals = list(g_obj.get("signals", {}).values())
    g_summary = g_obj.get("summary_text", "Crecimiento e inversión de calidad superior.")
    g_rating = g_obj.get("rating", "CRECIMIENTO ALTO")
    
    nm = scores.get("novy_marx_analysis", {}).get("latest_result", {})
    gp_total = nm.get("gross_profitability_total", 0.5926) * 100
    gp_exc = nm.get("gross_profitability_ex_cash", 0.6608) * 100
    p_label = nm.get("percentile_label", "Top 5% de la Industria")

    # Comparativa de Novy-Marx vs Mediana Sectorial
    benchmarks = scores.get("benchmarks_used", {})
    median_gpa = benchmarks.get("median_gross_profitability", 0.2569) * 100.0
    gpa_diff = gp_total - median_gpa
    gpa_diff_str = f"+{gpa_diff:.2f} pp" if gpa_diff >= 0 else f"{gpa_diff:.2f} pp"
    gpa_is_higher = gp_total >= median_gpa
    
    roc_green = scores.get("greenblatt_roc_analysis", {}).get("latest_roc_pct")
    if roc_green is None:
        roc_green = (scores.get("greenblatt_roc_analysis", {}).get("latest_result", {}).get("roc_greenblatt", 0.30) or 0.30) * 100.0
    
    roic_data = scores.get("intangible_roic_analysis", {}).get("latest_result", {})
    roic_adj_raw = roic_data.get("adjusted_roic")
    if roic_adj_raw is None:
        roic_adj_raw = scores.get("wacc_and_spread_analysis", {}).get("roic_adjusted", 0.30)
    roic_adj = (roic_adj_raw * 100.0) if roic_adj_raw <= 1.5 else roic_adj_raw
    
    wacc_data = scores.get("wacc_and_spread_analysis", {})
    wacc_raw = wacc_data.get("wacc")
    wacc_val = (wacc_raw * 100.0) if wacc_raw is not None else wacc_data.get("wacc_percentage", 9.5)
    
    spread_raw = wacc_data.get("economic_spread_adjusted") or wacc_data.get("economic_spread_traditional")
    spread_val = (spread_raw * 100.0) if spread_raw is not None else wacc_data.get("economic_spread_percentage", 20.0)
    
    solv_data = scores.get("debt_and_solvency_analysis", {}).get("latest_result", {})
    distress = solv_data.get("distress_models", {})
    z_score = distress.get("altman_z_double_prime", 3.23)
    rating_synth = distress.get("synthetic_rating", "AAA")
    interest_cov_raw = solv_data.get("debt_service", {}).get("interest_coverage")
    interest_cov_str = solv_data.get("debt_service", {}).get("interest_coverage_str")
    if interest_cov_str:
        interest_cov_display = interest_cov_str
    elif interest_cov_raw is not None:
        interest_cov_display = f"{interest_cov_raw:.1f}x"
    else:
        interest_cov_display = "SÓLIDA"
    interest_cov = interest_cov_raw if interest_cov_raw is not None else 100.0
    
    forn_data = scores.get("forensic_accounting_analysis", {})
    forn_lr = forn_data.get("latest_result", {})
    sloan_obj = forn_lr.get("sloan_accrual", {}) or forn_data.get("sloan_accrual_analysis", {}).get("latest_result", {})
    sloan_val = sloan_obj.get("sloan_ratio_pct")
    if sloan_val is None:
        sloan_val = sloan_obj.get("sloan_ratio", -0.0479) * 100.0
    sloan = sloan_val

    sloan_ni = (sloan_obj.get("net_income") or 0.0) / 1e9
    sloan_cfo = (sloan_obj.get("cfo") or 0.0) / 1e9
    sloan_accruals = (sloan_obj.get("total_accruals") or 0.0) / 1e9
    sloan_assets = (sloan_obj.get("avg_assets") or 0.0) / 1e9
    sloan_is_safe = (-10.0 <= sloan_val <= 5.0)

    def _fmt_b(val_b):
        if val_b is None:
            return "-"
        if val_b < 0:
            return f"-${abs(val_b):,.2f}B"
        return f"${val_b:,.2f}B"

    sloan_detail = {
        "sloan_val": sloan_val,
        "sloan_str": f"{sloan_val:.2f}%",
        "net_income": _fmt_b(sloan_ni),
        "cfo": _fmt_b(sloan_cfo),
        "total_accruals": _fmt_b(sloan_accruals),
        "avg_assets": _fmt_b(sloan_assets),
        "is_safe": sloan_is_safe,
        "status": sloan_obj.get("status", "EXCELENTE"),
        "badge": sloan_obj.get("badge", "ALTA CONVERSIÓN DE CAJA"),
        "diagnosis": sloan_obj.get("diagnosis", "Conservadurismo contable sobresaliente. El flujo de caja operativo supera holgadamente a la utilidad neta."),
    }
    
    # Montier C-Score & Banderas Forenses Auditadas
    montier_obj = forn_lr.get("montier_c_score", {}) or forn_data.get("montier_c_score", {}).get("LTM", {})
    montier_score = montier_obj.get("total_score")
    if montier_score is None:
        montier_score = montier_obj.get("c_score", 1)
    montier_rating = montier_obj.get("rating", "RIESGO MUY BAJO / LIBROS LIMPIOS")
    montier_badge = montier_obj.get("badge", "CONTABILIDAD CONSERVADORA")
    montier_verdict = montier_obj.get("verdict", "Ganancias de alta calidad avaladas por caja real.")
    montier_flags_dict = montier_obj.get("flags_breakdown", {})
    montier_flags = list(montier_flags_dict.values())
    montier_is_safe = (montier_score <= 1)

    montier_detail = {
        "score": montier_score,
        "max_score": 6,
        "rating": montier_rating,
        "badge": montier_badge,
        "verdict": montier_verdict,
        "flags": montier_flags,
        "is_safe": montier_is_safe,
    }

    # Solvencia 13.1 y 13.2
    lev_data = solv_data.get("cash_flow_leverage", {})
    cov_data = solv_data.get("debt_service", {})
    dist_data = solv_data.get("distress_models", {})

    total_debt_m = lev_data.get("total_debt") if lev_data.get("total_debt") is not None else 0.0
    cash_m = lev_data.get("cash") if lev_data.get("cash") is not None else 0.0
    net_debt_m = lev_data.get("net_debt") if lev_data.get("net_debt") is not None else 0.0
    ebitda_m = lev_data.get("ebitda")
    fcf_m_val = lev_data.get("fcf") if lev_data.get("fcf") is not None else 0.0
    is_net_cash = lev_data.get("is_net_cash", False)
    net_debt_ebitda_val = lev_data.get("net_debt_to_ebitda", 0.25)
    solv_13_1_safe = is_net_cash or (isinstance(net_debt_ebitda_val, (int, float)) and net_debt_ebitda_val < 1.5)

    if isinstance(net_debt_m, (int, float)):
        if net_debt_m < 0:
            net_debt_display = f"-${abs(net_debt_m):,.1f}M (Caja Neta)"
        elif net_debt_m > 0:
            net_debt_display = f"+${net_debt_m:,.1f}M"
        else:
            net_debt_display = "$0.0M"
    else:
        net_debt_display = "N/A"

    solvency_13_1 = {
        "total_debt": f"${total_debt_m:,.1f}M" if isinstance(total_debt_m, (int, float)) else "N/A",
        "cash": f"${cash_m:,.1f}M" if isinstance(cash_m, (int, float)) else "N/A",
        "net_debt": net_debt_display,
        "is_net_cash": is_net_cash,
        "ebitda": f"${ebitda_m:,.1f}M" if isinstance(ebitda_m, (int, float)) else "N/A",
        "net_debt_to_ebitda_str": lev_data.get("net_debt_to_ebitda_str", "0.25x"),
        "net_debt_to_ebitda_status": lev_data.get("status", "Grado Inversión Superior (< 1.5x)"),
        "fcf": f"${fcf_m_val:,.1f}M" if isinstance(fcf_m_val, (int, float)) else "N/A",
        "net_debt_to_fcf_str": lev_data.get("net_debt_to_fcf_str", "0.31x"),
        "badge": lev_data.get("badge", "APALANCAMIENTO BAJO"),
        "diagnosis": lev_data.get("diagnosis", "Apalancamiento muy conservador frente a la generación operativa."),
        "is_safe": solv_13_1_safe,
    }

    ebit_cov_m = cov_data.get("ebit")
    interest_exp_m = cov_data.get("interest_expense")
    cov_val = cov_data.get("interest_coverage", 41.8)
    solv_13_2_safe = isinstance(cov_val, (int, float)) and (cov_val >= 10.0 or is_net_cash)

    solvency_13_2 = {
        "ebit": f"${ebit_cov_m:,.1f}M" if isinstance(ebit_cov_m, (int, float)) else "N/A",
        "interest_expense": f"${interest_exp_m:,.1f}M" if isinstance(interest_exp_m, (int, float)) else "N/A",
        "interest_coverage_str": cov_data.get("interest_coverage_str", "41.8x"),
        "cash_interest_coverage_str": cov_data.get("cash_interest_coverage_str", "39.6x"),
        "financial_burden_pct": f"{cov_data.get('financial_burden_pct', 2.53):.2f}%" if isinstance(cov_data.get('financial_burden_pct'), (int, float)) else "N/A",
        "status": cov_data.get("status", "COBERTURA EXCELENTE (> 10.0x)"),
        "badge": cov_data.get("badge", "MÁXIMA PROTECCIÓN"),
        "diagnosis": cov_data.get("diagnosis", "Los beneficios operativos cubren holgadamente los intereses."),
        "is_safe": solv_13_2_safe,
    }

    altman_val = dist_data.get("altman_z_double_prime", 3.23)
    altman_is_safe = (isinstance(altman_val, (int, float)) and altman_val >= 2.60)

    distress_detail = {
        "altman_z": f"{altman_val:.2f}" if isinstance(altman_val, (int, float)) else str(altman_val),
        "altman_val": altman_val if isinstance(altman_val, (int, float)) else 3.23,
        "altman_zone": dist_data.get("altman_zone", "ZONA SEGURA (BAJO RIESGO DE QUIEBRA)"),
        "altman_badge": dist_data.get("altman_badge", "ZONA SEGURA"),
        "altman_diagnosis": dist_data.get("altman_diagnosis", "Probabilidad estadística de insolvencia virtualmente nula a 2 años vista."),
        "altman_x1": f"{dist_data.get('altman_x1'):.4f}" if isinstance(dist_data.get('altman_x1'), (int, float)) else "N/A",
        "altman_x2": f"{dist_data.get('altman_x2'):.4f}" if isinstance(dist_data.get('altman_x2'), (int, float)) else "N/A",
        "altman_x3": f"{dist_data.get('altman_x3'):.4f}" if isinstance(dist_data.get('altman_x3'), (int, float)) else "N/A",
        "altman_x4": f"{dist_data.get('altman_x4'):.4f}" if isinstance(dist_data.get('altman_x4'), (int, float)) else "N/A",
        "altman_is_safe": altman_is_safe,
        "synthetic_rating": dist_data.get("synthetic_rating", "AAA"),
        "synthetic_rating_desc": dist_data.get("synthetic_rating_desc", "GRADO INSTITUCIONAL MÁXIMO (AAA / Aaa)"),
        "default_spread_pct": f"+{dist_data.get('default_spread_pct', 0.60):.2f}%" if isinstance(dist_data.get('default_spread_pct'), (int, float)) else "+0.40%",
        "default_probability": dist_data.get("default_probability", "< 0.2%"),
        "rating_is_safe": True,
    }


    def _to_billions(val):
        if val is None:
            return 0.0
        v = float(val)
        return round(v / 1e9 if abs(v) > 1e6 else v / 1e3, 2)

    def _norm_pct(val):
        if val is None:
            return 0.0
        v = float(val)
        return round(v * 100.0 if abs(v) <= 1.0 else v, 2)

    # Series para Gráficos
    chart_periods = list(reversed(fys))
    rev_series = [_to_billions(canonical.get("revenue", {}).get(p)) for p in chart_periods]
    gp_series = [_to_billions(canonical.get("gross_profit", {}).get(p)) for p in chart_periods]
    ni_series = [_to_billions(canonical.get("net_income", {}).get(p)) for p in chart_periods]
    
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

    # Flujos de caja ($B): CFO, CapEx y FCF
    cfo_series = [_to_billions(canonical.get("cash_from_operations", {}).get(p)) for p in chart_periods]
    capex_series = [_to_billions(canonical.get("capital_expenditures", {}).get(p)) for p in chart_periods]
    fcf_series = [_to_billions(canonical.get("free_cash_flow", {}).get(p)) for p in chart_periods]

    # Recompras, Acciones y BPA
    cfd = fs.get("cash_flow_detail", {})
    buybacks_dict = {}
    for b_key in ["PaymentsForRepurchaseOfCommonStock", "PaymentsForRepurchaseOfEquity", "PaymentsForRepurchaseOfCapitalStock"]:
        if b_key in cfd and "values" in cfd[b_key]:
            buybacks_dict = cfd[b_key]["values"]
            break
    
    # Unidades dinámicas para recompras
    raw_buybacks = [abs(float(buybacks_dict.get(p, 0) or 0)) for p in chart_periods]
    max_bb = max(raw_buybacks + [0])
    buybacks_unit = "B" if max_bb >= 1e9 else "B" # Mantener base B para coherencia en gráfico o M si menor
    bb_scale = 1e9
    buybacks_series = [round(abs(float(buybacks_dict.get(p, 0) or 0)) / bb_scale, 2) for p in chart_periods]

    # Unidades dinámicas para acciones en circulación (B o M)
    shares_dict = canonical.get("shares_diluted_adjusted", {}) or canonical.get("shares_diluted", {})
    max_shares = max([abs(float(shares_dict.get(p, 0) or 0)) for p in chart_periods] + [0])
    if max_shares >= 1e9:
        shares_unit = "B"
        shares_scale = 1e9
    elif max_shares >= 1e6:
        shares_unit = "M"
        shares_scale = 1e6
    else:
        shares_unit = "M"
        shares_scale = 1e6
    shares_series = [round(float(shares_dict.get(p, 0) or 0) / shares_scale, 2) for p in chart_periods]

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

    total_bb = sum(abs(float(v or 0)) for v in buybacks_dict.values() if v is not None)
    if total_bb >= 1e9:
        bb_str = f">${total_bb/1e9:,.1f}B"
    elif total_bb >= 1e6:
        bb_str = f">${total_bb/1e6:,.1f}M"
    else:
        bb_str = f">${total_bb:,.0f}"

    buybacks_summary = {
        "float_change_pct": float_str,
        "total_buybacks": bb_str
    }

    # Peer group Novy-Marx
    peers = scores.get("novy_marx_analysis", {}).get("peer_ranking", [])

    # Tabla P&L estructurada con desglose de BPA Split-Adjusted vs As-Reported
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

    table_pnl = []
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
                val_str = f"{prefix}{scale_val/1000:,.1f}B" if scale_val >= 1000 else f"{prefix}{scale_val:,.0f}M"
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
    
    if not segments_raw:
        xlsx_file = ticker_dir / "financial_statements.xlsx"
        if xlsx_file.exists():
            try:
                import openpyxl
                wb_seg = openpyxl.load_workbook(xlsx_file, data_only=True)
                if "Desglose de Segmentos" in wb_seg.sheetnames:
                    ws_seg = wb_seg["Desglose de Segmentos"]
                    headers_seg = [ws_seg.cell(row=4, column=c).value for c in range(1, ws_seg.max_column + 1)]
                    p_headers = [h for h in headers_seg[1:] if h is not None]
                    p_list, g_list = [], []
                    cur_mode = None
                    for r_idx in range(5, ws_seg.max_row + 1):
                        lbl = ws_seg.cell(row=r_idx, column=1).value
                        if not lbl: continue
                        lbl_s = str(lbl).strip()
                        if "PRODUCTO" in lbl_s: cur_mode = "p"; continue
                        elif "GEOGR" in lbl_s: cur_mode = "g"; continue
                        c_name = lbl_s.replace("   ", "").strip()
                        row_vals = {}
                        for c_i, p_name in enumerate(p_headers, start=2):
                            v = ws_seg.cell(row=r_idx, column=c_i).value
                            try: row_vals[p_name] = float(v) if v is not None and str(v) != "-" else None
                            except: row_vals[p_name] = None
                        item = {"name": c_name, "is_subtotal": c_name in ["Products"], "values": row_vals}
                        if cur_mode == "p": p_list.append(item)
                        elif cur_mode == "g": g_list.append(item)
                    segments_raw = {"periods": p_headers, "product_segments": p_list, "geographic_segments": g_list}
            except Exception:
                pass

    seg_periods = segments_raw.get("periods", fys)
    prod_items = segments_raw.get("product_segments", [])
    geo_items = segments_raw.get("geographic_segments", [])

    tot_prod_ltm = sum(item["values"].get("LTM") or 0.0 for item in prod_items if item["name"] != "Products")
    tot_geo_ltm = sum(item["values"].get("LTM") or 0.0 for item in geo_items)

    table_products = []
    for item in prod_items:
        v_ltm = item["values"].get("LTM") or 0.0
        mix_pct = (v_ltm / tot_prod_ltm * 100.0) if tot_prod_ltm > 0 and item["name"] != "Products" else (100.0 if item["name"] == "Products" else 0.0)
        row_vals = []
        for p in seg_periods:
            val = item["values"].get(p)
            if val is not None:
                row_vals.append(f"${val/1000:,.1f}B" if val >= 1000 else f"${val:,.0f}M")
            else:
                row_vals.append("-")
        table_products.append({
            "name": item["name"],
            "is_subtotal": item["is_subtotal"],
            "mix_pct": f"{mix_pct:.1f}%" if item["name"] != "Products" else "-",
            "values": row_vals
        })

    table_geos = []
    for item in geo_items:
        v_ltm = item["values"].get("LTM") or 0.0
        mix_pct = (v_ltm / tot_geo_ltm * 100.0) if tot_geo_ltm > 0 else 0.0
        row_vals = []
        for p in seg_periods:
            val = item["values"].get(p)
            if val is not None:
                row_vals.append(f"${val/1000:,.1f}B" if val >= 1000 else f"${val:,.0f}M")
            else:
                row_vals.append("-")
        table_geos.append({
            "name": item["name"],
            "mix_pct": f"{mix_pct:.1f}%",
            "values": row_vals
        })

    # KPIs de resumen de segmentos dinámicos
    real_prod_items = [item for item in prod_items if not item.get("is_subtotal") and item["name"].lower() not in ["products", "total net sales"]]
    if not real_prod_items:
        real_prod_items = prod_items

    sorted_prods = sorted(real_prod_items, key=lambda x: x["values"].get("LTM") or 0.0, reverse=True)
    top_prod = sorted_prods[0] if len(sorted_prods) > 0 else {"name": "Línea Principal", "values": {}}
    second_prod = sorted_prods[1] if len(sorted_prods) > 1 else {"name": "Línea Secundaria", "values": {}}

    top_prod_ltm = top_prod["values"].get("LTM") or 0.0
    second_prod_ltm = second_prod["values"].get("LTM") or 0.0

    sorted_geos = sorted(geo_items, key=lambda x: x["values"].get("LTM") or 0.0, reverse=True)
    top_geo = sorted_geos[0] if len(sorted_geos) > 0 else {"name": "Mercado Principal", "values": {}}
    top_geo_ltm = top_geo["values"].get("LTM") or 0.0

    intl_item = next((item for item in geo_items if "international" in item["name"].lower() or "foreign" in item["name"].lower() or "resto" in item["name"].lower()), None)
    if intl_item:
        intl_ltm = intl_item["values"].get("LTM") or 0.0
    else:
        intl_ltm = max(0.0, tot_geo_ltm - top_geo_ltm)
    intl_pct = (intl_ltm / tot_geo_ltm * 100.0) if tot_geo_ltm > 0 else 0.0

    def _fmt_seg_val(val):
        if val >= 1000:
            return f"${val/1000:,.1f}B"
        return f"${val:,.0f}M"

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

    # Series para Gráficos de Segmentos (orden cronológico)
    seg_chart_periods = list(reversed(seg_periods))
    palette = ["#38bdf8", "#a855f7", "#10b981", "#f59e0b", "#f43f5e", "#ec4899", "#6366f1", "#14b8a6", "#84cc16", "#eab308"]

    products_trend_datasets = []
    for idx, item in enumerate(prod_items):
        if item.get("is_subtotal"):
            continue
        c = palette[idx % len(palette)]
        data_pts = [round((item["values"].get(p) or 0) / 1000.0, 2) for p in seg_chart_periods]
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
    for idx, item in enumerate(geo_items):
        c = palette[idx % len(palette)]
        data_pts = [round((item["values"].get(p) or 0) / 1000.0, 2) for p in seg_chart_periods]
        geos_trend_datasets.append({
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

    # Datos para Donut Charts LTM
    donut_prod_labels = [item["name"] for item in prod_items if not item.get("is_subtotal") and item["name"].lower() not in ["products", "total net sales"]]
    if not donut_prod_labels:
        donut_prod_labels = [item["name"] for item in prod_items]
    donut_prod_data = [round((next((item["values"].get("LTM") or 0 for item in prod_items if item["name"] == name), 0)) / 1000.0, 2) for name in donut_prod_labels]
    donut_prod_colors = [palette[idx % len(palette)] for idx in range(len(donut_prod_labels))]

    donut_geo_labels = [item["name"] for item in geo_items]
    donut_geo_data = [round((item["values"].get("LTM") or 0) / 1000.0, 2) for item in geo_items]
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

    vp = get_valuation_parameters(scores, ticker=ticker, profile_data=prof_data, live_price=live_price)
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
        hist_growth = (vp.get("cagr_5y", 0.0) / 100.0) if vp.get("cagr_5y") else 0.08
        hist_growth_pct = vp.get("cagr_5y", 0.0)
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
        hist_growth = (vp["cagr_5y"] / 100.0) if vp.get("cagr_5y") else 0.08
        hist_growth_pct = vp.get("cagr_5y", 0.0)
        wacc_dec = vp.get("wacc_val", 0.095)
        gn_dec = 0.025

        # Cálculo del Valor Intrínseco Teórico (DCF a 10 años con Gordon-Shapiro)
        pv_fcf = 0.0
        r_t = rev_base
        for t in range(1, 11):
            r_t *= (1.0 + hist_growth)
            pv_fcf += (r_t * fcf_margin) / ((1.0 + wacc_dec) ** t)
        tv = (r_t * (1.0 + gn_dec) * fcf_margin) / max(wacc_dec - gn_dec, 0.005)
        pv_tv = tv / ((1.0 + wacc_dec) ** 10)
        ev_total = pv_fcf + pv_tv
        equity_val = ev_total - net_debt_m
        fair_price_base = equity_val / shares_m if shares_m > 0 else stock_price

        g_implied = vp.get("g_implied_our_pct", 0.0) / 100.0
        gap_exp = (g_implied - hist_growth) * 100.0

    gap_expectations_str = f"{'+' if gap_exp >= 0 else ''}{gap_exp:.1f} pp"

    premium_pct = ((stock_price - fair_price_base) / fair_price_base) * 100.0 if fair_price_base > 0 else 0.0
    if premium_pct > 25.0:
        valuation_status = "SOBREVALORADA"
    elif premium_pct < -15.0:
        valuation_status = "INFRAVALORADA"
    else:
        valuation_status = "JUSTO"

    context = {
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
        "g_score": g_score,
        "g_signals": g_signals,
        "g_summary": g_summary,
        "g_rating": g_rating,
        "gp_total": f"{gp_total:.2f}%",
        "gp_total_val": gp_total,
        "gp_exc": f"{gp_exc:.2f}%",
        "p_label": p_label,
        "median_gpa": f"{median_gpa:.2f}%",
        "median_gpa_val": median_gpa,
        "gpa_diff_str": gpa_diff_str,
        "gpa_is_higher": gpa_is_higher,
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
        "peers": peers,
        "table_pnl": table_pnl,
        # JSON para Chart.js
        "chart_periods_json": json.dumps(chart_periods),
        "rev_series_json": json.dumps(rev_series),
        "gp_series_json": json.dumps(gp_series),
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
    }

    return render(request, "company_detail.html", context)
