#!/usr/bin/env python3
"""
Cron job: Nómina viernes en Odoo.
Ejecución: Viernes 5:00 PM (America/Caracas UTC-4).
Genera reporte de nómina semanal y envía a Telegram @Skynet_27_bot.
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
logger = logging.getLogger("odoo.nomina_viernes")

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


async def get_nomina_report() -> dict[str, Any]:
    from src.integrations.odoo.odoo_sync import OdooClient

    try:
        odoo = OdooClient()
        if not odoo.connect():
            return {"error": "No se pudo conectar a Odoo"}

        # Buscar empleados activos
        employees = odoo.execute_kw(
            "hr.employee",
            "search_read",
            [[("active", "=", True)]],
            {
                "fields": [
                    "name",
                    "job_id",
                    "department_id",
                    "contract_id",
                    "work_email",
                    "mobile_phone",
                ],
                "limit": 100,
            },
        )

        # Buscar contratos activos
        contracts = odoo.execute_kw(
            "hr.contract",
            "search_read",
            [[("state", "=", "open")]],
            {
                "fields": [
                    "name",
                    "employee_id",
                    "wage",
                    "wage_type",
                    "structure_type_id",
                    "date_start",
                    "date_end",
                ],
                "limit": 100,
            },
        )

        # Buscar estructuras de nómina
        structures = odoo.execute_kw(
            "hr.payroll.structure",
            "search_read",
            [],
            {"fields": ["name", "type_id", "rule_ids"], "limit": 50},
        )

        return {
            "employees": employees,
            "contracts": contracts,
            "structures": structures,
            "emp_count": len(employees),
            "contract_count": len(contracts),
        }
    except Exception as e:
        logger.exception(f"Error nómina: {e}")
        return {"error": str(e)}


async def main() -> None:
    logger.info("=== Iniciando odoo_nomina_viernes ===")

    result = await get_nomina_report()

    now = datetime.now(CARACAS_TZ).strftime("%Y-%m-%d %H:%M")

    if "error" in result:
        message = f"❌ <b>Nómina Viernes</b> ({now})\n\nError: {result['error']}"
    else:
        lines = [f"💼 <b>Nómina Viernes</b> ({now})"]
        lines.append(f"👥 Empleados activos: <b>{result['emp_count']}</b>")
        lines.append(f"📄 Contratos activos: <b>{result['contract_count']}</b>")

        if result["employees"]:
            lines.append("\n👤 <b>Empleados:</b>")
            for emp in result["employees"][:15]:
                name = emp.get("name", "Sin nombre")
                job = emp.get("job_id", [0, "Sin cargo"])[1]
                dept = emp.get("department_id", [0, "Sin depto"])[1]
                lines.append(f"  • {name} — {job} / {dept}")
            if len(result["employees"]) > 15:
                lines.append(f"  ... y {len(result['employees']) - 15} más")

        if result["contracts"]:
            lines.append("\n📋 <b>Contratos:</b>")
            for c in result["contracts"][:10]:
                name = c.get("name", "Sin nombre")
                emp = c.get("employee_id", [0, "Sin empleado"])[1]
                wage = c.get("wage", 0)
                lines.append(f"  • {name} ({emp}): ${wage:,.2f}/mes")

        message = "\n".join(lines)

    await send_telegram(message)
    logger.info("=== Finalizado odoo_nomina_viernes ===")

    if "error" in result:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
