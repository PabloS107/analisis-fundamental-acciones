"""
health_check.py - Suite de Diagnóstico y Sanidad Automática del Sistema.
Verifica:
1. Conectividad oficial con la SEC (API y User-Agent).
2. Estado y permisos de Google Drive.
3. Integridad y estándares de todas las Skills registradas en Antigravity.
4. Auditoría contable de todas las empresas procesadas en data/processed/.
5. Generación del reporte de calidad QA_REPORT.md.
"""

import os
import sys
import json
import urllib.request
from pathlib import Path
from datetime import datetime

# UTF-8 para consola en Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Añadir scripts del pipeline al PATH para importar audit_engine
pipeline_dir = Path(__file__).resolve().parent.parent / "pipeline"
if str(pipeline_dir) not in sys.path:
    sys.path.insert(0, str(pipeline_dir))

try:
    from audit_engine import run_full_audit
except ImportError:
    run_full_audit = None

try:
    from drive_manager import resolve_google_drive_path
except ImportError:
    resolve_google_drive_path = None

try:
    from sec_rate_limiter import safe_sec_request
except ImportError:
    safe_sec_request = None


def test_sec_connectivity():
    """Comprueba la conexión con SEC EDGAR y la validez del User-Agent."""
    config_path = Path("config/sec_config.json")
    if not config_path.exists():
        return {
            "component": "SEC EDGAR API",
            "status": "FAIL",
            "message": "Archivo config/sec_config.json no encontrado."
        }
        
    with open(config_path, "r", encoding="utf-8") as f:
        cfg = json.load(f)
        
    identity = cfg.get("sec_identity", "")
    if not identity:
        return {
            "component": "SEC EDGAR API",
            "status": "FAIL",
            "message": "Identidad no configurada en sec_config.json"
        }
        
    # Test HTTP a la SEC
    url = "https://data.sec.gov/submissions/CIK0000320193.json"
    start = datetime.now()
    try:
        if safe_sec_request:
            res = safe_sec_request(url, identity=identity, timeout=10)
            elapsed_ms = int((datetime.now() - start).total_seconds() * 1000)
            if res and isinstance(res, dict):
                return {
                    "component": "SEC EDGAR API",
                    "status": "PASS",
                    "latency_ms": elapsed_ms,
                    "message": f"Conectado exitosamente con User-Agent: '{identity}' (Latencia: {elapsed_ms}ms, Rate-Limited)"
                }
        req = urllib.request.Request(url, headers={"User-Agent": identity})
        with urllib.request.urlopen(req, timeout=10) as resp:
            elapsed_ms = int((datetime.now() - start).total_seconds() * 1000)
            if resp.status == 200:
                return {
                    "component": "SEC EDGAR API",
                    "status": "PASS",
                    "latency_ms": elapsed_ms,
                    "message": f"Conectado exitosamente con User-Agent: '{identity}' (Latencia: {elapsed_ms}ms)"
                }
            else:
                return {
                    "component": "SEC EDGAR API",
                    "status": "FAIL",
                    "message": f"Código HTTP inesperado de la SEC: {resp.status}"
                }
    except Exception as e:
        return {
            "component": "SEC EDGAR API",
            "status": "FAIL",
            "message": f"Error al conectar con la SEC: {e}"
        }


def test_google_drive():
    """Comprueba el montaje, lectura y escritura de Google Drive."""
    if resolve_google_drive_path:
        base_drive = resolve_google_drive_path()
    else:
        config_path = Path("config/sec_config.json")
        base_drive = Path("G:\\Mi unidad\\analisis fundamental")
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                base_drive = Path(cfg.get("google_drive_base_path", str(base_drive)))
            
    if not base_drive or not base_drive.exists():
        return {
            "component": "Google Drive",
            "status": "FAIL",
            "message": f"Carpeta no encontrada en: {base_drive}"
        }
        
    # Test de escritura
    test_file = base_drive / ".health_check_tmp.txt"
    try:
        with open(test_file, "w", encoding="utf-8") as f:
            f.write("test_health_check")
        test_file.unlink()
        
        # Test de unión en workspace
        junction = Path("drive_input")
        junction_ok = junction.exists()
        
        return {
            "component": "Google Drive",
            "status": "PASS",
            "message": f"Unidad montada con permisos R/W en {base_drive} (Acceso directo workspace: {'OK' if junction_ok else 'No configurado'})"
        }
    except Exception as e:
        return {
            "component": "Google Drive",
            "status": "FAIL",
            "message": f"Error de permisos de escritura en Drive: {e}"
        }


def test_skills_integrity():
    """Verifica que todas las skills registradas cumplan los estándares de Antigravity."""
    skills_root = Path(".agents/skills")
    if not skills_root.exists():
        return [{
            "component": "Skills Antigravity",
            "status": "FAIL",
            "message": "Directorio .agents/skills no existe."
        }]
        
    results = []
    for skill_dir in skills_root.iterdir():
        if not skill_dir.is_dir():
            continue
            
        skill_name = skill_dir.name
        skill_md = skill_dir / "SKILL.md"
        
        if not skill_md.exists():
            results.append({
                "component": f"Skill: {skill_name}",
                "status": "FAIL",
                "message": f"Falta archivo obligatorio SKILL.md en {skill_dir}"
            })
            continue
            
        with open(skill_md, "r", encoding="utf-8") as f:
            content = f.read()
            
        has_frontmatter = content.startswith("---") and "name:" in content and "description:" in content
        pipeline_dir = Path("pipeline")
        has_scripts = (skill_dir / "scripts").exists() or (pipeline_dir.exists() and len(list(pipeline_dir.glob("*.py"))) > 0)
        
        if has_frontmatter and has_scripts:
            scripts_count = len(list(pipeline_dir.glob("*.py"))) if pipeline_dir.exists() else 0
            results.append({
                "component": f"Skill: {skill_name}",
                "status": "PASS",
                "message": f"Estándar Antigravity válido con frontmatter y scripts consolidados en pipeline/ ({scripts_count} scripts)."
            })
        else:
            issues = []
            if not has_frontmatter:
                issues.append("frontmatter YAML incompleto")
            if not has_scripts:
                issues.append("sin scripts en scripts/")
            results.append({
                "component": f"Skill: {skill_name}",
                "status": "WARNING",
                "message": f"Observaciones: {', '.join(issues)}"
            })
            
    return results


