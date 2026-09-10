# Diseño de integración: Hermes → Meta Devtools MCP → Meta API

Fecha: 2026-09-09
Autor: Prometeo — FASE 2, pendiente de aprobación del Líder
Depende de: docs/META_MCP_INVESTIGACION.md

## 0. Alcance honesto (leer primero)

El MCP server de Meta NO envía mensajes y NO genera tokens de Graph API.
Split de responsabilidades:

| Capacidad | Vía |
|---|---|
| Enviar mensajes WhatsApp (whatsapp_business_messaging) | Graph API directa con token de producción del Líder (fuera del MCP) |
| Configurar/verificar webhook (whatsapp_business_management, parte operativa) | Meta Devtools MCP (`devtools_webhook_manage`, `devtools_webhook_test`) |
| Estado App Review / compliance / API health | Meta Devtools MCP (read-only) |
| Token de producción | Manual: dashboard Meta → App → WhatsApp → Configuration (24h) o system-user token permanente vía Business Manager |

Recomendación al Líder: token de SYSTEM USER permanente desde Business
Manager para el envío de mensajes — elimina la renovación diaria de los
tokens "temporary" de 24h.

## 1. Arquitectura

```
┌──────────────┐  OAuth (1 vez, `hermes mcp login`)   ┌──────────────────────────┐
│    Hermes    │ ───────────────────────────────────► │ mcp.facebook.com/devtools │
│  (agente)    │        Streamable HTTP MCP           │  (Meta Social Techn. MCP)│
│              │                                      └───────────┬──────────────┘
│ mcp_servers: │                                                  │ Graph API (management:
│ meta_devtools│                                                  │ webhooks, review, health)
└──────┬───────┘                                                  ▼
       │ token system-user (env, .env)              Meta Graph API v25.0
       └────────────────────────────────────────► /{phone_id}/messages (envío)
```

- MCP: solo configuración/observabilidad de la app + webhooks.
- Envío de mensajes: Graph API REST directo con token del Líder (igual que hoy).

## 2. Auth flow OAuth (Líder autoriza 1 vez)

1. Líder añade el server (config.yaml, sección 4) — solo URL, sin secrets.
2. Líder ejecuta `hermes mcp login meta_devtools` (interactivo): Hermes abre
   browser → login Meta → consent screen → selecciona la app de Estación H2O
   → scope Manage.
3. Tokens OAuth persistidos por `HermesTokenStorage`
   (`$HERMES_HOME/...mcp tokens...`, ver tools/mcp_oauth.py).
4. Renovación: refresh automático por el cliente MCP de Hermes al expirar;
   si el refresh falla → re-login manual (errores de auth se reportan al
   Líder, no se reintentan en silencio).

Restricciones de Meta (beta):
- Flujo OAuth se repite si el cliente pierde los tokens (restart del host no
  debe perderlos: tokens en disco, no en memoria).
- Rollout gradual: si la cuenta del Líder no tiene acceso, error
  "It looks like this app isn't available" → esperar/feedback a Meta.
- Hermes NO está en la lista de clientes validados → posible error
  "Facebook login is currently unavailable for this app". Plan B: puente
  `mcp-remote` (npm) vía stdio: `command: npx, args: [-y, mcp-remote, https://mcp.facebook.com/devtools]`.

## 3. Scopes mínimos

| Scope MCP | Apps | Por qué |
|---|---|---|
| Manage | App WhatsApp Estación H2O | webhooks: subscribe/update_fields/test_send |
| Read | (incluido en Manage) | estado, review, compliance, API health |

Graph API (NO por MCP; se solicitan en App Review):
- whatsapp_business_messaging — enviar mensajes
- whatsapp_business_management — configurar webhook y números

## 4. Invocación de MCP tools desde Hermes — decisión

Opciones evaluadas:
1. HTTP directo al MCP server — innecesario, reinventa el protocolo.
2. Librería `mcp` Python vía cliente nativo de Hermes — RECOMENDADA (ya
   implementada: mcp_oauth.py + mcp_config.py + mcp_startup.py, transporte
   streamable_http, OAuth interactivo con persistencia).
