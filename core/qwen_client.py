"""Cliente Ollama local para inferencia con Qwen 2.5 7B.

Usa httpx directamente (no SDK de Ollama) para control total del timeout
y compatibilidad con versiones anteriores.

Features:
- Async client (httpx)
- Connection pool singleton
- Fallback si Ollama cae
- Latencia tracking
"""

import time
from typing import Any

import httpx

from core.config import get_settings
from core.logger import get_logger

logger = get_logger("qwen")


class QwenClient:
    """Cliente singleton para Ollama API local."""

    _instance: "QwenClient | None" = None

    def __init__(self) -> None:
        settings = get_settings()
        self.base_url = settings.ollama_host
        self.default_model = settings.ollama_default_model
        self.timeout = settings.ollama_timeout
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(self.timeout, connect=5.0),
        )

    @classmethod
    def get_instance(cls) -> "QwenClient":
        """Singleton pattern."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def chat(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.3,
    ) -> dict[str, Any]:
        """Chat con modelo local de Ollama.

        Args:
            messages: [{role, content}, ...]
            model: modelo (default: qwen2.5:7b)
            temperature: 0.0 determinista

        Returns:
            dict con: response, model, latency_ms, tokens
        """
        model = model or self.default_model
        start = time.monotonic()

        try:
            response = await self.client.post(
                "/api/chat",
                json={
                    "model": model,
                    "messages": messages,
                    "stream": False,
                    "options": {"temperature": temperature},
                },
            )
            response.raise_for_status()
            data = response.json()

            latency_ms = int((time.monotonic() - start) * 1000)
            content = data.get("message", {}).get("content", "")
            eval_count = data.get("eval_count", 0)
            prompt_eval_count = data.get("prompt_eval_count", 0)

            logger.info(
                "qwen_chat_success",
                model=model,
                latency_ms=latency_ms,
                prompt_tokens=prompt_eval_count,
                completion_tokens=eval_count,
            )

            return {
                "response": content,
                "model": model,
                "latency_ms": latency_ms,
                "usage": {
                    "prompt_tokens": prompt_eval_count,
                    "completion_tokens": eval_count,
                    "total_tokens": prompt_eval_count + eval_count,
                },
                "cost_usd": 0.0,
            }

        except httpx.ConnectError as e:
            logger.error("qwen_connect_error", model=model, error=str(e))
            raise RuntimeError(f"Ollama no disponible en {self.base_url}") from e
        except httpx.HTTPStatusError as e:
            logger.error("qwen_http_error", model=model, status=e.response.status_code)
            raise
        except Exception as e:
            logger.error("qwen_chat_error", model=model, error=str(e))
            raise

    async def list_models(self) -> list[str]:
        """Listar modelos disponibles en Ollama."""
        try:
            response = await self.client.get("/api/tags")
            response.raise_for_status()
            data = response.json()
            return [m["name"] for m in data.get("models", [])]
        except Exception as e:
            logger.error("qwen_list_models_error", error=str(e))
            return []

    async def close(self) -> None:
        """Cerrar cliente (al apagar)."""
        await self.client.aclose()


async def get_qwen() -> QwenClient:
    """Helper async-friendly."""
    return QwenClient.get_instance()
