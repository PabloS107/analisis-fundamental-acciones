# Orquestador Universal de Análisis Fundamental Institucional

Plataforma modular e institucional para la extracción automatizada de estados financieros oficiales desde **SEC EDGAR** (US-GAAP e IFRS), normalización multi-arquetipo, auditoría contable de partida doble, scoring cuantitativo académico, valoración intrínseca dual y visualización interactiva a través de un **Terminal Web en Django**.

---

## 1. Arquitectura y Estructura del Repositorio

```text
Analisis fundamental de acciones/
├── AGENTS.md                         # Reglas obligatorias irrestrictas (STOP & PROPOSE, Regla 1–7)
├── CURRENT_CONTEXT.md                # Estado vivo del sistema y bitácora de auditoría por capas
├── QA_REPORT.md                      # Reporte automático generado por tests/health_check.py
├── Iniciar_Dashboard_Web.bat         # Lanzador 1-clic en Windows para el Dashboard Web Django
├── pyproject.toml / requirements.txt # Metadatos y dependencias Python del proyecto
│
├── pipeline/                         # Motor central de extracción, auditoría, scoring y valoración
│   ├── fundamental_pipeline.py       # Orquestador CLI y programático (Pre-Flight + Pasos A–E)
│   ├── sec_extractor.py              # Fachada de extracción XBRL US-GAAP/IFRS y segmentos
│   ├── financial_scoring_engine.py   # Fachada de F-Score, G-Score, Novy-Marx, ROIC, WACC, Forense y Solvencia
│   ├── valuation_engine.py           # Fachada de Reverse DCF (2/3 etapas), Excess Return y sensibilidad
│   ├── audit_engine.py               # Motor de auditoría de identidades contables y sanidad
│   ├── sec_modules/                  # 12 módulos SEC: taxonomía, arquetipos, LTM, segmentos, KPIs y gobernanza
│   ├── audit_modules/                # Verificación cruzada de pares/SEC (data_verifier) y período (period_integrity)
│   ├── scoring_modules/              # 5 módulos cuantitativos (Piotroski, Mohanram, ROIC, Forense, Solvencia)
│   ├── valuation_modules/            # Modelos DCF/Excess Return, histórico y proveedor de mercado en vivo
│   └── infra/                        # Rutas SSOT (config_loader), JSON atómico, rate limiter SEC y Drive
│
├── web_dashboard/                    # Aplicación Web Django (Terminal Financiero Interactivo)
│   ├── manage.py                     # CLI de Django
│   ├── web_dashboard/                # settings.py (LocMemCache), urls.py, wsgi.py / asgi.py
│   ├── analytics/                    # context_processors, json_cache (mtime+size), pipeline_runner, urls, tests
│   │   └── views/                    # 14 módulos cohesivos por pestaña y arquetipo
│   └── templates/                    # base.html, index.html y company_detail.html (6 pestañas + JS)
│
├── tests/                            # Suite de pruebas automatizadas y diagnóstico
│   ├── health_check.py               # Diagnóstico integral (SEC API, Drive, Skills y auditoría de empresas)
│   ├── sec_extraction/               # 8 suites de clasificación, taxonomía IFRS, KPIs, XBRL y frescura SEC
│   ├── accounting_audit/             # 8 suites de identidades P&L, balance, flujos, As-Reported y período
│   ├── scoring_valuation/            # 7 suites de F/G-Score, ROC, forense, solvencia, mercado y valoración
│   ├── web_dashboard/                # 8 suites de higiene AST, vistas Django, gráficos, segmentos y Drive
│   └── e2e_stress/                   # 7 suites de estrés adversarial y orquestación E2E multi-arquetipo
│
├── config/                           # Configuración y benchmarks sectoriales
│   ├── sec_config.json               # Identidad User-Agent SEC EDGAR y rutas locales/Drive
│   ├── industry_medians.json         # Medianas Damodaran por código SIC y mapeo ticker_to_sic
│   └── peer_benchmarks.json          # Cifras LTM auditadas de grupos de pares por sector SIC
│
├── data/
│   ├── cache/                        # Cachés locales efímeras (market_data_cache.json, sec_company_tickers.json)
│   └── processed/{TICKER}/           # Datasets JSON canónicos auditados por empresa
│
├── docs/                             # Especificaciones matemáticas e índice documental
│   └── Especificacion_Calculos_FScore_GScore.txt
│
├── drive_input/                      # Acceso/respaldo local sincronizado con presentaciones PDF y datos Drive
└── .agents/                          # Reglas y skills registradas del asistente
```

---

## 2. Los 5 Arquetipos Contables Soportados

El clasificador institucional ([`pipeline/sec_modules/entity_classifier.py`](pipeline/sec_modules/entity_classifier.py)) detecta dinámicamente el modelo contable de cada emisor combinando códigos SIC de la SEC, estructura del balance y taxonomía US-GAAP/IFRS, sin hardcodear lógica por ticker:

