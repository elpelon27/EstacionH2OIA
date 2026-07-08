"""
 ============================================================================
 Google Sheets Integration — Valentina Bridge
 Estación H2O · Maracaibo, Venezuela
 ============================================================================

Guarda cada pedido confirmado en la hoja "Pedidos" del spreadsheet de
Google Sheets compartido con el service account valentina-h2o.

Credenciales (extraídas del TXT histórico, l.36575):
  - Spreadsheet ID: 1Bbp4Xqw5E7bb7loJ262K9lMPFinNSIW-ws1i7ZAmiYk
  - Service account: valentina-h2o@valentina-h2o.iam.gserviceaccount.com
  - JSON credentials: /mnt/ssd_trabajo/hermes-agent/config/google_credentials.json

Columnas de la hoja "Pedidos" (mapeo decidido con el Líder, l.36597-36651):
  A: Fecha          → timestamp ISO 8601 America/Caracas
  B: Hora           → HH:MM
  C: Cliente        → nombre (se obtiene del perfil de WhatsApp)
  D: Telefono       → +58 XXXXXXXXXX (hasheado si PII_SAFE=true)
  E: Producto       → "Botellones" / "Hielo" / "Combinado"
  F: Cant Botellones
  G: Cant Hielo
  H: Direccion      → texto libre o "Ver GPS"
  I: GPS            → https://maps.google.com/?q=lat,lng (clickable, para chofer)
  J: Monto EUR      → total calculado
  K: Metodo Pago    → "Pago Móvil" / "Efectivo"
  L: Pagado         → "PENDIENTE" (lo cierra financial agent)
  M: Frecuencia     → vacío (lo completa agente fidelización)
  N: Credito        → vacío (lo completa financial si no paga)
  O: Estado         → "registrado" / "enviado" / "entregado" / "cancelado"
  P: Phone Hash     → SHA256+salt (para cruzar con otros agentes preservando PII)
  Q: Conversation ID→ Dify conversation_id (trazabilidad)

Dependencias: gspread, google-auth (ver requirements.txt)
"""

import logging
import os
import threading
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger("valentina_bridge.sheets")

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
GOOGLE_SHEET_NAME = os.getenv("GOOGLE_SHEET_NAME", "Pedidos")
GOOGLE_SHEETS_ENABLED = os.getenv("GOOGLE_SHEETS_ENABLED", "true").lower() == "true"


