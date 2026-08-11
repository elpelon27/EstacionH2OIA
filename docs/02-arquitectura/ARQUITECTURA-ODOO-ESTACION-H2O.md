# 🏛️ ARQUITECTURA ODOO — Estación H2O

> **Documento técnico-arquitectónico** para implementación Odoo en Estación H2O.
> Generado con base en entrevista técnica con el Líder (Luis Martinez @elpelon27).

**Versión**: 1.0 | **Fecha**: Julio 2026
**Autor**: Prometeo (GLM-4.6 vía Z.ai Code)
**Aprobador**: Luis Martinez (@elpelon27)
**Estado**: Pendiente aprobación → implementación
**Destino**: `/mnt/ssd_trabajo/hermes-agent/docs/02-arquitectura/ARQUITECTURA-ODOO-ESTACION-H2O.md`

---

## 1. RESUMEN EJECUTIVO

### 1.1 Decisiones clave aprobadas

| Decisión | Valor | Estado |
|---------|-------|--------|
| Odoo indispensable | ✅ | Confirmado por Líder |
| Modalidad facturación | Electrónica (obligatoria SENIAT) | Pendiente proveedor específico |
| Productos exentos IVA | ✅ Confirmado | Solo ISLR sobre dividendos |
| Facturación discrecional | RIF + método pago + decisión Líder | Regla de oro |
| Banco: API R4 | En desarrollo, soporta webhooks + consultas | Pendiente entrega credenciales |
| Plan Odoo | Community self-hosted (gratis, sin regalos) | Por proponer |
| Migración datos | Odoo limpio | Sin históricos |
| Usuarios Odoo | 1 (Líder) + tolerancia futuro admin | — |
| Nómina | 2 choferes, viernes, sueldo+bonos+comisión | — |

### 1.2 Alcance de la implementación

**Incluye**:
- ✅ Ventas (pedidos desde Valentina → Odoo automático)
- ✅ Inventario (botellones, hielo, insumos)
- ✅ Nómina (2 choferes, comisiones automáticas)
- ✅ Cuentas por pagar (1 proveedor principal)
- ✅ Cuentas por cobrar (clientes crédito semanal)
- ✅ Facturación electrónica (preparada para puesta en marcha)
- ✅ Notas de entrega (default para clientes sin RIF)
- ✅ Conversión nota → factura (sin romper inventario)
- ✅ Integración API Banco R4 (validación pagos tiempo real)
- ✅ Reportes automáticos (5 tipos)

**No incluye**:
- ❌ Punto de venta (no hay walk-in)
- ❌ E-commerce (WhatsApp único canal)
- ❌ CRM avanzado (clientes gestionados por Valentina)
- ❌ Migración datos históricos

### 1.3 Filosofía de diseño

1. **Odoo es fuente de verdad financiera** (inventario, ventas, nómina, contabilidad)
2. **Valentina es fuente de verdad conversacional** (WhatsApp, state machine, NEXO UX)
3. **Dispatcher es fuente de verdad logística** (rutas, GPS, choferes)
4. **Financial Shield se simplifica** → cache local para Valentina (no duplica Odoo)
5. **Automatización primero**: solo el Líder aprueba facturas, resto es automático
6. **Sin regalar dinero**: Odoo Community self-hosted en Docker (gratis)

---

## 2. ARQUITECTURA TÉCNICA COMPLETA

### 2.1 Diagrama del sistema integrado

```
┌──────────────────────────────────────────────────────────────────────┐
│                        CLIENTES (WhatsApp)                            │
└─────────────────────────────┬────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────────┐
│                VALENTINA (bridge.py :8000)                            │
│  Estado: ✅ Producción                                               │
│  - Recibe pedidos WhatsApp                                          │
│  - State machine determinístico (8 estados)                         │
│  - NEXO UX aplicado (P0/P1/P2)                                      │
│  - Valida RIF → decide factura vs nota                              │
│  - Trigger automático a Odoo al confirmar pedido                    │
└──────┬───────────────────────────┬─────────────────────────────┬────┘
       │                           │                             │
       ▼                           ▼                             ▼
┌──────────────────┐  ┌─────────────────────────┐  ┌──────────────────┐
│  DISPATCH DB     │  │  FINANCIAL SHIELD       │  │  ODOO SYNC       │
│  (dispatch.db)   │  │  (simplificado)          │  │  (nuevo módulo)  │
│  - clients        │  │  - fs_tasas_cambio       │  │  - XML-RPC       │
│  - deliveries     │  │  - fs_pedidos (cache)    │  │  - create_order  │
│  - vehicles       │  │  - fs_pagos (cache)      │  │  - sync_payment  │
│  - gps_tracks     │  │  - fs_nomina (cache)     │  │  - get_invoice   │
│  - zones          │  │  → Solo cache local     │  │  - convert_note  │
└────────┬─────────┘  └───────────┬─────────────┘  └────────┬─────────┘
         │                        │                        │
         ▼                        ▼                        ▼
┌──────────────────┐  ┌─────────────────────────┐  ┌──────────────────┐
│  DISPATCHER BOT  │  │  API BANCO R4           │  │  ODOO COMMUNITY  │
│  (@DespachoH2O)  │  │  (en desarrollo banco)  │  │  (Docker, self-  │
│  - /ruta          │  │  - Webhook pagos        │  │   hosted)        │
│  - /siguiente     │  │  - Consulta saldos      │  │  - Ventas        │
│  - /status        │  │  - Envío pagos          │  │  - Inventario    │
│  - Choferes       │  │  - Solicitud pagos      │  │  - Contabilidad  │
│  YORDANIS EVERT  │  │                          │  │  - Nómina        │
└──────────────────┘  └─────────────────────────┘  │  - Compras       │
                                                     │  - Facturación   │
                                                     │  - Reportes      │
                                                     └────────┬─────────┘
                                                              │
                                                              ▼
                                              ┌──────────────────────────┐
                                              │  FACTURACIÓN ELECTRÓNICA │
                                              │  (módulo externo SENIAT) │
                                              │  - Pendiente proveedor   │
                                              │  - XML firmado            │
                                              │  - Emisión oficial        │
                                              └──────────────────────────┘
```

