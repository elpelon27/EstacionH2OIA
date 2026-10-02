#!/usr/bin/env python3
"""Tests Bloque 2 Fase 2.3: endpoints bridge para POD (GET/POST/status)."""
import base64
import os
import sqlite3
import sys
import tempfile

os.environ["POD_VEHICLE_TOKEN"] = "test-token-bloque2"
# Worktree-safe y autonomo: root derivado de la ubicacion de ESTE archivo.
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)

# BD temporal propia del test (patron de test_bottle_tracker.py).
# Antes apuntaba a data/dispatch.db del repo => 'no such table' en worktrees
# y su fixture ensuciaba la BD compartida. pod_router.py respeta
# DISPATCH_DB_PATH (env), verificada en su fuente lineas 36-40.
_TEST_DB = os.path.join(tempfile.mkdtemp(prefix="pod_bloque2_"), "dispatch.db")
os.environ["DISPATCH_DB_PATH"] = _TEST_DB
os.environ["POD_PHOTO_DIR"] = os.path.dirname(_TEST_DB)
os.environ["POD_REVOKED_FILE"] = os.path.join(os.path.dirname(_TEST_DB), "pod_revoked.json")
DB = _TEST_DB
H = {"X-Vehicle-Token": "test-token-bloque2"}

# Si api.pod_router ya fue importado por otro test (conftest importa
# test_gps_tracker que fija DISPATCH_DB_PATH=/tmp/test_gps_tracker.db),
# el env ya no sirve: la constante quedo fijada en el modulo.
# Parchear tambien la constante del modulo si este ya vive en sys.modules.
def _redirect_pod_router_db():
    mod = sys.modules.get("api.pod_router")
    if mod is not None:
        if not hasattr(mod, "_ORIGINAL_DISPATCH_DB_PATH"):
            mod._ORIGINAL_DISPATCH_DB_PATH = mod.DISPATCH_DB_PATH
        mod.DISPATCH_DB_PATH = _TEST_DB

_redirect_pod_router_db()


def _restore_pod_router_db():
    """Restaurar la BD del router para no contaminar tests posteriores."""
    mod = sys.modules.get("api.pod_router")
    if mod is not None and hasattr(mod, "_ORIGINAL_DISPATCH_DB_PATH"):
        mod.DISPATCH_DB_PATH = mod._ORIGINAL_DISPATCH_DB_PATH
        del mod._ORIGINAL_DISPATCH_DB_PATH

