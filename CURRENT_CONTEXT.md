# ESTADO Y CONTEXTO DEL PROYECTO: ORQUESTADOR UNIVERSAL DE ANÁLISIS FUNDAMENTAL

**Última actualización:** 11 de Noviembre de 2026 (Reorganización estructural de `pipeline/`, `tests/` y guías `README.md`)  
**Rama activa de Git:** `main` (sincronizada con `origin/main`)  
**Estado del sistema:** ✅ Operativo | `unittest discover -s tests`: **413 PASS / 2 SKIP / 1 FAIL preexistente** (`test_web_statements.py:460` tras sync LTM AAPL en `4b453fa`) | Django `analytics`: **6/6 PASS** | `health_check.test_skills_integrity`: **PASS (32 scripts)** | Cero regresiones de rutas/imports  
**Tag de respaldo local:** `archive/banking-excel-d5a4c61` (commit banking-Excel eliminado, preservado en local)  
**Notas de arquitectura del almacenamiento:** el proyecto sigue sirviendo JSON como artefacto canónico; ver Sección 7 (Opción A aplicada) y Sección 8 (hallazgos de auditoría y pendientes).
**Universo activo de control y validación (9 empresas en 5 arquetipos contables):**
- **Corporativo / Industrial:** `AAPL` (Apple), `DECK` (Deckers Outdoor), `NVDA` (NVIDIA)
- **Banca Tradicional y Digital:** `NU` (Nubank), `JPM` (JPMorgan Chase)
- **Aseguradoras:** `PGR` (Progressive Corporation)
- **Inmobiliario / REITs:** `O` (Realty Income)
- **Plataformas Tecnológicas Híbridas:** `MELI` (MercadoLibre)
- **Big Tech Diversificada:** `META` (Meta Platforms)

---

## 1. Arquitectura del Proyecto y Principios Fundamentales

Este proyecto es un **Orquestador Universal de Análisis Fundamental Institucional** que procesa filings oficiales auditados de la SEC EDGAR (10-K, 10-Q), presentaciones a inversores y transcripciones de earnings calls, generando:
1. Modelos de datos estructurados canónicos en JSON (`data/processed/{TICKER}/financial_statements.json`, `fundamental_scores.json`, `audit_report.json`).
2. Informes institucionales de valoración y auditoría en Word (`.docx`) y Markdown (`.md`).
3. Un **Dashboard Web Interactivo en Django** (`web_dashboard/`) con interfaz estilo terminal financiera (**Fiscal.ai** / Bloomberg), con pestañas especializadas: Estados Financieros dinámicos (3 modos), Segmentos y Geografía, Rentabilidad y Asignación de Capital, Calidad de Negocio, Auditoría Forense y Solvencia, y Simulador de Valoración (Reverse DCF / Excess Return 2-Etapas).

### Reglas de Operación Estrictas ([AGENTS.md](file:///c:/Users/pablo/OneDrive/Documents/Analisis%20fundamental%20de%20acciones/AGENTS.md)):
- **Regla 1 (STOP & PROPOSE):** Parada obligatoria ante errores de cálculo, diseño o excepciones; diagnóstico forense previo y validación obligatoria del usuario antes de tocar el código.
- **Regla 2 (Verificación Triangulada Obligatoria):** Todo cambio debe validarse multidimensionalmente (test lógico unitario, test de regresión cruzada con empresas de control, inspección visual de artefactos reales).
- **Regla 3 (Pedagogía Contable Transparente):** En entidades financieras o modelos atípicos, los ratios deben acompañarse de su fórmula, interpretación y justificación institucional.
- **Regla 4 (Universalidad sin Hardcodear Tickers):** Prohibido el uso de `if ticker == "..."`. Todo cálculo debe derivarse dinámicamente del perfil contable y de los datos procesados (`data/processed/{TICKER}/`).
- **Regla 5 (Cero Código Muerto):** Prohibido conservar ramas erróneas comentadas o parches acumulativos; refactorización canónica limpia.
- **Regla 6 (Cero Datos Inventados / Observabilidad N/D):** Prohibida la imputación de valores falsos o ceros arbitrarios; señalización explícita como `N/D` y registro en `audit_report.json`.
- **Regla 7 (Auto-Sync a GitHub):** Commit y push inmediato a `origin/main` tras verificar satisfactoriamente cualquier cambio.

---

## 2. Los 5 Arquetipos Contables del Motor

El motor clasifica dinámicamente cada compañía según su naturaleza financiera y normativa contable (SEC/US-GAAP/IFRS):

| Arquetipo | Identificador | Empresas de Control | Métricas Clave Específicas | Métricas Excluidas / Ajustadas |
| :--- | :--- | :--- | :--- | :--- |
| **Corporativo Estándar** | `CORPORATE` | `AAPL`, `DECK`, `NVDA` | Gross Margin, EBIT, EBITDA, FCF, NOPAT, ROIC Damodaran, Novy-Marx GP/A, Piotroski F-Score | Aplica cascade completo de 14 secciones corporativas. |
| **Banca y Neobancos** | `FINANCIAL_BANKING` | `NU`, `JPM` | Margen de Intereses (NII), Net Interest Margin (NIM), Risk-Adjusted NIM, Cost-to-Income, Ratio CET1, NPLs (15-90d, >90d), Cobertura, Cost of Risk, ROTCE vs Ke | Excluye COGS, Gross Profit, FCF tradicional, Capital de Trabajo y Altman Z'' (evitando falsos positivos de quiebra). |
| **Aseguradoras** | `INSURANCE` | `PGR` | Combined Ratio (Loss Ratio + Expense Ratio), Primas Emitidas (GWP/NWP), Rendimiento de Cartera de Inversión (Float), Ratio de Solvencia / RBC, ROE vs Ke | Excluye WACC corporativo tradicional; aplica Blume Adjusted Beta con piso prudencial de Cost of Equity ($K_e \ge r_f + 3.25\%$). |
| **Inmobiliario** | `REIT` | `O` | FFO (Funds From Operations), AFFO (Adjusted FFO), Tasa de Ocupación, Deuda Neta / EBITDAre, Cobertura de Intereses | Reemplaza el FCF por AFFO; neutraliza la depreciación inmobiliaria no monetaria. |
| **Plataformas Híbridas** | `PLATFORM_HYBRID` | `MELI` | Desglose Segmental (Commerce + FinTech / Mercado Pago), Normalización de Fondos de Clientes (Float), FCF Normalizado | Aísla el capital de trabajo de los depósitos transaccionales de clientes para evitar distorsiones en el Reverse DCF. |

---

## 3. Hitos e Implementaciones Recientes (Fases 1 a 5)

### FASE 1: Segmentos de Negocio y Geografía Dinámica
- Generación dinámica de `segments_data.json` y visualización jerárquica con tarjetas informativas y badges de concentración.
- Cuadre del 100.0% de los segmentos primarios contra los ingresos netos consolidados del P&L.
- Soporte para marcas (`DECK`: UGG, HOKA), plataformas (`NVDA`: Data Center Hyperscale vs AI Enterprise, Edge Computing), divisiones (`META`: Family of Apps vs Reality Labs) y carteras de crédito (`NU`: NII vs Fees).

