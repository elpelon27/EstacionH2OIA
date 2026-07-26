#!/usr/bin/env python3
"""Script para cron 08:00 — check-in matutino del dispatcher.

Verifica que:
- El servicio dispatcher-bot.service esté activo.
- La BD dispatch.db responda y tenga clientes/vehicles.
- La BD conversations.db tenga dispatch_queue con pedidos pending.

Envía resumen por Telegram al Líder.
"""
import asyncio
import sys
import os
import sqlite3
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Cargar .env
env_path = Path("/mnt/ssd_trabajo/hermes-agent/config/.env")
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

sys.path.insert(0, "/mnt/ssd_trabajo/hermes-agent")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("dispatcher_checkin")

CARACAS_TZ = timezone(timedelta(hours=-4))
DB_DISPATCH = os.getenv("DISPATCH_DB_PATH", "/mnt/ssd_trabajo/hermes-agent/data/dispatch.db")
DB_CONV = os.getenv("SQLITE_PATH", "/mnt/ssd_trabajo/hermes-agent/data/conversations.db")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "1663148211")


def _check_conversations_db() -> dict[str, int]:
    """Verifica conversations.db: dispatch_queue pedidos pending."""
    info = {"dispatch_queue_pending": 0, "dispatch_queue_total": 0, "orders_today": 0}
    try:
        conn = sqlite3.connect(DB_CONV)
        row = conn.execute(
            "SELECT estado, COUNT(*) FROM dispatch_queue GROUP BY estado"
        ).fetchall()
        info["dispatch_queue_total"] = sum(r[1] for r in row) if row else 0
        info["dispatch_queue_pending"] = next(
            (r[1] for r in row if r[0] == "pending"), 0
        )
        conn.close()
    except Exception as e:
        logger.error("Error leyendo conversations.db: %s", e)
    return info


def _check_dispatch_db() -> dict[str, int]:
    """Verifica dispatch.db: clientes, vehicles, deliveries."""
    info = {"clients": 0, "vehicles": 0, "deliveries_pending": 0}
    try:
        conn = sqlite3.connect(DB_DISPATCH)
        for table in ("clients", "vehicles"):
            count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
            info[table] = count[0] if count else 0
        row = conn.execute(
            "SELECT status, COUNT(*) FROM deliveries GROUP BY status"
        ).fetchall()
        info["deliveries_pending"] = next(
            (r[1] for r in row if r[0] == "pending"), 0
        )
        conn.close()
    except Exception as e:
        logger.error("Error leyendo dispatch.db: %s", e)
    return info


def _check_service() -> str:
    """Verifica que dispatcher-bot.service esté activo."""
    try:
        import subprocess
        r = subprocess.run(
            ["systemctl", "is-active", "dispatcher-bot.service"],
            capture_output=True, text=True, timeout=5
        )
        return r.stdout.strip()
    except Exception:
        return "unknown"


async def main() -> None:
    try:
        import httpx

        now = datetime.now(CARACAS_TZ)
        svc_status = _check_service()
        conv_info = _check_conversations_db()
        dispatch_info = _check_dispatch_db()

        msg = (
            f"📋 **Dispatcher Check-in {now.strftime('%Y-%m-%d %H:%M')}**\n\n"
            f"🤖 Servicio: {svc_status}\n"
            f"👤 Clients: {dispatch_info['clients']}\n"
            f"🚗 Vehicles: {dispatch_info['vehicles']}\n"
            f"📦 Deliveries pending: {dispatch_info['deliveries_pending']}\n"
            f"📬 Dispatch queue pending: {conv_info['dispatch_queue_pending']}\n"
            f"📊 Dispatch queue total: {conv_info['dispatch_queue_total']}\n"
        )
        logger.info("Check-in: %s | clients=%d vehicles=%d pending=%d",
                    svc_status, dispatch_info["clients"],
                    dispatch_info["vehicles"], conv_info["dispatch_queue_pending"])

        if TELEGRAM_BOT_TOKEN:
            async with httpx.AsyncClient() as client:
                await client.post(
                    f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                    json={
                        "chat_id": TELEGRAM_CHAT_ID,
                        "text": msg,
                        "parse_mode": "Markdown",
                    },
                    timeout=10,
                )
            logger.info("Check-in enviado por Telegram")
        else:
            logger.info("TELEGRAM_BOT_TOKEN no configurado — solo log local")

    except Exception as e:
        logger.error("Error dispatcher check-in: %s", e)


if __name__ == "__main__":
    asyncio.run(main())
