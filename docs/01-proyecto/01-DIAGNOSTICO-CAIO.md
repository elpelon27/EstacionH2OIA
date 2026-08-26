# Diagnóstico CAIO — Estación H2O / Prometeo

**Fecha**: 2026-08-26 (Día 34)
**Autor**: Prometeo (GLM 5.2 vía OpenRouter)
**Fuente**: ANALISIS_ARQUITECTURA_2026-07-21.md + ROADMAP-vivo.md + verificación en vivo 2026-08-26
**Repo**: github.com/elpelon27/EstacionH2OIA — rama feat/odoo-r4-integration, 194 commits

---

## 1. Estado Actual del Sistema (verificado 2026-08-26)

### 1.1 Métricas de Código

| Métrica | Valor | Fuente |
|---------|-------|--------|
| Commits totales | 194 | `git rev-list --count HEAD` |
| Rama activa | feat/odoo-r4-integration | `git branch` |
| Tests pasados | 956 passed, 15 skipped, 0 failed | `pytest -q --tb=no` (2026-08-26) |
| Archivos de test | 59 (sin conftest/__init__) | `find tests -name "*.py"` |
| Cobertura total | 61% (3114 stmts, 1214 missing) | pytest-cov |
| mypy api/ | 0 errores | ROADMAP-vivo commit 1028066 |
| mypy skills/ + src/ | ~72 errores (no bloqueantes, P3) | ROADMAP-vivo |
| ruff api/ | 14 errores preexistentes (E402 + F841) | ROADMAP-vivo |

### 1.2 Servicios en Producción

| Servicio | Estado | Verificación |
|----------|--------|--------------|
| valentina-bridge | active | `systemctl is-active` (Type=notify + WatchdogSec=30s) |
| cloudflared | active | Named tunnel valentina.estacionh2o.com |
| dispatcher-bot | active | Telegram bot choferes |
| telegram-bot | active | Prometeo bot Líder |
| odoo-web | Up (Docker) | Odoo 17 Community self-hosted |
| odoo-db | Up (Docker) | PostgreSQL para Odoo |

### 1.3 Cron Jobs Activos

| Cron | Schedule | Script |
|------|----------|--------|
| Analytics diario | 07:00 | skills/run_analytics_7am.py |
| Route planner | 07:45 | skills/run_route_planner.py |
| Dispatcher checkin | 08:00 | skills/run_dispatcher_checkin.py |
| FS reporte | 18:30 | skills/run_fs_reporte.py |
| FS recordatorios | cada 30min | skills/run_fs_recordatorios.py |
| Backup verificación | día 1 mes 06:00 | scripts/verify_backup.sh |
| Log cleanup | domingo 04:00 | find logs -mtime +30 -delete |

### 1.4 Base de Datos (verificado 2026-08-26)

**conversations.db** (SQLite WAL mode, foreign_keys ON):
- fs_pedidos: 80 registros
- orders: 37 registros
- fs_pagos: 2 registros
- fs_audit_log: activo (4 triggers)
- fs_tasas_cambio, fs_cuentas_cobrar, fs_nomina, fs_productos, fs_empleados, fs_verificacion_log, fs_proveedor_pagos, fs_reportes_diarios
- conversation_state: FSM persistente (phone_hash PK)
- dispatch_queue: tabla creada en _init_db

**dispatch.db** (SQLite WAL mode, foreign_keys ON):
- clients: 3 registros
- deliveries: 4 registros
- zones, vehicles, bottles, bottle_movements, bottle_alerts, dispatch_sessions, gps_tracks, geofence_events, route_history, dispatch_notifications

### 1.5 SOUL

- Versión: 2.1.0
- Ubicación: docs/01-proyecto/SOUL-hermes-v2.md
- FASE 2 completada: §6 4→6 capas (Buffer+Social), §6.2 mem0→Consolidador v2.0.18, Redis→Buffer, Qdrant 402pts, Ollama +qwen2.5:3b
- Verificado: 2026-08-24

### 1.6 Integraciones

**R4 CONECTA V3.0** (banco):
- Archivos: src/integrations/r4/ (client.py, hmac_auth.py, codigos.py, webhooks.py)
- 13 endpoints implementados con HMAC-SHA256 por endpoint
- Webhooks /webhook/r4/consulta + /webhook/r4/notifica (bidireccionales)
- IP whitelist: 45.175.213.98, 200.74.203.91, 204.199.249.3
- Tests: tests/test_r4_commerce_secret_split.py + tests/unit/test_r4_webhooks_coverage.py
- **PENDIENTE**: Token de producción (sandbox only hasta entrega de credenciales por banco)

