# MINUTA DE DESARROLLO — WorkloadRouter Guards Implementation
**Fecha:** 2026-08-07  
**Autor:** PROMETEO (Hermes Agent)  
**Rama:** main (directo en servidor)  
**Commit:** pendiente (trabajo en working tree)

---

## 1. RESUMEN EJECUTIVO

Se implementaron **tres capas de protección operacional** para el `WorkloadRouter` que gestiona el enrutamiento de tareas LLM en Estación H2O:

| Capa | Archivo | Función |
|------|---------|---------|
| **Cost Guard** | `core/cost_guard.py` | Bloquea llamadas a OpenRouter si gasto diario ≥ $15 (configurable); alerta a $5 |
| **Rate Limiter** | `core/rate_limiter.py` | Token bucket por modelo/proveedor (evita 429 y abuso de cuotas) |
| **Circuit Breaker** | `core/circuit_breaker.py` | State machine (CLOSED/OPEN/HALF_OPEN) para fallos en cascada |

**Integración:** `core/workload_router.py` → `execute()` ahora pasa por los 3 guards antes de llamar a cualquier LLM (OpenRouter/Fusion), con **fallback automático a Qwen local** si cualquier guard falla.

---

## 2. ARCHIVOS CREADOS

### 2.1 `core/cost_guard.py` (82 líneas)
```python
class CostGuard:
    - check() -> dict: {status: "ok"|"alerted"|"blocked", alert_sent, block_active, spent_today}
    - is_blocked() -> bool
    - _send_telegram_alert() -> async (Bot API directo)
    - reset_manual() / _reset_for_new_day() (auto a medianoche)

Thresholds desde config/.env:
- openrouter_daily_alert_usd = 5.0
- openrouter_daily_block_usd = 15.0
```
**Tests:** 7/7 passing (`tests/unit/test_cost_guard.py`)

---

### 2.2 `core/rate_limiter.py` (155 líneas)
```python
class TokenBucket:
    - capacity, refill_rate_per_sec
    - try_consume(tokens) -> bool
    - time_until_ready(tokens) -> float

class RateLimiter:
    - acquire(key, tokens=1, timeout=5.0) -> bool
    - get_status(key) -> dict (para métricas)
    - Buckets por: modelo (llm:openrouter:glm-4.5), cliente, IP, global
```
**Config:** `rate_limit_llm_per_agent_per_min = 60` (default)

---

### 2.3 `core/circuit_breaker.py` (248 líneas)
```python
class CircuitBreaker (state machine):
    CLOSED → (5 fallos) → OPEN → (60s) → HALF_OPEN → (2 éxitos) → CLOSED
    - call(func, *args) -> await func() | raise CircuitOpenError
    - Excluye: TimeoutError, ConnectionError, RuntimeError (cuentan como fallo)
    - Otras excepciones: NO cuentan (validación, etc.)

class CircuitBreakerRegistry:
    - get(name) -> CircuitBreaker (singleton por proveedor)
    - call(name, func, *args) -> shortcut
```
**Config sugerida (próxima iteración):**
- `cb_failure_threshold = 5`
- `cb_recovery_timeout_sec = 60`
- `cb_success_threshold = 2`

---

## 3. ARCHIVOS MODIFICADOS

### 3.1 `core/workload_router.py` (+170 líneas netas)
**Cambios clave en `execute()`:**

```python
# 1. Cost Guard check (solo OpenRouter/Fusion)
guard_result = await cost_guard.check()
if guard_result["status"] == "blocked":
    return await self._execute_qwen_local(messages, temperature)  # FALLBACK

# 2. Rate Limiter acquire
rate_allowed = await rate_limiter.acquire(f"llm:{provider}:{model}", timeout=5.0)
if not rate_allowed:
    return await self._execute_qwen_local(messages, temperature)  # FALLBACK

# 3. Circuit Breaker wrapper
try:
    return await self._execute_with_circuit_breaker(...)
except CircuitOpenError:
    return await self._execute_qwen_local(messages, temperature)  # FALLBACK
except Exception:
    return await self._execute_qwen_local(messages, temperature)  # FALLBACK
```

**Nuevos métodos privados:**
- `_get_provider_info(route)` → (provider_key, model_name, estimated_cost_usd)
- `_execute_with_circuit_breaker(...)` → envuelve Fusion / OpenRouter single
- `_execute_qwen_local(messages, temperature)` → fallback final unificado

---

### 3.2 `tests/unit/test_workload_router.py`
- Añadido mock de `get_cost_guard` en `test_execute_fusion`
- Test pasa sin credenciales OpenRouter reales

---

### 3.3 `tests/unit/test_cost_guard.py` (pre-existente)
- **Todos los 7 tests pasan** tras adaptar implementación a la interfaz esperada:
  - `check()` retorna dict (no `CostGuardResult`)
  - `is_blocked()` método público
  - `_send_telegram_alert()` async
  - `get_openrouter_sync()` expuesto para tests

---

## 4. FLUJO DE FALLBACK COMPLETO

