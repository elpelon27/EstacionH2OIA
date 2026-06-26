# ADR-004: Markdown as Truth

**Estado**: Aceptado
**Fecha**: 2026-06-25

## Contexto
Sistema anterior tenía documentación aspiracional (MEMORY.md decía "100% operativo" con 4,498 reinicios).

## Decisión
8 documentos Markdown vivos como única fuente de verdad:
- BOOTSTRAP.md — plano maestro
- MEMORY.md — estado vivo (Hermes actualiza auto)
- ROADMAP.md — hoja de ruta
- RUNBOOK.md — incidentes comunes
- HEARTBEAT.md — log de salud (Hermes actualiza auto)
- SOUL.md — personalidad Valentina (solo Líder)
- USER.md — perfil Líder (solo Líder)
- AGENTS.md — catálogo agentes

## Consecuencias
**Positivas**:
- Transparencia total
- Versionado semver
- Editable por humano (Obsidian) Y máquina (Hermes)

**Negativas**:
- Requiere disciplina de edición

## Reglas de edición
- Hermes actualiza MEMORY.md y HEARTBEAT.md automáticamente
- Hermes propone cambios a ROADMAP.md, RUNBOOK.md, AGENTS.md vía PR
- Hermes NO toca SOUL.md, USER.md (solo lectura)
- Cualquier cambio a BOOTSTRAP.md o ADRs requiere OK verbal del Líder
