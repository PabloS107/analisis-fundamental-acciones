"""
fundamental_pipeline.py - Orquestador maestro para extracción de datos fundamentales.
Incluye:
- Pre-Flight Checks (Comprobaciones previas de conectividad, identidad y Drive).
- Extracción oficial SEC EDGAR (XBRL US-GAAP).
- Ingesta de documentos cualitativos desde Google Drive (Presentaciones y Transcripciones).
- Post-Flight Audit (Motor de Auditoría Contable y Sanidad).
- Generación del Dossier Ejecutivo con Certificación de Auditoría.
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
from sec_extractor import extract_sec_data, load_sec_config
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


def generate_executive_dossier_markdown(ticker, full_financials, dossier_qual, audit_results, output_path, gov_data=None, scoring_data=None):
    """Genera un informe ejecutivo consolidado en formato Markdown legible y estructurado con auditoría, gobernanza y scores fundamentales."""

    company_name = full_financials.get("company_name", ticker)
    cik = full_financials.get("cik", "N/A")
    fys = full_financials.get("fiscal_years", [])
    summary = full_financials.get("canonical_summary", {})
    ratios = full_financials.get("key_ratios", {})
    sec_narr = dossier_qual.get("sec_narratives_summary", {})
    
    lines = []
    lines.append(f"# Dossier Fundamental Ejecutivo: {company_name} ({ticker.upper()})")
    lines.append(f"\n*Generado: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')} | CIK SEC: {cik}*")
    lines.append("\n---\n")
    
    # Badge de Auditoría
    if audit_results and audit_results.get("overall_status") == "PASS":
        lines.append("> 🛡️ **ESTADO DE AUDITORÍA CONTABLE: CERTIFICADO 100% VÁLIDO**  \n"
                     f"> Todas las identidades contables (Partida Doble, Flujo de Caja y Márgenes) fueron verificadas matemáticamente sin discrepancias con la SEC.\n")
    else:
        lines.append(f"> ⚠️ **ESTADO DE AUDITORÍA: OBSERVACIONES ({audit_results.get('compliance_score_pct', 0)}% Aprobado)**\n")
        
    # 1. Tabla Resumen de Estados Contables
    lines.append("## 1. Estados Financieros Auditados (US-GAAP / SEC EDGAR)")
    lines.append("\n> **Fuente Oficial:** Formularios 10-K presentados ante la Securities and Exchange Commission (SEC).\n")
    
    header = "| Partida (en Millones USD) | " + " | ".join(fys) + " |"
    sep = "| :--- | " + " | ".join([":---:" for _ in fys]) + " |"
    lines.append(header)
    lines.append(sep)
    
    def fmt_millions(val):
        if val is None or val == "":
            return "N/D"
        try:
            num = float(val)
            return f"${num / 1_000_000:,.1f}M"
        except (ValueError, TypeError):
            return str(val)

    def fmt_pct(val):
        if val is None or val == "":
            return "N/D"
        try:
            return f"{float(val):.2f}%"
        except (ValueError, TypeError):
            return str(val)

    metrics_to_show = [
        ("Ingresos (Revenue)", "revenue"),
        ("Costo de Ventas (COGS)", "cost_of_goods_sold"),
        ("Margen Bruto (Gross Profit)", "gross_profit"),
        ("Gastos Operativos (OpEx)", "operating_expenses"),
        ("Beneficio Operativo (EBIT)", "operating_income"),
        ("Beneficio Neto (Net Income)", "net_income"),
        ("Flujo de Caja Operativo (CFO)", "cash_from_operations"),
        ("Inversión de Capital (CapEx)", "capital_expenditures"),
        ("Flujo de Caja Libre (FCF)", "free_cash_flow"),
        ("Efectivo e Inversiones Líquidas", "cash_and_equivalents"),
        ("Deuda Total", "total_debt"),
        ("Deuda Neta", "net_debt"),
        ("Patrimonio Neto (Equity)", "stockholders_equity"),
    ]
    
    for label, key in metrics_to_show:
        row_vals = [fmt_millions(summary.get(key, {}).get(fy)) for fy in fys]
        lines.append(f"| **{label}** | " + " | ".join(row_vals) + " |")
        
    lines.append("\n### Ratios de Rentabilidad y Eficiencia")
    r_header = "| Métrica / Ratio | " + " | ".join(fys) + " |"
    r_sep = "| :--- | " + " | ".join([":---:" for _ in fys]) + " |"
    lines.append(r_header)
    lines.append(r_sep)
    
    ratios_to_show = [
        ("Margen Bruto %", "gross_margin_pct"),
        ("Margen Operativo %", "operating_margin_pct"),
        ("Margen Neto %", "net_margin_pct"),
        ("Margen FCF %", "fcf_margin_pct"),
        ("Conversión FCF % (FCF / Net Income)", "fcf_conversion_pct"),
        ("Retorno sobre Patrimonio (ROE %)", "roe_pct"),
        ("Retorno sobre Activos (ROA %)", "roa_pct"),
        ("Retorno sobre Capital Tangible (ROC Greenblatt %)", "roc_greenblatt_pct"),
    ]

    roc_analysis = scoring_data.get("greenblatt_roc_analysis", {}) if scoring_data else {}
    roc_series = roc_analysis.get("annual_series", {})
    roc_ltm = roc_analysis.get("ltm", {})
    
    for label, key in ratios_to_show:
        row_vals = []
        for fy in fys:
            v = ratios.get(key, {}).get(fy)
            if v is None and key == "roc_greenblatt_pct":
                if fy == "LTM":
                    v = roc_ltm.get("roc_pct") if roc_ltm.get("roc_pct") is not None else ((roc_ltm.get("roc_avg") or roc_ltm.get("roc_ltm", 0)) * 100 if (roc_ltm.get("roc_avg") or roc_ltm.get("roc_ltm")) else None)
                else:
                    g_res = roc_series.get(fy, {})
                    v = g_res.get("roc_pct") if g_res.get("roc_pct") is not None else (g_res.get("roc_avg", 0) * 100 if g_res.get("roc_avg") else None)
            row_vals.append(fmt_pct(v))
        lines.append(f"| **{label}** | " + " | ".join(row_vals) + " |")
        
    # 2. Resumen Cualitativo SEC 10-K
    lines.append("\n---\n")
    lines.append("## 2. Análisis del Negocio y Modelo Operativo (Item 1 del 10-K)")
    item1 = sec_narr.get("item_1_business_summary", "")
    if item1:
        lines.append(f"\n{item1[:1200]}...\n")
    else:
        lines.append("\n*Información de Item 1 pendiente de extracción.*\n")
        
    lines.append("## 3. Factores de Riesgo Críticos (Item 1A del 10-K)")
    item1a = sec_narr.get("item_1a_risks_summary", "")
    if item1a:
        lines.append(f"\n{item1a[:1200]}...\n")
    else:
        lines.append("\n*Información de Item 1A pendiente de extracción.*\n")
        
    lines.append("## 4. Discusión de la Dirección y Márgenes (Item 7 MD&A)")
    item7 = sec_narr.get("item_7_mda_summary", "")
    if item7:
        lines.append(f"\n{item7[:1200]}...\n")
    else:
        lines.append("\n*Información de Item 7 pendiente de extracción.*\n")
        
    # 3. Documentos de Google Drive
    lines.append("## 5. Información de Google Drive (Presentaciones y Transcripciones)")
    presentations = dossier_qual.get("presentations_found", [])
    transcripts = dossier_qual.get("transcripts_found", [])
    
    if presentations:
        lines.append(f"\n### Presentaciones a Inversores Procesadas ({len(presentations)} encontradas)")
        for p in presentations:
            lines.append(f"- **Archivo:** `{p['filename']}` ({p['total_slides']} diapositivas)")
            guidance = p.get("guidance_kpi_extracted", [])
            if guidance:
                lines.append("  - **Puntos clave de Guidance / Metas:**")
                for g in guidance[:5]:
                    lines.append(f"    - *{g}*")
    else:
        lines.append("\n*No se encontraron presentaciones PDF en la carpeta de Google Drive aún.*")
        
    if transcripts:
        lines.append(f"\n### Transcripciones de Earnings Calls ({len(transcripts)} encontradas)")
        for t in transcripts:
            lines.append(f"- **Archivo:** `{t['filename']}`")
            parsed = t.get("parsed_transcript", {})
            if parsed.get("qa_highlights"):
                lines.append("  - **Temas destacados en la sesión de preguntas de analistas:**")
                for qa in parsed["qa_highlights"][:3]:
                    lines.append(f"    - *{qa[:200]}...*")
    else:
        lines.append("\n*No se encontraron transcripciones en la carpeta de Google Drive aún.*")
        
    # 4. Gobernanza y Señales de Insiders (8-K, Form 4 y 144)
    if gov_data:
        scorecard = gov_data.get("scorecard", {})
        lines.append("\n---\n")
        lines.append("## 6. Gobernanza Corporativa, Sentimiento Insider y Alertas 8-K")
        lines.append(f"\n> **Dictamen de Gobernanza:** {scorecard.get('governance_rating', 'N/A')} (Puntuación: {scorecard.get('governance_score', 'N/A')}/100)  \n"
                     f"> **Sentimiento Insider:** {scorecard.get('insider_sentiment_label', 'N/A')}  \n"
                     f"> **Cumplimiento de Planes 10b5-1:** {scorecard.get('ratio_10b5_compliance_pct', 0)}% de ventas programadas de forma automática.")
        
        events_8k = gov_data.get("form_8k_events", [])
        if events_8k:
            lines.append("\n### Hechos Relevantes Recientes (Formulario 8-K)")
            for ev in events_8k[:4]:
                lines.append(f"- **{ev['filing_date']} ({', '.join(ev['items'])}):** {ev['title']}")
                lines.append(f"  - *Diagnóstico:* {ev['diagnostic']}")
                
        f4_sum = gov_data.get("form_4_insiders", {}).get("summary", {})
        if f4_sum:
            lines.append("\n### Resumen de Transacciones de Insiders (Formulario 4 y 144)")
            lines.append(f"- **Compras en Mercado Abierto (Fondos Propios):** ${f4_sum.get('total_open_market_buys_usd', 0):,.2f}")
            lines.append(f"- **Ventas Programadas (Planes Rule 10b5-1):** ${f4_sum.get('total_10b5_sales_usd', 0):,.2f}")
            lines.append(f"- **Ventas Discrecionales (Toma de Beneficios):** ${f4_sum.get('total_discretionary_sales_usd', 0):,.2f}")

    # 5. Scores Fundamentales (Piotroski & Mohanram)
    if scoring_data:
        diag = scoring_data.get("latest_diagnosis", {})
        g_roc = diag.get("greenblatt_roc", {})
        f_audit = diag.get("forensic_audit", {})
        roc_line = ""
        if g_roc:
            roc_line = f"> **ROC Greenblatt (Productividad Tangible):** {g_roc.get('roc_pct', 'N/D')}% (vs. Mediana Sector {g_roc.get('peer_median_pct', 'N/D')}%, Spread: {g_roc.get('spread_vs_peer_pct', 0):+.2f} p.p.) — {g_roc.get('rating_label', '')}  \n"

        forensic_line = ""
        if f_audit:
            forensic_line = (
                f"> **Auditoría Forense & Calidad Contable:** {f_audit.get('global_badge', 'N/A')}  \n"
                f"> - **Ratio de Devengos de Sloan:** {f_audit.get('sloan_ratio_pct', 'N/D')}% [{f_audit.get('sloan_badge', 'N/A')}]  \n"
                f"> - **Montier C-Score (0-6):** {f_audit.get('montier_score', 'N/D')}/6 [{f_audit.get('montier_badge', 'N/A')}]  \n"
                f"> - **Spreads de Divergencia:** AR vs Ventas: {f_audit.get('ar_sales_spread_pct', 'N/D')}%, Inv vs COGS: {f_audit.get('inv_cogs_spread_pct', 'N/D')}%, Activos Blandos: {f_audit.get('soft_assets_ratio_pct', 'N/D')}%  \n"
            )

        lines.append("\n---\n")
        lines.append("## 7. Diagnóstico Cuantitativo Fundamental & Auditoría Forense")
        lines.append(f"\n> **Clasificación Estratégica en Matriz:** {diag.get('badge', 'N/A')}  \n"
                     f"> **Piotroski F-Score (Solvencia Interna):** {diag.get('f_score', 0)} / 9 Puntos ({diag.get('f_rating', 'N/A')})  \n"
                     f"> **Mohanram G-Score (Ventaja Sectorial):** {diag.get('g_score', 0)} / 8 Puntos ({diag.get('g_rating', 'N/A')})  \n"
                     f"{roc_line}"
                     f"{forensic_line}"
                     f"> **Tesis Cuantitativa:** {diag.get('investment_thesis', '')}\n")

    lines.append("\n---\n")
    lines.append(f"> **Archivos generados para siguientes módulos:**\n"
                 f"> - `financial_statements.json` (Datos estructurados limpios para DCF y Múltiplos)\n"
                 f"> - `fundamental_scores.json` / `financial_scores.json` (Puntuaciones y desgloses de Piotroski, Mohanram y Auditoría Forense)\n"
                 f"> - `qualitative_dossier.json` (Dossier cualitativo de presentaciones y llamadas)\n"
                 f"> - `governance_insider_data.json` (Gobernanza, Form 4, 144 y 8-K)\n"
                 f"> - `audit_report.md` (Certificado matemático de partida doble y reconciliación)")

                 
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
        
    print(f"[Pipeline] Dossier Ejecutivo generado en: {output_path}")


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
    
    # 3. Paso A: Extracción SEC EDGAR
    financials, sec_narratives = extract_sec_data(ticker, out_dir)
    
    # 4. Paso B: Ingesta de Documentos de Google Drive
    qualitative_dossier = parse_driver_documents(ticker, custom_drive_path, out_dir)
    
    # 4b. Paso B2: Extracción Automática Universal de Conferencia de Resultados (Earnings Calls)
    print(f"\n[Pipeline] Extrayendo y estructurando conferencia de resultados (Earnings Call)...")
    try:
        ec_data = extract_and_generate_earnings_call_data(ticker, out_dir)
        print(f"[Pipeline] Conferencia de resultados integrada exitosamente.")
    except Exception as e:
        print(f"[Pipeline Warning] Extracción automática de earnings call con observaciones: {e}")
    
    # 5. Paso C: Extracción y Conciliación de KPIs Operativos y Métricas Non-GAAP (Ex-99.1 & Presentaciones)
    print(f"\n[Pipeline] Extrayendo KPIs operativos y métricas Non-GAAP (Ex-99.1 y Presentaciones)...")
    kpi_recon = extract_operational_kpis(
        ticker,
        archetype=financials.get("archetype"),
        output_dir=out_dir,
        custom_drive_path=custom_drive_path
    )
    
    # 6. Paso D: Motor de Auditoría Contable (Post-Flight Check)
    print(f"\n[Pipeline] Ejecutando auditoría contable de corroboración...")
    audit_results = run_full_audit(ticker, out_dir)
    
    # 7. Paso E: Módulo de Gobernanza, Insiders (Form 4 y 144) y Alertas 8-K
    gov_data = analyze_governance_and_insiders(ticker, out_dir)
    
    # 8. Paso F: Motor Cuantitativo de Scoring Fundamental (Piotroski & Mohanram)
    print(f"\n[Pipeline] Ejecutando motor cuantitativo de scoring fundamental (Piotroski & Mohanram)...")
    fin_json = out_dir / "financial_statements.json"
    scoring_data = calculate_fundamental_scores(ticker, fin_json, out_dir)
    
    # 9. Paso G: Generar Dossier Ejecutivo con Certificado, Gobernanza y Scores
    dossier_path = out_dir / "executive_dossier.md"
    generate_executive_dossier_markdown(ticker, financials, qualitative_dossier, audit_results, dossier_path, gov_data=gov_data, scoring_data=scoring_data)
    
    # 10. Paso H: Generar Informe Institucional Word (.docx) y Markdown (.md)
    print(f"\n[Pipeline] Generando informe institucional de investigación en Word (.docx)...")
    try:
        from generate_earnings_report import generate_full_report
        docx_res, md_res = generate_full_report(ticker)
        print(f"[Pipeline] Informe Word generado exitosamente: {docx_res.name}")
    except Exception as e:
        print(f"[Pipeline Warning] Error generando informe institucional Word: {e}")

    # 11. Paso I: Sincronizar en Google Drive
    sync_to_google_drive(ticker, out_dir, custom_drive_path)

    
    print(f"\n{'='*70}")
    print(f"  PIPELINE COMPLETADO CON ÉXITO PARA {ticker}")
    print(f"  Dictamen de Auditoría: {audit_results.get('overall_status')} ({audit_results.get('compliance_score_pct')}%)")
    print(f"  Archivos listos en: {out_dir}")
    print(f"{'='*70}\n")
    
    return out_dir


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pipeline Maestro de Extracción Fundamental")
    parser.add_argument("--ticker", required=True, help="Ticker bursátil (ej. AAPL, MSFT, MELI)")
    parser.add_argument("--drive-path", default=None, help="Ruta opcional personalizada de Google Drive")
    parser.add_argument("--out-dir", default=None, help="Ruta opcional de salida")
    args = parser.parse_args()
    
    run_pipeline(args.ticker, args.drive_path, args.out_dir)
