"""
governance_insider_analyzer.py - Motor de Análisis de Gobernanza Corporativa,
Sentimiento de Insiders (Form 4 y 144) y Radar de Alertas Tempranas (Form 8-K).

Extrae y analiza de SEC EDGAR:
1. Formulario 8-K: Detección de hechos materiales, cambios en el C-suite (Item 5.02),
   cambios de auditor (Item 4.01) y estrés financiero/deuda (Item 2.04).
2. Formulario 4: Registro de transacciones de directivos, diferenciando compras
   en mercado abierto (Código P), ventas rutinarias bajo planes Rule 10b5-1 y ventas discrecionales.
3. Formulario 144: Avisos anticipados de venta de acciones restringidas y banderas de anomalía.
"""

import argparse
from datetime import datetime
import logging

from edgar import Company, set_identity

try:
    from json_io import atomic_json_write
    from config_loader import load_sec_config, resolve_output_dir, DEFAULT_SEC_IDENTITY
    from sec_rate_limiter import sec_call_with_retry, default_rate_limiter
except ImportError:
    try:
        from pipeline.json_io import atomic_json_write
        from pipeline.config_loader import load_sec_config, resolve_output_dir, DEFAULT_SEC_IDENTITY
        from pipeline.sec_rate_limiter import sec_call_with_retry, default_rate_limiter
    except ImportError:
        from .json_io import atomic_json_write
        from .config_loader import load_sec_config, resolve_output_dir, DEFAULT_SEC_IDENTITY
        from .sec_rate_limiter import sec_call_with_retry, default_rate_limiter

logger = logging.getLogger(__name__)

ITEMS_8K_GUIDE = {
    "Item 1.01": {
        "title": "Entrada en un Acuerdo Comercial Material No Ordinario",
        "description": "La compañía ha formalizado un contrato estratégico fuera del curso ordinario (alianzas clave, acuerdos de licencia o exclusividad, contratos con proveedores estratégicos).",
        "risk_level": "NEUTRAL_TO_POSITIVE",
        "diagnostic_hint": "Evaluar si el contrato amplía el foso defensivo o genera dependencia operativa.",
    },
    "Item 1.02": {
        "title": "Terminación de un Acuerdo Comercial Material",
        "description": "Ruptura, cancelación o vencimiento anticipado de un contrato de negocio crítico.",
        "risk_level": "WARNING",
        "diagnostic_hint": "Alerta de riesgo comercial: analizar si supone pérdida de ingresos relevantes o deterioro de relaciones con socios clave.",
    },
    "Item 2.01": {
        "title": "Adquisición o Disposición Significativa de Activos (M&A)",
        "description": "Operaciones corporativas de fusión, adquisición (M&A) o venta sustancial de filiales o unidades de negocio.",
        "risk_level": "WATCH",
        "diagnostic_hint": "Examinar el precio pagado (múltiplos), el apalancamiento asumido y el riesgo de integración del negocio adquirido.",
    },
    "Item 2.02": {
        "title": "Resultados de Operaciones y Condición Financiera",
        "description": "Publicación trimestral de resultados financieros y notas de prensa de resultados antes de la presentación formal del 10-Q o 10-K.",
        "risk_level": "NEUTRAL",
        "diagnostic_hint": "Avance de cifras financieras oficiales auditadas o preliminares.",
    },
    "Item 2.03": {
        "title": "Creación de una Obligación Financiera Directa o Fuera de Balance",
        "description": "Emisión de nueva deuda corporativa, suscripción de líneas de crédito sindicadas o contingencias fuera de balance.",
        "risk_level": "WATCH",
        "diagnostic_hint": "Monitorear el aumento de deuda bruta, tipos de interés acordados y fechas de vencimiento.",
    },
    "Item 2.04": {
        "title": "Eventos de Aceleración o Impago de Deuda (Default / Covenants)",
        "description": "Alerta máxima de solvencia: la compañía ha incumplido pagos de deuda o vulnerado covenants bancarios, provocando la exigibilidad inmediata de los pasivos.",
        "risk_level": "CRITICAL_RED_FLAG",
        "diagnostic_hint": "¡Bandera roja crítica! Riesgo severo de reestructuración forzosa, quiebra o dilución masiva de accionistas.",
    },
    "Item 3.01": {
        "title": "Aviso de Incumplimiento de Estándares de Cotización (Delisting)",
        "description": "Notificación oficial de la bolsa (NASDAQ / NYSE) de que la empresa no cumple requisitos mínimos (precio < $1, retraso en presentar estados contables).",
        "risk_level": "CRITICAL_RED_FLAG",
        "diagnostic_hint": "Riesgo inminente de exclusión de cotización y colapso de liquidez para los accionistas.",
    },
    "Item 4.01": {
        "title": "Cambio de Contables / Auditores Independientes",
        "description": "Cese, dimisión o sustitución de la firma de auditoría independiente de la compañía.",
        "risk_level": "HIGH_WARNING",
        "diagnostic_hint": "Alerta forense primordial: investigar si existieron discrepancias contables o desacuerdos en principios contables US-GAAP con el auditor saliente.",
    },
    "Item 5.01": {
        "title": "Cambio en el Control de la Compañía",
        "description": "Toma de control hostil, compra mayoritaria o cambio significativo en la estructura del accionariado de control.",
        "risk_level": "HIGH_IMPACT",
        "diagnostic_hint": "Evaluar la alineación del nuevo accionista de control con los inversores minoritarios.",
    },
    "Item 5.02": {
        "title": "Salida o Nombramiento de Directores y C-Suite; Acuerdos de Compensación",
        "description": "Modificaciones en los cargos de máxima responsabilidad (CEO, CFO, Director General) o cambios en los paquetes de compensación e incentivos en acciones.",
        "risk_level": "WATCH_GOVERNANCE",
        "diagnostic_hint": "Comprobar si es un relevo planificado y ordenado o una dimisión abrupta. Analizar si la compensación incentiva el valor por acción a largo plazo.",
    },
    "Item 5.03": {
        "title": "Enmiendas a Estatutos Corporativos o Código de Ética",
        "description": "Modificación de estatutos, derechos de voto o normas de gobernanza interna.",
        "risk_level": "NEUTRAL",
        "diagnostic_hint": "Verificar que las enmiendas no reduzcan los derechos de voto o protección de los accionistas minoritarios.",
    },
    "Item 7.01": {
        "title": "Regulación FD (Fair Disclosure)",
        "description": "Divulgación pública obligatoria de presentaciones a inversores para garantizar acceso equitativo a la información de mercado.",
        "risk_level": "NEUTRAL",
        "diagnostic_hint": "Información cualitativa compartida con analistas o conferencias del sector.",
    },
    "Item 8.01": {
        "title": "Otros Eventos Materiales no Clasificados",
        "description": "Cualquier otro hecho de relevancia material que la directiva decida comunicar formalmente a los accionistas.",
        "risk_level": "NEUTRAL",
        "diagnostic_hint": "Hechos corporativos diversos de interés general.",
    },
}

