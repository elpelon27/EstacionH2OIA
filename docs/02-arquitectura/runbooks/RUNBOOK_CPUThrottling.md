# RUNBOOK: CPUThrottling
**Alert:** `CPUThrottling` | **Severity:** WARNING | **Response Time:** < 15 min

---

## DESCRIPCIÓN
Valentina Bridge usando > 100% CPU (1 core) sostenido.

**Métrica:** `rate(process_cpu_seconds_total{job="hermes"}[5m]) > 1.0`

---

## DIAGNÓSTICO (2-3 min)

```bash
# 1. Ver CPU actual
curl -s http://localhost:8000/metrics | grep process_cpu_seconds_total

# 2. Ver procesos
top -bn1 | grep valentina-bridge

# 3. Ver qué está consumiendo CPU
py-spy top --pid $(pgrep -f "uvicorn.*bridge:app") 2>/dev/null || echo "py-spy no instalado"
```

---

## ACCIONES

### 1. Reinicio rápido (resuelve 90%)
```bash
sudo systemctl restart valentina-bridge
sleep 10
curl -s http://localhost:8000/metrics | grep process_cpu_seconds_total
```

### 2. Si persiste: verificar loop infinito / carga anómala
```bash
# Ver logs recientes
journalctl -u valentina-bridge -n 200 --no-pager | grep -E "loop|CPU|timeout|error"

# Verificar si hay requests colgados
curl -s http://localhost:8000/metrics | grep -E "valentina_response_time|valentina_messages_total"
```

### 3. Si persiste: reinicio completo
```bash
sudo systemctl restart valentina-bridge dispatcher-bot telegram-bot prometeo-telegram
docker restart docker-api-1 docker-ollama-1
```

---

## VERIFICACIÓN

```bash
# CPU rate < 0.8
curl -s http://localhost:8000/metrics | grep 'process_cpu_seconds_total' | awk '{print $2}'
```

---

## ESCALAMIENTO

| Nivel | Tiempo | Acción |
|-------|--------|--------|
| Nivel 1 | 0-15 min | Reinicio bridge |
| Nivel 2 | 15-30 min | Reinicio stack completo |
| Nivel 3 | 30+ min | Contactar Prometeo/Líder |

---

## REGISTRO

| Campo | Valor |
|-------|-------|
| Fecha/Hora | |
| CPU rate antes | |
| CPU rate después | |
| Acción | |

**Firmado por:** ___________ | **Fecha:** ___________