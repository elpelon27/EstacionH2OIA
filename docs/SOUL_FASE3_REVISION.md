---
title: SOUL v2.1 FASE 3 — Revisión de Diseño (parches 4, 5, 7, 10)
---

# SOUL v2.1 FASE 3 — Revisión de Diseño ANTES de implementar

**Última actualización:** 2026-09-10
**Autor:** Prometeo (a revisión del Líder)
**Fuente:** PATCHSET v2026.08.20 (parches 4, 5, 7, 10) + verificación EN VIVO de toda
la infraestructura (2026-09-10, §6.4: la realidad del servidor manda)
**Repo:** github.com/elpelon27/EstacionH2OIA (rama feat/odoo-r4-integration)
**Estado:** DISEÑO — NO IMPLEMENTAR hasta aprobación del Líder

---

## RESUMEN EJECUTIVO

FASE 3 implementa el "sistema nervioso autónomo" de la memoria de 6 capas: 4 scripts
Python (consolidador, 2 jobs de decay, warming) que convierten la política de olvido
declarativa en mecanismos ejecutables. **Todo el andamiaje ya existe y está verificado
en vivo**: las 3 BDs SQLite (hermes_memory.db, interactions.db, conversations.db) con
sus tablas y CHECK constraints ya creadas en FASE 2, mem0 2.0.18 instalado, Ollama con
los 6 modelos, Qdrant activo (402 pts), Redis vivo (DBSIZE=0 — D6 se llena aquí).

**Hallazgo crítico de la revisión:** hay un desfase entre el diseño del patchset y la
realidad de los datos:
1. `consolidation_log` ya tiene 1 entrada (2026-08-25: 1 sesión, 50 chunks leídos,
   0 hechos extraídos) — el Consolidador ya se ejecutó una vez en dry-run/probe,
   pero NO existe `scripts/consolidator.py` en el repo. Hay que localizar qué lo
   generó (¿script efímero de FASE 2?) antes de re-implementar.
2. `interactions.db` tiene 0 registros: el decay social (0.99/día) es un no-op
   hasta que la capa Social empiece a recibir escrituras — y NADA escribe en ella
   hoy. FASE 3 sin writers sociales = decay sin input.
3. `cron_runs` tiene 0 registros: el warming predictivo (parche 10) necesita un
   hook que registre cada ejecución de cron ANTES de poder detectar patrones.

**Recomendación: implementar POR PARTES, en 3 incrementos independientes con
checkpoint después de cada uno** (detallado abajo). Riesgo total: MEDIO, controlable.
Estimación: 3 sesiones de trabajo (~4-6h efectivas) + 1 semana de calibración
observacional.

---

## ESTADO REAL DE LA INFRAESTRUCTURA (verificado en vivo 2026-09-10)

| Componente | Estado | Evidencia |
|---|---|---|
| `data/hermes_memory.db` | ✅ 7 tablas (consolidation_log, cron_runs, warming_log, traces_hot, traces_archive, archive) | sqlite3 `.tables` |
| `data/interactions.db` | ✅ 3 tablas (interactions, conflicts, interactions_archive) — **0 rows** | COUNT=0 |
| `data/conversations.db` | ✅ 16 tablas — fs_audit_log 114.881 rows, conversations 1 row, dispatch_queue 3 | sqlite3 COUNT |
| Redis | ✅ PONG, **DBSIZE=0** (D6) | redis-cli |
| Qdrant `hermes_memory` | ✅ 402 pts, 768d | GET /collections |
| mem0 | ✅ 2.0.18 | import verificado |
| Ollama | ✅ 6 modelos (nomic-embed-text, qwen2.5:7b/3b, qwen7b-pro, llama3.2:1b) | /api/tags |
| `consolidation_log` | ⚠️ 1 entrada previa (2026-08-25, 0 hechos) | SELECT |
| `cron_runs` | ⚠️ 0 filas — sin hook de registro | SELECT |
| Scripts FASE 3 | 🔴 NO existen: consolidator.py, decay_social.py, decay_semantic.py, warming.py | ls scripts/ |

---

## PARCHE 4 — §6.3: Política de olvido con decay ejecutable

**Objetivo:** convertir "N sesiones" en fórmula medible:
`relevance_t = relevance_0 × (decay_factor ^ días_sin_acceso)`, con tabla de
half-lives por capa y dos jobs ejecutores.

**Textos:** ya aplicados declarativamente en FASE 1 (el §6.3 del SOUL actual). Lo que
FALTA es el código ejecutor.

