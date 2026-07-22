# 📓 BOOTSTRAP — Estación H2O

**Última actualización**: 2026-07-05 (Día 13)
**Estado**: ✅ Producción real alcanzada

---

## 🎯 Qué es esto

Documento maestro del proyecto. Punto de entrada para cualquier sesión.

**Cómo retomar tras corte**:
```
CONTINUAR PROMETEO — Estación H2O
Leí /home/z/my-project/upload/MASTER_MEMORY_CELL_PROMETEO.md
y /home/z/my-project/upload/CIERRE_JORNADA_2026-07-05.md
Estado: [describir dónde quedamos]
```

---

## 📋 Contexto

- **Negocio**: Estación H2O — distribución de agua y hielo en Maracaibo, Venezuela
- **Líder**: Luis Martinez (@elpelon27) — +58 412-256-0720
- **Arquitecto IA**: Prometeo
- **Servidor**: skynet-System-product-name (Maracaibo)
- **Repo**: https://github.com/elpelon27/EstacionH2OIA
- **WhatsApp Valentina**: +58 422-711-9156
- **Horario**: Lun-Sáb 8am-6pm

---

## 🏗️ Stack tecnológico (confirmado en producción)

- **Framework**: FastAPI + uvicorn (Python 3.12)
- **IA**: qwen2.5:7b via Ollama (local, 0$)
- **WhatsApp**: Meta Cloud API oficial (graph.facebook.com/v25.0)
- **Workflow**: Dify 1.15.0 (modo Chatbot con pre_prompt)
- **Tunnel**: Cloudflare Tunnel (HTTPS público sin abrir puertos)
- **DB**: SQLite (conversaciones + pedidos) + Google Sheets (persistencia compartida)
- **Observabilidad**: Prometheus + Grafana
- **Alertas**: Telegram bot (pendiente activar)
- **Systemd**: valentina-bridge.service + telegram-bot.service (pendiente)

---

## 📂 Estructura del repo en servidor

```
/mnt/ssd_trabajo/hermes-agent/
├── api/bridge.py              # Puente FastAPI (v1.2.0 — GPS + Sheets)
├── config/.env                # Secrets (NO commitear)
├── config/google_credentials.json  # Service account Google (pendiente descargar)
├── data/conversations.db      # SQLite conversaciones + pedidos
├── skills/
│   ├── google_sheets.py       # Integración Google Sheets (17 columnas)
│   ├── telegram_bot.py        # Kill switch + alertas
│   └── self_improve_skill.py  # Análisis nocturno 10pm
├── systemd/
│   ├── valentina-bridge.service
│   └── telegram-bot.service
├── tests/test_bridge.py       # 16 tests pytest
├── venv/                      # Python 3.12 virtualenv
├── .env.example               # Template 17 variables
├── requirements.txt           # 11 dependencias pinned
├── Makefile                   # 12 comandos
├── deploy.sh                  # Despliegue automático
├── 02-arquitectura/RUNBOOK-operacional.md  # Guía 6 pasos
└── README.md                  # Arquitectura + 7 ADRs
```

---

## 🗺️ Documentos vivos (8 Markdown en Obsidian)

| Doc | Propósito | Frecuencia actualización |
|-----|-----------|--------------------------|
| `01-proyecto/BOOTSTRAP.md` | Este archivo — punto de entrada | Cada sesión |
| `05-tech-debt/MEMORY-celda.md` | Celda de memoria maestra | Cada sesión |
| `02-arquitectura/ROADMAP-plan.md` | Plan de trabajo reciclado | Tras cada hito |
| `02-arquitectura/RUNBOOK-operacional.md` | Guía operacional 6 pasos | Cuando cambia deploy |
| `02-arquitectura/HEARTBEAT.md` | Estado del sistema en vivo | Automático cada hora |
| `01-proyecto/SOUL-valentina.md` | Personalidad de Valentina | Solo si cambia prompt |
| `01-proyecto/USER-lider.md` | Perfil del Líder | Cambios de contacto |
| `01-proyecto/AGENTS-catalogo.md` | Catálogo de agentes/skills | Al añadir skill nueva |

---

## 🚀 Estado actual (Día 13)

✅ **Valentina en producción real** — primer cliente atendido 2026-07-04 22:25  
⏸️ **Google Sheets al 90%** — falta descargar `google_credentials.json`  
⏸️ **Telegram bot** — pendiente `TELEGRAM_BOT_TOKEN`  
⏸️ **Skills Fase 2** — bloqueadas por Google Sheets

**Próximo paso**: Descargar credenciales Google Sheets (15 min).

---

## 🔗 Enlaces rápidos

- **Meta Dashboard**: https://developers.facebook.com/apps/975863248739508/
- **Google Sheet Pedidos**: https://docs.google.com/spreadsheets/d/1Bbp4Xqw5E7bb7loJ262K9lMPFinNSIW-ws1i7ZAmiYk/edit
- **Google Cloud Console**: https://console.cloud.google.com/iam-admin/serviceaccounts?project=valentina-h2o
- **Dify local**: http://localhost (servidor Maracaibo)
- **Bridge health**: http://localhost:8000/health
- **Bridge metrics**: http://localhost:8000/metrics

---

**Prometeo mantiene el rumbo. Líder decide el norte.**
