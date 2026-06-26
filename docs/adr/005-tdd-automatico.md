# ADR-005: TDD automático

**Estado**: Aceptado
**Fecha**: 2026-06-25

## Contexto
Sistema anterior tenía 0% cobertura de tests. Refactors arriesgados.

## Decisión
Hermes escribe tests PRIMERO en cada feature (TDD). CI bloquea PRs sin tests o con coverage <60% en core/.

## Consecuencias
**Positivas**:
- Calidad garantizada
- Refactors seguros

**Negativas**:
- Desarrollo ~30% más lento
- Hermes debe ser bueno escribiendo tests (Fusion ayuda)
