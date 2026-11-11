# -*- coding: utf-8 -*-
"""
tests/test_web_valuation.py - Verificación de Renderizado Web Django para la Super Pestaña de Valoración:
- Selector Maestro Dual Lens (GAAP vs Económico Moderno / Owner Earnings)
- Radiografía Forense de CapEx (Mantenimiento vs Crecimiento) y Owner Earnings (Buffett-Greenwald)
- Bandas de Valoración Dinámica Z-Score (EV / NOPAT Ajustado)
- Cajón de Trazabilidad y Caja Blanca (10-K Audit Traceability Drawer)
- Aislamiento prudencial de arquetipos financieros (NU) sin regresiones
"""
import os
import sys
import unittest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for _p in (ROOT_DIR, os.path.join(ROOT_DIR, 'pipeline'), os.path.join(ROOT_DIR, 'web_dashboard')):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import pipeline  # noqa: E402, F401
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'web_dashboard.settings')

import django
django.setup()

from django.test import Client
from django.test.utils import setup_test_environment, teardown_test_environment


class TestWebValuationSuperTab(unittest.TestCase):
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

    def test_01_aapl_valuation_super_tab_rendering(self):
        """Verifica que para AAPL se rendericen todos los componentes de la Super Pestaña de Valoración."""
        response = self.client.get('/company/AAPL/')
        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')

        # 1. Selector Maestro Dual Lens
        self.assertIn('Dual Valuation Engine', content)
        self.assertIn('btnLensGAAP', content)
        self.assertIn('btnLensOE', content)
        self.assertIn('lensBoxMargin', content)
        self.assertIn('lensBoxGImplied', content)
        self.assertIn('lensBoxFairPrice', content)

        # 2. Radiografía Forense del CapEx & Owner Earnings
        self.assertIn('Radiografía Forense del CapEx & Owner Earnings', content)
        self.assertIn('CapEx de Mantenimiento', content)
        self.assertIn('CapEx de Crecimiento', content)
        self.assertIn('Beneficios del Propietario', content)
        self.assertIn('btnDcfBaseOE', content)
        self.assertIn('btnDcfBaseFCF', content)

        # 3. Múltiplos Históricos y Reversión a la Media con Chart.js
        self.assertIn('Múltiplos Históricos y Reversión a la Media', content)
        self.assertIn('historicalMultiplesChart', content)
        self.assertIn('statCurrentMultiple', content)
        self.assertIn('statMedianMultiple', content)
        self.assertIn('chkRefMedian', content)

        # 4. Cajón de Trazabilidad y Caja Blanca con KaTeX y Cifras Reales
        self.assertIn('Trazabilidad y Caja Blanca: Conciliación Contable de Datos Auditados (SEC 10-K)', content)
        self.assertIn('Paso 1: Reconstrucción del NOPAT Económico Ajustado', content)
        self.assertIn('Paso 2: Conciliación de Owner Earnings', content)
        self.assertIn('Paso 3: Inventario Histórico Multianual de I+D', content)
        self.assertIn('Identidades Contables Universales y Conciliación Numérica Auditada', content)
        self.assertIn('katex', content.lower())

    def test_02_deck_valuation_super_tab_rendering(self):
        """Verifica que para DECK se renderice la Super Pestaña sin errores ni regresiones."""
        response = self.client.get('/company/DECK/')
        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')

        self.assertIn('Dual Valuation Engine', content)
        self.assertIn('Radiografía Forense del CapEx & Owner Earnings', content)
        self.assertIn('Múltiplos Históricos y Reversión a la Media', content)
        self.assertIn('Trazabilidad y Caja Blanca', content)

    def test_03_nu_banking_valuation_isolation(self):
        """Verifica que para bancos (NU) el arquetipo financiero se preserve limpiamente sin errores."""
        response = self.client.get('/company/NU/')
        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')

        # En bancos no debe mostrarse el selector corporativo de Dual Engine ni Owner Earnings
        self.assertNotIn('Dual Valuation Engine', content)
        self.assertNotIn('Radiografía Forense del CapEx', content)
        self.assertIn('P / TBV (Tangible Book)', content)

        # Debe mostrarse el protocolo de transparencia financiera
        self.assertIn('Protocolo de Transparencia para Arquetipo Financiero', content)
        # Y debe preservarse el modelo de Excess Return bancario (P/TBV y ROTCE)
        self.assertIn('ROTCE Sostenible', content)
        self.assertIn('Excess Return', content)


if __name__ == '__main__':
    unittest.main()
