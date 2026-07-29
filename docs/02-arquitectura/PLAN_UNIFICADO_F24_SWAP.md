# 📋 PLAN UNIFICADO FASE 2.4 — DISPATCHER AVANZADO + SWAP
**Estación H2O · Maracaibo, Venezuela**  
**Versión**: 1.0 | **Fecha**: 2026-07-28 | **Autor**: Prometeo (GLM 5.2 vía Hermes)  
**Fuentes fusionadas**:  
- `docs/02-arquitectura/DISPATCHER_ARCHITECTURE.md` (arquitectura técnica, 921 líneas)  
- `Protocolo_Implementacion_Swap.pdf` (protocolo negocio, 122 páginas)  
- `docs/02-arquitectura/ROADMAP-vivo.md` (estado real repo, 173 líneas)  
- Estado actual repo (commits, BD, skills, tests)  

**Principio rector**: *Escalabilidad por diseño — el dispatcher será el componente más modificado. Arquitectura modular, interfaces claras, deuda técnica cero al ingresar.*

---

## 🎯 OBJETIVO ESTRATÉGICO

Construir un **Dispatcher Avanzado** que sea el cerebro logístico del modelo **Swap** (botellón loaner + sellado en planta), integrando:
- **Ruteo óptimo** (OR-Tools VRP + Haversine → futuro OSRM)
- **Despacho a operadores** (Telegram Bot dedicado)
- **Tracking GPS** (Tasker automático + check-in manual)
- **Inventario de botellones loaner** (165 unidades, tracking individual)
- **Integración nativa** con Valentina (bridge) + Financial Shield v3.0
- **Escalabilidad nativa**: preparado para OSRM, Fleetbase, ML prediction, 2º/3er triciclo

---

## 📦 ESTADO ACTUAL (Baseline 2026-07-28)

| Componente | Estado actual del repo | 
|----------------------| 
| **FASE 1**: 100% completa ✅ | 
| **Financial Shield v3.0**: Deployado en prod ✅ | 
| **BD `dispatch.db`**: Schema completo ✅ (11 tablas, índices, FKs) | 
| **Route Engine** (`skills/dispatch/route_engine.py`) | ✅ Completo (OR-Tools VRP + Haversine + fallback NN) |
| **Dispatcher Bot** (`skills/dispatcher.py`) | ✅ Funcional (standalone, registro choferes, check-in, botones) |
| **Route Planner Cron** (`skills/run_route_planner.py`) | ✅ 7:45am activo (OR-Tools VRP) |
| **Bridge → Dispatch Queue** | ✅ Integrado (`_send_to_dispatch_queue` en bridge.py) |
| **Seed Data** (zonas, vehículos) | ⚠️ Parcial en BD, falta script `seed_data.py` |
| **DispatcherSkill + WorkloadRouter** | ❌ **FALTA** (crítico) |
| **FastAPI Endpoints** (`/dispatch/*`) | ❌ **FALTA** (crítico) |
| **Bridge → Dispatcher Integration** | ❌ **FALTA** (crítico: `send_delivery_to_chofer` no llamado) |
| **Webhook TG Choferes** | ❌ **FALTA** (crítico) |
| **GPS Tracker Skill** | ❌ Falta (Tasker + Telegram) |
| **Seed Data Script** | ❌ Falta |
| **Tests E2E** | ❌ Faltan |

---

## 🏗️ ARQUITECTURA ESCALABLE — DISEÑO MODULAR

