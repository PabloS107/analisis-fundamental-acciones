# Configuración y Benchmarks Sectoriales (`config/`)

Este directorio almacena los **3 archivos de configuración JSON** que gobiernan la identidad oficial ante SEC EDGAR, las rutas de salida/sincronización, las medianas sectoriales (Damodaran NYU Stern) y el catálogo auditado de grupos de pares por código SIC.

---

## 1. Archivos en `config/` y Cómo se Cargan

| Archivo | Cargadores SSOT en Código | Propósito Principal |
| :--- | :--- | :--- |
| `sec_config.json` | [`pipeline/infra/config_loader.py`](../pipeline/infra/config_loader.py) (`load_sec_config`, `get_sec_headers`, `resolve_local_output_base`) | Define el `User-Agent` exigido por SEC EDGAR (`sec_identity`), la ruta base de Google Drive (`google_drive_base_path`), la ruta local de datos procesados (`local_output_path`), el flag `sync_output_to_drive` y las ventanas históricas por defecto (`default_years_history`, `default_quarters_history`). |
| `industry_medians.json` | [`pipeline/scoring_modules/scoring_utils.py`](../pipeline/scoring_modules/scoring_utils.py) (`load_industry_medians`, `get_sector_benchmarks`) | Catálogo de medianas sectoriales Damodaran por código SIC (`SIC_3571`, `SIC_7372`, `SIC_3674`, `SIC_7370`, `SIC_5961`, `SIC_3021`, `SIC_6199`, `SIC_7389`, `SIC_6021`, `SIC_6798`, `SIC_6331`), respaldo `BROAD_MARKET` (S&P 500 Non-Financials) y tabla de mapeo `ticker_to_sic`. |
| `peer_benchmarks.json` | [`pipeline/scoring_modules/scoring_utils.py`](../pipeline/scoring_modules/scoring_utils.py) (`load_peer_benchmarks`, `compute_peer_benchmarks`, `get_sector_benchmarks`) y [`pipeline/audit_modules/data_verifier.py`](../pipeline/audit_modules/data_verifier.py) (`verify_peer_group_benchmarks`) | Almacena bajo `industry_benchmarks` las cifras LTM auditadas de competidores reales por sector SIC (`SIC_3571`, `SIC_3021`, `SIC_6199`, `SIC_7389`, `SIC_3674`, `SIC_7370`, `SIC_7372`, `SIC_6021`, `SIC_6798`, `SIC_6331`) para recalcular dinámicamente medianas, percentil 75 y rankings comparativos. |

---

## 2. Detalle Técnico y Flujo de Resolución

### 2.1. `sec_config.json`
Claves configuradas actualmente:
- `sec_identity`: Encabezado `User-Agent` obligatorio en toda petición a `data.sec.gov` y `edgartools` (en `pre_flight_checks` se valida que no esté vacío y contenga `@`).
- `google_drive_base_path`: Ruta raíz en Windows hacia Google Drive (`G:\Mi unidad\analisis fundamental`), usada con menor prioridad que `--drive-path` o las variables de entorno `GOOGLE_DRIVE_PATH` / `GOOGLE_DRIVE_BASE_PATH` en `drive_manager.py`.
- `local_output_path`: Ruta relativa o absoluta para los artefactos procesados (`data\processed`), anclada invariablemente a `PROJECT_ROOT` por `resolve_local_output_base()`.
- `sync_output_to_drive`: Booleano (`true`/`false`) que activa o desactiva la copia final en `fundamental_pipeline.sync_to_google_drive()`.
- `default_years_history` / `default_quarters_history`: Ventanas históricas por defecto (`5` años / `8` trimestres).

> Si `sec_config.json` falta o contiene JSON inválido, `load_sec_config()` emite un aviso y retorna valores de respaldo seguros sin abortar la lectura ni depender del `cwd`.

### 2.2. `industry_medians.json`
Cada clave `SIC_<código>` contiene los parámetros sectoriales consumidos por el motor de scoring:
- **Mohanram G-Score y Rentabilidad**: `median_roa`, `p75_roa`, `median_cfroa`, `median_cv_roa`, `median_sales_growth`, `median_cv_sales_growth`, `median_rd_intensity`, `median_capex_intensity`, `median_total_reinvestment`, `is_asset_light`.
- **Novy-Marx GP/A**: `median_gross_profitability`, `p75_gross_profitability`, `median_gp_ex_cash`, `median_gross_margin`, `median_asset_turnover`.
- **ROIC Intangible (Damodaran) y WACC**: `rd_useful_life_years`, `sga_capitalization_pct`, `sga_useful_life_years`, `damodaran_industry_wacc`, `damodaran_unlevered_beta`, `median_traditional_roic`, `median_adjusted_roic`, `median_economic_spread`.
- **`ticker_to_sic`**: Mapeo auxiliar de ticker → código SIC de 4 dígitos usado cuando el perfil o filing no aporta un SIC limpio.

