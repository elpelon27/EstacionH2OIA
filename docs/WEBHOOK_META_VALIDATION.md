---
title: Webhook Meta — Validación de payload por tipo (field)
---

# Validación de payload del webhook Meta — lógica por tipo

**Última actualización:** 2026-09-09
**Autor:** Prometeo (aprobado por Líder)
**Repo:** github.com/elpelon27/EstacionH2OIA (rama feat/odoo-r4-integration)
**Archivo:** `api/bridge.py` → `_validate_meta_payload()`

## Problema (hallazgo del piloto automático 2026-09-09)

`_validate_meta_payload` exigía `contacts` incondicionalmente en el payload.
Pero los **status updates reales de Meta NO traen `contacts`** — solo los
mensajes entrantes lo traen. Resultado: los status updates de Meta
(delivered/read/sent/template) recibían **400 espurios** del bridge.

## Cambio realizado

La validación ahora se ramifica según `entry[0].changes[0].field`, que es como
Meta identifica el tipo de webhook:

| `field` | Comportamiento |
|---|---|
| `"messages"` (mensaje entrante) | Exige `contacts` con `wa_id` válido (8-15 dígitos), igual que antes |
| `"message_status"` (status de envío) | **NO exige contacts** — solo valida que `value` sea dict; warning informativo si no tiene `statuses` ni `message` |
| `"message_template_status_update"` (status de template) | Ídem anterior |
| Field ausente | Se trata como `"messages"` (backward compat: payloads de mensaje siempre traen field; tests legacy no lo incluían) |
| Field desconocido | Log warning + aceptar (flexibilidad ante nuevos tipos de webhook de Meta) |

Seguridad intacta: si el field es `"messages"`, la validación de contacts/wa_id
sigue siendo estricta (es la única vía por la que un mensaje entra al flujo de
procesamiento). Los status updates se aceptan pero el handler igual los ignora
con `{"status": "ignored", "reason": "status_update"}` (línea ~3170 del bridge).

Lo NO tocado (según reglas del Líder): path `/webhook/meta`, verificación GET
(hub.challenge), validación HMAC (`_verify_meta_signature`).

## Tests

Archivo: `tests/unit/test_bridge_webhook_endpoints.py` (28 tests) y
`tests/unit/test_bridge_coverage.py` (tests legacy intactos).

Nuevos casos de validación:
- `test_message_entrante_con_contacts_pasa` ✅
- `test_message_entrante_sin_contacts_400` ✅ (seguimos protegiendo mensajes)
- `test_status_update_sin_contacts_pasa` ✅ (EL FIX)
- `test_status_update_con_contacts_tambien_pasa` ✅
- `test_template_status_update_sin_contacts_pasa` ✅
- `test_status_update_value_no_dict_falla` ✅ (value inválido sigue rebotando)
- `test_field_desconocido_acepta` ✅

Test de endpoint actualizado: `test_signature_valida_status_update_ignored` ahora
usa un payload REAL de Meta (field=`message_status`, sin contacts) y verifica
200 + `reason: "status_update"`.

## Verificación

- ruff api/bridge.py: clean
- mypy api/bridge.py: 0 errores
- pytest suite completa: **995 passed, 15 skipped** — sin regresiones
- Cobertura total del repo: 65%

## Nota de deploy

El bridge en producción (`valentina-bridge.service`) corre el código del repo;
aplicar el fix requiere reinicio del servicio (a coordinar con Líder — el piloto
no reinicia producción sin aprobación).

💧