def test_processed_companies():
    """Audita contablemente todas las empresas procesadas en data/processed/."""
    processed_dir = Path("data/processed")
    if not processed_dir.exists():
        return []
        
    results = []
    for comp_dir in processed_dir.iterdir():
        if comp_dir.is_dir() and (comp_dir / "financial_statements.json").exists():
            ticker = comp_dir.name
            if run_full_audit:
                try:
                    audit = run_full_audit(ticker, comp_dir)
                    results.append({
                        "component": f"Auditoría Contable: {ticker}",
                        "status": audit["overall_status"],
                        "score_pct": audit["compliance_score_pct"],
                        "message": f"Fidelidad contable: {audit['compliance_score_pct']}% ({audit['passed_tests']} de {audit['passed_tests'] + audit['failed_tests']} pruebas superadas)"
                    })
                except Exception as e:
                    results.append({
                        "component": f"Auditoría Contable: {ticker}",
                        "status": "FAIL",
                        "message": f"Error al auditar {ticker}: {e}"
                    })
    return results


def run_system_health_check():
    """Punto de entrada de la suite de diagnóstico."""
    print(f"\n{'='*75}")
    print("  SUITE DE DIAGNÓSTICO Y CONTROL DE CALIDAD (HEALTH CHECK)")
    print(f"  Fecha: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    print(f"{'='*75}\n")
    
    checks = []
    
    # 1. SEC API
    print("[1/4] Comprobando API oficial SEC EDGAR...")
    sec_res = test_sec_connectivity()
    checks.append(sec_res)
    print(f"  [{sec_res['status']}] {sec_res['message']}")
    
    # 2. Google Drive
    print("\n[2/4] Comprobando integración de Google Drive...")
    drive_res = test_google_drive()
    checks.append(drive_res)
    print(f"  [{drive_res['status']}] {drive_res['message']}")
    
    # 3. Skills Antigravity
    print("\n[3/4] Comprobando registro e integridad de Skills...")
    skills_res = test_skills_integrity()
    for s in skills_res:
        checks.append(s)
        print(f"  [{s['status']}] {s['component']}: {s['message']}")
        
    # 4. Auditoría Contable de Empresas
    print("\n[4/4] Ejecutando auditorías contables de empresas extraídas...")
    comp_res = test_processed_companies()
    for c in comp_res:
        checks.append(c)
        print(f"  [{c['status']}] {c['component']}: {c['message']}")
        
    # Balance general
    passed = sum(1 for c in checks if c["status"] == "PASS")
    failed = sum(1 for c in checks if c["status"] == "FAIL")
    warns = sum(1 for c in checks if c["status"] == "WARNING")
    total = len(checks)
    
    print(f"\n{'-'*75}")
    print(f"  RESUMEN DE SALUD DEL SISTEMA: {'TODO OPERATIVO' if failed == 0 else 'CON FALLOS'}")
    print(f"  Pruebas Superadas: {passed} / {total} | Fallos: {failed} | Advertencias: {warns}")
    print(f"{'-'*75}\n")
    
    # Generar QA_REPORT.md
    generate_qa_report(checks, passed, failed, warns)
    return failed == 0


def generate_qa_report(checks, passed, failed, warns):
    """Genera el reporte persistente QA_REPORT.md en la raíz del proyecto."""
    lines = []
    lines.append("# Reporte de Salud y Calidad del Asistente (QA Report)")
    lines.append(f"\n*Última comprobación: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}*")
    lines.append("\n---\n")
    
    if failed == 0:
        lines.append("### 🟢 ESTADO GLOBAL: 100% OPERATIVO Y AUDITADO\n")
    else:
        lines.append(f"### 🔴 ESTADO GLOBAL: {failed} COMPONENTES REQUIEREN ATENCIÓN\n")
        
    lines.append(f"- **Total de Verificaciones:** {len(checks)}")
    lines.append(f"- **Superadas (PASS):** {passed}")
    lines.append(f"- **Fallidas (FAIL):** {failed}")
    lines.append(f"- **Advertencias (WARNING):** {warns}\n")
    
    lines.append("## Tabla de Diagnóstico de Componentes")
    lines.append("| Estado | Componente / Instrumento | Diagnóstico Detallado |")
    lines.append("| :---: | :--- | :--- |")
    
    for c in checks:
        icon = "✅" if c["status"] == "PASS" else ("❌" if c["status"] == "FAIL" else "⚠️")
        lines.append(f"| {icon} **{c['status']}** | {c['component']} | {c['message']} |")
        
    report_path = Path("QA_REPORT.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"[Health Check] Reporte guardado en: {report_path.resolve()}")


if __name__ == "__main__":
    success = run_system_health_check()
    sys.exit(0 if success else 1)
