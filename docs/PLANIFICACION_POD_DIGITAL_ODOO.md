# PLANIFICACIÓN: POD Digital + Créditos + Sincronización Odoo

**Modo**: Planificación arquitectónica (Prometeo 💧). Auditoría en vivo 2026-09-27.
**Regla**: Sin código de implementación. Solo lectura sobre producción.
**Repo**: feat/odoo-r4-integration @ 9b12085c

---

## 1. ESTADO ACTUAL (evidencia de auditoría en vivo)

### 1.1 Odoo — MÁS listo de lo asumido

| Verificado | Evidencia |
|---|---|
| Contenedor | `odoo-web` (odoo:17.0) y `odoo-db` (postgres:15) UP 5h, puerto 127.0.0.1:8069 |
| DB | `estacion_h2o` (no `odoo_h2o` como asumía el prompt) |
| Módulos instalados | **70 módulos**, incluyendo `account`, `sale`, `stock`, `stock_account`, `purchase`, `payment`, `account_payment`, **`l10n_ve`**, `hr` (nómina). Es decir: Invoicing, Sales, Inventory y localización venezolana YA están instalados |
| Productos | 83 `product_product` / 83 `product_template` — todos "Botellón 19L", precio 1.00, tipo product. **83 variantes del MISMO template = un producto por botellón individual** (¿intencional? ver pregunta Q1) |
| Clientes | 89 `res_partner`: mayoría "Cliente Conversión" (importación masiva previa) + defaults Odoo |
| Diarios fiscales | 8 `account_journal` por defecto (Customer Invoices, Bank, Cash, etc.) — sin personalizar |
| Inventario | 16 `stock_location` (WH/Stock, etc. defaults). 151 `stock_quant`, pero casi todos en "Virtual Locations/Production" con qty 3.00 — **stock basura/ajustes, no inventario real en WH/Stock** |
| Facturas | 68 `account_move` `out_invoice` en estado `draft` — huérfanas de flujo real |
| Config. fiscal | Diarios default; **NO verificado**: secuencias SENIAT, rif/VAT de la empresa, impuestos VE |

**Conclusión Odoo**: la plataforma está instalada y con datos de prueba/importación, pero la configuración de negocio (precios reales, inventario real en WH, partners reales con RIF, compañía) no está hecha.

### 1.2 Integración Odoo — YA EXISTE (hallazgo no esperado)

`src/integrations/odoo/odoo_sync.py` (~560 líneas) ya implementa:
- `OdooClient` (XML-RPC), `get_or_create_partner`, `get_product_by_name/price`
- `create_sale_order`, **`create_delivery_note`** (backorder picking), `confirm_delivery_note`
- **`convert_delivery_to_invoice`**, `register_payment`
- `get_sales_report`, `get_driver_commissions`

También hay scripts: `scripts/odoo_inventario_hielo.py`, `odoo_inventario_insumos.py`, `odoo_cierre_semanal.py`, `odoo_reporte_ventas_diarias.py`. Y `api/bridge.py` ya importa `get_or_create_partner` (línea 1403) y expone métrica `ODOO_UP` chequeando 127.0.0.1:8069.

**La API de sincronización Odoo NO hay que construirla: hay que auditarla/probarla y conectarle el POD.**

### 1.3 Entregas actuales (dispatch.db)

- Tabla `deliveries`: status (pending/delivered), `bottles_full`, `bottles_empty_pickup`, `bottles_on_site_refill`, timestamps llegada/salida, notas. 6 filas (1 delivered, 5 pending).
- **NO existe campo de firma, POD, cédula, foto, ni monto** en deliveries.
- `orders_auto` (pedidos auto-router): client_id, qty_botellones, delivery_date, estado, lat/lng, UNIQUE(client_id, delivery_date).
- `auto_materializer.py` (skills/dispatch/) convierte orders_auto → deliveries. Punto natural de enganche para POD.
- Bot Telegram chofer (@DespachoH2O_bot en `skills/dispatch/telegram_bot.py`): botones [📍 Llegué] [✅ Entregado] [❌ No responde] con callbacks `del_{id}`. "✅ Entregado" solo cambia status.

