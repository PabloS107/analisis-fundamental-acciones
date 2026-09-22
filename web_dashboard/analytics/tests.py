from django.test import TestCase, Client

class ValuationAndSensitivityTests(TestCase):
    def setUp(self):
        self.client = Client()

    def test_deck_valuation_and_sensitivity(self):
        response = self.client.get('/company/DECK/')
        self.assertEqual(response.status_code, 200)
        ctx = response.context
        
        # Exact mathematical parity with Word report (.docx Section 14)
        self.assertAlmostEqual(ctx['g_implied_pct'], -3.7, delta=0.1)
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
        self.assertIn('-3.', base_row['g_25']) # Central scenario cell
        
        # HTML content verification
        content = response.content.decode('utf-8')
        self.assertIn('Matriz Bidimensional de Sensibilidad Reverse DCF', content)
        self.assertIn('ESCENARIO CENTRAL', content)
        self.assertIn('netDebt = -1602.60', content)

    def test_aapl_valuation_and_sensitivity(self):
        response = self.client.get('/company/AAPL/')
        self.assertEqual(response.status_code, 200)
        ctx = response.context
        
        # Exact parity for Apple (Section 14)
        self.assertAlmostEqual(ctx['g_implied_pct'], 16.0, delta=1.5)
        self.assertEqual(len(ctx['sensitivity_grid']), 5)
        self.assertTrue(ctx['sensitivity_grid'][2]['is_base'])

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
