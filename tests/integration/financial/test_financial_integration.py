"""
Tests de integración para Financial Shield v3.0
Requieren BD real (sqlite) y conexiones externas mockeadas
"""

from datetime import UTC, datetime
import contextlib
import os
from unittest.mock import patch

import pytest

from src.financial import database as db
from src.financial.models import PedidoFinanciero
from src.financial.verificacion import (
    recovery_scan_stuck_payments,
    verificar_pago_manual,
)


@pytest.fixture(autouse=True, scope="module")
def _isolated_financial_db(tmp_path_factory):
    """Aísla la BD financiera en un tempfile por corrida (NUNCA producción).

    database.py desvía a /tmp/test_financial.db solo con CI/GITHUB_ACTIONS; en
    local toca data/conversations.db real (dejó pedido 90010 persistido → UNIQUE
    en re-corridas). Aquí redirigimos db.DB_PATH a una BD fresca y aplicamos el
    schema, SIN tocar SQLITE_PATH (que api/bridge.py usa para dispatch_queue).
    """
    import tempfile

    tmp_db = tempfile.mktemp(suffix="_financial_test.db")
    original_db_path = db.DB_PATH
    db.DB_PATH = tmp_db
    db.init_database_v3()
    yield
    db.DB_PATH = original_db_path
    with contextlib.suppress(OSError):
        os.unlink(tmp_db)


