# Suite de Pruebas Automatizadas y Diagnóstico (`tests/`)

Este directorio centraliza las pruebas unitarias, de regresión contable, de renderizado web Django, de estrés adversarial y el diagnóstico de salud integral del sistema.

---

## 1. Arquitectura de `tests/` e Inicialización de Imports

- [`__init__.py`](__init__.py): Configura automáticamente `sys.path` al descubrir pruebas con `unittest discover`, insertando `PROJECT_ROOT`, `pipeline/` (junto con sus 5 subpaquetes `infra`, `sec_modules`, `audit_modules`, `scoring_modules`, `valuation_modules`) y `web_dashboard/`, además de importar `pipeline`.
- [`health_check.py`](health_check.py): Suite de diagnóstico integral ejecutable directamente con `python tests/health_check.py`. Verifica:
  1. `test_sec_connectivity`: Conectividad HTTP real contra `data.sec.gov` y validez del `User-Agent` en `config/sec_config.json`.
  2. `test_google_drive`: Montaje y permisos R/W de Google Drive y presencia de `drive_input/`.
  3. `test_skills_integrity`: Frontmatter YAML y scripts consolidados en `pipeline/` para `.agents/skills/`.
  4. `test_processed_companies`: Ejecuta `audit_engine.run_full_audit()` sobre cada empresa extraída en `data/processed/{TICKER}/` y genera [`QA_REPORT.md`](../QA_REPORT.md) en la raíz.
- **Pruebas adicionales en Django:** [`web_dashboard/analytics/tests.py`](../web_dashboard/analytics/tests.py) (`ValuationAndSensitivityTests`, 6 pruebas ejecutadas vía `manage.py test analytics`).

---

## 2. Catálogo Completo por Subcarpeta (38 archivos `test_*.py`)

### 2.1. `tests/sec_extraction/` (8 archivos)
Valida la clasificación de arquetipos, taxonomías US-GAAP/IFRS, frescura de filings, caché de contexto SEC, extracción de KPIs Non-GAAP e higiene XBRL.

| Archivo | Qué Verifica |
| :--- | :--- |
| `test_archetype_classifier.py` | Detección, extracción canónica y normalización recíproca de los 5 arquetipos (`REAL_ESTATE_REIT`, `INSURANCE`, `FINANCIAL_BANKING`, `PLATFORM_ECOSYSTEM`, `STANDARD_CORPORATE`), rangos SIC y cero regresiones en emisoras de control. |
| `test_ifrs_taxonomy.py` | Soporte IFRS / formularios `20-F` y `6-K`, calibración de escalas (miles/millones), eliminación de GP/FCF artificial en bancos, deuda bancaria (`JPM`) y ecosistema híbrido (`MELI`). |
| `test_kpi_extractor.py` | Normalización de KPIs operativos Non-GAAP (`8-K`/`6-K Ex-99.1` y presentaciones) por arquetipo, manejo explícito `DATO_NO_DISPONIBLE` ante faltantes (Regla 6), puntuación dinámica de recencia PDF y uso de `normalize_archetype` SSOT. |
| `test_multiclass_eps_and_xbrl_hygiene.py` | Saneamiento de EPS multi-clase (`StatementClassOfStockAxis` priorizando clases A/B sobre C), aislamiento de filas dimensionales en reconciliación, cero `FutureWarning` en pandas y precedencia en `normalize_archetype`. |
| `test_sec_extractor_modularization.py` | Integridad de fachada en `pipeline/sec_extractor.py` (`< 650` líneas), re-exportaciones `__all__`, compatibilidad de imports duales y ejecución desacoplada de `pipeline/sec_modules/`. |
| `test_sec_freshness.py` | Derivación de etiquetas de período (`10-Q`/`10-K`/`20-F`), filtro de `6-K` en FPIs (`NU`), retrocompatibilidad sin `sec_metadata`, caché de 15 min en `/api/sec-freshness/<ticker>/` y 2 tests de red opt-in (`RUN_SEC_NETWORK_TESTS=1`). |
| `test_sec_rate_limiter.py` | Pacing `<= 10 req/s` ante SEC EDGAR, backoff exponencial ante `TooManyRequestsError` / HTTP 429 (`Retry-After`), decorador `@sec_retry_with_backoff` y `safe_sec_request`. |
| `test_shared_filing_context.py` | Caché *lazy* en memoria de `SharedFilingContext` (`Company`, `get_filings`, `filing.obj()`, `filing.xbrl()`, `facts_df`), telemetría `cache_hits` vs `network_fetches` y retrocompatibilidad con `filing_context=None`. |

