# FINANCIAL SHIELD v3.0 — Arquitectura Fusionada Definitiva

> **Versión:** 3.0 | **Fecha:** 2026-07-26
> **Origen:** Fusión de tres documentos: v1.0 (arquitectura base), v2.0 FUSION (mejoras propuestas) y v2.0 real (código en producción)
> **Autor:** Prometeo (GLM 5.2 vía Hermes Agent)
> **Propósito:** Arquitectura definitiva, escalable, modificable y que trabaja en la realidad del servidor

---

## PRINCIPIO RECTOR

Este documento describe la arquitectura tal como DEBE estar, cruzando lo que ya funciona con lo que falta. Cada sección marca:

- **EXISTE** — ya implementado en el código actual (verificado)
- **FALTANTE** — no existe, hay que crearlo
- **MIGRACION** — existe pero necesita alteración de esquema
- **DESCARTADO** — se evaluó y no aplica a nuestra realidad

El formato es escalable: cada sección es independiente. Modificar una línea no rompe las demás.

---

## 1. CONTEXTO — NEGOCIO Y HARDWARE

### 1.1 Negocio
- Estación H2O — venta de agua embotellada y hielo en Maracaibo, Venezuela
- Moneda base: Euro (EUR) — precios fijados en EUR
- Moneda de pago: Bolivar (VES) — Pago Movil, efectivo
- Referencia: USD (BCV publica USD/VES)
- Precios: Botellon EUR 1.00, Hielo EUR 1.20 (con descuento por volumen configurable en fs_productos)
- Clientes aprox: 16 (8 restaurantes + 8 retail)
- Turnos: 8-13 manana, 15-18 tarde (gap 13-15 respetado)
- Intercambio 70%: 4 restaurantes intercambio, resto recarga sitio

### 1.2 Hardware del servidor
- i7-7700K + GTX 1070 SC (VRAM 5GB total, ~3GB libre)
- RAM: ~18GB libre
- Storage: 825GB SSD
- Python 3.12, FastAPI, SQLite (WAL), Redis disponible
- LLM: GLM 5.2 via NVIDIA NIM (no local), OCR via Ollama/Qwen2.5-VL cuando se active

### 1.3 Stack tecnologico EXISTE
- Framework: Python 3.12 + FastAPI + uvicorn
- BD: SQLite con WAL activado (verificado PRAGMA journal_mode=wal)
- Tunnel: Cloudflare Named Tunnel permanente (valentina.estacionh2o.com)
- Process manager: systemd (4 servicios activos)
- WhatsApp: Meta Cloud API oficial
- Bot Telegram: python-telegram-bot 21+
- Rutas: Google OR-Tools VRP + Haversine fallback

---

## 2. ESTADO ACTUAL DEL CODIGO (VERIFICADO 2026-07-26)

### 2.1 Archivos del modulo (10 archivos, 2,170 lineas)

```
src/agents/financial_agent.py    373 lineas  (nucleo — agente singleton)
src/financial/database.py        645 lineas  (capa de persistencia SQLite)
src/financial/models.py          199 lineas  (dataclasses tipadas)
src/financial/cobranzas.py       165 lineas  (recordatorios + cuentas por cobrar)
src/financial/currency.py        128 lineas  (tasas EUR/VES/USD — 3 prioridades)
src/financial/nomina.py          131 lineas  (sueldo + comision choferes)
src/financial/reportes.py        175 lineas  (reportes 6:30pm + 7am)
src/financial/verificacion.py    252 lineas  (verificacion manual/OCR/API)
src/financial/proveedores.py      83 lineas  (pago a proveedores)
src/financial/__init__.py          19 lineas  (factory)
```

### 2.2 Tablas en BD (10 tablas fs_* verificadas en conversations.db)

