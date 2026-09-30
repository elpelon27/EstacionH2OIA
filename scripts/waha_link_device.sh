#!/usr/bin/env bash
# =============================================================================
# Vinculación de números de WhatsApp de choferes vía WAHA (WhatsApp HTTP API)
# =============================================================================
# Endpoints VERIFICADOS contra WAHA 2026.9.1 (engine WEBJS, tier CORE) el
# 2026-09-30. Difieren del plan original:
#   - QR real:  GET /api/{session}/auth/qr          -> image/png directa
#   - (NO existe /api/sessions/{session}/qr  -> 404 verificado)
#   - Ciclo:    POST /api/sessions -> POST /api/sessions/{n}/start -> QR
#   - Estado:   GET  /api/sessions/{n}   status=WORKING cuando escanea
#
# Uso:  ./scripts/waha_link_device.sh chofer_1
# =============================================================================
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# --- Cargar config/.env ---
if [[ -f "$REPO_ROOT/config/.env" ]]; then
    set -a; # shellcheck disable=SC1091
    . "$REPO_ROOT/config/.env"
    set +a
fi

WAHA_BASE_URL="${WAHA_BASE_URL:-http://127.0.0.1:3000}"
WAHA_API_KEY="${WAHA_API_KEY:?Falta WAHA_API_KEY (config/.env)}"
# @Skynet_27_bot verificado via getMe -> username Skynet_27_bot
TELEGRAM_BOT_TOKEN="${TELEGRAM_BOT_TOKEN:?Falta TELEGRAM_BOT_TOKEN (config/.env)}"
TELEGRAM_CHAT_ID="${TELEGRAM_CHAT_ID:-1663148211}"

SESSION_NAME="${1:?Uso: $0 <session_name>  (ej. chofer_1)}"
LABEL="${2:-$SESSION_NAME}"
QR_TIMEOUT_S="${QR_TIMEOUT_S:-300}"   # 5 minutos por defecto
POLL_INTERVAL_S="${POLL_INTERVAL_S:-5}"

QR_DIR="/tmp/waha_qr"
mkdir -p "$QR_DIR"
QR_FILE="$QR_DIR/waha_qr_${SESSION_NAME}.png"

api() {  # api <METHOD> <path> [data]
    local method="$1" path="$2" data="${3:-}"
    local args=(-sS -m 60 -X "$method" "${WAHA_BASE_URL}${path}" -H "X-Api-Key: ${WAHA_API_KEY}" -w '\n%{http_code}')
    [[ -n "$data" ]] && args+=(-H "Content-Type: application/json" -d "$data")
    curl "${args[@]}"
}

notify() {  # notify <texto>
    curl -sS -m 30 "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
        --data-urlencode "chat_id=${TELEGRAM_CHAT_ID}" \
        --data-urlencode "text=$1" \
        -o /dev/null -w "telegram_msg=%{http_code}\n" || echo "telegram_msg=FALLÓ"
}

send_qr() {  # send_qr <caption>
    local caption="$1"
    curl -sS -m 60 "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendPhoto" \
        -F "chat_id=${TELEGRAM_CHAT_ID}" \
        -F "photo=@${QR_FILE}" \
        -F "caption=${caption}" \
        -o /dev/null -w "telegram_photo=%{http_code}\n" || echo "telegram_photo=FALLÓ"
}

STATUS="$(api GET "/api/sessions/${SESSION_NAME}" | tail -1)"
existing=$(curl -sS -m 20 "${WAHA_BASE_URL}/api/sessions/${SESSION_NAME}" -H "X-Api-Key: ${WAHA_API_KEY}")

echo "==> [$SESSION_NAME] Endpoint WAHA reachable"

# --- 1. Crear sesión (idempotente: 200 si ya existe o 201 si nueva) ---
if [[ "$STATUS" == "200" ]]; then
    echo "    Sesión ya existe (reutilizando)"
