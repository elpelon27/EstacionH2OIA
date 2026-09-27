#!/usr/bin/env python3
"""Tests del sistema de clasificación de clientes (plan de peso).

FASE 4 de la directiva:
1. /set_peso restaurante/clinica/escuela → is_automatic=1.
2. /set_peso gimnasio/hotel/etc → is_automatic=0.
3. auto_router: get_daily_route incluye TODOS los is_automatic=1;
   lunes duplica cantidad.
4. Comandos Telegram: auth, validaciones (async).

Usa clientes de TEST reales en dispatch.db (prefijo TEST_) y los
elimina al final. No toca bridge.py ni geofence.py.
"""
import asyncio
import os
import sqlite3
import sys
import types
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
os.environ.setdefault("BRIDGE_ALLOW_INSECURE_SALT", "1")

DB = str(REPO / "data" / "dispatch.db")
sys.path.insert(0, str(REPO / "skills"))

import client_commands as cc  # noqa: E402

from scripts.routing import auto_router  # noqa: E402

passed: list[str] = []
failed: list[str] = []


def check(name: str, cond, detail: str = "") -> None:  # noqa: ANN001
    ok = bool(cond)
    (passed if ok else failed).append(name)
    mark = "✅" if ok else "❌"
    print(f"  {mark} {name} {detail}")


def db() -> sqlite3.Connection:
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c


def seed_test_clients() -> None:
    """Crea 3 clientes de test (se limpian al final)."""
    with db() as c:
        for ph, name in [
            ("+584120009001", "TEST_Restaurante"),
            ("+584120009002", "TEST_Gimnasio"),
            ("+584120009003", "TEST_Clinica"),
        ]:
            c.execute(
                "INSERT OR IGNORE INTO clients "
                "(phone, phone_hash, name, client_type, is_priority, "
                "is_automatic, active, avg_bottles_per_visit, created_at, "
                "updated_at) VALUES (?,?,?, 'retail', 0, 0, 1, 4, "
                "strftime('%s','now'), strftime('%s','now'))",
                (ph, "test_hash_" + ph[-4:], name),
            )


def cleanup() -> None:
    auto_router.init_auto_orders_table()  # idempotente (primera corrida)
    with db() as c:
        c.execute("DELETE FROM clients WHERE name LIKE 'TEST_%'")
        c.execute("DELETE FROM orders_auto WHERE client_id IN "
                  "(SELECT id FROM clients WHERE name LIKE 'TEST_%')")
        c.execute(
            "DELETE FROM orders_auto WHERE client_id NOT IN "
            "(SELECT id FROM clients)"
        )
    # audit log de test no se limpia (trazabilidad), solo clientes.


class FakeChat:
    def __init__(self, cid: int) -> None:
        self.id = cid


class FakeMessage:
    def __init__(self) -> None:
        self.sent: list[str] = []

    async def reply_text(self, text: str) -> None:
        self.sent.append(text)


def fake_update(chat_id: int = 1663148211):
    msg = FakeMessage()
    upd = types.SimpleNamespace(
        effective_chat=FakeChat(chat_id), message=msg,
    )
    return upd, msg


def fake_ctx(args: list[str]):
    return types.SimpleNamespace(args=args)


async def run_set_peso(phone: str, tipo: str, notas: list[str] | None = None):
    upd, msg = fake_update()
    await cc.cmd_set_peso(upd, fake_ctx([phone, tipo] + (notas or [])))
    return msg.sent[-1] if msg.sent else ""


async def run_cmd(fn, *args_list: str) -> str:  # noqa: ANN001
    upd, msg = fake_update()
    await fn(upd, fake_ctx(list(args_list)))
    return msg.sent[-1] if msg.sent else ""