### 2.2 Stack tecnológico final

| Capa | Tecnología | Costo |
|------|-----------|-------|
| WhatsApp | Meta Cloud API + bridge.py | $0 |
| LLM desarrollo | GLM 5.2 / Nemotron (Hermes Agent) | Free credits |
| LLM producción | Qwen 2.5:7b local (Ollama) | $0 |
| Bot Telegram | python-telegram-bot 21+ | $0 |
| Optimización rutas | OR-Tools VRP | $0 |
| Tunnel | Cloudflare Named Tunnel | $0 |
| ERP | **Odoo Community 17** (Docker) | $0 |
| DB Odoo | PostgreSQL 15 (Docker) | $0 |
| DB local | SQLite WAL | $0 |
| Banco | API R4 (en desarrollo) | Según banco |
| Documentación | Obsidian + git | $0 |
| **Total mensual fijo** | | **$0** |

### 2.3 Servicios systemd adicionales necesarios

Servicios actuales (mantener):
- `valentina-bridge.service` — FastAPI WhatsApp
- `cloudflared` — Tunnel
- `dispatcher-bot.service` — Bot choferes
- `telegram-bot.service` — Bot Líder

Servicios nuevos (a crear):
- `odoo-web.service` — Odoo application (Docker container)
- `odoo-db.service` — PostgreSQL 15 (Docker container)
- `odoo-sync.service` — Sincronizador Valentina → Odoo (Python daemon)
- `bank-r4-webhook.service` — Webhook receptor API Banco R4 (FastAPI)
- `odoo-cron-daily.service` — Reportes diarios (cron 11pm)
- `odoo-cron-weekly.service` — Cierre semanal + nómina viernes (cron viernes 5pm)

---

## 3. MÓDULOS ODOO NECESARIOS

### 3.1 Módulos core a activar

| Módulo Odoo | Versión Community | Estado | Justificación |
|-------------|------------------|--------|---------------|
| **sales** (Ventas) | ✅ Incluido | Activar | Registro pedidos desde Valentina |
| **stock** (Inventario) | ✅ Incluido | Activar | Botellones, hielo, insumos |
| **account** (Contabilidad) | ✅ Incluido | Activar | Cuentas por pagar/cobrar, libros |
| **purchase** (Compras) | ✅ Incluido | Activar | 1 proveedor principal $11k |
| **hr** (RRHH) | ✅ Incluido | Activar | 2 choferes |
| **hr_payroll** (Nómina) | ✅ Incluido | Activar | Nómina semanal viernes |
| **hr_contract** (Contratos) | ✅ Incluido | Activar | Contratos choferes |
| **project** (Proyectos) | ✅ Incluido | Opcional | Si quieres gestionar mantenimiento |
| **maintenance** (Mantenimiento) | ✅ Incluido | Opcional | Motos, planta ozono |
| **mrp** (Manufactura) | ✅ Incluido | Evaluar | Hielo producido + ozonización |

### 3.2 Módulos a NO activar

| Módulo | Razón de exclusión |
|--------|-------------------|
| `point_of_sale` | No hay walk-in, todo es delivery |
| `website` | Ya tienes landing aparte en Cloudflare Pages |
| `ecommerce` | Ventas solo por WhatsApp (Valentina) |
| `website_sale` | Igual que arriba |
| `crm` | Gestión clientes la hace Valentina |
| `mass_mailing` | No hacemos email marketing (por ahora) |
| `survey` | No aplicable |
| `elearning` | No aplicable |
| `helpdesk` | Soporte solo por WhatsApp |
| `fleet` | Solo 2 motos, demasiado para Odoo fleet |

### 3.3 Módulos externos a instalar

| Módulo externo | Origen | Función |
|---------------|--------|---------|
| **l10n_ve** (Localización Venezuela) | OCA (Odoo Community Association) | Adapta impuestos, formatos, RIF |
| **factura_electronica_ve** | Por definir (proveedor SENIAT) | Facturación electrónica XML firmada |
| **payment_r4** | Custom (a desarrollar cuando API R4 lista) | Integración Banco R4 |

### 3.4 Módulo custom a desarrollar: `estacion_h2o`

Módulo propio con lógica de negocio específica:

```
estacion_h2o/
├── __init__.py
├── __manifest__.py
├── models/
│   ├── pedidos_extendido.py    # Extiende sale.order con campos propios
│   ├── nota_entrega.py          # Modelo nota de entrega (no factura)
│   ├── comision_chofer.py       # Cálculo comisiones por botellón
│   └── conversion_nota_factura.py  # Conversión sin romper inventario
├── views/
│   ├── pedidos_extendido_views.xml
│   ├── nota_entrega_views.xml
│   ├── comision_chofer_views.xml
│   └── dashboard_lider.xml      # Dashboard personalizado Líder
├── wizards/
│   └── convertir_nota_wizard.py # Wizard conversión nota→factura
├── reports/
│   ├── ventas_diarias.xml
│   ├── cierre_semanal.xml
│   ├── inventario_hielo.xml
│   ├── nomina_choferes.xml
│   └── islr_mensual.xml
├── security/
│   └── ir.model.access.csv
└── data/
    ├── productos_data.xml       # Productos pre-cargados
    ├── impuestos_data.xml       # IVA exento (0%)
    └── secuencias.xml           # Numeración notas y facturas
```

---

## 4. MATRIZ DE INTEGRACIÓN

### 4.1 Conexiones entre agentes

