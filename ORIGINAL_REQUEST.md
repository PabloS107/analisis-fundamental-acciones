# Original User Request

## 2026-09-06T18:20:50Z

This is a single self-contained fix; keep it small and focused.

Corregir integralmente los tres desajustes contables y de sincronización detectados en el modelo financiero en Excel (`financial_statements.xlsx`), el motor cuantitativo de scoring (`financial_scoring_engine.py`) y la base de pares (`peer_benchmarks.json`): restaurar la visualización de datos en la hoja de Ratios Financieros, actualizar a LTM auditado todas las empresas comparables de la hoja de Pares, y conectar dinámicamente las medianas del Mohanram G-Score (Hoja 7) con las calculadas en la tabla del grupo de pares (Hoja 8).

Working directory: c:/Users/pablo/OneDrive/Documents/Analisis fundamental de acciones
Integrity mode: development

## Requirements

### R1. Restaurar Datos Numéricos en la Hoja 2 ("Ratios Financieros")
En `excel_formatter.py` (función `create_ratios_sheet`), corregir la extracción de métricas para leer de la clave `key_ratios` de `financial_statements.json` (evitando diccionarios vacíos). Verificar que los 9 ratios financieros institucionales (márgenes Bruto, Operativo, Neto, FCF Margin, Conversión FCF, ROE, ROA, Current Ratio y Debt to Equity) muestren sus valores numéricos correspondientes (%) y (x) a lo largo de los 11 períodos (LTM y FY2016-FY2025).

### R2. Actualización Homogénea a LTM de Todas las Empresas del Peer Group (Hoja 8)
En `config/peer_benchmarks.json` y la Hoja 8 ("Peer Group & Medianas"), sincronizar y verificar las cifras financieras de todos los competidores de hardware (DELL, HPQ, HPE, SMCI, WDC, STX, NTAP) en base a sus últimos 12 meses móviles (LTM) auditados ante la SEC, garantizando que ninguna empresa mezcle años fiscales pasados ni bases heterogéneas.

### R3. Sincronización Dinámica de Medianas: Hoja 7 (Scores) vs Hoja 8 (Peer Group)
Unificar la fuente de verdad de las medianas del sector:
1. `financial_scoring_engine.py` debe cargar y calcular dinámicamente las medianas sectoriales a partir de los pares de `config/peer_benchmarks.json` para el sector de la empresa (o recibir las medianas calculadas), de modo que la mediana contra la que se evalúa la empresa en la Hoja 7 (ej. ROA, CFROA, Intensidad de I+D y Reinversión Total) sea idéntica al 100% al valor que arroja la fila `MEDIANA DEL SECTOR` de la Hoja 8.
2. Actualizar las notas flotantes (tooltips de celda) de la Hoja 7 para reflejar con total transparencia la misma mediana oficial calculada en la Hoja 8.

## Acceptance Criteria

### Hoja 2 ("Ratios Financieros")
- [ ] La pestaña "Ratios Financieros" de `financial_statements.xlsx` muestra valores numéricos para todos los períodos históricos y LTM, sin celdas con `-` injustificadas.
- [ ] Los tooltips explicativos de ratios se mantienen intactos y funcionales.

### Hoja 8 ("Peer Group & Medianas")
- [ ] Todas las filas de competidores en la Hoja 8 reflejan datos de períodos LTM sincronizados.
- [ ] Las fórmulas dinámicas de `=MEDIAN(...)`, `=AVERAGE(...)`, `=PERCENTILE(...)` y `=RANK(...)` calculan sin errores `#¿NOMBRE?` ni `#NAME?`.

