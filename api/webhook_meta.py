"""
Webhook Meta Cloud API — Endpoints GET (verificación) y POST (recepción).

Extraído de bridge.py para desacoplar la capa de transporte del negocio.
"""

import hashlib
import hmac
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse, PlainTextResponse

from core.config import get_settings

logger = logging.getLogger("valentina_bridge.webhook_meta")

# Cache de deduplicación (message_id → timestamp). TTL 5 min.
_seen_messages: dict[str, float] = {}
DEDUP_TTL_SECONDS = 300

# Callback registrado por bridge.py para procesar mensajes
_message_handler: Callable[[dict[str, Any], dict[str, Any]], Awaitable[None]] | None = None


def _verify_meta_hmac(body: bytes, signature: str, app_secret: str) -> bool:
    """Verifica firma HMAC-SHA256 del webhook de Meta."""
    if not app_secret:
        logger.error("META_APP_SECRET no configurado — rechazando webhook")
        return False
    if not signature:
        return False
    expected = "sha256=" + hmac.new(app_secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def _is_duplicate(message_id: str) -> bool:
    """True si el message_id ya fue procesado en los últimos 5 min."""
    now = time.time()
    expired = [mid for mid, ts in _seen_messages.items() if now - ts > DEDUP_TTL_SECONDS]
    for mid in expired:
        del _seen_messages[mid]
    if message_id in _seen_messages:
        return True
    _seen_messages[message_id] = now
    return False


def set_message_handler(
    handler: Callable[[dict[str, Any], dict[str, Any]], Awaitable[None]],
) -> None:
    """Registra el handler de mensajes (llamado desde bridge.py al arrancar)."""
    global _message_handler
    _message_handler = handler


def register_webhook_meta_routes(app: FastAPI) -> None:
    """Registra los endpoints del webhook Meta en la app FastAPI."""
    settings = get_settings()

    @app.get("/webhook/meta")
    async def verify_webhook(
        request: Request,
        hub_mode: str = Query(..., alias="hub.mode"),
        hub_challenge: str = Query(..., alias="hub.challenge"),
        hub_verify_token: str = Query(..., alias="hub.verify_token"),
    ) -> PlainTextResponse:
        """Verificación inicial del webhook por Meta."""
        if hub_mode == "subscribe" and hub_verify_token == settings.meta_verify_token:
            logger.info("webhook_verified_by_meta")
            return PlainTextResponse(hub_challenge)
        else:
            logger.warning("webhook_verification_failed")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Verification failed",
            )

    @app.post("/webhook/meta")
    async def webhook_meta(request: Request) -> JSONResponse:
        """Recibe webhook de Meta Cloud API."""
        # 1. Verificar HMAC-SHA256 (seguridad crítica)
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
            logger.error("webhook_parse_error")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="JSON inválido",
            ) from e

        # 3. Validar estructura básica
        if data.get("object") != "whatsapp_business_account":
            return JSONResponse({"status": "ignored", "reason": "not_whatsapp"})

        # 4. Procesar entries
        if _message_handler is None:
            logger.error("message_handler not registered")
            return JSONResponse({"status": "error", "reason": "handler_not_ready"})

        entries = data.get("entry", [])
        for entry in entries:
            changes = entry.get("changes", [])
            for change in changes:
                field = change.get("field")
                value = change.get("value", {})

                if field == "messages":
                    messages = value.get("messages", [])
                    for msg in messages:
                        await _message_handler(msg, value)

        return JSONResponse({"status": "received"})
