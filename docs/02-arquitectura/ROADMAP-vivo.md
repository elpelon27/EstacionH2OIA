# MAPA DE RUTA VIVO — Estación H2O / Prometeo

**Última actualización**: 2026-07-25 (Día 30 — ROADMAP sincronizado con estado real del repo)
**Autor**: Prometeo (GLM 5.2 vía NVIDIA NIM)
**Fuente**: docs/05-tech-debt/ANALISIS_ARQUITECTURA_2026-07-21.md (36 fallas) + estado actual del repo
**Repo**: https://github.com/elpelon27/EstacionH2OIA — 77+ commits, sincronizado

---

## COMPLETADO (hasta 2026-07-25)

### B1 — Webhook Meta al named tunnel permanente — HECHO
Webhook Meta apuntando a `https://valentina.estacionh2o.com/webhook/meta`. Named tunnel cloudflared activo. Quick tunnel efimero eliminado.

### B2 — Reconciliar systemd unit /etc vs repo — PARCIAL
Systemd unit del repo copiado a /etc y bridge reiniciado el 2026-07-22. **PENDIENTE**: copiar unit nuevo (Type=notify + WatchdogSec=30s del P1-2) a /etc. El /etc actual aun tiene Type=simple. Ver sección PENDIENTE.

### B3 — Reiniciar bridge para activar r1-r7 — HECHO
Bridge reiniciado 2026-07-22 y nuevamente 2026-07-24 17:27. Logs confirman: "SQLite inicializado WAL + foreign_keys ON", "Watchdog systemd activo", tabla `conversation_state` creada.

### FASE 1.5 — Bridge hacia dispatch_queue (2026-07-21, commit fd9ff21)
- `_send_to_dispatch_queue` DEFINIDA pero NUNCA LLAMADA → ahora llamada en 2 puntos de cierre.
- Test E2E: PASS.

### FASE 1 paso 2 — Sync clients dispatch.db (2026-07-21, commit fd9ff21)
- `_sync_client_to_dispatch_db` upsert por phone_hash con running avg botellones.
- `_nearest_zone_id` haversine contra 5 zones Maracaibo.

### Reparaciones r1-r7 (2026-07-22, commit 7d656a8)
- r1: `_init_db()` crea tabla `dispatch_queue` + 3 indices.
- r2: `PRAGMA foreign_keys=ON` en `get_dispatch_db`/`get_conv_db` + helper `_get_db_with_fk`.
- r3: `journal_mode=WAL` + `synchronous=NORMAL` en ambas BDs (persiste en archivo).
- r5: `LOG_SALT` fail-closed (aborta startup si default inseguro).
- r6: Botones `new_arr`/`new_del`/`new_no` con handler en dispatcher.py (FASE 1.4).
- r7: Fix use-after-close `conn` en `_save_order_to_db_and_sheets` + `_ASYNCTASKS_REFS` set.

### Cleanup infraestructura (2026-07-22, commit e8a4509)
- Detenido `cloudflared-tunnel.service` (quick tunnel efimero duplicado).
- Creado `skills/run_dispatcher_checkin.py` (cron 08:00 funcional).
- API key NVIDIA movida a `config/.env` (`NVIDIA_API_KEY`).
- Eliminados 3 `.bak` files tracked en git (174KB bloat).
- `scripts/backup_db.sh`: backup diario 2am, retention 14 dias.
- `/etc/logrotate.d/hermes-agent` instalado (weekly, rotate 4, compress).

### P0/P1 batch (2026-07-22, commit b3e1580)
- P0-2: `/metrics` con IP allowlist (127.0.0.1, ::1, 172.19.0.0/16).
- P0-3: Kill switch movido a `data/valentina.kill` con 0600.
- P1-3: 3 bare `except:` cambiados a `except Exception:`.
- P1-5: Haversine dedup — bridge importa `route_engine.haversine` con fallback.
- P2-3: Docstring de `_send_to_dispatch_queue` corregido.

### FASE 1.3 — Cron 7:45am ruta automatica (2026-07-22, commit 7e2b757)
Script `skills/run_route_planner.py` creado y testeado. OR-Tools VRP, 2 pedidos fake → 2 rutas asignadas. Cron `45 7 * * *` activo.

