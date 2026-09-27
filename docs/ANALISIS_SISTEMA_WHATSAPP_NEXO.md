# Análisis del Sistema WhatsApp NEXO y Rediseño de Flujo (GPS primero)

**Última actualización**: 2026-09-27
**Autor**: Prometeo
**Fuente**: Verificación en vivo (código + BDs + Qdrant) — 2026-09-27
**Repo**: https://github.com/EstacionH2O/EstacionH2OIA (branch `feat/odoo-r4-integration`)

---

## 1. Qué era NEXO y dónde está su configuración

NEXO **no es una herramienta ni un archivo de configuración**: es el nombre interno del
**plan de mejoras UX del bot Valentina**, organizado en lotes P0/P1/P2. Su "config" está
distribuida en:

| Componente | Ubicación | Contenido |
|---|---|---|
| Definición del plan / system prompt | `docs/01-proyecto/SOUL-valentina.md` (v5, "NEXO UX P0/P1/P2 + Named Tunnel") | Personalidad y reglas UX |
| Implementación | `api/bridge.py` (~3.679 líneas, FSM + NEXO P0/P1/P2 en comentarios) | `# NEXO P0: Botones fantasma`, `# NEXO P1: Error recovery`, etc. |
| Historial de aplicación | Commits 47eab16 (P0), 3912527 (P1), 58c7980 (P2) — 17 jul | Notas de voz, finalización cálida, vocabulario |
| Contexto de migración | `docs/03-sesiones/Migracion-Hermes-Prometeo-Contexto.md` | Resumen NEXO aplicado |

**No está en Dify** (Dify solo es el backend LLM de respaldo en
`http://localhost/v1/chat-messages`), ni en `src/integrations/` (que solo contiene
`odoo/`, `r4/`, `tests/`). La lógica de conversación es **determinística en bridge.py**
(Dify se usa como fallback).

### Qué incluye NEXO hoy (verificado en bridge.py)
- **P0 Botones fantasma**: salidas elegantes ("gracias" tras pedido, texto libre en `menu_sent`).
- **P0 Notas de voz**: redirige a texto ("Prefiero leer su mensaje escrito…").
- **P1 Error recovery**: no repetir el mismo mensaje, lenguaje cálido al fallar la dirección.
- **P1 "volver"/"menu"**: reinicia al menú desde cualquier estado.
- **P1 Finalización completa**: qué se hizo + qué sigue + cómo volver.
- **P2 Vocabulario cálido**: tono 💧 de Valentina.

### Geocerca: estado real (verificado en vivo 2026-09-27)
- `scripts/security/geofence.py` — geocerca POLIGONAL completa: `check_location()`
  (ray casting), `future_zone_customers`, mensaje "no atendemos tu zona".
- Endpoint expuesto: `api/routes/dispatch.py` → `POST /geofence/check`.
- **CRÍTICO**: `check_location()` **NO está cableado en el flujo del bot**
  (`api/bridge.py` no la invoca). Y **no hay polígono activo** en `security.db`
  (`get_active_polygon() = None`; sin polígono devuelve `sin_geocerca` y no bloquea).
- La FSM actual pide GPS solo en `awaiting_address`, DESPUÉS de elegir productos.

## 2. Flujo actual (verificado)

```
┌─────────────┐
│  Hola/Inicio │
└──────┬──────┘
       ▼
┌─────────────────────────────────────┐
│ Menú lista (menu_sent)              │
│ 1 Recarga botellones (€1.00)        │
│ 2 Hielo (€1.20)                     │
│ 3 Combinado                         │
│ 4 Consultar estado                   │
│ 5 Otra consulta                     │
└──────┬──────────────────────────────┘
       ▼  (o pedido directo por texto: "3 botellones")
┌──────────────────────┐   mínimo 3 bot / 2 hielo (combinado)
│ Validar cantidad     │──────────❌──> pedir ajuste
└──────┬───────────────┘
       ▼
┌──────────────────────┐
│ awaiting_address     │  ← aquí llega el GPS (location) o texto
│ (GPS + edificio +    │     ⚠ SIN VALIDACIÓN DE GEOCERCA
│  punto de referencia)│     ⚠ SIN POLÍGONO ACTIVO EN BD
└──────┬───────────────┘
       ▼
┌──────────────────────┐
│ awaiting_payment     │  💳 Pago Móvil | 💵 Efectivo
└──────┬───────────────┘
       ▼  (Pago Móvil → datos bancarios → "✅ Ya pagué")
┌──────────────────────┐
│ awaiting_confirmation│  → dispatch_queue + dispatch.db
└──────┬───────────────┘     → asignación vehículo + chofer
       ▼
┌──────────────────────┐
│ completed            │  (NEXO P1: cierre cálido)
└──────────────────────┘
```

**Brechas detectadas**: la geocerca se verifica (si acaso) demasiado tarde y el bot
gasta interacciones con clientes fuera de zona; además hoy no se aplica en absoluto.

## 3. Flujo propuesto (directiva del Líder: GPS primero)

