# ADR-003: Hot Failover 8 min

**Estado**: Aceptado
**Fecha**: 2026-06-25

## Contexto
Cortes eléctricos/Internet en Maracaibo. VPS debe asumir control.

## Decisión
Heartbeat cada 1 min. Detección a los 8 min (3 min sospecha + 2 min re-intento + 3 min validación). VPS corriendo recepcionista + despachador con OpenRouter.

## Consecuencias
**Positivas**:
- 8 min de tolerancia a cortes transitorios
- VPS productivo (no solo pasivo)

**Negativas**:
- 8 min de downtime en failover (aceptable para negocio de agua)

## Alternativas
- 3 min: muy agresivo, failovers por falsos positivos
- 15 min: demasiado para clientes esperando
