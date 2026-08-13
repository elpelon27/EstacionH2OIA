# ADR-010: Monitoreo — Health extendido + métricas Prometheus

**Estado**: Aceptado
**Fecha**: 2026-08-12
**Relaciona**: FASE 7 (fix watchdog), FASE 9 de monitoreo

## Contexto
El hogar-servidor opera servicios críticos en producción (valentina-bridge,
dispatcher-bot, Odoo, cloudflared). En 2026-08-12 dos servicios cayeron en crash
loop: `valentina-bridge` (113 reinicios, matado por watchdog systemd con SIGABRT)
y `dispatcher-bot` (ModuleNotFoundError). El sistema necesitaba un health check que
viera más allá del propio bridge (Odoo, BDs, cola de despacho) y métricas que
alerten antes de que un servicio muera.

## Decisión
Extender `/health` con checks de dependencias del hogar y añadir métricas
Prometheus de negocio/estado, manteniendo el endpoint `/metrics` protegido por
IP allowlist (localhost + Docker 172.19/16).

Razones:
- Cobertura: el health previo solo veía tokens de Meta/Dify y SQLite; no veía si
  Odoo estaba caído ni la cola de despacho acumulada
- El check Odoo es **TCP con timeout corto (500ms)** para no añadir latencia al
  health (que systemd consulta en cada watchdog/restart)
- `dispatch_queue_pending` da señal temprana de pedidos atascados
- Las métricas nuevas (gauge) se exponen vía Prometheus para dashboards

## Consecuencias
**Positivas**:
- Visibilidad de Odoo, dispatch.db y cola de despacho en un solo `/health`
- Métricas `valentina_odoo_up` y `valentina_dispatch_queue_pending` scrapeables
- Corrección del watchdog systemd (Type=simple sin WatchdogSec, Restart=always):
  un watchdog que mataba un servicio sano era peor que ninguno

**Negativas/riesgos**:
- El check TCP solo verifica puerto, no auth (la auth real está en
  `/webhook/r4/health` de Odoo)
- Requiere restart del bridge para activar las nuevas métricas en producción

## Implementación
- `api/bridge.py`: helpers `_check_tcp_up()`, `_count_pending_queue()`
- `/health` → nuevos checks: `odoo`, `dispatch_db`, `dispatch_queue_pending`
- `/metrics` → nuevas métricas: `valentina_odoo_up`, `valentina_dispatch_queue_pending`
- Tests: `tests/unit/test_bridge.py` (27 passed) valida el import y endpoints