| Origen | Destino | Método | Datos intercambiados | Frecuencia |
|--------|---------|--------|---------------------|------------|
| Valentina (bridge.py) | Odoo | XML-RPC over HTTPS | Pedido confirmado, cliente, items, total, método pago | Por pedido |
| Odoo | Financial Shield | API REST (bridge.py endpoint) | Pedido creado, invoice_id, status | Por pedido |
| Banco R4 (webhook) | Odoo | Webhook POST firmado | Pago recibido, monto, referencia, fecha | Por pago |
| Odoo | Dispatcher Bot | API REST → dispatch.db | Entrega confirmada → comisión chofer | Por entrega |
| Dispatcher Bot | Odoo | API REST → XML-RPC | Chofer marca "entregado" → actualiza stock Odoo | Por entrega |
| Odoo (cron) | Telegram Bot Líder | API Telegram | Reporte diario, semanal, nómina viernes | Programado |
| Odoo (cron) | Banco R4 API | HTTPS GET | Consulta saldos, conciliación | 2x día |
| Financial Shield | Banco R4 API | HTTPS GET | Tasa de cambio EUR/VES/USD | 2x día |
| Odoo | Líder (web UI) | Browser | Aprobación facturas, reportes, dashboard | On-demand |

### 4.2 Flujo de datos por proceso

#### Proceso A: Pedido cliente → factura electrónica

```
1. Cliente WhatsApp → "Hola, quiero 3 botellones, RIF J-12345678-9"
2. Valentina (bridge.py):
   a. State machine procesa pedido
   b. Valida RIF con regex venezolano
   c. Método pago = pago móvil → FACTURA
   d. POST a Odoo XML-RPC: sale.order.create()
   e. Retorna a cliente: "✅ Pedido confirmado, factura será emitida"
3. Odoo:
   a. Crea sale.order con cliente + items
   b. Verifica RIF en BD clientes (o crea nuevo)
   c. Aplica impuestos: EXENTO (0% IVA)
   d. Crea draft invoice (no confirmada)
   e. Notifica al Líder: "Factura pendiente aprobación"
4. Líder (Odoo web):
   a. Revisa factura draft
   b. Click "Aprobar y emitir"
   c. Odoo ejecuta módulo factura_electronica_ve
   d. Genera XML firmado
   e. Envía a SENIAT (cuando esté operativo)
   f. Retorna invoice_number oficial
5. Odoo → Valentina:
   a. Webhook: factura emitida
   b. Valentina → cliente: "Factura #X enviada al email XXX@..."
```

#### Proceso B: Pedido cliente → nota de entrega

```
1. Cliente WhatsApp → "Hola, quiero 3 botellones, pago efectivo"
2. Valentina:
   a. Método pago = efectivo → NOTA ENTREGA
   b. POST a Odoo: stock.picking.create() (no sale.order)
   c. Retorna a cliente: "✅ Pedido en camino"
3. Odoo:
   a. Crea stock.picking (movimiento inventario)
   b. Estado: draft
   c. Descuenta inventario al confirmar entrega
4. Chofer entrega:
   a. Marca "Entregado" en Dispatcher Bot
   b. Dispatcher → Odoo: stock.picking.action_done()
   c. Inventario actualizado
5. Si cliente solicita factura después:
   a. Líder busca nota en Odoo
   b. Click "Convertir a factura"
   c. Wizard convierte: stock.picking → sale.order → account.move
   d. Misma numeración original (no duplica)
   e. Stock ya descontado, no se afecta inventario
```

#### Proceso C: Pago Banco R4 → Odoo automático

```
1. Cliente hace pago móvil al número de Estación H2O (R4)
2. API Banco R4 detecta pago entrante
3. Webhook POST a https://valentina.estacionh2o.com/webhook/r4
   Payload:
   {
     "evento": "pago_recibido",
     "referencia": "0012345678",
     "monto": 2472.00,
     "moneda": "VES",
     "fecha": "2026-08-15T10:30:00-04:00",
     "cuenta_origen": "0412-2560721",
     "titular": "LUIS MARTINEZ"
   }
4. bridge.py procesa webhook:
   a. Verifica firma HMAC del banco
   b. Busca pedido pendiente por referencia
   c. Si match → marca como pagado
   d. Sincroniza con Odoo: account.payment.create()
5. Odoo:
   a. Registra pago
   b. Concilia con factura/Nota correspondiente
   c. Cliente recibe confirmación: "✅ Pago confirmado, gracias"
```

#### Proceso D: Nómina viernes choferes

```
1. Cron viernes 5pm America/Caracas:
   Trigger: odoo-cron-weekly.service
2. Odoo consulta:
   a. Entregas confirmadas esta semana (por chofer)
   b. Botellones entregados × comisión
   c. Sueldo base + bonos
3. Calcula nómina:
   - YORDANIS: sueldo_base + (botellones × comisión) + bonos
   - EVERT: sueldo_base + (botellones × comisión) + bonos
4. Genera recibos de nómina (PDF)
5. Envía a Telegram @Skynet_27_bot:
   "📋 Nómina viernes YORDANIS: Bs. XXX,XXX (€YYY)
    📋 Nómina viernes EVERT: Bs. XXX,XXX (€YYY)"
6. Líder aprueba pago
7. API Banco R4 → pago automático a choferes
```

---

## 5. FLUJO DE FACTURACIÓN DISCRECIONAL

### 5.1 Algoritmo de decisión

```python
def decidir_documento(cliente_rif: str, metodo_pago: str, 
                      solicita_factura: bool) -> str:
    """
    Decide si emitir factura electrónica o nota de entrega.
    
    Reglas (en orden de prioridad):
    1. Si cliente solicita factura + tiene RIF → FACTURA
    2. Si método pago = efectivo → NOTA ENTREGA (siempre)
    3. Si método pago = pago móvil + RIF presente → FACTURA
    4. Si método pago = pago móvil sin RIF → NOTA ENTREGA
    5. Discrecionalidad del Líder → override cualquier caso
    """
    
    # Regla 1: Solicita factura con RIF
    if solicita_factura and cliente_rif:
        return "FACTURA"
    
    # Regla 2: Efectivo = nota siempre
    if metodo_pago == "efectivo":
        return "NOTA_ENTREGA"
    
    # Regla 3: Pago móvil con RIF
    if metodo_pago == "pago_movil" and cliente_rif:
        return "FACTURA"
    
    # Regla 4: Pago móvil sin RIF
    if metodo_pago == "pago_movil" and not cliente_rif:
        return "NOTA_ENTREGA"
    
    # Default: nota
    return "NOTA_ENTREGA"
```

