"""
tests/test_config_and_pipeline_runner.py - Pruebas de Capa 0 (Configuración, Rutas y Orquestador Unificado).

Verifica:
1. Invariancia absoluta respecto al CWD (ejecutar desde web_dashboard/ apunta siempre a PROJECT_ROOT).
2. Fuente única de verdad en pipeline/config_loader.py y sec_freshness.py.
3. Unificación CLI/Web entre fundamental_pipeline.run_pipeline y analytics.pipeline_runner.
4. Ausencia de scripts/carpetas obsoletas (earnings_call_extractor, doc_parser, web_dashboard/data).
5. Resiliencia en search_companies (urllib.parse) y caché corrupto en pipeline_runner.
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PIPELINE_DIR = PROJECT_ROOT / "pipeline"
WEB_DIR = PROJECT_ROOT / "web_dashboard"

for p in (PROJECT_ROOT, PIPELINE_DIR, WEB_DIR):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "web_dashboard.settings")

from pipeline.config_loader import (
    CONFIG_DIR,
    DATA_CACHE_DIR,
    DATA_PROCESSED_DIR,
    DRIVE_INPUT_DIR,
    get_sec_headers,
    load_sec_config,
    resolve_market_cache_path,
    resolve_output_dir,
)
from pipeline.market_data_provider import MarketDataExtractor
from pipeline.sec_modules.sec_freshness import get_local_sec_metadata
from pipeline import fundamental_pipeline
import django

django.setup()
from analytics import pipeline_runner


class TestCapa0ConfigAndPaths(unittest.TestCase):

    def test_01_paths_invariant_to_cwd(self):
        """Cambiar CWD a web_dashboard/ o /tmp no altera rutas de config, caché ni data/processed."""
        orig_cwd = os.getcwd()
        try:
            os.chdir(WEB_DIR)
            cfg = load_sec_config()
            self.assertIn("sec_identity", cfg)
            self.assertEqual(resolve_output_dir("UBER"), (DATA_PROCESSED_DIR / "UBER").resolve())
            self.assertEqual(MarketDataExtractor.CACHE_FILE.resolve(), (DATA_CACHE_DIR / "market_data_cache.json").resolve())
            self.assertEqual(resolve_market_cache_path().resolve(), (DATA_CACHE_DIR / "market_data_cache.json").resolve())
            self.assertEqual(DRIVE_INPUT_DIR.resolve(), (PROJECT_ROOT / "drive_input").resolve())
            self.assertEqual(CONFIG_DIR.resolve(), (PROJECT_ROOT / "config").resolve())

            meta = get_local_sec_metadata("AAPL")
            self.assertTrue(meta["has_local_data"])
        finally:
            os.chdir(orig_cwd)

    def test_02_obsolete_artifacts_removed(self):
        """Confirma eliminación de módulos de llamadas/docx, huérfanos Capa 2 y carpeta residual web_dashboard/data."""
        self.assertFalse((PIPELINE_DIR / "earnings_call_extractor.py").exists())
        self.assertFalse((PIPELINE_DIR / "doc_parser.py").exists())
        self.assertFalse((PIPELINE_DIR / "cross_verifier.py").exists())
        self.assertFalse((PIPELINE_DIR / "run_scoring.py").exists())
        self.assertFalse((WEB_DIR / "data").exists())

    def test_03_load_sec_config_corrupt_json_fallback(self):
        """Si un sec_config.json está corrupto, no silencia excepción fatal y retorna defaults seguros."""
        with tempfile.TemporaryDirectory() as tmpdir:
            bad_cfg = Path(tmpdir) / "bad_sec_config.json"
            bad_cfg.write_text("{corrupt json", encoding="utf-8")
            cfg = load_sec_config(config_path=bad_cfg)
            self.assertIn("sec_identity", cfg)
            self.assertIn("@", cfg["sec_identity"])
            headers = get_sec_headers(config_path=bad_cfg)
            self.assertIn("User-Agent", headers)


class TestCapa0UnifiedOrchestrator(unittest.TestCase):

    def test_04_run_pipeline_emits_progress_and_uses_shared_context(self):
        """run_pipeline usa SharedFilingContext, omite earnings_call/doc_parser y reporta hitos."""
        events = []

        def _cb(msg, pct):
            events.append((pct, msg))

        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = Path(tmpdir) / "TESTCO"
            with (
                patch.object(fundamental_pipeline, "pre_flight_checks"),
                patch.object(fundamental_pipeline, "SharedFilingContext") as mock_ctx_cls,
                patch.object(fundamental_pipeline, "extract_sec_data", return_value=({"archetype": "STANDARD_CORPORATE"}, {})) as mock_sec,
                patch.object(fundamental_pipeline, "extract_operational_kpis") as mock_kpi,
                patch.object(fundamental_pipeline, "run_full_audit", return_value={"overall_status": "PASS", "compliance_score_pct": 100.0}) as mock_audit,
                patch.object(fundamental_pipeline, "analyze_governance_and_insiders") as mock_gov,
                patch.object(fundamental_pipeline, "calculate_fundamental_scores") as mock_score,
                patch.object(fundamental_pipeline, "sync_to_google_drive") as mock_sync,
            ):
                res_dir = fundamental_pipeline.run_pipeline(
                    "testco",
                    custom_drive_path=tmpdir,
                    custom_output_dir=out_dir,
                    progress_callback=_cb,
                )

        self.assertEqual(res_dir, out_dir)
        mock_ctx_cls.assert_called_once_with("TESTCO")
        ctx_instance = mock_ctx_cls.return_value
        mock_sec.assert_called_once()
        self.assertIs(mock_sec.call_args.kwargs["filing_context"], ctx_instance)
        mock_kpi.assert_called_once()
        mock_audit.assert_called_once_with("TESTCO", out_dir)
        mock_gov.assert_called_once_with("TESTCO", out_dir, filing_context=ctx_instance)
        mock_score.assert_called_once()
        mock_sync.assert_called_once()
        self.assertEqual(events[0][0], 10)
        self.assertEqual(events[-1][0], 100)

    def test_05_pipeline_runner_worker_delegates_to_run_pipeline(self):
        """_execute_pipeline_worker delega a run_pipeline y actualiza _ACTIVE_JOBS hasta COMPLETED."""
        t = "MOCK_RUN"
        with pipeline_runner._JOBS_LOCK:
            pipeline_runner._ACTIVE_JOBS[t] = {
                "ticker": t,
                "status": "RUNNING",
                "progress_pct": 5,
                "step": "Init",
                "completed": False,
                "error": None,
            }
        try:
            def fake_run_pipeline(ticker, custom_output_dir=None, progress_callback=None):
                if progress_callback:
                    progress_callback("Paso intermedio", 55)
                return custom_output_dir

            with patch.object(fundamental_pipeline, "run_pipeline", side_effect=fake_run_pipeline) as mock_rp:
                pipeline_runner._execute_pipeline_worker(t)

            mock_rp.assert_called_once()
            status = pipeline_runner.get_job_status(t)
            self.assertEqual(status["status"], "COMPLETED")
            self.assertEqual(status["progress_pct"], 100)
            self.assertTrue(status["completed"])
            self.assertFalse((WEB_DIR / "data").exists())
        finally:
            with pipeline_runner._JOBS_LOCK:
                pipeline_runner._ACTIVE_JOBS.pop(t, None)

    def test_06_search_companies_urllib_parse_and_corrupt_cache(self):
        """search_companies usa urllib.parse sin errores y tolera caché corrupto."""
        fake_yahoo_resp = MagicMock()
        fake_yahoo_resp.read.return_value = json.dumps({
            "quotes": [{"symbol": "MSFT", "shortname": "Microsoft Corp", "quoteType": "EQUITY"}]
        }).encode("utf-8")
        fake_yahoo_resp.__enter__.return_value = fake_yahoo_resp
        fake_yahoo_resp.__exit__.return_value = False

        with (
            patch.object(pipeline_runner, "_load_or_fetch_sec_tickers", return_value={}),
            patch("urllib.request.urlopen", return_value=fake_yahoo_resp),
        ):
            res = pipeline_runner.search_companies("micro soft", limit=4)

        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["ticker"], "MSFT")

        # Verificar fallback seguro ante caché SEC corrupto si falla descarga
        with tempfile.TemporaryDirectory() as tmpdir:
            bad_cache = Path(tmpdir) / "sec_company_tickers.json"
            bad_cache.write_text("{corrupt", encoding="utf-8")
            with (
                patch.object(pipeline_runner, "CACHE_DIR", Path(tmpdir)),
                patch.object(pipeline_runner, "SEC_TICKERS_CACHE", bad_cache),
                patch("urllib.request.urlopen", side_effect=OSError("offline")),
            ):
                tickers_data = pipeline_runner._load_or_fetch_sec_tickers()
                self.assertEqual(tickers_data, {})


if __name__ == "__main__":
    unittest.main()
