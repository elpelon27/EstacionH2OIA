# 📋 DEUDAS TÉCNICAS Y PROYECTOS - Estación H2O / Valentina
**Última actualización:** 2026-08-13 (corte Fase A/B/C/D) | **Commit:** `6877602` | **Estado CI:** ✅ GREEN

---

## ✅ DEUDAS TÉCNICAS RESUELTAS (Este sprint)

| ID | Deuda | Acción tomada | Commit |
|---|---|---|---|
| **DT-02** | ~72 errores mypy en core/ y skills/ | Type hints genéricos, `TypeVar`, `Awaitable`, overrides ortools | `55ad9c7` → `44d9f6e` |
| **DT-03** | Ruff E402/F841/E501/N806 en api/bridge.py | Imports locales, variables usadas, líneas <100 | `9d6cdf9` |
| **DT-04** | Backup off-site sin remote funcional | OAuth gdrive-personal + script backup_db.sh | `44d9f6e` |
| **DT-05** | Event in-memory no cross-process | Tabla `dispatch_notifications` + híbrido Event+SQLite | `9d6cdf9` |
| **DT-06** | prometeo-telegram sin hardening systemd | MemoryMax, CPUQuota, RestartSec exponencial, sandboxing | `9d6cdf9` |
| **DT-07** | cloudflared sin watchdog | `cloudflared-watchdog.timer` (cada 60s, HTTP health) | `c7889b5` |
| **DT-08** | Logs NVIDIA/GDM spam journalctl | `/etc/modprobe.d/nvidia.conf` con `NVreg_LogLevel=0` | `ae83637` |
| **DT-09** | Ruff errors en skills/ y src/ | `skills/`, `src/financial/`, `src/integrations/` — E501, N806, B904, SIM117, F841, unused imports, SIM102, SIM118, SIM401, E722, F402, B007, W291/W293 | `003d43e` → `a569fe2` |
| **DT-10** | mypy `unused-ignore` en 6 ubicaciones | `core/logger.py`, `skills/dispatcher.py`, `core/openrouter_client.py`, `skills/dispatch/telegram_bot.py` — limpieza type ignores | `003d43e` → `a569fe2` |
| **DT-11** | `conftest.py` mypy `no-untyped-def` | `Generator[str, None, None]` type hint + import `typing.Generator` | `c362db7` |
| **DT-13** | Tests de integración no en CI | `.github/workflows/ci.yml` + 25 integration tests passing | `e1a2b31` |
| **DT-14** | `requirements.txt` vs `pyproject.toml` drift | `[project.dependencies]` + `[project.optional-dependencies].dev` | `4263f51` |
| **DT-15** | Secrets hardcodeados en tests | `HERMES_PROJECT_ROOT` env var + fixture `reset_prometheus` autouse | `cba1637`, `c362db7` |
| **DT-16** | `UP042` str+Enum en r4/codigos.py y hmac_auth.py | Migrar a `StrEnum` (Python 3.11+) | `a569fe2` |
| **DT-17** | `E402` module imports en r4/webhooks.py | Mover imports `time`, `defaultdict` al top | `8dbc80d` |
| **DT-18** | `N805`/`B904`/`B008`/`SIM102` en r4/webhooks.py | `cls→self`, `raise from`, `Depends()`, `if` combinado | `8dbc80d` |
| **DT-19** | `F821` Undefined `Orchestrator` en memory_aware_agent | `TYPE_CHECKING` guard | `a569fe2` |
| **DT-20** | `W291` trailing whitespace en orchestrator.py | `ruff format` | `a569fe2` |
| **DT-21** | `SIM118` key in dict.keys() en external_skills.py | `ruff --fix` | `a569fe2` |
| **DT-22** | `B007` unused loop var en external_skills.py | `_` convention | `a569fe2` |
| **DT-23** | `E501` long lines en unified_memory.py | `src/memory/unified_memory.py:243,253` — strings concatenadas | `6877602` |
| **DT-24** | `E501` long lines en external_skills.py | `src/orchestration/external_skills.py:223` — path concatenado | `6877602` |
| **DT-25** | `E501`/`W293`/`B008` residual en r4/webhooks.py | Código comentado refactorizado, `Depends` singleton, `field_validator`, newline | `e6768fc` |
| **DT-26** | `E501` docstrings en orchestrator.py | 5 docstrings refactorizadas a strings concatenadas | `e6768fc` |
| **FASE 7 Seguridad** | Hardening bridge.py + infra | Rate limiting dual (IP + teléfono), payload validation, input sanitization, logrotate, backup_daily.sh, fail2ban script | `f30037c` |

