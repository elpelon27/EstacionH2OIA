#!/usr/bin/env python3
"""Tests bot + llm_client Whatsscanbot (DT-WSIMPORT 2F).

Estructura:
  1. Smoke test llm_client con llamada REAL a DeepSeek V4 Flash (OpenRouter).
  2. Test _process_export del pipeline (parser+db+qdrant+detector), sin Telegram.
  3. Test _is_authorized con Update simulados (chat autorizado vs no).
No conecta a Telegram en modo polling (eso es el E2E de 2G).
"""

from __future__ import annotations

import logging
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import llm_client  # noqa: E402
import parser as wsp  # noqa: E402
from bot import _is_authorized, _process_export  # noqa: E402

import db as wdb  # noqa: E402

logging.basicConfig(level=logging.WARNING)
FAIL = 0
TEST_HASHES: set[str] = set()
TEST_PHONES = {"+584141112233"}


def check(name: str, cond: bool, extra: str = "") -> None:
    global FAIL
    if not cond:
        FAIL += 1
    print(f"[{'OK ' if cond else 'FAIL'}] {name} {extra}")


class FakeChat:
    def __init__(self, cid: int) -> None:
        self.id = cid


class FakeUser:
    def __init__(self, un: str) -> None:
        self.username = un


class FakeUpdate:
    def __init__(self, cid: int, un: str = "user") -> None:
        self.effective_chat = FakeChat(cid)
        self.effective_user = FakeUser(un)
        self.message = None
        self.effective_message = None


# ── Test autorización ──────────────────────────────────────────────────
check("auth: chat del Líder autorizado", _is_authorized(FakeUpdate(1663148211)))
check("auth: chat ajeno RECHAZADO", not _is_authorized(FakeUpdate(999999999)))
check("auth: chat sin objeto RECHAZADO", not _is_authorized(FakeUpdate(0)))

# ── Pre-clean: eliminar imports de corridas previas del test ──────────
with sqlite3.connect(wdb.DB_PATH) as c:
    old_rows = c.execute(
        "SELECT id FROM whatsapp_imports "
        "WHERE source_text_preview LIKE '%paste_test%'"
    ).fetchall()
    for (oid,) in old_rows:
        c.execute("DELETE FROM whatsapp_messages WHERE import_id=?", (oid,))
        c.execute("DELETE FROM whatsapp_imports WHERE id=?", (oid,))
with sqlite3.connect(wdb.DISPATCH_DB) as c:
    for ph in TEST_PHONES:
        c.execute("DELETE FROM clients WHERE phone=?", (ph,))

# ── Test pipeline _process_export (sin Telegram) ───────────────────────
CHAT = """[01/09/2026, 10:00] +58 414-1112233: Hola, quiero pedir 2 botellones
[01/09/2026, 10:02] Yo: Claro, confirmado para la tarde
[01/09/2026, 11:00] +58 414-1112233: Ya hice la transferencia de 15 euros
[02/09/2026, 12:00] +58 414-1112233: El pedido llegó perfecto, gracias
"""
res = wsp.parse_paste(CHAT)
import hashlib  # noqa: E402

h = hashlib.sha256(CHAT.encode()).hexdigest()
TEST_HASHES.add(h)
report = _process_export("paste", "paste_test", CHAT, res)
print("--- reporte generado ---")
print(report)
print("-----------------------")
check("pipeline: reporte exitoso", report.startswith("✅ Import #"))
check("pipeline: teléfono detectado", "+58414" in report)
check("pipeline: 4 mensajes", "4 mensajes" in report)
check("pipeline: pedidos detectados", "pedidos=2" in report)
check("pipeline: pago detectado", "pagos=1" in report)
check("pipeline: resumen LLM presente", "🧠" in report)

# dedup: reprocesar mismo texto
report2 = _process_export("paste", "paste_test", CHAT, res)
check("pipeline: dedup por hash", "duplicado" in report2.lower())

# tier LLM: verificar que el resumen usó un tier de la cadena
iid = wdb.get_import_by_hash(h)
check("pipeline: import en DB", iid is not None)
if iid:
    import json  # noqa: E402
    with wdb._conn() as c:  # noqa: SLF001
        row = c.execute(
            "SELECT summary_json FROM whatsapp_imports WHERE id=?",
            (iid["id"],),
        ).fetchone()
    sj = json.loads(row[0]) if row and row[0] else {}
    check("pipeline: tier guardado en DB",
          sj.get("tier") in [m for m, _ in llm_client.DEFAULT_CHAIN],
          str(sj.get("tier")))

# ── Smoke test llm_client REAL (DeepSeek V4 Flash primario) ─────────────
try:
    out = llm_client.summarize_chat(
        "Test Cliente", "+584141112233",
        [{"timestamp": "2026-09-01T10:00:00", "sender_name": "Luis",
          "message_text": "Quiero 2 botellones y pago por PagoMovil"}],
    )
    check("llm: resumen OK", bool(out["summary"]))
    check("llm: tier primario DeepSeek",
          out["tier"] == "deepseek/deepseek-v4-flash", f"tier={out['tier']}")
except Exception as e:  # noqa: BLE001
    check("llm: resumen OK", False, str(e))

# ── Cleanup ────────────────────────────────────────────────────────────
import sqlite3  # noqa: E402

with sqlite3.connect(wdb.DB_PATH) as c:
    for hh in TEST_HASHES:
        row = c.execute("SELECT id FROM whatsapp_imports WHERE source_file_hash=?",
                        (hh,)).fetchone()
        if row:
            c.execute("DELETE FROM whatsapp_messages WHERE import_id=?", (row[0],))
            c.execute("DELETE FROM whatsapp_imports WHERE id=?", (row[0],))
    for ph in TEST_PHONES:
        c.execute("DELETE FROM whatsapp_contacts WHERE phone=?", (ph,))
with sqlite3.connect(wdb.DISPATCH_DB) as c:
    for ph in TEST_PHONES:
        c.execute("DELETE FROM clients WHERE phone=?", (ph,))
check("cleanup OK", True)

print()
if FAIL:
    print(f"❌ {FAIL} tests FALLARON")
    sys.exit(1)
print("✅ Todos los tests bot + llm_client OK (2F)")
