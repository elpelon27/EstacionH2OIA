#!/usr/bin/env python3
"""Detección de ataques coordinados + modo lockdown (FASE 3).

Límites del Líder (globales):
- 29 msg/min → alerta operador
- 100 msg/hora → alerta operador
- 700 msg/día → STOP: solo responder conocidos + notificar + esperar decisión
- 50+ números nuevos en 10 min → observación
- Spam programado: mensajes idénticos de múltiples números o timing exacto → bloqueo auto
- Salir de lockdown: SOLO confirmación del operador.
"""
import json
import sqlite3
import time
from collections import Counter
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "security.db"

LIMITS = {
    "per_min": 29,
    "per_hour": 100,
    "per_day": 700,
    "new_numbers_10min": 50,
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
        CREATE TABLE IF NOT EXISTS global_message_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone TEXT NOT NULL,
            text_hash TEXT,
            timestamp REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_gm_ts ON global_message_log(timestamp);
        CREATE INDEX IF NOT EXISTS idx_gm_text ON global_message_log(text_hash, timestamp);
        CREATE TABLE IF NOT EXISTS known_numbers (
            phone TEXT PRIMARY KEY,
            first_seen REAL NOT NULL,
            registered INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS security_state (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS attack_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            detected_at REAL NOT NULL,
            attack_type TEXT NOT NULL,
            details_json TEXT,
            resolved INTEGER NOT NULL DEFAULT 0
        );
        """)
    c.close()


# ---- estado --------------------------------------------------------------

def _state_get(key: str, default=None):
    init_db()
    c = _conn()
    try:
        row = c.execute("SELECT value FROM security_state WHERE key=?", (key,)).fetchone()
        return json.loads(row["value"]) if row else default
    finally:
        c.close()


def _state_set(key: str, value):
    init_db()
    c = _conn()
    try:
        with c:
            c.execute(
                "INSERT INTO security_state(key, value, updated_at) VALUES(?,?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
                (key, json.dumps(value), time.time()))
    finally:
        c.close()


def is_lockdown() -> bool:
    return bool(_state_get("lockdown", False))


def set_lockdown(reason: str):
    _state_set("lockdown", True)
    _state_set("lockdown_reason", reason)
    log_attack("lockdown_activado", {"reason": reason})


def release_lockdown(operator: str = "operador"):
    """SOLO el operador llama esto (via /lockdown_release)."""
    _state_set("lockdown", False)
    _state_set("lockdown_reason", None)
    log_attack("lockdown_liberado", {"operator": operator})


# ---- registro ------------------------------------------------------------

def _text_hash(text: str) -> str:
    import hashlib
    return hashlib.sha256((text or "").strip().lower().encode()).hexdigest()[:16]


def record_global_message(phone: str, text: str = "", ts: float | None = None,
                          is_known: bool | None = None):
    """Registra mensaje global + detecta números nuevos.
    Llamar para CADA mensaje entrante (después del rate_limiter)."""
    init_db()
    ts = ts or time.time()
    import re
    d = re.sub(r"\D", "", str(phone or ""))
    c = _conn()
    try:
        with c:
            c.execute("INSERT INTO global_message_log(phone, text_hash, timestamp) VALUES(?,?,?)",
                      (d, _text_hash(text), ts))
            # número nuevo?
            row = c.execute("SELECT phone FROM known_numbers WHERE phone=?", (d,)).fetchone()
            if row is None:
                c.execute("INSERT INTO known_numbers(phone, first_seen) VALUES(?,?)",
                          (d, ts))
                is_new = True
            else:
                is_new = False
            if is_known:
                c.execute("UPDATE known_numbers SET registered=1 WHERE phone=?", (d,))
    finally:
        c.close()
    return {"is_new": is_new}


def mark_registered(phone: str):
    """Marca número como conocido/registrado (cliente con historial)."""
    init_db()
    import re
    d = re.sub(r"\D", "", str(phone or ""))
    c = _conn()
    try:
        with c:
            c.execute("INSERT INTO known_numbers(phone, first_seen, registered) VALUES(?,?,1) "
                      "ON CONFLICT(phone) DO UPDATE SET registered=1",
                      (d, time.time()))
    finally:
        c.close()


def is_known_number(phone: str) -> bool:
    init_db()
    import re
    d = re.sub(r"\D", "", str(phone or ""))
    c = _conn()
    try:
        row = c.execute("SELECT registered FROM known_numbers WHERE phone=?", (d,)).fetchone()
        return bool(row and row["registered"])
    finally:
        c.close()


# ---- métricas ------------------------------------------------------------

_COUNT_TABLES = {"global_message_log": "global_message_log"}  # allowlist fija


def _count_since(table: str, seconds: float) -> int:
    t = _COUNT_TABLES.get(table)  # nunca interpolar input externo
    if t is None:
        raise ValueError(f"tabla no permitida: {table}")
    c = _conn()
    try:
        row = c.execute(
            "SELECT count() c FROM " + t + " WHERE timestamp >= ?",
            (time.time() - seconds,)).fetchone()
        return row["c"]
    finally:
        c.close()


def mensajes_por_minuto() -> int:
    return _count_since("global_message_log", 60)


def mensajes_por_hora() -> int:
    return _count_since("global_message_log", 3600)


def mensajes_por_dia() -> int:
    return _count_since("global_message_log", 86400)


def numeros_nuevos_en_10min() -> int:
    c = _conn()
    try:
        row = c.execute(
            "SELECT count() c FROM known_numbers WHERE first_seen >= ?",
            (time.time() - 600,)).fetchone()
        return row["c"]
    finally:
        c.close()


# ---- detección -----------------------------------------------------------

def log_attack(attack_type: str, details: dict):
    init_db()
    c = _conn()
    try:
        with c:
            c.execute("INSERT INTO attack_events(detected_at, attack_type, details_json) "
                      "VALUES(?,?,?)",
                      (time.time(), attack_type, json.dumps(details)))
    finally:
        c.close()


def recent_attacks(limit: int = 20) -> list[dict]:
    c = _conn()
    try:
        rows = c.execute(
            "SELECT detected_at, attack_type, details_json, resolved FROM attack_events "
            "ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        c.close()


def detect_spam_pattern() -> list[str]:
    """Spam programado: mismo texto_hash desde >=5 números distintos en 10 min."""
    c = _conn()
    try:
        rows = c.execute(
            """SELECT text_hash, count(DISTINCT phone) n
               FROM global_message_log
               WHERE timestamp >= ? AND text_hash IS NOT NULL AND text_hash != ''
               GROUP BY text_hash HAVING n >= 8""",
            (time.time() - 600,)).fetchall()
        return [r["text_hash"] for r in rows]
    finally:
        c.close()


def spam_numbers_for(text_hash: str) -> list[str]:
    c = _conn()
    try:
        rows = c.execute(
            "SELECT DISTINCT phone FROM global_message_log WHERE text_hash=? AND timestamp>=?",
            (text_hash, time.time() - 600)).fetchall()
        return [r["phone"] for r in rows]
    finally:
        c.close()


# ---- gateway principal ---------------------------------------------------

def check_global(phone: str, text: str = "", ts: float | None = None) -> dict:
    """Punto de entrada global (después de rate_limiter.check_incoming).

    Returns:
      allow: bool — False si en lockdown y número no conocido
      action: 'ok' | 'alerta_min' | 'alerta_hora' | 'observacion_nuevos'
              | 'lockdown' | 'spam_bloqueado'
      notify_operator: dict|None — notificación para @Skynet_27_bot
    """
    init_db()
    ts = ts or time.time()
    rec = record_global_message(phone, text, ts)
    notify = None

    if is_lockdown():
        if is_known_number(phone):
            return {"allow": True, "action": "lockdown_conocido", "notify_operator": None}
        return {"allow": False, "action": "lockdown", "notify_operator": None}

    # orden por severidad: dia > hora > minuto
    d = mensajes_por_dia()
    if d >= LIMITS["per_day"]:
        set_lockdown(f"limite diario {d} mensajes alcanzado")
        return {"allow": is_known_number(phone), "action": "lockdown",
                "notify_operator": {"event": "LIMITE_DIARIO_700", "valor": d,
                                    "accion": "solo conocidos + esperar decision operador"}}

    h = mensajes_por_hora()
    if h >= LIMITS["per_hour"]:
        log_attack("limite_hora", {"msg_hora": h})
        return {"allow": True, "action": "alerta_hora",
                "notify_operator": {"event": "limite_100_hora", "valor": h}}

    m = mensajes_por_minuto()
    if m >= LIMITS["per_min"]:
        log_attack("limite_minuto", {"msg_min": m})
        return {"allow": True, "action": "alerta_min",
                "notify_operator": {"event": "limite_29_min", "valor": m}}

    # spam programado: mensajes idénticos multi-número
    spam_hashes = detect_spam_pattern()
    for h in spam_hashes:
        nums = spam_numbers_for(h)
        if len(nums) >= 8:
            log_attack("spam_programado", {"text_hash": h, "numeros": nums})
            notify = {"event": "spam_programado", "numeros": nums}
            # bloqueo automático (import tardío para evitar ciclo)
            from rate_limiter import add_to_blacklist
            for n in nums:
                add_to_blacklist(n, "spam programado (mensaje identico multi-numero)",
                                 permanent=True)
            return {"allow": False, "action": "spam_bloqueado", "notify_operator": notify}

    if numeros_nuevos_en_10min() >= LIMITS["new_numbers_10min"]:
        log_attack("numeros_nuevos_oleada", {"nuevos_10min": numeros_nuevos_en_10min()})
        return {"allow": True, "action": "observacion_nuevos",
                "notify_operator": {"event": "50_numeros_nuevos_10min",
                                    "valor": numeros_nuevos_en_10min()}}
    return {"allow": True, "action": "ok", "notify_operator": None}
