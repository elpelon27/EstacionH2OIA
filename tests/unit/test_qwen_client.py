"""Tests para core/qwen_client.py."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from core.qwen_client import QwenClient


@pytest.fixture
def client():
    """Fixture: instancia fresca de QwenClient."""
    QwenClient._instance = None
    return QwenClient.get_instance()


def test_singleton_pattern(client):
    """get_instance debe retornar siempre la misma instancia."""
    client2 = QwenClient.get_instance()
    assert client is client2


def test_default_model(client):
    """Default model debe ser qwen2.5:7b."""
    assert client.default_model == "qwen2.5:7b"


def test_base_url(client):
    """Base URL debe apuntar a localhost:11434."""
    assert client.base_url == "http://localhost:11434"


@pytest.mark.asyncio
async def test_chat_success(client):
    """chat() debe retornar respuesta cuando Ollama funciona."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "message": {"content": "Hola desde Qwen"},
        "eval_count": 20,
        "prompt_eval_count": 10,
    }
    mock_response.raise_for_status = MagicMock()

    with patch.object(client.client, "post", new=AsyncMock(return_value=mock_response)):
        result = await client.chat(
            messages=[{"role": "user", "content": "test"}],
            model="qwen2.5:7b",
        )

    assert result["response"] == "Hola desde Qwen"
    assert result["model"] == "qwen2.5:7b"
    assert result["cost_usd"] == 0.0
    assert result["latency_ms"] >= 0
    assert result["usage"]["prompt_tokens"] == 10
    assert result["usage"]["completion_tokens"] == 20


@pytest.mark.asyncio
async def test_chat_connect_error(client):
    """chat() debe lanzar RuntimeError si Ollama no disponible."""
    with (
        patch.object(
            client.client,
            "post",
            new=AsyncMock(side_effect=httpx.ConnectError("Connection refused")),
        ),
        pytest.raises(RuntimeError, match="Ollama no disponible"),
    ):
        await client.chat(messages=[{"role": "user", "content": "test"}])


@pytest.mark.asyncio
async def test_list_models_success(client):
    """list_models debe retornar lista de nombres."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "models": [
            {"name": "qwen2.5:7b"},
            {"name": "qwen2.5:3b"},
            {"name": "llama3.2:1b"},
        ]
    }
    mock_response.raise_for_status = MagicMock()

    with patch.object(client.client, "get", new=AsyncMock(return_value=mock_response)):
        models = await client.list_models()

    assert len(models) == 3
    assert "qwen2.5:7b" in models


@pytest.mark.asyncio
async def test_list_models_error(client):
    """list_models debe retornar [] si hay error."""
    with patch.object(client.client, "get", new=AsyncMock(side_effect=Exception("Network error"))):
        models = await client.list_models()

    assert models == []