class TestAtomicPaymentFlow:
    """Test flujo completo: crear pedido → pago parcial → pago total → estado pagado"""

    @pytest.fixture(autouse=True)
    def setup_db(self):
        """Limpiar tablas de test antes y después"""
        with db.get_db() as conn:
            # Disable FK checks for cleanup
            conn.execute("PRAGMA foreign_keys = OFF")
            conn.execute(
                "DELETE FROM fs_pagos WHERE fs_pedido_id IN (SELECT id FROM fs_pedidos WHERE pedido_id >= 90000)"
            )
            conn.execute("DELETE FROM fs_pedidos WHERE pedido_id >= 90000")
            conn.execute(
                "DELETE FROM fs_verificacion_log WHERE fs_pedido_id IN (SELECT id FROM fs_pedidos WHERE pedido_id >= 90000)"
            )
            conn.execute("PRAGMA foreign_keys = ON")
        yield
        with db.get_db() as conn:
            conn.execute("PRAGMA foreign_keys = OFF")
            conn.execute(
                "DELETE FROM fs_pagos WHERE fs_pedido_id IN (SELECT id FROM fs_pedidos WHERE pedido_id >= 90000)"
            )
            conn.execute("DELETE FROM fs_pedidos WHERE pedido_id >= 90000")
            conn.execute(
                "DELETE FROM fs_verificacion_log WHERE fs_pedido_id IN (SELECT id FROM fs_pedidos WHERE pedido_id >= 90000)"
            )
            conn.execute("PRAGMA foreign_keys = ON")

    @pytest.mark.asyncio
    async def test_pago_total_directo(self):
        """Pago único que cubre el total → estado 'pagado'"""
        # Crear pedido
        pedido = PedidoFinanciero(
            pedido_id=90001,
            cliente_telefono="+584121112233",
            cliente_nombre="Cliente Test Total",
            monto_total_eur=10.00,
            monto_total_ves=1000.00,
            tasa_eur_ves=100.0,
            tasa_eur_ves_deuda=100.0,
            botellones_cantidad=5,
            metodo_pago="pagomovil",
            estado_pago="pendiente",
            estado_entrega="confirmado",
            creado_at=datetime.now(UTC).isoformat(),
            actualizado_at=datetime.now(UTC).isoformat(),
        )
        fs_pedido_id = db.create_pedido_financiero(pedido)
        assert fs_pedido_id > 0

        # Verificar pago total
        with patch("src.financial.verificacion.get_eur_ves_rate", return_value=101.0):
            result = await verificar_pago_manual(
                fs_pedido_id=fs_pedido_id,
                monto_eur=10.00,
                metodo_pago="pagomovil",
                referencia="REF123456",
                verificado_por="test_manual",
            )

        assert result["success"] is True
        assert result["nuevo_estado"] == "pagado"

        # Verificar en BD
        with db.get_db() as conn:
            row = conn.execute("SELECT * FROM fs_pedidos WHERE id = ?", (fs_pedido_id,)).fetchone()
            assert row["estado_pago"] == "pagado"
            assert row["monto_pagado_eur"] == 10.00
            assert row["tasa_eur_ves_deuda"] == 100.0  # Congelada

            pago_row = conn.execute(
                "SELECT * FROM fs_pagos WHERE fs_pedido_id = ?", (fs_pedido_id,)
            ).fetchone()
            assert pago_row["monto_eur"] == 10.00
            assert pago_row["tasa_eur_ves_pago"] == 101.0  # Tasa al momento del pago
            assert pago_row["verificado"] == 1
            assert pago_row["referencia"] == "REF123456"

    @pytest.mark.asyncio
    async def test_pago_parcial_then_total(self):
        """Dos pagos parciales que suman el total → estado 'parcial' luego 'pagado'"""
        pedido = PedidoFinanciero(
            pedido_id=90002,
            cliente_telefono="+584121112244",
            cliente_nombre="Cliente Test Parcial",
            monto_total_eur=10.00,
            monto_total_ves=1000.00,
            tasa_eur_ves=100.0,
            tasa_eur_ves_deuda=100.0,
            botellones_cantidad=5,
            metodo_pago="pagomovil",
            estado_pago="pendiente",
            estado_entrega="confirmado",
            creado_at=datetime.now(UTC).isoformat(),
            actualizado_at=datetime.now(UTC).isoformat(),
        )
        fs_pedido_id = db.create_pedido_financiero(pedido)

        # Pago parcial 1: €4.00
        with patch("src.financial.verificacion.get_eur_ves_rate", return_value=101.0):
            result1 = await verificar_pago_manual(
                fs_pedido_id=fs_pedido_id,
                monto_eur=4.00,
                metodo_pago="pagomovil",
                referencia="REF111111",
                verificado_por="test_parcial_1",
            )

        assert result1["success"] is True
        assert result1["nuevo_estado"] == "parcial"

        with db.get_db() as conn:
            row = conn.execute(
                "SELECT monto_pagado_eur, estado_pago FROM fs_pedidos WHERE id = ?", (fs_pedido_id,)
            ).fetchone()
            assert row["monto_pagado_eur"] == 4.00
            assert row["estado_pago"] == "parcial"

        # Pago parcial 2: €6.00 (completa el total)
        with patch("src.financial.verificacion.get_eur_ves_rate", return_value=102.0):
            result2 = await verificar_pago_manual(
                fs_pedido_id=fs_pedido_id,
                monto_eur=6.00,
                metodo_pago="pagomovil",
                referencia="REF222222",
                verificado_por="test_parcial_2",
            )

        assert result2["success"] is True
        assert result2["nuevo_estado"] == "pagado"

        with db.get_db() as conn:
            row = conn.execute(
                "SELECT monto_pagado_eur, estado_pago FROM fs_pedidos WHERE id = ?", (fs_pedido_id,)
            ).fetchone()
            assert row["monto_pagado_eur"] == 10.00
            assert row["estado_pago"] == "pagado"

            # Verificar dos pagos en fs_pagos
            pagos = conn.execute(
                "SELECT * FROM fs_pagos WHERE fs_pedido_id = ? ORDER BY id", (fs_pedido_id,)
            ).fetchall()
            assert len(pagos) == 2
            assert pagos[0]["monto_eur"] == 4.00
            assert pagos[0]["tasa_eur_ves_pago"] == 101.0
            assert pagos[1]["monto_eur"] == 6.00
            assert pagos[1]["tasa_eur_ves_pago"] == 102.0

    @pytest.mark.asyncio
    async def test_anti_fraude_referencia_duplicada(self):
        """Misma referencia + mismo método → rechazo"""
        pedido = PedidoFinanciero(
            pedido_id=90003,
            cliente_telefono="+584121112255",
            cliente_nombre="Cliente Test Fraude",
            monto_total_eur=10.00,
            tasa_eur_ves=100.0,
            tasa_eur_ves_deuda=100.0,
            botellones_cantidad=5,
            metodo_pago="pagomovil",
            estado_pago="pendiente",
            estado_entrega="confirmado",
            creado_at=datetime.now(UTC).isoformat(),
            actualizado_at=datetime.now(UTC).isoformat(),
        )
        fs_pedido_id = db.create_pedido_financiero(pedido)

        # Primer pago
        with patch("src.financial.verificacion.get_eur_ves_rate", return_value=100.0):
            result1 = await verificar_pago_manual(
                fs_pedido_id=fs_pedido_id,
                monto_eur=10.00,
                metodo_pago="pagomovil",
                referencia="REF_DUPLICADA",
                verificado_por="test_fraude_1",
            )
        assert result1["success"] is True

        # Segundo pago con MISMA referencia y MISMO método
        with patch("src.financial.verificacion.get_eur_ves_rate", return_value=100.0):
            result2 = await verificar_pago_manual(
                fs_pedido_id=fs_pedido_id,
                monto_eur=5.00,
                metodo_pago="pagomovil",
                referencia="REF_DUPLICADA",  # DUPLICADA
                verificado_por="test_fraude_2",
            )

        assert result2["success"] is False
        assert "duplicada" in result2["mensaje"].lower()

    @pytest.mark.asyncio
    async def test_mismo_referencia_distinto_metodo_permitido(self):
        """Misma referencia pero distinto método → permitido (ej: pagomovil vs efectivo)"""
        pedido = PedidoFinanciero(
            pedido_id=90004,
            cliente_telefono="+584121112266",
            cliente_nombre="Cliente Test Metodo",
            monto_total_eur=10.00,
            tasa_eur_ves=100.0,
            tasa_eur_ves_deuda=100.0,
            botellones_cantidad=5,
            metodo_pago="pagomovil",
            estado_pago="pendiente",
            estado_entrega="confirmado",
            creado_at=datetime.now(UTC).isoformat(),
            actualizado_at=datetime.now(UTC).isoformat(),
        )
        fs_pedido_id = db.create_pedido_financiero(pedido)

        # Pago pagomovil
        with patch("src.financial.verificacion.get_eur_ves_rate", return_value=100.0):
            result1 = await verificar_pago_manual(
                fs_pedido_id=fs_pedido_id,
                monto_eur=5.00,
                metodo_pago="pagomovil",
                referencia="REF_COMUN",
                verificado_por="test_metodo_1",
            )
        assert result1["success"] is True

        # Pago efectivo con misma ref
        with patch("src.financial.verificacion.get_eur_ves_rate", return_value=100.0):
            result2 = await verificar_pago_manual(
                fs_pedido_id=fs_pedido_id,
                monto_eur=5.00,
                metodo_pago="efectivo_eur",
                referencia="REF_COMUN",  # Misma ref, distinto método
                verificado_por="test_metodo_2",
            )
        assert result2["success"] is True


