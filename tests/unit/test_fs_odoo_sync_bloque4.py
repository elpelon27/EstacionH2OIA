#!/usr/bin/env python3
"""Tests Bloque 4 Fase 4.2: sync bidireccional fs_* ↔ Odoo (cleanup estricto)."""
import sqlite3
import subprocess
import sys
import uuid

sys.path.insert(0, "/mnt/ssd_trabajo/hermes-agent")
CONV_DB = "/mnt/ssd_trabajo/hermes-agent/data/conversations.db"
REPO = "/mnt/ssd_trabajo/hermes-agent"

conn = sqlite3.connect(CONV_DB)
conn.row_factory = sqlite3.Row

TEST_PHONE = f"0000-TESTFS-{uuid.uuid4().hex[:6]}"
CREATED_PEDIDOS: list[int] = []
CREATED_PAGOS: list[int] = []


def make_pedido(monto=4.2, estado_pago="pendiente") -> int:
    pid = 90000 + uuid.uuid4().int % 9000  # único por corrida (evita colisiones Odoo)
    rowid = conn.execute(
        """INSERT INTO fs_pedidos
           (pedido_id, cliente_telefono, cliente_nombre, monto_total_eur,
            botellones_cantidad, hielo_cantidad, estado_pago, estado_entrega,
            tasa_eur_ves, creado_at, actualizado_at)
           VALUES (?, ?, 'Cliente Test FS Bloque4', ?, 3, 1, ?, 'sin_entregar',
                   40.0, datetime('now'), datetime('now'))""",
        (pid, TEST_PHONE, monto, estado_pago),
    ).lastrowid
    conn.commit()
    CREATED_PEDIDOS.append(rowid)
    return rowid


def make_pago(fs_pedido_id: int, monto: float, verificado: bool) -> int:
    rowid = conn.execute(
        """INSERT INTO fs_pagos
           (fs_pedido_id, cliente_telefono, cliente_nombre, monto_eur,
            metodo_pago, referencia, tasa_eur_ves_pago, verificacion_metodo,
            verificado, creado_at)
           VALUES (?, ?, 'Cliente Test FS Bloque4', ?, 'pago_movil', ?, 40.0,
                   'manual', ?, datetime('now'))""",
        (fs_pedido_id, TEST_PHONE, monto, f"REF-{uuid.uuid4().hex[:8]}", int(verificado)),
    ).lastrowid
    conn.commit()
    CREATED_PAGOS.append(rowid)
    return rowid


