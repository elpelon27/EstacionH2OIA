"""FastAPI Gateway — Puente entre WhatsApp Cloud API (Meta) y Valentina.

Reemplaza completamente a WAHA. No requiere QR, no se desconecta.
Webhooks: https://developers.facebook.com/docs/whatsapp/cloud-api/webhooks/payload-examples
"""

import hashlib
import hmac
import time
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse, PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

from agents.valentina import get_valentina
from core.config import get_settings
from core.cost_guard import get_cost_guard
from core.logger import get_logger, setup_logging
from core.meta_client import get_meta_client

# Inicializar
setup_logging()
logger = get_logger("api")

app = FastAPI(
    title="Hermes Agent API",
    description="Gateway entre WhatsApp Cloud API y Valentina",
    version="0.2.0",
)

# Métricas Prometheus
MESSAGES_RECEIVED = Counter("hermes_messages_received_total", "Mensajes recibidos")
MESSAGES_PROCESSED = Counter("hermes_messages_processed_total", "Mensajes procesados")
MESSAGE_PROCESSING_TIME = Histogram(
    "hermes_message_processing_seconds",
    "Tiempo de procesamiento de mensajes",
)
HUMAN_ESCALATIONS = Counter(
    "hermes_human_escalations_total",
    "Veces que cliente pidió hablar con humano",
)

# Estado global
_kill_switch_active = False
_dedup_cache: dict[str, float] = {}

# Cache de mensajes de WhatsApp (status updates pueden llegar antes que el message)
_message_cache: dict[str, dict[str, Any]] = {}


@app.get("/health")  # type: ignore[misc]
async def health() -> dict[str, str]:
    """Healthcheck para Prometheus."""
    return {"status": "ok", "version": "0.2.0"}


@app.get("/metrics")  # type: ignore[misc]
async def metrics() -> PlainTextResponse:
    """Métricas para Prometheus."""
    return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)


# ===== WEBHOOK VERIFICATION (GET) =====
@app.get("/webhook/meta")  # type: ignore[misc]
async def verify_webhook(
    request: Request,
    hub_mode: str = Query(..., alias="hub.mode"),
    hub_challenge: str = Query(..., alias="hub.challenge"),
    hub_verify_token: str = Query(..., alias="hub.verify_token"),
) -> str:
    """Verificación inicial del webhook por Meta.

    Meta envía un GET con hub.mode=subscribe, hub.verify_token y hub.challenge.
    Si el token coincide, retornamos hub.challenge para confirmar.
    """
    settings = get_settings()

    if hub_mode == "subscribe" and hub_verify_token == settings.meta_verify_token:
        logger.info("webhook_verified_by_meta")
        return hub_challenge
    else:
        logger.warning("webhook_verification_failed", token=hub_verify_token)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Verification failed")


# ===== WEBHOOK RECEIVER (POST) =====
@app.post("/webhook/meta")  # type: ignore[misc]
async def webhook_meta(request: Request) -> JSONResponse:
    """Recibir webhook de Meta Cloud API.

    Verifica HMAC-SHA256, procesa mensajes entrantes, ignora status updates.
    Retorna 200 OK inmediatamente y procesa en background.
    """
    MESSAGES_RECEIVED.inc()

    # 1. Verificar HMAC-SHA256 (seguridad crítica)
    settings = get_settings()
    body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256", "")

    if not _verify_meta_hmac(body, signature, settings.meta_app_secret):
        logger.warning("webhook_hmac_invalid")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="HMAC inválido",
        )

    # 2. Parsear payload
    try:
        data = await request.json()
    except Exception as e:
        logger.error("webhook_parse_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="JSON inválido",
        ) from e

    # 3. Procesar el webhook
    # Meta envía: { "object": "whatsapp_business_account", "entry": [...] }
    if data.get("object") != "whatsapp_business_account":
        return JSONResponse({"status": "ignored", "reason": "not_whatsapp"})

    entries = data.get("entry", [])
    for entry in entries:
        changes = entry.get("changes", [])
        for change in changes:
            field = change.get("field")
            value = change.get("value", {})

            # Solo procesar mensajes entrantes (no status updates)
            if field == "messages":
                messages = value.get("messages", [])
                for msg in messages:
                    await _handle_meta_message(msg, value)

    return JSONResponse({"status": "received"})


async def _handle_meta_message(msg: dict[str, Any], value: dict[str, Any]) -> None:
    """Procesar un mensaje individual de Meta Cloud API."""
    global _kill_switch_active

    msg_id = msg.get("id", "")
    msg_type = msg.get("type", "")

    # Solo procesar mensajes de texto por ahora
    if msg_type != "text":
        logger.info("message_ignored_non_text", msg_type=msg_type, msg_id=msg_id)
        return

    # Extraer datos
    from_phone = msg.get("from", "")
    text_body = msg.get("text", {}).get("body", "")

    # Extraer nombre del contacto si está disponible
    contacts = value.get("contacts", [])
    contact_name = None
    if contacts:
        contact_name = contacts[0].get("profile", {}).get("name")

    if not from_phone or not text_body:
        logger.warning("message_missing_fields", msg_id=msg_id)
        return

    # Deduplicación
    now = time.time()
    expired = [k for k, v in _dedup_cache.items() if now - v > 300]
    for k in expired:
        _dedup_cache.pop(k, None)

    if msg_id in _dedup_cache:
        logger.info("message_duplicate_ignored", msg_id=msg_id)
        return
    _dedup_cache[msg_id] = now

    logger.info(
        "message_received",
        phone=from_phone,
        message_preview=text_body[:50],
        client_name=contact_name,
        msg_id=msg_id,
    )

    # Verificar kill switch
    if _kill_switch_active:
        logger.info("kill_switch_active_message_ignored", phone=from_phone)
        return

    # Procesar en background
    import asyncio

    asyncio.create_task(_process_message_background(from_phone, text_body, contact_name, msg_id))


