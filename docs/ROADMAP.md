---
doc: ROADMAP
version: 0.1.0
last_updated: 2026-06-25
updated_by: hermes-agent
---

# ROADMAP — Hoja de ruta Hermes Agent

## Fase 0 — Setup infraestructura (EN PROGRESO)
| Bloque | Estado | Fecha |
|--------|--------|-------|
| 10.1-10.5 Verificación + Docker + Ollama | ✅ | 2026-06-23 |
| 10.6 Repo Hermes Agent | ✅ | 2026-06-24 |
| 10.7 Docker Compose base | ✅ | 2026-06-24 |
| 10.8 Obsidian + Markdown | 🔄 | 2026-06-25 |
| 10.9 Test bots Telegram | ⏸️ | 2026-06-25 |
| 10.10 WAHA + WhatsApp | ⏸️ | 2026-06-25 |
| 10.11 Core Hermes | ⏸️ | 2026-06-26 |
| 10.12 Valentina + mem0 | ⏸️ | 2026-06-26 |
| 10.13 Dashboard Next.js | ⏸️ | 2026-06-27 |
| 10.14 Verificación final | ⏸️ | 2026-06-27 |

## Fase 1 — Hermes Core (Semana 2-3)
- [ ] core/hermes.py
- [ ] core/openrouter_client.py
- [ ] core/qwen_client.py
- [ ] core/fusion.py
- [ ] core/judge.py
- [ ] core/workload_router.py
- [ ] core/cost_guard.py
- [ ] Tests >80% cobertura en core/

## Fase 2 — Agentes productivos (Semana 4-5)
- [ ] agents/valentina.py
- [ ] agents/financial.py
- [ ] agents/dispatcher.py
- [ ] agents/notifier.py
- [ ] memory/memory_client.py
- [ ] api/main.py + webhooks
- [ ] db/schema.py
- [ ] Migraciones Alembic

## Fase 3 — Failover (Semana 6)
- [ ] VPS Hetzner CX32
- [ ] Litestream SQLite
- [ ] Qdrant snapshot 1h
- [ ] Test failover manual

## Fase 4 — Producción (Semana 7-8)
- [ ] Soft launch 5 clientes VIP
- [ ] Monitoreo intensivo
- [ ] Kill switch + failback
- [ ] Runbook 10 incidentes
- [ ] Video handover

## Fase 5 — Estabilización (Mes 3)
- [ ] Launch completo
- [ ] Hermes autodesarrollo controlado
- [ ] Métricas objetivo
- [ ] Plan escalabilidad 1000-3000/mes
