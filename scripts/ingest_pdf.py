#!/usr/bin/env python3
"""
Pipeline de ingesta de la Biblioteca H2O — Líder 💧

Flujo por PDF:
  1. Detecta nuevos PDFs en /mnt/ssd_trabajo/biblioteca/pdfs/inbox/
     (o recorre un directorio dado con --scan).
  2. Si el PDF no tiene capa de texto (escaneado): ocrmypdf -l spa primero.
  3. Sube a Paperless-ngx vía API REST (http://localhost:8001).
  4. Indexa texto en Qdrant (colección biblioteca_h2o, embeddings
     nomic-embed-text vía Ollama, chunks de ~2000 chars).
  5. Extrae hechos clave con Qwen local (Ollama, default qwen2.5:3b).
  6. Guarda los hechos en docs/biblioteca/<slug>.md
  7. Loggea: archivo, páginas, hechos extraídos → logs/ingest.log

Uso:
  venv/bin/python scripts/ingest_pdf.py            # modo watcher (loop)
  venv/bin/python scripts/ingest_pdf.py --once    # una pasada
  venv/bin/python scripts/ingest_pdf.py --scan "pdfs/Agrop M&M" --dry-run
"""

from __future__ import annotations

# ── SSD-first: temporales y caches al SSD, NO al disco raíz ─────────────────
# Debe ir ANTES de cualquier uso de OCR/tesseract/HF/torch. Relevante sobre
# todo desde cron, donde el entorno puede traer otras variables.
import os

os.environ["TMPDIR"] = "/mnt/ssd_trabajo/biblioteca/.tmp"
os.makedirs("/mnt/ssd_trabajo/biblioteca/.tmp", exist_ok=True)
os.environ["TMP"] = os.environ["TMPDIR"]
os.environ["TEMP"] = os.environ["TMPDIR"]
# HF/torch en SSD (refuerza el symlink ~/.cache/huggingface del usuario)
os.environ["HF_HOME"] = "/mnt/ssd_trabajo/skynet_cache/huggingface"
os.environ["TRANSFORMERS_CACHE"] = "/mnt/ssd_trabajo/skynet_cache/huggingface"
os.environ["TORCH_HOME"] = "/mnt/ssd_trabajo/skynet_cache/torch"

import argparse
import hashlib
import json
import logging
import re
import shutil
import subprocess
import sys
import time
import unicodedata
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

import requests

# ── Configuración ────────────────────────────────────────────────────────────
WATCH_DIR = Path("/mnt/ssd_trabajo/biblioteca/pdfs/inbox")
PROCESSED_DIR = Path("/mnt/ssd_trabajo/biblioteca/pdfs/processed")
FAILED_DIR = Path("/mnt/ssd_trabajo/biblioteca/pdfs/failed")
DOCS_DIR = Path("/mnt/ssd_trabajo/hermes-agent/docs/biblioteca")
LOG_FILE = Path("/mnt/ssd_trabajo/hermes-agent/logs/ingest.log")
OCR_TMP = Path("/mnt/ssd_trabajo/biblioteca/ocr-tmp")

PAPERLESS_URL = "http://localhost:8001"
PAPERLESS_USER = "lider"
PAPERLESS_PASS = "biblioteca_h2o_change_me"

QDRANT_URL = "http://localhost:6333"
QDRANT_COLLECTION = "biblioteca_h2o"
EMBED_MODEL = "nomic-embed-text"
EMBED_DIM = 768

OLLAMA_URL = "http://localhost:11434"
FACT_MODEL = "qwen2.5:3b"

POLL_SECONDS = 30

# ── Logging ─────────────────────────────────────────────────────────────────
# Rotación: 10 MB x 5 backups — evita que logs/ingest.log crezca indefinidamente
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        RotatingFileHandler(LOG_FILE, maxBytes=10_000_000, backupCount=5),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("ingest_pdf")


def slugify(name: str) -> str:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    s = re.sub(r"[^\w\s-]", "", s).strip().lower()
    return re.sub(r"[-\s]+", "-", s)[:80]


# ── Paso 0: PDF tiene texto? ─────────────────────────────────────────────────
def pdf_has_text(pdf: Path) -> tuple[bool, int, str]:
    """Devuelve (tiene_texto, num_páginas, texto). Extrae texto con pypdf."""
    try:
        from pypdf import PdfReader
    except ImportError:
        log.warning("pypdf no instalado — instálalo en el venv (pip install pypdf)")
        raise
    reader = PdfReader(str(pdf))
    pages = len(reader.pages)
    text = "\n".join((p.extract_text() or "") for p in reader.pages)
    return (len(text.strip()) > 100), pages, text


