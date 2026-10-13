---
name: fundamental-scoring-benchmark
description: >-
  Evaluates corporate financial health, solvency, growth quality, and pure capital productivity using Piotroski F-Score (0-9), Mohanram G-Score (0-8), Novy-Marx Gross Profitability to Assets (GP/A), Intangible-Adjusted ROIC (Damodaran roll-forward identity), Real-Time WACC multi-source extraction, and Economic Spread (EVA / Moat durability), maintaining dynamic peer group benchmarks and 9-sheet Excel financial models. Use this skill whenever calculating fundamental scores, benchmarking a company against industry peers, evaluating capital returns vs. hurdle rates, or formatting financial Excel workbooks.
---

# Fundamental Scoring & Benchmark Skill

Esta skill constituye el **motor cuantitativo y de benchmarking competitivo** del sistema de análisis fundamental. Su objetivo es evaluar la solidez interna, la calidad de crecimiento y la productividad pura del capital de las empresas cotizadas a través de los tres marcos académicos más rigurosos de Wall Street: el **Piotroski F-Score** (2000), el **Mohanram G-Score** (2005) y la **Rentabilidad Bruta sobre Activos de Robert Novy-Marx (GP/A)** (2013), contrastándolos de forma dinámica contra las medianas sectoriales auditadas del grupo de pares comparables (**Peer Group LTM**).

---

## 1. Cuándo activar esta Skill

Activa esta skill cuando el usuario solicite:
- Evaluar la solidez financiera o calidad contable mediante el **Piotroski F-Score (0-9 puntos)**.
- Evaluar la ventaja competitiva o estabilidad de crecimiento mediante el **Mohanram G-Score (0-8 puntos)**.
- Calcular e interpretar la **Rentabilidad Bruta sobre Activos de Novy-Marx (GP/A)**, su cálculo dual (Activos Totales vs. Ex-Caja), descomposición DuPont y matriz de 4 cuadrantes.
- Comparar una empresa contra su **Peer Group** o calcular **medianas sectoriales LTM** (ROA, CFROA, I+D, Reinversión, Gross Profitability).
- Generar el informe ejecutivo institucional en Word (`.docx`) y Markdown (`.md`).
- Visualizar métricas interactivas en la plataforma web Django (`web_dashboard/`).

---

## 2. Modelos Cuantitativos y Mejoras Institucionales

### A. Piotroski F-Score (Salud Financiera Interna: 0 a 9 Puntos)
Evalúa 3 dimensiones fundamentales de solvencia y eficiencia operativa:
1. **Rentabilidad:**
   - F1 (ROA > 0): Retorno positivo sobre activos promedio.
   - F2 (CFO > 0): Flujo de caja operativo positivo.
   - F3 (Delta ROA > 0): Expansión del retorno sobre activos respecto al ejercicio previo.
   - F4 (Calidad Sloan: CFO > Net Income): Ganancias respaldadas por efectivo real, libres de manipulaciones de devengo.
2. **Apalancamiento y Liquidez:**
   - F5 (Delta LEVER <= 0): Desendeudamiento financiero total real (deuda financiera corriente + no corriente).
   - F6 (Delta CR > 0): Expansión de la razón de liquidez corriente (Current Ratio).
   - F7 (EQ_OFFER <= 0): Ausencia de dilución accionarial, evaluada estrictamente sobre **Acciones Básicas** (aísla el efecto del Treasury Stock Method).
3. **Eficiencia Operativa:**
   - F8 (Delta Margin > 0): Expansión del margen bruto.
   - F9 (Delta Turn > 0): Aumento de la rotación de activos instalados.

### B. Mohanram G-Score (Calidad de Crecimiento vs. Industria: 0 a 8 Puntos)
Contrasta la empresa contra las **medianas dinámicas de sus competidores LTM**:
1. **Desempeño Financiero Sectorial:**
   - G1: ROA > Mediana del Sector (Hoja 8).
   - G2: CFROA (CFO / Activos) > Mediana del Sector (Hoja 8).
   - G3: CFO > Net Income (Calidad de devengo en empresas de crecimiento).
