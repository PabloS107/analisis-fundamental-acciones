# Submódulos Cuantitativos de Scoring, Rentabilidad, Forense y Solvencia (`pipeline/scoring_modules/`)

Contiene los **5 módulos cuantitativos** orquestados por [`../financial_scoring_engine.py`](../financial_scoring_engine.py) para generar el artefacto `data/processed/{TICKER}/fundamental_scores.json` a lo largo de 10 años fiscales (`FY`) y `LTM`.

---

## 1. Catálogo de Scripts y Modelos Implementados

### 1. [`scoring_utils.py`](./scoring_utils.py)
Infraestructura de datos, benchmarks sectoriales y normalización contable por período:
- **Utilidades numéricas y temporales**: `_safe_float`, `_to_millions` (escala a `$M` si `abs(val) > 1e6`), `_clean_sic_code`, `_chronological_annual_fys`, `_linear_percentile`.
- **Benchmarks dinámicos**: `load_industry_medians()` (`config/industry_medians.json`), `load_peer_benchmarks()` (`config/peer_benchmarks.json`), `compute_peer_benchmarks()` (medianas y percentil 75 calculados dinámicamente desde los pares: ROA, CFROA, GP/A, GP/A ex-caja, Margen Bruto, Rotación, ROIC tradicional/ajustado, WACC, Spread Económico y ROC Greenblatt) y `get_sector_benchmarks()` (búsqueda por SIC exacto -> ticker -> prefijo SIC 3/2 dígitos -> arquetipo `_ARCHETYPE_TO_SIC` -> `BROAD_MARKET`).
- **Extracción estandarizada por período (`extract_period_metrics`)**: resuelve jerárquicamente deuda (`_COMBINED_DEBT_TAGS`, `_LT_DEBT_TAGS`, `_ST_DEBT_TAGS`), capital de trabajo (`ar`, `inv`, `other_current_assets`), `gross_ppe`, `accumulated_depreciation`, `depreciation_and_amortization`, `effective_tax_rate` (acotada a `[0.05, 0.35]`, respaldo `0.21`), `goodwill`, `intangible_assets`, e indicadores inmobiliarios (`ffo`, `affo`, `real_estate_depreciation`).

---

### 2. [`piotroski_mohanram.py`](./piotroski_mohanram.py)
Evalúa salud financiera histórica y calidad del crecimiento mediante **3 calculadores**:

1. **`PiotroskiScoreCalculator` (Piotroski F-Score, escala `0–9`)**:
   - *Rentabilidad (4 pts)*: `F_ROA` (`NI / Avg Assets > 0`), `F_CFO` (`CFO > 0`), `F_dROA` (`ΔROA > 0`), `F_ACCRUAL` (`CFO > NI`).
   - *Apalancamiento y Liquidez (3 pts)*: `F_dLEVER` (`Δ(Debt / Assets) <= 0.0001`), `F_dLIQUID` (`ΔCurrent Ratio > 0`), `EQ_OFFER` (`ΔBasic Shares <= 0.01%` del capital previo).
   - *Eficiencia Operativa (2 pts)*: `F_dMARGIN` (`ΔGross Margin > 0`), `F_dTURN` (`ΔAsset Turnover > 0`).
   - Bandas: `>= 8` (`SALUD EXCEPCIONAL`), `6–7` (`SALUD SÓLIDA`), `5` (`SALUD MODERADA`), `< 5` (`VULNERABILIDAD FINANCIERA`).

