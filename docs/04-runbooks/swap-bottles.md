# Runbook — SWAP de 165 Botellones (Modelo 1:1)

> **Proyecto**: Prometeo — Estación H2O · Maracaibo, Edo. Zulia, Venezuela
> **Base**: Av 8 con Calle 68/69 (Hotel Kristoff) · `10.6447, -71.6101` · radio 13 km
> **Versión**: 1.0 · **Estado**: Operativo (post-migración)
> **Fuente normativa**: `Descargas/H2O/Protocolo_Implementacion_Swap.pdf` v1.0
> **DB operativa**: `/mnt/ssd_trabajo/hermes-agent/data/dispatch.db`

---

## 1. Propósito

Migrar la recarga de botellones de agua (19 L / ~20 kg) del modelo de **trasegado en sitio** al **modelo SWAP 1:1 con loaner sellado en planta**. En cada parada el operador entrega **1 botellón lleno y sellado** y retira **1 botellón vacío** del cliente. El botellón vacío regresa a planta para lavado, desinfección, llenado y sellado; el cliente nunca presencia el trasegado.

**El número 165** es el inventario rotatorio de loaners necesario para cubrir el 100 % de la operación sin desembolso de capital (el negocio ya dispone de las unidades):

| Concepto | Cálculo | Unidades |
|---|---|---|
| Loaners en poder de clientes | 1 por cliente activo | 100 |
| Buffer en planta (lavado + llenado) | 30 % del volumen diario (~110) | 35 |
| Cargados en triciclo (1 viaje) | Capacidad por viaje | 30 |
| Margen de seguridad (rotura/pérdida) | 10 % sobre el total | ~17 |
| **TOTAL loaners empresa** | | **≈ 165** |

**Regla inquebrantable**: ningún botellón sale de la planta hacia el triciclo sin el sello *tamper-evident* aplicado correctamente. Un botellón sin sello equivale a un botellón trasegado en sitio — pierde todo el valor sanitario del modelo.

---

## 2. Prerrequisitos (verificar antes del Día 1)

| Componente | Estado requerido | Dónde |
|---|---|---|
| Inventario de loaners empresa | ≥ 165 unidades, etiquetadas con cinta de marca | Planta |
| Estación de lavado y sellado | Operativa, validada con volumen piloto | Planta |
| Insumos mínimos | Tapones sellables (300), bandas tamper-evident (500), desinfectante 5 L, guantes (100 pares), etiquetas de fecha (500) | Planta |
| `dispatch.db` | Inicializada con seed de zonas + vehículos | `data/dispatch.db` |
| Bot de despacho (Telegram) | Webhook `/dispatch/telegram/webhook` activo | `api/routes/dispatch.py` |
| Operadores capacitados | Planta + ruta habilitados (verificación final pasada) | — |
| Triciclos | 2 operativos, compartimento limpio/sucio separado | — |

---

## 3. Plan de 3 semanas

| Semana | Foco | Actividades clave | Resultado esperado | Hitos de control |
|---|---|---|---|---|
| **S1 (Días 1-6)** | Preparación interna | Verificar ≥ 165 loaners · validar estación de lavado · comprar insumos · capacitar operadores (planta + ruta) · etiquetar loaners con cinta de marca · diseñar/imprimir tarjetas al cliente · inicializar `dispatch.db` y sembrar 100 clientes con `bottle_exchange_model=1` | Planta y equipo listos. Operadores habilitados. | **D6**: verificación de planta y operadores — si no se cumple, **posponer** inicio de S2 |
| **S2 (Días 7-13)** | Migración piloto | Identificar 30-40 clientes piloto (B2B + multifamiliares) · WhatsApp a piloto 5 días antes · D7: iniciar entregas SWAP en piloto · D8-13: completar piloto y capturar feedback · ajustar protocolo si surgen problemas · subir precio a USD 1.30 **solo** en piloto migrado | 30-40 clientes migrados. Feedback capturado. Protocolo ajustado. | **D10**: revisión intermedia · **D13**: decisión **GO/NO-GO** para migración completa (si el piloto generó más reclamos de los previstos, extender una semana más) |
| **S3 (Días 14-20)** | Migración completa | WhatsApp al resto de la cartera · D14-18: migrar casas unifamiliares y restantes · D19-20: cuadre final de inventario de envases · aplicar USD 1.30 al 100 % de la cartera · auditoría de cumplimiento · evaluación de KPIs | 100 % cartera migrada. Precio USD 1.30 vigente. Protocolo consolidado. | **D20**: cierre formal del proyecto SWAP · evaluación de KPIs · decisión sobre activación del 2.º triciclo (solo tras 90 días estables) |

