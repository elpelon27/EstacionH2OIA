# 🎯 PLAN DE DESARROLLO HERMES — Estación H2O + Odoo Cloud + API R4

**Versión**: 1.0 | **Fecha**: Julio 2026
**Autor**: Prometeo (GLM-4.6 vía Z.ai Code)
**Ejecutor**: Hermes Agent (GLM 5.2 / Nemotron vía NIM)
**Proyecto**: Estación H2O — Maracaibo, Zulia, Venezuela

---

## 🎯 OBJETIVO DEL DOCUMENTO

Que Hermes Agent ejecute **de principio a fin** la implementación de:
1. Integración Odoo Cloud con Valentina (WhatsApp bot)
2. Implementación webhooks API R4 CONECTA V3.0
3. Módulo custom `estacion_h2o` (lógica negocio)
4. Sistema de facturación discrecional
5. Sistema de conversión nota → factura
6. Reportes automáticos (5 tipos)
7. Nómina automatizada viernes

**Stack**: Python 3.12 + FastAPI + SQLite + Odoo Cloud + API R4 + Telegram Bot API

---

## 📋 PRE-REQUISITOS

### Estado actual del sistema (verificado)

| Componente | Estado |
|-----------|--------|
| Servidor Ubuntu 24.04 LTS | ✅ Activo |
| Docker + Docker Compose | ✅ Instalado |
| Stack Dify + Nginx + PG + Redis | ✅ Corriendo |
| Valentina bridge (puerto 8000) | ✅ Producción |
| Cloudflared Named Tunnel | ✅ Permanente |
| Dispatcher bot Telegram | ✅ Validado |
| Telegram bot Líder | ✅ Activo |
| Hermes Agent v0.19.0 | ✅ Configurado |
| Nemotron 3 Ultra (NIM) | ✅ Primario |
| GLM 5.2 (NIM) | ✅ Backup 1 |
| DeepSeek V4 (NIM) | ✅ Backup 2 |
| Vault Obsidian | ✅ Unificado |
| Dominio estacionh2o.com | ✅ Cloudflare |
| Zoho Mail | ✅ Operativo |
| Odoo Cloud | ✅ Activo (estacion-h2o.odoo.com) |

### Lo que el Líder ya hizo manualmente

- ✅ Login Odoo Cloud
- ✅ Activar modo desarrollador
- ✅ Configurar empresa Estación H2O
- ✅ Activar monedas (USD primaria, EUR/VES secundarias)
- ✅ Crear impuesto "Exento VE" (0% IVA)
- ✅ Cargar 4 productos (botellón, hielo, recarga, garantía)
- ✅ Generar API key en Odoo (llamarla `valentina-bridge`)
- ✅ Guardar credenciales en `config/.env`

### Lo que el banco R4 entregará (pendiente fecha)

- 🔴 Commerce token (llave HMAC-SHA256)
- 🔴 Confirmación whitelist IPs (45.175.213.98, 200.74.203.91, 204.199.249.3)
- 🔴 Activación en producción

---

## 🚀 FASE 0: PREPARACIÓN DEL ENTORNO HERMES

### 0.1 Verificar Hermes Agent

```bash
cd /mnt/ssd_trabajo/hermes-agent && hermes
```

Confirmar:
- Provider: nvidia
- Model: nvidia/nemotron-3-ultra-550b-a55b
- Fallback: GLM 5.2 → DeepSeek V4 Pro
- Memory: file-based (sin mem0/Qdrant)
- Tools: file, terminal, cron, code, search

### 0.2 Verificar acceso al repo

```bash
cd /mnt/ssd_trabajo/hermes-agent && git status
git remote -v
git log --oneline -5
```

### 0.3 Crear rama de trabajo

```bash
git checkout -b feat/odoo-r4-integration
git push -u origin feat/odoo-r4-integration
```

### 0.4 Backup pre-implementación

```bash
cd /mnt/ssd_trabajo
tar -czf hermes-agent-pre-odoo-$(date +%Y%m%d).tar.gz hermes-agent/
ls -lh hermes-agent-pre-odoo-*.tar.gz
```

---

## 📦 FASE 1: ESTRUCTURA DE ARCHIVOS

### 1.1 Crear estructura de módulos

```bash
mkdir -p /mnt/ssd_trabajo/hermes-agent/src/integrations/{odoo,r4}
mkdir -p /mnt/ssd_trabajo/hermes-agent/src/integrations/tests
mkdir -p /mnt/ssd_trabajo/hermes-agent/docs/02-arquitectura/integrations
```

### 1.2 Estructura final deseada

