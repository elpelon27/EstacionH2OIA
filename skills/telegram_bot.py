"""
 ============================================================================
 Telegram Bot — Kill Switch + Status para Valentina Bridge
 Estación H2O · Maracaibo, Venezuela
 ============================================================================

Corre como servicio systemd separado (telegram-bot.service).
Escucha comandos del Líder (chat_id verificado) y opera el kill switch.

Comandos:
    /status   — Estado del bridge (uptime, msgs hoy, pedidos)
    /stop     — Activar kill switch (detiene respuestas de Valentina)
    /start    — Desactivar kill switch (Valentina vuelve a responder)
    /logs     — Últimos 20 logs del bridge
    /orders   — Pedidos de hoy
    /metrics  — Resumen métricas del día
    /help     — Mostrar ayuda

Seguridad:
    Solo el chat_id del Líder (TELEGRAM_CHAT_ID) tiene permiso.
    Cualquier otro usuario recibe "No autorizado".

Despliegue:
    systemd/telegram-bot.service
    python skills/telegram_bot.py
 """

import os
import sys
import time
import sqlite3
import logging
import asyncio
from datetime import datetime, timezone, timedelta

import telegram
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

# ============================================================================
# Config
# ============================================================================

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = int(os.getenv("TELEGRAM_CHAT_ID", "1663148211"))
KILL_SWITCH_FILE = os.getenv("KILL_SWITCH_FILE", "/tmp/valentina.kill")
SQLITE_PATH = os.getenv(
    "SQLITE_PATH", "/mnt/ssd_trabajo/hermes-agent/data/conversations.db"
)
BRIDGE_HEALTH_URL = os.getenv("BRIDGE_HEALTH_URL", "http://localhost:8000/health")

# Zona horaria Caracas (UTC-4)
CARACAS_TZ = timezone(timedelta(hours=-4))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("telegram_bot")


# ============================================================================
# Autorización
# ============================================================================

def _is_authorized(update: Update) -> bool:
    """Solo el chat_id del Líder puede usar el bot."""
    return update.effective_chat.id == TELEGRAM_CHAT_ID


async def _unauthorized(update: Update) -> None:
    await update.message.reply_text(
        "🚫 No autorizado. Este bot es privado de Estación H2O."
    )
    logger.warning(
        "Acceso no autorizado de chat_id=%s username=%s",
        update.effective_chat.id,
        update.effective_user.username,
    )


# ============================================================================
# Comandos
# ============================================================================

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Desactiva kill switch — Valentina vuelve a responder."""
    if not _is_authorized(update):
        return await _unauthorized(update)

    if os.path.exists(KILL_SWITCH_FILE):
        os.remove(KILL_SWITCH_FILE)
        await update.message.reply_text(
            "✅ <b>Kill switch DESACTIVADO</b>\n\nValentina está respondiendo de nuevo. 💧",
            parse_mode="HTML",
        )
        logger.info("Kill switch desactivado por Líder")
    else:
        await update.message.reply_text(
            "ℹ️ El kill switch no estaba activo. Valentina ya estaba respondiendo."
        )


async def cmd_stop(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Activa kill switch — Valentina deja de responder."""
    if not _is_authorized(update):
        return await _unauthorized(update)

    with open(KILL_SWITCH_FILE, "w") as f:
        f.write(f"killed by {update.effective_user.username} at {datetime.now(CARACAS_TZ)}")

    await update.message.reply_text(
        "🛑 <b>Kill switch ACTIVADO</b>\n\nValentina NO responderá mensajes nuevos.\n"
        "Para reactivar: /start",
        parse_mode="HTML",
    )
    logger.warning("Kill switch activado por Líder")