FORM4_CODES_GUIDE = {
    "P": {
        "name": "Compra en Mercado Abierto (Open Market Purchase)",
        "description": "El directivo compra acciones con dinero propio de su bolsillo a precios de cotización de mercado.",
        "signal": "BULLISH_CONVICTION",
        "impact": "Máxima señal de convicción interna: ningún directivo compra con su patrimonio personal a menos que considere que la acción está infravalorada.",
    },
    "S": {
        "name": "Venta en Mercado Abierto (Open Market Sale)",
        "description": "Venta de acciones en el mercado secundario. Debe diferenciarse entre ventas por plan 10b5-1 o ventas discrecionales.",
        "signal": "NEUTRAL_TO_BEARISH",
        "impact": "Las ventas bajo planes 10b5-1 son automáticas y rutinarias. Las ventas discrecionales a precios máximos sugieren toma de beneficios.",
    },
    "F": {
        "name": "Retención Fiscal (Tax Withholding)",
        "description": "Entrega obligatoria o retención automática de acciones para cubrir el pago de impuestos derivados de la consolidación de RSUs.",
        "signal": "NEUTRAL_ROUTINE",
        "impact": "Operación puramente administrativa/fiscal. No implica en absoluto pérdida de confianza en la compañía.",
    },
    "A": {
        "name": "Concesión de Capital (Grant / Award)",
        "description": "Entrega de opciones sobre acciones o unidades de acciones restringidas (RSUs) como parte de su retribución.",
        "signal": "ALIGNED_INCENTIVE",
        "impact": "Incentivo a largo plazo para alinear a los directivos con el rendimiento para el accionista.",
    },
    "M": {
        "name": "Ejercicio de Opciones (Option Exercise)",
        "description": "Conversión de opciones de compra sobre acciones acumuladas.",
        "signal": "NEUTRAL",
        "impact": "Aumenta la tenencia bruta de acciones de los directivos tras el pago del precio de ejercicio.",
    },
}

