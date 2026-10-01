#!/usr/bin/env bash
# =============================================================================
# Chequeo de seguridad + configuración empresarial del celular del chofer
# =============================================================================
# Uso:  ./scripts/harden_phone.sh <serial> <vehicle_id>
#   ./scripts/harden_phone.sh SP6300000000016611 1   # Yordanis
#   ./scripts/harden_phone.sh <serial>           2   # Evert
#
# RESTRICCIÓN DE LA DIRECTIVA: NO instalar apps.
# WhatsApp, Telegram y Chrome ya están instalados y operativos según el Líder.
# Este script solo VERIFICA que sigan activos; nunca hace install.
#
# Requiere: adb devices debe listar el equipo como "device" (no unauthorized).
# =============================================================================
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ -f "$REPO_ROOT/config/.env" ]]; then
    set -a; # shellcheck disable=SC1091
    . "$REPO_ROOT/config/.env"
    set +a
fi

SERIAL="${1:?Uso: $0 <serial> <vehicle_id>}"
VEHICLE_ID="${2:?Uso: $0 <serial> <vehicle_id>  (1=Yordanis, 2=Evert)}"
TELEGRAM_BOT_TOKEN="${TELEGRAM_BOT_TOKEN:-}"
TELEGRAM_CHAT_ID="${TELEGRAM_CHAT_ID:-1663148211}"

case "$VEHICLE_ID" in
    1) CHOFER="YORDANIS"; VEHICULO="Triciclo 1"; WA="584222560722"; SESSION="chofer_1" ;;
    2) CHOFER="EVERT";    VEHICULO="Triciclo 2"; WA="584222560723"; SESSION="chofer_2" ;;
    *) CHOFER="DESCONOCIDO"; VEHICULO="?"; WA="?"; SESSION="?" ;;
esac

# Apps a bloquear (solo disable-user: NO desinstala, reversible)
BLOCK_LIST=(
    com.facebook.katana
    com.instagram.android
    com.tiktok.android
)

# Apps que DEBEN estar activas (solo verificación, nunca install)
REQUIRED_LIST=(
    com.whatsapp
    org.telegram.messenger
    com.android.chrome
)

adb_shell() { timeout 25 adb -s "$SERIAL" shell "$@" 2>/dev/null | tr -d '\r'; }

notify() {
    [[ -z "$TELEGRAM_BOT_TOKEN" ]] && { echo "AVISO: $1"; return; }
    curl -sS -m 30 "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
        --data-urlencode "chat_id=${TELEGRAM_CHAT_ID}" \
        --data-urlencode "text=$1" -o /dev/null || echo "fallo telegram"
}

echo "=== Endureciendo $SERIAL → $CHOFER ($VEHICULO) ==="
echo "    (NO se instala ninguna app por directiva del Líder)"

# --- 1. Verificar autorización ---
state=$(timeout 20 adb devices 2>/dev/null | awk -v s="$SERIAL" '$1==s {print $2}')
case "$state" in
    "")
        echo "❌ $SERIAL no aparece en adb devices"; exit 1 ;;
    unauthorized)
        echo "⚠️  $SERIAL unauthorized: aceptá el diálogo en el celular"; exit 1 ;;
    device)
        echo "  ✓ ADB autorizado" ;;
    *)
        echo "❌ Estado inesperado: $state"; exit 1 ;;
esac

modelo=$(adb_shell getprop ro.product.model)
android=$(adb_shell getprop ro.build.version.release)
echo "  ✓ Equipo: $modelo (Android $android)"

