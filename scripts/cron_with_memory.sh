#!/bin/bash
# cron_with_memory.sh — Wrapper de crons que registra cada ejecución en
# hermes_memory.db::cron_runs (PARCHE 10, SOUL v2.1 FASE 3 — §11.2a).
#
# Uso: cron_with_memory.sh <nombre_cron> <comando> [args...]
#
# Registra: timestamp, éxito/fracaso, duración_ms, output_hash (sha256 del
# stdout — nunca guarda el output: privacidad §6.6). Si un cron falla 2 veces
# consecutivas, deja constancia (el Consolidador lo lee para skill candidate).
#
# Fail-open: si el registro falla, el comando igualmente se ejecuta y su exit
# code se preserva (el wrapper NUNCA bloquea el cron original).
#
# Autor: Prometeo · FASE 3 SOUL v2.1.0 · 2026-09-10

set -u

REPO="/mnt/ssd_trabajo/hermes-agent"
PYTHON="${REPO}/venv/bin/python"
MEMORY_DB="${REPO}/data/hermes_memory.db"
REGISTRY="${REPO}/data/.cron_failure_streak"

if [ "$#" -lt 2 ]; then
    echo "usage: cron_with_memory.sh <nombre_cron> <comando> [args...]" >&2
    exit 2
fi

CRON_NAME="$1"
shift

START_NS=$(date +%s%N)
# Ejecutar el comando real; capturar output en memoria (no disco) y exit code
OUTPUT=$("$@" 2>&1)
EXIT_CODE=$?
END_NS=$(date +%s%N)

DURATION_MS=$(( (END_NS - START_NS) / 1000000 ))
OUTPUT_HASH=$(printf '%s' "$OUTPUT" | sha256sum | cut -d' ' -f1)
SUCCESS=$(( EXIT_CODE == 0 ? 1 : 0 ))

# Registrar en cron_runs (fail-open: error de registro no rompe el cron)
if [ -x "$PYTHON" ]; then
    "$PYTHON" - "$CRON_NAME" "$SUCCESS" "$DURATION_MS" "$OUTPUT_HASH" "$EXIT_CODE" <<'PYEOF' || true
import sqlite3
import sys
from datetime import UTC, datetime

name, success, duration_ms, output_hash, exit_code = sys.argv[1:6]
db = "/mnt/ssd_trabajo/hermes-agent/data/hermes_memory.db"
err = None
if exit_code != "0":
    # Guardar solo el TAIL del output como error (diagnóstico, no privacidad)
    err = None  # output completo NO se persiste (privacidad §6.6)

try:
    conn = sqlite3.connect(db, timeout=10)
    conn.execute(
        "INSERT INTO cron_runs (cron_name, success, duration_ms, output_hash, error) "
        "VALUES (?, ?, ?, ?, ?)",
        (name, bool(int(success)), int(duration_ms), output_hash, err),
    )
    conn.commit()
    conn.close()
except Exception as e:
    print(f"[cron_with_memory] registro falló (fail-open): {e}", file=sys.stderr)
PYEOF
else
    echo "[cron_with_memory] python no encontrado — ejecución registrada solo en log" >&2
fi

# Streak de fallos: 2 consecutivos → marcar (el Consolidador/episódica lo lee)
if [ "$EXIT_CODE" -ne 0 ]; then
    COUNT=$(cat "$REGISTRY" 2>/dev/null || echo 0)
    COUNT=$((COUNT + 1))
    echo "$COUNT" > "$REGISTRY"
    if [ "$COUNT" -ge 2 ]; then
        echo "[cron_with_memory] ADVERTENCIA: '$CRON_NAME' falló $COUNT veces consecutivas — candidato a entrada episódica + skill (§11.2a)" >&2
    fi
else
    rm -f "$REGISTRY" 2>/dev/null || true
fi

exit "$EXIT_CODE"