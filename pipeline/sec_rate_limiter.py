"""
sec_rate_limiter.py - Controlador de Tasa (Rate Limiting) y Reintentos Exponenciales para SEC EDGAR.
Cumple estrictamente la política oficial de la SEC (máximo 10 solicitudes por segundo por User-Agent).

Funcionalidades:
1. SECRateLimiter: Control preventivo de cadencia entre peticiones (pacing mínimo de 0.15s -> max 6.67 req/s).
2. sec_retry_with_backoff / sec_call_with_retry: Envoltorio resiliente con retroceso exponencial ante
   códigos HTTP 429 (Too Many Requests), TooManyRequestsError y bloqueos perimetrales temporales.
3. safe_sec_request: Cliente HTTP unificado con inyección de User-Agent, control de tasa y captura de 429.
"""

import time
import json
import random
import threading
import urllib.request
import urllib.error
from pathlib import Path
from functools import wraps

# Intentar importar excepciones de edgar si está instalado
try:
    from edgar.httprequests import TooManyRequestsError as EdgarTooManyRequestsError
except ImportError:
    try:
        from edgar.core import TooManyRequestsException as EdgarTooManyRequestsError
    except ImportError:
        class EdgarTooManyRequestsError(Exception):
            pass


class SECRateLimiter:
    """
    Controlador de cadencia (pacing) para peticiones a la SEC.
    Garantiza un intervalo mínimo configurable entre cualquier llamada consecutiva.
    """
    def __init__(self, min_interval=0.15):
        """
        :param min_interval: Pausa mínima forzada en segundos entre llamadas (0.15s = ~6.67 req/s).
                             La SEC permite hasta 10 req/s, por lo que 0.15s proporciona un 33% de margen.
        """
        self.min_interval = min_interval
        self._last_call_time = 0.0
        self._lock = threading.Lock()

    def pace(self):
        """Bloquea el hilo actual si no ha transcurrido el tiempo mínimo desde la última llamada."""
        with self._lock:
            now = time.time()
            elapsed = now - self._last_call_time
            if elapsed < self.min_interval:
                sleep_time = self.min_interval - elapsed
                time.sleep(sleep_time)
            self._last_call_time = time.time()

    def wait_if_needed(self):
        """Alias intuitivo de pace()."""
        self.pace()


# Instancia singleton predeterminada para todo el proceso
default_rate_limiter = SECRateLimiter(min_interval=0.15)


