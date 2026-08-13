# RUNBOOK — Integraciones Odoo + R4 Conecta

**Última actualización**: 2026-08-12

Procedimientos operativos para las integraciones externas del hogar. Si aplica
un runbook específico de Financial Shield/Odoo, está en `docs/02-arquitectura/runbooks/`.

---

## 🔍 Diagnóstico rápido

```bash
# ¿Espera el bridge?
systemctl is-active valentina-bridge
curl -s -m 5 http://localhost:8000/health | python3 -m json.tool

# ¿Odoo responde?
curl -s -m 5 -o /dev/null -w "%{http_code}\n" http://localhost:8069/web/login

# ¿R4 webhook sano?
curl -s http://localhost:8000/webhook/r4/health

# ¿Pedidos atascados en cola de despacho?
sqlite3 data/conversations.db "SELECT COUNT(*) FROM dispatch_queue WHERE estado='pending';"
```

---

## 🐳 Odoo Docker

### Ver estado
```bash
docker ps --format "{{.Names}} {{.Status}}" | grep -E "odoo"
```

### Logs
```bash
docker logs odoo-web --tail 100
docker logs odoo-db --tail 50
```

### Reiniciar contenedores
```bash
cd infra/odoo && docker compose restart
docker compose up -d   # si estuvieran apagados
```

### Conectar por XML-RPC (smoke)
```bash
venv/bin/python -c "from src.integrations.odoo.odoo_sync import OdooClient; print(OdooClient().connect())"
```

### Backup
El backup diario (`backup_daily.sh` a las 3 AM) incluye el Postgres de Odoo.
Restaurar el volumen `odoo-db-data` desde el backup con retención 30 días.

---

## 🏦 R4 / Pago móvil

### Health del webhook
```bash
curl -s http://localhost:8000/webhook/r4/health
```

### Verificar estado de un pedido tras pago
```bash
sqlite3 data/conversations.db \
  "SELECT pedido_id, cliente_telefono, monto_total_eur, estado_pago FROM fs_pedidos ORDER BY id DESC LIMIT 20;"
```

### Reprocesar/validar pago manual (si el webhook no marcó)
```bash
venv/bin/python -c "
import asyncio
from src.financial.verificacion import verificar_pago_manual
# verificar_pago_manual(fs_pedido_id=..., monto_eur=..., metodo_pago='pagomovil', referencia=..., verificado_por='manual')
"
```

### ⚠️ Crash loop de valentina (2026-08-12)
Causa: watchdog systemd (`WatchdogSec=30`) mataba el bridge con SIGABRT aunque
estaba sano — el loop asyncio que envía `WATCHDOG=1` no despertaba a tiempo por
scan recovery/consumer con SQLite síncrono. **Solución**: unit con `Type=simple`
sin `WatchdogSec`; `Restart=always` + `StartLimitAction=none` cubren recovery.
NO reactivar `WatchdogSec` sin un loop de watchdog que no dependa del event loop.

---

## 📊 Monitoreo

```bash
# Salud completa (incluye Odoo, dispatch_db, cola)
curl -s http://localhost:8000/health | python3 -m json.tool

# Métricas Prometheus
curl -s http://localhost:8000/metrics | grep -E "valentina_(odoo_up|dispatch_queue_pending|messages_total)"
```

Umbrales sugeridos de alerta:
- `dispatch_queue_pending` > 10 por > 15 min → revisar dispatcher/consumer
- `valentina_odoo_up == 0` → Odoo caído → alarma (no bloquea WhatsApp pero sí facturación)
- `messages_total{status="error"}` creciendo → revisar Dify/Meta

---

## ✅ Checklist post-deploy de integración

- [ ] `docker ps` muestra odoo-web Up + odoo-db Up
- [ ] `/health` → `odoo: true`, `dispatch_db: true`
- [ ] `/webhook/r4/health` responde
- [ ] `sqlite3 data/conversations.db "SELECT COUNT(*) FROM dispatch_queue WHERE estado='pending';"`
      bajo control
- [ ] test e2e: `venv/bin/python -m pytest tests/e2e/test_fase8_e2e.py -q` → 4 passed
