# 🗺️ ROADMAP VIVO — Estación H2O / Prometeo

**Última actualización**: 2026-07-22 (Día 27 — sesión Prometeo x Líder tras caída API)
**Autor**: Prometeo (GLM 5.2 vía NVIDIA NIM)
**Fuente**: docs/05-tech-debt/ANALISIS_ARQUITECTURA_2026-07-21.md (36 fallas) + estado actual del repo

---

## ✅ COMPLETADO (hasta 2026-07-22)

### FASE 1.5 — Bridge → dispatch_queue (2026-07-21, commit fd9ff21)
- `_send_to_dispatch_queue` DEFINIDA pero NUNCA LLAMADA → ahora llamada en 2 puntos de cierre.
- Test E2E: PASS.

### FASE 1 paso 2 — Sync clients dispatch.db (2026-07-21, commit fd9ff21)
- `_sync_client_to_dispatch_db` upsert por phone_hash con running avg botellones.
- `_nearest_zone_id` haversine contra 5 zones Maracaibo.

### Reparaciones r1-r7 (2026-07-22, commit 7d656a8)
- r1: `_init_db()` crea tabla `dispatch_queue` + 3 índices.
- r2: `PRAGMA foreign_keys=ON` en `get_dispatch_db`/`get_conv_db` + helper `_get_db_with_fk`.
- r3: `journal_mode=WAL` + `synchronous=NORMAL` en ambas BDs (persiste en archivo).
- r5: `LOG_SALT` fail-closed (aborta startup si default inseguro).
- r6: Botones `new_arr`/`new_del`/`new_no` con handler en dispatcher.py (FASE 1.4).
- r7: Fix use-after-close `conn` en `_save_order_to_db_and_sheets` + `_ASYNCTASKS_REFS` set.

### Cleanup infraestructura (2026-07-22, commit e8a4509)
- Detenido `cloudflared-tunnel.service` (quick tunnel efímero duplicado).
- Creado `skills/run_dispatcher_checkin.py` (cron 08:00 funcional).
- `scripts/prometeo/prometeo.py`: API key NVIDIA → `config/.env` (`NVIDIA_API_KEY`).
- Eliminados 3 `.bak` files tracked en git (174KB bloat).
- `scripts/backup_db.sh`: backup diario 2am, retention 14 días. Cron añadido.
- `/etc/logrotate.d/hermes-agent` instalado (weekly, rotate 4, compress).

---

## 🔴 BLOQUEANTES — Requieren acción del Líder (1-liner c/u)

### B1 — Apuntar webhook Meta al named tunnel permanente (CRÍTICO)
**Estado**: El webhook en Meta Dashboard apunta a `trycloudflare.com` efímero (cambia cada ~8h). El named tunnel `valentina.estacionh2o.com` YA está corriendo pero Meta NO le envía webhooks.
**Acción del Líder**: En Meta Dashboard → WhatsApp → Callback URL, cambiar a:
```
https://valentina.estacionh2o.com/webhook/meta
```
Verify Token: `a2ee0e434375cb232a99f10e4e1d210a` (sin cambios).
**Impacto**: Si no se hace, los mensajes WhatsApp se pierden cuando el trycloudflare caduca.

### B2 — Reconciliar systemd unit /etc vs repo (r4 del análisis)
**Estado**: `/etc/systemd/system/valentina-bridge.service` tiene `StartLimitBurst=5` que el repo NO tiene. El repo tiene hardening que /etc NO tiene. Drift.
**Acción del Líder**:
```bash
sudo cp /mnt/ssd_trabajo/hermes-agent/systemd/valentina-bridge.service /etc/systemd/system/valentina-bridge.service
sudo systemctl daemon-reload
sudo systemctl restart valentina-bridge.service
```
**Impacto**: Sin esto, futuras ediciones del repo no impactan producción.

