# Referencia — Recursos del servidor (comandos verificados 2026-10-09)

> Compartidos con los skills `ingeniero-agronomo` y `zootecnista` (misma
> biblioteca H2O). Mapa de fuentes: hechos → Qdrant → Open Notebook → PDF
> original. LO NUEVO de Quirón: la cadena de Visión (sección 9).

## 1. Hechos extraídos (siempre primero)

```bash
grep -il "garrapata\|parasito\|mastitis\|diarrea\|vacuna" /mnt/ssd_trabajo/hermes-agent/docs/biblioteca/*.md
```

## 2. Qdrant — búsqueda semántica

```bash
cd /mnt/ssd_trabajo/hermes-agent && venv/bin/python - <<'EOF'
import requests
query = "verminosis bovina trópico garrapata control"
q = requests.post("http://localhost:11434/api/embed",
    json={"model": "nomic-embed-text", "input": [query]}).json()["embeddings"][0]
r = requests.post("http://localhost:6333/collections/biblioteca_h2o/points/search",
    json={"vector": q, "limit": 8, "with_payload": True})
for p in r.json()["result"]:
    print(round(p["score"], 3), "|", p["payload"].get("file"), "|",
          str(p["payload"].get("text", p["payload"].get("chunk", "")))[:300])
EOF
```

- Score > 0,75 relevante; 0,6-0,75 revisar. Payload trae `file` SIEMPRE y
  `chunk` = NÚMERO DE PÁGINA (no texto) → ir al original (§4) o al hecho.
- Verificar: `curl -s http://localhost:6333/collections | jq`.

## 3. Open Notebook

```bash
curl -s http://localhost:5055/health
curl -s http://localhost:5055/api/search -X POST -H 'Content-Type: application/json' \
  -d '{"query": "sanidad bovina trópico", "mode": "semantic"}'
```

UI del Líder: `http://localhost:8502`.

## 4. PDF original

Paperless-ngx (`http://localhost:8001`, user `lider`, pass dev `biblioteca_h2o_change_me`):

```bash
curl -s -u lider:biblioteca_h2o_change_me \
  "http://localhost:8001/api/documents/?query=parasitologia" | jq '.results[] | {id, title}'
curl -s -u lider:biblioteca_h2o_change_me \
  http://localhost:8001/api/documents/<ID>/download/ -o /tmp/doc.pdf
```

Archivo directo (SOLO LECTURA): `/mnt/ssd_trabajo/biblioteca/pdfs/Agrop M&M/`.
Escribir solo en `pdfs/inbox/`.

## 5. Ollama — resumen/extracción local

```bash
curl -s http://localhost:11434/api/tags   # verificar modelos ANTES de usar
curl -s http://localhost:11434/api/generate -d '{
  "model": "qwen2.5:7b", "stream": false,
  "prompt": "Resume en español, hechos y números:\n\n<TEXTO>"
}' | jq -r '.response'
```

## 6. Ingesta de PDF nuevo

```bash
cp nuevo.pdf /mnt/ssd_trabajo/biblioteca/pdfs/inbox/
cd /mnt/ssd_trabajo/hermes-agent && venv/bin/python scripts/ingest_pdf.py --once
tail -20 logs/ingest.log
```

Registrar aprendizaje en `docs/veterinario/aprendizajes.md` y tachar deuda.

## 7. descarga-libros

```bash
cd /mnt/ssd_trabajo/herramientas-libres/descarga-libros
python3 descarga_libros.py buscar "<título>"
```

## 8. Bitácoras y casos de Quirón

| Archivo | Contenido |
|---|---|
| `docs/veterinario/aprendizajes.md` | una línea: fecha + lección + fuente |
| `docs/veterinario/deudas-conocimiento.md` | tema sin cobertura + material sugerido |
| `docs/veterinario/casos/AAA-MM-DD-<tema>.md` | historia clínica: hallazgos, diferenciales, plan, evolución |

Crear directorios si no existen.

## 9. ⭐ Cadena de VISIÓN (exclusiva de Quirón, verificada 09-oct)

```bash
cd /mnt/ssd_trabajo/hermes-agent/skills/medico-veterinario

# Foto:
python3 vision.py imagen /ruta/foto.jpg --especie bovino -p "qué preocupa" \
  -o docs/veterinario/casos/$(date +%F)-caso.md
# Video (cuadros automáticos con ffmpeg):
python3 vision.py video /ruta/video.mp4 --especie bovino --max-cuadros 16
# JSON: --json · forzar offline: --local · otro modelo: --modelo z-ai/glm-4.6v
```

- Tier 1 API: `scripts/llm_client.py` con `task_type="video"` (env
  `OPENROUTER_MODEL_VIDEO`, default `google/gemini-3.1-pro-preview`; misma
  `OPENROUTER_API_KEY` de la casa). Probado 09-oct: foto de hato Nelore →
  informe semiológico completo (ECC, garrapatas-no-visibles-a-distancia,
  triage, anamnesis, plan) en ~1 min.
- Tier 2 local: Ollama `qwen2.5vl:3b` (instalado 09-oct) — CPU, LENTO
  (minutos por imagen); uso: offline/respaldo.
- Requisitos: ffmpeg/ffprobe en PATH; imagen ≤8 MB (re-escalar si no);
  videos: se muestrean cuadros equidistantes y se mandan con timestamps.
- Fallos API → cae automáticamente a local y lo reporta en `degradado_por`
  (con `--json`) o en stderr (texto).

## Cobertura de la biblioteca (orientativo, 2026-10)

**Fuerte**: pastoreo/forrajes tropicales, suelos, lechería a pasto (material
de Tripólemo y la cosecha nordestina `nordeste_*` — palma, leucena, sorgo,
ILPF; útil para nutrición, no para clínica).
**Débil / deudas esperadas de Quirón**: medicina interna bovina tropical,
parasitología clínica (garrapaticidas, resistencia), formularios de dosis,
calendarios sanitarios venezolanos, ovinos, aves de traspatio, porcinos,
mastitis, reproducción patológica, atlas de lesiones. → registrar deudas y
cazar con descarga-libros + ingesta.
