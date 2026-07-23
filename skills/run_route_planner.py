#!/usr/bin/env python3
"""Script para cron 7:45am — planifica rutas automáticas del día.

Lee dispatch_queue (pedidos pending) de conversations.db, los convierte en
ClientOrder para el route_engine, calcula rutas VRP con OR-Tools, crea
dispatch_sessions + deliveries en dispatch.db, marca pedidos como 'enviado',
y notifica a cada chofer por Telegram con su ruta del día.

Cron: 45 7 * * * /mnt/ssd_trabajo/hermes-agent/venv/bin/python skills/run_route_planner.py
"""
import asyncio
import sys
import os
import sqlite3
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

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
logger = logging.getLogger("route_planner")

CARACAS_TZ = timezone(timedelta(hours=-4))
CONV_DB = os.getenv("SQLITE_PATH", "/mnt/ssd_trabajo/hermes-agent/data/conversations.db")
DISPATCH_DB = os.getenv("DISPATCH_DB_PATH", "/mnt/ssd_trabajo/hermes-agent/data/dispatch.db")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
# Chat ID del grupo de choferes (pendiente configurar por Líder)
TELEGRAM_DISPATCH_CHAT = os.getenv("TELEGRAM_DISPATCH_CHAT", "")


def _get_dispatch_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DISPATCH_DB)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


def _get_conv_db() -> sqlite3.Connection:
    conn = sqlite3.connect(CONV_DB)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


