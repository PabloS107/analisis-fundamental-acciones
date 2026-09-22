"""
test_drive_manager.py - Pruebas unitarias completas para drive_manager.py.
Verifica:
1. Jerarquía de resolución de rutas de Google Drive (custom -> env var -> config -> auto-detect -> fallback local).
2. Estructura de carpetas por ticker (presentations, transcripts, processed).
3. Copia segura de archivos con reintentos exponenciales ante bloqueos por sincronización (PermissionError).
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Agregar scripts al sys.path
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / ".agents" / "skills" / "fundamental-data-extractor" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from drive_manager import (
    load_sec_config,
    resolve_google_drive_path,
    find_ticker_drive_dir,
    get_ticker_drive_processed_dir,
    safe_copy_file
)


class TestDriveManager(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_path = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_load_sec_config(self):
        """Verifica que load_sec_config cargue el archivo JSON o devuelva diccionario por defecto."""
        cfg = load_sec_config()
        self.assertIsInstance(cfg, dict)
        self.assertIn("sec_identity", cfg)

    def test_resolve_custom_path_precedence(self):
        """Argumento explícito custom_path tiene prioridad absoluta."""
        custom = self.base_path / "custom_drive"
        custom.mkdir()
        resolved = resolve_google_drive_path(custom_path=str(custom))
        self.assertEqual(resolved, custom.resolve())

    def test_resolve_env_var_precedence(self):
        """Variable de entorno GOOGLE_DRIVE_PATH tiene prioridad sobre config y autodetect."""
        env_dir = self.base_path / "env_drive"
        env_dir.mkdir()
        
        with patch.dict(os.environ, {"GOOGLE_DRIVE_PATH": str(env_dir)}, clear=False):
            resolved = resolve_google_drive_path()
            self.assertEqual(resolved, env_dir.resolve())

    def test_resolve_env_var_base_path(self):
        """Variable de entorno GOOGLE_DRIVE_BASE_PATH se reconoce si no está GOOGLE_DRIVE_PATH."""
        env_dir = self.base_path / "env_base_drive"
        env_dir.mkdir()
        
        with patch.dict(os.environ, {"GOOGLE_DRIVE_BASE_PATH": str(env_dir)}, clear=False):
            if "GOOGLE_DRIVE_PATH" in os.environ:
                del os.environ["GOOGLE_DRIVE_PATH"]
            resolved = resolve_google_drive_path()
            self.assertEqual(resolved, env_dir.resolve())

    def test_find_ticker_drive_dir_scaffolding(self):
        """Verifica que find_ticker_drive_dir cree la estructura presentations y transcripts si no existen."""
        ticker_dir = find_ticker_drive_dir("TEST_TICKER", custom_drive_path=self.base_path)
        self.assertIsNotNone(ticker_dir)
        self.assertTrue((ticker_dir / "presentations").exists())
        self.assertTrue((ticker_dir / "transcripts").exists())

    def test_get_ticker_drive_processed_dir(self):
        """Verifica que get_ticker_drive_processed_dir cree y devuelva el directorio processed."""
        proc_dir = get_ticker_drive_processed_dir("TEST_TICKER", custom_drive_path=self.base_path)
        self.assertIsNotNone(proc_dir)
        self.assertTrue(proc_dir.exists())
        self.assertEqual(proc_dir.name, "processed")

    def test_safe_copy_file_success(self):
        """Verifica que safe_copy_file copie exitosamente un archivo existente."""
        src = self.base_path / "source.txt"
        src.write_text("Hello fundamental analysis", encoding="utf-8")
        dst = self.base_path / "dest.txt"
        
        result = safe_copy_file(src, dst)
        self.assertTrue(result)
        self.assertTrue(dst.exists())
        self.assertEqual(dst.read_text(encoding="utf-8"), "Hello fundamental analysis")

    def test_safe_copy_file_nonexistent_source(self):
        """Verifica que safe_copy_file devuelva False si el archivo origen no existe."""
        src = self.base_path / "non_existent.txt"
        dst = self.base_path / "dest.txt"
        result = safe_copy_file(src, dst)
        self.assertFalse(result)

    def test_safe_copy_file_retry_on_permission_error(self):
        """Verifica que ante un PermissionError temporal de Drive, safe_copy_file reintente con éxito."""
        src = self.base_path / "locked_source.txt"
        src.write_text("Locked content", encoding="utf-8")
        dst = self.base_path / "dest_locked.txt"

        calls = []
        original_copy2 = __import__("shutil").copy2

        def mock_copy2(s, d):
            calls.append(len(calls) + 1)
            if len(calls) < 3:
                raise PermissionError("WinError 32: El archivo está siendo utilizado por otro proceso (Google Drive Sync)")
            return original_copy2(s, d)

        with patch("shutil.copy2", side_effect=mock_copy2):
            result = safe_copy_file(src, dst, max_retries=4, base_delay=0.01)
            self.assertTrue(result)
            self.assertEqual(len(calls), 3)  # Falló 2 veces, tuvo éxito al tercer intento
            self.assertTrue(dst.exists())

    def test_safe_copy_file_failure_exhausted_retries(self):
        """Verifica que si el error de permisos persiste en todos los reintentos, no lance excepción no controlada."""
        src = self.base_path / "permanent_lock.txt"
        src.write_text("Permanent lock", encoding="utf-8")
        dst = self.base_path / "dest_fail.txt"

        with patch("shutil.copy2", side_effect=PermissionError("Locked indefinitely")):
            result = safe_copy_file(src, dst, max_retries=3, base_delay=0.01)
            self.assertFalse(result)
            self.assertFalse(dst.exists())


if __name__ == "__main__":
    unittest.main()
