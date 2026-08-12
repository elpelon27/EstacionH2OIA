"""Tests para core/circuit_breaker.py."""
import asyncio

import pytest

from core.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerRegistry,
    CircuitOpenError,
    CircuitState,
    get_circuit_breaker_registry,
)


@pytest.fixture
def cb_config():
    """Configuración rápida para tests."""
    return CircuitBreakerConfig(
        failure_threshold=2,
        recovery_timeout_sec=1,
        success_threshold=1,
    )


@pytest.fixture
def breaker(cb_config):
    """Fixture: CircuitBreaker con config rápida."""
    return CircuitBreaker("test_breaker", cb_config)


def test_circuit_breaker_initial_state(breaker):
    """Estado inicial debe ser CLOSED."""
    assert breaker.stats.state == CircuitState.CLOSED
    assert breaker.stats.consecutive_failures == 0
    assert breaker.stats.consecutive_successes == 0


@pytest.mark.asyncio
async def test_call_success_in_closed(breaker):
    """Llamada exitosa en CLOSED mantiene estado."""
    async def success_func():
        return "ok"

    result = await breaker.call(success_func)
    assert result == "ok"
    assert breaker.stats.state == CircuitState.CLOSED
    assert breaker.stats.consecutive_failures == 0


@pytest.mark.asyncio
async def test_call_failure_in_closed(breaker):
    """Fallo en CLOSED incrementa contador."""
    async def fail_func():
        raise ConnectionError("connection failed")

    with pytest.raises(ConnectionError):
        await breaker.call(fail_func)

    assert breaker.stats.state == CircuitState.CLOSED
    assert breaker.stats.consecutive_failures == 1
    assert breaker.stats.total_failures == 1


@pytest.mark.asyncio
async def test_call_trips_to_open(breaker):
    """Tras failure_threshold fallos, pasa a OPEN."""
    async def fail_func():
        raise ConnectionError("connection failed")

    # Primer fallo
    with pytest.raises(ConnectionError):
        await breaker.call(fail_func)
    assert breaker.stats.state == CircuitState.CLOSED

    # Segundo fallo → OPEN
    with pytest.raises(ConnectionError):
        await breaker.call(fail_func)
    assert breaker.stats.state == CircuitState.OPEN
    assert breaker.stats.consecutive_failures == 2


@pytest.mark.asyncio
async def test_call_rejected_when_open(breaker):
    """En OPEN, rechaza rápido sin ejecutar func."""
    async def fail_func():
        raise ConnectionError("connection failed")

    # Forzar OPEN con dos fallos
    with pytest.raises(ConnectionError):
        await breaker.call(fail_func)
    with pytest.raises(ConnectionError):
        await breaker.call(fail_func)
    assert breaker.stats.state == CircuitState.OPEN

    # Tercera llamada → rechazada (CircuitOpenError)
    with pytest.raises(CircuitOpenError):
        await breaker.call(fail_func)

    assert breaker.stats.total_rejected == 1


@pytest.mark.asyncio
async def test_call_half_open_after_timeout(breaker):
    """Tras recovery_timeout, pasa a HALF_OPEN."""
    async def fail_func():
        raise ConnectionError("connection failed")

    async def success_func():
        return "ok"

    # Forzar OPEN
    with pytest.raises(ConnectionError):
        await breaker.call(fail_func)
    with pytest.raises(ConnectionError):
        await breaker.call(fail_func)
    assert breaker.stats.state == CircuitState.OPEN

    # Esperar recovery timeout
    await asyncio.sleep(1.1)

    # Siguiente llamada → HALF_OPEN, ejecuta func
    result = await breaker.call(success_func)
    assert result == "ok"
    # Con success_threshold=1, éxito en HALF_OPEN → CLOSED inmediato
    assert breaker.stats.state == CircuitState.CLOSED
    assert breaker.stats.consecutive_failures == 0


@pytest.mark.asyncio
async def test_call_half_open_success_closes(breaker):
    """Éxito en HALF_OPEN → CLOSED (success_threshold=1)."""
    async def fail_func():
        raise ConnectionError("connection failed")

    async def success_func():
        return "ok"

    # Forzar OPEN
    with pytest.raises(ConnectionError):
        await breaker.call(fail_func)
    with pytest.raises(ConnectionError):
        await breaker.call(fail_func)
    await asyncio.sleep(1.1)

    # Éxito en HALF_OPEN
    result = await breaker.call(success_func)
    assert result == "ok"
    assert breaker.stats.state == CircuitState.CLOSED
    assert breaker.stats.consecutive_failures == 0


