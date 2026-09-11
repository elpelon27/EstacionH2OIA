#!/usr/bin/env python3
"""Whatsscanbot — DB layer (DT-WSIMPORT 2C).

Aísla TODO el acceso a data/whatsapp_bot.db. Además hace UPSERT de
contactos en dispatch.db clients (sin tocar schema), reutilizando la
normalización +58 de scripts/import_contacts_vcf.py vía parser.normalize_phone.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

ROOT = Path("/mnt/ssd_trabajo/hermes-agent")
DB_PATH = Path(ROOT / "data" / "whatsapp_bot.db")
DISPATCH_DB = Path(ROOT / "data" / "dispatch.db")


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB_PATH, timeout=30)
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA foreign_keys=ON")
    return c


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


# ── imports ────────────────────────────────────────────────────────────

def insert_import(
    contact_phone: str | None,
    contact_name: str | None,
    source_type: str,
    source_file_hash: str,
    source_text_preview: str | None = None,
) -> int:
    """Crea el registro de import. ValueError si hash duplicado."""
    try:
        with _conn() as c:
            cur = c.execute(
                """INSERT INTO whatsapp_imports
                   (contact_phone, contact_name, source_type,
                    source_file_hash, source_text_preview)
                   VALUES (?,?,?,?,?)""",
                (contact_phone, contact_name, source_type,
                 source_file_hash, (source_text_preview or "")[:500]),
            )
            assert cur.lastrowid is not None
            return int(cur.lastrowid)
    except sqlite3.IntegrityError as e:
        raise ValueError(f"import duplicado: {source_file_hash}") from e


def get_import_by_hash(source_file_hash: str) -> dict[str, Any] | None:
    with _conn() as c:
        c.row_factory = sqlite3.Row
        row = c.execute(
            "SELECT * FROM whatsapp_imports WHERE source_file_hash=?",
            (source_file_hash,),
        ).fetchone()
        return dict(row) if row else None


def finalize_import(
    import_id: int,
    message_count: int,
    period_start: str | None,
    period_end: str | None,
) -> None:
    with _conn() as c:
        c.execute(
            """UPDATE whatsapp_imports
               SET message_count=?, period_start=?, period_end=?
               WHERE id=?""",
            (message_count, period_start, period_end, import_id),
        )


def set_import_summary(import_id: int, summary: dict[str, Any]) -> None:
    with _conn() as c:
        c.execute(
            "UPDATE whatsapp_imports SET summary_json=? WHERE id=?",
            (json.dumps(summary, ensure_ascii=False), import_id),
        )


def list_imports(limit: int = 20) -> list[dict[str, Any]]:
    with _conn() as c:
        c.row_factory = sqlite3.Row
        rows = c.execute(
            """SELECT id, contact_phone, contact_name, message_count,
                      period_start, period_end, imported_at, source_type
               FROM whatsapp_imports ORDER BY id DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


# ── messages ──────────────────────────────────────────────────────────

def insert_message(import_id: int, msg: dict[str, Any]) -> int | None:
    """INSERT; None si duplicado por msg_hash (dedup)."""
    h = msg.get("msg_hash") or sha256_text(
        f"{import_id}|{msg.get('timestamp','')}|{msg.get('sender_name','')}"
        f"|{msg.get('message_text','')}"
    )
    try:
        with _conn() as c:
            cur = c.execute(
                """INSERT INTO whatsapp_messages
                   (import_id, phone, sender_name, message_text, timestamp,
                    direction, message_type, media_path, msg_hash)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (import_id, msg.get("phone"), msg.get("sender_name"),
                 msg.get("message_text"), msg.get("timestamp"),
                 msg.get("direction"), msg.get("message_type", "text"),
                 msg.get("media_path"), h),
            )
            if cur.lastrowid is None:
                return None
            return int(cur.lastrowid)
    except sqlite3.IntegrityError:
        return None


def search_messages(query: str, limit: int = 10) -> list[dict[str, Any]]:
    """LIKE search simple (fallback cuando Qdrant no aplica)."""
    q = f"%{query}%"
    with _conn() as c:
        c.row_factory = sqlite3.Row
        rows = c.execute(
            """SELECT m.*, i.contact_name FROM whatsapp_messages m
               JOIN whatsapp_imports i ON i.id = m.import_id
               WHERE m.message_text LIKE ? AND m.message_type='text'
               ORDER BY m.timestamp DESC LIMIT ?""",
            (q, limit),
        ).fetchall()
        return [dict(r) for r in rows]


def get_contact(phone: str) -> dict[str, Any] | None:
    with _conn() as c:
        c.row_factory = sqlite3.Row
        row = c.execute(
            "SELECT * FROM whatsapp_contacts WHERE phone=?", (phone,)
        ).fetchone()
        return dict(row) if row else None


# ── contacts (whatsapp_bot.db + UPSERT dispatch.db) ────────────────────

def upsert_contact(
    phone: str | None,
    name: str | None,
    first_seen: str | None = None,
    last_seen: str | None = None,
    n_messages: int = 0,
) -> int | None:
    """UPSERT en whatsapp_contacts + dispatch.db clients.

    Returns whatsapp_contacts rowcount (1 si insert, 0 si update).
    """
    if not phone:
        return None
    with _conn() as c:
        cur = c.execute(
            """INSERT INTO whatsapp_contacts
                   (phone, name, first_seen_at, last_seen_at, total_messages)
               VALUES (?,?,?,?,?)
               ON CONFLICT(phone) DO UPDATE SET
                   name=COALESCE(excluded.name, name),
                   last_seen_at=COALESCE(excluded.last_seen_at, last_seen_at),
                   total_messages=total_messages+excluded.total_messages""",
            (phone, name, first_seen, last_seen, n_messages),
        )
        rowcount = cur.rowcount
    _upsert_dispatch_client(phone, name)
    return rowcount


def _phone_hash(phone: str) -> str:
    return hashlib.sha256(phone.encode()).hexdigest()


def _upsert_dispatch_client(phone: str, name: str | None) -> None:
    """UPSERT por phone (UNIQUE) en dispatch.db clients. NUNCA crea schema."""
    try:
        with sqlite3.connect(DISPATCH_DB, timeout=30) as c:
            c.row_factory = sqlite3.Row
            row = c.execute(
                "SELECT id FROM clients WHERE phone=?", (phone,)
            ).fetchone()
            if row:
                if name:
                    c.execute(
                        "UPDATE clients SET updated_at=strftime('%s','now') "
                        "WHERE id=?", (row["id"],),
                    )
                client_id = int(row["id"])
            else:
                cur = c.execute(
                    """INSERT INTO clients
                       (phone, phone_hash, name, client_type)
                       VALUES (?,?,?, 'retail')""",
                    (phone, _phone_hash(phone), name),
                )
                assert cur.lastrowid is not None
                client_id = int(cur.lastrowid)
        with _conn() as c:
            c.execute(
                """UPDATE whatsapp_contacts
                   SET is_client=1, client_id=? WHERE phone=?""",
                (client_id, phone),
            )
    except sqlite3.Error:
        # dispatch.db es producción: fallar acá NO rompe el import
        pass
