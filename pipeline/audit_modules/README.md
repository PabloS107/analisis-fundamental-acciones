# Submódulos de Auditoría Contable e Integridad Temporal (`pipeline/audit_modules/`)

Contiene los módulos encargados de garantizar la consistencia matemática, temporal y regulatoria de los artefactos en `data/processed/{TICKER}/`, complementando las 6 pruebas por período de [`../audit_engine.py`](../audit_engine.py).

---

## 1. Módulos y Responsabilidades

### 1. [`period_integrity.py`](./period_integrity.py)
Motor determinista y sin dependencia de red que evalúa **5 invariantes universales (P1–P5)** sobre `financial_statements.json` y `cross_verification_report.json`:

| Código | Check | Qué Verifica | Severidades Posibles |
| :--- | :--- | :--- | :--- |
| **P1** | `METADATA_PRESENTE` | Que exista el bloque `sec_metadata` certificando la procedencia del `LTM`. | `PASS` / `WARN` |
| **P2** | `PERIODO_NO_POSTERIOR` | Que `ltm_period_end <= latest_periodic_date` (el cierre contable no puede ser posterior a la fecha de presentación del filing). | `PASS` / `WARN` / `ERROR` |
| **P3** | `PERIODO_NO_FUTURO` | Que `ltm_period_end <= fecha de extracción`. | `PASS` / `ERROR` |
| **P4** | `LTM_IGUAL_FY` | Si el último formulario periódico es anual (`10-K`, `20-F`, `40-F`) y `ltm_period == latest_fy`, comprueba en todas las filas no abstractas de `as_reported_statements` (`income_statement`, `balance_sheet`, `cash_flow_statement`) que `LTM == FY_reciente` dentro de `LTM_FY_REL_TOLERANCE = 0.001` (o `$1`). | `PASS` / `ERROR` |
| **P5** | `VERIFICACION_VIGENTE` | Calcula el SHA-256 (`file_fingerprint`) de `financial_statements.json` y valida que coincida con `source_fingerprint` de `cross_verification_report.json` (con respaldo por fecha en reportes legacy). | `PASS` / `WARN` (`MISSING`, `STALE`, `LEGACY_UNVERIFIABLE`) |

Funciones expuestas: `file_fingerprint`, `check_period_integrity`, `check_verification_freshness`, `run_period_integrity`.

---

### 2. [`data_verifier.py`](./data_verifier.py)
Motor de **verificación cruzada tripartita** y auditoría sectorial de pares:

1. **Verificación Tripartita por Emisora (`verify_financial_data`)**:
   - Contrasta cada ejercicio activo (y `LTM`) de `financial_statements.json` frente a:
     1. Extracción local SEC (`canonical_summary` y ecuación de balance `audit_engine.audit_balance_sheet`).
     2. API oficial **SEC Company Facts** (`data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json`, aplicando *Latest Filed Priority* en `extract_fact_annual_series`).
     3. Agregador de mercado informativo (`yfinance`).
   - Evalúa `Revenue`, `Net Income`, `CFO`, `CapEx`, `FCF`, `Diluted EPS` (raw vs `eps_diluted_adjusted` con detección de splits `_STANDARD_SPLIT_FACTORS`), `Diluted Shares` y la Ecuación Fundamental del Balance.
   - Asigna estados auditables: `EXACT_MATCH` (<= 0.05%), `RECONCILED` (<= `tolerance_pct`, por defecto 2.5%), `SPLIT_ADJUSTED`, `FLAGGED`, `SINGLE_SOURCE` (sin dato equivalente en SEC Company Facts) o `INCOMPLETE`.
   - Dictamen global (`overall_status`): `CERTIFIED_VALID`, `PARTIALLY_VERIFIED` o `OBSERVATIONS_FLAGGED`.
   - Incluye `source_fingerprint` (SHA-256 de `financial_statements.json`) para enlazar con el control `P5` de `period_integrity.py`.

2. **Auditoría de Grupo de Pares (`verify_peer_group_benchmarks`)**:
   - Consulta SEC Company Facts para los competidores definidos en `config/peer_benchmarks.json` (resueltos mediante `PEER_CIK_CATALOG` y el target local en `data/processed/{TICKER}/financial_statements.json`).
   - Recalcula intensidades de I+D, reinversión total, ROA y CFROA, actualiza `config/peer_benchmarks.json` de forma atómica y sincroniza los reportes hacia Google Drive (`_sync_reports_to_drive`).

#### Ejecución por CLI
```powershell
python pipeline/audit_modules/data_verifier.py --ticker DECK
python pipeline/audit_modules/data_verifier.py --ticker DECK --verify-peers
```

---

## 2. Artefactos Producidos y Validados

| Artefacto | Rol del Subpaquete | Contenido Clave |
| :--- | :--- | :--- |
| `data/processed/{TICKER}/audit_report.json` | Escrito por [`../audit_engine.py`](../audit_engine.py) incluyendo resultados `P1–P5` de `period_integrity.run_period_integrity()` | `overall_status`, `compliance_score_pct`, `years_audited`, `period_integrity` |
| `data/processed/{TICKER}/cross_verification_report.json` y `.md` | Generados por `data_verifier.verify_financial_data()` | `fidelity_score_pct`, `overall_status`, `source_fingerprint` (SHA-256), `detailed_reconciliations` |
| `data/processed/{TICKER}/peer_verification_report.json` y `.md` | Generados por `data_verifier.verify_peer_group_benchmarks()` | Cifras auditadas de competidores (`revenue_usd_m`, `assets_usd_m`, `roa_pct`, `cfroa_pct`, `rd_intensity_pct`) |
| `config/peer_benchmarks.json` | Actualizado atómicamente por `verify_peer_group_benchmarks()` | Cifras LTM/anuales auditadas del grupo de pares consumidas por `scoring_utils.py` |

---

## 3. Matriz de Impacto ante Modificaciones

| Script Modificado | Artefactos JSON/Config Afectados | Módulos Aguas Abajo Dependientes | Comandos `unittest` Recomendados tras Editar |
| :--- | :--- | :--- | :--- |
| `period_integrity.py` | - `audit_report.json` (bloque `period_integrity` al correr `audit_engine`)<br>- `cross_verification_report.json` (provee `file_fingerprint` a `data_verifier.py`) | - `pipeline/audit_engine.py` (`run_full_audit`)<br>- `pipeline/audit_modules/data_verifier.py`<br>- `pipeline/fundamental_pipeline.py` (Paso C)<br>- `tests/health_check.py` | `python -m unittest tests/accounting_audit/test_period_integrity.py tests/accounting_audit/test_audit_engine.py -v` |
| `data_verifier.py` | - `data/processed/{TICKER}/cross_verification_report.json` y `.md`<br>- `data/processed/{TICKER}/peer_verification_report.json` y `.md`<br>- `config/peer_benchmarks.json` (si se usa `--verify-peers`) | - `period_integrity.py` (control `P5 VERIFICACION_VIGENTE`)<br>- `scoring_modules/scoring_utils.py` y `novy_marx` / `greenblatt_roc` (si actualiza `config/peer_benchmarks.json`)<br>- Google Drive (`_sync_reports_to_drive`) | `python -m unittest tests/accounting_audit/test_period_integrity.py tests/sec_extraction/test_ifrs_taxonomy.py tests/accounting_audit/test_balance_sheet_reconciliation.py -v` |

### Verificación Global del Subpaquete

```powershell
python -m unittest discover -s tests/accounting_audit -v
```
