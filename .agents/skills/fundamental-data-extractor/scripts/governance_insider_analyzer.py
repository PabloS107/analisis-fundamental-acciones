"""
governance_insider_analyzer.py - Motor de Análisis de Gobernanza Corporativa,
Sentimiento de Insiders (Form 4 y 144) y Radar de Alertas Tempranas (Form 8-K).

Extrae y analiza de SEC EDGAR:
1. Formulario 8-K: Detección de hechos materiales, cambios en el C-suite (Item 5.02),
   cambios de auditor (Item 4.01) y estrés financiero/deuda (Item 2.04).
2. Formulario 4: Registro de transacciones de directivos, diferenciando compras
   en mercado abierto (Código P), ventas rutinarias bajo planes Rule 10b5-1,
   ventas discrecionales y retenciones de impuestos (Código F).
3. Formulario 144: Avisos anticipados de venta de acciones restringidas y banderas de anomalía.

Genera explicaciones educativas para cada evento y diagnósticos fundamentales para la tesis de inversión.
"""

import os
import sys
import re
import json
import argparse
from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd

from edgar import Company, set_identity

try:
    from sec_rate_limiter import sec_call_with_retry, default_rate_limiter
except ImportError:
    try:
        from .sec_rate_limiter import sec_call_with_retry, default_rate_limiter
    except ImportError:
        def sec_call_with_retry(fn, *args, **kwargs):
            return fn(*args, **kwargs)
        default_rate_limiter = None


# =====================================================================
# DICCIONARIOS EDUCATIVOS DE ÍTEMS REGULATORIOS DE LA SEC
# =====================================================================

ITEMS_8K_GUIDE = {
    "Item 1.01": {
        "title": "Entrada en un Acuerdo Comercial Material No Ordinario",
        "description": "La compañía ha formalizado un contrato estratégico fuera del curso ordinario (alianzas clave, acuerdos de licencia o exclusividad, contratos con proveedores estratégicos).",
        "risk_level": "NEUTRAL_TO_POSITIVE",
        "diagnostic_hint": "Evaluar si el contrato amplía el foso defensivo o genera dependencia operativa."
    },
    "Item 1.02": {
        "title": "Terminación de un Acuerdo Comercial Material",
        "description": "Ruptura, cancelación o vencimiento anticipado de un contrato de negocio crítico.",
        "risk_level": "WARNING",
        "diagnostic_hint": "Alerta de riesgo comercial: analizar si supone pérdida de ingresos relevantes o deterioro de relaciones con socios clave."
    },
    "Item 2.01": {
        "title": "Adquisición o Disposición Significativa de Activos (M&A)",
        "description": "Operaciones corporativas de fusión, adquisición (M&A) o venta sustancial de filiales o unidades de negocio.",
        "risk_level": "WATCH",
        "diagnostic_hint": "Examinar el precio pagado (múltiplos), el apalancamiento asumido y el riesgo de integración del negocio adquirido."
    },
    "Item 2.02": {
        "title": "Resultados de Operaciones y Condición Financiera",
        "description": "Publicación trimestral de resultados financieros y notas de prensa de resultados antes de la presentación formal del 10-Q o 10-K.",
        "risk_level": "NEUTRAL",
        "diagnostic_hint": "Avance de cifras financieras oficiales auditadas o preliminares."
    },
    "Item 2.03": {
        "title": "Creación de una Obligación Financiera Directa o Fuera de Balance",
        "description": "Emisión de nueva deuda corporativa, suscripción de líneas de crédito sindicadas o contingencias fuera de balance.",
        "risk_level": "WATCH",
        "diagnostic_hint": "Monitorear el aumento de deuda bruta, tipos de interés acordados y fechas de vencimiento."
    },
    "Item 2.04": {
        "title": "Eventos de Aceleración o Impago de Deuda (Default / Covenants)",
        "description": "Alerta máxima de solvencia: la compañía ha incumplido pagos de deuda o vulnerado covenants bancarios, provocando la exigibilidad inmediata de los pasivos.",
        "risk_level": "CRITICAL_RED_FLAG",
        "diagnostic_hint": "¡Bandera roja crítica! Riesgo severo de reestructuración forzosa, quiebra o dilución masiva de accionistas."
    },
    "Item 3.01": {
        "title": "Aviso de Incumplimiento de Estándares de Cotización (Delisting)",
        "description": "Notificación oficial de la bolsa (NASDAQ / NYSE) de que la empresa no cumple requisitos mínimos (precio < $1, retraso en presentar estados contables).",
        "risk_level": "CRITICAL_RED_FLAG",
        "diagnostic_hint": "Riesgo inminente de exclusión de cotización y colapso de liquidez para los accionistas."
    },
    "Item 4.01": {
        "title": "Cambio de Contables / Auditores Independientes",
        "description": "Cese, dimisión o sustitución de la firma de auditoría independiente de la compañía.",
        "risk_level": "HIGH_WARNING",
        "diagnostic_hint": "Alerta forense primordial: investigar si existieron discrepancias contables o desacuerdos en principios contables US-GAAP con el auditor saliente."
    },
    "Item 5.01": {
        "title": "Cambio en el Control de la Compañía",
        "description": "Toma de control hostil, compra mayoritaria o cambio significativo en la estructura del accionariado de control.",
        "risk_level": "HIGH_IMPACT",
        "diagnostic_hint": "Evaluar la alineación del nuevo accionista de control con los inversores minoritarios."
    },
    "Item 5.02": {
        "title": "Salida o Nombramiento de Directores y C-Suite; Acuerdos de Compensación",
        "description": "Modificaciones en los cargos de máxima responsabilidad (CEO, CFO, Director General) o cambios en los paquetes de compensación e incentivos en acciones.",
        "risk_level": "WATCH_GOVERNANCE",
        "diagnostic_hint": "Comprobar si es un relevo planificado y ordenado o una dimisión abrupta. Analizar si la compensación incentiva el valor por acción a largo plazo."
    },
    "Item 5.03": {
        "title": "Enmiendas a Estatutos Corporativos o Código de Ética",
        "description": "Modificación de estatutos, derechos de voto o normas de gobernanza interna.",
        "risk_level": "NEUTRAL",
        "diagnostic_hint": "Verificar que las enmiendas no reduzcan los derechos de voto o protección de los accionistas minoritarios."
    },
    "Item 7.01": {
        "title": "Regulación FD (Fair Disclosure)",
        "description": "Divulgación pública obligatoria de presentaciones a inversores para garantizar acceso equitativo a la información de mercado.",
        "risk_level": "NEUTRAL",
        "diagnostic_hint": "Información cualitativa compartida con analistas o conferencias del sector."
    },
    "Item 8.01": {
        "title": "Otros Eventos Materiales no Clasificados",
        "description": "Cualquier otro hecho de relevancia material que la directiva decida comunicar formalmente a los accionistas.",
        "risk_level": "NEUTRAL",
        "diagnostic_hint": "Hechos corporativos diversos de interés general."
    }
}

