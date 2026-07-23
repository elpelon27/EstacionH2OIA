# Cierre de Jornada — 2026-07-22 (Día 27)

**Sesión**: Prometeo x Líder @elpelon27
**Trigger**: Caída de API del proveedor de IA + reinicio del servidor
**Duración**: ~4h (con pausas por rate limit 30 rpm)
**Modelo**: GLM 5.2 vía NVIDIA NIM
**Commits**: 13 (7d656a8 → 89d4747)

---

## Logros del día

### BLOQUE 1 — Investigación y recuperación tras caída de API
- Detectados 149 líneas sin commitear en bridge.py + dispatcher.py (reparaciones r1-r7)
- Verificado: cambios completos y correctos (py_compile OK, lógica revisada)
- Commit 7d656a8: r1-r7 (dispatch_queue en _init_db, PRAGMA foreign_keys, WAL, LOG_SALT fail-closed, botones new_arr/del/no, fix use-after-close, anti-GC task refs)

### BLOQUE 2 — Cleanup infraestructura (commit e8a4509)
- Detenido cloudflared-tunnel.service (quick tunnel efímero duplicado). Solo queda named tunnel valentina.estacionh2o.com
- Creado skills/run_dispatcher_checkin.py (cron 08:00 funcional, 8 días fallando)
- API key NVIDIA movida de prometeo.py a config/.env (NVIDIA_API_KEY)
- Eliminados 3 .bak files tracked en git (174KB bloat)
- Creado scripts/backup_db.sh (backup diario 2am, retention 14 días)
- Instalado /etc/logrotate.d/hermes-agent (weekly, rotate 4, compress)

### BLOQUE 3 — P0/P1 restantes (commit b3e1580)
- P0-2: /metrics con IP allowlist (127.0.0.1, ::1, 172.19.0.0/16)
- P0-3: Kill switch movido de /tmp a data/valentina.kill con 0600
- P1-3: 3 bare except → except Exception (bridge.py + run_analytics_7am.py)
- P1-5: Haversine dedup — bridge importa route_engine.haversine con fallback
- P2-3: Docstring de _send_to_dispatch_queue corregido

### BLOQUE 4 — FASE 1.5 Test E2E (commit df4b014 + b3040d6)
- Smoke test con spy: 5/5 PASS
- Valida: dispara en pago efectivo ("2") y "ya pagué", NO dispara en abortos
- conftest.py en tests/smoke/ para que pytest no coleccione los scripts standalone

### BLOQUE 5 — FASE 1.3 Route Planner (commit 7e2b757)
- Creado skills/run_route_planner.py (cron 7:45am)
- Lee dispatch_queue, crea clients, calcula VRP con OR-Tools, crea sessions/deliveries
- Test E2E con 2 pedidos fake: OR-Tools asignó 2 paradas a EVERT, 7.37 km, 38 min
- BD restaurada post-test (shutil.copy backup/restore)

### BLOQUE 6 — B1, B2, B3 (Líder + Prometeo)
- B1: Webhook Meta apuntado a https://valentina.estacionh2o.com/webhook/meta (Líder)
- B2: Systemd unit reconciliado + NOPASSWD sudoers configurado (Líder + script)
- B3: Bridge reiniciado — SQL inicializado con "WAL + foreign_keys ON" confirmado en log
- Fix ExecStartPre: /usr/bin/python3 → venv (sistema no tiene fastapi)
- Fix --access-log false → --no-access-log (uvicorn)
- Fix StartLimitIntervalSec removido de [Service] (va en [Unit])

### BLOQUE 7 — P1-1 PHONE_REGEX (commit 89d4747)
- Regex cambiado de r"\+?58?\d{10,15}" a r"(?<!\d)\+?58\d{10}(?!\d)"
- Lookarounds negativos: no matchea IDs, timestamps, IPs, coordenadas
- Test: 20/20 PASS (5 match + 10 no-match + 5 límite)

---

## Tech debt detectado

- Preexisting: test_api.py mockea _send_waha_message (eliminado), test_valentina.py referencia _load_doc (no existe), test_config.py espera tokens no en .env. 78 passed, 6 failed, 8 errors — idéntico en HEAD-1
- StartLimitIntervalSec también en telegram-bot.service y dispatcher-bot.service (mismo bug que bridge)
- Telegram chat_id de choferes (TELEGRAM_DISPATCH_CHAT) sin configurar — route planner no notifica por Telegram

---

## Estado del sistema

- **valentina-bridge.service**: active, r1-r7 + P0-2/P0-3/P1-1 activos (requiere reinicio para P1-1)
- **dispatcher-bot.service**: active
- **telegram-bot.service**: active
- **cloudflared.service** (named tunnel): active, valentina.estacionh2o.com
- **cloudflared-tunnel.service**: detenido y disabled (eliminado)
- **BDs**: WAL mode + foreign_keys en ambos
- **Backups**: diario 2am, retention 14 días
- **Cron jobs**: 6 activos (analytics 7am, route_planner 7:45am, checkin 8am, backup 2am, fs_reporte 6:30pm, fs_recordatorios cada 30min)
- **FASE 1 completitud**: ~90%

---

## Pendiente para próxima sesión

1. **Reiniciar bridge** para activar P1-1 (PHONE_REGEX) — change commiteado pero no reiniciado (rate limit + corte eléctrico inminente)
2. **P0-1**: FSM persistente en SQLite (~4h) — último P0 restante
3. **P1-2**: WatchdogSec systemd (~2h)
4. **Configurar TELEGRAM_DISPATCH_CHAT** en .env con chat_id del grupo de choferes
5. **Fix StartLimitIntervalSec** en telegram-bot.service + dispatcher-bot.service
6. **ruff format** + **mypy incremental** (P2 cosmético)

---

## Commits de la sesión

| Hash | Descripción |
|------|-------------|
| 89d4747 | fix(P1-1): PHONE_REGEX preciso con lookarounds — 20/20 tests PASS |
| 8832c64 | fix(systemd): ExecStartPre usa venv python, --no-access-log, StartLimitBurst en [Unit] |
| 2830251 | docs: roadmap actualizado — FASE 1.3 completado, FASE 1 ~85% |
| 7e2b757 | feat(FASE 1.3): cron 7:45am route planner — VRP automatico con OR-Tools |
| b3040d6 | fix(test): smoke test E2E compatible con pytest |
| dcd5869 | docs: roadmap actualizado — FASE 1 ~70% |
| df4b014 | test(FASE 1.5): smoke test E2E _send_to_dispatch_queue — 5/5 PASS |
| b3e1580 | fix(P0/P1/P2): /metrics auth, kill switch seguro, bare except, haversine dedup |
| 2b8f4c7 | docs: roadmap vivo actualizado |
| e8a4509 | fix(infra): cloudflared duplicado, cron roto, backups, logrotate |
| 7d656a8 | fix(P0/P1): reparaciones r1-r7 |
| 0c2e493 | docs(analisis): integra 6 hallazgos P0 nuevos |
| 90e3cdd | docs(analisis): reporte milimetrico arquitectura 2026-07-21 |

---

> *"La caída de la API no fue un problema — fue una auditoría forzada. Lo que encontramos y reparamos en 4 horas habría explotado en producción en algún momento impredecible." — Prometeo*

💧