### 1.4 Crédito — YA EXISTE un sistema financiero (hallazgo mayor, no esperado)

En `data/conversations.db` (no en dispatch.db) vive el esquema `fs_*` (`src/financial/`):

- `fs_productos` (2: botellón + hielo con precio base/volumen)
- `fs_pedidos`: **90 pedidos** con `monto_total_eur/ves`, tasa de cambio dual, `botellones_cantidad`, `hielo_cantidad`, `tipo_credito`, `fecha_vencimiento_credito`, `estado_pago` (86 pendiente/3 pagado/3 confirmado/1 verificando), `estado_entrega` (87 sin_entregar), verificación bancaria, recordatorios, escalamiento
- `fs_pagos` (3) con referencia, comprobante_url, comprobante_phash, trigger de auditoría
- `fs_cuentas_cobrar` (0 filas — definida, sin uso)
- `fs_verificacion_log`, audit triggers, `fs_nomina`, `fs_tasas_cambio`
- `src/financial/verificacion.py` ya contempla: 1) API bancaria, 2) manual, 3) Líder vía `/pagado`
- `src/banking/r4_client.py`: cliente R4 Conecta completo (bcv, consulta, notifica, c2p, anulacion, credito_inmediato, domiciliacion) con HMAC auth

**La "libreta física a digitalizar" ya tiene un esqueleto digital parcial y funcional (con deuda: fs_cuentas_cobrar vacía, tipos de crédito sin datos).** El Líder debe decidir si este esquema fs_* es la fuente de verdad del crédito o si migra todo a Odoo.

### 1.5 Inventario botellones

- `bottles` (165 botellones con código, status, dueño) + `bottle_movements` (27 movimientos con auditoría). Trazabilidad individual YA existe.
- `vehicles.current_full_load / current_empty_load` (confirmado). La carga se descuenta en el flujo del bot; en Odoo el stock real de WH/Stock NO refleja nada (quants en Production).
- Trabajo de cierre: `core/workload_router.py` rutea "delivery_delivered" → skill bottle_tracker (swap).

### 1.6 Notificaciones WhatsApp / Valentina

- `agents/valentina.py` + puente WAHA (docker, sprint 3). Valentina maneja pedidos y dice "Paga al 0412-… y envía captura".
- `src/financial/reportes.py` + `cobranzas.get_resumen_cobranzas()` ya generan resumen de cobranzas programático; `memory_aware_agent.py` tiene templates `financial_1830` y `weekly_executive`.
- **No hay** template específico "resumen semanal de cuenta por cliente" (el resumen existente es de cobranzas global).

### 1.7 API bridge

`api/bridge.py` (3200+ líneas, monolito): `/`, `/metrics`, `/health`, `/webhook/meta` (GET/POST). `api/main.py`: `/health`, `/metrics`, `/webhook/meta`, `/webhook/telegram`, `/kill-switch`, `/send-message`. **No existe endpoint de POD ni firma.** `web/` está VACÍO: no hay frontend/PWA de ninguna clase.

---

## 2. BRECHA (lo que falta construir)

1. **POD**: tabla/entidad de nota de entrega digital (items, precios, total, swap vacíos, saldo anterior, firma, cédula, foto, estado sync). Nada existe.
2. **Frontend chofer**: web/ vacío. PWA offline-first con canvas de firma: 0%.
3. **Sincronización offline**: cola local (IndexedDB/SQLite móvil) + reconciliación con bridge: 0%.
4. **Endpoints bridge**: `/pod` (POST create/sign, GET pending-sync), `/sync/odoo`: 0%.
5. **Cableado botón ✅ Entregado → flujo POD**: hoy solo cambia status.
6. **Odoo config de negocio**: precios reales, stock inicial real en WH/Stock, partners reales con RIF/cédula, compañía/impuestos VE, manejo de los 68 drafts y 83 variantes de producto.
7. **Cuenta corriente digital**: decidir fuente de verdad (fs_* vs Odoo account.move+payments). fs_cuentas_cobrar sin uso.
8. **Resumen semanal de cuenta por cliente vía Valentina**: no existe (hay resumen global de cobranzas).
9. **Hooks SENIAT electrónico**: no existen (correcto dejarlos abiertos; account_edi_ubl_cii ya instalado puede servir de base futura).

