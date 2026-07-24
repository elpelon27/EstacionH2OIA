# 🔑 RESUMEN PARA RETOMAR — Estación H2O / Prometeo

**Última actualización**: 2026-07-24 (Día 29)
**Versión**: 2.0.0
**Arquitecto IA**: Prometeo (GLM 5.2 vía NVIDIA NIM)
**Líder**: Luis Martinez (@elpelon27)
**Repo**: https://github.com/elpelon27/EstacionH2OIA — 73 commits, sincronizado

---

## 🚨 SI SE PIERDE LA CONVERSACIÓN

Copia este archivo y pégalo como primer mensaje a Prometeo con:

```
CONTINUAR PROMETEO — Estación H2O
Leí /mnt/ssd_trabajo/hermes-agent/docs/05-tech-debt/RESUMEN_RETOMAR.md
Estado: retomando desde Día 29
```

---

## 📊 ESTADO ACTUAL DEL PROYECTO (Día 29, 2026-07-24)

### FASE 1: ~99% COMPLETADA

**P0 (bloqueantes): 11/11 RESUELTAS — TODAS**
- r1-r7: dispatch_queue en _init_db, PRAGMA foreign_keys, WAL, LOG_SALT fail-closed, botones dispatcher, use-after-close fix, anti-GC task refs
- cloudflared duplicado eliminado (named tunnel permanente valentina.estacionh2o.com)
- cron 08:00 reparado (run_dispatcher_checkin.py creado)
- backups diarios 2am + logrotate semanal
- /metrics con IP allowlist
- kill switch movido a data/valentina.kill con 0600
- FSM persistente en SQLite (tabla conversation_state, commit 3cda570)

**P1 (críticas): 12/13 RESUELTAS**
- API key NVIDIA → .env, .bak eliminados, logrotate, haversine factor, LOG_SALT, use-after-close, GC tasks, bare except, haversine dedup, docstring, PHONE_REGEX, WatchdogSec
- Única P1 restante: FSM persistente (ya contado como P0-1)

**P2 (cosmético): PARCIAL**
- 46 errores ruff E501 pendientes
- mypy type hints pendientes
- tests/unit/test_bridge.py pendiente

### SERVICIOS EN PRODUCCIÓN (4 activos)
- **valentina-bridge.service** — Type=notify, WatchdogSec=30s, PID activo
- **dispatcher-bot.service** — StartLimitBurst en [Unit] corregido
- **telegram-bot.service** — StartLimitBurst en [Unit] corregido
- **cloudflared.service** — named tunnel valentina.estacionh2o.com

### CRON JOBS (6 activos)
| Hora | Script | Función |
|------|--------|---------|
| 07:00 | run_analytics_7am.py | Reporte diario analytics |
| 07:45 | run_route_planner.py | VRP automático OR-Tools |
| 08:00 | run_dispatcher_checkin.py | Check-in choferes |
| 02:00 | backup_db.sh | Backup BD (retention 14 días) |
| 18:30 | run_fs_reporte.py | Reporte diario Financial Shield |
| */30min | run_fs_recordatorios.py | Recordatorios pagos |

### TESTS
- Smoke tests: 29/29 PASS (5 E2E + 20 PHONE_REGEX + 21 FSM + 8 watchdog, 3 suites)
- pytest suite: 78 passed, 14 skipped (tests obsoletos arquitectura anterior), 0 failed

---

## 🏗️ ARQUITECTURA ACTUAL

```
Cliente WhatsApp → Meta Cloud API → Cloudflare Tunnel (valentina.estacionh2o.com)
                                                          ↓
                                              Bridge FastAPI :8000 (api/bridge.py)
                                                ↓                    ↓
                                           Dify Chatbot        Google Sheets
                                           qwen2.5:7b          "Pedidos" (17 cols)
                                           System Prompt v4
                                                ↓
                                    SQLite (conversations.db)
                                    - conversations, orders, dispatch_queue
                                    - conversation_state (FSM persistente P0-1)
                                    - fs_pedidos, fs_pagos, fs_tasas_cambio, etc.
                                    - PRAGMA WAL + foreign_keys ON
                                                ↓
                                    Dispatcher Bot (Telegram)
                                    - Choferes: YORDANIS + EVERT
                                    - Route Planner VRP OR-Tools 7:45am
                                    - TELEGRAM_DISPATCH_CHAT=8523722341
```

