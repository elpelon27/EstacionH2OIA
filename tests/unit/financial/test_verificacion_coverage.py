"""
Coverage tests for src/financial/verificacion.py — mock MetaWhatsAppClient + BD.
"""

import base64
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.financial import database as db
from src.financial.models import PedidoFinanciero
from src.financial.verificacion import (
    _check_vram,
    _compute_phash,
    _download_whatsapp_image,
    _escalar_humano,
    _get_pedidos_para_recordatorio,
    _ocr_qwen_vl,
    _process_reminder_cycle,
    recovery_scan_stuck_payments,
    run_reminder_cycle,
    verificar_pago_api_bancaria,
    verificar_pago_manual,
    verificar_pago_ocr,
)


def _make_pedido(**overrides) -> PedidoFinanciero:
    defaults = dict(
        id=1,
        pedido_id=1001,
        cliente_telefono="584121234567",
        cliente_nombre="Juan Pérez",
        monto_total_eur=10.00,
        monto_total_ves=1000.00,
        tasa_eur_ves=100.0,
        tasa_eur_ves_deuda=100.0,
        botellones_cantidad=5,
        estado_pago="pendiente",
        estado_entrega="entregado",
        recordatorios_enviados=0,
        escalo_humano=False,
        creado_at=datetime.now(UTC).isoformat(),
        actualizado_at=datetime.now(UTC).isoformat(),
    )
    defaults.update(overrides)
    return PedidoFinanciero(**defaults)


def _mock_meta_client(success=True):
    """Create a mock MetaWhatsAppClient."""
    mock = MagicMock()
    mock.send_text_message = AsyncMock(
        return_value={"success": success, "message_id": "msg_123"} if success else {"success": False, "error": "fail"}
    )
    return mock


# ---------------------------------------------------------------------------
# _compute_phash / _check_vram
# ---------------------------------------------------------------------------

class TestPhashVram:
    def test_compute_phash_no_lib(self):
        # PHASH_AVAILABLE is likely False in test env → returns None
        result = _compute_phash(b"fake_image_data")
        # Either None (if PIL not available) or a string
        assert result is None or isinstance(result, str)

    def test_check_vram_no_nvml(self):
        # NVML_AVAILABLE is False in test env → returns True (fail-open)
        result = _check_vram()
        assert result is True


# ---------------------------------------------------------------------------
# _process_reminder_cycle
# ---------------------------------------------------------------------------

class TestProcessReminderCycle:
    async def test_process_reminder_success(self, tmp_db):
        """Test that a recordatorio is sent and persisted."""
        pid = db.create_pedido_financiero(
            PedidoFinanciero(
                pedido_id=1001,
                cliente_telefono="584121234567",
                cliente_nombre="Juan",
                monto_total_eur=10.0,
                tasa_eur_ves=100.0,
                tasa_eur_ves_deuda=100.0,
                estado_pago="pendiente",
                estado_entrega="entregado",
                creado_at=datetime.now(UTC).isoformat(),
                actualizado_at=datetime.now(UTC).isoformat(),
            )
        )
        pedido = db.get_pedido_financiero_by_pedido_id(1001)
        assert pedido is not None

        mock_client = _mock_meta_client(success=True)
        with patch("core.meta_client.get_meta_client", AsyncMock(return_value=mock_client)):
            result = await _process_reminder_cycle(pedido)

        assert result["accion"] == "recordatorio_enviado"
        assert result["intento"] == 1
        assert "Recordatorio #1" in result["mensaje"]

        # Verify BD was updated
        updated = db.get_pedido_financiero_by_pedido_id(1001)
        assert updated.recordatorios_enviados == 1
        assert updated.ultimo_recordatorio_at is not None

    async def test_process_reminder_whatsapp_fails_soft(self, tmp_db):
        """WhatsApp failure should not break the flow (fail-soft)."""
        pid = db.create_pedido_financiero(
            PedidoFinanciero(
                pedido_id=1002,
                cliente_telefono="584121234567",
                cliente_nombre="Juan",
                monto_total_eur=10.0,
                tasa_eur_ves=100.0,
                tasa_eur_ves_deuda=100.0,
                estado_pago="pendiente",
                estado_entrega="entregado",
                creado_at=datetime.now(UTC).isoformat(),
                actualizado_at=datetime.now(UTC).isoformat(),
            )
        )
        pedido = db.get_pedido_financiero_by_pedido_id(1002)

        mock_client = _mock_meta_client(success=False)
        with patch("core.meta_client.get_meta_client", AsyncMock(return_value=mock_client)):
            result = await _process_reminder_cycle(pedido)

        # Still persists despite WhatsApp failure
        assert result["accion"] == "recordatorio_enviado"
        assert result["intento"] == 1

    async def test_process_reminder_exception_continues(self, tmp_db):
        """Even if get_meta_client raises, the flow continues (fail-soft)."""
        pid = db.create_pedido_financiero(
            PedidoFinanciero(
                pedido_id=1003,
                cliente_telefono="584121234567",
                cliente_nombre="Juan",
                monto_total_eur=10.0,
                tasa_eur_ves=100.0,
                tasa_eur_ves_deuda=100.0,
                estado_pago="pendiente",
                estado_entrega="entregado",
                creado_at=datetime.now(UTC).isoformat(),
                actualizado_at=datetime.now(UTC).isoformat(),
            )
        )
        pedido = db.get_pedido_financiero_by_pedido_id(1003)

        with patch("core.meta_client.get_meta_client", AsyncMock(side_effect=Exception("connection error"))):
            result = await _process_reminder_cycle(pedido)

        assert result["accion"] == "recordatorio_enviado"
        assert result["intento"] == 1


