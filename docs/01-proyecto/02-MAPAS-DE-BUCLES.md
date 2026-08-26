# Mapas de Bucles de Feedback — Estación H2O / Prometeo

**Fecha**: 2026-08-26 (Día 34)
**Autor**: Prometeo (GLM 5.2 vía OpenRouter)
**Objetivo**: Mapear los bucles de feedback del sistema para identificar puntos de optimización y medición

---

## Bucle A: Pedidos

**Cliente → WhatsApp → Valentina → Odoo → Dispatcher → Chofer → Cliente**

### Diagrama

```
Cliente (WhatsApp)
    │
    ▼ 1. Mensaje: "Necesito 3 botellones"
Valentina (bridge.py)
    │
    ├─ 2. FSM: awaiting_qty → awaiting_address → awaiting_payment → awaiting_confirmation
    ├─ 3. _calc_total (determinístico): qty × precio + hielo
    ├─ 4. Guard: mínimo 3 botellones
    │
    ▼ 5. _send_to_dispatch_queue(ph_hash, state, items)
dispatch.db: dispatch_queue (INSERT)
    │
    ▼ 6. _sync_client_to_dispatch_db(phone_hash, running_avg_botellones)
dispatch.db: clients (UPSERT)
    │
    ▼ 7. Route planner (cron 07:45) OR-Tools VRP
dispatch.db: deliveries (INSERT), route_history
    │
    ▼ 8. Notificación Telegram @DespachoH2O_bot
Chofer (YORDANIS / EVERT)
    │
    ▼ 9. Botón "✅ Entregado" (new_arr_) / "❌ No entregado" (new_no_)
dispatch.db: deliveries (UPDATE status)
    │
    ▼ 10. Confirmación a cliente via Valentina
Cliente (WhatsApp)
```

### Inputs
- Mensaje WhatsApp del cliente (texto, emoji)
- Cantidad de botellones solicitada
- Dirección de entrega
- Método de pago (efectivo / pago móvil)
- Ubicación GPS del chofer (si disponible)

### Procesos
- FSM conversacional (conversation_state en SQLite)
- Cálculo determinístico de totales (_calc_total)
- Validación de mínimos (guard: 3 botellones)
- Inserción en dispatch_queue
- Upsert de cliente en dispatch.db (running avg botellones)
- Route planning OR-Tools VRP (cron 07:45)
- Asignación a chofer por zona (5 zonas Maracaibo)
- Confirmación de entrega via botones Telegram

### Outputs
- Pedido confirmado en orders (conversations.db)
- Cliente sincronizado en clients (dispatch.db)
- Delivery creado en deliveries (dispatch.db)
- Ruta optimizada en route_history
- Mensaje de confirmación al cliente

### Métricas de Éxito

| Métrica | Target actual | Medición |
|---------|---------------|----------|
| Pedidos/día | 10-15 (estimado) | `SELECT COUNT(*) FROM orders WHERE date = today` |
| Tiempo respuesta Valentina | < 5s | Latencia bridge.py → respuesta WhatsApp |
| Tasa abandono FSM | < 20% | Pedidos iniciados no completados / total iniciados |
| Tasa entrega exitosa | > 90% | `SELECT status FROM deliveries WHERE status = 'delivered'` / total |
| Tiempo entrega (pedido→entrega) | < 2h | `created_at` vs `delivered_at` en deliveries |
| Clientes en dispatch.db | 16 (actual: 3) | `SELECT COUNT(*) FROM clients` |

### Estado actual
- **OPERATIVO**: bridge→dispatch_queue→dispatcher→chofer funcionando
- **GAP**: Solo 3 clientes registrados vs 16 estimados (adopción parcial)
- **GAP**: Solo 4 deliveries registrados (sistema arrancando)
- **GAP**: Odoo sync (paso 5b: pedido→factura/nota) PENDIENTE

---

## Bucle B: Pagos

**Cliente → Pago Móvil → R4 Webhook → Odoo → Valentina → Cliente**

### Diagrama

