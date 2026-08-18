#!/usr/bin/env python3
"""Cobertura completa: incrusta y upserts chunks de TODOS los 78 .md en
hermes_memory con metadatos source/title, de forma determinista (sin la
extracción LLM frágil de mem0). Usa el mismo embedder nomic-embed-text.
"""

import hashlib
import json
import sys
import time
import urllib.request
import uuid
from datetime import UTC, datetime
from pathlib import Path

from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct

OLLAMA = "http://localhost:11434"
Q_URL = "http://localhost:6333"
COLL = "hermes_memory"
MAX_CHUNK = 3400  # nomic-embed-text falla (500) pasado ~2000-4000 chars (ctx 2048)
SPLIT = 3400
USER = "obsidian_docs"


def embed(text: str) -> list[float]:
    req = urllib.request.Request(
        OLLAMA + "/api/embeddings",
        data=json.dumps({"model": "nomic-embed-text:latest", "prompt": text}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())["embedding"]  # type: ignore[no-any-return]


def chunk_text(text: str) -> list[str]:
    if len(text) <= SPLIT:
        return [text]
    out, cur = [], ""
    for line in text.split("\n"):
        if len(cur) + len(line) + 1 > MAX_CHUNK and cur:
            out.append(cur)
            cur = ""
        cur += line + "\n"
        if len(cur) > MAX_CHUNK:
            out.append(cur)
            cur = ""
    if cur.strip():
        out.append(cur)
    return [c for c in out if c.strip()]


def main(force: bool = False) -> None:
    files = sorted(set(l.strip() for l in open("/tmp/doclist.txt") if l.strip()))
    print("archivos a cubrir:", len(files), flush=True)

    # vectores existentes: ignorar, escribimos solo con md5 determinista de (source,chunk,numero)
    existing = set()
    c = QdrantClient(Q_URL)
    if force:
        print(
            "--force: se re-upsertan TODOS los puntos obsidian_docs (existing ignorado)", flush=True
        )
    else:
        off: int | str | None = 0
        have = True
        while have:
            pts, nxt = c.scroll(
                collection_name=COLL,
                limit=500,
                offset=off,
                with_payload=["source", "title", "chunk"],
                with_vectors=False,
            )
            for p in pts:
                if p.payload is not None and p.payload.get("kind") == "obsidian_docs" and p.payload.get("source"):
                    existing.add(
                        (
                            p.payload["source"],
                            p.payload.get("chunk", ""),
                            p.payload.get("title", ""),
                        )
                    )
            if nxt is None:
                have = False
            else:
                off = nxt
        print("pts observados kind=obsidian_docs:", len(existing), flush=True)

    t0 = time.time()
    added = 0
    for rel in files:
        text = Path(rel).read_text(encoding="utf-8", errors="ignore")
        chunks = chunk_text(text)
        title = Path(rel).stem
        for ci, ch in enumerate(chunks):
            key = (rel, str(ci), title)
            if key in existing:
                continue
            vec = embed(ch)
            h = hashlib.md5(ch.encode()).hexdigest()
            pid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"obsidian_{rel}#{ci}:{h}"))
            c.upsert(
                collection_name=COLL,
                points=[
                    PointStruct(
                        id=pid,
                        vector=vec,
                        payload={
                            "source": rel,
                            "title": title,
                            "chunk": ci,
                            "kind": "obsidian_docs",
                            "user_id": USER,
                            "hash": h,
                            "data": ch[:2000],
                            "created_at": datetime.now(UTC).isoformat(),
                            "updated_at": datetime.now(UTC).isoformat(),
                        },
                    )
                ],
            )
            added += 1
        print(f"  [upsert] {rel} chunks={len(chunks)} ({time.time()-t0:.0f}s)", flush=True)
    print(f"DONE added_new={added} time={time.time()-t0:.0f}s", flush=True)


if __name__ == "__main__":
    main(force="--force" in sys.argv)
