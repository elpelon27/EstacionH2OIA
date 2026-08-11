#!/bin/bash
# ============================================================================
# backup_daily.sh — Backup diario de bases de datos y configuración
# Ejecución: 3:00 AM diario via systemd timer
# ============================================================================

set -euo pipefail

# Cargar variables de entorno
if [[ -f "/mnt/ssd_trabajo/hermes-agent/config/.env" ]]; then
    set -a
    source /mnt/ssd_trabajo/hermes-agent/config/.env
    set +a
fi

# Configuración
BACKUP_DIR="${DATABASE_BACKUP_PATH:-/mnt/ssd_trabajo/backups/daily}"
DATE=$(date -u +"%Y%m%d_%H%M%S")
HOSTNAME=$(hostname)
RETENTION_DAYS=30

# Crear directorio de backup
mkdir -p "$BACKUP_DIR"

# Logging
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$BACKUP_DIR/backup_${DATE}.log"
}

# Enviar Telegram
send_telegram() {
    local message="$1"
    local bot_token="${TELEGRAM_BOT_TOKEN_HERMES:-${TELEGRAM_BOT_TOKEN:-}}"
    local chat_id="${TELEGRAM_CHAT_ID_HERMES:-${TELEGRAM_CHAT_ID:-1663148211}}"
    
    if [[ -n "$bot_token" ]]; then
        curl -s -X POST "https://api.telegram.org/bot${bot_token}/sendMessage" \
            -d chat_id="$chat_id" \
            -d text="$message" \
            -d parse_mode="HTML" \
            >/dev/null 2>&1 || true
    fi
}

log "=== Iniciando backup diario ==="

# Contador de errores
ERRORS=0

# 1. Backup conversations.db (SQLite WAL)
log "Backup conversations.db..."
if [[ -f "/mnt/ssd_trabajo/hermes-agent/data/conversations.db" ]]; then
    # Usar sqlite3 .backup para backup consistente con WAL
    /mnt/ssd_trabajo/hermes-agent/venv/bin/python3 -c "
import sqlite3
src = sqlite3.connect('/mnt/ssd_trabajo/hermes-agent/data/conversations.db')
dst = sqlite3.connect('$BACKUP_DIR/conversations_${DATE}.db')
src.backup(dst)
dst.close()
src.close()
print('OK')
" && log "  ✅ conversations.db backup OK" || { log "  ❌ conversations.db backup FAILED"; ((ERRORS++)); }
else
    log "  ⚠️ conversations.db no existe"
fi

# 2. Backup dispatch.db
log "Backup dispatch.db..."
if [[ -f "/mnt/ssd_trabajo/hermes-agent/data/dispatch.db" ]]; then
    /mnt/ssd_trabajo/hermes-agent/venv/bin/python3 -c "
import sqlite3
src = sqlite3.connect('/mnt/ssd_trabajo/hermes-agent/data/dispatch.db')
dst = sqlite3.connect('$BACKUP_DIR/dispatch_${DATE}.db')
src.backup(dst)
dst.close()
src.close()
print('OK')
" && log "  ✅ dispatch.db backup OK" || { log "  ❌ dispatch.db backup FAILED"; ((ERRORS++)); }
else
    log "  ⚠️ dispatch.db no existe"
fi

# 3. Backup config/.env (sin secrets en log)
log "Backup config..."
cp /mnt/ssd_trabajo/hermes-agent/config/.env "$BACKUP_DIR/env_${DATE}.bak" 2>/dev/null \
    && log "  ✅ config backup OK" || { log "  ❌ config backup FAILED"; ((ERRORS++)); }

# 4. Backup systemd units
log "Backup systemd units..."
mkdir -p "$BACKUP_DIR/systemd_${DATE}"
cp /mnt/ssd_trabajo/hermes-agent/systemd/*.service "$BACKUP_DIR/systemd_${DATE}/" 2>/dev/null \
    && log "  ✅ systemd units backup OK" || { log "  ❌ systemd units backup FAILED"; ((ERRORS++)); }

# 5. Comprimir backups antiguos (>1 día) para ahorrar espacio
log "Comprimiendo backups antiguos..."
find "$BACKUP_DIR" -name "*.db" -mtime +1 -exec gzip -f {} \; 2>/dev/null
find "$BACKUP_DIR" -name "*.bak" -mtime +1 -exec gzip -f {} \; 2>/dev/null

# 6. Limpiar backups > RETENTION_DAYS
log "Limpiando backups > ${RETENTION_DAYS} días..."
find "$BACKUP_DIR" -type f -mtime +${RETENTION_DAYS} -delete 2>/dev/null

# 7. Verificar espacio en disco
DISK_USAGE=$(df -h /mnt/ssd_trabajo | awk 'NR==2 {print $5}' | sed 's/%//')
log "Uso de disco SSD: ${DISK_USAGE}%"

# Resumen
END_TIME=$(date -u +"%Y%m%d_%H%M%S")
BACKUP_SIZE=$(du -sh "$BACKUP_DIR" 2>/dev/null | cut -f1)

if [[ $ERRORS -eq 0 ]]; then
    STATUS="✅ EXITOSO"
    MESSAGE="💾 <b>Backup Diario</b> ($DATE)\n\nEstado: $STATUS\nTamaño total: $BACKUP_SIZE\nDisco: ${DISK_USAGE}%\nErrores: 0"
else
    STATUS="❌ CON ERRORES"
    MESSAGE="💾 <b>Backup Diario</b> ($DATE)\n\nEstado: $STATUS\nTamaño total: $BACKUP_SIZE\nDisco: ${DISK_USAGE}%\nErrores: $ERRORS"
fi

log "=== Backup finalizado: $STATUS ==="
log "Tamaño total backups: $BACKUP_SIZE"

send_telegram "$MESSAGE"

exit $ERRORS