FORM4_CODES_GUIDE = {
    "P": {
        "name": "Compra en Mercado Abierto (Open Market Purchase)",
        "description": "El directivo compra acciones con dinero propio de su bolsillo a precios de cotización de mercado.",
        "signal": "BULLISH_CONVICTION",
        "impact": "Máxima señal de convicción interna: ningún directivo compra con su patrimonio personal a menos que considere que la acción está infravalorada."
    },
    "S": {
        "name": "Venta en Mercado Abierto (Open Market Sale)",
        "description": "Venta de acciones en el mercado secundario. Debe diferenciarse entre ventas por plan 10b5-1 o ventas discrecionales.",
        "signal": "NEUTRAL_TO_BEARISH",
        "impact": "Las ventas bajo planes 10b5-1 son automáticas y rutinarias. Las ventas discrecionales a precios máximos sugieren toma de beneficios."
    },
    "F": {
        "name": "Retención Fiscal (Tax Withholding)",
        "description": "Entrega obligatoria o retención automática de acciones para cubrir el pago de impuestos derivados de la consolidación de RSUs.",
        "signal": "NEUTRAL_ROUTINE",
        "impact": "Operación puramente administrativa/fiscal. No implica en absoluto pérdida de confianza en la compañía."
    },
    "A": {
        "name": "Concesión de Capital (Grant / Award)",
        "description": "Entrega de opciones sobre acciones o unidades de acciones restringidas (RSUs) como parte de su retribución.",
        "signal": "ALIGNED_INCENTIVE",
        "impact": "Incentivo a largo plazo para alinear a los directivos con el rendimiento para el accionista."
    },
    "M": {
        "name": "Ejercicio de Opciones (Option Exercise)",
        "description": "Conversión de opciones de compra sobre acciones acumuladas.",
        "signal": "NEUTRAL",
        "impact": "Aumenta la tenencia bruta de acciones de los directivos tras el pago del precio de ejercicio."
    }
}

