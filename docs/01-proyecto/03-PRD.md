# PRD — Product Requirements Document — Estación H2O

**Fecha**: 2026-08-26 (Día 34)
**Autor**: Prometeo (GLM 5.2 vía OpenRouter)
**Aprobador**: Luis Martinez (@elpelon27) — Líder de Estación H2O
**Fuente**: ROADMAP-vivo.md + DIAGNOSTICO-CAIO.md + verificación en vivo 2026-08-26
**Estado**: ACTIVO — basado en datos reales del proyecto

---

## 1. Visión

Automatizar el 100% del flujo operativo de Estación H2O (venta de botellones de agua + SWAP de 165 loaners) mediante un sistema de agentes IA que:

- Recibe pedidos por WhatsApp (Valentina)
- Optimiza rutas de entrega (Dispatcher + OR-Tools VRP)
- Gestiona pagos móviles con validación bancaria (R4 CONECTA V3.0)
- Factura electronicamente (Odoo 17 + SENIAT)
- Mantiene memoria del negocio (SOUL v2.1, 6 capas)
- Reporta métricas al Líder por Telegram (Prometeo)

**Filosofía**: Odoo = fuente de verdad financiera | Valentina = fuente conversacional | Dispatcher = fuente logística

---

## 2. Usuarios

### 2.1 Persona 1: Líder (Luis Martinez)

- **Rol**: Propietario y tomador de decisiones
- **Herramientas**: Odoo Web (dashboard) + Telegram (@Skynet_27_bot)
- **Necesidades**:
  - Reportes automáticos: ventas diarias, cierre semanal, inventario, nómina
  - Aprobación de facturas, nómina, overrides de documento
  - Visibilidad total del negocio en tiempo real
- **Frecuencia**: Diario (mañana reportes, viernes nómina/cierre)

### 2.2 Persona 2: Cliente

- **Rol**: Comprador de botellones de agua
- **Herramientas**: WhatsApp (dialoga con Valentina)
- **Necesidades**:
  - Pedir botellones fácilmente (minimo 3)
  - Pagar con efectivo o pago móvil
  - Recibir confirmación de entrega
  - Tarifa justa con tasa BCV actualizada
- **Frecuencia**: 1-3 pedidos/semana por cliente activo
- **Universo actual**: 16 clientes estimados (3 registrados en dispatch.db)

### 2.3 Persona 3: Chofer (YORDANIS, EVERT)

- **Rol**: Entrega de botellones en triciclo
- **Herramientas**: Telegram (@DespachoH2O_bot)
- **Necesidades**:
  - Recibir ruta del día (zonas Maracaibo)
  - Marcar entregas (botones: ✅ Entregado / ❌ No entregado)
  - Reportar botellones vacíos devueltos (SWAP)
- **Frecuencia**: Diario, ruta 07:45am

### 2.4 Persona 4: Contador (por contratar)

- **Rol**: Cumplimiento fiscal (SENIAT)
- **Herramientas**: Odoo Web + Excel export
- **Necesidades**:
  - Libros de venta/compra
  - Declaración IVA quincenal
  - Declaración ISLR mensual
  - Auditoría de facturas

---

## 3. Problema

### 3.1 Problemas actuales (verificados)

| # | Problema | Evidencia |
|---|----------|-----------|
| P1 | Pedidos manuales por WhatsApp sin trazabilidad | 37 orders en BD vs 16 clientes activos = subregistro |
| P2 | Pagos sin validación bancaria automática | R4 en sandbox, 2 fs_pagos manuales |
| P3 | Sin facturación electrónica | Odoo Docker Up pero sin módulos activados, sin l10n_ve |
| P4 | Rutas de entrega sin optimización formal | 4 deliveries en dispatch.db, route planner activo pero bajo uso |
| P5 | Sin inventario digital de 165 loaners (SWAP) | bottle_movements existe pero adopción parcial |
| P6 | Reportes manuales o incompletos | Cron analytics 7am activo pero sin Odoo data source |
| P7 | Nómina calculada manualmente | Sin dispersión R4, sin Odoo hr_payroll |
| P8 | Sin memoria de cliente entre sesiones | Qdrant con 402 puntos pero "dormido" en producción |

