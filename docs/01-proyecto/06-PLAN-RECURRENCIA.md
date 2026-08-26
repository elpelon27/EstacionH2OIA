# Plan de Recurrencia — Estación H2O / Prometeo

**Fecha**: 2026-08-26 (Día 34)
**Autor**: Prometeo (GLM 5.2 vía OpenRouter)
**Aprobador**: Luis Martinez (@elpelon27) — Líder de Estación H2O
**Objetivo**: Modelo de ingresos recurrentes para escalar de 16 a 30 clientes en 3 meses

---

## Contexto Actual (verificado 2026-08-26)

| Métrica | Valor | Fuente |
|---------|-------|--------|
| Clientes activos estimados | 16 | Estimación del Líder |
| Clientes en dispatch.db | 3 | `SELECT COUNT(*) FROM clients` |
| Pedidos totales (orders) | 37 | `SELECT COUNT(*) FROM orders` |
| Pagos registrados (fs_pagos) | 2 | `SELECT COUNT(*) FROM fs_pagos` |
| Ingresos recurrentes | 0 | Sin suscripciones activas |
| Odoo | Docker Up, sin módulos activados | `docker ps` |
| R4 CONECTA | Sandbox, pendiente token prod | src/integrations/r4/ |

---

## Modelo de Recurrencia: 4 Pilares

### Pilar A: Suscripción Restaurantes

**Modelo**: Pago semanal con domiciliación R4

**Funcionamiento**:
1. Restaurante suscribe: N botellones/semana a precio fijo
2. Cada semana: R4 CONECTA cobra automático via DomiciliacionCELE (teléfono) o DomiciliacionCNTA (cuenta 20d)
3. Odoo crea account.payment.subscription con ciclo semanal
4. Valentina coordina entrega semanal automática
5. Si no hay devolución de vacíos, se ajusta factura

**Endpoints R4 utilizados**:
- DomiciliacionCELE (teléfono): primera vez afilia teléfono
- DomiciliacionCNTA (cuenta 20d): cobro recurrente por cuenta
- CICuentas: pago a cuenta 20 dígitos

**Integración Odoo**:
- Módulo: account.payment.subscription (Odoo 17 Community)
- Modelo: sale.subscription → genera factura automática cada ciclo
- Pago: R4 domiciliación → Odoo register_payment

**Precios referenciales** (definidos por Líder):
- Plan 10 botellones/semana: precio fijo semanal con descuento vs individual
- Plan 20 botellones/semana: precio mayorista
- Incluye hielo opcional

**Target**: 3 restaurantes suscritos en 3 meses

**Estado**: FASE FUTURA — requiere:
- Odoo módulos activados (account, sale_subscription)
- R4 token producción
- Productos cargados en Odoo

---

### Pilar B: Sistema 5/7 (Lealtad)

**Modelo**: 5 pedidos = 1 gratis, 7 pedidos = descuento

**Funcionamiento**:
1. Valentina cuenta pedidos por cliente (phone_hash en orders)
2. Pedido #5: Valentina aplica descuento automático (1 botellón gratis)
3. Pedido #7: Valentina aplica 10% descuento en total
4. Ciclo se reinicia después del beneficio
5. Cliente recibe mensaje: "¡Es tu 5to pedido! Tienes 1 botellón gratis 🎉"

**Implementación técnica**:
```python
# En bridge.py, al confirmar pedido:
order_count = await get_order_count(ph_hash)
if order_count % 5 == 0:  # Pedido 5, 10, 15...
    total = total - unit_price  # 1 botellón gratis
    msg = "¡Pedido 5! Tienes 1 botellón gratis 🎉"
elif order_count % 7 == 0:  # Pedido 7, 14, 21...
    total = total * 0.90  # 10% descuento
    msg = "¡Pedido 7! 10% de descuento aplicado 🎉"
```

**Base de datos**:
- `SELECT COUNT(*) FROM orders WHERE phone_hash = ?` → contador de pedidos
- Odoo: loyalty.program (módulo sale_loyalty en Community)
- FS: fs_pedidos con campo contador por cliente

**Target**: 60% de clientes activos reaching 5 pedidos en 3 meses

**Estado**: FASE FUTURA — requiere:
- Implementación en bridge.py (lógica de contador + descuento)
- Odoo sale_loyalty module activado (opcional, para tracking Odoo)
- Tests unitarios para lógica 5/7

---

### Pilar C: Pre-pago Botellones