RULE144_GUIDE = {
    "definition": "La Regla 144 de la SEC regula la venta pública de acciones restringidas o en manos de personas de control (insiders).",
    "purpose": "Exige que los directivos notifiquen formalmente a la SEC (Formulario 144) su intención de vender antes o en el momento de dar la orden de venta.",
    "is_10b5_1": "Si la venta está amparada por un plan Rule 10b5-1, fue programada con meses de antelación sin conocimiento de información privilegiada.",
    "discretionary_sale": "Si la venta NO está amparada por un plan 10b5-1, el directivo está vendiendo de forma discrecional en el mercado abierto.",
    "large_liquidation": "Alerta cuando el volumen propuesto a vender representa un porcentaje atípicamente elevado de la posición total del directivo."
}


def load_sec_config():
    """Carga configuración del entorno."""
    possible_paths = [
        Path("config/sec_config.json"),
        Path(__file__).resolve().parents[4] / "config" / "sec_config.json",
        Path(__file__).resolve().parents[3] / "config" / "sec_config.json",
    ]
    for p in possible_paths:
        if p.exists():
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
    return {
        "sec_identity": "Pablo Inversiones pablo_inversiones@gmail.com",
        "google_drive_base_path": "G:\\Mi unidad\\analisis fundamental",
        "local_output_path": "data\\processed"
    }


# =====================================================================
# 1. SCANNER DE FORMULARIO 8-K
# =====================================================================

def scan_8k_filings(company, max_filings=25):
    """Escanea los formularios 8-K recientes, mapea ítems, extrae contexto y elabora diagnósticos."""
    print(f"[Governance Analyzer] Escaneando formularios 8-K en SEC EDGAR...")
    filings = sec_call_with_retry(company.get_filings, form="8-K")
    if not filings or len(filings) == 0:
        return []

    results = []
    target_count = min(max_filings, len(filings))
    
    for i in range(target_count):
        f = filings[i]
        date_str = str(f.filing_date)
        try:
            if default_rate_limiter:
                default_rate_limiter.pace()
            obj = sec_call_with_retry(f.obj)
            items_raw = getattr(obj, "items", []) or []
            if not items_raw and hasattr(f, "items"):
                items_raw = [f.items] if isinstance(f.items, str) else list(f.items)
                
            items_clean = []
            for it in items_raw:
                s = str(it).strip()
                if not s.startswith("Item"):
                    s = f"Item {s}"
                items_clean.append(s)
                
            if not items_clean:
                continue
                
            # Extraer texto resumen de los ítems
            descriptions = []
            explanations = []
            diagnostics = []
            highest_risk = "LOW"
            
            for it in items_clean:
                guide = ITEMS_8K_GUIDE.get(it, {
                    "title": f"Hecho Regulatorio ({it})",
                    "description": "Evento de notificación corporativa ante la SEC.",
                    "risk_level": "NEUTRAL",
                    "diagnostic_hint": "Evento regulatorio ordinario."
                })
                descriptions.append(guide["title"])
                explanations.append(guide["description"])
                diagnostics.append(guide["diagnostic_hint"])
                
                if guide["risk_level"] in ["CRITICAL_RED_FLAG"]:
                    highest_risk = "CRITICAL"
                elif guide["risk_level"] in ["HIGH_WARNING", "HIGH_IMPACT"] and highest_risk != "CRITICAL":
                    highest_risk = "HIGH"
                elif guide["risk_level"] in ["WATCH_GOVERNANCE", "WATCH"] and highest_risk not in ["CRITICAL", "HIGH"]:
                    highest_risk = "MEDIUM"

            # Previsualización del contenido
            text_preview = ""
            try:
                for it in items_clean:
                    if hasattr(obj, "__getitem__") and it in obj.items:
                        raw_sec_text = str(obj[it])
                        clean_t = " ".join(raw_sec_text.split())
                        if len(clean_t) > 20:
                            text_preview = clean_t[:350] + ("..." if len(clean_t) > 350 else "")
                            break
            except Exception:
                text_preview = "Contenido extraído del formulario oficial SEC."
                
            # Diagnóstico contextualizado específico para ítems clave
            custom_diag = " | ".join(diagnostics)
            if "Item 5.02" in items_clean:
                if "transition" in text_preview.lower() or "chief executive officer" in text_preview.lower():
                    custom_diag = "Transición en la Dirección General (CEO): Relevo formal de liderazgo ejecutivo registrado ante la SEC. Verificar continuidad estratégica y alineación de incentivos."
                else:
                    custom_diag = "Cambio o asignación en el equipo directivo/consejo de administración y enmienda de planes de compensación."
            elif "Item 4.01" in items_clean:
                custom_diag = "ALERTA FORENSE CRÍTICA: Sustitución de auditor independiente. Revisar si hubo desacuerdos contables con la administración."
            elif "Item 2.04" in items_clean:
                custom_diag = "ALERTA DE LIQUIDEZ Y DEUDA: Notificación de aceleración o impago de obligaciones financieras."
                
            results.append({
                "filing_date": date_str,
                "accession_number": str(f.accession_number),
                "items": items_clean,
                "title": " / ".join(descriptions),
                "explanation": " ".join(explanations),
                "diagnostic": custom_diag,
                "risk_rating": highest_risk,
                "text_snippet": text_preview
            })
        except Exception as e:
            continue

    print(f"[Governance Analyzer] Procesados {len(results)} formularios 8-K.")
    return results


