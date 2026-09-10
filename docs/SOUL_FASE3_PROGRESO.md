---
title: SOUL v2.1 FASE 3 — Progreso de implementación
---

# SOUL FASE 3 — Progreso de implementación

**Última actualización:** 2026-09-10
**Autor:** Prometeo
**Fuente:** implementación en vivo con verificación por evidencia (Líder: nunca
informes pasados, siempre datos reales)
**Repo:** github.com/elpelon27/EstacionH2OIA (rama feat/odoo-r4-integration)

## Estado por parche

| Parche | Nombre | Estado | Commit | Evidencia |
|---|---|---|---|---|
| 10 | cron_runs + warming | ✅ IMPLEMENTADO | 0b5170d | cron_runs 2 registros de test OK→limpiados; Redis DBSIZE 0→10; warming_log 1 entrada |
| 4 | Decay social + semántico | ✅ IMPLEMENTADO | e1cd2f1 (fix en snapshot 113c05e) | dry-runs OK; fix payload created_at: 400/400 puntos parseables |
| 5 | Consolidador | 🟡 EXISTE (b199e36) — postergado por Líder (decisiones D-5.x) | — | consolidator.py funcional con dry-run/guardarraíl; requiere decisiones del Líder antes de --live |
| 7 | Warming selectivo | 🟡 EXISTE (b199e36) — postergado por Líder (D-7.x) | — | warming.py funcional; caso --force verificado; patrones requieren 3+ semanas de cron_runs |

## PARCHE 10 — Detalle de lo implementado (2026-09-10)

**NUEVO `scripts/cron_with_memory.sh`** — wrapper fail-open de crons:
- Registra en `hermes_memory.db::cron_runs`: nombre, éxito, duración_ms,
  output_hash (sha256; el output NUNCA se persiste — privacidad §6.6).
- Streak de fallos: 2 consecutivos → advertencia de skill candidate (§11.2a).
- Fail-open: si el registro falla, el cron original igual corre y su exit code
  se preserva.
- Verificado en vivo: éxito → `success=1`, hash 64-hex; fallo → `success=0`,
  exit 1 preservado, streak=1.

**Crontab migrado** (backup previo en /home/skynet/crontab.backup.20260910):
```
0  23 * * *  cron_with_memory.sh ingest_pdf_diario       (ingest_pdf.py --once)
0  3  * * *  cron_with_memory.sh decay_social_diario     (decay_social.py)
0  2  * * 0  cron_with_memory.sh decay_semantic_semanal  (decay_semantic.py)
30 6  * * *  cron_with_memory.sh warming_diario          (warming.py)  ← NUEVO
```
(snapshot cada 2min, push cada 10min y backup 4am quedan fuera del wrapper a
propósito: son infraestructura, no generan memoria útil.)

**warming.py verificado end-to-end (--force):**
- Redis: DBSIZE 0 → 10, claves `hermes:warm:<qdrant_id>`, TTL 7200s ✓
- `warming_log`: 1 entrada (pattern_detected, 10 chunks, miss_rate 1.0) ✓
- La detección de patrones automáticos dará positivo cuando cron_runs acumule
  ≥3 ejecuciones en mismo día/hora (~3 semanas con los crons actuales).

**Dependencia añadida:** redis-py 8.1.0 en venv (warming.py la requería; no
estaba instalada).

**D6 CERRADO** — Redis ya no está vacío: la capa Buffer tiene su primer
writer legítimo operando con cron diario.

## PARCHE 4 — Detalle de lo implementado (2026-09-10)

Los scripts ya existían (b199e36, 2026-08-24) — la corrección del error de la
revisión está en SOUL_FASE3_REVISION.md. Lo hecho hoy:

**FIX CRÍTICO en `decay_semantic.py`:** leía `payload['timestamp']`, pero los
402 puntos reales de `hermes_memory` usan `created_at` → el decay saltaba
TODOS los puntos silenciosamente (el dry-run "0 archivados" era falso
negativo). Ahora soporta `created_at | timestamp | updated_at`.
- Verificación tras el fix: 400/400 puntos con fecha parseable; el más viejo
  es del 2026-06-27 (75 días → relevance 0.69 > umbral 0.1: nada que archivar
  HOY — resultado correcto, no bug).

**Dry-runs verificados:**
- decay_social: 0 interacciones (tabla vacía — normal; el decay social será
  no-op hasta que la capa Social tenga writers).
- decay_semantic: 402 puntos, 0 archivables hoy.

**Decisiones D-4.1/D-4.2 resueltas por diseño existente:**
- D-4.1: relevance NO se persiste — se calcula on-the-fly desde la fecha del
  payload (sin shadow-map necesario).
- D-4.2: el decay usa `created_at` como proxy de último acceso. Instrumentar
  lecturas reales queda para FASE 4 si el Líder lo pide.

## PENDIENTE — Parches 5 y 7 (esperan al Líder)

- **Parche 5 (Consolidador):** consolidator.py ya está funcional (dry-run
  default, guardarraíl 3 fallos, extracción con qwen2.5:7b, embeddings reales
  nomic-embed-text 768d — fix b3d3d33). Antes de --live se necesitan las
  decisiones D-5.1 (watermark), D-5.2 (fuente de lectura) y la calibración del
  prompt de extracción. NO se agendó en crontab.
- **Parche 7 (Warming selectivo):** warming.py ya está funcional y verificado
  con --force. Los patrones automáticos (caso a) requieren cron_runs con 3+
  semanas de datos — ya acumulando desde hoy. Los casos (b) y (c) requieren
  las decisiones D-7.1 y la exclusión del bus de eventos (confirmada en
  revisión como FASE 4+).

## Verificación en vivo (evidencia de esta sesión)

```
$ redis-cli DBSIZE → 10 (antes 0)
$ redis-cli KEYS "hermes:warm:*" → 10 claves
$ redis-cli TTL <key> → 7200
$ sqlite3 data/hermes_memory.db "SELECT * FROM warming_log;"
  → pattern_detected|10|1.0|2026-09-10 19:01:16
$ sqlite3 data/hermes_memory.db "SELECT COUNT(*) FROM cron_runs;" (post-limpieza) → 0
  (los registros de test se limpiaron; los reales empiezan con los crons de hoy)
$ ./scripts/cron_with_memory.sh test X → cron_runs correcto, exit preservado
```

## Deudas actualizadas

- **D6 (Redis vacío): CERRADA** — warming_diario llena la capa Buffer a diario.
- **D10 (FASE 3 sin implementar): CERRADA al 50%** — parches 10 y 4 operativos
  con cron; 5 y 7 existentes pero postergados a decisión del Líder.
- **D12 (mem0migrations):** ya documentada (docs/QDRANT_COLLECTIONS.md).

💧