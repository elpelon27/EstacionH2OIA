"""Tests para cubrir las lineas sin cobertura de core/workload_router.py.

Lineas sin cubrir: 159, 169, 186, 195 — casos donde route != QWEN_LOCAL
y ocurre un error (cost_guard blocked, rate_limited, circuit_open, exception).

Usamos trigger="architect_request" que mapea a Route.FUSION para que los
guards se ejecuten y los fallbacks a Qwen local se activen.
"""

import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# NO mockear skills.payment_skill aqui — test_workload_router.py ya lo hace
# y si lo repetimos contaminamos el modulo. Estos tests solo usan triggers
# que van a FUSION, no a PAYMENT_SKILL, asi que no necesitamos el mock.

from core.workload_router import Route, WorkloadRouter  # noqa: E402
from core.circuit_breaker import CircuitOpenError  # noqa: E402


@pytest.fixture
def router():
    return WorkloadRouter()


@patch("core.workload_router.get_cost_guard")
@patch("core.workload_router.get_rate_limiter")
@pytest.mark.asyncio
async def test_fusion_rate_limited_fallback_qwen(mock_get_rate, mock_get_cost, router):
    """FUSION + rate_limited -> fallback a Qwen local (linea 168)."""
    mock_guard = MagicMock()
    mock_guard.check = AsyncMock(return_value={"status": "ok", "spent_today": 0.0})
    mock_get_cost.return_value = mock_guard

    mock_rate = AsyncMock()
    mock_rate.acquire = AsyncMock(return_value=False)
    mock_get_rate.return_value = mock_rate

    with patch.object(router, "_execute_qwen_local", new_callable=AsyncMock) as mock_qwen:
        mock_qwen.return_value = {"response": "fallback ok"}
        result = await router.execute(
            trigger="architect_request",
            messages=[{"role": "user", "content": "test"}],
        )

    assert result["response"] == "fallback ok"
    mock_qwen.assert_awaited_once()


@patch("core.workload_router.get_cost_guard")
@patch("core.workload_router.get_rate_limiter")
@patch("core.workload_router.get_circuit_breaker_registry")
@pytest.mark.asyncio
async def test_fusion_circuit_open_fallback_qwen(mock_get_cb, mock_get_rate, mock_get_cost, router):
    """FUSION + circuit_open -> fallback a Qwen local (linea 184-185)."""
    mock_guard = MagicMock()
    mock_guard.check = AsyncMock(return_value={"status": "ok", "spent_today": 0.0})
    mock_get_cost.return_value = mock_guard

    mock_rate = AsyncMock()
    mock_rate.acquire = AsyncMock(return_value=True)
    mock_get_rate.return_value = mock_rate

    mock_cb_registry = MagicMock()
    mock_cb_registry.call = AsyncMock(side_effect=CircuitOpenError("circuit open"))
    mock_get_cb.return_value = mock_cb_registry

    with patch.object(router, "_execute_qwen_local", new_callable=AsyncMock) as mock_qwen:
        mock_qwen.return_value = {"response": "circuit fallback ok"}
        result = await router.execute(
            trigger="architect_request",
            messages=[{"role": "user", "content": "test"}],
        )

    assert result["response"] == "circuit fallback ok"
    mock_qwen.assert_awaited_once()


@patch("core.workload_router.get_cost_guard")
@patch("core.workload_router.get_rate_limiter")
@patch("core.workload_router.get_circuit_breaker_registry")
@pytest.mark.asyncio
async def test_fusion_general_exception_fallback_qwen(
    mock_get_cb, mock_get_rate, mock_get_cost, router
):
    """FUSION + exception generica -> fallback a Qwen local (linea 193-194)."""
    mock_guard = MagicMock()
    mock_guard.check = AsyncMock(return_value={"status": "ok", "spent_today": 0.0})
    mock_get_cost.return_value = mock_guard

    mock_rate = AsyncMock()
    mock_rate.acquire = AsyncMock(return_value=True)
    mock_get_rate.return_value = mock_rate

    mock_cb_registry = MagicMock()
    mock_cb_registry.call = AsyncMock(side_effect=RuntimeError("unexpected LLM error"))
    mock_get_cb.return_value = mock_cb_registry

    with patch.object(router, "_execute_qwen_local", new_callable=AsyncMock) as mock_qwen:
        mock_qwen.return_value = {"response": "error fallback ok"}
        result = await router.execute(
            trigger="architect_request",
            messages=[{"role": "user", "content": "test"}],
        )

    assert result["response"] == "error fallback ok"
    mock_qwen.assert_awaited_once()