> **Política de reversión**: el SWAP es el estándar de la empresa. No se ofrece trasegado como alternativa. Si un cliente insiste en volver al trasegado, se respeta su decisión y se da de baja del servicio.

---

## 4. Asignación de vehículos

Dos triciclos motorizados, 1 operador c/u. Capacidad: **30 llenos / 70 vacíos** por unidad. Turnos: mañana `08:00-13:00`, tarde `15:00-18:00`. La separación física entre llenos (zona limpia, sello intacto) y vacíos (zona sucia) es obligatoria.

### 4.1 Asignación por fase del rollout

| Fase | Vehículo | Operador | Zonas asignadas | Clientes aprox. | Notas |
|---|---|---|---|---|---|
| **S2 Piloto** | Triciclo 1 (`vehicle_id=1`) | Operador 1 | Centro (4) + Las Delicias (2) | ~20 B2B | Mayor densidad B2B; ventanas acotadas horario laboral |
| **S2 Piloto** | Triciclo 2 (`vehicle_id=2`) | Operador 2 | Bella Vista (1) | ~15 multifamiliares | Ventanas amplias B2C |
| **S3 Completa** | Triciclo 1 (`vehicle_id=1`) | Operador 1 | Bella Vista (1) + La Limpia (3) | ~50 | |
| **S3 Completa** | Triciclo 2 (`vehicle_id=2`) | Operador 2 | Centro (4) + Tierra Negra (5) | ~50 | |

### 4.2 Capacidad y cadencia diaria

- Volumen diario objetivo: **~110 botellones** entregados (1:1) → ~55 por triciclo/día.
- Cada triciclo carga **30 llenos sellados** al iniciar el turno y retorna a planta **3-4 veces/día** para descargar vacíos y recargar llenos.
- En cada recarga se hace **conteo cruzado**: operador de ruta reporta vacíos traídos, operador de planta los recibe y confirma. Cualquier diferencia se investiga **en el acto** (no se acumula al cierre).
- Al cierre de jornada el inventario total debe cuadrar:
  `loaners en clientes + loaners en planta (limpios + sucios + en proceso) + loaners en triciclo = 165`

### 4.3 Registro de asignación en `dispatch.db`

```sql
-- Una sesión de despacho por vehículo por turno por día (única)
INSERT INTO dispatch_sessions (vehicle_id, shift, date, status, total_bottles_full, route_algorithm)
VALUES (1, 'morning', '2026-08-25', 'planning', 30, 'ortools_vrp');
-- Devuelve session_id; se usa para crear las deliveries de esa ruta.
```

```sql
-- Carga inicial del triciclo al iniciar el turno
UPDATE vehicles
SET current_full_load = 30, current_empty_load = 0
WHERE id = 1;
```

---

## 5. Modelo 1:1 — el intercambio en cada parada

Cada parada es una transacción de **1 lleno entrante / 1 vacío saliente**. El operador **no trasega agua**, **no abre** el botellón del cliente, **no toca el sello** del lleno que entrega.

### 5.1 Secuencia estándar (≈ 3-4 min por parada)

| Paso | Acción | Tiempo |
|---|---|---|
| 1 | Estacionar triciclo y anunciar llegada (timbre/llamado) | 30 s |
| 2 | Bajar con: 1 lleno sellado + libreta de pedido/cobro | 20 s |
| 3 | Solicitar el vacío (debe estar drenado, sin agua residual) | 10 s |
| 4 | Inspección visual rápida del vacío (sin grietas, sin cuerpo extraño) | 10 s |
| 5 | Entregar lleno sellado / recibir vacío | 30 s |
| 6 | Confirmar pedido y cobro (efectivo/crédito) | 30-60 s |
| 7 | Cargar vacío en compartimento de retornos (zona sucia) | 20 s |
| 8 | Registrar transacción en libreta (cliente, entregados/recogidos, monto) | 20 s |
| 9 | Despedirse y continuar | 10 s |

### 5.2 Reglas sanitarias del operador en ruta

- Manos limpias / gel alcoholado antes de tocar el cuello del lleno.
- **No tocar el sello tamper-evident** — lo rompe el cliente al instalarlo.
- No apoyar el botellón en el piso; si el cliente tarda, sostenerlo o apoyarlo en superficie limpia.
- Uniforme limpio (mandil/camiseta de la empresa).
- Agarrar el vacío del cliente **por el cuerpo**, no por el cuello.
- Cabello largo: recogido.

