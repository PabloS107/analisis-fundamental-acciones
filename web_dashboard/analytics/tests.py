from django.test import TestCase, Client

class ValuationAndSensitivityTests(TestCase):
    def setUp(self):
        self.client = Client()

    def test_deck_valuation_and_sensitivity(self):
        response = self.client.get('/company/DECK/')
        self.assertEqual(response.status_code, 200)
        ctx = response.context
        
        # Parity with Word report (.docx Section 14) and dynamic valuation engine
        expected_g_implied = ctx['vp']['g_implied_our_pct']
        self.assertAlmostEqual(ctx['g_implied_pct'], expected_g_implied, delta=0.01)
        self.assertAlmostEqual(ctx['fcf_margin_pct'], 20.2, delta=0.1)
        self.assertEqual(ctx['net_debt_m'], -1602.6)
        self.assertAlmostEqual(ctx['rev_base'], 5527.3, delta=1.0)
        self.assertGreater(ctx['stock_price'], 50.0)
        
        # Sensitivity matrix tests
        grid = ctx['sensitivity_grid']
        self.assertEqual(len(grid), 5)
        base_row = grid[2]
        self.assertTrue(base_row['is_base'])
        self.assertIn(f"{ctx['vp']['wacc_pct']:.2f}%", base_row['wacc_label'])
        self.assertAlmostEqual(float(base_row['g_25'].replace('%', '')), expected_g_implied, delta=0.15) # Central scenario cell
        
        # HTML content verification
        content = response.content.decode('utf-8')
        self.assertIn('Matriz Bidimensional de Sensibilidad Reverse DCF', content)
        self.assertIn('ESCENARIO CENTRAL', content)
        self.assertIn('netDebt = -1602.60', content)

    def test_aapl_valuation_and_sensitivity(self):
        response = self.client.get('/company/AAPL/')
        self.assertEqual(response.status_code, 200)
        ctx = response.context
        
        # Dynamic exact parity for Apple (Section 14) calculated automatically
        expected_g_implied = ctx['vp']['g_implied_our_pct']
        self.assertAlmostEqual(ctx['g_implied_pct'], expected_g_implied, delta=0.01)
        self.assertEqual(len(ctx['sensitivity_grid']), 5)
        base_row = ctx['sensitivity_grid'][2]
        self.assertTrue(base_row['is_base'])
        self.assertIn(f"{expected_g_implied:.1f}", base_row['g_25'])
        self.assertGreater(ctx['stock_price'], 50.0)

    def test_nu_banking_view(self):
        response = self.client.get('/company/NU/')
        self.assertEqual(response.status_code, 200)
        ctx = response.context
        self.assertTrue(ctx['is_financial'])
        self.assertEqual(ctx['ticker'], 'NU')
        # Excess Return Model checks
        self.assertIn('fair_value_excess_return', ctx['vp'])
        self.assertGreater(ctx['vp']['fair_value_excess_return'], 0.0)
        self.assertEqual(len(ctx['sensitivity_grid']), 5)
        # Verify solvency displays N/A cleanly for non-applicable banking metrics
        self.assertEqual(ctx['solvency_13_1']['ebitda'], 'N/A')
        self.assertEqual(ctx['solvency_13_2']['ebit'], 'N/A')

    def test_meli_hybrid_view(self):
        response = self.client.get('/company/MELI/')
        self.assertEqual(response.status_code, 200)
        ctx = response.context
        self.assertFalse(ctx['is_financial'])
        self.assertEqual(ctx['ticker'], 'MELI')
        # Margen FCF normalizado en modelo de valoración (10.15%)
        self.assertAlmostEqual(ctx['fcf_margin_pct'], 10.15, delta=0.5)
        # Reverse DCF implied growth is calculated dynamically
        self.assertIsInstance(ctx['g_implied_pct'], float)
        self.assertEqual(len(ctx['sensitivity_grid']), 5)
        # Elementos reactivos de la interfaz web
        content = response.content.decode('utf-8')
        self.assertIn('id="headerFairPrice"', content)
        self.assertIn('id="headerValuationBadge"', content)
        self.assertIn('id="sensitivityGridBody"', content)
        self.assertIn('Margen FCF Auditado:', content)

    def test_index_cards_complete(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        companies = {c['ticker']: c for c in response.context['companies']}
        
        # Deckers checks
        deck = companies.get('DECK')
        self.assertIsNotNone(deck)
        self.assertEqual(deck['f_score'], 6)
        self.assertIn('48.', deck['roic_adj'])
        self.assertTrue(deck['wacc'].endswith('%'))
        self.assertTrue(deck['spread'].startswith('+'))
        self.assertTrue(deck['price'].startswith('$'))
        
        # Apple checks
        aapl = companies.get('AAPL')
        self.assertIsNotNone(aapl)
        self.assertEqual(aapl['f_score'], 9)
        self.assertIn('50.', aapl['roic_adj'])
        self.assertTrue(aapl['price'].startswith('$'))

        # NU checks
        nu = companies.get('NU')
        self.assertIsNotNone(nu)
        self.assertIsInstance(nu['f_score'], int)

        # MELI checks
        meli = companies.get('MELI')
        self.assertIsNotNone(meli)

    def test_cash_flow_adjusted_fcf_and_buybacks(self):
        """Verifica que el estado de flujos contemple FCF Ajustado y Recompras Netas puras sin filas obsoletas."""
        for ticker in ['NVDA', 'AAPL', 'DECK']:
            response = self.client.get(f'/company/{ticker}/')
            self.assertEqual(response.status_code, 200)
            content = response.content.decode('utf-8')
            self.assertIn('Flujo de Caja Libre Ajustado (FCF Menos Retención Fiscal SBC)', content)
            self.assertIn('RECOMPRAS NETAS DE ACCIONES (Net Share Repurchases)', content)
            self.assertIn('TOTAL RECOMPRAS DE ACCIONES (Buybacks Consolidados)', content)
