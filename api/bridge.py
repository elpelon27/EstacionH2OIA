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

import os
import sqlite3
import hashlib
import hmac
import json
import time
import logging
import asyncio
import signal
from contextlib import asynccontextmanager
from typing import Optional
from datetime import datetime, timezone, timedelta

import httpx
from fastapi import FastAPI, Request, Response, HTTPException, Depends
from fastapi.responses import PlainTextResponse, JSONResponse, Response as RawResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# Métricas Prometheus
try:
    from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False

# Telegram alerts (opcional, no bloquea si no está configurado)
try:
    import telegram
    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False

# ============================================================================
# Configuración (todas las secrets via variables de entorno)
# ============================================================================

META_ACCESS_TOKEN = os.getenv("META_ACCESS_TOKEN", "")
META_PHONE_NUMBER_ID = os.getenv("META_PHONE_NUMBER_ID", "")
META_APP_SECRET = os.getenv("META_APP_SECRET", "")
META_VERIFY_TOKEN = os.getenv("META_VERIFY_TOKEN", "")
META_API_VERSION = os.getenv("META_API_VERSION", "v25.0")

DIFY_API_URL = os.getenv(
    "DIFY_API_URL", "http://localhost/v1/chat-messages"
)
DIFY_API_KEY = os.getenv("DIFY_API_KEY", "")

BRIDGE_HOST = os.getenv("BRIDGE_HOST", "0.0.0.0")
BRIDGE_PORT = int(os.getenv("BRIDGE_PORT", "8000"))
LOG_LEVEL = os.getenv("BRIDGE_LOG_LEVEL", "INFO").upper()

RATE_PER_PHONE = int(os.getenv("RATE_LIMIT_PER_PHONE", "30"))
RATE_PER_IP = int(os.getenv("RATE_LIMIT_PER_IP", "100"))

SQLITE_PATH = os.getenv(
    "SQLITE_PATH", "/mnt/ssd_trabajo/hermes-agent/data/conversations.db"
)

LOG_SALT = os.getenv("LOG_SALT", "change-this-in-production")

# Telegram (alerts + kill switch). Opcional: si no está configurado, se omite.
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "1663148211")  # Líder por defecto
TELEGRAM_ENABLED = bool(TELEGRAM_BOT_TOKEN) and TELEGRAM_AVAILABLE

# Kill switch: archivo centinela. Si existe, el bridge se detiene.
KILL_SWITCH_FILE = os.getenv("KILL_SWITCH_FILE", "/tmp/valentina.kill")

# Cliente HTTP reutilizable (connection pooling)
_http_client: Optional[httpx.AsyncClient] = None
_telegram_bot = None

# Cache de deduplicación (message_id → timestamp). En memoria, 5 min TTL.
# En producción con >1000 msg/día, migrar a Redis. Para Estación H2O basta.
_seen_messages: dict[str, float] = {}
DEDUP_TTL_SECONDS = 300  # 5 minutos

# Hora de arranque para uptime
START_TIME = time.time()

# --- Horario laboral (America/Caracas UTC-4) ---
# Publicado al cliente: "Lunes a Sábado, 8:00 AM - 6:00 PM"
# El .env interno decía 07:40 pero el prompt oficial publica 8:00 AM.
# Usamos el horario publicado al cliente.
BUSINESS_HOURS_START = int(os.getenv("BUSINESS_HOURS_START", "8"))   # 8 AM
BUSINESS_HOURS_END = int(os.getenv("BUSINESS_HOURS_END", "18"))      # 6 PM
BUSINESS_HOURS_DAYS = os.getenv("BUSINESS_HOURS_DAYS", "1,2,3,4,5,6")  # Lun-Sáb (1=Lun, 6=Sáb, 0=Dom)
CARACAS_TZ = timezone(timedelta(hours=-4))  # America/Caracas UTC-4

# Mensaje fuera de horario (verbatim del System Prompt v4)
OUT_OF_HOURS_MESSAGE = (
    "¡Hola! 👋 En este momento estamos fuera de horario (Lun-Sáb, 8am-6pm).\n"
    "He registrado tu mensaje y lo programaremos para la primera hora de mañana.\n"
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
# Métricas Prometheus
# ============================================================================

if PROMETHEUS_AVAILABLE:
    MESSAGES_TOTAL = Counter(
        "valentina_messages_total",
        "Mensajes entrantes de WhatsApp",
        ["status"],  # ok, ignored, error, duplicate
    )
    RESPONSE_TIME = Histogram(
        "valentina_response_time_seconds",
        "Tiempo total de respuesta (webhook → Meta send)",
        buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0),
    )
    DIFY_CALLS = Counter(
        "valentina_dify_calls_total",
        "Llamadas a Dify Chatflow",
        ["status"],  # ok, error, timeout
    )
    META_SEND = Counter(
        "valentina_meta_send_total",
        "Envíos a Meta Graph API",
        ["status"],  # ok, error
    )
    ORDERS_TOTAL = Counter(
        "valentina_orders_total",
        "Pedidos confirmados por Valentina",
    )
    ESCALATIONS_TOTAL = Counter(
        "valentina_escalations_total",
        "Escalamientos a humano",
    )
    ACTIVE_CONVERSATIONS = Gauge(
        "valentina_active_conversations",
        "Conversaciones activas (últimas 24h)",
    )
    DEDUP_HITS = Counter(
        "valentina_dedup_hits_total",
        "Mensajes duplicados ignorados",
    )
