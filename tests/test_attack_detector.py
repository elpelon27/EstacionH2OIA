#!/usr/bin/env python3
"""Tests FASE 3: ataques coordinados + lockdown."""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "security"))
import attack_detector as ad  # noqa: E402
import rate_limiter as rl  # noqa: E402

PASS, FAIL = 0, 0


def check(name, cond):
    global PASS, FAIL
    print(f"  [{'OK' if cond else 'FAIL'}] {name}")
    if cond:
        PASS += 1
    else:
        FAIL += 1


def main():
    ad.DB_PATH = Path("/tmp/security_test_attack.db")
    rl.DB_PATH = ad.DB_PATH  # comparte para blacklist del spam
    for p in (ad.DB_PATH,):
        if p.exists():
            p.unlink()
    ad.init_db()

    print("1) Mensajes normales pasan")
    r = ad.check_global("+584121234567", "hola", ts=time.time())
    check("permitido", r["allow"] is True)
    check("acción ok (bajo todos los límites)", r["action"] == "ok")

    print("2) 29 msg/min dispara alerta operador")
    # registrar 29 mensajes (28 + el del paso 1)
    base = time.time()
    for i in range(28):
        ad.record_global_message(f"58412{i:08d}", f"msg {i}", ts=base)
    # limpiar: recrear métricas — check_global con 29 en ventana
    r = ad.check_global("584121234568", "x", ts=base + 1)
    check("29/min → alerta_min o superior",
          r["action"] in ("alerta_min", "alerta_hora", "observacion_nuevos", "lockdown"))
    check("notifica operador", r["notify_operator"] is not None)

    print("3) 50 números nuevos en 10min → observación")
    # ya hay ~29 nuevos; sumar hasta 50
    for i in range(30, 52):
        ad.record_global_message(f"58424{i:08d}", "hola", ts=base)
    check("numeros_nuevos_en_10min >= 50", ad.numeros_nuevos_en_10min() >= 50)

    print("4) 700 msg/día → LOCKDOWN (solo conocidos)")
    # marcar un número como conocido
    ad.mark_registered("584161111111")
    # inundar hasta 700
    for i in range(0, 700):
        ad.record_global_message("58414999999", "spam", ts=base)
    r = ad.check_global("58414999999", "spam", ts=base + 2)
    check("lockdown activo tras 700/día", ad.is_lockdown() is True)
    check("número desconocido en lockdown → rechazado",
          ad.check_global("58414999998", "x", ts=base + 3)["allow"] is False)
    r2 = ad.check_global("584161111111", "hola", ts=base + 4)
    check("número CONOCIDO en lockdown → pasa", r2["allow"] is True)

    print("5) Salir de lockdown solo con operador")
    ad.release_lockdown("test_operador")
    check("lockdown liberado", ad.is_lockdown() is False)
    r3 = ad.check_global("58414999998", "x", ts=base + 5)
    check("desconocido pasa tras liberar", r3["allow"] is True)

    print("6) Spam programado: mensaje idéntico de >=5 números → bloqueo automático")
    ad2 = ad  # DB nueva para spam limpio
    if ad2.DB_PATH.exists():
        ad2.DB_PATH.unlink()
    ad2.init_db()
    rl.DB_PATH = ad2.DB_PATH
    rl._initialized = False  # forzar re-init sobre la DB nueva
    ad2._state_set("lockdown", False)
    for ph in ["58411111111", "58412222222", "58413333333", "58414444444", "58415555555"]:
        ad2.record_global_message(ph, "COMPRE AHORA http://spam.xyz", ts=base)
    r4 = ad2.check_global("58416666666", "COMPRE AHORA http://spam.xyz", ts=base + 1)
    check("spam detectado → bloqueo", r4["action"] == "spam_bloqueado")
    from rate_limiter import is_blacklisted
    rl.init_db()
    check("números spam en blacklist", rl.is_blacklisted("58411111111"))
    check("5 números spam bloqueados", all(
        rl.is_blacklisted(n) for n in
        ["58411111111", "58412222222", "58413333333", "58414444444", "58415555555"]))

    print("7) Ataques quedan registrados")
    atks = ad.recent_attacks(50)
    tipos = {a["attack_type"] for a in atks}
    check("hay eventos de ataque", len(atks) > 0)
    check("incluye spam_programado", "spam_programado" in tipos)

    print(f"\nRESULTADO: {PASS} OK / {FAIL} FAIL")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