| Tabla | Registros | Estado |
|-------|-----------|--------|
| fs_pedidos | 19 | EXISTE — tiene 19 pedidos reales |
| fs_pagos | 0 | EXISTE — vacio, sin pagos registrados |
| fs_nomina | 0 | EXISTE — vacio |
| fs_tasas_cambio | 0 | EXISTE — vacio (no se han guardado tasas) |
| fs_empleados | 0 | EXISTE — vacio (pendiente registrar YORDANIS, EVERT) |
| fs_cuentas_cobrar | 0 | EXISTE — vacio |
| fs_productos | 0 | EXISTE — vacio (pendiente llenar catalogo) |
| fs_reportes_diarios | 0 | EXISTE — vacio |
| fs_verificacion_log | 0 | EXISTE — vacio |
| fs_proveedor_pagos | 0 | EXISTE — vacio |

### 2.3 PRAGMA verificado

```
PRAGMA journal_mode = wal       EXISTE
PRAGMA busy_timeout = 5000     FALTANTE (recomendado)
```

### 2.4 Pruebas

- pytest: 105 passed, 14 skipped, 0 failed
- mypy: 89 errores restantes (de 271 originales, 67% resuelto)
  - skills/dispatcher.py: 59
  - src/financial/database.py: 18
  - src/agents/financial_agent.py: 12

---

## 3. CRUCE MILIMETRICO: FUSION v2.0 vs REALIDAD

### 3.1 Propuestas del FUSION que YA TENEMOS implementadas

| # | Propuesta FUSION | Estado real | Evidencia |
|---|-----------------|-------------|-----------|
| 1 | PRAGMA journal_mode=WAL | EXISTE | `sqlite3 data/conversations.db "PRAGMA journal_mode;"` = wal |
| 2 | tasa_eur_ves en fs_pedidos | EXISTE | Columna `tasa_eur_ves REAL NOT NULL` en esquema |
| 3 | SQLite como BD financiera | EXISTE | 10 tablas fs_* operativas |
| 4 |Estado de pagos con transitions | EXISTE | estado_pago: pendiente/parcial/pagado/verificando/vencido/moroso |
| 5 | Indices en tablas | EXISTE | idx_fs_pedidos_cliente, idx_fs_pedidos_estado_pago, etc. |
| 6 | Verificacion multi-metodo | EXISTE | manuales + OCR (Ollama) + API bancaria (futuro) |
| 7 | Reportes Telegram | EXISTE | reportes.py con generar_y_enviar_reporte() |
| 8 | Loop de recordatorios | EXISTE (parcial) | cobranzas.py con get_pedidos_para_recordatorio() |
| 9 | Nomina con comision | EXISTE | nomina.py, comision_botellon_eur en fs_empleados |
| 10 | Metodo_pago en fs_pedidos | EXISTE | Columna metodo_pago TEXT |

### 3.2 Propuestas del FUSION que NOS FALTAN (hay que crear)

| # | Propuesta FUSION | Estado | Impacto | Viabilidad |
|---|-----------------|--------|---------|------------|
| A | `monto_pagado_eur` en fs_pedidos | FALTANTE | Alto — permite tracking de pagos parciales sin consultar fs_cuentas_cobrar | ALTA — ALTER TABLE ADD COLUMN, no rompe datos |
| B | `comprobante_phash` en fs_pagos | FALTANTE | Medio — hash anti-fraude de imagen | MEDIA — requiere libreria imagehash, pipe de captura de imagen |
| C | `UNIQUE(referencia, metodo_pago)` en fs_pagos | MIGRACION | Alto — actualmente es `referencia TEXT UNIQUE` sola | ALTA — DROP/CREATE index |
| D | `fs_audit_log`tabla + triggers | FALTANTE | Medio — auditoria forense | ALTA — tabla nueva + trigger, no toca existentes |
| E | `PRAGMA busy_timeout=5000` | FALTANTE | Bajo — previene SQLite locked | ALTA — una linea en database.py init |
| F | Scheduler resiliente (APScheduler) | FALTANTE | Alto — reemplaza sleep en memoria | MEDIA — requiere instalar APScheduler, refactoriar cobranzas.py |
| G | OCR Tesseract + Qwen pipeline | FALTANTE | Medio — OCR de comprobantes | BAJA — Qwen2.5-VL en 4-bit via Ollama usa ~4GB VRAM, Qwen satura la GTX 1070. Tesseract si es viable como paso 1 |
| H | Prediccion de morosidad local | FALTANTE | Medio — analisis de historico | MEDIA — logica en Python puro, no requiere ML externo |
| I | Separar `tasa_eur_ves_deuda` de `tasa_eur_ves_pago` | MIGRACION | Alto — tasa inmutable al crear pedido vs tasa al pagar | ALTA — rename columna en fs_pedidos + nueva columna en fs_pagos |