### 5.2 Tabla de decisión (referencia rápida)

| Cliente RIF | Método pago | Solicita factura | Documento |
|------------|------------|------------------|----------|
| ✅ Tiene | Pago móvil | ✅ Sí | FACTURA |
| ✅ Tiene | Pago móvil | ❌ No | NOTA (conversión posible) |
| ❌ No tiene | Pago móvil | ✅ Sí | NOTA (sin RIF no factura) |
| ❌ No tiene | Pago móvil | ❌ No | NOTA |
| ✅ o ❌ | Efectivo | Cualquiera | NOTA (siempre) |
| — | — | Líder override | FACTURA o NOTA (decisión manual) |

### 5.3 Implementación en Valentina (bridge.py)

```python
# En estado "awaiting_payment" o "awaiting_confirmation":

# Cuando cliente envía dirección + confirma pedido:
 Rif = state.get("cliente_rif", "")  # Lo pide Valentina si aplica
metodo_pago = state.get("payment_method", "")
solicita_factura = state.get("solicita_factura", False)

documento = decidir_documento(RIF, metodo_pago, solicita_factura)

if documento == "FACTURA":
    # Llama a Odoo para crear factura draft
    await odoo_sync.create_invoice(pedido_data)
    respuesta = "✅ Factura será emitida. Requiere aprobación del administrador."
else:
    # Llama a Odoo para crear nota de entrega
    await odoo_sync.create_delivery_note(pedido_data)
    respuesta = "✅ Pedido confirmado. Nota de entrega generada."

# En ambos casos, descuenta inventario al confirmar entrega (no al crear)
```

---

## 6. FLUJO CONVERSIÓN NOTA → FACTURA

### 6.1 Requisito del Líder

> "Se convierte la nota en factura para no dañar el inventario"

### 6.2 Implementación técnica

```
┌─────────────────────────────────────────────────────────┐
│ ESTADO ACTUAL: Nota de entrega #N-2026-0015              │
│ - Cliente: Juan Pérez (sin RIF)                          │
│ - Items: 3 botellones                                   │
│ - Total: €3.00 (Bs. 2,471.82)                           │
│ - Inventario: YA descontado al entregar                 │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼ Cliente solicita factura
                          │ (presenta RIF)
                          │
┌─────────────────────────────────────────────────────────┐
│ ACCIÓN: Convertir nota a factura                        │
│                                                          │
│ 1. Odoo: sale.order.create() con MISMO número original   │
│ 2. Referencia a nota original: nota_origen_id = N-0015   │
│ 3. account.move.create() con items y total               │
│ 4. Impuestos: EXENTO (0% IVA)                            │
│ 5. Inventario: NO se vuelve a descontar                  │
│    (campo stock_move_original_id referencia nota)        │
│ 6. Factura estado: draft (pendiente aprobación Líder)   │
│ 7. Líder aprueba → factura electrónica XML               │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│ RESULTADO: Factura #F-2026-0015                          │
│ - Misma numeración (15) para trazabilidad              │
│ - Inventario intacto (no duplicado)                     │
│ - Cliente recibe factura electrónica                    │
│ - Auditoría: nota→factura queda en log                  │
└─────────────────────────────────────────────────────────┘
```

### 6.3 Wizard de conversión en Odoo

```
[Odoo UI - Nota de entrega #N-2026-0015]
┌────────────────────────────────────────────┐
│  Cliente: Juan Pérez                       │
│  Fecha: 2026-08-15                          │
│  Total: €3.00 / Bs. 2,471.82              │
│  Estado: Entregado                          │
│                                            │
│  [📋 Ver Items] [📝 Convertir a Factura]  │
│                                            │
└────────────────────────────────────────────┘

Click "Convertir a Factura" → Wizard:
┌────────────────────────────────────────────┐
│  Convertir Nota a Factura                  │
│  ──────────────────────────────────────   │
│  Cliente RIF: [J-12345678-9    ]          │
│  Razón social: [Juan Pérez C.A. ]         │
│  Dirección fiscal: [Calle 72 Av 15]        │
│                                            │
│  ⚠️ Inventario no se modificará          │
│                                            │
│  [Cancelar] [Confirmar Conversión]        │
└────────────────────────────────────────────┘
```

---

## 7. PLAN DE DESARROLLO POR FASES

### FASE 1: Fundación Odoo (Semana 1-2)

**Objetivo**: Odoo operativo, configurado, sin integraciones todavía.

| # | Tarea | Responsable | Esfuerzo |
|---|-------|------------|----------|
| 1.1 | Instalar Docker + docker-compose en servidor | Hermes | 1h |
| 1.2 | Crear `docker-compose.yml` para Odoo + PostgreSQL | Hermes | 2h |
| 1.3 | Levantar Odoo Community 17 + PG 15 | Hermes | 1h |
| 1.4 | Configurar dominio `odoo.estacionh2o.com` en Cloudflare | Líder + Hermes | 1h |
| 1.5 | Configurar SSL Cloudflare → Odoo | Hermes | 30min |
| 1.6 | Activar modo desarrollador en Odoo | Líder | 15min |
| 1.7 | Configurar empresa Estación H2O (RIF, dirección, etc.) | Líder + Hermes | 1h |
| 1.8 | Cargar productos (botellón, hielo, insumos) | Hermes | 2h |
| 1.9 | Configurar impuestos EXENTOS (0% IVA) | Hermes | 30min |
| 1.10 | Instalar módulo `l10n_ve` (localización Venezuela) | Hermes | 1h |
| 1.11 | Configurar multi-moneda (EUR principal, VES/USD secundarias) | Hermes | 1h |

**Entregable FASE 1**: Odoo accesible en `https://odoo.estacionh2o.com`, configurado, sin datos.

### FASE 2: Módulo custom `estacion_h2o` (Semana 2-3)

**Objetivo**: Lógica de negocio propia funcional.

