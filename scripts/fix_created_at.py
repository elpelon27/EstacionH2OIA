#!/usr/bin/env python3
"""Fix causa-raíz: los puntos obsidian_docs de hermes_memory tenían
created_at/updated_at como float (time.time()), y mem0 espera string ISO
timezone-aware (datetime.fromisoformat). Re-upserta todos esos puntos
conservando el vector e id (pids deterministas uuid5), solo reescribiendo
el timestamp como ISO-UTC. Verificado 2026-08-15."""

import json
from datetime import UTC, datetime

from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct

Q_URL = "http://localhost:6333"
COLL = "hermes_memory"


def main():
    c = QdrantClient(Q_URL)
    fixed = skipped = 0
    off, have = 0, True
    while have:
        pts, nxt = c.scroll(
            collection_name=COLL,
            limit=500,
            offset=off,
            with_payload=True,
            with_vectors=True,
        )
        to_upsert = []
        for p in pts:
            if p.payload.get("kind") != "obsidian_docs":
                continue
            now = datetime.now(UTC).isoformat()
            payload = dict(p.payload)
            old = payload.get("created_at")
            if isinstance(old, str) and not isinstance(old, bool):
                # ya es string ISO: tampoco tocar salvo que decidas normalizar
                skipped += 1
            else:
                payload["created_at"] = now
                payload["updated_at"] = now
                fixed += 1
            to_upsert.append(PointStruct(id=p.id, vector=p.vector, payload=payload))
        if to_upsert:
            c.upsert(collection_name=COLL, points=to_upsert)
        if nxt is None:
            have = False
        else:
            off = nxt
    print(json.dumps({"obsidian_docs_fixed": fixed, "ya_iso_ok": skipped}, indent=2))


if __name__ == "__main__":
    main()
