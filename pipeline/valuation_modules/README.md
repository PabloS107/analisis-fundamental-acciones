# Submódulos de Valoración Intrínseca y Datos de Mercado (`pipeline/valuation_modules/`)

Contiene los **3 módulos matemáticos y de mercado** que alimentan la fachada [`../valuation_engine.py`](../valuation_engine.py) y el cálculo de costo de capital en [`../scoring_modules/profitability_capital.py`](../scoring_modules/profitability_capital.py).

---

## 1. Catálogo de Scripts y Modelos Matemáticos

### 1. [`dcf_models.py`](./dcf_models.py)
Concentra las funciones puras de valoración intrínseca, inversa y comparables:

- **Reverse DCF de 2 Etapas (`solve_reverse_dcf`)**:
  - Resuelve por bisección (`100` iteraciones, rango `[-30%, +80%]`) la tasa anual implícita de crecimiento de ingresos `g` durante `forecast_years = 10` años tal que `PV(FCF) + PV(Terminal Value) == EV_mercado`, donde `EV_mercado = (Precio × Acciones_B × 1000) + Deuda_Neta_M` y `Terminal Value = FCF_10 × (1 + gn) / (WACC - gn)`.
- **Reverse DCF de 3 Etapas (`solve_reverse_dcf_3stage`)**:
  - Modela un crecimiento inicial `g1` constante entre los años `1..fade_start_year` (por defecto `5`), seguido de un *fade* competitivo lineal entre los años `6..10` hacia el crecimiento terminal `gn` (`terminal_growth = 2.5%`), despejando `g1` por bisección (`80` iteraciones, rango `[-50%, +150%]`).
- **DCF Forward (`calculate_dcf_details`)**:
  - Soporta `model_type="2STAGE"` y `"3STAGE"`, devolviendo `fair_price`, `ev`, `equity_val`, `pv_fcf` y `pv_tv`.
- **Excess Return Model de 2 Etapas para Banca y Seguros (`compute_two_stage_excess_return_ptbv`)**:
  - Calcula el múltiplo justificado `P/TBV` en bancos (`FINANCIAL_BANKING`) y aseguradoras (`INSURANCE`) sobre `fade_years = 5`:
    - *Seguros*: `r_terminal` acotado a `min(rotce, ke + 0.105)` y tasa de retención `0.45`.
    - *Banca*: si `cagr_5y >= 25.0%` (*high-growth bank*), `spread_cap = 0.145` y `retention = 0.72`; en bancos tradicionales, `spread_cap = 0.105` y `retention = 0.40`.
    - Proyecta el crecimiento compuesto del Valor en Libros Tangible (`BV_t`), descuenta los retornos excedentes `(r_t - Ke) × BV_t` de la Etapa 1 y suma el valor presente del exceso terminal `(r_terminal - Ke) / (Ke - g_term)`.
- **Otros Pilares de Valoración**:
  - `calculate_epv_pvgo`: Earnings Power Value (sin crecimiento, descontando `SBC` de `NOPAT` sostenible) y proporción `PVGO` del precio actual.
  - `calculate_eva_valuation`: Valoración por Beneficio Económico (`EVA`) sobre Capital Invertido con *fade* a 10 años.
  - `calculate_5y_forward_irr`: Simulador de TIR esperada a 5 años con *bridge* (`growth_contrib`, `margin_contrib`, `buyback_contrib`, `multiple_contrib`, `div_contrib`).
  - `calculate_multiples_valuation`: Múltiplos actuales (`P/E`, `EV/EBITDA`, `EV/EBIT`, `EV/FCF`, `P/S`, `FCF Yield %`, `PEG`, `PEGY`), medianas de pares y precios imputados (`composite`).
  - `calculate_owner_earnings_and_capex`: Desglose `CapEx Mantenimiento` vs `CapEx Crecimiento` (usando `D&A` o fallback `40%` si falta), `Inversión Neta en I+D`, `Owner Earnings = FCF + Growth CapEx + Net R&D Inv` y despeje `g_implied_oe_pct` vía Reverse DCF de 3 etapas.
  - `get_valuation_football_field`: Rangos `[low, base, high]` de los 5 métodos y precio consenso (mediana).
- **Helpers de serie/formato**: `_compute_series_cagr`, `_compute_share_reduction_rate`, `_fmt_money`, `_fmt_pct`.

---

### 2. [`market_history.py`](./market_history.py)
Series históricas con cotizaciones reales de mercado y trazabilidad contable *White-Box*:

- **Bandas Z-Score Dinámicas (`calculate_z_score_valuation`)**:
  - Calcula `EV / NOPAT Ajustado` sobre cierres trimestrales reales (`period="5y"`, `interval="3mo"` vía `yfinance`, persistidos en `historical_quarterly_prices` dentro de `data/cache/market_data_cache.json`).
  - Construye bandas estadísticas (`-2σ`, `-1σ`, `mean`, `+1σ`, `+2σ`) y estado de valoración (`COMPRA FUERTE`, `VALORACIÓN NORMAL`, `RANGO ALTO`, `EUFORIA`).
  - **Cumplimiento estricto de Regla 6**: si es arquetipo financiero, `NOPAT <= 0`, o no existe histórico real de cotizaciones, retorna `z_score: None` y `status: "N/D (...)"` — **nunca fabrica cotizaciones sintéticas**.
