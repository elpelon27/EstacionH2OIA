#!/usr/bin/env python3
"""
archive_audit_log.py — Archiva registros viejos de fs_audit_log.

Mueve registros de conversations.db::fs_audit_log con edad > threshold_dias
a conversations_archive.db::fs_audit_log (crea la BD si no existe).
Luego hace DELETE + VACUUM en la BD principal.

Uso:
  python3 scripts/archive_audit_log.py --dry-run              # solo contar
  python3 scripts/archive_audit_log.py --threshold 14         # ejecutar
  python3 scripts/archive_audit_log.py --threshold 30 --dry-run

Autor: Prometeo · Piloto Automático 2026-08-24
"""

import argparse
import os
import sqlite3
from typing import Any

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAIN_DB = os.path.join(BASE_DIR, "data", "conversations.db")
ARCHIVE_DB = os.path.join(BASE_DIR, "data", "conversations_archive.db")
TABLE = "fs_audit_log"

ARCHIVE_SCHEMA = f"""
CREATE TABLE IF NOT EXISTS {TABLE} (
    id                  INTEGER PRIMARY KEY,
    tabla               TEXT NOT NULL,
    registro_id         INTEGER NOT NULL,
    accion              TEXT NOT NULL,
    estado_anterior     TEXT,
    estado_nuevo        TEXT,
    modificado_por      TEXT,
    timestamp           TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_{TABLE}_tabla_reg ON {TABLE}(tabla, registro_id);
CREATE INDEX IF NOT EXISTS idx_{TABLE}_timestamp ON {TABLE}(timestamp);
"""


def get_db_size(path: str) -> int:
    return os.path.getsize(path) if os.path.exists(path) else 0


def fmt_size(n: int) -> str:
    size: float = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}TB"


def dry_run(threshold_days: int) -> int:
    """Cuenta registros a archivar sin tocar nada."""
    conn = sqlite3.connect(MAIN_DB)
    # SQLite datetime('now', '-N days') es más robusto
    count = int(
        conn.execute(
            f"SELECT COUNT(*) FROM {TABLE} "
            f"WHERE timestamp < datetime('now', '-{threshold_days} days')"
        ).fetchone()[0]
    )
    total = int(conn.execute(f"SELECT COUNT(*) FROM {TABLE}").fetchone()[0])
    oldest, newest = conn.execute(f"SELECT MIN(timestamp), MAX(timestamp) FROM {TABLE}").fetchone()
    conn.close()

    print(f"  Total registros en {TABLE}: {total}")
    print(f"  Registros >{threshold_days} días (a archivar): {count}")
    print(f"  Registros que quedan: {total - count}")
    print(f"  Rango timestamps: {oldest} → {newest}")
    print(f"  Tamaño BD principal: {fmt_size(get_db_size(MAIN_DB))}")
    return count


def archive(threshold_days: int) -> None:
    """Ejecuta el archivado real."""
    size_before = get_db_size(MAIN_DB)
    print(f"  Tamaño conversations.db antes: {fmt_size(size_before)}")

    # 1. Crear/abrir BD de archivo y crear schema
    arch_conn = sqlite3.connect(ARCHIVE_DB)
    arch_conn.executescript(ARCHIVE_SCHEMA)
    arch_conn.commit()

    # Verificar cuántos ya hay en archivo
    existing = arch_conn.execute(f"SELECT COUNT(*) FROM {TABLE}").fetchone()[0]
    print(f"  Registros existentes en archivo: {existing}")

    # 2. Leer registros a archivar de la BD principal
    main_conn = sqlite3.connect(MAIN_DB)
    cutoff_expr = f"datetime('now', '-{threshold_days} days')"

    rows: list[tuple[Any, ...]] = main_conn.execute(
        f"SELECT id, tabla, registro_id, accion, "
        f"estado_anterior, estado_nuevo, modificado_por, timestamp "
        f"FROM {TABLE} WHERE timestamp < {cutoff_expr}"
    ).fetchall()

    count_to_archive = len(rows)
    print(f"  Registros a archivar: {count_to_archive}")

    if count_to_archive == 0:
        print("  Nada que archivar. Cancelando.")
        main_conn.close()
        arch_conn.close()
        return

    # 3. Insertar en BD de archivo
    # INSERT OR IGNORE para no duplicar si se corre múltiples veces
    arch_conn.executemany(
        f"INSERT OR IGNORE INTO {TABLE} "
        f"(id, tabla, registro_id, accion, estado_anterior, "
        f"estado_nuevo, modificado_por, timestamp) "
        f"VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    arch_conn.commit()

    archived_count = arch_conn.execute(f"SELECT COUNT(*) FROM {TABLE}").fetchone()[0]
    arch_conn.close()
    print(f"  Registros en archivo después de insert: {archived_count}")

    # 4. DELETE de la BD principal
    main_conn.execute(f"DELETE FROM {TABLE} WHERE timestamp < {cutoff_expr}")
    deleted = main_conn.total_changes
    main_conn.commit()  # commit explícito antes de VACUUM
    print(f"  Registros eliminados de conversations.db: {deleted}")
    main_conn.close()

    # 5. VACUUM en conexión nueva (autocommit mode)
    print("  Ejecutando VACUUM...")
    vacuum_conn = sqlite3.connect(MAIN_DB, isolation_level=None)
    vacuum_conn.execute("VACUUM")
    vacuum_conn.close()

    size_after = get_db_size(MAIN_DB)
    size_archive = get_db_size(ARCHIVE_DB)
    saved = size_before - size_after

    print("\n  RESULTADO:")
    print(
        f"    conversations.db:  {fmt_size(size_before)} → "
        f"{fmt_size(size_after)} (−{fmt_size(saved)})"
    )
    print(
        f"    conversations_archive.db: " f"{fmt_size(size_archive)} ({archived_count} registros)"
    )
    print(f"    Espacio recuperado: {fmt_size(saved)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Archiva fs_audit_log viejo")
    parser.add_argument("--dry-run", action="store_true", help="Solo contar, no modificar")
    parser.add_argument(
        "--threshold",
        type=int,
        default=14,
        help="Días de antigüedad para archivar (default: 14)",
    )
    args = parser.parse_args()

    print(f"\n{'=' * 60}")
    print("  ARCHIVE AUDIT LOG — Prometeo Piloto Automático")
    print(f"  Threshold: {args.threshold} días | Dry-run: {args.dry_run}")
    print(f"  BD principal:  {MAIN_DB}")
    print(f"  BD archivo:    {ARCHIVE_DB}")
    print(f"{'=' * 60}\n")

    if args.dry_run:
        count = dry_run(args.threshold)
        if count > 0:
            print(f"\n  → Dry-run OK. {count} registros listos para archivar.")
            print("  → Ejecuta sin --dry-run para archivar.")
        else:
            print(f"\n  → No hay registros >{args.threshold} días para archivar.")
        return

    archive(args.threshold)
    print("\n  ✓ Archivado completado.\n")


if __name__ == "__main__":
    main()