---

## 6. Registro en `dispatch.db`

La base `dispatch.db` es la **fuente de lectura** del dispatcher (SQLite local, latencia < 1 ms) y el destino de escritura de cada SWAP. Tablas involucradas: `clients`, `bottles`, `vehicles`, `deliveries`, `dispatch_sessions`, `zones`.

### 6.1 Sembrar un cliente en modelo SWAP

```sql
-- Todo cliente migrado a SWAP lleva bottle_exchange_model=1 y 1 loaner asignado
INSERT INTO clients (phone, phone_hash, name, address_text, lat, lng,
                    client_type, bottle_exchange_model, bottle_return_hours,
                    zone_id, priority, active)
VALUES ('+58412XXXXXXX', '<sha256+salt>', 'Cliente Piloto SRL',
        'Av. 4 entre Calles 70 y 71', 10.6500, -71.6200,
        'restaurant', 1, 24, 4, 3, 1);
-- => client_id

-- Loaner asignado a ese cliente (1:1)
INSERT INTO bottles (bottle_code, client_id, status, assigned_at, expected_return_at)
VALUES ('H2O-001', <client_id>, 'with_client',
        strftime('%s','now'), strftime('%s','now','+24 hours'));
```

### 6.2 Ciclo de vida de un loaner (tabla `bottles.status`)

```
available  ──despacho──▶  in_transit_full  ──entrega──▶  with_client
                                                              │
                                   ─────  próximo swap  ──────┤
                                                              ▼
                        available  ◀──lavado/sellado──  in_transit_empty
```

- `available` — en planta, listo para despacho (sellado)
- `in_transit_full` — en el triciclo camino al cliente (lleno)
- `with_client` — en poder del cliente (el loaner anterior queda vacío esperando retiro)
- `in_transit_empty` — regresando a planta (vacío)
- `maintenance` — en lavado/desinfección/llenado/sellado
- `retired` — dado de baja (grietas, degradación)

### 6.3 Transacción de un SWAP (entrega + retiro, 1:1)

```sql
BEGIN;

-- 1. Crear la entrega de la ruta (1 lleno a dejar, 1 vacío a recoger)
INSERT INTO deliveries (dispatch_session_id, client_id, vehicle_id,
                        order_sequence, status,
                        bottles_full, bottles_empty_pickup)
VALUES (<session_id>, <client_id>, <vehicle_id>, <n>, 'en_route', 1, 1);

-- 2. El loaner lleno pasa a "en camino al cliente"
UPDATE bottles
SET status = 'in_transit_full',
    dispatch_delivery_id = <delivery_id>,
    updated_at = strftime('%s','now')
WHERE id = <loaner_lleno_id>;

-- 3. Al confirmar entrega (bot del operador): marcar delivered + tiempos
UPDATE deliveries
SET status = 'delivered',
    actual_arrival = strftime('%s','now'),
    actual_departure = strftime('%s','now'),
    duration_seconds = 240,
    updated_at = strftime('%s','now')
WHERE id = <delivery_id>;

-- 4. El loaner entregado queda "with_client"; el vacío retirado pasa a "in_transit_empty"
UPDATE bottles SET status = 'with_client',  client_id = <client_id>,
                   updated_at = strftime('%s','now') WHERE id = <loaner_lleno_id>;
UPDATE bottles SET status = 'in_transit_empty',
                   updated_at = strftime('%s','now') WHERE id = <loaner_vacio_id>;

-- 5. Actualizar carga del triciclo
UPDATE vehicles
SET current_full_load = current_full_load - 1,
    current_empty_load = current_empty_load + 1
WHERE id = <vehicle_id>;

COMMIT;
```

### 6.4 Recepción en planta (fin de viaje)

```sql
-- El operador de planta recibe los vacíos: pasan a maintenance (lavado) y cuadran
UPDATE bottles SET status = 'maintenance', updated_at = strftime('%s','now')
WHERE id IN (<ids_vacios_recibidos>);

-- Recarga del triciclo con llenos sellados para el siguiente viaje
UPDATE vehicles SET current_full_load = 30, current_empty_load = 0
WHERE id = <vehicle_id>;
```

### 6.5 Verificaciones de fin de jornada

