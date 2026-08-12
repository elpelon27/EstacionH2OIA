"""Tests para api/main.py.

NOTA: Estos tests son de la arquitectura anterior (WAHA + ValentinaAgent).
El sistema actual usa api/bridge.py (Meta Cloud API + Dify + FSM deterministico).
Los tests que referencian funciones eliminadas (_send_waha_message) estan marcados skip.
"""

from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """Fixture: cliente async para FastAPI.
    
    Import api.main here (not at module level) so Prometheus metrics
    are registered AFTER reset_prometheus fixture runs.
    """
    import importlib
    import sys
    if "api.main" in sys.modules:
        importlib.reload(sys.modules["api.main"])
    else:
        import api.main
    from api.main import app
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
    assert "hermes_messages_received_total" in resp.text or "valentina_messages_total" in resp.text


@pytest.mark.asyncio
async def test_webhook_whatsapp_no_hmac_in_dev(client):
    """En desarrollo (sin secret), webhook debe procesar sin HMAC.
    SKIP: _send_waha_message fue eliminado en migracion a Meta Cloud API."""
    pytest.skip("Arquitectura anterior: _send_waha_message eliminado, bridge.py usa Meta Graph API")


@pytest.mark.asyncio
async def test_webhook_whatsapp_missing_fields(client):
    """Webhook sin 'from' o 'body' debe retornar 400.
    SKIP: /webhook/whatsapp migrado a /webhook/meta en bridge.py."""
    pytest.skip("Ruta /webhook/whatsapp migrada a /webhook/meta en bridge.py")


@pytest.mark.asyncio
async def test_webhook_whatsapp_invalid_json(client):
    """JSON invalido debe retornar 400.
    SKIP: /webhook/whatsapp migrado a /webhook/meta en bridge.py."""
    pytest.skip("Ruta /webhook/whatsapp migrada a /webhook/meta en bridge.py")


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
