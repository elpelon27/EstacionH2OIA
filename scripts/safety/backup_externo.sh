#!/bin/bash
TS=$(date '+%Y%m%d_%H%M%S')
LOG=/home/skynet/backup_externo.log

echo "=== BACKUP EXTERNO $TS ===" >> $LOG

# 1. USB físico (rsync) — no aborta si el USB no está disponible
USB=/media/skynet/"Nuevo vol"/hermes-backup
if mkdir -p "$USB" 2>/dev/null && [ -w "$USB" ]; then
  rsync -avz --delete \
    --exclude='venv/' \
    --exclude='__pycache__/' \
    --exclude='.git/objects/' \
    --exclude='*.pyc' \
    /mnt/ssd_trabajo/hermes-agent/ "$USB/" >> $LOG 2>&1
  echo "✓ USB backup OK" >> $LOG
else
  echo "⚠ USB no disponible/escribible — se omite (PENDIENTE PERMISO)" >> $LOG
fi

# 2. Google Drive (rclone, solo backups críticos)
# NOTA: remoto "off-site" está ROTO (Service Account sin cuota de Google Drive, error 403
# storageQuotaExceeded desde 2026-09-03). Se usa gdrive-personal (OAuth personal, verificado OK).
rclone copy /mnt/ssd_trabajo/backups/daily/ \
  gdrive-personal:EstacionH2O_Backups/daily/ \
  --transfers 4 >> $LOG 2>&1
[ $? -eq 0 ] && echo "✓ GDrive daily OK" >> $LOG || echo "⚠ GDrive daily FALLÓ" >> $LOG

# 3. Repo a Google Drive (espejo del contenido de trabajo)
# .git/ se excluye COMPLETO: el historial ya está replicado en GitHub (push automático
# post-commit + cron cada 10 min), y copiar .git en vivo choca con el snapshot cron cada 2 min.
rclone sync /mnt/ssd_trabajo/hermes-agent/ \
  gdrive-personal:EstacionH2O_Backups/hermes-repo/ \
  --exclude='venv/' \
  --exclude='__pycache__/' \
  --exclude='.git/' \
  --exclude='*.pyc' \
  --transfers 4 >> $LOG 2>&1
[ $? -eq 0 ] && echo "✓ GDrive repo sync OK" >> $LOG || echo "⚠ GDrive repo sync FALLÓ" >> $LOG

echo "✓ Backup externo $TS completado" >> $LOG
