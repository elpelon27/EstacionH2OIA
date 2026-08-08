"""
Meta Cloud API Client — WhatsApp Business API wrapper.

Extraído de bridge.py para desacoplar la capa de transporte Meta del negocio.
"""

import hashlib
import hmac
import logging
from typing import Any

import httpx

from core.config import get_settings

logger = logging.getLogger("valentina_bridge.meta_client")

# HTTP client global (inicializado en lifespan de bridge.py)
_http_client: httpx.AsyncClient | None = None


def set_http_client(client: httpx.AsyncClient) -> None:
    """Registra el cliente HTTP compartido (llamado desde bridge.py lifespan)."""
    global _http_client
    _http_client = client


def get_http_client() -> httpx.AsyncClient:
    """Obtiene el cliente HTTP (requiere que set_http_client() ya se haya llamado)."""
    if _http_client is None:
        raise RuntimeError("HTTP client not initialized. Call set_http_client() first.")
    return _http_client


class MetaClient:
    """Cliente para Meta WhatsApp Cloud API."""

    def __init__(self) -> None:
        settings = get_settings()
        self.access_token = settings.meta_access_token
        self.phone_number_id = settings.meta_phone_number_id
        self.app_secret = settings.meta_app_secret
        self.api_version = settings.meta_api_version

    def _verify_signature(self, raw_body: bytes, signature_header: str) -> bool:
        """Verifica HMAC-SHA256 del body con APP_SECRET de Meta."""
        if not self.app_secret:
            logger.error("META_APP_SECRET no configurado — rechazando webhook")
            return False
        if not signature_header:
            return False
        expected = "sha256=" + hmac.new(
            self.app_secret.encode(), raw_body, hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, signature_header)

    @property
    def _base_url(self) -> str:
        return f"https://graph.facebook.com/{get_settings().meta_api_version}/{self.phone_number_id}/messages"

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

    def _assert_configured(self) -> bool:
        if not self.access_token or not self.phone_number_id:
            logger.error("META_ACCESS_TOKEN o META_PHONE_NUMBER_ID no configurados")
            return False
        return True

    async def send_text(self, phone: str, text: str) -> bool:
        """Envía un mensaje de texto via Meta Graph API."""
        if not self._assert_configured():
            return False

        from api.bridge import _phone_hash  # import local para evitar ciclos

        url = self._base_url
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": phone,
            "type": "text",
            "text": {"body": text, "preview_url": False},
        }
        try:
            client = get_http_client()
            resp = await client.post(url, headers=self._headers, json=payload, timeout=10)
            if resp.status_code == 200:
                from api.bridge import _phone_hash  # import local para evitar ciclos
                logger.info("Mensaje enviado a phone:%s (len=%d)", _phone_hash(phone)[:8], len(text))
                return True
            logger.error("Meta send API error %d: %s", resp.status_code, resp.text[:200])
            return False
        except httpx.HTTPError as e:
            logger.error("Error enviando a Meta: %s", e)
            return False

    async def send_interactive(
        self,
        phone: str,
        body_text: str,
        interactive_type: str,
        buttons: list[dict[str, Any]] | None = None,
        list_sections: list[dict[str, Any]] | None = None,
        button_text: str = "Ver opciones",
        header_text: str | None = None,
        footer_text: str | None = None,
    ) -> bool:
        """Envía un mensaje interactivo (list o button) via Meta Graph API."""
        if not self._assert_configured():
            return False

        from api.bridge import _phone_hash  # import local para evitar ciclos

        url = f"https://graph.facebook.com/{get_settings().meta_api_version}/{self.phone_number_id}/messages"

        interactive = {"type": interactive_type, "body": {"text": body_text}}

        if header_text:
            interactive["header"] = {"type": "text", "text": header_text[:60]}
        if footer_text:
            interactive["footer"] = {"text": footer_text[:60]}

        if interactive_type == "button":
            interactive["action"] = {
                "buttons": [
                    {"type": "reply", "reply": {"id": b["id"], "title": b["title"][:20]}}
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
            client = get_http_client()
            resp = await client.post(url, headers=self._headers, json=payload, timeout=10)
            if resp.status_code == 200:
                logger.info(
                    "Mensaje interactivo (%s) enviado a phone:%s",
                    interactive_type,
                    _phone_hash(phone)[:8],
                )
                return True
            logger.error("Meta send interactive error %d: %s", resp.status_code, resp.text[:200])
            return False
        except httpx.HTTPError as e:
            logger.error("Error enviando interactivo a Meta: %s", e)
            return False


# Singleton global
_meta_client: MetaClient | None = None


def get_meta_client() -> MetaClient:
    """Singleton MetaClient."""
    global _meta_client
    if _meta_client is None:
        _meta_client = MetaClient()
    return _meta_client
