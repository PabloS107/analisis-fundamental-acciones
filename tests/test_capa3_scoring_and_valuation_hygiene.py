"""
tests/test_capa3_scoring_and_valuation_hygiene.py - Pruebas unitarias e invariantes de Capa 3:
Valida la modularización en pipeline/scoring_modules y pipeline/valuation_modules,
higiene AST, SSOT de arquetipos y cumplimiento estricto de Regla 4 y Regla 6 (cero fallbacks
ficticios, cero series sintéticas y trazabilidad exacta de g_implied_oe_pct).
"""

import ast
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PIPELINE_DIR = PROJECT_ROOT / "pipeline"
for p in (PROJECT_ROOT, PIPELINE_DIR):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import financial_scoring_engine
import valuation_engine
from scoring_modules import profitability_capital
from valuation_modules import market_history


class TestCapa3ASTAndExports(unittest.TestCase):
    """Verifica higiene AST, límites de tamaño y retrocompatibilidad de fachadas."""

    def test_capa3_ast_hygiene_and_function_size(self):
        files = (
            [PIPELINE_DIR / "financial_scoring_engine.py", PIPELINE_DIR / "valuation_engine.py"]
            + sorted((PIPELINE_DIR / "scoring_modules").glob("*.py"))
            + sorted((PIPELINE_DIR / "valuation_modules").glob("*.py"))
        )
        for f in files:
            src = f.read_text(encoding="utf-8")
            tree = ast.parse(src, filename=str(f))
            for node in ast.walk(tree):
                if isinstance(node, ast.ExceptHandler):
                    self.assertIsNotNone(node.type, f"Bare except detectado en {f}:{node.lineno}")
                    is_pass = len(node.body) == 1 and isinstance(node.body[0], ast.Pass)
                    self.assertFalse(is_pass, f"except: pass silencioso detectado en {f}:{node.lineno}")
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    span = (node.end_lineno or node.lineno) - node.lineno + 1
                    self.assertLessEqual(span, 180, f"Función > 180L en {f}:{node.lineno} {node.name} ({span}L)")

    def test_no_prohibited_hardcoded_literals_in_capa3(self):
        banned_fragments = (
            "0.1090",
            "\"price\": 230.0",
            "\"market_cap_usd_m\": 3000000.0",
            "current_price * 0.85",
            "current_price * factor for factor in [0.65",
            "rotce_val = 0.15",
        )
        files = (
            [PIPELINE_DIR / "financial_scoring_engine.py", PIPELINE_DIR / "valuation_engine.py"]
            + sorted((PIPELINE_DIR / "scoring_modules").glob("*.py"))
            + sorted((PIPELINE_DIR / "valuation_modules").glob("*.py"))
        )
        for f in files:
            src = f.read_text(encoding="utf-8")
            for frag in banned_fragments:
                self.assertNotIn(frag, src, f"Literal/fallback prohibido {frag!r} encontrado en {f}")

    def test_facade_reexports_all_public_symbols(self):
        for attr in (
            "load_industry_medians",
            "load_peer_benchmarks",
            "compute_peer_benchmarks",
            "get_sector_benchmarks",
            "PiotroskiScoreCalculator",
            "MohanramScoreCalculator",
            "CombinedMatrixClassifier",
            "NovyMarxCalculator",
            "IntangibleROICCalculator",
            "GreenblattROCCalculator",
            "WACCCalculator",
            "ForensicAccountingEngine",
            "DebtSolvencyEngine",
            "extract_period_metrics",
            "calculate_fundamental_scores",
            "_safe_float",
            "_to_millions",
            "normalize_archetype",
        ):
            self.assertTrue(hasattr(financial_scoring_engine, attr), f"Falta re-export {attr} en financial_scoring_engine")

        for attr in (
            "get_report_archetype",
            "get_solvency_archetype",
            "get_valuation_parameters",
            "_generate_sensitivity_grid",
            "solve_reverse_dcf",
            "solve_reverse_dcf_3stage",
            "calculate_dcf_details",
            "calculate_epv_pvgo",
            "calculate_eva_valuation",
            "calculate_5y_forward_irr",
            "calculate_multiples_valuation",
            "calculate_owner_earnings_and_capex",
            "calculate_z_score_valuation",
            "calculate_historical_multiples_analysis",
            "build_audit_traceability",
            "get_valuation_football_field",
            "_fmt_money",
            "_fmt_pct",
        ):
            self.assertTrue(hasattr(valuation_engine, attr), f"Falta re-export {attr} en valuation_engine")


