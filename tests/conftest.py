"""pytest configuration and fixtures for test isolation."""
import os
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

# Add project root to path
sys.path.insert(0, "/mnt/ssd_trabajo/hermes-agent")

# Mock ONLY the module that doesn't exist as a package:
# - skills.dispatcher (file is skills/dispatcher.py, not skills/dispatcher/)
# DO NOT mock:
# - skills.dispatch (real package at skills/dispatch/)
# - skills.dispatcher_skill (real file at skills/dispatcher_skill.py)

mock_dispatcher = AsyncMock()
mock_dispatcher.DISPATCH_DB = "/mnt/ssd_trabajo/hermes-agent/data/dispatch.db"
mock_dispatcher.CONV_DB = "/mnt/ssd_trabajo/hermes-agent/data/conversations.db"
sys.modules["skills.dispatcher"] = mock_dispatcher

# Import the REAL skills module and add the mocked modules to it
import skills
skills.dispatcher = mock_dispatcher


# =============================================================================
# DISABLE TEST FILE FIXTURES AT IMPORT TIME (before pytest sees them)
# =============================================================================

import importlib.util

# Disable test_bottle_tracker.py's fixtures at import time
spec = importlib.util.spec_from_file_location(
    "tests.unit.test_bottle_tracker", 
    "/mnt/ssd_trabajo/hermes-agent/tests/unit/test_bottle_tracker.py"
)
bt_module = importlib.util.module_from_spec(spec)
sys.modules["tests.unit.test_bottle_tracker"] = bt_module
spec.loader.exec_module(bt_module)

# Delete the test file's fixtures entirely so pytest uses ours
del bt_module.reset_bottle_tracker_singleton
del bt_module.test_db
# del bt_module.tracker  # tracker is a function, not a fixture

# Same for dispatch_telegram_bot
spec2 = importlib.util.spec_from_file_location(
    "tests.unit.test_dispatch_telegram_bot",
    "/mnt/ssd_trabajo/hermes-agent/tests/unit/test_dispatch_telegram_bot.py"
)
tbot_module = importlib.util.module_from_spec(spec2)
sys.modules["tests.unit.test_dispatch_telegram_bot"] = tbot_module
spec2.loader.exec_module(tbot_module)

del tbot_module.patch_bot_db

# Same for gps_tracker
spec3 = importlib.util.spec_from_file_location(
    "tests.unit.test_gps_tracker",
    "/mnt/ssd_trabajo/hermes-agent/tests/unit/test_gps_tracker.py"
)
gps_module_test = importlib.util.module_from_spec(spec3)
sys.modules["tests.unit.test_gps_tracker"] = gps_module_test
spec3.loader.exec_module(gps_module_test)

# Disable any fixtures in gps_tracker that might conflict
if hasattr(gps_module_test, 'test_db'):
    del gps_module_test.test_db
if hasattr(gps_module_test, 'tracker'):
    del gps_module_test.tracker


# =============================================================================
# DATABASE ISOLATION FIXTURES
# =============================================================================

_test_db_path = None