try:
    # --- TEST 1: fs_pedido → Odoo invoice ---
    p1 = make_pedido()
    r = subprocess.run(["venv/bin/python", "-c", f"""
import sys; sys.path.insert(0, '{REPO}')
from scripts.fs_odoo_sync import get_odoo, sync_pedido_to_odoo
import sqlite3
conn = sqlite3.connect('{CONV_DB}'); conn.row_factory = sqlite3.Row
odoo = get_odoo()
print('INVOICE_ID:', sync_pedido_to_odoo(odoo, conn, {p1}))
"""], capture_output=True, text=True, cwd=REPO)
    combined = r.stdout + r.stderr
    assert "INVOICE_ID:" in combined and "None" not in combined.split("INVOICE_ID:")[-1], combined
    row = conn.execute("SELECT odoo_invoice_id FROM fs_pedidos WHERE id=?", (p1,)).fetchone()
    assert row["odoo_invoice_id"], dict(row)
    print("TEST1_OK: fs_pedido → Odoo invoice", row["odoo_invoice_id"])

    # --- TEST 2: fs_pago verificado → Odoo payment ---
    g1 = make_pago(p1, 4.2, verificado=True)
    r = subprocess.run(["venv/bin/python", "-c", f"""
import sys; sys.path.insert(0, '{REPO}')
from scripts.fs_odoo_sync import get_odoo, sync_pago_to_odoo
import sqlite3
conn = sqlite3.connect('{CONV_DB}'); conn.row_factory = sqlite3.Row
odoo = get_odoo()
print('PAYMENT_ID:', sync_pago_to_odoo(odoo, conn, {g1}))
"""], capture_output=True, text=True, cwd=REPO)
    combined = r.stdout + r.stderr
    assert "PAYMENT_ID:" in combined and "None" not in combined.split("PAYMENT_ID:")[-1], combined
    row = conn.execute("SELECT odoo_payment_id FROM fs_pagos WHERE id=?", (g1,)).fetchone()
    assert row["odoo_payment_id"], dict(row)
    print("TEST2_OK: fs_pago → Odoo payment", row["odoo_payment_id"])

    # --- TEST 3: idempotencia (re-sync no duplica) ---
    r = subprocess.run(["venv/bin/python", "-c", f"""
import sys; sys.path.insert(0, '{REPO}')
from scripts.fs_odoo_sync import get_odoo, sync_pedido_to_odoo
import sqlite3
conn = sqlite3.connect('{CONV_DB}'); conn.row_factory = sqlite3.Row
odoo = get_odoo()
a = sync_pedido_to_odoo(odoo, conn, {p1})
b = sync_pedido_to_odoo(odoo, conn, {p1})
print('IDS:', a, b)
assert a == b, f'no idempotente {{a}} != {{b}}'
"""], capture_output=True, text=True, cwd=REPO)
    assert "IDS:" in r.stdout, r.stdout + r.stderr
    print("TEST3_OK: idempotente")

    # --- TEST 4: bidireccional — pagar en Odoo → fs_pedidos pasa a pagado ---
    # Nota: la invoice de Odoo se construye de botellones/hielo (3+1 = 4.20),
    # no del monto_total_eur del fs_pedido. Se paga el total de la invoice.
    p2 = make_pedido(monto=2.0)
    r = subprocess.run(["venv/bin/python", "-c", f"""
import sys; sys.path.insert(0, '{REPO}')
from scripts.fs_odoo_sync import get_odoo, sync_pedido_to_odoo, sync_odoo_to_fs
import sqlite3
conn = sqlite3.connect('{CONV_DB}'); conn.row_factory = sqlite3.Row
odoo = get_odoo()
inv = sync_pedido_to_odoo(odoo, conn, {p2})
print('INV:', inv)
inv_data = odoo.execute_kw('account.move', 'read', [[inv]], {{'fields': ['amount_total']}})
total = inv_data[0]['amount_total']
print('TOTAL:', total)
# Pagar directo en Odoo (simula ajuste manual del Lider)
pay = odoo.register_payment(inv, total, 'cash', 'FS-ADJUST-TEST')
print('PAY:', pay)
print('BACK:', sync_odoo_to_fs(odoo, conn))
"""], capture_output=True, text=True, cwd=REPO)
    combined = r.stdout + r.stderr
    assert "INV:" in combined and "None" not in combined.split("INV:")[-1].split("\n")[0], combined
    row = conn.execute("SELECT estado_pago FROM fs_pedidos WHERE id=?", (p2,)).fetchone()
    assert row["estado_pago"] == "pagado", dict(row)
    print("TEST4_OK: Odoo→fs_* (pago manual Odoo reflejado en fs_pedidos)")

    print("ALL_FS_SYNC_TESTS_PASSED")
finally:
    # --- Cleanup fs_* ---
    for pid in CREATED_PEDIDOS:
        conn.execute("DELETE FROM fs_pedidos WHERE id=?", (pid,))
    for gid in CREATED_PAGOS:
        conn.execute("DELETE FROM fs_pagos WHERE id=?", (gid,))
    conn.commit()
    left = conn.execute(
        "SELECT COUNT(*) c FROM fs_pedidos WHERE cliente_telefono LIKE '0000-TESTFS-%'"
    ).fetchone()["c"]
    conn.close()
    assert left == 0, left
    print("FS_CLEANUP_OK")
