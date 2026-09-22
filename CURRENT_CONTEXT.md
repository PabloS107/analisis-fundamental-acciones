# ESTADO Y CONTEXTO DEL PROYECTO: MOTOR UNIVERSAL DE ANÁLISIS FUNDAMENTAL

**Fecha de guardado:** 22 de Septiembre de 2026 (10:48 ART)  
**Estado del sistema:** ✅ 100% Operativo | 68/68 Tests Unitarios Aprobados | Sincronización Google Drive Activa  
**Empresas validadas de extremo a extremo:** `AAPL` (Apple Inc.) y `DECK` (Deckers Outdoor Corp.)

---

## 1. Arquitectura del Sistema Consolidada

El proyecto cuenta con un **Orquestador Universal Único** parametrizado para procesar cualquier empresa pública a partir de sus filings SEC EDGAR, datos de mercado y transcripciones:

1. **Extracción y Procesamiento:**
   - [`sec_extractor.py`](.agents/skills/fundamental-data-extractor/scripts/sec_extractor.py): Extracción XBRL desde SEC EDGAR (taxonomías US-GAAP e IFRS-full) con manejo de rate-limiting (HTTP 429). Prioriza `Revenues` sobre ASC 606 y mantiene flujos discretos LTM para BPA.
   - [`market_data_provider.py`](.agents/skills/fundamental-data-extractor/scripts/market_data_provider.py): Arbitraje de datos de mercado en tiempo real y consenso de analistas (Yahoo Finance & CNBC) con fallback dinámico por ticker.
   - [`financial_scoring_engine.py`](.agents/skills/fundamental-data-extractor/scripts/financial_scoring_engine.py):
     - Piotroski F-Score (9 señales)
     - Mohanram G-Score (8 señales)
     - Novy-Marx Gross Profitability (GP/A)
     - Intangible-Adjusted ROIC (Damodaran roll-forward identity)
     - Costo de Capital Ponderado (WACC) y Economic Spread (EVA)
     - Auditoría Forense: Ratio Devengos Sloan, Matriz de Divergencias de Alerta Temprana, Montier C-Score (0-6 banderas)
     - Altman Z''-Score (no manufacturero / mercados emergentes)
     - Damodaran Synthetic Credit Rating

2. **Generación de Entregables:**
   - [`excel_formatter.py`](.agents/skills/fundamental-data-extractor/scripts/excel_formatter.py): Genera modelo financiero institucional de 11 pestañas en formato Excel (`.xlsx`). Hoja 8 con ranking ascendente de WACC (`=RANK(..., 1)`).
   - [`generate_earnings_report.py`](.agents/skills/fundamental-data-extractor/scripts/generate_earnings_report.py): Orquestador Universal que construye el informe institucional de 14 secciones maestras en Word (`.docx`) y Markdown (`.md`).
   - Sub-módulos modulares conectados:
     - `novy_marx_report_builder.py` (Sección 10)
     - `roic_wacc_report_builder.py` (Sección 11)
     - `forensic_report_builder.py` (Sección 12)
     - `solvency_report_builder.py` (Sección 13)
     - `valuation_report_builder.py` (Sección 14): Sensibilidad y Cuadro de Mando 100% dinámicos sin textos fijos de Apple ni Deckers.
   - Scripts redundantes eliminados: `deck_report_builder.py` y cualquier lógica bifurcada fija eliminada.

3. **Estructura Desacoplada de Datos por Ticker:**
   En `data/processed/<TICKER>/` y replicado en `drive_input/<TICKER>/processed/` y `G:\Mi unidad\analisis fundamental\<TICKER>\processed`:
   - `company_profile.json`: Perfil corporativo, canales de negocio, segmentos, geografía, balance, gobernanza y benchmarking de pares (GP/A en porcentajes explícitos).
   - `earnings_call_data.json`: Análisis cualitativo de la conferencia de resultados (Bloque A actual y Bloque B longitudinal 5 trimestres).
   - `fundamental_scores.json` / `financial_scores.json`: Resultados cuantitativos de todos los modelos de scoring, forensic y valoración.
   - `Analisis_Resultados_<PERIODO>_<TICKER>.docx` y `.md`: Informes ejecutivos finales generados.
   - `Modelo_Financiero_<TICKER>.xlsx`: Modelo institucional en Excel.

---

