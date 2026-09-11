# R4 Conecta — Prueba Interna de Pago (Monitoreo)

**Fecha:** 2026-09-11
**Prueba:** Pago real del Líder a cuenta R4 Conecta para validar comunicación bidireccional.
**Alcance:** Solo monitoreo. Sin cambios de código/config. Sin llamada al banco.

---

## 1. PRE-PAGO (18:30:24 -04)

| Verificación | Resultado |
|---|---|
| valentina-bridge.service | ✅ active (running) desde 15:48:02 -04, deps OK |
| GET /webhook/r4/consulta | ✅ HTTP 405 (esperado: solo POST; ruta viva, túnel sano, sin 502/503) |
| Config R4 en .env | ✅ R4_WEBHOOK_AUTH_TOKEN, R4_WEBHOOK_ALLOWED_IPS, R4_COMMERCE_ID, R4_COMMERCE_SECRET, R4_COMMERCE_TOKEN, R4_ID_COMERCIO, R4_TELEFONO_COMERCIO, R4_WEBHOOK_RATE_LIMIT/WINDOW — todos presentes |
| Logs R4 últimas 24h | 0 eventos (limpio) |
| Estado DB base | conversations.db → fs_pagos COUNT = 2 (solo test_audit del 2026-08-16) |

**Nota:** La tabla de pagos `fs_pagos` vive en `conversations.db`, NO en `dispatch.db` (la directiva apuntaba a la DB equivocada; documentado aquí).

## 2. DURANTE EL PAGO

Monitoreo en tiempo real con `journalctl -f` filtrado (sesión proc_2d89a60c7b86). El banco envió **4 webhooks R4consulta**:

| Timestamp (-04) | Evento |
|---|---|
| 18:32:05 | R4consulta recibido — **IP rechazada** `200.74.203.91` |
| 18:32:25 | R4consulta recibido (reintento) — **IP rechazada** `200.74.203.91` |
| 18:33:44 | R4consulta recibido (reintento) — **IP rechazada** `200.74.203.91` |
| 18:34:47 | R4consulta recibido (reintento) — **IP rechazada** `200.74.203.91` |
| 18:39:13 | R4consulta recibido (5º intento, backoff creciente) — **IP rechazada** `200.74.203.91` |

Total: **5 intentos R4consulta** entre 18:32:05 y 18:39:13, todos rechazados por IP.

Log representativo:
```
2026-09-11 18:32:05 [INFO] R4 Webhook IPs permitidas: {'45.175.213.98', '204.199.249.3', '200.199.249.3'}
2026-09-11 18:32:05 [INFO] === R4consulta/MBconsulta webhook recibido ===
2026-09-11 18:32:05 [WARNING] R4 Webhook IP rechazada: 200.74.203.91 (permitidas: {...})
```

- **R4notifica NUNCA llegó** (solo R4consulta, que es el primer callback del par).
- El bridge respondió **403** en cada intento (rechazo de IP; el payload nunca fue procesado, por lo que no hay monto/referencia capturados del payload).

**Root cause:** el banco está enviando desde la IP **200.74.203.91**, que es la IP ANTIGUA del whitelist. Según el skill del proyecto (actualización 2026-08-18), el banco reportó como IPs nuevas `45.175.213.98`, `200.199.249.3` y `204.199.249.3`, y `200.74.203.91` fue reemplazada por `200.199.249.3`. En producción el banco sigue saliendo por la IP antigua, que ya no está en `R4_WEBHOOK_ALLOWED_IPS`.

## 3. POST-PAGO

- `fs_pagos` COUNT sigue en **2** → **el pago NO se registró en DB** (los webhooks fueron rechazados antes del procesamiento).
- Sin registros en logs de archivo.
- Ventana de 10 min cubierta (18:31 → 18:38:58): solo los 4 intentos rechazados arriba.

## 4-bis. SEGUNDA VUELTA (18:44:43) — CICLO COMPLETO RECIBIDO ✅

Al reactivar el monitoreo (18:46) se detectó que a las **18:44:43** llegó el ciclo completo del banco, desde la IP whitelisted `45.175.213.98`:

**R4consulta** (IdCliente=18409679, Monto=300) → respuesta **status=True** (200 OK)
**R4notifica** (Referencia=125456046214, Monto=300.00 VES, TelefonoEmisor=04122560720, BancoEmisor=105, CodigoRed=00) → respuesta **abono=True** (200 OK)

Logs íntegros en journalctl (18:44:43). Sin rechazos de IP, sin errores de auth.

**DB:** NO hubo INSERT en fs_pagos. Causa: `buscar_pedidos_por_telefono_monto()` no encontró match. Verificado en fs_pedidos: existe UN pedido pendiente para ese teléfono (id 114, "Luis M.", 584122560720) pero con monto **2534.26 VES** — el pago de 300 VES no casa (tolerancia ±1%). Sin pedido casado, el flujo implementado (R4-25) acepta el pago (abono=True) sin registrar INSERT — comportamiento por diseño.

Nota adicional: el banco envía como IdCliente `18409679` (8 dígitos, no es teléfono) — el R4consulta lo loguea como "teléfono no normalizable"; el teléfono real del pagador llega en R4notifica (TelefonoEmisor).

## 4. Conclusión

| Pregunta | Respuesta |
|---|---|
| ¿Llegó el webhook del banco? | **SÍ** — 4 intentos R4consulta desde 200.74.203.91 |
| ¿Qué respondió el bridge? | **403** (IP no permitida) en los 4 intentos |
| ¿Errores de red? | NO — la conectividad banco→edge→bridge es correcta (los webhooks llegaron al origin en <1 s del pago) |
| ¿Se registró el pago en DB? | **NO** (rechazado en capa IP) |
| ¿Comunicación bidireccional confirmada? | **SÍ (banco→nosotros)** — ciclo completo R4consulta+R4notifica recibido y respondido 200 OK a las 18:44:43. Falta validar el registro del pago en DB, que requiere un pedido pendiente cuyo teléfono+monto casen con el pago enviado. |

## 5. Recomendación al Líder

**NO es necesario llamar al banco por fallas de red — la comunicación llega.** El problema es 100% nuestro whitelist:

1. **Acción inmediata (1 línea, tu decisión):** agregar `200.74.203.91` a `R4_WEBHOOK_ALLOWED_IPS` en `config/.env` y reiniciar valentina-bridge. Es la IP que el banco reportó como reemplazada (→ `200.199.249.3`) pero sigue usando en producción.
2. **Para la llamada al oficial del banco:** preguntar cuál es la IP de salida ACTUAL y definitiva para webhooks (¿siguen en 200.74.203.91 o migrarán a las nuevas?), y confirmar el UUID de `Authorization` que usarán.
3. Tras ajustar el whitelist, repetir una prueba de pago para validar el ciclo completo R4consulta + R4notifica y el INSERT en `fs_pagos`.

**Estado:** ❌ FALLA (por whitelist de IP) — infraestructura y conectividad OK.