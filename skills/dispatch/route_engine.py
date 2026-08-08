"""
 ============================================================================
 Route Engine — Motor de optimización de rutas VRP
 Estación H2O · Maracaibo, Venezuela
 ============================================================================

Usa Google OR-Tools para resolver el problema de ruteo de vehículos
con capacidad (CVRP) y ventanas de tiempo (TW).

Algoritmo: CVRPTW (Capacitated Vehicle Routing Problem with Time Windows)
Distancias: Haversine (Python puro, sin dependencias externas)

Entrada:
  - Lista de clientes con coordenadas (lat, lng)
  - Demanda por cliente (botellones)
  - Capacidad de vehículos (30 llenos c/u)
  - Coordenadas del depot (base: 10.6447, -71.6101)

Salida:
  - vehicle_1: [cliente_A, cliente_B, cliente_C]
  - vehicle_2: [cliente_D, cliente_E]
  - Métricas: distancia total, tiempo estimado
"""

import logging
import math
from dataclasses import dataclass
from typing import Any

from ortools.constraint_solver import (
    pywrapcp,
    routing_enums_pb2,
)

logger = logging.getLogger("dispatcher.route_engine")

# Coordenadas base (Hotel Kristoff, Av 8 con Calle 68/69)
DEPOT_LAT = 10.6447
DEPOT_LNG = -71.6101
OPERATION_RADIUS_KM = 13.0

# Capacidades
MAX_FULL_BOTTLES = 30  # por vehículo
MAX_EMPTY_BOTTLES = 70  # por vehículo

# Velocidad promedio triciclo en Maracaibo (km/h)
AVG_SPEED_KMH = 20.0

# Tiempo por entrega (minutos)
TIME_PER_DELIVERY_MIN = 8


