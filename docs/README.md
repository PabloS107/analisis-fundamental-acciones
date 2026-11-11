# Documentación y Reglas del Proyecto (`docs/`)

Este directorio contiene las especificaciones técnicas fundacionales del motor cuantitativo y sirve como punto de entrada hacia la gobernanza, el contexto operativo y la documentación modular por carpeta.

---

## 1. Contenido de `docs/`

### [`Especificacion_Calculos_FScore_GScore.txt`](Especificacion_Calculos_FScore_GScore.txt)
Documento de especificación matemática e institucional (*Versión 2 - Post-Auditoría & Mejoras*) que define la implementación del sistema bidimensional de calidad:
- **5 Mejoras Institucionales sobre los modelos académicos originales:**
  - *Mejora A (`EQ_OFFER`)*: Uso estricto de acciones básicas promedio ponderado (`WeightedAverageNumberOfSharesOutstandingBasic`) para aislar emisión/recompra real sin distorsión del *Treasury Stock Method*.
  - *Mejora B (`F_dLEVER`)*: Inclusión de la deuda financiera total (largo plazo + porción corriente / corto plazo) para evitar arbitraje de plazos.
  - *Mejora C (`G8`)*: Apalancamiento operativo comercial ($\Delta\text{Ventas }\% > \Delta\text{SG\&A }\%$) en lugar de premiar SG&A/Activos elevado.
  - *Mejora D (`G4`, `G5`)*: Tratamiento del hipercrecimiento mediante Coeficiente de Variación ($\text{CV} = \sigma / \mu$) y Cláusula de Aceleración sobre el percentil 75 sectorial.
  - *Mejora E (`G7`)*: Intensidad total de reinversión $((\text{CapEx} + \text{R\&D}) / \text{Activos})$ adaptada a modelos *Asset-Light*.
- **Piotroski F-Score (0–9):** Bloque I Rentabilidad y Caja (`F_ROA`, `F_CFO`, `F_dROA`, `F_ACCRUAL`), Bloque II Estructura y Liquidez (`F_dLEVER`, `F_dLIQUID`, `EQ_OFFER`) y Bloque III Eficiencia Operativa (`F_dMARGIN`, `F_dTURN`).
- **Mohanram G-Score (0–8):** Bloque I Rentabilidad vs. Industria (`G1`, `G2`, `G3`), Bloque II Estabilidad (`G4`, `G5`) y Bloque III Reinversión y Apalancamiento Comercial (`G6`, `G7`, `G8`).
- **Matriz de Decisión y Benchmarking SIC:** Clasificación en 4 cuadrantes (*Compounder de Élite*, *Crecimiento Vulnerable*, *Cash Cow Madura*, *Trampa de Valor / Riesgo*) apoyada en [`config/industry_medians.json`](../config/industry_medians.json) y validación numérica de referencia con `AAPL`.

> **Nota de evolución arquitectónica:** Las menciones históricas a hojas Excel o reportes `.docx` en el plan inicial de la Sección 8 de dicho `.txt` han quedado reemplazadas por la arquitectura actual basada en JSONs canónicos (`data/processed/{TICKER}/`) y el Dashboard Web Django (`web_dashboard/`).

---

## 2. Documentación Rectora del Repositorio

- **[`AGENTS.md`](../AGENTS.md)** — Reglas fundamentales e irrestrictas del proyecto:
  - **Regla 1:** Parada obligatoria y propuesta forense (*STOP & PROPOSE*) ante fallos de cálculo, diseño o excepciones.
  - **Regla 2:** Verificación triangulada obligatoria (tests unitarios + regresión con empresas de control + inspección de JSON/Django).
  - **Regla 3:** Transparencia y pedagogía contable en nuevas métricas y arquetipos financieros.
  - **Regla 4:** Universalidad absoluta sin hardcoding de tickers (`if ticker == ...` prohibido) y correcciones en la raíz del motor.
  - **Regla 5:** Eliminación de código muerto y deuda técnica.
  - **Regla 6:** Cero datos inventados o valores por defecto ficticios (`N/D` explícito y trazabilidad en `audit_report.json`).
  - **Regla 7:** Sincronización obligatoria con GitHub (`git commit` & `git push`) tras validar cambios.
- **[`CURRENT_CONTEXT.md`](../CURRENT_CONTEXT.md)** — Bitácora viva y estado del sistema, universo activo de empresas de control e historial de intervenciones por capas.
- **[`README.md`](../README.md)** — Guía general del **Orquestador Universal de Análisis Fundamental Institucional** en la raíz del proyecto.

---

## 3. Guías de Arquitectura e Impacto por Carpeta

| Carpeta | Guía (`README.md`) | Contenido Documentado |
| :--- | :--- | :--- |
| Raíz del Repositorio | [`README.md`](../README.md) | Árbol completo, 5 arquetipos contables, ejecución CLI del pipeline, lanzamiento web y pruebas. |
| Pipeline Central | [`pipeline/README.md`](../pipeline/README.md) | Flujo secuencial de `fundamental_pipeline.py` (Pre-Flight y Pasos A–E) y fachadas principales. |
| Extracción SEC / XBRL | [`pipeline/sec_modules/README.md`](../pipeline/sec_modules/README.md) | Los 12 módulos de extracción, taxonomía US-GAAP/IFRS, arquetipos, segmentos, KPIs Non-GAAP y gobernanza. |
| Auditoría Contable | [`pipeline/audit_modules/README.md`](../pipeline/audit_modules/README.md) | Verificación cruzada (`data_verifier.py`) e invariantes temporales/de período (`period_integrity.py`). |
| Scoring Cuantitativo | [`pipeline/scoring_modules/README.md`](../pipeline/scoring_modules/README.md) | F-Score, G-Score, Novy-Marx, ROIC Intangible, Greenblatt ROC, WACC/Ke, Sloan, Montier, Altman Z'' y ratings. |
| Valoración y Mercado | [`pipeline/valuation_modules/README.md`](../pipeline/valuation_modules/README.md) | Reverse DCF 2/3 etapas, Excess Return 2 etapas, múltiplos históricos y proveedor de mercado en vivo. |
| Infraestructura | [`pipeline/infra/README.md`](../pipeline/infra/README.md) | SSOT de rutas (`config_loader.py`), escritura atómica (`json_io.py`), rate limiter SEC y Google Drive. |
| Plataforma Web Django | [`web_dashboard/README.md`](../web_dashboard/README.md) | Configuración Django, `LocMemCache`, `json_cache`, `pipeline_runner`, URLs y plantillas HTML. |
| Vistas Django | [`web_dashboard/analytics/views/README.md`](../web_dashboard/analytics/views/README.md) | Los 14 submódulos de vistas y su **Matriz de Impacto Visual y de Datos** por pestaña. |
| Suite de Pruebas | [`tests/README.md`](../tests/README.md) | Catálogo de los 38 tests en 5 subcarpetas, `health_check.py` y comandos rápidos por módulo. |
| Configuración Sectorial | [`config/README.md`](../config/README.md) | Esquema y carga de `sec_config.json`, `industry_medians.json` y `peer_benchmarks.json`. |
