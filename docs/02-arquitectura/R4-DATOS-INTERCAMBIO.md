## 🏦 R4 CONECTA — Matriz de Intercambio de Datos (bidireccional)

**Proyecto**: Integración R4 Conecta V3.0 — Estación H2O Maracaibo
**Revisión**: 2026-08-13 (actualización 2) · Prometeo
**Estado**: Infraestructura lista · **3 datos entregados al banco** · pendiente lo que el banco debe enviarnos

> Objetivo: tener clara, EN UNA hoja, (A) qué nos debe dar el banco y
> (B) qué nos pedirá el banco a nosotros — para no frenar la activación
> por falta de un dato puntual.

---

## A.0 — DATOS ENTREGADOS AL BANCO (2026-08-13) ✅

> Estos son los valores que el banco pidió de nosotros. Verificados vía
> `curl` al health público por el tunnel Cloudflare (HTTP 200, service ok).

### A.0.1 — URL de NOTIFICACIÓN (R4notifica — pago móvil entrante)
```
https://valentina.estacionh2o.com/webhook/r4/notifica
```
- Método: POST · Content-Type: application/json
- Response: `{"abono": true|false}`

### A.0.2 — URL de CONSULTA (R4consulta — validación de cliente)
```
https://valentina.estacionh2o.com/webhook/r4/consulta
```
- Método: POST · Content-Type: application/json
- Response: `{"status": true|false}`

### A.0.3 — TOKEN de AUTORIZACIÓN (para que el banco nos llame)
```
d878a28a-186e-432f-93b2-e7f16522174c
```
- Header: `Authorization: Bearer d878a28a-186e-432f-93b2-e7f16522174c`
- ⚠️ Secreto. Entregar por canal seguro. Está en `config/.env` como `R4_WEBHOOK_AUTH_TOKEN`. Si se filtra → regenerar (T2).

### A.0.4 — POLÍTICA DE IP ALA ENTRADA (estrategia estricta de seguridad)
- El banco SOLO llamará desde estas IPs: `45.175.213.98, 200.74.203.91, 204.199.249.3`.
- **Cualquier otra IP de origen se BLOQUEA con HTTP 403** (aplica antes de auth token y HMAC).
- No se hacen excepciones. Si el banco necesita llamar desde otra IP → pedirnos actualizar la whitelist primero (T2) y NO abrir el acceso.

---

## A) DATOS QUE EL BANCO DEBE DARNOS (créditos / credenciales entrantes)

### A.1 — Verificación de estado actual en `config/.env` (2026-08-13)

| Variable | Requerida | Estado hoy | Nota |
|----------|-----------|------------|------|
| `R4_COMMERCE_TOKEN` | Sí | ✅ POBLADO (24) | Token comercio → **es la llave HMAC-SHA256** usada por `client.py` y verificación de webhooks |
| `R4_ID_COMERCIO` | Sí | ✅ POBLADO (10) | Identificador comercial ante el banco |
| `R4_TELEFONO_COMERCIO` | Sí | ✅ POBLADO (11) | `TelefonoComercio` en payloads |
| `R4_WEBHOOK_AUTH_TOKEN` | Sí | ✅ POBLADO (36) | Bearer token UUID para nuestros webhooks |
| `R4_HMAC_KEY` | Según contrato | ⚠️ VACÍO | Ver nota: en la implementación actual NO se usa por separado; el commerce token firma. Confirmar con el banco si hay secret HMAC adicional |
| `R4_BASE_URL` | Sí | ❌ VACÍO | `https://r4conecta.mibanco.com.ve/` (producción) |
| `R4_SANDBOX_URL` | Ojalá | ❌ VACÍO | Ambiente de pruebas (si el banco lo ofrece) |
| IP Whitelist entrante | Sí | ✅ En código | `45.175.213.98, 200.74.203.91, 204.199.249.3` |

### A.2 — ¿Qué hay que pedir/confirmar al asesor hoy?

1. **Base URL de producción** (y sandbox si existe) — es lo único bloqueante para salir de mock.
2. **Confirmar la llave de firma**: en nuestro código el `R4_COMMERCE_TOKEN` actúa como secreto HMAC-SHA256 (`build_auth_headers`). Preguntar si el banco usa un `Secret`/`HMAC Key` **distinto** del commerce token, y su formato (base64/hex). Si es distinto → crear `R4_HMAC_KEY`.
3. **Lista de códigos de banco (3 dígitos)** soportados, para validar `BancoEmisor` (ej: 0102 Mercantil, 0134 Banesco, 0169 Banco R4/Microfinanciero…).
4. **Confirmar las 3 IPs** desde las que el banco llamará nuestros webhooks.
5. **Formato y ubicación del header de firma**: el código acepta `X-Signature`, `X-Hmac-Signature` o `Authorization: HMAC <sig>`. Confirmar cuál usa el banco en `R4notifica`/`R4consulta` entrantes.

