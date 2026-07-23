#!/usr/bin/env python3
"""P1-1 — Test PHONE_REGEX en SanitizingFormatter.

Valida que el regex matchea SOLO teléfonos venezolanos reales y NO matcha
IDs, timestamps, IPs, ni otros números que aparecen en logs.
"""
import sys
import os
sys.path.insert(0, '/mnt/ssd_trabajo/hermes-agent')
os.environ['BRIDGE_ALLOW_INSECURE_SALT'] = '1'

import re

# Importar el regex de la clase
from api.bridge import SanitizingFormatter

_regex = SanitizingFormatter.PHONE_REGEX

results = []

def _test(name, text, should_match):
    matches = _regex.findall(text)
    matched = len(matches) > 0
    ok = matched == should_match
    status = "PASS" if ok else "FAIL"
    results.append((name, status, f"matched={matched} expected={should_match}"))
    print(f"  [{status}] {name}: matched={matched} expected={should_match}")


print("=" * 60)
print("P1-1 — Test PHONE_REGEX (SanitizingFormatter)")
print("=" * 60)

# --- DEBE MATCHear (teléfonos venezolanos reales) ---
print("\nDEBE MATCH (telefonos venezolanos):")
_test("con +58", "+584127110000", True)
_test("sin +58", "584127110000", True)
_test("en texto", "Pedido de +584127110000 llego", True)
_test("en log", "INFO: phone:+584127110000 order=123", True)
_test("con prefijo", "wa.me/584127110000", True)

# --- NO DEBE MATCHear (IDs, timestamps, IPs, otros) ---
print("\nNO DEBE MATCH (IDs, timestamps, IPs, otros):")
_test("order_id", "order=1234567890", False)
_test("timestamp_unix", "timestamp=1719000000", False)
_test("ip_address", "ip=172.19.0.1", False)
_test("timestamp_iso", "2026-07-22T14:33:23", False)
_test("pid", "PID=4950", False)
_test("pedido_id corto", "pedido_id=45", False)
_test("metrics number", "valentina_dify_calls_total=15", False)
_test("total_eur", "total=3.00", False)
_test("latitud", "lat=10.651", False)
_test("longitud", "lng=-71.622", False)

# --- CASOS LIMITE ---
print("\nCASOS LIMITE:")
_test("telefono muy corto", "+58412", False)
_test("telefono muy largo", "+584127110000999999", False)
_test("numero sin 58", "4127110000", False)
_test("dos telefonos", "+584121234567 +584147654321", True)
_test("telefono en URL", "https://wa.me/584127110000", True)

# Resumen
print("\n" + "=" * 60)
passed = sum(1 for _, s, _ in results if s == "PASS")
failed = sum(1 for _, s, _ in results if s == "FAIL")
print(f"RESULTADO: {passed} PASS, {failed} FAIL de {len(results)} casos")
if failed:
    print("\nFALLAS:")
    for name, status, detail in results:
        if status == "FAIL":
            print(f"  X {name}: {detail}")
    sys.exit(1)
else:
    print("\nTodos los casos PASS — PHONE_REGEX preciso")
    sys.exit(0)
