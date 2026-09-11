#!/usr/bin/env python3
"""Tests DB layer Whatsscanbot (DT-WSIMPORT 2C).

ATENCIÓN: upsert_contact escribe en dispatch.db REAL. Se hace BACKUP
antes y se limpia el registro de prueba al final.
"""

from __future__ import annotations

import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import db as wdb  # noqa: A004,E402

FAIL = 0
TEST_PHONE = "+584149998887"  # teléfono de prueba, se elimina al final


def check(name: str, cond: bool, extra: str = "") -> None:
    global FAIL
    if not cond:
        FAIL += 1
    print(f"[{'OK ' if cond else 'FAIL'}] {name} {extra}")


# ── Backup dispatch.db antes de tocar ──────────────────────────────────
backup = wdb.DISPATCH_DB.with_suffix(".db.bak_2C_test")
shutil.copy2(wdb.DISPATCH_DB, backup)
print(f"backup dispatch.db -> {backup}")


def cleanup() -> None:
    try:
        with sqlite3.connect(wdb.DISPATCH_DB) as c:
            c.execute("DELETE FROM clients WHERE phone=?", (TEST_PHONE,))
        with sqlite3.connect(wdb.DB_PATH) as c:
            c.execute("DELETE FROM whatsapp_imports WHERE source_file_hash LIKE 'test2c%'")
            c.execute("DELETE FROM whatsapp_contacts WHERE phone=?", (TEST_PHONE,))
    except sqlite3.Error:
        pass


try:
    cleanup()

    # Test 1: insert_import + verify
    iid = wdb.insert_import(
        TEST_PHONE, "Test Cliente", "txt",
        "test2c-hash-001", "preview del texto",
    )
    check("insert_import devuelve id > 0", iid > 0, f"id={iid}")
    wdb.finalize_import(iid, 5, "2026-09-01T10:00:00", "2026-09-02T11:00:00")

    # Test 2: get_import_by_hash + dedup
    found = wdb.get_import_by_hash("test2c-hash-001")
    check("get_import_by_hash encuentra", found is not None)
    check("finalize_import actualizó count",
          found and found["message_count"] == 5)
    dup = None
    try:
        wdb.insert_import(TEST_PHONE, "X", "txt", "test2c-hash-001", "")
        check("insert duplicado RECHAZADO", False)
    except ValueError:
        check("insert duplicado RECHAZADO", True)
        dup = "rejected"

    # Test 3: insert_message + dedup msg_hash
    m1 = {"phone": TEST_PHONE, "sender_name": "Test Cliente",
          "message_text": "hola necesito 2 botellones",
          "timestamp": "2026-09-01T10:00:00", "direction": "in",
          "msg_hash": "test2c-msg-1"}
    m2 = dict(m1)  # mismo hash → dedup
    r1 = wdb.insert_message(iid, m1)
    r2 = wdb.insert_message(iid, m2)
    check("insert_message ok", r1 is not None)
    check("mensaje duplicado ignorado (None)", r2 is None)
    hits = wdb.search_messages("botellones")
    check("search_messages LIKE", len(hits) == 1, f"hits={len(hits)}")

    # Test 4: upsert_contact (insert + update) + dispatch.db
    wdb.upsert_contact(TEST_PHONE, "Test Cliente",
                       "2026-09-01T10:00:00", "2026-09-02T11:00:00", 5)
    c1 = wdb.get_contact(TEST_PHONE)
    check("upsert_contact inserta", c1 is not None)
    check("total_messages=5", c1 and c1["total_messages"] == 5)
    wdb.upsert_contact(TEST_PHONE, None, None, "2026-09-03T12:00:00", 3)
    c2 = wdb.get_contact(TEST_PHONE)
    check("upsert acumula msgs (8)", c2 and c2["total_messages"] == 8)
    check("is_client=1 tras UPSERT dispatch", c2 and c2["is_client"] == 1)
    check("client_id seteado", c2 and c2["client_id"] is not None)
    with sqlite3.connect(wdb.DISPATCH_DB) as c:
        row = c.execute(
            "SELECT phone, name, phone_hash FROM clients WHERE phone=?",
            (TEST_PHONE,),
        ).fetchone()
    check("dispatch.db clients tiene teléfono", row is not None, str(row))

    # Test 5: list_imports
    lst = wdb.list_imports()
    check("list_imports incluye el test",
          any(i["id"] == iid for i in lst))

finally:
    cleanup()
    # backup se mantiene como archivo .bak para auditoría (no se sobreescribe prod)
    print(f"cleanup OK. Backup conservado en {backup}")

print()
if FAIL:
    print(f"❌ {FAIL} tests FALLARON")
    sys.exit(1)
print("✅ Todos los tests DB layer OK (2C)")
_ = subprocess  # noqa