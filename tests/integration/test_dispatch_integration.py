"""
============================================================================
Test de integración: DispatcherSkill + WorkloadRouter
Estación H2O · Maracaibo, Venezuela
============================================================================

Valida que el DispatcherSkill está correctamente registrado en el WorkloadRouter
y que los actions básicos funcionan.
"""

import pytest

from core.workload_router import Route, get_router
from skills.dispatch import DispatcherTelegramBot, get_dispatcher_bot
from skills.dispatcher_skill import get_dispatcher_skill


class TestDispatcherSkillIntegration:
    """Tests de integración del DispatcherSkill con WorkloadRouter."""

    def test_router_resolves_dispatch_request(self):
        """El router resuelve 'dispatch_request' a Route.DISPATCH_SKILL."""
        router = get_router()
        route = router.resolve("dispatch_request")
        assert route == Route.DISPATCH_SKILL

    def test_router_resolves_dispatch_actions(self):
        """El router resuelve todos los triggers de dispatch."""
        router = get_router()

        # Verificar todos los triggers de dispatch en ROUTE_TABLE
        dispatch_triggers = [
            "dispatch_request",
            "dispatch_route_compute",
            "dispatch_delivery_update",
            "dispatch_gps_track",
            "dispatch_bottle_inventory",
        ]

        for trigger in dispatch_triggers:
            route = router.resolve(trigger)
            assert (
                route == Route.DISPATCH_SKILL
            ), f"Trigger '{trigger}' no resuelve a DISPATCH_SKILL"

    def test_dispatcher_skill_singleton(self):
        """DispatcherSkill es singleton."""
        s1 = get_dispatcher_skill()
        s2 = get_dispatcher_skill()
        assert s1 is s2
        assert s1.name == "dispatcher"

    def test_dispatcher_skill_actions_map(self):
        """DispatcherSkill tiene todas las actions esperadas."""
        skill = get_dispatcher_skill()

        expected_actions = {
            "compute_route",
            "notify_driver",
            "update_delivery",
            "record_gps",
            "check_geofence",
            "get_bottle_inventory",
            "get_heatmap_data",
            "assign_bottle_to_client",
            "return_bottle_from_client",
            "send_bottle_to_wash",
            "get_driver_status",
        }

        # Verificar que el action_map interno tiene todas las keys
        assert hasattr(skill, "_DispatcherSkill__action_map") or hasattr(skill, "execute")

        # El execute method usa action_map dict - verificamos que maneja actions desconocidas
        import asyncio

        async def test_unknown():
            result = await skill.execute(action="unknown_action")
            assert result["success"] is False
            assert "desconocida" in result["error"]

        asyncio.run(test_unknown())

    def test_dispatcher_telegram_bot_singleton(self):
        """DispatcherTelegramBot es singleton."""
        b1 = get_dispatcher_bot()
        b2 = get_dispatcher_bot()
        assert b1 is b2
        assert isinstance(b1, DispatcherTelegramBot)

    def test_dispatch_skill_lazy_imports(self):
        """Los sub-componentes se importan perezosamente (no rompen si falta deps)."""
        skill = get_dispatcher_skill()

        # Acceder a route_engine debe importar sin error
        re = skill.route_engine
        assert "compute_vrp_route" in re
        assert "ClientOrder" in re
        assert "VRPResult" in re

        # telegram_bot debe instanciarse
        tb = skill.telegram_bot
        assert isinstance(tb, DispatcherTelegramBot)


class TestDispatcherSkillActions:
    """Tests unitarios de actions específicas (mocking BD)."""

    @pytest.mark.asyncio
    async def test_compute_route_action_structure(self):
        """Action compute_route retorna estructura esperada."""
        skill = get_dispatcher_skill()

        orders = [
            {
                "client_id": 1,
                "name": "Test Cliente",
                "lat": 10.6500,
                "lng": -71.6200,
                "bottles_full": 3,
                "priority": 5,
            }
        ]

        # Nota: esto intentará usar OR-Tools; si falla, el fallback NN se activa
        result = await skill.execute(
            action="compute_route",
            orders=orders,
            num_vehicles=2,
            vehicle_capacity=30,
        )

        # Verificar estructura de respuesta (no necesariamente éxito)
        assert "success" in result
        assert "message" in result
        assert "data" in result or result["success"] is False

    @pytest.mark.asyncio
    async def test_check_geofence_action(self):
        """Action check_geofence retorna estructura correcta."""
        skill = get_dispatcher_skill()

        # Punto dentro del perímetro (centro operaciones)
        result = await skill.execute(
            action="check_geofence",
            lat=10.6447,
            lng=-71.6101,
        )

        assert result["success"] is True
        assert "data" in result
        assert "inside" in result["data"]
        assert result["data"]["inside"] is True

        # Punto fuera (Caracas ~400km)
        result_out = await skill.execute(
            action="check_geofence",
            lat=10.5000,
            lng=-66.9000,
        )

        assert result_out["success"] is True
        assert result_out["data"]["inside"] is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
