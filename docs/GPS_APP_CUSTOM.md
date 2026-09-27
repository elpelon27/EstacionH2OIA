# App GPS Custom del Chofer — Especificación (listo para desarrollar)

**Directiva Líder 💧**: app custom simple que reporta cada 45s al endpoint existente.

## Endpoint (VERIFICADO EN VIVO 2026-09-27 — HTTP 200 + fila en gps_tracks)

```
POST http://<servidor>:8000/dispatch/gps
Content-Type: application/json

{
  "vehicle_id": 1,           // 1=YORDANIS, 2=EVERT (tabla vehicles)
  "lat": 10.651,             // float, grados decimales
  "lng": -71.631,
  "accuracy": 8.5,           // opcional, metros
  "speed": 12.3,             // opcional, km/h
  "source": "app",           // libre ("app" recomendado)
  "track_type": "periodic"   // "periodic" para tracking continuo
}
```

Respuesta: `{"success": true, "data": {"in_perimeter": true, ...}}`
El endpoint valida geocerca (13km Maracaibo) y guarda en gps_tracks.

## Comportamiento de la app (checklist para el dev)

1. Al abrir: pedir vehicle_id (o escanear QR con `vehicle_id=N`), guardar localmente.
2. FOREGROUND SERVICE Android: GPS cada **45 segundos** → POST arriba.
3. Reintentos: si falla el POST, encolar en local (máx 200 puntos) y reenviar.
4. Batch permitido: la API acepta 1 punto por POST; enviar en serie está OK a 45s.
5. Botón "Terminar turno" → dejar de enviar (privacidad del chofer).
6. Batería: GPS pasivo/balanced es suficiente (45s no necesita high-accuracy 1Hz).
7. Opción Tasker (sin app): HTTP POST Request cada 45s con %LOC en JSON. Mismo endpoint.

## Qué hay listo en el servidor

- `POST /dispatch/gps` (api/routes/dispatch.py:105) — verificado 200.
- `gps_tracks` con índice por vehículo+tiempo; `source` distingue app/telegram/tasker.
- WAHA (docker `waha`, 127.0.0.1:3000, API key en config/.env WAHA_API_KEY) — listo
  para avisos al cliente cuando llegue la SIM.
- OSRM (docker `osrm`, 127.0.0.1:5000) — Venezuela completo, verificado ruta
  Maracaibo 6.62 km / 10.7 min.

## Próximo paso cuando haya teléfonos

Chofer hace /start a @DespachoH2O_bot → se registra su chat_id real (DT-01) →
instalar app o Tasker con su vehicle_id → verificar gps_tracks se llena cada 45s.

---
💧 Prometeo · 2026-09-27
