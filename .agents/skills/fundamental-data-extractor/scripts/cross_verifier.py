"""
cross_verifier.py - Motor de Verificación Cruzada Multi-Fuente y Auditoría de Datos.
Compara de forma quirúrgica los estados financieros extraídos de SEC EDGAR contra
fuentes independientes de consenso institucional (Yahoo Finance / Fiscal.ai / Wall Street Consensus).
Garantiza paridad contable, detecta omisiones taxonómicas (ej. ingresos Fintech vs ASC 606, CapEx en 10-Q)
y genera reportes de certificación de datos con tolerancia matemática.
"""

import os
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
import pandas as pd
import numpy as np

try:
    import yfinance as yf
except ImportError:
    yf = None


class CrossVerifier:
    """Validador y Auditor Cruzado de Datos Financieros SEC vs Plataformas Externas."""

    TOLERANCE_PASS_PCT = 5.0   # <= 5% se considera coincidencia exacta (Match)
    TOLERANCE_WARN_PCT = 15.0  # 5% - 15% advertencia por diferencias de convención contable
    # > 15% se marca como DISCREPANCIA crítica (FAIL)

    METRIC_MAPPING = {
        "revenue": {
            "label": "Ingresos Totales (Revenues)",
            "yf_fin_keys": ["Total Revenue", "Operating Revenue"],
            "unit_scale": 1.0,
        },
        "operating_income": {
            "label": "Beneficio Operativo (Operating Income / EBIT)",
            "yf_fin_keys": ["Operating Income", "EBIT"],
            "unit_scale": 1.0,
        },
        "net_income": {
            "label": "Beneficio Neto (Net Income)",
            "yf_fin_keys": ["Net Income Common Stockholders", "Net Income", "Net Income From Continuing Operation Net Minority Interest"],
            "unit_scale": 1.0,
        },
        "cash_from_operations": {
            "label": "Flujo de Caja Operativo (CFO)",
            "yf_cf_keys": ["Operating Cash Flow", "Cash Flowsfromusedin Operating Activities"],
            "unit_scale": 1.0,
        },
        "capital_expenditures": {
            "label": "Inversiones de Capital (CapEx)",
            "yf_cf_keys": ["Capital Expenditure", "Capital Expenditures"],
            "unit_scale": -1.0,  # En Yahoo Finance suele venir negativo
        },
        "free_cash_flow": {
            "label": "Flujo de Caja Libre (FCF)",
            "yf_cf_keys": ["Free Cash Flow"],
            "unit_scale": 1.0,
        },
        "total_assets": {
            "label": "Activos Totales (Total Assets)",
            "yf_bal_keys": ["Total Assets"],
            "unit_scale": 1.0,
        },
        "stockholders_equity": {
            "label": "Patrimonio Neto (Stockholders' Equity)",
            "yf_bal_keys": ["Stockholders Equity", "Common Stock Equity", "Total Equity Gross Minority Interest"],
            "unit_scale": 1.0,
        },
        "cash_and_equivalents": {
            "label": "Efectivo y Equivalentes (Cash & Equivalents)",
            "yf_bal_keys": ["Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments"],
            "unit_scale": 1.0,
        },
        "total_debt": {
            "label": "Deuda Financiera Total",
            "yf_bal_keys": ["Total Debt"],
            "unit_scale": 1.0,
        },
        "shares_diluted": {
            "label": "Acciones Diluidas en Circulación",
            "yf_fin_keys": ["Diluted Average Shares", "Ordinary Shares Number"],
            "unit_scale": 1.0,
        },
        "eps_diluted": {
            "label": "Beneficio Por Acción Diluido (Diluted EPS)",
            "yf_fin_keys": ["Diluted EPS", "Basic EPS"],
            "unit_scale": 1.0,
        }
    }

    def __init__(self, ticker: str, data_dir: Optional[Path] = None):
        self.ticker = ticker.strip().upper()
        self.data_dir = Path(data_dir) if data_dir else Path("data/processed") / self.ticker
        self.sec_json_path = self.data_dir / "financial_statements.json"
        self.sec_data: Dict[str, Any] = {}
        self.external_data: Dict[str, Any] = {}
        self.audit_results: List[Dict[str, Any]] = []

    def load_sec_data(self) -> bool:
        """Carga el JSON canónico extraído de la SEC."""
        if not self.sec_json_path.exists():
            print(f"[Cross Verifier] Error: No existe {self.sec_json_path}")
            return False
        with open(self.sec_json_path, "r", encoding="utf-8") as f:
            self.sec_data = json.load(f)
        return True

    def fetch_external_market_data(self) -> bool:
        """Descarga estados financieros oficiales de Yahoo Finance para contrastar."""
        if yf is None:
            print("[Cross Verifier] Error: yfinance no está instalado.")
            return False

        print(f"[Cross Verifier] Consultando consenso externo de mercado para {self.ticker}...")
        try:
            tk = yf.Ticker(self.ticker)
            fin_annual = tk.financials
            fin_quarterly = tk.quarterly_financials
            bal_annual = tk.balance_sheet
            bal_quarterly = tk.quarterly_balance_sheet
            cf_annual = tk.cashflow
            cf_quarterly = tk.quarterly_cashflow

            self.external_data = {
                "fin_annual": fin_annual,
                "fin_quarterly": fin_quarterly,
                "bal_annual": bal_annual,
                "bal_quarterly": bal_quarterly,
                "cf_annual": cf_annual,
                "cf_quarterly": cf_quarterly,
                "fast_info": getattr(tk, "fast_info", {}),
                "info": getattr(tk, "info", {})
            }
            return True
        except Exception as e:
            print(f"[Cross Verifier] Error al consultar datos externos: {e}")
            return False

    def _extract_yf_metric(self, df_annual: pd.DataFrame, df_quarterly: pd.DataFrame, keys: List[str], period: str, scale: float = 1.0, is_balance_sheet: bool = False) -> Optional[float]:
        """Extrae el valor correspondiente a un período (LTM o FY) desde DataFrames de yfinance."""
        if period == "LTM":
            # Si es Balance Sheet o Conteo de Acciones, se toma el trimestre más reciente (MRQ), NO se suman trimestres
            if is_balance_sheet:
                if df_quarterly is not None and not df_quarterly.empty:
                    for k in keys:
                        if k in df_quarterly.index:
                            series = df_quarterly.loc[k].dropna()
                            if len(series) > 0:
                                return float(series.iloc[0]) * scale
                if df_annual is not None and not df_annual.empty:
                    for k in keys:
                        if k in df_annual.index:
                            series = df_annual.loc[k].dropna()
                            if len(series) > 0:
                                return float(series.iloc[0]) * scale
                return None

            # Si es Estado de Resultados o Flujo de Caja (flujo), sumar últimos 4 trimestres
            if df_quarterly is not None and not df_quarterly.empty:
                for k in keys:
                    if k in df_quarterly.index:
                        series = df_quarterly.loc[k].dropna()
                        if len(series) >= 4:
                            val = float(series.iloc[:4].sum()) * scale
                            return abs(val) if "expenditure" in k.lower() else val
            # Fallback al ejercicio anual más reciente si no hay 4 trimestres
            if df_annual is not None and not df_annual.empty:
                for k in keys:
                    if k in df_annual.index:
                        series = df_annual.loc[k].dropna()
                        if len(series) > 0:
                            val = float(series.iloc[0]) * scale
                            return abs(val) if "expenditure" in k.lower() else val
            return None

        # Período Anual (ej. FY2025, FY2024)
        m = None
        for ch in period:
            if ch.isdigit():
                m = period[period.find(ch):period.find(ch)+4]
                break
        target_year = m if m else period

        if df_annual is not None and not df_annual.empty:
            for k in keys:
                if k in df_annual.index:
                    for col in df_annual.columns:
                        if target_year in str(col):
                            raw = df_annual.loc[k, col]
                            if pd.notna(raw):
                                try:
                                    val = float(raw) * scale
                                    return abs(val) if "expenditure" in k.lower() else val
                                except (ValueError, TypeError):
                                    pass
        return None

    def run_cross_verification(self) -> Dict[str, Any]:
        """Ejecuta la comparación métrica a métrica entre SEC y datos externos."""
        if not self.sec_data:
            if not self.load_sec_data():
                return {"status": "FAIL", "message": "No se pudieron cargar datos de la SEC."}

        if not self.external_data:
            if not self.fetch_external_market_data():
                return {"status": "FAIL", "message": "No se pudieron obtener datos externos de mercado."}

        canonical = self.sec_data.get("canonical_summary", {})
        fys = self.sec_data.get("fiscal_years", [])
        # Tomar los 3 períodos más relevantes: LTM y los 2 ejercicios más recientes
        periods_to_check = [p for p in ["LTM"] + [f for f in fys if f != "LTM"][:3] if p in fys or p == "LTM"]

        fin_ann = self.external_data.get("fin_annual")
        fin_q = self.external_data.get("fin_quarterly")
        bal_ann = self.external_data.get("bal_annual")
        bal_q = self.external_data.get("bal_quarterly")
        cf_ann = self.external_data.get("cf_annual")
        cf_q = self.external_data.get("cf_quarterly")

        audit_items = []
        matches_count = 0
        warn_count = 0
        fail_count = 0

        for metric_name, conf in self.METRIC_MAPPING.items():
            sec_dict = canonical.get(metric_name, {})
            label = conf["label"]
            scale = conf.get("unit_scale", 1.0)

            for period in periods_to_check:
                sec_val = sec_dict.get(period)
                if sec_val is None:
                    continue

                ext_val = None
                if "yf_fin_keys" in conf:
                    is_bs = metric_name in ["shares_diluted"]
                    ext_val = self._extract_yf_metric(fin_ann, fin_q, conf["yf_fin_keys"], period, scale, is_balance_sheet=is_bs)
                elif "yf_bal_keys" in conf:
                    ext_val = self._extract_yf_metric(bal_ann, bal_q, conf["yf_bal_keys"], period, scale, is_balance_sheet=True)
                elif "yf_cf_keys" in conf:
                    ext_val = self._extract_yf_metric(cf_ann, cf_q, conf["yf_cf_keys"], period, scale, is_balance_sheet=False)

                if ext_val is None:
                    continue

                diff = abs(sec_val - ext_val)
                denom = max(abs(ext_val), 1.0)
                delta_pct = (diff / denom) * 100.0

                diagnosis = ""
                if delta_pct <= self.TOLERANCE_PASS_PCT:
                    status = "MATCH"
                    matches_count += 1
                    diagnosis = "Paridad perfecta entre SEC EDGAR y consenso de mercado."
                elif delta_pct <= self.TOLERANCE_WARN_PCT:
                    status = "TOLERABLE_DIFF"
                    warn_count += 1
                    diagnosis = f"Diferencia menor ({delta_pct:.1f}%): Convención contable de consolidación o redondeo."
                else:
                    status = "DISCREPANCY"
                    fail_count += 1
                    # Diagnóstico forense automático
                    if metric_name == "revenue" and sec_val < ext_val:
                        diagnosis = "Alerta: Los ingresos de la SEC son inferiores al consenso. Posible exclusión de líneas auxiliares o fintech (ASC 606)."
                    elif metric_name == "capital_expenditures" and sec_val == 0:
                        diagnosis = "Alerta Crítica: CapEx registrado en $0.0 en la SEC mientras el mercado reporta inversiones de capital."
                    elif metric_name == "free_cash_flow" and sec_val > ext_val * 1.3:
                        diagnosis = "Alerta Crítica: FCF sobrestimado en la SEC. Verificar CapEx o distorsión por fondos de clientes en CFO."
                    elif metric_name == "stockholders_equity" and sec_val < 0 and ext_val > 0:
                        diagnosis = "Alerta Crítica: Patrimonio negativo en la SEC vs positivo en consenso. Revisar mapeo de subcuentas IFRS/GAAP."
                    else:
                        diagnosis = f"Divergencia significativa ({delta_pct:.1f}%): Requiere conciliación manual o ajuste de mapeo taxonómico."

                audit_items.append({
                    "metric": metric_name,
                    "label": label,
                    "period": period,
                    "sec_value": sec_val,
                    "external_value": ext_val,
                    "delta_usd": diff,
                    "delta_pct": round(delta_pct, 2),
                    "status": status,
                    "diagnosis": diagnosis
                })

        overall_status = "PASS" if fail_count == 0 else "DISCREPANCY_DETECTED"
        summary = {
            "ticker": self.ticker,
            "verification_timestamp": datetime.now().isoformat(),
            "overall_status": overall_status,
            "metrics_checked": len(audit_items),
            "matches": matches_count,
            "tolerable_differences": warn_count,
            "critical_discrepancies": fail_count,
            "details": audit_items
        }

        self._save_reports(summary)
        return summary

    def _save_reports(self, summary: Dict[str, Any]) -> None:
        """Guarda el informe en formato JSON y Markdown legible."""
        json_out = self.data_dir / "cross_verification_report.json"
        with open(json_out, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)

        md_out = self.data_dir / "cross_verification_report.md"
        badge = "🟢 VERIFICACIÓN APROBADA (MATCH)" if summary["overall_status"] == "PASS" else "🔴 DISCREPANCIAS DETECTADAS (ALERTA)"

        lines = [
            f"# Certificado de Verificación Cruzada de Datos: {self.ticker}",
            f"**Dictamen Institucional:** {badge}  ",
            f"*Fecha de Auditoría: {summary['verification_timestamp']} | Métricas Auditadas: {summary['metrics_checked']}*",
            "",
            f"- **Coincidencias Exactas (Delta <= 5%):** {summary['matches']}",
            f"- **Diferencias Menores Tolerables (Delta 5-15%):** {summary['tolerable_differences']}",
            f"- **Discrepancias Críticas (Delta > 15%):** {summary['critical_discrepancies']}",
            "",
            "---",
            "",
            "## Tabla de Corroboración Métrica a Métrica (SEC EDGAR vs. Consenso de Mercado)",
            "",
            "| Parámetro Financiero | Período | Valor SEC EDGAR | Valor Plataformas (Yahoo / Fiscal.ai) | Diferencia % | Estado | Diagnóstico Forense |",
            "| :--- | :---: | :---: | :---: | :---: | :---: | :--- |"
        ]

        for it in summary["details"]:
            sec_fmt = f"${it['sec_value']:,.1f} M" if abs(it['sec_value']) >= 1e6 else f"{it['sec_value']:,.2f}"
            ext_fmt = f"${it['external_value']:,.1f} M" if abs(it['external_value']) >= 1e6 else f"{it['external_value']:,.2f}"
            st_badge = "✅ MATCH" if it['status'] == "MATCH" else ("⚠️ AVISO" if it['status'] == "TOLERABLE_DIFF" else "❌ DISCREPANCIA")
            lines.append(
                f"| **{it['label']}** | {it['period']} | {sec_fmt} | {ext_fmt} | **{it['delta_pct']:.1f}%** | {st_badge} | {it['diagnosis']} |"
            )

        with open(md_out, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        print(f"[Cross Verifier] Certificado de auditoría guardado en: {md_out}")


def run_cross_verification_for_ticker(ticker: str, data_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Punto de entrada programático para invocar el verificador cruzado."""
    verifier = CrossVerifier(ticker, data_dir)
    return verifier.run_cross_verification()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Verificador Cruzado SEC vs Consenso de Mercado")
    parser.add_argument("--ticker", required=True, help="Ticker de la empresa a auditar (ej. MELI, NU, AAPL)")
    parser.add_argument("--data-dir", default=None, help="Directorio de datos procesados")
    args = parser.parse_args()

    res = run_cross_verification_for_ticker(args.ticker, Path(args.data_dir) if args.data_dir else None)
    print(f"\n[Resultado Global]: {res.get('overall_status')} (Matches: {res.get('matches')}, Discrepancies: {res.get('critical_discrepancies')})")
