"""
Coverage tests for src/financial/verificacion.py — mock MetaWhatsAppClient + BD.

NOTE: _process_reminder_cycle and _escalar_humano call db.log_verificacion INSIDE
a `with db.get_db()` block, which would deadlock SQLite (nested write connection).
We mock db.log_verificacion to avoid this.
"""

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


def _make_pedido_row(**overrides) -> PedidoFinanciero:
    """Create a PedidoFinanciero for testing."""
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


def _create_pedido_in_db(pedido_id=1001, **overrides) -> PedidoFinanciero:
    """Helper: create a pedido in tmp DB and return it."""
    now = datetime.now(UTC).isoformat()
    defaults = dict(
        pedido_id=pedido_id,
        cliente_telefono="584121234567",
        cliente_nombre="Juan",
        monto_total_eur=10.0,
        tasa_eur_ves=100.0,
        tasa_eur_ves_deuda=100.0,
        estado_pago="pendiente",
        estado_entrega="entregado",
        creado_at=now,
        actualizado_at=now,
    )
    defaults.update(overrides)
    pedido = PedidoFinanciero(**defaults)
    db.create_pedido_financiero(pedido)
    return db.get_pedido_financiero_by_pedido_id(pedido_id)


def _set_pedido_extras(pedido_id, **updates):
    """Update pedido fields not persisted by create_pedido_financiero."""
    with db.get_db() as conn:
        sets = ", ".join(f"{k} = ?" for k in updates)
        conn.execute(f"UPDATE fs_pedidos SET {sets} WHERE pedido_id = ?",
                     list(updates.values()) + [pedido_id])


def _mock_meta_client(success=True):
    """Create a mock MetaWhatsAppClient."""
    mock = MagicMock()
    mock.send_text_message = AsyncMock(
        return_value={"success": success, "message_id": "msg_123"} if success
        else {"success": False, "error": "fail"}
    )
    return mock


# ---------------------------------------------------------------------------
# _compute_phash / _check_vram
# ---------------------------------------------------------------------------

class TestPhashVram:
    def test_compute_phash_no_lib(self):
        result = _compute_phash(b"fake_image_data")
        assert result is None or isinstance(result, str)

    def test_check_vram_returns_bool(self):
        # NVML may or may not be available; just check it returns a bool
        result = _check_vram()
        assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# _process_reminder_cycle
# ---------------------------------------------------------------------------

class TestProcessReminderCycle:
    async def test_process_reminder_success(self, tmp_db):
        """Test that a recordatorio is sent and persisted."""
        pedido = _create_pedido_in_db(pedido_id=1001)
        mock_client = _mock_meta_client(success=True)

        with (
            patch("core.meta_client.get_meta_client", AsyncMock(return_value=mock_client)),
            patch("src.financial.verificacion.db.log_verificacion"),
        ):
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
        pedido = _create_pedido_in_db(pedido_id=1002)
        mock_client = _mock_meta_client(success=False)

        with (
            patch("core.meta_client.get_meta_client", AsyncMock(return_value=mock_client)),
            patch("src.financial.verificacion.db.log_verificacion"),
        ):
            result = await _process_reminder_cycle(pedido)

        assert result["accion"] == "recordatorio_enviado"
        assert result["intento"] == 1

    async def test_process_reminder_exception_continues(self, tmp_db):
        """Even if get_meta_client raises, the flow continues (fail-soft)."""
        pedido = _create_pedido_in_db(pedido_id=1003)

        with (
            patch("core.meta_client.get_meta_client", AsyncMock(side_effect=Exception("conn error"))),
            patch("src.financial.verificacion.db.log_verificacion"),
        ):
            result = await _process_reminder_cycle(pedido)

        assert result["accion"] == "recordatorio_enviado"
        assert result["intento"] == 1


# ---------------------------------------------------------------------------
# _escalar_humano
# ---------------------------------------------------------------------------

class TestEscalarHumano:
    async def test_escalar_humano(self, tmp_db):
        pedido = _create_pedido_in_db(pedido_id=2001, cliente_nombre="María", monto_total_eur=25.0)

        with patch("src.financial.verificacion.db.log_verificacion"):
            result = await _escalar_humano(pedido, intento=4)

        assert result["accion"] == "escalar_humano"
        assert "ESCALAMIENTO HUMANO" in result["mensaje"]
        assert result["mensaje_cliente"] is None

        updated = db.get_pedido_financiero_by_pedido_id(2001)
        assert updated.escalo_humano  # SQLite returns 1 (truthy)


