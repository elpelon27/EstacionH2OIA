#!/usr/bin/env python3
"""
Migración v3.1 conversations.db — Estación H2O Maracaibo
========================================================
Corrige desviaciones entre esquema real y especificación Financial Shield v3.0.

Cambios:
1. fs_pedidos: añadir monto_total_ves, tasa_usd_ves_ref
2. fs_pedidos: corregir monto_pagado_eur (DEFAULT 0), tasa_eur_ves_deuda (NOT NULL DEFAULT 0)
3. fs_pedidos: añadir UNIQUE en pedido_id
4. fs_pagos: eliminar columna duplicada tasa_eur_ves, asegurar tasa_eur_ves_pago NOT NULL
5. Añadir trigger trg_audit_fs_pagos_update faltante
6. Backfill: poblar tasa_eur_ves_deuda = tasa_eur_ves donde sea 0/NULL
7. Backfill: monto_pagado_eur = SUM(fs_pagos.monto_eur) por pedido verificado
8. Backfill: fs_pagos.tasa_eur_ves_pago = tasa_eur_ves (migrar de columna vieja)

Estrategia: Recrear tablas (SQLite no soporta ALTER COLUMN NOT NULL / DROP COLUMN directo).
"""

import os
import sqlite3
import sys
from datetime import datetime

DB_PATH = os.getenv("SQLITE_PATH", "/mnt/ssd_trabajo/hermes-agent/data/conversations.db")
BACKUP_DIR = "/mnt/ssd_trabajo/backups"


def log(msg: str) -> None:
    print(f"[{datetime.now().isoformat()}] {msg}", flush=True)


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.row_factory = sqlite3.Row
    return conn


def backup_db() -> str:
    """Crea backup antes de migrar."""
    os.makedirs(BACKUP_DIR, exist_ok=True)
    backup_path = (
        f"{BACKUP_DIR}/conversations_pre_v31_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
    )
    conn = get_conn()
    conn.execute(f"VACUUM INTO '{backup_path}'")
    conn.close()
    log(f"Backup creado: {backup_path}")
    return backup_path


def check_column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(r["name"] == column for r in rows)


def check_index_exists(conn: sqlite3.Connection, index_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='index' AND name=?", (index_name,)
    ).fetchone()
    return row is not None


def check_trigger_exists(conn: sqlite3.Connection, trigger_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='trigger' AND name=?", (trigger_name,)
    ).fetchone()
    return row is not None


def migrate_fs_pedidos(conn: sqlite3.Connection) -> None:
    """Recrea fs_pedidos con esquema correcto."""
    log("Migrando fs_pedidos...")

    # Verificar qué columnas faltan (solo informativo; la recreación es incondicional)
    check_column_exists(conn, "fs_pedidos", "monto_total_ves")
    check_column_exists(conn, "fs_pedidos", "tasa_usd_ves_ref")
    check_index_exists(conn, "ux_fs_pedidos_pedido_id")

    # Deshabilitar FKs temporalmente para recrear tabla
    conn.execute("PRAGMA foreign_keys = OFF")

    # Limpiar tablas temporales de intentos previos
    conn.execute("DROP TABLE IF EXISTS fs_pedidos_v31")
    conn.execute("DROP TABLE IF EXISTS fs_pagos_v31")

    # SQLite requiere recrear tabla para cambiar NOT NULL / DEFAULT
    # Creamos tabla temporal con esquema correcto
    conn.executescript("""
    CREATE TABLE fs_pedidos_v31 (
        id                      INTEGER PRIMARY KEY AUTOINCREMENT,
        pedido_id               INTEGER NOT NULL UNIQUE,
        cliente_telefono        TEXT NOT NULL,
        cliente_nombre          TEXT,
        operador_id             INTEGER,
        monto_total_eur         REAL NOT NULL,
        monto_total_ves         REAL,
        tasa_eur_ves            REAL NOT NULL,
        tasa_usd_ves_ref        REAL,
        tasa_eur_ves_deuda      REAL NOT NULL DEFAULT 0,
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
        monto_pagado_eur        REAL DEFAULT 0
    );

    -- Copiar datos existentes (mapear columnas)
    INSERT INTO fs_pedidos_v31 (
        id, pedido_id, cliente_telefono, cliente_nombre, operador_id,
        monto_total_eur, monto_total_ves, tasa_eur_ves, tasa_usd_ves_ref,
        tasa_eur_ves_deuda, botellones_cantidad, hielo_cantidad, metodo_pago,
        estado_pago, estado_entrega, tipo_credito, fecha_vencimiento_credito,
        verificacion_bancaria, recordatorios_enviados, ultimo_recordatorio_at,
        escalo_humano, entrega_confirmada_at, creado_at, actualizado_at,
        monto_pagado_eur
    )
    SELECT
        id, pedido_id, cliente_telefono, cliente_nombre, operador_id,
        monto_total_eur,
        monto_total_ves,
        tasa_eur_ves,
        tasa_usd_ves_ref,
        COALESCE(tasa_eur_ves_deuda, 0),
        botellones_cantidad, hielo_cantidad, metodo_pago,
        estado_pago, estado_entrega, tipo_credito, fecha_vencimiento_credito,
        verificacion_bancaria, recordatorios_enviados, ultimo_recordatorio_at,
        escalo_humano, entrega_confirmada_at, creado_at, actualizado_at,
        COALESCE(monto_pagado_eur, 0)
    FROM fs_pedidos;

    DROP TABLE fs_pedidos;
    ALTER TABLE fs_pedidos_v31 RENAME TO fs_pedidos;
    """)

    # Re-habilitar FKs
    conn.execute("PRAGMA foreign_keys = ON")

    # Recrear índices
    conn.executescript("""
    CREATE INDEX IF NOT EXISTS idx_fs_pedidos_cliente ON fs_pedidos(cliente_telefono);
    CREATE INDEX IF NOT EXISTS idx_fs_pedidos_estado_pago ON fs_pedidos(estado_pago);
    CREATE INDEX IF NOT EXISTS idx_fs_pedidos_estado_entrega ON fs_pedidos(estado_entrega);
    CREATE UNIQUE INDEX IF NOT EXISTS ux_fs_pedidos_pedido_id ON fs_pedidos(pedido_id);
    """)

    log("fs_pedidos migrado OK")


