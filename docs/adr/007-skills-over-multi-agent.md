# ADR-007: Skills sobre Multi-agente para <1,000 msg/día

**Estado**: Aceptado
**Fecha**: 2026-07-02

## Contexto
El roadmap original contemplaba 10 agentes separados. Para 300 consultas/mes (~10/día) con 1 operador, esto es overkill.

## Decisión
Arquitectura híbrida: 6 skills + 2 agentes en 1 proceso FastAPI.
- Skills: funciones modulares invocadas por workload_router
- Agentes: Valentina (WhatsApp) y Dispatcher (Telegram) con estado conversacional
- self_improve_skill: usa Fusion Tournament en horario nocturno (6:00pm-7:40am)

## Consecuencias
**Positivas**:
- 1 proceso, 1 operador, mantenimiento simple
- 0 overhead de comunicación inter-agente
- Skills reutilizan core/ (logger, config, cost_guard)

**Negativas**:
- Acoplamiento (un bug puede afectar todo)
- No escala horizontalmente (pero innecesario a este volumen)

## Cuándo reconsiderar
Solo al superar 1,000 conversaciones/día o contratar 2do operador.
