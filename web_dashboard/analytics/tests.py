from django.test import TestCase, Client

class ValuationAndSensitivityTests(TestCase):
    def setUp(self):
        self.client = Client()

    def test_deck_valuation_and_sensitivity(self):
        response = self.client.get('/company/DECK/')
        self.assertEqual(response.status_code, 200)
        ctx = response.context
        
        # Parity with dynamic valuation engine
        expected_g_implied = ctx['vp']['g_implied_our_pct']
        self.assertAlmostEqual(ctx['g_implied_pct'], expected_g_implied, delta=0.01)
        self.assertAlmostEqual(ctx['fcf_margin_pct'], ctx['vp'].get('fcf_margin_reported_pct', 18.87), delta=0.5)
        self.assertEqual(ctx['net_debt_m'], ctx['vp'].get('net_debt_m', -1209.7))
        self.assertAlmostEqual(ctx['rev_base'], ctx['vp'].get('rev_base_m', 5577.0), delta=1.0)
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
        self.assertIn(f"netDebt = {ctx['net_debt_m']:.2f}", content)

    def test_aapl_valuation_and_sensitivity(self):
        response = self.client.get('/company/AAPL/')
        self.assertEqual(response.status_code, 200)
        ctx = response.context
        
        # Dynamic exact parity for Apple calculated automatically
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
        self.assertIsInstance(deck['f_score'], int)
        self.assertTrue(deck['roic_adj'].endswith('%'))
        self.assertTrue(deck['wacc'].endswith('%'))
        self.assertTrue(deck['spread'].startswith('+'))
        self.assertTrue(deck['price'].startswith('$'))
        
        # Apple checks
        aapl = companies.get('AAPL')
        self.assertIsNotNone(aapl)
        self.assertIsInstance(aapl['f_score'], int)
        self.assertTrue(aapl['roic_adj'].endswith('%'))
        self.assertTrue(aapl['price'].startswith('$'))

        # NU checks
        nu = companies.get('NU')
        self.assertIsNotNone(nu)
        self.assertIsInstance(nu['f_score'], int)

        # MELI checks
        meli = companies.get('MELI')
        self.assertIsNotNone(meli)

    def test_cash_flow_adjusted_fcf_and_buybacks(self):
        """Verifica que el estado de flujos contemple FCF y Recompras en mercado abierto."""
        for ticker in ['NVDA', 'AAPL', 'DECK']:
            response = self.client.get(f'/company/{ticker}/')
            self.assertEqual(response.status_code, 200)
            content = response.content.decode('utf-8')
            self.assertIn('Flujo de Caja Libre (FCF)', content)
            self.assertIn('Recompra de Acciones en Mercado Abierto (Buybacks)', content)
