"""
filing_context.py - Manifiesto Único de Datos y Contexto XBRL en Memoria (SharedFilingContext).
Centraliza la conexión a SEC EDGAR, cacheando en memoria RAM:
- Instancia única de edgar.Company y metadatos maestros (CIK, Nombre, SIC, Arquetipo FPI, Estándar Contable).
- Colecciones de formularios por tipo (10-K, 20-F, 10-Q, 6-K, 8-K, Form 4, Form 144).
- Objetos de formulario parseados (.obj()) indexados por accession_number (cero descargas/parseos duplicados).
- Árboles XBRL parseados (.xbrl()) indexados por accession_number (eliminando el mayor cuello de botella de CPU/red).
- DataFrame de Company Facts (facts_df) único.
- Metadatos y adjuntos EX-99 de comunicados de resultados para reutilización entre KPIs y Earnings Calls.

Sigue el principio Shared Data Manifest de Fiscal.ai: 'Construir un único manifiesto de datos lógico
y aplicar sobre él múltiples lentes analíticos sin repetir llamadas de red ni parseos de archivo'.
"""

import os
import sys
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
import pandas as pd

try:
    from edgar import Company, set_identity
except ImportError:
    Company = None
    def set_identity(ident):
        pass

try:
    from sec_rate_limiter import sec_call_with_retry, default_rate_limiter
except ImportError:
    try:
        from .sec_rate_limiter import sec_call_with_retry, default_rate_limiter
    except ImportError:
        def sec_call_with_retry(fn, *args, **kwargs):
            return fn(*args, **kwargs)
        default_rate_limiter = None


def load_sec_config() -> dict:
    """Carga configuración del entorno de SEC EDGAR."""
    possible_paths = [
        Path("config/sec_config.json"),
        Path(__file__).resolve().parents[3] / "config" / "sec_config.json",
        Path(__file__).resolve().parents[2] / "config" / "sec_config.json",
        Path(__file__).resolve().parents[4] / "config" / "sec_config.json",
    ]
    for p in possible_paths:
        if p.exists():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
    return {
        "sec_identity": "Pablo Inversiones pablo_inversiones@gmail.com",
        "google_drive_base_path": "G:\\Mi unidad\\analisis fundamental",
        "local_output_path": "data\\processed"
    }


