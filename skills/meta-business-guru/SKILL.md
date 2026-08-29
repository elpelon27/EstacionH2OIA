---
name: meta-business-guru
description: "Administrar WhatsApp Business Cloud API de Meta."
version: 1.0.0
license: MIT
---

# Meta Business Guru — WhatsApp Business Cloud API + Instagram

Skill de referencia para administrar la plataforma WhatsApp Business (Cloud API) de
Meta desde el dashboard de desarrolladores. Contexto de la Estación H2O: el bot
Valentina corre sobre la Cloud API (token de usuario del sistema).

Reglas de seguridad:
- Chromium con perfil aislado; NUNCA loguearse en cuentas personales del Líder.
- Solo extraer documentación pública.
- Nunca escribir tokens en el repo; van en `.env` o variables del servicio.

## 1. Navegar el Meta Dashboard (developers.facebook.com)

1. https://developers.facebook.com/apps/ → lista de apps del portafolio.
2. Abrir la app (p.ej. la de Valentina) → menú lateral izquierdo:
   - **Panel de la app** (App Dashboard): resumen de estado, alertas, productos añadidos.
   - **WhatsApp > Configuración de la API** (API Setup): números, phone_number_id,
     ID de cuenta WhatsApp Business (WABA), token temporal de prueba, envío de mensajes de prueba.
   - **WhatsApp > Empezar** (Getting Started / Quickstart): guía paso a paso.
3. Roles y permisos: **Roles de la app** (App Roles) — administradores, desarrolladores,
   testers. Permisos: **Permisos y funciones** (Permissions & Features):
   whatsapp_business_messaging, whatsapp_business_management, business_management,
   instagram_basic, instagram_manage_messages (para IG DM), etc.
   Los permisos avanzados requieren revisión de la app (App Review) para producción.
4. Configuración general: **Configuración > Básica** (Settings > Basic):
   App ID, App Secret, dominios, URL de política de privacidad (obligatorio para
   pasar a modo producción).

Modo Dev vs Producción: una app en Development solo permite messaging a
administradores, testers y números de prueba. Para producción: cambiar el toggle
a "En vivo" (Live) tras completar requisitos (política de privacidad, ícono, etc.).

## 2. Dónde está la configuración de webhook

Ruta: App Dashboard → **WhatsApp → Configuración** (Configuration). Sección
"Webhook" con dos cosas:
1. **Callback URL** + **Verify token**: la URL pública del endpoint (p.ej. el
   bridge de Valentina) y un string compartido. Meta hace GET con
   `hub.mode=subscribe&hub.verify_token=<token>&hub.challenge=<challenge>`;
   el servidor debe responder con `hub.challenge` tal cual (HTTP 200).
2. **Suscripciones de campos (Webhook fields)**: activar `messages` (imprescindible),
   y opcionalmente `message_template_status_update` (aprobación/rechazo de
   plantillas) y `template_category_update`.
   IMPORTANTE: el webhook se configura por app, pero se añade la WABA como
   suscriptor (botón "Suscribirse al webhook" en la página de la WABA /
   Business Settings → WhatsApp Accounts).

Endpoints de gestión vía API:
- `POST /{waba-id}/subscribed_apps` — suscribir la app a la WABA.
- `GET /{app-id}/subscriptions?object=whatsapp_business_account` — verificar campos suscritos.
- `GET /{phone-number-id}/whatsapp_business_account` — verificar la WABA de un número.

## 3. Generar / regenerar tokens de acceso

Tipos de token:
- **Temporal (test)**: App Dashboard → WhatsApp → API Setup → "Generar identificador
  de acceso" (expira en ~24h). Solo para pruebas.
- **Usuario del sistema (permanente, recomendado para producción)**:
  https://business.facebook.com/settings/ → **Usuarios del sistema** (System Users) →
  seleccionar/crear usuario → **Asignar activos** (Assign Assets): la app con
  "Administrar la app" (Full control) y la WABA con "Administrar cuentas de WhatsApp
  Business" → **Generar identificador de acceso** (Generate access token) con permisos:
  business_management, whatsapp_business_messaging, whatsapp_business_management.
  Este token NO expira por sí solo (puede ser invalidado por cambio de contraseña de
  administradores o revocación manual).
