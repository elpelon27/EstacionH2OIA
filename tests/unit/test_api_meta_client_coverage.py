"""Tests unitarios para api/meta_client.py — MetaClient.

Cubre: set_http_client, get_http_client, MetaClient (__init__, _verify_signature,
_base_url, _headers, _assert_configured, send_text, send_interactive), get_meta_client.

Todo el I/O de red se mockea via httpx.AsyncClient mock.
No se usan credenciales reales — conftest.py ya define META_* env vars.
"""

import hashlib
import hmac
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Pre-register api.bridge mock so `from api.bridge import _phone_hash` works
# without importing the full bridge module (which has many deps).
_mock_bridge = MagicMock()
_mock_bridge._phone_hash = lambda phone: "hashed" + phone[:4]
sys.modules.setdefault("api.bridge", _mock_bridge)

from api.meta_client import MetaClient, get_meta_client, get_http_client, set_http_client


@pytest.fixture(autouse=True)
def _reset_state():
    """Reset singleton y http_client entre tests."""
    import api.meta_client as mc_mod
    old_http = mc_mod._http_client
    old_client = mc_mod._meta_client
    mc_mod._http_client = None
    mc_mod._meta_client = None
    yield
    mc_mod._http_client = old_http
    mc_mod._meta_client = old_client


# ============================================================================
# set_http_client / get_http_client
# ============================================================================

class TestHttpClient:
    def test_set_and_get(self):
        mock_client = MagicMock(spec=httpx.AsyncClient)
        set_http_client(mock_client)
        assert get_http_client() is mock_client

    def test_get_without_set_raises(self):
        with pytest.raises(RuntimeError, match="not initialized"):
            get_http_client()

    def test_set_overwrites(self):
        c1 = MagicMock(spec=httpx.AsyncClient)
        c2 = MagicMock(spec=httpx.AsyncClient)
        set_http_client(c1)
        set_http_client(c2)
        assert get_http_client() is c2


# ============================================================================
# MetaClient __init__
# ============================================================================

class TestMetaClientInit:
    def test_init_loads_settings(self):
        client = MetaClient()
        assert client.access_token is not None
        assert client.phone_number_id is not None
        assert client.app_secret is not None
        assert client.api_version is not None

    def test_base_url(self):
        client = MetaClient()
        url = client._base_url
        assert "graph.facebook.com" in url
        assert "messages" in url
        assert client.phone_number_id in url

    def test_headers(self):
        client = MetaClient()
        headers = client._headers
        assert headers["Authorization"].startswith("Bearer ")
        assert headers["Content-Type"] == "application/json"

    def test_assert_configured_true(self):
        client = MetaClient()
        assert client._assert_configured() is True

    def test_assert_configured_false_no_token(self):
        client = MetaClient()
        client.access_token = ""
        assert client._assert_configured() is False

    def test_assert_configured_false_no_phone(self):
        client = MetaClient()
        client.phone_number_id = ""
        assert client._assert_configured() is False


# ============================================================================
# _verify_signature
# ============================================================================

class TestVerifySignature:
    def test_valid_signature(self):
        client = MetaClient()
        body = b'{"test": "data"}'
        expected_sig = "sha256=" + hmac.new(
            client.app_secret.encode(), body, hashlib.sha256
        ).hexdigest()
        assert client._verify_signature(body, expected_sig) is True

    def test_invalid_signature(self):
        client = MetaClient()
        assert client._verify_signature(b'{"data": 1}', "sha256=invalid") is False

    def test_no_app_secret(self):
        client = MetaClient()
        client.app_secret = ""
        assert client._verify_signature(b'data', "sha256=sig") is False

    def test_no_signature_header(self):
        client = MetaClient()
        assert client._verify_signature(b'data', "") is False

    def test_empty_body(self):
        client = MetaClient()
        body = b''
        expected_sig = "sha256=" + hmac.new(
            client.app_secret.encode(), body, hashlib.sha256
        ).hexdigest()
        assert client._verify_signature(body, expected_sig) is True


# ============================================================================
# send_text
# ============================================================================

def _mock_response(status_code: int, text: str = "ok"):
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    return resp


class TestSendText:
    @pytest.mark.asyncio
    async def test_success(self):
        client = MetaClient()
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_http.post.return_value = _mock_response(200)
        set_http_client(mock_http)

        result = await client.send_text("584121234567", "hello")

        assert result is True
        mock_http.post.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_not_configured(self):
        client = MetaClient()
        client.access_token = ""

        result = await client.send_text("584121234567", "hello")

        assert result is False

    @pytest.mark.asyncio
    async def test_api_error_status(self):
        client = MetaClient()
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_http.post.return_value = _mock_response(500, "Internal error")
        set_http_client(mock_http)

        result = await client.send_text("584121234567", "hello")

        assert result is False

    @pytest.mark.asyncio
    async def test_http_error_exception(self):
        client = MetaClient()
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_http.post.side_effect = httpx.HTTPError("connection refused")
        set_http_client(mock_http)

        result = await client.send_text("584121234567", "hello")

        assert result is False

    @pytest.mark.asyncio
    async def test_no_http_client_raises(self):
        """send_text sin http_client registrado → RuntimeError desde get_http_client."""
        client = MetaClient()
        # _http_client is None (from fixture), so get_http_client raises RuntimeError
        # which is NOT httpx.HTTPError, so it propagates
        with pytest.raises(RuntimeError, match="not initialized"):
            await client.send_text("584121234567", "hello")


