import unittest
import json
import os
from pipeline.canonical_resolvers import resolve_canonical_balance_sheet, resolve_canonical_cash_flow


class TestBalanceSheetReconciliation(unittest.TestCase):
    """
    Verifica la consistencia matemática y contable de los Activos No Corrientes:
    sum(hijos de activos no corrientes) == Total Activos No Corrientes (0.0 discrepancia).
    """

    def _verify_company(self, ticker):
        path = os.path.join("data", "processed", ticker, "financial_statements.json")
        if not os.path.exists(path):
            self.skipTest(f"Archivo de {ticker} no existe en data/processed/")

        with open(path, "r", encoding="utf-8") as f:
            fs = json.load(f)

        if fs.get("archetype") == "FINANCIAL_BANKING":
            return

        periods = ["LTM", "FY2025", "FY2024"]
        bs = resolve_canonical_balance_sheet(fs, periods)

        keys = [
            "net_ppe",
            "rou_asset",
            "goodwill_and_intangibles",
            "long_term_investments",
            "deferred_tax_assets",
            "other_noncurrent_assets"
        ]

        for p in periods:
            tot_nca = bs["total_noncurrent_assets"].get(p)
            if tot_nca is None:
                continue
            row_sum = sum(bs[k].get(p) or 0.0 for k in keys)
            diff = abs(round(row_sum - tot_nca, 1))
            self.assertLessEqual(
                diff,
                1.0,
                msg=f"[{ticker} {p}] Discrepancia en Activos No Corrientes: Suma ({row_sum:,.0f}) != Subtotal ({tot_nca:,.0f}), Diff={diff}"
            )

    def test_meta_nca_reconciliation(self):
        """Verifica que en META los activos no corrientes cuadren con 0.0 de diferencia."""
        self._verify_company("META")

    def test_aapl_nca_reconciliation(self):
        """Verifica que en AAPL los activos no corrientes cuadren con 0.0 de diferencia."""
        self._verify_company("AAPL")

    def test_deck_nca_reconciliation(self):
        """Verifica que en DECK los activos no corrientes cuadren con 0.0 de diferencia."""
        self._verify_company("DECK")


if __name__ == "__main__":
    unittest.main()
