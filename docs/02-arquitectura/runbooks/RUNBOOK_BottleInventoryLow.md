# 📦 RUNBOOK: BottleInventoryLow
**Alert:** `BottleInventoryLow` | **Severity:** WARNING | **Response Time:** < 10 min

---

## 📋 DESCRIPCIÓN
Botellones disponibles en planta < 20 (stock de seguridad).

**Métrica:** `bottle_tracker_available < 20`

---

## 🔍 DIAGNÓSTICO (2-3 min)

```bash
# 1. Ver inventario actual
sqlite3 /mnt/ssd_trabajo/hermes-agent/data/dispatch.db "
SELECT status, COUNT(*) as count
FROM bottles
GROUP BY status;
"

# 2. Ver botellas overdue
sqlite3 /mnt/ssd_trabajo/hermes-agent/data/dispatch.db "
SELECT COUNT(*) as overdue
FROM bottles
WHERE status = 'with_client' 
  AND datetime(expected_return_at) < datetime('now');
"

# 3. Dashboard Grafana: SWAP - Bottle Inventory Tracking
```

---

## 🎯 ACCIONES

### A. Activar stock de seguridad (15-20 botellas reservadas)
```bash
# Verificar si hay botellas en 'maintenance' que puedan liberarse
sqlite3 /mnt/ssd_trabajo/hermes-agent/data/dispatch.db "
SELECT bottle_code, status
FROM bottles
WHERE status = 'maintenance'
LIMIT 5;
"

# Cambiar a available si están listas
sqlite3 /mnt/ssd_trabajo/hermes-agent/data/dispatch.db "
UPDATE bottles SET status = 'available', updated_at = datetime('now')
WHERE status = 'maintenance' AND bottle_code IN ('H2O-XXX', 'H2O-YYY');
"
```

### B. Acelerar recogida de vacíos (choferes)
- Enviar alerta a choferes vía Telegram: "⚠️ STOCK BAJO - Priorizar recogida de vacíos hoy"
- Verificar que choferes marquen "Entregado" y recojan vacíos en cada parada

### C. Lavado urgente en planta
- Coordinar con planta: lavado express de botellas en maintenance
- Target: 20+ botellas lavadas en 2 horas

### D. Si crítico (< 10): Proveedor backup 48h
- Contactar proveedor: orden urgente 30 botellas loaner
- Activar cláusula contrato 48h delivery

---

## ✅ VERIFICACIÓN

```bash
# Stock disponible > 20
sqlite3 /mnt/ssd_trabajo/hermes-agent/data/dispatch.db "
SELECT COUNT(*) FROM bottles WHERE status = 'available';
"
```

---

## 📞 ESCALAMIENTO

| Nivel | Stock | Acción |
|-------|-------|--------|
| **Nivel 1** | 15-20 | Acciones A-C |
| **Nivel 2** | 10-15 | A + B + C urgente + Líder informado |
| **Nivel 3** | < 10 | Proveedor backup + parar ventas no-B2B |

---

## 📝 REGISTRO

| Campo | Valor |
|-------|-------|
| Fecha/Hora | |
| Stock disponible | |
| Overdue count | |
| Acción tomada | |
| Resultado | |

**Firmado por:** ___________ | **Fecha:** ___________