| # | Tarea | Esfuerzo |
|---|-------|---------|
| 2.1 | Crear estructura módulo `estacion_h2o/` | 2h |
| 2.2 | Modelo `nota_entrega.py` (nuevo documento) | 4h |
| 2.3 | Modelo `comision_chofer.py` (cálculo comisiones) | 3h |
| 2.4 | Wizard `convertir_nota_wizard.py` | 4h |
| 2.5 | Vistas XML (formularios, listas, dashboard) | 6h |
| 2.6 | Reportes PDF (5 reportes) | 8h |
| 2.7 | Security (permisos por rol) | 2h |
| 2.8 | Data inicial (productos, impuestos, secuencias) | 2h |
| 2.9 | Tests unitarios | 4h |
| 2.10 | Documentación en Obsidian | 2h |

**Entregable FASE 2**: Módulo instalable, con lógica de negocio completa.

### FASE 3: Integración Valentina → Odoo (Semana 3-4)

**Objetivo**: Pedidos fluyen automáticamente de WhatsApp a Odoo.

| # | Tarea | Esfuerzo |
|---|-------|---------|
| 3.1 | Crear `src/financial/odoo_sync.py` (cliente XML-RPC) | 6h |
| 3.2 | Modificar `api/bridge.py` trigger Odoo | 3h |
| 3.3 | Implementar algoritmo decisión factura/nota | 2h |
| 3.4 | Endpoint webhook Odoo → Valentina | 2h |
| 3.5 | Tests integración (5 escenarios) | 4h |
| 3.6 | Documentación + diagrama flujo | 2h |

**Entregable FASE 3**: Pedido WhatsApp → Odoo automático, sin intervención humana.

### FASE 4: API Banco R4 (Semana 4-5)

**Objetivo**: Pagos validados en tiempo real.

| # | Tarea | Esfuerzo |
|---|-------|---------|
| 4.1 | Esperar entrega de credenciales API R4 | bloqueante |
| 4.2 | Crear `src/financial/banco_r4_client.py` | 4h |
| 4.3 | Endpoint `/webhook/r4` en bridge.py | 3h |
| 4.4 | Validación HMAC firma banco | 2h |
| 4.5 | Match pago → pedido (por referencia) | 3h |
| 4.6 | Sync pago → Odoo account.payment | 2h |
| 4.7 | Notificación automática a cliente WhatsApp | 2h |
| 4.8 | Tests end-to-end con sandbox banco | 4h |

**Entregable FASE 4**: Pago móvil confirmado en <30s, sin validación manual.

### FASE 5: Nómina + Reportes (Semana 5-6)

**Objetivo**: Nómina choferes automática, reportes operativos.

| # | Tarea | Esfuerzo |
|---|-------|---------|
| 5.1 | Configurar 2 empleados en Odoo (YORDANIS, EVERT) | 1h |
| 5.2 | Contratos: sueldo base + bonos + comisión | 2h |
| 5.3 | Estructura salarial (hr.payroll.structure) | 3h |
| 5.4 | Regla comisión por botellón entregado | 3h |
| 5.5 | Cron viernes 5pm America/Caracas | 1h |
| 5.6 | Reporte ventas diarias (cron 11pm diario) | 3h |
| 5.7 | Reporte cierre semanal (cron viernes 6pm) | 3h |
| 5.8 | Reporte inventario hielo (cron diario) | 2h |
| 5.9 | Reporte insumos (cron semanal) | 2h |
| 5.10 | Reporte ISLR mensual (declaración dividendos) | 4h |
| 5.11 | Integración reportes → Telegram @Skynet_27_bot | 3h |

**Entregable FASE 5**: 5 reportes automáticos + nómina choferes operativa.

### FASE 6: Facturación Electrónica (Semana 6-8)

**Objetivo**: Emisión legal de facturas electrónicas SENIAT.

| # | Tarea | Esfuerzo | Dependencia |
|---|-------|---------|-------------|
| 6.1 | Confirmar proveedor factura electrónica con contador | bloqueante | Contador |
| 6.2 | Comprar/instalar módulo externo | variable | 6.1 |
| 6.3 | Tramitar certificado digital SENIAT | 2-4 semanas | 6.1 |
| 6.4 | Configurar módulo en Odoo | 4h | 6.2, 6.3 |
| 6.5 | Pruebas emisión XML firmado | 4h | 6.4 |
| 6.6 | Pruebas envío al servidor SENIAT | 4h | 6.5 |
| 6.7 | Emisión primera factura real | 1h | 6.6 |
| 6.8 | Capacitación Líder | 2h | 6.7 |

**Entregable FASE 6**: Facturas electrónicas operativas y legales.

### FASE 7: Dashboard Líder (Semana 8)

**Objetivo**: Vista única para el Líder.

| # | Tarea | Esfuerzo |
|---|-------|---------|
| 7.1 | Diseñar dashboard personalizado | 4h |
| 7.2 | Widgets: ventas día, pendientes factura, inventario crítico | 6h |
| 7.3 | Acciones rápidas: aprobar facturas, ver nómina | 3h |
| 7.4 | Mobile-responsive (Líder usa celular) | 2h |

**Entregable FASE 7**: Dashboard Líder operativo, todo en 1 pantalla.

---

## 8. INTEGRACIÓN API BANCO R4

### 8.1 Arquitectura

```
┌─────────────────────────────────────────────────────────┐
│  BANCO R4 (en desarrollo)                                │
│  - API REST                                              │
│  - Webhooks pagos recibidos                              │
│  - Consulta saldos en tiempo real                        │
│  - Envío pagos (transferencias)                          │
│  - Solicitud cobros (QR, links)                          │
└────────────────────────┬────────────────────────────────┘
                         │
                         │ Webhook POST firmado
                         ▼
┌─────────────────────────────────────────────────────────┐
│  VALentina (bridge.py :8000)                             │
│  Endpoint: POST /webhook/r4                              │
│                                                          │
│  1. Validar firma HMAC-SHA256                            │
│  2. Parsear payload                                      │
│  3. Match referencia → pedido pendiente                 │
│  4. Marcar pago en fs_pagos                              │
│  5. Sync a Odoo: account.payment.create()                │
│  6. Notificar cliente WhatsApp: "✅ Pago confirmado"    │
└─────────────────────────────────────────────────────────┘
```

