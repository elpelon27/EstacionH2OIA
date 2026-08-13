#!/usr/bin/env python3
"""
Seed Data — Datos iniciales para Dispatcher + SWAP
Estación H2O · Maracaibo, Venezuela

Pobla:
- 5 zonas de Maracaibo
- 2 vehículos (Triciclo 1 y 2) con operador integrado
- 16 clientes piloto (B2B + multifamiliares + unifamiliares)
- 165 botellones loaner (H2O-001 a H2O-165)
"""

import logging
import sqlite3
from datetime import UTC, datetime
from typing import Any

# Inicializar LOG_SALT en módulo crypto centralizado
from core.crypto import hash_phone as _hash_phone

logger = logging.getLogger("dispatch.seed_data")

DISPATCH_DB = "/mnt/ssd_trabajo/hermes-agent/data/dispatch.db"

# Zona 1: Norte (Oeste) — Urbanizaciones alta densidad
# Zona 2: Centro — Comercial + residencial
# Zona 3: Sur (Este) — Urbanizaciones + B2B
# Zona 4: Oeste — Industrial + B2B
# Zona 5: San Francisco — Residencial + mixto

ZONES: list[dict[str, Any]] = [
    {
        "id": 1,
        "name": "Norte",
        "center_lat": 10.6700,
        "center_lng": -71.6300,
        "radius_km": 8.0,
        "description": "Urbanizaciones Norte (La Limpia, El Milagro, Veritas, etc.)",
    },
    {
        "id": 2,
        "name": "Centro",
        "center_lat": 10.6447,
        "center_lng": -71.6101,
        "radius_km": 5.0,
        "description": "Centro comercial + residencial denso",
    },
    {
        "id": 3,
        "name": "Sur-Este",
        "center_lat": 10.6100,
        "center_lng": -71.5800,
        "radius_km": 7.0,
        "description": "Sur-Este (La Lago, El Soler, etc.)",
    },
    {
        "id": 4,
        "name": "Oeste",
        "center_lat": 10.6500,
        "center_lng": -71.6600,
        "radius_km": 8.0,
        "description": "Oeste (Industrial, B2B, La Polar, etc.)",
    },
    {
        "id": 5,
        "name": "San Francisco",
        "center_lat": 10.6300,
        "center_lng": -71.6800,
        "radius_km": 8.0,
        "description": "San Francisco (residencial + mixto)",
    },
]

VEHICLES = [
    {
        "id": 1,
        "name": "Triciclo 1",
        "operator_name": "YORDANIS",
        "telegram_chat_id": 123456789,
        "max_full_bottles": 30,
        "max_empty_bottles": 70,
    },
    {
        "id": 2,
        "name": "Triciclo 2",
        "operator_name": "EVERT",
        "telegram_chat_id": 987654321,
        "max_full_bottles": 30,
        "max_empty_bottles": 70,
    },
]

