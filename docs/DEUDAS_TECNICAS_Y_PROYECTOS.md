# 📋 DEUDAS TÉCNICAS Y PROYECTOS - Estación H2O / Valentina
**Última actualización:** 2026-08-17 (import circular eliminado + mypy 0 + coverage 61%) | **Estado CI:** ✅ GREEN

## 🔒 BRECHA DE SEGURIDAD — CERRADA 2026-08-16 (API keys NVIDIA)
> `scripts/prometeo/hybrid_llm.py` tenía 3 API keys NVIDIA hardcodeadas (nvapi-*), expuestas
> en git history (commit 3b0d813). RESUELTO:
> - El archivo orquestaba 3 APIs NVIDIA que el Líder confirmó **descontinuadas** → **eliminado** (`git rm`).
> - 3 variables NVIDIA (NEMOTRON/GLM/DEEPSEEK) eliminadas del .env (inútiles).
> - Se conservó `NVIDIA_API_KEY` porque `scripts/prometeo/prometeo.py` la usa activamente
>   (ya lee de .env, NO hardcodeada — no era brecha).
> - Escaneo final: 0 literales `nvapi-*` en todo el repo (src/api/skills/scripts/core/tests).
> - Verificación: suite 345 passed / 14 skipped / 0 failures.
> - Claves comprometidas en git history quedan "muertas" (sin rotación, APIs descontinuadas).

## 🎯 CAMPAÑA MYPY — COMPLETADA 2026-08-16 (gate pre-commit v1.14.0)
> (Ver detalle completo en la sección CAMPAÑA MYPY más abajo.)
> Re-medido con el gate del repo: la deuda era ~93 errores (no 208 como el informe),
> concentrada en scripts/. TODA llevada a 0. Ver bloque detallado tras DEUDAS RESUELTAS.

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

## 🎯 DT-12 COBERTURA — EN PROGRESO 2026-08-16 (plan fraccionado)

### F1 ✓ LÍNEA BASE (medida con datos, 2026-08-16)
> Re-medición real de cobertura del perímetro (pytest-cov sobre tests/):
> - **api/bridge.py: 28%** (1425 stmts, 1028 miss) — NO 17% como decía el doc anterior.
> - **core/prometeo_approval.py: 65%** (178 stmts, 62 miss) — NO 0% como decía el doc anterior.
> - Total repo: 48% (3081 stmts, 1589 miss) — NO 38% documentado.
> Conclusión: el doc de deuda estaba desactualizado; el punto de partida real es mejor.
> Tests existentes ya cubren: _calc_total, _format_product_desc, _phone_hash, _detect_message_type,
> _fix_total_in_response, _sanitize_input_text, _verify_meta_signature.

### F2 🔄 core/prometeo_approval.py (65% → subir) — SUBAGENTE lanzado
> Objetivo: cubrir ramas de error (except del polling de request_approval, respuesta no-str en
> validation, input con None, else del while con timeout, get_pending con JSON corrupto,
> complete/cancel en ramas except). Crea tests/unit/test_prometeo_approval_coverage.py.

### F2 ✓ core/prometeo_approval.py 65% → 75% (COMPLETADA y VERIFICADA 2026-08-16)
> Subagente creó tests/unit/test_prometeo_approval_coverage.py (10 tests). VERIFICADO con datos:
> - core/prometeo_approval.py: **65% → 75%** (178 stmts, quedan 45 sin cubrir solo líneas 285-337).
> - Líneas nuevas cubiertas: 181-190 (except polling + expiración en while), 204 (sudo vacío→ValueError),
>   214 (validation no-str→bool), 217/219 (input None, type desconocido), 234-235 (get_pending JSON corrupto),
>   262-264 (complete except), 271/279-280 (cancel inexistente/except).
> - 285-337 = bloque CLI (__main__) NO cubierto a propósito: requiere subproceso + tocaría data/ real.
> - Tests verificado: 10 passed. Suite global intacta.

### F3 ✓ api/bridge.py — SUBAGENTE COMPLETADO y VERIFICADO (2026-08-16)
> Subagente creó tests/unit/test_bridge_coverage.py (48 tests, 21KB). VERIFICADO con datos:
> - api/bridge.py **28% → 29%** con tests unit (antes 1173 miss → 1013 miss, elimina 160 líneas).
> - Funciones nuevas cubiertas: _convert_eur_to_bs, _get_out_of_hours_message,
>   _is_within_business_hours, _validate_meta_payload, _is_duplicate, _is_kill_switch_active,
>   _get_state/_set_state/_clear_state, _save/get/clear_order_totals, _nearest_zone_id, _check_tcp_up.
> - Mockeos usados (sin red, sin secretos reales): datetime fake Caracas, socket a puerto cerrado,
>   SQLITE_PATH a tmp db, KILL_SWITCH_FILE a tmpfile, META_APP_SECRET="test".
> - NOTA: subagente dejó lineas_extra en estado inicial; se depuró y quedó 48 passed limpio.
> - NO toca api/bridge.py ni test_bridge.py ni test_bridge_helpers.py (git status: solo ?? nuevo).