else
    out=$(api POST "/api/sessions" "{\"name\":\"${SESSION_NAME}\"}")
    code=$(echo "$out" | tail -1)
    if [[ "$code" != "201" ]]; then
        notify "❌ No pude crear la sesión WAHA '${SESSION_NAME}' (HTTP $code). Verificá que WAHA esté arriba."
        exit 1
    fi
    echo "    Sesión creada (201)"
fi

cur_status=$(echo "$existing" | python3 -c 'import sys,json
try: print(json.load(sys.stdin).get("status",""))
except Exception: print("")' 2>/dev/null || echo "")

if [[ "$cur_status" == "WORKING" ]]; then
    notify "ℹ️ ${LABEL}: el número ya está vinculado (WORKING). No hay que escanear nada."
    echo "==> [$SESSION_NAME] YA VINCULADA — nada que hacer"
    exit 0
fi

# --- 2. Iniciar sesión (necesario: en STOPPED el QR da 422 verificado) ---
out=$(api POST "/api/sessions/${SESSION_NAME}/start")
code=$(echo "$out" | tail -1)
echo "    Start -> HTTP $code"
[[ "$code" != "201" ]] && echo "    (continuando; puede ya estar STARTING)"

# --- 3. Obtener QR (PNG binario directo, no base64 — verificado 2026-09-30) ---
echo "    Esperando a que el motor genere el QR..."
qr_code=0
for attempt in $(seq 1 12); do
    qr_code=$(curl -sS -m 45 -o "$QR_FILE" \
        -w '%{http_code}' \
        "${WAHA_BASE_URL}/api/${SESSION_NAME}/auth/qr" \
        -H "X-Api-Key: ${WAHA_API_KEY}" || echo 000)
    [[ "$qr_code" == "200" ]] && break
    sleep 5
done

if [[ "$qr_code" != "200" ]]; then
    notify "❌ ${LABEL}: WAHA no devolvió QR (HTTP ${qr_code}). Revisá el contenedor 'waha'."
    exit 1
fi

size=$(stat -c%s "$QR_FILE" 2>/dev/null || echo 0)
echo "    QR obtenido: ${QR_FILE} (${size} bytes, image/png)"

# --- 4. Enviar QR al Líder (@Skynet_27_bot, chat 1663148211 verificado) ---
send_qr "📱 Escaneá este QR con el WhatsApp del ${LABEL}: WhatsApp → Dispositivos vinculados → Escanear QR
🕐 Tengo ${QR_TIMEOUT_S}s de espera."

# --- 5. Polling hasta WORKING ---
echo "    Polling cada ${POLL_INTERVAL_S}s por hasta ${QR_TIMEOUT_S}s..."
elapsed=0
while [[ $elapsed -lt $QR_TIMEOUT_S ]]; do
    st=$(curl -sS -m 20 "${WAHA_BASE_URL}/api/sessions/${SESSION_NAME}" \
         -H "X-Api-Key: ${WAHA_API_KEY}" | python3 -c 'import sys,json
try: print(json.load(sys.stdin).get("status",""))
except Exception: print("")' 2>/dev/null || echo "")

    case "$st" in
        WORKING)
            notify "✅ ${LABEL} vinculado OK — sesión '${SESSION_NAME}' en estado WORKING."
            echo "==> ✅ [$SESSION_NAME] VINCULADO OK"
            rm -f "$QR_FILE"
            exit 0
            ;;
        FAILED)
            notify "❌ ${LABEL}: sesión FAILED. Pará el contenedor y reintentá: docker restart waha"
            exit 1
            ;;
    esac
    sleep "$POLL_INTERVAL_S"
    elapsed=$((elapsed + POLL_INTERVAL_S))
    printf "\r      [%3ds/%3ds] estado=%s" "$elapsed" "$QR_TIMEOUT_S" "${st:-?}"
done
echo ""

elapsed_min=$((QR_TIMEOUT_S / 60))
notify "⏱️ Timeout: ${LABEL} no escaneó el QR en ${elapsed_min} minutos. Reintentá con:
./scripts/waha_link_device.sh ${SESSION_NAME}"
echo "==> ⏱️  Timeout [$SESSION_NAME] sin escanear"
exit 2