# ============================================================================
# send_interactive
# ============================================================================

class TestSendInteractive:
    @pytest.mark.asyncio
    async def test_button_success(self):
        client = MetaClient()
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_http.post.return_value = _mock_response(200)
        set_http_client(mock_http)

        result = await client.send_interactive(
            phone="584121234567",
            body_text="Choose an option",
            interactive_type="button",
            buttons=[{"id": "btn1", "title": "Option 1"}],
            header_text="Header",
            footer_text="Footer",
        )

        assert result is True
        # Verify payload structure
        call_kwargs = mock_http.post.call_args
        payload = call_kwargs.kwargs["json"]
        assert payload["type"] == "interactive"
        assert payload["interactive"]["type"] == "button"
        assert payload["interactive"]["header"]["text"] == "Header"[:60]
        assert payload["interactive"]["footer"]["text"] == "Footer"[:60]

    @pytest.mark.asyncio
    async def test_list_success(self):
        client = MetaClient()
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_http.post.return_value = _mock_response(200)
        set_http_client(mock_http)

        sections = [{"title": "Section 1", "rows": [{"id": "r1", "title": "Row 1"}]}]
        result = await client.send_interactive(
            phone="584121234567",
            body_text="Select item",
            interactive_type="list",
            list_sections=sections,
            button_text="Ver opciones",
        )

        assert result is True
        call_kwargs = mock_http.post.call_args
        payload = call_kwargs.kwargs["json"]
        assert payload["interactive"]["action"]["button"] == "Ver opciones"[:20]
        assert payload["interactive"]["action"]["sections"] == sections

    @pytest.mark.asyncio
    async def test_unsupported_type(self):
        client = MetaClient()
        result = await client.send_interactive(
            phone="584121234567",
            body_text="test",
            interactive_type="unsupported_type",
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_not_configured(self):
        client = MetaClient()
        client.access_token = ""
        result = await client.send_interactive("584121234567", "test", "button")
        assert result is False

    @pytest.mark.asyncio
    async def test_api_error(self):
        client = MetaClient()
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_http.post.return_value = _mock_response(400, "Bad request")
        set_http_client(mock_http)

        result = await client.send_interactive(
            "584121234567", "test", "button", buttons=[{"id": "b1", "title": "B1"}]
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_http_error(self):
        client = MetaClient()
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_http.post.side_effect = httpx.HTTPError("timeout")
        set_http_client(mock_http)

        result = await client.send_interactive(
            "584121234567", "test", "button", buttons=[{"id": "b1", "title": "B1"}]
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_no_header_no_footer(self):
        """send_interactive sin header/footer → payload sin esas claves."""
        client = MetaClient()
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_http.post.return_value = _mock_response(200)
        set_http_client(mock_http)

        result = await client.send_interactive(
            "584121234567", "test", "button",
            buttons=[{"id": "b1", "title": "B1"}],
        )
        assert result is True
        payload = mock_http.post.call_args.kwargs["json"]
        assert "header" not in payload["interactive"]
        assert "footer" not in payload["interactive"]

    @pytest.mark.asyncio
    async def test_button_truncation(self):
        """Los títulos de botones se truncan a 20 chars."""
        client = MetaClient()
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_http.post.return_value = _mock_response(200)
        set_http_client(mock_http)

        long_title = "A" * 50
        await client.send_interactive(
            "584121234567", "test", "button",
            buttons=[{"id": "b1", "title": long_title}],
        )
        payload = mock_http.post.call_args.kwargs["json"]
        btn = payload["interactive"]["action"]["buttons"][0]
        assert len(btn["reply"]["title"]) <= 20

    @pytest.mark.asyncio
    async def test_list_no_sections(self):
        """list sin sections → sections=[] en payload."""
        client = MetaClient()
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_http.post.return_value = _mock_response(200)
        set_http_client(mock_http)

        await client.send_interactive("584121234567", "test", "list")
        payload = mock_http.post.call_args.kwargs["json"]
        assert payload["interactive"]["action"]["sections"] == []


# ============================================================================
# get_meta_client singleton
# ============================================================================

class TestGetMetaClient:
    def test_returns_instance(self):
        client = get_meta_client()
        assert isinstance(client, MetaClient)

    def test_singleton(self):
        c1 = get_meta_client()
        c2 = get_meta_client()
        assert c1 is c2
