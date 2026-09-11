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
| 5 | Consolidador | ✅ IMPLEMENTADO v2 (D-5.x) | a40dcdf (+snapshot 6317176) | Session DB validada (38 sesiones/25k msgs); watermark funcionando; 8/8 tests; cron 4:30 AM |
| 7 | Warming predictivo | ✅ IMPLEMENTADO v2 (D-7.x) | 16cb775 (+snapshot ab2224b) | auto DESACTIVADO hasta 2026-10-01; --force verificado end-to-end (10 chunks, TTL 7199s); 8/8 tests |

## PARCHE 5 — Detalle de lo implementado (2026-09-10, decisiones D-5.x aprobadas)

**D-5.2 VALIDADA con datos reales:** Session DB de Hermes = `/home/skynet/.hermes/state.db`
(NO conversations.db, que era fs_audit_log). Schema real: tablas `sessions` (id, source,
display_name, started_at unixepoch…) + `messages` (id INTEGER PK, session_id, role,
content, timestamp REAL, active, compacted). Contenido verificado: 38 sesiones, 25,443
mensajes, 2,589 con contenido sustancial. Era DISTINTO al schema esperado por el
consolidator.py v1 (leía fs_audit_log) → se reescribió la lectura (read-only, uri mode=ro).

**D-5.1:** tabla nueva `consolidation_watermark` (id=1 singleton, last_consolidated_id,
last_run_at, status) creada en hermes_memory.db, inicializada en 0. El consolidador
procesa solo `messages.id > watermark` y actualiza el watermark DESPUÉS de persistir el
log — nunca relee lo consolidado (verificado por test).

**D-5.3:** consolidation_log intacto; la entrada del 2026-08-25 (id=2) queda como
histórico (test explícito lo verifica).

**Otros cambios:**
- Modo: --dry-run por DEFECTO; --live requiere flag explícito (mutuamente excluyentes).
- Guardarraíles OOM: --max-sessions 20 y --max-messages 200 por corrida (flags).
- Extracción por sesión (prompt = conversación concatenada user/assistant, excluye
  tool/system/compacted), timeout Ollama 180s (v1 timeouteaba a 60s con qwen2.5:7b).
- Qdrant payload ahora incluye session_id de origen.
- cron `consolidador_diario` 4:30 AM vía cron_with_memory.sh (después de warming 6:30,
  staggered del backup 4:00).

**Verificación en vivo:** dry-run real leyó la sesión 20260813_151157 (10 msgs, extracción
Ollama 200 OK); 8/8 tests (test_consolidator_patch5.py, DBs aisladas en tmpdir).

## PARCHE 7 — Detalle de lo implementado (2026-09-10, decisiones D-7.x aprobadas)

- **D-7.1:** `auto_activation_ready()` — warming automático DESACTIVADO hasta
  2026-10-01 (AUTO_ACTIVATION_START 2026-09-10 + 21 días). Sin --force, responde
  `auto_disabled` y NO toca Redis. El cron warming_diario 6:30 AM sigue corriendo
  como no-op y sigue registrando cron_runs — que es justo la evidencia que D-7.1
  necesita acumular.
- **D-7.2:** TOP_K=10 memorias más probables (más recientes de Qdrant) con --force.
- **D-7.3:** TTL 7200s mantenido; verificado TTL real 7199s en Redis.
- **D-7.4:** sin eventos de agentes hermanos — el módulo no consume ningún bus de
  eventos (test D-7.4 verifica por AST que no exista código consumidor); explícitamente
  pospuesto a FASE 4+.
- `setex` deprecado → `set(key, value, ex=7200)`.
- warming_log event_types: `forced_manual` (nuevo) y `pattern_detected`.
- Cron warming_predictivo_diario NO agendado (espera activación D-7.1); el warming_diario
  existente queda como registro de cron_runs.
- **Fecha estimada de activación automática: 2026-10-01.**

**Verificación en vivo (--force):** 10 chunks cacheados, Redis DBSIZE 10, TTL 7199s,
warming_log id=3 `forced_manual|10`. 8/8 tests (test_warming_patch7.py).

**FIX colateral (infraestructura):** Redis nativo estaba en MISCONF desde el arranque —
`/etc/redis/redis.conf` minimalista sin `dir` → bgsave intentaba escribir `/dump.rdb`
→ writes bloqueados. La primera corrida de warming del parche 10 (10 claves) se perdió
al reiniciar. Fix: `dir /var/lib/redis`, `dbfilename hermes_redis.rdb`, save 900 1 /
300 10 (backup del conf en /etc/redis/redis.conf.bak.20260910). Verificado:
`rdb_last_bgsave_status:ok`, writes habilitados, persistencia activa.

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

## PENDIENTE — Activaciones futuras

- **2026-10-01: activación automática del warming (D-7.1).** El código ya está:
  `auto_activation_ready()` dará positivo y warming_diario 6:30 AM empezará a
  cachear patrones detectados sin intervención. En esa fecha, revisar que
  cron_runs tenga 21+ días de datos y que los patrones se detecten.

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

- **D6 (Redis vacío): CERRADA** — warming_diario llena la capa Buffer a diario
  (y 2026-09-10: Redis MISCONF corregido — persistencia RDB activa en /var/lib/redis).
- **D10 (FASE 3 sin implementar): CERRADA al 90%** — los 4 parches operativos
  (10, 4, 5, 7); único pendiente: activación automática del warming el 2026-10-01
  (D-7.1, ya programada en código; requiere solo esperar los 21 días de cron_runs).
- **D12 (mem0migrations):** ya documentada (docs/QDRANT_COLLECTIONS.md).

💧