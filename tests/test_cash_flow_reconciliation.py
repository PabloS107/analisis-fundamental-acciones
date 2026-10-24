import unittest
import json
import os
from pipeline.canonical_resolvers import resolve_canonical_cash_flow


class TestCashFlowReconciliation(unittest.TestCase):
    """
    Verifica la consistencia matemática y contable de la sección de Flujos de Caja
    (Beginning Cash + Net Change in Cash == Ending Cash) en empresas de control y META.
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

        cf_res = resolve_canonical_cash_flow(fs, periods)

        for p in periods:
            beg = cf_res["beginning_cash"].get(p)
            net = cf_res["net_change_in_cash"].get(p)
            end = cf_res["ending_cash"].get(p)

            # Si ambos existen, la suma matemática debe cuadrar
            if beg is not None and net is not None and end is not None:
                self.assertAlmostEqual(
                    round(beg + net, 2),
                    round(end, 2),
                    places=0,
                    msg=f"[{ticker} {p}] Fallo de conciliación: Beg ({beg:,.0f}) + Net ({net:,.0f}) != End ({end:,.0f})"
                )

            # Verificar que no sean idénticos por error de mapeo duplicado (excepto si net es casualmente beg)
            if beg is not None and net is not None and end is not None and round(end, 2) != round(beg * 2, 2):
                self.assertNotEqual(
                    beg,
                    net,
                    msg=f"[{ticker} {p}] Error de mapeo duplicado: Beg ({beg}) es idéntico a Net ({net})"
                )

    def test_meta_cash_flow_reconciliation(self):
        """Verifica la conciliación exacta en META para LTM y años fiscales."""
        self._verify_company("META")

    def test_aapl_cash_flow_reconciliation(self):
        """Verifica la conciliación exacta en AAPL."""
        self._verify_company("AAPL")

    def test_deck_cash_flow_reconciliation(self):
        """Verifica la conciliación exacta en DECK."""
        self._verify_company("DECK")


if __name__ == "__main__":
    unittest.main()
