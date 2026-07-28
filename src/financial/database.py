"""
============================================================================
Financial Shield — Base de datos v3.0
Estación H2O · Maracaibo, Venezuela
============================================================================

Gestiona conexión SQLite, migraciones, y queries del módulo financiero.
Todas las tablas usan prefijo fs_ para evitar colisiones con Valentina.
"""

import logging
import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta, timezone

from .models import (
    CuentaCobrar,
    Empleado,
    Nomina,
    Pago,
    PedidoFinanciero,
    Producto,
    ProveedorPago,
    ReporteDiario,
    TasaCambio,
)

logger = logging.getLogger("financial_shield.database")

# Timezone Caracas
CARACAS_TZ = timezone(timedelta(hours=-4))

# Path de la BD (misma que Valentina)
DB_PATH = os.getenv("SQLITE_PATH", "/mnt/ssd_trabajo/hermes-agent/data/conversations.db")

# ============================================================================
# Schema SQL completo v3.0 (idempotente)
# ============================================================================

SCHEMA_V3_SQL = """
-- ============================================================================
-- PRAGMAS OBLIGATORIOS (se ejecutan en cada conexión via get_db())
-- ============================================================================
-- PRAGMA journal_mode=WAL;
-- PRAGMA busy_timeout=5000;
-- PRAGMA foreign_keys=ON;
-- PRAGMA synchronous=NORMAL;

-- ============================================================================
-- 1. CATÁLOGO DE PRODUCTOS
-- ============================================================================
CREATE TABLE IF NOT EXISTS fs_productos (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre              TEXT NOT NULL,
    precio_base_eur     REAL NOT NULL,
    precio_volumen_eur  REAL,
    umbral_volumen      INTEGER,
    tiene_comision      BOOLEAN DEFAULT 0,
    comision_eur        REAL DEFAULT 0.0,
    activo              BOOLEAN DEFAULT 1
);

-- Seed inicial (idempotente)
INSERT OR IGNORE INTO fs_productos (id, nombre, precio_base_eur, precio_volumen_eur, umbral_volumen, tiene_comision, comision_eur, activo) VALUES
(1, 'Botellón 19L', 1.00, 0.85, 10, 1, 0.07, 1),
(2, 'Bolsa Hielo 7.5kg', 1.20, 0.90, 5, 0, 0.00, 1);

-- ============================================================================
-- 2. VISTA FINANCIERA DE PEDIDOS (1:1 con orders de Valentina)
-- ============================================================================
CREATE TABLE IF NOT EXISTS fs_pedidos (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    pedido_id               INTEGER NOT NULL UNIQUE,
    cliente_telefono        TEXT NOT NULL,
    cliente_nombre          TEXT,
    operador_id             INTEGER,
    monto_total_eur         REAL NOT NULL,
    monto_pagado_eur        REAL DEFAULT 0,                   -- v3.0: tracking parciales
    tasa_eur_ves_deuda      REAL NOT NULL,                   -- v3.0: tasa congelada al crear deuda
    tasa_usd_ves_ref        REAL,
    botellones_cantidad     INTEGER DEFAULT 0,
    hielo_cantidad          INTEGER DEFAULT 0,
    metodo_pago             TEXT,                            -- pagomovil|efectivo_eur|efectivo_ves
    estado_pago             TEXT DEFAULT 'pendiente',        -- pendiente|parcial|pagado|verificando|vencido|moroso
    estado_entrega          TEXT DEFAULT 'sin_entregar',     -- sin_entregar|entregado|confirmado
    tipo_credito            TEXT,                            -- NULL=contado | express|semanal|mensual
    fecha_vencimiento_credito TEXT,
    verificacion_bancaria   TEXT DEFAULT 'pending',          -- pending|api|ocr|manual
    recordatorios_enviados  INTEGER DEFAULT 0,
    ultimo_recordatorio_at  TEXT,                            -- ISO8601 UTC
    escalo_humano           BOOLEAN DEFAULT 0,
    entrega_confirmada_at   TEXT,                            -- ISO8601 UTC
    creado_at               TEXT NOT NULL,                   -- ISO8601 UTC
    actualizado_at          TEXT NOT NULL                    -- ISO8601 UTC
);

CREATE INDEX IF NOT EXISTS idx_fs_pedidos_cliente ON fs_pedidos(cliente_telefono);
CREATE INDEX IF NOT EXISTS idx_fs_pedidos_estado_pago ON fs_pedidos(estado_pago);
CREATE INDEX IF NOT EXISTS idx_fs_pedidos_estado_entrega ON fs_pedidos(estado_entrega);

-- ============================================================================
-- 3. PAGOS RECIBIDOS (historial completo, inmutable)
-- ============================================================================
CREATE TABLE IF NOT EXISTS fs_pagos (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    fs_pedido_id        INTEGER,
    cliente_telefono    TEXT NOT NULL,
    cliente_nombre      TEXT,
    monto_eur           REAL NOT NULL,
    monto_ves           REAL,
    tasa_eur_ves_pago   REAL NOT NULL,                       -- v3.0: tasa al segundo del pago
    metodo_pago         TEXT NOT NULL,                       -- pagomovil|efectivo_eur|efectivo_ves
    referencia          TEXT,                                -- solo pagomovil
    comprobante_phash   TEXT,                                -- v3.0: perceptual hash anti-fraude
    verificacion_metodo TEXT DEFAULT 'pending',              -- pending|api_bancaria|ocr|manual
    verificado          BOOLEAN DEFAULT 0,
    verificado_at       TEXT,
    verificado_por      TEXT,
    comprobante_url     TEXT,
    creado_at           TEXT NOT NULL,                       -- ISO8601 UTC
    FOREIGN KEY (fs_pedido_id) REFERENCES fs_pedidos(id)
);

-- v3.0: Anti-fraude real — misma referencia + mismo método = duplicado
CREATE UNIQUE INDEX IF NOT EXISTS ux_fs_pagos_ref_metodo ON fs_pagos(referencia, metodo_pago);
CREATE INDEX IF NOT EXISTS idx_fs_pagos_cliente ON fs_pagos(cliente_telefono);
CREATE INDEX IF NOT EXISTS idx_fs_pagos_pedido ON fs_pagos(fs_pedido_id);

-- ============================================================================
-- 4. CUENTAS POR COBRAR (créditos activos)
-- ============================================================================
CREATE TABLE IF NOT EXISTS fs_cuentas_cobrar (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    cliente_telefono        TEXT NOT NULL,
    cliente_nombre          TEXT,
    fs_pedido_id            INTEGER NOT NULL,
    monto_original_eur      REAL NOT NULL,
    monto_pagado_eur        REAL DEFAULT 0,
    tipo_credito            TEXT NOT NULL,                   -- express|semanal|mensual
    fecha_vencimiento       TEXT NOT NULL,                   -- ISO8601 date
    estado                  TEXT DEFAULT 'pendiente',        -- pendiente|parcial|pagado|vencido|moroso
    recordatorios_enviados  INTEGER DEFAULT 0,
    ultimo_recordatorio_at  TEXT,
    escalo_humano           BOOLEAN DEFAULT 0,
    cerrado_at              TEXT,
    creado_at               TEXT NOT NULL,
    actualizado_at          TEXT NOT NULL,
    FOREIGN KEY (fs_pedido_id) REFERENCES fs_pedidos(id)
);

CREATE INDEX IF NOT EXISTS idx_fs_cuentas_cobrar_estado ON fs_cuentas_cobrar(estado);
CREATE INDEX IF NOT EXISTS idx_fs_cuentas_cobrar_vencimiento ON fs_cuentas_cobrar(fecha_vencimiento);

-- ============================================================================
-- 5. LOG DE VERIFICACIÓN (auditoría operativa del loop)
-- ============================================================================
CREATE TABLE IF NOT EXISTS fs_verificacion_log (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    fs_pedido_id        INTEGER NOT NULL,
    intento             INTEGER NOT NULL,
    metodo_verificacion TEXT,                                -- api_bancaria|ocr|manual
    pago_encontrado     BOOLEAN DEFAULT 0,
    accion              TEXT,                                -- recordatorio_enviado|escalo_humano|pagado
    resultado_detalle   TEXT,
    timestamp           TEXT NOT NULL,                       -- ISO8601 UTC
    FOREIGN KEY (fs_pedido_id) REFERENCES fs_pedidos(id)
);

CREATE INDEX IF NOT EXISTS idx_fs_verificacion_log_pedido ON fs_verificacion_log(fs_pedido_id);

-- ============================================================================
-- 6. PAGOS A PROVEEDORES (solo contado)
-- ============================================================================
CREATE TABLE IF NOT EXISTS fs_proveedor_pagos (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    proveedor_id        INTEGER NOT NULL,
    proveedor_nombre    TEXT NOT NULL,
    concepto            TEXT NOT NULL,
    monto_eur           REAL NOT NULL,
    monto_ves           REAL,
    metodo_pago         TEXT,
    referencia          TEXT,
    tasa_eur_ves        REAL NOT NULL,
    comprobante_url     TEXT,
    creado_at           TEXT NOT NULL,
    creado_por          TEXT
);

-- ============================================================================
-- 7. EMPLEADOS Y NÓMINA
-- ============================================================================
CREATE TABLE IF NOT EXISTS fs_empleados (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre                  TEXT NOT NULL,
    rol                     TEXT NOT NULL DEFAULT 'operador',
    telefono                TEXT,
    sueldo_fijo_eur         REAL NOT NULL,
    comision_botellon_eur   REAL DEFAULT 0.07,
    telegram_id             TEXT,
    activo                  BOOLEAN DEFAULT 1,
    creado_at               TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fs_nomina (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    empleado_id             INTEGER NOT NULL,
    empleado_nombre         TEXT,
    fecha_inicio            TEXT NOT NULL,
    fecha_fin               TEXT NOT NULL,
    botellones_repartidos   INTEGER DEFAULT 0,
    sueldo_fijo_eur         REAL NOT NULL,
    comision_total_eur      REAL DEFAULT 0,
    total_eur               REAL NOT NULL,
    total_ves               REAL,
    tasa_eur_ves            REAL,
    estado                  TEXT DEFAULT 'pending',            -- pending|calculada|pagada
    pagado_at               TEXT,
    creado_at               TEXT NOT NULL,
    FOREIGN KEY (empleado_id) REFERENCES fs_empleados(id)
);

CREATE INDEX IF NOT EXISTS idx_fs_nomina_empleado ON fs_nomina(empleado_id);

-- ============================================================================
-- 8. HISTÓRICO DE TASAS (inmutable, solo INSERT)
-- ============================================================================
CREATE TABLE IF NOT EXISTS fs_tasas_cambio (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    par             TEXT NOT NULL,                           -- EUR/VES | USD/VES
    tasa            REAL NOT NULL,
    fuente          TEXT NOT NULL,                           -- open_er_api|frankfurter|manual|bcv
    notas           TEXT,
    registrado_at   TEXT NOT NULL                            -- ISO8601 UTC
);

CREATE INDEX IF NOT EXISTS idx_fs_tasas_cambio_par ON fs_tasas_cambio(par);

-- ============================================================================
-- 9. REPORTES DIARIOS
-- ============================================================================
CREATE TABLE IF NOT EXISTS fs_reportes_diarios (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha               TEXT NOT NULL,                       -- YYYY-MM-DD
    ventas_total_eur    REAL DEFAULT 0,
    cobros_total_eur    REAL DEFAULT 0,
    por_cobrar_eur      REAL DEFAULT 0,
    ventas_total_ves    REAL DEFAULT 0,
    cobros_total_ves    REAL DEFAULT 0,
    por_cobrar_ves      REAL DEFAULT 0,
    num_pedidos         INTEGER DEFAULT 0,
    num_pagados         INTEGER DEFAULT 0,
    num_pendientes      INTEGER DEFAULT 0,
    num_morosos         INTEGER DEFAULT 0,
    nomina_eur          REAL DEFAULT 0,
    generado_at         TEXT NOT NULL,
    enviado_telegram    BOOLEAN DEFAULT 0,
    telegram_msg_id     TEXT
);

-- ============================================================================
-- 10. v3.0 AUDITORÍA FORENSE (triggers automáticos)
-- ============================================================================
CREATE TABLE IF NOT EXISTS fs_audit_log (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    tabla               TEXT NOT NULL,                       -- fs_pedidos|fs_pagos|fs_cuentas_cobrar
    registro_id         INTEGER NOT NULL,
    accion              TEXT NOT NULL,                       -- INSERT|UPDATE|DELETE
    estado_anterior     TEXT,                                -- JSON
    estado_nuevo        TEXT,                                -- JSON
    modificado_por      TEXT,                                -- 'sistema'|'valentina'|'lider'|'dispatcher'
    timestamp           TEXT NOT NULL                        -- ISO8601 UTC
);

CREATE INDEX IF NOT EXISTS idx_fs_audit_log_tabla_reg ON fs_audit_log(tabla, registro_id);
CREATE INDEX IF NOT EXISTS idx_fs_audit_log_timestamp ON fs_audit_log(timestamp);

-- Triggers — se ejecutan AUTOMÁTICAMENTE en cada WRITE
CREATE TRIGGER IF NOT EXISTS trg_audit_fs_pedidos_insert
AFTER INSERT ON fs_pedidos
FOR EACH ROW
BEGIN
    INSERT INTO fs_audit_log (tabla, registro_id, accion, estado_anterior, estado_nuevo, modificado_por, timestamp)
    VALUES ('fs_pedidos', NEW.id, 'INSERT', NULL,
            json_object(
                'estado_pago', NEW.estado_pago,
                'monto_total_eur', NEW.monto_total_eur,
                'monto_pagado_eur', NEW.monto_pagado_eur,
                'estado_entrega', NEW.estado_entrega
            ),
            'sistema', datetime('now'));
END;

CREATE TRIGGER IF NOT EXISTS trg_audit_fs_pedidos_update
AFTER UPDATE ON fs_pedidos
FOR EACH ROW
BEGIN
    INSERT INTO fs_audit_log (tabla, registro_id, accion, estado_anterior, estado_nuevo, modificado_por, timestamp)
    VALUES ('fs_pedidos', NEW.id, 'UPDATE',
            json_object(
                'estado_pago', OLD.estado_pago,
                'monto_pagado_eur', OLD.monto_pagado_eur,
                'estado_entrega', OLD.estado_entrega,
                'recordatorios_enviados', OLD.recordatorios_enviados,
                'escalo_humano', OLD.escalo_humano
            ),
            json_object(
                'estado_pago', NEW.estado_pago,
                'monto_pagado_eur', NEW.monto_pagado_eur,
                'estado_entrega', NEW.estado_entrega,
                'recordatorios_enviados', NEW.recordatorios_enviados,
                'escalo_humano', NEW.escalo_humano
            ),
            'sistema', datetime('now'));
END;

CREATE TRIGGER IF NOT EXISTS trg_audit_fs_pagos_insert
AFTER INSERT ON fs_pagos
FOR EACH ROW
BEGIN
    INSERT INTO fs_audit_log (tabla, registro_id, accion, estado_anterior, estado_nuevo, modificado_por, timestamp)
    VALUES ('fs_pagos', NEW.id, 'INSERT', NULL,
            json_object(
                'fs_pedido_id', NEW.fs_pedido_id,
                'monto_eur', NEW.monto_eur,
                'metodo_pago', NEW.metodo_pago,
                'referencia', NEW.referencia,
                'verificado', NEW.verificado
            ),
            'sistema', datetime('now'));
END;

CREATE TRIGGER IF NOT EXISTS trg_audit_fs_cuentas_cobrar_update
AFTER UPDATE ON fs_cuentas_cobrar
FOR EACH ROW
BEGIN
    INSERT INTO fs_audit_log (tabla, registro_id, accion, estado_anterior, estado_nuevo, modificado_por, timestamp)
    VALUES ('fs_cuentas_cobrar', NEW.id, 'UPDATE',
            json_object('estado', OLD.estado, 'monto_pagado_eur', OLD.monto_pagado_eur),
            json_object('estado', NEW.estado, 'monto_pagado_eur', NEW.monto_pagado_eur),
            'sistema', datetime('now'));
END;
"""