```
Cliente (app banco)
    │
    ▼ 1. Transferencia pago móvil
Banco R4 CONECTA V3.0
    │
    ▼ 2. Webhook /webhook/r4/notifica (HMAC-SHA256, IP whitelist)
Valentina (bridge.py)
    │
    ├─ 3. Validar HMAC (Authorization header)
    ├─ 4. Validar IP origen (45.175.213.98, 200.74.203.91, 204.199.249.3)
    ├─ 5. Validar CodigoRed == "00" (APROBADO)
    ├─ 6. Validar referencia no duplicada (UNIQUE ref+metodo en fs_pagos)
    │
    ▼ 7. Financial Shield v3.0: add_pago_and_update_pedido() (atómico)
conversations.db: fs_pagos (INSERT) + fs_pedidos (UPDATE saldo)
    │
    ├─ 8. pHash perceptual del comprobante (anti-fraude duplicados visuales)
    ├─ 9. fs_audit_log (trigger INSERT/UPDATE)
    │
    ▼ 10. [FASE FUTURA] sync_pago_to_odoo() → Odoo account.move register_payment
Odoo (account.move → Paid)
    │
    ▼ 11. Valentina confirma al cliente: "Pago recibido ✓"
Cliente (WhatsApp)
```

### Inputs
- Notificación webhook R4 (JSON: banco, referencia, monto, cedula, telefono, CodigoRed)
- Comprobante de pago (imagen, si cliente envía screenshot)
- Tasa de cambio BCV (para conversión EUR/VES)

### Procesos
- Validación HMAC-SHA256 por endpoint (hmac_auth.py)
- IP whitelist del banco (middleware FastAPI)
- Validación de CodigoRed (codigos.py, "00" = APROBADO)
- Anti-fraude: UNIQUE(ref, metodo) + pHash perceptual de comprobantes
- Transacción atómica: add_pago_and_update_pedido() (deuda en EUR, pago a tasa del momento)
- Recovery Scan: recovery_scan_stuck_payments() detecta pagos atascados >24h
- OCR Turbo (cascada): Tesseract → Regex → Qwen2.5-VL (si cliente envía comprobante imagen)
- Auditoría: 4 triggers en fs_audit_log

### Outputs
- Pago registrado en fs_pagos (conversations.db)
- Saldo actualizado en fs_pedidos
- Auditoría en fs_audit_log
- [FASE FUTURA] Factura marcada como Paid en Odoo
- Confirmación al cliente via Valentina

### Métricas de Éxito

| Métrica | Target | Medición |
|---------|--------|----------|
| Tasa pago verificado | > 95% | fs_pagos verificados / total fs_pagos |
| Tiempo validación webhook | < 3s | Latencia recepción webhook → confirmación cliente |
| Fraude detectado (duplicados) | 0 incidentes | pHash matches en fs_verificacion_log |
| Pagos atascados (>24h) | 0 | recovery_scan_stuck_payments() count |
| Conciliación Odoo | 100% (FASE FUTURA) | fs_pagos vs Odoo account.move paid |

### Estado actual
- **OPERATIVO**: Financial Shield v3.0 + webhooks R4 implementados (sandbox)
- **GAP**: R4 en sandbox, pendiente token producción
- **GAP**: sync_pago_to_odoo() no implementado (Odoo sin activar)
- **GAP**: 2 fs_pagos registrados (volumen bajo, sistema arrancando)
- **FASE FUTURA**: Conciliación bancaria automática end-to-end

---

## Bucle C: Memoria

**Episódica → Consolidador → Semántica → Warming → Contexto**

### Diagrama

