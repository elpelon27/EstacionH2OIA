"""
============================================================================
Financial Shield — Analytics Skill (Reporte 7am)
Estación H2O · Maracaibo, Venezuela
============================================================================

Conecta el cron 7am existente con Financial Agent v3.0 real.
Reemplaza queries frágiles por llamadas a reportes.validados.
"""

import os
import sys
import logging
from typing import Any, Dict

# Configurar path para imports
sys.path.insert(0, "/mnt/ssd_trabajo/hermes-agent")

from src.financial import reportes

logger = logging.getLogger("financial_shield.analytics")


async def generar_reporte_diario_analytics(enviar_telegram: bool = True) -> Dict[str, Any]:
    """
    Genera reporte diario usando Financial Agent v3.0.
    
    Args:
        enviar_telegram: Si True, envía el reporte por Telegram al Líder.
        
    Returns:
        dict con claves: 'ok', 'enviado', 'reporte_id', 'mensaje', 'reporte'
    """
    try:
        logger.info("Generando reporte diario analytics (Financial Shield v3.0)...")
        
        # Usar función validada del módulo reportes
        reporte = await reportes.generar_y_enviar_reporte()
        
        if reporte and reporte.id:
            logger.info("✅ Reporte diario generado: ID=%d, fecha=%s", reporte.id, reporte.fecha)
            
            if enviar_telegram:
                # El envío ya está dentro de generar_y_enviar_reporte()
                # Verificar si se envió (reporte.enviado_telegram)
                enviado = bool(getattr(reporte, "enviado_telegram", False))
                return {
                    "ok": True,
                    "enviado": enviado,
                    "reporte_id": reporte.id,
                    "mensaje": f"Reporte {reporte.fecha} generado y enviado",
                    "reporte": reporte,
                }
            else:
                return {
                    "ok": True,
                    "enviado": False,
                    "reporte_id": reporte.id,
                    "mensaje": f"Reporte {reporte.fecha} generado (no enviado)",
                    "reporte": reporte,
                }
        else:
            logger.error("generar_y_enviar_reporte() no retornó reporte válido")
            return {
                "ok": False,
                "enviado": False,
                "reporte_id": None,
                "mensaje": "Error: reporte no generado",
                "reporte": None,
            }
            
    except Exception as e:
        logger.error("Error generando reporte analytics: %s", e, exc_info=True)
        return {
            "ok": False,
            "enviado": False,
            "reporte_id": None,
            "mensaje": f"Excepción: {e}",
            "reporte": None,
        }


async def main() -> None:
    """Punto de entrada para cron / CLI."""
    import logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    
    resultado = await generar_reporte_diario_analytics(enviar_telegram=True)
    
    if resultado["ok"]:
        print(f"✅ {resultado['mensaje']}")
        sys.exit(0)
    else:
        print(f"❌ {resultado['mensaje']}")
        sys.exit(1)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())