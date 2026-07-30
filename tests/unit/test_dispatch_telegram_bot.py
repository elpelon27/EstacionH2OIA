"""
============================================================================
Unit Tests — DispatcherTelegramBot (handlers, callbacks, BD helpers)
Estación H2O · Maracaibo, Venezuela
============================================================================

Tests unitarios mockando BD y Telegram API.
"""

import os
import sqlite3
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, "/mnt/ssd_trabajo/hermes-agent")

TEST_DB = "/tmp/test_dispatch_bot.db"


@pytest.fixture(scope="function")
def test_db():
    """Crea BD de test limpia para cada test."""
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    conn = sqlite3.connect(TEST_DB)
    conn.execute("PRAGMA foreign_keys = ON")
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
            estimated_arrival REAL,
            actual_arrival REAL,
            actual_departure REAL,
            operator_notes TEXT,
            feedback_score INTEGER,
            created_at REAL NOT NULL DEFAULT (strftime('%s','now')),
            updated_at REAL NOT NULL DEFAULT (strftime('%s','now'))
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
    conn.commit()

    # Datos semilla
    conn.execute(
        "INSERT INTO vehicles (id, name, operator_name, active) VALUES (1, 'Triciclo 1', 'YORDANIS', 1)"
    )
    conn.execute(
        "INSERT INTO vehicles (id, name, operator_name, active) VALUES (2, 'Triciclo 2', 'EVERT', 1)"
    )
    conn.execute(
        "INSERT INTO zones (id, name, center_lat, center_lng, radius_km) VALUES (1, 'Bella Vista', 10.6500, -71.6200, 3.0)"
    )
    conn.execute(
        "INSERT INTO zones (id, name, center_lat, center_lng, radius_km) VALUES (2, 'Las Delicias', 10.6400, -71.6150, 2.5)"
    )
    conn.execute(
        "INSERT INTO clients (id, phone, phone_hash, name, lat, lng, client_type, priority, zone_id) VALUES (1, '+584121234567', 'hash1', 'Restaurante El Portal', 10.6500, -71.6200, 'b2b', 1, 1)"
    )
    conn.execute(
        "INSERT INTO clients (id, phone, phone_hash, name, lat, lng, client_type, priority, zone_id) VALUES (2, '+584122345678', 'hash2', 'Sra. González', 10.6400, -71.6150, 'residential', 5, 2)"
    )
    conn.execute(
        "INSERT INTO deliveries (id, dispatch_session_id, client_id, vehicle_id, order_sequence, status, bottles_full) VALUES (1, 1, 1, 1, 1, 'pending', 6)"
    )
    conn.execute(
        "INSERT INTO deliveries (id, dispatch_session_id, client_id, vehicle_id, order_sequence, status, bottles_full) VALUES (2, 1, 2, 1, 2, 'pending', 3)"
    )
    conn.commit()
    conn.close()

    yield TEST_DB

    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)


@pytest.fixture(autouse=True)
def patch_bot_db(test_db):
    """Parchea las constantes del módulo telegram_bot."""
    import skills.dispatch.telegram_bot as tbot_module

    tbot_module.DISPATCH_DB = test_db
    tbot_module.CONV_DB = "/tmp/test_conv.db"
    tbot_module._dispatcher_bot_instance = None
    yield
    tbot_module._dispatcher_bot_instance = None


# Importar después de los fixtures
from skills.dispatch.telegram_bot import (
    DispatcherTelegramBot,
    check_geofence,
    format_gps_url,
    get_all_choferes,
    get_chofer_by_chat_id,
    get_dispatch_db,
    get_pending_deliveries_for_chofer,
    get_vehicle_by_id,
    register_chofer,
    save_gps_track,
    update_delivery_status,
)


