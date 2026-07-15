"""Script para cron: reporte analytics 7am — resumen día anterior."""
import asyncio
import sys
import os
import sqlite3
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Cargar .env
env_path = Path("/mnt/ssd_trabajo/hermes-agent/config/.env")
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

sys.path.insert(0, '/mnt/ssd_trabajo/hermes-agent')

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger("analytics_7am")

CARACAS_TZ = timezone(timedelta(hours=-4))
DB_PATH = os.getenv("SQLITE_PATH", "/mnt/ssd_trabajo/hermes-agent/data/conversations.db")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "1663148211")

async def main():
    try:
        import httpx

        # Fechas
        today = datetime.now(CARACAS_TZ)
        yesterday = today - timedelta(days=1)
        yesterday_str = yesterday.strftime("%Y-%m-%d")
        today_str = today.strftime("%Y-%m-%d")

        conn = sqlite3.connect(DB_PATH)

        # 1. Pedidos del día anterior (desde orders de Valentina)
        pedidos = conn.execute("""
            SELECT id, product_description, created_at
            FROM orders
            WHERE product_description LIKE '%✅ Pedido confirmado%'
            AND date(datetime(created_at, 'unixepoch', '-4 hours')) = ?
        """, (yesterday_str,)).fetchall()

        total_pedidos = len(pedidos)

        # 2. Parsear cantidades y ingresos
        import re
        total_botellones = 0
        total_hielo = 0
        total_ingresos_eur = 0.0

        for p in pedidos:
            desc = p[1] or ""
            bot_match = re.search(r'(\d+)\s*botellones?\s*de\s*agua', desc, re.IGNORECASE)
            hielo_match = re.search(r'(\d+)\s*bolsas?\s*de\s*hielo', desc, re.IGNORECASE)
            total_match = re.search(r'[€eE][Uu]?[Rr]?[Oo]?[Ss]?\s*:?\s*(\d+[.,]?\d*)', desc)

            if bot_match:
                total_botellones += int(bot_match.group(1))
            if hielo_match:
                total_hielo += int(hielo_match.group(1))
            if total_match:
                try:
                    total_ingresos_eur += float(total_match.group(1).replace(",", "."))
                except ValueError:
                    pass

        if total_ingresos_eur == 0 and (total_botellones + total_hielo) > 0:
            total_ingresos_eur = (total_botellones * 1.00) + (total_hielo * 1.20)

        # 3. Clientes únicos (por phone_hash)
        clientes_unicos = conn.execute("""
            SELECT COUNT(DISTINCT phone_hash)
            FROM orders
            WHERE product_description LIKE '%✅ Pedido confirmado%'
            AND date(datetime(created_at, 'unixepoch', '-4 hours')) = ?
        """, (yesterday_str,)).fetchone()[0]

        # 4. Pedidos pendientes de pago (fs_pedidos)
        pendientes_pago = conn.execute("""
            SELECT COUNT(*) FROM fs_pedidos
            WHERE estado_pago IN ('pendiente', 'verificando', 'parcial')
        """).fetchone()[0]

        por_cobrar_eur = conn.execute("""
            SELECT COALESCE(SUM(monto_total_eur), 0) FROM fs_pedidos
            WHERE estado_pago IN ('pendiente', 'verificando', 'parcial')
        """).fetchone()[0]

        # 5. Nómina acumulada semana (botellones repartidos × €0.07)
        # Lunes de esta semana
        lunes = (today - timedelta(days=today.weekday())).strftime("%Y-%m-%d")
        botellones_semana = conn.execute("""
            SELECT COALESCE(SUM(botellones_cantidad), 0)
            FROM fs_pedidos
            WHERE date(datetime(creado_at, '-4 hours')) >= ?
            AND estado_entrega != 'sin_entregar'
        """, (lunes,)).fetchone()[0]

        nomina_comision = botellones_semana * 0.07 * 2  # 2 empleados
        conn.close()

        # 6. Tasa actual
        try:
            from src.financial.currency import get_tasa_display
            tasa_str = get_tasa_display()
        except:
            tasa_str = "N/A"

        # 7. Calcular Bs.
        total_ingresos_bs = 0
        try:
            from src.financial.currency import convert_eur_to_ves
            total_ingresos_bs = convert_eur_to_ves(total_ingresos_eur) or 0
        except:
            pass

        # 8. Construir mensaje
        producto_top = "Botellones" if total_botellones >= total_hielo else "Hielo"

        msg = (
            f"🌅 <b>REPORTE 7AM — {yesterday_str}</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"💱 {tasa_str}\n\n"
            f"📦 <b>Ventas de ayer</b>\n"
            f"  Pedidos: {total_pedidos}\n"
            f"  Clientes únicos: {clientes_unicos}\n"
            f"  Botellones: {total_botellones}\n"
            f"  Bolsas hielo: {total_hielo}\n"
            f"  Producto top: {producto_top}\n"
            f"  Ingresos: €{total_ingresos_eur:.2f} (Bs. {total_ingresos_bs:.2f})\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"⏳ <b>Por cobrar</b>\n"
            f"  Pedidos pendientes: {pendientes_pago}\n"
            f"  Monto: €{por_cobrar_eur:.2f}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"👷 <b>Nómina semana</b> (desde {lunes})\n"
            f"  Botellones repartidos: {botellones_semana}\n"
            f"  Comisión total (2 emp): €{nomina_comision:.2f}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"💧 Estación H2O — {today.strftime('%H:%M')}"
        )

        # 9. Enviar por Telegram
        if TELEGRAM_BOT_TOKEN:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                    json={
                        "chat_id": TELEGRAM_CHAT_ID,
                        "text": msg,
                        "parse_mode": "HTML",
                    },
                    timeout=10,
                )
                if resp.status_code == 200:
                    logger.info("✅ Reporte 7am enviado por Telegram")
                else:
                    logger.error("Error Telegram: %d", resp.status_code)
        else:
            logger.warning("Telegram no configurado")
            print(msg)

        logger.info("Reporte: pedidos=%d ingresos=€%.2f clientes=%d", total_pedidos, total_ingresos_eur, clientes_unicos)

    except Exception as e:
        logger.error("Error analytics 7am: %s", e)

if __name__ == "__main__":
    asyncio.run(main())