# =====================================================================
# 1.1 SCANNER DE FORMULARIO 6-K (FOREIGN PRIVATE ISSUERS - FPI)
# =====================================================================

def check_is_foreign_private_issuer(company):
    """Verifica si la empresa es un Foreign Private Issuer (FPI) que reporta bajo 20-F / 40-F / 6-K."""
    try:
        f_20f = sec_call_with_retry(company.get_filings, form="20-F")
        if f_20f is not None and len(f_20f) > 0:
            return True
        f_40f = sec_call_with_retry(company.get_filings, form="40-F")
        if f_40f is not None and len(f_40f) > 0:
            return True
    except Exception:
        pass
    return False


def scan_6k_filings(company, max_filings=25):
    """Escanea los formularios 6-K recientes de Emisores Privados Extranjeros (FPI)."""
    print(f"[Governance Analyzer] Escaneando formularios 6-K (FPI / Extranjero) en SEC EDGAR...")
    filings = sec_call_with_retry(company.get_filings, form="6-K")
    if not filings or len(filings) == 0:
        return []

    results = []
    target_count = min(max_filings, len(filings))
    for i in range(target_count):
        f = filings[i]
        date_str = str(f.filing_date)
        try:
            desc = getattr(f, "description", "") or getattr(f, "document_description", "") or "Informe periódico o hecho de relevancia material (Formulario 6-K)"
            results.append({
                "filing_date": date_str,
                "accession_number": str(getattr(f, "accession_number", "")),
                "title": "Hecho de Relevancia Material / Informe Periódico FPI (Formulario 6-K)",
                "description": desc,
                "diagnostic": "Comunicación corporativa periódica bajo estándares del regulador del país de origen y la SEC.",
                "risk_rating": "LOW"
            })
        except Exception:
            continue
    print(f"[Governance Analyzer] Procesados {len(results)} formularios 6-K.")
    return results



# =====================================================================
# 2. SCANNER DE FORMULARIO 4 (INSIDER TRADING)
# =====================================================================

