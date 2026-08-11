# 📋 MANUAL DE DESPLIEGUE — Odoo + Estación H2O + Financial Shield

> **ADVERTENCIA LEGAL**: Este documento combina conocimientos técnicos con marco legal venezolano. 
> Las normativas tributarias cambian. Antes de poner en producción, **debes validar todo con un 
> contador público colegiado y/o abogado tributario venezolano**. Lo aquí descrito es 
> arquitectura técnica, no asesoría legal.

**Versión**: 1.0 | **Fecha**: Julio 2026 | **Autor**: Prometeo (GLM-4.6)
**Proyecto**: Estación H2O · Maracaibo, Zulia, Venezuela
**Destino**: `/mnt/ssd_trabajo/hermes-agent/docs/02-arquitectura/MANUAL-ODOO-SENIAT.md`

---

## 1. CONTEXTO Y ALCANCE

### 1.1 Situación actual del proyecto

| Componente | Estado | Tecnología |
|-----------|--------|-----------|
| Valentina (WhatsApp) | ✅ Producción | Python + FastAPI + Meta Cloud API |
| Financial Shield v2.0 | ✅ Operativo | 10 tablas fs_* en SQLite |
| Dispatcher (@DespachoH2O_bot) | ✅ Validado | Telegram Bot + OR-Tools VRP |
| Odoo Cloud | 🟡 Contratado | https://estacion-h2o.odoo.com/odoo |
| Landing page | 🟡 En desarrollo | Cloudflare Pages |
| Integración legal SENIAT | 🔴 Pendiente | Requiere investigación |

### 1.2 Objetivo del manual

1. **Integrar Odoo** con el sistema existente (Valentina + Financial Shield + Dispatcher)
2. **Cumplir normativas tributarias venezolanas** (SENIAT)
3. **Definir roles claros**: qué hace el Líder, qué hace Financial Shield, qué hace Odoo
4. **Plan de homologación** ante SENIAT

### 1.3 Honestidad técnica

Hay aspectos que NO puedo validar solo:
- ❌ Resoluciones SENIAT específicas vigentes 2025-2026 (deben verificarse en seniat.gob.ve)
- ❌ Si Odoo está homologado oficialmente (probablemente NO)
- ❌ Requisitos exactos de facturación electrónica si ya es obligatoria
- ❌ Lista de impresoras fiscales homologadas vigente

Lo que SÍ puedo diseñar:
- ✅ Arquitectura técnica de integración
- ✅ Flujo de datos entre Valentina/Odoo/Financial Shield
- ✅ API endpoints necesarios
- ✅ Roles y responsabilidades
- ✅ Plan de despliegue paso a paso

---

## 2. MARCO LEGAL VENEZOLANO — Lo que necesitas saber

### 2.1 Impuestos aplicables a Estación H2O

| Impuesto | Tasa 2025 | Aplica a Estación H2O | Base legal |
|---------|----------|----------------------|-----------|
| **IVA** (Impuesto al Valor Agregado) | 16% | ✅ Sí, sobre ventas | Ley IVA vigente |
| **ISLR** (Impuesto Sobre la Renta) | Escala progresiva 6-34% | ✅ Sí, sobre utilidades | Ley ISLR |
| **IGTF** (Grandes Transacciones Financieras) | 3% | ⚠️ Solo si aceptas divisas en efectivo (USD/EUR) | Ley IGTF 2022 modificada |
| **Patente Industria y Comercio** | Variable municipal | ✅ Sí, obligatorio en Maracaibo | Ordenanza Municipal |
| **Tasa de Bomberos** | ~0.5-1% | ✅ Sí, en Maracaibo | Ordenanza Municipal |

### 2.2 Clasificación tributaria de Estación H2O

Existen dos categorías en Venezuela:

| Categoría | Requisitos | Estación H2O |
|-----------|-----------|---------------|
| **Contribuyente Ordinario** | Ventas < 75,000 UT anuales | Probable ✅ (verificar con contador) |
| **Contribuyente Especial** | Designado por SENIAT (voluntario o por volumen) | Probable no aún |

> **ACCIÓN**: tu contador debe confirmar en qué categoría estás. Esto define qué requisitos aplican.

### 2.3 Régimen de facturación en Venezuela

Venezuela tiene **tres modalidades** de facturación:

