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

import os
import sys
import time
import math
import sqlite3
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List

# Cargar .env
from pathlib import Path
env_path = Path("/mnt/ssd_trabajo/hermes-agent/config/.env")
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip())

sys.path.insert(0, "/mnt/ssd_trabajo/hermes-agent")

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

from skills.dispatch.route_engine import (
    haversine, check_operation_perimeter, DEPOT_LAT, DEPOT_LNG
)

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


def now_iso():
    return datetime.now(CARACAS_TZ).isoformat()


def now_epoch():
    return time.time()


# ============================================================================
# Base de datos helpers
# ============================================================================

def get_dispatch_db():
    conn = sqlite3.connect(DISPATCH_DB)
    # r2: foreign_keys ON per-conexion (PRAGMA no persiste)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


def get_conv_db():
    conn = sqlite3.connect(CONV_DB)
    # r2: foreign_keys ON per-conexion (PRAGMA no persiste)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


def register_chofer(chat_id: int, empleado_id: int, nombre: str):
    """Registra o actualiza chofer en vehicles table."""
    conn = get_dispatch_db()
    conn.execute("""
        UPDATE vehicles SET telegram_chat_id = ? WHERE id = ?
    """, (chat_id, empleado_id))
    conn.commit()
    conn.close()
    logger.info("Chofer registrado: %s → chat_id=%d (vehicle_id=%d)", nombre, chat_id, empleado_id)


