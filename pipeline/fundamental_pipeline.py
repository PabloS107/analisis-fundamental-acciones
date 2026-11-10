"""
fundamental_pipeline.py - Orquestador maestro para extracción de datos fundamentales.
Incluye:
- Pre-Flight Checks (Comprobaciones previas de conectividad, identidad y Drive).
- Extracción oficial SEC EDGAR (XBRL US-GAAP / IFRS y Segmentos).
- Extracción de KPIs operativos y métricas Non-GAAP (8-K/6-K Ex-99.1 y presentaciones).
- Post-Flight Audit (Motor de Auditoría Contable y Sanidad).
- Módulo de Gobernanza y Transacciones de Insiders.
- Motor Cuantitativo de Scoring Fundamental para el Dashboard Web.
- Sincronización automática en Google Drive.
"""

import argparse
import logging
import sys
from typing import Callable, Optional

logger = logging.getLogger(__name__)

# UTF-8 para consola en Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError, OSError) as exc:
        logger.debug("No se pudo reconfigurar stdout a UTF-8: %s", exc)

# Soportar importación tanto como paquete (`pipeline.fundamental_pipeline`) como script directo
try:
    from .config_loader import (
        load_sec_config,
        resolve_local_output_base,
        resolve_output_dir,
    )
    from .sec_extractor import extract_sec_data
    from .sec_modules.filing_context import SharedFilingContext
    from .drive_manager import (
        resolve_google_drive_path,
        safe_copy_file,
        get_ticker_drive_processed_dir,
    )
    from .audit_engine import run_full_audit
    from .governance_insider_analyzer import analyze_governance_and_insiders
    from .financial_scoring_engine import calculate_fundamental_scores
    from .kpi_extractor import extract_operational_kpis
except ImportError:
    from config_loader import (
        load_sec_config,
        resolve_local_output_base,
        resolve_output_dir,
    )
    from sec_extractor import extract_sec_data, SharedFilingContext
    from drive_manager import (
        resolve_google_drive_path,
        safe_copy_file,
        get_ticker_drive_processed_dir,
    )
    from audit_engine import run_full_audit
    from governance_insider_analyzer import analyze_governance_and_insiders
    from financial_scoring_engine import calculate_fundamental_scores
    from kpi_extractor import extract_operational_kpis


def pre_flight_checks(ticker):
    """Comprobaciones preventivas antes de iniciar la extracción."""
    print(f"\n[Pre-Flight Check] Verificando entorno para {ticker.upper()}...")
    cfg = load_sec_config()

    # 1. Identidad SEC
    identity = cfg.get("sec_identity", "")
    if not identity or "@" not in identity:
        raise ValueError("[Pre-Flight Error] Configuración de identidad SEC inválida en config/sec_config.json")
    print(f"  [OK] Identidad SEC configurada: {identity}")

    # 2. Google Drive
    drive_base = resolve_google_drive_path()
    if drive_base.exists():
        print(f"  [OK] Unidad de Google Drive accesible: {drive_base}")
    else:
        print(f"  [AVISO] Unidad de Google Drive no detectada en {drive_base}. Se usará carpeta local como respaldo.")

    # 3. Directorio de trabajo
    local_out = resolve_local_output_base(cfg)
    local_out.mkdir(parents=True, exist_ok=True)
    print(f"  [OK] Directorio de salida preparado: {local_out}")
    print("[Pre-Flight Check] Todas las comprobaciones previas SUPERADAS exitosamente.\n")


def sync_to_google_drive(ticker, local_output_dir, custom_drive_path=None):
    """Copia los archivos finales generados a Google Drive con reintentos para evitar bloqueos del cliente de sincronización."""
    cfg = load_sec_config()
    if not cfg.get("sync_output_to_drive", True):
        return

    processed_drive = get_ticker_drive_processed_dir(ticker, custom_drive_path)
    if not processed_drive:
        print("[Pipeline Sync] No se pudo localizar la carpeta de Google Drive para sincronización.")
        return

    print(f"\n[Pipeline Sync] Sincronizando salidas con Google Drive: {processed_drive}...")
    for item in local_output_dir.iterdir():
        if item.is_file():
            dst = processed_drive / item.name
            ok = safe_copy_file(item, dst, max_retries=4, base_delay=0.5)
            if ok:
                print(f"  -> Copiado a Drive: {item.name}")
            else:
                print(f"  [AVISO] No se pudo sincronizar {item.name} en Google Drive.")

    print("[Pipeline Sync] Sincronización con Google Drive finalizada.")