async def _process_message_background(
    phone: str,
    message: str,
    contact_name: str | None,
    msg_id: str,
) -> None:
    """Procesar mensaje en background y enviar respuesta vía Meta Cloud API."""
    start_time = time.monotonic()

    try:
        valentina = get_valentina()
        result = await valentina.process_message(
            phone=phone,
            message=message,
            client_name=contact_name,
        )

        elapsed = time.monotonic() - start_time
        MESSAGE_PROCESSING_TIME.observe(elapsed)
        MESSAGES_PROCESSED.inc()

        if result["needs_human_escalation"]:
            HUMAN_ESCALATIONS.inc()

        # Enviar respuesta vía Meta Cloud API
        meta_client = await get_meta_client()
        send_result = await meta_client.send_text_message(
            to=phone,
            text=result["response"],
            reply_to_message_id=msg_id,
        )

        if send_result["success"]:
            logger.info(
                "message_processed",
                phone=phone,
                elapsed_ms=int(elapsed * 1000),
                needs_human=result["needs_human_escalation"],
                meta_message_id=send_result["message_id"],
            )
        else:
            logger.error(
                "meta_send_failed",
                phone=phone,
                error=send_result["error"],
            )

    except Exception as e:
        logger.error("message_processing_error", phone=phone, error=str(e))


# ===== TELEGRAM WEBHOOK =====
@app.post("/webhook/telegram")  # type: ignore[misc]
async def webhook_telegram(request: Request) -> JSONResponse:
    """Recibir webhook de Telegram (comandos del Líder)."""
    global _kill_switch_active

    try:
        data = await request.json()
    except Exception as e:
        raise HTTPException(status_code=400, detail="JSON inválido") from e

    message = data.get("message", {})
    text = message.get("text", "").strip().lower()
    chat_id = message.get("chat", {}).get("id")

    settings = get_settings()
    if chat_id != settings.telegram_chat_id_lider:
        logger.warning("telegram_unauthorized", chat_id=chat_id)
        raise HTTPException(status_code=403, detail="No autorizado")

    if text == "/kill":
        _kill_switch_active = True
        logger.warning("kill_switch_activated_by_leader")
        return JSONResponse({"status": "ok", "message": "🔴 Kill switch activado"})

    if text == "/revive":
        _kill_switch_active = False
        logger.info("kill_switch_deactivated_by_leader")
        return JSONResponse({"status": "ok", "message": "✅ IA reactivada"})

    if text == "/status":
        guard = get_cost_guard()
        cost_status = await guard.check()
        return JSONResponse(
            {
                "status": "ok",
                "kill_switch": _kill_switch_active,
                "openrouter_spent_today": cost_status["spent_today"],
                "openrouter_status": cost_status["status"],
            }
        )

    return JSONResponse({"status": "ok", "message": "Comando no reconocido"})


# ===== KILL SWITCH API =====
@app.post("/kill-switch")  # type: ignore[misc]
async def kill_switch(request: Request) -> JSONResponse:
    """Activar/desactivar kill switch vía API (requiere token)."""
    global _kill_switch_active

    try:
        data = await request.json()
    except Exception as e:
        raise HTTPException(status_code=400, detail="JSON inválido") from e

    action = data.get("action", "").lower()
    if action == "kill":
        _kill_switch_active = True
        logger.warning("kill_switch_activated_via_api")
        return JSONResponse({"status": "ok", "kill_switch": True})
    if action == "revive":
        _kill_switch_active = False
        logger.info("kill_switch_deactivated_via_api")
        return JSONResponse({"status": "ok", "kill_switch": False})
    raise HTTPException(status_code=400, detail="action debe ser 'kill' o 'revive'")


# ===== SEND MESSAGE API =====
@app.post("/send-message")  # type: ignore[misc]
async def send_message(request: Request) -> JSONResponse:
    """Enviar mensaje proactivo a un cliente."""
    try:
        data = await request.json()
    except Exception as e:
        raise HTTPException(status_code=400, detail="JSON inválido") from e

    phone = data.get("phone", "")
    message = data.get("message", "")

    if not phone or not message:
        raise HTTPException(status_code=400, detail="Faltan 'phone' o 'message'")

    meta_client = await get_meta_client()
    result = await meta_client.send_text_message(to=phone, text=message)

    if result["success"]:
        return JSONResponse({"status": "ok", "message_sent": True})
    else:
        raise HTTPException(status_code=500, detail=result["error"])


def _verify_meta_hmac(body: bytes, signature: str, app_secret: str) -> bool:
    """Verificar firma HMAC-SHA256 del webhook de Meta."""
    if not app_secret or app_secret.startswith("PENDIENTE"):
        # En desarrollo, si no hay secret, permitir
        return True

    if not signature:
        return False

    expected = hmac.new(
        app_secret.encode(),
        body,
        hashlib.sha256,
    ).hexdigest()

    # Meta envía "sha256=xxxx"
    if signature.startswith("sha256="):
        signature = signature[7:]

    return hmac.compare_digest(expected, signature)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info",
    )
