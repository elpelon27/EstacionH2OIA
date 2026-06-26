"""Tests para core/fusion.py."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.fusion import FusionTournament, get_fusion


@pytest.fixture
def fusion():
    """Fixture: instancia fresca de FusionTournament."""
    return FusionTournament()


def test_get_fusion_singleton():
    """get_fusion debe retornar siempre la misma instancia."""
    f1 = get_fusion()
    f2 = get_fusion()
    assert f1 is f2


@pytest.mark.asyncio
async def test_run_models_parallel_success(fusion):
    """_run_models_parallel debe ejecutar 4 modelos y recolectar respuestas."""
    mock_responses = [
        {"response": "Respuesta GLM", "model": "z-ai/glm-4.5", "cost_usd": 0.001, "usage": {}},
        {
            "response": "Respuesta Claude",
            "model": "anthropic/claude-sonnet-4.5",
            "cost_usd": 0.005,
            "usage": {},
        },
        {
            "response": "Respuesta DeepSeek",
            "model": "deepseek/deepseek-chat-v3.2",
            "cost_usd": 0.0001,
            "usage": {},
        },
        {
            "response": "Respuesta Gemini",
            "model": "google/gemini-2.5-flash",
            "cost_usd": 0.0002,
            "usage": {},
        },
    ]

    mock_client = MagicMock()
    mock_client.chat = AsyncMock(side_effect=mock_responses)

    with patch("core.fusion.get_openrouter", new=AsyncMock(return_value=mock_client)):
        responses = await fusion._run_models_parallel(
            models=[
                "z-ai/glm-4.5",
                "anthropic/claude-sonnet-4.5",
                "deepseek/deepseek-chat-v3.2",
                "google/gemini-2.5-flash",
            ],
            messages=[{"role": "user", "content": "test"}],
            temperature=0.3,
            max_tokens=100,
        )

    assert len(responses) == 4
    assert all(r["success"] for r in responses)
    assert responses[0]["model"] == "z-ai/glm-4.5"
    assert responses[1]["model"] == "anthropic/claude-sonnet-4.5"


@pytest.mark.asyncio
async def test_run_models_parallel_one_fails(fusion):
    """Si un modelo falla, los otros deben continuar."""
    mock_responses = [
        {"response": "OK 1", "model": "z-ai/glm-4.5", "cost_usd": 0.001, "usage": {}},
        Exception("API error"),
        {
            "response": "OK 3",
            "model": "deepseek/deepseek-chat-v3.2",
            "cost_usd": 0.0001,
            "usage": {},
        },
        {"response": "OK 4", "model": "google/gemini-2.5-flash", "cost_usd": 0.0002, "usage": {}},
    ]

    mock_client = MagicMock()
    mock_client.chat = AsyncMock(side_effect=mock_responses)

    with patch("core.fusion.get_openrouter", new=AsyncMock(return_value=mock_client)):
        responses = await fusion._run_models_parallel(
            models=[
                "z-ai/glm-4.5",
                "anthropic/claude-sonnet-4.5",
                "deepseek/deepseek-chat-v3.2",
                "google/gemini-2.5-flash",
            ],
            messages=[{"role": "user", "content": "test"}],
            temperature=0.3,
            max_tokens=100,
        )

    assert len(responses) == 4
    assert responses[0]["success"] is True
    assert responses[1]["success"] is False
    assert responses[1]["error"] == "API error"
    assert responses[2]["success"] is True


@pytest.mark.asyncio
async def test_fusion_run_complete(fusion):
    """run() debe ejecutar tournament completo y retornar ganador."""
    mock_responses = [
        {"response": "Mejor respuesta", "model": "z-ai/glm-4.5", "cost_usd": 0.001, "usage": {}},
        {
            "response": "Respuesta media",
            "model": "anthropic/claude-sonnet-4.5",
            "cost_usd": 0.005,
            "usage": {},
        },
        {
            "response": "Otra respuesta",
            "model": "deepseek/deepseek-chat-v3.2",
            "cost_usd": 0.0001,
            "usage": {},
        },
        {
            "response": "Última respuesta",
            "model": "google/gemini-2.5-flash",
            "cost_usd": 0.0002,
            "usage": {},
        },
    ]

    mock_client = MagicMock()
    mock_client.chat = AsyncMock(side_effect=mock_responses)

    mock_judge_result = {
        "winner_model": "z-ai/glm-4.5",
        "winner_response": "Mejor respuesta",
        "winner_score": 8.5,
        "reason": "Más coherente y completo",
        "scores": {"z-ai/glm-4.5": {"score": 8.5, "reason": "best"}},
        "judge_cost_usd": 0.002,
    }

    with (
        patch("core.fusion.get_openrouter", new=AsyncMock(return_value=mock_client)),
        patch.object(fusion.judge, "evaluate", new=AsyncMock(return_value=mock_judge_result)),
    ):
        result = await fusion.run(
            messages=[{"role": "user", "content": "¿Cuánto es 2+2?"}],
        )

    assert result["winner_model"] == "z-ai/glm-4.5"
    assert result["winner_response"] == "Mejor respuesta"
    assert result["score"] == 8.5
    assert result["needs_human_escalation"] is False  # 8.5 >= 7.0
    assert len(result["all_responses"]) == 4
    assert result["total_cost_usd"] > 0


@pytest.mark.asyncio
async def test_fusion_needs_human_escalation(fusion):
    """Si score < 7.0, needs_human_escalation debe ser True."""
    mock_responses = [
        {"response": "Respuesta pobre", "model": "z-ai/glm-4.5", "cost_usd": 0.001, "usage": {}},
    ]

    mock_client = MagicMock()
    mock_client.chat = AsyncMock(side_effect=mock_responses)

    mock_judge_result = {
        "winner_model": "z-ai/glm-4.5",
        "winner_response": "Respuesta pobre",
        "winner_score": 4.0,
        "reason": "Baja calidad",
        "scores": {"z-ai/glm-4.5": {"score": 4.0, "reason": "poor"}},
        "judge_cost_usd": 0.001,
    }

    with (
        patch("core.fusion.get_openrouter", new=AsyncMock(return_value=mock_client)),
        patch.object(fusion.judge, "evaluate", new=AsyncMock(return_value=mock_judge_result)),
    ):
        result = await fusion.run(
            messages=[{"role": "user", "content": "test"}],
        )

    assert result["needs_human_escalation"] is True
    assert result["score"] < 7.0
