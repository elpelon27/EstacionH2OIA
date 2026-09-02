# WORKLOG — Coverage src/orchestration/
## 2026-08-17 | Piloto Automatico GLM 5.2

### OBJETIVO
Cubrir 3 modulos de src/orchestration/ que estaban a 0% coverage.
Objetivo: >60% en cada modulo.

### RESULTADOS

| Modulo | Antes | Despues | Tests |
|--------|-------|---------|-------|
| orchestrator.py | 0% | **97%** | 41 |
| memory_aware_agent.py | 0% | **99%** | 46 |
| external_skills.py | 0% | **70%** | 35 |
| skill_registry.py | 33% | 33%* | 32 (ya existente) |
| **TOTAL orchestration/** | **0%** | **~75%** | **122 nuevos** |

*skill_registry.py ya tenia 32 tests del commit anterior (test_orchestration_coverage.py).
El 33% reportado es solo con los nuevos tests de este directorio; con el test
archivo anterior el coverage real es mayor.

### ARCHIVOS CREADOS
- tests/unit/orchestration/conftest.py — fixtures mock_memory y mock_orchestrator
- tests/unit/orchestration/test_orchestrator.py — 41 tests
- tests/unit/orchestration/test_memory_aware_agent.py — 46 tests
- tests/unit/orchestration/test_external_skills.py — 35 tests

### VERIFICACION
- pytest tests/unit/orchestration/: 122 passed, 0 failures
- pytest tests/ (suite completa): 840 passed, 14 skipped, 0 failures
- mypy src/orchestration/: 0 errores en 5 archivos
- Coverage core/: 61%

### BUG DETECTADO (no arreglado)
Handoff recursion en memory_aware_agent.py:
- FinancialAgent -> ValentinaAgent (keyword "whatsapp")
- ValentinaAgent -> FinancialAgent (keyword "factura")
- Un mensaje con ambos keywords causa recursion infinita
- El keyword matching es orden-dependiente y no tiene proteccion anti-recursion
- Reportado en el commit message. NO arreglado sin autorizacion.

### METRICAS DE SUITE
- Tests: 718 -> 840 (+122)
- Coverage orchestration/: 0% -> ~75%
- Coverage total repo: subio (36% -> mayor, medible con --cov completo)
- mypy: 0 errores
- 0 failures

### COMMIT
e3c549a test(orchestration): 122 tests para 3 modulos (0% -> 70-99%)

---
Generado por Prometeo en piloto automatico — GLM 5.2 via OpenRouter. 💧

## 2026-09-01 | Pipeline Biblioteca H2O (Paperless + OCRmyPDF + Open-Notebook + Qdrant)

### OBJETIVO
Ingesta de conocimiento de la biblioteca de PDFs del Líder (ganadería, agricultura
regenerativa, preservación de tierras, trading): DMS + OCR + chat con docs +
extracción de hechos local + análisis profundo.

### ARQUITECTURA DESPLEGADA
- **Paperless-ngx** (Docker, infra/paperless/): web 127.0.0.1:8001, broker Redis
  dedicado, PostgreSQL 16 dedicado. OCR spa. Admin: lider / biblioteca_h2o_change_me
- **OCRmyPDF 17.11** en venv del proyecto (falta tesseract → sudo pendiente)
- **Open-Notebook** (Docker, infra/open-notebook/): UI 127.0.0.1:8502 (200 OK),
  API 127.0.0.1:5055 (healthy). SurrealDB interno. LLM vía Ollama host
  (host.docker.internal:11434) — configurar provider Qwen desde la UI.
- **Qdrant existente** (hermes_qdrant:6333): colección nueva `biblioteca_h2o`
  (embeddings nomic-embed-text, 768d, cosine), creada por el pipeline.
- **Pipeline**: scripts/ingest_pdf.py (watcher inbox / --once / --scan / --dry-run)
- **Skill**: skills/biblioteca-guru/SKILL.md (procedimientos de consulta)

### VERIFICACIÓN CON DATOS REALES (E2E)
- MANEJO Y CONSERVACION DE LA YUCA.pdf: 94 págs → Paperless doc_id
  e8679f2e-...; Qdrant 67 chunks; 20 hechos Qwen → docs/biblioteca/manejo-y-conservacion-de-la-yuca.md
- VARIEDADES YUCA PARA USO AGROINDUSTRIAL.pdf: 50 págs → doc_id 479ea887-...;
  29 chunks; 10 hechos → docs/biblioteca/variedades-yuca-para-uso-agroindustrial.md
- Qdrant biblioteca_h2o: 67+29=96 puntos, status green
- Paperless GET /api/documents/: 2 docs indexados (94 y 50 páginas)
- Open-Notebook GET /health: {"status":"healthy"}, UI 200
- Dry-run sobre YUCA/: 10/11 PDFs con texto OK; 1 escaneado (Siembra-Variedad
  yuca forrajera) requiere tesseract (sudo -S -p '' pendiente)

### BUG ENCONTRADO Y CORREGIDO (E2E)
Consume dir de Paperless apuntaba a pdfs/inbox → Paperless MOVÍA el PDF antes
que el pipeline (carrera doble consumidor). Corregido: Paperless consume SOLO de
biblioteca/paperless-consume/; ingest_pdf.py es dueño exclusivo de pdfs/inbox/.
Además move_to() ahora tolera archivos ya movidos.

### SUDO PENDIENTE (Líder)
- sudo apt install tesseract-ocr tesseract-ocr-spa  (OCR de escaneados)

### NOTAS
- No existe "Qwen 4B" literal en Ollama; se usa qwen2.5:3b (default) y
  qwen2.5:7b (calidad). Cambiar con --model.
- Open-Notebook usa SurrealDB propio; Qdrant es el índice del pipeline Hermes.
- Credenciales dev en infra/*: rotar antes de exponer fuera de 127.0.0.1.
- /mnt/ssd_trabajo/biblioteca → symlink a /mnt/ssd_trabajo/Biblioteca (spec pedía minúscula).

## 2026-09-01 (cierre) | Bloqueos resueltos por el Líder
- tesseract-ocr 5.3.4 + spa instalados → OCR E2E verificado:
  "Siembra-Variedad de yuca forrajera" (2 págs, escaneado) → ocrmypdf spa →
  Paperless doc_id c6727a50 → Qdrant 1 chunk → 6 hechos (43k plantas/ha,
  35-85 t/ha/año) → docs/biblioteca/siembra-variedad-...md
- Open-Notebook configurado (verificado vía API /api/models):
  credential Ollama host.docker.internal:11434, modelos qwen2.5:7b y
  qwen2.5:3b registrados. Pipeline 100% operativo, sin bloqueos.

## 2026-09-02 | Hardening SSD-first del pipeline de ingesta
- TMPDIR/TMP/TEMP → /mnt/ssd_trabajo/biblioteca/.tmp (antes de imports; vale desde cron)
- HF_HOME/TRANSFORMERS_CACHE/TORCH_HOME → /mnt/ssd_trabajo/skynet_cache (refuerzo del symlink)
- ocrmypdf con --temp-dir al SSD (OCR temporales fuera del disco raíz)
- RotatingFileHandler en ingest.log (10 MB x 5 backups)
- Qdrant verificado: bind mount Docker → /mnt/ssd_trabajo/qdrant/storage (158M, ya en SSD; no usa /var/lib)
- Procesos ingest/tesseract/ocrmypdf: cero colgados
- Dry-run post-cambios OK (12 PDFs); script arranca limpio
- Cron nocturno en standby (NO activado, orden del Líder)