```sql
-- 1. Cuadre de inventario: debe sumar 165
SELECT
  (SELECT COUNT(*) FROM bottles WHERE status='with_client')      AS en_clientes,
  (SELECT COUNT(*) FROM bottles WHERE status IN ('maintenance','available')) AS en_planta,
  (SELECT COUNT(*) FROM bottles WHERE status IN ('in_transit_full','in_transit_empty')) AS en_transito;

-- 2. Sesiones completadas del día
SELECT id, vehicle_id, shift, status, total_clients, total_bottles_full, total_distance_km
FROM dispatch_sessions WHERE date = date('now');

-- 3. Entregas pendientes / no respondidas (para reprogramar)
SELECT d.id, c.name, c.phone, d.status
FROM deliveries d JOIN clients c ON c.id = d.client_id
WHERE d.date(d.created_at/1, 'unixepoch') = date('now')
  AND d.status IN ('no_answer','pending');

-- 4. Sellos / loaners perdidos (KPI operativo: < 2 % mensual)
SELECT COUNT(*) AS perdidos FROM bottles WHERE status='retired'
  AND updated_at >= strftime('%s','now','-30 days');
```

---

## 7. Botones del bot de despacho (Telegram)

El bot de despacho envía la ruta al operador vía Telegram y recibe confirmaciones por **inline keyboard**. Cada botón dispara un `POST /dispatch/telegram/webhook` que actualiza `deliveries.status` y, en el caso de `✅ Entregado`, ejecuta la transacción SWAP de la §6.3.

### 7.1 Teclado inline por parada

```
🚪 Llegué        →  deliveries.status = 'arrived'
                   gps_tracks: track_type='checkin_arrive'
✅ Entregado     →  deliveries.status = 'delivered'  + SWAP 1:1 (§6.3)
                   bottles: lleno→with_client, vacío→in_transit_empty
                   vehicles: full_load-1, empty_load+1
❌ No responde   →  deliveries.status = 'no_answer'  (reprogramar)
🔧 Reportar      →  prompt texto libre → operator_notes
                   deliveries.status queda en 'arrived' hasta aclarar
⏭️ Siguiente     →  avanza order_sequence; envía la próxima parada
🏁 Fin de ruta   →  dispatch_sessions.status = 'completed'
                   vehicles: carga final registrada
```

### 7.2 Mensaje de ruta enviado al operador (ejemplo)

```
🚚 Ruta mañana · Triciclo 1 · 2026-08-25
Paradas: 8  ·  Carga: 30 llenos

1️⃣  Cliente Piloto SRL  ·  Av 4 c/70-71
    Llevar: 1 lleno · Recoger: 1 vacío
    [🚪 Llegué]  [⏭️ Saltar]
```

> **Convenio**: `bottles_full` y `bottles_empty_pickup` se fijan en **1** para toda parada SWAP (modelo 1:1). El bot no ofrece editar cantidades; si una parada requiere N>1, se generan N entregas consecutivas con el mismo `client_id` y `order_sequence` adyacentes.

---

## 8. Troubleshooting

### 8.1 Excepciones operativas del SWAP

| Situación | Acción estándar |
|---|---|
| Cliente no tiene el vacío listo | No se entrega el lleno (no hay intercambio). Reprogramar al día siguiente; cobrar solo si confirma tener el vacío. Si insiste en recibir lleno sin entregar vacío, cobrar **depósito de loaner** (USD 5-6 recuperables). |
| Vacío del cliente está dañado | No se acepta el intercambio. Se informa que su botellón está fuera de servicio; ofrecer vender uno nuevo o continuar con loaner + depósito. El dañado se devuelve al cliente. |
| Sello *tamper-evident* llega roto | **Reclamo sanitario grave**. Cambiar el botellón de inmediato por uno con sello intacto. Registrar incidente e investigar causa (manipulación en ruta, sellado defectuoso, fricción en triciclo). Si ocurre **> 2 veces/semana**, revisar el sellado en planta. |
| Cliente reporta sabor/olor extraño | Retirar el botellón, reemplazar sin costo, llevar el sospechoso a planta para análisis. Revisar lote de agua del día de llenado y estado de filtros/UV. Registrar en bitácora. |
| Loaner no regresa de un cliente | Tras 3 visitas sin devolución, contactar al cliente. Si no responde o se niega, cobrar valor del botellón (USD 5-6) en la próxima factura. Si abandona el servicio, contabilizar pérdida y ajustar inventario de loaners. |
| Operador reporta más vacíos que llenos entregados | Error de registro o hurto. Revisar libreta, confirmar con cada cliente, cuadrar inventario antes del cierre. Si la diferencia persiste, cargar al operador el valor de los envases no cuadrados. |
| Cliente quiere cancelar el SWAP y volver al trasegado | El SWAP es el estándar. No se ofrece trasegado como alternativa. Respetar la decisión y dar de baja del servicio. |

