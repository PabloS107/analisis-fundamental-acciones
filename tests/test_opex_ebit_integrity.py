import unittest
import json
from pathlib import Path
import sys

# Ensure web_dashboard is in path
sys.path.insert(0, str(Path(__file__).parent.parent / "web_dashboard"))
from analytics.views import resolve_canonical_income_statement


class TestOpExAndEBITIntegrity(unittest.TestCase):
    """
    Test suite de integridad matemática contable y fidelidad al Estado de Resultados publicado (Regla 2).
    Verifica que:
    1. Para arquetipos corporativos (AAPL, DECK, META, NVDA, MELI), la suma de las partidas visibles de OpEx
       coincida exactamente con Total OpEx reportado.
    2. Gross Profit - Total OpEx coincida exactamente con Operating Income (EBIT).
    3. Si una empresa no desglosa I+D en su carátula contable (ej. DECK), I+D no figure como partida restadora en el Estado de Resultados.
    4. En fintechs/plataformas con provisión crediticia (ej. MELI), dicha provisión no se duplique como 'Otros Gastos Operativos'.
    5. En entidades bancarias (JPM, NU), no se impute un EBIT corporativo tradicional artificial.
    """

    def setUp(self):
        self.proc_dir = Path(__file__).parent.parent / "data" / "processed"

    def test_deck_opex_integrity(self):
        p = self.proc_dir / "DECK" / "financial_statements.json"
        self.assertTrue(p.exists(), "DECK financial_statements.json debe existir")
        with open(p, "r", encoding="utf-8") as f:
            fs = json.load(f)
        fys = fs.get("fiscal_years", [])
        pnl = resolve_canonical_income_statement(fs, fys, archetype="STANDARD_CORPORATE")

        for period in ["FY2026", "FY2025", "FY2024"]:
            if period not in fys:
                continue
            rd = pnl["rd_expense"].get(period)
            sga = pnl["sga_expense"].get(period)
            tot_opex = pnl["total_operating_expenses"].get(period)
            ebit = pnl["operating_income"].get(period)
            gp = pnl["gross_profit"].get(period)

            # En DECK, I+D está en notas y consolidado en SG&A; no debe figurar en el P&L
            self.assertIsNone(rd, f"DECK {period}: rd_expense debe ser None en P&L para no romper la cascada")
            self.assertIsNotNone(sga, f"DECK {period}: sga_expense debe existir")
            self.assertIsNotNone(tot_opex, f"DECK {period}: total_operating_expenses debe existir")
            self.assertAlmostEqual(sga, tot_opex, delta=1.0, msg=f"DECK {period}: SG&A debe ser igual a Total OpEx")

            # Identidad Gross Profit - OpEx == EBIT
            self.assertAlmostEqual(gp - tot_opex, ebit, delta=1.0, msg=f"DECK {period}: GP - OpEx debe ser igual a EBIT")

    def test_meli_opex_no_duplicate_provision(self):
        p = self.proc_dir / "MELI" / "financial_statements.json"
        self.assertTrue(p.exists(), "MELI financial_statements.json debe existir")
        with open(p, "r", encoding="utf-8") as f:
            fs = json.load(f)
        fys = fs.get("fiscal_years", [])
        pnl = resolve_canonical_income_statement(fs, fys, archetype="PLATFORM_ECOSYSTEM")

        for period in ["FY2025", "FY2024"]:
            if period not in fys:
                continue
            rd = pnl["rd_expense"].get(period)
            sga = pnl["sga_expense"].get(period)
            clp = pnl["credit_loss_provision"].get(period)
            other = pnl["other_operating_expense"].get(period)
            tot_opex = pnl["total_operating_expenses"].get(period)
            ebit = pnl["operating_income"].get(period)
            gp = pnl["gross_profit"].get(period)

            # MELI no tiene otros gastos operativos huérfanos que dupliquen la provisión
            self.assertIsNone(other, f"MELI {period}: other_operating_expense no debe duplicar la provisión crediticia")
            comp_sum = (rd or 0.0) + (sga or 0.0) + (clp or 0.0) + (other or 0.0)
            self.assertAlmostEqual(comp_sum, tot_opex, delta=1.0, msg=f"MELI {period}: Suma de componentes debe igualar Total OpEx")
            self.assertAlmostEqual(gp - tot_opex, ebit, delta=1.0, msg=f"MELI {period}: GP - OpEx debe ser igual a EBIT")

    def test_corporate_control_companies_integrity(self):
        for ticker in ["AAPL", "META", "NVDA"]:
            p = self.proc_dir / ticker / "financial_statements.json"
            self.assertTrue(p.exists(), f"{ticker} financial_statements.json debe existir")
            with open(p, "r", encoding="utf-8") as f:
                fs = json.load(f)
            fys = fs.get("fiscal_years", [])
            pnl = resolve_canonical_income_statement(fs, fys, archetype="STANDARD_CORPORATE")

            for period in ["FY2025", "FY2024"]:
                if period not in fys:
                    continue
                rd = pnl["rd_expense"].get(period)
                sga = pnl["sga_expense"].get(period)
                other = pnl["other_operating_expense"].get(period)
                tot_opex = pnl["total_operating_expenses"].get(period)
                ebit = pnl["operating_income"].get(period)
                gp = pnl["gross_profit"].get(period)

                self.assertIsNotNone(rd, f"{ticker} {period}: Debe tener I+D en carátula")
                self.assertIsNotNone(sga, f"{ticker} {period}: Debe tener SG&A en carátula")
                comp_sum = (rd or 0.0) + (sga or 0.0) + (other or 0.0)
                self.assertAlmostEqual(comp_sum, tot_opex, delta=1.0, msg=f"{ticker} {period}: Suma OpEx mismatch")
                self.assertAlmostEqual(gp - tot_opex, ebit, delta=1.0, msg=f"{ticker} {period}: GP - OpEx != EBIT")

    def test_banking_no_artificial_ebit(self):
        for ticker in ["JPM", "NU"]:
            p = self.proc_dir / ticker / "financial_statements.json"
            if not p.exists():
                continue
            with open(p, "r", encoding="utf-8") as f:
                fs = json.load(f)
            fys = fs.get("fiscal_years", [])
            pnl = resolve_canonical_income_statement(fs, fys, archetype="FINANCIAL_BANKING")

            for period in fys:
                ebit = pnl["operating_income"].get(period)
                self.assertIsNone(ebit, f"{ticker} {period}: En entidades bancarias no se debe imputar EBIT corporativo")


if __name__ == "__main__":
    unittest.main()