@patch("core.workload_router.get_cost_guard")
@pytest.mark.asyncio
async def test_fusion_cost_guard_blocked_fallback_qwen(mock_get_cost, router):
    """FUSION + cost_guard blocked -> fallback a Qwen local (linea 157-158)."""
    mock_guard = MagicMock()
    mock_guard.check = AsyncMock(return_value={"status": "blocked", "spent_today": 5.0})
    mock_get_cost.return_value = mock_guard

    with patch.object(router, "_execute_qwen_local", new_callable=AsyncMock) as mock_qwen:
        mock_qwen.return_value = {"response": "cost fallback ok"}
        result = await router.execute(
            trigger="architect_request",
            messages=[{"role": "user", "content": "test"}],
        )

    assert result["response"] == "cost fallback ok"
    mock_qwen.assert_awaited_once()


# ============================================================================
# QWEN_LOCAL error paths — lines 169, 186, 195
# When route IS QWEN_LOCAL, errors can't fall back to Qwen, so they return
# error dict or re-raise. cost_guard doesn't run for QWEN_LOCAL (line 159 dead).
# ============================================================================

@patch("core.workload_router.get_cost_guard")
@patch("core.workload_router.get_rate_limiter")
@pytest.mark.asyncio
async def test_qwen_local_rate_limited_returns_error(mock_get_rate, mock_get_cost, router):
    """QWEN_LOCAL + rate_limited -> retorna error (linea 169)."""
    mock_guard = MagicMock()
    mock_guard.check = AsyncMock(return_value={"status": "ok", "spent_today": 0.0})
    mock_get_cost.return_value = mock_guard

    mock_rate = AsyncMock()
    mock_rate.acquire = AsyncMock(return_value=False)
    mock_get_rate.return_value = mock_rate

    result = await router.execute(
        trigger="whatsapp_message",  # -> QWEN_LOCAL
        messages=[{"role": "user", "content": "test"}],
    )

    assert result["error"] == "rate_limited"
    assert "key" in result


@patch("core.workload_router.get_qwen", new=AsyncMock(side_effect=CircuitOpenError("circuit open")))
@patch("core.workload_router.get_cost_guard")
@patch("core.workload_router.get_rate_limiter")
@patch("core.workload_router.get_circuit_breaker_registry")
@pytest.mark.asyncio
async def test_qwen_local_circuit_open_returns_error(mock_get_cb, mock_get_rate, mock_get_cost, router):
    """QWEN_LOCAL + CircuitOpenError from get_qwen -> retorna error (linea 186)."""
    mock_guard = MagicMock()
    mock_guard.check = AsyncMock(return_value={"status": "ok", "spent_today": 0.0})
    mock_get_cost.return_value = mock_guard

    mock_rate = AsyncMock()
    mock_rate.acquire = AsyncMock(return_value=True)
    mock_get_rate.return_value = mock_rate

    mock_cb_registry = MagicMock()
    mock_get_cb.return_value = mock_cb_registry

    result = await router.execute(
        trigger="whatsapp_message",
        messages=[{"role": "user", "content": "test"}],
    )

    assert result["error"] == "circuit_open"


@patch("core.workload_router.get_qwen", new=AsyncMock(side_effect=RuntimeError("unexpected LLM error")))
@patch("core.workload_router.get_cost_guard")
@patch("core.workload_router.get_rate_limiter")
@patch("core.workload_router.get_circuit_breaker_registry")
@pytest.mark.asyncio
async def test_qwen_local_general_exception_reraise(mock_get_cb, mock_get_rate, mock_get_cost, router):
    """QWEN_LOCAL + generic exception from get_qwen -> re-raise (linea 195)."""
    mock_guard = MagicMock()
    mock_guard.check = AsyncMock(return_value={"status": "ok", "spent_today": 0.0})
    mock_get_cost.return_value = mock_guard

    mock_rate = AsyncMock()
    mock_rate.acquire = AsyncMock(return_value=True)
    mock_get_rate.return_value = mock_rate

    mock_cb_registry = MagicMock()
    mock_get_cb.return_value = mock_cb_registry

    with pytest.raises(RuntimeError, match="unexpected LLM error"):
        await router.execute(
            trigger="whatsapp_message",
            messages=[{"role": "user", "content": "test"}],
        )