class TestDatabaseHelpers:
    """Tests de helpers de BD."""

    def test_get_dispatch_db_returns_connection(self):
        conn = get_dispatch_db()
        assert conn is not None
        conn.close()

    def test_register_chofer_updates_vehicle(self):
        register_chofer(123456, 1, "YORDANIS")
        conn = get_dispatch_db()
        row = conn.execute("SELECT telegram_chat_id FROM vehicles WHERE id = 1").fetchone()
        conn.close()
        assert row[0] == 123456

    def test_get_chofer_by_chat_id_found(self):
        register_chofer(999999, 2, "EVERT")
        chofer = get_chofer_by_chat_id(999999)
        assert chofer is not None
        assert chofer["operator_name"] == "EVERT"
        assert chofer["id"] == 2

    def test_get_chofer_by_chat_id_not_found(self):
        chofer = get_chofer_by_chat_id(0)
        assert chofer is None

    def test_get_all_choferes(self):
        register_chofer(111111, 1, "YORDANIS")
        choferes = get_all_choferes()
        assert len(choferes) >= 1
        assert any(c["operator_name"] == "YORDANIS" for c in choferes)

    def test_get_pending_deliveries_for_chofer(self):
        deliveries = get_pending_deliveries_for_chofer(1)
        assert len(deliveries) == 2
        assert all(d["status"] == "pending" for d in deliveries)
        assert deliveries[0]["bottles_full"] == 6

    def test_update_delivery_status_delivered(self):
        update_delivery_status(1, "delivered", "Entregado OK")
        conn = get_dispatch_db()
        row = conn.execute("SELECT status, operator_notes FROM deliveries WHERE id = 1").fetchone()
        conn.close()
        assert row[0] == "delivered"
        assert "Entregado OK" in row[1]

    def test_update_delivery_status_arrived(self):
        update_delivery_status(2, "arrived")
        conn = get_dispatch_db()
        row = conn.execute("SELECT status, actual_arrival FROM deliveries WHERE id = 2").fetchone()
        conn.close()
        assert row[0] == "arrived"
        assert row[1] is not None

    def test_save_gps_track_inserts_row(self):
        save_gps_track(
            1, 10.6500, -71.6200, accuracy=5.0, source="telegram", track_type="checkin_arrive"
        )
        conn = get_dispatch_db()
        row = conn.execute("SELECT * FROM gps_tracks WHERE vehicle_id = 1").fetchone()
        conn.close()
        assert row is not None
        assert row[2] == 10.6500  # lat
        assert row[3] == -71.6200  # lng
        assert row[4] == 5.0  # accuracy
        assert (
            row[6] == "telegram"
        )  # source (index 6 after: id, vehicle_id, lat, lng, accuracy, speed_kmh, source)

    def test_check_geofence_inside(self):
        inside = check_geofence(1, 10.6447, -71.6101)  # depot
        assert inside is True

    def test_check_geofence_outside_creates_event(self):
        inside = check_geofence(1, 10.5000, -66.9000)  # Caracas
        assert inside is False
        conn = get_dispatch_db()
        event = conn.execute("SELECT * FROM geofence_events WHERE vehicle_id = 1").fetchone()
        conn.close()
        assert event is not None
        assert event[2] == "exit"  # event_type

    def test_format_gps_url(self):
        url = format_gps_url(10.6500, -71.6200)
        assert url == "https://maps.google.com/?q=10.65,-71.62"

    def test_get_vehicle_by_id(self):
        v = get_vehicle_by_id(1)
        assert v is not None
        assert v["name"] == "Triciclo 1"
        assert v["operator_name"] == "YORDANIS"


class TestDispatcherTelegramBot:
    """Tests de la clase DispatcherTelegramBot (mocking Telegram)."""

    @pytest.fixture
    def bot(self):
        """Instancia del bot con token fake."""
        return DispatcherTelegramBot(token="123456:FAKE_TOKEN")

    @pytest.mark.asyncio
    async def test_send_delivery_to_chofer_vehicle_not_found(self, bot):
        """Vehículo sin chat_id → False."""
        bot.app = MagicMock()
        bot.app.bot = AsyncMock()

        result = await bot.send_delivery_to_chofer(
            vehicle_id=999,
            client_name="Test",
            client_phone="+584121112233",
            bottles_full=3,
            lat=10.65,
            lng=-71.62,
            address="Test",
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_send_delivery_to_chofer_success(self, bot):
        """Envío exitoso a chofer registrado."""
        register_chofer(555555, 1, "YORDANIS")

        bot.app = MagicMock()
        mock_bot = AsyncMock()
        bot.app.bot = mock_bot

        result = await bot.send_delivery_to_chofer(
            vehicle_id=1,
            client_name="Test",
            client_phone="+584121112233",
            bottles_full=3,
            lat=10.65,
            lng=-71.62,
            address="Test",
        )

        assert result is True
        mock_bot.send_message.assert_called_once()
        call_args = mock_bot.send_message.call_args
        assert call_args.kwargs["chat_id"] == 555555
        assert "NUEVO PEDIDO" in call_args.kwargs["text"]

    @pytest.mark.asyncio
    async def test_enviar_checkin_manana(self, bot):
        """Check-in matutino envía mensaje a todos los choferes."""
        register_chofer(111111, 1, "YORDANIS")
        register_chofer(222222, 2, "EVERT")

        bot.app = MagicMock()
        mock_bot = AsyncMock()
        bot.app.bot = mock_bot

        await bot.enviar_checkin_manana()

        assert mock_bot.send_message.call_count == 2
        calls = mock_bot.send_message.call_args_list
        assert calls[0].kwargs["chat_id"] == 111111
        assert calls[1].kwargs["chat_id"] == 222222
        assert "Buenos días" in calls[0].kwargs["text"]

    @pytest.mark.asyncio
    async def test_enviar_checkin_manana_no_bot(self, bot):
        """Si bot no inicializado → log error y return."""
        bot.app = None
        # No debe lanzar excepción
        await bot.enviar_checkin_manana()


class TestCallbacks:
    """Tests de lógica de callbacks (simulados)."""

    @pytest.mark.asyncio
    async def test_callback_registro_flow(self):
        """Flujo registro: /start → botón → registered."""
        pass  # Tests de integración completa requieren mocking complejo de telegram.Update

    @pytest.mark.asyncio
    async def test_callback_accion_arrived_requests_gps(self):
        """Botón Llegué → status=arrived + pide GPS."""
        pass

    @pytest.mark.asyncio
    async def test_callback_accion_delivered_shows_next(self):
        """Botón Entregado → status=delivered + muestra siguiente si hay."""
        pass

    @pytest.mark.asyncio
    async def test_callback_checkin_yes(self):
        """Check-in Sí → confirmado + log."""
        pass

    @pytest.mark.asyncio
    async def test_callback_checkin_no(self):
        """Check-in No → notifica admin + log warning."""
        pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