# 16 clientes piloto:
# Semana 1-2: B2B + multifamiliares
# Semana 3: unifamiliares
CLIENTS: list[dict[str, Any]] = [
    # B2B / Comercial (semana 1-2)
    {
        "phone": "+584140000001",
        "name": "Hotel del Lago",
        "address": "Av. Del Lago, Urbanización El Milagro",
        "lat": 10.6650,
        "lng": -71.6250,
        "client_type": "b2b",
        "visit_frequency": "daily",
        "bottle_exchange_model": 1,  # 1:1
        "bottle_return_hours": 24,
    },
    {
        "phone": "+584140000002",
        "name": "Restaurante El Faro",
        "address": "Av. Fuerzas Armadas, Centro",
        "lat": 10.6450,
        "lng": -71.6100,
        "client_type": "b2b",
        "visit_frequency": "daily",
        "bottle_exchange_model": 1,
        "bottle_return_hours": 24,
    },
    {
        "phone": "+584140000003",
        "name": "Clínica San Rafael",
        "address": "Av. Universidad, Veritas",
        "lat": 10.6700,
        "lng": -71.6300,
        "client_type": "b2b",
        "visit_frequency": "daily",
        "bottle_exchange_model": 1,
        "bottle_return_hours": 24,
    },
    {
        "phone": "+584140000004",
        "name": "Oficinas Corp. Polar",
        "address": "Zona Industrial, La Polar",
        "lat": 10.6550,
        "lng": -71.6550,
        "client_type": "b2b",
        "visit_frequency": "weekly",
        "bottle_exchange_model": 1,
        "bottle_return_hours": 36,
    },
    {
        "phone": "+584140000005",
        "name": "Universidad del Zulia - Rectorado",
        "address": "Av. Universidad, Veritas",
        "lat": 10.6680,
        "lng": -71.6280,
        "client_type": "b2b",
        "visit_frequency": "weekly",
        "bottle_exchange_model": 1,
        "bottle_return_hours": 36,
    },
    {
        "phone": "+584140000006",
        "name": "Centro Comercial Sambil",
        "address": "Av. Fuerzas Armadas, Sambil",
        "lat": 10.6400,
        "lng": -71.6050,
        "client_type": "b2b",
        "visit_frequency": "daily",
        "bottle_exchange_model": 1,
        "bottle_return_hours": 24,
    },
    # Multifamiliares (semana 1-2)
    {
        "phone": "+584140000007",
        "name": "Condominio Los Naranjos",
        "address": "Urbanización Los Naranjos, Norte",
        "lat": 10.6720,
        "lng": -71.6280,
        "client_type": "multifamiliar",
        "visit_frequency": "weekly",
        "bottle_exchange_model": 1,
        "bottle_return_hours": 36,
    },
    {
        "phone": "+584140000008",
        "name": "Residencias El Soler",
        "address": "Urbanización El Soler, Sur-Este",
        "lat": 10.6150,
        "lng": -71.5850,
        "client_type": "multifamiliar",
        "visit_frequency": "weekly",
        "bottle_exchange_model": 1,
        "bottle_return_hours": 36,
    },
    {
        "phone": "+584140000009",
        "name": "Edificio Las Palmas",
        "address": "Av. El Milagro, El Milagro",
        "lat": 10.6620,
        "lng": -71.6220,
        "client_type": "multifamiliar",
        "visit_frequency": "weekly",
        "bottle_exchange_model": 1,
        "bottle_return_hours": 36,
    },
    {
        "phone": "+584140000010",
        "name": "Torres del Lago",
        "address": "Av. Del Lago, Urbanización La Limpia",
        "lat": 10.6600,
        "lng": -71.6200,
        "client_type": "multifamiliar",
        "visit_frequency": "weekly",
        "bottle_exchange_model": 1,
        "bottle_return_hours": 36,
    },
    {
        "phone": "+584140000011",
        "name": "Conjunto Residencial Veritas",
        "address": "Urbanización Veritas, Norte",
        "lat": 10.6750,
        "lng": -71.6320,
        "client_type": "multifamiliar",
        "visit_frequency": "weekly",
        "bottle_exchange_model": 1,
        "bottle_return_hours": 36,
    },
    # Unifamiliares (semana 3)
    {
        "phone": "+584140000012",
        "name": "Familia Pérez - Casa 1",
        "address": "Calle 85, Urbanización La Limpia",
        "lat": 10.6680,
        "lng": -71.6260,
        "client_type": "unifamiliar",
        "visit_frequency": "biweekly",
        "bottle_exchange_model": 1,
        "bottle_return_hours": 48,
    },
    {
        "phone": "+584140000013",
        "name": "Familia González - Casa 2",
        "address": "Calle 72, Urbanización El Milagro",
        "lat": 10.6630,
        "lng": -71.6240,
        "client_type": "unifamiliar",
        "visit_frequency": "biweekly",
        "bottle_exchange_model": 1,
        "bottle_return_hours": 48,
    },
    {
        "phone": "+584140000014",
        "name": "Familia Rodríguez - Casa 3",
        "address": "Av. 5, Urbanización Veritas",
        "lat": 10.6730,
        "lng": -71.6310,
        "client_type": "unifamiliar",
        "visit_frequency": "biweekly",
        "bottle_exchange_model": 1,
        "bottle_return_hours": 48,
    },
    {
        "phone": "+584140000015",
        "name": "Familia Hernández - Casa 4",
        "address": "Calle 12, Urbanización La Limpia",
        "lat": 10.6650,
        "lng": -71.6240,
        "client_type": "unifamiliar",
        "visit_frequency": "biweekly",
        "bottle_exchange_model": 1,
        "bottle_return_hours": 48,
    },
    {
        "phone": "+584140000016",
        "name": "Familia Martínez - Casa 5",
        "address": "Av. Principal, Urbanización La Limpia",
        "lat": 10.6670,
        "lng": -71.6250,
        "client_type": "unifamiliar",
        "visit_frequency": "biweekly",
        "bottle_exchange_model": 1,
        "bottle_return_hours": 48,
    },
]


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DISPATCH_DB)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