# ============================================================================
# Conexión y migraciones
# ============================================================================


@contextmanager
def get_db() -> Iterator[sqlite3.Connection]:
    """Context manager para conexión SQLite (thread-safe, WAL, FK, busy_timeout)."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA synchronous=NORMAL")
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error("Error BD: %s", e)
        raise
    finally:
        conn.close()


def init_database_v3() -> None:
    """
    Migración idempotente a v3.0:
    - Ejecuta schema base (CREATE IF NOT EXISTS)
    - Añade columnas nuevas vía ALTER TABLE (seguro si ya existen)
    - Backfill: tasa_eur_ves_deuda = tasa_eur_ves legado
    - Backfill: monto_pagado_eur = suma pagos verificados
    - Sincroniza estado_pago según monto_pagado_eur
    """
    with get_db() as conn:
        # 1. Schema base (idempotente)
        conn.executescript(SCHEMA_V3_SQL)

        # 2. Migraciones ALTER TABLE (ignorar si columna ya existe)
        migraciones = [
            # fs_pedidos
            "ALTER TABLE fs_pedidos ADD COLUMN monto_pagado_eur REAL DEFAULT 0",
            "ALTER TABLE fs_pedidos ADD COLUMN tasa_eur_ves_deuda REAL DEFAULT 0",
            # fs_pagos
            "ALTER TABLE fs_pagos ADD COLUMN comprobante_phash TEXT",
            # Nota: UNIQUE(referencia, metodo_pago) se crea en schema; si existe, ignora
        ]

        for sql in migraciones:
            try:
                conn.execute(sql)
                logger.info("Migración aplicada: %s", sql[:60])
            except sqlite3.OperationalError as e:
                if "duplicate column" in str(e).lower() or "already exists" in str(e).lower():
                    pass  # Ya existe, ok
                else:
                    raise

        # 3. Backfill: tasa_eur_ves_deuda = tasa_eur_ves donde sea 0/NULL
        conn.execute("""
            UPDATE fs_pedidos 
            SET tasa_eur_ves_deuda = tasa_eur_ves 
            WHERE tasa_eur_ves_deuda = 0 OR tasa_eur_ves_deuda IS NULL
        """)

        # 4. Backfill: monto_pagado_eur = suma de pagos verificados por pedido
        conn.execute("""
            UPDATE fs_pedidos
            SET monto_pagado_eur = COALESCE((
                SELECT SUM(monto_eur) FROM fs_pagos 
                WHERE fs_pagos.fs_pedido_id = fs_pedidos.id AND verificado = 1
            ), 0)
            WHERE monto_pagado_eur = 0
        """)

        # 5. Sincronizar estado_pago según monto_pagado_eur
        conn.execute("""
            UPDATE fs_pedidos
            SET estado_pago = CASE
                WHEN monto_pagado_eur >= monto_total_eur - 0.01 THEN 'pagado'
                WHEN monto_pagado_eur > 0 THEN 'parcial'
                ELSE estado_pago
            END
            WHERE estado_pago IN ('pendiente', 'verificando')
        """)

    logger.info(
        "Financial Shield v3.0 DB inicializada/migrada — 10 tablas fs_* + audit_log + triggers"
    )


def now_iso() -> str:
    """Timestamp ISO 8601 UTC (no Caracas) para consistencia global."""
    return datetime.now(UTC).isoformat()


# ============================================================================
# Queries — Productos
# ============================================================================


def get_producto_by_id(producto_id: int) -> Producto | None:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM fs_productos WHERE id = ?", (producto_id,)).fetchone()
        if row:
            return Producto(**dict(row))
    return None


def get_producto_by_nombre(nombre: str) -> Producto | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM fs_productos WHERE nombre LIKE ? AND activo = 1", (f"%{nombre}%",)
        ).fetchone()
        if row:
            return Producto(**dict(row))
    return None


def get_all_productos() -> list[Producto]:
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM fs_productos WHERE activo = 1").fetchall()
        return [Producto(**dict(r)) for r in rows]


# ============================================================================
# Queries — Pedidos financieros
# ============================================================================


def create_pedido_financiero(pedido: PedidoFinanciero) -> int:
    """Crea un nuevo pedido financiero. Retorna ID."""
    now = now_iso()
    with get_db() as conn:
        cursor = conn.execute(
            """
            INSERT INTO fs_pedidos (
                pedido_id, cliente_telefono, cliente_nombre, operador_id,
                monto_total_eur, monto_total_ves, tasa_eur_ves, tasa_eur_ves_deuda,
                tasa_usd_ves_ref, botellones_cantidad, hielo_cantidad, metodo_pago,
                estado_pago, estado_entrega, tipo_credito,
                fecha_vencimiento_credito, verificacion_bancaria,
                creado_at, actualizado_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                pedido.pedido_id,
                pedido.cliente_telefono,
                pedido.cliente_nombre,
                pedido.operador_id,
                pedido.monto_total_eur,
                pedido.monto_total_ves,
                pedido.tasa_eur_ves,
                pedido.tasa_eur_ves_deuda,  # v3.0: ambos
                pedido.tasa_usd_ves_ref,
                pedido.botellones_cantidad,
                pedido.hielo_cantidad,
                pedido.metodo_pago,
                pedido.estado_pago,
                pedido.estado_entrega,
                pedido.tipo_credito,
                pedido.fecha_vencimiento_credito,
                pedido.verificacion_bancaria,
                now,
                now,
            ),
        )
        return cursor.lastrowid


