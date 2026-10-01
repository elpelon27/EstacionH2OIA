---
tags: [fase3, waha, anti-ban, rotacion, whatsapp, pod, operaciones]
fecha: 2026-09-30
estado: implementado-verificado
---

# Vinculación WAHA + Rotación Anti-Ban (Fase 3)

## Regla crítica del Líder (implementada)

Una entrega **NO** mezcla números de WhatsApp. Todos los mensajes de una misma
entrega (cerca, llegada, esperando, PDF firmado) salen del mismo chip. Lo que
rota es el **texto**, no el número.

```
Entrega del chofer 1 → chofer_1 para TODO (4 mensajes)
Entrega del chofer 2 → chofer_2 para TODO (4 mensajes)
```

Así se reparte tráfico entre 2 números sin que el cliente perciba inconsistencia.

## Endpoints WAHA reales (VERIFICADOS 2026-09-30 contra WAHA 2026.9.1 WEBJS/CORE)

El plan original tenía endpoints incorrectos. Correcciones:

| Paso | Plan original | Real (verificado) |
|---|---|---|
| QR | `GET /api/sessions/{n}/qr` → **404** | `GET /api/{n}/auth/qr` → **200 image/png** |
| QR formato | base64 JSON | **PNG binario directo** (`format=image` o default; `format=raw` da JSON con `value`) |
| Crear sesión | `POST /api/sessions` | `POST /api/sessions` ✅ correcto |
| Start | (no previsto) | **`POST /api/sessions/{n}/start`** — obligatorio, en STOPPED el QR da 422 |
| Estado | `GET /api/sessions/{n}` | ✅ correcto, `status=WORKING` |

Secuencia validada end-to-end: `POST /api/sessions` → `POST /api/sessions/{n}/start`
→ esperar `STARTING` → `GET /api/{n}/auth/qr` → PNG 4739 bytes → polling → `WORKING`.

## Artefactos

- `scripts/waha_link_device.sh <session>` — vincula un número: crea, arranca,
  obtiene QR, lo manda por Telegram, hace polling 5 min, reporta OK/timeout.
  Idempotente (si ya está WORKING avisa y sale).
- `scripts/waha_client.py` — `send_message_for_delivery()` con rotación.

## Datos de entorno verificados (primera mano, no inferidos)

- Contenedor `waha` (devlikeapro/waha:latest) Up, puerto 3000.
- API key real en `config/.env:95` (`WAHA_API_KEY`). Sin exportar da 401.
- Estado inicial: **`GET /api/sessions` → `[]`** (cero números vinculados).
- `@Skynet_27_bot` = `TELEGRAM_BOT_TOKEN` (getMe OK, username `Skynet_27_bot`).
- Chat del Líder `1663148211` = Luis Martinez (@elpelon27). Verificado con getChat.
- `vehicle_id` SÍ existe en el schema: `deliveries.vehicle_id` (col 3) y
  `pod_records.vehicle_id` (col 17).
- `vehicles`: 1 = Triciclo 1 / YORDANIS, 2 = Triciclo 2 / EVERT (ambos activos).

## API de la rotación

```python
from scripts.waha_client import session_for_vehicle, send_message_for_delivery

session_for_vehicle(1)          # 'chofer_1' — determinista, nunca aleatorio
send_message_for_delivery(
    phone="+584141234567",
    text_type="AVISO_LLEGADA",  # AVISO_CERCA|AVISO_LLEGADA|AVISO_ESPERANDO|PDF_FIRMA
    vehicle_id=1,
    delivery_id=555,
)  # → {'sent':..., 'session':'chofer_1', 'variant':2, 'delivery_id':555, ...}
```

5 variaciones por tipo, elegidas con `random.randrange` por envío.
Fail-open: nunca lanza; si WAHA no responde, el PDF queda en `data/pod_pdfs/`.

## Verificación ejecutada

- `bash -n scripts/waha_link_device.sh` → OK
- 5 variaciones exactas y sin duplicados en los 4 tipos → OK
- 200 llamadas por vehículo → **siempre la misma sesión** (REGLA CRÍTICA cumplida)
- `chofer_1 != chofer_2` → tráfico distribuido
- Rotación 200 muestras: las 5 variaciones usadas, distribución pareja
- Envío real a WAHA vivo con sesión `chofer_1` recién creada → HTTP 422
  (sesión sin escanear) con `session='chofer_1'`, `variant=2`, `delivery_id=555`
  → la petición llegó al servidor con los metadatos correctos
- Limpieza posterior: `[]` sesiones (no quedó basura)

