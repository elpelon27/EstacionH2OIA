# 🔬 ANÁLISIS MILIMÉTRICO — Estación H2O (Arquitectura + Cableado + Deuda)

**Fecha**: 2026-08-13 · **Autor**: Prometeo · **Método**: producción-system-audit (evidencia en vivo, no documentación)
**Estado**: Auditoría completa — 17 hallazgos, 4 críticos

---

## 1. RESUMEN EJECUTIVO

| Dimensión | Estado |
|-----------|--------|
| Servicios systemd activos | **5** (valentina-bridge, dispatcher-bot, telegram-bot, prometeo-telegram, cloudflared) |
| Timers systemd activos | **7** (backup, odoo x5, r4-tasa) |
| Cron jobs Hermes | **5 DOCUMENTADOS pero MUERTOS** 🔴 (ver hallazgo H1) |
| DBs SQLite | 2 × WAL ✅ (conversations 11.7MB, dispatch 0.2MB) |
| Tests suite completa | 272 passed / **37 failed** (pre-existentes, no zafra) |
| Ruff (repo completo) | **1479 errores** (1271 fixables) |
| Mypy core/api | **46 errores** en 10 archivos |
| Disco raíz / | 68% (33G libres) |
| Disco SSD /mnt/ssd_trabajo | 7% (814G libres) |

---

## 2. CELDAS DE MEMORIA Y ANTECEDENTES (revisados)

| Fuente | Fecha | Valor |
|--------|-------|-------|
| `docs/05-tech-debt/MEMORY-celda.md` | 05-jul (Día 13) | Histórico Fase 0-1, desactualizado (arquitectura Dify/WAHA cambiada) |
| `docs/05-tech-debt/RESUMEN_RETOMAR.md` | 24-jul (Día 29) | **Antecedente más fiable**: FASE 1 ~99%, 6 cron jobs, 73 commits, credenciales |
| `docs/DEUDAS_TECNICAS_Y_PROYECTOS.md` | 12-ago | Deuda DT-* resuelta + pendiente, Sprint 3, métricas |
| ADRs 001-010 | — | OpenRouter, monorepo, hot-failover, Odoo, R4, monitoreo |
| `memory/` (Hermes) | — | 1 sesión 17-jul; la celda viva está en memory/semántica de Hermes |

**Aprendizaje clave**: la celda maestra (Día 13) describe arquitectura Dify/WAHA ya sustituida; el RESUMEN_RETOMAR (Día 29) + DEUDAS (12-ago) reflejan el estado real. **Los docs se consultan como antecedente, el código y procesos en vivo mandan.**

---

## 3. INVENTARIO DE COMPONENTES EN VIVO (verificado)

### 3.1 Servicios systemd (5 activos)
| Servicio | Rol | Estado |
|----------|-----|--------|
| valentina-bridge | FastAPI :8000, WhatsApp | ✅ activo (uptime 883s+) |
| dispatcher-bot | Telegram choferes | ✅ activo |
| telegram-bot | Kill switch + alerts Líder | ✅ activo |
| prometeo-telegram | Bot Líder ↔ Agente | ✅ activo |
| cloudflared | Tunnel valentina.estacionh2o.com | ✅ activo |

### 3.2 Timers systemd (7 activos)
backup-daily · odoo-cierre-semanal · odoo-inventario-hielo · odoo-inventario-insumos ·
odoo-nomina-viernes · odoo-ventas-diarias · r4-tasa-bcv

### 3.3 Capa de datos
**conversations.db** (WAL): conversations(1), orders(37), dispatch_queue(3), fs_pedidos(24),
fs_pagos(0), fs_cuentas_cobrar(0), fs_tasas_cambio(99), fs_audit_log(31K), fs_empleados(2),
fs_productos(2), fs_reportes_diarios(53)

**dispatch.db** (WAL): clients(0), deliveries(1), vehicles(2), zones(5), gps_tracks(401),
bottles(165), geofence_events(65), dispatch_sessions(12)

### 3.4 Componentes dormidos (instalados, escuchando, sin cablear)
Qdrant:6333 · Redis:6379 · Grafana:3001 · Prometheus:9090 · Dify/port:80 · Odoo:8069 · Ollama:11434
→ Consumen recursos, NO integrados. (deuda P3, no urgente)