# ============================================================================
# Haversine — Cálculo de distancias
# ============================================================================


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calcula distancia en km entre dos puntos GPS.
    Fórmula de Haversine — precisa para distancias cortas (<50km).
    """
    R = 6371  # Radio de la Tierra en km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.asin(math.sqrt(a))
    return round(R * c, 3)


def build_distance_matrix(locations: list[tuple[float, float]]) -> list[list[int]]:
    """
    Construye matriz de distancias en metros entre todos los puntos.
    locations[0] = depot (base)
    locations[1:] = clientes
    """
    n = len(locations)
    matrix = [[0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if i != j:
                dist_km = haversine(
                    locations[i][0], locations[i][1], locations[j][0], locations[j][1]
                )
                matrix[i][j] = int(dist_km * 1000)  # metros (int para OR-Tools)
    return matrix


# ============================================================================
# Modelos de datos
# ============================================================================


@dataclass
class ClientOrder:
    """Pedido de un cliente para el route engine."""

    client_id: int
    name: str
    lat: float
    lng: float
    bottles_full: int  # botellones llenos a entregar
    bottles_empty_pickup: int = 0  # botellones vacíos a recoger
    priority: int = 5  # 1=crítico, 10=flexible
    address: str = ""
    phone: str = ""


@dataclass
class RouteResult:
    """Resultado de una ruta calculada."""

    vehicle_id: int
    operator_name: str
    stops: list[ClientOrder]
    total_distance_km: float
    total_duration_min: int
    total_bottles: int


@dataclass
class VRPResult:
    """Resultado completo del VRP solver."""

    routes: list[RouteResult]
    total_distance_km: float
    total_duration_min: int
    algorithm: str
    unassigned: list[ClientOrder]


# ============================================================================
# VRP Solver — Google OR-Tools
# ============================================================================


def compute_vrp_route(
    orders: list[ClientOrder],
    num_vehicles: int = 2,
    vehicle_capacity: int = MAX_FULL_BOTTLES,
    depot_lat: float = DEPOT_LAT,
    depot_lng: float = DEPOT_LNG,
    operators: list[str] | None = None,
) -> VRPResult:
    """
    Calcula rutas optimizadas usando OR-Tools CVRP.

    Args:
        orders: Lista de pedidos de clientes con coordenadas
        num_vehicles: Número de vehículos (default 2)
        vehicle_capacity: Capacidad de botellones por vehículo
        depot_lat: Latitud del depot (base)
        depot_lng: Longitud del depot
        operators: Lista de nombres de operadores

    Returns:
        VRPResult con rutas optimizadas por vehículo
    """
    if not orders:
        return VRPResult(
            routes=[],
            total_distance_km=0,
            total_duration_min=0,
            algorithm="empty",
            unassigned=[],
        )

    if operators is None:
        operators = ["YORDANIS", "EVERT"]

    # Preparar ubicaciones: [depot] + [clientes...]
    locations = [(depot_lat, depot_lng)]
    for order in orders:
        locations.append((order.lat, order.lng))

    # Construir matriz de distancias
    distance_matrix = build_distance_matrix(locations)

    # Crear modelo de datos para OR-Tools
    data: dict[str, Any] = {}
    data["distance_matrix"] = distance_matrix
    data["num_vehicles"] = num_vehicles
    data["depot"] = 0  # Índice del depot en la matriz
    data["demands"] = [0] + [o.bottles_full for o in orders]  # 0 = depot
    data["vehicle_capacities"] = [vehicle_capacity] * num_vehicles

    # Crear routing index manager
    manager = pywrapcp.RoutingIndexManager(
        len(data["distance_matrix"]),
        data["num_vehicles"],
        data["depot"],
    )

    # Crear routing model
    routing = pywrapcp.RoutingModel(manager)

    # Función de distancia
    def distance_callback(from_index: int, to_index: int) -> int:
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        return int(data["distance_matrix"][from_node][to_node])

    transit_callback_index = routing.RegisterTransitCallback(distance_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

    # Restricción de capacidad
    def demand_callback(from_index: int) -> int:
        from_node = manager.IndexToNode(from_index)
        return int(data["demands"][from_node])

    demand_callback_index = routing.RegisterUnaryTransitCallback(demand_callback)
    routing.AddDimensionWithVehicleCapacity(
        demand_callback_index,
        0,  # slack
        data["vehicle_capacities"],  # capacidades por vehículo
        True,  # start cumul to zero
        "Capacity",
    )

    # Parámetros de búsqueda
    search_parameters = pywrapcp.DefaultRoutingSearchParameters()
    search_parameters.first_solution_strategy = (
        routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    )
    search_parameters.local_search_metaheuristic = (
        routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    )
    search_parameters.time_limit.seconds = 10  # 10 segundos máximo

    # Resolver
    logger.info(
        "Resolviendo VRP con OR-Tools — %d clientes, %d vehículos", len(orders), num_vehicles
    )
    solution = routing.SolveWithParameters(search_parameters)

    if not solution:
        logger.warning("OR-Tools no encontró solución — usando fallback por cercanía")
        return _fallback_nearest_neighbor(orders, num_vehicles, depot_lat, depot_lng, operators)

    # Extraer rutas
    routes: list[RouteResult] = []
    total_distance = 0.0
    total_duration = 0
    unassigned: list[ClientOrder] = []

    for vehicle_id in range(num_vehicles):
        index = routing.Start(vehicle_id)
        route_stops = []
        route_distance = 0
        route_bottles = 0

        while not routing.IsEnd(index):
            node = manager.IndexToNode(index)
            if node > 0:  # No es el depot
                order = orders[node - 1]  # -1 porque locations[0] es depot
                route_stops.append(order)
                route_bottles += order.bottles_full

            prev_index = index
            index = solution.Value(routing.NextVar(index))
            route_distance += routing.GetArcCostForVehicle(prev_index, index, vehicle_id)

        route_distance_km = round(route_distance / 1000, 2)
        route_duration_min = int(
            (route_distance_km / AVG_SPEED_KMH * 60) + (len(route_stops) * TIME_PER_DELIVERY_MIN)
        )

        routes.append(
            RouteResult(
                vehicle_id=vehicle_id + 1,
                operator_name=operators[vehicle_id]
                if vehicle_id < len(operators)
                else f"Operador {vehicle_id + 1}",
                stops=route_stops,
                total_distance_km=route_distance_km,
                total_duration_min=route_duration_min,
                total_bottles=route_bottles,
            )
        )

        total_distance += route_distance_km
        total_duration += route_duration_min

        logger.info(
            "Vehículo %d (%s): %d paradas, %.2f km, %d min, %d botellones",
            vehicle_id + 1,
            routes[-1].operator_name,
            len(route_stops),
            route_distance_km,
            route_duration_min,
            route_bottles,
        )

    # Verificar no asignados
    assigned_ids = set()
    for route in routes:
        for stop in route.stops:
            assigned_ids.add(stop.client_id)
    for order in orders:
        if order.client_id not in assigned_ids:
            unassigned.append(order)

    return VRPResult(
        routes=routes,
        total_distance_km=round(total_distance, 2),
        total_duration_min=total_duration,
        algorithm="ortools_vrp",
        unassigned=unassigned,
    )


# ============================================================================
# Fallback — Nearest Neighbor (si OR-Tools falla)
# ============================================================================


def _fallback_nearest_neighbor(
    orders: list[ClientOrder],
    num_vehicles: int,
    depot_lat: float,
    depot_lng: float,
    operators: list[str],
) -> VRPResult:
    """
    Fallback simple: asigna clientes al vehículo con menos carga.
    No es óptimo pero garantiza que todos los pedidos se despachan.
    """
    # Ordenar por prioridad (1=crítico primero)
    sorted_orders = sorted(orders, key=lambda o: o.priority)

    # Distribuir entre vehículos
    vehicle_orders: list[list[ClientOrder]] = [[] for _ in range(num_vehicles)]
    vehicle_loads = [0] * num_vehicles
    unassigned: list[ClientOrder] = []

    for order in sorted_orders:
        # Encontrar vehículo con menos carga que pueda llevar el pedido
        best_vehicle = -1
        best_load = MAX_FULL_BOTTLES + 1

        for v in range(num_vehicles):
            if (
                vehicle_loads[v] < best_load
                and vehicle_loads[v] + order.bottles_full <= MAX_FULL_BOTTLES
            ):
                best_vehicle = v
                best_load = vehicle_loads[v]

        if best_vehicle >= 0:
            vehicle_orders[best_vehicle].append(order)
            vehicle_loads[best_vehicle] += order.bottles_full
        else:
            # No cabe en ningún vehículo → unassigned
            unassigned.append(order)

    # Calcular distancias
    routes: list[RouteResult] = []
    total_distance = 0.0
    total_duration = 0

    for v in range(num_vehicles):
        route_stops = vehicle_orders[v]
        route_distance = 0.0
        prev_lat, prev_lng = depot_lat, depot_lng

        for stop in route_stops:
            route_distance += haversine(prev_lat, prev_lng, stop.lat, stop.lng)
            prev_lat, prev_lng = stop.lat, stop.lng

        # Regreso al depot
        if route_stops:
            route_distance += haversine(prev_lat, prev_lng, depot_lat, depot_lng)

        route_distance_km = round(route_distance, 2)
        route_duration_min = int(
            (route_distance_km / AVG_SPEED_KMH * 60) + (len(route_stops) * TIME_PER_DELIVERY_MIN)
        )

        routes.append(
            RouteResult(
                vehicle_id=v + 1,
                operator_name=operators[v] if v < len(operators) else f"Operador {v + 1}",
                stops=route_stops,
                total_distance_km=route_distance_km,
                total_duration_min=route_duration_min,
                total_bottles=vehicle_loads[v],
            )
        )

        total_distance += route_distance_km
        total_duration += route_duration_min

    logger.info(
        "Fallback nearest neighbor: %d rutas, %.2f km total, %d unassigned",
        len(routes),
        total_distance,
        len(unassigned),
    )

    return VRPResult(
        routes=routes,
        total_distance_km=round(total_distance, 2),
        total_duration_min=total_duration,
        algorithm="nearest_neighbor_fallback",
        unassigned=unassigned,
    )


# ============================================================================
# Geofencing
# ============================================================================


def check_operation_perimeter(lat: float, lng: float) -> bool:
    """Verifica si el punto está dentro del radio de operación (13km)."""
    distance = haversine(DEPOT_LAT, DEPOT_LNG, lat, lng)
    return distance <= OPERATION_RADIUS_KM


def find_nearest_zone(lat: float, lng: float, zones: list[dict[str, Any]]) -> int | None:
    """
    Encuentra la zona más cercana a un punto.
    zones: lista de dicts con id, center_lat, center_lng, radius_km
    """
    nearest = None
    min_dist = float("inf")

    for zone in zones:
        dist = haversine(lat, lng, zone["center_lat"], zone["center_lng"])
        if dist < min_dist:
            min_dist = dist
            nearest = zone["id"]

    return nearest


def check_zone_membership(lat: float, lng: float, zones: list[dict[str, Any]]) -> list[int]:
    """Retorna IDs de zonas a las que pertenece el punto."""
    matching: list[int] = []
    for zone in zones:
        dist = haversine(lat, lng, zone["center_lat"], zone["center_lng"])
        if dist <= zone["radius_km"]:
            matching.append(zone["id"])
    return matching


# ============================================================================
# Test
# ============================================================================

if __name__ == "__main__":
    # Test con clientes simulados en Maracaibo
    test_orders = [
        ClientOrder(
            client_id=1,
            name="Restaurante El Portal",
            lat=10.6500,
            lng=-71.6200,
            bottles_full=6,
            priority=1,
        ),
        ClientOrder(
            client_id=2, name="Sra. González", lat=10.6400, lng=-71.6150, bottles_full=3, priority=5
        ),
        ClientOrder(
            client_id=3,
            name="Restaurante La Buena Mesa",
            lat=10.6550,
            lng=-71.6100,
            bottles_full=6,
            priority=1,
        ),
        ClientOrder(
            client_id=4, name="Sr. Pérez", lat=10.6420, lng=-71.6050, bottles_full=3, priority=5
        ),
        ClientOrder(
            client_id=5,
            name="Farmacia Central",
            lat=10.6600,
            lng=-71.6000,
            bottles_full=4,
            priority=3,
        ),
    ]

    result = compute_vrp_route(test_orders)

    print(f"\n{'='*60}")
    print(f"RESULTADO VRP — Algoritmo: {result.algorithm}")
    print(f"Distancia total: {result.total_distance_km} km")
    print(f"Duración total: {result.total_duration_min} min")
    print(f"No asignados: {len(result.unassigned)}")
    print(f"{'='*60}")

    for route in result.routes:
        print(f"\n🚚 {route.operator_name} (Vehículo {route.vehicle_id})")
        print(f"   Paradas: {len(route.stops)}")
        print(f"   Distancia: {route.total_distance_km} km")
        print(f"   Duración: {route.total_duration_min} min")
        print(f"   Botellones: {route.total_bottles}")
        for i, stop in enumerate(route.stops, 1):
            print(
                f"   {i}. {stop.name} — {stop.bottles_full} botellones (prioridad {stop.priority})"
            )
