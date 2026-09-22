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
python .agents/skills/fundamental-data-extractor/scripts/fundamental_pipeline.py --ticker <TICKER>
```

### Scripts individuales disponibles:
1. **Extracción exclusiva de SEC EDGAR:**
   ```powershell
   python .agents/skills/fundamental-data-extractor/scripts/sec_extractor.py --ticker <TICKER>
   ```
   Genera:
   - `financial_statements.json`: JSON estructurado con balance, resultados, cash flow y ratios canónicos.
   - `financial_statements.xlsx`: Libro Excel formateado con pestañas separadas y colores corporativos.
   - `sec_narrative.json`: Textos oficiales de Item 1 (Negocio), Item 1A (Riesgos) e Item 7 (MD&A).

2. **Procesamiento de documentos en Drive:**
   ```powershell
   python .agents/skills/fundamental-data-extractor/scripts/doc_parser.py --ticker <TICKER>
   ```
   Genera:
   - `qualitative_dossier.json`: Guidance numérico, objetivos y Q&A de analistas.

3. **Auditoría Contable de Corroboración Matemática:**
   ```powershell
   python .agents/skills/fundamental-data-extractor/scripts/audit_engine.py --ticker <TICKER>
   ```
   Genera:
   - `audit_certificate.json`: Certificado con el desglose de pruebas contables.
   - `audit_report.md`: Reporte de auditoría con fórmulas matemáticas de partida doble.

4. **Gobernanza Corporativa, Insiders (Form 4/144) y Alertas Tempranas (8-K):**
   ```powershell
   python .agents/skills/fundamental-data-extractor/scripts/governance_insider_analyzer.py --ticker <TICKER>
   ```
   Genera:
   - `governance_insider_data.json`: Scorecard de gobernanza, detección de hechos materiales (8-K), compras y ventas de insiders (Form 4) diferenciando planes 10b5-1, y avisos de venta de acciones restringidas (Form 144) con banderas de anomalía.

5. **Motor Cuantitativo de Scoring Fundamental (Piotroski & Mohanram):**
   ```powershell
   python .agents/skills/fundamental-data-extractor/scripts/financial_scoring_engine.py <TICKER>
   ```
   Genera:
   - `fundamental_scores.json`: Puntuación detallada criterio por criterio de Piotroski F-Score (0-9 pts) y Mohanram G-Score (0-8 pts) con benchmarks sectoriales (SIC/GICS), evolución histórica multianual (2016-2025 + LTM) y clasificación estratégica en matriz 2x2 (*Compounder de Élite*, *Cash Cow*, *Crecimiento Vulnerable*, *Trampa de Valor*).
   - Incorpora 5 mejoras institucionales: Acciones Básicas para $EQ\_OFFER$, Deuda Financiera Total para $F\_\Delta LEVER$, Apalancamiento Operativo Comercial ($\% \Delta \text{Ventas} > \% \Delta \text{SG\&A}$) para $G8$, Coeficiente de Variación / Cláusula de Hipercrecimiento para $G4/G5$, y Tasa de Inversión Total para modelos *Asset-Light* en $G7$.

6. **Generador de Informe Ejecutivo Institucional (Word y Markdown):**
   ```powershell
   python .agents/skills/fundamental-data-extractor/scripts/generate_earnings_report.py
   ```
   Genera:
   - `Analisis_Resultados_Q3_FY26_<TICKER>.docx`: Informe formateado en Word con tablas, tipografía ejecutiva, cuadro de mando de gobernanza y scorecard cuantitativo de Piotroski y Mohanram.
   - `Analisis_Resultados_Q3_FY26_<TICKER>.md`: Informe equivalente en Markdown.

7. **Suite de Pruebas Unitarias y Diagnóstico del Sistema:**
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
1. `financial_statements.xlsx`: Modelo Excel de 7 pestañas para revisión visual con cifras en Millones de USD ($M), ratios en %, 10 años + LTM, y la Hoja 7 interactiva "Scores Fundamentales".
2. `financial_statements.json`: Datos fuente auditados listos para scripts de valuación y modelos matemáticos.
3. `fundamental_scores.json`: Resultados cuantitativos de Piotroski F-Score, Mohanram G-Score y Matriz Combinada.
4. `qualitative_dossier.json`: Resumen de riesgos, negocio, guidance de presentaciones y Q&A de llamadas.
5. `sec_narrative.json`: Textos oficiales íntegros de 10-K (Item 1, 1A y 7).
6. `governance_insider_data.json`: Scorecard de gobernanza, análisis de 8-K, Form 4 y 144 con explicaciones educativas y diagnósticos.
7. `audit_certificate.json`: Certificado con puntaje de fidelidad contable y pruebas superadas.
8. `audit_report.md`: Reporte legible de auditoría matemática de partida doble.
9. `executive_dossier.md`: Informe resumen ejecutivo consolidado listo para ser presentado al usuario.
10. `Analisis_Resultados_Q3_FY26_<TICKER>.docx`: Informe Word con diseño institucional de Wall Street.
11. `Analisis_Resultados_Q3_FY26_<TICKER>.md`: Informe Markdown de análisis fundamental, gobernanza y scoring.