```
┌─────────────────────────────────────────────────────────────────────┐
│                        HERMES AGENT (Ubuntu Local)                  │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                    WORKLOAD ROUTER                            │   │
│  │  Routes: dispatch_request, dispatch_route_compute,           │   │
│  │  dispatch_delivery_update, dispatch_gps_track                │   │
│  └────────────────────────┬──────────────────────────────────────┘   │
│                           │                                          │
│                           v                                          │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │              DISPATCHER SKILL (BaseSkill)                   │   │
│  │  Actions: compute_route, notify_driver, update_delivery,    │   │
│  │  insert_dynamic_stop, record_gps, check_geofence,           │   │
│  │  get_heatmap_data, get_bottle_inventory                     │   │
│  └────────────────────────┬──────────────────────────────────────┘   │
│                           │                                          │
│         ┌─────────────────┼─────────────────┬────────────────────┐  │
│         v                 v                 v                    v  │
│  ┌───────────────┐ ┌───────────────┐ ┌───────────────┐ ┌────────┐ │
│  │ Route Engine  │ │ Telegram Bot  │ │ GPS Tracker   │ │ Swap   │ │
│  │ (OR-Tools)    │ │ (Operadores)  │ │ (Tasker+TG)   │ │ Tracker│ │
│  └───────┬───────┘ └───────┬───────┘ └───────┬───────┘ └────┬───┘ │
│         │                 │                 │              │      │
│         └─────────────────┼─────────────────┼──────────────┘      │
│                           v                 v                      │
│              ┌─────────────────────────────────────────────┐      │
│              │         SQLite (dispatch.db)                │      │
│              │  clients | deliveries | gps_tracks | bottles │      │
│              │  vehicles | zones | route_history            │      │
│              └─────────────────────────────────────────────┘      │
└─────────────────────────────────────────────────────────────────────┘
```

### Principios de Escalabilidad (Diseño por Contrato)

| Principio | Implementación |
|-----------|----------------|
| **Interfaces explícitas** | Cada submódulo expone `Protocol` (typing) o ABC |
| **Inyección de dependencias** | `DispatcherSkill` recibe `RouteEngine`, `TelegramBot`, `GPSTracker` por constructor |
| **Feature flags** | `settings.dispatch_enable_osrm`, `dispatch_enable_fleetbase` |
| **Plugin architecture** | `RouteEngine` es swappable (Haversine → OSRM → Fleetbase) |
| **Event-driven** | `DispatcherSkill` emite eventos → `EventBus` → Sheets Sync, Financial Shield, Valentina |
| **Config-driven** | Todo configurable vía `core/config.py` + `.env` (sin hardcode) |

---

## 📋 PLAN DE IMPLEMENTACIÓN — SPRINTS

### **SPRINT 1 — CORE CRÍTICO** (Semana 1) — *Desbloquea todo lo demás*

| Tarea | Archivo(s) | Descripción | Done Criteria |
|-------|------------|-------------|---------------|
| **1.1** | `skills/dispatcher_skill.py` | Skill principal `DispatcherSkill(BaseSkill)` con actions: `compute_route`, `notify_driver`, `update_delivery`, `record_gps`, `get_bottle_inventory` | `workload_router.execute(trigger="dispatch_request", action="compute_route")` retorna `VRPResult` |
| **1.2** | `core/workload_router.py` | Registrar routes: `dispatch_request`, `dispatch_route_compute`, `dispatch_delivery_update`, `dispatch_gps_track`, `dispatch_bottle_inventory` | `router.resolve("dispatch_request") == Route.DISPATCH_SKILL` |
| **1.3** | `api/routes/dispatch.py` | FastAPI endpoints: `POST /dispatch/route/compute`, `POST /dispatch/delivery/update`, `POST /dispatch/gps`, `GET /dispatch/vehicles/status`, `GET /dispatch/bottles/inventory` | `curl -X POST /dispatch/route/compute` retorna `VRPResult` |
| **1.4** | `api/bridge.py` | Integrar `send_delivery_to_chofer` en `_send_to_dispatch_queue` (ya existe en dispatcher.py, falta llamarlo) | Pedido confirmado → aparece en Telegram chofer |
| **1.5** | `api/routes/dispatch.py` | Webhook `POST /dispatch/telegram/webhook` para bot operadores | Bot responde a check-in / entregas |
| **1.6** | `core/config.py` | Variables: `DISPATCH_BOT_TOKEN`, `DISPATCH_DB_PATH`, `DISPATCH_OPERATION_CENTER_LAT/LON/RADIUS`, `DISPATCH_MAX_INSERTION_DEVIATION_MIN`, `DISPATCH_GPS_INTERVAL_SECONDS`, `DISPATCH_BOTTLE_RETURN_HOURS_RESIDENTIAL/ENTERPRISE` | `settings.dispatch_bot_token` leído desde `.env` |

