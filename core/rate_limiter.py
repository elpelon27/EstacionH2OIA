"""Rate Limiter — Token Bucket por modelo/proveedor.

Implementa rate limiting distribuido en memoria (single-process) para
proteger proveedores LLM (OpenRouter, Ollama) de exceder cuotas.

Uso:
    limiter = get_rate_limiter()
    allowed = await limiter.acquire("openrouter:glm-4.5", tokens=1)
    if not allowed:
        raise RateLimitExceeded("...")

Configuración via Settings:
    rate_limit_llm_per_agent_per_min: 60  (global default)
    rate_limit_client_per_min: 30          (por cliente/IP)
"""

import asyncio
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from core.config import get_settings
from core.logger import get_logger

logger = get_logger("rate_limiter")


@dataclass
class TokenBucket:
    """Bucket de tokens para un key (modelo, cliente, IP, etc.)."""

    capacity: int
    refill_rate_per_sec: float
    tokens: float = field(init=False)
    last_refill: float = field(init=False)

    def __post_init__(self) -> None:
        self.tokens = float(self.capacity)
        self.last_refill = time.monotonic()

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self.last_refill
        new_tokens = elapsed * self.refill_rate_per_sec
        self.tokens = min(self.capacity, self.tokens + new_tokens)
        self.last_refill = now

    def try_consume(self, tokens: int = 1) -> bool:
        """Intentar consumir tokens. Retorna True si disponible."""
        self._refill()
        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False

    def time_until_ready(self, tokens: int = 1) -> float:
        """Segundos hasta que haya tokens disponibles."""
        self._refill()
        if self.tokens >= tokens:
            return 0.0
        deficit = tokens - self.tokens
        return deficit / self.refill_rate_per_sec


class RateLimiter:
    """Gestor de buckets por clave (modelo, cliente, IP, global)."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self._buckets: dict[str, TokenBucket] = {}
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._default_capacity = self.settings.rate_limit_llm_per_agent_per_min
        self._default_refill = self._default_capacity / 60.0  # tokens/sec

    def _get_bucket(
        self, key: str, capacity: int | None = None, refill_rate: float | None = None
    ) -> TokenBucket:
        """Obtener o crear bucket para una clave."""
        if key not in self._buckets:
            cap = capacity or self._default_capacity
            rate = refill_rate or self._default_refill
            self._buckets[key] = TokenBucket(capacity=cap, refill_rate_per_sec=rate)
        return self._buckets[key]

    async def acquire(
        self,
        key: str,
        tokens: int = 1,
        capacity: int | None = None,
        refill_rate: float | None = None,
        timeout: float = 0.0,
    ) -> bool:
        """Adquirir permiso para `tokens` requests.

        Args:
            key: identificador único (ej: "openrouter:glm-4.5", "client:58412...", "ip:192.168.1.1")
            tokens: cuántos tokens consumir (default 1)
            capacity: capacidad del bucket (override)
            refill_rate: tasa de recarga tokens/sec (override)
            timeout: segundos a esperar si bucket vacío (0 = no wait, fail fast)

        Returns:
            True si adquirido, False si timeout o denegado.
        """
        lock = self._locks[key]
        async with lock:
            bucket = self._get_bucket(key, capacity, refill_rate)

            if bucket.try_consume(tokens):
                return True

            if timeout <= 0:
                logger.debug("rate_limit_denied", key=key, tokens=tokens)
                return False

            # Esperar hasta que haya tokens o timeout
            wait_time = bucket.time_until_ready(tokens)
            if wait_time > timeout:
                logger.debug("rate_limit_timeout", key=key, wait_time=wait_time, timeout=timeout)
                return False

            logger.debug("rate_limit_wait", key=key, wait_time=wait_time)
            await asyncio.sleep(wait_time)
            # Reintentar después de esperar
            return bucket.try_consume(tokens)

    def get_status(self, key: str) -> dict[str, Any]:
        """Estado actual de un bucket (para debugging/métricas)."""
        bucket = self._buckets.get(key)
        if not bucket:
            return {"exists": False}
        bucket._refill()
        return {
            "exists": True,
            "tokens_available": round(bucket.tokens, 2),
            "capacity": bucket.capacity,
            "refill_rate_per_sec": bucket.refill_rate_per_sec,
            "utilization_pct": round((1 - bucket.tokens / bucket.capacity) * 100, 1),
        }

    def reset(self, key: str) -> None:
        """Reset manual de un bucket (testing/admin)."""
        if key in self._buckets:
            del self._buckets[key]
        logger.info("rate_limit_bucket_reset", key=key)


# Singleton
_rate_limiter_instance: RateLimiter | None = None


def get_rate_limiter() -> RateLimiter:
    """Obtener instancia singleton del RateLimiter."""
    global _rate_limiter_instance
    if _rate_limiter_instance is None:
        _rate_limiter_instance = RateLimiter()
    return _rate_limiter_instance