**Entregables de código:**
- `scripts/decay_social.py` — recorre `interactions.db::interactions`, aplica decay
  0.99/día sobre `relevance`, archiva <0.1 (mover a `interactions_archive` con gzip).
  Cron: diario 3am.
- `scripts/decay_semantic.py` — recorre Qdrant `hermes_memory`, aplica 0.995/día,
  archiva <0.1 en `hermes_memory.db::archive` (no borra: guarda qdrant_id, markdown,
  relevance y rationale). Cron: domingo 2am.

**Dependencias:** ninguna entre parches; interactions.db (existe, vacía);
hermes_memory.db::archive (existe, schema verificado: original_qdrant_id,
fact_markdown, relevance_at_archive, rationale).

**Puntos de diseño a decidir por el Líder:**
- D-4.1: ¿Dónde vive `relevance` en Qdrant? El payload actual de hermes_memory NO
  tiene campo relevance (verificado: chunk, created_at, data, hash, kind, source,
  title, updated_at, user_id). Opciones: (a) añadir al payload en cada upsert,
  (b) mantener un shadow-map en hermes_memory.db. **Recomiendo (b)** — evita
  re-escribir 402 puntos existentes y Qdrant sigue siendo fuente de embeddings,
  no de estado.
- D-4.2: `updated_at` del payload puede servir como proxy de "último acceso", pero
  NO es lo mismo (actualización ≠ evocación). Decidir si el decay usa updated_at
  (simple) o si instrumentamos lecturas (más fiel, más código).

**Riesgos:** BAJOS — ambos jobs son idempotentes, operan sobre tablas con 0-402
registros, y archivan (nunca borran). El riesgo real es el cron mal agendado
(colisión con backup 4am: no, decay es 3am, backup externo 4am — OK).

**Tests:** dry-run flag obligatorio; unit test de la fórmula de decay con
relevance_0 conocidos; test de umbral 0.1; verificación de archive con INSERT dummy.

**Tiempo:** 1.5h (ambos jobs juntos — comparten ~80% de estructura).

---

## PARCHE 5 — §6.5: El Consolidador

**Objetivo:** automatizar episódica→semántica: leer conversations de últimas 24h,
extraer hechos con mem0 + qwen2.5:7b (confianza certain|inferred|tentative),
indexar en Qdrant (768d nomic-embed-text), escribir Markdown en vault Obsidian,
auditar en consolidation_log. Regla de oro: hechos que tocan SOUL/skills/modelo del
Líder → tentative + notificar. Guardarraíl: 3 fallos consecutivos → stop + escalar.

**Archivos que toca:**
- NUEVO `scripts/consolidator.py`
- LECTURA: conversations.db (fs_audit_log es la fuente real de actividad —
  conversations tiene solo 1 fila), hermes_memory.db::consolidation_log (escritura)
- ESCRITURA: Qdrant hermes_memory (upsert), docs/ vault (Markdown con frontmatter)
- CONEXIÓN: mem0 2.0.18, Ollama (qwen2.5:7b clasifica, nomic-embed-text embebe)

**Dependencias:** parche 4 NO bloquea (decay puede llegar después); requiere que
mem0 tenga credenciales/API de LLM configuradas para extracción (verificar si mem0
usa Ollama local o API remota — configuración a auditar antes de implementar).

**Punto crítico D-5.1:** el patchset dice "leer entries de conversations.db no
consolidadas (flag consolidated=0)" — **esa columna NO existe** en ninguna tabla
(verificado en vivo). El Consolidador necesita su propio ledger de procesamiento:
recomiendo una tabla `consolidation_watermark` (o reutilizar consolidation_log con
last_seen_ts) para saber qué ya procesó. Decidir con el Líder.

**Punto crítico D-5.2:** ¿qué lee exactamente? conversations.db es mayormente BD de
NEGOCIO (fs_* tables, §6.1). La episódica real vive en el session_search de Hermes
(SQLite del agente) + fs_audit_log (114k rows de auditoría). Definir la fuente
exacta: ¿audit_log de últimas 24h? ¿solo session DB? Esto cambia el prompt de
extracción completo. **ESTA es la decisión de diseño más importante de FASE 3.**

**Punto D-5.3:** la entrada preexistente en consolidation_log (2026-08-25, 50
chunks leídos, 0 extraídos) sugiere que alguien ya probó el pipeline. Localizar ese
código (¿bash history? ¿script borrado?) para no duplicar trabajo.

**Riesgos:** MEDIOS — es el único parche que ESCRIBE en Qdrant producción (402 pts)
y en el vault (docs/ = repo git). Un bug puede contaminar la semántica o commitear
Markdown basura. Mitigación: dry-run por defecto (imprime, no escribe), flag --live
explícito, y en live: límite de N hechos por corrida los primeros 7 días.