# --- 2a. Bloquear apps innecesarias ---
echo "--- Bloqueo de apps ---"
bloqueadas=(); no_presentes=()
for pkg in "${BLOCK_LIST[@]}"; do
    if adb_shell pm list packages "$pkg" | grep -q "$pkg"; then
        adb_shell pm disable-user --user 0 "$pkg" >/dev/null 2>&1
        nuevo=$(adb_shell pm list packages -d "$pkg" | grep -q "$pkg" && echo disabled || echo ACTIVA)
        if [[ "$nuevo" == "disabled" ]]; then
            bloqueadas+=("$pkg"); echo "  🔒 BLOQUEADA: $pkg"
        else
            echo "  ⚠️  no se pudo bloquear: $pkg"
        fi
    else
        no_presentes+=("$pkg"); echo "  · no instalada (nada que bloquear): $pkg"
    fi
done

# --- 2b. GPS alta precisión (location_mode 3) ---
echo "--- GPS ---"
adb_shell settings put secure location_mode 3 >/dev/null 2>&1
adb_shell settings put location location_mode 3 >/dev/null 2>&1
lm=$(adb_shell settings get secure location_mode)
echo "  ✓ location_mode = $lm  (3 = alta precisión)"

# --- 2c. Pantalla ---
echo "--- Pantalla ---"
adb_shell settings put system screen_brightness 255 >/dev/null 2>&1
adb_shell settings put system screen_off_timeout 600000 >/dev/null 2>&1
brillo=$(adb_shell settings get system screen_brightness)
timeout_s=$(adb_shell settings get system screen_off_timeout)
echo "  ✓ brillo = $brillo"
echo "  ✓ apagado = ${timeout_s} ms ($((timeout_s / 60000)) min)"

# --- 2d. Verificar apps requeridas (SOLO verificar) ---
echo "--- Apps requeridas (verificación, sin instalar) ---"
activas=(); faltantes=()
for pkg in "${REQUIRED_LIST[@]}"; do
    if adb_shell pm list packages "$pkg" | grep -q "$pkg"; then
        estado=$(adb_shell pm list packages -d "$pkg" | grep -q "$pkg" && echo BLOQUEADA || echo activa)
        if [[ "$estado" == "activa" ]]; then
            activas+=("$pkg"); echo "  ✅ $pkg ($estado)"
        else
            faltantes+=("$pkg (BLOQUEADA)"); echo "  ⚠️  $pkg está BLOQUEADA"
        fi
    else
        faltantes+=("$pkg"); echo "  ❌ $pkg NO instalada"
    fi
done

# --- Verificar sesión WAHA de este chofer ---
waha="?"
if [[ -n "${WAHA_API_KEY:-}" ]]; then
    waha=$(curl -sS -m 15 "http://127.0.0.1:3000/api/sessions/${SESSION}" \
        -H "X-Api-Key: ${WAHA_API_KEY}" 2>/dev/null | python3 -c 'import sys,json
try:
    d=json.load(sys.stdin); print(d.get("status","?"), (d.get("me") or {}).get("id","").split("@")[0])
except Exception: print("?")' 2>/dev/null || echo "?")
    echo "  ✓ Sesión WAHA $SESSION: $waha"
fi

# --- Reporte ---
report="🔒 ENDURECIMIENTO — ${CHOFER} (${VEHICULO})

Equipo: ${modelo} · Android ${android} · ${SERIAL}

BLOQUEADAS (${#bloqueadas[@]}):
$([ ${#bloqueadas[@]} -eq 0 ] && echo "  ninguna" || printf '  🔒 %s\n' "${bloqueadas[@]}")

No instaladas (${#no_presentes[@]}): $(echo "${no_presentes[*]:-ninguna}")

CONFIGURADO:
· GPS alta precisión (location_mode=3)
· Brillo ${brillo}
· Apagado de pantalla $((timeout_s / 60000)) min

APPS REQUERIDAS — activas (${#activas[@]}): $(echo "${activas[*]:-NINGUNA}")
Con problema (${#faltantes[@]}): $(echo "${faltantes[*]:-ninguna}")

Sesión WAHA ${SESSION}: ${waha}
NO se instaló ninguna app (por directiva)."

notify "$report"
echo
echo "$report"