---

### **SPRINT 2 — COMPONENTES FALTANTES** (Semana 2)

| Tarea | Archivo(s) | Descripción | Done Criteria |
|-------|------------|-------------|---------------|
| **2.1** | `skills/dispatch/telegram_bot.py` | Refactor de `skills/dispatcher.py` → clase `DispatcherTelegramBot` con flujo: registro, check-in, botones [Llegué/Entregado/No responde], GPS location, geofencing | Operadores registrados reciben rutas y reportan entregas |
| **2.2** | `skills/dispatch/seed_data.py` | Poblar BD: 5 zonas Maracaibo, 2 vehículos (Triciclo 1/2), operadores YORDANIS/EVERT, 16 clientes piloto | `sqlite3 dispatch.db "SELECT * FROM zones"` → 5 filas |
| **2.3** | `skills/dispatch/gps_tracker.py` | Procesar GPS de Tasker (cada 5 min) + Telegram check-in. Almacena en `gps_tracks`. Geofencing: perímetro 13km + 5 zonas. Alerta si sale. | `curl POST /dispatch/gps` → punto guardado + alerta si fuera |
| **2.4** | `skills/dispatch/seed_data.py` | Poblar 16 clientes piloto (B2B + multifamiliares semana 1-2, unifamiliares semana 3). Campos: phone, phone_hash, name, address, lat/lng, client_type, visit_frequency, bottle_exchange_model=1, bottle_return_hours=24/36 | 16 clientes con lat/lng reales en `clients` |
| **2.5** | `skills/dispatch/__init__.py` | Exportar: `DispatcherSkill`, `DispatcherTelegramBot`, `RouteEngine`, `GPSTracker` | `from skills.dispatch import DispatcherSkill` funciona |

---

### **SPRINT 3 — INTEGRACIÓN SWAP + E2E** (Semana 3)

| Tarea | Archivo(s) | Descripción | Done Criteria |
|-------|------------|-------------|---------------|
| **3.1** | `skills/dispatch/bottle_tracker.py` | **NUEVO** - Tracking individual de 165 botellones loaner: estados `available | in_transit_full | with_client | in_transit_empty | maintenance | retired`. Tracking por `bottle_code` (H2O-001 a H2O-165). Endpoints: `assign_to_client`, `return_from_client`, `send_to_wash`, `mark_maintenance`, `get_inventory`. | `GET /dispatch/bottles/inventory` → 165 botellones con estado |
| **3.2** | `api/bridge.py` | Integración Swap: al confirmar entrega (`delivered`), llamar `bottle_tracker.assign_to_client(bottle_code, client_id)` + `bottle_tracker.return_from_client(old_bottle_code)`. Al recibir vacío en planta → `send_to_wash()`. | Botellón lleno entregado → estado `with_client`; vacío recogido → `in_transit_empty` |
| **3.3** | `skills/dispatch/sheets_sync.py` | Sincronización Google Sheets: `Mapa_Calor` (cada GPS → sector, calle, pasadas), `Feedback_Clientes` (feedback_score al completar entrega), `Botellas_Control` (inventario loaner). Async fire-and-forget como `google_sheets.py` actual. | Datos fluyen a Sheets cada entrega/GPS |
| **3.4** | `tests/integration/test_dispatch_flow.py` | **Test E2E completo**: Pedido WhatsApp → Valentina confirma → Bridge → Dispatch Queue → Route Engine → Bot Chofer → Check-in → GPS → Entregado → Botellón loaner tracking → Sheets Sync → Financial Shield. | `pytest tests/integration/test_dispatch_flow.py -v` → PASS |
| **3.5** | `skills/dispatch/dynamic_inserter.py` | Inserción dinámica (FASE 2.2): nuevo pedido on-demand → evalúa capacidad + distancia + desvío <10 min → inserta en ruta óptima → notifica chofer. | Pedido on-demand insertado en ruta activa |

