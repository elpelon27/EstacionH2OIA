# Capturas Reales de la PWA — POD Digital

Fecha: 2026-09-27 · Prometeo 💧 · Método: Playwright + Chromium headless
(mobile 390×780 @2x, touch habilitado) contra el bridge de producción (:8000).

## Capturas obtenidas (docs/screenshots/)

| Archivo | Pantalla | Contenido verificado |
|---|---|---|
| pod_01_pin.png | PIN del chofer | Overlay de PIN, campo 4 dígitos, contador de intentos |
| pod_02_datos.png | Datos de entrega | Cliente real (Luis M.), productos AGUA+HIELO, total €4.20, cédula, vacíos/tapas |
| pod_03_firma.png | Canvas de firma | Trazo real dibujado (verificado píxel a píxel antes de capturar) + botones de acción |
| pod_04_exito.png | Confirmación | "✅ Sincronizado — Nota registrada (POD #31)" tras POST /api/pod/submit 200 |

El flujo capturado es E2E real: PIN válido → carga de datos por API → firma
dibujada con eventos pointer → cédula → Confirmar → submit HTTP 200 →
pod_record firmado en dispatch.db (firma base64 > 1KB verificada).

## Datos de test usados y limpieza

- Delivery #9999 (client 1206 Luis M., 3 AGUA) + pod_record → BORRADOS.
- Odoo quedó en 0 movimientos / 0 pagos (verificado tras limpieza).
- Nota: el cron fs_odoo_sync (*/15) alcanzó a crear 21 invoices de los pedidos
  basura ANTES de la purga de Fase 5.0; se purgaron también de Odoo.

## BUG REAL encontrado y corregido durante las capturas

Al cargar, la PWA ajusta el canvas mientras la app está oculta detrás del
PIN (display:none → width=0). En un celular real la firma saldría VACÍA y el
submit fallaría con 400 "Firma requerida para status=signed".

Fix (web/pod_form.html): al validar el PIN y mostrar la app se re-dispara
`window.dispatchEvent(new Event('resize'))` para que el canvas ajuste su
tamaño real. Documentado como desviación de la regla "no tocar la PWA":
era un bug de producción que bloqueaba el entregable.

## Plan B — capturas manuales desde el celular (si se quieren "de verdad")

Las capturas de arriba son del navegador headless del servidor. Para el
Líder, verlo en el celular real:

1. Crear un delivery de test (o esperar uno real de la ruta del día).
2. Abrir Chrome (Android):
   `http://valentina.estacionh2o.com:8000/pod/<delivery_id>?token=<POD_VEHICLE_TOKEN>`
3. Flujo: PIN (POD_CHOFER_PIN del config/.env) → datos → firmar con el dedo
   → (opcional foto con la cámara) → Confirmar → "✅ Sincronizado".
4. Capturas de pantalla Android: botón encendido + volumen abajo
   (o gesto de 3 dedos según el equipo).
5. Enviarse las 4 capturas por Telegram/WhatsApp y guardarlas en
   docs/screenshots/ si se quiere reemplazar las del servidor.

## Script reutilizable

```bash
# requiere: venv/bin/pip install playwright && venv/bin/playwright install chromium
# fixture: delivery + pod_record con client 1206 (ver dev/capturas_pwa.py)
venv/bin/python dev/capturas_pwa.py
```
