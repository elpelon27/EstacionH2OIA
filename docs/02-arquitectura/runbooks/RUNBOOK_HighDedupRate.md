# 🔄 RUNBOOK: HighDedupRate
**Alert:** `HighDedupRate` | **Severity:** INFO | **Response Time:** < 30 min

---

## 📋 DESCRIPCIÓN
Alta tasa de mensajes duplicados de Meta (reintentos de webhook).

**Métrica:** `rate(valentina_dedup_hits_total[5m]) > 5`

---

## 🔍 DIAGNÓSTICO (2-3 min)

```bash
# 1. Ver tasa actual
curl -s http://localhost:8000/metrics | grep valentina_dedup_hits_total

# 2. Verificar si bridge responde lento (causa reintentos Meta)
curl -s http://localhost:8000/metrics | grep valentina_response_time_seconds_bucket

# 3. Ver logs de deduplicación
journalctl -u valentina-bridge -n 50 --no-pager | grep -i duplicate
```

---

## 🎯 CAUSAS Y ACCIONES

| Causa | Acción |
|-------|--------|
| **Bridge lento (>5s)** | Ver `BridgeHighResponseTime` runbook |
| **Meta reintentando por red** | Monitorear, suele auto-resolverse |
| **Bug en cache deduplicación** | Reiniciar bridge: `sudo systemctl restart valentina-bridge` |

---

## ✅ ACCIONES RECOMENDADAS

### 1. Monitorear 15 min (suele ser transitorio)
```bash
watch -n 30 'curl -s http://localhost:8000/metrics | grep valentina_dedup_hits_total'
```

### 2. Si persiste > 30 min: reiniciar bridge
```bash
sudo systemctl restart valentina-bridge
```

---

## ✅ VERIFICACIÓN

```bash
# Dedup rate < 1/s
curl -s http://localhost:8000/metrics | grep 'valentina_dedup_hits_total' | head -1
```

---

## 📝 REGISTRO

| Campo | Valor |
|-------|-------|
| Fecha/Hora | |
| Dedup rate pico | |
| Causa | |
| Acción | |

**Firmado por:** ___________ | **Fecha:** ___________