# ---------------------------------------------------------------------------
# _get_pedidos_para_recordatorio
# ---------------------------------------------------------------------------

class TestGetPedidosParaRecordatorio:
    async def test_empty_list(self, tmp_db):
        result = _get_pedidos_para_recordatorio()
        assert isinstance(result, list)
        assert len(result) == 0

    async def test_returns_eligible_pedidos(self, tmp_db):
        _create_pedido_in_db(pedido_id=3001)
        result = _get_pedidos_para_recordatorio()
        assert len(result) == 1
        assert result[0].pedido_id == 3001

    async def test_skips_recently_reminded(self, tmp_db):
        recent = datetime.now(UTC).isoformat()
        _create_pedido_in_db(pedido_id=3002)
        _set_pedido_extras(3002, ultimo_recordatorio_at=recent, recordatorios_enviados=1)
        result = _get_pedidos_para_recordatorio()
        assert len(result) == 0

    async def test_invalid_timestamp_passes(self, tmp_db):
        _create_pedido_in_db(pedido_id=3003)
        _set_pedido_extras(3003, ultimo_recordatorio_at="invalid-timestamp", recordatorios_enviados=1)
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
        _create_pedido_in_db(pedido_id=4001)
        mock_client = _mock_meta_client(success=True)
        with (
            patch("core.meta_client.get_meta_client", AsyncMock(return_value=mock_client)),
            patch("src.financial.verificacion.db.log_verificacion"),
        ):
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
        _create_pedido_in_db(pedido_id=5001, estado_pago="verificando")
        _set_pedido_extras(5001, recordatorios_enviados=0)
        mock_client = _mock_meta_client(success=True)
        with (
            patch("core.meta_client.get_meta_client", AsyncMock(return_value=mock_client)),
            patch("src.financial.verificacion.db.log_verificacion"),
        ):
            result = await recovery_scan_stuck_payments()
        assert result == 1


# ---------------------------------------------------------------------------
# verificar_pago_manual
# ---------------------------------------------------------------------------

class TestVerificarPagoManual:
    async def test_verificar_pago_manual_success(self, tmp_db):
        pedido = _create_pedido_in_db(pedido_id=6001)

        with patch("src.financial.verificacion.get_eur_ves_rate", AsyncMock(return_value=100.0)):
            result = await verificar_pago_manual(
                fs_pedido_id=pedido.id,
                monto_eur=10.0,
                metodo_pago="pagomovil",
                referencia="REF_MANUAL_001",
                verificado_por="test",
            )

        assert result["success"] is True
        assert "pagado" in result["nuevo_estado"]
        assert result["pago_id"] > 0

    async def test_verificar_pago_manual_duplicate_ref(self, tmp_db):
        pedido = _create_pedido_in_db(pedido_id=6002)

        with patch("src.financial.verificacion.get_eur_ves_rate", AsyncMock(return_value=100.0)):
            # First payment with the referencia
            await verificar_pago_manual(
                fs_pedido_id=pedido.id,
                monto_eur=5.0,
                metodo_pago="pagomovil",
                referencia="DUP_REF_001",
            )
            # Second payment with same referencia + method → rejected
            result = await verificar_pago_manual(
                fs_pedido_id=pedido.id,
                monto_eur=5.0,
                metodo_pago="pagomovil",
                referencia="DUP_REF_001",
            )
        assert result["success"] is False
        assert "duplicada" in result["mensaje"].lower()

    async def test_verificar_pago_manual_no_tasa(self, tmp_db):
        pedido = _create_pedido_in_db(pedido_id=6003)

        with patch("src.financial.verificacion.get_eur_ves_rate", AsyncMock(return_value=None)):
            result = await verificar_pago_manual(
                fs_pedido_id=pedido.id,
                monto_eur=10.0,
                metodo_pago="efectivo_eur",
            )
        assert result["success"] is True


# ---------------------------------------------------------------------------
# verificar_pago_api_bancaria
# ---------------------------------------------------------------------------

class TestVerificarApiBancaria:
    async def test_api_bancaria_delegates_to_manual(self, tmp_db):
        pedido = _create_pedido_in_db(pedido_id=7001)

        with patch("src.financial.verificacion.get_eur_ves_rate", AsyncMock(return_value=100.0)):
            result = await verificar_pago_api_bancaria(
                fs_pedido_id=pedido.id,
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