RULE144_GUIDE = {
    "definition": "La Regla 144 de la SEC regula la venta pública de acciones restringidas o en manos de personas de control (insiders).",
    "purpose": "Exige que los directivos notifiquen formalmente a la SEC (Formulario 144) su intención de vender antes o en el momento de dar la orden de venta.",
    "is_10b5_1": "Si la venta está amparada por un plan Rule 10b5-1, fue programada con meses de antelación sin conocimiento de información privilegiada.",
    "discretionary_sale": "Si la venta NO está amparada por un plan 10b5-1, el directivo está vendiendo de forma discrecional en el mercado abierto.",
    "large_liquidation": "Alerta cuando el volumen propuesto a vender representa un porcentaje atípicamente elevado de la posición total del directivo.",
}


def scan_8k_filings(company, max_filings=25, filing_context=None):
    """Escanea los formularios 8-K recientes, mapea ítems, extrae contexto y elabora diagnósticos."""
    print("[Governance Analyzer] Escaneando formularios 8-K en SEC EDGAR...")
    filings = filing_context.get_filings(form="8-K") if filing_context else sec_call_with_retry(company.get_filings, form="8-K")
    if not filings or len(filings) == 0:
        return []

    results = []
    for f in filings[: min(max_filings, len(filings))]:
        date_str = str(f.filing_date)
        try:
            if default_rate_limiter:
                default_rate_limiter.pace()
            obj = filing_context.get_filing_obj(f) if filing_context else sec_call_with_retry(f.obj)
            items_raw = getattr(obj, "items", []) or []
            if not items_raw and hasattr(f, "items"):
                items_raw = [f.items] if isinstance(f.items, str) else list(f.items)

            items_clean = [s if s.startswith("Item") else f"Item {s}" for s in (str(it).strip() for it in items_raw)]
            if not items_clean:
                continue

            descriptions, explanations, diagnostics = [], [], []
            highest_risk = "LOW"
            for it in items_clean:
                guide = ITEMS_8K_GUIDE.get(
                    it,
                    {
                        "title": f"Hecho Regulatorio ({it})",
                        "description": "Evento de notificación corporativa ante la SEC.",
                        "risk_level": "NEUTRAL",
                        "diagnostic_hint": "Evento regulatorio ordinario.",
                    },
                )
                descriptions.append(guide["title"])
                explanations.append(guide["description"])
                diagnostics.append(guide["diagnostic_hint"])
                if guide["risk_level"] == "CRITICAL_RED_FLAG":
                    highest_risk = "CRITICAL"
                elif guide["risk_level"] in ("HIGH_WARNING", "HIGH_IMPACT") and highest_risk != "CRITICAL":
                    highest_risk = "HIGH"
                elif guide["risk_level"] in ("WATCH_GOVERNANCE", "WATCH") and highest_risk not in ("CRITICAL", "HIGH"):
                    highest_risk = "MEDIUM"

            text_preview = ""
            try:
                for it in items_clean:
                    if hasattr(obj, "__getitem__") and it in obj.items:
                        clean_t = " ".join(str(obj[it]).split())
                        if len(clean_t) > 20:
                            text_preview = clean_t[:350] + ("..." if len(clean_t) > 350 else "")
                            break
            except Exception as exc:
                logger.debug("No se pudo extraer vista previa de 8-K (%s): %s", date_str, exc)
                text_preview = "Contenido extraído del formulario oficial SEC."

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

            results.append(
                {
                    "filing_date": date_str,
                    "accession_number": str(f.accession_number),
                    "items": items_clean,
                    "title": " / ".join(descriptions),
                    "explanation": " ".join(explanations),
                    "diagnostic": custom_diag,
                    "risk_rating": highest_risk,
                    "text_snippet": text_preview,
                }
            )
        except Exception as exc:
            logger.debug("Omitiendo 8-K (%s) por error de parseo: %s", date_str, exc)

    print(f"[Governance Analyzer] Procesados {len(results)} formularios 8-K.")
    return results


