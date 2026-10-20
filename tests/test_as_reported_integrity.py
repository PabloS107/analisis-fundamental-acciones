"""
Tests de integridad y no-regresión universal para As-Reported Statements (Regla 2 y Regla 6)
Verifica:
1. Sin colisión dimensional ni duplicación de LTM con distinto FY_latest (AAPL, MELI).
2. Sin inversión de signos entre LTM y FY_latest en partidas de costos y gastos (MELI, NU, NVDA).
3. Ninguna cuenta no total del Balance tiene un valor LTM idéntico a Total Assets (NU).
4. El LTM de Long-term debt y Dividends paid en as_reported_statements de NVDA coincide con canonical_summary.
"""
import unittest
import json
from pathlib import Path

DATA_DIR = Path("data/processed")
TICKERS = ["AAPL", "DECK", "JPM", "MELI", "META", "NU", "NVDA", "O", "PGR"]

def load_statements(ticker):
    path = DATA_DIR / ticker / "financial_statements.json"
    assert path.exists(), f"financial_statements.json for {ticker} not found"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

class TestAsReportedIntegrity(unittest.TestCase):

    def test_1_no_duplicate_ltm_on_different_fy(self):
        """1. Dos filas distintas del mismo estado no deben compartir el mismo valor LTM teniendo distinto FY_latest."""
        for ticker in TICKERS:
            data = load_statements(ticker)
            as_reported = data.get("as_reported_statements", {})
            fys = [p for p in data.get("fiscal_years", []) if p != "LTM"]
            if not fys:
                continue
            latest_fy = fys[0]

            for s_name, rows in as_reported.items():
                non_abs_rows = [r for r in rows if not r.get("is_abstract") and r.get("values", {}).get("LTM") is not None]
                for i in range(len(non_abs_rows)):
                    for j in range(i + 1, len(non_abs_rows)):
                        r1 = non_abs_rows[i]
                        r2 = non_abs_rows[j]
                        v1_ltm = r1["values"].get("LTM")
                        v2_ltm = r2["values"].get("LTM")
                        v1_fy = r1["values"].get(latest_fy)
                        v2_fy = r2["values"].get(latest_fy)
                        
                        if v1_fy is not None and v2_fy is not None and v1_fy != v2_fy and v1_fy != 0.0 and v2_fy != 0.0:
                            if v1_ltm == v2_ltm and v1_ltm != 0.0:
                                self.fail(
                                    f"[{ticker}] [{s_name}] Dimensional collision: rows '{r1['label']}' and '{r2['label']}' "
                                    f"share identical LTM={v1_ltm} but have distinct {latest_fy}: {v1_fy} vs {v2_fy}"
                                )

    def test_2_no_sign_inversion_in_costs_expenses(self):
        """2. Las filas de costos/gastos no deben cambiar de signo entre LTM y FY_latest."""
        for ticker in TICKERS:
            data = load_statements(ticker)
            as_reported = data.get("as_reported_statements", {})
            fys = [p for p in data.get("fiscal_years", []) if p != "LTM"]
            if not fys:
                continue
            latest_fy = fys[0]
            inc_rows = as_reported.get("income_statement", [])
            for r in inc_rows:
                if r.get("is_abstract"):
                    continue
                lbl = r.get("label", "").lower()
                conc = r.get("concept", "").lower()
                is_expense = (
                    any(ind in conc or ind in lbl for ind in ('cost of', 'costof', 'expense', 'expenses', 'charges', 'provision', 'research', 'selling', 'administrative'))
                    and not any(excl in conc for excl in ('income', 'revenue', 'gain', 'operatingincomeloss', 'netincomeloss', 'profitloss'))
                )
                if is_expense:
                    v_ltm = r["values"].get("LTM")
                    v_fy = r["values"].get(latest_fy)
                    if v_ltm is not None and v_fy is not None and v_ltm != 0.0 and v_fy != 0.0:
                        self.assertTrue(
                            (v_ltm > 0 and v_fy > 0) or (v_ltm < 0 and v_fy < 0),
                            f"[{ticker}] Sign inversion in expense row '{r['label']}': LTM={v_ltm} vs {latest_fy}={v_fy}"
                        )

    def test_3_no_balance_account_equals_total_assets(self):
        """3. Ninguna cuenta no-total del Balance debe tener un valor LTM idéntico a Total Assets."""
        for ticker in TICKERS:
            data = load_statements(ticker)
            as_reported = data.get("as_reported_statements", {})
            bal_rows = as_reported.get("balance_sheet", [])
            tot_assets_ltm = None
            for r in bal_rows:
                lbl = r.get("label", "").lower()
                conc = r.get("concept", "").lower()
                if (conc in ("us-gaap_assets", "assets", "ifrs-full_assets") or lbl in ("total assets", "assets", "activos totales", "total de activos")):
                    tot_assets_ltm = r["values"].get("LTM")
                    break
            
            if tot_assets_ltm is not None and tot_assets_ltm != 0.0:
                for r in bal_rows:
                    lbl = r.get("label", "").lower()
                    conc = r.get("concept", "").lower()
                    if r.get("is_abstract"):
                        continue
                    if any(tot_kw in lbl for tot_kw in ["total assets", "total liabilities and", "total liabilities &", "total equity and liabilities", "total equity & liabilities"]):
                        continue
                    if conc in ("us-gaap_assets", "assets", "ifrs-full_assets", "us-gaap_liabilitiesandstockholdersequity", "ifrs-full_equityandliabilities"):
                        continue
                    v_ltm = r["values"].get("LTM")
                    if v_ltm is not None and v_ltm == tot_assets_ltm:
                        self.fail(
                            f"[{ticker}] Account '{r['label']}' ({conc}) has LTM={v_ltm} identical to Total Assets={tot_assets_ltm}"
                        )

    def test_4_nvda_debt_and_dividends_match_canonical(self):
        """4. Reconciliación estricta de Long-term debt y Dividends paid en NVDA contra canonical_summary."""
        data = load_statements("NVDA")
        as_reported = data.get("as_reported_statements", {})
        canonical = data.get("canonical_summary", {})
        
        # 4a. Long-term debt
        lt_debt_as_reported = None
        for r in as_reported.get("balance_sheet", []):
            lbl = r.get("label", "").lower()
            conc = r.get("concept", "").lower()
            if "long-term debt" in lbl or conc.endswith("longtermdebtnoncurrent"):
                lt_debt_as_reported = r["values"].get("LTM")
                break
                
        canonical_lt_debt = canonical.get("long_term_debt", {}).get("LTM")
        if canonical_lt_debt is None and canonical.get("total_debt", {}).get("LTM") is not None:
            canonical_lt_debt = canonical.get("total_debt", {}).get("LTM") - (canonical.get("short_term_debt", {}).get("LTM") or 0.0)

        if lt_debt_as_reported is not None and canonical_lt_debt is not None:
            self.assertEqual(
                lt_debt_as_reported, canonical_lt_debt,
                f"[NVDA] Long-term debt mismatch: as_reported={lt_debt_as_reported} vs canonical={canonical_lt_debt}"
            )

        # 4b. Dividends paid
        div_as_reported = None
        for r in as_reported.get("cash_flow_statement", []):
            lbl = r.get("label", "").lower()
            conc = r.get("concept", "").lower()
            if "dividend" in lbl or conc.endswith("paymentsofdividends"):
                div_as_reported = r["values"].get("LTM")
                break
                
        canonical_div = canonical.get("dividends_paid", {}).get("LTM")
        if div_as_reported is not None and canonical_div is not None:
            self.assertEqual(
                abs(div_as_reported), abs(canonical_div),
                f"[NVDA] Dividends paid mismatch: as_reported={div_as_reported} vs canonical={canonical_div}"
            )

    def test_5_100_percent_spanish_labels(self):
        """5. Verifica que el 100% de las partidas en as_reported_statements cuenten con traducción al español y tooltip."""
        for ticker in TICKERS:
            data = load_statements(ticker)
            as_reported = data.get("as_reported_statements", {})
            for s_name, rows in as_reported.items():
                for r in rows:
                    lbl = r.get("label", "")
                    sp_lbl = r.get("spanish_label")
                    orig_tt = r.get("orig_tooltip")
                    self.assertTrue(
                        bool(sp_lbl and sp_lbl.strip()),
                        f"[{ticker}] [{s_name}] Missing spanish_label for row '{lbl}'"
                    )
                    self.assertTrue(
                        bool(orig_tt and orig_tt.strip()),
                        f"[{ticker}] [{s_name}] Missing orig_tooltip for row '{lbl}'"
                    )

    def test_6_dual_view_context_integrity(self):
        """6. Verifica que la vista Django company_detail construya ambos modelos de estados financieros (std y as_rep)."""
        import os, sys
        sys.path.insert(0, os.path.abspath('web_dashboard'))
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "web_dashboard.settings")
        import django
        django.setup()
        from django.test import RequestFactory
        from analytics.views import company_detail

        rf = RequestFactory()
        req = rf.get("/company/AAPL/")

        for ticker in TICKERS:
            res = company_detail(req, ticker=ticker)
            self.assertEqual(res.status_code, 200, f"[{ticker}] company_detail failed with status {res.status_code}")
            html = res.content.decode("utf-8")
            self.assertIn("table-view-std", html, f"[{ticker}] Standardized table view missing in HTML")
            self.assertIn("table-view-asrep", html, f"[{ticker}] As-reported table view missing in HTML")
            self.assertIn("btn-view-std", html, f"[{ticker}] View switch toggle missing in HTML")

if __name__ == "__main__":
    unittest.main()
