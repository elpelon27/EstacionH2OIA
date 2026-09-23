#!/bin/bash
# Strix pentesting semanal (FASE 8) — GUARD TRIPLE:
# 1. Solo corre si config/strix_targets.env existe con STRIX_ENABLED=1
# 2. Targets SOLO del ambiente de pruebas (jamás producción)
# 3. Sin archivo → exit 0 silencioso (PENDIENTE LÍDER)
set -euo pipefail

REPO=/mnt/ssd_trabajo/hermes-agent
TARGETS="$REPO/config/strix_targets.env"
REPORT_DIR="$REPO/docs/seguridad"

if [ ! -f "$TARGETS" ]; then
    echo "strix_targets.env no existe — Strix PENDIENTE LÍDER (ambiente aislado no creado)"
    exit 0
fi

source "$TARGETS"
if [ "${STRIX_ENABLED:-0}" != "1" ]; then
    echo "STRIX_ENABLED != 1 — Strix deshabilitado"
    exit 0
fi

# Guard anti-producción: jamas apuntar a IPs/puertos de producción
if [ -n "${STRIX_TARGET:-}" ]; then
    case "$STRIX_TARGET" in
        *156.255.155.24*|*localhost*|*127.0.0.1*|*0.0.0.0*)
            echo "BLOQUEADO: target apunta a producción loopback/IP pública"
            exit 1
            ;;
    esac
fi

mkdir -p "$REPORT_DIR"
DATE=$(date +%Y%m%d)
REPORT="$REPORT_DIR/strix_report_${DATE}.md"

echo "# Strix Report $DATE" > "$REPORT"
echo "Target: ${STRIX_TARGET:-<sin target>}" >> "$REPORT"

cd "$REPO"
if ! command -v uv &>/dev/null && [ ! -d "$REPO/external_repos/strix/.venv" ]; then
    echo "Strix no instalado (uv/.venv ausente) — documentar y salir." >> "$REPORT"
    exit 0
fi

# Ejecutar strix SOLO contra el ambiente de pruebas
cd "$REPO/external_repos/strix"
STRIX_RESULT=$(timeout 3600 "$REPO/venv/bin/python" -m strix --target "$STRIX_TARGET" \
    --output "$REPORT" 2>&1 || echo "strix falló/timeout — revisar logs")
echo "strix: $STRIX_RESULT" >> "$REPORT"

# Notificar vuln crítica → operador (vía archivo; el bot la lee en /ataque_detectado)
if grep -qi "critical\|crítica" "$REPORT"; then
    echo "VULN CRÍTICA DETECTADA — ver $REPORT" >&2
fi