# Esquema: copia FIEL del esquema real de data/dispatch.db (tronco) para las
# tablas que este test toca: clients, vehicles, deliveries + pod_records
# canonico (db/pod_schema.sql). Verificado con PRAGMA table_info 2026-10-01.
_SCHEMA_FILES = [
    os.path.join(_ROOT, "db", "pod_schema.sql"),
]
_BASE_SCHEMA = """
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

# Fixture
conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
# Crear esquema: canonico (pod_records) + tablas base
for sf in _SCHEMA_FILES:
    if os.path.exists(sf):
        conn.executescript(open(sf).read())
conn.executescript(_BASE_SCHEMA)
# Semilla: al menos un client y un vehicle para la delivery de prueba
if conn.execute("SELECT COUNT(*) c FROM clients").fetchone()["c"] == 0:
    conn.execute("INSERT INTO clients (name) VALUES ('Cliente Bloque2')")
if conn.execute("SELECT COUNT(*) c FROM vehicles").fetchone()["c"] == 0:
    conn.execute("INSERT INTO vehicles (name, operator_name) VALUES ('Vehiculo Bloque2', 'TEST')")
client = conn.execute("SELECT id FROM clients LIMIT 1").fetchone()
vehicle = conn.execute("SELECT id FROM vehicles LIMIT 1").fetchone()
cur = conn.execute(
    """INSERT INTO deliveries
       (dispatch_session_id, client_id, vehicle_id, order_sequence, status, bottles_full)
       VALUES (1, ?, ?, 998, 'pending', 3)""",
    (client["id"], vehicle["id"]),
)
did = cur.lastrowid
conn.commit()
print(f"FIXTURE: delivery #{did}")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from api.pod_router import router  # noqa: E402

app = FastAPI()
app.include_router(router)
c = TestClient(app)

# did2 se define dentro del try (TEST 4); si una prueba anterior falla,
# el finally hacia NameError: did2. Inicializar antes y limpiar solo lo creado.
did2 = None

try:
    # TEST 1: GET /api/pod/{id} devuelve datos correctos
    r = c.get(f"/api/pod/{did}", headers=H)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["delivery_id"] == did
    assert data["client_name"], data
    assert data["product_details"]["items"][0]["qty"] == 3
    assert data["product_details"]["total"] == 3.0
    assert data["pod_status"] == "pending"
    print("TEST1_OK: GET pod datos correctos")

    # TEST 1b: sin token → 401
    r = c.get(f"/api/pod/{did}")
    assert r.status_code == 401, r.text
    print("TEST1b_OK: auth 401 sin token")

    # TEST 2: POST /api/pod/submit guarda firma + foto
    fake_png = base64.b64encode(b"\x89PNG-fake-signature").decode()
    fake_jpg = base64.b64encode(b"\xff\xd8-fake-photo").decode()
    r = c.post(
        "/api/pod/submit",
        json={
            "delivery_id": did,
            "client_cedula": "V-98765432",
            "signature_canvas": fake_png,
            "photo_proof": fake_jpg,
            "empty_bottles_received": 3,
            "caps_received": 2,
            "pod_status": "signed",
        },
        headers=H,
    )
    assert r.status_code == 200, r.text
    pod_id = r.json()["pod_id"]
    assert r.json()["status"] == "ok"
    print(f"TEST2_OK: submit pod #{pod_id}")

    # Verificar en DB: firma, foto en disco, campos
    row = conn.execute("SELECT * FROM pod_records WHERE id=?", (pod_id,)).fetchone()
    assert row["signature_canvas"] == fake_png
    assert row["photo_proof"] and os.path.exists(row["photo_proof"])
    assert row["client_cedula"] == "V-98765432"
    assert row["empty_bottles_received"] == 3
    assert row["caps_received"] == 2
    assert row["pod_status"] == "signed"
    assert row["synced_to_odoo"] == 0
    print("TEST2b_OK: firma+foto persistidas, synced_to_odoo=0")

    # TEST 3: GET /api/pod/status/{id}
    r = c.get(f"/api/pod/status/{did}", headers=H)
    assert r.status_code == 200, r.text
    st = r.json()
    assert st["pod_status"] == "signed", st
    assert st["synced_to_odoo"] == 0
    print("TEST3_OK: status signed")

    # TEST 4: photo_only sin firma (cliente ausente)
    did2 = conn.execute(
        """INSERT INTO deliveries
           (dispatch_session_id, client_id, vehicle_id, order_sequence, status, bottles_full)
           VALUES (1, ?, ?, 997, 'pending', 1)""",
        (client["id"], vehicle["id"]),
    ).lastrowid
    conn.commit()
    r = c.post(
        "/api/pod/submit",
        json={"delivery_id": did2, "photo_proof": fake_jpg, "pod_status": "photo_only"},
        headers=H,
    )
    assert r.status_code == 200, r.text
    r = c.get(f"/api/pod/status/{did2}", headers=H)
    assert r.json()["pod_status"] == "photo_only"
    # refused sin foto → 400
    r = c.post(
        "/api/pod/submit",
        json={"delivery_id": did2, "pod_status": "refused"},
        headers=H,
    )
    assert r.status_code == 400, r.text
    print("TEST4_OK: photo_only/refused validaciones")

    # TEST 5: 404 entrega inexistente
    r = c.get("/api/pod/999999", headers=H)
    assert r.status_code == 404
    print("TEST5_OK: 404")

    print("ALL_POD_ENDPOINT_TESTS_PASSED")
finally:
    # Cleanup (defensivo: did2 puede no existir si fallo una prueba anterior)
    if did2 is not None:
        conn.execute("DELETE FROM pod_records WHERE delivery_id IN (?, ?)", (did, did2))
        conn.execute("DELETE FROM deliveries WHERE id IN (?, ?)", (did, did2))
    else:
        conn.execute("DELETE FROM pod_records WHERE delivery_id = ?", (did,))
        conn.execute("DELETE FROM deliveries WHERE id = ?", (did,))
    conn.commit()
    conn.close()
    _restore_pod_router_db()
    print("CLEANUP_OK")
