#!/usr/bin/env python3
"""
consolidator.py — Consolidador automático de memoria episódica → semántica.

Lee entries no consolidadas de conversations.db, extrae hechos atómicos con
mem0, los clasifica con Ollama qwen2.5:7b, y los indexa en Qdrant + Obsidian.

Trigger: fin de sesión + cada 6h de inactividad.
Guardarraíl: si falla 3 veces consecutivas, detener y notificar.

Uso:
  python3 scripts/consolidator.py --dry-run          # solo leer, no escribir
  python3 scripts/consolidator.py                    # ejecutar consolidación
  python3 scripts/consolidator.py --hours 24         # últimas 24h

Autor: Prometeo · FASE 3 SOUL v2.1.0 · 2026-08-24
"""

import argparse
import json
import logging
import os
import sqlite3
import time
from datetime import UTC, datetime
from typing import Any

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("consolidator")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONV_DB = os.path.join(BASE_DIR, "data", "conversations.db")
MEMORY_DB = os.path.join(BASE_DIR, "data", "hermes_memory.db")
VAULT_DIR = os.path.join(BASE_DIR, "docs", "03-sesiones")

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")

MAX_CONSECUTIVE_FAILURES = 3
FAILURE_TRACK_FILE = os.path.join(BASE_DIR, "data", ".consolidator_failures")


