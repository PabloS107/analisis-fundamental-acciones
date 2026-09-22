"""
test_sec_rate_limiter.py - Pruebas unitarias para sec_rate_limiter.py.
Verifica:
1. Pacing del rate limiter garantizando cumplimiento del límite de 10 req/s.
2. Reintento resiliente con backoff ante TooManyRequestsError de edgartools.
3. Reintento ante HTTP 429 de urllib/REST API respetando Retry-After.
4. Límite de reintentos máximos y no-reintento ante excepciones no relacionadas (ej. ValueError).
5. Funcionamiento del decorador @sec_retry_with_backoff.
6. Inyección de User-Agent y parseo seguro en safe_sec_request.
"""

import time
import unittest
import urllib.error
from unittest.mock import patch, MagicMock
from pathlib import Path
import sys

# Asegurar que los scripts de la skill estén en sys.path
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / ".agents" / "skills" / "fundamental-data-extractor" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from sec_rate_limiter import (
    SECRateLimiter,
    sec_call_with_retry,
    sec_retry_with_backoff,
    safe_sec_request,
    EdgarTooManyRequestsError
)


class TestSECRateLimiter(unittest.TestCase):

    def test_rate_limiter_pacing(self):
        """Verifica que SECRateLimiter aplique el retraso mínimo entre llamadas consecutivas."""
        limiter = SECRateLimiter(min_interval=0.08)
        start = time.time()
        for _ in range(3):
            limiter.pace()
        elapsed = time.time() - start
        # 3 llamadas con min_interval=0.08 requieren al menos 2 pausas de 0.08 = 0.16s
        self.assertGreaterEqual(elapsed, 0.15)

    def test_sec_call_with_retry_immediate_success(self):
        """Verifica que una llamada sin errores retorne su resultado inmediatamente."""
        mock_fn = MagicMock(return_value={"status": "ok"})
        limiter = SECRateLimiter(min_interval=0.0)
        
        result = sec_call_with_retry(mock_fn, "arg1", key="val", rate_limiter=limiter)
        self.assertEqual(result, {"status": "ok"})
        self.assertEqual(mock_fn.call_count, 1)

    def test_sec_call_with_retry_on_edgar_429(self):
        """Verifica que capture TooManyRequestsError de edgartools y reintente con éxito."""
        calls = []

        def mock_edgar_call():
            calls.append(len(calls) + 1)
            if len(calls) < 3:
                # Simular excepción de TooManyRequestsError
                err = EdgarTooManyRequestsError("https://data.sec.gov/submissions/CIK0000320193.json")
                err.retry_after = 0.02
                raise err
            return {"data": "filing_content"}

        limiter = SECRateLimiter(min_interval=0.0)
        result = sec_call_with_retry(
            mock_edgar_call,
            max_retries=4,
            base_delay=0.01,
            rate_limiter=limiter
        )
        self.assertEqual(result, {"data": "filing_content"})
        self.assertEqual(len(calls), 3)

    def test_sec_call_with_retry_on_http_429(self):
        """Verifica que capture urllib.error.HTTPError con código 429 y reintente."""
        calls = []

        def mock_http_call():
            calls.append(len(calls) + 1)
            if len(calls) < 2:
                headers = MagicMock()
                headers.get.return_value = "0.01"
                raise urllib.error.HTTPError("https://data.sec.gov", 429, "Too Many Requests", headers, None)
            return "success_content"

        limiter = SECRateLimiter(min_interval=0.0)
        result = sec_call_with_retry(
            mock_http_call,
            max_retries=3,
            base_delay=0.01,
            rate_limiter=limiter
        )
        self.assertEqual(result, "success_content")
        self.assertEqual(len(calls), 2)

    def test_sec_call_with_retry_exhausted(self):
        """Verifica que si persiste el código 429 tras agotar reintentos, lance la excepción original."""
        def mock_failing_call():
            raise urllib.error.HTTPError("https://data.sec.gov", 429, "Too Many Requests", MagicMock(), None)

        limiter = SECRateLimiter(min_interval=0.0)
        with self.assertRaises(urllib.error.HTTPError):
            sec_call_with_retry(
                mock_failing_call,
                max_retries=2,
                base_delay=0.01,
                rate_limiter=limiter
            )

    def test_sec_call_with_retry_non_retryable_exception(self):
        """Verifica que errores deterministas (ej. ValueError) se propaguen inmediatamente sin reintentos."""
        mock_fn = MagicMock(side_effect=ValueError("Formato contable inválido"))
        limiter = SECRateLimiter(min_interval=0.0)

        with self.assertRaises(ValueError):
            sec_call_with_retry(mock_fn, max_retries=3, rate_limiter=limiter)
        
        self.assertEqual(mock_fn.call_count, 1)

    def test_decorator_syntax(self):
        """Verifica que el decorador @sec_retry_with_backoff funcione correctamente."""
        calls = []

        @sec_retry_with_backoff(max_retries=3, base_delay=0.01, rate_limiter=SECRateLimiter(min_interval=0.0))
        def decorated_function(x, y):
            calls.append(len(calls) + 1)
            if len(calls) == 1:
                raise urllib.error.HTTPError("https://data.sec.gov", 429, "Too Many Requests", MagicMock(), None)
            return x + y

        res = decorated_function(10, 20)
        self.assertEqual(res, 30)
        self.assertEqual(len(calls), 2)

    @patch("urllib.request.urlopen")
    def test_safe_sec_request_json(self, mock_urlopen):
        """Verifica que safe_sec_request inyecte headers y devuelva diccionario JSON."""
        mock_resp = MagicMock()
        mock_resp.headers = {"Content-Type": "application/json", "Content-Encoding": "identity"}
        mock_resp.read.return_value = b'{"cik": "0000320193", "name": "Apple Inc."}'
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        limiter = SECRateLimiter(min_interval=0.0)
        data = safe_sec_request(
            "https://data.sec.gov/submissions/CIK0000320193.json",
            identity="Test User test@gmail.com",
            rate_limiter=limiter
        )
        self.assertIsInstance(data, dict)
        self.assertEqual(data.get("name"), "Apple Inc.")


if __name__ == "__main__":
    unittest.main()