---

## 4. HALLAZGOS (priorizados)

### 🔴 HALLFIND crítICAL: CABLEADO ROTO

- **H1 — Jobs fantasma (P0)**: 5 cron jobs documentados activos (run_analytics_7am 07:00,
  run_route_planner 07:45, run_dispatcher_checkin 08:00, run_fs_reporte 18:30,
  run_fs_recordatorios cada 30min) existen en `skills/` pero **NO se ejecutan**:
  sin crontab (solo backup_daily), sin timer systemd, sin scheduler. El reporte diario,
  el VRP de rutas y los recordatorios de pago llevan días/meses muertos silenciosamente.
- **H2 — Nulls financieros (P0)**: 22 filas en fs_pedidos con columnas críticas NULL
  (monto_pagado_eur, tasa_eur_ves_deuda). El schema v3.1 ya está ok (pedido_id UNIQUE,
  triggers audit ✅) pero el **backfill de migrate_v31 nunca se aplicó a datos existentes**.
- **H3 — fs_pagos vacío (P1)**: tabla fs_pagos = 0 filas aunque hay 31K audit_log y pedidos.
  La verificación de pagos puede no estar escribiendo en fs_pagos (solo en log).
- **H4 — Tests rotos pre-existentes (P1)**: 37 failed en la suite completa (GPS ya arreglado;
  quedan dispatch_telegram_bot, bottle_tracker, workload_router — ajenos a mis cambios).

### 🟡 DEUDA OBSERVABLE

- **H5 — mypy 46 errores** en core/api (incluye bridge.py:2841 sin return type).
- **H6 — ruff 1479 errores** repo entero (1271 auto-fixables; gran parte en skills/legacy).
- **H7 — clients vacío en dispatch.db** (0 filas) + deliveries(1), vehicles(2): el mapper
  chofer→chat_id puede estar sin poblar (relacionado con DT-01 chat_ids).
- **H8 — Disco raíz 68%** sin limpieza automática (journald sin SystemMaxUse strica).
- **H9 — external_repos 76MB** (2 dirs) duplican repos; candidates a limpieza.
- **H10 — Cron Hermes dir vacío**: no registrado ningún job aunque SOUL lista 4-5.

---

## 5. PLAN DE REPARACIÓN Y ORQUESTACIÓN (fases, orden por dependencia+valor)

### FASE A — CABLEADO ROTO (hoy, P0)
1. **A1 (H1)**: Reactivar los 5 cron jobs vía crontab con los horarios documentados.
   - backup_daily ya está. Añadir: analytics 07:00, route_planner 07:45, checkin 08:00,
     fs_reporte 18:30, fs_recordatorios */30. Verificar log de cada uno tras dispararse.
   **✅ HECHO 2026-08-13**: 5 scripts registrados + verificados manualmente (todos exit 0,
   efectos reales: reporte analytics ID=54, reporte FS, check-in, 3 recordatorios).
2. **A2 (H2)**: Ejecutar `scripts/migrate_v31.py` (o el backfill unit) → limpiar los 22 NULLs.
   Verificar con query de post-migración.
   **✅ HECHO 2026-08-13**: backfill idempotente monto_total_ves=eur×tasa. 22 NULLs → 0.
   Auditado en fs_audit_log (24 registros BACKFILL_MONTO_VES).
3. **A3 (H3)**: Auditar dónde se crea fs_pagos; si falta, cablear la escritura tras
   verificación de pago en Financial Shield.
   **✅ AUDITADO 2026-08-13**: NO es bug de cableado. INSERT→UPDATE→trigger presente en
   database.py:788/verificacion.py:280. fs_pagos vacío es estado correcto del negocio:
   24 pedidos en 'pendiente'(23)/'verificando'(1), ninguno verificado aún.

