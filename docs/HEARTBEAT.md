# 💓 HEARTBEAT — Estado del Sistema en Vivo

**Última actualización**: 2026-07-05 22:30 -04
**Próxima actualización automática**: cada hora (pendiente cron)

---

## 🟢 Estado general: OPERATIONAL

| Componente | Estado | Detalle |
|-----------|--------|---------|
| valentina-bridge.service | 🟢 active (running) | uptime ~30 min |
| cloudflared-tunnel.service | 🟢 active (running) | URL strip-occupations-purple-scholars |
| ollama.service | 🟢 active (running) | qwen2.5:7b cargado |
| Dify (12 contenedores) | 🟢 all running | http://localhost |
| Qdrant | 🟢 up | puerto 6333 |
| Redis | 🟢 up | puerto 6379 |
| Prometheus | 🟢 up | puerto 9090 |
| Grafana | 🟢 up | puerto 3001 |
| Webhook Meta | 🟢 verificado | suscrito a messages |
| Telegram bot | 🔴 pendiente | TELEGRAM_BOT_TOKEN vacío |
| Google Sheets | 🟡 al 90% | falta google_credentials.json |

---

## 📊 Métricas de hoy (Día 13)

- **Mensajes procesados**: 6 (1 conversación)
- **Pedidos confirmados**: 1 (primer cliente real)
- **Tasa de éxito**: 100% (6/6)
- **Latencia promedio**: 3-5s
- **Errores**: 0
- **Deduplicados**: 0
- **Escalamientos humano**: 0

---

## 🎯 Próximas verificaciones automáticas (pendiente cron)

```bash
# Agregar a crontab -e:
* * * * * curl -sf http://localhost:8000/health > /dev/null || echo "Valentina DOWN" >> /var/log/valentina-alerts.log
0 * * * * /mnt/ssd_trabajo/hermes-agent/venv/bin/python /mnt/ssd_trabajo/hermes-agent/skills/self_improve_skill.py
0 3 * * * cp /mnt/ssd_trabajo/hermes-agent/data/conversations.db /mnt/ssd_trabajo/backups/conversations-$(date +\%Y\%m\%d).db
```

---

## 🔔 Alertas activas

| Severidad | Alerta | Trigger | Estado |
|-----------|--------|---------|--------|
| 🔴 crítica | Bridge down | /health != 200 por 1 min | 🟢 no activa |
| 🔴 crítica | Dify caído | dify_error rate > 50% en 5 min | 🟢 no activa |
| 🟡 alta | Meta 401 | token expirado | 🟢 no activa |
| 🟢 info | Pedido confirmado | cada pedido | 🟢 1 hoy |
| 🟢 info | Rate limit hit | cliente > 30 msg/min | 🟢 no activa |

---

## 📈 Tendencia (cuando tengamos más datos)

| Día | Mensajes | Pedidos | Tasa éxito | Latencia |
|-----|----------|---------|------------|----------|
| 13 | 6 | 1 | 100% | 3-5s |

---

**Este archivo se actualiza automáticamente cuando el cron job esté activo.**