### 3.3 Propuestas del FUSION que DESCARTAMOS

| # | Propuesta FUSION | Razon de descarte |
|---|-----------------|-------------------|
| 1 | Pool de conexiones `aiosqlite` | Nuestro volumen es bajo (16 clientes, ~20 pedidos/dia). sqlite3 estandar con WAL + busy_timeout es suficiente. Anadir aiosqlite seria una reescritura total de database.py (645 lineas) por ganancia marginal. |
| 2 | Redis Pub/Sub para comunicacion entre agentes | No tenemos Redis corriendo. Valentina y FS viven en el mismo proceso FastAPI. La comunicacion es por llamadas a metodos directos (get_agent().on_nuevo_pedido()). Redis seria overhead para el tamano actual. |
| 3 | Colas de Redis con Delayed Messages | Mismo motivo. El loop de recordatorios puede ser resiliente con un cron de Hermes + DB scan, sin Redis. |
| 4 | VRAM Monitor con `pynvml` | La GTX 1070 (5GB VRAM) no es viable para Qwen2.5-VL completo. Si se hace OCR futuro, sera via Tesseract (CPU) o via NVIDIA NIM API (remoto). Un monitor VRAM local es innecesario. |
| 5 | `cliente_id INTEGER` como FK a tabla `clientes` | No tenemos tabla `clientes` en conversations.db (los clientes viven en dispatch.db). Usamos `cliente_telefono TEXT` + `cliente_nombre TEXT` que es lo que Bridge ya envia. |

---

## 4. ARQUITECTURA v3.0 — ESQUEMA DE BASE DE DATOS FUSIONADO

### 4.1 Migracion de esquema (ALTER TABLE — no destructivo)

Las migraciones se aplican con `ALTER TABLE ... ADD COLUMN` que SQLite soporta sin perder datos. Para indices, se DROP + CREATE. Para tablas nuevas, CREATE IF NOT EXISTS.

