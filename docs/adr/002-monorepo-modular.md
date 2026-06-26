# ADR-002: Monorepo modular

**Estado**: Aceptado
**Fecha**: 2026-06-25

## Contexto
10+ agentes + core + api + db + tests. ¿Mono o multi-repo?

## Decisión
Monorepo modular con directorios:
- core/ — Orquestador + Workload Router + Fusion
- agents/ — Agentes productivos (Qwen local)
- dev/ — Agentes de desarrollo (OpenRouter)
- api/ — FastAPI gateway + webhooks
- db/ — SQLite + migraciones Alembic
- memory/ — mem0 + Qdrant
- infra/ — Docker Compose + systemd
- docs/ — Markdown fuente de verdad + ADRs
- tests/ — Unit, integration, E2E
- web/ — Dashboard Next.js

## Consecuencias
**Positivas**:
- 1 operador, simplifica deploys
- Tests E2E simples
- Refactors cross-module fáciles

**Negativas**:
- Repo grande (manejable con .gitignore)

## Alternativas
- Multi-repo: overhead de sincronización innecesario
