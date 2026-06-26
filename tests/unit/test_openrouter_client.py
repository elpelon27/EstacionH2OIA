"""Tests para core/openrouter_client.py."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.openrouter_client import OpenRouterClient


@pytest.fixture
def client():
    """Fixture: instancia fresca de OpenRouterClient."""
    OpenRouterClient._instance = None
    return OpenRouterClient.get_instance()


def test_singleton_pattern(client):
    """get_instance debe retornar siempre la misma instancia."""
    client2 = OpenRouterClient.get_instance()
    assert client is client2


def test_initial_spent_today_zero(client):
    """Al iniciar, spent_today debe ser 0."""
    assert client.spent_today == 0.0


def test_reset_daily_spent(client):
    """reset_daily_spent debe poner spent_today en 0."""
    client._spent_today = 5.5
    client.reset_daily_spent()
    assert client.spent_today == 0.0


def test_estimate_cost_glm(client):
    """Costo de GLM-4.5 debe calcularse correctamente."""
    cost = client._estimate_cost("z-ai/glm-4.5", 1000, 500)
    expected = round((1000 / 1_000_000 * 0.60) + (500 / 1_000_000 * 2.20), 6)
    assert cost == expected


def test_estimate_cost_claude(client):
    """Costo de Claude Sonnet debe ser más alto que GLM."""
    cost_claude = client._estimate_cost("anthropic/claude-sonnet-4.5", 1000, 500)
    cost_glm = client._estimate_cost("z-ai/glm-4.5", 1000, 500)
    assert cost_claude > cost_glm


def test_estimate_cost_unknown_model(client):
    """Modelo desconocido debe usar pricing default."""
    cost = client._estimate_cost("unknown/model", 1000, 500)
    assert cost > 0


@pytest.mark.asyncio
async def test_chat_success(client):
    """chat() debe retornar respuesta cuando API funciona."""
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "Hola desde OpenRouter"
    mock_response.usage.prompt_tokens = 10
    mock_response.usage.completion_tokens = 5
    mock_response.usage.total_tokens = 15

    with patch.object(
        client.client.chat.completions, "create", new=AsyncMock(return_value=mock_response)
    ):
        result = await client.chat(
            messages=[{"role": "user", "content": "test"}],
            model="z-ai/glm-4.5",
        )

    assert result["response"] == "Hola desde OpenRouter"
    assert result["model"] == "z-ai/glm-4.5"
    assert result["usage"]["prompt_tokens"] == 10
    assert result["cost_usd"] > 0
    assert client.spent_today > 0


@pytest.mark.asyncio
async def test_chat_error(client):
    """chat() debe propagar excepciones."""
    with (
        patch.object(
            client.client.chat.completions,
            "create",
            new=AsyncMock(side_effect=Exception("API down")),
        ),
        pytest.raises(Exception, match="API down"),
    ):
        await client.chat(messages=[{"role": "user", "content": "test"}])
