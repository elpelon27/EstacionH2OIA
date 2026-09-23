#!/usr/bin/env python3
"""Tests FASE 6: teléfonos hasheados en DB (aditivo, sin tocar columnas en claro)."""
import sqlite3
import sys
from pathlib import Path

REPO = Path("/mnt/ssd_trabajo/hermes-agent")
sys.path.insert(0, str(REPO / "scripts" / "security"))
import data_hardening as dh  # noqa: E402

PASS, FAIL = 0, 0


def check(name, cond):
    global PASS, FAIL
    print(f"  [{'OK' if cond else 'FAIL'}] {name}")
    if cond:
        PASS += 1
    else:
        FAIL += 1


def main():
    # DB de test aislada
    import shutil
    test_dir = Path("/tmp/fase6_test")
    if test_dir.exists():
        shutil.rmtree(test_dir)
    test_dir.mkdir()
    dh.CONV_DB = test_dir / "conversations.db"
    dh.WA_DB = test_dir / "whatsapp_bot.db"
    # crear schema copiado del real
    src = sqlite3.connect(f"file:{REPO/'data/conversations.db'}?mode=ro", uri=True)
    schema = [r[0] for r in src.execute(
        "SELECT sql FROM sqlite_master WHERE sql IS NOT NULL AND name IN "
        "('fs_pedidos','fs_pagos')")]
    src.close()
    dst = sqlite3.connect(dh.CONV_DB)
    for s in schema:
        dst.execute(s)
    dst.execute("INSERT INTO fs_pedidos(pedido_id, cliente_telefono, monto_total_eur, "
                "tasa_eur_ves, creado_at, actualizado_at) VALUES(1,'+58 412-1234567',1,1,'x','y')")
    dst.commit(); dst.close()

    print("1) Hash con el estándar del ecosistema (core.crypto, LOG_SALT)")
    salt = dh._ensure_salt()
    h = dh.phone_hash("+584121234567")
    check("hash es 32 hex chars (formato clients)", len(h) == 32)
    check("hash determinista", dh.phone_hash("+58 412-1234567") == h)
    # igual que clients.phone_hash para el mismo E.164
    from core.crypto import hash_phone
    check("consistente con core.crypto.hash_phone('+584121234567')",
          hash_phone("+584121234567") == h)

    print("2) Backfill hashea teléfonos")
    r = dh.harden_conversations()
    check("1 pedido hasheado", r["fs_pedidos"] == 1)
    v = dh.verify_hashed()
    check("verify: hashed=1, mismatch=0", v["fs_pedidos_hashed"] == 1 and v["fs_pedidos_mismatch"] == 0)

    print("3) Columnas en claro NO tocadas (estrategia aditiva)")
    c = sqlite3.connect(dh.CONV_DB)
    ph = c.execute("SELECT cliente_telefono FROM fs_pedidos WHERE pedido_id=1").fetchone()[0]
    c.close()
    check("teléfono en claro sigue (purga = PENDIENTE LÍDER)", ph == "+58 412-1234567")

    print("4) Runtime puede hashear para comparar")
    c = sqlite3.connect(dh.CONV_DB)
    h_db = c.execute("SELECT cliente_telefono_hash FROM fs_pedidos WHERE pedido_id=1").fetchone()[0]
    c.close()
    check("runtime re-hashea y coincide", dh.phone_hash(ph) == h_db)

    print("5) DB ausente / tabla vacía no rompe")
    dh.WA_DB = test_dir / "no_existe.db"
    r = dh.harden_whatsapp()
    check("whatsapp ausente → nota, no excepción", "nota" in r)

    shutil.rmtree(test_dir)
    print(f"\nRESULTADO: {PASS} OK / {FAIL} FAIL")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
