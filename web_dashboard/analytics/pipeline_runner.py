"""
pipeline_runner.py - Servicio de Ejecución y Monitoreo Asíncrono del Pipeline Universal.

Permite:
1. Buscar y resolver empresas por Ticker, CIK o Nombre (ej. 'google' -> GOOGL, Alphabet Inc.).
2. Iniciar el pipeline universal en un hilo desacoplado (Background Thread).
3. Monitorear el progreso en tiempo real con hitos porcentuales y logs estructurados.
4. Prevenir ejecuciones duplicadas simultáneas sobre el mismo ticker.
"""

import sys
import time
import json
import threading
import urllib.request
import urllib.error
from pathlib import Path
from typing import Dict, Any, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
PIPELINE_DIR = PROJECT_ROOT / "pipeline"
if str(PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(PIPELINE_DIR))

CACHE_DIR = PROJECT_ROOT / "data" / "cache"
SEC_TICKERS_CACHE = CACHE_DIR / "sec_company_tickers.json"

# Estado en memoria de tareas de ejecución {ticker: status_dict}
_ACTIVE_JOBS: Dict[str, Dict[str, Any]] = {}
_JOBS_LOCK = threading.Lock()


def get_sec_headers() -> Dict[str, str]:
    cfg_p = PROJECT_ROOT / "config" / "sec_config.json"
    identity = "Pablo Inversiones pablo_inversiones@gmail.com"
    if cfg_p.exists():
        try:
            with open(cfg_p, "r", encoding="utf-8") as f:
                identity = json.load(f).get("sec_identity", identity)
        except Exception:
            pass
    return {"User-Agent": identity, "Accept-Encoding": "gzip, deflate"}


