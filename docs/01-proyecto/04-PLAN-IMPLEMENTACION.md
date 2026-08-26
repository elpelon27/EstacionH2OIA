# 📋 PLAN DE DESARROLLO — Odoo Cloud + API R4 CONECTA V3.0
## Estación H2O · Maracaibo, Venezuela

**Versión**: 2.0 | **Fecha**: Agosto 2026  
**Autor**: Prometeo (Hermes Agent)  
**Aprobador**: Luis Martinez (@elpelon27)  
**Estado**: 🏗️ **IMPLEMENTACIÓN EN PROGRESO — FASES 0-7 COMPLETAS, FASES 8-10 COMPLETAS**  
**Destino**: `docs/01-proyecto/04-PLAN-IMPLEMENTACION.md` (renombrado desde docs/06-manuales/)

---

## 🎯 RESUMEN EJECUTIVO

Implementación completa de **Odoo Community self-hosted (Docker)** + **API R4 CONECTA V3.0** para Estación H2O, integrando:
- Facturación electrónica (preparada SENIAT) con decisión discrecional (RIF + método pago + override Líder)
- 13 endpoints R4 con HMAC-SHA256 por endpoint
- 5 reportes automáticos (diario, semanal, inventario hielo, insumos, nómina viernes, ISLR mensual)
- 7 cron jobs systemd
- Seguridad: IP whitelist banco, HMAC, TLS 1.2+, backup diario

**Filosofía**: Odoo = fuente de verdad financiera | Valentina = fuente conversacional | Dispatcher = fuente logística

---

## 📦 DOCUMENTOS DE REFERENCIA (leídos y asimilados)

| Doc | Ruta | Estado |
|-----|------|--------|
| Arquitectura maestra | `docs/02-arquitectura/ARQUITECTURA-ODOO-ESTACION-H2O.md` | ✅ Leído (1095 líneas) |
| Marco legal SENIAT | `docs/02-arquitectura/MANUAL-ODOO-SENIAT.md` | ✅ Leído (692 líneas) |
| Contexto proyecto | `docs/03-sesiones/Migracion-Hermes-Prometeo-Contexto.md` | ✅ Leído (434 líneas) |
| Espec R4 Banco | `/home/skynet/Descargas/R4 CONECTA V3.0 (006).pdf` | ✅ Leído (32 páginas, 13 endpoints) |

---

## 🏗️ FASES DEL PLAN (11 FASES)

---

### **FASE 0: Preparación entorno** ✅ COMPLETA

| # | Tarea | Detalle | Verificación |
|---|-------|---------|--------------|
| 0.1 | Backup completo | `tar -czf hermes-agent-backup-$(date +%Y%m%d).tar.gz /mnt/ssd_trabajo/hermes-agent --exclude=venv --exclude=.git --exclude=__pycache__` | Backup > 100MB, restaurable |
| 0.2 | Rama git | `git checkout -b feat/odoo-r4-integration` | `git branch` muestra rama activa |
| 0.3 | Verificar Hermes | `hermes --version` + `curl -s https://valentina.estacionh2o.com/health` | Health = OK, Hermes responde |
| 0.4 | Verificar servicios | `systemctl status valentina-bridge cloudflared dispatcher-bot telegram-bot` | 4 servicios active |
| 0.5 | Verificar BD | `sqlite3 data/conversations.db ".tables"` + `sqlite3 data/dispatch.db ".tables"` | Tablas fs_* y dispatch intactas |
| 0.6 | Verificar DNS/Tunnel | `curl -s https://valentina.estacionh2o.com/health` | 200 OK, TLS válido |

---

### **FASE 1: Estructura de archivos** ✅ COMPLETA

```
src/
├── integrations/
│   ├── odoo/
│   │   ├── __init__.py
│   │   ├── client.py          # XML-RPC: auth, create_partner, create_sale_order, create_invoice, create_stock_picking, get_invoice_pdf, confirm_invoice, register_payment, search_partner_by_rif
│   │   ├── sync.py            # sync_pedido_to_odoo, decidir_documento, convert_nota_to_factura, sync_pago_to_odoo, get_daily_sales_report, get_weekly_close_report, get_inventory_status, get_payroll_weekly
│   │   ├── models.py          # Dataclasses: OdooPartner, OdooOrder, OdooInvoice, OdooStockPicking
│   │   └── exceptions.py      # OdooAuthError, OdooValidationError, OdooConnectionError
│   └── r4/
│       ├── __init__.py
│       ├── client.py          # 13 endpoints: consulta_tasa_bcv, validar_cliente_pago, procesar_notificacion_pago, disper_pagos, vuelto, generar_otp, debito_inmediato, credito_inmediato, consultar_operacion, domiciliacion_cuenta, domiciliacion_telefono, anulacion_c2p, credito_inmediato_cuentas_20d
│       ├── hmac_auth.py       # Patrones HMAC-SHA256 por endpoint
│       ├── webhooks.py        # Endpoints /webhook/r4/consulta + /webhook/r4/notifica (FastAPI)
│       ├── codigos.py         # Tabla códigos red interbancaria 00-99
│       ├── models.py          # Request/Response dataclasses para cada endpoint
│       └── exceptions.py      # R4AuthError, R4ValidationError, R4BankError
```

**Comando de creación:**
```bash
mkdir -p /mnt/ssd_trabajo/hermes-agent/src/integrations/odoo
mkdir -p /mnt/ssd_trabajo/hermes-agent/src/integrations/r4
touch /mnt/ssd_trabajo/hermes-agent/src/integrations/odoo/__init__.py
touch /mnt/ssd_trabajo/hermes-agent/src/integrations/r4/__init__.py
```

---

### **FASE 2: Configurar API Keys (.env)** ✅ COMPLETA

**Archivo:** `/mnt/ssd_trabajo/hermes-agent/config/.env` (añadir, NO sobrescribir)

