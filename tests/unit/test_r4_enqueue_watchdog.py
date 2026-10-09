#!/usr/bin/env python3
"""Tests §1/§2 (2026-10-08): encolado webhook R4 → despacho + watchdog pagados-sin-cola.

Misión 2026-10-08 (parches/2026-10-08-prompt-hermes-pago-despacho.md):
- §1: webhook R4notifica (src/integrations/r4/webhooks.py) encola la entrega a
  dispatch_queue tras verificar el pago (antes SOLO el flujo de conversación
  encolaba → pedidos pagados por Pago Móvil nunca llegaban al chofer).
- §2: watchdog — fs_pedidos con estado_pago='pagado' >15 min sin fila en
  dispatch_queue → alerta Telegram al Líder, UNA sola vez por pedido.

Corre sobre BDs temporales (no toca data/conversations.db de producción).
"""

import asyncio
import os
import shutil
import sqlite3
import sys
import tempfile
from datetime import UTC, datetime, timedelta

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)


@pytest.fixture()
def tmp_dbs(monkeypatch):
    """BDs temporales + schema mínimo que usan las funciones bajo test."""
    tmp = tempfile.mkdtemp(prefix="h2o_wd_")
    conv = os.path.join(tmp, "conv.db")
    disp = os.path.join(tmp, "disp.db")
    monkeypatch.setenv("SQLITE_PATH", conv)
    monkeypatch.setenv("DISPATCH_DB_PATH", disp)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")  # sin alertas reales en tests
    monkeypatch.setenv("META_ACCESS_TOKEN", "")
    monkeypatch.setenv("META_PHONE_NUMBER_ID", "")

    conn = sqlite3.connect(conv)
    conn.executescript(
        """
        CREATE TABLE fs_pedidos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_telefono TEXT, cliente_nombre TEXT,
            monto_total_eur REAL, botellones_cantidad INTEGER DEFAULT 0,
            hielo_cantidad INTEGER DEFAULT 0, metodo_pago TEXT,
            estado_pago TEXT DEFAULT 'pendiente',
            estado_entrega TEXT DEFAULT 'sin_entregar',
            creado_at TEXT
        );
        CREATE TABLE fs_verificacion_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fs_pedido_id INTEGER NOT NULL, intento INTEGER NOT NULL,
            metodo_verificacion TEXT, pago_encontrado BOOLEAN DEFAULT 0,
            accion TEXT, resultado_detalle TEXT, timestamp TEXT NOT NULL
        );
        CREATE TABLE fs_tasas_cambio (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            par TEXT, tasa REAL, registrado_at TEXT
        );
        CREATE TABLE dispatch_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fs_pedido_id INTEGER, cliente_nombre TEXT, cliente_telefono TEXT,
            producto_desc TEXT, total_eur REAL, total_bs REAL, metodo_pago TEXT,
            gps_lat REAL, gps_lng REAL, gps_url TEXT, direccion TEXT,
            chofer_asignado TEXT, estado TEXT DEFAULT 'pending',
            enviado_at TEXT, respondido_at TEXT, creado_at TEXT NOT NULL
        );
        """
    )
    # dispatch.db: clients (dirección/GPS) — fila SIN gps para probar §Prueba-3
    dconn = sqlite3.connect(disp)
    dconn.executescript(
        """
        CREATE TABLE clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone TEXT, name TEXT, lat REAL, lng REAL,
            address_text TEXT, updated_at REAL
        );
        """
    )
    dconn.execute(
        "INSERT INTO clients (phone, name, lat, lng, address_text) "
        "VALUES ('04122560720', 'María Pérez', NULL, NULL, NULL)"
    )
    dconn.commit()
    dconn.close()

    # Pedido pagado hace 30 min (para §1 y §2)
    c = (datetime.now(UTC) - timedelta(minutes=30)).isoformat()
    conn.execute(
        "INSERT INTO fs_pedidos (id, cliente_telefono, cliente_nombre, "
        "monto_total_eur, botellones_cantidad, metodo_pago, estado_pago, creado_at) "
        "VALUES (2267, '04122560720', 'María Pérez', 3.00, 2, 'pagomovil', 'pagado', ?)",
        (c,),
    )
    conn.execute(
        "INSERT INTO fs_tasas_cambio (par, tasa, registrado_at) "
        "VALUES ('EUR/VES', 979.08, ?)",
        (c,),
    )
    conn.commit()
    conn.close()

    # importar DESPUÉS de setear env (módulo lee env en helpers)
    from src.integrations.r4 import webhooks as W

    yield W
    shutil.rmtree(tmp, ignore_errors=True)


