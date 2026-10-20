---
trigger: glob
globs: "pipeline/*.py, web_dashboard/analytics/*.py, web_dashboard/templates/*.html, tests/*.py"
description: "Invariantes contables obligatorios para as_reported_statements (SEC Extractor) y su visualización en Django."
---

# Invariantes Obligatorios para Estados Financieros As-Reported (SEC ↔ Web)

1. **Prohibición de Imputar LTM = FY_latest (Cumplimiento Estricto de Regla 6):**
   - Queda terminantemente PROHIBIDO asumir `delta_interino = 0.0` (`LTM = FY_latest`) cuando una partida de flujo (P&L o Cash Flow) o de Balance del 10-K no haga match en el 10-Q. Si no se encuentra en el 10-Q ni en `facts_df` (vía suma de 4 trimestres discretos para flujos o `get_mrq_fact` para balance), debe quedar en `None` (`-` en la web), salvo que en `canonical_summary` / `resolve_canonical_balance_sheet` exista una derivación contable exacta por identidad patrimonial (ej. APIC = Equity - Retained Earnings - AOCI + Treasury Stock).
2. **Cero Colisiones por Dimensión o Sinónimos:**
   - Ninguna fila con `dimension == True` (ej. `Products`, `Services`, `Class A`, `Class B`) puede emparejarse en `hist_df` ni en `q_face` únicamente por `concept` sin exigir coincidencia de `dimension_member` o etiqueta exacta. Dos filas con distinto `label` jamás pueden clonar el monto total consolidado.
   - El emparejamiento por grupo de sinónimos (`all_tax_maps`) solo puede usar un concepto candidato si dicho concepto NO está ya presente como otra fila propia dentro del mismo estado financiero.
3. **Homogeneidad Algebraica de Signos (LTM vs FY):**
   - En `as_reported_statements`, toda fila debe mantener la misma convención de signo entre `LTM` y todos los ejercicios anuales `FYxxxx`. Si el 10-K reporta un gasto o salida de caja con signo negativo en `FY_latest` (o si se normaliza a positivo/negativo), todos los períodos de esa misma fila (`LTM` y `FY` históricos) deben normalizarse al mismo signo antes de persistir el JSON y antes de calcular `% YoY` o `CAGR 5Y`.
4. **Sincronización Canónica (SSOT):**
   - Los valores en `as_reported_statements` para las líneas troncales (`Revenue`, `GrossProfit`, `OperatingIncomeLoss`, `NetIncomeLoss`, `Assets`, `Liabilities`, `StockholdersEquity`, `LongTermDebtNoncurrent`, `PaymentsOfDividends`, `PaymentsForRepurchaseOfCommonStock`, `NetCashProvidedByUsedInOperatingActivities`, `NetCashProvidedByUsedInInvestingActivities`, `NetCashProvidedByUsedInFinancingActivities`) deben reconciliarse contra `canonical_summary` para que ningún saneamiento canónico (como deuda o dividendos LTM en `NVDA`) quede desincronizado de la tabla As-Reported.