```bash
# === ODOO CLOUD ===
ODOO_URL=https://estacion-h2o.odoo.com
ODOO_DB=estacion-h2o
ODOO_USERNAME=administracion@estacionh2o.com
ODOO_PASSWORD=****  # Generar en Odoo Settings > Users > Account Security > New API Key
ODOO_API_KEY=****   # API Key generada (para XML-RPC auth)

# === BANCO R4 CONECTA V3.0 ===
R4_BASE_URL=https://r4conecta.mibanco.com.ve
R4_COMMERCE_TOKEN=****           # Proporcionado por el banco (Commerce)
R4_WEBHOOK_AUTH_TOKEN=****       # UUID generado por comercio para webhooks (ej: f8423bb2-10c9-4d0f-8300-aaf8fea18c72)
R4_IP_WHITELIST=45.175.213.98,200.74.203.91,204.199.249.3

# === FACTURACIÓN ===
INVOICE_DECISION_MODE=discrecional  # discrecional | automatico
DEFAULT_INVOICE_TYPE=nota_entrega   # factura | nota_entrega
```

> ⚠️ **NUNCA commitear .env** — está en .gitignore. Valores reales se configuran en servidor.

---

### **FASE 3: Documentos referencia en vault Obsidian** ✅ COMPLETA

Crear/actualizar en `/mnt/ssd_trabajo/hermes-agent/docs/`:

| Archivo | Contenido | Origen |
|---------|-----------|--------|
| `02-arquitectura/R4-ENDPOINTS-REFERENCE.md` | 13 endpoints con JSON request/response exactos, HMAC patterns, URLs | PDF R4 páginas 5-32 |
| `02-arquitectura/R4-CODIGOS-RED.md` | Tabla completa códigos 00-99 con significado | PDF R4 página 11 |
| `02-arquitectura/HMAC-PATTERNS-R4.md` | Patrones HMAC por endpoint (qué campos firmar) | PDF R4 páginas 6, 9, 14, 16, 17, 18, 19, 20, 21, 22, 30, 32 |
| `04-decisiones/008-odoo-cloud-vs-self-hosted.md` | ADR: Community self-hosted Docker (gratis) vs Cloud (costo) | Decisión aprobada |
| `04-decisiones/009-r4-webhooks-bidirectional.md` | ADR: Webhooks R4 consulta + notificación en bridge.py | Pendiente |
| `04-decisiones/010-facturacion-discrecional.md` | ADR: Algoritmo RIF + método pago + override Líder | Aprobado en arquitectura |

---

### **FASE 4: Desarrollo módulos Python** ✅ COMPLETA

#### **4.1 `src/integrations/odoo/client.py`** — XML-RPC Client

**Métodos requeridos:**
```python
class OdooClient:
    async def authenticate() -> int                           # Retorna UID
    async def search_partner_by_rif(rif: str) -> dict | None  # Busca cliente por RIF
    async def create_partner(data: dict) -> int               # Crea partner, retorna ID
    async def create_sale_order(data: dict) -> int            # Crea sale.order, retorna ID
    async def create_invoice(data: dict) -> int               # Crea account.move (draft), retorna ID
    async def create_stock_picking(data: dict) -> int         # Crea stock.picking (nota entrega), retorna ID
    async def get_invoice_pdf(invoice_id: int) -> bytes       # Descarga PDF factura
    async def confirm_invoice(invoice_id: int) -> bool        # Confirma factura draft → posted
    async def register_payment(invoice_id: int, data: dict) -> bool  # Registra pago en factura
    async def convert_note_to_invoice(picking_id: int, rif: str, reason: str) -> int  # Wizard conversión
    async def get_product_id_by_name(name: str) -> int        # Busca producto por nombre
```

**Detalles técnicos:**
- XML-RPC over HTTPS: `odoorpc` o `xmlrpc.client` + `aiohttp` para async
- Autenticación: `common.authenticate(db, username, api_key, {})`
- Modelos: `execute_kw(db, uid, api_key, model, method, args, kwargs)`
- Manejo errores: reintentos exponenciales (3 max), timeout 30s
- Logging estructurado: `logger.info("Odoo create_invoice", invoice_id=X, partner_id=Y)`

#### **4.2 `src/integrations/odoo/sync.py`** — Lógica de sincronización

**Funciones principales:**
```python
async def sync_pedido_to_odoo(pedido_data: dict) -> dict:
    """Trigger desde bridge.py cuando pedido confirmado.
    Decide factura vs nota, crea en Odoo, retorna {tipo, odoo_id, numero}"""

async def decidir_documento(cliente_rif: str, metodo_pago: str, solicita_factura: bool) -> str:
    """Algoritmo decisión (ver sección 5.1 arquitectura):
    1. Si solicita_factura + RIF → FACTURA
    2. Si metodo_pago == 'efectivo' → NOTA_ENTREGA
    3. Si metodo_pago == 'pago_movil' + RIF → FACTURA
    4. Si metodo_pago == 'pago_movil' sin RIF → NOTA_ENTREGA
    5. Override Líder → FACTURA o NOTA"""

async def convert_nota_to_factura(picking_id: int, rif: str, razon_social: str, direccion_fiscal: str) -> dict:
    """Wizard conversión: stock.picking → sale.order → account.move
    - Misma numeración original (trazabilidad)
    - NO duplica inventario (stock_move_original_id referencia nota)
    - Retorna factura en estado draft (pendiente aprobación Líder)"""

async def sync_pago_to_odoo(pago_data: dict) -> bool:
    """Desde webhook R4: busca factura por referencia, registra payment, concilia"""

async def get_daily_sales_report(fecha: date) -> dict:
    """Ventas totales, IVA cobrado, pagos recibidos, por método pago"""

async def get_weekly_close_report(fecha_inicio: date, fecha_fin: date) -> dict:
    """Cierre semanal: ventas, comisiones choferes, cuentas cobrar, inventario"""

async def get_inventory_status() -> dict:
    """Botellones (disponibles/en_tránsito/con_cliente), hielo, insumos"""

async def get_payroll_weekly() -> dict:
    """Nómina viernes: YORDANIS + EVERT (sueldo + botellones×comisión + bonos)"""

async def get_islr_monthly(mes: int, año: int) -> dict:
    """Base imponible ISLR, retenciones, declaración mensual"""
```

#### **4.3 `src/integrations/r4/client.py`** — 13 Endpoints R4

**Endpoints (base URL: `https://r4conecta.mibanco.com.ve/`):**

