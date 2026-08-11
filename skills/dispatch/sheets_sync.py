"""
============================================================================
Sheets Sync — Sincronización Google Sheets para Dispatcher
Estación H2O · Maracaibo, Venezuela
============================================================================

Sincroniza tres hojas en Google Sheets:
1. **Mapa_Calor** - cada GPS → sector, calle, pasadas (para heatmap de rutas)
2. **Feedback_Clientes** - feedback_score al completar entrega
3. **Botellas_Control** - inventario loaner (estados, alertas, overdue)

Async fire-and-forget como google_sheets.py actual.
"""

import logging
import os
import threading
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger("dispatch.sheets_sync")

# Cache del cliente gspread (singleton thread-safe)
_sheets_client = None
_sheets_lock = threading.Lock()
_spreadsheet = None

# Zona horaria Caracas (UTC-4)
CARACAS_TZ = timezone(timedelta(hours=-4))

# Configuración (leída de variables de entorno)
GOOGLE_CREDENTIALS_PATH = os.getenv(
    "GOOGLE_CREDENTIALS_PATH",
    "/mnt/ssd_trabajo/hermes-agent/config/google_credentials.json",
)
GOOGLE_SPREADSHEET_ID = os.getenv(
    "GOOGLE_SPREADSHEET_ID",
    "1Bbp4Xqw5E7bb7loJ262K9lMPFinNSIW-ws1i7ZAmiYk",
)
GOOGLE_SHEETS_ENABLED = os.getenv("GOOGLE_SHEETS_ENABLED", "true").lower() == "true"

# Nombres de hojas para Dispatcher
SHEET_MAPA_CALOR = "Mapa_Calor"
SHEET_FEEDBACK = "Feedback_Clientes"
SHEET_BOTELLAS = "Botellas_Control"


def _get_client() -> Any:
    """Inicializa el cliente gspread de forma perezosa (lazy + thread-safe)."""
    global _sheets_client, _spreadsheet
    if _spreadsheet is not None:
        return _spreadsheet

    if not GOOGLE_SHEETS_ENABLED:
        logger.info("Google Sheets deshabilitado (GOOGLE_SHEETS_ENABLED=false)")
        return None

    if not os.path.exists(GOOGLE_CREDENTIALS_PATH):
        logger.warning(
            "Credenciales Google no encontradas en %s — sync NO se ejecutará",
            GOOGLE_CREDENTIALS_PATH,
        )
        return None

    try:
        import gspread
        from google.oauth2.service_account import Credentials

        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = Credentials.from_service_account_file(GOOGLE_CREDENTIALS_PATH, scopes=scopes)
        # gspread v6+: authorize() es la forma recomendada
        _sheets_client = gspread.authorize(creds)
        _spreadsheet = _sheets_client.open_by_key(GOOGLE_SPREADSHEET_ID)
        logger.info(
            "Google Sheets conectado (Dispatcher): spreadsheet=%s",
            GOOGLE_SPREADSHEET_ID[:12] + "...",
        )
        return _spreadsheet
    except ImportError:
        logger.warning(
            "gspread no instalado — sync NO se ejecutará. "
            "Instala con: pip install gspread google-auth"
        )
        return None
    except Exception as e:
        logger.error("Error conectando a Google Sheets (Dispatcher): %s", e)
        return None


def _get_or_create_worksheet(spreadsheet: Any, title: str, headers: list[str]) -> Any:
    """Obtiene la hoja o la crea con headers si no existe."""
    try:
        return spreadsheet.worksheet(title)
    except Exception:
        worksheet = spreadsheet.add_worksheet(title=title, rows=1000, cols=30)
        worksheet.update("A1", [headers])
        logger.info("Hoja '%s' creada con headers", title)
        return worksheet


# ============================================================================
# MAPA_CALOR - GPS Heatmap
# ============================================================================

MAPA_CALOR_HEADERS = [
    "Fecha",
    "Hora",
    "Vehicle_ID",
    "Operator",
    "Lat",
    "Lng",
    "Sector",
    "Calle",
    "Pasadas",
    "Source",  # tasker | telegram | checkin
    "Track_Type",  # periodic | checkin_arrive | checkin_depart
]


