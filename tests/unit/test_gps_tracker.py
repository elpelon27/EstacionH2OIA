"""
============================================================================
Unit Tests — GPSTracker (geofencing, heatmap, BD)
Estación H2O · Maracaibo, Venezuela
============================================================================
"""

import os
import sqlite3
import sys

import pytest

sys.path.insert(0, "/mnt/ssd_trabajo/hermes-agent")

TEST_DB = "/tmp/test_gps_tracker.db"
os.environ["DISPATCH_DB_PATH"] = TEST_DB


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
            active INTEGER DEFAULT 1,
            created_at REAL NOT NULL DEFAULT (strftime('%s','now'))
        )
    """)
    conn.execute("""
        CREATE TABLE zones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            center_lat REAL,
            center_lng REAL,
            radius_km REAL,
            color TEXT DEFAULT '#3B82F6',
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
    conn.execute(
        "INSERT INTO vehicles (id, name, operator_name, active) VALUES (1, 'Triciclo 1', 'YORDANIS', 1)"
    )
    conn.execute(
        "INSERT INTO zones (id, name, center_lat, center_lng, radius_km) VALUES (1, 'Bella Vista', 10.6500, -71.6200, 3.0)"
    )
    conn.execute(
        "INSERT INTO zones (id, name, center_lat, center_lng, radius_km) VALUES (2, 'Las Delicias', 10.6400, -71.6150, 2.5)"
    )
    conn.commit()
    conn.close()

    yield TEST_DB

    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)


@pytest.fixture(autouse=True)
def patch_gps_db(test_db):
    """Parchea DISPATCH_DB en el módulo gps_tracker."""
    import skills.dispatch.gps_tracker as gps_module

    gps_module.DISPATCH_DB = test_db
    gps_module._gps_tracker_instance = None
    yield
    gps_module._gps_tracker_instance = None


from skills.dispatch.gps_tracker import (
    GeofenceResult,
    GPSPoint,
    get_gps_tracker,
)


