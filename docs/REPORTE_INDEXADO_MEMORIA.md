# REPORTE — Indexado de Obsidian en Memoria Tripartita

**Fecha:** parcial — 2026-08-15
**Sistema:** Hermes Agent / Estación H2O
**Estado global:** ACTIVO Y FUNCIONAL

---

## 1) Resultado del indexado (tópico principal)

| Métrica | Valor |
|---|---|
| Archivos .md procesados | **78 / 78** |
| Archivos con vectores en Qdrant | **78 / 78** |
| Total de puntos (memorias) en `hermes_memory` | **389** |
| Puntos procedentes de mem0 (extracción LLM) | ~122 |
| Puntos añadidos por cobertura determinista | 226 |
| Dimensión de vectores | 768 (nomic-embed-text) |
| Distancia | COSINE |
| Tiempo total del indexado | ~56 min (extracción LLM) |
| Tiempo de la pasada de cobertura | 32 s |

**Scripts usados:**
- `scripts/index_obsidian.py` — indexado vía mem0 (procesó los 78, pero mem0 solo materializó puntos con `source` para 32; ver advertencia abajo).
- `scripts/ensure_coverage.py` — pasada determinista que incrusta cada chunk con nomic-embed-text y hace upsert directo a Qdrant con metadatos `source`/`title`. Esto garantizó los 78/78.
- `scripts/verify_final.py`, `count_coverage.py`, `audit_payload.py` — verificación.

---

## 2) Búsqueda semántica (funciona)

Se probó con 3 consultas reales contra la colección. Ejemplos:

- **"deuda técnica del proyecto"** → `FASE3_EXTERNAL_SKILLS_INTEGRATION.md` (0.78), `RESUMEN_RETOMAR.md` (0.72, 0.70)
- **"arquitectura de Estación H2O"** → `RESUMEN_RETOMAR.md` (0.83) y otros
- **"agentes de hermes"** → `HERMES_AGENT_SUPERPOWERS_ARCHITECTURE.md` (0.75), `FASE3_EXTERNAL_SKILLS_INTEGRATION.md` (0.71), `ROADMAP-plan.md` (0.70)

Resultado: la búsqueda semántica devuelve resultados relevantes con `source` y `score`.

---

## 3) Memoria tripartita — estado por capa

| Capa | Backend | Estado | Observación |
|---|---|---|---|
| **Capa 1** persistente de sesión | `state.db` (SQLite de Hermes) | OK | 3 sesiones, 335 mensajes |
| **Capa 2** memoria de trabajo / caché | Redis (6379) | OK (servicio) | dbsize bajo (uso mínimo) |
| **Capa 3** memoria vectorial / semántica | Qdrant (6333) `hermes_memory` vía mem0 | OK | 389 puntos, 78 archivos |

Los 3 contenedores están levantados y responden.

---

## ⚠️ Advertencias (transparencia)

1. **mem0 materializó solo 32 de 78 archivos** en la primera pasada.
   - Causa raíz: mem0 apoya su guardado en la extracción LLM de "memorias" (qwen2.5:7b en GTX 1070). En 64/99 add()s extrajo 0 memorias y hubo 26 errores internos (`new_retrieved_facts: 'facts'`). Además, **nomic-embed-text devuelve HTTP 500 para textos > ~2000-4000 chars** (contexto 2048 tokens), así que los chunks grandes fallaron al incrustar en silencio.
   - Solución aplicada: pasada determinista con chunks ≤ 3400 chars + upsert directo. Quedó **78/78**.
2. **mem0 v1.0.11** instalado (el reporte inicial citaba v2.0.18).
3. **ChromaDB NO está instalado ni corriendo** — se descartó por decisión del usuario; Qdrant cumple la capa 3.
4. El vault `obsidian/vault` es un **symlink a `/home/skynet/Documentos`** que contiene loops de symlink hacia `docs/`. El conjunto canónico (78 .md reales) se tomó de `docs/*` saltando `docs/obsidian`.

---

## Archivos de utilidad creados
- `scripts/index_obsidian.py` — indexado mem0
- `scripts/ensure_coverage.py` — cobertura determinista Qdrant
- `scripts/verify_final.py` — verificación tripartita
- `scripts/count_coverage.py` — recuento de cobertura
- `scripts/audit_payload.py` — auditoría de payloads
- `scripts/smoke_memory.py`, `calibrate_add.py` — pruebas

**Veredicto: la memoria tripartita (state.db + Redis + Qdrant/mem0) está ACTIVA y la búsqueda semántica funciona sobre los 78 archivos de Obsidian.**