# ── Paso 1: OCR si hace falta ────────────────────────────────────────────────
def ensure_text_layer(pdf: Path) -> tuple[Path, bool, int, str]:
    """Si el PDF no tiene texto, OCR con ocrmypdf. Devuelve (path_usable, ocr_aplicado, páginas, texto)."""
    has_text, pages, text = pdf_has_text(pdf)
    if has_text:
        return pdf, False, pages, text
    ocrmypdf = shutil.which("ocrmypdf") or str(
        Path(sys.executable).with_name("ocrmypdf")
    )
    OCR_TMP.mkdir(parents=True, exist_ok=True)
    out = OCR_TMP / f"{pdf.stem}.ocr.pdf"
    log.info("OCR: %s (escaneado, %s páginas)", pdf.name, pages)
    r = subprocess.run(
        [ocrmypdf, str(pdf), str(out), "-l", "spa", "--force-ocr", "--deskew",
         "--temp-dir", str(OCR_TMP)],  # temporales del OCR al SSD, no al raíz
        capture_output=True, text=True,
    )
    if r.returncode != 0 or not out.exists():
        raise RuntimeError(f"ocrmypdf falló en {pdf.name}: {r.stderr[-500:]}")
    has_text, pages, text = pdf_has_text(out)
    if not has_text:
        raise RuntimeError(f"OCR no produjo texto legible: {pdf.name}")
    return out, True, pages, text


# ── Paso 2: subir a Paperless-ngx ────────────────────────────────────────────
def upload_to_paperless(pdf: Path) -> int | None:
    """Sube el PDF a Paperless vía API. Devuelve document_id o None si falla."""
    try:
        with open(pdf, "rb") as f:
            r = requests.post(
                f"{PAPERLESS_URL}/api/documents/post_document/",
                auth=(PAPERLESS_USER, PAPERLESS_PASS),
                files={"document": (pdf.name, f, "application/pdf")},
                timeout=300,
            )
        if r.status_code in (200, 201):
            doc_id = r.json()
            log.info("Paperless: %s → doc_id=%s", pdf.name, doc_id)
            return doc_id
        log.error("Paperless rechazó %s: %s %s", pdf.name, r.status_code, r.text[:200])
    except requests.RequestException as e:
        log.error("Paperless inalcanzable (%s): %s", pdf.name, e)
    return None


# ── Paso 3: Qdrant ───────────────────────────────────────────────────────────
def embed(texts: list[str]) -> list[list[float]]:
    r = requests.post(
        f"{OLLAMA_URL}/api/embed",
        json={"model": EMBED_MODEL, "input": texts},
        timeout=300,
    )
    r.raise_for_status()
    return r.json()["embeddings"]


def chunk_text(text: str, size: int = 2000, overlap: int = 200) -> list[str]:
    chunks = []
    start = 0
    while start < len(text):
        chunks.append(text[start : start + size])
        start += size - overlap
    return chunks


def ensure_qdrant_collection():
    r = requests.get(f"{QDRANT_URL}/collections/{QDRANT_COLLECTION}", timeout=30)
    if r.status_code == 200:
        return
    requests.put(
        f"{QDRANT_URL}/collections/{QDRANT_COLLECTION}",
        json={"vectors": {"size": EMBED_DIM, "distance": "Cosine"}},
        timeout=60,
    ).raise_for_status()
    log.info("Qdrant: colección %s creada", QDRANT_COLLECTION)


def index_in_qdrant(pdf: Path, text: str, doc_id, meta: dict) -> int:
    ensure_qdrant_collection()
    chunks = chunk_text(text)
    if not chunks:
        return 0
    vectors = embed(chunks)
    points = []
    base = hashlib.md5(str(pdf).encode()).hexdigest()[:12]
    for i, (chunk, vec) in enumerate(zip(chunks, vectors)):
        points.append(
            {
                "id": int(hashlib.md5(f"{base}-{i}".encode()).hexdigest()[:15], 16),
                "vector": vec,
                "payload": {
                    "source": str(pdf),
                    "file": pdf.name,
                    "chunk": i,
                    "doc_id": doc_id,
                    **meta,
                },
            }
        )
    requests.put(
        f"{QDRANT_URL}/collections/{QDRANT_COLLECTION}/points",
        json={"points": points},
        timeout=120,
    ).raise_for_status()
    return len(points)


# ── Paso 4: extracción de hechos con Qwen local ──────────────────────────────
FACT_PROMPT = """Eres un analista agrícola experto. Del siguiente texto de un documento
de la biblioteca (ganadería, agricultura regenerativa, preservación de tierras, trading),
extrae los HECHOS CLAVE y TÉCNICAS concretas. Formato:
- Un hecho por línea, empezando con "- ".
- Incluye cifras, condiciones, nombres técnicos y recomendaciones accionables.
- Máximo 20 hechos, solo lo esencial. Responde en español.

TEXTO:
{text}"""