#### Modalidad A: Impresora Fiscal (tradicional)
- Equipo físico homologado por SENIAT
- Imprime factura fiscal con memoria fiscal
- Marcas: Befequitas, Epson, Hasar, Schreiber
- Costo: ~$500-1500 por impresora
- Obligatorio para contribuyentes especiales

#### Modalidad B: Factura Libre (sin impresora fiscal)
- Para contribuyentes ordinarios
- Facturas impresas en cualquier impresora
- Debe cumplir requisitos formales (RIF, número correlativo, etc.)
- Sistema de facturación propio u Odoo

#### Modalidad C: Factura Electrónica (en proceso de implementación)
- SENIAT está migrando hacia factura electrónica
- Implementación gradual por sectores
- Requiere software homologado + certificado digital
- Estado actual 2025: piloto, no universalmente obligatorio

> **VERIFICAR**: con tu contador cuál modalidad te aplica HOY. Esto define el alcance del proyecto.

### 2.4 Requisitos formales de toda factura venezolana

Independiente de la modalidad, toda factura debe contener:

1. ✅ Razón social completa de Estación H2O
2. ✅ RIF (J-XXXXXXXX-X) visible
3. ✅ Dirección fiscal completa
4. ✅ Teléfono de contacto
5. ✅ Número de factura correlativo
6. ✅ Fecha de emisión
7. ✅ Datos del cliente (nombre, RIF/CI, dirección)
8. ✅ Descripción detallada del producto/servicio
9. ✅ Cantidad y unidad (litros, bolsas, unidades)
10. ✅ Precio unitario + total
11. ✅ Descuento (si aplica)
12. ✅ Subtotal, IVA (16%), Total
13. ✅ "Contribuyente ordinario/especial" (según caso)
14. ✅ "Obligado a llevar libros" (si aplica)
15. ✅ Número de control y zeta (si impresora fiscal)

---

## 3. ARQUITECTURA DE INTEGRACIÓN PROPUESTA

### 3.1 Diagrama del sistema completo

```
┌─────────────────────────────────────────────────────────────┐
│                    CLIENTES (WhatsApp)                       │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│              VALENTINA (bridge.py :8000)                      │
│  Estado: ✅ Producción                                       │
│  - Recibe pedidos WhatsApp                                   │
│  - State machine determinístico                              │
│  - NEXO UX aplicado                                          │
└──────┬────────────────────────────────────────┬─────────────┘
       │                                        │
       ▼                                        ▼
┌──────────────────────┐         ┌──────────────────────────────┐
│   DISPATCH QUEUE      │         │   FINANCIAL SHIELD v2.0      │
│   (conversations.db)  │         │   (conversations.db)          │
│   Estado: ✅ Activo    │         │   Estado: ✅ Operativo       │
└──────────┬───────────┘         │   - fs_pedidos                │
           │                     │   - fs_pagos                  │
           ▼                     │   - fs_nomina                 │
┌──────────────────────┐         │   - fs_cuentas_cobrar         │
│   DISPATCHER BOT     │         │   - fs_tasas_cambio           │
│   (@DespachoH2O_bot) │         │   - fs_productos              │
│   Estado: ✅ Validado │         │   - fs_verificacion_log       │
└──────────────────────┘         └──────────┬───────────────────┘
                                            │
                                            │ API REST (nueva)
                                            ▼
                                ┌──────────────────────────────┐
                                │      ODOO CLOUD              │
                                │  estacion-h2o.odoo.com       │
                                │  Estado: 🟡 Contratado       │
                                │  - Facturación                │
                                │  - Inventario                 │
                                │  - Contabilidad               │
                                │  - Clientes (CRM)             │
                                └──────────┬───────────────────┘
                                           │
                                           ▼
                                ┌──────────────────────────────┐
                                │  IMPRESORA FISCAL / PDF       │
                                │  (según modalidad SENIAT)     │
                                └──────────────────────────────┘
```

### 3.2 Responsabilidades por componente

| Componente | Qué hace | Qué NO hace |
|-----------|---------|-------------|
| **Valentina** | Recibe pedidos WhatsApp, confirma, deriva | No factura, no calcula impuestos |
| **Financial Shield** | Registra pedidos, pagos, nómina, tasas | No emite facturas fiscales |
| **Odoo** | Factura, contabilidad, inventario, CRM | No atiende WhatsApp, no despacha |
| **Dispatcher** | Optimiza rutas, envía choferes | No factura, no cobra |
| **Líder** | Decisiones, configuración, supervisión | No opera el día a día manual |
| **Contador** | Validación legal, declaraciones, libros | No programa, no opera sistema |

