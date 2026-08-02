# ⏱️ RUNBOOK: BridgeHighResponseTime
**Alert:** `BridgeHighResponseTime` | **Severity:** WARNING | **Response Time:** < 15 min

---

## 📋 DESCRIPCIÓN
Latencia P95 de Valentina Bridge > 10 segundos durante 5+ minutos.

**Métrica:** `histogram_quantile(0.95, rate(valentina_response_time_seconds_bucket[5m])) > 10`

---

## 🔍 DIAGNÓSTICO (5-10 min)

```bash
# 1. Verificar latencia actual
curl -s http://localhost:8000/metrics | grep valentina_response_time_seconds_bucket

# 2. Verificar salud de dependencias
# Dify
curl -s http://localhost/v1/chat-messages \
  -H "Authorization: Bearer $DIFY_API_KEY" \
  -d '{"inputs":{},"query":"test","response_mode":"blocking","user":"health"}' \
  -w "\nHTTP: %{http_code} Time: %{time_total}s\n" -o /dev/null

# Meta Graph API
curl -s "https://graph.facebook.com/v25.0/me?access_token=$META_ACCESS_TOKEN" \
  -w "\nHTTP: %{http_code} Time: %{time_total}s\n" -o /dev/null

# 3. Verificar recursos del sistema
htop  # CPU, RAM
df -h /mnt/ssd_trabajo  # Disco
```

---

## 🎯 CAUSAS COMUNES Y ACCIONES

| Causa | Síntomas | Acción |
|-------|----------|--------|
| **Dify lento/caído** | `/chat-messages` > 5s | Reiniciar Dify / Ollama: `docker restart docker-api-1 docker-ollama-1` |
| **Meta API lento** | Graph API > 3s | Verificar conectividad, reintentar luego (fuera de control) |
| **BD bloqueada** | `database is locked` en logs | Verificar `PRAGMA busy_timeout`, reiniciar bridge |
| **CPU throttling** | CPU > 100% | Verificar procesos, reiniciar bridge |
| **Memoria alta** | RSS > 800MB | Reiniciar bridge: `sudo systemctl restart valentina-bridge` |

---

## ✅ PLAN DE ACCIÓN RECOMENDADO

### Paso 1: Reinicio rápido del bridge (resuelve 80% casos)
```bash
sudo systemctl restart valentina-bridge
sleep 10
curl -s http://localhost:8000/health | jq .
```

### Paso 2: Si persiste, reiniciar Dify + Ollama
```bash
docker restart docker-api-1 docker-ollama-1
sleep 15
# Verificar Dify
curl -s http://localhost/v1/chat-messages -H "Authorization: Bearer $DIFY_API_KEY" -d '{"inputs":{},"query":"test","response_mode":"blocking","user":"health"}'
```

### Paso 3: Si persiste, reiniciar todo el stack
```bash
sudo systemctl restart valentina-bridge dispatcher-bot telegram-bot prometeo-telegram
docker restart docker-api-1 docker-ollama-1 docker-redis-1 docker-db_postgres-1
```

---

## 🔍 VERIFICACIÓN POST-FIX

```bash
# Latencia P95 < 5s
curl -s http://localhost:8000/metrics | grep -A20 'valentina_response_time_seconds_bucket' | head -25

# Health OK
curl -s http://localhost:8000/health | jq .

# Test mensaje real (número de prueba)
```

---

## 📞 ESCALAMIENTO

| Nivel | Tiempo | Acción |
|-------|--------|--------|
| **Nivel 1** | 0-15 min | Ejecutar pasos 1-2 |
| **Nivel 2** | 15-30 min | Paso 3 + contactar Líder |
| **Nivel 3** | 30+ min | Revisar arquitectura, posible rollback deploy |

---

## 📝 REGISTRO DE INCIDENTE

| Campo | Valor |
|-------|-------|
| Fecha/Hora inicio | |
| Latencia P95 máxima | |
| Causa raíz | |
| Acción que resolvió | |
| Tiempo total inactividad | |

**Firmado por:** ___________ | **Fecha:** ___________
