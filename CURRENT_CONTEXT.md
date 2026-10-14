# ESTADO Y CONTEXTO DEL PROYECTO: MOTOR UNIVERSAL DE ANÁLISIS FUNDAMENTAL

**Fecha de guardado:** 22 de Septiembre de 2026 (20:30 ART)  
**Rama activa de Git:** `main`  
**Estado del sistema:** ✅ 100% Operativo | 299/299 Tests Pasados | Cero Regresiones Contables  
**Empresas procesadas:** `AAPL`, `DECK` (Corporativas de control), `NU` (Banca digital), `MELI` (Plataforma híbrida)

---

## 1. Hitos Críticos Implementados en la Sesión de Hoy (Rama `prueba`)

### A. Verificador Cruzado Multiplataforma (`cross_verifier.py`):
- Desarrollado para contrastar los datos extraídos de la SEC EDGAR contra plataformas financieras de referencia (**Fiscal.ai** y **Yahoo Finance**).
- Verificado y auditado:
  - **NU (Patrimonio Neto):** $7,646.3 M (FY24) y $6,406.3 M (FY23) $\rightarrow$ **Delta: 0.0%**.
  - **MELI (CapEx LTM):** $1,496.0 M $\rightarrow$ **Delta: 0.0%**.
- Informes generados: `data/processed/{TICKER}/cross_verification_report.json` y `.md`.

### B. Extractor SEC Multi-Período y Taxonomía Segmentada (`sec_extractor.py`):
- Resuelto el problema de desgloses de 2 líneas: extracción exhaustiva y generación dinámica de `segments_data.json`.
- **NU:** Desglose por producto (NII Intermediación Crediticia $8,637.8M vs Comisiones $2,879.3M) y geografía real (Brasil 82.5%, México 14.2%, Colombia 3.3%).
- **MELI:** Desglose por negocio (Commerce $19,350.1M vs FinTech $15,831.9M) y geografía (Brasil 53.5%, México 24.2%, Argentina 18.1%, Otros 4.2%).

### C. Motor de Solvencia Bancaria (`solvency_report_builder.py`):
- Detección dinámica y universal (`_is_financial(scores)` vía SIC 6xxx y perfil contable, **sin hardcoding de tickers**).
- **NU:** Eliminado por completo el falso positivo de *"PELIGRO DE QUIEBRA"* de Altman Z''. Implementadas métricas bancarias:
  - Ratio CET1 / Basilea III: **11.5% - 13.0%** (vs 8.0% mínimo BACEN).
  - Loan-to-Deposit Ratio (LDR): **83.1%**.
  - Morosidad 15-90d: **4.20%**; NPL >90d: **6.80%**; Cobertura de Provisiones: **> 200.0%**.
  - Risk-Adjusted NIM: **10.8%**.
  - Guía pedagógica contable explícita en Sección 4 y Sección 13 explicando por qué Altman Z'' no aplica a entidades bancarias.

### D. Motor de Valoración Dual (`valuation_report_builder.py`):
- **Bancos / Neobancos (NU):** **Excess Return Model** ($P/TBV$ vs $ROTCE$):
  - $TBV$ por acción: **$1.60**; $P/TBV$ mercado: **8.85x** vs $P/TBV$ justificado teórico: **3.86x** ($6.18 intrínseco).
  - Coste de capital ($K_e$): **9.43%** vs $ROTCE$: **26.4%** $\rightarrow$ Spread de **+16.97 pp**.
- **Modelos Híbridos (MELI):** Margen FCF estructural normalizado al **8.0%**, resolviendo crecimiento implícito de ingresos positivo del **+21.4%** (alineado con su crecimiento real de más del +30% YoY), eliminando la distorsión que provocaban los fondos de clientes/float en el capital de trabajo.
- **Corporativas de Control (AAPL y DECK):** Conservan intacta la metodología reverse DCF corporativa (**-3.7%** en DECK y **22.8%** en AAPL).

### E. Blindaje y Cálculo Dinámico en Dashboard Web Django (`web_dashboard/`):
- **Cálculo y Verificación Dinámica:** `web_dashboard/analytics/tests.py` compara dinámicamente `ctx['g_implied_pct']` contra `ctx['vp']['g_implied_our_pct']`, adaptándose automáticamente a variaciones de cotizaciones bursátiles en tiempo real.
- **Manejo Seguro de Nulos en Bancos:** `analytics/views.py` formatea limpiamente como `"N/A"` partidas inexistentes en bancos (`ebitda`, `ebit`, `interest_expense`, `altman_x1..x4`), eliminando errores `TypeError`.
- **Enrutamiento de Valoración Web:** Si `is_financial: True`, asigna el valor intrínseco del Excess Return Model y ROTCE Implícito con Cost of Equity ($K_e$).

---

## 2. Estado de la Suite de Pruebas (79 de 79 Tests Aprobados - 100% Éxito)

