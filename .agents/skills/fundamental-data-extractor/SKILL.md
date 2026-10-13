---
name: fundamental-data-extractor
description: >-
  Extracts official audited financial statements (10-K, 10-Q) from SEC EDGAR via XBRL, parses investor presentations and earnings call transcripts from Google Drive, and generates clean structured JSON and Excel datasets for fundamental stock analysis. Use this skill whenever the user requests extracting financial statements, filing data, balance sheets, cash flows, or qualitative reports for any public company.
---

# Fundamental Data Extractor Skill

Esta skill es el motor de entrada de datos para el asistente de análisis fundamental. Su objetivo es obtener, limpiar y estandarizar tanto la información cuantitativa auditada (normativa US-GAAP de la SEC) como la información cualitativa estratégica (presentaciones, guidance y llamadas de resultados) antes de proceder a la valuación o análisis de ratios.

---

## 1. Cuándo activar esta Skill

Activa esta skill cuando el usuario pida:
- Extraer o consultar estados financieros (Balance, Cuenta de Resultados, Flujo de Caja) de una empresa cotizada (ej. AAPL, MSFT, MELI, GOOGL, NVDA, etc.).
- Procesar formularios oficiales 10-K, 10-Q u 8-K presentados ante la SEC.
- Leer y estructurar una presentación de inversores (slides en PDF) o transcripción de conferencia de resultados depositada en Google Drive.
- Iniciar el análisis fundamental o construir el modelo financiero base de una acción.

---

## 2. Fuentes de Datos y Rutas

- **SEC EDGAR API (`data.sec.gov`):**
  - Conexión oficial y directa con identidad configurada en [sec_config.json](../../../config/sec_config.json).
  - Extracción de conceptos XBRL oficiales (100% libre de errores o estimaciones de terceros).
