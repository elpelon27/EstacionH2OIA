#!/bin/bash
# Backup diario de BDs SQLite — Estación H2O
# Cron: 0 2 * * * /mnt/ssd_trabajo/hermes-agent/scripts/backup_db.sh
# Retention: 14 días local, 90 días off-site
# Off-site: rclone → GDrive/B2/S3 (configurar remote 'offsite')

set -euo pipefail

REPO="/mnt/ssd_trabajo/hermes-agent"
BACKUP_DIR="${REPO}/backups"
DATE=$(date +%Y%m%d)
RETENTION_LOCAL_DAYS=14
RETENTION_OFFSITE_DAYS=90
RCLONE_REMOTE="gdrive-personal"  # Configurar: rclone config → nombre del remote
RCLONE_PATH="estacion-h2o/backups"  # Path dentro del remote

mkdir -p "${BACKUP_DIR}"

# ===== BACKUP LOCAL =====
echo "[$(date)] === INICIO BACKUP LOCAL ==="

# Backup conversations.db (Valentina: orders, dispatch_queue, fs_pedidos)
if [ -f "${REPO}/data/conversations.db" ]; then
    sqlite3 "${REPO}/data/conversations.db" ".backup '${BACKUP_DIR}/conversations-${DATE}.db'"
    echo "[$(date)] conversations.db -> backups/conversations-${DATE}.db"
fi

# Backup dispatch.db (Dispatcher: clients, deliveries, vehicles)
if [ -f "${REPO}/data/dispatch.db" ]; then
    sqlite3 "${REPO}/data/dispatch.db" ".backup '${BACKUP_DIR}/dispatch-${DATE}.db'"
    echo "[$(date)] dispatch.db -> backups/dispatch-${DATE}.db"
fi

# Limpiar backups locales mayores a RETENTION_LOCAL_DAYS
find "${BACKUP_DIR}" -name "*.db" -mtime +${RETENTION_LOCAL_DAYS} -delete
echo "[$(date)] Limpieza local retention ${RETENTION_LOCAL_DAYS} días completada"

LOCAL_COUNT=$(find "${BACKUP_DIR}" -name "*.db" | wc -l)
echo "[$(date)] Total backups locales: ${LOCAL_COUNT}"

# ===== BACKUP OFF-SITE (rclone) =====
if command -v rclone >/dev/null 2>&1 && rclone listremotes 2>/dev/null | grep -q "^${RCLONE_REMOTE}:"; then
    echo "[$(date)] === INICIO BACKUP OFF-SITE (${RCLONE_REMOTE}) ==="
    
    # Sync backups a off-site
    rclone copy "${BACKUP_DIR}/" "${RCLONE_REMOTE}:${RCLONE_PATH}/" \
        --progress \
        --transfers 4 \
        --checkers 8 \
        --retries 3 \
        --low-level-retries 10 \
        2>&1 | while IFS= read -r line; do echo "[$(date)] [rclone] $line"; done
    
    RCLONE_EXIT=${PIPESTATUS[0]}
    if [ ${RCLONE_EXIT} -eq 0 ]; then
        echo "[$(date)] ✅ Sync off-site completado"
        
        # Limpiar off-site mayor a RETENTION_OFFSITE_DAYS
        rclone delete "${RCLONE_REMOTE}:${RCLONE_PATH}/" \
            --min-age ${RETENTION_OFFSITE_DAYS}d \
            --rmdirs \
            2>&1 | while IFS= read -r line; do echo "[$(date)] [rclone-cleanup] $line"; done
        echo "[$(date)] Limpieza off-site retention ${RETENTION_OFFSITE_DAYS} días completada"
    else
        echo "[$(date)] ❌ Sync off-site FALLÓ (exit=${RCLONE_EXIT})"
    fi
else
    echo "[$(date)] ⚠️ rclone no instalado o remote '${RCLONE_REMOTE}' no configurado — saltando off-site"
    echo "[$(date)] Para configurar: rclone config (crear remote '${RCLONE_REMOTE}' GDrive/B2/S3)"
fi

echo "[$(date)] === BACKUP COMPLETADO ==="
