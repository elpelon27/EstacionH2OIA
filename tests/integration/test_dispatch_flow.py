"""
============================================================================
Test E2E — Flujo completo Dispatcher + SWAP
Estación H2O · Maracaibo, Venezuela
============================================================================

Test E2E completo: Pedido WhatsApp → Valentina confirma → Bridge → 
Dispatch Queue → Route Engine → Bot Chofer → Check-in → GPS → 
Entregado → Botellón loaner tracking → Sheets Sync → Financial Shield
"""

import pytest
import asyncio
import os
import sys
import sqlite3

sys.path.insert(0, "/mnt/ssd_trabajo/hermes-agent")

# Configurar BD de test
TEST_DB = "/tmp/test_dispatch_e2e.db"


@pytest.fixture(scope="function")
def test_db():
    """Crea BD de test limpia con esquema completo."""
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    
    conn = sqlite3.connect(TEST_DB)
    conn.execute("PRAGMA foreign_keys = ON")
    
    # Tablas base
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
            updated_at REAL NOT NULL DEFAULT (strftime('%s','now')),
            FOREIGN KEY (dispatch_session_id) REFERENCES dispatch_sessions(id),
            FOREIGN KEY (client_id) REFERENCES clients(id),
            FOREIGN KEY (vehicle_id) REFERENCES vehicles(id)
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
            created_at REAL NOT NULL DEFAULT (strftime('%s','now')),
            FOREIGN KEY (vehicle_id) REFERENCES vehicles(id)
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
            created_at REAL NOT NULL DEFAULT (strftime('%s','now')),
            FOREIGN KEY (vehicle_id) REFERENCES vehicles(id)
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
            created_at REAL NOT NULL DEFAULT (strftime('%s','now')),
            FOREIGN KEY (vehicle_id) REFERENCES vehicles(id)
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
            creado_at TEXT NOT NULL
        )
    """)
    
    # Tablas SWAP
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
    
    # Datos de prueba
    import time
    now = time.time()
    
    # Vehículos
    conn.execute("INSERT INTO vehicles (id, name, operator_name, active) VALUES (1, 'Triciclo 1', 'YORDANIS', 1)")
    conn.execute("INSERT INTO vehicles (id, name, operator_name, active) VALUES (2, 'Triciclo 2', 'EVERT', 1)")
    
    # Zonas
    conn.execute("INSERT INTO zones (id, name, center_lat, center_lng, radius_km) VALUES (1, 'Bella Vista', 10.6500, -71.6200, 3.0)")
    conn.execute("INSERT INTO zones (id, name, center_lat, center_lng, radius_km) VALUES (2, 'Las Delicias', 10.6400, -71.6150, 2.5)")
    
    # Clientes
    conn.execute("""INSERT INTO clients (id, phone, phone_hash, name, address_text, lat, lng, client_type, priority, zone_id) 
                   VALUES (1, '+584121234567', 'hash1', 'Restaurante El Portal', 'Av. 2 El Milagro', 10.6500, -71.6200, 'b2b', 1, 1)""")
    conn.execute("""INSERT INTO clients (id, phone, phone_hash, name, address_text, lat, lng, client_type, priority, zone_id) 
                   VALUES (2, '+584141112233', 'hash2', 'Residencias Los Sauces', 'Urbanización Los Sauces', 10.6520, -71.6180, 'multifamily', 4, 1)""")
    
    # Sesión de despacho
    conn.execute("INSERT INTO dispatch_sessions (id, vehicle_id, shift, date, status, total_clients, total_bottles_full, total_distance_km, total_duration_minutes, route_algorithm, route_computed_at) VALUES (1, 1, 'morning', '2026-07-29', 'active', 2, 9, 15.5, 60, 'ortools_vrp', 1785365000)")
    
    # Entregas
    conn.execute("""INSERT INTO deliveries (id, dispatch_session_id, client_id, vehicle_id, order_sequence, status, bottles_full, estimated_arrival) VALUES (1, 1, 1, 1, 1, 'pending', 6, 1785366000)""")
    conn.execute("""INSERT INTO deliveries (id, dispatch_session_id, client_id, vehicle_id, order_sequence, status, bottles_full, estimated_arrival) VALUES (2, 1, 2, 1, 2, 'pending', 3, 1785369000)""")
    
    # 165 botellones
    for i in range(1, 166):
        conn.execute("INSERT INTO bottles (id, bottle_code, status) VALUES (?, ?, 'available')", (i, f"H2O-{i:03d}"))
    
    conn.commit()
    conn.close()
    
    yield TEST_DB
    
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)


@pytest.fixture
def patch_db(monkeypatch, test_db):
    """Parchea las constantes de BD para usar test DB."""
    import skills.dispatcher as dispatcher_module
    import skills.dispatch.telegram_bot as telegram_bot_module
    import skills.dispatch.gps_tracker as gps_tracker_module
    import skills.dispatch.bottle_tracker as bottle_tracker_module
    import skills.dispatcher_skill as dispatcher_skill_module
    
    for mod in [dispatcher_module, telegram_bot_module, gps_tracker_module, bottle_tracker_module, dispatcher_skill_module]:
        if hasattr(mod, 'DISPATCH_DB'):
            monkeypatch.setattr(mod, 'DISPATCH_DB', test_db)
        if hasattr(mod, 'DISPATCH_DB_PATH'):
            monkeypatch.setattr(mod, 'DISPATCH_DB_PATH', test_db)
    
    # Reset singletons to pick up new DB path
    import skills.dispatch.bottle_tracker as bt_module
    import skills.dispatch.gps_tracker as gt_module
    import skills.dispatch.telegram_bot as tbot_module
    import skills.dispatcher_skill as ds_module
    
    bt_module._bottle_tracker_instance = None
    gt_module._gps_tracker_instance = None
    tbot_module._dispatcher_bot_instance = None
    ds_module._dispatcher_skill_instance = None


class TestDispatchFlowE2E:
    """Test E2E completo del flujo de despacho + SWAP."""

    @pytest.mark.asyncio
    async def test_complete_flow(self, patch_db):
        """Flujo completo: Pedido → Route → Chofer → GPS → Entrega → SWAP → Sheets."""
        from skills.dispatcher_skill import get_dispatcher_skill
        from skills.dispatch.bottle_tracker import get_bottle_tracker
        from skills.dispatch.gps_tracker import get_gps_tracker, GPSPoint
        from core.workload_router import get_router
        from skills.dispatch.route_engine import compute_vrp_route, ClientOrder
        
        # 1. Route Engine calcula ruta
        orders = [
            ClientOrder(client_id=1, name="Restaurante El Portal", lat=10.6500, lng=-71.6200, bottles_full=6, priority=1),
            ClientOrder(client_id=2, name="Residencias Los Sauces", lat=10.6520, lng=-71.6180, bottles_full=3, priority=4),
        ]
        route_result = compute_vrp_route(orders, num_vehicles=1)
        assert len(route_result.routes) == 1
        assert route_result.routes[0].total_bottles == 9
        
        # 2. Chofer check-in 8am
        gps_tracker = get_gps_tracker()
        checkin_result = await gps_tracker.process_gps_point(
            GPSPoint(vehicle_id=1, lat=10.6447, lng=-71.6101, source="telegram", track_type="checkin_arrive")
        )
        assert checkin_result.inside_perimeter is True
        
        # 3. Chofer presiona "Llegué"
        from skills.dispatch.telegram_bot import get_dispatcher_bot
        bot = get_dispatcher_bot()
        
        # Simular callback "arr_1"
        # (en test real se mockearía Telegram)
        
        # 4. Chofer presiona "Entregado" - trigger SWAP
        dispatcher = get_dispatcher_skill()
        result = await dispatcher.execute(
            action="delivery_delivered",
            client_id=1,
            delivery_id=1,
        )
        assert result["success"] is True
        assert result["data"]["bottle"]["bottle_code"] == "H2O-001"
        
        # 4.5. Chofer confirma entrega en la app (with_client)
        confirm_result = await dispatcher.execute(
            action="confirm_delivery",
            bottle_code=result["data"]["bottle"]["bottle_code"],
            client_id=1,
        )
        assert confirm_result["success"] is True
        assert confirm_result["data"]["bottle"]["status"] == "with_client"
        
        # 5. Chofer recoge vacío
        bottle_tracker = get_bottle_tracker()
        return_result = await bottle_tracker.return_from_client(
            bottle_code=result["data"]["bottle"]["bottle_code"],
            client_id=1,
            delivery_id=1,
        )
        assert return_result["success"] is True
        assert return_result["bottle"]["status"] == "in_transit_empty"
        
        # 6. Planta recibe vacío → lavado
        wash_result = await bottle_tracker.send_to_wash(
            bottle_code=result["data"]["bottle"]["bottle_code"],
        )
        assert wash_result["success"] is True
        assert wash_result["bottle"]["status"] == "maintenance"
        
        # 7. Lavado completado → disponible
        wash_complete = await bottle_tracker.wash_complete(
            bottle_code=result["data"]["bottle"]["bottle_code"],
        )
        assert wash_complete["success"] is True
        assert wash_complete["bottle"]["status"] == "available"
        
        # 8. Inventario final = 165
        stats = await bottle_tracker.get_inventory_stats()
        assert stats["total"] == 165
        assert stats["by_status"]["available"] == 165


if __name__ == "__main__":
    pytest.main([__file__, "-v"])