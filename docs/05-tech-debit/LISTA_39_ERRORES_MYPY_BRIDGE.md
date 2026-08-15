# ✅ LISTA DE ERRORES MYPY — follow-imports de `api/bridge.py`

> **Requerimiento:** LISTA DE 49 ERRORES MYPY DOCUMENTADA
>
> **Hallazgo de verificación:** el conteo "49" registrado en `DEUDAS_TECNICAS_Y_PROYECTOS.md`
> está **desactualizado**. Al ejecutar el mismo hook de pre-commit (`mirrors-mypy` v1.14.0,
> `--ignore-missing-imports`, follow-imports desde `api/bridge.py`) sobre el árbol actual,
> el resultado real es de **39 errores en 13 archivos**. Este documento es la lista
> definitiva y verificada de esos 39.

- **Fecha de captura:** 2026-08-15
- **Mando:** `pre-commit run mypy --files api/bridge.py`
- **Hook:** pre-commit hook id `mypy` (mirrors-mypy rev v1.14.0)
- **Config:** `--ignore-missing-imports`, `strict=true`, `python_version=3.12`
- **Resultado mypy:** `Found 39 errors in 13 files (checked 1 source file)`
- **Archivo base verificado:** `api/bridge.py` → arrastra 12 archivos más vía follow-imports

---

## Resumen por archivo

| Archivo | Errores | Código(s) |
|---------|:-------:|-----------|
| api/routes/dispatch.py | 10 | misc |
| api/bridge.py | 8 | misc (6), unused-ignore (1), no-any-return (1) |
| src/financial/verificacion.py | 4 | unused-ignore (3), no-any-return (1) |
| src/integrations/r4/webhooks.py | 3 | misc |
| skills/google_sheets.py | 2 | unused-ignore |
| skills/dispatch/telegram_bot.py | 2 | unused-ignore |
| skills/dispatcher.py | 2 | unused-ignore |
| api/webhook_meta.py | 2 | misc |
| api/guardrail.py | 2 | unused-ignore |
| core/workload_router.py | 1 | unused-ignore |
| core/logger.py | 1 | unused-ignore |
| core/judge.py | 1 | unused-ignore |
| core/fusion.py | 1 | unused-ignore |

**Total:** 39

## Resumen por código de error

| Código | Conteo | Naturaleza |
|--------|:------:|------------|
| `misc` | 21 | `Untyped decorator makes function "…" untyped` |
| `unused-ignore` | 16 | `Unused "type: ignore" comment` |
| `no-any-return` | 2 | `Returning Any from function declared to return "…"` |

---

## Ejecución verificada (salida truncada a los puntos señalados)

Focal: `api/bridge.py` hub → **checked 1 source file**, 13 archivos involucrados.

---

## LISTA DETALLADA — 39 errores

### A. `misc` — Funciones con decorador sin tipar (21)

En todos los casos: el patrón FastAPI/externas decoradas devuelve la función sin anotación,
lo que `strict` marca como untyped. **Fix:** anotar el decorador (tipar su `*args/**kwargs`
y `Callable`) o añadir `# type: ignore[misc]` intencionado tras tipar la decoradora.

