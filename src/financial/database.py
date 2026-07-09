"""
 ============================================================================
 Financial Shield — Base de datos
 Estación H2O · Maracaibo, Venezuela
 ============================================================================

Gestiona conexión SQLite, migraciones, y queries del módulo financiero.
Todas las tablas usan prefijo fs_ para evitar colisiones con Valentina.
 """

import os
import sqlite3
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
from contextlib import contextmanager

from .models import (
    Producto, PedidoFinanciero, Pago, CuentaCobrar,
    Empleado, Nomina, ProveedorPago, TasaCambio,
    ReporteDiario, VerificacionLog
)

logger = logging.getLogger("financial_shield.database")

# Timezone Caracas
CARACAS_TZ = timezone(timedelta(hours=-4))

# Path de la BD (misma que Valentina)
DB_PATH = os.getenv(
    "SQLITE_PATH",
    "/mnt/ssd_trabajo/hermes-agent/data/conversations.db"
)

# ============================================================================
# Schema SQL completo (10 tablas fs_*)
# ============================================================================

SCHEMA_SQL = """
-- Catálogo de productos
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

-- Vista financiera de cada pedido (1:1 con orders de Valentina)
CREATE TABLE IF NOT EXISTS fs_pedidos (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    pedido_id               INTEGER NOT NULL,
    cliente_telefono        TEXT,
    cliente_nombre          TEXT,
    operador_id             INTEGER,
    monto_total_eur         REAL NOT NULL,
    monto_total_ves         REAL,
    tasa_eur_ves            REAL NOT NULL,
    tasa_usd_ves_ref        REAL,
    botellones_cantidad     INTEGER DEFAULT 0,
    hielo_cantidad          INTEGER DEFAULT 0,
    metodo_pago             TEXT,
    estado_pago             TEXT DEFAULT 'pendiente',
    estado_entrega          TEXT DEFAULT 'sin_entregar',
    tipo_credito            TEXT,
    fecha_vencimiento_credito TEXT,
    verificacion_bancaria   TEXT DEFAULT 'pending',
    recordatorios_enviados  INTEGER DEFAULT 0,
    ultimo_recordatorio_at  TEXT,
    escalo_humano           BOOLEAN DEFAULT 0,
    entrega_confirmada_at   TEXT,
    creado_at               TEXT NOT NULL,
    actualizado_at          TEXT NOT NULL,
    UNIQUE(pedido_id)
);

-- Pagos recibidos
CREATE TABLE IF NOT EXISTS fs_pagos (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    fs_pedido_id        INTEGER,
    cuenta_cobrar_id    INTEGER,
    cliente_telefono    TEXT NOT NULL,
    cliente_nombre      TEXT,
    monto_eur           REAL NOT NULL,
    monto_ves           REAL,
    metodo_pago         TEXT NOT NULL,
    referencia          TEXT UNIQUE,
    tasa_eur_ves        REAL NOT NULL,
    verificacion_metodo TEXT DEFAULT 'pending',
    verificado          BOOLEAN DEFAULT 0,
    verificado_at       TEXT,
    verificado_por      TEXT,
    comprobante_url     TEXT,
    creado_at           TEXT NOT NULL,
    FOREIGN KEY (fs_pedido_id) REFERENCES fs_pedidos(id)
);

-- Cuentas por cobrar (créditos activos)
CREATE TABLE IF NOT EXISTS fs_cuentas_cobrar (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    cliente_telefono        TEXT NOT NULL,
    cliente_nombre          TEXT,
    fs_pedido_id            INTEGER NOT NULL,
    monto_original_eur      REAL NOT NULL,
    monto_pagado_eur        REAL DEFAULT 0,
    tipo_credito            TEXT NOT NULL,
    fecha_vencimiento       TEXT NOT NULL,
    estado                  TEXT DEFAULT 'pendiente',
    recordatorios_enviados  INTEGER DEFAULT 0,
    ultimo_recordatorio_at  TEXT,
    escalo_humano           BOOLEAN DEFAULT 0,
    cerrado_at              TEXT,
    creado_at               TEXT NOT NULL,
    actualizado_at          TEXT NOT NULL,
    FOREIGN KEY (fs_pedido_id) REFERENCES fs_pedidos(id)
);

-- Log de verificaciones (auditoría)
CREATE TABLE IF NOT EXISTS fs_verificacion_log (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    fs_pedido_id        INTEGER NOT NULL,
    intento             INTEGER NOT NULL,
    metodo_verificacion TEXT,
    pago_encontrado     BOOLEAN DEFAULT 0,
    accion              TEXT,
    resultado_detalle   TEXT,
    timestamp           TEXT NOT NULL,
    FOREIGN KEY (fs_pedido_id) REFERENCES fs_pedidos(id)
);

-- Pagos a proveedores (solo contado)
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

-- Empleados
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

-- Nómina
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
    estado                  TEXT DEFAULT 'pending',
    pagado_at               TEXT,
    creado_at               TEXT NOT NULL,
    FOREIGN KEY (empleado_id) REFERENCES fs_empleados(id)
);

-- Histórico de tasas (inmutable)
CREATE TABLE IF NOT EXISTS fs_tasas_cambio (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    par             TEXT NOT NULL,
    tasa            REAL NOT NULL,
    fuente          TEXT NOT NULL,
    notas           TEXT,
    registrado_at   TEXT NOT NULL
);

-- Reportes diarios
CREATE TABLE IF NOT EXISTS fs_reportes_diarios (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha               TEXT NOT NULL,
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

-- Índices
CREATE INDEX IF NOT EXISTS idx_fs_pedidos_cliente ON fs_pedidos(cliente_telefono);
CREATE INDEX IF NOT EXISTS idx_fs_pedidos_estado_pago ON fs_pedidos(estado_pago);
CREATE INDEX IF NOT EXISTS idx_fs_pedidos_estado_entrega ON fs_pedidos(estado_entrega);
CREATE INDEX IF NOT EXISTS idx_fs_cuentas_cobrar_estado ON fs_cuentas_cobrar(estado);
CREATE INDEX IF NOT EXISTS idx_fs_cuentas_cobrar_vencimiento ON fs_cuentas_cobrar(fecha_vencimiento);
CREATE INDEX IF NOT EXISTS idx_fs_pagos_referencia ON fs_pagos(referencia);
CREATE INDEX IF NOT EXISTS idx_fs_pagos_cliente ON fs_pagos(cliente_telefono);
CREATE INDEX IF NOT EXISTS idx_fs_verificacion_log_pedido ON fs_verificacion_log(fs_pedido_id);
CREATE INDEX IF NOT EXISTS idx_fs_tasas_cambio_par ON fs_tasas_cambio(par);
CREATE INDEX IF NOT EXISTS idx_fs_nomina_empleado ON fs_nomina(empleado_id);
"""