def get_pedido_financiero_by_pedido_id(pedido_id: int) -> PedidoFinanciero | None:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM fs_pedidos WHERE pedido_id = ?", (pedido_id,)).fetchone()
        if row:
            return PedidoFinanciero(**dict(row))
    return None


def get_pedidos_by_cliente(cliente_telefono: str) -> list[PedidoFinanciero]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM fs_pedidos WHERE cliente_telefono = ? ORDER BY creado_at DESC",
            (cliente_telefono,),
        ).fetchall()
        return [PedidoFinanciero(**dict(r)) for r in rows]


def buscar_pedidos_por_telefono_monto(
    telefono_emisor: str,
    monto_str: str,
    estados_permitidos: list[str] | None = None,
) -> list[PedidoFinanciero]:
    """
    Busca fs_pedidos que coincidan con teléfono y monto aproximado.
    
    Args:
        telefono_emisor: Teléfono del pagador (se normaliza internamente)
        monto_str: Monto como string (ej: "123.45")
        estados_permitidos: Lista de estados_pago válidos (default: pendiente,verificando,parcial,vencido)
    
    Returns:
        Lista de PedidoFinanciero ordenados por fecha (más reciente primero)
    """
    if estados_permitidos is None:
        estados_permitidos = ["pendiente", "verificando", "parcial", "vencido"]
    
    try:
        monto_objetivo = float(monto_str)
    except (ValueError, TypeError):
        logger.warning("Monto inválido para búsqueda: %s", monto_str)
        return []
    
    # Rango de tolerancia ±1% (mínimo 1 centavo)
    tolerancia = max(0.01, monto_objetivo * 0.01)
    monto_min = monto_objetivo - tolerancia
    monto_max = monto_objetivo + tolerancia
    
    # Normalizar teléfono: solo dígitos, 10 dígitos finales
    import re
    digitos = re.sub(r"\D", "", telefono_emisor)
    if digitos.startswith("58"):
        digitos = digitos[2:]
    if digitos.startswith("0"):
        digitos = digitos[1:]
    
    if len(digitos) != 10:
        logger.warning("Teléfono no normalizable a 10 dígitos: %s → %s", telefono_emisor, digitos)
        telefono_norm = telefono_emisor  # fallback
    else:
        telefono_norm = digitos
    
    placeholders = ",".join(["?"] * len(estados_permitidos))
    
    with get_db() as conn:
        query = f"""
            SELECT * FROM fs_pedidos
            WHERE 
                (cliente_telefono LIKE ? OR cliente_telefono LIKE ? OR cliente_telefono LIKE ?)
                AND monto_total_eur BETWEEN ? AND ?
                AND estado_pago IN ({",".join(["?"] * len(estados_permitidos))})
            ORDER BY creado_at DESC
        """
        
        # Variaciones de teléfono: +58XXXXXXXXXX, 0XXXXXXXXXX, XXXXXXXXXX
        tel_vars = [
            f"%{telefono_norm}%",
            f"+58{telefono_norm}%",
            f"0{telefono_norm}%",
        ]
        
        params = tel_vars + [monto_min, monto_max] + estados_permitidos
        rows = conn.execute(query, params).fetchall()
        return [PedidoFinanciero(**dict(r)) for r in rows]


