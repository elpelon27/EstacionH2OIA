# ADR-001: OpenRouter Fusion Tournament

**Estado**: Aceptado
**Fecha**: 2026-06-25

## Contexto
Se requiere alta calidad en decisiones críticas (arquitectura, código core, respuestas a clientes nuevos). Un solo modelo puede fallar.

## Decisión
Implementar Fusion Tournament con 4 modelos compitiendo en paralelo:
- z-ai/glm-4.5 (base + juez)
- anthropic/claude-sonnet-4.5 (razonamiento profundo)
- deepseek/deepseek-chat-v3.2 (código + matemáticas)
- google/gemini-2.5-flash (contexto 1M + multimodal)

GLM-4.5 evalúa las 4 respuestas con 5 criterios ponderados:
- Coherencia (25%)
- Seguridad (25%)
- Adherencia a reglas (20%)
- Completitud (15%)
- Calidad técnica (15%)

## Consecuencias
**Positivas**:
- Calidad superior en decisiones críticas
- Diversidad de enfoques
- Auditabilidad (se persisten las 4 respuestas + scores)

**Negativas**:
- Costo 4× por tarea Fusion (justificado para tareas críticas)
- Latencia = max(modelos) + judge (~10-15s)

## Alternativas consideradas
- Modelo único (Claude): caro, single point of failure
- Router determinista: sin diversidad
- Sakana Fugu: caja negra, más caro ($5/$30 por M tokens), no auditable

## Referencias
- Sakana Fugu research: ignorado (ver investigación 2026-06-23)
- Plano BOOTSTRAP.md §7
