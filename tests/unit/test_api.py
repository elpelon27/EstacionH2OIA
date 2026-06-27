"""Tests para api/main.py."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from api.main import app


@pytest.fixture
async def client():
    """Fixture: cliente async para FastAPI."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_health(client):
    """GET /health debe retornar status ok."""
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "version" in data


@pytest.mark.asyncio
async def test_metrics(client):
    """GET /metrics debe retornar texto plano con métricas Prometheus."""
    resp = await client.get("/metrics")
    assert resp.status_code == 200
    assert "hermes_messages_received_total" in resp.text


@pytest.mark.asyncio
async def test_webhook_whatsapp_no_hmac_in_dev(client):
    """En desarrollo (sin secret), webhook debe procesar sin HMAC."""
    # Mock Valentina para no depender de Ollama

    mock_valentina = MagicMock()
    mock_valentina.process_message = AsyncMock(
        return_value={
            "response": "Hola",
            "needs_human_escalation": False,
            "memory_used": 0,
        }
    )

    with (
        patch("api.main.get_valentina", return_value=mock_valentina),
        patch("api.main._send_waha_message", new=AsyncMock()),
    ):
        resp = await client.post(
            "/webhook/whatsapp",
            json={
                "from": "584122560721@s.whatsapp.net",
                "body": "hola",
                "contact": {"name": "Luis"},
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["response_sent"] is True


@pytest.mark.asyncio
async def test_webhook_whatsapp_missing_fields(client):
    """Webhook sin 'from' o 'body' debe retornar 400."""
    resp = await client.post(
        "/webhook/whatsapp",
        json={"from": "", "body": ""},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_webhook_whatsapp_invalid_json(client):
    """JSON inválido debe retornar 400."""
    resp = await client.post(
        "/webhook/whatsapp",
        content="invalid json",
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_kill_switch_via_api(client):
    """POST /kill-switch debe activar/desactivar."""
    # Activar
    resp = await client.post("/kill-switch", json={"action": "kill"})
    assert resp.status_code == 200
    assert resp.json()["kill_switch"] is True

    # Desactivar
    resp = await client.post("/kill-switch", json={"action": "revive"})
    assert resp.status_code == 200
    assert resp.json()["kill_switch"] is False


@pytest.mark.asyncio
async def test_kill_switch_invalid_action(client):
    """Action inválido debe retornar 400."""
    resp = await client.post("/kill-switch", json={"action": "invalid"})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_send_message_missing_fields(client):
    """send-message sin phone o message debe retornar 400."""
    resp = await client.post("/send-message", json={"phone": "", "message": ""})
    assert resp.status_code == 400