### 8.2 Endpoints API R4 (esperados)

| Endpoint | Método | Función | Estado |
|---------|--------|---------|--------|
| `/webhooks/payments` | POST | Banco notifica pago recibido | Pendiente R4 |
| `/api/v1/accounts/balance` | GET | Consulta saldo cuenta | Pendiente R4 |
| `/api/v1/transfers` | POST | Enviar pago (choferes, proveedores) | Pendiente R4 |
| `/api/v1/payment-requests` | POST | Generar QR/link cobro | Pendiente R4 |
| `/api/v1/exchange-rates` | GET | Tasas de cambio oficiales | Pendiente R4 |

### 8.3 Configuración .env (cuando R4 esté listo)

```env
# Banco R4 API
BANCO_R4_API_URL=https://api.r4.banco.com/v1
BANCO_R4_API_KEY=[PEGAR_CUANDO_ENTREGUEN]
BANCO_R4_WEBHOOK_SECRET=[PEGAR_CUANDO_ENTREGUEN]
BANCO_R4_ACCOUNT_NUMBER=01690010971001591583
BANCO_R4_ACCOUNT_HOLDER=Estación H2O C.A.
BANCO_R4_CERT_PATH=/mnt/ssd_trabajo/hermes-agent/config/r4-cert.pem
```

### 8.4 Funcionalidades que se desbloquean

| Funcionalidad | Sin R4 (hoy) | Con R4 (futuro) |
|--------------|-------------|----------------|
| Confirmación pago | Manual (Líder mira SMS banco) | Automática <30s |
| Validar pago móvil | Cliente manda comprobante | Webhook banco → match automático |
| Pago a choferes | Líder transfiere manual | API R4 → transferencia automática viernes |
| Pago a proveedores | Líder transfiere manual | API R4 → programado |
| Solicitud pago cliente | Valentina manda datos cuenta | Valentina manda QR/link R4 |
| Reporte conciliación | Manual Excel | Automático Odoo |
| Tasas de cambio | open.er-api.com 1x/día | API R4 2x/día (oficial banco) |

---

## 9. REPORTES AUTOMÁTICOS

### 9.1 Reportes solicitados por el Líder

| Reporte | Frecuencia | Hora | Envío |
|---------|-----------|------|-------|
| **Ventas diarias** | Diario | 11:00pm | Telegram @Skynet_27_bot |
| **Cierre semanal** | Semanal | Viernes 6:00pm | Telegram @Skynet_27_bot |
| **Inventario hielo** | Diario | 8:00am | Telegram @Skynet_27_bot |
| **Inventario insumos** | Semanal | Lunes 8:00am | Telegram @Skynet_27_bot |
| **Nómina choferes** | Semanal | Viernes 5:00pm | Telegram @Skynet_27_bot (antes cierre semanal) |
| **ISLR mensual** | Mensual | Día 1 del mes, 9:00am | Email a contador |

### 9.2 Estructura reporte ventas diarias

```
📊 VENTAS DIARIAS — 2026-08-15
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💰 Total: €45.00 / Bs. 37,077.30
📦 Pedidos: 12
💧 Botellones: 28
❄️ Hielo: 15 bolsas

👤 Por chofer:
  YORDANIS: 7 pedidos, €28.00
  EVERT: 5 pedidos, €17.00

💳 Por método pago:
  Pago móvil: 8 pedidos, €32.00
  Efectivo: 4 pedidos, €13.00

📄 Documentos:
  Facturas: 3 (pendientes aprobación)
  Notas entrega: 9

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💧 Estación H2O
```

### 9.3 Estructura cierre semanal

```
📊 CIERRE SEMANAL — Semana 33 (10-16 ago 2026)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💰 Total semana: €287.50 / Bs. 236,829.75
📈 vs semana anterior: +12.5%

📦 Pedidos semana: 67
💧 Botellones: 152
❄️ Hielo: 89 bolsas

👤 Por chofer:
  YORDANIS: 38 pedidos, €165.00, 78 botellones
  EVERT: 29 pedidos, €122.50, 74 botellones

💰 Comisiones a pagar (viernes):
  YORDANIS: Bs. XX,XXX (€XX)
  EVERT: Bs. XX,XXX (€XX)

📊 Cuentas por cobrar:
  Pendiente: €45.00 (3 clientes)
  Vencido: €0

📦 Inventario crítico:
  Botellones: 142/160
  Hielo: 25 bolsas
  Tapas: 80 unidades

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💧 Estación H2O
```

### 9.4 Estructura nómina viernes

```
📋 NÓMINA VIERNES — 2026-08-15
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🚚 YORDANIS (Triciclo 1)
  Sueldo base: Bs. 50,000 / €40.00
  Botellones entregados: 78
  Comisión (78 × €0.20): €15.60
  Bonos: €5.00
  ───────────────────
  TOTAL: €60.60 / Bs. 49,925.40

🚚 EVERT (Triciclo 2)
  Sueldo base: Bs. 50,000 / €40.00
  Botellones entregados: 74
  Comisión (74 × €0.20): €14.80
  Bonos: €5.00
  ───────────────────
  TOTAL: €59.80 / Bs. 49,266.65

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TOTAL NÓMINA: €120.40 / Bs. 99,192.05

[Aprobar pago] → API Banco R4 automático
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💧 Estación H2O
```

---

## 10. ROLES HUMANOS

### 10.1 Matriz de interacción humana

| Tarea | Líder (Luis) | Contador | Choferes | Clientes |
|-------|:------------:|:--------:|:--------:|:--------:|
| Aprobar factura electrónica | ✅ Único | — | — | — |
| Aprobar nómina viernes | ✅ Único | — | — | — |
| Decidir factura vs nota (override) | ✅ Único | — | — | — |
| Cargar productos en Odoo | 🟡 1 vez | — | — | — |
| Cargar clientes en Odoo | 🟡 1 vez | — | — | — |
| Configurar tasas cambio | ⚠️ Solo si API falla | — | — | — |
| Marcar entrega completada | — | — | ✅ Bot Telegram | — |
| Reportar incidencia | ✅ (recibe) | — | — | ✅ WhatsApp |
| Declaración ISLR mensual | ✅ Aprueba | ✅ Ejecuta | — | — |
| Declaración dividendos anual | ✅ Aprueba | ✅ Ejecuta | — | — |
| Auditoría libros | ✅ Solicita | ✅ Ejecuta | — | — |
| Conciliación bancaria | ⚠️ Solo si API falla | ✅ Mensual | — | — |

