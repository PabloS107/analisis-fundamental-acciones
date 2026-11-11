# Submódulos Transversales de Infraestructura (`pipeline/infra/`)

Contiene los **5 módulos de soporte transversal** utilizados por todas las capas del pipeline, el Dashboard Web Django y las utilidades de respaldo en Google Drive.

---

## 1. Catálogo de Scripts

### 1. [`config_loader.py`](./config_loader.py) — Fuente Única de Verdad (SSOT) de Rutas y Configuración
- **Invariancia respecto al CWD**: calcula `PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent` (3 niveles hacia arriba desde `pipeline/infra/config_loader.py`) y expone las rutas canónicas absolutas:
  - `CONFIG_DIR` (`PROJECT_ROOT/config`)
  - `DATA_DIR` (`PROJECT_ROOT/data`)
  - `DATA_PROCESSED_DIR` (`PROJECT_ROOT/data/processed`)
  - `DATA_CACHE_DIR` (`PROJECT_ROOT/data/cache`)
  - `DRIVE_INPUT_DIR` (`PROJECT_ROOT/drive_input`)
- **Carga de `config/sec_config.json`**:
  - `load_sec_config(config_path=None)`: lee `config/sec_config.json` combinándolo con valores mínimos seguros (`sec_identity`, `google_drive_base_path`, `local_output_path`, `sync_output_to_drive`).
  - `get_sec_headers(config_path=None)`: construye `{"User-Agent": identity, "Accept-Encoding": "gzip, deflate"}`.
  - `resolve_local_output_base(cfg=None)` y `resolve_output_dir(ticker, output_dir=None)`: resuelven siempre rutas ancladas a `PROJECT_ROOT`, evitando crear carpetas residuales (como `web_dashboard/data/`) cuando Django arranca fuera de la raíz.
  - `resolve_market_cache_path()`: retorna `DATA_CACHE_DIR / "market_data_cache.json"`.

---

### 2. [`json_io.py`](./json_io.py) — Escritura Atómica de JSON
- **`atomic_json_write(path, data, **dump_kwargs)`**:
  - Crea los directorios padres si no existen.
  - Serializa primero a un archivo temporal único en el mismo directorio (`{target.name}.tmp-{pid}-{uuid}`), ejecuta `f.flush()` + `os.fsync(f.fileno())` y sustituye el destino mediante `os.replace(tmp, target)`.
  - Si ocurre cualquier excepción (`BaseException`), limpia el archivo temporal sin corromper ni truncar el JSON existente en disco, garantizando lecturas consistentes desde Django (`json_cache.py`) o verificadores concurrentes.

---

### 3. [`sec_rate_limiter.py`](./sec_rate_limiter.py) — Control de Tasa y Resiliencia HTTP SEC EDGAR
Cumple estrictamente la política oficial de la SEC (máximo 10 peticiones por segundo por `User-Agent`):
- **`SECRateLimiter(min_interval=0.15)`** y singleton **`default_rate_limiter`**:
  - Control preventivo de cadencia (*pacing*) protegido con `threading.Lock()`. Un intervalo mínimo de `0.15s` limita el tráfico a ~`6.67 req/s`, dejando un margen de seguridad del 33% por debajo del tope de la SEC.
  - Métodos: `pace()` y alias `wait_if_needed()`.
- **`sec_call_with_retry(...)`** y decorador **`@sec_retry_with_backoff(...)`**:
  - Aplica `rate_limiter.pace()` antes de cada intento.
  - Reintenta con *backoff* exponencial + *jitter* ante HTTP `429` (`urllib.error.HTTPError`, `requests`/`httpx` `status_code == 429`), `TooManyRequestsError` / `TooManyRequestsException` de `edgartools` (respetando la cabecera `Retry-After` vía `_parse_retry_after_header`) y errores transitorios de red (`URLError`, `TimeoutError`, `ConnectionResetError`). Relanza de inmediato errores de lógica o validación no transitorios.
- **`safe_sec_request(url, identity=None, timeout=15, max_retries=4, base_delay=1.0, rate_limiter=None)`**:
  - Cliente HTTP unificado sobre `urllib.request` para consultas REST directas a `data.sec.gov`, inyectando `User-Agent` (desde `config_loader`) y `Accept-Encoding: gzip, deflate`, con descompresión automática `gzip` y parseo JSON.
- *Nota sobre caché*: `sec_rate_limiter.py` gestiona exclusivamente cadencia, cabeceras y reintentos HTTP; el almacenamiento en caché se realiza en RAM mediante `SharedFilingContext` ([`../sec_modules/filing_context.py`](../sec_modules/filing_context.py)) y en disco mediante `data/cache/market_data_cache.json` ([`../valuation_modules/market_data_provider.py`](../valuation_modules/market_data_provider.py)) y `data/cache/sec_company_tickers.json` (`web_dashboard/analytics/pipeline_runner.py`).

---

### 4. [`drive_manager.py`](./drive_manager.py) — Gestor de Rutas y Sincronización Resiliente con Google Drive
- **`resolve_google_drive_path(custom_path=None)`**: resuelve la carpeta raíz de Google Drive con precedencia estricta:
  1. `custom_path` explícito (p. ej. `--drive-path`).
  2. Variables de entorno `GOOGLE_DRIVE_PATH` o `GOOGLE_DRIVE_BASE_PATH`.
  3. `google_drive_base_path` en `config/sec_config.json`.
  4. Auto-detección multiplataforma (`_auto_detect_system_drive_path` para Windows `G:`..`C:`, macOS `~/Library/CloudStorage` y `/Volumes`, Linux `~/GoogleDrive`, etc.).
  5. Respaldo local `DRIVE_INPUT_DIR` (`PROJECT_ROOT/drive_input`).
