"""
json_cache.py - Carga de JSON procesados con caché de Django.

La clave de caché incorpora mtime + tamaño del archivo, por lo que
cualquier cambio en disco invalida automáticamente la entrada anterior.
Se devuelve una copia profunda para que el llamador pueda mutar el
resultado sin corromper la caché.
"""

import copy
import hashlib
import json
from pathlib import Path

from django.core.cache import cache


def load_json_cached(path, timeout=3600):
    p = Path(path)
    try:
        st = p.stat()
    except OSError:
        raise FileNotFoundError(p)
    raw = f"{p}:{st.st_mtime_ns}:{st.st_size}".encode("utf-8")
    key = "processed-json:" + hashlib.md5(raw).hexdigest()
    data = cache.get(key)
    if data is None:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        cache.set(key, data, timeout)
    return copy.deepcopy(data)