# Seed inicial de productos
SEED_PRODUCTOS_SQL = """
INSERT OR IGNORE INTO fs_productos (id, nombre, precio_base_eur, precio_volumen_eur, umbral_volumen, tiene_comision, comision_eur, activo) VALUES
(1, 'Botellón 19L', 1.00, 0.85, 10, 1, 0.07, 1),
(2, 'Bolsa Hielo 7.5kg', 1.20, 0.90, 5, 0, 0.00, 1);
"""


# ============================================================================
# Conexión y migraciones
# ============================================================================

@contextmanager
def get_db():
    """Context manager para conexión SQLite (thread-safe)."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error("Error BD: %s", e)
        raise
    finally:
        conn.close()


def init_database():
    """Inicializa tablas fs_* y carga seed de productos."""
    with get_db() as conn:
        conn.executescript(SCHEMA_SQL)
        conn.executescript(SEED_PRODUCTOS_SQL)
    logger.info("BD Financial Shield inicializada — 10 tablas fs_* creadas")


def now_iso() -> str:
    """Timestamp ISO 8601 America/Caracas."""
    return datetime.now(CARACAS_TZ).isoformat()


# ============================================================================
# Queries — Productos
# ============================================================================

def get_producto_by_id(producto_id: int) -> Optional[Producto]:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM fs_productos WHERE id = ?", (producto_id,)).fetchone()
        if row:
            return Producto(**dict(row))
    return None


def get_producto_by_nombre(nombre: str) -> Optional[Producto]:
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM fs_productos WHERE nombre LIKE ? AND activo = 1",
            (f"%{nombre}%",)
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
        cursor = conn.execute("""
            INSERT INTO fs_pedidos (
                pedido_id, cliente_telefono, cliente_nombre, operador_id,
                monto_total_eur, monto_total_ves, tasa_eur_ves, tasa_usd_ves_ref,
                botellones_cantidad, hielo_cantidad, metodo_pago,
                estado_pago, estado_entrega, tipo_credito,
                fecha_vencimiento_credito, verificacion_bancaria,
                creado_at, actualizado_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            pedido.pedido_id, pedido.cliente_telefono, pedido.cliente_nombre,
            pedido.operador_id, pedido.monto_total_eur, pedido.monto_total_ves,
            pedido.tasa_eur_ves, pedido.tasa_usd_ves_ref,
            pedido.botellones_cantidad, pedido.hielo_cantidad, pedido.metodo_pago,
            pedido.estado_pago, pedido.estado_entrega, pedido.tipo_credito,
            pedido.fecha_vencimiento_credito, pedido.verificacion_bancaria,
            now, now
        ))
        return cursor.lastrowid