- **`find_ticker_drive_dir`** y **`get_ticker_drive_processed_dir`**: localizan o crean `{Drive}/{TICKER}/presentations` y `{Drive}/{TICKER}/processed`.
- **`safe_copy_file(src, dst, max_retries=4, base_delay=0.5)`**: copia archivos (`shutil.copy2`) con reintentos y retroceso exponencial ante bloqueos temporales del cliente de sincronización de Drive (`PermissionError` / `OSError`).

---

### 5. [`sync_to_drive.py`](./sync_to_drive.py) — Sincronizador de Código Fuente a Google Drive
Utilidad CLI independiente (`python pipeline/infra/sync_to_drive.py`) que replica una copia limpia del código fuente del repositorio hacia `{google_drive_base_path}/codigo_analisis_fundamental`:
- Toma `source_root = Path(__file__).resolve().parent.parent.parent` y resuelve el destino con `load_sec_config` (`config_loader`).
- Sincroniza `SYNC_DIRS = ["pipeline", "web_dashboard", "config", "tests", "docs"]` y `ROOT_FILES = ["requirements.txt", "pyproject.toml", "README.md", "Iniciar_Dashboard_Web.bat", "AGENTS.md", ".gitignore"]`.
- Excluye artefactos de entorno y temporales (`EXCLUDED_DIR_NAMES`: `__pycache__`, `.venv`, `.git`, `cache`, `.system_generated`; `EXCLUDED_EXTS`: `.pyc`, `.sqlite3`, `.db`, `.tmp`, `.lock`; `EXCLUDED_FILENAMES`: `.DS_Store`, `desktop.ini`, `Thumbs.db`).

---

## 2. Matriz de Impacto Transversal

| Script Modificado | Artefactos / Rutas Afectadas | Consumidores Directos e Indirectos en Todo el Proyecto | Comandos `unittest` Recomendados tras Editar |
| :--- | :--- | :--- | :--- |
| `config_loader.py` | - Lectura de `config/sec_config.json`<br>- Resolución de `data/processed/`, `data/cache/`, `drive_input/` | - **Todas** las fachadas (`fundamental_pipeline`, `sec_extractor`, `financial_scoring_engine`, `valuation_engine`, `audit_engine`)<br>- `sec_modules` (`filing_context`, `sec_freshness`, `sec_segment_extractor`, `kpi_extractor`, `governance_insider_analyzer`)<br>- `audit_modules/data_verifier.py`, `valuation_modules` (`market_data_provider`, `market_history`)<br>- `web_dashboard/analytics/` (`view_utils.py`, `pipeline_runner.py`), `tests/health_check.py` | `python -m unittest tests/web_dashboard/test_config_and_pipeline_runner.py tests/sec_extraction/test_sec_freshness.py tests/web_dashboard/test_capa4_web_analytics_hygiene.py -v` |
| `json_io.py` | Todos los JSON generados en `data/processed/{TICKER}/` y `data/cache/` | - `sec_extractor.py`, `sec_segment_extractor.py`, `kpi_extractor.py`, `governance_insider_analyzer.py`<br>- `audit_engine.py`, `data_verifier.py`, `financial_scoring_engine.py`<br>- `market_data_provider.py`, `market_history.py`<br>- `web_dashboard/analytics/pipeline_runner.py` (`sec_company_tickers.json`) | `python -m unittest tests/scoring_valuation/test_market_data.py tests/sec_extraction/test_kpi_extractor.py tests/web_dashboard/test_config_and_pipeline_runner.py -v` |
| `sec_rate_limiter.py` | Peticiones HTTP a `data.sec.gov` y `edgar-tools` | - `sec_extractor.py`, `filing_context.py`, `kpi_extractor.py`, `governance_insider_analyzer.py`<br>- `audit_modules/data_verifier.py`<br>- `tests/health_check.py` | `python -m unittest tests/sec_extraction/test_sec_rate_limiter.py tests/sec_extraction/test_shared_filing_context.py -v` |
| `drive_manager.py` | Carpetas `{Drive}/{TICKER}/presentations` y `{Drive}/{TICKER}/processed` | - `fundamental_pipeline.py` (Pre-Flight y Paso E)<br>- `sec_modules/kpi_extractor.py` (lectura de PDFs y sync de `presentation_reconciliation.json`)<br>- `audit_modules/data_verifier.py` (`_sync_reports_to_drive`)<br>- `tests/health_check.py` | `python -m unittest tests/web_dashboard/test_drive_manager.py tests/sec_extraction/test_kpi_extractor.py -v` |
| `sync_to_drive.py` | Réplica del código en `{Drive}/codigo_analisis_fundamental` | - Utilidad standalone de sincronización manual/respaldo del repositorio completo | `python -c "import pipeline; from pipeline.infra import sync_to_drive; print('OK', sync_to_drive.SYNC_DIRS)"` |

### Verificación Global de Infraestructura e Importaciones

```powershell
python -c "import pipeline; from pipeline.config_loader import PROJECT_ROOT; from pipeline.json_io import atomic_json_write; from pipeline.sec_rate_limiter import SECRateLimiter; from pipeline.drive_manager import resolve_google_drive_path; print('OK', PROJECT_ROOT)"
python -m unittest tests/web_dashboard/test_config_and_pipeline_runner.py tests/web_dashboard/test_drive_manager.py tests/sec_extraction/test_sec_rate_limiter.py -v
```