---

## 🔑 CREDENCIALES Y RUTAS CRÍTICAS

### Servidor Maracaibo
- **Usuario**: skynet
- **Repo**: /mnt/ssd_trabajo/hermes-agent/
- **Venv**: /mnt/ssd_trabajo/hermes-agent/venv/
- **.env**: /mnt/ssd_trabajo/hermes-agent/config/.env
- **SQLite**: /mnt/ssd_trabajo/hermes-agent/data/conversations.db
- **Dispatch DB**: /mnt/ssd_trabajo/hermes-agent/data/dispatch.db
- **Bridge**: /mnt/ssd_trabajo/hermes-agent/api/bridge.py
- **Backups**: /mnt/ssd_trabajo/hermes-agent/backups/ (cron 2am, 14 días retention)
- **Logs**: journald + /mnt/ssd_trabajo/hermes-agent/logs/
- **Logrotate**: /etc/logrotate.d/hermes-agent (weekly, rotate 4, compress)
- **Sudoers NOPASSWD**: /etc/sudoers.d/h2o-deploy (systemctl restart, daemon-reload, cp systemd units)

### Systemd Units (versionados en repo + copiados a /etc)
- systemd/valentina-bridge.service — Type=notify, WatchdogSec=30s
- systemd/telegram-bot.service — StartLimitBurst en [Unit]
- systemd/dispatcher-bot.service — StartLimitBurst en [Unit]

### Meta Cloud API
- App ID: 975863248739508
- Phone Number ID: 1186108677920030
- API Version: v25.0
- Token: permanente (System User, no expira)
- Webhook: https://valentina.estacionh2o.com/webhook/meta

### Telegram
- Bot token: en .env (TELEGRAM_BOT_TOKEN)
- Chat Líder: 1663148211 (TELEGRAM_CHAT_ID)
- Chat Choferes: 8523722341 (TELEGRAM_DISPATCH_CHAT)

### Google Sheets
- Spreadsheet ID: 1Bbp4Xqw5E7bb7loJ262K9lMPFinNSIW-ws1i7ZAmiYk
- Service account: valentina-h2o@valentina-h2o.iam.gservice.com
- Pestañas: Pedidos, Pagos, Validacion_Pagos, Aprendizaje, Categoria_Cliente, Feedback_Clientes, Feedback_Agentes, Mapa_Calor, Saldos_Clientes, Ventas

### Dify
- App: "Valentina" (modo Chatbot)
- API Key: en .env (DIFY_API_KEY)
- URL: http://localhost/v1/chat-messages
- Prompt: System Prompt v4 (máquina 8 estados)

---

## 💶 PRECIOS (confirmados, sin cambios)

- **Botellón de agua**: €1.00 c/u
- **Bolsa de hielo**: €1.20 c/u
- **Pedido mínimo**: 3 unidades
- Definidos en bridge.py: PRECIO_BOTELLON=1.00, PRECIO_HIELO=1.20

---

## 📝 DECISIONES DEL LÍDER (acumuladas hasta Día 29)

1. Migrar a WhatsApp Cloud API oficial (no más WAHA)
2. Valentina NO es proactiva (hardcore chatbot, menú 5 botones)
3. Horario: 8am-6pm Lun-Sáb (publicado al cliente)
4. Skills > Multi-agente para 10 msg/día
5. Nombre: Estación H2O
6. Arquitecto IA: Prometeo
7. Precios: Agua €1.00, Hielo €1.20 (CONFIRMADO, se mantiene)
8. Fuera de horario: recibir pedido y programar para mañana
9. Valentina cierra ventas SOLA
10. Máquina de estados estricta (un paso por mensaje)
11. Datos pago: R4 Banco Microfinanciero 0169, cuenta 0169 0010 9710 0159 1583, RIF J-506356899, Pago Móvil +58 412-2560721
12. Google Sheets como fuente compartida
13. PII_SAFE=false en Google Sheets (teléfonos reales)
14. PII_SAFE=true en logs journald (teléfonos hasheados)
15. Guard de horario determinístico en código (no en prompt)
16. SQLite sobre PostgreSQL hasta >1000 msg/día
17. Systemd sobre Docker para el bridge
18. Kill switch via Telegram solo para Líder (chat_id 1663148211)
19. TDD obligatorio para skills nuevas (cobertura 80%)
20. Rate limit proveedor IA: 30 rpm con pausas de 10 min

