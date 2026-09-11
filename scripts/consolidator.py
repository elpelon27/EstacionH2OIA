#!/usr/bin/env python3
"""
consolidator.py — Consolidador automático de memoria episódica → semántica.

SOUL FASE 3 · PARCHE 5 (v2, decisiones D-5.x aprobadas por el Líder 2026-09-10):
- D-5.1: watermark propio en hermes_memory.db::consolidation_watermark
  (last_consolidated_id = max messages.id ya procesado). NO usa --hours ni relee.
- D-5.2: fuente de lectura = Session DB de Hermes (/home/skynet/.hermes/state.db,
  tablas sessions + messages), NO conversations.db/fs_audit_log.
- D-5.3: consolidation_log se mantiene intacto; la entrada del 2026-08-25 queda
  como histórico. Este parche sigue escribiendo en consolidation_log (--live only).

Modo: --dry-run por defecto; --live requiere flag explícito.
Guardarraíles:
- nunca consolida más de MAX_SESSIONS_PER_RUN sesiones por corrida (OOM).
- máx MAX_MESSAGES_PER_RUN mensajes por corrida.
- 3 fallos consecutivos → detención (seguimiento en data/.consolidator_failures).

Uso:
  venv/bin/python scripts/consolidator.py                # dry-run por defecto
  venv/bin/python scripts/consolidator.py --live         # consolida de verdad
  venv/bin/python scripts/consolidator.py --live --max-sessions 5

Autor: Prometeo · FASE 3 SOUL v2.1.0 · Parche 5 v2 · 2026-09-10
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
MEMORY_DB = os.path.join(BASE_DIR, "data", "hermes_memory.db")
VAULT_DIR = os.path.join(BASE_DIR, "docs", "03-sesiones")

# D-5.2: Session DB de Hermes (validada en vivo: 38 sesiones, 25k mensajes).
# No es conversations.db (esa era fs_audit_log y no es la fuente correcta).
SESSION_DB = os.getenv(
    "HERMES_SESSION_DB",
    "/home/skynet/.hermes/state.db",
)

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")

MAX_SESSIONS_PER_RUN = 20  # guardarraíl OOM (D-5 guardarraíl de sesiones)
MAX_MESSAGES_PER_RUN = 200  # guardarraíl OOM (mensajes por corrida)
MAX_CONSECUTIVE_FAILURES = 3
FAILURE_TRACK_FILE = os.path.join(BASE_DIR, "data", ".consolidator_failures")

# Roles que contienen conversación útil (excluye tool/system)
CONVERSATION_ROLES = ("user", "assistant")


# ---------------------------------------------------------------------------
# Watermark (D-5.1)
# ---------------------------------------------------------------------------

def get_watermark(memory_conn: sqlite3.Connection) -> int:
    """Lee last_consolidated_id del watermark (0 si no existe)."""
    row = memory_conn.execute(
        "SELECT last_consolidated_id FROM consolidation_watermark WHERE id = 1"
    ).fetchone()
    return row[0] if row else 0


def update_watermark(
    memory_conn: sqlite3.Connection,
    last_id: int,
    status: str = "ok",
) -> None:
    """Actualiza el watermark con el último message.id consolidado."""
    memory_conn.execute(
        "UPDATE consolidation_watermark "
        "SET last_consolidated_id = ?, last_run_at = ?, status = ? "
        "WHERE id = 1",
        (last_id, datetime.now(UTC).isoformat(), status),
    )
    memory_conn.commit()


# ---------------------------------------------------------------------------
# Lectura de la Session DB (D-5.2)
# ---------------------------------------------------------------------------

def get_unconsolidated_sessions(
    since_id: int,
    max_sessions: int,
    max_messages: int,
) -> tuple[list[dict[str, Any]], int]:
    """
    Lee sesiones con mensajes nuevos (messages.id > since_id) de la Session DB.

    Retorna (sesiones, new_max_id). Cada sesión trae sus mensajes de
    conversación (user/assistant, activos, no compactados), recortados al
    guardarraíl de mensajes. new_max_id es el mayor message.id visto.
    """
    conn = sqlite3.connect(f"file:{SESSION_DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        # Sesiones que tienen al menos un mensaje posterior al watermark
        rows = conn.execute(
            "SELECT DISTINCT s.id, s.source, s.display_name, s.message_count, "
            "s.started_at, s.ended_at "
            "FROM sessions s JOIN messages m ON m.session_id = s.id "
            "WHERE m.id > ? AND m.role IN (?, ?) AND m.active = 1 "
            "AND m.compacted = 0 AND m.content IS NOT NULL "
            "AND length(m.content) > 0 "
            "ORDER BY s.started_at DESC LIMIT ?",
            (since_id, *CONVERSATION_ROLES, max_sessions),
        ).fetchall()
        sessions: list[dict[str, Any]] = []
        new_max_id = since_id
        budget = max_messages
        for row in rows:
            if budget <= 0:
                break
            msgs = conn.execute(
                "SELECT id, role, content, timestamp FROM messages "
                "WHERE session_id = ? AND id > ? AND role IN (?, ?) "
                "AND active = 1 AND compacted = 0 "
                "AND content IS NOT NULL AND length(content) > 0 "
                "ORDER BY timestamp ASC LIMIT ?",
                (row["id"], since_id, *CONVERSATION_ROLES, budget),
            ).fetchall()
            if not msgs:
                continue
            new_max_id = max(new_max_id, max(m["id"] for m in msgs))
            budget -= len(msgs)
            sessions.append(
                {
                    "session_id": row["id"],
                    "source": row["source"],
                    "display_name": row["display_name"],
                    "started_at": row["started_at"],
                    "messages": [
                        {
                            "id": m["id"],
                            "role": m["role"],
                            "content": m["content"],
                            "timestamp": m["timestamp"],
                        }
                        for m in msgs
                    ],
                }
            )
        return sessions, new_max_id
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Extracción de hechos (Ollama) e indexación (Qdrant/Obsidian) — sin cambios
# ---------------------------------------------------------------------------

def extract_facts_with_ollama(text: str, model: str = "qwen2.5:7b") -> list[dict[str, Any]]:
    """
    Usa Ollama local para extraer hechos atómicos de un texto.

    Retorna lista de {fact, confidence, source}.
    """
    import httpx

    prompt = (
        "Eres un extractor de hechos para un sistema de memoria de un negocio "
        "de venta de botellones de agua en Maracaibo, Venezuela.\n"
        "Del siguiente fragmento de conversación del agente Hermes, "
        "extrae hechos OBJECTIVOS y relevantes para futuras sesiones "
        "(preferencias del usuario, decisiones tomadas, estado de tareas, "
        "datos del negocio).\n"
        "Formato: JSON array de objetos con 'fact' y 'confidence' "
        "(certain|inferred|tentative).\n"
        "Si no hay hechos relevantes, retorna [].\n\n"
        f"Fragmento:\n{text[:3000]}\n\n"
        "Responde SOLO con JSON válido:\n"
    )

    try:
        with httpx.Client(timeout=180) as client:
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
            facts = json.loads(data.get("response", "[]"))
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
            emb = resp.json().get("embedding", [])
            if len(emb) != 768:
                logger.warning(
                    f"Embedding dimension mismatch: expected 768, got {len(emb)}"
                )
            return emb
    except Exception as e:
        logger.warning(f"Embedding generation failed: {e}")
    return []


def index_in_qdrant(facts: list[dict[str, Any]], session_id: str) -> int:
    """Indexa hechos en Qdrant collection hermes_memory con embeddings reales."""
    try:
        from qdrant_client import QdrantClient
        from qdrant_client.models import PointStruct

        client = QdrantClient(url=QDRANT_URL)
        count = 0
        for fact in facts:
            fact_text = fact.get("fact", str(fact))
            confidence = fact.get("confidence", "tentative")
            point_id = abs(hash(fact_text)) % (2**63)

            vector = get_embedding(fact_text)
            if not vector:
                logger.warning(f"Skipping fact {point_id}: sin embedding")
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
                            "session_id": session_id,
                            "created_at": datetime.now(UTC).isoformat(),
                        },
                    )
                ],
            )
            count += 1
        return count
    except Exception as e:
        logger.warning(f"Qdrant indexing failed: {e}")
        return 0


def write_to_obsidian(facts: list[dict[str, Any]], session_id: str) -> int:
    """Escribe hechos en el vault Obsidian. Retorna count exitoso."""
    os.makedirs(VAULT_DIR, exist_ok=True)

    ts = datetime.now(UTC).strftime("%Y-%m-%d_%H%M%S")
    filepath = os.path.join(VAULT_DIR, f"consolidated_{ts}.md")

    lines = [
        "---",
        "source: consolidator",
        f"session: {session_id}",
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
    lines += ["", "*Generado por consolidator.py · FASE 3 SOUL · Parche 5 v2*"]

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
    """Registra la ejecución en hermes_memory.db::consolidation_log (D-5.3: se preserva)."""
    conn = sqlite3.connect(MEMORY_DB)
    conn.execute(
        "INSERT INTO consolidation_log "
        "(sessions_processed, chunks_read, facts_extracted, "
        "facts_certain, facts_inferred, facts_tentative, "
        "conflicts_detected, errors, duration_ms) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (sessions, chunks, facts_total, facts_certain,
         facts_inferred, facts_tentative, conflicts, errors, duration_ms),
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Guardarraíl de fallos
# ---------------------------------------------------------------------------

def check_failure_count() -> int:
    try:
        with open(FAILURE_TRACK_FILE) as f:
            return int(f.read().strip())
    except (FileNotFoundError, ValueError):
        return 0


def increment_failure() -> int:
    count = check_failure_count() + 1
    with open(FAILURE_TRACK_FILE, "w") as f:
        f.write(str(count))
    return count


def reset_failures() -> None:
    import contextlib

    with contextlib.suppress(FileNotFoundError):
        os.remove(FAILURE_TRACK_FILE)


# ---------------------------------------------------------------------------
# Orquestación
# ---------------------------------------------------------------------------

def run_consolidation(live: bool, max_sessions: int, max_messages: int) -> dict[str, Any]:
    """
    Ejecuta la consolidación completa.

    dry-run (live=False): lee Session DB + watermark, extrae hechos (para
    estimar), NO escribe en Qdrant/Obsidian/consolidation_log/watermark.
    live (live=True): escribe en Qdrant + Obsidian + consolidation_log y
    actualiza el watermark.
    """
    start = time.time()
    failures = check_failure_count()
    if failures >= MAX_CONSECUTIVE_FAILURES:
        logger.error(
            f"Consolidador detenido: {failures} fallos consecutivos. "
            f"Eliminar {FAILURE_TRACK_FILE} para reiniciar."
        )
        return {"status": "halted", "reason": "failure_guardrail"}

    memory_conn = sqlite3.connect(MEMORY_DB)
    try:
        since_id = get_watermark(memory_conn)
        logger.info(
            f"Consolidador iniciado (live={live}, watermark={since_id}, "
            f"max_sessions={max_sessions}, max_messages={max_messages})"
        )

        sessions, new_max_id = get_unconsolidated_sessions(
            since_id, max_sessions, max_messages
        )
        if not sessions:
            logger.info(
                "No hay sesiones nuevas para consolidar (watermark al día)."
            )
            return {"status": "no_work", "sessions": 0, "facts": 0}

        total_msgs = sum(len(s["messages"]) for s in sessions)
        logger.info(
            f"Sesiones a procesar: {len(sessions)} ({total_msgs} mensajes, "
            f"hasta message.id {new_max_id})"
        )

        # Extraer hechos por sesión (prompt = conversación concatenada)
        all_facts: list[dict[str, Any]] = []
        per_session: list[tuple[str, list[dict[str, Any]]]] = []
        for sess in sessions:
            convo = "\n".join(
                f"[{m['role']}] {m['content'][:1500]}"
                for m in sess["messages"]
            )
            if len(convo.strip()) < 20:
                continue
            facts = extract_facts_with_ollama(convo)
            all_facts.extend(facts)
            per_session.append((sess["session_id"], facts))
            logger.info(
                f"  {sess['session_id']}: {len(sess['messages'])} msgs → "
                f"{len(facts)} hechos"
            )

        certain = sum(1 for f in all_facts if f.get("confidence") == "certain")
        inferred = sum(1 for f in all_facts if f.get("confidence") == "inferred")
        tentative = sum(1 for f in all_facts if f.get("confidence") == "tentative")

        duration_ms = int((time.time() - start) * 1000)

        if live:
            indexed = 0
            written = 0
            for session_id, facts in per_session:
                if facts:
                    indexed += index_in_qdrant(facts, session_id)
                    written += write_to_obsidian(facts, session_id)
            log_consolidation(
                sessions=len(sessions),
                chunks=total_msgs,
                facts_total=len(all_facts),
                facts_certain=certain,
                facts_inferred=inferred,
                facts_tentative=tentative,
                conflicts=0,
                errors=None,
                duration_ms=duration_ms,
            )
            # Watermark SIEMPRE después de persistir el log (D-5.1)
            update_watermark(memory_conn, new_max_id, "ok")
            reset_failures()
            logger.info(
                f"LIVE: {indexed} hechos indexados en Qdrant, {written} en "
                f"Obsidian; watermark → {new_max_id}"
            )
        else:
            logger.info(
                f"DRY-RUN: {len(all_facts)} hechos habrían sido indexados "
                f"(certain={certain}, inferred={inferred}, "
                f"tentative={tentative}). Nada escrito; watermark sin cambio."
            )

        return {
            "status": "ok",
            "live": live,
            "sessions": len(sessions),
            "messages": total_msgs,
            "facts": len(all_facts),
            "new_max_id": new_max_id,
        }
    finally:
        memory_conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Consolidador de memoria episódica → semántica (Parche 5 v2)"
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Solo leer y extraer, no escribir (default)",
    )
    mode.add_argument(
        "--live",
        action="store_true",
        help="Ejecutar consolidación real (escribe Qdrant/Obsidian/log/watermark)",
    )
    parser.add_argument(
        "--max-sessions",
        type=int,
        default=MAX_SESSIONS_PER_RUN,
        help=f"Máximo de sesiones por corrida (default: {MAX_SESSIONS_PER_RUN})",
    )
    parser.add_argument(
        "--max-messages",
        type=int,
        default=MAX_MESSAGES_PER_RUN,
        help=f"Máximo de mensajes por corrida (default: {MAX_MESSAGES_PER_RUN})",
    )
    args = parser.parse_args()

    live = args.live  # sin --live, dry-run (default)
    try:
        result = run_consolidation(live, args.max_sessions, args.max_messages)
        logger.info(f"Resultado: {json.dumps(result, default=str)}")
    except Exception as e:
        failures = increment_failure()
        logger.error(
            f"Consolidador falló ({failures}/{MAX_CONSECUTIVE_FAILURES}): {e}"
        )
        if failures >= MAX_CONSECUTIVE_FAILURES:
            logger.error("GUARDARRAÍL: consolidador detenido por fallos consecutivos")


if __name__ == "__main__":
    main()