### 3.3 Flujo de datos completo (pedido → factura)

```
1. Cliente WhatsApp → "Hola, quiero 3 botellones"
         │
         ▼
2. Valentina (bridge.py) 
   - Toma pedido
   - Calcula total €X.XX
   - Pide método de pago
         │
         ▼
3. INSERT en dispatch_queue (conversations.db)
   + INSERT en fs_pedidos (Financial Shield)
         │
         ▼
4. Cliente paga (móvil/effectivo)
   - Valentina confirma pago
   - INSERT en fs_pagos
         │
         ▼
5. 🆕 NUEVO: Trigger asíncrono a Odoo
   POST https://estacion-h2o.odoo.com/api/v1/invoices
   {
     "cliente": {"nombre": "...", "rif_ci": "...", "direccion": "..."},
     "items": [{"producto": "Botellón 19L", "cantidad": 3, "precio": 1.00}],
     "subtotal": 3.00,
     "iva": 0.48,
     "total": 3.48,
     "metodo_pago": "pago_movil_bs" | "efectivo_eur",
     "tasa_cambio_usada": 823.94
   }
         │
         ▼
6. Odoo recibe → genera factura fiscal
   - Asigna número correlativo
   - Aplica formato legal venezolano
   - Si impresora fiscal: imprime automáticamente
   - Si factura libre: genera PDF
         │
         ▼
7. Odoo retorna:
   {
     "invoice_id": 1234,
     "invoice_number": "FA-2026-0001",
     "pdf_url": "https://estacion-h2o.odoo.com/...",
     "control_number": "..."
   }
         │
         ▼
8. Valentina → cliente por WhatsApp:
   "✅ Factura emitida. Si desea copia digital, escríbame su email."
```

---

## 4. ROL DEL LÍDER vs FINANCIAL SHIELD

### 4.1 Matriz de responsabilidades

| Tarea | Líder (Luis) | Financial Shield | Odoo | Valentina | Contador |
|-------|:------------:|:----------------:|:----:|:---------:|:--------:|
| **Configuración inicial Odoo** | ✅ Decide | — | 🟡 Recibe config | — | ⚠️ Valida |
| **Cargar productos en Odoo** | ✅ Aprueba | — | 🟡 Almacena | — | — |
| **Registrar clientes en Odoo** | — | 🟡 Sincroniza | ✅ Almacena | — | — |
| **Recibir pedido WhatsApp** | — | — | — | ✅ Atiende | — |
| **Calcular total + IVA** | — | 🟡 Pre-calcula | ✅ Emite | — | — |
| **Generar factura fiscal** | — | — | ✅ Emite | — | ⚠️ Supervisa |
| **Registrar pago** | — | ✅ fs_pagos | 🟡 Sincroniza | — | ⚠️ Revisa |
| **Calcular comisión choferes** | — | ✅ fs_nomina | — | — | — |
| **Declarar IVA mensual** | ✅ Autoriza | — | 🟡 Exporta | — | ✅ Ejecuta |
| **Declarar ISLR anual** | ✅ Autoriza | — | 🟡 Exporta | — | ✅ Ejecuta |
| **Cargar tasas de cambio** | ✅ Define | ✅ fs_tasas | — | — | — |
| **Resolver disputas** | ✅ Decide | 🟡 Reporta | — | — | — |
| **Auditar libros** | ✅ Solicita | — | 🟡 Exporta | — | ✅ Ejecuta |

### 4.2 Lo que maneja Financial Shield (extendido para Odoo)

El Financial Shield actual tiene 8 módulos. Para integrar Odoo necesitas agregar:

#### Módulo NUEVO: `odoo_sync.py`