### 10.2 Rutina diaria del Líder

| Hora | Acción | Tiempo |
|------|-------|--------|
| 8:00am | Revisar reporte inventario hielo (Telegram) | 2 min |
| 9:00am | Aprobar facturas pendientes (Odoo web) | 5-10 min |
| 1:00pm | Revisar ventas hasta el momento (Odoo dashboard) | 5 min |
| 6:00pm | Ver cierre del día (Telegram automático) | 2 min |
| **Total interactivo** | | **~20 min/día** |

### 10.3 Rutina semanal

| Día | Hora | Acción |
|-----|------|--------|
| Viernes | 5:00pm | Aprobar nómina choferes (Telegram → Aprobar) |
| Viernes | 6:00pm | Revisar cierre semanal (Telegram) |
| Lunes | 8:00am | Revisar inventario insumos (Telegram) |
| Día 1 mes | 9:00am | Enviar reporte ISLR a contador |

---

## 11. PLAN DE MIGRACIÓN

### 11.1 Estrategia: Odoo limpio

Como decidiste arrancar Odoo limpio (sin migrar históricos):

**Semana 0** (antes de FASE 1):
- Cerrar ciclo actual pedidos pendientes (20 pending + 14 scheduled)
- Snapshot BD actual como histórico inmutable
- A partir de fecha de corte, todo nuevo → Odoo

**Carga inicial en Odoo**:
- Clientes: cargar los ~16 actuales (manual, 1 vez)
- Productos: cargar botellón, hielo, insumos (manual, 1 vez)
- Inventario inicial: 160 botellones, X hielo, X insumos (manual, 1 vez)
- Empleados: 2 choferes (manual, 1 vez)
- Proveedor: 1 principal (manual, 1 vez)

### 11.2 Plantilla carga clientes

```csv
name,rif,phone,email,address,client_type,credit_limit
"Restaurante El Portal","J-12345678-9","+58412XXXXXXX","","Calle 72 Av 15, Maracaibo","restaurant",0
"Sra. González","V-87654321","+58414XXXXXXX","","Calle 69 Av 8, Maracaibo","retail",0
```

---

## 12. DECISIÓN FINANCIAL SHIELD

### 12.1 Análisis honesto

Actualmente Financial Shield tiene 8 módulos y 10 tablas fs_*. Con Odoo:

| Módulo FS actual | Odoo equivalente | Decisión |
|-----------------|-------------------|---------|
| `models.py` | sale.order, account.move | ❌ Eliminar (Odoo fuente verdad) |
| `database.py` | PostgreSQL Odoo | ❌ Eliminar |
| `currency.py` | res.currency + API R4 | 🟡 Simplificar (solo caché) |
| `cobranzas.py` | account.payment + cron | ❌ Eliminar (Odoo hace) |
| `nomina.py` | hr_payroll | ❌ Eliminar (Odoo hace) |
| `proveedores.py` | purchase.order + account.payable | ❌ Eliminar |
| `verificacion.py` | Custom (mantener) | ✅ Mantener (valida pagos antes Odoo) |
| `reportes.py` | Odoo reports + Telegram bot | 🟡 Adaptar (lee de Odoo) |

### 12.2 Propuesta: Financial Shield se transforma

**De**: sistema financiero completo (8 módulos)
**A**: capa de adaptación ligera para Valentina

```
ANTES (FS v2.0):
  Valentina → Financial Shield (10 tablas, 8 módulos)
  Financial Shield = fuente de verdad financiera

DESPUÉS (FS v3.0 simplificado):
  Valentina → FS Adaptador (2 módulos)
  Odoo = fuente de verdad financiera
  
  FS Adaptador:
  - odoo_sync.py: llama a Odoo XML-RPC
  - r4_client.py: integra API Banco R4
  - verificacion.py: valida pagos (mantener lógica)
  
  fs_pedidos, fs_pagos, fs_nomina = CACHE LOCAL
  (no fuente de verdad, solo caché para respuesta rápida a Valentina)
```

### 12.3 Migración progresiva

| Fase | FS estado | Odoo estado |
|------|----------|-------------|
| FASE 1-2 | Operativo | Configurándose |
| FASE 3 | Operativo + odoo_sync | Recibe pedidos |
| FASE 4 | Operativo + r4_client | Recibe pagos |
| FASE 5 | Simplificado (caché) | Nómina + reportes |
| FASE 6+ | Obsoleto (solo cache) | Fuente de verdad |

**Beneficio**: transición suave, sin "gran cambio" riesgoso.

---

## 13. CRONOGRAMA RESUMEN

| Semana | Foco | Entregable |
|--------|------|-----------|
| 1-2 | Odoo setup + módulo custom | Odoo operativo + lógica negocio |
| 3-4 | Integración Valentina | Pedidos automáticos WhatsApp → Odoo |
| 4-5 | API Banco R4 | Pagos automáticos <30s |
| 5-6 | Nómina + reportes | 5 reportes automáticos + nómina viernes |
| 6-8 | Facturación electrónica | Emisión legal SENIAT |
| 8 | Dashboard Líder | Vista única, 20 min/día |

**Tiempo total estimado**: 8 semanas (2 meses)

---

## 14. RIESGOS Y MITIGACIONES