def get_pedido_financiero_by_pedido_id(pedido_id: int) -> Optional[PedidoFinanciero]:
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM fs_pedidos WHERE pedido_id = ?", (pedido_id,)
        ).fetchone()
        if row:
            return PedidoFinanciero(**dict(row))
    return None


def get_pedidos_by_cliente(cliente_telefono: str) -> list[PedidoFinanciero]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM fs_pedidos WHERE cliente_telefono = ? ORDER BY creado_at DESC",
            (cliente_telefono,)
        ).fetchall()
        return [PedidoFinanciero(**dict(r)) for r in rows]


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
        conn.execute("""
            UPDATE fs_pedidos
            SET estado_pago = ?, verificacion_bancaria = ?, actualizado_at = ?
            WHERE id = ?
        """, (nuevo_estado, verificacion_metodo, now, fs_pedido_id))


def incrementar_recordatorio(fs_pedido_id: int):
    """Incrementa contador de recordatorios enviados."""
    now = now_iso()
    with get_db() as conn:
        conn.execute("""
            UPDATE fs_pedidos
            SET recordatorios_enviados = recordatorios_enviados + 1,
                ultimo_recordatorio_at = ?, actualizado_at = ?
            WHERE id = ?
        """, (now, now, fs_pedido_id))


def marcar_escalo_humano(fs_pedido_id: int):
    """Marca pedido como escalado a humano (3 recordatorios fallidos)."""
    now = now_iso()
    with get_db() as conn:
        conn.execute("""
            UPDATE fs_pedidos
            SET escalo_humano = 1, actualizado_at = ?
            WHERE id = ?
        """, (now, fs_pedido_id))


def confirmar_entrega(fs_pedido_id: int, operador_id: int = None):
    """Confirma entrega de pedido (trigger para loop de verificación)."""
    now = now_iso()
    with get_db() as conn:
        conn.execute("""
            UPDATE fs_pedidos
            SET estado_entrega = 'confirmado',
                entrega_confirmada_at = ?,
                estado_pago = 'verificando',
                operador_id = ?,
                actualizado_at = ?
            WHERE id = ?
        """, (now, operador_id, now, fs_pedido_id))


# ============================================================================
# Queries — Pagos
# ============================================================================