async def _save_mapa_calor_async(data: list[dict[str, Any]]) -> None:
    """Guarda puntos GPS en hoja Mapa_Calor (fire-and-forget)."""

    def _sync():
        spreadsheet = _get_client()
        if not spreadsheet:
            return
        ws = _get_or_create_worksheet(spreadsheet, SHEET_MAPA_CALOR, MAPA_CALOR_HEADERS)

        now = datetime.now(CARACAS_TZ)
        fecha = now.strftime("%Y-%m-%d")
        hora = now.strftime("%H:%M:%S")

        rows = []
        for d in data:
            rows.append(
                [
                    fecha,
                    hora,
                    d.get("vehicle_id", ""),
                    d.get("operator", ""),
                    d.get("lat", ""),
                    d.get("lng", ""),
                    d.get("sector", ""),
                    d.get("calle", ""),
                    d.get("pasadas", 1),
                    d.get("source", "tasker"),
                    d.get("track_type", "periodic"),
                ]
            )

        if rows:
            ws.append_rows(rows, value_input_option="USER_ENTERED")
            logger.info("Mapa_Calor: %d filas guardadas", len(rows))

    thread = threading.Thread(target=_sync, daemon=True)
    thread.start()


# ============================================================================
# FEEDBACK_CLIENTES
# ============================================================================

FEEDBACK_HEADERS = [
    "Fecha",
    "Hora",
    "Delivery_ID",
    "Client_ID",
    "Client_Name",
    "Phone",
    "Feedback_Score",  # 1-5
    "Feedback_Comment",
    "Vehicle_ID",
    "Operator",
]


async def _save_feedback_async(data: list[dict[str, Any]]) -> None:
    """Guarda feedback de clientes en hoja Feedback_Clientes (fire-and-forget)."""

    def _sync():
        spreadsheet = _get_client()
        if not spreadsheet:
            return
        ws = _get_or_create_worksheet(spreadsheet, SHEET_FEEDBACK, FEEDBACK_HEADERS)

        now = datetime.now(CARACAS_TZ)
        fecha = now.strftime("%Y-%m-%d")
        hora = now.strftime("%H:%M:%S")

        rows = []
        for d in data:
            rows.append(
                [
                    fecha,
                    hora,
                    d.get("delivery_id", ""),
                    d.get("client_id", ""),
                    d.get("client_name", ""),
                    d.get("phone", ""),
                    d.get("feedback_score", ""),
                    d.get("feedback_comment", ""),
                    d.get("vehicle_id", ""),
                    d.get("operator", ""),
                ]
            )

        if rows:
            ws.append_rows(rows, value_input_option="USER_ENTERED")
            logger.info("Feedback_Clientes: %d filas guardadas", len(rows))

    thread = threading.Thread(target=_sync, daemon=True)
    thread.start()


# ============================================================================
# BOTELLAS_CONTROL - Inventario Loaner
# ============================================================================

BOTELLAS_HEADERS = [
    "Fecha",
    "Hora",
    "Bottle_Code",
    "Status",  # available | in_transit_full | with_client |
    # in_transit_empty | maintenance | retired
    "Client_ID",
    "Client_Name",
    "Delivery_ID",
    "Assigned_At",
    "Expected_Return_At",
    "Returned_At",
    "Alert_Type",  # overdue_return | maintenance_due | lost | damaged
    "Alert_Severity",
    "Alert_Acknowledged",
]


async def _save_botellas_control_async(data: list[dict[str, Any]]) -> None:
    """Guarda inventario de botellones en hoja Botellas_Control (fire-and-forget)."""

    def _sync():
        spreadsheet = _get_client()
        if not spreadsheet:
            return
        ws = _get_or_create_worksheet(spreadsheet, SHEET_BOTELLAS, BOTELLAS_HEADERS)

        now = datetime.now(CARACAS_TZ)
        fecha = now.strftime("%Y-%m-%d")
        hora = now.strftime("%H:%M:%S")

        rows = []
        for d in data:
            rows.append(
                [
                    fecha,
                    hora,
                    d.get("bottle_code", ""),
                    d.get("status", ""),
                    d.get("client_id", ""),
                    d.get("client_name", ""),
                    d.get("delivery_id", ""),
                    d.get("assigned_at", ""),
                    d.get("expected_return_at", ""),
                    d.get("returned_at", ""),
                    d.get("alert_type", ""),
                    d.get("alert_severity", ""),
                    d.get("acknowledged", 0),
                ]
            )

        if rows:
            ws.append_rows(rows, value_input_option="USER_ENTERED")
            logger.info("Botellas_Control: %d filas guardadas", len(rows))

    thread = threading.Thread(target=_sync, daemon=True)
    thread.start()


# ============================================================================
# API PÚBLICA - Entry Points
# ============================================================================


async def sync_mapa_calor(gps_points: list[dict[str, Any]]) -> None:
    """
    Sincroniza puntos GPS a hoja Mapa_Calor.

    Args:
        gps_points: lista de dicts con keys:
            - vehicle_id, operator, lat, lng, sector, calle,
              pasadas (default 1), source, track_type
    """
    await _save_mapa_calor_async(gps_points)