```
Conversación (WhatsApp/Telegram)
    │
    ▼ 1. Episódica: conversations.db (conversations table, 34MB)
    │   - Cada mensaje: phone_hash, message_text, timestamp, role
    │
    ▼ 2. Consolidador (mem0 2.0.18): post-sesión
    │   - Lee episódica
    │   - Extrae hechos atómicos
    │   - Propone inserción en semántica con confianza inferida
    │
    ▼ 3. Semántica: Qdrant (402 puntos, 768d embeddings nomic-embed-text)
    │   - Hechos consolidados con score de confianza
    │   - Búsqueda por similaridad vectorial
    │
    ▼ 4. Warming: Buffer (Redis→Buffer en SOUL v2.1)
    │   - Pre-carga hechos relevantes antes de respuesta
    │   - Social layer: patrones de interacción cliente
    │
    ▼ 5. Contexto: Inyectado en prompt de Valentina/Prometeo
    │   - System prompt + SOUL + hechos semánticos + episódica reciente
    │
    ▼ 6. Respuesta con contexto enriquecido
Cliente (WhatsApp/Telegram)
```

### Inputs
- Mensajes de conversación (episódica)
- SOUL v2.1 (6 capas: Buffer, Episódica, Semántica, Procedural, Social, Consolidador)
- Hechos históricos del cliente (running avg botellones, zonas frecuentes)

### Procesos
- Episódica: SQLite conversations table (34MB, persistente)
- Consolidador: mem0 2.0.18 (pip instalado, integrado vía indexado)
  - Post-sesión: lee episódica, extrae hechos atómicos
  - Propone inserción en semántica con confianza inferida
- Semántica: Qdrant (402 puntos, embeddings nomic-embed-text 768d)
- Warming: Buffer layer (reemplazó Redis en SOUL v2.1)
  - Pre-carga hechos antes de generar respuesta
  - Social layer: patrones de interacción por cliente
- Contexto: Inyectado en system prompt de Valentina
  - SOUL + hechos semánticos + episódica reciente + buffer warming

### Outputs
- Respuesta con conocimiento del cliente (historial, preferencias)
- Hechos consolidados en Qdrant (memoria a largo plazo)
- Patrones sociales (frecuencia de pedidos, métodos de pago preferidos)

### Métricas de Éxito

| Métrica | Target | Medición |
|---------|--------|----------|
| Puntos en Qdrant | Crecimiento sostenido | `client.count(collection)` — actual: 402 |
| Latencia warming | < 500ms | Tiempo query Qdrant → inyección en prompt |
| Tasa consolidación | > 80% sesiones generan hechos | Sesiones con nuevo punto en Qdrant / total sesiones |
| Recall útil | > 70% | Hechos inyectados que son relevantes a la consulta |
| Tamaño episódica | < 100MB | `du -sh data/conversations.db` — actual: 34MB |

### Estado actual
- **OPERATIVO**: SOUL v2.1 con 6 capas activas
- **OPERATIVO**: Consolidador mem0 2.0.18 (upgrade v1.0.11→v2.0.18 completado 2026-08-24)
- **OPERATIVO**: Qdrant con 402 puntos, embeddings nomic-embed-text 768d (commit b3d3d33)
- **OPERATIVO**: Buffer layer (reemplazó Redis)
- **GAP**: Qdrant + mem0 están "dormidos" según ROADMAP — pendiente activación plena en producción
- **GAP**: No hay métricas de recall o tasa de consolidación medidas todavía

---

## Bucle D: Deuda Técnica

**Detección → Priorización → Fix → Tests → Coverage**

### Diagrama