else:
    # Stubs si prometheus_client no está instalado
    class _Stub:
        def labels(self, *a, **kw): return self
        def inc(self, *a, **kw): pass
        def observe(self, *a, **kw): pass
        def set(self, *a, **kw): pass
    MESSAGES_TOTAL = RESPONSE_TIME = DIFY_CALLS = META_SEND = _Stub()
    ORDERS_TOTAL = ESCALATIONS_TOTAL = DEDUP_HITS = _Stub()
    ACTIVE_CONVERSATIONS = _Stub()


# ============================================================================
# Logging con sanitización de PII
# ============================================================================

class SanitizingFormatter(logging.Formatter):
    """Reemplaza números de teléfono por hash SHA256+salt en los logs."""

    PHONE_REGEX = __import__("re").compile(r"\+?58?\d{10,15}")

    def format(self, record: logging.LogRecord) -> str:
        msg = super().format(record)
        # Hashear cualquier cosa que parezca un teléfono venezolano
        def _hash_phone(match):
            phone = match.group(0)
            h = hashlib.sha256(
                f"{LOG_SALT}:{phone}".encode()
            ).hexdigest()[:12]
            return f"phone:{h}"

        return self.PHONE_REGEX.sub(_hash_phone, msg)


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
    conn.commit()
    conn.close()
    logger.info("SQLite inicializado en %s", SQLITE_PATH)


def _phone_hash(phone: str) -> str:
    """Hash determinístico del teléfono para almacenar sin exponer PII."""
    return hashlib.sha256(f"{LOG_SALT}:{phone}".encode()).hexdigest()[:32]


def _get_conversation_id(phone: str) -> Optional[str]:
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

limiter = Limiter(key_func=get_remote_address, default_limits=[])


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
    expected = "sha256=" + hmac.new(
        META_APP_SECRET.encode(), raw_body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature_header)


async def _send_whatsapp_message(phone: str, text: str) -> bool:
    """Envía un mensaje de texto via Meta Graph API."""
    if not META_ACCESS_TOKEN or not META_PHONE_NUMBER_ID:
        logger.error("META_ACCESS_TOKEN o META_PHONE_NUMBER_ID no configurados")
        return False
    url = (
        f"https://graph.facebook.com/{META_API_VERSION}"
        f"/{META_PHONE_NUMBER_ID}/messages"
    )
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
        resp = await _http_client.post(url, headers=headers, json=payload, timeout=10)
        if resp.status_code == 200:
            logger.info("Mensaje enviado a phone:%s (len=%d)", _phone_hash(phone)[:8], len(text))
            return True
        logger.error(
            "Meta send API error %d: %s", resp.status_code, resp.text[:200]
        )
        return False
    except httpx.HTTPError as e:
        logger.error("Error enviando a Meta: %s", e)
        return False


async def _call_dify(query: str, phone: str, conv_id: Optional[str]) -> Optional[dict]:
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
        resp = await _http_client.post(
            DIFY_API_URL, headers=headers, json=payload, timeout=30
        )
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
        f"🚨 <b>{title}</b>\n\n<code>{detail[:500]}</code>\n\n⏰ {datetime.now(timezone.utc).isoformat()}"
    )


def _is_kill_switch_active() -> bool:
    """True si el archivo centinela existe (kill switch activado via Telegram)."""
    return os.path.exists(KILL_SWITCH_FILE)


# ============================================================================
# Parser de respuestas de Valentina → estructura de pedido para Google Sheets
# ============================================================================

