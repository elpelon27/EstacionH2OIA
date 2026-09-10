# OpenNotebook "Content too large" — Diagnóstico profundo + Fix (2026-09-10)

## TL;DR — Causa raíz

El modelo NO es el problema. Gemini 3.1 Pro Preview vía OpenRouter aceptó en pruebas
directas hasta 975k tokens sin error. El problema es el **camino "full content" del
context builder**: cuando un chat del notebook incluye un source con estado
`full content`, OpenNotebook pasa el `full_text` COMPLETO al LLM. Los libros de la
biblioteca tienen hasta 3M chars (~975k tokens); uno solo ya roza el límite, y
sumado a insights + prompt + historial dispara el error 400 de OpenRouter:

```
This endpoint's maximum context length is 1048576 tokens.
However, you requested about 1319661 tokens (1318811 of text input, 850 in the output).
```

`error_classifier.py` traduce cualquier error que contenga "context length" /
"token limit" / "max_tokens" al mensaje genérico **"Content too large for the
selected model"** — por eso el Líder veía "Content too large" aunque el modelo
tuviera 1M de contexto.

## Config encontrada (viva, verificada 2026-09-10)

- Config de modelos NO está en `.env` del contenedor: vive en **SurrealDB**
  (tabla `model`, record `open_notebook:default_models`), coherente con el skill.
- Modelos: `google/gemini-3.1-pro-preview` (openrouter, language) = default chat,
  tools, transformation Y large_context. Embeddings: ollama `nomic-embed-text`.
- Credencial openrouter presente en tabla `credential` (api_key encriptada
  con OPEN_NOTEBOOK_ENCRYPTION_KEY, llega bien al contenedor).
- Model instantiation live: `OpenRouterLanguageModel(base_url=https://openrouter.ai/api/v1,
  model_name='google/gemini-3.1-pro-preview', max_tokens=850, temperature=1.0)`.
  El `max_tokens=850` es de SALIDA; no es la causa.
- Chunking: CHUNK_SIZE=400, CHUNK_OVERLAP=60 (chars/tokens de chunk de embedding).
  Chunks reales: min 29, max 1730, avg ~1031 chars.
- Env del contenedor: solo `OLLAMA_API_BASE`, `TIKTOKEN_CACHE_DIR`, `API_HOST` +
  vars SurrealDB/compose. NO hay vars de retrieval/max chunks en env.
- NO existe config `max_chunks` ni `top_k` en el código de OpenNotebook; la
  búsqueda vectorial (`fn::vector_search`) usa top 10 resultados de chunks.

## Tests directos del modelo (vía el propio stack esperanto de OpenNotebook)

| Prompt | Resultado |
|---|---|
| "hola" | OK |
| ~20k tokens | OK |
| ~60k tokens | OK |
| ~150k tokens | OK |
| full_text real 3.0M chars (975k tokens) | OK |
| 5M chars (~1.3M tokens) | FALLO 400 "maximum context length is 1048576 tokens" → exactamente el error que produce "Content too large" |

## Datos del notebook (notebook:edp1yex9eud1m2zd4hm6 "Biblioteca H2O")

- 459 sources con full_text, total 109M chars (~27M tokens).
- Top: "Food Chemistry" 3.0M chars, "El Rumiante" 2.4M chars, "Nutrient
  Requirements of Dairy Cattle" 2.1M chars.
- Contexto default (sin context_config): 460 sources "short" = **21,383 tokens** — sano.
- Insights: 0 registros. Notes: 1.
- Caminos de contexto:
  - Default (short): id+title+insights por source → pequeño, OK.
  - "full content" (long): **id+title+insights+FULL_TEXT completo** → el culpable.
  - source_chat: trunca full_text a 5000 chars → sano.
  - vector_search: top-10 chunks de ~1000 chars → pequeño, OK.

## Fix aplicado

La imagen es prebuilt (`lfnovo/open_notebook:v1-latest`), /app NO está montado.
Fix vía bind-mount de un solo archivo parcheado:

- `infra/open-notebook/patches/context_builder.py` — copia parcheada de
  `/app/open_notebook/utils/context_builder.py` (original respaldado en
  `patches/context_builder.py.orig`).
- `infra/open-notebook/docker-compose.yml` — mount `:ro` del parche sobre
  `/app/open_notebook/utils/context_builder.py`.

Parche: en `build_notebook_context`, constante `MAX_NOTEBOOK_CONTEXT_TOKENS = 800_000`.
En las ramas "full content" (sources y notes) se calcula
`token_count(total_content + str(context))` antes de incluir; si excede el cap,
el ítem se skipea con warning "Skipping source X: would exceed ... context cap".
800k deja ~248k de margen para system prompt + historial + salida vs el límite
duro de 1,048,576 tokens del endpoint.

## Verificación en vivo (post-fix)

- Contenedor recreado con el mount (grep `MAX_NOTEBOOK_CONTEXT_TOKENS` = 5 hits en
  /app del contenedor).
- `build_notebook_context(nb, None)` → 460 sources, 21,383 tokens (idéntico al
  pre-fix; sin regresión).
- `build_notebook_context(nb, {'sources': {'6wm93lh88dmplulq5v60': 'full content'}})`
  → 0 sources incluidos, 0 tokens: el source de 975k tokens se skipea con warning
  en vez de tumbar el request.
- Worker surreal-commands: RUNNING tras el recreate, backlog vacío.
- API `/docs`: HTTP 200.

## Pendientes / notas

- La reducción de "max chunks a 3" que menciona el Líder no corresponde a ningún
  setting real de OpenNotebook (no existe ese control); el problema era el
  camino "full content", ya tapado.
- Si en el futuro se quiere contexto full de un libro gigante, las opciones son:
  (a) subir el cap (parche), (b) dividir el libro en sources menores, o
  (c) confiar en vector_search (top-10 chunks) en vez de "full content".
- El skill `mlops/open-notebook` fue actualizado con estos hallazgos.
- Rollback del fix: quitar el volumen del compose y `docker compose up -d`;
  el original está en `patches/context_builder.py.orig`.
