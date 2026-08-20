#!/usr/bin/env python3
"""
Cron job: Actualizar tasa BCV desde R4 Conecta.
Ejecución: 9:00 AM y 3:00 PM hora Caracas (America/Caracas UTC-4).
Guarda en fs_tasas_cambio (par='USD/VES' y 'EUR/VES').
Envía resultado a Telegram @Skynet_27_bot.
"""

import asyncio
import logging
import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from typing import Any

# Cargar .env desde config/
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
logger = logging.getLogger("r4.tasa_bcv")

# Paths
SQLITE_PATH = os.getenv("SQLITE_PATH", "/mnt/ssd_trabajo/hermes-agent/data/conversations.db")
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


async def fetch_fallback_tasas() -> dict[str, Any]:
    """
    Fallback: consulta tasas USD/VES y EUR/VES desde open.er-api.com.

    Usado cuando R4 Conecta falla (code 108, credenciales pendientes, etc.).

    Hace DOS llamadas independientes para obtener cada par directo:
    - GET /v6/latest/USD → rate VES = USD/VES directo
    - GET /v6/latest/EUR → rate VES = EUR/VES directo
    """
    import httpx

    results: dict[str, Any] = {"USD": None, "EUR": None, "errors": [], "fuente": "open_er_api"}

    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            # USD/VES directo
            resp_usd = await client.get("https://open.er-api.com/v6/latest/USD")
            if resp_usd.status_code == 200:
                ves_usd = resp_usd.json().get("rates", {}).get("VES")
                if ves_usd:
                    results["USD"] = round(float(ves_usd), 4)
                    logger.info(f"Fallback USD/VES: {results['USD']}")
                else:
                    results["errors"].append("Fallback USD: VES no encontrado")
            else:
                results["errors"].append(f"Fallback USD HTTP {resp_usd.status_code}")

            # EUR/VES directo (endpoint separado con base EUR)
            resp_eur = await client.get("https://open.er-api.com/v6/latest/EUR")
            if resp_eur.status_code == 200:
                ves_eur = resp_eur.json().get("rates", {}).get("VES")
                if ves_eur:
                    results["EUR"] = round(float(ves_eur), 4)
                    logger.info(f"Fallback EUR/VES: {results['EUR']}")
                else:
                    results["errors"].append("Fallback EUR: VES no encontrado")
            else:
                results["errors"].append(f"Fallback EUR HTTP {resp_eur.status_code}")

    except Exception as e:
        results["errors"].append(f"Fallback excepción: {e}")
        logger.error(f"Error en fallback open.er-api.com: {e}")

    return results


async def update_tasa_bcv() -> dict[str, Any]:
    """
    Actualiza tasa BCV desde R4 Conecta.

    Si R4 falla (code 108, timeout, etc.), cae a fallback open.er-api.com.
    """
    from src.integrations.r4.client import R4Client

    results: dict[str, Any] = {"USD": None, "EUR": None, "errors": [], "fuente": "R4_BCV"}
    r4_failed = False

    try:
        async with R4Client() as client:
            fechavalor = datetime.now(CARACAS_TZ).strftime("%Y-%m-%d")

            # USD
            response_usd = await client.consulta_tasa_bcv(fechavalor, "USD")
            if response_usd.success and response_usd.data.get("tipocambio"):
                tasa_usd = float(response_usd.data["tipocambio"])
                results["USD"] = tasa_usd
                logger.info(f"Tasa BCV USD: {tasa_usd}")
            else:
                error = f"USD: {response_usd.message}"
                results["errors"].append(error)
                logger.error(error)
                r4_failed = True

            # EUR (solo consultar si USD tuvo exito)
            if not r4_failed:
                response_eur = await client.consulta_tasa_bcv(fechavalor, "EUR")
                if response_eur.success and response_eur.data.get("tipocambio"):
                    tasa_eur = float(response_eur.data["tipocambio"])
                    results["EUR"] = tasa_eur
                    logger.info(f"Tasa BCV EUR: {tasa_eur}")
                else:
                    error = f"EUR: {response_eur.message}"
                    results["errors"].append(error)
                    logger.error(error)
                    r4_failed = True

    except Exception as e:
        error = f"Excepción R4: {e}"
        results["errors"].append(error)
        logger.exception(error)
        r4_failed = True

    # Fallback a open.er-api.com si R4 fallo
    if r4_failed:
        logger.warning("R4 BCV falló, usando fallback open.er-api.com")
        fallback = await fetch_fallback_tasas()
        if fallback["USD"] is not None:
            results["USD"] = fallback["USD"]
        if fallback["EUR"] is not None:
            results["EUR"] = fallback["EUR"]
        results["fuente"] = "open_er_api"
        # Limpiar errores si el fallback obtuvo tasas
        if results["USD"] is not None or results["EUR"] is not None:
            results["errors"] = []

    return results