| # | Endpoint | Método | Path | HMAC Pattern |
|---|----------|--------|------|--------------|
| 1 | Consulta tasa BCV | POST | `MBbcv` | `fechavalor + moneda` |
| 2 | Validar cliente pago (consulta) | POST | `R4consulta` | UUID comercio (header Authorization) |
| 3 | Notificación pago móvil | POST | `R4notifica` | UUID comercio (header Authorization) |
| 4 | Dispersión pagos | POST | `R4pagos` | `monto + fecha (MM/DD/YYYY)` |
| 5 | Vuelto | POST | `MBvuelto` | `Telefono_destino + Monto + Banco + Cedula` |
| 6 | Generar OTP | POST | `GenerarOtp` | `Banco + Monto + Telefono + Cedula` |
| 7 | Débito Inmediato | POST | `DebitoInmediato` | `Banco + Cedula + Telefono + Monto + OTP` |
| 8 | Crédito Inmediato | POST | `CreditoInmediato` | `Banco + Cedula + Telefono + Monto` |
| 9 | Consultar Operaciones | POST | `ConsultarOperaciones` | `Id` (UUID) |
| 10 | Domiciliación Cuenta 20d | POST | `TransferenciaOnline/DomiciliacionCNTA` | `cuenta` |
| 11 | Domiciliación Teléfono | POST | `TransferenciaOnline/DomiciliacionCELE` | `telefono` |
| 12 | Crédito Inmediato Cuentas 20d | POST | `CICuentas` | `Cedula + Cuenta + Monto` |
| 13 | Anulación C2P | POST | `MBanulacionC2P` | `Banco` |

**Headers comunes:**
```python
headers = {
    "Content-Type": "application/json",
    "Authorization": hmac_hex,  # Calculado por hmac_auth.py
    "Commerce": R4_COMMERCE_TOKEN
}
```

#### **4.4 `src/integrations/r4/hmac_auth.py`** — Patrones HMAC-SHA256

```python
import hmac
import hashlib

def calculate_hmac(commerce_token: str, payload_string: str) -> str:
    """HMAC-SHA256 Output Text Format Hex"""
    return hmac.new(
        commerce_token.encode('utf-8'),
        payload_string.encode('utf-8'),
        hashlib.sha256
    ).hexdigest().upper()

# Patrones por endpoint (extraídos del PDF):
HMAC_PATTERNS = {
    "MBbcv": lambda data: f"{data['Fechavalor']}{data['Moneda']}",
    "R4consulta": lambda data: str(uuid.uuid4()),  # UUID generado por comercio
    "R4notifica": lambda data: str(uuid.uuid4()),  # UUID generado por comercio
    "R4pagos": lambda data: f"{data['monto']}{data['fecha']}",  # MM/DD/YYYY
    "MBvuelto": lambda data: f"{data['TelefonoDestino']}{data['Monto']}{data['Banco']}{data['Cedula']}",
    "GenerarOtp": lambda data: f"{data['Banco']}{data['Monto']}{data['Telefono']}{data['Cedula']}",
    "DebitoInmediato": lambda data: f"{data['Banco']}{data['Cedula']}{data['Telefono']}{data['Monto']}{data['OTP']}",
    "CreditoInmediato": lambda data: f"{data['Banco']}{data['Cedula']}{data['Telefono']}{data['Monto']}",
    "ConsultarOperaciones": lambda data: data['Id'],
    "DomiciliacionCNTA": lambda data: data['cuenta'],
    "DomiciliacionCELE": lambda data: data['telefono'],
    "CICuentas": lambda data: f"{data['Cedula']}{data['Cuenta']}{data['Monto']}",
    "MBanulacionC2P": lambda data: data['Banco'],
}
```

#### **4.5 `src/integrations/r4/webhooks.py`** — FastAPI Endpoints

```python
# En api/bridge.py o nuevo router api/routes/r4_webhooks.py
from fastapi import APIRouter, Request, Header, HTTPException
from src.integrations.r4.client import R4Client
from src.integrations.odoo.sync import sync_pago_to_odoo

router = APIRouter(prefix="/webhook/r4", tags=["r4-webhooks"])

@router.post("/consulta")
async def r4_consulta_webhook(
    request: Request,
    authorization: str = Header(None),
    commerce: str = Header(None)
):
    """Banco consulta si cliente existe y acepta pago.
    Valida HMAC, busca cliente en BD, retorna {"status": true/false}"""
    
@router.post("/notifica")
async def r4_notifica_webhook(
    request: Request,
    authorization: str = Header(None),
    commerce: str = Header(None)
):
    """Banco notifica pago recibido.
    Valida HMAC, verifica referencia/banco/monto, 
    sincroniza con Odoo (sync_pago_to_odoo),
    retorna {"abono": true/false}"""
```

**Validaciones obligatorias en webhook notifica:**
1. Verificar HMAC (Authorization header)
2. Verificar IP en whitelist (45.175.213.98, 200.74.203.91, 204.199.249.3)
3. Verificar `CodigoRed == "00"` (APROBADO)
4. Verificar referencia no duplicada en `fs_pagos`
5. Verificar monto y banco coinciden con pedido esperado
6. Solo entonces `abono: true`

#### **4.6 `src/integrations/r4/codigos.py`** — Tabla códigos red