---

## B) DATOS QUE EL BANCO NOS PEDIRÁ (solicitud de datos / onboarding del comercio)

> Cuando el banco nos envíe su formulario de alta / validación de comercio,
> típicamente pedirá lo siguiente. Prepáralo ANTES para responder de una vez.

### B.1 — Datos legales / de identidad del negocio
- Razón social / nombre comercial: **Estación H2O**
- RIF (J-… si es jurídico, o V-… si es persona) — confirmar el que usa el comercio
- Cédula/RIF del representante legal o titular
- Correo corporativo de contacto
- Teléfono del comercio: **`0412…` (el de `R4_TELEFONO_COMERCIO`)**
- Actividad económica / giro del negocio (venta de agua / botellones)

### B.2 — Datos financieros (cuenta de comercio)
- Número de cuenta bancaria del comercio donde se abonarán los pagos móviles
- Banco de esa cuenta (¿el mismo R4 / otro?) y tipo de cuenta (corriente/ahorro)
- Moneda de operación (Bs / USD) y cómo se maneja la tasa BCV

### B.3 — Datos técnicos (nuestra infraestructura, YA lista)
| Dato | Valor | Estado |
|------|-------|--------|
| Dominio del comercio | `estacionh2o.com` | ✅ |
| URL callback notificación | `https://valentina.estacionh2o.com/webhook/r4/notifica` | ✅ |
| URL callback consulta | `https://valentina.estacionh2o.com/webhook/r4/consulta` | ✅ |
| (si aplica) URL de tasa BCV | `https://valentina.estacionh2o.com/webhook/r4/bcv` o endpoint MBbcv saliente | ⚠️ confirmar |
| TLS | HTTPS vía Cloudflare (válido) | ✅ |
| Método de autenticación | HMAC-SHA256 + Bearer token + IP whitelist | ✅ |
| IPs de callback (banco→nosotros las llama, pero confirmar) | `45.175.213.98, 200.74.203.91, 204.199.249.3` | ✅ |
| IP origen de SALIDA (nosotros→banco) | IP pública del servidor (tunel Cloudflare / origen) | ❌ obtener |

### B.4 — Posibles documentos adjuntos
- Registro mercantil / acta constitutiva (si aplica)
- Estado de cuenta o carta bancaria
- Comprobante de titularidad de la cuenta

---

## C) FLUJO DE CAMPO (para no romper HMAC)

Los campos de cada endpoint deben respetar **exactamente** el string-to-sign del PDF:

| Endpoint | String-to-Sign | Dirección |
|----------|----------------|-----------|
| `R4bcv` | `Fechavalor + Moneda` | banco → nosotros (consulta) |
| `R4consulta` | `IdCliente + Monto + TelefonoComercio` | banco → nosotros |
| `R4notifica` | 9 campos en orden del PDF | banco → nosotros ⭐ |
| `R4c2p` | `TelefonoDestino + Monto + Banco + Cedula` | nosotros → banco |
| `CreditoInmediato` | `Banco + Cedula + Telefono + Monto` | nosotros → banco |
| `ConsultarOperaciones` | `Id` | nosotros → banco (poll) |

> ⚠️ Para `R4notifica` la firma usa los 9 campos del payload en el orden exacto
> que documenta el PDF (ver `HMAC_PATTERNS` en `src/integrations/r4/hmac_auth.py`).
> Cualquier reorden/omisión invalida la firma → HTTP 401.

---

## ✅ CHECKLIST DE ACTIVACIÓN (cuando llegue lo pendiente)

- [ ] `R4_BASE_URL` en `config/.env` (y `R4_SANDBOX_URL` si aplica)
- [ ] Confirmar/preparar `R4_HMAC_KEY` si el banco usa secret separado
- [ ] Tener la **cuenta de comercio** donde abonar (B.2)
- [ ] Tener **RIF y datos legales** a la mano (B.1)
- [ ] Confirmar **header de firma** entrante y **códigos de banco** (A.2)
- [ ] Reiniciar bridge: `sudo systemctl restart valentina-bridge`
- [ ] `python -m skills.r4banco_test test_bcv` → tasa real
- [ ] Mock `R4notifica` → pedido real abonado (E2E con banco)
- [ ] Actualizar este doc con los valores firmes (NUNCA credenciales en git)
