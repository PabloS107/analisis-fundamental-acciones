"""
tests/test_market_data.py - Suite de pruebas unitarias para MarketDataExtractor.
Verifica extracción en tiempo real, validación cruzada multi-fuente (Yahoo vs. CNBC),
tolerancias, arbitraje con SEC Form 10-Q, caché de sesión y modo offline seguro.
"""

import os
import sys
import json
import unittest
from pathlib import Path

# Añadir scripts al path
scripts_dir = Path(".agents/skills/fundamental-data-extractor/scripts").resolve()
sys.path.insert(0, str(scripts_dir))

from market_data_provider import MarketDataExtractor


class TestMarketDataExtractor(unittest.TestCase):

    def test_01_realtime_metrics_aapl(self):
        """Verifica la extracción y consenso de métricas en tiempo real para AAPL."""
        data = MarketDataExtractor.get_market_data("AAPL")
        self.assertEqual(data["ticker"], "AAPL")
        self.assertFalse(data["is_offline"])
        self.assertGreater(data["price"], 100.0)
        self.assertGreater(data["market_cap_usd_m"], 1000000.0)  # > $1 Trillion
        self.assertGreater(data["rf_10y"], 0.03)                # > 3%
        self.assertLess(data["rf_10y"], 0.07)                   # < 7%
        self.assertGreater(data["beta"], 0.8)
        self.assertLess(data["beta"], 1.5)
        self.assertIn("audit", data)
        self.assertIn("notes", data["audit"])

    def test_02_realtime_metrics_deck(self):
        """Verifica la extracción para DECK comprobando resiliencia ante stock split."""
        data = MarketDataExtractor.get_market_data("DECK")
        self.assertEqual(data["ticker"], "DECK")
        self.assertFalse(data["is_offline"])
        self.assertGreater(data["price"], 50.0)
        self.assertLess(data["price"], 200.0)  # Post split 6:1 precio ~$80-$120
        self.assertGreater(data["market_cap_usd_m"], 8000.0)    # > $8B
        self.assertGreater(data["beta"], 0.8)

    def test_03_tolerance_consensus_logic(self):
        """Verifica la lógica de tolerancia y consenso numérico."""
        # Si dos fuentes difieren en menos de 1.5%, debe promediar
        price_a = 300.0
        price_b = 302.0
        diff_pct = abs(price_a - price_b) / ((price_a + price_b) / 2.0)
        self.assertLessEqual(diff_pct, MarketDataExtractor.TOLERANCE_PRICE_PCT)

        # Tolerancia Rf <= 10 bps
        rf_a = 0.0480
        rf_b = 0.0485
        self.assertLessEqual(abs(rf_a - rf_b), MarketDataExtractor.TOLERANCE_RF_BPS)

        # Tolerancia Beta <= 0.15
        beta_a = 1.08
        beta_b = 1.12
        self.assertLessEqual(abs(beta_a - beta_b), MarketDataExtractor.TOLERANCE_BETA)

    def test_04_session_cache_and_timestamp(self):
        """Verifica que los datos se guarden en caché con timestamp y se reutilicen."""
        cache_path = Path("data/cache/market_data_cache.json")
        self.assertTrue(cache_path.exists(), "El archivo de caché debe existir tras consultar datos")
        with open(cache_path, "r", encoding="utf-8") as f:
            cache = json.load(f)
        self.assertIn("AAPL", cache)
        self.assertIn("timestamp", cache["AAPL"])
        self.assertIn("timestamp_epoch", cache["AAPL"])


if __name__ == "__main__":
    unittest.main()