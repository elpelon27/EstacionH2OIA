# Investigación: Meta Devtools MCP (Meta Social Technologies MCP)

Fecha: 2026-09-09
Autor: Prometeo (agente) — encargo del Líder 💧
Estado: FASE 1 — investigación sin tocar producción
Fuente primaria: https://developers.facebook.com/documentation/mcp/devtools-mcp (actualizada Jun 12, 2026)

NOTA IMPORTANTE: Las URLs del encargo (`/docs/mcp/...`) devuelven 404.
La ruta real es `/documentation/mcp/...`. El server antes se llamaba
"Meta Developer Tools MCP"; ahora es "Meta Social Technologies MCP".
El endpoint y el prefijo `devtools_` NO cambiaron.

## 1. URL exacta del MCP server (remote HTTP)

| Atributo | Valor |
|---|---|
| Nombre | Meta Social Technologies MCP |
| Transport | Streamable HTTP (remote MCP) |
| Endpoint | `https://mcp.facebook.com/devtools` |
| Auth | OAuth con cuenta Meta developer (consent screen) |
| Estado | Beta — interfaz y toolset pueden cambiar |
| Rollout | Gradual: puede no estar disponible para todas las cuentas |

## 2. Scopes disponibles

Se configuran POR APP en facebook.com > Settings > Business Integrations.
NO son scopes de Graph API; son scopes del propio MCP server:

| Scope | Acceso |
|---|---|
| Read | Solo lectura: config de la app, App Review, compliance, API health, topics y suscripciones de webhook |
| Manage | Todo Read + crear/actualizar/eliminar suscripciones de webhook. La gestión de webhooks es LA ÚNICA capacidad de escritura |

Revocable en cualquier momento desde Business Integrations.
Cada reinicio del cliente exige completar el flujo OAuth de nuevo
(docs oficiales: "You'll need to complete the sign-in flow again when you restart the client").

## 3. Cómo se conecta un cliente (patrón Claude Code)

Claude Code (remote HTTP nativo):
```
claude mcp add --transport http meta_social_technologies https://mcp.facebook.com/devtools
/mcp  → seleccionar meta_social_technologies → Authenticate (browser OAuth)
```

Clientes solo-stdio usan el puente `mcp-remote` (npm) que proxifica el
server remoto por stdio. NO es nuestro caso (Hermes soporta HTTP nativo).

## 4. Auth flow (OAuth con consent screen)

1. Añadir el server al cliente (solo URL, sin App ID/Secret).
2. El cliente inicia el flujo OAuth → abre browser.
3. Login con cuenta Meta developer.
4. Consent screen: seleccionar QUÉ apps se le conceden al server.
5. Ajustar scope (Read/Manage) por app desde Business Integrations.
6. Verificar: el cliente debe listar las 10 herramientas `devtools_*`.

Errores documentados:
- "It looks like this app isn't available" → cuenta sin acceso aprobado (rollout gradual).
- "Facebook login is currently unavailable for this app" → cliente MCP aún no soportado por Meta.

## 5. Herramientas disponibles (10, prefijo `devtools_`)

1. `devtools_discovery` — buscar docs de desarrollador Meta (sin permisos de app).
2. `devtools_app_list` — listar apps accesibles (roles developer/admin/tester) + scopes concedidos. Usar primero para obtener app_id.
3. `devtools_app` — settings, permisos, config de la app (actions: basic_settings, advanced_settings, security, restrictions, data_protection_officer).
4. `devtools_app_review` — estado de App Review (status, history, privileges, requirements).
5. `devtools_compliance` — estado de cumplimiento, acciones abiertas, violaciones.
6. `devtools_api_usage` — rate limits, volumen de llamadas, deprecaciones.
7. `devtools_webhook_list` — topics de webhook disponibles + suscripciones actuales (list_topics, list_subscriptions).
8. `devtools_webhook_manage` — CRUD de suscripciones de webhook: subscribe, unsubscribe, update_fields. Requiere scope Manage + callback URL HTTPS live que pase verificación de Meta.
9. `devtools_webhook_test` — enviar payload de prueba a una suscripción (test_send).
10. `devtools_api_changelog` — productos de changelog + URLs RSS (sin permisos de app).

