#!/bin/bash
# Wrapper para telegram-bot: carga .env y ejecuta python
set -euo pipefail

ENV_FILE="/mnt/ssd_trabajo/hermes-agent/config/.env"
WORKDIR="/mnt/ssd_trabajo/hermes-agent/skills"
PYTHON="/mnt/ssd_trabajo/hermes-agent/venv/bin/python"

# Cargar variables de entorno
set -a
source "$ENV_FILE"
set +a

cd "$WORKDIR"
exec "$PYTHON" telegram_bot.py