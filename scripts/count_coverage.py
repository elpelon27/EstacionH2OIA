#!/usr/bin/env python3
"""Recuento preciso: archivos representados en qdrant vs los 78 canonicos."""

from qdrant_client import QdrantClient

c = QdrantClient("http://localhost:6333")
res = c.scroll(collection_name="hermes_memory", limit=2000, with_payload=True, with_vectors=False)[
    0
]

# puntos y fuentes de los indexados (kind=obsidian o con source)
mine = [p for p in res if p.payload.get("source")]
srcs: dict[str, int] = {}
for p in mine:
    s = p.payload.get("source")
    srcs[s] = srcs.get(s, 0) + 1

print("total puntos en coleccion:", len(res))
print("puntos indexados (con source):", len(mine))
print("archivos distintos representados:", len(srcs))

# lista canonica de 78
canon = sorted(set(l.strip() for l in open("/tmp/doclist.txt") if l.strip()))
print("canonicos:", len(canon))
covered = set(srcs.keys())
missing = [f for f in canon if f not in covered]
print("cubiertos:", len(covered), "| faltantes en qdrant:", len(missing))
for f in missing[:20]:
    print("   FALTA:", f)

# fallback: algunos puntos de mem0 guardan el chunk bajo 'data'; buscar por titulo/source parcial
# mostrar cuantos puntos por archivo para los representados
print("\npor archivo (primeros 10):")
for s, n in sorted(srcs.items(), key=lambda x: -x[1])[:10]:
    print(f"   {n:3d}  {s}")