### Respuestas a las preguntas clave del Líder

¿Puede renovar tokens (Graph API)?
NO. El MCP no gestiona access tokens de Graph API. No hay tool de tokens.

¿Puede configurar webhook URL?
SÍ — `devtools_webhook_manage` (subscribe/update_fields) con scope Manage,
y `devtools_webhook_test` para verificar el endpoint. Es su única capacidad de escritura.

¿Puede generar production token?
NO. Los tokens de Graph API se generan en el dashboard de Meta
(App > WhatsApp > Configuration) o vía Graph API login, NO vía este MCP.
El MCP NO cubre el gap que causó el hallazgo #1 del Líder (token debug-only).

## 6. Permisos para whatsapp_business_messaging

El MCP NO maneja permisos de Graph API ni envía mensajes:
- `whatsapp_business_messaging` (enviar mensajes) — se solicita en App Review, NO vía MCP.
- `whatsapp_business_management` (configurar webhook/numbers) — ídem.
Lo que el MCP sí hace: consultar el ESTADO de ese App Review
(`devtools_app_review`) y del compliance (`devtools_compliance`),
y gestionar la suscripción de webhook (el paso operativo de "configurar webhook URL").

## 7. Tiempo de vida del acceso / revocación

- El grant es revocable en cualquier momento (Business Integrations).
- Tokens OAuth del MCP: manejados por el cliente (Meta no documenta TTL en la página del server).
- Las docs advierten que el flujo OAuth se repite al reiniciar el cliente → el cliente debe persistir/refresh tokens; ver diseño.

## 8. ¿Puede Hermes usar este MCP server remoto? — SÍ, nativamente

Verificado contra el código real de Hermes instalado en este host
(/home/skynet/.hermes/hermes-agent):

1. Cliente MCP nativo con transporte HTTP (StreamableHTTP):
   `references/native-mcp.md` del skill hermes-agent — config.yaml:
   ```yaml
   mcp_servers:
     meta_devtools:
       url: "https://mcp.facebook.com/devtools"
   ```
   Requisito: paquete `mcp` instalado (con `mcp.client.streamable_http`).

2. OAuth de servidores MCP remotos — SOPORTADO, verificado en código:
   - `tools/mcp_oauth.py` (1956 líneas): flujo OAuth interactivo con browser,
     callback en localhost con puerto reservado, `HermesTokenStorage`
     (persistencia de tokens/client_info por server), manejo de refresh.
   - `hermes_cli/mcp_config.py`: `force_interactive_oauth()` y
     `_oauth_tokens_present()` — `hermes mcp login` es el comando explícito
     de autenticación interactiva.
   - `hermes_cli/mcp_startup.py`: `_discover_mcp_tools_without_interactive_oauth()`
     — el arranque en background no bloquea esperando OAuth; se autentica
     con `hermes mcp login`.

3. Registro de tools: prefijo `mcp_{server}_{tool}` → p.ej.
   `mcp_meta_devtools_webhook_manage`.

No hace falta ningún adaptador nuevo, ni mcp-remote, ni puente Claude Code.
Meta NO lista Hermes como "cliente validado" (solo Claude, ChatGPT, Codex,
Cursor). Riesgo: error "Facebook login is currently unavailable for this app"
si Meta restringe por client_id/user-agent. Mitigación en el diseño.

## 9. Conclusión de viabilidad

- VIABLE para: gestión de la app Meta (estado, compliance, App Review,
  API health) y CONFIGURACIÓN/TEST de webhooks — exactamente la parte
  operativa de whatsapp_business_management.
- NO VIABLE para: enviar mensajes (whatsapp_business_messaging) ni
  generar/renovar tokens de producción. Eso sigue siendo Graph API directa
  con token generado por el Líder en el dashboard (paso manual inevitable
  mientras la app no esté aprobada en App Review).
- El token "Debug only" (hallazgo #1) se reemplaza con un token permanente
  del dashboard App > WhatsApp > Configuration ("temporary" 24h o
  system-user token permanente vía Business Manager). El MCP no interviene ahí.