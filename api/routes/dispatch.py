"""FastAPI routes para Dispatcher — endpoints internos y webhook Telegram choferes."""

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from core.logger import get_logger
from core.workload_router import get_router

logger = get_logger("dispatch_routes")

router = APIRouter(prefix="/dispatch", tags=["dispatcher"])


# ============================================================================
# Pydantic Models
# ============================================================================


class ComputeRouteRequest(BaseModel):
    orders: list[dict[str, Any]] = Field(default_factory=list)
    num_vehicles: int = 2
    vehicle_capacity: int = 30
    depot_lat: float = 10.6447
    depot_lng: float = -71.6101
    operators: list[str] | None = None


class NotifyDriverRequest(BaseModel):
    vehicle_id: int
    client_name: str
    client_phone: str
    bottles_full: int
    lat: float
    lng: float
    address: str
    total_eur: float = 0
    total_bs: float = 0
    metodo_pago: str = ""


class UpdateDeliveryRequest(BaseModel):
    delivery_id: int
    status: str
    notes: str = ""


class RecordGPSRequest(BaseModel):
    vehicle_id: int
    lat: float
    lng: float
    accuracy: float | None = None
    speed: float | None = None
    source: str = "telegram"
    delivery_id: int | None = None
    track_type: str = "checkin"


class CheckGeofenceRequest(BaseModel):
    lat: float
    lng: float


# ============================================================================
# Endpoints
# ============================================================================


@router.post("/route/compute")  # type: ignore[misc]
async def compute_route(request: ComputeRouteRequest) -> dict[str, Any]:
    """Calcula ruta optimizada (OR-Tools VRP)."""
    router = get_router()
    result = await router.execute(
        trigger="dispatch_request",
        action="compute_route",
        orders=request.orders,
        num_vehicles=request.num_vehicles,
        vehicle_capacity=request.vehicle_capacity,
        depot_lat=request.depot_lat,
        depot_lng=request.depot_lng,
        operators=request.operators,
    )
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "Error computing route"))
    return result


@router.post("/delivery/update")  # type: ignore[misc]
async def update_delivery(request: UpdateDeliveryRequest) -> dict[str, Any]:
    """Actualiza estado de entrega."""
    router = get_router()
    result = await router.execute(
        trigger="dispatch_request",
        action="update_delivery",
        delivery_id=request.delivery_id,
        status=request.status,
        notes=request.notes,
    )
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "Error updating delivery"))
    return result


@router.post("/gps")  # type: ignore[misc]
async def record_gps(request: RecordGPSRequest) -> dict[str, Any]:
    """Registra punto GPS (Tasker o Telegram)."""
    router = get_router()
    result = await router.execute(
        trigger="dispatch_request",
        action="record_gps",
        vehicle_id=request.vehicle_id,
        lat=request.lat,
        lng=request.lng,
        accuracy=request.accuracy,
        speed=request.speed,
        source=request.source,
        delivery_id=request.delivery_id,
        track_type=request.track_type,
    )
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "Error recording GPS"))
    return result


@router.get("/vehicles/status")  # type: ignore[misc]
async def get_vehicles_status() -> dict[str, Any]:
    """Estado de todos los vehículos/choferes."""
    router = get_router()
    result = await router.execute(
        trigger="dispatch_request",
        action="get_driver_status",
        vehicle_id=0,  # 0 = todos
    )
    if not result.get("success"):
        raise HTTPException(
            status_code=500, detail=result.get("error", "Error getting vehicles status")
        )
    return result


@router.get("/bottles/inventory")  # type: ignore[misc]
async def get_bottles_inventory() -> dict[str, Any]:
    """Inventario de botellones loaner (SWAP)."""
    router = get_router()
    result = await router.execute(
        trigger="dispatch_request",
        action="get_bottle_inventory",
    )
    if not result.get("success"):
        raise HTTPException(
            status_code=500, detail=result.get("error", "Error getting bottle inventory")
        )
    return result


@router.post("/geofence/check")  # type: ignore[misc]
async def check_geofence(request: CheckGeofenceRequest) -> dict[str, Any]:
    """Verifica si punto está dentro del perímetro de operación."""
    router = get_router()
    result = await router.execute(
        trigger="dispatch_request",
        action="check_geofence",
        lat=request.lat,
        lng=request.lng,
    )
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "Error checking geofence"))
    return result


@router.post("/notify/driver")  # type: ignore[misc]
async def notify_driver(request: NotifyDriverRequest) -> dict[str, Any]:
    """Envía notificación a chofer por Telegram."""
    router = get_router()
    result = await router.execute(
        trigger="dispatch_request",
        action="notify_driver",
        vehicle_id=request.vehicle_id,
        client_name=request.client_name,
        client_phone=request.client_phone,
        bottles_full=request.bottles_full,
        lat=request.lat,
        lng=request.lng,
        address=request.address,
        total_eur=request.total_eur,
        total_bs=request.total_bs,
        metodo_pago=request.metodo_pago,
    )
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "Error notifying driver"))
    return result


# ============================================================================
# Webhook Telegram Bot Choferes
# ============================================================================


@router.post("/telegram/webhook")  # type: ignore[misc]
async def telegram_webhook(request: Request) -> dict[str, Any]:
    """Webhook para bot Telegram de operadores."""
    try:
        update = await request.json()
        # Procesar via DispatcherSkill
        router = get_router()
        await router.execute(
            trigger="dispatch_request",
            action="handle_telegram_update",
            update=update,
        )
        return {"ok": True}
    except Exception as e:
        logger.exception("Error en webhook Telegram: %s", e)
        return {"ok": False, "error": str(e)}


@router.get("/health")  # type: ignore[misc]
async def health_check() -> dict[str, Any]:
    """Health check del dispatcher."""
    return {
        "status": "healthy",
        "service": "dispatcher",
        "dispatch_db": "/mnt/ssd_trabajo/hermes-agent/data/dispatch.db",
    }


# ============================================================================
# Dispatch Queue Consumer Endpoint
# ============================================================================


@router.post("/process-queue")  # type: ignore[misc]
async def process_queue(max_orders: int = 20) -> dict[str, Any]:
    """Procesa pedidos pending de dispatch_queue en tiempo real.

    Este endpoint consume la dispatch_queue (conversations.db) y:
    1. Lee pedidos pending
    2. Asigna a chofer/vehículo con menos carga
    3. Crea delivery en dispatch.db
    4. Notifica chofer via /dispatch/notify-driver
    5. Marca pedidos como 'enviado'
    """
    from skills.dispatch.consumer import process_queue_endpoint as consumer_process

    return await consumer_process(max_orders=max_orders)
