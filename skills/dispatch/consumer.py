#!/usr/bin/env python3
"""
============================================================================
Dispatch Queue Consumer — Procesa pedidos pending en tiempo real
Estación H2O · Maracaibo, Venezuela
============================================================================

Consumer que lee dispatch_queue (pedidos pending) de conversations.db,
los asigna a choferes/vehículos y crea deliveries en dispatch.db.

Uso:
    - Cron cada 15 min: python skills/dispatch/consumer.py
    - Endpoint: POST /dispatch/process-queue
    - Llamada directa: await consume_pending_orders()

Diferencia con run_route_planner.py (7:45am):
- Este es INCREMENTAL: procesa pedidos que llegan durante el día
- Asigna a chofer con menos carga actual (no VRP completo)
- Notificación inmediata a chofer
- Marca pedidos como 'enviado' en dispatch_queue
"""

import asyncio
import sys
import os
import sqlite3
import logging
import httpx
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Optional

# Cargar .env
env_path = Path("/mnt/ssd_trabajo/hermes-agent/config/.env")
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

sys.path.insert(0, "/mnt/ssd_trabajo/hermes-agent")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("dispatch_consumer")

CARACAS_TZ = timezone(timedelta(hours=-4))
CONV_DB = os.getenv("SQLITE_PATH", "/mnt/ssd_trabajo/hermes-agent/data/conversations.db")
DISPATCH_DB = os.getenv("DISPATCH_DB_PATH", "/mnt/ssd_trabajo/hermes-agent/data/dispatch.db")
DEPOT_LAT = 10.6447
DEPOT_LNG = -71.6101
OPERATION_RADIUS_KM = 13.0


def _get_conv_db() -> sqlite3.Connection:
    conn = sqlite3.connect(CONV_DB)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


def _get_dispatch_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DISPATCH_DB)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


