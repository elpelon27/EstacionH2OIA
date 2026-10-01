#!/usr/bin/env bash
# =============================================================================
# Configuración automática del celular de un chofer vía ADB
# =============================================================================
# Uso:  ./scripts/setup_phone_auto.sh <serial> <vehicle_id>
#   ./scripts/setup_phone_auto.sh ABC123 1   # Yordanis (Triciclo 1)
#   ./scripts/setup_phone_auto.sh ABC123 2   # Evert    (Triciclo 2)
#
# Requiere: celular conectado por USB con depuración USB activada y el
# diálogo "Permitir depuración USB" aceptado (adb devices debe decir "device",
# no "unauthorized").
#
# NO instala apps de terceros sin verificar; reporta todo por Telegram.
# =============================================================================
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ -f "$REPO_ROOT/config/.env" ]]; then
    set -a; # shellcheck disable=SC1091
    . "$REPO_ROOT/config/.env"
    set +a
fi

SERIAL="${1:?Uso: $0 <serial> <vehicle_id>}"
VEHICLE_ID="${2:?Uso: $0 <serial> <vehicle_id>   (1=Yordanis, 2=Evert)}"

TELEGRAM_BOT_TOKEN="${TELEGRAM_BOT_TOKEN:-}"
TELEGRAM_CHAT_ID="${TELEGRAM_CHAT_ID:-1663148211}"

case "$VEHICLE_ID" in
    1) CHOFER="YORDANIS"; VEHICULO="Triciclo 1"; WA="584222560722"; SESSION="chofer_1" ;;
    2) CHOFER="EVERT";    VEHICULO="Triciclo 2"; WA="584222560723"; SESSION="chofer_2" ;;
    *) CHOFER="DESCONOCIDO"; VEHICULO="?"; WA="?"; SESSION="?" ;;
esac

notify() {
    [[ -z "$TELEGRAM_BOT_TOKEN" ]] && { echo "AVISO: $1"; return; }
    curl -sS -m 30 "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
        --data-urlencode "chat_id=${TELEGRAM_CHAT_ID}" \
        --data-urlencode "text=$1" -o /dev/null || echo "fallo telegram"
}

adb_shell() { timeout 25 adb -s "$SERIAL" shell "$@" 2>/dev/null | tr -d '\r'; }

echo "=== Configurando equipo $SERIAL → $CHOFER ($VEHICULO) ==="

# --- 1. Verificar que ADB lo vea y esté autorizado ---
state=$(timeout 20 adb devices 2>/dev/null | awk -v s="$SERIAL" '$1==s {print $2}')
if [[ -z "$state" ]]; then
    msg="❌ El equipo $SERIAL no aparece en adb devices.

Conectá el celular por USB, activá Depuración USB y aceptá el diálogo
'Permitir depuración USB' en la pantalla del celular."
    echo "$msg"; notify "$msg"; exit 1
fi
if [[ "$state" == "unauthorized" ]]; then
    msg="⚠️ El equipo $SERIAL está 'unauthorized'.

En el celular aparece un diálogo '¿Permitir depuración USB?'.
Marca 'Permitir siempre desde este equipo' y aceptá."
    echo "$msg"; notify "$msg"; exit 1
fi
if [[ "$state" != "device" ]]; then
    msg="❌ Equipo $SERIAL en estado inesperado: $state"
    echo "$msg"; notify "$msg"; exit 1
fi
echo "  ✓ ADB estado: $state"

# --- 2. Identificar el equipo ---
modelo=$(adb_shell getprop ro.product.model)
android=$(adb_shell getprop ro.build.version.release)
fabricante=$(adb_shell getprop ro.product.manufacturer)
echo "  ✓ Equipo: $fabricante $modelo (Android $android)"

# --- 3. Pantalla encendida mientras carga (crítico en ruta) ---
adb_shell settings put global stay_on_while_plugged_in 3
adb_shell settings put system screen_off_timeout 600000   # 10 min
echo "  ✓ Pantalla: se mantiene encendida mientras carga"

# --- 4. Brillo alto para visibilidad en exteriores ---
adb_shell settings put system screen_brightness 200
echo "  ✓ Brillo ajustado"

# --- 5. Verificar WhatsApp instalado ---
wa=$(adb_shell pm list packages com.whatsapp)
if [[ -n "$wa" ]]; then
    wa_ver=$(adb_shell dumpsys package com.whatsapp | grep -m1 versionName | sed 's/.*=//')
    echo "  ✓ WhatsApp instalado ($wa_ver)"
    wa_status="instalado ($wa_ver)"
else
    echo "  ⚠️ WhatsApp NO instalado en este equipo"
    wa_status="NO INSTALADO"
fi

# --- 6. Verificar que la sesión WAHA de este chofer esté WORKING ---
waha_status="desconocido"
if [[ -n "${WAHA_API_KEY:-}" ]]; then
    waha_status=$(curl -sS -m 15 "http://127.0.0.1:3000/api/sessions/${SESSION}" \
        -H "X-Api-Key: ${WAHA_API_KEY}" 2>/dev/null | python3 -c 'import sys,json
try:
    d=json.load(sys.stdin); print(d.get("status","?"), (d.get("me") or {}).get("id","").split("@")[0])
except Exception: print("?","")' 2>/dev/null || echo "?")
    echo "  ✓ Sesión WAHA $SESSION: $waha_status"
fi

# --- 7. Registrar en dispatch.db ---
if command -v sqlite3 >/dev/null && [[ -f "$REPO_ROOT/data/dispatch.db" ]]; then
    sqlite3 "$REPO_ROOT/data/dispatch.db" \
        "UPDATE vehicles SET operator_name='$CHOFER' WHERE id=$VEHICLE_ID;" 2>/dev/null
    row=$(sqlite3 "$REPO_ROOT/data/dispatch.db" \
        "SELECT id,name,operator_name FROM vehicles WHERE id=$VEHICLE_ID;" 2>/dev/null)
    echo "  ✓ DB: $row"
else
    echo "  ⚠️ sqlite3 o dispatch.db no disponible, salto registro"
    row="(no registrado)"
fi

# --- Reporte ---
report="📱 EQUIPO CONFIGURADO — ${CHOFER} (${VEHICULO})

Dispositivo: ${fabricante} ${modelo} · Android ${android}
Serial ADB: ${SERIAL}

WhatsApp: ${wa_status}
Número esperado: +${WA}
Sesión WAHA ${SESSION}: ${waha_status}

Ajustes aplicados:
· Pantalla encendida mientras carga (stay_on_while_plugged_in=3)
· Apagado de pantalla a 10 min
· Brillo alto para exteriores

DB: ${row}

⚠️ Verificá que el WhatsApp de este equipo sea el +${WA}. Si es otro número,
la regla de consistencia por entrega se rompe."

notify "$report"
echo
echo "=== LISTO: $SERIAL → $CHOFER ==="
echo "$report"