### 2.3. `peer_benchmarks.json`
Estructura `{"industry_benchmarks": {"SIC_XXXX": {"sic_code", "industry_name", "fiscal_year_basis", "source", "peers": [...]}}}`:
- En `get_sector_benchmarks()` (`scoring_utils.py`), primero se carga la base de `industry_medians.json` y luego se busca el grupo de pares en `peer_benchmarks.json` siguiendo una cascada de 4 niveles:
  1. `SIC_<código>` exacto.
  2. Búsqueda del `ticker` dentro de las listas `peers` existentes.
  3. Coincidencia por prefijo SIC de 3 o 2 dígitos.
  4. Fallback por arquetipo normalizado (`_ARCHETYPE_TO_SIC`: p. ej. `FINANCIAL_BANKING → SIC_6021`, `REAL_ESTATE_REIT → SIC_6798`, `INSURANCE → SIC_6331`, `PLATFORM_ECOSYSTEM → SIC_7389`).
- Cuando se encuentra un grupo de pares, `compute_peer_benchmarks()` recalcula dinámicamente `median_roa`, `p75_roa`, `median_cfroa`, `median_rd_intensity`, `median_total_reinvestment`, `median_capex_intensity`, `median_gross_profitability`, `p75_gross_profitability`, `median_gp_ex_cash`, `median_gross_margin`, `median_asset_turnover`, `median_traditional_roic`, `median_adjusted_roic`, `median_wacc`, `median_economic_spread` y `median_greenblatt_roc`, sobrescribiendo los valores estáticos base de `industry_medians.json` e inyectando `peers_detail`.
- Además, `web_dashboard/analytics/views/views_scoring_quality.py` (`_resolve_novy_marx_peers`) invoca `load_industry_medians()` y `get_sector_benchmarks()` como respaldo dinámico si `fundamental_scores.json` no incluyera `novy_marx_analysis.peer_ranking`.
- El verificador `data_verifier.py` (`verify_peer_group_benchmarks`) puede contrastar cada par contra SEC Company Facts y reescribir atómicamente `peer_benchmarks.json` junto con `peer_verification_report.json/.md`.

---

## 3. Matriz de Impacto ante Modificaciones

| Archivo Modificado | Efecto Directo al Modificarlo | Módulos y Vistas Impactadas | Pruebas Recomendadas |
| :--- | :--- | :--- | :--- |
| `config/sec_config.json` | Cambia la identidad HTTP ante SEC EDGAR (si falta `@` falla `pre_flight_checks`), redirige `local_output_path` o desactiva/cambia el destino de Google Drive. | `config_loader.py`, `sec_rate_limiter.py`, `sec_extractor.py`, `filing_context.py`, `sec_freshness.py`, `kpi_extractor.py`, `governance_insider_analyzer.py`, `drive_manager.py`, `data_verifier.py`, `fundamental_pipeline.py`, `pipeline_runner.py` (descarga `sec_company_tickers.json`), `tests/health_check.py`. | `python -m unittest discover -s tests/web_dashboard -v` (`test_config_and_pipeline_runner.py`, `test_drive_manager.py`) y `python tests/health_check.py` |
| `config/industry_medians.json` | Modifica umbrales de Mohanram G-Score (`G1`, `G2`, `G4`, `G6`, `G7`), vida útil de I+D / porcentaje capitalizable de SG&A en ROIC Damodaran (`rd_useful_life_years`, `sga_capitalization_pct`), beta desapalancada / WACC de industria y mapeo `ticker_to_sic`. | `scoring_utils.py`, `piotroski_mohanram.py`, `profitability_capital.py`, `financial_scoring_engine.py`, `views_scoring_quality.py` (pestaña `💎 Calidad de Negocio`). | `python -m unittest discover -s tests/scoring_valuation -v` (`test_scoring_engine.py`) |
| `config/peer_benchmarks.json` | Sobrescribe dinámicamente medianas y P75 de ROA, CFROA, I+D, CapEx, GP/A, ROIC, WACC y ROC Greenblatt vía `compute_peer_benchmarks()`, y cambia la tabla comparativa de competidores en el dashboard. | `scoring_utils.py`, `piotroski_mohanram.py`, `profitability_capital.py`, `data_verifier.py`, `views_scoring_quality.py` (`peers` en `#tab-quality`). | `python -m unittest discover -s tests/scoring_valuation -v` (`test_scoring_engine.py`, `test_roc_greenblatt.py`) y `python -m unittest tests.web_dashboard.test_web_statements -v` |
