# ESTADO Y CONTEXTO DEL PROYECTO: ORQUESTADOR UNIVERSAL DE ANÁLISIS FUNDAMENTAL

**Última actualización:** 9 de Noviembre de 2026 (noche, sesión de cierre)  
**Rama activa de Git:** `main` (sincronizada con `origin/main`)  
**Estado del sistema:** ✅ 100% Operativo | Suite de Pruebas: **364/364 OK** (solo 2 skips de red SEC, `RUN_SEC_NETWORK_TESTS=1`) | Health Check: 100.0% Cumplimiento Contable | Cero Regresiones  
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

```
Analisis fundamental de acciones/
├── CURRENT_CONTEXT.md              # Este archivo (SSOT del contexto y estado vivo del proyecto)
├── AGENTS.md                       # Reglas mandatorias irrestrictas del proyecto
├── QA_REPORT.md                    # Reporte generado por tests/health_check.py
├── pipeline/                       # Motores centrales de extracción, scoring y valoración
│   ├── sec_extractor.py            # Extracción universal de SEC EDGAR XBRL multi-arquetipo
│   ├── financial_taxonomy.py       # Mapeo canónico unificado de conceptos XBRL
│   ├── financial_scoring_engine.py # Motores Piotroski, Mohanram, Novy-Marx, ROIC, WACC/Ke
│   ├── audit_engine.py             # Auditoría de identidades contables y sanidad
│   ├── valuation_report_builder.py # Reverse DCF y Excess Return Model 2-Etapas
│   └── solvency_report_builder.py  # Diagnóstico de solvencia bancaria, aseguradora y corporativa
├── web_dashboard/                  # Aplicación Web Django
│   ├── analytics/views.py          # Lógica de presentación, reconciliación de estados y modelos
│   ├── templates/company_detail.html # Plantilla integral con pestañas interactivas y simulador JS
│   └── manage.py                   # Administrador de Django
├── tests/                          # Suite de tests automatizados
│   ├── test_web_statements.py      # Verificación de tablas y reconciliaciones web
│   ├── health_check.py             # Verificación multidimensional de fidelidad contable
│   └── test_*.py                   # Tests unitarios cuantitativos y de regresión
└── data/processed/{TICKER}/        # Datasets auditados y entregables generados
    ├── financial_statements.json   # Estados financieros y summary canónico
    ├── fundamental_scores.json     # Puntuaciones, retornos sobre capital y valoración
    ├── audit_report.json           # Log de auditoría contable y faltantes
    ├── *.docx                      # Informe institucional Word
    └── *.md                        # Informe institucional Markdown
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
