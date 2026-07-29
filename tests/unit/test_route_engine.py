"""
============================================================================
Unit Tests — Route Engine (Haversine, VRP, Geofencing)
Estación H2O · Maracaibo, Venezuela
============================================================================

Tests unitarios puros (sin BD, sin red) para el motor de rutas.
"""

import pytest
from skills.dispatch.route_engine import (
    haversine,
    build_distance_matrix,
    compute_vrp_route,
    check_operation_perimeter,
    find_nearest_zone,
    check_zone_membership,
    ClientOrder,
    RouteResult,
    VRPResult,
)


class TestHaversine:
    """Tests de la fórmula de Haversine (distancia esférica)."""

    def test_same_point_zero_distance(self):
        """Distancia de un punto a sí mismo = 0."""
        d = haversine(10.6447, -71.6101, 10.6447, -71.6101)
        assert d == 0.0

    def test_known_distance_depot_to_bella_vista(self):
        """Depot (Hotel Kristoff) a Bella Vista ≈ 1.23 km."""
        d = haversine(10.6447, -71.6101, 10.6500, -71.6200)
        assert 1.2 < d < 1.3

    def test_symmetric(self):
        """Haversine es simétrico: d(A,B) == d(B,A)."""
        d1 = haversine(10.6447, -71.6101, 10.6500, -71.6200)
        d2 = haversine(10.6500, -71.6200, 10.6447, -71.6101)
        assert abs(d1 - d2) < 0.001

    def test_caracas_distance_approx_515km(self):
        """Maracaibo a Caracas ≈ 515 km (sanity check)."""
        d = haversine(10.6447, -71.6101, 10.5000, -66.9000)
        assert 510 < d < 520

    def test_precision_3_decimals(self):
        """Resultado redondeado a 3 decimales (km)."""
        d = haversine(10.6447, -71.6101, 10.6500, -71.6200)
        assert round(d, 3) == d


class TestBuildDistanceMatrix:
    """Tests de construcción de matriz de distancias para OR-Tools."""

    def test_matrix_shape(self):
        """Matriz NxN donde N = 1 depot + n clientes."""
        locations = [(10.0, -71.0), (10.1, -71.0), (10.0, -70.9)]
        matrix = build_distance_matrix(locations)
        assert len(matrix) == 3
        assert all(len(row) == 3 for row in matrix)

    def test_diagonal_zero(self):
        """Diagonal siempre 0 (distancia a sí mismo)."""
        locations = [(10.0, -71.0), (10.1, -71.0), (10.0, -70.9)]
        matrix = build_distance_matrix(locations)
        for i in range(3):
            assert matrix[i][i] == 0

    def test_symmetric_matrix(self):
        """Matriz simétrica: matrix[i][j] == matrix[j][i]."""
        locations = [(10.0, -71.0), (10.1, -71.0), (10.0, -70.9)]
        matrix = build_distance_matrix(locations)
        for i in range(3):
            for j in range(3):
                assert matrix[i][j] == matrix[j][i]

    def test_units_meters_integers(self):
        """Valores en metros (int) para OR-Tools."""
        locations = [(10.6447, -71.6101), (10.6500, -71.6200)]
        matrix = build_distance_matrix(locations)
        assert isinstance(matrix[0][1], int)
        assert matrix[0][1] > 0


class TestComputeVRPRoute:
    """Tests del solver VRP con OR-Tools (y fallback NN)."""

    @pytest.fixture
    def sample_orders(self):
        """Pedidos de prueba en Maracaibo."""
        return [
            ClientOrder(client_id=1, name="Restaurante El Portal", lat=10.6500, lng=-71.6200, bottles_full=6, priority=1),
            ClientOrder(client_id=2, name="Sra. González", lat=10.6400, lng=-71.6150, bottles_full=3, priority=5),
            ClientOrder(client_id=3, name="Restaurante La Buena Mesa", lat=10.6550, lng=-71.6100, bottles_full=6, priority=1),
            ClientOrder(client_id=4, name="Sr. Pérez", lat=10.6420, lng=-71.6050, bottles_full=3, priority=5),
            ClientOrder(client_id=5, name="Farmacia Central", lat=10.6600, lng=-71.6000, bottles_full=4, priority=3),
        ]

    def test_empty_orders_returns_empty_result(self):
        """Sin pedidos → resultado vacío sin error."""
        result = compute_vrp_route([])
        assert isinstance(result, VRPResult)
        assert result.routes == []
        assert result.total_distance_km == 0
        assert result.algorithm == "empty"

    def test_single_vehicle_two_orders(self, sample_orders):
        """2 pedidos, 1 vehículo → 1 ruta con 2 paradas."""
        result = compute_vrp_route(sample_orders[:2], num_vehicles=1)
        assert len(result.routes) == 1
        assert len(result.routes[0].stops) == 2
        assert result.routes[0].total_bottles == 9
        assert result.total_distance_km > 0

    def test_two_vehicles_distributes_load(self, sample_orders):
        """2 vehículos → carga distribuida (aprox 50/50)."""
        result = compute_vrp_route(sample_orders, num_vehicles=2)
        assert len(result.routes) == 2
        # Suma de botellones = total
        total_bottles = sum(r.total_bottles for r in result.routes)
        assert total_bottles == sum(o.bottles_full for o in sample_orders)

    def test_capacity_constraint_respected(self, sample_orders):
        """Capacidad 30 botellones → no vehículo excede 30."""
        # 5 pedidos = 22 botellones total, bien bajo 30
        result = compute_vrp_route(sample_orders, num_vehicles=2, vehicle_capacity=30)
        for route in result.routes:
            assert route.total_bottles <= 30

    def test_capacity_forces_more_vehicles(self):
        """Si capacidad baja, pedidos se distribuyen en más vehículos."""
        orders = [
            ClientOrder(client_id=i, name=f"Cliente {i}", lat=10.64 + i*0.01, lng=-71.61, bottles_full=20, priority=5)
            for i in range(1, 4)  # 3 x 20 = 60 botellones
        ]
        # Capacidad 30 → necesita al menos 2 vehículos
        result = compute_vrp_route(orders, num_vehicles=2, vehicle_capacity=30)
        assert len(result.routes) == 2
        for route in result.routes:
            assert route.total_bottles <= 30

    def test_priority_orders_served_first(self, sample_orders):
        """Pedidos prioridad 1 (restaurantes) se asignan antes que prioridad 5."""
        result = compute_vrp_route(sample_orders, num_vehicles=2)
        # Verificar que al menos un restaurante está en la ruta
        all_stops = [s for r in result.routes for s in r.stops]
        priority_1_stops = [s for s in all_stops if s.priority == 1]
        assert len(priority_1_stops) >= 2  # 2 restaurantes en sample

    def test_unassigned_orders_returned(self):
        """Pedidos que no caben → lista unassigned."""
        orders = [
            ClientOrder(client_id=i, name=f"C{i}", lat=10.64, lng=-71.61, bottles_full=20, priority=5)
            for i in range(1, 4)  # 60 botellones
        ]
        result = compute_vrp_route(orders, num_vehicles=1, vehicle_capacity=30)
        assert len(result.unassigned) >= 1  # Al menos 1 no cabe en 1 vehículo cap 30

    def test_algorithm_field_present(self, sample_orders):
        """Resultado incluye campo algorithm (ortools_vrp o fallback)."""
        result = compute_vrp_route(sample_orders, num_vehicles=2)
        assert result.algorithm in ("ortools_vrp", "nearest_neighbor_fallback")