```
┌─────────────┐
│  1era msg    │
└──────┬──────┘
       ▼
┌───────────────────────────────────────────────┐
│ 📍 "Para atenderle, primero envíe su          │
│     ubicación por GPS" (state=gps_required)  │
└──────┬────────────────────────────────────────┘
       ▼  location recibida
┌───────────────────────────────────────────────┐
│ check_location(phone, lat, lng)               │
│ (scripts/security/geofence.py, ya existe)     │
└──────┬───────────────────────┬────────────────┘
   DENTRO                  FUERA
       │                       │
       ▼                       ▼
┌──────────────────┐  ┌────────────────────────────────┐
│ Menú actual       │  │ MSG_FUERA_ZONA + número a       │
│ (botellones,     │  │ future_zone_customers +         │
│  hielo, estado…)  │  │ TERMINAR conversación          │
└──────┬───────────┘  │ (state=completed, sin menú)    │
       ▼              └────────────────────────────────┘
│ awaiting_address  │  ← GPS ya validado; pedir solo
│ (edificio +       │     edificio/referencia
│  referencia)      │
       ▼
│ awaiting_payment  │ → (igual que flujo actual)
       ▼
│ awaiting_confirmation → dispatch → completed
```

Cambios de código necesarios (bridge.py):
1. Nuevo estado inicial `gps_required` en `_handle_deterministic` (state None → pedir
   ubicación en vez de menú).
2. En el handler `msg_type == "location"`: si estado `gps_required`, llamar
   `check_location()`; si `fuera` → responder `MSG_FUERA_ZONA`, `_clear_state`,
   no mostrar menú; si `ok` → continuar a menú.
3. En `awaiting_address`: GPS ya validado → pedir solo edificio/referencia (evita
   re-pedir ubicación, hoy redundante).
4. Prerequisito: **cargar el polígono activo** en `security.db` (`set_polygon()`)
   — hoy no existe, sin él `check_location` devuelve `sin_geocerca` y no bloquea.

## 4. Análisis del sistema actual y 3 mejoras propuestas

Sistema: WhatsApp (Meta Cloud API) → cloudflared → uvicorn bridge.py (FSM determinista
+ Dify fallback) → dispatch_queue/conversations.db → dispatcher → chofer; clientes en
dispatch.db + Odoo; pagos R4/pago móvil. FSM en SQLite por phone_hash.

### Mejora 1 — GPS-primero con geocerca cableada (esta tarea)
Impacto: cero conversaciones desperdiciadas con clientes fuera de zona; datos limpios
en `future_zone_customers` para expansión; dirección y zona ya verificadas antes de
tomar el pedido. Costo: ~4 puntos de código (arriba). Riesgo bajo: `sin_geocerca`
es fail-open si el Líder no carga polígono.

### Mejora 2 — Diferir la recolección del resto de la dirección
Hoy se pide GPS + edificio + referencia juntos en un solo mensaje y el cliente suele
mandar solo el GPS (address queda "Mi ubicación: GPS: lat,lng"). Mejor: al recibir GPS
validado, autocompletar `zone_id` y pedir UN solo mensaje corto de referencia; usar
reverse-geocoding local (Nominatim cache) solo si el cliente no completa. Reduce un
ciclo de ida-vuelta por pedido y mejora la calidad de `address_text` para el chofer.

### Mejora 3 — Recordatorio de clientes fuera de zona (activar código muerto)
`future_zone_notify_pending()` ya existe pero nadie lo llama. Crear job semanal que
notifique cuando se expanda el polígono: convierte rechazos en clientes futuros con
cero código nuevo (solo un cron + plantilla de mensaje). Complemento UX: incluir en
MSG_FUERA_ZONA la oferta "te avisamos cuando lleguemos a tu zona" con botón de
confirmación (opt-in explícito).

Otras observaciones (no bloqueantes): las notas de voz se descartan pidiendo texto
(P0 correcto para 40+, pero un stt local sería la evolución natural); el tar de
respaldo de la exportación iPhone ya no es necesario en /tmp tras purga (ver §5).

## 5. Depuración de conversaciones WhatsApp (TAREA 1)

- Origen: `/mnt/ssd_trabajo/imports/iphone_whatsapp/output/` — 2,2 GB verificados
  (no 1,6 GB como se estimaba): `decrypted_db/`, `wa_domain_files/`,
  `wbc_result/`, `result.json` (ChatStorage.sqlite 36 MB x2, Biz.sqlite 12 MB x2,
  cientos de MB de mp4 duplicados).
- Previo a borrar se verificó EN VIVO: Qdrant colección `whatsapp_patterns`
  = **219 puntos, status green** (curl localhost:6333, 2026-09-27).
- Backup íntegro: `/tmp/iphone_whatsapp_output_20260927_093411.tar` (2,1 GB,
  61.885 archivos, `tar -df` sin diferencias).
- Originales ELIMINADOS del SSD. Espacio liberado: **2,0 GB** (df: 120G → 118G usados,
  751G → 753G libres en /mnt/ssd_trabajo).
- Ojo: el tar en `/tmp` está en el disco raíz (82% usado). Eliminar tras confirmar
  que los patrones bastan; los archivos crudos solo sirven para re-extracción.

---
💧