def main() -> int:
    print("== SETUP: seed clientes TEST ==")
    cleanup()
    seed_test_clients()
    with db() as c:
        check("3 clientes TEST creados",
              c.execute("SELECT COUNT(*) FROM clients WHERE name LIKE 'TEST_%'").fetchone()[0] == 3)

    print("== TEST 1: /set_peso restaurante → NIVEL 1 automático ==")
    r = asyncio.run(run_set_peso("+584120009001", "restaurante", ["especialidad: parrilla"]))
    check("responde NIVEL 1", "NIVEL 1" in r and "Automático" in r, r)
    with db() as c:
        row = c.execute("SELECT is_priority, is_automatic, client_type, priority_notes "
                        "FROM clients WHERE phone='+584120009001'").fetchone()
        check("is_priority=1", row["is_priority"] == 1)
        check("is_automatic=1", row["is_automatic"] == 1)
        check("client_type=restaurante", row["client_type"] == "restaurante")
        check("notas guardadas", row["priority_notes"] == "especialidad: parrilla")

    print("== TEST 2: /set_peso gimnasio → NIVEL 2 on-demand ==")
    r = asyncio.run(run_set_peso("+584120009002", "gimnasio"))
    check("responde NIVEL 2", "NIVEL 2" in r and "On-Demand" in r, r)
    with db() as c:
        row = c.execute("SELECT is_priority, is_automatic FROM clients "
                        "WHERE phone='+584120009002'").fetchone()
        check("is_priority=1", row["is_priority"] == 1)
        check("is_automatic=0", row["is_automatic"] == 0)

    print("== TEST 2b: clinica → NIVEL 1 ==")
    asyncio.run(run_set_peso("+584120009003", "clinica"))
    with db() as c:
        row = c.execute("SELECT is_automatic FROM clients "
                        "WHERE phone='+584120009003'").fetchone()
        check("clinica is_automatic=1", row["is_automatic"] == 1)

    print("== TEST 3: auto_router.get_daily_route ==")
    lunes = date(2026, 9, 28)     # lunes
    martes = date(2026, 9, 29)    # martes
    r_lunes = auto_router.get_daily_route(lunes)
    r_martes = auto_router.get_daily_route(martes)
    ids_lunes = {e["client_id"] for e in r_lunes}
    with db() as c:
        autos = {r[0] for r in c.execute(
            "SELECT id FROM clients WHERE is_automatic=1").fetchall()}
    check("incluye TODOS los is_automatic=1", autos == ids_lunes,
          f"autos={autos} ruta={ids_lunes}")
    check("lunes duplica (4→8)",
          all(e["qty_botellones"] == 8 for e in r_lunes),
          str([(e['name'], e['qty_botellones']) for e in r_lunes]))
    check("martes normal (4)",
          all(e["qty_botellones"] == 4 for e in r_martes))

    print("== TEST 3b: create_daily_orders idempotente ==")
    s1 = auto_router.create_daily_orders(lunes)
    s2 = auto_router.create_daily_orders(lunes)
    check("crea pedidos", s1["creados"] == len(autos), str(s1))
    no_dup = s2["creados"] == 0 and s2["ignorados"] == len(autos)
    check("segunda corrida no duplica", no_dup, str(s2))
    with db() as c:
        rows = c.execute("SELECT estado, is_monday_double FROM orders_auto "
                         "WHERE delivery_date='2026-09-28'").fetchall()
        check("estado pending_dispatch", all(r["estado"] == "pending_dispatch" for r in rows))
        check("is_monday_double=1", all(r["is_monday_double"] == 1 for r in rows))

    print("== TEST 4: comandos Telegram (auth, validaciones) ==")
    # auth: chat_id equivocado → sin respuesta
    upd_bad, msg_bad = fake_update(chat_id=999999)
    asyncio.run(cc.cmd_set_peso(upd_bad, fake_ctx(["+584120009001", "hotel"])))
    check("chat no autorizado ignorado", msg_bad.sent == [])
    # tipo inválido
    r = asyncio.run(run_set_peso("+584120009001", "hospital"))
    check("tipo inválido rechazado", "inválido" in r.lower(), r)
    # cliente inexistente
    r = asyncio.run(run_set_peso("+589990000000", "hotel"))
    check("cliente inexistente → error", "no existe" in r, r)
    # /unset_peso
    r = asyncio.run(run_cmd(cc.cmd_unset_peso, "+584120009001"))
    check("unset_peso responde", "quitado" in r, r)
    with db() as c:
        row = c.execute("SELECT is_priority, is_automatic, client_type "
                        "FROM clients WHERE phone='+584120009001'").fetchone()
        check("unset pone 0/0", row["is_priority"] == 0 and row["is_automatic"] == 0)
        check("unset NO cambia client_type", row["client_type"] == "restaurante")
    # /list_peso
    r = asyncio.run(run_cmd(cc.cmd_list_peso))
    check("list_peso muestra NIVEL 1 y 2", "NIVEL 1" in r and "NIVEL 2" in r, r[:80])
    # /list_tipo
    r = asyncio.run(run_cmd(cc.cmd_list_tipo, "clinica"))
    check("list_tipo clinica lista TEST_Clinica", "TEST_Clinica" in r, r)
    # /client_info
    r = asyncio.run(run_cmd(cc.cmd_client_info, "+584120009002"))
    check("client_info ficha completa", "gimnasio" in r and "NIVEL 2" in r, r[:80])

    print("== CLEANUP ==")
    cleanup()
    with db() as c:
        check("clientes TEST eliminados",
              c.execute("SELECT COUNT(*) FROM clients WHERE name LIKE 'TEST_%'").fetchone()[0] == 0)
        n = c.execute(
            "SELECT COUNT(*) FROM orders_auto WHERE delivery_date='2026-09-28'"
        ).fetchone()[0]
        check("orders_auto de test eliminadas", n == 0)

    print(f"\nRESULTADO: {len(passed)} OK / {len(failed)} FALLOS")
    if failed:
        print("FALLOS:", failed)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
