# Referencia — Recursos del servidor (comandos verificados 2026-10-08)

## Mapa de fuentes (del más rápido al más profundo)

1. **Hechos extraídos** — `/mnt/ssd_trabajo/hermes-agent/docs/biblioteca/*.md`
   (resúmenes ya procesados de cada PDF; consulta por grep, costo ~0).
2. **Qdrant `biblioteca_h2o`** — búsqueda semántica sobre todos los PDFs.
3. **Open Notebook** — chat conversacional con los docs ingeridos (UI/API).
4. **PDF original** — Paperless-ngx o el archivo en `/mnt/ssd_trabajo/biblioteca/pdfs/`.

## 1. Hechos extraídos (siempre primero)

```bash
# por tema (agregar sinónimos: compost|abono|biofertilizante|humus...)
grep -il "pastoreo\|potrero\|carga animal" /mnt/ssd_trabajo/hermes-agent/docs/biblioteca/*.md
```

## 2. Qdrant — búsqueda semántica

```bash
cd /mnt/ssd_trabajo/hermes-agent && venv/bin/python - <<'EOF'
import requests
# IMPORTANTE: probar 2-3 variantes de la consulta y quedarse con las mejores
query = "biofertilizantes fermentados suelo tropical"
q = requests.post("http://localhost:11434/api/embed",
    json={"model": "nomic-embed-text", "input": [query]}).json()["embeddings"][0]
r = requests.post("http://localhost:6333/collections/biblioteca_h2o/points/search",
    json={"vector": q, "limit": 8, "with_payload": True})
for p in r.json()["result"]:
    print(round(p["score"], 3), "|", p["payload"].get("file"), "|",
          str(p["payload"].get("text", p["payload"].get("chunk", "")))[:300])
EOF
```

- Score > 0.75 suele ser relevante; entre 0.6-0.75 revisar con calma.
- El payload trae `file` SIEMPRE; `text`/`chunk` a veces vienen vacíos → abrir
  el original (sección 4).
- Verificar servicio: `curl -s http://localhost:6333/collections | jq`.

## 3. Open Notebook

```bash
curl -s http://localhost:5055/health          # {"status": "healthy"}
curl -s http://localhost:5055/api/search -X POST \
  -H 'Content-Type: application/json' \
  -d '{"query": "pastoreo rotacional", "mode": "semantic"}'
```

- UI para el Líder: `http://localhost:8502`
- Open Notebook usa su propio índice (SurrealDB); NO confundirlo con Qdrant,
  que es el índice del pipeline Hermes. Si la API no tiene el doc, Qdrant sí puede.

## 4. PDF original

### Paperless-ngx (`http://localhost:8001`, user `lider`, pass dev `biblioteca_h2o_change_me`)

```bash
# buscar
curl -s -u lider:biblioteca_h2o_change_me \
  "http://localhost:8001/api/documents/?query=primavesi" | jq '.results[] | {id, title}'
# descargar
curl -s -u lider:biblioteca_h2o_change_me \
  http://localhost:8001/api/documents/<ID>/download/ -o /tmp/doc.pdf
```

### Archivo directo (SOLO LECTURA)

```bash
ls "/mnt/ssd_trabajo/biblioteca/pdfs/Agrop M&M/" | grep -i "suelo"
```

Subcarpetas: `Agrop M&M/` (temáticos), `inbox/` (ingesta), `processed/`,
`failed/`. Nunca escribir fuera de `inbox/`.

## 5. Ollama — resumen/extracción local

```bash
curl -s http://localhost:11434/api/tags   # verificar modelos disponibles ANTES de usar
curl -s http://localhost:11434/api/generate -d '{
  "model": "qwen2.5:7b", "stream": false,
  "prompt": "Extrae los hechos clave, dosis y recetas del texto (español, una línea cada uno):\n\n<TEXTO>"
}' | jq -r '.response'
```

Modelos vistos 2026-10-08: `qwen2.5:7b` (calidad), `qwen2.5:3b` (rápido),
`qwen3.6:35b` (máximo), `nomic-embed-text` (embeddings), `veloz`/`nocturno`
(perfiles locales). Los nombres cambian: verificar siempre.

## 6. Ingesta de PDF nuevo (escalado de conocimiento)

```bash
cp nuevo.pdf /mnt/ssd_trabajo/biblioteca/pdfs/inbox/
cd /mnt/ssd_trabajo/hermes-agent && venv/bin/python scripts/ingest_pdf.py --once
tail -20 logs/ingest.log
ls docs/biblioteca/ | grep <tema>   # el .md de hechos ya debe existir
```

Luego registrar la lección en `docs/agronomo/aprendizajes.md` y tachar la
deuda en `docs/agronomo/deudas-conocimiento.md`.

## 7. Bitácoras del Ingeniero Agrónomo

| Archivo | Contenido |
|---|---|
| `docs/agronomo/aprendizajes.md` | una línea por lección: fecha + lección + fuente |
| `docs/agronomo/deudas-conocimiento.md` | tema sin cobertura + material sugerido al Líder |

Crearlos si no existen (directorio `docs/agronomo/` incluido).

## Cobertura actual de la biblioteca (orientativo, 2026-10)

**Fuerte:** ganadería tropical a pastoreo (Voisin, Zietsman, Savory, rumen,
lechería), suelos vivos y agroecología (Restrepo, Primavesi, compost,
biofertilizantes, lombricultura, cromatografía), agua/paisaje (Yeomans Keyline,
Eugenio Gras), forrajes tropicales (moringa, palma, nopal, caña, yuca, sorgo),
JADAM/control biológico, permacultura, ILPF/agroforestería.

**Débil / probable deuda:** horticultura intensiva regenerativa, agricultura de
precisión, ovinos específicos (la mayoría del material es bovino de leche),
postcosecha sin frío, cereales tropicales, sanidad ovina.
