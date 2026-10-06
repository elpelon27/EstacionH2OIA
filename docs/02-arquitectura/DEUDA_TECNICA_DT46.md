# Deuda Técnica — DT-46 (prueba de campo 2026-10-05)

> Derivado de la minuta DT-46. Cada ítem: causa raíz, decisión del Líder y alcance pendiente.

## DT-46-A — Asignación de choferes por GPS en tiempo real (Issue 4, Fase 2)
**Decisión**: política actual (menor carga pending, `consumer.py::_get_active_vehicles_with_load` +
`bridge.py::_assign_vehicle_for_order`) se MANTIENE. No implementar GPS polling de choferes ahora.
**Hecho**: Fase 1 aplicada — 3 deliveries stale de Yordanis (vehicle_id=1, ids 1202/10201/10203)
marcadas `cancelled` (nota "stale cleanup DT-46"). Pending vehicle 1 = 0.
**Pendiente si se retoma**: los choferes no reportan ubicación continua (gps_tracks solo tiene
405 registros de vehicle 1, último 2026-09-27; cero de Evert). Haría falta: fuente de GPS del
chofer (botón Telegram / PWA), tabla de última posición por vehículo, y criterio de
desempate distancia-vs-carga.

## DT-46-B — Generación automática del link POD (Issue 5, Parte 2)
**Decisión**: flujo manual se MANTIENE — el link al chofer se genera solo al tocar "✅ Entregado"
(telegram_bot.py:740/867, `del_` callback). No automatizar ahora.
**Hecho**: Parte 1 aplicada — POD_SIGN_URL corregido de `http://...:8000/pod` (puerto no expuesto,
link muerto desde internet) a `https://valentina.estacionh2o.com/pod`. Verificado en el proceso
del bridge y en el edge (HTTP 422 en /pod/test = ruta viva).
**Pendiente si se retoma**: enviar el link de firma directamente al CLIENTE al confirmar entrega
(hoy el link solo va al chofer; el cliente recibe el PDF firmado vía WAHA, que requiere que el
chofer complete la PWA).

## DT-46-C — Aviso de cercanía al cliente (Issue 6)
**Causa raíz**: NO IMPLEMENTADO — grep `aviso_cercania|proximidad|cercania` en *.py del repo: 0 matches.
OSRM corre (docker `osrm`, :5000) pero nada lo consulta para proximidad.
**Alcance estimado del desarrollo**: polling GPS del chofer en ruta (requiere DT-46-A),
cálculo ETA OSRM o umbral de distancia haversine al cliente, trigger de una sola vez por
delivery (flag en deliveries), y envío del WhatsApp de aviso.
**Dependencia**: bloqueado por DT-46-A (sin GPS del chofer no hay disparador).

## Estado de los 6 issues DT-46 (resumen)
| Issue | Fix | Estado |
|---|---|---|
| 1 doble send/log | FIX 1A consumer.py logging | APLICADO (verificado 1 línea, no 2) |
| 2 C2P | C2P_ENABLED=true | APLICADO; pendiente prueba real banco |
| 3 GPS doble | FIX 3 A-D bridge.py | APLICADO (13/13 + 12/12 tests) |
| 4 despacho Evert-only | Fase 1 stale cleanup | APLICADO; Fase 2 = DT-46-A |
| 5 POD link | Parte 1 POD_SIGN_URL https | APLICADO; Parte 2 = DT-46-B |
| 6 aviso cercanía | — | DT-46-C (no implementado) |

Backups: /tmp/bridge_backup_DT46_fix3.py, /tmp/consumer_backup_DT46.py,
/tmp/env_backup_DT46_20261005_201559.env, /tmp/dispatch_backup_DT46.db
