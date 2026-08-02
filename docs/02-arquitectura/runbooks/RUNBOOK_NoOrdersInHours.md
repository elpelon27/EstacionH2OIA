# 📭 RUNBOOK: NoOrdersInHours
**Alert:** `NoOrdersInHours` | **Severity:** WARNING | **Response Time:** < 30 min

---

## 📋 DESCRIPCIÓN
No se han confirmado pedidos en la última hora durante horario laboral (8am-6pm).

**Métrica:** `increase(valentina_orders_total[1h]) == 0 and hour() > 8 and hour() < 18`

---

## 🔍 DIAGNÓSTICO (3-5 min)

```bash
# 1. Verificar pedidos hoy
sqlite3 /mnt/ssd_trabajo/hermes-agent/data/conversations.db "
SELECT COUNT(*) FROM orders WHERE date(created_at, 'unixepoch', 'localtime') = date('now', 'localtime');
"

# 2. Verificar mensajes recientes
journalctl -u valentina-bridge -n 50 --no-pager | grep -i "mensaje\|pedido\|order"

# 3. Verificar Dify responde
curl -s http://localhost/v1/chat-messages -H "Authorization: Bearer $DIFY_API_KEY" -d '{"inputs":{},"query":"test","response_mode":"blocking","user":"health"}'
```

---

## 🎯 CAUSAS Y ACCIONES

| Causa | Verificación | Acción |
|-------|--------------|--------|
| **Día festivo / domingo** | `date +%u` (1=Lun, 7=Dom) | Normal, no acción |
| **Hora fuera de horario** | `date +%H` (8-18) | Normal si <8 o >18 |
| **Dify caído** | Test query falla | Reiniciar Dify/Ollama |
| **Bridge caído** | Health check falla | Reiniciar bridge |
| **Sin clientes activos** | Normal en días lentos | Monitorear |

---

## ✅ ACCIONES

### 1. Verificar si es día laborable y horario
```bash
# Día semana (1=Lun..7=Dom) y hora
date +%u && date +%H
# Si domingo (7) o <8 / >18 → Normal
```

### 2. Si es horario laboral y día laborable:
```bash
# Reiniciar bridge + Dify
sudo systemctl restart valentina-bridge
docker restart docker-api-1 docker-ollama-1
sleep 15
curl -s http://localhost:8000/health | jq .
```

---

## ✅ VERIFICACIÓN

```bash
# Verificar que llegan mensajes
journalctl -u valentina-bridge -f | grep -i "mensaje\|message"
```

---

## 📝 REGISTRO

| Campo | Valor |
|-------|-------|
| Fecha/Hora | |
| Día/Hora | |
| Causa | |
| Acción | |

**Firmado por:** ___________ | **Fecha:** ___________
