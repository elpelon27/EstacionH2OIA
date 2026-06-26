# ADR-006: Consolidación WAHA

**Estado**: Aceptado
**Fecha**: 2026-06-25

## Contexto
Sistema anterior probó 5 librerías WhatsApp (Evolution API, whatsapp-web.js, Baileys, Meta Cloud API, OpenWA). Cada migración rompió sesión. OpenWA tenía webhook sin HMAC y sesión caía en restart.

## Decisión
Migrar a WAHA (https://github.com/devlikeapro/waha) como librería definitiva.
- Engine: WEBJS
- HMAC nativo: X-Webhook-Hmac (SHA-512)
- Sesión persistente: WAHA_WORKER_RESTART_SESSIONS=True
- Session storage: local en M2

## Consecuencias
**Positivas**:
- Sesión no cae en restart
- HMAC verificado en cada webhook
- 6.8k★ GitHub, releases mensuales, OSS 100%

**Negativas**:
- Cambio de contrato API vs OpenWA
- Re-escaneo QR único al migrar

## Plan de rollback
- Mantener OpenWA detenido 30 días como backup
- Si WAHA falla: docker stop waha → docker start openwa
- Después de 30 días estables, eliminar OpenWA

## Referencias
- Investigación comparativa: 2026-06-23 (ver sesión recap día 3)
