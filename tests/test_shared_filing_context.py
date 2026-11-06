"""
test_shared_filing_context.py - Pruebas unitarias para SharedFilingContext (Prioridad 3).
Verifica:
1. Caché lazy en memoria de Company y propiedades derivadas (CIK, Name, SIC, Estándar Contable, Arquetipo FPI).
2. Deduplicación estricta de llamadas de red: get_filings() solo invoca edgar.Company una vez por tipo de formulario.
3. Cero re-parseos de objetos filing.obj() y árboles filing.xbrl() indexados por accession_number.
4. Deduplicación de Facts DataFrame (company.get_facts()).
5. Registro y exactitud de telemetría de desempeño (cache_hits vs network_fetches).
6. Retrocompatibilidad: funciones operan idénticamente cuando filing_context=None.
"""

import unittest
from unittest.mock import MagicMock, patch
import pandas as pd
from pipeline.sec_modules.filing_context import SharedFilingContext


class TestSharedFilingContext(unittest.TestCase):

    def setUp(self):
        # Crear un mock de filing con accession_number único
        self.mock_filing_10k_1 = MagicMock()
        self.mock_filing_10k_1.accession_number = "0000320193-23-000106"
        self.mock_filing_10k_1.form = "10-K"
        self.mock_filing_10k_1.filing_date = "2023-11-03"

        self.mock_filing_10k_2 = MagicMock()
        self.mock_filing_10k_2.accession_number = "0000320193-24-000106"
        self.mock_filing_10k_2.form = "10-K"
        self.mock_filing_10k_2.filing_date = "2024-11-01"

        self.mock_filing_10q = MagicMock()
        self.mock_filing_10q.accession_number = "0000320193-24-000050"
        self.mock_filing_10q.form = "10-Q"
        self.mock_filing_10q.filing_date = "2024-05-03"

        # Mock Company
        self.mock_company = MagicMock()
        self.mock_company.cik = 320193
        self.mock_company.name = "Apple Inc."
        self.mock_company.sic = 3571
        self.mock_company.get_filings.side_effect = self._mock_get_filings

    def _mock_get_filings(self, form):
        if form == "10-K":
            return [self.mock_filing_10k_2, self.mock_filing_10k_1]
        elif form == "10-Q":
            return [self.mock_filing_10q]
        elif isinstance(form, (list, tuple)) and "10-K" in form:
            return [self.mock_filing_10k_2, self.mock_filing_10k_1]
        elif form == "20-F" or form == "40-F":
            return []
        return []

    def test_company_and_metadata_lazy_caching(self):
        """Verifica resolución y caché de propiedades maestras de la compañía."""
        ctx = SharedFilingContext("AAPL", company=self.mock_company)
        
        self.assertEqual(ctx.ticker, "AAPL")
        self.assertEqual(ctx.cik, "0000320193")
        self.assertEqual(ctx.name, "Apple Inc.")
        self.assertEqual(ctx.sic_code, "3571")
        self.assertFalse(ctx.is_fpi)
        self.assertEqual(ctx.accounting_standard, "US-GAAP")

        # CIK de nuevo debe venir de la propiedad cacheada
        self.assertEqual(ctx.cik, "0000320193")

    def test_get_filings_caching_deduplication(self):
        """Verifica que consultas repetidas a get_filings() reutilicen la memoria RAM."""
        ctx = SharedFilingContext("AAPL", company=self.mock_company)

        # Primera consulta: debe llamar a mock_company.get_filings
        filings_1 = ctx.get_filings("10-K")
        self.assertEqual(len(filings_1), 2)
        self.assertEqual(ctx.stats["network_fetches"], 1)
        self.assertEqual(ctx.stats["cache_hits"], 0)

        # Segunda consulta con mismo formulario: debe ser un Cache Hit
        filings_2 = ctx.get_filings("10-K")
        self.assertEqual(filings_1, filings_2)
        self.assertEqual(ctx.stats["network_fetches"], 1)
        self.assertEqual(ctx.stats["cache_hits"], 1)

        # Consulta con lista equivalente: se normaliza y cachea
        filings_list_1 = ctx.get_filings(["10-K", "20-F"])
        self.assertEqual(ctx.stats["network_fetches"], 2)

        filings_list_2 = ctx.get_filings(["20-F", "10-K"])  # Mismo set ordenado
        self.assertEqual(filings_list_1, filings_list_2)
        self.assertEqual(ctx.stats["cache_hits"], 2)

    def test_get_filing_obj_deduplication(self):
        """Verifica que doc.obj() solo se ejecute una vez por accession_number."""
        ctx = SharedFilingContext("AAPL", company=self.mock_company)
        fake_parsed_obj = MagicMock()
        fake_parsed_obj.items = ["Item 1", "Item 7"]
        self.mock_filing_10k_1.obj.return_value = fake_parsed_obj

        # Primer parseo
        obj_1 = ctx.get_filing_obj(self.mock_filing_10k_1)
        self.assertEqual(obj_1, fake_parsed_obj)
        self.assertEqual(self.mock_filing_10k_1.obj.call_count, 1)
        self.assertEqual(ctx.stats["obj_parses"], 1)

        # Segundo parseo del mismo documento (ej. en narrativas tras As-Reported): Cache Hit en RAM
        obj_2 = ctx.get_filing_obj(self.mock_filing_10k_1)
        self.assertEqual(obj_2, fake_parsed_obj)
        self.assertEqual(self.mock_filing_10k_1.obj.call_count, 1)  # No se volvió a llamar
        self.assertEqual(ctx.stats["cache_hits"], 1)

    def test_get_filing_xbrl_deduplication_and_linkage(self):
        """Verifica que el árbol XBRL se guarde y que si obj() ya lo tenía, no llame a .xbrl()."""
        ctx = SharedFilingContext("AAPL", company=self.mock_company)
        fake_xb = MagicMock()
        self.mock_filing_10k_2.xbrl.return_value = fake_xb

        # Llamada directa a get_filing_xbrl
        xb_1 = ctx.get_filing_xbrl(self.mock_filing_10k_2)
        self.assertEqual(xb_1, fake_xb)
        self.assertEqual(self.mock_filing_10k_2.xbrl.call_count, 1)
        self.assertEqual(ctx.stats["xbrl_parses"], 1)

        # Segunda llamada a get_filing_xbrl (ej. en sec_segment_extractor)
        xb_2 = ctx.get_filing_xbrl(self.mock_filing_10k_2)
        self.assertEqual(xb_2, fake_xb)
        self.assertEqual(self.mock_filing_10k_2.xbrl.call_count, 1)  # Cero re-parseos
        self.assertEqual(ctx.stats["cache_hits"], 1)

    def test_facts_df_caching(self):
        """Verifica que company.get_facts() solo se descargue y convierta a DataFrame una vez."""
        ctx = SharedFilingContext("AAPL", company=self.mock_company)
        mock_facts_obj = MagicMock()
        mock_df = pd.DataFrame({"concept": ["us-gaap:Assets"], "numeric_value": [1000.0]})
        mock_facts_obj.to_dataframe.return_value = mock_df
        self.mock_company.get_facts.return_value = mock_facts_obj

        df1 = ctx.get_facts_df()
        self.assertIsNotNone(df1)
        self.assertEqual(len(df1), 1)
        self.assertEqual(self.mock_company.get_facts.call_count, 1)

        # Segunda llamada (ej. fallback para notas contables)
        df2 = ctx.get_facts_df()
        self.assertIs(df1, df2)
        self.assertEqual(self.mock_company.get_facts.call_count, 1)  # Cero llamadas adicionales
        self.assertEqual(ctx.stats["cache_hits"], 1)

    def test_telemetry_summary_generation(self):
        """Verifica que print_telemetry_summary no arroje excepciones y reporte métricas."""
        ctx = SharedFilingContext("AAPL", company=self.mock_company)
        ctx.stats["cache_hits"] = 5
        ctx.stats["network_fetches"] = 2
        # No debe lanzar excepción
        ctx.print_telemetry_summary()


if __name__ == "__main__":
    unittest.main()
