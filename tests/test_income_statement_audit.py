import os
import sys
import unittest
import json

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, 'web_dashboard'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'web_dashboard.settings')

import django
django.setup()

from django.test import Client
from django.test.utils import setup_test_environment, teardown_test_environment

class TestIncomeStatementAudit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        setup_test_environment()

    @classmethod
    def tearDownClass(cls):
        teardown_test_environment()
        super().tearDownClass()

    def setUp(self):
        self.client = Client()
        self.tickers = ['AAPL', 'DECK', 'JPM', 'MELI', 'META', 'NU', 'NVDA', 'O', 'PGR']

    def test_all_companies_status_code_and_pnl_presence(self):
        """Verify all 9 companies load cleanly and have std_pnl populated."""
        for t in self.tickers:
            resp = self.client.get(f'/company/{t}/')
            self.assertEqual(resp.status_code, 200, f"Failed to load {t}")
            std_pnl = resp.context.get('std_pnl', [])
            self.assertTrue(len(std_pnl) > 0, f"std_pnl empty for {t}")
            
    def test_tax_benefit_display_integrity(self):
        """Verify that when tax is a benefit (crédito fiscal), it displays with '+' and reconciles EBT to NI."""
        # NVDA FY2023 had a tax benefit of $187M
        resp = self.client.get('/company/NVDA/')
        self.assertEqual(resp.status_code, 200)
        std_pnl = resp.context.get('std_pnl', [])
        fys = resp.context.get('statements_fys', [])
        fy23_idx = fys.index('FY2023') - 1 # cell index in annual_cells
        
        tax_row = next(r for r in std_pnl if 'Impuesto sobre Beneficios' in r.get('label', ''))
        tax_val = tax_row['annual_cells'][fy23_idx]['abs']
        self.assertTrue(tax_val.startswith('+$'), f"Expected positive benefit +$187.0M, got {tax_val}")

    def test_meli_associates_reconciliation(self):
        """Verify MELI associates equity method is extracted and reconciles Net Income."""
        resp = self.client.get('/company/MELI/')
        self.assertEqual(resp.status_code, 200)
        std_pnl = resp.context.get('std_pnl', [])
        fys = resp.context.get('statements_fys', [])
        fy23_idx = fys.index('FY2023') - 1
        
        assoc_row = next((r for r in std_pnl if 'Asociadas' in r.get('label', '')), None)
        self.assertIsNotNone(assoc_row, "Associates row should be present for MELI")
        self.assertEqual(assoc_row['annual_cells'][fy23_idx]['abs'], '$3.0M')

    def test_nvda_dps_populated_in_historical_years(self):
        """Verify NVDA DPS is populated in FY2020-FY2022 via cashflow fallback."""
        resp = self.client.get('/company/NVDA/')
        self.assertEqual(resp.status_code, 200)
        std_pnl = resp.context.get('std_pnl', [])
        fys = resp.context.get('statements_fys', [])
        
        dps_row = next(r for r in std_pnl if 'Dividendos por Acción (DPS)' in r.get('label', ''))
        for yr in ['FY2022', 'FY2021', 'FY2020']:
            idx = fys.index(yr) - 1
            val = dps_row['annual_cells'][idx]['abs']
            self.assertNotEqual(val, '-', f"NVDA DPS in {yr} should not be dash")
            self.assertTrue(val.startswith('$'), f"NVDA DPS in {yr} should be formatted: {val}")

if __name__ == '__main__':
    unittest.main()
