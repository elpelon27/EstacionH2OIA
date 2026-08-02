# 🚚 RUNBOOK: VehicleSaturated
**Alert:** `VehicleSaturated` | **Severity:** WARNING | **Response Time:** < 15 min

---

## 📋 DESCRIPCIÓN
Un vehículo tiene más de 8 entregas pendientes simultáneamente.

**Métrica:** `sum by (vehicle_id) (deliveries_pending) > 8`

---

## 🔍 DIAGNÓSTICO (2-5 min)

```bash
# 1. Ver deliveries pendientes por vehículo
sqlite3 /mnt/ssd_trabajo/hermes-agent/data/dispatch.db "
SELECT v.operator_name, v.name, COUNT(d.id) as pending
FROM vehicles v
LEFT JOIN deliveries d ON d.vehicle_id = v.id AND d.status = 'pending'
WHERE v.active = 1
GROUP BY v.id;
"

# 2. Ver queue en bridge
sqlite3 /mnt/ssd_trabajo/hermes-agent/data/conversations.db "
SELECT estado, COUNT(*) as count
FROM dispatch_queue
GROUP BY estado;
"

# 3. Verificar estado choferes en Telegram Bot
# /status en @DespachoH2O_bot
```

---

## 🎯 ACCIONES

### A. Rebalanceo manual (si un chofer tiene mucho y otro poco)
```bash
# 1. Identificar vehicle_id saturado y vehicle_id libre
# 2. Mover deliveries pendientes del saturado al libre
sqlite3 /mnt/ssd_trabajo/hermes-agent/data/dispatch.db "
UPDATE deliveries SET vehicle_id = <libre_id> 
WHERE vehicle_id = <saturado_id> AND status = 'pending'
LIMIT 3;
"
```

### B. Si ambos saturados: priorizar y diferir
- Verificar en `dispatch_queue` qué pedidos son B2B daily (urgentes)
- Mover pedidos no urgentes a `estado = 'diferido'` en conversations.db

### C. Si es recurrente: aumentar flota / optimizar rutas
- Ejecutar VRP completo: `python skills/run_route_planner.py`
- Verificar capacidad real de triciclos (30 llenos)

---

## ✅ VERIFICACIÓN

```bash
# Verificar balance
sqlite3 /mnt/ssd_trabajo/hermes-agent/data/dispatch.db "
SELECT v.operator_name, COUNT(d.id) as pending
FROM vehicles v
LEFT JOIN deliveries d ON d.vehicle_id = v.id AND d.status = 'pending'
WHERE v.active = 1
GROUP BY v.id;
"
# Debe mostrar ambos < 8
```

---

## 📞 ESCALAMIENTO

| Nivel | Trigger | Acción |
|-------|---------|--------|
| **Nivel 1** | Un vehículo > 8 | Rebalanceo manual |
| **Nivel 2** | Ambos > 8 | Priorizar B2B, diferir resto, contactar Líder |
| **Nivel 3** | Recurrente diario | Ejecutar VRP, evaluar flota |

---

## 📝 REGISTRO

| Campo | Valor |
|-------|-------|
| Fecha/Hora | |
| Vehicle saturado | |
| Entregas pendientes | |
| Acción tomada | |
| Resultado | |

**Firmado por:** ___________ | **Fecha:** ___________