2. **`MohanramScoreCalculator` (Mohanram G-Score, escala `0–8`)**:
   - *Rentabilidad vs. Mediana del Sector (3 pts)*: `G1_ROA` (`ROA > median_roa`), `G2_CFROA` (`CFROA > median_cfroa`), `G3_ACCRUAL` (`CFO > NI`).
   - *Estabilidad y Predictibilidad (2 pts)*: `G4_VAR_ROA` (`CV(ROA) < median_cv_roa` o `ROA >= p75_roa`), `G5_VAR_GROWTH` (`CV(Crecimiento Ventas) < median_cv_sales_growth` o crecimiento `>= 20%`).
   - *Inversión en Futuro e Intangibles (3 pts)*: `G6_RD_INTENSITY` (`I+D / Assets > median_rd_intensity`), `G7_CAPEX_INTENSITY` (evalúa `(CapEx + I+D) / Assets > median_total_reinvestment` cuando `is_asset_light=True`, o `CapEx / Assets > median_capex_intensity` en caso contrario), `G8_OPERATING_LEVERAGE` (`%ΔVentas > %ΔSG&A`).
   - Bandas: `>= 6` (`CRECIMIENTO DE ÉLITE`), `4–5` (`CRECIMIENTO PROMEDIO`), `< 4` (`CRECIMIENTO FRÁGIL`).

3. **`CombinedMatrixClassifier` (Matriz Estratégica 2×2 F/G)**:
   - `F >= 6 y G >= 6`: `CUADRANTE I: COMPOUNDER DE ÉLITE`
   - `F < 6 y G >= 6`: `CUADRANTE II: CRECIMIENTO VULNERABLE`
   - `F >= 6 y G < 6`: `CUADRANTE III: GENERADOR MADURO (CASH COW)`
   - `F < 6 y G < 6`: `CUADRANTE IV: TRAMPA DE VALOR / DETERIORO`

---

### 3. [`profitability_capital.py`](./profitability_capital.py)
Motores de productividad del capital y costo de financiamiento:

1. **`NovyMarxCalculator` (Gross Profitability to Assets — GP/A, 2013)**:
   - Calcula `gross_profitability_total = GP / Total Assets`, `gross_profitability_ex_cash = GP / (Total Assets - Cash)`, `cash_drag_pct`, descomposición DuPont (`gross_margin × asset_turnover_total` con verificación `dupont_verified`), cuadrantes DuPont I–IV, percentil sectorial (`Top 5%`, `Top 25%`, `> Mediana`, `< Mediana`), tendencia a 3 y 5 años, `cv_gpa` y tabla ordenada `peer_ranking`.
   - En `FINANCIAL_BANKING` e `INSURANCE` devuelve `is_applicable=False` y `pedagogical_guidance` (Regla 3).

2. **`IntangibleROICCalculator` (ROIC Ajustado por Intangibles — Damodaran / Mauboussin)**:
   - Realiza un *roll-forward* cronológico capitalizando el gasto en I+D (`rd_useful_life_years`, defecto `4` años) y el porcentaje sectorial de SG&A (`sga_capitalization_pct`, `sga_useful_life_years`, defecto `2` años), construyendo `rd_stock`, `mkt_stock` y `total_intangible_stock`.
   - Calcula `ebit_adj`, `nopat_trad`, `nopat_adj`, capital invertido final y promedio (`ic_trad_avg`, `ic_adj_avg`), `roic_trad`, `roic_adj` y matriz de sensibilidad (`n_minus_1`, `n_base`, `n_plus_1`).
   - Para `REAL_ESTATE_REIT`: ajusta por depreciación inmobiliaria y CapEx de mantenimiento (`ebit_adj = ebit + re_dep - maint_capex`, `ic_trad_end = assets + accum_dep - cash - nibcl`) sin capitalizar intangibles.

3. **`GreenblattROCCalculator` (Return on Capital — Magic Formula)**:
   - `ROC = EBIT / Average Operating Tangible Capital`, donde el capital tangible operativo es `(Current Assets - Cash) - (Current Liabilities - Short-Term Debt) + Net PP&E` con salvaguarda inferior en `Net PP&E` cuando `NWC < 0` y piso `max(1.0, ...)`.
   - Compara frente a `peer_greenblatt_roc_median` e inhibe el cálculo (`is_applicable=False` + `pedagogical_guidance`) en `FINANCIAL_BANKING` e `INSURANCE`.

