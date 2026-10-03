# Diseño — Integración R4c2p (Cobro Automático C2P)

**Última actualización:** 2026-10-03
**Autor:** Prometeo (modo cerebro, sin tocar producción)
**Fuente:** R4 CONECTA V3.0 (006).pdf, págs. 5, 16, 30, 32 — verificado en vivo 2026-10-03
**Repo:** /mnt/ssd_trabajo/hermes-agent @ feat/odoo-r4-integration
**Estado:** ✅ FASE 2 IMPLEMENTADA (2026-10-03) — C2P_ENABLED=false hasta habilitación
del banco. Tests: tests/unit/test_r4_c2p.py (20/20) + suite global 1025 passed.

---

## 0. Resumen ejecutivo

Se agrega el método R4c2p ("Cobro Automático") como tercera opción de pago en
Valentina, junto a Pago Móvil (R4consulta/R4notifica, ya operativo) y Efectivo.
El cliente da su cédula y banco; el banco le envía una autorización por SMS/app;
al confirmar, el débito llega a la cuenta del comercio y Valentina despacha.

⚠️ **Tres divergencias entre el brief y el PDF oficial** (el PDF manda):

| # | Brief | PDF (verificado) |
|---|-------|------------------|
| 1 | Body: `IdCliente, TelefonoComercio, Monto, BancoEmisor` | Body real: `TelefonoDestino, Cedula, Concepto, Banco, Ip, Monto, Otp` |
| 2 | Respuesta asincrónica vía webhook nuevo | Respuesta **síncrona**: `{"code":"00","message":"...","reference":"..."}` — no se documenta webhook para C2P |
| 3 | Banco emisor código 3 dígitos | `Banco` es string **4 numérico** (ej: `"0105"`) y `Cedula` 9 alfanumérico (`"V12345678"`, sin guion) |

El campo `Otp` del request implica flujo en 2 pasos (ver §2): primero
`GenerarOtp` (el banco le manda el OTP al cliente por SMS), el cliente nos
dicta el código, y recién entonces enviamos `R4c2p` con ese OTP. **Pendiente
confirmar con el banco** si C2P exige el paso GenerarOtp o si el banco envía
el OTP automáticamente al recibir el cobro (§8 Preguntas al banco).

---

## 1. Especificación del banco (extraída del PDF, págs. 30-32 y 16)

### 1.1 Endpoint

```
POST https://r4conecta.mibanco.com.ve/MBc2p
Headers:
  Content-Type: application/json
  Authorization: HMAC-SHA256 hex de "TelefonoDestino+Monto+Banco+Cedula"
                 usando como llave R4_COMMERCE_SECRET
  Commerce: R4_COMMERCE_ID
```

### 1.2 Request (JSON Modelo R4c2p, pág. 30)

```json
{
  "TelefonoDestino": "04145555555",   // 11 numérico — celular del cliente
  "Cedula": "V12345678",              // 9 alfanumérico, sin guion
  "Concepto": "PRUEBA",              // concepto/descripción del cobro
  "Banco": "0105",                   // 4 numérico — banco emisor del cliente
  "Ip": "192.168.1.20",              // IP origen (aclarar con banco, §8)
  "Monto": "1.15",                   // máx 8 enteros + 2 decimales, punto '.'
  "Otp": "13309525"                  // OTP interbancario (ver §2)
}
```

### 1.3 Response — SÍNCRONA (pág. 30)

Aprobado (`code "00"`):
```json
{"message": "TRANSACCION EXITOSA", "code": "00", "reference": "59707278"}
```
Rechazado (ej. `code "08"`):
```json
{"code": "08", "message": "TOKEN inválido"}
```

Códigos C2P (ya definidos en `src/integrations/r4/codigos.py`):
`00` aprobado · `08` token inválido · `15` llave errónea · `30` error formato ·
`41` banco fuera de servicio · `51` fondos insuficientes · `56` celular no
coincide · `80` documento de identificación errado.

### 1.4 GenerarOtp (pág. 16) — paso previo probable