## Pendiente / deuda técnica

- ⚠️ `tests/unit/test_pod_waha_fase2.py` rompe en **colección**: fixture busca
  tabla `deliveries` en otra DB. **PREEXISTENTE** — verificado: falla idéntico
  en HEAD limpio con `git stash`. Tech debt aparte, fuera del alcance de esta tarea.
- `waha_client.py` usa defaults `chofer_1`/`chofer_2`; sobreescribibles con
  `WAHA_SESSION_VEHICLE_1` / `WAHA_SESSION_VEHICLE_2` / `WAHA_SESSION_FALLBACK`.

---

# Actualización 2026-10-01 — vinculación REAL completada

## ⚠️ Hallazgo crítico: el QR de WAHA está ROTO en este build

El flujo QR documentado arriba **falla en producción**. Error real en los logs
del contenedor:

```
[W] Error Error [TypeError]: window.require(...).Cmd.refreshQR is not a function
```

Causa: WAHA 2026.9.1 (engine WEBJS) carga WhatsApp Web `2.3000.1048901417`,
versión donde Meta ya no expone `Cmd.refreshQR`. Sin refresco, el QR expira
(~40 s) y WhatsApp muestra **"NO SE PUDO VINCULAR DISPOSITIVO"**.

Descartado como causa: desfase de reloj (host y contenedor sincronizados en UTC).

Dos intentos de QR con espera de 5 minutos terminaron en timeout con estado
`SCAN_QR_CODE` sostenido (nunca llegó a `WORKING`).

## ✅ Solución que SÍ funcionó: código de emparejamiento (pairing code)

Endpoint verificado:

```
POST /api/{session}/auth/request-code
{"phoneNumber":"584222560722","codeMethod":"SMS"}
→ 201 {"code":"86FJ-JWHD"}
```

**Ventaja clave para la regla crítica del Líder:** el pairing code va ligado al
número de teléfono enviado en `phoneNumber`. No es un QR genérico que pueda
escanear cualquiera — si el código se genera para `584222560722`, solo ese
número puede completar la vinculación. La correspondencia sesión↔chofer queda
garantizada por construcción, no por confianza.

Proceso en el celular: WhatsApp → Dispositivos vinculados →
**Vincular con número de teléfono** → ingresar el número → el código de 8
caracteres aparece para autorizar.

## Estado final VERIFICADO (2026-10-01)

```
chofer_1  status=WORKING  numero=584222560722@c.us  push=Estacionh20   (Yordanis)
chofer_2  status=WORKING  numero=584222560723@c.us  push=Estacionh2o   (Evert)
```

Verificación cruzada contra los números de la directiva: **AMBOS CORRECTOS**.
Ningún número duplicado entre sesiones.

## Prueba de envío REAL con los chips vinculados

```
AVISO_CERCA   entrega=9001 vehiculo=1 → sesión=chofer_1 variación 5/5 → sent=True HTTP 201
AVISO_LLEGADA entrega=9002 vehiculo=2 → sesión=chofer_2 variación 1/5 → sent=True HTTP 201
```

Cada entrega sale de su propio chip y el texto rota. Fail-open intacto.

## Nuevo script

`scripts/verify_waha_sessions.py` — verifica que cada sesión tenga el número
correcto del chofer y que no haya números duplicados. Exit 0 = todo correcto.

```
./venv/bin/python scripts/verify_waha_sessions.py
```

Útil para correr antes de cada jornada o tras un reinicio del contenedor.

## Recomendación

Considerar migrar a la imagen `devlikeapro/waha:gows-2026.9.1` (engine GOWS,
disponible en el registry) si el QR vuelve a necesitarse. GOWS no depende del
DOM de WhatsApp Web y es más resistente a estos cambios. **No se hizo ahora**
porque el pairing code resolvió la vinculación sin downtime y el contenedor
`waha` no está en ningún compose ni systemd (fue lanzado manualmente) —
recrearlo era un riesgo innecesario. Estado del contenedor documentado en este
archivo por si hay que reconstruirlo:

```
IMAGE  devlikeapro/waha:latest
BINDS  /mnt/ssd_trabajo/waha:/sessions
PORTS  127.0.0.1:3000->3000/tcp
ENV    WHATSAPP_DEFAULT_ENGINE=WEBJS, WAHA_GOWS_PATH=/app/gows,
       WAHA_GOWS_SOCKET=/tmp/gows.sock, WHATSAPP_API_KEY (config/.env:95)
NET    bridge    RESTART  unless-stopped
```
