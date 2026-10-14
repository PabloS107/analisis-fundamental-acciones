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

4. **Principio de Corrección en la Raíz Universal (Root-Level Fixes for Future Companies):** Toda corrección, incorporación de conceptos contables o ajuste algorítmico detectado en una empresa (ej. `META`) debe formularse e implementarse **exclusivamente en la raíz del motor** (`pipeline/sec_extractor.py`, `pipeline/financial_taxonomy.py`, `web_dashboard/analytics/views.py`). Queda terminantemente prohibido crear soluciones cosméticas o parches aislados; cada cambio debe enriquecer la taxonomía canónica y las identidades contables para que beneficie de forma permanente y automática al 100% de las futuras empresas procesadas.

5. **Alcance Universal Condicionado al Arquetipo de Negocio (Archetype-Scoped Universal Fixes):**
   - Cuando se resuelva una anomalía, cálculo o métrica en el motor central, la solución debe propagarse automáticamente a todas las empresas del sistema **cuyo modelo contable lo amerite**.
   - Queda prohibido alterar o forzar métricas sobre arquetipos para los cuales la métrica sea conceptualmente inaplicable (por ejemplo: el Montier C-Score tradicional o ratios de inventario/COGS aplican universalmente a empresas comerciales, industriales y tecnológicas, pero no deben imponerse sobre el arquetipo bancario/financiero donde el balance y los flujos operan bajo otra taxonomía).
   - El motor debe identificar dinámicamente el arquetipo de la empresa y aplicar la corrección universal a todas las compañías que compartan dicha naturaleza contable.

---

## REGLA 5: ELIMINACIÓN DEFINITIVA DE CÓDIGO OBSOLETO Y PREVENCIÓN DE DEUDA TÉCNICA (CLEAN REFACTORING & ZERO DEAD CODE)
1. Queda estrictamente PROHIBIDO conservar código obsoleto, ramas lógicas erróneas comentadas (`# TODO: old code`), acumulaciones de condicionales huérfanas o parches acumulativos defensivos que enmascaren la causa raíz.
2. Cada vez que se corrija un algoritmo, una fórmula o una extracción contable, **las líneas de código erróneas o que generaban el problema deben ser eliminadas en su totalidad**, dejando únicamente la lógica canónica refactorizada.
3. El código debe mantenerse esbelto, trazable, auto-documentado y libre de redundancias.

---

## REGLA 6: INTEGRIDAD DE DATOS, PROHIBICIÓN DE VALORES POR DEFECTO FICTICIOS Y OBSERVABILIDAD DE FALTANTES (ZERO FAKE DEFAULTS)
1. **Prohibición de Imputación Silenciosa / Valores Falsos:** Cuando un KPI, ratio contable, partida de balance o flujo de caja no pueda extraerse o calcularse para un período (sea LTM o un año fiscal determinado), queda **terminantemente PROHIBIDO** imputar un valor sustituto aproximado, inventar cifras o forzar un `0.0` artificial que oculte la ausencia del dato.
2. **Señalización Explícita y Observabilidad (`N/D` / Alerta Visual):** El dato no encontrado debe señalarse de forma inequívoca en la interfaz web y en los informes como **`N/D`** o con un badge/indicador visual de advertencia (*"Dato No Disponible / Pendiente de Mapeo XBRL"*).
3. **Trazabilidad Forense para la Corrección en la Raíz:** Todo valor faltante debe quedar registrado en el log de auditoría (`data/processed/{TICKER}/audit_report.json`). Esta señalización abierta es lo que permite al analista y al desarrollador identificar con precisión quirúrgica qué etiqueta XBRL falta en `financial_taxonomy.py` o qué cálculo falló en el motor, procediendo a corregirlo en la raíz del proyecto para todas las empresas presentes y futuras.

---

## REGLA 7: SINCRONIZACIÓN AUTOMÁTICA Y OBLIGATORIA CON EL REPOSITORIO GITHUB (AUTO-SYNC TO GITHUB)
1. **Commit & Push Inmediato:** Cada vez que se implemente, valide o modifique cualquier archivo, script, modelo, prueba o plantilla en el proyecto y los tests/auditorías hayan concluido satisfactoriamente, los cambios deben confirmarse (`git commit`) y enviarse automáticamente e inmediatamente al repositorio remoto de GitHub (`git push origin <rama_activa>`).
2. **Mensajes de Commit Descriptivos:** Los mensajes de commit deben ser claros, estructurados y reflejar con precisión técnica el alcance del cambio (convención conventional commits: `feat:`, `fix:`, `refactor:`, `test:`, `docs:`).
3. **Cero Cambios Huérfanos:** Queda estrictamente prohibido finalizar una intervención, refactorización o corrección dejando modificaciones locales pendientes de sincronizar con el repositorio remoto de GitHub.
