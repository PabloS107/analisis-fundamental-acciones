#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
sync_to_drive.py - Utilidad de sincronización automática de código a Google Drive.

Replicación limpia del código fuente hacia la unidad sincronizada de Google Drive
(ej. G:\Mi unidad\analisis fundamental\codigo_analisis_fundamental) para auditoría
e inspección remota en tiempo real.
"""

import sys
import os
import shutil
from pathlib import Path

# Directorios del proyecto que deben replicarse
SYNC_DIRS = [
    "pipeline",
    "web_dashboard",
    "config",
    "tests",
    "docs",
]

# Archivos en la raíz del proyecto que deben copiarse
ROOT_FILES = [
    "requirements.txt",
    "pyproject.toml",
    "README.md",
    "Iniciar_Dashboard_Web.bat",
    "AGENTS.md",
    ".gitignore",
]

# Nombres de directorios a ignorar estrictamente
EXCLUDED_DIR_NAMES = {
    "__pycache__",
    ".venv",
    "venv",
    "env",
    ".env",
    ".git",
    ".pytest_cache",
    ".idea",
    ".vscode",
    "cache",
    ".system_generated",
}

# Extensiones de archivos a ignorar estrictamente
EXCLUDED_EXTS = {
    ".pyc",
    ".pyo",
    ".pyd",
    ".sqlite3",
    ".db",
    ".tmp",
    ".lock",
}

# Nombres exactos de archivos a ignorar
EXCLUDED_FILENAMES = {
    ".DS_Store",
    "desktop.ini",
    "Thumbs.db",
}


_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from pipeline.config_loader import DEFAULT_DRIVE_BASE_PATH, load_sec_config


def get_drive_destination(source_root: Path) -> Path:
    """Determina la ruta de destino en Google Drive usando config_loader (SSOT)."""
    cfg = load_sec_config(source_root / "config" / "sec_config.json")
    drive_base = cfg.get("google_drive_base_path") or DEFAULT_DRIVE_BASE_PATH
    return Path(drive_base) / "codigo_analisis_fundamental"


def should_exclude(rel_path: Path) -> bool:
    """Verifica si un archivo o carpeta debe excluirse según las reglas de limpieza."""
    parts = set(rel_path.parts)
    if parts.intersection(EXCLUDED_DIR_NAMES):
        return True

    filename = rel_path.name
    if filename in EXCLUDED_FILENAMES:
        return True

    suffix = rel_path.suffix.lower()
    if suffix in EXCLUDED_EXTS:
        return True

    return False


def sync_project_to_drive():
    """Ejecuta la sincronización limpia del código hacia Google Drive."""
    source_root = Path(__file__).resolve().parent.parent.parent
    dest_root = get_drive_destination(source_root)

    print("=" * 70)
    print("  SINCRONIZADOR UNIVERSAL DE CÓDIGO FUENTE A GOOGLE DRIVE")
    print("=" * 70)
    print(f"  -> Origen  : {source_root}")
    print(f"  -> Destino : {dest_root}")
    print("-" * 70)

    # Validar que la unidad destino exista o sea accesible
    dest_parent = dest_root.parent
    if not dest_parent.exists():
        print(f"[ERROR CRÍTICO] La ruta base de Google Drive no está disponible:")
        print(f"  {dest_parent}")
        print("Asegúrate de que Google Drive para escritorio esté iniciado y la unidad G: montada.")
        sys.exit(1)

    dest_root.mkdir(parents=True, exist_ok=True)

    copied_count = 0
    updated_count = 0
    skipped_count = 0
    errors_count = 0

    # 1. Sincronizar carpetas especificadas
    for folder_name in SYNC_DIRS:
        folder_src = source_root / folder_name
        if not folder_src.exists():
            continue

        print(f"[Sincronizando carpeta] {folder_name}/ ...")
        for root, dirs, files in os.walk(folder_src):
            # Modificar dirs in-place para que os.walk no entre en carpetas excluidas
            dirs[:] = [d for d in dirs if d not in EXCLUDED_DIR_NAMES]

            for file_name in files:
                src_file = Path(root) / file_name
                rel_path = src_file.relative_to(source_root)

                if should_exclude(rel_path):
                    skipped_count += 1
                    continue

                dest_file = dest_root / rel_path
                try:
                    dest_file.parent.mkdir(parents=True, exist_ok=True)
                    # Comprobar si existe y tiene mismo tamaño y mtime para estadísticas
                    is_new = not dest_file.exists()
                    shutil.copy2(src_file, dest_file)
                    if is_new:
                        copied_count += 1
                    else:
                        updated_count += 1
                except Exception as err:
                    print(f"  [Error copiando {rel_path}]: {err}")
                    errors_count += 1

    # 2. Sincronizar archivos raíz
    print("[Sincronizando archivos raíz] ...")
    for file_name in ROOT_FILES:
        src_file = source_root / file_name
        if not src_file.exists():
            continue

        rel_path = Path(file_name)
        if should_exclude(rel_path):
            skipped_count += 1
            continue

        dest_file = dest_root / rel_path
        try:
            dest_file.parent.mkdir(parents=True, exist_ok=True)
            is_new = not dest_file.exists()
            shutil.copy2(src_file, dest_file)
            if is_new:
                copied_count += 1
            else:
                updated_count += 1
        except Exception as err:
            print(f"  [Error copiando archivo raíz {file_name}]: {err}")
            errors_count += 1

    total_synced = copied_count + updated_count

    print("-" * 70)
    print("  RESUMEN DE SINCRONIZACIÓN A GOOGLE DRIVE:")
    print(f"  - Archivos nuevos creados   : {copied_count}")
    print(f"  - Archivos actualizados     : {updated_count}")
    print(f"  - Total archivos sincronizados: {total_synced}")
    print(f"  - Archivos/Rutas omitidas  : {skipped_count} (exclusiones de limpieza)")
    print(f"  - Errores detectados        : {errors_count}")
    print("=" * 70)

    if errors_count == 0:
        print("[EXITO] Sincronización completada exitosamente en:")
        print(f"   {dest_root}")
    else:
        print(f"[AVISO] Sincronización finalizada con {errors_count} advertencias/errores.")


if __name__ == "__main__":
    sync_project_to_drive()
