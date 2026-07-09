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

import hashlib
import hmac
import json
import logging
import os
import sqlite3
import time
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta, timezone
import sys
sys.path.insert(0, '/mnt/ssd_trabajo/hermes-agent')


import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.responses import Response as RawResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

# Métricas Prometheus
try:
    from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

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

DIFY_API_URL = os.getenv("DIFY_API_URL", "http://localhost/v1/chat-messages")
DIFY_API_KEY = os.getenv("DIFY_API_KEY", "")

BRIDGE_HOST = os.getenv("BRIDGE_HOST", "0.0.0.0")
BRIDGE_PORT = int(os.getenv("BRIDGE_PORT", "8000"))
LOG_LEVEL = os.getenv("BRIDGE_LOG_LEVEL", "INFO").upper()

RATE_PER_PHONE = int(os.getenv("RATE_LIMIT_PER_PHONE", "30"))
RATE_PER_IP = int(os.getenv("RATE_LIMIT_PER_IP", "100"))

SQLITE_PATH = os.getenv("SQLITE_PATH", "/mnt/ssd_trabajo/hermes-agent/data/conversations.db")

LOG_SALT = os.getenv("LOG_SALT", "change-this-in-production")

# Telegram (alerts + kill switch). Opcional: si no está configurado, se omite.
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "1663148211")  # Líder por defecto
TELEGRAM_ENABLED = bool(TELEGRAM_BOT_TOKEN) and TELEGRAM_AVAILABLE

# Kill switch: archivo centinela. Si existe, el bridge se detiene.
KILL_SWITCH_FILE = os.getenv("KILL_SWITCH_FILE", "/tmp/valentina.kill")

# Cliente HTTP reutilizable (connection pooling)
_http_client: httpx.AsyncClient | None = None
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
BUSINESS_HOURS_START = int(os.getenv("BUSINESS_HOURS_START", "8"))  # 8 AM
BUSINESS_HOURS_END = int(os.getenv("BUSINESS_HOURS_END", "18"))  # 6 PM
BUSINESS_HOURS_DAYS = os.getenv(
    "BUSINESS_HOURS_DAYS", "1,2,3,4,5,6"
)  # Lun-Sáb (1=Lun, 6=Sáb, 0=Dom)
CARACAS_TZ = timezone(timedelta(hours=-4))  # America/Caracas UTC-4

# Mensaje fuera de horario (verbatim del System Prompt v4)
def _get_out_of_hours_message():
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
            return (f"¡Hola! 👋 Abrimos en {minutes_to_open} minutos. "
                    f"Por favor escríbame a las {BUSINESS_HOURS_START}:00am. ¡Gracias! 💧")
    
    # Si es día de apertura pero falta más de 30 min
    if day in open_days and now.hour < BUSINESS_HOURS_START:
        return (f"¡Hola! 👋 En este momento estamos fuera de horario. "
                f"Abrimos a las {BUSINESS_HOURS_START}:00am. "
                f"He registrado tu mensaje y te responderemos al abrir. ¡Gracias! 💧")
    
    # Si es después del cierre o día no laboral
    return ("¡Hola! 👋 En este momento estamos fuera de horario (Lun-Sáb, 8am-6pm).\n"
            "He registrado tu mensaje y lo programaremos para la primera hora de mañana. "
            "Un asesor te contactará para confirmar. ¡Gracias! 💧")


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
        def labels(self, *a, **kw):
            return self

        def inc(self, *a, **kw):
            pass

        def observe(self, *a, **kw):
            pass

        def set(self, *a, **kw):
            pass

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
            h = hashlib.sha256(f"{LOG_SALT}:{phone}".encode()).hexdigest()[:12]
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
    expected = "sha256=" + hmac.new(META_APP_SECRET.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header)


async def _send_whatsapp_message(phone: str, text: str) -> bool:
    """Envía un mensaje de texto via Meta Graph API."""
    if not META_ACCESS_TOKEN or not META_PHONE_NUMBER_ID:
        logger.error("META_ACCESS_TOKEN o META_PHONE_NUMBER_ID no configurados")
        return False
    url = f"https://graph.facebook.com/{META_API_VERSION}" f"/{META_PHONE_NUMBER_ID}/messages"
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
    buttons: list = None,
    list_sections: list = None,
    button_text: str = "Ver opciones",
    header_text: str = None,
    footer_text: str = None,
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

    url = (
        f"https://graph.facebook.com/{META_API_VERSION}"
        f"/{META_PHONE_NUMBER_ID}/messages"
    )
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


def _detect_message_type(answer: str) -> dict:
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
                        {"id": "1", "title": "Recarga de botellones", "description": "Agua €1.00 c/u"},
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
    if ("cómo desea pagar" in ans_lower or "como desea pagar" in ans_lower) and (
        "pago móvil" in ans_lower or "efectivo" in ans_lower
    ):
        return {
            "type": "button",
            "body": answer.split("¿Cómo")[0].strip()
            + "\n\n¿Cómo desea pagar?",
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


async def _call_dify(query: str, phone: str, conv_id: str | None) -> dict | None:
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
            r"(?:coordenadas:|GPS:)\s*(-?\d+[.,]?\d*)\s*,\s*(-?\d+[.,]?\d*)",
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
            await _send_telegram(
                "✅ <b>Valentina Bridge iniciado</b>\n\n💧 Estación H2O lista para atender."
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
    yield

    # Graceful shutdown
    logger.info("Cerrando conexiones...")
    if _telegram_bot:
        await _send_telegram(
            "⚠️ <b>Valentina Bridge detenido</b>\n\nLos mensajes no se responden temporalmente."
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
                        "Por favor, escriba las cantidades así: 'X botellones y Y bolsas' (ej: 3 botellones y 2 bolsas).",
                    )
                MESSAGES_TOTAL.labels(status="ok").inc()
                logger.info("✍️ custom_combo → pedido cantidades manuales")
                return JSONResponse({"status": "ok", "message_id": msg_id, "handled": "custom_combo"})

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
                    "Disculpe, no entendí. Por favor, envíe el número de la opción que desea (1-5).",
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
        logger.info("📍 GPS recibido - phone:%s lat=%f lng=%f",
            _phone_hash(value.get("contacts", [{}])[0].get("wa_id", ""))[:8],
            latitude, longitude)
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
    logger.info(
        "📥 msg_from=phone:%s len=%d text_preview=%s", ph_short, len(text_body), text_body[:30]
    )

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
    # Detectar si la respuesta de Valentina debe ir como botones interactivos
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
                "INSERT INTO orders (phone_hash, product_description, status, created_at) VALUES (?, ?, ?, ?)",
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
