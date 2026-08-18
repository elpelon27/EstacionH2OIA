#!/usr/bin/env python3
"""
Cron job: Reporte diario de ventas desde Odoo.
Ejecución: 11:00 PM diario (America/Caracas UTC-4).
Genera reporte de ventas del día y envía a Telegram @Skynet_27_bot.
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

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("odoo.ventas_diarias")

CARACAS_TZ = timezone(timedelta(hours=-4))


async def send_telegram(message: str) -> bool:
    """Envía mensaje a Telegram @Skynet_27_bot."""
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN_HERMES") or os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID_HERMES") or os.getenv("TELEGRAM_CHAT_ID", "1663148211")
    assert chat_id is not None

    if not bot_token:
        logger.warning("TELEGRAM_BOT_TOKEN no configurado - saltando envío Telegram")
        return False

    try:
        import telegram

        bot = telegram.Bot(token=bot_token)
        await bot.send_message(chat_id=chat_id, text=message, parse_mode="HTML")
        logger.info("Telegram enviado correctamente")
        return True
    except Exception as e:
        logger.error(f"Error enviando Telegram: {e}")
        return False


async def get_odoo_sales_report(date_str: str | None = None) -> dict[str, Any]:
    """Obtiene reporte de ventas de Odoo para una fecha."""
    if date_str is None:
        date_str = datetime.now(CARACAS_TZ).strftime("%Y-%m-%d")

    from src.integrations.odoo.odoo_sync import OdooClient

    try:
        odoo = OdooClient()
        if not odoo.connect():
            return {"error": "No se pudo conectar a Odoo", "date": date_str}

        # Buscar órdenes del día usando execute_kw
        domain = [
            ["date_order", ">=", f"{date_str} 00:00:00"],
            ["date_order", "<=", f"{date_str} 23:59:59"],
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
                ]
            },
        )

        # Calcular totales
        total_orders = len(orders)
        total_amount = sum(o.get("amount_total", 0) for o in orders)

        # Agrupar por cliente
        by_partner = {}
        for o in orders:
            partner = o.get("partner_id", [0, "Sin cliente"])[1]
            if partner not in by_partner:
                by_partner[partner] = {"count": 0, "total": 0}
            by_partner[partner]["count"] += 1
            by_partner[partner]["total"] += o.get("amount_total", 0)

        return {
            "date": date_str,
            "total_orders": total_orders,
            "total_amount": total_amount,
            "by_partner": by_partner,
            "orders": orders,
        }
    except Exception as e:
        logger.exception(f"Error obteniendo reporte Odoo: {e}")
        return {"error": str(e), "date": date_str}


async def main() -> None:
    logger.info("=== Iniciando odoo_reporte_ventas_diarias ===")

    date_str = datetime.now(CARACAS_TZ).strftime("%Y-%m-%d")
    report = await get_odoo_sales_report(date_str)

    if "error" in report:
        message = f"❌ <b>Reporte Ventas Diario</b> ({date_str})\n\nError: {report['error']}"
    else:
        lines = [f"📈 <b>Reporte Ventas Diario</b> ({date_str})"]
        lines.append(f"📦 Órdenes: <b>{report['total_orders']}</b>")
        lines.append(f"💰 Total: <b>${report['total_amount']:.2f}</b>")

        if report["by_partner"]:
            lines.append("\n👥 <b>Por cliente:</b>")
            for partner, data in sorted(report["by_partner"].items(), key=lambda x: -x[1]["total"])[
                :10
            ]:
                lines.append(f"  • {partner}: {data['count']} órdenes, ${data['total']:.2f}")
            if len(report["by_partner"]) > 10:
                lines.append(f"  ... y {len(report['by_partner']) - 10} clientes más")

        message = "\n".join(lines)

    await send_telegram(message)
    logger.info("=== Finalizado odoo_reporte_ventas_diarias ===")

    if "error" in report:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