def _load_or_fetch_sec_tickers() -> Dict[str, Dict[str, Any]]:
    """Carga o descarga el directorio canónico de tickers de la SEC (~10k empresas)."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    if SEC_TICKERS_CACHE.exists():
        try:
            # Reutilizar caché si tiene menos de 7 días
            if (time.time() - SEC_TICKERS_CACHE.stat().st_mtime) < (7 * 86400):
                with open(SEC_TICKERS_CACHE, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass

    try:
        req = urllib.request.Request("https://www.sec.gov/files/company_tickers.json", headers=get_sec_headers())
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            with open(SEC_TICKERS_CACHE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            return data
    except Exception as e:
        print(f"[PipelineRunner] Aviso al descargar company_tickers de SEC: {e}")
        if SEC_TICKERS_CACHE.exists():
            with open(SEC_TICKERS_CACHE, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}


def search_companies(query: str, limit: int = 8) -> List[Dict[str, Any]]:
    """
    Busca coincidencias por ticker o nombre de empresa.
    Soporta búsqueda offline rápida en sec_company_tickers y fallback a Yahoo Search.
    """
    q = query.strip().lower()
    if not q:
        return []

    results: List[Dict[str, Any]] = []
    seen_tickers = set()

    # 1. Búsqueda local en directorio SEC
    sec_data = _load_or_fetch_sec_tickers()
    exact_matches = []
    prefix_matches = []
    contains_matches = []

    for item in sec_data.values():
        t = str(item.get("ticker", "")).upper()
        title = str(item.get("title", ""))
        cik = str(item.get("cik_str", "")).zfill(10)
        t_low = t.lower()
        title_low = title.lower()

        entry = {"ticker": t, "name": title, "cik": cik, "source": "SEC"}

        if t_low == q:
            exact_matches.append(entry)
        elif t_low.startswith(q) or title_low.startswith(q):
            prefix_matches.append(entry)
        elif q in title_low:
            contains_matches.append(entry)

    # Ordenar por relevancia
    for group in [exact_matches, prefix_matches, contains_matches]:
        for item in group:
            if item["ticker"] not in seen_tickers:
                seen_tickers.add(item["ticker"])
                results.append(item)
                if len(results) >= limit:
                    break
        if len(results) >= limit:
            break

    # 2. Si no hubo suficientes resultados, consultar Yahoo Finance Search API
    if len(results) < limit:
        try:
            y_url = f"https://query2.finance.yahoo.com/v1/finance/search?q={urllib.parse.quote(q)}"
            req = urllib.request.Request(y_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                y_data = json.loads(resp.read().decode("utf-8"))
                for quote in y_data.get("quotes", []):
                    sym = quote.get("symbol", "").upper()
                    short_name = quote.get("shortname") or quote.get("longname") or sym
                    quote_type = quote.get("quoteType", "")
                    # Priorizar acciones ordinarias o ADRs (evitar opciones o futuros)
                    if quote_type in ["EQUITY", ""] and "." not in sym and sym not in seen_tickers:
                        seen_tickers.add(sym)
                        results.append({
                            "ticker": sym,
                            "name": short_name,
                            "cik": "N/D",
                            "source": "Market"
                        })
                        if len(results) >= limit:
                            break
        except Exception:
            pass

    return results[:limit]


def get_job_status(ticker: str) -> Dict[str, Any]:
    """Obtiene el estado de ejecución en tiempo real para un ticker dado."""
    t = ticker.strip().upper()
    with _JOBS_LOCK:
        if t in _ACTIVE_JOBS:
            return dict(_ACTIVE_JOBS[t])
    
    # Comprobar si ya existe analizada en disco
    proc_dir = PROJECT_ROOT / "data" / "processed" / t
    if (proc_dir / "fundamental_scores.json").exists() and (proc_dir / "financial_statements.json").exists():
        return {
            "ticker": t,
            "status": "COMPLETED",
            "progress_pct": 100,
            "step": "Análisis finalizado y disponible en terminal.",
            "completed": True,
            "error": None
        }

    return {
        "ticker": t,
        "status": "IDLE",
        "progress_pct": 0,
        "step": "Sin ejecución activa.",
        "completed": False,
        "error": None
    }


def _execute_pipeline_worker(ticker: str):
    """Hilo trabajador que ejecuta el orquestador universal paso a paso con telemetría."""
    t = ticker.strip().upper()
    try:
        def update_step(step_desc: str, pct: int):
            with _JOBS_LOCK:
                if t in _ACTIVE_JOBS:
                    _ACTIVE_JOBS[t]["step"] = step_desc
                    _ACTIVE_JOBS[t]["progress_pct"] = pct
                    _ACTIVE_JOBS[t]["updated_at"] = time.time()
            print(f"[PipelineRunner] [{t}] ({pct}%) -> {step_desc}")

        update_step("Verificando identidad SEC e inicializando directorios...", 10)
        from fundamental_pipeline import run_pipeline
        
        update_step("Conectando con SEC EDGAR y descargando estados financieros 10-K / 10-Q...", 25)
        # Importar y configurar identidad de edgar
        from sec_extractor import extract_sec_data, load_sec_config
        from edgar import set_identity
        cfg = load_sec_config()
        set_identity(cfg.get("sec_identity", "Pablo Inversiones pablo_inversiones@gmail.com"))

        out_dir = PROJECT_ROOT / "data" / "processed" / t
        out_dir.mkdir(parents=True, exist_ok=True)
        
        financials, sec_narratives = extract_sec_data(t, out_dir)
        
        update_step("Extrayendo conferencias de resultados (Earnings Calls y Guidance)...", 45)
        try:
            from earnings_call_extractor import extract_and_generate_earnings_call_data
            extract_and_generate_earnings_call_data(t, out_dir)
        except Exception as e:
            print(f"[PipelineRunner] Earnings call warning: {e}")

        update_step("Extrayendo y normalizando KPIs operativos Non-GAAP de 8-K / 6-K...", 60)
        try:
            from kpi_extractor import extract_operational_kpis
            extract_operational_kpis(t, archetype=financials.get("archetype"), output_dir=out_dir)
        except Exception as e:
            print(f"[PipelineRunner] KPI warning: {e}")

        update_step("Ejecutando auditoría contable y gobernanza institucional...", 75)
        from audit_engine import run_full_audit
        from governance_insider_analyzer import analyze_governance_and_insiders
        run_full_audit(t, out_dir)
        analyze_governance_and_insiders(t, out_dir)

        update_step("Calculando modelos cuantitativos (Piotroski, Novy-Marx, WACC, Reverse DCF)...", 85)
        from financial_scoring_engine import calculate_fundamental_scores
        fin_json = out_dir / "financial_statements.json"
        calculate_fundamental_scores(t, fin_json, out_dir)

        update_step("Compilando informes ejecutivos Word (.docx) y Markdown (.md)...", 95)
        from generate_earnings_report import generate_full_report
        generate_full_report(t)

        update_step("¡Análisis completado! Entregables e interfaz web listos.", 100)
        with _JOBS_LOCK:
            if t in _ACTIVE_JOBS:
                _ACTIVE_JOBS[t]["status"] = "COMPLETED"
                _ACTIVE_JOBS[t]["completed"] = True
                _ACTIVE_JOBS[t]["error"] = None

    except Exception as exc:
        err_msg = str(exc)
        print(f"[PipelineRunner] ERROR CRÍTICO procesando {t}: {err_msg}")
        with _JOBS_LOCK:
            if t in _ACTIVE_JOBS:
                _ACTIVE_JOBS[t]["status"] = "FAILED"
                _ACTIVE_JOBS[t]["completed"] = True
                _ACTIVE_JOBS[t]["error"] = err_msg


def launch_pipeline_job(ticker: str) -> Dict[str, Any]:
    """Inicia la tarea del pipeline si no está ya en ejecución."""
    t = ticker.strip().upper()
    with _JOBS_LOCK:
        current_job = _ACTIVE_JOBS.get(t)
        if current_job and current_job.get("status") == "RUNNING":
            return current_job

        new_job = {
            "ticker": t,
            "status": "RUNNING",
            "progress_pct": 5,
            "step": "Iniciando proceso de análisis fundamental...",
            "completed": False,
            "error": None,
            "started_at": time.time()
        }
        _ACTIVE_JOBS[t] = new_job

    worker = threading.Thread(target=_execute_pipeline_worker, args=(t,), daemon=True)
    worker.start()
    return new_job