## 2. Últimas Modificaciones Realizadas y Validadas (Sesión Actual)

### A. Secciones 9.1 (Piotroski F-Score) y 9.2 (Mohanram G-Score)
- **Problema corregido:** En `generate_earnings_report.py`, se buscaba la clave inexistente `criteria` en vez de `signals`, provocando un fallback a 2 filas genéricas sin narrativa en DECK.
- **Solución:**
  - Extracción directa y dinámica de las **9 señales de Piotroski** y **8 de Mohanram** para el período LTM y año previo.
  - Restauración completa de la narrativa pedagógica de Stanford (Joseph Piotroski) y Columbia (Partha Mohanram).
  - Inclusión dinámica de los **4 puntos estratégicos para el inversor**:
    1. Respaldo de caja operativa vs. beneficio neto contable.
    2. Reducción y control del apalancamiento financiero.
    3. Protección al accionista minoritario (dilución vs. recompras netas).
    4. Eficiencia operativa (margen bruto y rotación de activos).
  - Tablas completas y desgloses desplegados en Word y Markdown.

### B. Sección 9.3 (Benchmarking Competitivo Sectorial)
- **Problema corregido:** Existían dos formatos incompatibles (uno de escala en AAPL y otro de retornos/scores en DECK).
- **Solución:**
  - Creación de la **Tabla Híbrida Maestra Unificada** de 9 columnas:
    `Ticker | Compañía | Ventas ($M) | Margen Bruto | Margen EBIT | ROIC Intang. | GP/A | F-Score | G-Score`
  - Ancho de 6.8 pulgadas en Word con alineaciones numéricas institucionales y Markdown idéntico.
  - Actualización de `company_profile.json` para DECK y AAPL con la estructura de 9 columnas.

### C. Sección 12.4 (Cuadro de Mando Consolidado de Fidelidad Contable)
- **Problema corregido:** Textos diagnósticos fijados con frases de Apple (e.g., "superciclo", "cero distorsión" pese a +10.7 pp, y "probabilidad < 5%" pese a Montier 3/6).
- **Solución:**
  - Implementación de `_evaluate_forensic_diagnostics` en `forensic_report_builder.py`.
  - Diagnósticos 100% dinámicos en base a los datos reales:
    - **DIO:** Umbral adaptativo (`< 45d` para tecnología, `< 130d` para calzado/retail). Para Deckers (126.4d), diagnostica *«Rotación equilibrada (126.4d); ciclo operativo dentro del estándar sectorial»*.
    - **Variación de Activos Blandos:** Reconoce el incremento (`+10.7 pp`) contextualizando que el ratio total (`49.8%`) permanece bajo la zona de peligro del 75%.
    - **Montier C-Score:** Diagnostica *«Riesgo moderado (3/6); banderas operativas no constitutivas de fraude»*.
    - **Spread AR vs. Ventas:** Contextualiza que el DSO ultra-bajo (`25.0d`) descarta ventas infladas en canal (*channel stuffing*).

### D. Paridad 100% Reverse DCF y Matriz de Sensibilidad (Word vs. Web Dashboard)
- **Problemas corregidos:**
  1. En `views.py`, los ingresos base caían en un fallback de \$1,000M al buscar en una clave inexistente de `peer_ranking`, inflando el margen FCF al 111.8%.
  2. En `company_detail.html` (JS), `targetMktCap = targetPrice * shares` omitía por completo la Deuda Neta ($-\$1,602.6\text{ M}$ de caja neta para DECK), resolviendo $g_{\text{implied}}$ en -1.41% en vez de -3.7%.
  3. En la web faltaba la **Matriz Bidimensional de Sensibilidad (5x6)** presente en la Sección 14.4 del Word.
  4. La interfaz web no explicaba por qué el Crecimiento Implícito no varía al mover el slider de ventas proyectadas (metodología *Expectations Investing* de Mauboussin).
- **Solución implementada:**
  - `views.py` ahora consume directamente `get_valuation_parameters` y `_generate_sensitivity_grid` de `valuation_report_builder.py`.
  - `valuation_report_builder.py` ajustó la precisión de `shares_b` a 4 decimales (`round(shares_b, 4)`), asegurando coherencia perfecta en empresas de media capitalización como DECK.
  - `company_detail.html` incorporó `netDebt` en el cálculo de `fairPrice` y `targetEV = (targetPrice * shares) + netDebt`.
  - Se renderizó la **Matriz de Sensibilidad 5x6** con resaltado del escenario central (WACC base y $g_n = 2.5\%$).
