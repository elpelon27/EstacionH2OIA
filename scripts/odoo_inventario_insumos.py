#!/usr/bin/env python3
"""
Cron job: Inventario de insumos en Odoo.
Ejecución: Lunes 8:00 AM (America/Caracas UTC-4).
Consulta stock de botellones, vasos, tapas, etc. y envía a Telegram @Skynet_27_bot.
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
logger = logging.getLogger("odoo.inventario_insumos")

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


async def get_insumos_inventory() -> dict[str, Any]:
    from src.integrations.odoo.odoo_sync import OdooClient

    # Palabras clave para insumos
    keywords = [
        "botellon",
        "botellón",
        "garrafa",
        "vaso",
        "cup",
        "tapa",
        "cap",
        "tapón",
        "etiqueta",
        "label",
        "bolsa",
        "bag",
        "preforma",
        "preform",
    ]

    try:
        odoo = OdooClient()
        if not odoo.connect():
            return {"error": "No se pudo conectar a Odoo"}

        # Construir domain OR para búsqueda (mezcla operador "|" con tuplas)
        domain: list[Any] = []
        for i, kw in enumerate(keywords):
            if i == 0:
                domain.append(("name", "ilike", kw))
            else:
                domain.insert(0, "|")
                domain.append(("name", "ilike", kw))

        products = odoo.execute_kw(
            "product.product",
            "search_read",
            [domain],
            {
                "fields": [
                    "name",
                    "qty_available",
                    "virtual_available",
                    "uom_id",
                    "categ_id",
                    "standard_price",
                    "list_price",
                    "type",
                ]
            },
        )

        return {
            "products": products,
            "count": len(products),
        }
    except Exception as e:
        logger.exception(f"Error inventario insumos: {e}")
        return {"error": str(e)}


async def main() -> None:
    logger.info("=== Iniciando odoo_inventario_insumos ===")

    result = await get_insumos_inventory()

    now = datetime.now(CARACAS_TZ).strftime("%Y-%m-%d %H:%M")

    if "error" in result:
        message = f"❌ <b>Inventario Insumos</b> ({now})\n\nError: {result['error']}"
    else:
        lines = [f"📦 <b>Inventario Insumos</b> ({now})"]

        if result["count"] == 0:
            lines.append("⚠️ No se encontraron insumos")
            message = "\n".join(lines)
        else:
            # Agrupar por categoría
            by_categ: dict[str, list[dict[str, Any]]] = {}
            for p in result["products"]:
                categ = p.get("categ_id", [0, "Sin categoría"])[1]
                if categ not in by_categ:
                    by_categ[categ] = []
                by_categ[categ].append(p)

            for categ, prods in sorted(by_categ.items()):
                lines.append(f"\n📂 <b>{categ}</b> ({len(prods)} items):")
                for p in prods:
                    name = p.get("name", "Sin nombre")
                    qty = p.get("qty_available", 0)
                    virtual = p.get("virtual_available", 0)
                    uom = p.get("uom_id", [0, "und"])[1]
                    alert = " 🔴" if qty <= 10 else (" 🟡" if qty <= 50 else "")
                    lines.append(f"  • {name}: {qty} {uom} (disp: {virtual}){alert}")

            message = "\n".join(lines)

    await send_telegram(message)
    logger.info("=== Finalizado odoo_inventario_insumos ===")

    if "error" in result:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
