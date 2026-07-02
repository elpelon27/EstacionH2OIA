---
doc: ROADMAP
version: 2.0.0
last_updated: 2026-07-02
updated_by: prometeo
---

# ROADMAP — Hoja de ruta Estación H2O

## Fase 0 — Setup infraestructura ✅ COMPLETADA
- ✅ 10.1-10.5 Setup base + Docker + Ollama
- ✅ 10.6 Repo Hermes Agent
- ✅ 10.7 Docker Compose base (5 servicios)
- ✅ 10.8 Obsidian + Markdown docs
- ✅ 10.9 Meta Cloud API (reemplazó WAHA)
- ✅ 10.10 Core Hermes (8 módulos, 91 tests)
- ✅ 10.11 Valentina + mem0 + API Gateway
- ✅ Systemd blindaje (auto-arranque)
- ✅ Cloudflare Tunnel (HTTPS público)
- ✅ Skills básicas (payment, inventory, self_improve)

## Fase 1 — Dify + Workflow Visual 🔄 EN PROGRESO
- [ ] Crear Chatflow de Valentina en Dify
- [ ] Conectar Dify con WhatsApp Cloud API
- [ ] Probar workflow end-to-end
- [ ] 5 clientes VIP en producción

## Fase 2 — Skills Operativas
- [ ] route_skill.py (Haversine + 5 zonas Maracaibo)
- [ ] analytics_skill.py (reporte diario 7am Telegram)
- [ ] support_skill.py (FAQ RAG con Qdrant)
- [ ] dispatcher.py (agente logística Telegram)

## Fase 3 — Estabilización
- [ ] Métrica: >70% conversaciones sin humano
- [ ] Eliminar Node.js legacy
- [ ] ADR-007: Skills sobre multi-agente
- [ ] Dominio propio para Cloudflare Tunnel

## Fase 4 — Crecimiento
- [ ] Migrar a número real (+58 412-2560721)
- [ ] Publicar App en Meta (verificación negocio)
- [ ] Plan escalabilidad 1,000-3,000 consultas/mes