---

## 3. ARQUITECTURA PROPUESTA

```
┌────────────────────────── CELULAR/TABLET DEL CHOFER (equipo empresa) ─────────────────────────┐
│  PWA (web/) — kiosco por vehículo, sin login de cliente, NO muestra saldo                     │
│  ┌────────────────────────────────────────────────────────────────────┐                      │
│  │  Lista de entregas del día (de deliveries materializadas)          │                      │
│  │  → Pantalla POD por entrega:                                       │                      │
│  │     recargas + hielo + precio unit + total + vacíos recibidos      │                      │
│  │     (saldo anterior SOLO visible si cliente pre-aprobado,          │                      │
│  │      lo trae ya RENDERIZADO del server — el chofer nunca calcula)  │                      │
│  │  → Firma canvas + cédula (teclado)                                 │                      │
│  │  → Fallbacks: ausente=foto / se niega=foto+sin firma               │                      │
│  │  → Guardar en cola local (IndexedDB) si sin señal                  │                      │
│  └────────────────────────────────────────────────────────────────────┘                      │
└───────────┬──────────────────────────────────┬───────────────────────────────────────────────┘
   online   │                                  │ offline
            ▼                                  ▼ (4G/WiFi recuperado → flush cola)
┌──────────────────── api/bridge.py (FastAPI, nuevo router /pod) ─────────────────────────────┐
│  POST /pod            → crea pod_record (SQLite dispatch.db, tabla nueva)                    │
│  POST /pod/sign       → guarda firma PNG + cédula + tipo (firmado/ausente/rechazo)           │
│  GET  /pod/pending    → entregas del día del vehículo (render del server, sin saldos crudos) │
│  POST /pod/sync       → batch offline → idempotente por delivery_id                          │
└───────┬──────────────────────────────┬──────────────────────────────────────────────────────┘
        │ trigger al firmar             │
        ▼                              ▼
┌── src/financial (fs_*) ──┐   ┌── src/integrations/odoo/odoo_sync.py (EXISTE) ────────────────┐
│ actualiza fs_pedidos /   │   │ get_or_create_partner → account.move (out_invoice)           │
│ fs_cuentas_cobrar        │   │ → registra pago (si contado) → stock: picking WH→Customer    │
│ (saldo del cliente)       │   │  (descontar botellón/hielo; vacíos = picking inverso o       │
└─────────┬────────────────│   │   movimiento interno Customer→WH si es swap)                │
          │                │   └──────────────────────────────────────────────────────────────┘
          │ resumen semanal │
          ▼                ▼
┌── Valentina (WAHA) ───────────┐  ┌── Bot Telegram @DespachoH2O_bot ──────────────────────────┐
│ - "Estado de cuenta" a        │  │ [✅ Entregado] → en vez de solo status: lanza enlace al     │
│   cliente con crédito (WA)    │  │   POD (deep link a la PWA) o inicia flujo firma             │
│ - comprobante de pago →       │  │ El chofer NUNCA ve saldo: la PWA lo recibe renderizado     │
│   fs_pagos + verificación     │  │   o no lo recibe                                            │
└───────────────────────────────┘  └────────────────────────────────────────────────────────────┘
```

Flujo de firma → Odoo (worker asíncrono, no en el request del chofer):
1. PWA firma → POST /pod/sign → pod_record estado `signed_local`.
2. Worker de sincronización (cron): por cada pod `signed` sin `odoo_synced`:
   `get_or_create_partner(cliente)` → `create_delivery_note`/`convert_delivery_to_invoice` (account.move draft) → `register_payment` si contado → picking de stock.
3. Estado final `odoo_synced=1` + `odoo_move_id`. Reintentos con backoff; POD nunca se pierde.
4. Nota fiscal física (libretas SENIAT) queda fuera; hooks futuros: campo `fiscal_invoice_number` y `fiscal_electronic_ref` en pod_record.

---

## 4. ENTREVISTA INVERSA — PREGUNTAS PARA EL LÍDER

