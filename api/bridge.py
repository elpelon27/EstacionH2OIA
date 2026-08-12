"""
 ============================================================================
 Valentina Bridge — FastAPI ↔ Dify ↔ Meta Cloud API
 Estación H2O · Maracaibo, Venezuela
 ============================================================================

Recibe mensajes de WhatsApp via Meta Cloud API webhook, los envía al Chatflow
de Dify (qwen2.5:7b local), y devuelve la respuesta de Valentina al cliente.

Arquitectura:
    WhatsApp cliente → Meta Cloud API → [este puente :8000] → Dify Chatflow
                                                                  ↓
    WhatsApp cliente ← Meta Graph API ← [este puente :8000] ← respuesta

Despliegue:
    /mnt/ssd_trabajo/hermes-agent/api/bridge.py
    Systemd: hermes-agent.service
    Cloudflare Tunnel: cloudflared-tunnel.service (HTTPS público para webhook Meta)

Seguridad:
    - HMAC-SHA256 verification del header X-Hub-Signature-256 (APP_SECRET)
    - Rate limiting: 30 req/min por teléfono, 100 req/min por IP (slowapi)
    - Log sanitization: teléfonos hasheados con SHA256+salt (nunca en plaintext)
    - Deduplicación: cache de message_id (Meta reintenta si no responde 200 rápido)
    - Conversation persistence: SQLite (phone → dify_conversation_id)

Autor: Prometeo (arquitecto IA Estación H2O)
"""

# Standard library imports
import asyncio
import hashlib
import hmac
import json
import logging
import os
import re
import sqlite3
import sys
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

# System path for local imports
sys.path.insert(0, "/mnt/ssd_trabajo/hermes-agent")

# Third-party imports
import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.responses import Response as RawResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

# Local imports
from api.meta_client import get_meta_client, set_http_client
from src.integrations.r4.webhooks import include_r4_webhooks

try:
    from api.routes.dispatch import router as dispatch_router
except ModuleNotFoundError:
    # When running from /mnt/ssd_trabajo/hermes-agent/api/ (systemd WorkingDirectory)
    import sys

    sys.path.insert(0, "/mnt/ssd_trabajo/hermes-agent")
    from api.routes.dispatch import router as dispatch_router

# Métricas Prometheus
try:
    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False

# Telegram alerts (opcional, no bloquea si no está configurado)
try:
    import telegram

    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False

# P1-2: sdnotify para watchdog systemd
try:
    import sdnotify
except ImportError:
    sdnotify = None


# Helper: convertir EUR a Bs. usando última tasa guardada en fs_tasas_cambio
def _convert_eur_to_bs(eur: float) -> float | None:
    try:
        import sqlite3

        conn = sqlite3.connect(SQLITE_PATH)
        row = conn.execute(
            "SELECT tasa FROM fs_tasas_cambio "
            "WHERE par='EUR/VES' ORDER BY registrado_at DESC LIMIT 1"
        ).fetchone()
        conn.close()
        if row and row[0] > 0:
            return float(round(eur * row[0], 2))
    except Exception:
        pass
    return None


# Financial Shield integration
try:
    from src.agents.financial_agent import get_agent as get_fs_agent

    _fs_agent = None  # Lazy init

    def _get_fs() -> Any:
        global _fs_agent
        if _fs_agent is None:
            _fs_agent = get_fs_agent()
            _fs_agent.init()
            return _fs_agent
except Exception:
    _fs_agent = None

    def _get_fs() -> Any:
        return None


# P1-2: sdnotify para watchdog systemd
try:
    import sdnotify
except ImportError:
    sdnotify = None

# ============================================================================
# Configuración (todas las secrets via variables de entorno)
# ============================================================================

META_ACCESS_TOKEN = os.getenv("META_ACCESS_TOKEN", "")
META_PHONE_NUMBER_ID = os.getenv("META_PHONE_NUMBER_ID", "")
META_APP_SECRET = os.getenv("META_APP_SECRET", "")
META_VERIFY_TOKEN = os.getenv("META_VERIFY_TOKEN", "")
META_API_VERSION = os.getenv("META_API_VERSION", "v25.0")

DIFY_API_URL = os.getenv("DIFY_API_URL", "http://localhost/v1/chat-messages")
DIFY_API_KEY = os.getenv("DIFY_API_KEY", "")

BRIDGE_HOST = os.getenv("BRIDGE_HOST", "0.0.0.0")
BRIDGE_PORT = int(os.getenv("BRIDGE_PORT", "8000"))
LOG_LEVEL = os.getenv("BRIDGE_LOG_LEVEL", "INFO").upper()

RATE_PER_PHONE = int(os.getenv("RATE_LIMIT_PER_PHONE", "30"))
RATE_PER_IP = int(os.getenv("RATE_LIMIT_PER_IP", "100"))

SQLITE_PATH = os.getenv("SQLITE_PATH", "/mnt/ssd_trabajo/hermes-agent/data/conversations.db")

# dispatch.db contiene clients/deliveries/vehicles/zones/gps_tracks
# (usado por skills/dispatcher.py y route_engine.py)
DISPATCH_DB_PATH = os.getenv("DISPATCH_DB_PATH", "/mnt/ssd_trabajo/hermes-agent/data/dispatch.db")

LOG_SALT = os.getenv("LOG_SALT", "change-this-in-production")

# r5: fail-closed si LOG_SALT quedó con default inseguro en producción.
# El .env real define 32 chars reales; si EnvironmentFile no se carga (systemd
# mal configurado) o se ejecuta fuera de systemd, el default es predecible y
# todos los hashes de teléfono son crackeables por tabla arcoiris.
# Excepción: tests/deploy scripts (pueden pasar BRIDGE_ALLOW_INSECURE_SALT=1).
_INSECURE_LOG_SALT = LOG_SALT == "change-this-in-production"
if _INSECURE_LOG_SALT and not os.getenv("BRIDGE_ALLOW_INSECURE_SALT"):
    import sys as _sys

    _sys.stderr.write(
        "\n*** FATAL: LOG_SALT inseguro. Define LOG_SALT en config/.env con "
        'al menos 32 chars aleatorios (ej: python3 -c "import secrets; '
        'print(secrets.token_hex(32))"). Para bypass en dev/tests: '
        "BRIDGE_ALLOW_INSECURE_SALT=1\n\n"
    )
    raise RuntimeError("LOG_SALT default inseguro - abortando startup (fail-closed r5)")

# Telegram (alerts + kill switch). Opcional: si no está configurado, se omite.
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

# r7: Set para mantener referencias a asyncio tasks creados fire-and-forget.
# Evita que el GC cancele el task silenciosamente. Auto-limpia cuando done.
_ASYNCTASKS_REFS: set[asyncio.Task[Any]] = set()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "1663148211")  # Líder por defecto
TELEGRAM_ENABLED = bool(TELEGRAM_BOT_TOKEN) and TELEGRAM_AVAILABLE

# Kill switch: archivo centinela. Si existe, el bridge se detiene.
# P0-3: movido de /tmp a data/ — /tmp es 1777 (writable por todos), data/ es del user skynet.
# Persiste tras reboot (antes se perdía). 0600 al crear (ver telegram_bot.py cmd_stop).
KILL_SWITCH_FILE = os.getenv(
    "KILL_SWITCH_FILE", "/mnt/ssd_trabajo/hermes-agent/data/valentina.kill"
)

# Cliente HTTP reutilizable (connection pooling)
_http_client: httpx.AsyncClient | None = None
_telegram_bot = None

# Cache de deduplicación (message_id → timestamp). En memoria, 5 min TTL.
# En producción con >1000 msg/día, migrar a Redis. Para Estación H2O basta.
_seen_messages: dict[str, float] = {}
DEDUP_TTL_SECONDS = 300  # 5 minutos

# Hora de arranque para uptime
START_TIME = time.time()

# P0-B FIX: Background task reference for recovery scan
_recovery_task: asyncio.Task[Any] | None = None

# State tracking: último total correcto por teléfono (para corregir en mensajes posteriores)
# phone_hash -> {"total": float, "qty_bot": int, "qty_hielo": int}
_last_order_totals: dict[str, dict[str, float | int]] = {}

# --- Horario laboral (America/Caracas UTC-4) ---
# Publicado al cliente: "Lunes a Sábado, 8:00 AM - 6:00 PM"
# El .env interno decía 07:40 pero el prompt oficial publica 8:00 AM.
# Usamos el horario publicado al cliente.
BUSINESS_HOURS_START = int(os.getenv("BUSINESS_HOURS_START", "8"))  # 8 AM
BUSINESS_HOURS_END = int(os.getenv("BUSINESS_HOURS_END", "18"))  # 6 PM
BUSINESS_HOURS_DAYS = os.getenv(
    "BUSINESS_HOURS_DAYS", "1,2,3,4,5,6"
)  # Lun-Sáb (1=Lun, 6=Sáb, 0=Dom)
CARACAS_TZ = timezone(timedelta(hours=-4))  # America/Caracas UTC-4


# Mensaje fuera de horario (verbatim del System Prompt v4)
def _get_out_of_hours_message() -> str:
    """Mensaje dinámico según qué tan cerca está de la apertura."""
    now = datetime.now(CARACAS_TZ)
    day = now.weekday() + 1
    if day == 7:
        day = 0
    open_days = [int(d) for d in BUSINESS_HOURS_DAYS.split(",")]

    # Si es día de apertura y falta menos de 30 min
    if day in open_days:
        minutes_to_open = (BUSINESS_HOURS_START * 60) - (now.hour * 60 + now.minute)
        if 0 < minutes_to_open <= 30:
            return (
                f"¡Hola! 👋 Abrimos en {minutes_to_open} minutos. "
                f"Por favor escríbame a las {BUSINESS_HOURS_START}:00am. ¡Gracias! 💧"
            )

    # Si es día de apertura pero falta más de 30 min
    if day in open_days and now.hour < BUSINESS_HOURS_START:
        return (
            f"¡Hola! 👋 Ahora mismo estamos cerrados 🌙 "
            f"Abrimos a las {BUSINESS_HOURS_START}:00am. "
            f"He registrado tu mensaje y te responderemos al abrir. ¡Gracias! 💧"
        )

    # Si es después del cierre o día no laboral
    return (
        "¡Hola! 👋 Ahora mismo estamos cerrados 🌙 Volvemos a las 8:00 AM (Lun-Sáb, 8am-6pm).\n"
        "He registrado tu mensaje y lo programaremos para la primera hora de mañana. "
        "Un asesor te contactará para confirmar. ¡Gracias! 💧"
    )


def _is_within_business_hours() -> bool:
    """
    Verifica si el momento actual (America/Caracas) está dentro del horario laboral.
    Determinístico — no depende del LLM.
    """
    now_caracas = datetime.now(CARACAS_TZ)
    day = now_caracas.weekday() + 1  # Python: Lun=0, Sáb=5, Dom=6 → nosotros: Lun=1, Sáb=6, Dom=0
    if day == 7:  # Domingo en Python es 6 → nosotros lo mapeamos a 0
        day = 0
    open_days = [int(d) for d in BUSINESS_HOURS_DAYS.split(",")]
    if day not in open_days:
        return False
    hour = now_caracas.hour + now_caracas.minute / 60
    return BUSINESS_HOURS_START <= hour < BUSINESS_HOURS_END


# ============================================================================
# Métricas Prometheus — Lazy initialization para evitar duplicados en tests
# ============================================================================


def _get_prometheus_metrics():
    """Crear o retornar métricas Prometheus existentes (lazy singleton).

    Evita ValueError: Duplicated timeseries cuando el módulo se importa
    múltiples veces en tests (pytest reloads).
    """
    if not PROMETHEUS_AVAILABLE:
        # Stubs si prometheus_client no está instalado
        class _Stub:
            def labels(self, *a: Any, **kw: Any) -> "_Stub":
                return self

            def inc(self, *a: Any, **kw: Any) -> None:
                pass

            def observe(self, *a: Any, **kw: Any) -> None:
                pass

            def set(self, *a: Any, **kw: Any) -> None:
                pass

        return {
            "MESSAGES_TOTAL": _Stub(),
            "RESPONSE_TIME": _Stub(),
            "DIFY_CALLS": _Stub(),
            "META_SEND": _Stub(),
            "ORDERS_TOTAL": _Stub(),
            "ESCALATIONS_TOTAL": _Stub(),
            "ACTIVE_CONVERSATIONS": _Stub(),
            "DEDUP_HITS": _Stub(),
        }

    from prometheus_client import REGISTRY, Counter, Gauge, Histogram

    # Nombres de métricas para chequear existencia
    metric_names = {
        "MESSAGES_TOTAL": "valentina_messages_total",
        "RESPONSE_TIME": "valentina_response_time_seconds",
        "DIFY_CALLS": "valentina_dify_calls_total",
        "META_SEND": "valentina_meta_send_total",
        "ORDERS_TOTAL": "valentina_orders_total",
        "ESCALATIONS_TOTAL": "valentina_escalations_total",
        "ACTIVE_CONVERSATIONS": "valentina_active_conversations",
        "DEDUP_HITS": "valentina_dedup_hits_total",
    }

    metrics = {}
    for attr_name, metric_name in metric_names.items():
        # Buscar si ya existe en el registry
        existing = None
        for collector in REGISTRY._collector_to_names:
            if metric_name in REGISTRY._collector_to_names[collector]:
                existing = collector
                break

        if existing:
            metrics[attr_name] = existing
        else:
            # Crear nueva métrica
            if attr_name == "MESSAGES_TOTAL":
                metrics[attr_name] = Counter(
                    metric_name,
                    "Mensajes entrantes de WhatsApp",
                    ["status"],  # ok, ignored, error, duplicate
                )
            elif attr_name == "RESPONSE_TIME":
                metrics[attr_name] = Histogram(
                    metric_name,
                    "Tiempo total de respuesta (webhook → Meta send)",
                    buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0),
                )
            elif attr_name == "DIFY_CALLS":
                metrics[attr_name] = Counter(
                    metric_name,
                    "Llamadas a Dify Chatflow",
                    ["status"],  # ok, error, timeout
                )
            elif attr_name == "META_SEND":
                metrics[attr_name] = Counter(
                    metric_name,
                    "Envíos a Meta Graph API",
                    ["status"],  # ok, error
                )
            elif attr_name == "ORDERS_TOTAL":
                metrics[attr_name] = Counter(
                    metric_name,
                    "Pedidos confirmados por Valentina",
                )
            elif attr_name == "ESCALATIONS_TOTAL":
                metrics[attr_name] = Counter(
                    metric_name,
                    "Escalamientos a humano",
                )
            elif attr_name == "ACTIVE_CONVERSATIONS":
                metrics[attr_name] = Gauge(
                    metric_name,
                    "Conversaciones activas (últimas 24h)",
                )
            elif attr_name == "DEDUP_HITS":
                metrics[attr_name] = Counter(
                    metric_name,
                    "Mensajes duplicados ignorados",
                )

    return metrics


# Inicializar métricas (lazy - se ejecuta una sola vez al importar)
_prom_metrics = _get_prometheus_metrics()
MESSAGES_TOTAL = _prom_metrics["MESSAGES_TOTAL"]
RESPONSE_TIME = _prom_metrics["RESPONSE_TIME"]
DIFY_CALLS = _prom_metrics["DIFY_CALLS"]
META_SEND = _prom_metrics["META_SEND"]
ORDERS_TOTAL = _prom_metrics["ORDERS_TOTAL"]
ESCALATIONS_TOTAL = _prom_metrics["ESCALATIONS_TOTAL"]
ACTIVE_CONVERSATIONS = _prom_metrics["ACTIVE_CONVERSATIONS"]
DEDUP_HITS = _prom_metrics["DEDUP_HITS"]


# ============================================================================
# Logging con sanitización de PII
# ============================================================================


