# POD PWA — Guía de Testeo Manual (Bloque 3)

Fecha: 2026-09-27 · Prometeo 💧 · Estado: E2E verificado en vivo

## Arquitectura de la prueba

- PWA: `web/pod_form.html`, servida por el bridge en `GET /pod/{delivery_id}?token=XXX`
- API: `GET/POST /api/pod/*` (api/pod_router.py)
- Bridge producción: `valentina-bridge.service`, puerto 8000
- Credenciales de test en `config/.env`: `POD_VEHICLE_TOKEN`, `POD_CHOFER_PIN`

## 1. Preparar un delivery de test

```bash
cd /mnt/ssd_trabajo/hermes-agent
sqlite3 data/dispatch.db "INSERT INTO deliveries
  (dispatch_session_id, client_id, vehicle_id, order_sequence, status, bottles_full)
  VALUES (1, (SELECT id FROM clients LIMIT 1), (SELECT id FROM vehicles LIMIT 1),
  995, 'pending', 2);
SELECT last_insert_rowid();"   # anota el ID, ej: 1211
```

## 2. Abrir la PWA (en el celular del chofer o navegador)

```
http://valentina.estacionh2o.com:8000/pod/<ID>?token=<POD_VEHICLE_TOKEN>
```

Verificar en cada paso:
1. Pantalla de PIN aparece → ingresar `POD_CHOFER_PIN` (4 dígitos) → entra a la app.
2. Header muestra cliente y dirección.
3. Tabla de productos con total (AGUA 2 x 1.00 = 2.00 EUR).
4. Si el cliente tiene crédito: banda amarilla "Saldo anterior" (render server-side).
5. Token inválido → "⛔ Acceso denegado".

## 3. Flujo de firma (caso normal)

1. Escribir cédula (ej: V-11222333).
2. Firmar con el dedo en el canvas → trazo visible.
3. Botón "Borrar firma" limpia el canvas.
4. (Opcional) "📷 Tomar foto" → preview visible.
5. Llenar vacíos recibidos / tapas.
6. "✅ Confirmar Entrega" → mensaje verde "✅ Sincronizado — Nota registrada (POD #X)".

Verificar en el servidor:
```bash
sqlite3 data/dispatch.db "SELECT id, pod_status, client_cedula, synced_to_odoo
  FROM pod_records WHERE delivery_id=<ID>;"
# Esperado: pod_status=signed, synced_to_odoo=0 (worker Bloque 4 sincroniza a Odoo)
ls data/pod_photos/ | grep <ID>   # foto en disco si se tomó
```

## 4. Casos alternativos

- **Cliente no firma**: solo foto → "📷 Cliente no firma — Tomar foto" → pod_status=photo_only.
  Sin foto el botón muestra error (foto obligatoria).
- **Cliente rechaza**: foto + confirmación → pod_status=refused.
- **Sin cédula o sin firma** al confirmar → mensajes de validación, no envía.

## 5. Simular OFFLINE (verificado en vivo 2026-09-27)

La PWA guarda en IndexedDB (base `pod_offline`, store `pendientes`, key=delivery_id) si el POST falla.

Opción A — modo avión del celular: llenar todo, Confirmar →
"✅ Guardado local — Pendiente sync". Al recuperar señal (evento `online`
o al reabrir la PWA) reenvía automáticamente → "✅ Sincronizado" y borra de IndexedDB.

Opción B — en servidor, probar que la cola funciona (hecho en vivo):
```bash
# 1. Levantar una instancia de test en 8123
cd api && POD_VEHICLE_TOKEN=... POD_CHOFER_PIN=... LOG_SALT=... \
  ../venv/bin/uvicorn bridge:app --host 127.0.0.1 --port 8123 &
# 2. Submit online OK → pod_id X
# 3. kill -9 <pid>  → curl devuelve code=000 (sin conexión real)
# 4. La PWA en este estado guarda en IndexedDB (imposible llegar al server)
# 5. Relanzar uvicorn → reenvío del pendiente OK → pod_status=signed
```
Verificado: submit online → server muerto (code 000) → server arriba → reenvío con
`offline_created=1` aceptado → `pod_records` queda signed/synced_to_odoo=0.

Nota: la PWA también cachea los datos de la entrega en localStorage
(`pod_cache_<id>`) para poder abrir la nota SIN conexión si ya se cargó una vez.
El PIN offline se valida contra el último PIN correcto cacheado (localStorage).

## 6. PIN — bloqueo (verificado en vivo)

3 intentos fallidos → "⚠️ Acceso bloqueado. Se notificó al operador." y el
endpoint responde 423. La PWA llama a `/api/pod/pin_failed/<id>` que alerta
al operador vía Telegram si `TELEGRAM_ALERT_CHAT`/`TELEGRAM_ALERT_TOKEN`
están configurados en config/.env.

## 7. Test automático (regresión)

```bash
venv/bin/python tests/unit/test_pwa_bloque3.py      # PWA + PIN + E2E navegador simulado
venv/bin/python tests/unit/test_pod_endpoints_bloque2.py  # endpoints base
venv/bin/python tests/unit/test_pod_bloque2.py      # botón Entregado → pod_record
```
Todos ALL_PASSED contra dispatch.db real con cleanup.

## Limpieza post-test

```bash
sqlite3 data/dispatch.db "DELETE FROM pod_records WHERE delivery_id=<ID>;
  DELETE FROM deliveries WHERE id=<ID>;"
rm -f data/pod_photos/pod_<ID>_*.jpg
```
