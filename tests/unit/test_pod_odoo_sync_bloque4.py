#!/usr/bin/env python3
"""Tests Bloque 4 Fase 4.1: worker POD → Odoo (con cleanup estricto en Odoo).

INTEGRACIÓN REAL: requiere Odoo 17 vivo (docker odoo-web) + credenciales
en infra/odoo/.env. No usa BD compartida: BD temporal propia vía helper.
"""
import json
import os
import subprocess
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)

os.environ.setdefault("ODOO_URL", "http://localhost:8069")
os.environ.setdefault("ODOO_DB", "estacion_h2o")
os.environ.setdefault("ODOO_USERNAME", "admin")
# password: desde infra/odoo/.env. Es un archivo git-ignored (credenciales),
# NO existe en worktrees: buscar en este arbol primero, luego en el tronco
# donde vive la infra real.
_ENV_CANDIDATES = [
    os.path.join(_ROOT, "infra", "odoo", ".env"),
    "/mnt/ssd_trabajo/hermes-agent/infra/odoo/.env",
]
for _env_path in _ENV_CANDIDATES:
    if os.path.exists(_env_path):
        with open(_env_path) as f:
            for line in f:
                if line.startswith("ODOO_PASSWORD"):
                    os.environ["ODOO_PASSWORD"] = line.split("=", 1)[1].strip()
        break
if not os.environ.get("ODOO_PASSWORD"):
    raise RuntimeError("ODOO_PASSWORD no encontrada: falta infra/odoo/.env (tronco)")

from tests.unit.pod_test_helper import setup_pod_test  # noqa: E402

ctx = setup_pod_test("test-token-bloque4")
conn = ctx.conn
DB = ctx.db
ODOO_DOCKER = ["docker", "exec", "-i", "odoo-web", "odoo", "shell", "-d", "estacion_h2o",
               "--no-http", "--stop-after-init"]


def odoo_shell(script: str) -> str:
    r = subprocess.run(ODOO_DOCKER, input=script, capture_output=True, text=True, timeout=180)
    return r.stdout + r.stderr


def cleanup_odoo(pod_ids: list[int]) -> str:
    """Borra en Odoo TODO lo creado para los PODs de test. Retorna salida odoo_shell.

    Nota: el script usa invoice_origin='ND-POD-{id}' (linea 212) y
    sale.order/picking origin 'POD-{id}' (linea 180); cubrir AMBOS formatos.
    Ademas buscar por partner TESTPOD para capturar residuos de corridas previas.
    """
    ids = ",".join(str(i) for i in pod_ids)
    return odoo_shell(f"""
# Limpieza por partner de test (captura residuos de corridas previas)
pt = env['res.partner'].search([('phone','like','%TESTPOD%')])
for pid in ({ids}):
    inv = env['account.move'].search(['|',('invoice_origin','like',f'ND-POD-{{pid}}'),('invoice_origin','like',f'POD-{{pid}}')])
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
    pk = env['stock.picking'].search([('origin','in',[f'POD-{{pid}}',f'ND-POD-{{pid}}'])])
    for p in pk:
        try: p.action_cancel()
        except Exception: pass
    env.cr.commit()
    if pk:
        env.cr.execute("DELETE FROM stock_move_line WHERE picking_id IN %s", [tuple(pk.ids)])
        env.cr.execute("DELETE FROM stock_move WHERE picking_id IN %s", [tuple(pk.ids)])
        env.cr.commit()
        pk.unlink()
env.cr.commit()
# Partners de test al final (dependencias borradas arriba)
if pt: pt.unlink()
env.cr.commit()
print("CLEANUP_DONE")
""")


conn = ctx.conn
client = conn.execute("SELECT id, phone FROM clients LIMIT 1").fetchone()
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


def _run_sync() -> subprocess.CompletedProcess:
    """Correr el worker contra ESTA BD temporal (env heredado + DISPATCH_DB_PATH)."""
    env = {**os.environ, "DISPATCH_DB_PATH": DB}
    return subprocess.run(
        [sys.executable, os.path.join(_ROOT, "scripts", "pod_odoo_sync.py")],
        capture_output=True, text=True, cwd=_ROOT, env=env, timeout=180,
    )


