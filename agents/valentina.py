"""Agente Valentina — Recepcionista WhatsApp de Estación H2O.

Combina:
- System prompt optimizado (hardcoded para velocidad)
- mem0 (memoria largo plazo del cliente)
- Memoria de sesión (últimos 4 mensajes para no repetir menú)
- Qwen local (vía WorkloadRouter)
"""
from typing import Any
import httpx
from core.config import get_settings
from core.logger import get_logger
from core.workload_router import get_router
from memory.memory_client import get_memory

logger = get_logger("valentina")

# System prompt optimizado (corto para latencia < 5s en GTX 1070)
SYSTEM_PROMPT = """Eres Valentina, asistente de Estación H2O (agua/hielo a domicilio en Maracaibo).
NO eres proactiva. Respuestas cortas (máx 2 líneas).

WORKFLOW:
1. Si es primer mensaje: "¡Hola! 💧 ¿Qué deseas? 1️⃣ Agua 2️⃣ Hielo 3️⃣ Combinada 4️⃣ Asesor"
2. Si elige 1: Preguntar cantidad. Precio: 1.00€ c/u. Preguntar dirección.
3. Si elige 2: Preguntar cantidad (bolsas 7kg). Precio: 1.20€ c/u. Preguntar dirección.
4. Si elige 3: Preguntar cantidades de ambos. Preguntar dirección.
5. Si elige 4 o pide humano: "Conectándote con un asesor..." (avisar al Líder).
6. Si confirma pedido: "¡Genial! Total: {total}€. Paga al 0412-2560721 y envía captura."

PRECIOS (NO cambiar): Agua 20L = 1.00€ | Hielo 7kg = 1.20€
Fuera de horario (7:40am-6:00pm): Programar para mañana.
NO inventes precios. NO sugieras productos extra.
"""

# Memoria de sesión (corto plazo: últimos 4 mensajes por teléfono)
_sessions: dict[str, list[dict[str, str]]] = {}


class ValentinaAgent:
    """Recepcionista WhatsApp de Estación H2O."""

    def __init__(self) -> None:
        self.settings = get_settings()

    async def process_message(
        self,
        phone: str,
        message: str,
        client_name: str | None = None,
    ) -> dict[str, Any]:
        """Procesar mensaje entrante de WhatsApp y generar respuesta."""
        logger.info(
            "message_received",
            phone=phone,
            message_preview=message[:50],
            client_name=client_name,
        )

        # 1. Buscar memoria largo plazo en mem0
        memory_client = await get_memory()
        client_memories = await memory_client.search_memory(
            query=message,
            user_id=phone,
            limit=3,
        )

        # 2. Escalación a humano
        if self._needs_human_escalation(message):
            logger.info("human_escalation_requested", phone=phone)
            await self._notify_leader_human_request(phone, message, client_name)
            return {
                "response": "Conectándote con un asesor, un momento por favor. 👨‍💼",
                "needs_human_escalation": True,
                "memory_used": len(client_memories),
            }

        # 3. Construir contexto con memoria de sesión (corto plazo)
        messages = self._build_context(phone, message, client_memories)

        # 4. Llamar Qwen local
        router = get_router()
        result = await router.execute(
            trigger="whatsapp_message",
            messages=messages,
            temperature=0.1,
        )

        response_text = result.get("response", "Disculpa, no pude procesar tu mensaje.")

        # 5. Actualizar memoria de sesión (corto plazo)
        self._update_session(phone, message, response_text)

        # 6. Guardar en mem0 (largo plazo)
        await memory_client.add_memory(
            content=f"Cliente dijo: {message}. Valentina respondió: {response_text}",
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
        triggers = ["hablar con alguien", "humano", "operador", "asesor", "persona real", "tu jefe", "dueño", "gerente", "supervisor", "4"]
        msg_lower = message.lower().strip()
        return any(t in msg_lower for t in triggers)

    def _build_context(
        self,
        phone: str,
        message: str,
        memories: list[dict[str, Any]],
    ) -> list[dict[str, str]]:
        """Construir contexto para el LLM: system + memoria largo plazo + sesión."""
        system_content = SYSTEM_PROMPT

        # Agregar memoria largo plazo (mem0)
        if memories:
            memory_text = "\n".join(f"- {m.get('memory', '')}" for m in memories if m.get("memory"))
            system_content += f"\n\nMEMORIA DEL CLIENTE:\n{memory_text}"

        messages = [{"role": "system", "content": system_content}]

        # Agregar historial de sesión (últimos 4 mensajes)
        session = _sessions.get(phone, [])
        messages.extend(session)

        # Agregar mensaje actual
        messages.append({"role": "user", "content": message})

        return messages

    def _update_session(self, phone: str, user_msg: str, assistant_msg: str) -> None:
        """Actualizar memoria de sesión (mantener solo últimos 4 mensajes)."""
        if phone not in _sessions:
            _sessions[phone] = []

        _sessions[phone].append({"role": "user", "content": user_msg})
        _sessions[phone].append({"role": "assistant", "content": assistant_msg})

        # Mantener solo últimos 4 mensajes (2 turnos) para no inflar el prompt
        if len(_sessions[phone]) > 4:
            _sessions[phone] = _sessions[phone][-4:]


    async def _notify_leader_human_request(
        self,
        phone: str,
        message: str,
        client_name: str | None,
    ) -> None:
        """Notificar al Líder vía Telegram."""
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
                    logger.error("telegram_escalation_error", status=resp.status_code)
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
