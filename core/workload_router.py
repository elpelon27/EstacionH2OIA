"""Workload Router — decide qué modelo/agente/skill procesa cada tarea.

Filosofía:
- 7:40am - 6:00pm: Operación productiva (clientes) → Qwen local
- 6:00pm - 7:40am: Auto-mejora del sistema → Fusion Tournament
"""
from enum import Enum
from datetime import datetime, time
from typing import Any
from core.config import get_settings
from core.logger import get_logger
from core.qwen_client import get_qwen
from core.openrouter_client import get_openrouter
from core.fusion import get_fusion

logger = get_logger("router")


class Route(str, Enum):
    """Destinos posibles para una tarea."""
    QWEN_LOCAL = "qwen_local"
    OPENROUTER_GLM = "openrouter:glm"
    OPENROUTER_CLAUDE = "openrouter:claude"
    OPENROUTER_DEEPSEEK = "openrouter:deepseek"
    OPENROUTER_GEMINI = "openrouter:gemini"
    FUSION = "fusion"
    PAYMENT_SKILL = "skill:payment"
    INVENTORY_SKILL = "skill:inventory"
    SELF_IMPROVE_SKILL = "skill:self_improve"
    DISPATCH_SKILL = "skill:dispatcher"


# Mapeo de triggers → ruta (tabla determinista)
ROUTE_TABLE: dict[str, Route] = {
    # Productivo (7:40am - 6:00pm)
    "whatsapp_message": Route.QWEN_LOCAL,
    "payment_received": Route.PAYMENT_SKILL,
    "inventory_check": Route.INVENTORY_SKILL,
    "dispatch_request": Route.DISPATCH_SKILL,
    "dispatch_route_compute": Route.DISPATCH_SKILL,
    "dispatch_delivery_update": Route.DISPATCH_SKILL,
    "dispatch_gps_track": Route.DISPATCH_SKILL,
    "dispatch_bottle_inventory": Route.DISPATCH_SKILL,
    "delivery_delivered": Route.DISPATCH_SKILL,  # SWAP: entrega confirmada → bottle_tracker
    
    # Auto-mejora (6:00pm - 7:40am)
    "self_improve_request": Route.SELF_IMPROVE_SKILL,
    
    # Desarrollo (cualquier horario)
    "architect_request": Route.FUSION,
    "code_generation_complex": Route.OPENROUTER_DEEPSEEK,
    "code_generation_critical": Route.FUSION,
    "rag_history_query": Route.OPENROUTER_GEMINI,
    "log_summary_daily": Route.OPENROUTER_GLM,
    "prompt_validation": Route.FUSION,
    "bug_diagnosis": Route.FUSION,
}


class WorkloadRouter:
    """Enruta tareas al modelo/skill óptimo según el trigger y horario."""

    def __init__(self) -> None:
        self.settings = get_settings()

    def resolve(self, trigger: str) -> Route:
        """Resolver ruta para un trigger dado.
        
        Aplica lógica de horario: si es self_improve y estamos en horario
        laboral, lo bloquea (solo nocturno).
        """
        route = ROUTE_TABLE.get(trigger, Route.QWEN_LOCAL)  # Default: Qwen local
        
        # Regla: self_improve solo después de 6:00pm
        if route == Route.SELF_IMPROVE_SKILL:
            if self._is_business_hours():
                logger.warning("self_improve_blocked_during_business_hours")
                return Route.QWEN_LOCAL  # Fallback: no hacer nada especial
        
        logger.info("route_resolved", trigger=trigger, route=route.value)
        return route

    async def execute(
        self,
        trigger: str,
        messages: list[dict[str, str]] | None = None,
        temperature: float = 0.3,
        max_tokens: int = 1024,
        **kwargs: Any
    ) -> dict[str, Any]:
        """Ejecutar tarea enrutándola al modelo/skill correcto.

        Args:
            trigger: tipo de tarea
            messages: prompt [{role, content}, ...] (para LLM)
            temperature: temperatura
            max_tokens: máximo tokens
            **kwargs: argumentos adicionales para skills (ej: image_url, action)

        Returns:
            Respuesta del modelo o resultado de la skill
        """
        route = self.resolve(trigger)

        # === SKILLS ===
        if route == Route.PAYMENT_SKILL:
            from skills.payment_skill import PaymentSkill
            payment_skill = PaymentSkill()
            return await payment_skill.execute(**kwargs)

        if route == Route.INVENTORY_SKILL:
            from skills.inventory_skill import InventorySkill
            inventory_skill = InventorySkill()
            return await inventory_skill.execute(**kwargs)

        if route == Route.SELF_IMPROVE_SKILL:
            from skills.self_improve_skill import SelfImproveSkill
            self_improve_skill = SelfImproveSkill()
            return await self_improve_skill.execute(**kwargs)

        if route == Route.DISPATCH_SKILL:
            from skills.dispatcher_skill import get_dispatcher_skill
            dispatcher_skill = get_dispatcher_skill()
            return await dispatcher_skill.execute(**kwargs)

        # === LLM ROUTING ===
        if route == Route.QWEN_LOCAL:
            qwen_client = await get_qwen()
            result: dict[str, Any] = await qwen_client.chat(
                messages=messages or [], temperature=temperature
            )
            return result

        if route == Route.FUSION:
            fusion = get_fusion()
            return await fusion.run(
                messages=messages or [], temperature=temperature, max_tokens=max_tokens
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
            messages=messages or [], model=model, temperature=temperature, max_tokens=max_tokens
        )

    def _is_business_hours(self) -> bool:
        """Verificar si estamos en horario laboral (7:40am - 6:00pm)."""
        now = datetime.now().time()
        return time(7, 40) <= now <= time(18, 0)


# Singleton
_router_instance: WorkloadRouter | None = None


def get_router() -> WorkloadRouter:
    """Obtener instancia singleton del WorkloadRouter."""
    global _router_instance
    if _router_instance is None:
        _router_instance = WorkloadRouter()
    return _router_instance