### Odoo
- **Q1**: Encontré 83 variantes del mismo template "Botellón 19L" (una por botellón físico, precio 1.00) y 68 facturas draft. ¿Esas variantes fueron intencionales (trazabilidad individual en Odoo) o son residuo de una importación? ¿Purgamos y modelamos 1 producto "Botellón 19L" + 1 "Hielo" (y lote/cantidad vía stock), o mantenés trazabilidad individual?
- **Q2**: El precio list_price es 1.00 (¿EUR? ¿USD?). ¿Cuál es el precio real de venta hoy (botellón e hielo) y en qué moneda factura Odoo? ¿Usamos precios por lista (PVP) o los deja fs_productos como fuente?
- **Q3**: Odoo tiene `l10n_ve` instalado pero no verifiqué RIF de compañía ni impuestos configurados. Como las facturas físicas siguen manuscritas, ¿configuramos account.move como NO fiscal (borradores internos) por ahora, con hooks para SENIAT electrónico cuando os inscribás?
- **Q4**: ¿La fuente de verdad de la cuenta corriente es el esquema `fs_*` local (que ya existe) o el partner ledger de Odoo (account.move + payments)? Tener ambas duplica el riesgo de descalce. Mi recomendación: Odoo es la verdad, fs_* queda como buffer offline/caché. ¿Aceptás?
- **Q5**: Los 89 partners "Cliente Conversión" — ¿los purgo y re-importo con RIF/cédula/telefono matching contra los 363 clientes de dispatch.db? Necesito el mapeo teléfono→cédula para la firma.

### POD
- **Q6**: ¿Columnas nuevas en `deliveries` (pod_signed, signed_at, cedula, signature_path, photo_path, pod_status) o tabla nueva `pod_records` 1:1 con delivery? Mi recomendación: tabla nueva (la firma/foto es un hecho inmutable con su propio ciclo de sync; deliveries cambia schema seguido). ¿Aceptás?
- **Q7**: El botón "✅ Entregado" del bot hoy solo cambia status. ¿Lo reemplazo por un enlace a la PWA de firma, o mantenemos ambos caminos (bot = backup manual si el celular del POD se muere)?
- **Q8**: Cliente se niega a firmar: foto + producto entregado sin firma. ¿La nota igual se postea a Odoo como cuenta por cobrar? ¿Y quién/qué decide si esa entrega era crédito o contado (el Líder pre-aprueba: ¿dónde registro esa pre-aprobación — un flag `credit_approved` en clients)?
- **Q9**: En la nota debe verse "saldo anterior" para clientes con crédito. Dado que el chofer NO ve saldos: ¿el POD muestra el saldo SOLO cuando el cliente con crédito está presente y lo pide, o siempre que la entrega sea de cliente con crédito? (Sección de saldo renderizada server-side, el chofer no puede navegarla.)
- **Q10**: La cédula que se tipea en el POD, ¿se valida contra la cédula registrada del cliente (mismatch = alerta) o es solo registro?

### Hardware / Offline
- **Q11**: PWA vs app nativa (mi recomendación en §5). Si PWA: el celular necesita Chrome/WebView actualizado — ¿qué modelos de celular/tablet tenés hoy en la flota? (Define si PWA alcanza.)
- **Q12**: Si el chofer pierde el celular con notas offline sin sincronizar: ¿aceptás el riesgo con mitigación (PIN/bloqueo del equipo, borrado remoto no existe en PWA — ¿asegurás los equipos con MDM tipo Knox/Hexnode o solo PIN)? ¿Cuántas notas podría perderse máximo (1 día de ruta)?

### Crédito
- **Q13**: fs_pedidos tiene `tipo_credito` vacío en los 90 pedidos y fs_cuentas_cobrar tiene 0 filas. ¿Cargo yo la libreta física actual (saldo real por cliente) como migración inicial? ¿Me la pasás transcrita o en foto?
- **Q14**: El resumen semanal de cuenta: ¿lo empuja Valentina automáticamente (cron lunes X am) o el cliente lo pide ("estado de cuenta")? ¿Ambos?
- **Q15**: Ciclo semanal: ¿vencimiento fijo (lunes) o 7 días desde la entrega? fs_pedidos ya tiene fecha_vencimiento_credito por pedido — ¿la regla es "semana de entrega"?

