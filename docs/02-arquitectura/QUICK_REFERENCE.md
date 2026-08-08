# Quick Reference — Estación H2O Operations

> **Última actualización**: 2026-08-07

---

## 🔧 COMANDOS ESSENCIALES

### Health Checks
```bash
# Bridge completo
curl -s http://localhost:8000/health | jq .

# Métricas Prometheus
curl -s http://localhost:8000/metrics | grep valentina

# Estado servicios
systemctl status cloudflared dispatcher-bot telegram-bot valentina-bridge --no-pager
```

### Queue Management
```bash
# Ver pedidos pendientes
sqlite3 /mnt/ssd_trabajo/hermes-agent/data/conversations.db \
  "SELECT id, cliente_nombre, estado FROM dispatch_queue WHERE estado='pending';"

# Forzar procesamiento consumer
curl -s -X POST http://localhost:8000/dispatch/process-queue | jq .
```

### Logs
```bash
# Tiempo real (todos)
journalctl -u valentina-bridge -u dispatcher-bot -u telegram-bot -f

# Solo bridge últimos 50 líneas
journalctl -u valentina-bridge -n 50 --no-pager

# Solo errores
journalctl -u valentina-bridge -p err --since "1 hour ago"
```

### Backup
```bash
# Manual
sudo -u valentina /mnt/ssd_trabajo/hermes-agent/scripts/backup_db.sh

# Ver backups
ls -la /mnt/ssd_trabajo/hermes-agent/backups/
```

### Tests
```bash
# Suite completa (requiere grupo valentina)
newgrp valentina && cd /mnt/ssd_trabajo/hermes-agent && \
  /mnt/ssd_trabajo/hermes-agent/venv/bin/python -m pytest tests/ -x -q --no-cov

# Solo unit tests
newgrp valentina && cd /mnt/ssd_trabajo/hermes-agent && \
  /mnt/ssd_trabajo/hermes-agent/venv/bin/python -m pytest tests/unit/ -q --no-cov
```

### Performance Profiling
```bash
# Bridge (30s)
sudo ~/.cargo/bin/py-spy record -o profile.svg --pid $(systemctl show valentina-bridge -p MainPID --value) --duration 30

# Dispatcher bot
sudo ~/.cargo/bin/py-spy record -o dispatcher_profile.svg --pid $(systemctl show dispatcher-bot -p MainPID --value) --duration 30
```

---

## 🚨 EMERGENCIA

### Kill Switch (Telegram bot líder)
```
/stop   → Activa kill switch (Valentina deja de responder)
/start  → Desactiva kill switch
/status → Estado completo
/health → Health check
```

### Reinicio Servicios
```bash
# Reinicio ordenado
sudo systemctl restart valentina-bridge dispatcher-bot telegram-bot

# Solo bridge
sudo systemctl restart valentina-bridge

# Verificar tras reinicio
sleep 3 && curl -s http://localhost:8000/health | jq .
```

---

## 📊 MONITOREO CLAVE

| Métrica | Normal | Alerta |
|---|---|---|
| Bridge uptime | > 0 | = 0 (down) |
| Consumer loop | Active | No logs "Consumer loop iniciado" |
| Queue pending | < 50 | > 100 |
| Memory bridge | < 500MB | > 800MB |
| Memory dispatcher | < 200MB | > 200MB |
| Cloudflared | Active | Inactive/Restarting |

---

## 🔑 CREDENCIALES Y RUTAS

| Recurso | Ruta / Comando |
|---|---|
| Bridge code | `/mnt/ssd_trabajo/hermes-agent/api/bridge.py` |
| Dispatcher skill | `/mnt/ssd_trabajo/hermes-agent/skills/dispatcher_skill.py` |
| Consumer loop | `/mnt/ssd_trabajo/hermes-agent/skills/dispatch/consumer.py` |
| Config .env | `/mnt/ssd_trabajo/hermes-agent/config/.env` |
| Systemd units | `/etc/systemd/system/*.service` |
| Backups | `/mnt/ssd_trabajo/hermes-agent/backups/` |
| Flamegraphs | `/mnt/ssd_trabajo/hermes-agent/*_profile.svg` |
| Docs arquitectura | `/mnt/ssd_trabajo/hermes-agent/docs/02-arquitectura/` |

---

## 🚀 DEPLOY / CAMBIOS

```bash
# 1. Cambios en código
git add -A && git commit -m "msg" && git push

# 2. Si cambia systemd unit
sudo cp /mnt/ssd_trabajo/hermes-agent/systemd/*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl restart <servicio>

# 3. Si cambia .env
sudo systemctl restart valentina-bridge dispatcher-bot telegram-bot
```

---

*Quick reference generado 2026-08-07*