class SanitizingFormatter(logging.Formatter):
    """Reemplaza números de teléfono por hash SHA256+salt en los logs."""

    # P1-1: Regex preciso con lookarounds — solo matchea teléfono venezolano
    # real (+58XXXXXXXXXX o 58XXXXXXXXXX o XXXXXXXXXX si empieza con 412/414/416/424/426).
    # Antes: r"\+?58?\d{10,15}" sin anchors → matcheaba IDs, timestamps, IPs.
    # Ahora: requiere que NO haya dígitos antes ni después (boundary de dígitos).
    PHONE_REGEX = __import__("re").compile(r"(?<!\d)\+?58\d{10}(?!\d)")

    def format(self, record: logging.LogRecord) -> str:
        msg = super().format(record)

        # Hashear cualquier cosa que parezca un teléfono venezolano
        def _hash_phone(match: re.Match[str]) -> str:
            phone = match.group(0)
            h = hashlib.sha256(f"{LOG_SALT}:{phone}".encode()).hexdigest()[:12]
            return f"phone:{h}"

        return str(self.PHONE_REGEX.sub(_hash_phone, msg))


logger = logging.getLogger("valentina_bridge")
logger.setLevel(LOG_LEVEL)
_handler = logging.StreamHandler()
_handler.setFormatter(
    SanitizingFormatter(
        fmt="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
)
logger.addHandler(_handler)


# ============================================================================
# SQLite — persistencia de conversation_id por teléfono
# ============================================================================


def _init_db() -> None:
    os.makedirs(os.path.dirname(SQLITE_PATH), exist_ok=True)
    conn = sqlite3.connect(SQLITE_PATH)
    # r2/r3: foreign_keys + WAL activados en init (persiste en archivo)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS conversations (
            phone_hash TEXT PRIMARY KEY,
            dify_conversation_id TEXT NOT NULL,
            last_seen REAL NOT NULL,
            messages_count INTEGER DEFAULT 1
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone_hash TEXT NOT NULL,
            product_description TEXT,
            address TEXT,
            total_eur REAL,
            status TEXT DEFAULT 'pending',
            created_at REAL NOT NULL
        )
        """
    )
    # r1: dispatch_queue table (estaba ausente del _init_db original).
    # _send_to_dispatch_queue (linea 796) la usa INSERT pero la tabla jamas
    # era creada aqui -> regenerar BD = explosion sqlite3.OperationalError.
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS dispatch_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fs_pedido_id INTEGER,
            cliente_nombre TEXT,
            cliente_telefono TEXT,
            producto_desc TEXT,
            total_eur REAL,
            total_bs REAL,
            metodo_pago TEXT,
            gps_lat REAL,
            gps_lng REAL,
            gps_url TEXT,
            direccion TEXT,
            chofer_asignado TEXT,
            estado TEXT DEFAULT 'pending',
            enviado_at TEXT,
            respondido_at TEXT,
            creado_at TEXT NOT NULL
        )
        """
    )
    # Indices para queries frecuentes (analytics 7am, dispatcher polling)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_phone_hash ON orders(phone_hash)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_created_at ON orders(created_at)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_dispatch_queue_estado ON dispatch_queue(estado, creado_at)"
    )

    # P0-1: FSM persistente — tabla conversation_state.
    # Persiste _conversation_state y _last_order_totals en SQLite.
    # Si uvicorn muere, los estados awaiting_payment/awaiting_confirmation
    # se recuperan al reiniciar (lazy load desde esta tabla).
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS conversation_state (
            phone_hash TEXT PRIMARY KEY,
            state_json TEXT NOT NULL,
            total REAL,
            qty_bot INTEGER,
            qty_hielo INTEGER,
            updated_at REAL NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_conv_state_updated ON conversation_state(updated_at)"
    )
    conn.commit()
    conn.close()
    logger.info("SQLite inicializado en %s (WAL + foreign_keys ON)", SQLITE_PATH)


def _get_db_with_fk(path: str = SQLITE_PATH, row_factory: bool = False) -> sqlite3.Connection:
    """Abre conexion SQLite con PRAGMA foreign_keys = ON (per-conexion, no persiste).
    r2: Usa este helper en TODA insercion/actualizacion que dependa de FK enforcement.
    """
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    if row_factory:
        conn.row_factory = sqlite3.Row
    return conn


def _phone_hash(phone: str) -> str:
    """Hash determinístico del teléfono para almacenar sin exponer PII."""
    return hashlib.sha256(f"{LOG_SALT}:{phone}".encode()).hexdigest()[:32]


def _get_conversation_id(phone: str) -> str | None:
    conn = sqlite3.connect(SQLITE_PATH)
    row = conn.execute(
        "SELECT dify_conversation_id FROM conversations WHERE phone_hash = ?",
        (_phone_hash(phone),),
    ).fetchone()
    conn.close()
    return row[0] if row else None


def _save_conversation_id(phone: str, conv_id: str) -> None:
    ph = _phone_hash(phone)
    conn = sqlite3.connect(SQLITE_PATH)
    conn.execute(
        """
        INSERT INTO conversations (phone_hash, dify_conversation_id, last_seen, messages_count)
        VALUES (?, ?, ?, 1)
        ON CONFLICT(phone_hash) DO UPDATE SET
            dify_conversation_id = excluded.dify_conversation_id,
            last_seen = excluded.last_seen,
            messages_count = messages_count + 1
        """,
        (ph, conv_id, time.time()),
    )
    conn.commit()
    conn.close()


# ============================================================================
# Rate limiting
# ============================================================================

def _get_phone_key(request: Request) -> str:
    """Extrae el teléfono del payload de Meta para rate limiting por teléfono.
    Meta envía el teléfono en contacts[0].wa_id dentro del JSON body.
    """
    # La key function se ejecuta ANTES de leer el body, así que no podemos
    # parsear el JSON aquí. Usamos una aproximación: header X-Forwarded-For
    # o IP como fallback. El rate limit real por teléfono se hace DENTRO
    # del handler después de parsear.
    return get_remote_address(request)


def _get_rate_limit_key(request: Request) -> tuple[str, str]:
    """Retorna (ip_key, phone_key) para dual rate limiting.
    El phone_key se resuelve dentro del handler (ver _check_phone_rate_limit).
    """
    ip = get_remote_address(request)
    return ip, ""


limiter = Limiter(key_func=_get_phone_key, default_limits=[])


# ============================================================================
# Rate limiting helpers (phone-based)
# ============================================================================

# In-memory rate limit store for phone-based limiting
# Key: phone_hash, Value: list of timestamps
_phone_rate_limit_store: dict[str, list[float]] = {}
_phone_rate_limit_lock = asyncio.Lock()


async def _check_phone_rate_limit(phone: str) -> bool:
    """Verifica rate limit por teléfono (30 req/min por defecto).
    Returns True si está dentro del límite, False si excedido.
    """
    if not phone:
        return True  # Sin teléfono no podemos limitar, permitir

    ph_hash = _phone_hash(phone)
    now = time.time()
    window_start = now - 60  # 1 minuto

    async with _phone_rate_limit_lock:
        # Limpiar timestamps antiguos
        if ph_hash in _phone_rate_limit_store:
            _phone_rate_limit_store[ph_hash] = [
                ts for ts in _phone_rate_limit_store[ph_hash] if ts > window_start
            ]
        else:
            _phone_rate_limit_store[ph_hash] = []

        # Verificar límite
        if len(_phone_rate_limit_store[ph_hash]) >= RATE_PER_PHONE:
            logger.warning(
                "Rate limit por teléfono excedido: phone:%s (límite %d/min)",
                ph_hash[:8],
                RATE_PER_PHONE,
            )
            MESSAGES_TOTAL.labels(status="rate_limited_phone").inc()
            return False

        # Registrar request
        _phone_rate_limit_store[ph_hash].append(now)
        return True


# ============================================================================
# Payload validation / sanitization
# ============================================================================


def _validate_meta_payload(data: dict[str, Any]) -> bool:
    """Valida estructura básica del payload de Meta Cloud API.
    Previene procesamiento de payloads malformados o ataques de inyección.
    """
    # Estructura mínima esperada: entry[0].changes[0].value
    try:
        entry = data.get("entry", [])
        if not entry or not isinstance(entry, list):
            return False

        changes = entry[0].get("changes", [])
        if not changes or not isinstance(changes, list):
            return False

        value = changes[0].get("value", {})
        if not value or not isinstance(value, dict):
            return False

        # Debe tener contacts array
        contacts = value.get("contacts", [])
        if not contacts or not isinstance(contacts, list):
            return False

        contact = contacts[0]
        if not isinstance(contact, dict):
            return False

        # wa_id es requerido para identificar al remitente
        wa_id = contact.get("wa_id")
        if not wa_id or not isinstance(wa_id, str):
            return False

        # Validación básica de wa_id (solo dígitos, longitud razonable)
        if not wa_id.isdigit() or len(wa_id) < 8 or len(wa_id) > 15:
            return False

        # Si tiene messages, validar estructura básica
        messages = value.get("messages", [])
        if messages:
            if not isinstance(messages, list):
                return False
            msg = messages[0]
            if not isinstance(msg, dict):
                return False
            # msg.id es requerido
            msg_id = msg.get("id")
            if not msg_id or not isinstance(msg_id, str):
                return False
            # msg.type es requerido
            msg_type = msg.get("type")
            if not msg_type or not isinstance(msg_type, str):
                return False

        return True

    except (KeyError, IndexError, AttributeError, TypeError):
        return False


def _sanitize_input_text(text: str) -> str:
    """Sanitiza texto de entrada del usuario (WhatsApp).
    - Remueve caracteres de control (excepto \n, \r, \t)
    - Limita longitud máxima
    - Escapa secuencias potencialmente peligrosas para logging/SQL
    """
    if not text:
        return ""

    # Limitar longitud (WhatsApp max es ~4096, nosotros ponemos límite conservador)
    max_len = 2000
    if len(text) > max_len:
        text = text[:max_len] + "… [truncado]"

    # Remover caracteres de control peligrosos (ASCII 0-31 excepto \n \r \t)
    # \x00-\x08, \x0b-\x0c, \x0e-\x1f
    text = "".join(
        ch for ch in text if ord(ch) >= 32 or ch in ("\n", "\r", "\t")
    )

    # Normalizar whitespace excesivo
    import re
    text = re.sub(r"[\s]+", " ", text).strip()

    return text


# ============================================================================
# Meta Cloud API helpers
# ============================================================================


def _verify_meta_signature(raw_body: bytes, signature_header: str) -> bool:
    """Verifica HMAC-SHA256 del body con APP_SECRET de Meta."""
    if not META_APP_SECRET:
        logger.error("META_APP_SECRET no configurado — rechazando webhook")
        return False
    if not signature_header:
        return False
    expected = "sha256=" + hmac.new(META_APP_SECRET.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header)


async def _send_whatsapp_message(phone: str, text: str) -> bool:
    """Envía un mensaje de texto via Meta Graph API."""
    if not META_ACCESS_TOKEN or not META_PHONE_NUMBER_ID:
        logger.error("META_ACCESS_TOKEN o META_PHONE_NUMBER_ID no configurados")
        return False
    url = f"https://graph.facebook.com/{META_API_VERSION}/{META_PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {META_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": phone,
        "type": "text",
        "text": {"body": text, "preview_url": False},
    }
    try:
        assert _http_client is not None, "http client not initialized"
        resp = await _http_client.post(url, headers=headers, json=payload, timeout=10)
        if resp.status_code == 200:
            logger.info("Mensaje enviado a phone:%s (len=%d)", _phone_hash(phone)[:8], len(text))
            return True
        logger.error("Meta send API error %d: %s", resp.status_code, resp.text[:200])
        return False
    except httpx.HTTPError as e:
        logger.error("Error enviando a Meta: %s", e)
        return False


# ============================================================================
# Mensajes interactivos (List Messages + Quick Reply Buttons) — Meta Cloud API
# ============================================================================


async def _send_whatsapp_interactive(
    phone: str,
    body_text: str,
    interactive_type: str,
    buttons: list[dict[str, Any]] | None = None,
    list_sections: list[dict[str, Any]] | None = None,
    button_text: str = "Ver opciones",
    header_text: str | None = None,
    footer_text: str | None = None,
) -> bool:
    """
    Envía un mensaje interactivo (list o button) via Meta Graph API.

    Args:
        phone: teléfono del cliente
        body_text: texto principal del mensaje
        interactive_type: "list" o "button"
        buttons: para "button" — lista de dicts {"id": str, "title": str} (máx 3)
        list_sections: para "list" — lista de secciones con rows
        button_text: para "list" — texto del botón "Ver opciones"
        header_text: título opcional (máx 60 chars)
        footer_text: pie opcional (máx 60 chars)
    """
    if not META_ACCESS_TOKEN or not META_PHONE_NUMBER_ID:
        logger.error("META_ACCESS_TOKEN o META_PHONE_NUMBER_ID no configurados")
        return False

    url = f"https://graph.facebook.com/{META_API_VERSION}/{META_PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {META_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }

    interactive = {"type": interactive_type, "body": {"text": body_text}}

    if header_text:
        interactive["header"] = {"type": "text", "text": header_text[:60]}
    if footer_text:
        interactive["footer"] = {"text": footer_text[:60]}

    if interactive_type == "button":
        # Quick Reply: máximo 3 botones
        interactive["action"] = {
            "buttons": [
                {
                    "type": "reply",
                    "reply": {"id": b["id"], "title": b["title"][:20]},
                }
                for b in (buttons or [])[:3]
            ]
        }
    elif interactive_type == "list":
        interactive["action"] = {
            "button": button_text[:20],
            "sections": list_sections or [],
        }
    else:
        logger.error("Tipo interactivo no soportado: %s", interactive_type)
        return False

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": phone,
        "type": "interactive",
        "interactive": interactive,
    }

    try:
        assert _http_client is not None, "http client not initialized"
        resp = await _http_client.post(url, headers=headers, json=payload, timeout=10)
        if resp.status_code == 200:
            logger.info(
                "Mensaje interactivo (%s) enviado a phone:%s",
                interactive_type,
                _phone_hash(phone)[:8],
            )
            return True
        logger.error(
            "Meta send interactive error %d: %s",
            resp.status_code,
            resp.text[:200],
        )
        return False
    except httpx.HTTPError as e:
        logger.error("Error enviando interactivo a Meta: %s", e)
        return False


