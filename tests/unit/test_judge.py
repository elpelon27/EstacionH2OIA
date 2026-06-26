"""Tests para core/judge.py."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.judge import CRITERIA_WEIGHTS, JUDGE_SYSTEM_PROMPT, Judge


@pytest.fixture
def judge():
    """Fixture: instancia de Judge."""
    return Judge()


def test_criteria_weights_sum_to_one():
    """Los pesos de los criterios deben sumar 1.0."""
    total = sum(CRITERIA_WEIGHTS.values())
    assert abs(total - 1.0) < 0.001


def test_judge_system_prompt_exists():
    """El system prompt del juez debe existir y no estar vacío."""
    assert len(JUDGE_SYSTEM_PROMPT) > 100
    assert "coherencia" in JUDGE_SYSTEM_PROMPT
    assert "seguridad" in JUDGE_SYSTEM_PROMPT


@pytest.mark.asyncio
async def test_evaluate_no_valid_responses(judge):
    """Si no hay respuestas válidas, retornar winner 'none'."""
    responses = [
        {"model": "z-ai/glm-4.5", "success": False, "response": ""},
        {"model": "anthropic/claude-sonnet-4.5", "success": False, "response": ""},
    ]

    result = await judge.evaluate(
        prompt=[{"role": "user", "content": "test"}],
        responses=responses,
    )

    assert result["winner_model"] == "none"
    assert result["winner_score"] == 0.0


@pytest.mark.asyncio
async def test_evaluate_single_valid_response(judge):
    """Si solo 1 respuesta válida, es ganador por defecto."""
    responses = [
        {"model": "z-ai/glm-4.5", "success": True, "response": "Única respuesta"},
        {"model": "anthropic/claude-sonnet-4.5", "success": False, "response": ""},
    ]

    result = await judge.evaluate(
        prompt=[{"role": "user", "content": "test"}],
        responses=responses,
    )

    assert result["winner_model"] == "z-ai/glm-4.5"
    assert result["winner_response"] == "Única respuesta"
    assert result["winner_score"] == 7.0  # Default para única respuesta


@pytest.mark.asyncio
async def test_evaluate_multiple_responses_with_mock(judge):
    """Con múltiples respuestas válidas, el juez debe evaluar y seleccionar."""
    responses = [
        {"model": "z-ai/glm-4.5", "success": True, "response": "Respuesta 1"},
        {"model": "anthropic/claude-sonnet-4.5", "success": True, "response": "Respuesta 2"},
    ]

    mock_judge_response = """```json
    {
      "evaluations": [
        {
          "model": "z-ai/glm-4.5",
          "scores": {
            "coherencia": 8, "seguridad": 9, "adherencia_reglas": 7,
            "completitud": 8, "calidad_tecnica": 9
          },
          "total_score": 8.3,
          "reason": "Buena respuesta"
        },
        {
          "model": "anthropic/claude-sonnet-4.5",
          "scores": {
            "coherencia": 7, "seguridad": 8, "adherencia_reglas": 6,
            "completitud": 7, "calidad_tecnica": 8
          },
          "total_score": 7.2,
          "reason": "Respuesta aceptable"
        }
      ],
      "winner": "z-ai/glm-4.5",
      "winner_reason": "Mayor coherencia y calidad técnica"
    }
    ```"""

    mock_client = MagicMock()
    mock_client.chat = AsyncMock(
        return_value={
            "response": mock_judge_response,
            "cost_usd": 0.002,
            "usage": {},
        }
    )

    with patch("core.judge.get_openrouter", new=AsyncMock(return_value=mock_client)):
        result = await judge.evaluate(
            prompt=[{"role": "user", "content": "test"}],
            responses=responses,
        )

    assert result["winner_model"] == "z-ai/glm-4.5"
    assert result["winner_response"] == "Respuesta 1"
    assert result["winner_score"] > 0
    assert "z-ai/glm-4.5" in result["scores"]
    assert "anthropic/claude-sonnet-4.5" in result["scores"]
    assert result["judge_cost_usd"] == 0.002


@pytest.mark.asyncio
async def test_evaluate_judge_error_fallback(judge):
    """Si el juez falla, debe hacer fallback a primera respuesta válida."""
    responses = [
        {"model": "z-ai/glm-4.5", "success": True, "response": "Respuesta 1"},
        {"model": "anthropic/claude-sonnet-4.5", "success": True, "response": "Respuesta 2"},
    ]

    mock_client = MagicMock()
    mock_client.chat = AsyncMock(side_effect=Exception("Judge API down"))

    with patch("core.judge.get_openrouter", new=AsyncMock(return_value=mock_client)):
        result = await judge.evaluate(
            prompt=[{"role": "user", "content": "test"}],
            responses=responses,
        )

    assert result["winner_model"] == "z-ai/glm-4.5"
    assert result["winner_response"] == "Respuesta 1"
    assert result["winner_score"] == 5.0  # Fallback score


def test_build_judge_prompt(judge):
    """_build_judge_prompt debe construir mensajes correctamente."""
    prompt = [{"role": "user", "content": "¿Cuánto es 2+2?"}]
    responses = [
        {"model": "z-ai/glm-4.5", "response": "4"},
        {"model": "anthropic/claude-sonnet-4.5", "response": "Es 4"},
    ]

    messages = judge._build_judge_prompt(prompt, responses)

    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert "¿Cuánto es 2+2?" in messages[1]["content"]
    assert "z-ai/glm-4.5" in messages[1]["content"]
    assert "4" in messages[1]["content"]


def test_parse_judge_response_valid_json(judge):
    """_parse_judge_response debe parsear JSON válido."""
    judge_response = """{
      "evaluations": [
        {
          "model": "z-ai/glm-4.5",
          "scores": {
            "coherencia": 8, "seguridad": 9, "adherencia_reglas": 7,
            "completitud": 8, "calidad_tecnica": 9
          },
          "total_score": 8.3,
          "reason": "Buena"
        }
      ],
      "winner": "z-ai/glm-4.5",
      "winner_reason": "Mejor respuesta"
    }"""

    responses = [{"model": "z-ai/glm-4.5", "response": "4"}]

    result = judge._parse_judge_response(judge_response, responses)

    assert result["winner_model"] == "z-ai/glm-4.5"
    assert result["winner_response"] == "4"
    assert result["winner_score"] > 0
    assert "z-ai/glm-4.5" in result["scores"]


def test_parse_judge_response_invalid_json(judge):
    """_parse_judge_response debe hacer fallback si JSON es inválido."""
    judge_response = "Esto no es JSON"
    responses = [{"model": "z-ai/glm-4.5", "response": "4"}]

    result = judge._parse_judge_response(judge_response, responses)

    assert result["winner_model"] == "z-ai/glm-4.5"
    assert result["winner_score"] == 5.0  # Fallback
