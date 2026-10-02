#!/usr/bin/env python3
"""Tests Bloque 3: PWA servida + PIN + flujo E2E del navegador (simulado)."""
import base64
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

os.environ["POD_VEHICLE_TOKEN"] = "test-token-bloque3"
os.environ["POD_CHOFER_PIN"] = "4321"  # este test usa PIN propio

from tests.unit.pod_test_helper import setup_pod_test  # noqa: E402

ctx = setup_pod_test("test-token-bloque3")
conn = ctx.conn
DB = ctx.db

# Fixture
client = conn.execute("SELECT id FROM clients LIMIT 1").fetchone()
vehicle = conn.execute("SELECT id FROM vehicles LIMIT 1").fetchone()
did = conn.execute(
    """INSERT INTO deliveries
       (dispatch_session_id, client_id, vehicle_id, order_sequence, status, bottles_full)
       VALUES (1, ?, ?, 996, 'pending', 2)""",
    (client["id"], vehicle["id"]),
).lastrowid
conn.commit()
print(f"FIXTURE: delivery #{did}")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import api.pod_router as pr  # noqa: E402

app = FastAPI()
app.include_router(pr.router)
app.include_router(pr.pwa_router)
c = TestClient(app)

try:
    # TEST 1: PWA servida con token válido
    r = c.get(f"/pod/{did}?token=test-token-bloque3")
    assert r.status_code == 200, r.text
    assert "Proof of Delivery" in r.text and "canvas" in r.text
    print("TEST1_OK: PWA servida (HTML completo)")

    # TEST 1b: token inválido → 403/401
    r = c.get(f"/pod/{did}?token=token-malo")
    assert r.status_code in (401, 403), r.status_code
    print("TEST1b_OK: token inválido rechazado")

    # TEST 2: PIN correcto
    r = c.post(f"/api/pod/pin/{did}?token=test-token-bloque3", json={"pin": "4321"})
    assert r.status_code == 200, r.text
    print("TEST2_OK: PIN correcto aceptado")

    # TEST 2b: PIN incorrecto → 401 con contador
    r = c.post(f"/api/pod/pin/{did}?token=test-token-bloque3", json={"pin": "0000"})
    assert r.status_code == 401, r.text
    assert "1/3" in r.text, r.text
    print("TEST2b_OK: PIN incorrecto 401 (1/3)")

    # TEST 2c: 3 fallos → 423 bloqueado
    c.post(f"/api/pod/pin/{did}?token=test-token-bloque3", json={"pin": "0000"})
    r = c.post(f"/api/pod/pin/{did}?token=test-token-bloque3", json={"pin": "0000"})
    assert r.status_code == 401 and "3/3" in r.text
    r = c.post(f"/api/pod/pin/{did}?token=test-token-bloque3", json={"pin": "4321"})
    assert r.status_code == 423, r.text
    print("TEST2c_OK: bloqueado tras 3 fallos (423)")
    # Reset para el test E2E
    pr._pin_fails.pop(did or 0, None)

    # TEST 3: E2E del navegador — GET datos → submit firma+foto → status
    r = c.get(f"/api/pod/{did}?token=test-token-bloque3", headers={"X-Vehicle-Token": "test-token-bloque3"})
    assert r.status_code == 200
    datos = r.json()
    assert datos["client_name"] and datos["product_details"]["total"] == 2.0
    print("TEST3_OK: GET datos PWA")

    firma = base64.b64encode(b"\x89PNG-firma-e2e").decode()
    foto = base64.b64encode(b"\xff\xd8-foto-e2e").decode()
    r = c.post(
        "/api/pod/submit",
        json={
            "delivery_id": did,
            "client_cedula": "V-11222333",
            "signature_canvas": firma,
            "photo_proof": foto,
            "empty_bottles_received": 2,
            "caps_received": 1,
            "pod_status": "signed",
        },
        headers={"X-Vehicle-Token": "test-token-bloque3"},
    )
    assert r.status_code == 200, r.text
    pod_id = r.json()["pod_id"]
    print(f"TEST3b_OK: submit E2E pod #{pod_id}")

    row = conn.execute("SELECT * FROM pod_records WHERE id=?", (pod_id,)).fetchone()
    assert row["signature_canvas"] == firma
    assert os.path.exists(row["photo_proof"]), row["photo_proof"]
    assert row["client_cedula"] == "V-11222333"
    print("TEST3c_OK: firma+foto persistidas en disco")

    r = c.get(f"/api/pod/status/{did}?token=test-token-bloque3")
    assert r.json()["pod_status"] == "signed"
    print("TEST3d_OK: status signed")

    print("ALL_PWA_TESTS_PASSED")
finally:
    conn.execute("DELETE FROM pod_records WHERE delivery_id=?", (did,))
    conn.execute("DELETE FROM deliveries WHERE id=?", (did,))
    ctx.teardown()
    print("CLEANUP_OK")
