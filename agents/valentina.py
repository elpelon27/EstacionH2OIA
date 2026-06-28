"""Agente Valentina — Recepcionista WhatsApp de Estación H2O.

Combina:
- docs/SOUL.md (personalidad)
- docs/USER.md (perfil del Líder)
- docs/prompts/valentina.v1.md (system prompt base)
- mem0 (memoria del cliente: preferencias, historial)
- Qwen local (vía WorkloadRouter) para generar respuesta

Flujo:
1. Mensaje entra → buscar cliente en mem0
2. Construir contexto: system prompt + personalidad + memoria del cliente
3. Llamar Qwen local para generar respuesta
4. Guardar interacción en mem0 (para futuras conversaciones)
5. Si cliente pide humano → escalar al Líder vía Telegram
"""

from pathlib import Path
from typing import Any

import httpx

from core.config import get_settings
from core.logger import get_logger
from core.workload_router import get_router
from memory.memory_client import get_memory

logger = get_logger("valentina")

# Paths a documentos Markdown (fuente de verdad)
DOCS_PATH = Path(__file__).parent.parent / "docs"


class ValentinaAgent:
    """Recepcionista WhatsApp de Estación H2O."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.soul = self._load_doc("SOUL.md")
        self.user_profile = self._load_doc("USER.md")
        self.system_prompt = self._load_doc("prompts/valentina.v1.md")

    def _load_doc(self, filename: str) -> str:
        """Cargar documento Markdown desde docs/.

        Args:
            filename: nombre del archivo (ej: "SOUL.md")

        Returns:
            Contenido del archivo o string vacío si no existe
        """
        filepath = DOCS_PATH / filename
        try:
            content = filepath.read_text(encoding="utf-8")
            logger.info("doc_loaded", filename=filename, chars=len(content))
            return content
        except FileNotFoundError:
            logger.warning("doc_not_found", filename=filename)
            return ""

    async def process_message(
        self,
        phone: str,
        message: str,
        client_name: str | None = None,
    ) -> dict[str, Any]:
        """Procesar mensaje entrante de WhatsApp y generar respuesta.

        Args:
            phone: número de teléfono del cliente (ej: "584122560721")
            message: texto del mensaje
            client_name: nombre del cliente si se conoce (opcional)

        Returns:
            dict con: response, needs_human_escalation, memory_used
        """
        logger.info(
            "message_received",
            phone=phone,
            message_preview=message[:50],
            client_name=client_name,
        )

        # 1. Buscar memoria del cliente en mem0
        memory_client = await get_memory()
        client_memories = await memory_client.search_memory(
            query=message,
            user_id=phone,
            limit=5,
        )

        # 2. Verificar si cliente pide hablar con humano
        if self._needs_human_escalation(message):
            logger.info("human_escalation_requested", phone=phone)
            await self._notify_leader_human_request(phone, message, client_name)
            return {
                "response": (
                    "Por supuesto, te conecto con nuestro equipo. " "Un momento por favor. 👨‍💼"
                ),
                "needs_human_escalation": True,
                "memory_used": len(client_memories),
            }

        # 3. Construir contexto para Qwen
        messages = self._build_context(
            phone=phone,
            message=message,
            client_name=client_name,
            memories=client_memories,
        )

        # 4. Llamar Qwen local vía WorkloadRouter
        router = get_router()
        result = await router.execute(
            trigger="whatsapp_message",
            messages=messages,
            temperature=0.1,  # Ligeramente creativa pero coherente
        )

        response_text = result.get("response", "Disculpa, no pude procesar tu mensaje.")

        # 5. Guardar interacción en mem0 (para futuras conversaciones)
        await memory_client.add_memory(
            content=f"Cliente ({phone}) dijo: {message}. Valentina respondió: {response_text}",
            user_id=phone,
            metadata={"type": "conversation", "client_name": client_name or "unknown"},
        )

        logger.info(
            "message_processed",
            phone=phone,
            response_preview=response_text[:50],
            memory_used=len(client_memories),
        )

        return {
            "response": response_text,
            "needs_human_escalation": False,
            "memory_used": len(client_memories),
        }

    def _needs_human_escalation(self, message: str) -> bool:
        """Detectar si el cliente pide hablar con humano.

        Args:
            message: mensaje del cliente

        Returns:
            True si detecta intención de hablar con humano
        """
        triggers = [
            "hablar con alguien",
            "hablar con humano",
            "operador",
            "persona real",
            "tu jefe",
            "el dueño",
            "gerente",
            "supervisor",
            "alguien",
        ]
        message_lower = message.lower()
        return any(trigger in message_lower for trigger in triggers)

    def _build_context(
        self,
        phone: str,
        message: str,
        client_name: str | None,
        memories: list[dict[str, Any]],
    ) -> list[dict[str, str]]:
        """Construir lista de mensajes para el LLM.

        Combina: system prompt + personalidad + memoria + mensaje actual
        """
        # System prompt base (de valentina.v1.md)
        system_content = self.system_prompt

        # Agregar personalidad (de SOUL.md)
        if self.soul:
            system_content += f"\n\n--- PERSONALIDAD ---\n{self.soul}"

        # Agregar perfil del Líder (de USER.md)
        if self.user_profile:
            system_content += f"\n\n--- PERFIL DEL LÍDER ---\n{self.user_profile}"

        # Agregar memoria del cliente (de mem0)
        if memories:
            memory_text = "\n".join(f"- {m.get('memory', '')}" for m in memories if m.get("memory"))
            system_content += f"\n\n--- MEMORIA DEL CLIENTE ({phone}) ---\n{memory_text}"

        # Nombre del cliente si se conoce
        if client_name:
            system_content += f"\n\nEl cliente se llama {client_name}. Salúdalo por su nombre."

        return [
            {"role": "system", "content": system_content},
            {"role": "user", "content": message},
        ]

    async def _notify_leader_human_request(
        self,
        phone: str,
        message: str,
        client_name: str | None,
    ) -> None:
        """Notificar al Líder vía Telegram que un cliente pide hablar con humano.

        Args:
            phone: teléfono del cliente
            message: mensaje original del cliente
            client_name: nombre del cliente si se conoce
        """
        token = self.settings.telegram_bot_token_h2o
        chat_id = self.settings.telegram_chat_id_lider

        if not token or not chat_id:
            logger.warning("no_telegram_configured_for_escalation")
            return

        name_str = f" ({client_name})" if client_name else ""
        alert_text = (
            f"🔔 ESCALACIÓN HUMANA\n\n"
            f"Cliente: {phone}{name_str}\n"
            f"Mensaje: {message}\n\n"
            f"Responde directamente por WhatsApp."
        )

        try:
            async with httpx.AsyncClient(timeout=10) as http_client:
                resp = await http_client.post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    json={"chat_id": chat_id, "text": alert_text},
                )
                if resp.status_code == 200:
                    logger.info("leader_notified_escalation", phone=phone)
                else:
                    logger.error(
                        "telegram_escalation_error",
                        status=resp.status_code,
                    )
        except Exception as e:
            logger.error("telegram_escalation_exception", error=str(e))


# Singleton
_valentina_instance: ValentinaAgent | None = None


def get_valentina() -> ValentinaAgent:
    """Obtener instancia singleton de Valentina."""
    global _valentina_instance
    if _valentina_instance is None:
        _valentina_instance = ValentinaAgent()
    return _valentina_instance
