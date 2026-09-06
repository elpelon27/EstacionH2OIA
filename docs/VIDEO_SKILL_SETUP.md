# VIDEO SKILL SETUP — claude-watch / pipeline de videos YouTube

Skill para analizar videos de YouTube y convertirlos en conocimiento
indexado. Implementado PARTE 1-6, 2026-09-04/05. Test real de
regresión OK (commit 88f1e35).

## Arquitectura

```
                    ┌─────────────────────────────────────────────┐
                    │              TRIGGERS                       │
                    │  CLI: /watch <url>   (scripts/prometeo/)    │
                    │  Telegram: /watch <url>  ó URL suelta       │
                    │             /watchstatus (estado)           │
                    └──────────────────┬──────────────────────────┘
                                       │
                              video_watch_service.py
                    (validación, dedupe Qdrant, rate limit, timeout)
                                       │
                          /home/skynet/watch_video.sh
                                       │
                    ┌──────────────────▼──────────────────────────┐
                    │  skills/claude-watch/watch.py               │
                    │                                             │
                    │  1. yt-dlp → video + captions VTT           │
                    │  2. ffprobe → duración → intervalo adapt.   │
                    │  3. ffmpeg → frames JPEG 512px (cap 240)    │
                    │  4. transcript VTT → texto con timestamps   │
                    │  5. LLMClient task_type="video"             │
                    │     Gemini 3.1 Pro Preview (OpenRouter)     │
                    │     frames base64 + transcript (ventanas)   │
                    │  6. skill_generator --dry-run (nunca auto)  │
                    └───────┬──────────┬──────────┬───────────────┘
                            │          │          │
                ┌───────────▼───┐ ┌────▼─────┐ ┌──▼──────────────┐
                │ docs/videos/  │ │ Qdrant   │ │ obsidian-vault/ │
                │ <id>.md/.json │ │videos_h2o│ │ videos/<id>.md  │
                │               │ │(nomic-   │ │ (espejo humano) │
                │               │ │ embed 768│ │                 │
                │               │ │UUID pts) │ │                 │
                └───────────────┘ └──────────┘ └─────────────────┘
```

## Uso

### CLI (servidor)

```
/home/skynet/watch_video.sh https://www.youtube.com/watch?v=<ID> [tema]
# tema: auto (default, Gemini clasifica) | agropecuario | h2o | otro

# o vía Prometeo interactivo:
python3 scripts/prometeo/prometeo.py
> /watch https://www.youtube.com/watch?v=<ID>
> /watch-status
```

### Telegram (bot prometeo-telegram, servicio systemd)

```
/watch https://www.youtube.com/watch?v=<ID>
/watchstatus          (nota: sin guion — Telegram solo permite [a-z0-9_])
```

Cualquier mensaje que contenga una URL de YouTube también dispara el
pipeline. Rate limit: 1 video cada 5 min por usuario, máx 20/día.

## Estructura de carpetas

```
skills/claude-watch/watch.py        # pipeline principal
skills/claude-watch-source/         # código fuente adaptado (download/frames/transcribe)
scripts/video_watch_service.py      # lógica compartida triggers (rate limit, dedupe)
scripts/skill_generator.py          # genera skills desde videos (dry-run por defecto)
scripts/prometeo/prometeo.py        # trigger CLI
skills/prometeo_telegram.py         # trigger Telegram (systemd: prometeo-telegram)
docs/videos/<video-id>.md|.json     # salida analysis
obsidian-vault/videos/<id>.md       # espejo para consulta humana
logs/video_usage.log                # uso (JSON lines, rate limiting)
```

## Colección Qdrant videos_h2o

- Vectores: nomic-embed-text (Ollama, 768 dims, Cosine)
- Point IDs: **UUID v5 determinísticos** — `uuid5(NAMESPACE_URL,
  "<video_id>-c<chunk>")`. Re-indexar el mismo video NO duplica puntos
  (mismo input → mismo UUID → upsert idempotente). Fix PARTE 6: antes
  eran strings crudos y Qdrant devolvía 400 (colección quedó en 0).
