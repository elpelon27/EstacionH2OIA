# 📓 INDEX — Vault Obsidian Estación H2O

**Vault**: `/home/z/my-project/upload/obsidian-vault/`  
**Sandbox mirror**: copiar a `/mnt/ssd_trabajo/hermes-agent/docs/` en servidor  
**Última actualización**: 2026-07-05 (Día 13)

---

## 📚 8 Markdown vivos (fuente única de verdad)

| # | Doc | Propósito | Frecuencia actualización |
|---|-----|-----------|--------------------------|
| 1 | `BOOTSTRAP.md` | Punto de entrada, contexto general | Cada sesión |
| 2 | `MEMORY.md` | Celda memoria maestra, estado proyecto | Cada sesión |
| 3 | `ROADMAP.md` | Plan de trabajo reciclado, próximos pasos | Tras cada hito |
| 4 | `RUNBOOK.md` | Guía operacional, troubleshooting | Cuando cambia deploy |
| 5 | `HEARTBEAT.md` | Estado del sistema en vivo | Automático cada hora (cron) |
| 6 | `SOUL.md` | Personalidad y prompt de Valentina | Solo si cambia prompt |
| 7 | `USER.md` | Perfil del Líder, preferencias | Cambios de contacto |
| 8 | `AGENTS.md` | Catálogo de agentes/skills | Al añadir skill |

---

## 🗂️ Documentos adicionales (fuera del vault)

| Doc | Ubicación | Propósito |
|-----|-----------|-----------|
| `CIERRE_JORNADA_2026-07-03.md` | `/upload/` | Cierre sesión día 12 |
| `CIERRE_JORNADA_2026-07-05.md` | `/upload/` | Cierre sesión día 13 (HOY) |
| `ROADMAP_VIVO.md` | `/upload/` | Versión extendida del roadmap |
| `MASTER_MEMORY_CELL_PROMETEO.md` | `/upload/` | Celda memoria (copia espejo de MEMORY.md) |
| `HERMES-AGENT-BOOTSTRAP.md` | `/upload/` | Plano maestro día 12 (1241 líneas) |
| `COMMIT_SUMMARY.md` | `/upload/` | Resumen commit GitHub próximo |
| `worklog.md` | raíz sandbox | Histórico completo (~1400 líneas) |

---

## 🚀 Cómo usar este vault

### Al iniciar sesión:
1. Lee `BOOTSTRAP.md` (punto de entrada)
2. Lee `MEMORY.md` (estado actual)
3. Lee el último `CIERRE_JORNADA_*.md`
4. Lee `ROADMAP.md` (próximos pasos)

### Al cerrar sesión:
1. Actualiza `MEMORY.md` con nuevo estado
2. Actualiza `ROADMAP.md` si cambiaron próximos pasos
3. Crea nuevo `CIERRE_JORNADA_YYYY-MM-DD.md`
4. Actualiza `HEARTBEAT.md` con métricas del día
5. Si cambia el prompt: actualiza `SOUL.md`
6. Si añades skill: actualiza `AGENTS.md`

### En servidor Maracaibo:
```bash
# Sincronizar vault (copia del sandbox al servidor)
scp -r /home/z/my-project/upload/obsidian-vault/* \
  skynet@servidor:/mnt/ssd_trabajo/hermes-agent/docs/
```

---

## 🔗 Tags Obsidian sugeridos

- `#valentina` — todo lo relacionado con la recepcionista
- `#produccion` — cosas en producción real
- `#fase-1`, `#fase-2`, `#fase-3` — por fase del roadmap
- `#bug-fix` — lecciones aprendidas de bugs
- `#adr` — architecture decision records
- `#skill` — skills nuevas o modificadas
- `#deploy` — operaciones de deploy
- `#cierre-jornada` — resúmenes de sesión

---

## 💧 Filosofía del vault

> *"Los Markdown vivos son la única fuente de verdad. Si no está en el vault, no existe. Si está en el vault, está actualizado." — Prometeo*

**Reglas**:
1. Si cambias código → actualiza `RUNBOOK.md` y `AGENTS.md`
2. Si cambias prompt → actualiza `SOUL.md`
3. Si cierras sesión → crea `CIERRE_JORNADA_*.md` + actualiza `MEMORY.md`
4. Si añades skill → actualiza `AGENTS.md` + `ROADMAP.md`
5. Si aprendes una lección → actualiza `MEMORY.md` (sección lecciones)

---

**Mantenido por**: Prometeo (arquitecto IA)  
**Aprobado por**: Luis Martinez (Líder)
