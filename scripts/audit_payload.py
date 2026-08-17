#!/usr/bin/env python3
"""Audita cómo mem0 materializó las memorias en Qdrant."""

from qdrant_client import QdrantClient

c = QdrantClient("http://localhost:6333")

res, nxt = c.scroll(
    collection_name="hermes_memory", limit=300, with_payload=True, with_vectors=False
)
pts = res
print("puntos scrolleados:", len(pts))
has_src = sum(1 for p in pts if p.payload.get("source"))
print("puntos con payload[source]:", has_src)

# mostrar estructura de payloads (claves) y ejemplos
from collections import Counter

keycounter: Counter[tuple[str, ...]] = Counter()
examples = {}
for p in pts:
    k = tuple(sorted(p.payload.keys()))
    keycounter[k] += 1
    if k not in examples:
        examples[k] = p
print("\n--- estrucs de payload distintas ---")
for k, n in keycounter.most_common():
    print(f"  {n:3d} pts: claves={k}")

print("\n--- ejemplo de cada estruc ---")
for k, p in list(examples.items())[:5]:
    print("  claves:", k)
    print("   ", {kk: str(vv)[:90] for kk, vv in p.payload.items()})

# progreso json
import json

pr = json.load(open("/mnt/ssd_trabajo/hermes-agent/scripts/.idx_progress.json"))
print("\narchivos completados en progress json:", len(pr["done"]))
