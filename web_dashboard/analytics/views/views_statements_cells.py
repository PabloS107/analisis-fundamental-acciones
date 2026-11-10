# -*- coding: utf-8 -*-
"""
Submódulo de Formateo de Celdas, Secciones Estandarizadas y Filas SEC As-Reported.
"""
import re

from .view_utils import fmt_money_m, logger, usd_to_m

try:
    from pipeline.financial_bilingual_map import get_spanish_label
except ImportError as exc:
    logger.warning("financial_bilingual_map no disponible (%s); usando etiquetas originales.", exc)

    def get_spanish_label(lbl, conc=None):
        return lbl


def detail_num(dict_src, key, p):
    """Extrae un escalar desde diccionarios SEC detail con matching por prefijo/token."""
    if not dict_src or not key:
        return None
    if key in dict_src:
        obj = dict_src[key]
        if isinstance(obj, dict):
            return obj["values"].get(p) if "values" in obj else obj.get(p)
    cand_key = f"us-gaap_{key}" if not str(key).startswith("us-gaap_") else str(key)[len("us-gaap_"):]
    if cand_key in dict_src:
        obj = dict_src[cand_key]
        if isinstance(obj, dict):
            return obj["values"].get(p) if "values" in obj else obj.get(p)
    raw_key = str(key).split(":")[-1].split("_")[-1].lower()
    for k, obj in dict_src.items():
        if str(k).split(":")[-1].split("_")[-1].lower() == raw_key and isinstance(obj, dict):
            return obj["values"].get(p) if "values" in obj else obj.get(p)
    return None


def _fmt_shares(val) -> str:
    if val is None:
        return "-"
    scale = abs(float(val))
    return f"{scale / 1e6:,.1f}M" if scale >= 1e6 else f"{scale:,.1f}"


def _fmt_eps(val) -> str:
    if val is None:
        return "-"
    v = float(val)
    return f"-${abs(v):.2f}" if v < 0 else f"${v:.2f}"


def _should_include_row(row_def, data_dict, statements_fys) -> bool:
    if row_def[7]:
        return True
    for p in statements_fys:
        v = data_dict.get(p)
        if v is not None:
            try:
                if abs(float(v)) > 1e-6:
                    return True
            except (ValueError, TypeError) as exc:
                logger.debug("Valor no numérico ignorado en fila '%s' (%s=%r): %s", row_def[1], p, v, exc)
    return False


def build_standardized_section(sections_def, source_data, statements_fys, canonical, default_pct_mode=None) -> list:
    """Construye filas estandarizadas filtrando partidas vacías opcionales y preservando tooltips."""
    out_rows = []
    for sec_title, items in sections_def:
        sec_visible_items = []
        for item in items:
            lbl, k, op, r_type, ind, bold, neg, _, p_mode, tip = item
            if r_type in ("shares", "eps", "dps"):
                val_dict = {p: source_data.get(k, {}).get(p) for p in statements_fys}
            else:
                val_dict = {p: usd_to_m(source_data.get(k, {}).get(p)) for p in statements_fys}

            if k in ("preferred_dividends", "minority_interest_pnl") and any(v is not None and abs(float(v or 0)) > 1e-6 for v in val_dict.values()):
                val_dict = {p: (val_dict[p] if val_dict.get(p) is not None else 0.0) for p in statements_fys}

            if _should_include_row(item, val_dict, statements_fys):
                eff_tooltip = tip or f"Estándar Canónico: {k}"
                if k == "sga_expense":
                    canon_rd = canonical.get("rd_expense", {}) if isinstance(canonical, dict) else {}
                    if any(v is not None for v in canon_rd.values()) and not any(v is not None for v in source_data.get("rd_expense", {}).values()):
                        eff_tooltip = (
                            f"{eff_tooltip}. En empresas que integran I+D/diseño en gastos generales "
                            "(ej. calzado y retail), incluye la inversión reportada en notas del 10-K."
                        )
                sec_visible_items.append({
                    "label": lbl, "orig_tooltip": eff_tooltip, "clarification": None,
                    "operator": op, "row_type": r_type, "indent": ind, "is_bold": bold,
                    "negate_val": neg, "data": val_dict, "pct_mode": p_mode or default_pct_mode,
                })
        if sec_visible_items:
            if sec_title:
                out_rows.append({
                    "label": sec_title, "orig_tooltip": f"Sección Canónica: {sec_title}",
                    "clarification": None, "operator": "", "row_type": "section_header",
                    "indent": False, "is_bold": True, "negate_val": False,
                    "data": {p: None for p in statements_fys}, "pct_mode": None,
                })
            out_rows.extend(sec_visible_items)
    return out_rows