4. **`WACCCalculator` (CAPM, WACC/Ke y Economic Spread / Moat)**:
   - Consume datos de mercado en vivo/caché desde `MarketDataExtractor.get_market_data()` (`rf_10y`, `beta`, `erp`, `market_cap_usd_m`).
   - **Corporaciones, Plataformas y REITs (`model_type = "WACC"`)**: `Ke = Rf + Beta × ERP`, `Kd_after_tax = Kd_pre_tax × (1 - tax_rate)` (con piso de interés implícito `rf + 0.006` si `kd_pre_tax < 2%`, o libre de deuda si `debt <= $1M`), ponderación a valor de mercado (`EV = Market Cap + Debt`), `WACC = We·Ke + Wd·Kd_after_tax` y `Spread = ROIC_adj - WACC`.
   - **Banca y Seguros (`model_type = "COST_OF_EQUITY_KE"`)**: aplica ajuste de reversión a la media tipo **Blume Beta** cuando `beta < 0.80` (`beta = 0.67 * beta + 0.33 * 1.0`) y piso `ke = max(rf + beta * erp, rf + 0.0325)` con `we=1.0`, `wd=0.0`; calcula `TBV = Equity - Goodwill - Intangibles`, `ROE`, `ROTCE` y `Spread = ROTCE (o ROE) - Ke`.
   - Clasifica el Moat según el spread (`>= 15 pp` `WIDE MOAT`, `5–15 pp` `NARROW MOAT`, `0–5 pp` `ESTÁNDAR`, `< 0 pp` `DESTRUCCIÓN DE VALOR`).

---

### 4. [`forensic_accounting.py`](./forensic_accounting.py) (`ForensicAccountingEngine`)
Implementa **3 modelos forenses** para calidad de beneficios y detección de anomalías contables *(nota: **Beneish M-Score no está implementado** en la base de código actual)*:
1. **Ratio de Devengos de Sloan (`sloan_accrual_analysis`)**: `(Net Income - CFO) / Avg Total Assets`. Bandas: `< -3%` (`EXCELENTE`), `-3% a +7%` (`SALUDABLE`), `+7% a +10%` (`PRECAUCIÓN`), `> +10%` (`ALERTA ROJA`).
2. **Matriz de Divergencias (`divergence_matrix`)**:
   - `ar_sales_spread`: `%ΔAR - %ΔVentas` y variación en días de cobro (`DSO`); alerta si `spread > 10%` y `ΔDSO > +5.0 días`.
   - `inv_cogs_spread`: `%ΔInventarios - %ΔCOGS` y variación de `DIO`; alerta si `spread > 15%` y `ΔDIO > +7.0 días`.
   - `soft_assets`: `(Total Assets - Net PP&E - Cash) / Total Assets`; alerta si `ratio > 75%` y `Δ > +3.0 pp`.
3. **Montier C-Score (`montier_c_score`, escala `0–6`)**: suma 6 banderas binarias (`f1_cfo_divergence`: `NI > CFO`; `f2_ar_vs_sales`: `ΔDSO > 0` o `%ΔAR > %ΔVentas`; `f3_inv_vs_cogs`: `ΔDIO > 0` o `%ΔInv > %ΔCOGS`, `0` si no hay inventario; `f4_other_current_assets`: incremento en `Otros Activos Corrientes / Ventas > 0.001`; `f5_depreciation_rate`: caída `> 0.5 pp` en `D&A / Gross PP&E`; `f6_asset_growth`: `ΔActivos > 15%` y `> 1.15 × ΔVentas`).
- Consolida `forensic_verdict`, `global_badge` y `global_color`. En `FINANCIAL_BANKING` e `INSURANCE`, Sloan, AR/Ventas, Inventarios/COGS y Montier C-Score retornan estado `NO APLICABLE` preservando `soft_assets` en la matriz de divergencias.

---