### 2.2. `tests/accounting_audit/` (8 archivos)
Valida identidades contables puras, integridad de estados estandarizados y *As-Reported*, cuadre de balance y flujo de caja e invariantes de vigencia temporal.

| Archivo | Qué Verifica |
| :--- | :--- |
| `test_as_reported_integrity.py` | Ausencia de duplicación LTM con distinto `FY_latest`, preservación de signos en costos/gastos, prevención de colisión con `Total Assets`, paridad de deuda/dividendos en `NVDA` y etiquetas 100% en español. |
| `test_audit_engine.py` | Identidad pura de Margen Bruto (`GP = Rev - COGS`), rechazo de COGS/OpEx negativos, FCF por arquetipo (`AFFO` en REITs, `SKIP` en financieras), bug `diff_adj` en `audit_eps_consistency` y auditoría real de `DECK`, `MELI` y `O`. |
| `test_balance_sheet_reconciliation.py` | Reconciliación matemática exacta de Activos No Corrientes (`sum(hijos) == Total Activos No Corrientes`) en `META`, `AAPL` y `DECK`. |
| `test_cash_flow_reconciliation.py` | Consistencia de caja (`Beginning Cash + Net Change in Cash == Ending Cash`) tanto dinámica como persistida para `META`, `AAPL`, `DECK`, `NVDA`, `JPM`, `MELI`, `O` y `PGR`. |
| `test_income_statement_audit.py` | Carga HTTP 200 y presencia de `std_pnl` en 9 empresas, integridad de beneficio fiscal, conciliación de asociadas en `MELI` y DPS histórico en `NVDA`. |
| `test_opex_ebit_integrity.py` | Cuadre exacto `sum(OpEx) == Total OpEx` y `Gross Profit - OpEx == EBIT`, no imputación de I+D en `DECK`, no duplicación de provisión crediticia en `MELI` y no imputación de EBIT corporativo en `JPM`/`NU`. |
| `test_period_integrity.py` | Invariantes de Plan P0 (`pipeline/audit_modules/period_integrity.py`): detección de períodos posteriores al filing o futuros, chequeo `LTM == FY` tras `10-K`, vigencia por huella SHA frente a `cross_verification_report.json` y estado `SINGLE_SOURCE`. |
| `test_verify_aapl_nca.py` | Script independiente de verificación matemática puntual sobre los Activos No Corrientes LTM de `AAPL` en `data/processed/AAPL/financial_statements.json`. *(Se ejecuta directamente con `python`, no contiene clases `unittest.TestCase`).* |

### 2.3. `tests/scoring_valuation/` (7 archivos)
Valida los motores cuantitativos de scoring, retornos sobre capital, contabilidad forense, solvencia, valoración y extracción de mercado.

| Archivo | Qué Verifica |
| :--- | :--- |
| `test_capa3_scoring_and_valuation_hygiene.py` | Higiene AST (`<= 180L`, cero `except: pass`) en `scoring_modules/`, `valuation_modules/`, `financial_scoring_engine.py` y `valuation_engine.py`, prohibición de literales ficticios (Regla 4 y 6), re-exports de fachada y trazabilidad LaTeX de `g_implied_oe_pct`. |
| `test_forensic_engine.py` | Ratio Sloan de devengos, matriz de divergencias de alerta temprana, Montier C-Score (0–6), escalado porcentual `t-1`, regresión `AAPL`/`DECK` e inhibición `NO APLICABLE` en entidades financieras. |
| `test_market_data.py` | Consenso en tiempo real Yahoo vs. CNBC en `MarketDataExtractor`, tolerancias, arbitraje de acciones con `10-Q`, caché de sesión y modo offline seguro. |
| `test_roc_greenblatt.py` | Cálculo de Greenblatt Return on Capital (ROC) con Capital Tangible Operativo Promedio, salvaguarda ante NWC negativo o capital nulo, benchmark sectorial e inhibición en banca y seguros. |
| `test_scoring_engine.py` | Estructura de `industry_medians.json`, Piotroski F-Score (incl. tolerancia relativa en `EQ_OFFER`), Mohanram G-Score, Novy-Marx GP/A, ROIC Intangible (Damodaran), WACC vs. Ke y sincronización dinámica con `peer_benchmarks.json`. |
| `test_solvency_engine.py` | Apalancamiento (`Net Debt/EBITDA`, `Net Debt/FCF`), cobertura de intereses, liquidez, Altman Z''-Score, escalera de rating sintético Damodaran, jerarquía multitaxonómica de deuda e inhibición bancaria/aseguradora. |
| `test_valuation_engine.py` | Reverse DCF para corporaciones (`AAPL`, `DECK`), normalización de float en híbridos (`MELI`), Excess Return Model en banca (`NU`), sensibilidad 5×6, Owner Earnings, Z-Score EV/NOPAT y múltiplos históricos. |

