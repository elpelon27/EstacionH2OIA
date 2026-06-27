"""Workload Router — decide qué modelo/agente procesa cada tarea.

Filosofía:
- Operación productiva (clientes) → Qwen local (0$ por token)
- Tareas rutinarias de desarrollo → OpenRouter modelo único
- Decisiones críticas → Fusion Tournament (4 modelos + juez)
"""

from enum import Enum
from typing import Any

from core.config import get_settings
from core.fusion import get_fusion
from core.logger import get_logger
from core.openrouter_client import get_openrouter
from core.qwen_client import get_qwen

logger = get_logger("router")


class Route(str, Enum):
    """Destinos posibles para una tarea."""

    QWEN_LOCAL = "qwen_local"
    OPENROUTER_GLM = "openrouter:glm"
    OPENROUTER_CLAUDE = "openrouter:claude"
    OPENROUTER_DEEPSEEK = "openrouter:deepseek"
    OPENROUTER_GEMINI = "openrouter:gemini"
    FUSION = "fusion"


# Mapeo de triggers → ruta (tabla determinista)
ROUTE_TABLE: dict[str, Route] = {
    # Productivo (Qwen local)
    "whatsapp_message": Route.QWEN_LOCAL,
    "payment_received": Route.QWEN_LOCAL,
    "dispatch_request": Route.QWEN_LOCAL,
    # Desarrollo (OpenRouter)
    "architect_request": Route.FUSION,
    "code_generation_complex": Route.OPENROUTER_DEEPSEEK,
    "code_generation_critical": Route.FUSION,
    "rag_history_query": Route.OPENROUTER_GEMINI,
    "log_summary_daily": Route.OPENROUTER_GLM,
    "prompt_validation": Route.FUSION,
    "bug_diagnosis": Route.FUSION,
}


class WorkloadRouter:
    """Enruta tareas al modelo óptimo según el trigger."""

    def __init__(self) -> None:
        self.settings = get_settings()

    def resolve(self, trigger: str) -> Route:
        """Resolver ruta para un trigger dado.

        Args:
            trigger: identificador de la tarea (ej: "whatsapp_message")

        Returns:
            Route a usar (QWEN_LOCAL, OPENROUTER_X, o FUSION)
        """
        route = ROUTE_TABLE.get(trigger, Route.QWEN_LOCAL)  # Default: Qwen local
        logger.info("route_resolved", trigger=trigger, route=route.value)
        return route

    async def execute(
        self,
        trigger: str,
        messages: list[dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 1024,
    ) -> dict[str, Any]:
        """Ejecutar tarea enrutándola al modelo correcto.

        Args:
            trigger: tipo de tarea
            messages: prompt [{role, content}, ...]
            temperature: temperatura
            max_tokens: máximo tokens

        Returns:
            Respuesta del modelo (formato unificado)
        """
        route = self.resolve(trigger)

        if route == Route.QWEN_LOCAL:
            qwen = await get_qwen()
            result: dict[str, Any] = await qwen.chat(messages=messages, temperature=temperature)
            return result

        if route == Route.FUSION:
            fusion = get_fusion()
            return await fusion.run(
                messages=messages, temperature=temperature, max_tokens=max_tokens
            )

        # OpenRouter modelo único
        or_client = await get_openrouter()
        model_map: dict[Route, str] = {
            Route.OPENROUTER_GLM: "z-ai/glm-4.5",
            Route.OPENROUTER_CLAUDE: "anthropic/claude-sonnet-4.5",
            Route.OPENROUTER_DEEPSEEK: "deepseek/deepseek-chat-v3.2",
            Route.OPENROUTER_GEMINI: "google/gemini-2.5-flash",
        }
        model = model_map[route]
        return await or_client.chat(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )


# Singleton
_router_instance: WorkloadRouter | None = None


def get_router() -> WorkloadRouter:
    """Obtener instancia singleton del WorkloadRouter."""
    global _router_instance
    if _router_instance is None:
        _router_instance = WorkloadRouter()
    return _router_instance