### 5. [`solvency_credit.py`](./solvency_credit.py) (`DebtSolvencyEngine`)
Evalúa apalancamiento, cobertura, liquidez y riesgo de crédito en 4 bloques por período:
1. **`cash_flow_leverage`**: `net_debt`, `ebitda`, `fcf`, `net_debt_to_ebitda` (`CAJA NETA`, `< 1.5x`, `1.5x–3.0x`, `3.0x–4.0x`, `> 4.0x`), `net_debt_to_fcf` y `debt_to_cfo`.
2. **`debt_service`**: cobertura de intereses (`EBIT / Interest` y `CFO / Interest` en corporativas; `EBITDAre / Interest` con umbrales `>= 4.5x`, `3.2x`, `2.2x` en `REAL_ESTATE_REIT`; ratio `Equity / Assets` en `FINANCIAL_BANKING` / `INSURANCE`).
3. **`liquidity_and_refinancing`**: `current_ratio`, `quick_ratio`, `cash_ratio`, `rollover_risk_pct` (`ST Debt / Total Debt`) y `debt_to_capital_pct`.
4. **`distress_and_credit_models`**:
   - **Altman Z''-Score (4 variables)**: `Z'' = 6.56·X1 + 3.26·X2 + 6.72·X3 + 1.05·X4` (`> 2.60` Zona Segura, `1.10–2.60` Zona Gris, `< 1.10` Distress). Inhibido con `is_applicable=False` y `pedagogical_guidance` para `FINANCIAL_BANKING`, `INSURANCE` y `REAL_ESTATE_REIT`.
   - **Rating Sintético Damodaran (`AAA` a `D`)**: asigna `synthetic_rating`, `default_spread_pct` y `default_probability` vía tabla `_SYNTHETIC_RATING_TABLE` sobre cobertura de intereses (con ajuste `1.25x` en REITs), o mediante capitalización (`Equity / Assets`) y `ROE` en banca/seguros (`AA-`, `A+`, `BBB+`, `BB`).

---

## 2. Ramificación por los 5 Arquetipos Contables

| Modelo / Motor | `STANDARD_CORPORATE` | `PLATFORM_ECOSYSTEM` | `REAL_ESTATE_REIT` | `FINANCIAL_BANKING` | `INSURANCE` |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Piotroski F-Score (0–9)** | Completo | Completo | Completo | Calculado (señales corrientes `N/A` si no hay CA/CL o GP) | Calculado (señales corrientes `N/A` si no hay CA/CL o GP) |
| **Mohanram G-Score (0–8)** | Completo (SIC) | Completo (`SIC_7389`) | Completo (`SIC_6798`) | Completo (`SIC_6021`) | Completo (`SIC_6331`) |
| **Novy-Marx GP/A** | Completo | Completo | Completo (`GP` vía NOI si falta `GrossProfit`) | **Inhibido** (`NO APLICABLE` + guía pedagógica) | **Inhibido** (`NO APLICABLE` + guía pedagógica) |
| **Intangible ROIC** | Capitaliza I+D + %SG&A | Capitaliza I+D + %SG&A | **Adaptado REIT** (`ebit + re_dep - maint_capex`, sin intangibles) | Usa métricas financieras en `WACCCalculator` | Usa métricas financieras en `WACCCalculator` |
| **Greenblatt ROC** | Completo | Completo | Completo | **Inhibido** (`NO APLICABLE` + guía pedagógica) | **Inhibido** (`NO APLICABLE` + guía pedagógica) |
| **WACC / Ke** | WACC (`We·Ke + Wd·Kd`) | WACC (`We·Ke + Wd·Kd`) | WACC (`We·Ke + Wd·Kd`) | **Ke CAPM + Blume Beta** (`< 0.80`), `ROTCE/ROE - Ke` | **Ke CAPM + Blume Beta** (`< 0.80`), `ROTCE/ROE - Ke` |
| **Forense (Sloan, Div., Montier)** | Completo | Completo | Completo | **Inhibido** (`NO APLICABLE`, conserva `soft_assets`) | **Inhibido** (`NO APLICABLE`, conserva `soft_assets`) |
| **Cobertura Deuda & Solvencia** | `EBIT / Int` + Rating Damodaran | `EBIT / Int` + Rating Damodaran | `EBITDAre / Int` + Rating `1.25x` | `Equity / Assets` + Rating bancario (`AA-`..`BB`) | `Equity / Assets` + Rating asegurador (`AA-`..`BB`) |
| **Altman Z''-Score** | Completo | Completo | **Inhibido** (`NO APLICABLE` + guía) | **Inhibido** (`NO APLICABLE` + guía) | **Inhibido** (`NO APLICABLE` + guía) |

