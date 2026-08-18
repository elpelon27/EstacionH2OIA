"""Tests unitarios para src/financial/currency.py.

Cubre:
- get_eur_ves_rate (3 prioridades: open.er-api, frankfurter, BD)
- _try_open_er_api (exito, error http, excepcion)
- _try_frankfurter (exito, error http, excepcion)
- set_manual_rate
- convert_eur_to_ves (con tasa, sin tasa, tasa cero)
- convert_ves_to_eur (con tasa, sin tasa, tasa cero)
- get_tasa_display (con tasa, sin tasa)
"""

import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.financial.currency import (
    convert_eur_to_ves,
    convert_ves_to_eur,
    get_eur_ves_rate,
    get_tasa_display,
    set_manual_rate,
    _try_frankfurter,
    _try_open_er_api,
)


class TestTryOpenErApi:
    @pytest.mark.asyncio
    async def test_success_with_ves_and_usd(self):
        """200 OK con VES y USD -> retorna float VES."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"rates": {"VES": 45.50, "USD": 1.08}}

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with patch("src.financial.currency.httpx.AsyncClient", return_value=mock_client):
            with patch("src.financial.currency.db.save_tasa"):
                result = await _try_open_er_api()

        assert result == 45.50

    @pytest.mark.asyncio
    async def test_success_no_ves(self):
        """200 OK pero sin VES -> retorna None."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"rates": {"USD": 1.08}}

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with patch("src.financial.currency.httpx.AsyncClient", return_value=mock_client):
            result = await _try_open_er_api()

        assert result is None

    @pytest.mark.asyncio
    async def test_http_error(self):
        """status != 200 -> retorna None."""
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.json.return_value = {}

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with patch("src.financial.currency.httpx.AsyncClient", return_value=mock_client):
            result = await _try_open_er_api()

        assert result is None

    @pytest.mark.asyncio
    async def test_exception_returns_none(self):
        """Excepcion de red -> retorna None."""
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(side_effect=Exception("connection refused"))
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("src.financial.currency.httpx.AsyncClient", return_value=mock_client):
            result = await _try_open_er_api()

        assert result is None


class TestTryFrankfurter:
    @pytest.mark.asyncio
    async def test_success(self):
        """200 OK con USD -> retorna float."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"rates": {"USD": 1.085}}

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with patch("src.financial.currency.httpx.AsyncClient", return_value=mock_client):
            result = await _try_frankfurter()

        assert result == 1.085

    @pytest.mark.asyncio
    async def test_no_usd(self):
        """200 OK sin USD -> retorna None."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"rates": {}}

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with patch("src.financial.currency.httpx.AsyncClient", return_value=mock_client):
            result = await _try_frankfurter()

        assert result is None

    @pytest.mark.asyncio
    async def test_exception_returns_none(self):
        """Excepcion -> retorna None."""
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(side_effect=Exception("timeout"))
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("src.financial.currency.httpx.AsyncClient", return_value=mock_client):
            result = await _try_frankfurter()

        assert result is None


class TestGetEurVesRate:
    @pytest.mark.asyncio
    async def test_priority1_open_er_api(self):
        """Si open.er-api devuelve tasa, la usa y no consulta frankfurter."""
        with patch("src.financial.currency._try_open_er_api", new_callable=AsyncMock) as mock_api:
            mock_api.return_value = 45.50
            with patch("src.financial.currency.db.save_tasa") as mock_save:
                result = await get_eur_ves_rate()

        assert result == 45.50
        mock_save.assert_called_once_with("EUR/VES", 45.50, "open_er_api", "open.er-api.com")

    @pytest.mark.asyncio
    async def test_priority3_last_saved(self):
        """Si API falla y no hay frankfurter, usa ultima de BD."""
        mock_last = MagicMock()
        mock_last.tasa = 42.00
        mock_last.fuente = "manual"

        with patch("src.financial.currency._try_open_er_api", new_callable=AsyncMock) as mock_api:
            mock_api.return_value = None
            with patch("src.financial.currency._try_frankfurter", new_callable=AsyncMock) as mock_f:
                mock_f.return_value = None
                with patch("src.financial.currency.db.get_last_tasa", return_value=mock_last):
                    with patch("src.financial.currency.db.save_tasa"):
                        result = await get_eur_ves_rate()

        assert result == 42.00

    @pytest.mark.asyncio
    async def test_all_fail_returns_none(self):
        """Todas las fuentes fallan -> None."""
        with patch("src.financial.currency._try_open_er_api", new_callable=AsyncMock) as mock_api:
            mock_api.return_value = None
            with patch("src.financial.currency._try_frankfurter", new_callable=AsyncMock) as mock_f:
                mock_f.return_value = None
                with patch("src.financial.currency.db.get_last_tasa", return_value=None):
                    result = await get_eur_ves_rate()

        assert result is None


class TestConvertEurToVes:
    def test_with_explicit_rate(self):
        assert convert_eur_to_ves(10.0, tasa=45.0) == 450.0

    def test_with_zero_rate_uses_db(self):
        mock_last = MagicMock()
        mock_last.tasa = 40.0
        with patch("src.financial.currency.db.get_last_tasa", return_value=mock_last):
            assert convert_eur_to_ves(10.0, tasa=0) == 400.0

    def test_no_rate_uses_db(self):
        mock_last = MagicMock()
        mock_last.tasa = 50.0
        with patch("src.financial.currency.db.get_last_tasa", return_value=mock_last):
            assert convert_eur_to_ves(5.0) == 250.0

    def test_no_rate_no_db_returns_zero(self):
        with patch("src.financial.currency.db.get_last_tasa", return_value=None):
            assert convert_eur_to_ves(100.0) == 0.0


class TestConvertVesToEur:
    def test_with_explicit_rate(self):
        assert convert_ves_to_eur(450.0, tasa=45.0) == 10.0

    def test_with_zero_rate_uses_db(self):
        mock_last = MagicMock()
        mock_last.tasa = 40.0
        with patch("src.financial.currency.db.get_last_tasa", return_value=mock_last):
            assert convert_ves_to_eur(400.0, tasa=0) == 10.0

    def test_no_rate_no_db_returns_ves(self):
        """Sin tasa y sin BD, tasa default=1 -> retorna el monto tal cual."""
        with patch("src.financial.currency.db.get_last_tasa", return_value=None):
            assert convert_ves_to_eur(100.0) == 100.0


class TestSetManualRate:
    def test_saves_and_returns(self):
        with patch("src.financial.currency.db.save_tasa") as mock_save:
            result = set_manual_rate(43.50, "EUR/VES")
        assert result == 43.50
        mock_save.assert_called_once_with(
            "EUR/VES", 43.50, "manual", "Ingresada por L\u00edder via Telegram"
        )


class TestGetTasaDisplay:
    def test_with_rate(self):
        mock_last = MagicMock()
        mock_last.tasa = 45.50
        mock_last.fuente = "open_er_api"
        with patch("src.financial.currency.db.get_last_tasa", return_value=mock_last):
            result = get_tasa_display()
        assert "Bs. 45.50" in result
        assert "open_er_api" in result

    def test_no_rate(self):
        with patch("src.financial.currency.db.get_last_tasa", return_value=None):
            assert get_tasa_display() == "Tasa no disponible"

    def test_zero_rate(self):
        mock_last = MagicMock()
        mock_last.tasa = 0
        mock_last.fuente = "test"
        with patch("src.financial.currency.db.get_last_tasa", return_value=mock_last):
            assert get_tasa_display() == "Tasa no disponible"