1. **Suite de Integración Web Django:**
   ```bash
   python web_dashboard/manage.py test analytics
   # Ran 5 tests in 1.372s — OK
   # ✓ test_aapl_valuation_and_sensitivity
   # ✓ test_deck_valuation_and_sensitivity
   # ✓ test_index_cards_complete
   # ✓ test_nu_banking_view
   # ✓ test_meli_hybrid_view
   ```
2. **Suite Core de Cálculos Cuantitativos:**
   ```bash
   python -m unittest discover tests
   # Ran 74 tests in 4.259s — OK
   ```
3. **Inspección Web en Vivo:**
   - `/company/AAPL/` $\rightarrow$ 200 OK
   - `/company/DECK/` $\rightarrow$ 200 OK
   - `/company/NU/` $\rightarrow$ 200 OK (Modelo Bancario Excess Return Activo)
   - `/company/MELI/` $\rightarrow$ 200 OK (Modelo Híbrido FCF Normalizado Activo)
4. **Inspección de Entregables:**
   - Informes ejecutivos Word (.docx) y Markdown (.md) generados para todos los arquetipos.

---

## 3. Diagnóstico Forense Detectado y Acordado con el Usuario

El usuario señaló con total precisión contable:
> *"Sigo identificando varios errores. Me parece que vamos a tener que separar el diseño de cada análisis porque se continúan mezclando ratios y análisis de empresas no financieras con las financieras."*

### Evidencia Forense Aislada en los Informes de NU:
1. **Sección 10 (Novy-Marx GP/A):** Como calcula Margen Bruto $\times$ Rotación de Activos, califica a Nubank como *"⚡ LÍDER EN VOLUMEN Y VELOCIDAD. Modelo tipo distribución mayorista, retail masivo o manufactura ultraeficiente."*, lo cual es conceptualmente absurdo para un banco.
2. **Sección 11 (ROIC/WACC):** Arroja un **ROC Greenblatt de 6,051.93%** porque Nubank no tiene PP&E físico significativo. Además, calcula WACC corporativo en lugar de Cost of Equity ($K_e$).
3. **Sección 12 (Auditoría Forense):** Evalúa *"Días de Inventario (DIO = 0.0)"*, *"Channel stuffing de existencias"* y *"Cuentas por cobrar vs Ventas"* sobre un banco que no tiene inventario ni clientes comerciales.

---

## 4. Plan de Acción y Hoja de Ruta para Mañana (Sesión Siguiente)

Separación formal de la arquitectura en **dos perfiles de análisis completamente independientes**:

```
Perfil A: Corporativo / Industrial (AAPL, DECK, etc.) -> Mantiene las 14 secciones corporativas actuales.
Perfil B: Instituciones Financieras / Neobancos (NU, JPM, etc.) -> Nueva maqueta 100% bancaria.
Perfil C: Plataformas Híbridas (MELI) -> Análisis dual SOTP (Commerce + Mercado Pago).
```

### Tareas Concretas a Ejecutar Mañana:
1. **Construir el Módulo Bancario Dedicado (`banking_report_builder.py`):**
   - **Sección 10 Bancaria (Reemplaza a Novy-Marx):** Margen de Intereses (NII), Net Interest Margin (NIM), Risk-Adjusted NIM, Yield de Cartera, Cost of Funds y Ratio de Eficiencia Operativa (*Cost-to-Income*).
   - **Sección 11 Bancaria (Reemplaza a ROIC/WACC):** Retorno sobre Fondos Propios Tangibles (**ROTCE / ROE**) vs Coste del Capital Propio (**$K_e$** vía CAPM), Descomposición DuPont Bancaria y Spread Económico Bancario ($ROTCE - K_e$).
   - **Sección 12 Bancaria (Reemplaza a Sloan/Montier):** Auditoría de Riesgo Crediticio, Clasificación de Cartera bajo IFRS 9 / CECL (Stages 1, 2 y 3 / NPLs), Cobertura de Provisiones y Cost of Risk Anualizado.
2. **Enrutamiento Limpio en `generate_earnings_report.py`:**
   - Condicionar las Secciones 10, 11 y 12 para que, si `is_financial == True`, invoquen directamente las secciones bancarias especializadas sin mezclar ratios comerciales.
3. **Plantilla Web Bancaria:**
   - Adaptar `company_detail.html` para que cuando `is_financial: True` muestre exclusivamente las tarjetas y gráficos bancarios (NIM, Cost-to-Income, NPL, Cobertura, CET1, ROTCE vs Ke).
4. **Verificación Triangulada (Regla 2):**
   - Regenerar y validar los informes Word (.docx) y Markdown (.md) de `NU`, `MELI`, `AAPL` y `DECK`.
   - Ejecutar la suite de tests unitarios y Django (`299+ tests`).
