# -*- coding: utf-8 -*-
"""
tests/test_capa4_web_analytics_hygiene.py - Pruebas unitarias e invariantes de Capa 4:
Valida modularización de web_dashboard/analytics/, higiene AST (<= 180L, cero except: pass),
SSOT de rutas/arquetipos, conversión explícita de unidades y cumplimiento de Regla 6.
"""
import ast
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from django.test import RequestFactory

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = PROJECT_ROOT / "web_dashboard"
if str(WEB_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "web_dashboard.settings")

import django  # noqa: E402

django.setup()

from analytics.views import view_utils  # noqa: E402
from analytics.views import views as analytics_views  # noqa: E402
from analytics.views.views_charts import build_charts_and_segments_context  # noqa: E402
from analytics.views.views_charts_sector import build_sector_kpis_and_series  # noqa: E402
from analytics.views.views_scoring import build_scoring_context  # noqa: E402
from analytics.views.views_valuation import build_valuation_context  # noqa: E402


class TestCapa4ASTAndStaticHygiene(unittest.TestCase):
    """Verifica higiene AST, límites de tamaño y ausencia de defaults prohibidos."""

    def test_analytics_ast_hygiene_and_function_size(self):
        files = sorted(
            f for f in (WEB_DIR / "analytics").rglob("*.py")
            if "__pycache__" not in str(f)
        )
        self.assertGreaterEqual(len(files), 15)
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

    def test_no_prohibited_regla6_defaults_in_views(self):
        banned_fragments = (
            'cred_kpis.get("npl_90_plus_pct", 18.7)',
            'cred_kpis.get("provision_coverage_15_plus_pct", 105.0)',
            'or "WIDE MOAT"',
            '"41.8x"',
            "else 3.23",
            'vp.get("buyback_rate_pct", 1.5)',
        )
        view_files = sorted((WEB_DIR / "analytics" / "views").glob("*.py"))
        for f in view_files:
            src = f.read_text(encoding="utf-8")
            for frag in banned_fragments:
                self.assertNotIn(frag, src, f"Literal Regla 6 prohibido {frag!r} en {f}")


class TestCapa4SSOTAndRegla6Behavior(unittest.TestCase):
    """Valida invariantes contables, arquetipos SSOT y ausencia de valores ficticios."""

    def test_unit_converters_eliminate_threshold_bugs(self):
        self.assertEqual(view_utils.usd_to_m(-500_000.0), -0.5)
        self.assertEqual(view_utils.already_m(4_719_984.5), 4_719_984.5)
        self.assertEqual(view_utils.pct_from_key_ratio(0.86), 0.86)
        self.assertIsNone(view_utils.usd_to_m(None))
        self.assertIsNone(view_utils.pct_from_key_ratio(None))

    def test_archetype_resolution_uses_ssot_normalization(self):
        self.assertEqual(view_utils.resolve_company_archetype({"archetype": "BANKING"}, {}), "FINANCIAL_BANKING")
        self.assertEqual(view_utils.resolve_company_archetype({}, {"archetype": "REIT"}), "REAL_ESTATE_REIT")
        self.assertEqual(view_utils.resolve_company_archetype({"archetype": "INSURER"}, {}), "INSURANCE")
        self.assertEqual(view_utils.resolve_company_archetype({"archetype": "ECOSYSTEM_PLATFORM"}, {}), "PLATFORM_ECOSYSTEM")

    def test_scoring_preserves_zero_scores_and_returns_nd_on_empty(self):
        zero_scores = {
            "piotroski_f_score": {"LTM": {"total_score": 0, "signals": {}}},
            "mohanram_g_score": {"LTM": {"total_score": 0, "signals": {}}},
        }
        ctx = build_scoring_context(
            ticker="EMPTY_Z", scores=zero_scores, fs={}, fys=["LTM"],
            statements_fys=["LTM"], latest_p="LTM", canonical={},
            archetype="STANDARD_CORPORATE", is_banking=False, bs_data={},
        )
        self.assertEqual(ctx["f_score"], 0)
        self.assertEqual(ctx["g_score"], 0)
        self.assertEqual(ctx["rating_synth"], "N/D")
        self.assertEqual(ctx["interest_cov_display"], "N/D")
        self.assertEqual(ctx["kpis_returns"]["wacc_val"], "N/D")
        self.assertEqual(ctx["sloan_detail"]["sloan_str"], "N/D")
        self.assertEqual(ctx["solvency_13_2"]["interest_coverage_str"], "N/D")
        self.assertEqual(ctx["distress_detail"]["altman_bucket"], 0)
        self.assertFalse(ctx["distress_detail"]["rating_is_safe"])

    def test_platform_kpis_no_meli_fallback_and_missing_margins_none(self):
        sector = build_sector_kpis_and_series(
            canonical={"revenue": {"FY2025": 1000e6}, "free_cash_flow": {}},
            key_ratios={"cost_of_risk_loans_pct": {"FY2025": 0.86}},
            enriched={},
            chart_periods=["FY2025"],
        )
        pk = sector["platform_kpis"]
        self.assertIsNone(pk["npl_15_90_pct"])
        self.assertIsNone(pk["npl_90_plus_pct"])
        self.assertIsNone(pk["provision_coverage_pct"])
        self.assertEqual(pk["gmv_3m_str"], "N/D")
        self.assertEqual(pk["credit_portfolio_str"], "N/D")
        self.assertEqual(sector["cost_of_risk_series"], [0.86])

        with tempfile.TemporaryDirectory() as tmpdir:
            ch = build_charts_and_segments_context(
                ticker_dir=Path(tmpdir),
                fs={"sec_metadata": {}, "fiscal_years": ["FY2025"]},
                fys=["FY2025"],
                canonical={"revenue": {"FY2025": 1000e6}, "free_cash_flow": {}},
                key_ratios={"gross_margin_pct": {}},
                enriched={},
            )
        self.assertEqual(json.loads(ch["fcf_m_series_json"]), [None])
        self.assertEqual(json.loads(ch["gm_series_json"]), [None])

    def test_index_card_and_valuation_missing_inputs_no_fake_defaults(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            comp_dir = Path(tmpdir) / "SYN_EMPTY"
            comp_dir.mkdir(parents=True, exist_ok=True)
            (comp_dir / "fundamental_scores.json").write_text(json.dumps({"ticker": "SYN_EMPTY"}), encoding="utf-8")
            card = analytics_views._build_index_card(comp_dir, cache_data={}, mkt_extractor=None)

        self.assertEqual(card["f_score"], "-")
        self.assertEqual(card["g_score"], "-")
        self.assertEqual(card["rating"], "N/D")
        self.assertEqual(card["wacc"], "N/D")
        self.assertEqual(card["roic_adj"], "N/D")
        self.assertEqual(card["spread"], "N/D")
        self.assertEqual(card["moat_badge"], "N/D")

        rf = RequestFactory()
        req = rf.get("/company/SYN_EMPTY/")
        with patch("market_data_provider.MarketDataExtractor.get_market_data", return_value={"price": None}):
            val_ctx = build_valuation_context(
                request=req, DATA_DIR=Path(tmpdir), ticker="SYN_EMPTY", scores={}, fs={},
                statements_fys=["FY2025"], canonical={}, archetype="STANDARD_CORPORATE", is_banking=False,
            )
        self.assertEqual(val_ctx["buyback_rate_pct"], 0.0)


if __name__ == "__main__":
    unittest.main()