**Odoo 17 Community** (Docker self-hosted):
- Archivos: src/integrations/odoo/ (odoo_sync.py)
- Docker: odoo-web + odoo-db Up
- **PENDIENTE**: Módulos core activación, l10n_ve, productos cargados, API Key generada

**Financial Shield v3.0**:
- Deployado en producción (commit 91439f7)
- Transacción atómica add_pago_and_update_pedido()
- OCR Turbo cascada: Tesseract → Regex → Qwen2.5-VL
- Anti-fraude: UNIQUE(ref, metodo) + pHash perceptual
- Auditoría: 4 triggers fs_audit_log
- Recovery Scan: recovery_scan_stuck_payments() en lifespan bridge

---

## 2. Capacidades del Sistema

### 2.1 Capacidades Operacionales (probadas en producción)

| # | Capacidad | Estado | Evidencia |
|---|-----------|--------|-----------|
| C1 | Recibir pedidos por WhatsApp (Meta Cloud API) | OPERATIVO | Valentina bridge activo, webhook valentina.estacionh2o.com |
| C2 | FSM conversacional persistente | OPERATIVO | conversation_state en SQLite, 21/21 tests PASS |
| C3 | Cálculo determinístico de totales | OPERATIVO | _calc_total + _fix_total_in_response |
| C4 | Mínimo 3 botellones por pedido | OPERATIVO | Guards en bridge.py |
| C5 | Dispatch queue (pedido → dispatcher) | OPERATIVO | _send_to_dispatch_queue en 2 puntos de cierre, 5/5 E2E PASS |
| C6 | Sync clients bridge→dispatch.db | OPERATIVO | _sync_client_to_dispatch_db upsert por phone_hash |
| C7 | Route planning automático (OR-Tools VRP) | OPERATIVO | Cron 07:45, 5 zonas Maracaibo, haversine correcto |
| C8 | Botones chofer Telegram (entregar/no) | OPERATIVO | new_arr/new_del/new_no con handler |
| C9 | Financial Shield v3.0 (cache pedidos/pagos) | OPERATIVO | 80 fs_pedidos, 2 fs_pagos, OCR Turbo, anti-fraude |
| C10 | Watchdog systemd (detecta deadlock) | OPERATIVO | Type=notify + WatchdogSec=30s, 8/8 tests PASS |
| C11 | Kill switch persistente | OPERATIVO | data/valentina.kill con 0600 |
| C12 | Backup BD diario | OPERATIVO | scripts/backup_db.sh + verify_backup.sh |
| C13 | Logrotate | OPERATIVO | /etc/logrotate.d/hermes-agent |
| C14 | Métricas Prometheus + Loki | OPERATIVO | Docker: hermes_prometheus + hermes_loki + hermes_promtail |
| C15 | Reporte diario 7am → Telegram | OPERATIVO | Cron 07:00 run_analytics_7am.py |
| C16 | Recordatorios pagos pendientes | OPERATIVO | Cron cada 30min run_fs_recordatorios.py |

### 2.2 Capacidades en Desarrollo

| # | Capacidad | Estado | Bloqueador |
|---|-----------|--------|------------|
| D1 | Odoo sync (pedido → factura/nota) | EN DESARROLLO | Odoo Docker Up pero módulos core no activados, productos no cargados |
| D2 | Webhooks R4 producción | EN DESARROLLO | Código listo, pendiente token prod del banco |
| D3 | Reporte ISLR mensual | PENDIENTE | Requiere Odoo contabilidad activa |
| D4 | Dispersión nómina via R4 | PENDIENTE | Requiere token R4 prod |
| D5 | Conversión nota→factura | PENDIENTE | Requiere Odoo wizard + l10n_ve |
| D6 | Memoria vectorial (Qdrant) | DORMIDO | Config en .env, memory_client.py existe, pendiente activación |

---

## 3. Gaps (Brechas detectadas)

### 3.1 Gaps de Producto

| # | Gap | Impacto | Prioridad |
|---|-----|---------|-----------|
| G1 | Sin facturación electrónica operativa (SENIAT) | No se emiten facturas legales, solo notas entrega | ALTA |
| G2 | Sin conciliación bancaria automática (R4 en sandbox) | Pagos se registran manual en FS, no hay validación bancaria end-to-end | ALTA |
| G3 | Sin inventario Odoo (productos no cargados) | Stock se gestiona manual, no hay trazabilidad de botellones en Odoo | ALTA |
| G4 | Sin nómina automatizada | Cálculo manual, no hay dispersión R4 | MEDIA |
| G5 | Sin CRM/clientes en Odoo | 3 clientes en dispatch.db, sin historial de compras en Odoo | MEDIA |
| G6 | Sin memoria vectorial activa (Qdrant dormido) | Prometeo no tiene recall semántico de conversaciones previas | MEDIA |

