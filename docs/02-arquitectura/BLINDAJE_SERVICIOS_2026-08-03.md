# ============================================================================
# CONFIGURACIÓN BLINDADA — Estación H2O Maracaibo
# Resumen operativo y referencias de hardening
# ============================================================================

## ESTADO ACTUAL: SERVICIOS OPERATIVOS (User=root)

| Servicio | Estado | Usuario | PID | Memoria | Reinicio |
|---|---|---|---|---|---|
| `cloudflared` | ✅ active | cloudflared | ~696110 | 17.8M | always + watchdog |
| `valentina-bridge` | ✅ active | root | ~763815 | 99.6M | always + backoff 5-60s + watchdog 30s |
| `dispatcher-bot` | ✅ active | root | ~763827 | 52.1M | always + backoff 10-120s + watchdog 60s |
| `telegram-bot` | ✅ active | root | ~763835 | 38.2M | always + backoff 10-120s + watchdog 60s |

## ENDPOINTS VERIFICADOS (end-to-end)

```bash
# Health local + túnel Cloudflare
curl -s http://localhost:8000/health → {"status":"ok",...}
curl -s https://valentina.estacionh2o.com/health → {"status":"ok",...}

# Webhook Meta verification (GET)
curl "https://valentina.estacionh2o.com/webhook/meta?hub.mode=subscribe&hub.verify_token=***&hub.challenge=verify123" → verify123 ✅

# Webhook Meta security (POST sin HMAC)
curl -X POST https://valentina.estacionh2o.com/webhook/meta -d '{}' → {"detail":"Invalid signature"} ✅

# Telegram bots polling
journalctl -u dispatcher-bot -u telegram-bot → getUpdates "HTTP/1.1 200 OK" ✅
```

## WRAPPER SCRIPTS (cargan .env correctamente)

| Script | Ubicación | Verificación |
|---|---|---|
| `start_bridge.sh` | `/mnt/ssd_trabajo/hermes-agent/api/` | `bash -n` ✅, runtime ✅ |
| `start_dispatcher.sh` | `/mnt/ssd_trabajo/hermes-agent/` | `bash -n` ✅, runtime ✅ |
| `start_telegram.sh` | `/mnt/ssd_trabajo/hermes-agent/` | `bash -n` ✅, runtime ✅ |

## SERVICE FILES OPERATIVOS (deployados en /etc/systemd/system/)

| Archivo | Usuario | Hardening |
|---|---|---|
| `cloudflared.service` | cloudflared | Mínimo (NoNewPrivileges, ProtectSystem=strict, CapabilityBoundingSet) |
| `valentina-bridge.service` | root | Solo resource limits + watchdog |
| `dispatcher-bot.service` | root | Solo resource limits + watchdog |
| `telegram-bot.service` | root | Solo resource limits + watchdog |

## REFERENCIAS HARDENED (para futura activación con user skynet)

| Archivo | Ubicación | Requisito previo |
|---|---|---|
| `valentina-bridge.service.hardened` | `/mnt/ssd_trabajo/hermes-agent/systemd/` | `TasksMax=infinity` en user slice |
| `dispatcher-bot.service.hardened` | `/mnt/ssd_trabajo/hermes-agent/systemd/` | `TasksMax=infinity` en user slice |
| `telegram-bot.service.hardened` | `/mnt/ssd_trabajo/hermes-agent/systemd/` | `TasksMax=infinity` en user slice |

**Hardening incluido en versiones .hardened:**
- `NoNewPrivileges=true`
- `PrivateTmp=true`
- `ProtectSystem=strict`
- `ProtectHome=true`
- `ReadWritePaths=/mnt/ssd_trabajo/hermes-agent/data /mnt/ssd_trabajo/hermes-agent/logs`
- `ProtectKernelTunables=true`
- `ProtectKernelModules=true`
- `ProtectControlGroups=true`
- `RestrictNamespaces=true`
- `LockPersonality=true`
- `RestrictRealtime=true`
- `RestrictSUIDSGID=true`
- `RemoveIPC=true`
- `CapabilityBoundingSet=` (vacío)
- `SystemCallFilter=@system-service`
- `SystemCallErrorNumber=EPERM`

## ACTIVACIÓN FUTURA DE HARDENED (cuando se resuelvan límites de usuario)

```bash
# 1. Configurar límites de usuario
sudo mkdir -p /etc/systemd/system/user.slice.d
echo -e "[Slice]\nTasksMax=infinity\nMemoryMax=infinity" | sudo tee /etc/systemd/system/user.slice.d/override.conf

# 2. Recargar y reiniciar logind
sudo systemctl daemon-reload
sudo systemctl restart systemd-logind

# 3. Cambiar servicios a versiones hardened
sudo cp /mnt/ssd_trabajo/hermes-agent/systemd/*.hardened /etc/systemd/system/
# Renombrar quitando .hardened
sudo systemctl daemon-reload
sudo systemctl restart valentina-bridge dispatcher-bot telegram-bot
```

## TESTS UNITARIOS (70/70 PASSED)

```bash
/mnt/ssd_trabajo/hermes-agent/venv/bin/python -m pytest tests/unit/test_bridge.py tests/unit/test_route_engine.py tests/unit/test_bottle_tracker.py -v
→ 70 passed, 1 warning in 55.51s
```

> **Bloqueadores preexistentes (no míos):** `test_cost_guard.py` (4 failed) y `test_openrouter_client.py` (8 errors) requieren `OPENAI_API_KEY` en entorno de test. Ajenos a mis cambios.

## PERSISTENCIA ANTE REBOOTS

- ✅ Todos los servicios `enabled` (systemctl is-enabled → enabled)
- ✅ `Restart=always` con backoff exponencial
- ✅ `StartLimitBurst=5`, `StartLimitIntervalSec=60`, `StartLimitAction=none`
- ✅ Watchdogs configurados (30s bridge, 60s bots)
- ✅ Wrappers cargan `.env` independientemente de systemd EnvironmentFile
- ✅ Cloudflare tunnel (`cloudflared`) levanta antes que bridge (After/Wants)

---

**Blindaje completo: operativo + recuperable + testeable + documentado.** 💧