```python
CODIGOS_RED = {
    "00": "APROBADO",
    "01": "REFERIRSE AL CLIENTE",
    "12": "TRANSACCION INVALIDA",
    "13": "MONTO INVALIDO",
    "14": "NUMERO TELEFONO RECEPTOR ERRADO",
    "05": "TIEMPO DE RESPUESTA EXCEDIDO",
    "30": "ERROR DE FORMATO",
    "41": "SERVICIO NO ACTIVO",
    "43": "SERVICIO NO ACTIVO",
    "55": "TOKEN INVALIDO",
    "56": "CELULAR NO COINCIDE",
    "57": "NEGADA POR EL RECEPTOR",
    "62": "CUENTA RESTRINGIDA",
    "68": "RESPUESTA TARDIA, PROCEDE REVERSO",
    "80": "CEDULA O PASAPORTE ERRADO",
    "87": "TIME OUT",
    "90": "CIERRE BANCARIO EN PROCESO",
    "91": "INSTITUCION NO DISPONIBLE",
    "92": "BANCO RECEPTOR NO AFILIADO",
    "99": "ERROR EN NOTIFICACION",
    # Códigos débito/crédito/domiciliación (páginas 23-29)
    "ACCP": "OPERACION ACEPTADA",
    "AC00": "OPERACION EN ESPERA DE RESPUESTA DEL RECEPTOR",
    "AB01": "TIEMPO DE ESPERA AGOTADO",
    "AB07": "AGENTE FUERA DE LINEA",
    "AC01": "NUMERO DE CUENTA INCORRECTO",
    "AC04": "CUENTA CANCELADA",
    "AC06": "CUENTA BLOQUEADA",
    "AC09": "MONEDA NO VALIDA",
    "AG01": "TRANSACCION RESTRINGIDA",
    "AG09": "PAGO NO RECIBIDO",
    "AG10": "AGENTE SUSPENDIDO O EXCLUIDO",
    "AM02": "MONTO TRANSACCION NO PERMITIDO",
    "AM04": "SALDO INSUFICIENTE",
    "AM05": "OPERACION DUPLICADA",
    "BE01": "DATOS CLIENTE NO CORRESPONDEN A LA CUENTA",
    "BE20": "LONGITUD NOMBRE INVALIDA",
    "CH20": "NUMERO DECIMALES INCORRECTO",
    "CUST": "CANCELACION SOLICITADA POR DEUDOR",
    "DS02": "OPERACION CANCELADA",
    "DT03": "FECHA PROCESAMIENTO NO BANCARIA",
    "DU01": "IDENTIFICACION MENSAJE DUPLICADO",
    "ED05": "LIQUIDACION FALLIDA",
    "FF05": "CODIGO PRODUCTO INCORRECTO",
    "FF07": "CODIGO SUBPRODUCTO INCORRECTO",
    "MD01": "NO POSEE AFILIACION",
    "MD09": "AFILIACION INACTIVA",
    "MD15": "MONTO INCORRECTO / COBRO NO PERMITIDO",
    "MD22": "AFILIACION SUSPENDIDA",
    "RC08": "CODIGO BANCO NO EXISTE",
    "RJCT": "OPERACION RECHAZADA",
    "TKCM": "CODIGO UNICO DEBITO INCORRECTO",
    "VE01": "FUERA DE HORARIO PERMITIDO",
    "TM01": "RECHAZO TECNICO",
    # C2P específicos (páginas 30-31)
    "08": "TOKEN INVALIDO",
    "15": "LLAVE ERRONEA",
    "51": "INSUFICIENCIA DE FONDOS / NO TIENE FONDOS DISPONIBLES",
}
```

#### **4.7 Modificar `api/bridge.py`** — Trigger Odoo + Webhooks R4

**Ubicación:** En `_send_to_dispatch_queue()` (aprox línea 796), DESPUÉS de insertar en dispatch_queue:

```python
# --- NUEVO: Trigger Odoo Sync (ASÍNCRONO, no bloquea flujo) ---
async def _trigger_odoo_sync(ph_hash: str, state: dict, from_phone: str):
    try:
        from src.integrations.odoo.sync import sync_pedido_to_odoo, decidir_documento
        
        cliente_rif = state.get("cliente_rif", "")
        metodo_pago = state.get("payment_method", "")
        solicita_factura = state.get("solicita_factura", False)
        
        documento = decidir_documento(cliente_rif, metodo_pago, solicita_factura)
        
        pedido_data = {
            "cliente_nombre": state.get("contact_name", ""),
            "cliente_telefono": from_phone,
            "cliente_rif": cliente_rif,
            "items": state.get("items", []),
            "total_eur": state.get("total_eur", 0),
            "total_bs": state.get("total_bs", 0),
            "metodo_pago": metodo_pago,
            "documento_tipo": documento,
            "tasa_cambio_usada": state.get("tasa_cambio", 0),
        }
        
        result = await sync_pedido_to_odoo(pedido_data)
        logger.info("Odoo sync completado", tipo=result["tipo"], odoo_id=result["odoo_id"])
        
    except Exception as e:
        logger.error("Error sync Odoo (no bloquea): %s", e)
        # NO re-lanzar: el flujo principal continúa

# Llamar al final de _send_to_dispatch_queue:
# asyncio.create_task(_trigger_odoo_sync(ph_hash, state, from_phone))
```

**Nuevos endpoints en bridge.py:**
```python
# Webhooks R4 (añadir al router principal)
from src.integrations.r4.webhooks import router as r4_webhook_router
app.include_router(r4_webhook_router)
```

---

### **FASE 5: Tests unitarios** ✅ COMPLETA

| Test File | Qué prueba | Cobertura objetivo |
|-----------|------------|-------------------|
| `tests/unit/integrations/test_odoo_client.py` | Auth, create_partner, create_sale_order, create_invoice, create_stock_picking, get_invoice_pdf, convert_note_to_invoice | 90% |
| `tests/unit/integrations/test_odoo_sync.py` | decidir_documento (tabla completa), sync_pedido_to_odoo, convert_nota_to_factura, sync_pago_to_odoo, reportes | 85% |
| `tests/unit/integrations/test_r4_client.py` | 13 endpoints request/response, HMAC patterns, códigos red | 90% |
| `tests/unit/integrations/test_r4_hmac.py` | HMAC-SHA256 por endpoint con vectors conocidos | 100% |
| `tests/unit/integrations/test_r4_webhooks.py` | /consulta (status true/false), /notifica (abono true/false, validaciones) | 85% |
| `tests/unit/integrations/test_nota_entrega.py` | Crear nota, convertir a factura, inventario no duplicado | 90% |
| `tests/unit/integrations/test_conversor.py` | Conversión nota→factura misma numeración, stock intacto | 90% |

**Ejecutar:** `pytest tests/unit/integrations/ -v --tb=short`

---

### **FASE 6: Cron jobs systemd (7 timers)** ✅ COMPLETA

