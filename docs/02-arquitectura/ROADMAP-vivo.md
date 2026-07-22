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

## 🟡 PRÓXIMO — FASE 1.3: Cron 7:45am ruta automática (3h)

**Objetivo**: Cada día a 7:45am, leer `dispatch_queue` (pedidos pending del día anterior), generar ruta óptima con OR-Tools VRP (`route_engine.py`), asignar a choferes YORDANIS + EVERT, enviar notificación Telegram.

**Tareas**:
1. Crear `skills/run_route_planner.py` (script cron 7:45am).
2. Leer `dispatch_queue` WHERE estado='pending' de conversations.db.
3. Llamar `route_engine.py` con vehicles activos + deliveries pendientes.
4. Insertar resultado en `dispatch.db.deliveries` + `dispatch_sessions`.
5. Enviar notificación Telegram a cada chofer con su ruta del día.
6. Cron: `45 7 * * * /mnt/ssd_trabajo/hermes-agent/venv/bin/python skills/run_route_planner.py >> logs/route_planner.log 2>&1`

**Prerequisito**: B3 (reiniciar bridge para activar r1 = dispatch_queue table en _init_db).

**Estimación**: 3h.

---

## 🟡 FASE 1.5: Test E2E dispatcher (2h)

**Objetivo**: Validar el flujo completo: pedido WhatsApp → bridge → dispatch_queue → dispatcher → chofer → ack.

**Tareas**:
1. Smoke test ad-hoc del bridge con spy en `_send_to_dispatch_queue`.
2. Verificar que `dispatch_queue` recibe el pedido.
3. Verificar que `_sync_client_to_dispatch_db` crea el client en dispatch.db.
4. Simular callback de chofer (`new_arr`, `new_del`, `new_no`).
5. Verificar `update_delivery_status` actualiza la delivery.

**Patrón**: Backup/restore BD real con `shutil.copy` (ver skill pitfalls #15).

**Estimación**: 2h.

---

## 🟠 P0 RESTANTES (del análisis 36 fallas — 3 quedan)

### P0-1: Estado FSM en memoria NO persistente (P1 en análisis, P0 en práctica)
**Archivo**: `api/bridge.py:146+153+747` (`_seen_messages`, `_last_order_totals`, `_conversation_state`).
**Riesgo**: Si uvicorn muere, estados `awaiting_payment`/`awaiting_confirmation` se pierden. Cliente pagó pero el pedido no se procesa.
**Fix**:Persistir `_conversation_state` en SQLite (`conversation_state(phone_hash, state_json, updated_at)`), carga perezosa.
**Estimación**: 4h.

### P0-2: `/metrics` sin auth
**Archivo**: `api/bridge.py` endpoint `/metrics`.
**Fix**: Filtrar con IP allowlist (`127.0.0.1` + `172.19.0.0/16` Docker). Basic Auth como alternativa.
**Estimación**: 30min.

### P0-3: Kill switch en `/tmp/valentina.kill` (escribible por todos)
**Archivo**: `skills/telegram_bot.py:49+85`.
**Fix**: Mover a `data/valentina.kill` con 0600. Auto-clear si > 24h.
**Estimación**: 30min.

---

## 🟠 P1 RESTANTES (del análisis 36 fallas — 6 quedan)

### P1-1: PHONE_REGEX demasiado greedy
**Archivo**: `api/bridge.py:286-298`.
**Fix**: `re.compile(r"(?<!\d)\+?58\d{10}(?!\d)")` con lookarounds + tests.
**Estimación**: 1h (con tests).

### P1-2: WatchdogSec= en systemd
**Fix**: Añadir `WatchdogSec=30s` + `sd_notify("WATCHDOG=1")` desde task asyncio periódica. Paquete `sdnotify`.
**Estimación**: 2h.

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

## 📊 MÉTRICAS DE PROGRESO

- Fallas P0 totales detectadas: 11
- Fallas P0 resueltas: 8 (r1-r7 + cloudflared + cron + backups)
- Fallas P0 restantes: 3 (FSM persistente, /metrics auth, kill switch)
- Fallas P1 totales: 13
- Fallas P1 resueltas: 7 (API key, .bak, logrotate, haversine factor, LOG_SALT, use-after-close, GC tasks)
- Fallas P1 restantes: 6
- FASE 1 completitud: ~60%

💧
