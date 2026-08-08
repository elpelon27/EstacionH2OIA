"""
============================================================================
Bottle Tracker — Tracking individual de 165 botellones loaner (SWAP)
Estación H2O · Maracaibo, Venezuela
============================================================================

Modelo Swap: Botellón loaner + sellado en planta

Estados del botellón:
- available: En planta, listo para asignar
- in_transit_full: En ruta hacia cliente (lleno)
- with_client: Entregado al cliente (lleno → esperando vacío)
- in_transit_empty: Recogido del cliente, volviendo a planta (vacío)
- maintenance: En lavado/reparación en planta
- retired: Dado de baja (roto, perdido, no recuperable)

Tracking por bottle_code: H2O-001 a H2O-165

Transiciones válidas:
    available → in_transit_full (assign_to_client)
    in_transit_full → with_client (confirm_delivery)
    with_client → in_transit_empty (return_from_client)
    in_transit_empty → maintenance (send_to_wash)
    maintenance → available (wash_complete)
    * → retired (mark_lost/damaged)
"""

import logging
import sqlite3
import time
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

logger = logging.getLogger("dispatch.bottle_tracker")

DISPATCH_DB = "/mnt/ssd_trabajo/hermes-agent/data/dispatch.db"


class BottleStatus(StrEnum):
    AVAILABLE = "available"
    IN_TRANSIT_FULL = "in_transit_full"
    WITH_CLIENT = "with_client"
    IN_TRANSIT_EMPTY = "in_transit_empty"
    MAINTENANCE = "maintenance"
    RETIRED = "retired"


class MovementType(StrEnum):
    ASSIGN_TO_CLIENT = "assign_to_client"
    CONFIRM_DELIVERY = "confirm_delivery"
    RETURN_FROM_CLIENT = "return_from_client"
    SEND_TO_WASH = "send_to_wash"
    WASH_COMPLETE = "wash_complete"
    MARK_LOST = "mark_lost"
    MARK_DAMAGED = "mark_damaged"
    MARK_RETIRED = "mark_retired"


VALID_TRANSITIONS = {
    BottleStatus.AVAILABLE: {
        BottleStatus.IN_TRANSIT_FULL,
        BottleStatus.MAINTENANCE,
        BottleStatus.RETIRED,
    },
    BottleStatus.IN_TRANSIT_FULL: {
        BottleStatus.WITH_CLIENT,
        BottleStatus.AVAILABLE,
        BottleStatus.RETIRED,
    },
    BottleStatus.WITH_CLIENT: {
        BottleStatus.IN_TRANSIT_EMPTY,
        BottleStatus.RETIRED,
    },
    BottleStatus.IN_TRANSIT_EMPTY: {
        BottleStatus.MAINTENANCE,
        BottleStatus.AVAILABLE,
        BottleStatus.RETIRED,
    },
    BottleStatus.MAINTENANCE: {
        BottleStatus.AVAILABLE,
        BottleStatus.RETIRED,
    },
    BottleStatus.RETIRED: set(),
}


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DISPATCH_DB)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


def now_epoch() -> float:
    return time.time()


@dataclass
class Bottle:
    """Representa un botellón loaner."""
    bottle_code: str
    status: str
    client_id: int | None = None
    dispatch_delivery_id: int | None = None
    assigned_at: float | None = None
    expected_return_at: float | None = None
    returned_at: float | None = None
    created_at: float = 0
    updated_at: float = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "bottle_code": self.bottle_code,
            "status": self.status,
            "client_id": self.client_id,
            "dispatch_delivery_id": self.dispatch_delivery_id,
            "assigned_at": self.assigned_at,
            "expected_return_at": self.expected_return_at,
            "returned_at": self.returned_at,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class BottleMovement:
    """Registro de movimiento/auditoría de botellón."""
    bottle_code: str
    from_status: str | None
    to_status: str
    from_client_id: int | None
    to_client_id: int | None
    delivery_id: int | None
    location_lat: float | None
    location_lng: float | None
    performed_by: str  # 'operator' | 'plant' | 'system'
    notes: str
    created_at: float


@dataclass
class BottleAlert:
    """Alerta de botellón (overdue, maintenance, lost)."""
    bottle_code: str
    alert_type: str  # 'overdue_return' | 'maintenance_due' | 'lost' | 'damaged'
    severity: str  # 'info' | 'warning' | 'critical'
    acknowledged: int = 0
    acknowledged_by: str | None = None
    acknowledged_at: float | None = None
    created_at: float = 0
    resolved_at: float | None = None