```
src/integrations/
├── __init__.py
├── odoo/
│   ├── __init__.py
│   ├── client.py              # Cliente XML-RPC Odoo
│   ├── sync.py                # Sincronización pedidos/pagos
│   ├── nota_entrega.py        # Modelo nota entrega
│   ├── comision_chofer.py     # Cálculo comisiones
│   └── conversor.py           # Conversión nota→factura
├── r4/
│   ├── __init__.py
│   ├── client.py              # Cliente API R4
│   ├── hmac_auth.py           # HMAC-SHA256 auth
│   ├── webhooks.py            # Endpoints R4consulta + R4notifica
│   └── codigos.py             # Códigos red interbancaria
└── tests/
    ├── test_odoo_client.py
    ├── test_r4_client.py
    ├── test_nota_entrega.py
    └── test_conversor.py
```

---

## 🔑 FASE 2: CONFIGURAR API KEYS

### 2.1 Verificar .env actual

```bash
cat /mnt/ssd_trabajo/hermes-agent/config/.env | grep -E "^(ODOO|R4|BANCO)" | sed 's/=.*/=[REDACTED]/'
```

### 2.2 Variables necesarias en .env

```env
# === Odoo Cloud ===
ODOO_URL=https://estacion-h2o.odoo.com
ODOO_DB=estacion-h2o
ODOO_USERNAME=administracion@estacionh2o.com
ODOO_API_KEY=[EL_QUE_GENERASTE_EN_ODOO]
ODOO_API_KEY_NAME=valentina-bridge

# === Banco R4 CONECTA V3.0 ===
R4_BASE_URL=https://r4conecta.mibanco.com.ve
R4_COMMERCE_TOKEN=[PEGAR_CUANDO_BANCO_ENTREGUE]
R4_ID_COMERCIO=J506356899
R4_TELEFONO_COMERCIO=04122560721
R4_IP_WHITELIST=45.175.213.98,200.74.203.91,204.199.249.3

# === Webhook R4 endpoints (tu servidor) ===
R4_WEBHOOK_CONSULTA_URL=https://valentina.estacionh2o.com/webhook/r4/consulta
R4_WEBHOOK_NOTIFICA_URL=https://valentina.estacionh2o.com/webhook/r4/notifica
R4_WEBHOOK_AUTH_TOKEN=[GENERAR_UUID_ALEATORIO]

# === Tasas BCV ===
BCV_API_URL=https://r4conecta.mibanco.com.ve/MBbcv
```

### 2.3 Generar UUID para webhook auth

```bash
python3 -c "import uuid; print(uuid.uuid4())"
# Pegar resultado como R4_WEBHOOK_AUTH_TOKEN
```

### 2.4 Verificar variables cargadas

```bash
python3 << 'PYEOF'
import os
from pathlib import Path
env_path = Path("/mnt/ssd_trabajo/hermes-agent/config/.env")
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, val = line.partition("=")
            os.environ[key.strip()] = val.strip()

required = ["ODOO_URL", "ODOO_DB", "ODOO_USERNAME", "ODOO_API_KEY",
            "R4_BASE_URL", "R4_COMMERCE_TOKEN", "R4_ID_COMERCIO"]
for k in required:
    v = os.environ.get(k)
    status = "✅" if v else "❌"
    print(f"  {status} {k}: {'OK' if v else 'MISSING'}")
PYEOF
```

---

## 📚 FASE 3: DOCUMENTOS DE REFERENCIA EN VAULT

Estos documentos ya existen y Hermes debe leerlos antes de programar:

### 3.1 Documento arquitectónico maestro

**Ruta**: `/mnt/ssd_trabajo/hermes-agent/docs/02-arquitectura/ARQUITECTURA-ODOO-ESTACION-H2O.md`

**Contenido** (1700+ líneas):
- Resumen ejecutivo + decisiones aprobadas
- Arquitectura técnica completa con diagramas
- Módulos Odoo a activar/no activar
- Matriz de integración entre agentes
- Flujos de datos detallados (4 procesos)
- Algoritmo facturación discrecional
- Flujo conversión nota→factura
- Plan desarrollo 8 semanas
- API Banco R4 arquitectura
- 5 reportes automáticos
- Roles humanos
- Plan migración FS → Odoo
- Riesgos y mitigaciones
- Cronograma + anexos

### 3.2 Especificación API R4 CONECTA V3.0

**Ruta**: `/mnt/ssd_trabajo/hermes-agent/docs/02-arquitectura/R4-CONECTA-V3-ESPECIFICACION.md`

