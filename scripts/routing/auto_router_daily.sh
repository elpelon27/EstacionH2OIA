#!/bin/bash
# Auto-routing NIVEL 1 — 6:00 AM diario (cron del Líder).
# Materializa pedidos de clientes is_automatic=1 en orders_auto
# (estado 'pending_dispatch') para que el dispatcher los asigne.
# Idempotente: UNIQUE(client_id, delivery_date) + INSERT OR IGNORE.
set -euo pipefail
REPO=/mnt/ssd_trabajo/hermes-agent
cd "$REPO"
mkdir -p logs
venv/bin/python scripts/routing/auto_router.py --create >> logs/auto_router_cron.log 2>&1
echo "$(date '+%F %T') auto_router OK" >> logs/auto_router_cron.log