---

## 3. Matriz de Impacto sobre `fundamental_scores.json` y Dashboard Web

| Script Modificado | Claves de `fundamental_scores.json` Afectadas | Módulos Aguas Abajo y Pestañas Web Dependientes | Comandos `unittest` Recomendados tras Editar |
| :--- | :--- | :--- | :--- |
| `scoring_utils.py` | Todas (`benchmarks_used`, `sic_code`, `industry_name`, insumos de todos los calculadores) | - Todos los demás módulos de `scoring_modules/`<br>- `financial_scoring_engine.py`, `valuation_engine.py`<br>- `views_scoring_quality.py`, `views.py` (`index.html` + `#tab-quality`, `#tab-forensic`, `#tab-reversedcf`) | `python -m unittest tests/scoring_valuation/test_scoring_engine.py tests/scoring_valuation/test_capa3_scoring_and_valuation_hygiene.py -v` |
| `piotroski_mohanram.py` | - `piotroski_f_score`<br>- `mohanram_g_score`<br>- `combined_matrix`<br>- `latest_diagnosis` (`f_score`, `g_score`, `quadrant`, `investment_thesis`) | - `views.py` (`_build_index_card` en `index.html`)<br>- `views_scoring_quality.py` -> Pestaña `#tab-quality` y barra superior de `company_detail.html` | `python -m unittest tests/scoring_valuation/test_scoring_engine.py tests/e2e_stress/test_e2e_universal_orchestrator.py -v` |
| `profitability_capital.py` | - `novy_marx_analysis`<br>- `intangible_roic_analysis`<br>- `greenblatt_roc_analysis`<br>- `wacc_analysis` / `wacc_and_spread_analysis` / `roic_wacc_analysis`<br>- `latest_diagnosis` (`novy_marx`, `greenblatt_roc`, `roic_wacc`) | - `valuation_engine.py` (`wacc`, `ke`, `roic_adjusted`, `tangible_book_value_usd_m`, `nopat_adj` histórico)<br>- `valuation_modules/market_history.py` (series `nopat_adj`)<br>- `views.py` (`index.html`), `views_scoring_quality.py` (`#tab-quality`), `views_valuation.py` (`#tab-reversedcf`) | `python -m unittest tests/scoring_valuation/test_roc_greenblatt.py tests/scoring_valuation/test_capa3_scoring_and_valuation_hygiene.py tests/e2e_stress/test_challenger_m2_2_adversarial.py -v` |
| `forensic_accounting.py` | - `forensic_accounting_analysis`<br>- `latest_diagnosis.forensic_audit` | - `views_scoring_forensics.py` (`build_sloan_detail`, `build_montier_detail`)<br>- Pestaña `#tab-forensic` (`Auditoría Forense & Solvencia Financiera`) | `python -m unittest tests/scoring_valuation/test_forensic_engine.py tests/web_dashboard/test_web_forensics.py -v` |
| `solvency_credit.py` | - `debt_and_solvency_analysis`<br>- `latest_diagnosis.solvency_credit` | - `valuation_engine.py` (lee `cash_flow_leverage`: `ebit`, `capex`, `fcf`, `dna`, `net_debt`)<br>- `views.py` (`index.html`), `views_scoring_forensics.py` (`#tab-forensic`), cabecera de `company_detail.html` (`rating_synth`) | `python -m unittest tests/scoring_valuation/test_solvency_engine.py tests/e2e_stress/test_challenger_m2_stress.py tests/web_dashboard/test_web_forensics.py -v` |

### Verificación Global del Subpaquete

```powershell
python -m unittest discover -s tests/scoring_valuation -v
```