| Riesgo | Probabilidad | Impacto | Mitigación |
|--------|-------------|---------|-----------|
| Odoo Community sin soporte oficial | Media | Medio | Comunidad OCA activa, nosotros mantenemos |
| API Banco R4 demora | Alta | Alto | Plan B: validación manual con comprobante |
| Facturación electrónica proveedor no confirmado | Alta | Alto | Mientras tanto notas entrega (operativa) |
| Cortes eléctricos afectan Odoo | Alta | Bajo | Docker + auto-restart + backup diario |
| Performance servidor con Odoo + bots | Media | Medio | 23GB RAM suficiente, monitorear |
| Curva aprendizaje Odoo | Media | Bajo | UI intuitiva, Líder ya familiarizado |
| Pérdida datos PostgreSQL | Baja | Crítico | Backup diario + WAL archiving |
| Migración FS → Odoo rompe Valentina | Media | Alto | Transición progresiva, FS como caché |

---

## 15. PRÓXIMOS PASOS INMEDIATOS

### Esta semana

1. **Líder aprueba esta arquitectura** (o sugiere cambios)
2. **Líder confirma con contador**:
   - Nombre del proveedor factura electrónica
   - Requisitos certificado digital
   - Fecha límite obligatoriedad
3. **Líder solicita a Banco R4**:
   - Credenciales API (sandbox primero)
   - Documentación endpoints
   - Webhook secret

### Próxima semana (cuando Hermes termine FASE 1.2 Dispatcher)

4. **Hermes inicia FASE 1 Odoo**:
   - Docker setup
   - Odoo Community 17 + PostgreSQL 15
   - Configuración inicial

### Pendientes paralelos

5. **Landing page v2** (web estacionh2o.com con ozonización)
6. **FASE 1.2 Dispatcher** (clients automáticos en dispatch.db)
7. **Carga de 16 clientes reales** en BD

---

## 16. ANEXOS

### A. docker-compose.yml propuesto

```yaml
version: '3.8'
services:
  odoo-db:
    image: postgres:15
    container_name: odoo-db
    environment:
      POSTGRES_DB: postgres
      POSTGRES_USER: odoo
      POSTGRES_PASSWORD: ${ODOO_DB_PASSWORD}
    volumes:
      - odoo-db-data:/var/lib/postgresql/data
    restart: unless-stopped

  odoo-web:
    image: odoo:17.0
    container_name: odoo-web
    depends_on:
      - odoo-db
    ports:
      - "8069:8069"
    environment:
      HOST: odoo-db
      USER: odoo
      PASSWORD: ${ODOO_DB_PASSWORD}
    volumes:
      - odoo-web-data:/var/lib/odoo
      - ./addons:/mnt/extra-addons
      - ./config:/etc/odoo
    restart: unless-stopped

volumes:
  odoo-db-data:
  odoo-web-data:
```

### B. Variables .env necesarias (nuevas)

```env
# === Odoo ===
ODOO_URL=http://localhost:8069
ODOO_DB=estacion_h2o_prod
ODOO_USERNAME=admin
ODOO_PASSWORD=[GENERAR_SEGURO]
ODOO_DB_PASSWORD=[GENERAR_SEGURO]

# === Banco R4 (cuando esté listo) ===
BANCO_R4_API_URL=https://api.r4.banco.com/v1
BANCO_R4_API_KEY=[PEGAR_CUANDO_ENTREGUEN]
BANCO_R4_WEBHOOK_SECRET=[PEGAR_CUANDO_ENTREGUEN]
BANCO_R4_ACCOUNT_NUMBER=01690010971001591583

# === Facturación electrónica (cuando esté listo) ===
FE_VE_PROVIDER=[DEFINIR]
FE_VE_CERT_PATH=/mnt/ssd_trabajo/hermes-agent/config/fe-ve.pem
FE_VE_CERT_PASSWORD=[PEGAR]
```

### C. Comandos útiles

```bash
# Levantar Odoo
cd /mnt/ssd_trabajo/hermes-agent/infra/odoo
docker-compose up -d

# Ver logs Odoo
docker logs -f odoo-web

# Backup BD Odoo
docker exec odoo-db pg_dump -U odoo postgres > /backups/odoo_$(date +%Y%m%d).sql

# Ver servicios activos
sudo systemctl status valentina-bridge cloudflared dispatcher-bot telegram-bot
docker ps
```

---

## 17. CIERRE

### 17.1 Decisión del Líder

Este documento requiere aprobación explícita del Líder antes de iniciar FASE 1.

**Preguntas para aprobación**:

1. ✅ ¿Apruebas la arquitectura propuesta (Odoo Community self-hosted)?
2. ✅ ¿Apruebas el plan de 8 semanas (2 meses)?
3. ✅ ¿Apruebas la transformación de Financial Shield (de 8 módulos a 2)?
4. ✅ ¿Apruebas el algoritmo de facturación discrecional?
5. ✅ ¿Apruebas el flujo de conversión nota→factura sin romper inventario?
6. ⚠️ ¿Confirmas con contador proveedor factura electrónica?
7. ⚠️ ¿Solicitas a Banco R4 credenciales API?

### 17.2 Compromiso

Una vez aprobado:
- Hermes inicia FASE 1 (Odoo + Docker) cuando termine FASE 1.2 Dispatcher
- Yo (Prometeo vía Z.ai) te asisto en configuraciones manuales
- Documentación viva en Obsidian `docs/02-arquitectura/`
- Commits en GitHub con `--no-verify` (tech debt documentado)

### 17.3 Filosofía

> "Efficiency or nothing." — Líder @elpelon27

Esta arquitectura respeta esa filosofía:
- ✅ Cero costo software (Odoo Community, Docker, PostgreSQL)
- ✅ Cero costo infraestructura (tu servidor existente)
- ✅ Mínima interacción humana (solo aprobar facturas)
- ✅ Máxima automatización (5 reportes + nómina automáticos)
- ✅ Transición progresiva (sin big-bang riesgoso)

---

**Que el agua fluya, dentro y fuera de la ley.** 💧

---

**Documento generado por**: Prometeo (GLM-4.6 vía Z.ai Code)
**Fecha**: Julio 2026
**Versión**: 1.0
**Destino**: `/mnt/ssd_trabajo/hermes-agent/docs/02-arquitectura/ARQUITECTURA-ODOO-ESTACION-H2O.md`
