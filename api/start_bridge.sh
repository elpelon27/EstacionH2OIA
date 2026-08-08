#!/bin/bash
# Wrapper para valentina-bridge: carga .env y ejecuta uvicorn
set -euo pipefail

ENV_FILE="/mnt/ssd_trabajo/hermes-agent/config/.env"
WORKDIR="/mnt/ssd_trabajo/hermes-agent/api"
UVICORN="/mnt/ssd_trabajo/hermes-agent/venv/bin/uvicorn"

# Cargar variables de entorno (systemd EnvironmentFile no lo hace bien con este .env)
set -a
source "$ENV_FILE"
set +a

cd "$WORKDIR"
exec "$UVICORN" bridge:app \
    --host 0.0.0.0 \
    --port 8000 \
    --workers 1 \
    --log-level info \
    --no-access-log