- **Token de usuario** (User token): expira; prolongable vía extensión de token
  de larga duración (~60 días) — NO recomendado para bots.

Verificación: `GET https://graph.facebook.com/v23.0/me?access_token=<TOKEN>` →
debe devolver el App ID/data. Si devuelve error 190 → token inválido/expirado (ver procedures.md c).

## 4. Verificar el estado de la cuenta WhatsApp Business

1. **Calidad de la cuenta (Quality rating)**: App Dashboard → WhatsApp →
   Configuración de la API → panel "Calidad" del número, o Business Settings →
   WhatsApp Accounts → ver detalle del número. Niveles: Verde (High), Amarillo
   (Medium), Rojo (Low). Si cae a rojo por reportes/bloqueos → límites de envío reducidos.
2. **Estado del número**: verde = conectado y verificado; verificar que el
   número no esté "pendiente de verificación" ni migrado a otra app.
3. **Límites de messaging (messaging limit tier)**: 1k / 10k / 100k / ilimitado
   destinatarios únicos/día según calidad y volumen.
4. Vía API: `GET /{phone-number-id}?fields=verified_name,quality_rating,
   display_phone_number,webhook_verification_status` con token de la app
   (necesita whatsapp_business_management).
5. Bloqueos/flags de la app: dashboard → "Cumplimiento normativo"
   (App Compliance) y avisos en la parte superior del dashboard.

## 5. Gestionar plantillas de mensajes (message templates)

UI: App Dashboard → **WhatsApp → Plantillas de mensajes** (Message Templates).
- Crear: nombre (solo minúsculas/guiones bajos), categoría (MARKETING, UTILITY,
  AUTHENTICATION), idioma (es), cuerpo con variables {{1}}, {{2}}, ejemplos
  obligatorios, botones (quick reply, URL, phone, flow, copy code, marketing opt-out).
- Estados: ENVIADA (submitted) → APROBADA / RECHAZADA / PAUSED. Meta revisa en
  minutos–24h. El resultado llega por webhook `message_template_status_update`.
- Edición de plantillas aprobadas: crear una nueva versión (no se puede editar
  el cuerpo de una aprobada sin re-revisión).
- API equivalente (Business Management API):
  `POST /{waba-id}/message_templates`, `GET /{waba-id}/message_templates`,
  `DELETE /{waba-id}/message_templates?hsm_id=<id>`, y para enviar:
  `POST /{phone-number-id}/messages` con `{"type":"template","template":{...}}`.
- Fuera de la ventana de 24h SIEMPRE se requiere plantilla aprobada.

## 6. Configurar el botón de inicio (Get Started / Empezar)

Opciones de arranque de conversación:
1. **CTA en el enlace wa.me / QR**: `https://wa.me/<número>?text=hola` abre el
   chat con un mensaje pre-cargado — el "get started" más simple y lo que
   Valentina usa: imprimir QR con ese link.
2. **Mensaje de bienvenida**: en Cloud API el flujo se maneja en tu propio
   servidor: cuando llega el primer `messages` webhook del usuario, el bot
   responde (ventana 24h abierta).
3. **Botones de lista/respuesta rápida** en el primer mensaje de respuesta del
   bot para guiar al usuario (payload: interactive type=list o button).
4. **Flows / plantilla con botón**: si el usuario inicia por plantilla
   MARKETING con botón, el click llega como webhook `button_reply`.
5. Instagram equivalente: respuesta automática "Empezar" (Get Started) se
   configura en la app de Instagram (Ajustes → Mensajes) o vía
   Instagram Messaging API con payload `ice_breakers`.

## 7. Leer la facturación y pagos