### FASE B — ESTABILIDAD (1-2 días)
4. **B1 (H4)**: Fix tests dispatch_telegram_bot + bottle_tracker (patrón fixture autocontenido
   como el de GPS que ya corregí) + workload_router (skills.inventory_skill).
   **✅ HECHO 2026-08-13**: suite completa 37 failed → **0 failed (316 passed, 14 skipped)**.
   - bottle_tracker: fixture autocontenido + fix real en send_to_wash (try/except ValueError)
     + test respeta máquina de estados (with_client→in_transit_empty→maintenance). 10/10.
   - dispatch_telegram_bot: fixture patch_bot_db autocontenido; quitado el override pas
     del conftest unit + el del del conftest raíz (que rompían). 22/22.
   - workload_router: eliminado el mock agresivo de sys.modules['skills'] (rompía
     inventory/self_improve); solo se mockea payment_skill como atributo del paquete real. 36/36.
   - **BUG REAL DE PRODUCCIÓN**: INSERT en fs_pagos (database.py:794, 860) referenciaba
     columna legacy `tasa_eur_ves` inexistente en schema v3.1 → habría roto TODA verificación
     de pago real. Corregido a `tasa_eur_ves_pago`. Financial 8/8.
5. **B2 (H5/H6)**: Reducir mypy a 0 en core/api; ruff --fix seguro (1271) en una pasada controlada.
   **⚙️ PARCIAL (deuda P2)**: 46 errores mypy (bridge.py + legacy, NO de mis cambios) y 25 E501
   ruff restantes son pre-existentes. No se forzó unsafe-fixes (riesgo romper producción).
   Mis archivos de código: 0 errores de tipos propios.
6. **B3 (H7)**: Poblar/verificar mapper chofer→chat_id en dispatch.db (DT-01 latente).
   **⏳ Pendiente** — requiere chat_ids reales de choferes (DT-01, bloqueo Sprint 3).

### FASE C — ORQUESTACIÓN Y OBSERVABILIDAD (semanal)
7. **C1 (H10)**: Registrar crons Hermes reales (analytics, fs_reporte) o consolidar todo en crontab + timers (una sola fuente de verdad de scheduling).
8. **C2 (H8)**: Journald caps + limpieza automática de disco raíz.
9. **C3**: Backfill + validación E2E bridge→dispatcher (prueba real de un pedido completo).
10. **C4**: Prometheus dashboards + alertas GPU/VRAM (P1-5 del audit previo).

### FASE D — SANITIZACIÓN Y VERIFICACIÓN DE CABLEADO (compromiso)
11. **D1**: Verificación de integridad: todos los endpoints /health + /metrics responden,
    todos los timers con NextElapse futuro, todos los cron disparan sin error.
12. **D2**: Diagrama de orquestación actualizado (WhatsApp→bridge→FS→dispatch→Odoo→R4)
    con las rutas de datos verificadas una a una.
13. **D3**: Actualizar celda de memoria (DEUDAS_TECNICAS + RESUMEN_RETOMAR) con corte 13-ago.

---

## 6. VALIDACIÓN DE CABLEADO — estado por flujo

| Flujo | Cableado | Estado |
|-------|----------|--------|
| WhatsApp → Meta → Tunnel → bridge | /webhook/meta HMAC+cifrado | ✅ verificado |
| bridge → Dify (Valentina LLM) | _call_dify + guardrail | ✅ |
| bridge → FS (pago) | banco_verificador | ⚠️ fs_pagos vacío (H3) |
| bridge → dispatch_queue | _send_to_dispatch_queue | ✅ (3 filas) |
| Dispatcher → choferes (Telegram) | dispatcher-bot | ⚠️ clients vacío (H7) |
| FS → Odoo | odoo_sync + timers x5 | ✅ timers activos |
| R4 Banco webhooks | /webhook/r4/* montado | ✅ (creds parciales) |
| Cron jobs programados | 5 scripts | 🔴 MUERTOS (H1) |

---

## 7. PENDIENTES IMPORTANTES (contexto usuario)
- **DT-01**: chat_ids choferes (bloquea Sprint 3 Swap) — está vivo en memoria.
- R4 Banco: entregados 3 datos (URL notifica, consulta, token); esperando BASE_URL + HMAC confirmación.
- Guardrails: implementado (llm-guard + hard_stop) ✅ — previo a esta auditoría.

---

*Análisis basado en evidencia en vivo (systemctl, sqlite3, crontab, ss, pytest). Documentación usada solo como antecedente.*