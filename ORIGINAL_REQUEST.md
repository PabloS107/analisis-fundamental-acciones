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
