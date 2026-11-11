# Plataforma Web Django (`web_dashboard/`)

Aplicación web institucional desarrollada en **Django** (`Django>=5.0.0,<=6.1.1`) que sirve la terminal interactiva de análisis fundamental sobre los datasets JSON canónicos almacenados en `data/processed/{TICKER}/`. No utiliza modelos relacionales ORM para almacenar estados financieros; en su lugar, opera con lectura cacheada en memoria (`LocMemCache`) invalidada automáticamente por firma de archivo (`mtime + tamaño`), garantizando cero desincronización entre el pipeline y la interfaz web.

---

## 1. Lanzamiento y Comandos Esenciales

```powershell
# Opción 1: Lanzador directo en Windows (abre navegador y arranca el servidor en :8000)
.\Iniciar_Dashboard_Web.bat

# Opción 2: Arranque manual desde la raíz del repositorio
python web_dashboard/manage.py runserver 127.0.0.1:8000

# Ejecutar la suite de integración Django (analytics/tests.py)
python web_dashboard/manage.py test analytics
```

> **Invariancia de directorio de trabajo (CWD):** Tanto si ejecutas `manage.py` desde la raíz como desde `web_dashboard/`, todas las rutas a `data/processed/` y `data/cache/` se resuelven de forma absoluta mediante la Fuente Única de Verdad ([`pipeline/infra/config_loader.py`](../pipeline/infra/config_loader.py)), evitando crear carpetas residuales dentro de `web_dashboard/`.

---

## 2. Arquitectura de la Aplicación

```text
web_dashboard/
├── manage.py                         # Utilidad CLI de Django (DJANGO_SETTINGS_MODULE='web_dashboard.settings')
├── db.sqlite3                        # Base SQLite estándar de Django (sesiones/admin/test runner)
├── web_dashboard/                    # Configuración del proyecto Django
│   ├── settings.py                   # TEMPLATES, context_processors, LocMemCache y STATIC_URL
│   ├── urls.py                       # Enrutamiento raíz ('admin/' e include('analytics.urls'))
│   ├── wsgi.py / asgi.py             # Puntos de entrada WSGI/ASGI
└── analytics/                        # App principal del terminal financiero
    ├── urls.py                       # 6 rutas HTML + API REST JSON
    ├── context_processors.py         # nav_companies (carrusel superior dinámico de tickers)
    ├── json_cache.py                 # load_json_cached() con clave md5(path:mtime_ns:size)
    ├── pipeline_runner.py            # Buscador SEC/Yahoo y lanzador asíncrono en background thread
    ├── tests.py                      # 6 pruebas de integración Django (ValuationAndSensitivityTests)
    └── views/                        # 14 módulos cohesivos de lógica de presentación (ver views/README.md)
└── templates/
    ├── base.html                     # Layout maestro: Tailwind CDN, Chart.js, KaTeX y navbar scrollable
    ├── index.html                    # Portada: buscador Zero-Touch, modal de progreso y grid de tarjetas
    └── company_detail.html           # Ficha integral de empresa con 6 pestañas y simulador JS en vivo
```

---

## 3. Componentes Centrales y Flujo de Datos

### 3.1. `manage.py` y `web_dashboard/settings.py`
- **`manage.py`**: Configura `DJANGO_SETTINGS_MODULE = 'web_dashboard.settings'` y delega a `execute_from_command_line(sys.argv)`.
- **`web_dashboard/settings.py`**:
  - Registra `'analytics'` en `INSTALLED_APPS`.
  - Configura `TEMPLATES` apuntando a `BASE_DIR / 'templates'` e inyecta `'analytics.context_processors.nav_companies'` en todas las respuestas HTML.
  - Define **`CACHES['default']`** con `django.core.cache.backends.locmem.LocMemCache` (`LOCATION: 'analitica-fundamental'`, `KEY_PREFIX: 'af'`, `TIMEOUT: 3600`, `MAX_ENTRIES: 512`) para acelerar la lectura repetida de JSONs (~3-7x más rápido en cargas subsecuentes).

### 3.2. Enrutamiento (`web_dashboard/urls.py` y `analytics/urls.py`)
`web_dashboard/urls.py` delega la raíz a `analytics.urls` (`app_name = 'analytics'`):

| Ruta URL | Nombre (`name`) | Vista Destino | Propósito |
| :--- | :--- | :--- | :--- |
| `/` | `analytics:index` | `views.index` | Portada comparativa de empresas auditadas y buscador de incorporación. |
| `/company/<str:ticker>/` | `analytics:company_detail` | `views.company_detail` | Terminal completa de la empresa con 6 pestañas y simulador DCF/Excess Return. |
| `/api/search/` | `analytics:company_search` | `views.company_search` | Autocompletado JSON (`?q=`) sobre catálogo SEC y Yahoo Search API. |
| `/api/pipeline/trigger/` | `analytics:trigger_pipeline` | `views.trigger_pipeline` | POST para lanzar `run_pipeline` en segundo plano para un ticker. |
| `/api/pipeline/status/<str:ticker>/` | `analytics:pipeline_status` | `views.pipeline_status` | GET de telemetría en vivo (`status`, `progress_pct`, `step`, `completed`, `error`). |
| `/api/sec-freshness/<str:ticker>/` | `analytics:sec_freshness` | `views.sec_freshness_view` | GET de frescura de filings SEC (caché en memoria de 900s; `?force=1` fuerza consulta). |

