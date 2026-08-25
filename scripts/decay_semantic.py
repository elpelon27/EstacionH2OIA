#!/usr/bin/env python3
"""
decay_semantic.py — Aplica decay exponencial a la capa Semántica (Qdrant).

Recorre Qdrant collection hermes_memory, aplica decay 0.995/día,
archiva puntos con relevance < 0.1 en hermes_memory.db::archive.

Cron: semanal domingo 2am.

Uso:
  python3 scripts/decay_semantic.py --dry-run    # solo calcular
  python3 scripts/decay_semantic.py               # ejecutar decay

Autor: Prometeo · FASE 3 SOUL v2.1.0 · 2026-08-24
"""

import argparse
import logging
import os
import sqlite3
from datetime import UTC, datetime
from typing import Any

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("decay_semantic")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEMORY_DB = os.path.join(BASE_DIR, "data", "hermes_memory.db")

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
DECAY_FACTOR = 0.995  # por día
ARCHIVE_THRESHOLD = 0.1


def apply_decay(dry_run: bool) -> dict[str, int]:
    """Aplica decay a Qdrant. Retorna stats."""
    stats: dict[str, int] = {
        "total": 0,
        "archived": 0,
        "remaining": 0,
    }

    try:
        from qdrant_client import QdrantClient

        client = QdrantClient(url=QDRANT_URL)

        # Contar puntos totales
        info = client.get_collection("hermes_memory")
        stats["total"] = info.points_count or 0

        # Scroll through all points
        now = datetime.now(UTC)
        to_archive: list[dict[str, Any]] = []

        offset = None
        while True:
            results = client.scroll(
                collection_name="hermes_memory",
                limit=100,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            points, next_offset = results[0], results[1]

            if not points:
                break

            for point in points:
                payload = point.payload or {}
                ts_str = payload.get("timestamp", "")
                try:
                    created = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                except (ValueError, AttributeError):
                    continue

                days_since = (now - created).days
                if days_since <= 0:
                    continue

                relevance = DECAY_FACTOR**days_since
                if relevance < ARCHIVE_THRESHOLD:
                    to_archive.append(
                        {
                            "id": point.id,
                            "payload": payload,
                            "relevance": relevance,
                        }
                    )

            if next_offset is None:
                break
            offset = next_offset

        stats["archived"] = len(to_archive)
        stats["remaining"] = stats["total"] - len(to_archive)

        if not dry_run and to_archive:
            # Archivar en SQLite
            conn = sqlite3.connect(MEMORY_DB)
            for item in to_archive:
                payload = item["payload"]
                fact_md = payload.get("fact", str(payload))
                conn.execute(
                    "INSERT INTO archive "
                    "(original_qdrant_id, fact_markdown, "
                    "relevance_at_archive, rationale) "
                    "VALUES (?, ?, ?, ?)",
                    (
                        str(item["id"]),
                        fact_md,
                        item["relevance"],
                        f"Decay semántico: {item['relevance']:.4f} < {ARCHIVE_THRESHOLD}",
                    ),
                )
            conn.commit()
            conn.close()

            # Eliminar de Qdrant
            ids_to_delete = [item["id"] for item in to_archive]
            client.delete(
                collection_name="hermes_memory",
                points_selector=ids_to_delete,
            )
            logger.info(
                f"Archivados {len(to_archive)} puntos en "
                f"hermes_memory.db::archive y eliminados de Qdrant"
            )
        elif dry_run:
            logger.info(f"[DRY-RUN] Se archivarían {len(to_archive)} puntos")
        else:
            logger.info("Nada que archivar.")

    except Exception as e:
        logger.error(f"Error en decay_semantic: {e}")
        stats["total"] = -1

    return stats


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Aplica decay exponencial a Qdrant (capa semántica)"
    )
    parser.add_argument("--dry-run", action="store_true", help="Solo calcular, no archivar")
    args = parser.parse_args()

    logger.info(f"Decay semántico iniciado (dry_run={args.dry_run})")
    stats = apply_decay(args.dry_run)
    if stats["total"] >= 0:
        logger.info(
            f"Total: {stats['total']}, "
            f"Archivados: {stats['archived']}, "
            f"Restantes: {stats['remaining']}"
        )


if __name__ == "__main__":
    main()