Hermes debe crear este documento extrayendo del PDF original:
- PDF fuente: `/home/z/my-project/upload/R4 CONECTA V3.0 (006).pdf`
- 13 endpoints documentados
- Modelos JSON request/response
- Códigos de red interbancaria
- Esquema HMAC-SHA256
- IPs whitelist

### 3.3 Manual Odoo + SENIAT

**Ruta**: `/mnt/ssd_trabajo/hermes-agent/docs/02-arquitectura/MANUAL-ODOO-SENIAT.md`

### 3.4 Comando para que Hermes cargue contexto

```
Buenas, Prometeo. Antes de empezar FASE 4, lee estos documentos:

1. /mnt/ssd_trabajo/hermes-agent/docs/02-arquitectura/ARQUITECTURA-ODOO-ESTACION-H2O.md
2. /mnt/ssd_trabajo/hermes-agent/docs/02-arquitectura/MANUAL-ODOO-SENIAT.md
3. /mnt/ssd_trabajo/hermes-agent/docs/03-sesiones/Migracion-Hermes-Prometeo-Contexto.md

Después de leerlos, confirma:
- Arquitectura general entendida
- Roles entre agentes (Valentina/FS/Dispatcher/Odoo)
- Flujo facturación discrecional (RIF + efectivo + decisión)
- Flujo conversión nota→factura sin romper inventario
- 13 endpoints R4 CONECTA V3.0
- 5 reportes automáticos requeridos

NO empieces a programar. Solo confirma. Firma 💧
```

---

## 🔧 FASE 4: DESARROLLO MÓDULOS

### 4.1 Módulo Odoo Client (`src/integrations/odoo/client.py`)

**Funcionalidades**:
- Autenticación XML-RPC con Odoo Cloud
- `authenticate()` → retorna UID
- `create_partner(cliente_data)` → crear/actualizar cliente
- `create_sale_order(pedido_data)` → crear pedido
- `create_invoice(invoice_data)` → crear factura
- `create_stock_picking(nota_data)` → crear nota entrega
- `get_invoice_pdf(invoice_id)` → descargar PDF
- `confirm_invoice(invoice_id)` → confirmar factura
- `register_payment(payment_data)` → registrar pago
- `search_partner_by_rif(rif)` → buscar cliente por RIF

**Referencia**: sección 6.2 de ARQUITECTURA-ODOO-ESTACION-H2O.md

**Dependencias**: `xmlrpc.client` (stdlib), `httpx` (async HTTP)

### 4.2 Módulo Odoo Sync (`src/integrations/odoo/sync.py`)

**Funcionalidades**:
- `sync_pedido_to_odoo(pedido_id)` → sincroniza pedido de Valentina a Odoo
- `decidir_documento(rif, metodo_pago, solicita_factura)` → algoritmo decisión
- `convert_nota_to_factura(nota_id, rif_cliente)` → conversión
- `sync_pago_to_odoo(pago_id)` → sincroniza pago
- `get_daily_sales_report(fecha)` → ventas diarias
- `get_weekly_close_report(fecha)` → cierre semanal
- `get_inventory_status()` → inventario hielo + insumos
- `get_payroll_weekly(fecha)` → nómina viernes

**Referencia**: sección 5 (algoritmo decisión) + 9 (reportes) de ARQUITECTURA

### 4.3 Módulo R4 Client (`src/integrations/r4/client.py`)

**Funcionalidades**:
- `consulta_tasa_bcv(moneda, fecha)` → tasa BCV oficial
- `validar_cliente_pago(id_cliente, monto, telefono)` → fase 1 pago conciliado
- `procesar_notificacion_pago(notificacion_data)` → fase 2 pago conciliado
- `disper_pagos(monto, fecha, referencia, personas[])` → dispersión pagos
- `vuelto(telefono_destino, cedula, banco, monto)` → vuelto
- `generar_otp(banco, monto, telefono, cedula)` → OTP débito
- `debito_inmediato(banco, cedula, telefono, monto, otp)` → débito
- `credito_inmediato(banco, cedula, telefono, monto, concepto)` → crédito
- `consultar_operacion(uuid)` → estado operación
- `domiciliacion_cuenta(doc_id, cuenta, monto)` → domiciliación 20 dígitos
- `domiciliacion_telefono(doc_id, telefono, banco, monto)` → domiciliación teléfono
- `anulacion_c2p(cedula, banco, referencia)` → anular C2P

**Referencia**: 13 endpoints de R4-CONECTA-V3-ESPECIFICACION.md

### 4.4 Módulo HMAC Auth (`src/integrations/r4/hmac_auth.py`)