### FASE 2: Capital Allocation Framework y Recompras de Mercado Abierto
- Extracción purificada de flujos de capital en `resolve_canonical_capital_flows`:
  - Aislamiento de recompras en mercado abierto (`share_repurchases_open_market`) separadas de retenciones fiscales por RSUs (`share_repurchases_sbc_tax`).
  - Identidad de retorno total al accionista: `Recompras Netas + Dividendos Pagados`.
  - Tarjetas acumuladas en años fiscales cerrados (sin duplicar el último ejercicio con LTM).
  - Paleta institucional de alto contraste en gráficos Chart.js.

### FASE 3: Motor de Valoración y Modelo Excess Return 2-Etapas
- **Ajuste Blume de Beta y Piso Institucional de $K_e$ (`financial_scoring_engine.py`):**
  - Para entidades financieras y aseguradoras (`FINANCIAL_BANKING`, `INSURANCE`), las betas históricas extremas convergen hacia la media del mercado: $\text{Beta}_{\text{Blume}} = 0.67 \times \text{Beta}_{\text{raw}} + 0.33 \times 1.0$.
  - Piso prudencial institucional: $K_e = \max(r_f + \beta \times \text{ERP}, r_f + 0.0325)$.
- **Modelo Excess Return de 2 Etapas con Fade (`valuation_report_builder.py`):**
  - Sustituyó la fórmula perpetua de 1 etapa que distorsionaba el valor en picos de ciclo o fases de hipercrecimiento (ej. PGR con ROE 34% o NU con crecimiento >40%).
  - Etapa 1: Crecimiento explícito con desvanecimiento lineal (*fade*) de 5 años del ROTCE/ROE hacia el retorno de equilibrio a largo plazo.
  - Etapa 2: Valor terminal con $g = 2.5\% - 3.0\%$.

### FASE 4: Sincronización del Simulador Web y Matriz de Sensibilidad
- **Sincronización del Slider (`company_detail.html` y `views.py`):**
  - Limitación del slider de crecimiento proyectado a `init_growth_disp` ($\le 20.0\%$), evitando que el Reverse DCF arranque con tasas extremas no sostenibles (48.7% en MELI o 66.9% en NVDA).
- **Simulador JavaScript Excess Return 2-Etapas:**
  - Implementada la función `computeTwoStagePtbv(rotceVal, keVal, gTerm, cagr5y, isIns)` en el front-end con idéntica formulación matemática a Python, garantizando paridad exacta entre el informe y el simulador interactivo.

### FASE 5: Saneamiento Universal de la Pestaña "📑 Estados Financieros" (Fiscal.ai Style)
- **P&L Cascade:**
  - Lógica universal que detecta si corresponde mostrar desglose granular (`Ventas y Marketing` + `Gastos Generales y Admin`) o fila continua `Total Gastos de Venta, Generales y Admin (SG&A Consolidado)` (evitando celdas vacías en `AAPL` o `NVDA`).
  - Conciliación de notas al pie de I+D (ej. `DECK`), deduciendo I+D del SG&A para que la suma cuadre exactamente con `Total OpEx`.
- **Balance General Clasificado:**
  - Deduplicación de Fondo de Comercio e Intangibles; eliminación de notas no materiales en LTM (`AAPL` saneado de $50,834M espurios a `-`).
  - Cuadre residual en Activos No Corrientes: `sum(Activos No Corrientes) == Total Activos No Corrientes`.
  - Fallback universal para pasivos acumulados (`Accrued Liabilities`) y derivación canónica de APIC (`META`: $103,981M).
  - Partida doble perfecta: $\text{Total Activos} = \text{Total Pasivos} + \text{Patrimonio Neto}$ en el 100% de períodos y empresas.
- **Flujos de Caja Reconciliados al Céntimo:**
  - **CFI:** Partida residual `Inversión Neta en Valores Negociables y Otros Activos de Inversión` calculada como `cfi_v - (-abs(capex) - abs(ma))`, garantizando que $(-CapEx) + (-M&A) + Inversión Neta == CFI$.
  - **CFF:** Partida residual `Emisión de Acciones y Otros Flujos de Financiación` garantizando que $(-Total Recompras) + (-Dividendos) + (±Deuda) + (±Otros) == CFF$.
- **Saneamiento Canónico en Datos Procesados (`financial_statements.json`):**
  - Claves canónicas (`rd_expense`, `sga_expense`, `sm_expense`, `ga_expense`, `operating_expenses`, `interest_expense`) pobladas para `AAPL`, `DECK`, `META` y `NVDA`.
  - Dividendo LTM de `NVDA` ajustado al dato auditado real de $974.0M (eliminando la cifra distorsionada de $6,776M).
  - Deuda LTM de `NVDA` ajustada al stock point-in-time de cierre de período ($7,469M LP / $8,468M total, eliminando la suma trimestral errónea de $32,366M).

---

## 4. Estado de Verificación Triangulada y Salud del Sistema

La suite de pruebas automatizadas y el protocolo de verificación cruzada se encuentran en **100.0% de aprobación**:

```bash
# 1. Tests de Estados Financieros Web y Reconciliaciones:
python -m unittest tests/test_web_statements.py
# Ran 20 tests — OK (100% PASS)

# 2. Tests de Vistas, Valoración y Sensibilidad Django:
python web_dashboard/manage.py test analytics
# Ran 6 tests — OK (100% PASS)

# 3. Auditoría Contable y Health Check del Universo Completo:
python tests/health_check.py
# Fidelidad contable: 100.0% en las 9 empresas:
#   AAPL: 77/77 PASS | DECK: 70/70 PASS | JPM: 50/50 PASS
#   MELI: 69/69 PASS | META: 76/76 PASS | NU:  23/23 PASS
#   NVDA: 76/76 PASS | O:    55/55 PASS | PGR: 51/51 PASS
# Pruebas Superadas: 13 / 13 | Fallos: 0 | Advertencias: 0

# 4. Suite Completa del Repositorio:
python -m unittest discover -s tests -v
# Ran 55 tests — OK (100% PASS)
```

---

## 5. Estructura de Directorios Clave

