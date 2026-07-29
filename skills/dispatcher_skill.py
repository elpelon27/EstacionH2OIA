"""Dispatcher Skill — Orquestador de despacho inteligente para Estación H2O.

Integra al WorkloadRouter como skill 'dispatcher'.
Expone actions: compute_route, notify_driver, update_delivery, record_gps,
check_geofence, get_bottle_inventory, get_heatmap_data.
"""

import logging
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from core.config import get_settings
from core.logger import get_logger

if TYPE_CHECKING:
    from skills.dispatch.route_engine import ClientOrder, VRPResult
    from skills.dispatch.telegram_bot import DispatcherTelegramBot
    from skills.dispatch.gps_tracker import GPSTracker
    from skills.dispatch.bottle_tracker import BottleTracker

logger = get_logger("dispatcher_skill")


class DispatcherSkill:
    """Skill principal del Dispatcher — se integra al WorkloadRouter."""

    def __init__(self) -> None:
        self.name = "dispatcher"
        self.settings = get_settings()
        self.logger = get_logger("dispatcher_skill")
        # Sub-componentes (lazy init para no cargar OR-Tools si no se usa)
        self._route_engine: Optional[Dict[str, Any]] = None
        self._telegram_bot: Optional["DispatcherTelegramBot"] = None
        self._gps_tracker: Optional["GPSTracker"] = None
        self._bottle_tracker: Optional["BottleTracker"] = None

    # ----------------------------------------------------------------------
    # Lazy initialization de sub-componentes
    # ----------------------------------------------------------------------
    @property
    def route_engine(self) -> Dict[str, Any]:
        if self._route_engine is None:
            from skills.dispatch.route_engine import compute_vrp_route, ClientOrder, VRPResult
            self._route_engine = {
                "compute_vrp_route": compute_vrp_route,
                "ClientOrder": ClientOrder,
                "VRPResult": VRPResult,
            }
        return self._route_engine

    @property
    def telegram_bot(self) -> "DispatcherTelegramBot":
        if self._telegram_bot is None:
            from skills.dispatch.telegram_bot import DispatcherTelegramBot
            self._telegram_bot = DispatcherTelegramBot()
        return self._telegram_bot

    @property
    def gps_tracker(self) -> "GPSTracker":
        if self._gps_tracker is None:
            from skills.dispatch.gps_tracker import GPSTracker
            self._gps_tracker = GPSTracker()
        return self._gps_tracker

    @property
    def bottle_tracker(self) -> "BottleTracker":
        if self._bottle_tracker is None:
            from skills.dispatch.bottle_tracker import BottleTracker
            self._bottle_tracker = BottleTracker()
        return self._bottle_tracker

    # ----------------------------------------------------------------------
    # Actions expuestas al WorkloadRouter
    # ----------------------------------------------------------------------
    async def execute(self, **kwargs: Any) -> Dict[str, Any]:
        """Punto de entrada único desde WorkloadRouter."""
        action = kwargs.pop("action", None)
        if not action:
            return self._error("Falta parámetro 'action'")

        action_map: Dict[str, Any] = {
            "compute_route": self._compute_route,
            "notify_driver": self._notify_driver,
            "update_delivery": self._update_delivery,
            "record_gps": self._record_gps,
            "check_geofence": self._check_geofence,
            "get_bottle_inventory": self._get_bottle_inventory,
            "get_heatmap_data": self._get_heatmap_data,
            "assign_bottle_to_client": self._assign_bottle_to_client,
            "return_bottle_from_client": self._return_bottle_from_client,
            "send_bottle_to_wash": self._send_bottle_to_wash,
            "get_driver_status": self._get_driver_status,
        }

        handler = action_map.get(action)
        if not handler:
            return self._error(f"Acción desconocida: {action}")

        try:
            result = await handler(**kwargs)
            return result
        except Exception as e:
            self.logger.exception("Error en action=%s: %s", action, e)
            return self._error(f"Error ejecutando {action}: {e}")

    # ----------------------------------------------------------------------
    # Action: compute_route
    # ----------------------------------------------------------------------
    async def _compute_route(
        self,
        orders: List[Dict[str, Any]],
        num_vehicles: int = 2,
        vehicle_capacity: int = 30,
        depot_lat: float = 10.6447,
        depot_lng: float = -71.6101,
        operators: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Calcula rutas optimizadas usando OR-Tools VRP."""
        ClientOrder = self.route_engine["ClientOrder"]
        compute_vrp_route = self.route_engine["compute_vrp_route"]

        client_orders = [
            ClientOrder(
                client_id=o["client_id"],
                name=o["name"],
                lat=o["lat"],
                lng=o["lng"],
                bottles_full=o.get("bottles_full", 0),
                bottles_empty_pickup=o.get("bottles_empty_pickup", 0),
                priority=o.get("priority", 5),
                address=o.get("address", ""),
                phone=o.get("phone", ""),
            )
            for o in orders
        ]

        result = compute_vrp_route(
            orders=client_orders,
            num_vehicles=num_vehicles,
            vehicle_capacity=vehicle_capacity,
            depot_lat=depot_lat,
            depot_lng=depot_lng,
            operators=operators,
        )

        return {
            "success": True,
            "message": "Ruta calculada",
            "data": {
                "algorithm": result.algorithm,
                "total_distance_km": result.total_distance_km,
                "total_duration_min": result.total_duration_min,
                "unassigned": len(result.unassigned),
                "routes": [
                    {
                        "vehicle_id": r.vehicle_id,
                        "operator_name": r.operator_name,
                        "stops": [
                            {
                                "client_id": s.client_id,
                                "name": s.name,
                                "lat": s.lat,
                                "lng": s.lng,
                                "bottles_full": s.bottles_full,
                                "bottles_empty_pickup": s.bottles_empty_pickup,
                                "priority": s.priority,
                                "address": s.address,
                                "phone": s.phone,
                            }
                            for s in r.stops
                        ],
                        "total_distance_km": r.total_distance_km,
                        "total_duration_min": r.total_duration_min,
                        "total_bottles": r.total_bottles,
                    }
                    for r in result.routes
                ],
            },
        }

    # ----------------------------------------------------------------------
    # Action: notify_driver
    # ----------------------------------------------------------------------
    async def _notify_driver(
        self,
        vehicle_id: int,
        client_name: str,
        client_phone: str,
        bottles_full: int,
        lat: float,
        lng: float,
        address: str,
        total_eur: float = 0,
        total_bs: float = 0,
        metodo_pago: str = "",
    ) -> Dict[str, Any]:
        """Envía un pedido al chofer por Telegram."""
        ok = await self.telegram_bot.send_delivery_to_chofer(
            vehicle_id=vehicle_id,
            client_name=client_name,
            client_phone=client_phone,
            bottles_full=bottles_full,
            lat=lat,
            lng=lng,
            address=address,
            total_eur=total_eur,
            total_bs=total_bs,
            metodo_pago=metodo_pago,
        )
        return {"success": True, "message": "Notificación enviada" if ok else "Falló envío", "data": {"sent": ok}}

    # ----------------------------------------------------------------------
    # Action: update_delivery
    # ----------------------------------------------------------------------
    async def _update_delivery(
        self,
        delivery_id: int,
        status: str,
        notes: str = "",
    ) -> Dict[str, Any]:
        """Actualiza estado de una entrega (desde bot chofer o bridge)."""
        from skills.dispatcher import update_delivery_status
        update_delivery_status(delivery_id, status, notes)
        return {"success": True, "message": f"Entrega {delivery_id} actualizada a {status}"}

    # ----------------------------------------------------------------------
    # Action: record_gps
    # ----------------------------------------------------------------------
    async def _record_gps(
        self,
        vehicle_id: int,
        lat: float,
        lng: float,
        accuracy: Optional[float] = None,
        speed: Optional[float] = None,
        source: str = "telegram",
        delivery_id: Optional[int] = None,
        track_type: str = "checkin",
    ) -> Dict[str, Any]:
        """Registra punto GPS (Tasker o Telegram check-in)."""
        from skills.dispatcher import save_gps_track, check_geofence

        save_gps_track(
            vehicle_id=vehicle_id,
            lat=lat,
            lng=lng,
            accuracy=accuracy,
            speed=speed,
            source=source,
            delivery_id=delivery_id,
            track_type=track_type,
        )

        in_perimeter = check_geofence(vehicle_id, lat, lng)

        return {"success": True, "message": "GPS registrado", "data": {"in_perimeter": in_perimeter, "lat": lat, "lng": lng}}

    # ----------------------------------------------------------------------
    # Action: check_geofence
    # ----------------------------------------------------------------------
    async def _check_geofence(self, lat: float, lng: float) -> Dict[str, Any]:
        """Verifica si un punto está dentro del perímetro de operación."""
        from skills.dispatch.route_engine import check_operation_perimeter
        inside = check_operation_perimeter(lat, lng)
        return {"success": True, "message": "Geofence verificado", "data": {"inside": inside}}

    # ----------------------------------------------------------------------
    # Action: get_bottle_inventory (SWAP)
    # ----------------------------------------------------------------------
    async def _get_bottle_inventory(self) -> Dict[str, Any]:
        """Retorna inventario de botellones loaner (SWAP)."""
        stats = await self.bottle_tracker.get_inventory_stats()
        return {"success": True, "message": "Inventario botellones", "data": stats}

    # ----------------------------------------------------------------------
    # Action: get_heatmap_data
    # ----------------------------------------------------------------------
    async def _get_heatmap_data(self) -> Dict[str, Any]:
        """Datos para mapa de calor (Google Sheets Mapa_Calor)."""
        data = await self.gps_tracker.get_heatmap_data()
        return {"success": True, "message": "Datos heatmap", "data": data}

    # ----------------------------------------------------------------------
    # Actions SWAP — Botellones loaner
    # ----------------------------------------------------------------------
    async def _assign_bottle_to_client(
        self,
        bottle_code: str,
        client_id: int,
        delivery_id: int,
    ) -> Dict[str, Any]:
        """Asigna botellón lleno a cliente (entregado)."""
        result = await self.bottle_tracker.assign_to_client(
            bottle_code=bottle_code,
            client_id=client_id,
            delivery_id=delivery_id,
        )
        return {"success": True, "message": "Botellón asignado a cliente", "data": result}

    async def _return_bottle_from_client(
        self,
        bottle_code: str,
        client_id: int,
        delivery_id: int,
    ) -> Dict[str, Any]:
        """Recibe botellón vacío del cliente (recogido)."""
        result = await self.bottle_tracker.return_from_client(
            bottle_code=bottle_code,
            client_id=client_id,
            delivery_id=delivery_id,
        )
        return {"success": True, "message": "Botellón vacío recibido", "data": result}

    async def _send_bottle_to_wash(self, bottle_code: str) -> Dict[str, Any]:
        """Envía botellón vacío a lavado en planta."""
        result = await self.bottle_tracker.send_to_wash(bottle_code)
        return {"success": True, "message": "Botellón enviado a lavado", "data": result}

    # ----------------------------------------------------------------------
    # Action: get_driver_status
    # ----------------------------------------------------------------------
    async def _get_driver_status(self, vehicle_id: int) -> Dict[str, Any]:
        """Estado actual del chofer/vehículo."""
        # TODO: implementar lookup por vehicle_id
        return {"success": True, "message": "Estado chofer", "data": {"vehicle_id": vehicle_id}}

    # ----------------------------------------------------------------------
    # Helpers
    # ----------------------------------------------------------------------
    def _success(self, message: str, data: Any = None) -> Dict[str, Any]:
        return {"success": True, "message": message, "data": data, "error": None, "skill": self.name}

    def _error(self, message: str) -> Dict[str, Any]:
        self.logger.error("skill_error", skill=self.name, error=message)
        return {"success": False, "message": None, "data": None, "error": message, "skill": self.name}


# ============================================================================
# Factory
# ============================================================================
_dispatcher_skill_instance: Optional["DispatcherSkill"] = None


def get_dispatcher_skill() -> "DispatcherSkill":
    """Obtiene instancia singleton del DispatcherSkill."""
    global _dispatcher_skill_instance
    if _dispatcher_skill_instance is None:
        _dispatcher_skill_instance = DispatcherSkill()
    return _dispatcher_skill_instance