### F4 ✓ VERIFICACIÓN GLOBAL — DT-12 fracción CERRADA (2026-08-16)
> - Suite completa: 345 → **403 passed** (+58 tests de F2 y F3), 14 skipped, 0 failures.
> - Cobertura agregada: core/prometeo_approval 75% (era 65%), api/bridge 29% (era 28%).
> - Total repo sube de 48% a ~50% estimado (medible en cierre de sprint).
> - 2 archivos de test nuevos (untracked): test_prometeo_approval_coverage.py, test_bridge_coverage.py.
> - Regla cumplida: NO se modificó código de producción para "hacer pasar" tests; solo tests nuevos.
> Proyecto: DT-12 completo (elevar coverage total) sigue como objetivo de sprint; esta fracción
> cubrió el perímetro bridge + prometeo_approval. Pendiente: subir api/bridge.py sustancialmente
> (requiere mockear Dify/Telegram/Meta → mayor esfuerzo) y otros módulos de baja cobertura.

### F5 🔄 api/bridge.py — funciones de red con mock (Dify/Telegram/Meta) — SUBAGENTE EN CURSO
> Siguiente fracción DT-12 (paralela a F6). Objetivo: cubrir funciones async del bridge que
> tocan servicios externos mockeando dependencias (SIN red real):
> _send_whatsapp_message/_send_whatsapp_interactive (Meta), _call_dify (Dify), _send_telegram/
> _alert_critical (Telegram), _send_to_dispatch_queue (SQLite), _convert_eur_to_bs.
> Mock: bridge._http_client via AsyncMock; META/DIFY a valores test; reset _seen_messages/_conversation_state;
> SQLITE_PATH a tmp. Crea tests/unit/test_bridge_network.py. Guardas: sin red, no tocar producción.

### F5 ✓ api/bridge.py — funciones de red con mock — COMPLETADO y VERIFICADO (2026-08-16)
> Subagente creó tests/unit/test_bridge_network.py (26 tests, 16KB). VERIFICADO con datos:
> - api/bridge.py **29% → 38%** con tests unit (887 miss, +160 líneas cubiertas de red).
> - Cubre: _send_whatsapp_message, _send_whatsapp_interactive (button/list/header/footer/no-soporte),
>   _call_dify (éxito/conv_id/sin-key/status≠200/HTTPError), _send_telegram (disabled/bot-None/éxito/except),
>   _alert_critical, _send_to_dispatch_queue (INSERT feliz, sin GPS, fail-soft DB inexistente), _convert_eur_to_bs.
> - Mocks: bridge._http_client (AsyncMock), _telegram_bot, core.workload_router en sys.modules
>   (evita fallback HTTP real a localhost:8000), SQLITE_PATH a tmp, reset _seen_messages/_conversation_state.
> - NO toca api/bridge.py ni tests existentes. Sin red real. Sin secretos reales.
> - Suite completa integrada: 429 passed / 14 skipped / 0 failures.

### F6 ✓ CONECTAR UNIFIED MEMORY AL AGENTE ACTIVO — COMPLETADA (2026-08-16)
> Gap encontrado: el bot activo /memory semantic hacía búsqueda LITERAL (grep) en el vault,
> NO usaba la memoria semántica certificada (Qdrant). Integración aplicada y DESPLEGADA:
> - skills/prometeo_telegram.py: /memory semantic ahora consulta UnifiedMemory (Qdrant, 5 hits)
>   con FALLBACK a grep si la semántica falla (nunca rompe; búsqueda degrada graceful).
> - VERIFICADO: py_compile OK, ruff limpio (producción), y la lógica real devuelve 5 resultados
>   semánticos de Qdrant (scores 0.68-0.78: deudas técnicas, SOUL, RESUMEN_RETOMAR).
> - DESPLIEGUE: prometeo-telegram.service reiniciado (MainPID 922698 → 2943914, nuevo = carga el
>   cambio). Bot operativo (polling getUpdates 200 OK). Error NetworkError httpx.ReadError al
>   arranque era transitorio de Telegram (no relacionado con F6) y se auto-recuperó.
> - Backup del archivo: /tmp/prometeo_telegram.py.backup_<ts>.

## 🎯 DT-27 LINT CONFTEST.PY — COMPLETADO 2026-08-16
> Re-medido con datos: los 34 issues del doc (W293, E501, I001, E402, F401, SIM105, W291/292)
> YA estaban a 0 (ruff check limpio — doc desactualizado). El resto real era FORMATO:
> `ruff format` aplicado a tests/conftest.py (33+/34-, cambio de forma puro, sin tocar lógica).
> VERIFICADO: ruff format --check limpio, ruff check limpio, suite completa 429 passed / 0 failures.
> Backup: /tmp/conftest.py.backup_<ts>.

