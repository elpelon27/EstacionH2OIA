#!/usr/bin/env python3
"""Test E2E odoo_sync.py — BLOQUE 1 Fase 2. Datos de test, se borran después."""
import logging, sys
sys.path.insert(0, "/mnt/ssd_trabajo/hermes-agent")
logging.basicConfig(level=logging.INFO)
from src.integrations.odoo.odoo_sync import OdooClient, OdooConfig

cfg = OdooConfig(url="http://localhost:8069", db="estacion_h2o", username="admin", password="H2O_pod_2026!sync")
odoo = OdooClient(cfg)
assert odoo.connect(), "FALLO CONEXION"

# 1. partner
pid = odoo.get_or_create_partner("Cliente Test POD", phone="0000-TEST-POD")
print("PARTNER_ID:", pid)

# 2. productos
agua = odoo.get_product_by_name("AGUA 19Lts")
hielo = odoo.get_product_by_name("HIELO 7kg")
print("AGUA:", agua and agua["id"], "HIELO:", hielo and hielo["id"])

# 3. delivery note: 3 agua + 1 hielo
items = [
    {"product_id": agua["id"], "quantity": 3, "price_unit": 1.00, "name": "AGUA 19Lts"},
    {"product_id": hielo["id"], "quantity": 1, "price_unit": 1.20, "name": "HIELO 7kg"},
]
pn = odoo.create_delivery_note(pid, items, origin="TEST-POD-001")
print("PICKING_ID:", pn)

ok = odoo.confirm_delivery_note(pn)
print("PICKING_CONFIRMED:", ok)
state = odoo.execute_kw("stock.picking", "read", [[pn]], {"fields": ["state"]})[0]["state"]
print("PICKING_STATE:", state)

# 4. convertir a invoice
so = odoo.convert_delivery_to_invoice(pn, partner_vat="V-00000000", partner_name="Cliente Test POD", partner_street="Test")
print("SALE_ORDER_ID:", so)

if not so:
    print("FALLO CONVERSION"); sys.exit(1)

inv = odoo.execute_kw("account.move", "search_read", [[("partner_id","=",pid),("move_type","=","out_invoice")]], {"fields":["id","state","amount_total","ref","invoice_origin"]})
print("INVOICES:", inv)

# 5. payment 4.40
iid = inv[0]["id"]
pay = odoo.register_payment(iid, 4.40, "pago_movil", "TEST-PAY-001")
print("PAYMENT_ID:", pay)
if pay:
    pstate = odoo.execute_kw("account.payment", "read", [[pay]], {"fields": ["state", "is_matched", "amount"]})
    print("PAYMENT_STATE:", pstate)
inv2 = odoo.execute_kw("account.move", "read", [[iid]], {"fields": ["state", "amount_residual"]})
print("INVOICE_AFTER_PAYMENT:", inv2)
print("E2E_DONE")
