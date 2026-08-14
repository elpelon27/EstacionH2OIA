"""
============================================================================
Dispatcher Bot — Sistema de Despacho Inteligente
Estación H2O · Maracaibo, Venezuela
============================================================================

Bot de Telegram para operadores (YORDANIS + EVERT).

Flujo:
1. /start → Registro (selecciona quién es)
2. Check-in 8am → Confirma llegada
3. Recibe pedidos con GPS clicable + botones
4. [✅ Entregado] [❌ No responde] → Actualiza BD
5. GPS guardado en cada check-in (datos = ORO para mapa de calor)

Filosofía: #FastAndFurious — el operador NO piensa, el sistema le dice dónde ir.
"""

import logging
import os
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

# El raíz del proyecto DEBE ir en sys.path ANTES de importar skills.*
# (ver: ModuleNotFoundError: No module named 'skills' al correr como python skills/dispatcher.py)
sys.path.insert(0, "/mnt/ssd_trabajo/hermes-agent")

from skills.dispatch.route_engine import check_operation_perimeter

# Cargar .env
env_path = Path("/mnt/ssd_trabajo/hermes-agent/config/.env")
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip())

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("dispatcher_bot")

CARACAS_TZ = timezone(timedelta(hours=-4))

DISPATCHER_TOKEN = os.getenv("DISPATCHER_BOT_TOKEN", "")
CONV_DB = os.getenv("SQLITE_PATH", "/mnt/ssd_trabajo/hermes-agent/data/conversations.db")
DISPATCH_DB = "/mnt/ssd_trabajo/hermes-agent/data/dispatch.db"

if not DISPATCHER_TOKEN:
    logger.error("DISPATCHER_BOT_TOKEN no configurado")
    sys.exit(1)


def now_iso() -> str:
    return datetime.now(CARACAS_TZ).isoformat()


def now_epoch() -> float:
    return time.time()


# ============================================================================
# Base de datos helpers
# ============================================================================


def get_dispatch_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DISPATCH_DB)
    # r2: foreign_keys ON per-conexion (PRAGMA no persiste)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


def get_conv_db() -> sqlite3.Connection:
    conn = sqlite3.connect(CONV_DB)
    # r2: foreign_keys ON per-conexion (PRAGMA no persiste)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


def register_chofer(chat_id: int, empleado_id: int, nombre: str) -> None:
    """Registra o actualiza chofer en vehicles table."""
    conn = get_dispatch_db()
    conn.execute(
        """
        UPDATE vehicles SET telegram_chat_id = ? WHERE id = ?
        """,
        (chat_id, empleado_id),
    )
    conn.commit()
    conn.close()
    logger.info("Chofer registrado: %s → chat_id=%d (vehicle_id=%d)", nombre, chat_id, empleado_id)


