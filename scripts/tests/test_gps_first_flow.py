#!/usr/bin/env python3
"""Tests GPS-primero: cableado de geocerca al flujo de Valentina (bridge.py).

Escenarios de la directiva:
1. Nueva conversación DENTRO de zona → pide GPS → location → menú.
2. Nueva conversación FUERA de zona → MSG_FUERA_ZONA → NO menú.
3. Conversación en curso (awaiting_payment) → NO pide GPS de nuevo.
4. Extra: primer mensaje ya es location → geocerca directa.
"""
import asyncio
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from api.bridge import (  # noqa: E402
    _clear_state,
    _get_state,
    _handle_deterministic,
    _set_state,
)
from scripts.security.geofence import check_location  # noqa: E402

TEST_PH = "+584120000001"
PH_HASH = "test_gps_first_0001"
DENTRO = (10.6725, -71.6126)  # centro Maracaibo (dentro, polígono id=3)
FUERA = (10.4806, -66.9036)   # Caracas (fuera)

passed: list[str] = []
failed: list[str] = []


def check(name: str, cond, detail: str = "") -> None:  # noqa: ANN001
    ok = bool(cond)
    (passed if ok else failed).append(name)
    mark = "✅" if ok else "❌"
    print(f"  {mark} {name} {detail}")


def state() -> str | None:
    return _get_state(PH_HASH).get("state")


msg_greeting = {"type": "text", "text": {"body": "Hola"}}

print("== TEST 1: nueva conversación DENTRO de zona ==")
_clear_state(PH_HASH)
r = asyncio.run(_handle_deterministic(
    PH_HASH, "Hola", TEST_PH, "Test Uno", msg_greeting, {}
)) or {}
check("1a saludo → estado gps_required", state() == "gps_required",
      f"state={state()}")
check("1b respuesta pide ubicación",
      "ubicación" in r.get("answer", "").lower(),
      f"answer={r.get('answer', '')[:60]}")
msg_loc = {"type": "location",
           "location": {"latitude": DENTRO[0], "longitude": DENTRO[1]}}
r = asyncio.run(_handle_deterministic(
    PH_HASH, "Mi ubicación: (coordenadas: 10.6725, -71.6126)",
    TEST_PH, "Test Uno", msg_loc, {},
)) or {}
check("1c GPS dentro → estado menu_sent", state() == "menu_sent",
      f"state={state()}")
inter = r.get("interactive") or {}
check("1d incluye menú interactivo",
      inter.get("type") == "list"
      and "Ver opciones" in inter.get("button_text", ""))
check("1e mensaje confirma zona", "zona" in r.get("answer", ""))

print("== TEST 2: nueva conversación FUERA de zona ==")
_clear_state(PH_HASH)
r = asyncio.run(_handle_deterministic(
    PH_HASH, "Buenas", TEST_PH, "Test Dos", msg_greeting, {}
)) or {}
check("2a pide GPS primero", state() == "gps_required")
msg_loc_fuera = {"type": "location",
                 "location": {"latitude": FUERA[0], "longitude": FUERA[1]}}
r = asyncio.run(_handle_deterministic(
    PH_HASH, "Mi ubicación: (coordenadas: 10.4806, -66.9036)",
    TEST_PH, "Test Dos", msg_loc_fuera, {},
)) or {}
check("2b responde MSG_FUERA_ZONA",
      "no atendemos tu zona" in r.get("answer", ""),
      f"answer={r.get('answer', '')[:60]}")
check("2c NO muestra menú", "interactive" not in r)
check("2d conversación terminada (completed)",
      state() == "completed", f"state={state()}")
chk = check_location(TEST_PH, FUERA[0], FUERA[1])
check("2e check_location reporta fuera", chk["status"] == "fuera")

print("== TEST 3: conversación en curso NO pide GPS ==")
_set_state(PH_HASH, {"state": "awaiting_payment", "total_eur": 3.0,
                     "qty_botellones": 3, "qty_hielo": 0})
r = asyncio.run(_handle_deterministic(
    PH_HASH, "1", TEST_PH, "Test Tres",
    {"type": "text", "text": {"body": "1"}}, {},
)) or {}
check("3a sigue flujo de pago (no pide GPS)",
      "pago" in r.get("answer", "").lower(),
      f"answer={r.get('answer', '')[:60]}")
check("3b estado avanzó a awaiting_qr_respuesta (rediseño Pago Móvil ágil)",
      state() == "awaiting_qr_respuesta")

print("== TEST 4 (extra): primer mensaje YA es location ==")
_clear_state(PH_HASH)
r = asyncio.run(_handle_deterministic(
    PH_HASH, "Mi ubicación: (coordenadas: 10.6725, -71.6126)",
    TEST_PH, "Test Cuatro", msg_loc, {},
)) or {}
check("4a location como 1er msg → geocerca → menú",
      state() == "menu_sent" and bool(r.get("interactive")))

# Limpieza: estado de test + fila en future_zone_customers
_clear_state(PH_HASH)
sec = sqlite3.connect("data/security.db")
sec.execute(
    "DELETE FROM future_zone_customers WHERE phone = ?",
    (TEST_PH.replace("+", ""),),
)
sec.commit()
rows = sec.execute(
    "SELECT COUNT(*) FROM future_zone_customers"
).fetchone()[0]
print(f"\nLimpieza OK: future_zone rows={rows}")

print(f"\nRESULTADO: {len(passed)} OK / {len(failed)} FALLOS")
if failed:
    print("FALLOS:", failed)
sys.exit(1 if failed else 0)
