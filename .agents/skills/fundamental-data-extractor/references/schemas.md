# Esquema Estándar de Datos Fundamentales (Fundamental Data Schema)

Este documento define la estructura y nomenclatura canónica que produce la skill `fundamental-data-extractor`. Todos los módulos posteriores de análisis (DCF, Múltiplos, DuPont, Calidad de Negocio/Moat) deben consumir estos mismos campos estandarizados.

---

## 1. `financial_statements.json`

Contiene los datos numéricos extraídos directamente de los formularios 10-K / 10-Q oficiales de la SEC (normativa US-GAAP).
Abarca **10 ejercicios fiscales completos + período LTM (Last Twelve Months / TTM)**.

```json
{
  "ticker": "AAPL",
  "company_name": "Apple Inc.",
  "cik": "0000320193",
  "source": "SEC EDGAR (US-GAAP Oficial)",
  "extraction_timestamp": "2026-09-04T15:30:00Z",
  "fiscal_years": [
    "LTM",
    "FY2025",
    "FY2024",
    "FY2023",
    "FY2022",
    "FY2021",
    "FY2020",
    "FY2019",
    "FY2018",
    "FY2017",
    "FY2016"
  ],
  
  "canonical_summary": {
    "revenue": { "LTM": 466823000000.0, "FY2025": 416161000000.0, ... },
    "cost_of_goods_sold": { "LTM": 239700000000.0, ... },
    "gross_profit": { "LTM": 227123000000.0, ... },
    "operating_expenses": { ... },
    "operating_income": { ... },
    "net_income": { "LTM": 128930000000.0, ... },
    "shares_diluted": { "LTM": 15004700000.0, ... },
    "cash_from_operations": { "LTM": 146724000000.0, ... },
    "capital_expenditures": { "LTM": 15389000000.0, ... },
    "free_cash_flow": { "LTM": 131335000000.0, ... },
    "cash_and_equivalents": { ... },
    "total_debt": { ... },
    "net_debt": { ... },
    "total_assets": { "LTM": 383266000000.0, ... },
    "stockholders_equity": { "LTM": 73733000000.0, ... }
  },

  "key_ratios": {
    "gross_margin_pct": { "LTM": 48.65, "FY2025": 46.91, ... },
    "operating_margin_pct": { "LTM": 33.17, ... },
    "net_margin_pct": { "LTM": 27.62, ... },
    "fcf_margin_pct": { "LTM": 28.13, ... },
    "fcf_conversion_pct": { "LTM": 101.9, ... },
    "roe_pct": { "LTM": 119.9, ... },
    "roa_pct": { "LTM": 33.64, ... },
    "current_ratio": { "LTM": 0.89, ... },
    "debt_to_equity": { "LTM": 1.15, ... }
  },

  "income_statement_detail": { ... },
  "balance_sheet_detail": { ... },
  "cash_flow_detail": { ... }
}
```

---

## 2. Convenciones de Unidades y Formato

1. **Moneda Base**: Todas las variables en `canonical_summary` se almacenan en **dólares enteros (USD)** dentro de `financial_statements.json` para evitar pérdidas de precisión en cálculos matemáticos.
2. **Modelo Excel (`financial_statements.xlsx`)**:
   - Pestaña 1 (`Resumen Fundamental`): Cifras formateadas en **Millones de USD ($M)**.
   - Pestaña 2 (`Ratios Financieros`): Márgenes y Retornos formateados en **Porcentaje (%)**, múltiplos en **(x)**.
   - Pestaña 3, 4, 5 (`Cuenta de Resultados`, `Balance Patrimonial`, `Flujo de Caja`): En **Millones de USD ($M)**.
   - Pestaña 6 (`Desglose de Segmentos`): En **Millones de USD ($M)**.
   - Columna 2 (`LTM`): Con encabezado diferenciado en Gris Pizarra / Dorado para identificar el período de doce meses móviles.
3. **Manejo de Cero vs. No Disponible**:
   - Cero (`0.0`): La empresa reportó explícitamente 0 en esa partida o no incurrió en gastos/ingresos.
   - `null` / `"-"`: El concepto no aplica o no fue reportado por la empresa en ese ejercicio fiscal.
