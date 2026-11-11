"""
config_loader.py - Fuente Única de Verdad (SSOT) para rutas del proyecto y configuración SEC.

Garantiza invariancia respecto al directorio de trabajo (CWD), evitando la creación de
carpetas residuales (ej. web_dashboard/data/) cuando Django u otros scripts arrancan
fuera de la raíz del repositorio.
"""

import json
from pathlib import Path
from typing import Any, Dict, Optional, Union

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"
DATA_DIR = PROJECT_ROOT / "data"
DATA_PROCESSED_DIR = DATA_DIR / "processed"
DATA_CACHE_DIR = DATA_DIR / "cache"
DRIVE_INPUT_DIR = PROJECT_ROOT / "drive_input"

DEFAULT_SEC_IDENTITY = "Pablo Inversiones pablo_inversiones@gmail.com"
DEFAULT_DRIVE_BASE_PATH = r"G:\Mi unidad\analisis fundamental"


def load_sec_config(config_path: Optional[Union[str, Path]] = None) -> Dict[str, Any]:
    """
    Carga config/sec_config.json desde la raíz del proyecto (o ruta explícita).
    Siempre retorna las claves mínimas requeridas sin silenciar errores de lectura.
    """
    defaults: Dict[str, Any] = {
        "sec_identity": DEFAULT_SEC_IDENTITY,
        "google_drive_base_path": DEFAULT_DRIVE_BASE_PATH,
        "local_output_path": str(DATA_PROCESSED_DIR),
        "sync_output_to_drive": True,
    }

    target = Path(config_path) if config_path else (CONFIG_DIR / "sec_config.json")
    if not target.exists():
        return defaults

    try:
        with open(target, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        if not isinstance(loaded, dict):
            print(f"[ConfigLoader] Aviso: {target} no contiene un objeto JSON válido; usando valores por defecto.")
            return defaults
        merged = {**defaults, **loaded}
        return merged
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[ConfigLoader] Aviso leyendo {target}: {exc}; usando valores por defecto.")
        return defaults


def get_sec_headers(config_path: Optional[Union[str, Path]] = None) -> Dict[str, str]:
    """Construye los encabezados HTTP estándar exigidos por SEC EDGAR."""
    cfg = load_sec_config(config_path=config_path)
    identity = cfg.get("sec_identity") or DEFAULT_SEC_IDENTITY
    return {
        "User-Agent": identity,
        "Accept-Encoding": "gzip, deflate",
    }


def resolve_local_output_base(cfg: Optional[Dict[str, Any]] = None) -> Path:
    """Resuelve la carpeta base de datos procesados anclada a PROJECT_ROOT si es relativa."""
    config = cfg if cfg is not None else load_sec_config()
    raw_out = config.get("local_output_path")
    if not raw_out:
        return DATA_PROCESSED_DIR
    p = Path(raw_out)
    if p.is_absolute():
        return p
    return (PROJECT_ROOT / p).resolve()


def resolve_output_dir(ticker: str, output_dir: Optional[Union[str, Path]] = None) -> Path:
    """Devuelve el directorio de salida para un ticker garantizando ruta consistente."""
    if output_dir is not None:
        return Path(output_dir)
    return resolve_local_output_base() / ticker.strip().upper()


def resolve_market_cache_path() -> Path:
    """Devuelve la ruta canónica única del caché de mercado (PROJECT_ROOT/data/cache/market_data_cache.json)."""
    return DATA_CACHE_DIR / "market_data_cache.json"
