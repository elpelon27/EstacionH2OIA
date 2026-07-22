"""
 ============================================================================
 Telegram Bot — Kill Switch + Alerts para Valentina Bridge
 Estación H2O · Maracaibo, Venezuela
 ============================================================================

Corre como servicio systemd separado (telegram-bot.service).
Escucha comandos del Líder (chat_id verificado) y opera el kill switch.

Comandos:
    /status   — Estado del bridge (uptime, checks, kill_switch)
    /stop     — Activar kill switch (detiene respuestas de Valentina)
    /start    — Desactivar kill switch (Valentina vuelve a responder)
    /orders   — Pedidos de hoy
    /logs     — Últimos 20 logs del bridge
    /metrics  — Resumen métricas del día
    /tasa     — Ver/cambiar tasa EUR/VES (ej: /tasa 825.50)
    /help     — Mostrar ayuda

Seguridad:
    Solo el chat_id del Líder (TELEGRAM_CHAT_ID) tiene permiso.
 """

import os
import sys
import time
import sqlite3
import logging
from datetime import datetime, timezone, timedelta

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("telegram_bot")

CARACAS_TZ = timezone(timedelta(hours=-4))

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = int(os.getenv("TELEGRAM_CHAT_ID", "1663148211"))
KILL_SWITCH_FILE = os.getenv("KILL_SWITCH_FILE", "/mnt/ssd_trabajo/hermes-agent/data/valentina.kill")
SQLITE_PATH = os.getenv(
    "SQLITE_PATH", "/mnt/ssd_trabajo/hermes-agent/data/conversations.db"
)
BRIDGE_HEALTH_URL = os.getenv("BRIDGE_HEALTH_URL", "http://localhost:8000/health")


def _is_authorized(update: Update) -> bool:
    return update.effective_chat.id == TELEGRAM_CHAT_ID


async def _unauthorized(update: Update) -> None:
    await update.message.reply_text("🚫 No autorizado. Este bot es privado de Estación H2O.")
    logger.warning(
        "Acceso no autorizado de chat_id=%s username=%s",
        update.effective_chat.id,
        update.effective_user.username,
    )


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_authorized(update):
        return await _unauthorized(update)
    if os.path.exists(KILL_SWITCH_FILE):
        os.remove(KILL_SWITCH_FILE)
        await update.message.reply_text(
            "✅ Kill switch DESACTIVADO\nValentina está respondiendo de nuevo. 💧"
        )
        logger.info("Kill switch desactivado por Líder")
    else:
        await update.message.reply_text("ℹ️ El kill switch no estaba activo.")