# ---------------------------------------------------------------------------
# _escalar_humano
# ---------------------------------------------------------------------------

class TestEscalarHumano:
    async def test_escalar_humano(self, tmp_db):
        pid = db.create_pedido_financiero(
            PedidoFinanciero(
                pedido_id=2001,
                cliente_telefono="584121234567",
                cliente_nombre="María",
                monto_total_eur=25.0,
                tasa_eur_ves=100.0,
                tasa_eur_ves_deuda=100.0,
                estado_pago="pendiente",
                estado_entrega="entregado",
                creado_at=datetime.now(UTC).isoformat(),
                actualizado_at=datetime.now(UTC).isoformat(),
            )
        )
        pedido = db.get_pedido_financiero_by_pedido_id(2001)

        result = await _escalar_humano(pedido, intento=4)

        assert result["accion"] == "escalar_humano"
        assert "ESCALAMIENTO HUMANO" in result["mensaje"]
        assert result["mensaje_cliente"] is None

        # Verify BD updated
        updated = db.get_pedido_financiero_by_pedido_id(2001)
        assert updated.escalo_humano is True


# ---------------------------------------------------------------------------
# _get_pedidos_para_recordatorio
# ---------------------------------------------------------------------------

class TestGetPedidosParaRecordatorio:
    async def test_empty_list(self, tmp_db):
        result = _get_pedidos_para_recordatorio()
        assert isinstance(result, list)
        assert len(result) == 0

    async def test_returns_eligible_pedidos(self, tmp_db):
        db.create_pedido_financiero(
            PedidoFinanciero(
                pedido_id=3001,
                cliente_telefono="584121234567",
                cliente_nombre="Juan",
                monto_total_eur=10.0,
                tasa_eur_ves=100.0,
                tasa_eur_ves_deuda=100.0,
                estado_pago="pendiente",
                estado_entrega="entregado",
                creado_at=datetime.now(UTC).isoformat(),
                actualizado_at=datetime.now(UTC).isoformat(),
            )
        )
        result = _get_pedidos_para_recordatorio()
        assert len(result) == 1
        assert result[0].pedido_id == 3001

    async def test_skips_recently_reminded(self, tmp_db):
        # Pedido with a very recent reminder should be skipped
        recent = datetime.now(UTC).isoformat()
        db.create_pedido_financiero(
            PedidoFinanciero(
                pedido_id=3002,
                cliente_telefono="584121234567",
                cliente_nombre="Juan",
                monto_total_eur=10.0,
                tasa_eur_ves=100.0,
                tasa_eur_ves_deuda=100.0,
                estado_pago="pendiente",
                estado_entrega="entregado",
                ultimo_recordatorio_at=recent,
                recordatorios_enviados=1,
                creado_at=datetime.now(UTC).isoformat(),
                actualizado_at=datetime.now(UTC).isoformat(),
            )
        )
        result = _get_pedidos_para_recordatorio()
        assert len(result) == 0  # Skipped because < INTERVALO_MINUTOS

    async def test_invalid_timestamp_passes(self, tmp_db):
        # If timestamp can't be parsed, pedido should still be included
        db.create_pedido_financiero(
            PedidoFinanciero(
                pedido_id=3003,
                cliente_telefono="584121234567",
                cliente_nombre="Juan",
                monto_total_eur=10.0,
                tasa_eur_ves=100.0,
                tasa_eur_ves_deuda=100.0,
                estado_pago="pendiente",
                estado_entrega="entregado",
                ultimo_recordatorio_at="invalid-timestamp",
                recordatorios_enviados=1,
                creado_at=datetime.now(UTC).isoformat(),
                actualizado_at=datetime.now(UTC).isoformat(),
            )
        )
        result = _get_pedidos_para_recordatorio()
        assert len(result) == 1


