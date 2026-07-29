#!/usr/bin/env python3
"""
============================================================================
Seed Data — Pobla dispatch.db con datos base para Estación H2O
Estación H2O · Maracaibo, Venezuela
============================================================================

Puebla:
- 5 zonas de Maracaibo (Bella Vista, Las Delicias, La Limpia, Centro, Tierra Negra)
- 2 vehículos (Triciclo 1/2, shift 'both')
- 16 clientes piloto (B2B + multifamiliares semana 1-2, unifamiliares semana 3)
- 165 botellones loaner (H2O-001 a H2O-165)

Uso:
    python skills/dispatch/seed_data.py
"""

import sqlite3
import time
from pathlib import Path

DISPATCH_DB = "/mnt/ssd_trabajo/hermes-agent/data/dispatch.db"
BOTTLE_PREFIX = "H2O-"
TOTAL_BOTTLES = 165


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DISPATCH_DB)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


def hash_phone(phone: str) -> str:
    """Hash simple para phone_hash (consistente con bridge.py)."""
    import hashlib

    salt = "change-this-in-production"  # LOG_SALT del .env
    return hashlib.sha256(f"{salt}:{phone}".encode()).hexdigest()[:32]


def seed_zones() -> None:
    """5 zonas de Maracaibo."""
    zones = [
        {
            "name": "Bella Vista",
            "description": "Zona residencial/comercial al norte",
            "center_lat": 10.6500,
            "center_lng": -71.6200,
            "radius_km": 3.0,
            "color": "#3B82F6",
        },
        {
            "name": "Las Delicias",
            "description": "Zona residencial consolidada",
            "center_lat": 10.6400,
            "center_lng": -71.6150,
            "radius_km": 2.5,
            "color": "#10B981",
        },
        {
            "name": "La Limpia",
            "description": "Zona comercial e industrial",
            "center_lat": 10.6450,
            "center_lng": -71.6050,
            "radius_km": 3.0,
            "color": "#F59E0B",
        },
        {
            "name": "Centro",
            "description": "Centro histórico y comercial",
            "center_lat": 10.6447,
            "center_lng": -71.6101,
            "radius_km": 2.0,
            "color": "#EF4444",
        },
        {
            "name": "Tierra Negra",
            "description": "Zona residencial en expansión sur",
            "center_lat": 10.6300,
            "center_lng": -71.6000,
            "radius_km": 3.5,
            "color": "#8B5CF6",
        },
    ]

    conn = get_db()
    now = time.time()
    for z in zones:
        conn.execute(
            """
            INSERT OR IGNORE INTO zones (name, description, center_lat, center_lng, radius_km, color, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                z["name"],
                z["description"],
                z["center_lat"],
                z["center_lng"],
                z["radius_km"],
                z["color"],
                now,
            ),
        )
    conn.commit()
    conn.close()
    print(f"✅ Zonas: {len(zones)} insertadas/verificadas")


def seed_vehicles() -> None:
    """2 triciclos (operadores YORDANIS + EVERT)."""
    vehicles = [
        {
            "name": "Triciclo 1",
            "operator_name": "YORDANIS",
            "max_full_bottles": 30,
            "max_empty_bottles": 70,
            "shift": "both",
            "active": 1,
        },
        {
            "name": "Triciclo 2",
            "operator_name": "EVERT",
            "max_full_bottles": 30,
            "max_empty_bottles": 70,
            "shift": "both",
            "active": 1,
        },
    ]

    conn = get_db()
    now = time.time()
    for v in vehicles:
        conn.execute(
            """
            INSERT OR IGNORE INTO vehicles (name, operator_name, max_full_bottles, max_empty_bottles, shift, active, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                v["name"],
                v["operator_name"],
                v["max_full_bottles"],
                v["max_empty_bottles"],
                v["shift"],
                v["active"],
                now,
            ),
        )
    conn.commit()
    conn.close()
    print(f"✅ Vehículos: {len(vehicles)} insertados/verificados")


