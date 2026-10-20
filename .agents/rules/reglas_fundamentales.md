---
trigger: always_on
description: "Reglas institucionales de auditoría contable, parada obligatoria (STOP & PROPOSE), cero datos inventados y verificación triangulada."
---
# REGLAS FUNDAMENTALES DEL PROYECTO: ORQUESTADOR UNIVERSAL DE ANÁLISIS FUNDAMENTAL

Estas reglas son de cumplimiento continuo, irrestricto y mandatorio para todo agente de IA y desarrollador que opere en este proyecto. Tienen prioridad absoluta sobre cualquier iniciativa de refactorización o edición de código.

---

## REGLA 1: PROTOCOLO DE PARADA OBLIGATORIA ANTE ERRORES DE CÁLCULO O DISEÑO (STOP & PROPOSE)
Cuando se detecte cualquier error en el código de los scripts que involucre:
- Fallos o discrepancias en cálculos contables o cuantitativos (fórmulas rotas, denominadores cero, valores nulos no controlados, desbordes).
- Errores de diseño o visualización (tablas desalineadas, campos vacíos o 'N/D' no justificados, discrepancias entre el informe Word y la web Django).
- Excepciones en tiempo de ejecución (`TypeError`, `ValueError`, `KeyError`, etc.).

**MANDATO:**
1. **PARADA AUTOMÁTICA INMEDIATA:** Queda estrictamente PROHIBIDO continuar editando o encadenar "parches rápidos" sobre la marcha.
2. **DIAGNÓSTICO FORENSE:** Se debe pausar la edición, aislar la causa raíz y formular un informe de diagnóstico con:
   - Archivo(s) y número(s) de línea exactos donde se origina la discrepancia.
   - Causa raíz técnica y contable (qué dato falló, cómo se extrajo y por qué).
   - Solución propuesta detallada (lógica algorítmica, cambios exactos y consecuencias en la arquitectura).
3. **VALIDACIÓN PREVIA DEL USUARIO:** Antes de aplicar cualquier modificación al código fuente, se debe exponer la propuesta y su explicación al usuario. NO se tocará ningún archivo hasta contar con la evaluación y aprobación explícita del usuario.

---

## REGLA 2: MÉTODO DE TESTEO Y VERIFICACIÓN TRIANGULADA OBLIGATORIA (VERIFICATION PROTOCOL)
Ninguna solución, corrección o nueva funcionalidad puede darse por concluida ni considerarse aprobada únicamente porque un script termine sin arrojar excepciones (`exit code 0`). Toda propuesta debe acompañarse obligatoriamente de un método de testeo multidimensional:

1. **Test Lógico y Matemático (Unitario):**
   - Ejecución o creación de tests automatizados (suite `tests/`) que verifiquen matemáticamente la consistencia de las fórmulas, tolerancias de redondeo y manejo de valores límite/nulos.
2. **Test de Regresión Universal (Zero Regressions):**
   - Validación cruzada para certificar que el cambio no altere, degrade ni distorsione los resultados de las empresas de control previas (ej. `AAPL` y `DECK` para el ámbito corporativo/industrial).
3. **Test de Inspección Visual de Artefactos Reales:**
   - **Documento Word (.docx):** Verificación directa de tablas, alineaciones, badges institucionales, formatos de moneda/porcentaje y encabezados.
   - **Dashboard Web Django:** Comprobación de que las tarjetas de resumen y la vista de detalle reflejen con precisión los mismos valores auditados del informe.
   - **Informe Markdown (.md):** Verificación de sintaxis, renderizado de tablas y fórmulas KaTeX.

---

## REGLA 3: TRANSPARENCIA Y PEDAGOGÍA CONTABLE EN NUEVAS MÉTRICAS Y SECTORES
En empresas financieras (bancos, fintechs, prestamistas digitales) o modelos atípicos:
1. Las métricas corporativas tradicionales que no apliquen (como fondo de maniobra, ratio corriente, margen bruto o COGS) no deben ocultarse arbitrariamente ni dejarse en blanco sin explicación.
2. Todo nuevo ratio (NIM, NPLs / Morosidad, Ratio de Eficiencia, Cost of Risk, Cobertura de Provisiones, ROE / ROTCE, CET1) debe ir acompañado en los informes de su respectiva guía pedagógica institucional:
   - Qué mide exactamente la métrica.
   - Fórmula contable utilizada.
   - Cómo se interpreta el resultado (umbrales de mercado / benchmarks).
   - Justificación de por qué reemplaza o complementa al análisis no financiero.

---

## REGLA 4: PRESERVACIÓN DEL ORQUESTADOR UNIVERSAL Y AISLAMIENTO DE DATOS
1. Queda estrictamente prohibido introducir valores hardcodeados (`if ticker == "..."`) o parámetros fijos de una empresa en los motores de cálculo, constructores de informes o vistas web.
2. Toda lógica debe ser invariante de escala, dinámica y derivada exclusivamente de los archivos procesados de la empresa en curso (`data/processed/{TICKER}/`).
3. El desglose de segmentos de negocio, geografía de distribución y benchmarking de pares sectoriales debe generarse dinámicamente según la taxonomía y perfil de cada compañía.
