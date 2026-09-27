#!/usr/bin/env python3
"""Worker de sincronización POD → Odoo (Bloque 4, Fase 4.1).

Cada corrida:
  1. Busca pod_records synced_to_odoo=0 y pod_status IN (signed, photo_only).
  2. Para cada POD: partner → delivery note → invoice → pago (si aplica).
  3. Marca synced_to_odoo=1/synced_at. Si Odoo falla: log, NO marca, reintenta.
Idempotente: odoo_ref en pod_records guarda el picking/invoice creado;
si ya existe, no duplica.

Cron: */5 * * * * (ver docs). Ejecutar con el venv del repo.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import sys
from datetime import datetime, timezone

sys.path.insert(0, "/mnt/ssd_trabajo/hermes-agent")

from src.integrations.odoo.odoo_sync import OdooClient, OdooConfig  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("pod_odoo_sync")

DISPATCH_DB = os.getenv(
    "DISPATCH_DB_PATH", "/mnt/ssd_trabajo/hermes-agent/data/dispatch.db"
)
CONV_DB = os.getenv(
    "CONVERSATIONS_DB_PATH", "/mnt/ssd_trabajo/hermes-agent/data/conversations.db"
)

# Columnas de idempotencia (ALTER si no existen)
_IDEMPOTENT_COLS = ("odoo_partner_id", "odoo_picking_id", "odoo_invoice_id")


def _ensure_columns(conn: sqlite3.Connection) -> None:
    cols = {r[1] for r in conn.execute("PRAGMA table_info(pod_records)")}
    for c in _IDEMPOTENT_COLS:
        if c not in cols:
            conn.execute(f"ALTER TABLE pod_records ADD COLUMN {c} INTEGER")
    conn.commit()


def get_odoo() -> OdooClient:
    cfg = OdooConfig(
        url=os.getenv("ODOO_URL", "http://localhost:8069"),
        db=os.getenv("ODOO_DB", "estacion_h2o"),
        username=os.getenv("ODOO_USERNAME", "admin"),
        password=os.getenv("ODOO_PASSWORD", ""),
    )
    client = OdooClient(cfg)
    if not client.connect():
        raise RuntimeError("No se pudo conectar a Odoo")
    return client


def _product_map(odoo: OdooClient) -> dict[str, int]:
    """default_code → product_product.id para los 4 productos POD."""
    out: dict[str, int] = {}
    for code in ("AGUA19L", "HIELO7KG", "VACIO19L", "TAPAS19L"):
        rows = odoo.execute_kw(
            "product.product",
            "search_read",
            [[("default_code", "=", code)]],
            {"fields": ["id"], "limit": 1},
        )
        if rows:
            out[code] = rows[0]["id"]
        else:
            log.warning("Producto %s no existe en Odoo — línea omitida", code)
    return out


def _build_items(pod: sqlite3.Row, pmap: dict[str, int]) -> list[dict]:
    """Líneas de la nota de entrega desde product_details_json + swap/tapas."""
    items: list[dict] = []
    details = json.loads(pod["product_details_json"] or "{}")
    for it in details.get("items", []):
        pid = pmap.get(it["code"])
        if pid and it.get("qty", 0) > 0:
            items.append(
                {
                    "product_id": pid,
                    "quantity": it["qty"],
                    "price_unit": it.get("price", 0.0),
                    "name": it["code"],
                }
            )
    # Swap: vacíos recibidos (producto sin precio)
    if pod["empty_bottles_received"] and pmap.get("VACIO19L"):
        items.append(
            {
                "product_id": pmap["VACIO19L"],
                "quantity": pod["empty_bottles_received"],
                "price_unit": 0.0,
                "name": "VACIO19L",
            }
        )
    # Tapas devueltas (control de gastos)
    if pod["caps_received"] and pmap.get("TAPAS19L"):
        items.append(
            {
                "product_id": pmap["TAPAS19L"],
                "quantity": pod["caps_received"],
                "price_unit": 0.0,
                "name": "TAPAS19L",
            }
        )
    return items


def _pago_r4_confirmado(client_phone: str) -> dict | None:
    """Busca pago confirmado en fs_pagos para el teléfono (pago inmediato)."""
    try:
        conn = sqlite3.connect(CONV_DB)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """SELECT monto_eur, referencia, metodo_pago FROM fs_pagos
               WHERE cliente_telefono = ? AND verificado = 1
               ORDER BY id DESC LIMIT 1""",
            (client_phone,),
        ).fetchone()
        conn.close()
        return dict(row) if row else None
    except Exception:
        return None


def sync_pod(odoo: OdooClient, pod: sqlite3.Row, pmap: dict[str, int],
             dconn: sqlite3.Connection) -> bool:
    """Sincroniza un POD a Odoo. True si quedó synced."""
    pod_id = pod["id"]
    phone = pod["client_phone"] or ""

    # --- a) Partner (idempotente) ---
    partner_id = pod["odoo_partner_id"]
    if not partner_id:
        partner_id = odoo.get_or_create_partner(
            pod["client_name"] or f"Cliente {phone}",
            phone=phone,
        )
        dconn.execute(
            "UPDATE pod_records SET odoo_partner_id=? WHERE id=?", (partner_id, pod_id)
        )
        dconn.commit()

    items = _build_items(pod, pmap)
    if not items:
        log.error("POD #%d sin productos válidos — descartado", pod_id)
        dconn.execute(
            "UPDATE pod_records SET synced_to_odoo=1, synced_at=? WHERE id=?",
            (datetime.now(timezone.utc).isoformat(), pod_id),
        )
        dconn.commit()
        return True

    # --- b) Delivery note (idempotente) ---
    picking_id = pod["odoo_picking_id"]
    if not picking_id:
        picking_id = odoo.create_delivery_note(
            partner_id, items, origin=f"POD-{pod_id}"
        )
        dconn.execute(
            "UPDATE pod_records SET odoo_picking_id=? WHERE id=?", (picking_id, pod_id)
        )
        dconn.commit()
        if not odoo.confirm_delivery_note(picking_id):
            log.error("POD #%d: fallo validando picking %s — reintento", pod_id, picking_id)
            return False

    # --- c) Invoice (idempotente) ---
    invoice_id = pod["odoo_invoice_id"]
    if not invoice_id:
        order_id = odoo.convert_delivery_to_invoice(
            picking_id,
            partner_vat=pod["client_cedula"] or "",
            partner_name=pod["client_name"] or "",
            partner_street="",
        )
        if order_id is None:
            log.error("POD #%d: fallo convirtiendo picking→invoice — reintento", pod_id)
            return False
        inv = odoo.execute_kw(
            "account.move",
            "search_read",
            [[("ref", "=", f"POD-{pod_id}"), ("move_type", "=", "out_invoice")]],
            {"fields": ["id"], "limit": 1},
        )
        if not inv:
            inv = odoo.execute_kw(
                "account.move",
                "search_read",
                [[("invoice_origin", "=", f"ND-POD-{pod_id}")]],
                {"fields": ["id"], "limit": 1},
            )
        if not inv:
            log.error("POD #%d: invoice creada pero no encontrada — reintento", pod_id)
            return False
        invoice_id = inv[0]["id"]
        dconn.execute(
            "UPDATE pod_records SET odoo_invoice_id=? WHERE id=?", (invoice_id, pod_id)
        )
        dconn.commit()

    # --- d) Pago inmediato si R4 confirmado ---
    pago = _pago_r4_confirmado(phone)
    if pago and pago["monto_eur"]:
        odoo.register_payment(
            invoice_id,
            float(pago["monto_eur"]),
            pago.get("metodo_pago") or "pago_movil",
            pago.get("referencia") or f"POD-{pod_id}",
        )
        log.info("POD #%d: pago %.2f registrado contra factura %s",
                 pod_id, pago["monto_eur"], invoice_id)

    # --- e) Marcar synced ---
    dconn.execute(
        "UPDATE pod_records SET synced_to_odoo=1, synced_at=? WHERE id=?",
        (datetime.now(timezone.utc).isoformat(), pod_id),
    )
    dconn.commit()
    log.info("POD #%d sincronizado: partner=%s picking=%s invoice=%s",
             pod_id, partner_id, picking_id, invoice_id)
    return True


def run_once() -> int:
    """Una corrida del worker. Retorna cuántos PODs sincronizó."""
    dconn = sqlite3.connect(DISPATCH_DB)
    dconn.row_factory = sqlite3.Row
    _ensure_columns(dconn)
    pending = dconn.execute(
        """SELECT * FROM pod_records
           WHERE synced_to_odoo = 0 AND pod_status IN ('signed', 'photo_only')"""
    ).fetchall()
    if not pending:
        dconn.close()
        return 0
    log.info("PODs pendientes de sync: %d", len(pending))
    odoo = get_odoo()
    pmap = _product_map(odoo)
    synced = 0
    for pod in pending:
        try:
            if sync_pod(odoo, pod, pmap, dconn):
                synced += 1
        except Exception:
            log.exception("POD #%s falló — se reintenta próximo ciclo", pod["id"])
    dconn.close()
    return synced


def main() -> None:
    if "--loop" in sys.argv:
        import time

        interval = int(os.getenv("POD_SYNC_INTERVAL", "300"))
        while True:
            try:
                run_once()
            except Exception:
                log.exception("Ciclo falló")
            time.sleep(interval)
    else:
        n = run_once()
        log.info("Corrida única: %d PODs sincronizados", n)


if __name__ == "__main__":
    main()
