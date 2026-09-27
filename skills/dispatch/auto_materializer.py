#!/usr/bin/env python3
"""
Materializador orders_auto → deliveries — puente Nivel 1 (directiva Líder 💧).

Convierte los pedidos automáticos (orders_auto, estado 'pending_dispatch') en
deliveries reales de una dispatch_session por vehículo, repartidos entre los
operadores POR ZONA con ROTACIÓN diaria (zona↔operador rota cada día, decisión
#10 del Líder), para que el chofer los reciba vía @DespachoH2O_bot (/plan y /ruta).

Reglas:
- Lee orders_auto del día (delivery_date = hoy, Caracas).
- Reparte zonas entre vehículos activos con rotación:
  zonas ordenadas por carga (desc), vehículos ordenados por id.
  El día de la semana (weekday) define el offset de rotación.
- Crea (o reusa) una dispatch_session por vehículo con shift='both', date=hoy.
- INSERT OR IGNORE por (session, client, order_auto id en operator_notes).
- Idempotente: re-ejecutar no duplica (reusa session y ignora duplicados).
- No toca bridge.py ni auto_router.py.
"""

import logging
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO))

DISPATCH_DB = Path(str(_REPO / "data" / "dispatch.db"))
CARACAS_TZ = timezone(timedelta(hours=-4))

logger = logging.getLogger("dispatch.auto_materializer")


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DISPATCH_DB))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def today_str() -> str:
    return datetime.now(CARACAS_TZ).date().isoformat()


def now_epoch() -> float:
    return datetime.now(CARACAS_TZ).timestamp()


def _assign_zones_with_rotation(
    zone_loads: list[tuple[int | None, int]],  # [(zone_id, n_pedidos), ...] orden desc por carga
    vehicles: list[dict[str, Any]],  # activos con chat_id (u orden por id)
    rotation_offset: int,  # weekday() de hoy: rota el emparejamiento zona↔operador
) -> dict[int | None, int]:
    """Reparte zonas entre vehículos con rotación diaria.

    Devuelve {zone_id: vehicle_id}. Un vehículo puede recibir varias zonas
    si hay menos zonas que vehículos (o viceversa: zonas se reparten round-robin).
    """
    if not vehicles or not zone_loads:
        return {}
    assignment: dict[int | None, int] = {}
    v_ids = [v["id"] for v in vehicles]
    n_v = len(v_ids)
    for i, (zone, _load) in enumerate(zone_loads):
        # round-robin: zona i-th → vehículo (i + offset) % n_vehiculos
        assignment[zone] = v_ids[(i + rotation_offset) % n_v]
    return assignment


def materialize_day(delivery_date: str | None = None) -> dict[str, Any]:
    """Materializa orders_auto del día en deliveries por vehículo.

    Idempotente: sessions con UNIQUE(vehicle_id, date, shift) y
    UNIQUE operator_notes='auto:<order_auto_id>' por session.
    """
    d = delivery_date or today_str()
    rotation_offset = datetime.fromisoformat(d).weekday()
    report: dict[str, Any] = {"date": d, "orders": [], "sessions": [], "inserted": 0}

    conn = _conn()
    try:
        orders = conn.execute(
            """
            SELECT oa.id AS order_auto_id, oa.client_id, oa.qty_botellones, oa.zone_id
            FROM orders_auto oa
            WHERE oa.delivery_date = ? AND oa.estado = 'pending_dispatch'
            ORDER BY oa.zone_id, oa.id
            """,
            (d,),
        ).fetchall()

        if not orders:
            report["msg"] = "Sin orders_auto pendientes para hoy."
            return report

        # Zonas por carga (para balancear) — zone_id None se trata como zona aparte
        zone_load: dict[int | None, int] = {}
        for o in orders:
            z = o["zone_id"]
            zone_load[z] = zone_load.get(z, 0) + 1
        zone_loads = sorted(zone_load.items(), key=lambda kv: (-kv[1], str(kv[0])))

        vehicles = conn.execute(
            "SELECT id, name, operator_name FROM vehicles WHERE active = 1 ORDER BY id"
        ).fetchall()
        if not vehicles:
            report["error"] = "No hay vehículos activos."
            return report

        assignment = _assign_zones_with_rotation(
            [list(kv) for kv in zone_loads],  # type: ignore[arg-type]
            [dict(v) for v in vehicles],
            rotation_offset,
        )

        # Session por vehículo (idempotente por índice único)
        session_ids: dict[int, int] = {}
        for v in vehicles:
            conn.execute(
                """
                INSERT OR IGNORE INTO dispatch_sessions
                (vehicle_id, shift, date, status, route_algorithm, created_at)
                VALUES (?, 'both', ?, 'active', 'auto_materializer', ?)
                """,
                (v["id"], d, now_epoch()),
            )
            row = conn.execute(
                """
                SELECT id FROM dispatch_sessions
                WHERE vehicle_id = ? AND date = ? AND shift = 'both'
                """,
                (v["id"], d),
            ).fetchone()
            assert row is not None
            session_ids[v["id"]] = row["id"]
            report["sessions"].append({"vehicle_id": v["id"], "session_id": row["id"]})

        # Insertar deliveries idempotentes
        max_seq_by_session: dict[int, int] = {}
        for o in orders:
            vid = assignment.get(o["zone_id"])
            if vid is None:
                continue
            sid = session_ids[vid]
            seq = max_seq_by_session.get(sid, 0)
            # ocupar huecos si ya existían
            exists = conn.execute(
                """
                SELECT 1 FROM deliveries
                WHERE dispatch_session_id = ?
                  AND operator_notes = ?
                """,
                (sid, f"auto:{o['order_auto_id']}"),
            ).fetchone()
            if exists:
                continue
            seq += 1
            max_seq_by_session[sid] = seq
            conn.execute(
                """
                INSERT INTO deliveries
                (dispatch_session_id, client_id, vehicle_id, order_sequence,
                 status, bottles_full, operator_notes, created_at, updated_at)
                VALUES (?, ?, ?, ?, 'pending', ?, ?, ?, ?)
                """,
                (
                    sid,
                    o["client_id"],
                    vid,
                    seq,
                    o["qty_botellones"],
                    f"auto:{o['order_auto_id']}",
                    now_epoch(),
                    now_epoch(),
                ),
            )
            report["inserted"] += 1
            report["orders"].append(
                {"order_auto_id": o["order_auto_id"], "vehicle_id": vid, "zone": o["zone_id"]}
            )
            # Marcar orden como asignada
            conn.execute(
                "UPDATE orders_auto SET estado = 'assigned' WHERE id = ?",
                (o["order_auto_id"],),
            )

        conn.commit()
        report["assignment"] = {str(k): v for k, v in assignment.items()}
        return report
    finally:
        conn.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    r = materialize_day()
    print(f"Materialización {r['date']}: {r['inserted']} deliveries insertados")
    print(f"Sesiones: {r['sessions']}")
    print(f"Zonas→vehículo: {r.get('assignment', {})}")
    if r.get("msg"):
        print(r["msg"])
    if r.get("error"):
        print(f"ERROR: {r['error']}")
        sys.exit(1)