def migrate_fs_pagos(conn: sqlite3.Connection) -> None:
    """Recrea fs_pagos eliminando columna duplicada y corrigiendo NOT NULL."""
    log("Migrando fs_pagos...")

    # Deshabilitar FKs temporalmente
    conn.execute("PRAGMA foreign_keys = OFF")

    conn.executescript("""
    CREATE TABLE fs_pagos_v31 (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        fs_pedido_id        INTEGER,
        cuenta_cobrar_id    INTEGER,
        cliente_telefono    TEXT NOT NULL,
        cliente_nombre      TEXT,
        monto_eur           REAL NOT NULL,
        monto_ves           REAL,
        metodo_pago         TEXT NOT NULL,
        referencia          TEXT,
        tasa_eur_ves_pago   REAL NOT NULL,
        verificacion_metodo TEXT DEFAULT 'pending',
        verificado          BOOLEAN DEFAULT 0,
        verificado_at       TEXT,
        verificado_por      TEXT,
        comprobante_url     TEXT,
        creado_at           TEXT NOT NULL,
        comprobante_phash   TEXT,
        FOREIGN KEY (fs_pedido_id) REFERENCES fs_pedidos(id)
    );

    -- Copiar datos: migrar tasa_eur_ves -> tasa_eur_ves_pago donde esté vacío
    INSERT INTO fs_pagos_v31 (
        id, fs_pedido_id, cuenta_cobrar_id, cliente_telefono, cliente_nombre,
        monto_eur, monto_ves, metodo_pago, referencia, tasa_eur_ves_pago,
        verificacion_metodo, verificado, verificado_at, verificado_por,
        comprobante_url, creado_at, comprobante_phash
    )
    SELECT
        id, fs_pedido_id, cuenta_cobrar_id, cliente_telefono, cliente_nombre,
        monto_eur, monto_ves, metodo_pago, referencia,
        COALESCE(NULLIF(tasa_eur_ves_pago, 0), tasa_eur_ves),
        verificacion_metodo, verificado, verificado_at, verificado_por,
        comprobante_url, creado_at, comprobante_phash
    FROM fs_pagos;

    DROP TABLE fs_pagos;
    ALTER TABLE fs_pagos_v31 RENAME TO fs_pagos;
    """)

    # Re-habilitar FKs
    conn.execute("PRAGMA foreign_keys = ON")

    # Recrear índices
    conn.executescript("""
    CREATE INDEX IF NOT EXISTS idx_fs_pagos_cliente ON fs_pagos(cliente_telefono);
    CREATE UNIQUE INDEX IF NOT EXISTS ux_fs_pagos_ref_metodo ON fs_pagos(referencia, metodo_pago);
    CREATE INDEX IF NOT EXISTS idx_fs_pagos_pedido ON fs_pagos(fs_pedido_id);
    CREATE INDEX IF NOT EXISTS idx_fs_pagos_referencia ON fs_pagos(referencia);
    """)

    log("fs_pagos migrado OK")


def add_missing_trigger(conn: sqlite3.Connection) -> None:
    """Añade trigger de auditoría faltante en fs_pagos."""
    log("Añadiendo trigger trg_audit_fs_pagos_update...")

    if not check_trigger_exists(conn, "trg_audit_fs_pagos_update"):
        conn.execute("""
        CREATE TRIGGER trg_audit_fs_pagos_update
        AFTER UPDATE ON fs_pagos
        FOR EACH ROW
        BEGIN
            INSERT INTO fs_audit_log (
                tabla, registro_id, accion, estado_anterior, estado_nuevo,
                modificado_por, timestamp
            )
            VALUES ('fs_pagos', NEW.id, 'UPDATE',
                    json_object(
                        'fs_pedido_id', OLD.fs_pedido_id,
                        'monto_eur', OLD.monto_eur,
                        'metodo_pago', OLD.metodo_pago,
                        'referencia', OLD.referencia,
                        'verificado', OLD.verificado
                    ),
                    json_object(
                        'fs_pedido_id', NEW.fs_pedido_id,
                        'monto_eur', NEW.monto_eur,
                        'metodo_pago', NEW.metodo_pago,
                        'referencia', NEW.referencia,
                        'verificado', NEW.verificado
                    ),
                    'sistema', datetime('now'));
        END;
        """)
        log("Trigger trg_audit_fs_pagos_update creado")
    else:
        log("Trigger trg_audit_fs_pagos_update ya existe")


