"""
Coverage tests for src/financial/cobranzas.py — mock BD, test recordatorios/escalamiento.
"""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from src.financial.cobranzas import (
    calcular_fecha_vencimiento,
    crear_cuenta_cobrar,
    get_pedidos_para_recordatorio,
    get_resumen_cobranzas,
    procesar_recordatorio,
)
from src.financial.models import CuentaCobrar, PedidoFinanciero


def _make_pedido(**overrides) -> PedidoFinanciero:
    defaults = dict(
        id=1,
        pedido_id=1001,
        cliente_telefono="584121234567",
        cliente_nombre="Juan Pérez",
        monto_total_eur=25.0,
        tasa_eur_ves=100.0,
        estado_pago="pendiente",
        estado_entrega="entregado",
        recordatorios_enviados=0,
        escalo_humano=False,
        creado_at=datetime.now(UTC).isoformat(),
        actualizado_at=datetime.now(UTC).isoformat(),
    )
    defaults.update(overrides)
    return PedidoFinanciero(**defaults)


# ---------------------------------------------------------------------------
# calcular_fecha_vencimiento
# ---------------------------------------------------------------------------

class TestCalcularFechaVencimiento:
    def test_express(self):
        result = calcular_fecha_vencimiento("express")
        assert isinstance(result, str)
        # Should parse as a datetime
        dt = datetime.fromisoformat(result)
        assert dt is not None

    def test_semanal(self):
        result = calcular_fecha_vencimiento("semanal")
        dt = datetime.fromisoformat(result)
        assert dt is not None

    def test_mensual(self):
        result = calcular_fecha_vencimiento("mensual")
        dt = datetime.fromisoformat(result)
        assert dt is not None

    def test_contado_default(self):
        result = calcular_fecha_vencimiento("contado")
        dt = datetime.fromisoformat(result)
        assert dt is not None

    def test_express_is_sooner_than_mensual(self):
        express = datetime.fromisoformat(calcular_fecha_vencimiento("express"))
        mensual = datetime.fromisoformat(calcular_fecha_vencimiento("mensual"))
        assert express < mensual


# ---------------------------------------------------------------------------
# crear_cuenta_cobrar
# ---------------------------------------------------------------------------

class TestCrearCuentaCobrar:
    def test_creacion_exitosa(self):
        pedido = _make_pedido()
        with patch("src.financial.cobranzas.db.create_cuenta_cobrar", return_value=42) as mock_create:
            cuenta_id = crear_cuenta_cobrar(pedido, "semanal")

        assert cuenta_id == 42
        mock_create.assert_called_once()
        cuenta_arg = mock_create.call_args[0][0]
        assert cuenta_arg.cliente_telefono == "584121234567"
        assert cuenta_arg.monto_original_eur == 25.0
        assert cuenta_arg.tipo_credito == "semanal"
        assert cuenta_arg.estado == "pendiente"

    def test_creacion_con_pedido_sin_id(self):
        pedido = _make_pedido(id=None)
        with patch("src.financial.cobranzas.db.create_cuenta_cobrar", return_value=1):
            cuenta_id = crear_cuenta_cobrar(pedido, "express")
        assert cuenta_id == 1


# ---------------------------------------------------------------------------
# get_pedidos_para_recordatorio
# ---------------------------------------------------------------------------

class TestGetPedidosParaRecordatorio:
    def test_lista_vacia(self):
        with patch("src.financial.cobranzas.db.get_pedidos_pendientes_pago", return_value=[]):
            result = get_pedidos_para_recordatorio()
        assert result == []

    def test_sin_recordatorio_previo(self):
        pedido = _make_pedido(ultimo_recordatorio_at=None)
        with patch("src.financial.cobranzas.db.get_pedidos_pendientes_pago", return_value=[pedido]):
            result = get_pedidos_para_recordatorio()
        assert len(result) == 1

    def test_recordatorio_reciente_se_filtra(self):
        # Recent reminder → should be filtered out
        recent = datetime.now(UTC).isoformat()
        pedido = _make_pedido(ultimo_recordatorio_at=recent, recordatorios_enviados=1)
        with patch("src.financial.cobranzas.db.get_pedidos_pendientes_pago", return_value=[pedido]):
            result = get_pedidos_para_recordatorio()
        assert len(result) == 0

    def test_recordatorio_antiguo_pasa(self):
        # Old reminder → should pass
        old = datetime(2020, 1, 1, tzinfo=UTC).isoformat()
        pedido = _make_pedido(ultimo_recordatorio_at=old, recordatorios_enviados=1)
        with patch("src.financial.cobranzas.db.get_pedidos_pendientes_pago", return_value=[pedido]):
            result = get_pedidos_para_recordatorio()
        assert len(result) == 1

    def test_timestamp_invalido_pasa(self):
        pedido = _make_pedido(ultimo_recordatorio_at="not-a-date", recordatorios_enviados=1)
        with patch("src.financial.cobranzas.db.get_pedidos_pendientes_pago", return_value=[pedido]):
            result = get_pedidos_para_recordatorio()
        assert len(result) == 1


# ---------------------------------------------------------------------------
# procesar_recordatorio
# ---------------------------------------------------------------------------

