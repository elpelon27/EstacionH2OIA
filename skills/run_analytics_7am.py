#!/usr/bin/env python3
"""Script para cron: reporte analytics 7am — resumen día anterior.
Usa Analytics Skill (Financial Shield v3.0) en lugar de queries frágiles."""

import asyncio
import logging
import os
import sys
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
logger = logging.getLogger("analytics_7am_cron")


async def main() -> None:
    try:
        from skills.analytics_skill import generar_reporte_diario_analytics

        resultado = await generar_reporte_diario_analytics(enviar_telegram=True)

        if resultado["ok"]:
            logger.info("✅ Cron analytics 7am completado OK: %s", resultado["mensaje"])
        else:
            logger.error("Cron analytics 7am FALLÓ: %s", resultado["mensaje"])
            sys.exit(1)

    except Exception as e:
        logger.error("Error cron analytics 7am: %s", e, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
