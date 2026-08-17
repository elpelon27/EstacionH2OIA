#!/usr/bin/env python3
"""
Boot Alert Script — Notifica por Telegram cuando el servidor reinicia.
Se ejecuta via systemd oneshot @reboot o cron @reboot.
"""

import json
import os
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any

# Cargar configuración desde variables de entorno o archivo
CONFIG_PATH = Path("/mnt/ssd_trabajo/hermes-agent/config/boot_alert.json")


def load_config() -> dict[str, Any]:
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    # Fallback a variables de entorno
    return {
        "bot_token": os.getenv("TELEGRAM_BOOT_BOT_TOKEN"),
        "chat_id": os.getenv("TELEGRAM_BOOT_CHAT_ID"),
    }


def get_uptime() -> float | None:
    try:
        with open("/proc/uptime") as f:
            secs = float(f.read().split()[0])
        return secs
    except Exception:
        return None


def get_boot_time() -> str:
    try:
        out = subprocess.check_output(["who", "-b"], text=True).strip()
        return out.replace("system boot", "").strip()
    except Exception:
        return "desconocido"


def get_last_boot_info() -> str:
    """Obtiene info del boot anterior desde journalctl."""
    try:
        out = subprocess.check_output(
            ["journalctl", "--list-boots", "--no-pager"], text=True, stderr=subprocess.DEVNULL
        )
        lines = out.strip().split("\n")
        if len(lines) >= 2:
            # La línea -1 es el boot anterior
            return lines[-2].strip()
    except Exception:
        pass
    return "no disponible"


def get_public_ip() -> str:
    try:
        out = subprocess.check_output(
            ["curl", "-s", "--max-time", "5", "https://api.ipify.org"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
        return out.strip()
    except Exception:
        return "no disponible"


def send_telegram(config: dict[str, Any], message: str) -> bool:
    """Envía mensaje via Telegram Bot API."""
    if not config.get("bot_token") or not config.get("chat_id"):
        print("Config incompleta: falta bot_token o chat_id", file=sys.stderr)
        return False

    url = f"https://api.telegram.org/bot{config['bot_token']}/sendMessage"
    payload = {"chat_id": config["chat_id"], "text": message, "parse_mode": "HTML"}
    try:
        import urllib.parse
        import urllib.request

        data = urllib.parse.urlencode(payload).encode()
        req = urllib.request.Request(url, data=data)
        with urllib.request.urlopen(req, timeout=10) as resp:
            return bool(resp.status == 200)
    except Exception as e:
        print(f"Error enviando Telegram: {e}", file=sys.stderr)
        return False


def main() -> int:
    config = load_config()

    hostname = socket.gethostname()
    boot_time = get_boot_time()
    uptime = get_uptime()
    last_boot = get_last_boot_info()
    public_ip = get_public_ip()

    # Servicios críticos a verificar
    critical_services = ["valentina-bridge", "dispatcher-bot", "telegram-bot", "cloudflared"]

    service_status = []
    for svc in critical_services:
        try:
            out = subprocess.check_output(
                ["systemctl", "is-active", svc], text=True, stderr=subprocess.DEVNULL
            ).strip()
            status = "✅" if out == "active" else f"❌ ({out})"
        except Exception:
            status = "❓ (no instalado)"
        service_status.append(f"  {svc}: {status}")

    msg = (
        f"🔄 <b>REINICIO DETECTADO</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🖥 <b>Host:</b> {hostname}\n"
        f"🌐 <b>IP pública:</b> {public_ip}\n"
        f"⏰ <b>Boot actual:</b> {boot_time}\n"
        f"⏱ <b>Uptime:</b> {uptime:.0f}s\n"
        f"📜 <b>Boot anterior:</b> {last_boot}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"<b>Servicios críticos:</b>\n" + "\n".join(service_status)
    )

    if send_telegram(config, msg):
        print("✅ Alerta de boot enviada")
        return 0
    else:
        print("❌ Falló envío de alerta", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