**Modelo**: Comprar 10, usar cuando quieras

**Funcionamiento**:
1. Cliente paga 10 botellones por adelantado (precio con descuento vs individual)
2. Saldo se registra en Odoo (prepaid credit / wallet)
3. Cada pedido, Valentina descuenta del saldo
4. Valentina informa: "Tienes 7 botellones prepago restantes"
5. Cuando saldo < 2, Valentina sugiere recargar

**Implementación técnica**:
- Odoo: loyalty.program con tipo "prepaid" (wallet/credit)
- o account_credit_control module
- Valentina: consulta saldo antes de cobrar, descuenta automáticamente
- FS: fs_pedidos con tipo 'prepago' y link al paquete comprado

**Flujo de pago**:
1. Cliente paga 10 botellones (pago móvil o efectivo)
2. R4 webhook notifica pago (o registro manual si efectivo)
3. Odoo credita wallet del cliente
4. Valentina confirma: "10 botellones prepago cargados. Saldo: 10"
5. Pedidos futuros descuentan automáticamente

**Precios referenciales** (definidos por Líder):
- Paquete 10 botellones: descuento vs precio individual (ej: 10% menos)
- Paquete 20 botellones: descuento mayor
- Saldo expira en 90 días (configurable)

**Target**: 8 clientes con pre-pago activo en 3 meses

**Estado**: FASE FUTURA — requiere:
- Odoo loyalty/prepaid module activado
- Valentina: lógica de consulta y descuento de saldo
- R4 token producción (para pago móvil del paquete)

---

### Pilar D: Referidos (Cliente trae cliente)

**Modelo**: Cliente trae cliente = descuento

**Funcionamiento**:
1. Cliente A refiere a Cliente B
2. Cliente B hace primer pedido por Valentina y menciona "me refirió [Cliente A]"
3. Valentina registra referido (phone_hash A → phone_hash B)
4. Cliente A recibe descuento en próximo pedido (ej: 1 botellón gratis o 10% off)
5. Cliente B recibe primer pedido con pequeño descuento de bienvenida

**Implementación técnica**:
- Tabla nueva en dispatch.db: `referrals(referrer_hash, referred_hash, date, status)`
- Valentina: si cliente nuevo menciona un referidor, registra
- Odoo: sale_loyalty con coupon program (referral coupon)
- FS: fs_pedidos con campo referral_discount

**Flujo**:
```
Cliente B: "Necesito 3 botellones, me refirió Juan Pérez"
Valentina: "¡Bienvenido! Juan Pérez recibe 1 botellón gratis por referirte."
         → INSERT INTO referrals(referrer=A, referred=B, status='pending')
         → Cliente A: "Tu referido Juan hizo su primer pedido. Tienes 1 botellón gratis en tu próximo pedido 🎉"
```

**Target**: 5 referidos exitosos en 3 meses

**Estado**: FASE FUTURA — requiere:
- Tabla referrals en dispatch.db
- Lógica en Valentina para detectar y registrar referidos
- Odoo coupon program (sale_loyalty)

---

## Proyección: 16 → 30 clientes en 3 meses

### Mes 1: Adopción (16 clientes existentes)

| Métrica | Target | Notas |
|---------|--------|-------|
| Clientes registrados dispatch.db | 16 | Plan de adopción completado |
| Pedidos/día | 8-10 | Todos por Valentina |
| Suscripciones restaurantes | 0 | Piloto siguiente mes |
| Pre-pago activos | 2 | Early adopters |
| Referidos | 1 | Primer referido exitoso |
| Sistema 5/7 | Activo | Implementar lógica en bridge.py |

### Mes 2: Crecimiento (16 → 24 clientes)

| Métrica | Target | Notas |
|---------|--------|-------|
| Clientes nuevos | 8 | 5 por referidos + 3 orgánicos |
| Pedidos/día | 12-15 | Crecimiento natural |
| Suscripciones restaurantes | 1 | Primer restaurante piloto |
| Pre-pago activos | 5 | Crecimiento |
| Referidos | 3 | Sistema funcionando |
| Sistema 5/7 | 3 clientes reaching 5 pedidos | Lealtad activa |

### Mes 3: Consolidación (24 → 30 clientes)