- Payload: video_id, url, title, duration_sec, tema (OBLIGATORIO, para
  routing futuro de skills), transcript_chunk_id, chunk (1200 chars),
  indexed_at.
- Chunking Qdrant: CHUNK_CHARS=1200 (NO tocar, independiente del
  chunking de análisis).

## Config (Gemini + adaptativa)

`.env` / `config/.env.example`:

```
OPENROUTER_MODEL_VIDEO=google/gemini-3.1-pro-preview
YOUTUBE_VIDEO_MAX_DURATION=7200        # 2 horas máx
YOUTUBE_VIDEO_FRAME_INTERVAL_SHORT=10  # videos <=30min
YOUTUBE_VIDEO_FRAME_INTERVAL_MEDIUM=30 # videos 30min-1h
YOUTUBE_VIDEO_FRAME_INTERVAL_LONG=60   # videos >1h
YOUTUBE_VIDEO_MAX_FRAMES=240
YOUTUBE_VIDEO_TRANSCRIPT_WINDOW=30000  # chars por ventana de análisis
YOUTUBE_VIDEO_TRANSCRIPT_OVERLAP=5000  # overlap entre ventanas
OBSIDIAN_VAULT_PATH=/mnt/ssd_trabajo/hermes-agent/obsidian-vault
EST_COST_PER_VIDEO_USD=0.02
```

El tier `gemini-3-pro-preview` en LLMClient tiene flag `video_ok: true`
y SOLO se usa para video — el chat sigue en GLM 5.3 → GLM 5.2 free →
Ollama (regla del Líder).

### Videos cortos vs largos

| Duración | Frame interval | Frames máx | Transcript |
|----------|---------------|------------|------------|
| <=30 min | 10s           | 240        | 1 pasada (<=30k chars) |
| 30-60 min| 30s           | 240        | ventanas 30k + overlap 5k |
| >60 min  | 60s           | 240        | ventanas 30k + overlap 5k |

Videos largos: cada ventana de transcript se analiza por separado
(con todos los frames) y un llamado final de consolidación fusiona los
análisis parciales deduplicando el overlap. `--frame-interval N`
explícito pisa el valor adaptativo.

## Costos reales (medidos, test 2026-09-05)

| Video | Costo real |
|-------|-----------|
| 2:20 min (14 frames, 4.4k chars) | **$0.0196** (in≈6k tok, out≈0.6k) |
| ~10 min | ≈ $0.04 |
| ~1 h | ≈ $0.10-0.20 |
| ~2 h | ≈ $0.20-0.50 |

Estimación original $0.15/video era 7.5x mayor que el real para videos
cortos. `EST_COST_PER_VIDEO_USD=0.02` ajustado al test real. El usage
real de tokens se loguea en cada llamado (`LLM usage <tier>: in=, out=`).

## Limitaciones

- Solo YouTube (youtube.com/watch, youtu.be, shorts). Sin Vimeo/local.
- Máx 7200s (2h). Videos más largos se rechazan con `video_too_long`.
- Requiere captions nativas — sin ellas el análisis es solo de frames.
- Timeout del pipeline: 20 min (videos 2h con descarga lenta pueden
  rozarlo; el rate limit de descarga de YouTube es la variable principal).
- Rate limits Gemini/OpenRouter: 429 → LLMClient reintenta con el
  siguiente tier (pero solo hay un tier video_ok).
- Qdrant/Ollama caídos NO abortan el MD (degradación graceful), solo
  pierde el indexado.

## Reglas: cuándo genera skill

`skill_generator.py --dry-run` corre al final de cada /watch. Criterio:
SOLO si el video enseña un **procedimiento operativo replicable**
(skill_proposal no-null del análisis). NUNCA crea skills automáticamente
— la decisión se reporta al Líder, que aprueba la creación.

## Firmas por sombrero 🤠

Cada video procesado se firma según el tema detectado:

| Tema | Firma |
|------|-------|
| agropecuario | 🐄 |
| h2o | 💧 |
| trading | 📈 |
| default / otro | 🔧 |
