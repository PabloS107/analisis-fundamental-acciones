---
name: fundamental-data-extractor
description: >-
  Extracts official audited financial statements (10-K, 10-Q, 20-F, 6-K) from SEC EDGAR via XBRL, extracts operational Non-GAAP KPIs from 8-K/6-K Ex-99.1 and investor presentations, and generates clean structured JSON datasets for the Django web dashboard. Use this skill whenever the user requests extracting financial statements, filing data, balance sheets, cash flows, or operational KPIs for any public company.
---

# Fundamental Data Extractor Skill

Esta skill es el motor de entrada de datos para el asistente de análisis fundamental. Su objetivo es obtener, limpiar y estandarizar la información cuantitativa auditada (normativa US-GAAP e IFRS de la SEC) y los KPIs operativos de comunicados 8-K/6-K para el Dashboard Web Django (`web_dashboard/`).

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
- **Google Drive (Entrada opcional de presentaciones):**
  - Ruta base: `G:\Mi unidad\analisis fundamental\<TICKER>\`
  - El usuario puede depositar allí presentaciones en PDF (subcarpeta `presentations/` o directamente en la carpeta del ticker).
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
   - `segments_data.json`: Segmentos operativos y geográficos ASC 280 / ASC 606.

2. **Extracción de KPIs Operativos y Métricas Non-GAAP (8-K / 6-K Ex-99.1):**
   ```powershell
   python pipeline/kpi_extractor.py --ticker <TICKER>
   ```
   Genera:
   - `presentation_reconciliation.json`: KPIs sectoriales normalizados consumidos por el Dashboard Web.

3. **Auditoría Contable de Corroboración Matemática:**
   ```powershell
   python pipeline/audit_engine.py --ticker <TICKER>
   ```
   Genera:
   - `audit_report.json`: Dictamen completo por período de identidades contables y sanidad.

4. **Gobernanza Corporativa, Insiders (Form 4/144) y Alertas Tempranas (8-K):**
   ```powershell
   python pipeline/governance_insider_analyzer.py --ticker <TICKER>
   ```
   Genera:
   - `governance_insider_data.json`: Scorecard de gobernanza, detección de hechos materiales (8-K), compras y ventas de insiders (Form 4) diferenciando planes 10b5-1, y avisos de venta de acciones restringidas (Form 144) con banderas de anomalía.

5. **Motor Cuantitativo de Scoring Fundamental (Piotroski & Mohanram):**
   ```powershell
   python pipeline/financial_scoring_engine.py <TICKER>
   ```
   Genera:
   - `fundamental_scores.json`: Puntuación detallada criterio por criterio de Piotroski F-Score (0-9 pts) y Mohanram G-Score (0-8 pts) con benchmarks sectoriales (SIC/GICS), evolución histórica multianual (2016-2025 + LTM) y clasificación estratégica en matriz 2x2 (*Compounder de Élite*, *Cash Cow*, *Crecimiento Vulnerable*, *Trampa de Valor*).

6. **Pipeline Unificado y Servidor Web Django:**
   ```powershell
   python pipeline/fundamental_pipeline.py --ticker <TICKER>
   python web_dashboard/manage.py runserver
   ```
   Ejecuta el procesamiento integral de datos y disponibiliza la visualización interactiva en el Dashboard Web Django.

7. **Suite de Pruebas Unitarias y Diagnóstico del Sistema:**
   ```powershell
   python -m unittest discover -s tests -v
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
3. `segments_data.json`: Segmentos operativos y geográficos.
4. `presentation_reconciliation.json`: KPIs operativos Non-GAAP.
5. `audit_report.json`: Log de auditoría contable y faltantes.
6. `sec_narrative.json`: Textos oficiales íntegros de 10-K (Item 1, 1A y 7).
7. `governance_insider_data.json`: Scorecard de gobernanza, análisis de 8-K, Form 4 y 144.

