"""Tests para core/workload_router.py."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.workload_router import ROUTE_TABLE, Route, WorkloadRouter, get_router


@pytest.fixture
def router():
    """Fixture: instancia fresca de WorkloadRouter."""
    return WorkloadRouter()


def test_get_router_singleton():
    """get_router debe retornar siempre la misma instancia."""
    r1 = get_router()
    r2 = get_router()
    assert r1 is r2


def test_resolve_whatsapp_to_qwen(router):
    """whatsapp_message debe rutear a Qwen local."""
    assert router.resolve("whatsapp_message") == Route.QWEN_LOCAL


def test_resolve_payment_to_qwen(router):
    """payment_received debe rutear a Qwen local."""
    assert router.resolve("payment_received") == Route.QWEN_LOCAL


def test_resolve_architect_to_fusion(router):
    """architect_request debe rutear a Fusion."""
    assert router.resolve("architect_request") == Route.FUSION


def test_resolve_code_complex_to_deepseek(router):
    """code_generation_complex debe rutear a DeepSeek."""
    assert router.resolve("code_generation_complex") == Route.OPENROUTER_DEEPSEEK


def test_resolve_unknown_trigger_defaults_qwen(router):
    """Trigger desconocido debe defaultear a Qwen local."""
    assert router.resolve("unknown_trigger_xyz") == Route.QWEN_LOCAL


def test_route_table_completeness():
    """ROUTE_TABLE debe tener al menos 10 triggers mapeados."""
    assert len(ROUTE_TABLE) >= 10


@pytest.mark.asyncio
async def test_execute_qwen_local(router):
    """execute() con trigger whatsapp debe llamar a Qwen."""
    mock_qwen = MagicMock()
    mock_qwen.chat = AsyncMock(return_value={"response": "Hola", "model": "qwen2.5:7b"})

    with patch("core.workload_router.get_qwen", new=AsyncMock(return_value=mock_qwen)):
        result = await router.execute(
            trigger="whatsapp_message",
            messages=[{"role": "user", "content": "hola"}],
        )

    assert result["response"] == "Hola"
    mock_qwen.chat.assert_called_once()


@pytest.mark.asyncio
async def test_execute_fusion(router):
    """execute() con trigger architect_request debe llamar a Fusion."""
    mock_fusion = MagicMock()
    mock_fusion.run = AsyncMock(
        return_value={
            "winner_response": "Mejor respuesta",
            "winner_model": "z-ai/glm-4.5",
            "score": 8.5,
        }
    )

    with patch("core.workload_router.get_fusion", return_value=mock_fusion):
        result = await router.execute(
            trigger="architect_request",
            messages=[{"role": "user", "content": "diseña arquitectura"}],
        )

    assert result["winner_response"] == "Mejor respuesta"
    mock_fusion.run.assert_called_once()


@pytest.mark.asyncio
async def test_execute_openrouter_single(router):
    """execute() con trigger code_generation_complex debe llamar a OpenRouter DeepSeek."""
    mock_or = MagicMock()
    mock_or.chat = AsyncMock(
        return_value={
            "response": "def foo(): pass",
            "model": "deepseek/deepseek-chat-v3.2",
        }
    )

    with patch("core.workload_router.get_openrouter", new=AsyncMock(return_value=mock_or)):
        result = await router.execute(
            trigger="code_generation_complex",
            messages=[{"role": "user", "content": "escribe función"}],
        )

    assert result["response"] == "def foo(): pass"
    assert result["model"] == "deepseek/deepseek-chat-v3.2"
    mock_or.chat.assert_called_once()
