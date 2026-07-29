# 📋 PLAN DE TRABAJO MAÑANA — PRIORIDADES ORDENADAS
**Fecha**: 2026-07-29 | **Sesión**: Día 32 | **Estado**: SPRINT 1 completado, SPRINT 2 inicia

---

## 🎯 OBJETIVO MAÑANA: SPRINT 2 — Componentes Faltantes del Dispatcher

### **ORDEN DE PRIORIDADES**

| # | Tarea | Archivo | Complejidad | Tiempo | Dependencia |
|---|-------|---------|-------------|--------|-------------|
| **1** | **Telegram Bot Operadores** (refactor) | `skills/dispatch/telegram_bot.py` | 🔴 Alta | 1.5-2h | Base para todo |
| **2** | **Seed Data** (zonas, vehículos, clientes) | `skills/dispatch/seed_data.py` | 🟠 Media | 0.5-1h | Requerido por bot + route engine |
| **3** | **GPS Tracker** (Tasker + Telegram + Geofence) | `skills/dispatch/gps_tracker.py` | 🔴 Alta | 1.5-2h | Requiere seed data |
| **4** | **Package Init** | `skills/dispatch/__init__.py` | 🟢 Baja | 0.25h | Al final |
| **5** | **Tests Unitarios básicos** | `tests/unit/test_dispatch_*.py` | 🟠 Media | 1h | Paralelizable |

---

## 📦 ESTADO ACTUAL (Baseline Mañana)

### ✅ **COMPLETADO HOY (SPRINT 1)**
- `skills/dispatcher_skill.py` — Skill principal BaseSkill con 11 actions
- `core/workload_router.py` — Route.DISPATCH_SKILL + 5 triggers registrados
- `api/routes/dispatch.py` — 9 endpoints FastAPI (`/dispatch/*`)
- `core/config.py` — 20+ variables dispatcher/swap
- `api/bridge.py` — Integración `_send_to_dispatch_queue` → `/dispatch/notify-driver`
- `api/main.py` — Router dispatch registrado
- Tests: **126 passed, 14 skipped**

### 🗂️ **ARCHIVOS MODIFICADOS HOY**
```
skills/dispatcher_skill.py          (nuevo)
core/workload_router.py             (modificado)
api/routes/dispatch.py              (nuevo)
core/config.py                      (modificado)
api/bridge.py                       (modificado)
api/main.py                         (modificado)
docs/02-arquitectura/PLAN_UNIFICADO_F24_SWAP.md (nuevo)
```

---

## 🔄 PRIMER PASO MAÑANA — VERIFICACIÓN RÁPIDA

```bash
cd /mnt/ssd_trabajo/hermes-agent
PYTHONPATH=. venv/bin/python -c "
from core.workload_router import get_router, Route
r = get_router()
assert r.resolve('dispatch_request') == Route.DISPATCH_SKILL
print('✅ WorkloadRouter OK')

from skills.dispatcher_skill import get_dispatcher_skill
s = get_dispatcher_skill()
print(f'✅ DispatcherSkill: {s.name}')

from api.main import app
routes = [r.path for r in app.routes if 'dispatch' in r.path]
print(f'✅ FastAPI routes: {len(routes)} endpoints')
"
```

---

## 📝 NOTAS PARA MAÑANA

1. **Telegram Bot Operadores**: Refactor `skills/dispatcher.py` (800 líneas) → clase `DispatcherTelegramBot` con:
   - Registro choferes (`/start` → botones vehículo)
   - Check-in 8am (botones Sí/No)
   - Flujo entregas: `/siguiente` → botones [Llegué/Entregado/No responde]
   - GPS location handler
   - Geofencing alerta
   - Webhook receiver para `/dispatch/telegram/webhook`

2. **Seed Data**: Poblar `dispatch.db` con:
   - 5 zonas Maracaibo (Bella Vista, Las Delicias, La Limpia, Centro, Tierra Negra)
   - 2 vehículos (Triciclo 1/2, shift 'both')
   - 16 clientes piloto (B2B + multifamiliares semana 1-2)

3. **GPS Tracker**: Procesar Tasker (cada 5 min) + Telegram check-in + geofencing 13km + 5 zonas

---

## 💾 COMMIT DE HOY
`ccc4b4c9` — "feat: DispatcherSkill + WorkloadRouter integration (SPRINT 1.1-1.2)"
`6a99896`  — "fix: mypy clean financial/database.py (21 errores → 0)"
`b6d02dc`  — "fix: lint cleanup R4Banco + banking/ + banking_webhooks + analytics_skill"
`2ff0bdf`  — "feat: R4Banco integración completa + FASE 2.3 Analytics Skill + mypy dispatcher"

---

**Listo para arrancar mañana con SPRINT 2.1**. 💧