class BottleTracker:
    """Tracker de botellones loaner para modelo SWAP."""

    # Config
    RETURN_HOURS_RESIDENTIAL = 36
    RETURN_HOURS_ENTERPRISE = 24
    OVERDUE_CHECK_INTERVAL_HOURS = 6

    def __init__(self) -> None:
        self.logger = logging.getLogger("dispatch.bottle_tracker")

    # ----------------------------------------------------------------------
    # Core: Transiciones de estado
    # ----------------------------------------------------------------------

    def _validate_transition(self, from_status: str, to_status: str) -> bool:
        """Valida que la transición sea permitida."""
        allowed = VALID_TRANSITIONS.get(BottleStatus(from_status), set())
        return BottleStatus(to_status) in allowed

    def _get_bottle(self, bottle_code: str) -> Bottle | None:
        conn = get_db()
        row = conn.execute(
            "SELECT * FROM bottles WHERE bottle_code = ?", (bottle_code,)
        ).fetchone()
        conn.close()
        if not row:
            return None
        return Bottle(
            bottle_code=row["bottle_code"],
            status=row["status"],
            client_id=row["client_id"],
            dispatch_delivery_id=row["dispatch_delivery_id"],
            assigned_at=row["assigned_at"],
            expected_return_at=row["expected_return_at"],
            returned_at=row["returned_at"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def _update_bottle_status(
        self,
        bottle_code: str,
        new_status: str,
        client_id: int | None = None,
        delivery_id: int | None = None,
        performed_by: str = "system",
        notes: str = "",
        location_lat: float | None = None,
        location_lng: float | None = None,
    ) -> Bottle:
        """Actualiza estado del botellón y registra movimiento."""
        bottle = self._get_bottle(bottle_code)
        if not bottle:
            raise ValueError(f"Botellón {bottle_code} no encontrado")

        old_status = bottle.status
        if not self._validate_transition(old_status, new_status):
            raise ValueError(f"Transición inválida: {old_status} → {new_status}")

        now = now_epoch()
        conn = get_db()

        # Actualizar botellón
        update_fields = ["status = ?", "updated_at = ?"]
        params = [new_status, now]

        # Handle client_id - if explicitly provided (even None), update it
        if "client_id" in locals() or client_id is not None:
            update_fields.append("client_id = ?")
            params.append(client_id)
        if "delivery_id" in locals() or delivery_id is not None:
            update_fields.append("dispatch_delivery_id = ?")
            params.append(delivery_id)
        if new_status == BottleStatus.IN_TRANSIT_FULL:
            update_fields.append("assigned_at = ?")
            params.append(now)
        elif new_status == BottleStatus.WITH_CLIENT:
            # Calcular expected_return_at según tipo de cliente
            if client_id:
                client = conn.execute(
                    "SELECT client_type, bottle_return_hours FROM clients WHERE id = ?",
                    (client_id,),
                ).fetchone()
                if client:
                    hours = client["bottle_return_hours"] or (
                        self.RETURN_HOURS_ENTERPRISE if client["client_type"] == "b2b"
                        else self.RETURN_HOURS_RESIDENTIAL
                    )
                    update_fields.append("expected_return_at = ?")
                    params.append(now + hours * 3600)
        elif new_status == BottleStatus.IN_TRANSIT_EMPTY:
            update_fields.append("returned_at = ?")
            params.append(now)

        params.append(bottle_code)
        conn.execute(
            f"UPDATE bottles SET {', '.join(update_fields)} WHERE bottle_code = ?",
            params,
        )

        # Registrar movimiento
        conn.execute(
            """
            INSERT INTO bottle_movements
            (bottle_code, from_status, to_status, from_client_id, to_client_id,
             delivery_id, location_lat, location_lng, performed_by, notes, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                bottle_code,
                old_status,
                new_status,
                bottle.client_id,
                client_id,
                delivery_id,
                location_lat,
                location_lng,
                performed_by,
                notes,
                now,
            ),
        )

        conn.commit()
        conn.close()

        self.logger.info(
            "🔄 Botellón %s: %s → %s (by=%s, client=%s, delivery=%s)",
            bottle_code, old_status, new_status, performed_by, client_id, delivery_id
        )

        return self._get_bottle(bottle_code)  # type: ignore[return-value]

    def _create_alert(
        self,
        bottle_code: str,
        alert_type: str,
        severity: str = "warning",
        notes: str = "",
    ) -> None:
        """Crea alerta si no existe una igual sin resolver."""
        conn = get_db()
        existing = conn.execute(
            """
            SELECT id FROM bottle_alerts
            WHERE bottle_code = ? AND alert_type = ? AND resolved_at IS NULL
            """,
            (bottle_code, alert_type),
        ).fetchone()
        if existing:
            conn.close()
            return

        conn.execute(
            """
            INSERT INTO bottle_alerts (bottle_code, alert_type, severity, notes, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (bottle_code, alert_type, severity, notes, now_epoch()),
        )
        conn.commit()
        conn.close()
        self.logger.warning("🚨 Alerta %s: %s (%s)", alert_type, bottle_code, severity)

    # ----------------------------------------------------------------------
    # API Pública: Acciones SWAP
    # ----------------------------------------------------------------------

    async def assign_to_client(
        self,
        bottle_code: str,
        client_id: int,
        delivery_id: int,
        performed_by: str = "operator",
        location_lat: float | None = None,
        location_lng: float | None = None,
    ) -> dict[str, Any]:
        """
        Asigna botellón lleno a cliente (salida de planta).
        available → in_transit_full
        """
        # Verificar que el botellón esté disponible
        bottle = self._get_bottle(bottle_code)
        if not bottle:
            return {"success": False, "error": f"Botellón {bottle_code} no encontrado", "bottle": None}
        if bottle.status != BottleStatus.AVAILABLE:
            return {"success": False, "error": f"Botellón {bottle_code} no está disponible (estado: {bottle.status})", "bottle": None}

        try:
            bottle = self._update_bottle_status(
                bottle_code=bottle_code,
                new_status=BottleStatus.IN_TRANSIT_FULL,
                client_id=client_id,
                delivery_id=delivery_id,
                performed_by=performed_by,
                notes=f"Asignado a cliente {client_id} en delivery {delivery_id}",
                location_lat=location_lat,
                location_lng=location_lng,
            )
            return {"success": True, "bottle": bottle.to_dict()}
        except ValueError as e:
            return {"success": False, "error": str(e), "bottle": None}

    async def confirm_delivery(
        self,
        bottle_code: str,
        client_id: int,
        performed_by: str = "operator",
        location_lat: float | None = None,
        location_lng: float | None = None,
    ) -> dict[str, Any]:
        """
        Confirma entrega al cliente (botón 'Entregado' en app chofer).
        in_transit_full → with_client
        """
        # Verificar que el botellón esté en tránsito lleno
        bottle = self._get_bottle(bottle_code)
        if not bottle:
            return {
                "success": False,
                "error": f"Botellón {bottle_code} no encontrado",
                "bottle": None,
            }
        if bottle.status != BottleStatus.IN_TRANSIT_FULL:
            return {
                "success": False,
                "error": (
                    f"Botellón {bottle_code} no está en tránsito lleno "
                    f"(estado: {bottle.status})"
                ),
                "bottle": None,
            }

        try:
            bottle = self._update_bottle_status(
                bottle_code=bottle_code,
                new_status=BottleStatus.WITH_CLIENT,
                client_id=client_id,
                performed_by=performed_by,
                notes="Entrega confirmada por chofer",
                location_lat=location_lat,
                location_lng=location_lng,
            )
            return {"success": True, "bottle": bottle.to_dict()}
        except ValueError as e:
            return {"success": False, "error": str(e), "bottle": None}

    async def return_from_client(
        self,
        bottle_code: str,
        client_id: int,
        delivery_id: int,
        performed_by: str = "operator",
        location_lat: float | None = None,
        location_lng: float | None = None,
    ) -> dict[str, Any]:
        """
        Recibe botellón vacío del cliente (recogida).
        with_client → in_transit_empty
        """
        # Verificar que el botellón pertenece al cliente
        bottle = self._get_bottle(bottle_code)
        if not bottle:
            return {"success": False, "error": f"Botellón {bottle_code} no encontrado", "bottle": None}
        if bottle.client_id != client_id:
            return {"success": False, "error": f"Cliente {client_id} no coincide con el dueño del botellón ({bottle.client_id})", "bottle": None}

        try:
            bottle = self._update_bottle_status(
                bottle_code=bottle_code,
                new_status=BottleStatus.IN_TRANSIT_EMPTY,
                client_id=client_id,
                delivery_id=delivery_id,
                performed_by=performed_by,
                notes=f"Botellón vacío recogido de cliente {client_id}",
                location_lat=location_lat,
                location_lng=location_lng,
            )
            return {"success": True, "bottle": bottle.to_dict()}
        except ValueError as e:
            return {"success": False, "error": str(e), "bottle": None}

    async def send_to_wash(
        self,
        bottle_code: str,
        performed_by: str = "plant",
        notes: str = "Enviado a lavado en planta",
    ) -> dict[str, Any]:
        """
        Envía botellón vacío a lavado en planta.
        in_transit_empty → maintenance
        """
        bottle = self._update_bottle_status(
            bottle_code=bottle_code,
            new_status=BottleStatus.MAINTENANCE,
            performed_by=performed_by,
            notes=notes,
        )
        return {"success": True, "bottle": bottle.to_dict()}

    async def wash_complete(
        self,
        bottle_code: str,
        performed_by: str = "plant",
    ) -> dict[str, Any]:
        """
        Lavado completado, botellón disponible de nuevo.
        maintenance → available
        """
        try:
            bottle = self._update_bottle_status(
                bottle_code=bottle_code,
                new_status=BottleStatus.AVAILABLE,
                client_id=None,
                delivery_id=None,
                performed_by=performed_by,
                notes="Lavado completado, disponible para reasignar",
            )
            return {"success": True, "bottle": bottle.to_dict()}
        except ValueError as e:
            return {"success": False, "error": str(e), "bottle": None}

    async def mark_lost(
        self,
        bottle_code: str,
        performed_by: str = "operator",
        notes: str = "Reportado como perdido",
    ) -> dict[str, Any]:
        """Marca botellón como perdido/retirado."""
        bottle = self._update_bottle_status(
            bottle_code=bottle_code,
            new_status=BottleStatus.RETIRED,
            performed_by=performed_by,
            notes=notes,
        )
        self._create_alert(bottle_code, "lost", "critical", notes)
        return {"success": True, "bottle": bottle.to_dict()}

    async def mark_damaged(
        self,
        bottle_code: str,
        performed_by: str = "plant",
        notes: str = "Dañado en lavado/inspección",
    ) -> dict[str, Any]:
        """Marca botellón como dañado/retirado."""
        bottle = self._update_bottle_status(
            bottle_code=bottle_code,
            new_status=BottleStatus.RETIRED,
            performed_by=performed_by,
            notes=notes,
        )
        self._create_alert(bottle_code, "damaged", "warning", notes)
        return {"success": True, "bottle": bottle.to_dict()}

    # ----------------------------------------------------------------------
    # Consultas
    # ----------------------------------------------------------------------

    async def get_bottle(self, bottle_code: str) -> dict[str, Any] | None:
        """Obtiene estado actual de un botellón."""
        bottle = self._get_bottle(bottle_code)
        return bottle.to_dict() if bottle else None

    async def get_inventory_stats(self) -> dict[str, Any]:
        """Estadísticas de inventario para dashboard/API."""
        conn = get_db()
        # Conteo por estado
        status_counts = dict(
            conn.execute(
                "SELECT status, COUNT(*) as cnt FROM bottles GROUP BY status"
            ).fetchall()
        )
        # Total
        total = sum(status_counts.values())
        # Overdue
        overdue = conn.execute(
            """
            SELECT COUNT(*) FROM bottles
            WHERE status = 'with_client' AND expected_return_at < ?
            """,
            (now_epoch(),),
        ).fetchone()[0]
        # Alertas activas
        active_alerts = conn.execute(
            "SELECT COUNT(*) FROM bottle_alerts WHERE resolved_at IS NULL"
        ).fetchone()[0]
        conn.close()

        return {
            "total": total,
            "by_status": status_counts,
            "overdue_count": overdue,
            "active_alerts": active_alerts,
        }

    async def get_bottles_by_status(self, status: str) -> list[dict[str, Any]]:
        """Lista botellones por estado."""
        conn = get_db()
        rows = conn.execute(
            "SELECT * FROM bottles WHERE status = ? ORDER BY bottle_code", (status,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    async def get_available_bottle(self) -> dict[str, Any] | None:
        """Obtiene un botellón disponible para asignar (status = 'available')."""
        conn = get_db()
        row = conn.execute(
            "SELECT * FROM bottles WHERE status = 'available' ORDER BY bottle_code LIMIT 1"
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    async def get_overdue_bottles(self) -> list[dict[str, Any]]:
        """Botellones con devolución vencida."""
        conn = get_db()
        rows = conn.execute(
            """
            SELECT b.*, c.name as client_name, c.phone, c.client_type, c.bottle_return_hours
            FROM bottles b
            JOIN clients c ON b.client_id = c.id
            WHERE b.status = 'with_client' AND b.expected_return_at < ?
            ORDER BY b.expected_return_at ASC
            """,
            (now_epoch(),),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    async def get_active_alerts(self) -> list[dict[str, Any]]:
        """Alertas sin resolver."""
        conn = get_db()
        rows = conn.execute(
            """
            SELECT a.*, b.status as bottle_status
            FROM bottle_alerts a
            JOIN bottles b ON a.bottle_code = b.bottle_code
            WHERE a.resolved_at IS NULL
            ORDER BY
                CASE a.severity WHEN 'critical' THEN 1 WHEN 'warning' THEN 2 ELSE 3 END,
                a.created_at DESC
            """
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    async def acknowledge_alert(self, alert_id: int, acknowledged_by: str) -> dict[str, Any]:
        """Marca alerta como reconocida."""
        conn = get_db()
        conn.execute(
            """
            UPDATE bottle_alerts SET acknowledged = 1, acknowledged_by = ?, acknowledged_at = ?
            WHERE id = ?
            """,
            (acknowledged_by, now_epoch(), alert_id),
        )
        conn.commit()
        conn.close()
        return {"success": True, "alert_id": alert_id}

    async def resolve_alert(self, alert_id: int, resolved_by: str) -> dict[str, Any]:
        """Resuelve alerta."""
        conn = get_db()
        conn.execute(
            """
            UPDATE bottle_alerts SET resolved_at = ? WHERE id = ?
            """,
            (now_epoch(), alert_id),
        )
        conn.commit()
        conn.close()
        return {"success": True, "alert_id": alert_id}

    async def get_movement_history(self, bottle_code: str, limit: int = 50) -> list[dict[str, Any]]:
        """Historial de movimientos de un botellón."""
        conn = get_db()
        rows = conn.execute(
            """
            SELECT * FROM bottle_movements
            WHERE bottle_code = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (bottle_code, limit),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # ----------------------------------------------------------------------
    # Mantenimiento / Overdue Check (llamado por cron)
    # ----------------------------------------------------------------------

    async def check_overdue_bottles(self) -> dict[str, Any]:
        """Verifica botellones overdue y crea alertas. Llamado por cron cada 6h."""
        overdue = await self.get_overdue_bottles()
        created = 0
        for b in overdue:
            hours_overdue = (now_epoch() - b["expected_return_at"]) / 3600
            severity = "critical" if hours_overdue > 48 else "warning"
            self._create_alert(
                b["bottle_code"],
                "overdue_return",
                severity,
                f"Botellón overdue {hours_overdue:.1f}h (cliente: {b['client_name']})",
            )
            created += 1
        return {"checked": len(overdue), "alerts_created": created}


# ============================================================================
# Factory / Singleton
# ============================================================================

_bottle_tracker_instance: BottleTracker | None = None


def get_bottle_tracker() -> BottleTracker:
    """Obtiene instancia singleton del BottleTracker."""
    global _bottle_tracker_instance
    if _bottle_tracker_instance is None:
        _bottle_tracker_instance = BottleTracker()
    return _bottle_tracker_instance


# ============================================================================
# Test rápido
# ============================================================================

if __name__ == "__main__":
    import asyncio

    async def test():
        tracker = get_bottle_tracker()

        # Verificar inventario inicial
        stats = await tracker.get_inventory_stats()
        print(f"Inventario inicial: {stats}")

        # Test flujo completo con H2O-001
        bottle_code = "H2O-001"

        # 1. Asignar a cliente (salida planta)
        r1 = await tracker.assign_to_client(bottle_code, client_id=1, delivery_id=100)
        print(f"1. Assign: {r1['bottle']['status']}")

        # 2. Confirmar entrega (chofer entrega)
        r2 = await tracker.confirm_delivery(bottle_code, client_id=1)
        print(f"2. Confirm delivery: {r2['bottle']['status']}")

        # 3. Recoger vacío (chofer recoge)
        r3 = await tracker.return_from_client(bottle_code, client_id=1, delivery_id=100)
        print(f"3. Return from client: {r3['bottle']['status']}")

        # 4. Enviar a lavado (planta)
        r4 = await tracker.send_to_wash(bottle_code)
        print(f"4. Send to wash: {r4['bottle']['status']}")

        # 5. Lavado completado
        r5 = await tracker.wash_complete(bottle_code)
        print(f"5. Wash complete: {r5['bottle']['status']}")

        # Stats finales
        stats = await tracker.get_inventory_stats()
        print(f"Inventario final: {stats}")

    asyncio.run(test())