def seed_clients() -> None:
    """16 clientes piloto: B2B + multifamiliares (semana 1-2), unifamiliares (semana 3)."""
    clients = [
        # B2B - Restaurantes (prioridad alta, botellón exchange model 1)
        {
            "phone": "+584121234567",
            "name": "Restaurante El Portal",
            "address_text": "Av. 2 El Milagro, Bella Vista",
            "lat": 10.6500,
            "lng": -71.6200,
            "client_type": "b2b",
            "avg_bottles_per_visit": 6,
            "visit_frequency": "daily",
            "visit_days": "1,2,3,4,5,6",
            "priority": 1,
            "zone_name": "Bella Vista",
            "bottle_exchange_model": 1,
            "bottle_return_hours": 24,
        },
        {
            "phone": "+584122345678",
            "name": "Restaurante La Buena Mesa",
            "address_text": "Calle 72, Las Delicias",
            "lat": 10.6400,
            "lng": -71.6150,
            "client_type": "b2b",
            "avg_bottles_per_visit": 6,
            "visit_frequency": "daily",
            "visit_days": "1,2,3,4,5,6",
            "priority": 1,
            "zone_name": "Las Delicias",
            "bottle_exchange_model": 1,
            "bottle_return_hours": 24,
        },
        {
            "phone": "+584123456789",
            "name": "Farmacia Central",
            "address_text": "Av. Universidad, La Limpia",
            "lat": 10.6450,
            "lng": -71.6050,
            "client_type": "b2b",
            "avg_bottles_per_visit": 4,
            "visit_frequency": "3x_week",
            "visit_days": "1,3,5",
            "priority": 3,
            "zone_name": "La Limpia",
            "bottle_exchange_model": 1,
            "bottle_return_hours": 24,
        },
        {
            "phone": "+584124567890",
            "name": "Panadería San José",
            "address_text": "Calle 93, Centro",
            "lat": 10.6447,
            "lng": -71.6101,
            "client_type": "b2b",
            "avg_bottles_per_visit": 5,
            "visit_frequency": "daily",
            "visit_days": "1,2,3,4,5,6",
            "priority": 2,
            "zone_name": "Centro",
            "bottle_exchange_model": 1,
            "bottle_return_hours": 24,
        },
        # Multifamiliares - Semana 1-2 (prioridad media, exchange model 1)
        {
            "phone": "+584141112233",
            "name": "Residencias Los Sauces - Torre A",
            "address_text": "Urbanización Los Sauces, Bella Vista",
            "lat": 10.6520,
            "lng": -71.6180,
            "client_type": "multifamily",
            "avg_bottles_per_visit": 3,
            "visit_frequency": "2x_week",
            "visit_days": "2,5",
            "priority": 4,
            "zone_name": "Bella Vista",
            "bottle_exchange_model": 1,
            "bottle_return_hours": 36,
        },
        {
            "phone": "+584142223344",
            "name": "Residencias Los Sauces - Torre B",
            "address_text": "Urbanización Los Sauces, Bella Vista",
            "lat": 10.6525,
            "lng": -71.6185,
            "client_type": "multifamily",
            "avg_bottles_per_visit": 3,
            "visit_frequency": "2x_week",
            "visit_days": "2,5",
            "priority": 4,
            "zone_name": "Bella Vista",
            "bottle_exchange_model": 1,
            "bottle_return_hours": 36,
        },
        {
            "phone": "+584143334455",
            "name": "Condominio Las Palmas",
            "address_text": "Av. Principal, Las Delicias",
            "lat": 10.6380,
            "lng": -71.6120,
            "client_type": "multifamily",
            "avg_bottles_per_visit": 4,
            "visit_frequency": "2x_week",
            "visit_days": "1,4",
            "priority": 4,
            "zone_name": "Las Delicias",
            "bottle_exchange_model": 1,
            "bottle_return_hours": 36,
        },
        {
            "phone": "+584144445566",
            "name": "Edificio Centro Plaza",
            "address_text": "Calle 88, Centro",
            "lat": 10.6460,
            "lng": -71.6080,
            "client_type": "multifamily",
            "avg_bottles_per_visit": 5,
            "visit_frequency": "3x_week",
            "visit_days": "1,3,5",
            "priority": 3,
            "zone_name": "Centro",
            "bottle_exchange_model": 1,
            "bottle_return_hours": 36,
        },
        {
            "phone": "+584145556677",
            "name": "Conjunto Residencial El Rosal",
            "address_text": "Sector El Rosal, La Limpia",
            "lat": 10.6470,
            "lng": -71.6020,
            "client_type": "multifamily",
            "avg_bottles_per_visit": 3,
            "visit_frequency": "2x_week",
            "visit_days": "2,6",
            "priority": 5,
            "zone_name": "La Limpia",
            "bottle_exchange_model": 1,
            "bottle_return_hours": 36,
        },
        {
            "phone": "+584146667788",
            "name": "Urbanización Tierra Negra - Módulo 1",
            "address_text": "Av. Tierra Negra, Tierra Negra",
            "lat": 10.6280,
            "lng": -71.5980,
            "client_type": "multifamily",
            "avg_bottles_per_visit": 4,
            "visit_frequency": "2x_week",
            "visit_days": "3,6",
            "priority": 5,
            "zone_name": "Tierra Negra",
            "bottle_exchange_model": 1,
            "bottle_return_hours": 36,
        },
        # Unifamiliares - Semana 3 (prioridad estándar, exchange model 1)
        {
            "phone": "+584161112233",
            "name": "Sra. González (Casa 123)",
            "address_text": "Calle 75, Las Delicias",
            "lat": 10.6420,
            "lng": -71.6130,
            "client_type": "residential",
            "avg_bottles_per_visit": 2,
            "visit_frequency": "weekly",
            "visit_days": "1",
            "priority": 5,
            "zone_name": "Las Delicias",
            "bottle_exchange_model": 1,
            "bottle_return_hours": 36,
        },
        {
            "phone": "+584162223344",
            "name": "Sr. Pérez (Casa 456)",
            "address_text": "Av. 3A, Bella Vista",
            "lat": 10.6540,
            "lng": -71.6160,
            "client_type": "residential",
            "avg_bottles_per_visit": 2,
            "visit_frequency": "weekly",
            "visit_days": "3",
            "priority": 5,
            "zone_name": "Bella Vista",
            "bottle_exchange_model": 1,
            "bottle_return_hours": 36,
        },
        {
            "phone": "+584163334455",
            "name": "Familia Rodríguez (Casa 789)",
            "address_text": "Calle 90, Centro",
            "lat": 10.6430,
            "lng": -71.6070,
            "client_type": "residential",
            "avg_bottles_per_visit": 1,
            "visit_frequency": "biweekly",
            "visit_days": "5",
            "priority": 6,
            "zone_name": "Centro",
            "bottle_exchange_model": 1,
            "bottle_return_hours": 36,
        },
        {
            "phone": "+584164445566",
            "name": "Sra. Martínez (Casa 321)",
            "address_text": "Calle 12, La Limpia",
            "lat": 10.6480,
            "lng": -71.6000,
            "client_type": "residential",
            "avg_bottles_per_visit": 2,
            "visit_frequency": "weekly",
            "visit_days": "2",
            "priority": 5,
            "zone_name": "La Limpia",
            "bottle_exchange_model": 1,
            "bottle_return_hours": 36,
        },
        {
            "phone": "+584165556677",
            "name": "Sr. López (Casa 654)",
            "address_text": "Av. Principal, Tierra Negra",
            "lat": 10.6320,
            "lng": -71.5950,
            "client_type": "residential",
            "avg_bottles_per_visit": 1,
            "visit_frequency": "biweekly",
            "visit_days": "4",
            "priority": 6,
            "zone_name": "Tierra Negra",
            "bottle_exchange_model": 1,
            "bottle_return_hours": 36,
        },
        {
            "phone": "+584166667788",
            "name": "Familia Hernández (Casa 987)",
            "address_text": "Calle 66, Las Delicias",
            "lat": 10.6360,
            "lng": -71.6100,
            "client_type": "residential",
            "avg_bottles_per_visit": 3,
            "visit_frequency": "weekly",
            "visit_days": "6",
            "priority": 5,
            "zone_name": "Las Delicias",
            "bottle_exchange_model": 1,
            "bottle_return_hours": 36,
        },
    ]

    conn = get_db()
    now = time.time()

    # Mapear zone_name -> zone_id
    zone_map = {}
    for row in conn.execute("SELECT id, name FROM zones").fetchall():
        zone_map[row["name"]] = row["id"]

    inserted = 0
    for c in clients:
        zone_id = zone_map.get(c["zone_name"])
        if zone_id is None:
            print(f"⚠️ Zona no encontrada: {c['zone_name']} para cliente {c['name']}")
            continue

        ph = hash_phone(c["phone"])
        conn.execute(
            """
            INSERT OR IGNORE INTO clients (
                phone, phone_hash, name, address_text, lat, lng, client_type,
                avg_bottles_per_visit, visit_frequency, visit_days, priority,
                zone_id, bottle_exchange_model, bottle_return_hours, active, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                c["phone"],
                ph,
                c["name"],
                c["address_text"],
                c["lat"],
                c["lng"],
                c["client_type"],
                c["avg_bottles_per_visit"],
                c["visit_frequency"],
                c["visit_days"],
                c["priority"],
                zone_id,
                c["bottle_exchange_model"],
                c["bottle_return_hours"],
                1,
                now,
                now,
            ),
        )
        if conn.total_changes > inserted:
            inserted += 1

    conn.commit()
    conn.close()
    print(f"✅ Clientes: {inserted} insertados/verificados (total objetivo: 16)")


def seed_bottles() -> None:
    """165 botellones loaner: H2O-001 a H2O-165."""
    conn = get_db()

    # Verificar cuántos ya existen
    existing = conn.execute(
        "SELECT COUNT(*) FROM bottles WHERE bottle_code LIKE ?", (f"{BOTTLE_PREFIX}%",)
    ).fetchone()[0]

    if existing >= TOTAL_BOTTLES:
        conn.close()
        print(f"✅ Botellones: {existing} ya existentes (objetivo: {TOTAL_BOTTLES})")
        return

    now = time.time()
    to_insert = TOTAL_BOTTLES - existing
    print(f"📦 Insertando {to_insert} botellones loaner...")

    batch = []
    for i in range(existing + 1, TOTAL_BOTTLES + 1):
        code = f"{BOTTLE_PREFIX}{i:03d}"
        batch.append((code, "available", None, None, None, now, now))

    conn.executemany(
        """
        INSERT INTO bottles (bottle_code, status, client_id, dispatch_delivery_id, assigned_at, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        batch,
    )
    conn.commit()
    conn.close()
    print(f"✅ Botellones loaner: {TOTAL_BOTTLES} totales (insertados {to_insert} nuevos)")


def seed_all() -> None:
    """Ejecuta todos los seeds en orden."""
    print("=" * 60)
    print("🌱 SEED DATA — Estación H2O Maracaibo")
    print("=" * 60)

    Path(DISPATCH_DB).parent.mkdir(parents=True, exist_ok=True)

    seed_zones()
    seed_vehicles()
    seed_clients()
    seed_bottles()

    # Verificación final
    conn = get_db()
    counts = {
        "zones": conn.execute("SELECT COUNT(*) FROM zones").fetchone()[0],
        "vehicles": conn.execute("SELECT COUNT(*) FROM vehicles WHERE active=1").fetchone()[0],
        "clients": conn.execute("SELECT COUNT(*) FROM clients WHERE active=1").fetchone()[0],
        "bottles": conn.execute("SELECT COUNT(*) FROM bottles").fetchone()[0],
        "bottles_available": conn.execute(
            "SELECT COUNT(*) FROM bottles WHERE status='available'"
        ).fetchone()[0],
    }
    conn.close()

    print("\n" + "=" * 60)
    print("📊 RESUMEN FINAL")
    print("=" * 60)
    for k, v in counts.items():
        print(f"  {k}: {v}")
    print("=" * 60)
    print("💧 Seed completado — Estación H2O listo para operar")


if __name__ == "__main__":
    seed_all()
