# Respaldo de trabajo pendiente — 2026-08-16

> Backup NO commiteado. Servidor se colgó a mitad de sesión (proceso terminado "killed").
> Este archivo preserva el estado para retomar más tarde. NO commitear como parte de un
> cambio lógico de feature; es solo respaldo de contexto.

## Contexto
- Rama: `feat/odoo-r4-integration`
- Sesión previa: revisión/garantías de calidad (mypy + integración de memoria) del repo.
- Ultimos commits de la rama (snapshot inicio de sesión):
  - `a5af5cc` fix: mypy clean en bridge follow-imports (39 errores → 0)
  - `60e1d5a` docs: registrar deuda mypy pendiente (208 errores producción)
  - `0048f34` docs: auditoría milimétrica + inventario orquestación + cierre
- Deuda mypy de producción: ~208 errores → ver `docs/DEUDAS_TECNICAS_Y_PROYECTOS.md` y `docs/05-tech-debit/`.
- Estado general del repo al inicio de sesión (snapshot `git status`):
  - 18 staged, 25 modified, 10 untracked.

## Qué quedó pendiente (INCOMPLETO por el cuelgue)

### 1. Verificación funcional de memoria (bridge Qdrant + Nomic) — RESUELTA 2026-08-16
- `src/memory/unified_memory.py`: el bridge ya consume `self.memory.add(...)`.
- ✅ Verificación funcional CORRIDA y OK: `scripts/smoke_memory.py` → init 1.2s, search 0.1s, SMOKE_OK.
  Qdrant @6333 y Ollama @11434 vivos; nomic-embed + qwen2.5:7b disponibles.
- ⚠️ CORRECCIÓN DE NÚMERO: la colección `hermes_memory` tiene **402 points**, NO 81.
  El "81" era una métrica mal copiada (conteo de docs 78/78 vs puntos reales).
  402 = coherente con chunking ≤3400 chars (varios vectores por doc).
- ⚠️ DEUDA NUEVA (infraestructura): Qdrant cliente venv **1.18.0** vs servidor **1.12.4**
  → major mismatch (compat check dispara warning). Riesgo de cableado a futuro.
  Acción recomendada: alinear versión (up/downgrade cliente) bajo control, NO a lo bruto.

### 2. mypy — errores puntuales abiertos (según transcript previo)
- `external_skills.py`: 1 error mypy — `self.execute_kw` bytes → cascade `AgentType.ax`.
- `skill_registry` import: `from ..skill_registry import SkillRegistry`.
  - OJO: el módulo vive en `src/orchestration/skill_registry.py`, pero los imports
    apuntaban a `memory/…`. Verificar ruta correcta.
- Uso del gate del repo (NO confundir versiones):
  - `pre-commit run mypy --files <f>` (mypy v1.14.0 pinned).
  - mypy 1.20.2 del venv da conteos distintos → no fiar de él.
  - follow-imports arrastra 12+ archivos.

### 3. Tests — mock/helpers impuros
- `tests/prometheus/test_prometheus_api.py` (o ruta equivalente): mock del módulo
  insuficiente → falta configurar atributos internos del mock (fallo: `module has no
  attribute`). Revisar `conftest.py` / fixtures.
- `src/integrations/odoo_sync.py` (o helpers): helper impuro porque usa
  `datetime.now()` en cuerpo → regla: extraer helper con `_now` para pureza.

### 4. Otros verificados OK (no re-tocar)
- 7 archivos con py_compile OK al cierre.
- Qdrant/Nomic embedding: pitfall `nomic-embed` falla > ~4k chars → chunkear <=3400.

## CHECKPOINT MYPY — creado 2026-08-16 (inicio deuda mypy)
> Inicio del ataque a la deuda mypy de producción. Punto de control previo.
- Deuda documentada: 208 errores; top-3 = odoo_sync(28) + external_skills(25) + r4/client(16) = 69.
- Gate oficial: `pre-commit run mypy --files <f>` (v1.14.0 pinned). NO usar mypy 1.20.2 del venv.
- Archivos ya modificados pre-sesión (no tocar por error): external_skills.py trae 25 según doc,
  pero aparece modificado en git (estado pre-cuelgue). RE-MEDIR antes de asumir.

## CHECKPOINT SEGURIDAD — creado 2026-08-16 (brecha: secrets NVIDIA en hybrid_llm.py)
> Inicio del ataque a la brecha de seguridad. Punto de control previo.
- Brecha: scripts/prometeo/hybrid_llm.py tiene 3 API keys NVIDIA hardcodeadas (nvapi-*).
- Objetivo: moverlas a .env (variables de entorno) y hacer que el código las lea de env.
- NO imprimir/entregar los valores de las keys (secretos). No leer .env salvo nombres de var.
- NUNCA commitear los secrets; el .env debe seguir ignorado por git.