@pytest.fixture
def patch_dispatch_db(monkeypatch):
    """Patch DISPATCH_DB in all modules that use it to use a temp database per test.
    
    This fixture is NOT autouse - tests must explicitly request it.
    Each test gets a fresh temp database with the correct schema.
    """
    global _test_db_path
    import tempfile
    import sqlite3
    
    # Create temp database with correct schema
    test_db = tempfile.mktemp(suffix=".db")
    _test_db_path = test_db
    
    conn = sqlite3.connect(test_db)
    conn.execute("PRAGMA foreign_keys = ON")
    
    # Schema from test_bottle_tracker.py
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
            created_at REAL NOT_NULL DEFAULT (strftime('%s','now')),
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
    # Also add tables needed by dispatch_telegram_bot and gps_tracker tests
    conn.execute("""
        CREATE TABLE vehicles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            operator_name TEXT,
            telegram_chat_id INTEGER,
            max_full_bottles INTEGER DEFAULT 30,
            max_empty_bottles INTEGER DEFAULT 70,
            current_full_load INTEGER DEFAULT 0,
            current_empty_load INTEGER DEFAULT 0,
            shift TEXT,
            active INTEGER DEFAULT 1,
            created_at REAL NOT_NULL DEFAULT (strftime('%s','now'))
        )
    """)
    conn.execute("""
        CREATE TABLE deliveries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dispatch_session_id INTEGER NOT_NULL,
            client_id INTEGER NOT_NULL,
            vehicle_id INTEGER NOT_NULL,
            order_sequence INTEGER NOT_NULL,
            status TEXT NOT_NULL DEFAULT 'pending',
            bottles_full INTEGER DEFAULT 0,
            bottles_empty_pickup INTEGER DEFAULT 0,
            bottles_on_site_refill INTEGER DEFAULT 0,
            estimated_arrival REAL,
            actual_arrival REAL,
            actual_departure REAL,
            duration_seconds INTEGER,
            created_at REAL NOT_NULL DEFAULT (strftime('%s','now')),
            updated_at REAL NOT_NULL DEFAULT (strftime('%s','now')),
            FOREIGN KEY (client_id) REFERENCES clients(id),
            FOREIGN KEY (vehicle_id) REFERENCES vehicles(id)
        )
    """)
    conn.execute("""
        CREATE TABLE gps_tracks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vehicle_id INTEGER NOT_NULL,
            lat REAL NOT_NULL,
            lng REAL NOT_NULL,
            accuracy REAL,
            speed_kmh REAL,
            source TEXT NOT_NULL DEFAULT 'telegram',
            delivery_id INTEGER,
            track_type TEXT DEFAULT 'periodic',
            created_at REAL NOT_NULL DEFAULT (strftime('%s','now')),
            FOREIGN KEY (vehicle_id) REFERENCES vehicles(id)
        )
    """)
    conn.execute("""
        CREATE TABLE geofence_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vehicle_id INTEGER NOT_NULL,
            event_type TEXT NOT_NULL,
            zone_id INTEGER,
            lat REAL NOT_NULL,
            lng REAL NOT_NULL,
            created_at REAL NOT_NULL DEFAULT (strftime('%s','now')),
            FOREIGN KEY (vehicle_id) REFERENCES vehicles(id)
        )
    """)
    conn.execute("""
        CREATE TABLE dispatch_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            route_data TEXT,
            status TEXT DEFAULT 'active',
            created_at REAL NOT_NULL DEFAULT (strftime('%s','now')),
            completed_at REAL
        )
    """)
    conn.execute("""
        CREATE TABLE dispatch_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fs_pedido_id INTEGER,
            cliente_nombre TEXT,
            cliente_telefono TEXT,
            producto_desc TEXT,
            total_eur REAL,
            total_bs REAL,
            metodo_pago TEXT,
            gps_lat REAL,
            gps_lng REAL,
            gps_url TEXT,
            direccion TEXT,
            chofer_asignado TEXT,
            estado TEXT DEFAULT 'pending',
            enviado_at TEXT,
            respondido_at TEXT,
            creado_at TEXT NOT_NULL
        )
    """)
    conn.execute("""
        CREATE TABLE zones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT_NULL,
            description TEXT,
            center_lat REAL,
            center_lng REAL,
            radius_km REAL,
            color TEXT DEFAULT '#3B82F6',
            created_at REAL NOT_NULL DEFAULT (strftime('%s','now'))
        )
    """)
    
    # Insert 165 bottles + test clients
    for i in range(1, 166):
        conn.execute("INSERT INTO bottles (bottle_code, status) VALUES (?, 'available')", (f"H2O-{i:03d}",))
    conn.execute("INSERT INTO clients (id, name) VALUES (1, 'Test Client 1'), (2, 'Test Client 2')")
    conn.execute("INSERT INTO vehicles (id, name, operator_name, telegram_chat_id) VALUES (1, 'Triciclo 1', 'YORDANIS', 12345), (2, 'Triciclo 2', 'EVERT', 67890)")
    conn.execute("INSERT INTO zones (id, name) VALUES (1, 'Test Zone')")
    conn.commit()
    conn.close()
    
    # Patch all modules that use DISPATCH_DB
    import skills.dispatch.bottle_tracker as bt_module
    import skills.dispatch.telegram_bot as tbot_module
    import skills.dispatch.gps_tracker as gps_module
    import skills.dispatcher_skill as ds_module
    
    original_bt_db = bt_module.DISPATCH_DB
    original_tbot_db = getattr(tbot_module, 'DISPATCH_DB', None)
    original_gps_db = getattr(gps_module, 'DISPATCH_DB', None)
    original_ds_db = getattr(ds_module, 'DISPATCH_DB', None)
    
    bt_module.DISPATCH_DB = test_db
    bt_module._bottle_tracker_instance = None
    
    if hasattr(tbot_module, 'DISPATCH_DB'):
        tbot_module.DISPATCH_DB = test_db
    if hasattr(tbot_module, '_dispatcher_bot_instance'):
        tbot_module._dispatcher_bot_instance = None
    
    if hasattr(gps_module, 'DISPATCH_DB'):
        gps_module.DISPATCH_DB = test_db
    if hasattr(gps_module, '_gps_tracker_instance'):
        gps_module._gps_tracker_instance = None
    
    if hasattr(ds_module, 'DISPATCH_DB'):
        ds_module.DISPATCH_DB = test_db
    if hasattr(ds_module, '_dispatcher_skill_instance'):
        ds_module._dispatcher_skill_instance = None
    
    yield test_db
    
    # Cleanup
    bt_module.DISPATCH_DB = original_bt_db
    bt_module._bottle_tracker_instance = None
    
    if hasattr(tbot_module, 'DISPATCH_DB'):
        tbot_module.DISPATCH_DB = original_tbot_db
    if hasattr(tbot_module, '_dispatcher_bot_instance'):
        tbot_module._dispatcher_bot_instance = None
    
    if hasattr(gps_module, 'DISPATCH_DB'):
        gps_module.DISPATCH_DB = original_gps_db
    if hasattr(gps_module, '_gps_tracker_instance'):
        gps_module._gps_tracker_instance = None
    
    if hasattr(ds_module, 'DISPATCH_DB'):
        ds_module.DISPATCH_DB = original_ds_db
    if hasattr(ds_module, '_dispatcher_skill_instance'):
        ds_module._dispatcher_skill_instance = None
    
    # Cleanup temp file
    try:
        os.unlink(test_db)
    except OSError:
        pass
    _test_db_path = None


# =============================================================================
# OVERRIDE TEST FILE'S FIXTURES - as proper pytest fixtures
# =============================================================================

@pytest.fixture(autouse=True)
def reset_bottle_tracker_singleton():
    """Override test file's fixture - our autouse fixture handles singleton reset."""
    pass


@pytest.fixture
def test_db(patch_dispatch_db):
    """Override test file's test_db fixture - yield the temp DB path.
    
    Depends on patch_dispatch_db to ensure DB is created first.
    """
    yield patch_dispatch_db


@pytest.fixture
def tracker(test_db):
    """Override test file's tracker fixture - use our patched DB."""
    import skills.dispatch.bottle_tracker as bt_module
    from skills.dispatch.bottle_tracker import get_bottle_tracker
    tracker = get_bottle_tracker()
    yield tracker


def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line("markers", "slow: marks tests as slow")
    config.addinivalue_line("markers", "integration: marks tests as integration tests")
    config.addinivalue_line("markers", "unit: marks tests as unit tests")