def check_is_foreign_private_issuer(company, filing_context=None):
    """Verifica si la empresa es un Foreign Private Issuer (reporta bajo 20-F / 40-F / 6-K)."""
    if filing_context:
        return filing_context.is_fpi
    try:
        for form_type in ("20-F", "40-F"):
            filings = sec_call_with_retry(company.get_filings, form=form_type)
            if filings is not None and len(filings) > 0:
                return True
    except Exception as exc:
        logger.debug("Error verificando condición FPI: %s", exc)
    return False


def scan_6k_filings(company, max_filings=25, filing_context=None):
    """Escanea los formularios 6-K recientes de Emisores Privados Extranjeros (FPI)."""
    print("[Governance Analyzer] Escaneando formularios 6-K (FPI / Extranjero) en SEC EDGAR...")
    filings = filing_context.get_filings(form="6-K") if filing_context else sec_call_with_retry(company.get_filings, form="6-K")
    if not filings or len(filings) == 0:
        return []

    results = []
    for f in filings[: min(max_filings, len(filings))]:
        date_str = str(f.filing_date)
        try:
            desc = (
                getattr(f, "description", "")
                or getattr(f, "document_description", "")
                or "Informe periódico o hecho de relevancia material (Formulario 6-K)"
            )
            results.append(
                {
                    "filing_date": date_str,
                    "accession_number": str(getattr(f, "accession_number", "")),
                    "title": "Hecho de Relevancia Material / Informe Periódico FPI (Formulario 6-K)",
                    "description": desc,
                    "diagnostic": "Comunicación corporativa periódica bajo estándares del regulador del país de origen y la SEC.",
                    "risk_rating": "LOW",
                }
            )
        except Exception as exc:
            logger.debug("Omitiendo 6-K (%s) por error de lectura: %s", date_str, exc)
    print(f"[Governance Analyzer] Procesados {len(results)} formularios 6-K.")
    return results


def _has_form4_tx(raw_txs, date_str, insider, code, shares_int):
    return any(
        r["filing_date"] == date_str and r["insider"] == insider and r["code"] == code and r["shares"] == shares_int
        for r in raw_txs
    )


def _record_form4_buy(raw_txs, insiders_activity, totals, date_str, insider, position, sh, pr):
    val = sh * pr
    sh_int = int(sh)
    totals["buys_usd"] += val
    totals["buys_shares"] += sh_int
    insiders_activity[insider]["buys_usd"] += val
    insiders_activity[insider]["shares_bought"] += sh_int
    raw_txs.append(
        {
            "filing_date": date_str,
            "insider": insider,
            "position": position,
            "type": "COMPRA_MERCADO_ABIERTO",
            "code": "P",
            "shares": sh_int,
            "price": round(pr, 2),
            "total_usd": round(val, 2),
            "is_10b5_1": False,
            "explanation": FORM4_CODES_GUIDE["P"]["description"],
            "diagnostic": "MÁXIMA CONVICCIÓN ALCISTA: Compra directa con fondos propios en mercado abierto.",
        }
    )


def _record_form4_sale(raw_txs, insiders_activity, totals, date_str, insider, position, sh, pr, is_10b5):
    val = sh * pr
    sh_int = int(sh)
    if is_10b5:
        totals["sales_10b5_usd"] += val
        totals["sales_10b5_shares"] += sh_int
        insiders_activity[insider]["sales_10b5_usd"] += val
        diag = "VENTA RUTINARIA (PLAN 10b5-1): Venta programada previamente para diversificación o liquidez periódica."
        tx_type = "VENTA_PROGRAMADA_10B5"
    else:
        totals["sales_discr_usd"] += val
        totals["sales_discr_shares"] += sh_int
        insiders_activity[insider]["sales_discretionary_usd"] += val
        diag = "VENTA DISCRECIONAL: Venta no programada en mercado abierto; monitorear si coincide con máximos históricos."
        tx_type = "VENTA_DISCRECIONAL"

    insiders_activity[insider]["shares_sold"] += sh_int
    raw_txs.append(
        {
            "filing_date": date_str,
            "insider": insider,
            "position": position,
            "type": tx_type,
            "code": "S",
            "shares": sh_int,
            "price": round(pr, 2),
            "total_usd": round(val, 2),
            "is_10b5_1": is_10b5,
            "explanation": FORM4_CODES_GUIDE["S"]["description"],
            "diagnostic": diag,
        }
    )


