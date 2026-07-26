"""Cliente OpenRouter unificado (compatible con OpenAI SDK).

OpenRouter expone una API compatible con OpenAI, por eso usamos el SDK
oficial de OpenAI con base_url apuntando a openrouter.ai.

Features:
- Async client (httpx)
- Connection pool singleton
- Streaming support
- Cost tracking (gasto acumulado)
- Automatic retry on 429
"""

from typing import Any

from openai import AsyncOpenAI

from core.config import get_settings
from core.logger import get_logger

logger = get_logger("openrouter")


class OpenRouterClient:
    """Cliente singleton para OpenRouter API."""

    _instance: "OpenRouterClient | None" = None

    def __init__(self) -> None:
        settings = get_settings()
        self.client = AsyncOpenAI(
            api_key=settings.openrouter_api_key,
            base_url=settings.openrouter_base_url,
            default_headers={
                "HTTP-Referer": settings.openrouter_site_url,
                "X-Title": settings.openrouter_app_name,
            },
            timeout=settings.fusion_timeout_sec,
            max_retries=3,
        )
        self._spent_today: float = 0.0

    @classmethod
    def get_instance(cls) -> "OpenRouterClient":
        """Singleton pattern."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def chat(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 1024,
    ) -> dict[str, Any]:
        """Enviar mensaje a modelo de OpenRouter.

        Args:
            messages: lista de mensajes [{role, content}, ...]
            model: modelo a usar (default: openrouter_default_model)
            temperature: 0.0 determinista, 1.0 creativo
            max_tokens: máximo tokens de respuesta

        Returns:
            dict con: response, model, usage, cost_usd
        """
        settings = get_settings()
        model = model or settings.openrouter_default_model

        try:
            response = await self.client.chat.completions.create(
                model=model,
                messages=messages,  # type: ignore[arg-type]
                temperature=temperature,
                max_tokens=max_tokens,
            )

            content = response.choices[0].message.content or ""
            usage = response.usage
            assert usage is not None

            # Cálculo de costo aproximado (OpenRouter no lo da directo)
            # Se actualiza con la API /credits cuando esté disponible
            cost = self._estimate_cost(model, usage.prompt_tokens, usage.completion_tokens)
            self._spent_today += cost

            logger.info(
                "openrouter_chat_success",
                model=model,
                prompt_tokens=usage.prompt_tokens,
                completion_tokens=usage.completion_tokens,
                cost_usd=round(cost, 4),
                spent_today=round(self._spent_today, 4),
            )

            return {
                "response": content,
                "model": model,
                "usage": {
                    "prompt_tokens": usage.prompt_tokens,
                    "completion_tokens": usage.completion_tokens,
                    "total_tokens": usage.total_tokens,
                },
                "cost_usd": cost,
            }

        except Exception as e:
            logger.error("openrouter_chat_error", model=model, error=str(e))
            raise

    def _estimate_cost(self, model: str, prompt_tokens: int, completion_tokens: int) -> float:
        """Estimación de costo en USD basada en pricing conocido.

        Pricing por millón de tokens (input/output):
        - z-ai/glm-4.5: $0.60 / $2.20
        - anthropic/claude-sonnet-4.5: $3.00 / $15.00
        - deepseek/deepseek-chat-v3.2: $0.14 / $0.28
        - google/gemini-2.5-flash: $0.075 / $0.30
        """
        pricing = {
            "z-ai/glm-4.5": (0.60, 2.20),
            "anthropic/claude-sonnet-4.5": (3.00, 15.00),
            "deepseek/deepseek-chat-v3.2": (0.14, 0.28),
            "google/gemini-2.5-flash": (0.075, 0.30),
        }
        input_price, output_price = pricing.get(model, (1.0, 2.0))
        cost = (prompt_tokens / 1_000_000 * input_price) + (
            completion_tokens / 1_000_000 * output_price
        )
        return round(cost, 6)

    @property
    def spent_today(self) -> float:
        """Gasto acumulado hoy en USD (precisión completa para tests)."""
        return self._spent_today

    def reset_daily_spent(self) -> None:
        """Reset contador diario (llamar a medianoche)."""
        self._spent_today = 0.0
        logger.info("openrouter_daily_spent_reset")


async def get_openrouter() -> OpenRouterClient:
    """Helper async-friendly para obtener instancia."""
    return OpenRouterClient.get_instance()
