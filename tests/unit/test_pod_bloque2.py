#!/usr/bin/env python3
"""Tests Bloque 2: esquema POD + botón Entregado → pod_record.

Usa la DB real dispatch.db con rollback: crea un delivery de test,
llama a create_pod_record (función real del bot), verifica, y limpia.
"""
import sqlite3
import sys

sys.path.insert(0, "/mnt/ssd_trabajo/hermes-agent/skills/dispatch")
sys.path.insert(0, "/mnt/ssd_trabajo/hermes-agent")

DB = "/mnt/ssd_trabajo/hermes-agent/data/dispatch.db"
conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row

# Fixture: delivery de test (pendiente) sobre client/vehicle existentes
client = conn.execute("SELECT id FROM clients LIMIT 1").fetchone()
vehicle = conn.execute("SELECT id FROM vehicles LIMIT 1").fetchone()
cur = conn.execute(
    """INSERT INTO deliveries (dispatch_session_id, client_id, vehicle_id, order_sequence, status, bottles_full)
       VALUES (1, ?, ?, 999, 'pending', 2)""",
    (client["id"], vehicle["id"]),
)
test_delivery_id = cur.lastrowid
conn.commit()
print(f"FIXTURE: delivery test #{test_delivery_id}")

# Import función real del bot
import importlib
import telegram_bot as tb  # noqa: E402
importlib.reload(tb)

# TEST 1: botón Entregado → crea pod_record (simula el flujo del callback)
tb.update_delivery_status(test_delivery_id, "delivered")
pod_id = tb.create_pod_record(test_delivery_id)
assert pod_id, "FALLO: create_pod_record devolvió None"
print(f"TEST1_OK: pod_record #{pod_id} creado")

# TEST 2: pod_status default = pending
row = conn.execute("SELECT pod_status FROM pod_records WHERE id=?", (pod_id,)).fetchone()
assert row["pod_status"] == "pending", f"pod_status={row['pod_status']}"
print("TEST2_OK: pod_status='pending'")

# TEST 3: delivery status = delivered + pod_id/pod_status vinculados
row = conn.execute(
    "SELECT status, pod_id, pod_status FROM deliveries WHERE id=?", (test_delivery_id,)
).fetchone()
assert row["status"] == "delivered", f"status={row['status']}"
assert row["pod_id"] == pod_id, f"pod_id={row['pod_id']} != {pod_id}"
assert row["pod_status"] == "pending"
print("TEST3_OK: delivery delivered + vinculado a POD")

# TEST 4: idempotencia (segundo clic no duplica)
pod_id2 = tb.create_pod_record(test_delivery_id)
assert pod_id2 == pod_id, f"no idempotente: {pod_id2} != {pod_id}"
count = conn.execute(
    "SELECT COUNT(*) c FROM pod_records WHERE delivery_id=?", (test_delivery_id,)
).fetchone()["c"]
assert count == 1, f"{count} pods duplicados"
print("TEST4_OK: idempotente")

# TEST 5: JOIN deliveries + pod_records + clients
row = conn.execute(
    """SELECT d.id, p.id pod, c.name FROM deliveries d
       JOIN pod_records p ON p.delivery_id=d.id
       JOIN clients c ON c.id=d.client_id WHERE d.id=?""",
    (test_delivery_id,),
).fetchone()
assert row and row["pod"] == pod_id and row["name"]
print(f"TEST5_OK: join ok (cliente={row['name']})")

# Cleanup
conn.execute("DELETE FROM pod_records WHERE id=?", (pod_id,))
conn.execute("DELETE FROM deliveries WHERE id=?", (test_delivery_id,))
conn.commit()
left = conn.execute(
    "SELECT COUNT(*) c FROM pod_records WHERE delivery_id=?", (test_delivery_id,)
).fetchone()["c"]
assert left == 0
conn.close()
print("CLEANUP_OK")
print("ALL_POD_TESTS_PASSED")
