"""
 ============================================================================
 Financial Shield — Reportes diarios (6:30 PM Telegram)
 Estación H2O · Maracaibo, Venezuela
 ============================================================================

Genera y envía reporte diario a las 6:30 PM (cierre 6pm + 30min buffer).
 """

import os
import logging
import httpx
from datetime import datetime, timezone, timedelta
from typing import Optional

from . import database as db
from .models import ReporteDiario
from .currency import get_eur_ves_rate, get_tasa_display, convert_eur_to_ves
from .cobranzas import get_resumen_cobranzas
from .proveedores import get_total_egresos_periodo
from .nomina import generar_reporte_nomina
import asyncio

logger = logging.getLogger("financial_shield.reportes")

CARACAS_TZ = timezone(timedelta(hours=-4))

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "1663148211")


async def generar_reporte_diario() -> ReporteDiario:
    """Genera reporte diario con todas las métricas del día."""
    today = datetime.now(CARACAS_TZ).strftime("%Y-%m-%d")
    now_iso = datetime.now(CARACAS_TZ).isoformat()

    # Obtener tasa
    tasa = await get_eur_ves_rate()
    if tasa is None:
        tasa = 0.0
        logger.warning("Tasa EUR/VES no disponible, usando 0")

    # Consultar pedidos del día
    with db.get_db() as conn:
        # Ventas del día
        ventas = conn.execute("""
            SELECT
                COUNT(*) as num_pedidos,
                SUM(monto_total_eur) as total_eur,
                SUM(CASE WHEN estado_pago = 'pagado' THEN 1 ELSE 0 END) as num_pagados,
                SUM(CASE WHEN estado_pago IN ('pendiente', 'verificando', 'parcial') THEN 1 ELSE 0 END) as num_pendientes,
                SUM(CASE WHEN estado_pago = 'moroso' THEN 1 ELSE 0 END) as num_morosos
            FROM fs_pedidos
            WHERE DATE(creado_at) = ?
        """, (today,)).fetchone()

        # Cobros del día (pagos verificados)
        cobros = conn.execute("""
            SELECT SUM(monto_eur) as total_cobros_eur
            FROM fs_pagos
            WHERE DATE(verificado_at) = ? AND verificado = 1
        """, (today,)).fetchone()

        # Por cobrar (pendiente + vencido)
        por_cobrar = conn.execute("""
            SELECT SUM(monto_total_eur) as total
            FROM fs_pedidos
            WHERE estado_pago IN ('pendiente', 'verificando', 'parcial', 'vencido', 'moroso')
        """).fetchone()

    # Egresos a proveedores del día
    egresos = get_total_egresos_periodo(today, today)

    # Resumen cobranzas
    cobranzas = get_resumen_cobranzas()

    # Construir reporte
    ventas_eur = ventas["total_eur"] or 0 if ventas else 0
    cobros_eur = cobros["total_cobros_eur"] or 0 if cobros else 0
    por_cobrar_eur = por_cobrar["total"] or 0 if por_cobrar else 0

    ventas_ves = convert_eur_to_ves(ventas_eur, tasa) if tasa else 0
    cobros_ves = convert_eur_to_ves(cobros_eur, tasa) if tasa else 0
    por_cobrar_ves = convert_eur_to_ves(por_cobrar_eur, tasa) if tasa else 0

    reporte = ReporteDiario(
        fecha=today,
        ventas_total_eur=round(ventas_eur, 2),
        cobros_total_eur=round(cobros_eur, 2),
        por_cobrar_eur=round(por_cobrar_eur, 2),
        ventas_total_ves=round(ventas_ves, 2),
        cobros_total_ves=round(cobros_ves, 2),
        por_cobrar_ves=round(por_cobrar_ves, 2),
        num_pedidos=ventas["num_pedidos"] if ventas else 0,
        num_pagados=ventas["num_pagados"] if ventas else 0,
        num_pendientes=ventas["num_pendientes"] if ventas else 0,
        num_morosos=ventas["num_morosos"] if ventas else 0,
        nomina_eur=0.0,  # Se calcula por separado
        generado_at=now_iso,
    )

    # Guardar en BD
    reporte_id = db.save_reporte_diario(reporte)
    reporte.id = reporte_id

    return reporte


def formatear_reporte_telegram(reporte: ReporteDiario, tasa_str: str) -> str:
    """Formatea el reporte como mensaje HTML para Telegram."""
    lineas = [
        f"📊 <b>REPORTE DIARIO — {reporte.fecha}</b>\n",
        f"💱 Tasa: {tasa_str}\n",
        f"━━━━━━━━━━━━━━━━━━\n",
        f"📦 <b>Ventas</b>\n",
        f"  Pedidos: {reporte.num_pedidos}\n",
        f"  Pagados: {reporte.num_pagados}\n",
        f"  Pendientes: {reporte.num_pendientes}\n",
        f"  Morosos: {reporte.num_morosos}\n",
        f"  Total: €{reporte.ventas_total_eur:.2f} (Bs. {reporte.ventas_total_ves:.2f})\n",
        f"━━━━━━━━━━━━━━━━━━\n",
        f"💰 <b>Cobros del día</b>\n",
        f"  €{reporte.cobros_total_eur:.2f} (Bs. {reporte.cobros_total_ves:.2f})\n",
        f"━━━━━━━━━━━━━━━━━━\n",
        f"⏳ <b>Por cobrar (total)</b>\n",
        f"  €{reporte.por_cobrar_eur:.2f} (Bs. {reporte.por_cobrar_ves:.2f})\n",
    ]

    # Agregar morosos si hay
    if reporte.num_morosos > 0:
        lineas.append(f"\n🚨 <b>Clientes morosos: {reporte.num_morosos}</b>")

    lineas.append(f"\n━━━━━━━━━━━━━━━━━━")
    lineas.append(f"💧 Estación H2O — {datetime.now(CARACAS_TZ).strftime('%H:%M')}")

    return "\n".join(lineas)


async def enviar_reporte_telegram(reporte: ReporteDiario) -> bool:
    """Envía reporte por Telegram al Líder."""
    if not TELEGRAM_BOT_TOKEN:
        logger.warning("Telegram no configurado, reporte no enviado")
        return False

    tasa_str = get_tasa_display()
    mensaje = formatear_reporte_telegram(reporte, tasa_str)

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                json={
                    "chat_id": TELEGRAM_CHAT_ID,
                    "text": mensaje,
                    "parse_mode": "HTML",
                },
                timeout=10,
            )
            if resp.status_code == 200:
                msg_id = resp.json().get("result", {}).get("message_id", "")
                db.mark_reporte_enviado(reporte.id, str(msg_id))
                logger.info("Reporte diario enviado por Telegram")
                return True
            else:
                logger.error("Error enviando reporte Telegram: %d", resp.status_code)
    except Exception as e:
        logger.error("Error enviando reporte: %s", e)
    return False


async def generar_y_enviar_reporte():
    """Función principal: genera + envía reporte diario."""
    reporte = await generar_reporte_diario()
    await enviar_reporte_telegram(reporte)
    return reporte
