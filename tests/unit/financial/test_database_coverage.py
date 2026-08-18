"""
Coverage tests for src/financial/database.py — CRUD functions with SQLite tmp.
"""

from datetime import UTC, datetime

import pytest

from src.financial import database as db
from src.financial.models import (
    CuentaCobrar,
    Empleado,
    Nomina,
    Pago,
    PedidoFinanciero,
    ProveedorPago,
    ReporteDiario,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_pedido(**overrides) -> PedidoFinanciero:
    defaults = dict(
        pedido_id=1001,
        cliente_telefono="+584121234567",
        cliente_nombre="Juan Pérez",
        operador_id=1,
        monto_total_eur=10.00,
        monto_total_ves=1000.00,
        tasa_eur_ves=100.0,
        tasa_eur_ves_deuda=100.0,
        botellones_cantidad=5,
        hielo_cantidad=2,
        metodo_pago="pagomovil",
        estado_pago="pendiente",
        estado_entrega="sin_entregar",
        creado_at=datetime.now(UTC).isoformat(),
        actualizado_at=datetime.now(UTC).isoformat(),
    )
    defaults.update(overrides)
    return PedidoFinanciero(**defaults)


# ---------------------------------------------------------------------------
# now_iso / init
# ---------------------------------------------------------------------------

class TestNowIso:
    def test_now_iso_returns_str(self):
        result = db.now_iso()
        assert isinstance(result, str)
        assert "T" in result

    def test_init_database_alias(self, tmp_db):
        db.init_database()
        # Should not raise even if called twice
        db.init_database_v3()


# ---------------------------------------------------------------------------
# Productos
# ---------------------------------------------------------------------------

class TestProductos:
    def test_get_producto_by_id_found(self, tmp_db):
        p = db.get_producto_by_id(1)
        assert p is not None
        assert p.nombre == "Botellón 19L"

    def test_get_producto_by_id_not_found(self, tmp_db):
        p = db.get_producto_by_id(999)
        assert p is None

    def test_get_producto_by_nombre_found(self, tmp_db):
        p = db.get_producto_by_nombre("Botellón")
        assert p is not None
        assert "Botellón" in p.nombre

    def test_get_producto_by_nombre_not_found(self, tmp_db):
        p = db.get_producto_by_nombre("NoExiste")
        assert p is None

    def test_get_all_productos(self, tmp_db):
        productos = db.get_all_productos()
        assert len(productos) >= 2
        nombres = [p.nombre for p in productos]
        assert "Botellón 19L" in nombres


# ---------------------------------------------------------------------------
# Pedidos
# ---------------------------------------------------------------------------

class TestPedidos:
    def test_create_and_get_pedido(self, tmp_db):
        pedido = _make_pedido()
        pid = db.create_pedido_financiero(pedido)
        assert pid > 0

        retrieved = db.get_pedido_financiero_by_pedido_id(1001)
        assert retrieved is not None
        assert retrieved.cliente_nombre == "Juan Pérez"
        assert retrieved.id == pid

    def test_get_pedido_not_found(self, tmp_db):
        assert db.get_pedido_financiero_by_pedido_id(99999) is None

    def test_get_pedidos_by_cliente(self, tmp_db):
        db.create_pedido_financiero(_make_pedido(pedido_id=2001))
        db.create_pedido_financiero(
            _make_pedido(pedido_id=2002, cliente_telefono="+584121234567")
        )
        pedidos = db.get_pedidos_by_cliente("+584121234567")
        assert len(pedidos) == 2

    def test_get_pedidos_by_cliente_empty(self, tmp_db):
        pedidos = db.get_pedidos_by_cliente("+999999999999")
        assert pedidos == []

    def test_get_pedidos_pendientes_pago(self, tmp_db):
        # Pedido entregado, pendiente — should appear
        db.create_pedido_financiero(
            _make_pedido(pedido_id=3001, estado_pago="pendiente", estado_entrega="entregado")
        )
        # Pedido sin entregar — should NOT appear
        db.create_pedido_financiero(
            _make_pedido(pedido_id=3002, estado_pago="pendiente", estado_entrega="sin_entregar")
        )
        result = db.get_pedidos_pendientes_pago()
        assert any(p.pedido_id == 3001 for p in result)
        assert not any(p.pedido_id == 3002 for p in result)

    def test_update_estado_pago(self, tmp_db):
        pid = db.create_pedido_financiero(_make_pedido())
        db.update_estado_pago(pid, "pagado", "manual")
        retrieved = db.get_pedido_financiero_by_pedido_id(1001)
        assert retrieved.estado_pago == "pagado"
        assert retrieved.verificacion_bancaria == "manual"

    def test_incrementar_recordatorio(self, tmp_db):
        pid = db.create_pedido_financiero(_make_pedido())
        db.incrementar_recordatorio(pid)
        retrieved = db.get_pedido_financiero_by_pedido_id(1001)
        assert retrieved.recordatorios_enviados == 1
        assert retrieved.ultimo_recordatorio_at is not None

    def test_marcar_escalo_humano(self, tmp_db):
        pid = db.create_pedido_financiero(_make_pedido())
        db.marcar_escalo_humano(pid)
        retrieved = db.get_pedido_financiero_by_pedido_id(1001)
        assert retrieved.escalo_humano is True

    def test_confirmar_entrega(self, tmp_db):
        pid = db.create_pedido_financiero(_make_pedido())
        db.confirmar_entrega(pid, operador_id=2)
        retrieved = db.get_pedido_financiero_by_pedido_id(1001)
        assert retrieved.estado_entrega == "confirmado"
        assert retrieved.estado_pago == "verificando"
        assert retrieved.operador_id == 2
        assert retrieved.entrega_confirmada_at is not None


# ---------------------------------------------------------------------------
# Buscar pedidos por teléfono + monto + mejor match
# ---------------------------------------------------------------------------

class TestBuscarPedidos:
    def test_buscar_por_telefono_monto_normalizado(self, tmp_db):
        db.create_pedido_financiero(
            _make_pedido(
                pedido_id=4001,
                cliente_telefono="+584121234567",
                monto_total_eur=25.00,
            )
        )
        results = db.buscar_pedidos_por_telefono_monto("584121234567", "25.00")
        assert len(results) == 1
        assert results[0].pedido_id == 4001

    def test_buscar_monto_invalido(self, tmp_db):
        results = db.buscar_pedidos_por_telefono_monto("+584121234567", "abc")
        assert results == []

    def test_buscar_sin_resultados(self, tmp_db):
        results = db.buscar_pedidos_por_telefono_monto("+589999999999", "99.99")
        assert results == []

    def test_seleccionar_mejor_match_vacio(self):
        assert db.seleccionar_mejor_match([], "123", 10.0) is None

    def test_seleccionar_mejor_match_unico(self):
        p = _make_pedido()
        result = db.seleccionar_mejor_match([p], "+584121234567", 10.0)
        assert result is p

    def test_seleccionar_mejor_match_scoring(self):
        p1 = _make_pedido(pedido_id=1, cliente_telefono="+584121234567", monto_total_eur=10.0)
        p2 = _make_pedido(pedido_id=2, cliente_telefono="+584122222222", monto_total_eur=10.0)
        result = db.seleccionar_mejor_match([p1, p2], "+584121234567", 10.0)
        assert result.pedido_id == 1  # exact phone match scores higher


# ---------------------------------------------------------------------------
# Pagos
# ---------------------------------------------------------------------------

class TestPagos:
    def test_add_pago_and_update_pedido_full(self, tmp_db):
        pid = db.create_pedido_financiero(_make_pedido(monto_total_eur=10.00))
        pago_id, estado = db.add_pago_and_update_pedido(
            fs_pedido_id=pid,
            monto_eur=10.00,
            monto_ves=1000.0,
            tasa_eur_ves_pago=100.0,
            metodo_pago="pagomovil",
            referencia="REF001",
            verificacion_metodo="manual",
            verificado_por="test",
        )
        assert pago_id > 0
        assert estado == "pagado"

    def test_add_pago_partial(self, tmp_db):
        pid = db.create_pedido_financiero(_make_pedido(monto_total_eur=10.00))
        pago_id, estado = db.add_pago_and_update_pedido(
            fs_pedido_id=pid,
            monto_eur=5.00,
            monto_ves=500.0,
            tasa_eur_ves_pago=100.0,
            metodo_pago="efectivo_eur",
            verificacion_metodo="manual",
        )
        assert estado == "parcial"

    def test_create_pago_legacy(self, tmp_db):
        pid = db.create_pedido_financiero(_make_pedido())
        pago = Pago(
            fs_pedido_id=pid,
            cliente_telefono="+584121234567",
            cliente_nombre="Juan",
            monto_eur=5.0,
            monto_ves=500.0,
            metodo_pago="pagomovil",
            referencia="LEG001",
            tasa_eur_ves=100.0,
            verificacion_metodo="manual",
            verificado=True,
            verificado_at=datetime.now(UTC).isoformat(),
            verificado_por="test",
        )
        pago_id = db.create_pago(pago)
        assert pago_id > 0

    def test_verificar_pago_manual_db(self, tmp_db):
        pid = db.create_pedido_financiero(_make_pedido())
        pago = Pago(
            fs_pedido_id=pid,
            cliente_telefono="+584121234567",
            monto_eur=5.0,
            metodo_pago="pagomovil",
        )
        pago_id = db.create_pago(pago)
        db.verificar_pago_manual(pago_id, "lider")
        pagos = db.get_pagos_by_cliente("+584121234567")
        assert any(p.id == pago_id and p.verificado for p in pagos)

    def test_get_pago_by_referencia_found(self, tmp_db):
        pid = db.create_pedido_financiero(_make_pedido())
        db.add_pago_and_update_pedido(
            fs_pedido_id=pid,
            monto_eur=10.0,
            monto_ves=1000.0,
            tasa_eur_ves_pago=100.0,
            metodo_pago="pagomovil",
            referencia="DUP001",
        )
        pago = db.get_pago_by_referencia("DUP001")
        assert pago is not None
        assert pago.referencia == "DUP001"

    def test_get_pago_by_referencia_not_found(self, tmp_db):
        assert db.get_pago_by_referencia("NOEXISTE") is None


# ---------------------------------------------------------------------------
# Cuentas por cobrar
# ---------------------------------------------------------------------------

class TestCuentasCobrar:
    def _create_cuenta(self, **overrides) -> CuentaCobrar:
        defaults = dict(
            cliente_telefono="+584121234567",
            cliente_nombre="Juan",
            fs_pedido_id=1,
            monto_original_eur=100.0,
            monto_pagado_eur=0.0,
            tipo_credito="semanal",
            fecha_vencimiento="2020-01-01",
            estado="pendiente",
        )
        defaults.update(overrides)
        return CuentaCobrar(**defaults)

    def test_create_and_get_activas(self, tmp_db):
        db.create_cuenta_cobrar(self._create_cuenta(estado="pendiente"))
        db.create_cuenta_cobrar(self._create_cuenta(estado="parcial"))
        db.create_cuenta_cobrar(self._create_cuenta(estado="pagado"))
        activas = db.get_cuentas_cobrar_activas()
        assert len(activas) == 2  # pendiente + parcial

    def test_get_cuentas_vencidas(self, tmp_db):
        # fecha_vencimiento in the past → vencida
        db.create_cuenta_cobrar(self._create_cuenta(fecha_vencimiento="2020-01-01"))
        # fecha_vencimiento in the future → no vencida
        db.create_cuenta_cobrar(self._create_cuenta(fecha_vencimiento="2099-12-31"))
        vencidas = db.get_cuentas_vencidas()
        assert len(vencidas) == 1


# ---------------------------------------------------------------------------
# Tasas de cambio
# ---------------------------------------------------------------------------

class TestTasas:
    def test_save_and_get_last_tasa(self, tmp_db):
        db.save_tasa("EUR/VES", 105.5, "manual", "test")
        tasa = db.get_last_tasa("EUR/VES")
        assert tasa is not None
        assert tasa.tasa == 105.5
        assert tasa.fuente == "manual"
        assert tasa.notas == "test"

    def test_get_last_tasa_not_found(self, tmp_db):
        assert db.get_last_tasa("XYZ/ABC") is None

    def test_save_multiple_tasas_returns_latest(self, tmp_db):
        db.save_tasa("EUR/VES", 100.0, "bcv")
        db.save_tasa("EUR/VES", 110.0, "manual")
        tasa = db.get_last_tasa("EUR/VES")
        assert tasa.tasa == 110.0


# ---------------------------------------------------------------------------
# Verificación log
# ---------------------------------------------------------------------------

class TestVerificacionLog:
    def test_log_verificacion(self, tmp_db):
        pid = db.create_pedido_financiero(_make_pedido())
        db.log_verificacion(pid, 1, "manual", False, "recordatorio_enviado", "test detalle")
        with db.get_db() as conn:
            row = conn.execute(
                "SELECT * FROM fs_verificacion_log WHERE fs_pedido_id = ?", (pid,)
            ).fetchone()
        assert row is not None
        assert row["intento"] == 1
        assert row["accion"] == "recordatorio_enviado"
        assert row["resultado_detalle"] == "test detalle"


# ---------------------------------------------------------------------------
# Empleados y nómina
# ---------------------------------------------------------------------------

class TestEmpleadosNomina:
    def test_create_and_get_empleados(self, tmp_db):
        emp = Empleado(
            nombre="Pedro",
            rol="operador",
            telefono="+584121234567",
            sueldo_fijo_eur=300.0,
            comision_botellon_eur=0.07,
            activo=True,
        )
        eid = db.create_empleado(emp)
        assert eid > 0

        empleados = db.get_all_empleados()
        assert any(e.id == eid for e in empleados)

    def test_get_all_empleados_only_active(self, tmp_db):
        db.create_empleado(Empleado(nombre="Activo", sueldo_fijo_eur=300.0, activo=True))
        db.create_empleado(Empleado(nombre="Inactivo", sueldo_fijo_eur=300.0, activo=False))
        empleados = db.get_all_empleados()
        nombres = [e.nombre for e in empleados]
        assert "Activo" in nombres
        assert "Inactivo" not in nombres

    def test_create_nomina(self, tmp_db):
        eid = db.create_empleado(Empleado(nombre="Pedro", sueldo_fijo_eur=300.0))
        nom = Nomina(
            empleado_id=eid,
            empleado_nombre="Pedro",
            fecha_inicio="2026-08-01",
            fecha_fin="2026-08-15",
            botellones_repartidos=100,
            sueldo_fijo_eur=300.0,
            comision_total_eur=7.0,
            total_eur=307.0,
            total_ves=30700.0,
            tasa_eur_ves=100.0,
            estado="calculada",
        )
        nid = db.create_nomina(nom)
        assert nid > 0


# ---------------------------------------------------------------------------
# Proveedores
# ---------------------------------------------------------------------------

class TestProveedores:
    def test_create_proveedor_pago(self, tmp_db):
        pago = ProveedorPago(
            proveedor_id=1,
            proveedor_nombre="Aqua Supplier",
            concepto="Compra bidones",
            monto_eur=50.0,
            monto_ves=5000.0,
            metodo_pago="efectivo_eur",
            referencia="PROV001",
            tasa_eur_ves=100.0,
        )
        pid = db.create_proveedor_pago(pago)
        assert pid > 0


# ---------------------------------------------------------------------------
# Reportes diarios
# ---------------------------------------------------------------------------

class TestReportesDiarios:
    def test_save_and_mark_reporte(self, tmp_db):
        reporte = ReporteDiario(
            fecha="2026-08-17",
            ventas_total_eur=100.0,
            cobros_total_eur=80.0,
            por_cobrar_eur=20.0,
            ventas_total_ves=10000.0,
            cobros_total_ves=8000.0,
            por_cobrar_ves=2000.0,
            num_pedidos=10,
            num_pagados=8,
            num_pendientes=2,
            num_morosos=0,
        )
        rid = db.save_reporte_diario(reporte)
        assert rid > 0

        db.mark_reporte_enviado(rid, "msg_123")
        with db.get_db() as conn:
            row = conn.execute("SELECT * FROM fs_reportes_diarios WHERE id = ?", (rid,)).fetchone()
        assert row["enviado_telegram"] == 1
        assert row["telegram_msg_id"] == "msg_123"


# ---------------------------------------------------------------------------
# get_db error handling
# ---------------------------------------------------------------------------

class TestGetDbErrors:
    def test_get_db_rollback_on_error(self, tmp_db):
        """Verify that get_db rolls back on exception."""
        pid = db.create_pedido_financiero(_make_pedido())
        # Force an error inside the context manager
        with pytest.raises(Exception):
            with db.get_db() as conn:
                conn.execute("INSERT INTO fs_pedidos (id) VALUES (?)", (pid,))
        # The failed insert should have been rolled back
        with db.get_db() as conn:
            rows = conn.execute("SELECT * FROM fs_pedidos WHERE id = ?", (pid,)).fetchall()
        assert len(rows) == 1  # Only the original insert
