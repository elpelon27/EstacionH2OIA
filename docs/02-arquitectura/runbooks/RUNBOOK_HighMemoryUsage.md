# RUNBOOK: HighMemoryUsage
**Alert:** `HighMemoryUsage` | **Severity:** WARNING | **Response Time:** < 15 min

---

## DESCRIPCIÓN
Valentina Bridge memoria RSS > 80% del límite (1GB).

**Métrica:** `(process_resident_memory_bytes{job="hermes"} / 1024 / 1024 / 1024) > 0.8`

---

## DIAGNÓSTICO (2-3 min)

```bash
# 1. Ver memoria actual
curl -s http://localhost:8000/metrics | grep process_resident_memory_bytes

# 2. Ver proceso
ps aux | grep valentina-bridge

# 3. Ver logs por memory leaks
journalctl -u valentina-bridge -n 100 --no-pager | grep -i memory
```

---

## ACCIONES

### 1. Reinicio rápido (resuelve 95%)
```bash
sudo systemctl restart valentina-bridge
sleep 10
curl -s http://localhost:8000/metrics | grep process_resident_memory_bytes
```

### 2. Si persiste: reinicio completo stack
```bash
sudo systemctl restart valentina-bridge dispatcher-bot telegram-bot prometeo-telegram
docker restart docker-api-1 docker-ollama-1
```

---

## VERIFICACIÓN

```bash
# RSS < 800MB (80% de 1GB)
curl -s http://localhost:8000/metrics | grep 'process_resident_memory_bytes' | awk '{print $2/1024/1024 " MB"}'
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
| RSS antes | |
| RSS después | |
| Acción | |

**Firmado por:** ___________ | **Fecha:** ___________