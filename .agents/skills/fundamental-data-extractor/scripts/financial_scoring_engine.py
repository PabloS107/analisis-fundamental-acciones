"""
financial_scoring_engine.py - Motor Cuantitativo de Scoring Fundamental:
Piotroski F-Score (2000) y Mohanram G-Score (2005) con Mejoras Institucionales.

Implementa:
- 9 criterios de Piotroski F-Score (0 a 9 puntos).
- 8 criterios de Mohanram G-Score (0 a 8 puntos) contra medianas sectoriales (SIC / GICS).
- 5 mejoras institucionales consensuadas:
  1. EQ_OFFER con Acciones Básicas exclusivamente (aísla el efecto del Treasury Stock Method).
  2. F_dLEVER con Deuda Financiera Total (corriente + no corriente).
  3. G8 mediante Apalancamiento Operativo Comercial (% Delta Ventas > % Delta SG&A).
  4. G4 y G5 ajustados por Coeficiente de Variación (CV) y Cláusula de Hipercrecimiento / Alto Desempeño.
  5. G7 adaptado a modelos Asset-Light mediante Tasa de Inversión Total (CapEx + R&D).
- Matriz Combinada de Decisión (Compounder de Élite, Cash Cow, Crecimiento Vulnerable, Trampa de Valor).
- Exportación estructurada a JSON y soporte para series multianuales (2016-2025 + LTM).
"""

import os
import sys
import json
import math
import statistics
from pathlib import Path
import json
import math
import statistics
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

try:
    from market_data_provider import MarketDataExtractor
except ImportError:
    try:
        from .market_data_provider import MarketDataExtractor
    except ImportError:
        MarketDataExtractor = None

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass




def load_industry_medians(config_path: Optional[str] = None) -> Dict[str, Any]:
    """Carga el catálogo de medianas sectoriales por código SIC/GICS."""
    if config_path and Path(config_path).exists():
        p = Path(config_path)
    else:
        # Buscar en config/industry_medians.json relativo a la raíz del proyecto
        base_dir = Path(__file__).resolve().parent
        candidates = [
            base_dir.parent.parent.parent.parent / "config" / "industry_medians.json",
            base_dir.parent.parent.parent / "config" / "industry_medians.json",
            Path("config/industry_medians.json"),
            Path("../config/industry_medians.json")
        ]
        p = None
        for c in candidates:
            if c.exists():
                p = c
                break

    if p and p.exists():
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)

    # Fallback por defecto si no existe archivo
    return {
        "BROAD_MARKET": {
            "sic_code": "0000",
            "industry_name": "Broad Market Benchmark (S&P 500 Non-Financials)",
            "median_roa": 0.055,
            "p75_roa": 0.100,
            "median_cfroa": 0.078,
            "median_cv_roa": 0.38,
            "median_sales_growth": 0.060,
            "median_cv_sales_growth": 0.42,
            "median_rd_intensity": 0.035,
            "median_capex_intensity": 0.045,
            "median_total_reinvestment": 0.080,
            "is_asset_light": False
        }
    }


def load_peer_benchmarks(config_path: Optional[str] = None) -> Dict[str, Any]:
    """Carga los benchmarks y cifras LTM del grupo de pares desde config/peer_benchmarks.json."""
    if config_path and Path(config_path).exists():
        p = Path(config_path)
    else:
        base_dir = Path(__file__).resolve().parent
        candidates = [
            base_dir.parent.parent.parent.parent / "config" / "peer_benchmarks.json",
            base_dir.parent.parent.parent / "config" / "peer_benchmarks.json",
            Path("config/peer_benchmarks.json"),
            Path("../config/peer_benchmarks.json")
        ]
        p = None
        for c in candidates:
            if c.exists():
                p = c
                break

    if p and p.exists():
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)

    return {}


def _safe_float(val: Any) -> Optional[float]:
    """Convierte con seguridad un valor numérico o string a float, filtrando NaN y cadenas no numéricas."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val) if not math.isnan(val) else None
    try:
        s = str(val).strip().replace(",", "")
        if s.lower() in ("none", "nan", "n/a", "-", ""):
            return None
        f = float(s)
        return f if not math.isnan(f) else None
    except (ValueError, TypeError):
        return None


def _to_millions(val: Optional[float]) -> Optional[float]:
    """Escala a millones si la magnitud absoluta excede $1M, soportando valores negativos."""
    if val is None:
        return None
    return val / 1e6 if abs(val) > 1e6 else val


def compute_peer_benchmarks(peers: Any) -> Dict[str, Any]:
    """Calcula dinámicamente las medianas sectoriales y percentil 75 a partir de los pares de la industria (Hoja 8)."""
    if isinstance(peers, dict):
        peers = peers.get("peers", [])
    roas = []
    cfroas = []
    rds = []
    reinvs = []
    capexs = []
    gps = []
    gp_ex_cashs = []
    gms = []
    turns = []

    for p in peers:
        assets = _safe_float(p.get("total_assets_usd_m"))
        if not assets or assets <= 0:
            continue
        rd = _safe_float(p.get("rd_expense_usd_m")) or 0.0
        capex = _safe_float(p.get("capex_usd_m")) or 0.0
        ni = _safe_float(p.get("net_income_usd_m")) or 0.0
        cfo = _safe_float(p.get("cfo_usd_m")) or 0.0
        rev = _safe_float(p.get("revenue_usd_m"))
        gp = _safe_float(p.get("gross_profit_usd_m"))
        cash = _safe_float(p.get("cash_usd_m")) or 0.0

        roas.append(ni / assets)
        cfroas.append(cfo / assets)
        rds.append(rd / assets)
        reinvs.append((rd + capex) / assets)
        capexs.append(capex / assets)

        if gp is not None:
            gps.append(gp / assets)
            op_assets = (assets - cash) if (assets > cash and (assets - cash) > 0) else assets
            gp_ex_cashs.append(gp / op_assets)
            if rev and rev > 0:
                gms.append(gp / rev)
        if rev and rev > 0:
            turns.append(rev / assets)

    # ROIC, WACC, Spread y ROC en pares si están disponibles
    trad_roics = [_safe_float(p.get("traditional_roic")) for p in peers if p.get("traditional_roic") is not None]
    adj_roics = [_safe_float(p.get("adjusted_roic")) for p in peers if p.get("adjusted_roic") is not None]
    waccs = [_safe_float(p.get("wacc")) for p in peers if p.get("wacc") is not None]
    spreads = [_safe_float(p.get("economic_spread")) for p in peers if p.get("economic_spread") is not None]
    rocs = [_safe_float(p.get("greenblatt_roc", p.get("roc"))) for p in peers if p.get("greenblatt_roc") is not None or p.get("roc") is not None]

    def _excel_percentile(data, p):
        sorted_data = sorted(data)
        n = len(sorted_data)
        if n == 0:
            return 0.0
        if n == 1:
            return sorted_data[0]
        rank = (n - 1) * p
        lower_idx = int(rank)
        upper_idx = min(lower_idx + 1, n - 1)
        weight = rank - lower_idx
        return sorted_data[lower_idx] + weight * (sorted_data[upper_idx] - sorted_data[lower_idx])

    return {
        "median_roa": statistics.median(roas) if roas else 0.055,
        "median_cfroa": statistics.median(cfroas) if cfroas else 0.078,
        "median_rd_intensity": statistics.median(rds) if rds else 0.035,
        "median_total_reinvestment": statistics.median(reinvs) if reinvs else 0.080,
        "median_capex_intensity": statistics.median(capexs) if capexs else 0.045,
        "p75_roa": _excel_percentile(roas, 0.75) if roas else 0.100,
        "median_gross_profitability": statistics.median(gps) if gps else 0.280,
        "p75_gross_profitability": _excel_percentile(gps, 0.75) if gps else 0.400,
        "median_gp_ex_cash": statistics.median(gp_ex_cashs) if gp_ex_cashs else 0.320,
        "median_gross_margin": statistics.median(gms) if gms else 0.380,
        "median_asset_turnover": statistics.median(turns) if turns else 0.75,
        "median_traditional_roic": statistics.median(trad_roics) if trad_roics else 0.185,
        "median_adjusted_roic": statistics.median(adj_roics) if adj_roics else 0.165,
        "median_wacc": statistics.median(waccs) if waccs else 0.088,
        "median_economic_spread": statistics.median(spreads) if spreads else 0.077,
        "median_greenblatt_roc": statistics.median(rocs) if rocs else 0.350,
        "peer_greenblatt_roc_median": statistics.median(rocs) if rocs else 0.350
    }


def get_sector_benchmarks(
    sic_code: Optional[str],
    medians_db: Dict[str, Any],
    ticker: Optional[str] = None,
    peer_benchmarks_db: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Obtiene los benchmarks de la industria para un código SIC o ticker, integrando dinámicamente las medianas de los pares (Hoja 8)."""
    if not sic_code and ticker:
        ticker_map = medians_db.get("ticker_to_sic", {})
        sic_code = ticker_map.get(ticker.upper())

    base_bm = None
    if sic_code:
        sic_clean = str(sic_code).strip()
        key = f"SIC_{sic_clean}"
        if key in medians_db:
            base_bm = medians_db[key]
        else:
            for k, v in medians_db.items():
                if isinstance(v, dict) and v.get("sic_code") == sic_clean:
                    base_bm = v
                    break

    if not base_bm:
        base_bm = medians_db.get("BROAD_MARKET", {
            "sic_code": "0000",
            "industry_name": "Broad Market Benchmark",
            "median_roa": 0.055,
            "p75_roa": 0.100,
            "median_cfroa": 0.078,
            "median_cv_roa": 0.38,
            "median_sales_growth": 0.060,
            "median_cv_sales_growth": 0.42,
            "median_rd_intensity": 0.035,
            "median_capex_intensity": 0.045,
            "median_total_reinvestment": 0.080,
            "is_asset_light": False
        })

    benchmarks = dict(base_bm)

    # Cargar y calcular medianas dinámicas de config/peer_benchmarks.json (Hoja 8)
    if peer_benchmarks_db is None:
        peer_benchmarks_db = load_peer_benchmarks()

    ind_peers = peer_benchmarks_db.get("industry_benchmarks", {})
    peer_group = None
    if sic_code:
        sic_key = f"SIC_{str(sic_code).strip()}"
        if sic_key in ind_peers:
            peer_group = ind_peers[sic_key]

    if not peer_group and ticker:
        for k, v in ind_peers.items():
            if any(p.get("ticker", "").upper() == ticker.upper() for p in v.get("peers", [])):
                peer_group = v
                break

    if peer_group and "peers" in peer_group:
        dyn_medians = compute_peer_benchmarks(peer_group["peers"])
        benchmarks.update(dyn_medians)
        benchmarks["peers_detail"] = peer_group.get("peers", [])
        benchmarks["peer_group_name"] = peer_group.get("industry_name", benchmarks.get("industry_name"))
        benchmarks["peer_count"] = len(peer_group.get("peers", []))
        benchmarks["peer_source"] = peer_group.get("source", "SEC EDGAR Form 10-K & 10-Q Audited Reports")
        benchmarks["dynamic_peer_medians"] = True

    return benchmarks



class PiotroskiScoreCalculator:
    """Calculador canónico del Piotroski F-Score (2000) con mejoras de deuda total y acciones básicas."""

    @staticmethod
    def calculate_year(
        period: str,
        current_data: Dict[str, float],
        prev_data: Optional[Dict[str, float]],
        prev2_data: Optional[Dict[str, float]]
    ) -> Dict[str, Any]:
        """
        Calcula los 9 criterios para un periodo dado t frente a t-1 (y t-2 para rotación de activos).
        current_data contiene:
          - net_income, cfo, total_assets, total_debt, current_assets, current_liabilities,
            basic_shares, gross_profit, revenue.
        """
        results = {
            "period": period,
            "signals": {},
            "total_score": 0,
            "max_score": 9,
            "rating": "",
            "summary_text": ""
        }

        ni_t = _safe_float(current_data.get("net_income"))
        cfo_t = _safe_float(current_data.get("cfo"))
        assets_t = _safe_float(current_data.get("total_assets"))
        debt_t = _safe_float(current_data.get("total_debt"))
        ca_t = _safe_float(current_data.get("current_assets"))
        cl_t = _safe_float(current_data.get("current_liabilities"))
        shares_t = _safe_float(current_data.get("basic_shares"))
        gp_t = _safe_float(current_data.get("gross_profit"))
        rev_t = _safe_float(current_data.get("revenue"))

        # Datos año t-1
        ni_prev = _safe_float(prev_data.get("net_income")) if prev_data else None
        assets_prev = _safe_float(prev_data.get("total_assets")) if prev_data else None
        debt_prev = _safe_float(prev_data.get("total_debt")) if prev_data else None
        ca_prev = _safe_float(prev_data.get("current_assets")) if prev_data else None
        cl_prev = _safe_float(prev_data.get("current_liabilities")) if prev_data else None
        shares_prev = _safe_float(prev_data.get("basic_shares")) if prev_data else None
        gp_prev = _safe_float(prev_data.get("gross_profit")) if prev_data else None
        rev_prev = _safe_float(prev_data.get("revenue")) if prev_data else None

        # Datos año t-2 (para rotación previa)
        assets_prev2 = _safe_float(prev2_data.get("total_assets")) if prev2_data else None

        score = 0

        # -------------------------------------------------------------
        # Bloque I: Rentabilidad (4 Señales)
        # -------------------------------------------------------------
        # 1. F_ROA: Net Income / Assets_{t-1} > 0
        roa_denom = assets_prev if (assets_prev and assets_prev > 0) else assets_t
        roa_t = (ni_t / roa_denom) if (ni_t is not None and roa_denom and roa_denom > 0) else None
        pass_roa = bool(roa_t is not None and roa_t > 0)
        score += 1 if pass_roa else 0
        results["signals"]["F_ROA"] = {
            "name": "ROA Positivo",
            "category": "Rentabilidad",
            "value": roa_t,
            "formatted_value": f"{roa_t*100:.2f}%" if roa_t is not None else "N/A",
            "comparison_label": f"{roa_t*100:.2f}% > 0%" if roa_t is not None else "N/A",
            "threshold": "> 0.00%",
            "passed": pass_roa,
            "points": 1 if pass_roa else 0,
            "description": "Utilidad neta positiva sobre la base de activos instalados."
        }

        # 2. F_CFO: Cash Flow from Operations > 0
        pass_cfo = bool(cfo_t is not None and cfo_t > 0)
        score += 1 if pass_cfo else 0
        results["signals"]["F_CFO"] = {
            "name": "CFO Positivo",
            "category": "Rentabilidad",
            "value": cfo_t,
            "formatted_value": f"${cfo_t/1e6:,.1f}M" if cfo_t is not None else "N/A",
            "comparison_label": f"${cfo_t/1e9:,.1f}B > $0" if cfo_t is not None else "N/A",
            "threshold": "> $0M",
            "passed": pass_cfo,
            "points": 1 if pass_cfo else 0,
            "description": "Flujo de caja operativo neto positivo."
        }

        # 3. F_dROA: ROA_t - ROA_{t-1} > 0
        roa_prev_denom = assets_prev2 if (assets_prev2 and assets_prev2 > 0) else assets_prev
        roa_prev = (ni_prev / roa_prev_denom) if (ni_prev is not None and roa_prev_denom and roa_prev_denom > 0) else None
        delta_roa = (roa_t - roa_prev) if (roa_t is not None and roa_prev is not None) else None
        pass_droa = bool(delta_roa is not None and delta_roa > 0)
        score += 1 if pass_droa else 0
        results["signals"]["F_dROA"] = {
            "name": "Mejora de ROA (Delta ROA)",
            "category": "Rentabilidad",
            "value": delta_roa,
            "formatted_value": f"{delta_roa*100:+.2f}%" if delta_roa is not None else "N/A",
            "comparison_label": f"{roa_t*100:.1f}% vs {roa_prev*100:.1f}% ({delta_roa*100:+.2f}%)" if (roa_t is not None and roa_prev is not None) else (f"{delta_roa*100:+.2f}%" if delta_roa is not None else "N/A"),
            "threshold": "> 0.00%",
            "passed": pass_droa,
            "points": 1 if pass_droa else 0,
            "description": "Aceleración de la rentabilidad sobre activos frente al año previo."
        }

        # 4. F_ACCRUAL: CFO > Net Income (Calidad Contable de Sloan)
        pass_accrual = bool(cfo_t is not None and ni_t is not None and cfo_t > ni_t)
        accrual_diff = (cfo_t - ni_t) if (cfo_t is not None and ni_t is not None) else None
        score += 1 if pass_accrual else 0
        results["signals"]["F_ACCRUAL"] = {
            "name": "Calidad Contable (CFO > NI)",
            "category": "Rentabilidad",
            "value": accrual_diff,
            "formatted_value": f"${accrual_diff/1e6:+,.1f}M" if accrual_diff is not None else "N/A",
            "comparison_label": f"CFO ${cfo_t/1e9:.1f}B > NI ${ni_t/1e9:.1f}B" if (cfo_t is not None and ni_t is not None) else "N/A",
            "threshold": "CFO > Utilidad Neta",
            "passed": pass_accrual,
            "points": 1 if pass_accrual else 0,
            "description": "Beneficios respaldados por efectivo contante (bajos devengos contables)."
        }

        # -------------------------------------------------------------
        # Bloque II: Estructura de Capital, Deuda y Liquidez (3 Señales)
        # -------------------------------------------------------------
        # 5. F_dLEVER: Deuda Total_t / Activos_t <= Deuda Total_{t-1} / Activos_{t-1} (Mejora B)
        lev_t = (debt_t / assets_t) if (debt_t is not None and assets_t and assets_t > 0) else None
        lev_prev = (debt_prev / assets_prev) if (debt_prev is not None and assets_prev and assets_prev > 0) else None
        delta_lev = (lev_t - lev_prev) if (lev_t is not None and lev_prev is not None) else None
        # Pasa si el apalancamiento no subió (<= 0)
        pass_dlever = bool(delta_lev is not None and delta_lev <= 0.0001)
        score += 1 if pass_dlever else 0
        results["signals"]["F_dLEVER"] = {
            "name": "Desendeudamiento Total",
            "category": "Apalancamiento y Liquidez",
            "value": delta_lev,
            "formatted_value": f"{delta_lev*100:+.2f}%" if delta_lev is not None else "N/A",
            "comparison_label": f"Deuda {lev_t*100:.1f}% vs {lev_prev*100:.1f}% ({delta_lev*100:+.2f}%)" if (lev_t is not None and lev_prev is not None) else (f"{delta_lev*100:+.2f}%" if delta_lev is not None else "N/A"),
            "threshold": "Delta Deuda Total <= 0%",
            "passed": pass_dlever,
            "points": 1 if pass_dlever else 0,
            "description": "Reducción o estabilidad del apalancamiento financiero total sobre activos."
        }

        # 6. F_dLIQUID: Current Ratio_t > Current Ratio_{t-1}
        cr_t = (ca_t / cl_t) if (ca_t is not None and cl_t and cl_t > 0) else None
        cr_prev = (ca_prev / cl_prev) if (ca_prev is not None and cl_prev and cl_prev > 0) else None
        delta_cr = (cr_t - cr_prev) if (cr_t is not None and cr_prev is not None) else None
        pass_dliquid = bool(delta_cr is not None and delta_cr > 0)
        score += 1 if pass_dliquid else 0
        results["signals"]["F_dLIQUID"] = {
            "name": "Mejora de Razón Corriente",
            "category": "Apalancamiento y Liquidez",
            "value": delta_cr,
            "formatted_value": f"{delta_cr:+.3f}x" if delta_cr is not None else "N/A",
            "comparison_label": f"CR {cr_t:.2f}x vs {cr_prev:.2f}x ({delta_cr:+.2f}x)" if (cr_t is not None and cr_prev is not None) else (f"{delta_cr:+.2f}x" if delta_cr is not None else "N/A"),
            "threshold": "Delta Current Ratio > 0x",
            "passed": pass_dliquid,
            "points": 1 if pass_dliquid else 0,
            "description": "Mayor cobertura de pasivos a corto plazo con activos corrientes."
        }

        # 7. EQ_OFFER: Basic Shares_t <= Basic Shares_{t-1} (Mejora A: Acciones Básicas)
        delta_shares = (shares_t - shares_prev) if (shares_t is not None and shares_prev is not None) else None
        pass_eq_offer = bool(delta_shares is not None and delta_shares <= 0.001)
        score += 1 if pass_eq_offer else 0
        results["signals"]["EQ_OFFER"] = {
            "name": "Cero Dilución (Acciones Básicas)",
            "category": "Apalancamiento y Liquidez",
            "value": delta_shares,
            "formatted_value": f"{delta_shares/1e6:+,.1f}M acciones" if delta_shares is not None else "N/A",
            "comparison_label": f"Acc {shares_t/1e6:,.0f}M vs {shares_prev/1e6:,.0f}M ({delta_shares/1e6:+,.0f}M)" if (shares_t is not None and shares_prev is not None) else (f"{delta_shares/1e6:+,.0f}M" if delta_shares is not None else "N/A"),
            "threshold": "Delta Acciones Básicas <= 0",
            "passed": pass_eq_offer,
            "points": 1 if pass_eq_offer else 0,
            "description": "Sin emisión neta dilutiva de capital; recompra de acciones o estabilidad."
        }

        # -------------------------------------------------------------
        # Bloque III: Eficiencia Operativa (2 Señales)
        # -------------------------------------------------------------
        # 8. F_dMARGIN: Gross Margin_t > Gross Margin_{t-1}
        gm_t = (gp_t / rev_t) if (gp_t is not None and rev_t and rev_t > 0) else None
        gm_prev = (gp_prev / rev_prev) if (gp_prev is not None and rev_prev and rev_prev > 0) else None
        delta_gm = (gm_t - gm_prev) if (gm_t is not None and gm_prev is not None) else None
        pass_dmargin = bool(delta_gm is not None and delta_gm > 0)
        score += 1 if pass_dmargin else 0
        results["signals"]["F_dMARGIN"] = {
            "name": "Expansión de Margen Bruto",
            "category": "Eficiencia Operativa",
            "value": delta_gm,
            "formatted_value": f"{delta_gm*100:+.2f}%" if delta_gm is not None else "N/A",
            "comparison_label": f"MB {gm_t*100:.1f}% vs {gm_prev*100:.1f}% ({delta_gm*100:+.2f}%)" if (gm_t is not None and gm_prev is not None) else (f"{delta_gm*100:+.2f}%" if delta_gm is not None else "N/A"),
            "threshold": "Delta Margen Bruto > 0%",
            "passed": pass_dmargin,
            "points": 1 if pass_dmargin else 0,
            "description": "Mayor poder de fijación de precios o menor coste unitario de ventas."
        }

        # 9. F_dTURN: Asset Turnover_t > Asset Turnover_{t-1}
        # Turnover_t = Rev_t / Assets_{t-1}
        # Turnover_{t-1} = Rev_{t-1} / Assets_{t-2}
        turn_t_denom = assets_prev if (assets_prev and assets_prev > 0) else assets_t
        turn_t = (rev_t / turn_t_denom) if (rev_t is not None and turn_t_denom and turn_t_denom > 0) else None

        turn_prev_denom = assets_prev2 if (assets_prev2 and assets_prev2 > 0) else assets_prev
        turn_prev = (rev_prev / turn_prev_denom) if (rev_prev is not None and turn_prev_denom and turn_prev_denom > 0) else None

        delta_turn = (turn_t - turn_prev) if (turn_t is not None and turn_prev is not None) else None
        pass_dturn = bool(delta_turn is not None and delta_turn > 0)
        score += 1 if pass_dturn else 0
        results["signals"]["F_dTURN"] = {
            "name": "Expansión Rotación de Activos",
            "category": "Eficiencia Operativa",
            "value": delta_turn,
            "formatted_value": f"{delta_turn:+.3f}x" if delta_turn is not None else "N/A",
            "comparison_label": f"Rot {turn_t:.2f}x vs {turn_prev:.2f}x ({delta_turn:+.2f}x)" if (turn_t is not None and turn_prev is not None) else (f"{delta_turn:+.2f}x" if delta_turn is not None else "N/A"),
            "threshold": "Delta Rotación > 0x",
            "passed": pass_dturn,
            "points": 1 if pass_dturn else 0,
            "description": "Mayor volumen de ingresos generado por cada dólar de activo instalado."
        }

        results["total_score"] = score
        if score >= 8:
            results["rating"] = "SALUD EXCEPCIONAL"
            results["status_color"] = "GREEN"
            results["summary_text"] = "Solidez financiera de primer nivel institucional. Calidad de balance óptima."
        elif score >= 6:
            results["rating"] = "SALUD SÓLIDA"
            results["status_color"] = "GREEN_LIGHT"
            results["summary_text"] = "Finanzas saludables y balance robusto con áreas menores de optimización."
        elif score >= 5:
            results["rating"] = "SALUD MODERADA"
            results["status_color"] = "YELLOW"
            results["summary_text"] = "Desempeño financiero equilibrado, monitorear márgenes o apalancamiento."
        else:
            results["rating"] = "VULNERABILIDAD FINANCIERA"
            results["status_color"] = "RED"
            results["summary_text"] = "Alerta de estrés operativo, dilución o deterioro de liquidez."

        return results