def format_as_reported_row(row_raw, target_fys, fs, pct_mode=None) -> dict:
    """Formatea una partida cruda SEC As-Reported con traducción bilingüe y escalado explícito."""
    orig_lbl = row_raw.get("label", "")
    conc = row_raw.get("concept", "")
    lbl = get_spanish_label(orig_lbl, conc) if orig_lbl else (row_raw.get("spanish_label") or "")
    orig_tooltip = row_raw.get("orig_tooltip") or (f"{orig_lbl} ({conc})" if conc else orig_lbl)
    is_abs = row_raw.get("is_abstract", False) or row_raw.get("row_type") == "section_header"
    lvl = row_raw.get("level", 0)
    is_tot = row_raw.get("is_total", False)
    clarif = row_raw.get("clarification")
    vals = row_raw.get("values", {}) or row_raw.get("data", {})

    if is_abs:
        return {
            "label": lbl, "orig_tooltip": orig_tooltip, "clarification": clarif,
            "operator": "", "row_type": "section_header", "indent": False,
            "is_bold": True, "data": {p: None for p in target_fys}, "pct_mode": None,
        }

    lbl_lower, conc_lower = orig_lbl.lower(), conc.lower()
    is_dollar_account = any(k in conc_lower for k in ("value", "capital", "equity", "proceeds", "payments", "accruals", "repurchase", "borrowings", "cash")) or any(
        k in lbl_lower for k in ("par value", "stated value", "additional paid", "common stock, $", "preferred stock, $")
    )
    is_eps = not is_dollar_account and (
        "earningspershare" in conc_lower
        or (("per share" in lbl_lower or "pershare" in conc_lower) and any(w in conc_lower or w in lbl_lower for w in ("basic", "diluted", "earnings", "loss", "dividend", "distribution")))
    )
    is_shares = not is_dollar_account and not is_eps and (
        "weightedaveragenumberofshares" in conc_lower or "weightedaveragenumberofdilutedshares" in conc_lower
        or conc_lower in ("commonstocksharesoutstanding", "commonstocksharesissued", "sharesoutstanding", "preferredstocksharesoutstanding")
        or ("number of shares" in lbl_lower and "value" not in conc_lower)
        or ("shares outstanding" in lbl_lower and "value" not in conc_lower and "par value" not in lbl_lower)
    )

    cf_det, bs_det, inc_det = fs.get("cash_flow_detail", {}), fs.get("balance_sheet_detail", {}), fs.get("income_statement_detail", {})
    data_m = {}
    for p in target_fys:
        v = vals.get(p)
        if v is None and conc:
            v = detail_num(cf_det, conc, p) or detail_num(bs_det, conc, p) or detail_num(inc_det, conc, p)
        if v is None and orig_lbl:
            clean_target = re.sub(r"[^a-z0-9]", "", lbl_lower)
            if len(clean_target) >= 4:
                for src_dict in (cf_det, bs_det, inc_det):
                    if not isinstance(src_dict, dict):
                        continue
                    for item_obj in src_dict.values():
                        if isinstance(item_obj, dict) and item_obj.get("label"):
                            if re.sub(r"[^a-z0-9]", "", item_obj["label"].lower()) == clean_target:
                                v_cand = item_obj.get("values", {}).get(p)
                                if v_cand is not None:
                                    v = v_cand
                                    break
                    if v is not None:
                        break
        data_m[p] = None if v is None else (float(v) if (is_eps or is_shares) else usd_to_m(v))

    if is_eps:
        row_type, operator, bold, indent, p_mode = "eps", "", is_tot, (lvl > 2), None
    elif is_shares:
        row_type, operator, bold, indent, p_mode = "shares", "", False, True, None
    elif is_tot:
        is_res = conc_lower in ("netincomeloss", "profitloss", "operatingincomeloss", "assets") or any(
            w in lbl_lower for w in ("net income", "total assets", "operating income", "cash generated by operating activities", "flujo de caja operativo", "utilidad neta", "activos totales")
        )
        row_type, operator, bold, indent, p_mode = ("result" if is_res else "subtotal"), "[=]", True, (lvl > 2), pct_mode
    else:
        row_type, operator, bold, indent, p_mode = "item", "", False, (lvl > 2), pct_mode

    return {
        "label": lbl, "orig_tooltip": orig_tooltip, "clarification": clarif,
        "operator": operator, "row_type": row_type, "indent": indent,
        "is_bold": bold, "data": data_m, "pct_mode": p_mode,
    }


def _format_cell_abs(val, row_type: str, negate_val: bool) -> str:
    if row_type == "shares":
        return _fmt_shares(val)
    if row_type in ("eps", "dps"):
        return _fmt_eps(val)
    if row_type == "metric_pct":
        return f"{val:.1f}%" if val is not None else "-"
    if row_type == "multiple":
        return f"{val:.2f}x" if val is not None else "-"
    if row_type in ("net_debt", "net_cash", "metric"):
        return (f"-${abs(val):,.1f}M" if val < 0 else f"${val:,.1f}M") if val is not None else "-"
    if negate_val and val is not None:
        if val < -0.01:
            return f"+${abs(val):,.1f}M"
        if val > 0.01:
            return f"-${val:,.1f}M"
        return "$0.0M"
    return fmt_money_m(val)


