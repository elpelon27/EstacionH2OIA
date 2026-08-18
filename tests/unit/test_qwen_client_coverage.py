"""Tests unitarios para cubrir las lineas sin cobertura de core/qwen_client.py.

Cubre:
- chat() con httpx.HTTPStatusError (lineas 106-108)
- chat() con Exception generica (lineas 109-111)
- close() (linea 126)
- get_qwen() helper (linea 131)
- list_models() con respuesta vacia
"""

import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.qwen_client import QwenClient, get_qwen


@pytest.fixture
def client():
    """Fixture: instancia fresca de QwenClient con singleton reseteado."""
    QwenClient._instance = None
    c = QwenClient.get_instance()
    yield c
    QwenClient._instance = None


class TestChatErrorPaths:
    @pytest.mark.asyncio
    async def test_http_status_error(self, client):
        """chat() con HTTPStatusError → re-raise (lineas 106-108)."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        error = httpx.HTTPStatusError(
            "Server error", request=MagicMock(), response=mock_response
        )

        with (
            patch.object(client.client, "post", new=AsyncMock(side_effect=error)),
            pytest.raises(httpx.HTTPStatusError),
        ):
            await client.chat(messages=[{"role": "user", "content": "test"}])

    @pytest.mark.asyncio
    async def test_generic_exception(self, client):
        """chat() con Exception generica → re-raise (lineas 109-111)."""
        with (
            patch.object(client.client, "post", new=AsyncMock(side_effect=ValueError("bad data"))),
            pytest.raises(ValueError, match="bad data"),
        ):
            await client.chat(messages=[{"role": "user", "content": "test"}])

    @pytest.mark.asyncio
    async def test_timeout_exception(self, client):
        """chat() con httpx.TimeoutException → re-raise via except Exception."""
        with (
            patch.object(client.client, "post", new=AsyncMock(side_effect=httpx.TimeoutException("timeout"))),
            pytest.raises(httpx.TimeoutException),
        ):
            await client.chat(messages=[{"role": "user", "content": "test"}])


class TestClose:
    @pytest.mark.asyncio
    async def test_close(self, client):
        """close() debe llamar aclose() (linea 126)."""
        with patch.object(client.client, "aclose", new=AsyncMock()) as mock_aclose:
            await client.close()
            mock_aclose.assert_awaited_once()


class TestGetQwen:
    @pytest.mark.asyncio
    async def test_get_qwen_returns_instance(self):
        """get_qwen() helper debe retornar instancia de QwenClient (linea 131)."""
        QwenClient._instance = None
        result = await get_qwen()
        assert isinstance(result, QwenClient)
        QwenClient._instance = None


class TestListModelsEdgeCases:
    @pytest.mark.asyncio
    async def test_empty_models(self, client):
        """list_models con models vacio → []."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"models": []}
        mock_response.raise_for_status = MagicMock()

        with patch.object(client.client, "get", new=AsyncMock(return_value=mock_response)):
            models = await client.list_models()

        assert models == []

    @pytest.mark.asyncio
    async def test_no_models_key(self, client):
        """list_models sin key 'models' → []."""
        mock_response = MagicMock()
        mock_response.json.return_value = {}
        mock_response.raise_for_status = MagicMock()

        with patch.object(client.client, "get", new=AsyncMock(return_value=mock_response)):
            models = await client.list_models()

        assert models == []