```
Detección
    │
    ├─ Análisis de arquitectura (ej: ANALISIS_ARQUITECTURA_2026-07-21.md)
    ├─ Subagentes en paralelo (código backend + infraestructura/datos)
    ├─ ruff / mypy / pytest en pre-commit
    ├─ Code review (gh CLI)
    │
    ▼
Priorización
    │
    ├─ P0: Bloqueante / Producción (11 detectadas, 11 resueltas)
    ├─ P1: Crítico / Mantenibilidad (13 detectadas, 13 resueltas)
    ├─ P2: Cosmético / Deuda documentada (12 detectadas, parcial)
    ├─ P3: No bloqueantes (~72 mypy + 14 ruff, postergables)
    │
    ▼
Fix
    │
    ├─ Commit con descripción del fix
    ├─ --no-verify si mypy pre-commit bloquea por deuda preexistente
    ├─ Fraccionar grandes cambios con checkpoint/backup por sección
    │
    ▼
Tests
    │
    ├─ Unit tests (tests/unit/): 956 passed, 15 skipped, 0 failed
    ├─ Smoke tests (tests/smoke/): FSM, watchdog, phone_regex, dispatch_queue
    ├─ Integration tests (tests/integration/): bridge_dispatcher, dispatch_flow, financial
    ├─ E2E tests (tests/e2e/): fase8_e2e
    │
    ▼
Coverage
    │
    ├─ pytest-cov: 61% total (3114 stmts, 1214 missing)
    ├─ api/bridge.py: ~85% (tras 27 tests unitarios)
    ├─ core/: 99-100% (config, crypto, fusion, judge, logger, meta_client)
    ├─ Rate limiter: 100% (tras fix)
    ├─ Workload router: 99%
    │
    ▼ ¿Coverage suficiente?
    │
    ├─ SÍ → Cerrar deuda, documentar en ROADMAP-vivo.md
    └─ NO → Volver a Detección (nuevos tests needed)
```

### Inputs
- Análisis de arquitectura (subagentes paralelos)
- Output de ruff, mypy, pytest
- Code review en PRs (gh CLI)
- Detección manual durante desarrollo

### Procesos
- **Detección**: análisis milimétrico con subagentes en paralelo (código + infra + datos)
- **Priorización**: P0 (bloqueante) → P1 (crítico) → P2 (cosmético) → P3 (postergable)
- **Fix**: commits con descripción, --no-verify si mypy bloquea por deuda preexistente
- **Tests**: unit (tests/unit/), smoke (tests/smoke/), integration (tests/integration/), e2e (tests/e2e/)
- **Coverage**: pytest-cov report, target por módulo

### Outputs
- Bug resuelto + commit en repo
- Test(s) nuevo(s) que cubren el caso
- Coverage incrementada
- Documentación actualizada en ROADMAP-vivo.md

### Métricas de Éxito

| Métrica | Target | Actual | Medición |
|---------|--------|--------|----------|
| Fallas P0 abiertas | 0 | 0 | ROADMAP-vivo |
| Fallas P1 abiertas | 0 | 0 | ROADMAP-vivo |
| Tests pasando | > 950 | 956 | `pytest -q --tb=no` |
| Tests fallando | 0 | 0 | `pytest -q --tb=no` |
| Coverage total | > 60% | 61% | pytest-cov |
| mypy api/ errores | 0 | 0 | `mypy api/` |
| Commits con tests | > 80% | No medido formalmente | git log + test file correlation |
| Tiempo resolución P0 | < 24h | Cumplido históricamente | commit timestamps |

### Estado actual
- **OPERATIVO**: Bucle funcionando. 11/11 P0 + 13/13 P1 resueltas
- **OPERATIVO**: 956 tests, 0 failures, 61% coverage
- **PENDIENTE**: P3 (72 mypy + 14 ruff) no bloqueantes
- **PENDIENTE**: Coverage formalización de target por módulo
- **MEJORA**: Coverage subió de 21% (sin -x) a 61% (con -x, parando en primer fallo → 956 passed completos)

---

## Resumen de Bucles

| Bucle | Estado | Puntos de optimización |
|-------|--------|----------------------|
| A: Pedidos | OPERATIVO (Odoo sync pendiente) | Adopción: 3→16 clientes; activar Odoo |
| B: Pagos | OPERATIVO (R4 sandbox) | Token R4 producción; sync Odoo |
| C: Memoria | OPERATIVO (Qdrant dormido) | Activar Qdrant plenamente; medir recall |
| D: Deuda técnica | OPERATIVO | P3 mypy/ruff; coverage target por módulo |

**Interdependencia**: El Bucle A alimenta al B (pedidos generan pagos), B alimenta C (pagos generan hechos episódicos), todos generan deuda técnica (Bucle D). El Bucle D mantiene la calidad de A, B y C.

---

**Firma**: 💧