## 🎯 OBSERVABILIDAD — COMPLETADO 2026-08-16 (Prometheus/Grafana)
> Diagnóstico real: Prometheus ya evaluaba 23 reglas de alerta (saludable, 0 firing); el gap era
> que Grafana vivía sin dashboards (el mount solo traía datasources). RESUELTO:
> - Conectados los 4 dashboards del repo a Grafana vivo: copiado monitoring/grafana/ ->
>   infra/grafana/provisioning/dashboards/ (dashboards.yml + 4 JSON) + reload provisioning (HTTP 200).
> - VERIFICADO (API Grafana autenticada): 4 dashboards cargados — Dispatcher, Financial Shield,
>   SWAP Bottle Inventory, Valentina Bridge Overview.
> - Flujo de datos CONFIRMADO: Grafana con uid datasource real (PBFA97CFB590B2093) consulta
>   Prometheus y ve 4 targets up: node/hermes/prometheus/gpu = 1.
> - Alertas: 23 reglas activas, 0 firing (todo sano).
> - Backup: /tmp/obs_backup/prometheus.yml.
> PENDIENTE para otra sesión (stack ampliado, no bloqueante): Loki/Promtail (log agg) + Tempo (tracing).

## 🎯 CAMPAÑA MYPY — COMPLETADA 2026-08-16 (gate pre-commit v1.14.0)
> Re-medición real: la deuda era ~93 errores (no 208), concentrada en scripts/. TODA LIMPIADA.
> Archivos llevados a 0 errores (gate oficial): r4banco_test(24→0), boot_alert(14→0),
> r4_update_tasa_bcv(10→0), banco_verificador(4→0), api/banking_webhooks(4→0),
> hybrid_llm(8→0), odoo_inventario_insumos(5→0), odoo_reporte_ventas_diarias(4→0),
> sheets_sync(3→0), odoo_nomina_viernes(3→0), odoo_inventario_hielo(3→0),
> odoo_cierre_semanal(3→0), health_check(2→0), telegram_bot(1→0), prometeo(1→0),
> security_check(4→0).
> Patrón aplicado: anotaciones de retorno con tipos reales (no solo -> None), dict[str,Any],
> `# type: ignore[misc]` en decoradores slowapi (idiomatico), bool() para Chat.id Any-mixed.
> Verificación final: 16 archivos todos a 0, py_compile OK, suite 345 passed / 14 skipped / 0 fail.
> ⚠️ SECURITY DEUDA (no tocada a lo bruto): scripts/prometeo/hybrid_llm.py tiene API keys
> NVIDIA hardcodeadas (nvapi-*). Sacar a variables de entorno es pendiente de seguridad.

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

## 🐍 DEUDA MYPY — COMPLETADA 2026-08-17 (0 errores)

> Re-medición final con gate mypy 1.20.2 (python3.12, strict=true).
> Historial: el doc anterior decía 208 errores → la realidad eran 89 al medir →
> se limpiaron 27 quick wins (25 unused-ignore + 2 redundant-cast) →
> 63 restantes limpiados por subagente → **0 errores en 89 archivos**.
>
> Bug encontrado y reparado: api/unified_messenger.py tenía syntax error
> (tags XML pegados accidentalmente + _make_send duplicado) — reparado.
>
> Import circular eliminado: api/meta_client.py importaba _phone_hash de
> api/bridge.py en 3 lugares. Ahora importa hash_phone de core/crypto.py directamente.


---

## 🔴 DEUDA TÉCNICA PENDIENTE (Bloqueante)

| ID | Deuda | Descripción | Acción requerida | Prioridad |
|---|---|---|---|---|
| **DT-01** | `vehicles.telegram_chat_id` NULL | Choferes Yordanis y Evert no pueden recibir pedidos/alertas | Pedirles que escriban `/start` a `@DespachoH2O_bot` → UPDATE vehicles SET telegram_chat_id = <id> WHERE driver_name IN ('YORDANIS','EVERT') | **CRÍTICA** (desbloquea Sprint 3 E2E Swap) |

---

## 🟡 DEUDAS TÉCNICAS IDENTIFICADAS (No bloqueantes)

| ID | Deuda | Archivos afectados | Descripción | Esfuerzo estimado |
|---|---|---|---|---|
| **DT-12** | Cobertura de tests | `core/`, `agents/`, `api/` | ✅ EN PROGRESO: core/ al 61% (3116 stmts, 1214 miss). 580 passed. Modulos al 100%: meta_client, crypto, logger, qwen_client, judge, circuit_breaker, fusion, config, openrouter_client, rate_limiter, unified_messenger, guardrail, workload_router (99%). Pendiente: api/bridge.py (38%), src/orchestration/ (0%), src/financial/ (25-41%). | ~8-16h → reducido |
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
| **Unified Memory (mem0 + Ollama)** | 🟢 Operativa | Qdrant 402pts (81/81 fuentes) + Redis + mem0. Búsqueda semántica verificada (2026-08-15) tras fix `created_at` float→ISO. Pendiente: conectar al agente activo |

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
| **Tests passing** | 580/580 (14 skipped) | 100% |
| **Coverage (core/)** | 61% | >60% ✅ |
| **Coverage (total repo)** | 36% | >45% |
| **Mypy errors (todo repo)** | 0 | 0 ✅ |
| **Ruff errors (core/api)** | 0 | 0 ✅ |
| **Ruff errors (todo repo)** | ~91 | 0 |
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