def get_chofer_by_chat_id(chat_id: int) -> Optional[dict]:
    """Obtiene datos del chofer por chat_id."""
    conn = get_dispatch_db()
    row = conn.execute(
        "SELECT * FROM vehicles WHERE telegram_chat_id = ? AND active = 1",
        (chat_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_choferes() -> List[dict]:
    """Obtiene todos los choferes activos con chat_id."""
    conn = get_dispatch_db()
    rows = conn.execute(
        "SELECT * FROM vehicles WHERE active = 1 AND telegram_chat_id IS NOT NULL"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_pending_deliveries_for_chofer(vehicle_id: int) -> List[dict]:
    """Obtiene entregas pendientes para un vehículo."""
    conn = get_dispatch_db()
    rows = conn.execute("""
        SELECT d.*, c.name as client_name, c.phone, c.address_text,
               c.lat, c.lng, c.priority
        FROM deliveries d
        JOIN clients c ON d.client_id = c.id
        WHERE d.vehicle_id = ? AND d.status = 'pending'
        ORDER BY d.order_sequence ASC
    """, (vehicle_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_delivery_status(delivery_id: int, status: str, notes: str = ""):
    """Actualiza estado de una entrega."""
    conn = get_dispatch_db()
    now = now_epoch()
    if status == "delivered":
        conn.execute("""
            UPDATE deliveries SET status = ?, actual_departure = ?, operator_notes = ?, updated_at = ?
            WHERE id = ?
        """, (status, now, notes, now, delivery_id))
    elif status == "arrived":
        conn.execute("""
            UPDATE deliveries SET status = ?, actual_arrival = ?, updated_at = ?
            WHERE id = ?
        """, (status, now, now, delivery_id))
    else:
        conn.execute("""
            UPDATE deliveries SET status = ?, operator_notes = ?, updated_at = ?
            WHERE id = ?
        """, (status, notes, now, delivery_id))
    conn.commit()
    conn.close()
    logger.info("Entrega #%d → %s", delivery_id, status)


def save_gps_track(vehicle_id: int, lat: float, lng: float, 
                   accuracy: float = None, speed: float = None,
                   source: str = "telegram", delivery_id: int = None,
                   track_type: str = "checkin"):
    """Guarda punto GPS para mapa de calor futuro. DATOS = ORO."""
    conn = get_dispatch_db()
    conn.execute("""
        INSERT INTO gps_tracks (vehicle_id, lat, lng, accuracy, speed_kmh, source, delivery_id, track_type, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (vehicle_id, lat, lng, accuracy, speed, source, delivery_id, track_type, now_epoch()))
    conn.commit()
    conn.close()
    logger.info("📍 GPS guardado: vehicle=%d lat=%f lng=%f type=%s", vehicle_id, lat, lng, track_type)


def check_geofence(vehicle_id: int, lat: float, lng: float):
    """Verifica geofencing y registra eventos."""
    in_perimeter = check_operation_perimeter(lat, lng)
    if not in_perimeter:
        conn = get_dispatch_db()
        conn.execute("""
            INSERT INTO geofence_events (vehicle_id, event_type, lat, lng, created_at)
            VALUES (?, 'exit', ?, ?, ?)
        """, (vehicle_id, lat, lng, now_epoch()))
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
    chat_id = update.effective_chat.id

    # Verificar si ya está registrado
    chofer = get_chofer_by_chat_id(chat_id)
    if chofer:
        await update.message.reply_text(
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
        await update.message.reply_text("❌ No hay vehículos disponibles para registrar.")
        return

    keyboard = []
    for v in vehicles:
        keyboard.append([
            InlineKeyboardButton(
                f"Soy {v['operator_name']} ({v['name']})",
                callback_data=f"reg_{v['id']}"
            )
        ])
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "👋 ¡Bienvenido al sistema de despacho de Estación H2O!\n\n"
        "¿Quién eres?",
        reply_markup=reply_markup
    )


async def callback_registro(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Maneja registro de chofer."""
    query = update.callback_query
    await query.answer()

    data = query.data
    if not data.startswith("reg_"):
        return

    vehicle_id = int(data.replace("reg_", ""))
    chat_id = query.message.chat_id

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
    chat_id = update.effective_chat.id
    chofer = get_chofer_by_chat_id(chat_id)

    if not chofer:
        await update.message.reply_text("❌ No estás registrado. Envía /start")
        return

    deliveries = get_pending_deliveries_for_chofer(chofer["id"])

    if not deliveries:
        await update.message.reply_text("📭 No tienes entregas pendientes hoy.")
        return

    msg = f"📋 RUTA DE HOY — {chofer['operator_name']}\n"
    msg += f"━━━━━━━━━━━━━━━━\n"
    msg += f"Total paradas: {len(deliveries)}\n\n"

    for i, d in enumerate(deliveries, 1):
        status_emoji = "✅" if d["status"] == "delivered" else "⏳"
        msg += f"{status_emoji} {i}. {d['client_name']}\n"
        msg += f"   📦 {d['bottles_full']} botellones\n"
        if d["lat"] and d["lng"]:
            msg += f"   📍 {format_gps_url(d['lat'], d['lng'])}\n"
        msg += "\n"

    msg += f"━━━━━━━━━━━━━━━━\n"
    msg += f"💧 Estación H2O"

    await update.message.reply_text(msg)


async def cmd_siguiente(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Muestra la próxima parada con botones de acción."""
    chat_id = update.effective_chat.id
    chofer = get_chofer_by_chat_id(chat_id)

    if not chofer:
        await update.message.reply_text("❌ No estás registrado. Envía /start")
        return

    deliveries = get_pending_deliveries_for_chofer(chofer["id"])
    pending = [d for d in deliveries if d["status"] == "pending"]

    if not pending:
        await update.message.reply_text("✅ No tienes entregas pendientes. ¡Día completado!")
        return

    d = pending[0]  # Primera pendiente

    msg = f"📍 PRÓXIMA PARADA\n"
    msg += f"━━━━━━━━━━━━━━━━\n"
    msg += f"👤 {d['client_name']}\n"
    msg += f"📱 {d['phone']}\n"
    msg += f"📦 {d['bottles_full']} botellones\n"
    if d["lat"] and d["lng"]:
        msg += f"📍 {format_gps_url(d['lat'], d['lng'])}\n"
    msg += f"━━━━━━━━━━━━━━━━"

    keyboard = [[
        InlineKeyboardButton("📍 Llegué", callback_data=f"arr_{d['id']}"),
        InlineKeyboardButton("✅ Entregado", callback_data=f"del_{d['id']}"),
    ], [
        InlineKeyboardButton("❌ No responde", callback_data=f"no_{d['id']}"),
    ]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(msg, reply_markup=reply_markup)


async def callback_accion(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Maneja botones de acción del chofer."""
    query = update.callback_query
    await query.answer()

    data = query.data
    chat_id = query.message.chat_id
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

            keyboard = [[
                InlineKeyboardButton("📍 Llegué", callback_data=f"arr_{next_d['id']}"),
                InlineKeyboardButton("✅ Entregado", callback_data=f"del_{next_d['id']}"),
            ], [
                InlineKeyboardButton("❌ No responde", callback_data=f"no_{next_d['id']}"),
            ]]
            await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(keyboard))
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
                f"ℹ️ Pedido notificado. La ruta oficial se planifica a las 7:45 AM.\n"
                f"Si ya lo entregaste/completaste, el sistema lo procesará en la siguiente ruta.\n"
                f"💧 Estación H2O"
            )
            logger.info(
                "new_%s ack sin delivery asociado (vehicle_id=%d)", action_kind, vehicle_id
            )
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
            await query.edit_message_text(
                "✅ Entrega completada.\n\n🏁 ¡Buen trabajo!\n💧 Estación H2O"
            )
        elif action_kind == "no":
            update_delivery_status(delivery_id, "no_answer", "Cliente no responde")
            await query.edit_message_text(
                "❌ Marcado como 'No responde'.\n\n"
                "El administrador será notificado."
            )


async def handle_location(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Recibe ubicación GPS del chofer vía Telegram."""
    chat_id = update.effective_chat.id
    chofer = get_chofer_by_chat_id(chat_id)

    if not chofer:
        return

    location = update.message.location
    lat = location.latitude
    lng = location.longitude

    # Guardar GPS (DATOS = ORO para mapa de calor)
    save_gps_track(
        vehicle_id=chofer["id"],
        lat=lat, lng=lng,
        accuracy=location.horizontal_accuracy if hasattr(location, 'horizontal_accuracy') else None,
        source="telegram",
        track_type="checkin_arrive"
    )

    # Verificar geofencing
    in_perimeter = check_geofence(chofer["id"], lat, lng)

    if in_perimeter:
        await update.message.reply_text(
            f"📍 Ubicación registrada.\n"
            f"✅ Dentro del perímetro de operación.\n\n"
            f"Entrega en proceso. Toca ✅ Entregado cuando completes."
        )
    else:
        await update.message.reply_text(
            f"📍 Ubicación registrada.\n"
            f"⚠️ Estás fuera del perímetro de operación (13km).\n"
            f"Verifica que la ubicación sea correcta."
        )


async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Estado del chofer."""
    chat_id = update.effective_chat.id
    chofer = get_chofer_by_chat_id(chat_id)

    if not chofer:
        await update.message.reply_text("❌ No estás registrado. Envía /start")
        return

    deliveries = get_pending_deliveries_for_chofer(chofer["id"])
    total = len(deliveries)
    delivered = len([d for d in deliveries if d["status"] == "delivered"])
    pending = total - delivered

    await update.message.reply_text(
        f"📊 ESTADO — {chofer['operator_name']}\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"🚚 {chofer['name']}\n"
        f"📦 Capacidad: {chofer['current_full_load']}/{chofer['max_full_bottles']} llenos\n\n"
        f"📋 Entregas hoy:\n"
        f"  Total: {total}\n"
        f"  Completadas: {delivered}\n"
        f"  Pendientes: {pending}"
    )


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "🚚 Sistema de Despacho — Estación H2O\n"
        "━━━━━━━━━━━━━━━━\n"
        "Comandos:\n"
        "/start — Registrarse\n"
        "/ruta — Ver ruta completa del día\n"
        "/siguiente — Ver próxima parada\n"
        "/status — Ver tu estado\n"
        "/help — Esta ayuda\n\n"
        "💡 Envía tu ubicación GPS en cada parada\n"
        "💧 Estación H2O — #FastAndFurious"
    )


# ============================================================================
# Envío de pedidos a choferes (llamado por bridge)
# ============================================================================

async def send_delivery_to_chofer(
    app: Application,
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
):
    """Envía un pedido al chofer por Telegram."""

    conn = get_dispatch_db()
    vehicle = conn.execute("SELECT * FROM vehicles WHERE id = ?", (vehicle_id,)).fetchone()
    conn.close()

    if not vehicle or not vehicle["telegram_chat_id"]:
        logger.warning("Vehículo %d no tiene chat_id de Telegram", vehicle_id)
        return False

    chat_id = vehicle["telegram_chat_id"]
    gps_url = format_gps_url(lat, lng) if lat and lng else ""

    # Construir mensaje según método de pago
    if metodo_pago and ("efectivo" in metodo_pago.lower()):
        bs_str = f" (Bs. {total_bs:.2f})" if total_bs and total_bs > 0 else ""
        msg = (
            f"🚚 NUEVO PEDIDO\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"👤 {client_name}\n"
            f"📱 {client_phone}\n"
            f"📦 {bottles_full} botellones de agua\n"
            f"💰 Total: €{total_eur:.2f}{bs_str}\n"
        )
        if gps_url:
            msg += f"📍 {gps_url}\n"
        msg += f"⚠️ PAGO EN EFECTIVO — Cobrar al entregar\n"
        msg += f"━━━━━━━━━━━━━━━━"
    else:
        msg = (
            f"🚚 NUEVO PEDIDO\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"👤 {client_name}\n"
            f"📱 {client_phone}\n"
            f"📦 {bottles_full} botellones de agua\n"
        )
        if gps_url:
            msg += f"📍 {gps_url}\n"
        msg += f"━━━━━━━━━━━━━━━━"

    keyboard = [[
        InlineKeyboardButton("📍 Llegué", callback_data=f"new_arr_{vehicle_id}"),
        InlineKeyboardButton("✅ Entregado", callback_data=f"new_del_{vehicle_id}"),
    ], [
        InlineKeyboardButton("❌ No responde", callback_data=f"new_no_{vehicle_id}"),
    ]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        await app.bot.send_message(
            chat_id=chat_id,
            text=msg,
            reply_markup=reply_markup,
        )
        logger.info("📦 Pedido enviado a %s (vehicle=%d)", vehicle["operator_name"], vehicle_id)
        return True
    except Exception as e:
        logger.error("Error enviando a chofer %s: %s", vehicle["operator_name"], e)
        return False


# ============================================================================
# Check-in 8:00 AM
# ============================================================================

async def enviar_checkin_manana(app: Application):
    """Envía check-in a todos los choferes a las 8am."""
    choferes = get_all_choferes()

    for chofer in choferes:
        keyboard = [[
            InlineKeyboardButton("✅ Sí, llegué", callback_data=f"checkin_yes_{chofer['id']}"),
            InlineKeyboardButton("❌ No puedo hoy", callback_data=f"checkin_no_{chofer['id']}"),
        ]]
        try:
            await app.bot.send_message(
                chat_id=chofer["telegram_chat_id"],
                text=f"🌅 Buenos días {chofer['operator_name']}\n¿Confirmas tu llegada hoy?",
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
            logger.info("🌅 Check-in enviado a %s", chofer["operator_name"])
        except Exception as e:
            logger.error("Error check-in %s: %s", chofer["operator_name"], e)


async def callback_checkin(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    data = query.data
    if data.startswith("checkin_yes_"):
        vehicle_id = int(data.replace("checkin_yes_", ""))
        conn = get_dispatch_db()
        v = conn.execute("SELECT operator_name FROM vehicles WHERE id = ?", (vehicle_id,)).fetchone()
        conn.close()
        nombre = v["operator_name"] if v else "?"
        await query.edit_message_text(f"✅ Check-in confirmado: {nombre}\n¡Buen día! 💧")
        logger.info("🌅 Check-in OK: %s", nombre)
    elif data.startswith("checkin_no_"):
        vehicle_id = int(data.replace("checkin_no_", ""))
        conn = get_dispatch_db()
        v = conn.execute("SELECT operator_name FROM vehicles WHERE id = ?", (vehicle_id,)).fetchone()
        conn.close()
        nombre = v["operator_name"] if v else "?"
        await query.edit_message_text(f"❌ {nombre} no puede hoy.\nEl administrador será notificado.")
        logger.warning("⚠️ Check-in negativo: %s", nombre)


# ============================================================================
# Aplicación principal
# ============================================================================

def main():
    logger.info("🚚 Dispatcher Bot iniciando...")

    app = Application.builder().token(DISPATCHER_TOKEN).build()

    # Comandos
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("ruta", cmd_ruta))
    app.add_handler(CommandHandler("siguiente", cmd_siguiente))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("help", cmd_help))

    # Callbacks
    app.add_handler(CallbackQueryHandler(callback_registro, pattern="^reg_"))
    app.add_handler(CallbackQueryHandler(callback_accion, pattern="^(arr_|del_|no_|new_)"))
    app.add_handler(CallbackQueryHandler(callback_checkin, pattern="^checkin_"))

    # Location handler (GPS del chofer)
    app.add_handler(MessageHandler(filters.LOCATION, handle_location))

    logger.info("🚚 Dispatcher Bot listo — esperando choferes...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
