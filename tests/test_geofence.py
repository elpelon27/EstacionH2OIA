#!/usr/bin/env python3
"""Tests FASE 2: geocerca poligonal."""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "security"))
import geofence as gf  # noqa: E402

PASS, FAIL = 0, 0


def check(name, cond):
    global PASS, FAIL
    print(f"  [{'OK' if cond else 'FAIL'}] {name}")
    PASS, FAIL = PASS + (cond is True or cond == True), FAIL + (not cond)


# Polígono de prueba: cuadrado alrededor de Caracas (Chacao/El Rosal)
POLY = {
    "type": "Polygon",
    "coordinates": [[
        [-66.880, 10.490], [-66.820, 10.490],
        [-66.820, 10.530], [-66.880, 10.530], [-66.880, 10.490]
    ]]
}


def main():
    gf.DB_PATH = Path("/tmp/security_test_geofence.db")
    if gf.DB_PATH.exists():
        gf.DB_PATH.unlink()
    gf.init_db()

    print("1) Punto dentro/fuera del polígono (ray casting)")
    # El Rosal (dentro)
    check("dentro: El Rosal", gf.is_inside_polygon(10.500, -66.850, POLY["coordinates"]))
    # Maracaibo (fuera, lejos)
    check("fuera: Maracaibo", not gf.is_inside_polygon(10.65, -71.65, POLY["coordinates"]))
    # San Cristóbal (fuera)
    check("fuera: San Cristóbal", not gf.is_inside_polygon(7.77, -72.23, POLY["coordinates"]))
    # punto justo en el borde norte
    check("borde superior (dentro por cierre)", gf.is_inside_polygon(10.529, -66.850, POLY["coordinates"]))

    print("2) Polígono activo / desactivado")
    check("sin polígono activo → sin_geocerca",
          gf.check_location("584121234567", 10.5, -66.85)["status"] == "sin_geocerca")
    pid = gf.set_polygon("zona_caracas_test", POLY, activate=True)
    check("set_polygon devuelve id", isinstance(pid, int) and pid > 0)
    poly = gf.get_active_polygon()
    check("polígono activo existe", poly is not None and poly["name"] == "zona_caracas_test")

    print("3) check_location dentro/fuera")
    r = gf.check_location("+58 412-1234567", 10.500, -66.850)
    check("dentro → ok, sin mensaje", r["status"] == "ok" and r["message"] is None)
    r = gf.check_location("+58 412-1234567", 10.65, -71.65)  # Maracaibo
    check("fuera → mensaje de zona", r["status"] == "fuera" and isinstance(r["message"], str))
    check("mensaje contiene 'no atendemos'", "no atendemos" in r["message"].lower())

    print("4) future_zone_customers (fuera NO va a audit, se guarda aparte)")
    pend = gf.future_zone_notify_pending()
    check("1 número fuera de zona registrado", len(pend) == 1)
    check("teléfono normalizado a dígitos", pend[0]["phone"] == "584121234567")
    check("coordenadas guardadas", pend[0]["lat"] == 10.65 and pend[0]["lng"] == -71.65)
    # reenvío de la misma ubicación (idempotente)
    gf.check_location("+58 412-1234567", 10.65, -71.65)
    check("reenvío no duplica", len(gf.future_zone_notify_pending()) == 1)

    print("5) Ubicación reenviada: mismo punto, validación de punto (no en vivo)")
    r = gf.check_location("584241234567", 10.500, -66.850)
    check("ubicación reenviada dentro → aceptada", r["status"] == "ok")

    print(f"\nRESULTADO: {PASS} OK / {FAIL} FAIL")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