```
Trigger LLM (architect_request, code_generation_*, etc.)
         │
         ▼
┌─────────────────────────────────────┐
│  Cost Guard: spent_today >= $15?    │
└─────────────────────────────────────┘
         │ NO                    │ YES
         ▼                       ▼
┌─────────────────────────────────────┐
│  Rate Limiter: tokens disponibles?  │
└─────────────────────────────────────┘
         │ NO                    │ YES
         ▼                       ▼
┌─────────────────────────────────────┐
│  Circuit Breaker: estado CLOSED?    │
└─────────────────────────────────────┘
         │ OPEN                   │ YES
         ▼                       ▼
    FALLBACK QWEN           ┌─────────────────────────────────────┐
    (local, $0, ~500ms)     │  Ejecutar LLM (OpenRouter/Fusion)   │
                            └─────────────────────────────────────┘
                                         │
                            ┌────────────┴────────────┐
                            ▼                         ▼
                       ÉXITO                      ERROR
                            │                         │
                            ▼                         ▼
                       Retornar              FALLBACK QWEN
                       respuesta             (local, $0)
```

---

## 5. CONFIGURACIÓN REQUERIDA (config/.env)

```bash
# Cost Guard
openrouter_daily_alert_usd=5.0
openrouter_daily_block_usd=15.0

# Rate Limiter (ya existía)
rate_limit_llm_per_agent_per_min=60

# Circuit Breaker (nuevos - añadir a Settings si se quiere tunear)
# cb_failure_threshold=5
# cb_recovery_timeout_sec=60
# cb_success_threshold=2

# Telegram para alertas (ya existía)
telegram_bot_token_hermes=xxx
telegram_chat_id_lider=1663148211
```

---

## 6. TESTS EJECUTADOS

```bash
# Tests específicos nuevos
pytest tests/unit/test_cost_guard.py -v        # 7 passed
pytest tests/unit/test_workload_router.py -v   # 11 passed

# Suite completa (excluyendo test_bridge.py con error pre-existente)
pytest tests/ --ignore=tests/unit/test_bridge.py -v
# 198 passed, 14 skipped, 8 errors (errores pre-existentes en test_openrouter_client.py por falta de credenciales)
```

**Cobertura nueva:**
- `core/cost_guard.py`: 77%
- `core/rate_limiter.py`: 70%
- `core/circuit_breaker.py`: 64%
- `core/workload_router.py`: 64%

---

## 7. PRÓXIMOS PASOS RECOMENDADOS (P1-P3)

| Prioridad | Acción | Esfuerzo |
|-----------|--------|----------|
| **P1** | Añadir métricas Prometheus en `execute()` (`router_requests_total`, `router_latency_seconds`, `router_fallback_total`, `router_cost_usd`) | 30 min |
| **P1** | Exponer `circuit_breaker_status` en `/health` endpoint | 15 min |
| **P2** | Configurar `cb_*` thresholds en `Settings` (pydantic) | 10 min |
| **P2** | Añadir retry con backoff en `qwen_client.py` (tenacity) | 20 min |
| **P3** | Temperature / max_tokens por trigger (config dict) | 20 min |
| **P3** | Limpiar Fusion models: quitar Claude o añadir trigger `code_generation_premium` | 10 min |

---

## 8. ARQUITECTURA RESULTADA (VISUAL)

```
┌────────────────────────────────────────────────────────────────────────┐
│                         WORKLOAD ROUTER                                │
│  resolve(trigger) → Route                                              │
└────────────────────────────┬───────────────────────────────────────────┘
                             │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
         ┌─────────┐   ┌─────────────┐ ┌────────────┐
         │ SKILLS  │   │   LLM LOCAL │ │  LLM CLOUD │
         │(Payment,│   │  (Qwen/Ollama)│ │ (OpenRouter│
         │Inventory,│   │   $0, <1s    │ │  + Fusion) │
         │Dispatch)│   └──────┬──────┘ └──────┬─────┘
         └─────────┘          │              │
                              │              ▼
                              │     ┌─────────────────┐
                              │     │   GUARDS CHAIN  │
                              │     │ 1. Cost Guard   │
                              │     │ 2. Rate Limiter │
                              │     │ 3. Circuit Brk  │
                              │     └────────┬────────┘
                              │              │
                              ▼              ▼
                       ┌───────────────────────────────┐
                       │     FALLBACK: QWEN LOCAL      │
                       │   (siempre disponible, $0)    │
                       └───────────────────────────────┘
```

---

## 9. ROLLBACK PLAN

Si algo falla en producción:
```bash
# 1. Revertir workload_router.py a versión anterior
git checkout HEAD~1 -- core/workload_router.py

# 2. Los nuevos módulos no rompen nada si no se importan
#    (son lazy-loaded dentro de execute())

# 3. Verificar: python3 -c "from core.workload_router import get_router; print('OK')"
```

---

## 10. FIRMA

**Desarrollado por:** PROMETEO (Hermes Agent)  
**Validado por:** Tests automatizados (198 passed)  
**Estado:** ✅ Listo para merge / deploy en próxima ventana de mantenimiento

---

*Documento generado automáticamente al completar la implementación. Guardar en `docs/development/minuta-workload-router-guards-20260807.md` para trazabilidad.*