---
doc: RUNBOOK
version: 0.1.0
last_updated: 2026-06-25
updated_by: hermes-agent
---

# RUNBOOK — Incidentes comunes + solución

## Incidente 1: Sesión WhatsApp cae
**Síntoma**: WAHA no recibe mensajes
**Diagnóstico**:
docker logs hermes_waha --tail 50
curl -s http://localhost:3000/api/sessions/estacionh2o_main | jq .status

**Resolución**:
curl -X POST http://localhost:3000/api/sessions/estacionh2o_main/start -H "X-Api-Key: $WAHA_API_KEY"
# Si no funciona:
docker restart hermes_waha

## Incidente 2: Hermes Agent no responde
**Síntoma**: API 500 o timeout
**Diagnóstico**:
sudo systemctl status hermes-agent
sudo journalctl -u hermes-agent --since "1 hour ago" | tail -50

**Resolución**:
sudo systemctl restart hermes-agent

## Incidente 3: Ollama no responde
**Síntoma**: Qwen tarda >30s o no responde
**Resolución**:
sudo systemctl restart ollama
sleep 10
ollama run qwen2.5:7b "test"

## Incidente 4: OpenRouter 429 (rate limit)
**Resolución**: Esperar 60s. Si persiste, fallback automático a Qwen local.

## Incidente 5: Disco M2 lleno
**Diagnóstico**:
df -h /mnt/ssd_trabajo
du -sh /mnt/ssd_trabajo/* | sort -hr | head -10

**Resolución**:
docker system prune -af --volumes
sudo journalctl --vacuum-time=3d
find /mnt/ssd_trabajo/backups -mtime +30 -delete

## Incidente 6: Qdrant no responde
docker restart hermes_qdrant
sleep 10
curl http://localhost:6333/healthz

## Incidente 7: Telegram bot no envía alertas
curl -s "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN_HERMES/getMe" | jq .
# Si getMe falla: token revocado, generar nuevo con @BotFather

## Incidente 8: Gasto OpenRouter > $15/día
# Verificar en https://openrouter.ai/credits
# Si abuso: /kill vía Telegram
# Aumentar umbral en .env si es legítimo

## Incidente 9: GPU no detectada
sudo ubuntu-drivers autoinstall
sudo reboot

## Incidente 10: Perdí mi password de skynet
# En GRUB, presionar 'e' en entrada Ubuntu
# Añadir 'init=/bin/bash' después de 'linux ...'
# Ctrl+X, luego:
mount -o remount,rw /
passwd skynet
exec /sbin/init
