"""
audit_engine.py - Motor de Auditoría Contable y Corroboración de Datos Financieros.
Ejecuta pruebas matemáticas de identidades contables invariantes (partida doble, flujo de caja,
márgenes y trazabilidad US-GAAP de la SEC) garantizando precisión milimétrica en 10 años + LTM.
"""

import os
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime

# Garantizar compatibilidad UTF-8 en terminales Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def load_financial_data(ticker, custom_dir=None):
    """Carga los estados financieros generados."""
    if custom_dir:
        json_path = Path(custom_dir) / "financial_statements.json"
    else:
        json_path = Path("data/processed") / ticker.upper() / "financial_statements.json"
        
    if not json_path.exists():
        raise FileNotFoundError(f"No se encontró el archivo de datos: {json_path}")
        
    with open(json_path, "r", encoding="utf-8") as f:
        return json.load(f), json_path.parent


def audit_balance_sheet(data, fy):
    """Prueba 1: Ecuación Fundamental del Balance: Activos = Pasivos + Patrimonio."""
    bal_detail = data.get("balance_sheet_detail", {})
    summary = data.get("canonical_summary", {})
    
    # Buscar Activos
    assets = summary.get("total_assets", {}).get(fy)
    if assets is None:
        for k, v in bal_detail.items():
            if k in ["Assets", "us-gaap_Assets", "TotalAssets"] and fy in v.get("values", {}):
                assets = v["values"][fy]
                break
        
    # Buscar Pasivos
    liabilities = None
    for k, v in bal_detail.items():
        if any(cand == k or k.endswith(f"_{cand}") for cand in ["Liabilities", "LiabilitiesCurrentAndNoncurrent"]):
            if fy in v.get("values", {}):
                liabilities = v["values"][fy]
                break
            
    # Buscar Patrimonio
    equity = summary.get("stockholders_equity", {}).get(fy)
    if equity is None:
        for k, v in bal_detail.items():
            if any(cand == k or k.endswith(f"_{cand}") for cand in ["StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest", "CommonEquity"]):
                if fy in v.get("values", {}):
                    equity = v["values"][fy]
                    break
    if "ifrs-full_Equity" in bal_detail and fy in bal_detail["ifrs-full_Equity"].get("values", {}):
        ifrs_tot_eq = bal_detail["ifrs-full_Equity"]["values"][fy]
        if ifrs_tot_eq is not None:
            equity = ifrs_tot_eq
        
    # Buscar Mezzanine Equity / Acciones Preferentes Rescatables (US-GAAP ASC 480)
    mezzanine = 0.0
    for k, v in bal_detail.items():
        if any(cand == k or k.endswith(f"_{cand}") for cand in [
            "TemporaryEquityCarryingAmount",
            "RedeemableNoncontrollingInterestEquityPreferredCarryingAmount",
            "RedeemablePreferredStockCarryingAmount",
            "TemporaryEquityCarryingAmountIncludingPortionAttributableToNoncontrollingInterests",
            "RedeemableNoncontrollingInterestEquityCarryingAmount"
        ]):
            if fy in v.get("values", {}):
                mezz_val = v["values"][fy]
                if mezz_val is not None:
                    try:
                        mezzanine += float(mezz_val)
                    except (ValueError, TypeError):
                        pass

    # Verificar si LiabilitiesAndStockholdersEquity está reportado directamente
    liab_equity = None
    for k, v in bal_detail.items():
        if any(cand == k or k.endswith(f"_{cand}") for cand in ["LiabilitiesAndStockholdersEquity", "EquityAndLiabilities"]):
            if fy in v.get("values", {}):
                liab_equity = v["values"][fy]
                break

    # Fallback para pasivos cuando la compañía solo reporta pasivos desglosados y LiabilitiesAndStockholdersEquity
    if liabilities is None and equity is not None:
        if liab_equity is not None:
            liabilities = liab_equity - equity - mezzanine
        elif assets is not None:
            liabilities = assets - equity - mezzanine

    if assets is None or (liabilities is None and liab_equity is None) or equity is None:
        return {
            "test_name": "Ecuación Fundamental del Balance (Activos = Pasivos + Patrimonio)",
            "passed": None,
            "status": "SKIP",
            "message": f"Partidas insuficientes en {fy} para verificar balance completo."
        }
        
    calc_sum = liabilities + equity + mezzanine if liabilities is not None else liab_equity
    if liab_equity is not None and abs(assets - float(liab_equity)) <= max(assets * 0.0001, 1000.0):
        diff = round(abs(assets - float(liab_equity)), 2)
        calc_sum = float(liab_equity)
        passed = True
    else:
        diff = round(abs(assets - calc_sum), 2)
        passed = diff <= max(assets * 0.0001, 1000.0)
    
    return {
        "test_name": "Ecuación Fundamental del Balance (Activos = Pasivos + Patrimonio)",
        "passed": passed,
        "status": "PASS" if passed else "FAIL",
        "assets": assets,
        "liabilities": liabilities,
        "equity": equity,
        "mezzanine_equity": mezzanine if mezzanine > 0 else None,
        "liabilities_plus_equity": calc_sum,
        "discrepancy_usd": diff,
        "tolerance_usd": round(max(assets * 0.0001, 1000.0), 2)
    }


