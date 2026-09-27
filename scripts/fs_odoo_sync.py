#!/usr/bin/env python3
"""Sync bidireccional fs_* ↔ Odoo (Bloque 4, Fase 4.2).

fs_pedidos → Odoo invoices (dirección principal: facturas se originan local).
fs_pagos → Odoo payments. Inverso: si el Líder ajusta pago/saldo en Odoo
(payments de facturas sincronizadas), se refleja en fs_pedidos/fs_pagos.
Conflict resolution: Odoo = referencia fiscal, fs_* = referencia operacional.

Cron: */15 * * * * (logs/fs_sync.log).
"""
from __future__ import annotations

import logging
import os
import sqlite3
import sys

sys.path.insert(0, "/mnt/ssd_trabajo/hermes-agent")

from dotenv import load_dotenv  # noqa: E402

_env_before = {k: os.environ.get(k) for k in os.environ if k.startswith("ODOO_")}
load_dotenv("/mnt/ssd_trabajo/hermes-agent/config/.env")
load_dotenv("/mnt/ssd_trabajo/hermes-agent/infra/odoo/.env", override=True)
os.environ.update({k: v for k, v in _env_before.items() if v is not None})

from src.integrations.odoo.odoo_sync import OdooClient, OdooConfig  # noqa: E402

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
log = logging.getLogger("fs_odoo_sync")

CONV_DB = os.getenv(
    "CONVERSATIONS_DB_PATH", "/mnt/ssd_trabajo/hermes-agent/data/conversations.db"
)


def _ensure_columns(conn: sqlite3.Connection) -> None:
    cols_p = {r[1] for r in conn.execute("PRAGMA table_info(fs_pedidos)")}
    if "odoo_invoice_id" not in cols_p:
        conn.execute("ALTER TABLE fs_pedidos ADD COLUMN odoo_invoice_id INTEGER")
    cols_g = {r[1] for r in conn.execute("PRAGMA table_info(fs_pagos)")}
    if "odoo_payment_id" not in cols_g:
        conn.execute("ALTER TABLE fs_pagos ADD COLUMN odoo_payment_id INTEGER")
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


# ------------------------------------------------------------------
# fs_* → Odoo
# ------------------------------------------------------------------

def sync_pedido_to_odoo(odoo: OdooClient, conn: sqlite3.Connection, pedido_id: int) -> int | None:
    """fs_pedidos → Odoo invoice (crea si no existe). Retorna odoo_invoice_id."""
    p = conn.execute("SELECT * FROM fs_pedidos WHERE id = ?", (pedido_id,)).fetchone()
    if not p:
        log.error("sync_pedido: fs_pedidos #%s no existe", pedido_id)
        return None
    if "odoo_invoice_id" not in p.keys():
        _ensure_columns(conn)

    ref = f"FS-{p['pedido_id']}"
    existing = odoo.execute_kw(
        "account.move",
        "search_read",
        [[("ref", "=", ref), ("move_type", "=", "out_invoice")]],
        {"fields": ["id", "state"]},
    )
    if existing:
        inv_id = existing[0]["id"]
        if existing[0]["state"] == "draft":
            odoo.execute_kw("account.move", "action_post", [[inv_id]])
        if p["odoo_invoice_id"] != inv_id:
            conn.execute(
                "UPDATE fs_pedidos SET odoo_invoice_id=? WHERE id=?", (inv_id, pedido_id)
            )
            conn.commit()
        return int(inv_id)

    partner_id = odoo.get_or_create_partner(
        p["cliente_nombre"] or f"Cliente {p['cliente_telefono']}",
        phone=p["cliente_telefono"],
    )
    # Buscar productos por nombre (AGUA19L / HIELO7KG)
    lines = []
    for code, qty, price in (
        ("AGUA 19Lts", p["botellones_cantidad"], 1.0),
        ("HIELO 7kg", p["hielo_cantidad"], 1.2),
    ):
        if not qty:
            continue
        prod = odoo.get_product_by_name(code)
        if not prod:
            log.warning("Producto %s no encontrado en Odoo", code)
            continue
        lines.append(
            (0, 0, {"product_id": prod["id"], "quantity": qty, "price_unit": price})
        )
    if not lines:
        log.error("fs_pedidos #%s sin productos válidos — omitido", pedido_id)
        return None

    inv_id = odoo.execute_kw(
        "account.move",
        "create",
        [
            {
                "move_type": "out_invoice",
                "partner_id": partner_id,
                "ref": ref,
                "invoice_line_ids": lines,
            }
        ],
    )
    # Postear la invoice (necesaria para registrar payments contra ella)
    odoo.execute_kw("account.move", "action_post", [[inv_id]])
    conn.execute(
        "UPDATE fs_pedidos SET odoo_invoice_id=? WHERE id=?", (inv_id, pedido_id)
    )
    conn.commit()
    log.info(
        "fs_pedidos #%s → Odoo invoice %s (ref %s, %.2f EUR)",
        pedido_id, inv_id, ref, p["monto_total_eur"] or 0,
    )
    return int(inv_id)