### Hoja 7 ("Scores Fundamentales") y Coherencia Global
- [ ] Las señales G1 (ROA), G2 (CFROA), G6 (I+D) y G7 (Reinversión) en `financial_scores.json` y en la Hoja 7 de Excel se comparan exactamente contra las medianas calculadas en la Hoja 8.
- [ ] No existe ninguna discrepancia entre el benchmark mostrado en la Hoja 7 y la mediana calculada en la Hoja 8.
- [ ] El conjunto de pruebas unitarias (`python -m unittest tests/test_scoring_engine.py`) y el diagnóstico de salud (`python tests/health_check.py`) se ejecutan y aprueban al 100%.
- [ ] El archivo `financial_statements.xlsx` regenerado se sincroniza en la carpeta de Google Drive: `G:\Mi unidad\analisis fundamental\AAPL\processed\`.


## 2026-10-03T14:12:03Z

# Teamwork Project Prompt — Final

> Status: Launched
> Goal: Multi-agent execution of the refactoring plan
> Requested team: Full team

Auditoría y refactorización integral del Orquestador Universal de Análisis Fundamental para resolver los 54 defectos detectados (16 críticos), garantizando la detección automática del arquetipo contable desde la extracción de datos (SEC EDGAR), su propagación en el motor de scoring central y la eliminación de fallbacks hardcodeados conforme a las Reglas de AGENTS.md.

Working directory: c:/Users/pablo/OneDrive/Documents/Analisis fundamental de acciones
Integrity mode: development

## Requirements

### R1. Detección Automática y Universal del Arquetipo en la Extracción (`pipeline/sec_extractor.py`)
- Durante la fase de extracción de estados contables (SEC EDGAR XBRL / 10-K / 10-Q), el sistema debe clasificar y persistir de forma obligatoria y canónica el `archetype` en `financial_statements.json`.
- La clasificación debe ser dinámica, derivada de:
  - Códigos SIC y taxonomía sectorial GICS: Bancos/Crédito (SIC 60xx, 61xx -> `FINANCIAL_BANKING`), Aseguradoras (SIC 63xx, 64xx -> `INSURANCE`), REITs (SIC 6798 -> `REAL_ESTATE_REIT`), Plataformas híbridas/ecosistemas (SIC 7389 / eCommerce con fintech -> `PLATFORM_ECOSYSTEM`), y Corporativas/Industriales -> `CORPORATE_STANDARD`.
  - Firma contable del balance y P&L (ej. existencia de depósitos de clientes, cartera de préstamos, float de inversiones, reservas de siniestros o transacciones de propiedades inmobiliarias).
- Cero hardcoding de tickers en la detección (`if ticker == "..."` prohibido por REGLA 4 de `AGENTS.md`).

### R2. Desacoplamiento por Arquetipos en el Motor Central de Scoring (`pipeline/financial_scoring_engine.py`)
- El motor de scoring debe leer `archetype` de `financial_statements.json` y ramificar sus módulos de cálculo.
- Si `archetype == "FINANCIAL_BANKING"` o `"INSURANCE"`, inhibir de raíz el cálculo de métricas corporativas absurdas (ej. ROC Greenblatt de 11.211% y Altman Z'' de quiebra).
- La extracción de deuda financiera debe recurrir siempre a `canonical_summary.total_debt` y soportar taxonomías IFRS (`ifrs-full_Borrowings`), REITs (`NotesPayable`) y GAAP bancario (`LongTermDebtAndCapitalLeaseObligationsIncludingCurrentMaturities`), erradicando la asignación de deuda = 0.0 en NU, O, PGR y JPM.
- Corregir las guardas de signo en gastos financieros (intereses negativos no deben traducirse en "libre de deuda").

### R3. Normalización Contable y Corrección de Taxonomías XBRL (`pipeline/sec_extractor.py` y `audit_engine.py`)
- Incorporar en la taxonomía de deuda a largo plazo de JPMorgan Chase el concepto `LongTermDebtAndCapitalLeaseObligationsIncludingCurrentMaturities` (~$435.206M).
- Normalizar signos en P&L para evitar costos o gastos negativos (caso COGS, I+D y SG&A en MELI), auditando identidades contables sin usar máscaras que oculten el signo (`abs(cogs)`).
- Desacoplar compras de inmuebles comerciales del CapEx de mantenimiento en REITs (caso O / Realty Income).

### R4. Erradicación Absoluta de Fallbacks Hardcodeados (Cumplimiento Estricto REGLA 4 de `AGENTS.md`)
- Eliminar de `solvency_report_builder.py`, `valuation_report_builder.py` y `roic_wacc_report_builder.py` todas las filas y cifras fijas de Nubank o Apple (`$30,400 M`, `26.40%`, `1000.0`, etc.).
- Toda cifra en los informes DOCX, MD y Excel debe ser derivada de forma dinámica de los datos del emisor analizado o reflejar `'N/D'` con justificación metodológica.
- Separar formalmente el informe de aseguradoras (`INSURANCE`) del informe bancario para que PGR no herede la plantilla de bancos.

### R5. Sincronización y Blindaje del Dashboard Web Django (`web_dashboard/`)
- Corregir el simulador interactivo JS en `company_detail.html` para que en bancos no recalcule con DCF corporativo ni sobrescriba la valoración con `$0,00`.
- Corregir las etiquetas y datos del índice (`ROTCE - Ke` vs `ROIC - WACC`).
- Generación de artefactos para `JPM`, `O` y `PGR` evitando errores 404 al navegar por sus vistas.
- Corrección del cálculo de mix de segmentos excluyendo subtotales y métricas agregadas del denominador.

## Acceptance Criteria

### Detección y Propagación de Arquetipos
- [ ] Todo emisor procesado cuenta con su campo `archetype` correctamente asignado en `financial_statements.json` y consumido por el motor de scoring.
- [ ] 0 ejecuciones de Altman Z'' o Greenblatt ROC corporativo sobre entidades bancarias o aseguradoras.

### Integridad Cuantitativa y Contable
- [ ] 0 emisiones de deuda en 0.0 para entidades con pasivo financiero (`NU`, `O`, `PGR`, `JPM`).
- [ ] Deuda total de JPMorgan Chase refleja la cifra auditada real (~$500.000M).
- [ ] COGS y gastos operativos de MercadoLibre normalizados con signo positivo e identidades respetadas.
- [ ] D/E y WACC consistentes en las 8 empresas del corpus (`AAPL`, `DECK`, `JPM`, `MELI`, `NU`, `NVDA`, `O`, `PGR`).

### Zero Regressions en Empresas de Control
- [ ] Cero regresiones en `AAPL` y `DECK` (manteniendo exactitud 100% en scoring corporativo y suites de tests).

### Verificación de Artefactos e Informes
- [ ] Ausencia total de cadenas hardcodeadas de Nubank o Apple en informes de terceros.
- [ ] Dashboard Django 100% navegable sin 404s en ninguna de las 8 compañías.
- [ ] Suite de pruebas ampliada con cobertura para entidades financieras, REITs y aseguradoras pasando al 100%.


## 2026-10-03T21:11:53Z

Los límites de cuota han sido restablecidos. Reanuda la orquestación del proyecto desde el estado actual documentado en `.agents/teamwork/orchestrator/progress.md`. 

Estado actual verificado:
- Fase 0 (Survey & Scope Mapping) completada.
- Pista A (E2E Testing Suite): 65 tests en tests/test_e2e_universal_orchestrator.py completados.
- Pista B / Hito 1 (Arquetipos y Taxonomías): Worker M1 completó las Features 1-4 en `sec_extractor.py` y `audit_engine.py`.
- Reanuda el Gate M1 (revisores, challengers, auditor forense), completa la verificación de Hito 1 y avanza secuencialmente a Milestone 2 (Scoring Engine Decoupling), Milestone 3 (Eradication of Fallbacks) y Milestone 4 (Web Dashboard).


## 2026-10-04T12:46:51Z

Los límites de cuota han sido restablecidos. Reanuda la orquestación del proyecto desde el estado actual documentado en `.agents/teamwork/orchestrator/progress.md`.

Estado actual verificado:
- Milestone 1 (Detección de Arquetipos y Taxonomías): 100% COMPLETADO Y APROBADO.
- Milestone 2 (Financial Scoring Engine Decoupling): Worker M2 ya implementó y verificó las Features 5-8 en `pipeline/financial_scoring_engine.py` y entregó `handoff.md`.
- Acción inmediata: Convoca el panel Gate M2 (2 Reviewers, 2 Challengers, Forensic Auditor) para certificar el Hito 2 y continúa secuencialmente con Milestone 3 (Eradication of Hardcoded Fallbacks) y Milestone 4 (Web Dashboard Hardening).
