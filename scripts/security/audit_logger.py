#!/usr/bin/env python3
"""Logs y auditoría estructurados (FASE 5).

Reglas del Líder:
- Eventos: mensaje_entrante, cliente_bloqueado, cliente_observacion,
  ataque_coordinado_detectado, operador_decision, pago_confirmado,
  intento_fallo_acceso.
- NO loguear cliente_fuera_geocerca (va aparte a future_zone_customers).
- Retención: 3 años (no borrar antes).
- Nunca se guarda contenido del mensaje (solo metadatos).
"""
import json
import sqlite3
import time
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "security.db"

RETENTION_YEARS = 3

EVENT_TYPES = {
    "mensaje_entrante",
    "cliente_bloqueado",
    "cliente_observacion",
    "ataque_coordinado_detectado",
    "operador_decision",
    "pago_confirmado",
    "intento_fallo_acceso",
}


def _conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB_PATH, timeout=30)
    c.row_factory = sqlite3.Row
    return c


def init_db():
    c = _conn()
    with c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS security_audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp REAL NOT NULL,
            event_type TEXT NOT NULL,
            phone TEXT,
            ip_origin TEXT,
            details_json TEXT,
            action_taken TEXT,
            operator_decision TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_audit_ts ON security_audit_log(timestamp);
        CREATE INDEX IF NOT EXISTS idx_audit_event ON security_audit_log(event_type, timestamp);
        CREATE INDEX IF NOT EXISTS idx_audit_phone ON security_audit_log(phone, timestamp);
        """)
    c.close()


def log_event(event_type: str, phone: str | None = None, ip_origin: str | None = None,
              details: dict | None = None, action_taken: str | None = None,
              operator_decision: str | None = None) -> int:
    """Registra evento de auditoría. Valida tipo (lista cerrada del Líder).

    'cliente_fuera_geocerca' NO existe como tipo — por diseño se rechaza
    (se almacena aparte en future_zone_customers).
    """
    init_db()
    if event_type == "cliente_fuera_geocerca":
        raise ValueError(
            "cliente_fuera_geocerca NO se loguea (regla del Líder): "
            "usar geofence.check_location → future_zone_customers")
    if event_type not in EVENT_TYPES:
        raise ValueError(f"event_type inválido: {event_type} "
                         f"(permitidos: {sorted(EVENT_TYPES)})")
    import re
    ph = re.sub(r"\D", "", str(phone or "")) or None
    c = _conn()
    try:
        with c:
            cur = c.execute(
                """INSERT INTO security_audit_log
                   (timestamp, event_type, phone, ip_origin, details_json,
                    action_taken, operator_decision)
                   VALUES(?,?,?,?,?,?,?)""",
                (time.time(), event_type, ph, ip_origin,
                 json.dumps(details, ensure_ascii=False) if details else None,
                 action_taken, operator_decision))
            return int(cur.lastrowid or 0)
    finally:
        c.close()


def get_events(event_type: str | None = None, phone: str | None = None,
              since: float | None = None, limit: int = 100) -> list[dict]:
    """Consulta de eventos (para /cliente_info y /stats del operador)."""
    init_db()
    q = "SELECT * FROM security_audit_log WHERE 1=1"
    args: list = []
    if event_type:
        q += " AND event_type=?"; args.append(event_type)
    if phone:
        import re
        q += " AND phone=?"; args.append(re.sub(r"\D", "", str(phone)))
    if since:
        q += " AND timestamp>=?"; args.append(since)
    q += " ORDER BY id DESC LIMIT ?"; args.append(limit)
    c = _conn()
    try:
        rows = c.execute(q, args).fetchall()
        return [dict(r) for r in rows]
    finally:
        c.close()


def purge_expired() -> int:
    """Purga SOLO eventos con más de 3 años (retención). Nunca borra antes."""
    init_db()
    cutoff = time.time() - RETENTION_YEARS * 365 * 24 * 3600
    c = _conn()
    try:
        with c:
            cur = c.execute("DELETE FROM security_audit_log WHERE timestamp < ?", (cutoff,))
            return cur.rowcount
    finally:
        c.close()


def verify_retention() -> dict:
    """Verifica que no hay eventos <3 años siendo purgados (test de retención)."""
    init_db()
    c = _conn()
    try:
        total = c.execute("SELECT count() c FROM security_audit_log").fetchone()["c"]
        old = c.execute(
            "SELECT count() c FROM security_audit_log WHERE timestamp < ?",
            (time.time() - RETENTION_YEARS * 365 * 24 * 3600,)).fetchone()["c"]
        return {"total": total, "older_than_3y": old,
                "retention_years": RETENTION_YEARS}
    finally:
        c.close()
