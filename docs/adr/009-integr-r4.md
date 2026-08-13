# ADR-009: Integración Banco R4 Conecta V3.0 (HMAC-SHA256)

**Estado**: Aceptado
**Fecha**: 2026-08-12
**Relaciona**: ADR-008 (Odoo), FASE 5 del plan de integración

## Contexto
La mayor parte de los cobros se reciben por **pago móvil** interbancario. Para
verificar pagos en tiempo real y no depender de la revisión manual del comprobante,
el banco R4 Conecta expone una API REST + webhooks con autenticación por
**HMAC-SHA256** (13 patrones de firma documentados en el PDF bancario). El
worklog previo documentó la FASE 5 como "completa" pero `process_r4notifica` del
webhook seguía retornando un mock; la integración real vive en Financial Shield.

## Decisión
Integrar R4 Conecta V3.0 con módulos dedicados que implementan los 13 patrones
HMAC-SHA256 y exponen webhooks seguros para consulta (validación de cliente) y
notificación (pago confirmado).

Razones:
- Pago móvil concentra la mayoría de los cobros → verificación automática reduce
  cartera vencida y fricción al cliente
- HMAC-SHA256 timing-safe da integridad/autenticación de cada request
- IP whitelist + Bearer token + rate-limit = defensa en profundidad
- Integración con Financial Shield `verificar_pago_manual` → estado `pagado`

## Consecuencias
**Positivas**:
- Webhook `/webhook/r4/consulta` y `/webhook/r4/notifica` con validación completa
- CodigoRed=00 → match por teléfono+monto → verificación FS → `estado_pago`
- Historial en `fs_audit_log` con origen `banco_r4`

**Negativas/riesgos**:
- HMAC exige sincronización estricta de headers y payload (13 firmantes distintos)
- En sandbox/desarrollo se usa mock cuando el token está vacío
- **Bug crítico corregido (2026-08-12)**: la verificación real en
  `banco_verificador.procesar_notifica_pago_movil` estaba indentada DENTRO del
  bloque `if pedido ya pagado`, siendo código muerto → los pagos de pedidos
  pendientes nunca se verificaban y la función retornaba `None`. Se corrigió la
  indentación (T2, requiere restart del bridge).

## Implementación
- `src/integrations/r4/codigos.py`: códigos de red y respuesta interbancaria
- `src/integrations/r4/hmac_auth.py`: 13 patrones HMAC-SHA256 (timing-safe)
- `src/integrations/r4/client.py`: 13 endpoints async con mock si token vacío
- `src/integrations/r4/webhooks.py`: routers `/webhook/r4/*` (incluidos en bridge)
- `src/financial/banco_verificador.py`: procesador real FASE 6 (verificación FS)
- Cron: `r4_tasa_bcv.py` (9 AM + 3 PM Caracas)
