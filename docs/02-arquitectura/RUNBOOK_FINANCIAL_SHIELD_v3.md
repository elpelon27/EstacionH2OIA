# 📋 RUNBOOK v3.0 — Guía Operacional Financial Shield

**Última actualización**: 2026-07-27 (Día 30 — Financial Shield v3.0 deployado)

---

## 🚀 Deploy Financial Shield v3.0

```bash
# 1. Actualizar código (ya hecho)
cd /mnt/ssd_trabajo/hermes-agent
git pull origin main

# 2. Ejecutar migración BD v3.0 (idempotente)
python3 -c "
from src.financial.database import init_database_v3
init_database_v3()
print('Migración v3.0 completada')
"

# 3. Verificar migración
sqlite3 data/conversations.db "
SELECT sql FROM sqlite_master 
WHERE type='trigger' AND name LIKE 'trg_audit%';
"
# Debe mostrar 4 triggers: fs_pedidos_insert, fs_pedidos_update, fs_pagos_insert, fs_cuentas_cobrar_update

sqlite3 data/conversations.db "PRAGMA table_info(fs_pedidos);" | grep -E "monto_pagado_eur|tasa_eur_ves_deuda"
sqlite3 data/conversations.db "PRAGMA table_info(fs_pagos);" | grep -E "tasa_eur_ves_pago|comprobante_phash|ux_fs_pagos_ref_metodo"

# 4. Reiniciar bridge (para activar recovery scan)
sudo systemctl restart valentina-bridge.service

# 5. Verificar logs
sudo journalctl -u valentina-bridge -n 50 | grep -i "financial shield\|recovery"
```

---

## 📊 Operaciones Financial Shield v3.0

### Ver estado de pagos
```bash
# Pedidos pendientes de pago
sqlite3 data/conversations.db "
SELECT 
    p.id, p.pedido_id, p.cliente_nombre, p.cliente_telefono,
    p.monto_total_eur, p.monto_pagado_eur,
    p.tasa_eur_ves_deuda, p.estado_pago, p.estado_entrega,
    p.recordatorios_enviados, p.ultimo_recordatorio_at
FROM fs_pedidos p
WHERE p.estado_pago IN ('pendiente', 'verificando', 'parcial')
AND p.escalo_humano = 0
ORDER BY p.entrega_confirmada_at ASC;
"

# Pagos verificados hoy
sqlite3 data/conversations.db "
SELECT 
    pg.id, pg.fs_pedido_id, pg.cliente_nombre, pg.monto_eur,
    pg.metodo_pago, pg.referencia, pg.verificacion_metodo,
    pg.tasa_eur_ves_pago, pg.verificado_at
FROM fs_pagos pg
WHERE DATE(pg.verificado_at) = DATE('now', 'localtime')
ORDER BY pg.verificado_at DESC;
"
```

### Ver auditoría forense
```bash
# Cambios recientes en fs_pedidos
sqlite3 data/conversations.db "
SELECT 
    al.timestamp, al.tabla, al.registro_id, al.accion,
    al.estado_anterior, al.estado_nuevo, al.modificado_por
FROM fs_audit_log al
WHERE al.tabla = 'fs_pedidos'
ORDER BY al.timestamp DESC
LIMIT 20;
"

# Auditoría completa de un pedido
sqlite3 data/conversations.db "
SELECT 
    al.timestamp, al.accion, al.estado_anterior, al.estado_nuevo
FROM fs_audit_log al
WHERE al.tabla = 'fs_pedidos' AND al.registro_id = <FS_PEDIDO_ID>
ORDER BY al.timestamp;
"
```

### Ejecutar ciclo de recordatorios manual
```bash
python3 -c "
import asyncio
from src.financial.verificacion import run_reminder_cycle
result = asyncio.run(run_reminder_cycle())
print('Resultado:', result)
"
```

### Recovery scan manual (si bridge reinició sin recovery)
```bash
python3 -c "
import asyncio
from src.financial.verificacion import recovery_scan_stuck_payments
count = asyncio.run(recovery_scan_stuck_payments())
print(f'Pedidos reanudados: {count}')
"
```

---

## 🔄 Ciclo de Pagos v3.0

### Flujo Contado (normal)
1. **Pedido creado** → `fs_pedidos.estado_pago='pendiente'`, `tasa_eur_ves_deuda` congelada
2. **Entrega confirmada** (Dispatcher) → `estado_pago='verificando'`, `estado_entrega='confirmado'`
3. **Líder verifica pago** (Telegram `/pagado`) → Transacción atómica:
   - INSERT en `fs_pagos` con `tasa_eur_ves_pago` (tasa actual)
   - UPDATE `fs_pedidos.monto_pagado_eur += monto_eur`
   - Si `monto_pagado_eur >= monto_total_eur` → `estado_pago='pagado'`
   - Si `0 < monto_pagado_eur < monto_total_eur` → `estado_pago='parcial'`