async def cmd_stop(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_authorized(update):
        return await _unauthorized(update)
    # P0-3: crear con 0600 (antes en /tmp era 1777=writable por todos)
    import os as _os
    _fd = _os.open(KILL_SWITCH_FILE, _os.O_CREAT | _os.O_WRONLY | _os.O_TRUNC, 0o600)
    with _os.fdopen(_fd, "w") as f:
        f.write(f"killed by {update.effective_user.username} at {datetime.now(CARACAS_TZ)}")
    await update.message.reply_text(
        "🛑 Kill switch ACTIVADO\nValentina NO responderá mensajes nuevos.\nPara reactivar: /start"
    )
    logger.warning("Kill switch activado por Líder")


async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_authorized(update):
        return await _unauthorized(update)
    import httpx
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(BRIDGE_HEALTH_URL, timeout=5)
            health = resp.json()
    except Exception as e:
        await update.message.reply_text("❌ Bridge no responde: " + str(e))
        return
    kill_active = health.get("checks", {}).get("kill_switch", False)
    uptime = health.get("uptime_seconds", 0)
    status_emoji = "🛑" if kill_active else ("✅" if health["status"] == "ok" else "⚠️")
    msg = (
        status_emoji + " Estado Valentina Bridge\n\n"
        "• Status: " + str(health["status"]) + "\n"
        "• Uptime: " + str(int(uptime // 60)) + " min\n"
        "• Dify API: " + ("✅" if health["checks"]["dify_api_key"] else "❌") + "\n"
        "• Meta API: " + ("✅" if health["checks"]["meta_access_token"] else "❌") + "\n"
        "• SQLite: " + ("✅" if health["checks"]["sqlite"] else "❌") + "\n"
        "• Kill switch: " + ("🛑 ACTIVO" if kill_active else "✅ inactivo") + "\n"
    )
    await update.message.reply_text(msg)


async def cmd_orders(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
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
    msg = "📋 Pedidos de hoy (" + str(len(orders)) + ")\n\n"
    for oid, desc, status, ts in orders:
        time_str = datetime.fromtimestamp(ts, CARACAS_TZ).strftime("%H:%M")
        desc_short = desc[:80].replace("\n", " ")
        msg += "#" + str(oid) + " [" + time_str + "] " + desc_short + "\n   → " + status + "\n"
    await update.message.reply_text(msg)


async def cmd_logs(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
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
        await update.message.reply_text("❌ No se pudo leer logs: " + str(e))
        return
    if not logs:
        await update.message.reply_text("📭 No hay logs.")
        return
    if len(logs) > 3800:
        logs = logs[-3800:]
    await update.message.reply_text("📋 Últimos logs\n\n" + logs)


async def cmd_metrics(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_authorized(update):
        return await _unauthorized(update)
    import httpx
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get("http://localhost:8000/metrics", timeout=5)
            metrics_text = resp.text
    except Exception as e:
        await update.message.reply_text("❌ No se pudo obtener métricas: " + str(e))
        return

    def _extract(name):
        for line in metrics_text.split("\n"):
            if line.startswith(name) and not line.startswith(name + "_"):
                parts = line.split()
                return parts[-1] if len(parts) > 1 else "0"
        return "0"

    msg = (
        "📊 Métricas del bridge\n\n"
        "• Mensajes OK: " + _extract("valentina_messages_total") + "\n"
        "• Pedidos: " + _extract("valentina_orders_total") + "\n"
        "• Escalamientos: " + _extract("valentina_escalations_total") + "\n"
        "• Duplicados: " + _extract("valentina_dedup_hits_total") + "\n"
    )
    await update.message.reply_text(msg)


async def cmd_tasa(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Ver o cambiar tasa EUR/VES."""
    if not _is_authorized(update):
        return await _unauthorized(update)
    args = ctx.args
    if not args:
        sys.path.insert(0, "/mnt/ssd_trabajo/hermes-agent")
        from src.financial.currency import get_tasa_display
        await update.message.reply_text("Tasa actual: " + get_tasa_display())
        return
    try:
        tasa = float(args[0].replace(",", "."))
        sys.path.insert(0, "/mnt/ssd_trabajo/hermes-agent")
        from src.financial.currency import set_manual_rate
        set_manual_rate(tasa)
        await update.message.reply_text("✅ Tasa actualizada: 1 = Bs. " + str(tasa))
        logger.info("Tasa manual: %.2f", tasa)
    except ValueError:
        await update.message.reply_text("❌ Formato inválido. Usa: /tasa 825.50")


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_authorized(update):
        return await _unauthorized(update)
    help_text = (
        "💧 Valentina Bridge — Comandos\n\n"
        "/status — Estado del bridge\n"
        "/stop — 🛑 Activar kill switch\n"
        "/start — ✅ Desactivar kill switch\n"
        "/orders — 📋 Pedidos de hoy\n"
        "/logs — 📋 Últimos 20 logs\n"
        "/metrics — 📊 Métricas\n"
        "/tasa — 💱 Ver/cambiar tasa (ej: /tasa 825.50)\n"
        "/help — Esta ayuda\n\n"
        "Chat ID: " + str(TELEGRAM_CHAT_ID)
    )
    await update.message.reply_text(help_text)


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
    app.add_handler(CommandHandler("tasa", cmd_tasa))
    app.add_handler(CommandHandler("help", cmd_help))

    logger.info("Telegram bot iniciado. Esperando comandos del Líder (chat_id=%s)", TELEGRAM_CHAT_ID)
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
