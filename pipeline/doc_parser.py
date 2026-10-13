"""
doc_parser.py - Procesador de presentaciones a inversores (PDFs) y transcripciones de llamadas de resultados (Earnings Calls).
Escanea la carpeta de Google Drive correspondiente al Ticker y extrae guidance, métricas cualitativas y Q&A.
"""

import os
import sys
import re
import json
import argparse
from pathlib import Path
from datetime import datetime
from pypdf import PdfReader


try:
    from drive_manager import (
        load_sec_config,
        resolve_google_drive_path,
        find_ticker_drive_dir,
        get_ticker_drive_processed_dir,
        safe_copy_file
    )
except ImportError:
    try:
        from .drive_manager import (
            load_sec_config,
            resolve_google_drive_path,
            find_ticker_drive_dir,
            get_ticker_drive_processed_dir,
            safe_copy_file
        )
    except ImportError:
        def load_sec_config():
            return {
                "google_drive_base_path": "G:\\Mi unidad\\analisis fundamental",
                "local_output_path": "data\\processed"
            }
        def resolve_google_drive_path(custom_path=None):
            return Path(custom_path) if custom_path else Path("G:\\Mi unidad\\analisis fundamental")
        def find_ticker_drive_dir(ticker, custom_drive_path=None):
            base_drive = resolve_google_drive_path(custom_drive_path)
            c = base_drive / ticker.upper()
            return c if c.exists() else None


def extract_text_from_pdf(pdf_path):
    """Extrae texto página por página / slide por slide de un archivo PDF."""
    slides = []
    try:
        reader = PdfReader(pdf_path)
        for idx, page in enumerate(reader.pages):
            text = page.extract_text() or ""
            clean_text = "\n".join([line.strip() for line in text.splitlines() if line.strip()])
            if clean_text:
                slides.append({
                    "slide_number": idx + 1,
                    "content": clean_text
                })
    except Exception as e:
        print(f"[Doc Parser] Error al leer PDF {pdf_path.name}: {e}")
    return slides


def extract_guidance_and_kpis(text):
    """Detecta menciones de guidance, objetivos futuros y métricas cuantitativas clave."""
    keywords = [
        "guidance", "outlook", "expect", "forecast", "target", "projected", "objective",
        "margin", "revenue growth", "capex", "free cash flow", "fy2", "q1", "q2", "q3", "q4"
    ]
    extracted_lines = []
    for line in text.splitlines():
        line_lower = line.lower()
        if any(k in line_lower for k in keywords) and any(c.isdigit() for c in line):
            if len(line.strip()) > 15:
                extracted_lines.append(line.strip())
    return extracted_lines[:15]


