# FRENTE R2-API — Nucleo logico de la API

## Mision

Endurecer y verificar el nucleo logico del sistema. Su material de
trabajo son los modulos de Python bajo `core/` y `api/`.
NO toca infraestructura (eso es R1) NI esquema de base de datos (eso es R3).

## Worktree asignado (VERIFICADO 2026-10-01)

```
/mnt/ssd_trabajo/10-r2-api     rama: 10-r2-api
  base: 5cc44536 (snapshot: 20261001_060201)
  creado con: git worktree add /mnt/ssd_trabajo/10-r2-api 10-r2-api
```

## Archivos bajo tu responsabilidad (8228 lineas Python verificadas)

```
core/                      circuit_breaker.py, config.py, cost_guard.py,
                           crypto.py, fusion.py, judge.py, logger.py,
                           meta_client.py, openrouter_client.py,
                           prometeo_approval.py, qwen_client.py,
                           rate_limiter.py, workload_router.py
api/                       main.py, bridge.py, guardrail.py, pod_router.py,
                           banking_webhooks.py, meta_client.py,
                           unified_messenger.py, webhook_meta.py,
                           routes/dispatch.py, webhooks/
 tests/unit/ tests/smoke/     tests de este frente
```

## FUERA de tu permiso

```
infra/  scripts/  systemd/  db/migrations/    → son de R1 y R3
agentes/  → solo lectura, salvo tu propio reporte
```

Si necesitas algo de esas rutas: DETENTE e informalo como BLOQUEADO.

## Hallazgo critico descubierto al crear este frente

`setUpTearDown`: NO existe `tests/conftest.py` a nivel raiz como fixture
compartida visible en la raiz de tests/. Antes de inventar fixtures,
verifica si `tests/conftest.py` existe:

```bash
test -f tests/conftest.py && echo EXISTE || echo NO_EXISTE
```

Si NO existe, tu primer gate fallara y deberas crearlo con las fixtures
que necesites — eso SI es trabajo tuyo y esta permitido.

## Tareas de este frente

### T1 — Verificar columnas nuevas (contrato entre R3 y R2)
Comprueba contra la BD REAL que existan:

```
api_call_log.action_type
api_call_log.backoff_count
api_call_log.consecutive_count
api_call_log.pending
```

Si NO existen: **NO las crees**. Eso es de R3. Repórtalo como BLOQUEADO
con el texto exacto del error. Coordinas con PROMETEO, no lo resuelvas solo.

### T2 — Firmar peticiones salientes
Toda peticion saliente debe llevar firma. Reglas:
- Header con marca de tiempo fresca → 200 OK
- Timestamp viejo (replay) → rechazo **403**
- Peticion repetida (mismo idempotency) → **409 DUPLICATE**

### T3 — Guardarrail
Toda salida pasa por `guardrail.py`. Probar los tres casos del
guardarrail (permitir / bloquear / escalar) y dejar evidencia.

## Gates de validacion (ejecutar y pegar la salida REAL)

```bash
# G0 — el arbol esta en HEAD correcto
git status --porcelain

# G1 — el modulo importa limpio
python3 -c "import core.crypto, core.fusion; print('G1 OK')"

# G2 — los modulos criticos compilan
python3 -m py_compile core/*.py api/*.py

# G3 — los tests corren
timeout 600 python3 -m pytest tests/unit tests/smoke -x -q 2>&1 | tail -25
```

## Formato de reporte obligatorio

```
FRENTE: r2-api
WORKTREE: /mnt/ssd_trabajo/10-r2-api
ARCHIVOS_MODIFICADOS:
  - <ruta>
COMMITS:
  - <sha> <mensaje>
EVIDENCIA:
  $ git worktree list
  <salida real>
GATES:
  - G0 estado:  <salida real>
  - G1 imports: <salida real>
  - G2 compile: <salida real>
  - G3 tests:   <salida real, incluyendo fallos>
RIESGOS:
  - <riesgo concreto, o "ninguno">
BLOQUEADO:
  - <dependencia sin resolver, o "ninguna">
```

Si BLOQUEADO no esta vacio: FRENAR e informar. No inventar.
