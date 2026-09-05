#!/usr/bin/env python3
"""
============================================================================
claude-watch adaptado a Hermes — análisis de video → conocimiento
============================================================================
Pipeline:
  1. Descarga (yt-dlp) + transcript (captions nativos VTT)  [reutiliza source]
  2. Frames JPEG (ffmpeg, scene-change + uniform)            [reutiliza source]
  3. Análisis con LLMClient task_type="video" (Gemini 3 Pro vía OpenRouter,
     frames como imágenes base64 + transcript)
  4. Decisión de "tema" (auto → el LLM lo clasifica)
  5. Outputs: docs/videos/<id>.md + <id>.json + espejo obsidian-vault/videos/
  6. Indexado del transcript en Qdrant videos_h2o (nomic-embed-text, 768)
     con campo "tema" OBLIGATORIO para routing futuro de skills.

Regla del Líder: el tier video NO se usa para chat; chat sigue en GLM→Ollama.
"""
from __future__ import annotations

import argparse
import base64
import json
import logging
import re
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

REPO = Path("/mnt/ssd_trabajo/hermes-agent")
sys.path.insert(0, str(REPO))  # para scripts.llm_client
sys.path.insert(0, str(REPO / "skills" / "claude-watch-source" / "scripts"))

import httpx  # noqa: E402
from download import download, is_url  # noqa: E402
from frames import extract, get_metadata  # noqa: E402
from qdrant_client import QdrantClient  # noqa: E402
from qdrant_client.models import PointStruct  # noqa: E402
from transcribe import parse_vtt  # noqa: E402

from scripts.llm_client import LLMClient  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("claude-watch")

FRAME_WIDTH = 512
MAX_FRAMES = 60          # presupuesto de tokens: ~40-80k para 512px
CHUNK_CHARS = 1200       # tamaño de chunk de transcript para Qdrant
EMBED_MODEL = "nomic-embed-text:latest"
QDRANT_URL = "http://localhost:6333"
EMBED_URL = "http://localhost:11434/api/embeddings"

TEMAS_VALIDOS = {"agropecuario", "h2o", "otro"}

ANALYSIS_PROMPT = """Analizás videos como un editor experto. Recibís frames
extraídos (en orden cronológico, con timestamps) y el transcript del video.

Tu trabajo:
1. Devolver un JSON válido (SIN markdown, sin ```json, JSON puro) con:
{
  "tldr": ["3-5 bullets con lo esencial"],
  "key_moments": [{"timestamp": "MM:SS o HH:MM:SS", "desc": "..."}],
  "key_facts": ["hechos concretos, datos, afirmaciones verificables"],
  "quotable": ["2-3 frases textuales destacadas"],
  "entities": ["personas, empresas, herramientas, lugares"],
  "concepts": ["frameworks, modelos mentales, patrones"],
  "tema_sugerido": "agropecuario|h2o|otro",
  "skill_proposal": "nombre-kebab-case o null"
}
2. tema_sugerido: clasificá por contenido (producción agropecuaria/ganadería/
agricultura → agropecuario; negocio de agua/botellones/despacho → h2o;
resto → otro).
3. skill_proposal: SOLO si el video enseña un procedimiento operativo
replicable; si no, null.

El intent del usuario (por qué se mira el video): {intent}"""


def video_id_from(url: str, title: str) -> str:
    """ID estable: id de YouTube si existe, si no slug del título."""
    m = re.search(r"(?:v=|youtu\.be/|shorts/)([A-Za-z0-9_-]{11})", url)
    if m:
        return f"yt-{m.group(1)}"
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:40]
    return f"vid-{slug or 'unknown'}"