def parse_transcript_text(transcript_text):
    """Separa una transcripción entre la presentación de ejecutivos y la sesión de Q&A con analistas."""
    qa_patterns = [
        r"(?:operator,\s+(?:may|can)\s+we\s+have\s+the\s+first\s+question)",
        r"(?:take\s+our\s+first\s+question\s+from)",
        r"(?:open\s+the\s+call\s+to\s+questions\s+from\s+analysts)",
        r"(question[\s-]and[\s-]answer\s+session)",
        r"(questions\s+and\s+answers)",
        r"(q\s*&\s*a\s+session)",
        r"(analyst\s+q&a)"
    ]
    
    qa_split_idx = -1
    for pat in qa_patterns:
        m = re.search(pat, transcript_text, re.IGNORECASE)
        if m:
            qa_split_idx = m.start()
            break
            
    if qa_split_idx != -1:
        exec_part = transcript_text[:qa_split_idx].strip()
        qa_part = transcript_text[qa_split_idx:].strip()
    else:
        exec_part = transcript_text.strip()
        qa_part = ""
        
    # Extraer preguntas y respuestas estructuradas
    qa_items = []
    if qa_part:
        speaker_pattern = r'\n\n([A-Z][a-zA-Z\s\.\,\-]+)\n(Director of Investor Relations|CEO|CFO|Incoming CEO|Analyst|Operator)\n(\d+:\d+:\d+)\n\n'
        parts = re.split(speaker_pattern, qa_part)
        
        curr_analyst = None
        curr_q = []
        curr_answers = []
        
        i = 1
        while i < len(parts):
            name = parts[i].strip()
            role = parts[i+1].strip()
            ts = parts[i+2].strip()
            content = parts[i+3].strip() if i+3 < len(parts) else ''
            
            if role == 'Analyst':
                if curr_analyst and curr_q:
                    ans_text = " | ".join(curr_answers) if curr_answers else "Sin respuesta directa"
                    qa_items.append(f"**{curr_analyst}:** {' '.join(curr_q)[:400]}... \n  - *Respuesta:* {ans_text[:500]}...")
                    curr_answers = []
                    curr_q = []
                clean_name = name.split("from")[-1].strip() if "from" in name else name
                curr_analyst = f"{clean_name} ({ts})"
                curr_q.append(content)
            elif role in ['CEO', 'CFO', 'Incoming CEO']:
                if curr_analyst:
                    curr_answers.append(f"{name} ({role}): {content}")
            i += 4
            
        if curr_analyst and curr_q:
            ans_text = " | ".join(curr_answers) if curr_answers else "Sin respuesta directa"
            qa_items.append(f"**{curr_analyst}:** {' '.join(curr_q)[:400]}... \n  - *Respuesta:* {ans_text[:500]}...")

        # Formato FactSet / StreetEvents (ej. Jay Sole \n Analyst, UBS ... Q / Stefano Caroti ... A)
        if not qa_items:
            factset_pattern = r'\n([A-Z][a-zA-Z\s\.\,\-]+)\n([^\n]+?)\s+([QA])\s*\n'
            fs_parts = re.split(factset_pattern, qa_part)
            if len(fs_parts) > 3:
                curr_q_analyst = None
                curr_q_body = ""
                curr_a_list = []
                
                k = 1
                while k < len(fs_parts):
                    spk_name = fs_parts[k].strip()
                    spk_role = fs_parts[k+1].strip()
                    tag = fs_parts[k+2].strip()
                    body = fs_parts[k+3].strip() if k+3 < len(fs_parts) else ""
                    # Limpiar headers de factset repetidos universales (cualquier compañía)
                    body_clean = re.sub(r'^[^\n]+?\s+FACTSET\s+www\.callstreet\.com\s*', '', body, flags=re.MULTILINE)
                    body_clean = re.sub(r'.*?FACTSET\s+www\.callstreet\.com\s*', '', body_clean)
                    
                    if tag == "Q":
                        if curr_q_analyst and curr_q_body:
                            ans_str = " | ".join(curr_a_list) if curr_a_list else "Sin respuesta directa"
                            qa_items.append(f"**{curr_q_analyst}:** {curr_q_body[:350]}... \n  - *Respuesta:* {ans_str[:450]}...")
                            curr_a_list = []
                        curr_q_analyst = f"{spk_name} ({spk_role})"
                        curr_q_body = body_clean
                    elif tag == "A":
                        if curr_q_analyst:
                            curr_a_list.append(f"{spk_name}: {body_clean[:300]}")
                    k += 4
                    
                if curr_q_analyst and curr_q_body:
                    ans_str = " | ".join(curr_a_list) if curr_a_list else "Sin respuesta directa"
                    qa_items.append(f"**{curr_q_analyst}:** {curr_q_body[:350]}... \n  - *Respuesta:* {ans_str[:450]}...")
            
    return {
        "executive_remarks_length": len(exec_part),
        "executive_remarks_preview": exec_part[:2000] + ("..." if len(exec_part) > 2000 else ""),
        "has_qa_section": len(qa_part) > 0,
        "qa_highlights": qa_items[:12]
    }


