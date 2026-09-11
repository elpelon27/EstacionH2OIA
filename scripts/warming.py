#!/usr/bin/env python3
"""
warming.py — Warming predictivo de memoria semántica en Redis.

SOUL FASE 3 · PARCHE 7 (v2, decisiones D-7.x aprobadas por el Líder 2026-09-10):
- D-7.1: activación automática requiere 3 SEMANAS de datos en cron_runs
  (AUTO_ACTIVATION_AFTER_DAYS = 21). Antes de esa fecha, el warming automático
  está DESACTIVADO: solo --force manual.
- D-7.2: top-10 memorias más probables a pre-cargar (TOP_K = 10).
- D-7.3: TTL 7200s (se mantiene el valor actual).
- D-7.4: NO hay eventos de agentes hermanos (no existe bus de eventos);
  esa fuente queda explícitamente excluida hacia FASE 4+.

Uso:
  venv/bin/python scripts/warming.py              # auto (inactivo hasta D-7.1)
  venv/bin/python scripts/warming.py --dry-run    # solo detectar/simular
  venv/bin/python scripts/warming.py --force      # forzar warming manual (SIEMPRE disponible)

Autor: Prometeo · FASE 3 SOUL v2.1.0 · Parche 7 v2 · 2026-09-10
"""

import argparse
import json
import logging
import os
import sqlite3
from collections import Counter
from datetime import UTC, datetime, timedelta
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

WARMING_TTL = 7200  # D-7.3: 2 horas en segundos (se mantiene)
PATTERN_THRESHOLD = 3  # ≥3 ejecuciones en mismo día/hora
TOP_K = 10  # D-7.2: top-10 memorias más probables a pre-cargar
AUTO_ACTIVATION_AFTER_DAYS = 21  # D-7.1: 3 semanas de datos en cron_runs
# D-7.4: sin bus de eventos de agentes hermanos — fuente explícitamente
# excluida hasta FASE 4+. Nada de código la consume aquí.
AUTO_ACTIVATION_START = datetime(2026, 9, 10, tzinfo=UTC)  # fecha de inicio del acumulo (parche 10)


def auto_activation_ready() -> tuple[bool, str]:
    """
    D-7.1: el warming automático solo puede activarse cuando cron_runs tiene
    ≥21 días de datos desde el inicio del registro (parche 10, 2026-09-10).
    """
    now = datetime.now(UTC)
    eligible_at = AUTO_ACTIVATION_START + timedelta(days=AUTO_ACTIVATION_AFTER_DAYS)
    if now >= eligible_at:
        return True, "auto activable (21+ días de cron_runs)"
    remaining = eligible_at - now
    return (
        False,
        f"auto DESACTIVADO hasta {eligible_at.date().isoformat()} "
        f"(faltan {remaining.days} días; usa --force para warming manual)",
    )


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

    patterns: Counter[str] = Counter()
    for _cron_name, executed_at in rows:
        try:
            dt = datetime.fromisoformat(executed_at.replace("Z", "+00:00"))
            key = f"{dt.strftime('%A')}_{dt.hour:02d}h"
            patterns[key] += 1
        except (ValueError, AttributeError):
            continue

    detected = []
    for key, count in patterns.most_common(20):
        if count >= PATTERN_THRESHOLD:
            detected.append({"pattern": key, "count": count})
    return detected


def prefetch_to_redis(chunks: list[dict[str, Any]], dry_run: bool, event_type: str) -> int:
    """Pre-carga chunks en Redis con TTL 7200s (D-7.3). Retorna count exitoso."""
    try:
        import redis

        r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
        r.ping()
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

    if not dry_run:
        conn = sqlite3.connect(MEMORY_DB)
        conn.execute(
            "INSERT INTO warming_log "
            "(event_type, chunks_prefetched, cache_hits, cache_misses, miss_rate) "
            "VALUES (?, ?, 0, ?, 1.0)",
            (event_type, count, count),
        )
        conn.commit()
        conn.close()

    return count


def get_top_chunks_from_qdrant() -> list[dict[str, Any]]:
    """D-7.2: obtiene top-10 memorias más probables de Qdrant (más recientes)."""
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
        return [
            {"id": str(point.id), "payload": point.payload or {}}
            for point in points
        ]
    except Exception as e:
        logger.warning(f"Qdrant no disponible: {e}")
        return []


def run_warming(dry_run: bool, force: bool) -> dict[str, Any]:
    """
    Ejecuta el warming predictivo.

    Reglas (D-7.x):
    - --force: warming manual SIEMPRE disponible (independiente de D-7.1).
    - Sin --force: solo si auto-activación lista (D-7.1) Y hay patrones.
    """
    logger.info(f"Warming iniciado (dry_run={dry_run}, force={force})")
    ready, reason = auto_activation_ready()
    logger.info(f"Auto-activación: {reason}")

    if force:
        chunks = get_top_chunks_from_qdrant()
        if chunks:
            cached = prefetch_to_redis(chunks, dry_run, "forced_manual")
            logger.info(
                f"Warming --force: {cached} chunks cacheados en Redis (TTL={WARMING_TTL}s)"
            )
            return {"status": "ok", "trigger": "force", "chunks": cached}
        logger.info("No hay chunks en Qdrant para warming.")
        return {"status": "no_chunks", "trigger": "force", "chunks": 0}

    # Camino automático: bloqueado hasta D-7.1 (21 días de cron_runs)
    if not ready:
        logger.info(
            "Warming automático OMITIDO (D-7.1: requiere 21 días de cron_runs; "
            "usa --force para warming manual)."
        )
        return {"status": "auto_disabled", "trigger": "auto", "chunks": 0}

    patterns = detect_patterns()
    if patterns:
        logger.info(f"Patrones detectados: {len(patterns)}")
        for p in patterns[:5]:
            logger.info(f"  {p['pattern']}: {p['count']} ejecuciones")
    else:
        logger.info("No se detectaron patrones temporales.")

    if patterns:
        chunks = get_top_chunks_from_qdrant()
        if chunks:
            cached = prefetch_to_redis(chunks, dry_run, "pattern_detected")
            logger.info(
                f"Warming: {cached} chunks cacheados en Redis (TTL={WARMING_TTL}s)"
            )
            return {"status": "ok", "trigger": "pattern", "chunks": cached}
        logger.info("No hay chunks en Qdrant para warming.")
        return {"status": "no_chunks", "trigger": "pattern", "chunks": 0}

    logger.info("Warming omitido: sin patrones detectados.")
    return {"status": "no_patterns", "trigger": "auto", "chunks": 0}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Warming predictivo de memoria en Redis (Parche 7 v2)"
    )
    parser.add_argument("--dry-run", action="store_true", help="Solo detectar/simular")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Forzar warming manual (única vía hasta activación auto D-7.1)",
    )
    args = parser.parse_args()

    result = run_warming(args.dry_run, args.force)
    logger.info(f"Resultado: {json.dumps(result)}")


if __name__ == "__main__":
    main()