def get_chofer_by_chat_id(chat_id: int) -> dict[str, Any] | None:
    """Obtiene datos del chofer por chat_id."""
    conn = get_dispatch_db()
    row = conn.execute(
        "SELECT * FROM vehicles WHERE telegram_chat_id = ? AND active = 1", (chat_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_choferes() -> list[dict[str, Any]]:
    """Obtiene todos los choferes activos con chat_id."""
    conn = get_dispatch_db()
    rows = conn.execute(
        "SELECT * FROM vehicles WHERE active = 1 AND telegram_chat_id IS NOT NULL"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_pending_deliveries_for_chofer(vehicle_id: int) -> list[dict[str, Any]]:
    """Obtiene entregas pendientes para un vehículo."""
    conn = get_dispatch_db()
    rows = conn.execute(
        """
        SELECT d.*, c.name as client_name, c.phone, c.address_text,
               c.lat, c.lng, c.priority
        FROM deliveries d
        JOIN clients c ON d.client_id = c.id
        WHERE d.vehicle_id = ? AND d.status = 'pending'
        ORDER BY d.order_sequence ASC
        """,
        (vehicle_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_delivery_status(delivery_id: int, status: str, notes: str = "") -> None:
    """Actualiza estado de una entrega."""
    conn = get_dispatch_db()
    now = now_epoch()
    if status == "delivered":
        conn.execute(
            """
            UPDATE deliveries
            SET status = ?, actual_departure = ?,
                operator_notes = ?, updated_at = ?
            WHERE id = ?
            """,
            (status, now, notes, now, delivery_id),
        )
    elif status == "arrived":
        conn.execute(
            """
            UPDATE deliveries
            SET status = ?, actual_arrival = ?, updated_at = ?
            WHERE id = ?
            """,
            (status, now, now, delivery_id),
        )
    else:
        conn.execute(
            """
            UPDATE deliveries
            SET status = ?, operator_notes = ?, updated_at = ?
            WHERE id = ?
            """,
            (status, notes, now, delivery_id),
        )
    conn.commit()
    conn.close()
    logger.info("Entrega #%d → %s", delivery_id, status)


def save_gps_track(
    vehicle_id: int,
    lat: float,
    lng: float,
    accuracy: float | None = None,
    speed: float | None = None,
    source: str = "telegram",
    delivery_id: int | None = None,
    track_type: str = "checkin",
) -> None:
    """Guarda punto GPS para mapa de calor futuro. DATOS = ORO."""
    conn = get_dispatch_db()
    conn.execute(
        """
        INSERT INTO gps_tracks
        (vehicle_id, lat, lng, accuracy, speed_kmh, source, delivery_id, track_type, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (vehicle_id, lat, lng, accuracy, speed, source, delivery_id, track_type, now_epoch()),
    )
    conn.commit()
    conn.close()
    logger.info(
        "📍 GPS guardado: vehicle=%d lat=%f lng=%f type=%s", vehicle_id, lat, lng, track_type
    )


def check_geofence(vehicle_id: int, lat: float, lng: float) -> bool:
    """Verifica geofencing y registra eventos."""
    in_perimeter = check_operation_perimeter(lat, lng)
    if not in_perimeter:
        conn = get_dispatch_db()
        conn.execute(
            """
            INSERT INTO geofence_events (vehicle_id, event_type, lat, lng, created_at)
            VALUES (?, 'exit', ?, ?, ?)
            """,
            (vehicle_id, lat, lng, now_epoch()),
        )
        conn.commit()
        conn.close()
        logger.warning("⚠️ Vehículo %d fuera del perímetro (13km)", vehicle_id)
    return in_perimeter


def format_gps_url(lat: float, lng: float) -> str:
    """Genera URL clicable de Google Maps."""
    return f"https://maps.google.com/?q={lat},{lng}"


# ============================================================================
# Comandos Telegram
# ============================================================================


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Registro de chofer."""
    chat = update.effective_chat
    message = update.message
    assert chat is not None and message is not None
    chat_id = chat.id

    # Verificar si ya está registrado
    chofer = get_chofer_by_chat_id(chat_id)
    if chofer:
        await message.reply_text(
            f"✅ Ya estás registrado como {chofer['operator_name']}.\n\n"
            f"Comandos:\n"
            f"/ruta — Ver tu ruta de hoy\n"
            f"/siguiente — Ver próxima parada\n"
            f"/status — Tu estado actual\n"
            f"/help — Ayuda"
        )
        return

    # Mostrar vehículos disponibles para selección
    conn = get_dispatch_db()
    vehicles = conn.execute(
        "SELECT id, name, operator_name FROM vehicles WHERE active = 1 AND telegram_chat_id IS NULL"
    ).fetchall()
    conn.close()

    if not vehicles:
        await message.reply_text("❌ No hay vehículos disponibles para registrar.")
        return

    keyboard: list[list[InlineKeyboardButton]] = []
    for v in vehicles:
        keyboard.append(
            [
                InlineKeyboardButton(
                    f"Soy {v['operator_name']} ({v['name']})", callback_data=f"reg_{v['id']}"
                )
            ]
        )
    reply_markup = InlineKeyboardMarkup(keyboard)

    await message.reply_text(
        "👋 ¡Bienvenido al sistema de despacho de Estación H2O!\n\n¿Quién eres?",
        reply_markup=reply_markup,
    )


async def callback_registro(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Maneja registro de chofer."""
    query = update.callback_query
    assert query is not None
    await query.answer()

    data = query.data
    assert data is not None
    if not data.startswith("reg_"):
        return

    vehicle_id = int(data.replace("reg_", ""))
    message = query.message
    assert message is not None
    chat_id = message.chat_id  # type: ignore[attr-defined]

    conn = get_dispatch_db()
    vehicle = conn.execute("SELECT * FROM vehicles WHERE id = ?", (vehicle_id,)).fetchone()
    conn.close()

    if not vehicle:
        await query.edit_message_text("❌ Vehículo no encontrado.")
        return

    register_chofer(chat_id, vehicle_id, vehicle["operator_name"])

    await query.edit_message_text(
        f"✅ Registrado como {vehicle['operator_name']}\n"
        f"🚚 {vehicle['name']}\n\n"
        f"Comandos:\n"
        f"/ruta — Ver tu ruta de hoy\n"
        f"/siguiente — Ver próxima parada\n"
        f"/status — Tu estado\n"
        f"/help — Ayuda\n\n"
        f"💧 Estación H2O — #FastAndFurious"
    )


async def cmd_ruta(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Muestra la ruta completa del día."""
    chat = update.effective_chat
    message = update.message
    assert chat is not None and message is not None
    chat_id = chat.id
    chofer = get_chofer_by_chat_id(chat_id)

    if not chofer:
        await message.reply_text("❌ No estás registrado. Envía /start")
        return

    deliveries = get_pending_deliveries_for_chofer(chofer["id"])

    if not deliveries:
        await message.reply_text("📭 No tienes entregas pendientes hoy.")
        return

    msg = f"📋 RUTA DE HOY — {chofer['operator_name']}\n"
    msg += "━━━━━━━━━━━━━━━━\n"
    msg += f"Total paradas: {len(deliveries)}\n\n"

    for i, d in enumerate(deliveries, 1):
        status_emoji = "✅" if d["status"] == "delivered" else "⏳"
        msg += f"{status_emoji} {i}. {d['client_name']}\n"
        msg += f"   📦 {d['bottles_full']} botellones\n"
        if d["lat"] and d["lng"]:
            msg += f"   📍 {format_gps_url(d['lat'], d['lng'])}\n"
        msg += "\n"

    msg += "━━━━━━━━━━━━━━━━\n"
    msg += "💧 Estación H2O"

    await message.reply_text(msg)


async def cmd_siguiente(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Muestra la próxima parada con botones de acción."""
    chat = update.effective_chat
    message = update.message
    assert chat is not None and message is not None
    chat_id = chat.id
    chofer = get_chofer_by_chat_id(chat_id)

    if not chofer:
        await message.reply_text("❌ No estás registrado. Envía /start")
        return

    deliveries = get_pending_deliveries_for_chofer(chofer["id"])
    pending = [d for d in deliveries if d["status"] == "pending"]

    if not pending:
        await message.reply_text("✅ No tienes entregas pendientes. ¡Día completado!")
        return

    d = pending[0]  # Primera pendiente

    msg = "📍 PRÓXIMA PARADA\n"
    msg += "━━━━━━━━━━━━━━━━\n"
    msg += f"👤 {d['client_name']}\n"
    msg += f"📱 {d['phone']}\n"
    msg += f"📦 {d['bottles_full']} botellones\n"
    if d["lat"] and d["lng"]:
        msg += f"📍 {format_gps_url(d['lat'], d['lng'])}\n"
    msg += "━━━━━━━━━━━━━━━━"

    keyboard = [
        [
            InlineKeyboardButton("📍 Llegué", callback_data=f"arr_{d['id']}"),
            InlineKeyboardButton("✅ Entregado", callback_data=f"del_{d['id']}"),
        ],
        [
            InlineKeyboardButton("❌ No responde", callback_data=f"no_{d['id']}"),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await message.reply_text(msg, reply_markup=reply_markup)


async def callback_accion(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Maneja botones de acción del chofer."""
    query = update.callback_query
    assert query is not None
    await query.answer()

    data = query.data
    assert data is not None
    message = query.message
    assert message is not None
    chat_id = message.chat_id  # type: ignore[attr-defined]
    chofer = get_chofer_by_chat_id(chat_id)

    if not chofer:
        await query.edit_message_text("❌ No estás registrado.")
        return

    if data.startswith("arr_"):
        delivery_id = int(data.replace("arr_", ""))
        update_delivery_status(delivery_id, "arrived")

        # Solicitar ubicación GPS del chofer
        await query.edit_message_text(
            "✅ Llegada registrada.\n\n"
            "📍 Por favor, envía tu ubicación actual por GPS.\n"
            "(Toca el clip 📎 → Ubicación → Enviar mi ubicación actual)"
        )

    elif data.startswith("del_"):
        delivery_id = int(data.replace("del_", ""))
        update_delivery_status(delivery_id, "delivered")

        # Verificar si hay más entregas
        deliveries = get_pending_deliveries_for_chofer(chofer["id"])
        pending = [d for d in deliveries if d["status"] == "pending"]

        if pending:
            next_d = pending[0]
            msg = (
                f"✅ Entrega completada.\n\n"
                f"📍 PRÓXIMA PARADA:\n"
                f"👤 {next_d['client_name']}\n"
                f"📱 {next_d['phone']}\n"
                f"📦 {next_d['bottles_full']} botellones\n"
            )
            if next_d["lat"] and next_d["lng"]:
                msg += f"📍 {format_gps_url(next_d['lat'], next_d['lng'])}\n"

            keyboard = [
                [
                    InlineKeyboardButton("📍 Llegué", callback_data=f"arr_{next_d['id']}"),
                    InlineKeyboardButton("✅ Entregado", callback_data=f"del_{next_d['id']}"),
                ],
                [
                    InlineKeyboardButton("❌ No responde", callback_data=f"no_{next_d['id']}"),
                ],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(msg, reply_markup=reply_markup)
        else:
            await query.edit_message_text(
                "✅ Entrega completada.\n\n"
                "🏁 No tienes más entregas pendientes. ¡Buen trabajo!\n"
                "💧 Estación H2O"
            )

    elif data.startswith("no_"):
        delivery_id = int(data.replace("no_", ""))
        update_delivery_status(delivery_id, "no_answer", "Cliente no responde")

        await query.edit_message_text(
            "❌ Marcado como 'No responde'.\n\n"
            "El administrador será notificado.\n"
            "Usa /siguiente para ver la próxima parada."
        )

    # r6/FASE 1.4: Botones "new_arr/new_del/new_no" usan vehicle_id (NO delivery_id).
    # Llegan desde send_pedido_to_chofer() en bridge._send_to_dispatch_queue flow.
    # Estrategia: buscar el último delivery pendiente del vehículo y aplicarle
    # la acción. Si no hay delivery en tabla, marcar como evento pendiente.
    elif data.startswith(("new_arr_", "new_del_", "new_no_")):
        # data format: "new_arr_<vehicle_id>", "new_del_<vehicle_id>", etc.
        # separar: parts = ["new", "arr", "<vehicle_id>"]
        parts = data.split("_")
        action_kind = parts[1]
        try:
            vehicle_id = int(parts[2])
        except (IndexError, ValueError):
            logger.warning("callback_accion: new_* malformed data=%s", data)
            await query.edit_message_text("❌ Datos del botón inválidos.")
            return

        # Buscar último delivery pendiente de este vehículo
        conn = get_dispatch_db()
        delivery = conn.execute(
            """
            SELECT id FROM deliveries
            WHERE vehicle_id = ? AND status = 'pending'
            ORDER BY order_sequence ASC LIMIT 1
            """,
            (vehicle_id,),
        ).fetchone()
        conn.close()

        if not delivery:
            # No hay delivery planificado en tabla — pedido recibido vía dispatch_queue
            # pero dispatcher no ha generado route todavía. Marcar como notificación
            # informativa para que chofer sepa que su ack no generó acción.
            await query.edit_message_text(
                "ℹ️ Pedido notificado. La ruta oficial se planifica a las 7:45 AM.\n"
                "Si ya lo entregaste/completaste, el sistema lo procesará en la "
                "siguiente ruta.\n"
                "💧 Estación H2O"
            )
            logger.info("new_%s ack sin delivery asociado (vehicle_id=%d)", action_kind, vehicle_id)
            return

        delivery_id = delivery["id"]
        if action_kind == "arr":
            update_delivery_status(delivery_id, "arrived")
            await query.edit_message_text(
                "✅ Llegada registrada.\n\n"
                "📍 Por favor, envía tu ubicación actual por GPS.\n"
                "(Toca el clip 📎 → Ubicación → Enviar mi ubicación actual)"
            )
        elif action_kind == "del":
            update_delivery_status(delivery_id, "delivered")

            # SWAP: Notificar WorkloadRouter para asignar
            # botellón loaner (available -> in_transit_full)
            try:
                from core.workload_router import get_router

                router = get_router()
                result = await router.execute(
                    trigger="dispatch_request",
                    action="assign_loaner_bottle",
                    params={"vehicle_id": vehicle_id, "delivery_id": delivery_id},
                )
                if result.get("success"):
                    logger.info(
                        "SWAP: loaner bottle asignado a vehicle_id=%d, delivery_id=%d",
                        vehicle_id,
                        delivery_id,
                    )
                else:
                    logger.warning(
                        "SWAP: failed to assign loaner: %s", result.get("error", "unknown")
                    )
            except Exception as e:
                logger.warning("SWAP: error notificando WorkloadRouter: %s", e)

            await query.edit_message_text(
                "✅ Llegada registrada.\n\n"
                "📍 Por favor, envía tu ubicación actual por GPS.\n"
                "(Toca el clip 📎 → Ubicación → Enviar mi ubicación actual)"
            )
        elif action_kind == "del":
            update_delivery_status(delivery_id, "delivered")

            # SWAP: Notificar al WorkloadRouter para tracking
            # de botellón (available -> in_transit_full -> with_client)
            try:
                from core.workload_router import get_router

                router = get_router()
                result = await router.execute(
                    trigger="dispatch_request",
                    action="track_loaner_bottle",
                    params={"vehicle_id": vehicle_id, "delivery_id": delivery_id},
                )
                if result.get("success"):
                    logger.info(
                        "SWAP: loaner bottle tracking OK vehicle_id=%d, delivery_id=%d",
                        vehicle_id,
                        delivery_id,
                    )
                else:
                    logger.warning("SWAP: tracking failed: %s", result.get("error", "unknown"))
            except Exception as e:
                logger.warning("SWAP: error notificando WorkloadRouter: %s", e)

            await query.edit_message_text(
                "✅ Entrega completada. ✅ Botellón loaner tracking activado.\n"
                "━━━━━━━━━━━━━━━━\n"
                "💧 Estación H2O"
            )
        elif action_kind == "no":
            update_delivery_status(delivery_id, "no_answer", "Cliente no responde")

            await query.edit_message_text(
                "❌ Marcado como 'No responde'.\n\n"
                "El administrador será notificado.\n"
                "Usa /siguiente para ver la próxima parada."
            )


async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Estado actual del chofer."""
    chat = update.effective_chat
    message = update.message
    assert chat is not None and message is not None
    chat_id = chat.id
    chofer = get_chofer_by_chat_id(chat_id)

    if not chofer:
        await message.reply_text("❌ No estás registrado. Envía /start")
        return

    conn = get_dispatch_db()
    deliveries = conn.execute(
        """
        SELECT status, COUNT(*) as count FROM deliveries
        WHERE vehicle_id = ? GROUP BY status
        """,
        (chofer["id"],),
    ).fetchall()
    conn.close()

    msg = f"📊 ESTADO — {chofer['operator_name']}\n"
    msg += "━━━━━━━━━━━━━━━━\n"
    for d in deliveries:
        emoji = "✅" if d["status"] == "delivered" else "⏳"
        msg += f"{emoji} {d['status']}: {d['count']}\n"
    msg += "━━━━━━━━━━━━━━━━\n"
    msg += "💧 Estación H2O"

    await message.reply_text(msg)


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Ayuda."""
    assert update.message is not None
    await update.message.reply_text(
        "🤖 COMANDOS DISPATCHER\n"
        "━━━━━━━━━━━━━━━━\n"
        "/start — Registro inicial\n"
        "/ruta — Ver ruta completa del día\n"
        "/siguiente — Próxima parada con botones\n"
        "/status — Tu estado actual\n"
        "/help — Esta ayuda\n"
        "━━━━━━━━━━━━━━━━\n"
        "BOTONES:\n"
        "📍 Llegué — Confirmar llegada a cliente\n"
        "✅ Entregado — Confirmar entrega + SWAP\n"
        "❌ No responde — Cliente no contesta\n"
        "━━━━━━━━━━━━━━━━\n"
        "💧 Estación H2O"
    )


async def cmd_health(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Health check endpoint para kill-switch bot."""
    assert update.message is not None
    import sqlite3

    # Check dispatch DB connectivity
    db_ok = False
    pending_deliveries = 0
    try:
        conn = sqlite3.connect("/mnt/ssd_trabajo/hermes-agent/data/dispatch.db")
        conn.execute("PRAGMA foreign_keys = ON")
        row = conn.execute('SELECT COUNT(*) FROM deliveries WHERE status = "pending"').fetchone()
        pending_deliveries = row[0] if row else 0
        conn.close()
        db_ok = True
    except Exception as e:
        logger.error("Health check DB error: %s", e)

    # Check bridge HTTP
    bridge_ok = False
    try:
        import httpx

        async with httpx.AsyncClient() as client:
            resp = await client.get("http://localhost:8000/health", timeout=3.0)
            bridge_ok = resp.status_code == 200
    except Exception:
        pass

    status = "🟢 HEALTHY" if (db_ok and bridge_ok) else "🔴 DEGRADED"
    msg = (
        f"🏥 HEALTH CHECK — {status}\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"DB: {'🟢' if db_ok else '🔴'}\n"
        f"Bridge: {'🟢' if bridge_ok else '🔴'}\n"
        f"Pending deliveries: {pending_deliveries}\n"
        f"━━━━━━━━━━━━━━━━"
    )
    await update.message.reply_text(msg)


def main() -> None:
    """Entry point para systemd."""
    if not DISPATCHER_TOKEN:
        logger.error("DISPATCHER_BOT_TOKEN no configurado")
        sys.exit(1)

    application = Application.builder().token(DISPATCHER_TOKEN).build()

    # Comandos
    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("ruta", cmd_ruta))
    application.add_handler(CommandHandler("siguiente", cmd_siguiente))
    application.add_handler(CommandHandler("status", cmd_status))
    application.add_handler(CommandHandler("help", cmd_help))
    application.add_handler(CommandHandler("health", cmd_health))

    # Callbacks
    application.add_handler(CallbackQueryHandler(callback_registro, pattern="^reg_"))
    application.add_handler(CallbackQueryHandler(callback_accion, pattern="^(arr_|del_|no_|new_)"))
    application.add_handler(CallbackQueryHandler(callback_registro, pattern="^reg_"))

    logger.info("🚀 Dispatcher Bot iniciado — %s", datetime.now().isoformat())
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