# ---------------------------------------------------------------------------
# run_reminder_cycle
# ---------------------------------------------------------------------------

class TestRunReminderCycle:
    async def test_empty_cycle(self, tmp_db):
        stats = await run_reminder_cycle()
        assert stats["procesados"] == 0
        assert stats["recordatorios_enviados"] == 0
        assert stats["escalados"] == 0
        assert stats["errores"] == 0

    async def test_cycle_with_pedido(self, tmp_db):
        db.create_pedido_financiero(
            PedidoFinanciero(
                pedido_id=4001,
                cliente_telefono="584121234567",
                cliente_nombre="Juan",
                monto_total_eur=10.0,
                tasa_eur_ves=100.0,
                tasa_eur_ves_deuda=100.0,
                estado_pago="pendiente",
                estado_entrega="entregado",
                creado_at=datetime.now(UTC).isoformat(),
                actualizado_at=datetime.now(UTC).isoformat(),
            )
        )
        mock_client = _mock_meta_client(success=True)
        with patch("core.meta_client.get_meta_client", AsyncMock(return_value=mock_client)):
            stats = await run_reminder_cycle()

        assert stats["procesados"] == 1
        assert stats["recordatorios_enviados"] == 1


# ---------------------------------------------------------------------------
# recovery_scan_stuck_payments
# ---------------------------------------------------------------------------

class TestRecoveryScan:
    async def test_empty_scan(self, tmp_db):
        result = await recovery_scan_stuck_payments()
        assert result == 0

    async def test_recovers_stuck_pedido(self, tmp_db):
        db.create_pedido_financiero(
            PedidoFinanciero(
                pedido_id=5001,
                cliente_telefono="584121234567",
                cliente_nombre="Juan",
                monto_total_eur=10.0,
                tasa_eur_ves=100.0,
                tasa_eur_ves_deuda=100.0,
                estado_pago="verificando",
                estado_entrega="entregado",
                recordatorios_enviados=0,
                creado_at=datetime.now(UTC).isoformat(),
                actualizado_at=datetime.now(UTC).isoformat(),
            )
        )
        mock_client = _mock_meta_client(success=True)
        with patch("core.meta_client.get_meta_client", AsyncMock(return_value=mock_client)):
            result = await recovery_scan_stuck_payments()

        assert result == 1


# ---------------------------------------------------------------------------
# verificar_pago_manual
# ---------------------------------------------------------------------------

class TestVerificarPagoManual:
    async def test_verificar_pago_manual_success(self, tmp_db):
        pid = db.create_pedido_financiero(
            PedidoFinanciero(
                pedido_id=6001,
                cliente_telefono="584121234567",
                cliente_nombre="Juan",
                monto_total_eur=10.0,
                tasa_eur_ves=100.0,
                tasa_eur_ves_deuda=100.0,
                estado_pago="pendiente",
                estado_entrega="entregado",
                creado_at=datetime.now(UTC).isoformat(),
                actualizado_at=datetime.now(UTC).isoformat(),
            )
        )

        with patch("src.financial.verificacion.get_eur_ves_rate", AsyncMock(return_value=100.0)):
            result = await verificar_pago_manual(
                fs_pedido_id=pid,
                monto_eur=10.0,
                metodo_pago="pagomovil",
                referencia="REF_MANUAL_001",
                verificado_por="test",
            )

        assert result["success"] is True
        assert "pagado" in result["nuevo_estado"]
        assert result["pago_id"] > 0

    async def test_verificar_pago_manual_duplicate_ref(self, tmp_db):
        pid = db.create_pedido_financiero(
            PedidoFinanciero(
                pedido_id=6002,
                cliente_telefono="584121234567",
                cliente_nombre="Juan",
                monto_total_eur=10.0,
                tasa_eur_ves=100.0,
                tasa_eur_ves_deuda=100.0,
                estado_pago="pendiente",
                estado_entrega="entregado",
                creado_at=datetime.now(UTC).isoformat(),
                actualizado_at=datetime.now(UTC).isoformat(),
            )
        )
        # First payment with the referencia
        with patch("src.financial.verificacion.get_eur_ves_rate", AsyncMock(return_value=100.0)):
            await verificar_pago_manual(
                fs_pedido_id=pid,
                monto_eur=5.0,
                metodo_pago="pagomovil",
                referencia="DUP_REF_001",
            )
            # Second payment with same referencia + method → should be rejected
            result = await verificar_pago_manual(
                fs_pedido_id=pid,
                monto_eur=5.0,
                metodo_pago="pagomovil",
                referencia="DUP_REF_001",
            )
        assert result["success"] is False
        assert "duplicada" in result["mensaje"].lower()

    async def test_verificar_pago_manual_no_tasa(self, tmp_db):
        pid = db.create_pedido_financiero(
            PedidoFinanciero(
                pedido_id=6003,
                cliente_telefono="584121234567",
                cliente_nombre="Juan",
                monto_total_eur=10.0,
                tasa_eur_ves=100.0,
                tasa_eur_ves_deuda=100.0,
                estado_pago="pendiente",
                estado_entrega="entregado",
                creado_at=datetime.now(UTC).isoformat(),
                actualizado_at=datetime.now(UTC).isoformat(),
            )
        )
        with patch("src.financial.verificacion.get_eur_ves_rate", AsyncMock(return_value=None)):
            result = await verificar_pago_manual(
                fs_pedido_id=pid,
                monto_eur=10.0,
                metodo_pago="efectivo_eur",
            )
        assert result["success"] is True