class _FakePedido:
    """Simula PedidoFinanciero tal como llega a _enqueue_delivery_from_fs."""

    id = 2267
    cliente_telefono = "04122560720"
    cliente_nombre = "María Pérez"
    monto_total_eur = 3.00
    botellones_cantidad = 2
    hielo_cantidad = 0
    metodo_pago = "pagomovil"


class TestEnqueueDeliveryFromFs:
    """§1: encolar a despacho desde el webhook R4, idempotente."""

    def test_enqueue_crea_fila_pending(self, tmp_dbs):
        W = tmp_dbs
        r = W._enqueue_delivery_from_fs(_FakePedido())
        assert r["enqueued"] is True
        assert r["existing"] is False

        conn = sqlite3.connect(os.environ["SQLITE_PATH"])
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM dispatch_queue WHERE fs_pedido_id = 2267"
        ).fetchone()
        conn.close()
        assert row is not None
        assert row["estado"] == "pending"
        assert row["cliente_telefono"] == "04122560720"
        assert row["producto_desc"] == "2 botellones de agua"
        assert row["total_bs"] == pytest.approx(2937.24)  # 3.00 * 979.08

    def test_idempotencia_no_duplica(self, tmp_dbs):
        """Prueba 2 de la misión: R4 duplicado → NO segunda fila."""
        W = tmp_dbs
        W._enqueue_delivery_from_fs(_FakePedido())
        conn = sqlite3.connect(os.environ["SQLITE_PATH"])
        antes = conn.execute("SELECT COUNT(*) FROM dispatch_queue").fetchone()[0]
        conn.close()

        r2 = W._enqueue_delivery_from_fs(_FakePedido())

        conn = sqlite3.connect(os.environ["SQLITE_PATH"])
        despues = conn.execute("SELECT COUNT(*) FROM dispatch_queue").fetchone()[0]
        conn.close()
        assert antes == despues == 1
        assert r2["enqueued"] is False
        assert r2["existing"] is True

    def test_sin_gps_campos_vacios_sin_excepcion(self, tmp_dbs):
        """Prueba 3: pedido sin GPS → fila encolada, dirección vacía, sin raise."""
        W = tmp_dbs
        r = W._enqueue_delivery_from_fs(_FakePedido())
        assert r["enqueued"] is True

        conn = sqlite3.connect(os.environ["SQLITE_PATH"])
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT gps_lat, gps_lng, gps_url, direccion FROM dispatch_queue WHERE fs_pedido_id=2267"
        ).fetchone()
        conn.close()
        assert row["gps_lat"] is None
        assert row["gps_lng"] is None
        assert row["gps_url"] == ""
        assert row["direccion"] == ""


class TestWatchdogDespacho:
    """§2: pagado >15 min sin cola → exactamente UNA alerta."""

    def test_watchdog_alerta_una_vez(self, tmp_dbs):
        """Prueba 4: ciclo1=1 alerta, ciclo2=0 (idempotente)."""
        W = tmp_dbs
        # Sin encolar (simula falla silenciosa del §1)
        n1 = W.watchdog_ciclo_despacho()
        n2 = W.watchdog_ciclo_despacho()
        assert n1 == 1, "debió alertar 1 vez"
        assert n2 == 0, "segundo ciclo no debe re-alertar"

    def test_watchdog_ignora_ya_encolado(self, tmp_dbs):
        W = tmp_dbs
        W._enqueue_delivery_from_fs(_FakePedido())  # encolado → no alertar
        n = W.watchdog_ciclo_despacho()
        assert n == 0

    def test_watchdog_ignora_entregado_y_viejo(self, tmp_dbs):
        """Ventana 24h + estado_entrega: entregados y >24h no alertan."""
        W = tmp_dbs
        conn = sqlite3.connect(os.environ["SQLITE_PATH"])
        c_hoy = (datetime.now(UTC) - timedelta(minutes=30)).isoformat()
        c_viejo = (datetime.now(UTC) - timedelta(days=3)).isoformat()
        # pagado + ya entregado (ruta 7:45) → NO alertar
        conn.execute(
            "INSERT INTO fs_pedidos (cliente_telefono, monto_total_eur, estado_pago, estado_entrega, creado_at) "
            "VALUES ('04129998888', 5.0, 'pagado', 'entregado', ?)",
            (c_hoy,),
        )
        # pagado + sin entregar pero de hace 3 días → fuera de ventana → NO alertar
        conn.execute(
            "INSERT INTO fs_pedidos (cliente_telefono, monto_total_eur, estado_pago, estado_entrega, creado_at) "
            "VALUES ('04121112222', 2.0, 'pagado', 'sin_entregar', ?)",
            (c_viejo,),
        )
        conn.commit()
        conn.close()

        n = W.watchdog_ciclo_despacho()
        assert n == 1  # solo el 2267 de hoy sin entregar