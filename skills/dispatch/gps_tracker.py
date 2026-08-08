"""
============================================================================
GPS Tracker — Procesamiento de posiciones GPS (Tasker + Telegram)
Estación H2O · Maracaibo, Venezuela
============================================================================

Procesa GPS de dos fuentes:
1. Tasker (Android) → POST /dispatch/gps cada 5 min (automático, background)
2. Telegram check-in → location message (manual, al llegar a cliente)

Almacena en gps_tracks (mapa de calor futuro) + geofence_events (alertas).

Geofencing: perímetro 13km desde depot (Hotel Kristoff) + 5 zonas Maracaibo.
Alerta si sale del perímetro (cooldown 5 min para no spamear).
"""

import logging
import sqlite3
import time
from dataclasses import dataclass
from typing import Any

from skills.dispatch.route_engine import (
    check_zone_membership,
    find_nearest_zone,
    haversine,
)

logger = logging.getLogger("dispatch.gps_tracker")

# Config
DISPATCH_DB = "/mnt/ssd_trabajo/hermes-agent/data/dispatch.db"
DEPOT_LAT = 10.6447
DEPOT_LNG = -71.6101
OPERATION_RADIUS_KM = 13.0
GEOFENCE_ALERT_COOLDOWN_SECONDS = 300  # 5 min entre alertas del mismo vehículo


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DISPATCH_DB)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


def now_epoch() -> float:
    return time.time()


@dataclass
class GPSPoint:
    """Punto GPS normalizado para procesamiento."""

    vehicle_id: int
    lat: float
    lng: float
    accuracy: float | None = None
    speed_kmh: float | None = None
    source: str = "tasker"  # "tasker" | "telegram" | "manual"
    delivery_id: int | None = None
    track_type: str = "periodic"  # "periodic" | "checkin_arrive" | "checkin_depart"


@dataclass
class GeofenceResult:
    """Resultado de verificación de geofencing."""

    inside_perimeter: bool
    nearest_zone_id: int | None
    zone_ids: list[int]
    distance_to_depot_km: float
    alert_triggered: bool
    alert_message: str = ""


