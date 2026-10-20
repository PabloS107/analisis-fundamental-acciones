---
trigger: glob
globs: "pipeline/*.py, web_dashboard/analytics/*.py, web_dashboard/templates/*.html, tests/*.py"
description: "Arquitectura Dual (Opción A) en Español e invariantes obligatorios para Estados Financieros en SEC Extractor y Django."
---

# Especificación e Invariantes: Estados Financieros (Opción A — Español Institucional)

1. **Arquitectura Dual Obligatoria en la Pestaña `📑 Estados Financieros`:**
   - **Modo 1 (Por defecto): `📐 Vista Estandarizada (10Y + LTM)`:** Alimentada al 100% por `canonical_summary`, `resolve_canonical_balance_sheet` y `resolve_canonical_capital_flows`, adaptada dinámicamente a los 5 arquetipos (`STANDARD_CORPORATE`, `PLATFORM_ECOSYSTEM`, `FINANCIAL_BANKING`, `INSURANCE`, `REAL_ESTATE_REIT`). Prohibido mostrar guiones `-` injustificados en líneas troncales o subtotales que no cuadren con la suma de sus componentes.
   - **Modo 2 (Toggle secundario): `🏛️ Filing Oficial SEC (As-Reported)`:** Muestra las líneas literales del último 10-K/20-F acotadas a `LTM` + los 3 ejercicios anuales auditados del filing (`statements_fys[:4]`), eliminando columnas históricas vacías.
2. **Idioma 100% Español en una Sola Línea:**
   - La columna de nombre de partida debe mostrar **únicamente el nombre en Español** en una sola línea limpia (sin concatenar el inglés entre paréntesis). El nombre original en inglés de la SEC y el concepto XBRL se muestran en un tooltip al posar el cursor.
   - En `financial_bilingual_map.py`, el matching por concepto XBRL exacto tiene prioridad sobre el texto, y el matching parcial de texto debe evaluar las claves ordenadas de mayor a menor longitud (`sorted(..., key=len, reverse=True)`) con un traductor heurístico por tokens para garantizar 0% de partidas en inglés en futuras empresas.
3. **Invariantes Contables Inquebrantables (`sanitize_and_validate_statements`):**
   - **Cero Imputación Falsa (`LTM != FY_latest`):** Prohibido asumir `delta_interino = 0.0` cuando una partida de flujo o balance no figure en el 10-Q.
   - **Cero Colisión Dimensional:** Filas con `dimension == True` (`Products`, `Services`, `Class A/B`) jamás pueden heredar el monto de la cuenta total consolidada.
   - **Signo Uniforme Longitudinal:** Toda fila de costos/gastos debe mantener el mismo signo algebraico entre `LTM` y todos los `FYxxxx`.
   - **Anclaje Canónico:** En `as_reported_statements`, las líneas troncales (Ingresos, Utilidad Neta, Activos Totales, Deuda LP, Dividendos, Recompras, CFO, CFI, CFF) deben estar reconciliadas con `canonical_summary`.