```
POST https://r4conecta.mibanco.com.ve/GenerarOtp
Authorization: HMAC de "Banco + Cedula + Telefono + Monto"
{"Banco": "0192", "Monto": "50.00", "Telefono": "04145555555", "Cedula": "V12345678"}
```
El banco pagador genera el OTP y lo envía al cliente por su canal. Ya
implementado en `R4Client.generar_otp()`.

### 1.5 Anulación C2P (pág. 32)

```
POST https://r4conecta.mibanco.com.ve/MBanulacionC2P
Authorization: HMAC de "Banco"
{"Cedula": "V12345678", "Banco": "0105", "Referencia": "58945790"}
```
Ya implementado en `R4Client.anulacion_c2p()`. Se usa para revertir un cobro
C2P aprobado por error (ej. cliente se arrepiente antes del despacho).

### 1.6 Estado actual del código (verificado 2026-10-03)

Ya existe en el repo (herencia del plan R4):
- `R4Endpoint.R4C2P` + `HMACPattern(fields=TelefonoDestino, Monto, Banco, Cedula)` en `hmac_auth.py` ✔
- Mapeo `R4C2P → "/MBc2p"` en `client.py` (real + mock) ✔
- `R4Client.anulacion_c2p()` ✔ · códigos C2P en `codigos.py` ✔
- **Falta:** método `cobro_c2p()` en `R4Client`, webhook, FSM, DB, menú.

---

## 2. Flujo completo C2P (diseño)

```
Cliente                          Valentina (bridge.py)              Banco (R4 Conecta)
  │  "2" (Cobro Automático)  ───► estado awaiting_c2p_cedula
  │  "V-12345678"            ───► valida formato, guarda, pasa a
  │                             │  awaiting_c2p_banco
  │  "0114" (o "BNC")       ───► valida contra lista SUDEBAN,
  │                             │  guarda en clients
  │                             │  ── generar_otp(banco, monto, tel, cedula) ──► GenerarOtp
  │                             │  ◄── code 00 (OTP en camino al cliente) ──
  │  ◄── "Le cobraremos X VES. Recibirá un código de su banco."
  │      estado awaiting_c2p_otp (timeout 5 min)
  │  "13309525" (el OTP)    ───► ── cobro_c2p(...) ─────────────► POST /MBc2p
  │                             │  ◄── SÍNCRONA: code 00 + reference ──
  │  ◄── "✅ Pago confirmado. Su repartidor va en camino."
  │      pedido → pagado, encolar despacho, estado completed
  │
  │  (si code != 00)
  │  ◄── "❌ El pago fue rechazado. ¿Desea pagar con Pago Móvil (1) o Efectivo (3)?"
```

Notas:
- El timeout de 5 min vigila el estado `awaiting_c2p_otp` (el cliente tarda en
  recibir/dictar el OTP). Si expira → cancelar C2P y ofrecer Pago Móvil/Efectivo.
- La respuesta del banco es síncrona; el "webhook" del brief queda como
  **contingencia opcional** (§3) porque el PDF no lo documenta para C2P.
- Si el banco responde `code "00"` pero el pedido no debe despacharse, existe
  `anulacion_c2p()` para revertir.

---

## 3. Endpoint webhook nuevo (contingencia, NO documentado por el banco)

`POST /webhook/r4/c2p` en `api/bridge.py`:

- **Propósito:** si el banco activara una notificación asincrónica de C2P
  (como hace con R4notifica), este endpoint ya estaría escuchando.
- **Validación (mismo modelo R4-25 / commit 28f103a):**
  - IP en `R4_WEBHOOK_ALLOWED_IPS` (45.175.213.98, 200.199.249.3, 204.199.249.3)
  - `Authorization: <UUID>` directo, comparado con `hmac.compare_digest()`
  - **SIN HMAC en webhooks entrantes** (confirmado en PDF págs. 7, 9)
- **Payload esperado (supuesto, a validar con banco):**
  `{"TelefonoDestino", "Cedula", "Monto", "Referencia", "code"}`
