"""Tests para core/workload_router.py."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from core.workload_router import WorkloadRouter, Route, ROUTE_TABLE, get_router


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


def test_resolve_payment_to_skill(router):
    """payment_received debe rutear a payment_skill."""
    assert router.resolve("payment_received") == Route.PAYMENT_SKILL


def test_resolve_inventory_to_skill(router):
    """inventory_check debe rutear a inventory_skill."""
    assert router.resolve("inventory_check") == Route.INVENTORY_SKILL


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
async def test_execute_inventory_skill(router):
    """execute() con trigger inventory_check debe llamar a InventorySkill."""
    with patch("skills.inventory_skill.InventorySkill.execute", new=AsyncMock(return_value={"success": True})):
        result = await router.execute(trigger="inventory_check", action="get_stock")
    assert result["success"] is True


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


@patch("core.workload_router.get_cost_guard")
@patch("core.workload_router.get_fusion")
async def test_execute_fusion(mock_get_fusion, mock_get_cost_guard, router):
    """execute() con trigger architect_request debe llamar a Fusion."""
    mock_fusion = MagicMock()
    mock_fusion.run = AsyncMock(return_value={
        "winner_response": "Mejor respuesta",
        "winner_model": "z-ai/glm-4.5",
        "score": 8.5,
    })
    mock_get_fusion.return_value = mock_fusion

    # Mock cost_guard.check() to return "ok" status
    mock_guard = MagicMock()
    mock_guard.check = AsyncMock(return_value={
        "status": "ok",
        "alert_sent": False,
        "block_active": False,
        "spent_today": 0.0,
    })
    mock_get_cost_guard.return_value = mock_guard

    result = await router.execute(
        trigger="architect_request",
        messages=[{"role": "user", "content": "diseña arquitectura"}],
    )

    assert result["winner_response"] == "Mejor respuesta"
    mock_fusion.run.assert_called_once()
