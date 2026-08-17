#!/usr/bin/env python3
"""Verificación final de la memoria tripartita tras indexar los 78 .md."""

from qdrant_client import QdrantClient

print("=" * 60)
print("1) ESTADO DE LA COLECCIÓN QDRANT")
print("=" * 60)
c = QdrantClient("http://localhost:6333")
cols = [x.name for x in c.get_collections().collections]
print("colecciones:", cols)
info = c.get_collection("hermes_memory")
print("puntos (memorias) en hermes_memory:", info.points_count)
print("config vectores:", info.config.params.vectors)

# distinct source (archivos indexados)
res = c.scroll(collection_name="hermes_memory", limit=500, with_payload=["source"])[0]
sources: dict[str, int] = {}
for pt in res:
    s = pt.payload.get("source")
    if s:
        sources[s] = sources.get(s, 0) + 1
print("archivos distintos indexados:", len(sources), "de 78")
print("total memorias por archivos:", sum(sources.values()))

print()
print("=" * 60)
print("2) BÚSQUEDA SEMÁNTICA (búsqueda directa en Qdrant, sin mem0 LLM)")
print("=" * 60)
# usar el embedder nomic via ollama para una query
import json as _j
import urllib.request


def embed(text: str) -> list[float]:
    req = urllib.request.Request(
        "http://localhost:11434/api/embeddings",
        data=_j.dumps({"model": "nomic-embed-text:latest", "prompt": text}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as r:
        return _j.loads(r.read())["embedding"]  # type: ignore[no-any-return]


for q in ["deuda técnica del proyecto", "arquitectura de Estación H2O", "agentes de hermes"]:
    vec = embed(q)
    hits = c.query_points(
        collection_name="hermes_memory", query=vec, limit=3, with_payload=True
    ).points
    print(f"\nQUERY: {q!r}")
    for h in hits:
        print(
            f"  score={h.score:.3f} src={h.payload.get('source')} "
            f"title={h.payload.get('title', '')}"
        )

print()
print("=" * 60)
print("3) MEMORIA TRIPARTITA")
print("=" * 60)
# state.db (SQLite hermès)
import sqlite3

con = sqlite3.connect("/home/skynet/hermes-unified/state.db")
n_sessions = con.execute("select count(*) from sessions").fetchone()[0]
n_msg = con.execute("select count(*) from messages").fetchone()[0]
print(f"state.db: {n_sessions} sesiones, {n_msg} mensajes")
# Redis
import subprocess

r = subprocess.run(["redis-cli", "dbsize"], capture_output=True, text=True)
print("redis dbsize:", r.stdout.strip())
# qdrant ya visto
print("qdrant hermes_memory puntos:", info.points_count)
print("Verificación completa: OK")
