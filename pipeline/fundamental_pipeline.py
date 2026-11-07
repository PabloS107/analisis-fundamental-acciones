"""
fundamental_pipeline.py - Orquestador maestro para extracción de datos fundamentales.
Incluye:
- Pre-Flight Checks (Comprobaciones previas de conectividad, identidad y Drive).
- Extracción oficial SEC EDGAR (XBRL US-GAAP).
- Ingesta de documentos cualitativos desde Google Drive (Presentaciones y Transcripciones).
- Post-Flight Audit (Motor de Auditoría Contable y Sanidad).
- Módulo de Gobernanza y Transacciones de Insiders.
- Motor Cuantitativo de Scoring Fundamental para el Dashboard Web.
- Sincronización automática en Google Drive.
"""

import os
import sys
import shutil
import json
import argparse
from pathlib import Path
from datetime import datetime

# UTF-8 para consola en Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Importar extractores internos
from sec_extractor import extract_sec_data, load_sec_config, SharedFilingContext
from doc_parser import parse_driver_documents, find_ticker_drive_dir
from drive_manager import resolve_google_drive_path, safe_copy_file, get_ticker_drive_processed_dir
from audit_engine import run_full_audit
from governance_insider_analyzer import analyze_governance_and_insiders
from financial_scoring_engine import calculate_fundamental_scores
from kpi_extractor import extract_operational_kpis
from earnings_call_extractor import extract_and_generate_earnings_call_data


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
    local_out = Path(cfg.get("local_output_path", "data/processed"))
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


def run_pipeline(ticker, custom_drive_path=None, custom_output_dir=None):
    """Ejecuta el pipeline completo de extracción, compilación y auditoría."""
    cfg = load_sec_config()
    ticker = ticker.strip().upper()
    
    print(f"\n{'='*70}")
    print(f"  INICIANDO PIPELINE FUNDAMENTAL PARA: {ticker}")
    print(f"{'='*70}")
    
    # 1. Pre-Flight Checks
    pre_flight_checks(ticker)
    
    # 2. Definir directorio de salida local
    if custom_output_dir:
        out_dir = Path(custom_output_dir)
    else:
        out_dir = Path(cfg.get("local_output_path", "data/processed")) / ticker
    out_dir.mkdir(parents=True, exist_ok=True)
    
    # 2.5. Manifiesto Único en Memoria (SharedFilingContext)
    filing_context = SharedFilingContext(ticker)

    # 3. Paso A: Extracción SEC EDGAR
    financials, sec_narratives = extract_sec_data(ticker, out_dir, filing_context=filing_context)
    
    # 4. Paso B: Ingesta de Documentos de Google Drive
    qualitative_dossier = parse_driver_documents(ticker, custom_drive_path, out_dir)
    
    # 4b. Paso B2: Extracción Automática Universal de Conferencia de Resultados (Earnings Calls)
    print(f"\n[Pipeline] Extrayendo y estructurando conferencia de resultados (Earnings Call)...")
    try:
        ec_data = extract_and_generate_earnings_call_data(ticker, out_dir, filing_context=filing_context)
        print(f"[Pipeline] Conferencia de resultados integrada exitosamente.")
    except Exception as e:
        print(f"[Pipeline Warning] Extracción automática de earnings call con observaciones: {e}")
    
    # 5. Paso C: Extracción y Conciliación de KPIs Operativos y Métricas Non-GAAP (Ex-99.1 & Presentaciones)
    print(f"\n[Pipeline] Extrayendo KPIs operativos y métricas Non-GAAP (Ex-99.1 y Presentaciones)...")
    kpi_recon = extract_operational_kpis(
        ticker,
        archetype=financials.get("archetype"),
        output_dir=out_dir,
        custom_drive_path=custom_drive_path,
        filing_context=filing_context
    )
    
    # 6. Paso D: Motor de Auditoría Contable (Post-Flight Check)
    print(f"\n[Pipeline] Ejecutando auditoría contable de corroboración...")
    audit_results = run_full_audit(ticker, out_dir)
    
    # 7. Paso E: Módulo de Gobernanza, Insiders (Form 4 y 144) y Alertas 8-K
    gov_data = analyze_governance_and_insiders(ticker, out_dir, filing_context=filing_context)
    
    # 8. Paso F: Motor Cuantitativo de Scoring Fundamental (Piotroski & Mohanram)
    print(f"\n[Pipeline] Ejecutando motor cuantitativo de scoring fundamental (Piotroski & Mohanram)...")
    fin_json = out_dir / "financial_statements.json"
    scoring_data = calculate_fundamental_scores(ticker, fin_json, out_dir)
    
    # 9. Paso G: Sincronizar en Google Drive
    sync_to_google_drive(ticker, out_dir, custom_drive_path)

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