def init_zones(conn: sqlite3.Connection) -> None:
    logger.info("Insertando zonas...")
    for zone in ZONES:
        conn.execute(
            """
            INSERT OR IGNORE INTO zones (id, name, center_lat, center_lng, radius_km, description)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                zone["id"],
                zone["name"],
                zone["center_lat"],
                zone["center_lng"],
                zone["radius_km"],
                zone["description"],
            ),
        )
    conn.commit()
    logger.info("Zonas insertadas: %d", len(ZONES))


def init_vehicles(conn: sqlite3.Connection) -> None:
    logger.info("Insertando vehículos...")
    for v in VEHICLES:
        conn.execute(
            """
            INSERT OR IGNORE INTO vehicles
            (id, name, operator_name, telegram_chat_id, max_full_bottles, max_empty_bottles)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                v["id"],
                v["name"],
                v["operator_name"],
                v["telegram_chat_id"],
                v["max_full_bottles"],
                v["max_empty_bottles"],
            ),
        )
    conn.commit()
    logger.info("Vehículos insertados: %d", len(VEHICLES))


def init_clients(conn: sqlite3.Connection) -> None:
    logger.info("Insertando clientes piloto...")
    # Import haversine from route_engine
    import sys

    sys.path.insert(0, "/mnt/ssd_trabajo/hermes-agent")
    from skills.dispatch.route_engine import haversine

    for client in CLIENTS:
        # Calcular zona más cercana
        best_zone = None
        best_dist = float("inf")
        for zone in ZONES:
            dist = haversine(client["lat"], client["lng"], zone["center_lat"], zone["center_lng"])
            if dist < best_dist:
                best_dist = dist
                best_zone = zone["id"]

        phone_hash = _hash_phone(client["phone"])

        conn.execute(
            """
            INSERT OR IGNORE INTO clients (
                phone, phone_hash, name, address_text, lat, lng, zone_id,
                client_type, visit_frequency, bottle_exchange_model, bottle_return_hours
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                client["phone"],
                phone_hash,
                client["name"],
                client["address"],
                client["lat"],
                client["lng"],
                best_zone,
                client["client_type"],
                client["visit_frequency"],
                client["bottle_exchange_model"],
                client["bottle_return_hours"],
            ),
        )
    conn.commit()
    logger.info("Clientes insertados: %d", len(CLIENTS))


def init_bottles(conn: sqlite3.Connection) -> None:
    logger.info("Insertando 165 botellones loaner...")
    now = datetime.now(UTC).isoformat()
    for i in range(1, 166):
        bottle_code = f"H2O-{i:03d}"
        conn.execute(
            """
            INSERT OR IGNORE INTO bottles (bottle_code, status, created_at, updated_at)
            VALUES (?, 'available', ?, ?)
            """,
            (bottle_code, now, now),
        )
    conn.commit()
    logger.info("Botellones insertados: 165")


def run_seed() -> None:
    logger.info("=== INICIANDO SEED DATA ===")
    conn = get_db()

    # Asegurar que tablas existan (schema ya existe en dispatch.db)
    init_zones(conn)
    init_vehicles(conn)
    init_clients(conn)
    init_bottles(conn)

    # Verificar
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM zones")
    logger.info("Zonas totales: %d", cur.fetchone()[0])
    cur.execute("SELECT COUNT(*) FROM vehicles")
    logger.info("Vehículos totales: %d", cur.fetchone()[0])
    cur.execute("SELECT COUNT(*) FROM clients")
    logger.info("Clientes totales: %d", cur.fetchone()[0])
    cur.execute("SELECT COUNT(*) FROM bottles")
    logger.info("Botellones totales: %d", cur.fetchone()[0])

    conn.close()
    logger.info("=== SEED DATA COMPLETADO ===")


if __name__ == "__main__":
    import os

    from core.crypto import set_log_salt

    LOG_SALT = os.getenv("LOG_SALT", "change-this-in-production")
    set_log_salt(LOG_SALT)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    run_seed()