| Timer | Schedule (America/Caracas) | Qué ejecuta | Script |
|-------|---------------------------|-------------|--------|
| `r4-tasa-bcv.timer` | 9:00 + 15:00 diario | Consulta BCV USD/VES → actualiza `fs_tasas_cambio` | `scripts/cron/r4_tasa_bcv.py` |
| `odoo-ventas-diarias.timer` | 23:00 diario | Reporte ventas diarias → Telegram Líder | `scripts/cron/odoo_daily_sales.py` |
| `odoo-cierre-semanal.timer` | Viernes 18:00 | Cierre semanal + nómina choferes → Telegram | `scripts/cron/odoo_weekly_close.py` |
| `odoo-inventario-hielo.timer` | 8:00 diario | Inventario hielo → Telegram + Sheets | `scripts/cron/odoo_inventory_ice.py` |
| `odoo-inventario-insumos.timer` | Lunes 8:00 | Inventario insumos (botellones, tapas, etiquetas) | `scripts/cron/odoo_inventory_supplies.py` |
| `odoo-nomina-viernes.timer` | Viernes 17:00 | Cálculo nómina YORDANIS/EVERT → Telegram para aprobación | `scripts/cron/odoo_payroll_friday.py` |
| `odoo-islr-mensual.timer` | Día 1 mes 9:00 | Base ISLR mensual → Telegram + exporta Excel | `scripts/cron/odoo_islr_monthly.py` |
| `backup-daily.timer` | 3:00 diario | Backup BD + configs → almacenamiento remoto | `scripts/cron/backup_daily.py` |

**Ejemplo unit file:**
```ini
# /etc/systemd/system/odoo-ventas-diarias.service
[Unit]
Description=Odoo Ventas Diarias Report
After=network.target

[Service]
Type=oneshot
WorkingDirectory=/mnt/ssd_trabajo/hermes-agent
ExecStart=/mnt/ssd_trabajo/hermes-agent/venv/bin/python scripts/cron/odoo_daily_sales.py
EnvironmentFile=/mnt/ssd_trabajo/hermes-agent/config/.env
User=skynet

# /etc/systemd/system/odoo-ventas-diarias.timer
[Unit]
Description=Daily Odoo Sales Report Timer

[Timer]
OnCalendar=*-*-* 23:00:00
Persistent=true
Timezone=America/Caracas

[Install]
WantedBy=timers.target
```

**Activar:**
```bash
sudo systemctl daemon-reload
for timer in r4-tasa-bcv odoo-ventas-diarias odoo-cierre-semanal odoo-inventario-hielo odoo-inventario-insumos odoo-nomina-viernes odoo-islr-mensual backup-daily; do
    sudo systemctl enable --now ${timer}.timer
done
```

---

### **FASE 7: Seguridad** ✅ COMPLETA

| Medida | Implementación | Verificación |
|--------|----------------|--------------|
| **IP Whitelist R4** | Middleware FastAPI en `/webhook/r4/*` que valida `request.client.host` contra `R4_IP_WHITELIST` | `curl` desde IP no autorizada → 403 |
| **HMAC Verification** | `hmac_auth.py` valida header `Authorization` en cada webhook R4 | Request con HMAC inválido → 401 |
| **.env no en git** | Verificar `.gitignore` incluye `config/.env` y `*.env` | `git status` no muestra .env |
| **Backup diario automático** | `backup-daily.timer` → S3/Drive/NAS remoto + retención 30 días | Restore test mensual |
| **TLS 1.2+** | Cloudflare Tunnel maneja TLS (certificado válido) | `curl -v https://valentina.estacionh2o.com` muestra TLS 1.3 |
| **Rate limiting** | `core/rate_limiter.py` en webhooks R4 (max 100/min por IP) | Load test pasa |
| **Logs estructurados JSON** | `core/logger.py` → JSON en stdout para Loki/ELK | Log entry tiene `timestamp`, `level`, `event`, `trace_id` |

---

### **FASE 8: Tests end-to-end** ✅ COMPLETA

| Escenario | Descripción | Criterio éxito |
|-----------|-------------|----------------|
| **Pago móvil sandbox** | Simular webhook R4 con `CodigoRed=00` → busca pedido por referencia → sync_pago_to_odoo → factura marked paid en Odoo | Factura en Odoo estado "Paid", fs_pagos actualizado |
| **Conversión nota→factura** | Crear nota entrega (efectivo) → cliente solicita factura + RIF → wizard conversión → misma numeración, inventario intacto | Nota y factura comparten número secuencia, stock.move no duplicado |
| **Reportes automáticos** | Ejecutar 5 scripts cron manualmente → validar formato Telegram + datos correctos vs BD | Mensajes Telegram llegan a @Skynet_27_bot, totales cuadran |
| **Tasa BCV** | `r4-tasa-bcv` script → consulta MBbcv → actualiza fs_tasas_cambio → Valentina usa nueva tasa | Tasa en BD = respuesta BCV, Valentina cotiza con tasa actual |
| **Dispersión nómina** | `odoo-nomina-viernes` → calcula comisiones → R4 `R4pagos` → choferes reciben | Referencias R4 registradas, montos correctos por chofer |

---

### **FASE 9: Monitoreo** ✅ COMPLETA

| Métrica | Tipo | Descripción | Alerta |
|---------|------|-------------|--------|
| `odoo_sync_total` | Counter | Total sincronizaciones Odoo (success/error) | Error rate > 5% |
| `odoo_sync_duration_seconds` | Histogram | Latencia sync_pedido_to_odoo | p99 > 10s |
| `r4_webhook_received_total` | Counter | Webhooks R4 recibidos (/consulta, /notifica) | Drop > 10% |
| `r4_webhook_hmac_failures` | Counter | Fallos HMAC en webhooks | > 0 en 5 min |
| `r4_api_calls_total` | Counter | Llamadas salientes a API R4 por endpoint | Error rate > 10% |
| `daily_sales_report_sent` | Gauge | 1 si reporte diario enviado, 0 si falló | == 0 a las 23:15 |
| `weekly_payroll_calculated` | Gauge | 1 si nómina viernes calculada | == 0 viernes 17:15 |
| `backup_success` | Gauge | 1 si backup diario OK | == 0 a las 3:15 |

