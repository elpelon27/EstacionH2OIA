#!/bin/bash
# ============================================================================
# Install hardened systemd services for Estación H2O
# Ejecutar con: sudo bash install_hardened_services.sh
# ============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SYSTEMD_DIR="/etc/systemd/system"
SOURCE_DIR="${SCRIPT_DIR}/../systemd"

echo "🔧 Instalando servicios systemd endurecidos..."

# 1. Crear usuario cloudflared si no existe
if ! id "cloudflared" &>/dev/null; then
    echo "👤 Creando usuario cloudflared..."
    useradd -r -s /usr/sbin/nologin -d /nonexistent cloudflared
fi

# 2. Copiar archivos de servicio endurecidos
SERVICES=(
    "valentina-bridge.service.hardened:valentina-bridge.service"
    "dispatcher-bot.service.hardened:dispatcher-bot.service"
    "telegram-bot.service.hardened:telegram-bot.service"
    "cloudflared.service.hardened:cloudflared.service"
    "cloudflare-watchdog.service.hardened:cloudflare-watchdog.service"
    "boot-alert.service:boot-alert.service"
)

for mapping in "${SERVICES[@]}"; do
    src="${mapping%%:*}"
    dst="${mapping##*:}"
    echo "📄 Instalando $dst..."
    cp "${SOURCE_DIR}/${src}" "${SYSTEMD_DIR}/${dst}"
done

# 3. Copiar timer (no necesita hardened, ya está bien)
if [[ -f "${SOURCE_DIR}/cloudflare-watchdog.timer" ]]; then
    cp "${SOURCE_DIR}/cloudflare-watchdog.timer" "${SYSTEMD_DIR}/"
fi

# 4. Configurar watchdog
echo "⌚ Configurando hardware watchdog..."
if [[ -f "${SCRIPT_DIR}/config/watchdog.conf" ]]; then
    cp "${SCRIPT_DIR}/config/watchdog.conf" /etc/watchdog.conf
fi

# 5. Crear directorios PID para watchdog
mkdir -p /run
touch /run/valentina-bridge.pid /run/dispatcher-bot.pid /run/telegram-bot.pid /run/cloudflared.pid
chown skynet:skynet /run/valentina-bridge.pid /run/dispatcher-bot.pid /run/telegram-bot.pid
chown cloudflared:cloudflared /run/cloudflared.pid

# 6. Recargar systemd
echo "🔄 Recargando systemd..."
systemctl daemon-reload

# 7. Habilitar servicios
echo "✅ Habilitando servicios..."
systemctl enable valentina-bridge.service
systemctl enable dispatcher-bot.service
systemctl enable telegram-bot.service
systemctl enable cloudflared.service
systemctl enable cloudflare-watchdog.timer
systemctl enable boot-alert.service

# 8. Habilitar watchdog (si está instalado)
if systemctl list-unit-files | grep -q watchdog.service; then
    echo "🐕 Habilitando watchdog..."
    systemctl enable watchdog.service
fi

echo ""
echo "✅ INSTALACIÓN COMPLETA"
echo ""
echo "Próximos pasos:"
echo "  1. Editar /mnt/ssd_trabajo/hermes-agent/config/boot_alert.json con token/chat_id reales"
echo "  2. Reiniciar servicios: sudo systemctl restart valentina-bridge dispatcher-bot telegram-bot cloudflared"
echo "  3. Iniciar watchdog: sudo systemctl start watchdog"
echo "  4. Verificar estado: sudo systemctl status valentina-bridge dispatcher-bot telegram-bot cloudflared boot-alert"
echo "  5. Probar alerta de boot: sudo systemctl start boot-alert"