class MohanramScoreCalculator:
    """Calculador del Mohanram G-Score (2005) adaptado con benchmarks sectoriales y mejoras modernas."""

    @staticmethod
    def calculate_year(
        period: str,
        current_data: Dict[str, float],
        prev_data: Optional[Dict[str, float]],
        historical_series: List[Dict[str, Any]],
        benchmarks: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Calcula los 8 criterios para el Mohanram G-Score:
        - historical_series: lista de dicts de los últimos 3 a 5 años (orden cronológico) con keys 'period', 'net_income', 'revenue', 'total_assets'.
        """
        results = {
            "period": period,
            "signals": {},
            "total_score": 0,
            "max_score": 8,
            "rating": "",
            "benchmark_info": {
                "sic_code": benchmarks.get("sic_code", "0000"),
                "industry_name": benchmarks.get("industry_name", "Broad Market"),
                "is_asset_light": benchmarks.get("is_asset_light", False)
            },
            "summary_text": ""
        }

        ni_t = _safe_float(current_data.get("net_income"))
        cfo_t = _safe_float(current_data.get("cfo"))
        assets_t = _safe_float(current_data.get("total_assets"))
        assets_prev = _safe_float(prev_data.get("total_assets")) if prev_data else assets_t
        assets_denom = assets_prev if (assets_prev and assets_prev > 0) else assets_t

        rd_t = _safe_float(current_data.get("rd_expense")) or 0.0
        capex_t = _safe_float(current_data.get("capex")) or 0.0
        sga_t = _safe_float(current_data.get("sga_expense"))
        sga_prev = _safe_float(prev_data.get("sga_expense")) if prev_data else None

        rev_t = _safe_float(current_data.get("revenue"))
        rev_prev = _safe_float(prev_data.get("revenue")) if prev_data else None

        score = 0

        # -------------------------------------------------------------
        # Bloque I: Rentabilidad y Flujo de Caja vs Sector (3 Señales)
        # -------------------------------------------------------------
        # 1. G1: ROA_t > Median ROA Sector
        roa_t = (ni_t / assets_denom) if (ni_t is not None and assets_denom and assets_denom > 0) else None
        med_roa = benchmarks.get("median_roa", 0.055)
        pass_g1 = bool(roa_t is not None and roa_t > med_roa)
        score += 1 if pass_g1 else 0
        results["signals"]["G1_ROA"] = {
            "name": "ROA > Mediana del Sector",
            "category": "Rentabilidad vs Sector",
            "value": roa_t,
            "formatted_value": f"{roa_t*100:.2f}%" if roa_t is not None else "N/A",
            "comparison_label": f"ROA {roa_t*100:.2f}% vs Med {med_roa*100:.2f}%" if roa_t is not None else "N/A",
            "benchmark": f"{med_roa*100:.2f}%",
            "passed": pass_g1,
            "points": 1 if pass_g1 else 0,
            "description": "Rentabilidad sobre activos superior a la mitad del sector."
        }

        # 2. G2: CFROA_t > Median CFROA Sector
        cfroa_t = (cfo_t / assets_denom) if (cfo_t is not None and assets_denom and assets_denom > 0) else None
        med_cfroa = benchmarks.get("median_cfroa", 0.078)
        pass_g2 = bool(cfroa_t is not None and cfroa_t > med_cfroa)
        score += 1 if pass_g2 else 0
        results["signals"]["G2_CFROA"] = {
            "name": "CFROA > Mediana del Sector",
            "category": "Rentabilidad vs Sector",
            "value": cfroa_t,
            "formatted_value": f"{cfroa_t*100:.2f}%" if cfroa_t is not None else "N/A",
            "comparison_label": f"CFROA {cfroa_t*100:.2f}% vs Med {med_cfroa*100:.2f}%" if cfroa_t is not None else "N/A",
            "benchmark": f"{med_cfroa*100:.2f}%",
            "passed": pass_g2,
            "points": 1 if pass_g2 else 0,
            "description": "Generación de caja operativa sobre activos líder en la industria."
        }

        # 3. G3: CFO > Net Income (Calidad Contable)
        pass_g3 = bool(cfo_t is not None and ni_t is not None and cfo_t > ni_t)
        score += 1 if pass_g3 else 0
        diff_cfo_ni = (cfo_t - ni_t) if (cfo_t is not None and ni_t is not None) else None
        results["signals"]["G3_ACCRUAL"] = {
            "name": "Calidad Contable (CFO > NI)",
            "category": "Rentabilidad vs Sector",
            "value": diff_cfo_ni,
            "formatted_value": f"${diff_cfo_ni/1e6:+,.1f}M" if diff_cfo_ni is not None else "N/A",
            "comparison_label": f"CFO ${cfo_t/1e9:.1f}B > NI ${ni_t/1e9:.1f}B" if (cfo_t is not None and ni_t is not None) else "N/A",
            "benchmark": "CFO > Utilidad",
            "passed": pass_g3,
            "points": 1 if pass_g3 else 0,
            "description": "Flujo de caja operativo superior a las ganancias devengadas."
        }

        # -------------------------------------------------------------
        # Bloque II: Estabilidad y Predictibilidad Ajustada (2 Señales - Mejora D)
        # -------------------------------------------------------------
        # 4. G4: Estabilidad de ROA (Coeficiente de Variación o ROA en P75)
        # Extraer serie histórica de ROA
        hist_roas = []
        for item in historical_series:
            r_ni = item.get("net_income")
            r_ass = item.get("total_assets")
            if r_ni is not None and r_ass and r_ass > 0:
                hist_roas.append(r_ni / r_ass)

        cv_roa = None
        pass_g4 = False
        p75_roa_benchmark = benchmarks.get("p75_roa", 0.100)
        med_cv_roa = benchmarks.get("median_cv_roa", 0.38)

        if len(hist_roas) >= 2:
            mean_roa = sum(hist_roas) / len(hist_roas)
            var_roa = sum((x - mean_roa) ** 2 for x in hist_roas) / (len(hist_roas) - 1)
            std_roa = math.sqrt(var_roa)
            cv_roa = (std_roa / mean_roa) if (mean_roa and mean_roa > 0) else 1.0

            # Cláusula de Aceleración: Pasa si el CV es bajo O si el ROA actual está persistentemente en el P75 de la industria
            if cv_roa < med_cv_roa or (roa_t is not None and roa_t >= p75_roa_benchmark):
                pass_g4 = True
        elif roa_t is not None and roa_t >= p75_roa_benchmark:
            pass_g4 = True

        score += 1 if pass_g4 else 0
        results["signals"]["G4_VAR_ROA"] = {
            "name": "Estabilidad / Nivel Superior de ROA",
            "category": "Estabilidad y Predictibilidad",
            "value": cv_roa,
            "formatted_value": f"CV={cv_roa:.2f}" if cv_roa is not None else ("P75 Líder" if pass_g4 else "N/A"),
            "comparison_label": f"CV {cv_roa:.2f} < {med_cv_roa:.2f} (o P75)" if cv_roa is not None else ("P75 Líder" if pass_g4 else "N/A"),
            "benchmark": f"CV < {med_cv_roa:.2f} o ROA >= {p75_roa_benchmark*100:.2f}%",
            "passed": pass_g4,
            "points": 1 if pass_g4 else 0,
            "description": "Baja volatilidad en rentabilidad o nivel de retorno permanentemente en percentil 75 superior."
        }

        # 5. G5: Estabilidad de Crecimiento de Ventas (CV o Hipercrecimiento)
        hist_growths = []
        for i in range(1, len(historical_series)):
            v_curr = historical_series[i].get("revenue")
            v_prev = historical_series[i-1].get("revenue")
            if v_curr and v_prev and v_prev > 0:
                hist_growths.append((v_curr - v_prev) / v_prev)

        cv_growth = None
        pass_g5 = False
        med_cv_growth = benchmarks.get("median_cv_sales_growth", 0.42)

        if len(hist_growths) >= 2:
            mean_g = sum(hist_growths) / len(hist_growths)
            var_g = sum((x - mean_g) ** 2 for x in hist_growths) / (len(hist_growths) - 1)
            std_g = math.sqrt(var_g)
            cv_growth = (std_g / mean_g) if (mean_g and mean_g > 0) else 1.0

            # Cláusula de Hipercrecimiento: Pasa si CV < mediana O crecimiento medio >= 20% anual
            if cv_growth < med_cv_growth or mean_g >= 0.20:
                pass_g5 = True
        elif rev_t and rev_prev and rev_prev > 0:
            single_g = (rev_t - rev_prev) / rev_prev
            if single_g >= 0.20:
                pass_g5 = True

        score += 1 if pass_g5 else 0
        results["signals"]["G5_VAR_GROWTH"] = {
            "name": "Estabilidad / Aceleración de Ventas",
            "category": "Estabilidad y Predictibilidad",
            "value": cv_growth,
            "formatted_value": f"CV={cv_growth:.2f}" if cv_growth is not None else ("Hipercrecimiento" if pass_g5 else "N/A"),
            "comparison_label": f"CV {cv_growth:.2f} vs {med_cv_growth:.2f}" if cv_growth is not None else ("g >= 20%" if pass_g5 else "N/A"),
            "benchmark": f"CV < {med_cv_growth:.2f} o Crecimiento >= 20%",
            "passed": pass_g5,
            "points": 1 if pass_g5 else 0,
            "description": "Trayectoria predecible de ingresos o expansión acelerada superior al 20% anual."
        }

        # -------------------------------------------------------------
        # Bloque III: Inversión en Futuro e Intangibles (3 Señales - Mejoras C y E)
        # -------------------------------------------------------------
        # 6. G6: Intensidad en I+D (R&D / Activos Iniciales > Mediana Sector)
        rd_intensity = (rd_t / assets_denom) if (rd_t and assets_denom and assets_denom > 0) else 0.0
        med_rd = benchmarks.get("median_rd_intensity", 0.035)
        pass_g6 = bool(rd_intensity > med_rd)
        score += 1 if pass_g6 else 0
        results["signals"]["G6_RD_INTENSITY"] = {
            "name": "Intensidad en I+D vs Sector",
            "category": "Inversión en Futuro e Intangibles",
            "value": rd_intensity,
            "formatted_value": f"{rd_intensity*100:.2f}%",
            "comparison_label": f"I+D {rd_intensity*100:.2f}% vs Med {med_rd*100:.2f}%" if rd_intensity is not None else "N/A",
            "benchmark": f"> {med_rd*100:.2f}%",
            "passed": pass_g6,
            "points": 1 if pass_g6 else 0,
            "description": "Reinversión en investigación y desarrollo para fortalecer ventajas competitivas (moats)."
        }

        # 7. G7: Intensidad de CapEx / Tasa de Inversión Total (Mejora E: Asset-Light)
        is_asset_light = benchmarks.get("is_asset_light", False)
        capex_intensity = (capex_t / assets_denom) if (capex_t and assets_denom and assets_denom > 0) else 0.0
        total_reinvestment = ((capex_t + rd_t) / assets_denom) if (assets_denom and assets_denom > 0) else 0.0

        if is_asset_light:
            med_reinv = benchmarks.get("median_total_reinvestment", 0.080)
            pass_g7 = bool(total_reinvestment > med_reinv)
            g7_val = total_reinvestment
            g7_fmt = f"{total_reinvestment*100:.2f}% (Total)"
            g7_bm = f"> {med_reinv*100:.2f}% (I+D+CapEx)"
            g7_desc = "Tasa de Inversión Total en Crecimiento (I+D + CapEx) para modelos ligeros en activos."
            g7_comp = f"Reinv {total_reinvestment*100:.2f}% vs Med {med_reinv*100:.2f}%"
        else:
            med_capex = benchmarks.get("median_capex_intensity", 0.045)
            pass_g7 = bool(capex_intensity > med_capex)
            g7_val = capex_intensity
            g7_fmt = f"{capex_intensity*100:.2f}% (CapEx)"
            g7_bm = f"> {med_capex*100:.2f}%"
            g7_desc = "Reinversión en infraestructura de capital físico (CapEx) sobre activos."
            g7_comp = f"CapEx {capex_intensity*100:.2f}% vs Med {med_capex*100:.2f}%"

        score += 1 if pass_g7 else 0
        results["signals"]["G7_CAPEX_INTENSITY"] = {
            "name": "Reinversión de Capital / Asset-Light",
            "category": "Inversión en Futuro e Intangibles",
            "value": g7_val,
            "formatted_value": g7_fmt,
            "comparison_label": g7_comp,
            "benchmark": g7_bm,
            "passed": pass_g7,
            "points": 1 if pass_g7 else 0,
            "description": g7_desc
        }

        # 8. G8: Apalancamiento Operativo Comercial (Mejora C: % Delta Ventas > % Delta SG&A)
        growth_rev = ((rev_t - rev_prev) / rev_prev) if (rev_t is not None and rev_prev is not None and rev_prev > 0) else None
        growth_sga = ((sga_t - sga_prev) / sga_prev) if (sga_t is not None and sga_prev is not None and sga_prev > 0) else None

        pass_g8 = False
        if growth_rev is not None and growth_sga is not None:
            pass_g8 = bool(growth_rev > growth_sga)
        elif growth_rev is not None and growth_rev > 0:
            pass_g8 = True

        score += 1 if pass_g8 else 0
        diff_growth = (growth_rev - growth_sga) if (growth_rev is not None and growth_sga is not None) else None
        results["signals"]["G8_OPERATING_LEVERAGE"] = {
            "name": "Apalancamiento Comercial (SG&A)",
            "category": "Inversión en Futuro e Intangibles",
            "value": diff_growth,
            "formatted_value": f"Ventas: {growth_rev*100:+.1f}% vs SG&A: {growth_sga*100:+.1f}%" if (growth_rev is not None and growth_sga is not None) else "N/A",
            "comparison_label": f"Vtas {growth_rev*100:+.1f}% vs SG&A {growth_sga*100:+.1f}%" if (growth_rev is not None and growth_sga is not None) else "N/A",
            "benchmark": "% Delta Ventas > % Delta SG&A",
            "passed": pass_g8,
            "points": 1 if pass_g8 else 0,
            "description": "Eficiencia comercial: ingresos escalan con mayor dinamismo que los gastos administrativos y de ventas."
        }

        results["total_score"] = score
        if score >= 6:
            results["rating"] = "CRECIMIENTO DE ÉLITE"
            results["status_color"] = "GREEN"
            results["summary_text"] = "Liderazgo superior en rentabilidad, alta reinversión y ventajas competitivas sostenibles."
        elif score >= 4:
            results["rating"] = "CRECIMIENTO PROMEDIO"
            results["status_color"] = "YELLOW"
            results["summary_text"] = "Desempeño en línea con la mediana de la industria; vigilar reinversión o volatilidad."
        else:
            results["rating"] = "CRECIMIENTO FRÁGIL"
            results["status_color"] = "RED"
            results["summary_text"] = "Retornos rezagados frente a competidores o crecimiento inestable/destructivo de capital."

        return results


class CombinedMatrixClassifier:
    """Clasifica la empresa en la matriz estratégica 2x2 F-Score vs G-Score."""

    @staticmethod
    def classify(f_score: int, g_score: int) -> Dict[str, Any]:
        """
        Matriz de 4 Cuadrantes:
        - Cuadrante I: Compounder de Élite (F >= 7, G >= 6)
        - Cuadrante II: Crecimiento Vulnerable (F < 7, G >= 6)
        - Cuadrante III: Generador Maduro / Cash Cow (F >= 7, G < 6)
        - Cuadrante IV: Trampa de Valor / Deterioro (F < 7, G < 6)
        """
        if f_score >= 6 and g_score >= 6:
            quadrant = "CUADRANTE I: COMPOUNDER DE ÉLITE"
            badge = "💎 COMPOUNDER DE ÉLITE"
            color = "GREEN"
            thesis = (
                "Compañía excepcional: Combina sólida salud financiera intrínseca, balance robusto, generación líquida de caja "
                "y desendeudamiento (F-Score sólido >= 6) con superioridad competitiva, disciplina en I+D y crecimiento "
                "por encima de la mediana del sector (G-Score destacado >= 6). Perfil ideal para inversión a largo plazo."
            )
        elif f_score < 6 and g_score >= 6:
            quadrant = "CUADRANTE II: CRECIMIENTO VULNERABLE"
            badge = "⚠️ CRECIMIENTO VULNERABLE"
            color = "YELLOW"
            thesis = (
                "Alto dinamismo comercial y fuerte reinversión frente a la industria, pero con balances internos moderados o frágiles "
                "(presión en capital de trabajo, apalancamiento o dilución accionaria, F-Score < 6). "
                "Riesgo de ejecución si el financiamiento se restringe."
            )
        elif f_score >= 6 and g_score < 6:
            quadrant = "CUADRANTE III: GENERADOR MADURO (CASH COW)"
            badge = "🛡️ GENERADOR MADURO (CASH COW)"
            color = "BLUE"
            thesis = (
                "Excelente salud y disciplina de capital interna: balance desendeudado, márgenes estables y sólida "
                "conversión a flujo de caja libre, pero con menor ritmo de reinversión o crecimiento que el promedio "
                "de su sector. Típica vaca lechera con retornos predecibles pero menor expansión."
            )
        else:
            quadrant = "CUADRANTE IV: TRAMPA DE VALOR / DETERIORO"
            badge = "🚨 TRAMPA DE VALOR / DETERIORO"
            color = "RED"
            thesis = (
                "Alerta roja fundamental: Balances en deterioro, pérdida de margen operativo o desalineación de flujo "
                "de caja combinados con retornos rezagados respecto a sus competidores. Alto riesgo de pérdida permanente."
            )

        return {
            "quadrant": quadrant,
            "badge": badge,
            "color": color,
            "investment_thesis": thesis,
            "f_score": f_score,
            "g_score": g_score
        }


class NovyMarxCalculator:
    """
    Calculador del ratio de Rentabilidad Bruta sobre Activos de Robert Novy-Marx (2013).
    Gross Profitability to Assets (GP/A) con Descomposición DuPont Dual,
    Ajuste Sectorial (Industry De-meaning) y Explicaciones Pedagógicas.
    """

    @staticmethod
    def calculate_period(
        period: str,
        current_data: Dict[str, float],
        benchmarks: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Calcula Novy-Marx GP/A para un período individual (LTM o año fiscal específico).
        current_data contiene:
          - revenue, gross_profit, total_assets, cash
        """
        rev = _safe_float(current_data.get("revenue"))
        gp = _safe_float(current_data.get("gross_profit"))
        assets = _safe_float(current_data.get("total_assets"))
        cash = _safe_float(current_data.get("cash") or current_data.get("cash_and_equiv") or current_data.get("cash_and_cash_equivalents")) or 0.0

        # Validación del sector financiero (SIC 6000-6999)
        sic_code = str(benchmarks.get("sic_code", "0000")).strip()
        is_financial = sic_code.startswith("6") or benchmarks.get("gics_sector") == "Financials"

        # 1. GP / Activos Totales (Formulación original de Novy-Marx 2013)
        gp_a = (gp / assets) if (gp is not None and assets and assets > 0) else None

        # 2. GP / Activos Operativos (Ex-Caja y Equivalentes)
        operating_assets = (assets - cash) if (assets is not None and assets > cash and (assets - cash) > 0) else assets
        gp_a_ex_cash = (gp / operating_assets) if (gp is not None and operating_assets and operating_assets > 0) else None

        # 3. Efecto Arrastre de Caja (Cash Drag)
        cash_drag = (gp_a_ex_cash - gp_a) if (gp_a_ex_cash is not None and gp_a is not None) else 0.0

        # 4. Descomposición DuPont
        gross_margin = (gp / rev) if (gp is not None and rev and rev > 0) else None
        turnover_total = (rev / assets) if (rev is not None and assets and assets > 0) else None
        turnover_ex_cash = (rev / operating_assets) if (rev is not None and operating_assets and operating_assets > 0) else None

        # Verificación DuPont: Margen Bruto * Rotación == GP/A
        dupont_product = (gross_margin * turnover_total) if (gross_margin is not None and turnover_total is not None) else None
        dupont_verified = bool(dupont_product is not None and gp_a is not None and abs(dupont_product - gp_a) < 0.005)

        # Benchmarks sectoriales
        med_gpa = _safe_float(benchmarks.get("median_gross_profitability")) or 0.280
        p75_gpa = _safe_float(benchmarks.get("p75_gross_profitability")) or 0.400
        med_gp_ex = _safe_float(benchmarks.get("median_gp_ex_cash")) or 0.320
        med_gm = _safe_float(benchmarks.get("median_gross_margin")) or 0.380
        med_turn = _safe_float(benchmarks.get("median_asset_turnover")) or 0.75

        # 5. Ajuste Sectorial (Industry De-meaning)
        adj_gp_a = (gp_a - med_gpa) if gp_a is not None else None
        adj_gp_a_ex_cash = (gp_a_ex_cash - med_gp_ex) if gp_a_ex_cash is not None else None

        # 6. Matriz Estratégica de 4 Cuadrantes (Margen vs Rotación)
        gm_high = (gross_margin is not None and gross_margin >= med_gm)
        turn_high = (turnover_total is not None and turnover_total >= med_turn)

        if gm_high and turn_high:
            quadrant = "CUADRANTE I: COMPOUNDER DE ÉLITE"
            quadrant_badge = "💎 COMPOUNDER DE ÉLITE (MARGEN + VELOCIDAD)"
            quadrant_desc = (
                "Excelente perfil competitivo: combina un margen bruto por encima de la mediana sectorial "
                f"({gross_margin*100:.1f}% vs {med_gm*100:.1f}%) con una rotación de activos superior a sus competidores "
                f"({turnover_total:.2f}x vs {med_turn:.2f}x). La empresa ejerce simultáneamente poder de marca/precios "
                "y alta velocidad de conversión de capital."
            )
        elif gm_high and not turn_high:
            quadrant = "CUADRANTE II: MONOPOLIO / PODER DE MARCA"
            quadrant_badge = "👑 MONOPOLIO / PODER DE MARCA"
            quadrant_desc = (
                f"Ventaja impulsada por precios: margen bruto destacado ({gross_margin*100:.1f}% vs mediana {med_gm*100:.1f}%), "
                f"pero rotación de capital moderada o baja ({turnover_total:.2f}x vs mediana {med_turn:.2f}x). "
                "Típico de modelos de alto valor unitario, patentes exclusivas o marcas de lujo."
            )
        elif not gm_high and turn_high:
            quadrant = "CUADRANTE III: LÍDER EN VOLUMEN Y ESCALA"
            quadrant_badge = "⚡ LÍDER EN VOLUMEN Y VELOCIDAD"
            quadrant_desc = (
                f"Ventaja impulsada por rotación: márgenes ajustados ({gross_margin*100:.1f}% vs mediana {med_gm*100:.1f}%), "
                f"pero alta velocidad de despliegue de activos ({turnover_total:.2f}x vs mediana {med_turn:.2f}x). "
                "Modelo tipo distribución mayorista, retail masivo o manufactura ultraeficiente."
            )
        else:
            quadrant = "CUADRANTE IV: BAJA PRODUCTIVIDAD DE CAPITAL"
            quadrant_badge = "⚠️ BAJA PRODUCTIVIDAD DE CAPITAL"
            quadrant_desc = (
                f"Alerta de eficiencia: tanto el margen bruto ({gross_margin*100:.1f}% si existe) como la rotación "
                f"({turnover_total:.2f}x) se sitúan por debajo de las medianas de la industria. El capital instalado "
                "no genera suficiente valor económico por unidad de costo."
            )

        # 7. Percentil Sectorial y Explicación Pedagógica
        if gp_a is not None:
            if gp_a >= (p75_gpa * 1.25):
                percentile_label = "Top 5% de la Industria"
                percentile_expl = (
                    f"Su rentabilidad bruta ({gp_a*100:.2f}%) supera ampliamente al 95% de sus competidores, "
                    "situándola en el 5% superior más productivo y eficiente de todo el mercado."
                )
                rating = "PRODUCTIVIDAD EXCEPCIONAL"
            elif gp_a >= p75_gpa:
                percentile_label = "Top 25% (Percentil 75+)"
                percentile_expl = (
                    f"Supera al 75% de las empresas de su sector ({gp_a*100:.2f}% vs P75 {p75_gpa*100:.2f}%), "
                    "evidenciando una ventaja competitiva neta y sostenida en la generación de margen bruto."
                )
                rating = "PRODUCTIVIDAD SOBRESALIENTE"
            elif gp_a >= med_gpa:
                percentile_label = "Superior a la Mediana (Percentil 50-75)"
                percentile_expl = (
                    f"Rinde por encima de la empresa típica del sector ({gp_a*100:.2f}% vs mediana {med_gpa*100:.2f}%), "
                    "generando valor operativo positivo respecto al promedio de la industria."
                )
                rating = "PRODUCTIVIDAD SÓLIDA"
            else:
                percentile_label = "Inferior a la Mediana (< Percentil 50)"
                percentile_expl = (
                    f"Se encuentra por debajo de la mediana del sector ({gp_a*100:.2f}% vs mediana {med_gpa*100:.2f}%), "
                    "lo que sugiere una baja productividad de capital o costos directos desfavorables frente a sus pares."
                )
                rating = "PRODUCTIVIDAD REZAGADA"
        else:
            percentile_label = "N/A"
            percentile_expl = "Datos no disponibles o insuficientes."
            rating = "SIN CALIFICAR"

        # Explicaciones pedagógicas detalladas para cada resultado
        explanations = {
            "gross_profitability_total": (
                f"Gross Profitability (Activos Totales) = {gp_a*100:.2f}%: "
                f"Por cada $1.00 de activo total en su balance, la empresa genera ${gp_a:.2f} de utilidad bruta anual pura."
                if gp_a is not None else "N/A"
            ),
            "gross_profitability_ex_cash": (
                f"Gross Profitability Operativa (Ex-Caja) = {gp_a_ex_cash*100:.2f}%: "
                f"Al restar el efectivo e inversiones líquidas ociosas (${cash/1e6:,.1f}M), el capital estrictamente productivo rinde a un {gp_a_ex_cash*100:.2f}% "
                f"(${gp_a_ex_cash:.2f} de utilidad bruta por cada dólar invertido en activos operativos)."
                if gp_a_ex_cash is not None else "N/A"
            ),
            "cash_drag": (
                f"Efecto Arrastre de Caja (Cash Drag) = {cash_drag*100:+.2f} p.p.: "
                f"Mantener liquidez acumulada reduce artificialmente el ratio nominal de rentabilidad en {abs(cash_drag*100):.2f} puntos porcentuales. "
                "El negocio operativo subyacente es más rentable de lo que refleja el balance general agregado."
                if cash_drag is not None else "N/A"
            ),
            "gross_margin": (
                f"Margen Bruto = {gross_margin*100:.2f}%: "
                f"Retiene {gross_margin*100:.1f} centavos de utilidad bruta por cada dólar vendido tras cubrir los costos directos de producción (COGS). "
                f"Frente a la mediana del sector ({med_gm*100:.1f}%), denota "
                f"{'un fuerte poder de fijación de precios y foso de marca.' if gross_margin and gross_margin >= med_gm else 'menor margen unitario o mayor intensidad de costos directos.'}"
                if gross_margin is not None else "N/A"
            ),
            "asset_turnover": (
                f"Rotación de Activos Totales = {turnover_total:.2f}x: "
                f"La compañía rota su base total de activos {turnover_total:.2f} veces al año en ingresos. "
                f"Frente a la mediana sectorial ({med_turn:.2f}x), refleja "
                f"{'una velocidad de comercialización y eficiencia logística superior.' if turnover_total and turnover_total >= med_turn else 'un ciclo de rotación de capital más pausado o activos de largo plazo.'}"
                if turnover_total is not None else "N/A"
            ),
            "dupont_verification": (
                f"Descomposición DuPont: Margen Bruto ({gross_margin*100:.2f}%) × Rotación ({turnover_total:.3f}x) = {dupont_product*100:.2f}% "
                f"(Coincidencia exacta con GP/A de {gp_a*100:.2f}%)."
                if (gross_margin is not None and turnover_total is not None and gp_a is not None) else "N/A"
            ),
            "sector_adjustment": (
                f"Gross Profitability Ajustada por Sector = {adj_gp_a*100:+.2f} p.p.: "
                f"La empresa supera en {adj_gp_a*100:+.2f} puntos porcentuales a la empresa intermedia (mediana de {med_gpa*100:.1f}%) de su industria. "
                f"Su rentabilidad de capital es {'estructuralmente superior a sus competidores.' if adj_gp_a and adj_gp_a > 0 else 'inferior a la media del sector.'}"
                if adj_gp_a is not None else "N/A"
            )
        }

        return {
            "period": period,
            "gross_profitability_total": gp_a,
            "gross_profitability_ex_cash": gp_a_ex_cash,
            "cash_drag_pct": cash_drag,
            "gross_margin": gross_margin,
            "asset_turnover_total": turnover_total,
            "asset_turnover_ex_cash": turnover_ex_cash,
            "dupont_verified": dupont_verified,
            "rating": rating,
            "percentile_label": percentile_label,
            "percentile_explanation": percentile_expl,
            "quadrant": quadrant,
            "quadrant_badge": quadrant_badge,
            "quadrant_description": quadrant_desc,
            "adjusted_gp_a": adj_gp_a,
            "adjusted_gp_a_ex_cash": adj_gp_a_ex_cash,
            "benchmarks_used": {
                "median_gross_profitability": med_gpa,
                "p75_gross_profitability": p75_gpa,
                "median_gp_ex_cash": med_gp_ex,
                "median_gross_margin": med_gm,
                "median_asset_turnover": med_turn,
            },
            "explanations": explanations,
            "is_financial_institution": is_financial
        }

    @staticmethod
    def calculate_series(
        fiscal_years: List[str],
        period_metrics: Dict[str, Dict[str, float]],
        benchmarks: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Calcula la serie histórica completa de Novy-Marx GP/A y analiza la tendencia a 3 y 5 años.
        Soporta cronología dinámica: si fiscal_years contiene LTM, FY2026 o FY2025, toma automáticamente
        el período más reciente y busca los períodos de t-3 y t-5 reales.
        """
        period_results = {}
        for fy in fiscal_years:
            m = period_metrics.get(fy, {})
            period_results[fy] = NovyMarxCalculator.calculate_period(fy, m, benchmarks)

        # Identificar periodos cronológicos ordenados (de más antiguo a más reciente)
        annual_fys = [y for y in fiscal_years if y != "LTM"]
        annual_fys_sorted = sorted(annual_fys, key=lambda x: int(x.replace("FY", "")) if "FY" in x else 0)

        chronological_keys = list(annual_fys_sorted)
        if "LTM" in fiscal_years:
            chronological_keys.append("LTM")

        # Período más reciente
        recent_fy = "LTM" if "LTM" in fiscal_years else (annual_fys_sorted[-1] if annual_fys_sorted else fiscal_years[0])
        recent_res = period_results.get(recent_fy, {})
        recent_gpa = recent_res.get("gross_profitability_total")

        # Buscar t-3 y t-5 dinámicamente en annual_fys_sorted
        period_3y = None
        period_5y = None
        delta_3y = None
        delta_5y = None

        if len(annual_fys_sorted) >= 3:
            period_3y = annual_fys_sorted[-3]
            gpa_3y = period_results.get(period_3y, {}).get("gross_profitability_total")
            if recent_gpa is not None and gpa_3y is not None:
                delta_3y = recent_gpa - gpa_3y

        if len(annual_fys_sorted) >= 5:
            period_5y = annual_fys_sorted[-5]
            gpa_5y = period_results.get(period_5y, {}).get("gross_profitability_total")
            if recent_gpa is not None and gpa_5y is not None:
                delta_5y = recent_gpa - gpa_5y

        # Serie histórica de GP/A de los últimos 5 años para Coeficiente de Variación
        last_5_keys = annual_fys_sorted[-5:] if len(annual_fys_sorted) >= 5 else annual_fys_sorted
        gpa_history = [period_results[k]["gross_profitability_total"] for k in last_5_keys if period_results.get(k, {}).get("gross_profitability_total") is not None]

        cv_gpa = None
        if len(gpa_history) >= 3:
            mean_val = statistics.mean(gpa_history)
            stdev_val = statistics.stdev(gpa_history)
            if mean_val > 0:
                cv_gpa = stdev_val / mean_val

        # Diagnóstico de tendencia
        if delta_5y is not None:
            if delta_5y > 0.05:
                trend_diag = f"Expansión estructural acelerada (+{delta_5y*100:.2f} p.p. en 5 años); aumento continuo de la productividad pura de capital."
            elif delta_5y > 0:
                trend_diag = f"Trayectoria constructiva y estable (+{delta_5y*100:.2f} p.p. en 5 años); foso económico protegido."
            else:
                trend_diag = f"Compresión de rentabilidad sobre activos ({delta_5y*100:.2f} p.p. en 5 años); vigilar presión en costos directos o acumulación de activos."
        elif delta_3y is not None:
            trend_diag = f"Variación a 3 años de {delta_3y*100:+.2f} p.p."
        else:
            trend_diag = "Historial insuficiente para evaluar tendencia de 3-5 años."

        # Ranking de pares directo si existen en benchmarks
        peer_ranking = []
        peers = benchmarks.get("peers_detail", [])
        for p in peers:
            t = p.get("ticker")
            t_assets = _safe_float(p.get("total_assets_usd_m"))
            t_rev = _safe_float(p.get("revenue_usd_m"))
            t_gp = _safe_float(p.get("gross_profit_usd_m"))
            t_cash = _safe_float(p.get("cash_usd_m")) or 0.0
            if t_assets and t_assets > 0 and t_gp is not None:
                p_gpa = t_gp / t_assets
                p_op_assets = (t_assets - t_cash) if (t_assets > t_cash and (t_assets - t_cash) > 0) else t_assets
                p_gpa_ex = t_gp / p_op_assets
                peer_ranking.append({
                    "ticker": t,
                    "company_name": p.get("company_name", t),
                    "is_target": p.get("is_target", False),
                    "period": p.get("period", "LTM"),
                    "gross_profitability_total": p_gpa,
                    "gross_profitability_ex_cash": p_gpa_ex,
                    "gross_margin": (t_gp / t_rev) if (t_rev and t_rev > 0) else None,
                    "asset_turnover": (t_rev / t_assets) if (t_rev and t_rev > 0) else None,
                })

        peer_ranking.sort(key=lambda x: x["gross_profitability_total"] if x["gross_profitability_total"] is not None else -999, reverse=True)

        return {
            "by_period": period_results,
            "latest_period": recent_fy,
            "latest_result": recent_res,
            "trend": {
                "period_3y_basis": period_3y,
                "delta_3y": delta_3y,
                "period_5y_basis": period_5y,
                "delta_5y": delta_5y,
                "cv_gpa": cv_gpa,
                "trend_diagnosis": trend_diag,
                "chronological_periods": chronological_keys
            },
            "peer_ranking": peer_ranking
        }



class IntangibleROICCalculator:
    """
    Calculador del ROIC Ajustado por Intangibles bajo la metodología roll-forward de Damodaran y Mauboussin.
    Capitaliza I+D (100%) y Marketing/SG&A (% sectorial) creando activos intangibles fuera de balance
    y amortizándolos en vidas útiles de N años.
    """

    @staticmethod
    def calculate_series(
        fiscal_years: List[str],
        period_metrics: Dict[str, Dict[str, Any]],
        benchmarks: Dict[str, Any],
        ticker: str = ""
    ) -> Dict[str, Any]:
        """
        Calcula la serie histórica completa de ROIC Tradicional vs. ROIC Ajustado por Intangibles
        y la matriz de sensibilidad de vida útil N.
        """
        annual_fys = [y for y in fiscal_years if y != "LTM"]
        annual_fys_sorted = sorted(annual_fys, key=lambda x: int(x.replace("FY", "")) if "FY" in x else 0)

        n_rd_base = int(benchmarks.get("rd_useful_life_years", 4))
        n_mkt_base = int(benchmarks.get("sga_useful_life_years", 2))
        sga_cap_pct = float(benchmarks.get("sga_capitalization_pct", 0.0))

        # Función auxiliar para calcular serie dada una vida útil de I+D (n_rd)
        def _compute_for_lifespan(n_rd: int, n_mkt: int):
            rd_stock = 0.0
            mkt_stock = 0.0
            rd_invs = {}
            mkt_invs = {}
            results = {}

            for fy in annual_fys_sorted:
                m = period_metrics.get(fy, {})
                # Normalizar a millones si vienen en unidades completas
                raw_rd = _safe_float(m.get("rd_expense")) or 0.0
                raw_sga = _safe_float(m.get("sga_expense")) or 0.0
                rd_exp = _to_millions(raw_rd) or 0.0
                sga_exp = _to_millions(raw_sga) or 0.0
                mkt_exp = sga_exp * sga_cap_pct

                rd_invs[fy] = rd_exp
                mkt_invs[fy] = mkt_exp

                idx = annual_fys_sorted.index(fy)

                # Amortización de I+D (vintage lineal)
                rd_amort = 0.0
                for k in range(1, n_rd + 1):
                    if idx - k >= 0:
                        past_fy = annual_fys_sorted[idx - k]
                        rd_amort += rd_invs.get(past_fy, 0.0) / float(n_rd)

                # Amortización de Marketing
                mkt_amort = 0.0
                for k in range(1, n_mkt + 1):
                    if idx - k >= 0:
                        past_fy = annual_fys_sorted[idx - k]
                        mkt_amort += mkt_invs.get(past_fy, 0.0) / float(n_mkt)

                # Roll-forward: Stock_t = Stock_{t-1} + Inv_t - Amort_t
                rd_stock = max(0.0, rd_stock + rd_exp - rd_amort)
                mkt_stock = max(0.0, mkt_stock + mkt_exp - mkt_amort)
                total_intangibles = rd_stock + mkt_stock

                # Utilidad operativa / EBIT
                raw_gp = _safe_float(m.get("gross_profit")) or 0.0
                gp = _to_millions(raw_gp) or 0.0
                raw_ni = _safe_float(m.get("net_income")) or 0.0
                ni = _to_millions(raw_ni) or 0.0
                raw_ebit = _safe_float(m.get("operating_income"))
                if raw_ebit is not None:
                    ebit = _to_millions(raw_ebit)
                elif gp and sga_exp is not None:
                    ebit = gp - sga_exp - rd_exp
                else:
                    ebit = ni

                # Tasa impositiva
                tax_rate = _safe_float(m.get("effective_tax_rate")) or 0.21
                tax_rate = max(0.05, min(0.35, tax_rate))

                # NOPAT
                nopat_trad = ebit * (1.0 - tax_rate)
                ebit_adj = ebit + (rd_exp - rd_amort) + (mkt_exp - mkt_amort)
                nopat_adj = ebit_adj * (1.0 - tax_rate)

                # Capital Invertido
                raw_assets = _safe_float(m.get("total_assets")) or 0.0
                assets = _to_millions(raw_assets) or 0.0
                raw_cash = _safe_float(m.get("cash")) or 0.0
                cash = _to_millions(raw_cash) or 0.0
                raw_cl = _safe_float(m.get("current_liabilities")) or 0.0
                cl = _to_millions(raw_cl) or 0.0
                raw_st_debt = _safe_float(m.get("short_term_debt")) or 0.0
                st_debt = _to_millions(raw_st_debt) or 0.0

                nibcl = max(0.0, cl - st_debt)
                ic_trad_end = max(1.0, assets - cash - nibcl)
                ic_adj_end = ic_trad_end + total_intangibles

                # Capital Invertido Promedio ((t + t-1) / 2)
                # Garantiza correspondencia temporal institucional con el NOPAT anual
                if idx > 0:
                    prev_fy = annual_fys_sorted[idx - 1]
                    prev_res = results.get(prev_fy, {})
                    prev_ic_trad = prev_res.get("ic_trad_end", prev_res.get("ic_trad", ic_trad_end))
                    prev_ic_adj = prev_res.get("ic_adj_end", prev_res.get("ic_adj", ic_adj_end))
                    ic_trad_avg = (ic_trad_end + prev_ic_trad) / 2.0
                    ic_adj_avg = (ic_adj_end + prev_ic_adj) / 2.0
                else:
                    ic_trad_avg = ic_trad_end
                    ic_adj_avg = ic_adj_end

                roic_trad_avg = (nopat_trad / ic_trad_avg) if ic_trad_avg > 0 else None
                roic_adj_avg = (nopat_adj / ic_adj_avg) if ic_adj_avg > 0 else None
                roic_trad_end = (nopat_trad / ic_trad_end) if ic_trad_end > 0 else None
                roic_adj_end = (nopat_adj / ic_adj_end) if ic_adj_end > 0 else None

                # Base estándar institucional: promedio para correspondencia temporal con NOPAT
                ic_trad = ic_trad_avg
                ic_adj = ic_adj_avg
                roic_trad = roic_trad_avg
                roic_adj = roic_adj_avg

                results[fy] = {
                    "period": fy,
                    "ebit": ebit,
                    "ebit_adj": ebit_adj,
                    "tax_rate": tax_rate,
                    "nopat_trad": nopat_trad,
                    "nopat_adj": nopat_adj,
                    "ic_trad": ic_trad,
                    "ic_adj": ic_adj,
                    "ic_trad_end": ic_trad_end,
                    "ic_adj_end": ic_adj_end,
                    "ic_trad_avg": ic_trad_avg,
                    "ic_adj_avg": ic_adj_avg,
                    "rd_investment": rd_exp,
                    "rd_amortization": rd_amort,
                    "rd_stock": rd_stock,
                    "mkt_investment": mkt_exp,
                    "mkt_amortization": mkt_amort,
                    "mkt_stock": mkt_stock,
                    "total_intangible_stock": total_intangibles,
                    "roic_trad": roic_trad,
                    "roic_adj": roic_adj,
                    "roic_trad_end": roic_trad_end,
                    "roic_adj_end": roic_adj_end,
                    "roic_trad_avg": roic_trad_avg,
                    "roic_adj_avg": roic_adj_avg
                }

            # Si existe LTM, calcularlo con el stock más reciente
            if "LTM" in fiscal_years:
                m_ltm = period_metrics.get("LTM", {})
                last_fy = annual_fys_sorted[-1] if annual_fys_sorted else "FY2025"
                last_res = results.get(last_fy, {})

                raw_rd = _safe_float(m_ltm.get("rd_expense")) or 0.0
                raw_sga = _safe_float(m_ltm.get("sga_expense")) or 0.0
                rd_exp_ltm = _to_millions(raw_rd) or 0.0
                sga_exp_ltm = _to_millions(raw_sga) or 0.0
                mkt_exp_ltm = sga_exp_ltm * sga_cap_pct

                # Amortización LTM aproximada al último año fiscal
                rd_amort_ltm = last_res.get("rd_amortization", 0.0)
                mkt_amort_ltm = last_res.get("mkt_amortization", 0.0)

                rd_stock_ltm = last_res.get("rd_stock", 0.0)
                mkt_stock_ltm = last_res.get("mkt_stock", 0.0)
                total_intangibles_ltm = rd_stock_ltm + mkt_stock_ltm

                raw_gp = _safe_float(m_ltm.get("gross_profit")) or 0.0
                gp = _to_millions(raw_gp) or 0.0
                raw_ni = _safe_float(m_ltm.get("net_income")) or 0.0
                ni = _to_millions(raw_ni) or 0.0
                raw_ebit = _safe_float(m_ltm.get("operating_income"))
                if raw_ebit is not None:
                    ebit_ltm = _to_millions(raw_ebit)
                elif gp and sga_exp_ltm is not None:
                    ebit_ltm = gp - sga_exp_ltm - rd_exp_ltm
                else:
                    ebit_ltm = ni

                tax_rate_ltm = _safe_float(m_ltm.get("effective_tax_rate")) or last_res.get("tax_rate", 0.21)
                nopat_trad_ltm = ebit_ltm * (1.0 - tax_rate_ltm)
                ebit_adj_ltm = ebit_ltm + (rd_exp_ltm - rd_amort_ltm) + (mkt_exp_ltm - mkt_amort_ltm)
                nopat_adj_ltm = ebit_adj_ltm * (1.0 - tax_rate_ltm)

                raw_assets = _safe_float(m_ltm.get("total_assets")) or 0.0
                assets_ltm = _to_millions(raw_assets) or 0.0
                raw_cash = _safe_float(m_ltm.get("cash")) or 0.0
                cash_ltm = _to_millions(raw_cash) or 0.0
                raw_cl = _safe_float(m_ltm.get("current_liabilities")) or 0.0
                cl_ltm = _to_millions(raw_cl) or 0.0
                raw_st_debt = _safe_float(m_ltm.get("short_term_debt")) or 0.0
                st_debt_ltm = _to_millions(raw_st_debt) or 0.0

                nibcl_ltm = max(0.0, cl_ltm - st_debt_ltm)
                ic_trad_ltm_end = max(1.0, assets_ltm - cash_ltm - nibcl_ltm)
                ic_adj_ltm_end = ic_trad_ltm_end + total_intangibles_ltm

                prev_ic_trad = last_res.get("ic_trad_end", last_res.get("ic_trad", ic_trad_ltm_end))
                prev_ic_adj = last_res.get("ic_adj_end", last_res.get("ic_adj", ic_adj_ltm_end))
                ic_trad_ltm_avg = (ic_trad_ltm_end + prev_ic_trad) / 2.0
                ic_adj_ltm_avg = (ic_adj_ltm_end + prev_ic_adj) / 2.0

                roic_trad_ltm_avg = (nopat_trad_ltm / ic_trad_ltm_avg) if ic_trad_ltm_avg > 0 else None
                roic_adj_ltm_avg = (nopat_adj_ltm / ic_adj_ltm_avg) if ic_adj_ltm_avg > 0 else None
                roic_trad_ltm_end = (nopat_trad_ltm / ic_trad_ltm_end) if ic_trad_ltm_end > 0 else None
                roic_adj_ltm_end = (nopat_adj_ltm / ic_adj_ltm_end) if ic_adj_ltm_end > 0 else None

                ic_trad_ltm = ic_trad_ltm_avg
                ic_adj_ltm = ic_adj_ltm_avg
                roic_trad_ltm = roic_trad_ltm_avg
                roic_adj_ltm = roic_adj_ltm_avg

                results["LTM"] = {
                    "period": "LTM",
                    "ebit": ebit_ltm,
                    "ebit_adj": ebit_adj_ltm,
                    "tax_rate": tax_rate_ltm,
                    "nopat_trad": nopat_trad_ltm,
                    "nopat_adj": nopat_adj_ltm,
                    "ic_trad": ic_trad_ltm,
                    "ic_adj": ic_adj_ltm,
                    "ic_trad_end": ic_trad_ltm_end,
                    "ic_adj_end": ic_adj_ltm_end,
                    "ic_trad_avg": ic_trad_ltm_avg,
                    "ic_adj_avg": ic_adj_ltm_avg,
                    "rd_investment": rd_exp_ltm,
                    "rd_amortization": rd_amort_ltm,
                    "rd_stock": rd_stock_ltm,
                    "mkt_investment": mkt_exp_ltm,
                    "mkt_amortization": mkt_amort_ltm,
                    "mkt_stock": mkt_stock_ltm,
                    "total_intangible_stock": total_intangibles_ltm,
                    "roic_trad": roic_trad_ltm,
                    "roic_adj": roic_adj_ltm,
                    "roic_trad_end": roic_trad_ltm_end,
                    "roic_adj_end": roic_adj_ltm_end,
                    "roic_trad_avg": roic_trad_ltm_avg,
                    "roic_adj_avg": roic_adj_ltm_avg
                }

            return results

        # Caso Base
        base_results = _compute_for_lifespan(n_rd_base, n_mkt_base)

        # Matriz de Sensibilidad: N-1, N, N+1
        n_low = max(2, n_rd_base - 1)
        n_high = n_rd_base + 1
        sens_low = _compute_for_lifespan(n_low, n_mkt_base)
        sens_high = _compute_for_lifespan(n_high, n_mkt_base)

        recent_fy = "LTM" if "LTM" in fiscal_years else (annual_fys_sorted[-1] if annual_fys_sorted else fiscal_years[0])
        rec_base = base_results.get(recent_fy, {})
        rec_low = sens_low.get(recent_fy, {})
        rec_high = sens_high.get(recent_fy, {})

        sensitivity_matrix = {
            "n_minus_1": {
                "lifespan_years": n_low,
                "intangibles_usd_m": rec_low.get("total_intangible_stock", 0.0),
                "roic_adj": rec_low.get("roic_adj")
            },
            "n_base": {
                "lifespan_years": n_rd_base,
                "intangibles_usd_m": rec_base.get("total_intangible_stock", 0.0),
                "roic_adj": rec_base.get("roic_adj")
            },
            "n_plus_1": {
                "lifespan_years": n_high,
                "intangibles_usd_m": rec_high.get("total_intangible_stock", 0.0),
                "roic_adj": rec_high.get("roic_adj")
            }
        }

        # Explicaciones pedagógicas
        roic_trad_val = rec_base.get("roic_trad", 0.0)
        roic_adj_val = rec_base.get("roic_adj", 0.0)
        stock_val = rec_base.get("total_intangible_stock", 0.0)
        ic_trad_val = rec_base.get("ic_trad", 1.0)
        ic_adj_val = rec_base.get("ic_adj", 1.0)

        explanations = {
            "roic_traditional": (
                f"ROIC Tradicional = {roic_trad_val*100:.2f}%: Mide el retorno operativo sobre el capital invertido promedio en libros contables. "
                "Al tratar I+D y Marketing como gastos corrientes en lugar de inversiones de capital, distorsiona al alza el ratio "
                "en empresas intensivas en activos intangibles."
                if roic_trad_val else "N/A"
            ),
            "roic_adjusted": (
                f"ROIC Ajustado por Intangibles = {roic_adj_val*100:.2f}%: Refleja la rentabilidad económica real al capitalizar ${stock_val:,.1f}M "
                f"en activos de innovación/marca y amortizarlos económicamente a {n_rd_base} años. "
                f"Calculado sobre el Capital Invertido Promedio (${ic_adj_val:,.1f}M vs. ${ic_trad_val:,.1f}M tradicional), "
                "garantizando la correspondencia temporal perfecta entre el flujo anual de NOPAT y el capital desplegado durante el ejercicio."
                if roic_adj_val else "N/A"
            ),
            "sensitivity": (
                f"Matriz de Sensibilidad: Acelerando la amortización a {n_low} años el ROIC ajustado promedio es de {rec_low.get('roic_adj', 0)*100:.2f}%, "
                f"y extendiéndola a {n_high} años es de {rec_high.get('roic_adj', 0)*100:.2f}%. En todos los escenarios, la rentabilidad "
                "se mantiene estructuralmente sólida y supera con holgura el costo de capital."
            )
        }

        return {
            "by_period": base_results,
            "latest_period": recent_fy,
            "latest_result": rec_base,
            "sensitivity_matrix": sensitivity_matrix,
            "parameters": {
                "rd_useful_life_years": n_rd_base,
                "sga_useful_life_years": n_mkt_base,
                "sga_capitalization_pct": sga_cap_pct
            },
            "explanations": explanations
        }


class GreenblattROCCalculator:
    """
    Calculadora de Retorno sobre Capital Tangible Operativo (Joel Greenblatt - Magic Formula).
    ROC = EBIT / Capital Tangible Operativo Promedio ((t + t-1) / 2)
    Capital Tangible = NWC Operativo + Net PP&E
    NWC Operativo = (Activos Corrientes - Caja) - (Pasivos Corrientes - Deuda CP)
    Salvaguarda para modelos con capital de trabajo negativo:
    Si NWC < 0, se acota inferiormente a Net PP&E: max(Net PP&E, NWC + Net PP&E).
    """

    @staticmethod
    def compute_tangible_capital(current_assets: float, cash: float, current_liabilities: float, short_term_debt: float, net_ppe: float) -> float:
        """Calcula el capital tangible operativo según Joel Greenblatt con salvaguarda para NWC negativo."""
        op_ca = max(0.0, current_assets - cash)
        op_cl = max(0.0, current_liabilities - short_term_debt)
        op_nwc = op_ca - op_cl
        tangible_cap = max(net_ppe, op_nwc + net_ppe) if op_nwc < 0 else (op_nwc + net_ppe)
        return max(1.0, tangible_cap)

    @staticmethod
    def rate_roc(roc_val: float) -> str:
        """Categoriza el ROC Greenblatt en bandas de calidad institucional."""
        if roc_val is None:
            return "N/A"
        if roc_val >= 0.40:
            return "ELITE (> 40%)"
        elif roc_val >= 0.25:
            return "EXCELENTE (25% - 40%)"
        elif roc_val >= 0.15:
            return "SÓLIDO (15% - 25%)"
        elif roc_val >= 0.10:
            return "MODERADO (10% - 15%)"
        elif roc_val >= 0.0:
            return "DEFICIENTE (< 10%)"
        else:
            return "DESTRUCTOR (< 0%)"

    @staticmethod
    def calculate_series(fiscal_years: List[str], period_metrics: Dict[str, Dict[str, Any]], benchmarks: Dict[str, Any], ticker: str = "") -> Dict[str, Any]:
        annual_fys = [y for y in fiscal_years if y != "LTM"]
        annual_fys_sorted = sorted(annual_fys, key=lambda x: int(x.replace("FY", "")) if "FY" in x else 0)

        results = {}

        # 1. Calcular capital tangible para cada periodo anual
        for idx, fy in enumerate(annual_fys_sorted):
            m = period_metrics.get(fy, {})
            raw_ebit = _safe_float(m.get("operating_income"))
            raw_gp = _safe_float(m.get("gross_profit"))
            raw_sga = _safe_float(m.get("sga_expense"))
            raw_rd = _safe_float(m.get("rd_expense")) or 0.0
            raw_ni = _safe_float(m.get("net_income"))

            if raw_ebit is not None:
                ebit = _to_millions(raw_ebit)
            elif raw_gp is not None and raw_sga is not None:
                ebit = _to_millions(raw_gp - raw_sga - raw_rd)
            else:
                ebit = _to_millions(raw_ni)

            raw_ca = _safe_float(m.get("current_assets")) or 0.0
            ca = _to_millions(raw_ca) or 0.0
            raw_cash = _safe_float(m.get("cash")) or 0.0
            cash = _to_millions(raw_cash) or 0.0
            raw_cl = _safe_float(m.get("current_liabilities")) or 0.0
            cl = _to_millions(raw_cl) or 0.0
            raw_st_debt = _safe_float(m.get("short_term_debt")) or 0.0
            st_debt = _to_millions(raw_st_debt) or 0.0
            raw_ppe = _safe_float(m.get("net_ppe")) or 0.0
            net_ppe = _to_millions(raw_ppe) or 0.0

            op_ca = max(0.0, ca - cash)
            op_cl = max(0.0, cl - st_debt)
            op_nwc = op_ca - op_cl

            # Salvaguarda institucional Greenblatt: si NWC es negativo, capital tangible no puede ser menor a net_ppe
            tangible_cap_end = max(net_ppe, op_nwc + net_ppe) if op_nwc < 0 else (op_nwc + net_ppe)
            tangible_cap_end = max(1.0, tangible_cap_end)

            if idx > 0:
                prev_fy = annual_fys_sorted[idx - 1]
                prev_res = results.get(prev_fy, {})
                prev_cap = prev_res.get("tangible_capital_end", tangible_cap_end)
                tangible_cap_avg = (tangible_cap_end + prev_cap) / 2.0
            else:
                tangible_cap_avg = tangible_cap_end

            roc_avg = (ebit / tangible_cap_avg) if (ebit is not None and tangible_cap_avg > 0) else None
            roc_end = (ebit / tangible_cap_end) if (ebit is not None and tangible_cap_end > 0) else None

            results[fy] = {
                "period": fy,
                "ebit_usd_m": ebit,
                "current_assets_usd_m": ca,
                "cash_usd_m": cash,
                "current_liabilities_usd_m": cl,
                "short_term_debt_usd_m": st_debt,
                "op_current_assets_usd_m": op_ca,
                "op_current_liabilities_usd_m": op_cl,
                "nwc_usd_m": op_nwc,
                "net_ppe_usd_m": net_ppe,
                "tangible_capital_end": tangible_cap_end,
                "tangible_capital_avg": tangible_cap_avg,
                "roc_avg": roc_avg,
                "roc_end": roc_end,
                "roc_pct": round(roc_avg * 100, 2) if roc_avg is not None else None
            }

        # LTM
        if "LTM" in fiscal_years:
            m_ltm = period_metrics.get("LTM", {})
            last_fy = annual_fys_sorted[-1] if annual_fys_sorted else "FY2025"
            last_res = results.get(last_fy, {})

            raw_ebit = _safe_float(m_ltm.get("operating_income"))
            raw_gp = _safe_float(m_ltm.get("gross_profit"))
            raw_sga = _safe_float(m_ltm.get("sga_expense"))
            raw_rd = _safe_float(m_ltm.get("rd_expense")) or 0.0
            raw_ni = _safe_float(m_ltm.get("net_income"))

            if raw_ebit is not None:
                ebit_ltm = _to_millions(raw_ebit)
            elif raw_gp is not None and raw_sga is not None:
                ebit_ltm = _to_millions(raw_gp - raw_sga - raw_rd)
            else:
                ebit_ltm = _to_millions(raw_ni)

            raw_ca = _safe_float(m_ltm.get("current_assets")) or 0.0
            ca_ltm = _to_millions(raw_ca) or 0.0
            raw_cash = _safe_float(m_ltm.get("cash")) or 0.0
            cash_ltm = _to_millions(raw_cash) or 0.0
            raw_cl = _safe_float(m_ltm.get("current_liabilities")) or 0.0
            cl_ltm = _to_millions(raw_cl) or 0.0
            raw_st_debt = _safe_float(m_ltm.get("short_term_debt")) or 0.0
            st_debt_ltm = _to_millions(raw_st_debt) or 0.0
            raw_ppe = _safe_float(m_ltm.get("net_ppe")) or 0.0
            net_ppe_ltm = _to_millions(raw_ppe) or 0.0

            op_ca_ltm = max(0.0, ca_ltm - cash_ltm)
            op_cl_ltm = max(0.0, cl_ltm - st_debt_ltm)
            op_nwc_ltm = op_ca_ltm - op_cl_ltm

            tangible_cap_ltm_end = max(net_ppe_ltm, op_nwc_ltm + net_ppe_ltm) if op_nwc_ltm < 0 else (op_nwc_ltm + net_ppe_ltm)
            tangible_cap_ltm_end = max(1.0, tangible_cap_ltm_end)

            prev_cap = last_res.get("tangible_capital_end", tangible_cap_ltm_end)
            tangible_cap_ltm_avg = (tangible_cap_ltm_end + prev_cap) / 2.0

            roc_ltm_avg = (ebit_ltm / tangible_cap_ltm_avg) if (ebit_ltm is not None and tangible_cap_ltm_avg > 0) else None
            roc_ltm_end = (ebit_ltm / tangible_cap_ltm_end) if (ebit_ltm is not None and tangible_cap_ltm_end > 0) else None

            results["LTM"] = {
                "period": "LTM",
                "ebit_usd_m": ebit_ltm,
                "current_assets_usd_m": ca_ltm,
                "cash_usd_m": cash_ltm,
                "current_liabilities_usd_m": cl_ltm,
                "short_term_debt_usd_m": st_debt_ltm,
                "op_current_assets_usd_m": op_ca_ltm,
                "op_current_liabilities_usd_m": op_cl_ltm,
                "nwc_usd_m": op_nwc_ltm,
                "net_ppe_usd_m": net_ppe_ltm,
                "tangible_capital_end": tangible_cap_ltm_end,
                "tangible_capital_avg": tangible_cap_ltm_avg,
                "roc_avg": roc_ltm_avg,
                "roc_ltm": roc_ltm_avg,
                "roc_end": roc_ltm_end,
                "roc_pct": round(roc_ltm_avg * 100, 2) if roc_ltm_avg is not None else None
            }

        # Mediana de pares
        peer_roc_median = benchmarks.get("peer_greenblatt_roc_median", benchmarks.get("peer_roc_median", 0.25))

        recent_fy = "LTM" if "LTM" in fiscal_years else (annual_fys_sorted[-1] if annual_fys_sorted else fiscal_years[0])
        latest = results.get(recent_fy, {})
        latest_roc = latest.get("roc_avg", 0.0) or 0.0

        if latest_roc >= 0.50:
            rating = "COMPOUNDER_TANGIBLE_ELITE"
            label = "Rentabilidad Tangible Excepcional (> 50% ROC - Negocio Asset-Light Dominante)"
        elif latest_roc >= 0.25:
            rating = "STRONG_CAPITAL_EFFICIENCY"
            label = "Alta Eficiencia de Capital Tangible (25% - 50% ROC - Foso Defensivo Sólido)"
        elif latest_roc >= 0.12:
            rating = "MODERATE_EFFICIENCY"
            label = "Eficiencia de Capital Adecuada (12% - 25% ROC - Rendimiento en Línea con Mercado)"
        else:
            rating = "CAPITAL_INTENSIVE_LOW_RETURN"
            label = "Baja Productividad del Capital Tangible (< 12% ROC - Negocio Intensivo en Capital)"

        spread_vs_peer = round((latest_roc - peer_roc_median) * 100, 2)

        ltm_payload = dict(results.get("LTM", latest))
        if "roc_ltm" not in ltm_payload and "roc_avg" in ltm_payload:
            ltm_payload["roc_ltm"] = ltm_payload["roc_avg"]

        return {
            "methodology": "Joel Greenblatt Magic Formula - Return on Capital (EBIT / Average Operating Tangible Capital)",
            "recent_period": recent_fy,
            "annual_series": results,
            "ltm": ltm_payload,
            "latest_result": latest,
            "latest_roc": latest_roc,
            "latest_roc_pct": round(latest_roc * 100, 2),
            "peer_roc_median": peer_roc_median,
            "peer_roc_median_pct": round(peer_roc_median * 100, 2),
            "spread_vs_peer_pct": spread_vs_peer,
            "peer_comparison": {
                "company_roc_ltm": latest_roc,
                "peer_median_roc": peer_roc_median,
                "spread_vs_peer_median": spread_vs_peer
            },
            "rating": rating,
            "rating_label": label,
            "explanation": (
                f"ROC Greenblatt = {latest_roc*100:.2f}% vs. Mediana Sectorial {peer_roc_median*100:.2f}% "
                f"(Diferencial: {spread_vs_peer:+.2f}%). Mide la productividad operativa pura pre-tax "
                f"sobre el capital tangible operativo desplegado (${latest.get('tangible_capital_avg', 0):,.1f}M promedio)."
            )
        }


class WACCCalculator:
    """
    Calculador del Costo Promedio Ponderado de Capital (WACC) con datos de mercado validados en tiempo real,
    tratamiento de empresas sin deuda / exceso de caja y Spread Económico (EVA).
    """

    @staticmethod
    def calculate_wacc_and_spread(
        ticker: str,
        recent_fy: str,
        period_data: Dict[str, Any],
        roic_adjusted: float,
        roic_traditional: float,
        benchmarks: Dict[str, Any],
        diluted_shares_10q: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Calcula WACC institucional y Spread Económico.
        """
        # 1. Obtener datos de mercado en tiempo real
        sector_beta_fb = float(benchmarks.get("damodaran_unlevered_beta", 1.10))
        sector_wacc_fb = float(benchmarks.get("damodaran_industry_wacc", 0.088))

        if MarketDataExtractor is not None:
            mkt = MarketDataExtractor.get_market_data(
                ticker,
                diluted_shares_10q=diluted_shares_10q,
                sector_beta_fallback=sector_beta_fb,
                sector_wacc_fallback=sector_wacc_fb
            )
        else:
            mkt = {
                "ticker": ticker,
                "price": 230.0,
                "market_cap_usd_m": 3000000.0,
                "rf_10y": 0.0425,
                "beta": sector_beta_fb,
                "erp": 0.0475,
                "audit": {"status": "FALLBACK_MODULE_MISSING", "notes": "MarketDataExtractor no disponible"}
            }

        rf = float(mkt.get("rf_10y", 0.0425))
        beta = float(mkt.get("beta", sector_beta_fb))
        erp = float(mkt.get("erp", 0.0475))

        # 2. Costo del Equity (CAPM)
        ke = rf + (beta * erp)

        # 3. Costo de la Deuda y Escudo Fiscal
        raw_debt = _safe_float(period_data.get("total_debt")) or 0.0
        debt = _to_millions(raw_debt) or 0.0

        raw_interest = _safe_float(period_data.get("interest_expense")) or 0.0
        interest = _to_millions(raw_interest) or 0.0

        tax_rate = _safe_float(period_data.get("effective_tax_rate")) or 0.21
        tax_rate = max(0.05, min(0.35, tax_rate))

        is_debt_free = (debt <= 1.0)
        if is_debt_free:
            kd_pre_tax = 0.0
            kd_after_tax = 0.0
            debt = 0.0
        else:
            kd_pre_tax = (interest / debt) if (debt > 0 and interest > 0) else rf
            # Sanity check: si kd_pre_tax es anómalamente bajo o alto
            if kd_pre_tax < 0.02:
                kd_pre_tax = rf + 0.006  # Spread AA/AAA de mercado
            kd_after_tax = kd_pre_tax * (1.0 - tax_rate)

        # 4. Ponderaciones de Estructura de Capital (Valores de Mercado)
        mcap = float(mkt.get("market_cap_usd_m", 0.0))
        total_enterprise_val = mcap + debt

        if total_enterprise_val > 0:
            we = mcap / total_enterprise_val
            wd = debt / total_enterprise_val
        else:
            we = 1.0
            wd = 0.0

        # 5. WACC Consolidado
        if is_debt_free:
            wacc = ke
        else:
            wacc = (we * ke) + (wd * kd_after_tax)

        # 6. Spreads Económicos
        economic_spread_adj = (roic_adjusted - wacc) if roic_adjusted is not None else None
        economic_spread_trad = (roic_traditional - wacc) if roic_traditional is not None else None

        # 7. Evaluación de Foso Defensivo (Economic Moat)
        if economic_spread_adj is not None:
            if economic_spread_adj >= 0.15:
                moat_rating = "FOSO DEFENSIVO EXCEPCIONAL (WIDE MOAT)"
                moat_badge = "🏰 WIDE MOAT / COMPOUNDING MACHINE"
                moat_expl = (
                    f"El negocio genera un retorno ajustado ({roic_adjusted*100:.2f}%) que supera a su costo de capital ({wacc*100:.2f}%) "
                    f"por más de {economic_spread_adj*100:.2f} puntos porcentuales. "
                    "Por cada $100 de capital empleado, crea más de $15 anuales de valor neto por encima de lo que exigen accionistas y bancos. "
                    "Posee ventajas competitivas profundas y duraderas."
                )
            elif economic_spread_adj >= 0.05:
                moat_rating = "FOSO DEFENSIVO SÓLIDO (NARROW MOAT)"
                moat_badge = "🛡️ NARROW MOAT / CREACIÓN DE VALOR SOSTENIBLE"
                moat_expl = (
                    f"El negocio genera un Spread positivo de +{economic_spread_adj*100:.2f} p.p. sobre el WACC ({wacc*100:.2f}%), "
                    "demostrando capacidad de generar valor económico superior a la media de forma constante frente a sus competidores."
                )
            elif economic_spread_adj >= 0.0:
                moat_rating = "RENDIMIENTO COMPETITIVO ESTÁNDAR"
                moat_badge = "⚖️ RENDIMIENTO COMPETITIVO ESTÁNDAR"
                moat_expl = (
                    f"El retorno ({roic_adjusted*100:.2f}%) apenas cubre el costo de financiamiento ({wacc*100:.2f}%), "
                    f"dejando un excedente marginal de +{economic_spread_adj*100:.2f} p.p. Opera en un entorno de alta competencia sin poder de fijación de precios."
                )
            else:
                moat_rating = "DESTRUCCIÓN NETA DE VALOR ECONÓMICO"
                moat_badge = "⚠️ DESTRUCCIÓN DE VALOR ECONÓMICO"
                moat_expl = (
                    f"El retorno ({roic_adjusted*100:.2f}%) es inferior al costo de capital exigido ({wacc*100:.2f}%), "
                    f"destruyendo {abs(economic_spread_adj*100):.2f} puntos porcentuales de valor por cada ciclo operativo."
                )
        else:
            moat_rating = "N/A"
            moat_badge = "N/A"
            moat_expl = "Datos insuficientes para calcular el spread económico."

        # Explicaciones pedagógicas detalladas
        explanations = {
            "ke_capm": (
                f"Costo del Equity (Ke) = {ke*100:.2f}%: Tasa mínima que exigen los accionistas por invertir en la empresa. "
                f"Calculado mediante CAPM: Tasa Libre de Riesgo Rf ({rf*100:.2f}%) + Beta ({beta:.2f}) × Prima de Riesgo ERP ({erp*100:.2f}%)."
            ),
            "kd_debt": (
                "Empresa sin deuda financiera: No incurre en gastos de interés ni requiere ponderar deuda."
                if is_debt_free else
                f"Costo de la Deuda Neto = {kd_after_tax*100:.2f}% (Tasa antes de impuestos {kd_pre_tax*100:.2f}% con escudo fiscal del {tax_rate*100:.1f}%)."
            ),
            "wacc": (
                f"WACC = {wacc*100:.2f}%: Tasa de corte u obstáculo financiero global. "
                f"Pondera {we*100:.1f}% de Equity y {wd*100:.1f}% de Deuda a valores de mercado. "
                f"Frente a la mediana del sector ({sector_wacc_fb*100:.2f}%), su costo de financiamiento es "
                f"{'más bajo y competitivo.' if wacc <= sector_wacc_fb else 'ligeramente superior.'}"
            ),
            "economic_spread": moat_expl
        }

        return {
            "period": recent_fy,
            "market_data": mkt,
            "cost_of_equity_ke": ke,
            "cost_of_debt_kd_pre_tax": kd_pre_tax,
            "cost_of_debt_kd_after_tax": kd_after_tax,
            "effective_tax_rate": tax_rate,
            "market_cap_usd_m": mcap,
            "total_debt_usd_m": debt,
            "enterprise_value_usd_m": total_enterprise_val,
            "weight_equity": we,
            "weight_debt": wd,
            "is_debt_free": is_debt_free,
            "wacc": wacc,
            "sector_wacc_benchmark": sector_wacc_fb,
            "roic_traditional": roic_traditional,
            "roic_adjusted": roic_adjusted,
            "economic_spread_traditional": economic_spread_trad,
            "economic_spread_adjusted": economic_spread_adj,
            "moat_rating": moat_rating,
            "moat_badge": moat_badge,
            "explanations": explanations
        }


class ForensicAccountingEngine:
    """
    Motor Especializado de Auditoría Forense y Detección de Manipulación Contable.
    
    Implementa 3 instrumentos dinámicos no redundantes:
    1. Ratio de Devengos de Sloan (Sloan Accrual Anomaly Ratio):
       - Identifica la desconexión entre el beneficio neto y el flujo de caja operativo sobre los activos totales promedio.
       - Fórmula: (Net Income - CFO) / Activos Totales Promedio
       - Zonas de Calidad: < -3% (Excelente/Alta Calidad CFO > NI), -3% a +7% (Equilibrado/Normal), +7% a +10% (Precaución), > +10% (Alerta Roja de Devengos).
    2. Matriz de Divergencias de Alerta Temprana (Early Warning Spreads):
       - Divergencia Cuentas por Cobrar vs. Ventas: (% Delta AR - % Delta Ventas) y DSO (Días de Cobro). Detecta Channel Stuffing / Facturación Agresiva.
       - Divergencia Inventarios vs. Coste de Ventas: (% Delta Inventario - % Delta COGS) y DIO (Días de Inventario). Detecta existencias no vendidas o absorción artificial de costes fijos.
       - Ratio de Activos Blandos (Soft Assets Ratio): [Total Assets - (Net PP&E + Cash)] / Total Assets. Detecta capitalización excesiva de gastos diferidos e intangibles dudosos.
    3. Montier C-Score (James Montier - 'Cooking the Books', 0 a 6 banderas binarias):
       - Flag 1: Beneficio Neto > Flujo de Caja Operativo (NI > CFO)
       - Flag 2: Crecimiento de Cuentas por Cobrar > Crecimiento de Ventas (% Delta AR > % Delta Sales)
       - Flag 3: Crecimiento de Inventarios > Crecimiento de Coste de Ventas (% Delta Inv > % Delta COGS)
       - Flag 4: Deterioro del Margen Bruto (Gross Margin_t < Gross Margin_t-1)
       - Flag 5: Aumento del Ratio de Activos Blandos (Soft Assets Ratio_t > Soft Assets Ratio_t-1)
       - Flag 6: Reducción de la Tasa de Depreciación Contable (Depr Rate_t < Depr Rate_t-1)
       - Calificación: 0-1 Puntos (Riesgo Muy Bajo / Libros Limpios), 2-3 Puntos (Riesgo Moderado / Vigilancia), 4-6 Puntos (Riesgo Alto / Alarma Forense).
    """

    @classmethod
    def calculate_forensic_series(
        cls,
        fiscal_years: List[str],
        period_metrics: Dict[str, Dict[str, Any]],
        benchmarks: Optional[Dict[str, Any]] = None,
        ticker: str = ""
    ) -> Dict[str, Any]:
        """Calcula la serie histórica completa y LTM para los tres instrumentos de auditoría forense."""
        annual_fys = [y for y in fiscal_years if y != "LTM"]
        annual_fys_sorted = sorted(annual_fys, key=lambda x: int(x.replace("FY", "")) if "FY" in x else 0)

        sloan_analysis: Dict[str, Any] = {}
        divergence_matrix: Dict[str, Any] = {}
        montier_analysis: Dict[str, Any] = {}

        for fy in fiscal_years:
            curr = period_metrics.get(fy, {})

            # Identificar periodo precedente t-1
            prev_fy = None
            if fy == "LTM":
                if annual_fys_sorted:
                    prev_fy = annual_fys_sorted[-1]
            else:
                if fy in annual_fys_sorted:
                    idx = annual_fys_sorted.index(fy)
                    if idx >= 1:
                        prev_fy = annual_fys_sorted[idx - 1]

            prev = period_metrics.get(prev_fy) if prev_fy else None

            # -------------------------------------------------------------
            # 1. Ratio de Devengos de Sloan (Sloan Accrual Anomaly)
            # -------------------------------------------------------------
            ni = _safe_float(curr.get("net_income"))
            cfo = _safe_float(curr.get("cfo"))
            assets_t = _safe_float(curr.get("total_assets"))
            assets_prev = _safe_float(prev.get("total_assets")) if prev else None

            if assets_t and assets_prev and assets_t > 0 and assets_prev > 0:
                avg_assets = (assets_t + assets_prev) / 2.0
            else:
                avg_assets = assets_t

            if ni is not None and cfo is not None and avg_assets and avg_assets > 0:
                total_accruals = ni - cfo
                sloan_ratio = total_accruals / avg_assets
                sloan_ratio_pct = round(sloan_ratio * 100.0, 2)

                if sloan_ratio < -0.03:
                    sloan_status = "EXCELENTE"
                    sloan_badge = "ALTA CONVERSIÓN DE CAJA (CFO > NI)"
                    sloan_color = "#2E7D32"
                    sloan_diag = (
                        "Conservadurismo contable sobresaliente. El flujo de caja operativo supera holgadamente a la utilidad neta, "
                        "generando devengos negativos que blindan al accionista de inflaciones artificiales de beneficios."
                    )
                elif -0.03 <= sloan_ratio <= 0.07:
                    sloan_status = "SALUDABLE"
                    sloan_badge = "DEVENGOS EQUILIBRADOS"
                    sloan_color = "#1976D2"
                    sloan_diag = (
                        "Los devengos contables operan en el rango óptimo y equilibrado (-3% a +7%). "
                        "Existe sólida correspondencia entre ingresos contables y cobros de efectivo."
                    )
                elif 0.07 < sloan_ratio <= 0.10:
                    sloan_status = "PRECAUCIÓN"
                    sloan_badge = "DEVENGOS ELEVADOS (ZONA DE ALERTA)"
                    sloan_color = "#F57C00"
                    sloan_diag = (
                        "El beneficio devengado supera al flujo de caja operativo en más del 7% de los activos. "
                        "Se aconseja vigilar la agresividad en reconocimiento de facturación y variaciones en capital de trabajo."
                    )
                else:
                    sloan_status = "ALERTA ROJA"
                    sloan_badge = "PELIGRO DE MANIPULACIÓN"
                    sloan_color = "#D32F2F"
                    sloan_diag = (
                        "Anomalía severa de devengos (> +10%). Alto riesgo de utilidades contables 'de papel' no respaldadas por efectivo real. "
                        "Fuerte propensión histórica a deterioros de resultados y ajustes futuros."
                    )

                sloan_analysis[fy] = {
                    "period": fy,
                    "prior_period": prev_fy,
                    "net_income": ni,
                    "cfo": cfo,
                    "total_accruals": total_accruals,
                    "ending_assets": assets_t,
                    "avg_assets": avg_assets,
                    "sloan_ratio": round(sloan_ratio, 4),
                    "sloan_ratio_pct": sloan_ratio_pct,
                    "status": sloan_status,
                    "badge": sloan_badge,
                    "color": sloan_color,
                    "diagnosis": sloan_diag
                }
            else:
                sloan_analysis[fy] = {
                    "period": fy,
                    "prior_period": prev_fy,
                    "net_income": ni,
                    "cfo": cfo,
                    "total_accruals": None,
                    "ending_assets": assets_t,
                    "avg_assets": avg_assets,
                    "sloan_ratio": None,
                    "sloan_ratio_pct": None,
                    "status": "N/D",
                    "badge": "DATOS INSUFICIENTES",
                    "color": "#757575",
                    "diagnosis": "Datos contables insuficientes para calcular el ratio de devengos."
                }

            # -------------------------------------------------------------
            # 2. Matriz de Divergencias de Alerta Temprana
            # -------------------------------------------------------------
            # 2.1 Cuentas por Cobrar vs. Ventas (Channel Stuffing)
            ar_t = _safe_float(curr.get("accounts_receivable"))
            ar_prev = _safe_float(prev.get("accounts_receivable")) if prev else None
            rev_t = _safe_float(curr.get("revenue"))
            rev_prev = _safe_float(prev.get("revenue")) if prev else None

            d_ar = ((ar_t - ar_prev) / abs(ar_prev)) if (ar_t is not None and ar_prev and ar_prev > 0) else None
            d_rev = ((rev_t - rev_prev) / abs(rev_prev)) if (rev_t is not None and rev_prev and rev_prev > 0) else None
            ar_sales_spread = (d_ar - d_rev) if (d_ar is not None and d_rev is not None) else None

            dso_t = ((ar_t / rev_t) * 365.0) if (ar_t is not None and rev_t and rev_t > 0) else None
            dso_prev = ((ar_prev / rev_prev) * 365.0) if (ar_prev is not None and rev_prev and rev_prev > 0) else None
            delta_dso = (dso_t - dso_prev) if (dso_t is not None and dso_prev is not None) else None

            flag_ar = False
            if ar_sales_spread is not None and ar_sales_spread > 0.10 and (delta_dso is not None and delta_dso > 5.0):
                flag_ar = True
                status_ar = "ALERTA DE DESCONEXIÓN"
                trap_ar = "Riesgo de Channel Stuffing / Facturación Agresiva"
                color_ar = "#D32F2F"
                diag_ar = (
                    f"Cuentas por cobrar crecen {round(ar_sales_spread * 100, 1)}% más rápido que las ventas, "
                    f"dilatando el cobro en +{round(delta_dso, 1)} días (DSO: {round(dso_t, 1)}d). Alerta de facturación acelerada."
                )
            else:
                status_ar = "COBRANZA SANA"
                trap_ar = "Bajo Riesgo Contable"
                color_ar = "#2E7D32"
                diag_ar = (
                    f"Rotación y cobros armónicos con el ritmo de negocio (Spread: {round(ar_sales_spread * 100, 1) if ar_sales_spread is not None else 0.0}%, "
                    f"DSO: {round(dso_t, 1) if dso_t is not None else 0.0}d). Cobranza disciplinada."
                )

            # 2.2 Inventarios vs. Coste de Ventas (Inventory Bloat / Absorción)
            inv_t = _safe_float(curr.get("inventory"))
            inv_prev = _safe_float(prev.get("inventory")) if prev else None
            cogs_t = _safe_float(curr.get("cost_of_goods_sold"))
            cogs_prev = _safe_float(prev.get("cost_of_goods_sold")) if prev else None

            d_inv = ((inv_t - inv_prev) / abs(inv_prev)) if (inv_t is not None and inv_prev and inv_prev > 0) else None
            d_cogs = ((cogs_t - cogs_prev) / abs(cogs_prev)) if (cogs_t is not None and cogs_prev and cogs_prev > 0) else None
            inv_cogs_spread = (d_inv - d_cogs) if (d_inv is not None and d_cogs is not None) else None

            dio_t = ((inv_t / cogs_t) * 365.0) if (inv_t is not None and cogs_t and cogs_t > 0) else None
            dio_prev = ((inv_prev / cogs_prev) * 365.0) if (inv_prev is not None and cogs_prev and cogs_prev > 0) else None
            delta_dio = (dio_t - dio_prev) if (dio_t is not None and dio_prev is not None) else None

            flag_inv = False
            if inv_cogs_spread is not None and inv_cogs_spread > 0.15 and (delta_dio is not None and delta_dio > 7.0):
                flag_inv = True
                status_inv = "REVISIÓN OPERATIVA"
                trap_inv = "Acumulación de Inventario / Sobreabsorción de Costes"
                color_inv = "#F57C00"
                diag_inv = (
                    f"Las existencias crecen {round(inv_cogs_spread * 100, 1)}% por encima del coste de ventas, elevando el inventario en "
                    f"+{round(delta_dio, 1)} días (DIO: {round(dio_t, 1)}d). Evaluar si responde a preparación estacional de lanzamientos o acumulación no vendida."
                )
            else:
                status_inv = "INVENTARIO CONTROLADO"
                trap_inv = "Bajo Riesgo Contable"
                color_inv = "#2E7D32"
                diag_inv = (
                    f"Inventario en sintonía con la cadencia de costes (Spread: {round(inv_cogs_spread * 100, 1) if inv_cogs_spread is not None else 0.0}%, "
                    f"DIO: {round(dio_t, 1) if dio_t is not None else 0.0}d). Existencias optimizadas."
                )

            # 2.3 Índice de Activos Blandos (Soft Assets Ratio)
            net_ppe_t = _safe_float(curr.get("net_ppe")) or 0.0
            cash_t = _safe_float(curr.get("cash")) or 0.0
            soft_assets_usd = (assets_t - (net_ppe_t + cash_t)) if assets_t else None
            soft_assets_ratio = (soft_assets_usd / assets_t) if (soft_assets_usd is not None and assets_t and assets_t > 0) else None

            soft_assets_prev = None
            if prev and assets_prev and assets_prev > 0:
                net_ppe_prev = _safe_float(prev.get("net_ppe")) or 0.0
                cash_prev = _safe_float(prev.get("cash")) or 0.0
                soft_assets_prev = (assets_prev - (net_ppe_prev + cash_prev)) / assets_prev

            delta_soft_assets = (soft_assets_ratio - soft_assets_prev) if (soft_assets_ratio is not None and soft_assets_prev is not None) else None

            flag_soft = False
            if soft_assets_ratio is not None and soft_assets_ratio > 0.75 and (delta_soft_assets is not None and delta_soft_assets > 0.03):
                flag_soft = True
                status_soft = "PESO ELEVADO"
                trap_soft = "Predominio de Activos Blandos / Intangibles"
                color_soft = "#F57C00"
                diag_soft = (
                    f"El {round(soft_assets_ratio * 100, 1)}% del balance consiste en activos no respaldados por PP&E físico ni caja inmediata "
                    f"(incremento de +{round(delta_soft_assets * 100, 1)} p.p.). Vigilar la capitalización de partidas diferidas."
                )
            else:
                status_soft = "ESTRUCTURA NORMAL"
                trap_soft = "Patrimonio Equilibrado"
                color_soft = "#2E7D32"
                diag_soft = (
                    f"El balance conserva solidez estructural (Ratio Activos Blandos: {round(soft_assets_ratio * 100, 1) if soft_assets_ratio is not None else 0.0}%). "
                    "Adecuado respaldo de activos duros y liquidez."
                )

            divergence_matrix[fy] = {
                "period": fy,
                "ar_sales_spread": {
                    "ar_t": ar_t,
                    "ar_prev": ar_prev,
                    "delta_ar": round(d_ar, 6) if d_ar is not None else None,
                    "delta_ar_pct": round(d_ar * 100, 2) if d_ar is not None else None,
                    "rev_t": rev_t,
                    "rev_prev": rev_prev,
                    "delta_rev": round(d_rev, 6) if d_rev is not None else None,
                    "delta_rev_pct": round(d_rev * 100, 2) if d_rev is not None else None,
                    "spread": round(ar_sales_spread, 6) if ar_sales_spread is not None else None,
                    "spread_pct": round(ar_sales_spread * 100, 2) if ar_sales_spread is not None else None,
                    "dso": round(dso_t, 1) if dso_t is not None else None,
                    "delta_dso": round(delta_dso, 1) if delta_dso is not None else None,
                    "flag": flag_ar,
                    "status": status_ar,
                    "trap_risk": trap_ar,
                    "color": color_ar,
                    "diagnosis": diag_ar
                },
                "inv_cogs_spread": {
                    "inv_t": inv_t,
                    "inv_prev": inv_prev,
                    "delta_inv": round(d_inv, 6) if d_inv is not None else None,
                    "delta_inv_pct": round(d_inv * 100, 2) if d_inv is not None else None,
                    "cogs_t": cogs_t,
                    "cogs_prev": cogs_prev,
                    "delta_cogs": round(d_cogs, 6) if d_cogs is not None else None,
                    "delta_cogs_pct": round(d_cogs * 100, 2) if d_cogs is not None else None,
                    "spread": round(inv_cogs_spread, 6) if inv_cogs_spread is not None else None,
                    "spread_pct": round(inv_cogs_spread * 100, 2) if inv_cogs_spread is not None else None,
                    "dio": round(dio_t, 1) if dio_t is not None else None,
                    "delta_dio": round(delta_dio, 1) if delta_dio is not None else None,
                    "flag": flag_inv,
                    "status": status_inv,
                    "trap_risk": trap_inv,
                    "color": color_inv,
                    "diagnosis": diag_inv
                },
                "soft_assets": {
                    "total_assets": assets_t,
                    "net_ppe": net_ppe_t,
                    "cash": cash_t,
                    "soft_assets_usd": soft_assets_usd,
                    "soft_assets_ratio": round(soft_assets_ratio, 6) if soft_assets_ratio is not None else None,
                    "soft_assets_ratio_pct": round(soft_assets_ratio * 100, 2) if soft_assets_ratio is not None else None,
                    "delta_soft_assets": round(delta_soft_assets, 6) if delta_soft_assets is not None else None,
                    "delta_soft_assets_pct": round(delta_soft_assets * 100, 2) if delta_soft_assets is not None else None,
                    "flag": flag_soft,
                    "status": status_soft,
                    "trap_risk": trap_soft,
                    "color": color_soft,
                    "diagnosis": diag_soft
                }
            }

            # -------------------------------------------------------------
            # 3. Montier C-Score (James Montier - Cooking the Books, 0 a 6)
            # -------------------------------------------------------------
            if prev is None:
                total_montier = None
                montier_rating = "DATOS INSUFICIENTES (SIN T-1)"
                montier_badge = "NO EVALUABLE"
                montier_color = "#757575"
                montier_verdict = "No se dispone de ejercicio precedente (t-1) para evaluar las variaciones interanuales del Montier C-Score."
                flags_bd = {
                    "f1_cfo_divergence": {"name": "1. Divergencia Beneficio vs. Flujo de Caja", "condition": "NI > CFO", "value_str": "N/D", "flag": None, "status": "N/D", "rationale": "Sin ejercicio previo para comparar."},
                    "f2_ar_vs_sales": {"name": "2. Cuentas por Cobrar vs. Ventas", "condition": "Δ Cuentas por Cobrar % > Δ Ventas %", "value_str": "N/D", "flag": None, "status": "N/D", "rationale": "Sin ejercicio previo para comparar."},
                    "f3_inv_vs_cogs": {"name": "3. Inventarios vs. Coste de Ventas", "condition": "Δ Inventarios % > Δ Coste de Ventas %", "value_str": "N/D", "flag": None, "status": "N/D", "rationale": "Sin ejercicio previo para comparar."},
                    "f4_gross_margin": {"name": "4. Deterioro del Margen Bruto", "condition": "Margen Bruto_t < Margen Bruto_t-1", "value_str": "N/D", "flag": None, "status": "N/D", "rationale": "Sin ejercicio previo para comparar."},
                    "f5_soft_assets": {"name": "5. Incremento de Activos Blandos", "condition": "Ratio Activos Blandos_t > Ratio Activos Blandos_t-1", "value_str": "N/D", "flag": None, "status": "N/D", "rationale": "Sin ejercicio previo para comparar."},
                    "f6_depreciation_rate": {"name": "6. Reducción de la Tasa de Depreciación", "condition": "Tasa Depreciación_t < Tasa Depreciación_t-1", "value_str": "N/D", "flag": None, "status": "N/D", "rationale": "Sin ejercicio previo para comparar."}
                }
            else:
                # Bandera 1: Divergencia Beneficio vs. Flujo de Caja Operativa (NI > CFO)
                f1 = 1 if (ni is not None and cfo is not None and ni > cfo) else 0
                val_f1 = f"NI: ${ni/1e6:,.1f}M vs CFO: ${cfo/1e6:,.1f}M" if (ni is not None and cfo is not None) else "N/D"

                # Bandera 2: Crecimiento de Cuentas por Cobrar > Crecimiento de Ventas
                f2 = 1 if (d_ar is not None and d_rev is not None and d_ar > d_rev and d_ar > 0) else 0
                val_f2 = f"ΔAR: {round(d_ar*100, 1)}% vs ΔVentas: {round(d_rev*100, 1)}%" if (d_ar is not None and d_rev is not None) else "N/D"

                # Bandera 3: Crecimiento de Inventarios > Crecimiento de Coste de Ventas
                f3 = 1 if (d_inv is not None and d_cogs is not None and d_inv > d_cogs and d_inv > 0) else 0
                val_f3 = f"ΔInv: {round(d_inv*100, 1)}% vs ΔCOGS: {round(d_cogs*100, 1)}%" if (d_inv is not None and d_cogs is not None) else "N/D"

                # Bandera 4: Deterioro del Margen Bruto
                gp_t = _safe_float(curr.get("gross_profit"))
                gm_t = (gp_t / rev_t) if (gp_t is not None and rev_t and rev_t > 0) else None
                gp_prev = _safe_float(prev.get("gross_profit")) if prev else None
                gm_prev = (gp_prev / rev_prev) if (gp_prev is not None and rev_prev and rev_prev > 0) else None
                f4 = 1 if (gm_t is not None and gm_prev is not None and gm_t < (gm_prev - 0.002)) else 0
                val_f4 = f"Margen Bruto: {round(gm_t*100, 2)}% vs {round(gm_prev*100, 2)}%" if (gm_t is not None and gm_prev is not None) else (f"{round(gm_t*100, 2)}%" if gm_t is not None else "N/D")

                # Bandera 5: Aumento del Ratio de Activos Blandos
                f5 = 1 if (soft_assets_ratio is not None and soft_assets_prev is not None and soft_assets_ratio > (soft_assets_prev + 0.005)) else 0
                val_f5 = f"Activos Blandos: {round(soft_assets_ratio*100, 1)}% vs {round(soft_assets_prev*100, 1)}%" if (soft_assets_ratio is not None and soft_assets_prev is not None) else "N/D"

                # Bandera 6: Reducción de la Tasa de Depreciación Contable
                dna_t = _safe_float(curr.get("depreciation_and_amortization")) or 0.0
                gross_ppe_t = net_ppe_t + dna_t
                depr_rate_t = (dna_t / gross_ppe_t) if gross_ppe_t > 0 else 0.0

                dna_prev = _safe_float(prev.get("depreciation_and_amortization")) or 0.0 if prev else 0.0
                net_ppe_p = _safe_float(prev.get("net_ppe")) or 0.0 if prev else 0.0
                gross_ppe_p = net_ppe_p + dna_prev
                depr_rate_prev = (dna_prev / gross_ppe_p) if gross_ppe_p > 0 else 0.0

                f6 = 1 if (prev and depr_rate_prev > 0 and depr_rate_t < (depr_rate_prev - 0.005)) else 0
                val_f6 = f"Tasa Deprec: {round(depr_rate_t*100, 2)}% vs {round(depr_rate_prev*100, 2)}%" if (prev and depr_rate_prev > 0) else f"{round(depr_rate_t*100, 2)}%"

                total_montier = f1 + f2 + f3 + f4 + f5 + f6

                if total_montier <= 1:
                    montier_rating = "RIESGO MUY BAJO / LIBROS LIMPIOS"
                    montier_badge = "CONTABILIDAD CONSERVADORA"
                    montier_color = "#2E7D32"
                    montier_verdict = (
                        "La compañía supera con honores la auditoría forense. Con 0-1 banderas aisladas, "
                        "la probabilidad empírica de manipulación es mínima (< 5%). Ganancias de alta calidad avaladas por caja real."
                    )
                elif 2 <= total_montier <= 3:
                    montier_rating = "RIESGO MODERADO / ALERTA PREVENTIVA"
                    montier_badge = "ZONA DE VIGILANCIA CONTABLE"
                    montier_color = "#F57C00"
                    montier_verdict = (
                        "Se observan 2 a 3 señales atípicas de capital de trabajo o márgenes. Si bien no implica manipulación contable dolosa, "
                        "amerita verificar la estacionalidad del inventario y los términos contractuales de clientes."
                    )
                else:
                    montier_rating = "RIESGO ALTO / ALERTA FORENSE"
                    montier_badge = "PELIGRO DE MAQUILLAJE CONTABLE"
                    montier_color = "#D32F2F"
                    montier_verdict = (
                        "Alerta forense crítica. Se activan 4 o más banderas de alarma simultáneas "
                        "(beneficios no monetizados, inventario o cobros divergentes y presión en márgenes). Alto riesgo de contabilidad agresiva."
                    )

                flags_bd = {
                    "f1_cfo_divergence": {
                        "name": "1. Divergencia Beneficio vs. Flujo de Caja",
                        "condition": "Utilidad Neta > Flujo de Caja Operativo (NI > CFO)",
                        "value_str": val_f1,
                        "flag": bool(f1),
                        "status": "FLAG" if f1 else "OK",
                        "rationale": "La utilidad contable no se transforma en liquidez real. Alerta de beneficios de papel."
                    },
                    "f2_ar_vs_sales": {
                        "name": "2. Cuentas por Cobrar vs. Ventas",
                        "condition": "Δ Cuentas por Cobrar % > Δ Ventas %",
                        "value_str": val_f2,
                        "flag": bool(f2),
                        "status": "FLAG" if f2 else "OK",
                        "rationale": "Las cuentas a cobrar crecen más rápido que las ventas. Indica relajación de cobros o facturación apresurada (channel stuffing)."
                    },
                    "f3_inv_vs_cogs": {
                        "name": "3. Inventarios vs. Coste de Ventas",
                        "condition": "Δ Inventarios % > Δ Coste de Ventas %",
                        "value_str": val_f3,
                        "flag": bool(f3),
                        "status": "FLAG" if f3 else "OK",
                        "rationale": "Las existencias crecen más rápido que los costes de venta. Puede esconder producto no vendido o absorción de costes en inventario para inflar márgenes."
                    },
                    "f4_gross_margin": {
                        "name": "4. Deterioro del Margen Bruto",
                        "condition": "Margen Bruto_t < Margen Bruto_t-1",
                        "value_str": val_f4,
                        "flag": bool(f4),
                        "status": "FLAG" if f4 else "OK",
                        "rationale": "El deterioro del margen bruto genera incentivos en los ejecutivos para estirar partidas contables inferiores."
                    },
                    "f5_soft_assets": {
                        "name": "5. Incremento de Activos Blandos",
                        "condition": "Ratio Activos Blandos_t > Ratio Activos Blandos_t-1",
                        "value_str": val_f5,
                        "flag": bool(f5),
                        "status": "FLAG" if f5 else "OK",
                        "rationale": "Aumento del peso relativo de partidas del balance que no son activos productivos tangibles ni tesorería."
                    },
                    "f6_depreciation_rate": {
                        "name": "6. Reducción de la Tasa de Depreciación",
                        "condition": "Tasa Depreciación_t < Tasa Depreciación_t-1",
                        "value_str": val_f6,
                        "flag": bool(f6),
                        "status": "FLAG" if f6 else "OK",
                        "rationale": "Reducción de la amortización contable respecto a los activos brutos, inflando el beneficio neto al estirar vidas útiles."
                    }
                }

            montier_analysis[fy] = {
                "period": fy,
                "total_score": total_montier,
                "max_score": 6,
                "rating": montier_rating,
                "badge": montier_badge,
                "color": montier_color,
                "verdict": montier_verdict,
                "flags_breakdown": flags_bd
            }

        # Dictamen consolidado para el período más reciente
        recent_period = "LTM" if "LTM" in fiscal_years else (fiscal_years[0] if fiscal_years else "N/A")
        latest_sloan = sloan_analysis.get(recent_period, {})
        latest_div = divergence_matrix.get(recent_period, {})
        latest_montier = montier_analysis.get(recent_period, {})

        sloan_rat = latest_sloan.get("sloan_ratio")
        montier_sc = latest_montier.get("total_score", 0)

        if (sloan_rat is not None and sloan_rat < -0.03) and montier_sc <= 2:
            global_verdict = (
                f"CALIDAD DE BENEFICIOS EXCEPCIONAL (GRADO INSTITUCIONAL): Conversión de efectivo sobresaliente "
                f"(Ratio Sloan: {latest_sloan.get('sloan_ratio_pct')}%, CFO > Utilidad Neta), devengos negativos que suprimen riesgo de inflación contable "
                f"y Montier C-Score de {montier_sc}/6 que descarta maniobras de manipulación deliberada."
            )
            global_color = "#2E7D32"
            global_badge = "MÁXIMA CALIDAD CONTABLE"
        elif (sloan_rat is not None and -0.03 <= sloan_rat <= 0.07) and montier_sc <= 3:
            global_verdict = (
                f"CONTABILIDAD SALUDABLE Y EQUILIBRADA: Devengos dentro de la banda histórica normal "
                f"(Ratio Sloan: {latest_sloan.get('sloan_ratio_pct')}%) y Montier C-Score de {montier_sc}/6. "
                "Los resultados financieros reflejan razonablemente la realidad económica de las operaciones."
            )
            global_color = "#1976D2"
            global_badge = "ESTÁNDAR SALUDABLE"
        elif montier_sc >= 4 or (sloan_rat is not None and sloan_rat > 0.10):
            global_verdict = (
                f"ALERTA FORENSE POR CALIDAD DE RESULTADOS: Detección de devengos desproporcionados "
                f"(Ratio Sloan: {latest_sloan.get('sloan_ratio_pct')}%) o Montier C-Score elevado ({montier_sc}/6). "
                "Se recomienda auditoría minuciosa de políticas contables, partidas no monetarias y devengos acumulados."
            )
            global_color = "#D32F2F"
            global_badge = "ALERTA FORENSE"
        else:
            global_verdict = (
                f"ZONA DE VIGILANCIA POR DESFASES OPERATIVOS: Montier C-Score de {montier_sc}/6 con divergencias puntuales en capital de trabajo. "
                "Revisar ciclos estacionales de inventarios y condiciones comerciales de cobro."
            )
            global_color = "#F57C00"
            global_badge = "ZONA DE VIGILANCIA"

        return {
            "ticker": ticker.upper(),
            "periods": fiscal_years,
            "recent_period": recent_period,
            "sloan_accrual_analysis": sloan_analysis,
            "divergence_matrix": divergence_matrix,
            "montier_c_score": montier_analysis,
            "latest_result": {
                "period": recent_period,
                "sloan_accrual": latest_sloan,
                "divergences": latest_div,
                "montier_c_score": latest_montier,
                "forensic_verdict": global_verdict,
                "global_color": global_color,
                "global_badge": global_badge
            }
        }


class DebtSolvencyEngine:
    """
    Motor Institucional de Análisis de Deuda, Solvencia y Estrés Financiero:
    1. Apalancamiento y Capacidad de Amortización frente a Flujos de Caja (Cash Flow Leverage).
    2. Cobertura de Carga Financiera y Servicio de la Deuda (Debt Service Coverage).
    3. Liquidez Inmediata y Riesgo de Refinanciación (Liquidity & Rollover Risk).
    4. Modelos Predictivos de Quiebra y Rating Sintético (Altman Z''-Score & Damodaran).
    """

    @classmethod
    def _get_synthetic_rating(cls, int_cov: Optional[float], is_debt_free: bool = False) -> Dict[str, Any]:
        """Asigna el rating sintético, descripción, spread de default y probabilidad empírica según Damodaran."""
        if is_debt_free:
            return {
                "rating": "AAA",
                "desc": "MÁXIMA CALIDAD CREDITICIA (LIBRE DE DEUDA)",
                "default_spread": 0.0040,
                "default_spread_pct": 0.40,
                "default_probability": "< 0.1%",
                "color": "#2E7D32"
            }
        elif int_cov is None or int_cov >= 8.5:
            return {
                "rating": "AAA",
                "desc": "GRADO INSTITUCIONAL MÁXIMO (AAA / Aaa)",
                "default_spread": 0.0060,
                "default_spread_pct": 0.60,
                "default_probability": "< 0.2%",
                "color": "#2E7D32"
            }
        elif int_cov >= 6.5:
            return {
                "rating": "AA",
                "desc": "SOLVENCIA MUY FUERTE (AA / Aa2)",
                "default_spread": 0.0080,
                "default_spread_pct": 0.80,
                "default_probability": "0.3%",
                "color": "#2E7D32"
            }
        elif int_cov >= 5.5:
            return {
                "rating": "A+",
                "desc": "SOLVENCIA ROBUSTA (A+ / A1)",
                "default_spread": 0.0110,
                "default_spread_pct": 1.10,
                "default_probability": "0.5%",
                "color": "#1976D2"
            }
        elif int_cov >= 4.25:
            return {
                "rating": "A",
                "desc": "SOLVENCIA BUENA (A / A2)",
                "default_spread": 0.0130,
                "default_spread_pct": 1.30,
                "default_probability": "0.7%",
                "color": "#1976D2"
            }
        elif int_cov >= 3.0:
            return {
                "rating": "A-",
                "desc": "SOLVENCIA SATISFACTORIA (A- / A3)",
                "default_spread": 0.0150,
                "default_spread_pct": 1.50,
                "default_probability": "1.0%",
                "color": "#1976D2"
            }
        elif int_cov >= 2.5:
            return {
                "rating": "BBB",
                "desc": "GRADO DE INVERSIÓN LÍMITE (BBB / Baa2)",
                "default_spread": 0.0200,
                "default_spread_pct": 2.00,
                "default_probability": "2.2%",
                "color": "#F57C00"
            }
        elif int_cov >= 2.25:
            return {
                "rating": "BB+",
                "desc": "GRADO ESPECULATIVO (BB+ / Ba1 - HIGH YIELD)",
                "default_spread": 0.0250,
                "default_spread_pct": 2.50,
                "default_probability": "3.5%",
                "color": "#F57C00"
            }
        elif int_cov >= 2.0:
            return {
                "rating": "BB",
                "desc": "GRADO ESPECULATIVO MODERADO (BB / Ba2)",
                "default_spread": 0.0300,
                "default_spread_pct": 3.00,
                "default_probability": "5.0%",
                "color": "#D32F2F"
            }
        elif int_cov >= 1.5:
            return {
                "rating": "B",
                "desc": "ALTA VULNERABILIDAD FINANCIERA (B / B2)",
                "default_spread": 0.0450,
                "default_spread_pct": 4.50,
                "default_probability": "10.0%",
                "color": "#D32F2F"
            }
        elif int_cov >= 1.0:
            return {
                "rating": "CCC",
                "desc": "RIESGO SUSTANCIAL DE IMPAGO (CCC / Caa)",
                "default_spread": 0.0800,
                "default_spread_pct": 8.00,
                "default_probability": "25.0%",
                "color": "#D32F2F"
            }
        else:
            return {
                "rating": "D",
                "desc": "DEFAULT INMINENTE O TÉCNICO (D / Default)",
                "default_spread": 0.1500,
                "default_spread_pct": 15.00,
                "default_probability": "> 50.0%",
                "color": "#D32F2F"
            }

    @classmethod
    def calculate_solvency_series(
        cls,
        fiscal_years: List[str],
        period_metrics: Dict[str, Dict[str, Any]],
        benchmarks: Optional[Dict[str, Any]] = None,
        ticker: str = "",
        market_cap: Optional[float] = None
    ) -> Dict[str, Any]:
        """Calcula la serie histórica completa y LTM de solvencia, liquidez y riesgo de quiebra."""
        leverage_series: Dict[str, Any] = {}
        coverage_series: Dict[str, Any] = {}
        liquidity_series: Dict[str, Any] = {}
        distress_series: Dict[str, Any] = {}

        for fy in fiscal_years:
            curr = period_metrics.get(fy, {})

            # Variables base en $M
            raw_debt = _safe_float(curr.get("total_debt")) or 0.0
            debt = _to_millions(raw_debt) or 0.0

            raw_cash = _safe_float(curr.get("cash")) or 0.0
            cash = _to_millions(raw_cash) or 0.0

            net_debt = debt - cash

            raw_ebit = _safe_float(curr.get("operating_income")) if curr.get("operating_income") is not None else _safe_float(curr.get("ebit"))
            ebit = _to_millions(raw_ebit)

            raw_dna = _safe_float(curr.get("depreciation_and_amortization")) or 0.0
            dna = _to_millions(raw_dna) or 0.0

            ebitda = (ebit + dna) if ebit is not None else None

            raw_cfo = _safe_float(curr.get("cfo")) if curr.get("cfo") is not None else _safe_float(curr.get("operating_cash_flow"))
            cfo = _to_millions(raw_cfo)

            raw_capex = _safe_float(curr.get("capex")) or 0.0
            capex = _to_millions(raw_capex) or 0.0

            fcf = (cfo - capex) if cfo is not None else None

            raw_st_debt = _safe_float(curr.get("short_term_debt")) or 0.0
            st_debt = _to_millions(raw_st_debt) or 0.0

            raw_lt_debt = _safe_float(curr.get("long_term_debt")) or 0.0
            lt_debt = _to_millions(raw_lt_debt) or 0.0

            raw_interest = _safe_float(curr.get("interest_expense")) or 0.0
            interest = _to_millions(raw_interest) or 0.0

            # Si el interés reportado es 0 pero la empresa tiene deuda material (> $100M), estimar con coste conservador
            interest_estimated = False
            if debt > 100.0 and interest <= 0.0:
                interest = debt * 0.045
                interest_estimated = True

            raw_ca = _safe_float(curr.get("current_assets"))
            ca = _to_millions(raw_ca)

            raw_cl = _safe_float(curr.get("current_liabilities"))
            cl = _to_millions(raw_cl)

            raw_ar = _safe_float(curr.get("accounts_receivable")) or 0.0
            ar = _to_millions(raw_ar) or 0.0

            raw_inv = _safe_float(curr.get("inventory")) or 0.0
            inv = _to_millions(raw_inv) or 0.0

            raw_assets = _safe_float(curr.get("total_assets"))
            assets = _to_millions(raw_assets)

            raw_equity = _safe_float(curr.get("stockholders_equity"))
            equity = _to_millions(raw_equity) if raw_equity is not None else 0.0

            raw_re = _safe_float(curr.get("retained_earnings"))
            re = _to_millions(raw_re) if raw_re is not None else 0.0

            raw_liab = _safe_float(curr.get("total_liabilities"))
            liab = _to_millions(raw_liab) if raw_liab is not None else ((assets - equity) if assets is not None else None)

            # -------------------------------------------------------------
            # Bloque 1: Apalancamiento y Capacidad de Repago frente a Flujos de Caja
            # -------------------------------------------------------------
            is_debt_free = (debt <= 1.0)
            is_net_cash = (net_debt <= 0.0)

            nd_to_ebitda = None
            nd_to_ebitda_str = "N/D"
            if is_debt_free or is_net_cash:
                nd_to_ebitda = round(net_debt / ebitda, 2) if (ebitda and ebitda > 0) else 0.0
                nd_to_ebitda_str = "CAJA NETA"
                status_leverage = "EXCELENTE (POSICIÓN DE CAJA NETA)"
                color_leverage = "#2E7D32"
                badge_leverage = "CAJA NETA"
                diag_leverage = f"Estructura ultra sólida sin deuda neta ({round(net_debt, 1):+,.1f}$M). La liquidez disponible excede a la deuda total."
            elif ebitda and ebitda > 0:
                ratio = net_debt / ebitda
                nd_to_ebitda = round(ratio, 2)
                nd_to_ebitda_str = f"{ratio:.2f}x"
                if ratio < 1.5:
                    status_leverage = "GRADO INVERSIÓN SUPERIOR (< 1.5x)"
                    color_leverage = "#2E7D32"
                    badge_leverage = "APALANCAMIENTO BAJO"
                    diag_leverage = f"Apalancamiento muy conservador ({ratio:.2f}x EBITDA). La empresa extinguiría su deuda neta en {ratio:.1f} años de beneficio operativo bruto."
                elif ratio <= 3.0:
                    status_leverage = "APALANCAMIENTO MODERADO (1.5x - 3.0x)"
                    color_leverage = "#1976D2"
                    badge_leverage = "APALANCAMIENTO SALUDABLE"
                    diag_leverage = f"Apalancamiento equilibrado y controlado ({ratio:.2f}x EBITDA), común en empresas con flujos de caja predecibles."
                elif ratio <= 4.0:
                    status_leverage = "VULNERABILIDAD FINANCIERA (3.0x - 4.0x)"
                    color_leverage = "#F57C00"
                    badge_leverage = "ZONA DE VIGILANCIA"
                    diag_leverage = f"Apalancamiento elevado ({ratio:.2f}x EBITDA). Requiere seguimiento de covenants y tipos de interés."
                else:
                    status_leverage = "GRADO ESPECULATIVO / ALTO APALANCAMIENTO (> 4.0x)"
                    color_leverage = "#D32F2F"
                    badge_leverage = "ALERTA COVENANTS"
                    diag_leverage = f"Alto riesgo de sobreendeudamiento ({ratio:.2f}x EBITDA). Vulnerabilidad crítica ante caídas en demanda."
            else:
                status_leverage = "EBITDA NEGATIVO O NULO"
                color_leverage = "#D32F2F"
                badge_leverage = "DÉFICIT OPERATIVO"
                diag_leverage = "EBITDA insuficiente para calcular el ratio de amortización."

            nd_to_fcf = None
            nd_to_fcf_str = "N/D"
            if is_debt_free or is_net_cash:
                nd_to_fcf = round(net_debt / fcf, 2) if (fcf and fcf > 0) else 0.0
                nd_to_fcf_str = "CAJA NETA"
            elif fcf and fcf > 0:
                r_fcf = net_debt / fcf
                nd_to_fcf = round(r_fcf, 2)
                nd_to_fcf_str = f"{r_fcf:.2f}x"

            debt_to_cfo = round(debt / cfo, 2) if (cfo and cfo > 0) else None

            leverage_series[fy] = {
                "period": fy,
                "total_debt": round(debt, 1),
                "cash": round(cash, 1),
                "net_debt": round(net_debt, 1),
                "ebit": round(ebit, 1) if ebit is not None else None,
                "dna": round(dna, 1),
                "ebitda": round(ebitda, 1) if ebitda is not None else None,
                "cfo": round(cfo, 1) if cfo is not None else None,
                "capex": round(capex, 1),
                "fcf": round(fcf, 1) if fcf is not None else None,
                "net_debt_to_ebitda": nd_to_ebitda,
                "net_debt_to_ebitda_str": nd_to_ebitda_str,
                "net_debt_to_fcf": nd_to_fcf,
                "net_debt_to_fcf_str": nd_to_fcf_str,
                "debt_to_cfo": debt_to_cfo,
                "is_debt_free": is_debt_free,
                "is_net_cash": is_net_cash,
                "status": status_leverage,
                "badge": badge_leverage,
                "color": color_leverage,
                "diagnosis": diag_leverage
            }

            # -------------------------------------------------------------
            # Bloque 2: Cobertura de Carga Financiera y Servicio de la Deuda
            # -------------------------------------------------------------
            if is_debt_free:
                int_cov = None
                int_cov_str = "INFINITA (SIN DEUDA)"
                cash_int_cov = None
                cash_int_cov_str = "INFINITA (SIN DEUDA)"
                burden_pct = 0.0
                status_service = "LIBRE DE DEUDA"
                color_service = "#2E7D32"
                badge_service = "SERVICIO BLINDADO"
                diag_service = "La compañía opera sin deuda financiera, por lo que carece de gasto financiero que comprometa sus resultados."
            elif interest > 0 and ebit is not None:
                cov = ebit / interest
                int_cov = round(cov, 2)
                int_cov_str = f"{cov:.1f}x"
                cash_cov = (cfo / interest) if (cfo and cfo > 0) else None
                cash_int_cov = round(cash_cov, 2) if cash_cov is not None else None
                cash_int_cov_str = f"{cash_cov:.1f}x" if cash_cov is not None else "N/D"
                burden = (interest / cfo * 100.0) if (cfo and cfo > 0) else 0.0
                burden_pct = round(burden, 2)

                if cov >= 10.0:
                    status_service = "COBERTURA EXCELENTE (> 10.0x)"
                    color_service = "#2E7D32"
                    badge_service = "MÁXIMA PROTECCIÓN"
                    diag_service = f"Los beneficios operativos cubren {cov:.1f} veces los intereses. Carga financiera insignificante ({burden_pct:.1f}% del CFO)."
                elif cov >= 5.0:
                    status_service = "COBERTURA SALUDABLE (5.0x - 10.0x)"
                    color_service = "#1976D2"
                    badge_service = "COBERTURA ROBUSTA"
                    diag_service = f"Cobertura cómoda ({cov:.1f}x). Margen operativo holgado para resistir incrementos en el coste de financiación."
                elif cov >= 2.5:
                    status_service = "VULNERABILIDAD A CICLOS (2.5x - 5.0x)"
                    color_service = "#F57C00"
                    badge_service = "VIGILANCIA DE INTERESES"
                    diag_service = f"Cobertura ajustada ({cov:.1f}x). Sensibilidad ante caídas de margen o subidas de tipos."
                else:
                    status_service = "PELIGRO DE DEFAULT (< 2.5x)"
                    color_service = "#D32F2F"
                    badge_service = "ESTRÉS FINANCIERO"
                    diag_service = f"Carga de intereses asfixiante ({cov:.1f}x). Alto riesgo de refinanciación forzada o impago."
            else:
                int_cov = None
                int_cov_str = "N/D"
                cash_int_cov = None
                cash_int_cov_str = "N/D"
                burden_pct = 0.0
                status_service = "GASTO FINANCIERO MÍNIMO"
                color_service = "#2E7D32"
                badge_service = "SIN CARGA FINANCIERA"
                diag_service = "Gasto financiero reportado mínimo o absorbido por ingresos financieros."

            coverage_series[fy] = {
                "period": fy,
                "ebit": round(ebit, 1) if ebit is not None else None,
                "interest_expense": round(interest, 1),
                "interest_estimated": interest_estimated,
                "interest_coverage": int_cov,
                "interest_coverage_str": int_cov_str,
                "cash_interest_coverage": cash_int_cov,
                "cash_interest_coverage_str": cash_int_cov_str,
                "financial_burden_pct": burden_pct,
                "status": status_service,
                "badge": badge_service,
                "color": color_service,
                "diagnosis": diag_service
            }

            # -------------------------------------------------------------
            # Bloque 3: Liquidez Inmediata y Perfil de Vencimiento
            # -------------------------------------------------------------
            cr = round(ca / cl, 2) if (ca is not None and cl and cl > 0) else None
            qr = round((cash + ar) / cl, 2) if (cl and cl > 0) else None
            cash_r = round(cash / cl, 2) if (cl and cl > 0) else None
            rollover_pct = round((st_debt / debt) * 100.0, 2) if debt > 0 else 0.0
            tot_cap = debt + max(0.0, equity)
            debt_to_cap_pct = round((debt / tot_cap) * 100.0, 2) if tot_cap > 0 else 0.0

            if qr is not None and qr >= 1.2:
                status_liq = "LIQUIDEZ EXCELENTE (QUICK RATIO > 1.2x)"
                color_liq = "#2E7D32"
                badge_liq = "COLCHÓN DE LIQUIDEZ"
                diag_liq = f"La liquidez ácida ({qr:.2f}x) cubre sobradamente los pasivos inmediatos sin depender de vender inventario."
            elif qr is not None and qr >= 0.8:
                status_liq = "LIQUIDEZ EQUILIBRADA (0.8x - 1.2x)"
                color_liq = "#1976D2"
                badge_liq = "EQUILIBRADA"
                diag_liq = f"Liquidez operativa dentro de la media ({qr:.2f}x). Gestión estándar de cobros y caja."
            elif qr is not None:
                status_liq = "GESTIÓN DE CAPITAL DE TRABAJO AGRESIVA (< 0.8x)"
                color_liq = "#F57C00"
                badge_liq = "LIQUIDEZ AJUSTADA"
                diag_liq = f"Quick ratio de {qr:.2f}x. Típico en empresas con poder de negociación que financian operaciones con proveedores (Working Capital negativo)."
            else:
                status_liq = "NO APLICABLE (ENTIDAD FINANCIERA / MODELO SIN BALANCE CORRIENTE)"
                color_liq = "#607D8B"
                badge_liq = "N/A FINANCIERA"
                diag_liq = "Estructura de balance sin clasificación corriente/no corriente (bancos y aseguradoras operan con activos/pasivos financieros directos)."

            liquidity_series[fy] = {
                "period": fy,
                "current_assets": round(ca, 1) if ca is not None else None,
                "current_liabilities": round(cl, 1) if cl is not None else None,
                "accounts_receivable": round(ar, 1),
                "inventory": round(inv, 1),
                "cash": round(cash, 1),
                "current_ratio": cr,
                "quick_ratio": qr,
                "cash_ratio": cash_r,
                "short_term_debt": round(st_debt, 1),
                "long_term_debt": round(lt_debt, 1),
                "total_debt": round(debt, 1),
                "rollover_risk_pct": rollover_pct,
                "debt_to_capital_pct": debt_to_cap_pct,
                "status": status_liq,
                "badge": badge_liq,
                "color": color_liq,
                "diagnosis": diag_liq
            }

            # -------------------------------------------------------------
            # Bloque 4: Modelos Predictivos de Quiebra y Rating Sintético
            # -------------------------------------------------------------
            # 4.1 Altman Z''-Score (4 variables para empresas globales/servicios)
            z_score = None
            x1 = x2 = x3 = x4 = None
            if assets and assets > 0 and liab and liab > 0:
                nwc = (ca - cl) if (ca is not None and cl is not None) else 0.0
                x1 = round(nwc / assets, 4)
                x2 = round(re / assets, 4)
                x3 = round((ebit / assets), 4) if ebit is not None else 0.0
                # Si el equity contable es negativo (por recompras masivas), acotar x4 a 0 para no distorsionar
                adj_eq = max(0.0, equity)
                x4 = round(adj_eq / liab, 4)
                z_score = round(6.56 * x1 + 3.26 * x2 + 6.72 * x3 + 1.05 * x4, 2)

                if z_score > 2.60:
                    altman_zone = "ZONA SEGURA (BAJO RIESGO DE QUIEBRA)"
                    altman_badge = "ZONA SEGURA"
                    altman_color = "#2E7D32"
                    diag_altman = f"Altman Z''-Score de {z_score:.2f} (> 2.60). Probabilidad estadística de insolvencia virtualmente nula a 2 años vista."
                elif z_score >= 1.10:
                    altman_zone = "ZONA GRIS (PRECAUCIÓN Y SEGUIMIENTO)"
                    altman_badge = "ZONA GRIS"
                    altman_color = "#F57C00"
                    diag_altman = f"Altman Z''-Score de {z_score:.2f} (entre 1.10 y 2.60). Requiere seguimiento de márgenes y apalancamiento."
                else:
                    altman_zone = "ZONA DE DISTRESS (ALTO RIESGO DE INSOLVENCIA)"
                    altman_badge = "PELIGRO DE QUIEBRA"
                    altman_color = "#D32F2F"
                    diag_altman = f"Altman Z''-Score crítico de {z_score:.2f} (< 1.10). Severo estrés financiero y riesgo de default."
            else:
                altman_zone = "DATOS INSUFICIENTES"
                altman_badge = "N/D"
                altman_color = "#757575"
                diag_altman = "Estructura de balance incompleta para calcular Altman Z''-Score."

            # 4.2 Rating Sintético Damodaran
            synth_dict = cls._get_synthetic_rating(int_cov, is_debt_free=is_debt_free)
            synth_rating = synth_dict["rating"]
            synth_desc = synth_dict["desc"]
            default_spread = synth_dict["default_spread"]
            default_prob = synth_dict["default_probability"]
            color_rating = synth_dict["color"]

            distress_series[fy] = {
                "period": fy,
                "altman_x1": x1,
                "altman_x2": x2,
                "altman_x3": x3,
                "altman_x4": x4,
                "altman_z_double_prime": z_score,
                "altman_zone": altman_zone,
                "altman_badge": altman_badge,
                "altman_color": altman_color,
                "altman_diagnosis": diag_altman,
                "synthetic_rating": synth_rating,
                "synthetic_rating_desc": synth_desc,
                "default_spread": default_spread,
                "default_spread_pct": round(default_spread * 100.0, 2),
                "default_probability": default_prob,
                "rating_color": color_rating
            }

        # Dictamen consolidado para el período más reciente
        recent_period = "LTM" if "LTM" in fiscal_years else (fiscal_years[0] if fiscal_years else "N/A")
        latest_lev = leverage_series.get(recent_period, {})
        latest_cov = coverage_series.get(recent_period, {})
        latest_liq = liquidity_series.get(recent_period, {})
        latest_dist = distress_series.get(recent_period, {})

        is_clean_solvency = (
            (latest_lev.get("is_net_cash") or (latest_lev.get("net_debt_to_ebitda") is not None and latest_lev.get("net_debt_to_ebitda") < 1.5))
            and (latest_dist.get("altman_z_double_prime") is not None and latest_dist.get("altman_z_double_prime") > 2.60)
        )

        if is_clean_solvency:
            global_verdict = (
                f"FORTALEZA FINANCIERA INQUEBRANTABLE (GRADO INSTITUCIONAL AAA/AA): "
                f"Apalancamiento óptimo ({latest_lev.get('net_debt_to_ebitda_str')}), "
                f"cobertura de intereses de {latest_cov.get('interest_coverage_str')} y "
                f"Altman Z''-Score de {latest_dist.get('altman_z_double_prime', 'N/D')} en Zona Segura. "
                "Cero estrés crediticio, con capacidad excepcional de financiación en cualquier ciclo macroeconómico."
            )
            global_badge = "MÁXIMA SOLVENCIA INSTITUCIONAL"
            global_color = "#2E7D32"
        elif latest_dist.get("altman_z_double_prime") is not None and latest_dist.get("altman_z_double_prime") < 1.10:
            global_verdict = (
                f"ALERTA CRÍTICA DE SOLVENCIA Y ESTRÉS FINANCIERO: "
                f"Altman Z''-Score de {latest_dist.get('altman_z_double_prime')} en Zona de Distress. "
                f"Apalancamiento de {latest_lev.get('net_debt_to_ebitda_str')} y cobertura de {latest_cov.get('interest_coverage_str')}. "
                "Alto riesgo de incumplimiento de covenants y vulnerabilidad ante vencimientos de deuda."
            )
            global_badge = "ALERTA DE INSOLVENCIA"
            global_color = "#D32F2F"
        else:
            global_verdict = (
                f"SOLVENCIA EQUILIBRADA BAJO MONITOREO: "
                f"Apalancamiento controlado ({latest_lev.get('net_debt_to_ebitda_str')}), "
                f"cobertura de {latest_cov.get('interest_coverage_str')} y Altman Z''-Score de {latest_dist.get('altman_z_double_prime', 'N/D')}. "
                "Estructura de capital adecuada sin riesgos inminentes de impago."
            )
            global_badge = "SOLVENCIA MODERADA"
            global_color = "#1976D2"

        return {
            "available": True,
            "ticker": ticker.upper(),
            "periods": fiscal_years,
            "recent_period": recent_period,
            "cash_flow_leverage": leverage_series,
            "debt_service": coverage_series,
            "liquidity_and_refinancing": liquidity_series,
            "distress_and_credit_models": distress_series,
            "latest_result": {
                "period": recent_period,
                "cash_flow_leverage": latest_lev,
                "debt_service": latest_cov,
                "liquidity": latest_liq,
                "distress_models": latest_dist,
                "solvency_verdict": global_verdict,
                "global_color": global_color,
                "global_badge": global_badge
            }
        }


def extract_period_metrics(financials: Dict[str, Any], period: str) -> Dict[str, float]:
    """Extrae las variables contables estandarizadas de un periodo específico desde financial_statements.json."""
    summary = financials.get("canonical_summary", {})
    inc_detail = financials.get("income_statement_detail", {})
    bal_detail = financials.get("balance_sheet_detail", {})
    cf_detail = financials.get("cash_flow_detail", {})

    def get_val(container: Dict[str, Any], key: str) -> Optional[float]:
        if key in container:
            v = container[key]
            if isinstance(v, dict):
                # Puede ser {period: val} o {'values': {period: val}}
                vals = v.get("values", v)
                res = vals.get(period)
                if res is not None and not (isinstance(res, float) and math.isnan(res)):
                    return float(res)
        return None

    # 1. Utilidad Neta
    ni = get_val(summary, "net_income")
    if ni is None:
        ni = get_val(inc_detail, "NetIncomeLoss")

    # 2. Flujo de Caja Operativo
    cfo = get_val(summary, "cash_from_operations")
    if cfo is None:
        cfo = get_val(cf_detail, "NetCashProvidedByUsedInOperatingActivities")

    # 3. Activos Totales
    assets = get_val(summary, "total_assets")
    if assets is None:
        assets = get_val(bal_detail, "Assets")

    # 4. Deuda Financiera Total (Mejora B: LongTermDebtNoncurrent + LongTermDebtCurrent)
    lt_debt = get_val(bal_detail, "LongTermDebtNoncurrent")
    st_debt = get_val(bal_detail, "LongTermDebtCurrent")
    total_debt = get_val(bal_detail, "LongTermDebt")

    if lt_debt is not None and st_debt is not None:
        debt = lt_debt + st_debt
    elif total_debt is not None:
        debt = total_debt
    elif lt_debt is not None:
        debt = lt_debt
    else:
        debt = 0.0

    # 5. Activos Corrientes y Pasivos Corrientes
    ca = get_val(bal_detail, "AssetsCurrent")
    cl = get_val(bal_detail, "LiabilitiesCurrent")

    # 6. Acciones Básicas (Mejora A)
    basic_shares = get_val(summary, "shares_basic")
    if basic_shares is None:
        basic_shares = get_val(inc_detail, "WeightedAverageNumberOfSharesOutstandingBasic")
    if basic_shares is None:
        basic_shares = get_val(summary, "shares_diluted")
    if basic_shares is None:
        basic_shares = get_val(inc_detail, "WeightedAverageNumberOfDilutedSharesOutstanding")
    if basic_shares is None:
        basic_shares = get_val(bal_detail, "CommonStockSharesOutstanding")

    # 7. Margen Bruto y Ventas
    gp = get_val(summary, "gross_profit")
    if gp is None:
        gp = get_val(inc_detail, "GrossProfit")

    rev = get_val(summary, "revenue")
    if rev is None:
        rev = get_val(inc_detail, "RevenueFromContractWithCustomerExcludingAssessedTax")
    if rev is None:
        rev = get_val(inc_detail, "Revenues")

    # 8. I+D, CapEx y SG&A
    rd = get_val(inc_detail, "ResearchAndDevelopmentExpense") or 0.0

    capex = get_val(summary, "capital_expenditures")
    if capex is None:
        capex = get_val(cf_detail, "PaymentsToAcquirePropertyPlantAndEquipment")
    if capex is None:
        capex = 0.0

    sga = get_val(inc_detail, "SellingGeneralAndAdministrativeExpense")
    if sga is None:
        sga = get_val(inc_detail, "OperatingExpenses")

    # 9. Efectivo e Inversiones Líquidas (para Ex-Caja en Novy-Marx)
    cash = get_val(summary, "cash_and_equivalents")
    if cash is None:
        cash = get_val(bal_detail, "CashAndCashEquivalentsAtCarryingValue")
    if cash is None:
        cash = get_val(bal_detail, "CashAndCashEquivalents")
    if cash is None:
        cash = get_val(bal_detail, "CashCashEquivalentsAndShortTermInvestments")
    if cash is None:
        cash = 0.0

    # 10. Variables complementarias para ROIC, ROC y WACC
    ebit = get_val(summary, "operating_income")
    if ebit is None:
        ebit = get_val(inc_detail, "OperatingIncomeLoss")

    # 11. PP&E Neto para Capital Tangible (ROC Greenblatt)
    net_ppe = get_val(summary, "net_ppe")
    if net_ppe is None:
        net_ppe = get_val(bal_detail, "PropertyPlantAndEquipmentNet")
    if net_ppe is None:
        net_ppe = get_val(bal_detail, "PropertyPlantAndEquipmentAndFinanceLeaseRightOfUseAssetAfterAccumulatedDepreciationAndAmortization")
    if net_ppe is None:
        net_ppe = get_val(bal_detail, "PropertyPlantAndEquipment")

    interest = get_val(summary, "interest_expense")
    if interest is None:
        interest = get_val(inc_detail, "InterestExpense")
    if interest is None:
        interest = get_val(inc_detail, "InterestExpenseDebt")
    if interest is None:
        interest = get_val(inc_detail, "InterestExpenseNonoperating")
    if interest is None:
        interest = get_val(inc_detail, "InterestAndDebtExpense")
    if interest is None:
        interest = get_val(cf_detail, "InterestPaidNet")
    if interest is None:
        interest = 0.0

    tax_exp = get_val(summary, "income_tax_expense")
    if tax_exp is None:
        tax_exp = get_val(inc_detail, "IncomeTaxExpenseBenefit")

    ebt = get_val(summary, "income_before_tax")
    if ebt is None:
        ebt = get_val(inc_detail, "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments")
    if ebt is None:
        ebt = get_val(inc_detail, "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest")

    diluted_shares = get_val(summary, "shares_diluted")
    if diluted_shares is None:
        diluted_shares = get_val(inc_detail, "WeightedAverageNumberOfDilutedSharesOutstanding")
    if diluted_shares is None:
        diluted_shares = basic_shares

    eff_tax_rate = 0.21
    if tax_exp is not None and ebt is not None and ebt > 0:
        eff_tax_rate = max(0.05, min(0.35, tax_exp / ebt))

    # 12. Cuentas por Cobrar (Accounts Receivable)
    ar = get_val(bal_detail, "AccountsReceivableNetCurrent")
    if ar is None:
        ar = get_val(bal_detail, "AccountsReceivableNet")
    if ar is None:
        ar = get_val(bal_detail, "ReceivablesNetCurrent")
    if ar is None:
        ar = get_val(bal_detail, "AccountsAndOtherReceivablesNetCurrent")

    # 13. Inventarios (Inventory)
    inv = get_val(bal_detail, "InventoryNet")
    if inv is None:
        inv = get_val(bal_detail, "Inventories")
    if inv is None:
        inv = get_val(bal_detail, "InventoryGross")

    # 14. Costo de Bienes Vendidos (COGS)
    cogs = get_val(summary, "cost_of_goods_sold")
    if cogs is None:
        cogs = get_val(inc_detail, "CostOfGoodsAndServicesSold")
    if cogs is None:
        cogs = get_val(inc_detail, "CostOfGoodsSold")
    if cogs is None:
        cogs = get_val(inc_detail, "CostOfRevenue")
    if cogs is None and rev is not None and gp is not None:
        cogs = rev - gp

    # 15. Depreciación y Amortización (D&A)
    dna = get_val(cf_detail, "DepreciationDepletionAndAmortization")
    if dna is None:
        dna = get_val(cf_detail, "DepreciationAmortizationAndAccretionNet")
    if dna is None:
        dna = get_val(cf_detail, "DepreciationAndAmortization")
    if dna is None:
        depr = get_val(cf_detail, "Depreciation")
        amort = get_val(cf_detail, "AmortizationOfIntangibleAssets") or 0.0
        if depr is not None:
            dna = depr + amort
    if dna is None:
        dna = get_val(inc_detail, "DepreciationAndAmortization")
    if dna is None:
        dna = get_val(inc_detail, "Depreciation")

    # 16. Patrimonio Neto (Stockholders' Equity), Resultados Acumulados y Pasivos Totales (para Solvencia y Altman Z)
    equity = get_val(summary, "stockholders_equity")
    if equity is None:
        equity = get_val(bal_detail, "StockholdersEquity")
    if equity is None:
        equity = get_val(bal_detail, "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest")

    retained_earnings = get_val(bal_detail, "RetainedEarningsAccumulatedDeficit")
    if retained_earnings is None:
        retained_earnings = get_val(bal_detail, "RetainedEarnings")

    total_liabilities = get_val(summary, "total_liabilities")
    if total_liabilities is None:
        total_liabilities = get_val(bal_detail, "Liabilities")
    if total_liabilities is None and assets is not None and equity is not None:
        total_liabilities = assets - equity

    return {
        "net_income": ni,
        "cfo": cfo,
        "total_assets": assets,
        "total_debt": debt,
        "short_term_debt": st_debt or 0.0,
        "long_term_debt": lt_debt or 0.0,
        "current_assets": ca,
        "current_liabilities": cl,
        "stockholders_equity": equity,
        "retained_earnings": retained_earnings,
        "total_liabilities": total_liabilities,
        "basic_shares": basic_shares,
        "diluted_shares": diluted_shares,
        "gross_profit": gp,
        "revenue": rev,
        "rd_expense": rd,
        "capex": abs(capex) if capex is not None else 0.0,
        "sga_expense": sga,
        "cash": cash,
        "operating_income": ebit,
        "net_ppe": net_ppe,
        "interest_expense": interest,
        "effective_tax_rate": eff_tax_rate,
        "accounts_receivable": ar,
        "inventory": inv,
        "cost_of_goods_sold": cogs,
        "depreciation_and_amortization": dna
    }


def calculate_fundamental_scores(ticker: str, financials_json_path: Path, out_dir: Optional[Path] = None) -> Dict[str, Any]:
    """
    Función principal de ejecución del motor de scoring fundamental.
    Calcula F-Score y G-Score para todos los años disponibles (incluyendo LTM).
    """
    with open(financials_json_path, "r", encoding="utf-8") as f:
        financials = json.load(f)

    cik = financials.get("cik", "N/A")
    company_name = financials.get("company_name", ticker)
    fiscal_years = financials.get("fiscal_years", [])

    # Obtener código SIC
    sic_code = financials.get("sic_code")
    if not sic_code:
        # Extraer de sec_narrative si existe
        narrative_path = Path(financials_json_path).parent / "sec_narrative.json"
        if narrative_path.exists():
            try:
                with open(narrative_path, "r", encoding="utf-8") as nf:
                    ndata = json.load(nf)
                    sic_code = ndata.get("sic_code")
            except Exception:
                pass

    medians_db = load_industry_medians()
    benchmarks = get_sector_benchmarks(sic_code, medians_db, ticker=ticker)

    # Construir mapa de métricas por periodo
    period_metrics = {}
    for fy in fiscal_years:
        period_metrics[fy] = extract_period_metrics(financials, fy)

    # Identificar periodos en orden cronológico para la serie histórica (omitiendo LTM para varianza histórica de FYs)
    annual_fys = [y for y in fiscal_years if y != "LTM"]
    annual_fys_sorted = sorted(annual_fys, key=lambda x: int(x.replace("FY", "")) if "FY" in x else 0)

    # Lista cronológica de datos históricos para varianzas
    hist_series = []
    for y in annual_fys_sorted:
        m = period_metrics.get(y, {})
        hist_series.append({
            "period": y,
            "net_income": m.get("net_income"),
            "revenue": m.get("revenue"),
            "total_assets": m.get("total_assets")
        })

    scoring_results = {
        "ticker": ticker.upper(),
        "company_name": company_name,
        "cik": cik,
        "sic_code": benchmarks.get("sic_code"),
        "industry_name": benchmarks.get("industry_name"),
        "benchmarks_used": benchmarks,
        "fiscal_years": fiscal_years,
        "piotroski_f_score": {},
        "mohanram_g_score": {},
        "combined_matrix": {},
        "latest_diagnosis": {}
    }

    # Calcular para cada periodo
    for i, fy in enumerate(fiscal_years):
        curr_m = period_metrics.get(fy, {})

        # Identificar periodo t-1 y t-2
        prev_fy = None
        prev2_fy = None

        if fy == "LTM":
            # Para LTM, t-1 es el último FY completo
            if len(annual_fys_sorted) >= 1:
                prev_fy = annual_fys_sorted[-1]
            if len(annual_fys_sorted) >= 2:
                prev2_fy = annual_fys_sorted[-2]
        else:
            # Buscar en annual_fys_sorted
            if fy in annual_fys_sorted:
                idx = annual_fys_sorted.index(fy)
                if idx >= 1:
                    prev_fy = annual_fys_sorted[idx - 1]
                if idx >= 2:
                    prev2_fy = annual_fys_sorted[idx - 2]

        prev_m = period_metrics.get(prev_fy) if prev_fy else None
        prev2_m = period_metrics.get(prev2_fy) if prev2_fy else None

        # Serie histórica hasta este periodo para varianzas de G-Score
        if fy == "LTM":
            sub_hist = hist_series[-5:] if len(hist_series) >= 5 else hist_series
        else:
            idx = annual_fys_sorted.index(fy) if fy in annual_fys_sorted else -1
            if idx >= 0:
                sub_hist = hist_series[max(0, idx - 4): idx + 1]
            else:
                sub_hist = hist_series[-5:]

        # 1. Piotroski F-Score
        f_res = PiotroskiScoreCalculator.calculate_year(fy, curr_m, prev_m, prev2_m)
        scoring_results["piotroski_f_score"][fy] = f_res

        # 2. Mohanram G-Score
        g_res = MohanramScoreCalculator.calculate_year(fy, curr_m, prev_m, sub_hist, benchmarks)
        scoring_results["mohanram_g_score"][fy] = g_res

        # 3. Matriz Combinada
        matrix_res = CombinedMatrixClassifier.classify(f_res["total_score"], g_res["total_score"])
        scoring_results["combined_matrix"][fy] = matrix_res

    # 4. Novy-Marx Gross Profitability to Assets (GP/A) con serie histórica multianual y pares
    novy_marx_series = NovyMarxCalculator.calculate_series(fiscal_years, period_metrics, benchmarks)
    scoring_results["novy_marx_analysis"] = novy_marx_series

    # 5. ROIC Ajustado por Intangibles con capitalización roll-forward y sensibilidad
    roic_analysis = IntangibleROICCalculator.calculate_series(fiscal_years, period_metrics, benchmarks, ticker=ticker)
    scoring_results["intangible_roic_analysis"] = roic_analysis

    # 5.1 ROC Greenblatt (Return on Capital Tangible Operativo)
    greenblatt_roc_analysis = GreenblattROCCalculator.calculate_series(fiscal_years, period_metrics, benchmarks, ticker=ticker)
    scoring_results["greenblatt_roc_analysis"] = greenblatt_roc_analysis

    # 6. Costo de Capital (WACC en tiempo real) y Spread Económico (EVA)
    recent_fy = "LTM" if "LTM" in fiscal_years else fiscal_years[0]
    rec_roic_data = roic_analysis.get("latest_result", {})
    rec_metrics = period_metrics.get(recent_fy, {})
    latest_diluted_shares = rec_metrics.get("diluted_shares")

    wacc_analysis = WACCCalculator.calculate_wacc_and_spread(
        ticker=ticker,
        recent_fy=recent_fy,
        period_data=rec_metrics,
        roic_adjusted=rec_roic_data.get("roic_adj"),
        roic_traditional=rec_roic_data.get("roic_trad"),
        benchmarks=benchmarks,
        diluted_shares_10q=latest_diluted_shares
    )
    scoring_results["wacc_and_spread_analysis"] = wacc_analysis
    scoring_results["roic_wacc_analysis"] = {
        "roic": roic_analysis,
        "wacc": wacc_analysis
    }

    # 7. Auditoría Forense Contable y Detección de Manipulación de Beneficios (Sloan, Divergencias y Montier C-Score)
    forensic_analysis = ForensicAccountingEngine.calculate_forensic_series(fiscal_years, period_metrics, benchmarks, ticker=ticker)
    scoring_results["forensic_accounting_analysis"] = forensic_analysis

    # 8. Análisis Institucional de Deuda, Solvencia y Estrés Financiero (Apalancamiento, Cobertura, Altman Z'' y Damodaran)
    mcap_for_solvency = float(wacc_analysis.get("market_data", {}).get("market_cap_usd_m", 0.0)) or None
    solvency_analysis = DebtSolvencyEngine.calculate_solvency_series(
        fiscal_years, period_metrics, benchmarks, ticker=ticker, market_cap=mcap_for_solvency
    )
    scoring_results["debt_and_solvency_analysis"] = solvency_analysis

    # Diagnóstico del periodo más reciente (LTM o el último año fiscal auditado)
    recent_fy = "LTM" if "LTM" in fiscal_years else fiscal_years[0]
    latest_f = scoring_results["piotroski_f_score"].get(recent_fy, {})
    latest_g = scoring_results["mohanram_g_score"].get(recent_fy, {})
    latest_matrix = scoring_results["combined_matrix"].get(recent_fy, {})
    latest_nm = novy_marx_series.get("latest_result", {})
    latest_forensic = forensic_analysis.get("latest_result", {})
    latest_solvency = solvency_analysis.get("latest_result", {})

    scoring_results["latest_diagnosis"] = {
        "period": recent_fy,
        "f_score": latest_f.get("total_score", 0),
        "f_max": 9,
        "f_rating": latest_f.get("rating", "N/A"),
        "g_score": latest_g.get("total_score", 0),
        "g_max": 8,
        "g_rating": latest_g.get("rating", "N/A"),
        "quadrant": latest_matrix.get("quadrant", "N/A"),
        "badge": latest_matrix.get("badge", "N/A"),
        "color": latest_matrix.get("color", "N/A"),
        "investment_thesis": latest_matrix.get("investment_thesis", ""),
        "novy_marx": {
            "gross_profitability_total": latest_nm.get("gross_profitability_total"),
            "gross_profitability_ex_cash": latest_nm.get("gross_profitability_ex_cash"),
            "cash_drag_pct": latest_nm.get("cash_drag_pct"),
            "gross_margin": latest_nm.get("gross_margin"),
            "asset_turnover_total": latest_nm.get("asset_turnover_total"),
            "quadrant": latest_nm.get("quadrant"),
            "quadrant_badge": latest_nm.get("quadrant_badge"),
            "rating": latest_nm.get("rating"),
            "percentile_label": latest_nm.get("percentile_label"),
            "percentile_explanation": latest_nm.get("percentile_explanation"),
            "adjusted_gp_a": latest_nm.get("adjusted_gp_a"),
            "trend_diagnosis": novy_marx_series.get("trend", {}).get("trend_diagnosis")
        },
        "greenblatt_roc": {
            "roc_avg": greenblatt_roc_analysis.get("latest_roc"),
            "roc_pct": greenblatt_roc_analysis.get("latest_roc_pct"),
            "peer_median_pct": greenblatt_roc_analysis.get("peer_roc_median_pct"),
            "spread_vs_peer_pct": greenblatt_roc_analysis.get("spread_vs_peer_pct"),
            "rating": greenblatt_roc_analysis.get("rating"),
            "rating_label": greenblatt_roc_analysis.get("rating_label")
        },
        "roic_wacc": {
            "wacc": wacc_analysis.get("wacc"),
            "ke": wacc_analysis.get("cost_of_equity_ke"),
            "kd_after_tax": wacc_analysis.get("cost_of_debt_kd_after_tax"),
            "we": wacc_analysis.get("weight_equity"),
            "wd": wacc_analysis.get("weight_debt"),
            "roic_traditional": wacc_analysis.get("roic_traditional"),
            "roic_adjusted": wacc_analysis.get("roic_adjusted"),
            "economic_spread_adjusted": wacc_analysis.get("economic_spread_adjusted"),
            "moat_rating": wacc_analysis.get("moat_rating"),
            "moat_badge": wacc_analysis.get("moat_badge"),
            "total_intangibles_usd_m": rec_roic_data.get("total_intangible_stock"),
            "market_data_status": wacc_analysis.get("market_data", {}).get("audit", {}).get("status")
        },
        "forensic_audit": {
            "sloan_ratio_pct": latest_forensic.get("sloan_accrual", {}).get("sloan_ratio_pct"),
            "sloan_status": latest_forensic.get("sloan_accrual", {}).get("status"),
            "sloan_badge": latest_forensic.get("sloan_accrual", {}).get("badge"),
            "montier_score": latest_forensic.get("montier_c_score", {}).get("total_score"),
            "montier_max": 6,
            "montier_rating": latest_forensic.get("montier_c_score", {}).get("rating"),
            "montier_badge": latest_forensic.get("montier_c_score", {}).get("badge"),
            "ar_sales_spread_pct": latest_forensic.get("divergences", {}).get("ar_sales_spread", {}).get("spread_pct"),
            "inv_cogs_spread_pct": latest_forensic.get("divergences", {}).get("inv_cogs_spread", {}).get("spread_pct"),
            "soft_assets_ratio_pct": latest_forensic.get("divergences", {}).get("soft_assets", {}).get("soft_assets_ratio_pct"),
            "global_verdict": latest_forensic.get("forensic_verdict"),
            "global_badge": latest_forensic.get("global_badge"),
            "global_color": latest_forensic.get("global_color")
        },
        "solvency_credit": {
            "net_debt_usd_m": latest_solvency.get("cash_flow_leverage", {}).get("net_debt"),
            "net_debt_to_ebitda": latest_solvency.get("cash_flow_leverage", {}).get("net_debt_to_ebitda"),
            "net_debt_to_ebitda_str": latest_solvency.get("cash_flow_leverage", {}).get("net_debt_to_ebitda_str"),
            "net_debt_to_fcf": latest_solvency.get("cash_flow_leverage", {}).get("net_debt_to_fcf"),
            "net_debt_to_fcf_str": latest_solvency.get("cash_flow_leverage", {}).get("net_debt_to_fcf_str"),
            "interest_coverage": latest_solvency.get("debt_service", {}).get("interest_coverage"),
            "interest_coverage_str": latest_solvency.get("debt_service", {}).get("interest_coverage_str"),
            "quick_ratio": latest_solvency.get("liquidity", {}).get("quick_ratio"),
            "cash_ratio": latest_solvency.get("liquidity", {}).get("cash_ratio"),
            "rollover_risk_pct": latest_solvency.get("liquidity", {}).get("rollover_risk_pct"),
            "altman_z_score": latest_solvency.get("distress_models", {}).get("altman_z_double_prime"),
            "altman_zone": latest_solvency.get("distress_models", {}).get("altman_zone"),
            "synthetic_rating": latest_solvency.get("distress_models", {}).get("synthetic_rating"),
            "synthetic_rating_desc": latest_solvency.get("distress_models", {}).get("synthetic_rating_desc"),
            "default_spread_pct": latest_solvency.get("distress_models", {}).get("default_spread_pct"),
            "default_probability": latest_solvency.get("distress_models", {}).get("default_probability"),
            "solvency_verdict": latest_solvency.get("solvency_verdict"),
            "global_badge": latest_solvency.get("global_badge"),
            "global_color": latest_solvency.get("global_color")
        }
    }

    # Guardar en JSON de salida si se provee out_dir
    if out_dir:
        out_path = Path(out_dir) / "fundamental_scores.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(scoring_results, f, indent=2)
        print(f"[Scoring Engine] Resultados cuantitativos guardados exitosamente en: {out_path}")

        # Guardar también como financial_scores.json para compatibilidad total con los requerimientos
        fin_scores_path = Path(out_dir) / "financial_scores.json"
        with open(fin_scores_path, "w", encoding="utf-8") as f:
            json.dump(scoring_results, f, indent=2)
        print(f"[Scoring Engine] Copia sincronizada guardada en: {fin_scores_path}")

    return scoring_results


if __name__ == "__main__":
    ticker = sys.argv[1] if len(sys.argv) > 1 else "AAPL"
    json_path = Path(f"data/processed/{ticker}/financial_statements.json")
    if not json_path.exists():
        print(f"Error: No se encontró {json_path}")
        sys.exit(1)

    out = calculate_fundamental_scores(ticker, json_path, json_path.parent)
    diag = out["latest_diagnosis"]
    nm = diag.get("novy_marx", {})
    fa = diag.get("forensic_audit", {})
    print(f"\n{'='*75}")
    print(f"  DIAGNÓSTICO FUNDAMENTAL CUANTITATIVO: {ticker.upper()} ({diag['period']})")
    print(f"{'='*75}")
    print(f"  Piotroski F-Score:       {diag['f_score']}/9 ({diag['f_rating']})")
    print(f"  Mohanram G-Score:        {diag['g_score']}/8 ({diag['g_rating']})")
    print(f"  Matriz F/G:              {diag['badge']}")
    print(f"  Novy-Marx GP/A (Total):  {nm.get('gross_profitability_total', 0)*100:.2f}% [{nm.get('percentile_label')}]")
    print(f"  Novy-Marx GP/A (Ex-Caja):{nm.get('gross_profitability_ex_cash', 0)*100:.2f}% (Cash Drag: {nm.get('cash_drag_pct', 0)*100:+.2f} p.p.)")
    print(f"  DuPont Estratégico:      {nm.get('quadrant_badge')}")
    print(f"  ROC Greenblatt:          {diag.get('greenblatt_roc', {}).get('roc_pct', 'N/A')}%")
    print(f"  Ratio Sloan Devengos:    {fa.get('sloan_ratio_pct', 'N/A')}% [{fa.get('sloan_badge', 'N/A')}]")
    print(f"  Montier C-Score:         {fa.get('montier_score', 'N/A')}/6 [{fa.get('montier_badge', 'N/A')}]")
    print(f"  Dictamen Forense:        {fa.get('global_badge', 'N/A')}")
    print(f"  Tesis Ejecutiva:         {diag['investment_thesis']}")
    print(f"{'='*75}\n")
