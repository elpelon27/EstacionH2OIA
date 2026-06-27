"""Tests para memory/memory_client.py."""

from unittest.mock import MagicMock, patch

import pytest

from memory.memory_client import MemoryClient


@pytest.fixture
def mock_settings():
    """Mock settings para evitar cargar .env real."""
    with patch("core.config.get_settings") as mock:
        settings = MagicMock()
        settings.qdrant_url = "http://localhost:6333"
        settings.qdrant_api_key = "test-key"
        settings.qdrant_collection = "test_collection"
        settings.ollama_host = "http://localhost:11434"
        mock.return_value = settings
        yield settings


@pytest.fixture
def client(mock_settings):
    """Fixture: MemoryClient con mem0 mockeado."""
    with patch("mem0.Memory") as mock_memory_class:
        mock_instance = MagicMock()
        mock_memory_class.from_config.return_value = mock_instance
        MemoryClient._instance = None
        c = MemoryClient()
        return c


def test_singleton_pattern(client, mock_settings):
    """get_instance debe retornar siempre la misma instancia."""
    with patch("mem0.Memory"):
        c1 = MemoryClient.get_instance()
        c2 = MemoryClient.get_instance()
        assert c1 is c2


@pytest.mark.asyncio
async def test_add_memory_success(client):
    """add_memory debe guardar y retornar resultado con event."""
    client.client.add = MagicMock(return_value={"id": "mem-123", "event": "ADD"})

    result = await client.add_memory(
        content="Cliente prefiere 3 recargas los viernes",
        user_id="584122560721",
    )

    assert result["id"] == "mem-123"
    assert result["event_type"] == "ADD"
    client.client.add.assert_called_once()


@pytest.mark.asyncio
async def test_add_memory_with_metadata(client):
    """add_memory debe pasar metadata correctamente."""
    client.client.add = MagicMock(return_value={"id": "mem-456", "event": "ADD"})

    await client.add_memory(
        content="Cliente paga con Pago Móvil",
        user_id="584122560721",
        metadata={"category": "payment_method"},
    )

    args, kwargs = client.client.add.call_args
    assert kwargs["metadata"] == {"category": "payment_method"}


@pytest.mark.asyncio
async def test_search_memory_returns_list(client):
    """search_memory debe retornar lista de recuerdos."""
    client.client.search = MagicMock(
        return_value=[
            {"memory": "Prefiere 3 recargas", "score": 0.95},
            {"memory": "Paga con Pago Móvil", "score": 0.85},
        ]
    )

    results = await client.search_memory(
        query="¿qué prefiere?",
        user_id="584122560721",
    )

    assert len(results) == 2
    assert results[0]["memory"] == "Prefiere 3 recargas"
    assert results[0]["score"] == 0.95


@pytest.mark.asyncio
async def test_search_memory_empty(client):
    """search_memory debe retornar [] si no hay recuerdos."""
    client.client.search = MagicMock(return_value=[])

    results = await client.search_memory(
        query="cliente nuevo",
        user_id="584999999999",
    )

    assert results == []


@pytest.mark.asyncio
async def test_search_memory_error_returns_empty(client):
    """search_memory debe retornar [] si hay error."""
    client.client.search = MagicMock(side_effect=Exception("Qdrant connection error"))

    results = await client.search_memory(
        query="test",
        user_id="584122560721",
    )

    assert results == []


@pytest.mark.asyncio
async def test_get_client_memories(client):
    """get_client_memories debe retornar todos los recuerdos del cliente."""
    client.client.get_all = MagicMock(
        return_value=[
            {"memory": "Recuerdo 1"},
            {"memory": "Recuerdo 2"},
            {"memory": "Recuerdo 3"},
        ]
    )

    results = await client.get_client_memories(user_id="584122560721")

    assert len(results) == 3


@pytest.mark.asyncio
async def test_delete_memory_success(client):
    """delete_memory debe retornar True si se elimina correctamente."""
    client.client.delete = MagicMock()

    result = await client.delete_memory(memory_id="mem-123")

    assert result is True
    client.client.delete.assert_called_once_with(memory_id="mem-123")


@pytest.mark.asyncio
async def test_delete_memory_error(client):
    """delete_memory debe retornar False si hay error."""
    client.client.delete = MagicMock(side_effect=Exception("Not found"))

    result = await client.delete_memory(memory_id="mem-invalid")

    assert result is False
