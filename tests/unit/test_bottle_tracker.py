#!/usr/bin/env python3
"""
============================================================================
Unit Tests — Bottle Tracker (SWAP: 165 botellones loaner)
Estación H2O · Maracaibo, Venezuela
============================================================================

Tests unitarios para el tracking individual de botellones loaner.
"""

import pytest
import os
import sqlite3
import sys

sys.path.insert(0, "/mnt/ssd_trabajo/hermes-agent")

from skills.dispatch.bottle_tracker import BottleTracker
import skills.dispatch.bottle_tracker as bt_module


TEST_DB = "/tmp/test_bottle_tracker.db"


@pytest.fixture(scope="function")
def test_db():
    """Crea BD de test limpia con esquema completo."""
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    conn = sqlite3.connect(TEST_DB)
    conn.execute("PRAGMA foreign_keys = ON")

    # Tablas base
    conn.execute("""
        CREATE TABLE bottles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bottle_code TEXT UNIQUE NOT NULL,
            client_id INTEGER,
            status TEXT NOT NULL DEFAULT 'available',
            dispatch_delivery_id INTEGER,
            assigned_at REAL,
            expected_return_at REAL,
            returned_at REAL,
            created_at REAL NOT NULL DEFAULT (strftime('%s','now')),
            updated_at REAL NOT NULL DEFAULT (strftime('%s','now')),
            FOREIGN KEY (client_id) REFERENCES clients(id)
        )
    """)
    conn.execute("""
        CREATE TABLE bottle_movements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bottle_code TEXT NOT NULL,
            from_status TEXT,
            to_status TEXT,
            from_client_id INTEGER,
            to_client_id INTEGER,
            delivery_id INTEGER,
            location_lat REAL,
            location_lng REAL,
            performed_by TEXT,
            notes TEXT,
            created_at REAL NOT NULL DEFAULT (strftime('%s','now')),
            FOREIGN KEY (bottle_code) REFERENCES bottles(bottle_code)
        )
    """)
    conn.execute("""
        CREATE TABLE bottle_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bottle_code TEXT NOT NULL,
            alert_type TEXT NOT NULL,
            severity TEXT DEFAULT 'warning',
            acknowledged INTEGER DEFAULT 0,
            acknowledged_by TEXT,
            acknowledged_at REAL,
            created_at REAL NOT NULL DEFAULT (strftime('%s','now')),
            resolved_at REAL,
            FOREIGN KEY (bottle_code) REFERENCES bottles(bottle_code)
        )
    """)
    conn.execute("""
        CREATE TABLE clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            active INTEGER DEFAULT 1,
            client_type TEXT DEFAULT 'retail',
            bottle_return_hours INTEGER DEFAULT 36
        )
    """)

    # 165 botellones
    for i in range(1, 166):
        conn.execute("INSERT INTO bottles (bottle_code, status) VALUES (?, 'available')", (f"H2O-{i:03d}",))
    conn.execute("INSERT INTO clients (id, name) VALUES (1, 'Test Client 1'), (2, 'Test Client 2')")
    conn.commit()
    conn.close()

    yield TEST_DB

    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)


@pytest.fixture(autouse=True)
def reset_bottle_tracker_singleton():
    """Reset singleton before each test to avoid cross-test contamination."""
    bt_module._bottle_tracker_instance = None
    yield
    bt_module._bottle_tracker_instance = None


@pytest.fixture
def tracker(test_db):
    """Crea instancia BottleTracker apuntando a test_db."""
    original_db = bt_module.DISPATCH_DB
    bt_module.DISPATCH_DB = test_db
    bt_module._bottle_tracker_instance = None
    try:
        from skills.dispatch.bottle_tracker import get_bottle_tracker
        tracker = get_bottle_tracker()
        yield tracker
    finally:
        bt_module.DISPATCH_DB = original_db
        bt_module._bottle_tracker_instance = None