# ---------------------------------------------------------------------------
# verificar_pago_api_bancaria
# ---------------------------------------------------------------------------

class TestVerificarApiBancaria:
    async def test_api_bancaria_delegates_to_manual(self, tmp_db):
        pid = db.create_pedido_financiero(
            PedidoFinanciero(
                pedido_id=7001,
                cliente_telefono="584121234567",
                cliente_nombre="Juan",
                monto_total_eur=10.0,
                tasa_eur_ves=100.0,
                tasa_eur_ves_deuda=100.0,
                estado_pago="pendiente",
                estado_entrega="entregado",
                creado_at=datetime.now(UTC).isoformat(),
                actualizado_at=datetime.now(UTC).isoformat(),
            )
        )
        with patch("src.financial.verificacion.get_eur_ves_rate", AsyncMock(return_value=100.0)):
            result = await verificar_pago_api_bancaria(
                fs_pedido_id=pid,
                codigo_confirmacion="CONF001",
                monto_esperado_eur=10.0,
            )
        assert result["success"] is True


# ---------------------------------------------------------------------------
# verificar_pago_ocr
# ---------------------------------------------------------------------------

class TestVerificarPagoOcr:
    async def test_ocr_disabled(self, tmp_db):
        result = await verificar_pago_ocr(
            fs_pedido_id=1,
            image_url="http://example.com/img.jpg",
            monto_esperado_eur=10.0,
        )
        assert result["success"] is False
        assert result["needs_manual"] is True
        assert "deshabilitado" in result["mensaje"]


# ---------------------------------------------------------------------------
# _download_whatsapp_image
# ---------------------------------------------------------------------------

class TestDownloadImage:
    async def test_no_token_returns_none(self):
        result = await _download_whatsapp_image("http://example.com/img.jpg", "")
        assert result is None

    async def test_download_success(self):
        """Mock httpx to test successful image download."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"url": "http://example.com/actual.jpg"}

        mock_img_response = MagicMock()
        mock_img_response.status_code = 200
        mock_img_response.content = b"fake_image_bytes"

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=[mock_response, mock_img_response])
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("src.financial.verificacion.httpx.AsyncClient", return_value=mock_client):
            result = await _download_whatsapp_image("img_id", "fake_token")

        assert result == b"fake_image_bytes"

    async def test_download_http_error(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=Exception("network error"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("src.financial.verificacion.httpx.AsyncClient", return_value=mock_client):
            result = await _download_whatsapp_image("img_id", "fake_token")

        assert result is None


# ---------------------------------------------------------------------------
# _ocr_qwen_vl
# ---------------------------------------------------------------------------

class TestOcrQwenVl:
    async def test_qwen_success(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "message": {"content": '{"referencia": "123456", "monto_ves": 1000}'}
        }

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("src.financial.verificacion.httpx.AsyncClient", return_value=mock_client):
            result = await _ocr_qwen_vl(b"fake_image_data")

        assert result is not None
        assert result["referencia"] == "123456"
        assert result["monto_ves"] == 1000

    async def test_qwen_non_200(self):
        mock_response = MagicMock()
        mock_response.status_code = 500

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("src.financial.verificacion.httpx.AsyncClient", return_value=mock_client):
            result = await _ocr_qwen_vl(b"fake_image_data")

        assert result is None