### 3.3. `analytics/context_processors.py` (`nav_companies`)
- Escanea `DATA_DIR` (`data/processed/`) buscando subdirectorios válidos que contengan `fundamental_scores.json` o `financial_statements.json`.
- Calcula una firma agregada `_dir_signature(entries)` concatenando `{ticker}:{st_mtime_ns}:{st_size}` de cada empresa y la convierte en clave `nav_companies:{md5}` en `LocMemCache` (`NAV_CACHE_TTL = 3600`).
- Evita re-parsear todos los `fundamental_scores.json` en cada request mientras los archivos en disco no cambien, e invalida al instante cuando se procesa o actualiza cualquier empresa.

### 3.4. `analytics/json_cache.py` (`load_json_cached`)
- Firma: `load_json_cached(path, timeout=3600)`.
- Lee `stat()` del archivo y construye la clave `processed-json:{md5(f"{p}:{st.st_mtime_ns}:{st.st_size}")}`.
- Si hay acierto en `LocMemCache`, evita re-parsear el JSON desde disco; en cualquier caso retorna **`copy.deepcopy(data)`** para garantizar que las vistas puedan mutar estructuras en memoria sin contaminar la caché compartida entre requests.

### 3.5. `analytics/pipeline_runner.py`
Servicio de búsqueda e incorporación *Zero-Touch* ejecutado directamente desde la web:
- **`search_companies(query, limit=8)`**: Descarga y cachea por 7 días `data/cache/sec_company_tickers.json` (`https://www.sec.gov/files/company_tickers.json` usando `get_sec_headers()` y `atomic_json_write`). Ordena coincidencias exactas, por prefijo y por subcadena; si no alcanza `limit`, consulta la API de búsqueda de Yahoo Finance (`EQUITY`, excluyendo opciones/futuros).
- **`launch_pipeline_job(ticker)`**: Protegido por `_JOBS_LOCK` (`threading.Lock`) sobre `_ACTIVE_JOBS`. Si el ticker ya está en estado `RUNNING`, retorna la instantánea actual sin duplicar hilos; de lo contrario crea un `threading.Thread(..., daemon=True)` apuntando a `_execute_pipeline_worker`.
- **`_execute_pipeline_worker(ticker)`**: Delega la ejecución completa al orquestador unificado `pipeline.fundamental_pipeline.run_pipeline(t, custom_output_dir=out_dir, progress_callback=update_step)`, actualizando el porcentaje y el mensaje de progreso en tiempo real.
- **`get_job_status(ticker)`**: Retorna el estado del hilo activo en `_ACTIVE_JOBS` o, si ya existen `fundamental_scores.json` y `financial_statements.json` en `data/processed/{TICKER}/`, devuelve `COMPLETED` (`100%`).

### 3.6. Plantillas (`templates/`)
- **`base.html`**: Carga Tailwind CSS (CDN), Chart.js (CDN), KaTeX (`window.triggerKaTeX`), y renderiza el navbar superior con el carrusel horizontal desplazable de `nav_companies` (`#tickerStrip`).
- **`index.html`**: Barra de búsqueda con *debounce* (280ms) conectada a `/api/search/`, modal en vivo con *polling* cada 2.5s a `/api/pipeline/status/<ticker>/`, y cuadrícula de tarjetas adaptadas por arquetipo (`FINANCIAL_BANKING` muestra ROE/ROTCE, NIM y Ke; los demás arquetipos muestran Novy-Marx GP/A, ROIC Ajustado y WACC).
- **`company_detail.html`**: Cabecera ejecutiva con cotización en vivo (`?refresh=1`), valor intrínseco, semáforo de valoración, botón de sincronización SEC (`syncWithSec`), banner de `data_warnings` y **6 pestañas interactivas**:
  1. `tab-statements` (**📑 Estados Financieros**): Alternador *Vista Estandarizada (10Y + LTM)* vs *Reporte Oficial SEC (3Y + LTM)*, subpestañas (*Cascada Completa*, *Estado de Resultados*, *Flujo de Caja*, *Balance General*), modos *Importes ($M)*, *% Vertical*, *% YoY & CAGR*, buscador de partidas y exportación CSV.
  2. `tab-segments` (**🌍 Segmentos & Geografía**): Tablas ASC 280 de productos, canales, territorios geográficos, líneas discontinuadas y 4 gráficos Chart.js (`chartProductTrends`, `chartGeoTrends`, `chartProductDonut`, `chartGeoDonut`).
  3. `tab-charts` (**📈 Rentabilidad & Asignación de Capital**): Gráficos y KPIs específicos por arquetipo (banca, plataformas/ecosistemas y corporativas: `chartRevNI`, `chartMargins`, `chartCashConversion`, `chartNetBuybacksFloat`, `chartCapitalAllocation`, `chartBankingIncome`, `chartBankingBalance`, `chartBankingRisk`, `chartDepositsCountryDonut`, `chartPlatformGMVTPV`, `chartPlatformUsers`).
  4. `tab-quality` (**💎 Calidad de Negocio & Retornos sobre Capital**): Desglose señal a señal de Piotroski F-Score (0-9), Mohanram G-Score (0-8), gráficos `chartROICReturns` y `chartROCNovyMarx`, y tabla de pares Novy-Marx.
  5. `tab-forensic` (**🛡️ Auditoría Forense & Solvencia Financiera**): Sloan Accruals (escala de 4 cajas), Montier C-Score (0-6), tarjetas 13.1 (Deuda Neta/EBITDA), 13.2 (Cobertura de Intereses), Altman Z'' y rating sintético Damodaran.
  6. `tab-reversedcf` (**💎 Valoración & Futuro (360°)**): Selector *Dual Valuation Engine* (GAAP vs Owner Earnings), simulador interactivo JavaScript de Reverse DCF (2 y 3 etapas) y Excess Return 2-Etapas (`computeTwoStagePtbv`), matriz de sensibilidad 5×6, múltiples históricos (`historicalMultiplesChart`) y cajón de trazabilidad KaTeX.

