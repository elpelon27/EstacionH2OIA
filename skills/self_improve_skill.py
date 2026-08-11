"""Self-Improve Skill — Auto-análisis con Fusion Tournament (nocturno)."""

from typing import Any

from core.fusion import get_fusion
from skills.base_skill import BaseSkill


class SelfImproveSkill(BaseSkill):
    def __init__(self) -> None:
        super().__init__("self_improve")

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        action = kwargs.get("action", "analyze_day")
        if action == "analyze_day":
            return await self._analyze_day(kwargs.get("conversations", []))
        return self._error(f"Acción no reconocida: {action}")

    async def _analyze_day(self, conversations: list[dict[str, Any]]) -> dict[str, Any]:
        if not conversations:
            return self._error("No hay conversaciones")
        fusion = get_fusion()
        result = await fusion.run(
            messages=[
                {"role": "user", "content": f"Analiza estas conversaciones: {conversations[-10:]}"}
            ],
            temperature=0.2,
            max_tokens=1024,
        )
        return self._success(
            {"analysis": result.get("winner_response", ""), "score": result.get("score", 0)}
        )