### 2.4. `tests/web_dashboard/` (8 archivos)
Valida las vistas modulares de Django, cachés, runner del pipeline, Google Drive, gráficos Chart.js y renderizado de cada pestaña.

| Archivo | Qué Verifica |
| :--- | :--- |
| `test_capa4_web_analytics_hygiene.py` | Higiene AST de los módulos en `web_dashboard/analytics/`, ausencia de defaults prohibidos (Regla 6), conversores de escala (`usd_to_m`, `already_m`, `pct_from_key_ratio`) y preservación de puntajes `0` o `N/D`. |
| `test_config_and_pipeline_runner.py` | Invariancia de rutas SSOT respecto al CWD, eliminación de artefactos obsoletos, resiliencia de `load_sec_config`, emisión de progreso en `run_pipeline` y delegación desde `analytics.pipeline_runner`. |
| `test_drive_manager.py` | Precedencia de rutas Google Drive (`custom -> env -> sec_config -> auto -> local`), scaffolding de carpetas por ticker y `safe_copy_file` con reintentos ante `PermissionError`. |
| `test_profitability_capital_allocation_charts.py` | Tab `#tab-charts` (conversión de caja, Recompra Neta vs. Float, Marco 5Y de Asignación de Capital, adquisiciones M&A y renderizado HTML across arquetipos). |
| `test_segment_chart_periods.py` | Inicio dinámico del eje X en gráficos de tendencias de segmentos (`chartProductTrends`, `chartGeoTrends`), evitando huecos nulos iniciales. |
| `test_web_forensics.py` | Coherencia semántica y clases visuales (Tailwind `emerald`/`rose`, cubetas Sloan 1–4, Montier C-Score y Caja Neta) en `#tab-forensic` (`NVDA`, `AAPL`, `DECK`). |
| `test_web_statements.py` | Cobertura transversal de la interfaz web: 3 estados estandarizados y *As-Reported*, flujos de capital SSOT, segmentos ASC 280 + márgenes operativos, calidad F/G-Score, ranking Novy-Marx y tooltips analíticos MEMO. |
| `test_web_valuation.py` | Renderizado de `#tab-reversedcf` (*Dual Valuation Engine*, radiografía CapEx/Owner Earnings, `historicalMultiplesChart`, cajón KaTeX y aislamiento financiero en `NU`). |

### 2.5. `tests/e2e_stress/` (7 archivos)
Valida el sistema extremo a extremo y somete los motores a pruebas de estrés adversarial, límites sintéticos y auditoría estática AST.

