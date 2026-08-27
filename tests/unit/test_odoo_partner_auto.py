"""
Tests unitarios para get_or_create_partner y OdooClient auto-registro.

Mockea OdooClient para no tocar red ni Odoo real.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure project root in path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.integrations.odoo.odoo_sync import (  # noqa: E402
    OdooClient,
    get_or_create_partner,
    reset_odoo_client,
)

# ─── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset_singleton():
    """Reset Odoo singleton between tests."""
    reset_odoo_client()
    yield
    reset_odoo_client()


@pytest.fixture
def mock_odoo_client():
    """Crea un OdooClient mockeado que simula conexión exitosa."""
    client = MagicMock(spec=OdooClient)
    client.connected = True
    client._ensure_connected = MagicMock()
    client.execute_kw = MagicMock()
    return client


# ─── Tests: OdooClient.search_partner_by_phone ─────────────────────────


class TestSearchPartnerByPhone:
    """Test del método search_partner_by_phone."""

    def test_found_by_phone(self, mock_odoo_client):
        """Si encuentra por phone, retorna ID."""
        mock_odoo_client.execute_kw.return_value = [
            {"id": 42, "name": "Juan Pérez", "phone": "+584123334422"}
        ]
        # Replace __class__ to use real method
        real_client = OdooClient.__new__(OdooClient)
        real_client._models = mock_odoo_client
        real_client._uid = 1
        real_client.config = MagicMock()
        real_client.config.db = "test"
        real_client.config.password = "test"
        real_client._models = mock_odoo_client

        result = OdooClient.search_partner_by_phone(real_client, "+584123334422")
        assert result == 42

    def test_not_found(self, mock_odoo_client):
        """Si no encuentra, retorna None."""
        mock_odoo_client.execute_kw.return_value = []
        real_client = OdooClient.__new__(OdooClient)
        real_client._models = mock_odoo_client
        real_client._uid = 1
        real_client.config = MagicMock()
        real_client.config.db = "test"
        real_client.config.password = "test"

        result = OdooClient.search_partner_by_phone(real_client, "+584999999999")
        assert result is None

    def test_empty_phone(self, mock_odoo_client):
        """Telefono vacío retorna None sin llamar a Odoo."""
        real_client = OdooClient.__new__(OdooClient)
        real_client._models = mock_odoo_client
        real_client._uid = 1
        real_client.config = MagicMock()
        real_client.config.db = "test"
        real_client.config.password = "test"

        result = OdooClient.search_partner_by_phone(real_client, "")
        assert result is None
        mock_odoo_client.execute_kw.assert_not_called()


# ─── Tests: OdooClient.get_or_create_partner_by_phone ──────────────────


class TestGetOrCreatePartnerByPhone:
    """Test del método get_or_create_partner_by_phone."""

    def test_existing_partner_returns_id(self):
        """Si el partner ya existe, retorna su ID sin crear nuevo."""
        client = OdooClient.__new__(OdooClient)
        client.search_partner_by_phone = MagicMock(return_value=99)
        client.create_partner_from_whatsapp = MagicMock(return_value=77)

        result = client.get_or_create_partner_by_phone("+584123334422", "Maria")
        assert result == 99
        client.create_partner_from_whatsapp.assert_not_called()

    def test_new_partner_creates_and_returns_id(self):
        """Si no existe, crea nuevo partner y retorna ID."""
        client = OdooClient.__new__(OdooClient)
        client.search_partner_by_phone = MagicMock(return_value=None)
        client.create_partner_from_whatsapp = MagicMock(return_value=55)

        result = client.get_or_create_partner_by_phone("+584123334422", "Pedro Nuevo")
        assert result == 55
        client.create_partner_from_whatsapp.assert_called_once_with(
            "Pedro Nuevo", "+584123334422"
        )

    def test_odoo_error_returns_none(self):
        """Si Odoo lanza excepción, retorna None (fail-soft)."""
        client = OdooClient.__new__(OdooClient)
        client.search_partner_by_phone = MagicMock(
            side_effect=ConnectionError("Odoo down")
        )

        result = client.get_or_create_partner_by_phone("+584123334422", "Pedro")
        assert result is None


# ─── Tests: get_or_create_partner (función módulo) ─────────────────────


class TestGetOrCreatePartnerModule:
    """Test de la función módulo get_or_create_partner."""

    def test_odoo_unavailable_returns_none(self):
        """Si Odoo no está disponible, retorna None sin explotar."""
        with patch(
            "src.integrations.odoo.odoo_sync.get_odoo_client",
            side_effect=RuntimeError("No se pudo conectar a Odoo"),
        ):
            result = get_or_create_partner("+584123334422", "Test Client")
            assert result is None

    def test_partner_found_returns_id(self):
        """Si Odoo disponible y partner existe, retorna ID."""
        mock_client = MagicMock(spec=OdooClient)
        mock_client.get_or_create_partner_by_phone.return_value = 77
        with patch(
            "src.integrations.odoo.odoo_sync.get_odoo_client",
            return_value=mock_client,
        ):
            result = get_or_create_partner("+584123334422", "Juan")
            assert result == 77

    def test_partner_created_returns_id(self):
        """Si Odoo disponible y partner nuevo, retorna ID del creado."""
        mock_client = MagicMock(spec=OdooClient)
        mock_client.get_or_create_partner_by_phone.return_value = 88
        with patch(
            "src.integrations.odoo.odoo_sync.get_odoo_client",
            return_value=mock_client,
        ):
            result = get_or_create_partner("+584123334422", "Nuevo Cliente")
            assert result == 88

    def test_unexpected_error_returns_none(self):
        """Cualquier error inesperado retorna None (fail-soft)."""
        mock_client = MagicMock(spec=OdooClient)
        mock_client.get_or_create_partner_by_phone.side_effect = Exception("Unexpected")
        with patch(
            "src.integrations.odoo.odoo_sync.get_odoo_client",
            return_value=mock_client,
        ):
            result = get_or_create_partner("+584123334422", "Test")
            assert result is None

    def test_empty_name_uses_phone(self):
        """Si name es vacío, lo pasa al cliente que usa phone como nombre."""
        mock_client = MagicMock(spec=OdooClient)
        mock_client.get_or_create_partner_by_phone.return_value = 99
        with patch(
            "src.integrations.odoo.odoo_sync.get_odoo_client",
            return_value=mock_client,
        ):
            result = get_or_create_partner("+584123334422", "")
            assert result == 99
            # Verificar que se llamó con phone y name vacío
            mock_client.get_or_create_partner_by_phone.assert_called_once_with(
                "+584123334422", ""
            )