## CICLO DE SESIÓN COMPLETO — VALIDADO 2026-08-16 (inicio → cierre, milimétrico)
> Ciclo del skill memoria-hechos verificado de inicio a cierre con datos reales.
- **INICIO:** --status (L1 sauces 7/1922, L2 Redis, L3 Qdrant 402pts/81, grafo 2) + --recall contexto OK.
- **CIERRE:** --add de hecho de sesión #3 (persistido en hechos.json, fuente de verdad) OK.
- **FLUJO DEL DATO:** escritura → vault (hechos.json) → recall por tema → OK. Sin fugas.
- **2 TIPOS DE RECUPERACIÓN VERIFICADOS:** vectorial (Qdrant docs) + grafo versionable (JSON).
- **MEJORA DE ROBUSTEZ APLICADA (validada en sandbox):** el match por tema del recall
  no descomponía guiones (`sesion-2026-08-16-ciclo` no matcheaba query parcial).
  Ahora `_split_tokens` descompone espacios/guiones/guiones-bajos → recall partial OK.
- **VERIFICACIÓN GLOBAL:** suite 345/14/0, gate mypy limpio, py_compile OK,
  hechos.json con 3 hechos coherentes [1,2,3].

## CERTIFICACIÓN DE LAS 4 CAPAS — COMPLETADO 2026-08-16 (brechas cerradas)
> Las 3 brechas restantes verificadas con datos reales y cerradas. Suite verde 345/14/0.
1. **CAPA EPISÓDICA** (`conversations.db` + `state.db`): verificada en vivo.
   - conversations.db: 16 tablas, datos reales (fs_audit_log 37k, fs_tasas_cambio 113, etc.).
   - state.db (L1): 7 sesiones, 1896 mensajes; FTS trigram ~909 mensajes indexados.
   - `session_search` recuperó sesión previa 20260815 (consulta real, no simulada).
   - Redis (L2): PONG, dbsize 0 (caché vacía = correcto, no falso silencio).
2. **CAPA PROCEDURAL** (skills): 84 skills cargadas y operativas vía skills_list.
   - py_compile OK en todos los archivos reparados hoy.
3. **CICLO `memoria-hechos`** (skill del grafo tripartito): verificado end-to-end.
   - `--status`: L3 Qdrant 402pts/81 archivos, L1 sesiones, L2 Redis, grafo JSON.
   - `--add`: hecho #2 persistido en docs/memoria/hechos.json (backup previo hecho).
   - `--recall`: recuperación semántica OK.
   - **BUG REAL ENCONTRADO Y REPARADO:** `cmd_recall` rompía con `TypeError: 'int'
     object is not subscriptable` cuando algún payload guarda `text`/`chunk` como int.
     Fix: `pl = h.payload or {}` + `str(_raw)[:160]`. Validado en sandbox → productivo.
   - + limpieza de 4 errores mypy pre-existentes del skill (tipado): gate PASSA limpio.

## RESOLUCIÓN QDRANT — COMPLETADO 2026-08-16 (neurocirugía exitosa)
> Deuda técnica Qdrant RESUELTA y verificada de punta a punta.
- **Versiones finales productivas:** qdrant-client **1.12.2** (alineado a servidor 1.12.4),
  mem0ai 1.0.11, protobuf **6.33.6**.
- **Proceso (sandbox → integración):** validado en venv sandbox `/tmp/qdrant_sandbox`
  (0 warnings + memoria recuperable) ANTES de tocar el venv productivo.
- **Efecto colateral capturado y resuelto:** el downgrade arrastró protobuf 5.29.6, que
  rompía ortools (exige >=6.33.1,<6.34). Subido a 6.33.6.
- **VERIFICACIÓN FINAL:** 0 warnings incompatibilidad, health True, memoria "Estación
  H2O" recuperada, suite completa 345 passed / 14 skipped / 0 failures.
- **LEADING TIP para futuro:** qdrant-client 1.12.x y ortools 9.15 exigen rangos de
  protobuf mutuamente incompatibles con grpcio-tools (<6.0) y opentelemetry (<6.0);
  pip reporta esos conflictos como warnings pero la suite NO importa esas deps
  transitivas de telemetría. NO "resolverlos" a ciegas — verificar por ejecución.

