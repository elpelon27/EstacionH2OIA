#!/usr/bin/env python3
"""Tests Bloque 4 Fase 4.1: worker POD → Odoo (con cleanup estricto en Odoo)."""
import json
import os
import sqlite3
import subprocess
import sys

os.environ.setdefault("ODOO_URL", "http://localhost:8069")
os.environ.setdefault("ODOO_DB", "estacion_h2o")
os.environ.setdefault("ODOO_USERNAME", "admin")
# password: desde infra/odoo/.env
for line in open("/mnt/ssd_trabajo/hermes-agent/infra/odoo/.env"):
    if line.startswith("ODOO_PASSWORD"):
        os.environ["ODOO_PASSWORD"] = line.split("=", 1)[1].strip()

sys.path.insert(0, "/mnt/ssd_trabajo/hermes-agent")
DB = "/mnt/ssd_trabajo/hermes-agent/data/dispatch.db"
ODOO_DOCKER = ["docker", "exec", "-i", "odoo-web", "odoo", "shell", "-d", "estacion_h2o",
               "--no-http", "--stop-after-init"]


def odoo_shell(script: str) -> str:
    r = subprocess.run(ODOO_DOCKER, input=script, capture_output=True, text=True, timeout=180)
    return r.stdout + r.stderr


def cleanup_odoo(pod_ids: list[int]) -> None:
    """Borra en Odoo TODO lo creado para los PODs de test."""
    ids = ",".join(str(i) for i in pod_ids)
    odoo_shell(f"""
for pid in ({ids}):
    inv = env['account.move'].search([('invoice_origin','like',f'POD-{{pid}}')])
    for i in inv:
        try:
            if i.state == 'posted': i.button_draft()
        except Exception: pass
    env.cr.commit()
    if inv: inv.unlink()
    pay = env['account.payment'].search([('ref','like',f'%POD-{{pid}}%')])
    for p in pay:
        try:
            p.action_draft()
        except Exception: pass
    env.cr.commit()
    if pay: pay.unlink()
    so = env['sale.order'].search([('origin','like',f'%POD-{{pid}}%')])
    for o in so:
        if o.state != 'cancel': o._action_cancel()
    env.cr.commit()
    if so: so.unlink()
    pk = env['stock.picking'].search([('origin','=',f'POD-{{pid}}')])
    for p in pk:
        try: p.action_cancel()
        except Exception: pass
    env.cr.commit()
    if pk:
        env.cr.execute("DELETE FROM stock_move_line WHERE picking_id IN %s", [tuple(pk.ids)])
        env.cr.execute("DELETE FROM stock_move WHERE picking_id IN %s", [tuple(pk.ids)])
        env.cr.commit()
        pk.unlink()
    p = env['res.partner'].search([('phone','like','%TESTPOD%')])
    env.cr.commit()
    if p: p.unlink()
env.cr.commit()
print("CLEANUP_DONE")
""")


conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
client = conn.execute("SELECT id, phone FROM clients WHERE phone NOT LIKE '%TEST%' LIMIT 1").fetchone()
vehicle = conn.execute("SELECT id FROM vehicles LIMIT 1").fetchone()


def make_pod(status: str, caps: int = 0) -> tuple[int, int]:
    """Crea delivery + pod_record de test. Retorna (delivery_id, pod_id)."""
    did = conn.execute(
        """INSERT INTO deliveries
           (dispatch_session_id, client_id, vehicle_id, order_sequence, status, bottles_full)
           VALUES (1, ?, ?, 994, 'delivered', 2)""",
        (client["id"], vehicle["id"]),
    ).lastrowid
    details = json.dumps({"items": [{"code": "AGUA19L", "qty": 2, "price": 1.0}], "total": 2.0})
    pid = conn.execute(
        """INSERT INTO pod_records
           (delivery_id, client_phone, client_name, client_cedula,
            product_details_json, empty_bottles_received, caps_received,
            total_eur, pod_status, vehicle_id)
           VALUES (?, '0000-TESTPOD-1', 'Cliente Test POD Bloque4', 'V-999',
                   ?, 2, ?, 2.0, ?, ?)""",
        (did, details, caps, status, vehicle["id"]),
    ).lastrowid
    conn.execute("UPDATE deliveries SET pod_id=?, pod_status=? WHERE id=?", (pid, status, did))
    conn.commit()
    return did, pid