def save_tasas(
    usd: float | None = None, eur: float | None = None, fuente: str = "R4_BCV"
) -> bool:
    """Guarda tasas en SQLite fs_tasas_cambio (INSERT — tabla de historial)."""
    try:
        conn = sqlite3.connect(SQLITE_PATH)
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")

        now = datetime.now(CARACAS_TZ).isoformat()

        if usd is not None:
            conn.execute(
                """INSERT INTO fs_tasas_cambio (par, tasa, registrado_at, fuente)
                   VALUES ('USD/VES', ?, ?, ?)""",
                (usd, now, fuente),
            )
            logger.info(f"Guardado USD/VES = {usd} (fuente: {fuente})")

        if eur is not None:
            conn.execute(
                """INSERT INTO fs_tasas_cambio (par, tasa, registrado_at, fuente)
                   VALUES ('EUR/VES', ?, ?, ?)""",
                (eur, now, fuente),
            )
            logger.info(f"Guardado EUR/VES = {eur} (fuente: {fuente})")

        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.exception(f"Error guardando tasas: {e}")
        return False


def get_last_tasas() -> dict[str, Any]:
    """Obtiene últimas tasas guardadas para comparar."""
    try:
        conn = sqlite3.connect(SQLITE_PATH)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT par, tasa, registrado_at FROM fs_tasas_cambio WHERE par IN ('USD/VES', 'EUR/VES')"
        ).fetchall()
        conn.close()
        return {
            row["par"]: {"tasa": row["tasa"], "registrado_at": row["registrado_at"]} for row in rows
        }
    except Exception as e:
        logger.warning(f"Error leyendo tasas previas: {e}")
        return {}


async def main() -> None:
    """Main entry point."""
    logger.info("=== Iniciando r4_update_tasa_bcv ===")

    # Leer tasas previas
    prev = get_last_tasas()
    prev_usd = prev.get("USD/VES", {}).get("tasa")
    prev_eur = prev.get("EUR/VES", {}).get("tasa")

    # Consultar R4 (con fallback automático)
    results = await update_tasa_bcv()

    usd = results["USD"]
    eur = results["EUR"]
    errors = results["errors"]
    fuente = results.get("fuente", "R4_BCV")

    # Guardar si hay cambios
    saved = False
    if usd is not None and usd != prev_usd or eur is not None and eur != prev_eur:
        saved = save_tasas(usd=usd, eur=eur, fuente=fuente) or saved
    elif usd is not None or eur is not None:
        # Primera vez o sin cambios
        saved = save_tasas(usd=usd, eur=eur, fuente=fuente)

    # Preparar mensaje Telegram
    now_caracas = datetime.now(CARACAS_TZ).strftime("%Y-%m-%d %H:%M")
    lines = [f"📊 <b>Actualización Tasa BCV</b> ({now_caracas})"]

    # Indicar fuente
    if fuente == "open_er_api":
        lines.append("ℹ️ Fuente: open.er-api.com (fallback — R4 pendiente)")

    if usd is not None:
        change = ""
        if prev_usd and usd != prev_usd:
            diff = usd - prev_usd
            pct = (diff / prev_usd) * 100
            change = f" ({diff:+.2f} | {pct:+.1f}%)"
        lines.append(f"💵 USD/VES: <b>{usd:.2f}</b>{change}")

    if eur is not None:
        change = ""
        if prev_eur and eur != prev_eur:
            diff = eur - prev_eur
            pct = (diff / prev_eur) * 100
            change = f" ({diff:+.2f} | {pct:+.1f}%)"
        lines.append(f"💶 EUR/VES: <b>{eur:.2f}</b>{change}")

    if errors:
        lines.append(f"\n⚠️ Errores: {'; '.join(errors)}")

    if not usd and not eur:
        lines.append("❌ No se obtuvieron tasas")

    lines.append(f"\n💾 Guardado: {'Sí' if saved else 'No (sin cambios)'}")

    message = "\n".join(lines)
    await send_telegram(message)

    logger.info("=== Finalizado r4_update_tasa_bcv ===")

    if errors and not usd and not eur:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