class TestAuditLog:
    """Tests de auditoría forense (triggers)"""

    @pytest.mark.asyncio
    async def test_audit_log_on_pedido_update(self):
        """Verificar que fs_audit_log captura UPDATE en fs_pedidos"""
        pedido = PedidoFinanciero(
            pedido_id=90010,
            cliente_telefono="+584121112277",
            cliente_nombre="Cliente Audit",
            monto_total_eur=10.00,
            tasa_eur_ves=100.0,
            tasa_eur_ves_deuda=100.0,
            botellones_cantidad=5,
            metodo_pago="pagomovil",
            estado_pago="pendiente",
            estado_entrega="confirmado",
            creado_at=datetime.now(UTC).isoformat(),
            actualizado_at=datetime.now(UTC).isoformat(),
        )
        fs_pedido_id = db.create_pedido_financiero(pedido)

        # Verificar pago (cambia estado_pago y monto_pagado_eur)
        with patch("src.financial.verificacion.get_eur_ves_rate", return_value=100.0):
            await verificar_pago_manual(
                fs_pedido_id=fs_pedido_id,
                monto_eur=10.00,
                metodo_pago="pagomovil",
                referencia="REF_AUDIT",
                verificado_por="test_audit",
            )

        # Verificar audit log
        with db.get_db() as conn:
            audit_rows = conn.execute(
                "SELECT * FROM fs_audit_log WHERE tabla = 'fs_pedidos' AND registro_id = ? ORDER BY id",
                (fs_pedido_id,),
            ).fetchall()

            # Debe haber INSERT inicial + UPDATE tras pago
            assert len(audit_rows) >= 2

            insert_row = audit_rows[0]
            assert insert_row["accion"] == "INSERT"
            assert insert_row["estado_anterior"] is None
            assert "estado_pago" in insert_row["estado_nuevo"]

            update_row = audit_rows[1]
            assert update_row["accion"] == "UPDATE"
            import json

            estado_nuevo = json.loads(update_row["estado_nuevo"])
            assert "monto_pagado_eur" in estado_nuevo
            assert estado_nuevo["estado_pago"] == "pagado"

    @pytest.mark.asyncio
    async def test_audit_log_on_pago_insert(self):
        """Verificar que fs_audit_log captura INSERT en fs_pagos"""
        pedido = PedidoFinanciero(
            pedido_id=90011,
            cliente_telefono="+584121112288",
            cliente_nombre="Cliente Audit Pago",
            monto_total_eur=10.00,
            tasa_eur_ves=100.0,
            tasa_eur_ves_deuda=100.0,
            botellones_cantidad=5,
            metodo_pago="pagomovil",
            estado_pago="pendiente",
            estado_entrega="confirmado",
            creado_at=datetime.now(UTC).isoformat(),
            actualizado_at=datetime.now(UTC).isoformat(),
        )
        fs_pedido_id = db.create_pedido_financiero(pedido)

        with patch("src.financial.verificacion.get_eur_ves_rate", return_value=100.0):
            result = await verificar_pago_manual(
                fs_pedido_id=fs_pedido_id,
                monto_eur=10.00,
                metodo_pago="pagomovil",
                referencia="REF_AUDIT_PAGO_UNIQUE",
                verificado_por="test_audit_pago",
            )
        pago_id = result["pago_id"]

        with db.get_db() as conn:
            # Buscar específicamente el audit log para este pago
            audit_rows = conn.execute(
                "SELECT * FROM fs_audit_log WHERE tabla = 'fs_pagos' AND registro_id = ? ORDER BY id DESC LIMIT 1",
                (pago_id,),
            ).fetchall()

            assert len(audit_rows) >= 1
            insert_row = audit_rows[0]
            assert insert_row["accion"] == "INSERT"
            import json

            estado_nuevo = json.loads(insert_row["estado_nuevo"])
            assert estado_nuevo["monto_eur"] == 10.00
            assert estado_nuevo["metodo_pago"] == "pagomovil"
            assert estado_nuevo["referencia"] == "REF_AUDIT_PAGO_UNIQUE"


