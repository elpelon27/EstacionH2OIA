#!/usr/bin/env bash
# =============================================================================
# WAHA health check + auto-reconexión
# =============================================================================
# Corre por cron cada 15 minutos. Objetivo: que una sesión caída se recupere
# sola y, si no puede, avisar al Líder por Telegram (@Skynet_27_bot).
#
# Lógica:
#   1. Verificar que el contenedor esté arriba. Si no, intentar levantarlo.
#   2. Para cada sesión esperada (chofer_1, chofer_2):
#        - WORKING            -> OK, no hacer nada (silencioso)
#        - SCAN_QR_CODE etc.  -> POST /start y re-verificar
#        - Sigue caída        -> alerta a Telegram (una sola vez por caída)
#   3. Verificar que el número vinculado sea el correcto (regla crítica).
#
# El "una sola vez por caída" se logra con un flag en /tmp que se borra cuando
# la sesión vuelve a WORKING, para no spamnear cada 15 min.
# =============================================================================
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ -f "$REPO_ROOT/config/.env" ]]; then
    set -a; # shellcheck disable=SC1091
    . "$REPO_ROOT/config/.env"
    set +a
fi

WAHA_BASE_URL="${WAHA_BASE_URL:-http://127.0.0.1:3000}"
WAHA_API_KEY="${WAHA_API_KEY:-}"
TELEGRAM_BOT_TOKEN="${TELEGRAM_BOT_TOKEN:-}"
TELEGRAM_CHAT_ID="${TELEGRAM_CHAT_ID:-1663148211}"

# sesión=número esperado (regla crítica del Líder)
EXPECTED_1="chofer_1:584222560722"
EXPECTED_2="chofer_2:584222560723"
SESSIONS=("$EXPECTED_1" "$EXPECTED_2")

STATE_DIR="/tmp/waha_health"
mkdir -p "$STATE_DIR"

notify() {
    local text="$1"
    [[ -z "$TELEGRAM_BOT_TOKEN" ]] && { echo "SIN_TOKEN: $text"; return; }
    curl -sS -m 30 "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
        --data-urlencode "chat_id=${TELEGRAM_CHAT_ID}" \
        --data-urlencode "text=${text}" \
        -o /dev/null -w "" || echo "fallo telegram"
}

api_get() { curl -sS -m 15 "$1" -H "X-Api-Key: ${WAHA_API_KEY}" 2>/dev/null || echo ""; }
api_post() { curl -sS -m 30 -X POST "$1" -H "X-Api-Key: ${WAHA_API_KEY}" 2>/dev/null || echo ""; }

if [[ -z "$WAHA_API_KEY" ]]; then
    echo "FATAL: falta WAHA_API_KEY"
    exit 1
fi

# --- 1. Contenedor arriba? ---
if ! api_get "${WAHA_BASE_URL}/api/version" | grep -q "version"; then
    echo "WAHA no responde — intentando levantar compose"
    if [[ -d "$REPO_ROOT/infra/waha" ]]; then
        (cd "$REPO_ROOT/infra/waha" && timeout 120 docker compose up -d >/dev/null 2>&1)
        sleep 60
    fi
    if ! api_get "${WAHA_BASE_URL}/api/version" | grep -q "version"; then
        notify "🚨 WAHA CAÍDO y no pude revivirlo.

El servicio de WhatsApp de los choferes no responde.
Revisá el servidor: cd infra/waha && docker compose up -d"
        echo "FATAL: WAHA irrecuperable"
        exit 1
    fi
    notify "♻️ WAHA estaba caído y lo reinicié automáticamente. Verificando sesiones..."
fi

OVERALL=0

# --- 2. Cada sesión ---
for entry in "${SESSIONS[@]}"; do
    name="${entry%%:*}"
    expected="${entry##*:}"
    flag="$STATE_DIR/${name}.alerted"

    raw=$(api_get "${WAHA_BASE_URL}/api/sessions/${name}")
    read -r status me <<<"$(echo "$raw" | python3 -c 'import sys,json
try:
    d=json.load(sys.stdin)
    print(d.get("status","MISSING"), (d.get("me") or {}).get("id","").split("@")[0])
except Exception:
    print("MISSING","")' 2>/dev/null)"

    if [[ "$status" == "WORKING" ]]; then
        # Verificación de identidad (regla crítica)
        if [[ -n "$me" && "$me" != "$expected" ]]; then
            notify "🚨 ${name} está WORKING pero con el número EQUIVOCADO.
Esperado: +${expected}  |  Vinculado: +${me}
El cliente recibiría mensajes del chofer incorrecto. Revisá YA."
            OVERALL=1
        else
            echo "OK   ${name} WORKING (+${me})"
            rm -f "$flag"   # recuperada => limpiar flag de alerta
        fi
        continue
    fi

    echo "CAÍDA ${name} status=${status} — intentando reconectar"
    api_post "${WAHA_BASE_URL}/api/sessions/${name}/start" >/dev/null 2>&1
    sleep 25

    raw2=$(api_get "${WAHA_BASE_URL}/api/sessions/${name}")
    status2=$(echo "$raw2" | python3 -c 'import sys,json
try: print(json.load(sys.stdin).get("status","MISSING"))
except Exception: print("MISSING")' 2>/dev/null)

    if [[ "$status2" == "WORKING" ]]; then
        me2=$(echo "$raw2" | python3 -c 'import sys,json
try: print((json.load(sys.stdin).get("me") or {}).get("id","").split("@")[0])
except Exception: print("")' 2>/dev/null)
        notify "♻️ ${name} se reconectó solo (estaba ${status}, ahora WORKING +${me2})."
        rm -f "$flag"
        echo "RECUPERADA ${name}"
    else
        OVERALL=1
        if [[ ! -f "$flag" ]]; then
            notify "🚨 ${name} NO está vinculado (estado: ${status2}).

Intenté reconectar y no pude. Hay que re-vincular el número +${expected}:
  ./scripts/waha_link_device.sh ${name} ${expected}
(Eso manda un código de emparejamiento a este chat.)

No aviso de nuevo hasta que se recupere."
            touch "$flag"
        fi
        echo "FALLO ${name} sigue ${status2}"
    fi
done

exit "$OVERALL"