2. **Estabilidad y Consistencia:**
   - G4: Coeficiente de Variación de ROA menor a la mediana o inclusión en el **Percentil 75 Líder** de rentabilidad.
   - G5: Coeficiente de Variación del crecimiento de ventas menor a la mediana o **Cláusula de Hipercrecimiento** (g >= 20%).
3. **Inversiones en Ventaja Competitiva (Moat):**
   - G6: Intensidad de I+D (R&D / Activos) superior a la mediana del sector.
   - G7: Reinversión Total ([CapEx + R&D] / Activos) superior a la mediana, adaptada a modelos Asset-Light.
   - G8: Apalancamiento Operativo Comercial (% Delta Ventas > % Delta SG&A).

### C. Novy-Marx Gross Profitability to Assets (GP/A) (Productividad Pura del Capital)
Evalúa la eficiencia económica pura del capital instalado sin distorsiones de partidas extraordinarias o gastos de I+D/marketing:
1. **Cálculo Dual de Productividad y Efecto Arrastre de Caja (*Cash Drag*):**
   - $\text{GP/A Total} = \frac{\text{Utilidad Bruta}}{\text{Activos Totales}}$
   - $\text{GP/A Ex-Caja (Operativo)} = \frac{\text{Utilidad Bruta}}{\text{Activos Totales} - \text{Efectivo y Equivalentes}}$
   - $\text{Cash Drag} = \text{GP/A Ex-Caja} - \text{GP/A Total}$ (mide en p.p. la dilución por atesoramiento de liquidez ociosa).
2. **Descomposición DuPont de Novy-Marx:**
   - $\text{GP/A} = \text{Margen Bruto} \times \text{Rotación de Activos} = \left(\frac{\text{Utilidad Bruta}}{\text{Ingresos}}\right) \times \left(\frac{\text{Ingresos}}{\text{Activos}}\right)$
   - Verificación matemática estricta de la identidad ($|\text{Producto DuPont} - \text{GP/A}| < 0.005$).
3. **Matriz Estratégica de 4 Cuadrantes:**
   - **Cuadrante I: Compounder de Élite** (Margen Bruto > Mediana y Rotación > Mediana).
   - **Cuadrante II: Monopolio / Poder de Marca** (Margen Bruto > Mediana y Rotación <= Mediana).
   - **Cuadrante III: Líder en Volumen y Escala** (Margen Bruto <= Mediana y Rotación > Mediana).
   - **Cuadrante IV: Baja Productividad de Capital** (Margen Bruto <= Mediana y Rotación <= Mediana).
4. **Ajuste Sectorial (*Industry De-meaning*):**
   - $\text{GP/A Ajustada} = \text{GP/A}_{\text{empresa}} - \text{Mediana Sectorial}$.
   - Clasificación por percentiles: Top 5%, Top 25% (P75+), Superior a Mediana (P50-P75), Rezagada (<P50).
5. **Gestión Dinámica de Años Fiscales:**
   - Respeta estrictamente la cronología fidedigna de cada empresa reportada ante la SEC (ej. FY2026/LTM en DECK vs. FY2025/LTM en AAPL), sin fijar años estáticos.

### D. ROIC Ajustado por Intangibles, WACC en Tiempo Real y Creación de Valor (EVA)
Evalúa el verdadero rendimiento económico sobre el capital desplegado y la durabilidad de las ventajas competitivas (*Economic Moat*):
1. **Identidad Contable Roll-Forward de Intangibles (Damodaran & Mauboussin):**
   - $\text{Stock}_t = \text{Stock}_{t-1} + E_t - \text{Amort}_t$
   - **Cubeta I+D (R&D)**: 100% capitalizado, amortización lineal en $N_{RD}$ años (3-5 Tech, 8-10 Farma, 5 Semiconductores).
   - **Cubeta Marketing / Marca (SG&A)**: 20%-40% del SG&A capitalizado para marcas B2C de consumo masivo (DECK, NKE), amortizado en $N_{MKT} = 2-3$ años.