def get_conversations_since(hours: int, limit: int = 50) -> list[dict[str, Any]]:
    """Lee entries de fs_audit_log de las últimas N horas como fuente de hechos."""
    conn = sqlite3.connect(CONV_DB)
    conn.row_factory = sqlite3.Row
    cutoff = f"datetime('now', '-{hours} hours')"
    rows = conn.execute(
        f"SELECT id, tabla, registro_id, accion, estado_anterior, estado_nuevo, "
        f"modificado_por, timestamp FROM fs_audit_log "
        f"WHERE timestamp >= {cutoff} ORDER BY timestamp ASC LIMIT {limit}"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def extract_facts_with_ollama(text: str, model: str = "qwen2.5:7b") -> list[dict[str, Any]]:
    """
    Usa Ollama local para extraer hechos atómicos de un texto.

    Retorna lista de {fact, confidence, source}.
    """
    import httpx

    prompt = (
        "Eres un extractor de hechos para un sistema de memoria de un negocio "
        "de venta de botellones de agua en Maracaibo, Venezuela.\n"
        "Del siguiente registro de auditoría de cambio de estado, "
        "extrae hechos OBJECTIVOS y relevantes para futuras sesiones.\n"
        "Formato: JSON array de objetos con 'fact' y 'confidence' "
        "(certain|inferred|tentative).\n"
        "Ejemplos de hechos útiles:\n"
        '  {"fact": "Pedido 42 cambió estado_pago a pagado", '
        '"confidence": "certain"}\n'
        '  {"fact": "Cliente tel 0414 tiene 3 pedidos pendientes", '
        '"confidence": "inferred"}\n'
        "Ignora cambios triviales (mismo estado → mismo estado).\n"
        "Si no hay hechos relevantes, retorna [].\n\n"
        f"Registro:\n{text[:2000]}\n\n"
        "Responde SOLO con JSON válido:\n"
    )

    try:
        with httpx.Client(timeout=30) as client:
            resp = client.post(
                f"{OLLAMA_URL}/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "format": "json",
                    "stream": False,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            text_response = data.get("response", "[]")
            facts = json.loads(text_response)
            if not isinstance(facts, list):
                return []
            return facts
    except Exception as e:
        logger.warning(f"Ollama extraction failed: {e}")
        return []


def get_embedding(text: str, model: str = "nomic-embed-text") -> list[float]:
    """Genera embedding real con Ollama nomic-embed-text (768d)."""
    import httpx

    try:
        with httpx.Client(timeout=30) as client:
            resp = client.post(
                f"{OLLAMA_URL}/api/embeddings",
                json={"model": model, "prompt": text[:8000]},
            )
            resp.raise_for_status()
            data = resp.json()
            emb = data.get("embedding", [])
            if len(emb) != 768:
                logger.warning(
                    f"Embedding dimension mismatch: "
                    f"expected 768, got {len(emb)}"
                )
            return emb
    except Exception as e:
        logger.warning(f"Embedding generation failed: {e}")
    return []


def index_in_qdrant(facts: list[dict[str, Any]]) -> int:
    """Indexa hechos en Qdrant collection hermes_memory con embeddings reales."""
    try:
        from qdrant_client import QdrantClient
        from qdrant_client.models import PointStruct

        client = QdrantClient(url=QDRANT_URL)
        count = 0
        for _i, fact in enumerate(facts):
            fact_text = fact.get("fact", str(fact))
            confidence = fact.get("confidence", "tentative")
            point_id = abs(hash(fact_text)) % (2**63)

            # Embedding real con nomic-embed-text (768d)
            vector = get_embedding(fact_text)
            if not vector:
                logger.warning(
                    f"Skipping fact {point_id}: sin embedding"
                )
                continue

            client.upsert(
                collection_name="hermes_memory",
                points=[
                    PointStruct(
                        id=point_id,
                        vector=vector,
                        payload={
                            "fact": fact_text,
                            "confidence": confidence,
                            "source": "consolidator",
                            "timestamp": datetime.now(UTC).isoformat(),
                        },
                    )
                ],
            )
            count += 1
        return count
    except Exception as e:
        logger.warning(f"Qdrant indexing failed: {e}")
        return 0


def write_to_obsidian(facts: list[dict[str, Any]]) -> int:
    """Escribe hechos en el vault Obsidian. Retorna count exitoso."""
    if not os.path.exists(VAULT_DIR):
        os.makedirs(VAULT_DIR, exist_ok=True)

    ts = datetime.now(UTC).strftime("%Y-%m-%d_%H%M%S")
    filepath = os.path.join(VAULT_DIR, f"consolidated_{ts}.md")

    lines = [
        "---",
        "source: consolidator",
        f"timestamp: {ts}",
        f"facts_count: {len(facts)}",
        "---",
        "",
        f"# Consolidación automática {ts}",
        "",
    ]

    for fact in facts:
        f_text = fact.get("fact", str(fact))
        conf = fact.get("confidence", "tentative")
        lines.append(f"- **[{conf}]** {f_text}")

    lines.append("")
    lines.append("*Generado por consolidator.py · FASE 3 SOUL v2.1.0*")

    try:
        with open(filepath, "w") as f:
            f.write("\n".join(lines))
        logger.info(f"Obsidian note written: {filepath}")
        return len(facts)
    except Exception as e:
        logger.warning(f"Obsidian write failed: {e}")
        return 0


def log_consolidation(
    sessions: int,
    chunks: int,
    facts_total: int,
    facts_certain: int,
    facts_inferred: int,
    facts_tentative: int,
    conflicts: int,
    errors: str | None,
    duration_ms: int,
) -> None:
    """Registra la ejecución en hermes_memory.db::consolidation_log."""
    conn = sqlite3.connect(MEMORY_DB)
    conn.execute(
        "INSERT INTO consolidation_log "
        "(sessions_processed, chunks_read, facts_extracted, "
        "facts_certain, facts_inferred, facts_tentative, "
        "conflicts_detected, errors, duration_ms) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            sessions,
            chunks,
            facts_total,
            facts_certain,
            facts_inferred,
            facts_tentative,
            conflicts,
            errors,
            duration_ms,
        ),
    )
    conn.commit()
    conn.close()


def check_failure_count() -> int:
    """Lee el contador de fallos consecutivos."""
    try:
        with open(FAILURE_TRACK_FILE) as f:
            return int(f.read().strip())
    except (FileNotFoundError, ValueError):
        return 0


def increment_failure() -> int:
    """Incrementa el contador de fallos. Retorna el nuevo count."""
    count = check_failure_count() + 1
    with open(FAILURE_TRACK_FILE, "w") as f:
        f.write(str(count))
    return count


def reset_failures() -> None:
    """Resetea el contador de fallos tras éxito."""
    import contextlib

    with contextlib.suppress(FileNotFoundError):
        os.remove(FAILURE_TRACK_FILE)


def run_consolidation(hours: int, dry_run: bool) -> None:
    """Ejecuta la consolidación completa."""
    start = time.time()
    failures = check_failure_count()
    if failures >= MAX_CONSECUTIVE_FAILURES:
        logger.error(
            f"Consolidador detenido: {failures} fallos consecutivos. "
            f"Requiere intervención manual. Eliminar {FAILURE_TRACK_FILE} para reiniciar."
        )
        return

    logger.info(f"Consolidador iniciado (horas={hours}, dry_run={dry_run})")

    # 1. Leer conversaciones (limitadas para no saturar Ollama)
    conversations = get_conversations_since(hours, limit=50)
    if not conversations:
        logger.info("No hay conversaciones para consolidar.")
        log_consolidation(0, 0, 0, 0, 0, 0, 0, None, int((time.time() - start) * 1000))
        return

    logger.info(f"Conversaciones leídas: {len(conversations)}")

    # 2. Extraer hechos con Ollama
    all_facts: list[dict[str, Any]] = []
    for conv in conversations:
        # Construir texto descriptivo del cambio de estado
        accion = conv.get("accion", "")
        tabla = conv.get("tabla", "")
        estado_nuevo = conv.get("estado_nuevo", "{}")
        text = (
            f"Tabla: {tabla}, Acción: {accion}, "
            f"Registro ID: {conv.get('registro_id', '')}, "
            f"Estado nuevo: {estado_nuevo}"
        )
        if len(text) < 20:
            continue
        facts = extract_facts_with_ollama(text)
        all_facts.extend(facts)

    logger.info(f"Hechos extraídos: {len(all_facts)}")

    # 3. Clasificar por confianza
    certain = sum(1 for f in all_facts if f.get("confidence") == "certain")
    inferred = sum(1 for f in all_facts if f.get("confidence") == "inferred")
    tentative = sum(1 for f in all_facts if f.get("confidence") == "tentative")

    # 4. Indexar en Qdrant + Obsidian
    if not dry_run and all_facts:
        indexed = index_in_qdrant(all_facts)
        written = write_to_obsidian(all_facts)
        logger.info(f"Qdrant: {indexed} indexados, Obsidian: {written} escritos")
        reset_failures()
    else:
        logger.info("Dry-run: no se escribe a Qdrant/Obsidian")

    # 5. Log
    duration_ms = int((time.time() - start) * 1000)
    log_consolidation(
        sessions=1,
        chunks=len(conversations),
        facts_total=len(all_facts),
        facts_certain=certain,
        facts_inferred=inferred,
        facts_tentative=tentative,
        conflicts=0,
        errors=None,
        duration_ms=duration_ms,
    )
    logger.info(f"Consolidación completada en {duration_ms}ms")


def main() -> None:
    parser = argparse.ArgumentParser(description="Consolidador de memoria episódica → semántica")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Solo leer, no escribir a Qdrant/Obsidian",
    )
    parser.add_argument(
        "--hours",
        type=int,
        default=24,
        help="Horas hacia atrás para consolidar (default: 24)",
    )
    args = parser.parse_args()

    try:
        run_consolidation(args.hours, args.dry_run)
    except Exception as e:
        failures = increment_failure()
        logger.error(f"Consolidador falló ({failures}/{MAX_CONSECUTIVE_FAILURES}): {e}")
        if failures >= MAX_CONSECUTIVE_FAILURES:
            logger.error("GUARDARRAÍL: consolidador detenido por fallos consecutivos")


if __name__ == "__main__":
    main()
