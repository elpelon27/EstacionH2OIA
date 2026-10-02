"""Helper comun para tests POD worktree-safe (familia A, frente R3).

Problema que resuelve (verificado 2026-10-01):
- Los tests POD hardcodeaban /mnt/ssd_trabajo/hermes-agent => en worktrees
  apuntaban a BD vacia => sqlite3.OperationalError: no such table.
- adema, api/pod_router fija DISPATCH_DB_PATH al IMPORTAR (linea 36), y
  tests/conftest.py importa test_gps_tracker ANTES, que ya cargo el router
  con otra BD. El env solo no basta si el modulo ya vive en sys.modules.

Uso (al inicio del test, ANTES de importar api.pod_router):

    from tests.unit.pod_test_helper import setup_pod_test
    ctx = setup_pod_test("test-token-XXX")   # devuelve SimpleNamespace
    ...
    ctx.teardown()                            # en el finally
"""
import os
import sqlite3
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

_ROOT = Path(__file__).resolve().parents[2]

# Esquema FIEL al real de data/dispatch.db (verificado con PRAGMA
# table_info 2026-10-01) + pod_records canonico (db/pod_schema.sql).
_SCHEMA = """
CREATE TABLE IF NOT EXISTS clients (
    id INTEGER PRIMARY KEY AUTOINCREMENT, phone TEXT, phone_hash TEXT,
    name TEXT, address_text TEXT, lat REAL, lng REAL, client_type TEXT,
    avg_bottles_per_visit INTEGER, visit_frequency TEXT, visit_days TEXT,
    priority INTEGER, zone_id INTEGER, bottle_exchange_model INTEGER,
    bottle_return_hours INTEGER, active INTEGER, notes TEXT,
    created_at REAL, updated_at REAL, is_priority INTEGER,
    is_automatic INTEGER, priority_notes TEXT
);
CREATE TABLE IF NOT EXISTS vehicles (
    id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
    operator_name TEXT, telegram_chat_id INTEGER,
    max_full_bottles INTEGER DEFAULT 30, max_empty_bottles INTEGER DEFAULT 70,
    current_full_load INTEGER DEFAULT 0, current_empty_load INTEGER DEFAULT 0,
    shift TEXT, active INTEGER DEFAULT 1,
    created_at REAL NOT NULL DEFAULT (strftime('%s','now'))
);
CREATE TABLE IF NOT EXISTS deliveries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dispatch_session_id INTEGER NOT NULL, client_id INTEGER NOT NULL,
    vehicle_id INTEGER NOT NULL, order_sequence INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending', bottles_full INTEGER DEFAULT 0,
    bottles_empty_pickup INTEGER DEFAULT 0, bottles_on_site_refill INTEGER DEFAULT 0,
    estimated_arrival REAL, actual_arrival REAL, actual_departure REAL,
    duration_seconds INTEGER, operator_notes TEXT, feedback_score INTEGER,
    created_at REAL NOT NULL DEFAULT (strftime('%s','now')),
    updated_at REAL NOT NULL DEFAULT (strftime('%s','now')),
    pod_id INTEGER, pod_status TEXT,
    FOREIGN KEY (client_id) REFERENCES clients(id),
    FOREIGN KEY (vehicle_id) REFERENCES vehicles(id)
);
"""


def setup_pod_test(token: str, seed: bool = True) -> SimpleNamespace:
    """Preparar entorno POD aislado. Llamar ANTES de importar api.pod_router.

    - BD temporal propia (tmpdir) con esquema real + pod_schema.sql canonico
    - env DISPATCH_DB_PATH/POD_PHOTO_DIR/POD_REVOKED_FILE/PDF dir redirigidos
    - parchea api.pod_router.DISPATCH_DB_PATH si ya fue importado
    - semillas: 2 clients (retail + restaurant), 2 vehicles
    """
    tmpdir = Path(tempfile.mkdtemp(prefix="pod_test_"))
    db = str(tmpdir / "dispatch.db")

    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    schema_sql = _ROOT / "db" / "pod_schema.sql"
    if schema_sql.exists():
        conn.executescript(schema_sql.read_text())

    if seed:
        conn.execute(
            "INSERT INTO clients (name, phone, client_type, address_text) "
            "VALUES ('Cliente Retail Test', '+584120000001', 'retail', 'Calle Test 1')"
        )
        conn.execute(
            "INSERT INTO clients (name, phone, client_type, address_text) "
            "VALUES ('Restaurant Nivel1 Test', '+584120000002', 'restaurant', 'Av Test 2')"
        )
        conn.execute(
            "INSERT INTO vehicles (name, operator_name) VALUES ('Triciclo T1', 'TEST1'), ('Triciclo T2', 'TEST2')"
        )
        conn.commit()

    os.environ["DISPATCH_DB_PATH"] = db
    os.environ["POD_PHOTO_DIR"] = str(tmpdir / "photos")
    os.environ["POD_REVOKED_FILE"] = str(tmpdir / "pod_revoked.json")
    os.environ.setdefault("POD_VEHICLE_TOKEN", token)
    os.environ.setdefault("POD_CHOFER_PIN", "1379")
    if _ROOT not in sys.path:
        sys.path.insert(0, str(_ROOT))

    # Parchear el router si ya fue importado (constantes fijadas al importar:
    # DISPATCH_DB_PATH linea 36, PHOTO_DIR linea 40, REVOKED_FILE linea 75)
    _patched = []
    from pathlib import Path as _P
    mod = sys.modules.get("api.pod_router")
    if mod is not None:
        mod._POD_TEST_ORIGINALS = {
            "DISPATCH_DB_PATH": getattr(mod, "DISPATCH_DB_PATH", db),
            "PHOTO_DIR": getattr(mod, "PHOTO_DIR", None),
            "REVOKED_FILE": getattr(mod, "REVOKED_FILE", None),
        }
        mod.DISPATCH_DB_PATH = db
        mod.PHOTO_DIR = _P(str(tmpdir / "photos"))
        mod.PHOTO_DIR.mkdir(parents=True, exist_ok=True)
        mod.REVOKED_FILE = _P(str(tmpdir / "pod_revoked.json"))
        _patched.append(mod)

    return SimpleNamespace(
        root=_ROOT,
        db=db,
        conn=conn,
        tmpdir=tmpdir,
        pdf_dir=tmpdir / "pdfs",
        patched_modules=_patched,
        teardown=lambda: _teardown(conn, _patched, tmpdir),
    )


def _teardown(conn, patched_modules, tmpdir: Path) -> None:
    try:
        conn.commit()
        conn.close()
    except Exception:
        pass
    for mod in patched_modules:
        try:
            originals = getattr(mod, "_POD_TEST_ORIGINALS", None)
            if originals:
                for key, val in originals.items():
                    if val is not None:
                        setattr(mod, key, val)
                del mod._POD_TEST_ORIGINALS
        except Exception:
            pass
    import shutil

    shutil.rmtree(tmpdir, ignore_errors=True)
