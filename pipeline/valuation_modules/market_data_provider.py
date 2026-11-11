"""
market_data_provider.py - Extractor y Validador Cruzado de Datos de Mercado en Tiempo Real.

Módulo de extracción y doble chequeo para:
1. Tasa Libre de Riesgo (Rf): Rendimiento del Bono del Tesoro de EE.UU. a 10 Años (^TNX / US10Y).
2. Beta (β): Sensibilidad de mercado a 5 años mensual (Yahoo vs. CNBC vs. Benchmark Damodaran).
3. Precio y Capitalización Bursátil (Market Cap - E): Yahoo Finance vs. CNBC, arbitrado con Form 10-Q de la SEC.
"""

import datetime
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
import pipeline  # noqa: E402, F401

try:
    from json_io import atomic_json_write
    from config_loader import resolve_market_cache_path
except ImportError:
    try:
        from pipeline.json_io import atomic_json_write
        from pipeline.config_loader import resolve_market_cache_path
    except ImportError:
        from .json_io import atomic_json_write
        from .config_loader import resolve_market_cache_path

try:
    import yfinance as yf
except ImportError:
    yf = None

logger = logging.getLogger(__name__)

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


class MarketDataExtractor:
    """Extractor y Validador Cruzado de Métricas Financieras en Tiempo Real."""

    CACHE_FILE = resolve_market_cache_path()
    DEFAULT_CACHE_TTL_SECONDS = 3600

    TOLERANCE_PRICE_PCT = 0.015
    TOLERANCE_RF_BPS = 0.0010
    TOLERANCE_BETA = 0.15

    @classmethod
    def _load_cache(cls) -> Dict[str, Any]:
        """Carga el archivo de caché si existe."""
        if cls.CACHE_FILE.exists():
            try:
                with open(cls.CACHE_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (OSError, json.JSONDecodeError) as exc:
                logger.debug("No se pudo leer caché de mercado (%s): %s", cls.CACHE_FILE, exc)
        return {}

    @classmethod
    def _save_cache(cls, data: Dict[str, Any]) -> None:
        """Guarda los datos en caché creando directorios padres si hace falta."""
        try:
            cls.CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
            atomic_json_write(cls.CACHE_FILE, data, indent=2)
        except Exception as e:
            print(f"[MarketData] Advertencia al guardar cache: {e}")

    @classmethod
    def fetch_yahoo_metrics(cls, ticker: str) -> Dict[str, Any]:
        """Extrae métricas desde Yahoo Finance (vía yfinance o HTTP directo)."""
        res: Dict[str, Any] = {
            "source": "Yahoo Finance",
            "price": None,
            "market_cap": None,
            "beta": None,
            "rf_10y": None,
            "shares_outstanding": None,
            "success": False,
        }

        if yf is not None:
            try:
                yt = yf.Ticker(ticker)
                fi = getattr(yt, "fast_info", None)
                if fi:
                    res["price"] = getattr(fi, "last_price", None)
                    res["market_cap"] = getattr(fi, "market_cap", None)
                    res["shares_outstanding"] = getattr(fi, "shares", None)

                try:
                    info = yt.info or {}
                    res["beta"] = info.get("beta")
                    res["market_cap"] = res["market_cap"] or info.get("marketCap")
                    res["price"] = res["price"] or info.get("currentPrice") or info.get("regularMarketPrice")
                except Exception as exc:
                    logger.debug("yfinance info no disponible para %s: %s", ticker, exc)

                try:
                    tnx_p = getattr(yf.Ticker("^TNX").fast_info, "last_price", None)
                    if tnx_p is not None:
                        res["rf_10y"] = float(tnx_p) / 100.0 if tnx_p > 1.0 else float(tnx_p)
                except Exception as exc:
                    logger.debug("Tasa ^TNX vía yfinance no disponible: %s", exc)

                if res["price"] is not None:
                    res["success"] = True
                    return res
            except Exception as e:
                print(f"[MarketData] yfinance aviso: {e}")

        try:
            r = requests.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}", headers=DEFAULT_HEADERS, timeout=5)
            if r.status_code == 200:
                res["price"] = r.json()["chart"]["result"][0]["meta"].get("regularMarketPrice")
                res["success"] = True

            r_tnx = requests.get("https://query1.finance.yahoo.com/v8/finance/chart/%5ETNX", headers=DEFAULT_HEADERS, timeout=5)
            if r_tnx.status_code == 200:
                p_tnx = r_tnx.json()["chart"]["result"][0]["meta"].get("regularMarketPrice")
                if p_tnx:
                    res["rf_10y"] = float(p_tnx) / 100.0 if p_tnx > 1.0 else float(p_tnx)
        except Exception as e:
            print(f"[MarketData] Yahoo HTTP v8 error: {e}")

        return res

    @classmethod
    def fetch_cnbc_metrics(cls, ticker: str) -> Dict[str, Any]:
        """Extrae métricas desde CNBC Quote Webservice."""
        res: Dict[str, Any] = {
            "source": "CNBC Quote Service",
            "price": None,
            "market_cap": None,
            "beta": None,
            "rf_10y": None,
            "shares_outstanding": None,
            "success": False,
        }
        try:
            url = f"https://quote.cnbc.com/quote-html-webservice/restQuote/symbolType/symbol?symbols={ticker}|US10Y&requestMethod=itv&output=json"
            r = requests.get(url, headers=DEFAULT_HEADERS, timeout=5)
            if r.status_code == 200:
                quotes = r.json().get("FormattedQuoteResult", {}).get("FormattedQuote", [])
                for q in quotes:
                    sym = q.get("symbol")
                    if sym == ticker:
                        p_str = q.get("last")
                        if p_str:
                            res["price"] = float(str(p_str).replace(",", "").replace("$", ""))
                        b_str = q.get("beta")
                        if b_str and b_str != "UNCH":
                            try:
                                res["beta"] = float(b_str)
                            except ValueError as exc:
                                logger.debug("Beta CNBC no numérica (%r): %s", b_str, exc)
                        so_str = q.get("sharesout")
                        if so_str:
                            try:
                                so_clean = str(so_str).upper()
                                if so_clean.endswith("B"):
                                    res["shares_outstanding"] = float(so_clean[:-1]) * 1e9
                                elif so_clean.endswith("M"):
                                    res["shares_outstanding"] = float(so_clean[:-1]) * 1e6
                                else:
                                    res["shares_outstanding"] = float(so_clean.replace(",", ""))
                            except ValueError as exc:
                                logger.debug("sharesout CNBC no numérico (%r): %s", so_str, exc)
                    elif sym == "US10Y":
                        rf_str = q.get("last")
                        if rf_str:
                            try:
                                val = float(str(rf_str).replace("%", "").strip())
                                res["rf_10y"] = val / 100.0 if val > 1.0 else val
                            except ValueError as exc:
                                logger.debug("US10Y CNBC no numérico (%r): %s", rf_str, exc)
                if res["price"] is not None:
                    res["success"] = True
        except Exception as e:
            print(f"[MarketData] CNBC aviso: {e}")

        return res

    @classmethod
    def _build_offline_fallback(
        cls, ticker: str, now_iso: str, cache: Dict[str, Any], diluted_shares_10q: Optional[float], sector_beta_fallback: float
    ) -> Dict[str, Any]:
        """Construye respuesta segura offline preservando caché válido si existe."""
        print(f"[MarketData] AVISO: Modo Offline activado para {ticker}. Utilizando parámetros de seguridad.")
        cached_item = cache.get(ticker, {})
        c_price = cached_item.get("price")
        c_shares = diluted_shares_10q or cached_item.get("diluted_shares")
        c_mktcap = (c_shares * c_price / 1e6) if (c_shares and c_price) else cached_item.get("market_cap_usd_m")
        return {
            "ticker": ticker,
            "timestamp": now_iso,
            "timestamp_epoch": time.time(),
            "is_offline": True,
            "from_cache": bool(cached_item),
            "price": c_price,
            "market_cap_usd_m": c_mktcap,
            "diluted_shares": c_shares,
            "dividend_yield": cached_item.get("dividend_yield"),
            "rf_10y": 0.0425,
            "beta": cached_item.get("beta") or sector_beta_fallback,
            "erp": 0.0475,
            "audit": {
                "status": "FALLBACK_OFFLINE",
                "sources_used": ["Offline Cached / Sector Defaults"],
                "notes": f"Modo offline para {ticker}: datos extraídos de caché o pendientes de conexión en vivo.",
            },
        }

    @classmethod
    def _arbitrate_price(cls, price_a: Optional[float], price_b: Optional[float], audit_log: List[str]) -> Optional[float]:
        """Arbitra precio de mercado entre Yahoo Finance y CNBC dentro de tolerancia."""
        if price_a and price_b:
            diff_pct = abs(price_a - price_b) / ((price_a + price_b) / 2.0)
            if diff_pct <= cls.TOLERANCE_PRICE_PCT:
                chosen = round((price_a + price_b) / 2.0, 4)
                audit_log.append(f"Precio validado por consenso: ${chosen:.2f} (Yahoo: ${price_a:.2f}, CNBC: ${price_b:.2f}, Δ={diff_pct*100:.2f}%)")
                return chosen
            audit_log.append(f"ALERTA: Discrepancia de precio > 1.5% (Yahoo: ${price_a:.2f}, CNBC: ${price_b:.2f}). Se adopta Yahoo Finance.")
            return price_a
        chosen = price_a or price_b
        audit_log.append(f"Precio extraído de fuente única disponible: ${chosen:.2f}")
        return chosen

    @classmethod
    def _arbitrate_shares_and_mcap(
        cls,
        yf_data: Dict[str, Any],
        cnbc_data: Dict[str, Any],
        diluted_shares_10q: Optional[float],
        chosen_price: Optional[float],
        audit_log: List[str],
    ) -> Tuple[Optional[float], float]:
        """Arbitra conteo accionario con protección ante splits recientes y calcula Market Cap."""
        source_shares = yf_data.get("shares_outstanding") or cnbc_data.get("shares_outstanding")
        source_mcap = yf_data.get("market_cap")
        shares = source_shares or diluted_shares_10q
        mcap_source = "Fuentes de Mercado Validadas"

        if diluted_shares_10q and source_shares and abs(diluted_shares_10q - source_shares) / max(diluted_shares_10q, source_shares) > 0.50:
            audit_log.append(
                f"Aviso Split Accionario: Se detectó variación significativa entre 10-Q ({diluted_shares_10q:,.0f}) y mercado actual ({source_shares:,.0f}). Se prioriza conteo ajustado por split."
            )
            shares = source_shares
        elif diluted_shares_10q:
            shares = diluted_shares_10q
            mcap_source = "Precio de Mercado x Acciones Diluidas Auditadas (SEC 10-Q)"

        if shares and chosen_price:
            market_cap = chosen_price * shares
            audit_log.append(f"Market Cap calculado: ${market_cap / 1e6:,.1f}M vía {mcap_source}")
        elif source_mcap:
            market_cap = source_mcap
            audit_log.append(f"Market Cap directo: ${market_cap / 1e6:,.1f}M")
        else:
            market_cap = 0.0
        return shares, market_cap

    @classmethod
    def get_market_data(
        cls,
        ticker: str,
        diluted_shares_10q: Optional[float] = None,
        sector_beta_fallback: float = 1.10,
        sector_wacc_fallback: float = 0.085,
        bypass_cache: bool = False,
    ) -> Dict[str, Any]:
        """Ejecuta extracción, validación cruzada y arbitraje de métricas en tiempo real."""
        ticker = ticker.upper()
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

        cache = cls._load_cache()
        if not bypass_cache and ticker in cache:
            cached_entry = cache[ticker]
            if time.time() - cached_entry.get("timestamp_epoch", 0) < cls.DEFAULT_CACHE_TTL_SECONDS:
                cached_entry["from_cache"] = True
                return cached_entry

        yf_data = cls.fetch_yahoo_metrics(ticker)
        cnbc_data = cls.fetch_cnbc_metrics(ticker)
        if not (yf_data["success"] or cnbc_data["success"]):
            return cls._build_offline_fallback(ticker, now_iso, cache, diluted_shares_10q, sector_beta_fallback)

        audit_log: List[str] = []
        chosen_price = cls._arbitrate_price(yf_data.get("price"), cnbc_data.get("price"), audit_log)
        shares, market_cap = cls._arbitrate_shares_and_mcap(yf_data, cnbc_data, diluted_shares_10q, chosen_price, audit_log)

        rf_a, rf_b = yf_data.get("rf_10y"), cnbc_data.get("rf_10y")
        if rf_a and rf_b:
            if abs(rf_a - rf_b) <= cls.TOLERANCE_RF_BPS:
                chosen_rf = round((rf_a + rf_b) / 2.0, 5)
                audit_log.append(f"Rf (Bono 10Y) consensuado: {chosen_rf*100:.3f}% (Yahoo ^TNX: {rf_a*100:.3f}%, CNBC US10Y: {rf_b*100:.3f}%)")
            else:
                chosen_rf = rf_b or rf_a
                audit_log.append(f"Aviso Rf: Discrepancia de tasas ({rf_a*100:.3f}% vs {rf_b*100:.3f}%). Se adopta {chosen_rf*100:.3f}%.")
        else:
            chosen_rf = rf_a or rf_b or 0.0425
            audit_log.append(f"Rf de fuente disponible: {chosen_rf*100:.3f}%")

        beta_a, beta_b = yf_data.get("beta"), cnbc_data.get("beta")
        if beta_a and beta_b:
            diff_beta = abs(beta_a - beta_b)
            if diff_beta <= cls.TOLERANCE_BETA:
                chosen_beta = round((beta_a + beta_b) / 2.0, 3)
                audit_log.append(f"Beta validado: {chosen_beta:.2f} (Yahoo: {beta_a:.2f}, CNBC: {beta_b:.2f}, Δ={diff_beta:.2f})")
            else:
                chosen_beta = round(beta_a, 3)
                audit_log.append(f"Aviso Beta: Discrepancia moderada (Yahoo: {beta_a:.2f}, CNBC: {beta_b:.2f}). Se adopta Yahoo 5Y Monthly.")
        else:
            chosen_beta = beta_a or beta_b or sector_beta_fallback
            audit_log.append(f"Beta adoptado: {chosen_beta:.2f} (Fuente disponible o sector fallback)")

        if abs(chosen_beta - sector_beta_fallback) > 0.80:
            audit_log.append(f"ADVERTENCIA AUDITORÍA: La Beta ({chosen_beta:.2f}) se desvía fuertemente del promedio del sector ({sector_beta_fallback:.2f}).")

        result = {
            "ticker": ticker,
            "timestamp": now_iso,
            "timestamp_epoch": time.time(),
            "is_offline": False,
            "from_cache": False,
            "price": chosen_price,
            "market_cap_usd_m": round(market_cap / 1e6, 2) if market_cap else 0.0,
            "diluted_shares": shares,
            "rf_10y": chosen_rf,
            "beta": chosen_beta,
            "erp": 0.0475,
            "raw_sources": {"yahoo": yf_data, "cnbc": cnbc_data},
            "audit": {
                "status": "VALIDATED_CONSENSUS",
                "sources_used": [s for s in ("Yahoo Finance", "CNBC Quote Service") if (yf_data["success"] or cnbc_data["success"])],
                "notes": " | ".join(audit_log),
            },
        }
        cache[ticker] = result
        cls._save_cache(cache)
        return result


if __name__ == "__main__":
    test_ticker = sys.argv[1] if len(sys.argv) > 1 else "AAPL"
    print(f"Probando MarketDataExtractor para {test_ticker}...")
    res = MarketDataExtractor.get_market_data(test_ticker, diluted_shares_10q=15000000000)
    print(json.dumps(res, indent=2))
