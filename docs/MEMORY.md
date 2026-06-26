---
doc: MEMORY
version: 0.1.0
last_updated: 2026-06-25T08:00:00-04:00
updated_by: hermes-agent
---

# MEMORY — Estado vivo del sistema

> 🔄 Hermes Agent actualiza este archivo automáticamente. No editar manualmente.

## Estado actual
- Fase: Fase 0 — Setup infraestructura
- Progreso: 7/14 bloques completados (50%)
- Último bloque completado: 10.7 Docker Compose base
- Próximo bloque: 10.8 Obsidian + Markdown docs (en progreso)

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

## Modelos IA disponibles
- qwen2.5:7b (4.7GB) — Principal Valentina
- qwen2.5:3b (1.9GB) — Reservas
- qwen2.5:7b-instruct-q4_K_M (4.7GB) — Instrucción
- qwen7b-pro (4.7GB) — Backup
- llama3.2:1b (1.3GB) — Rápido
- nomic-embed-text (274MB) — Embeddings mem0

## Eventos recientes
- 2026-06-24 18:51 — Repo Hermes Agent inicializado
- 2026-06-24 19:26 — Dependencias Python instaladas (17 paquetes)
- 2026-06-24 19:30 — Docker Compose base levantado (5 servicios)
- 2026-06-24 19:35 — Prometheus fix permisos + scrape target
- 2026-06-25 08:00 — Reanudación trabajo, FASE A BLOQUE 10.8

## Pendientes críticos
- [ ] BLOQUE 10.8: completar FASE A + FASE B (Obsidian)
- [ ] BLOQUE 10.10: WAHA + WhatsApp
- [ ] BLOQUE 10.11: Core Hermes (fusion, router)
- [ ] BLOQUE 10.12: Valentina + mem0
- [ ] BLOQUE 10.13: Dashboard web
