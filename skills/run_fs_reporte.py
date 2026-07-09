"""Script para cron: genera y envía reporte diario FS a las 6:30pm."""
import asyncio
import sys
import os
import logging

# Cargar variables de entorno desde .env (cron no carga systemd EnvironmentFile)
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
logger = logging.getLogger("fs_reporte_cron")

async def main():
    try:
        from src.agents.financial_agent import get_agent
        agent = get_agent()
        agent.init()
        logger.info("Generando reporte diario FS...")
        reporte = await agent.generar_y_enviar_reporte()
        if reporte:
            logger.info("Reporte enviado: fecha=%s pedidos=%d ventas=€%.2f",
                         reporte.fecha, reporte.num_pedidos, reporte.ventas_total_eur)
        else:
            logger.warning("Reporte no generado")
    except Exception as e:
        logger.error("Error reporte FS: %s", e)

if __name__ == "__main__":
    asyncio.run(main())