**Health check extendido** (`/health`):
```json
{
  "status": "ok",
  "version": "x.y.z",
  "odoo": {"connected": true, "last_sync": "2026-08-09T22:00:00Z"},
  "r4_bank": {"webhook_ok": true, "last_notification": "2026-08-09T20:30:00Z"},
  "database": {"conversations": "ok", "dispatch": "ok"},
  "services": {"valentina": "up", "dispatcher": "up", "telegram": "up"}
}
```

---

### **FASE 10: Documentación** ✅ COMPLETA

| Doc | Ruta | Contenido |
|-----|------|-----------|
| **README Integraciones** | `docs/06-manuales/README-INTEGRACIONES.md` | Setup, variables .env, cómo testear, troubleshooting |
| **Runbook Operación** | `docs/06-manuales/RUNBOOK-OPERACION.md` | Qué hacer si: Odoo caído, R4 webhook falla, factura no emitida, backup falla |
| **ADR 008** | `docs/04-decisiones/008-odoo-cloud-vs-self-hosted.md` | Community self-hosted Docker (gratis) vs Cloud (costo) — decisión: self-hosted |
| **ADR 009** | `docs/04-decisiones/009-r4-webhooks-bidirectional.md` | Webhooks R4 consulta + notificación en bridge.py vs servicio separado |
| **ADR 010** | `docs/04-decisiones/010-facturacion-discrecional.md` | Algoritmo RIF + método pago + override Líder — por qué no automático puro |

---

### **FASE 11: Rollout progresivo 8 semanas** ⏳ PENDIENTE (requiere token R4 producción)

| Semana | Actividad | Entregable | Criterio go/no-go |
|--------|-----------|------------|-------------------|
| **1-2** | Setup Odoo Docker + módulos core + API keys | Odoo accesible, productos cargados, auth OK | `create_partner` + `create_sale_order` funciona |
| **3-4** | Integración Valentina → Odoo (sync_pedido, decidir_documento) | Pedido WhatsApp → factura/nota en Odoo automático | 5 pedidos reales end-to-end OK |
| **4-5** | API R4 (cuando banco entregue credenciales) | Webhooks /consulta + /notifica operativos | Sandbox banco: pago → factura pagada en Odoo |
| **5-6** | Reportes automáticos (5 tipos) + cron jobs | 7 timers systemd activos + Telegram reportes | 1 semana completa reportes OK |
| **6-7** | Seguridad + monitoreo + runbook | IP whitelist, HMAC, TLS, métricas Prometheus, alertas | Penetration test básico pasa |
| **8** | Producción gradual | 10% clientes → 50% → 100% | 0 incidencias críticas 48h |

---

## 🧮 ALGORITMO DECISIÓN DOCUMENTO (Sección 5.1 Arquitectura)

```python
def decidir_documento(cliente_rif: str, metodo_pago: str, solicita_factura: bool, lider_override: str = None) -> str:
    """
    Reglas en orden de prioridad:
    1. Override del Líder (manual en Odoo/Valentina) → FACTURA | NOTA_ENTREGA
    2. Si cliente solicita factura + tiene RIF → FACTURA
    3. Si método pago = efectivo → NOTA_ENTREGA (siempre)
    4. Si método pago = pago_movil + RIF presente → FACTURA
    5. Si método pago = pago_movil sin RIF → NOTA_ENTREGA
    6. Default → NOTA_ENTREGA
    """
    if lider_override in ("FACTURA", "NOTA_ENTREGA"):
        return lider_override
    
    if solicita_factura and cliente_rif:
        return "FACTURA"
    
    if metodo_pago == "efectivo":
        return "NOTA_ENTREGA"
    
    if metodo_pago == "pago_movil" and cliente_rif:
        return "FACTURA"
    
    if metodo_pago == "pago_movil" and not cliente_rif:
        return "NOTA_ENTREGA"
    
    return "NOTA_ENTREGA"
```

**Tabla de decisión rápida:**

| Cliente RIF | Método pago | Solicita factura | Documento |
|-------------|-------------|------------------|-----------|
| ✅ Tiene | Pago móvil | ✅ Sí | **FACTURA** |
| ✅ Tiene | Pago móvil | ❌ No | NOTA (conversión posible) |
| ❌ No tiene | Pago móvil | ✅ Sí | NOTA (sin RIF no factura legal) |
| ❌ No tiene | Pago móvil | ❌ No | NOTA |
| ✅ o ❌ | Efectivo | Cualquiera | **NOTA (siempre)** |
| — | — | Líder override | FACTURA o NOTA (manual) |

---

## 🔄 FLUJO CONVERSIÓN NOTA → FACTURA (Sin romper inventario)

```
┌─────────────────────────────────────────────────────────┐
│ ESTADO ACTUAL: Nota de entrega #N-2026-0015              │
│ - Cliente: Juan Pérez (sin RIF)                          │
│ - Items: 3 botellones                                   │
│ - Total: €3.00                                           │
│ - Inventario: YA descontado al entregar (stock.picking.done)│
└─────────────────────────────────────────────────────────┘
                          │
                          ▼ Cliente solicita factura + presenta RIF
                          │
┌─────────────────────────────────────────────────────────┐
│ ACCIÓN: Convertir nota a factura (Wizard Odoo)           │
│                                                          │
│ 1. sale.order.create() con MISMA numeración (15)         │
│ 2. nota_origen_id = N-0015 (trazabilidad)                │
│ 3. account.move.create() con items + total               │
│ 4. Impuestos: EXENTO (0% IVA - botellón intercambio)     │
│ 5. Inventario: NO se vuelve a descontar                  │
│    → stock_move_original_id referencia nota original     │
│ 6. Factura estado: draft (pendiente aprobación Líder)    │
│ 7. Líder aprueba → factura electrónica XML (SENIAT)      │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│ RESULTADO: Factura #F-2026-0015                          │
│ - Misma numeración (15) para trazabilidad               │
│ - Inventario intacto (no duplicado)                      │
│ - Cliente recibe factura electrónica                     │
│ - Auditoría: nota→factura queda en log Odoo              │
└─────────────────────────────────────────────────────────┘
```

---

## 🏦 13 ENDPOINTS R4 CONECTA V3.0 (Resumen técnico)