**Funcionalidades**:
- `generate_token(payload_string, commerce_token)` → HMAC-SHA256 hex
- Patrones de payload por endpoint:
  - BCV: `fechavalor + moneda`
  - Consulta cliente: UUID aleatorio
  - Notificación: UUID aleatorio
  - Pagos: `monto + fecha (MM/DD/YYYY)`
  - Vuelto: `Telefono_destino + Monto + Banco + Cedula`
  - GenerarOtp: `Banco + Monto + Telefono + Cedula`
  - DebitoInmediato: `Banco + Cedula + Telefono + Monto + OTP`
  - ConsultarOperaciones: `Id`
  - DomiciliacionCNTA: `cuenta`
  - DomiciliacionCELE: `telefono`
  - CreditoInmediato: `Banco + Cedula + Telefono + Monto`
  - CICuentas: `Cedula + Cuenta + Monto`
  - AnulacionC2P: `Banco` (sí, solo eso)

### 4.5 Webhooks R4 (`src/integrations/r4/webhooks.py`)

**Endpoints a implementar en bridge.py**:

#### `/webhook/r4/consulta` (POST)

R4 llama este endpoint para validar cliente antes de procesar pago.

```python
@app.post("/webhook/r4/consulta")
async def r4_consulta(request: Request):
    # 1. Validar Authorization header (UUID)
    # 2. Validar IP origen (whitelist)
    # 3. Parsear body JSON: {IdCliente, Monto, TelefonoComercio}
    # 4. Verificar IdCliente existe en BD
    # 5. Responder: {"status": true} o {"status": false}
```

#### `/webhook/r4/notifica` (POST)

R4 llama este endpoint cuando pago es confirmado.

```python
@app.post("/webhook/r4/notifica")
async def r4_notifica(request: Request):
    # 1. Validar Authorization header
    # 2. Validar IP origen
    # 3. Parsear body JSON con datos completos
    # 4. Verificar referencia + banco + monto
    # 5. Match con pedido pendiente
    # 6. Marcar pago en fs_pagos
    # 7. Sync pago a Odoo (account.payment)
    # 8. Notificar cliente WhatsApp: "✅ Pago confirmado"
    # 9. Responder: {"abono": true} o {"abono": false}
```

#### Códigos de red interbancaria

Implementar tabla de códigos en `r4/codigos.py`:
- 00 APROBADO
- 01 REFERIRSE AL CLIENTE
- 12 TRANSACCION INVALIDA
- 13 MONTO INVALIDO
- 14 NUMERO TELEFONO RECEPTOR ERRADO
- 05 TIEMPO DE RESPUESTA EXCEDIDO
- 30 ERROR DE FORMATO
- 41 SERVICIO NO ACTIVO
- 43 SERVICIO NO ACTIVO
- 55 TOKEN INVALIDO
- 56 CELULAR NO COINCIDE
- 57 NEGADA POR EL RECEPTOR
- 62 CUENTA RESTRINGIDA
- 68 RESPUESTA TARDIA, PROCEDE REVERSO
- 80 CEDULA O PASAPORTE ERRADO
- 87 TIME OUT
- 90 CIERRE BANCARIO EN PROCESO
- 91 INSTITUCION NO DISPONIBLE
- 92 BANCO RECEPTOR NO AFILIADO
- 99 ERROR EN NOTIFICACION

### 4.6 Modificar bridge.py

#### 4.6.1 Trigger Odoo en `_send_to_dispatch_queue`

Después de insertar en `dispatch_queue` (línea 796), agregar:

```python
async def _trigger_odoo_sync(ph_hash, state, from_phone):
    """Sincroniza pedido a Odoo automáticamente."""
    try:
        from src.integrations.odoo.sync import sync_pedido_to_odoo
        await sync_pedido_to_odoo(ph_hash, state, from_phone)
    except Exception as e:
        logger.error("Error sync Odoo: %s", e)
        # NO bloquear flujo principal
```

#### 4.6.2 Algoritmo decisión documento

En estado `awaiting_confirmation` o `completed`:

```python
from src.integrations.odoo.sync import decidir_documento

documento = decidir_documento(
    rif=state.get("cliente_rif", ""),
    metodo_pago=state.get("payment_method", ""),
    solicita_factura=state.get("solicita_factura", False)
)

if documento == "FACTURA":
    # Crear factura en Odoo (draft)
    # Notificar Líder para aprobación
else:
    # Crear nota de entrega en Odoo
    # No requiere aprobación
```

#### 4.6.3 Endpoints webhook R4