3. Puente Claude Code / mcp-remote — solo como plan B si Meta bloquea
   el OAuth por cliente no validado.

Config (config.yaml, NO .env — no hay secrets en el server MCP;
los tokens OAuth los persiste Hermes automáticamente):

```yaml
mcp_servers:
  meta_devtools:
    url: "https://mcp.facebook.com/devtools"
    timeout: 120
    connect_timeout: 60
```

Tools resultantes: mcp_meta_devtools_app_list,
mcp_meta_devtools_webhook_manage, mcp_meta_devtools_webhook_test,
mcp_meta_devtools_app_review, mcp_meta_devtools_compliance, etc.

## 5. Variables de entorno (.env.example — SOLO secrets de envío Graph API)

No existen META_MCP_OAUTH_CLIENT_ID/SECRET: el OAuth del MCP es del
server de Meta, sin registro de cliente propio (ver investigación §3).
Estas variables del encargo quedan DESCARTADAS por diseño correcto.

Añadir a .env.example (el archivo no existe aún; crearlo con este bloque):
```
# ── Meta WhatsApp Cloud API (envío de mensajes — Graph API directa) ──
WHATSAPP_TOKEN=            # token system-user permanente (Business Manager) o temporary 24h
WHATSAPP_PHONE_NUMBER_ID=  # ID del número de WhatsApp Business
WHATSAPP_VERIFY_TOKEN=     # token para verificación del webhook (elegido por nosotros)
WHATSAPP_APP_ID=1186108677920030
```

## 6. Flujo de renovación de tokens

- MCP OAuth: refresh automático cliente Hermes; re-login manual solo si
  Meta invalida la sesión (documentado en troubleshooting del diseño).
- Graph API system-user token: NO expira (permanente) — cero renovación.
- Graph API temporary token (plan C): expira en 24h → cron diario que
  alerta al Líder si no hay system-user token aún.

## 7. Manejo de errores

| Error | Detección | Acción |
|---|---|---|
| OAuth MCP expirado/revocado | 401 del server MCP | Reportar al Líder → `hermes mcp login meta_devtools` |
| Token Graph expirado (error 190, como hallazgo #1) | respuesta API code 190 | Alertar; no reintentar en silencio |
| Scope Manage faltante | error de devtools_webhook_manage | Líder ajusta en Business Integrations |
| Webhook callback falla verificación | devtools_webhook_test test_send | Revisar endpoint HTTPS + hub.challenge |
| Cliente no validado por Meta | "Facebook login is currently unavailable" | Plan B: puente mcp-remote stdio |
| Rollout sin acceso | "This app isn't available" | Esperar aprobación de Meta (beta gradual) |

Seguridad: no loggear tokens; Hermes ya redacta credenciales en errores MCP.

## 8. Pasos manuales del Líder (aprobación previa)

1. Aprobar este diseño.
2. Generar system-user token en Business Manager con whatsapp_business_messaging + whatsapp_business_management → WHATSAPP_TOKEN en .env.
3. `hermes mcp login meta_devtools` + consent en browser (1 vez).
4. Verificar con `mcp_meta_devtools_app_list` (debe listar la app 1186108677920030).
5. Con webhook live (HTTPS con hub.challenge), Hermes hace el resto:
   subscribe + update_fields + test_send vía MCP.

## 9. Estimación (tras aprobación)

- Config MCP + .env.example + login: ~30 min.
- Suscripción y test de webhook vía MCP: ~1 h (requiere webhook H2O desplegado y HTTPS alcanzable).
- Envío de mensajes (Graph API, ya sea canal WhatsApp existente o script):
  depende del diseño del gateway del Líder — fuera del alcance de este MCP.

## 10. Nota de riesgos

- MCP en Beta: toolset puede cambiar.
- Meta no valida Hermes como cliente (plan B mcp-remote documentado).
- El MCP NO resuelve el token debug-only por sí mismo; el reemplazo a
  system-user token es paso manual del Líder (dashboard), sin MCP.