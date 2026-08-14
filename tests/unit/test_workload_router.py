"""Tests para core/workload_router.py."""
import sys
from unittest.mock import MagicMock

# Mock skills.payment_skill module before any imports (ollama not in CI)
mock_payment_skill = MagicMock()
mock_payment_skill.PaymentSkill = MagicMock()
sys.modules["skills.payment_skill"] = mock_payment_skill

# NOTE (2026-08-13): NO se mockea el paquete 'skills' completo (sys.modules['skills'])
# — eso rompía 'from skills.inventory_skill import ...' y 'skills.self_improve_skill'
# con "skills is not a package". Solo payment_skill necesita mock (depende de ollama),
# y se expone como atributo del paquete skills real para que 'skills.payment_skill' funcione.
import skills as _skills

_skills.payment_skill = mock_payment_skill

from datetime import time
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


def test_resolve_self_improve_blocked_during_business_hours(router):
    """self_improve_request debe bloquearse en horario laboral y caer a QWEN_LOCAL."""
    with patch.object(router, "_is_business_hours", return_value=True):
        route = router.resolve("self_improve_request")
        assert route == Route.QWEN_LOCAL


def test_resolve_self_improve_allowed_after_hours(router):
    """self_improve_request debe permitirse fuera de horario laboral."""
    with patch.object(router, "_is_business_hours", return_value=False):
        route = router.resolve("self_improve_request")
        assert route == Route.SELF_IMPROVE_SKILL


@pytest.mark.asyncio
async def test_execute_inventory_skill(router):
    """execute() con trigger inventory_check debe llamar a InventorySkill."""
    with patch(
        "skills.inventory_skill.InventorySkill.execute",
        new=AsyncMock(return_value={"success": True}),
    ):
        result = await router.execute(trigger="inventory_check", action="get_stock")
    assert result["success"] is True


@pytest.mark.asyncio
async def test_execute_payment_skill(router):
    """execute() con trigger payment_received debe llamar a PaymentSkill."""
    # Patch the mocked module's PaymentSkill class
    import skills.payment_skill
    with patch.object(skills.payment_skill, "PaymentSkill") as mock_skill_class:
        mock_skill_instance = AsyncMock()
        mock_skill_instance.execute = AsyncMock(return_value={"success": True, "amount": 100})
        mock_skill_class.return_value = mock_skill_instance

        result = await router.execute(trigger="payment_received", amount=100)

    assert result["success"] is True
    assert result["amount"] == 100
    mock_skill_instance.execute.assert_called_once_with(amount=100)


@pytest.mark.asyncio
async def test_execute_self_improve_skill(router):
    """execute() con trigger self_improve_request debe llamar a SelfImproveSkill."""
    with patch(
        "skills.self_improve_skill.SelfImproveSkill.execute",
        new=AsyncMock(return_value={"improved": True}),
    ), patch.object(router, "_is_business_hours", return_value=False):
        result = await router.execute(trigger="self_improve_request")
    assert result["improved"] is True


@pytest.mark.asyncio
async def test_execute_dispatch_skill(router):
    """execute() con trigger dispatch_request debe llamar a DispatcherSkill."""
    with patch("skills.dispatcher_skill.get_dispatcher_skill") as mock_get:
        mock_dispatcher = AsyncMock()
        mock_dispatcher.execute = AsyncMock(return_value={"dispatched": True})
        mock_get.return_value = mock_dispatcher

        result = await router.execute(trigger="dispatch_request", action="route")

    assert result["dispatched"] is True
    mock_dispatcher.execute.assert_called_once_with(action="route")


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
@pytest.mark.asyncio
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


@patch("core.workload_router.get_cost_guard")
@pytest.mark.asyncio
async def test_execute_fusion_blocked_by_cost_guard(mock_get_cost_guard, router):
    """Fusion debe caer a Qwen local si cost_guard bloquea."""
    mock_guard = MagicMock()
    mock_guard.check = AsyncMock(return_value={
        "status": "blocked",
        "alert_sent": True,
        "block_active": True,
        "spent_today": 55.0,
    })
    mock_get_cost_guard.return_value = mock_guard

    mock_qwen = MagicMock()
    mock_qwen.chat = AsyncMock(return_value={"response": "Fallback Qwen", "model": "qwen2.5:7b"})

    with patch("core.workload_router.get_qwen", new=AsyncMock(return_value=mock_qwen)):
        result = await router.execute(
            trigger="architect_request",
            messages=[{"role": "user", "content": "test"}],
        )

    assert result["response"] == "Fallback Qwen"
    mock_qwen.chat.assert_called_once()