```text
Analisis fundamental de acciones/
├── AGENTS.md                           # Reglas obligatorias irrestrictas (STOP & PROPOSE, Reglas 1–7)
├── CURRENT_CONTEXT.md                  # Este archivo (SSOT del contexto y estado vivo del proyecto)
├── QA_REPORT.md                        # Reporte automático generado por tests/health_check.py
├── README.md                           # Guía general actualizada del Orquestador Universal
├── Iniciar_Dashboard_Web.bat           # Lanzador 1-clic en Windows para el Dashboard Web Django
├── pyproject.toml / requirements.txt   # Metadatos y dependencias Python del proyecto
├── pipeline/                           # Motor central (5 fachadas + 5 subpaquetes temáticos + 6 README.md)
│   ├── __init__.py                     # Extiende __path__ y sys.path con los 5 subpaquetes (100% retrocompatible)
│   ├── README.md                       # Arquitectura global del pipeline y matriz de impacto de fachadas
│   ├── fundamental_pipeline.py         # Orquestador CLI y programático (Pre-Flight + Pasos A–E)
│   ├── sec_extractor.py                # Fachada pública de extracción SEC XBRL US-GAAP/IFRS y segmentos
│   ├── financial_scoring_engine.py     # Fachada de F/G-Score, Novy-Marx, ROIC, WACC/Ke, Forense y Solvencia
│   ├── valuation_engine.py             # Fachada de Reverse DCF (2/3 etapas), Excess Return y sensibilidad
│   ├── audit_engine.py                 # Fachada de auditoría de identidades contables y sanidad
│   ├── sec_modules/                    # 12 módulos SEC + __init__.py + README.md (taxonomía, LTM, segmentos, KPIs, gobernanza)
│   ├── audit_modules/                  # data_verifier.py, period_integrity.py + __init__.py + README.md
│   ├── scoring_modules/                # 5 módulos cuantitativos + __init__.py + README.md
│   ├── valuation_modules/              # dcf_models.py, market_history.py, market_data_provider.py + __init__.py + README.md
│   └── infra/                          # config_loader.py, json_io.py, sec_rate_limiter.py, drive_manager.py, sync_to_drive.py + __init__.py + README.md
├── web_dashboard/                      # Aplicación Web Django (Terminal Financiero Interactivo)
│   ├── README.md                       # Arquitectura Django, caché mtime+size y matriz de impacto
│   ├── manage.py                       # CLI de Django
│   ├── web_dashboard/                  # settings.py (LocMemCache), urls.py, wsgi.py, asgi.py
│   ├── analytics/                      # context_processors, json_cache, pipeline_runner, urls, tests
│   │   └── views/                      # 14 módulos cohesivos por pestaña/arquetipo + README.md (matriz visual/datos)
│   └── templates/                      # base.html, index.html, company_detail.html (6 pestañas + simulador JS)
├── tests/                              # Suite modular de pruebas automatizadas (416 tests + health_check)
│   ├── __init__.py                     # Configura sys.path, importa pipeline y desambigua web_dashboard.__path__
│   ├── README.md                       # Mapa completo de suites y guía rápida de ejecución por módulo
│   ├── health_check.py                 # Diagnóstico integral (SEC API, Drive, Skills 32 scripts y auditoría)
│   ├── sec_extraction/                 # 8 suites (arquetipos, IFRS, KPIs, XBRL, frescura, rate limiter, context)
│   ├── accounting_audit/               # 8 suites (P&L, balance, flujos, As-Reported, OpEx/EBIT, período)
│   ├── scoring_valuation/              # 7 suites (Capa 3 AST, F/G-Score, ROC, forense, solvencia, mercado, DCF)
│   ├── web_dashboard/                  # 8 suites (Capa 4 AST, runner, Drive, gráficos, segmentos, vistas web)
│   └── e2e_stress/                     # 7 suites (Challengers M1/M2/M3, E2E multi-arquetipo y estrés empírico)
├── config/                             # sec_config.json, industry_medians.json, peer_benchmarks.json + README.md
├── docs/                               # Especificacion_Calculos_FScore_GScore.txt + README.md
├── drive_input/                        # Acceso/respaldo local de presentaciones y datos Drive
└── data/                               # cache/ (efímero) y processed/{TICKER}/ (datasets JSON canónicos auditados)
```

---

## 6. Procedimiento para Futuras Modificaciones (Protocolo de Actualización Continua)

A partir de este hito, **cada intervención o cambio en el repositorio debe seguir este ciclo**:
1. **Pausa y Diagnóstico (Regla 1):** Identificar la causa raíz técnica y contable, y presentar la propuesta STOP & PROPOSE para aprobación del usuario.
2. **Implementación Universal (Reglas 4, 5 y 6):** Aplicar correcciones a nivel de motor raíz (`pipeline/` o `views.py`), sin hardcodear tickers, eliminando código muerto y sin inventar cifras.
3. **Verificación Triangulada (Regla 2):** Ejecutar las suites de pruebas (`tests/test_web_statements.py`, `health_check.py`, Django tests).
4. **Actualización del Contexto (`CURRENT_CONTEXT.md`):** Registrar las modificaciones, decisiones de diseño tomadas y el nuevo estado del sistema en este archivo.
5. **Auto-Sync a GitHub (Regla 7):** Realizar `git add .`, `git commit` descriptivo y `git push origin <rama>` de forma inmediata.

---

## 7. Sesión 2026-11-09 (Registro de la intervención)

### A. Limpieza del repositorio y ramas
- Eliminadas 7 ramas locales: master y prueba (ancestras de main), y las 4 del commit banking-Excel (d5a4c61, ligado al flujo Excel/docx ya eliminado del proyecto) + audit_project_scripts.
- d5a4c61 preservado en tag local archive/banking-excel-d5a4c61. Eliminados también sus 3 worktrees (código Excel/docx/presentación, sin commit), descartando trabajo en proceso por decisión del usuario.
- fix/estados-financieros-auditoria conservada (fixes LTM de caja/balance, no es Excel).
- Rama activa: main (= origin/main en aca139e).

### B. Evaluación JSON vs base de datos (Opción A aplicada, Opción B pendiente)
- Web lee JSONs de data/processed en cada request (~6.5MB, ~100ms parseo por carga).
- Opción A implementada y verificada: pipeline/json_io.py (atomic_json_write temp+os.replace+fsync) en los 19 puntos de escritura; web_dashboard/analytics/json_cache.py (load_json_cached por mtime+size + deepcopy); caché LocMem en settings.py; nav_companies cacheado por firma de directorios (antes re-parseaba 11 fundamental_scores.json por cada página); company_detail sin 500 (404 controlado ante JSON corrupto).
- Smoke test: 11 páginas HTTP 200; segunda carga 3-7x más rápida (/ de 1868ms a 254ms).
- Opción B (híbrido JSON canónico + SQLite serving layer) diseñada como siguiente paso, no aplicada aún.

### C. Auditoría de la cadena SEC a Django (hallazgos)
- GOOGL audit FAIL persistente: shares diluidos históricos no normalizados por split 20:1 (FY2015/FY2020); la auditoría detecta pero no corrige.
- 214 except:pass silenciosos en pipeline (sec_xbrl_ltm.py concentra 42).
- financial_scores.json == fundamental_scores.json (duplicado exacto x10, ~3.6MB).
- JSONs de artefactos mutados por la suite (tests escribían en data/processed/; ahora ruteados a tmp).
- data/cache/market_data_cache.json cambiando ~2x/día con la suite (red); se revierte en cada corrida.

### D. Bloque 1: salud de la suite de tests (completado)
- 21 fallos preexistentes de main triageados con causa raíz (AAPL/DECK/META extracción 2026-10/11 + SEC 429):
  - test_sec_freshness test_04/05: omitidos salvo RUN_SEC_NETWORK_TESTS=1 (red SEC).
  - test_16: contrato .md/.docx eliminado por diseno (27d3dcf); reescrito a dashboard web.
  - Goldens de scoring (AAPL FY2026 F=9/G=7, DECK G=5/rating PROMEDIO, DECK cash_drag>0.35) y web (fal 478.834M, DECK total 5.577.0M/HOKA 2.680.8M/EBIT LTM 1,315.9M, META extracción 10-Q + AI capex, NVDA taxonomía FY2026 Data Center > Compute/Networking, AAPL CAGR 5Y 5.5%, ROIC 45.0%, DEUDA Financiera AAPL 80.111,0M) actualizados y verificados contra artefactos auditados.
  - Tests ya no reescriben artefactos del repo (auditoría y scoring a tmp); artefactos revertidos tras cada corrida.
- Suite: 364/364 OK (skipped=2).

