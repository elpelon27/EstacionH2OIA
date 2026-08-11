# 📋 DEUDAS TÉCNICAS Y PROYECTOS - Estación H2O / Valentina
**Última actualización:** 2026-08-11 | **Commit:** `003d43e` | **Estado CI:** ✅ GREEN

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
| **DT-09** | Ruff errors en skills/ y src/ | `skills/`, `src/financial/`, `src/integrations/` — E501, N806, B904, SIM117, F841, unused imports, SIM102, SIM118, SIM401, E722, F402, B007, W291/W293 | `003d43e` |
| **DT-10** | mypy `unused-ignore` en 6 ubicaciones | `core/logger.py`, `skills/dispatcher.py`, `core/openrouter_client.py`, `skills/dispatch/telegram_bot.py` — limpieza type ignores | `003d43e` |
| **FASE 7 Seguridad** | Hardening bridge.py + infra | Rate limiting dual (IP + teléfono), payload validation, input sanitization, logrotate, backup_daily.sh, fail2ban script | `f30037c` |

---

## 🔴 DEUDA TÉCNICA PENDIENTE (Bloqueante)

| ID | Deuda | Descripción | Acción requerida | Prioridad |
|---|---|---|---|---|
| **DT-01** | `vehicles.telegram_chat_id` NULL | Choferes Yordanis y Evert no pueden recibir pedidos/alertas | Pedirles que escriban `/start` a `@DespachoH2O_bot` → UPDATE vehicles SET telegram_chat_id = <id> WHERE driver_name IN ('YORDANIS','EVERT') | **CRÍTICA** (desbloquea Sprint 3 E2E Swap) |

---

## 🟡 DEUDAS TÉCNICAS IDENTIFICADAS (No bloqueantes)

| ID | Deuda | Archivos afectados | Descripción | Esfuerzo estimado |
|---|---|---|---|---|
| **DT-11** | `conftest.py` mypy `no-untyped-def` | `conftest.py` | Fixture sin type hint | ~15min |
| **DT-12** | Cobertura de tests < 35% | `core/`, `agents/`, `api/` | Solo 28% coverage; falta tests unitarios para lógica crítica | ~8-16h |
| **DT-13** | Tests de integración no corren en CI | `tests/integration/` | Requieren BD real, services, secrets | ~4h (mock infra) |
| **DT-14** | `requirements.txt` vs `pyproject.toml` drift | Ambos archivos | `pyproject.toml` no tiene `[project.dependencies]` | ~30min |
| **DT-15** | Secrets hardcodeados en tests | `tests/unit/test_kill_switch.py`, `tests/unit/test_api.py` | Paths `/mnt/ssd_trabajo/...` hardcoded | ~1h |
| **DT-16** | `UP042` str+Enum en r4/codigos.py y hmac_auth.py | `src/integrations/r4/codigos.py:13`, `src/integrations/r4/hmac_auth.py:18` | Migrar a `StrEnum` (Python 3.11+) | ~30min |
| **DT-17** | `E402` module imports en r4/webhooks.py | `src/integrations/r4/webhooks.py:97,98` | Mover imports al top | ~15min |
| **DT-18** | `N805`/`B904`/`B008` en r4/webhooks.py | `src/integrations/r4/webhooks.py` | self naming, raise from, Depends defaults | ~1h |
| **DT-19** | `F821` Undefined `Orchestrator` en memory_aware_agent | `src/orchestration/memory_aware_agent.py:41` | Import o TYPE_CHECKING guard | ~15min |
| **DT-20** | `W291` trailing whitespace en orchestrator.py | `src/orchestration/orchestrator.py:408` | ruff format | ~5min |
| **DT-21** | `SIM118` key in dict.keys() en external_skills.py | `src/orchestration/external_skills.py:651` | ruff fix | ~5min |
| **DT-22** | `B007` unused loop var en external_skills.py | `src/orchestration/external_skills.py:662` | `_` convention | ~5min |
| **DT-23** | `E501` long lines en unified_memory.py | `src/memory/unified_memory.py:243,253` | Refactor strings | ~30min |
| **DT-24** | `E501` long lines en external_skills.py | `src/orchestration/external_skills.py:223` | Refactor | ~15min |

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
2. **DT-11/DT-14/DT-15** → conftest.py, requirements sync, secrets en tests (quick wins ~2h)
3. **Runbook CI/CD** → Documentar workflow actual

### Corto plazo (2-3 semanas)
4. **DT-16/DT-17/DT-18** → UP042 StrEnum, E402 imports, N805/B904/B008 en r4/webhooks
5. **DT-19/DT-20/DT-21/DT-22** → Limpieza orchestration/memory (F821, W291, SIM118, B007)
6. **DT-12** → Subir coverage a >60% en core/ (prioridad: `workload_router`, `cost_guard`, `circuit_breaker`)
7. **DT-13** → Tests integración con testcontainers o mocks
8. **Activar Unified Memory** → Qdrant + Redis + mem0 para memoria semántica persistente

### Mediano plazo (1-2 meses)
9. **Prometheus + Grafana + Loki** → Observabilidad completa
10. **Swap bottles migración** → Ejecutar plan 3-semanas
11. **Runbooks completos** → Deploy, rollback, swap, disaster recovery

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

*Documento vivo - Actualizar tras cada sprint o cambio significativo* 💧