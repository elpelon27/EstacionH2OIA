# Referencia — Recursos del servidor (comandos verificados 2026-10-09)

> Compartidos con el skill `ingeniero-agronomo` (misma biblioteca H2O).
> Mapa de fuentes (del más rápido al más profundo): hechos → Qdrant →
> Open Notebook → PDF original.

## 1. Hechos extraídos (siempre primero)

```bash
# por tema (sinónimos: lecheria|leche|cebú|ganado|vacas|pastoreo...)
grep -il "destete\|toro\|vaca\|leche" /mnt/ssd_trabajo/hermes-agent/docs/biblioteca/*.md
```

## 2. Qdrant — búsqueda semántica

```bash
cd /mnt/ssd_trabajo/hermes-agent && venv/bin/python - <<'EOF'
import requests
# IMPORTANTE: probar 2-3 variantes de la consulta y quedarse con las mejores
query = "vacas lecheras cebú pastoreo tropical"
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
  en el payload) → abrir el original (sección 4) o el hecho en `docs/biblioteca/`.
- Verificar servicio: `curl -s http://localhost:6333/collections | jq`.

## 3. Open Notebook

```bash
curl -s http://localhost:5055/health          # {"status": "healthy"}
curl -s http://localhost:5055/api/search -X POST \
  -H 'Content-Type: application/json' \
  -d '{"query": "pastoreo racional vacas lecheras", "mode": "semantic"}'
```

- UI para el Líder: `http://localhost:8502`
- Open Notebook usa su propio índice (SurrealDB); NO confundirlo con Qdrant.

## 4. PDF original

### Paperless-ngx (`http://localhost:8001`, user `lider`, pass dev `biblioteca_h2o_change_me`)

```bash
curl -s -u lider:biblioteca_h2o_change_me \
  "http://localhost:8001/api/documents/?query=voisin" | jq '.results[] | {id, title}'
curl -s -u lider:biblioteca_h2o_change_me \
  http://localhost:8001/api/documents/<ID>/download/ -o /tmp/doc.pdf
```

### Archivo directo (SOLO LECTURA)

```bash
ls "/mnt/ssd_trabajo/biblioteca/pdfs/Agrop M&M/" | grep -i "ganado\|leche\|pasto"
```

Subcarpetas: `Agrop M&M/` (temáticos), `inbox/` (ingesta), `processed/`,
`failed/`. Nunca escribir fuera de `inbox/`.

## 5. Ollama — resumen/extracción local

```bash
curl -s http://localhost:11434/api/tags   # verificar modelos ANTES de usar
curl -s http://localhost:11434/api/generate -d '{
  "model": "qwen2.5:7b", "stream": false,
  "prompt": "Extrae los hechos clave, números y recomendaciones del texto (español, una línea cada uno):\n\n<TEXTO>"
}' | jq -r '.response'
```

Nombres de modelos cambian: verificar siempre con `/api/tags`.

## 6. Ingesta de PDF nuevo (escalado de conocimiento)

```bash
cp nuevo.pdf /mnt/ssd_trabajo/biblioteca/pdfs/inbox/
cd /mnt/ssd_trabajo/hermes-agent && venv/bin/python scripts/ingest_pdf.py --once
tail -20 logs/ingest.log
ls docs/biblioteca/ | grep <tema>   # el .md de hechos ya debe existir
```

Luego registrar la lección en `docs/zootecnista/aprendizajes.md` y tachar la
deuda en `docs/zootecnista/deudas-conocimiento.md`.

## 7. descarga-libros — cazar material público (deudas autónomas)

```bash
cd /mnt/ssd_trabajo/herramientas-libres/descarga-libros
python3 descarga_libros.py buscar "<tema, ej. girolando nutricion>"
python3 descarga_libros.py pedir "<título exacto>"
```

- Open Library (buscador) y archive.org (descargas) primero; Anna's Archive vía
  `annas-archive.is` (requiere AA_SECRET_KEY); Telegram Zlibrary como módulo.
- Nada de secuestros publicitarios (`annas-archive.gs` NO).
- Todo PDF conseguido → ingesta (sección 6) → aprendizaje registrado.

## 8. Bitácoras del Zootecnista

| Archivo | Contenido |
|---|---|
| `docs/zootecnista/aprendizajes.md` | una línea por lección: fecha + lección + fuente |
| `docs/zootecnista/deudas-conocimiento.md` | tema sin cobertura + material sugerido al Líder |

Crearlos si no existen (directorio `docs/zootecnista/` incluido).

## Cobertura actual de la biblioteca (orientativo, 2026-10)

**Fuerte:** pastoreo racional y lechería a pasto (Voisin, Zietsman, Savory),
forrajes tropicales (moringa, palma, nopal, caña, sorgo — incluida la cosecha
nordestina `nordeste_*`), suelos y bioinsumos (Restrepo, Primavesi, JADAM).

**Débil / probable deuda de Aristeo:** genética animal y mejoramiento (sumarios
DEP, heredabilidades por raza), razas específicas (Sindi/Sindi Nordestino,
Gir Leiteiro, Guzerat, Nelore — libros de la ABCZ/Embrapa), Jersey tropical,
Girolando, nutrición por requerimientos (NRC, BR-CORTE), reproducción/IATF,
calidad de canal. → registrar deudas y cazar material.