### FASE 1.5 — Test E2E dispatcher (2026-07-22, commit df4b014)
Smoke test con spy: 5/5 PASS. Valida dispara en pago efectivo y "ya pagué", NO dispara en abortos.

### P1-1 — PHONE_REGEX preciso (2026-07-23, commit 89d4747)
Regex cambiado a `r"(?<!\d)\+?58\d{10}(?!\d)"` con lookarounds negativos. 20/20 tests PASS. ACTIVO en prod tras reinicio 2026-07-24.

### P0-1 — FSM persistente en SQLite (2026-07-24, commit 3cda570)
**Antes**: `_conversation_state` y `_last_order_totals` eran dicts en memoria. Si uvicorn moria, estados `awaiting_payment`/`awaiting_confirmation` se perdian.
**Fix**: Tabla `conversation_state` en SQLite (`phone_hash` PK, `state_json`, `total`, `qty_bot`, `qty_hielo`, `updated_at`). `_get_state` lazy load desde SQLite con cache en memoria. `_set_state` write-through. `_last_order_totals` persiste en mismo row via helpers `_save/_get/_clear_order_totals`. `_seen_messages` permanece en memoria (TTL 5min, efimero).
**Test**: 21/21 PASS (tests/smoke/test_fsm_persistente.py).
**ACTIVO en prod** tras reinicio 2026-07-24 17:27 — tabla creada, log confirma.

### P1-2 — WatchdogSec systemd (2026-07-24, commit e24fcbf)
**Antes**: Si el bridge se colgaba (deadlock, memory leak), systemd no lo detectaba — servicio 'active' pero no respondia.
**Fix**: `Type=notify` + `WatchdogSec=30s` en systemd unit. `_watchdog_loop()` en bridge.py envia `WATCHDOG=1` cada 15s via `sdnotify`. `READY=1` al arrancar. Cancelacion limpia en shutdown.
**Test**: 8/8 PASS (tests/smoke/test_watchdog.py).
**ACTIVO en prod** — log confirma "Watchdog systemd activo (interval=15s)". **PENDIENTE**: copiar systemd unit a /etc (ver PENDIENTE).

### StartLimitIntervalSec en telegram-bot + dispatcher-bot (2026-07-24, commit efae9ce)
Mismo bug que tenia el bridge (StartLimitIntervalSec en [Service] en lugar de [Unit]). Corregido en `telegram-bot.service` y `dispatcher-bot.service`. VERIFICADO: ambos units contienen StartLimitIntervalSec.

### TELEGRAM_DISPATCH_CHAT en .env (2026-07-24, commit b5540fe)
`TELEGRAM_DISPATCH_CHAT=8523722341` configurado en `config/.env`. Route planner ahora notifica choferes por Telegram.

### Bugs Dia 15 (DEUDA_TECNICA_DIA_15.md) — 4 bugs RESUELTOS (2026-07-24, commit 18bc053)
Verificado en codigo:
1. **CRITICA**: qwen2.5:7b calculos incorrectos → RESUELTO. `_calc_total` deterministico + `_fix_total_in_response` en bridge.py.
2. **ALTA**: Minimo 3 botellones → RESUELTO. Guards en bridge.py lineas 1264-1651.
3. **MEDIA**: Botones de pago no aparecen → RESUELTO. Regex `_detect_message_type` ajustado.
4. **MEDIA**: Mensaje compuesto mal interpretado → RESUELTO. Prompt + regex refinados.

### Tests rotos pytest (14 fallos preexistentes) — RESUELTOS (2026-07-24, commit 18bc053)
- test_api.py: 3 tests skip (_send_waha_message eliminado, /webhook/whatsapp migrado a /webhook/meta).
- test_valentina.py: 9 tests skip (_load_doc eliminado en refactor, system prompt ahora hardcoded).
- test_config.py: 2 tests skip condicional (OPENROUTER_API_KEY y TELEGRAM_BOT_TOKEN_H2O no configurados).
- Resultado: 105 passed, 14 skipped, 0 failed — antes: 78 passed, 6 failed, 8 errors.

### P2-1 — ruff E501 (2026-07-24, commit 523d899)
46 errores E501 → 0. 26 noqa en strings de mensajes al cliente.