| Identificador Canónico | Arquetipo | Emisoras de Control | Lógica Contable y de Valoración Aplicada |
| :--- | :--- | :--- | :--- |
| `STANDARD_CORPORATE` | **Corporativo e Industrial** | `AAPL`, `DECK`, `GOOGL`, `META`, `NVDA`, `UBER` | Cascada P&L completa (`Revenue → COGS → Gross Profit → OpEx → EBIT → Net Income`), ROIC Intangible (Damodaran), Novy-Marx GP/A, Piotroski F-Score, Mohanram G-Score, Altman Z'' y Reverse DCF (2 y 3 etapas + Owner Earnings). |
| `FINANCIAL_BANKING` | **Banca y Neobancos** | `JPM`, `NU` | Estructura bajo Article 9 S-X (`Interest Income/Expense → NII`, `Non-Interest Income`, provisiones crediticias, depósitos y cartera neta); KPIs bancarios (`NIM`, `Efficiency Ratio`, `ROE/ROTCE`, `CET1`, `NPL`, `Cost of Risk`); inhibe COGS/FCF/Altman Z''/ROC y valora con **Excess Return 2-Etapas (P/TBV vs. ROTCE y Ke con Beta Blume)**. |
| `INSURANCE` | **Aseguradoras** | `PGR` | Estructura bajo Article 7 S-X (`Net Premiums Earned`, `Net Investment Income`, `Losses & LAE`, `DAC`, reservas técnicas y `Float`); KPIs técnicos (`Combined Ratio`, `Loss Ratio`, `Expense Ratio`, rendimiento de cartera); valora con **Excess Return / Gordon-Shapiro (P/BV vs. ROE y Ke)**. |
| `REAL_ESTATE_REIT` | **Inmobiliario (REITs)** | `O` | Estructura inmobiliaria (`Rental Revenue`, `Property OpEx`, `NOI`, `FFO`, `AFFO`, `LTV`); desacopla CapEx de mantenimiento frente a adquisiciones inmobiliarias y evalúa dividend payout sobre `AFFO`. |
| `PLATFORM_ECOSYSTEM` | **Plataformas Híbridas** | `MELI` | Conserva P&L comercial completo incorporando métricas crediticias (`Credit Loss Provision`, `GMV`, `TPV`, `MAUs`, cartera de crédito y morosidad) y normaliza el capital de trabajo / FCF frente al float de clientes en el Reverse DCF. |

---

## 3. Cómo Lanzar el Dashboard Web Django

Toda la exploración visual se realiza desde la aplicación web Django en `web_dashboard/`. Cualquier nueva empresa procesada en `data/processed/{TICKER}/` se incorpora automáticamente al catálogo superior y a la portada gracias a `nav_companies` y `load_json_cached` (`mtime + tamaño`).

### Opción rápida (Windows, 1 clic)
Ejecuta [`Iniciar_Dashboard_Web.bat`](Iniciar_Dashboard_Web.bat) en la raíz del proyecto. Abrirá `http://127.0.0.1:8000/` e iniciará el servidor local de Django.

### Opción manual por terminal
```powershell
python web_dashboard/manage.py runserver 127.0.0.1:8000
```

### Capacidades del Terminal Web
- **Portada (`/`):** Tarjetas comparativas adaptadas por arquetipo y barra de **Incorporación Zero-Touch** (`/api/search/`, `/api/pipeline/trigger/`, `/api/pipeline/status/<ticker>/`) para buscar cualquier emisor cotizado en SEC/Yahoo y ejecutar el pipeline en segundo plano con seguimiento en vivo.
- **Ficha de Empresa (`/company/<TICKER>/`):** Cotización en tiempo real (`?refresh=1`), botón de verificación de frescura SEC (`Sincronizar SEC`), avisos de integridad contable y **6 pestañas interactivas**:
  1. **📑 Estados Financieros:** Alternador *Vista Estandarizada (10Y + LTM)* vs. *Reporte Oficial SEC (3Y + LTM)*, subpestañas P&L / Flujo / Balance / Cascada Completa, modos `$M` / `% Vertical` / `% YoY & CAGR`, búsqueda en vivo y exportación CSV.
  2. **🌍 Segmentos & Geografía:** Tablas jerárquicas ASC 280 conciliadas al 100% contra ingresos consolidados, márgenes por segmento, territorios y gráficos de tendencia/mix.
  3. **📈 Rentabilidad & Asignación de Capital:** Series históricas de márgenes, conversión `FCF/NI`, Recompra Neta vs. Float y marco 5Y de asignación de capital (y vistas específicas de banca/plataforma).
  4. **💎 Calidad de Negocio & Retornos sobre Capital:** Desglose de Piotroski F-Score (0–9), Mohanram G-Score (0–8), ROIC Ajustado vs. WACC/Ke, Greenblatt ROC y ranking de pares Novy-Marx.
  5. **🛡️ Auditoría Forense & Solvencia Financiera:** Ratio Sloan, Montier C-Score (0–6), apalancamiento Deuda Neta / EBITDA, cobertura de intereses, Altman Z'' y rating sintético Damodaran.
  6. **💎 Valoración & Futuro (360°):** Selector *Dual Valuation Engine* (GAAP vs. Owner Earnings), simulador interactivo en tiempo real de Reverse DCF / Excess Return, matriz de sensibilidad 5×6, múltiples históricos y cajón de trazabilidad KaTeX.