def extract_frames(video_path: str, work: Path, interval: int) -> tuple[list[dict], dict]:
    """Frames uniformes cada `interval` segundos, cap MAX_FRAMES."""
    meta = get_metadata(video_path)
    duration = meta.get("duration") or 0
    n = min(int(duration // interval) + 1, MAX_FRAMES) if duration else MAX_FRAMES
    raw = extract(video_path, work / "frames", fps=1.0 / interval,
                  resolution=FRAME_WIDTH, max_frames=n)
    frames = [{
        "timestamp": int(f["timestamp_seconds"]),
        "timestamp_h": f"{int(f['timestamp_seconds'] // 3600):02d}:"
                       f"{int(f['timestamp_seconds'] % 3600 // 60):02d}:"
                       f"{int(f['timestamp_seconds'] % 60):02d}",
        "frame_path": f["path"],
    } for f in raw]
    return frames, meta


def transcript_from(vtt_path: str | None) -> str:
    if not vtt_path or not Path(vtt_path).exists():
        return ""
    cues = parse_vtt(vtt_path)
    return "\n".join(
        f"[{int(c['start']) // 3600:02d}:{int(c['start']) % 3600 // 60:02d}:"
        f"{int(c['start']) % 60:02d}] {c['text']}"
        for c in cues
    )


def analyze(frames: list[dict], transcript: str, intent: str,
            llm: LLMClient) -> dict:
    """LLM multimodal: frames base64 + transcript → JSON de análisis."""
    content: list[dict] = [{"type": "text", "text":
        ANALYSIS_PROMPT.format(intent=intent or "resumen general")
        + "\n\nTRANSCRIPT:\n" + (transcript[:30000] or "(sin transcript)")}]
    n_frames = 0
    for f in frames:
        p = Path(f["frame_path"])
        if not p.exists() or p.stat().st_size > 1_500_000:
            continue
        b64 = base64.b64encode(p.read_bytes()).decode()
        content.append({"type": "text", "text": f"\nFRAME t={f['timestamp_h']}"})
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
        })
        n_frames += 1
    log.info("Análisis: %d frames + %d chars transcript", n_frames, len(transcript))
    resp = llm.complete(
        [{"role": "user", "content": content}],
        task_type="video",
        temperature=0.3,
        max_tokens=4096,
    )
    if "error" in resp:
        raise RuntimeError(f"LLM video falló: {resp['error']}")
    txt = resp["content"].strip()
    if txt.startswith("```"):
        txt = re.sub(r"^```(json)?\s*|\s*```$", "", txt)
    try:
        return json.loads(txt)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", txt, re.S)
        if not m:
            raise
        return json.loads(m.group(0))


def embed(text: str) -> list[float]:
    r = httpx.post(EMBED_URL, json={"model": EMBED_MODEL, "prompt": text},
                   timeout=120)
    r.raise_for_status()
    return r.json()["embedding"]


def index_qdrant(collection: str, payload: dict, transcript: str,
                 tema: str) -> int:
    """Chunk transcript + indexar. Devuelve nº de puntos guardados."""
    if not transcript:
        return 0
    chunks = [transcript[i:i + CHUNK_CHARS]
              for i in range(0, len(transcript), CHUNK_CHARS)]
    base_id = re.sub(r"[^a-z0-9-]", "", payload["video_id"].lower())
    points = []
    for i, chunk in enumerate(chunks):
        points.append(PointStruct(
            id=f"{base_id}-c{i:04d}",
            vector=embed(chunk),
            payload={
                **payload,
                "tema": tema,
                "transcript_chunk_id": f"{base_id}-c{i:04d}",
                "chunk": chunk,
                "indexed_at": datetime.now(UTC).isoformat(),
            },
        ))
    client = QdrantClient(url=QDRANT_URL, timeout=60)
    client.upsert(collection_name=collection, points=points, wait=True)
    return len(points)


