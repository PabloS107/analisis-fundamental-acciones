# Submódulos de Extracción SEC, Taxonomía, Segmentos y KPIs (`pipeline/sec_modules/`)

Contiene los **12 módulos especializados** encargados de conectar con SEC EDGAR, clasificar el arquetipo contable de la compañía, normalizar estados financieros US-GAAP e IFRS a 10 años + LTM/MRQ, resolver vistas canónicas e idioma español, extraer segmentos ASC 280 / ASC 606, verificar frescura de presentaciones y capturar KPIs operativos y señales de gobernanza.

---

## 1. Catálogo de los 12 Scripts

### Capa de Contexto, Clasificación y Ontología

1. **[`filing_context.py`](./filing_context.py)** (`SharedFilingContext`)
   - Manifiesto único en memoria RAM por corrida del pipeline para eliminar descargas y parseos duplicados.
   - Cachea de forma perezosa (`lazy`): instancia `edgar.Company`, metadatos (`cik`, `name`, `sic_code`, `is_fpi`, `accounting_standard`), colecciones de filings (`get_filings`), objetos parseados `.obj()` (`get_filing_obj`), árboles XBRL `.xbrl()` (`get_filing_xbrl`), `facts_df` (`get_facts_df`) y metadatos del último comunicado de resultados (`get_latest_earnings_release_data`).
   - Registra telemetría de rendimiento (`cache_hits`, `network_fetches`, `obj_parses`, `xbrl_parses`).

2. **[`entity_classifier.py`](./entity_classifier.py)**
   - Fuente Única de Verdad (SSOT) para clasificación dinámica de entidades en los **5 arquetipos institucionales**:
     - `STANDARD_CORPORATE` (alias recíproco `CORPORATE_STANDARD`)
     - `FINANCIAL_BANKING`
     - `INSURANCE`
     - `REAL_ESTATE_REIT`
     - `PLATFORM_ECOSYSTEM`
   - Combina código SIC (`parse_sic_code`, división FIRE `6000–6799`, códigos plataforma `{5961, 7389, 5990}`), perfil declarado (`_resolve_declared_archetype`) y huella booleana XBRL (`_extract_concept_fingerprint`: excluye pasivos `ASC 606` de depósitos bancarios).
   - Funciones principales: `normalize_archetype`, `detect_company_archetype`, `is_banking_or_financial`, `clean_concept_name`.

3. **[`financial_taxonomy.py`](./financial_taxonomy.py)**
   - Define los mapas jerárquicos de etiquetas US-GAAP e IFRS por arquetipo: `CORPORATE_TAXONOMY_MAP`, `BANKING_TAXONOMY_MAP`, `REIT_TAXONOMY_MAP`, `INSURANCE_TAXONOMY_MAP`, `PLATFORM_TAXONOMY_MAP` y `XBRL_TAXONOMY_MAP`.
   - Expone `get_first_matching_value` (búsqueda jerárquica tolerante a prefijos/guiones), `reconcile_accounting_identities` (derivación algebraica de `gross_profit`, `operating_expenses`, `operating_income`, `total_liquid_cash`, `total_debt`, `net_debt`, `free_cash_flow` y `net_working_capital` respetando el arquetipo) y `generate_data_integrity_badge`.

4. **[`financial_bilingual_map.py`](./financial_bilingual_map.py)**
   - Motor de traducción técnica al español para partidas US-GAAP, IFRS, Banca, Seguros y REITs.
   - Implementa 4 niveles de prioridad en `get_spanish_label` / `get_spanish_clarification`: (1) diccionario exacto `SPANISH_CLARIFICATIONS`, (2) concepto canónico `CANONICAL_CONCEPT_MAP`, (3) coincidencia parcial ordenada por longitud descendente (`SORTED_MAP_KEYS`), y (4) traductor gramatical universal `heuristic_translate` (`HEURISTIC_REPLACEMENTS`), con desambiguación dimensional (`Products` / `Services` en costo vs ingresos).

5. **[`canonical_resolvers.py`](./canonical_resolvers.py)**
   - Motor canónico SSOT compartido entre el pipeline (`sec_statement_reconciler.py`) y las vistas Django (`views_statements.py`, `views_statements_memo.py`).
   - Resuelve e integra los 3 estados estandarizados y flujos de capital:
     - `resolve_canonical_capital_flows` (recompras en mercado abierto, planes de acciones, retención SBC, dividendos, M&A, emisiones y repagos de deuda).
     - `resolve_canonical_balance_sheet` (garantiza cierre contable de activos corrientes y no corrientes, deuda multi-tramo, BVPS/TBVPS y partidas bancarias/aseguradoras).
     - `resolve_canonical_income_statement` (desglose OpEx sin duplicar I+D o provisiones de crédito, EBIT, EBT, BPA y campos específicos de Banca/Seguros/REIT).
     - `resolve_canonical_cash_flow` (4 secciones: CFO, CFI, CFF, puente de caja y FCF/AFFO respetando Regla 6).