2. **Reconstitución de NOPAT y Capital Invertido:**
   - $\text{NOPAT}_{\text{Adj}} = [\text{EBIT} + (E_{RD} - \text{Amort}_{RD}) + (E_{MKT} - \text{Amort}_{MKT})] \times (1 - t)$
   - $\text{Capital Invertido}_{\text{Adj}} = \text{Activos Operativos} + \text{Stock Neto de Intangibles}$
   - $\text{ROIC}_{\text{Adj}} = \frac{\text{NOPAT}_{\text{Adj}}}{\text{Capital Invertido}_{\text{Adj}}}$
3. **Cálculo del WACC con Validación Cruzada en Tiempo Real:**
   - Extracción contemporánea multi-fuente: Yahoo Finance (`^TNX`, `quoteSummary`) vs. CNBC Quote Service (`US10Y`, quotes).
   - $K_e$ vía CAPM: $K_e = R_f + \beta \times \text{ERP}$.
   - Ponderaciones a valor de mercado ($E$ y $D$). Arbitraje con SEC Form 10-Q (acciones diluidas).
   - Manejo de empresas sin deuda ($D = 0 \implies \text{WACC} = K_e$) y con exceso de caja.
4. **Spread Económico y Durabilidad del Foso Defensivo (*Economic Moat*):**
   - $\text{Spread} = \text{ROIC}_{\text{Adj}} - \text{WACC}$
   - $\text{Spread} > +15\%$: **Foso Defensivo Excepcional (*Wide Moat / Compounding Machine*)**.
   - $\text{Spread} \in [+5\%, +15\%]$: **Foso Defensivo Sólido (*Narrow Moat*)**.
   - $\text{Spread} \in [0\%, +5\%]$: **Rendimiento Competitivo Estándar**.
   - $\text{Spread} < 0\%$: **Destrucción Neta de Valor Económico**.
5. **Matriz de Sensibilidad de Vida Útil 3D:**
   - Evalúa la estabilidad del ROIC y del Spread ante variaciones de vida útil en $N-1$, $N$, y $N+1$ años.

---

## 3. Comandos y Scripts Disponibles

```powershell
# 1. Ejecutar el cálculo completo de scores cuantitativos (Piotroski, Mohanram y Novy-Marx):
python .agents/skills/fundamental-scoring-benchmark/scripts/run_scoring.py AAPL

# 2. Actualizar el modelo financiero interactivo en Excel (Hojas 1 a 8):
python .agents/skills/fundamental-scoring-benchmark/scripts/update_excel_model.py AAPL

# 3. Generar el informe institucional en Word (.docx) y Markdown (.md):
python .agents/skills/fundamental-scoring-benchmark/scripts/generate_report.py AAPL
```

---

## 4. Fuentes de Verdad y Archivos Consumidos

- **Pares y Medianas Oficiales:** `config/peer_benchmarks.json` (Primaria con datos LTM auditados y métricas GP/A) y `config/industry_medians.json` (Respaldo sectorial por código SIC).
- **Entrada Financiera:** `data/processed/<TICKER>/financial_statements.json`.
- **Salidas Producidas:**
  - `data/processed/<TICKER>/fundamental_scores.json`: Resultados detallados de F-Score, G-Score, matriz combinada y `novy_marx_analysis`.
  - `data/processed/<TICKER>/Analisis_Resultados_<TICKER>.docx`: Informe Word institucional con Sección 11 de Novy-Marx GP/A en 4 bloques.
  - `data/processed/<TICKER>/Analisis_Resultados_<TICKER>.md`: Informe Markdown sincronizado.
  - Plataforma Web Django (`web_dashboard/`): Panel interactivo por empresa con visualización en tiempo real.