- **Múltiplos Históricos Multianuales (`calculate_historical_multiples_analysis`)**:
  - Obtiene cierres reales al mes de cierre fiscal (`_lookup_fy_close_price`, 8 años de historia vía `yfinance`) para los últimos 5 `FY` + `LTM` (sin factores ficticios como `0.85x`).
  - Rama corporativa (`_compute_corporate_hist_series`): `ev_nopat_adj`, `p_oe`, `pe_gaap`, `ev_ebit`, `ev_ebitda`, `ev_fcf`, `ev_sales`.
  - Rama financiera (`_compute_financial_hist_series`): `p_tbv`, `pe_gaap`, `p_sales`.
  - Calcula mediana, media, mínimo, máximo, desviación porcentual e `imputed_price` (con `status: "N/D (LTM No Disponible o Pérdidas)"` si falta el múltiplo actual).
- **Trazabilidad White-Box (`build_audit_traceability`)**:
  - Paso a paso auditable de `NOPAT Ajustado`, `Owner Earnings`, fórmulas `LaTeX` (`math_formulas`) con valores sustituidos y tabla histórica multianual (`by_period_history`), o dictamen TBV/ROTCE en entidades financieras.

---

### 3. [`market_data_provider.py`](./market_data_provider.py) (`MarketDataExtractor`)
Extractor y validador cruzado en tiempo real de parámetros de mercado con caché persistente:

- **Fuentes y Arbitraje Multi-Fuente**:
  - Consulta en vivo **Yahoo Finance** (`yfinance` + fallback HTTP `query1.finance.yahoo.com/v8/finance/chart/`) y **CNBC Quote Service** (`US10Y` + quote).
  - Arbitra precio (`TOLERANCE_PRICE_PCT = 1.5%`), tasa libre de riesgo a 10 años `^TNX`/`US10Y` (`TOLERANCE_RF_BPS = 10 bps`) y Beta 5Y (`TOLERANCE_BETA = 0.15`).
  - Arbitra acciones diluidas frente a `diluted_shares_10q` (si difieren `> 50%`, prioriza conteo ajustado por split reciente) y calcula `market_cap_usd_m`.
  - Registra bitácora detallada en `audit.notes` (`VALIDATED_CONSENSUS` vs `FALLBACK_OFFLINE`).
- **Caché Persistente en Disco (`data/cache/market_data_cache.json`)**:
  - Resuelve la ruta canónica vía `config_loader.resolve_market_cache_path()` y escribe de forma atómica con `atomic_json_write()`.
  - TTL por defecto: `DEFAULT_CACHE_TTL_SECONDS = 3600` (1 hora), anulable con `bypass_cache=True` (invocado en la web mediante `?refresh=1`).
- **Modo Offline Seguro (`_build_offline_fallback`)**:
  - Si fallan ambas fuentes remotas, preserva precio, acciones y beta previamente cacheados en `data/cache/market_data_cache.json` (respaldado por `sector_beta_fallback`, `rf_10y = 0.0425`, `erp = 0.0475`) marcando `is_offline: True` y `audit.status: "FALLBACK_OFFLINE"`.

---

## 2. Matriz de Impacto ante Modificaciones

| Script Modificado | Artefactos / Cachés Afectados | Consumidores Aguas Abajo (Pipeline y Dashboard Web) | Comandos `unittest` Recomendados tras Editar |
| :--- | :--- | :--- | :--- |
| `dcf_models.py` | Ninguno en disco directamente (cálculo dinámico en tiempo real) | - `pipeline/valuation_engine.py` (`get_valuation_parameters`, `_generate_sensitivity_grid`, `_build_financial_valuation`, `_build_corporate_valuation`)<br>- `web_dashboard/analytics/views/views_valuation.py`<br>- Pestaña `#tab-reversedcf` (`Valoración & Futuro (360°)`: Reverse DCF 2/3 etapas, Excess Return P/TBV, EPV, EVA, 5Y IRR, Owner Earnings, Football Field, Grilla 5×6) | `python -m unittest tests/scoring_valuation/test_valuation_engine.py tests/scoring_valuation/test_capa3_scoring_and_valuation_hygiene.py tests/web_dashboard/test_web_valuation.py -v` |
| `market_history.py` | - Lee/actualiza bloque `historical_quarterly_prices` en `data/cache/market_data_cache.json` | - `pipeline/valuation_engine.py` (`z_score_analysis`, `historical_multiples`, `audit_traceability`)<br>- `web_dashboard/analytics/views/views_valuation.py`<br>- Pestaña `#tab-reversedcf` (Subpestaña Múltiplos Históricos, Bandas Z-Score y Drawer White-Box) | `python -m unittest tests/scoring_valuation/test_capa3_scoring_and_valuation_hygiene.py tests/web_dashboard/test_web_valuation.py tests/e2e_stress/test_challenger_m3_stress.py -v` |
| `market_data_provider.py` | - `data/cache/market_data_cache.json`<br>- Indirecto: `fundamental_scores.json` (`wacc_analysis.market_data`, `wacc`, `ke`, `economic_spread_adjusted`) | - `scoring_modules/profitability_capital.py` (`WACCCalculator`)<br>- `pipeline/financial_scoring_engine.py` (Paso D)<br>- `pipeline/valuation_engine.py`<br>- `web_dashboard/analytics/views/views.py` (`index.html`) y `views_valuation.py` (`#tab-reversedcf`) | `python -m unittest tests/scoring_valuation/test_market_data.py tests/scoring_valuation/test_valuation_engine.py tests/web_dashboard/test_web_valuation.py -v` |

### Verificación Global del Subpaquete

```powershell
python -m unittest discover -s tests/scoring_valuation -v
```
