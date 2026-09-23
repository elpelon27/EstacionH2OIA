#!/usr/bin/env python3
"""Tests flujo geolocalización manual: /set_gps + Location → dispatch.db.

Offline: fake Updates, dispatch.db temporal por test.
"""
import asyncio
import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "security"))

os.environ["TELEGRAM_CHAT_ID"] = "1663148211"

import audit_logger as al  # noqa: E402
import security_commands as sc  # noqa: E402

PASS, FAIL = 0, 0
LEADER = 1663148211


def check(name, cond):
    global PASS, FAIL
    print(f"  [{'OK' if cond else 'FAIL'}] {name}")
    if cond:
        PASS += 1
    else:
        FAIL += 1


class FakeChat:
    def __init__(self, chat_id):
        self.id = chat_id


class FakeLocation:
    def __init__(self, lat, lng):
        self.latitude = lat
        self.longitude = lng


class FakeMessage:
    def __init__(self, location=None):
        self.location = location


class FakeUpdate:
    def __init__(self, chat_id=LEADER, location=None):
        self.effective_chat = FakeChat(chat_id)
        self.message = FakeMessage(location)
        self.location = location


class FakeContext:
    def __init__(self, args):
        self.args = args
        self.sent = []

    async def send_message(self, chat_id, text):
        self.sent.append((chat_id, text))


def run(cmd, update, args=None):
    ctx = FakeContext(args)
    sc._reply_orig = sc._reply

    async def _capture(update, context, text):
        context.sent.append((update.effective_chat.id, text))
    sc._reply = _capture
    try:
        asyncio.run(cmd(update, ctx))
    finally:
        sc._reply = sc._reply_orig
    return ctx.sent


def make_dispatch_db(path: Path, phone: str, address_text: str = None):
    conn = sqlite3.connect(path)
    conn.execute(
        """CREATE TABLE clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone TEXT NOT NULL, phone_hash TEXT NOT NULL, name TEXT,
            address_text TEXT, lat REAL, lng REAL, client_type TEXT DEFAULT 'retail',
            priority INTEGER DEFAULT 5, active INTEGER DEFAULT 1,
            created_at REAL DEFAULT (strftime('%s','now')),
            updated_at REAL DEFAULT (strftime('%s','now')))"""
    )
    conn.execute(
        "INSERT INTO clients (phone, phone_hash, name, address_text) VALUES (?,?,?,?)",
        (phone, "deadbeef", "Cliente Test", address_text),
    )
    conn.commit()
    conn.close()


def client_row(db):
    conn = sqlite3.connect(db)
    row = conn.execute("SELECT id, lat, lng, address_text FROM clients").fetchone()
    conn.close()
    return row


def main():
    al.DB_PATH = sc.al.DB_PATH = Path("/tmp/test_set_gps_audit.db")
    for p in (al.DB_PATH,):
        if p.exists():
            p.unlink()
    al.init_db()

    test_db = Path("/tmp/test_set_gps_dispatch.db")
    if test_db.exists():
        test_db.unlink()
    phone = "584122560720"
    make_dispatch_db(test_db, phone, address_text="Calle 5, Maracaibo")
    sc.DISPATCH_DB = str(test_db)
    sc.GPS_PENDING.clear()

    print("T1: /set_gps guarda estado")
    sent = run(sc.cmd_set_gps, FakeUpdate(), args=[phone])
    check("responde confirmación", any("mandá tu ubicación" in t for _, t in sent))
    check("estado guardado", sc.GPS_PENDING.get(LEADER) == phone)

    print("T2: location con estado previo guarda en DB y limpia estado")
    lat, lng = 10.681683540344, -71.597465515137
    sent = run(sc.handle_gps_location,
               FakeUpdate(location=FakeLocation(lat, lng)))
    row = client_row(test_db)
    check("responde guardado", any("Ubicación GPS guardada" in t for _, t in sent))
    check("lat guardada", abs(row[1] - lat) < 1e-9)
    check("lng guardada", abs(row[2] - lng) < 1e-9)
    check("address_text preservada", row[3] == "Calle 5, Maracaibo")
    check("estado limpiado", LEADER not in sc.GPS_PENDING)

    print("T3: location sin estado previo responde error")
    sent = run(sc.handle_gps_location,
               FakeUpdate(location=FakeLocation(lat, lng)))
    check("responde usar /set_gps", any("/set_gps" in t for _, t in sent))
    row2 = client_row(test_db)
    check("DB no cambió", abs(row2[1] - lat) < 1e-9 and row2[3] == "Calle 5, Maracaibo")

    print("T4: /set_gps sin argumento responde uso")
    sent = run(sc.cmd_set_gps, FakeUpdate(), args=[])
    check("responde uso", any("Uso: /set_gps" in t for _, t in sent))

    print("T5: chat no autorizado no armar estado")
    run(sc.cmd_set_gps, FakeUpdate(chat_id=999), args=[phone])
    check("estado no armado", 999 not in sc.GPS_PENDING)

    print(f"\n{'✅' if FAIL == 0 else '❌'} {PASS} OK / {FAIL} FAIL")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