| Métrica | Target | Notas |
|---------|--------|-------|
| Clientes nuevos | 6 | 4 referidos + 2 orgánicos |
| Pedidos/día | 15-20 | Crecimiento sostenido |
| Suscripciones restaurantes | 3 | 3 restaurantes activos |
| Pre-pago activos | 8 | Modelo establecido |
| Referidos | 5 | Sistema maduro |
| Sistema 5/7 | 10+ clientes reaching 5 pedidos | Lealtad consolidada |

### Proyección de Ingresos (estimación cualitativa)

| Concepto | Mes 1 | Mes 2 | Mes 3 |
|----------|-------|-------|-------|
| Ventas individuales | Estables | Crecimiento | Crecimiento |
| Suscripciones restaurantes | 0 | 1 plan semanal | 3 planes semanales |
| Pre-pago | 2 paquetes | 5 paquetes | 8 paquetes |
| Ingresos recurrentes % | 0% | 15% | 30% |
| **Total clientes** | **16** | **24** | **30** |

> Nota: Las cifras exactas de ingresos las define el Líder basado en precio actual del botellón y tasa BCV. Esta proyección es cualitativa, no financiera.

---

## Integración con Odoo (account.payment.subscription)

### Módulos Odoo requeridos (Community 17)

| Módulo | Uso | Estado |
|--------|-----|--------|
| sale_loyalty | Sistema 5/7 + referidos (coupons) | Pendiente activación |
| sale_subscription / sale_management | Suscripciones restaurantes | Pendiente activación |
| account_payment_subscription | Domiciliación R4 automática | Pendiente activación |
| sale_prepaid / account_credit | Pre-pago wallet | Pendiente activación (módulo comunitario) |
| l10n_ve | Localización Venezuela (IVA/ISLR) | Pendiente instalación |

### Flujo de integración

```
Valentina (bridge.py)
    │
    ├─ Pedido individual → Odoo sale.order (RF-03)
    │
    ├─ Suscripción restaurante → Odoo sale.subscription
    │    └─ Ciclo semanal → factura automática → R4 DomiciliacionCNTA
    │
    ├─ Pre-pago → Odoo wallet/credit
    │    └─ Pago paquete → credit wallet → descuento por pedido
    │
    ├─ Sistema 5/7 → Odoo sale_loyalty (loyalty program)
    │    └─ 5 pedidos → coupon auto-generado → descuento en próximo
    │
    └─ Referido → Odoo sale_loyalty (referral coupon)
         └─ Cliente nuevo → coupon para referidor
```

### Dependencias de implementación

1. **Odoo módulos activados**: sales, stock, account, sale_loyalty, sale_management, l10n_ve
2. **R4 token producción**: Para domiciliación automática de suscripciones
3. **Productos cargados en Odoo**: Botellón 20L, Hielo 5kg, paquetes pre-pago
4. **Clientes migrados a Odoo**: Los 16 clientes actuales como res.partner
5. **Lógica en Valentina**: bridge.py actualizado para consultar/descontar saldo, aplicar descuentos 5/7, registrar referidos

### Estado de implementación

| Componente | Código | Odoo | R4 | Tests |
|------------|--------|------|-----|-------|
| Suscripción restaurantes | PENDIENTE | PENDIENTE | SANDBOX | PENDIENTE |
| Sistema 5/7 | PENDIENTE | PENDIENTE | N/A | PENDIENTE |
| Pre-pago | PENDIENTE | PENDIENTE | SANDBOX | PENDIENTE |
| Referidos | PENDIENTE | PENDIENTE | N/A | PENDIENTE |

**Todos los pilares son FASE FUTURA** hasta que Odoo esté completamente activado y R4 tenga token de producción.

---

## Riesgos del Modelo de Recurrencia

| Riesgo | Probabilidad | Impacto | Mitigación |
|--------|-------------|---------|------------|
| Restaurantes no quieren domiciliación | MEDIA | MEDIO | Ofrecer pago manual semanal como alternativa |
| Sistema 5/7 explota por pedidos falsos | BAJA | BAJO | Contar solo pedidos completados (no cancelados) |
| Pre-pago saldo expira y cliente se molesta | MEDIA | MEDIO | Avisar 7 días antes de expiración via Valentina |
| Referidos falsos (cliente se autorefiera) | BAJA | BAJO | Validar que referred sea phone_hash distinto a referrer |
| Odoo loyalty module no disponible en Community | MEDIA | MEDIO | Usar módulo comunitario o implementar lógica en FS |
| R4 domiciliación rechazada por banco | MEDIA | ALTO | Tener plan B: pago manual + recordatorio Valentina |

---

**Firma**: 💧