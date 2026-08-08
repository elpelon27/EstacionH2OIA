"""Circuit Breaker — State machine para proteger proveedores LLM.

Implementa el patrón Circuit Breaker con tres estados:
- CLOSED: normal, requests pasan, cuenta fallos
- OPEN: fallo threshold alcanzado, rechaza rápido (fail-fast)
- HALF_OPEN: tras recovery_timeout, permite request de prueba

Configuración via Settings (nuevos campos sugeridos):
    cb_failure_threshold: int = 5       # fallos consecutivos para abrir
    cb_recovery_timeout_sec: int = 60   # seg antes de half-open
    cb_success_threshold: int = 2       # éxitos en half-open para cerrar

Integración: WorkloadRouter.execute() envuelve llamadas LLM con circuit breaker.
"""

import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from core.config import get_settings
from core.logger import get_logger

logger = get_logger("circuit_breaker")


class CircuitState(StrEnum):
    """Estados del circuit breaker."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitBreakerConfig:
    """Configuración del breaker para un proveedor."""

    failure_threshold: int = 5
    recovery_timeout_sec: int = 60
    success_threshold: int = 2
    excluded_exceptions: tuple[type[Exception], ...] = (
        asyncio.TimeoutError,
        ConnectionError,
        RuntimeError,
    )


@dataclass
class CircuitBreakerStats:
    """Estadísticas para observabilidad."""

    state: CircuitState = CircuitState.CLOSED
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    last_failure_time: float = 0.0
    last_state_change: float = field(default_factory=time.monotonic)
    total_calls: int = 0
    total_failures: int = 0
    total_rejected: int = 0


class CircuitBreaker:
    """Circuit breaker por proveedor (modelo, host, etc.)."""

    def __init__(
        self,
        name: str,
        config: CircuitBreakerConfig | None = None,
    ) -> None:
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self.stats = CircuitBreakerStats()
        self._lock = asyncio.Lock()

    def _should_trip(self) -> bool:
        """Verificar si debe pasar a OPEN."""
        return self.stats.consecutive_failures >= self.config.failure_threshold

    def _should_close(self) -> bool:
        """Verificar si debe pasar de HALF_OPEN a CLOSED."""
        return self.stats.consecutive_successes >= self.config.success_threshold

    def _is_recovery_timeout_elapsed(self) -> bool:
        """Verificar si pasó el timeout para ir a HALF_OPEN."""
        return (time.monotonic() - self.stats.last_failure_time) >= self.config.recovery_timeout_sec

    async def call(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Ejecutar función protegida por el circuit breaker.

        Args:
            func: callable async a ejecutar
            *args, **kwargs: argumentos para func

        Returns:
            Resultado de func()

        Raises:
            CircuitOpenError: si breaker está OPEN y no es half-open trial
            Exception: cualquier excepción de func() (se registra como fallo)
        """
        async with self._lock:
            self.stats.total_calls += 1

            # State machine logic
            if self.stats.state == CircuitState.OPEN:
                if self._is_recovery_timeout_elapsed():
                    # Transición a HALF_OPEN
                    self.stats.state = CircuitState.HALF_OPEN
                    self.stats.consecutive_successes = 0
                    self.stats.last_state_change = time.monotonic()
                    logger.info("circuit_breaker_half_open", name=self.name)
                else:
                    # Rechazar rápido
                    self.stats.total_rejected += 1
                    logger.warning("circuit_breaker_rejected", name=self.name, state="OPEN")
                    raise CircuitOpenError(f"Circuit breaker {self.name} is OPEN")

            # Ejecutar la llamada
            try:
                result = await func(*args, **kwargs)
                await self._on_success()
                return result

            except self.config.excluded_exceptions:
                # Excepción que cuenta como fallo
                await self._on_failure()
                raise

            except Exception as e:
                # Otras excepciones: NO cuentan como fallo del proveedor (ej: validation error)
                # Solo log y re-raise
                logger.debug("circuit_breaker_non_failure_exception", name=self.name, error=str(e))
                raise

    async def _on_success(self) -> None:
        """Registrar éxito y actualizar estado."""
        self.stats.consecutive_failures = 0

        if self.stats.state == CircuitState.HALF_OPEN:
            self.stats.consecutive_successes += 1
            if self._should_close():
                self.stats.state = CircuitState.CLOSED
                self.stats.last_state_change = time.monotonic()
                logger.info("circuit_breaker_closed", name=self.name)

        elif self.stats.state == CircuitState.CLOSED:
            # En closed, resetear contador de éxitos (solo fallos importan)
            pass

    async def _on_failure(self) -> None:
        """Registrar fallo y actualizar estado."""
        self.stats.consecutive_failures += 1
        self.stats.total_failures += 1
        self.stats.last_failure_time = time.monotonic()

        if self.stats.state == CircuitState.HALF_OPEN:
            # Cualquier fallo en half-open → volver a OPEN
            self.stats.state = CircuitState.OPEN
            self.stats.last_state_change = time.monotonic()
            logger.warning("circuit_breaker_reopened", name=self.name)

        elif self.stats.state == CircuitState.CLOSED:
            if self._should_trip():
                self.stats.state = CircuitState.OPEN
                self.stats.last_state_change = time.monotonic()
                logger.warning(
                    "circuit_breaker_opened",
                    name=self.name,
                    failures=self.stats.consecutive_failures,
                )

    def get_status(self) -> dict:
        """Estado actual para métricas/debugging."""
        return {
            "name": self.name,
            "state": self.stats.state.value,
            "consecutive_failures": self.stats.consecutive_failures,
            "consecutive_successes": self.stats.consecutive_successes,
            "total_calls": self.stats.total_calls,
            "total_failures": self.stats.total_failures,
            "total_rejected": self.stats.total_rejected,
            "failure_threshold": self.config.failure_threshold,
            "recovery_timeout_sec": self.config.recovery_timeout_sec,
            "success_threshold": self.config.success_threshold,
        }

    def force_open(self) -> None:
        """Forzar apertura manual (admin/testing)."""
        self.stats.state = CircuitState.OPEN
        self.stats.last_state_change = time.monotonic()
        logger.warning("circuit_breaker_force_open", name=self.name)

    def force_close(self) -> None:
        """Forzar cierre manual (admin/testing)."""
        self.stats.state = CircuitState.CLOSED
        self.stats.consecutive_failures = 0
        self.stats.last_state_change = time.monotonic()
        logger.info("circuit_breaker_force_close", name=self.name)


