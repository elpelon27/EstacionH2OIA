# ROADMAP SKILLS — FASE 4: Herramientas Evaluadas

**Última actualización**: 2026-09-01
**Autor**: Prometeo (GLM 5.3 vía OpenRouter)
**Fuente**: evaluación de herramientas candidatas para FASE 4 (razonamiento + escala)
**Estado Qdrant al evaluar**: ~402 puntos (768d, nomic-embed-text) — sin carga que justifique index TurboVec todavía

---

## Herramientas Evaluadas

### 1. Semantica — Grafos de Conocimiento ✅ APROBADA (condicionada a datos)
- **Qué**: Capa de grafos de conocimiento sobre la memoria semántica (entidades: clientes, pedidos, rutas, pagos → relaciones tipadas).
- **Beneficio medido en evaluación**: 40-50% de mejora en recall de memoria frente a búsqueda vectorial plana.
- **Estado**: APROBADA en arquitectura, pero la mejora solo es medible con volumen real.
- **Bloqueada por**: **VOLUMEN DE DATOS** — con ~402 puntos y <500 transacciones históricas, el grafo no supera al índice plano. Activar cuando fs_pedidos supere 500+ transacciones reales.
- **No bloqueada por Odoo/R4**: no requiere endpoints nuevos ni tocar producción.

### 2. TurboVec — Vector Index 10-50x 🟡 APROBADA (condicionada a escala)
- **Qué**: Motor de vectores ligero (RyanCodrai/turbovec, score 91 en estudio repos) como index acelerado.
- **Beneficio**: búsqueda 10-50x más rápida que Qdrant HNSW a partir de cierto volumen.
- **Estado**: APROBADA para el futuro, NO instalar todavía.
- **Bloqueada por**: **VOLUMEN DE DATOS** — umbral definido: cuando Qdrant supere **5000 puntos**. Con 402 actuales, la ganancia es nula y el swap introduce riesgo sin beneficio.
- **Criterio de activación (verificable)**: `curl Qdrant /collections/hermes_memory` → points.count > 5000.
- **No bloqueada por Odoo/R4**: swap local en memoria, sin tocar prod ni whitelist.

### 3. Loop Engineering — Orquestación de Loops de Agentes 🔴 BLOQUEADA
- **Qué**: Orquestación de loops de agentes (agent-to-agent, workflows iterativos con verificación por sección).
- **Estado**: EVALUADA, no integrar aún.
- **Bloqueada por**:
  - **ODOO PRODUCCIÓN**: los loops de mayor valor (conciliación pagos→pedidos→inventario) requieren Odoo operativo en producción; hoy no lo está.
  - **R4 WHITELIST**: los loops que cierran el ciclo de pago automático dependen del webhook `/webhook/r4/notifica` con las IPs del banco confirmadas en whitelist — pendiente confirmación del banco (45.175.213.98, 200.74.203.91, 204.199.249.3).
- **Desbloqueo**: Odoo en producción + whitelist R4 confirmada end-to-end (curl desde IP del banco → 200, desde IP no autorizada → 403).

### 4. Agent Skills Spec (agentskills.io) ✅ INTEGRADA
- **Qué**: Especificación Agent Skills como estándar de empaquetado/discovery de skills (fase discovery → activation → execution).
- **Estado**: **YA INTEGRADA** en FASE 3 (`src/orchestration/external_skills.py`, AnthropicSkillsConnector; ver `AGENT-SKILLS-ESPECIFICACION.md` y commit 43b017a).
- **Bloqueada por**: NADA — es el estándar vigente del repo. Las herramientas nuevas de FASE 4 DEBEN empaquetarse bajo esta spec.

---

## Matriz de Bloqueos

| Herramienta | Odoo producción | R4 whitelist | Volumen de datos (500+ transacciones) | Estado |
|---|---|---|---|---|
| Semantica (grafos) | — | — | 🔴 BLOQUEA | Aprobada, esperar 500+ transacciones |
| TurboVec (vector index) | — | — | 🟡 BLOQUEA (>5000 pts Qdrant) | Aprobada, esperar umbral Qdrant |
| Loop Engineering | 🔴 BLOQUEA | 🔴 BLOQUEA | — | Evaluada, sin integrar |
| Agent Skills spec | ✅ Integrada | ✅ Integrada | ✅ Integrada | Estándar vigente |

---

## Criterios de Desbloqueo (verificables, nunca de informes pasados)

1. **Volumen de datos**: `SELECT COUNT(*) FROM fs_pedidos` ≥ 500 → activar Semantica; Qdrant points.count > 5000 → activar TurboVec.
2. **Odoo producción**: servicios Odoo activos + sync verificado con datos reales en vivo.
3. **R4 whitelist**: test end-to-end con IP del banco (200) + IP no autorizada (403) — ver `skills/r4banco_test.py`.

## Orden Sugerido de Activación

1. Agent Skills spec (ya activa — base para todo lo demás)
2. Semantica — al alcanzar 500+ transacciones
3. TurboVec — al superar 5000 puntos en Qdrant
4. Loop Engineering — al desbloquearse Odoo producción + R4 whitelist (ambos)

---
💧
