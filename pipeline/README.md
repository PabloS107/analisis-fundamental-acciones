# Arquitectura del Pipeline Universal de Análisis Fundamental (`pipeline/`)

El paquete `pipeline/` concentra toda la lógica de extracción regulatoria, auditoría contable, modelado cuantitativo, valoración intrínseca e infraestructura del **Orquestador Universal de Análisis Fundamental**.

Está diseñado bajo el patrón **Fachadas Públicas + Subpaquetes Temáticos** para mantener puntos de entrada estables, código cohesionado y retrocompatibilidad total de importaciones en CLI, Django y suites de pruebas.

---

## 1. Organización del Paquete

```text
pipeline/
├── __init__.py                   # Bootstrap de rutas (__path__ y sys.path) para imports duales
├── fundamental_pipeline.py       # Fachada maestra: orquesta el flujo E2E (Pre-Flight -> Paso E)
├── sec_extractor.py              # Fachada de extracción SEC EDGAR (10-K/20-F, 10-Q/6-K, XBRL)
├── audit_engine.py               # Fachada de auditoría contable e invariantes de período
├── financial_scoring_engine.py   # Fachada del motor cuantitativo (F/G, Novy-Marx, ROIC, WACC, Forense, Solvencia)
├── valuation_engine.py           # Fachada de valoración dual (Reverse DCF, Excess Return, Múltiplos, Z-Score)
│
├── sec_modules/                  # 12 módulos de extracción XBRL, taxonomía, LTM, segmentos, KPIs y gobernanza
├── audit_modules/                # 2 módulos de verificación tripartita e integridad temporal de períodos
├── scoring_modules/              # 5 módulos cuantitativos de calidad, rentabilidad, forense y solvencia
├── valuation_modules/            # 3 módulos de DCF/Excess Return, histórico de precios y datos en tiempo real
└── infra/                        # 5 módulos transversales de configuración SSOT, I/O atómico, rate-limit y Drive
```

### Garantía de Importaciones Retrocompatibles (`pipeline/__init__.py`)

[`__init__.py`](./__init__.py) ejecuta `_bootstrap_pipeline_paths()` al importarse el paquete `pipeline`, registrando de forma idempotente en `__path__` y `sys.path` la raíz del proyecto, `pipeline/` y sus 5 subpaquetes (`infra`, `sec_modules`, `audit_modules`, `scoring_modules`, `valuation_modules`). Asimismo, los subpaquetes y las 5 fachadas añaden estas rutas a `sys.path` cuando se invocan directamente por script. De este modo funcionan indistintamente:

- Importaciones de paquete: `from pipeline.sec_extractor import extract_sec_data`, `from pipeline.config_loader import PROJECT_ROOT`, `from pipeline.valuation_modules import solve_reverse_dcf`.
- Importaciones directas: `from config_loader import PROJECT_ROOT`, `from data_verifier import verify_financial_data`, `from market_data_provider import MarketDataExtractor`.

---

## 2. Flujo de Ejecución Secuencial (`fundamental_pipeline.py`)

El orquestador maestro [`fundamental_pipeline.py`](./fundamental_pipeline.py) expone `run_pipeline(ticker, custom_drive_path=None, custom_output_dir=None, progress_callback=None)` (consumido tanto por CLI como en segundo plano por `web_dashboard/analytics/pipeline_runner.py`) y ejecuta seis etapas secuenciales compartiendo un único manifiesto en memoria (`SharedFilingContext`):

```text
  [Pre-Flight]  --->  [Paso A: SEC XBRL]  --->  [Paso B: KPIs Non-GAAP]
       |                                                   |
       v                                                   v
  [Paso E: Drive Sync] <--- [Paso D: Scoring/Valoración] <--- [Paso C: Auditoría y Gobernanza]
```

1. **Pre-Flight (`pre_flight_checks`)**:
   - Carga `config/sec_config.json` mediante `config_loader.load_sec_config()`.
   - Verifica que exista una identidad SEC válida (`sec_identity` con `@`).
   - Comprueba la disponibilidad de la unidad de Google Drive (`drive_manager.resolve_google_drive_path()`) y prepara el directorio base local (`data/processed/`).
   - Instancia `SharedFilingContext(ticker)` para deduplicar descargas y parseos `.obj()` / `.xbrl()` / `facts_df` durante toda la corrida.
