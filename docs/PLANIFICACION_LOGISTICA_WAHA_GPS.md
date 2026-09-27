# Planificación Logística: WAHA + GPS + ETA + Auto-Routing Nivel 1

**Fecha**: 2026-09-27
**Autor**: Prometeo (orquestador, modo planificación)
**Fuente**: Auditoría EN VIVO (código + data/dispatch.db + docker ps) — 2026-09-27
**Estado**: DOCUMENTO DE PLANIFICACIÓN — sin código de implementación

---

## 1. ESTADO ACTUAL (verificado en vivo, lo que ya existe y sirve)

### 1.1 Bot @DespachoH2O_bot (skills/dispatch/telegram_bot.py, ~630 líneas)

**Ya implementado y operativo** (systemd: `dispatcher-bot.service`):

| Componente | Estado | Detalle verificado |
|---|---|---|
| `/start` con auto-registro | ✅ | Menú de vehículos activos sin chat_id → botón "Soy YORDANIS (Triciclo 1)" → `register_chofer()` hace UPDATE vehicles |
| `/ruta` | ✅ | Lista entregas del chofer con GPS URL por parada |
| `/siguiente` | ✅ | Próxima parada + **botones "📍 Llegué" (arr_) / "✅ Entregado" (del_) / "❌ No responde" (no_)** |
| `/status`, `/help` | ✅ | Estado del chofer |
| Separación por chofer | ✅ EXISTE HOY | El bot resuelve identidad vía `get_chofer_by_chat_id(chat_id)` — cada chofer tiene SU chat privado con el bot, SUS botones van con SU delivery_id. **2 choferes en 1 bot ya funciona por diseño.** |

**Conclusión clave sobre "2 choferes en 1 bot es complicado"**: el código YA separa
sesiones por chat_id (conversación 1-a-1 privado bot↔chofer). El problema real es
otro: los chat_ids de vehicles son **placeholders (111111, 222222)** — DT-01 sigue
sin resolverse desde el 12-ago. Sin /start real de Yordanis y Evert, NADA del
Sprint 3 E2E puede probarse. No hacen falta 2 bots.

### 1.2 GPS actual

- `gps_tracks` (data/dispatch.db): schema completo con lat/lng/accuracy/speed_kmh/
  source/track_type, índices por vehículo+tiempo. **Vacio en la práctica** para
  tracking continuo: source hoy = "telegram" (manual) o "tasker" (app Android
  Tasker ya contemplada en `skills/dispatch/gps_tracker.py`).
- `POST /api/dispatch/gps` existe (api/routes/dispatch.py:105) → endpoint de
  ingest listo para recibir pings de una app/Traccar.
- **No hay WAHA, Traccar, OSRM ni GraphHopper** en docker ps (verificado): solo
  Dify, Odoo, Prometheus/Loki/Promtail, OpenNotebook, Paperless.

### 1.3 Dispatch de pedidos (flujo hoy)

1. Cliente WhatsApp → Meta Cloud API → Cloudflare Tunnel → `valentina-bridge.service`
   (api/bridge.py, FSM 8 estados) → `dispatch_queue` (conversations.db).
2. Cron 7:45 FASE 1.1 lee dispatch_queue → `compute_vrp_route()` (OR-Tools) →
   `dispatch_sessions` + `deliveries` (data/dispatch.db).
3. Bot notifica a chofer (bloqueado por DT-01: chat_ids placeholder).
4. `deliveries` ya tiene `estimated_arrival`, `actual_arrival`, `duration_seconds`
   — columnas listas para ETA/estadía, hoy sin calcular.

### 1.4 Auto-Routing Nivel 1 (commit c3b6572f, "creada ayer")

- `scripts/routing/auto_router.py`: clientes `is_automatic=1` → ruta diaria
  obligatoria; lunes qty×2; materializa en **orders_auto** con estado
  `pending_dispatch`.
- **HALLAZGO CRÍTICO**: orders_auto tiene **0 filas** y NADIE la lee salvo el
  propio auto_router y sus tests. **No existe el puente orders_auto → deliveries
  → bot**. El flujo se corta: los pedidos automáticos nunca llegan al chofer.
- Falta además: cliente `is_automatic` no aparece con conteo >0 verificado y no
  hay división entre 2 operadores (la ruta es una sola lista).

### 1.5 Errores de documentación encontrados (validar antes de codificar)

- `db/dispatch.db` está **VACÍA** (0 tablas); la DB activa es `data/dispatch.db`
  (300K). Los backups antiguos en backups/ usan `driver_name`; la tabla actual
  usa `operator_name`. Cualquier script que apunte a db/ o a driver_name rompe.

---

## 2. BRECHA (lo que falta construir)

