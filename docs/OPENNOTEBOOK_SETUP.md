# OpenNotebook — Setup Biblioteca H2O

Estado: OPERATIVO · 2026-09-03
UI: http://localhost:8502 · API: http://localhost:5055 (localhost only)

## Arquitectura final

```
[428 PDFs procesados]                        [Hermes pipeline (intacto)]
 /mnt/ssd_trabajo/biblioteca/pdfs/processed/  → OCR/Qdrant biblioteca_h2o (57.822 pts)
        │
        │ import único (PyMuPDF texto completo → API /api/sources/json)
        ▼
[OpenNotebook stack (Docker)]
  opennotebook_web (lfnovo/open_notebook:v1-latest)
    :5055 API FastAPI | :8502 UI web
  opennotebook_surrealdb (surrealdb/surrealdb:v2, :8002 interno)
    - sources + source_embedding (chunks + vectores 768d)
        │                                     ▲
        │ consulta "pastoreo rotacional"      │ RAG: chunks reales
        ▼                                     │
[Líder ← navegador :8502] → [DeepSeek V4 Flash vía OpenRouter]
                             $0.14/$0.28 por 1M tokens (~$0.0002/consulta)
```

## NOTA DE ARQUITECTURA (decisión del Líder, 2026-09-03)

OpenNotebook NO consulta Qdrant — su búsqueda vectorial vive en SurrealDB
(fn::vector_search sobre source_embedding, verificado en el código fuente).
En lugar de forkear OpenNotebook (cirugía mayor, se rompe en cada upgrade):
- Los PDFs se importaron como sources con TEXTO COMPLETO
- Re-embebidos con el MISMO modelo que Qdrant: nomic-embed-text
  (Ollama local, 768 dim) — vectores semánticamente equivalentes, costo $0
- Qdrant biblioteca_h2o queda INTACTO como índice maestro del pipeline Hermes
- No hay duplicación de PDFs: OpenNotebook guarda texto, no archivos

## Configuración aplicada

### Modelos (guardados en SurrealDB vía API :5055)

| Rol | Modelo | Provider | Verificado |
|---|---|---|---|
| default_chat_model | deepseek/deepseek-v4-flash | openrouter | ✅ test OK |
| default_transformation_model | deepseek/deepseek-v4-flash | openrouter | ✅ |
| default_tools_model | deepseek/deepseek-v4-flash | openrouter | ✅ |
| large_context_model | deepseek/deepseek-v4-flash | openrouter | ✅ |
| default_embedding_model | nomic-embed-text | ollama (local) | ✅ 768 dim |

Nombre exacto del modelo verificado en openrouter.ai/api/v1/models:
`deepseek/deepseek-v4-flash` (NO existe "deepseek-chat-v4-flash").

### Credenciales

- credential openrouter: guardada en SurrealDB (encriptada con
  OPEN_NOTEBOOK_ENCRYPTION_KEY). API key NO en el repo.
- credential ollama: http://host.docker.internal:11434 (preexistente).

### Contenedores (preexistentes de sesión anterior)

```
opennotebook_web        → 127.0.0.1:5055 (API) + 127.0.0.1:8502 (UI)
opennotebook_surrealdb  → 127.0.0.1:8002
data: /mnt/ssd_trabajo/biblioteca/open-notebook/notebook_data (SSD)
repo de referencia: /mnt/ssd_trabajo/repos/open-notebook
```

## Cómo consultar (Líder)

1. Abrir http://localhost:8502 → notebook "Biblioteca H2O"
2. Buscar (ícono lupa) → búsqueda vectorial sobre los 428 libros
3. Chat con notebook: pregunta en lenguaje natural → DeepSeek sintetiza
   citando los libros reales
4. Vía API (para scripts):
   ```
   curl -X POST http://127.0.0.1:5055/api/search \
     -d '{"query":"pastoreo rotacional","type":"vector","limit":10}'
   ```

## Comparativa Qwen vs DeepSeek

Ver docs/opennotebook_vs_qwen.md — DeepSeek gana en citas reales, precisión
y no alucina; Qwen local afirmó hablar "según los libros indexados" sin
haberlos visto. Decisión del Líder confirmada con evidencia.

## Costos

- DeepSeek V4 Flash: $0.14/$0.28 por 1M tokens (input/output)
- Consulta RAG compleja medida: $0.000196 → ~5.000 consultas por dólar
- Embeddings: $0 (nomic-embed-text local)
- Estimado primer mes con uso intensivo (<100 consultas/día): < $1

## Seguridad

- OpenNotebook NO modifica Qdrant: solo lee su propia SurrealDB
  (verificado: biblioteca_h2o sigue en 57.822 puntos, sin colecciones nuevas)
- API/UI bindeadas a 127.0.0.1 (no expuestas a la red)
- Sin OPEN_NOTEBOOK_PASSWORD → API sin auth PERO solo accesible desde localhost
- Cache/data en SSD: /mnt/ssd_trabajo/biblioteca/open-notebook/notebook_data
- PDFs originales NO duplicados

## Mantenimiento

- Nuevos PDFs: el pipeline Hermes (ingest_pdf.py) sigue indexando en Qdrant.
  Para que aparezcan en OpenNotebook: re-ejecutar
  /mnt/ssd_trabajo/open-notebook-import/import_biblioteca.py
  (retoma desde import_state.json, importa solo los nuevos)