### E. Bug real encontrado y corregido en la raíz (Regla 4)
- resolve_canonical_balance_sheet (pipeline/canonical_resolvers.py) mezclaba el FY2026/canonical con el 10-Q intermedio de as-reported cuando LTM==FY2026 (post-10-K), rompiendo la Partida Doble en AAPL LTM por -16.709B.
- Fix: si el canonical LTM es duplicado del FY más reciente (varios totales canónicos coincidentes), los fallbacks as-reported de LTM resuelven contra ese FY. Verificado: identidad CA+NCA=TA, TL+EQ=TLE=TA al céntimo en AAPL, NVDA, DECK, MELI, META, GOOGL, O, PGR (bancos/aseguradoras no clasificables: N/A).
- Dashboard AAPL verificado HTTP 200 con las cifras corregidas.
- Nota: tabla As-Reported AAPL sigue mostrando el 10-Q de junio 2026 (por diseño: crudo vs SSOT resuelto). Decisión pendiente: etiqueta de la columna LTM.

### Pendientes para la próxima sesión (en orden sugerido)
1. EQ_OFFER en financial_scoring_engine.py: tolerancia 0.001 acciones crudas (250 shares tumban la señal de cero dilución); debe ser epsilon relativo (p. ej. 0.1% de shares previas).
2. GOOGL split-adjustment de shares históricas en auditoría BPA (L1, requiere Regla 1).
3. Decidir duplicado financial_scores.json vs fundamental_scores.json.
4. Logging persistente de la suite/pipeline (print() no sobrevive al reinicio).
5. data/cache/ en .gitignore + git rm --cached market_data_cache.json (opcional).
6. Opción B: capa SQLite de lectura para el dashboard (sincronización pipeline→BD tras cada análisis).
7. Question pendiente: etiqueta 'LTM' en columna as-reported (10-Q intermedio vs FY2026).

---

## 8. SesiÃ³n 2026-11-10 (Registro de la intervenciÃ³n)

### Estado verificado: Suite COMPLETA 365/365 OK (skipped=2 red SEC). Cero regresiones.

### Correcciones aplicadas en esta sesiÃ³n
1. EQ_OFFER (pipeline/financial_scoring_engine.py): la tolerancia absoluta <=0.001 acciones
   crudas daba FAIL ante ruido de redondeo (250 acciones sobre 14.66B). Cambiada a relativa
   <=0.01% del capital previo (misma semÃ¡ntica que F_dLEVER). Nuevo test test_19 de regresiÃ³n.
2. GOOGL EPS BPA (2 partes):
   - sec_canonical_builder.py: eps_*_adjusted ya no divide un EPS XBRL ya restatementado
     (doble aplicaciÃ³n del factor 20:1 -> 0.15 basura). Ahora deriva de NI/shares restatementadas.
   - audit_engine.py: la ruta ajustada compara eps_reported vs NI/shares_adj (independiente,
     no tautolÃ³gica); tolerancia relativa 2% con piso 0.20 en las 3 comparaciones del test.
   - Resultado: FY2020 PASS; 5 empresas-control al 100%; GOOGL 98.6% con FY2015 FAIL.
   - FY2015 de GOOGL: dato XBRL huÃ©rfano â€” 92.86 inexistante en todos los filings de Alphabet
     (FY2015 10-K reporta 22.84 consolidado/24.34 clase C; no estÃ¡ en us-gaap_EarningsPerShareDiluted).
     Pendiente arreglo taxonÃ³mico multi-clase (emisoras con axis StatementClassOfStockAxis).
3. financial_scores.json eliminado (duplicado exacto x10, -3.6MB): escritura del pipeline
   suprimida; referencias de tests apuntan a fundamental_scores.json; ficheros retirados del repo.
4. data/cache/ en .gitignore; market_data_cache.json ya no se versiona (arresca el diff diario).
5. Suite: 365 tests OK (antes 364 OK/21 fail preexistentes; -2 redes SEC skip por defecto).

### Hallazgo mayor pendiente para la prÃ³xima sesiÃ³n
- El extractor de EPS no maneja emisoras multi-clase (axis StatementClassOfStockAxis en XBRL,
  p. ej. GOOGL clases A/B vs C): de ahÃ­ naciÃ³ el dato 92.86. Afecta a futuras multi-clase.
- Antes de tocar: decidir si se reextrae GOOGL completo (pipeline, ~15-30 min red) o se
  implementa el arreglo taxonÃ³mico raÃ­z + spec de per-miembro/total en los EPS facts.

### Nota sobre artefactos de mercado
- data/cache/market_data_cache.json refrescado por la suite con precios en vivo; no versionado.
- data/processed/UBER/ NUEVO (sin tracking): aparece como extracciÃ³n de hoy 10:20; origen no
  confirmado (Â¿re-extracciÃ³n vÃ­a dashboard?). Se deja fuera del commit y pendiente de tu decisiÃ³n
  (commit vs actualizar manualmente vs eliminar).

---

## 9. Sesión 2026-11-10 — Auditoría por Capas: Capa 0 completada (STOP & PROPOSE -> Capa 1)

### Estado verificado tras Capa 0
- `python -m unittest discover -s tests -q`: **371 tests en 253.340s — OK (`skipped=2` pruebas de red opt-in en `test_sec_freshness.py`)**.
- `python web_dashboard/manage.py test analytics`: **6 tests en 17.278s — 5 OK, 1 fallo preexistente** (`ValuationAndSensitivityTests.test_meli_hybrid_view`, etiqueta `'Margen FCF Auditado:'` eliminada en `34d4e6e`, diferido a Capa 5).
- `python tests/health_check.py`: **14 / 15 PASS** (1 fallo preexistente: `GOOGL` 98.6% `70/71` por EPS `FY2015`, diferido a Capa 1). `AAPL`, `DECK`, `JPM`, `MELI`, `META`, `NU`, `NVDA`, `O`, `PGR`, `UBER` al **100.0%**.
- Dashboard Django (`GET /`, `/company/AAPL/`, `/company/DECK/`, `/company/UBER/` desde CWD `web_dashboard/`): **HTTP 200** sin recrear `web_dashboard/data/`.

### Cambios implementados en Capa 0
1. **SSOT de rutas y configuración (`pipeline/config_loader.py`):** Centralizados `PROJECT_ROOT`, `CONFIG_DIR`, `DATA_DIR`, `DATA_PROCESSED_DIR`, `DATA_CACHE_DIR`, `DRIVE_INPUT_DIR`, `load_sec_config()`, `get_sec_headers()`, `resolve_output_dir()` y `resolve_market_cache_path()`, eliminando definiciones duplicadas y el import roto `from ..sec_config` en `sec_freshness.py`. Eliminado el anclaje relativo al CWD que generaba `web_dashboard/data/` al ejecutar `manage.py runserver`.
2. **Orquestación unificada CLI + Web:** `pipeline/fundamental_pipeline.py` (`run_pipeline(..., progress_callback=...)`) pasó a ser la fuente única invocada por CLI y por `web_dashboard/analytics/pipeline_runner.py` (con `import urllib.parse` restaurado, snapshots thread-safe en `launch_pipeline_job` y tolerancia ante JSON corrupto).
3. **Retiro definitivo de flujo `.docx` / Excel / llamadas de resultados:** Eliminados `pipeline/earnings_call_extractor.py` y `pipeline/doc_parser.py`; limpiadas sus referencias en `fundamental_pipeline.py`, `pipeline_runner.py`, `filing_context.py`, `index.html`, `.agents/skills/*`.
4. **Limpieza residual y re-extracción de `UBER`:** Eliminados `web_dashboard/data/`, carpetas/copias repetidas en `drive_input/`, artefactos obsoletos (`earnings_call_data.json`, `qualitative_dossier.json`, `audit_certificate.json`, `audit_report.md`, bloqueo `~$financial_statements.xlsx` en Drive) y carpetas mock en Drive (`MOCK_REIT`, `MOCK_INS`, fijando `test_archetype_classifier.py` a `tmp`). Re-extraído `UBER` desde cero con el pipeline unificado (`PASS 100.0%`, 58/58).
5. **Pruebas nuevas (`tests/test_config_and_pipeline_runner.py`):** 6 pruebas de invariancia de CWD, delegación del runner web y ausencia de módulos/carpetas obsoletas.