| Archivo | Qué Verifica |
| :--- | :--- |
| `test_challenger_m1_2.py` | Estrés empírico de identidades P&L (`GP = Rev - COGS`), AFFO REITs, redondeos en mega-caps (`NVDA`) y casos borde en `audit_engine`. |
| `test_challenger_m2_2_adversarial.py` | Estrés adversarial de jerarquía de deuda (GAAP/IFRS/Banca/REIT), signo negativo en intereses, capital tangible negativo/nulo e integridad en disco de las empresas procesadas. |
| `test_challenger_m2_stress.py` | Verificación de inhibición de Altman Z'' y Greenblatt ROC en banca/seguros (y sus alias), ramificación WACC vs. Ke y escaneo de cero hardcoding de tickers. |
| `test_challenger_m3_2_adversarial.py` | Integración multi-arquetipo (`NU`, `JPM`, `PGR`, `O`, `MELI`, `AAPL`, `DECK`), exclusión de subtotales en mix de segmentos y ausencia de constantes hardcodeadas. |
| `test_challenger_m3_stress.py` | Escaneo AST/Regex de prohibición de `if ticker == ...` y fallbacks ficticios en motores de cálculo + resistencia ante diccionarios vacíos, `None` y divisiones por cero. |
| `test_e2e_universal_orchestrator.py` | Suite E2E de 4 niveles (*Feature Coverage*, *Boundary Cases*, *Cross-Feature Pairwise*, *Real-World Scenarios*) sobre clasificación, desacople financiero, integridad de datos, no-hardcoding y renderizado Django. |
| `test_m1_empirical_stress.py` | Estrés empírico sobre límites exactos de códigos SIC, normalización recíproca de arquetipos, etiquetas bancarias de deuda y verificación empírica de `AAPL`, `DECK`, `JPM`, `MELI` y `O`. |

---

## 3. Guía Rápida de Comandos

### Comandos Generales
```powershell
# Ejecutar TODA la suite unittest desde la raíz del repositorio
python -m unittest discover -s tests -q

# Ejecutar pruebas por subcarpeta temática (modo verboso)
python -m unittest discover -s tests/sec_extraction -v
python -m unittest discover -s tests/accounting_audit -v
python -m unittest discover -s tests/scoring_valuation -v
python -m unittest discover -s tests/web_dashboard -v
python -m unittest discover -s tests/e2e_stress -v

# Incluir las 2 pruebas de red en vivo contra SEC EDGAR (opcional)
$env:RUN_SEC_NETWORK_TESTS="1"; python -m unittest tests.sec_extraction.test_sec_freshness -v

# Ejecutar suite de integración propia de la app Django
python web_dashboard/manage.py test analytics

# Ejecutar verificación puntual de Activos No Corrientes AAPL
python tests/accounting_audit/test_verify_aapl_nca.py

# Ejecutar Health Check completo del sistema y regenerar QA_REPORT.md
python tests/health_check.py
```

### Qué Ejecutar Tras Modificar Cada Módulo

| Área / Módulo Modificado | Comandos Recomendados |
| :--- | :--- |
| `pipeline/sec_extractor.py` o `pipeline/sec_modules/*` | `python -m unittest discover -s tests/sec_extraction -v` y `python -m unittest discover -s tests/accounting_audit -v` |
| `pipeline/audit_engine.py` o `pipeline/audit_modules/*` | `python -m unittest discover -s tests/accounting_audit -v` y `python tests/health_check.py` |
| `pipeline/financial_scoring_engine.py` o `pipeline/scoring_modules/*` | `python -m unittest discover -s tests/scoring_valuation -v` |
| `pipeline/valuation_engine.py` o `pipeline/valuation_modules/*` | `python -m unittest tests.scoring_valuation.test_valuation_engine tests.scoring_valuation.test_market_data tests.scoring_valuation.test_capa3_scoring_and_valuation_hygiene -v` y `python web_dashboard/manage.py test analytics` |
| `pipeline/infra/*` o `pipeline/fundamental_pipeline.py` | `python -m unittest tests.web_dashboard.test_config_and_pipeline_runner tests.web_dashboard.test_drive_manager tests.sec_extraction.test_sec_rate_limiter -v` |
| `config/*.json` | `python -m unittest discover -s tests/scoring_valuation -v` y `python -m unittest tests.web_dashboard.test_config_and_pipeline_runner -v` |
| `web_dashboard/` (`analytics/views/*`, `templates/*`, `settings.py`, `pipeline_runner.py`, `json_cache.py`) | `python -m unittest discover -s tests/web_dashboard -v` y `python web_dashboard/manage.py test analytics` |
| Cambio transversal o previo a `git push` (Regla 2 y Regla 7) | `python -m unittest discover -s tests -q`, `python web_dashboard/manage.py test analytics` y `python tests/health_check.py` |