---

### **SPRINT 4 — OBSERVABILIDAD + HARDENING** (Semana 4)

| Tarea | Archivo(s) | Descripción |
|-------|------------|-------------|
| **4.1** | `skills/dispatch/dashboard.py` | Dashboard FastAPI + Leaflet.js: mapa tiempo real (triciclos, entregas, GPS heatmap), métricas: entregas/hora, km/entrega, botellones/turno, alertas geofence |
| **4.2** | `skills/dispatch/alerts.py` | Alertas: geofence exit, botellón overdue (36h residencial / 24h empresarial), chofer no check-in, capacidad excedida, botellón perdido. Vía Telegram (Líder + Chofer) |
| **4.3** | `tests/unit/test_*.py` | Tests unitarios: `test_route_engine.py`, `test_haversine.py`, `test_geofence.py`, `test_bottle_tracker.py`, `test_dynamic_inserter.py` |
| **4.6** | `docs/02-arquitectura/DISPATCHER_SWAP_ARCHITECTURE.md` | Documentación final: arquitectura, APIs, flujos, configuración, troubleshooting |

---

## 🔧 INTEGRACIÓN CON FINANCIAL SHIELD v3.0 + VALENTINA

### Flujo Unificado: Pedido → Swap → Cobro

```
WhatsApp Cliente
      │
      ▼
Valentina (bridge.py) ──confirma pedido──► orders table (status=registrado)
      │                                        │
      │          _send_to_dispatch_queue()    │
      ▼                                        ▼
DispatcherSkill.compute_route()         Financial Shield
   │                                         │
   ▼                                         ▼
Route Engine (OR-Tools)              fs_pedidos creado
   │                                         │
   ▼                                         ▼
Bot Chofer recibe ruta              fs_pagos + fs_cuentas_cobrar
   │                                         │
   ▼                                         ▼
Check-in Llegué + GPS              Cobranzas automáticas
   │                                         │
   ▼                                         ▼
Entregado + Botellón vacío          Cobro confirmado
   │                                         │
   ▼                                         ▼
Bottle Tracker:                    Financial Shield:
  assign_to_client()                  add_pago_and_update_pedido()
  return_from_client()                update estado_pago
  send_to_wash()                      conciliación automática
```

### Puntos de Integración Críticos

| Punto | Componente A | Componente B | Contrato |
|-------|--------------|--------------|----------|
| **Pedido confirmado** | `bridge.py` | `DispatcherSkill` | `dispatch_request` trigger → `compute_route` |
| **Entrega completada** | `DispatcherBot` | `BottleTracker` + `FinancialShield` | `delivered` → `assign_to_client` + `add_pago_and_update_pedido` |
| **Botellón vacío en planta** | `DispatcherBot` | `BottleTracker` | `return_from_client` → `send_to_wash` |
| **Cobro validado** | `FinancialShield` | `DispatcherSkill` | `verified` → libera capacidad vehículo |
| **Reporte diario 7am** | `AnalyticsSkill` | `FinancialShield` + `DispatcherSkill` | Métricas unificadas |

---

## 📊 MODELO DE DATOS — EXTENSIONES SWAP

### Tabla `bottles` (ya existe en `dispatch.db`)
```sql
-- Estados: available | in_transit_full | with_client | in_transit_empty | maintenance | retired
-- Tracking: bottle_code (H2O-001..H2O-165), client_id, dispatch_delivery_id, expected_return_at
```

### Nuevas Tablas Requeridas