## 🎯 AUDITORÍA MILIMÉTRICA + SANITIZACIÓN COMPLETA (2026-08-13) — RESUELTO
| Ítem | Deuda | Acción tomada |
|------|-------|---------------|
| **H1-P0** | 5 cron jobs "fantasma" (analytics, route, checkin, fs_reporte, recordatorios) NO se ejecutaban | Reactivados en crontab + verificados manualmente (todos exit 0) |
| **H2-P0** | 22 NULLs en fs_pedidos.monto_total_ves | Backfill idempotente eur×tasa → 0 NULLs, auditado |
| **H3-P1** | INSERT fs_pagos referenciaba columna `tasa_eur_ves` inexistente (schema v3.1) | **BUG REAL PRODUCCIÓN**: corregido a `tasa_eur_ves_pago` en database.py:794,860. Habría roto toda verificación de pago |
| **H4-P1** | 37 tests rotos pre-existentes | Suite completa: **316 passed, 0 failed** |
| **H8-P0** | Disco raíz 68%; journald sin límite (523M) | límites journald (SystemMaxUse=200M) + vacuum → 117M |
| **H10-P1** | Cron Hermes vacío / scheduling disperso | Inventario único de orquestación + diagrama creados |
| **P2-5a** | Sin alertas Prometheus | 23 reglas (9 nuevas + 14 recuperadas), 0 errores |
| **P2-5b** | Sin monitoreo GPU/VRAM | gpu-exporter systemd (:9101), job 'gpu' up |
| **P2 mypy** | 46 errores core/api | 46 → **0** (tipado en 10 archivos + fix import financial_agent) |
| **P2 ruff** | E501 en archivos tocados | Divididas líneas largas (tests); quedan 7 E402 intencionales |

---

## 🔴 DEUDA TÉCNICA PENDIENTE (Bloqueante)

| ID | Deuda | Descripción | Acción requerida | Prioridad |
|---|---|---|---|---|
| **DT-01** | `vehicles.telegram_chat_id` NULL | Choferes Yordanis y Evert no pueden recibir pedidos/alertas | Pedirles que escriban `/start` a `@DespachoH2O_bot` → UPDATE vehicles SET telegram_chat_id = <id> WHERE driver_name IN ('YORDANIS','EVERT') | **CRÍTICA** (desbloquea Sprint 3 E2E Swap) |

---

## 🟡 DEUDAS TÉCNICAS IDENTIFICADAS (No bloqueantes)

| ID | Deuda | Archivos afectados | Descripción | Esfuerzo estimado |
|---|---|---|---|---|
| **DT-12** | Cobertura de tests < 35% | `core/`, `agents/`, `api/` | Solo 28% coverage; falta tests unitarios para lógica crítica (`workload_router`, `cost_guard`, `circuit_breaker`, `fusion`, `judge`, `openrouter_client`) | ~8-16h |
| **DT-27** | Lint legacy en conftest.py | `tests/conftest.py` | 34 issues (W293, E501, I001, E402, F401, SIM105, W291/292) | ~1h |

---

## 📦 PROYECTOS ACTIVOS / PLANIFICADOS

### 🚀 Sprint 3 - Swap E2E (EN PROGRESO, bloqueado en DT-01)
| Tarea | Estado | Notas |
|---|---|---|
| Registro choferes (Yordanis, Evert) | 🔴 BLOQUEADO | Requiere DT-01 |
| Check-in 8am automático | ✅ Código listo | Espera chat_ids |
| Flujo pedido: GPS → [Llegué] → [Entregado] | ✅ Código listo | `skills/dispatch/telegram_bot.py` |
| Swap loaner bottles (165 unidades) | ⏳ Pendiente | Migración 3-semanas planificada |
| Mapa de calor GPS histórico | ⏳ Pendiente | Datos = ORO para optimización rutas |