async def sync_feedback(
    delivery_id: int,
    client_id: int,
    client_name: str,
    phone: str,
    feedback_score: int,
    feedback_comment: str = "",
    vehicle_id: int = 0,
    operator: str = "",
) -> None:
    """
    Sincroniza feedback de cliente a hoja Feedback_Clientes.

    Args:
        delivery_id: ID de la entrega
        client_id: ID del cliente
        client_name: Nombre del cliente
        phone: Teléfono
        feedback_score: 1-5
        feedback_comment: Comentario opcional
        vehicle_id: ID del vehículo
        operator: Nombre del operador
    """
    data = [
        {
            "delivery_id": delivery_id,
            "client_id": client_id,
            "client_name": client_name,
            "phone": phone,
            "feedback_score": feedback_score,
            "feedback_comment": feedback_comment,
            "vehicle_id": vehicle_id,
            "operator": operator,
        }
    ]
    await _save_feedback_async(data)


async def sync_botellas_control(bottles_data: list[dict[str, Any]]) -> None:
    """
    Sincroniza inventario de botellones a hoja Botellas_Control.

    Args:
        bottles_data: lista de dicts con keys:
            - bottle_code, status, client_id, client_name,
              delivery_id, assigned_at, expected_return_at, returned_at,
              alert_type, alert_severity, acknowledged
    """
    data = []
    for b in bottles_data:
        data.append(
            {
                "bottle_code": b.get("bottle_code", ""),
                "status": b.get("status", ""),
                "client_id": b.get("client_id", ""),
                "client_name": b.get("client_name", ""),
                "delivery_id": b.get("delivery_id", ""),
                "assigned_at": b.get("assigned_at", ""),
                "expected_return_at": b.get("expected_return_at", ""),
                "returned_at": b.get("returned_at", ""),
                "alert_type": b.get("alert_type", ""),
                "alert_severity": b.get("alert_severity", ""),
                "acknowledged": b.get("acknowledged", 0),
            }
        )
    await _save_botellas_control_async(data)


async def sync_all_dispatcher() -> None:
    """
    Sincronización completa de todo el estado actual del dispatcher.
    Se ejecuta periódicamente (ej: cada hora) o bajo demanda.
    """
    # Obtener datos actuales de BD
    from skills.dispatch.bottle_tracker import get_bottle_tracker
    from skills.dispatch.gps_tracker import get_gps_tracker

    gps_tracker = get_gps_tracker()
    bottle_tracker = get_bottle_tracker()

    # 1. Mapa_Calor - últimos 24h
    heatmap_data = gps_tracker.get_heatmap_data(hours_back=24)
    await _save_mapa_calor_async(heatmap_data)

    # 2. Botellas_Control - inventario completo
    bottles = await bottle_tracker.get_bottles_by_status("available")
    bottles += await bottle_tracker.get_bottles_by_status("in_transit_full")
    bottles += await bottle_tracker.get_bottles_by_status("with_client")
    bottles += await bottle_tracker.get_bottles_by_status("in_transit_empty")
    bottles += await bottle_tracker.get_bottles_by_status("maintenance")
    bottles += await bottle_tracker.get_bottles_by_status("retired")

    # Enriquecer con nombres de clientes
    enriched_bottles = []
    for b in bottles:
        enriched = dict(b)
        if b.get("client_id"):
            enriched["client_name"] = f"Client_{b['client_id']}"
        enriched_bottles.append(enriched)

    # Preparar datos para sheets
    bottles_data = []
    for b in enriched_bottles:
        bottles_data.append(
            {
                "bottle_code": b.get("bottle_code", ""),
                "status": b.get("status", ""),
                "client_id": b.get("client_id", ""),
                "client_name": b.get("client_name", ""),
                "delivery_id": b.get("delivery_id", ""),
                "assigned_at": b.get("assigned_at", ""),
                "expected_return_at": b.get("expected_return_at", ""),
                "returned_at": b.get("returned_at", ""),
                "alert_type": b.get("alert_type", ""),
                "alert_severity": b.get("alert_severity", ""),
                "acknowledged": b.get("acknowledged", 0),
            }
        )

    await _save_botellas_control_async(bottles_data)

    logger.info("sync_all_dispatcher completado")


# ============================================================================
# Test
# ============================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("=== Test Sheets Sync Dispatcher ===")
    print(f"Credentials: {GOOGLE_CREDENTIALS_PATH}")
    print(f"Spreadsheet ID: {GOOGLE_SPREADSHEET_ID}")
    print(f"Enabled: {GOOGLE_SHEETS_ENABLED}")
    print(f"Creds exist: {os.path.exists(GOOGLE_CREDENTIALS_PATH)}")