def seleccionar_mejor_match(
    pedidos: list[PedidoFinanciero],
    telefono_emisor: str,
    monto: float,
) -> PedidoFinanciero | None:
    """
    Selecciona el mejor match entre candidatos.
    Criterios: 1) teléfono exacto, 2) monto exacto, 3) más reciente.
    """
    if not pedidos:
        return None
    
    if len(pedidos) == 1:
        return pedidos[0]
    
    import re
    telefono_norm = re.sub(r"\D", "", telefono_emisor)
    if telefono_norm.startswith("58"):
        telefono_norm = telefono_norm[2:]
    if telefono_norm.startswith("0"):
        telefono_norm = telefono_norm[1:]
    
    scored = []
    for p in pedidos:
        score = 0
        p_tel_norm = re.sub(r"\D", "", p.cliente_telefono or "")
        if p_tel_norm.startswith("58"):
            p_tel_norm = p_tel_norm[2:]
        if p_tel_norm.startswith("0"):
            p_tel_norm = p_tel_norm[1:]
        
        # Teléfono exacto (últimos 10 dígitos)
        if p_tel_norm == telefono_norm:
            score += 100
        elif telefono_norm in p_tel_norm or p_tel_norm in telefono_norm:
            score += 50
        
        # Monto exacto (dentro de centavos)
        if abs(p.monto_total_eur - monto) < 0.01:
            score += 50
        elif abs(p.monto_total_eur - monto) < 1.0:
            score += 20
        
        # Más reciente
        score += 10
        
        scored.append((score, p))
    
    scored.sort(key=lambda x: x[0], reverse=True)
    
    logger.info(
        "Match scoring: top=%s (score=%.0f) vs alternatives=%d",
        scored[0][1].id, scored[0][0], len(scored) - 1
    )
    
    return scored[0][1]


