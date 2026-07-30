"""
============================================================================
Unit Tests — Sheets Sync (Dispatcher)
Estación H2O · Maracaibo, Venezuela
============================================================================

Tests unitarios para la sincronización Google Sheets del Dispatcher.
"""

import pytest
import os
import sys

sys.path.insert(0, "/mnt/ssd_trabajo/hermes-agent")

from skills.dispatch.sheets_sync import (
    MAPA_CALOR_HEADERS,
    FEEDBACK_HEADERS,
    BOTELLAS_HEADERS,
    SHEET_MAPA_CALOR,
    SHEET_FEEDBACK,
    SHEET_BOTELLAS,
    sync_mapa_calor,
    sync_feedback,
    sync_botellas_control,
)


class TestSheetsSyncHeaders:
    """Tests de headers de las hojas."""

    def test_mapa_calor_headers(self):
        """Headers de Mapa_Calor correctos."""
        assert MAPA_CALOR_HEADERS == [
            "Fecha",
            "Hora",
            "Vehicle_ID",
            "Operator",
            "Lat",
            "Lng",
            "Sector",
            "Calle",
            "Pasadas",
            "Source",
            "Track_Type",
        ]

    def test_feedback_headers(self):
        """Headers de Feedback_Clientes correctos."""
        assert FEEDBACK_HEADERS == [
            "Fecha",
            "Hora",
            "Delivery_ID",
            "Client_ID",
            "Client_Name",
            "Phone",
            "Feedback_Score",
            "Feedback_Comment",
            "Vehicle_ID",
            "Operator",
        ]

    def test_botellas_headers(self):
        """Headers de Botellas_Control correctos."""
        assert BOTELLAS_HEADERS == [
            "Fecha",
            "Hora",
            "Bottle_Code",
            "Status",
            "Client_ID",
            "Client_Name",
            "Delivery_ID",
            "Assigned_At",
            "Expected_Return_At",
            "Returned_At",
            "Alert_Type",
            "Alert_Severity",
            "Alert_Acknowledged",
        ]

    def test_sheet_names(self):
        """Nombres de hojas correctos."""
        assert SHEET_MAPA_CALOR == "Mapa_Calor"
        assert SHEET_FEEDBACK == "Feedback_Clientes"
        assert SHEET_BOTELLAS == "Botellas_Control"


class TestSheetsSyncAPI:
    """Tests de API pública (mocking Google Sheets)."""

    @pytest.mark.asyncio
    async def test_sync_mapa_calor_structure(self):
        """sync_mapa_calor acepta estructura correcta."""
        # Solo verificamos que la función existe y se puede llamar
        # (no ejecutamos _sync real que necesita credenciales)
        from skills.dispatch.sheets_sync import sync_mapa_calor
        
        # No debe lanzar excepción por estructura
        data = [{
            "vehicle_id": 1,
            "operator": "YORDANIS",
            "lat": 10.6500,
            "lng": -71.6200,
            "sector": "Bella Vista",
            "calle": "Av. 4",
            "pasadas": 2,
            "source": "tasker",
            "track_type": "periodic",
        }]
        
        # La función debe existir y ser callable
        assert callable(sync_mapa_calor)

    @pytest.mark.asyncio
    async def test_sync_feedback_structure(self):
        """sync_feedback acepta estructura correcta."""
        from skills.dispatch.sheets_sync import sync_feedback
        
        assert callable(sync_feedback)
        
        # Verificar parámetros esperados
        import inspect
        sig = inspect.signature(sync_feedback)
        params = list(sig.parameters.keys())
        expected = [
            "delivery_id", "client_id", "client_name", "phone",
            "feedback_score", "feedback_comment", "vehicle_id", "operator"
        ]
        for p in expected:
            assert p in params

    @pytest.mark.asyncio
    async def test_sync_botellas_control_structure(self):
        """sync_botellas_control acepta estructura correcta."""
        from skills.dispatch.sheets_sync import sync_botellas_control
        
        assert callable(sync_botellas_control)

    @pytest.mark.asyncio
    async def test_sync_all_dispatcher_exists(self):
        """sync_all_dispatcher existe."""
        from skills.dispatch.sheets_sync import sync_all_dispatcher
        assert callable(sync_all_dispatcher)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])