def _fetch_pending_orders() -> list:
    """Lee pedidos pending de dispatch_queue en conversations.db."""
    conn = _get_conv_db()
    rows = conn.execute(
        """SELECT id, cliente_nombre, cliente_telefono, producto_desc,
                  total_eur, metodo_pago, gps_lat, gps_lng, direccion
           FROM dispatch_queue WHERE estado = 'pending'
           ORDER BY creado_at ASC"""
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
        # Actualizar lat/lng si vienen del pedido
        if lat is not None and lng is not None:
            conn.execute(
                "UPDATE clients SET lat=?, lng=?, address_text=?, updated_at=? WHERE id=?",
                (lat, lng, address, datetime.now(CARACAS_TZ).timestamp(), row["id"]),
            )
        return row["id"]

    # Crear nuevo client
    conn.execute(
        """INSERT INTO clients (phone, phone_hash, name, address_text, lat, lng,
           client_type, priority, active, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, 'retail', 5, 1, ?, ?)""",
        (phone, phone_hash, name or phone, address, lat, lng,
         datetime.now(CARACAS_TZ).timestamp(), datetime.now(CARACAS_TZ).timestamp()),
    )
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def _extract_bottles(producto_desc: str) -> int:
    """Extrae cantidad de botellones del producto_desc (ej '3 botellones de agua')."""
    import re
    m = re.search(r"(\d+)\s*botell", producto_desc or "", re.IGNORECASE)
    return int(m.group(1)) if m else 1


def _get_active_vehicles(conn: sqlite3.Connection) -> list:
    """Retorna vehicles activos con su operator_name."""
    return conn.execute(
        "SELECT id, name, operator_name, max_full_bottles FROM vehicles WHERE active=1"
    ).fetchall()


async def _notify_chofer(route, total_distance: float):
    """Envía notificación Telegram al chofer con su ruta del día."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_DISPATCH_CHAT:
        logger.info("Telegram no configurado — skip notificación chofer")
        return

    import httpx

    stops_text = "\n".join(
        f"  {i+1}. {stop.name} — {stop.bottles_full} botellones\n     {stop.address}"
        for i, stop in enumerate(route.stops)
    )

    msg = (
        f"📋 **Ruta del día {datetime.now(CARACAS_TZ).strftime('%Y-%m-%d')}**\n\n"
        f"🚗 {route.vehicle_id} — {route.operator_name}\n"
        f"📦 {len(route.stops)} paradas\n"
        f"💧 {route.total_bottles} botellones\n"
        f"📏 {route.total_distance_km:.1f} km\n"
        f"⏱️ ~{route.total_duration_min} min\n\n"
        f"**Paradas:**\n{stops_text}\n\n"
        f"💧 Estación H2O"
    )

    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                json={
                    "chat_id": TELEGRAM_DISPATCH_CHAT,
                    "text": msg,
                    "parse_mode": "Markdown",
                },
                timeout=10,
            )
        logger.info("Telegram enviado a %s (%d paratas)", route.operator_name, len(route.stops))
    except Exception as e:
        logger.error("Error Telegram: %s", e)


async def main():
    try:
        from skills.dispatch.route_engine import (
            compute_vrp_route, ClientOrder, DEPOT_LAT, DEPOT_LNG,
        )

        # 1. Leer pedidos pending
        pending = _fetch_pending_orders()
        if not pending:
            logger.info("No hay pedidos pending en dispatch_queue — nada que planificar")
            return

        logger.info("Pedidos pending: %d", len(pending))

        conn = _get_dispatch_db()
        vehicles = _get_active_vehicles(conn)
        if not vehicles:
            logger.warning("No hay vehicles activos — no se puede planificar")
            conn.close()
            return

        # 2. Convertir pedidos a ClientOrder + crear clients
        orders = []
        order_map = []  # (dispatch_queue_id, client_id) para updates

        for p in pending:
            lat = p["gps_lat"]
            lng = p["gps_lng"]
            # Si no hay GPS, usar depot como fallback (mejor que saltar el pedido)
            if lat is None or lng is None:
                logger.warning("Pedido %d sin GPS — usando depot como fallback", p["id"])
                lat, lng = DEPOT_LAT, DEPOT_LNG

            client_id = _find_or_create_client(
                conn, p["cliente_nombre"] or "", p["cliente_telefono"] or "",
                lat, lng, p["direccion"] or "",
            )
            bottles = _extract_bottles(p["producto_desc"])

            orders.append(ClientOrder(
                client_id=client_id,
                name=p["cliente_nombre"] or p["cliente_telefono"] or "Cliente",
                lat=lat,
                lng=lng,
                bottles_full=bottles,
                address=p["direccion"] or "",
                phone=p["cliente_telefono"] or "",
            ))
            order_map.append((p["id"], client_id))

        conn.commit()

        # 3. Calcular rutas VRP
        operators = [v["operator_name"] for v in vehicles if v["operator_name"]]
        vrp_result = compute_vrp_route(
            orders=orders,
            num_vehicles=len(vehicles),
            vehicle_capacity=vehicles[0]["max_full_bottles"] if vehicles else 30,
            operators=operators,
        )

        logger.info(
            "VRP calculado: %d rutas, %.1f km total, %d min, alg=%s, unassigned=%d",
            len(vrp_result.routes), vrp_result.total_distance_km,
            vrp_result.total_duration_min, vrp_result.algorithm,
            len(vrp_result.unassigned),
        )

        # 4. Crear dispatch_sessions + deliveries en dispatch.db
        today_str = datetime.now(CARACAS_TZ).strftime("%Y-%m-%d")
        now_ts = datetime.now(CARACAS_TZ).timestamp()

        for route in vrp_result.routes:
            # Crear dispatch_session
            conn.execute(
                """INSERT INTO dispatch_sessions
                   (vehicle_id, shift, date, status, total_clients, total_bottles_full,
                    total_distance_km, total_duration_minutes, route_algorithm,
                    route_computed_at, created_at)
                   VALUES (?, 'morning', ?, 'planning', ?, ?, ?, ?, ?, ?, ?)""",
                (route.vehicle_id, today_str, len(route.stops), route.total_bottles,
                 route.total_distance_km, route.total_duration_min,
                 vrp_result.algorithm, now_ts, now_ts),
            )
            session_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

            # Crear deliveries
            for seq, stop in enumerate(route.stops):
                conn.execute(
                    """INSERT INTO deliveries
                       (dispatch_session_id, client_id, vehicle_id, order_sequence,
                        status, bottles_full, created_at, updated_at)
                       VALUES (?, ?, ?, ?, 'pending', ?, ?, ?)""",
                    (session_id, stop.client_id, route.vehicle_id, seq + 1,
                     stop.bottles_full, now_ts, now_ts),
                )

            # 5. Notificar chofer
            await _notify_chofer(route, vrp_result.total_distance_km)

        conn.commit()

        # 6. Marcar pedidos de dispatch_queue como 'enviado'
        conv_conn = _get_conv_db()
        for dq_id, _ in order_map:
            conv_conn.execute(
                "UPDATE dispatch_queue SET estado='enviado', enviado_at=? WHERE id=?",
                (datetime.now(CARACAS_TZ).isoformat(), dq_id),
            )
        conv_conn.commit()
        conv_conn.close()
        conn.close()

        logger.info("Planificación completada: %d pedidos → %d rutas", len(pending), len(vrp_result.routes))

        # Log unassigned
        if vrp_result.unassigned:
            for u in vrp_result.unassigned:
                logger.warning("Pedido SIN asignar: client=%s bottles=%d", u.name, u.bottles_full)

    except Exception as e:
        logger.error("Error route planner: %s", e, exc_info=True)


if __name__ == "__main__":
    asyncio.run(main())
