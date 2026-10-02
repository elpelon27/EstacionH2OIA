#!/usr/bin/env python3
"""Tests Bloque 2 Fase 2.3: endpoints bridge para POD (GET/POST/status)."""
import base64
import os
import sqlite3
import sys
import tempfile

os.environ["POD_VEHICLE_TOKEN"] = "test-token-bloque2"
# Worktree-safe y autonomo: usar el helper comun (BD temporal + parcheo del
# router si ya fue importado). Detalle del porque en tests/unit/pod_test_helper.py.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from tests.unit.pod_test_helper import setup_pod_test  # noqa: E402

ctx = setup_pod_test("test-token-bloque2")
conn = ctx.conn
DB = ctx.db
H = {"X-Vehicle-Token": "test-token-bloque2"}

# Fixture: delivery de prueba sobre la BD temporal del helper
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
    ctx.teardown()
    print("CLEANUP_OK")
