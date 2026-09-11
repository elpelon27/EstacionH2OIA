#!/usr/bin/env python3
"""Whatsscanbot — Qdrant indexer (DT-WSIMPORT 2D).

Collection whatsapp_conversations: 768 dim, Cosine.
Embeddings: nomic-embed-text vía Ollama local (solo embeddings;
la regla del Líder prohíbe Ollama para PARSEO, no para embeddings).
IDs determinísticos: uuid5(namespace, msg_hash) → reimport idempotente.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

import requests
from qdrant_client import QdrantClient
from qdrant_client.http import models as qm

logger = logging.getLogger("whatsscan.indexer")

QDRANT_URL = "http://localhost:6333"
COLLECTION = "whatsapp_conversations"
OLLAMA_URL = "http://localhost:11434"
EMBED_MODEL = "nomic-embed-text"
EMBED_DIM = 768
UUID_NS = uuid.uuid5(uuid.NAMESPACE_URL, "whatsscanbot")

_client: QdrantClient | None = None


def client() -> QdrantClient:
    global _client
    if _client is None:
        _client = QdrantClient(url=QDRANT_URL, timeout=30)
    return _client


def ensure_collection() -> None:
    c = client()
    if not c.collection_exists(COLLECTION):
        c.create_collection(
            collection_name=COLLECTION,
            vectors_config=qm.VectorParams(size=EMBED_DIM, distance=qm.Distance.COSINE),
        )
        logger.info("collection %s creada (%dd Cosine)", COLLECTION, EMBED_DIM)


def embed(texts: list[str]) -> list[list[float]]:
    """Embeddings por batch con nomic-embed-text (Ollama)."""
    out: list[list[float]] = []
    for t in texts:
        r = requests.post(
            f"{OLLAMA_URL}/api/embed",
            json={"model": EMBED_MODEL, "input": [t]},
            timeout=60,
        )
        r.raise_for_status()
        out.append(r.json()["embeddings"][0])
    return out


def point_id(msg_hash: str) -> str:
    return str(uuid.uuid5(UUID_NS, msg_hash))


def index_messages(import_id: int, messages: list[dict[str, Any]]) -> int:
    """Indexa mensajes de texto. Devuelve N de puntos upsertados."""
    ensure_collection()
    texts = [m.get("message_text", "") for m in messages
             if m.get("message_type", "text") == "text"]
    msgs = [m for m in messages if m.get("message_type", "text") == "text"]
    if not msgs:
        return 0
    vectors = embed(texts)
    points = [
        qm.PointStruct(
            id=point_id(m.get("msg_hash", "")),
            vector=v,
            payload={
                "import_id": import_id,
                "phone": m.get("phone"),
                "sender": m.get("sender_name"),
                "message": (m.get("message_text") or "")[:2000],
                "timestamp": m.get("timestamp"),
            },
        )
        for m, v in zip(msgs, vectors, strict=True)
    ]
    client().upsert(collection_name=COLLECTION, points=points, wait=True)
    return len(points)


def search(query: str, limit: int = 5, phone: str | None = None) -> list[dict[str, Any]]:
    """Búsqueda semántica; filtro opcional por phone."""
    ensure_collection()
    vec = embed([query])[0]
    flt = qm.FieldCondition(key="phone", match=qm.MatchValue(value=phone)) if phone else None
    res = client().query_points(
        collection_name=COLLECTION,
        query=vec,
        limit=limit,
        query_filter=qm.Filter(must=[flt]) if flt else None,
        with_payload=True,
    )
    return [
        {"score": p.score, **p.payload}  # type: ignore[misc]
        for p in res.points
    ]


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    ensure_collection()
    info = client().get_collection(COLLECTION)
    vec_size = None
    if info.config.params.vectors:
        vp = info.config.params.vectors
        vec_size = vp.size if not isinstance(vp, dict) else None
    print(json.dumps({
        "collection": COLLECTION,
        "points": info.points_count,
        "dim": vec_size,
    }, indent=2))