def _process_single_form4_obj(obj, date_str, raw_txs, insiders_activity, totals):
    """Extrae compras, ventas (10b5-1 / discrecionales) y concesiones de un objeto Form 4."""
    insider = getattr(obj, "insider_name", "Desconocido") or "Desconocido"
    position = getattr(obj, "position", "Directivo") or "Directivo"

    entry = insiders_activity.setdefault(
        insider,
        {
            "position": position,
            "buys_usd": 0.0,
            "sales_10b5_usd": 0.0,
            "sales_discretionary_usd": 0.0,
            "shares_bought": 0,
            "shares_sold": 0,
            "grants": 0,
            "tx_count": 0,
        },
    )
    entry["tx_count"] += 1

    is_10b5_1_general = False
    try:
        fn_text = str(getattr(obj, "footnotes", "")).lower()
        is_10b5_1_general = any(tok in fn_text for tok in ("10b5-1", "10b5", "rule 10b5"))
    except Exception as exc:
        logger.debug("Error leyendo footnotes en Form 4 (%s): %s", date_str, exc)

    try:
        buys_df = obj.common_stock_purchases
        if buys_df is not None and not buys_df.empty:
            for _, row in buys_df.iterrows():
                _record_form4_buy(
                    raw_txs, insiders_activity, totals, date_str, insider, position, float(row.get("Shares", 0) or 0), float(row.get("Price", 0) or 0)
                )
    except Exception as exc:
        logger.debug("Sin common_stock_purchases en Form 4 (%s): %s", date_str, exc)

    try:
        sales_df = obj.common_stock_sales
        if sales_df is not None and not sales_df.empty:
            for _, row in sales_df.iterrows():
                row_fn = str(row.get("footnotes", "")).lower()
                is_10b5 = is_10b5_1_general or ("10b5-1" in row_fn or "10b5" in row_fn)
                _record_form4_sale(
                    raw_txs, insiders_activity, totals, date_str, insider, position, float(row.get("Shares", 0) or 0), float(row.get("Price", 0) or 0), is_10b5
                )
    except Exception as exc:
        logger.debug("Sin common_stock_sales en Form 4 (%s): %s", date_str, exc)

    try:
        activities = obj.get_transaction_activities() if hasattr(obj, "get_transaction_activities") else []
        for act in activities:
            act_code = getattr(act, "code", "")
            sh = float(getattr(act, "shares", 0) or 0)
            if sh <= 0:
                continue
            pr = float(getattr(act, "price_per_share", 0) or getattr(act, "value", 0) or 0)
            sh_int = int(sh)
            if _has_form4_tx(raw_txs, date_str, insider, act_code, sh_int):
                continue

            fn_act = str(getattr(act, "footnotes_text", "")).lower()
            is_10b5 = is_10b5_1_general or ("10b5-1" in fn_act or "10b5" in fn_act)
            if act_code == "P":
                _record_form4_buy(raw_txs, insiders_activity, totals, date_str, insider, position, sh, pr)
            elif act_code == "S":
                _record_form4_sale(raw_txs, insiders_activity, totals, date_str, insider, position, sh, pr, is_10b5)
            elif act_code == "A":
                totals["grants_shares"] += sh_int
                insiders_activity[insider]["grants"] += sh_int
                raw_txs.append(
                    {
                        "filing_date": date_str,
                        "insider": insider,
                        "position": position,
                        "type": "CONCESIÓN_RSU_ACCIONES",
                        "code": "A",
                        "shares": sh_int,
                        "price": 0.0,
                        "total_usd": 0.0,
                        "is_10b5_1": False,
                        "explanation": FORM4_CODES_GUIDE.get("A", {}).get("description", "Concesión de capital"),
                        "diagnostic": "INCENTIVO DE CAPITAL: Asignación de unidades de acciones restringidas ligadas a permanencia y objetivos de valor.",
                    }
                )
    except Exception as exc:
        logger.debug("Error procesando transaction_activities en Form 4 (%s): %s", date_str, exc)