### Capa de Extracción XBRL, LTM, Conciliación y Frescura

6. **[`sec_xbrl_ltm.py`](./sec_xbrl_ltm.py)**
   - Extracción cruda XBRL, desambiguación de BPA multi-clase (`sanitize_multiclass_eps_df` sobre `StatementClassOfStockAxis` para evitar sumas espurias entre clases A/B/C), conversión tabular (`dataframe_to_concept_dict`, `convert_xb_statement_to_df`) y fusión multi-año (`merge_annual_statement_df`, `enrich_annual_statements_with_individual_filings` aplicando *Latest Filed Priority* + extracción de notas ECL en `20-F`).
   - Consultas a `CompanyFacts` (`get_mrq_fact`, `get_mrq_fact_sum`, `get_ltm_quarterly_metric`, `get_fact_fallback`).
   - Cálculo e inyección de columnas `LTM`/`MRQ`: `compute_and_inject_ltm_columns` (para emisores `10-Q`) y `extract_6k_fpi_interim` (parser HTML para Foreign Private Issuers `6-K` con detección de escala local/global `detect_table_scale_factor`, `detect_global_doc_scale` y calibración frente al último `FY`).

7. **[`sec_statement_reconciler.py`](./sec_statement_reconciler.py)**
   - `build_as_reported_statements`: construye `as_reported_statements` (P&L, Balance, Flujo de Caja) preservando jerarquía y líneas oficiales de la carátula SEC mediante emparejamiento histórico de 3 niveles con candado dimensional (`_filter_by_dimension_lock`) y cálculo LTM/MRQ.
   - `sanitize_and_validate_statements`: candado automático post-extracción que homogeneiza signos (`_normalize_statement_row_signs`), añade `spanish_label` y `orig_tooltip`, sincroniza `LTM == latest_fy` cuando el último filing periódico es anual (`10-K`/`20-F`/`40-F`), resuelve colisiones dimensionales LTM y pre-calcula `resolved_canonical_statements` en `financial_statements.json`.

8. **[`sec_canonical_builder.py`](./sec_canonical_builder.py)**
   - `extract_canonical_summary`: construye `canonical_summary` y `key_ratios` con ramas especializadas por arquetipo (`_extract_banking_pnl_period`, `_extract_reit_pnl_period`, `_extract_insurance_pnl_period`, `_extract_corporate_pnl_period`, `_extract_banking_bs_period`, `_extract_insurance_bs_period`, `_extract_corporate_bs_period`).
   - Calcula retornos sobre balances promedio `(t + t-1)/2` (`roa_avg_pct`, `roe_avg_pct`, `roc_greenblatt_pct`), métricas sectoriales (`efficiency_ratio_pct`, `risk_adj_nim_pct`, `cost_of_risk_pct`, `ldr_pct`, `combined_ratio_pct`, `ffo`/`affo`/`noi`) y detección retroactiva de Stock Splits (`split_adjustment_factor`, `shares_*_adjusted`, `eps_*_adjusted`, `dps_adjusted`).

9. **[`sec_segment_extractor.py`](./sec_segment_extractor.py)**
   - `build_and_save_segments_data` (y wrapper `build_10yr_segment_df`): extrae desglose histórico (hasta 8 `10-K`/`20-F` + inyección LTM de `10-Q`/`6-K`) de segmentos de producto, canales, geografías y resultado operativo por segmento bajo `ASC 280` / `ASC 606`.
   - Resuelve jerarquías padre-hijo, limpia subtotales/ruido dimensional y genera `data/processed/{TICKER}/segments_data.json`.

10. **[`sec_freshness.py`](./sec_freshness.py)**
    - `build_sec_freshness_metadata` y `derive_period_label`: construyen el bloque `sec_metadata` (`ltm_period`, `ltm_period_end`, `latest_periodic_form`, `latest_periodic_date`, `latest_periodic_accession`, `latest_8k_earnings_date`).
    - `get_local_sec_metadata` y `check_sec_freshness`: comparan el dataset local contra SEC EDGAR con Salvaguarda 1 (retrocompatibilidad sin inventar LTM en legacy -> `N/D`) y Salvaguarda 2 (filtrado de `6-K` sin XBRL o estados financieros).

### Capa de KPIs Non-GAAP, Comunicados y Gobernanza