def _build_order_payload(
    from_phone: str,
    answer: str,
    contact_name: str,
    conversation_id: str,
) -> dict:
    """
    Parsea la respuesta de Valentina para extraer datos del pedido.

    La respuesta contiene algo como:
    "✅ Pedido confirmado: 3 botellones de agua. Dirección: Calle 69.
     💰 Total: €3.00 (págalo en bolívares al cambio BCV del día).
     ¿Cómo desea pagar? 1️⃣ Pago Móvil 2️⃣ Efectivo contra entrega."

    O con GPS:
    "✅ Pedido confirmado: 2 bolsas de hielo. Dirección: Mi ubicación: ... (coordenadas: 10.63, -71.64)..."

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

    # Total en euros
    total_match = re.search(r"[€eE][Uu]?[Rr]?[Oo]?[Ss]?\s*:?\s*(\d+[.,]?\d*)", answer)
    if total_match:
        try:
            payload["total_eur"] = float(total_match.group(1).replace(",", "."))
        except ValueError:
            pass

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
            r"coordenadas:\s*(-?\d+[.,]\d+)\s*,\s*(-?\d+[.,]\d+)",
            payload["address"],
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

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _http_client, _telegram_bot
    _init_db()
    _http_client = httpx.AsyncClient()

    # Inicializar bot de Telegram si está configurado
    if TELEGRAM_ENABLED:
        try:
            _telegram_bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)
            await _send_telegram("✅ <b>Valentina Bridge iniciado</b>\n\n💧 Estación H2O lista para atender.")
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
    yield

    # Graceful shutdown
    logger.info("Cerrando conexiones...")
    if _telegram_bot:
        await _send_telegram("⚠️ <b>Valentina Bridge detenido</b>\n\nLos mensajes no se responden temporalmente.")
    await _http_client.aclose()
    logger.info("Valentina Bridge detenido")


app = FastAPI(
    title="Valentina Bridge",
    description="Webhook Meta Cloud API → Dify Chatflow → Meta Graph API",
    version="1.0.0",
    lifespan=lifespan,
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@app.get("/")
async def root():
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
async def metrics():
    """Endpoint de métricas Prometheus para scrapeo."""
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
async def health():
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


@app.get("/webhook/meta", response_class=PlainTextResponse)
async def meta_verify(request: Request):
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
async def meta_webhook(request: Request):
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
        raise HTTPException(status_code=400, detail="Invalid JSON")

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
            "📍 Ubicación GPS recibida de phone:%s lat=%s lng=%s",
            _phone_hash(value.get("contacts", [{}])[0].get("wa_id", ""))[:8],
            latitude,
            longitude,
        )
        # Marcar como texto para que el flujo continúe normal
        msg_type = "text"
        # Reescribir el mensaje para que el flujo de texto lo procese
        msg["text"] = {"body": text_body}

    if msg_type != "text":
        from_phone = value.get("contacts", [{}])[0].get("wa_id", "")
        if from_phone:
            await _send_whatsapp_message(
                from_phone,
                "Disculpe, por ahora solo puedo recibir mensajes de texto o ubicación GPS. "
                "Por favor, envíe el número de la opción que desea (1-5).",
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

    ph_short = _phone_hash(from_phone)[:8]
    logger.info("📥 msg_from=phone:%s len=%d text_preview=%s", ph_short, len(text_body), text_body[:30])

    # 4.5. GUARD DE HORARIO (determinístico, no depende del LLM)
    # Si está fuera de horario laboral (Lun-Sáb 8am-6pm America/Caracas),
    # responder directamente con mensaje fuera de horario SIN llamar a Dify.
    # El mensaje se guarda en SQLite para que el dispatcher lo procese mañana.
    if not _is_within_business_hours():
        now_caracas = datetime.now(CARACAS_TZ)
        logger.info(
            "🕐 Fuera de horario (Caracas %s día=%d) — respondiendo mensaje programado para phone:%s",
            now_caracas.strftime("%H:%M"),
            now_caracas.weekday(),
            ph_short,
        )
        # Guardar el mensaje en SQLite como "scheduled" para que el dispatcher lo procese
        try:
            conn = sqlite3.connect(SQLITE_PATH)
            conn.execute(
                "INSERT INTO orders (phone_hash, product_description, status, created_at) VALUES (?, ?, ?, ?)",
                (_phone_hash(from_phone), f"[FUERA HORARIO] {text_body[:200]}", "scheduled", time.time()),
            )
            conn.commit()
            conn.close()
        except sqlite3.Error as e:
            logger.error("Error guardando mensaje fuera de horario: %s", e)

        # Enviar mensaje fuera de horario al cliente (sin consultar Dify)
        sent = await _send_whatsapp_message(from_phone, OUT_OF_HOURS_MESSAGE)
        if sent:
            MESSAGES_TOTAL.labels(status="ok").inc()
            META_SEND.labels(status="ok").inc()
            logger.info("Mensaje fuera de horario enviado a phone:%s", ph_short)
        else:
            MESSAGES_TOTAL.labels(status="error").inc()
            META_SEND.labels(status="error").inc()
            logger.error("No se pudo enviar mensaje fuera de horario a phone:%s", ph_short)

        RESPONSE_TIME.observe(time.time() - request_start)
        return JSONResponse({
            "status": "out_of_hours",
            "message_id": msg_id,
            "scheduled_for_tomorrow": True,
        })

    # 5. Llamar a Dify (solo si está dentro de horario)
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
                "INSERT INTO orders (phone_hash, product_description, status, created_at) VALUES (?, ?, ?, ?)",
                (_phone_hash(from_phone), answer[:500], "pending", time.time()),
            )
            conn.commit()
            conn.close()
            ORDERS_TOTAL.inc()
            logger.info("Orden guardada en SQLite para phone:%s", ph_short)
            # Notificar al Líder del nuevo pedido
            await _send_telegram(
                f"💧 <b>Nuevo pedido</b>\n\n<code>{answer[:300]}</code>"
            )

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