## CHECKPOINT QDRANT — creado 2026-08-16 (pre-downgrade del cliente)
> NEUROCIRUGÍA sobre memoria. Punto de control ANTES de tocar el cableado Qdrant.
- **Hecho REVALIDADO con datos duros (no por memoria):**
  - Cliente venv: `qdrant-client 1.18.0`
  - Servidor: Docker `qdrant/qdrant:v1.12.4` (contenedor `hermes_qdrant`, healthy)
  - Política oficial Qdrant: "Major match + minor diff ≤ 1" → 6 > 1 = INCOMPATIBLE confirmado.
- **ESTADO ACTUAL ARRIBA y FUNCIONAL** (sin tocar): el venv con cliente 1.18.0 ya corre
  contra servidor 1.12.4 (smoke pasó, 402 points, memoria recuperable). La incompatibilidad
  es solo WARNING, no rompe hoy — pero es deuda de cableado.
- **VEHÍCULO ELEGIDO:** downgrade del CLIENTE del venv a 1.12.x. NO tocar el contenedor
  Docker (producción viva con la memoria real). Mínimo invasivo, cero riesgo de pérdida.
- **PLAN NEUROQUIRÚRGICO:**
  1. Sandbox: crear venv aparte `/tmp/qdrant_sandbox`, instalar qdrant-client==1.12.2
     (NOTA: 1.12.4 NO existe en PyPI; el último de la rama 1.12 es 1.12.2 → alinea
     cliente a la MISMA rama menor del servidor, óptimo). Verificar SIN warning +
     operaciones add/search OK contra servidor 1.12.4.
  2. Si 100% operativo en sandbox → reaplicar el downgrade en el venv productivo.
  3. Re-verificar smoke + suite + recovery de memoria "Estación H2O".
- SI ALGO SALE MAL: restaurar cliente 1.18.0 (pip install qdrant-client==1.18.0).

## REGISTRO DE REPARACIONES — COMPLETADO 2026-08-16
> Estado final tras las reparaciones. Suite verde: 345 passed, 14 skipped, 0 failures.
> Gate mypy oficial (pre-commit v1.14.0) sobre archivos tocados: PASSED.
1. ✅ Memoria. Causa raíz de la pérdida de continuidad encontrada y reparada:
   - `unified_memory.py` apuntaba a vector store **FAISS** en ruta INEXISTENTE
     (`/mnt/valentina_ssd/mem0_faiss`) → el bridge escribía en el vacío.
     Ahora usa **Qdrant `hermes_memory` @6333** (canónico, verificado, vivo).
   - `user_id` default era `hermes-agent` (NO existe ningún punto con ese id) →
     búsquedas devolvían 0. Ahora default = `obsidian_docs` (capa semántica real).
   - Parser resiliente a payload sin `metadata` (fix AttributeError).
   - Verificado E2E: `UnifiedMemory().search(...)` recupera "Estación H2O", arquitectura, etc.
2. ✅ Test fantasma eliminado: `tests/unit/test_date_utils.py` importaba
   `src.common.date_utils` que JAMÁS existió (colegaba abortaba en colección →
   359 tests ni corrían). Eliminado (era untracked).
3. ✅ Aislamiento de BD financiera: test_financial_integration corría contra la
   **DB real de producción** `data/conversations.db` (dejó pedido 90010 persistido →
   UNIQUE constraint). Añadido fixture `_isolated_financial_db` (tempfile + schema,
   sin tocar `SQLITE_PATH` que usa bridge para dispatch). Genera idempotencia.
4. ✅ Bridge/dispatch e2e: verificados pasan junto a financial (12 tests juntos).

## CHECKPOINT DE RETOMAR — creado 2026-08-16 (inicio reparaciones)
> Si algo sale mal DURANTE las reparaciones, volver a este punto.
- Estado del repo en este checkpoint: equivalente al snapshot inicial (ver Contexto arriba).
  Al inicio de reparaciones: HEAD `a5af5cc`, ~10 staged, ~11 modified unstaged.
- Regla de oro del cableado: NUNCA dejar al agente sin memoria. Antes de tocar el
  cableado de memoria (unified_memory / Qdrant / Nomic / bridge), este checkpoint ya
  existe + queda un doc de estado en disco + puntero persistente en las celdas.
- NO se commitea nada en este checkpoint (respaldar ≠ commitear, según orden del Líder).
- Orden de reparaciones acordado:
  1. Verificación funcional de memoria (Qdrant 81 / Nomic 81) — solo VALIDA, no modifica.
  2. mypy puntuales: external_skills.py + skill_registry import.
  3. Tests: test_prometheus mock + helper impuro odoo_sync (datetime.now).
  4. Gateway pre-commit: `pre-commit run mypy --files <archivos>`.

## Nota
- No se ejecutó ni se commiteó nada nuevo en este respaldo.
- El estado exacto puede haber cambiado si hubo commits tras el snapshot inicial
  (verificar con git antes de retomar).