### 3.2 Problemas que se agravan sin intervención

- Crecimiento de 16 a 30 clientes triplicaría carga operativa manual
- Cortes eléctricos en Maracaibo pueden perder pedidos en vuelo
- Cumplimiento SENIAT cada vez más estricto
- Competencia con apps de delivery (PedidosYa, etc.)

---

## 4. Solución

### 4.1 Arquitectura de la Solución (sistema ya construido, en activación)

```
┌─────────────────────────────────────────────────────────┐
│ CLIENTE (WhatsApp)                                       │
│    └→ Valentina (bridge.py) ← FSM persistente SQLite    │
│         ├→ Financial Shield v3.0 (cache pedidos/pagos)  │
│         ├→ Odoo 17 (facturación, inventario, nómina)    │
│         ├→ R4 CONECTA V3.0 (webhooks pago móvil)        │
│         └→ Dispatcher (route planner OR-Tools VRP)      │
│              └→ Chofer (Telegram bot)                   │
│                                                         │
│ PROMETEO (Telegram bot Líder)                           │
│    └→ Reportes automáticos (cron: 7am, 18:30, viernes)  │
│                                                         │
│ SOUL v2.1 (6 capas memoria)                             │
│    Episódica → Consolidador → Semántica → Warming       │
└─────────────────────────────────────────────────────────┘
```

### 4.2 Componentes del Sistema

| Componente | Rol | Estado | Tech |
|------------|-----|--------|------|
| Valentina (bridge.py) | Bot WhatsApp, FSM conversacional, orquestador | OPERATIVO | FastAPI + Meta Cloud API + SQLite WAL |
| Financial Shield v3.0 | Cache local de pedidos/pagos, anti-fraude, OCR | OPERATIVO | SQLite + Tesseract + Qwen2.5-VL |
| Dispatcher | Route planning, asignación choferes, tracking | OPERATIVO | Python + OR-Tools VRP + Telegram |
| Odoo 17 | Facturación, contabilidad, inventario, CRM, nómina | EN ACTIVACIÓN | Docker self-hosted Community |
| R4 CONECTA V3.0 | Validación y notificación de pagos móviles | SANDBOX | HMAC-SHA256 + webhooks FastAPI |
| Prometeo | Bot Telegram del Líder, reportes automáticos | OPERATIVO | Python + Telegram API |
| SOUL v2.1 | Memoria tripartita (episódica, semántica, procedural) | OPERATIVO | Qdrant + mem0 2.0.18 + Buffer |
| Cloudflared | Tunnel HTTPS permanente | OPERATIVO | valentina.estacionh2o.com |
| Prometheus + Loki | Monitoreo y logs | OPERATIVO | Docker (hermes_prometheus, hermes_loki) |

---

## 5. Requisitos Funcionales

### RF-01: Gestión de Pedidos (Valentina)
- **RF-01.1**: Recibir mensaje WhatsApp → iniciar FSM (awaiting_qty)
- **RF-01.2**: Validar mínimo 3 botellones por pedido
- **RF-01.3**: Calcular total determinísticamente (qty × precio + hielo)
- **RF-01.4**: Persistir FSM en SQLite (conversation_state) — sobrevive restarts
- **RF-01.5**: Confirmar pedido → insertar en orders + dispatch_queue
- **RF-01.6**: Sincronizar cliente en dispatch.db (upsert por phone_hash, running avg)
- **Estado**: OPERATIVO (956 tests, FSM 21/21 PASS)

### RF-02: Gestión de Pagos (Financial Shield + R4)
- **RF-02.1**: Recibir webhook R4 /notifica (HMAC-SHA256 + IP whitelist)
- **RF-02.2**: Validar CodigoRed == "00" (APROBADO)
- **RF-02.3**: Anti-fraude: UNIQUE(ref, metodo) + pHash perceptual de comprobantes
- **RF-02.4**: Transacción atómica add_pago_and_update_pedido()
- **RF-02.5**: Recovery Scan: detectar pagos atascados >24h (lifespan bridge)
- **RF-02.6**: OCR Turbo: Tesseract → Regex → Qwen2.5-VL (comprobantes imagen)
- **RF-02.7**: Auditoría: 4 triggers en fs_audit_log
- **RF-02.8**: [FASE FUTURA] sync_pago_to_odoo() → Odoo account.move Paid
- **Estado**: OPERATIVO (sandbox), R4 prod pendiente