def get_pedidos_pendientes_pago() -> list[PedidoFinanciero]:
    """Pedidos entregados pero sin pago (para loop de recordatorios)."""
    with get_db() as conn:
        rows = conn.execute("""
            SELECT * FROM fs_pedidos
            WHERE estado_pago IN ('pendiente', 'verificando', 'parcial')
            AND estado_entrega IN ('entregado', 'confirmado')
            AND escalo_humano = 0
            AND recordatorios_enviados < 3
            ORDER BY entrega_confirmada_at ASC
        """).fetchall()
        return [PedidoFinanciero(**dict(r)) for r in rows]


def update_estado_pago(fs_pedido_id: int, nuevo_estado: str, verificacion_metodo: str = None):
    """Actualiza estado de pago de un pedido financiero."""
    now = now_iso()
    with get_db() as conn:
        conn.execute(
            """
            UPDATE fs_pedidos
            SET estado_pago = ?, verificacion_bancaria = ?, actualizado_at = ?
            WHERE id = ?
        """,
            (nuevo_estado, verificacion_metodo, now, fs_pedido_id),
        )


def incrementar_recordatorio(fs_pedido_id: int):
    """Incrementa contador de recordatorios enviados."""
    now = now_iso()
    with get_db() as conn:
        conn.execute(
            """
            UPDATE fs_pedidos
            SET recordatorios_enviados = recordatorios_enviados + 1,
                ultimo_recordatorio_at = ?, actualizado_at = ?
            WHERE id = ?
        """,
            (now, now, fs_pedido_id),
        )