### Próxima intervención pendiente de aprobación (Capa 1 — STOP & PROPOSE)
- `entity_classifier.py:normalize_archetype`, corrección de `FutureWarning` pandas y excepciones silenciosas en `sec_modules/`, modularización de monolitos de extracción y arreglo taxonómico multi-clase EPS (`StatementClassOfStockAxis`, `GOOGL FY2015`). *(Completada en la Sección 10).*

---

## 10. Sesión 2026-11-10 — Auditoría por Capas: Capa 1 completada (STOP & PROPOSE -> Capa 2)

### Estado verificado tras Capa 1
- `python -m unittest discover -s tests -q`: **376 tests en 247.252s — OK (`skipped=2` pruebas opt-in de red en `test_sec_freshness.py`)**. Cero `FutureWarning` de pandas.
- `python tests/health_check.py`: **15 / 15 PASS | Fallos: 0 | Advertencias: 0**. Las 11 emisoras extraídas (`AAPL`, `DECK`, `GOOGL`, `JPM`, `MELI`, `META`, `NU`, `NVDA`, `O`, `PGR`, `UBER`) alcanzan **100.0%** de fidelidad contable.
- Re-extracción real de `GOOGL` (`python pipeline/fundamental_pipeline.py --ticker GOOGL`): **PASS 100.0%** (`64` aprobados, `0` fallos, `2` omitidos).
- Dashboard Django (`GET /` y `/company/{TICKER}/` para las 11 empresas, total 12 rutas): todas **HTTP 200**.
- `python web_dashboard/manage.py test analytics`: **6 tests en 12.735s — 5 OK, 1 fallo preexistente** (`ValuationAndSensitivityTests.test_meli_hybrid_view`, `'Margen FCF Auditado:'` diferido a Capa 5).

### Cambios implementados en Capa 1
1. **`pipeline/entity_classifier.py`:** Corregida fuga de `default` ajeno en `normalize_archetype()` sobre alias corporativos, añadido logging estructurado, estrechado `except` en `parse_sic_code()` y descompuesto `detect_company_archetype()` en `_has_concept_match`, `_extract_concept_fingerprint` y `_resolve_declared_archetype`.
2. **Eliminación de suma errónea multi-clase XBRL y blindaje dimensional (`pipeline/sec_modules/sec_xbrl_ltm.py`, `pipeline/sec_modules/sec_statement_reconciler.py`):** Implementados `sanitize_multiclass_eps_df()` y `_select_primary_class_eps()` para corregir promedios/sumas sobre `us-gaap:StatementClassOfStockAxis` priorizando clases A/B sobre clase C sin distorsionar EPS consolidados; protegidos `dataframe_to_concept_dict()` y `merge_annual_statement_df()` frente a sobrescrituras de filas dimensionales; eliminado `df.loc[len(df)]` / `pd.concat` con columnas vacías mediante `_append_rows_safely()` e inserción directa (cero `FutureWarning`).
3. **Higiene AST y modularización de Capa 1:** Eliminados `bare except:`, los `39` `except ...: pass` silenciosos y las importaciones muertas en los 10 archivos de ingestión (`entity_classifier.py`, `financial_taxonomy.py`, `canonical_resolvers.py`, `sec_extractor.py`, `sec_modules/{__init__,sec_freshness,sec_xbrl_ltm,sec_statement_reconciler,sec_canonical_builder,sec_segment_extractor}.py`). Modularizados `sec_canonical_builder.py` (de monolito 1242L a helpers cohesivos + guard de `lt_debt` no inicializado en `comb_debt`), `canonical_resolvers.py` (`_CAPITAL_FLOW_KEYS`, `_BS_CONCEPT_KEYS` y helpers SSOT de balance, P&L y flujo de caja), `sec_segment_extractor.py` (constantes a nivel de módulo, `_upsert_segment_entry` compartido y eliminación de 4 sets muertos) y `sec_extractor.py` (`622` líneas, bajo el contrato `< 650` y con `build_sec_freshness_metadata` en `sec_freshness.py`).
4. **Pruebas unitarias nuevas (`tests/test_multiclass_eps_and_xbrl_hygiene.py`):** 5 pruebas con `-W error::FutureWarning` validando EPS multi-clase (`StatementClassOfStockAxis`), aislamiento dimensional, cero `FutureWarning` en pandas y precedencia de `normalize_archetype()`.

### Próxima intervención pendiente de aprobación (Capa 2 — STOP & PROPOSE)
- `audit_engine.py`: bug de reporte residual `diff_adj` en `audit_eps_consistency()` (p. ej. `DECK FY2016/FY2017` con `status=PASS` pero `discrepancy=3.49 / 0.26`).
- Módulos huérfanos sin llamadores: `pipeline/cross_verifier.py` (`364L`) y `pipeline/run_scoring.py` (`17L`), además de duplicidad `cross_verifier.py` vs `data_verifier.py`.
- SSOT, `Regla 6` e higiene en `kpi_extractor.py`, `governance_insider_analyzer.py`, `data_verifier.py`, `market_data_provider.py`, `drive_manager.py`, `sec_rate_limiter.py` y `filing_context.py` (elimina copias locales de arquetipos/años fijos/marcas, `total_tax_withholding_shares` muerto, restos de `"transcripts"` y `except: pass`). *(Completada en la Sección 11).*

---

## 11. Sesión 2026-11-10 — Auditoría por Capas: Capa 2 completada (STOP & PROPOSE -> Capa 3)

### Estado verificado tras Capa 2
- **Higiene AST (11 archivos de Capa 2 e infraestructura):** `0` `bare except:`, `0` `except ...: pass` silenciosos y `0` funciones `> 180` líneas (`audit_engine.py`, `config_loader.py`, `data_verifier.py`, `drive_manager.py`, `fundamental_pipeline.py`, `governance_insider_analyzer.py`, `json_io.py`, `kpi_extractor.py`, `market_data_provider.py`, `sec_rate_limiter.py`, `sec_modules/filing_context.py`).
- **Suite unitaria dirigida Capa 2 (`8` módulos):** **69 tests en 4.364s — OK**.
- **`python -m unittest discover -s tests -q`:** **382 tests en 311.795s — OK (`skipped=2`)** (`exit code 0`).
- **`python tests/health_check.py`:** **15 / 15 PASS | Fallos: 0 | Advertencias: 0**. Las 11 emisoras (`AAPL`, `DECK`, `GOOGL`, `JPM`, `MELI`, `META`, `NU`, `NVDA`, `O`, `PGR`, `UBER`) alcanzan **100.0%**; en `data/processed/DECK/audit_report.json` tanto `FY2016` como `FY2017` reportan `"status": "PASS"` y `"discrepancy": 0.0`.
- **Dashboard Django (`GET /` + 11 rutas `/company/{TICKER}/`):** **12 / 12 HTTP 200**.
- **`python web_dashboard/manage.py test analytics`:** **6 tests en 14.805s — 5 OK, 1 fallo preexistente** (`ValuationAndSensitivityTests.test_meli_hybrid_view`, `'Margen FCF Auditado:'` diferido a Capa 5).

