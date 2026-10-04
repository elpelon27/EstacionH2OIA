#!/usr/bin/env python3
"""Watchdog WAHA chofer_1 + chofer_2 — auto-reconexión con alerta única.

Silencioso cuando todo está OK (stdout vacío = no se envía nada).
Imprime solo cuando: recupera una sesión caída, o no logra recuperar.

Lógica (skill waha-vinculacion-y-rotacion):
  1. GET /api/sessions/{n} -> status WORKING + me.id == número esperado
  2. Si caída: POST /start -> re-verificar
  3. Si recae: docker restart waha -> start -> re-verificar
  4. Verificación crítica de número (consistencia por entrega)
  5. Flag /tmp/waha_wd_incident_{n}: alerta UNA sola vez por incidente
     (se borra al recuperar — evita spam cada tick).

El docker restart es compartido: si AMBAS están caídas, se hace UN solo
restart (no dos seguidos).
"""
import json
import os
import subprocess
import sys
import time
import urllib.request

BASE = "http://127.0.0.1:3000"
SESSIONS = {
    "chofer_1": "584222560722@c.us",
    "chofer_2": "584222560723@c.us",
}
ENV_FILE = "/mnt/ssd_trabajo/hermes-agent/config/.env"

API_KEY = None
for line in open(ENV_FILE):
    line = line.strip()
    if line.startswith("WAHA_API_KEY=") and not line.startswith("#"):
        API_KEY = line.split("=", 1)[1].strip().strip('"').strip("'")
if not API_KEY:
    print("FATAL: no pude leer WAHA_API_KEY de config/.env")
    sys.exit(1)


def api(method, path):
    req = urllib.request.Request(BASE + path, method=method,
                                 headers={"X-Api-Key": API_KEY,
                                          "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()
    except Exception as e:
        return 0, str(e)


def status(session):
    code, body = api("GET", "/api/sessions/" + session)
    try:
        d = json.loads(body)
        return d.get("status", ""), (d.get("me") or {}).get("id", "")
    except Exception:
        return "UNREACHABLE", ""


def ok(session, st, me):
    return st == "WORKING" and me == SESSIONS[session]


def flag_path(session):
    return "/tmp/waha_wd_incident_" + session


msgs = []          # mensajes a reportar (salida no vacía = se entrega)
any_failed = False

# --- 1. Diagnóstico inicial ---
down = {}          # session -> (st, me)
for s in SESSIONS:
    st, me = status(s)
    if ok(s, st, me):
        if os.path.exists(flag_path(s)):
            os.remove(flag_path(s))  # incidente cerrado, permitir futuras alertas
    else:
        down[s] = (st, me)

if not down:
    sys.exit(0)  # todo sano: silencio total

# --- 2. Primer escalón: POST /start en cada caída ---
for s in down:
    api("POST", "/api/sessions/%s/start" % s)
time.sleep(20)

still_down = {}
for s in down:
    st, me = status(s)
    if ok(s, st, me):
        if not os.path.exists(flag_path(s)):
            open(flag_path(s), "w").write("recovered\n")
            msgs.append("🛠️ WAHA watchdog: %s estaba caída y la recuperé vía "
                        "POST /start. Verificado WORKING con el número "
                        "correcto (%s)." % (s, me))
    else:
        still_down[s] = (st, me)

# --- 3. Segundo escalón: docker restart + start (UNO solo si ambas caídas) ---
if still_down:
    subprocess.run(["docker", "restart", "waha"], check=False,
                   capture_output=True, timeout=120)
    time.sleep(30)
    for s in still_down:
        api("POST", "/api/sessions/%s/start" % s)
    time.sleep(25)

    for s, _ in still_down.items():
        st, me = status(s)
        if ok(s, st, me):
            if not os.path.exists(flag_path(s)):
                open(flag_path(s), "w").write("recovered\n")
                msgs.append("🛠️ WAHA watchdog: %s recuperada vía docker "
                            "restart + start. WORKING con el número "
                            "correcto (%s)." % (s, me))
        else:
            any_failed = True
            if not os.path.exists(flag_path(s)):
                open(flag_path(s), "w").write("failed\n")
                msgs.append(
                    "🚨 WAHA watchdog: %s sigue caída (estado=%s, me=%s) tras "
                    "start y docker restart. Requiere intervención manual. "
                    "Re-vincular si es necesario:\n"
                    "./scripts/waha_link_device.sh %s %s"
                    % (s, st or "?", me or "sin número", s,
                       SESSIONS[s].replace("@c.us", "")))

# --- Verificación anti-número-equivocado en sesiones WORKING ---
for s in SESSIONS:
    st, me = status(s)
    if st == "WORKING" and me and me != SESSIONS[s]:
        any_failed = True
        if not os.path.exists(flag_path(s)):
            open(flag_path(s), "w").write("wrong_number\n")
            msgs.append("🚨 %s: sesión WORKING pero con el número EQUIVOCADO. "
                        "Esperado: %s | Vinculado: %s. Consistencia por "
                        "entura rota — revisar antes de operar."
                        % (s, SESSIONS[s], me))

if msgs:
    print("\n".join(msgs))
sys.exit(1 if any_failed else 0)
