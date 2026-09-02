---
name: biblioteca-guru
description: Consultar la biblioteca de PDFs del Líder (ganadería, agricultura regenerativa, preservación de tierras, trading) vía Open-Notebook, Paperless-ngx y Qdrant. Usar cuando el usuario pregunte "¿qué dicen los libros sobre X?" o pida extracción/cruce de conocimiento de la biblioteca.
version: 1.0.0
---

# Biblioteca Guru 💧

Pipeline de conocimiento de la Biblioteca H2O:

- **PDFs originales:** `/mnt/ssd_trabajo/biblioteca/pdfs/` (solo lectura; subcarpetas por tema)
- **Inbox de ingesta:** `/mnt/ssd_trabajo/biblioteca/pdfs/inbox/` — depositar PDFs nuevos aquí
- **Paperless-ngx (DMS):** `http://localhost:8001` — user `lider`, pass `biblioteca_h2o_change_me`
- **Open-Notebook (chat con docs):** UI `http://localhost:8502` — API `http://localhost:5055`
- **Qdrant:** `http://localhost:6333` — colección `biblioteca_h2o` (embeddings nomic-embed-text)
- **Ollama (Qwen local):** `http://localhost:11434` — modelo por defecto `qwen2.5:3b` (factores: qwen2.5:7b para más calidad)
- **Hechos extraídos:** `docs/biblioteca/*.md`
- **Log de ingesta:** `logs/ingest.log`

## Procedimientos

### a) Consultar Open-Notebook — "¿Qué dicen los libros sobre X?"

1. Verificar servicio: `curl http://localhost:5055/health` → `{"status": "healthy"}`
2. Búsqueda semántica vía API (si el notebook ya ingirió los docs):
   ```bash
   curl -s http://localhost:5055/api/search -X POST \
     -H 'Content-Type: application/json' \
     -d '{"query": "pastoreo rotacional", "mode": "semantic"}'
   ```
3. Alternativa directa por Qdrant (no depende de la UI de Open-Notebook):
   ```bash
   venv/bin/python - <<'EOF'
   import requests
   q = requests.post("http://localhost:11434/api/embed",
       json={"model": "nomic-embed-text", "input": ["pastureo rotacional vacunos"]}).json()["embeddings"][0]
   r = requests.post("http://localhost:6333/collections/biblioteca_h2o/points/search",
       json={"vector": q, "limit": 8, "with_payload": True})
   for p in r.json()["result"]:
       print(p["score"], p["payload"]["file"], "\n", p["payload"].get("text", p["payload"].get("chunk", ""))[:300], "\n---")
   EOF
   ```
   (usar el venv del proyecto: `/mnt/ssd_trabajo/hermes-agent/venv`)

### b) Buscar en Paperless-ngx — tags, fechas, autores

```bash
# Login implícito con basic auth; buscar por título/contenido
curl -s -u lider:biblioteca_h2o_change_me \
  "http://localhost:8001/api/documents/?query=yuca" | jq '.results[] | {id, title, created, tags}'
# Tags / correspondents / document types
curl -s -u lider:biblioteca_h2o_change_me http://localhost:8001/api/tags/ | jq
# Descargar el archivo original
curl -s -u lider:biblioteca_h2o_change_me \
  http://localhost:8001/api/documents/<ID>/download/ -o /tmp/doc.pdf
```
OCR en español ya configurado (`PAPERLESS_OCR_LANGUAGE=spa`).

### c) Extracción de hechos — Qwen resume capítulo/documento

1. Descargar el PDF de Paperless (procedimiento b) o usar el original en `pdfs/`.
2. Extraer texto: `venv/bin/python -c "from pypdf import PdfReader; print('\n'.join((p.extract_text() or '') for p in PdfReader('doc.pdf').pages))" > /tmp/doc.txt`
3. Resumen/hechos con Qwen local:
   ```bash
   curl -s http://localhost:11434/api/generate -d '{
     "model": "qwen2.5:7b", "stream": false,
     "prompt": "Extrae los hechos clave y técnicas del texto (máx 20, en español, una línea cada uno):\n\n<TEXTO CAPÍTULO>"}' | jq -r '.response'
   ```
   Para capítulos largos, procesar por secciones de ~12k chars.

### d) Análisis profundo — GLM 5.3 Max cruza fuentes

1. Reunir hechos ya extraídos de `docs/biblioteca/*.md` relevantes al tema (grep por palabras clave).
2. Realizar búsquedas semánticas en Qdrant con 2-3 variantes de la consulta.
3. Presentar los fragmentos + hechos consolidados al modelo de análisis profundo
   (GLM 5.3 Max vía OpenRouter — el propio Hermes lo usa como provider) pidiendo:
   síntesis cruzada, contradicciones entre fuentes, y recomendaciones accionables
   con citas (archivo + página/chunk).
4. SIEMPRE citar fuente por cada afirmación: `[archivo.pdf, chunk N]` o `[archivo.pdf, pág. N]`.

### e) Ingesta de nuevos PDFs

```bash
cp nuevo.pdf /mnt/ssd_trabajo/biblioteca/pdfs/inbox/
cd /mnt/ssd_trabajo/hermes-agent && venv/bin/python scripts/ingest_pdf.py --once
# o modo watcher (daemon): venv/bin/python scripts/ingest_pdf.py
```
Ver resultado en `logs/ingest.log` y `docs/biblioteca/`.

## Integración con AgroScout (FASE FUTURA)

Consultas tipo "¿Qué técnicas de pastoreo rotacional recomiendan los libros para Maracaibo?":
1. Búsqueda semántica Qdrant: "pastoreo rotacional", "manejo de pasturas tropicales", "carga animal trópico".
2. Hechos de `docs/biblioteca/` filtrados por keywords.
3. Filtrar por aplicabilidad al clima de Maracaibo (bosque seco tropical, ~40°C).
4. Cruce con GLM 5.3 Max citando cada fuente.
5. Entregar recomendación al pipeline AgroScout como JSON estructurado
   (técnica, fuente, condiciones locales).

## Pitfalls

- **Paperless consume y MUEVE lo que está en `pdfs/inbox/`** tras ingesta. Los originales temáticos (subcarpetas) NO se tocan; nunca apuntar el consumption dir a `pdfs/` raíz.
- **PDFs escaneados sin tesseract** → ocrmypdf falla. Requiere `sudo apt install tesseract-ocr tesseract-ocr-spa` (pendiente de sudo en el host).
- **Colección de Qdrant `biblioteca_h2o`**: la crea `ingest_pdf.py` automáticamente si no existe.
- **Open-Notebook usa SurrealDB internamente**, no Qdrant; Qdrant es el índice del pipeline Hermes, Open-Notebook tiene el suyo propio tras ingerir docs por su UI.
- **Modelos Ollama disponibles:** qwen2.5:3b (rápido), qwen2.5:7b / qwen7b-pro (calidad). No existe "Qwen 4B" literal.
- Credenciales dev en este skill (`biblioteca_h2o_change_me`, etc.) — rotar antes de exponer puertos fuera de 127.0.0.1.
