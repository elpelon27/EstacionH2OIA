"""FastAPI Gateway — Puente entre WhatsApp (WAHA) y Valentina.

Endpoints:
- POST /webhook/whatsapp: Recibe mensajes de WAHA (con HMAC)
- POST /webhook/telegram: Recibe comandos del Líder
- GET  /health: Healthcheck
- POST /kill-switch: Desactiva Valentina (solo Líder)
- GET  /metrics: Métricas para Prometheus
- POST /send-message: Enviar mensaje proactivo a cliente
"""

import hashlib
import hmac
import time

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse, PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

from agents.valentina import get_valentina
from core.config import get_settings
from core.cost_guard import get_cost_guard
from core.logger import get_logger, setup_logging

# Inicializar
setup_logging()
logger = get_logger("api")

app = FastAPI(
    title="Hermes Agent API",
    description="Gateway entre WhatsApp y Valentina",
    version="0.1.0",
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


@app.get("/health")  # type: ignore[misc]
async def health() -> dict[str, str]:
    """Healthcheck para Prometheus."""
    return {"status": "ok", "version": "0.1.0"}


@app.get("/metrics")  # type: ignore[misc]
async def metrics() -> PlainTextResponse:
    """Métricas para Prometheus."""
    return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/webhook/whatsapp")  # type: ignore[misc]
async def webhook_whatsapp(request: Request) -> JSONResponse:
    """Recibir webhook de WAHA con mensaje de WhatsApp.

    Retorna 200 inmediatamente y procesa en background para evitar
    que WAHA reenvíe el webhook por timeout.
    """
    global _kill_switch_active

    MESSAGES_RECEIVED.inc()

    # 1. Verificar HMAC (seguridad crítica)
    settings = get_settings()
    body = await request.body()
    signature = request.headers.get("X-Webhook-Hmac", "")

    if not _verify_hmac(body, signature, settings.waha_webhook_secret):
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

    # 3. Extraer datos del payload de WAHA
    payload = data.get("payload", data)

    if payload.get("fromMe", False):
        return JSONResponse({"status": "ignored", "reason": "own_message"})

    phone = payload.get("from", "")
    if "@lid" not in phone:
        phone = phone.replace("@s.whatsapp.net", "").replace("@c.us", "")

    # Ignorar estados de WhatsApp y grupos
    if "status@broadcast" in phone or "@g.us" in phone:
        logger.info("webhook_ignored_status_or_group", phone=phone)
        return JSONResponse({"status": "ignored", "reason": "status_or_group"})

    message = payload.get("body", "")
    contact_name = payload.get("contact", {}).get("name")

    if not phone or not message:
        logger.warning("webhook_missing_fields", phone=phone, has_message=bool(message))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Faltan campos from o body",
        )

    logger.info("webhook_received", phone=phone, message_preview=message[:50])

    # 4. Verificar kill switch
    if _kill_switch_active:
        logger.info("kill_switch_active_message_ignored", phone=phone)
        return JSONResponse(
            {"status": "ignored", "reason": "kill_switch_active"},
            status_code=200,
        )

    # 5. Retornar 200 OK INMEDIATAMENTE a WAHA
    # Esto evita que WAHA reenvíe el webhook por timeout
    # El procesamiento se hace en background

    import asyncio

    asyncio.create_task(_process_message_background(phone, message, contact_name, payload))

    return JSONResponse({"status": "received", "processing": "async"})