def _detect_message_type(answer: str) -> dict[str, Any]:
    """
    Analiza la respuesta de Valentina (Dify) y decide qué tipo de
    mensaje interactivo enviar (si aplica).

    Returns:
        dict con claves:
            - type: "text" | "list" | "button"
            - body: texto a mostrar al cliente (puede ser recortado)
            - buttons: para "button" — lista de botones
            - list_sections: para "list" — secciones con rows
            - button_text: para "list" — texto del botón principal
    """
    if not answer:
        return {"type": "text"}

    ans_lower = answer.lower()

    # --- MENÚ PRINCIPAL (5 opciones) → List Message ---
    # Detecta: "1️⃣ Recarga de botellones" + "2️⃣" + "5️⃣"
    if "1️⃣" in answer and "5️⃣" in answer and ("opción" in ans_lower or "servirle" in ans_lower):
        # Body limpio sin la lista de números (la lista va en las rows)
        body = "¡Buen día! 👋 Soy Valentina de Estación H2O.\n¿En qué puedo servirle hoy?"
        return {
            "type": "list",
            "body": body,
            "button_text": "📋 Ver opciones",
            "list_sections": [
                {
                    "title": "Menú principal",
                    "rows": [
                        {
                            "id": "1",
                            "title": "Recarga de botellones",
                            "description": "Agua €1.00 c/u",
                        },
                        {"id": "2", "title": "Pedido de hielo", "description": "Bolsas €1.20 c/u"},
                        {"id": "3", "title": "Pedido combinado", "description": "Agua + hielo"},
                        {"id": "4", "title": "Consultar estado", "description": "Mi pedido"},
                        {"id": "5", "title": "Otra consulta", "description": "Hablemos"},
                    ],
                }
            ],
        }

    # --- ¿Cuántos botellones? → Quick Reply con cantidades (mínimo 3) ---
    if "cuántos botellones" in ans_lower and "cuántas bolsas" not in ans_lower:
        return {
            "type": "button",
            "body": answer.split(".")[0] + ".",
            "buttons": [
                {"id": "3", "title": "3️⃣ 3 botellones"},
                {"id": "4", "title": "4️⃣ 4 botellones"},
                {"id": "custom_qty", "title": "✍️ Otra cantidad"},
            ],
        }

    # --- ¿Cuántas bolsas de hielo? → Quick Reply con cantidades (mínimo 3) ---
    if "cuántas bolsas" in ans_lower and "cuántos botellones" not in ans_lower:
        return {
            "type": "button",
            "body": answer.split(".")[0] + ".",
            "buttons": [
                {"id": "3", "title": "3️⃣ 3 bolsas"},
                {"id": "4", "title": "4️⃣ 4 bolsas"},
                {"id": "custom_qty", "title": "✍️ Otra cantidad"},
            ],
        }

    # --- ¿Cuántos botellones Y cuántas bolsas? (combinado) → combos frecuentes ---
    if "cuántos botellones" in ans_lower and "cuántas bolsas" in ans_lower:
        return {
            "type": "button",
            "body": answer.split(".")[0] + ".",
            "buttons": [
                {"id": "3 botellones y 2 bolsas", "title": "3️⃣ agua + 2️⃣ hielo"},
                {"id": "4 botellones y 3 bolsas", "title": "4️⃣ agua + 3️⃣ hielo"},
                {"id": "custom_combo", "title": "✍️ Otra combinación"},
            ],
        }

    # --- ¿Cómo desea pagar? → Quick Reply Pago Móvil / Efectivo ---
    # Detectar múltiples variantes del mensaje de pago
    pago_keywords = [
        "cómo desea pagar",
        "como desea pagar",
        "desea pagar",
        "método de pago",
        "metodo de pago",
        "forma de pago",
        "1️⃣ pago móvil",
        "1️⃣ pago movil",
        "2️⃣ efectivo",
    ]
    has_pago_question = any(kw in ans_lower for kw in pago_keywords)
    has_pago_options = (
        "pago móvil" in ans_lower or "pago movil" in ans_lower or "efectivo" in ans_lower
    )
    if has_pago_question and has_pago_options:
        return {
            "type": "button",
            "body": answer.split("¿Cómo")[0].strip() + "\n\n¿Cómo desea pagar?",
            "buttons": [
                {"id": "1", "title": "💳 Pago Móvil"},
                {"id": "2", "title": "💵 Efectivo"},
            ],
        }

    # --- Después de dar datos de cuenta → Quick Reply "Ya pagué" ---
    if "envíe el comprobante" in ans_lower or "envie el comprobante" in ans_lower:
        return {
            "type": "button",
            "body": answer,
            "buttons": [
                {"id": "ya_pague", "title": "✅ Ya pagué"},
            ],
        }

    # --- "custom_qty" respondido por Dify (pidiendo número) ---
    # Si Dify dice "escriba la cantidad" o similar, sin botones
    if "escriba la cantidad" in ans_lower or "escribe la cantidad" in ans_lower:
        return {"type": "text"}  # cliente debe escribir número

    # --- Default: texto plano ---
    return {"type": "text"}


async def _call_dify(query: str, phone: str, conv_id: str | None) -> dict[str, Any] | None:
    """Llama al Chatflow de Dify y devuelve {answer, conversation_id}."""
    if not DIFY_API_KEY:
        logger.error("DIFY_API_KEY no configurada")
        return None
    headers = {
        "Authorization": f"Bearer {DIFY_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "inputs": {},
        "query": query,
        "response_mode": "blocking",
        "user": f"wa_{_phone_hash(phone)[:16]}",
    }
    if conv_id:
        payload["conversation_id"] = conv_id
    try:
        assert _http_client is not None, "http client not initialized"
        resp = await _http_client.post(DIFY_API_URL, headers=headers, json=payload, timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            return {
                "answer": data.get("answer", ""),
                "conversation_id": data.get("conversation_id", ""),
            }
        logger.error("Dify error %d: %s", resp.status_code, resp.text[:300])
        return None
    except httpx.HTTPError as e:
        logger.error("Error llamando a Dify: %s", e)
        return None


# ============================================================================
# Deduplicación
# ============================================================================


def _is_duplicate(message_id: str) -> bool:
    """True si el message_id ya fue procesado en los últimos 5 min."""
    now = time.time()
    # Limpieza perezosa
    expired = [mid for mid, ts in _seen_messages.items() if now - ts > DEDUP_TTL_SECONDS]
    for mid in expired:
        del _seen_messages[mid]
    if message_id in _seen_messages:
        return True
    _seen_messages[message_id] = now
    return False


# ============================================================================
# Telegram — alertas y kill switch
# ============================================================================


async def _send_telegram(message: str, parse_mode: str = "HTML") -> None:
    """Envía un mensaje de alerta al chat_id del Líder. No bloquea si falla."""
    if not TELEGRAM_ENABLED:
        return
    try:
        if _telegram_bot is None:
            return
        await _telegram_bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=message,
            parse_mode=parse_mode,
        )
    except Exception as e:
        logger.warning("No se pudo enviar alerta Telegram: %s", e)


async def _alert_critical(title: str, detail: str) -> None:
    """Alerta crítica → Telegram + log error."""
    logger.error("🚨 CRÍTICA: %s — %s", title, detail)
    await _send_telegram(
        f"🚨 <b>{title}</b>\n\n<code>{detail[:500]}</code>\n\n⏰ {datetime.now(UTC).isoformat()}"
    )


def _is_kill_switch_active() -> bool:
    """True si el archivo centinela existe (kill switch activado via Telegram)."""
    return os.path.exists(KILL_SWITCH_FILE)


# ============================================================================
# Parser de respuestas de Valentina → estructura de pedido para Google Sheets
# ============================================================================


# ============================================================================
# BRIDGE DETERMINÍSTICO — Máquina de estados sin Dify (latencia <1s)
# ============================================================================

# State tracking por teléfono: phone_hash -> estado de conversación
_conversation_state: dict[str, dict[str, Any]] = {}

# Precios oficiales
PRECIO_BOTELLON = 1.00
PRECIO_HIELO = 1.20

# Datos bancarios
BANK_DATA = (
    "Perfecto. Le comparto los datos para su pago:\n\n"
    "🏦 Banco: R4, Banco Microfinanciero 0169\n"
    "💳 Cuenta: 0169 0010 9710 0159 1583\n"
    "🆔 RIF: J-506356899\n"
    "📱 Pago Móvil: +58 412-2560721\n"
    "💰 Total: €{total:.2f} (Bs. {total_bs:.2f})\n\n"
    "Envíe el comprobante de pago por aquí. ¡Gracias! 💧"
)

OUT_OF_HOURS_MSG = (
    "¡Hola! 👋 Ahora mismo estamos cerrados 🌙 Volvemos a las 8:00 AM (Lun-Sáb, 8am-6pm)."
)


def _get_state(ph_hash: str) -> dict[str, Any]:
    """Obtiene el estado conversacional del teléfono.
    P0-1: Lazy load desde SQLite con cache en memoria."""
    cached = _conversation_state.get(ph_hash)
    if cached is not None:
        return cached
    try:
        conn = sqlite3.connect(SQLITE_PATH)
        row = conn.execute(
            "SELECT state_json, total, qty_bot, qty_hielo "
            "FROM conversation_state WHERE phone_hash = ?",
            (ph_hash,),
        ).fetchone()
        conn.close()
        if row and row[0]:
            state = json.loads(row[0])
            _conversation_state[ph_hash] = state
            logger.info(
                "📋 FSM recuperado de SQLite para %s: state=%s", ph_hash[:8], state.get("state")
            )
            return dict(state)
    except sqlite3.Error as e:
        logger.warning("No se pudo leer FSM de SQLite para %s: %s", ph_hash[:8], e)
    return {"state": None}


def _set_state(ph_hash: str, state: dict[str, Any]) -> None:
    """Guarda el estado conversacional.
    P0-1: Write-through a SQLite + cache en memoria."""
    _conversation_state[ph_hash] = state
    try:
        state_json = json.dumps(state, ensure_ascii=False)
        now = time.time()
        conn = sqlite3.connect(SQLITE_PATH)
        conn.execute(
            """
            INSERT INTO conversation_state (
                phone_hash, state_json, total, qty_bot, qty_hielo, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(phone_hash) DO UPDATE SET
                state_json = excluded.state_json,
                total = excluded.total,
                qty_bot = excluded.qty_bot,
                qty_hielo = excluded.qty_hielo,
                updated_at = excluded.updated_at
            """,
            (
                ph_hash,
                state_json,
                state.get("total"),
                state.get("qty_bot"),
                state.get("qty_hielo"),
                now,
            ),
        )
        conn.commit()
        conn.close()
    except sqlite3.Error as e:
        logger.warning("No se pudo persistir FSM a SQLite para %s: %s", ph_hash[:8], e)


def _clear_state(ph_hash: str) -> None:
    """Limpia el estado (pedido completado o reinicio).
    P0-1: DELETE de SQLite + pop de cache."""
    _conversation_state.pop(ph_hash, None)
    try:
        conn = sqlite3.connect(SQLITE_PATH)
        conn.execute("DELETE FROM conversation_state WHERE phone_hash = ?", (ph_hash,))
        conn.commit()
        conn.close()
    except sqlite3.Error as e:
        logger.warning("No se pudo limpiar FSM de SQLite para %s: %s", ph_hash[:8], e)


def _save_order_totals(ph_hash: str, total: float, qty_bot: int, qty_hielo: int) -> None:
    """P0-1: Persiste _last_order_totals en conversation_state (mismo row del FSM)."""
    _last_order_totals[ph_hash] = {"total": total, "qty_bot": qty_bot, "qty_hielo": qty_hielo}
    try:
        conn = sqlite3.connect(SQLITE_PATH)
        conn.execute(
            """
            INSERT INTO conversation_state (
                phone_hash, state_json, total, qty_bot, qty_hielo, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(phone_hash) DO UPDATE SET
                total = excluded.total,
                qty_bot = excluded.qty_bot,
                qty_hielo = excluded.qty_hielo,
                updated_at = excluded.updated_at
            """,
            (
                ph_hash,
                json.dumps({"state": None}, ensure_ascii=False),
                total,
                qty_bot,
                qty_hielo,
                time.time(),
            ),
        )
        conn.commit()
        conn.close()
    except sqlite3.Error as e:
        logger.warning("No se pudo persistir order_totals a SQLite para %s: %s", ph_hash[:8], e)


def _get_order_totals(ph_hash: str) -> dict[str, Any] | None:
    """P0-1: Lee _last_order_totals con cache + fallback SQLite."""
    cached = _last_order_totals.get(ph_hash)
    if cached is not None:
        return cached
    try:
        conn = sqlite3.connect(SQLITE_PATH)
        row = conn.execute(
            "SELECT total, qty_bot, qty_hielo FROM conversation_state WHERE phone_hash = ?",
            (ph_hash,),
        ).fetchone()
        conn.close()
        if row and row[0] is not None:
            totals = {"total": row[0], "qty_bot": row[1] or 0, "qty_hielo": row[2] or 0}
            _last_order_totals[ph_hash] = totals
            logger.info(
                "📋 order_totals recuperado de SQLite para %s: total=€%.2f", ph_hash[:8], row[0]
            )
            return totals
    except sqlite3.Error as e:
        logger.warning("No se pudo leer order_totals de SQLite para %s: %s", ph_hash[:8], e)
    return None


def _clear_order_totals(ph_hash: str) -> None:
    """P0-1: Limpia order_totals de cache + SQLite (columnas a NULL)."""
    _last_order_totals.pop(ph_hash, None)
    try:
        conn = sqlite3.connect(SQLITE_PATH)
        conn.execute(
            "UPDATE conversation_state SET total=NULL, "
            "qty_bot=NULL, qty_hielo=NULL WHERE phone_hash = ?",
            (ph_hash,),
        )
        conn.commit()
        conn.close()
    except sqlite3.Error as e:
        logger.warning("No se pudo limpiar order_totals de SQLite para %s: %s", ph_hash[:8], e)


def _calc_total(qty_bot: int, qty_hielo: int) -> float:
    """Calcula total determinístico."""
    return round((qty_bot * PRECIO_BOTELLON) + (qty_hielo * PRECIO_HIELO), 2)


def _format_product_desc(qty_bot: int, qty_hielo: int) -> str:
    """Formatea descripción del producto para confirmación."""
    parts = []
    if qty_bot > 0:
        parts.append(f"{qty_bot} botellones de agua")
    if qty_hielo > 0:
        parts.append(f"{qty_hielo} bolsas de hielo")
    return " y ".join(parts) if parts else "productos"


def _nearest_zone_id(lat: float | None, lng: float | None, max_km: float = 5.0) -> int | None:
    """Haversine contra la tabla zones de dispatch.db. Retorna zone_id más cercano
    dentro de max_km, o None si no hay GPS o ninguna zona calza.

    P1-5: usa haversine de route_engine (fórmula esférica correcta) en vez del
    cálculo plano aproximado local. Fallback al cálculo local si el import falla.
    """
    if lat is None or lng is None:
        return None
    try:
        conn = _get_db_with_fk(DISPATCH_DB_PATH, row_factory=True)
        rows = conn.execute("SELECT id, center_lat, center_lng, radius_km FROM zones").fetchall()
        conn.close()
    except Exception as e:
        logger.warning("zones lookup falló: %s", e)
        return None

    # P1-5: usar haversine de route_engine (esférico, preciso) con fallback local
    _haversine_impl: Any = None
    with suppress(ImportError):
        from skills.dispatch.route_engine import haversine as _haversine_impl

    best_id = None
    best_km = float("inf")
    for r in rows:
        if r["center_lat"] is None or r["center_lng"] is None:
            continue
        if _haversine_impl is not None:
            km = _haversine_impl(lat, lng, r["center_lat"], r["center_lng"])
        else:
            # Fallback: aproximación plana con factor cos(lat) para Maracaibo
            cos_lat = 0.9827  # cos(10.65°π/180) — Maracaibo lat ~10.65°N
            dlat = (r["center_lat"] - lat) * 111.32
            dlng = (r["center_lng"] - lng) * 111.32 * cos_lat
            km = (dlat * dlat + dlng * dlng) ** 0.5
        threshold = r["radius_km"] if r["radius_km"] else max_km
        if km < threshold and km < best_km:
            best_km = km
            best_id = r["id"]
    return best_id


