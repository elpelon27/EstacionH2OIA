# ⚠️ RUNBOOK: BridgeHighErrorRate
**Alert:** `BridgeHighErrorRate` | **Severity:** WARNING | **Response Time:** < 10 min

---

## 📋 DESCRIPCIÓN
Tasa de errores en Valentina Bridge > 0.1 req/s durante 2+ minutos.

**Métrica:** `rate(valentina_messages_total{status="error"}[5m]) > 0.1`

---

## 🔍 DIAGNÓSTICO (3-5 min)

```bash
# 1. Ver errores recientes
journalctl -u valentina-bridge -n 100 --no-pager | grep -i error

# 2. Ver métricas de error
curl -s http://localhost:8000/metrics | grep valentina_messages_total

# 3. Verificar health
curl -s http://localhost:8000/health | jq .
```

---

## 🎯 CAUSAS COMUNES

| Causa | Acción |
|-------|--------|
| **HMAC verification failed** | Verificar META_APP_SECRET en .env |
| **Dify timeout/unavailable** | Reiniciar Dify/Ollama |
| **Meta API rate limit** | Esperar / backoff exponencial |
| **DB locked** | Reiniciar bridge, verificar busy_timeout |
| **JSON decode error** | Verificar payload Meta webhook |

---

## ✅ ACCIONES

### 1. Reinicio rápido (resuelve 90%)
```bash
sudo systemctl restart valentina-bridge
sleep 10
curl -s http://localhost:8000/health | jq .
```

### 2. Verificar secrets
```bash
# Verificar que META_APP_SECRET, DIFY_API_KEY, etc. están en .env
grep -E "META_APP_SECRET|DIFY_API_KEY|META_ACCESS_TOKEN" /mnt/ssd_trabajo/hermes-agent/config/.env
```

### 3. Si persiste: reinicio completo
```bash
sudo systemctl restart valentina-bridge dispatcher-bot telegram-bot prometeo-telegram
docker restart docker-api-1 docker-ollama-1
```

---

## ✅ VERIFICACIÓN

```bash
# Error rate < 0.01
curl -s http://localhost:8000/metrics | grep 'valentina_messages_total{status="error"}'
```

---

## 📞 ESCALAMIENTO

| Nivel | Tiempo | Acción |
|-------|--------|--------|
| **Nivel 1** | 0-10 min | Reinicio + verificación secrets |
| **Nivel 2** | 10-20 min | Reinicio completo stack |
| **Nivel 3** | 20+ min | Contactar Prometeo/Líder |

---

## 📝 REGISTRO

| Campo | Valor |
|-------|-------|
| Fecha/Hora | |
| Error rate pico | |
| Causa | |
| Acción | |

**Firmado por:** ___________ | **Fecha:** ___________
