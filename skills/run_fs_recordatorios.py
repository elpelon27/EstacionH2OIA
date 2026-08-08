"""Script para cron: procesa recordatorios pendientes cada 30 min."""
import asyncio
import logging
import os
import sys

# Cargar .env
from pathlib import Path

env_path = Path("/mnt/ssd_trabajo/hermes-agent/config/.env")
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip())

sys.path.insert(0, '/mnt/ssd_trabajo/hermes-agent')

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger("fs_recordatorios_cron")

async def main() -> None:
    try:
        from src.agents.financial_agent import get_agent
        agent = get_agent()
        agent.init()
        logger.info("Procesando recordatorios pendientes...")
        resultados = await agent.procesar_recordatorios_pendientes()
        if resultados:
            logger.info("Recordatorios procesados: %d", len(resultados))
            for r in resultados:
                logger.info("  → %s", r)
        else:
            logger.info("No hay recordatorios pendientes")
    except Exception as e:
        logger.error("Error recordatorios FS: %s", e)

if __name__ == "__main__":
    asyncio.run(main())