```python
"""
Financial Shield - Módulo Odoo Sync
Sincroniza fs_pedidos y fs_pagos con Odoo Cloud.
Trigger: cuando pedido pasa a "completed" en Valentina.
"""
import httpx
import logging
from typing import Optional

logger = logging.getLogger("financial_shield.odoo_sync")

ODOO_URL = "https://estacion-h2o.odoo.com"
ODOO_DB = "estacion-h2o"
ODOO_USERNAME = "administracion@estacionh2o.com"
ODOO_PASSWORD = "[CONFIGURAR_EN_.env]"
ODOO_API_KEY = "[GENERAR_EN_ODOO]"


class OdooSync:
    """Cliente asíncrono para Odoo XML-RPC / JSON-RPC."""
    
    def __init__(self):
        self.uid: Optional[int] = None
        self.base_url = f"{ODOO_URL}/jsonrpc"
    
    async def authenticate(self) -> int:
        """Autentica con Odoo y retorna UID."""
        # Implementar XML-RPC common.authenticate
        pass
    
    async def create_invoice(self, pedido_data: dict) -> dict:
        """Crea factura en Odoo desde un fs_pedido."""
        # 1. Verificar/crear cliente en Odoo
        # 2. Crear factura con líneas
        # 3. Aplicar impuestos IVA 16%
        # 4. Confirmar factura
        # 5. Retornar invoice_id + pdf_url
        pass
    
    async def sync_payment(self, pago_data: dict) -> bool:
        """Registra pago en Odoo desde fs_pagos."""
        # 1. Buscar factura por número
        # 2. Registrar pago (móvil/effectivo)
        # 3. Conciliar
        pass
    
    async def export_daily_report(self, fecha: str) -> dict:
        """Exporta resumen diario para declaración."""
        # Ventas totales, IVA cobrado, pagos recibidos
        pass
```

#### Modificaciones a módulos existentes

| Módulo | Cambio necesario |
|--------|-----------------|
| `database.py` | Agregar tabla `odoo_sync_log` (invoice_id, fs_pedido_id, sync_at, status) |
| `models.py` | Agregar dataclass `OdooInvoice` |
| `cobranzas.py` | Tras registrar pago en fs_pagos → trigger sync_payment Odoo |
| `nomina.py` | Sin cambios (Odoo no gestiona nómina de choferes) |
| `reportes.py` | Generar reporte desde Odoo + Financial Shield combinado |
| `currency.py` | Sin cambios (Odoo puede leer nuestras tasas) |

---

## 5. PLAN DE DESPLIEGUE PASO A PASO

### 5.1 Pre-requisitos (verificar antes de empezar)

| Item | Estado | Acción si falta |
|------|--------|----------------|
| Cuenta Odoo Cloud activa | 🟡 Verificar | Login en estacion-h2o.odoo.com |
| RIF jurídico de Estación H2O | ✅ (probable) | Si no, gestionar en SENIAT |
| Clasificación contribuyente (ordinario/especial) | 🔴 Verificar | Preguntar a contador |
| Patente Industria y Comercio Maracaibo | 🔴 Verificar | Alcaldía Maracaibo |
| Contador público colegiado asignado | 🔴 Recomendar | Si no tienes, buscar uno |
| API key Odoo generada | 🔴 Generar | Settings → User → API Keys |
| Acceso SSH al servidor | ✅ Confirmado | — |
| Backup completo del proyecto | ✅ Hecho | hermes-agent-backup-20260721.tar.gz |

### 5.2 Fase 1: Configuración Odoo (1 día)

#### Paso 1.1: Activar modo desarrollador en Odoo

1. Login en https://estacion-h2o.odoo.com
2. Settings → Scroll abajo → "Activate developer mode"
3. Aparece icono "🔧" en menú superior

#### Paso 1.2: Configurar empresa

Settings → Companies → Estación H2O:

| Campo | Valor |
|-------|-------|
| Company Name | Estación H2O, C.A. (ver RIF exacto) |
| RIF / VAT | J-XXXXXXXX-X (pegar RIF real) |
| Address | Av 8 con Calle 68/69, Hotel Kristoff |
| City | Maracaibo |
| State | Zulia |
| Country | Venezuela |
| Phone | +58 412-2560721 |
| Email | administracion@estacionh2o.com |
| Website | https://estacionh2o.com (cuando esté arriba) |
| Currency | VES (Bolívares) + EUR (secundaria) |

#### Paso 1.3: Configurar impuestos venezolanos

Accounting → Configuration → Taxes → Crear:

| Tax Name | Amount | Type | Affects |
|----------|--------|------|---------|
| IVA 16% Venta | 16.00% | Tax included in price | Sales |
| IVA 16% Compra | 16.00% | Tax excluded | Purchases |
| IGTF 3% USD efectivo | 3.00% | Tax on total (if applies) | Sales |
| Exento IVA | 0% | Tax | Sales (botellón intercambio) |