### 🛡️ Hardening & Observabilidad
| Proyecto | Estado | Descripción |
|---|---|---|
| **Prometheus + Grafana stack** | 🟡 Parcial | `/metrics` expuesto, falta dashboards + alertas |
| **Log aggregation (Loki/Promtail)** | ⏳ Pendiente | Journalctl → Loki para queries centralizadas |
| **Distributed tracing (Tempo/Jaeger)** | ⏳ Pendiente | Request flow: WhatsApp → Bridge → Dify → Meta |
| **Backup verification automatizado** | ⏳ Pendiente | Restore test mensual + alerta si falla |
| **Disaster recovery runbook** | 📝 Documentado | `docs/04-runbooks/disaster-recovery.md` |

### 🤖 Agentes & Skills
| Proyecto | Estado | Descripción |
|---|---|---|
| **Valentina WhatsApp v2** | 🟢 En producción | Recibe pedidos, responde FAQ, escala a humano |
| **Dispatcher Telegram Bot** | 🟢 En producción | Check-in 8am, GPS, botones entrega |
| **Financial Shield v3.0** | 🟢 En producción | Cuentas por cobrar, verificación bancaria, anti-fraude |
| **Prometeo Telegram** | 🟢 En producción | Kill switch, approvals, status, logs |
| **WorkloadRouter** | 🟢 En producción | NIM → OpenRouter → fusion, cost guard, circuit breaker |
| **Unified Memory (mem0 + Ollama)** | 🟡 Instalado, no integrado | Qdrant + Redis + mem0 listos para activar |

### 📚 Documentación & Runbooks
| Proyecto | Estado | Ubicación |
|---|---|---|
| **Arquitectura 2026-08-07** | ✅ Completo | `docs/02-arquitectura/ARQUITECTURA_2026-08-07.md` |
| **Runbooks operativos** | ✅ 15 runbooks | `docs/04-runbooks/` |
| **Runbook CI/CD** | ⏳ Pendiente | Crear `docs/04-runbooks/ci-cd.md` |
| **Runbook Swap bottles** | ⏳ Pendiente | Crear `docs/04-runbooks/swap-bottles.md` |
| **Runbook Disaster Recovery** | 📝 Esbozo | `docs/04-runbooks/disaster-recovery.md` |

---

## 🎯 PRÓXIMOS PASOS RECOMENDADOS (Orden de prioridad)

### Inmediato (Esta semana)
1. **DT-01** → Obtener chat_ids de Yordanis y Evert → Desbloquear Sprint 3
2. **DT-27** → Limpieza conftest.py legacy (~1h)

### Corto plazo (2-3 semanas)
3. **DT-12** → Subir coverage a >60% en core/ (prioridad: `workload_router`, `cost_guard`, `circuit_breaker`, `fusion`, `judge`, `openrouter_client`)
4. **Activar Unified Memory** → Qdrant + Redis + mem0 para memoria semántica persistente

### Mediano plazo (1-2 meses)
5. **Prometheus + Grafana + Loki** → Observabilidad completa
6. **Swap bottles migración** → Ejecutar plan 3-semanas
7. **Runbooks completos** → Deploy, rollback, swap, disaster recovery

---

## 📊 MÉTRICAS DE SALUD DEL PROYECTO

| Métrica | Actual | Objetivo |
|---|---|---|
| **CI/CD Status** | ✅ GREEN | GREEN |
| **Tests passing** | 149/149 (core/bridge/financial) | 100% |
| **Coverage (core)** | ~28% | >60% |
| **Mypy errors (core/api)** | 0 | 0 |
| **Ruff errors (core/api)** | 0 | 0 |
| **Ruff errors (skills/src financial/r4/odoo)** | 0 | 0 |
| **Ruff errors (todo repo)** | ~20 | 0 |
| **Mypy warnings (todo repo)** | ~6 | 0 |
| **Deploy frequency** | Manual | Weekly |
| **MTTR (Mean Time To Recovery)** | ~15min | <10min |

---

## 🔗 ENLACES ÚTILES

- **Repo:** https://github.com/elpelon27/EstacionH2OIA
- **CI/CD Runs:** https://github.com/elpelon27/EstacionH2OIA/actions
- **Vault Obsidian:** `docs/` (symlink a `~/Documentos/Obsidian Vault`)
- **Server:** `/mnt/ssd_trabajo/hermes-agent`
- **Bot Choferes:** `@DespachoH2O_bot`
- **Bot Líder:** `@Skynet_27_bot`

---

*Documento vivo - Actualizado tras cada sprint o cambio significativo* 💧