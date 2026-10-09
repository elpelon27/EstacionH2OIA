#!/bin/bash
# Warm-up LLM Valentina — garantiza que qwen2.5:7b esté cargada en Ollama.
# Creado 2026-10-09 (forense Falla 1): con OLLAMA_MAX_LOADED_MODELS=1, otros
# proyectos de la máquina desalojan el modelo; el próximo cliente pagaba la
# recarga (>30s) y el bridge respondía "problemas técnicos".
# Este script recarga y FIJA el modelo (keep_alive=-1) sin que un cliente pague el costo.
# Cron sugerido: cada 10 minutos.
set -uo pipefail

MODEL="${OLLAMA_MODEL:-qwen2.5:7b}"
API="http://localhost:11434/api/generate"

# Si ya está cargada, salir gratis (barato: solo consulta /api/ps)
LOADED=$(curl -sS -m 5 http://localhost:11434/api/ps 2>/dev/null | grep -c "$MODEL" || true)
if [ "$LOADED" -gt 0 ]; then
    exit 0
fi

# Recarga mínima + pin permanente
START=$(date +%s)
curl -sS -m 300 "$API" -d "{\"model\": \"$MODEL\", \"prompt\": \"\", \"keep_alive\": -1, \"options\": {\"num_predict\": 1}}" >/dev/null 2>&1
END=$(date +%s)
echo "$(date '+%F %T') warmup $MODEL cargado en $((END-START))s (estaba desalojado)"