class TestGPSTracker:
    """Tests del GPSTracker."""

    def test_singleton(self):
        t1 = get_gps_tracker()
        t2 = get_gps_tracker()
        assert t1 is t2

    @pytest.mark.asyncio
    async def test_process_gps_point_inside_perimeter(self):
        tracker = get_gps_tracker()
        point = GPSPoint(vehicle_id=1, lat=10.6447, lng=-71.6101, source="tasker")  # depot
        result = await tracker.process_gps_point(point)

        assert isinstance(result, GeofenceResult)
        assert result.inside_perimeter is True
        assert result.distance_to_depot_km < 0.1
        assert result.alert_triggered is False

    @pytest.mark.asyncio
    async def test_process_gps_point_outside_perimeter(self):
        tracker = get_gps_tracker()
        point = GPSPoint(vehicle_id=1, lat=10.5000, lng=-66.9000, source="tasker")  # Caracas
        result = await tracker.process_gps_point(point)

        assert result.inside_perimeter is False
        assert result.distance_to_depot_km > 500  # Real distance ~515km
        assert result.alert_triggered is True  # Primera vez → alerta
        assert "Fuera de perímetro" in result.alert_message

    @pytest.mark.asyncio
    async def test_cooldown_alerts(self):
        """Segunda alerta en <5min no dispara."""
        tracker = get_gps_tracker()
        point = GPSPoint(vehicle_id=1, lat=10.5000, lng=-66.9000, source="tasker")

        r1 = await tracker.process_gps_point(point)
        assert r1.alert_triggered is True

        r2 = await tracker.process_gps_point(point)
        assert r2.alert_triggered is False  # Cooldown

    @pytest.mark.asyncio
    async def test_process_gps_point_bella_vista_zone(self):
        """Punto en Bella Vista → zona 1."""
        tracker = get_gps_tracker()
        point = GPSPoint(vehicle_id=1, lat=10.6500, lng=-71.6200, source="telegram")
        result = await tracker.process_gps_point(point)

        assert result.inside_perimeter is True
        assert result.nearest_zone_id == 1
        assert 1 in result.zone_ids

    @pytest.mark.asyncio
    async def test_get_heatmap_data(self):
        tracker = get_gps_tracker()

        points = [
            GPSPoint(vehicle_id=1, lat=10.6500, lng=-71.6200, source="tasker"),
            GPSPoint(vehicle_id=1, lat=10.6501, lng=-71.6201, source="tasker"),
            GPSPoint(vehicle_id=1, lat=10.6500, lng=-71.6200, source="telegram"),
        ]
        for p in points:
            await tracker.process_gps_point(p)

        heatmap = tracker.get_heatmap_data(hours_back=1)
        assert len(heatmap) >= 1
        assert all("passes" in h for h in heatmap)
        assert all("zone_id" in h for h in heatmap)

    @pytest.mark.asyncio
    async def test_get_vehicle_timeline(self):
        tracker = get_gps_tracker()

        points = [
            GPSPoint(vehicle_id=1, lat=10.6500, lng=-71.6200, source="tasker"),
            GPSPoint(vehicle_id=1, lat=10.6510, lng=-71.6210, source="tasker"),
        ]
        for p in points:
            await tracker.process_gps_point(p)

        timeline = tracker.get_vehicle_timeline(vehicle_id=1, hours_back=1)
        assert len(timeline) == 2
        assert timeline[0]["lat"] == 10.6500
        assert timeline[1]["lat"] == 10.6510

    @pytest.mark.asyncio
    async def test_get_geofence_events(self):
        tracker = get_gps_tracker()

        point = GPSPoint(vehicle_id=1, lat=10.5000, lng=-66.9000, source="tasker")
        await tracker.process_gps_point(point)

        events = tracker.get_geofence_events(hours_back=1)
        assert len(events) == 1
        assert events[0]["vehicle_id"] == 1
        assert events[0]["event_type"] == "exit"

    @pytest.mark.asyncio
    async def test_gps_saved_to_db(self):
        tracker = get_gps_tracker()
        point = GPSPoint(
            vehicle_id=1,
            lat=10.6500,
            lng=-71.6200,
            accuracy=5.0,
            speed_kmh=20.0,
            source="tasker",
            track_type="periodic",
        )
        await tracker.process_gps_point(point)

        conn = sqlite3.connect(TEST_DB)
        row = conn.execute("SELECT * FROM gps_tracks WHERE vehicle_id = 1").fetchone()
        conn.close()

        assert row is not None
        assert row[2] == 10.6500  # lat
        assert row[3] == -71.6200  # lng
        assert row[4] == 5.0  # accuracy
        assert row[5] == 20.0  # speed
        assert row[6] == "tasker"  # source


class TestGPSPointDataclass:
    def test_gps_point_defaults(self):
        p = GPSPoint(vehicle_id=1, lat=10.0, lng=-71.0)
        assert p.accuracy is None
        assert p.speed_kmh is None
        assert p.source == "tasker"
        assert p.delivery_id is None
        assert p.track_type == "periodic"

    def test_gps_point_all_fields(self):
        p = GPSPoint(
            vehicle_id=2,
            lat=10.5,
            lng=-71.5,
            accuracy=3.0,
            speed_kmh=15.0,
            source="telegram",
            delivery_id=5,
            track_type="checkin_arrive",
        )
        assert p.vehicle_id == 2
        assert p.track_type == "checkin_arrive"


class TestGeofenceResult:
    def test_result_fields(self):
        r = GeofenceResult(
            inside_perimeter=True,
            nearest_zone_id=1,
            zone_ids=[1, 2],
            distance_to_depot_km=2.5,
            alert_triggered=False,
            alert_message="",
        )
        assert r.inside_perimeter is True
        assert r.nearest_zone_id == 1
        assert r.zone_ids == [1, 2]
        assert r.distance_to_depot_km == 2.5
        assert r.alert_triggered is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
