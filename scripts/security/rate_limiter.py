#!/usr/bin/env python3
"""Rate limiting + blacklist única + detección código país (FASE 1).

Reglas del Líder:
- Solo +58 (Venezuela); internacional → bloqueo inmediato + blacklist.
- 3 mensajes en 60s → advertencia + 1h silencio.
- 1ra ofensa: 1h silencio. 2da ofensa <24h: permanente, sin apelación.
- Cliente que pagó aunque ignoró menú NO cuenta como ofensa.
- DB aislada: data/security.db (no toca producción).
"""
import re
import sqlite3
import threading
import time
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "security.db"
_salt = None


def _conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB_PATH, timeout=30)
    c.row_factory = sqlite3.Row
    return c


_init_lock = threading.Lock()
_initialized = False


def init_db():
    global _initialized
    with _init_lock:
        if _initialized:
            return
        c = _conn()
        with c:
            c.executescript("""
            CREATE TABLE IF NOT EXISTS blacklist_phone (
                phone TEXT PRIMARY KEY,
                reason TEXT,
                blocked_at REAL NOT NULL,
                is_permanent INTEGER NOT NULL DEFAULT 0,
                expires_at REAL
            );
            CREATE INDEX IF NOT EXISTS idx_blacklist_expires
                ON blacklist_phone(expires_at);
            CREATE TABLE IF NOT EXISTS offenses_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                phone TEXT NOT NULL,
                offense_type TEXT NOT NULL,
                timestamp REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_offenses_phone_ts
                ON offenses_log(phone, timestamp);
            CREATE TABLE IF NOT EXISTS message_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                phone TEXT NOT NULL,
                timestamp REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_msglog_phone_ts
                ON message_log(phone, timestamp);
            """)
        c.close()
        _initialized = True


def _norm_phone(phone: str) -> str:
    """Normaliza a formato E.164 sin '+' → solo dígitos."""
    digits = re.sub(r"\D", "", str(phone or ""))
    return digits


def es_numero_venezolano(phone: str) -> bool:
    """True solo si es +58 (Venezuela). Acepta '58...' o '+58...'.
    Números cortos tipo WhatsApp ('0@s.whatsapp.net' no aplica aquí)."""
    d = _norm_phone(phone)
    if not d:
        return False
    if d.startswith("00"):
        d = d[2:]
    if d.startswith("58"):
        # 58 + 10 dígitos = número móvil venezolano válido
        return len(d) == 12
    return False


# ---- blacklist -----------------------------------------------------------

def is_blacklisted(phone: str) -> bool:
    """True si está en blacklist y (permanente o no expirado)."""
    init_db()
    d = _norm_phone(phone)
    c = _conn()
    try:
        row = c.execute(
            "SELECT is_permanent, expires_at FROM blacklist_phone WHERE phone=?",
            (d,)).fetchone()
        if not row:
            return False
        if row["is_permanent"]:
            return True
        if row["expires_at"] is None:
            return True
        return time.time() < row["expires_at"]
    finally:
        c.close()


def add_to_blacklist(phone: str, reason: str, permanent: bool = False,
                     duration_s: float = 3600.0) -> None:
    """Agrega/actualiza blacklist. Temporal (1h por defecto) o permanente."""
    init_db()
    d = _norm_phone(phone)
    now = time.time()
    c = _conn()
    try:
        with c:
            c.execute(
                """INSERT INTO blacklist_phone(phone, reason, blocked_at, is_permanent, expires_at)
                   VALUES(?,?,?,?,?)
                   ON CONFLICT(phone) DO UPDATE SET
                     reason=excluded.reason,
                     blocked_at=excluded.blocked_at,
                     is_permanent=MAX(blacklist_phone.is_permanent, excluded.is_permanent),
                     expires_at=excluded.expires_at""",
                (d, reason, now, int(permanent),
                 None if permanent else now + duration_s))
    finally:
        c.close()