@pytest.mark.asyncio
async def test_call_half_open_failure_reopens(breaker):
    """Fallo en HALF_OPEN → vuelve a OPEN."""
    async def fail_func():
        raise ConnectionError("connection failed")

    # Forzar OPEN
    with pytest.raises(ConnectionError):
        await breaker.call(fail_func)
    with pytest.raises(ConnectionError):
        await breaker.call(fail_func)
    await asyncio.sleep(1.1)

    # Fallo en HALF_OPEN
    with pytest.raises(ConnectionError):
        await breaker.call(fail_func)
    assert breaker.stats.state == CircuitState.OPEN


@pytest.mark.asyncio
async def test_excluded_exceptions_count_as_failure(breaker):
    """Excepciones en excluded_exceptions cuentan como fallo."""
    async def timeout_func():
        raise TimeoutError("timeout")

    with pytest.raises(asyncio.TimeoutError):
        await breaker.call(timeout_func)

    assert breaker.stats.consecutive_failures == 1
    assert breaker.stats.total_failures == 1


@pytest.mark.asyncio
async def test_non_excluded_exceptions_do_not_count(breaker):
    """Otras excepciones NO cuentan como fallo del proveedor."""
    async def value_error_func():
        raise ValueError("validation error")

    with pytest.raises(ValueError):
        await breaker.call(value_error_func)

    assert breaker.stats.consecutive_failures == 0
    assert breaker.stats.total_failures == 0
    assert breaker.stats.state == CircuitState.CLOSED


def test_get_status(breaker):
    """get_status debe retornar dict con métricas."""
    status = breaker.get_status()
    assert status["name"] == "test_breaker"
    assert status["state"] == "closed"
    assert status["consecutive_failures"] == 0
    assert status["failure_threshold"] == 2
    assert status["recovery_timeout_sec"] == 1


def test_force_open(breaker):
    """force_open debe poner breaker en OPEN."""
    breaker.force_open()
    assert breaker.stats.state == CircuitState.OPEN


def test_force_close(breaker):
    """force_close debe poner breaker en CLOSED y resetear contadores."""
    breaker.force_open()
    breaker.force_close()
    assert breaker.stats.state == CircuitState.CLOSED
    assert breaker.stats.consecutive_failures == 0


@pytest.mark.asyncio
async def test_registry_get_creates_breaker():
    """Registry.get debe crear breaker si no existe."""
    registry = CircuitBreakerRegistry()
    breaker = await registry.get("new_breaker")
    assert isinstance(breaker, CircuitBreaker)
    assert breaker.name == "new_breaker"


@pytest.mark.asyncio
async def test_registry_get_returns_same_breaker():
    """Registry.get debe retornar misma instancia para mismo nombre."""
    registry = CircuitBreakerRegistry()
    b1 = await registry.get("same")
    b2 = await registry.get("same")
    assert b1 is b2


@pytest.mark.asyncio
async def test_registry_call_shortcut():
    """Registry.call = get + call en uno."""
    registry = CircuitBreakerRegistry()

    async def success_func():
        return "registry_ok"

    result = await registry.call("shortcut_breaker", success_func)
    assert result == "registry_ok"


@pytest.mark.asyncio
async def test_registry_get_all_status():
    """get_all_status retorna estado de todos los breakers."""
    registry = CircuitBreakerRegistry()
    await registry.get("breaker1")
    await registry.get("breaker2")

    all_status = registry.get_all_status()
    assert "breaker1" in all_status
    assert "breaker2" in all_status
    assert all_status["breaker1"]["state"] == "closed"


def test_circuit_open_error():
    """CircuitOpenError es Exception."""
    err = CircuitOpenError("test")
    assert isinstance(err, Exception)
    assert str(err) == "test"


def test_circuit_breaker_config_defaults():
    """Config por defecto."""
    config = CircuitBreakerConfig()
    assert config.failure_threshold == 5
    assert config.recovery_timeout_sec == 60
    assert config.success_threshold == 2


def test_get_circuit_breaker_registry_singleton():
    """get_circuit_breaker_registry retorna singleton."""
    r1 = get_circuit_breaker_registry()
    r2 = get_circuit_breaker_registry()
    assert r1 is r2
