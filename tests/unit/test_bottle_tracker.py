#!/usr/bin/env python3
"""
============================================================================
Unit Tests — Bottle Tracker (SWAP: 165 botellones loaner)
Estación H2O · Maracaibo, Venezuela
============================================================================

Tests unitarios para el tracking individual de botellones loaner.
Todas las fixtures se heredan de tests/conftest.py (root).
"""

import pytest
import sys

sys.path.insert(0, "/mnt/ssd_trabajo/hermes-agent")

from skills.dispatch.bottle_tracker import BottleTracker


class TestBottleTracker:
    """Tests para BottleTracker."""

    @pytest.mark.asyncio
    async def test_get_inventory_stats_initial(self, test_db):
        """Verifica estado inicial del inventario."""
        tracker = BottleTracker()
        stats = await tracker.get_inventory_stats()
        
        assert stats["total"] == 165
        assert stats["by_status"].get("available", 0) == 165
        assert stats["overdue_count"] == 0

    @pytest.mark.asyncio
    async def test_assign_to_client(self, test_db):
        """Asigna botellón a un cliente."""
        tracker = BottleTracker()
        
        result = await tracker.assign_to_client(
            bottle_code="H2O-001",
            client_id=1,
            delivery_id=100,
        )
        
        assert result["success"] is True
        assert result["bottle"]["status"] == "in_transit_full"
        assert result["bottle"]["client_id"] == 1
        
        stats = await tracker.get_inventory_stats()
        assert stats["by_status"].get("available", 0) == 164
        assert stats["by_status"].get("in_transit_full", 0) == 1
        
        # Verificar estado en BD
        import sqlite3
        conn = sqlite3.connect("/tmp/test_bottle_tracker.db")
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT bottle_code, status, client_id FROM bottles WHERE bottle_code = 'H2O-001'"
        ).fetchone()
        conn.close()
        
        assert row["status"] == "in_transit_full"
        assert row["client_id"] == 1

    @pytest.mark.asyncio
    async def test_confirm_delivery(self, test_db):
        """Confirma entrega de botellón."""
        tracker = BottleTracker()
        
        # Primero asignar
        await tracker.assign_to_client("H2O-010", client_id=1, delivery_id=200)
        
        # Confirmar entrega
        result = await tracker.confirm_delivery(
            bottle_code="H2O-010",
            client_id=1,
        )
        
        assert result["success"] is True
        assert result["bottle"]["status"] == "with_client"
        
        # Verificar estado
        import sqlite3
        conn = sqlite3.connect("/tmp/test_bottle_tracker.db")
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT bottle_code, status FROM bottles WHERE bottle_code = 'H2O-010'"
        ).fetchone()
        conn.close()
        
        assert row["status"] == "with_client"

    @pytest.mark.asyncio
    async def test_confirm_delivery_wrong_status_fails(self, test_db):
        """Confirma entrega de botellón en estado incorrecto falla."""
        tracker = BottleTracker()
        
        # Intentar confirmar sin asignar primero
        result = await tracker.confirm_delivery(
            bottle_code="H2O-020",
            client_id=1,
        )
        
        assert result["success"] is False
        assert "in_transit_full" in result["error"] or "tránsito" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_return_from_client(self, test_db):
        """Retorno de botellones desde cliente."""
        tracker = BottleTracker()
        
        # Asignar y confirmar entrega
        await tracker.assign_to_client("H2O-050", client_id=1, delivery_id=500)
        await tracker.confirm_delivery("H2O-050", client_id=1)
        
        # Retornar
        result = await tracker.return_from_client(
            bottle_code="H2O-050",
            client_id=1,
            delivery_id=600,
        )
        
        assert result["success"] is True
        assert result["bottle"]["status"] == "in_transit_empty"
        
        # Verificar estado vuelve a available después de wash_complete
        await tracker.send_to_wash("H2O-050", performed_by="plant")
        await tracker.wash_complete("H2O-050", performed_by="plant")
        
        import sqlite3
        conn = sqlite3.connect("/tmp/test_bottle_tracker.db")
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT bottle_code, status FROM bottles WHERE bottle_code = 'H2O-050'"
        ).fetchone()
        conn.close()
        
        assert row["status"] == "available"

    @pytest.mark.asyncio
    async def test_send_to_wash(self, test_db):
        """Envía botellones a lavado."""
        tracker = BottleTracker()
        
        await tracker.assign_to_client("H2O-060", client_id=1, delivery_id=700)
        await tracker.confirm_delivery("H2O-060", client_id=1)
        
        # Enviar a lavado
        result = await tracker.send_to_wash(
            bottle_code="H2O-060",
            performed_by="plant",
        )
        
        assert result["success"] is True
        assert result["bottle"]["status"] == "maintenance"
        
        # Verificar estado
        import sqlite3
        conn = sqlite3.connect("/tmp/test_bottle_tracker.db")
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT status FROM bottles WHERE bottle_code = 'H2O-060'"
        ).fetchone()
        conn.close()
        
        assert row["status"] == "maintenance"

    @pytest.mark.asyncio
    async def test_wash_complete(self, test_db):
        """Completa lavado, botellón vuelve a available."""
        tracker = BottleTracker()
        
        await tracker.assign_to_client("H2O-070", client_id=1, delivery_id=900)
        await tracker.confirm_delivery("H2O-070", client_id=1)
        await tracker.return_from_client("H2O-070", client_id=1, delivery_id=950)
        await tracker.send_to_wash("H2O-070", performed_by="plant")
        
        result = await tracker.wash_complete(
            bottle_code="H2O-070",
            performed_by="plant",
        )
        
        assert result["success"] is True
        assert result["bottle"]["status"] == "available"
        
        import sqlite3
        conn = sqlite3.connect("/tmp/test_bottle_tracker.db")
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT status FROM bottles WHERE bottle_code = 'H2O-070'"
        ).fetchone()
        conn.close()
        
        assert row["status"] == "available"

    @pytest.mark.asyncio
    async def test_full_lifecycle(self, test_db):
        """Ciclo completo: assign → deliver → return → wash → available."""
        tracker = BottleTracker()
        bottle = "H2O-080"
        
        # 1. Asignar
        r = await tracker.assign_to_client(bottle, client_id=1, delivery_id=1100)
        assert r["success"]
        
        # 2. Entregar
        r = await tracker.confirm_delivery(bottle, client_id=1)
        assert r["success"]
        
        # 3. Retornar
        r = await tracker.return_from_client(bottle, client_id=1, delivery_id=1200)
        assert r["success"]
        
        # 3b. Verificar in_transit_empty
        import sqlite3
        conn = sqlite3.connect("/tmp/test_bottle_tracker.db")
        conn.row_factory = sqlite3.Row
        row = conn.execute(f"SELECT status FROM bottles WHERE bottle_code = '{bottle}'").fetchone()
        conn.close()
        assert row["status"] == "in_transit_empty"
        
        # 4. Enviar a lavado
        r = await tracker.send_to_wash(bottle, client_id=1, delivery_id=1300)
        assert r["success"]
        
        # 5. Lavado completo
        r = await tracker.wash_complete(bottle, performed_by="plant")
        assert r["success"]
        
        # 6. Verificar available final
        conn = sqlite3.connect("/tmp/test_bottle_tracker.db")
        conn.row_factory = sqlite3.Row
        row = conn.execute(f"SELECT status FROM bottles WHERE bottle_code = '{bottle}'").fetchone()
        conn.close()
        assert row["status"] == "available"

    @pytest.mark.asyncio
    async def test_movement_history_recorded(self, test_db):
        """Verifica que cada movimiento queda registrado en bottle_movements."""
        tracker = BottleTracker()
        
        await tracker.assign_to_client("H2O-090", client_id=1, delivery_id=1400)
        await tracker.confirm_delivery("H2O-090", client_id=1)
        await tracker.return_from_client("H2O-090", client_id=1, delivery_id=1500)
        await tracker.send_to_wash("H2O-090", performed_by="plant")
        await tracker.wash_complete("H2O-090", performed_by="plant")
        
        import sqlite3
        conn = sqlite3.connect("/tmp/test_bottle_tracker.db")
        conn.row_factory = sqlite3.Row
        movements = conn.execute(
            "SELECT from_status, to_status FROM bottle_movements WHERE bottle_code = 'H2O-090' ORDER BY created_at"
        ).fetchall()
        conn.close()
        
        statuses = [(m["from_status"], m["to_status"]) for m in movements]
        expected = [
            ("available", "in_transit_full"),
            ("in_transit_full", "with_client"),
            ("with_client", "in_transit_empty"),
            ("in_transit_empty", "maintenance"),
            ("maintenance", "available"),
        ]
        assert statuses == expected

    @pytest.mark.asyncio
    async def test_invalid_transition_fails(self, test_db):
        """Transición inválida falla (ej: assign → wash sin deliver)."""
        tracker = BottleTracker()
        
        # Asignar pero no entregar
        await tracker.assign_to_client("H2O-100", client_id=1, delivery_id=1600)
        
        # Intentar lavar sin entregar
        result = await tracker.send_to_wash("H2O-100", performed_by="plant")
        
        assert result["success"] is False
        assert "in_transit_empty" in result["error"] or "maintenance" in result["error"]


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])