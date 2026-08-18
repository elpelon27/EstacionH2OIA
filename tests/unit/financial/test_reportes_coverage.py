"""
Coverage tests for src/financial/reportes.py — mock BD/Telegram/httpx.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.financial.models import ReporteDiario
from src.financial.reportes import (
    enviar_reporte_telegram,
    formatear_reporte_telegram,
    generar_reporte_diario,
    generar_y_enviar_reporte,
)


def _make_reporte(**overrides) -> ReporteDiario:
    defaults = dict(
        id=1,
        fecha="2026-08-17",
        ventas_total_eur=150.0,
        cobros_total_eur=120.0,
        por_cobrar_eur=30.0,
        ventas_total_ves=15000.0,
        cobros_total_ves=12000.0,
        por_cobrar_ves=3000.0,
        num_pedidos=15,
        num_pagados=12,
        num_pendientes=3,
        num_morosos=0,
        nomina_eur=300.0,
        generado_at=datetime.now(UTC).isoformat(),
    )
    defaults.update(overrides)
    return ReporteDiario(**defaults)


# ---------------------------------------------------------------------------
# formatear_reporte_telegram (pure function)
# ---------------------------------------------------------------------------

class TestFormatearReporte:
    def test_formato_basico(self):
        reporte = _make_reporte()
        result = formatear_reporte_telegram(reporte, "€1 = Bs. 100.00")

        assert "REPORTE DIARIO" in result
        assert "2026-08-17" in result
        assert "Bs. 100.00" in result
        assert "Pedidos: 15" in result
        assert "Pagados: 12" in result
        assert "Pendientes: 3" in result
        assert "€150.00" in result
        assert "Estación H2O" in result

    def test_formato_con_morosos(self):
        reporte = _make_reporte(num_morosos=5)
        result = formatear_reporte_telegram(reporte, "€1 = Bs. 100.00")
        assert "morosos: 5" in result

    def test_formato_sin_morosos(self):
        reporte = _make_reporte(num_morosos=0)
        result = formatear_reporte_telegram(reporte, "Tasa no disponible")
        assert "morosos" not in result.lower()

    def test_formato_tasa_no_disponible(self):
        reporte = _make_reporte()
        result = formatear_reporte_telegram(reporte, "Tasa no disponible")
        assert "Tasa no disponible" in result


# ---------------------------------------------------------------------------
# generar_reporte_diario (uses BD + currency)
# ---------------------------------------------------------------------------

class TestGenerarReporteDiario:
    async def test_generar_con_tasa(self, tmp_db):
        """Test report generation with mocked tasa and empty BD."""
        with (
            patch("src.financial.reportes.get_eur_ves_rate", AsyncMock(return_value=100.0)),
            patch("src.financial.reportes.get_total_egresos_periodo", return_value={"num_pagos": 0, "total_eur": 0.0, "total_ves": 0.0}),
            patch("src.financial.reportes.get_resumen_cobranzas", return_value={"num_activas": 0, "num_vencidas": 0}),
        ):
            reporte = await generar_reporte_diario()

        assert reporte is not None
        assert reporte.id is not None and reporte.id > 0
        assert isinstance(reporte.fecha, str)
        assert reporte.num_pedidos == 0  # Empty BD
        assert reporte.ventas_total_eur == 0.0

    async def test_generar_tasa_no_disponible(self, tmp_db):
        """When tasa is None, should use 0.0."""
        with (
            patch("src.financial.reportes.get_eur_ves_rate", AsyncMock(return_value=None)),
            patch("src.financial.reportes.get_total_egresos_periodo", return_value={"num_pagos": 0, "total_eur": 0.0, "total_ves": 0.0}),
            patch("src.financial.reportes.get_resumen_cobranzas", return_value={"num_activas": 0, "num_vencidas": 0}),
        ):
            reporte = await generar_reporte_diario()

        assert reporte is not None
        assert reporte.ventas_total_ves == 0.0  # 0 tasa → 0 VES

    async def test_generar_con_pedidos(self, tmp_db):
        """Test with actual pedidos in the DB."""
        from src.financial import database as db
        from src.financial.models import PedidoFinanciero

        now_iso = datetime.now(UTC).isoformat()
        db.create_pedido_financiero(
            PedidoFinanciero(
                pedido_id=1001,
                cliente_telefono="584121234567",
                cliente_nombre="Juan",
                monto_total_eur=25.0,
                tasa_eur_ves=100.0,
                tasa_eur_ves_deuda=100.0,
                estado_pago="pagado",
                estado_entrega="entregado",
                creado_at=now_iso,
                actualizado_at=now_iso,
            )
        )
        with (
            patch("src.financial.reportes.get_eur_ves_rate", AsyncMock(return_value=100.0)),
            patch("src.financial.reportes.get_total_egresos_periodo", return_value={"num_pagos": 0, "total_eur": 0.0, "total_ves": 0.0}),
            patch("src.financial.reportes.get_resumen_cobranzas", return_value={"num_activas": 0, "num_vencidas": 0}),
        ):
            reporte = await generar_reporte_diario()

        assert reporte.num_pedidos >= 1
        assert reporte.ventas_total_eur >= 25.0


# ---------------------------------------------------------------------------
# enviar_reporte_telegram
# ---------------------------------------------------------------------------

class TestEnviarReporteTelegram:
    async def test_sin_token(self, tmp_db, monkeypatch):
        """When TELEGRAM_BOT_TOKEN is empty, should return False."""
        monkeypatch.setattr("src.financial.reportes.TELEGRAM_BOT_TOKEN", "")
        reporte = _make_reporte()
        result = await enviar_reporte_telegram(reporte)
        assert result is False

    async def test_envio_exitoso(self, tmp_db, monkeypatch):
        """Mock httpx to simulate successful Telegram send."""
        monkeypatch.setattr("src.financial.reportes.TELEGRAM_BOT_TOKEN", "fake_token")
        monkeypatch.setattr("src.financial.reportes.TELEGRAM_CHAT_ID", "12345")
        monkeypatch.setattr("src.financial.reportes.get_tasa_display", return_value="€1 = Bs. 100.00")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": {"message_id": 999}}

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        reporte = _make_reporte()
        with patch("src.financial.reportes.httpx.AsyncClient", return_value=mock_client):
            result = await enviar_reporte_telegram(reporte)

        assert result is True

    async def test_envio_error_http(self, tmp_db, monkeypatch):
        """Mock httpx to simulate HTTP error."""
        monkeypatch.setattr("src.financial.reportes.TELEGRAM_BOT_TOKEN", "fake_token")
        monkeypatch.setattr("src.financial.reportes.TELEGRAM_CHAT_ID", "12345")
        monkeypatch.setattr("src.financial.reportes.get_tasa_display", return_value="€1 = Bs. 100.00")

        mock_response = MagicMock()
        mock_response.status_code = 500

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        reporte = _make_reporte()
        with patch("src.financial.reportes.httpx.AsyncClient", return_value=mock_client):
            result = await enviar_reporte_telegram(reporte)
        assert result is False

    async def test_envio_exception(self, tmp_db, monkeypatch):
        """Mock httpx to raise exception."""
        monkeypatch.setattr("src.financial.reportes.TELEGRAM_BOT_TOKEN", "fake_token")
        monkeypatch.setattr("src.financial.reportes.TELEGRAM_CHAT_ID", "12345")
        monkeypatch.setattr("src.financial.reportes.get_tasa_display", return_value="€1 = Bs. 100.00")

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=Exception("network error"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        reporte = _make_reporte()
        with patch("src.financial.reportes.httpx.AsyncClient", return_value=mock_client):
            result = await enviar_reporte_telegram(reporte)
        assert result is False


# ---------------------------------------------------------------------------
# generar_y_enviar_reporte
# ---------------------------------------------------------------------------

class TestGenerarYEnviar:
    async def test_generar_y_enviar_sin_token(self, tmp_db, monkeypatch):
        """End-to-end: generate + attempt send (no token → send fails)."""
        monkeypatch.setattr("src.financial.reportes.TELEGRAM_BOT_TOKEN", "")
        with (
            patch("src.financial.reportes.get_eur_ves_rate", AsyncMock(return_value=100.0)),
            patch("src.financial.reportes.get_total_egresos_periodo", return_value={"num_pagos": 0, "total_eur": 0.0, "total_ves": 0.0}),
            patch("src.financial.reportes.get_resumen_cobranzas", return_value={"num_activas": 0, "num_vencidas": 0}),
        ):
            reporte = await generar_y_enviar_reporte()

        assert reporte is not None
        assert reporte.id is not None