### Cambios implementados en Capa 2
1. **`pipeline/audit_engine.py` (`506L`):** Corregido bug residual de `diff_adj` en `audit_eps_consistency()` cuando `net_income_total` concilia el BPA; extraídos `_find_concept_value()` y `_select_net_cash_change()`; eliminados `except: pass` mediante `logger.debug`.
2. **Eliminación de huérfanos y modularización de `pipeline/data_verifier.py` (`862L`):** Eliminados `pipeline/cross_verifier.py` y `pipeline/run_scoring.py` (cero llamadores); descompuesto `data_verifier.py` en `_sync_reports_to_drive()`, `_detect_standard_split_factor()`, `_extract_sec_facts_bundle()`, `_reconcile_fiscal_year()`, `_detect_target_sic()` y `_audit_single_peer_entry()`, removiendo `facts_ebit` muerto, ruta fija `"G:/Mi unidad/..."` y los 5 `except: pass`.
3. **`pipeline/kpi_extractor.py` (`777L`) y `pipeline/drive_manager.py` (`199L`):** Conectado `normalize_archetype` SSOT desde `entity_classifier`; reemplazados años hardcodeados en `_score_pdf_recency()` (6 pts/año + trimestre `1-4` sin techo fijo), defaults ficticios bancarios (`113.0`, `1.0`, `9.1`, `57.0`), caso especial `"ugg"` y `0.0` en `build_comparisons_block()` por `None` / `"DATO_NO_DISPONIBLE"` (`Regla 6`); suprimida creación automática de carpetas `"transcripts"` en `drive_manager.py`.
4. **`pipeline/governance_insider_analyzer.py` (`691L`), `pipeline/market_data_provider.py` (`351L`), `sec_rate_limiter.py` (`213L`), `filing_context.py` (`354L`), `json_io.py` (`42L`) y `fundamental_pipeline.py` (`190L`):** Eliminado `total_tax_withholding_shares` muerto, reutilizado `filing_context.get_filing_obj()` en Form 4/144, descompuesto `scan_form4_filings()` y `get_market_data()`, extraído `_parse_retry_after_header()`, limpiada referencia residual a `"Earnings Calls"` y eliminados todos los `except: pass`.
5. **Pruebas actualizadas y nuevas:** Extendidos `tests/test_audit_engine.py`, `tests/test_kpi_extractor.py`, `tests/test_drive_manager.py` y `tests/test_config_and_pipeline_runner.py` (`+6` pruebas unitarias netas: `376 -> 382`).

### Próxima intervención pendiente de aprobación (Capa 3 — STOP & PROPOSE)
- *(Completada en la Sección 12).*

---

## 12. Sesión 2026-11-10 — Auditoría por Capas: Capa 3 completada (STOP & PROPOSE -> Capa 4)

### Estado verificado tras Capa 3
- `python -m unittest discover -s tests -q`: **392 tests en 343.521s — OK (`skipped=2`)** (incluye los 10 nuevos tests en `tests/test_capa3_scoring_and_valuation_hygiene.py`).
- Suite focalizada Capa 3 (`test_capa3_scoring_and_valuation_hygiene.py`, `scoring`, `roc_greenblatt`, `forensic`, `solvency`, `valuation`, `challenger_m2*`, `challenger_m3*`): **119 tests en 120.425s — OK**.
- Paridad matemática A/B contra `git show 01a0ce3` sobre las 11 emisoras: coincidencia exacta en 10 (`AAPL`, `DECK`, `GOOGL`, `JPM`, `META`, `NU`, `NVDA`, `O`, `PGR`, `UBER`) y equivalencia numérica en `1e-12` ULP para `MELI.total_intangibles_usd_m`.
- `python tests/health_check.py`: **15 / 15 PASS | Fallos: 0 | Advertencias: 0**.
- Dashboard Django (`GET /` y 11 rutas `/company/{TICKER}/`): **12 / 12 HTTP 200**.
- `python web_dashboard/manage.py test analytics`: **6 tests en 18.386s — 5 OK, 1 fallo preexistente** (`ValuationAndSensitivityTests.test_meli_hybrid_view`, `'Margen FCF Auditado:'`, incluido en el STOP & PROPOSE de Capa 4).
- Auditoría AST sobre los 11 archivos de Capa 3: **0** `except:` desnudos, **0** `except: pass` silenciosos y **0** funciones `> 180L`.

### Cambios implementados en Capa 3
1. **Modularización y fachada retrocompatible de Scoring (`pipeline/scoring_modules/` + `pipeline/financial_scoring_engine.py` `328L`):**
   - Creados 6 submódulos cohesivos: `__init__.py` (`50L`), `scoring_utils.py` (`693L`), `piotroski_mohanram.py` (`629L`), `profitability_capital.py` (`1109L`), `forensic_accounting.py` (`504L`) y `solvency_credit.py` (`550L`).
   - Unificada la normalización de arquetipos vía `normalize_archetype` importada desde `pipeline/entity_classifier.py` (SSOT), `CONFIG_DIR` SSOT en `load_peer_benchmarks`, tabla `_SYNTHETIC_RATING_TABLE` en solvencia, preservación de `0.0` contable en `_first_present`, y eliminación de duplicación FY/LTM en `IntangibleROICCalculator` y `GreenblattROCCalculator`.
2. **Modularización y fachada retrocompatible de Valoración (`pipeline/valuation_modules/` + `pipeline/valuation_engine.py` `742L`):**
   - Creados `__init__.py` (`46L`), `dcf_models.py` (`602L`) y `market_history.py` (`513L`).
   - `get_report_archetype` y `get_solvency_archetype` delegados al SSOT `entity_classifier` (`detect_company_archetype` / `normalize_archetype`); `get_valuation_parameters` descompuesto en `_load_valuation_inputs`, `_resolve_capital_structure_and_wacc`, `_resolve_net_debt_m`, `_build_financial_pillars`, `_build_financial_valuation`, `_compute_corporate_margins_and_dcf` y `_build_corporate_valuation` (todas las funciones `< 180L`).
3. **Eliminación de fallbacks ficticios (Regla 4 / Regla 6) y manejo explícito de excepciones:**
   - Erradicados los `12` bloques `except Exception: pass` silenciosos (`3` en scoring, `9` en valoración, reemplazados por errores explícitos o `logger.debug`).
   - Eliminados literales/series sintéticas prohibidos: fallback Apple `"price": 230.0` / `"market_cap_usd_m": 3000000.0` en `WACCCalculator` (ahora `None` + `"UNAVAILABLE_MODULE_MISSING"`), `g_implied_fiscal` con `wacc=0.1090`/`fcf_margin=0.244` (ahora alineado a `g_implied_our`), precios sintéticos `current_price * [0.65, ...]` en `calculate_z_score_valuation`, cierres ficticios `current_price * 0.85` en `calculate_historical_multiples_analysis` (`price: None` sin histórico real), `rotce_val = 0.15`, `price = 100.0`, `base_rev_m = 100.0`, `buyback_rate = 1.5` (ahora `0.0`), y filas `"10.0%"` en `_generate_sensitivity_grid` (ahora `"N/D"` cuando faltan insumos corporativos).
   - Corregido `build_audit_traceability` para recibir e interpolar `g_implied_oe_pct` real en la fórmula LaTeX `reverse_dcf`.