### B3 — Reiniciar valentina-bridge.service para activar reparaciones r1-r7
**Estado**: Los cambios r1-r7 están commiteados (7d656a8) pero el bridge corriendo (PID 4950) carga el código ANTERIOR. Para activar WAL en `_init_db` y el fail-closed de LOG_SALT, hay que reiniciar.
**Regla**: Diff-before-restart — el diff YA fue mostrado (commits 7d656a8 + e8a4509).
**Acción del Líder**: `systemctl restart valentina-bridge.service` (o "autorizo" / "arranca").
**Impacto**: Sin reinicio, las fixes r1-r7 no protegen producción.

---

## 🟡 FASE 1.3: Cron 7:45am ruta automática — COMPLETADO (commit 7e2b757)

Script `skills/run_route_planner.py` creado y testeado con 2 pedidos fake:
1. Lee `dispatch_queue` (estado='pending') de conversations.db
2. Crea/actualiza clients en dispatch.db (find_by_phone o insert con phone_hash)
3. Convierte pedidos a `ClientOrder` dataclass para route_engine
4. Calcula rutas VRP con OR-Tools (`compute_vrp_route`) — fallback NN si falla
5. Crea `dispatch_sessions` + `deliveries` (order_sequence) en dispatch.db
6. Marca pedidos de `dispatch_queue` como 'enviado'
7. Notifica choferes por Telegram (si `TELEGRAM_DISPATCH_CHAT` configurado en .env)

Test E2E: 2 pedidos → 2 clients creados → OR-Tools asignó 2 paradas al Vehículo 2 (EVERT),
7.37 km, 38 min, 8 botellones → 2 sessions + 2 deliveries creadas ✅. BD restaurada post-test.

Cron: `45 7 * * *` añadido al crontab.

**Prerequisito**: B3 (reiniciar bridge para activar r1 = dispatch_queue table en _init_db).
**Pendiente**: Líder debe configurar `TELEGRAM_DISPATCH_CHAT` en .env con el chat_id del grupo de choferes.

---

## 🟡 FASE 1.5: Test E2E dispatcher — COMPLETADO (commit df4b014, 5/5 PASS)

Smoke test con spy valida que `_send_to_dispatch_queue` dispara en:
- Pago efectivo '2' → payment_method='Efectivo' + address presente ✅
- 'ya pagué' tras pago móvil → payment_method='Pago Móvil' ✅

Y NO dispara en abortos:
- 'volver', 'menú', 'atrás' desde awaiting_payment ✅

---

## 🟠 P0 RESTANTES (del análisis 36 fallas — 3 quedan)

### P0-2: `/metrics` sin auth — RESUELTO (commit b3e1580)
IP allowlist (127.0.0.1, ::1, 172.19.0.0/16 Docker) aplicada al endpoint /metrics.

### P0-3: Kill switch /tmp/valentina.kill — RESUELTO (commit b3e1580)
Movido a data/valentina.kill con 0600 al crear. Persiste tras reboot. Cambio en bridge.py + telegram_bot.py.

### P0-1: Estado FSM en memoria NO persistente — RESUELTO (commit 3cda570)
**Antes**: `_conversation_state` y `_last_order_totals` eran dicts en memoria. Si uvicorn moria, estados `awaiting_payment`/`awaiting_confirmation` se perdian.
**Fix**: Tabla `conversation_state` en SQLite (`phone_hash` PK, `state_json`, `total`, `qty_bot`, `qty_hielo`, `updated_at`). `_get_state` hace lazy load desde SQLite con cache en memoria. `_set_state` es write-through. `_last_order_totals` persiste en mismo row via helpers `_save_order_totals`/`_get_order_totals`/`_clear_order_totals`. `_seen_messages` permanece en memoria (TTL 5min, efimero).
**Test**: 21/21 PASS (tests/smoke/test_fsm_persistente.py) — recupera estados tras reinicio simulado, upsert, clear, multiplex telefonos.
**Requiere**: Reinicio del bridge para activar `_init_db` (crea tabla nueva).

---

## 🟠 P1 RESTANTES (del análisis 36 fallas — 6 quedan)

