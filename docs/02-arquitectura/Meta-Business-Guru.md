---
tags:
  - skill
  - meta
  - whatsapp
  - instagram
---

# Meta Business Guru

## Resumen

Skill de referencia para administrar la plataforma **WhatsApp Business Cloud API** de Meta (e **Instagram**) desde el dashboard de desarrolladores. Da cobertura completa al ciclo de vida de la cuenta del bot **Valentina** de la Estación H2O: dashboard, webhooks, tokens, plantillas, facturación y resolución de errores.

- **Ubicación del código**: `skills/meta-business-guru/` (ruta completa: `/home/skynet/hermes-unified/skills/productivity/meta-business-guru/`)
- **Archivos**: `SKILL.md` (doc principal), `urls.json` (links oficiales), `procedures.md` (procedimientos step-by-step)
- **Commit de creación**: 92b4987 (2026-08-28), extraído con evidencia en vivo de https://developers.facebook.com/docs/whatsapp/cloud-api/get-started (doc jun-2026, API v23.0)
- **Reglas de seguridad**: Chromium con perfil aislado, nunca logins personales del Líder, tokens solo en `.env` (nunca en repo).

## Qué cubre (SKILL.md)

1. Navegación del Meta Dashboard (developers.facebook.com/apps/)
2. Configuración de webhook (callback URL + verify token + campos suscritos)
3. Generación/regeneración de tokens (temporal vs usuario del sistema)
4. Estado de la cuenta WhatsApp Business (quality rating, tiers de envío)
5. Gestión de plantillas de mensajes (MARKETING / UTILITY / AUTHENTICATION)
6. Botón de inicio (Get Started / wa.me + QR)
7. Facturación y pagos (créditos, errores 132000)
8. Tabla comparativa: WhatsApp Business App vs Cloud API

## Procedimientos clave (procedures.md)

| Procedimiento | Cuándo usarlo |
|---|---|
| **a. Regenerar token expirado** | Error 190 subcode 463; token de usuario del sistema en Business Settings → Usuarios del sistema |
| **b. Verificar/reconfigurar webhook** | Bot no recibe mensajes; GET hub.challenge debe responder 200 + campo `messages` activo + WABA suscrita |
| **c. Error 190** (token expired/invalid) | Subcodes: 463 expirado, 467 invalidado (cambio de contraseña admin), puro = token mal copiado |
| **d. Error 465** (app does not belong to business) | La app no pertenece al portafolio dueño de la WABA; reasignar activos o transferir app |
| e–g | Pagar facturas, cambiar número asociado, activar botón "Empezar" |

Diagnóstico rápido: `curl -s "https://graph.facebook.com/v23.0/me?access_token=$TOKEN"` → sin error = token sano.

## Relación con el proyecto

- Contexto del bot Valentina y su integración con Odoo 17: [[MASTER_MEMORY_CELL_PROMETEO]]
- Plan de implementación de la integración (R4, Odoo, WhatsApp): [[04-PLAN-IMPLEMENTACION]]
- Link oficial del skill: [[HERMES_AGENT_SUPERPOWERS_ARCHITECTURE]] (arquitectura de skills Hermes)

## Referencias oficiales

- https://developers.facebook.com/docs/whatsapp
- https://developers.facebook.com/docs/whatsapp/cloud-api
- https://developers.facebook.com/docs/whatsapp/business-management-api
- https://business.facebook.com/settings/
- Lista completa en `skills/meta-business-guru/urls.json`