11. **[`kpi_extractor.py`](./kpi_extractor.py)**
    - `extract_operational_kpis`: combina el último `8-K` Item 2.02 / `6-K` Ex-99.1 (`extract_from_sec_ex99`) y presentaciones PDF en Drive/local (`extract_from_presentation_pdf`).
    - Normaliza KPIs por arquetipo (`normalize_banking_kpis`, `normalize_platform_kpis`, `normalize_corporate_kpis`, `normalize_reit_kpis`, `normalize_insurance_kpis`), construye el bloque `comparisons` contra `financial_statements.json` y escribe `data/processed/{TICKER}/presentation_reconciliation.json`.

12. **[`governance_insider_analyzer.py`](./governance_insider_analyzer.py)**
    - `analyze_governance_and_insiders`: escanea hasta 25 `8-K` (alertas Item 2.04 default, 4.01 cambio de auditor, 5.02 cambios C-suite), 25 `6-K` para emisores `FPI`, 40 `Form 4` (compras abiertas código `P`, ventas `10b5-1` vs discrecionales, retenciones `F`) y 20 `Form 144`.
    - Calcula `governance_score` (20–100) y `insider_sentiment` (o exención Sección 16 en FPI) y escribe `data/processed/{TICKER}/governance_insider_data.json`.

---

## 2. Matriz de Impacto ante Modificaciones

> **Nota sobre `sec_narrative.json`:** Este artefacto es generado directamente por `_extract_10k_narratives()` en la fachada [`../sec_extractor.py`](../sec_extractor.py) apoyándose en `filing_context.py` (`get_filings`, `get_filing_obj`, `sic_code`).