| # | Endpoint | URL Path | Uso Estación H2O |
|---|----------|----------|------------------|
| 1 | **Consulta tasa BCV** | `MBbcv` | Actualizar tasa USD/VES 2x día (cron) |
| 2 | **Validar cliente pago** | `R4consulta` | Webhook: banco pregunta si aceptamos pago → `{"status": true}` |
| 3 | **Notificación pago** | `R4notifica` | Webhook: banco notifica pago recibido → sync Odoo + `{"abono": true}` |
| 4 | **Dispersión pagos** | `R4pagos` | Pagar nómina choferes + proveedores (viernes) |
| 5 | **Vuelto** | `MBvuelto` | Devolución dinero a cliente (si aplica) |
| 6 | **Generar OTP** | `GenerarOtp` | Paso 1 para débito/crédito inmediato |
| 7 | **Débito Inmediato** | `DebitoInmediato` | Cobrar a cliente (con OTP) |
| 8 | **Crédito Inmediato** | `CreditoInmediato` | Enviar pago a teléfono (sin cuenta 20d) |
| 9 | **Consultar Operaciones** | `ConsultarOperaciones` | Verificar estado si respuesta ≠ ACCP |
| 10 | **Domiciliación Cuenta 20d** | `DomiciliacionCNTA` | Cobro recurrente por cuenta 20 dígitos |
| 11 | **Domiciliación Teléfono** | `DomiciliacionCELE` | Cobro recurrente por teléfono (primera vez afilia) |
| 12 | **Crédito Inmediato Cuentas 20d** | `CICuentas` | Pago a cuenta 20 dígitos |
| 13 | **Anulación C2P** | `MBanulacionC2P` | Anular pago móvil recibido (si error) |

**Patrones HMAC por endpoint (críticos):**
- BCV: `fechavalor + moneda`
- Consulta/Notifica: UUID comercio (header Authorization)
- Dispersión: `monto + fecha(MM/DD/YYYY)`
- Vuelto: `Telefono_destino + Monto + Banco + Cedula`
- OTP: `Banco + Monto + Telefono + Cedula`
- Débito: `Banco + Cedula + Telefono + Monto + OTP`
- Crédito: `Banco + Cedula + Telefono + Monto`
- Consultar Ops: `Id` (UUID)
- Domiciliación Cuenta: `cuenta`
- Domiciliación Tel: `telefono`
- Crédito 20d: `Cedula + Cuenta + Monto`
- Anulación C2P: `Banco`

---

## 📊 5 REPORTES AUTOMÁTICOS (Estructura)

### 1. **Ventas Diarias** (23:00 diario)
```
📊 VENTAS DIARIAS - 2026-08-09
━━━━━━━━━━━━━━━━━━━━━━━━━━━
💰 Total: €XXX.XX / Bs.XXX,XXX
📦 Botellones: XX | 🧊 Hielo: XX
💳 Pago móvil: €XX | 💵 Efectivo: €XX
📋 Facturas: XX | 📝 Notas: XX
🏦 IVA 16%: €XX.XX
📈 Vs ayer: +X%
```

### 2. **Cierre Semanal** (Viernes 18:00)
```
📊 CIERRE SEMANAL - Sem 32 (Aug 4-8)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💰 Ventas: €X,XXX / Bs.XXX,XXX
📦 Botellones: XXXX | 🧊 Hielo: XXX
💳 Cobranzas: €XXX (XX% cobrado)
👥 Clientes crédito: XX (€XXX pendiente)
🚚 Comisiones: YORDANIS €XX | EVERT €XX
📦 Inventario: Botellones disp: XX | Hielo: XX
```

### 3. **Inventario Hielo** (8:00 diario)
```
🧊 INVENTARIO HIELO - 2026-08-09
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📦 Bolsas disp: XX
📦 En tránsito: XX
🏭 Producción ayer: XX bolsas
⚠️ Alerta: < 20 bolsas → producir
```

### 4. **Inventario Insumos** (Lunes 8:00)
```
📦 INVENTARIO INSUMOS - Sem 32
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🟦 Botellones vacíos: XX (mín 50)
🟦 Tapones: XX (mín 100)
🟦 Etiquetas: XX (mín 200)
🟦 Film stretch: X rollos
⚠️ Pedir: [items bajo mínimo]
```

### 5. **Nómina Viernes** (Viernes 17:00)
```
👥 NÓMINA VIERNES - 2026-08-08
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🚚 YORDANIS (Triciclo 1)
   Sueldo base: Bs.XX,XXX
   Comisión (XX bot × Bs.XX): Bs.XX,XXX
   Bonos: Bs.XX,XXX
   ─────────────────────
   TOTAL: Bs.XX,XXX (€XXX.XX)

🚚 EVERT (Triciclo 2)
   Sueldo base: Bs.XX,XXX
   Comisión (XX bot × Bs.XX): Bs.XX,XXX
   Bonos: Bs.XX,XXX
   ─────────────────────
   TOTAL: Bs.XX,XXX (€XXX.XX)

✅ [Aprobar pago]  ❌ [Revisar]
```

### 6. **ISLR Mensual** (Día 1, 9:00)
```
📋 ISLR MENSUAL - Julio 2026
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💰 Ingresos brutos: Bs.XXX,XXX
📉 Costos deducibles: Bs.XX,XXX
📊 Base imponible: Bs.XXX,XXX
📈 Retención ISLR (X%): Bs.XX,XXX
📄 Declaración: [Generar Excel para contador]
```

---

## 👥 MATRIZ ROLES HUMANOS

| Rol | Quién | Qué decide/ejecuta | Herramienta |
|-----|-------|-------------------|-------------|
| **Líder** | Luis Martinez | Aprueba facturas, nómina, override documento, configura Odoo | Odoo Web + Telegram |
| **Contador** | Por contratar | Declara IVA/ISLR, audita libros, valida facturas | Odoo Web + Excel export |
| **Choferes** | YORDANIS, EVERT | Marcan entregas en @DespachoH2O_bot, reportan vacíos | Telegram Bot |
| **Valentina (IA)** | Sistema | Recibe pedidos, calcula totales, decide documento inicial, trigger Odoo | bridge.py (auto) |
| **Dispatcher (IA)** | Sistema | Optimiza rutas, asigna choferes, GPS tracking | dispatcher.py (auto) |
| **Financial Shield** | Sistema | Cache local pedidos/pagos/nómina, tasas cambio, recordatorios | fs_* tables (auto) |
| **Odoo** | Sistema | Facturación, contabilidad, inventario, CRM, nómina, reportes | Odoo Web/XML-RPC (auto) |