### 8.2 Problemas técnicos / `dispatch.db`

| Síntoma | Causa probable | Solución |
|---|---|---|
| El bot no envía la ruta | Webhook `/dispatch/telegram/webhook` caído o Cloudflare Tunnel offline | `systemctl status hermes-agent.service` · `journalctl -u hermes-agent.service -n 50 --no-pager` · `curl https://<tunnel>/dispatch/health` |
| GPS del operador no actualiza | Tasker inactivo en el Android o sin datos | Verificar permiso de ubicación + batería sin restricción para Tasker; forzar `POST /dispatch/gps` de prueba |
| `SQLITE_BUSY: database is locked` | Sesión de dispatcher con transacción abierta | Revisar que toda transacción SWAP termine con `COMMIT;` (§6.3). `fuser data/dispatch.db` para ver procesos. Reintentar con *retry* exponencial. |
| Inventario no cuadra (≠ 165) | Loaner sin estado actualizado o pérdida no registrada | Ejecutar §6.5.1 · auditar `bottles` por `status` · buscar loaners en `in_transit_*` sin `returned_at` · reconciliar con libreta de planta |
| Sello defectuoso > 1 % (KPI) | Selladora térmica mal calibrada o bandas viejas | Revisar temperatura/tiempo (3-4 s hasta contracción uniforme) · stock de bandas · re-entrenar operador de planta (§7.1 del protocolo) |
| Cliente migra pero `bottle_exchange_model=0` | Cliente sembrado sin flag SWAP | `UPDATE clients SET bottle_exchange_model=1 WHERE id=<id>;` y asignar loaner (§6.1) |
| `deliveries` duplicadas para mismo `client_id`/día | Doble cálculo de ruta o reintento de webhook | Validar unicidad por `(dispatch_session_id, order_sequence)` · deduplicar por `message_id` en el puente |
| Ruta vacía al calcular | No hay pedidos con `Estado='registrado'` y `Pagado!='PENDIENTE'` en Google Sheets | Verificar hoja **Pedidos** (READ) · sincronizar y recalcular `POST /dispatch/route/compute` |

### 8.3 Puntos de contacto para escalar

- **Logs del agente**: `journalctl -u hermes-agent.service -n 50 --no-pager`
- **Health del dispatcher**: `GET /dispatch/health`
- **Estado de vehículos y carga**: `GET /dispatch/vehicles/status`
- **Ruta activa**: `GET /dispatch/route/active`
- **Reclamo sanitario grave (sello roto)**: escalar al propietario el mismo día; si se repite > 2 veces/semana, revisar sellado en planta.

---

## 9. KPIs post-implementación (monitoreo mensual)

| Dimensión | KPI | Meta | Frecuencia |
|---|---|---|---|
| Sanitaria | Reclamos sanitarios mensuales | 0 | Mensual |
| Sanitaria | Botellones rechazados en lavado | < 5 % del volumen | Semanal |
| Sanitaria | Sellos tamper-evident defectuosos | < 1 % | Semanal |
| Operativa | Botellones perdidos (inventario) | < 2 % mensual | Mensual |
| Operativa | Tiempo promedio por parada | 3-4 min | Mensual |
| Operativa | Drops por ruta por día | 30-40 | Semanal |
| Comercial | Tasa de retención mensual | > 90 % | Mensual |
| Comercial | Nuevos clientes por recomendación | > 3/mes | Mensual |
| Comercial | Satisfacción del cliente (encuesta) | > 85 % | Trimestral |
| Financiera | Utilidad mensual post-SWAP | ≥ USD 2 200 | Mensual |
| Financiera | Margen EBITDA | > 55 % | Mensual |
| Financiera | Costo variable unitario | ≤ USD 0.26 | Mensual |

> Cualquier KPI que se desvíe de la meta por **dos periodos consecutivos** activa revisión del protocolo. La expansión al 2.º triciclo se decide solo tras **90 días estables** del modelo SWAP.

---

## 10. Referencias

- Protocolo fuente: `Descargas/H2O/Protocolo_Implementacion_Swap.pdf` (v1.0)
- Arquitectura del dispatcher y schema completo de `dispatch.db`: `Descargas/H2O/DISPATCHER_ARCHITECTURE.md`
- Runbook base de despliegue (Valentina/WhatsApp): `Descargas/H2O/valentina-kit-completo/valentina-kit/RUNBOOK.md`
- Modelo financiero: `Descargas/Modelo_Financiero_Botellones_Agua.xlsx`