class TestCapa3Regla6AndSSOT(unittest.TestCase):
    """Valida correcciones de Regla 6, Regla 4 y trazabilidad matemática."""

    def test_g_implied_fiscal_matches_real_wacc_and_margin(self):
        scoring_data = {
            "ticker": "SYN_CORP",
            "archetype": "STANDARD_CORPORATE",
            "wacc_analysis": {
                "wacc": 0.075,
                "cost_of_equity_ke": 0.085,
                "effective_tax_rate": 0.21,
                "market_data": {"price": 50.0, "diluted_shares": 100e6, "rf_10y": 0.04, "beta": 1.0, "erp": 0.045},
            },
            "debt_and_solvency_analysis": {"cash_flow_leverage": {"LTM": {"net_debt": 0.0, "ebit": 200.0, "fcf": 120.0}}},
        }
        fs_data = {
            "canonical_summary": {"revenue": {"LTM": 1000e6}, "free_cash_flow": {"LTM": 120e6}},
            "key_ratios": {"fcf_margin_pct": {"LTM": 12.0}},
        }
        with patch.object(market_history, "_fetch_yf_history", return_value=None), patch.object(
            market_history, "resolve_market_cache_path", return_value=Path(tempfile.gettempdir()) / "no_cache_xyz.json"
        ):
            vp = valuation_engine.get_valuation_parameters(scoring_data, "SYN_CORP", fs_data=fs_data)
        self.assertEqual(vp["g_implied_fiscal_pct"], vp["g_implied_our_pct"])

    def test_z_score_never_fabricates_synthetic_prices(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            no_cache = Path(tmpdir) / "empty_cache.json"
            with patch.object(market_history, "_fetch_yf_history", return_value=None), patch.object(
                market_history, "resolve_market_cache_path", return_value=no_cache
            ):
                res = valuation_engine.calculate_z_score_valuation("UNKNOWN_XYZ", 100.0, 10.0, 0.0, 50.0, is_financial=False)
        self.assertIsNone(res["z_score"])
        self.assertIsNone(res["mean_multiple"])
        self.assertEqual(res["bands"], {})
        self.assertEqual(res["history"], [])
        self.assertEqual(res["current_multiple"], 20.0)
        self.assertIn("N/D", res["status"])

    def test_historical_multiples_never_fabricates_085_close_prices(self):
        fs_data = {
            "canonical_summary": {
                "revenue": {"FY2025": 1000e6, "FY2024": 900e6},
                "net_income": {"FY2025": 100e6, "FY2024": 90e6, "LTM": 110e6},
                "free_cash_flow": {"FY2025": 110e6, "FY2024": 95e6, "LTM": 115e6},
            }
        }
        with patch.object(market_history, "_fetch_yf_history", return_value=None):
            hm_corp = valuation_engine.calculate_historical_multiples_analysis(
                "SYN_NO_HIST", 50.0, 100.0, 0.0, 100.0, 100.0, fs_obj=fs_data, is_financial=False
            )
            hm_fin = valuation_engine.calculate_historical_multiples_analysis(
                "SYN_BANK_NO_HIST", 25.0, 100.0, 0.0, 0.0, 0.0, fs_obj=fs_data, is_financial=True, tbv_per_share=10.0
            )
        fy_rows_corp = [r for r in hm_corp["annual_table"] if r["period"] != "LTM"]
        fy_rows_fin = [r for r in hm_fin["annual_table"] if r["period"] != "LTM"]
        self.assertTrue(all(r["price"] is None for r in fy_rows_corp))
        self.assertTrue(all(r["price"] is None for r in fy_rows_fin))

    def test_audit_traceability_renders_real_g_implied_oe_in_latex(self):
        trace = valuation_engine.build_audit_traceability(
            ticker="SYN",
            ebit_reported_m=100.0,
            rd_expense_m=10.0,
            rd_amortization_m=5.0,
            ebit_adjusted_m=105.0,
            tax_rate_pct=20.0,
            nopat_adjusted_m=84.0,
            cfo_m=95.0,
            capex_total_m=25.0,
            maint_capex_m=15.0,
            growth_capex_m=10.0,
            net_rd_inv_m=5.0,
            fcf_reported_m=70.0,
            owner_earnings_m=85.0,
            shares_m=100.0,
            stock_price=30.0,
            net_debt_m=0.0,
            wacc_pct=9.0,
            gn_pct=2.5,
            rd_stock_m=20.0,
            roic_trad_pct=15.0,
            roic_adj_pct=14.0,
            spread_pct=5.0,
            z_score_obj={"z_score": None, "status": "N/D"},
            is_financial=False,
            g_implied_oe_pct=14.3,
        )
        self.assertIn("14.3\\%", trace["math_formulas"]["reverse_dcf"]["latex_substituted"])

    def test_wacc_calculator_missing_extractor_no_apple_defaults(self):
        with patch.object(profitability_capital, "MarketDataExtractor", None):
            res = profitability_capital.WACCCalculator.calculate_wacc_and_spread(
                ticker="NO_MKT",
                recent_fy="FY2025",
                period_data={"total_debt": 0.0},
                roic_adjusted=0.18,
                roic_traditional=0.18,
                benchmarks={},
                archetype="STANDARD_CORPORATE",
            )
        self.assertIsNone(res["market_cap_usd_m"])
        self.assertIsNone(res["enterprise_value_usd_m"])
        self.assertIsNone(res["market_data"]["price"])
        self.assertEqual(res["market_data"]["audit"]["status"], "UNAVAILABLE_MODULE_MISSING")

    def test_empty_entities_no_fake_100_015_15_defaults(self):
        vp_bank = valuation_engine.get_valuation_parameters({"archetype": "BANKING"}, "EMPTY_BK")
        self.assertEqual(vp_bank["archetype"], "FINANCIAL_BANKING")
        self.assertIsNone(vp_bank["rotce_val"])
        self.assertIsNone(vp_bank["rotce_pct"])
        self.assertIsNone(vp_bank["spread_economic_pct"])
        self.assertEqual(vp_bank["price"], 0.0)
        self.assertEqual(vp_bank["buyback_rate_pct"], 0.0)

        vp_corp = valuation_engine.get_valuation_parameters({}, "EMPTY_CORP")
        self.assertEqual(vp_corp["price"], 0.0)
        self.assertEqual(vp_corp["base_rev_m"], 0.0)
        self.assertEqual(vp_corp["buyback_rate_pct"], 0.0)
        grid = valuation_engine._generate_sensitivity_grid(vp_corp)
        self.assertEqual(len(grid), 5)
        for row in grid:
            self.assertEqual(len(row), 8)
            self.assertEqual(row[1:7], ("N/D", "N/D", "N/D", "N/D", "N/D", "N/D"))

    def test_valuation_archetype_ssot_normalization(self):
        self.assertEqual(valuation_engine.get_report_archetype({"archetype": "BANKING"}), "FINANCIAL_BANKING")
        self.assertEqual(valuation_engine.get_report_archetype({"archetype": "REAL_ESTATE"}), "REAL_ESTATE_REIT")
        self.assertEqual(valuation_engine.get_report_archetype({"archetype": "REIT"}), "REAL_ESTATE_REIT")
        self.assertEqual(valuation_engine.get_report_archetype({"archetype": "INSURER"}), "INSURANCE")
        self.assertEqual(valuation_engine.get_report_archetype({"archetype": "ECOSYSTEM_PLATFORM"}), "PLATFORM_ECOSYSTEM")
        self.assertEqual(
            valuation_engine.get_report_archetype(
                {"sic_code": "7389", "industry_name": "E-Commerce Marketplace & Fintech Ecosystem"}
            ),
            "PLATFORM_ECOSYSTEM",
        )


if __name__ == "__main__":
    unittest.main()
