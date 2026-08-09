"""Tests para core/cost_guard.py."""

from datetime import date
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


@pytest.mark.asyncio
async def test_reset_for_new_day_direct(guard):
    """_reset_for_new_day debe resetear flags y llamar a client.reset_daily_spent."""
    guard._last_check_date = "2020-01-01"
    guard._alert_sent = True
    guard._block_active = True

    mock_client = AsyncMock()
    mock_client.spent_today = 0.0
    mock_client.reset_daily_spent = AsyncMock()

    with patch("core.cost_guard.get_openrouter", new=AsyncMock(return_value=mock_client)):
        await guard._reset_for_new_day()

    assert guard._alert_sent is False
    assert guard._block_active is False
    assert guard._last_check_date == date.today()
    mock_client.reset_daily_spent.assert_called_once()


@pytest.mark.asyncio
async def test_send_telegram_alert_success(guard):
    """_send_telegram_alert debe enviar mensaje cuando está configurado."""
    with patch("core.cost_guard.get_settings") as mock_settings:
        mock_settings.return_value.telegram_bot_token_hermes = "test_token"
        mock_settings.return_value.telegram_chat_id_lider = "123456"

        with patch("httpx.AsyncClient.post", new=AsyncMock()) as mock_post:
            await guard._send_telegram_alert("Test alert")
            mock_post.assert_called_once()


@pytest.mark.asyncio
async def test_send_telegram_alert_not_configured(guard):
    """_send_telegram_alert debe loggear warning si no hay token/chat_id."""
    with patch("core.cost_guard.get_settings") as mock_settings:
        mock_settings.return_value.telegram_bot_token_hermes = ""
        mock_settings.return_value.telegram_chat_id_lider = ""

        with patch("core.cost_guard.logger.warning") as mock_warn:
            await guard._send_telegram_alert("Test alert")
            mock_warn.assert_called_with("cost_guard_telegram_not_configured")


@pytest.mark.asyncio
async def test_send_telegram_alert_failure(guard):
    """_send_telegram_alert debe loggear error si falla la petición."""
    with patch("core.cost_guard.get_settings") as mock_settings:
        mock_settings.return_value.telegram_bot_token_hermes = "test_token"
        mock_settings.return_value.telegram_chat_id_lider = "123456"

        with patch("httpx.AsyncClient.post", side_effect=Exception("network error")):
            with patch("core.cost_guard.logger.error") as mock_error:
                await guard._send_telegram_alert("Test alert")
                mock_error.assert_called_once()


def test_reset_manual(guard):
    """reset_manual debe limpiar flags."""
    guard._alert_sent = True
    guard._block_active = True

    guard.reset_manual()

    assert guard._alert_sent is False
    assert guard._block_active is False


def test_get_openrouter_sync(guard):
    """get_openrouter_sync debe retornar instancia singleton de OpenRouterClient."""
    from core.cost_guard import get_openrouter_sync

    client = get_openrouter_sync()
    assert client is not None
    # Segunda llamada debe ser la misma instancia
    client2 = get_openrouter_sync()
    assert client is client2


@pytest.mark.asyncio
async def test_check_exactly_at_alert_threshold(guard):
    """En threshold exacto de alerta ($5), debe alertar."""
    mock_client = MagicMock()
    mock_client.spent_today = 5.0  # Exactamente el threshold
    mock_alert = AsyncMock()

    with (
        patch("core.cost_guard.get_openrouter", new=AsyncMock(return_value=mock_client)),
        patch.object(guard, "_send_telegram_alert", new=mock_alert),
    ):
        result = await guard.check()

    assert result["status"] == "alerted"
    assert result["alert_sent"] is True


@pytest.mark.asyncio
async def test_check_exactly_at_block_threshold(guard):
    """En threshold exacto de bloqueo ($15), debe bloquear."""
    mock_client = MagicMock()
    mock_client.spent_today = 15.0  # Exactamente el threshold
    mock_alert = AsyncMock()

    with (
        patch("core.cost_guard.get_openrouter", new=AsyncMock(return_value=mock_client)),
        patch.object(guard, "_send_telegram_alert", new=mock_alert),
    ):
        result = await guard.check()

    assert result["status"] == "blocked"
    assert result["block_active"] is True


@pytest.mark.asyncio
async def test_check_alert_then_block_progression(guard):
    """Primero alerta, luego bloqueo al aumentar gasto."""
    mock_client = MagicMock()
    mock_alert = AsyncMock()

    # Paso 1: gasto $6 → alerta
    mock_client.spent_today = 6.0
    with (
        patch("core.cost_guard.get_openrouter", new=AsyncMock(return_value=mock_client)),
        patch.object(guard, "_send_telegram_alert", new=mock_alert),
    ):
        result = await guard.check()
        assert result["status"] == "alerted"
        assert result["alert_sent"] is True

    # Paso 2: gasto $16 → bloqueo
    mock_client.spent_today = 16.0
    with (
        patch("core.cost_guard.get_openrouter", new=AsyncMock(return_value=mock_client)),
        patch.object(guard, "_send_telegram_alert", new=mock_alert),
    ):
        result = await guard.check()
        assert result["status"] == "blocked"
        assert result["block_active"] is True
        assert guard.is_blocked() is True