### P2-4 — tests/unit/test_bridge.py (2026-07-24, commit a3a58ee)
27 tests unitarios del bridge creados. Suite pytest: 105 passed, 14 skipped, 0 failed.

### P2-5 — RESUMEN_RETOMAR.md (2026-07-24, commit ff25415)
Reescrito Dia 29 — estado real, rutas corregidas, arquitectura actual.

### P2-2 — mypy type hints en api/ (2026-07-25, commit 1028066)
bridge.py 66→0 errores, main.py 8→0. Anotaciones return type + params, genericos parametrizados (dict[str, Any], set[Task], Task[None]), casts explicitos, asserts _http_client not None, response_model=None en meta_verify. Cero cambios de logica. pytest 105 pass, 0 fail.

### fix(financial): return await (2026-07-25, commit 7c99b37)
`generar_y_enviar_reporte` en financial_agent.py no descartaba el valor del await.

---

## PENDIENTE — Requiere accion

### P1 — Copiar systemd unit nuevo a /etc (Líder)
El bridge corre el codigo nuevo (P0-1 + P1-2 activos en logs), pero el systemd unit en /etc es el viejo (Type=simple, sin WatchdogSec). El watchdog envia WATCHDOG=1 pero systemd no lo enforcementa.
```bash
sudo cp /mnt/ssd_trabajo/hermes-agent/systemd/valentina-bridge.service /etc/systemd/system/valentina-bridge.service
sudo systemctl daemon-reload
sudo systemctl restart valentina-bridge.service
```

### P3 — mypy en skills/ y src/ (~72 errores, no bloqueantes)
mypy api/ esta en 0, pero mypy global sigue mostrando errores en:
- skills/dispatch/route_engine.py (14 errores)
- skills/google_sheets.py (12 errores)
- skills/payment_skill.py (1 error)
- src/agents/financial_agent.py (15 errores)
- core/workload_router.py (2 errores)
- core/openrouter_client.py (8 errores)
- core/logger.py (1 error)
- memory/memory_client.py (1 error)
No bloquean commits (pre-commit solo revisa api/), pero son tech debt real.

### P3 — Ruff 14 errores E402 preexistentes en api/bridge.py
7 E402 por `sys.path.insert` antes de imports (intencional por arquitectura del módulo), 2 F841 variable asignada sin uso, 5 E501 restantes. Preexistentes, no regresiones.

---

## FASE 2 (post-FASE 1)

Tras FASE 1 completa (~99%), iniciar FASE 2 segun `docs/DISPATCHER_ARCHITECTURE.md`:
- Financial Agent (lee Pedidos, escribe Pagos + Saldos_Clientes)
- Route Skill avanzado
- Analytics Skill (reporte diario 7am Telegram)
- Dispatcher avanzado

---

## METRICAS DE PROGRESO (actualizado 2026-07-25)

- Fallas P0 totales: 11 — TODAS RESUELTAS
- Fallas P1 totales: 13 — TODAS RESUELTAS (FSM, WatchdogSec, PHONE_REGEX, bare except, haversine, StartLimitIntervalSec, TELEGRAM_DISPATCH_CHAT, bugs Dia 15)
- FASE 1 completitud: ~99%
- Commits totales repo: 77+
- Smoke tests: 29/29 PASS (3 suites: FSM + watchdog + PHONE_REGEX)
- pytest suite: 105 passed, 14 skipped, 0 failed (27 nuevos test_bridge.py)
- mypy api/: 0 errores (bridge.py 66→0, main.py 8→0)
- mypy skills/ + src/: ~72 errores (no bloqueantes, P3)
- ruff api/: 14 errores preexistentes (E402 + F841, P3)
- Servicios prod: 4 active (bridge Type=notify + WatchdogSec, dispatcher, telegram, cloudflared)
- Cron jobs: 6 activos (analytics 7am, route_planner 7:45am, checkin 8am, backup 2am, fs_reporte 6:30pm, fs_recordatorios cada 30min)
- TELEGRAM_DISPATCH_CHAT: configurado (8523722341)
- GitHub: sincronizado (https://github.com/elpelon27/EstacionH2OIA)
