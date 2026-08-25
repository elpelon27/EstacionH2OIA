#!/usr/bin/env python3
"""
decay_social.py — Aplica decay exponencial a la capa Social (interactions.db).

Recorre interactions.db, aplica decay 0.99/día, archiva entradas con
relevance < 0.1.

Cron: diario 3am.

Uso:
  python3 scripts/decay_social.py --dry-run    # solo calcular
  python3 scripts/decay_social.py               # ejecutar decay

Autor: Prometeo · FASE 3 SOUL v2.1.0 · 2026-08-24
"""

import argparse
import logging
import os
import sqlite3
from datetime import UTC, datetime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("decay_social")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INTERACTIONS_DB = os.path.join(BASE_DIR, "data", "interactions.db")

DECAY_FACTOR = 0.99  # por día
ARCHIVE_THRESHOLD = 0.1  # relevance < 0.1 se archiva


def apply_decay(dry_run: bool) -> dict[str, int]:
    """Aplica decay a interactions.db. Retorna stats."""
    conn = sqlite3.connect(INTERACTIONS_DB)
    stats: dict[str, int] = {
        "total": 0,
        "archived": 0,
        "remaining": 0,
    }

    # Leer todas las interacciones
    rows = conn.execute(
        "SELECT id, created_at FROM interactions WHERE resolution_status != 'archived'"
    ).fetchall()
    stats["total"] = len(rows)

    now = datetime.now(UTC)
    to_archive: list[int] = []

    for row in rows:
        row_id, created_at_str = row
        try:
            created = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            continue

        days_since = (now - created).days
        if days_since <= 0:
            continue

        relevance = DECAY_FACTOR**days_since
        if relevance < ARCHIVE_THRESHOLD:
            to_archive.append(row_id)

    stats["archived"] = len(to_archive)
    stats["remaining"] = stats["total"] - len(to_archive)

    if not dry_run and to_archive:
        # Mover a interactions_archive
        for row_id in to_archive:
            row_data = conn.execute("SELECT * FROM interactions WHERE id = ?", (row_id,)).fetchone()
            if row_data:
                conn.execute(
                    "INSERT OR IGNORE INTO interactions_archive "
                    "(id, actor_id, channel, message_hash, payload_preview, "
                    "intent_detected, commitment_made, emotional_tag, "
                    "resolution_status, created_at, resolved_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    row_data,
                )
                conn.execute(
                    "UPDATE interactions SET resolution_status = 'expired' " "WHERE id = ?",
                    (row_id,),
                )
        conn.commit()
        logger.info(f"Archivadas {len(to_archive)} interacciones (relevance < {ARCHIVE_THRESHOLD})")
    elif dry_run:
        logger.info(f"[DRY-RUN] Se archivarían {len(to_archive)} interacciones")
    else:
        logger.info("Nada que archivar.")

    conn.close()
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Aplica decay exponencial a interactions.db")
    parser.add_argument("--dry-run", action="store_true", help="Solo calcular, no archivar")
    args = parser.parse_args()

    logger.info(f"Decay social iniciado (dry_run={args.dry_run})")
    stats = apply_decay(args.dry_run)
    logger.info(
        f"Total: {stats['total']}, "
        f"Archivadas: {stats['archived']}, "
        f"Restantes: {stats['remaining']}"
    )


if __name__ == "__main__":
    main()