def marcar_escalo_humano(fs_pedido_id: int):
    """Marca pedido como escalado a humano (3 recordatorios fallidos)."""
    now = now_iso()
    with get_db() as conn:
        conn.execute(
            """
            UPDATE fs_pedidos
            SET escalo_humano = 1, actualizado_at = ?
            WHERE id = ?
        """,
            (now, fs_pedido_id),
        )


def confirmar_entrega(fs_pedido_id: int, operador_id: int = None):
    """Confirma entrega de pedido (trigger para loop de verificación)."""
    now = now_iso()
    with get_db() as conn:
        conn.execute(
            """
            UPDATE fs_pedidos
            SET estado_entrega = 'confirmado',
                entrega_confirmada_at = ?,
                estado_pago = 'verificando',
                operador_id = ?,
                actualizado_at = ?
            WHERE id = ?
        """,
            (now, operador_id, now, fs_pedido_id),
        )


# v3.0: Actualización atómica de monto pagado + estado
def add_pago_and_update_pedido(
    fs_pedido_id: int,
    monto_eur: float,
    monto_ves: float,
    tasa_eur_ves_pago: float,
    metodo_pago: str,
    referencia: str = None,
    comprobante_phash: str = None,
    verificacion_metodo: str = "manual",
    verificado_por: str = "sistema",
) -> tuple[int, str]:
    """
    Transacción atómica: INSERT en fs_pagos + UPDATE fs_pedidos (monto_pagado_eur, estado_pago).
    Retorna (pago_id, nuevo_estado_pago).
    """
    now = now_iso()
    with get_db() as conn:
        # 1. Insertar pago (incluye tasa_eur_ves legacy para compatibilidad)
        cursor = conn.execute(
            """
            INSERT INTO fs_pagos (
                fs_pedido_id, cliente_telefono, cliente_nombre,
                monto_eur, monto_ves, tasa_eur_ves, tasa_eur_ves_pago, metodo_pago,
                referencia, comprobante_phash, verificacion_metodo,
                verificado, verificado_at, verificado_por, creado_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)
        """,
            (
                fs_pedido_id,
                "",
                "",  # cliente_telefono/nombre se llenan desde el pedido si hace falta
                monto_eur,
                monto_ves,
                tasa_eur_ves_pago,
                tasa_eur_ves_pago,
                metodo_pago,
                referencia,
                comprobante_phash,
                verificacion_metodo,
                now,
                verificado_por,
                now,
            ),
        )
        pago_id = cursor.lastrowid

        # 2. Actualizar pedido: sumar monto_pagado_eur + recalcular estado
        conn.execute(
            """
            UPDATE fs_pedidos
            SET monto_pagado_eur = monto_pagado_eur + ?,
                estado_pago = CASE
                    WHEN monto_pagado_eur + ? >= monto_total_eur - 0.01 THEN 'pagado'
                    WHEN monto_pagado_eur + ? > 0 THEN 'parcial'
                    ELSE estado_pago
                END,
                actualizado_at = ?
            WHERE id = ?
        """,
            (monto_eur, monto_eur, monto_eur, now, fs_pedido_id),
        )

        # 3. Obtener nuevo estado
        row = conn.execute(
            "SELECT estado_pago FROM fs_pedidos WHERE id = ?", (fs_pedido_id,)
        ).fetchone()
        nuevo_estado = row["estado_pago"] if row else "desconocido"

    return pago_id, nuevo_estado


