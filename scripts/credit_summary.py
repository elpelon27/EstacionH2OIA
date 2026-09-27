#!/usr/bin/env python3
"""Resumen semanal de crédito automático (Bloque 4, Fase 4.3).

- generate_weekly_summary(phone): texto formateado con pedidos pendientes
  de los últimos 7 días, totales EUR/VES (tasa BCV de fs_tasas_cambio).
- send_summary_via_valentina(phone, summary): Meta Cloud API (oficial).
- --weekly: envía a todos los clientes con saldo pendiente.
- --phone <num>: resumen on-demand para un cliente.

Cron: 0 8 * * 1 (lunes 8 AM, logs/credit_summary.log).
"""
from __future__ import annotations

import logging
import os
import sqlite3
import sys
import urllib.request
from datetime import datetime, timedelta

sys.path.insert(0, "/mnt/ssd_trabajo/hermes-agent")

from dotenv import load_dotenv  # noqa: E402

load_dotenv("/mnt/ssd_trabajo/hermes-agent/config/.env")

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
log = logging.getLogger("credit_summary")

CONV_DB = os.getenv(
    "CONVERSATIONS_DB_PATH", "/mnt/ssd_trabajo/hermes-agent/data/conversations.db"
)


def _tasa_bcv(conn: sqlite3.Connection) -> float | None:
    """Última tasa EUR/VES desde fs_tasas_cambio (la que alimenta al R4)."""
    try:
        row = conn.execute(
            "SELECT tasa FROM fs_tasas_cambio ORDER BY fecha DESC LIMIT 1"
        ).fetchone()
        if row:
            return float(row[0])
        row = conn.execute(
            "SELECT * FROM fs_tasas_cambio LIMIT 1"
        ).fetchone()
        if row:
            keys = row.keys()
            for name in ("tasa_eur_ves", "eur_ves", "valor"):
                if name in keys and row[name]:
                    return float(row[name])
    except Exception:
        pass
    return None


def generate_weekly_summary(phone: str) -> str | None:
    """Texto del resumen semanal de crédito para el teléfono. None si no hay deuda."""
    conn = sqlite3.connect(CONV_DB)
    conn.row_factory = sqlite3.Row
    desde = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
    pedidos = conn.execute(
        """SELECT pedido_id, cliente_nombre, creado_at, monto_total_eur,
                  botellones_cantidad, hielo_cantidad, estado_pago
           FROM fs_pedidos
           WHERE cliente_telefono = ? AND estado_pago IN ('pendiente','verificando')
           AND creado_at >= ?
           ORDER BY creado_at""",
        (phone, desde),
    ).fetchall()
    if not pedidos:
        conn.close()
        return None

    nombre = pedidos[0]["cliente_nombre"] or phone
    total_eur = sum(float(p["monto_total_eur"] or 0) for p in pedidos)
    tasa = _tasa_bcv(conn)
    total_ves = total_eur * tasa if tasa else None
    conn.close()

    fecha_ini = (datetime.now() - timedelta(days=7)).strftime("%d/%m")
    fecha_fin = datetime.now().strftime("%d/%m/%Y")
    lineas = [
        "📋 Resumen Semanal — Estación H2O 💧",
        "",
        f"Cliente: {nombre}",
        f"Período: {fecha_ini} a {fecha_fin}",
        "",
        f"Pedidos pendientes: {len(pedidos)}",
    ]
    if total_ves:
        lineas.append(
            f"Total: {total_eur:.2f} EUR ({total_ves:,.2f} VES a tasa {tasa})"
        )
    else:
        lineas.append(f"Total: {total_eur:.2f} EUR")
    lineas.append("")
    lineas.append("Detalle:")
    for i, p in enumerate(pedidos, 1):
        fecha = (p["creado_at"] or "")[:10]
        partes = []
        if p["botellones_cantidad"]:
            partes.append(f"{p['botellones_cantidad']} AGUA")
        if p["hielo_cantidad"]:
            partes.append(f"{p['hielo_cantidad']} HIELO")
        desc = " + ".join(partes) or "pedido"
        lineas.append(
            f"{i}. {fecha} — {desc} = {float(p['monto_total_eur'] or 0):.2f} EUR"
        )
    lineas += [
        "",
        f"Total a pagar: {total_eur:.2f} EUR",
        "",
        "Para pagar, respondé a este mensaje con tu comprobante de transferencia.",
    ]
    return "\n".join(lineas)


def send_summary_via_valentina(phone: str, summary: str) -> bool:
    """Envía el resumen por Meta Cloud API (oficial, NO WAHA)."""
    token = os.getenv("META_ACCESS_TOKEN", "")
    phone_id = os.getenv("META_PHONE_NUMBER_ID", "")
    if not token or not phone_id:
        log.error("Meta Cloud API no configurada (META_ACCESS_TOKEN/PHONE_NUMBER_ID)")
        return False
    # Normalizar a formato internacional sin '+' para Meta
    to = phone.lstrip("+").replace(" ", "").replace("-", "")
    import json

    payload = json.dumps(
        {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"preview_url": False, "body": summary},
        }
    )
    req = urllib.request.Request(
        f"https://graph.facebook.com/v20.0/{phone_id}/messages",
        data=payload.encode(),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            ok = resp.status == 200
        log.info("Resumen enviado a %s (Meta API ok=%s)", to, ok)
        return ok
    except Exception as e:
        log.error("Fallo enviando resumen a %s: %s", to, e)
        return False


def _json_escape(s: str) -> str:
    import json

    return json.dumps(s)


def clientes_con_deuda() -> list[tuple[str, str]]:
    """[(telefono, nombre)] con pedidos pendientes en los últimos 7 días."""
    conn = sqlite3.connect(CONV_DB)
    conn.row_factory = sqlite3.Row
    desde = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
    rows = conn.execute(
        """SELECT cliente_telefono, MAX(cliente_nombre) nombre
           FROM fs_pedidos
           WHERE estado_pago IN ('pendiente','verificando') AND creado_at >= ?
           GROUP BY cliente_telefono""",
        (desde,),
    ).fetchall()
    conn.close()
    return [(r["cliente_telefono"], r["nombre"] or "") for r in rows]


def run_weekly() -> None:
    """Envía resumen a todos los clientes con deuda (cron lunes 8 AM)."""
    destinatarios = clientes_con_deuda()
    log.info("Resumen semanal: %d clientes con deuda", len(destinatarios))
    enviados = 0
    for phone, _nombre in destinatarios:
        summary = generate_weekly_summary(phone)
        if summary and send_summary_via_valentina(phone, summary):
            enviados += 1
    log.info("Resumen semanal: %d/%d enviados", enviados, len(destinatarios))


def main() -> None:
    if "--weekly" in sys.argv:
        run_weekly()
    elif "--phone" in sys.argv:
        phone = sys.argv[sys.argv.index("--phone") + 1]
        summary = generate_weekly_summary(phone)
        if summary:
            print(summary)
            if "--send" in sys.argv:
                send_summary_via_valentina(phone, summary)
        else:
            print(f"Sin pedidos pendientes para {phone}")
    else:
        print("Uso: --weekly | --phone <num> [--send]")


if __name__ == "__main__":
    main()