def _sync_client_to_dispatch_db(ph_hash: str, from_phone: str, state: dict[str, Any]) -> None:
    """Upsert del cliente en dispatch.db (tabla clients) por phone_hash.
    Se llama después de encolar el pedido en dispatch_queue (conversations.db),
    para que el módulo dispatcher tenga un cliente real al planear rutas.

    Semántica:
    - phone_hash es UNIQUE → si ya existe, se actualiza address/lat/lng/updated_at.
    - Si no existe, se inserta con defaults razonables (retail, priority=5, active=1).
    - Calcula zone_id automáticamente por haversine contra las 5 zones conocidas.
    """
    try:
        name = state.get("contact_name", "") or from_phone
        address = state.get("address", "")
        lat = state.get("latitude")
        lng = state.get("longitude")
        qty_bot = state.get("qty_botellones", 0) or 0
        zone_id = _nearest_zone_id(lat, lng)
        total_bottles_visit = qty_bot  # proxy simple; hielo no es botellones
        now = datetime.now(CARACAS_TZ).timestamp()

        conn = _get_db_with_fk(DISPATCH_DB_PATH)
        # Upsert vía INSERT OR REPLACE preservando updated_at; OJO: REPLACE pierde
        # el id autoincremental en updates — usamos INSERT ... ON CONFLICT si existe.
        existing = conn.execute(
            "SELECT id, avg_bottles_per_visit FROM clients WHERE phone_hash = ?",
            (ph_hash,),
        ).fetchone()

        if existing:
            client_id, prev_avg = existing
            # Running average muy simple: media entre visita previa y nueva.
            # Si prev_avg era None/0, usar la visit actual.
            new_avg = (
                total_bottles_visit
                if (prev_avg or 0) == 0
                else int(((prev_avg or 0) + total_bottles_visit) / 2)
            )
            conn.execute(
                """
                UPDATE clients SET
                    name = ?,
                    address_text = ?,
                    lat = ?,
                    lng = ?,
                    zone_id = ?,
                    avg_bottles_per_visit = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (name, address, lat, lng, zone_id, new_avg, now, client_id),
            )
            logger.info(
                "👤 Client actualizado dispatch.db id=%d phone:%s zone=%s",
                client_id,
                ph_hash[:8],
                zone_id,
            )
        else:
            conn.execute(
                """
                INSERT INTO clients (
                    phone, phone_hash, name, address_text, lat, lng,
                    client_type, avg_bottles_per_visit, priority, zone_id,
                    active, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'retail', ?, 5, ?, 1, ?, ?)
                """,
                (
                    from_phone,
                    ph_hash,
                    name,
                    address,
                    lat,
                    lng,
                    total_bottles_visit,
                    zone_id,
                    now,
                    now,
                ),
            )
            logger.info(
                "👤 Client creado dispatch.db phone:%s zone=%s bottles=%d",
                ph_hash[:8],
                zone_id,
                total_bottles_visit,
            )

        conn.commit()
        conn.close()
    except Exception as e:
        # No romper el flujo del bridge si dispatch.db falla
        logger.error("Error sincronizando client a dispatch.db: %s", e)


def _send_to_dispatch_queue(ph_hash: str, state: dict[str, Any], from_phone: str) -> None:
    """Escribe pedido en dispatch_queue para que el dispatcher lo envíe al chofer.
    TRIGGER: cuando cliente confirma pago (efectivo '2' o 'ya pagué' tras pago móvil).
    NO encolar en abortos ('volver'/'menú' desde awaiting_payment).

    SPRINT 4.1: Usa WorkloadRouter → DispatcherSkill para notificación al chofer
    (antes: llamada HTTP directa a /dispatch/notify-driver).

    SPRINT 4.2: Vehicle assignment inteligente por zona y capacidad.
    """
    import sqlite3 as _sq3

    import httpx

    try:
        qty_bot = state.get("qty_botellones", 0)
        qty_hielo = state.get("qty_hielo", 0)
        total = state.get("total_eur", 0.0)
        metodo = state.get("payment_method", "")
        address = state.get("address", "")
        lat = state.get("latitude")
        lng = state.get("longitude")
        contact_name = state.get("contact_name", "")

        gps_url = f"https://maps.google.com/?q={lat},{lng}" if lat and lng else ""
        total_bs = _convert_eur_to_bs(total) or 0

        parts = []
        if qty_bot > 0:
            parts.append(f"{qty_bot} botellones de agua")
        if qty_hielo > 0:
            parts.append(f"{qty_hielo} bolsas de hielo")
        producto_desc = " + ".join(parts) if parts else "productos"

        conn = _sq3.connect(SQLITE_PATH)
        conn.execute(
            """
            INSERT INTO dispatch_queue (
                cliente_nombre, cliente_telefono, producto_desc,
                total_eur, total_bs, metodo_pago,
                gps_lat, gps_lng, gps_url, direccion,
                estado, creado_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)
        """,
            (
                contact_name,
                from_phone,
                producto_desc,
                total,
                total_bs,
                metodo,
                lat,
                lng,
                gps_url,
                address,
                datetime.now(CARACAS_TZ).isoformat(),
            ),
        )
        conn.commit()
        conn.close()
        logger.info("📦 Pedido enviado a dispatch_queue para phone:%s", ph_hash[:8])

        # Notificar al consumer loop para procesamiento inmediato (sub-segundo)
        try:
            from skills.dispatch.consumer import notify_consumer

            notify_consumer()
        except Exception:
            pass  # Fail silently si consumer no está corriendo

        # FASE 1 paso 2: sincronizar cliente en dispatch.db (clients table)
        # para que el dispatcher tenga un cliente real al planear rutas.
        _sync_client_to_dispatch_db(ph_hash, from_phone, state)

        # SPRINT 4.2: Vehicle assignment inteligente
        vehicle_id = _assign_vehicle_for_order(lat, lng, qty_bot)

        # SPRINT 4.1: Notificar al chofer via WorkloadRouter → DispatcherSkill
        # (antes: llamada HTTP directa a /dispatch/notify-driver)
        try:
            import asyncio

            from core.workload_router import get_router

            router = get_router()

            # Ejecutar notificación de forma asíncrona (fire-and-forget)
            async def _notify_driver_async():
                # Retry logic: 3 attempts with exponential backoff
                max_retries = 3
                base_delay = 0.5  # seconds

                for attempt in range(1, max_retries + 1):
                    try:
                        result = await router.execute(
                            trigger="dispatch_request",
                            action="notify_driver",
                            vehicle_id=vehicle_id,
                            client_name=contact_name,
                            client_phone=from_phone,
                            bottles_full=state.get("qty_botellones", 0),
                            lat=lat or 0.0,
                            lng=lng or 0.0,
                            address=address,
                            total_eur=total,
                            total_bs=total_bs,
                            metodo_pago=metodo,
                        )
                        if result.get("success") and result.get("data", {}).get("sent"):
                            logger.info(
                                "📦 Pedido notificado a chofer via WorkloadRouter → "
                                "DispatcherSkill (vehicle=%d)",
                                vehicle_id,
                            )
                            return True
                        else:
                            logger.warning(
                                "⚠️ Notificación a chofer falló (intento %d/%d): %s",
                                attempt,
                                max_retries,
                                result.get("message", "unknown"),
                            )
                    except Exception as e:
                        logger.warning(
                            "Error en notificación WorkloadRouter (intento %d/%d): %s",
                            attempt,
                            max_retries,
                            e,
                        )

                    # Wait before retry (exponential backoff)
                    if attempt < max_retries:
                        await asyncio.sleep(base_delay * (2 ** (attempt - 1)))

                # All retries failed
                logger.error("❌ Notificación a chofer falló tras %d intentos", max_retries)
                return False

            # Fire-and-forget sin bloquear el flujo del bridge
            import asyncio as _asyncio

            try:
                loop = _asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(_notify_driver_async())
                else:
                    _asyncio.run(_notify_driver_async())
            except RuntimeError:
                # No hay loop, crear uno nuevo
                _asyncio.run(_notify_driver_async())

        except Exception as e:
            logger.warning("Error importando WorkloadRouter para notificación: %s", e)
            # Fallback: llamada HTTP directa (método anterior)
            try:
                dispatch_url = "http://localhost:8000/dispatch/notify-driver"
                payload = {
                    "vehicle_id": vehicle_id,
                    "client_name": contact_name,
                    "client_phone": from_phone,
                    "bottles_full": state.get("qty_botellones", 0),
                    "lat": lat or 0.0,
                    "lng": lng or 0.0,
                    "address": address,
                    "total_eur": total,
                    "total_bs": total_bs,
                    "metodo_pago": metodo,
                }
                # Retry logic for fallback HTTP
                max_retries = 3
                for attempt in range(1, max_retries + 1):
                    try:
                        with httpx.Client(timeout=10.0) as client:
                            resp = client.post(dispatch_url, json=payload)
                            if resp.status_code == 200:
                                logger.info(
                                    "📦 Pedido notificado a chofer via fallback HTTP "
                                    "/dispatch/notify-driver (vehicle=%d)",
                                    vehicle_id,
                                )
                                break
                            else:
                                logger.warning(
                                    "Fallback HTTP status %d (intento %d/%d)",
                                    resp.status_code,
                                    attempt,
                                    max_retries,
                                )
                    except Exception as e2:
                        logger.warning(
                            "Fallback HTTP error (intento %d/%d): %s", attempt, max_retries, e2
                        )

                    if attempt < max_retries:
                        import time

                        time.sleep(0.5 * (2 ** (attempt - 1)))
                else:
                    logger.error("❌ Fallback HTTP también falló tras %d intentos", max_retries)
            except Exception as e2:
                logger.error("Fallback HTTP exception: %s", e2)
    except Exception as e:
        logger.error("Error enviando a dispatch_queue: %s", e)


def _assign_vehicle_for_order(lat: float | None, lng: float | None, bottles_needed: int) -> int:
    """
    Asigna vehículo óptimo basado en:
    1. Zona del cliente (haversine a centros de zona)
    2. Capacidad disponible (pending_deliveries < 10, max_full_bottles)
    3. Menor carga actual

    Returns: vehicle_id (1 o 2)
    """
    import sqlite3 as _sq3

    if lat is None or lng is None:
        logger.warning("Sin GPS para assignment, usando vehicle_id=1 por defecto")
        return 1

    try:
        dispatch_conn = _sq3.connect("/mnt/ssd_trabajo/hermes-agent/data/dispatch.db")
        dispatch_conn.row_factory = _sq3.Row

        # 1. Encontrar zona más cercana al cliente
        zones = dispatch_conn.execute(
            "SELECT id, center_lat, center_lng "
            "FROM zones WHERE center_lat IS NOT NULL AND center_lng IS NOT NULL"
        ).fetchall()

        if not zones:
            logger.warning("No hay zonas definidas, usando vehicle_id=1")
            return 1

        # Haversine simple inline
        from math import atan2, cos, radians, sin, sqrt

        def haversine(lat1, lng1, lat2, lng2):
            r = 6371.0
            dlat = radians(lat2 - lat1)
            dlng = radians(lng2 - lng1)
            a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlng / 2) ** 2
            return 2 * r * atan2(sqrt(a), sqrt(1 - a))

        best_zone_id = None
        best_dist = float("inf")
        for z in zones:
            dist = haversine(lat, lng, z["center_lat"], z["center_lng"])
            if dist < best_dist:
                best_dist = dist
                best_zone_id = z["id"]

        logger.info("Cliente en zona más cercana: %s (%.1f km)", best_zone_id, best_dist)

        # 2. Buscar vehicles activos con chat_id y capacidad
        query = (
            "SELECT v.id, v.name, v.operator_name, v.telegram_chat_id, "
            "v.max_full_bottles, "
            "COALESCE(SUM(CASE WHEN d.status = 'pending' THEN 1 ELSE 0 END), 0) "
            "as pending_deliveries "
            "FROM vehicles v "
            "LEFT JOIN deliveries d ON d.vehicle_id = v.id AND d.status = 'pending' "
            "WHERE v.active = 1 AND v.telegram_chat_id IS NOT NULL "
            "GROUP BY v.id, v.name, v.operator_name, v.telegram_chat_id, v.max_full_bottles "
            "ORDER BY pending_deliveries ASC, v.id ASC"
        )
        vehicles = dispatch_conn.execute(query).fetchall()

        dispatch_conn.close()

        if not vehicles:
            logger.warning("No hay vehicles con chat_id configurado, usando vehicle_id=1")
            return 1

        # 3. Filtrar por capacidad: pending < 10 y max_full_bottles >= bottles_needed
        suitable = []
        for v in vehicles:
            if v["pending_deliveries"] < 10 and v["max_full_bottles"] >= bottles_needed:
                suitable.append(v)

        if not suitable:
            logger.warning(
                "Ningún vehicle tiene capacidad para %d botellones, usando el de menos carga",
                bottles_needed,
            )
            suitable = [v for v in vehicles if v["pending_deliveries"] < 10]
            if not suitable:
                logger.warning("Todos los vehicles saturados, usando vehicle_id=1")
                return 1

        # 4. Retornar el de menos carga (ya ordenado por pending_deliveries ASC)
        chosen = suitable[0]
        logger.info(
            "Vehicle asignado: %s (%s) - pending=%d, cap=%d, need=%d",
            chosen["name"],
            chosen["operator_name"],
            chosen["pending_deliveries"],
            chosen["max_full_bottles"],
            bottles_needed,
        )
        return chosen["id"]

    except Exception as e:
        logger.error("Error en vehicle assignment: %s, defaulting to 1", e)
        return 1


def _handle_deterministic(
    ph_hash: str,
    text_body: str,
    from_phone: str,
    contact_name: str,
    msg: dict[str, Any],
    value: dict[str, Any],
) -> dict[str, Any] | None:
    """
    Maneja la conversación determinísticamente (sin Dify).
    Returns: dict con 'answer' (str) y opcional 'interactive' (dict), o None si debe delegar a Dify.
    """
    state = _get_state(ph_hash)
    current_state = state.get("state")
    text_lower = text_body.lower().strip()

    # Detectar si viene de botón interactivo
    msg.get("type") == "interactive" or msg.get("_was_interactive", False)

    # ====================================================================
    # ESTADO: None (nueva conversación) o completed
    # ====================================================================
    if current_state is None or current_state == "completed":
        # Detectar saludo
        greetings = [
            "hola",
            "buenas",
            "buenos dias",
            "buen dia",
            "buenas tardes",
            "buenas noches",
            "saludos",
            "hey",
            "que mas",
            "q mas",
        ]
        has_greeting = any(text_lower.startswith(g) for g in greetings) or text_lower in greetings

        # Bug 4 fix: Detectar mensaje compuesto (saludo + pedido)
        # Ej: "buenas me envían 3 recargas" → agua + cantidad 3
        # Ej: "hola, 2 bolsas de hielo" → hielo + cantidad 2
        # Ej: "buenas, 3 botellones y 2 hielo" → combinado
        botellones_match = re.search(r"(\d+)\s*(botellones?|recargas?|agua)", text_lower)
        hielo_match = re.search(r"(\d+)\s*(bolsas?|hielo)", text_lower)

        # Pedido combinado detectado
        if botellones_match and hielo_match:
            qty_bot = int(botellones_match.group(1))
            qty_hielo = int(hielo_match.group(1))
            if qty_bot < 3 or qty_hielo < 2:
                greeting_prefix = "¡Buen día! 👋 " if has_greeting else ""
                return {
                    "answer": f"{greeting_prefix}"
                    "Claro, con gusto le atendemos. Para pedido combinado, "
                    "el mínimo es 3 botellones y 2 bolsas de hielo."
                }
            _set_state(
                ph_hash,
                {"state": "awaiting_address", "qty_botellones": qty_bot, "qty_hielo": qty_hielo},
            )
            greeting_prefix = "¡Buen día! 👋 " if has_greeting else ""
            return {
                "answer": f"{greeting_prefix}¡Anotado! 📝 "
                f"{qty_bot} botellones de agua y {qty_hielo} bolsas de hielo. "
                "Por favor, envíe su ubicación por GPS, "
                "nombre del edificio/casa/local y un punto de referencia."
            }

        # Pedido de agua detectado
        elif botellones_match:
            qty = int(botellones_match.group(1))
            if qty < 3:
                greeting_prefix = "¡Buen día! 👋 " if has_greeting else ""
                return {
                    "answer": f"{greeting_prefix}"
                    "Claro, con gusto le atendemos. "
                    "Le comento que el pedido mínimo es de 3 botellones. "
                    "¿Desea pedir 3 o más?"
                }
            _set_state(
                ph_hash, {"state": "awaiting_address", "qty_botellones": qty, "qty_hielo": 0}
            )
            greeting_prefix = "¡Buen día! 👋 " if has_greeting else ""
            return {
                "answer": f"{greeting_prefix}¡Anotado! 📝 "
                f"{qty} botellones de agua. Por favor, "
                "envíe su ubicación por GPS, "
                "nombre del edificio/casa/local y un punto de referencia."
            }

        # Pedido de hielo detectado
        elif hielo_match:
            qty = int(hielo_match.group(1))
            if qty < 3:
                greeting_prefix = "¡Buen día! 👋 " if has_greeting else ""
                return {
                    "answer": f"{greeting_prefix}"
                    "Claro, con gusto le atendemos. "
                    "Le comento que el pedido mínimo es de 3 bolsas de hielo. "
                    "¿Desea pedir 3 o más?"
                }
            _set_state(
                ph_hash, {"state": "awaiting_address", "qty_hielo": qty, "qty_botellones": 0}
            )
            greeting_prefix = "¡Buen día! 👋 " if has_greeting else ""
            return {
                "answer": f"{greeting_prefix}¡Anotado! 📝 "
                f"{qty} bolsas de hielo. Por favor, "
                "envíe su ubicación por GPS, "
                "nombre del edificio/casa/local y un punto de referencia."
            }

        # Si hay saludo pero no hay pedido, mostrar menú
        if has_greeting:
            _clear_state(ph_hash)
            _set_state(ph_hash, {"state": "menu_sent"})
            return {
                "answer": (
                    "¡Buen día! 👋 Soy Valentina de Estación H2O. " "¿En qué puedo servirle hoy?"
                ),
                "interactive": {
                    "type": "list",
                    "body": (
                        "¡Buen día! 👋 Soy Valentina de Estación H2O.\n"
                        "¿En qué puedo servirle hoy?"
                    ),
                    "button_text": "📋 Ver opciones",
                    "list_sections": [
                        {
                            "title": "Menú principal",
                            "rows": [
                                {
                                    "id": "1",
                                    "title": "Recarga de botellones",
                                    "description": "Agua €1.00 c/u",
                                },
                                {
                                    "id": "2",
                                    "title": "Pedido de hielo",
                                    "description": "Bolsas €1.20 c/u",
                                },
                                {
                                    "id": "3",
                                    "title": "Pedido combinado",
                                    "description": "Agua + hielo",
                                },
                                {
                                    "id": "4",
                                    "title": "Consultar estado",
                                    "description": "Mi pedido",
                                },
                                {"id": "5", "title": "Otra consulta", "description": "Hablemos"},
                            ],
                        }
                    ],
                },
            }
        # NEXO P0: Botones fantasma — si escribe "gracias" tras pedido completado
        _thanks_words = [
            "gracias",
            "muchas gracias",
            "mil gracias",
            "ok gracias",
            "gracias valentina",
            "perfecto",
            "excelente",
            "genial",
        ]
        if text_lower in _thanks_words:
            return {
                "answer": "¡Con gusto! 💧 ¿En qué más le puedo ayudar?",
                "interactive": {
                    "type": "list",
                    "body": "¡Con gusto! 💧\n¿En qué más le puedo ayudar?",
                    "button_text": "📋 Ver opciones",
                    "list_sections": [
                        {
                            "title": "Menú principal",
                            "rows": [
                                {
                                    "id": "1",
                                    "title": "Recarga de botellones",
                                    "description": "Agua €1.00 c/u",
                                },
                                {
                                    "id": "2",
                                    "title": "Pedido de hielo",
                                    "description": "Bolsas €1.20 c/u",
                                },
                                {
                                    "id": "3",
                                    "title": "Pedido combinado",
                                    "description": "Agua + hielo",
                                },
                                {
                                    "id": "4",
                                    "title": "Consultar estado",
                                    "description": "Mi pedido",
                                },
                                {"id": "5", "title": "Otra consulta", "description": "Hablemos"},
                            ],
                        }
                    ],
                },
            }
        # Si no es saludo y no hay estado, delegar a Dify
        return None

    # ====================================================================
    # ESTADO: menu_sent (cliente debe seleccionar opción 1-5)
    # ====================================================================
    if current_state == "menu_sent":
        # Opción 1: Recarga de botellones
        if text_body.strip() == "1":
            _set_state(ph_hash, {"state": "awaiting_qty_agua"})
            return {
                "answer": "¿Cuántos botellones de agua desea recargar?",
                "interactive": {
                    "type": "button",
                    "body": "¿Cuántos botellones de agua desea recargar?",
                    "buttons": [
                        {"id": "3", "title": "3️⃣ 3 botellones"},
                        {"id": "4", "title": "4️⃣ 4 botellones"},
                        {"id": "custom_qty", "title": "✍️ Otra cantidad"},
                    ],
                },
            }

        # Opción 2: Pedido de hielo
        if text_body.strip() == "2":
            _set_state(ph_hash, {"state": "awaiting_qty_hielo"})
            return {
                "answer": "¿Cuántas bolsas de hielo necesita?",
                "interactive": {
                    "type": "button",
                    "body": "¿Cuántas bolsas de hielo necesita?",
                    "buttons": [
                        {"id": "3", "title": "3️⃣ 3 bolsas"},
                        {"id": "4", "title": "4️⃣ 4 bolsas"},
                        {"id": "custom_qty", "title": "✍️ Otra cantidad"},
                    ],
                },
            }

        # Opción 3: Pedido combinado
        if text_body.strip() == "3":
            _set_state(ph_hash, {"state": "awaiting_qty_combo"})
            return {
                "answer": "¿Cuántos botellones de agua y cuántas bolsas de hielo necesita?",
                "interactive": {
                    "type": "button",
                    "body": "¿Cuántos botellones de agua y cuántas bolsas de hielo necesita?",
                    "buttons": [
                        {"id": "3 botellones y 2 bolsas", "title": "3️⃣ agua + 2️⃣ hielo"},
                        {"id": "4 botellones y 3 bolsas", "title": "4️⃣ agua + 3️⃣ hielo"},
                        {"id": "custom_combo", "title": "✍️ Otra combinación"},
                    ],
                },
            }

        # Opción 4: Consultar estado → delegar a Dify
        if text_body.strip() == "4":
            return None  # Dify maneja

        # Opción 5: Otra consulta → delegar a Dify
        if text_body.strip() == "5":
            return None  # Dify maneja

        # NEXO P0: Botones fantasma — si escribe texto libre en menu_sent,
        # reenviar menú (no delegar a Dify)
        # Palabras comunes que no son pedidos: gracias, ok, si, no, bueno
        _common_words = [
            "gracias",
            "ok",
            "si",
            "sí",
            "no",
            "bueno",
            "perfecto",
            "excelente",
            "genial",
            "bye",
            "chao",
            "adios",
            "hasta luego",
        ]
        if text_lower in _common_words or len(text_body) < 3:
            return {
                "answer": "¿En qué más le puedo ayudar?",
                "interactive": {
                    "type": "list",
                    "body": "¿En qué más le puedo ayudar?",
                    "button_text": "📋 Ver opciones",
                    "list_sections": [
                        {
                            "title": "Menú principal",
                            "rows": [
                                {
                                    "id": "1",
                                    "title": "Recarga de botellones",
                                    "description": "Agua €1.00 c/u",
                                },
                                {
                                    "id": "2",
                                    "title": "Pedido de hielo",
                                    "description": "Bolsas €1.20 c/u",
                                },
                                {
                                    "id": "3",
                                    "title": "Pedido combinado",
                                    "description": "Agua + hielo",
                                },
                                {
                                    "id": "4",
                                    "title": "Consultar estado",
                                    "description": "Mi pedido",
                                },
                                {"id": "5", "title": "Otra consulta", "description": "Hablemos"},
                            ],
                        }
                    ],
                },
            }
        # Si no es palabra común, delegar a Dify (puede ser mensaje compuesto)
        return None

    # ====================================================================
    # ESTADO: awaiting_qty_agua (cliente debe enviar cantidad de botellones)
    # ====================================================================
    if current_state == "awaiting_qty_agua":
        if text_body.strip() == "custom_qty":
            _set_state(ph_hash, {"state": "awaiting_custom_qty_agua"})
            return {
                "answer": "Por favor, escriba la cantidad que necesita (solo el número, mínimo 3)."
            }

        qty_match = re.match(r"^(\d+)$", text_body.strip())
        if qty_match:
            qty = int(qty_match.group(1))
            if qty < 3:
                return {
                    "answer": "Claro, con gusto le atendemos. Le comento que el pedido mínimo es de 3 unidades. ¿Desea pedir 3 o más?",  # noqa: E501
                    "interactive": {
                        "type": "button",
                        "body": "Claro, con gusto le atendemos. Le comento que el pedido mínimo es de 3 unidades. ¿Desea pedir 3 o más?",  # noqa: E501
                        "buttons": [
                            {"id": "3", "title": "3️⃣ 3 botellones"},
                            {"id": "4", "title": "4️⃣ 4 botellones"},
                            {"id": "custom_qty", "title": "✍️ Otra cantidad"},
                        ],
                    },
                }
            # Cantidad válida → pedir dirección
            new_state = state.copy()
            new_state["state"] = "awaiting_address"
            new_state["qty_botellones"] = qty
            new_state["qty_hielo"] = 0
            _set_state(ph_hash, new_state)
            return {
                "answer": "Perfecto. Por favor, envíe su ubicación por GPS, nombre del edificio/casa/local y un punto de referencia."  # noqa: E501
            }

        return None  # Delegar a Dify

    # ====================================================================
    # ESTADO: awaiting_custom_qty_agua (cliente debe escribir número)
    # ====================================================================
    if current_state == "awaiting_custom_qty_agua":
        qty_match = re.match(r"^(\d+)$", text_body.strip())
        if qty_match:
            qty = int(qty_match.group(1))
            if qty < 3:
                return {
                    "answer": "Claro, con gusto le atendemos. Le comento que el pedido mínimo es de 3 unidades. ¿Desea pedir 3 o más?"  # noqa: E501
                }
            new_state = state.copy()
            new_state["state"] = "awaiting_address"
            new_state["qty_botellones"] = qty
            new_state["qty_hielo"] = 0
            _set_state(ph_hash, new_state)
            return {
                "answer": "Perfecto. Por favor, envíe su ubicación por GPS, nombre del edificio/casa/local y un punto de referencia."  # noqa: E501
            }
        return None

    # ====================================================================
    # ESTADO: awaiting_qty_hielo (cliente debe enviar cantidad de hielo)
    # ====================================================================
    if current_state == "awaiting_qty_hielo":
        if text_body.strip() == "custom_qty":
            _set_state(ph_hash, {"state": "awaiting_custom_qty_hielo"})
            return {
                "answer": "Por favor, escriba la cantidad que necesita (solo el número, mínimo 3)."
            }

        qty_match = re.match(r"^(\d+)$", text_body.strip())
        if qty_match:
            qty = int(qty_match.group(1))
            if qty < 3:
                return {
                    "answer": "Claro, con gusto le atendemos. Le comento que el pedido mínimo es de 3 unidades. ¿Desea pedir 3 o más?",  # noqa: E501
                    "interactive": {
                        "type": "button",
                        "body": "Claro, con gusto le atendemos. Le comento que el pedido mínimo es de 3 unidades. ¿Desea pedir 3 o más?",  # noqa: E501
                        "buttons": [
                            {"id": "3", "title": "3️⃣ 3 bolsas"},
                            {"id": "4", "title": "4️⃣ 4 bolsas"},
                            {"id": "custom_qty", "title": "✍️ Otra cantidad"},
                        ],
                    },
                }
            new_state = state.copy()
            new_state["state"] = "awaiting_address"
            new_state["qty_hielo"] = qty
            new_state["qty_botellones"] = 0
            _set_state(ph_hash, new_state)
            return {
                "answer": "Perfecto. Por favor, envíe su ubicación por GPS, nombre del edificio/casa/local y un punto de referencia."  # noqa: E501
            }

        return None

    # ====================================================================
    # ESTADO: awaiting_custom_qty_hielo
    # ====================================================================
    if current_state == "awaiting_custom_qty_hielo":
        qty_match = re.match(r"^(\d+)$", text_body.strip())
        if qty_match:
            qty = int(qty_match.group(1))
            if qty < 3:
                return {
                    "answer": "Claro, con gusto le atendemos. Le comento que el pedido mínimo es de 3 unidades. ¿Desea pedir 3 o más?"  # noqa: E501
                }
            new_state = state.copy()
            new_state["state"] = "awaiting_address"
            new_state["qty_hielo"] = qty
            new_state["qty_botellones"] = 0
            _set_state(ph_hash, new_state)
            return {
                "answer": "Perfecto. Por favor, envíe su ubicación por GPS, nombre del edificio/casa/local y un punto de referencia."  # noqa: E501
            }
        return None

    # ====================================================================
    # ESTADO: awaiting_qty_combo (cliente debe enviar cantidades combinadas)
    # ====================================================================
    if current_state == "awaiting_qty_combo":
        if text_body.strip() == "custom_combo":
            _set_state(ph_hash, {"state": "awaiting_custom_combo"})
            return {
                "answer": "Por favor, escriba las cantidades así: 'X botellones y Y bolsas' (ej: 3 botellones y 2 bolsas)."  # noqa: E501
            }

        # Intentar parsear "3 botellones y 2 bolsas"
        bot_match = re.search(r"(\d+)\s*botellones?", text_lower)
        hielo_match = re.search(r"(\d+)\s*bolsas?", text_lower)
        if bot_match and hielo_match:
            qty_bot = int(bot_match.group(1))
            qty_hielo = int(hielo_match.group(1))
            if qty_bot < 3 or qty_hielo < 2:
                return {
                    "answer": "Claro, con gusto le atendemos. Para pedido combinado, el mínimo es 3 botellones y 2 bolsas de hielo."  # noqa: E501
                }
            new_state = state.copy()
            new_state["state"] = "awaiting_address"
            new_state["qty_botellones"] = qty_bot
            new_state["qty_hielo"] = qty_hielo
            _set_state(ph_hash, new_state)
            return {
                "answer": "Perfecto. Por favor, envíe su ubicación por GPS, nombre del edificio/casa/local y un punto de referencia."  # noqa: E501
            }

        return None

    # ====================================================================
    # ESTADO: awaiting_custom_combo
    # ====================================================================
    if current_state == "awaiting_custom_combo":
        bot_match = re.search(r"(\d+)\s*botellones?", text_lower)
        hielo_match = re.search(r"(\d+)\s*bolsas?", text_lower)
        if bot_match and hielo_match:
            qty_bot = int(bot_match.group(1))
            qty_hielo = int(hielo_match.group(1))
            if qty_bot < 3 or qty_hielo < 2:
                return {
                    "answer": "Claro, con gusto le atendemos. Para pedido combinado, el mínimo es 3 botellones y 2 bolsas de hielo."  # noqa: E501
                }
            new_state = state.copy()
            new_state["state"] = "awaiting_address"
            new_state["qty_botellones"] = qty_bot
            new_state["qty_hielo"] = qty_hielo
            _set_state(ph_hash, new_state)
            return {
                "answer": "Perfecto. Por favor, envíe su ubicación por GPS, nombre del edificio/casa/local y un punto de referencia."  # noqa: E501
            }
        return None

    # ====================================================================
    # ESTADO: awaiting_address (cliente debe enviar dirección o GPS)
    # ====================================================================
    if current_state == "awaiting_address":
        # Si viene GPS (location), extraer coordenadas
        latitude = None
        longitude = None
        if msg.get("type") == "location":
            loc = msg.get("location", {})
            latitude = loc.get("latitude")
            longitude = loc.get("longitude")
            loc_name = loc.get("name", "")
            loc_addr = loc.get("address", "")
            addr_parts = []
            if loc_addr:
                addr_parts.append(loc_addr)
            if loc_name:
                addr_parts.append(loc_name)
            if not addr_parts:
                addr_parts.append(f"GPS: {latitude}, {longitude}")
            addr_parts.append(f"(coordenadas: {latitude}, {longitude})")
            address = "Mi ubicación: " + ", ".join(addr_parts)
        else:
            # Texto libre
            address = text_body.strip()
            # Verificar si contiene coordenadas
            coord_match = re.search(
                r"(?:coordenadas:|GPS:)\s*(-?\d+[.,]?\d*)\s*,\s*(-?\d+[.,]?\d*)",
                address,
                re.IGNORECASE,
            )
            if coord_match:
                try:
                    latitude = float(coord_match.group(1).replace(",", "."))
                    longitude = float(coord_match.group(2).replace(",", "."))
                except ValueError:
                    pass

        if len(address) < 5:
            # NEXO P1: Error recovery — lenguaje más cálido
            return {
                "answer": "¿A dónde le llevamos su pedido? 📍 Envíe su ubicación GPS o escriba su dirección completa."  # noqa: E501
            }

        # Guardar dirección + calcular total + confirmar pedido
        qty_bot = state.get("qty_botellones", 0)
        qty_hielo = state.get("qty_hielo", 0)
        total = _calc_total(qty_bot, qty_hielo)
        product_desc = _format_product_desc(qty_bot, qty_hielo)

        new_state = state.copy()
        new_state["state"] = "awaiting_payment"
        new_state["address"] = address
        new_state["latitude"] = latitude
        new_state["longitude"] = longitude
        new_state["total_eur"] = total
        new_state["contact_name"] = contact_name
        _set_state(ph_hash, new_state)

        # Guardar en SQLite + Google Sheets
        _save_order_to_db_and_sheets(
            from_phone,
            ph_hash,
            contact_name,
            qty_bot,
            qty_hielo,
            address,
            latitude,
            longitude,
            total,
            new_state.get("conversation_id", ""),
        )

        confirm_msg = (
            f"✅ Pedido confirmado: {product_desc}. Dirección: {address}.\n\n"
            f"💰 Total: €{total:.2f} (Bs. {_convert_eur_to_bs(total) or 0:.2f}).\n\n"
            f"¿Cómo desea pagar?"
        )
        return {
            "answer": confirm_msg,
            "interactive": {
                "type": "button",
                "body": confirm_msg,
                "buttons": [
                    {"id": "1", "title": "💳 Pago Móvil"},
                    {"id": "2", "title": "💵 Efectivo"},
                ],
            },
        }

    # ====================================================================
    # ESTADO: awaiting_payment (cliente debe elegir 1 o 2)
    # ====================================================================
    if current_state == "awaiting_payment":
        total = state.get("total_eur", 0.0)

        if text_body.strip() == "1":
            # Pago Móvil
            new_state = state.copy()
            new_state["state"] = "awaiting_confirmation"
            new_state["payment_method"] = "Pago Móvil"
            _set_state(ph_hash, new_state)
            return {
                "answer": BANK_DATA.format(total=total, total_bs=_convert_eur_to_bs(total) or 0),
                "interactive": {
                    "type": "button",
                    "body": BANK_DATA.format(total=total, total_bs=_convert_eur_to_bs(total) or 0),
                    "buttons": [
                        {"id": "ya_pague", "title": "✅ Ya pagué"},
                    ],
                },
            }

        if text_body.strip() == "2":
            # Efectivo
            new_state = state.copy()
            new_state["state"] = "completed"
            new_state["payment_method"] = "Efectivo"
            _set_state(ph_hash, new_state)
            # FASE 1.5: Encolar pedido para dispatcher (antes de limpiar estado)
            _send_to_dispatch_queue(ph_hash, new_state, from_phone)
            _clear_state(ph_hash)
            return {
                "answer": f"Perfecto. Pague en efectivo al recibir su pedido.\n\n💰 Total: €{total:.2f} (Bs. {_convert_eur_to_bs(total) or 0:.2f})\n\nEl chofer va en camino. ¡Gracias! 💧"  # noqa: E501
            }

        # NEXO P1: Si escribe "volver" o "menu", reiniciar al menú
        if text_lower in ["volver", "menú", "menu", "atrás", "atras", "inicio"]:
            _clear_state(ph_hash)
            _set_state(ph_hash, {"state": "menu_sent"})
            return {
                "answer": "Claro, volvemos al inicio.",
                "interactive": {
                    "type": "list",
                    "body": "Claro, volvemos al inicio. 🔄\n¿En qué puedo servirle? 💧",
                    "button_text": "📋 Ver opciones",
                    "list_sections": [
                        {
                            "title": "Menú principal",
                            "rows": [
                                {
                                    "id": "1",
                                    "title": "Recarga de botellones",
                                    "description": "Agua €1.00 c/u",
                                },
                                {
                                    "id": "2",
                                    "title": "Pedido de hielo",
                                    "description": "Bolsas €1.20 c/u",
                                },
                                {
                                    "id": "3",
                                    "title": "Pedido combinado",
                                    "description": "Agua + hielo",
                                },
                                {
                                    "id": "4",
                                    "title": "Consultar estado",
                                    "description": "Mi pedido",
                                },
                                {"id": "5", "title": "Otra consulta", "description": "Hablemos"},
                            ],
                        }
                    ],
                },
            }

        # NEXO P1: Error recovery — no repetir mismo mensaje
        return {
            "answer": "¿Cómo prefiere pagar? 💳 Pago Móvil o 💵 Efectivo. Puede escribir 1 o 2."
        }

    # ====================================================================
    # ESTADO: awaiting_confirmation (cliente debe enviar "ya pagué")
    # ====================================================================
    if current_state == "awaiting_confirmation":
        if text_lower in [
            "ya pagué",
            "ya pague",
            "ya pagué.",
            "ya pague.",
            "pagué",
            "pague",
            "listo",
            "ya",
        ]:
            # FASE 1.5: Encolar pedido para dispatcher (antes de limpiar estado)
            _send_to_dispatch_queue(ph_hash, state, from_phone)
            _clear_state(ph_hash)
            # NEXO P1: Finalización completa — qué se hizo + qué sigue + cómo volver
            qty_bot = state.get("qty_botellones", 0)
            qty_hielo = state.get("qty_hielo", 0)
            address = state.get("address", "")
            parts = []
            if qty_bot > 0:
                parts.append(f"{qty_bot} botellones de agua")
            if qty_hielo > 0:
                parts.append(f"{qty_hielo} bolsas de hielo")
            producto_str = " y ".join(parts) if parts else "su pedido"
            addr_short = address[:60] + "..." if len(address) > 60 else address
            return {
                "answer": f"✅ ¡Pedido completado!\n\nLe llevamos {producto_str} a {addr_short}.\nEl chofer le contactará pronto.\n\nSi necesita algo más, escríbame aquí. 💧"  # noqa: E501
            }

        # Si envía otra cosa, reenviar botón
        total = state.get("total_eur", 0.0)
        return {
            "answer": BANK_DATA.format(total=total, total_bs=_convert_eur_to_bs(total) or 0),
            "interactive": {
                "type": "button",
                "body": BANK_DATA.format(total=total, total_bs=_convert_eur_to_bs(total) or 0),
                "buttons": [
                    {"id": "ya_pague", "title": "✅ Ya pagué"},
                ],
            },
        }

    # NEXO P0: Botones fantasma — en cualquier estado, si cliente escribe
    # "gracias", "ok", "si" o similar, reenviar botones del estado actual
    _ack_words = ["gracias", "ok", "si", "sí", "perfecto", "bueno", "excelente", "genial", "listo"]
    if text_lower in _ack_words:
        # Reenviar menú principal como fallback seguro
        return {
            "answer": "¿En qué más le puedo ayudar?",
            "interactive": {
                "type": "list",
                "body": "¿En qué más le puedo ayudar?",
                "button_text": "📋 Ver opciones",
                "list_sections": [
                    {
                        "title": "Menú principal",
                        "rows": [
                            {
                                "id": "1",
                                "title": "Recarga de botellones",
                                "description": "Agua €1.00 c/u",
                            },
                            {
                                "id": "2",
                                "title": "Pedido de hielo",
                                "description": "Bolsas €1.20 c/u",
                            },
                            {"id": "3", "title": "Pedido combinado", "description": "Agua + hielo"},
                            {"id": "4", "title": "Consultar estado", "description": "Mi pedido"},
                            {"id": "5", "title": "Otra consulta", "description": "Hablemos"},
                        ],
                    }
                ],
            },
        }

    # Si no matchea ningún estado, delegar a Dify
    return None


def _save_order_to_db_and_sheets(
    from_phone: str,
    ph_hash: str,
    contact_name: str,
    qty_bot: int,
    qty_hielo: int,
    address: str,
    latitude: float | None,
    longitude: float | None,
    total: float,
    conversation_id: str,
) -> None:
    """Guarda el pedido en SQLite + Google Sheets (no bloqueante)."""
    import sqlite3

    try:
        conn = sqlite3.connect(SQLITE_PATH)
        product_desc = _format_product_desc(qty_bot, qty_hielo)
        # r7: usar cursor.lastrowid (more limpio que SELECT last_insert_rowid())
        # ANTES de conn.close() para evitar use-after-close.
        cursor = conn.execute(
            "INSERT INTO orders (phone_hash, product_description, status, created_at) VALUES (?, ?, ?, ?)",  # noqa: E501
            (
                ph_hash,
                f"✅ Pedido confirmado: {product_desc}. Total: €{total:.2f}",
                "pending",
                time.time(),
            ),
        )
        pedido_id = cursor.lastrowid  # capturado antes del close
        conn.commit()
        conn.close()
        ORDERS_TOTAL.inc()
        logger.info(
            "Orden guardada en SQLite para phone:%s total=€%.2f id=%d",
            ph_hash[:8],
            total,
            pedido_id,
        )

        # Notificar a Financial Shield para registro financiero
        try:
            fs = _get_fs()
            if fs:
                import asyncio

                # r7: pedido_id ya capturado, conn ya cerrada. Llamar a FS async.
                metodo_pago_str = "pagomovil"  # Default, se actualiza después
                # r7: usar create_task con referencia guardada (GC no cancela task).
                _fs_task = asyncio.ensure_future(
                    fs.on_nuevo_pedido(
                        pedido_id=pedido_id,
                        cliente_telefono=from_phone,
                        cliente_nombre=contact_name,
                        qty_botellones=qty_bot,
                        qty_hielo=qty_hielo,
                        metodo_pago=metodo_pago_str,
                        total_eur=total,
                    )
                )
                # Mantener referencia débil en una set global para evitar cancelación por GC
                _ASYNCTASKS_REFS.add(_fs_task)
                _fs_task.add_done_callback(_ASYNCTASKS_REFS.discard)
                logger.info("🛡️ FS notificado: pedido=%d total=€%.2f", pedido_id, total)
        except Exception as fs_err:
            logger.error("Error notificando a FS: %s", fs_err)
    except sqlite3.Error as e:
        logger.error("Error guardando orden SQLite: %s", e)

    # P0-1: Guardar order_totals con persistencia SQLite
    _save_order_totals(ph_hash, total, qty_bot, qty_hielo)

    # Google Sheets async
    order_payload = {
        "phone": from_phone,
        "phone_hash": ph_hash,
        "contact_name": contact_name,
        "product_type": "Combinado"
        if qty_bot > 0 and qty_hielo > 0
        else ("Botellones" if qty_bot > 0 else "Hielo"),
        "qty_botellones": qty_bot,
        "qty_hielo": qty_hielo,
        "address": address,
        "latitude": latitude,
        "longitude": longitude,
        "total_eur": total,
        "payment_method": "",
        "conversation_id": conversation_id,
        "raw_answer": f"✅ Pedido confirmado: {_format_product_desc(qty_bot, qty_hielo)}. Total: €{total:.2f}",  # noqa: E501
    }
    try:
        from skills.google_sheets import save_order_async

        save_order_async(order_payload)
        logger.info("Pedido enviado a Google Sheets para phone:%s", ph_hash[:8])
    except Exception as gs_err:
        logger.error("Error enviando a Google Sheets: %s", gs_err)


def _fix_total_in_response(answer: str, payload: dict[str, Any]) -> str:
    """
    Reemplaza el total en la respuesta de Valentina por el cálculo
    determinístico del bridge. Si Dify calculó mal, el bridge lo corrige.

    Busca patrones como:
    - "Total: €6.00" → "Total: €3.00"
    - "Total: €6,00" → "Total: €3.00"
    - "total: 6 euros" → "Total: €3.00"
    """
    if payload["total_eur"] <= 0:
        return answer  # No hay nada que corregir

    correct_total = f"€{payload['total_eur']:.2f}"

    # Patrones de total en la respuesta del LLM
    patterns = [
        # "Total: €6.00" o "Total: €6,00"
        r"(Total:\s*)[€eE][Uu]?[Rr]?[Oo]?[Ss]?\s*:?\s*(\d+[.,]\d{2})",
        # "Total: 6 euros" o "total: 6.00"
        r"(Total:\s*)(\d+[.,]?\d*)\s*(euros?|€)?",
    ]

    fixed = answer
    for pattern in patterns:
        fixed = re.sub(
            pattern,
            lambda m: f"{m.group(1)}{correct_total}",
            fixed,
            flags=re.IGNORECASE,
        )

    if fixed != answer:
        logger.info(
            "🔧 Total corregido en respuesta: LLM=€%.2f → bridge=€%.2f",
            payload.get("_llm_total", 0),
            payload["total_eur"],
        )
    return fixed


def _build_order_payload(
    from_phone: str,
    answer: str,
    contact_name: str,
    conversation_id: str,
) -> dict[str, Any]:
    """
    Parsea la respuesta de Valentina para extraer datos del pedido.

    La respuesta contiene algo como:
    "✅ Pedido confirmado: 3 botellones de agua. Dirección: Calle 69.
     💰 Total: €3.00 (págalo en bolívares al cambio BCV del día).
     ¿Cómo desea pagar? 1️⃣ Pago Móvil 2️⃣ Efectivo contra entrega."

    O con GPS:
    (
        "✅ Pedido confirmado: 2 bolsas de hielo. "
        "Dirección: Mi ubicación: ... "
        "(coordenadas: 10.63, -71.64)..."
    )

    Returns: dict listo para skills.google_sheets.save_order_async
    """
    import re

    payload = {
        "phone": from_phone,
        "phone_hash": _phone_hash(from_phone),
        "contact_name": contact_name,
        "product_type": "",
        "qty_botellones": 0,
        "qty_hielo": 0,
        "address": "",
        "latitude": None,
        "longitude": None,
        "total_eur": 0.0,
        "payment_method": "",
        "conversation_id": conversation_id or "",
        "raw_answer": answer,
    }

    # Tipo de producto + cantidades
    # Patrones comunes: "3 botellones de agua", "2 bolsas de hielo",
    # "2 botellones de agua y 3 bolsas de hielo"
    botellones_match = re.search(r"(\d+)\s*botellones?\s*de\s*agua", answer, re.IGNORECASE)
    hielo_match = re.search(r"(\d+)\s*bolsas?\s*de\s*hielo", answer, re.IGNORECASE)

    if botellones_match and hielo_match:
        payload["product_type"] = "Combinado"
        payload["qty_botellones"] = int(botellones_match.group(1))
        payload["qty_hielo"] = int(hielo_match.group(1))
    elif botellones_match:
        payload["product_type"] = "Botellones"
        payload["qty_botellones"] = int(botellones_match.group(1))
    elif hielo_match:
        payload["product_type"] = "Hielo"
        payload["qty_hielo"] = int(hielo_match.group(1))

    # Total en euros — CÁLCULO DETERMINÍSTICO (no extraer del LLM)
    # El LLM puede equivocarse en cálculos. El bridge calcula con precios oficiales.
    precio_botellon = 1.00  # €
    precio_hielo = 1.20  # €
    qty_bot_val: Any = payload.get("qty_botellones", 0)
    qty_hielo_val: Any = payload.get("qty_hielo", 0)
    payload["total_eur"] = round(
        (float(qty_bot_val) * precio_botellon) + (float(qty_hielo_val) * precio_hielo), 2
    )

    # Método de pago (si aparece en la respuesta de confirmación de pago)
    answer_lower = answer.lower()
    if "pago móvil" in answer_lower or "pago movil" in answer_lower:
        payload["payment_method"] = "Pago Móvil"
    elif "efectivo" in answer_lower:
        payload["payment_method"] = "Efectivo"

    # Dirección: extraer entre "Dirección:" y el primer "."
    # Patrones: "Dirección: Calle 69." / "Dirección: Mi ubicación: ..."
    addr_match = re.search(r"Direcci[oó]n:\s*(.+?)(?:\.\s|\n|$)", answer, re.IGNORECASE)
    if addr_match:
        payload["address"] = addr_match.group(1).strip()
        # Si la dirección contiene coordenadas, extraerlas
        coord_match = re.search(
            r"(?:coordenadas:|GPS:)\s*(-?\d+[.,]?\d*)\s*,\s*(-?\d+[.,]?\d*)",
            str(payload["address"]),
            re.IGNORECASE,
        )
        if coord_match:
            try:
                payload["latitude"] = float(coord_match.group(1).replace(",", "."))
                payload["longitude"] = float(coord_match.group(2).replace(",", "."))
            except ValueError:
                pass

    logger.info(
        "Pedido parseado: %s botellones=%d hielo=%d total=€%.2f lat=%s lng=%s",
        payload["product_type"],
        payload["qty_botellones"],
        payload["qty_hielo"],
        payload["total_eur"],
        payload["latitude"],
        payload["longitude"],
    )
    return payload


# ============================================================================
# FastAPI app
# ============================================================================

# P1-2: Watchdog systemd — envia WATCHDOG=1 cada 15s.
# systemd reinicia el servicio si no recibe notify en WatchdogSec=30s.
_watchdog_task: asyncio.Task[None] | None = None


async def _watchdog_loop() -> None:
    """Loop asyncio que envia sd_notify WATCHDOG=1 cada 15s."""
    if sdnotify is None:
        logger.warning("sdnotify no instalado — watchdog systemd inactivo")
        return
    notifier = sdnotify.SystemdNotifier()
    interval = 15  # mitad de WatchdogSec=30s
    logger.info("Watchdog systemd activo (interval=%ds)", interval)
    while True:
        try:
            notifier.notify("WATCHDOG=1")
        except Exception as e:
            logger.warning("Watchdog notify fallo: %s", e)
        await asyncio.sleep(interval)


# ============================================================================
# Meta webhook message processor — core business logic
# ============================================================================


async def _process_meta_message(msg: dict[str, Any], value: dict[str, Any]) -> None:
    """
    Procesa un mensaje de Meta Cloud API ya validado y parseado.
    Llamado desde webhook_meta.py tras validación HMAC, kill-switch, dedup, etc.
    """
    logger.info("_process_meta_message called - delegating to internal handler")
    # The actual processing is done in meta_webhook endpoint
    # This function is kept for compatibility with webhook_meta.py
    pass


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    global _http_client, _telegram_bot, _watchdog_task, _recovery_task
    _init_db()
    _http_client = httpx.AsyncClient()

    # Importar y registrar webhook Meta
    from api.webhook_meta import register_webhook_meta_routes, set_message_handler

    register_webhook_meta_routes(app)
    set_message_handler(_process_meta_message)

    # Registrar HTTP client en MetaClient
    set_http_client(_http_client)

    # Inicializar MetaClient singleton
    get_meta_client()

    # P1-2: Iniciar watchdog systemd
    if sdnotify is not None:
        sdnotify.SystemdNotifier().notify("READY=1")
        _watchdog_task = asyncio.create_task(_watchdog_loop())
    else:
        logger.warning("sdnotify no instalado — Type=notify puede colgar el startup")

    # Inicializar bot de Telegram si está configurado
    if TELEGRAM_ENABLED:
        try:
            _telegram_bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)
            await _send_telegram(
                "✅ <b>Valentina Bridge iniciado</b>\\\\n\\\\n💧 Estación H2O lista para atender."
            )
            logger.info("Telegram alerts activadas (chat_id=%s)", TELEGRAM_CHAT_ID)
        except Exception as e:
            logger.warning("Telegram no disponible: %s", e)

    # Limpiar kill switch al arranque (por si quedó de un restart forzado)
    if os.path.exists(KILL_SWITCH_FILE):
        os.remove(KILL_SWITCH_FILE)
        logger.info("Kill switch limpiado al arranque")

    logger.info("Valentina Bridge iniciado en puerto %d", BRIDGE_PORT)
    logger.info("Dify API: %s", DIFY_API_URL)
    logger.info("Meta API version: %s", META_API_VERSION)
    logger.info("Prometheus metrics: %s", "activadas" if PROMETHEUS_AVAILABLE else "no disponibles")

    # P0-B FIX: Recovery scan en background task POST-yield
    # (no bloquea startup, evita 'database is locked')
    async def _run_recovery_scan():
        # Pequeña pausa para que el bridge termine de arrancar y acepte requests
        await asyncio.sleep(2)
        try:
            from src.financial.verificacion import recovery_scan_stuck_payments

            recovered = await recovery_scan_stuck_payments()
            if recovered:
                logger.warning("Financial Shield recovery (bg): %d pedidos reanudados", recovered)
        except Exception as e:
            logger.warning("Financial Shield recovery scan (bg) falló: %s", e)

    _recovery_task = asyncio.create_task(_run_recovery_scan())

    # Iniciar consumer loop en background (procesa dispatch_queue en tiempo real)
    from skills.dispatch.consumer import consumer_loop

    _consumer_task = asyncio.create_task(consumer_loop(poll_interval=5))
    logger.info("🔄 Consumer loop task creado")

    yield

    # P1-2: Cancelar watchdog en shutdown
    if _watchdog_task:
        _watchdog_task.cancel()
        with suppress(asyncio.CancelledError):
            await _watchdog_task

    # Cancelar recovery task si aún está corriendo
    if _recovery_task and not _recovery_task.done():
        _recovery_task.cancel()
        with suppress(asyncio.CancelledError):
            await _recovery_task

    # Cancelar consumer loop
    if "_consumer_task" in globals() and _consumer_task and not _consumer_task.done():
        _consumer_task.cancel()
        with suppress(asyncio.CancelledError):
            await _consumer_task

        # Graceful shutdown
        logger.info("Cerrando conexiones...")
        if _telegram_bot:
            await _send_telegram(
                "⚠️ <b>Valentina Bridge detenido</b>\\\\\\\\n\\\\\\\\n"
                "Los mensajes no se responden temporalmente."
            )
        await _http_client.aclose()
        logger.info("Valentina Bridge detenido")


app = FastAPI(
    title="Valentina Bridge",
    description="Webhook Meta Cloud API → Dify Chatflow → Meta Graph API",
    version="1.0.0",
    lifespan=lifespan,
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]

# Registrar webhooks R4 Conecta
include_r4_webhooks(app)

# Include dispatch routes
app.include_router(dispatch_router)


@app.get("/")
async def root() -> dict[str, Any]:
    """Endpoint raíz — info básica para verificar que el puente está vivo."""
    return {
        "name": "Valentina Bridge",
        "status": "operational" if not _is_kill_switch_active() else "kill_switch_active",
        "uptime_seconds": time.time() - START_TIME,
        "version": "1.1.0",
        "dify_configured": bool(DIFY_API_KEY),
        "meta_configured": bool(META_ACCESS_TOKEN and META_PHONE_NUMBER_ID),
        "telegram_enabled": TELEGRAM_ENABLED,
        "prometheus_enabled": PROMETHEUS_AVAILABLE,
        "endpoints": {
            "webhook_meta": "/webhook/meta [GET verify, POST messages]",
            "health": "/health",
            "metrics": "/metrics (Prometheus)",
        },
    }


@app.get("/metrics")
async def metrics(request: Request) -> RawResponse:
    """Endpoint de métricas Prometheus para scrapeo.

    P0-2: IP allowlist — solo localhost y red Docker local (172.19.0.0/16).
    Evita que /metrics exponga internals (kill_switch state, Python version,
    error counters) si el tunnel catch-all se relaja o se abre subdominio.
    """
    # IP allowlist
    client_ip = request.client.host if request.client else ""
    _allowed = client_ip in ("127.0.0.1", "::1") or client_ip.startswith("172.19.")
    if not _allowed:
        raise HTTPException(status_code=403, detail="Access denied")
    if not PROMETHEUS_AVAILABLE:
        return JSONResponse(
            {"error": "prometheus_client no instalado"},
            status_code=503,
        )
    # Actualizar gauge de conversaciones activas
    try:
        conn = sqlite3.connect(SQLITE_PATH)
        cutoff = time.time() - 86400  # últimas 24h
        count = conn.execute(
            "SELECT COUNT(*) FROM conversations WHERE last_seen > ?", (cutoff,)
        ).fetchone()[0]
        conn.close()
        ACTIVE_CONVERSATIONS.set(count)
    except sqlite3.Error:
        pass
    return RawResponse(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )


@app.get("/health")
async def health() -> JSONResponse:
    """Health check para systemd / Prometheus / Cloudflare."""
    ok = bool(DIFY_API_KEY and META_ACCESS_TOKEN and META_PHONE_NUMBER_ID)
    kill_switch = _is_kill_switch_active()
    status = "ok"
    if kill_switch:
        status = "kill_switch_active"
        ok = False
    elif not ok:
        status = "degraded"
    return JSONResponse(
        status_code=200 if ok else 503,
        content={
            "status": status,
            "uptime_seconds": time.time() - START_TIME,
            "checks": {
                "dify_api_key": bool(DIFY_API_KEY),
                "meta_access_token": bool(META_ACCESS_TOKEN),
                "meta_phone_number_id": bool(META_PHONE_NUMBER_ID),
                "sqlite": os.path.exists(SQLITE_PATH),
                "telegram": TELEGRAM_ENABLED,
                "kill_switch": kill_switch,
            },
        },
    )


@app.get("/webhook/meta", response_class=PlainTextResponse, response_model=None)
async def meta_verify(request: Request) -> PlainTextResponse:
    """Verificación del webhook de Meta Cloud API (paso de configuración único).

    Meta envía los parámetros con PUNTOS (hub.mode, hub.verify_token, hub.challenge),
    no con guiones bajos. Por eso usamos request.query_params en lugar de parámetros
    declarados en la firma de la función.
    """
    params = request.query_params
    hub_mode = params.get("hub.mode", "")
    hub_verify_token = params.get("hub.verify_token", "")
    hub_challenge = params.get("hub.challenge", "")

    if hub_mode == "subscribe" and hub_verify_token == META_VERIFY_TOKEN:
        logger.info("Webhook Meta verificado correctamente")
        return PlainTextResponse(hub_challenge)
    logger.warning(
        "Verificación Meta fallida — hub_mode=%s token_match=%s",
        hub_mode,
        hub_verify_token == META_VERIFY_TOKEN,
    )
    raise HTTPException(status_code=403, detail="Verification failed")


@app.post("/webhook/meta")
@limiter.limit(f"{RATE_PER_IP}/minute")
async def meta_webhook(request: Request) -> JSONResponse:
    """
    Recibe mensajes de WhatsApp desde Meta Cloud API.

    Flujo:
      1. Verificar HMAC-SHA256 (X-Hub-Signature-256)
      2. Kill switch check (si está activado, no procesar)
      3. Parsear entry[0].changes[0].value.messages[0]
      4. Deduplicar por message_id
      5. Llamar a Dify con conversation_id persistida
      6. Enviar respuesta via Meta Graph API
      7. Persistir nuevo conversation_id
      8. Métricas Prometheus + alertas Telegram si crítico
    """
    request_start = time.time()
    raw_body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256", "")

    # 1. HMAC verification
    if not _verify_meta_signature(raw_body, signature):
        logger.warning("Signature Meta inválida — posible ataque o APP_SECRET mal configurado")
        MESSAGES_TOTAL.labels(status="error").inc()
        raise HTTPException(status_code=403, detail="Invalid signature")

    # 2. Kill switch — si está activado, ignorar mensajes (no responder)
    if _is_kill_switch_active():
        logger.warning("Kill switch activo — mensaje ignorado")
        MESSAGES_TOTAL.labels(status="ignored").inc()
        return JSONResponse({"status": "ignored", "reason": "kill_switch_active"})

    try:
        data = json.loads(raw_body)
    except json.JSONDecodeError:
        MESSAGES_TOTAL.labels(status="error").inc()
        raise HTTPException(status_code=400, detail="Invalid JSON") from None

    # 2.5. Sanitizar/validar payload de entrada
    if not _validate_meta_payload(data):
        logger.warning("Payload Meta inválido — estructura inesperada")
        MESSAGES_TOTAL.labels(status="error").inc()
        raise HTTPException(status_code=400, detail="Invalid payload structure")

    # Meta envía status updates (delivered, read) en el mismo webhook.
    # Solo procesamos mensajes entrantes, ignoramos status.
    try:
        entry = data["entry"][0]
        changes = entry["changes"][0]
        value = changes["value"]
    except (KeyError, IndexError):
        return JSONResponse({"status": "ignored", "reason": "no_entry"})

    # Si es un status update (delivered/read/sent), ack y salir
    if "statuses" in value:
        return JSONResponse({"status": "ignored", "reason": "status_update"})

    messages = value.get("messages", [])
    if not messages:
        return JSONResponse({"status": "ignored", "reason": "no_messages"})

    msg = messages[0]
    msg_id = msg.get("id", "")
    msg_type = msg.get("type", "")

    # 3. Deduplicación
    if _is_duplicate(msg_id):
        logger.info("Mensaje duplicado ignorado: %s", msg_id)
        MESSAGES_TOTAL.labels(status="duplicate").inc()
        DEDUP_HITS.inc()
        return JSONResponse({"status": "ignored", "reason": "duplicate"})

    # Procesamos mensajes interactivos (button_reply, list_reply) como texto
    if msg_type == "interactive":
        interactive = msg.get("interactive", {})
        int_type = interactive.get("type", "")
        if int_type == "button_reply":
            # Cliente tocó un botón Quick Reply
            button_id = interactive.get("button_reply", {}).get("id", "")
            button_title = interactive.get("button_reply", {}).get("title", "")
            logger.info("🔘 Button reply: id=%s title=%s", button_id, button_title)

            # Mapear IDs especiales a texto que Dify entiende
            if button_id == "custom_qty":
                # Bridge maneja localmente: NO llamar a Dify
                from_phone_interactive = value.get("contacts", [{}])[0].get("wa_id", "")
                if from_phone_interactive:
                    await _send_whatsapp_message(
                        from_phone_interactive,
                        "Por favor, escriba la cantidad que necesita (solo el número, mínimo 3).",
                    )
                MESSAGES_TOTAL.labels(status="ok").inc()
                logger.info("✍️ custom_qty → pedido cantidad manual")
                return JSONResponse({"status": "ok", "message_id": msg_id, "handled": "custom_qty"})

            elif button_id == "custom_combo":
                from_phone_interactive = value.get("contacts", [{}])[0].get("wa_id", "")
                if from_phone_interactive:
                    await _send_whatsapp_message(
                        from_phone_interactive,
                        "Por favor, escriba las cantidades así: 'X botellones y Y bolsas' (ej: 3 botellones y 2 bolsas).",  # noqa: E501
                    )
                MESSAGES_TOTAL.labels(status="ok").inc()
                logger.info("✍️ custom_combo → pedido cantidades manuales")
                return JSONResponse(
                    {"status": "ok", "message_id": msg_id, "handled": "custom_combo"}
                )

            elif button_id == "ya_pague":
                text_body = "ya pagué"
            elif button_id in ("1", "2", "3", "4"):
                # Cantidad o método de pago
                text_body = button_id
            else:
                # Combinado: "3 botellones y 2 bolsas" etc
                text_body = button_id

            # Reescribir msg como texto para que el flujo continúa
            msg["text"] = {"body": text_body}
            msg_type = "text"
            logger.info("📥 interactive button → text: %s", text_body[:30])

        elif int_type == "list_reply":
            # Cliente tocó una opción del List Message (menú principal)
            list_id = interactive.get("list_reply", {}).get("id", "")
            list_title = interactive.get("list_reply", {}).get("title", "")
            logger.info("📋 List reply: id=%s title=%s", list_id, list_title)

            # El ID de la lista es el número de opción (1-5)
            text_body = list_id or list_title
            msg["text"] = {"body": text_body}
            msg_type = "text"
            logger.info("📥 list reply → text: %s", text_body[:30])
        else:
            # Tipo interactivo desconocido, responder como texto
            from_phone = value.get("contacts", [{}])[0].get("wa_id", "")
            if from_phone:
                await _send_whatsapp_message(
                    from_phone,
                    "Disculpe, no logré entender 🤔 Por favor, envíe el número de la opción que desea (1️⃣ a 5️⃣).",  # noqa: E501
                )
            MESSAGES_TOTAL.labels(status="ignored").inc()
            return JSONResponse({"status": "ignored", "reason": "interactive_unknown"})

    # Procesamos texto Y ubicaciones GPS (location). Otros tipos (image, audio)
    # se responden con un mensaje amable pidiendo texto.
    if msg_type == "location":
        # WhatsApp envía {latitude, longitude, name?, address?} cuando el cliente
        # usa el botón 📍 para compartir su ubicación.
        location = msg.get("location", {})
        latitude = location.get("latitude")
        longitude = location.get("longitude")
        name = location.get("name", "")
        address = location.get("address", "")

        if latitude is None or longitude is None:
            logger.warning("Mensaje location sin coordenadas válidas")
            MESSAGES_TOTAL.labels(status="ignored").inc()
            return JSONResponse({"status": "ignored", "reason": "location_no_coords"})

        # Construir texto descriptivo de la ubicación para Dify
        # Prioridad: address + name > name > "GPS: lat, lng"
        location_parts = []
        if address:
            location_parts.append(address)
        if name:
            location_parts.append(name)
        if not location_parts:
            location_parts.append(f"GPS: {latitude}, {longitude}")
        # Siempre incluir coordenadas para que Valentina/despachador las tenga
        location_parts.append(f"(coordenadas: {latitude}, {longitude})")

        # Convertir a texto que Dify procesará como si fuera la dirección
        text_body = "Mi ubicación: " + ", ".join(location_parts)
        logger.info(
            "📍 GPS recibido - phone:%s lat=%f lng=%f",
            _phone_hash(value.get("contacts", [{}])[0].get("wa_id", ""))[:8],
            latitude,
            longitude,
        )
        # Marcar como texto para que el flujo continúe normal
        msg_type = "text"
        # Reescribir el mensaje para que el flujo de texto lo procese
        msg["text"] = {"body": text_body}

    # NEXO P0: Manejo de notas de voz (usuarios 40+ las envían frecuentemente)
    if msg_type == "audio":
        from_phone = value.get("contacts", [{}])[0].get("wa_id", "")
        if from_phone:
            await _send_whatsapp_message(
                from_phone,
                "Prefiero leer su mensaje escrito. Puede escribirme lo que necesita aquí mismo. 💧",
            )
        MESSAGES_TOTAL.labels(status="ignored").inc()
        logger.info("🎤 Nota de voz recibida — redirigiendo a texto")
        return JSONResponse({"status": "ignored", "reason": "audio_redirected"})

    # Otros tipos no soportados (image, video, document, sticker)
    if msg_type != "text":
        from_phone = value.get("contacts", [{}])[0].get("wa_id", "")
        if from_phone:
            await _send_whatsapp_message(
                from_phone,
                "Por favor, escríbame lo que necesita. Le respondo enseguida. 💧",
            )
        MESSAGES_TOTAL.labels(status="ignored").inc()
        return JSONResponse({"status": "ignored", "reason": f"type_{msg_type}"})

    # 4. Extraer teléfono y texto
    from_phone = value.get("contacts", [{}])[0].get("wa_id", "")
    text_body = msg.get("text", {}).get("body", "").strip()

    if not from_phone or not text_body:
        logger.warning("Mensaje sin teléfono o texto válido")
        MESSAGES_TOTAL.labels(status="ignored").inc()
        return JSONResponse({"status": "ignored", "reason": "missing_fields"})

    # 4.5. Rate limit por teléfono (antes de procesar)
    if not await _check_phone_rate_limit(from_phone):
        await _send_whatsapp_message(
            from_phone,
            "Demasiadas solicitudes. Por favor, espere un momento y vuelva a intentarlo. 💧",
        )
        MESSAGES_TOTAL.labels(status="rate_limited_phone").inc()
        return JSONResponse(
            {"status": "rate_limited", "message_id": msg_id, "reason": "phone_rate_limit"}
        )

    # 4.6. Sanitizar texto de entrada (previene inyección, control chars, etc.)
    text_body = _sanitize_input_text(text_body)

    ph_short = _phone_hash(from_phone)[:8]
    ph_short_full = _phone_hash(from_phone)
    logger.info(
        "📥 msg_from=phone:%s len=%d text_preview=%s", ph_short, len(text_body), text_body[:30]
    )

    # Bug 2 fix: GUARD DE MÍNIMOS — si cliente ESCRIBE número < 3 como cantidad
    # NO aplicar si viene de botón interactivo (list_reply o button_reply)
    # porque "1" puede ser selección del menú, no cantidad
    is_from_interactive = msg.get("type") == "interactive" or msg.get("_was_interactive", False)
    if not is_from_interactive:
        qty_match = re.match(r"^(\d+)$", text_body.strip())
        if qty_match:
            qty_num = int(qty_match.group(1))
            if qty_num < 3:
                await _send_whatsapp_message(
                    from_phone,
                    "Claro, con gusto le atendemos. Le comento que el pedido mínimo es de "
                    "3 unidades. ¿Desea pedir 3 o más?",
                )
                MESSAGES_TOTAL.labels(status="ok").inc()
                logger.info("🚫 Cantidad %d rechazada (mínimo 3) para phone:%s", qty_num, ph_short)
                return JSONResponse(
                    {"status": "ok", "message_id": msg_id, "handled": "minimum_rejected"}
                )

    # 4.5. GUARD DE HORARIO (determinístico, no depende del LLM)
    # Si está fuera de horario laboral (Lun-Sáb 8am-6pm America/Caracas),
    # responder directamente con mensaje fuera de horario SIN llamar a Dify.
    # El mensaje se guarda en SQLite para que el dispatcher lo procese mañana.
    if not _is_within_business_hours():
        now_caracas = datetime.now(CARACAS_TZ)
        logger.info(
            "🕐 Fuera de horario (Caracas %s día=%d) — respondiendo mensaje programado para phone:%s",  # noqa: E501
            now_caracas.strftime("%H:%M"),
            now_caracas.weekday(),
            ph_short,
        )
        # Guardar el mensaje en SQLite como "scheduled" para que el dispatcher lo procese
        try:
            conn = sqlite3.connect(SQLITE_PATH)
            conn.execute(
                "INSERT INTO orders (phone_hash, product_description, status, created_at) VALUES (?, ?, ?, ?)",  # noqa: E501
                (
                    _phone_hash(from_phone),
                    f"[FUERA HORARIO] {text_body[:200]}",
                    "scheduled",
                    time.time(),
                ),
            )
            conn.commit()
            conn.close()
        except sqlite3.Error as e:
            logger.error("Error guardando mensaje fuera de horario: %s", e)

        # Enviar mensaje fuera de horario al cliente (sin consultar Dify)
        sent = await _send_whatsapp_message(from_phone, _get_out_of_hours_message())
        if sent:
            MESSAGES_TOTAL.labels(status="ok").inc()
            META_SEND.labels(status="ok").inc()
            logger.info("Mensaje fuera de horario enviado a phone:%s", ph_short)
        else:
            MESSAGES_TOTAL.labels(status="error").inc()
            META_SEND.labels(status="error").inc()
            logger.error("No se pudo enviar mensaje fuera de horario a phone:%s", ph_short)

        RESPONSE_TIME.observe(time.time() - request_start)
        return JSONResponse(
            {
                "status": "out_of_hours",
                "message_id": msg_id,
                "scheduled_for_tomorrow": True,
            }
        )

    # 5. INTENTAR FLUJO DETERMINÍSTICO PRIMERO (latencia <1s)
    # Si el bridge puede manejar el mensaje sin Dify, lo hace
    contact_name = value.get("contacts", [{}])[0].get("profile", {}).get("name", "")
    det_result = _handle_deterministic(
        ph_short_full, text_body, from_phone, contact_name, msg, value
    )

    if det_result is not None:
        # El bridge manejó el mensaje determinísticamente
        answer = det_result["answer"]
        interactive = det_result.get("interactive")

        logger.info(
            "⚡ Respuesta determinística para phone:%s (state=%s)",
            ph_short,
            _get_state(ph_short_full).get("state"),
        )

        # Enviar respuesta (interactiva o texto)
        if interactive:
            if interactive["type"] == "list":
                sent = await _send_whatsapp_interactive(
                    from_phone,
                    interactive["body"],
                    "list",
                    list_sections=interactive.get("list_sections", []),
                    button_text=interactive.get("button_text", "Ver opciones"),
                )
            elif interactive["type"] == "button":
                sent = await _send_whatsapp_interactive(
                    from_phone,
                    interactive["body"],
                    "button",
                    buttons=interactive.get("buttons", []),
                )
            else:
                sent = await _send_whatsapp_message(from_phone, answer)
        else:
            sent = await _send_whatsapp_message(from_phone, answer)

        if sent:
            MESSAGES_TOTAL.labels(status="ok").inc()
            META_SEND.labels(status="ok").inc()
            RESPONSE_TIME.observe(time.time() - request_start)
            logger.info(
                "⚡ Mensaje determinístico enviado a phone:%s (len=%d)", ph_short, len(answer)
            )
        else:
            MESSAGES_TOTAL.labels(status="error").inc()
            META_SEND.labels(status="error").inc()

        return JSONResponse({"status": "ok", "message_id": msg_id, "mode": "deterministic"})

    # 6. Si el bridge NO pudo manejarlo, llamar a Dify (para opción 4, 5, o mensajes inesperados)
    logger.info("🤖 Delegando a Dify para phone:%s (no determinístico)", ph_short)
    existing_conv = _get_conversation_id(from_phone)
    dify_result = await _call_dify(text_body, from_phone, existing_conv)

    if not dify_result or not dify_result.get("answer"):
        logger.error("Dify no respondió para phone:%s", ph_short)
        DIFY_CALLS.labels(status="error").inc()
        MESSAGES_TOTAL.labels(status="error").inc()
        # Alerta crítica: Dify caído
        await _alert_critical(
            "Dify no responde",
            f"phone:{ph_short} msg_id={msg_id}\nDify API: {DIFY_API_URL}",
        )
        await _send_whatsapp_message(
            from_phone,
            "Disculpe, en este momento tengo dificultades técnicas. "
            "Un asesor le contactará en breve. ¡Gracias! 💧",
        )
        RESPONSE_TIME.observe(time.time() - request_start)
        return JSONResponse({"status": "error", "reason": "dify_failed"})

    DIFY_CALLS.labels(status="ok").inc()
    answer = dify_result["answer"]
    new_conv = dify_result.get("conversation_id", "")

    # 6. Persistir conversation_id
    if new_conv and new_conv != existing_conv:
        _save_conversation_id(from_phone, new_conv)

    # 7. Enviar respuesta al cliente via Meta
    # Detectar si la respuesta de Valentina debe ir como botones interactivos
    # Bug 1 fix: corregir total en respuesta antes de enviar (determinístico)
    # SIEMPRE corregir el total si hay un pedido conocido para este teléfono
    ph_hash = _phone_hash(from_phone)

    # Si es confirmación de pedido, calcular y guardar el total
    if "✅ Pedido confirmado" in answer or "✅ Pedido registrado" in answer:
        order_payload_fix = _build_order_payload(
            from_phone=from_phone,
            answer=answer,
            contact_name=value.get("contacts", [{}])[0].get("profile", {}).get("name", ""),
            conversation_id=new_conv,
        )
        # P0-1: Guardar total para correcciones futuras (persistente)
        _save_order_totals(
            ph_hash,
            order_payload_fix["total_eur"],
            order_payload_fix["qty_botellones"],
            order_payload_fix["qty_hielo"],
        )
        answer = _fix_total_in_response(answer, order_payload_fix)
        logger.info(
            "🔧 Total corregido en confirmación para phone:%s total=€%.2f",
            ph_short,
            order_payload_fix["total_eur"],
        )

    # Para TODAS las respuestas que contengan "€", corregir el total si tenemos uno guardado
    elif "€" in answer:
        saved = _get_order_totals(ph_hash)
        if saved:
            # Crear payload temporal con el total guardado
            temp_payload = {"total_eur": saved["total"], "_llm_total": 0}
            answer = _fix_total_in_response(answer, temp_payload)
            logger.info(
                "🔧 Total corregido en respuesta posterior para phone:%s total=€%.2f",
                ph_short,
                saved["total"],
            )

    # Limpiar state si el pedido se completa ("Gracias por su compra")
    if "Gracias por su compra" in answer or "pedido está confirmado y en camino" in answer:
        _clear_order_totals(ph_hash)
        logger.info("🧹 State limpiado para phone:%s (pedido completado)", ph_short)

    msg_type_info = _detect_message_type(answer)

    if msg_type_info["type"] == "list":
        sent = await _send_whatsapp_interactive(
            from_phone,
            msg_type_info["body"],
            "list",
            list_sections=msg_type_info.get("list_sections", []),
            button_text=msg_type_info.get("button_text", "Ver opciones"),
        )
    elif msg_type_info["type"] == "button":
        sent = await _send_whatsapp_interactive(
            from_phone,
            msg_type_info["body"],
            "button",
            buttons=msg_type_info.get("buttons", []),
        )
    else:
        sent = await _send_whatsapp_message(from_phone, answer)
    if not sent:
        logger.error("No se pudo enviar respuesta a phone:%s", ph_short)
        META_SEND.labels(status="error").inc()
        MESSAGES_TOTAL.labels(status="error").inc()
        # Alerta crítica: Meta token expirado
        await _alert_critical(
            "Meta send API falló",
            f"phone:{ph_short} — posible token expirado (rotar cada 60 días)",
        )
        RESPONSE_TIME.observe(time.time() - request_start)
        return JSONResponse({"status": "error", "reason": "meta_send_failed"})

    META_SEND.labels(status="ok").inc()

    # 8. Si la respuesta contiene "✅ Pedido registrado", guardar orden en SQLite
    #    + enviar a Google Sheets para que otros agentes/skills puedan consumir
    if "✅ Pedido registrado" in answer or "✅ Pedido confirmado" in answer:
        try:
            conn = sqlite3.connect(SQLITE_PATH)
            conn.execute(
                "INSERT INTO orders (phone_hash, product_description, status, created_at) VALUES (?, ?, ?, ?)",  # noqa: E501
                (_phone_hash(from_phone), answer[:500], "pending", time.time()),
            )
            conn.commit()
            conn.close()
            ORDERS_TOTAL.inc()
            logger.info("Orden guardada en SQLite para phone:%s", ph_short)
            # Notificar al Líder del nuevo pedido
            await _send_telegram(f"💧 <b>Nuevo pedido</b>\n\n<code>{answer[:300]}</code>")

            # --- Enviar a Google Sheets (no bloquea el webhook) ---
            order_payload = _build_order_payload(
                from_phone=from_phone,
                answer=answer,
                contact_name=value.get("contacts", [{}])[0].get("profile", {}).get("name", ""),
                conversation_id=new_conv,
            )
            try:
                from skills.google_sheets import save_order_async

                save_order_async(order_payload)
                logger.info("Pedido enviado a Google Sheets para phone:%s", ph_short)
            except ImportError:
                logger.warning("skills.google_sheets no disponible — pedido NO fue a Sheets")
            except Exception as gs_err:
                logger.error("Error enviando a Google Sheets: %s", gs_err)

        except sqlite3.Error as e:
            logger.error("Error guardando orden: %s", e)

    # Detectar escalamientos
    if "transferiré a un asesor" in answer:
        ESCALATIONS_TOTAL.inc()

    MESSAGES_TOTAL.labels(status="ok").inc()
    RESPONSE_TIME.observe(time.time() - request_start)
    return JSONResponse({"status": "ok", "message_id": msg_id})


# ============================================================================
# Punto de entrada (para desarrollo; producción usa uvicorn via systemd)
# ============================================================================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "bridge:app",
        host=BRIDGE_HOST,
        port=BRIDGE_PORT,
        log_level=LOG_LEVEL.lower(),
        access_log=False,  # los logs custom ya son suficientes
    )
