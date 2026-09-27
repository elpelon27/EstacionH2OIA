#!/usr/bin/env python3
"""Tests Bloque 5 Fase 5.1: kill-switch revocable + /revoke + /activate + /reset_pin."""
import json
import os
import sqlite3
import sys
from unittest.mock import MagicMock, patch

os.environ["POD_VEHICLE_TOKENS"] = "tok-veh1:1,tok-veh2:2"
os.environ["POD_CHOFER_PIN"] = "1379"
os.environ["POD_REVOKED_FILE"] = "/tmp/pod_revoked_test.json"
sys.path.insert(0, "/mnt/ssd_trabajo/hermes-agent")

DB = "/mnt/ssd_trabajo/hermes-agent/data/dispatch.db"

import api.pod_router as pr  # noqa: E402

# Fixture: delivery + pod offline del vehículo 1
conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
client = conn.execute("SELECT id FROM clients LIMIT 1").fetchone()
did = conn.execute(
    """INSERT INTO deliveries
       (dispatch_session_id, client_id, vehicle_id, order_sequence, status, bottles_full)
       VALUES (1, ?, 1, 992, 'delivered', 1)""",
    (client["id"],),
).lastrowid
pod_id = conn.execute(
    """INSERT INTO pod_records
       (delivery_id, client_phone, client_name, pod_status, vehicle_id, synced_to_odoo)
       VALUES (?, '0000-KS-TEST', 'Cliente KS Test', 'signed', 1, 0)""",
    (did,),
).lastrowid
conn.commit()

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

app = FastAPI()
app.include_router(pr.router)
app.include_router(pr.pwa_router)
c = TestClient(app)

try:
    if os.path.exists(pr.REVOKED_FILE):
        os.remove(pr.REVOKED_FILE)

    # TEST 1: token veh1 funciona antes de revocar
    r = c.get("/api/pod/status/1?token=tok-veh1")
    assert r.status_code == 200, r.text
    print("TEST1_OK: token veh1 válido (200) antes de revoke")

    # TEST 2: /revoke_vehicle 1 → PWA bloqueada (403) + POD comprometido
    n = pr.revoke_vehicle(1)
    assert n == 1, f"esperaba 1 POD comprometido, got {n}"
    r = c.get("/api/pod/status/1?token=tok-veh1")
    assert r.status_code == 403, f"esperaba 403, got {r.status_code}"
    r = c.get("/pod/1?token=tok-veh1")
    assert r.status_code == 403
    row = conn.execute("SELECT pod_status FROM pod_records WHERE id=?", (pod_id,)).fetchone()
    assert row["pod_status"] == "compromised", dict(row)
    with open(pr.REVOKED_FILE) as f:
        state = json.loads(f.read())
    assert "1" in state["revoked"]
    print("TEST2_OK: revoke → 403 en PWA y API + POD 'compromised'")

    # TEST 3: otro vehículo no afectado
    r = c.get("/api/pod/status/2?token=tok-veh2")
    assert r.status_code == 200, r.text
    print("TEST3_OK: vehículo 2 sigue operativo")

    # TEST 4: /activate_vehicle 1 → PWA reactivada
    ok = pr.activate_vehicle(1)
    assert ok
    r = c.get("/api/pod/status/1?token=tok-veh1")
    assert r.status_code == 200, r.status_code
    print("TEST4_OK: activate → token vuelve a validar (200)")

    # TEST 5: activate de no-revocado → False
    assert pr.activate_vehicle(99) is False
    print("TEST5_OK: activate sin revoke → False")

    # TEST 6: PIN bloqueado → reset_pin desbloquea
    for _ in range(3):
        c.post("/api/pod/pin/1?token=tok-veh1", json={"pin": "0000"})
    r = c.post("/api/pod/pin/1?token=tok-veh1", json={"pin": "1379"})
    assert r.status_code == 423, r.text  # bloqueado
    pr.reset_pin(1)
    r = c.post("/api/pod/pin/1?token=tok-veh1", json={"pin": "1379"})
    assert r.status_code == 200, r.text  # desbloqueado
    print("TEST6_OK: PIN bloqueado → /reset_pin desbloquea")

    # TEST 7: comandos registrados en el bot + guard
    import skills.client_commands as cc

    fake_app = MagicMock()
    cc.register_client_handlers(fake_app)
    cmds = []
    for call in fake_app.add_handler.call_args_list:
        cmds.extend(getattr(call.args[0], "commands", frozenset()))
    for expected in ("revoke_vehicle", "activate_vehicle", "reset_pin", "resumen"):
        assert expected in cmds, f"falta {expected}: {cmds}"
    print("TEST7_OK: 9 comandos registrados (incl. kill-switch)")

    import asyncio

    async def t():
        upd = MagicMock()
        upd.effective_chat.id = 12345
        ctx = MagicMock()
        ctx.args = ["1"]
        with patch("skills.client_commands._reply") as mr:
            await cc.cmd_revoke_vehicle(upd, ctx)
            mr.assert_not_called()

    asyncio.run(t())
    print("TEST8_OK: guard bloquea no-Líder en kill-switch")

    print("ALL_KILLSWITCH_TESTS_PASSED")
finally:
    conn.execute("DELETE FROM pod_records WHERE id=?", (pod_id,))
    conn.execute("DELETE FROM deliveries WHERE id=?", (did,))
    conn.commit()
    conn.close()
    if os.path.exists(pr.REVOKED_FILE):
        os.remove(pr.REVOKED_FILE)
    print("CLEANUP_OK")
