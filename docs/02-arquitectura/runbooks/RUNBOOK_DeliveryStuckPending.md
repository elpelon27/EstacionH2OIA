# 📦 RUNBOOK: DeliveryStuckPending
**Alert:** `DeliveryStuckPending` | **Severity:** WARNING | **Response Time:** < 15 min

---

## 📋 DESCRIPCIÓN
Una entrega lleva más de 30 minutos en estado "pending" sin actualización.

**Métrica:** `sum by (delivery_id) (delivery_status_pending) > 0 for 30m`

---

## 🔍 DIAGNÓSTICO (3-5 min)

```bash
# 1. Identificar delivery atascado
sqlite3 /mnt/ssd_trabajo/hermes-agent/data/dispatch.db "
SELECT d.id, v.operator_name, d.status, d.created_at, 
       (strftime('%s','now') - d.created_at)/60 as minutes_stuck
FROM deliveries d
JOIN vehicles v ON d.vehicle_id = v.id
WHERE d.status = 'pending'
  AND (strftime('%s','now') - d.created_at) > 1800
ORDER BY minutes_stuck DESC;
"

# 2. Verificar si chofer recibió notificación
sqlite3 /mnt/ssd_trabajo/hermes-agent/data/dispatch.db "
SELECT v.operator_name, v.telegram_chat_id
FROM vehicles v
JOIN deliveries d ON d.vehicle_id = v.id
WHERE d.id = <delivery_id>;
"

# 3. Ver logs del dispatcher bot
journalctl -u dispatcher-bot -n 100 --no-pager | grep <delivery_id>
```

---

## 🎯 ACCIONES

### A. Chofer no recibió notificación (chat_id NULL o error Telegram)
```bash
# 1. Verificar chat_id
sqlite3 /mnt/ssd_trabajo/hermes-agent/data/dispatch.db "
SELECT v.id, v.operator_name, v.telegram_chat_id
FROM vehicles v WHERE v.active = 1;
"

# 2. Si NULL: pedir a chofer que ejecute /start en @DespachoH2O_bot
# 3. Re-enviar notificación manual
curl -X POST http://localhost:8000/dispatch/notify/driver -H "Content-Type: application/json" -d '{
  "vehicle_id": <vehicle_id>,
  "client_name": "<cliente>",
  "client_phone": "<telefono>",
  "bottles_full": <n>,
  "lat": <lat>, "lng": <lng>,
  "address": "<direccion>",
  "total_eur": <total>, "total_bs": <total_bs>,
  "metodo_pago": "<metodo>"
}'
```

### B. Chofer recibió pero no actúa
- Llamar directamente al chofer (Teléfono en vehicles table)
- Verificar si está en ruta / sin señal / ocupado

### C. Delivery ya completado pero no marcado
- Verificar con chofer: "¿Ya entregaste el pedido #X?"
- Si sí: marcar manualmente
```bash
sqlite3 /mnt/ssd_trabajo/hermes-agent/data/dispatch.db "
UPDATE deliveries SET status = 'delivered', actual_departure = datetime('now'), updated_at = datetime('now')
WHERE id = <delivery_id>;
"
```

### D. Cliente canceló / no está
- Marcar como `no_answer` o `cancelled`
- Mover botellas de vuelta a available si ya cargadas

---

## ✅ VERIFICACIÓN

```bash
# No deliveries stuck > 30 min
sqlite3 /mnt/ssd_trabajo/hermes-agent/data/dispatch.db "
SELECT COUNT(*) FROM deliveries
WHERE status = 'pending'
  AND (strftime('%s','now') - created_at) > 1800;
"
# Debe ser 0
```

---

## 📞 ESCALAMIENTO

| Nivel | Tiempo | Acción |
|-------|--------|--------|
| **Nivel 1** | 0-15 min | Re-enviar notificación / llamar chofer |
| **Nivel 2** | 15-30 min | Marcar manualmente / reasignar a otro vehículo |
| **Nivel 3** | 30+ min | Contactar Líder, revisar proceso |

---

## 📝 REGISTRO

| Campo | Valor |
|-------|-------|
| Fecha/Hora | |
| Delivery ID | |
| Chofer | |
| Causa | |
| Acción | |
| Resultado | |

**Firmado por:** ___________ | **Fecha:** ___________
