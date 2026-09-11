#!/usr/bin/env python3
"""Whatsscanbot — detector de datos de producción (DT-WSIMPORT 2E).

Regex determinista sobre cada mensaje: pedidos / pagos / entregas / problemas.
NUNCA usa LLM. Extrae también montos y divisas cuando están presentes.
"""

from __future__ import annotations

import re
from typing import Any

RE_PEDIDO = re.compile(
    r"pedido|botell[oó]n|botell[oó]nes|garrafa|garraf[oó]n|garrafones|"
    r"bid[oó]n|bidones|botella|botellas|env[ií]ame|"
    r"quiero|necesito|p[aá]same",
    re.IGNORECASE,
)
RE_PAGO = re.compile(
    r"pago|pag[oó]|pagar|transferencia|transfer[ií]|pagom[oó]vil|"
    r"pago m[oó]vil|zelle|banesco|mercantil|bdv|bicentenario|"
    r"punto de venta|efectivo|cancela|bs\.?\b|usd|eur",
    re.IGNORECASE,
)
RE_ENTREGA = re.compile(
    r"entrega|entregad|recib[ií]|lleg[oó]|lle[gq][aó]|confirmo|"
    r"en camino|despachad",
    re.IGNORECASE,
)
RE_PROBLEMA = re.compile(
    r"problema|falla|no lleg[oó]|no ha llegado|reclamo|"
    r"queja|defectuoso|roto|fuga|fugando|devuelv|mal estado|"
    r"demasiado tarde|muy tarde|lleg[oó] tarde|demora|no funciona",
    re.IGNORECASE,
)
RE_MONTO = re.compile(
    r"(?P<monto>\d{1,6}(?:[.,]\d{1,2})?)\s*"
    r"(?P<divisa>eur|€|usd|\$|bs\.?|bol[ií]vares?)",
    re.IGNORECASE,
)


def detect(text: str) -> dict[str, Any]:
    """Detecta flags de producción en un mensaje. Regex puro."""
    text = text or ""
    monto_match = RE_MONTO.search(text)
    return {
        "pedido": bool(RE_PEDIDO.search(text)),
        "pago": bool(RE_PAGO.search(text)),
        "entrega": bool(RE_ENTREGA.search(text)),
        "problema": bool(RE_PROBLEMA.search(text)),
        "monto": float(monto_match.group("monto").replace(",", "."))
        if monto_match else None,
        "divisa": monto_match.group("divisa").upper() if monto_match else None,
    }


def detect_batch(messages: list[dict[str, Any]]) -> dict[str, Any]:
    """Agrega detección sobre una lista de mensajes.

    Returns: {"pedidos": N, "pagos": N, "entregas": N, "problemas": N,
              "montos": [{"monto":..,"divisa":..}], "ejemplos": {...}}
    """
    agg: dict[str, Any] = {
        "pedidos": 0, "pagos": 0, "entregas": 0, "problemas": 0,
        "montos": [], "ejemplos": {},
    }
    for m in messages:
        d = detect(m.get("message_text") or m.get("text") or "")
        if d["pedido"]:
            agg["pedidos"] += 1
            agg["ejemplos"].setdefault(
                "pedido", m.get("message_text") or m.get("text") or "")
        if d["pago"]:
            agg["pagos"] += 1
            agg["ejemplos"].setdefault(
                "pago", m.get("message_text") or m.get("text") or "")
        if d["entrega"]:
            agg["entregas"] += 1
            agg["ejemplos"].setdefault(
                "entrega", m.get("message_text") or m.get("text") or "")
        if d["problema"]:
            agg["problemas"] += 1
            agg["ejemplos"].setdefault(
                "problema", m.get("message_text") or m.get("text") or "")
        if d["monto"]:
            agg["montos"].append({"monto": d["monto"], "divisa": d["divisa"]})
    return agg
