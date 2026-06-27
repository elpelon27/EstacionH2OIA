"""Tests para core/cost_guard.py."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.cost_guard import CostGuard, get_cost_guard


@pytest.fixture
def guard():
    """Fixture: instancia fresca de CostGuard."""
    CostGuard._instance = None
    g = CostGuard()
    g._alert_sent = False
    g._block_active = False
    return g


def test_get_cost_guard_singleton():
    """get_cost_guard debe retornar siempre la misma instancia."""
    CostGuard._instance = None
    g1 = get_cost_guard()
    g2 = get_cost_guard()
    assert g1 is g2


def test_initial_state_ok(guard):
    """Al iniciar, no debe haber alertas ni bloqueos."""
    assert guard._alert_sent is False
    assert guard._block_active is False
    assert guard.is_blocked() is False


@pytest.mark.asyncio
async def test_check_no_alert_under_threshold(guard):
    """Si gasto < $5, no debe enviar alerta."""
    mock_client = MagicMock()
    mock_client.spent_today = 2.0

    with patch("core.cost_guard.get_openrouter", new=AsyncMock(return_value=mock_client)):
        result = await guard.check()

    assert result["status"] == "ok"
    assert result["alert_sent"] is False
    assert result["block_active"] is False


@pytest.mark.asyncio
async def test_check_alert_at_5_usd(guard):
    """Si gasto >= $5, debe enviar alerta."""
    mock_client = MagicMock()
    mock_client.spent_today = 5.5
    mock_alert = AsyncMock()

    with (
        patch("core.cost_guard.get_openrouter", new=AsyncMock(return_value=mock_client)),
        patch.object(guard, "_send_telegram_alert", new=mock_alert),
    ):
        result = await guard.check()

    assert result["status"] == "alerted"
    assert result["alert_sent"] is True
    assert result["block_active"] is False
    mock_alert.assert_called_once()


@pytest.mark.asyncio
async def test_check_block_at_15_usd(guard):
    """Si gasto >= $15, debe activar bloqueo."""
    mock_client = MagicMock()
    mock_client.spent_today = 16.0
    mock_alert = AsyncMock()

    with (
        patch("core.cost_guard.get_openrouter", new=AsyncMock(return_value=mock_client)),
        patch.object(guard, "_send_telegram_alert", new=mock_alert),
    ):
        result = await guard.check()

    assert result["status"] == "blocked"
    assert result["block_active"] is True
    assert guard.is_blocked() is True


@pytest.mark.asyncio
async def test_check_no_duplicate_alert(guard):
    """Si ya se envió alerta, no reenviar en checks siguientes."""
    mock_client = MagicMock()
    mock_client.spent_today = 6.0
    mock_alert = AsyncMock()

    with (
        patch("core.cost_guard.get_openrouter", new=AsyncMock(return_value=mock_client)),
        patch.object(guard, "_send_telegram_alert", new=mock_alert),
    ):
        await guard.check()
        await guard.check()

    assert guard._alert_sent is True
    assert mock_alert.call_count == 1


@pytest.mark.asyncio
async def test_reset_if_new_day(guard):
    """Al cambiar de día, contadores deben resetearse."""
    guard._last_check_date = "2020-01-01"
    guard._alert_sent = True
    guard._block_active = True

    mock_client = MagicMock()
    mock_client.spent_today = 0.0  # Reset a 0
    mock_client.reset_daily_spent = MagicMock()

    with (
        patch("core.cost_guard.get_openrouter", new=AsyncMock(return_value=mock_client)),
        patch("core.cost_guard.get_openrouter_sync", return_value=mock_client),
    ):
        result = await guard.check()

    assert guard._alert_sent is False
    assert guard._block_active is False
    assert result["spent_today"] == 0.0
