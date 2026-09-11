#!/usr/bin/env python3
"""Whatsscanbot — creación inicial de data/whatsapp_bot.db (3 tablas aisladas).

DT-WSIMPORT 2A. NO toca dispatch.db ni ninguna otra DB del sistema.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

DB_PATH = Path("/mnt/ssd_trabajo/hermes-agent/data/whatsapp_bot.db")

SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS whatsapp_imports (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    contact_phone      TEXT,
    contact_name       TEXT,
    message_count      INTEGER NOT NULL DEFAULT 0,
    period_start       TEXT,
    period_end         TEXT,
    imported_at        REAL NOT NULL DEFAULT (strftime('%s','now')),
    source_type        TEXT NOT NULL,          -- 'zip' | 'txt' | 'paste'
    source_file_hash   TEXT UNIQUE,            -- sha256 del input original (dedup)
    source_text_preview TEXT
);
CREATE INDEX IF NOT EXISTS idx_wi_phone ON whatsapp_imports(contact_phone);

CREATE TABLE IF NOT EXISTS whatsapp_messages (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    import_id    INTEGER NOT NULL REFERENCES whatsapp_imports(id) ON DELETE CASCADE,
    phone        TEXT,
    sender_name  TEXT,
    message_text TEXT NOT NULL,
    timestamp    TEXT,
    direction    TEXT,                         -- 'in' | 'out' | 'unknown'
    message_type TEXT,                         -- 'text' | 'media' | 'system'
    media_path   TEXT,
    msg_hash     TEXT UNIQUE                   -- sha256(import_id|ts|sender|text): dedup
);
CREATE INDEX IF NOT EXISTS idx_wm_import ON whatsapp_messages(import_id);
CREATE INDEX IF NOT EXISTS idx_wm_phone ON whatsapp_messages(phone);
CREATE INDEX IF NOT EXISTS idx_wm_ts ON whatsapp_messages(timestamp);

CREATE TABLE IF NOT EXISTS whatsapp_contacts (
    phone          TEXT PRIMARY KEY,           -- normalizado +58XXXXXXXXXX
    name           TEXT,
    first_seen_at  TEXT,
    last_seen_at   TEXT,
    total_messages INTEGER NOT NULL DEFAULT 0,
    is_client      INTEGER NOT NULL DEFAULT 0, -- 1 si existe en dispatch.db clients
    client_id      INTEGER                      -- FK lógica a dispatch.db clients.id
);
"""


def main() -> None:
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.executescript(SCHEMA)
        conn.commit()
        tables = [
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
        ]
        print(f"OK — {DB_PATH} creada. Tablas: {tables}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
