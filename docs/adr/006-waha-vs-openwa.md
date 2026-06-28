# ADR-006: WhatsApp Cloud API Oficial (Meta)

**Estado**: Aceptado
**Fecha**: 2026-06-28
**Actualiza**: ADR-006 original (WAHA)

## Contexto
Sistema anterior probó 5 librerías WhatsApp no oficiales (Evolution API, whatsapp-web.js, Baileys, Meta Cloud API, OpenWA). WAHA tenía webhook sin HMAC y sesión caía en restart. Cada desconexión = pérdida de ventas (100% del negocio depende de WhatsApp).

## Decisión
Migrar a WhatsApp Cloud API oficial de Meta (reemplaza WAHA).

Razones:
- SLA empresarial Meta 99.9% vs caídas aleatorias WAHA
- Sin QR, sin navegador Puppeteer, sin reconexión manual
- Webhooks HMAC-SHA256 oficiales
- Costo casi cero para volumen actual (~$1.50/mes)
- Venezuela sin bloqueo geográfico ni de pagos
- Cumple ToS (sin riesgo de baneo)

## Consecuencias
**Positivas**:
- Conexión permanente sin QR
- Estabilidad empresarial
- Webhooks seguros (HMAC-SHA256)
- Soporte oficial de Meta

**Negativas**:
- Requiere verificación de negocio (RIF + factura)
- Requiere plantillas pre-aprobadas para mensajes fuera de 24h
- Migración atómica del número (no se puede usar en app y API simultáneamente)

## Implementación
- `core/meta_client.py`: cliente WhatsApp Cloud API
- `api/main.py`: webhook handler `/webhook/meta` con HMAC-SHA256
- Eliminado: `infra/docker-compose.waha.yml`, container `hermes_waha`