```sql
-- Historial de movimientos de botellón (auditoría completa)
CREATE TABLE IF NOT EXISTS bottle_movements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bottle_code TEXT NOT NULL,
    from_status TEXT, to_status TEXT,
    from_client_id INTEGER, to_client_id INTEGER,
    delivery_id INTEGER,
    location_lat REAL, location_lng REAL,
    performed_by TEXT, -- 'operator' | 'plant' | 'system'
    notes TEXT,
    created_at REAL NOT NULL DEFAULT (strftime('%s','now')),
    FOREIGN KEY (bottle_code) REFERENCES bottles(bottle_code)
);

-- Alertas de botellones (overdue, maintenance, lost)
CREATE TABLE IF NOT EXISTS bottle_alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bottle_code TEXT NOT NULL,
    alert_type TEXT NOT NULL, -- 'overdue_return' | 'maintenance_due' | 'lost' | 'damaged'
    severity TEXT DEFAULT 'warning', -- 'info' | 'warning' | 'critical'
    acknowledged INTEGER DEFAULT 0,
    acknowledged_by TEXT,
    acknowledged_at REAL,
    created_at REAL NOT NULL DEFAULT (strftime('%s','now')),
    resolved_at REAL,
    FOREIGN KEY (bottle_code) REFERENCES bottles(bottle_code)
);
```

---

## 📈 MÉTRICAS DE ÉXITO (KPIs) — ALINEADOS CON SWAP

| Métrica | Baseline (Hoy) | Meta Fase 2.4 | Meta Swap Completo |
|---------|----------------|---------------|---------------------|
| **Clientes con GPS registrado** | 0% | 80% (13/16 piloto) | 100% |
| **Puntos GPS/turno/operador** | 0 | 30 (check-in) → 200 (Tasker) | 200+ |
| **Botellones con tracking individual** | 0 | 165 (100% loaner) | 165+ |
| **Botellones overdue (>36h/24h)** | Desconocido | <5% | <1% |
| **Viajes duplicados a misma zona** | Alto | -50% | <5% |
| **Tiempo promedio por entrega** | Desconocido | Baseline registrado | -20% vs baseline |
| **Clientes con botellón overdue >36h** | Desconocido | 0 (alertas automáticas) | 0 |
| **Cobertura Mapa_Calor** | 0 zonas | 3/5 zonas | 5/5 zonas |
| **Tasa migración Swap** | 0% | 100% (16 piloto) | 100% |
| **Reclamos sanitarios mensuales** | >0 | 0 (Mes 2) | 0 |

---

## ⚙️ CONFIGURACIÓN CENTRALIZADA (`core/config.py`)

```python
# ── Dispatcher / Swap ──
dispatch_bot_token: str = ""                           # Token Bot Telegram operadores
dispatch_db_path: str = "/mnt/ssd_trabajo/hermes-agent/data/dispatch.db"
dispatch_operation_center_lat: float = 10.6447
dispatch_operation_center_lon: float = -71.6101
dispatch_operation_radius_km: float = 13.0

# Ruteo
dispatch_max_full_bottles: int = 30
dispatch_max_empty_bottles: int = 70
dispatch_avg_speed_kmh: float = 20.0
dispatch_time_per_delivery_min: int = 8
dispatch_max_insertion_deviation_min: int = 10
dispatch_max_insertion_distance_km: float = 2.0

# Swap
dispatch_bottle_return_hours_residential: int = 36
dispatch_bottle_return_hours_enterprise: int = 24
dispatch_total_loaner_bottles: int = 165
dispatch_bottle_code_prefix: str = "H2O-"

# GPS / Tasker
dispatch_gps_interval_seconds: int = 300
dispatch_geofence_alert_cooldown_seconds: int = 300
dispatch_tasker_battery_threshold: int = 20

# Ruteo
dispatch_route_compute_minutes_before_shift: int = 15
dispatch_max_insertion_deviation_min: int = 10
dispatch_max_insertion_distance_km: float = 2.0

# OSRM (Fase 2)
dispatch_osrm_enabled: bool = False
dispatch_osrm_url: str = "http://localhost:5000"

# Fleetbase (Fase 3 eval)
dispatch_fleetbase_enabled: bool = False
dispatch_fleetbase_url: str = ""
```

