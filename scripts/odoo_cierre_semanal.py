#!/usr/bin/env python3
"""
Cron job: Cierre semanal de Odoo.
Ejecución: Viernes 6:00 PM (America/Caracas UTC-4).
Genera reporte consolidado de la semana y envía a Telegram @Skynet_27_bot.
"""

import asyncio
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Any

# Cargar .env
from dotenv import load_dotenv

load_dotenv("/mnt/ssd_trabajo/hermes-agent/config/.env")

# Configurar paths
sys.path.insert(0, "/mnt/ssd_trabajo/hermes-agent")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("odoo.cierre_semanal")

CARACAS_TZ = timezone(timedelta(hours=-4))


async def send_telegram(message: str) -> bool:
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN_HERMES") or os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID_HERMES") or os.getenv("TELEGRAM_CHAT_ID", "1663148211")

    if not bot_token:
        logger.warning("TELEGRAM_BOT_TOKEN no configurado")
        return False

    try:
        import telegram

        bot = telegram.Bot(token=bot_token)
        await bot.send_message(chat_id=chat_id, text=message, parse_mode="HTML")
        return True
    except Exception as e:
        logger.error(f"Error Telegram: {e}")
        return False


async def get_weekly_report() -> dict[str, Any]:
    from src.integrations.odoo.odoo_sync import OdooClient

    now = datetime.now(CARACAS_TZ)
    # Calcular lunes de esta semana
    monday = now - timedelta(days=now.weekday())
    monday_str = monday.strftime("%Y-%m-%d")
    now_str = now.strftime("%Y-%m-%d")

    try:
        odoo = OdooClient()
        if not odoo.connect():
            return {"error": "No se pudo conectar a Odoo"}

        domain = [
            ["date_order", ">=", f"{monday_str} 00:00:00"],
            ["date_order", "<=", f"{now_str} 23:59:59"],
            ["state", "in", ["sale", "done"]],
        ]
        orders = odoo.execute_kw(
            "sale.order",
            "search_read",
            [domain],
            {
                "fields": [
                    "name",
                    "partner_id",
                    "date_order",
                    "amount_total",
                    "state",
                    "currency_id",
                    "user_id",
                ]
            },
        )

        total_orders = len(orders)
        total_amount = sum(o.get("amount_total", 0) for o in orders)

        # Por día
        by_day = {}
        for o in orders:
            date_str = o.get("date_order", "")[:10]
            if date_str not in by_day:
                by_day[date_str] = {"count": 0, "total": 0}
            by_day[date_str]["count"] += 1
            by_day[date_str]["total"] += o.get("amount_total", 0)

        # Por vendedor
        by_user = {}
        for o in orders:
            user = o.get("user_id", [0, "Sin asignar"])[1]
            if user not in by_user:
                by_user[user] = {"count": 0, "total": 0}
            by_user[user]["count"] += 1
            by_user[user]["total"] += o.get("amount_total", 0)

        # Top clientes
        by_partner = {}
        for o in orders:
            partner = o.get("partner_id", [0, "Sin cliente"])[1]
            if partner not in by_partner:
                by_partner[partner] = {"count": 0, "total": 0}
            by_partner[partner]["count"] += 1
            by_partner[partner]["total"] += o.get("amount_total", 0)

        return {
            "period": f"{monday_str} a {now_str}",
            "total_orders": total_orders,
            "total_amount": total_amount,
            "by_day": by_day,
            "by_user": by_user,
            "top_partners": dict(sorted(by_partner.items(), key=lambda x: -x[1]["total"])[:10]),
        }
    except Exception as e:
        logger.exception(f"Error cierre semanal: {e}")
        return {"error": str(e)}


async def main() -> None:
    logger.info("=== Iniciando odoo_cierre_semanal ===")

    report = await get_weekly_report()

    if "error" in report:
        message = f"❌ <b>Cierre Semanal</b>\n\nError: {report['error']}"
    else:
        lines = [
            f"📊 <b>Cierre Semanal</b> ({report['period']})",
            f"📦 Órdenes: <b>{report['total_orders']}</b>",
            f"💰 Total: <b>${report['total_amount']:.2f}</b>",
            "\n📅 <b>Por día:</b>",
        ]
        for day in sorted(report["by_day"].keys()):
            d = report["by_day"][day]
            lines.append(f"  {day}: {d['count']} órdenes, ${d['total']:.2f}")

        lines.append("\n👤 <b>Por vendedor:</b>")
        for user, data in sorted(report["by_user"].items(), key=lambda x: -x[1]["total"]):
            lines.append(f"  {user}: {data['count']} órdenes, ${data['total']:.2f}")

        lines.append("\n🏆 <b>Top 10 clientes:</b>")
        for partner, data in list(report["top_partners"].items())[:10]:
            lines.append(f"  {partner}: {data['count']} órdenes, ${data['total']:.2f}")

        message = "\n".join(lines)

    await send_telegram(message)
    logger.info("=== Finalizado odoo_cierre_semanal ===")

    if "error" in report:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
