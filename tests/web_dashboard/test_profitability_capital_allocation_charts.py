# -*- coding: utf-8 -*-
"""
test_profitability_capital_allocation_charts.py
Test unitario y de regresión universal para la pestaña 'Rentabilidad y Asignación de Capital' rediseñada.
Valida:
1. Calidad Contable y Conversión de Caja (FCF vs Net Income y Ratio %)
2. Dinámica del Accionista: Recompra Neta ($M = Recompras - SBC) vs Float (Acciones Diluidas)
3. Marco de Asignación de Capital: Retorno vs Reinversión (Dos columnas agrupadas vs CFO)
4. Compatibilidad universal con arquetipos: AAPL, NVDA, DECK, GOOGL, META y JPM.
5. Renderizado HTML completo de la plantilla company_detail.html con el cliente Django.
"""

import unittest
import os
import sys
import json
from pathlib import Path

# Setup Django environment
PROJECT_ROOT = Path(__file__).resolve().parents[2]
for _p in (PROJECT_ROOT, PROJECT_ROOT / "pipeline", PROJECT_ROOT / "web_dashboard"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
import pipeline  # noqa: E402, F401
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'web_dashboard.settings')
import django
django.setup()

from django.test import Client
from analytics.views.views_charts import build_charts_and_segments_context


