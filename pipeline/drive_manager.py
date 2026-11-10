"""
drive_manager.py - Gestor Centralizado de Rutas y Sincronización con Google Drive.
Proporciona:
1. Resolución jerárquica de rutas con compatibilidad multiplataforma (Windows, macOS, Linux).
2. Sincronización resiliente con reintentos y retroceso exponencial ante bloqueos (PermissionError/OSError).
3. Detección automática de carpetas por ticker y subcarpetas 'presentations' y 'processed'.
"""

import logging
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Optional, Union

try:
    from config_loader import load_sec_config, DRIVE_INPUT_DIR
except ImportError:
    try:
        from .config_loader import load_sec_config, DRIVE_INPUT_DIR
    except ImportError:
        from pipeline.config_loader import load_sec_config, DRIVE_INPUT_DIR

logger = logging.getLogger(__name__)


def _auto_detect_system_drive_path() -> Optional[Path]:
    """Intenta auto-detectar la carpeta de Google Drive según el sistema operativo."""
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
    1. custom_path explícito (ej. argumento CLI --drive-path)
    2. Variable de entorno GOOGLE_DRIVE_PATH o GOOGLE_DRIVE_BASE_PATH
    3. config/sec_config.json ("google_drive_base_path")
    4. Auto-detección por sistema operativo (sys.platform)
    5. Fallback a directorio local 'drive_input'
    """
    if custom_path:
        return Path(custom_path)

    env_path = os.environ.get("GOOGLE_DRIVE_PATH") or os.environ.get("GOOGLE_DRIVE_BASE_PATH")
    if env_path:
        return Path(env_path)

    cfg = load_sec_config()
    cfg_drive = cfg.get("google_drive_base_path")
    if cfg_drive:
        p = Path(cfg_drive)
        if p.exists():
            return p

    detected = _auto_detect_system_drive_path()
    if detected is not None and detected.exists():
        return detected

    if cfg_drive:
        p = Path(cfg_drive)
        if sys.platform != "win32" and ":" in cfg_drive:
            return DRIVE_INPUT_DIR
        return p

    return DRIVE_INPUT_DIR


def find_ticker_drive_dir(ticker: str, custom_drive_path: Optional[Union[str, Path]] = None) -> Optional[Path]:
    """Localiza la carpeta del ticker en Google Drive o enlaces locales."""
    base_drive = resolve_google_drive_path(custom_drive_path)
    ticker_clean = ticker.strip()

    candidates = [
        base_drive / ticker_clean.upper(),
        base_drive / ticker_clean.lower(),
        DRIVE_INPUT_DIR / ticker_clean.upper(),
        DRIVE_INPUT_DIR / ticker_clean.lower(),
    ]

    for c in candidates:
        if c.exists() and c.is_dir():
            return c

    if base_drive.exists():
        target = base_drive / ticker_clean.upper()
        try:
            target.mkdir(parents=True, exist_ok=True)
            (target / "presentations").mkdir(exist_ok=True)
            return target
        except OSError as exc:
            print(f"[DriveManager] Aviso creando carpetas en {target}: {exc}")

    return None


def get_ticker_drive_processed_dir(ticker: str, custom_drive_path: Optional[Union[str, Path]] = None) -> Optional[Path]:
    """Obtiene y asegura la existencia de la subcarpeta 'processed' del ticker en Google Drive."""
    ticker_dir = find_ticker_drive_dir(ticker, custom_drive_path)
    if ticker_dir:
        processed_dir = ticker_dir / "processed"
        try:
            processed_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            logger.debug("No se pudo crear subcarpeta processed en %s: %s", processed_dir, exc)
        return processed_dir

    base_drive = resolve_google_drive_path(custom_drive_path)
    if base_drive.exists():
        direct_processed = base_drive / ticker.strip().upper() / "processed"
        try:
            direct_processed.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            logger.debug("No se pudo crear ruta directa processed en %s: %s", direct_processed, exc)
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
    except OSError as exc:
        print(f"  [AVISO] No se pudo preparar carpeta destino {dst_p.parent}: {exc}")

    for attempt in range(1, max_retries + 1):
        try:
            shutil.copy2(src_p, dst_p)
            return True
        except (PermissionError, OSError) as e:
            if attempt < max_retries:
                time.sleep(base_delay * (2 ** (attempt - 1)))
            else:
                print(f"  [AVISO] Archivo {src_p.name} ocupado por sincronizador de Drive tras {max_retries} intentos: {e}")
                return False
        except Exception as e:
            print(f"  [AVISO] Error al copiar {src_p.name} a {dst_p}: {e}")
            return False
    return False
