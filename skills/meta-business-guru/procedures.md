# Procedimientos step-by-step — Meta WhatsApp Business Cloud API

Contexto: bot Valentina (Estación H2O) sobre Cloud API. Todos requieren sesión
de administrador del portafolio en business.facebook.com / developers.facebook.com.
Regla: Chromium perfil aislado, nunca credenciales personales del Líder en texto.

## a. Regenerar un token expirado

1. Diagnóstico: `curl -s "https://graph.facebook.com/v23.0/me?access_token=$TOKEN"`
   → si `error.code == 190`, el token murió (subcode 463 = expirado, 467 = invalidado).
2. Ir a https://business.facebook.com/settings/ → **Usuarios del sistema**.
3. Seleccionar el usuario del sistema del bot (p.ej. "valentina-bot") →
   verificar en "Activos asignados" que aún tiene la app y la WABA con control total
   (si falta, reasignar: Asignar activos → app → Administrar app; WABA →
   Administrar cuentas de WhatsApp Business).
4. **Generar identificador de acceso** → seleccionar la app → copiar el token.
5. Guardar SOLO en `.env` / variables del servicio (p.ej.
   `WHATSAPP_TOKEN=...` del bridge de Valentina). Rotar el secreto en el
   servidor y reiniciar el servicio.
6. Verificar en vivo: `curl -s "https://graph.facebook.com/v23.0/me?access_token=$NUEVO"`
   → debe devolver data sin error. Luego enviar un mensaje de prueba.
7. NOTA: los tokens de usuario del sistema NO expiran solos; si mueren suele
   ser por cambio de contraseña de un admin del portafolio — anotar la causa.

## b. Verificar y reconfigurar webhook

1. App Dashboard (developers.facebook.com/apps/) → app → **WhatsApp → Configuración**.
2. Verificar Callback URL y Verify token: deben apuntar al endpoint público del
   bot (HTTPS, puerto 443/80, certificado válido — Meta no acepta self-signed).
3. "Probar" (Test): Meta envía el GET de verificación
   `?hub.mode=subscribe&hub.verify_token=X&hub.challenge=Y`; el servidor debe
   responder exactamente `Y` con 200. Si falla: revisar logs del servidor,
   firewall/proxy (nginx), y que el verify token coincida con el del `.env`.
4. Verificar **campos suscritos**: `messages` activo (y opcional
   `message_template_status_update`).
5. Verificar suscripción de la WABA: en la página de la WABA (Business Settings →
   WhatsApp Accounts) debe existir la app como suscriptora. Vía API:
   `GET /{waba-id}/subscribed_apps` con token de app → debe listar la app.
   Si vacío: `POST /{waba-id}/subscribed_apps`.
6. Prueba end-to-end: mandar un WhatsApp al número del bot → confirmar en los
   logs del servidor que llega el payload `object=whatsapp_business_account`
   con `changes[].value.messages`.

## c. Resolver error 190 (token expired / invalid)

- Causa: token inválido, expirado o revocado. Subcodes: 463 expirado,
  467 invalidado (cambio de contraseña / revocación), 190 puro = token mal copiado.
- Fix:
  1. Confirmar subcode con el mensaje del error de la API.
  2. Si 463 (user token de larga duración): regenerar (procedimiento a).
  3. Si 467: revisar quién cambió contraseña de admin; re-emitir token de
     usuario del sistema (procedimiento a) — estos no caducan por tiempo.
  4. Verificar que el token en el `.env` no tenga saltos de línea/espacios
     (error típico al copiar).
  5. Verificar versión de API: si se usa `v19.0` o menor, subir a v23.0
     (versiones viejas se descontinúan y devuelven errores).
  6. Verificación final: GET /me sin error + envío de mensaje de prueba OK.

## d. Resolver error 465 (app does not belong to business)

- Causa: la app que hace la llamada no pertenece al portafolio empresarial dueño
  de la WABA, o la WABA no está asignada a la app.
