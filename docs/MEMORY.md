---
doc: MEMORY
version: 2.0.0
last_updated: 2026-07-02
updated_by: prometeo
---

# MEMORY — Estado vivo del sistema

> 🔄 Prometeo actualiza este archivo automáticamente.

## Estado actual
- **Fase**: Fase 1 — Skills + Dify Workflow
- **Progreso**: Dify instalado y conectado a Qwen 2.5 7B local
- **WhatsApp**: Meta Cloud API oficial operativa (+58 422-711-9156)
- **Asistente IA**: Ahora responde por "Prometeo" (arquitecto del sistema)

## Servicios activos
| Servicio | Estado | Puerto |
|----------|--------|--------|
| Docker | ✅ active | — |
| Ollama | ✅ active | 11434 |
| Qdrant | ✅ healthy | 6333 |
| Redis | ✅ healthy | 6379 |
| Prometheus | ✅ healthy | 9090 |
| Grafana | ✅ ok | 3001 |
| Node Exporter | ✅ ok | 9100 |
| Hermes Agent API | ✅ active (systemd) | 8000 |
| Cloudflare Tunnel | ✅ active (systemd) | 80 |
| Dify | ✅ active | 80 |

## Componentes Hermes Agent
- ✅ core/ (8 módulos: config, logger, openrouter, qwen, fusion, judge, router, cost_guard, meta_client)
- ✅ memory/ (mem0 + Qdrant + Qwen local para extracción)
- ✅ agents/valentina.py (hardcore chatbot, no proactiva, 4 botones)
- ✅ skills/ (base, payment, inventory, self_improve)
- ✅ api/main.py (webhook Meta Cloud API con HMAC-SHA256)
- ✅ Dify (instalado, Qwen configurado, pendiente crear workflow visual)

## Eventos recientes
- 2026-07-01 — Meta Cloud API oficial operativa
- 2026-07-01 — Valentina respondiendo en producción (Qwen local)
- 2026-07-02 — Dify instalado y conectado a Qwen 2.5 7B
- 2026-07-02 — Prometeo asume rol de arquitecto del sistema
- 2026-07-02 — Valentina hardcore chatbot (no proactiva, 4 botones)
- 2026-07-02 — Skills implementadas (payment, inventory, self_improve)

## Pendientes
- [ ] Crear Chatflow visual de Valentina en Dify
- [ ] Conectar Dify con WhatsApp Cloud API
- [ ] Migrar número real a Meta Cloud API (cuando Meta desbloquee)
- [ ] Implementar route_skill, analytics_skill, support_skill
- [ ] 5 clientes VIP en producción