---

## 4. Matriz de Impacto ante Modificaciones

| Archivo Modificado | Efecto en el Sistema / Riesgo | Módulos Dependientes / Vistas Afectadas | Tests a Ejecutar Tras Editar |
| :--- | :--- | :--- | :--- |
| `web_dashboard/settings.py` | Altera configuración de `LocMemCache`, `context_processors`, `TEMPLATES` o base de datos de pruebas. | Toda la app Django; invalidación o TTL de `json_cache` y `nav_companies`. | `python web_dashboard/manage.py test analytics` y `python -m unittest discover -s tests/web_dashboard -v` |
| `analytics/urls.py` | Cambia rutas URL o nombres (`analytics:*`) usados por `{% url %}` y `fetch()` en JS. | `base.html`, `index.html`, `company_detail.html`, clientes de prueba Django. | `python web_dashboard/manage.py test analytics` y `tests/web_dashboard/test_web_statements.py` |
| `analytics/context_processors.py` | Modifica el catálogo superior `#tickerStrip` o su firma de caché en `LocMemCache`. | `base.html` y todas las vistas HTML renderizadas. | `tests/web_dashboard/test_capa4_web_analytics_hygiene.py` y `python web_dashboard/manage.py test analytics` |
| `analytics/json_cache.py` | Cambia la invalidación por `mtime+size` o la seguridad de copia (`deepcopy`). | Todas las lecturas de `financial_statements.json`, `fundamental_scores.json`, `segments_data.json`, `company_profile.json` y `market_data_cache.json`. | `tests/web_dashboard/test_capa4_web_analytics_hygiene.py` y `tests/web_dashboard/test_config_and_pipeline_runner.py` |
| `analytics/pipeline_runner.py` | Afecta la búsqueda de tickers SEC/Yahoo, el bloqueo de hilos duplicados o la delegación a `run_pipeline`. | Endpoints `/api/search/`, `/api/pipeline/trigger/`, `/api/pipeline/status/<ticker>/` y modal de `index.html`. | `python -m unittest tests.web_dashboard.test_config_and_pipeline_runner -v` |
| `analytics/views/*.py` | Altera variables de contexto, unidades, lógica contable visual o dictámenes por arquetipo. | `index.html`, `company_detail.html` y sus 6 pestañas. *(Ver detalle por submódulo en [`analytics/views/README.md`](analytics/views/README.md)).* | `python -m unittest discover -s tests/web_dashboard -v` y `python web_dashboard/manage.py test analytics` |
| `templates/base.html` | Impacta estilos globales, librerías CDN (Tailwind/Chart.js/KaTeX) y barra de tickers. | `index.html` y `company_detail.html`. | `python web_dashboard/manage.py test analytics` y `tests/e2e_stress/test_e2e_universal_orchestrator.py` |
| `templates/index.html` | Altera tarjetas de portada, autocompletado o modal de incorporación Zero-Touch. | Vista `views.index` y endpoints `/api/search/`, `/api/pipeline/*`. | `python web_dashboard/manage.py test analytics` (`test_index_cards_complete`) |
| `templates/company_detail.html` | Altera tablas, etiquetas inspeccionadas por aserciones HTML o el simulador JS Reverse DCF / Excess Return. | Los 6 tabs de ficha de empresa y paridad matemática Python ↔ JS. | `python -m unittest discover -s tests/web_dashboard -v`, `python web_dashboard/manage.py test analytics` y `tests/e2e_stress/test_e2e_universal_orchestrator.py` |