- Fix:
  1. https://business.facebook.com/settings/ → **Aplicaciones** (Business Apps):
     verificar que la app esté añadida al portafolio. Si no: Añadir → 
     "Crear/App existente".
  2. **Usuarios del sistema** → usuario del bot → **Asignar activos** →
     activar la WABA con "Administrar cuentas de WhatsApp Business" y la app
     con "Administrar app" → Guardar.
  3. En el App Dashboard → WhatsApp → Configuración de la API: verificar que
     el número aparece y el WABA ID coincide con el del portafolio.
  4. Si la app pertenece a OTRO portafolio (p.ej. portafolio personal):
     transferir la app al portafolio correcto (Settings de la app → 
     avanzado / contactar soporte si está en otro dueño), o crear la app dentro
     del portafolio correcto y reconfigurar.
  5. Verificar: `curl -s -X GET "https://graph.facebook.com/v23.0/{WABA_ID}"
     -H "Authorization: Bearer $TOKEN"` → devuelve la WABA sin error.

## e. Pagar facturas pendientes

1. https://business.facebook.com/settings/ → **Facturación** (Billing) del portafolio.
2. Revisar **Saldo de créditos** / estado de la cuenta de anuncios asociada:
   si aparece "Pago pendiente" o saldo negativo, los envíos fallan
   (errores típicos: 132000 "account blocked", o error de facturación en el
   response con `error.type: OAuthException` + mensaje de pago).
3. **Métodos de pago** → añadir/confirmar tarjeta válida (o PayPal si disponible).
4. Pagar el monto pendiente ("Pagar ahora") y esperar que el estado pase a
   activo (suele ser inmediato, hasta 2h en algunos casos).
5. Verificación en vivo: enviar mensaje de prueba por la API → 200 OK.
6. Prevención: activar recarga automática de créditos y alertas de saldo bajo.

## f. Cambiar el número de teléfono asociado

1. App Dashboard → **WhatsApp → Configuración de la API**.
2. Caso A — añadir número nuevo: "Añadir número de teléfono" → elegir país,
   marcar (los números venezolanos requieren pin de 4 dígitos vía SMS/llamada
   si ya tienen WhatsApp activo) → recibir código por SMS/llamada → verificar.
3. Caso B — migrar número desde la app WhatsApp Business (móvil): en la app
   móvil, Ajustes → registrarlo en Cloud API con el código de emparejamiento;
   el número NO puede estar activo en ambos a la vez.
4. El número nuevo arranca en calidad "verde" temporal con límite bajo
   (250 destinatarios únicos/día hasta que suba el tier).
5. Actualizar `phone_number_id` en el `.env`/config del bot (¡el ID cambia!)
   y reiniciar el servicio.
6. Verificación: enviar mensaje de prueba con el nuevo phone_number_id → 200;
   recibir webhook en el servidor.
7. Migración de datos: los metadatos (nombre verificado, quality rating del
   número viejo) no se transfieren; re-verificar perfil del negocio
   (nombre, dirección, horario) en WhatsApp Profile del dashboard.

## g. Activar el botón "Empezar" (Get Started)

Para Cloud API no existe un toggle literal "Empezar" en el dashboard; se logra así:
1. **QR/enlace directo (recomendado, Estación H2O)**: generar
   `https://wa.me/<numero_con_codigo_pais>?text=hola` (texto pre-cargado).
   Imprimir el QR (WhatsApp → Configuración de la API → "Enlaces QR" /
   o cualquier generador de QR) y pegarlo en la estación.
2. **Saludo automático del bot**: programar en el servidor que al recibir el
   PRIMER mensaje (`messages` webhook de un wa_id nuevo) responda con un menú
   interactivo (`type: interactive`, `interactive.type: button` o `list`) con
   opciones: "Pedir botellón", "SWAP", "Precios", "Hablar con humano".
   (Ventana de 24h queda abierta → mensajes libres).
3. **Instagram** (si se activa IG DM): la respuesta "Empezar" / ice breakers se
   configuran vía Instagram Messaging API (payload `ice_breakers` en
   conversaciones) o en la app de Instagram → Ajustes → Mensajes → respuestas.
4. Verificación end-to-end: escanear el QR con un teléfono de prueba →
   enviar el texto pre-cargado → confirmar webhook recibido en el servidor →
   bot responde con el menú.