def sec_call_with_retry(fn, *args, max_retries=5, base_delay=1.0, max_delay=32.0, rate_limiter=None, **kwargs):
    """
    Ejecuta una función que interactúa con la SEC aplicando control de tasa preventivo
    y reintentos con backoff exponencial si la SEC devuelve HTTP 429 o TooManyRequestsError.
    
    :param fn: Función a invocar.
    :param max_retries: Cantidad máxima de reintentos ante error 429 o de red temporal.
    :param base_delay: Retardo inicial base en segundos ante el primer fallo 429.
    :param max_delay: Límite superior de espera entre reintentos.
    :param rate_limiter: Instancia de SECRateLimiter a utilizar (por defecto default_rate_limiter).
    """
    limiter = rate_limiter if rate_limiter is not None else default_rate_limiter
    
    for attempt in range(1, max_retries + 1):
        if limiter:
            limiter.pace()
            
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            # 1. Comprobar si es un error HTTP 429 o TooManyRequestsError
            is_429 = False
            retry_after_header = None
            
            # Caso Edgar TooManyRequestsError
            if isinstance(e, EdgarTooManyRequestsError) or type(e).__name__ in ["TooManyRequestsError", "TooManyRequestsException"]:
                is_429 = True
                retry_after_header = getattr(e, "retry_after", None)
            
            # Caso urllib.error.HTTPError
            elif isinstance(e, urllib.error.HTTPError):
                if e.code == 429:
                    is_429 = True
                    try:
                        hdr = e.headers.get("Retry-After")
                        if hdr:
                            retry_after_header = float(hdr)
                    except Exception:
                        pass
            
            # Caso requests / httpx HTTPStatusError
            elif hasattr(e, "response") and getattr(e.response, "status_code", None) == 429:
                is_429 = True
                try:
                    hdr = e.response.headers.get("Retry-After")
                    if hdr:
                        retry_after_header = float(hdr)
                except Exception:
                    pass
                    
            # Caso mensaje de error que contiene 429 o Too Many Requests
            elif "429" in str(e) or "too many requests" in str(e).lower():
                is_429 = True
                
            # Si no es un error de rate limit 429 ni un error de conexión transitorio, relanzar de inmediato
            is_transient_network = isinstance(e, (urllib.error.URLError, TimeoutError, ConnectionResetError))
            if not is_429 and not is_transient_network:
                raise e
                
            # Si se alcanzaron los reintentos máximos, relanzar la excepción original
            if attempt == max_retries:
                print(f"[SEC Rate Limiter] ERROR CRÍTICO: Reintentos agotados ({max_retries}/{max_retries}) ante límite de tasa de la SEC: {e}")
                raise e
                
            # Calcular tiempo de espera: respetar Retry-After si viene especificado, o usar backoff exponencial
            if retry_after_header and retry_after_header > 0:
                delay = float(retry_after_header)
            else:
                delay = min(max_delay, base_delay * (2 ** (attempt - 1)) + random.uniform(0.1, 0.4))
                
            print(f"[SEC Rate Limiter] Límite de tasa (HTTP 429 / Congestión) detectado en SEC EDGAR. Esperando {delay:.2f}s antes de reintentar (Intento {attempt}/{max_retries})...")
            time.sleep(delay)


def sec_retry_with_backoff(max_retries=5, base_delay=1.0, max_delay=32.0, rate_limiter=None):
    """
    Decorador para proteger funciones que interactúan con la SEC con reintentos y limitación de tasa.
    """
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            return sec_call_with_retry(
                fn, *args,
                max_retries=max_retries,
                base_delay=base_delay,
                max_delay=max_delay,
                rate_limiter=rate_limiter,
                **kwargs
            )
        return wrapper
    return decorator


def safe_sec_request(url, identity=None, timeout=15, max_retries=4, base_delay=1.0, rate_limiter=None):
    """
    Realiza una solicitud HTTP directa a las APIs REST oficiales de la SEC (data.sec.gov),
    garantizando la inclusión del User-Agent oficial, control de cadencia previo y
    reintentos automáticos con retroceso exponencial ante HTTP 429.
    
    :param url: URL a consultar en data.sec.gov
    :param identity: String User-Agent (ej. 'Nombre Inversor correo@ejemplo.com')
    :param timeout: Tiempo máximo de espera en segundos.
    :return: Diccionario con la respuesta JSON parseada o bytes/texto.
    """
    if identity is None:
        try:
            from drive_manager import load_sec_config
            cfg = load_sec_config()
            identity = cfg.get("sec_identity", "Pablo Inversiones pablo_inversiones@gmail.com")
        except Exception:
            identity = "Pablo Inversiones pablo_inversiones@gmail.com"
            
    headers = {
        "User-Agent": identity,
        "Accept-Encoding": "gzip, deflate"
    }

    def _do_request():
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            content_type = resp.headers.get("Content-Type", "")
            raw = resp.read()
            if "gzip" in resp.headers.get("Content-Encoding", "").lower():
                import gzip
                raw = gzip.decompress(raw)
            text = raw.decode("utf-8", errors="replace")
            if "json" in content_type or text.strip().startswith("{"):
                try:
                    return json.loads(text)
                except Exception:
                    return text
            return text

    return sec_call_with_retry(
        _do_request,
        max_retries=max_retries,
        base_delay=base_delay,
        rate_limiter=rate_limiter
    )
