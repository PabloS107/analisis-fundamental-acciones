"""
drive_manager.py - Gestor Centralizado de Rutas y Sincronizacion con Google Drive.
Proporciona:
1. Resolucion jerarquica de rutas con compatibilidad multiplataforma (Windows, macOS, Linux).
2. Sincronizacion resiliente con reintentos y retroceso exponencial ante bloqueos (PermissionError/OSError).
3. Deteccion automatica de carpetas por ticker y subcarpetas 'processed'.
"""

import os
import sys
import time
import json
import shutil
from pathlib import Path
from typing import Optional, Union, List


def load_sec_config() -> dict:
    """Carga la configuracion con la ruta base de Google Drive buscando en varias ubicaciones relativas."""
    possible_paths = [
        Path("config/sec_config.json"),
        Path(__file__).resolve().parents[4] / "config" / "sec_config.json",
        Path(__file__).resolve().parents[3] / "config" / "sec_config.json",
        Path(__file__).resolve().parent.parent / "config" / "sec_config.json",
    ]
    for p in possible_paths:
        try:
            if p.exists():
                with open(p, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            continue
    return {
        "google_drive_base_path": "G:\\Mi unidad\\analisis fundamental",
        "local_output_path": "data\\processed"
    }


def _auto_detect_system_drive_path() -> Optional[Path]:
    """
    Intenta auto-detectar la carpeta de Google Drive segun el sistema operativo (Windows, macOS, Linux).
    """
    subfolder_candidates = ["analisis fundamental", "Analisis fundamental", ""]

    if sys.platform == "win32":
        drive_letters = ["G", "H", "I", "D", "E", "F", "C"]
        drive_names = ["Mi unidad", "My Drive"]
        for letter in drive_letters:
            for d_name in drive_names:
                candidate_root = Path(f"{letter}:/{d_name}")
                if candidate_root.exists():
                    for sub in subfolder_candidates:
                        p = candidate_root / sub if sub else candidate_root
                        if p.exists():
                            return p

    elif sys.platform == "darwin":
        home = Path.home()
        cloud_storage = home / "Library" / "CloudStorage"
        if cloud_storage.exists():
            for entry in cloud_storage.iterdir():
                if "GoogleDrive" in entry.name:
                    for d_name in ["Mi unidad", "My Drive"]:
                        candidate_root = entry / d_name
                        if candidate_root.exists():
                            for sub in subfolder_candidates:
                                p = candidate_root / sub if sub else candidate_root
                                if p.exists():
                                    return p

        volumes = Path("/Volumes")
        if volumes.exists():
            for entry in volumes.iterdir():
                if "GoogleDrive" in entry.name:
                    for d_name in ["Mi unidad", "My Drive"]:
                        candidate_root = entry / d_name
                        if candidate_root.exists():
                            for sub in subfolder_candidates:
                                p = candidate_root / sub if sub else candidate_root
                                if p.exists():
                                    return p

    elif sys.platform.startswith("linux"):
        home = Path.home()
        for base in [home / "GoogleDrive", home / "drive", home / "googledrive"]:
            for d_name in ["Mi unidad", "My Drive", ""]:
                candidate_root = base / d_name if d_name else base
                if candidate_root.exists():
                    for sub in subfolder_candidates:
                        p = candidate_root / sub if sub else candidate_root
                        if p.exists():
                            return p

    return None


def resolve_google_drive_path(custom_path: Optional[Union[str, Path]] = None) -> Path:
    """
    Resuelve la ruta base de Google Drive con orden de precedencia estricto:
    1. custom_path explicito (ej. argumento CLI --drive-path)
    2. Variable de entorno GOOGLE_DRIVE_PATH o GOOGLE_DRIVE_BASE_PATH
    3. config/sec_config.json ("google_drive_base_path")
    4. Auto-deteccion por sistema operativo (sys.platform)
    5. Fallback a directorio local 'drive_input'
    """
    # 1. Argumento explicito
    if custom_path:
        return Path(custom_path)

    # 2. Variable de entorno
    env_path = os.environ.get("GOOGLE_DRIVE_PATH") or os.environ.get("GOOGLE_DRIVE_BASE_PATH")
    if env_path:
        return Path(env_path)

    # 3. Archivo de configuracion
    cfg = load_sec_config()
    cfg_drive = cfg.get("google_drive_base_path")
    if cfg_drive:
        p = Path(cfg_drive)
        if p.exists():
            return p

    # 4. Auto-deteccion por sistema operativo
    detected = _auto_detect_system_drive_path()
    if detected is not None and detected.exists():
        return detected

    if cfg_drive:
        p = Path(cfg_drive)
        if sys.platform != "win32" and ":" in cfg_drive:
            return Path("drive_input")
        return p

    # 5. Fallback local por defecto
    return Path("drive_input")


def find_ticker_drive_dir(ticker: str, custom_drive_path: Optional[Union[str, Path]] = None) -> Optional[Path]:
    """Localiza la carpeta del ticker en Google Drive o enlaces locales."""
    base_drive = resolve_google_drive_path(custom_drive_path)
    ticker_clean = ticker.strip()

    candidates = [
        base_drive / ticker_clean.upper(),
        base_drive / ticker_clean.lower(),
        Path("drive_input") / ticker_clean.upper(),
        Path("drive_input") / ticker_clean.lower(),
    ]

    for c in candidates:
        if c.exists() and c.is_dir():
            return c

    # Si la base de Drive existe, crear la carpeta para conveniencia
    if base_drive.exists():
        target = base_drive / ticker_clean.upper()
        try:
            target.mkdir(parents=True, exist_ok=True)
            (target / "presentations").mkdir(exist_ok=True)
            (target / "transcripts").mkdir(exist_ok=True)
            return target
        except Exception:
            pass

    return None


def get_ticker_drive_processed_dir(ticker: str, custom_drive_path: Optional[Union[str, Path]] = None) -> Optional[Path]:
    """Obtiene y asegura la existencia de la subcarpeta 'processed' del ticker en Google Drive."""
    ticker_dir = find_ticker_drive_dir(ticker, custom_drive_path)
    if ticker_dir:
        processed_dir = ticker_dir / "processed"
        try:
            processed_dir.mkdir(parents=True, exist_ok=True)
            return processed_dir
        except Exception:
            return processed_dir

    base_drive = resolve_google_drive_path(custom_drive_path)
    if base_drive.exists():
        direct_processed = base_drive / ticker.strip().upper() / "processed"
        try:
            direct_processed.mkdir(parents=True, exist_ok=True)
            return direct_processed
        except Exception:
            return direct_processed
    return None


def safe_copy_file(src: Union[str, Path], dst: Union[str, Path], max_retries: int = 4, base_delay: float = 0.5) -> bool:
    """
    Copia un archivo hacia Google Drive manejando bloqueos temporales (PermissionError / OSError)
    con reintentos y retroceso exponencial (backoff).
    """
    src_p = Path(src)
    dst_p = Path(dst)
    if not src_p.exists():
        print(f"  [AVISO] Archivo origen no existe para sincronizar: {src_p}")
        return False

    try:
        dst_p.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass

    for attempt in range(1, max_retries + 1):
        try:
            shutil.copy2(src_p, dst_p)
            return True
        except (PermissionError, OSError) as e:
            if attempt < max_retries:
                delay = base_delay * (2 ** (attempt - 1))
                time.sleep(delay)
            else:
                print(f"  [AVISO] Archivo {src_p.name} ocupado por sincronizador de Drive tras {max_retries} intentos: {e}")
                return False
        except Exception as e:
            print(f"  [AVISO] Error al copiar {src_p.name} a {dst_p}: {e}")
            return False
    return False