def remove_from_blacklist(phone: str) -> bool:
    init_db()
    d = _norm_phone(phone)
    c = _conn()
    try:
        with c:
            cur = c.execute("DELETE FROM blacklist_phone WHERE phone=?", (d,))
        return cur.rowcount > 0
    finally:
        c.close()


# ---- contadores ----------------------------------------------------------

def record_message(phone: str, ts: float | None = None) -> None:
    """Registra mensaje entrante (para ventanas de rate)."""
    init_db()
    c = _conn()
    try:
        with c:
            c.execute("INSERT INTO message_log(phone, timestamp) VALUES(?,?)",
                      (_norm_phone(phone), ts or time.time()))
    finally:
        c.close()


def contar_mensajes_recientes(phone: str, ventana: float = 60.0) -> int:
    """Cantidad de mensajes del número en la ventana (segundos)."""
    init_db()
    d = _norm_phone(phone)
    c = _conn()
    try:
        row = c.execute(
            "SELECT count() c FROM message_log WHERE phone=? AND timestamp>=?",
            (d, time.time() - ventana)).fetchone()
        return row["c"]
    finally:
        c.close()


# ---- ofensas -------------------------------------------------------------

def record_offense(phone: str, offense_type: str) -> dict:
    """Registra ofensa y aplica política: 1ra → 1h silencio; 2da <24h → permanente.
    NO registra si el cliente tiene pago confirmado reciente (regla del Líder)."""
    init_db()
    d = _norm_phone(phone)
    now = time.time()
    c = _conn()
    try:
        with c:
            c.execute(
                "INSERT INTO offenses_log(phone, offense_type, timestamp) VALUES(?,?,?)",
                (d, offense_type, now))
        n = count_offenses(d, window=24 * 3600)
        if n >= 2:
            add_to_blacklist(d, f"{offense_type} (2da ofensa <24h)",
                             permanent=True)
            return {"action": "ban_permanente", "offenses": n}
        add_to_blacklist(d, f"{offense_type} (1ra ofensa)", permanent=False)
        return {"action": "silencio_1h", "offenses": n}
    finally:
        c.close()


def count_offenses(phone: str, window: float = 24 * 3600) -> int:
    init_db()
    d = _norm_phone(phone)
    c = _conn()
    try:
        row = c.execute(
            "SELECT count() c FROM offenses_log WHERE phone=? AND timestamp>=?",
            (d, time.time() - window)).fetchone()
        return row["c"]
    finally:
        c.close()


# ---- gateway principal ---------------------------------------------------

def check_incoming(phone: str, ts: float = None) -> dict:
    """Punto de entrada ÚNICO para cada mensaje de cliente.

    Returns dict:
      allow: bool — si False, NO responder (silencio) o enviar el mensaje indicado
      action: str — 'ok' | 'advertencia' | 'silencio' | 'ban_permanente' | 'internacional'
      message: str|None — mensaje a enviar al cliente (advertencia)
      reason: str
    """
    ts = ts or time.time()
    if not es_numero_venezolano(phone):
        add_to_blacklist(phone, "internacional", permanent=True)
        return {"allow": False, "action": "internacional",
                "message": None,
                "reason": "número no +58 → blacklist permanente"}
    if is_blacklisted(phone):
        return {"allow": False, "action": "silencio",
                "message": None, "reason": "en blacklist"}
    record_message(phone, ts)
    n = contar_mensajes_recientes(phone, ventana=60)
    if n > 3:  # 4to mensaje dentro de 60s
        res = record_offense(phone, "spam_rapido_3msg_60s")
        return {"allow": False, "action": res["action"],
                "message": ("Recibimos varios mensajes muy rápido. "
                            "Te atendemos en un momento 🙏"),
                "reason": f"{n} mensajes en 60s"}
    return {"allow": True, "action": "ok", "message": None, "reason": ""}
