#!/bin/bash
# watch_video.sh — analizar video YouTube y convertirlo en conocimiento
# Uso: watch_video.sh <youtube-url> [tema]  (tema: auto|agropecuario|h2o|otro)
set -euo pipefail
URL=$1
TEMA=${2:-auto}  # auto = Gemini decide el tema
cd /mnt/ssd_trabajo/hermes-agent
export PATH="$PWD/venv/bin:$PATH"  # yt-dlp vive en el venv; el servicio systemd no lo tiene en PATH
exec venv/bin/python skills/claude-watch/watch.py "$URL" \
  --output-dir docs/videos \
  --obsidian-dir obsidian-vault/videos \
  --qdrant-collection videos_h2o \
  --llm-tier gemini-3-pro-preview \
  --tema "$TEMA"
