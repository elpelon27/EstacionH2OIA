# Runbooks — Incidentes Comunes Estación H2O

> **Última actualización**: 2026-08-07

---

## 🚨 INCIDENTE 1: Bridge Down (Valentina no responde)

### Síntomas
- `curl /health` falla o timeout
- WhatsApp mensajes no procesados
- `systemctl status valentina-bridge` → inactive/failed

### Diagnóstico
```bash
# 1. Ver estado
systemctl status valentina-bridge --no-pager

# 2. Ver logs error
journalctl -u valentina-bridge -p err --since "10 minutes ago"

# 3. Verificar puerto
ss -tlnp | grep :8000

# 4. Verificar BD
sqlite3 /mnt/ssd_trabajo/hermes-agent/data/conversations.db "PRAGMA integrity_check;"
```

### Resolución
| Causa | Acción |
|---|---|
| OOM / MemoryMax | `systemctl restart valentina-bridge` |
| DB locked / corrupt | `sqlite3 ... "PRAGMA wal_checkpoint(FULL);"` + restart |
| Config .env inválida | Verificar `/mnt/ssd_trabajo/hermes-agent/config/.env` |
| Puerto ocupado | `ss -tlnp | grep :8000` → kill proceso |

### Post-fix
```bash
sudo systemctl restart valentina-bridge
sleep 3
curl -s http://localhost:8000/health | jq .
```

---

## 🚨 INCIDENTE 2: Cloudflared Tunnel Down (Webhooks no llegan)

### Síntomas
- Meta Cloud API devuelve timeout/error webhook
- WhatsApp mensajes no llegan a bridge
- `systemctl status cloudflared` → inactive/failed/activating

### Diagnóstico
```bash
# 1. Ver estado
systemctl status cloudflared --no-pager

# 2. Ver logs
journalctl -u cloudflared --since "10 minutes ago" | tail -30

# 3. Verificar conectividad
curl -I https://api.cloudflare.com
ping -c 3 1.1.1.1
```

### Resolución
| Causa | Acción |
|---|---|
| QUIC connection failed | `systemctl restart cloudflared` (reconecta auto) |
| DNS resolution failed | Verificar `/etc/resolv.conf` |
| Tunnel ID inválido | Verificar `/etc/cloudflared/config.yml` + credenciales |
| Network partition | Esperar auto-reconnect (cloudflared reintenta) |

### Post-fix
```bash
sudo systemctl restart cloudflared
sleep 5
systemctl status cloudflared --no-pager
# Verificar: "Registered tunnel connection" en logs
```

---

## 🚨 INCIDENTE 3: Dispatcher Bot No Notifica Choferes

### Síntomas
- Pedidos en `dispatch_queue` estado='pending' no se procesan
- Choferes no reciben Telegram
- Logs: "Vehículo X no tiene chat_id de Telegram"

### Diagnóstico
```bash
# 1. Ver queue
sqlite3 /mnt/ssd_trabajo/hermes-agent/data/conversations.db \
  "SELECT id, cliente_nombre, estado FROM dispatch_queue WHERE estado='pending';"

# 2. Ver vehicles
sqlite3 /mnt/ssd_trabajo/hermes-agent/data/dispatch.db \
  "SELECT id, name, operator_name, telegram_chat_id FROM vehicles;"

# 3. Ver consumer loop logs
journalctl -u valentina-bridge --since "5 minutes ago" | grep -E "Consumer|Procesando|notified"
```

### Resolución
| Causa | Acción |
|---|---|
| `telegram_chat_id` NULL | Chofer envía `/start` a @DespachoH2O_bot → obtener chat_id → UPDATE vehicles |
| Consumer loop muerto | `systemctl restart valentina-bridge` (recrea loop) |
| Telegram API rate limit | Esperar / verificar logs dispatcher-bot |
| Vehículo saturado (>10 pending) | Completar entregas o asignar otro vehicle |

### Fix chat_ids (cuando choferes los den)
```sql
UPDATE vehicles SET telegram_chat_id=<YORDANIS_ID> WHERE id=1;
UPDATE vehicles SET telegram_chat_id=<EVERT_ID> WHERE id=2;
```

---

## 🚨 INCIDENTE 4: Database Locked / Corrupt

### Síntomas
- `sqlite3.OperationalError: database is locked`
- `attempt to write a readonly database`
- Tests fallan con `sqlite3.OperationalError`

