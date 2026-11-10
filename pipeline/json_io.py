"""
json_io.py - Escritura atómica de archivos JSON.

Escribe primero a un archivo temporal en el mismo directorio y luego
hace os.replace() (atómico en el mismo volumen), de modo que ningún
lector (dashboard Django, verificadores) pueda observar un JSON a
medio escribir. El archivo temporal se limpia siempre.
"""

import json
import logging
import os
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)


def atomic_json_write(path, data, **dump_kwargs):
    """
    Persiste `data` como JSON en `path` de forma atómica.

    Acepta los mismos kwargs que json.dump (indent, ensure_ascii, default, ...).
    Si la escritura falla, el archivo destino queda intacto y se elimina el temporal.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f"{target.name}.tmp-{os.getpid()}-{uuid.uuid4().hex}")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, **dump_kwargs)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, target)
    except BaseException:
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError as exc:
            logger.debug("No se pudo limpiar archivo temporal %s: %s", tmp, exc)
        raise
    return target
