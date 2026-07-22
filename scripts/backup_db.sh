#!/bin/bash
# Backup diario de BDs SQLite — Estación H2O
# Cron: 0 2 * * * /mnt/ssd_trabajo/hermes-agent/scripts/backup_db.sh
# Retention: 14 días

set -euo pipefail

REPO="/mnt/ssd_trabajo/hermes-agent"
BACKUP_DIR="${REPO}/backups"
DATE=$(date +%Y%m%d)
RETENTION_DAYS=14

mkdir -p "${BACKUP_DIR}"

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

# Limpiar backups mayores a RETENTION_DAYS
find "${BACKUP_DIR}" -name "*.db" -mtime +${RETENTION_DAYS} -delete
echo "[$(date)] Limpieza retention ${RETENTION_DAYS} días completada"

# Contar backups restantes
BACKUP_COUNT=$(find "${BACKUP_DIR}" -name "*.db" | wc -l)
echo "[$(date)] Total backups: ${BACKUP_COUNT}"
