"""Tests unitarios para core/meta_client.py — MetaWhatsAppClient.

Cubre:
- send_text_message  (éxito / error status / excepción / reply_to)
- send_template_message (éxito / error status / excepción)
- get_instance (singleton)
- close()
- get_meta_client() helper async

Todo el I/O de red se mockea: httpx.AsyncClient.post se sustituye por AsyncMock.
No se usan credenciales reales — los valores vienen de conftest.py (test-token).
"""

# Asegurar que la raíz del proyecto está en sys.path
import os
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.meta_client import MetaWhatsAppClient, get_meta_client

# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture(autouse=True)
def _reset_singleton():
    """Resetea el singleton entre tests para evitar contaminación de estado."""
    MetaWhatsAppClient._instance = None
    yield
    MetaWhatsAppClient._instance = None


def _make_client_with_mock_http():
    """Crea una instancia de MetaWhatsAppClient con http_client mockeado."""
    client = MetaWhatsAppClient()
    client.http_client = AsyncMock()
    return client


def _mock_response(status_code: int, json_data: dict | None = None):
    """Construye una respuesta mock de httpx."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    return resp


# ============================================================================
# Singleton — get_instance
# ============================================================================

class TestSingleton:
    def test_get_instance_returns_instance(self):
        client = MetaWhatsAppClient.get_instance()
        assert isinstance(client, MetaWhatsAppClient)

    def test_get_instance_returns_same_instance(self):
        c1 = MetaWhatsAppClient.get_instance()
        c2 = MetaWhatsAppClient.get_instance()
        assert c1 is c2

    def test_get_instance_creates_only_once(self):
        c1 = MetaWhatsAppClient.get_instance()
        # Si llamamos de nuevo, no debe crear una nueva instancia
        c2 = MetaWhatsAppClient.get_instance()
        assert c1 is c2
        # Los atributos deben coincidir
        assert c1.base_url == c2.base_url
        assert c1.headers == c2.headers


# ============================================================================
# send_text_message
# ============================================================================

class TestSendTextMessage:
    @pytest.mark.asyncio
    async def test_success(self):
        client = _make_client_with_mock_http()
        client.http_client.post.return_value = _mock_response(
            200,
            {"messages": [{"id": "wamid.HBG...123"}]},
        )

        result = await client.send_text_message("584122560721", "Hola mundo")

        assert result["success"] is True
        assert result["message_id"] == "wamid.HBG...123"
        assert result["error"] is None

        # Verificar que se llamó con el payload correcto
        client.http_client.post.assert_awaited_once()
        call_kwargs = client.http_client.post.call_args
        assert call_kwargs.kwargs["json"]["messaging_product"] == "whatsapp"
        assert call_kwargs.kwargs["json"]["to"] == "584122560721"
        assert call_kwargs.kwargs["json"]["type"] == "text"
        assert call_kwargs.kwargs["json"]["text"]["body"] == "Hola mundo"

    @pytest.mark.asyncio
    async def test_success_with_reply_to(self):
        client = _make_client_with_mock_http()
        client.http_client.post.return_value = _mock_response(
            200,
            {"messages": [{"id": "wamid.REPLY456"}]},
        )

        result = await client.send_text_message(
            "584122560721", "Respuesta", reply_to_message_id="msg_123"
        )

        assert result["success"] is True
        assert result["message_id"] == "wamid.REPLY456"

        call_kwargs = client.http_client.post.call_args
        assert call_kwargs.kwargs["json"]["context"] == {"message_id": "msg_123"}

    @pytest.mark.asyncio
    async def test_cleans_phone_number(self):
        """El número se limpia de sufijos @c.us, @s.whatsapp.net, @lid."""
        client = _make_client_with_mock_http()
        client.http_client.post.return_value = _mock_response(
            200, {"messages": [{"id": "wamid.CLEAN"}]}
        )

        await client.send_text_message("584122560721@c.us", "test")

        call_kwargs = client.http_client.post.call_args
        assert call_kwargs.kwargs["json"]["to"] == "584122560721"

    @pytest.mark.asyncio
    async def test_cleans_phone_s_whatsapp_net(self):
        client = _make_client_with_mock_http()
        client.http_client.post.return_value = _mock_response(
            200, {"messages": [{"id": "wamid.CLEAN2"}]}
        )

        await client.send_text_message("584122560721@s.whatsapp.net", "test")

        call_kwargs = client.http_client.post.call_args
        assert call_kwargs.kwargs["json"]["to"] == "584122560721"

    @pytest.mark.asyncio
    async def test_cleans_phone_lid(self):
        client = _make_client_with_mock_http()
        client.http_client.post.return_value = _mock_response(
            200, {"messages": [{"id": "wamid.CLEAN3"}]}
        )

        await client.send_text_message("584122560721@lid", "test")

        call_kwargs = client.http_client.post.call_args
        assert call_kwargs.kwargs["json"]["to"] == "584122560721"

    @pytest.mark.asyncio
    async def test_error_status(self):
        """Status != 200 → success=False con mensaje de error."""
        client = _make_client_with_mock_http()
        client.http_client.post.return_value = _mock_response(
            401,
            {"error": {"message": "Invalid OAuth access token"}},
        )

        result = await client.send_text_message("584122560721", "test")

        assert result["success"] is False
        assert result["message_id"] is None
        assert result["error"] == "Invalid OAuth access token"

    @pytest.mark.asyncio
    async def test_error_status_unknown_error(self):
        """Error sin campo error.message → 'Unknown error'."""
        client = _make_client_with_mock_http()
        client.http_client.post.return_value = _mock_response(500, {})

        result = await client.send_text_message("584122560721", "test")

        assert result["success"] is False
        assert result["error"] == "Unknown error"

    @pytest.mark.asyncio
    async def test_exception(self):
        """Excepción de red → success=False con str(e)."""
        client = _make_client_with_mock_http()
        client.http_client.post.side_effect = httpx_error("Connection refused")

        result = await client.send_text_message("584122560721", "test")

        assert result["success"] is False
        assert result["message_id"] is None
        assert "Connection refused" in result["error"]

    @pytest.mark.asyncio
    async def test_empty_messages_list_hits_exception_path(self):
        """Respuesta 200 pero messages=[] → IndexError capturado → success=False."""
        client = _make_client_with_mock_http()
        client.http_client.post.return_value = _mock_response(200, {"messages": []})

        result = await client.send_text_message("584122560721", "test")

        # data.get("messages", [{}])[0] raises IndexError → except block
        assert result["success"] is False
        assert "index" in result["error"].lower()


# ============================================================================
# send_template_message
# ============================================================================

class TestSendTemplateMessage:
    @pytest.mark.asyncio
    async def test_success(self):
        client = _make_client_with_mock_http()
        client.http_client.post.return_value = _mock_response(
            200, {"messages": [{"id": "wamid.TPL123"}]}
        )

        result = await client.send_template_message("584122560721", "welcome_tpl")

        assert result["success"] is True
        assert result["message_id"] == "wamid.TPL123"
        assert result["error"] is None

        call_kwargs = client.http_client.post.call_args
        assert call_kwargs.kwargs["json"]["type"] == "template"
        assert call_kwargs.kwargs["json"]["template"]["name"] == "welcome_tpl"
        assert call_kwargs.kwargs["json"]["template"]["language"]["code"] == "es"

    @pytest.mark.asyncio
    async def test_success_custom_language(self):
        client = _make_client_with_mock_http()
        client.http_client.post.return_value = _mock_response(
            200, {"messages": [{"id": "wamid.TPL_EN"}]}
        )

        result = await client.send_template_message(
            "584122560721", "welcome_en", language_code="en_US"
        )

        assert result["success"] is True
        call_kwargs = client.http_client.post.call_args
        assert call_kwargs.kwargs["json"]["template"]["language"]["code"] == "en_US"

    @pytest.mark.asyncio
    async def test_cleans_phone(self):
        client = _make_client_with_mock_http()
        client.http_client.post.return_value = _mock_response(
            200, {"messages": [{"id": "wamid.TPL"}]}
        )

        await client.send_template_message("584122560721@c.us", "welcome_tpl")

        call_kwargs = client.http_client.post.call_args
        assert call_kwargs.kwargs["json"]["to"] == "584122560721"

    @pytest.mark.asyncio
    async def test_error_status(self):
        client = _make_client_with_mock_http()
        client.http_client.post.return_value = _mock_response(
            400, {"error": {"message": "Template not found"}}
        )

        result = await client.send_template_message("584122560721", "nonexistent_tpl")

        assert result["success"] is False
        assert result["message_id"] is None
        assert result["error"] == "Template not found"

    @pytest.mark.asyncio
    async def test_error_unknown_error(self):
        client = _make_client_with_mock_http()
        client.http_client.post.return_value = _mock_response(500, {})

        result = await client.send_template_message("584122560721", "tpl")

        assert result["success"] is False
        assert result["error"] == "Unknown error"

    @pytest.mark.asyncio
    async def test_exception(self):
        client = _make_client_with_mock_http()
        client.http_client.post.side_effect = httpx_error("Timeout")

        result = await client.send_template_message("584122560721", "tpl")

        assert result["success"] is False
        assert result["message_id"] is None
        assert "Timeout" in result["error"]


# ============================================================================
# close()
# ============================================================================

class TestClose:
    @pytest.mark.asyncio
    async def test_close_calls_aclose(self):
        client = _make_client_with_mock_http()
        client.http_client.aclose = AsyncMock()

        await client.close()

        client.http_client.aclose.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_close_on_real_client(self):
        """close() en un cliente con httpx real no debe lanzar."""
        client = MetaWhatsAppClient()
        # Reemplazar el cliente real por un mock para no abrir conexiones
        client.http_client = AsyncMock()
        client.http_client.aclose = AsyncMock()

        await client.close()
        client.http_client.aclose.assert_awaited_once()


# ============================================================================
# get_meta_client() helper
# ============================================================================

class TestGetMetaClient:
    @pytest.mark.asyncio
    async def test_returns_instance(self):
        client = await get_meta_client()
        assert isinstance(client, MetaWhatsAppClient)

    @pytest.mark.asyncio
    async def test_returns_singleton(self):
        c1 = await get_meta_client()
        c2 = await get_meta_client()
        assert c1 is c2


# ============================================================================
# Constructor — atributos básicos
# ============================================================================

class TestConstructor:
    def test_attributes_set(self):
        client = MetaWhatsAppClient()

        assert client.access_token is not None
        assert client.phone_number_id is not None
        assert client.api_version is not None
        assert "graph.facebook.com" in client.base_url
        assert "Authorization" in client.headers
        assert "Content-Type" in client.headers
        assert client.http_client is not None

    def test_base_url_contains_phone_number_id(self):
        client = MetaWhatsAppClient()
        assert client.phone_number_id in client.base_url


# ============================================================================
# Helper
# ============================================================================

def httpx_error(msg: str) -> Exception:
    """Crea una excepción simulando un error de httpx."""
    return Exception(msg)
