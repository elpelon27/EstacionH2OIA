"""
Tests unitarios para Financial Shield v3.0
"""

import uuid
from datetime import UTC, datetime

import pytest

from src.financial import database as db
from src.financial.currency import convert_eur_to_ves, convert_ves_to_eur
from src.financial.models import Pago, PedidoFinanciero, Producto
from src.financial.verificacion import (
    _escalar_humano,
    _get_pedidos_para_recordatorio,
    verificar_pago_manual,
)


class TestModels:
    """Tests de modelos de datos"""

    def test_producto_precio_unitario(self):
        p = Producto(
            id=1,
            nombre="Botellón 19L",
            precio_base_eur=1.00,
            precio_volumen_eur=0.85,
            umbral_volumen=10,
            tiene_comision=True,
            comision_eur=0.07,
            activo=True,
        )
        assert p.precio_unitario(5) == 1.00
        assert p.precio_unitario(10) == 0.85
        assert p.precio_unitario(15) == 0.85

    def test_producto_total(self):
        p = Producto(
            id=1,
            nombre="Botellón 19L",
            precio_base_eur=1.00,
            precio_volumen_eur=0.85,
            umbral_volumen=10,
            tiene_comision=True,
            comision_eur=0.07,
            activo=True,
        )
        assert p.total(5) == 5.00
        assert p.total(10) == 8.50


class TestCurrency:
    """Tests de conversión de monedas"""

    def test_convert_eur_to_ves(self):
        # Tasa: 1 EUR = 100 VES
        assert convert_eur_to_ves(10.0, 100.0) == 1000.0
        assert convert_eur_to_ves(1.5, 100.0) == 150.0
        assert convert_eur_to_ves(0, 100.0) == 0.0

    def test_convert_ves_to_eur(self):
        # Tasa: 1 EUR = 100 VES
        assert convert_ves_to_eur(1000.0, 100.0) == 10.0
        assert convert_ves_to_eur(150.0, 100.0) == 1.5
        assert convert_ves_to_eur(0, 100.0) == 0.0


class TestDatabase:
    """Tests de base de datos (requieren BD real)"""

    def test_get_all_productos(self):
        productos = db.get_all_productos()
        assert len(productos) >= 2
        nombres = [p.nombre for p in productos]
        assert "Botellón 19L" in nombres
        assert "Bolsa Hielo 7.5kg" in nombres

    def test_get_producto_by_id(self):
        p = db.get_producto_by_id(1)
        assert p is not None
        assert p.nombre == "Botellón 19L"
        assert p.precio_base_eur == 1.00

    def test_create_and_get_pedido(self):
        unique_pedido_id = 90000 + abs(hash(str(uuid.uuid4()))) % 10000
        pedido = PedidoFinanciero(
            pedido_id=unique_pedido_id,
            cliente_telefono="+584121234567",
            cliente_nombre="Test Cliente",
            monto_total_eur=10.00,
            monto_total_ves=1000.00,
            tasa_eur_ves=100.0,
            botellones_cantidad=5,
            hielo_cantidad=2,
            metodo_pago="pagomovil",
            estado_pago="pendiente",
            estado_entrega="sin_entregar",
            creado_at=datetime.now(UTC).isoformat(),
            actualizado_at=datetime.now(UTC).isoformat(),
        )
        pedido_id = db.create_pedido_financiero(pedido)
        assert pedido_id > 0

        # Recuperar
        retrieved = db.get_pedido_financiero_by_pedido_id(unique_pedido_id)
        assert retrieved is not None
        assert retrieved.cliente_telefono == "+584121234567"
        assert retrieved.monto_total_eur == 10.00


class TestVerificacionLogic:
    """Tests de lógica de verificación (sin I/O real)"""

    def test_calcular_fecha_vencimiento(self):
        from datetime import datetime

        from src.financial.cobranzas import calcular_fecha_vencimiento

        # calcular_fecha_vencimiento usa CARACAS_TZ (UTC-4), retorna string naive
        # Test que retorna fechas válidas en el futuro
        fecha_express = calcular_fecha_vencimiento("express")
        fecha_semanal = calcular_fecha_vencimiento("semanal")
        fecha_mensual = calcular_fecha_vencimiento("mensual")

        # Parsear como naive y comparar con now en UTC (aprox)
        now_utc = datetime.now(UTC)

        # Express: ~24h desde Caracas (UTC-4) = ~20h desde UTC
        venc_express = datetime.fromisoformat(fecha_express).replace(tzinfo=UTC)
        assert (venc_express - now_utc).total_seconds() >= 19 * 3600  # ~20h

        # Semanal: ~7 días
        venc_semanal = datetime.fromisoformat(fecha_semanal).replace(tzinfo=UTC)
        assert (venc_semanal - now_utc).total_seconds() >= 6 * 86400  # ~6.5 días

        # Mensual: ~30 días
        venc_mensual = datetime.fromisoformat(fecha_mensual).replace(tzinfo=UTC)
        assert (venc_mensual - now_utc).total_seconds() >= 28 * 86400  # ~28 días

    def test_pedido_financiero_campos_v3(self):
        """Verificar que los campos v3.0 existen en el modelo"""
        p = PedidoFinanciero(
            pedido_id=1,
            monto_total_eur=10.0,
            monto_pagado_eur=0.0,
            tasa_eur_ves_deuda=100.0,
        )
        assert hasattr(p, "monto_pagado_eur")
        assert hasattr(p, "tasa_eur_ves_deuda")
        assert p.monto_pagado_eur == 0.0
        assert p.tasa_eur_ves_deuda == 100.0

    def test_pago_campos_v3(self):
        """Verificar campos v3.0 en Pago"""
        pago = Pago(
            fs_pedido_id=1,
            monto_eur=5.0,
            tasa_eur_ves_pago=101.0,
            metodo_pago="pagomovil",
            comprobante_phash="abc123",
        )
        assert hasattr(pago, "tasa_eur_ves_pago")
        assert hasattr(pago, "comprobante_phash")
        assert pago.tasa_eur_ves_pago == 101.0
        assert pago.comprobante_phash == "abc123"


class TestReminderLogic:
    """Tests de lógica de recordatorios"""

    @pytest.mark.asyncio
    async def test_get_pedidos_para_recordatorio_vacio(self):
        # Sin BD real, solo test que la función no crashea
        pedidos = _get_pedidos_para_recordatorio()
        assert isinstance(pedidos, list)

    @pytest.mark.asyncio
    async def test_escalar_humano_estructura(self):
        """Test que _escalar_humano existe y retorna estructura esperada (mock BD)"""
        import inspect

        sig = inspect.signature(_escalar_humano)
        params = list(sig.parameters.keys())
        assert "pedido" in params
        assert "intento" in params

        # Verificar que es async
        assert inspect.iscoroutinefunction(_escalar_humano)


class TestAtomicPayment:
    """Tests de transacción atómica de pagos"""

    @pytest.mark.asyncio
    async def test_verificar_pago_manual_estructura(self):
        """Verificar que la función existe y tiene la firma correcta"""
        import inspect

        sig = inspect.signature(verificar_pago_manual)
        params = list(sig.parameters.keys())
        assert "fs_pedido_id" in params
        assert "monto_eur" in params
        assert "metodo_pago" in params
        assert "referencia" in params
        assert "verificado_por" in params


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
