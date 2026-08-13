# Informe de Migración v3.1 — Estación H2O Maracaibo

**Fecha**: 2026-08-12
**Ejecutado por**: Prometeo (Hermes Agent)
**Estado**: ✅ COMPLETADO CON ÉXITO

---

## Resumen de Cambios

### 1. Unificación de `phone_hash` (Single Source of Truth)
**Archivo nuevo**: `/mnt/ssd_trabajo/hermes-agent/core/crypto.py`

- Función `hash_phone(phone: str) -> str` centralizada usando `LOG_SALT` validado
- `set_log_salt()` / `get_log_salt()` para inyección única al startup
- Detección legacy: `is_legacy_hash()` (16 chars) vs `is_current_hash()` (32 chars)
- Compatibilidad: respeta `BRIDGE_ALLOW_INSECURE_SALT` para tests/dev

**Archivos actualizados**:
- `api/bridge.py` → usa `_hash_phone` de core.crypto
- `skills/dispatch/consumer.py` → usa `_hash_phone` de core.crypto  
- `skills/dispatch/seed_data.py` → usa `_hash_phone` de core.crypto

**Verificación**: Los tres módulos producen **hashes idénticos** para el mismo teléfono.

---

### 2. Migración conversations.db v3.1
**Script**: `/mnt/ssd_trabajo/hermes-agent/scripts/migrate_v31.py`
**Backup**: `/mnt/ssd_trabajo/backups/conversations_pre_v31_20260812_170820.db`

#### Tabla `fs_pedidos` — Correcciones aplicadas:
| Columna | Antes | Después |
|---------|-------|---------|
| `monto_total_ves` | ❌ No existía | ✅ REAL NULL |
| `tasa_usd_ves_ref` | ❌ No existía | ✅ REAL NULL |
| `monto_pagado_eur` | REAL sin DEFAULT | ✅ REAL DEFAULT 0 |
| `tasa_eur_ves_deuda` | REAL sin NOT NULL | ✅ REAL NOT NULL DEFAULT 0 |
| `pedido_id` | Solo NOT NULL | ✅ NOT NULL **UNIQUE** (índice `ux_fs_pedidos_pedido_id`) |

#### Tabla `fs_pagos` — Correcciones aplicadas:
- ❌ Eliminada columna duplicada `tasa_eur_ves` (legacy)
- ✅ `tasa_eur_ves_pago` ahora NOT NULL (única tasa de pago)
- ✅ Backfill: `tasa_eur_ves_pago = COALESCE(tasa_eur_ves_pago, tasa_eur_ves)` migrado

#### Triggers de Auditoría — Completados:
- ✅ `trg_audit_fs_pedidos_insert` (recreado tras DROP TABLE)
- ✅ `trg_audit_fs_pedidos_update` (recreado tras DROP TABLE)
- ✅ `trg_audit_fs_pagos_update` **NUEVO** (faltaba en producción)
- ✅ `trg_audit_fs_cuentas_cobrar_update` (ya existía, intacto)

#### Backfills ejecutados:
1. `tasa_eur_ves_deuda = tasa_eur_ves` donde era 0/NULL → **23 filas actualizadas**
2. `monto_pagado_eur = SUM(fs_pagos.monto_eur)` por pedido verificado → **0 filas NULL restantes**
3. Sincronización `estado_pago` según `monto_pagado_eur` → **completado**

---

### 3. Limpieza dispatch.db
- ✅ Tabla huérfana `dispatch_notifications` eliminada (`DROP TABLE`)
- Esquema dispatch.db intacto: 11 tablas operativas (zones, vehicles, clients, bottles, deliveries, dispatch_sessions, gps_tracks, geofence_events, route_history, bottle_movements, bottle_alerts)

---

### 4. Seed Data regenerado
- Ejecutado `python -m skills.dispatch.seed_data` con nuevo `hash_phone`
- 5 zonas, 2 vehículos, **19 clientes** (16 piloto + 3 previos), 165 botellones
- **Clientes nuevos usan hash de 32 chars** (formato actual)
- **Clientes legacy mantienen hash de 16 chars** (detectables con `is_legacy_hash()`)

---

## Verificaciones Post-Migración

```sql
-- conversations.db
fs_pedidos: 23 filas, 0 NULL en monto_pagado_eur, 0 NULL en tasa_eur_ves_deuda
fs_pagos: sin columna tasa_eur_ves duplicada, tasa_eur_ves_pago NOT NULL
Triggers: 4/4 audit triggers presentes
Índices: ux_fs_pedidos_pedido_id UNIQUE creado

-- dispatch.db  
clients: hashes mezclados (legacy 16 chars + nuevos 32 chars) — ambos válidos
dispatch_notifications: ELIMINADA

-- Core crypto
hash_phone() produce 32 chars determinísticos
bridge/consumer/seed_data: TODOS usan la misma función → hashes IDÉNTICOS
```

---

## Archivos Modificados/Creados

| Archivo | Tipo | Descripción |
|---------|------|-------------|
| `core/crypto.py` | **NUEVO** | Módulo criptográfico centralizado |
| `api/bridge.py` | MODIFICADO | Importa y usa `core.crypto.hash_phone` |
| `skills/dispatch/consumer.py` | MODIFICADO | Importa y usa `core.crypto.hash_phone` |
| `skills/dispatch/seed_data.py` | MODIFICADO | Importa y usa `core.crypto.hash_phone` |
| `scripts/migrate_v31.py` | **NUEVO** | Script de migración idempotente con backup |
| `scripts/migrate_v31.py` | EJECUTADO | Migración aplicada exitosamente |

---

## Puertas Abiertas para Futuras Mejoras

1. **Migración legacy de phone_hash en dispatch.db**
   - Script futuro: detectar `is_legacy_hash()` y re-hashear con `hash_phone()`
   - Requiere coordinación: bridge + consumer + seed_data deben estar alineados (ya lo están)

2. **Tabla `bottles` — FASE 2.4 Swap**
   - Esquema listo (165 botellones insertados)
   - Falta lógica de asignación/devolución en consumer/bridge
   - Documentado en `PLAN_UNIFICADO_F24_SWAP.md`

3. **Índices compuestos para consultas frecuentes**
   - `fs_pedidos(cliente_telefono, estado_pago)` para cobranzas
   - `fs_pagos(cliente_telefono, verificado)` para conciliación

4. **Particionado temporal fs_audit_log**
   - Tabla crecerá linealmente; considerar archivado mensual

---

## Rollback (si necesario)

```bash
# Restaurar conversations.db
cp /mnt/ssd_trabajo/backups/conversations_pre_v31_20260812_170820.db \
   /mnt/ssd_trabajo/hermes-agent/data/conversations.db

# dispatch.db no tuvo cambios destructivos (solo DROP tabla huérfana)
# Seed data es idempotente (INSERT OR IGNORE)
```

---

**Firmado**: 💧 Prometeo — Hermes Agent  
**Líder**: Luis Martinez (@elpelon27) — Estación H2O Maracaibo