def scan_form4_filings(company, max_filings=40):
    """Escanea las transacciones de Form 4, separa compras abiertas, ventas 10b5-1 y retenciones fiscales."""
    print(f"[Governance Analyzer] Escaneando transacciones de insiders (Formulario 4)...")
    filings = sec_call_with_retry(company.get_filings, form="4")
    if not filings or len(filings) == 0:
        return {"summary": {}, "transactions": []}

    target_count = min(max_filings, len(filings))
    raw_txs = []
    
    total_open_market_buys_usd = 0.0
    total_open_market_buys_shares = 0
    total_10b5_sales_usd = 0.0
    total_10b5_sales_shares = 0
    total_discretionary_sales_usd = 0.0
    total_discretionary_sales_shares = 0
    total_tax_withholding_shares = 0
    total_grants_shares = 0
    
    insiders_activity = {}

    for i in range(target_count):
        f = filings[i]
        date_str = str(f.filing_date)
        try:
            if default_rate_limiter:
                default_rate_limiter.pace()
            obj = sec_call_with_retry(f.obj)
            insider = getattr(obj, "insider_name", "Desconocido") or "Desconocido"
            position = getattr(obj, "position", "Directivo") or "Directivo"
            
            if insider not in insiders_activity:
                insiders_activity[insider] = {
                    "position": position,
                    "buys_usd": 0.0,
                    "sales_10b5_usd": 0.0,
                    "sales_discretionary_usd": 0.0,
                    "shares_bought": 0,
                    "shares_sold": 0,
                    "grants": 0,
                    "tx_count": 0
                }
            insiders_activity[insider]["tx_count"] += 1
            
            # Revisar notas al pie por mención a Rule 10b5-1
            is_10b5_1_general = False
            try:
                fn_text = str(getattr(obj, "footnotes", "")).lower()
                if "10b5-1" in fn_text or "10b5" in fn_text or "rule 10b5" in fn_text:
                    is_10b5_1_general = True
            except Exception:
                pass
                
            # 1. Compras en mercado abierto (Código P)
            try:
                buys_df = obj.common_stock_purchases
                if buys_df is not None and not buys_df.empty:
                    for _, row in buys_df.iterrows():
                        sh = float(row.get("Shares", 0) or 0)
                        pr = float(row.get("Price", 0) or 0)
                        val = sh * pr
                        total_open_market_buys_usd += val
                        total_open_market_buys_shares += int(sh)
                        insiders_activity[insider]["buys_usd"] += val
                        insiders_activity[insider]["shares_bought"] += int(sh)
                        
                        raw_txs.append({
                            "filing_date": date_str,
                            "insider": insider,
                            "position": position,
                            "type": "COMPRA_MERCADO_ABIERTO",
                            "code": "P",
                            "shares": int(sh),
                            "price": round(pr, 2),
                            "total_usd": round(val, 2),
                            "is_10b5_1": False,
                            "explanation": FORM4_CODES_GUIDE["P"]["description"],
                            "diagnostic": "MÁXIMA CONVICCIÓN ALCISTA: Compra directa con fondos propios en mercado abierto."
                        })
            except Exception:
                pass
                
            # 2. Ventas en mercado abierto (Código S)
            try:
                sales_df = obj.common_stock_sales
                if sales_df is not None and not sales_df.empty:
                    for _, row in sales_df.iterrows():
                        sh = float(row.get("Shares", 0) or 0)
                        pr = float(row.get("Price", 0) or 0)
                        val = sh * pr
                        
                        row_fn = str(row.get("footnotes", "")).lower()
                        is_10b5 = is_10b5_1_general or ("10b5-1" in row_fn or "10b5" in row_fn)
                        
                        if is_10b5:
                            total_10b5_sales_usd += val
                            total_10b5_sales_shares += int(sh)
                            insiders_activity[insider]["sales_10b5_usd"] += val
                            diag = "VENTA RUTINARIA (PLAN 10b5-1): Venta programada previamente para diversificación o liquidez periódica."
                            tx_type = "VENTA_PROGRAMADA_10B5"
                        else:
                            total_discretionary_sales_usd += val
                            total_discretionary_sales_shares += int(sh)
                            insiders_activity[insider]["sales_discretionary_usd"] += val
                            diag = "VENTA DISCRECIONAL: Venta no programada en mercado abierto; monitorear si coincide con máximos históricos."
                            tx_type = "VENTA_DISCRECIONAL"
                            
                        insiders_activity[insider]["shares_sold"] += int(sh)
                        raw_txs.append({
                            "filing_date": date_str,
                            "insider": insider,
                            "position": position,
                            "type": tx_type,
                            "code": "S",
                            "shares": int(sh),
                            "price": round(pr, 2),
                            "total_usd": round(val, 2),
                            "is_10b5_1": is_10b5,
                            "explanation": FORM4_CODES_GUIDE["S"]["description"],
                            "diagnostic": diag
                        })
            except Exception:
                pass
                
            # 3. Extracción unificada a través de get_transaction_activities()
            try:
                activities = obj.get_transaction_activities() if hasattr(obj, "get_transaction_activities") else []
                for act in activities:
                    act_code = getattr(act, "code", "")
                    sh = float(getattr(act, "shares", 0) or 0)
                    pr = float(getattr(act, "price_per_share", 0) or getattr(act, "value", 0) or 0)
                    val = sh * pr if pr > 0 else 0.0
                    fn_act = str(getattr(act, "footnotes_text", "")).lower()
                    is_10b5 = is_10b5_1_general or ("10b5-1" in fn_act or "10b5" in fn_act)
                    
                    if act_code == "P" and sh > 0 and not any(r["filing_date"] == date_str and r["insider"] == insider and r["code"] == "P" and r["shares"] == int(sh) for r in raw_txs):
                        total_open_market_buys_usd += val
                        total_open_market_buys_shares += int(sh)
                        insiders_activity[insider]["buys_usd"] += val
                        insiders_activity[insider]["shares_bought"] += int(sh)
                        raw_txs.append({
                            "filing_date": date_str,
                            "insider": insider,
                            "position": position,
                            "type": "COMPRA_MERCADO_ABIERTO",
                            "code": "P",
                            "shares": int(sh),
                            "price": round(pr, 2),
                            "total_usd": round(val, 2),
                            "is_10b5_1": False,
                            "explanation": FORM4_CODES_GUIDE.get("P", {}).get("description", "Compra en mercado abierto"),
                            "diagnostic": "MÁXIMA CONVICCIÓN ALCISTA: Compra directa con fondos propios en mercado abierto."
                        })
                    elif act_code == "S" and sh > 0 and not any(r["filing_date"] == date_str and r["insider"] == insider and r["code"] == "S" and r["shares"] == int(sh) for r in raw_txs):
                        if is_10b5:
                            total_10b5_sales_usd += val
                            total_10b5_sales_shares += int(sh)
                            insiders_activity[insider]["sales_10b5_usd"] += val
                            diag = "VENTA RUTINARIA (PLAN 10b5-1): Venta programada previamente para diversificación o liquidez periódica."
                            tx_type = "VENTA_PROGRAMADA_10B5"
                        else:
                            total_discretionary_sales_usd += val
                            total_discretionary_sales_shares += int(sh)
                            insiders_activity[insider]["sales_discretionary_usd"] += val
                            diag = "VENTA DISCRECIONAL: Venta no programada en mercado abierto; monitorear si coincide con máximos históricos."
                            tx_type = "VENTA_DISCRECIONAL"
                        insiders_activity[insider]["shares_sold"] += int(sh)
                        raw_txs.append({
                            "filing_date": date_str,
                            "insider": insider,
                            "position": position,
                            "type": tx_type,
                            "code": "S",
                            "shares": int(sh),
                            "price": round(pr, 2),
                            "total_usd": round(val, 2),
                            "is_10b5_1": is_10b5,
                            "explanation": FORM4_CODES_GUIDE.get("S", {}).get("description", "Venta en mercado abierto"),
                            "diagnostic": diag
                        })
                    elif act_code == "A" and sh > 0 and not any(r["filing_date"] == date_str and r["insider"] == insider and r["code"] == "A" and r["shares"] == int(sh) for r in raw_txs):
                        total_grants_shares += int(sh)
                        insiders_activity[insider]["grants"] += int(sh)
                        raw_txs.append({
                            "filing_date": date_str,
                            "insider": insider,
                            "position": position,
                            "type": "CONCESIÓN_RSU_ACCIONES",
                            "code": "A",
                            "shares": int(sh),
                            "price": 0.0,
                            "total_usd": 0.0,
                            "is_10b5_1": False,
                            "explanation": FORM4_CODES_GUIDE.get("A", {}).get("description", "Concesión de capital"),
                            "diagnostic": "INCENTIVO DE CAPITAL: Asignación de unidades de acciones restringidas ligadas a permanencia y objetivos de valor."
                        })
            except Exception:
                pass
        except Exception:
            continue

    summary = {
        "filings_analyzed": target_count,
        "total_open_market_buys_usd": round(total_open_market_buys_usd, 2),
        "total_open_market_buys_shares": total_open_market_buys_shares,
        "total_10b5_sales_usd": round(total_10b5_sales_usd, 2),
        "total_10b5_sales_shares": total_10b5_sales_shares,
        "total_discretionary_sales_usd": round(total_discretionary_sales_usd, 2),
        "total_discretionary_sales_shares": total_discretionary_sales_shares,
        "total_grants_shares": total_grants_shares,
        "ratio_10b5_vs_discretionary_pct": round((total_10b5_sales_usd / (total_10b5_sales_usd + total_discretionary_sales_usd) * 100), 1) if (total_10b5_sales_usd + total_discretionary_sales_usd) > 0 else 100.0,
        "active_insiders_count": len(insiders_activity),
        "insiders_breakdown": insiders_activity
    }
    
    print(f"[Governance Analyzer] Procesadas {len(raw_txs)} transacciones de directivos.")
    return {"summary": summary, "transactions": raw_txs}