| # | Ubicación | Error |
|---|-----------|-------|
| 1 | src/integrations/r4/webhooks.py:494 | Untyped decorator makes function "r4_consulta_webhook" untyped |
| 2 | src/integrations/r4/webhooks.py:538 | Untyped decorator makes function "r4_notifica_webhook" untyped |
| 3 | src/integrations/r4/webhooks.py:588 | Untyped decorator makes function "r4_webhook_health" untyped |
| 4 | api/webhook_meta.py:64 | Untyped decorator makes function "verify_webhook" untyped |
| 5 | api/webhook_meta.py:82 | Untyped decorator makes function "webhook_meta" untyped |
| 6 | api/routes/dispatch.py:70 | Untyped decorator makes function "compute_route" untyped |
| 7 | api/routes/dispatch.py:89 | Untyped decorator makes function "update_delivery" untyped |
| 8 | api/routes/dispatch.py:105 | Untyped decorator makes function "record_gps" untyped |
| 9 | api/routes/dispatch.py:126 | Untyped decorator makes function "get_vehicles_status" untyped |
| 10 | api/routes/dispatch.py:142 | Untyped decorator makes function "get_bottles_inventory" untyped |
| 11 | api/routes/dispatch.py:157 | Untyped decorator makes function "check_geofence" untyped |
| 12 | api/routes/dispatch.py:172 | Untyped decorator makes function "notify_driver" untyped |
| 13 | api/routes/dispatch.py:200 | Untyped decorator makes function "telegram_webhook" untyped |
| 14 | api/routes/dispatch.py:218 | Untyped decorator makes function "health_check" untyped |
| 15 | api/routes/dispatch.py:233 | Untyped decorator makes function "process_queue" untyped |
| 16 | api/bridge.py:2908 | Untyped decorator makes function "root" untyped |
| 17 | api/bridge.py:2928 | Untyped decorator makes function "metrics" untyped |
| 18 | api/bridge.py:2989 | Untyped decorator makes function "health" untyped |
| 19 | api/bridge.py:3048 | Untyped decorator makes function "meta_verify" untyped |
| 20 | api/bridge.py:3072 | Untyped decorator makes function "meta_webhook" untyped |
| 21 | api/bridge.py:3073 | Untyped decorator makes function "meta_webhook" untyped (2ª decoración) |

### B. `unused-ignore` — `# type: ignore` innecesarios (16)

Indican que un `# type: ignore` previo ya no es necesario (probablemente quedó obsoleto al
limpiar el tipado, o la línea a la que aplicaba se movió). **Fix:** eliminar el comentario
`# type: ignore` (mypy en `strict` exige que todo `ignore` esté justificado).

| # | Ubicación | Detalle |
|---|-----------|---------|
| 22 | core/logger.py:62 | type: ignore sin uso |
| 23 | skills/google_sheets.py:91 | type: ignore sin uso |
| 24 | skills/google_sheets.py:94 | type: ignore sin uso |
| 25 | api/guardrail.py:45 | type: ignore sin uso |
| 26 | api/guardrail.py:47 | type: ignore sin uso |
| 27 | src/financial/verificacion.py:43 | type: ignore sin uso |
| 28 | src/financial/verificacion.py:73 | type: ignore sin uso |
| 29 | src/financial/verificacion.py:349 | type: ignore sin uso |
| 30 | core/judge.py:129 | type: ignore sin uso |
| 31 | core/fusion.py:112 | type: ignore sin uso |
| 32 | skills/dispatcher.py:304 | type: ignore sin uso |
| 33 | skills/dispatcher.py:418 | type: ignore sin uso |
| 34 | skills/dispatch/telegram_bot.py:355 | type: ignore sin uso |
| 35 | skills/dispatch/telegram_bot.py:558 | type: ignore sin uso |
| 36 | core/workload_router.py:262 | type: ignore sin uso |
| 37 | api/bridge.py:2899 | type: ignore sin uso |

### C. `no-any-return` — retorno `Any` contra Return Type (2)

**Fix:** anotar el valor devuelto (cast/captura del valor con su tipo real) en lugar de
devolver `Any` hacia una firma tipada.

| # | Ubicación | Error |
|---|-----------|-------|
| 38 | src/financial/verificacion.py:460 | Returning Any from function declared to return "bytes \| None" |
| 39 | api/bridge.py:614 | Returning Any from function declared to return "str" |

---

## Recomendación de abordaje

1. **B (16 × unused-ignore):** trato mecánico — borrar los `# type: ignore` obsoletos.
   Limpia 16 de 39 y despeja ruido. Verificar que no reintroduzca errores: correr
   `./venv/bin/mypy <archivo> --ignore-missing-imports`.
2. **A (21 × misc):** tipar los 3 patrones de decorador repetidos (webhooks_meta,
   routes/dispatch, bridge). Un solo fix de decoradora reutilizable elimina ~21.
3. **C (2 × no-any-return):** corregir el retorno en `verificacion.py:460` y `bridge.py:614`.
4. Re-correr el hook completo hasta obtener `Found 0 errors`.