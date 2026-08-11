#!/bin/bash
# backup_daily.sh - Daily backup script for Estación H2O
# Runs via cron (daily at 03:00)
# Backs up: SQLite databases, configs, .env files

set -euo pipefail

# Configuración
BACKUP_ROOT="/mnt/ssd_trabajo/backups"
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="${BACKUP_ROOT}/daily/${DATE}"
RETENTION_DAYS=30  # Keep 30 days of daily backups
PROJECT_ROOT="/mnt/ssd_trabajo/hermes-agent"

# Colores para logging
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $(date '+%Y-%m-%d %H:%M:%S') $*"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $(date '+%Y-%m-%d %H:%M:%S') $*"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $(date '+%Y-%m-%d %H:%M:%S') $*"
}

# Crear directorio de backup
mkdir -p "${BACKUP_DIR}"
log_info "Iniciando backup diario en ${BACKUP_DIR}"

# 1. Backup SQLite databases (con WAL checkpoint para consistencia)
log_info "Backup de bases de datos SQLite..."

DB_FILES=(
    "${PROJECT_ROOT}/data/conversations.db"
    "${PROJECT_ROOT}/data/dispatch.db"
)

for db in "${DB_FILES[@]}"; do
    if [[ -f "$db" ]]; then
        db_name=$(basename "$db")
        # Forzar checkpoint WAL antes de copiar
        sqlite3 "$db" "PRAGMA wal_checkpoint(FULL);" 2>/dev/null || true
        cp "$db" "${BACKUP_DIR}/${db_name}"
        # Backup WAL y SHM si existen
        [[ -f "${db}-wal" ]] && cp "${db}-wal" "${BACKUP_DIR}/${db_name}-wal"
        [[ -f "${db}-shm" ]] && cp "${db}-shm" "${BACKUP_DIR}/${db_name}-shm"
        log_info "  ✓ ${db_name}"
    else
        log_warn "  ✗ No encontrado: ${db}"
    fi
done

# 2. Backup configuraciones críticas
log_info "Backup de configuraciones..."

CONFIG_FILES=(
    "${PROJECT_ROOT}/config/.env"
    "${PROJECT_ROOT}/config/.env.example"
    "${PROJECT_ROOT}/config/watchdog.conf"
    "${PROJECT_ROOT}/config/valentina-bridge-journald.conf"
    "${PROJECT_ROOT}/config/logrotate-valentina-bridge"
    "${PROJECT_ROOT}/config/google_credentials.json"
)

mkdir -p "${BACKUP_DIR}/config"
for cfg in "${CONFIG_FILES[@]}"; do
    if [[ -f "$cfg" ]]; then
        cp "$cfg" "${BACKUP_DIR}/config/"
        log_info "  ✓ $(basename "$cfg")"
    else
        log_warn "  ✗ No encontrado: ${cfg}"
    fi
done

# 3. Backup systemd service files
log_info "Backup de systemd services..."

mkdir -p "${BACKUP_DIR}/systemd"
SERVICE_FILES=(
    "/etc/systemd/system/valentina-bridge.service"
    "/etc/systemd/system/dispatcher-bot.service"
    "/etc/systemd/system/telegram-bot.service"
    "/etc/systemd/system/cloudflared.service"
)

for svc in "${SERVICE_FILES[@]}"; do
    if [[ -f "$svc" ]]; then
        cp "$svc" "${BACKUP_DIR}/systemd/"
        log_info "  ✓ $(basename "$svc")"
    else
        log_warn "  ✗ No encontrado: ${svc}"
    fi
done

# 4. Backup scripts de inicio
log_info "Backup de scripts de inicio..."

mkdir -p "${BACKUP_DIR}/scripts"
START_SCRIPTS=(
    "${PROJECT_ROOT}/api/start_bridge.sh"
    "${PROJECT_ROOT}/api/start_dispatcher.sh"
    "${PROJECT_ROOT}/api/start_telegram.sh"
)

for script in "${START_SCRIPTS[@]}"; do
    if [[ -f "$script" ]]; then
        cp "$script" "${BACKUP_DIR}/scripts/"
        log_info "  ✓ $(basename "$script")"
    fi
done

# 5. Crear manifest del backup
log_info "Creando manifest..."
cat > "${BACKUP_DIR}/MANIFEST.txt" <<EOF
Estación H2O - Backup Diario
=============================
Fecha: $(date '+%Y-%m-%d %H:%M:%S')
Host: $(hostname)
Usuario: $(whoami)

Archivos incluidos:
$(find "${BACKUP_DIR}" -type f | sort | sed "s|${BACKUP_DIR}/||")

Tamaños:
$(du -h "${BACKUP_DIR}"/* 2>/dev/null | sort -h)

EOF

# 6. Comprimir backup
log_info "Comprimiendo backup..."
cd "${BACKUP_ROOT}/daily"
tar -czf "${DATE}.tar.gz" "${DATE}"
if [[ $? -eq 0 ]]; then
    rm -rf "${BACKUP_DIR}"
    BACKUP_SIZE=$(du -h "${DATE}.tar.gz" | cut -f1)
    log_info "Backup comprimido: ${DATE}.tar.gz (${BACKUP_SIZE})"
else
    log_error "Error comprimiendo backup"
    exit 1
fi

# 7. Limpiar backups antiguos (retención)
log_info "Limpiando backups antiguos (>${RETENTION_DAYS} días)..."
find "${BACKUP_ROOT}/daily" -name "*.tar.gz" -mtime +${RETENTION_DAYS} -delete
REMAINING=$(ls -1 "${BACKUP_ROOT}/daily"/*.tar.gz 2>/dev/null | wc -l)
log_info "Backups restantes: ${REMAINING}"

# 8. Verificar integridad del backup recién creado
log_info "Verificando integridad..."
tar -tzf "${BACKUP_ROOT}/daily/${DATE}.tar.gz" > /dev/null
if [[ $? -eq 0 ]]; then
    log_info "✓ Integridad verificada"
else
    log_error "✗ FALLO DE INTEGRIDAD"
    exit 1
fi

log_info "=== Backup diario completado exitosamente ==="
exit 0