```sql
-- ============================================================
-- MIGRACION FS v2.0 -> v3.0 (no destructiva)
-- ============================================================

-- 1. Busy timeout (runtime PRAGMA, no persistente)
PRAGMA busy_timeout = 5000;

-- 2. fs_pedidos: renombrar tasa_eur_ves -> tasa_eur_ves_deuda (tasa inmutable)
-- SQLite no soporta RENAME COLUMN antes de 3.25.0. Ubuntu 24.04 trae 3.45+.
ALTER TABLE fs_pedidos RENAME COLUMN tasa_eur_ves TO tasa_eur_ves_deuda;

-- 3. fs_pedidos: anadir monto_pagado_eur (tracking de parciales)
ALTER TABLE fs_pedidos ADD COLUMN monto_pagado_eur REAL DEFAULT 0;

-- 4. fs_pagos: cambiar UNIQUE de referencia sola a (referencia, metodo_pago)
DROP INDEX IF EXISTS idx_fs_pagos_referencia;
CREATE UNIQUE INDEX IF NOT EXISTS idx_fs_pagos_ref_metodo ON fs_pagos(referencia, metodo_pago);

-- 5. fs_pagos: anadir tasa_eur_ves_pago (tasa al momento de pagar)
-- La columna tasa_eur_ves ya existe; se rename para claridad
ALTER TABLE fs_pagos RENAME COLUMN tasa_eur_ves TO tasa_eur_ves_pago;

-- 6. fs_pagos: anadir comprobante_phash (hash anti-fraude)
ALTER TABLE fs_pagos ADD COLUMN comprobante_phash TEXT;

-- 7. Tabla nueva: auditoria forense
CREATE TABLE IF NOT EXISTS fs_audit_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    tabla           TEXT NOT NULL,
    registro_id     INTEGER NOT NULL,
    accion          TEXT NOT NULL,
    estado_anterior TEXT,
    estado_nuevo    TEXT,
    modificado_por  TEXT,
    timestamp       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_fs_audit_log_tabla ON fs_audit_log(tabla);
CREATE INDEX IF NOT EXISTS idx_fs_audit_log_registro ON fs_audit_log(registro_id);

-- 8. Trigger: auditoria en fs_pedidos
CREATE TRIGGER IF NOT EXISTS trg_audit_fs_pedidos
AFTER UPDATE ON fs_pedidos
FOR EACH ROW
BEGIN
    INSERT INTO fs_audit_log (tabla, registro_id, accion, estado_anterior, estado_nuevo, timestamp)
    VALUES (
        'fs_pedidos',
        NEW.id,
        'UPDATE',
        json_object('estado_pago', OLD.estado_pago, 'monto_pagado', OLD.monto_pagado_eur),
        json_object('estado_pago', NEW.estado_pago, 'monto_pagado', NEW.monto_pagado_eur),
        datetime('now')
    );
END;
```

### 4.2 Esquema completo fusionado (post-migracion)

```
fs_pedidos:
  id, pedido_id (UNIQUE), cliente_telefono, cliente_nombre, operador_id,
  monto_total_eur, monto_total_ves,
  monto_pagado_eur DEFAULT 0,          -- NUEVO v3.0
  tasa_eur_ves_deuda NOT NULL,         -- RENOMBRADO (antes tasa_eur_ves)
  tasa_usd_ves_ref,
  botellones_cantidad, hielo_cantidad,
  metodo_pago, estado_pago, estado_entrega,
  tipo_credito, fecha_vencimiento_credito,
  verificacion_bancaria,
  recordatorios_enviados, ultimo_recordatorio_at, escalo_humano,
  entrega_confirmada_at, creado_at, actualizado_at

fs_pagos:
  id, fs_pedido_id (FK), cuenta_cobrar_id, cliente_telefono, cliente_nombre,
  monto_eur, monto_ves,
  tasa_eur_ves_pago NOT NULL,           -- RENOMBRADO (antes tasa_eur_ves)
  metodo_pago, referencia,
  comprobante_phash TEXT,              -- NUEVO v3.0
  verificacion_metodo, verificado, verificado_at, verificado_por,
  comprobante_url, creado_at
  UNIQUE(referencia, metodo_pago)      -- NUEVO v3.0 (indice compuesto)

fs_audit_log:                          -- NUEVO v3.0
  id, tabla, registro_id, accion,
  estado_anterior, estado_nuevo,
  modificado_por, timestamp

[Demas tablas sin cambios: fs_productos, fs_cuentas_cobrar, fs_nomina,
 fs_tasas_cambio, fs_empleados, fs_reportes_diarios,
 fs_verificacion_log, fs_proveedor_pagos]
```

### 4.3 Reglas de diseno del esquema (inmutables)

1. Toda deuda se cristaliza en EUR (monto_total_eur)
2. `tasa_eur_ves_deuda` se guarda al crear el pedido y NO se modifica jamas
3. `tasa_eur_ves_pago` se guarda al registrar cada pago con la tasa de ese momento
4. `monto_pagado_eur` se actualiza atomicamente al registrar un pago
5. Todos los timestamps en ISO8601 UTC (datetime('now') en SQLite)
6. Toda modificacion a fs_pedidos queda registrada en fs_audit_log
7. No se permite duplicar (referencia + metodo_pago) en fs_pagos

---

