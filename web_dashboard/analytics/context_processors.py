import json
from hashlib import md5
from pathlib import Path

from django.core.cache import cache

# Caché en memoria de la lista de empresas del menú.
# La clave incorpora los mtimes de los artefactos, por lo que cualquier
# re-procesado en disco invalida automáticamente el resultado cacheado.
DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "processed"
NAV_CACHE_KEY = "nav_companies"
NAV_CACHE_TTL = 3600


def _dir_signature(entries):
    parts = []
    for d, scores_file, fin_file in entries:
        src = scores_file if scores_file.exists() else fin_file
        try:
            st = src.stat()
            parts.append(f"{d.name}:{st.st_mtime_ns}:{st.st_size}")
        except OSError:
            parts.append(f"{d.name}:missing")
    return "|".join(parts)


def nav_companies(request):
    """
    Context processor universal que provee la lista dinámica de empresas
    analizadas con datos procesados válidos a todas las plantillas.
    """
    companies = []
    entries = []
    if DATA_DIR.exists():
        for d in sorted(DATA_DIR.iterdir(), key=lambda x: x.name):
            if d.is_dir() and not d.name.startswith("-") and not d.name.startswith("."):
                scores_file = d / "fundamental_scores.json"
                fin_file = d / "financial_statements.json"
                if scores_file.exists() or fin_file.exists():
                    entries.append((d, scores_file, fin_file))

    signature = _dir_signature(entries)
    cache_key = f"{NAV_CACHE_KEY}:{md5(signature.encode('utf-8')).hexdigest()}"
    cached = cache.get(cache_key)
    if cached is not None:
        return {"nav_companies": cached}

    for d, scores_file, _ in entries:
        ticker = d.name.upper()
        name = ticker
        if scores_file.exists():
            try:
                with open(scores_file, "r", encoding="utf-8") as f:
                    sc = json.load(f)
                    name = sc.get("company_name", ticker)
            except (OSError, json.JSONDecodeError) as exc:
                print(f"[NavCompanies] Aviso leyendo {scores_file}: {exc}")
        companies.append({
            "ticker": ticker,
            "name": name,
        })
    cache.set(cache_key, companies, NAV_CACHE_TTL)
    return {"nav_companies": companies}
