#!/usr/bin/env python3
"""
Cron job: Inventario de hielo en Odoo.
Ejecución: 8:00 AM diario (America/Caracas UTC-4).
Consulta stock de hielo (product.product) y envía a Telegram @Skynet_27_bot.
"""

import asyncio
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Any

from dotenv import load_dotenv

load_dotenv("/mnt/ssd_trabajo/hermes-agent/config/.env")

# Configurar paths
sys.path.insert(0, "/mnt/ssd_trabajo/hermes-agent")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("odoo.inventario_hielo")

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


async def get_hielo_inventory() -> dict[str, Any]:
    from src.integrations.odoo.odoo_sync import OdooClient

    try:
        odoo = OdooClient()
        if not odoo.connect():
            return {"error": "No se pudo conectar a Odoo"}

        # Buscar productos de hielo (categoría o nombre)
        # Primero buscar por nombre
        products = odoo.execute_kw(
            "product.product",
            "search_read",
            [["|", ("name", "ilike", "hielo"), ("name", "ilike", "ice")]],
            {
                "fields": [
                    "name",
                    "qty_available",
                    "virtual_available",
                    "uom_id",
                    "categ_id",
                    "standard_price",
                    "list_price",
                ]
            },
        )

        # Si no encuentra por nombre, buscar por categoría
        if not products:
            # Buscar categoría "Hielo" o "Ice"
            cats = odoo.execute_kw(
                "product.category",
                "search_read",
                [["|", ("name", "ilike", "hielo"), ("name", "ilike", "ice")]],
                {"fields": ["id", "name"], "limit": 5},
            )

            for cat in cats:
                cat_products = odoo.execute_kw(
                    "product.product",
                    "search_read",
                    [("categ_id", "=", cat["id"])],
                    {
                        "fields": [
                            "name",
                            "qty_available",
                            "virtual_available",
                            "uom_id",
                            "standard_price",
                            "list_price",
                        ]
                    },
                )
                products.extend(cat_products)

        return {
            "products": products,
            "count": len(products),
        }
    except Exception as e:
        logger.exception(f"Error inventario hielo: {e}")
        return {"error": str(e)}


async def main() -> None:
    logger.info("=== Iniciando odoo_inventario_hielo ===")

    result = await get_hielo_inventory()

    now = datetime.now(CARACAS_TZ).strftime("%Y-%m-%d %H:%M")

    if "error" in result:
        message = f"❌ <b>Inventario Hielo</b> ({now})\n\nError: {result['error']}"
    else:
        lines = [f"❄️ <b>Inventario Hielo</b> ({now})"]

        if result["count"] == 0:
            lines.append("⚠️ No se encontraron productos de hielo")
        else:
            total_qty = 0
            total_virtual = 0
            for p in result["products"]:
                name = p.get("name", "Sin nombre")
                qty = p.get("qty_available", 0)
                virtual = p.get("virtual_available", 0)
                uom = p.get("uom_id", [0, "und"])[1]
                total_qty += qty
                total_virtual += virtual
                lines.append(f"  📦 {name}: {qty} {uom} (disponible: {virtual} {uom})")

            lines.append(
                f"\n📊 Total en stock: <b>{total_qty}</b> | Próximo: <b>{total_virtual}</b>"
            )

        message = "\n".join(lines)

    await send_telegram(message)
    logger.info("=== Finalizado odoo_inventario_hielo ===")

    if "error" in result:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
