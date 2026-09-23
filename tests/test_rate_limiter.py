#!/usr/bin/env python3
"""Tests FASE 1: rate limiting + blacklist + código país (comentados por el Líder)."""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "security"))
import rate_limiter as rl  # noqa: E402

PASS, FAIL = 0, 0


def check(name, cond):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [OK] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name}")


def main():
    # DB de test aislada (no la real)
    rl.DB_PATH = Path("/tmp/security_test.db")
    if rl.DB_PATH.exists():
        rl.DB_PATH.unlink()
    rl.init_db()

    print("1) Números venezolanos vs internacionales")
    check("+58 412 1234567 es VE", rl.es_numero_venezolano("+584121234567"))
    check("584121234567 es VE", rl.es_numero_venezolano("584121234567"))
    check("+584121234567 normaliza a 12 dígitos",
          rl.es_numero_venezolano("+58 412-123-4567"))
    check("+1 555 1234567 NO es VE", not rl.es_numero_venezolano("+15551234567"))
    check("+57 300 1234567 (Colombia) NO es VE",
          not rl.es_numero_venezolano("+573001234567"))
    check("+44 (UK) NO es VE", not rl.es_numero_venezolano("+447911123456"))

    print("2) Internacional se bloquea + blacklist inmediata")
    res = rl.check_incoming("+15551234567")
    check("internacional rechazado", res["action"] == "internacional")
    check("internacional en blacklist", rl.is_blacklisted("15551234567"))
    check("internacional blacklist permanente",
          rl._conn().execute("SELECT is_permanent FROM blacklist_phone WHERE phone='15551234567'").fetchone()[0] == 1)

    print("3) +58 válido pasa")
    res = rl.check_incoming("+584121234567")
    check("venezolano permitido", res["allow"] is True)
    check("no está en blacklist", not rl.is_blacklisted("584121234567"))

    print("4) 3 mensajes en 60s dispara advertencia (4to)")
    now = time.time()
    rl.check_incoming("+584241234567", ts=now)
    rl.check_incoming("+584241234567", ts=now + 5)
    rl.check_incoming("+584241234567", ts=now + 10)
    res4 = rl.check_incoming("+584241234567", ts=now + 15)
    check("4to mensaje en 60s → advertencia+silencio",
          res4["action"] in ("silencio_1h", "advertencia") or not res4["allow"])
    check("hay mensaje de advertencia al cliente",
          isinstance(res4.get("message"), str))
    check("número ahora bloqueado 1h", rl.is_blacklisted("584241234567"))

    print("5) 1ra ofensa = 1h silencio (temporal)")
    rl.add_to_blacklist("+584141234567", "test", permanent=False)
    row = rl._conn().execute(
        "SELECT is_permanent, expires_at - blocked_at d FROM blacklist_phone WHERE phone='584141234567'").fetchone()
    check("temporal (no permanente)", row[0] == 0)
    check("expira en ~1h", 3500 < row[1] <= 3700)

    print("6) 2da ofensa <24h = permanente")
    rl.check_incoming("+584161234567", ts=now)
    # simular 1ra ofensa
    r1 = rl.record_offense("584161234567", "spam_rapido_3msg_60s")
    check("1ra ofensa → silencio 1h", r1["action"] == "silencio_1h")
    # 2da ofensa (dentro de 24h)
    r2 = rl.record_offense("584161234567", "spam_rapido_3msg_60s")
    check("2da ofensa → ban permanente", r2["action"] == "ban_permanente")
    check("permanente en DB",
          rl._conn().execute("SELECT is_permanent FROM blacklist_phone WHERE phone='584161234567'").fetchone()[0] == 1)

    print("7) remove_from_blacklist")
    check("remove funciona", rl.remove_from_blacklist("584161234567"))
    check("ya no está blacklisted", not rl.is_blacklisted("584161234567"))

    print(f"\nRESULTADO: {PASS} OK / {FAIL} FAIL")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
