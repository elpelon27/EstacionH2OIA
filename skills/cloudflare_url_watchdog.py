#!/usr/bin/env python3
"""
 ============================================================================
 Cloudflare URL Watchdog — Detecta cambios de URL trycloudflare
 Estación H2O · Maracaibo, Venezuela
 ============================================================================

Problema: Cada reinicio del servidor (corte eléctrico) cambia la URL de
trycloudflare, rompiendo el webhook de Meta. Meta NO permite actualizar
webhook via API, solo manualmente via dashboard.

Solución: Este script monitorea la URL cada 5 min. Si cambia:
1. Registra en log del sistema
2. Guarda URL actual en /tmp/cloudflare_url_actual.txt
3. (Futuro) Avisa por Telegram cuando TELEGRAM_BOT_TOKEN esté configurado

Despliegue:
    systemd: cloudflare-watchdog.service
    Ejecuta cada 5 min via systemd timer
 """

import os
import re
import time
import logging
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("cloudflare_watchdog")

CARACAS_TZ = timezone(timedelta(hours=-4))

# Archivo centinela con la URL actual
URL_FILE = Path("/tmp/cloudflare_url_actual.txt")
LOG_FILE = Path("/mnt/ssd_trabajo/hermes-agent/logs/url_changes.log")

# Configuración Telegram (opcional, avisa si hay token)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "1663148211")


def get_current_cloudflare_url() -> str | None:
    """Obtiene la URL trycloudflare actual de los logs de systemd."""
    try:
        result = subprocess.run(
            [
                "sudo", "journalctl",
                "-u",
                "cloudflared-tunnel.service",
                "--since",
                "10 minutes ago",
                "--no-pager",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        # Buscar la última URL trycloudflare en los logs
        urls = re.findall(
            r"https://[a-z0-9-]+\.trycloudflare\.com", result.stdout
        )
        return urls[-1] if urls else None
    except Exception as e:
        logger.error("Error obteniendo URL de cloudflared: %s", e)
        return None


def get_stored_url() -> str | None:
    """Lee la URL guardada del archivo centinela."""
    try:
        if URL_FILE.exists():
            return URL_FILE.read_text().strip()
    except Exception:
        pass
    return None


def save_url(url: str) -> None:
    """Guarda la URL actual en el archivo centinela."""
    try:
        URL_FILE.parent.mkdir(parents=True, exist_ok=True)
        URL_FILE.write_text(url)
    except Exception as e:
        logger.error("Error guardando URL: %s", e)


def log_change(old_url: str | None, new_url: str) -> None:
    """Registra el cambio de URL en log persistente."""
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        now = datetime.now(CARACAS_TZ).strftime("%Y-%m-%d %H:%M:%S")
        with open(LOG_FILE, "a") as f:
            f.write(f"[{now}] CAMBIO DE URL\n")
            f.write(f"  URL vieja: {old_url or '(ninguna)'}\n")
            f.write(f"  URL nueva: {new_url}\n")
            f.write(f"  Acción requerida: actualizar Meta Dashboard\n")
            f.write(f"    https://developers.facebook.com/apps/975863248739508/whatsapp_business/wa_settings/\n")
            f.write(f"    Callback URL: {new_url}/webhook/meta\n")
            f.write(f"    Verify Token: a2ee0e434375cb232a99f10e4e1d210a\n\n")
    except Exception as e:
        logger.error("Error escribiendo log: %s", e)


def send_telegram_alert(old_url: str | None, new_url: str) -> bool:
    """Envía alerta por Telegram si hay token configurado."""
    if not TELEGRAM_BOT_TOKEN:
        return False
    try:
        import httpx

        message = (
            f"⚠️ <b>CAMBIO DE URL CLOUDFLARE</b>\n\n"
            f"La URL pública cambió (probable reinicio del servidor).\n\n"
            f"📍 URL vieja: <code>{old_url or '(ninguna)'}</code>\n"
            f"🆕 URL nueva: <code>{new_url}</code>\n\n"
            f"📋 <b>ACCIÓN REQUERIDA:</b>\n"
            f"1. Ve a Meta Dashboard\n"
            f"2. Webhook → Editar\n"
            f"3. Callback URL: <code>{new_url}/webhook/meta</code>\n"
            f"4. Verificar y guardar\n\n"
            f"⏰ {datetime.now(CARACAS_TZ).strftime('%Y-%m-%d %H:%M:%S')}"
        )
        with httpx.Client() as client:
            resp = client.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                json={
                    "chat_id": TELEGRAM_CHAT_ID,
                    "text": message,
                    "parse_mode": "HTML",
                },
                timeout=10,
            )
        return resp.status_code == 200
    except Exception as e:
        logger.error("Error enviando Telegram: %s", e)
        return False


def main():
    """Función principal — ejecutar cada 5 min via systemd timer."""
    logger.info("Watchdog ejecutándose...")

    current_url = get_current_cloudflare_url()
    if not current_url:
        logger.warning("No se pudo obtener URL de cloudflared (¿servicio caído?)")
        return

    stored_url = get_stored_url()

    if stored_url == current_url:
        logger.info("URL sin cambios: %s", current_url)
        return

    # ¡URL CAMBIÓ!
    logger.warning("🚨 CAMBIO DE URL DETECTADO")
    logger.warning("   Vieja: %s", stored_url or "(ninguna)")
    logger.warning("   Nueva: %s", current_url)

    log_change(stored_url, current_url)
    save_url(current_url)

    if send_telegram_alert(stored_url, current_url):
        logger.info("Alerta Telegram enviada")
    else:
        logger.warning("No se envió Telegram (sin token o error)")

    # Imprimir acción requerida para que systemd journal la capture
    print("=" * 60)
    print("🚨 ACCIÓN REQUERIDA — ACTUALIZAR META DASHBOARD")
    print("=" * 60)
    print(f"URL nueva: {current_url}")
    print(f"Callback URL: {current_url}/webhook/meta")
    print(f"Verify Token: a2ee0e434375cb232a99f10e4e1d210a")
    print(f"Ir a: https://developers.facebook.com/apps/975863248739508/whatsapp_business/wa_settings/")
    print("=" * 60)


if __name__ == "__main__":
    main()