async def _process_message_background(
    phone: str,
    message: str,
    contact_name: str | None,
    payload: dict,
) -> None:
    """Procesar mensaje en background y enviar respuesta vía WAHA."""
    # Deduplicación: extraer ID del mensaje
    msg_id_data = payload.get("id", {})
    if isinstance(msg_id_data, str):
        msg_id = msg_id_data
    elif isinstance(msg_id_data, dict):
        msg_id = msg_id_data.get("_serialized") or msg_id_data.get("id") or ""
    else:
        msg_id = ""

    # Usar atributos de la función para persistir el cache entre llamadas
    if not hasattr(_process_message_background, "_cache"):
        _process_message_background._cache = {}

    cache = _process_message_background._cache
    now = time.time()

    # Limpiar cache viejo (>5 minutos)
    expired = [k for k, v in cache.items() if now - v > 300]
    for k in expired:
        cache.pop(k, None)

    # Generar clave de deduplicación: phone + mensaje (ignora mayúsculas/minúsculas)
    dedup_key = f"{phone}:{message.lower().strip()}"

    # Si ya procesamos este mensaje (por ID o por contenido), ignorar
    if (msg_id and msg_id in cache) or (dedup_key in cache):
        logger.info("webhook_duplicate_ignored", phone=phone, msg_id=msg_id)
        return

    # Guardar ambos: ID y contenido
    if msg_id:
        cache[msg_id] = now
    cache[dedup_key] = now

    start_time = time.monotonic()

    try:
        valentina = get_valentina()
        result = await valentina.process_message(
            phone=phone,
            message=message,
            client_name=contact_name,
        )
        # Truncar respuesta si es muy larga (WhatsApp la partiría en múltiples burbujas)
        if len(result["response"]) > 300:
            result["response"] = result["response"][:300] + "..."

        elapsed = time.monotonic() - start_time
        MESSAGE_PROCESSING_TIME.observe(elapsed)
        MESSAGES_PROCESSED.inc()

        if result["needs_human_escalation"]:
            HUMAN_ESCALATIONS.inc()

        # Enviar respuesta vía WAHA
        msg_id_data = payload.get("id", {})
        reply_to_id: str | None = None
        if isinstance(msg_id_data, str):
            reply_to_id = msg_id_data
        elif isinstance(msg_id_data, dict):
            reply_to_id = msg_id_data.get("_serialized") or msg_id_data.get("id")

        await _send_waha_message(phone, result["response"], reply_to_id)

        logger.info(
            "webhook_processed",
            phone=phone,
            elapsed_ms=int(elapsed * 1000),
            needs_human=result["needs_human_escalation"],
        )

    except Exception as e:
        logger.error("webhook_processing_error", phone=phone, error=str(e))


@app.post("/webhook/telegram")  # type: ignore[misc]
async def webhook_telegram(request: Request) -> JSONResponse:
    """Recibir webhook de Telegram (comandos del Líder).

    Comandos soportados:
    - /kill: activar kill switch
    - /revive: desactivar kill switch
    - /status: estado del sistema
    """
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


@app.post("/send-message")  # type: ignore[misc]
async def send_message(request: Request) -> JSONResponse:
    """Enviar mensaje proactivo a un cliente (ej: notificación de despacho)."""
    try:
        data = await request.json()
    except Exception as e:
        raise HTTPException(status_code=400, detail="JSON inválido") from e

    phone = data.get("phone", "")
    message = data.get("message", "")

    if not phone or not message:
        raise HTTPException(status_code=400, detail="Faltan 'phone' o 'message'")

    await _send_waha_message(phone, message)
    return JSONResponse({"status": "ok", "message_sent": True})


def _verify_hmac(body: bytes, signature: str, secret: str) -> bool:
    """Verificar firma HMAC SHA-512 del webhook."""
    if not secret or secret.startswith("PENDIENTE"):
        # En desarrollo, si no hay secret configurado, permitir
        return True

    expected = hmac.new(
        secret.encode(),
        body,
        hashlib.sha512,
    ).hexdigest()

    return hmac.compare_digest(expected, signature)


async def _send_waha_message(phone: str, message: str, reply_to: str | None = None) -> None:
    """Enviar mensaje a cliente vía WAHA API.

    Usa /api/sendText con el chatId tal como lo recibimos (@lid o @c.us).
    """
    import httpx

    settings = get_settings()
    headers = {"X-Api-Key": settings.waha_api_key}
    session = settings.waha_session_id

    # Usar el phone tal cual como chatId (WAHA acepta @lid y @c.us)
    chat_id = phone if "@" in phone else f"{phone}@c.us"

    url = f"{settings.waha_base_url}/api/sendText"
    payload = {
        "chatId": chat_id,
        "text": message,
        "session": session,
    }

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(url, json=payload, headers=headers)
            if resp.status_code in (200, 201, 202):
                logger.info("waha_message_sent", phone=phone, chat_id=chat_id)
            else:
                logger.error(
                    "waha_send_error",
                    phone=phone,
                    chat_id=chat_id,
                    status=resp.status_code,
                    response=resp.text[:300],
                )
    except Exception as e:
        logger.error("waha_send_exception", phone=phone, error=str(e))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info",
    )