1. **Dónde**: https://business.facebook.com/settings/ → sección **Facturación**
   (Billing) del portafolio empresarial. Muestra cada conversación/cargo por
   categoría (utility/marketing/authentication/service — las conversaciones
   iniciadas por el cliente en la ventana 24h son servicio = gratis).
2. **Método de pago**: Facturación → Métodos de pago → añadir tarjeta
   (o PayPal donde esté disponible). El cobro es por conversación entregada,
   según tarifa del país (revisar tarifa vigente en
   https://business.facebook.com/whatsapp/pricing — hay cambios periódicos).
3. **Créditos**: los créditos de la cuenta se consumen automáticamente; sin
   saldo → fallan los envíos con error de facturación (ver procedures.md e).
4. **Descarga de facturas**: Facturación → Historial → exportar CSV/PDF.
5. Si el envío falla con error 132000 (cuenta temporalmente bloqueada por
   falta de pago) → pagar la factura pendiente primero.

## 8. WhatsApp Business App vs WhatsApp Cloud API

| Aspecto | WhatsApp Business App (móvil) | Cloud API (la que usa Valentina) |
|---|---|---|
| Qué es | App móvil/web gratuita para pequeños negocios | API programable alojada en Meta; se paga por conversación |
| Dispositivos | 1 dispositivo + hasta 4 vinculados | Sin teléfono: número virtual gestionado vía API |
| Automatización/bots | Limitada (respuestas automáticas simples, etiquetas, catálogo) | Total: webhooks, plantillas, integración con Odoo, chatbots, flows |
| Límites | Envíos manuales; riesgo de ban por spam | Tiers por calidad (1k→ilimitado únicos/día) |
| Costo | Gratis | Por conversación iniciada por plantilla (tarifa por país/categoría); respuestas dentro de 24h gratis |
| Migración | — | Se puede migrar un número de la App a la Cloud API (el número NO puede estar activo en ambos a la vez) |
| Ideal para | Negocio pequeño sin automatización | Estación H2O: bot con inventario, pedidos, SWAP de loaners |

## Pasos clave extraídos de la doc oficial (Get Started, actualizado jun-2026)

Fuente: https://developers.facebook.com/docs/whatsapp/cloud-api/get-started
(verificada en vivo con navegador el 2026-08-28)

1. **Crear app de Meta con WhatsApp**: developers.facebook.com/apps → Crear
   aplicación → caso de uso "Conecta con los clientes a través de WhatsApp" →
   elegir portafolio empresarial → Crear aplicación.
2. **Empezar a usar la API**: botón "Empezar a usar la API" → conectar la app a
   una cuenta de WhatsApp Business (existente o nueva) → guardar el WABA ID.
3. **Enviar y recibir mensajes**: "Generar identificador de acceso" (temporal) →
   número De / número Para → Enviar mensaje → responder desde el teléfono para
   abrir la ventana de 24h. Guardar phone_number_id y WABA ID.
4. **Configurar webhook de prueba**: endpoint que reciba el GET de verificación
   (hub.challenge) y cargas JSON con object=whatsapp_business_account, entry[],
   changes[].value.messages. Activar campo `messages`.
5. **Usuario del sistema + token permanente**: Business Settings → Usuarios del
   sistema → Añadir → Asignar activos (app: Administrar app; WABA: Administrar
   cuentas de WhatsApp Business) → Generar identificador con permisos
   business_management, whatsapp_business_messaging, whatsapp_business_management.
6. **Enviar mensaje sin plantilla** (ventana 24h abierta):
   `curl 'https://graph.facebook.com/v23.0/<PHONE_NUMBER_ID>/messages' -H
   'Content-Type: application/json' -H 'Authorization: Bearer <TOKEN>' -d
   '{"messaging_product":"whatsapp","recipient_type":"individual","to":"<NUM>",
   "type":"text","text":{"body":"Hello!"}}'`
7. Versión de API usada en la doc vigente: v23.0.

Procedimientos paso a paso (token expirado, webhook, errores 190/465,
facturas, cambio de número, Get Started) → ver `procedures.md`.
Links oficiales → ver `urls.json`.