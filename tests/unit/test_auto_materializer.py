"""Tests del materializador orders_auto → deliveries (reparto por zonas con rotación)."""

import sqlite3
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

import skills.dispatch.auto_materializer as am  # noqa: E402


@pytest.fixture()
def db(tmp_path):
    """Copia la dispatch.db real a sandbox y la aísla del materializador."""
    src = REPO / "data" / "dispatch.db"
    db_path = tmp_path / "dispatch.db"
    if src.exists():
        db_path.write_bytes(src.read_bytes())
    else:
        db_path.write_bytes(b"")
    # recrear tablas mínimas por si la DB copiada no las tiene (o está vacía)
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS vehicles (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
            operator_name TEXT, telegram_chat_id INTEGER, active INTEGER DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS orders_auto (
            id INTEGER PRIMARY KEY AUTOINCREMENT, client_id INTEGER NOT NULL,
            qty_botellones INTEGER NOT NULL, delivery_date TEXT NOT NULL,
            estado TEXT NOT NULL DEFAULT 'pending_dispatch', zone_id INTEGER,
            created_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS dispatch_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT, vehicle_id INTEGER NOT NULL,
            shift TEXT NOT NULL, date TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'planning',
            route_algorithm TEXT, created_at REAL NOT NULL
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_session_vehicle_date_shift
            ON dispatch_sessions(vehicle_id, date, shift);
        DROP TABLE IF EXISTS clients;
        CREATE TABLE clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT, phone TEXT NOT NULL,
            phone_hash TEXT NOT NULL DEFAULT 'h', name TEXT,
            active INTEGER DEFAULT 1
        );
        DROP TABLE IF EXISTS deliveries;
        CREATE TABLE deliveries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dispatch_session_id INTEGER NOT NULL, client_id INTEGER NOT NULL,
            vehicle_id INTEGER NOT NULL, order_sequence INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending', bottles_full INTEGER DEFAULT 0,
            operator_notes TEXT, created_at REAL, updated_at REAL
        );
        """
    )
    # limpiar data preexistente y sembrar vehículos
    for t in ("vehicles", "orders_auto", "deliveries", "dispatch_sessions"):
        conn.execute(f"DELETE FROM {t}")
    conn.execute("DELETE FROM clients")
    for i in range(1, 6):
        conn.execute("INSERT INTO clients (phone, name) VALUES (?,?)", (f"04xx{i}", f"Cliente {i}"))
    conn.execute("INSERT INTO vehicles (name, operator_name, active) VALUES ('T1','YORDANIS',1)")
    conn.execute("INSERT INTO vehicles (name, operator_name, active) VALUES ('T2','EVERT',1)")
    conn.commit()
    conn.close()
    old = am.DISPATCH_DB
    am.DISPATCH_DB = db_path
    yield db_path
    am.DISPATCH_DB = old


def _seed_orders(db, date, orders):
    conn = sqlite3.connect(db)
    for i, (zone, qty) in enumerate(orders, 1):
        conn.execute(
            "INSERT INTO orders_auto (client_id, qty_botellones, delivery_date,"
            " zone_id, created_at) VALUES (?,?,?,?,strftime('%s','now'))",
            (i, qty, date, zone),
        )
    conn.commit()
    conn.close()


def test_materialize_assigns_and_is_idempotent(db):
    _seed_orders(db, "2026-09-28", [(1, 5), (1, 3), (2, 4)])  # lunes
    r1 = am.materialize_day("2026-09-28")
    assert r1["inserted"] == 3
    # idempotencia: segunda corrida no duplica
    r2 = am.materialize_day("2026-09-28")
    assert r2["inserted"] == 0
    conn = sqlite3.connect(db)
    n = conn.execute("SELECT COUNT(*) FROM deliveries").fetchone()[0]
    assert n == 3
    estados = conn.execute("SELECT estado FROM orders_auto").fetchall()
    assert all(e[0] == "assigned" for e in estados)
    conn.close()


def test_rotation_changes_assignment_next_day(db):
    """La rotación diaria debe cambiar qué vehículo recibe la misma zona."""
    _seed_orders(db, "2026-09-28", [(1, 5)])  # lunes → offset 0
    _seed_orders(db, "2026-09-29", [(1, 5)])  # martes → offset 1
    conn = sqlite3.connect(db)
    v_ids = sorted(r[0] for r in conn.execute("SELECT id FROM vehicles").fetchall())
    conn.close()
    assert len(v_ids) == 2
    r_lun = am.materialize_day("2026-09-28")
    r_mar = am.materialize_day("2026-09-29")
    # lunes (offset 0): zona 1 → primer vehículo; martes (offset 1): rota al segundo
    assert r_lun["assignment"]["1"] == v_ids[0]
    assert r_mar["assignment"]["1"] == v_ids[1]


def test_no_orders_returns_empty(db):
    r = am.materialize_day("2026-09-28")
    assert r["inserted"] == 0
    assert "msg" in r