def sync_pago_to_odoo(odoo: OdooClient, conn: sqlite3.Connection, pago_id: int) -> int | None:
    """fs_pagos → Odoo payment (crea si no existe, contra la invoice del pedido)."""
    g = conn.execute("SELECT * FROM fs_pagos WHERE id = ?", (pago_id,)).fetchone()
    if not g:
        log.error("sync_pago: fs_pagos #%s no existe", pago_id)
        return None
    if g["odoo_payment_id"]:
        return int(g["odoo_payment_id"])
    if not g["verificado"]:
        log.info("fs_pagos #%s no verificado — omitido", pago_id)
        return None

    # invoice del pedido (crear si hace falta)
    inv_id = None
    if g["fs_pedido_id"]:
        inv_id = sync_pedido_to_odoo(odoo, conn, g["fs_pedido_id"])
    if not inv_id:
        log.error("fs_pagos #%s sin invoice de pedido — omitido", pago_id)
        return None

    pay_ref = f"FSPAY-{g['id']}"
    existing = odoo.execute_kw(
        "account.payment", "search_read", [[("ref", "=", pay_ref)]], {"fields": ["id"]}
    )
    if existing:
        pay_id = existing[0]["id"]
    else:
        pay_id = odoo.register_payment(
            inv_id, float(g["monto_eur"]), g["metodo_pago"] or "pago_movil", pay_ref
        )
        if not pay_id:
            log.error("fs_pagos #%s: fallo registrando pago — reintento", pago_id)
            return None
    conn.execute(
        "UPDATE fs_pagos SET odoo_payment_id=? WHERE id=?", (pay_id, pago_id)
    )
    conn.commit()
    log.info("fs_pagos #%s → Odoo payment %s", pago_id, pay_id)
    return int(pay_id)


# ------------------------------------------------------------------
# Odoo → fs_* (ajustes manuales del Líder en Odoo)
# ------------------------------------------------------------------

def sync_odoo_to_fs(odoo: OdooClient, conn: sqlite3.Connection) -> int:
    """Refleja en fs_* pagos registrados DIRECTO en Odoo contra invoices FS-*.

    Si el Líder registra un payment en Odoo sobre una factura ref FS-<pedido>,
    y fs_pedidos sigue 'pendiente', marca el pago como verificado manual en fs_*.
    Odoo es la referencia fiscal; fs_* se alinea.
    """
    count = 0
    invoices = odoo.execute_kw(
        "account.move",
        "search_read",
        [[("ref", "=like", "FS-%"), ("move_type", "=", "out_invoice")]],
        {"fields": ["ref", "amount_residual"]},
    )
    for inv in invoices:
        ref = inv["ref"]  # FS-<pedido_id>
        try:
            pedido_num = int(ref.replace("FS-", ""))
        except ValueError:
            continue
        p = conn.execute(
            "SELECT id, estado_pago FROM fs_pedidos WHERE pedido_id = ?", (pedido_num,)
        ).fetchone()
        if not p:
            continue
        residual = float(inv["amount_residual"] or 0)
        if residual <= 0.005 and p["estado_pago"] not in ("pagado", "confirmado"):
            conn.execute(
                """UPDATE fs_pedidos SET estado_pago='pagado',
                   actualizado_at=datetime('now') WHERE id=?""",
                (p["id"],),
            )
            conn.commit()
            log.info("Odoo→fs: pedido %s pagado en Odoo (residual 0) — marcado", pedido_num)
            count += 1
    return count


def run_once() -> None:
    conn = sqlite3.connect(CONV_DB)
    conn.row_factory = sqlite3.Row
    _ensure_columns(conn)
    odoo = get_odoo()

    # Pedidos pendientes de sync (sin odoo_invoice_id, con monto)
    pend = conn.execute(
        """SELECT id FROM fs_pedidos
           WHERE odoo_invoice_id IS NULL AND monto_total_eur > 0
           ORDER BY id LIMIT 20"""
    ).fetchall()
    for row in pend:
        try:
            sync_pedido_to_odoo(odoo, conn, row["id"])
        except Exception:
            log.exception("fs_pedidos #%s falló — reintento próximo ciclo", row["id"])

    # Pagos verificados sin sync
    pagos = conn.execute(
        "SELECT id FROM fs_pagos WHERE odoo_payment_id IS NULL AND verificado=1 LIMIT 20"
    ).fetchall()
    for row in pagos:
        try:
            sync_pago_to_odoo(odoo, conn, row["id"])
        except Exception:
            log.exception("fs_pagos #%s falló — reintento próximo ciclo", row["id"])

    # Dirección inversa
    try:
        n = sync_odoo_to_fs(odoo, conn)
        if n:
            log.info("Odoo→fs: %d pedidos actualizados", n)
    except Exception:
        log.exception("sync_odoo_to_fs falló")

    conn.close()


def main() -> None:
    run_once()
    log.info("fs_odoo_sync corrida completa")


if __name__ == "__main__":
    main()