| # | Brecha | Tamaño estimado | Notas |
|---|---|---|---|
| B1 | DT-01: chat_ids reales de choferes | 5 min + coordinación | **Bloquea TODO.** Choferes hacen /start al bot; botón los registra automáticamente |
| B2 | Puente orders_auto → deliveries → bot | M | Nuevo "materializador": convierte pedidos auto en deliveries de la sesión del día, divididos entre vehículos 1 y 2 (balanceo por zona/cantidad) |
| B3 | GPS tracking continuo del chofer | M | Evaluar Traccar (docker, app Android "Traccar Client", ~200MB RAM) vs Tasker HTTP POST a /api/dispatch/gps (ya existe, cero infra nueva) |
| B4 | Motor ETA | M | OSRM self-hosted (docker, ~1-1.5GB RAM + dataset Venezuela OSM) vs API cloud (GraphHopper/Routing API con tráfico). **Sin tráfico real en OSRM** — la exactitud "5 min" con tráfico requiere datos de velocidad histórica propia (gps_tracks acumulando) |
| B5 | WAHA + número secundario | M | Docker + sesión WhatsApp no-oficial (web JS). Riesgo: ban del número. Requiere SIM/número nuevo |
| B6 | Orquestador de avisos (5 min ETA / llegada 50m / esperando) | M | Servicio que consume gps_tracks, calcula ETA a próxima parada, dispara WAHA al cliente. Geofence 50m ya hay tecnología (geofence.py ray-casting, reutilizable a escala parada) |
| B7 | Comando "pedir ruta al llegar a estación" | S | El chofer ya tiene /ruta; falta hook "estoy en estación" (geofence de la estación) que genere/active su sesión |
| B8 | Asignación dinámica por proximidad (triangulación) | L | Requiere OR-Tools con posición inicial del vehículo (ya soportado por VRP) o re-asignación en vivo |

---

## 3. ARQUITECTURA PROPUESTA

```
                        CLIENTE (WhatsApp principal: Valentina / Meta Cloud API)
                              │                          ▲
                              │ pedido                   │ aviso "5 min / llegué /
                              ▼                          │ esperando" (WAHA, núm. 2)
   [cloudflared tunnel] → valentina-bridge (FSM)         │
                              │                          │
                              ▼                          │
                     dispatch_queue ──► cron 7:45 ──► VRP OR-Tools ──► deliveries
                                                  (posiciones GPS iniciales)      │
   CLIENTES NIVEL 1 ──► auto_router (cron mañana) ──► orders_auto                   │
                              │                                                      │
                              ▼  (B2: materializador, reparto 2 operadores)         │
                          deliveries ◄──────────────────────────────────────────────┘
                              │                                     
                              ▼                                     
                     @DespachoH2O_bot (Telegram, 1 bot, 2 chats privados)           
                              ▲  /ruta, /siguiente, botones Llegué/Entregado        
                              │                                                     
   CHOFER (teléfono Android) ─┴─► GPS continuo ──► ingest /api/dispatch/gps        
                              (Traccar Client app  o  Tasker POST cada N min)       
                              │                                                     
                              ▼                                                     
                        gps_tracks ──► [NUEVO] motor-eta.service                   
                              │            (OSRM/GraphHopper + velocidad histórica) 
                              ▼                                                     
                     ETA <= 5 min → WAHA envía aviso al cliente ◄─────── geofence 50m
                     (radio 50m)  → WAHA "el repartidor llegó"
                     espera > X   → WAHA "está esperando"
```

**Flujo completo nuevo**: pedido (o auto Nivel 1) → VRP asigna → bot muestra ruta →
chofer GPS fluye → motor ETA vigila próxima parada → WAHA avisa cliente en 3
momentos → chofer confirma botones → deliveries.status pasa a delivered.