- **Google Drive (Entrada de usuario):**
  - Ruta base: `G:\Mi unidad\analisis fundamental\<TICKER>\`
  - El usuario puede depositar allí presentaciones en PDF (subcarpeta `presentations/` o directamente en la carpeta del ticker) y transcripciones de llamadas (`transcripts/`).
- **Salidas Estandarizadas:**
  - Carpeta local del proyecto: `data/processed/<TICKER>/`
  - Carpeta sincronizada en Drive: `G:\Mi unidad\analisis fundamental\<TICKER>\processed\`

---

## 3. Procedimiento de Ejecución

Para extraer los datos completos de una empresa, ejecuta el orquestador maestro:

```powershell
python pipeline/fundamental_pipeline.py --ticker <TICKER>
```

### Scripts individuales disponibles:
1. **Extracción exclusiva de SEC EDGAR:**
   ```powershell
   python pipeline/sec_extractor.py --ticker <TICKER>
   ```
   Genera:
   - `financial_statements.json`: JSON estructurado con balance, resultados, cash flow y ratios canónicos.
   - `sec_narrative.json`: Textos oficiales de Item 1 (Negocio), Item 1A (Riesgos) e Item 7 (MD&A).

2. **Extracción y Estructuración Automática de Earnings Calls (Sin Drive):**
   ```powershell
   python pipeline/earnings_call_extractor.py --ticker <TICKER>
   ```
   Genera:
   - `earnings_call_data.json`: Dataset canónico con Bloque A (Guidance oficial SEC 8-K, hitos estratégicos, riesgos y Q&A banco por banco con diagnóstico fundamental) y Bloque B (Auditoría longitudinal 5 trimestres, Say-Do ratio y credibilidad directiva).

3. **Procesamiento de documentos locales / Drive (Opcional):**
   ```powershell
   python pipeline/doc_parser.py --ticker <TICKER>
   ```
   Genera:
   - `qualitative_dossier.json`: Guidance numérico, presentaciones en PDF y notas suplementarias.

4. **Auditoría Contable de Corroboración Matemática:**
   ```powershell
   python pipeline/audit_engine.py --ticker <TICKER>
   ```
   Genera:
   - `audit_certificate.json`: Certificado con el desglose de pruebas contables.
   - `audit_report.md`: Reporte de auditoría con fórmulas matemáticas de partida doble.

5. **Gobernanza Corporativa, Insiders (Form 4/144) y Alertas Tempranas (8-K):**
   ```powershell
   python pipeline/governance_insider_analyzer.py --ticker <TICKER>
   ```
   Genera:
   - `governance_insider_data.json`: Scorecard de gobernanza, detección de hechos materiales (8-K), compras y ventas de insiders (Form 4) diferenciando planes 10b5-1, y avisos de venta de acciones restringidas (Form 144) con banderas de anomalía.

6. **Motor Cuantitativo de Scoring Fundamental (Piotroski & Mohanram):**
   ```powershell
   python pipeline/financial_scoring_engine.py <TICKER>
   ```
   Genera:
   - `fundamental_scores.json`: Puntuación detallada criterio por criterio de Piotroski F-Score (0-9 pts) y Mohanram G-Score (0-8 pts) con benchmarks sectoriales (SIC/GICS), evolución histórica multianual (2016-2025 + LTM) y clasificación estratégica en matriz 2x2 (*Compounder de Élite*, *Cash Cow*, *Crecimiento Vulnerable*, *Trampa de Valor*).
   - Incorpora 5 mejoras institucionales: Acciones Básicas para $EQ\_OFFER$, Deuda Financiera Total para $F\_\Delta LEVER$, Apalancamiento Operativo Comercial ($\% \Delta \text{Ventas} > \% \Delta \text{SG\&A}$) para $G8$, Coeficiente de Variación / Cláusula de Hipercrecimiento para $G4/G5$, y Tasa de Inversión Total para modelos *Asset-Light* en $G7$.

7. **Generador de Informe Ejecutivo Institucional (Word y Markdown):**
   ```powershell
   python pipeline/generate_earnings_report.py <TICKER>
   ```
   Genera:
   - `Analisis_Resultados_Q3_FY26_<TICKER>.docx`: Informe formateado en Word con tablas, tipografía ejecutiva, cuadro de mando de gobernanza y scorecard cuantitativo de Piotroski y Mohanram.
   - `Analisis_Resultados_Q3_FY26_<TICKER>.md`: Informe equivalente en Markdown.

8. **Suite de Pruebas Unitarias y Diagnóstico del Sistema:**
   ```powershell
   python -m unittest tests/test_scoring_engine.py -v
   python tests/health_check.py
   ```
   Comprueba SEC API, Google Drive, Skills de Antigravity, audita todas las empresas procesadas y valida al 100% los cálculos matemáticos de scoring.

---

## 4. Archivos Producidos y Especificación de Esquemas

Para consultar los nombres exactos de los campos y variables que consumirán los siguientes módulos (DCF, Múltiplos, DuPont), consulta la referencia:
- [schemas.md](./references/schemas.md)

Archivos generados en `data/processed/<TICKER>/` y `G:\Mi unidad\analisis fundamental\<TICKER>\processed\`:
1. `financial_statements.json`: Datos fuente auditados listos para scripts de valuación y modelos matemáticos.
2. `fundamental_scores.json`: Resultados cuantitativos de Piotroski F-Score, Mohanram G-Score y Matriz Combinada.
3. `earnings_call_data.json`: Conferencia de resultados y guidance oficial estructurado (Bloque A y Bloque B).
5. `qualitative_dossier.json`: Resumen de riesgos, negocio, guidance de presentaciones y Q&A de llamadas.
6. `sec_narrative.json`: Textos oficiales íntegros de 10-K (Item 1, 1A y 7).
7. `governance_insider_data.json`: Scorecard de gobernanza, análisis de 8-K, Form 4 y 144 con explicaciones educativas y diagnósticos.
8. `audit_certificate.json`: Certificado con puntaje de fidelidad contable y pruebas superadas.
9. `audit_report.md`: Reporte legible de auditoría matemática de partida doble.
10. `executive_dossier.md`: Informe resumen ejecutivo consolidado listo para ser presentado al usuario.
11. `Analisis_Resultados_Q3_FY26_<TICKER>.docx`: Informe Word con diseño institucional de Wall Street.
12. `Analisis_Resultados_Q3_FY26_<TICKER>.md`: Informe Markdown de análisis fundamental, gobernanza y scoring.

