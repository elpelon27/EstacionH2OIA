"""Cost Guard — alertas y bloqueo por gasto diario de OpenRouter.

Protege el presupuesto del Líder:
- $5/día → alerta Telegram al Líder
- $15/día → bloqueo duro (pausa OpenRouter, fallback a Qwen local)
"""

from datetime import UTC, datetime
from typing import Any

import httpx

from core.config import get_settings
from core.logger import get_logger
from core.openrouter_client import get_openrouter

logger = get_logger("cost_guard")


class CostGuard:
    """Monitor de gasto diario en OpenRouter."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.alert_threshold = self.settings.openrouter_daily_alert_usd
        self.block_threshold = self.settings.openrouter_daily_block_usd
        self._alert_sent = False
        self._block_active = False
        self._last_check_date: str | None = None

    async def check(self) -> dict[str, Any]:
        """Verificar gasto actual y tomar acciones.

        Returns:
            dict con: spent_today, alert_sent, block_active, status
        """
        self._reset_if_new_day()

        client = await get_openrouter()
        spent = client.spent_today

        # Verificar bloqueo duro
        if spent >= self.block_threshold and not self._block_active:
            self._block_active = True
            await self._send_telegram_alert(
                f"🔴 BLOQUEO OpenRouter: ${spent:.2f} hoy (límite ${self.block_threshold:.2f}). "
                "IA cloud pausada. Usando Qwen local."
            )
            logger.warning("cost_guard_block_activated", spent=spent)

        # Verificar alerta
        elif spent >= self.alert_threshold and not self._alert_sent:
            self._alert_sent = True
            await self._send_telegram_alert(
                f"🟠 ALERTA OpenRouter: ${spent:.2f} hoy (umbral ${self.alert_threshold:.2f}). "
                f"Bloqueo a ${self.block_threshold:.2f}."
            )
            logger.warning("cost_guard_alert_sent", spent=spent)

        return {
            "spent_today": round(spent, 4),
            "alert_threshold": self.alert_threshold,
            "block_threshold": self.block_threshold,
            "alert_sent": self._alert_sent,
            "block_active": self._block_active,
            "status": "blocked"
            if self._block_active
            else ("alerted" if self._alert_sent else "ok"),
        }

    def is_blocked(self) -> bool:
        """¿OpenRouter está bloqueado?"""
        return self._block_active

    def _reset_if_new_day(self) -> None:
        """Resetear contadores si cambió el día (UTC)."""
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        if self._last_check_date != today:
            self._last_check_date = today
            self._alert_sent = False
            self._block_active = False
            client = get_openrouter_sync()
            if client:
                client.reset_daily_spent()
            logger.info("cost_guard_daily_reset", date=today)

    async def _send_telegram_alert(self, message: str) -> None:
        """Enviar alerta a Telegram del Líder."""
        token = self.settings.telegram_bot_token_hermes
        chat_id = self.settings.telegram_chat_id_lider
        if not token or not chat_id:
            logger.warning("cost_guard_no_telegram_configured")
            return

        try:
            async with httpx.AsyncClient(timeout=10) as http_client:
                resp = await http_client.post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    json={"chat_id": chat_id, "text": message},
                )
                if resp.status_code == 200:
                    logger.info("cost_guard_alert_sent_telegram", message=message[:50])
                else:
                    logger.error("cost_guard_telegram_error", status=resp.status_code)
        except Exception as e:
            logger.error("cost_guard_telegram_exception", error=str(e))


def get_openrouter_sync() -> Any:
    """Obtener instancia OpenRouter de forma síncrona (para reset)."""
    from core.openrouter_client import OpenRouterClient

    return OpenRouterClient.get_instance()


# Singleton
_guard_instance: CostGuard | None = None


def get_cost_guard() -> CostGuard:
    """Obtener instancia singleton del CostGuard."""
    global _guard_instance
    if _guard_instance is None:
        _guard_instance = CostGuard()
    return _guard_instance
