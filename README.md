# Hermes Agent — Estación H2O IA

Orquestador de IA para automatización empresarial de **Estación H2O** (distribución de agua/hielo a domicilio en Maracaibo, Venezuela).

## Arquitectura

- **Workload Routing**: Qwen 2.5 7B local (producción, 0$) + OpenRouter (desarrollo)
- **Fusion Tournament**: 4 modelos compiten + GLM-5.2 juez para decisiones críticas
- **Hot Failover**: VPS espejo (Fase 3)
- **Markdown as Truth**: 8 docs vivos como fuente de verdad

## Stack

- Python 3.12 + FastAPI + SQLite + Ollama + OpenRouter + mem0 + Qdrant
- Docker Compose para servicios base
- Next.js para dashboard web
- WAHA para WhatsApp (con HMAC webhook nativo)

## Setup

Ver `docs/BOOTSTRAP.md` para instrucciones completas.

## Estructura

- `core/` — Orquestador + Workload Router + Fusion
- `agents/` — Agentes productivos (Valentina, Dispatcher, Financial, Notifier)
- `dev/` — Agentes de desarrollo (Architect, Coder, Reviewer)
- `api/` — FastAPI gateway + webhooks
- `db/` — SQLite + migraciones Alembic
- `memory/` — mem0 + Qdrant
- `infra/` — Docker Compose + systemd
- `docs/` — Markdown fuente de verdad + ADRs
- `tests/` — Unit, integration, E2E
- `web/` — Dashboard Next.js

## Licencia

Privado — Uso exclusivo Estación H2O.