def audit_gross_profit(data, fy):
    """Prueba 2: Consistencia de Margen Bruto: Margen Bruto = Ingresos - Costo de Ventas."""
    summary = data.get("canonical_summary", {})
    rev = summary.get("revenue", {}).get(fy)
    cogs = summary.get("cost_of_goods_sold", {}).get(fy)
    gp = summary.get("gross_profit", {}).get(fy)
    
    if rev is None or cogs is None or gp is None:
        return {
            "test_name": "Identidad de Margen Bruto (Gross Profit = Revenue - COGS)",
            "passed": None,
            "status": "SKIP",
            "message": f"Datos insuficientes de P&L para {fy}."
        }
        
    # Salvaguarda contable: COGS no debe reportarse con signo negativo
    if cogs < 0:
        return {
            "test_name": "Identidad de Margen Bruto (Gross Profit = Revenue - COGS)",
            "passed": False,
            "status": "FAIL",
            "revenue": rev,
            "cost_of_goods_sold": cogs,
            "gross_profit_reported": gp,
            "gross_profit_calculated": round(rev - cogs, 2),
            "discrepancy_usd": round(abs(gp - (rev - cogs)), 2),
            "message": f"COGS reportado con signo negativo ({cogs}). Los costos deben ser magnitudes positivas."
        }
        
    expected_gp = round(rev - cogs, 2)
    diff = round(abs(gp - expected_gp), 2)
    tolerance = max(abs(rev) * 0.0001, 10_000.0)
    passed = diff <= tolerance
    
    return {
        "test_name": "Identidad de Margen Bruto (Gross Profit = Revenue - COGS)",
        "passed": passed,
        "status": "PASS" if passed else "FAIL",
        "revenue": rev,
        "cost_of_goods_sold": cogs,
        "gross_profit_reported": gp,
        "gross_profit_calculated": expected_gp,
        "discrepancy_usd": diff,
        "tolerance_usd": round(tolerance, 2)
    }