def write_outputs(out_dir: Path, obsidian_dir: Path, data: dict) -> None:
    vid = data["video_id"]
    jpath = out_dir / f"{vid}.json"
    jpath.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                     encoding="utf-8")

    an = data.get("analysis", {})
    md = [
        f"# {data['title']}",
        "",
        f"- **URL**: {data['url']}",
        f"- **Duración**: {data['duration_sec']}s",
        f"- **Tema**: {data['tema']}",
        f"- **Analizado con**: {data.get('llm_model', '')}",
        f"- **Fecha**: {data.get('analyzed_at', '')}",
        "",
        "## TL;DR",
        *[f"- {b}" for b in an.get("tldr", [])],
        "",
        "## Momentos clave",
        *[f"- **{m.get('timestamp', '?')}**: {m.get('desc', '')}"
          for m in an.get("key_moments", [])],
        "",
        "## Hechos clave",
        *[f"- {f}" for f in an.get("key_facts", [])],
        "",
        "## Citas",
        *[f"> {q}" for q in an.get("quotable", [])],
        "",
        "## Entidades / Conceptos",
        ", ".join(an.get("entities", [])) or "—",
        "",
        ", ".join(an.get("concepts", [])) or "—",
        "",
        "## Transcript",
        data.get("transcript", "") or "(no disponible)",
    ]
    mtext = "\n".join(md)
    (out_dir / f"{vid}.md").write_text(mtext, encoding="utf-8")
    obsidian_dir.mkdir(parents=True, exist_ok=True)
    (obsidian_dir / f"{vid}.md").write_text(mtext, encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(
        prog="claude-watch",
        description="Analiza un video (YouTube/local) y lo convierte en "
                    "conocimiento indexado en Qdrant.")
    ap.add_argument("source", help="URL de YouTube o ruta local")
    ap.add_argument("--output-dir", default="docs/videos")
    ap.add_argument("--obsidian-dir", default="obsidian-vault/videos")
    ap.add_argument("--qdrant-collection", default="videos_h2o")
    ap.add_argument("--llm-tier", default="gemini-3-pro-preview")
    ap.add_argument("--tema", default="auto",
                    help="auto|agropecuario|h2o|otro (auto = Gemini clasifica)")
    ap.add_argument("--intent", default="", help="Por qué se mira el video")
    ap.add_argument("--frame-interval", type=int,
                    default=int(__import__("os").environ.get(
                        "YOUTUBE_VIDEO_FRAME_INTERVAL", "10")),
                    help="Segundos entre frames (default: env o 10)")
    ap.add_argument("--no-qdrant", action="store_true")
    ap.add_argument("--no-frames", action="store_true",
                    help="Solo transcript + análisis de texto")
    args = ap.parse_args()

    interval = max(5, args.frame_interval)
    work = Path(tempfile.mkdtemp(prefix="claude-watch-"))
    out_dir = (REPO / args.output_dir).resolve()
    obsidian_dir = (REPO / args.obsidian_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. Descarga
    log.info("Descargando: %s", args.source)
    d = download(args.source, str(work)) if is_url(args.source) else None
    if d is None:
        ap.error("Solo URLs soportadas en esta adaptación (usar yt-dlp para local)")
    video_path = d["video_path"]
    title = (d.get("info") or {}).get("title") or video_path
    url = args.source
    vid = video_id_from(url, title)
    log.info("Video: %s (%s)", title, vid)

    # 2. Frames
    meta = {}
    frames = []
    if not args.no_frames:
        frames, meta = extract_frames(video_path, work, interval)
        log.info("Frames: %d", len(frames))
    else:
        meta = get_metadata(video_path)

    # 3. Transcript
    transcript = transcript_from(d.get("subtitle_path"))
    log.info("Transcript: %d chars", len(transcript))

    # 4. Análisis LLM
    llm = LLMClient()
    tier = next((t for t in llm.tier_chain if t["name"] == args.llm_tier), None)
    if not tier or not tier.get("video_ok"):
        log.error("Tier %s no existe o no es video_ok", args.llm_tier)
        return 2
    analysis = analyze(frames, transcript, args.intent, llm)

    # 5. Tema
    tema = args.tema if args.tema != "auto" else analysis.get("tema_sugerido", "otro")
    if tema not in TEMAS_VALIDOS:
        tema = "otro"
    log.info("Tema: %s", tema)

    # 6. Outputs + Qdrant
    payload = {
        "video_id": vid,
        "url": url,
        "title": title,
        "duration_sec": int(meta.get("duration") or 0),
    }
    n_points = 0
    if not args.no_qdrant:
        try:
            n_points = index_qdrant(args.qdrant_collection, payload,
                                    transcript, tema)
            log.info("Qdrant: %d puntos en %s", n_points, args.qdrant_collection)
        except Exception as e:  # noqa: BLE001 — Qdrant/Ollama caído no aborta el MD
            log.error("Qdrant falló (outputs igual se generan): %s", e)

    data = {
        **payload,
        "transcript": transcript,
        "key_frames": [{"timestamp": f["timestamp"],
                        "frame_path": f["frame_path"]} for f in frames],
        "analysis": analysis,
        "tema": tema,
        "llm_model": tier["model"],
        "analyzed_at": datetime.now(UTC).isoformat(),
        "indexed_in_qdrant": n_points > 0,
        "qdrant_points": n_points,
        "obsidian_path": str((obsidian_dir / f"{vid}.md").relative_to(REPO)),
    }
    write_outputs(out_dir, obsidian_dir, data)
    log.info("OK: %s | %s | %s.json", vid, tema, out_dir / f"{vid}.json")
    print(json.dumps({"video_id": vid, "tema": tema, "points": n_points,
                      "md": str(out_dir / f"{vid}.md"),
                      "json": str(out_dir / f"{vid}.json")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
