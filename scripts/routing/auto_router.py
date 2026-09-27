#!/usr/bin/env python3
"""Auto-routing NIVEL 1 (restaurantes/clinicas/escuelas) — plan de peso del Líder.

Reglas:
- Clientes con is_automatic=1 entran en la ruta del día SIEMPRE
  (reparto diario obligatorio, sin necesidad de que pidan).
- Los LUNES se duplica la cantidad de botellones para estos clientes
  (domingo no se atiende).
- create_daily_orders() materializa los pedidos en dispatch.db
  (tabla orders_auto) con estado 'pending_dispatch' para que el
  dispatcher los asigne a vehículo/chofer.
- No toca bridge.py ni geofence.py: solo lee dispatch.db.
"""
import os
import sqlite3
import sys
from datetime import date
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO))

DISPATCH_DB = Path(
    os.environ.get("DISPATCH_DB_PATH", str(_REPO / "data" / "dispatch.db"))
)


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DISPATCH_DB))
    conn.row_factory = sqlite3.Row
    return conn


def init_auto_orders_table() -> None:
    """Crea orders_auto si no existe (idempotente)."""
    with _conn() as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS orders_auto (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER NOT NULL,
                phone TEXT,
                name TEXT,
                qty_botellones INTEGER NOT NULL,
                delivery_date TEXT NOT NULL,
                is_monday_double INTEGER NOT NULL DEFAULT 0,
                estado TEXT NOT NULL DEFAULT 'pending_dispatch',
                lat REAL,
                lng REAL,
                zone_id INTEGER,
                created_at REAL NOT NULL,
                UNIQUE(client_id, delivery_date)
            );
            """
        )


def get_daily_route(delivery_date: date | None = None) -> list[dict[str, Any]]:
    """Ruta del día: TODOS los clientes is_automatic=1.

    - Lunes (weekday()==0): qty = avg_bottles_per_visit * 2 (domingo no se atiende).
    - Otros días: qty = avg_bottles_per_visit.
    - avg faltante o 0 → default 3 (mínimo del negocio).

    Retorna lista de entregas automáticas (no escribe en DB).
    """
    d = delivery_date or date.today()
    is_monday = d.weekday() == 0
    conn = _conn()
    try:
        rows = conn.execute(
            "SELECT id, phone, name, lat, lng, zone_id, "
            "avg_bottles_per_visit, priority_notes "
            "FROM clients WHERE is_automatic = 1 AND active = 1 "
            "ORDER BY zone_id, name"
        ).fetchall()
    finally:
        conn.close()

    route: list[dict[str, Any]] = []
    for r in rows:
        base = int(r["avg_bottles_per_visit"] or 0) or 3
        qty = base * 2 if is_monday else base
        route.append(
            {
                "client_id": r["id"],
                "phone": r["phone"],
                "name": r["name"],
                "qty_botellones": qty,
                "delivery_date": d.isoformat(),
                "is_monday_double": int(is_monday),
                "lat": r["lat"],
                "lng": r["lng"],
                "zone_id": r["zone_id"],
                "estado": "pending_dispatch",
            }
        )
    return route


def create_daily_orders(delivery_date: date | None = None) -> dict[str, Any]:
    """Materializa la ruta del día en orders_auto (estado 'pending_dispatch').

    Idempotente: UNIQUE(client_id, delivery_date) + INSERT OR IGNORE —
    correr el cron dos veces no duplica pedidos.
    Retorna resumen {creados, ignorados, total_ruta, es_lunes}.
    """
    init_auto_orders_table()
    route = get_daily_route(delivery_date)
    import time

    conn = _conn()
    created = ignored = 0
    try:
        for item in route:
            cur = conn.execute(
                "INSERT OR IGNORE INTO orders_auto "
                "(client_id, phone, name, qty_botellones, delivery_date, "
                "is_monday_double, estado, lat, lng, zone_id, created_at) "
                "VALUES (?,?,?,?,?,?, 'pending_dispatch', ?,?,?,?)",
                (
                    item["client_id"], item["phone"], item["name"],
                    item["qty_botellones"], item["delivery_date"],
                    item["is_monday_double"], item["lat"], item["lng"],
                    item["zone_id"], time.time(),
                ),
            )
            if cur.rowcount:
                created += 1
            else:
                ignored += 1
        conn.commit()
    finally:
        conn.close()
    return {
        "creados": created,
        "ignorados": ignored,
        "total_ruta": len(route),
        "es_lunes": bool(route and route[0]["is_monday_double"]),
    }


if __name__ == "__main__":
    import json

    d = date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else None
    if "--create" in sys.argv:
        print(json.dumps(create_daily_orders(d), ensure_ascii=False))
    else:
        print(json.dumps(get_daily_route(d), ensure_ascii=False, indent=2))