try:
    # --- TEST 1: POD signed → sync crea picking+invoice en Odoo ---
    d1, p1 = make_pod("signed")
    out = _run_sync()
    combined = out.stdout + out.stderr
    assert f"POD #{p1} sincronizado" in combined, combined
    row = conn.execute("SELECT * FROM pod_records WHERE id=?", (p1,)).fetchone()
    assert row["synced_to_odoo"] == 1 and row["odoo_invoice_id"], dict(row)
    assert row["odoo_partner_id"] and row["odoo_picking_id"]
    print("TEST1_OK: signed → picking+invoice en Odoo, synced=1")

    # --- TEST 2: POD photo_only → también sincroniza ---
    d2, p2 = make_pod("photo_only", caps=3)  # con tapas
    _run_sync()
    row = conn.execute(
        "SELECT synced_to_odoo, odoo_invoice_id FROM pod_records WHERE id=?", (p2,)
    ).fetchone()
    assert row["synced_to_odoo"] == 1 and row["odoo_invoice_id"], dict(row)
    print("TEST2_OK: photo_only + tapas → sincronizado")

    # --- TEST 3: POD refused → NO sincroniza ---
    d3, p3 = make_pod("refused")
    _run_sync()
    row = conn.execute(
        "SELECT synced_to_odoo FROM pod_records WHERE id=?", (p3,)
    ).fetchone()
    assert row["synced_to_odoo"] == 0, "refused no debe sincronizar"
    print("TEST3_OK: refused descartado")

    # --- TEST 4: idempotencia — reset synced flags y re-correr = sin duplicar ---
    conn.execute("UPDATE pod_records SET synced_to_odoo=0 WHERE id IN (?,?)", (p1, p2))
    conn.commit()
    _run_sync()
    # Buscar en Odoo cuántas invoices con ese origin hay
    n = odoo_shell(f"""
inv = env['account.move'].search([('invoice_origin','like','POD-{p1}')])
print('COUNT_INVOICES_P1:', len(inv))
""")
    assert "COUNT_INVOICES_P1: 1" in n, n  # sigue 1, no duplicó
    row = conn.execute(
        "SELECT synced_to_odoo, odoo_picking_id FROM pod_records WHERE id=?", (p1,)
    ).fetchone()
    assert row["synced_to_odoo"] == 1
    print("TEST4_OK: idempotente (re-corr ida, 1 invoice)")

    # --- TEST 5: fallo Odoo → no marca synced ---
    os.environ["ODOO_URL"] = "http://localhost:9999"  # Odoo caído
    d4, p4 = make_pod("signed")
    r = _run_sync()
    os.environ["ODOO_URL"] = os.environ.get("ODOO_URL_ORIG", "http://localhost:8069")
    row = conn.execute("SELECT synced_to_odoo FROM pod_records WHERE id=?", (p4,)).fetchone()
    assert row["synced_to_odoo"] == 0, "no debe marcar synced con Odoo caído"
    print("TEST5_OK: Odoo caído → queda pendiente, reintenta")

    print("ALL_POD_SYNC_TESTS_PASSED")
finally:
    # Cleanup DB local (BD temporal del helper)
    pods = conn.execute("SELECT id FROM pod_records WHERE client_phone='0000-TESTPOD-1'").fetchall()
    pod_ids = [p["id"] for p in pods]
    # Cleanup Odoo estricto SIEMPRE (aunque haya fallado un assert)
    if pod_ids:
        try:
            out = cleanup_odoo(pod_ids)
            if out is None or "CLEANUP_DONE" not in out:
                # No crashear el finally: dejar diagnostico para inspeccion
                print(f"ODOO_CLEANUP_INCOMPLETE pod_ids={pod_ids}: {str(out)[:400]}")
            else:
                print("ODOO_CLEANUP_DONE:", pod_ids)
        except Exception as e:
            print(f"ODOO_CLEANUP_WARN: {type(e).__name__}: {e}")
    ctx.teardown()
    print("CLEANUP_OK")
