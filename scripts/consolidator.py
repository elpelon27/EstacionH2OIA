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

# ---------------------------------------------------------------------------
# Watermark POR SESIÓN (DT-36, 2026-10-11): el watermark global saltaba a
# max(messages.id) y dejaba mensajes antiguos permanentemente inelegibles.
# Ahora cada sesión trackea su propio último message.id consolidado en
# consolidation_session_watermark. El watermark global se preserva como
# registro de compatibilidad (máximo visto), pero la elegibilidad se decide
# por sesión.
# ---------------------------------------------------------------------------

def ensure_session_watermark_table(memory_conn: sqlite3.Connection) -> None:
    """Crea la tabla de watermarks por sesión si no existe (idempotente)."""
    memory_conn.execute(
        "CREATE TABLE IF NOT EXISTS consolidation_session_watermark ("
        " session_id TEXT PRIMARY KEY,"
        " last_consolidated_id INTEGER NOT NULL,"
        " last_run_at TEXT NOT NULL"
        ")"
    )
    memory_conn.commit()


def get_session_watermarks(memory_conn: sqlite3.Connection) -> dict[str, int]:
    """Lee el mapa session_id → last_consolidated_id (watermarks por sesión)."""
    ensure_session_watermark_table(memory_conn)
    rows = memory_conn.execute(
        "SELECT session_id, last_consolidated_id "
        "FROM consolidation_session_watermark"
    ).fetchall()
    return {r[0]: r[1] for r in rows}


def update_session_watermark(
    memory_conn: sqlite3.Connection,
    session_id: str,
    last_id: int,
) -> None:
    """Actualiza (upsert) el watermark de UNA sesión."""
    ensure_session_watermark_table(memory_conn)
    memory_conn.execute(
        "INSERT INTO consolidation_session_watermark "
        "(session_id, last_consolidated_id, last_run_at) "
        "VALUES (?, ?, ?) "
        "ON CONFLICT(session_id) DO UPDATE SET "
        "last_consolidated_id = excluded.last_consolidated_id, "
        "last_run_at = excluded.last_run_at",
        (session_id, last_id, datetime.now(UTC).isoformat()),
    )
    memory_conn.commit()

