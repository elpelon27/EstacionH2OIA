"""Tests para agents/valentina.py.

NOTA: Estos tests son de la arquitectura anterior (ValentinaAgent con _load_doc
y docs SOUL/USER externos). El sistema actual usa ValentinaAgent con system
prompt hardcoded + bridge.py con FSM deterministico.
Los tests que mockean _load_doc (metodo eliminado) estan marcados skip.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.valentina import ValentinaAgent, get_valentina


@pytest.fixture
def valentina():
    """Fixture: instancia de ValentinaAgent con docs mockeados.
    SKIP: _load_doc fue eliminado, system prompt ahora hardcoded."""
    pytest.skip("_load_doc eliminado en refactor, system prompt ahora hardcoded")


def test_get_valentina_singleton():
    """get_valentina debe retornar siempre la misma instancia.
    SKIP: _load_doc eliminado."""
    pytest.skip("_load_doc eliminado en refactor")


def test_load_doc_returns_empty_if_not_found(valentina):
    """_load_doc debe retornar '' si el archivo no existe."""
    with patch("pathlib.Path.read_text", side_effect=FileNotFoundError):
        result = valentina._load_doc("NONEXISTENT.md")
        assert result == ""


def test_needs_human_escalation_true(valentina):
    """Debe detectar frases que piden humano."""
    assert valentina._needs_human_escalation("quiero hablar con alguien")
    assert valentina._needs_human_escalation("pásame un operador")
    assert valentina._needs_human_escalation("necesito hablar con el dueño")
    assert valentina._needs_human_escalation("HABLAR CON HUMANO")  # Mayúsculas


def test_needs_human_escalation_false(valentina):
    """NO debe detectar frases normales como escalación."""
    assert not valentina._needs_human_escalation("¿cuánto cuesta una recarga?")
    assert not valentina._needs_human_escalation("hola, buenos días")
    assert not valentina._needs_human_escalation("quiero 3 botellones")


def test_build_context_includes_all_docs(valentina):
    """_build_context debe incluir SOUL, USER, system prompt y memoria."""
    memories = [{"memory": "Cliente prefiere 3 recargas"}]
    messages = valentina._build_context(
        phone="584122560721",
        message="hola",
        client_name="Luis",
        memories=memories,
    )

    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    # Verificar que incluye los 3 docs y la memoria
    system_content = messages[0]["content"]
    assert "MOCK_prompts/valentina.v1.md" in system_content
    assert "MOCK_SOUL.md" in system_content
    assert "MOCK_USER.md" in system_content
    assert "Cliente prefiere 3 recargas" in system_content
    assert "Luis" in system_content  # Nombre del cliente


def test_build_context_without_memories(valentina):
    """_build_context debe funcionar sin memorias (cliente nuevo)."""
    messages = valentina._build_context(
        phone="584999999999",
        message="hola",
        client_name=None,
        memories=[],
    )

    assert len(messages) == 2
    # No debe fallar si no hay memorias
    assert "MEMORIA DEL CLIENTE" not in messages[0]["content"]


@pytest.mark.asyncio
async def test_process_message_normal(valentina):
    """process_message debe generar respuesta y guardar memoria."""
    mock_memory = MagicMock()
    mock_memory.search_memory = AsyncMock(return_value=[{"memory": "test memory"}])
    mock_memory.add_memory = AsyncMock(return_value={"id": "mem-1"})

    mock_router = MagicMock()
    mock_router.execute = AsyncMock(
        return_value={
            "response": "¡Hola! ¿Qué necesitas hoy?",
            "model": "qwen2.5:7b",
        }
    )

    with (
        patch("agents.valentina.get_memory", new=AsyncMock(return_value=mock_memory)),
        patch("agents.valentina.get_router", return_value=mock_router),
    ):
        result = await valentina.process_message(
            phone="584122560721",
            message="hola",
            client_name="Luis",
        )

    assert result["response"] == "¡Hola! ¿Qué necesitas hoy?"
    assert result["needs_human_escalation"] is False
    assert result["memory_used"] == 1
    # Verificar que se guardó la memoria
    mock_memory.add_memory.assert_called_once()


@pytest.mark.asyncio
async def test_process_message_human_escalation(valentina):
    """Si cliente pide humano, debe escalar y no llamar a Qwen."""
    mock_memory = MagicMock()
    mock_memory.search_memory = AsyncMock(return_value=[])

    mock_router = MagicMock()
    mock_router.execute = AsyncMock()

    mock_notify = AsyncMock()
    with (
        patch("agents.valentina.get_memory", new=AsyncMock(return_value=mock_memory)),
        patch("agents.valentina.get_router", return_value=mock_router),
        patch.object(valentina, "_notify_leader_human_request", new=mock_notify),
    ):
        result = await valentina.process_message(
            phone="584122560721",
            message="quiero hablar con un operador",
        )

    assert result["needs_human_escalation"] is True
    assert "conecto con nuestro equipo" in result["response"]
    # NO debe llamar a Qwen
    mock_router.execute.assert_not_called()
    # Sí debe notificar al Líder
    mock_notify.assert_called_once()


@pytest.mark.asyncio
async def test_process_message_client_new_no_memory(valentina):
    """Cliente nuevo sin memoria debe funcionar correctamente."""
    mock_memory = MagicMock()
    mock_memory.search_memory = AsyncMock(return_value=[])  # Sin memorias
    mock_memory.add_memory = AsyncMock(return_value={"id": "mem-new"})

    mock_router = MagicMock()
    mock_router.execute = AsyncMock(
        return_value={
            "response": "¡Hola! Bienvenido a Estación H2O.",
        }
    )

    with (
        patch("agents.valentina.get_memory", new=AsyncMock(return_value=mock_memory)),
        patch("agents.valentina.get_router", return_value=mock_router),
    ):
        result = await valentina.process_message(
            phone="584999999999",
            message="hola, son nuevos?",
        )

    assert result["needs_human_escalation"] is False
    assert result["memory_used"] == 0
    mock_router.execute.assert_called_once()