| Script Modificado | Artefacto(s) JSON Generados o Modificados en `data/processed/{TICKER}/` | Módulos Aguas Abajo y Pestañas Web Dependientes | Comandos `unittest` Recomendados tras Editar |
| :--- | :--- | :--- | :--- |
| `filing_context.py` | Indirecto: acelera e hidrata `financial_statements.json`, `segments_data.json`, `sec_narrative.json`, `presentation_reconciliation.json` y `governance_insider_data.json` | - `sec_extractor.py`, `sec_xbrl_ltm.py`, `sec_segment_extractor.py`, `sec_freshness.py`, `kpi_extractor.py`, `governance_insider_analyzer.py`<br>- `fundamental_pipeline.py` (telemetría final) | `python -m unittest tests/sec_extraction/test_shared_filing_context.py tests/sec_extraction/test_sec_extractor_modularization.py -v` |
| `entity_classifier.py` | - `financial_statements.json` (`archetype`, `is_financial`, `business_model`)<br>- `presentation_reconciliation.json` (`archetype`)<br>- Propaga a `fundamental_scores.json` | - `financial_taxonomy.py`, `sec_canonical_builder.py`, `kpi_extractor.py`<br>- `scoring_modules/` (`scoring_utils`, `profitability_capital`, `forensic_accounting`, `solvency_credit`)<br>- `valuation_engine.py`<br>- `view_utils.py`, `views.py`, `views_statements_schemas.py` (todas las pestañas de `company_detail.html` e `index.html`) | `python -m unittest tests/sec_extraction/test_archetype_classifier.py tests/e2e_stress/test_m1_empirical_stress.py tests/e2e_stress/test_challenger_m2_stress.py -v` |
| `financial_taxonomy.py` | - `financial_statements.json` (`canonical_summary`, `key_ratios`, `as_reported_statements`) | - `sec_xbrl_ltm.py`, `sec_canonical_builder.py`, `sec_statement_reconciler.py`<br>- Indirecto: `audit_engine.py`, `financial_scoring_engine.py`, `valuation_engine.py`<br>- Pestañas `#tab-statements`, `#tab-charts`, `#tab-quality`, `#tab-forensic`, `#tab-reversedcf` | `python -m unittest tests/sec_extraction/test_ifrs_taxonomy.py tests/accounting_audit/test_opex_ebit_integrity.py tests/e2e_stress/test_m1_empirical_stress.py -v` |
| `financial_bilingual_map.py` | - `financial_statements.json` (`as_reported_statements[*].clarification` y `spanish_label`) | - `sec_statement_reconciler.py`<br>- `web_dashboard/analytics/views/views_statements_cells.py` (Pestaña `#tab-statements`, tabla SEC As-Reported) | `python -m unittest tests/web_dashboard/test_web_statements.py tests/accounting_audit/test_as_reported_integrity.py -v` |
| `canonical_resolvers.py` | - `financial_statements.json` (`resolved_canonical_statements`: `balance_sheet`, `income_statement`, `capital_flows`, `cash_flow`) | - `sec_statement_reconciler.py`<br>- `web_dashboard/analytics/views/views.py`, `views_statements.py`, `views_statements_memo.py`, `views_charts_series.py`, `views_scoring_forensics.py`<br>- Pestañas `#tab-statements`, `#tab-charts`, `#tab-forensic` | `python -m unittest tests/accounting_audit/test_balance_sheet_reconciliation.py tests/accounting_audit/test_cash_flow_reconciliation.py tests/accounting_audit/test_opex_ebit_integrity.py tests/web_dashboard/test_web_statements.py -v` |
| `sec_xbrl_ltm.py` | - `financial_statements.json` (`fiscal_years`, `*_detail`, `as_reported_statements`, `canonical_summary`) | - `sec_extractor.py`, `sec_canonical_builder.py`, `sec_statement_reconciler.py`<br>- `audit_engine.py` y `data_verifier.py`<br>- Todas las pestañas de `company_detail.html` | `python -m unittest tests/sec_extraction/test_multiclass_eps_and_xbrl_hygiene.py tests/sec_extraction/test_ifrs_taxonomy.py tests/accounting_audit/test_as_reported_integrity.py -v` |
| `sec_statement_reconciler.py` | - `financial_statements.json` (`as_reported_statements`, `canonical_summary` LTM/STI/dividends, `resolved_canonical_statements`) | - `sec_extractor.py`, `audit_engine.py`, `period_integrity.py`<br>- `views_statements.py`, `views_statements_cells.py` (Pestaña `#tab-statements` Estandarizada y As-Reported) | `python -m unittest tests/accounting_audit/test_as_reported_integrity.py tests/accounting_audit/test_income_statement_audit.py tests/web_dashboard/test_web_statements.py -v` |
| `sec_canonical_builder.py` | - `financial_statements.json` (`canonical_summary`, `key_ratios`) | - `sec_extractor.py`, `audit_engine.py`, `data_verifier.py`, `kpi_extractor.py`<br>- `financial_scoring_engine.py` (`scoring_utils.py`), `valuation_engine.py`<br>- `index.html` y todas las pestañas (`#tab-statements`, `#tab-charts`, `#tab-quality`, `#tab-forensic`, `#tab-reversedcf`) | `python -m unittest tests/sec_extraction/test_ifrs_taxonomy.py tests/accounting_audit/test_opex_ebit_integrity.py tests/accounting_audit/test_verify_aapl_nca.py tests/scoring_valuation/test_scoring_engine.py -v` |
| `sec_segment_extractor.py` | - `segments_data.json` | - `sec_extractor.py`<br>- `web_dashboard/analytics/views/views_charts_segments.py` y `views_charts.py`<br>- Pestaña `#tab-segments` (`Segmentos & Geografía`) | `python -m unittest tests/web_dashboard/test_segment_chart_periods.py tests/e2e_stress/test_challenger_m3_2_adversarial.py -v` |
| `sec_freshness.py` | - `financial_statements.json` (`sec_metadata`)<br>- Lee `sec_narrative.json` como respaldo legacy | - `sec_extractor.py`, `period_integrity.py`<br>- `web_dashboard/analytics/views/views.py` (`get_cached_sec_freshness`, endpoint `/api/sec-freshness/<ticker>/` y cabecera `sec_meta`), `views_charts.py` | `python -m unittest tests/sec_extraction/test_sec_freshness.py tests/accounting_audit/test_period_integrity.py -v` |
| `kpi_extractor.py` | - `presentation_reconciliation.json` | - `fundamental_pipeline.py` (Paso B)<br>- `views.py`, `views_statements_memo.py`, `views_charts_sector.py`<br>- Pestañas `#tab-statements` (tarjetas/MEMO sectoriales) y `#tab-charts` (KPIs bancarios/plataforma/corporativos) | `python -m unittest tests/sec_extraction/test_kpi_extractor.py tests/web_dashboard/test_profitability_capital_allocation_charts.py -v` |
| `governance_insider_analyzer.py` | - `governance_insider_data.json` | - `fundamental_pipeline.py` (Paso C) y sincronización a Google Drive (Paso E). *(Actualmente no es consumido directamente por ninguna vista de `web_dashboard/`, quedando disponible como artefacto de auditoría en `data/processed/{TICKER}/`).* | `python -m unittest tests/sec_extraction/test_sec_rate_limiter.py tests/sec_extraction/test_shared_filing_context.py -v`<br>`python -c "import pipeline; from pipeline.governance_insider_analyzer import analyze_governance_and_insiders; print('OK')"` |

### Verificación Global del Subpaquete

```powershell
python -m unittest discover -s tests/sec_extraction -v
```