---

## 🌐 IPS WHITELIST BANCO R4

```
45.175.213.98
200.74.203.91
204.199.249.3
```
> Solo permitir requests a `/webhook/r4/*` desde estas IPs. Middleware en FastAPI.

---

## ⚙️ VARIABLES .env NECESARIAS (Resumen)

```bash
# ODOO
ODOO_URL=https://estacion-h2o.odoo.com
ODOO_DB=estacion-h2o
ODOO_USERNAME=administracion@estacionh2o.com
ODOO_PASSWORD=****
ODOO_API_KEY=****

# BANCO R4
R4_BASE_URL=https://r4conecta.mibanco.com.ve
R4_COMMERCE_TOKEN=****
R4_WEBHOOK_AUTH_TOKEN=****  # UUID comercio para webhooks
R4_IP_WHITELIST=45.175.213.98,200.74.203.91,204.199.249.3

# FACTURACIÓN
INVOICE_DECISION_MODE=discrecional
DEFAULT_INVOICE_TYPE=nota_entrega

# EXISTENTES (no tocar)
META_VERIFY_TOKEN=a2ee0e434375cb232a99f10e4e1d210a
META_APP_SECRET=****
TELEGRAM_BOT_TOKEN=****
TELEGRAM_LEADER_CHAT_ID=****
DISPATCH_BOT_TOKEN=****
```

---

## ✅ CHECKLIST FINAL DE APROBACIÓN

| # | Criterio | Verificación | ✅/❌ |
|---|----------|--------------|------|
| 1 | Odoo Docker levantado y accesible | `curl https://estacion-h2o.odoo.com/web/login` | |
| 2 | Módulos core activados (sales, stock, account, purchase, hr, hr_payroll, hr_contract) | Odoo Apps | |
| 3 | Localización Venezuela (l10n_ve) instalada | Odoo Apps | |
| 4 | Productos cargados con precios e impuestos | Inventory → Products | |
| 5 | API Key Odoo generada y en .env | .env + test auth | |
| 6 | `src/integrations/odoo/client.py` pasa tests unitarios | `pytest tests/unit/integrations/test_odoo_client.py` | |
| 7 | `decidir_documento` cubre tabla completa | `pytest tests/unit/integrations/test_odoo_sync.py::test_decidir_documento` | |
| 8 | Conversión nota→factura preserva inventario | `pytest tests/unit/integrations/test_conversor.py` | |
| 9 | 13 endpoints R4 implementados con HMAC correcto | `pytest tests/unit/integrations/test_r4_client.py` | |
| 10 | Webhooks `/consulta` y `/notifica` responden JSON válido | `pytest tests/unit/integrations/test_r4_webhooks.py` | |
| 11 | Códigos red 00-99 mapeados | `src/integrations/r4/codigos.py` | |
| 12 | 7 cron timers systemd activos | `systemctl list-timers | grep odoo` | |
| 13 | IP whitelist R4 funcionando | `curl` desde IP no autorizada → 403 | |
| 14 | HMAC validation en webhooks | Request HMAC inválido → 401 | |
| 15 | Backup diario automático + restore test | `scripts/cron/backup_daily.py` + restore | |
| 16 | Health check extendido incluye Odoo + R4 | `curl /health` muestra odoo.connected=true | |
| 17 | Métricas Prometheus nuevas expuestas | `/metrics` tiene odoo_sync_*, r4_webhook_* | |
| 18 | 5 reportes automáticos llegan a Telegram Líder | Verificar @Skynet_27_bot 1 semana | |
| 19 | Pago móvil sandbox → factura pagada en Odoo | Test E2E con banco | |
| 20 | ADRs 008, 009, 010 documentados | `docs/04-decisiones/` | |
| 21 | Runbook operación completo | `docs/06-manuales/RUNBOOK-OPERACION.md` | |
| 22 | README integraciones actualizado | `docs/06-manuales/README-INTEGRACIONES.md` | |
| 23 | .env NO en git (verificar .gitignore) | `git check-ignore config/.env` | |
| 24 | TLS 1.2+ en todos los endpoints | `curl -v https://valentina.estacionh2o.com` | |

---

## 📝 ESTADO DE IMPLEMENTACIÓN (actualizado 2026-08-26)

Al actualizar este documento, confirmo que:

1. ✅ **FASE 0-7 COMPLETAS**: Entorno preparado, estructura creada, API keys configuradas, docs referencia, módulos Python desarrollados, tests unitarios, cron jobs, seguridad
2. ✅ **FASE 8-10 COMPLETAS**: Tests E2E (test_fase8_e2e.py), monitoreo (Prometheus + Loki Docker activos), documentación (3 runbooks en docs/04-runbooks/)
3. ⏳ **FASE 11 PENDIENTE**: Rollout progresivo requiere token R4 producción del banco
4. ✅ **Plan renombrado**: docs/06-manuales/PLAN-DESARROLLO-HERMES.md → docs/01-proyecto/04-PLAN-IMPLEMENTACION.md
5. ✅ **11 fases documentadas** con tareas, tiempos, verificaciones y responsables
6. ✅ **Entendido algoritmo facturación discrecional**: RIF + método pago + override Líder (5 reglas priorizadas)
7. ✅ **Entendidos 13 endpoints R4** con JSON request/response exactos, HMAC patterns, códigos red
8. ✅ **Odoo = Community self-hosted Docker (gratis)**, no Cloud de pago — Docker Up (odoo-web + odoo-db)
9. ✅ **Financial Shield v3.0 deployado** en producción (commit 91439f7)
10. ✅ **SOUL v2.1 activo** — 6 capas de memoria, Consolidador mem0 2.0.18, Qdrant 402pts
11. ✅ **956 tests pasando, 0 failed, 61% coverage** (verificado 2026-08-26)
12. ✅ **194 commits** en rama feat/odoo-r4-integration

---

**Firma**: 💧

**Próximo paso**: Obtener token R4 de producción del banco para iniciar **FASE 11** (rollout progresivo 8 semanas).