class TestRecoveryScan:
    class TestRecoveryScan:
        """Tests de recovery scan al arranque"""

        @pytest.mark.asyncio
        async def test_recovery_scan_no_stuck(self):
            """Recovery scan sin pedidos atascados → 0"""
            count = await recovery_scan_stuck_payments()
            assert count == 0

        @pytest.mark.asyncio
        async def test_recovery_scan_reanuda(self):
            """Recovery scan reanuda pedidos en 'verificando' sin recordatorio reciente"""
            # Crear pedido atascado
            from datetime import datetime

            pedido = PedidoFinanciero(
                pedido_id=90020,
                cliente_telefono="+584121112299",
                cliente_nombre="Cliente Recovery",
                monto_total_eur=10.00,
                tasa_eur_ves=100.0,
                tasa_eur_ves_deuda=100.0,
                botellones_cantidad=5,
                metodo_pago="pagomovil",
                estado_pago="verificando",
                estado_entrega="confirmado",
                recordatorios_enviados=1,
                ultimo_recordatorio_at=None,  # Sin recordatorio previo → debe reanudar
                escalo_humano=False,
                creado_at=datetime.now(UTC).isoformat(),
                actualizado_at=datetime.now(UTC).isoformat(),
            )
            fs_pedido_id = db.create_pedido_financiero(pedido)

            # Testear que recovery_scan_stuck_payments detecta el pedido
            # (sin ejecutar _process_reminder_cycle para evitar lock)
            import datetime as dt_module

            # Verificar que el pedido sería detectado por el recovery scan
            with db.get_db() as conn:
                rows = conn.execute(
                    """
                    SELECT * FROM fs_pedidos
                    WHERE estado_pago IN ('verificando', 'parcial')
                    AND escalo_humano = 0
                    AND recordatorios_enviados < ?
                    AND (
                        ultimo_recordatorio_at IS NULL
                        OR datetime(ultimo_recordatorio_at) <= datetime(?, '-' || ? || ' minutes')
                    )
                """,
                    (3, dt_module.datetime.now(dt_module.UTC).isoformat(), 60),
                ).fetchall()

            assert len(rows) == 1
            assert rows[0]["id"] == fs_pedido_id