# =====================================================================
# 3. SCANNER DE FORMULARIO 144 (AVISOS PREVIOS DE VENTA)
# =====================================================================

def scan_form144_filings(company, max_filings=20):
    """Escanea avisos preventivos de venta bajo la Regla 144, detectando banderas de anomalía."""
    print(f"[Governance Analyzer] Escaneando avisos preventivos de venta (Formulario 144)...")
    filings = sec_call_with_retry(company.get_filings, form="144")
    if not filings or len(filings) == 0:
        return {"summary": {}, "notices": []}

    target_count = min(max_filings, len(filings))
    notices = []
    
    total_market_value_usd = 0.0
    total_shares_to_sell = 0
    count_10b5 = 0
    count_discretionary = 0
    anomalies_detected = []

    for i in range(target_count):
        f = filings[i]
        date_str = str(f.filing_date)
        try:
            if default_rate_limiter:
                default_rate_limiter.pace()
            obj = sec_call_with_retry(f.obj)
            seller = getattr(obj, "person_selling", "Desconocido") or "Desconocido"
            shares = int(getattr(obj, "units_to_be_sold", 0) or 0)
            mv = float(getattr(obj, "market_value", 0.0) or 0.0)
            is_10b5 = bool(getattr(obj, "is_10b5_1_plan", False))
            is_large = bool(getattr(obj, "is_large_liquidation", False))
            anom_flags = getattr(obj, "anomaly_flags", []) or []
            
            total_market_value_usd += mv
            total_shares_to_sell += shares
            
            if is_10b5:
                count_10b5 += 1
                plan_diag = "Venta amparada bajo plan ciego Rule 10b5-1 (programada con antelación)."
            else:
                count_discretionary += 1
                plan_diag = "Venta NO sujeta a plan 10b5-1: Venta de acciones restringidas ejecutada con discreción inmediata."
                
            custom_notes = []
            if is_large:
                custom_notes.append("Liquidación de gran volumen respecto a su tenencia habitual.")
            if "SHORT_HOLD" in anom_flags:
                custom_notes.append("Período de tenencia atípicamente corto antes de la liquidación.")
            if not custom_notes:
                custom_notes.append("Trámite ordinario de notificación de venta de acciones restringidas.")
                
            notices.append({
                "filing_date": date_str,
                "person_selling": seller,
                "shares_to_sell": shares,
                "market_value_usd": round(mv, 2),
                "is_10b5_1": is_10b5,
                "is_large_liquidation": is_large,
                "anomaly_flags": anom_flags,
                "diagnostic": f"{plan_diag} {' '.join(custom_notes)}"
            })
            
            if anom_flags or is_large or not is_10b5:
                anomalies_detected.append({
                    "date": date_str,
                    "seller": seller,
                    "market_value_usd": round(mv, 2),
                    "is_10b5_1": is_10b5,
                    "flags": anom_flags,
                    "is_large": is_large
                })
        except Exception:
            continue

    summary = {
        "notices_analyzed": target_count,
        "total_shares_proposed": total_shares_to_sell,
        "total_value_proposed_usd": round(total_market_value_usd, 2),
        "notices_under_10b5": count_10b5,
        "notices_discretionary": count_discretionary,
        "notices_with_anomalies_count": len(anomalies_detected)
    }
    
    print(f"[Governance Analyzer] Procesados {len(notices)} avisos del Formulario 144.")
    return {"summary": summary, "notices": notices, "anomalies": anomalies_detected}