### 3.2 Gaps de Infraestructura

| # | Gap | Impacto |
|---|-----|---------|
| G7 | mypy skills/ + src/ con ~72 errores | Deuda técnica, no bloquea commits |
| G8 | ruff 14 errores E402/F841 en api/ | Deuda técnica cosmética |
| G9 | Sin restore test de backup | No se ha validado que backup sea restaurable |
| G10 | Odoo sin l10n_ve (localización Venezuela) | No calcula IVA/ISLR correctamente |

### 3.3 Gaps de Negocio

| # | Gap | Impacto |
|---|-----|---------|
| G11 | 3 clientes en dispatch.db vs 16 clientes reales estimados | Subregistro: muchos clientes operan sin pasar por Valentina |
| G12 | 4 deliveries en dispatch.db | Sistema de dispatch apenas arrancando, adopción baja |
| G13 | Sin modelo de recurrencia formalizado | No hay suscripciones, pre-pago, ni sistema de lealtad |
| G14 | SWAP 165 loaners sin tracking digital completo | bottle_movements existe pero adopción parcial |

---

## 4. Riesgos

### 4.1 Riesgos Técnicos

| # | Riesgo | Probabilidad | Impacto | Mitigación |
|---|--------|-------------|---------|------------|
| R1 | Odoo Docker se cae por OOM | MEDIA | ALTO | Monitorear memoria, reinicio automático Docker restart=always |
| R2 | Token R4 sandbox expira sin aviso | MEDIA | ALTO | Coordinar con banco para credenciales prod |
| R3 | SQLite corruption (WAL reduce pero no elimina) | BAJA | CRÍTICO | Backup diario + verify_backup.sh mensual |
| R4 | Cloudflare Tunnel caído | BAJA | CRÍTICO | Webhook Meta deja de recibir, mensajes perdidos |
| R5 | Qwen2.5:7b cálculos incorrectos residuales | BAJA | MEDIO | _calc_total determinístico ya mitigó, pero modelos Ollama pueden drift |

### 4.2 Riesgos de Negocio

| # | Riesgo | Probabilidad | Impacto | Mitigación |
|---|--------|-------------|---------|------------|
| R6 | Choferes no adoptan Telegram bot | MEDIA | ALTO | Plan de adopción DT-01, onboarding simple /start |
| R7 | Clientes prefieren WhatsApp manual vs Valentina | MEDIA | MEDIO | Migración gradual, Valentina transparente al cliente |
| R8 | Corte eléctrico prolongado (Maracaibo) | ALTA | ALTO | Sin UPS documentado, bridge cae, mensajes se pierden |
| R9 | Modelo intercambio 70/30 confunde clientes | MEDIA | MEDIO | Capacitación clara, Valentina explica automáticamente |

### 4.3 Riesgos de Cumplimiento

| # | Riesgo | Probabilidad | Impacto |
|---|--------|-------------|---------|
| R10 | SENIAT requiere facturación electrónica y no se tiene | ALTA | ALTO |
| R11 | API key NVIDIA en git history (commit pasado) | BAJA | MEDIO | Ya movida a .env, pero history contiene la key |

---

## 5. Resumen de Fallas Históricas (ANALISIS_ARQUITECTURA 2026-07-21)

| Prioridad | Total detectadas | Resueltas | Pendientes |
|-----------|-----------------|-----------|------------|
| P0 (Bloqueante) | 11 | 11 | 0 |
| P1 (Crítico) | 13 | 13 | 0 |
| P2 (Cosmético) | 12 | Parcial | ruff E501 resuelto (46→0), mypy api/ resuelto (66→0) |

**Todas las fallas P0 y P1 están resueltas** (verificado ROADMAP-vivo 2026-07-28).

### Pendientes P3 (no bloqueantes):
- mypy skills/ + src/ ~72 errores
- ruff 14 errores E402/F841 en api/bridge.py (intencional por sys.path.insert)
- Activación Qdrant + mem0

---

## 6. Conclusión del Diagnóstico

El sistema Estación H2O tiene una base técnica sólida: 956 tests pasando, 4 servicios en producción, Financial Shield v3.0 operacional, FSM persistente, watchdog systemd, y todos los bugs P0/P1 del análisis de arquitectura resueltos. SOUL v2.1 está activo con 6 capas de memoria.

Los gaps principales son de producto (Odoo sin activar, R4 en sandbox) y de adopción (3 clientes vs 16 estimados, 4 deliveries). El siguiente paso crítico es activar Odoo completamente y obtener credenciales R4 de producción para cerrar el bucle de pagos end-to-end.

La deuda técnica restante (P3: mypy, ruff) es cosmética y no bloquea el avance funcional.

---

**Firma**: 💧