#### Paso 1.4: Cargar productos

Inventory → Products → Crear:

| Producto | Precio | Unidad | Impuesto | Tipo |
|---------|--------|--------|----------|------|
| Botellón Agua 19L | €1.00 / Bs. XX | Unidad | IVA 16% | Consumible |
| Bolsa Hielo | €1.20 / Bs. XX | Unidad | IVA 16% | Consumible |
| Recarga Botellón (servicio) | €1.00 | Servicio | IVA 16% | Service |
| Botellón Vacío (garantía) | €10.00 | Unidad | Exento | Consumible |

#### Paso 1.5: Generar API key

Settings → Users → administracion@estacionh2o.com → Account Security → New API Key

Guarda la key en:
```bash
echo 'ODOO_API_KEY=[PEGAR_AQUI]' >> /mnt/ssd_trabajo/hermes-agent/config/.env
echo 'ODOO_URL=https://estacion-h2o.odoo.com' >> /mnt/ssd_trabajo/hermes-agent/config/.env
echo 'ODOO_DB=estacion-h2o' >> /mnt/ssd_trabajo/hermes-agent/config/.env
echo 'ODOO_USERNAME=administracion@estacionh2o.com' >> /mnt/ssd_trabajo/hermes-agent/config/.env
```

### 5.3 Fase 2: Desarrollo integración (3 días)

#### Paso 2.1: Crear módulo `src/financial/odoo_sync.py`

Responsabilidades:
- Autenticación XML-RPC con Odoo
- `create_invoice(pedido)` → retorna invoice_id
- `sync_payment(pago)` → registra pago
- `get_invoice_pdf(invoice_id)` → descarga PDF
- `export_daily_report(fecha)` → resumen para declaraciones

#### Paso 2.2: Modificar `api/bridge.py`

Agregar trigger en `_send_to_dispatch_queue` (línea 796):

```python
# Después de insertar en dispatch_queue:
async def _trigger_odoo_invoice(ph_hash, state, from_phone):
    """Cuando pedido se completa, crear factura en Odoo."""
    try:
        from src.financial.odoo_sync import OdooSync
        odoo = OdooSync()
        pedido_data = {
            "cliente_nombre": state.get("contact_name", ""),
            "cliente_telefono": from_phone,
            "items": [...],
            "subtotal": state.get("total_eur", 0),
            "metodo_pago": state.get("payment_method", ""),
        }
        invoice = await odoo.create_invoice(pedido_data)
        logger.info("Factura Odoo creada: %s", invoice["invoice_number"])
    except Exception as e:
        logger.error("Error sync Odoo: %s", e)
        # NO bloquear el flujo principal
```

#### Paso 2.3: Crear endpoint para recibir webhook de Odoo

```python
@app.post("/webhook/odoo")
async def odoo_webhook(request: Request):
    """Recibe eventos de Odoo (pago registrado, factura cancelada, etc.)."""
    # Validar token
    # Procesar evento
    # Actualizar fs_pedidos / fs_pagos
```

### 5.4 Fase 3: Pruebas y validación (2 días)

1. **Pedido de prueba** → verificar factura Odoo creada
2. **Pago registrado** → verificar sincronización
3. **PDF generado** → verificar formato legal
4. **Reporte diario** → verificar totales
5. **Conciliación** → cuadrar Financial Shield vs Odoo

### 5.5 Fase 4: Homologación SENIAT (variable)

#### 4.1 Decidir modalidad de facturación

| Modalidad | Costo | Tiempo | Recomendado para Estación H2O |
|----------|-------|--------|-------------------------------|
| **Impresora Fiscal** | $500-1500 | 1-2 meses | Si contribuyente especial |
| **Factura Libre (Odoo)** | $0 hardware | Inmediato | Si contribuyente ordinario |
| **Factura Electrónica** | Costo software homologado | 2-6 meses | Verificar si ya obligatorio |

> **DECISIÓN CLAVE**: tu contador debe decirte cuál aplica.

#### 4.2 Requisitos de homologación (verificar con SENIAT)

Posibles requisitos (verificar vigencia):
- ✅ RIF jurídico vigente
- ✅ Inscripción en registro de contribuyentes
- ✅ Sistema de facturación (Odoo + adaptación)
- ✅ Si impresora fiscal: equipo homologado + técnico certificado
- ✅ Si electrónica: certificado digital
- ✅ Libros de compra/venta actualizados