4. **Tests de regresión Capa 3 (`tests/test_capa3_scoring_and_valuation_hygiene.py` `253L`, 10 tests):** Verifican higiene AST (`0` funciones `> 180L`, `0` `except: pass`), ausencia de literales prohibidos, re-exports de fachada y cumplimiento de Regla 4/Regla 6.

### Próxima intervención pendiente de aprobación (Capa 4 — STOP & PROPOSE)
- *(Completada en la Sección 13).*

---

## 13. Sesión 2026-11-10 — Auditoría por Capas: Capa 4 completada (STOP & PROPOSE -> Plan P0 AAPL/NU + Capa 5)

### Estado verificado tras Capa 4
- `python -m unittest tests.test_e2e_universal_orchestrator tests.test_capa4_web_analytics_hygiene tests.test_web_forensics tests.test_web_valuation tests.test_profitability_capital_allocation_charts tests.test_segment_chart_periods tests.test_config_and_pipeline_runner tests.test_as_reported_integrity tests.test_opex_ebit_integrity tests.test_web_statements -q`: **133 tests en 84.071s — OK**.
- `python web_dashboard/manage.py test analytics`: **6 tests en 13.898s — OK (`6 / 6 PASS`, resuelto el fallo preexistente `test_meli_hybrid_view`)**.
- `python -m unittest tests.test_capa4_web_analytics_hygiene tests.test_period_integrity -v`: **23 tests en 0.162s — OK** (`7` de higiene Capa 4 + `16` de Plan P0).
- Dashboard Django (`GET /` y 11 rutas `/company/{TICKER}/`): **12 / 12 HTTP 200**.
- Auditoría AST sobre los `25` archivos `.py` de `web_dashboard/analytics/`: **0** `except:` desnudos, **0** `except: pass` silenciosos y **0** funciones `> 180L`.
- *(Nota: durante la ejecución de Capa 4 se incorporó en paralelo **Plan P0** — `pipeline/period_integrity.py`, `tests/test_period_integrity.py` y ediciones en `audit_engine.py`, `data_verifier.py` y `sec_freshness.py` — cuyos nuevos controles de período exponen 2 fallos reales en datasets históricos al correr `python tests/health_check.py`: **13 / 15 PASS | Fallos: 2** en `AAPL` y `NU`, y `test_m1_empirical_stress.py:520` `test_control_company_aapl_integrity` antes del arreglo de datos. Se dejan dichos archivos concurrentes sin alterar bajo **Regla 1**.)*

### Cambios implementados en Capa 4
1. **SSOT compartida (`web_dashboard/analytics/views/view_utils.py` `173L`) y `context_processors.py` (`62L`):**
   - Centralizados `DATA_DIR` (`DATA_PROCESSED_DIR`), `DRIVE_INPUT_DIR`, `resolve_market_cache_path` y `resolve_company_archetype` delegando en `pipeline.config_loader` y `pipeline.entity_classifier` (SSOT).
   - Separación explícita de unidades (`usd_to_m` para USD crudos SEC/canónicos, `already_m` para montos ya en `$M` del JSON de scoring y `pct_from_key_ratio` para ratios ya porcentuales), corrigiendo dos bugs silenciosos reales: la doble división de `ic_adj` en `JPM` (`$4,719,984.5M` frente a `$4.7M`) y la multiplicación `×100` en `cost_of_risk_series` cuando `Cost of Risk <= 1.0%` (`0.60%`/`0.57%` en lugar de `60%`/`57%`).
2. **Modularización de vistas monolíticas y eliminación de `except: pass`:**
   - [`views.py`](web_dashboard/analytics/views/views.py) (`325L`): `index` descompuesto con `_build_index_card` y `_resolve_latest_score`; erradicados los `6` `except Exception: pass` + `continue` silencioso.
   - [`views_scoring.py`](web_dashboard/analytics/views/views_scoring.py) (`91L` fachada) + `views_scoring_quality.py` (`385L`) + `views_scoring_forensics.py` (`469L`).
   - [`views_charts.py`](web_dashboard/analytics/views/views_charts.py) (`122L` fachada) + `views_charts_series.py` (`280L`) + `views_charts_sector.py` (`120L`) + `views_charts_segments.py` (`441L`).
   - [`views_statements.py`](web_dashboard/analytics/views/views_statements.py) (`112L` fachada) + `views_statements_schemas.py` (`294L`) + `views_statements_cells.py` (`265L`) + `views_statements_memo.py` (`438L`). (Verificado que `views_statements_memo.py` / `L1274` original ya formateaba `affo_per_share` con `affo_sh_val`).
   - [`views_valuation.py`](web_dashboard/analytics/views/views_valuation.py) (`142L`): erradicados los `2` `except Exception: pass`.
3. **Erradicación de defaults ficticios (`Regla 6`) y guardas seguras de plantilla:**
   - Eliminados defaults inventados: `"AAA"`, `0.095`, `"WIDE MOAT"` en `views.py`; `f_score=7`/`g_score=6` (incluyendo el bug falsy `0 or 7`), `"SALUD EXCEPCIONAL"`, `"EXCELENTE"`, `"41.8x"`, `3.23`, `"+0.40%"`, `"rating_is_safe": True` y dictámenes contradictorios en `O`/`JPM`/`PGR` (`altman_bucket = 0` cuando `altman_val` es `None`/`N/D`); fallback MELI (`7.0`, `18.7`, `105.0`) en `platform_kpis`; `fcf_m_series` y márgenes faltantes como `null` en Chart.js en lugar de `0.0`; y `"buyback_rate_pct": 1.5` en `views_valuation.py` (ahora `0.0`).
   - Guardas puntuales en `web_dashboard/templates/company_detail.html` (`f_score`/`g_score` `default_if_none:"N/D"`, `wSlider`/`baseWaccVal` leyendo `vp.wacc_pct` y tooltips Chart.js `ctx.parsed.y !== null`).
4. **Tests (`web_dashboard/analytics/tests.py` `118L`, `tests/test_capa4_web_analytics_hygiene.py` `162L` y `tests/test_e2e_universal_orchestrator.py` `L379`):**
   - Alineado `test_meli_hybrid_view` con la Super Pestaña de Valoración vigente (`'True FCF LTM (ex-SBC)'` / `'Dual Valuation Engine'`, ya que `'Margen FCF Auditado:'` había sido retirado en `5f78e23`).
   - Actualizado `test_r5_04_segment_mix_denominator_excludes_subtotals` para inspeccionar `views_charts*.py` tras la modularización de segmentos.