def scan_form4_filings(company, max_filings=40, filing_context=None):
    """Escanea las transacciones de Form 4 separando compras abiertas y ventas 10b5-1 / discrecionales."""
    print("[Governance Analyzer] Escaneando transacciones de insiders (Formulario 4)...")
    filings = filing_context.get_filings(form="4") if filing_context else sec_call_with_retry(company.get_filings, form="4")
    if not filings or len(filings) == 0:
        return {"summary": {}, "transactions": []}

    target_count = min(max_filings, len(filings))
    raw_txs = []
    insiders_activity = {}
    totals = {
        "buys_usd": 0.0,
        "buys_shares": 0,
        "sales_10b5_usd": 0.0,
        "sales_10b5_shares": 0,
        "sales_discr_usd": 0.0,
        "sales_discr_shares": 0,
        "grants_shares": 0,
    }

    for f in filings[:target_count]:
        date_str = str(f.filing_date)
        try:
            if default_rate_limiter:
                default_rate_limiter.pace()
            obj = filing_context.get_filing_obj(f) if filing_context else sec_call_with_retry(f.obj)
            _process_single_form4_obj(obj, date_str, raw_txs, insiders_activity, totals)
        except Exception as exc:
            logger.debug("Omitiendo Form 4 (%s) por error de descarga/parseo: %s", date_str, exc)

    sales_tot = totals["sales_10b5_usd"] + totals["sales_discr_usd"]
    summary = {
        "filings_analyzed": target_count,
        "total_open_market_buys_usd": round(totals["buys_usd"], 2),
        "total_open_market_buys_shares": totals["buys_shares"],
        "total_10b5_sales_usd": round(totals["sales_10b5_usd"], 2),
        "total_10b5_sales_shares": totals["sales_10b5_shares"],
        "total_discretionary_sales_usd": round(totals["sales_discr_usd"], 2),
        "total_discretionary_sales_shares": totals["sales_discr_shares"],
        "total_grants_shares": totals["grants_shares"],
        "ratio_10b5_vs_discretionary_pct": round((totals["sales_10b5_usd"] / sales_tot) * 100, 1) if sales_tot > 0 else 100.0,
        "active_insiders_count": len(insiders_activity),
        "insiders_breakdown": insiders_activity,
    }

    print(f"[Governance Analyzer] Procesadas {len(raw_txs)} transacciones de directivos.")
    return {"summary": summary, "transactions": raw_txs}


def scan_form144_filings(company, max_filings=20, filing_context=None):
    """Escanea avisos preventivos de venta bajo la Regla 144, detectando banderas de anomalía."""
    print("[Governance Analyzer] Escaneando avisos preventivos de venta (Formulario 144)...")
    filings = filing_context.get_filings(form="144") if filing_context else sec_call_with_retry(company.get_filings, form="144")
    if not filings or len(filings) == 0:
        return {"summary": {}, "notices": []}

    target_count = min(max_filings, len(filings))
    notices, anomalies_detected = [], []
    total_market_value_usd = 0.0
    total_shares_to_sell = count_10b5 = count_discretionary = 0

    for f in filings[:target_count]:
        date_str = str(f.filing_date)
        try:
            if default_rate_limiter:
                default_rate_limiter.pace()
            obj = filing_context.get_filing_obj(f) if filing_context else sec_call_with_retry(f.obj)
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

            notices.append(
                {
                    "filing_date": date_str,
                    "person_selling": seller,
                    "shares_to_sell": shares,
                    "market_value_usd": round(mv, 2),
                    "is_10b5_1": is_10b5,
                    "is_large_liquidation": is_large,
                    "anomaly_flags": anom_flags,
                    "diagnostic": f"{plan_diag} {' '.join(custom_notes)}",
                }
            )
            if anom_flags or is_large or not is_10b5:
                anomalies_detected.append(
                    {
                        "date": date_str,
                        "seller": seller,
                        "market_value_usd": round(mv, 2),
                        "is_10b5_1": is_10b5,
                        "flags": anom_flags,
                        "is_large": is_large,
                    }
                )
        except Exception as exc:
            logger.debug("Omitiendo Form 144 (%s) por error de parseo: %s", date_str, exc)

    summary = {
        "notices_analyzed": target_count,
        "total_shares_proposed": total_shares_to_sell,
        "total_value_proposed_usd": round(total_market_value_usd, 2),
        "notices_under_10b5": count_10b5,
        "notices_discretionary": count_discretionary,
        "notices_with_anomalies_count": len(anomalies_detected),
    }

    print(f"[Governance Analyzer] Procesados {len(notices)} avisos del Formulario 144.")
    return {"summary": summary, "notices": notices, "anomalies": anomalies_detected}