---

## 4. Cómo Ejecutar el Pipeline de Extracción y Análisis (CLI)

Antes de ejecutar extracciones contra SEC EDGAR, verifica que tu identidad (`Nombre correo@dominio.com`) esté configurada en [`config/sec_config.json`](config/sec_config.json).

```powershell
# Ejecución estándar (guarda en data/processed/<TICKER>/ y sincroniza con Drive si está activo)
python pipeline/fundamental_pipeline.py --ticker MSFT

# Opciones adicionales de rutas personalizadas
python pipeline/fundamental_pipeline.py --ticker MSFT --out-dir data/processed/MSFT --drive-path "G:\Mi unidad\analisis fundamental"
```

### Flujo de Ejecución (`run_pipeline`)
1. **Pre-Flight Checks:** Valida identidad SEC en `config/sec_config.json`, disponibilidad de Google Drive y directorio de salida local.
2. **Paso A (`sec_extractor.py`):** Descarga filings oficiales (`10-K`, `10-Q`, `20-F`, `6-K`) vía `SharedFilingContext` y `sec_rate_limiter`, clasifica arquetipo, construye `financial_statements.json`, `segments_data.json`, `sec_narrative.json` y `company_profile.json`.
3. **Paso B (`kpi_extractor.py`):** Extrae y normaliza métricas operativas Non-GAAP desde `8-K`/`6-K Ex-99.1` y presentaciones PDF en Drive (`presentation_reconciliation.json`).
4. **Paso C (`audit_engine.py` y `governance_insider_analyzer.py`):** Audita identidades contables e integridad de período (`audit_report.json`) y analiza compensación ejecutiva / transacciones Form 4 (`governance_insider_data.json`).
5. **Paso D (`financial_scoring_engine.py`):** Calcula F-Score, G-Score, Novy-Marx, ROIC Intangible, WACC/Ke, Sloan, Montier, solvencia y parámetros base de valoración (`fundamental_scores.json`).
6. **Paso E (`sync_to_google_drive`):** Replica los artefactos procesados en Google Drive si `sync_output_to_drive` es `true`.

---

## 5. Cómo Ejecutar las Suites de Pruebas

```powershell
# 1. Suite completa de pruebas unitarias, auditoría y estrés (38 módulos en tests/)
python -m unittest discover -s tests -q

# 2. Suites temáticas por subcarpeta (modo verboso)
python -m unittest discover -s tests/sec_extraction -v
python -m unittest discover -s tests/accounting_audit -v
python -m unittest discover -s tests/scoring_valuation -v
python -m unittest discover -s tests/web_dashboard -v
python -m unittest discover -s tests/e2e_stress -v

# 3. Suite de integración de Django
python web_dashboard/manage.py test analytics

# 4. Health Check integral del sistema (SEC API, Drive, Skills y auditoría de empresas)
python tests/health_check.py
```

---

## 6. Guías Especializadas por Carpeta

Para consultar las responsabilidades internas, esquemas de datos y matrices de impacto antes de editar cualquier archivo, revisa el `README.md` de cada módulo:

- **Gobernanza y Contexto:** [`AGENTS.md`](AGENTS.md) · [`CURRENT_CONTEXT.md`](CURRENT_CONTEXT.md) · [`docs/README.md`](docs/README.md)
- **Pipeline y Submódulos:** [`pipeline/README.md`](pipeline/README.md) · [`pipeline/sec_modules/README.md`](pipeline/sec_modules/README.md) · [`pipeline/audit_modules/README.md`](pipeline/audit_modules/README.md) · [`pipeline/scoring_modules/README.md`](pipeline/scoring_modules/README.md) · [`pipeline/valuation_modules/README.md`](pipeline/valuation_modules/README.md) · [`pipeline/infra/README.md`](pipeline/infra/README.md)
- **Web Django:** [`web_dashboard/README.md`](web_dashboard/README.md) · [`web_dashboard/analytics/views/README.md`](web_dashboard/analytics/views/README.md)
- **Configuración y Pruebas:** [`config/README.md`](config/README.md) · [`tests/README.md`](tests/README.md)