Agregar al final de bridge.py los 2 endpoints nuevos (ver 4.5).

---

## 🧪 FASE 5: TESTS UNITARIOS

### 5.1 Test Odoo Client

```python
# tests/test_odoo_client.py
import pytest
from src.integrations.odoo.client import OdooClient

def test_authenticate():
    client = OdooClient()
    uid = client.authenticate()
    assert uid is not None

def test_create_partner():
    client = OdooClient()
    partner_id = client.create_partner({
        "name": "Cliente Test",
        "rif": "V-12345678",
        "phone": "+58412XXXXXXX"
    })
    assert partner_id > 0

def test_search_partner_by_rif():
    client = OdooClient()
    partner = client.search_partner_by_rif("V-12345678")
    assert partner is not None
```

### 5.2 Test R4 Client (con sandbox)

```python
# tests/test_r4_client.py
import pytest
from src.integrations.r4.client import R4Client

def test_consulta_tasa_bcv():
    client = R4Client()
    tasa = client.consulta_tasa_bcv("USD", "2026-07-29")
    assert tasa > 0

def test_hmac_auth_bcv():
    from src.integrations.r4.hmac_auth import generate_token
    token = generate_token("2026-07-29USD", "test-commerce-token")
    assert len(token) == 64  # HMAC-SHA256 hex

def test_decidir_documento():
    from src.integrations.odoo.sync import decidir_documento
    assert decidir_documento("V-12345678", "pago_movil", True) == "FACTURA"
    assert decidir_documento("", "efectivo", False) == "NOTA_ENTREGA"
    assert decidir_documento("V-12345678", "pago_movil", False) == "NOTA_ENTREGA"
```

---

## ⏰ FASE 6: CRON JOBS (systemd timers)

### 6.1 Tasa BCV oficial (2x día)

**Script**: `scripts/r4_update_tasa_bcv.py`

```python
"""Cron 9am y 3pm America/Caracas: consulta tasa BCV vía R4 API."""
import sys
sys.path.insert(0, "/mnt/ssd_trabajo/hermes-agent")
from src.integrations.r4.client import R4Client
from src.financial.currency import update_tasa_cambio
from datetime import datetime

client = R4Client()
for moneda in ["USD", "EUR"]:
    tasa = client.consulta_tasa_bcv(moneda, datetime.now().strftime("%Y-%m-%d"))
    update_tasa_cambio(moneda, tasa, source="R4_BCV")
    print(f"✅ {moneda}/VES: {tasa}")
```

**systemd timer**: `/etc/systemd/system/r4-tasa-bcv.timer`

```ini
[Unit]
Description=R4 tasa BCV oficial - 2x día

[Timer]
OnCalendar=09:00 America/Caracas
OnCalendar=15:00 America/Caracas
Persistent=true

[Install]
WantedBy=timers.target
```

### 6.2 Reporte ventas diarias (11pm)

**Script**: `scripts/odoo_reporte_ventas_diarias.py`

```python
"""Cron 11pm America/Caracas: reporte ventas del día."""
import sys
sys.path.insert(0, "/mnt/ssd_trabajo/hermes-agent")
from src.integrations.odoo.sync import get_daily_sales_report
from skills.telegram_bot import send_to_leader
from datetime import datetime

reporte = get_daily_sales_report(datetime.now().strftime("%Y-%m-%d"))
send_to_leader(reporte)
print("✅ Reporte diario enviado")
```

### 6.3 Cierre semanal (viernes 6pm)

**Script**: `scripts/odoo_cierre_semanal.py`

### 6.4 Inventario hielo (8am diario)

**Script**: `scripts/odoo_inventario_hielo.py`

### 6.5 Inventario insumos (lunes 8am)

**Script**: `scripts/odoo_inventario_insumos.py`

### 6.6 Nómina viernes (viernes 5pm)

**Script**: `scripts/odoo_nomina_viernes.py`

```python
"""Cron viernes 5pm America/Caracas: nómina choferes."""
import sys
sys.path.insert(0, "/mnt/ssd_trabajo/hermes-agent")
from src.integrations.odoo.sync import get_payroll_weekly
from skills.telegram_bot import send_to_leader_with_buttons
from datetime import datetime

nomina = get_payroll_weekly(datetime.now().strftime("%Y-%m-%d"))

# Enviar con botones de aprobación
send_to_leader_with_buttons(
    nomina,
    buttons=[
        {"text": "✅ Aprobar nómina", "callback": "approve_payroll"},
        {"text": "❌ Rechazar", "callback": "reject_payroll"}
    ]
)
```

