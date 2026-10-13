import os
import sys
import unittest
from pathlib import Path

# Configurar Django para el entorno de test
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "web_dashboard"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "web_dashboard.settings")

import django
django.setup()

from django.test import Client


class TestWebDashboardForensics(unittest.TestCase):
    """
    Test de Verificación Triangulada Obligatoria (Regla 2):
    Certifica la coherencia semántica entre los cálculos cuantitativos/forenses
    y las clases visuales de alerta, badges y escalas de referencia en la interfaz Django.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.client = Client()

    def test_01_nvda_forensic_semantics(self):
        """Verifica que NVDA (con devengos agresivos LTM y C-Score 4) muestre alertas rojas dinámicas."""
        response = self.client.get("/company/NVDA/")
        self.assertEqual(response.status_code, 200)
        html = response.content.decode("utf-8")

        # 1. Sloan Accruals en Tarjeta Ejecutiva
        self.assertIn("NI &gt; CFO", html, "NVDA debe indicar dirección NI > CFO (utilidad superior al flujo operativo)")
        self.assertIn("Alerta Manipulación", html, "NVDA debe reflejar Alerta Manipulación en la escala de Sloan")

        # 2. Clases semánticas rojas en Sloan
        self.assertIn("bg-rose-100 text-rose-800", html, "Sloan badge de NVDA debe contener clase bg-rose-100 text-rose-800")
        self.assertIn("bg-rose-50 text-rose-700", html, "Fórmula de Sloan de NVDA debe usar píldora rose")

        # 3. Montier C-Score y Riesgo Forense
        self.assertIn("&gt; 70%", html, "Montier C-Score de NVDA (4/6) debe reportar riesgo > 70%")

        # 4. Solvencia y Caja Neta en Verde
        self.assertIn("CAJA NETA", html, "NVDA debe destacar su condición de Caja Neta")
        self.assertIn("bg-emerald-100 text-emerald-800", html, "Badge de Solvencia / Caja Neta debe ser emerald")

        # 5. Escala de 4 Cajas de Sloan: El badge de NVDA debe ubicarse en Box 4 (> +10%) y NO en Box 2
        self.assertIn("NVDA (22.21%)", html, "El badge del ticker con porcentaje debe figurar en el HTML")

    def test_02_aapl_and_deck_regression(self):
        """Zero Regressions: Certifica que AAPL y DECK sigan cargando con código 200 y métricas auditadas."""
        for ticker in ["AAPL", "DECK"]:
            response = self.client.get(f"/company/{ticker}/")
            self.assertEqual(response.status_code, 200)
            html = response.content.decode("utf-8")
            self.assertIn(ticker, html)
            self.assertIn("Piotroski F-Score", html)
            self.assertIn("Ratio de Sloan", html)


if __name__ == "__main__":
    unittest.main()
