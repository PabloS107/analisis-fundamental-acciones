"""
pipeline_runner.py - Servicio de Ejecución y Monitoreo Asíncrono del Pipeline Universal.

Permite:
1. Buscar y resolver empresas por Ticker, CIK o Nombre (ej. 'google' -> GOOGL, Alphabet Inc.).
2. Iniciar el pipeline universal en un hilo desacoplado (Background Thread) delegando a run_pipeline.
3. Monitorear el progreso en tiempo real con hitos porcentuales y logs estructurados.
4. Prevenir ejecuciones duplicadas simultáneas sobre el mismo ticker.
"""

import sys
import time
import json
import threading
import urllib.parse
import urllib.request
import urllib.error
from pathlib import Path
from typing import Dict, Any, List

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
PIPELINE_DIR = PROJECT_ROOT / "pipeline"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(PIPELINE_DIR))

try:
    from pipeline.json_io import atomic_json_write
    from pipeline.config_loader import (
        DATA_CACHE_DIR,
        DATA_PROCESSED_DIR,
        get_sec_headers as _shared_sec_headers,
    )
except ImportError:
    from json_io import atomic_json_write
    from config_loader import (
        DATA_CACHE_DIR,
        DATA_PROCESSED_DIR,
        get_sec_headers as _shared_sec_headers,
    )

CACHE_DIR = DATA_CACHE_DIR
SEC_TICKERS_CACHE = CACHE_DIR / "sec_company_tickers.json"

# Estado en memoria de tareas de ejecución {ticker: status_dict}
_ACTIVE_JOBS: Dict[str, Dict[str, Any]] = {}
_JOBS_LOCK = threading.Lock()


def get_sec_headers() -> Dict[str, str]:
    """Retorna encabezados SEC EDGAR desde la configuración centralizada."""
    return _shared_sec_headers()


def _load_or_fetch_sec_tickers() -> Dict[str, Dict[str, Any]]:
    """Carga o descarga el directorio canónico de tickers de la SEC (~10k empresas)."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    if SEC_TICKERS_CACHE.exists():
        try:
            # Reutilizar caché si tiene menos de 7 días
            if (time.time() - SEC_TICKERS_CACHE.stat().st_mtime) < (7 * 86400):
                with open(SEC_TICKERS_CACHE, "r", encoding="utf-8") as f:
                    return json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            print(f"[PipelineRunner] Aviso leyendo caché SEC tickers: {exc}")

    try:
        req = urllib.request.Request("https://www.sec.gov/files/company_tickers.json", headers=get_sec_headers())
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            atomic_json_write(SEC_TICKERS_CACHE, data, indent=2)
            return data
    except Exception as e:
        print(f"[PipelineRunner] Aviso al descargar company_tickers de SEC: {e}")
        if SEC_TICKERS_CACHE.exists():
            try:
                with open(SEC_TICKERS_CACHE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (OSError, json.JSONDecodeError) as cache_exc:
                print(f"[PipelineRunner] Aviso caché SEC corrupto ({SEC_TICKERS_CACHE}): {cache_exc}")
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
        except (urllib.error.URLError, json.JSONDecodeError, OSError) as exc:
            print(f"[PipelineRunner] Aviso en búsqueda Yahoo ({q}): {exc}")

    return results[:limit]


def get_job_status(ticker: str) -> Dict[str, Any]:
    """Obtiene el estado de ejecución en tiempo real para un ticker dado."""
    t = ticker.strip().upper()
    with _JOBS_LOCK:
        if t in _ACTIVE_JOBS:
            return dict(_ACTIVE_JOBS[t])

    # Comprobar si ya existe analizada en disco
    proc_dir = DATA_PROCESSED_DIR / t
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
    """Hilo trabajador que delega al orquestador unificado run_pipeline con telemetría."""
    t = ticker.strip().upper()
    try:
        def update_step(step_desc: str, pct: int):
            with _JOBS_LOCK:
                if t in _ACTIVE_JOBS:
                    _ACTIVE_JOBS[t]["step"] = step_desc
                    _ACTIVE_JOBS[t]["progress_pct"] = pct
                    _ACTIVE_JOBS[t]["updated_at"] = time.time()
            print(f"[PipelineRunner] [{t}] ({pct}%) -> {step_desc}")

        from pipeline.fundamental_pipeline import run_pipeline

        out_dir = DATA_PROCESSED_DIR / t
        run_pipeline(t, custom_output_dir=out_dir, progress_callback=update_step)

        with _JOBS_LOCK:
            if t in _ACTIVE_JOBS:
                _ACTIVE_JOBS[t]["status"] = "COMPLETED"
                _ACTIVE_JOBS[t]["progress_pct"] = 100
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
            return dict(current_job)

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
        snapshot = dict(new_job)

    worker = threading.Thread(target=_execute_pipeline_worker, args=(t,), daemon=True)
    worker.start()
    return snapshot