def run_pipeline(
    ticker: str,
    custom_drive_path=None,
    custom_output_dir=None,
    progress_callback: Optional[Callable[[str, int], None]] = None,
):
    """Ejecuta el pipeline completo de extracción, auditoría y scoring fundamental."""
    def _notify(msg: str, pct: int):
        if progress_callback is not None:
            progress_callback(msg, pct)

    ticker = ticker.strip().upper()

    print(f"\n{'='*70}")
    print(f"  INICIANDO PIPELINE FUNDAMENTAL PARA: {ticker}")
    print(f"{'='*70}")

    _notify("Verificando identidad SEC e inicializando directorios...", 10)
    pre_flight_checks(ticker)

    out_dir = resolve_output_dir(ticker, custom_output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Manifiesto Único en Memoria (SharedFilingContext)
    filing_context = SharedFilingContext(ticker)

    # Paso A: Extracción SEC EDGAR
    _notify("Conectando con SEC EDGAR y descargando estados financieros 10-K / 10-Q...", 25)
    financials, _ = extract_sec_data(ticker, out_dir, filing_context=filing_context)

    # Paso B: Extracción y Conciliación de KPIs Operativos y Métricas Non-GAAP (Ex-99.1 & Presentaciones)
    _notify("Extrayendo y normalizando KPIs operativos Non-GAAP de 8-K / 6-K...", 55)
    print("\n[Pipeline] Extrayendo KPIs operativos y métricas Non-GAAP (Ex-99.1 y Presentaciones)...")
    try:
        extract_operational_kpis(
            ticker,
            archetype=financials.get("archetype"),
            output_dir=out_dir,
            custom_drive_path=custom_drive_path,
            filing_context=filing_context,
        )
    except Exception as exc:
        print(f"[Pipeline Warning] Extracción de KPIs operativos con observaciones: {exc}")

    # Paso C: Motor de Auditoría Contable (Post-Flight Check) + Gobernanza
    _notify("Ejecutando auditoría contable y gobernanza institucional...", 75)
    print("\n[Pipeline] Ejecutando auditoría contable de corroboración...")
    audit_results = run_full_audit(ticker, out_dir)
    analyze_governance_and_insiders(ticker, out_dir, filing_context=filing_context)

    # Paso D: Motor Cuantitativo de Scoring Fundamental (Piotroski, Mohanram, Novy-Marx, ROIC/WACC)
    _notify("Calculando modelos cuantitativos (Piotroski, Novy-Marx, WACC, Reverse DCF)...", 90)
    print("\n[Pipeline] Ejecutando motor cuantitativo de scoring fundamental...")
    fin_json = out_dir / "financial_statements.json"
    calculate_fundamental_scores(ticker, fin_json, out_dir)

    # Paso E: Sincronizar en Google Drive
    _notify("Sincronizando artefactos procesados...", 97)
    sync_to_google_drive(ticker, out_dir, custom_drive_path)

    _notify("¡Análisis completado! Entregables e interfaz web listos.", 100)
    print(f"\n{'='*70}")
    print(f"  PIPELINE COMPLETADO CON ÉXITO PARA {ticker}")
    print(f"  Dictamen de Auditoría: {audit_results.get('overall_status')} ({audit_results.get('compliance_score_pct')}%)")
    print(f"  Archivos listos en: {out_dir}")
    filing_context.print_telemetry_summary()
    print(f"{'='*70}\n")

    return out_dir


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pipeline Maestro de Extracción Fundamental")
    parser.add_argument("--ticker", required=True, help="Ticker bursátil (ej. AAPL, MSFT, MELI)")
    parser.add_argument("--drive-path", default=None, help="Ruta opcional personalizada de Google Drive")
    parser.add_argument("--out-dir", default=None, help="Ruta opcional de salida")
    args = parser.parse_args()

    run_pipeline(args.ticker, args.drive_path, args.out_dir)