# =====================================================================
# 4. ORQUESTADOR Y SCORECARD DE GOBERNANZA INTEGRADO
# =====================================================================

def analyze_governance_and_insiders(ticker="AAPL", output_dir=None):
    """Ejecuta el escaneo completo de 8-K, Form 4 y Form 144, generando el veredicto y guardando JSON."""
    cfg = load_sec_config()
    set_identity(cfg.get("sec_identity", "Pablo Inversiones pablo_inversiones@gmail.com"))
    
    print(f"\n===========================================================================")
    print(f"  MÓDULO DE GOBERNANZA, INSIDERS Y ALERTAS TEMPRANAS: {ticker.upper()}")
    print(f"===========================================================================")
    
    company = sec_call_with_retry(Company, ticker.upper())
    
    if output_dir is None:
        output_dir = Path(cfg.get("local_output_path", "data/processed")) / ticker.upper()
    else:
        output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 1. Escanear formularios (detectando si es Foreign Private Issuer)
    is_fpi = check_is_foreign_private_issuer(company)
    events_6k = []
    if is_fpi:
        print(f"[Governance Analyzer] {ticker.upper()} identificado como Foreign Private Issuer (FPI / Reporta bajo 20-F / 6-K).")
        events_6k = scan_6k_filings(company, max_filings=25)

    events_8k = scan_8k_filings(company, max_filings=25)
    f4_data = scan_form4_filings(company, max_filings=40)
    f144_data = scan_form144_filings(company, max_filings=20)
    
    # 2. Evaluación de Riesgo de Gobernanza y Convicción
    # Puntuación base de Gobernanza (100 = Impecable)
    gov_score = 95
    gov_flags = []
    
    # Evaluar 8-K
    for ev in events_8k:
        if ev["risk_rating"] == "CRITICAL":
            gov_score -= 35
            gov_flags.append(f"Alerta Crítica 8-K ({', '.join(ev['items'])}): {ev['title']}")
        elif ev["risk_rating"] == "HIGH":
            gov_score -= 15
            gov_flags.append(f"Alerta Alta 8-K ({', '.join(ev['items'])}): {ev['title']}")
        elif "Item 5.02" in ev["items"] and "transition" in ev["diagnostic"].lower():
            gov_flags.append("Transición formal de CEO registrada (Item 5.02) - Monitoreo de sucesión.")

    # Evaluar Form 4
    f4_summary = f4_data.get("summary", {})
    discr_sales = f4_summary.get("total_discretionary_sales_usd", 0)
    buys_usd = f4_summary.get("total_open_market_buys_usd", 0)
    ratio_10b5 = f4_summary.get("ratio_10b5_vs_discretionary_pct", 100.0)
    
    insider_sentiment = "NEUTRAL_ROUTINE"
    sentiment_label = "Neutral / Ventas Rutinarias 10b5-1"
    
    if is_fpi:
        f4_note = "Emisor Privado Extranjero (FPI): Exento de la Sección 16 de la SEC (Regla 3a12-3(b)). Las transacciones de directivos se declaran ante el regulador del mercado local y no en Formularios 3, 4, 5 o 144 de la SEC."
        gov_flags.append(f4_note)
        insider_sentiment = "FPI_SECTION16_EXEMPT"
        sentiment_label = "FPI Exento de Sección 16 (Reportes en Regulador de Origen)"
    elif buys_usd > 10_000_000:
        insider_sentiment = "STRONG_BUYING"
        sentiment_label = "Fuerte Acumulación de Directivos (Convicción Alcista)"
        gov_score = min(100, gov_score + 5)
    elif buys_usd > 1_000_000:
        insider_sentiment = "MODERATE_BUYING"
        sentiment_label = "Compras Abiertas Moderadas por Directivos"
    elif discr_sales > 50_000_000 and ratio_10b5 < 50.0:
        insider_sentiment = "OPPORTUNISTIC_SELLING"
        sentiment_label = "Venta Discrecional Significativa (Toma de Beneficios)"
        gov_score -= 5
    else:
        insider_sentiment = "NEUTRAL_ROUTINE"
        sentiment_label = "Actividad Ordinaria Predominantemente bajo Planes 10b5-1"
        
    # Evaluar Form 144
    f144_summary = f144_data.get("summary", {})
    if f144_summary.get("notices_with_anomalies_count", 0) > 3:
        gov_score -= 5
        gov_flags.append(f"Detectadas {f144_summary.get('notices_with_anomalies_count')} avisos con banderas de venta fuera de plan o liquidaciones relevantes.")

    gov_score = max(20, min(100, gov_score))
    if gov_score >= 85:
        gov_rating = "SÓLIDA / BAJO RIESGO"
    elif gov_score >= 70:
        gov_rating = "ADECUADA / RIESGO MODERADO"
    else:
        gov_rating = "PRECAUCIÓN / ALERTA DE GOBERNANZA"

    full_governance_report = {
        "ticker": ticker.upper(),
        "is_foreign_private_issuer": is_fpi,
        "timestamp": datetime.now().isoformat(),
        "scorecard": {
            "governance_score": gov_score,
            "governance_rating": gov_rating,
            "insider_sentiment": insider_sentiment,
            "insider_sentiment_label": sentiment_label,
            "is_foreign_private_issuer": is_fpi,
            "open_market_buys_usd": buys_usd,
            "routine_10b5_sales_usd": f4_summary.get("total_10b5_sales_usd", 0),
            "discretionary_sales_usd": discr_sales,
            "ratio_10b5_compliance_pct": ratio_10b5,
            "audit_change_detected": any("Item 4.01" in ev.get("items", []) for ev in events_8k),
            "debt_default_detected": any("Item 2.04" in ev.get("items", []) for ev in events_8k),
            "ceo_transition_detected": any("Item 5.02" in ev.get("items", []) for ev in events_8k),
            "critical_flags": gov_flags
        },
        "form_8k_events": events_8k,
        "form_6k_events": events_6k,
        "form_4_insiders": f4_data,
        "form_144_notices": f144_data,
        "regulatory_guides": {
            "form_8k_guide": ITEMS_8K_GUIDE,
            "form_4_codes": FORM4_CODES_GUIDE,
            "form_144_guide": RULE144_GUIDE
        }
    }
    
    # Guardar archivo JSON
    out_json = output_dir / "governance_insider_data.json"
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(full_governance_report, f, indent=2, ensure_ascii=False)
    print(f"[Governance Analyzer] Datos consolidados de gobernanza guardados en: {out_json}")
    
    print(f"\n===========================================================================")
    print(f"  DICTAMEN DE GOBERNANZA: {gov_rating} (Puntuación: {gov_score}/100)")
    print(f"  SENTIMIENTO INSIDER: {sentiment_label}")
    print(f"  Ventas 10b5-1 Rutinarias: ${f4_summary.get('total_10b5_sales_usd', 0):,.2f} ({ratio_10b5}% del total)")
    print(f"===========================================================================\n")
    
    return full_governance_report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", default="AAPL")
    parser.add_argument("--out-dir", default=None)
    args = parser.parse_args()
    
    analyze_governance_and_insiders(args.ticker, args.out_dir)
