# R4 Conecta — Cierre Técnico (D3)

**Fecha:** 2026-09-11
**Alcance:** Whitelist de IPs del banco + validación end-to-end con pagos reales + monitoreo del pago de 322 VES.

---

## FASE 1 — Whitelist actualizado

- Backup previo: `config/.env.bak.20260911_r4ip`
- `R4_WEBHOOK_ALLOWED_IPS`: `45.175.213.98,200.199.249.3,204.199.249.3` → **`45.175.213.98,200.199.249.3,204.199.249.3,200.74.203.91`**
- Motivo: el banco alterna IPs de salida. La antigua 200.74.203.91 generó 8 rechazos 403 (18:32→19:23) mientras la nueva 45.175.213.98 sí estaba whitelisted.
- Bridge reiniciado: `active (running)` desde 19:41:17 -04, startup complete, sin errores.

## FASE 2 — Validación sistema 100% operativo

| Check | Resultado |
|---|---|
| valentina-bridge.service | ✅ active (running), deps OK |
| GET /webhook/r4/consulta (edge) | ✅ HTTP 405 (ruta viva, solo POST; túnel sano) |
| Whitelist | ✅ ambas IPs del banco (45.175.213.98 + 200.74.203.91) + las 2 nuevas documentadas |
| Logs (5 min) | ✅ sin errores/crash |
| Qdrant (localhost:6333) | ✅ responde (mem0migrations, whatsapp_conversations, …) |

## FASE 3 — Pago de 322 VES (Líder, prueba de comunicación)

Evento completo capturado en journalctl, **19:39:13 -04**, IP origen `45.175.213.98` (whitelisted):

1. **R4consulta** — IdCliente=18409679, Monto=322 → respuesta **status=True** (200 OK)
2. **R4notifica** — Referencia=125456076005, Monto=322.00 VES, TelefonoEmisor=04122560720, BancoEmisor=105, CodigoRed=00 → respuesta **abono=True** (200 OK)

| Pregunta | Respuesta |
|---|---|
| Webhook recibido | SÍ — ambos (consulta + notifica) |
| IP del banco | 45.175.213.98 |
| Status code | 200 OK en ambos callbacks |
| ¿Casó con pedido? | NO — sin pedido pendiente teléfono 04122560720 + 322 VES |
| INSERT en fs_pagos | NO — por diseño R4-25: sin match, se acepta el pago (abono=True) sin INSERT |
| WhatsApp al cliente | NO (solo se dispara con pedido casado) |
| Registro Odoo | NO (best-effort tras INSERT; no llegó a ejecutarse) |

**Nota:** el pago de 322 VES (igual que el de 300 VES a las 18:44:43) fue una prueba del Líder con cuenta de prueba; la falta de INSERT no es falla técnica — la casación teléfono+monto requiere un pedido real pendiente que case (±1%).

## FASE 4 — Cierre D3

D3 (R4 Conecta) ya figuraba CERRADA el 2026-09-09 (IPv4 sola); re-validada end-to-end hoy:

> Comunicación banco-bridge confirmada con webhooks reales. Banco manda R4consulta + R4notifica desde IPs 45.175.213.98 y 200.74.203.91 (ambas whitelisted). Bridge responde 200 OK con status=True y abono=True. Sistema 100% operativo.

Entrada actualizada en `DEUDAS_TECNICAS_Y_PROYECTOS.md`.

## Pendiente para una prueba futura (no bloquea el cierre)

- Validar el INSERT en fs_pagos con un pedido real pendiente cuyo teléfono+monto casen exactamente con el pago (incluye WhatsApp "✅ Pago confirmado" y registro Odoo best-effort).
- Confirmar con el oficial del banco la lista definitiva de IPs de salida para webhooks (hoy: 2 IPs activas observadas).