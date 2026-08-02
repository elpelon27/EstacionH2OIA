# 🔴 RUNBOOK: ServiceDown
**Alert:** `ServiceDown` | **Severity:** CRITICAL | **Response Time:** < 5 min

---

## 📋 DESCRIPCIÓN
Un servicio crítico (hermes, node, prometheus) está caído.

**Métrica:** `up{job=~"hermes|node|prometheus"} == 0`

---

## 🔍 DIAGNÓSTICO INMEDIATO (1 min)

```bash
# 1. Identificar qué servicio está caído
curl -s http://localhost:9090/api/v1/query?query=up | jq .

# 2. Verificar systemd
systemctl status valentina-bridge dispatcher-bot telegram-bot prometeo-telegram
systemctl status docker  # Para prometheus/node_exporter

# 3. Verificar puertos
ss -tlnp | grep -E '8000|9090|9100|3001|6379|6333|11434'
```

---

## 🎯 ACCIONES POR SERVICIO

### A. Valentina Bridge (job=hermes, port 8000)
```bash
# Reiniciar
sudo systemctl restart valentina-bridge
sleep 10
curl -s http://localhost:8000/health | jq .

# Si falla: ver logs
journalctl -u valentina-bridge -n 100 --no-pager
```

### B. Dispatcher Bot (Telegram choferes)
```bash
sudo systemctl restart dispatcher-bot
sleep 5
# Verificar: /status en @DespachoH2O_bot
```

### C. Prometheus (port 9090)
```bash
docker restart hermes_prometheus
sleep 10
curl -s http://localhost:9090/-/healthy
```

### D. Grafana (port 3001)
```bash
docker restart hermes_grafana
sleep 10
curl -s http://localhost:3001/api/health
```

### E. Node Exporter / Redis / Qdrant / Ollama
```bash
docker restart hermes_node_exporter
docker restart hermes_redis
docker restart hermes_qdrant
docker restart docker-ollama-1
```

### F. Dify (crítico para Valentina)
```bash
docker restart docker-api-1 docker-ollama-1 docker-redis-1 docker-db_postgres-1
# Verificar
curl -s http://localhost/v1/chat-messages -H "Authorization: Bearer $DIFY_API_KEY" -d '{"inputs":{},"query":"test","response_mode":"blocking","user":"health"}'
```

---

## 🔄 REINICIO COMPLETO STACK (orden crítico)

```bash
# 1. Base de datos
docker restart docker-db_postgres-1 docker-redis-1
sleep 5

# 2. IA / Dify
docker restart docker-ollama-1 docker-api-1
sleep 15

# 3. Bridge + Bots
sudo systemctl restart valentina-bridge dispatcher-bot telegram-bot prometeo-telegram
sleep 10

# 4. Monitoreo
docker restart hermes_prometheus hermes_grafana
sleep 10

# 5. Verificar todo
curl -s http://localhost:8000/health | jq .
curl -s http://localhost:9090/-/healthy
curl -s http://localhost:3001/api/health
```

---

## ✅ VERIFICACIÓN POST-RECUPERACIÓN

```bash
# Todos los servicios UP
curl -s http://localhost:9090/api/v1/query?query=up | jq '.data.result[] | select(.value[1]=="1") | .metric.job'

# Health checks
curl -s http://localhost:8000/health | jq -e '.status=="ok"'
curl -s http://localhost:9090/-/healthy
curl -s http://localhost:3001/api/health
```

---

## 📞 ESCALAMIENTO

| Nivel | Tiempo | Acción |
|-------|--------|--------|
| **Nivel 1** | 0-5 min | Reiniciar servicio individual |
| **Nivel 2** | 5-15 min | Reiniciar stack completo ordenado |
| **Nivel 3** | 15+ min | Contactar Líder + Prometeo, revisar logs, posible rollback |

---

## 📝 REGISTRO DE INCIDENTE

| Campo | Valor |
|-------|-------|
| Fecha/Hora | |
| Servicio caído | |
| Causa raíz | |
| Tiempo de inactividad | |
| Servicios afectados | |
| Acción de recuperación | |

**Firmado por:** ___________ | **Fecha:** ___________
