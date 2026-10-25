# -*- coding: utf-8 -*-
import unittest
import json
import os
from pipeline.canonical_resolvers import resolve_canonical_cash_flow


class TestCashFlowReconciliation(unittest.TestCase):
    """
    Verifica la consistencia matemática y contable de la sección de Flujos de Caja
    (Beginning Cash + Net Change in Cash == Ending Cash) en empresas de control y todos los sectores,
    tanto dinámicamente como en los datos persistidos consumidos por la web.
    """

    def _verify_company(self, ticker):
        path = os.path.join("data", "processed", ticker, "financial_statements.json")
        if not os.path.exists(path):
            self.skipTest(f"Archivo de {ticker} no existe en data/processed/")

        with open(path, "r", encoding="utf-8") as f:
            fs = json.load(f)

        periods = fs.get("fiscal_years", [])
        if "LTM" not in periods:
            periods = ["LTM"] + periods

        # 1. Verificación del cálculo dinámico
        cf_res = resolve_canonical_cash_flow(fs, periods)

        # 2. Verificación de los datos persistidos en disco (que consume la web Django)
        cf_stored = fs.get("resolved_canonical_statements", {}).get("cash_flow", {})

        for src_name, cf_data in [("Dinámico", cf_res), ("Persistido Web", cf_stored)]:
            if not cf_data:
                continue
            for p in periods:
                beg = cf_data.get("beginning_cash", {}).get(p)
                net = cf_data.get("net_change_in_cash", {}).get(p)
                end = cf_data.get("ending_cash", {}).get(p)

                # Si existen las 3 magnitudes, la suma matemática debe cuadrar
                if beg is not None and net is not None and end is not None:
                    self.assertAlmostEqual(
                        round(beg + net, 1),
                        round(end, 1),
                        places=0,
                        msg=f"[{ticker} {p} - {src_name}] Fallo de conciliación: Beg ({beg:,.0f}) + Net ({net:,.0f}) != End ({end:,.0f})"
                    )

                # Verificar que no sean idénticos por error de mapeo duplicado (excepto si net es casualmente beg)
                if beg is not None and net is not None and end is not None and round(end, 2) != round(beg * 2, 2):
                    self.assertNotEqual(
                        beg,
                        net,
                        msg=f"[{ticker} {p} - {src_name}] Error de mapeo duplicado: Beg ({beg}) es idéntico a Net ({net})"
                    )

    def test_meta_cash_flow_reconciliation(self):
        """Verifica la conciliación exacta en META."""
        self._verify_company("META")

    def test_aapl_cash_flow_reconciliation(self):
        """Verifica la conciliación exacta en AAPL."""
        self._verify_company("AAPL")

    def test_deck_cash_flow_reconciliation(self):
        """Verifica la conciliación exacta en DECK."""
        self._verify_company("DECK")

    def test_nvda_cash_flow_reconciliation(self):
        """Verifica la conciliación exacta en NVDA."""
        self._verify_company("NVDA")

    def test_jpm_banking_cash_flow_reconciliation(self):
        """Verifica la conciliación exacta en JPM (Banca)."""
        self._verify_company("JPM")

    def test_meli_platform_cash_flow_reconciliation(self):
        """Verifica la conciliación exacta en MELI (Fintech / E-Commerce)."""
        self._verify_company("MELI")

    def test_o_reit_cash_flow_reconciliation(self):
        """Verifica la conciliación exacta en O (Inmobiliario REIT)."""
        self._verify_company("O")

    def test_pgr_insurance_cash_flow_reconciliation(self):
        """Verifica la conciliación exacta en PGR (Asegurador)."""
        self._verify_company("PGR")


if __name__ == "__main__":
    unittest.main()
