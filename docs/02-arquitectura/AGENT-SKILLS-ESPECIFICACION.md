# Especificación Agent Skills (agentskills.io)

> Fuente: clon local en `/mnt/ssd_trabajo/repos/agentskills` (spec oficial, open standard, original de Anthropic, Apache 2.0 / CC-BY-4.0).
> Especificación formal: `docs/specification.mdx` — Guías: `docs/skill-creation/` (quickstart, best-practices, using-scripts, optimizing-descriptions, evaluating-skills).

## Qué es la especificación Agent Skills

Formato abierto y ligero para extender agentes IA con conocimiento especializado y workflows reproducibles. Un skill es simplemente **una carpeta con un `SKILL.md`** (metadatos + instrucciones). Portables entre agentes compatibles (Claude Code, VS Code/Copilot, OpenAI Codex, etc.): se construye una vez y funciona en cualquier cliente que implemente el estándar.

Funciona por **disclosure progresivo** (3 etapas):

1. **Discovery**: al arrancar, el agente carga solo `name` + `description` de cada skill (~100 tokens c/u) — basta para saber cuándo es relevante.
2. **Activation**: si la tarea matchea la `description`, carga el cuerpo completo del `SKILL.md` (< 5000 tokens recomendado).
3. **Execution**: el agente sigue las instrucciones y carga archivos extra (`scripts/`, `references/`, `assets/`) solo cuando los necesita.

## Estructura estándar de un skill

```
my-skill/
├── SKILL.md          # REQUERIDO: frontmatter YAML + cuerpo Markdown
├── scripts/          # Opcional: código ejecutable, autocontenido
├── references/       # Opcional: documentación técnica (REFERENCE.md, etc.)
├── assets/           # Opcional: plantillas, imágenes, datos
└── ...               # Cualquier archivo adicional
```

### Frontmatter (campos)

| Campo | Requerido | Restricciones |
|---|---|---|
| `name` | Sí | ≤64 chars, solo `[a-z0-9-]`, sin empezar/terminar en `-`, sin `--` consecutivos, **debe coincidir con el nombre del directorio** |
| `description` | Sí | ≤1024 chars. Qué hace + cuándo usarlo, con keywords de trigger |
| `license` | No | Nombre o referencia a LICENSE bundleado |
| `compatibility` | No | ≤500 chars. Requisitos de entorno (producto destino, paquetes, red) |
| `metadata` | No | Mapa libre string→string (author, version…) |
| `allowed-tools` | No | Tools pre-aprobadas, separadas por espacio (experimental) |

Mínimo viable:

```markdown
---
name: skill-name
description: Qué hace y cuándo usarlo.
---
```

### Reglas de cuerpo

- Sin restricciones de formato; secciones recomendadas: pasos, ejemplos I/O, casos borde.
- **< 500 líneas** el SKILL.md; el detalle va a `references/` (u `assets/`), referenciado con **rutas relativas al root del skill y un nivel de profundidad**.
- Referencias condicionales: "lee `references/api-errors.md` si la API devuelve non-200" — no un genérico "ver references/".
- Validación con la librería de referencia: `skills-ref validate ./my-skill` (en `skills-ref/` del repo clonado).

### Buenas prácticas clave (docs/skill-creation/best-practices)

- **Partir de experiencia real** (runbooks, incidentes, correcciones hechas al agente), no de conocimiento genérico del LLM.
- **Refinar con ejecución real**: iterar sobre traces, capturar falsos positivos. Cada corrección al agente → sección **Gotchas**.
- **Gastar contexto con criterio**: solo lo que el agente NO sabría por sí solo (convenciones del proyecto, gotchas, APIs específicas).
- **Defaults, no menús**: una herramienta por defecto + escape hatch, no listas de opciones equivalentes.
- **Calibrar control**: prescriptivo donde es frágil; libertad + el "por qué" donde tolera variación.
- **Procedimientos sobre declaraciones**: enseñar el método general, no la respuesta puntual.
- Patrones: Gotchas, plantillas de output (templates concretos > prosa), checklists multi-paso, validation loops (hacer → validar → corregir → repetir), plan-validate-execute para operaciones destructivas.

## Cómo aplicarlo a nuestros skills (meta-business-guru, r4-conecta-integration, valentina-bridge-infra, etc.)

Estado actual: los skills de Hermes ya usan la convención core (carpeta + SKILL.md + frontmatter YAML con `name`/`description` + `scripts/`/`references/`), así que **ya son compatibles con el estándar en lo esencial**. La especificación oficial es el subconjunto portable; Hermes añade campos extra (`version`, `author`, `platforms`, `metadata.hermes.*`) que encajan en el campo abierto `metadata` del estándar.

Acciones para alinear 100%:

1. **`name` == nombre de directorio** — verificar en cada skill existente (regla dura de la spec; `skills-ref validate` lo comprueba).
2. **`description` con keywords de trigger** — la spec permite hasta 1024 chars y espera "qué hace + cuándo usarlo" (ej: "R4 Conecta (MiBanco) gateway: HMAC auth, BCV rate, 401 di…"). Nuestro límite interno de 60 chars es un estándar propio; en skills pensadas para portar fuera de Hermes, usar la forma extendida de la spec.
3. **Migrar detalle a `references/` + triggers condicionales** — los SKILL.md gruesos (p.ej. [[Meta-Business-Guru]]) deberían quedar con el procedimiento núcleo (< 500 líneas) y mover tablas de endpoints/códigos de error a `references/` con instrucción de cuándo cargar cada archivo.
4. **Gotchas** — mover los "pitfalls" dispersos a una sección Gotchas al estilo spec (correcciones concretas, no consejos genéricos): p.ej. los 401 de R4 ([[R4-DATOS-INTERCAMBIO]]), comandos de recuperación del bridge ([[RUNBOOK-operacional]]).
5. **Scripts autocontenidos en `scripts/`** con mensajes de error útiles — valida con `skills-ref validate` antes de considerar portable.
6. **Campos de portabilidad**: usar `compatibility` para dependencias (p.ej. "Requires Python 3.12+ and access to R4 Conecta endpoints") en skills de integración.
7. **Base para futuras creaciones**: todo skill nuevo se construye sobre esta especificación (carpeta + SKILL.md mínimo conforme a spec + disclosure progresivo) y se le añaden encima los requisitos propios de Hermes (tier, tests, docs, ver [[PLAN-DESARROLLO-HERMES]]).

### Correlación con Hermes (mapeo rápido)

| Spec Agent Skills | Hermes in-repo |
|---|---|
| `name` + `description` requeridos | Igual (límite interno 60 chars) |
| `metadata` libre | `version`, `author`, `platforms`, `metadata.hermes.{tags,related_skills}` |
| `scripts/`, `references/`, `assets/` | Mismos directorios |
| `compatibility` | ≈ `platforms` + `required_environment_variables` |
| `allowed-tools` (experimental) | Sin equivalente directo |
| `skills-ref validate` | Validador local en `tools/skill_manager_tool.py` |

---
Fuentes: `agentskills/README.md`, `agentskills/docs/specification.mdx`, `agentskills/docs/skill-creation/{quickstart,best-practices}.mdx` (2026-08-31).
Relacionado: [[PLAN-DESARROLLO-HERMES]], [[Meta-Business-Guru]], [[R4-DATOS-INTERCAMBIO]], [[README-integr-odoo-r4]].
