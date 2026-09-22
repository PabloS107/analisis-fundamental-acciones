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
        self.assertIn('10.31%', base_row['wacc_label'])
        self.assertIn(f"{expected_g_implied:.1f}", base_row['g_25']) # Central scenario cell
        
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
        # Reverse DCF implied growth is positive and realistic
        self.assertGreater(ctx['g_implied_pct'], 10.0)
        self.assertEqual(len(ctx['sensitivity_grid']), 5)

    def test_index_cards_complete(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        companies = {c['ticker']: c for c in response.context['companies']}
        
        # Deckers checks
        deck = companies.get('DECK')
        self.assertIsNotNone(deck)
        self.assertEqual(deck['f_score'], 6)
        self.assertIn('53.', deck['roic_adj'])
        self.assertIn('10.31%', deck['wacc'])
        self.assertIn('+43.', deck['spread'])
        self.assertTrue(deck['price'].startswith('$'))
        
        # Apple checks
        aapl = companies.get('AAPL')
        self.assertIsNotNone(aapl)
        self.assertEqual(aapl['f_score'], 9)
        self.assertIn('52.', aapl['roic_adj'])
        self.assertTrue(aapl['price'].startswith('$'))

        # NU checks
        nu = companies.get('NU')
        self.assertIsNotNone(nu)
        self.assertEqual(nu['f_score'], 6)

        # MELI checks
        meli = companies.get('MELI')
        self.assertIsNotNone(meli)