### E. Tarjetas de Inicio, ROIC vs. WACC y Cotización en Tiempo Real
- **Problemas corregidos:**
  1. En `index.html`, las tarjetas mostraban `F-Score: - / 9`, `WACC: 0.00%` y `Spread EVA: 0.0pp` debido a lectura de claves incorrectas en `views.py`.
  2. No se visualizaba el ROIC Ajustado ni se comparaba explícitamente contra el WACC.
  3. No se mostraba la cotización de mercado en tiempo real en la tarjeta de inicio ni en el simulador DCF.
- **Solución implementada:**
  - `views.py` `index`: Corregidas las claves para extraer `total_score`, `wacc`, `roic_adjusted` y `economic_spread_adjusted`.
  - Integrado `MarketDataExtractor` para alimentar las tarjetas con la cotización en tiempo real (`$80.41 USD` para DECK y `$341.43 USD` para AAPL) con badge pulsante.
  - Rediseñada la tarjeta en `index.html` con un bloque destacado que compara formalmente:
    $$\text{ROIC Ajustado } (53.6\%) \text{ vs. WACC } (10.31\%) \implies \mathbf{Spread\ EVA = +43.3\text{ pp}}$$
  - `valuation_report_builder.py` adaptado para recibir `live_price`, permitiendo que el Reverse DCF resuelva contra la cotización en vivo sin distorsionar el Precio Justo Teórico ($P_{\text{fair}}$).
  - En `company_detail.html`, añadido badge `🟢 En Vivo` y botón `🔄 Refrescar` (`?refresh=1`).
  - Pruebas automatizadas en `web_dashboard/analytics/tests.py`: **3/3 tests aprobados**; **68/68 tests globales aprobados**.

---

## 3. Próximos Pasos / Hoja de Ruta para la Siguiente Sesión

1. **Expansión para Instituciones Financieras y Fintechs:**
   - El informe maestro de investigación arquitectónica ya está completado y validado en el sistema para:
     - Bancos comerciales tradicionales (`JPM`, `BAC`, etc.).
     - Bancos digitales y emisores de crédito (`NU` - Nu Holdings).
     - Modelos híbridos de e-commerce + fintech (`MELI` - MercadoLibre con Mercado Pago / Mercado Crédito).
   - Adaptación requerida en el motor cuantitativo:
     - Ratios que no aplican a bancos: Working Capital, Current Ratio, Gross Margin, Net PPE, FCFF, WACC tradicional, Altman Z industrial, Sloan Accruals estándar.
     - Ratios especializados bancarios a incorporar: Margen de Interés Neto (NIM), Cost of Risk, NPL Ratio / Mora (Etapa 1, 2 y 3 bajo IFRS 9), Ratio de Cobertura de Provisiones, CET1 / Ratio de Basilea, ROTCE / ROE, Ratio de Eficiencia.
     - Modelos de valoración bancaria: Modelo de Rentas Residuales / Retorno Excedente (*Excess Return Model*), Modelo de Descuento de Dividendos (DDM), P/TBV (Precio sobre Valor Tangible en Libros), y Suma de las Partes (*SOTP*) para híbridos como MELI.

2. **Diseño de Visualización y Dashboard (HTML / Django / Frontend):**
   - Una vez consolidadas las métricas bancarias, avanzar en el diseño visual de las tarjetas y dashboards interactivos para presentar los datos extraídos sin entrecruzamientos de empresas.

---

## 4. Comandos Clave de Ejecución y Verificación

- **Ejecutar Suite Completa de Tests (68 tests):**
  ```powershell
  python -m unittest discover tests
  ```
- **Generar Informe para Deckers (DECK):**
  ```powershell
  python .agents/skills/fundamental-data-extractor/scripts/generate_earnings_report.py DECK
  ```
- **Generar Informe para Apple (AAPL):**
  ```powershell
  python .agents/skills/fundamental-data-extractor/scripts/generate_earnings_report.py AAPL
  ```
- **Generar Modelo Excel de 11 Hojas:**
  ```powershell
  python .agents/skills/fundamental-data-extractor/scripts/excel_formatter.py
  ```
