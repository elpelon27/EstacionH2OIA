#!/usr/bin/env python3
"""Tests production_detector (DT-WSIMPORT 2E). Mensajes reales de ejemplo."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from production_detector import detect, detect_batch  # noqa: E402

FAIL = 0


def check(name: str, cond: bool, extra: str = "") -> None:
    global FAIL
    if not cond:
        FAIL += 1
    print(f"[{'OK ' if cond else 'FAIL'}] {name} {extra}")


# Casos positivos (estilo real Estación H2O)
d = detect("Hola, quiero pedir 3 botellones para mañana en la tarde")
check("pedido: botellones", d["pedido"])
d = detect("Envíame 2 garrafas por favor")
check("pedido: envíame garrafas", d["pedido"])
d = detect("Ya hice la transferencia de 15 euros")
check("pago: transferencia", d["pago"])
check("pago: monto 15 EUR", d["monto"] == 15.0 and d["divisa"].startswith("EUR"),
      f"{d['monto']} {d['divisa']}")
d = detect("Le pago por PagoMovil mañana, son 1200 Bs")
check("pago: pagomóvil Bs", d["pago"])
check("pago: monto 1200 BS", d["monto"] == 1200.0, str(d["monto"]))
d = detect("El pedido llegó perfecto, confirmo la entrega")
check("entrega: llegó/confirmo", d["entrega"])
d = detect("Tengo un reclamo, el garrafón vino con fuga")
check("problema: reclamo/fuga", d["problema"])
d = detect("No llegó mi pedido, ya van 3 días de demora")
check("problema: no llegó", d["problema"])
d = detect("Pago 20 EUR por Zelle")
check("pago: zelle+EUR", d["pago"] and d["monto"] == 20.0)

# Casos negativos (control de falsos positivos)
d = detect("Buenas tardes, ¿cómo estás?")
check("negativo: saludo", not any([d["pedido"], d["pago"], d["entrega"],
                                   d["problema"]]))
d = detect("Jaja ok 😂")
check("negativo: risa", not any([d["pedido"], d["pago"]]))

# Batch
msgs = [
    {"message_text": "Quiero 2 botellones"},
    {"message_text": "Transferencia hecha de 10 EUR"},
    {"message_text": "Llegó todo bien"},
    {"message_text": "Tengo un problema con el envase"},
    {"message_text": "Buenos días"},
]
agg = detect_batch(msgs)
check("batch: 1 pedido", agg["pedidos"] == 1)
check("batch: 1 pago", agg["pagos"] == 1)
check("batch: 1 entrega", agg["entregas"] == 1)
check("batch: 1 problema", agg["problemas"] == 1)
check("batch: montos", len(agg["montos"]) == 1)
check("batch: ejemplos", bool(agg["ejemplos"].get("pedido")))

print()
if FAIL:
    print(f"❌ {FAIL} tests FALLARON")
    sys.exit(1)
print("✅ Todos los tests production_detector OK (2E)")
