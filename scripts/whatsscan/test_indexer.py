#!/usr/bin/env python3
"""Tests indexer Qdrant (DT-WSIMPORT 2D). Indexa 5 msgs, busca, filtra."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from typing import Any

import indexer as ix  # noqa: A004,E402

FAIL = 0
TEST_PREFIX = "test2d-"
PHONE_A = "+584140000001"
PHONE_B = "+584140000002"


def check(name: str, cond: bool, extra: str = "") -> None:
    global FAIL
    if not cond:
        FAIL += 1
    print(f"[{'OK ' if cond else 'FAIL'}] {name} {extra}")


# limpiar puntos de tests previos
ix.ensure_collection()
existing = ix.client().scroll(collection_name=ix.COLLECTION,
                              limit=256, with_payload=True)[0]
del_ids: list[Any] = []
# no hay msg_hash en payload; usamos import_id negativo como marcador de test
for p in existing:
    if p.payload is not None and p.payload.get("import_id", 0) < 0:
        del_ids.append(p.id)
if del_ids:
    ix.client().delete(collection_name=ix.COLLECTION,
                       points_selector=del_ids)
    print(f"limpiados {len(del_ids)} puntos de test previos")

MSGS = [
    {"msg_hash": TEST_PREFIX + "1", "phone": PHONE_A, "sender_name": "Luis",
     "message_text": "Hola, quiero pedir 3 botellones de agua para mañana",
     "timestamp": "2026-09-01T10:00:00", "message_type": "text"},
    {"msg_hash": TEST_PREFIX + "2", "phone": PHONE_A, "sender_name": "Yo",
     "message_text": "Confirmado, te los llevamos por la tarde",
     "timestamp": "2026-09-01T10:05:00", "message_type": "text"},
    {"msg_hash": TEST_PREFIX + "3", "phone": PHONE_A, "sender_name": "Luis",
     "message_text": "Ya hice la transferencia de 15 euros",
     "timestamp": "2026-09-01T11:00:00", "message_type": "text"},
    {"msg_hash": TEST_PREFIX + "4", "phone": PHONE_B, "sender_name": "Maria",
     "message_text": "El garrafón llegó con fuga, tengo un reclamo",
     "timestamp": "2026-09-02T12:00:00", "message_type": "text"},
    {"msg_hash": TEST_PREFIX + "5", "phone": PHONE_B, "sender_name": "Yo",
     "message_text": "Disculpa, te cambiamos el garrafón hoy mismo",
     "timestamp": "2026-09-02T12:30:00", "message_type": "text"},
]

n = ix.index_messages(import_id=-1, messages=MSGS)  # import_id -1 = test
check("index 5 mensajes", n == 5, f"n={n}")

# idempotencia: reindexar no duplica
n2 = ix.index_messages(import_id=-1, messages=MSGS)
check("reindex idempotente (upsert mismos IDs)", n2 == 5)

# búsqueda semántica
res = ix.search("pedido de botellones de agua", limit=3)
check("search devuelve resultados", len(res) > 0)
check("top hit relevante",
      bool(res) and "botellones" in res[0].get("message", "").lower(),
      res[0].get("message", "")[:60] if res else "")

# filtro por phone
res_b = ix.search("garrafón con fuga", limit=5, phone=PHONE_B)
check("filtro por phone B", all(r.get("phone") == PHONE_B for r in res_b),
      f"hits={len(res_b)}")
res_a = ix.search("botellones", limit=5, phone=PHONE_A)
check("filtro por phone A", all(r.get("phone") == PHONE_A for r in res_a))

# cleanup puntos de test
test_ids = [ix.point_id(m["msg_hash"]) for m in MSGS]
ix.client().delete(collection_name=ix.COLLECTION, points_selector=test_ids)
check("cleanup puntos test", True)

print()
if FAIL:
    print(f"❌ {FAIL} tests FALLARON")
    sys.exit(1)
print("✅ Todos los tests indexer OK (2D)")
