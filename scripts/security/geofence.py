#!/usr/bin/env python3
"""Geocerca POLIGONAL (FASE 2).

Reglas del Líder:
- Polígono (no círculo) en GeoJSON, modificable por referencias del Líder.
- Cliente fuera de zona: "no atendemos su zona" + número a future_zone_customers.
- Ubicación reenviada: aceptada (no validamos en vivo, solo que el punto esté dentro).
- Fuera de geocerca NO va al audit log (se almacena aparte).
- Algoritmo: ray casting puro (sin dependencias).
"""
import json
import sqlite3
import time
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "security.db"

MSG_FUERA_ZONA = ("Gracias por escribirnos 💧 Por ahora no atendemos tu zona. "
                  "Guardamos tu número y te avisaremos en cuanto lleguemos.")


def _conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB_PATH, timeout=30)
    c.row_factory = sqlite3.Row
    return c


def init_db():
    c = _conn()
    with c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS geofence_polygon (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            polygon_geojson TEXT NOT NULL,
            created_at REAL NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS future_zone_customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone TEXT NOT NULL,
            lat REAL,
            lng REAL,
            requested_at REAL NOT NULL,
            notified INTEGER NOT NULL DEFAULT 0
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_future_phone
            ON future_zone_customers(phone);
        """)
    c.close()


def _to_ring(polygon):
    """Acepta dict GeoJSON, lista anillo [[lng,lat],...], o str JSON. Devuelve ring."""
    if isinstance(polygon, str):
        polygon = json.loads(polygon)
    if isinstance(polygon, dict):
        polygon = polygon.get("coordinates")
    if not polygon:
        return []
    first = polygon[0]
    if isinstance(first, (int, float)):  # ya es [lng, lat]
        return [(float(polygon[0]), float(polygon[1]))]
    if isinstance(first, dict):          # {"latitude":..,"longitude":..}
        return [(float(first.get("longitude", first.get("lng", 0))),
                 float(first.get("latitude", first.get("lat", 0))))]
    if isinstance(first, (list, tuple)):
        if isinstance(first[0], (list, tuple, dict)):
            # GeoJSON: multiple anillos -> tomar el exterior
            ring = polygon[0]
            if ring and isinstance(ring[0], dict):
                return [(float(q.get("longitude", q.get("lng", 0))),
                         float(q.get("latitude", q.get("lat", 0)))) for q in ring]
            return [(float(q[0]), float(q[1])) for q in ring]
        # anillo simple de [lng,lat]
        return [(float(q[0]), float(q[1])) for q in polygon]
    return []


def is_inside_polygon(lat: float, lng: float, polygon) -> bool:
    """Ray casting: True si (lat,lng) dentro del poligono (anillo exterior)."""
    pts = _to_ring(polygon)
    n = len(pts)
    if n < 3:
        return False
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = pts[i]        # (lng, lat)
        xj, yj = pts[j]
        if ((yi > lat) != (yj > lat)) and \
           (lng < (xj - xi) * (lat - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


def get_active_polygon() -> dict | None:
    """Polígono activo (id, name, geojson) o None."""
    c = _conn()
    try:
        row = c.execute(
            "SELECT id, name, polygon_geojson FROM geofence_polygon "
            "WHERE is_active=1 ORDER BY id DESC LIMIT 1").fetchone()
        return dict(row) if row else None
    finally:
        c.close()


def set_polygon(name: str, polygon_geojson, activate: bool = True) -> int:
    """Crea/actualiza el polígono de atención (referencias del Líder)."""
    init_db()
    if not isinstance(polygon_geojson, str):
        polygon_geojson = json.dumps(polygon_geojson)
    # valida que sea parseable
    json.loads(polygon_geojson)
    c = _conn()
    try:
        with c:
            if activate:
                c.execute("UPDATE geofence_polygon SET is_active=0 WHERE is_active=1")
            cur = c.execute(
                "INSERT INTO geofence_polygon(name, polygon_geojson, created_at, is_active) "
                "VALUES(?,?,?,?)", (name, polygon_geojson, time.time(), int(activate)))
            return int(cur.lastrowid or 0)
    finally:
        c.close()


def check_location(phone: str, lat: float, lng: float) -> dict:
    """Valida ubicación del cliente contra el polígono activo.

    Returns:
      status: 'ok' (dentro) | 'fuera' (fuera → mensaje + guardar) | 'sin_geocerca'
      message: mensaje a enviar si aplica
    """
    init_db()
    poly = get_active_polygon()
    if poly is None:
        # sin polígono activo: no bloquear (placeholder desactivado del Líder)
        return {"status": "sin_geocerca", "message": None}
    if is_inside_polygon(lat, lng, poly["polygon_geojson"]):
        return {"status": "ok", "message": None}
    # fuera de zona: almacenar APARTE (NO audit log) + mensaje
    c = _conn()
    try:
        with c:
            c.execute(
                """INSERT INTO future_zone_customers(phone, lat, lng, requested_at)
                   VALUES(?,?,?,?)
                   ON CONFLICT(phone) DO UPDATE SET
                     lat=excluded.lat, lng=excluded.lng,
                     requested_at=excluded.requested_at""",
                (re_digits(phone), lat, lng, time.time()))
    finally:
        c.close()
    return {"status": "fuera", "message": MSG_FUERA_ZONA}


def re_digits(s: str) -> str:
    import re
    return re.sub(r"\D", "", str(s or ""))


def future_zone_notify_pending() -> list[dict]:
    """Números fuera de zona pendientes de notificación si se expande la cobertura."""
    c = _conn()
    try:
        rows = c.execute(
            "SELECT phone, lat, lng, requested_at FROM future_zone_customers "
            "WHERE notified=0 ORDER BY requested_at").fetchall()
        return [dict(r) for r in rows]
    finally:
        c.close()