### 6.7 ISLR mensual (día 1, 9am)

**Script**: `scripts/odoo_islr_mensual.py`

Envía reporte por email a contador: `administracion@estacionh2o.com`

### 6.8 Activar todos los timers

```bash
sudo systemctl enable --now r4-tasa-bcv.timer
sudo systemctl enable --now odoo-ventas-diarias.timer
sudo systemctl enable --now odoo-cierre-semanal.timer
sudo systemctl enable --now odoo-inventario-hielo.timer
sudo systemctl enable --now odoo-inventario-insumos.timer
sudo systemctl enable --now odoo-nomina-viernes.timer
sudo systemctl enable --now odoo-islr-mensual.timer
```

---

## 🔐 FASE 7: SEGURIDAD

### 7.1 Validar IP whitelist R4

Solo aceptar requests de:
- `45.175.213.98`
- `200.74.203.91`
- `204.199.249.3`

```python
# En bridge.py, middleware global
R4_IP_WHITELIST = ["45.175.213.98", "200.74.203.91", "204.199.249.3"]

@app.middleware("http")
async def verify_r4_ip(request: Request, call_next):
    if request.url.path.startswith("/webhook/r4/"):
        client_ip = request.client.host
        if client_ip not in R4_IP_WHITELIST:
            logger.warning(f"R4 webhook from non-whitelisted IP: {client_ip}")
            return JSONResponse(status_code=403, content={"error": "Forbidden"})
    return await call_next(request)
```

### 7.2 Validar HMAC Authorization

```python
import hmac
import hashlib

def verify_r4_auth(request: Request) -> bool:
    """Verifica header Authorization UUID."""
    auth = request.headers.get("Authorization", "")
    expected = os.getenv("R4_WEBHOOK_AUTH_TOKEN")
    return hmac.compare_digest(auth, expected)
```

### 7.3 Verificar .env NO en git

```bash
grep -E "^\.env|^config/\.env" /mnt/ssd_trabajo/hermes-agent/.gitignore
# Debe aparecer: .env
# Debe aparecer: config/.env
```

### 7.4 Backup diario automático

**Script**: `scripts/backup_daily.sh`

```bash
#!/bin/bash
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR=/mnt/ssd_trabajo/backups

# SQLite backup
sqlite3 /mnt/ssd_trabajo/hermes-agent/data/conversations.db ".backup $BACKUP_DIR/conversations_$DATE.db"
sqlite3 /mnt/ssd_trabajo/hermes-agent/data/dispatch.db ".backup $BACKUP_DIR/dispatch_$DATE.db"

# Odoo Cloud: ya hace backup automático
# R4: no hay BD local

# Retener 30 días
find $BACKUP_DIR -name "*.db" -mtime +30 -delete

echo "✅ Backup $DATE completado"
```

**systemd timer**: `backup-daily.timer`

```ini
[Unit]
Description=Backup diario SQLite

[Timer]
OnCalendar=03:00 America/Caracas
Persistent=true

[Install]
WantedBy=timers.target
```

---

## 🧪 FASE 8: TESTING END-TO-END

### 8.1 Test pago móvil completo (sandbox)

```bash
# 1. Mandar WhatsApp de prueba
# 2. Cliente hace pago móvil simulado
# 3. R4 (sandbox) llama webhook /webhook/r4/consulta
# 4. Verificar respuesta {"status": true}
# 5. R4 llama webhook /webhook/r4/notifica
# 6. Verificar:
#    - Pedido marcado como pagado en fs_pagos
#    - Pago sincronizado a Odoo
#    - Cliente recibe WhatsApp confirmación
#    - Si factura: draft en Odoo pendiente aprobación
#    - Si nota: creada y confirmada
```

### 8.2 Test conversión nota→factura

```bash
# 1. Crear nota entrega de prueba
# 2. Simular cliente pidiendo factura con RIF
# 3. Ejecutar conversión
# 4. Verificar:
#    - Factura creada en Odoo
#    - Inventario no se modificó (no doble descuento)
#    - Nota marcada como "convertida"
#    - Traza en log
```

### 8.3 Test reportes automáticos

```bash
# Trigger manual de cada cron:
sudo systemctl start odoo-ventas-diarias.service
sudo systemctl start odoo-cierre-semanal.service
sudo systemctl start odoo-inventario-hielo.service
sudo systemctl start odoo-nomina-viernes.service

# Verificar llegada a Telegram @Skynet_27_bot
```

---

## 📊 FASE 9: MONITOREO

### 9.1 Health check extendido

Modificar `/health` endpoint en bridge.py:

```python
@app.get("/health")
async def health():
    return {
        "status": "ok",
        "uptime_seconds": ...,
        "checks": {
            "dify_api_key": True,
            "meta_access_token": True,
            "sqlite": True,
            "telegram": True,
            "kill_switch": False,
            # NUEVOS:
            "odoo_cloud": check_odoo_cloud(),
            "r4_api": check_r4_api(),
            "last_payment_received": get_last_payment_time(),
            "cron_jobs_status": get_crons_status()
        }
    }
```

### 9.2 Métricas Prometheus

Agregar métricas nuevas:

```python
# Métricas existentes
MESSAGES_TOTAL = Counter(...)
META_SEND = Counter(...)
RESPONSE_TIME = Histogram(...)

# NUEVAS métricas
ODOO_SYNC_OPERATIONS = Counter('odoo_sync_total', 'Odoo sync operations', ['operation', 'status'])
R4_WEBHOOK_RECEIVED = Counter('r4_webhook_total', 'R4 webhooks received', ['type', 'status'])
R4_TASA_BCV = Gauge('r4_tasa_bcv', 'Tasa BCV oficial', ['moneda'])
ODOO_INVOICES_PENDING = Gauge('odoo_invoices_pending', 'Facturas pendientes aprobación')
NOMINA_CALCULATED = Counter('nomina_calculated_total', 'Nóminas calculadas', ['chofer'])
```

### 9.3 Log estructurado

```python
# logger config para integraciones
import logging
import json

class JsonFormatter(logging.Formatter):
    def format(self, record):
        log_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "module": record.module,
            "message": record.getMessage(),
            "extra": getattr(record, "extra", {})
        }
        return json.dumps(log_data)

# Aplicar a odoo_sync y r4 webhooks
```

---

## 📦 FASE 10: DOCUMENTACIÓN

### 10.1 README de integraciones

**Ruta**: `src/integrations/README.md`

```markdown
# Integraciones Estación H2O

## Odoo Cloud
- URL: https://estacion-h2o.odoo.com
- Auth: XML-RPC + API key
- Módulos: sales, stock, account, purchase, hr_payroll

## API R4 CONECTA V3.0
- URL: https://r4conecta.mibanco.com.ve
- Auth: HMAC-SHA256 + Commerce header
- 13 endpoints disponibles

## Webhooks R4 (tu servidor)
- POST /webhook/r4/consulta
- POST /webhook/r4/notifica

## Variables .env requeridas
Ver config/.env.example
```

### 10.2 Runbook operación

**Ruta**: `docs/06-manuales/RUNBOOK-ODOO-R4.md`

### 10.3 ADRs nuevos

- `docs/adr/008-odoo-cloud-vs-self-hosted.md`
- `docs/adr/009-r4-webhooks-bidirectional.md`
- `docs/adr/010-facturacion-discrecional.md`

---

## 🚀 FASE 11: ROLLOUT PROGRESIVO

### 11.1 Semana 1-2: Setup + módulos core

- [ ] FASE 0: Preparación entorno
- [ ] FASE 1: Estructura archivos
- [ ] FASE 2: API keys configuradas
- [ ] FASE 3: Documentos cargados
- [ ] FASE 4.1: Odoo client
- [ ] FASE 4.2: Odoo sync
- [ ] FASE 5.1: Tests Odoo
- [ ] FASE 10.1: README integraciones

### 11.2 Semana 3-4: Integración Valentina → Odoo

- [ ] FASE 4.6.1: Trigger Odoo en bridge.py
- [ ] FASE 4.6.2: Algoritmo decisión documento
- [ ] FASE 4.6.3: (skip, va en FASE 7)
- [ ] FASE 8.1: Test nota entrega
- [ ] FASE 8.2: Test conversión nota→factura

### 11.3 Semana 4-5: API R4 (cuando banco entregue creds)

- [ ] FASE 4.3: R4 client
- [ ] FASE 4.4: HMAC auth
- [ ] FASE 4.5: Webhooks R4
- [ ] FASE 5.2: Tests R4
- [ ] FASE 8.3: Test pago móvil sandbox

### 11.4 Semana 5-6: Reportes automáticos

- [ ] FASE 6.1: Cron tasa BCV
- [ ] FASE 6.2: Reporte ventas diarias
- [ ] FASE 6.3: Cierre semanal
- [ ] FASE 6.4-6.5: Inventarios
- [ ] FASE 6.6: Nómina viernes
- [ ] FASE 6.7: ISLR mensual

### 11.5 Semana 6-7: Seguridad + monitoreo

