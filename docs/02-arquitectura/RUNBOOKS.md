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

---

## 🚨 INCIDENTE 7: "Servicio caído" que se recupera solo (DNS del ISP)

**Lección 2026-10-07:** episodios de `Temporary failure in name resolution`
(DNS del ISP) tumbaron salidas WhatsApp/Telegram y Dify. Síntoma engañoso:
servicios "caídos" que se recuperan solos.

### Fix aplicado (Líder)
- `/etc/systemd/resolved.conf.d/estacion-h2o.conf`
  (DNS 1.1.1.1/8.8.8.8, fallbacks 9.9.9.9/1.0.0.1)
- `nmcli ipv4.ignore-auto-dns yes` en perfiles `netplan-enp0s31f6` y `casam&m`.

### ⚠️ Reglas
- La conexión ethernet la genera **netplan**: si se corre `netplan apply`
  puede regenerar el perfil y pisar el DNS manual → verificar tras
  cualquier `netplan apply`.
- **REGLA GENERAL:** ante cualquier "servicio caído / no responde",
  descartar DNS PRIMERO:
  ```bash
  resolvectl query <host>
  journalctl -u <svc> | grep "name resolution"
  ```
## 🚨 INCIDENTE 8: LLM local desalojado — primer mensaje >30s "problemas técnicos"

**Lección 2026-10-09:** Ollama (nativo) corre con `OLLAMA_MAX_LOADED_MODELS=1`
COMPARTIDO con otros proyectos de la máquina (OpenNotebook: nocturno 22GB,
veloz, qwen3.6:35b). Cuando otro proyecto carga su modelo, `qwen2.5:7b`
(Valentina) es desalojado → el próximo cliente paga la recarga 4.7GB CPU
(>30s) → timeout del bridge → "dificultades técnicas". El 2do mensaje
respondía porque la recarga siguió en background.

### Fix aplicado
- Estructural (DECISIÓN DEL LÍDER): **migración a API única OpenRouter** —
  todo el ecosistema ya usaba `llm_client.py` (glm-5.3 → glm-5.2:free →
  ollama); Valentina (Dify) se integró con `deepseek/deepseek-chat`
  (A/B 10-oct: p95 3.23s, calidad superior, único que rechaza "ya pague"
  prematuro). ~$2/mes. Switch verificado con pre_prompt 8830 chars intacto.
- Transitorio (retirar tras cerebro único si procede): cron
  `*/10 * * * * scripts/warmup_valentina_llm.sh` recarga+fija el modelo.
- bridge `_call_dify`: retry UNA vez solo en timeout (30s→120s).

### ⚠️ Reglas
- La API de model-config de Dify **REEMPLAZA la config entera** — si se manda
  parcial borra el pre_prompt (pasó en el duplicado; NO pasó en producción
  porque se mandó completo + verificación post-switch).
- `z-ai/glm-5.2:free` (tier-2 de llm_client.py) YA NO EXISTE en catálogo
  OpenRouter → ese fallback está muerto silenciosamente → PENDIENTE
  actualizarlo.
- Ollama queda para: tier-3 de emergencia + proyectos ajenos a H2O.

## 🚨 INCIDENTE 9: INSERT roto "13 values for 12 columns" — pedidos nunca llegaban a choferes

**Lección 2026-10-09:** el bonus de idempotencia cruzada (commit 1b5ab1e0)
agregó `fs_pedido_id` a los VALORES del INSERT de `_send_to_dispatch_queue`
(bridge.py) pero no a las COLUMNAS → **TODA orden por conversación murió
silenciosamente desde el reinicio de la noche anterior** (síntoma: choferes
"en silencio", dispatcher sin mensajes; Google Sheets Sí registraba).

### Fix aplicado
- Columna `fs_pedido_id` agregada al INSERT (validado offline + tests).
- Fix posterior (§1 misión pago→despacho): webhook R4 encola la entrega al
  verificar el pago (idempotente) + watchdog pagado-sin-despachar (15 min,
  1 alerta/pedido) + aviso de llegada [📍 Llegué]→WhatsApp cliente.

### ⚠️ Reglas
- **El E2E debe cubrir TODAS las vías de un mismo flujo** (webhook bancario Y
  conversación): el bug vivió justo en la vía no probada.
- Antes de "choferes no reciben": `journalctl -u valentina-bridge | grep
  "dispatch_queue"` y `sqlite3 data/conversations.db "SELECT ... FROM
  dispatch_queue ORDER BY id DESC LIMIT 5"` — la cola es la fuente de verdad.

## 🚨 INCIDENTE 10: DOS CEREBROS dessincronizados — menú re-enviado dentro del pedido

**Lección 2026-10-10 (la más importante de la semana):** el híbrido bridge+Dify
tiene DOS dueños de estado (SM del bridge + conversación Dify). Incidente
08:33: turnos "1"/"3 botellones" delegados a Dify SIN avanzar la SM (quedó
`menu_sent`) → la dirección del cliente (08:34:38) cayó en estado viejo →
**menú re-enviado en mitad del pedido** → cliente re-elige → orden duplicada.
Primera respuesta 26s = init lazy del guardrail (~9s, primer mensaje
post-reinicio) + Dify frío (~15s; deepseek directo 0.79s).

### Fix estructural — MISIÓN "CEREBRO ÚNICO" (parches/2026-10-10-prompt-hermes-cerebro-unico.md, PENDIENTE)
- SM del bridge = ÚNICA dueña del flujo; saludo/menú determinísticos <2s
  (cero LLM); camino Dify PROHIBIDO de escribir estado; Dify solo off-menu
  STATELESS; guardrail pre-inicializado en startup; FEATURE FLAG
  `VALENTINA_SINGLE_BRAIN` para rollback; E2E aserta 0 delegaciones a Dify
  en flujo normal.
- Cosmético pendiente: logger del bridge duplica cada línea (dos handlers).

### ⚠️ Reglas
- NINGÚN componente puede escribir estado de otro por heurística — un dueño
  por estado, o dessertincronización garantizada bajo tráfico real.
- Primer contacto de cliente NUNCA debe pagar cold-start de nada (LLM,
  guardrail, pools): init en startup, no lazy.