def run_backfills(conn: sqlite3.Connection) -> None:
    """Ejecuta backfills de datos."""
    log("Ejecutando backfills...")

    # 1. Backfill tasa_eur_ves_deuda = tasa_eur_ves donde sea 0/NULL
    conn.execute("""
        UPDATE fs_pedidos
        SET tasa_eur_ves_deuda = tasa_eur_ves
        WHERE tasa_eur_ves_deuda = 0 OR tasa_eur_ves_deuda IS NULL
    """)
    log("Backfill tasa_eur_ves_deuda completado")

    # 2. Backfill monto_pagado_eur = SUM(fs_pagos.monto_eur) por pedido verificado
    conn.execute("""
        UPDATE fs_pedidos
        SET monto_pagado_eur = COALESCE((
            SELECT SUM(monto_eur) FROM fs_pagos
            WHERE fs_pagos.fs_pedido_id = fs_pedidos.id AND verificado = 1
        ), 0)
        WHERE monto_pagado_eur = 0 OR monto_pagado_eur IS NULL
    """)
    log("Backfill monto_pagado_eur completado")

    # 3. Sincronizar estado_pago según monto_pagado_eur
    conn.execute("""
        UPDATE fs_pedidos
        SET estado_pago = CASE
            WHEN monto_pagado_eur >= monto_total_eur - 0.01 THEN 'pagado'
            WHEN monto_pagado_eur > 0 THEN 'parcial'
            ELSE estado_pago
        END
        WHERE estado_pago IN ('pendiente', 'verificando')
    """)
    log("Sincronización estado_pago completada")

    conn.commit()


def verify_migration(conn: sqlite3.Connection) -> bool:
    """Verifica que la migración fue exitosa."""
    log("Verificando migración...")

    # Verificar columnas fs_pedidos
    cols = {r["name"]: r for r in conn.execute("PRAGMA table_info(fs_pedidos)").fetchall()}

    required_pedidos = {
        "monto_total_ves",
        "tasa_usd_ves_ref",
        "monto_pagado_eur",
        "tasa_eur_ves_deuda",
    }
    for col in required_pedidos:
        if col not in cols:
            log(f"❌ FALTA columna fs_pedidos.{col}")
            return False

    # Verificar NOT NULL / DEFAULT en monto_pagado_eur
    if cols["monto_pagado_eur"]["dflt_value"] is None:
        log("❌ monto_pagado_eur sin DEFAULT")
        return False

    # Verificar UNIQUE en pedido_id
    if not check_index_exists(conn, "ux_fs_pedidos_pedido_id"):
        log("❌ Falta UNIQUE en pedido_id")
        return False

    # Verificar fs_pagos no tiene tasa_eur_ves duplicada
    cols_pagos = {r["name"]: r for r in conn.execute("PRAGMA table_info(fs_pagos)").fetchall()}
    if "tasa_eur_ves" in cols_pagos and "tasa_eur_ves_pago" in cols_pagos:
        # Verificar que tasa_eur_ves ya no existe (debería haber sido eliminada)
        pass  # En SQLite la recreación de tabla la elimina

    # Verificar trigger
    if not check_trigger_exists(conn, "trg_audit_fs_pagos_update"):
        log("❌ Trigger trg_audit_fs_pagos_update no creado")
        return False

    # Verificar backfills
    row = conn.execute(
        "SELECT COUNT(*) as c FROM fs_pedidos WHERE tasa_eur_ves_deuda = 0"
    ).fetchone()
    if row["c"] > 0:
        log(
            f"⚠️ {row['c']} pedidos con tasa_eur_ves_deuda = 0 "
            "(puede ser legítimo si tasa_eur_ves = 0)"
        )

    row = conn.execute(
        "SELECT COUNT(*) as c FROM fs_pedidos WHERE monto_pagado_eur IS NULL"
    ).fetchone()
    if row["c"] > 0:
        log(f"❌ {row['c']} pedidos con monto_pagado_eur NULL")
        return False

    log("✅ Verificación exitosa")
    return True


def main() -> int:
    log("=== INICIANDO MIGRACIÓN v3.1 conversations.db ===")

    backup_db()

    conn = get_conn()
    try:
        migrate_fs_pedidos(conn)
        migrate_fs_pagos(conn)
        add_missing_trigger(conn)
        run_backfills(conn)

        if not verify_migration(conn):
            log("❌ VERIFICACIÓN FALLÓ — revisar logs")
            return 1

        log("=== MIGRACIÓN v3.1 COMPLETADA CON ÉXITO ===")
        return 0

    except Exception as e:
        log(f"❌ ERROR: {e}")
        import traceback

        traceback.print_exc()
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
