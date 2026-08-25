#!/usr/bin/env python3
"""
warming.py — Warming selectivo de memoria semántica en Redis.

Lee cron_runs de hermes_memory.db, detecta patrones temporales,
y pre-fetcha top-10 chunks de Qdrant a Redis con TTL 2h.

Trigger: patrón detectado o sesión iniciada.

Uso:
  python3 scripts/warming.py --dry-run    # solo detectar patrones
  python3 scripts/warming.py               # ejecutar warming
  python3 scripts/warming.py --force       forzar warming sin patrón

Autor: Prometeo · FASE 3 SOUL v2.1.0 · 2026-08-24
"""

import argparse
import json
import logging
import os
import sqlite3
from collections import Counter
from typing import Any

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("warming")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEMORY_DB = os.path.join(BASE_DIR, "data", "hermes_memory.db")

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))

WARMING_TTL = 7200  # 2 horas en segundos
PATTERN_THRESHOLD = 3  # ≥3 ejecuciones en mismo día/hora
TOP_K = 10  # top-10 chunks a precargar


def detect_patterns() -> list[dict[str, Any]]:
    """Detecta patrones temporales en cron_runs."""
    conn = sqlite3.connect(MEMORY_DB)
    rows = conn.execute(
        "SELECT cron_name, executed_at FROM cron_runs "
        "WHERE success = 1 ORDER BY executed_at DESC LIMIT 500"
    ).fetchall()
    conn.close()

    if not rows:
        return []

    # Agrupar por día de la semana + hora
    patterns: Counter[str] = Counter()
    for _cron_name, executed_at in rows:
        try:
            dt = __import__("datetime").datetime.fromisoformat(executed_at.replace("Z", "+00:00"))
            key = f"{dt.strftime('%A')}_{dt.hour:02d}h"
            patterns[key] += 1
        except (ValueError, AttributeError):
            continue

    # Filtrar patrones que superan el threshold
    detected = []
    for key, count in patterns.most_common(20):
        if count >= PATTERN_THRESHOLD:
            detected.append({"pattern": key, "count": count})

    return detected


def prefetch_to_redis(chunks: list[dict[str, Any]], dry_run: bool) -> int:
    """Pre-carga chunks en Redis con TTL. Retorna count exitoso."""
    try:
        import importlib

        redis = importlib.import_module("redis")

        r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
        r.ping()  # verificar conexión
    except Exception as e:
        logger.warning(f"Redis no disponible: {e}")
        return 0

    count = 0
    for chunk in chunks:
        key = f"hermes:warm:{chunk.get('id', hash(str(chunk)))}"
        value = json.dumps(chunk, default=str)

        if not dry_run:
            r.setex(key, WARMING_TTL, value)
        count += 1

    # Log en warming_log
    if not dry_run:
        conn = sqlite3.connect(MEMORY_DB)
        conn.execute(
            "INSERT INTO warming_log "
            "(event_type, chunks_prefetched, cache_hits, cache_misses, miss_rate) "
            "VALUES (?, ?, 0, ?, 1.0)",
            ("pattern_detected", count, count),
        )
        conn.commit()
        conn.close()

    return count


def get_top_chunks_from_qdrant() -> list[dict[str, Any]]:
    """Obtiene top-10 chunks más recientes de Qdrant."""
    try:
        from qdrant_client import QdrantClient

        client = QdrantClient(url=QDRANT_URL)
        results = client.scroll(
            collection_name="hermes_memory",
            limit=TOP_K,
            with_payload=True,
            with_vectors=False,
        )
        points = results[0] if results else []

        chunks = []
        for point in points:
            chunks.append(
                {
                    "id": str(point.id),
                    "payload": point.payload or {},
                }
            )
        return chunks
    except Exception as e:
        logger.warning(f"Qdrant no disponible: {e}")
        return []


def run_warming(dry_run: bool, force: bool) -> None:
    """Ejecuta el warming selectivo."""
    logger.info(f"Warming iniciado (dry_run={dry_run}, force={force})")

    # 1. Detectar patrones
    patterns = detect_patterns()
    if patterns:
        logger.info(f"Patrones detectados: {len(patterns)}")
        for p in patterns[:5]:
            logger.info(f"  {p['pattern']}: {p['count']} ejecuciones")
    else:
        logger.info("No se detectaron patrones temporales.")

    # 2. Si hay patrones o --force, ejecutar warming
    if patterns or force:
        chunks = get_top_chunks_from_qdrant()
        if chunks:
            cached = prefetch_to_redis(chunks, dry_run)
            logger.info(f"Warming: {cached} chunks cacheados en Redis " f"(TTL={WARMING_TTL}s)")
        else:
            logger.info("No hay chunks en Qdrant para warming.")
    else:
        logger.info("Warming omitido: sin patrones detectados (usa --force para forzar).")


def main() -> None:
    parser = argparse.ArgumentParser(description="Warming selectivo de memoria en Redis")
    parser.add_argument("--dry-run", action="store_true", help="Solo detectar patrones")
    parser.add_argument("--force", action="store_true", help="Forzar warming sin patrón")
    args = parser.parse_args()

    run_warming(args.dry_run, args.force)


if __name__ == "__main__":
    main()