def _haversine(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Distancia en km entre dos puntos."""
    from math import radians, sin, cos, sqrt, atan2
    R = 6371.0
    dlat = radians(lat2 - lat1)
    dlng = radians(lng2 - lng1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlng / 2) ** 2
    return 2 * R * atan2(sqrt(a), sqrt(1 - a))


def _fetch_pending_orders(limit: int = 20) -> list[Any]:
    """Lee pedidos pending de dispatch_queue en conversations.db."""
    conn = _get_conv_db()
    rows = conn.execute(
        """SELECT id, cliente_nombre, cliente_telefono, producto_desc,
                  total_eur, metodo_pago, gps_lat, gps_lng, direccion
           FROM dispatch_queue WHERE estado = 'pending'
           ORDER BY creado_at ASC LIMIT ?""",
        (limit,)
    ).fetchall()
    conn.close()
    return rows


def _find_or_create_client(conn: sqlite3.Connection, name: str, phone: str,
                           lat: float, lng: float, address: str) -> int:
    """Busca client por phone, o lo crea si no existe. Retorna client_id."""
    import hashlib
    phone_hash = hashlib.sha256(phone.encode()).hexdigest()[:16] if phone else ""

    row = conn.execute(
        "SELECT id FROM clients WHERE phone = ?", (phone,)
    ).fetchone()
    if row:
        if lat is not None and lng is not None:
            conn.execute(
                "UPDATE clients SET lat=?, lng=?, address_text=?, updated_at=? WHERE id=?",
                (lat, lng, address, datetime.now(CARACAS_TZ).timestamp(), row["id"]),
            )
        return row["id"]

    conn.execute(
        """INSERT INTO clients (phone, phone_hash, name, address_text, lat, lng,
           client_type, priority, active, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, 'retail', 5, 1, ?, ?)""",
        (phone, phone_hash, name or phone, address, lat, lng,
         datetime.now(CARACAS_TZ).timestamp(), datetime.now(CARACAS_TZ).timestamp()),
    )
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def _get_active_vehicles_with_load(conn: sqlite3.Connection) -> list[dict]:
    """Retorna vehicles activos con su carga actual (deliveries pending)."""
    today_start = datetime.now(CARACAS_TZ).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    today_end = today_start + 86400

    # Query vehicles with pending deliveries count, using date filter for today's sessions
    # but also include vehicles with no sessions for today (active vehicles)
    rows = conn.execute(
        """SELECT v.id, v.name, v.operator_name, v.max_full_bottles,
                  COALESCE(SUM(CASE WHEN d.status = 'pending' THEN 1 ELSE 0 END), 0) as pending_deliveries
           FROM vehicles v
           LEFT JOIN deliveries d ON d.vehicle_id = v.id AND d.status = 'pending'
           LEFT JOIN dispatch_sessions ds ON ds.id = d.dispatch_session_id
           WHERE v.active = 1
           GROUP BY v.id, v.name, v.operator_name, v.max_full_bottles
           ORDER BY pending_deliveries ASC, v.id ASC"""
    ).fetchall()

    return [
        {
            "id": r["id"],
            "name": r["name"],
            "operator_name": r["operator_name"],
            "max_full_bottles": r["max_full_bottles"],
            "pending_deliveries": r["pending_deliveries"],
        }
        for r in rows
    ]


def _extract_bottles(producto_desc: str) -> int:
    """Extrae cantidad de botellones del producto_desc (ej '3 botellones de agua')."""
    import re
    m = re.search(r"(\d+)\s*botell", producto_desc or "", re.IGNORECASE)
    return int(m.group(1)) if m else 1


async def _notify_chofer_direct(
    vehicle_id: int,
    operator_name: str,
    client_name: str,
    client_phone: str,
    bottles_full: int,
    lat: float,
    lng: float,
    address: str,
    total_eur: float,
    total_bs: float,
    metodo_pago: str,
) -> bool:
    """Envía notificación directa a chofer via endpoint /dispatch/notify-driver con retry."""
    max_retries = 3
    base_delay = 0.5
    
    for attempt in range(1, max_retries + 1):
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    "http://localhost:8000/dispatch/notify/driver",
                    json={
                        "vehicle_id": vehicle_id,
                        "client_name": client_name,
                        "client_phone": client_phone,
                        "bottles_full": bottles_full,
                        "lat": lat,
                        "lng": lng,
                        "address": address,
                        "total_eur": total_eur,
                        "total_bs": total_bs,
                        "metodo_pago": metodo_pago,
                    }
                )
                if resp.status_code == 200:
                    return True
                else:
                    logger.warning("Notificación chofer status %d (intento %d/%d)", resp.status_code, attempt, max_retries)
        except Exception as e:
            logger.warning("Error notificando chofer %s (intento %d/%d): %s", operator_name, attempt, max_retries, e)
        
        if attempt < max_retries:
            await asyncio.sleep(base_delay * (2 ** (attempt - 1)))
    
    logger.error("❌ Notificación a chofer %s falló tras %d intentos", operator_name, max_retries)
    return False


async def consume_pending_orders(max_orders: int = 20) -> dict[str, Any]:
    """
    Procesa pedidos pending de dispatch_queue:
    1. Lee pedidos pending
    2. Para cada pedido: busca/crea client, asigna a vehicle con menos carga
    3. Crea delivery en dispatch.db (sin dispatch_session si es pedido individual)
    4. Notifica chofer via /dispatch/notify-driver
    5. Marca pedido como 'enviado' en dispatch_queue

    Retorna: dict con stats {processed, notified, errors}
    """
    stats = {"processed": 0, "notified": 0, "errors": 0, "skipped": 0}

    pending = _fetch_pending_orders(limit=max_orders)
    if not pending:
        logger.info("No hay pedidos pending en dispatch_queue")
        return stats

    logger.info("Procesando %d pedidos pending", len(pending))

    for order in pending:
        try:
            order_id = order["id"]
            client_name = order["cliente_nombre"] or ""
            client_phone = order["cliente_telefono"] or ""
            producto_desc = order["producto_desc"] or ""
            total_eur = order["total_eur"] or 0.0
            metodo_pago = order["metodo_pago"] or ""
            lat = order["gps_lat"]
            lng = order["gps_lng"]
            address = order["direccion"] or ""

            # Fallback GPS si no viene
            if lat is None or lng is None:
                logger.warning("Pedido %d sin GPS — usando depot como fallback", order_id)
                lat, lng = DEPOT_LAT, DEPOT_LNG

            # Validar perímetro de operación
            if _haversine(lat, lng, DEPOT_LAT, DEPOT_LNG) > OPERATION_RADIUS_KM:
                logger.warning("Pedido %d fuera de perímetro (%.1f km) — skip", order_id, _haversine(lat, lng, DEPOT_LAT, DEPOT_LNG))
                stats["skipped"] += 1
                _mark_order_status(order_id, "fuera_perimetro")
                continue

            bottles = _extract_bottles(producto_desc)

            # Buscar/crear client en dispatch.db
            dispatch_conn = _get_dispatch_db()
            client_id = _find_or_create_client(dispatch_conn, client_name, client_phone, lat, lng, address)

            # Asignar a vehicle con menos carga
            vehicles = _get_active_vehicles_with_load(dispatch_conn)
            if not vehicles:
                logger.warning("No hay vehicles activos — pedido %d queda pending", order_id)
                dispatch_conn.close()
                stats["skipped"] += 1
                continue

            vehicle = vehicles[0]  # El que tiene menos pending_deliveries
            vehicle_id = vehicle["id"]
            operator_name = vehicle["operator_name"] or f"Vehículo {vehicle_id}"
            max_capacity = vehicle["max_full_bottles"]

            # Verificar capacidad
            if vehicle["pending_deliveries"] >= 10:  # Límite razonable
                logger.warning("Vehicle %s saturado (%d pendientes) — skip", operator_name, vehicle["pending_deliveries"])
                dispatch_conn.close()
                stats["skipped"] += 1
                continue

            # Crear delivery en dispatch.db
            today_str = datetime.now(CARACAS_TZ).strftime("%Y-%m-%d")
            now_ts = datetime.now(CARACAS_TZ).timestamp()

            # Crear dispatch_session simple para este pedido (o usar una existente 'morning')
            session_row = dispatch_conn.execute(
                """SELECT id FROM dispatch_sessions
                   WHERE vehicle_id = ? AND date = ? AND status IN ('planning', 'in_progress')
                   ORDER BY created_at DESC LIMIT 1""",
                (vehicle_id, today_str)
            ).fetchone()

            if session_row:
                session_id = session_row["id"]
            else:
                # Crear nueva session para este vehicle
                dispatch_conn.execute(
                    """INSERT INTO dispatch_sessions
                       (vehicle_id, shift, date, status, total_clients, total_bottles_full,
                        total_distance_km, total_duration_minutes, route_algorithm,
                        route_computed_at, created_at)
                       VALUES (?, 'realtime', ?, 'in_progress', 1, ?, 0, 0, 'realtime', ?, ?)""",
                    (vehicle_id, today_str, bottles, now_ts, now_ts)
                )
                session_id = dispatch_conn.execute("SELECT last_insert_rowid()").fetchone()[0]

            # Crear delivery
            dispatch_conn.execute(
                """INSERT INTO deliveries
                   (dispatch_session_id, client_id, vehicle_id, order_sequence,
                    status, bottles_full, created_at, updated_at)
                   VALUES (?, ?, ?, 1, 'pending', ?, ?, ?)""",
                (session_id, client_id, vehicle_id, bottles, now_ts, now_ts)
            )
            delivery_id = dispatch_conn.execute("SELECT last_insert_rowid()").fetchone()[0]

            dispatch_conn.commit()
            dispatch_conn.close()

            # Notificar chofer
            total_bs = total_eur * 36.5  # tasa aproximada
            notified = await _notify_chofer_direct(
                vehicle_id=vehicle_id,
                operator_name=operator_name,
                client_name=client_name,
                client_phone=client_phone,
                bottles_full=bottles,
                lat=lat,
                lng=lng,
                address=address,
                total_eur=total_eur,
                total_bs=total_bs,
                metodo_pago=metodo_pago,
            )

            if notified:
                stats["notified"] += 1

            # Marcar pedido como 'enviado' en dispatch_queue
            conv_conn = _get_conv_db()
            # Check if delivery_id column exists, if not use a different approach
            try:
                conv_conn.execute(
                    "UPDATE dispatch_queue SET estado='enviado', enviado_at=?, delivery_id=? WHERE id=?",
                    (datetime.now(CARACAS_TZ).isoformat(), delivery_id, order_id)
                )
            except sqlite3.OperationalError:
                # Column delivery_id doesn't exist, update without it
                conv_conn.execute(
                    "UPDATE dispatch_queue SET estado='enviado', enviado_at=? WHERE id=?",
                    (datetime.now(CARACAS_TZ).isoformat(), order_id)
                )
            conv_conn.commit()
            conv_conn.close()

            stats["processed"] += 1
            logger.info("Pedido %d → vehicle %s (%s), delivery #%d", order_id, vehicle["name"], operator_name, delivery_id)

        except Exception as e:
            logger.exception("Error procesando pedido %s: %s", order["id"] if "id" in order.keys() else "?", e)
            stats["errors"] += 1

    logger.info("Consumer stats: processed=%d notified=%d errors=%d skipped=%d",
                stats["processed"], stats["notified"], stats["errors"], stats["skipped"])
    return stats


def _mark_order_status(order_id: int, status: str) -> None:
    """Marca un pedido con estado específico en dispatch_queue."""
    conv_conn = _get_conv_db()
    conv_conn.execute(
        "UPDATE dispatch_queue SET estado=?, enviado_at=? WHERE id=?",
        (status, datetime.now(CARACAS_TZ).isoformat(), order_id)
    )
    conv_conn.commit()
    conv_conn.close()


# ============================================================================
# FastAPI Endpoint
# ============================================================================
async def process_queue_endpoint(max_orders: int = 20) -> dict[str, Any]:
    """Endpoint FastAPI: POST /dispatch/process-queue"""
    return await consume_pending_orders(max_orders=max_orders)


if __name__ == "__main__":
    # Ejecución standalone (cron)
    result = asyncio.run(consume_pending_orders(max_orders=20))
    print(f"Consumer result: {result}")
    sys.exit(0 if result["errors"] == 0 else 1)