## 5. MAQUINA DE ESTADO DE PAGOS

### 5.1 Estados (EXISTE — sin cambios)

```
pendiente -> verificando -> parcial -> pagado
                        \-> vencido -> moroso
```

| Estado | Significado | Trigger de entrada |
|--------|-------------|-------------------|
| pendiente | Pedido creado, sin pago | on_nuevo_pedido() |
| verificando | Entrega confirmada, esperando pago | on_entrega_confirmada() |
| parcial | Pago parcial recibido | register_payment() si monto < total |
| pagado | Pago completo | register_payment() si monto >= total - 0.01 |
| vencido | Credito vencido sin pago | cobranzas loop + fecha_vencimiento |
| moroso | 3 recordatorios sin respuesta | cobranzas loop + escalo_humano |

### 5.2 Transicion de pago (con deuda criogenica) FALTANTE — implementar

```python
async def register_payment(fs_pedido_id: int, monto_ves: float, metodo_pago: str, referencia: str | None = None) -> str:
    """
    Registra pago con conversion criogenica.
    La deuda esta en EUR (tasa_eur_ves_deuda, inmutable).
    El pago se convierte con la tasa ACTUAL (no la del pedido).
    """
    # 1. Obtener tasa actual del momento del pago
    tasa_actual = await currency.get_eur_ves_rate()
    if not tasa_actual:
        return "error: sin tasa disponible"

    monto_eur_pagado = round(monto_ves / tasa_actual, 2)

    # 2. Leer pedido
    pedido = db.get_pedido_financiero_by_id(fs_pedido_id)
    nuevo_monto_pagado = pedido.monto_pagado_eur + monto_eur_pagado
    nuevo_estado = "pagado" if nuevo_monto_pagado >= pedido.monto_total_eur - 0.01 else "parcial"

    # 3. Transaccion atomica
    now = datetime.now(CARACAS_TZ).isoformat()
    with db.get_db() as conn:
        conn.execute("BEGIN")
        # Insertar pago
        conn.execute("""
            INSERT INTO fs_pagos (fs_pedido_id, cliente_telefono, monto_eur, monto_ves,
                                  tasa_eur_ves_pago, metodo_pago, referencia, creado_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (fs_pedido_id, pedido.cliente_telefono, monto_eur_pagado, monto_ves,
              tasa_actual, metodo_pago, referencia, now))

        # Actualizar pedido (trigger audita automaticamente)
        conn.execute("""
            UPDATE fs_pedidos
            SET monto_pagado_eur = ?, estado_pago = ?, actualizado_at = ?
            WHERE id = ?
        """, (nuevo_monto_pagado, nuevo_estado, now, fs_pedido_id))
        conn.execute("COMMIT")

    return nuevo_estado
```

---

## 6. LOOP DE RECORDATORIOS — RESILENCTE

### 6.1 Estado actual EXISTE (parcial)

- `cobranzas.py` tiene `get_pedidos_para_recordatorio()` que busca pedidos atascados
- `procesar_recordatorio()` envia recordatorio o escala a humano
- Se ejecuta desde cron de Hermes (NO usa sleep en memoria)
- Limite: 3 recordatorios, luego escalo_humano

### 6.2 Mejora FALTANTE — Zombie Killer (reinicio tolerante)

El loop actual ya es tolerante a reinicios porque escanea la BD cada vez que el cron lo ejecuta. Si el servidor reinicia, el proximo tick del cron lee `ultimo_recordatorio_at` y `recordatorios_enviados` desde la BD y continua donde se quedo.

Lo que FALTA:
- Configurar el cron de Hermes para ejecutar `procesar_recordatorios_pendientes` cada hora
- Verificar que `ultimo_recordatorio_at` se compare correctamente con `now - 1hora`