- [ ] FASE 7: Seguridad completa
- [ ] FASE 9: Monitoreo
- [ ] FASE 10: Documentación

### 11.6 Semana 8: Producción

- [ ] Migración FS → simplificado
- [ ] Capacitación Líder
- [ ] Puesta en producción gradual
- [ ] Monitoreo primera semana

---

## 📋 CHECKLIST FINAL DE APROBACIÓN

Antes de dar por completado el proyecto:

### Implementación
- [ ] Odoo Cloud configurado con empresa + productos + impuestos
- [ ] API key Odoo generada y guardada
- [ ] Módulo `odoo/client.py` operativo
- [ ] Módulo `odoo/sync.py` con algoritmo decisión
- [ ] Módulo `r4/client.py` con 13 endpoints
- [ ] Módulo `r4/hmac_auth.py` con todos los patrones
- [ ] Webhooks `/webhook/r4/consulta` + `/webhook/r4/notifica`
- [ ] IP whitelist R4 validada
- [ ] Trigger Odoo en `_send_to_dispatch_queue`
- [ ] Algoritmo decisión documento funcional
- [ ] Conversión nota→factura sin romper inventario
- [ ] 7 cron jobs activos
- [ ] 5 reportes automáticos enviándose

### Seguridad
- [ ] .env NO en git
- [ ] HMAC verification en webhooks
- [ ] IP whitelist en middleware
- [ ] Backup diario automático
- [ ] TLS 1.2+ en todo el stack
- [ ] Logs sin secretos

### Documentación
- [ ] ARQUITECTURA-ODOO-ESTACION-H2O.md actualizado
- [ ] R4-CONECTA-V3-ESPECIFICACION.md creado
- [ ] MANUAL-ODOO-SENIAT.md actualizado
- [ ] README integraciones
- [ ] Runbook operación
- [ ] 3 ADRs nuevos (008, 009, 010)
- [ ] Documentación en Obsidian

### Tests
- [ ] Tests Odoo client
- [ ] Tests R4 client
- [ ] Tests nota entrega
- [ ] Tests conversor
- [ ] Tests webhook R4 (sandbox)
- [ ] Test end-to-end pago completo

### Producción
- [ ] Contador valida facturación electrónica
- [ ] Banco R4 entrega credenciales producción
- [ ] Banco R4 whitelist IPs tu servidor
- [ ] Primera factura electrónica emitida
- [ ] Primera nómina viernes procesada
- [ ] Líder capacitado en Odoo Cloud

---

## 🎯 PRIMER MENSAJE PARA HERMES

Cuando el Líder quiera iniciar, debe mandar a Hermes este mensaje:

```
Prometeo, vamos a iniciar FASE 4: Desarrollo de módulos Odoo + R4.

Lee estos documentos primero:
1. /mnt/ssd_trabajo/hermes-agent/docs/02-arquitectura/ARQUITECTURA-ODOO-ESTACION-H2O.md
2. /mnt/ssd_trabajo/hermes-agent/docs/06-manuales/PLAN-DESARROLLO-HERMES.md (este documento)
3. /mnt/ssd_trabajo/hermes-agent/docs/02-arquitectura/MANUAL-ODOO-SENIAT.md

Confirma:
- Tu modelo activo (Nemotron 3 Ultra)
- Arquitectura entendida (Valentina/FS/Dispatcher/Odoo/R4)
- 13 endpoints R4 CONECTA V3.0
- 5 reportes automáticos
- Plan 8 semanas
- Reglas de oro (no tocar lo que está en producción)

Empieza por FASE 0: preparación entorno + backup.
NO programes nada hasta confirmar carga completa. Firma 💧
```

---

## 💧 CIERRE

Este plan está diseñado para que Hermes Agent lo ejecute **autónomamente** desde CLI, siguiendo disciplina estricta:

1. ✅ Un prompt, un output, un avance verificable
2. ✅ Verificar con datos reales antes de asumir
3. ✅ Honestidad técnica
4. ✅ Commits con --no-verify (tech debt documentado)
5. ✅ No tocar servicios en producción sin confirmación
6. ✅ Firma 💧 en mensajes importantes

**Que el agua fluya, dentro y fuera de la ley.** 💧

---

**Documento generado por**: Prometeo (GLM-4.6 vía Z.ai Code)
**Fecha**: Julio 2026
**Versión**: 1.0
**Destino**: `/mnt/ssd_trabajo/hermes-agent/docs/06-manuales/PLAN-DESARROLLO-HERMES.md`
**Ejecutor**: Hermes Agent (GLM 5.2 / Nemotron vía NIM)