2. **Paso A — Extracción Oficial SEC EDGAR (`sec_extractor.extract_sec_data`)**:
   - Detecta el estándar contable (`US-GAAP` vs `IFRS` 20-F/40-F) y el arquetipo contable (`STANDARD_CORPORATE`, `FINANCIAL_BANKING`, `INSURANCE`, `REAL_ESTATE_REIT`, `PLATFORM_ECOSYSTEM`).
   - Extrae 10 años fiscales (`FY`) + período móvil `LTM`/`MRQ` (vía `10-Q` o parser HTML `6-K` para emisores extranjeros FPI).
   - Construye `canonical_summary`, `key_ratios`, `as_reported_statements` y `resolved_canonical_statements`.
   - Emite `financial_statements.json`, `segments_data.json` (ASC 280 / ASC 606) y `sec_narrative.json` (Items 1, 1A y 7 del 10-K/20-F).
3. **Paso B — Extracción y Conciliación de KPIs Operativos Non-GAAP (`kpi_extractor.extract_operational_kpis`)**:
   - Descarga el comunicado de resultados más reciente en SEC EDGAR (`8-K` Item 2.02 / `6-K` Ex-99.1) y, si existe, la presentación PDF más reciente en Drive o `drive_input/`.
   - Normaliza KPIs operativos según el arquetipo y concilia partidas de balance contra `financial_statements.json`.
   - Emite `presentation_reconciliation.json`. (Si falla o no existen comunicados, registra advertencia y continúa el pipeline).
4. **Paso C — Auditoría Contable e Inteligencia de Gobernanza**:
   - **Auditoría Contable (`audit_engine.run_full_audit`)**: valida 6 pruebas por período (Ecuación de Balance, Margen Bruto, FCF/AFFO, Reconciliación de Flujos de Caja, Límites de Sanidad y Consistencia de BPA) más los 5 invariantes temporales `P1–P5` de `period_integrity.py`. Emite `audit_report.json`.
   - **Gobernanza e Insiders (`governance_insider_analyzer.analyze_governance_and_insiders`)**: escanea formularios `8-K`, `6-K` (FPI), `Form 4` y `Form 144` calculando un puntaje de gobernanza (20–100) y sentimiento de directivos. Emite `governance_insider_data.json`.
5. **Paso D — Motor Cuantitativo de Scoring y Valoración Base (`financial_scoring_engine.calculate_fundamental_scores`)**:
   - Resuelve el código SIC y carga benchmarks sectoriales desde `config/industry_medians.json` y `config/peer_benchmarks.json`.
   - Ejecuta `PiotroskiScoreCalculator` (0–9), `MohanramScoreCalculator` (0–8), `CombinedMatrixClassifier`, `NovyMarxCalculator` (GP/A), `IntangibleROICCalculator` (Damodaran), `GreenblattROCCalculator` (ROC), `WACCCalculator` (CAPM/Ke en tiempo real vía `MarketDataExtractor`), `ForensicAccountingEngine` (Sloan, Divergencias, Montier C-Score) y `DebtSolvencyEngine` (Apalancamiento, Cobertura, Liquidez, Altman Z'' y Rating Sintético).
   - Emite `fundamental_scores.json`. *(La valoración intrínseca completa —Reverse DCF, Excess Return P/TBV, Múltiplos históricos, Owner Earnings, Z-Score— se calcula dinámicamente en `valuation_engine.py` a partir de `fundamental_scores.json`, `financial_statements.json`, `company_profile.json` y cotizaciones en vivo).*
6. **Paso E — Sincronización con Google Drive (`sync_to_google_drive`)**:
   - Si `sync_output_to_drive` es `True`, copia los artefactos finales de `data/processed/{TICKER}/` hacia la carpeta `processed/` del ticker en Google Drive con reintentos exponenciales (`safe_copy_file`), e imprime la telemetría de `SharedFilingContext`.

### Ejecución por Línea de Comandos

```powershell
# Pipeline completo para un ticker
python pipeline/fundamental_pipeline.py --ticker AAPL

# Fachadas individuales
python pipeline/sec_extractor.py --ticker AAPL
python pipeline/audit_engine.py --ticker AAPL
python pipeline/financial_scoring_engine.py AAPL   # o ALL para recalcular todo data/processed/
```

---

## 3. Las 5 Fachadas Públicas y sus Subpaquetes

