# Informe de Auditoría de Universalidad del Orquestador de Análisis Fundamental

**Fecha:** 9 de octubre de 2026
**Tipo:** Auditoría forense — solo lectura, sin cambios al código
**Pedido:** Verificar si datos pensados para una empresa pueden filtrarse a otras futuras y generar errores

---

## 1. Resumen en una página

Sí, hay fallas que rompen la universalidad, pero **no son del tipo "si ticker == NU"**.

Lo bueno:
- Ya no quedan montos fijos de Nubank o Apple en los motores (`$30.400M`, `26,4%`, etc. eliminados).
- El sistema ya distingue arquetipos: banco, aseguradora, REIT, plataforma, corporativa normal.

Lo malo:
1. **Las secciones 10 y 12 del informe se aplican a todas las empresas por igual**, incluso a bancos que no tienen inventario ni fábricas. Eso produce frases absurdas y números imposibles.
2. **Cuando falta un dato, el sistema pone 0 o AAA en silencio** en vez de decir "no disponible". Ese 0 luego se usa para calcular y contamina el resultado.
3. **Hay tres formas distintas de decir "es banco"** según el módulo, y no coinciden del todo. Una empresa futura puede caer en la categoría equivocada.
4. **Varios informes dicen "Apple Inc." por defecto** si alguien los llama sin indicar empresa. Hoy está mitigado, pero es un riesgo latente. Además hay rutas de Windows fijas que fallan en Linux.

**No se modificó ningún archivo de código** por tu indicación de "solo auditar".

---

## 2. Qué significa "universalidad" aquí

Tu proyecto promete esto:

> Cualquier empresa que entre por `data/processed/{TICKER}/` debe analizarse solo con sus propios datos auditados SEC, con la plantilla correcta para su tipo de negocio, sin heredar cifras, nombres ni supuestos de AAPL, NU, MELI u otra.

Si eso se rompe, una empresa nueva (ej. un banco regional en 2027) podría recibir:
- ratios de una industrial,
- un WACC de 9,5% inventado,
- una calificación AAA inmerecida,
- o el nombre "Apple Inc." en la portada.

Eso es lo auditado.

---

## 3. Cómo trabaja tu sistema (para entender las fallas)

1. **Extracción:** `pipeline/sec_extractor.py` descarga 10-K/10-Q XBRL de SEC EDGAR y guarda `financial_statements.json` con campo `archetype`.
2. **Scoring:** `pipeline/financial_scoring_engine.py` calcula Piotroski, Mohanram, Novy-Marx, ROIC/WACC, Altman, rating y guarda `fundamental_scores.json`.
3. **Informe:** `pipeline/generate_earnings_report.py` arma 14 secciones en Word y Markdown usando 5 constructores (Secc. 10 a 14).
4. **Excel:** modelo de 11 hojas con fórmulas vivas.
5. **Web:** `web_dashboard/` en Django lee esos JSON y muestra `/company/<TICKER>/`.

Empresas ya procesadas: AAPL, DECK (controles corporativos), NU (banco digital), MELI (híbrida), JPM, O, PGR, NVDA.

---

## 4. Hallazgo H1 — CRÍTICO: Secciones 10 y 12 no distinguen bancos

**En lenguaje simple:**
Al banco Nubank el informe le dice que es "líder en distribución mayorista" y le calcula días de inventario, cuando un banco no tiene galpones ni mercadería. También le calcula un retorno del capital de 6.051% porque casi no tiene máquinas físicas.

**Detalle técnico:**
- `pipeline/generate_earnings_report.py` líneas 1006 y 1012 llama siempre a Novy-Marx (Secc.10) y Forense Sloan/DIO/Montier (Secc.12), sin `if archetype == BANCO`.
- Esos dos constructores (`novy_marx_report_builder.py`, `forensic_report_builder.py`) no revisan si es banco o aseguradora.
- La Secc.11 ROIC/WACC sí está corregida y la 13 solvencia también. Faltan 10 y 12.

**Por qué pasó:**
El motor central ya inhibe Altman y ROC para bancos, pero el armado del Word no lo respeta para 10 y 12. Es el mismo problema que anotaste el 22/09/2026 en `CURRENT_CONTEXT.md`.

**Riesgo futuro:**
Todo banco, fintech o aseguradora nueva heredará narrativa industrial y números absurdos.

**Solución propuesta (pendiente de tu OK):**
Derivar Secc.10/12 por arquetipo: si es banco → NIM, ROTCE vs Ke, riesgo crédito IFRS9/CECL; si es seguro → Combined Ratio, float, RBC, P/BV; si es corporativa → mantener actual. Crear `banking_report_builder.py`.

---

## 5. Hallazgo H2 — ALTO: Datos faltantes se vuelven 0 o AAA

**En lenguaje simple:**
Si al sistema le falta un dato, en vez de escribir "N/D con explicación", escribe 0 o "AAA, máxima calidad". Luego ese 0 se usa en divisiones y promedios. Ejemplo: banco sin EBIT → EBIT=0 → cálculo roto pero parece válido. Empresa sin rating → aparece como AAA, la mejor nota.

