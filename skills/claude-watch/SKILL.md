---
name: claude-watch
description: >
  Analiza videos de YouTube/local con Gemini 3 Pro (OpenRouter) y los convierte
  en conocimiento: frames + transcript + análisis + campo tema para routing
  futuro a skills especializados. Indexa en Qdrant (videos_h2o). Úsalo cuando
  el Líder pida analizar/aprender de un video.
---

# claude-watch (adaptado a Hermes)

Flujo: descarga (yt-dlp) → frames (ffmpeg) → transcript (captions nativos) →
análisis (LLMClient, task_type="video", tier gemini-3-pro-preview) →
outputs (MD + JSON en docs/videos/, espejo en obsidian-vault/videos/) →
indexado en Qdrant colección videos_h2o (embeddings nomic-embed-text, 768).

## Invocación

```bash
/home/skynet/watch_video.sh <youtube-url> [tema]   # tema: auto|agropecuario|h2o|otro
```

o directo:

```bash
venv/bin/python skills/claude-watch/watch.py <url> \
  --output-dir docs/videos --obsidian-dir obsidian-vault/videos \
  --qdrant-collection videos_h2o --llm-tier gemini-3-pro-preview --tema auto
```

## Dependencias

ffmpeg/ffprobe (sistema), yt-dlp, ffmpeg-python (venv, ver requirements.txt),
Ollama nomic-embed-text para embeddings, Qdrant en localhost:6333,
OPENROUTER_API_KEY en config/.env.

## Reglas

- El análisis usa SOLO el tier video_ok (gemini-3-pro-preview); nunca GLM/Ollama.
- El campo "tema" es OBLIGATORIO en todo payload (routing futuro de skills).
- El transcript se indexa por chunks; los puntos llevan video_id + tema.
- No subir el video a ningún API: solo frames comprimidos (JPEG, 512px).