### Diagnóstico
```bash
# 1. Ver permisos
ls -la /mnt/ssd_trabajo/hermes-agent/data/

# 2. Ver WAL files
ls -la /mnt/ssd_trabajo/hermes-agent/data/*-wal /mnt/ssd_trabajo/hermes-agent/data/*-shm

# 3. Integrity check
sudo -u valentina sqlite3 /mnt/ssd_trabajo/hermes-agent/data/conversations.db "PRAGMA integrity_check;"
```

### Resolución
| Causa | Acción |
|---|---|
| Permisos incorrectos | `sudo chown -R valentina:valentina /mnt/ssd_trabajo/hermes-agent/data && sudo chmod 640 /mnt/ssd_trabajo/hermes-agent/data/*.db` |
| WAL corrupto | `sudo -u valentina sqlite3 conversations.db "PRAGMA wal_checkpoint(FULL);"` |
| Proceso zombie | `lsof /mnt/ssd_trabajo/hermes-agent/data/conversations.db` → kill |
| Usuario sin grupo | `usermod -a -G valentina skynet && newgrp valentina` |

### Post-fix
```bash
# Verificar
sudo -u valentina sqlite3 /mnt/ssd_trabajo/hermes-agent/data/conversations.db "PRAGMA integrity_check;"
# Debe retornar: ok
```

---

## 🚨 INCIDENTE 5: Financial Shield Tests Fallan (DB Readonly)

### Síntomas
- Tests `test_financial_integration.py` fallan con `attempt to write a readonly database`
- Otros tests pasan

### Causa Raíz
Tests corren como usuario `skynet` pero BD pertenece a `valentina:valentina` con permisos 640.

### Resolución
```bash
# Opción A: Ejecutar tests con grupo valentina
newgrp valentina << 'EOF'
cd /mnt/ssd_trabajo/hermes-agent
/mnt/ssd_trabajo/hermes-agent/venv/bin/python -m pytest tests/integration/financial/ -v --no-cov
EOF

# Opción B: Añadir skynet a grupo valentina (permanente)
sudo usermod -a -G valentina skynet
# Luego reiniciar sesión o: newgrp valentina
```

### Verificación
```bash
# Debe pasar
newgrp valentina && cd /mnt/ssd_trabajo/hermes-agent && \
  /mnt/ssd_trabajo/hermes-agent/venv/bin/python -m pytest tests/integration/financial/ -v --no-cov
```

---

## 🚨 INCIDENTE 5: Consumer Loop No Procesa Queue

### Síntomas
- Pedidos se acumulan en `dispatch_queue` estado='pending'
- Logs no muestran "Consumer loop iniciado" ni "Procesando"

### Diagnóstico
```bash
# 1. Ver si consumer task existe
journalctl -u valentina-bridge --since "10 minutes ago" | grep -E "Consumer loop|consumer_task"

# 2. Ver health
curl -s http://localhost:8000/health | jq .

# 3. Verificar notify_consumer import
grep -n "notify_consumer" /mnt/ssd_trabajo/hermes-agent/api/bridge.py
```

### Resolución
| Causa | Acción |
|---|---|
| Bridge reiniciado sin consumer | `systemctl restart valentina-bridge` |
| Import error | Verificar `skills.dispatch.consumer` existe |
| Event loop blocked | Reiniciar bridge completo |

---

## 🚨 INCIDENTE 6: Tests Financieros Fallan en CI (Permisos)

### Síntomas
- Tests pasan local con `newgrp valentina` pero fallan en CI/GitHub Actions

### Resolución CI
```yaml
# .github/workflows/tests.yml
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Setup valentina user
        run: |
          sudo useradd --system --no-create-home --shell /usr/sbin/nologin valentina
          sudo mkdir -p /mnt/ssd_trabajo/hermes-agent/data
          sudo chown -R valentina:valentina /mnt/ssd_trabajo/hermes-agent/data
      - name: Run tests as valentina
        run: |
          sudo -u valentina bash -c "
            cd /mnt/ssd_trabajo/hermes-agent
            source venv/bin/activate
            python -m pytest tests/ -x -q --no-cov
          "
```

---

## 📞 ESCALAMIENTO

| Nivel | Contacto | Cuando |
|---|---|---|
| **L1** | Runbooks arriba | Incidentes estándar |
| **L2** | Revisar logs + runbook | Runbook no resuelve en 15 min |
| **L3** | Llamar a ingeniero de guardia | Múltiples servicios down / data loss |

---

*Runbooks generados 2026-08-07 post chaos engineering*