### RF-03: Facturación (Odoo)
- **RF-03.1**: Decidir documento: RIF + método pago + override Líder (algoritmo discrecional)
- **RF-03.2**: Crear nota de entrega (stock.picking) para efectivo
- **RF-03.3**: Crear factura (account.move draft) para pago móvil con RIF
- **RF-03.4**: Conversión nota→factura sin duplicar inventario (wizard)
- **RF-03.5**: Registrar pago en factura (sync desde R4 webhook)
- **RF-03.6**: Generar PDF de factura/nota
- **RF-03.7**: [FASE FUTURA] Facturación electrónica SENIAT (XML)
- **Estado**: EN ACTIVACIÓN (Odoo Docker Up, módulos pendientes)

### RF-04: Dispatch y Rutas (Dispatcher)
- **RF-04.1**: Route planning automático (cron 07:45, OR-Tools VRP, 5 zonas Maracaibo)
- **RF-04.2**: Notificar choferes via Telegram (@DespachoH2O_bot)
- **RF-04.3**: Botones chofer: ✅ Entregado / ❌ No entregado
- **RF-04.4**: Actualizar deliveries en dispatch.db
- **RF-04.5**: Tracking GPS (gps_tracks, geofence_events)
- **RF-04.6**: SWAP: tracking de 165 loaners (bottle_movements, bottle_alerts)
- **Estado**: OPERATIVO (4 deliveries, adopción en crecimiento)

### RF-05: Reportes Automáticos (Prometeo)
- **RF-05.1**: Reporte ventas diarias (cron 07:00 → Telegram Líder)
- **RF-05.2**: Reporte cierre semanal (viernes 18:00 → Telegram)
- **RF-05.3**: Inventario hielo diario (08:00)
- **RF-05.4**: Inventario insumos semanal (lunes 08:00)
- **RF-05.5**: Nómina viernes (17:00 → aprobación Líder)
- **RF-05.6**: Recordatorios pagos pendientes (cada 30min)
- **RF-05.7**: [FASE FUTURA] ISLR mensual (día 1, 09:00)
- **Estado**: OPERATIVO (cron jobs activos, sin Odoo data source)

### RF-06: Memoria (SOUL v2.1)
- **RF-06.1**: Episódica: persistir conversaciones en SQLite (34MB)
- **RF-06.2**: Consolidador: mem0 2.0.18 post-sesión, extracción de hechos atómicos
- **RF-06.3**: Semántica: Qdrant (402 puntos, 768d embeddings nomic-embed-text)
- **RF-06.4**: Buffer: pre-carga hechos relevantes antes de respuesta
- **RF-06.5**: Social layer: patrones de interacción por cliente
- **RF-06.6**: Procedural: skills de Hermes (toda cicatriz → skill)
- **Estado**: OPERATIVO (Qdrant dormido, pendiente activación plena)

---

## 6. Requisitos No Funcionales

### RNF-01: Disponibilidad
- **RNF-01.1**: Bridge debe mantener > 99% uptime (WatchdogSec=30s, Restart=always)
- **RNF-01.2**: FSM persistente sobrevive restarts de uvicorn (SQLite, no memoria)
- **RNF-01.3**: Kill switch persistente (data/valentina.kill, 0600)
- **RNF-01.4**: Backup BD diario (scripts/backup_db.sh) + verificación mensual

### RNF-02: Seguridad
- **RNF-02.1**: Webhooks R4 con HMAC-SHA256 por endpoint + IP whitelist banco
- **RNF-02.2**: /metrics con IP allowlist (127.0.0.1, ::1, 172.19.0.0/16)
- **RNF-02.3**: LOG_SALT fail-closed (aborta startup si default inseguro)
- **RNF-02.4**: PHONE_REGEX con lookarounds (no PII en logs)
- **RNF-02.5**: .env en .gitignore (nunca commitear secrets)
- **RNF-02.6**: TLS 1.2+ via Cloudflare Tunnel (certificado válido)