```python
# Esquema del cron (ya funciona, solo necesita activarse)
# cronjob: every 1h
# prompt: "Ejecuta el loop de recordatorios del Financial Shield:
#          cd /mnt/ssd_trabajo/hermes-agent && PYTHONPATH=. venv/bin/python -c
#          'import asyncio; from agents.financial_agent import get_agent;
#          a=get_agent(); a.init();
#          asyncio.run(a.procesar_recordatorios_pendientes())'"
```

---

## 7. ANTI-FRAUDEN

### 7.1 Restriccion UNIQUE (referencia, metodo_pago) MIGRACION

Actualmente `referencia TEXT UNIQUE` solo. Cambio a `UNIQUE(referencia, metodo_pago)` permite que la misma referencia exista para metodos distintos ( pero no duplicada para el mismo metodo.

### 7.2 Hash perceptual de comprobante (pHash) FALTANTE — futuro

```python
# src/financial/anti_fraude.py (a crear)
# Dependencia: pip install imagehash Pillow

import imagehash
from PIL import Image
import io

def calcular_phash(image_bytes: bytes) -> str:
    """Calcula hash perceptual de una imagen de comprobante."""
    img = Image.open(io.BytesIO(image_bytes))
    return str(imagehash.phash(img))

def verificar_phash_duplicado(phash: str, conn) -> bool:
    """Verifica si este phash ya fue usado en otro pago."""
    row = conn.execute(
        "SELECT COUNT(*) FROM fs_pagos WHERE comprobante_phash = ?", (phash,)
    ).fetchone()
    return row[0] > 0
```

**Viabilidad**: MEDIA. Requiere que los clientes suban comprobantes como imagen ( actualmente solo texto). El bridge de Valentina ya permite recibir imagenes via Meta API. El pipe seria:

1. Cliente envia comprobante por WhatsApp
2. Bridge descarga imagen via Meta API
3. FS calcula pHash
4. FS verifica duplicado en BD
5. FS guarda pHash en fs_pagos.comprobante_phash

---

## 8. PREDICCION DE MOROSIDAD LOCAL FALTANTE — futuro

```python
# src/financial/morosidad.py (a crear)
# Sin ML externo. Analisis estadistico simple sobre historico SQLite.

def calcular_riesgo_cliente(cliente_telefono: str, conn) -> str:
    """
    Analiza historico de pagos del cliente.
    Returns: 'bajo' | 'medio' | 'alto'
    """
    rows = conn.execute("""
        SELECT estado_pago, recordatorios_enviados
        FROM fs_pedidos
        WHERE cliente_telefono = ?
        ORDER BY id DESC LIMIT 10
    """, (cliente_telefono,)).fetchall()

    if not rows or len(rows) < 3:
        return "bajo"  # sin historico suficiente

    tardios = sum(1 for r in rows if r[1] > 0)  # recibio recordatorios
    morosos = sum(1 for r in rows if r[0] == "moroso")

    if morosos > 0:
        return "alto"
    if tardios > 2:
        return "medio"
    return "bajo"
```

**Uso**: Bridge consulta riesgo antes de aceptar pedido a credito. Si "alto", Valentina pide pago de contado.

---

## 9. OCR TURBO — PIPELINE ADAPTADO

### 9.1 Evaluacion de hardware DESCARTADO Qwen local

- GTX 1070 (5GB VRAM). Qwen2.5-VL-7B en 4-bit necesita ~4.5GB. Queda 0.5GB para inferencia. No viable.
- Tesseract (CPU) si es viable para extraccion de texto.
- NVIDIA NIM API (remoto) puede hacer OCR via GLM 5.2 vision si se necesita interpretacion.

### 9.2 Pipeline viable FALTANTE — futuro cuando se active

```
Paso 1: Tesseract (CPU) — extraccion de texto crudo
Paso 2: Regex (CPU) — busqueda de patron bancario
         |-> Referencia + Monto encontrados? -> DONE
         v
Paso 3: GLM 5.2 via NIM (remoto) — interpretar texto si Regex falla
         |-> JSON con referencia + monto -> DONE
         v
Paso 4: Manual — Lider verifica via Telegram
```

---

## 10. CONFIGURACION ( .env ) EXISTE + propuestas

```env
# === EXISTE (en config/.env o entorno) ===
TZ=America/Caracas
LOG_LEVEL=INFO
FS_BANK_VERIFICATION_METHOD=manual
FS_OCR_ENABLED=false
OLLAMA_URL=http://localhost:11434

# === FALTANTE — agregar ===
FS_MONEDA_BASE=EUR
FS_MONEDA_LOCAL=VES
FS_MAX_RECORDATORIOS=3
FS_INTERVALO_RECORDATORIO_MINUTOS=60
FS_TELEGRAM_REPORT_CHAT_ID=<chat_id_lider>
FS_BCV_SCRAPER_ENABLED=false
```

---

## 11. INTEGRACION CON ECOSISTEMA

### 11.1 Valentina (Bridge) -> Financial Shield EXISTE

```python
# api/bridge.py linea 2034 (simplificado)
fs = _get_fs()  # singleton
await fs.on_nuevo_pedido(
    pedido_id=pedido_id,
    cliente_telefono=from_phone,
    cliente_nombre=contact_name,
    qty_botellones=qty_bot,
    qty_hielo=qty_hielo,
    metodo_pago=metodo_pago_str,
    total_eur=total,
)
```

### 11.2 Bug conocido #2: metodo_pago hardcodeado MIGRACION

**Problema**: Bridge hardcodea `metodo_pago="pagomovil"` en linea 2034. El metodo real se conoce despues cuando el cliente elige en el FSM.

**Solucion**: Anadir metodo `actualizar_metodo_pago` al agente FS:

```python
# src/agents/financial_agent.py — metodo nuevo
def actualizar_metodo_pago(self, fs_pedido_id: int, metodo_pago: str) -> None:
    """Actualiza metodo de pago despues de que el cliente elige."""
    from .database import get_db
    now = datetime.now(CARACAS_TZ).isoformat()
    with get_db() as conn:
        conn.execute("""
            UPDATE fs_pedidos
            SET metodo_pago = ?, actualizado_at = ?
            WHERE id = ?
        """, (metodo_pago, now, fs_pedido_id))
    logger.info("Metodo pago actualizado: fs_pedido=%d metodo=%s", fs_pedido_id, metodo_pago)
```

Bridge llama este metodo cuando el FSM detecta la eleccion (lineas 1832/1849 del bridge).

### 11.3 Bug conocido #3: pedidos existentes con metodo_pago vacio MIGRACION

Los 19 pedidos existentes tienen `metodo_pago` vacío. Se pueden actualizar con un script one-shot:

```sql
-- Suponiendo que la mayoria fueron pagomovil (default historico)
UPDATE fs_pedidos SET metodo_pago = 'pagomovil' WHERE metodo_pago IS NULL OR metodo_pago = '';
```

### 11.4 Dispatcher -> Financial Shield EXISTE (parcial)

```python
# Cuando chofer confirma entrega:
fs = get_agent()
fs.on_entrega_confirmada(fs_pedido_id=pedido_id, operador_id=chofer_id)
# Esto cambia estado_entrega a "entregado" y trigger el loop de verificacion
```

### 11.5 Financial Shield -> Telegram (reportes) EXISTE

```python
# reportes.py genera y envia via Telegram bot
# 6:30 PM: reporte diario del dia
# 7:00 AM: analytics del dia anterior (skills/run_analytics_7am.py)
```

---

## 12. ROADMAP DE IMPLEMENTACION

### Fase A — Migracion de esquema (1-2h)

- [ ] A1. Aplicar ALTER TABLE: rename tasa_eur_ves -> tasa_eur_ves_deuda
- [ ] A2. Aplicar ALTER TABLE: add monto_pagado_eur a fs_pedidos
- [ ] A3. Aplicar ALTER TABLE: rename tasa_eur_ves -> tasa_eur_ves_pago en fs_pagos
- [ ] A4. Aplicar ALTER TABLE: add comprobante_phash a fs_pagos
- [ ] A5. DROP/CREATE index: UNIQUE(referencia, metodo_pago) en fs_pagos
- [ ] A6. CREATE TABLE fs_audit_log + trigger
- [ ] A7. PRAGMA busy_timeout=5000 en database.py init
- [ ] A8. Actualizar models.py con nuevos campos
- [ ] A9. pytest debe seguir 105 passed

### Fase B — Fixes criticos (1-2h)

- [ ] B1. Metodo `actualizar_metodo_pago` en financial_agent.py
- [ ] B2. Llamar actualizar_metodo_pago desde bridge.py en FSM (lineas 1832/1849)
- [ ] B3. Script one-shot: fijar metodo_pago='pagomovil' en 19 pedidos existentes
- [ ] B4. Implementar `register_payment` con deuda criogenica en verificacion.py
- [ ] B5. pytest debe seguir 105 passed

### Fase C — Resiliencia (2-3h)

- [ ] C1. Activar cron de Hermes: ejecutar recordatorios cada 1h
- [ ] C2. Verificar que Zombie Killer funciona (reinicio + cron reanuda)
- [ ] C3. Llenar fs_empleados (YORDANIS, EVERT)
- [ ] C4. Llenar fs_productos (Botellon, Hielo con precios)
- [ ] C5. Llenar fs_tasas_cambio (seed inicial)

### Fase D — Mype limpieza (89 errores) (3-5h)

- [ ] D1. mypy database.py: 18 -> 0
- [ ] D2. mypy financial_agent.py: 12 -> 0
- [ ] D3. mypy dispatcher.py: 59 -> 0
- [ ] D4. pytest debe seguir 105 passed

### Fase E — Futuro (cuando el negocio lo requiera)

- [ ] E1. Anti-fraude pHash (cuando clientes suban comprobantes)
- [ ] E2. Prediccion de morosidad (cuando-hayan > 50 pedidos)
- [ ] E3. OCR Tesseract + GLM 5.2 vision (cuando se active FS_OCR_ENABLED)
- [ ] E4. Integracion comisiones choferes (FASE 2 del roadmap general)

---

## 13. CHECKLIST DE ACEPTACION (Definition of Done)

- [ ] BD segura: PRAGMA WAL + busy_timeout=5000 activos
- [ ] Integridad: transacciones usan BEGIN/COMMIT (context manager)
- [ ] Deuda criogenica: tasa_eur_ves_deuda al crear, tasa_eur_ves_pago al pagar
- [ ] Pagos parciales: monto_pagado_eur actualizado atomicamente
- [ ] Auditoria: trigger fs_audit_log registra todo UPDATE en fs_pedidos
- [ ] Anti-fraude: UNIQUE(referencia, metodo_pago) en fs_pagos
- [ ] Schedulador: cron Hermes cada 1h (no sleep en memoria)
- [ ] Separacion: FS es unico autorizado para fs_* (Valentina/Dispatcher no tocan)
- [ ] metodo_pago dinamico: bridge actualiza tras eleccion del cliente
- [ ] pytest 105 passed, 0 failed

---

## 14. ARCHIVOS CLAVE

| Archivo | Funcion | Lineas |
|---------|---------|--------|
| src/agents/financial_agent.py | Agente singleton (orquestador) | 373 |
| src/financial/database.py | Capa SQLite (init, CRUD, indices) | 645 |
| src/financial/models.py | Dataclasses tipadas | 199 |
| src/financial/cobranzas.py | Recordatorios + cuentas cobrar | 165 |
| src/financial/currency.py | Tasas EUR/VES/USD | 128 |
| src/financial/nomina.py | Nomina + comisiones | 131 |
| src/financial/reportes.py | Reportes Telegram | 175 |
| src/financial/verificacion.py | Verificacion pago | 252 |
| src/financial/proveedores.py | Pago proveedores | 83 |
| api/bridge.py:2034 | Integracion Valentina -> FS | - |

---

**Que el agua fluya.** 