class TestProfitabilityCapitalAllocationCharts(unittest.TestCase):

    def setUp(self):
        self.control_tickers = ['AAPL', 'NVDA', 'DECK', 'GOOGL', 'META']
        self.client = Client()

    def test_context_generation_for_control_tickers(self):
        for ticker in self.control_tickers:
            path = f"data/processed/{ticker}/financial_statements.json"
            if not os.path.exists(path):
                continue
            with open(path, "r", encoding="utf-8") as f:
                fs = json.load(f)

            scores_path = f"data/processed/{ticker}/fundamental_scores.json"
            scores = {}
            if os.path.exists(scores_path):
                with open(scores_path, "r", encoding="utf-8") as f:
                    scores = json.load(f)

            fys = fs.get("fiscal_years", [])
            canonical = fs.get("canonical_summary", {})
            key_ratios = fs.get("key_ratios", {})
            enriched = scores.get("enriched_statements", {})

            ticker_dir = Path(f"data/processed/{ticker}")
            ctx = build_charts_and_segments_context(
                ticker_dir=ticker_dir,
                fs=fs,
                fys=fys,
                canonical=canonical,
                key_ratios=key_ratios,
                enriched=enriched
            )

            # 1. Verificar claves exportadas para Conversión de Caja
            self.assertIn("cash_conv_rates_json", ctx)
            self.assertIn("cash_conv_summary", ctx)
            conv_rates = json.loads(ctx["cash_conv_rates_json"])
            self.assertIsInstance(conv_rates, list)
            self.assertGreater(len(conv_rates), 0)

            # Verificar lógica del ratio FCF / Net Income
            chart_periods = json.loads(ctx["chart_periods_json"])
            for idx, p in enumerate(chart_periods):
                ni = canonical.get("net_income", {}).get(p)
                fcf = canonical.get("free_cash_flow", {}).get(p)
                rate = conv_rates[idx]
                if ni is not None and ni > 0 and fcf is not None:
                    expected_rate = round((float(fcf) / float(ni)) * 100.0, 1)
                    self.assertEqual(rate, expected_rate, f"{ticker} {p} conversion rate mismatch")
                else:
                    self.assertIsNone(rate)

            # 2. Verificar Dinámica del Accionista (Recompra Neta vs Float)
            self.assertIn("net_buybacks_series_json", ctx)
            self.assertIn("net_buyback_colors_json", ctx)
            self.assertIn("net_buyback_borders_json", ctx)
            self.assertIn("sbc_series_json", ctx)
            self.assertIn("shares_yoy_pct_json", ctx)
            self.assertIn("buybacks_summary", ctx)

            net_bbs = json.loads(ctx["net_buybacks_series_json"])
            colors = json.loads(ctx["net_buyback_colors_json"])
            borders = json.loads(ctx["net_buyback_borders_json"])
            sbc_series = json.loads(ctx["sbc_series_json"])
            bb_series = json.loads(ctx["buybacks_series_json"])

            self.assertEqual(len(net_bbs), len(chart_periods))
            self.assertEqual(len(colors), len(chart_periods))
            for idx, net_val in enumerate(net_bbs):
                bb_val = bb_series[idx]
                sbc_val = sbc_series[idx]
                self.assertLessEqual(abs(net_val - (bb_val - sbc_val)), 0.15)
                if net_val >= 0:
                    self.assertIn("16, 185, 129", colors[idx])
                    self.assertEqual(borders[idx], "#10b981")
                else:
                    self.assertIn("244, 63, 94", colors[idx])
                    self.assertEqual(borders[idx], "#f43f5e")

            # 3. Verificar Marco de Asignación de Capital
            self.assertIn("chart_alloc_data_json", ctx)
            alloc_data = json.loads(ctx["chart_alloc_data_json"])
            self.assertIn("reinvest_rate_series", alloc_data)
            self.assertIn("return_rate_series", alloc_data)
            self.assertEqual(len(alloc_data["reinvest_rate_series"]), len(chart_periods))
            self.assertEqual(len(alloc_data["return_rate_series"]), len(chart_periods))

    def test_banking_archetype_integrity(self):
        """Verifica que el arquetipo bancario (JPM) no se rompa y genere su contexto correctamente"""
        path = "data/processed/JPM/financial_statements.json"
        if not os.path.exists(path):
            return
        with open(path, "r", encoding="utf-8") as f:
            fs = json.load(f)

        scores_path = "data/processed/JPM/fundamental_scores.json"
        scores = {}
        if os.path.exists(scores_path):
            with open(scores_path, "r", encoding="utf-8") as f:
                scores = json.load(f)

        fys = fs.get("fiscal_years", [])
        canonical = fs.get("canonical_summary", {})
        key_ratios = fs.get("key_ratios", {})
        enriched = scores.get("enriched_statements", {})

        ctx = build_charts_and_segments_context(
            ticker_dir=Path("data/processed/JPM"),
            fs=fs,
            fys=fys,
            canonical=canonical,
            key_ratios=key_ratios,
            enriched=enriched
        )
        self.assertIn("net_buybacks_series_json", ctx)
        self.assertIn("banking_kpis", ctx)

    def test_view_renders_company_detail_html(self):
        """Verifica que la vista web completa de Django renderice 200 OK y contenga los nuevos canvases y selectores"""
        for ticker in ['AAPL', 'NVDA', 'DECK', 'GOOGL', 'JPM']:
            response = self.client.get(f"/company/{ticker}/")
            self.assertEqual(response.status_code, 200, f"Failed to render company detail for {ticker}")
            html = response.content.decode('utf-8')
            if ticker != 'JPM':
                self.assertIn('chartCashConversion', html, f"chartCashConversion canvas missing in {ticker}")
                self.assertIn('chartNetBuybacksFloat', html, f"chartNetBuybacksFloat canvas missing in {ticker}")
                self.assertIn('chartCapitalAllocation', html, f"chartCapitalAllocation canvas missing in {ticker}")
                self.assertIn('setBuybackPeriodView', html, f"setBuybackPeriodView missing in {ticker}")
                self.assertIn('bb-period-btn', html, f"bb-period-btn selector missing in {ticker}")
                self.assertIn('Mix Recompras vs. Dividendos', html, f"Mix card missing in {ticker}")
                self.assertNotIn('chartCashFlow', html, f"Old chartCashFlow canvas still in {ticker}")
            else:
                self.assertIn('chartNetBuybacksFloatBanking', html, f"chartNetBuybacksFloatBanking canvas missing in JPM")

    def test_googl_and_deck_acquisitions_ma(self):
        """Verifica que GOOGL extraiga adquisiciones M&A ($34.2B LTM, $6.9B Mandiant) y DECK mantenga $0.0 orgánico"""
        # 1. GOOGL
        resp_googl = self.client.get("/company/GOOGL/")
        self.assertEqual(resp_googl.status_code, 200)
        html_googl = resp_googl.content.decode('utf-8')
        # GOOGL M&A debe estar presente en el dataset JSON del gráfico de asignación
        self.assertIn('"ma": [', html_googl)
        # 34270.0 ($34.2B) en LTM
        self.assertIn('34270.0', html_googl)

        # 2. DECK
        resp_deck = self.client.get("/company/DECK/")
        self.assertEqual(resp_deck.status_code, 200)
        html_deck = resp_deck.content.decode('utf-8')
        # DECK debe ser $0 (0.0%) M&A en todas sus series anuales
        self.assertIn('$0 (0.0%)', html_deck)

    def test_5y_audited_capital_allocation_kpis(self):
        """Verifica que las tarjetas de Asignación de Capital reflejen con precisión matemática los 5 años fiscales auditados."""
        expected_benchmarks = {
            'GOOGL': {
                'label': 'FY2021-FY2025 (5Y Auditado)',
                'tot_bb': '$279,005.0M',
                'tot_div': '$17,412.0M',
                'tot_return': '$296,417.0M',
            },
            'META': {
                'label': 'FY2021-FY2025 (5Y Auditado)',
                'tot_bb': '$148,640.0M',
                'tot_div': '$10,396.0M',
                'tot_return': '$159,036.0M',
            },
            'NVDA': {
                'label': 'FY2022-FY2026 (5Y Auditado)',
                'tot_bb': '$93,364.0M',
                'tot_div': '$3,000.0M',
                'tot_return': '$96,364.0M',
            },
            'AAPL': {
                'label': 'FY2022-FY2026 (5Y Auditado)',
                'tot_bb': '$439,002.0M',
                'tot_div': '$76,242.0M',
                'tot_return': '$515,244.0M',
            },
            'DECK': {
                'label': 'FY2022-FY2026 (5Y Auditado)',
                'tot_bb': '$2,711.1M',
                'tot_div': '$0',
                'tot_return': '$2,711.1M',
            },
        }

        for ticker, exp in expected_benchmarks.items():
            path = f"data/processed/{ticker}/financial_statements.json"
            with open(path, "r", encoding="utf-8") as f:
                fs = json.load(f)
            fys = fs.get("fiscal_years", [])
            canonical = fs.get("canonical_summary", {})
            key_ratios = fs.get("key_ratios", {})
            ticker_dir = Path(f"data/processed/{ticker}")
            ctx = build_charts_and_segments_context(
                ticker_dir=ticker_dir,
                fs=fs,
                fys=fys,
                canonical=canonical,
                key_ratios=key_ratios,
                enriched={}
            )
            kpis = ctx.get("alloc_kpis", {})
            self.assertEqual(kpis.get("recent_years_label"), exp["label"], f"{ticker} label mismatch")
            self.assertEqual(kpis.get("tot_bb_5y_str"), exp["tot_bb"], f"{ticker} buybacks mismatch")
            self.assertEqual(kpis.get("tot_div_5y_str"), exp["tot_div"], f"{ticker} dividends mismatch")
            self.assertEqual(kpis.get("total_shareholder_return_5y_str"), exp["tot_return"], f"{ticker} total return mismatch")


if __name__ == '__main__':
    unittest.main()