**Lugares exactos:**
- `valuation_report_builder.py:228` WACC por defecto 9,5% si falta; `:231-236` deuda 5%, impuesto 20%, costo deuda 4,5%; `:241-245` acciones por defecto 100 millones; `:226` precio por defecto $100.
- `solvency_report_builder.py:282,447,656,807` y `valuation:660` rating por defecto AAA con texto "LIBRE DE DEUDA".
- `market_data_provider.py:203-204` beta 1,10 y WACC 8,5% si Yahoo/CNBC fallan; tasa libre riesgo 4,25%.
- `financial_scoring_engine.py:241,1892-1893` medianas WACC 8,8% y decenas de `or 0.0`.

**Riesgo futuro:**
Cualquier empresa nueva con dato incompleto (muy común en IPO, REIT, seguro pequeño) recibirá supuestos corporativos yanquis y parecerá solvente/rentable sin serlo.

**Solución propuesta:**
N/D estricto: propagar `None`, prohibir `or 0.0` en métricas no aplicables, AAA solo si se calculó cobertura de intereses, exigir precio/acciones/beta auditados o abortar con aviso claro.

---

## 6. Hallazgo H3 — MEDIO: Tres diccionarios distintos para decir "es banco"

**En lenguaje simple:**
Un módulo dice `FINANCIAL_BANKING`, otro `BANKING_FINANCIAL`, otro `CORPORATE_INDUSTRIAL`. El traductor central no conoce la última variante, y el informe tiene una lista corta de códigos SIC (solo 6 bancarios y 5 de seguros) distinta del extractor principal. Resultado: una empresa futura puede ser clasificada como "normal" por error.

**Lugares:**
- `kpi_extractor.py:309,522` produce variantes no canónicas.
- `sec_extractor.py:125-131` `normalize_archetype` no incluye `CORPORATE_INDUSTRIAL`.
- `generate_earnings_report.py:667-676` heurística propia.
- Tres funciones `get_*_archetype` en solvencia, valuación y ROIC con reglas distintas.

**Solución propuesta:**
Una sola función canónica de normalización, eliminar heurísticas locales, hacer `archetype` obligatorio desde `financial_statements.json`.

---

## 7. Hallazgo H4 — BAJO + portabilidad

**Nombres por defecto:**
Cinco constructores tienen `ticker="AAPL", company_name="Apple Inc."` por defecto (`novy_marx:217`, `roic_wacc:1070`, `forensic:169`, `valuation:710`, `governance:646`). Hoy no se manifiesta porque el orquestador pasa el ticker explícito (`generate_earnings_report.py:1006-1018`), pero si mañana alguien reutiliza un constructor suelto para JPM u O, saldrá "Apple Inc.".

**Rutas fijas Windows:**
`data\\processed` y `G:\\Mi unidad...` en `sec_extractor.py:43-44`, `drive_manager.py`, `doc_parser.py`, `config/sec_config.json`. En Linux (`/mnt/c/...`) fallan. El caché `market_data_cache.json` reutilizado en modo offline puede arrastrar precios viejos.

---

## 8. Qué se revisó y qué NO se tocó

Revisado con búsqueda de código:
- `ticker == "AAPL/DECK/NU..."` → 0 ramas activas en `pipeline/` (solo valores por defecto en firmas y tests). Bien.
- Montos duros NU/Apple → 0 en `pipeline/`. Bien (M3 efectivo).
- `or 0.0`, `AAA`, `0.095`, `Apple Inc.`, `data\\processed` → hallazgos H2-H4 arriba.
- Propagación `archetype` → parcial: scoring, solvencia, valuación y ROIC sí; Novy-Marx y forense no.

No se editó, borró ni creó código fuente. Este informe es el único archivo nuevo.

---

## 9. Próximos pasos sugeridos (requieren tu autorización explícita)

1. H1: separar Secc.10/12 por arquetipo + crear módulo bancario/aseguradora.
2. H2: reemplazar fallbacks silenciosos por N/D justificado (Regla 3 AGENTS.md).
3. H3: unificar `normalize_archetype` y eliminar SIC lists duplicadas.
4. Verificación triangulada obligatoria (Regla 2): tests unitarios + zero-regressions AAPL/DECK + inspección visual docx/xlsx/web/md.

Sin tu OK no se aplica ningún cambio, según Regla 1 STOP & PROPOSE y tu orden "solo auditar".

---

## Anexo — Referencias para el programador

- Flujo: `sec_extractor.py` → `audit_engine.py` → `financial_scoring_engine.py` → `generate_earnings_report.py (1006,1009,1012,1015,1018)` → `web_dashboard/analytics/views.py`
- Contratos: `financial_statements.json: archetype`, `canonical_summary.total_debt`; `fundamental_scores.json: archetype, altman_zone NO APLICABLE, greenblatt is_applicable False, wacc model_type WACC vs COST_OF_EQUITY_KE`
- Reglas: `AGENTS.md` 1 STOP&PROPOSE, 2 verificación triangulada, 3 pedagogía bancaria, 4 cero hardcode, 5 zero dead code
- Estado: `PROJECT.md` M1-M3 DONE, M4 IN_PROGRESS, M5 PLANNED; `QA_REPORT.md` 08/10/26 JPM 76%, NU 60,9% por identidades corporativas no aplicables