# ============================================================================
# Queries — Pagos
# ============================================================================


def create_pago(pago: Pago) -> int:
    """Registra un pago recibido (legacy, usar add_pago_and_update_pedido para v3.0)."""
    now = now_iso()
    with get_db() as conn:
        cursor = conn.execute(
            """
            INSERT INTO fs_pagos (
                fs_pedido_id, cuenta_cobrar_id, cliente_telefono, cliente_nombre,
                monto_eur, monto_ves, metodo_pago, referencia, tasa_eur_ves,
                verificacion_metodo, verificado, verificado_at, verificado_por,
                comprobante_url, creado_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                pago.fs_pedido_id,
                pago.cuenta_cobrar_id,
                pago.cliente_telefono,
                pago.cliente_nombre,
                pago.monto_eur,
                pago.monto_ves,
                pago.metodo_pago,
                pago.referencia,
                pago.tasa_eur_ves,
                pago.verificacion_metodo,
                pago.verificado,
                pago.verificado_at,
                pago.verificado_por,
                pago.comprobante_url,
                now,
            ),
        )
        return cursor.lastrowid


def verificar_pago_manual(pago_id: int, verificado_por: str = "manual"):
    """Marca un pago como verificado manualmente."""
    now = now_iso()
    with get_db() as conn:
        conn.execute(
            """
            UPDATE fs_pagos
            SET verificado = 1, verificado_at = ?, verificado_por = ?,
                verificacion_metodo = 'manual'
            WHERE id = ?
        """,
            (now, verificado_por, pago_id),
        )


def get_pagos_by_cliente(cliente_telefono: str) -> list[Pago]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM fs_pagos WHERE cliente_telefono = ? ORDER BY creado_at DESC",
            (cliente_telefono,),
        ).fetchall()
        return [Pago(**dict(r)) for r in rows]


def get_pago_by_referencia(referencia: str) -> Pago | None:
    """Busca pago por referencia (anti-fraude)."""
    with get_db() as conn:
        row = conn.execute("SELECT * FROM fs_pagos WHERE referencia = ?", (referencia,)).fetchone()
        if row:
            return Pago(**dict(row))
    return None


# ============================================================================
# Queries — Cuentas por cobrar
# ============================================================================


def create_cuenta_cobrar(cuenta: CuentaCobrar) -> int:
    now = now_iso()
    with get_db() as conn:
        cursor = conn.execute(
            """
            INSERT INTO fs_cuentas_cobrar (
                cliente_telefono, cliente_nombre, fs_pedido_id,
                monto_original_eur, monto_pagado_eur, tipo_credito,
                fecha_vencimiento, estado, creado_at, actualizado_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                cuenta.cliente_telefono,
                cuenta.cliente_nombre,
                cuenta.fs_pedido_id,
                cuenta.monto_original_eur,
                cuenta.monto_pagado_eur,
                cuenta.tipo_credito,
                cuenta.fecha_vencimiento,
                cuenta.estado,
                now,
                now,
            ),
        )
        return cursor.lastrowid


def get_cuentas_cobrar_activas() -> list[CuentaCobrar]:
    """Cuentas por cobrar pendientes o parciales."""
    with get_db() as conn:
        rows = conn.execute("""
            SELECT * FROM fs_cuentas_cobrar
            WHERE estado IN ('pendiente', 'parcial')
            ORDER BY fecha_vencimiento ASC
        """).fetchall()
        return [CuentaCobrar(**dict(r)) for r in rows]


def get_cuentas_vencidas() -> list[CuentaCobrar]:
    """Cuentas vencidas (fecha < hoy)."""
    today = datetime.now(CARACAS_TZ).strftime("%Y-%m-%d")
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT * FROM fs_cuentas_cobrar
            WHERE estado IN ('pendiente', 'parcial')
            AND fecha_vencimiento < ?
            ORDER BY fecha_vencimiento ASC
        """,
            (today,),
        ).fetchall()
        return [CuentaCobrar(**dict(r)) for r in rows]


# ============================================================================
# Queries — Tasas de cambio
# ============================================================================


def save_tasa(par: str, tasa: float, fuente: str, notas: str = None):
    """Guarda tasa de cambio (inmutable, siempre INSERT)."""
    now = now_iso()
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO fs_tasas_cambio (par, tasa, fuente, notas, registrado_at)
            VALUES (?, ?, ?, ?, ?)
        """,
            (par, tasa, fuente, notas, now),
        )


