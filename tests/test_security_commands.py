#!/usr/bin/env python3
"""Tests FASE 4: comandos de seguridad del operador (offline, fake Updates)."""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "security"))

import os
os.environ["TELEGRAM_CHAT_ID"] = "1663148211"

import security_commands as sc  # noqa: E402
import rate_limiter as rl  # noqa: E402
import attack_detector as ad  # noqa: E402
import audit_logger as al  # noqa: E402

PASS, FAIL = 0, 0


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


class FakeUpdate:
    def __init__(self, chat_id=1663148211, args=None):
        self.effective_chat = FakeChat(chat_id)
        self.args = args or []


class FakeContext:
    def __init__(self, args, chat_id=1663148211):
        self.args = args
        self.bot = type("B", (), {})()
        self._chat_id = chat_id
        self.sent = []

    def send_message(self, chat_id, text):
        # simula lo que hace _reply
        self.sent.append((chat_id, text))


def run(cmd, args, chat_id=1663148211):
    u = FakeUpdate(chat_id)
    ctx = FakeContext(args, chat_id)
    sc._reply_orig = sc._reply
    # patch _reply to capture
    sc._reply = lambda update, context, text: context.sent.append(
        (update.effective_chat.id, text))
    try:
        cmd(u, ctx)
    finally:
        sc._reply = sc._reply_orig
    return ctx.sent


def main():
    # DB de test
    rl.DB_PATH = ad.DB_PATH = al.DB_PATH = Path("/tmp/security_test_cmds.db")
    sc.rl.DB_PATH = sc.ad.DB_PATH = sc.al.DB_PATH = sc.gf.DB_PATH = rl.DB_PATH
    for mod in (rl, ad, al, sc.rl, sc.ad, sc.al):
        mod.DB_PATH = rl.DB_PATH
    rl._initialized = False
    for p in [rl.DB_PATH]:
        if p.exists():
            p.unlink()
    rl.init_db(); ad.init_db(); al.init_db(); sc.gf.init_db()

    print("1) Solo el chat_id del Líder está autorizado")
    sent = run(sc.cmd_stats, [], chat_id=1663148211)
    check("Líder autorizado (recibe respuesta)", len(sent) == 1 and "ESTAD" in sent[0][1])
    sent = run(sc.cmd_stats, [], chat_id=999999999)
    check("intruso SIN respuesta", len(sent) == 0)
    n = len(al.get_events(event_type="intento_fallo_acceso"))
    check("intento fallido LOGUEADO", n >= 1)

    print("2) /blacklist_add y /blacklist_remove")
    sent = run(sc.cmd_blacklist_add, ["584121234567", "cliente", "problemático", "permanent"])
    check("add responde confirmación", len(sent) == 1 and "permanente" in sent[0][1])
    check("quedó en blacklist", rl.is_blacklisted("584121234567"))
    sent = run(sc.cmd_blacklist_remove, ["584121234567"])
    check("remove responde", len(sent) == 1 and "limpiada" in sent[0][1])
    check("ya no está", not rl.is_blacklisted("584121234567"))

    print("3) /block (1h) y /unblock")
    run(sc.cmd_block, ["584241234567"])
    check("bloqueado 1h", rl.is_blacklisted("584241234567"))
    row = rl._conn().execute("SELECT is_permanent FROM blacklist_phone WHERE phone='584241234567'").fetchone()
    check("es temporal (no permanente)", row[0] == 0)
    run(sc.cmd_unblock, ["584241234567"])
    check("desbloqueado", not rl.is_blacklisted("584241234567"))

    print("4) /observe")
    sent = run(sc.cmd_observe, ["584121234567"])
    check("observación confirmada", "observación" in sent[0][1].lower())
    check("evento cliente_observacion en audit", len(
        al.get_events(event_type="cliente_observacion", phone="584121234567")) >= 1)

    print("5) /credit_client")
    run(sc.cmd_credit_client, ["584141234567"])
    check("marcado como conocido/registrado", ad.is_known_number("584141234567"))

    print("6) /cliente_info")
    sent = run(sc.cmd_cliente_info, ["584121234567"])
    txt = sent[0][1]
    check("info incluye blacklist", "Blacklist" in txt or "blacklist" in txt)
    check("info incluye ofensas", "Ofensas" in txt)
    check("info incluye eventos", "eventos" in txt)

    print("7) /ataque_detectado y /lockdown_*")
    ad.log_attack("test_ataque", {"valor": 99})
    sent = run(sc.cmd_ataque_detectado, [])
    check("ataques listados", "test_ataque" in sent[0][1])
    sent = run(sc.cmd_lockdown_status, [])
    check("status responde estado", "Lockdown" in sent[0][1])
    ad.set_lockdown("test")
    check("lockdown activo", ad.is_lockdown())
    sent = run(sc.cmd_lockdown_release, [])
    check("release confirma", "liberado" in sent[0][1].lower())
    check("lockdown inactivo", not ad.is_lockdown())

    print("8) /stats del día")
    sent = run(sc.cmd_stats, [])
    check("stats incluye volúmenes", "/min" in sent[0][1])

    print("9) Uso inválido responde ayuda (no exception)")
    sent = run(sc.cmd_blacklist_add, [])
    check("falta phone → uso", len(sent) == 1 and "Uso" in sent[0][1])

    print(f"\nRESULTADO: {PASS} OK / {FAIL} FAIL")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