@patch("core.workload_router.get_cost_guard")
@patch("core.workload_router.get_rate_limiter")
@pytest.mark.asyncio
async def test_execute_openrouter_rate_limited_fallback(
    mock_get_rate_limiter, mock_get_cost_guard, router
):
    """OpenRouter debe caer a Qwen local si rate limiter bloquea."""
    mock_guard = MagicMock()
    mock_guard.check = AsyncMock(return_value={"status": "ok", "spent_today": 0.0})
    mock_get_cost_guard.return_value = mock_guard

    mock_rate_limiter = AsyncMock()
    mock_rate_limiter.acquire = AsyncMock(return_value=False)
    mock_get_rate_limiter.return_value = mock_rate_limiter

    mock_qwen = MagicMock()
    mock_qwen.chat = AsyncMock(return_value={"response": "Fallback rate", "model": "qwen2.5:7b"})

    with patch("core.workload_router.get_qwen", new=AsyncMock(return_value=mock_qwen)):
        result = await router.execute(
            trigger="code_generation_complex",
            messages=[{"role": "user", "content": "test"}],
        )

    assert result["response"] == "Fallback rate"


@patch("core.workload_router.get_cost_guard")
@patch("core.workload_router.get_rate_limiter")
@patch("core.workload_router.get_circuit_breaker_registry")
@pytest.mark.asyncio
async def test_execute_openrouter_circuit_open_fallback(
    mock_get_cb, mock_get_rate, mock_get_cost, router
):
    """OpenRouter debe caer a Qwen local si circuit breaker está abierto."""
    from core.circuit_breaker import CircuitOpenError

    mock_guard = MagicMock()
    mock_guard.check = AsyncMock(return_value={"status": "ok", "spent_today": 0.0})
    mock_get_cost.return_value = mock_guard

    mock_rate = AsyncMock()
    mock_rate.acquire = AsyncMock(return_value=True)
    mock_get_rate.return_value = mock_rate

    mock_cb_registry = MagicMock()
    mock_cb_registry.call = AsyncMock(side_effect=CircuitOpenError("circuit open"))
    mock_get_cb.return_value = mock_cb_registry

    mock_qwen = MagicMock()
    mock_qwen.chat = AsyncMock(return_value={"response": "Fallback circuit", "model": "qwen2.5:7b"})

    with patch("core.workload_router.get_qwen", new=AsyncMock(return_value=mock_qwen)):
        result = await router.execute(
            trigger="code_generation_complex",
            messages=[{"role": "user", "content": "test"}],
        )

    assert result["response"] == "Fallback circuit"


@patch("core.workload_router.get_cost_guard")
@patch("core.workload_router.get_rate_limiter")
@patch("core.workload_router.get_circuit_breaker_registry")
@pytest.mark.asyncio
async def test_execute_openrouter_general_exception_fallback(
    mock_get_cb, mock_get_rate, mock_get_cost, router
):
    """OpenRouter debe caer a Qwen local ante cualquier excepción."""
    mock_guard = MagicMock()
    mock_guard.check = AsyncMock(return_value={"status": "ok", "spent_today": 0.0})
    mock_get_cost.return_value = mock_guard

    mock_rate = AsyncMock()
    mock_rate.acquire = AsyncMock(return_value=True)
    mock_get_rate.return_value = mock_rate

    mock_cb_registry = MagicMock()
    mock_cb_registry.call = AsyncMock(side_effect=Exception("LLM error"))
    mock_get_cb.return_value = mock_cb_registry

    mock_qwen = MagicMock()
    mock_qwen.chat = AsyncMock(return_value={"response": "Fallback error", "model": "qwen2.5:7b"})

    with patch("core.workload_router.get_qwen", new=AsyncMock(return_value=mock_qwen)):
        result = await router.execute(
            trigger="code_generation_complex",
            messages=[{"role": "user", "content": "test"}],
        )

    assert result["response"] == "Fallback error"


@patch("core.workload_router.get_cost_guard")
@patch("core.workload_router.get_rate_limiter")
@patch("core.workload_router.get_circuit_breaker_registry")
@pytest.mark.asyncio
async def test_execute_openrouter_glm_success(mock_get_cb, mock_get_rate, mock_get_cost, router):
    """execute() con OPENROUTER_GLM debe llamar a OpenRouter chat."""
    mock_guard = MagicMock()
    mock_guard.check = AsyncMock(return_value={"status": "ok", "spent_today": 0.0})
    mock_get_cost.return_value = mock_guard

    mock_rate = AsyncMock()
    mock_rate.acquire = AsyncMock(return_value=True)
    mock_get_rate.return_value = mock_rate

    mock_or_client = AsyncMock()
    mock_or_client.chat = AsyncMock(return_value={
        "response": "GLM response",
        "model": "z-ai/glm-4.5",
        "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
        "cost_usd": 0.001,
    })

    with patch("core.workload_router.get_openrouter", new=AsyncMock(return_value=mock_or_client)):
        mock_cb_registry = MagicMock()
        async def mock_call(name, func, *args, **kwargs):
            return await func(*args, **kwargs)
        mock_cb_registry.call = AsyncMock(side_effect=mock_call)
        mock_get_cb.return_value = mock_cb_registry

        result = await router.execute(
            trigger="log_summary_daily",
            messages=[{"role": "user", "content": "summary"}],
        )

    assert result["response"] == "GLM response"
    mock_or_client.chat.assert_called_once()