**Stack a añadir (docker)**: waha (docker), traccar (opcional), osrm (opcional),
motor-eta (python systemd, igual patrón que skills/dispatch/*).

---

## 4. ENTREVISTA INVERSA — PREGUNTAS PARA EL LÍDER 💧

### Bloque A — Desbloqueo (sin esto no hay nada que construir)

1. **DT-01 sigue abierto desde el 12-ago.** ¿Puedes citar a Yordanis y Evert HOY
   a hacer /start a @DespachoH2O_bot? Con su mensaje el bot los registra solo
   (ya implementado). ¿O prefieres que les mande QR/instrucciones por WhatsApp?

2. Confirmé que **1 bot ya separa a los 2 choferes por chat_id privado** — cada
   chofer habla con el bot 1-a-1 y sus botones llevan SU delivery_id. Tu sensación
   de "2 choferes en 1 bot es complicado" ¿viene de un problema real visto en
   producción, o de una sesión grupal? Si es grupo: propongo **prohibir el grupo**
   (el bot solo responde chats privados) en vez de crear 2 bots. ¿Aprobás?

### Bloque B — WAHA y número secundario

3. ¿De dónde sale el número secundario (SIM nueva)? ¿Costo mensual aceptable?
   Riesgo asumido: WhatsApp no-oficial puede **banear el número** (no el
   principal). ¿Backup plan si lo banean (volver a Meta Cloud API con plantillas)?

4. ¿El aviso al cliente sale del número secundario SIEMPRE, o solo cuando el
   cliente tiene la ventana de 24h cerrada? Propongo: Ventana abierta → Meta
   Cloud API (número oficial Valentina); ventana cerrada → WAHA. ¿Aprobás?

5. ¿Qué texto exacto querés para los 3 avisos (5 min / llegada / esperando)?
   ¿Se les pide confirmar que están en casa (botón de respuesta)? Sin botón en
   WAHA no oficial solo hay texto simple.

### Bloque C — GPS del chofer

6. ¿Los teléfonos de Yordanis y Evert son Android con datos móviles confiables?
   Opción simple: app **Traccar Client** (gratis, envía cada 30-60s a nuestro
   servidor, ya hay endpoint /api/dispatch/gps). Opción custom: Tasker.
   ¿Preferís Traccar self-hosted (1 docker + 200MB RAM) o POST directo Tasker
   (cero infra nueva)? Recomiendo Traccar: app lista, mapa web incluido.

7. Batería/encendido: ¿el GPS debe correr todo el turno (8h)? ¿Se apaga al
   terminar? ¿Qué pasa si el chofer apaga el tracking (privacidad)?

### Bloque D — ETA y ruteo

8. **OSRM self-hosted** (docker, ~1-1.5GB RAM + mapa Venezuela ~500MB, sin datos
   de tráfico en tiempo real) vs **API cloud** (GraphHopper/Radar con tráfico,
   costo por llamada, dependencia externa). Dato clave: la exactitud "5 min"
   real se logra con **velocidad histórica propia** (tabla gps_tracks
   acumulando por hora/zona). Propuesta pragmática: empezar con distancia
   recta + velocidad promedio medida en vivo (cero dependencias), migrar a
   OSRM cuando tengamos 2 semanas de gps_tracks. ¿Aprobás lo pragmático?

9. ¿El aviso de 5 minutos tolera error? Si digo "5 min" y tardo 9, ¿es peor
   que no avisar? Propongo avisar solo cuando ETA ≤ 6 min con margen.

### Bloque E — Asignación dinámica y Nivel 1

10. ¿Cómo sabemos qué CLIENTE le toca a qué CHOFER cuando despachamos en vivo?
    Hoy VRP asigna al iniciar la sesión. Con "triangulación" dinámica: ¿re-asignar
    paradas pendientes entre choferes en tiempo real, o solo la PRIMERA asignación
    al salir de la estación se hace por proximidad? (re-asignar en vivo agrega
    complejidad y puede confundir al chofer que ya memorizó su ruta).

11. Nivel 1 (restaurantes/clínicas/escuelas): "repartida entre 2 operadores" —
    ¿división por ZONA (norte/sur), por CLIENTE fijo (cada cliente siempre el
    mismo chofer), o por CANTIDAD (balancear botellones)? Recomiendo zona +
    balanceo de cantidad como desempate.

12. orders_auto está creada pero VACÍA y nadie la lee. ¿Cuántos clientes
    tenemos hoy con is_automatic=1? ¿Confirmás que el auto_router ya corrió
    alguna vez o solo está el código? ¿A qué hora de la mañana generamos la
    ruta (cron)? ¿Los 2 "operadores" son Yordanis/Evert o son otros?

13. Geolocalización de clientes Nivel 1: orders_auto pide lat/lng de cada
    cliente. ¿Ya existen en clients (import WhatsApp)? Si faltan, ¿el chofer
    las fija en la primera entrega con su GPS (propongo esto)?

### Bloque F — Prioridades

14. Propuesta de orden de construcción (cada paso se puede verificar E2E):
    S1: DT-01 registro choferes + Sprint 3 Swap E2E real (ya todo el código existe).
    S2: Puente orders_auto → deliveries + división 2 operadores (Nivel 1).
    S3: GPS continuo (Traccar) + visualización.
    S4: Motor ETA simple (recta + velocidad medida) + avisos WAHA 3 momentos.
    S5: OSRM/GraphHopper si S4 no da exactitud suficiente.
    ¿Aprobás este orden o WAHA es primero (S4 antes que S2)?

15. Presupuesto de infra: WAHA + Traccar + (opcional) OSRM suman ~2GB RAM y
    3 dockers nuevos en el servidor. ¿OK con el hardware actual?

---

## 5. RIESGOS IDENTIFICADOS

- **Baneo del número secundario** por WhatsApp no-oficial (WAHA) → mitigar con
  número desechable y plan de fallback a plantillas Meta.
- **Choferes sin datos móviles / batería** → tracking intermitente rompe ETA.
- **gps_tracks vacío** → el motor de velocidad histórica necesita 1-2 semanas
  de acumulación antes de ser exacto.
- **Placeholder 111111/222222**: si algún envío de prueba fue a esos chat_ids,
  salió al vacío. No hacer E2E hasta registrar chat_ids reales.

---

*Prometeo · orquestador · modo planificación · 2026-09-27 · 💧*
