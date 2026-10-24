"""
test_sec_freshness.py - Pruebas Unitarias del Motor de Frescura SEC y Sincronización LTM.

Verifica:
1. Derivación estandarizada de etiquetas de período (10-Q, 10-K, 20-F).
2. Salvaguarda 1: Retrocompatibilidad total con JSONs existentes sin sec_metadata.
3. Salvaguarda 2: Filtro de formularios 6-K en emisores extranjeros (NU) evitando falsos positivos.
4. Salvaguarda 3: Caché de 15 minutos en el endpoint web de Django /api/sec-freshness/<ticker>/.
5. Regla 2 (Zero Regressions) en empresas de control (DECK, META, NU).
"""

import os
import sys
import time
import json
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
WEB_DASHBOARD_DIR = PROJECT_ROOT / "web_dashboard"
if str(WEB_DASHBOARD_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_DASHBOARD_DIR))

from pipeline.sec_modules.sec_freshness import (
    derive_period_label,
    get_local_sec_metadata,
    _is_valid_periodic_filing,
    check_sec_freshness,
)


class DummyFiling:
    def __init__(self, form, is_xbrl=0, primary_document="doc.htm", filing_date="2026-08-01"):
        self.form = form
        self.is_xbrl = is_xbrl
        self.primary_document = primary_document
        self.filing_date = filing_date


class TestSECFreshnessEngine(unittest.TestCase):

    def test_01_derive_period_label(self):
        """Verifica que las etiquetas de período contable se deriven con precisión."""
        self.assertEqual(derive_period_label("10-Q", "2026-03-31"), "Q1 2026")
        self.assertEqual(derive_period_label("10-Q", "2026-06-30"), "Q2 2026")
        self.assertEqual(derive_period_label("10-Q", "2026-09-30"), "Q3 2026")
        self.assertEqual(derive_period_label("10-Q", "2026-12-31"), "Q4 2026")
        self.assertEqual(derive_period_label("10-K", "2025-12-31"), "FY2025")
        self.assertEqual(derive_period_label("20-F", "2025-12-31"), "FY2025")
        self.assertEqual(derive_period_label("10-Q", None, "2026-07-30"), "Q2 2026")
        self.assertEqual(derive_period_label("", None, ""), "LTM")

    def test_02_foreign_issuer_6k_safeguard(self):
        """Salvaguarda 2: 6-Ks genéricos son descartados; sólo 6-Ks contables o con XBRL califican."""
        f_generic = DummyFiling("6-K", is_xbrl=0, primary_document="press_release.htm")
        self.assertFalse(_is_valid_periodic_filing(f_generic))

        f_xbrl = DummyFiling("6-K", is_xbrl=1, primary_document="press_release.htm")
        self.assertTrue(_is_valid_periodic_filing(f_xbrl))

        f_nufs = DummyFiling("6-K", is_xbrl=0, primary_document="nufs-20260630.htm")
        self.assertTrue(_is_valid_periodic_filing(f_nufs))

        f_interim = DummyFiling("6-K", is_xbrl=0, primary_document="interim_financial_statements.htm")
        self.assertTrue(_is_valid_periodic_filing(f_interim))

        # 10-Q y 10-K siempre son válidos
        self.assertTrue(_is_valid_periodic_filing(DummyFiling("10-Q")))
        self.assertTrue(_is_valid_periodic_filing(DummyFiling("10-K")))
        self.assertTrue(_is_valid_periodic_filing(DummyFiling("20-F")))

    def test_03_legacy_json_retrocompatibility(self):
        """Salvaguarda 1: JSONs existentes sin sec_metadata no fallan ni muestran N/D."""
        meta_local = get_local_sec_metadata("META")
        self.assertTrue(meta_local["has_local_data"])
        self.assertIsNotNone(meta_local["ltm_period"])
        self.assertNotEqual(meta_local["ltm_period"], "N/D")
        self.assertIsNotNone(meta_local["extraction_timestamp"])

        deck_local = get_local_sec_metadata("DECK")
        self.assertTrue(deck_local["has_local_data"])
        self.assertIsNotNone(deck_local["ltm_period"])
        self.assertNotEqual(deck_local["ltm_period"], "N/D")

        nu_local = get_local_sec_metadata("NU")
        self.assertTrue(nu_local["has_local_data"])
        self.assertIsNotNone(nu_local["ltm_period"])

    def test_04_meta_detects_new_quarter_in_sec(self):
        """Verifica que para META se detecte Q3 2026 en SEC frente al Q2 local."""
        res = check_sec_freshness("META", force_network=True)
        self.assertFalse(res["is_fresh"])
        self.assertTrue(res["has_newer_filing"])
        self.assertEqual(res["status"], "NEW_PERIODIC_AVAILABLE")
        self.assertEqual(res["local_ltm_period"], "Q2 2026")
        self.assertEqual(res["sec_latest_period"], "Q3 2026")
        self.assertEqual(res["sec_latest_form"], "10-Q")
        self.assertEqual(res["sec_latest_filing_date"], "2026-10-22")

    def test_05_deck_and_nu_controls(self):
        """Verifica empresas de control: DECK alerta de 8-K pendiente y NU se mantiene al día."""
        deck_res = check_sec_freshness("DECK", force_network=True)
        self.assertTrue(deck_res["is_fresh"])
        self.assertFalse(deck_res["has_newer_filing"])
        # DECK tiene un 8-K con Item 2.02 presentado el 22/10/2026
        self.assertTrue(deck_res["has_pending_8k"])
        self.assertEqual(deck_res["status"], "PENDING_8K_EARNINGS")

        nu_res = check_sec_freshness("NU", force_network=True)
        self.assertTrue(nu_res["is_fresh"])
        self.assertFalse(nu_res["has_newer_filing"])
        self.assertEqual(nu_res["status"], "UP_TO_DATE")

    def test_06_django_freshness_endpoint_cache(self):
        """Salvaguarda 3: Endpoint web /api/sec-freshness/<ticker>/ aplica caché de 15 minutos."""
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "web_dashboard.settings")
        import django
        django.setup()
        from django.test import RequestFactory
        from analytics.views.views import sec_freshness_view

        rf = RequestFactory()
        req = rf.get("/api/sec-freshness/META/")
        
        # Primera llamada (puebla la caché)
        t0 = time.time()
        resp1 = sec_freshness_view(req, "META")
        d1 = time.time() - t0
        self.assertEqual(resp1.status_code, 200)
        data1 = json.loads(resp1.content.decode("utf-8"))
        self.assertEqual(data1["ticker"], "META")

        # Segunda llamada (debe ser instantánea desde la caché en memoria)
        t0 = time.time()
        resp2 = sec_freshness_view(req, "META")
        d2 = time.time() - t0
        self.assertEqual(resp2.status_code, 200)
        self.assertLess(d2, 0.05, f"La respuesta cacheada tardó demasiado ({d2:.4f}s)")


if __name__ == "__main__":
    unittest.main()