| Fachada en `pipeline/` | Subpaquetes que Orquesta | Responsabilidad Principal | Guía Detallada del Subpaquete |
| :--- | :--- | :--- | :--- |
| [`fundamental_pipeline.py`](./fundamental_pipeline.py) | Todos (`sec_modules/`, `audit_modules/`, `scoring_modules/`, `valuation_modules/`, `infra/`) | Orquestación secuencial E2E (`Pre-Flight` -> `Paso E`), manejo de progreso (`progress_callback`) y sincronización final a Drive. | [`infra/README.md`](./infra/README.md) |
| [`sec_extractor.py`](./sec_extractor.py) | `sec_modules/`, `infra/` | Extracción oficial SEC EDGAR (10Y + LTM/MRQ), detección de arquetipo/estándar contable, narrativas 10-K y re-exportación de símbolos de `sec_modules`. | [`sec_modules/README.md`](./sec_modules/README.md) |
| [`audit_engine.py`](./audit_engine.py) | `audit_modules/`, `infra/` | Suite de 6 pruebas contables por período y verificación de integridad temporal/vigencia (`P1–P5`). | [`audit_modules/README.md`](./audit_modules/README.md) |
| [`financial_scoring_engine.py`](./financial_scoring_engine.py) | `scoring_modules/`, `valuation_modules/` (`market_data_provider`), `infra/` | Cálculo histórico + LTM de modelos cuantitativos de calidad, rentabilidad, WACC/Ke, análisis forense y solvencia crediticia. | [`scoring_modules/README.md`](./scoring_modules/README.md) |
| [`valuation_engine.py`](./valuation_engine.py) | `valuation_modules/`, `sec_modules/` (`entity_classifier`), `infra/` | Valoración dual por arquetipo (Reverse DCF 2/3 etapas, Excess Return P/TBV vs ROTCE, EPV, EVA, 5Y IRR, Owner Earnings, Z-Score y grilla 5×6). | [`valuation_modules/README.md`](./valuation_modules/README.md) |

---

## 4. Matriz de Impacto ante Modificaciones de las 5 Fachadas

| Fachada Modificada | Artefactos JSON Afectados en `data/processed/{TICKER}/` | Consumidores Aguas Abajo (Pipeline y Dashboard Web Django) | Suites `unittest` Obligatorias tras Editar |
| :--- | :--- | :--- | :--- |
| `fundamental_pipeline.py` | Orquesta todos (`financial_statements.json`, `segments_data.json`, `sec_narrative.json`, `presentation_reconciliation.json`, `audit_report.json`, `governance_insider_data.json`, `fundamental_scores.json`) | - CLI principal del pipeline<br>- `web_dashboard/analytics/pipeline_runner.py` (`_execute_pipeline_worker`) | `python -m unittest tests/web_dashboard/test_config_and_pipeline_runner.py -v`<br>`python -m unittest discover -s tests/e2e_stress -v` |
| `sec_extractor.py` | - `financial_statements.json`<br>- `sec_narrative.json`<br>- Delegación a `segments_data.json` | - `audit_engine.py` y `audit_modules/data_verifier.py`<br>- `financial_scoring_engine.py` y `valuation_engine.py`<br>- Todas las pestañas de `company_detail.html` y tarjetas de `index.html` | `python -m unittest tests/sec_extraction/test_sec_extractor_modularization.py tests/sec_extraction/test_archetype_classifier.py tests/sec_extraction/test_ifrs_taxonomy.py -v`<br>`python -m unittest discover -s tests/accounting_audit -v` |
| `audit_engine.py` | - `audit_report.json`<br>- `audit_balance_sheet` usado por `data_verifier.py` (`cross_verification_report.json`) | - `fundamental_pipeline.py` (Paso C: dictamen y `compliance_score_pct`)<br>- `audit_modules/data_verifier.py`<br>- `tests/health_check.py` | `python -m unittest tests/accounting_audit/test_audit_engine.py tests/accounting_audit/test_period_integrity.py tests/e2e_stress/test_challenger_m1_2.py -v` |
| `financial_scoring_engine.py` | - `fundamental_scores.json` | - `valuation_engine.py` (lee `wacc_analysis`, `intangible_roic_analysis`, `debt_and_solvency_analysis`, `benchmarks_used`)<br>- `views.py` (`index` y `company_detail`)<br>- `views_scoring.py`, `views_scoring_quality.py`, `views_scoring_forensics.py`<br>- Pestañas `#tab-quality`, `#tab-forensic`, `#tab-reversedcf` y tarjetas de `index.html` | `python -m unittest discover -s tests/scoring_valuation -v`<br>`python -m unittest tests/web_dashboard/test_web_forensics.py tests/web_dashboard/test_capa4_web_analytics_hygiene.py -v` |
| `valuation_engine.py` | Ninguno en disco por defecto (cálculo en tiempo real sobre JSONs procesados + `data/cache/market_data_cache.json`) | - `web_dashboard/analytics/views/views_valuation.py` (`get_valuation_parameters`, `_generate_sensitivity_grid`)<br>- Pestaña `#tab-reversedcf` (`Valoración & Futuro (360°)`) | `python -m unittest tests/scoring_valuation/test_valuation_engine.py tests/scoring_valuation/test_capa3_scoring_and_valuation_hygiene.py tests/web_dashboard/test_web_valuation.py -v` |
