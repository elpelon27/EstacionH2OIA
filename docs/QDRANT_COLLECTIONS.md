# Qdrant — Colecciones de Memoria Vectorial

**Última actualización:** 2026-09-09 (datos verificados en vivo contra Qdrant en localhost:6333)
**Autor:** Prometeo
**Repo:** github.com/elpelon27/EstacionH2OIA (rama feat/odoo-r4-integration)

Servidor Qdrant local (`http://localhost:6333`). Todas las cifras de puntos fueron
obtenidas con `GET /collections/<nombre>` el 2026-09-09 — no de reportes previos.

## Resumen

| Colección | Puntos | Dim | Distancia | Propósito |
|---|---|---|---|---|
| `biblioteca_h2o` | 57.822 | 768 | Cosine | Biblioteca documental (chunks de docs OCR) |
| `hermes_memory` | 402 | 768 | Cosine | Memoria semántica del agente (SOUL v2.1) |
| `videos_h2o` | 4 | 768 | Cosine | Transcripts de videos YouTube indexados |
| `mem0migrations` | 0 | 1536 | Cosine | Colección interna de mem0 (migraciones) |

## Detalle por colección

### `biblioteca_h2o` — 57.822 pts
Biblioteca documental de Estación H2O. Chunks de documentos procesados con OCR.
- Payload: `chunk` (texto), `doc_id`, `file`, `ocr`, `pages`, `source`
- Embeddings: 768d (nomic-embed-text vía Ollama)
- Es la colección de mayor volumen; origen: pipeline de ingesta de documentos
  (`docs/02-arquitectura/` para el pipeline completo).

### `hermes_memory` — 402 pts
Memoria semántica del agente Hermes (SOUL v2.1, capa semántica).
- Payload: `chunk`, `created_at`, `data`, `hash`, `kind`, `source`, `title`,
  `updated_at`, `user_id`
- Origen: skill `indexados-memoria` (ingesta de docs .md → mem0 + Qdrant)

### `videos_h2o` — 4 pts
Transcripts de videos YouTube indexados (pipeline video-knowledge-ingestion).
- Payload: `chunk`, `duration_sec`, `indexed_at`, `tema`, `title`,
  `transcript_chunk_id`, `url`, `video_id`
- Ejemplo verificado: video `yt-_igtBYf0CMY` re-procesado 2026-09-05 (4 puntos,
  duration 140s).

### `mem0migrations` — 0 pts (dim 1536)
Colección interna creada por mem0 para tracking de migraciones de su propia DB.
- No contiene datos del negocio; los 1536d corresponden al embedding provider por
  defecto de mem0 (OpenAI), no al nomic-embed-text (768d) local.
- Documentada aquí por D12 (antes aparecía en el servidor sin explicación).
- Acción esperada: sin mantenimiento manual. Si se elimina, mem0 la recreará.

## Notas operativas

- Verificación de conteo (usar siempre, no reportes viejos):
  `curl -s http://localhost:6333/collections/<name>` → `result.points_count`
- Umbral TurboVec (>5000 pts) aplica solo a `biblioteca_h2o`.
- El threshold de graph memory (500+ transacciones) usa `fs_pedidos` (SQLite), no Qdrant.

💧