@patch("core.workload_router.get_cost_guard")
@patch("core.workload_router.get_rate_limiter")
@patch("core.workload_router.get_circuit_breaker_registry")
@pytest.mark.asyncio
async def test_execute_openrouter_claude_success(mock_get_cb, mock_get_rate, mock_get_cost, router):
    """execute() con OPENROUTER_CLAUDE debe llamar a OpenRouter chat."""
    mock_guard = MagicMock()
    mock_guard.check = AsyncMock(return_value={"status": "ok", "spent_today": 0.0})
    mock_get_cost.return_value = mock_guard

    mock_rate = AsyncMock()
    mock_rate.acquire = AsyncMock(return_value=True)
    mock_get_rate.return_value = mock_rate

    mock_or_client = AsyncMock()
    mock_or_client.chat = AsyncMock(return_value={
        "response": "Claude response",
        "model": "anthropic/claude-sonnet-4.5",
        "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
        "cost_usd": 0.005,
    })

    with patch("core.workload_router.get_openrouter", new=AsyncMock(return_value=mock_or_client)):
        mock_cb_registry = MagicMock()
        async def mock_call(name, func, *args, **kwargs):
            return await func(*args, **kwargs)
        mock_cb_registry.call = AsyncMock(side_effect=mock_call)
        mock_get_cb.return_value = mock_cb_registry

        result = await router.execute(
            trigger="prompt_validation",
            messages=[{"role": "user", "content": "validate"}],
        )

    assert result["response"] == "Claude response"


@patch("core.workload_router.get_cost_guard")
@patch("core.workload_router.get_rate_limiter")
@patch("core.workload_router.get_circuit_breaker_registry")
@pytest.mark.asyncio
async def test_execute_openrouter_deepseek_success(
    mock_get_cb, mock_get_rate, mock_get_cost, router
):
    """execute() con OPENROUTER_DEEPSEEK debe llamar a OpenRouter chat."""
    mock_guard = MagicMock()
    mock_guard.check = AsyncMock(return_value={"status": "ok", "spent_today": 0.0})
    mock_get_cost.return_value = mock_guard

    mock_rate = AsyncMock()
    mock_rate.acquire = AsyncMock(return_value=True)
    mock_get_rate.return_value = mock_rate

    mock_or_client = AsyncMock()
    mock_or_client.chat = AsyncMock(return_value={
        "response": "DeepSeek response",
        "model": "deepseek/deepseek-chat-v3.2",
        "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
        "cost_usd": 0.0002,
    })

    with patch("core.workload_router.get_openrouter", new=AsyncMock(return_value=mock_or_client)):
        mock_cb_registry = MagicMock()
        async def mock_call(name, func, *args, **kwargs):
            return await func(*args, **kwargs)
        mock_cb_registry.call = AsyncMock(side_effect=mock_call)
        mock_get_cb.return_value = mock_cb_registry

        result = await router.execute(
            trigger="code_generation_complex",
            messages=[{"role": "user", "content": "code"}],
        )

    assert result["response"] == "DeepSeek response"


@patch("core.workload_router.get_cost_guard")
@patch("core.workload_router.get_rate_limiter")
@patch("core.workload_router.get_circuit_breaker_registry")
@pytest.mark.asyncio
async def test_execute_openrouter_gemini_success(mock_get_cb, mock_get_rate, mock_get_cost, router):
    """execute() con OPENROUTER_GEMINI debe llamar a OpenRouter chat."""
    mock_guard = MagicMock()
    mock_guard.check = AsyncMock(return_value={"status": "ok", "spent_today": 0.0})
    mock_get_cost.return_value = mock_guard

    mock_rate = AsyncMock()
    mock_rate.acquire = AsyncMock(return_value=True)
    mock_get_rate.return_value = mock_rate

    mock_or_client = AsyncMock()
    mock_or_client.chat = AsyncMock(return_value={
        "response": "Gemini response",
        "model": "google/gemini-2.5-flash",
        "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
        "cost_usd": 0.0001,
    })

    with patch("core.workload_router.get_openrouter", new=AsyncMock(return_value=mock_or_client)):
        mock_cb_registry = MagicMock()
        async def mock_call(name, func, *args, **kwargs):
            return await func(*args, **kwargs)
        mock_cb_registry.call = AsyncMock(side_effect=mock_call)
        mock_get_cb.return_value = mock_cb_registry

        result = await router.execute(
            trigger="rag_history_query",
            messages=[{"role": "user", "content": "query"}],
        )

    assert result["response"] == "Gemini response"