def analyze_governance_and_insiders(ticker="AAPL", output_dir=None, filing_context=None):
    """Ejecuta el escaneo completo de 8-K, 6-K, Form 4 y Form 144 y guarda el reporte JSON."""
    cfg = load_sec_config()
    set_identity(cfg.get("sec_identity", DEFAULT_SEC_IDENTITY))

    print(f"\n{'='*75}\n  MÓDULO DE GOBERNANZA, INSIDERS Y ALERTAS TEMPRANAS: {ticker.upper()}\n{'='*75}")
    company = filing_context.company if filing_context else sec_call_with_retry(Company, ticker.upper())

    out_dir = resolve_output_dir(ticker, output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    is_fpi = check_is_foreign_private_issuer(company, filing_context=filing_context)
    events_6k = []
    if is_fpi:
        print(f"[Governance Analyzer] {ticker.upper()} identificado como Foreign Private Issuer (FPI / Reporta bajo 20-F / 6-K).")
        events_6k = scan_6k_filings(company, max_filings=25, filing_context=filing_context)

    events_8k = scan_8k_filings(company, max_filings=25, filing_context=filing_context)
    f4_data = scan_form4_filings(company, max_filings=40, filing_context=filing_context)
    f144_data = scan_form144_filings(company, max_filings=20, filing_context=filing_context)

    gov_score = 95
    gov_flags = []
    for ev in events_8k:
        if ev["risk_rating"] == "CRITICAL":
            gov_score -= 35
            gov_flags.append(f"Alerta Crítica 8-K ({', '.join(ev['items'])}): {ev['title']}")
        elif ev["risk_rating"] == "HIGH":
            gov_score -= 15
            gov_flags.append(f"Alerta Alta 8-K ({', '.join(ev['items'])}): {ev['title']}")
        elif "Item 5.02" in ev["items"] and "transition" in ev["diagnostic"].lower():
            gov_flags.append("Transición formal de CEO registrada (Item 5.02) - Monitoreo de sucesión.")

    f4_summary = f4_data.get("summary", {})
    discr_sales = f4_summary.get("total_discretionary_sales_usd", 0)
    buys_usd = f4_summary.get("total_open_market_buys_usd", 0)
    ratio_10b5 = f4_summary.get("ratio_10b5_vs_discretionary_pct", 100.0)

    if is_fpi:
        gov_flags.append(
            "Emisor Privado Extranjero (FPI): Exento de la Sección 16 de la SEC (Regla 3a12-3(b)). "
            "Las transacciones de directivos se declaran ante el regulador del mercado local y no en Formularios 3, 4, 5 o 144 de la SEC."
        )
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

    f144_summary = f144_data.get("summary", {})
    if f144_summary.get("notices_with_anomalies_count", 0) > 3:
        gov_score -= 5
        gov_flags.append(
            f"Detectadas {f144_summary.get('notices_with_anomalies_count')} avisos con banderas de venta fuera de plan o liquidaciones relevantes."
        )

    gov_score = max(20, min(100, gov_score))
    gov_rating = "SÓLIDA / BAJO RIESGO" if gov_score >= 85 else ("ADECUADA / RIESGO MODERADO" if gov_score >= 70 else "PRECAUCIÓN / ALERTA DE GOBERNANZA")

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
            "critical_flags": gov_flags,
        },
        "form_8k_events": events_8k,
        "form_6k_events": events_6k,
        "form_4_insiders": f4_data,
        "form_144_notices": f144_data,
        "regulatory_guides": {
            "form_8k_guide": ITEMS_8K_GUIDE,
            "form_4_codes": FORM4_CODES_GUIDE,
            "form_144_guide": RULE144_GUIDE,
        },
    }

    out_json = out_dir / "governance_insider_data.json"
    atomic_json_write(out_json, full_governance_report, indent=2, ensure_ascii=False)
    print(f"[Governance Analyzer] Datos consolidados de gobernanza guardados en: {out_json}")
    print(
        f"\n{'='*75}\n  DICTAMEN DE GOBERNANZA: {gov_rating} (Puntuación: {gov_score}/100)\n"
        f"  SENTIMIENTO INSIDER: {sentiment_label}\n"
        f"  Ventas 10b5-1 Rutinarias: ${f4_summary.get('total_10b5_sales_usd', 0):,.2f} ({ratio_10b5}% del total)\n{'='*75}\n"
    )
    return full_governance_report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", default="AAPL")
    parser.add_argument("--out-dir", default=None)
    args = parser.parse_args()

    analyze_governance_and_insiders(args.ticker, args.out_dir)
