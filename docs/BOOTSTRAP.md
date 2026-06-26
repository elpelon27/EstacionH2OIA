---
doc: BOOTSTRAP
version: 1.0.0
last_updated: 2026-06-25
updated_by: lider
---

# BOOTSTRAP — Plano maestro Hermes Agent

> Documento extenso (1241 líneas). Copia completa disponible en sandbox Z.ai:
> /home/z/my-project/upload/HERMES-AGENT-BOOTSTRAP.md

## Resumen
Plano de ruta maestro para Hermes Agent — Estación H2O / Valentina Proactiva.

## Principios arquitectónicos
1. Workload Routing (Qwen local + OpenRouter)
2. Fusion Tournament (4 modelos + GLM-5.2 juez)
3. Hot Failover 8 min (Fase 3)
4. Markdown as Truth (8 docs vivos)
5. TDD Automático
6. Cost-Aware ($5/$15 OpenRouter)
7. Defense in Depth (HMAC + rate limit + kill switch)
8. Human-in-the-Loop (OK verbal para deploys)

## Stack
- Python 3.12 + FastAPI + SQLite + Ollama + OpenRouter + mem0 + Qdrant
- Docker Compose + systemd
- Next.js 16 para dashboard
- WAHA para WhatsApp (HMAC nativo)
- Obsidian para edición Markdown

## Ver también
- docs/ROADMAP.md — estado actual
- docs/adr/ — decisiones arquitectónicas
- docs/SOUL.md — personalidad Valentina
- docs/USER.md — perfil del Líder