async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Estado del bridge."""
    if not _is_authorized(update):
        return await _unauthorized(update)

    import httpx
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(BRIDGE_HEALTH_URL, timeout=5)
            health = resp.json()
    except Exception as e:
        await update.message.reply_text(f"❌ Bridge no responde: {e}")
        return

    kill_active = health.get("checks", {}).get("kill_switch", False)
    uptime = health.get("uptime_seconds", 0)

    status_emoji = "🛑" if kill_active else ("✅" if health["status"] == "ok" else "⚠️")

    msg = (
        f"{status_emoji} <b>Estado Valentina Bridge</b>\n\n"
        f"• Status: <code>{health['status']}</code>\n"
        f"• Uptime: <code>{int(uptime // 60)} min</code>\n"
        f"• Dify API: {'✅' if health['checks']['dify_api_key'] else '❌'}\n"
        f"• Meta API: {'✅' if health['checks']['meta_access_token'] else '❌'}\n"
        f"• SQLite: {'✅' if health['checks']['sqlite'] else '❌'}\n"
        f"• Kill switch: {'🛑 ACTIVO' if kill_active else '✅ inactivo'}\n"
    )
    await update.message.reply_text(msg, parse_mode="HTML")


async def cmd_orders(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Pedidos de hoy."""
    if not _is_authorized(update):
        return await _unauthorized(update)

    if not os.path.exists(SQLITE_PATH):
        await update.message.reply_text("❌ BD no encontrada")
        return

    conn = sqlite3.connect(SQLITE_PATH)
    today_start = datetime.now(CARACAS_TZ).replace(
        hour=0, minute=0, second=0, microsecond=0
    ).timestamp()
    orders = conn.execute(
        "SELECT id, product_description, status, created_at FROM orders WHERE created_at > ? ORDER BY created_at DESC LIMIT 10",
        (today_start,),
    ).fetchall()
    conn.close()

    if not orders:
        await update.message.reply_text("📭 No hay pedidos hoy.")
        return

    msg = f"📋 <b>Pedidos de hoy ({len(orders)})</b>\n\n"
    for oid, desc, status, ts in orders:
        time_str = datetime.fromtimestamp(ts, CARACAS_TZ).strftime("%H:%M")
        # Truncar desc para que entre en Telegram
        desc_short = desc[:80].replace("\n", " ")
        msg += f"#{oid} [{time_str}] <code>{desc_short}</code>\n   → <i>{status}</i>\n"

    await update.message.reply_text(msg, parse_mode="HTML")


async def cmd_logs(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Últimos 20 logs del bridge (via journalctl)."""
    if not _is_authorized(update):
        return await _unauthorized(update)

    import subprocess
    try:
        result = subprocess.run(
            ["journalctl", "-u", "valentina-bridge", "-n", "20", "--no-pager", "-o", "cat"],
            capture_output=True, text=True, timeout=5,
        )
        logs = result.stdout.strip()
    except Exception as e:
        await update.message.reply_text(f"❌ No se pudo leer logs: {e}")
        return

    if not logs:
        await update.message.reply_text("📭 No hay logs.")
        return

    # Truncar si muy largo (Telegram max 4096)
    if len(logs) > 3800:
        logs = logs[-3800:]
    await update.message.reply_text(f"📋 <b>Últimos logs</b>\n\n<code>{logs}</code>", parse_mode="HTML")


async def cmd_metrics(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Resumen métricas del día."""
    if not _is_authorized(update):
        return await _unauthorized(update)

    import httpx
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get("http://localhost:8000/metrics", timeout=5)
            metrics_text = resp.text
    except Exception as e:
        await update.message.reply_text(f"❌ No se pudo obtener métricas: {e}")
        return

    # Parsear métricas clave (formato Prometheus: name{labels} value)
    def _extract(name: str) -> str:
        for line in metrics_text.split("\n"):
            if line.startswith(name) and not line.startswith(name + "_"):
                parts = line.split()
                return parts[-1] if len(parts) > 1 else "0"
        return "0"

    msgs_total = _extract("valentina_messages_total")
    orders_total = _extract("valentina_orders_total")
    escalations = _extract("valentina_escalations_total")
    dedup = _extract("valentina_dedup_hits_total")

    msg = (
        f"📊 <b>Métricas del bridge</b>\n\n"
        f"• Mensajes procesados: <code>{msgs_total}</code>\n"
        f"• Pedidos confirmados: <code>{orders_total}</code>\n"
        f"• Escalamientos humano: <code>{escalations}</code>\n"
        f"• Duplicados ignorados: <code>{dedup}</code>\n"
    )
    await update.message.reply_text(msg, parse_mode="HTML")


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Mostrar ayuda."""
    if not _is_authorized(update):
        return await _unauthorized(update)

    help_text = (
        "💧 <b>Valentina Bridge — Comandos</b>\n\n"
        "<b>/status</b> — Estado del bridge (uptime, checks)\n"
        "<b>/stop</b> — 🛑 Activar kill switch (detiene Valentina)\n"
        "<b>/start</b> — ✅ Desactivar kill switch (reactiva Valentina)\n"
        "<b>/orders</b> — 📋 Pedidos de hoy\n"
        "<b>/logs</b> — 📋 Últimos 20 logs\n"
        "<b>/metrics</b> — 📊 Métricas del día\n"
        "<b>/help</b> — Esta ayuda\n\n"
        f"<i>Chat ID autorizado: {TELEGRAM_CHAT_ID}</i>"
    )
    await update.message.reply_text(help_text, parse_mode="HTML")


# ============================================================================
# Main
# ============================================================================

def main():
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN no configurado")
        sys.exit(1)

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("stop", cmd_stop))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("orders", cmd_orders))
    app.add_handler(CommandHandler("logs", cmd_logs))
    app.add_handler(CommandHandler("metrics", cmd_metrics))
    app.add_handler(CommandHandler("help", cmd_help))

    logger.info("Telegram bot iniciado. Esperando comandos del Líder (chat_id=%s)", TELEGRAM_CHAT_ID)
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