**Tests:** dry-run sobre 24h de audit_log (salida humana legible); test con hecho
contradictorio inyectado → conflictos en interactions.db::conflicts (schema ya
existe); test guardarraíl (3 fallos → flag stop persistente).

**Tiempo:** 2.5-3h de implementación + calibración del prompt de extracción
(iterativa, cuenta aparte).

---

## PARCHE 7 — §6.7: Warming selectivo

**Objetivo:** precargar en Redis (capa Buffer) los top-10 chunks Qdrant relevantes
ante patrones: (a) cron ejecutado ≥3x mismo día/hora semanal, (b) sesión del Líder
reciente <1h, (c) evento de agente hermano que históricamente precede consulta.

**Esto cierra D6:** Redis DBSIZE=0 hoy; warming es el primer writer legítimo de la
capa Buffer.

**Archivos:** NUEVO `scripts/warming.py`; LECTURA: hermes_memory.db::cron_runs
(0 filas hoy), Qdrant (search); ESCRITURA: Redis con claves `hermes:warm:*` TTL 2h,
hermes_memory.db::warming_log (schema listo: event_type, chunks_prefetched,
cache_hits, cache_misses, miss_rate).

**Dependencias:** PARCHE 10 (cron_runs) es su proveedor de patrones — warming sin
cron_runs poblado solo puede hacer el caso (b) (recuperación de sesión reciente).
El caso (c) (eventos de agentes hermanos) requiere un bus de eventos que NO existe
— recomiendo EXCLUIRLO del scope inicial de FASE 3 y documentarlo como FASE 4+.

**Punto D-7.1:** "top-10 chunks más relevantes al contexto actual" requiere saber
qué es "el contexto actual" sin sesión activa. Para warming basado en cron, el
contexto es predecible (ej: "analytics de lunes" → query embedding del título del
cron). Definir el mapping cron→query semantic por cron conocido, empezando con
los 2-3 crons reales del sistema (ingest_pdf 23:00, backup 04:00, verify_backup
mensual). Los otros 6 crons del sistema (snapshot, push) no generan memoria útil.

**Riesgos:** BAJOS — Redis es regenerable por diseño (TTL), un fallo de warming
solo significa cache frío (degradación a lazy loading, que es el comportamiento
actual). El riesgo principal es código que bloquea (timeout de Ollama al embeber
la query) → mitigar con timeout corto y fail-open (warming falla → nada pasa).

**Tests:** ejecutar warming → `redis-cli KEYS "hermes:warm:*"` muestra claves
(DBSIZE > 0 = D6 cerrado); TTL verificado (2h); warming_log con miss_rate calculado.

**Tiempo:** 1.5-2h.

---

## PARCHE 10 — §11.2a: Memoria predictiva de crons

**Objetivo:** cada ejecución de cron registra en cron_runs (timestamp, éxito,
duración, output_hash); patrón inferido a las ≥3 ejecuciones semanales
consistentes; 2 fallos consecutivos → entrada episódica con rationale + skill
candidate. El Consolidador lee cron_runs semanalmente y propone ajustes al warming.

**Archivos:** NUEVO hook de registro — opción recomendada: wrapper
`scripts/cron_with_memory.sh <nombre> <comando>` que invoca el comando, mide
duración, hashea output (sha256, no guarda el output — privacidad), y hace INSERT
en cron_runs. Migrar los crontabs existentes al wrapper (solo las líneas de
trabajo, no snapshot/push).

**Dependencias:** NINGUNA (independiente, se beneficia solo). Es prerequisito
opcional-ideal del warming (parche 7) para el caso (a).

**Riesgos:** BAJOS — INSERT-only en tabla vacía, fallo del wrapper nunca debe
bloquear el cron original (`|| true` + log). Riesgo único: modificar crontab
producción → backup del crontab ANTES (`crontab -l > backup`) y restore en 1 línea.

**Tests:** ejecutar wrapper con comando dummy → cron_runs COUNT=1 con success,
duration_ms y output_hash de 64 hex; fallo del wrapper no rompe el comando
envuelto; 2 fallos simulados → episódica con rationale (cuando consolidador exista).

**Tiempo:** 1h.

---

## ORDEN DE IMPLEMENTACIÓN RECOMENDADO (3 incrementos)