#### 4.3 Procedimiento sugerido

1. **Reunión con contador** (1h): clasificar contribuyente, decidir modalidad
2. **Validar Odoo** (1 día): cumple requisitos formales?
3. **Si impresora fiscal** (2-4 semanas): comprar equipo, instalar, configurar
4. **Si electrónica** (1-3 meses): tramitar certificado, instalar software homologado
5. **Solicitud SENIAT** (variable): formalizar homologación
6. **Capacitación personal** (1 día): cómo usar el sistema final

---

## 6. RECURSOS NECESARIOS

### 6.1 Recursos humanos

| Rol | Quién | Dedicación | Costo aprox |
|------|-------|-----------|-------------|
| Líder / Decisiones | Luis Martinez | 2h/semana | — |
| Contador público | Por contratar | 4h/mes | $50-150/mes |
| Desarrollador integración | Prometeo (Hermes Agent) | 3 días | $0 (in-house) |
| Asesor legal tributario | Por contratar (1 consulta) | 2h | $50-100 una vez |
| Técnico impresora fiscal (si aplica) | Por contratar | 1 día | $100-200 una vez |

### 6.2 Recursos técnicos

| Recurso | Costo | Estado |
|---------|-------|--------|
| Odoo Cloud (ya contratado) | Variable según plan | ✅ |
| Servidor local | $0 (ya tienes) | ✅ |
| Dominio estacionh2o.com | $0 (ya pagado) | ✅ |
| Impresora fiscal (si aplica) | $500-1500 | 🔴 Por comprar |
| Certificado digital (si electrónica) | $50-200/año | 🔴 Por tramitar |
| Backup offsite (Google Drive gratis) | $0 | ✅ |

### 6.3 Recursos de información legal

| Fuente | URL | Uso |
|--------|-----|-----|
| SENIAT oficial | http://www.seniat.gob.ve | Consultar resoluciones vigentes |
| Ley IVA | Buscar versión vigente | Base legal impuestos |
| Ley ISLR | Buscar versión vigente | Base legal renta |
| Ley IGTF | Gaceta Oficial 2022 | Grandes transacciones |
| Ordenanza Maracaibo | Alcaldía Maracaibo | Patente industria/comercio |

---

## 7. PLAN DE ACCIÓN INMEDIATO

### Esta semana (Líder)

1. **Reunión con contador** (1h)
   - Preguntas clave:
     - ¿Soy contribuyente ordinario o especial?
     - ¿Qué modalidad de facturación me aplica?
     - ¿Necesito impresora fiscal?
     - ¿Está obligado Estación H2O a factura electrónica ya?
     - ¿Qué libros debo llevar?
     - ¿Cómo declaro IVA mensual?
   
2. **Verificar cuenta Odoo** (30 min)
   - Login en https://estacion-h2o.odoo.com
   - Verificar plan contratado
   - Verificar módulos disponibles
   - Generar API key

3. **Recopilar documentos** (1 día)
   - RIF jurídico vigente
   - Documento constitutivo empresa
   - Última declaración IVA
   - Última declaración ISLR
   - Patente municipal

### Próxima semana (Prometeo + Líder)

1. **Desarrollar `src/financial/odoo_sync.py`** (3 días con Hermes Agent)
2. **Modificar `api/bridge.py`** para trigger Odoo (1 día)
3. **Pruebas integración** (2 días)
4. **Documentar en Obsidian** (1 día)

### Mes siguiente

1. **Homologación SENIAT** (según contador)
2. **Capacitación uso Odoo** (videos tutoriales)
3. **Migración datos históricos** (pedidos pasados a Odoo)
4. **Puesta en producción**

---

## 8. RIESGOS Y MITIGACIONES

| Riesgo | Probabilidad | Impacto | Mitigación |
|--------|-------------|---------|-----------|
| Odoo no homologado SENIAT | Alta | Alto | Verificar con contador antes de invertir tiempo |
| Cambios normativos durante implementación | Media | Medio | Mantener contacto con contador, revisar seniat.gob.ve mensual |
| Cortes eléctricos afectan sync Odoo | Alta | Bajo | Queue local + retry cuando vuelva luz |
| API Odoo cambia | Baja | Medio | Versionar integración, monitorear |
| Pérdida de datos fiscales | Baja | Crítico | Backup diario + replicación Odoo Cloud |
| Mala clasificación tributaria | Media | Alto | Asesoría legal inicial obligatoria |

