"""Cliente WhatsApp Cloud API oficial de Meta.

Reemplaza completamente a WAHA. No requiere QR, no se desconecta.
API: https://graph.facebook.com/v25.0/{PHONE_NUMBER_ID}/messages
"""

from typing import Any

import httpx

from core.config import get_settings
from core.logger import get_logger

logger = get_logger("meta_client")


class MetaWhatsAppClient:
    """Cliente singleton para WhatsApp Cloud API de Meta."""

    _instance: "MetaWhatsAppClient | None" = None

    def __init__(self) -> None:
        settings = get_settings()
        self.access_token = settings.meta_access_token
        self.phone_number_id = settings.meta_phone_number_id
        self.api_version = settings.meta_api_version
        self.base_url = (
            f"https://graph.facebook.com/{self.api_version}/{self.phone_number_id}/messages"
        )
        self.headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        self.http_client = httpx.AsyncClient(timeout=30.0)

    @classmethod
    def get_instance(cls) -> "MetaWhatsAppClient":
        """Singleton pattern."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def send_text_message(
        self,
        to: str,
        text: str,
        reply_to_message_id: str | None = None,
    ) -> dict[str, Any]:
        """Enviar mensaje de texto vía WhatsApp Cloud API.

        Args:
            to: número de teléfono con código de país (ej: "584122560721")
            text: texto del mensaje
            reply_to_message_id: ID del mensaje a responder (opcional)

        Returns:
            dict con: success, message_id, error
        """
        # Limpiar número (quitar @c.us, @lid, etc si los trae)
        to_clean = to.replace("@c.us", "").replace("@s.whatsapp.net", "").replace("@lid", "")

        payload: dict[str, Any] = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to_clean,
            "type": "text",
            "text": {
                "preview_url": False,
                "body": text,
            },
        }

        # Si hay reply_to, agregar contexto
        if reply_to_message_id:
            payload["context"] = {"message_id": reply_to_message_id}

        try:
            response = await self.http_client.post(
                self.base_url,
                headers=self.headers,
                json=payload,
            )

            if response.status_code == 200:
                data = response.json()
                msg_id = data.get("messages", [{}])[0].get("id", "")
                logger.info(
                    "meta_message_sent",
                    to=to_clean,
                    message_id=msg_id,
                )
                return {
                    "success": True,
                    "message_id": msg_id,
                    "error": None,
                }
            else:
                error_data = response.json()
                error_msg = error_data.get("error", {}).get("message", "Unknown error")
                logger.error(
                    "meta_message_error",
                    to=to_clean,
                    status=response.status_code,
                    error=error_msg,
                )
                return {
                    "success": False,
                    "message_id": None,
                    "error": error_msg,
                }

        except Exception as e:
            logger.error("meta_message_exception", to=to_clean, error=str(e))
            return {
                "success": False,
                "message_id": None,
                "error": str(e),
            }

    async def send_template_message(
        self,
        to: str,
        template_name: str,
        language_code: str = "es",
    ) -> dict[str, Any]:
        """Enviar mensaje con plantilla pre-aprobada.

        Args:
            to: número de teléfono
            template_name: nombre de la plantilla aprobada
            language_code: código de idioma (ej: "es", "en_US")

        Returns:
            dict con: success, message_id, error
        """
        to_clean = to.replace("@c.us", "").replace("@s.whatsapp.net", "").replace("@lid", "")

        payload = {
            "messaging_product": "whatsapp",
            "to": to_clean,
            "type": "template",
            "template": {"name": template_name, "language": {"code": language_code}},
        }

        try:
            response = await self.http_client.post(
                self.base_url,
                headers=self.headers,
                json=payload,
            )

            if response.status_code == 200:
                data = response.json()
                msg_id = data.get("messages", [{}])[0].get("id", "")
                logger.info(
                    "meta_template_sent",
                    to=to_clean,
                    template=template_name,
                    message_id=msg_id,
                )
                return {
                    "success": True,
                    "message_id": msg_id,
                    "error": None,
                }
            else:
                error_data = response.json()
                error_msg = error_data.get("error", {}).get("message", "Unknown error")
                logger.error(
                    "meta_template_error",
                    to=to_clean,
                    template=template_name,
                    error=error_msg,
                )
                return {
                    "success": False,
                    "message_id": None,
                    "error": error_msg,
                }

        except Exception as e:
            logger.error("meta_template_exception", to=to_clean, error=str(e))
            return {
                "success": False,
                "message_id": None,
                "error": str(e),
            }

    async def close(self) -> None:
        """Cerrar cliente HTTP."""
        await self.http_client.aclose()


async def get_meta_client() -> MetaWhatsAppClient:
    """Helper async-friendly."""
    return MetaWhatsAppClient.get_instance()