def build_statement_cells(r, target_fys, canonical, ebt_dict=None, bs_tot_assets=None) -> dict:
    """Construye valores formateados, % vertical, YoY y CAGR 5Y por fila."""
    if r.get("row_type") == "section_header":
        return {
            "label": r["label"], "orig_tooltip": r.get("orig_tooltip", ""), "clarification": r.get("clarification"),
            "operator": "", "row_type": "section_header", "indent": False, "is_bold": True,
            "values": ["" for _ in target_fys], "pcts": ["" for _ in target_fys], "yoy": ["" for _ in target_fys],
            "cagr_5y": "", "ltm_val": "", "ltm_pct": "", "ltm_yoy": "",
            "annual_cells": [{"abs": "", "pct": "", "yoy": ""} for _ in target_fys[1:]],
            "annual_vals": ["" for _ in target_fys[1:]], "latest_val": "", "latest_pct": "",
        }

    row_type, pct_mode, negate_val = r.get("row_type", "item"), r.get("pct_mode"), bool(r.get("negate_val"))
    row_vals, row_pcts, row_yoys = [], [], []

    for i, p in enumerate(target_fys):
        val = r["data"].get(p)
        val_prior = r["data"].get(target_fys[i + 1]) if (i + 1 < len(target_fys)) else None
        row_vals.append(_format_cell_abs(val, row_type, negate_val))

        if row_type in ("shares", "eps", "dps", "multiple"):
            pct_disp = "-"
        elif row_type == "metric_pct":
            pct_disp = f"{val:.1f}%" if val is not None else "-"
        elif pct_mode == "rev":
            rev_val = usd_to_m(canonical.get("revenue", {}).get(p))
            pct_disp = f"{((abs(val) if negate_val else val) / rev_val * 100.0):.1f}%" if (rev_val and rev_val != 0 and val is not None) else "-"
        elif pct_mode == "ebt":
            ebt_val = ebt_dict.get(p) if ebt_dict else None
            pct_disp = f"{(abs(val) / abs(ebt_val) * 100.0):.1f}%" if (ebt_val and ebt_val != 0 and val is not None) else "-"
        elif pct_mode == "assets":
            tot_ast = bs_tot_assets.get(p) if bs_tot_assets else None
            pct_disp = f"{(abs(val) / tot_ast * 100.0):.1f}%" if (tot_ast and tot_ast != 0 and val is not None) else "-"
        elif pct_mode == "ni":
            ni_val = usd_to_m(canonical.get("net_income", {}).get(p))
            pct_disp = f"{(val / ni_val * 100.0):.1f}%" if (ni_val and ni_val != 0 and val is not None) else "-"
        else:
            pct_disp = "-"
        row_pcts.append(pct_disp)

        if val is not None and val_prior is not None and abs(val_prior) > 0:
            yoy_pct = ((val - val_prior) / abs(val_prior)) * 100.0
            row_yoys.append("0.0%" if abs(yoy_pct) < 0.05 else f"{yoy_pct:+.1f}%")
        else:
            row_yoys.append("-")

    annual_periods = [p for p in target_fys if p != "LTM"]
    cagr_5y = "-"
    if len(annual_periods) >= 6:
        v_end, v_start = r["data"].get(annual_periods[0]), r["data"].get(annual_periods[5])
        if v_end is not None and v_start is not None and v_start > 0 and v_end > 0:
            cagr_5y = f"{(((v_end / v_start) ** (1.0 / 5.0) - 1.0) * 100.0):+.1f}%"

    annual_cells = [{"abs": row_vals[i], "pct": row_pcts[i], "yoy": row_yoys[i]} for i in range(1, len(target_fys))]
    return {
        "label": r["label"], "orig_tooltip": r.get("orig_tooltip", ""), "clarification": r.get("clarification"),
        "operator": r.get("operator", ""), "row_type": row_type, "indent": r.get("indent", False),
        "is_bold": r.get("is_bold", False), "values": row_vals, "pcts": row_pcts, "yoy": row_yoys, "cagr_5y": cagr_5y,
        "ltm_val": row_vals[0] if row_vals else "-", "ltm_pct": row_pcts[0] if row_pcts else "-",
        "ltm_yoy": row_yoys[0] if row_yoys else "-", "annual_cells": annual_cells,
        "annual_vals": row_vals[1:] if len(row_vals) > 1 else [],
        "latest_val": row_vals[0] if row_vals else "-", "latest_pct": row_pcts[0] if row_pcts else "-",
    }