def get_last_tasa(par: str = "EUR/VES") -> TasaCambio | None:
    """Obtiene la última tasa registrada para un par."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM fs_tasas_cambio WHERE par = ? ORDER BY registrado_at DESC LIMIT 1",
            (par,),
        ).fetchone()
        if row:
            return TasaCambio(**dict(row))
    return None


# ============================================================================
# Queries — Verificación log (auditoría operativa)
# ============================================================================


def log_verificacion(
    fs_pedido_id: int,
    intento: int,
    metodo: str,
    pago_encontrado: bool,
    accion: str,
    detalle: str = "",
):
    """Registra un intento de verificación en el log de auditoría."""
    now = now_iso()
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO fs_verificacion_log (
                fs_pedido_id, intento, metodo_verificacion,
                pago_encontrado, accion, resultado_detalle, timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
            (fs_pedido_id, intento, metodo, pago_encontrado, accion, detalle, now),
        )


# ============================================================================
# Queries — Empleados y Nómina
# ============================================================================


def create_empleado(emp: Empleado) -> int:
    now = now_iso()
    with get_db() as conn:
        cursor = conn.execute(
            """
            INSERT INTO fs_empleados (
                nombre, rol, telefono, sueldo_fijo_eur,
                comision_botellon_eur, telegram_id, activo, creado_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                emp.nombre,
                emp.rol,
                emp.telefono,
                emp.sueldo_fijo_eur,
                emp.comision_botellon_eur,
                emp.telegram_id,
                emp.activo,
                now,
            ),
        )
        return cursor.lastrowid


def get_all_empleados() -> list[Empleado]:
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM fs_empleados WHERE activo = 1").fetchall()
        return [Empleado(**dict(r)) for r in rows]


def create_nomina(nom: Nomina) -> int:
    now = now_iso()
    with get_db() as conn:
        cursor = conn.execute(
            """
            INSERT INTO fs_nomina (
                empleado_id, empleado_nombre, fecha_inicio, fecha_fin,
                botellones_repartidos, sueldo_fijo_eur, comision_total_eur,
                total_eur, total_ves, tasa_eur_ves, estado, creado_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                nom.empleado_id,
                nom.empleado_nombre,
                nom.fecha_inicio,
                nom.fecha_fin,
                nom.botellones_repartidos,
                nom.sueldo_fijo_eur,
                nom.comision_total_eur,
                nom.total_eur,
                nom.total_ves,
                nom.tasa_eur_ves,
                nom.estado,
                now,
            ),
        )
        return cursor.lastrowid


# ============================================================================
# Queries — Proveedores
# ============================================================================


def create_proveedor_pago(pago: ProveedorPago) -> int:
    now = now_iso()
    with get_db() as conn:
        cursor = conn.execute(
            """
            INSERT INTO fs_proveedor_pagos (
                proveedor_id, proveedor_nombre, concepto,
                monto_eur, monto_ves, metodo_pago, referencia,
                tasa_eur_ves, comprobante_url, creado_at, creado_por
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                pago.proveedor_id,
                pago.proveedor_nombre,
                pago.concepto,
                pago.monto_eur,
                pago.monto_ves,
                pago.metodo_pago,
                pago.referencia,
                pago.tasa_eur_ves,
                pago.comprobante_url,
                now,
                pago.creado_por,
            ),
        )
        return cursor.lastrowid


# ============================================================================
# Queries — Reportes diarios
# ============================================================================


def save_reporte_diario(reporte: ReporteDiario) -> int:
    now = now_iso()
    with get_db() as conn:
        cursor = conn.execute(
            """
            INSERT INTO fs_reportes_diarios (
                fecha, ventas_total_eur, cobros_total_eur, por_cobrar_eur,
                ventas_total_ves, cobros_total_ves, por_cobrar_ves,
                num_pedidos, num_pagados, num_pendientes, num_morosos,
                nomina_eur, generado_at, enviado_telegram
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                reporte.fecha,
                reporte.ventas_total_eur,
                reporte.cobros_total_eur,
                reporte.por_cobrar_eur,
                reporte.ventas_total_ves,
                reporte.cobros_total_ves,
                reporte.por_cobrar_ves,
                reporte.num_pedidos,
                reporte.num_pagados,
                reporte.num_pendientes,
                reporte.num_morosos,
                reporte.nomina_eur,
                now,
                reporte.enviado_telegram,
            ),
        )
        return cursor.lastrowid


def mark_reporte_enviado(reporte_id: int, telegram_msg_id: str):
    with get_db() as conn:
        conn.execute(
            """
            UPDATE fs_reportes_diarios
            SET enviado_telegram = 1, telegram_msg_id = ?
            WHERE id = ?
        """,
            (telegram_msg_id, reporte_id),
        )
