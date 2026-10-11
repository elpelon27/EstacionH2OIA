# ATTIC — Infraestructura de memoria "tripartita" — DECOMISIONADA 2026-10-11

## Qué era

La primera arquitectura de memoria semántica de Hermes (SOUL FASE 1-2):
- `memory_manager.py` (últ. mtime 2026-08-13): gestor de memoria propio que
  combinaba Chroma + Mem0.
- `chroma_db/` (últ. mtime 2026-08-15): store vectorial ChromaDB local.
- `dot-mem0/` (era `~/.mem0/`, últ. mtime 2026-08-16): historial Mem0
  (history.db 159 KB) + configs de migración faiss/qdrant.

## Cuándo murió

Entre el **13 y el 16 de agosto de 2026** — ninguna de las tres piezas volvió
a escribir después. Estuvo "muerta en pie" ~2 meses: los procesos vivos
(gateway, consolidador, crons) nunca la usaron en ese período; la memoria
real operaba por state.db + Qdrant + Redis (SOUL FASE 3).

## Por qué se retira

Dictaminado por la **doble auditoría ZCode/HERMES del 10-11 oct 2026** (ver
`docs/MEMORIA_CONTEXTO.md` § "Reparación de memoria 2026-10-11"): las tres
celdas estaban zombis (sin escritura desde agosto) y su presencia generaba
confusión operativa — p.ej. la frase "la memoria de Hermes no actualiza
desde agosto" era cierta SOLO para estas ruinas, no para el sistema vivo.

## Dónde vive la memoria hoy (post-decomisión)

- Episódica raw: `/home/skynet/hermes-unified/state.db` (SQLite + FTS5)
- Consolidación (episódica → semántica): `scripts/consolidator.py`
  (watermark POR SESIÓN desde DT-36, 2026-10-11)
- Semántica: Qdrant `hermes_memory` @ :6333 (embeddings nomic-embed-text 768d)
- Semántica legible: `docs/memoria/hechos.json` + notas en vault Obsidian
- Declarativa: `~/.hermes/memories/MEMORY.md` + `USER.md` (memory_enabled=true)

Restaurar si alguna vez hace falta: mover estos componentes de vuelta y
revisar dependencias primero (grep de `memory_manager|chroma|mem0`).

— Prometeo · Estación H2O · 2026-10-11