class TestBottleTracker:
    """Tests para BottleTracker."""

    @pytest.mark.asyncio
    async def test_get_inventory_stats_initial(self, tracker):
        """Verifica estado inicial del inventario."""
        stats = await tracker.get_inventory_stats()
        
        assert stats["total"] == 165
        assert stats["by_status"].get("available", 0) == 165
        assert stats["overdue_count"] == 0

    @pytest.mark.asyncio
    async def test_assign_to_client(self, tracker):
        """Asigna botellón a un cliente."""
        result = await tracker.assign_to_client(
            bottle_code="H2O-001",
            client_id=1,
            delivery_id=100,
        )
        
        assert result["success"] is True
        assert result["bottle"]["status"] == "in_transit_full"
        assert result["bottle"]["client_id"] == 1
        
        stats = await tracker.get_inventory_stats()
        assert stats["by_status"].get("available", 0) == 164
        assert stats["by_status"].get("in_transit_full", 0) == 1
        
        # Verificar estado en BD
        conn = sqlite3.connect("/tmp/test_bottle_tracker.db")
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT bottle_code, status, client_id FROM bottles WHERE bottle_code = 'H2O-001'"
        ).fetchone()
        conn.close()
        
        assert row["status"] == "in_transit_full"
        assert row["client_id"] == 1

    @pytest.mark.asyncio
    async def test_confirm_delivery(self, tracker):
        """Confirma entrega de botellón."""
        # Primero asignar
        await tracker.assign_to_client("H2O-010", client_id=1, delivery_id=200)
        
        # Confirmar entrega
        result = await tracker.confirm_delivery(
            bottle_code="H2O-010",
            client_id=1,
        )
        
        assert result["success"] is True
        assert result["bottle"]["status"] == "with_client"
        
        # Verificar estado
        conn = sqlite3.connect("/tmp/test_bottle_tracker.db")
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT bottle_code, status FROM bottles WHERE bottle_code = 'H2O-010'"
        ).fetchone()
        conn.close()
        
        assert row["status"] == "with_client"

    @pytest.mark.asyncio
    async def test_confirm_delivery_wrong_status_fails(self, tracker):
        """Confirma entrega de botellón en estado incorrecto falla."""
        # Intentar confirmar sin asignar primero
        result = await tracker.confirm_delivery(
            bottle_code="H2O-020",
            client_id=1,
        )
        
        assert result["success"] is False
        assert "in_transit_full" in result["error"] or "tránsito" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_return_from_client(self, tracker):
        """Retorno de botellones desde cliente."""
        # Asignar y confirmar entrega
        await tracker.assign_to_client("H2O-050", client_id=1, delivery_id=500)
        await tracker.confirm_delivery("H2O-050", client_id=1)
        
        # Retornar
        result = await tracker.return_from_client(
            bottle_code="H2O-050",
            client_id=1,
            delivery_id=600,
        )
        
        assert result["success"] is True
        assert result["bottle"]["status"] == "in_transit_empty"
        
        # Verificar estado vuelve a available después de wash_complete
        await tracker.send_to_wash("H2O-050", performed_by="plant")
        await tracker.wash_complete("H2O-050", performed_by="plant")
        
        conn = sqlite3.connect("/tmp/test_bottle_tracker.db")
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT bottle_code, status FROM bottles WHERE bottle_code = 'H2O-050'"
        ).fetchone()
        conn.close()
        
        assert row["status"] == "available"

    @pytest.mark.asyncio
    async def test_send_to_wash(self, tracker):
        """Envía botellones a lavado."""
        await tracker.assign_to_client("H2O-060", client_id=1, delivery_id=700)
        await tracker.confirm_delivery("H2O-060", client_id=1)
        
        # Enviar a lavado
        result = await tracker.send_to_wash(
            bottle_code="H2O-060",
            performed_by="plant",
        )
        
        assert result["success"] is True
        assert result["bottle"]["status"] == "maintenance"
        
        # Verificar estado
        conn = sqlite3.connect("/tmp/test_bottle_tracker.db")
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT status FROM bottles WHERE bottle_code = 'H2O-060'"
        ).fetchone()
        conn.close()
        
        assert row["status"] == "maintenance"

    @pytest.mark.asyncio
    async def test_wash_complete(self, tracker):
        """Completa lavado, botellón vuelve a available."""
        await tracker.assign_to_client("H2O-070", client_id=1, delivery_id=900)
        await tracker.confirm_delivery("H2O-070", client_id=1)
        await tracker.return_from_client("H2O-070", client_id=1, delivery_id=950)
        await tracker.send_to_wash("H2O-070", performed_by="plant")
        
        result = await tracker.wash_complete(
            bottle_code="H2O-070",
            performed_by="plant",
        )
        
        assert result["success"] is True
        assert result["bottle"]["status"] == "available"
        
        conn = sqlite3.connect("/tmp/test_bottle_tracker.db")
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT status FROM bottles WHERE bottle_code = 'H2O-070'"
        ).fetchone()
        conn.close()
        
        assert row["status"] == "available"

    @pytest.mark.asyncio
    async def test_full_lifecycle(self, tracker):
        """Ciclo completo: assign → deliver → return → wash → available."""
        bottle = "H2O-080"
        
        # 1. Asignar
        r = await tracker.assign_to_client(bottle, client_id=1, delivery_id=1100)
        assert r["success"]
        
        # 2. Entregar
        r = await tracker.confirm_delivery(bottle, client_id=1)
        assert r["success"]
        
        # 3. Retornar
        r = await tracker.return_from_client(bottle, client_id=1, delivery_id=1200)
        assert r["success"]
        
        # 3b. Verificar in_transit_empty
        conn = sqlite3.connect("/tmp/test_bottle_tracker.db")
        conn.row_factory = sqlite3.Row
        row = conn.execute(f"SELECT status FROM bottles WHERE bottle_code = '{bottle}'").fetchone()
        conn.close()
        assert row["status"] == "in_transit_empty"
        
        # 4. Enviar a lavado
        r = await tracker.send_to_wash(bottle, performed_by="plant")
        assert r["success"]
        
        # 5. Lavado completo
        r = await tracker.wash_complete(bottle, performed_by="plant")
        assert r["success"]
        
        # 6. Verificar available final
        conn = sqlite3.connect("/tmp/test_bottle_tracker.db")
        conn.row_factory = sqlite3.Row
        row = conn.execute(f"SELECT status FROM bottles WHERE bottle_code = '{bottle}'").fetchone()
        conn.close()
        assert row["status"] == "available"

    @pytest.mark.asyncio
    async def test_movement_history_recorded(self, tracker):
        """Verifica que cada movimiento queda registrado en bottle_movements."""
        await tracker.assign_to_client("H2O-090", client_id=1, delivery_id=1400)
        await tracker.confirm_delivery("H2O-090", client_id=1)
        await tracker.return_from_client("H2O-090", client_id=1, delivery_id=1500)
        await tracker.send_to_wash("H2O-090", performed_by="plant")
        await tracker.wash_complete("H2O-090", performed_by="plant")
        
        conn = sqlite3.connect("/tmp/test_bottle_tracker.db")
        conn.row_factory = sqlite3.Row
        movements = conn.execute(
            "SELECT from_status, to_status FROM bottle_movements WHERE bottle_code = 'H2O-090' ORDER BY created_at"
        ).fetchall()
        conn.close()
        
        statuses = [(m["from_status"], m["to_status"]) for m in movements]
        expected = [
            ("available", "in_transit_full"),
            ("in_transit_full", "with_client"),
            ("with_client", "in_transit_empty"),
            ("in_transit_empty", "maintenance"),
            ("maintenance", "available"),
        ]
        assert statuses == expected

    @pytest.mark.asyncio
    async def test_invalid_transition_fails(self, tracker):
        """Transición inválida falla (ej: assign → wash sin deliver)."""
        # Asignar pero no entregar
        await tracker.assign_to_client("H2O-100", client_id=1, delivery_id=1600)
        
        # Intentar lavar sin entregar
        result = await tracker.send_to_wash("H2O-100", performed_by="plant")
        
        assert result["success"] is False
        assert "in_transit_empty" in result["error"] or "maintenance" in result["error"]


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])