class GPSTracker:
    """Procesador de GPS para Tasker + Telegram."""

    def __init__(self) -> None:
        self._last_geofence_alert: dict[int, float] = {}  # vehicle_id -> last_alert_epoch

    # ----------------------------------------------------------------------
    # API pública
    # ----------------------------------------------------------------------

    async def process_gps_point(self, point: GPSPoint) -> GeofenceResult:
        """
        Procesa un punto GPS: guarda en BD, verifica geofencing, retorna resultado.
        Llamado desde:
        - FastAPI endpoint /dispatch/gps (Tasker)
        - Telegram location handler (check-in llegada)
        - DispatcherSkill.execute(action="record_gps")
        """
        # 1. Guardar punto GPS (DATOS = ORO para mapa de calor)
        self._save_gps_track(point)

        # 2. Verificar geofencing
        result = self._check_geofence(point)

        # 3. Si fuera de perímetro y pasó cooldown → alertar
        if not result.inside_perimeter and result.alert_triggered:
            self._save_geofence_event(point.vehicle_id, "exit", point.lat, point.lng)
            logger.warning(
                "🚨 GEOFENCE ALERT: vehicle=%d lat=%.6f lng=%.6f dist=%.2fkm",
                point.vehicle_id,
                point.lat,
                point.lng,
                result.distance_to_depot_km,
            )

        return result

    async def process_batch(self, points: list[GPSPoint]) -> list[GeofenceResult]:
        """Procesa lote de puntos (útil si Tasker envía buffer)."""
        results = []
        for p in points:
            results.append(await self.process_gps_point(p))
        return results

    def get_heatmap_data(
        self,
        hours_back: int = 24,
        vehicle_id: int | None = None,
        min_points: int = 1,
    ) -> list[dict[str, Any]]:
        """
        Retorna datos agregados para mapa de calor (Google Sheets Mapa_Calor).
        Agrupa por zona/sector, cuenta pasadas.
        """
        conn = get_db()
        cutoff = now_epoch() - (hours_back * 3600)

        where = "WHERE created_at >= ?"
        params: list[Any] = [cutoff]
        if vehicle_id:
            where += " AND vehicle_id = ?"
            params.append(vehicle_id)

        rows = conn.execute(
            f"""
            SELECT
                vehicle_id,
                lat,
                lng,
                COUNT(*) as passes,
                MAX(created_at) as last_seen
            FROM gps_tracks
            {where}
            GROUP BY vehicle_id, ROUND(lat, 4), ROUND(lng, 4)
            HAVING COUNT(*) >= ?
            ORDER BY passes DESC
            """,
            params + [min_points],
        ).fetchall()
        conn.close()

        # Enriquecer con zona más cercana
        enriched = []
        for r in rows:
            zone_id = find_nearest_zone(r["lat"], r["lng"], self._get_zones())
            enriched.append(
                {
                    "vehicle_id": r["vehicle_id"],
                    "lat": r["lat"],
                    "lng": r["lng"],
                    "passes": r["passes"],
                    "last_seen": r["last_seen"],
                    "zone_id": zone_id,
                }
            )
        return enriched

    def get_vehicle_timeline(
        self,
        vehicle_id: int,
        hours_back: int = 24,
    ) -> list[dict[str, Any]]:
        """Timeline de puntos GPS de un vehículo (para debugging/playback)."""
        conn = get_db()
        cutoff = now_epoch() - (hours_back * 3600)
        rows = conn.execute(
            """
            SELECT lat, lng, accuracy, speed_kmh, source, track_type, created_at
            FROM gps_tracks
            WHERE vehicle_id = ? AND created_at >= ?
            ORDER BY created_at ASC
            """,
            (vehicle_id, cutoff),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_geofence_events(
        self,
        hours_back: int = 24,
        vehicle_id: int | None = None,
    ) -> list[dict[str, Any]]:
        """Eventos de salida de perímetro."""
        conn = get_db()
        cutoff = now_epoch() - (hours_back * 3600)
        where = "WHERE created_at >= ?"
        params: list[Any] = [cutoff]
        if vehicle_id:
            where += " AND vehicle_id = ?"
            params.append(vehicle_id)
        rows = conn.execute(
            f"""
            SELECT vehicle_id, event_type, zone_id, lat, lng, created_at
            FROM geofence_events
            {where}
            ORDER BY created_at DESC
            """,
            params,
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # ----------------------------------------------------------------------
    # Internos
    # ----------------------------------------------------------------------

    def _save_gps_track(self, point: GPSPoint) -> None:
        conn = get_db()
        conn.execute(
            """
            INSERT INTO gps_tracks
            (
                vehicle_id,
                lat,
                lng,
                accuracy,
                speed_kmh,
                source,
                delivery_id,
                track_type,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                point.vehicle_id,
                point.lat,
                point.lng,
                point.accuracy,
                point.speed_kmh,
                point.source,
                point.delivery_id,
                point.track_type,
                now_epoch(),
            ),
        )
        conn.commit()
        conn.close()

    def _check_geofence(self, point: GPSPoint) -> GeofenceResult:
        # Distancia al depot
        dist_depot = haversine(DEPOT_LAT, DEPOT_LNG, point.lat, point.lng)
        inside_perimeter = dist_depot <= OPERATION_RADIUS_KM

        # Zonas
        zones = self._get_zones()
        zone_ids = check_zone_membership(point.lat, point.lng, zones)
        nearest_zone = find_nearest_zone(point.lat, point.lng, zones)

        # Cooldown de alerta
        last_alert = self._last_geofence_alert.get(point.vehicle_id, 0)
        alert_triggered = (
            not inside_perimeter and (now_epoch() - last_alert) >= GEOFENCE_ALERT_COOLDOWN_SECONDS
        )
        if alert_triggered:
            self._last_geofence_alert[point.vehicle_id] = now_epoch()

        msg = ""
        if not inside_perimeter:
            msg = f"⚠️ Fuera de perímetro ({dist_depot:.1f}km > {OPERATION_RADIUS_KM}km)"

        return GeofenceResult(
            inside_perimeter=inside_perimeter,
            nearest_zone_id=nearest_zone,
            zone_ids=zone_ids,
            distance_to_depot_km=round(dist_depot, 2),
            alert_triggered=alert_triggered,
            alert_message=msg,
        )

    def _save_geofence_event(
        self,
        vehicle_id: int,
        event_type: str,
        lat: float,
        lng: float,
        zone_id: int | None = None,
    ) -> None:
        conn = get_db()
        conn.execute(
            """
            INSERT INTO geofence_events (vehicle_id, event_type, zone_id, lat, lng, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (vehicle_id, event_type, zone_id, lat, lng, now_epoch()),
        )
        conn.commit()
        conn.close()

    def _get_zones(self) -> list[dict[str, Any]]:
        conn = get_db()
        rows = conn.execute(
            "SELECT id, name, center_lat, center_lng, radius_km FROM zones"
        ).fetchall()
        conn.close()
        return [
            {
                "id": r["id"],
                "name": r["name"],
                "center_lat": r["center_lat"],
                "center_lng": r["center_lng"],
                "radius_km": r["radius_km"],
            }
            for r in rows
        ]


# ============================================================================
# Factory / Singleton
# ============================================================================

_gps_tracker_instance: GPSTracker | None = None


def get_gps_tracker() -> GPSTracker:
    """Obtiene instancia singleton del GPSTracker."""
    global _gps_tracker_instance
    if _gps_tracker_instance is None:
        _gps_tracker_instance = GPSTracker()
    return _gps_tracker_instance


# ============================================================================
# Test rápido
# ============================================================================

if __name__ == "__main__":
    import asyncio

    async def test() -> None:
        tracker = get_gps_tracker()

        # Punto dentro (Bella Vista)
        p1 = GPSPoint(vehicle_id=1, lat=10.6500, lng=-71.6200, source="tasker")
        r1 = await tracker.process_gps_point(p1)
        msg1 = (
            f"Bella Vista: inside={r1.inside_perimeter}, "
            f"zone={r1.nearest_zone_id}, dist={r1.distance_to_depot_km}km"
        )
        print(msg1)

        # Punto fuera (Caracas ~400km)
        p2 = GPSPoint(vehicle_id=1, lat=10.5000, lng=-66.9000, source="tasker")
        r2 = await tracker.process_gps_point(p2)
        msg2 = (
            f"Caracas: inside={r2.inside_perimeter}, "
            f"alert={r2.alert_triggered}, dist={r2.distance_to_depot_km}km"
        )
        print(msg2)

        # Heatmap
        hm = tracker.get_heatmap_data(hours_back=168)  # 7 días
        print(f"Heatmap points: {len(hm)}")

    asyncio.run(test())