- **Comportamiento:** buscar pedido pendiente por teléfono+monto (±1%),
  marcar pagado, responder `200 {"status": true}`. Si el C2P ya fue
  confirmado por la vía síncrona, responder `200` idempotente sin duplicar.
- **Estado:** 🟡 se implementa como hook pasivo que solo loggea hasta que el
  banco confirme el formato real. No bloquea nada.

---

## 4. Modificaciones a Valentina (api/bridge.py)

### 4.1 Menú de pago actualizado (hoy: 2 opciones, línea ~1030)

```
¿Cómo desea pagar?
1️⃣ Pago Móvil (usted transfiere)
2️⃣ Cobro Automático (le cobramos directo)
3️⃣ Efectivo (al recibir)
```
Botones: `{"id":"1","title":"💳 Pago Móvil"}`,
`{"id":"2","title":"⚡ Cobro Automático"}`, `{"id":"3","title":"💵 Efectivo"}`.
⚠️ Renumerar Efectivo de "2" a "3" en TODOS los handlers que hoy esperan
"2" para efectivo (buscador por `metodo_pago`).

### 4.2 Estados FSM nuevos (persistidos en conversation_state, tabla ya existe)

| Estado | Significado | Transición |
|--------|-------------|------------|
| `awaiting_c2p_cedula` | espera cédula `V-12345678` | válida → `awaiting_c2p_banco` |
| `awaiting_c2p_banco` | espera código banco (4 dígitos o alias BNC/BBVA…) | válido → enviar GenerarOtp → `awaiting_c2p_otp` |
| `awaiting_c2p_otp` | espera OTP dictado por el cliente | OTP válido → enviar R4c2p → síncrono: pagado (`completed`) o rechazo → ofrecer 1/3 |

El timeout de 5 min se aplica a `awaiting_c2p_otp` (campo `c2p_expires_at`
en el state JSON; un job/scheduler existente o el próximo mensaje del
cliente evalúa la expiración).

### 4.3 Cancelación y fallback

- Timeout 5 min: "⏰ El código expiró. ¿Desea pagar con Pago Móvil (1) o
  Efectivo (3)?" → estado `awaiting_payment` (Pago Móvil) o flujo efectivo.
- Rechazo del banco: mapear `code` a mensaje humano (§7) y ofrecer 1/3.
- "volver"/"menú" desde cualquier estado c2p → abortar sin encolar pedido
  (misma regla que awaiting_payment, línea ~1535).

---

## 5. Datos del cliente y DB

Nuevos campos (se piden UNA sola vez; quedan guardados en `clients` y se
pre-cargan en pedidos siguientes):

| Campo | Formato | Validación |
|-------|---------|------------|
| `client_cedula` | `V12345678` (9 alfanumérico, sin guion; aceptar `V-12345678` y normalizar) | regex `^[VEJG][0-9]{7,8}$` |
| `client_banco_emisor` | `0105` (4 dígitos) | lista SUDEBAN (0114 BNC, 0102 BBVA, 0105 Mercantil, 0192 BNC pago móvil, …) + alias textual |

Migración:
```sql
ALTER TABLE clients ADD COLUMN client_cedula TEXT;
ALTER TABLE clients ADD COLUMN client_banco_emisor TEXT;
```
Igual a lo pedido en el brief; el banco del cliente se guarda como código de
4 dígitos (según PDF), no 3.

---

## 6. Cliente R4c2p (src/integrations/r4/client.py)

Método nuevo:
```python
async def cobro_c2p(self, telefono_destino: str, cedula: str,
                    banco: str, monto: str, concepto: str,
                    otp: str, ip: str) -> R4Response:
    """POST /MBc2p — Cobro C2P. Respuesta síncrona code+reference."""
```
- Firma HMAC ya registrada (`HMACPattern` R4C2P existe ✔) — solo conectar.
- Normalizaciones previas: cédula sin guion, monto `f"{monto:.2f}"` con
  punto decimal, banco 4 dígitos.
- Retorno: `R4Response(success=True, data={"reference": "59707278"})` si
  `code=="00"`; en caso contrario `success=False` con el `code` del banco.