### Próxima intervención pendiente de aprobación (STOP & PROPOSE — Hallazgos Plan P0 AAPL/NU + Capa 5)
1. **Resolución de hallazgos concurrentes de Plan P0 en `AAPL` y `NU` (prioritario para recuperar `15 / 15 PASS` en `health_check.py` y `test_m1_empirical_stress`):**
   - `AAPL` (`LTM_IGUAL_FY`): `31` filas de `as_reported_statements` en `data/processed/AAPL/financial_statements.json` tienen `LTM != FY2026` pese a `latest_periodic_form == "10-K"`. Diagnosticar causa en extracción `AAPL` o re-extraer `AAPL` + `data_verifier`.
   - `NU` (`PERIODO_NO_POSTERIOR` y `PERIODO_NO_FUTURO`): `sec_metadata` registra `ltm_period = "Q4 2026"`, `ltm_period_end = "2026-12-31"` con `latest_periodic_date = "2026-10-23"` y `extraction_timestamp = "2026-11-08"`. Corregir origen del mapeo de período en `6-K` / `NU` o re-extraer `NU` + `data_verifier`.
   - Decidir si confirmar/commitear el conjunto Plan P0 (`pipeline/period_integrity.py`, `audit_engine.py`, `data_verifier.py`, `sec_freshness.py`, `tests/test_period_integrity.py`).
2. **Capa 5 (`web_dashboard/templates/`): `company_detail.html` (`6038L`), `index.html` (`432L`) y `base.html` (`121L`):**
   - Descomponer el monolito `company_detail.html` (`6038L`) en parciales HTML cohesivos por pestaña (`templates/analytics/partials/`) y mover los `~2200L` de JavaScript embebido a módulos estáticos/locales limpios.
   - Eliminar duplicación JS de `syncWithSec` (`company_detail.html:5885-5967`) vs `startPipeline`/`pollPipeline` (`index.html:338-429`) y los bucles repetidos de DCF 3-Stage vs 2-Stage en `recalcDCF` / `solveCell` (`company_detail.html:4383-4435`, `4661`).
   - Limpiar defaults y XSS/texto legado en plantillas: `peCurrent` (`|default:20.0` en `company_detail.html:3866`), `ltm_period|default:"LTM"` (`company_detail.html:30`, alinear a `"N/D"`), `vp.rotce_pct|default:hist_growth_pct` (`L73`, `L3148`), escapes HTML en `index.html:271-277` y `company_detail.html:5843-5874`, y texto `"entregables"` legado en `index.html:403`.

---

## 14. Sesión 2026-11-11 — Reorganización Modular de `pipeline/` y `tests/`, Limpieza de Obsoletos y 12 Guías `README.md` de Impacto

### Cambios ejecutados
1. **Eliminación de documentación histórica obsoleta y caché de raíz:**
   - Eliminados vía `git rm -f`: `ORIGINAL_REQUEST.md`, `PROJECT.md`, `TEST_INFRA.md`, `TEST_READY.md`, `Informe_Auditoria_Universalidad_2026-10-09.md`, `docs/AUDIT_FORENSE_EXTRACTORES_SEC.md` y `docs/INFORME_AUDITORIA_CUANTITATIVA_SCORING.md`.
   - Eliminado directorio `__pycache__/` en raíz (y caché obsoleto en `pipeline/__pycache__/`).
2. **Reorganización modular de `pipeline/` en 5 fachadas + 5 subpaquetes temáticos (`32` scripts):**
   - Raíz de `pipeline/`: exclusivamente `__init__.py`, `README.md` y las 5 fachadas de entrada (`fundamental_pipeline.py`, `sec_extractor.py`, `financial_scoring_engine.py`, `valuation_engine.py`, `audit_engine.py`).
   - `pipeline/sec_modules/` (`12` módulos): reubicados `entity_classifier.py`, `financial_taxonomy.py`, `financial_bilingual_map.py`, `canonical_resolvers.py`, `kpi_extractor.py` y `governance_insider_analyzer.py` junto a los 6 submódulos SEC previos.
   - `pipeline/audit_modules/` (`2` módulos, nuevo subpaquete): `data_verifier.py` y `period_integrity.py`.
   - `pipeline/scoring_modules/` (`5` módulos): conservados sin cambios estructurales con bootstrap de `sys.path` en `__init__.py`.
   - `pipeline/valuation_modules/` (`3` módulos): reubicado `market_data_provider.py` junto a `dcf_models.py` y `market_history.py`.
   - `pipeline/infra/` (`5` módulos, nuevo subpaquete): reubicados `config_loader.py` (`PROJECT_ROOT` actualizado a `.parent.parent.parent`), `json_io.py`, `sec_rate_limiter.py`, `drive_manager.py` y `sync_to_drive.py` (`source_root` a `.parent.parent.parent`, eliminados `"schemas"`, `"TREE.txt"` y `"sync_to_drive.py"` de sus listas de sincronización).
   - **Retrocompatibilidad 100% de imports y CLI:** `pipeline/__init__.py` extiende `__path__` y `sys.path` con los 5 subpaquetes; las 5 fachadas, los 5 `__init__.py` de subpaquetes y los scripts CLI ejecutables directamente (`data_verifier.py`, `kpi_extractor.py`, `governance_insider_analyzer.py`, `market_data_provider.py`, `sync_to_drive.py`) registran `PROJECT_ROOT`/`pipeline` e importan `pipeline` cuando corresponde.
3. **Reorganización de `tests/` en 5 subpaquetes temáticos (`38` archivos `test_*.py` + `health_check.py`):**
   - Creados `tests/__init__.py` y subpaquetes `sec_extraction/` (`8`), `accounting_audit/` (`8`), `scoring_valuation/` (`7`), `web_dashboard/` (`8`) y `e2e_stress/` (`7`) con `__init__.py` en cada uno.
   - Actualizada la resolución de raíz a `parents[2]` / 3 niveles de `dirname` en los 38 tests y actualizado `tests/health_check.py` para contar recursivamente todos los scripts `.py` bajo `pipeline/` (`32` scripts).
   - Desambiguación de paquetes en `tests/__init__.py` y `tests/web_dashboard/__init__.py` extendiendo `web_dashboard.__path__` con `web_dashboard/web_dashboard` y `tests/web_dashboard` para evitar colisiones de nombres durante `python -m unittest discover -s tests`.
4. **Creación y actualización de los `12` archivos `README.md` en español con matrices de impacto:**
   - Raíz (`README.md`), `pipeline/README.md`, `pipeline/{sec_modules,audit_modules,scoring_modules,valuation_modules,infra}/README.md`, `web_dashboard/README.md`, `web_dashboard/analytics/views/README.md`, `tests/README.md`, `config/README.md` y `docs/README.md` (todos verificados con `0` enlaces rotos).

### Verificación final post-reorganización
- `python web_dashboard/manage.py test analytics`: **6/6 PASS** (`17.536s`).
- `python tests/accounting_audit/test_verify_aapl_nca.py`: **PASS** (`0.0M` diferencia en NCA LTM).
- `health_check.test_skills_integrity()`: **PASS** (`2/2` skills válidas, `32` scripts consolidados en `pipeline/`).
- `python -m unittest discover -s tests -q`: **416 tests en 264.697s — 413 PASS, 2 SKIP** (red SEC opt-in), **1 FAIL preexistente ajeno a la reorganización** (`tests/web_dashboard/test_web_statements.py:460` `test_quality_and_forensic_fixes_5_points` espera `$59,160.0M` en `AAPL`, pero el commit previo `4b453fa` actualizó `short_term_investments` LTM a `$20,417.0M`, resultando `$56,722.0M` de tesorería y `$23,389.0M` de deuda neta; pendiente de revisión bajo Regla 1).
- CLI e imports aislados (`data_verifier.py --help`, `kpi_extractor.py --help`, `governance_insider_analyzer.py --help`, `market_data_provider`, `sync_to_drive`, `fundamental_pipeline.py --help`, `sec_extractor.py --help`, `audit_engine.py --help`): **OK (`rc=0`)**.