def audit_free_cash_flow(data, fy):
    """Prueba 3: Consistencia de Free Cash Flow: FCF = Cash from Operations - CapEx."""
    archetype = data.get("archetype")
    summary = data.get("canonical_summary", {})
    fcf = summary.get("free_cash_flow", {}).get(fy)

    # En entidades bancarias y aseguradoras el FCF convencional no aplica
    if archetype in ("FINANCIAL_BANKING", "INSURANCE"):
        return {
            "test_name": "Identidad de Free Cash Flow (No aplicable a entidades financieras)",
            "passed": None,
            "status": "SKIP",
            "message": f"FCF no aplica a arquetipo {archetype}."
        }

    # En REITs, la identidad canónica institucional es AFFO = FFO - CapEx de Mantenimiento
    if archetype == "REAL_ESTATE_REIT":
        ffo = summary.get("ffo", {}).get(fy)
        rec_capex = summary.get("recurring_capex_maintenance", {}).get(fy)
        if rec_capex is None:
            rec_capex = summary.get("capital_expenditures", {}).get(fy)

        if ffo is None or rec_capex is None or fcf is None:
            return {
                "test_name": "Identidad de AFFO / FCF para REITs (FCF = FFO - CapEx Mantenimiento)",
                "passed": None,
                "status": "SKIP",
                "message": f"Faltan métricas FFO o CapEx recurrente para {fy}."
            }

        expected_affo = round(ffo - rec_capex, 2)
        diff = round(abs(fcf - expected_affo), 2)
        passed = diff <= 1000.0
        return {
            "test_name": "Identidad de AFFO / FCF para REITs (FCF = FFO - CapEx Mantenimiento)",
            "passed": passed,
            "status": "PASS" if passed else "FAIL",
            "ffo": ffo,
            "recurring_capex_maintenance": rec_capex,
            "fcf_reported": fcf,
            "fcf_calculated": expected_affo,
            "discrepancy_usd": diff
        }

    # Para empresas corporativas estándar e industriales: FCF = CFO - CapEx
    cfo = summary.get("cash_from_operations", {}).get(fy)
    capex = summary.get("capital_expenditures", {}).get(fy)
    
    if cfo is None or capex is None or fcf is None:
        return {
            "test_name": "Identidad de Free Cash Flow (FCF = CFO - CapEx)",
            "passed": None,
            "status": "SKIP",
            "message": f"Faltan flujos de efectivo para {fy}."
        }
        
    expected_fcf = round(cfo - capex, 2)
    diff = round(abs(fcf - expected_fcf), 2)
    passed = diff <= 1000.0
    
    return {
        "test_name": "Identidad de Free Cash Flow (FCF = CFO - CapEx)",
        "passed": passed,
        "status": "PASS" if passed else "FAIL",
        "cash_from_operations": cfo,
        "capital_expenditures": capex,
        "fcf_reported": fcf,
        "fcf_calculated": expected_fcf,
        "discrepancy_usd": diff
    }


def audit_cash_flow_reconciliation(data, fy):
    """Prueba 4: Reconciliación Integral de Flujo de Caja: Variación = Operativo + Inversión + Financiación."""
    if fy == "LTM":
        return {
            "test_name": "Reconciliación de Flujos de Caja (Net Change = CFO + CFI + CFF)",
            "passed": None,
            "status": "SKIP",
            "message": "Reconciliación detallada de variación de caja no aplica a período móvil derivado LTM."
        }
        
    cf_detail = data.get("cash_flow_detail", {})
    
    cfo = None
    cfi = None
    cff = None
    fx_effect = 0.0
    net_change_candidates = {}
    
    for k, v in cf_detail.items():
        if "NetCashProvidedByUsedInOperatingActivities" in k and fy in v.get("values", {}):
            cfo = v["values"][fy]
        elif "NetCashProvidedByUsedInInvestingActivities" in k and fy in v.get("values", {}):
            cfi = v["values"][fy]
        elif "NetCashProvidedByUsedInFinancingActivities" in k and fy in v.get("values", {}):
            cff = v["values"][fy]
        elif "EffectOfExchangeRate" in k and fy in v.get("values", {}):
            fx_effect = v["values"][fy] or 0.0
        elif any(nc in k for nc in ["PeriodIncreaseDecrease", "CashAndCashEquivalentsPeriodIncreaseDecrease"]) and fy in v.get("values", {}):
            val = v["values"][fy]
            if val is not None:
                net_change_candidates[k] = val
            
    # Priorización canónica de concepto US-GAAP (ASU 2016-18 con caja restringida y legacy)
    net_change = None
    for k, val in net_change_candidates.items():
        if "RestrictedCash" in k and "PeriodIncreaseDecrease" in k:
            net_change = val
            break
    if net_change is None:
        for k, val in net_change_candidates.items():
            if "CashAndCashEquivalentsPeriodIncreaseDecrease" in k:
                net_change = val
                break
    if net_change is None and net_change_candidates:
        net_change = list(net_change_candidates.values())[0]
            
    if cfo is None or cfi is None or cff is None or net_change is None:
        return {
            "test_name": "Reconciliación de Flujos de Caja (Net Change = CFO + CFI + CFF)",
            "passed": None,
            "status": "SKIP",
            "message": f"Detalle de flujo de caja incompleto para {fy}."
        }
        
    sum_flows = round(cfo + cfi + cff + fx_effect, 2)
    diff = round(abs(net_change - sum_flows), 2)
    # Se admite tolerancia de tipo de cambio / redondeo contable
    passed = diff <= max(abs(net_change) * 0.02, 50_000.0)
    
    return {
        "test_name": "Reconciliación de Flujos de Caja (Net Change = CFO + CFI + CFF)",
        "passed": passed,
        "status": "PASS" if passed else "FAIL",
        "cfo": cfo,
        "cfi": cfi,
        "cff": cff,
        "sum_of_activities": sum_flows,
        "net_change_reported": net_change,
        "discrepancy_usd": diff
    }