---

## 9. CHECKLIST FINAL

Antes de dar por completada la integración:

- [ ] Contador clasificó contribuyente
- [ ] Modalidad facturación definida
- [ ] Odoo configurado con empresa correcta
- [ ] Productos cargados en Odoo
- [ ] API key generada y guardada en .env
- [ ] Módulo `odoo_sync.py` desarrollado
- [ ] Trigger en bridge.py activo
- [ ] Webhook Odoo → Valentina operativo
- [ ] Pruebas end-to-end OK
- [ ] PDF facturas cumple requisitos legales
- [ ] Libros contables generan correctamente
- [ ] Personal capacitado
- [ ] Backup automatizado
- [ ] Homologación SENIAT tramitada (si aplica)
- [ ] Documentación completa en Obsidian

---

## 10. PRÓXIMOS PASOS RECOMENDADOS

### Inmediato (hoy)

1. **Agenda reunión con contador** — sin esto no avances
2. **Verifica login Odoo** — confirmar acceso
3. **Pásale este manual a Hermes** para que lo guarde en Obsidian

### Corto plazo (esta semana)

4. **Recolecta documentos legales** mencionados
5. **Define modalidad facturación** con contador
6. **Cuando Hermes termine FASE 1.2 Dispatcher**, él puede empezar `odoo_sync.py`

### Medio plazo (próximo mes)

7. **Desarrollo módulo Odoo sync**
8. **Pruebas integración**
9. **Homologación SENIAT**

---

## 11. ANEXOS

### A. Preguntas para el contador

Imprimir y llevar a la primera reunión:

1. ¿Soy contribuyente ordinario o especial?
2. ¿Qué modalidad de facturación me aplica?
3. ¿Necesito impresora fiscal?
4. ¿Está Estación H2O obligado a factura electrónica ya?
5. ¿Qué libros contables debo llevar?
6. ¿Cómo declaro IVA mensual?
7. ¿Cómo declaro ISLR anual?
8. ¿Aplica IGTF a mi negocio?
9. ¿Qué patente municipal necesito?
10. ¿Odoo como sistema de facturación es válido?
11. ¿Qué requisitos formales debe cumplir mi factura?
12. ¿Puedo aceptar pago en USD/EUR en efectivo?
13. ¿Qué tasa de cambio uso para declarar?
14. ¿Cada cuánto debo declarar?
15. ¿Qué multas aplican si me equivoco?

### B. Comandos útiles

```bash
# Verificar API Odoo accesible
curl -s https://estacion-h2o.odoo.com/web/login -o /dev/null -w "%{http_code}\n"

# Verificar .env tiene Odoo vars
grep ODOO /mnt/ssd_trabajo/hermes-agent/config/.env

# Backup Financial Shield antes de integrar
sqlite3 /mnt/ssd_trabajo/hermes-agent/data/conversations.db ".backup '/tmp/fs_backup_$(date +%Y%m%d).db'"

# Verificar Valentina sigue funcionando tras cambios
curl -s https://valentina.estacionh2o.com/health | python3 -m json.tool
```

### C. Documentos de referencia (pendientes de leer)

- [ ] Ley IVA Venezuela (versión vigente)
- [ ] Ley ISLR Venezuela (versión vigente)
- [ ] Ley IGTF (Gaceta Oficial 2022)
- [ ] Resoluciones SENIAT recientes
- [ ] Ordenanza Patente Industria y Comercio Maracaibo
- [ ] Manual Odoo facturación
- [ ] Lista impresoras fiscales homologadas (si aplica)

---

**DOCUMENTO TÉCNICO — NO ES ASESORÍA LEGAL**

Para completar este manual correctamente, necesitas:
1. Reunión con contador público colegiado venezolano
2. Validación de resoluciones SENIAT vigentes
3. Decisión sobre modalidad facturación
4. Confirmación de que Odoo cumple requisitos (probablemente requiere adaptación local)

**Que el agua fluya, dentro y fuera de la ley.** 💧

---

**Generado por**: Prometeo (GLM-4.6 vía Z.ai Code)
**Fecha**: Julio 2026
**Versión**: 1.0
**Destino**: `/mnt/ssd_trabajo/hermes-agent/docs/02-arquitectura/MANUAL-ODOO-SENIAT.md`
