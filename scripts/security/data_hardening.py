#!/usr/bin/env python3
"""Endurecimiento de datos (FASE 6) — hashing aditivo de teléfonos.

Reglas del Líder:
- phone_hash via core.crypto.hash_phone (LOG_SALT estandar del ecosistema).
- Hash de: fs_pedidos.cliente_telefono, fs_pagos.cliente_telefono (conversations.db),
  whatsapp_contacts.phone (whatsapp_bot.db).
- Estrategia ADITIVA: se agregan columnas *_hash y se hace backfill; las columnas
  en claro NO se tocan (el bridge en producción escribe ahí — zona sellada).
  La purga del claro queda PENDIENTE LÍDER (ventana de mantenimiento + cambio en bridge).
- Cifrado de conversations.db: PENDIENTE LÍDER (DB en uso por valentina-bridge;
  cifrar en caliente rompería el servicio).
"""
import hashlib
import os
import sqlite3
import sys
from pathlib import Path

REPO = Path("/mnt/ssd_trabajo/hermes-agent")
CONV_DB = REPO / "data" / "conversations.db"
WA_DB = REPO / "data" / "whatsapp_bot.db"


def _add_column(c: sqlite3.Connection, table: str, col: str):
    cols = [r[1] for r in c.execute(f"PRAGMA table_info({table})")]
    if col not in cols:
        c.execute(f"ALTER TABLE {table} ADD COLUMN {col} TEXT")


def harden_conversations(dry_run: bool = False) -> dict:
    """fs_pedidos + fs_pagos: agrega *_hash y backfill."""
    _ensure_salt()
    c = sqlite3.connect(CONV_DB, timeout=30)
    stats = {"fs_pedidos": 0, "fs_pagos": 0}
    try:
        with c:
            _add_column(c, "fs_pedidos", "cliente_telefono_hash")
            _add_column(c, "fs_pagos", "cliente_telefono_hash")
            if not dry_run:
                rows = c.execute(
                    "SELECT id, cliente_telefono FROM fs_pedidos "
                    "WHERE cliente_telefono IS NOT NULL AND cliente_telefono != ''").fetchall()
                for rid, ph in rows:
                    c.execute("UPDATE fs_pedidos SET cliente_telefono_hash=? WHERE id=?",
                              (phone_hash(ph), rid))
                    stats["fs_pedidos"] += 1
                rows = c.execute(
                    "SELECT id, cliente_telefono FROM fs_pagos "
                    "WHERE cliente_telefono IS NOT NULL AND cliente_telefono != ''").fetchall()
                for rid, ph in rows:
                    c.execute("UPDATE fs_pagos SET cliente_telefono_hash=? WHERE id=?",
                              (phone_hash(ph), rid))
                    stats["fs_pagos"] += 1
            c.commit()
    finally:
        c.close()
    return stats


def harden_whatsapp(dry_run: bool = False) -> dict:
    """whatsapp_contacts: agrega phone_hash y backfill."""
    _ensure_salt()
    if not WA_DB.exists():
        return {"whatsapp_contacts": 0, "nota": "DB no existe"}
    c = sqlite3.connect(WA_DB, timeout=30)
    stats = {"whatsapp_contacts": 0}
    try:
        with c:
            _add_column(c, "whatsapp_contacts", "phone_hash")
            if not dry_run:
                rows = c.execute(
                    "SELECT rowid, phone FROM whatsapp_contacts "
                    "WHERE phone IS NOT NULL AND phone != ''").fetchall()
                for rid, ph in rows:
                    c.execute("UPDATE whatsapp_contacts SET phone_hash=? WHERE rowid=?",
                              (phone_hash(ph), rid))
                    stats["whatsapp_contacts"] += 1
            c.commit()
    finally:
        c.close()
    return stats


def verify_hashed() -> dict:
    """Verifica que los teléfonos tienen hash correcto (test)."""
    _ensure_salt()
    out = {}
    c = sqlite3.connect(f"file:{CONV_DB}?mode=ro", uri=True)
    total = c.execute("SELECT count(*) FROM fs_pedidos WHERE cliente_telefono_hash IS NOT NULL").fetchone()[0]
    mismatch = 0
    for rid, ph, h in c.execute(
            "SELECT id, cliente_telefono, cliente_telefono_hash FROM fs_pedidos "
            "WHERE cliente_telefono IS NOT NULL AND cliente_telefono != ''"):
        if phone_hash(ph) != h:
            mismatch += 1
    out["fs_pedidos_hashed"] = total
    out["fs_pedidos_mismatch"] = mismatch
    c.close()
    if WA_DB.exists():
        c = sqlite3.connect(f"file:{WA_DB}?mode=ro", uri=True)
        out["whatsapp_contacts_hashed"] = c.execute(
            "SELECT count(*) FROM whatsapp_contacts WHERE phone_hash IS NOT NULL").fetchone()[0]
        c.close()
    return out


def _load_env_salt():
    """Carga el PRIMER LOG_SALT de config/.env (estandar vigente) y lo instala
    en core.crypto — mismo formato que clients.phone_hash."""
    import sys
    sys.path.insert(0, str(REPO))
    envf = REPO / "config" / ".env"
    salt = None
    if envf.exists():
        for line in envf.read_text().splitlines():
            line = line.strip()
            if line.startswith("LOG_SALT=") and salt is None:
                salt = line.split("=", 1)[1]
    if not salt or "change-this" in salt:
        raise RuntimeError("LOG_SALT invalido/ausente en config/.env")
    from core.crypto import set_log_salt
    set_log_salt(salt)
    return salt


def phone_hash(phone: str, salt: str | None = None) -> str:
    """Delega en core.crypto.hash_phone — formato estandar del ecosistema
    (SHA256(LOG_SALT:phone)[:32], phone en E.164 con '+')."""
    import re
    from core.crypto import hash_phone
    raw = str(phone or "").strip()
    d = re.sub(r"\D", "", raw)
    if not d:
        raise ValueError("phone vacio")
    e164 = "+" + d
    return hash_phone(e164)


def _ensure_salt() -> str:
    return _load_env_salt()



if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    print("conversations.db:", harden_conversations(dry))
    print("whatsapp_bot.db:", harden_whatsapp(dry))
    print("verify:", verify_hashed())