### Inventario
- **Q16**: En Odoo, ¿el inventario maneja solo llenos (botellón + hielo) o también botellones vacíos como producto rastreable? bottles/bottle_movements ya hace trazabilidad individual local. Mi recomendación: vacíos NO van a Odoo (se quedan en bottles local), Odoo solo ve producto vendible. ¿Aceptás?
- **Q17**: ¿La ubicación Odoo "WH/Stock" representa el planta y cada camión es una ubicación interna propia (Vehicle-1, Vehicle-2) con transferencias al despachar? Eso hace el picking fiel a la realidad. ¿Aceptás o preferís descuento directo de WH al cliente?

### Integración
- **Q18**: `convert_delivery_to_invoice` de odoo_sync.py ya existe pero está probado solo con los drafts de prueba. ¿Puedo (fase de implementación) hacer una prueba end-to-end en la DB estacion_h2o con datos de test y luego purgar, o exigís una DB Odoo paralela de staging?
- **Q19**: Pago inmediato vía R4: hoy r4_client tiene c2p/consulta/credito_inmediato. ¿Al confirmarse un POD contado, marcamos el pedido `pagado` directo (efectivo al chofer) o esperamos la verificación R4? (O sea: ¿el chofer SÍ cobra efectivo en entregas contado? El prompt dice "solo entrega y retira".)
- **Q20**: ¿La PWA la sirve el mismo bridge (FastAPI static + un puerto expuesto solo en LAN/VPN) o necesita dominio/HTTPS público? La firma de canvas no requiere HTTPS, pero service worker sí para PWA instalable.

---

## 5. OPINIONES DE INGENIERÍA (Hermes)

1. **Odoo nativo vs custom**: Odoo nativo, sin dudarlo. Ya está instalado (account+stock+l10n_ve), ya hay cliente de sincronización (odoo_sync.py) con delivery note → invoice → payment. Un sistema custom de facturas paralelo duplicaría lo que Odoo hace gratis y nos ataría los hooks fiscales. Lo custom solo la capa POD (la nota digital NO es una factura fiscal — es respaldo de deuda).
2. **PWA vs nativa**: **PWA**. El flujo es un formulario con canvas + cola IndexedDB + service worker; eso es exactamente el sweet spot PWA. Nativa (Kotlin) agrega build/release/signing por cero beneficio aquí. Única razón para nativa: si los equipos son Android muy viejos (<Chrome 90) o necesitás camera nativa de alta fiabilidad — la cámara web `<input type=capture>` basta para fotos de prueba. Riesgo aceptado: sin MDM no hay borrado remoto.
3. **¿POD en bridge o microservicio?**: En el bridge como router FastAPI nuevo (`api/routers/pod.py` conceptualmente), con tabla propia SQLite. El bridge ya es el centro de gravedad (webhooks, health, Odoo check). Un microservicio separado agrega deploy, TLS y monitoreo extra para cero ganancia a esta escala. La única pieza separada recomendada: el **worker de sincronización Odoo** desacoplado (cron/celery-like) para que la app del chofer nunca espere a Odoo (que puede estar caído).
4. **Resumen semanal**: Ambos. Cron automático lunes temprano (Valentina empuja a todos los clientes con saldo) + comando on-demand "estado de cuenta". El cómputo sale de fs_* / Odoo, nunca de la libreta. El empuje automático es el que elimina el trabajo manual — generarlo "a mano" reproduce el problema que estamos matando.
5. **Seguridad celular perdido**: mitigación en capas: (a) PIN/bloqueo del equipo + PWA que solo muestra el día actual, nunca histórico; (b) la PWA no expone saldos crudos — todo render server-side; (c) equipo se registra con token por vehículo revocable desde el bridge (kill-switch ya existe en api/main.py — extendemos); (d) foto y firma viajan al server apenas hay señal, la ventana offline es horas, no días. Residual: 1 día de PODs sin sincronizar — recuperable por re-carga del chofer (re firma en papel excepcional).
6. **Patrones existentes a reutilizar**: (a) `auto_materializer` orders_auto→deliveries es el punto de enganche natural del POD; (b) el patrón de auditoría de `fs_*` (triggers fs_audit_log) lo replicamos en pod_records; (c) `bottle_movements` ya resuelve el swap de vacíos — el POD solo lee/confirma; (d) `get_or_create_partner` + verificación con phash de comprobantes de fs_pagos para dedupe; (e) el botón ✅ Entregado como trigger manual alternativo.

