# 📋 RUNBOOK — Guía Operacional

**Última actualización**: 2026-07-05 (Día 13 — Post producción)

---

## 🚀 Deploy inicial (ya ejecutado Día 13)

```bash
# 1. Configurar .env (ya hecho)
cp .env.example config/.env
nano config/.env  # rellenar META_ACCESS_TOKEN, META_APP_SECRET, DIFY_API_KEY

# 2. Desplegar (ya ejecutado)
cd /mnt/ssd_trabajo/hermes-agent
bash deploy.sh

# 3. Fix systemd (ya aplicado)
sudo cp systemd/valentina-bridge.service /etc/systemd/system/
# (versión minimalista, sin hardening excesivo)

# 4. Configurar webhook Meta (ya hecho)
# Callback URL: https://<url-cloudflare>/webhook/meta
# Verify Token: [REDACTED_VERIFY_TOKEN]
# Suscrito a: messages
```

---

## 🔄 Operaciones rutinarias

### Ver estado del bridge
```bash
sudo systemctl status valentina-bridge.service
curl -s http://localhost:8000/health | python3 -m json.tool
```

### Ver logs en vivo
```bash
sudo journalctl -u valentina-bridge.service -f
```

### Ver pedidos en SQLite
```bash
sqlite3 /mnt/ssd_trabajo/hermes-agent/data/conversations.db \
  "SELECT id, phone_hash, product_description, status, datetime(created_at,'unixepoch') FROM orders ORDER BY created_at DESC LIMIT 20;"
```

### Ver conversaciones
```bash
sqlite3 /mnt/ssd_trabajo/hermes-agent/data/conversations.db \
  "SELECT phone_hash, messages_count, datetime(last_seen,'unixepoch') FROM conversations ORDER BY last_seen DESC LIMIT 20;"
```

### Ver métricas Prometheus
```bash
curl -s http://localhost:8000/metrics | grep valentina
```

### Reiniciar bridge
```bash
sudo systemctl restart valentina-bridge.service
```

### Backup SQLite
```bash
mkdir -p backups
cp data/conversations.db backups/conversations-$(date +%Y%m%d-%H%M%S).db
```

---

## 🆘 Kill switch (emergencia)

### Detener Valentina (no responde mensajes)
```bash
sudo systemctl stop valentina-bridge.service
# O crear archivo centinela:
touch /tmp/valentina.kill
```

### Reactivar Valentina
```bash
sudo systemctl start valentina-bridge.service
rm -f /tmp/valentina.kill
```

---

## 🔧 Troubleshooting

### Webhook verification failed
```bash
# Verificar que el bridge responde localmente
curl "http://localhost:8000/webhook/meta?hub.mode=subscribe&hub.verify_token=[REDACTED_VERIFY_TOKEN]&hub.challenge=test"
# Debe devolver: test
```

### Valentina no responde
```bash
# 1. ¿Llega el webhook?
sudo journalctl -u valentina-bridge -n 20 | grep msg_from

# 2. ¿Dify responde?
curl -X POST http://localhost/v1/chat-messages \
  -H "Authorization: Bearer $DIFY_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"inputs":{},"query":"hola","response_mode":"blocking","user":"test"}'

# 3. ¿Meta envía la respuesta?
sudo journalctl -u valentina-bridge -n 20 | grep "Mensaje enviado"
```

### Systemd 226/NAMESPACE
```bash
# Editar unit file sin directivas problemáticas
sudo nano /etc/systemd/system/valentina-bridge.service
# Eliminar: ProtectSystem, ReadWritePaths problemáticos, RestrictNamespaces
sudo systemctl daemon-reload
sudo systemctl restart valentina-bridge.service
```

### Meta 401 (token expirado)
1. Meta Dashboard → System Users → Generate New Token
2. Actualizar `META_ACCESS_TOKEN` en `.env`
3. `sudo systemctl restart valentina-bridge.service`

### Cloudflare URL cambió (tras restart)
```bash
systemctl status cloudflared-tunnel.service | grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com'
# Actualizar Callback URL en Meta Dashboard
```

---

## 📊 Operaciones Fase 2 (próximas)

### Activar Telegram bot (pendiente)
```bash
# 1. Obtener token de @Skynet_27_bot via @BotFather
# 2. Agregar a .env:
echo "TELEGRAM_BOT_TOKEN=xxx" >> config/.env
# 3. Instalar service
sudo cp systemd/telegram-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now telegram-bot.service
```

### Comandos Telegram del Líder
- `/status` — estado bridge
- `/stop` — kill switch
- `/start` — reactivar
- `/orders` — pedidos hoy
- `/logs` — últimos 20 logs
- `/metrics` — métricas del día
- `/help` — ayuda

---

## 💧 Contacto

- **Líder**: Luis Martinez (@elpelon27) — +58 412-256-0720
- **Arquitecto IA**: Prometeo
- **Repo**: https://github.com/elpelon27/EstacionH2OIA
- **WhatsApp Valentina**: +58 422-711-9156