### Flujo con Pagos Parciales
```
PAGADO TOTAL (€10)
   ↑
PARCIAL (€6)  ← 2do pago
   ↑
PARCIAL (€4)  ← 1er pago
   ↑
VERIFICANDO (€0)  ← entrega confirmada
   ↑
PENDIENTE       ← pedido creado
```

### Anti-Fraude Real
- **Constraint BD**: `UNIQUE(referencia, metodo_pago)` en `fs_pagos`
- **Misma ref + mismo método** = RECHAZADO
- **Misma ref + distinto método** = PERMITIDO (ej: pagomovil vs efectivo_eur)
- **pHash comprobante** (Fase 6): `comprobante_phash` para detectar imágenes editadas

---

## ⚠️ Troubleshooting Financial Shield

### "database is locked" en tests/concurrencia
```bash
# Verificar que WAL está activo
sqlite3 data/conversations.db "PRAGMA journal_mode;"
# Debe devolver: wal

# Verificar busy_timeout
sqlite3 data/conversations.db "PRAGMA busy_timeout;"
# Debe devolver: 5000
```

### Pedido no avanza a 'verificando' tras entrega
```bash
# Verificar que Dispatcher llama confirmar_entrega()
sqlite3 data/conversations.db "
SELECT id, estado_entrega, estado_pago, entrega_confirmada_at
FROM fs_pedidos WHERE pedido_id = <PEDIDO_ID>;
"
# estado_entrega debe ser 'confirmado', estado_pago 'verificando'
```

### Tasa de cambio no actualizada
```bash
# Verificar última tasa
sqlite3 data/conversations.db "
SELECT par, tasa, fuente, registrado_at
FROM fs_tasas_cambio
WHERE par = 'EUR/VES'
ORDER BY registrado_at DESC LIMIT 5;
"
# Forzar actualización manual
python3 -c "
from src.financial.currency import get_eur_ves_rate
import asyncio
print(asyncio.run(get_eur_ves_rate()))
"
```

### Recovery scan no detectó pedidos atascados
```bash
# Verificar criterios de detección
sqlite3 data/conversations.db "
SELECT id, pedido_id, cliente_nombre, estado_pago, recordatorios_enviados,
       ultimo_recordatorio_at, escalo_humano
FROM fs_pedidos
WHERE estado_pago IN ('verificando', 'parcial')
AND escalo_humano = 0
AND recordatorios_enviados < 3;
"
# Si hay resultados → recovery debería haberlos detectado
```

---

## 📱 Comandos Telegram (Líder)

| Comando | Acción |
|---------|--------|
| `/pagado <pedido_id> <monto_eur> [referencia]` | Verificar pago manual |
| `/pedidos_pendientes` | Lista pedidos en verificación |
| `/reporte` | Reporte diario (ejecuta run_fs_reporte) |
| `/cobranzas` | Resumen cuentas por cobrar |
| `/recovery` | Ejecutar recovery scan manual |
| `/auditoria <fs_pedido_id>` | Ver log forense de un pedido |

---

## 📈 Métricas Clave (Prometheus)

```bash
curl -s http://localhost:8000/metrics | grep -E "fs_pedidos_|fs_pagos_|verificacion_"
```

- `fs_pedidos_estado_pago_total{estado="pendiente|verificando|parcial|pagado|moroso"}`
- `fs_pagos_verificados_total{metodo="pagomovil|efectivo_eur|efectivo_ves", verificacion="manual|ocr|api"}`
- `verificacion_recordatorios_enviados_total`
- `verificacion_escalados_humano_total`
- `financial_shield_recovery_pedidos_reanudados`

---

## 🆘 Kill Switch Financial Shield

```bash
# Solo Financial Shield (no afecta Valentina)
touch /tmp/financial_shield.kill

# Verificar
ls -la /tmp/*.kill

# Reactivar
rm /tmp/financial_shield.kill
```

---

## 📚 Referencias

- **Arquitectura v3.0**: `docs/02-arquitectura/FINANCIAL_SHIELD_v3_ARQUITECTURA_DEFINITIVA.md`
- **Tests**: `tests/unit/financial/`, `tests/integration/financial/`
- **Repo**: https://github.com/elpelon27/EstacionH2OIA
- **WhatsApp Valentina**: +58 422-711-9156
- **Líder**: Luis Martinez (@elpelon27) — +58 412-256-0720