---

## 🛡️ PRINCIPIOS NO NEGOCIABLES

1. Skills > Multi-agente para 10 msg/día
2. qwen2.5:7b local para producción (0$)
3. Meta Cloud API oficial (no librerías no oficiales)
4. SQLite sobre PostgreSQL hasta >1000 msg/día
5. Systemd sobre Docker para el bridge
6. PII safe en logs (teléfonos hasheados en journald)
7. PII completa en Google Sheets (datos operativos del negocio)
8. Un paso por mensaje (máquina de estados estricta)
9. Kill switch via Telegram solo para Líder
10. Guard de horario determinístico en código (no en prompt)
11. Español como regla de oro en todas las respuestas

---

## 📂 ARCHIVOS CRÍTICOS

### Vault Obsidian (docs/ organizado en 6 carpetas)
- docs/01-proyecto/ — SOUL-valentina, AGENTS, BOOTSTRAP, USER
- docs/02-arquitectura/ — ROADMAP-vivo.md (vivo actualizado), ROADMAP-plan, RUNBOOK
- docs/03-sesiones/ — CIERRE_JORNADA_2026-07-22, REPARACIONES_2026-07-21, worklog
- docs/05-tech-debt/ — ANALISIS_ARQUITECTURA_2026-07-21, DEUDA_TECNICA_DIA_15, este archivo
- docs/adr/ — 7 ADRs (decisiones de arquitectura)
- docs/prompts/ — valentina.v1.md

### Smoke Tests (tests/smoke/)
- test_fsm_persistente.py — 21/21 PASS (P0-1 FSM)
- test_watchdog.py — 8/8 PASS (P1-2 watchdog)
- test_phone_regex.py — 20/20 PASS (P1-1 PHONE_REGEX)
- test_send_to_dispatch_queue.py — 5/5 PASS (FASE 1.5 E2E)

---

## 🚀 PRÓXIMO PASO

### FASE 2 — Skills avanzadas (post-FASE 1)
1. Financial Agent — lee Pedidos, escribe Pagos + Saldos_Clientes
2. Route Skill avanzado — optimización dinámica con tráfico
3. Analytics Skill — reporte diario 7am Telegram con gráficos
4. Dispatcher avanzado — asignación automática de choferes

### P2 COSMÉTICO (postergable)
- 46 errores ruff E501 en bridge.py (líneas > 120 chars)
- N errores mypy (type hints faltantes) en bridge.py
- Crear tests/unit/test_bridge.py (suite pytest del bridge)

---

## 💧 HISTORIA

- **Día 13** (2026-07-04): Primer cliente real end-to-end. Venta €2.40, qwen2.5:7b local 0$.
- **Día 15** (2026-07-07): 4 bugs detectados (cálculos, mínimo 3, botones pago, mensaje compuesto).
- **Día 22** (2026-07-22): Caída API → auditoría forzada. 13 commits, r1-r7, B1/B2/B3, FASE 1.3, P1-1.
- **Día 24** (2026-07-24): P0-1 FSM persistente + P1-2 WatchdogSec + StartLimitIntervalSec fix + 14 tests resueltos + 4 bugs Día 15 verificados resueltos. GitHub sincronizado. FASE 1 ~99%.

> *"La caída de la API no fue un problema — fue una auditoría forzada." — Prometeo*

**Descansa, Líder. La FASE 1 está virtualmente completa. 💧**