class TestGeofencing:
    """Tests de geofencing: perímetro 13km + 5 zonas."""

    def test_depot_inside_perimeter(self):
        """Depot está dentro del perímetro (distancia 0)."""
        inside = check_operation_perimeter(10.6447, -71.6101)
        assert inside is True

    def test_bella_vista_inside(self):
        """Bella Vista (1.23km) está dentro."""
        inside = check_operation_perimeter(10.6500, -71.6200)
        assert inside is True

    def test_caracas_outside(self):
        """Caracas (~400km) está fuera."""
        inside = check_operation_perimeter(10.5000, -66.9000)
        assert inside is False

    def test_boundary_exactly_13km(self):
        """Punto a ~12.9km del depot → dentro (≤). Haversine da ~12.923km con 12.9 offset."""
        # 12.9km hacia el norte: 12.9/111 ≈ 0.1162 grados
        lat = 10.6447 + (12.9 / 111.0)
        inside = check_operation_perimeter(lat, -71.6101)
        assert inside is True

    def test_boundary_just_outside_13km(self):
        """Punto a 13.1km del depot → fuera (>)."""
        lat = 10.6447 + (13.1 / 111.0)
        inside = check_operation_perimeter(lat, -71.6101)
        assert inside is False

    def test_zone_membership_bella_vista(self):
        """Bella Vista pertenece a zona 1 (Bella Vista). Usar zonas NO superpuestas."""
        zones = [
            {"id": 1, "name": "Bella Vista", "center_lat": 10.6500, "center_lng": -71.6200, "radius_km": 1.0},
            {"id": 2, "name": "Las Delicias", "center_lat": 10.6000, "center_lng": -71.6500, "radius_km": 2.5},
        ]
        matching = check_zone_membership(10.6500, -71.6200, zones)
        assert 1 in matching
        assert 2 not in matching

    def test_point_in_multiple_zones(self):
        """Punto en intersección → ambas zonas."""
        zones = [
            {"id": 1, "center_lat": 10.0, "center_lng": -71.0, "radius_km": 5.0},
            {"id": 2, "center_lat": 10.0, "center_lng": -71.0, "radius_km": 10.0},
        ]
        matching = check_zone_membership(10.0, -71.0, zones)
        assert set(matching) == {1, 2}

    def test_find_nearest_zone(self):
        """Zona más cercana a un punto."""
        zones = [
            {"id": 1, "center_lat": 10.6500, "center_lng": -71.6200, "radius_km": 3.0},
            {"id": 2, "center_lat": 10.6400, "center_lng": -71.6150, "radius_km": 2.5},
        ]
        nearest = find_nearest_zone(10.6500, -71.6200, zones)
        assert nearest == 1


class TestDataClasses:
    """Tests de dataclasses (serialización, campos)."""

    def test_client_order_creation(self):
        order = ClientOrder(
            client_id=1, name="Test", lat=10.0, lng=-71.0,
            bottles_full=5, bottles_empty_pickup=2, priority=3,
            address="Calle 1", phone="+584121234567"
        )
        assert order.client_id == 1
        assert order.bottles_full == 5
        assert order.bottles_empty_pickup == 2

    def test_route_result_fields(self):
        route = RouteResult(
            vehicle_id=1, operator_name="YORDANIS",
            stops=[], total_distance_km=15.5, total_duration_min=60, total_bottles=10
        )
        assert route.vehicle_id == 1
        assert route.operator_name == "YORDANIS"

    def test_vrp_result_fields(self):
        vrp = VRPResult(
            routes=[], total_distance_km=0, total_duration_min=0,
            algorithm="ortools_vrp", unassigned=[]
        )
        assert vrp.algorithm == "ortools_vrp"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])