```
INCREMENTO 1 (fundación, riesgo mínimo, ~1h):  PARCHE 10
  wrapper cron_with_memory.sh + migrar crontab (con backup previo)
  → cron_runs empieza a poblarse HOY (datos para el warming en 1-2 semanas)
  → checkpoint: verificar COUNT>0 tras el primer cron real

INCREMENTO 2 (decay, ~1.5h):                 PARCHE 4
  decay_social.py + decay_semantic.py, dry-run primero
  → agendar solo tras dry-run validado por el Líder
  → checkpoint: dry-run output revisado + decisiones D-4.1/D-4.2 tomadas

INCREMENTO 3 (el corazón, ~3h + calibración): PARCHE 5 → luego PARCHE 7
  consolidator.py dry-run → revisión humana de hechos extraídos → --live limitado
  warming.py (caso b primero; caso a cuando cron_runs tenga 3+ semanas de datos)
  → checkpoint: D6 cerrado (DBSIZE>0), consolidación auditada 7 días antes de
    hacerla post-sesión automática
```

Dependencias: 10 → 7 (provee datos, soft). 4 y 5 son independientes entre sí.
El patchset sugiere días 8-14; el orden de arriba prioriza riesgo-creciente.

## DECISIONES DEL LÍDER REQUERIDAS (bloqueantes)

1. **D-5.2 (LA CRÍTICA):** fuente de lectura del Consolidador — ¿fs_audit_log,
   session DB de Hermes, o ambas? Cambia todo el diseño del extractor.
2. **D-5.1:** estrategia de watermark (sin columna consolidated en el schema real).
3. **D-4.1:** dónde vive relevance para decay semántico (payload Qdrant vs
   shadow-map en hermes_memory.db — recomiendo shadow-map).
4. **D-4.2:** decay por updated_at (proxy) vs instrumentación de lecturas.
5. **D-7.1:** mapping cron→query de warming (propongo empezar con ingest_pdf).
6. Confirmar exclusión del caso (c) de warming (bus de eventos) → FASE 4+.
7. Localizar el origen de la entrada consolidation_log del 2026-08-25 (D-5.3).

## PUNTOS CRÍTICOS (qué puede romper)

- consolidator.py --live escribe en Qdrant prod (402 pts) y en docs/ (repo git):
  contaminación semántica o commits de Markdown basura. Mitigación: dry-run
  default, --live con cap de N hechos, revisión humana 7 días.
- Migrar crontab puede romper los jobs existentes si el wrapper tiene bugs:
  backup crontab previo + wrapper fail-open.
- decay_semantic.py --live sobre Qdrant: si la fórmula o el shadow-map tienen
  bugs, archiva hechos buenos. Mitigación: dry-run imprime qué archivaría.
- Nada de FASE 3 debe tocar bridge/webhook/tunnel/Meta (reglas): todos los
  scripts son standalone + crontab, cero interacción con servicios systemd.

## ROLLBACK PLAN

- Scripts nuevos: `rm scripts/{consolidator,decay_*,warming,cron_with_memory}.*`
  + `crontab` restaurado desde backup. Cero servicios reiniciados.
- Datos: decay y consolidador solo ARCHIVAN (nunca borran) → restaurar es mover
  de archive/interactions_archive de vuelta. Qdrant: los puntos archivados
  conservan su id → upsert de reactivación.
- consolidation_log/warming_log/cron_runs: tablas de auditoría, pueden truncarse
  sin pérdida funcional.
- SOUL doc: no se toca en FASE 3 (los textos de 4,5,7,10 ya se aplicaron en
  FASE 1-2 declarativamente) — no hay snapshot de SOUL que hacer.

## ESTIMACIÓN TOTAL

- Implementación: ~6h efectivas (10: 1h, 4: 1.5h, 5: 3h, 7: 1.5h)
- Calibración observacional: 1-2 semanas de consolidation_log/warming_log
  revisados por el Líder antes de automatizar post-sesión (FASE 4 lo formaliza)
- Cierre de deudas al completar: **D6** (Redis deja de estar vacío), **D10**
  (FASE 3 implementada), **D12** (mem0migrations queda documentada como
  colección interna — ya hecho en docs/QDRANT_COLLECTIONS.md)

## RECOMENDACIÓN FINAL

**Implementar POR PARTES** en el orden 10 → 4 → 5 → 7, con checkpoint del Líder
después de cada incremento (su modelo de neurocirugía: fraccionar + verificar).
NO implementar todo de una: el Consolidador (5) tiene decisiones de diseño
abiertas (D-5.1/D-5.2) que requieren tu input ANTES de escribir código. El parche
10 y el 4 pueden avanzar ya sin ninguna decisión pendiente.

FASE 4 (integración post-sesión + calibración + memoria-v2.md) queda fuera del
scope de esta revisión y se planifica cuando FASE 3 esté operativa.

💧