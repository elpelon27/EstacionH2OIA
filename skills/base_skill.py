"""Clase base para todas las skills de Hermes Agent."""
from typing import Any
from core.config import get_settings
from core.logger import get_logger

class BaseSkill:
    def __init__(self, name: str) -> None:
        self.name = name
        self.settings = get_settings()
        self.logger = get_logger(f"skill_{name}")

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        raise NotImplementedError

    def _success(self, data: dict[str, Any]) -> dict[str, Any]:
        return {"success": True, "data": data, "error": None, "skill": self.name}

    def _error(self, error: str) -> dict[str, Any]:
        self.logger.error("skill_error", skill=self.name, error=error)
        return {"success": False, "data": None, "error": error, "skill": self.name}
