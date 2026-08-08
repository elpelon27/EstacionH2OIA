"""
SPRINT 4.3 — E2E Test: Driver Registration + Real Telegram Flow Simulation

Validates the complete flow:
1. Driver sends /start → selects vehicle → registered with chat_id
2. Bridge _send_to_dispatch_queue() → WorkloadRouter → DispatcherSkill.notify_driver()
3. DispatcherTelegramBot.send_delivery_to_chofer() sends to registered chat_id
4. Consumer processes queue → creates delivery in dispatch.db
5. Driver actions: Llegué → Entregado → next delivery
"""

import os
import sqlite3
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, "/mnt/ssd_trabajo/hermes-agent")

TEST_DB = "/tmp/test_sprint43.db"


@pytest.fixture(scope="function")
def test_db():
    """Create clean test DB for each test."""
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    conn = sqlite3.connect(TEST_DB)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row

    # Create all required tables
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
            created_at REAL NOT NULL DEFAULT (strftime('%s','now'))
        )
    """)
    conn.execute("""
        CREATE TABLE clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone TEXT NOT NULL,
            phone_hash TEXT NOT NULL,
            name TEXT,
            address_text TEXT,
            lat REAL,
            lng REAL,
            client_type TEXT NOT NULL DEFAULT 'retail',
            avg_bottles_per_visit INTEGER DEFAULT 1,
            visit_frequency TEXT,
            visit_days TEXT,
            priority INTEGER DEFAULT 5,
            zone_id INTEGER,
            bottle_exchange_model INTEGER DEFAULT 0,
            bottle_return_hours INTEGER DEFAULT 36,
            active INTEGER DEFAULT 1,
            notes TEXT,
            created_at REAL NOT NULL DEFAULT (strftime('%s','now')),
            updated_at REAL NOT NULL DEFAULT (strftime('%s','now'))
        )
    """)
    conn.execute("""
        CREATE TABLE deliveries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dispatch_session_id INTEGER NOT NULL,
            client_id INTEGER NOT NULL,
            vehicle_id INTEGER NOT NULL,
            order_sequence INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            bottles_full INTEGER DEFAULT 0,
            bottles_empty_pickup INTEGER DEFAULT 0,
            bottles_on_site_refill INTEGER DEFAULT 0,
            estimated_arrival REAL,
            actual_arrival REAL,
            actual_departure REAL,
            duration_seconds INTEGER,
            operator_notes TEXT,
            feedback_score INTEGER,
            created_at REAL NOT NULL DEFAULT (strftime('%s','now')),
            updated_at REAL NOT NULL DEFAULT (strftime('%s','now'))
        )
    """)
    conn.execute("""
        CREATE TABLE dispatch_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vehicle_id INTEGER NOT NULL,
            shift TEXT NOT NULL,
            date TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'planning',
            total_clients INTEGER DEFAULT 0,
            total_bottles_full INTEGER DEFAULT 0,
            total_distance_km REAL DEFAULT 0,
            total_duration_minutes INTEGER DEFAULT 0,
            route_algorithm TEXT DEFAULT 'ortools_vrp',
            route_computed_at REAL,
            started_at REAL,
            completed_at REAL,
            created_at REAL NOT NULL DEFAULT (strftime('%s','now'))
        )
    """)
    conn.execute("""
        CREATE TABLE gps_tracks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vehicle_id INTEGER NOT NULL,
            lat REAL NOT NULL,
            lng REAL NOT NULL,
            accuracy REAL,
            speed_kmh REAL,
            source TEXT NOT NULL DEFAULT 'telegram',
            delivery_id INTEGER,
            track_type TEXT DEFAULT 'periodic',
            created_at REAL NOT NULL DEFAULT (strftime('%s','now'))
        )
    """)
    conn.execute("""
        CREATE TABLE geofence_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vehicle_id INTEGER NOT NULL,
            event_type TEXT NOT NULL,
            zone_id INTEGER,
            lat REAL NOT NULL,
            lng REAL NOT NULL,
            created_at REAL NOT NULL DEFAULT (strftime('%s','now'))
        )
    """)
    conn.execute("""
        CREATE TABLE zones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            center_lat REAL,
            center_lng REAL,
            radius_km REAL,
            color TEXT DEFAULT '#3B82F6',
            created_at REAL NOT NULL DEFAULT (strftime('%s','now'))
        )
    """)

    # Insert test zones
    conn.execute(
        "INSERT INTO zones (id, name, center_lat, center_lng, radius_km) VALUES (1, 'Norte', 10.6700, -71.6300, 8.0)"
    )
    conn.execute(
        "INSERT INTO zones (id, name, center_lat, center_lng, radius_km) VALUES (2, 'Centro', 10.6447, -71.6101, 5.0)"
    )
    conn.execute(
        "INSERT INTO zones (id, name, center_lat, center_lng, radius_km) VALUES (3, 'Sur-Este', 10.6100, -71.5800, 7.0)"
    )

    # Insert test vehicles (no chat_id initially)
    conn.execute(
        "INSERT INTO vehicles (id, name, operator_name, telegram_chat_id, max_full_bottles, max_empty_bottles, active) VALUES (1, 'Triciclo 1', 'YORDANIS', NULL, 30, 70, 1)"
    )
    conn.execute(
        "INSERT INTO vehicles (id, name, operator_name, telegram_chat_id, max_full_bottles, max_empty_bottles, active) VALUES (2, 'Triciclo 2', 'EVERT', NULL, 30, 70, 1)"
    )

    conn.commit()
    conn.close()

    yield TEST_DB

    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)


@pytest.fixture(autouse=True)
def patch_modules(test_db):
    """Patch modules to use test DB."""
    import skills.dispatch.consumer as consumer_module
    import skills.dispatch.telegram_bot as tbot_module
    import skills.dispatcher as dispatcher_module

    tbot_module.DISPATCH_DB = test_db
    dispatcher_module.DISPATCH_DB = test_db
    consumer_module.DISPATCH_DB = test_db
    consumer_module.CONV_DB = "/tmp/test_conv.db"
    tbot_module.CONV_DB = "/tmp/test_conv.db"
    dispatcher_module.CONV_DB = "/tmp/test_conv.db"

    tbot_module._dispatcher_bot_instance = None

    yield

    tbot_module._dispatcher_bot_instance = None


from core.workload_router import get_router
from skills.dispatch.telegram_bot import (
    DispatcherTelegramBot,
    get_chofer_by_chat_id,
    get_dispatch_db,
    get_pending_deliveries_for_chofer,
    register_chofer,
    update_delivery_status,
)


class TestSprint43E2E:
    """SPRINT 4.3 E2E Tests."""

    @pytest.mark.asyncio
    async def test_driver_registration_flow(self):
        """Test 1: Driver registers via /start → selects vehicle → chat_id stored."""
        # Setup
        bot = DispatcherTelegramBot()
        bot._ensure_app()

        # Simulate /start command - driver selects vehicle 1
        chat_id = 111111111

        # Manually register (simulating callback_registro)
        register_chofer(chat_id, 1, "YORDANIS")

        # Verify registration
        chofer = get_chofer_by_chat_id(chat_id)
        assert chofer is not None
        assert chofer["operator_name"] == "YORDANIS"
        assert chofer["telegram_chat_id"] == chat_id
        assert chofer["id"] == 1

        # Verify vehicle updated
        conn = get_dispatch_db()
        row = conn.execute("SELECT telegram_chat_id FROM vehicles WHERE id = 1").fetchone()
        conn.close()
        assert row[0] == chat_id

        print("✅ Driver registration flow works")

    @pytest.mark.asyncio
    async def test_notify_driver_via_workload_router(self):
        """Test 2: Bridge → WorkloadRouter → DispatcherSkill.notify_driver() → send_delivery_to_chofer."""
        # Setup: register driver first
        chat_id = 222222222
        register_chofer(chat_id, 1, "YORDANIS")

        # Mock Telegram bot send_message
        with patch("skills.dispatch.telegram_bot.Application") as mock_app_class:
            mock_app = AsyncMock()
            mock_bot = AsyncMock()
            mock_app.bot = mock_bot
            mock_app_class.builder.return_value.token.return_value.build.return_value = mock_app

            # Mock send_message to succeed
            mock_bot.send_message = AsyncMock(return_value=MagicMock(message_id=12345))

            # Create fresh bot instance (will use mocked Application)
            import skills.dispatch.telegram_bot as tbot_module

            tbot_module._dispatcher_bot_instance = None
            DispatcherTelegramBot()

            # Call notify_driver via WorkloadRouter
            router = get_router()
            result = await router.execute(
                trigger="dispatch_request",
                action="notify_driver",
                vehicle_id=1,
                client_name="Hotel del Lago",
                client_phone="+584121234567",
                bottles_full=5,
                lat=10.6650,
                lng=-71.6250,
                address="Av. Del Lago, Maracaibo",
                total_eur=5.0,
                total_bs=180.0,
                metodo_pago="efectivo",
            )

            assert result["success"]
            assert result["data"]["sent"]

            # Verify send_message was called
            mock_bot.send_message.assert_called_once()
            call_args = mock_bot.send_message.call_args
            assert call_args.kwargs["chat_id"] == chat_id
            assert "Hotel del Lago" in call_args.kwargs["text"]
            assert "5 botellones" in call_args.kwargs["text"]

            print("✅ Notify driver via WorkloadRouter works")

    @pytest.mark.asyncio
    async def test_consumer_creates_delivery_and_notifies(self):
        """Test 3: Consumer processes queue → creates delivery → notifies driver."""
        # Setup: register driver
        chat_id = 333333333
        register_chofer(chat_id, 1, "YORDANIS")

        # Insert pending order in dispatch_queue (simulate bridge)
        conv_db = sqlite3.connect("/tmp/test_conv.db")
        conv_db.execute("""
            CREATE TABLE IF NOT EXISTS dispatch_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
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
                estado TEXT DEFAULT 'pending',
                enviado_at TEXT,
                creado_at TEXT NOT NULL
            )
        """)
        from datetime import datetime, timedelta, timezone

        CARACAS_TZ = timezone(timedelta(hours=-4))
        now = datetime.now(CARACAS_TZ).isoformat()
        conv_db.execute(
            """
            INSERT INTO dispatch_queue (cliente_nombre, cliente_telefono, producto_desc,
                total_eur, total_bs, metodo_pago, gps_lat, gps_lng, direccion, estado, creado_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)
        """,
            (
                "Test Consumer Client",
                "+584129999999",
                "3 botellones de agua",
                3.0,
                108.0,
                "efectivo",
                10.65,
                -71.62,
                "Test Address",
                now,
            ),
        )
        conv_db.commit()
        conv_db.close()

        # Mock Telegram send
        with patch("skills.dispatch.telegram_bot.Application") as mock_app_class:
            mock_app = AsyncMock()
            mock_bot = AsyncMock()
            mock_app.bot = mock_bot
            mock_app_class.builder.return_value.token.return_value.build.return_value = mock_app
            mock_bot.send_message = AsyncMock(return_value=MagicMock(message_id=12345))

            import skills.dispatch.telegram_bot as tbot_module

            tbot_module._dispatcher_bot_instance = None

            # Run consumer
            from skills.dispatch.consumer import consume_pending_orders

            result = await consume_pending_orders(max_orders=10)

            assert result["processed"] >= 1
            assert result["notified"] >= 1
            assert result["errors"] == 0

            # Verify delivery created in dispatch.db
            conn = get_dispatch_db()
            delivery = conn.execute(
                "SELECT * FROM deliveries WHERE client_id IN (SELECT id FROM clients WHERE phone = ?) ORDER BY id DESC LIMIT 1",
                ("+584129999999",),
            ).fetchone()
            conn.close()

            assert delivery is not None
            assert delivery["status"] == "pending"
            assert delivery["bottles_full"] == 3
            # Vehicle assigned by consumer (could be 1 or 2 depending on load)
            assert delivery["vehicle_id"] in (1, 2)

            # Verify order marked as enviado
            conv_db = sqlite3.connect("/tmp/test_conv.db")
            conv_db.row_factory = sqlite3.Row
            order = conv_db.execute(
                "SELECT * FROM dispatch_queue WHERE cliente_nombre = ? ORDER BY id DESC LIMIT 1",
                ("Test Consumer Client",),
            ).fetchone()
            conv_db.close()

            assert order["estado"] == "enviado"
            assert order["enviado_at"] is not None

            print("✅ Consumer creates delivery and notifies driver")

    @pytest.mark.asyncio
    async def test_driver_actions_llegue_entregado(self):
        """Test 4: Driver actions - Llegué → Entregado → next delivery."""
        # Setup: register driver and create delivery
        chat_id = 444444444
        register_chofer(chat_id, 1, "YORDANIS")

        conn = get_dispatch_db()
        # Create client
        conn.execute("""
            INSERT INTO clients (phone, phone_hash, name, address_text, lat, lng, client_type, priority, zone_id, active)
            VALUES ('+584121111111', 'hash1', 'Test Client', 'Test Address', 10.65, -71.62, 'b2b', 5, 1, 1)
        """)
        client_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        # Create dispatch session
        conn.execute("""
            INSERT INTO dispatch_sessions (vehicle_id, shift, date, status, total_clients, total_bottles_full, created_at)
            VALUES (1, 'morning', '2026-08-01', 'in_progress', 1, 5, strftime('%s','now'))
        """)
        session_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        # Create delivery
        conn.execute(
            """
            INSERT INTO deliveries (dispatch_session_id, client_id, vehicle_id, order_sequence, status, bottles_full, created_at, updated_at)
            VALUES (?, ?, 1, 1, 'pending', 5, strftime('%s','now'), strftime('%s','now'))
        """,
            (session_id, client_id),
        )
        delivery_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.commit()
        conn.close()

        # Simulate driver pressing "Llegué" (arrived)
        update_delivery_status(delivery_id, "arrived")

        conn = get_dispatch_db()
        delivery = conn.execute(
            "SELECT status, actual_arrival FROM deliveries WHERE id = ?", (delivery_id,)
        ).fetchone()
        conn.close()

        assert delivery["status"] == "arrived"
        assert delivery["actual_arrival"] is not None

        # Simulate driver pressing "Entregado" (delivered)
        update_delivery_status(delivery_id, "delivered")

        conn = get_dispatch_db()
        delivery = conn.execute(
            "SELECT status, actual_departure FROM deliveries WHERE id = ?", (delivery_id,)
        ).fetchone()
        conn.close()

        assert delivery["status"] == "delivered"
        assert delivery["actual_departure"] is not None

        # Verify next delivery would be shown (no more pending)
        pending = get_pending_deliveries_for_chofer(1)
        assert len(pending) == 0

        print("✅ Driver actions Llegué → Entregado works")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