### RNF-03: Performance
- **RNF-03.1**: Latencia respuesta Valentina < 5s (Meta webhook timeout 30s)
- **RNF-03.2**: SQLite WAL mode (lecturas no bloquean escrituras)
- **RNF-03.3**: Route planning OR-Tools VRP < 10s para < 20 pedidos
- **RNF-03.4**: OCR Turbo cascada (Tesseract → Regex → Qwen2.5-VL con VRAM guard)

### RNF-04: Mantenibilidad
- **RNF-04.1**: 956 tests pasando, 0 failures (pytest suite)
- **RNF-04.2**: mypy api/ = 0 errores (type hints completos en bridge.py, main.py)
- **RNF-04.3**: Coverage total > 60% (actual: 61%)
- **RNF-04.4**: Logrotate weekly (logs/*.log, rotate 4, compress)
- **RNF-04.5**: SOUL v2.1 versionado semver

### RNF-05: Observabilidad
- **RNF-05.1**: Prometheus metrics (/metrics endpoint)
- **RNF-05.2**: Loki + Promtail (Docker, logs estructurados)
- **RNF-05.3**: fs_audit_log (4 triggers, auditoría completa pedidos/pagos)
- **RNF-05.4**: Health check (/health: ok/degraded)

---

## 7. Métricas de Éxito

### 7.1 Métricas de Producto (actual → target 3 meses)

| Métrica | Actual (2026-08-26) | Target (3 meses) | Fuente |
|---------|---------------------|-------------------|--------|
| Clientes registrados (dispatch.db) | 3 | 30 | `SELECT COUNT(*) FROM clients` |
| Pedidos/día | ~2-3 (37 orders total) | 10-15 | `SELECT COUNT(*) FROM orders WHERE date = today` |
| Deliveries totales | 4 | 200+ | `SELECT COUNT(*) FROM deliveries` |
| Pagos verificados | 2 | 100+ | `SELECT COUNT(*) FROM fs_pagos` |
| Facturas Odoo emitidas | 0 (Odoo sin activar) | 50+/mes | Odoo account.move count |
| Cobertura clientes digital | 19% (3/16) | 100% (30/30) | dispatch.db clients vs estimado |

### 7.2 Métricas Técnicas (actual → target)

| Métrica | Actual | Target | Fuente |
|---------|--------|--------|--------|
| Tests pasando | 956 | > 960 | pytest |
| Tests fallando | 0 | 0 | pytest |
| Coverage total | 61% | > 70% | pytest-cov |
| mypy api/ errores | 0 | 0 | mypy |
| Servicios active | 4+2 Docker | 4+2 | systemctl + docker ps |
| Fallas P0/P1 abiertas | 0 | 0 | ROADMAP-vivo |
| Puntos Qdrant | 402 | > 500 | Qdrant count |
| Commits totales | 194 | > 210 | git rev-list --count |

### 7.3 Métricas de Negocio (actual → target)

| Métrica | Actual | Target 3 meses | Fuente |
|---------|--------|----------------|--------|
| Recurrencia (clientes que repiten) | No medido | > 60% | orders agrupados por phone_hash |
| Tiempo entrega (pedido→entrega) | No medido | < 2h | deliveries created_at vs delivered_at |
| Tasa pago verificado | 100% (2/2 manual) | > 95% automatizado | fs_pagos verificados |
| Ingresos recurrentes | 0 | Inicio (suscripción piloto) | Odoo subscriptions |
| Adopción choferes Telegram | 0/2 confirmado | 2/2 | dispatcher-bot activity |

---

## 8. Roadmap (basado en ROADMAP-vivo.md + PLAN-DESARROLLO-HERMES.md)

### FASE 1 — COMPLETADA (2026-07-21 a 2026-07-28)

| Item | Estado | Evidencia |
|------|--------|-----------|
| Bridge → dispatch_queue | HECHO | commit fd9ff21, 5/5 E2E PASS |
| Sync clients dispatch.db | HECHO | upsert por phone_hash |
| Reparaciones r1-r7 | HECHO | commit 7d656a8 (init_db, FK, WAL, LOG_SALT, botones, use-after-close) |
| FSM persistente SQLite | HECHO | commit 3cda570, 21/21 PASS |
| Watchdog systemd | HECHO | commit e24fcbf, 8/8 PASS |
| PHONE_REGEX preciso | HECHO | commit 89d4747, 20/20 PASS |
| Financial Shield v3.0 | HECHO | commit 91439f7, 21 nuevos tests |
| Bugs Día 15 | HECHO | commit 18bc053, 4/4 resueltos |
| mypy api/ | HECHO | commit 1028066, 66→0 bridge, 8→0 main |
| ruff E501 | HECHO | commit 523d899, 46→0 |
| test_bridge.py | HECHO | commit a3a58ee, 27 tests |
| Cleanup infraestructura | HECHO | commit e8a4509 (cloudflared, .bak, logrotate, backup) |

### FASE 2 — EN PROGRESO (2026-07-28 → activo)

| Item | Estado | Notas |
|------|--------|-------|
| Financial Agent | INICIANDO | src/financial/ existe, cobranzas.py + reportes.py |
| Route Skill avanzado | OPERATIVO | route_engine.py con haversine + 5 zonas |
| Analytics Skill | OPERATIVO | run_analytics_7am.py cron activo |
| Dispatcher avanzado | OPERATIVO | dispatcher.py + Telegram bot, 4 deliveries |
| SOUL v2.1 FASE 3 | HECHO | Consolidador mem0 2.0.18, Qdrant 402pts, Buffer layer |

### FASE 3 — Odoo + R4 (PLAN-DESARROLLO-HERMES.md)

| Item | Estado | Notas |
|------|--------|-------|
| FASE 0: Preparación entorno | PENDIENTE | Backup, rama, verificar servicios |
| FASE 1: Estructura archivos | HECHO | src/integrations/odoo/ + r4/ creados |
| FASE 2: Configurar API Keys | PENDIENTE | .env con ODOO_* + R4_* |
| FASE 3: Docs referencia vault | PARCIAL | R4 docs existen, ADRs pendientes |
| FASE 4: Desarrollo módulos Python | PARCIAL | R4 client.py completo, odoo_sync.py creado |
| FASE 5: Tests unitarios | PARCIAL | test_r4_webhooks_coverage.py, test_r4_commerce_secret_split.py |
| FASE 6: Cron jobs systemd | PENDIENTE | 7 timers a configurar |
| FASE 7: Seguridad | PARCIAL | IP whitelist + HMAC activos, rate limiter existe |
| FASE 8: Tests E2E | PARCIAL | test_fase8_e2e.py existe |
| FASE 9: Monitoreo | PARCIAL | Prometheus + Loki activos, métricas Odoo/R4 pendientes |
| FASE 10: Documentación | PARCIAL | 3 runbooks en docs/04-runbooks/ |
| FASE 11: Rollout progresivo | PENDIENTE | 8 semanas, 10%→50%→100% |

### FASE FUTURA

| Item | Estado |
|------|--------|
| Facturación electrónica SENIAT (XML) | FASE FUTURA |
| Qdrant activación plena en producción | FASE FUTURA |
| Suscripciones restaurantes (Odoo subscriptions) | FASE FUTURA |
| Sistema 5/7 lealtad | FASE FUTURA |
| Pre-pago botellones | FASE FUTURA |
| Referidos cliente | FASE FUTURA |

---

## 9. Restricciones y Dependencias

- **R4 CONECTA**: Bloqueado por entrega de credenciales de producción por el banco
- **Odoo**: Community self-hosted (gratis), requiere activación manual de módulos
- **SENIAT**: Facturación electrónica requiere proveedor externo certificado
- **Hardware**: Servidor local Maracaibo, vulnerable a cortes eléctricos
- **Modelos IA**: Ollama local (qwen2.5:7b, qwen2.5-vl, qwen2.5:3b, nomic-embed-text) — sin dependencia de cloud para inferencia
- **OpenRouter**: GLM 5.2 para Prometeo (orquestación y razonamiento)

---

**Firma**: 💧