def extract_facts(text: str, model: str) -> list[str]:
    # Limitar texto para no saturar el modelo local
    sample = text[:12000]
    r = requests.post(
        f"{OLLAMA_URL}/api/generate",
        json={
            "model": model,
            "prompt": FACT_PROMPT.format(text=sample),
            "stream": False,
            "options": {"temperature": 0.2},
        },
        timeout=900,
    )
    r.raise_for_status()
    raw = r.json().get("response", "")
    facts = [
        l.strip().lstrip("-• ").strip()
        for l in raw.splitlines()
        if l.strip().startswith(("-", "•"))
    ]
    return [f for f in facts if len(f) > 10][:20]


def save_facts(pdf: Path, facts: list[str], meta: dict, out_dir: Path = DOCS_DIR):
    out_dir.mkdir(parents=True, exist_ok=True)
    slug = slugify(pdf.stem)
    lines = [
        f"# {pdf.stem}",
        "",
        f"- **Archivo:** `{pdf}`",
        f"- **Páginas:** {meta.get('pages', '?')}",
        f"- **OCR aplicado:** {'sí' if meta.get('ocr') else 'no'}",
        f"- **Paperless doc_id:** {meta.get('doc_id', '—')}",
        f"- **Chunks Qdrant:** {meta.get('chunks', '—')}",
        f"- **Ingestado:** {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        "",
        "## Hechos clave (Qwen local)",
        "",
    ]
    lines += [f"- {f}" for f in facts] or ["- (sin hechos extraídos)"]
    (out_dir / f"{slug}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out_dir / f"{slug}.md"


# ── Orquestación ─────────────────────────────────────────────────────────────
def process_pdf(pdf: Path, dry_run: bool = False, fact_model: str = FACT_MODEL) -> dict:
    log.info("── Procesando: %s", pdf.name)
    result = {"file": str(pdf), "pages": 0, "facts": 0, "ocr": False, "status": "ok"}

    usable, ocr_done, pages, text = ensure_text_layer(pdf)
    result["pages"] = pages
    result["ocr"] = ocr_done

    if dry_run:
        log.info("DRY-RUN %s: páginas=%s texto=%s chars ocr=%s", pdf.name, pages, len(text), ocr_done)
        return result

    doc_id = upload_to_paperless(usable)
    result["doc_id"] = doc_id

    chunks = index_in_qdrant(pdf, text, doc_id, {"pages": pages, "ocr": ocr_done})
    result["chunks"] = chunks

    facts = extract_facts(text, fact_model)
    result["facts"] = len(facts)
    md = save_facts(pdf, facts, result)
    result["facts_file"] = str(md)

    log.info(
        "OK %s: páginas=%s ocr=%s chunks=%s hechos=%s → %s",
        pdf.name, pages, ocr_done, chunks, len(facts), md,
    )
    return result


def move_to(pdf: Path, dest_dir: Path):
    if not pdf.exists():
        return  # ya movido por otro consumidor (p.ej. Paperless)
    dest_dir.mkdir(parents=True, exist_ok=True)
    target = dest_dir / pdf.name
    i = 1
    while target.exists():
        target = dest_dir / f"{pdf.stem}_{i}{pdf.suffix}"
        i += 1
    shutil.move(str(pdf), str(target))


def run_once(scan_dir: Path | None = None, dry_run: bool = False, fact_model: str = FACT_MODEL) -> list[dict]:
    search_dir = scan_dir or WATCH_DIR
    pdfs = sorted(search_dir.rglob("*.pdf")) if search_dir.is_dir() else []
    if not scan_dir:
        pdfs = [p for p in pdfs if PROCESSED_DIR not in p.parents and FAILED_DIR not in p.parents]
    log.info("Pasada: %s PDFs en %s", len(pdfs), search_dir)
    results = []
    for pdf in pdfs:
        try:
            res = process_pdf(pdf, dry_run=dry_run, fact_model=fact_model)
            results.append(res)
            if not dry_run and not scan_dir:
                move_to(pdf, PROCESSED_DIR)
        except Exception as e:
            log.error("FALLO %s: %s", pdf.name, e)
            results.append({"file": str(pdf), "status": "error", "error": str(e)})
            if not dry_run and not scan_dir:
                move_to(pdf, FAILED_DIR)
    return results


def main():
    ap = argparse.ArgumentParser(description="Ingesta Biblioteca H2O")
    ap.add_argument("--once", action="store_true", help="una sola pasada y salir")
    ap.add_argument("--scan", type=str, help="directorio a escanear (no watcher)")
    ap.add_argument("--dry-run", action="store_true", help="no subir/indexar, solo diagnóstico")
    ap.add_argument("--model", type=str, default=FACT_MODEL, help="modelo Ollama para hechos")
    args = ap.parse_args()

    WATCH_DIR.mkdir(parents=True, exist_ok=True)
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

    scan_dir = Path(args.scan) if args.scan else None
    if args.once or args.dry_run or args.scan:
        results = run_once(scan_dir, dry_run=args.dry_run, fact_model=args.model)
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return

    log.info("Watcher activo en %s (Ctrl+C para parar)", WATCH_DIR)
    while True:
        run_once()
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