def test_is_business_hours_true(router):
    """_is_business_hours debe retornar True entre 7:40am y 6:00pm."""
    with patch("core.workload_router.datetime") as mock_dt:
        mock_dt.now.return_value.time.return_value = time(12, 0)
        assert router._is_business_hours() is True


def test_is_business_hours_false_before(router):
    """_is_business_hours debe retornar False antes de 7:40am."""
    with patch("core.workload_router.datetime") as mock_dt:
        mock_dt.now.return_value.time.return_value = time(6, 0)
        assert router._is_business_hours() is False


def test_is_business_hours_false_after(router):
    """_is_business_hours debe retornar False después de 6:00pm."""
    with patch("core.workload_router.datetime") as mock_dt:
        mock_dt.now.return_value.time.return_value = time(19, 0)
        assert router._is_business_hours() is False


def test_is_business_hours_boundary_start(router):
    """_is_business_hours debe retornar True exactamente a las 7:40am."""
    with patch("core.workload_router.datetime") as mock_dt:
        mock_dt.now.return_value.time.return_value = time(7, 40)
        assert router._is_business_hours() is True


def test_is_business_hours_boundary_end(router):
    """_is_business_hours debe retornar True exactamente a las 6:00pm."""
    with patch("core.workload_router.datetime") as mock_dt:
        mock_dt.now.return_value.time.return_value = time(18, 0)
        assert router._is_business_hours() is True


def test_get_provider_info_qwen(router):
    """_get_provider_info para QWEN_LOCAL debe retornar ollama."""
    provider, model, cost = router._get_provider_info(Route.QWEN_LOCAL)
    assert provider == "ollama"
    assert model == "qwen2.5:7b"
    assert cost == 0.0


def test_get_provider_info_fusion(router):
    """_get_provider_info para FUSION debe retornar openrouter con costo estimado."""
    provider, model, cost = router._get_provider_info(Route.FUSION)
    assert provider == "openrouter"
    assert model == "fusion"
    assert cost == 0.02


def test_get_provider_info_openrouter_glm(router):
    """_get_provider_info para OPENROUTER_GLM debe retornar modelo correcto."""
    provider, model, cost = router._get_provider_info(Route.OPENROUTER_GLM)
    assert provider == "openrouter"
    assert model == "z-ai/glm-4.5"
    assert cost == 0.0014


def test_get_provider_info_openrouter_claude(router):
    """_get_provider_info para OPENROUTER_CLAUDE debe retornar modelo correcto."""
    provider, model, cost = router._get_provider_info(Route.OPENROUTER_CLAUDE)
    assert provider == "openrouter"
    assert model == "anthropic/claude-sonnet-4.5"
    assert cost == 0.009


def test_get_provider_info_openrouter_deepseek(router):
    """_get_provider_info para OPENROUTER_DEEPSEEK debe retornar modelo correcto."""
    provider, model, cost = router._get_provider_info(Route.OPENROUTER_DEEPSEEK)
    assert provider == "openrouter"
    assert model == "deepseek/deepseek-chat-v3.2"
    assert cost == 0.00021


def test_get_provider_info_openrouter_gemini(router):
    """_get_provider_info para OPENROUTER_GEMINI debe retornar modelo correcto."""
    provider, model, cost = router._get_provider_info(Route.OPENROUTER_GEMINI)
    assert provider == "openrouter"
    assert model == "google/gemini-2.5-flash"
    assert cost == 0.0001125


@pytest.mark.asyncio
async def test_execute_qwen_local_fallback(router):
    """_execute_qwen_local debe ejecutar Qwen y retornar respuesta."""
    mock_qwen = MagicMock()
    mock_qwen.chat = AsyncMock(return_value={"response": "Direct Qwen", "model": "qwen2.5:7b"})

    with patch("core.workload_router.get_qwen", new=AsyncMock(return_value=mock_qwen)):
        result = await router._execute_qwen_local(
            messages=[{"role": "user", "content": "direct"}],
            temperature=0.5,
        )

    assert result["response"] == "Direct Qwen"
    mock_qwen.chat.assert_called_once_with(
        messages=[{"role": "user", "content": "direct"}], temperature=0.5
    )