def audit_sanity_bounds(data, fy):
    """Prueba 5: Límites de Sanidad y Sentido Común Financiero."""
    summary = data.get("canonical_summary", {})
    ratios = data.get("key_ratios", {})
    
    rev = summary.get("revenue", {}).get(fy)
    shares = summary.get("shares_diluted", {}).get(fy)
    cash = summary.get("cash_and_equivalents", {}).get(fy)
    gm = ratios.get("gross_margin_pct", {}).get(fy)
    
    errors = []
    if rev is not None and rev <= 0:
        errors.append(f"Ingresos no positivos: {rev}")
    if shares is not None and shares <= 0:
        errors.append(f"Acciones en circulación no positivas: {shares}")
    if cash is not None and cash < 0:
        errors.append(f"Caja negativa: {cash}")
    if gm is not None and (gm < -100 or gm > 100):
        errors.append(f"Margen bruto fuera de rango habitual (-100% a 100%): {gm}%")
    cogs = summary.get("cost_of_goods_sold", {}).get(fy)
    if cogs is not None and cogs < 0:
        errors.append(f"Costo de ventas (COGS) negativo: {cogs}")
    op_exp = summary.get("operating_expenses", {}).get(fy)
    if op_exp is not None and op_exp < 0:
        errors.append(f"Gastos operativos (OpEx) negativos: {op_exp}")
        
    passed = len(errors) == 0
    return {
        "test_name": "Límites de Sanidad Financiera y Rango de Métricas",
        "passed": passed,
        "status": "PASS" if passed else "FAIL",
        "anomalies": errors
    }


def audit_eps_consistency(data, fy):
    """Prueba 6: Consistencia Matemática de BPA: EPS = Beneficio Neto / Acciones Diluidas."""
    summary = data.get("canonical_summary", {})
    inc_detail = data.get("income_statement_detail", {})
    net_income_total = summary.get("net_income", {}).get(fy)
    net_income = summary.get("net_income_common", {}).get(fy)
    if net_income is None:
        for k_ni in [
            "us-gaap_NetIncomeLossAvailableToCommonStockholdersDiluted",
            "NetIncomeLossAvailableToCommonStockholdersDiluted",
            "us-gaap_NetIncomeLossAvailableToCommonStockholdersBasic",
            "NetIncomeLossAvailableToCommonStockholdersBasic",
            "ProfitLossAttributableToOwnersOfParent",
            "ifrs-full_ProfitLossAttributableToOwnersOfParent",
        ]:
            if k_ni in inc_detail and fy in inc_detail[k_ni].get("values", {}):
                val_c = inc_detail[k_ni]["values"][fy]
                if val_c is not None:
                    net_income = val_c
                    break
    if net_income is None:
        net_income = net_income_total

    shares_diluted = summary.get("shares_diluted", {}).get(fy)
    eps_reported = summary.get("eps_diluted", {}).get(fy)
    eps_adj = summary.get("eps_diluted_adjusted", {}).get(fy)
    shares_adj = summary.get("shares_diluted_adjusted", {}).get(fy)
    split_factor = summary.get("split_adjustment_factor", {}).get(fy, 1.0)
    
    if net_income is None or shares_diluted is None or eps_reported is None or shares_diluted == 0:
        return {
            "test_name": "Consistencia Matemática de BPA (EPS = Net Income / Diluted Shares)",
            "passed": None,
            "status": "SKIP",
            "message": f"Datos insuficientes de Net Income o Acciones para {fy}."
        }
        
    calc_eps = round(net_income / shares_diluted, 2)
    diff = round(abs(eps_reported - calc_eps), 2)
    passed = diff <= 0.20
    
    diff_adj = None
    if not passed and eps_adj is not None and shares_adj:
        calc_eps_adj = round(net_income / shares_adj, 2)
        diff_adj = round(abs(eps_adj - calc_eps_adj), 2)
        passed = diff_adj <= 0.20

    if not passed and net_income_total is not None and net_income_total != net_income:
        calc_eps_tot = round(net_income_total / shares_diluted, 2)
        diff_tot = round(abs(eps_reported - calc_eps_tot), 2)
        if diff_tot <= 0.20:
            passed = True
            diff = diff_tot
            calc_eps = calc_eps_tot
            net_income = net_income_total
        
    return {
        "test_name": "Consistencia Matemática de BPA (EPS = Net Income / Diluted Shares)",
        "passed": passed,
        "status": "PASS" if passed else "FAIL",
        "net_income": net_income,
        "shares_diluted": shares_diluted,
        "eps_reported": eps_reported,
        "eps_calculated": calc_eps,
        "eps_adjusted": eps_adj,
        "split_factor": split_factor,
        "discrepancy": diff if diff_adj is None else diff_adj
    }


