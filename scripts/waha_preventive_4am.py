#!/usr/bin/env python3
"""Mantenimiento preventivo WAHA — diario 4 AM.

  1. Backup de /app/.sessions/webjs (docker cp) a /mnt/ssd_trabajo/backups/
  2. docker restart waha (limpia crashes de Puppeteer acumulados)
  3. POST /start en ambas sesiones + verificación WORKING y número correcto

Silencioso si todo sale bien (stdout vacío = nada se envía).
Retiene los últimos 14 backups; borra los más viejos.
"""
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from datetime import datetime

BASE = "http://127.0.0.1:3000"
SESSIONS = {
    "chofer_1": "584222560722@c.us",
    "chofer_2": "584222560723@c.us",
}
ENV_FILE = "/mnt/ssd_trabajo/hermes-agent/config/.env"
BACKUP_ROOT = "/mnt/ssd_trabajo/backups"
KEEP = 14

API_KEY = None
for line in open(ENV_FILE):
    line = line.strip()
    if line.startswith("WAHA_API_KEY=") and not line.startswith("#"):
        API_KEY = line.split("=", 1)[1].strip().strip('"').strip("'")
if not API_KEY:
    print("FATAL: no pude leer WAHA_API_KEY de config/.env")
    sys.exit(1)

msgs = []
fatal = False

# --- 1. Backup previo (OBLIGATORIO antes de tocar el contenedor) ---
stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
bk_dir = os.path.join(BACKUP_ROOT, "waha_webjs_%s" % stamp)
r = subprocess.run(["docker", "cp", "waha:/app/.sessions/webjs",
                    bk_dir + "/"], capture_output=True, timeout=120)
if r.returncode != 0:
    # sin backup no se toca el contenedor
    print("🚨 WAHA preventivo: FALLÓ el backup (docker cp) — NO reinicio el "
          "contenedor por seguridad. Salida: %s" % r.stderr.decode()[:300])
    sys.exit(1)

# retención: borrar los waha_webjs_* más viejos que los últimos KEEP
try:
    backups = sorted(d for d in os.listdir(BACKUP_ROOT)
                     if d.startswith("waha_webjs_"))
    for old in backups[:-KEEP]:
        shutil.rmtree(os.path.join(BACKUP_ROOT, old), ignore_errors=True)
except Exception:
    pass  # retención es best-effort, nunca bloquea

# --- 2. docker restart ---
r = subprocess.run(["docker", "restart", "waha"], capture_output=True,
                   timeout=180)
if r.returncode != 0:
    print("🚨 WAHA preventivo: docker restart falló: %s"
          % r.stderr.decode()[:300])
    sys.exit(1)

# --- 3. start + verificación ---


def api(method, path):
    req = urllib.request.Request(BASE + path, method=method,
                                 headers={"X-Api-Key": API_KEY,
                                          "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()
    except Exception as e:
        return 0, str(e)


time.sleep(30)
for s in SESSIONS:
    api("POST", "/api/sessions/%s/start" % s)
time.sleep(25)

for s, expected in SESSIONS.items():
    code, body = api("GET", "/api/sessions/" + s)
    try:
        d = json.loads(body)
        st, me = d.get("status", ""), (d.get("me") or {}).get("id", "")
    except Exception:
        st, me = "UNREACHABLE", ""
    if st == "WORKING" and me == expected:
        continue  # sano, silencioso
    fatal = True
    msgs.append("🚨 WAHA preventivo 4AM: %s no quedó WORKING tras el reinicio "
                "(estado=%s, me=%s). El watchdog de 7 min seguirá intentando; "
                "si persiste, re-vincular: ./scripts/waha_link_device.sh %s %s"
                % (s, st or "?", me or "sin número", s, expected.replace("@c.us", "")))

if fatal:
    print("\n".join(msgs))
sys.exit(1 if fatal else 0)
