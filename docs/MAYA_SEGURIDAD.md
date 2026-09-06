# MAYA DE SEGURIDAD — Estación H2O / Hermes

Sistema de protección contra cortes eléctricos y errores humanos.
Implementado 2026-09-03. 4 fases, 3 grietas cerradas.

## Resumen de fases

| Fase | Mecanismo | Grieta que cierra |
|------|-----------|------------------|
| 0 | Snapshots automáticos cada 2 min + tags safety-* | Sin puntos de restauración frecuentes |
| 1 | Push automático post-commit + cron push + backup USB externo | Todo vivía en 1 SSD |
| 2 | Checkpoint de tarea + branches de seguridad + limpieza de tags | Sin restauración identificable |
| 3 | Health check post-corte (systemd) + hook pre-commit crítico | Sin verificación de integridad |
| 4 | Rollback instantáneo no destructivo | Sin comando simple de recuperación |

## Comandos disponibles

| Comando | Función |
|---------|---------|
| `/home/skynet/snapshot_hermes.sh` | Snapshot manual (commit + tag safety-*) |
| `/home/skynet/before_change.sh <tarea>` | Branch de seguridad antes de cambio |
| `/home/skynet/backup_externo.sh` | Backup USB (repo + biblioteca) |
| `/home/skynet/health_check.sh` | Verificación de integridad → health_report.txt |
| `/home/skynet/rollback_hermes.sh [target]` | Rollback no destructivo. Sin args: último tag safety-*. Número: N commits atrás. Tag específico: safety-XXXX |
| `/home/skynet/limpiar_tags.sh` | Mantiene últimos 100 tags safety-* |

## Crons activos

| Horario | Tarea |
|---------|-------|
| */2 * * * * | Snapshot automático (commit + tag safety-* + push) |
| */10 * * * * | git push (respaldo si el hook falla) |
| 0 4 * * * | Backup USB diario |
| 0 23 * * * | Ingest de PDFs (nocturno) |
| 0 3 * * 0 | Limpieza de tags viejos (semanal) |

## Flujos de datos cubiertos por snapshots + push auto

- **Código y docs** (todo el repo, incluido `skills/claude-watch/`).
- **Skill de videos** (ver docs/VIDEO_SKILL_SETUP.md): los outputs
  `docs/videos/*.md|*.json` y el espejo `obsidian-vault/videos/*.md`
  viven en el repo → quedan cubiertos por el snapshot de 2 min y el
  push automático post-commit. Un video procesado queda preservado en
  GitHub (off-site) a lo sumo 2 minutos después de generarse. La
  memoria semántica (Qdrant videos_h2o) NO está en el repo, pero es
  re-construible re-ejecutando el pipeline (point IDs UUID5
  determinísticos → re-index sin duplicar).

## Servicios systemd

| Servicio | Función |
|----------|---------|
| hermes-health-check | Health check al arranque del sistema (reporte: /home/skynet/health_report.txt) |
| prometeo-telegram | Bot Telegram, auto-restart on-failure |
| open-notebook | Puerto 8502, auto-restart on-failure |
| backup-daily | Backup de DBs SQLite 3 AM (SSD local) |

## Reglas de uso

- **Ollama NUNCA para tareas técnicas** — solo chat/embeddings ligeros.
- **Hook pre-commit NO usar --no-verify en commits de desarrollo** — el gate de sintaxis (py_compile) debe correr en main/feat/*.
- **Snapshots automáticos SÍ pueden usar --no-verify** — son commits de seguridad, no de desarrollo.
- Regla 3-2-1 verificada: 3 copias (SSD + USB + GitHub), 2 medios (local + USB físico), 1 off-site (GitHub).

## Arquitectura de recuperación

Si algo se rompe:

1. Correr `/home/skynet/health_check.sh` y leer /home/skynet/health_report.txt
2. Si hay tarea interrumpida (⚠ en reporte), retomar desde .hermes/state/current_task.json
3. Para deshacer cambios: `/home/skynet/rollback_hermes.sh` (conserva lo descartado en branch recovery/*)
4. Para restaurar algo específico: `git cherry-pick <commit>` desde branch recovery/*

Si el SSD muere:

1. Clonar desde GitHub: `git clone https://github.com/elpelon27/EstacionH2OIA.git`
2. Restore de datos desde USB: /media/skynet/"Nuevo vol"/hermes-backup/
3. Recrear venv y servicios systemd (scripts en systemd/ y scripts/safety/ del repo)
