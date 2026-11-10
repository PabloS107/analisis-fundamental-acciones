"""
Tests unitarios para higiene XBRL multi-clase, aislamiento dimensional, ausencia de
FutureWarnings en pandas y normalización de arquetipos (Capa 1).
"""

import unittest
import warnings
from pathlib import Path
import sys

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from pipeline.entity_classifier import normalize_archetype
from pipeline.sec_modules.sec_xbrl_ltm import (
    _append_rows_safely,
    dataframe_to_concept_dict,
    merge_annual_statement_df,
    sanitize_multiclass_eps_df,
)


class TestMulticlassEpsAndXbrlHygiene(unittest.TestCase):
    """Valida correcciones raíz de Capa 1 sobre XBRL multi-clase, dimensiones y pandas."""

    def test_sanitize_multiclass_eps_unequal_classes_prioritizes_ab(self):
        """Reemplaza la suma artificial de ejes StatementClassOfStockAxis (4x) por Class A/B."""
        df = pd.DataFrame(
            [
                {
                    "concept": "us-gaap_EarningsPerShareDiluted",
                    "label": "Diluted earnings per share",
                    "dimension": False,
                    "dimension_axis": "",
                    "2015-12-31 (FY)": 92.86,
                    "2016-12-31 (FY)": 27.85,
                },
                {
                    "concept": "us-gaap_EarningsPerShareDiluted",
                    "label": "Class C Capital Stock [Member]",
                    "dimension": True,
                    "dimension_axis": "us-gaap:StatementClassOfStockAxis",
                    "2015-12-31 (FY)": 24.34,
                    "2016-12-31 (FY)": 27.85,
                },
                {
                    "concept": "us-gaap_EarningsPerShareDiluted",
                    "label": "Class A and Class B Common Stock [Member]",
                    "dimension": True,
                    "dimension_axis": "us-gaap:StatementClassOfStockAxis",
                    "2015-12-31 (FY)": 22.84,
                    "2016-12-31 (FY)": 27.85,
                },
                {
                    "concept": "us-gaap_EarningsPerShareDiluted",
                    "label": "Class A Common Stock [Member]",
                    "dimension": True,
                    "dimension_axis": "us-gaap:StatementClassOfStockAxis",
                    "2015-12-31 (FY)": 22.84,
                    "2016-12-31 (FY)": None,
                },
                {
                    "concept": "us-gaap_EarningsPerShareDiluted",
                    "label": "Class B Common Stock [Member]",
                    "dimension": True,
                    "dimension_axis": "us-gaap:StatementClassOfStockAxis",
                    "2015-12-31 (FY)": 22.84,
                    "2016-12-31 (FY)": None,
                },
            ]
        )

        cleaned = sanitize_multiclass_eps_df(df)
        parent = cleaned[cleaned["dimension"] == False].iloc[0]
        self.assertAlmostEqual(float(parent["2015-12-31 (FY)"]), 22.84, places=2)
        # 2016 no suma (27.85 + 27.85 = 55.70 != 27.85), debe preservarse intacto
        self.assertAlmostEqual(float(parent["2016-12-31 (FY)"]), 27.85, places=2)

    def test_sanitize_multiclass_eps_preserves_valid_and_equal_classes(self):
        """Preserva EPS válidos consolidados y corrige sumas 2x de clases simétricas."""
        df = pd.DataFrame(
            [
                {
                    "concept": "us-gaap_EarningsPerShareBasic",
                    "label": "Basic EPS",
                    "dimension": False,
                    "2024-12-31 (FY)": 10.00,
                    "2023-12-31 (FY)": 10.81,
                },
                {
                    "concept": "us-gaap_EarningsPerShareBasic",
                    "label": "Common Class A [Member]",
                    "dimension": True,
                    "2024-12-31 (FY)": 5.00,
                    "2023-12-31 (FY)": 10.81,
                },
                {
                    "concept": "us-gaap_EarningsPerShareBasic",
                    "label": "Common Class B [Member]",
                    "dimension": True,
                    "2024-12-31 (FY)": 5.00,
                    "2023-12-31 (FY)": None,
                },
            ]
        )
        cleaned = sanitize_multiclass_eps_df(df)
        parent = cleaned[cleaned["dimension"] == False].iloc[0]
        self.assertAlmostEqual(float(parent["2024-12-31 (FY)"]), 5.00, places=2)
        self.assertAlmostEqual(float(parent["2023-12-31 (FY)"]), 10.81, places=2)
        self.assertIsNone(sanitize_multiclass_eps_df(None))

    def test_dimensional_rows_cannot_overwrite_consolidated_concepts(self):
        """Filas dimensionales no sobrescriben totales consolidados en extracto ni merge."""
        df = pd.DataFrame(
            [
                {
                    "concept": "us-gaap_Revenues",
                    "label": "Total Revenues",
                    "dimension": False,
                    "FY2024": 100000.0,
                },
                {
                    "concept": "us-gaap_Revenues",
                    "label": "Segment X [Member]",
                    "dimension": True,
                    "FY2024": 25000.0,
                },
            ]
        )
        mapped = dataframe_to_concept_dict(df, ["FY2024"])
        self.assertEqual(mapped["us-gaap_Revenues"]["values"]["FY2024"], 100000.0)

        target_df = pd.DataFrame(
            [{"concept": "us-gaap_Revenues", "label": "Total Revenues", "dimension": False, "FY2024": 100000.0, "FY2023": None}]
        )
        source_df = pd.DataFrame(
            [
                {
                    "concept": "us-gaap_Revenues",
                    "label": "Segment X [Member]",
                    "dimension": True,
                    "FY2023": 22000.0,
                },
                {
                    "concept": "us-gaap_Revenues",
                    "label": "Total Revenues",
                    "dimension": False,
                    "FY2023": 90000.0,
                },
            ]
        )
        merge_annual_statement_df(source_df, target_df, ["FY2024", "FY2023"], overwrite_if_newer=True)
        row = target_df[target_df["concept"] == "us-gaap_Revenues"].iloc[0]
        self.assertEqual(float(row["FY2024"]), 100000.0)
        self.assertEqual(float(row["FY2023"]), 90000.0)

    def test_append_rows_and_merge_emit_zero_pandas_future_warnings(self):
        """Verifica cero FutureWarnings de pandas al inyectar filas con columnas NA/mixtas."""
        target_df = pd.DataFrame(
            [{"concept": "us-gaap_Revenues", "label": "Revenues", "FY2025": 500.0, "FY2024": None, "FY2023": None}]
        )
        new_rows = [
            {"concept": "us-gaap_GrossProfit", "label": "Gross Profit", "FY2025": None, "FY2024": 250.0, "dimension": False},
        ]
        with warnings.catch_warnings(record=True) as captured:
            warnings.simplefilter("always", FutureWarning)
            _append_rows_safely(target_df, new_rows)
            merge_annual_statement_df(
                pd.DataFrame([{"concept": "us-gaap_NetIncomeLoss", "label": "Net Income", "dimension": False, "FY2023": 80.0}]),
                target_df,
                ["FY2025", "FY2024", "FY2023"],
            )
        pandas_future = [w for w in captured if issubclass(w.category, FutureWarning)]
        self.assertEqual(pandas_future, [])
        self.assertEqual(len(target_df), 3)

    def test_normalize_archetype_never_leaks_custom_default_onto_corporate(self):
        """Asegura que alias corporativos retornen STANDARD_CORPORATE sin heredar default financiero."""
        self.assertEqual(normalize_archetype("CORPORATE_STANDARD", default="FINANCIAL_BANKING"), "STANDARD_CORPORATE")
        self.assertEqual(normalize_archetype("standard_corporate", default="INSURANCE"), "STANDARD_CORPORATE")
        self.assertEqual(normalize_archetype("", default="FINANCIAL_BANKING"), "FINANCIAL_BANKING")


if __name__ == "__main__":
    unittest.main()