class SharedFilingContext:
    """
    Manifiesto de datos compartido en memoria para una compañía durante la corrida del pipeline.
    Preserva el estado entre sec_extractor, sec_segment_extractor, kpi_extractor,
    earnings_call_extractor y governance_insider_analyzer.
    """

    def __init__(self, ticker: str, company: Any = None, sec_identity: Optional[str] = None):
        self.ticker = str(ticker).strip().upper()
        self._cfg = load_sec_config()
        self._identity = sec_identity or self._cfg.get("sec_identity", "Pablo Inversiones pablo_inversiones@gmail.com")
        
        # Configurar identidad de una sola vez
        try:
            set_identity(self._identity)
        except Exception:
            pass

        self._company = company
        self._cik: Optional[str] = None
        self._name: Optional[str] = None
        self._sic_code: Optional[str] = None
        self._accounting_std: Optional[str] = None
        self._is_fpi: Optional[bool] = None

        # Cachés lazy en RAM indexados
        self._filings_cache: Dict[Any, Any] = {}
        self._obj_cache: Dict[str, Any] = {}
        self._xbrl_cache: Dict[str, Any] = {}
        self._facts_df: Optional[pd.DataFrame] = None
        self._facts_fetched: bool = False
        self._earnings_release_data: Optional[Dict[str, Any]] = None

        # Telemetría de desempeño
        self.stats = {
            "cache_hits": 0,
            "network_fetches": 0,
            "obj_parses": 0,
            "xbrl_parses": 0
        }

    @property
    def company(self) -> Any:
        """Obtiene o resuelve perezosamente la instancia Company(ticker) de edgar-tools."""
        if self._company is None:
            if Company is None:
                raise ImportError("[SharedFilingContext] edgar-tools no está instalado en el entorno.")
            self.stats["network_fetches"] += 1
            self._company = sec_call_with_retry(Company, self.ticker)
        return self._company

    @property
    def cik(self) -> str:
        """CIK de 10 dígitos con ceros a la izquierda."""
        if self._cik is None:
            raw_cik = getattr(self.company, "cik", None)
            if raw_cik is not None:
                self._cik = str(raw_cik).zfill(10)
            else:
                self._cik = "0000000000"
        return self._cik

    @property
    def name(self) -> str:
        """Razón social oficial de la empresa registrada ante la SEC."""
        if self._name is None:
            self._name = getattr(self.company, "name", self.ticker) or self.ticker
        return self._name

    @property
    def sic_code(self) -> Optional[str]:
        """Código de clasificación industrial estándar (SIC)."""
        if self._sic_code is None:
            s = getattr(self.company, "sic", None)
            self._sic_code = str(s) if s is not None else None
        return self._sic_code

    @property
    def is_fpi(self) -> bool:
        """Determina si la empresa es un Foreign Private Issuer (reporta bajo 20-F / 40-F / 6-K)."""
        if self._is_fpi is None:
            try:
                f_20f = self.get_filings(form="20-F")
                if f_20f is not None and len(f_20f) > 0:
                    self._is_fpi = True
                    return True
                f_40f = self.get_filings(form="40-F")
                if f_40f is not None and len(f_40f) > 0:
                    self._is_fpi = True
                    return True
            except Exception:
                pass
            self._is_fpi = False
        return self._is_fpi

    @property
    def accounting_standard(self) -> str:
        """Detecta si la compañía reporta bajo IFRS (20-F / 40-F) o US-GAAP (10-K)."""
        if self._accounting_std is None:
            self._accounting_std = "US-GAAP"
            try:
                latest_filings = self.get_filings(form=["10-K", "20-F", "40-F"])
                if latest_filings and len(latest_filings) > 0:
                    top_form = str(getattr(latest_filings[0], "form", "")).upper()
                    if "20-F" in top_form or "40-F" in top_form:
                        self._accounting_std = "IFRS"
            except Exception:
                pass
        return self._accounting_std

    def _normalize_form_key(self, form: Union[str, List[str], Tuple[str, ...], set]) -> Any:
        """Normaliza el tipo de formulario a clave hashable inmutable."""
        if isinstance(form, (list, tuple, set)):
            return tuple(sorted([str(f).strip().upper() for f in form]))
        return str(form).strip().upper()

    def get_filings(self, form: Union[str, List[str], Tuple[str, ...], set]) -> Any:
        """
        Obtiene la colección de filings para un formulario o lista de formularios,
        cacheándola en memoria para evitar llamadas redundantes a company.get_filings().
        """
        key = self._normalize_form_key(form)
        if key in self._filings_cache:
            self.stats["cache_hits"] += 1
            return self._filings_cache[key]

        self.stats["network_fetches"] += 1
        raw_form = list(form) if isinstance(form, (list, tuple, set)) else form
        filings = sec_call_with_retry(self.company.get_filings, form=raw_form)
        self._filings_cache[key] = filings
        return filings

    def get_filing_obj(self, filing: Any) -> Any:
        """
        Descarga y parsea el objeto filing.obj(), indexándolo por accession_number.
        Si ya fue parseado previamente en cualquier submódulo, lo devuelve en O(1).
        Además, si expone financials.xb, indexa automáticamente el árbol XBRL en la caché.
        """
        if filing is None:
            return None

        acc_num = str(getattr(filing, "accession_number", "") or "")
        if not acc_num:
            self.stats["obj_parses"] += 1
            return sec_call_with_retry(filing.obj)

        if acc_num in self._obj_cache:
            self.stats["cache_hits"] += 1
            return self._obj_cache[acc_num]

        self.stats["obj_parses"] += 1
        obj = sec_call_with_retry(filing.obj)
        self._obj_cache[acc_num] = obj

        # Población oportunista de la caché XBRL si el objeto ya lo contiene
        try:
            if hasattr(obj, "financials") and obj.financials:
                xb = getattr(obj.financials, "xb", None)
                if xb and acc_num not in self._xbrl_cache:
                    self._xbrl_cache[acc_num] = xb
        except Exception:
            pass

        return obj

    def get_filing_xbrl(self, filing: Any) -> Any:
        """
        Devuelve el árbol XBRL del formulario (.xbrl()), indexado por accession_number.
        Reutiliza el parseo ya realizado por sec_extractor o enrich_annual_statements_with_individual_filings,
        eliminando el parseo repetido en sec_segment_extractor.
        """
        if filing is None:
            return None

        acc_num = str(getattr(filing, "accession_number", "") or "")
        if not acc_num:
            self.stats["xbrl_parses"] += 1
            return sec_call_with_retry(filing.xbrl)

        if acc_num in self._xbrl_cache:
            self.stats["cache_hits"] += 1
            return self._xbrl_cache[acc_num]

        # Si ya teníamos el objeto filing.obj(), comprobar si tiene financials.xb
        if acc_num in self._obj_cache:
            obj = self._obj_cache[acc_num]
            try:
                if hasattr(obj, "financials") and obj.financials:
                    xb = getattr(obj.financials, "xb", None)
                    if xb:
                        self._xbrl_cache[acc_num] = xb
                        self.stats["cache_hits"] += 1
                        return xb
            except Exception:
                pass

        self.stats["xbrl_parses"] += 1
        xb = sec_call_with_retry(filing.xbrl)
        self._xbrl_cache[acc_num] = xb
        return xb

    def get_facts_df(self) -> Optional[pd.DataFrame]:
        """
        Obtiene y cachea el DataFrame completo de Company Facts (company.get_facts()).
        Evita múltiples descargas de facts.json por ticker.
        """
        if self._facts_fetched:
            self.stats["cache_hits"] += 1
            return self._facts_df

        self._facts_fetched = True
        try:
            self.stats["network_fetches"] += 1
            facts_obj = sec_call_with_retry(self.company.get_facts)
            if hasattr(facts_obj, "to_dataframe"):
                self._facts_df = facts_obj.to_dataframe()
            else:
                self._facts_df = None
        except Exception:
            self._facts_df = None

        return self._facts_df

    def get_latest_earnings_release_data(self) -> Dict[str, Any]:
        """
        Localiza de forma unificada el último comunicado de resultados (Item 2.02 / 7.01 de Form 8-K o Form 6-K)
        y cachea los metadatos y adjuntos EX-99 para ser compartidos entre kpi_extractor y earnings_call_extractor.
        """
        if self._earnings_release_data is not None:
            self.stats["cache_hits"] += 1
            return self._earnings_release_data

        sec_info = {
            "filing_date": None,
            "accession_number": None,
            "form": None,
            "guidance_text": [],
            "exhibits": [],
            "attachments_meta": []
        }

        try:
            # Primero intentar con 8-K
            f8k = self.get_filings("8-K")
            target_filing = None
            if f8k and len(f8k) > 0:
                for f in f8k[:10]:
                    items_str = str(getattr(f, "items", ""))
                    if "2.02" in items_str or "7.01" in items_str:
                        target_filing = f
                        sec_info["form"] = "8-K"
                        break

            # Si es Foreign Private Issuer o no hay 8-K, buscar en 6-K
            if target_filing is None:
                f6k = self.get_filings("6-K")
                if f6k and len(f6k) > 0:
                    for f in f6k[:8]:
                        doc_str = str(getattr(f, "primary_document", "")).lower()
                        desc_str = str(getattr(f, "description", "")).lower()
                        if any(k in doc_str or k in desc_str for k in ["earnings", "results", "press", "release", "financial"]):
                            target_filing = f
                            sec_info["form"] = "6-K"
                            break
                    if target_filing is None and len(f6k) > 0:
                        target_filing = f6k[0]
                        sec_info["form"] = "6-K"

            if target_filing is not None:
                sec_info["filing_date"] = str(getattr(target_filing, "filing_date", None))
                sec_info["accession_number"] = str(getattr(target_filing, "accession_number", None))
                
                # Adjuntos y exhibits
                for att in getattr(target_filing, "attachments", []):
                    desc = str(getattr(att, "description", "")).lower()
                    doc = str(getattr(att, "document", "")).lower()
                    form_t = str(getattr(att, "form_type", "")).lower()
                    is_ex99 = "99.1" in desc or "ex-99" in form_t or "ex99" in doc or "pressrelease" in doc or "earnings" in doc
                    sec_info["attachments_meta"].append({
                        "document": getattr(att, "document", ""),
                        "description": getattr(att, "description", ""),
                        "form_type": getattr(att, "form_type", ""),
                        "is_ex99": is_ex99
                    })
        except Exception as e:
            pass

        self._earnings_release_data = sec_info
        return self._earnings_release_data

    def print_telemetry_summary(self):
        """Imprime en consola las métricas de eficiencia de caché del contexto."""
        hits = self.stats["cache_hits"]
        fetches = self.stats["network_fetches"]
        objs = self.stats["obj_parses"]
        xbrls = self.stats["xbrl_parses"]
        total_ops = hits + fetches + objs + xbrls
        hit_ratio = (hits / total_ops * 100) if total_ops > 0 else 0.0
        print(f"\n[SharedFilingContext Telemetry] {self.ticker.upper()} -> Cache Hits: {hits} | Network Fetches: {fetches} | Objs Parsed: {objs} | XBRL Parsed: {xbrls} (Hit Ratio: {hit_ratio:.1f}%)")
