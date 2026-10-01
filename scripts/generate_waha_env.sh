#!/usr/bin/env bash
# Genera infra/waha/.env con la API key real desde config/.env.
# El .env del compose NO se versiona (va en .gitignore).
set -euo pipefail

# Script vive en scripts/ -> repo root es un nivel arriba.
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET="$REPO_ROOT/infra/waha/.env"

KEY=""
if [[ -f "$REPO_ROOT/config/.env" ]]; then
    KEY="$(grep -E '^WAHA_API_KEY=' "$REPO_ROOT/config/.env" | head -1 | cut -d= -f2-)"
    KEY="${KEY%\"}"
    KEY="${KEY#\"}"
    KEY="${KEY%\'}"
    KEY="${KEY#\'}"
fi

if [[ -z "$KEY" ]]; then
    echo "FATAL: no encontre WAHA_API_KEY en config/.env" >&2
    exit 1
fi

umask 077
printf 'WAHA_API_KEY=%s\n' "$KEY" > "$TARGET"
chmod 600 "$TARGET"
echo "OK: $TARGET generado (key de ${#KEY} chars, permisos 600)"