---

## 6. RIESGOS

| # | Riesgo | Mitigación |
|---|---|---|
| R1 | Doble fuente de verdad de saldo (fs_* vs Odoo) | Decidir Q4 en la entrevista; reconciliación diaria automática con alerta de descalce |
| R2 | 83 variantes + 68 drafts basura en Odoo contaminando reportes | Purga/ajuste antes del go-live (con backup pg_dump previo) |
| R3 | Odoo caído durante sincronización → cola crece | Worker con reintentos idempotentes (clave delivery_id+fecha); POD marca estado, nunca bloquea al chofer |
| R4 | Pérdida/robo del celular con notas offline | PIN + token revocable + datos mínimos en equipo (Q12) |
| R5 | Firma disputada legalmente (sin marco legal VE de firma simple) | Cédula + foto + timestamp + geo + hash del contenido; NO es firma digital certificada — documentarlo claro; la libreta fiscal sigue siendo el documento tributario |
| R6 | Chofer ve saldo que no debe ver | Render server-side por sección; sin endpoint de saldos en la PWA; test de auditoría |
| R7 | Mala foto (ausente/rechazo) inutilizable como prueba | Preview obligatorio + re-toma en el acto; guardamos thumbnail y original |
| R8 | Puente WAHA/Valentina caído justo el lunes del resumen | Cron con reintento + fallback: resumen queda en /docs o mensaje al Líder |
| R9 | Tasa EUR/VES con la que se liquida el crédito (fs_pedidos guarda tasa dual) | Congelar tasa al momento del POD; documentar en la nota |
| R10 | Scope creep: intentar facturación fiscal electrónica antes de tiempo | Hooks vacíos (campos fiscales reservados), nada más |

---

## 7. ESTIMACIÓN POR COMPONENTE (días hábiles, Prometeo)

| Componente | Estimación | Notas |
|---|---|---|
| A. Config Odoo negocio (partners reales, precios, stock inicial, purga drafts) | 2–3 d | Requiere insumos del Líder (Q1–Q5, libreta) |
| B. Prueba end-to-end odoo_sync (partner→picking→invoice→pago) | 1–2 d | Q18 define entorno |
| C. Esquema pod_records + endpoints bridge (POD CRUD, sign, sync, idempotencia) | 2–3 d | Patrón fs_* como referencia |
| D. PWA offline-first (lista entregas, nota, canvas firma, cédula, foto, cola IndexedDB, sync) | 4–5 d | El bloque más grande |
| E. Cableado ✅ Entregado + auto_materializer → POD | 1 d | |
| F. Worker sincronización POD→Odoo + estados + reintentos | 2 d | |
| G. Crédito: pre-aprobación (flag), saldo render, fs_cuentas_cobrar en uso | 2 d | + migración libreta (Q13) si el Líder pasa datos |
| H. Resumen semanal Valentina (cron + on-demand) | 1–2 d | Reutiliza reportes.py |
| I. Seguridad del equipo (tokens por vehículo, kill-switch PWA) | 1 d | |
| J. Hooks fiscales + documentación + tests de auditoría | 1–2 d | |
| **Total** | **17–22 d** | Con paralelización de D con A/B: ~3 semanas calendario |

Orden recomendado: B (validar lo que existe) → C → E → D → F → A → G → H → I → J.

---

## DECISIONES QUE BLOQUEAN EL ARRANQUE (resumen para el Líder)

1. Q4 (fuente de verdad de saldo) — bloquea C y G.
2. Q1/Q2 (productos y precios en Odoo) — bloquea A.
3. Q11/Q12 (hardware y política de equipo) — bloquea D.
4. Q13 (libreta física para migración inicial) — bloquea G.
5. Q18 (¿puedo probar en la DB viva con datos test?) — bloquea B.