def create_pago(pago: Pago) -> int:
    """Registra un pago recibido."""
    now = now_iso()
    with get_db() as conn:
        cursor = conn.execute("""
            INSERT INTO fs_pagos (
                fs_pedido_id, cuenta_cobrar_id, cliente_telefono, cliente_nombre,
                monto_eur, monto_ves, metodo_pago, referencia, tasa_eur_ves,
                verificacion_metodo, verificado, verificado_at, verificado_por,
                comprobante_url, creado_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            pago.fs_pedido_id, pago.cuenta_cobrar_id, pago.cliente_telefono,
            pago.cliente_nombre, pago.monto_eur, pago.monto_ves, pago.metodo_pago,
            pago.referencia, pago.tasa_eur_ves, pago.verificacion_metodo,
            pago.verificado, pago.verificado_at, pago.verificado_por,
            pago.comprobante_url, now
        ))
        return cursor.lastrowid


def verificar_pago_manual(pago_id: int, verificado_por: str = "manual"):
    """Marca un pago como verificado manualmente."""
    now = now_iso()
    with get_db() as conn:
        conn.execute("""
            UPDATE fs_pagos
            SET verificado = 1, verificado_at = ?, verificado_por = ?,
                verificacion_metodo = 'manual'
            WHERE id = ?
        """, (now, verificado_por, pago_id))


def get_pagos_by_cliente(cliente_telefono: str) -> list[Pago]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM fs_pagos WHERE cliente_telefono = ? ORDER BY creado_at DESC",
            (cliente_telefono,)
        ).fetchall()
        return [Pago(**dict(r)) for r in rows]


def get_pago_by_referencia(referencia: str) -> Optional[Pago]:
    """Busca pago por referencia (anti-fraude)."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM fs_pagos WHERE referencia = ?", (referencia,)
        ).fetchone()
        if row:
            return Pago(**dict(row))
    return None


# ============================================================================
# Queries — Cuentas por cobrar
# ============================================================================

def create_cuenta_cobrar(cuenta: CuentaCobrar) -> int:
    now = now_iso()
    with get_db() as conn:
        cursor = conn.execute("""
            INSERT INTO fs_cuentas_cobrar (
                cliente_telefono, cliente_nombre, fs_pedido_id,
                monto_original_eur, monto_pagado_eur, tipo_credito,
                fecha_vencimiento, estado, creado_at, actualizado_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            cuenta.cliente_telefono, cuenta.cliente_nombre, cuenta.fs_pedido_id,
            cuenta.monto_original_eur, cuenta.monto_pagado_eur, cuenta.tipo_credito,
            cuenta.fecha_vencimiento, cuenta.estado, now, now
        ))
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
        rows = conn.execute("""
            SELECT * FROM fs_cuentas_cobrar
            WHERE estado IN ('pendiente', 'parcial')
            AND fecha_vencimiento < ?
            ORDER BY fecha_vencimiento ASC
        """, (today,)).fetchall()
        return [CuentaCobrar(**dict(r)) for r in rows]


# ============================================================================
# Queries — Tasas de cambio
# ============================================================================

def save_tasa(par: str, tasa: float, fuente: str, notas: str = None):
    """Guarda tasa de cambio (inmutable, siempre INSERT)."""
    now = now_iso()
    with get_db() as conn:
        conn.execute("""
            INSERT INTO fs_tasas_cambio (par, tasa, fuente, notas, registrado_at)
            VALUES (?, ?, ?, ?, ?)
        """, (par, tasa, fuente, notas, now))


def get_last_tasa(par: str = "EUR/VES") -> Optional[TasaCambio]:
    """Obtiene la última tasa registrada para un par."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM fs_tasas_cambio WHERE par = ? ORDER BY registrado_at DESC LIMIT 1",
            (par,)
        ).fetchone()
        if row:
            return TasaCambio(**dict(row))
    return None


# ============================================================================
# Queries — Verificación log (auditoría)
# ============================================================================