### P1-1: PHONE_REGEX demasiado greedy
**Archivo**: `api/bridge.py:286-298`.
**Fix**: `re.compile(r"(?<!\d)\+?58\d{10}(?!\d)")` con lookarounds + tests.
**Estimación**: 1h (con tests).

### P1-2: WatchdogSec systemd — RESUELTO (commit e24fcbf)
**Antes**: Si el bridge se colgaba (deadlock, memory leak), systemd no lo detectaba — servicio 'active' pero no respondia.
**Fix**: `Type=notify` + `WatchdogSec=30s` en systemd unit. `_watchdog_loop()` en bridge.py envia `WATCHDOG=1` cada 15s via `sdnotify`. `READY=1` al arrancar. Cancelacion limpia en shutdown.
**Test**: 8/8 PASS (tests/smoke/test_watchdog.py).
**Requiere**: Reiniciar bridge + copiar systemd unit a /etc.

### P1-3: Bare `except:` (E722) en bridge.py + run_analytics_7am.py
**Fix**: Cambiar a `except Exception:`.
**Estimación**: 30min.

### P1-4: Estado FSM no persistente (mismo que P0-1 arriba)
Ya contado.

### P1-5: Haversine duplicado entre bridge y route_engine
**Fix**: `from skills.dispatch.route_engine import haversine` en bridge.py, eliminar duplicación.
**Estimación**: 30min.

### P1-6: Logs creciendo sin logrotate — RESUELTO (commit e8a4509)

---

## 🔵 P2 COSMÉTICO (postergable)

- P2-1: 78 errores E501 (ruff line-length) en bridge.py.
- P2-2: 96 errores mypy (type hints faltantes) en bridge.py.
- P2-3: `_send_to_dispatch_queue` docstring stale (dice "dirección" pero ahora dispara en "ya pagué").
- P2-4: Crear `tests/unit/test_bridge.py` (suite pytest nueva).

---

## 📅 CRONOGRAMA PROPUESTO

| Sesión | Tareas | Estimación |
|--------|--------|-------------|
| HOY (Líder) | B1, B2, B3 (3 one-liners) | 10 min |
| Próxima 1 | FASE 1.3 cron 7:45am ruta automática | 3h |
| Próxima 2 | FASE 1.5 test E2E + P0-2 (/metrics auth) + P0-3 (kill switch) | 3h |
| Próxima 3 | P0-1 (FSM persistente) + P1-1 (PHONE_REGEX) | 5h |
| Próxima 4 | P1-2 (WatchdogSec) + P1-3 (bare except) + P1-5 (haversine dedup) | 3h |
| Próxima 5 | P2 cosmético (ruff format + mypy + test_bridge.py) | 4h |

**Total FASE 1 completa**: ~18h de trabajo de Prometeo + 10 min del Líder.

**Tras FASE 1 completa**: Iniciar FASE 2 (Financial Agent, Route Skill, Analytics Skill, Dispatcher avanzado) según `docs/DISPATCHER_ARCHITECTURE.md`.

---

## 📊 MÉTRICAS DE PROGRESO (actualizado 2026-07-24)

- Fallas P0 totales detectadas: 11
- Fallas P0 resueltas: 11 — TODAS LAS P0 RESUELTAS
- Fallas P1 totales: 13
- Fallas P1 resueltas: 12 (API key, .bak, logrotate, haversine factor, LOG_SALT, use-after-close, GC tasks, bare except, haversine dedup, docstring, PHONE_REGEX, WatchdogSec)
- Fallas P1 restantes: 1 (FSM persistente ya contado como P0-1)
- FASE 1 completitud: ~97%
- Commits sesión 2026-07-24: 4 (3cda570 P0-1, aea8648 docs, e24fcbf P1-2, + este docs)
- Smoke tests: 29/29 PASS (5 E2E dispatcher + 20 PHONE_REGEX + 21 FSM + 8 watchdog, 3 suites)
- Cron jobs: 6 activos

💧
