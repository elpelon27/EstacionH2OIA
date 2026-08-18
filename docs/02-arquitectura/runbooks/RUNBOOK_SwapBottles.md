# Runbook: Swap de Botellones (Loaner)

**Ultima actualizacion**: 2026-08-17
**Owner**: Líder (operacional) + Prometeo (sistema)
**Critico**: Si — proceso central del negocio

---

## Que es el Swap

El modelo Swap funciona asi:
1. Cliente recibe un botellon **loaner** (prestado) lleno
2. Cliente devuelve el botellon vacio en la siguiente entrega
3. Botellones vacios se sellan en planta para reutilizacion
4. Inventario: 165 unidades loaner con tracking individual por codigo QR

## Componentes del sistema

| Componente | Archivo | Estado |
|---|---|---|
| BottleTracker | `skills/dispatch/bottle_tracker.py` | Operativo |
| Route Engine (OR-Tools VRP) | `skills/dispatch/route_engine.py` | Operativo |
| Dispatcher Telegram Bot | `skills/dispatch/telegram_bot.py` | Operativo |
| DispatcherSkill | `skills/dispatcher_skill.py` | Operativo |
| FastAPI Endpoints | `api/routes/dispatch.py` | Operativo |
| BD dispatch.db | `data/dispatch.db` | 11 tablas, schema completo |

## Proceso de swap paso a paso

### 1. Asignacion de botellon loaner
- El sistema busca un botellon disponible (`bottle_tracker.get_available_bottle()`)
- Se asigna al cliente con `bottle_tracker.assign_bottle(bottle_code, client_id)`
- El botellon pasa a estado "assigned"

### 2. Entrega al cliente
- Chofer confirma entrega via Telegram bot (`[Entregado]`)
- `bottle_tracker.confirm_delivery(bottle_code, client_id)` cambia estado a "delivered"
- GPS se registra en `gps_tracks`

### 3. Recoleccion de vacio
- En la siguiente entrega, el chofer recoge el botellon vacio
- `bottle_tracker.collect_empty(bottle_code)` cambia estado a "returned"
- Botellon disponible para sellado

### 4. Sellado en planta
- Botellones retornados se sellan y pasan a "available"
- `bottle_tracker.refill_bottle(bottle_code)` cambia estado a "available"

## Estados de botellon

```
available -> assigned -> delivered -> returned -> available (ciclo)
```

## Comandos operacionales

### Ver inventario de botellones
```bash
cd /mnt/ssd_trabajo/hermes-agent
source venv/bin/activate
python3 -c "
from skills.dispatch.bottle_tracker import BottleTracker
bt = BottleTracker()
print(bt.get_inventory_summary())
"
```

### Ver botellones por estado
```bash
sqlite3 data/dispatch.db "
SELECT status, COUNT(*) as count 
FROM bottles 
GROUP BY status 
ORDER BY count DESC;
"
```

### Ver entregas pendientes
```bash
sqlite3 data/dispatch.db "
SELECT b.bottle_code, b.client_id, d.operator_name, b.assigned_at
FROM bottles b
JOIN deliveries d ON b.delivery_id = d.id
WHERE b.status = 'delivered'
ORDER BY b.assigned_at DESC;
"
```

### Ver botellones overdue (mas de X dias)
```bash
sqlite3 data/dispatch.db "
SELECT b.bottle_code, b.client_id, b.assigned_at,
       julianday('now') - julianday(b.assigned_at) as dias
FROM bottles b
WHERE b.status IN ('assigned', 'delivered')
  AND julianday('now') - julianday(b.assigned_at) > 7
ORDER BY dias DESC;
"
```

### Registrar botellon nuevo
```bash
sqlite3 data/dispatch.db "
INSERT INTO bottles (bottle_code, status, created_at)
VALUES ('SWAP-001', 'available', datetime('now'));
"
```

## Alertas automaticas

| Alerta | Condicion | Accion |
|---|---|---|
| BottleInventoryLow | < 10 botellones available | Notificar Líder |
| BottleOverdueHigh | > 20 botellones > 7 dias | Notificar Líder |
| DeliveryStuckPending | Entregas > 2h sin confirmar | Reasignar chofer |

## Migracion planificada

- 165 unidades loaner iniciales
- Migracion gradual en 3 semanas
- Mapa de calor GPS historico para optimizacion de rutas
- **BLOQUEADO por DT-01**: choferes Yordanis y Evert no tienen telegram_chat_id

## Backup

```bash
# Backup de dispatch.db
cp data/dispatch.db data/backups/dispatch_$(date +%Y%m%d_%H%M%S).db

# Restaurar
cp data/backups/dispatch_YYYYMMDD_HHMMSS.db data/dispatch.db
```