---

## 🚀 PRIMER PASO INMEDIATO — SPRINT 1.1

```bash
# 1. Crear DispatcherSkill
cat > /mnt/ssd_trabajo/hermes-agent/skills/dispatcher_skill.py << 'EOF'
# (código completo - ver siguiente paso)
EOF

# 2. Registrar en WorkloadRouter
# Editar core/workload_router.py:
#   - Agregar Route.DISPATCH_SKILL = "skill:dispatcher"
#   - Agregar triggers a ROUTE_TABLE
#   - Importar e instanciar en execute()

# 3. Verificar
cd /mnt/ssd_trabajo/hermes-agent && PYTHONPATH=. python -c "
from core.workload_router import get_router
r = get_router()
print(r.resolve('dispatch_request'))
"
```

---

## 📋 CHECKLIST DEFINITIVO — FASE 2.4 + SWAP

| Fase | Componente | Archivo Principal | Estado | Prioridad |
|------|------------|-------------------|--------|-----------|
| **1.1** | DispatcherSkill | `skills/dispatcher_skill.py` | ❌ | 🔴 Crítico |
| **1.2** | WorkloadRouter | `core/workload_router.py` | ❌ | 🔴 Crítico |
| **1.3** | FastAPI Endpoints | `api/routes/dispatch.py` | ❌ | 🔴 Crítico |
| **1.4** | Bridge Integration | `api/bridge.py` | ❌ | 🔴 Crítico |
| **1.5** | Webhook TG Choferes | `api/routes/dispatch.py` | ❌ | 🔴 Crítico |
| **1.6** | Config Centralizada | `core/config.py` | ❌ | 🔴 Crítico |
| **2.1** | Telegram Bot Operadores | `skills/dispatch/telegram_bot.py` | ❌ | 🟠 Alta |
| **2.2** | Seed Data | `skills/dispatch/seed_data.py` | ❌ | 🟠 Alta |
| **2.3** | GPS Tracker | `skills/dispatch/gps_tracker.py` | ❌ | 🟠 Alta |
| **2.5** | Package Init | `skills/dispatch/__init__.py` | ❌ | 🟠 Alta |
| **3.1** | **Bottle Tracker (SWAP)** | `skills/dispatch/bottle_tracker.py` | ❌ | 🔴 Crítico Swap |
| **3.2** | Bridge + Swap | `api/bridge.py` | ❌ | 🔴 Crítico Swap |
| **3.3** | Sheets Sync | `skills/dispatch/sheets_sync.py` | ❌ | 🟠 Alta |
| **3.4** | **Test E2E** | `tests/integration/test_dispatch_flow.py` | ❌ | 🔴 Crítico |
| **3.5** | Dynamic Inserter | `skills/dispatch/dynamic_inserter.py` | ❌ | 🟡 Media |
| **4.1** | Dashboard Web | `skills/dispatch/dashboard.py` | ❌ | 🟢 Baja |
| **4.2** | Alertas | `skills/dispatch/alerts.py` | ❌ | 🟢 Baja |
| **4.3** | Tests Unitarios | `tests/unit/test_*.py` | ❌ | 🟠 Alta |
| **4.6** | Documentación | `docs/02-arquitectura/DISPATCHER_SWAP_ARCHITECTURE.md` | ❌ | 🟢 Baja |

---

## 🚀 PRÓXIMO PASO INMEDIATO

> **¿Arranco con la creación de `skills/dispatcher_skill.py` + registro en `core/workload_router.py`?** 

Es el **primer eslabón** que desbloquea todo lo demás. Una vez registrado en el `WorkloadRouter`, el dispatcher pasa a ser un ciudadano de primera clase en el ecosistema Hermes. 💧