class TestProcesarRecordatorio:
    def test_enviar_recordatorio(self):
        """When intento <= MAX_RECORDATORIOS, should send reminder."""
        pedido = _make_pedido(recordatorios_enviados=0)
        with (
            patch("src.financial.cobranzas.db.incrementar_recordatorio") as mock_inc,
            patch("src.financial.cobranzas.db.log_verificacion") as mock_log,
        ):
            result = procesar_recordatorio(pedido)

        assert result["accion"] == "recordatorio_enviado"
        assert result["intento"] == 1
        assert "1/3" in result["mensaje"]
        assert result["mensaje_cliente"] is not None
        mock_inc.assert_called_once_with(1)
        mock_log.assert_called_once()

    def test_enviar_segundo_recordatorio(self):
        pedido = _make_pedido(recordatorios_enviados=1)
        with (
            patch("src.financial.cobranzas.db.incrementar_recordatorio"),
            patch("src.financial.cobranzas.db.log_verificacion"),
        ):
            result = procesar_recordatorio(pedido)
        assert result["intento"] == 2
        assert "2/3" in result["mensaje"]

    def test_escalar_humano_tras_max(self):
        """When intento > MAX_RECORDATORIOS, should escalate."""
        pedido = _make_pedido(recordatorios_enviados=3)
        with (
            patch("src.financial.cobranzas.db.marcar_escalo_humano") as mock_esc,
            patch("src.financial.cobranzas.db.log_verificacion") as mock_log,
        ):
            result = procesar_recordatorio(pedido)

        assert result["accion"] == "escalar_humano"
        assert result["mensaje_cliente"] is None
        assert "ESCALAMIENTO HUMANO" in result["mensaje"]
        assert "Juan Pérez" in result["mensaje"]
        assert "25.00" in result["mensaje"]
        mock_esc.assert_called_once_with(1)
        mock_log.assert_called_once()

    def test_escalar_con_pedido_sin_id(self):
        pedido = _make_pedido(id=None)
        with (
            patch("src.financial.cobranzas.db.marcar_escalo_humano"),
            patch("src.financial.cobranzas.db.log_verificacion"),
        ):
            result = procesar_recordatorio(pedido)
        assert result["accion"] == "escalar_humano"


# ---------------------------------------------------------------------------
# get_resumen_cobranzas
# ---------------------------------------------------------------------------

class TestGetResumenCobranzas:
    def test_resumen_vacio(self):
        with (
            patch("src.financial.cobranzas.db.get_cuentas_cobrar_activas", return_value=[]),
            patch("src.financial.cobranzas.db.get_cuentas_vencidas", return_value=[]),
        ):
            result = get_resumen_cobranzas()

        assert result["num_activas"] == 0
        assert result["num_vencidas"] == 0
        assert result["total_activas_eur"] == 0.0
        assert result["total_vencidas_eur"] == 0.0
        assert result["cuentas"] == []

    def test_resumen_con_cuentas(self):
        activa = CuentaCobrar(
            id=1,
            cliente_telefono="584121234567",
            cliente_nombre="Juan",
            fs_pedido_id=1,
            monto_original_eur=100.0,
            monto_pagado_eur=30.0,
            tipo_credito="semanal",
            fecha_vencimiento="2026-09-01",
            estado="parcial",
        )
        vencida = CuentaCobrar(
            id=2,
            cliente_telefono="584122222222",
            cliente_nombre="Ana",
            fs_pedido_id=2,
            monto_original_eur=50.0,
            monto_pagado_eur=0.0,
            tipo_credito="express",
            fecha_vencimiento="2020-01-01",
            estado="pendiente",
        )
        with (
            patch("src.financial.cobranzas.db.get_cuentas_cobrar_activas", return_value=[activa]),
            patch("src.financial.cobranzas.db.get_cuentas_vencidas", return_value=[vencida]),
        ):
            result = get_resumen_cobranzas()

        assert result["num_activas"] == 1
        assert result["num_vencidas"] == 1
        assert result["total_activas_eur"] == 70.0  # 100 - 30
        assert result["total_vencidas_eur"] == 50.0  # 50 - 0
        assert len(result["cuentas"]) == 1
        assert result["cuentas"][0]["cliente"] == "Ana"
        assert result["cuentas"][0]["telefono"] == "584122222222"
        assert result["cuentas"][0]["monto"] == 50.0

    def test_resumen_top_10_vencidas(self):
        """Should only return top 10 vencidas."""
        vencidas = [
            CuentaCobrar(
                id=i,
                cliente_telefono=f"58412{i:07d}",
                cliente_nombre=f"Cliente {i}",
                fs_pedido_id=i,
                monto_original_eur=10.0 * i,
                monto_pagado_eur=0.0,
                tipo_credito="express",
                fecha_vencimiento="2020-01-01",
                estado="pendiente",
            )
            for i in range(1, 16)  # 15 vencidas
        ]
        with (
            patch("src.financial.cobranzas.db.get_cuentas_cobrar_activas", return_value=[]),
            patch("src.financial.cobranzas.db.get_cuentas_vencidas", return_value=vencidas),
        ):
            result = get_resumen_cobranzas()

        assert result["num_vencidas"] == 15
        assert len(result["cuentas"]) == 10  # Top 10 only