class CircuitOpenError(Exception):
    """Excepción cuando circuit breaker está abierto."""

    pass


class CircuitBreakerRegistry:
    """Registro global de circuit breakers por nombre."""

    def __init__(self) -> None:
        self._breakers: dict[str, CircuitBreaker] = {}
        self._lock = asyncio.Lock()
        self.settings = get_settings()

    def _default_config(self) -> CircuitBreakerConfig:
        return CircuitBreakerConfig(
            failure_threshold=5,
            recovery_timeout_sec=60,
            success_threshold=2,
        )

    async def get(self, name: str) -> CircuitBreaker:
        """Obtener o crear breaker para un nombre."""
        async with self._lock:
            if name not in self._breakers:
                self._breakers[name] = CircuitBreaker(name, self._default_config())
            return self._breakers[name]

    async def call(
        self,
        name: str,
        func: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """Shortcut: get breaker + call en uno."""
        breaker = await self.get(name)
        return await breaker.call(func, *args, **kwargs)

    def get_all_status(self) -> dict[str, dict]:
        """Estado de todos los breakers."""
        return {name: cb.get_status() for name, cb in self._breakers.items()}


# Singleton
_registry_instance: CircuitBreakerRegistry | None = None


def get_circuit_breaker_registry() -> CircuitBreakerRegistry:
    """Obtener singleton del registry."""
    global _registry_instance
    if _registry_instance is None:
        _registry_instance = CircuitBreakerRegistry()
    return _registry_instance