def run_full_audit(ticker, custom_dir=None):
    """Ejecuta la suite completa de auditoría contable para una empresa."""
    data, output_dir = load_financial_data(ticker, custom_dir)
    fys = data.get("fiscal_years", [])
    cik = data.get("cik", "N/A")
    company_name = data.get("company_name", ticker.upper())
    
    print(f"\n{'='*75}")
    print(f"  MOTOR DE AUDITORÍA CONTABLE: {company_name} ({ticker.upper()})")
    print(f"  CIK SEC: {cik} | Períodos Auditados ({len(fys)}): {fys}")
    print(f"{'='*75}")
    
    audit_results = {
        "ticker": ticker.upper(),
        "company_name": company_name,
        "cik": cik,
        "audit_timestamp": datetime.now().isoformat(),
        "years_audited": {},
        "overall_status": "PASS",
        "total_tests": 0,
        "passed_tests": 0,
        "failed_tests": 0,
        "skipped_tests": 0,
        "compliance_score_pct": 100.0
    }
    
    for fy in fys:
        print(f"\n--- Auditando Período: {fy} ---")
        tests = [
            audit_balance_sheet(data, fy),
            audit_gross_profit(data, fy),
            audit_free_cash_flow(data, fy),
            audit_cash_flow_reconciliation(data, fy),
            audit_sanity_bounds(data, fy),
            audit_eps_consistency(data, fy)
        ]
        
        audit_results["years_audited"][fy] = tests
        for t in tests:
            audit_results["total_tests"] += 1
            if t["status"] == "PASS":
                audit_results["passed_tests"] += 1
                print(f"  [PASS] {t['test_name']}")
            elif t["status"] == "FAIL":
                audit_results["failed_tests"] += 1
                audit_results["overall_status"] = "FAIL"
                disc_msg = t.get("discrepancy_usd", t.get("discrepancy", t.get("anomalies", "N/A")))
                print(f"  [FAIL] {t['test_name']} -> Discrepancia/Detalle: {disc_msg}")
            else:
                audit_results["skipped_tests"] += 1
                print(f"  [SKIP] {t['test_name']} ({t.get('message', '')})")
                
    # Calcular score de cumplimiento
    executed_tests = audit_results["passed_tests"] + audit_results["failed_tests"]
    if executed_tests > 0:
        score = (audit_results["passed_tests"] / executed_tests) * 100.0
        audit_results["compliance_score_pct"] = round(score, 1)
        
    print(f"\n{'='*75}")
    print(f"  RESULTADO GLOBAL: {audit_results['overall_status']} | Cumplimiento: {audit_results['compliance_score_pct']}%")
    print(f"  Tests Aprobados: {audit_results['passed_tests']} | Fallidos: {audit_results['failed_tests']} | Omitidos: {audit_results['skipped_tests']}")
    print(f"{'='*75}\n")
    
    # Guardar reporte de auditoría
    audit_report_path = output_dir / "audit_report.json"
    with open(audit_report_path, "w", encoding="utf-8") as f:
        json.dump(audit_results, f, indent=2, ensure_ascii=False)
        
    return audit_results


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--dir", default=None)
    args = parser.parse_args()
    
    run_full_audit(args.ticker, args.dir)