# D-5.2: Session DB de Hermes (validada en vivo: 38 sesiones, 25k mensajes).
# No es conversations.db (esa era fs_audit_log y no es la fuente correcta).
# FIX 2026-10-02 (revinculación del alma): el default apuntaba a la instalación
# antigua ~/.hermes/state.db, congelada el 2026-08-13 — el consolidador corría
# "verde" consolidando NADA. Default re-alineado a la instalación viva
# hermes-unified (76 sesiones, mensajes hasta hoy). Watermark reseteado a 0 en
# la misma fecha para re-consolidar la historia desde la BD viva.
SESSION_DB = os.getenv(
    "HERMES_SESSION_DB",
    "/home/skynet/hermes-unified/state.db",
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
    session_watermarks: dict[str, int] | None = None,
    window_start: float | None = None,
    window_end: float | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """
    Lee sesiones con mensajes nuevos (id > watermark DE ESA SESIÓN) de la
    Session DB. DT-36: la elegibilidad se decide por sesión, no por el
    watermark global; los mensajes antiguos de una sesión con mensajes
    nuevos vuelven a ser elegibles.

    session_watermarks: mapa session_id → last_consolidated_id (por sesión).
    Si es None, se usa el watermark global como fallback para TODAS las
    sesiones (comportamiento de compatibilidad con el parche anterior).

    window_start/window_end (epoch float): si se pasan, solo se consideran
    sesiones cuyo started_at cae en la ventana (usado por --backfill).

    Retorna (sesiones, new_max_id). Cada sesión trae sus mensajes de
    conversación (user/assistant, activos, no compactados), recortados al
    guardarraíl de mensajes. new_max_id es el mayor message.id visto.
    """
    marks = session_watermarks if session_watermarks is not None else {}
    conn = sqlite3.connect(f"file:{SESSION_DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        # DT-36: una sesión es elegible si tiene al menos UN mensaje de
        # conversación con id > watermark DE ESA SESIÓN. DISTINCT evita que
        # el JOIN duplique sesiones (una fila por mensaje).
        rows = conn.execute(
            "SELECT DISTINCT s.id, s.source, s.display_name, s.message_count, "
            "s.started_at, s.ended_at "
            "FROM sessions s JOIN messages m ON m.session_id = s.id "
            "WHERE m.role IN (?, ?) AND m.active = 1 "
            "AND m.compacted = 0 AND m.content IS NOT NULL "
            "AND length(m.content) > 0 "
            "AND (? IS NULL OR s.started_at >= ?) "
            "AND (? IS NULL OR s.started_at <= ?) "
            "ORDER BY s.started_at ASC LIMIT ?",
            (
                *CONVERSATION_ROLES,
                window_start, window_start,
                window_end, window_end,
                max_sessions,
            ),
        ).fetchall()
        sessions: list[dict[str, Any]] = []
        new_max_id = since_id
        budget = max_messages
        for row in rows:
            if budget <= 0:
                break
            session_mark = marks.get(row["id"])
            if session_mark is None:
                # Sin entrada por-sesión: fallback al global (o 0 si venimos
                # de un backfill con watermark global ya avanzado).
                session_mark = (
                    0 if window_start is not None else since_id
                )
            msgs = conn.execute(
                "SELECT id, role, content, timestamp FROM messages "
                "WHERE session_id = ? AND id > ? AND role IN (?, ?) "
                "AND active = 1 AND compacted = 0 "
                "AND content IS NOT NULL AND length(content) > 0 "
                "ORDER BY timestamp ASC LIMIT ?",
                (row["id"], session_mark, *CONVERSATION_ROLES, budget),
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
            if len(sessions) >= max_sessions:
                break
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
                # FIX 2026-10-02: qwen2.5:7b con "format":"json" a veces
                # retorna un objeto único en vez de un array. Si es un dict
                # con "fact", lo envolvemos en lista; si no, descartamos.
                if isinstance(facts, dict) and "fact" in facts:
                    facts = [facts]
                else:
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

def run_consolidation(
    live: bool,
    max_sessions: int,
    max_messages: int,
    backfill: tuple[float, float] | None = None,
) -> dict[str, Any]:
    """
    Ejecuta la consolidación completa.

    dry-run (live=False): lee Session DB + watermark, extrae hechos (para
    estimar), NO escribe en Qdrant/Obsidian/consolidation_log/watermark.
    live (live=True): escribe en Qdrant + Obsidian + consolidation_log y
    actualiza el watermark (DT-36: POR SESIÓN; el global queda como máximo
    visto).

    backfill: tupla (window_start, window_end) epoch float. Si se pasa, se
    procesan SOLO sesiones cuyo started_at cae en la ventana, forzando su
    watermark por sesión a 0 (re-consolidación de historia, DT-36).
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
        window_start = backfill[0] if backfill else None
        window_end = backfill[1] if backfill else None
        # DT-36: watermarks por sesión.
        session_marks = get_session_watermarks(memory_conn)
        if backfill:
            # En backfill las sesiones objetivo se fuerzan a consolidar desde 0
            ws: float = backfill[0]
            session_marks = {
                sid: 0 if ws <= _started(sid) else mid
                for sid, mid in session_marks.items()
            }
        logger.info(
            f"Consolidador iniciado (live={live}, watermark={since_id}, "
            f"watermarks_por_sesion={len(session_marks)}, "
            f"backfill={'si' if backfill else 'no'}, "
            f"max_sessions={max_sessions}, max_messages={max_messages})"
        )

        # Watermarks por sesión para la query: en backfill NO se fuerzan a
        # vacío — los lotes previos ya escribieron watermarks por sesión y
        # deben respetarse; las sesiones de la ventana sin entrada usan 0
        # (elegibles). Fuera de backfill es simplemente la tabla.
        marks_for_query = session_marks
        sessions, new_max_id = get_unconsolidated_sessions(
            since_id,
            max_sessions,
            max_messages,
            session_watermarks=marks_for_query,
            window_start=window_start,
            window_end=window_end,
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
            # DT-36: watermark POR SESIÓN (cada sesión hasta su propio max),
            # y el global como registro de compatibilidad (máximo visto).
            for sess in sessions:
                sess_max = max(m["id"] for m in sess["messages"])
                update_session_watermark(memory_conn, sess["session_id"], sess_max)
            update_watermark(memory_conn, max(since_id, new_max_id), "ok")
            reset_failures()
            logger.info(
                f"LIVE: {indexed} hechos indexados en Qdrant, {written} en "
                f"Obsidian; watermarks por sesión actualizados "
                f"({len(sessions)} sesiones); global → {max(since_id, new_max_id)}"
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


def _started(session_id: str) -> float:
    """Epoch de inicio de una sesión (para filtrado de backfill)."""
    conn = sqlite3.connect(f"file:{SESSION_DB}?mode=ro", uri=True)
    try:
        row = conn.execute(
            "SELECT started_at FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        return row[0] if row else 0.0
    finally:
        conn.close()


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
    parser.add_argument(
        "--backfill",
        metavar="START_TS,END_TS",
        default=None,
        help=(
            "Ventana de fechas ISO separadas por coma (ej. "
            "2026-08-26T00:00:00+00:00,2026-09-30T23:59:59+00:00). Fuerza "
            "re-consolidación de las sesiones cuyo started_at cae en la "
            "ventana (watermark por sesión = 0)."
        ),
    )
    args = parser.parse_args()

    backfill = None
    if args.backfill:
        try:
            s_str, e_str = args.backfill.split(",", 1)
            from datetime import datetime as _dt
            ws = _dt.fromisoformat(s_str).timestamp()
            we = _dt.fromisoformat(e_str).timestamp()
            backfill = (ws, we)
        except ValueError as exc:
            parser.error(f"--backfill mal formado: {exc}")

    live = args.live  # sin --live, dry-run (default)
    try:
        result = run_consolidation(
            live, args.max_sessions, args.max_messages, backfill=backfill
        )
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