- Mock ya definido en `_mock_responses` (línea ~470) para tests.

---

## 7. Diálogo de Valentina — español neutro venezolano

- "¿Cómo desea pagar? 1) Pago Móvil 2) Cobro Automático 3) Efectivo"
- "Dígame su cédula (formato: V-12345678)"
- "Dígame el código de su banco (ej: 0114 BNC, 0102 BBVA)"
- "Le cobraremos X VES. Su banco le enviará un código por mensaje de texto. Dígamelo cuando lo reciba."
- "Esperando su código… (tiene 5 minutos)"
- "✅ Pago confirmado. Su repartidor va en camino. 💧"
- "❌ El pago fue rechazado. ¿Desea pagar con Pago Móvil (1) o Efectivo (3)?"
- "⏰ El código expiró. ¿Desea pagar con Pago Móvil (1) o Efectivo (3)?"

Mensajes por código de rechazo (mapa humano, sin exponer internals):
`51` → "❌ Fondos insuficientes…" · `41` → "❌ Su banco no está disponible
ahora…" · `80` → "❌ La cédula no coincide con su banco…" · resto → genérico.
Sin "vos", sin "decime", sin "che". Segunda persona = "usted" en todo momento.

---

## 8. Preguntas para el banco (bloqueantes/condicionantes)

1. **¿C2P requiere GenerarOtp previo o el banco envía el OTP solo?** El
   request exige `Otp`, pero el PDF no describe el paso a paso para C2P
   (sí lo describe para Débito Inmediato, pág. 16). Diseño asume 2 pasos.
2. **¿Qué va en el campo `Ip`?** ¿IP pública del comercio (nuestra) o del
   cliente? Ejemplo del PDF es una IP privada, poco concluyente.
3. **¿Existe notificación asincrónica C2P** (equivalente a R4notifica)?
   El webhook de §3 queda como hook pasivo mientras no respondan.
4. **¿El C2P se acredita vía R4notifica también?** Si sí, hay que dedup
   para no marcar dos veces el mismo pedido (idempotencia por `reference`).

---

## 9. Manejo de errores (resumen)

| Caso | Acción |
|------|--------|
| Cliente no dicta OTP en 5 min | Cancelar C2P, ofrecer Pago Móvil/Efectivo |
| Banco rechaza (code != 00) | Mensaje mapeado + ofrecer 1/3 |
| Timeout/red del banco hacia nosotros | Loggear (WARN), reintentos según `R4_MAX_RETRIES`, no bloquear conversación |
| Pedido pagado por duplicado (síncrono + webhook) | Idempotencia por `reference`; primer ganador marca, segundo solo log |
| R4 no disponible (401/108, placeholder token) | NO ofrecer opción 2 en el menú (feature flag `C2P_ENABLED` en config) hasta habilitación real |

El feature flag `C2P_ENABLED` (default `false`) permite desplegar todo el
código sin exponer la opción al cliente hasta que el banco active el servicio.

---

## 10. Plan de implementación (Fase 2, tras aprobación)

1. `R4Client.cobro_c2p()` + normalizaciones (client.py)
2. `POST /webhook/r4/c2p` pasivo (bridge.py) + validación IP/UUID
3. FSM: 3 estados nuevos + menú 3 opciones + renumerar Efectivo
4. `ALTER TABLE clients` (migración idempotente con try/except por columna)
5. `C2P_ENABLED` feature flag
6. Tests: request C2P correcto (HMAC fields exactos), aprobación síncrona,
   rechazo por código, timeout 5 min, menú 3 opciones, español neutro
   (assert sin "decime/vos/che" en plantillas), no-romper R4notifica
   (regresión: suite actual sigue verde)
7. Commits: `feat: integración R4c2p (Cobro Automático) + menú 3 opciones`

Reglas de la operación respetadas: Pago Móvil/R4notifica intactos, webhook
Meta y WAHA sin cambios, snapshot auto cada 2 min, commits --no-verify.

---

💧
