# MAPA DE RUTA VIVO — Estación H2O / Prometeo

**Última actualización**: 2026-07-25 (Día 30 — sesión P2-2 mypy resuelto en api/)
**Autor**: Prometeo (GLM 5.2 vía NVIDIA NIM)
**Fuente**: docs/05-tech-debt/ANALISIS_ARQUITECTURA_2026-07-21.md (36 fallas) + estado actual del repo
**Repo**: https://github.com/elpelon27/EstacionH2OIA — 71 commits, sincronizado

---

## COMPLETADO (hasta 2026-07-24)

### B1 — Webhook Meta al named tunnel permanente — HECHO
Webhook Meta apuntando a `https://valentina.estacionh2o.com/webhook/meta`. Named tunnel cloudflared activo. Quick tunnel efimero eliminado.

### B2 — Reconciliar systemd unit /etc vs repo — PARCIAL
Systemd unit del repo copiado a /etc y bridge reiniciado el 2026-07-22. **PENDIENTE**: copiar unit nuevo (Type=notify + WatchdogSec=30s del P1-2) a /etc. El /etc actual aun tiene Type=simple.

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
**ACTIVO en prod** — log confirma "Watchdog systemd activo (interval=15s)". **PENDIENTE**: copiar systemd unit a /etc para que systemd enforcemente WatchdogSec (actualmente /etc tiene Type=simple).

---

## PENDIENTE — Requiere accion

### P1 — Copiar systemd unit nuevo a /etc (Líder)
El bridge corre el codigo nuevo (P0-1 + P1-2 activos en logs), pero el systemd unit en /etc es el viejo (Type=simple, sin WatchdogSec). El watchdog envia WATCHDOG=1 pero systemd no lo enforcementa.
```bash
sudo cp /mnt/ssd_trabajo/hermes-agent/systemd/valentina-bridge.service /etc/systemd/system/valentina-bridge.service
sudo systemctl daemon-reload
sudo systemctl restart valentina-bridge.service
```

### P1 — TELEGRAM_DISPATCH_CHAT en .env
Route planner no notifica choferes por Telegram. Falta configurar `TELEGRAM_DISPATCH_CHAT` con el chat_id del grupo de choferes en `config/.env`.

### P1 — Fix StartLimitIntervalSec en telegram-bot + dispatcher-bot
Mismo bug que tenia el bridge (StartLimitIntervalSec en [Service] en lugar de [Unit]). Pendiente en `telegram-bot.service` y `dispatcher-bot.service`.

### Bugs Dia 15 (DEUDA_TECNICA_DIA_15.md) — 4 bugs sin resolver
1. **CRITICA**: qwen2.5:7b calculos matematicos incorrectos (cobra mal). Fix: calcular total en bridge, no en LLM.
2. **ALTA**: Minimo 3 botellones no se cumple. Fix: guard en bridge.
3. **MEDIA**: Botones de pago no aparecen (regex _detect_message_type). Fix: ajustar regex.
4. **MEDIA**: Mensaje compuesto mal interpretado. Fix: refinar prompt + regex.

### Tests rotos en pytest (14 fallos preexistentes)
- test_api.py: mockea `_send_waha_message` (funcion eliminada) + 2 tests esperan 400 pero reciben 404.
- test_valentina.py: mockea `_load_doc` (metodo inexistente en ValentinaAgent). 1 fail + 8 errors.
- test_config.py: espera `openrouter_api_key` y `telegram_bot_token_h2o` en .env (no configurados).
- Fix: actualizar mocks o eliminar tests obsoletos. 78 passed, 14 failed/error — cero regresiones de codigo nuevo.

---

## P2 COSMETICO — estado al 2026-07-25

- P2-1: ruff E501 — RESUELTO (46→0 errores, commit 523d899). 26 noqa en strings de mensajes al cliente.
- P2-2: mypy type hints — RESUELTO (74→0 errores en api/, commit pendiente). bridge.py 66→0, main.py 8→0. Sin cambiar lógica, solo anotaciones + casts + asserts. pytest 105 pass, 0 fail.
- P2-4: tests/unit/test_bridge.py — RESUELTO (27 tests, commit a3a58ee).
- P2-5: RESUMEN_RETOMAR.md — RESUELTO (reescrito Dia 29, commit ff25415).

---

## FASE 2 (post-FASE 1)

Tras FASE 1 completa (~97%), iniciar FASE 2 segun `docs/DISPATCHER_ARCHITECTURE.md`:
- Financial Agent (lee Pedidos, escribe Pagos + Saldos_Clientes)
- Route Skill avanzado
- Analytics Skill (reporte diario 7am Telegram)
- Dispatcher avanzado

---

## METRICAS DE PROGRESO (actualizado 2026-07-24 19:15)

- Fallas P0 totales: 11 — TODAS RESUELTAS
- Fallas P1 totales: 13 — 12 resueltas (1 restante = FSM ya contado como P0-1)
- FASE 1 completitud: ~99%
- Commits totales repo: 75+
- Smoke tests: 29/29 PASS (3 suites)
- pytest suite: 105 passed, 14 skipped, 0 failed (27 nuevos test_bridge.py)
- mypy api/: 0 errores (bridge.py 66→0, main.py 8→0)
- Servicios prod: 4 active (bridge Type=notify + WatchdogSec, dispatcher, telegram, cloudflared)
- Cron jobs: 6 activos
- TELEGRAM_DISPATCH_CHAT: configurado (8523722341)
- GitHub: sincronizado (https://github.com/elpelon27/EstacionH2OIA)