def _get_client():
    """Inicializa el cliente gspread de forma perezosa (lazy + thread-safe)."""
    global _sheets_client, _spreadsheet
    if _spreadsheet is not None:
        return _spreadsheet

    if not GOOGLE_SHEETS_ENABLED:
        logger.info("Google Sheets deshabilitado (GOOGLE_SHEETS_ENABLED=false)")
        return None

    if not os.path.exists(GOOGLE_CREDENTIALS_PATH):
        logger.warning(
            "Credenciales Google no encontradas en %s — pedidos NO se guardarán en Sheets",
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
        _sheets_client = gspread.authorize(creds)
        _spreadsheet = _sheets_client.open_by_key(GOOGLE_SPREADSHEET_ID)
        logger.info(
            "Google Sheets conectado: spreadsheet=%s hoja=%s",
            GOOGLE_SPREADSHEET_ID[:12] + "...",
            GOOGLE_SHEET_NAME,
        )
        return _spreadsheet
    except ImportError:
        logger.warning(
            "gspread no instalado — pedidos NO se guardarán en Sheets. "
            "Instala con: pip install gspread google-auth"
        )
        return None
    except Exception as e:
        logger.error("Error conectando a Google Sheets: %s", e)
        return None


def _ensure_header(worksheet) -> None:
    """Asegura que la fila 1 tenga los headers correctos. Idempotente."""
    expected_headers = [
        "Fecha",
        "Hora",
        "Cliente",
        "Telefono",
        "Producto",
        "Cant Botellones",
        "Cant Hielo",
        "Direccion",
        "GPS",
        "Monto EUR",
        "Metodo Pago",
        "Pagado",
        "Frecuencia",
        "Credito",
        "Estado",
        "Phone Hash",
        "Conversation ID",
    ]
    try:
        current = worksheet.row_values(1)
        if current != expected_headers:
            # Actualizar solo si difiere
            from gspread.utils import rowcol_to_a1

            range_str = f"A1:{rowcol_to_a1(1, len(expected_headers))}"
            worksheet.update(range_str, [expected_headers])
            logger.info("Headers de Google Sheets actualizados")
    except Exception as e:
        logger.warning("No se pudieron verificar headers: %s", e)


def _get_or_create_worksheet(spreadsheet):
    """Obtiene la hoja 'Pedidos' o la crea si no existe."""
    try:
        return spreadsheet.worksheet(GOOGLE_SHEET_NAME)
    except Exception:
        # La hoja no existe, crearla
        worksheet = spreadsheet.add_worksheet(title=GOOGLE_SHEET_NAME, rows=1000, cols=20)
        _ensure_header(worksheet)
        logger.info("Hoja '%s' creada en Google Sheets", GOOGLE_SHEET_NAME)
        return worksheet


def save_order_to_sheets(order_data: dict[str, Any]) -> bool:
    """
    Guarda un pedido en Google Sheets. No bloquea el webhook (best-effort).

    Args:
        order_data: dict con claves:
            - phone (str): teléfono del cliente en formato internacional
            - phone_hash (str): hash SHA256+salt
            - contact_name (str): nombre del perfil de WhatsApp
            - product_type (str): "Botellones" / "Hielo" / "Combinado"
            - qty_botellones (int)
            - qty_hielo (int)
            - address (str): dirección textual
            - latitude (float|None)
            - longitude (float|None)
            - total_eur (float)
            - payment_method (str): "Pago Móvil" / "Efectivo"
            - conversation_id (str): ID de conversación Dify
            - raw_answer (str): respuesta completa de Valentina (para parseo fallback)

    Returns:
        True si se guardó, False si falló.
    """
    spreadsheet = _get_client()
    if spreadsheet is None:
        return False

    worksheet = _get_or_create_worksheet(spreadsheet)
    if worksheet is None:
        return False

    # Asegurar headers (idempotente, solo la primera vez)
    _ensure_header(worksheet)

    # Construir fila
    now = datetime.now(CARACAS_TZ)
    fecha = now.strftime("%Y-%m-%d")
    hora = now.strftime("%H:%M")

    # GPS: formato link clicable (más práctico para reenviar al chofer por Telegram)
    lat = order_data.get("latitude")
    lng = order_data.get("longitude")
    if lat is not None and lng is not None:
        gps_url = f"https://maps.google.com/?q={lat},{lng}"
    else:
        gps_url = ""

    # Dirección: si hay GPS sin texto, indicar "Ver GPS"
    address = order_data.get("address", "") or ""
    if not address and gps_url:
        address = "Ver GPS"

    # Phone: por defecto hasheado, pero se puede mostrar completo si PII_SAFE=false
    pii_safe = os.getenv("PII_SAFE", "true").lower() == "true"
    telefono_display = order_data.get("phone_hash", "") if pii_safe else order_data.get("phone", "")

    row = [
        fecha,  # A: Fecha
        hora,  # B: Hora
        order_data.get("contact_name", ""),  # C: Cliente
        telefono_display,  # D: Telefono
        order_data.get("product_type", ""),  # E: Producto
        order_data.get("qty_botellones", 0),  # F: Cant Botellones
        order_data.get("qty_hielo", 0),  # G: Cant Hielo
        address,  # H: Direccion
        gps_url,  # I: GPS
        order_data.get("total_eur", 0.0),  # J: Monto EUR
        order_data.get("payment_method", ""),  # K: Metodo Pago
        "PENDIENTE",  # L: Pagado (lo cierra financial)
        "",  # M: Frecuencia (agente fidelización)
        "",  # N: Credito (financial si no paga)
        "registrado",  # O: Estado
        order_data.get("phone_hash", ""),  # P: Phone Hash
        order_data.get("conversation_id", ""),  # Q: Conversation ID
    ]

    try:
        worksheet.append_row(row, value_input_option="USER_ENTERED")
        logger.info(
            "Pedido guardado en Google Sheets: %s %s €%.2f",
            order_data.get("product_type"),
            order_data.get("contact_name", "anónimo"),
            order_data.get("total_eur", 0),
        )
        return True
    except Exception as e:
        logger.error("Error guardando en Google Sheets: %s", e)
        return False


def save_order_async(order_data: dict[str, Any]) -> None:
    """
    Wrapper no bloqueante: lanza save_order_to_sheets en un thread daemon.
    El webhook POST responde 200 inmediatamente sin esperar a Google Sheets.
    """
    thread = threading.Thread(
        target=save_order_to_sheets,
        args=(order_data,),
        daemon=True,
    )
    thread.start()


# ============================================================================
# Test de conexión (ejecutar manualmente: python google_sheets.py)
# ============================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("=== Test conexión Google Sheets ===")
    print(f"Credentials path: {GOOGLE_CREDENTIALS_PATH}")
    print(f"Spreadsheet ID: {GOOGLE_SPREADSHEET_ID}")
    print(f"Sheet name: {GOOGLE_SHEET_NAME}")
    print(f"Enabled: {GOOGLE_SHEETS_ENABLED}")
    print(f"Credentials exists: {os.path.exists(GOOGLE_CREDENTIALS_PATH)}")
    print()

    spreadsheet = _get_client()
    if spreadsheet:
        print(f"✅ Conectado. Título: {spreadsheet.title}")
        worksheets = [ws.title for ws in spreadsheet.worksheets()]
        print(f"   Hojas disponibles: {worksheets}")
        ws = _get_or_create_worksheet(spreadsheet)
        print(f"   Hoja activa: {ws.title}")
        print(f"   Filas con datos: {len(ws.get_all_values())}")

        # Test escribir fila de prueba
        test_data = {
            "phone": "+584122560721",
            "phone_hash": "test_hash_123",
            "contact_name": "TEST (eliminar)",
            "product_type": "Test",
            "qty_botellones": 0,
            "qty_hielo": 0,
            "address": "Test de conexión",
            "latitude": None,
            "longitude": None,
            "total_eur": 0.0,
            "payment_method": "Test",
            "conversation_id": "test",
            "raw_answer": "test",
        }
        if save_order_to_sheets(test_data):
            print("✅ Fila de prueba escrita (eliminar manualmente)")
        else:
            print("❌ No se pudo escribir fila de prueba")
    else:
        print("❌ No se pudo conectar a Google Sheets")
