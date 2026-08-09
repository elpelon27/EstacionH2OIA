"""
============================================================================
Unit Tests — Bottle Tracker (SWAP: 165 botellones loaner)
Estación H2O · Maracaibo, Venezuela
============================================================================

Tests unitarios para el tracking individual de botellones loaner.
"""

import pytest
import sqlite3
import os
import sys

sys.path.insert(0, "/mnt/ssd_trabajo/hermes-agent")

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
    import skills.dispatch.bottle_tracker as bt_module
    bt_module._bottle_tracker_instance = None
    yield
    bt_module._bottle_tracker_instance = None


def make_tracker(db_path: str):
    """Crea instancia BottleTracker aislada apuntando a db_path específico."""
    import skills.dispatch.bottle_tracker as bt_module
    # Parchear DB path solo para esta instancia
    original_db = bt_module.DISPATCH_DB
    bt_module.DISPATCH_DB = db_path
    try:
        # Reset singleton para forzar nueva instancia
        bt_module._bottle_tracker_instance = None
        from skills.dispatch.bottle_tracker import BottleTracker
        return BottleTracker()
    finally:
        bt_module.DISPATCH_DB = original_db


class TestBottleTracker:
    """Tests del BottleTracker - cada test usa su propia DB e instancia."""

    @pytest.mark.asyncio
    async def test_singleton(self, test_db):
        """Singleton pattern: get_bottle_tracker() returns same instance."""
        import skills.dispatch.bottle_tracker as bt_module
        t1 = bt_module.get_bottle_tracker()
        t2 = bt_module.get_bottle_tracker()
        assert t1 is t2  # get_bottle_tracker returns singleton

    @pytest.mark.asyncio
    async def test_get_inventory_stats_initial(self, test_db):
        tracker = make_tracker(test_db)
        stats = await tracker.get_inventory_stats()

        assert stats["total"] == 165
        assert stats["by_status"]["available"] == 165
        assert stats["overdue_count"] == 0
        assert stats["active_alerts"] == 0

    @pytest.mark.asyncio
    async def test_assign_to_client(self, test_db):
        tracker = make_tracker(test_db)

        result = await tracker.assign_to_client("H2O-001", client_id=1, delivery_id=100)

        assert result["success"] is True
        assert result["bottle"]["bottle_code"] == "H2O-001"
        assert result["bottle"]["status"] == "in_transit_full"
        assert result["bottle"]["client_id"] == 1
        assert result["bottle"]["dispatch_delivery_id"] == 100
        assert result["bottle"]["assigned_at"] is not None

    @pytest.mark.asyncio
    async def test_assign_already_assigned_fails(self, test_db):
        tracker = make_tracker(test_db)

        await tracker.assign_to_client("H2O-001", client_id=1, delivery_id=100)

        result = await tracker.assign_to_client("H2O-001", client_id=2, delivery_id=200)

        assert result["success"] is False
        assert "no está disponible" in result["error"]

    @pytest.mark.asyncio
    async def test_confirm_delivery(self, test_db):
        tracker = make_tracker(test_db)

        await tracker.assign_to_client("H2O-002", client_id=1, delivery_id=101)
        result = await tracker.confirm_delivery("H2O-002", client_id=1)

        assert result["success"] is True
        assert result["bottle"]["status"] == "with_client"
        assert result["bottle"]["expected_return_at"] is not None

    @pytest.mark.asyncio
    async def test_confirm_delivery_wrong_status_fails(self, test_db):
        tracker = make_tracker(test_db)

        result = await tracker.confirm_delivery("H2O-003", client_id=1)

        assert result["success"] is False
        assert "no está en tránsito lleno" in result["error"]

    @pytest.mark.asyncio
    async def test_return_from_client(self, test_db):
        tracker = make_tracker(test_db)

        await tracker.assign_to_client("H2O-004", client_id=1, delivery_id=102)
        await tracker.confirm_delivery("H2O-004", client_id=1)
        result = await tracker.return_from_client("H2O-004", client_id=1, delivery_id=102)

        assert result["success"] is True
        assert result["bottle"]["status"] == "in_transit_empty"
        assert result["bottle"]["returned_at"] is not None

    @pytest.mark.asyncio
    async def test_return_wrong_client_fails(self, test_db):
        tracker = make_tracker(test_db)

        await tracker.assign_to_client("H2O-005", client_id=1, delivery_id=103)
        await tracker.confirm_delivery("H2O-005", client_id=1)

        result = await tracker.return_from_client("H2O-005", client_id=999, delivery_id=103)

        assert result["success"] is False
        assert "no coincide" in result["error"]

    @pytest.mark.asyncio
    async def test_send_to_wash(self, test_db):
        tracker = make_tracker(test_db)

        await tracker.assign_to_client("H2O-006", client_id=1, delivery_id=104)
        await tracker.confirm_delivery("H2O-006", client_id=1)
        await tracker.return_from_client("H2O-006", client_id=1, delivery_id=104)
        result = await tracker.send_to_wash("H2O-006")

        assert result["success"] is True
        assert result["bottle"]["status"] == "maintenance"

    @pytest.mark.asyncio
    async def test_wash_complete(self, test_db):
        tracker = make_tracker(test_db)

        await tracker.assign_to_client("H2O-007", client_id=1, delivery_id=105)
        await tracker.confirm_delivery("H2O-007", client_id=1)
        await tracker.return_from_client("H2O-007", client_id=1, delivery_id=105)
        await tracker.send_to_wash("H2O-007")
        result = await tracker.wash_complete("H2O-007")

        assert result["success"] is True
        assert result["bottle"]["status"] == "available"
        assert result["bottle"]["client_id"] is None
        assert result["bottle"]["dispatch_delivery_id"] is None

    @pytest.mark.asyncio
    async def test_full_lifecycle(self, test_db):
        tracker = make_tracker(test_db)

        r1 = await tracker.assign_to_client("H2O-008", client_id=2, delivery_id=200)
        assert r1["bottle"]["status"] == "in_transit_full"

        r2 = await tracker.confirm_delivery("H2O-008", client_id=2)
        assert r2["bottle"]["status"] == "with_client"

        r3 = await tracker.return_from_client("H2O-008", client_id=2, delivery_id=200)
        assert r3["bottle"]["status"] == "in_transit_empty"

        r4 = await tracker.send_to_wash("H2O-008")
        assert r4["bottle"]["status"] == "maintenance"

        r5 = await tracker.wash_complete("H2O-008")
        assert r5["bottle"]["status"] == "available"
        assert r5["bottle"]["client_id"] is None

        stats = await tracker.get_inventory_stats()
        assert stats["by_status"]["available"] == 165

    @pytest.mark.asyncio
    async def test_movement_history_recorded(self, test_db):
        tracker = make_tracker(test_db)

        await tracker.assign_to_client("H2O-009", client_id=1, delivery_id=106)
        await tracker.confirm_delivery("H2O-009", client_id=1)

        conn = sqlite3.connect(test_db)
        conn.row_factory = sqlite3.Row
        movements = conn.execute(
            "SELECT * FROM bottle_movements WHERE bottle_code = ?", ("H2O-009",)
        ).fetchall()
        conn.close()

        assert len(movements) == 2
        assert movements[0]["from_status"] == "available"
        assert movements[0]["to_status"] == "in_transit_full"
        assert movements[1]["from_status"] == "in_transit_full"
        assert movements[1]["to_status"] == "with_client"

    @pytest.mark.asyncio
    async def test_nonexistent_bottle_fails(self, test_db):
        tracker = make_tracker(test_db)

        result = await tracker.assign_to_client("H2O-999", client_id=1, delivery_id=999)
        assert result["success"] is False
        assert "no encontrado" in result["error"]

    @pytest.mark.asyncio
    async def test_invalid_transition_fails(self, test_db):
        tracker = make_tracker(test_db)

        result = await tracker.confirm_delivery("H2O-010", client_id=1)
        assert result["success"] is False

        result = await tracker.return_from_client("H2O-010", client_id=1, delivery_id=999)
        assert result["success"] is False


class TestBottleStatusEnum:
    def test_status_values(self):
        from skills.dispatch.bottle_tracker import BottleStatus
        assert BottleStatus.AVAILABLE.value == "available"
        assert BottleStatus.IN_TRANSIT_FULL.value == "in_transit_full"
        assert BottleStatus.WITH_CLIENT.value == "with_client"
        assert BottleStatus.IN_TRANSIT_EMPTY.value == "in_transit_empty"
        assert BottleStatus.MAINTENANCE.value == "maintenance"
        assert BottleStatus.RETIRED.value == "retired"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])