"""Dispatcher Skill — Orquestador de despacho inteligente para Estación H2O.

Integra al WorkloadRouter como skill 'dispatcher'.
Expone actions: compute_route, notify_driver, update_delivery, record_gps,
check_geofence, get_bottle_inventory, get_heatmap_data.
"""

from typing import TYPE_CHECKING, Any, Optional

from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from core.config import get_settings
from core.logger import get_logger

if TYPE_CHECKING:
    from skills.dispatch.bottle_tracker import BottleTracker
    from skills.dispatch.gps_tracker import GPSTracker
    from skills.dispatch.telegram_bot import DispatcherTelegramBot

logger = get_logger("dispatcher_skill")


class DispatcherSkill:
    """Skill principal del Dispatcher — se integra al WorkloadRouter."""

    def __init__(self) -> None:
        self.name = "dispatcher"
        self.settings = get_settings()
        self.logger = get_logger("dispatcher_skill")
        # Sub-componentes (lazy init para no cargar OR-Tools si no se usa)
        self._route_engine: dict[str, Any] | None = None
        self._telegram_bot: DispatcherTelegramBot | None = None
        self._gps_tracker: GPSTracker | None = None
        self._bottle_tracker: BottleTracker | None = None

    # ----------------------------------------------------------------------
    # Lazy initialization de sub-componentes
    # ----------------------------------------------------------------------
    @property
    def route_engine(self) -> dict[str, Any]:
        if self._route_engine is None:
            from skills.dispatch.route_engine import ClientOrder, VRPResult, compute_vrp_route

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
    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        """Punto de entrada único desde WorkloadRouter."""
        action = kwargs.pop("action", None)
        if not action:
            return self._error("Falta parámetro 'action'")

        action_map: dict[str, Any] = {
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
            "confirm_delivery": self._confirm_delivery,
            "get_driver_status": self._get_driver_status,
            "delivery_delivered": self._delivery_delivered,
            "handle_telegram_update": self._handle_telegram_update,
        }

        handler = action_map.get(action)
        if not handler:
            return self._error(f"Acción desconocida: {action}")

        try:
            result: dict[str, Any] = await handler(**kwargs)
            return result
        except Exception as e:
            self.logger.exception("Error en action=%s: %s", action, e)
            return self._error(f"Error ejecutando {action}: {e}")

    # ----------------------------------------------------------------------
    # Action: compute_route
    # ----------------------------------------------------------------------
    async def _compute_route(
        self,
        orders: list[dict[str, Any]],
        num_vehicles: int = 2,
        vehicle_capacity: int = 30,
        depot_lat: float = 10.6447,
        depot_lng: float = -71.6101,
        operators: list[str] | None = None,
    ) -> dict[str, Any]:
        """Calcula rutas optimizadas usando OR-Tools VRP."""
        client_order = self.route_engine["ClientOrder"]
        compute_vrp_route = self.route_engine["compute_vrp_route"]

        client_orders = [
            client_order(
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
    ) -> dict[str, Any]:
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
        return {
            "success": True,
            "message": "Notificación enviada" if ok else "Falló envío",
            "data": {"sent": ok},
        }

    # ----------------------------------------------------------------------
    # Action: update_delivery
    # ----------------------------------------------------------------------
    async def _update_delivery(
        self,
        delivery_id: int,
        status: str,
        notes: str = "",
    ) -> dict[str, Any]:
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
        accuracy: float | None = None,
        speed: float | None = None,
        source: str = "telegram",
        delivery_id: int | None = None,
        track_type: str = "checkin",
    ) -> dict[str, Any]:
        """Registra punto GPS (Tasker o Telegram check-in)."""
        from skills.dispatcher import check_geofence, save_gps_track

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

        return {
            "success": True,
            "message": "GPS registrado",
            "data": {"in_perimeter": in_perimeter, "lat": lat, "lng": lng},
        }

    # ----------------------------------------------------------------------
    # Action: check_geofence
    # ----------------------------------------------------------------------
    async def _check_geofence(self, lat: float, lng: float) -> dict[str, Any]:
        """Verifica si un punto está dentro del perímetro de operación."""
        from skills.dispatch.route_engine import check_operation_perimeter

        inside = check_operation_perimeter(lat, lng)
        return {"success": True, "message": "Geofence verificado", "data": {"inside": inside}}

    # ----------------------------------------------------------------------
    # Action: get_bottle_inventory (SWAP)
    # ----------------------------------------------------------------------
    async def _get_bottle_inventory(self) -> dict[str, Any]:
        """Retorna inventario de botellones loaner (SWAP)."""
        stats = await self.bottle_tracker.get_inventory_stats()
        return {"success": True, "message": "Inventario botellones", "data": stats}

    # ----------------------------------------------------------------------
    # Action: get_heatmap_data
    # ----------------------------------------------------------------------
    async def _get_heatmap_data(self) -> dict[str, Any]:
        """Datos para mapa de calor (Google Sheets Mapa_Calor)."""
        data = self.gps_tracker.get_heatmap_data()
        return {"success": True, "message": "Datos heatmap", "data": data}

    # ----------------------------------------------------------------------
    # Actions SWAP — Botellones loaner
    # ----------------------------------------------------------------------
    async def _assign_bottle_to_client(
        self,
        bottle_code: str,
        client_id: int,
        delivery_id: int,
    ) -> dict[str, Any]:
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
    ) -> dict[str, Any]:
        """Recibe botellón vacío del cliente (recogido)."""
        result = await self.bottle_tracker.return_from_client(
            bottle_code=bottle_code,
            client_id=client_id,
            delivery_id=delivery_id,
        )
        return {"success": True, "message": "Botellón vacío recibido", "data": result}

    async def _send_bottle_to_wash(self, bottle_code: str) -> dict[str, Any]:
        """Envía botellón vacío a lavado en planta."""
        result = await self.bottle_tracker.send_to_wash(bottle_code)
        return {"success": True, "message": "Botellón enviado a lavado", "data": result}

    async def _confirm_delivery(
        self,
        bottle_code: str,
        client_id: int,
    ) -> dict[str, Any]:
        """Confirma entrega al cliente (with_client)."""
        result = await self.bottle_tracker.confirm_delivery(
            bottle_code=bottle_code,
            client_id=client_id,
        )
        return {"success": True, "message": "Entrega confirmada", "data": result}

    # ----------------------------------------------------------------------
    # Action: get_driver_status
    # ----------------------------------------------------------------------
    async def _get_driver_status(self, vehicle_id: int) -> dict[str, Any]:
        """Estado actual del chofer/vehículo."""
        from skills.dispatch.telegram_bot import get_vehicle_by_id

        vehicle = get_vehicle_by_id(vehicle_id)
        if not vehicle:
            return {
                "success": False,
                "message": f"Vehículo {vehicle_id} no encontrado",
                "data": None,
            }

        # Timeline GPS de las últimas 24h para estado de ubicación
        timeline: list[dict[str, Any]] = []
        try:
            timeline = self.gps_tracker.get_vehicle_timeline(vehicle_id, hours_back=24)
        except Exception as e:
            logger.warning("No se pudo obtener timeline GPS para vehículo %s: %s", vehicle_id, e)

        last_gps = timeline[-1] if timeline else None

        data = {
            "vehicle_id": vehicle_id,
            "name": vehicle.get("name"),
            "operator_name": vehicle.get("operator_name"),
            "telegram_chat_id": vehicle.get("telegram_chat_id"),
            "active": bool(vehicle.get("active", 0)),
            "last_gps": last_gps,
            "gps_points_24h": len(timeline),
        }
        return {"success": True, "message": "Estado chofer", "data": data}

    # ----------------------------------------------------------------------
    # Action: delivery_delivered
    # ----------------------------------------------------------------------
    async def _delivery_delivered(
        self,
        client_id: int,
        delivery_id: int,
    ) -> dict[str, Any]:
        """Confirma entrega y asigna botellón disponible al cliente (SWAP flow)."""
        # Buscar un botellón disponible para asignar
        available_bottle = await self.bottle_tracker.get_available_bottle()
        if not available_bottle:
            return {
                "success": False,
                "message": "No hay botellones disponibles para asignar",
                "data": None,
            }

        bottle_code = available_bottle["bottle_code"]

        # Asignar botellón al cliente (in_transit_full -> with_client)
        result = await self.bottle_tracker.assign_to_client(
            bottle_code=bottle_code,
            client_id=client_id,
            delivery_id=delivery_id,
        )
        return {
            "success": True,
            "message": "Entrega confirmada y botellón asignado a cliente",
            "data": result,
        }

    # ----------------------------------------------------------------------
    # Action: handle_telegram_update
    # ----------------------------------------------------------------------
    async def _handle_telegram_update(self, update: dict[str, Any]) -> dict[str, Any]:
        """Procesa update de Telegram Bot choferes vía DispatcherTelegramBot."""
        try:
            bot = self.telegram_bot
            # Asegurar que la aplicación está inicializada
            if bot.app is None:
                bot.app = Application.builder().token(bot.token).build()
                # Configurar handlers (copiado de run())
                bot.app.add_handler(CommandHandler("start", bot.cmd_start))
                bot.app.add_handler(CommandHandler("ruta", bot.cmd_ruta))
                bot.app.add_handler(CommandHandler("siguiente", bot.cmd_siguiente))
                bot.app.add_handler(CommandHandler("status", bot.cmd_status))
                bot.app.add_handler(CommandHandler("help", bot.cmd_help))
                bot.app.add_handler(CallbackQueryHandler(bot.callback_registro, pattern="^reg_"))
                bot.app.add_handler(
                    CallbackQueryHandler(bot.callback_accion, pattern="^(arr_|del_|no_|new_)")
                )
                bot.app.add_handler(CallbackQueryHandler(bot.callback_checkin, pattern="^checkin_"))
                bot.app.add_handler(MessageHandler(filters.LOCATION, bot.handle_location))
                # Inicializar la aplicación
                await bot.app.initialize()
            await bot.app.process_update(update)
            return {"success": True, "message": "Update procesado", "data": None}
        except Exception as e:
            self.logger.exception("Error procesando telegram update: %s", e)
            return self._error(f"Error procesando telegram update: {e}")

    # ----------------------------------------------------------------------
    # Helpers
    # ----------------------------------------------------------------------
    def _success(self, message: str, data: Any = None) -> dict[str, Any]:
        return {
            "success": True,
            "message": message,
            "data": data,
            "error": None,
            "skill": self.name,
        }

    def _error(self, message: str) -> dict[str, Any]:
        self.logger.error("skill_error", skill=self.name, error=message)
        return {
            "success": False,
            "message": None,
            "data": None,
            "error": message,
            "skill": self.name,
        }


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