def parse_driver_documents(ticker, custom_drive_path=None, output_dir=None):
    """Escanea la carpeta de Drive del Ticker y compila el dossier cualitativo unificado."""
    cfg = load_sec_config()
    ticker_dir = find_ticker_drive_dir(ticker, custom_drive_path)
    
    if output_dir is None:
        output_dir = Path(cfg.get("local_output_path", "data/processed")) / ticker.upper()
    else:
        output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"\n[Doc Parser] Escaneando documentos para {ticker.upper()}...")
    print(f"[Doc Parser] Carpeta Drive: {ticker_dir}")
    
    dossier = {
        "ticker": ticker.upper(),
        "scan_timestamp": datetime.now().isoformat(),
        "drive_folder": str(ticker_dir) if ticker_dir else "No encontrada",
        "presentations_found": [],
        "transcripts_found": [],
        "sec_narratives_summary": {}
    }
    
    # 1. Cargar narrativas SEC previas si existen
    sec_narrative_path = output_dir / "sec_narrative.json"
    if sec_narrative_path.exists():
        try:
            with open(sec_narrative_path, "r", encoding="utf-8") as f:
                sec_raw = json.load(f)
                dossier["sec_narratives_summary"] = {
                    "filing_date": sec_raw.get("filing_date"),
                    "item_1_business_summary": sec_raw.get("item_1_business", "")[:2000] + "...",
                    "item_1a_risks_summary": sec_raw.get("item_1a_risk_factors", "")[:2000] + "...",
                    "item_7_mda_summary": sec_raw.get("item_7_mda", "")[:2000] + "..."
                }
                print("[Doc Parser] Narrativas oficiales 10-K integradas con éxito.")
        except Exception as e:
            print(f"[Doc Parser] Error al leer sec_narrative.json: {e}")
            
    # 2. Escanear archivos en la carpeta de Drive (excluyendo subcarpeta processed)
    if ticker_dir and ticker_dir.exists():
        all_files = [f for f in ticker_dir.rglob("*") if "processed" not in f.parts]
        pdf_files = [f for f in all_files if f.is_file() and f.suffix.lower() == ".pdf"]
        text_files = [f for f in all_files if f.is_file() and f.suffix.lower() in [".txt", ".md"]]
        
        print(f"[Doc Parser] Archivos detectados en Drive: {len(pdf_files)} PDFs, {len(text_files)} textos/transcripciones.")
        
        # Procesar archivos PDF (diferenciando presentaciones de transcripciones)
        for pdf in pdf_files:
            rel_path = str(pdf.relative_to(ticker_dir)).lower()
            is_transcript_pdf = "transcript" in pdf.name.lower() or "transcript" in rel_path or "transcripts" in [p.lower() for p in pdf.parts]
            
            if is_transcript_pdf:
                print(f"[Doc Parser] Procesando transcripción en PDF: {pdf.name}")
                slides = extract_text_from_pdf(pdf)
                full_text = "\n".join([s["content"] for s in slides])
                parsed_t = parse_transcript_text(full_text)
                guidance = extract_guidance_and_kpis(full_text)
                dossier["transcripts_found"].append({
                    "filename": pdf.name,
                    "relative_path": str(pdf.relative_to(ticker_dir)),
                    "total_pages": len(slides),
                    "guidance_kpi_extracted": guidance,
                    "parsed_transcript": parsed_t
                })
            else:
                print(f"[Doc Parser] Procesando presentación PDF: {pdf.name}")
                slides = extract_text_from_pdf(pdf)
                full_text = "\n".join([s["content"] for s in slides])
                guidance = extract_guidance_and_kpis(full_text)
                
                dossier["presentations_found"].append({
                    "filename": pdf.name,
                    "relative_path": str(pdf.relative_to(ticker_dir)),
                    "total_slides": len(slides),
                    "guidance_kpi_extracted": guidance,
                    "slides_sample": slides[:5]  # Primeras 5 diapositivas
                })
            
        # Procesar Transcripciones (TXT / MD)
        for txt in text_files:
            print(f"[Doc Parser] Procesando transcripción en texto: {txt.name}")
            try:
                with open(txt, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                parsed_t = parse_transcript_text(content)
                guidance = extract_guidance_and_kpis(content)
                dossier["transcripts_found"].append({
                    "filename": txt.name,
                    "relative_path": str(txt.relative_to(ticker_dir)),
                    "guidance_kpi_extracted": guidance,
                    "parsed_transcript": parsed_t
                })
            except Exception as e:
                print(f"[Doc Parser] Error leyendo transcripción {txt.name}: {e}")
    else:
        print(f"[Doc Parser] Aviso: La carpeta {ticker_dir} está lista para recibir PDFs de presentaciones y transcripciones.")
        
    # Guardar resultado cualitativo unificado
    out_file = output_dir / "qualitative_dossier.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(dossier, f, indent=2, ensure_ascii=False)
    print(f"[Doc Parser] Dossier cualitativo guardado en: {out_file}")
    
    return dossier


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--drive-path", default=None)
    parser.add_argument("--out-dir", default=None)
    args = parser.parse_args()
    
    parse_driver_documents(args.ticker, args.drive_path, args.out_dir)
