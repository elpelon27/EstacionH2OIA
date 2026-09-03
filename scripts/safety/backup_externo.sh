#!/bin/bash
TS=$(date '+%Y%m%d_%H%M%S')
LOG=/home/skynet/backup_externo.log
USB=/media/skynet/"Nuevo vol"/hermes-backup

echo "=== BACKUP USB $TS ===" >> $LOG

if [ ! -d "$USB" ]; then
  mkdir -p "$USB" 2>/dev/null
fi

if [ ! -d "$USB" ]; then
  echo "⚠ USB no disponible — abortando" >> $LOG
  exit 1
fi

rsync -avz --delete \
  --exclude='venv/' \
  --exclude='__pycache__/' \
  --exclude='.git/objects/' \
  --exclude='*.pyc' \
  --exclude='node_modules/' \
  /mnt/ssd_trabajo/hermes-agent/ "$USB/" >> $LOG 2>&1

# Backup de biblioteca docs (resúmenes Qwen)
rsync -avz /mnt/ssd_trabajo/hermes-agent/docs/biblioteca/ \
  "$USB/docs-biblioteca/" >> $LOG 2>&1

echo "✓ Backup USB $TS completado" >> $LOG