try:
    # --- TEST 1: POD signed → sync crea picking+invoice en Odoo ---
    d1, p1 = make_pod("signed")
    out = subprocess.run(
        ["venv/bin/python", "scripts/pod_odoo_sync.py"], capture_output=True, text=True, cwd="/mnt/ssd_trabajo/hermes-agent"
    )
    combined = out.stdout + out.stderr
    assert "POD #%d sincronizado" % p1 in combined, combined
    row = conn.execute("SELECT * FROM pod_records WHERE id=?", (p1,)).fetchone()
    assert row["synced_to_odoo"] == 1 and row["odoo_invoice_id"], dict(row)
    assert row["odoo_partner_id"] and row["odoo_picking_id"]
    print("TEST1_OK: signed → picking+invoice en Odoo, synced=1")

    # --- TEST 2: POD photo_only → también sincroniza ---
    d2, p2 = make_pod("photo_only", caps=3)  # con tapas
    subprocess.run(["venv/bin/python", "scripts/pod_odoo_sync.py"],
                   capture_output=True, text=True, cwd="/mnt/ssd_trabajo/hermes-agent")
    row = conn.execute("SELECT synced_to_odoo, odoo_invoice_id FROM pod_records WHERE id=?", (p2,)).fetchone()
    assert row["synced_to_odoo"] == 1 and row["odoo_invoice_id"], dict(row)
    print("TEST2_OK: photo_only + tapas → sincronizado")

    # --- TEST 3: POD refused → NO sincroniza ---
    d3, p3 = make_pod("refused")
    subprocess.run(["venv/bin/python", "scripts/pod_odoo_sync.py"],
                   capture_output=True, text=True, cwd="/mnt/ssd_trabajo/hermes-agent")
    row = conn.execute("SELECT synced_to_odoo FROM pod_records WHERE id=?", (p3,)).fetchone()
    assert row["synced_to_odoo"] == 0, "refused no debe sincronizar"
    print("TEST3_OK: refused descartado")

    # --- TEST 4: idempotencia — reset synced flags y re-correr = sin duplicar ---
    conn.execute("UPDATE pod_records SET synced_to_odoo=0 WHERE id IN (?,?)", (p1, p2))
    conn.commit()
    subprocess.run(["venv/bin/python", "scripts/pod_odoo_sync.py"],
                   capture_output=True, text=True, cwd="/mnt/ssd_trabajo/hermes-agent")
    # Buscar en Odoo cuántas invoices con ese origin hay
    n = odoo_shell(f"""
inv = env['account.move'].search([('invoice_origin','like','POD-{p1}')])
print('COUNT_INVOICES_P1:', len(inv))
""")
    assert "COUNT_INVOICES_P1: 1" in n, n  # sigue 1, no duplicó
    row = conn.execute("SELECT synced_to_odoo, odoo_picking_id FROM pod_records WHERE id=?", (p1,)).fetchone()
    assert row["synced_to_odoo"] == 1
    print("TEST4_OK: idempotente (re-corr ida, 1 invoice)")

    # --- TEST 5: fallo Odoo → no marca synced ---
    os.environ["ODOO_URL"] = "http://localhost:9999"  # Odoo caído
    d4, p4 = make_pod("signed")
    r = subprocess.run(["venv/bin/python", "scripts/pod_odoo_sync.py"],
                       capture_output=True, text=True, cwd="/mnt/ssd_trabajo/hermes-agent",
                       env={**os.environ})
    row = conn.execute("SELECT synced_to_odoo FROM pod_records WHERE id=?", (p4,)).fetchone()
    assert row["synced_to_odoo"] == 0, "no debe marcar synced con Odoo caído"
    print("TEST5_OK: Odoo caído → queda pendiente, reintenta")

    print("ALL_POD_SYNC_TESTS_PASSED")
finally:
    # Cleanup DB local
    pods = conn.execute("SELECT id FROM pod_records WHERE client_phone='0000-TESTPOD-1'").fetchall()
    pod_ids = [p["id"] for p in pods]
    dids = [r["delivery_id"] for r in conn.execute(
        "SELECT delivery_id FROM pod_records WHERE client_phone='0000-TESTPOD-1'").fetchall()]
    conn.execute("DELETE FROM pod_records WHERE client_phone='0000-TESTPOD-1'")
    if dids:
        conn.executemany("DELETE FROM deliveries WHERE id=?", [(d,) for d in dids])
    conn.commit()
    conn.close()
    # Cleanup Odoo estricto
    if pod_ids:
        out = cleanup_odoo(pod_ids)
        assert out is not None and "CLEANUP_DONE" in out, out
        print("ODOO_CLEANUP_DONE:", pod_ids)
    print("CLEANUP_OK")
