#!/usr/bin/env python3
"""Tests del parser Whatsscanbot (DT-WSIMPORT 2B). Ejecutar directo."""

from __future__ import annotations

import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import parser as wsp  # noqa: A004,E402

FAIL = 0


def check(name: str, cond: bool, extra: str = "") -> None:
    global FAIL
    status = "OK " if cond else "FAIL"
    if not cond:
        FAIL += 1
    print(f"[{status}] {name} {extra}")


# ── Test 1: parse_paste con formatos múltiples ─────────────────────────
SAMPLE = """[12/09/2026, 15:30] Luis Martinez: Hola, quiero 2 botellones
[12/09/2026, 15:31] +58 412-1234567: Buenas tardes, sí disponible
[12/09/2026, 15:32] Luis Martinez: Cuánto sale el envío?
línea de continuación del mensaje anterior
[12/09/26, 3:35 PM] Maria: Ya hice la transferencia de 20 EUR
12/09/2026, 15:40 - Pedro: El pedido llegó perfecto
[15:30, 12/09/2024] Ana: Tengo un problema, no llegó mi pedido
2026-09-12, 16:00 - Yo: Confirmado, entrega mañana
"""
res = wsp.parse_paste(SAMPLE)
check("paste: 7 mensajes", len(res.messages) == 7, f"got {len(res.messages)}")
check("paste: multilinea anexada",
      "línea de continuación" in res.messages[2].text)
check("paste: bracket 2026", res.messages[0].timestamp == "2026-09-12T15:30:00")
check("paste: AM/PM", res.messages[3].timestamp == "2026-09-12T15:35:00",
      res.messages[3].timestamp or "")
check("paste: dash corto", res.messages[4].sender == "Pedro")
check("paste: time-first", res.messages[5].timestamp == "2024-09-12T15:30:00")
check("paste: ISO dash", res.messages[6].message_type == "text")
check("paste: phone extraído",
      res.contact_phone == "+584121234567", str(res.contact_phone))
check("paste: sender out", res.messages[7 - 1].direction == "out")

# ── Test 2: parse_txt con archivo de ejemplo ───────────────────────────
with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False,
                                 encoding="utf-8") as f:
    f.write(SAMPLE)
    tmp = f.name
res2 = wsp.parse_txt(tmp)
check("txt: 7 mensajes", len(res2.messages) == 7)
check("txt: contact_name del filename", res2.contact_name != "")
Path(tmp).unlink()

# ── Test 3: parse_zip mock ────────────────────────────────────────────
chat_a = "[01/09/2026, 10:00] +58 424-5556677: Buenos días, necesito 3 garrafas\n[01/09/2026, 10:05] Yo: Claro, va para la tarde\n"
chat_b = "[02/09/2026, 11:00] Ana Perez: Pago hecho por PagoMovil\n"
with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as zf:
    with zipfile.ZipFile(zf, "w") as z:
        z.writestr("+58 424 555 6677/WhatsApp Chat with Luis/_chat.txt", chat_a)
        z.writestr("Ana Perez/_chat.txt", chat_b)
    zpath = zf.name
exports = wsp.parse_zip(zpath)
Path(zpath).unlink()
check("zip: 2 exports", len(exports) == 2, f"got {len(exports)}")
ea = next(e for e in exports if "555" in e.contact_name or e.contact_phone)
check("zip: phone de carpeta", ea.contact_phone == "+584245556677",
      str(ea.contact_phone))
check("zip: 2 msgs en chat A", len(ea.messages) == 2)
check("zip: hash dedup", ea.messages[0].msg_hash != ea.messages[1].msg_hash)
eb = next(e for e in exports if e.contact_name == "Ana Perez")
check("zip: Ana 1 msg", len(eb.messages) == 1)

# ── Test 4: normalize_phone ────────────────────────────────────────────
check("norm: 0412", wsp.normalize_phone("0412-1234567") == "+584121234567")
check("norm: +58", wsp.normalize_phone("+58 412 123 4567") == "+584121234567")
check("norm: raro", wsp.normalize_phone("hola") is None)

print()
if FAIL:
    print(f"❌ {FAIL} tests FALLARON")
    sys.exit(1)
print("✅ Todos los tests del parser OK (2B)")
