# Referencia — Recursos del servidor (comandos verificados 2026-10-10)

## Mapa de fuentes (del más rápido al más profundo)

1. **Hechos extraídos** — `/mnt/ssd_trabajo/hermes-agent/docs/biblioteca/*.md`
   (resúmenes ya procesados de cada PDF; consulta por grep, costo ~0).
2. **Qdrant `biblioteca_h2o`** — búsqueda semántica sobre todos los PDFs.
3. **Open Notebook** — chat conversacional con los docs ingeridos (UI/API).
4. **PDF original** — Paperless-ngx o el archivo en `/mnt/ssd_trabajo/biblioteca/pdfs/`.

## 1. Hechos extraídos (siempre primero)

```bash
# por tema (agregar sinónimos: liofiliza|secado|sublima|deshidrata...)
grep -il "compost\|biofertilizante\|ferment" /mnt/ssd_trabajo/hermes-agent/docs/biblioteca/*.md
grep -il "agua\|potab" /mnt/ssd_trabajo/hermes-agent/docs/biblioteca/*.md
```

## 2. Qdrant — búsqueda semántica

```bash
cd /mnt/ssd_trabajo/hermes-agent && venv/bin/python - <<'EOF'
import requests
# IMPORTANTE: probar 2-3 variantes de la consulta y quedarse con las mejores
query = "fermentacion anaerobia silaje ph"
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
- El payload trae `file` SIEMPRE y `chunk` = **número de página** (no hay texto
  en el payload: el índice es semántico) → abrir el original (sección 4) o el
  hecho en `docs/biblioteca/`.
- Verificar servicio: `curl -s http://localhost:6333/collections | jq`.

## 3. Open Notebook

```bash
curl -s http://localhost:5055/health          # {"status": "healthy"}
curl -s http://localhost:5055/api/search -X POST \
  -H 'Content-Type: application/json' \
  -d '{"query": "actividad de agua conservacion alimentos", "mode": "semantic"}'
```

- UI para el Líder: `http://localhost:8502`
- Open Notebook usa su propio índice (SurrealDB); NO confundirlo con Qdrant,
  que es el índice del pipeline Hermes. Si la API no tiene el doc, Qdrant sí puede.

## 4. PDF original

### Paperless-ngx (`http://localhost:8001`, user `lider`, pass dev `biblioteca_h2o_change_me`)

```bash
# buscar
curl -s -u lider:biblioteca_h2o_change_me \
  "http://localhost:8001/api/documents/?query=agua" | jq '.results[] | {id, title}'
# descargar
curl -s -u lider:biblioteca_h2o_change_me \
  http://localhost:8001/api/documents/<ID>/download/ -o /tmp/doc.pdf
```

### Archivo directo (SOLO LECTURA)

```bash
ls "/mnt/ssd_trabajo/biblioteca/pdfs/Agrop M&M/" | grep -i "agua\|compost"
```

Subcarpetas: `Agrop M&M/` (temáticos), `inbox/` (ingesta), `processed/`,
`failed/`. Nunca escribir fuera de `inbox/`.

## 5. Ollama — resumen/extracción local

```bash
curl -s http://localhost:11434/api/tags   # verificar modelos disponibles ANTES de usar
curl -s http://localhost:11434/api/generate -d '{
  "model": "qwen2.5:7b", "stream": false,
  "prompt": "Extrae los hechos clave, constantes y rangos del texto (español, una línea cada uno):\n\n<TEXTO>"
}' | jq -r '.response'
```

Modelos vistos 2026-10: `qwen2.5:7b` (calidad), `qwen2.5:3b` (rápido),
`qwen3.6:35b` (máximo), `nomic-embed-text` (embeddings), `veloz`/`nocturno`
(perfiles locales). Los nombres cambian: verificar siempre.
Nota de la casa: los qwen3.x son razonadores — con `invocar_nocturno.py`
usar `"think": false`.

## 6. Ingesta de PDF nuevo (escalado de conocimiento)

```bash
cp nuevo.pdf /mnt/ssd_trabajo/biblioteca/pdfs/inbox/
cd /mnt/ssd_trabajo/hermes-agent && venv/bin/python scripts/ingest_pdf.py --once
tail -20 logs/ingest.log
ls docs/biblioteca/ | grep <tema>   # el .md de hechos ya debe existir
```

Luego registrar la lección en `docs/quimico/aprendizajes.md` y tachar la
deuda en `docs/quimico/deudas-conocimiento.md`.

## 7. descarga-libros — cazar material público

```bash
cd /mnt/ssd_trabajo/herramientas-libres/descarga-libros/ && python3 descarga_libros.py --help
```

Open Library (buscador es-ES), archive.org (descargas), Anna's Archive
(AA_BASE en config.env; descargas tras login = pendiente clave). Pedido →
PDF → Telegram al Líder. Clásicos a cazar (misión bibliográfica): Geankoplis,
Treybal, Felder-Rousseau, Perry's, Crittenden (Water Treatment), Fellows
(Food Processing), WHO Guidelines for Drinking-water Quality.

## 8. Bitácoras del Ingeniero Químico

| Archivo | Contenido |
|---|---|
| `docs/quimico/aprendizajes.md` | una línea por lección: fecha + lección + fuente |
| `docs/quimico/deudas-conocimiento.md` | tema sin cobertura + material sugerido al Líder |
| `docs/quimico/preguntas-abiertas.md` | pregunta, por qué importa, plan de búsqueda, fecha |

Crearlos si no existen (directorio `docs/quimico/` incluido).

## Cobertura actual de la biblioteca (orientativo, 2026-10)

**Fuerte (aprovechable con lente de proceso):** compost/biofertilizantes
(Restrepo, cromatografía), forrajes tropicales y palma (misiones nordeste,
Embrapa), pastoreo/agua-paisaje (Yeomans Keyline, Gras), ILPF, agroecología.

**Débil / probable deuda (hasta que la misión bibliográfica llene):**
ingeniería de proceso formal (Perry's, Treybal, Geankoplis), liofilización,
actividad de agua/isotermas, HACCP, tratamiento y normativa del agua (OMS/
COVENIN/EPA), farmacotecnia (estabilidad, diluciones), energía off-grid,
digestores de biogás.