def log_verificacion(fs_pedido_id: int, intento: int, metodo: str,
                     pago_encontrado: bool, accion: str, detalle: str = ""):
    """Registra un intento de verificación en el log de auditoría."""
    now = now_iso()
    with get_db() as conn:
        conn.execute("""
            INSERT INTO fs_verificacion_log (
                fs_pedido_id, intento, metodo_verificacion,
                pago_encontrado, accion, resultado_detalle, timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (fs_pedido_id, intento, metodo, pago_encontrado, accion, detalle, now))


# ============================================================================
# Queries — Empleados y Nómina
# ============================================================================

def create_empleado(emp: Empleado) -> int:
    now = now_iso()
    with get_db() as conn:
        cursor = conn.execute("""
            INSERT INTO fs_empleados (
                nombre, rol, telefono, sueldo_fijo_eur,
                comision_botellon_eur, telegram_id, activo, creado_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            emp.nombre, emp.rol, emp.telefono, emp.sueldo_fijo_eur,
            emp.comision_botellon_eur, emp.telegram_id, emp.activo, now
        ))
        return cursor.lastrowid


def get_all_empleados() -> list[Empleado]:
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM fs_empleados WHERE activo = 1").fetchall()
        return [Empleado(**dict(r)) for r in rows]


def create_nomina(nom: Nomina) -> int:
    now = now_iso()
    with get_db() as conn:
        cursor = conn.execute("""
            INSERT INTO fs_nomina (
                empleado_id, empleado_nombre, fecha_inicio, fecha_fin,
                botellones_repartidos, sueldo_fijo_eur, comision_total_eur,
                total_eur, total_ves, tasa_eur_ves, estado, creado_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            nom.empleado_id, nom.empleado_nombre, nom.fecha_inicio, nom.fecha_fin,
            nom.botellones_repartidos, nom.sueldo_fijo_eur, nom.comision_total_eur,
            nom.total_eur, nom.total_ves, nom.tasa_eur_ves, nom.estado, now
        ))
        return cursor.lastrowid


# ============================================================================
# Queries — Proveedores
# ============================================================================

def create_proveedor_pago(pago: ProveedorPago) -> int:
    now = now_iso()
    with get_db() as conn:
        cursor = conn.execute("""
            INSERT INTO fs_proveedor_pagos (
                proveedor_id, proveedor_nombre, concepto,
                monto_eur, monto_ves, metodo_pago, referencia,
                tasa_eur_ves, comprobante_url, creado_at, creado_por
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            pago.proveedor_id, pago.proveedor_nombre, pago.concepto,
            pago.monto_eur, pago.monto_ves, pago.metodo_pago, pago.referencia,
            pago.tasa_eur_ves, pago.comprobante_url, now, pago.creado_por
        ))
        return cursor.lastrowid


# ============================================================================
# Queries — Reportes diarios
# ============================================================================

def save_reporte_diario(reporte: ReporteDiario) -> int:
    now = now_iso()
    with get_db() as conn:
        cursor = conn.execute("""
            INSERT INTO fs_reportes_diarios (
                fecha, ventas_total_eur, cobros_total_eur, por_cobrar_eur,
                ventas_total_ves, cobros_total_ves, por_cobrar_ves,
                num_pedidos, num_pagados, num_pendientes, num_morosos,
                nomina_eur, generado_at, enviado_telegram
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            reporte.fecha, reporte.ventas_total_eur, reporte.cobros_total_eur,
            reporte.por_cobrar_eur, reporte.ventas_total_ves, reporte.cobros_total_ves,
            reporte.por_cobrar_ves, reporte.num_pedidos, reporte.num_pagados,
            reporte.num_pendientes, reporte.num_morosos, reporte.nomina_eur,
            now, reporte.enviado_telegram
        ))
        return cursor.lastrowid


def mark_reporte_enviado(reporte_id: int, telegram_msg_id: str):
    with get_db() as conn:
        conn.execute("""
            UPDATE fs_reportes_diarios
            SET enviado_telegram = 1, telegram_msg_id = ?
            WHERE id = ?
        """, (telegram_msg_id, reporte_id))
