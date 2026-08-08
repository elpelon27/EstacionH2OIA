"""Cost Guard — Enforcement de límites de gasto diario en OpenRouter.

Interfaz esperada por tests:
- check() -> dict con status, alert_sent, block_active, spent_today
- is_blocked() -> bool
- _send_telegram_alert() -> async
- get_openrouter_sync() para reset diario
"""

from dataclasses import dataclass
from datetime import date
from typing import Any

from core.config import get_settings
from core.logger import get_logger
from core.openrouter_client import OpenRouterClient, get_openrouter

logger = get_logger("cost_guard")


@dataclass
class CostGuardResult:
    """Resultado de la verificación de gasto."""

    status: str  # "ok", "alerted", "blocked"
    alert_sent: bool
    block_active: bool
    spent_today: float
    reason: str = ""


class CostGuard:
    """Guardián de presupuesto diario para OpenRouter."""

    _instance: "CostGuard | None" = None

    def __init__(self) -> None:
        if CostGuard._instance is not None:
            raise RuntimeError("Use get_cost_guard() for singleton")
        self.settings = get_settings()
        self._alert_usd = self.settings.openrouter_daily_alert_usd
        self._block_usd = self.settings.openrouter_daily_block_usd
        self._alert_sent = False
        self._block_active = False
        self._last_check_date = date.today()

    @classmethod
    def get_instance(cls) -> "CostGuard":
        """Singleton pattern."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def is_blocked(self) -> bool:
        """Verificar si el bloqueo está activo."""
        return self._block_active

    async def check(self) -> dict[str, Any]:
        """Verificar gasto actual y actuar según thresholds.

        Returns:
            dict con: status, alert_sent, block_active, spent_today
        """
        # Verificar cambio de día
        today = date.today()
        if today != self._last_check_date:
            await self._reset_for_new_day()

        client = await get_openrouter()
        current = client.spent_today

        # 1. Bloqueo duro
        if current >= self._block_usd:
            if not self._block_active:
                self._block_active = True
                await self._send_telegram_alert(
                    "🚨 COST GUARD BLOCKED: "
                    f"Gasto diario ${current:.2f} >= ${self._block_usd:.2f}. "
                    "Llamadas a OpenRouter bloqueadas hasta medianoche."
                )
            logger.warning(
                "cost_guard_blocked", spent_today=current, block_threshold=self._block_usd
            )
            return {
                "status": "blocked",
                "alert_sent": self._alert_sent,
                "block_active": True,
                "spent_today": current,
            }

        # 2. Alerta
        if current >= self._alert_usd:
            if not self._alert_sent:
                self._alert_sent = True
                await self._send_telegram_alert(
                    f"⚠️ COST GUARD ALERT: Gasto diario ${current:.2f} >= ${self._alert_usd:.2f}. "
                    f"Bloqueo en ${self._block_usd:.2f}."
                )
            logger.warning("cost_guard_alert", spent_today=current, alert_threshold=self._alert_usd)
            return {
                "status": "alerted",
                "alert_sent": True,
                "block_active": False,
                "spent_today": current,
            }

        # 3. OK
        return {
            "status": "ok",
            "alert_sent": self._alert_sent,
            "block_active": False,
            "spent_today": current,
        }

    async def _reset_for_new_day(self) -> None:
        """Reset automático al cambiar de día."""
        client = await get_openrouter()
        client.reset_daily_spent()
        self._alert_sent = False
        self._block_active = False
        self._last_check_date = date.today()
        logger.info("cost_guard_daily_reset", new_day=str(self._last_check_date))

    async def _send_telegram_alert(self, message: str) -> None:
        """Enviar alerta por Telegram al líder usando Bot API directo."""
        settings = get_settings()
        bot_token = settings.telegram_bot_token_hermes
        chat_id = settings.telegram_chat_id_lider
        if not bot_token or not chat_id:
            logger.warning("cost_guard_telegram_not_configured")
            return
        try:
            import httpx

            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            payload = {"chat_id": chat_id, "text": message, "parse_mode": "HTML"}
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.post(url, json=payload)
        except Exception as e:
            logger.error("cost_guard_telegram_failed", error=str(e))

    def reset_manual(self) -> None:
        """Reset manual (admin/testing)."""
        self._alert_sent = False
        self._block_active = False
        logger.info("cost_guard_manual_reset")


def get_cost_guard() -> CostGuard:
    """Obtener instancia singleton del CostGuard."""
    return CostGuard.get_instance()


def get_openrouter_sync() -> OpenRouterClient:
    """Acceso síncrono al cliente OpenRouter (para tests/reset)."""
    return OpenRouterClient.get_instance()
