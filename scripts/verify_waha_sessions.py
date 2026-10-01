#!/usr/bin/env python3
"""Verificacion cruzada: sesion WAHA <-> numero de chofer esperado.

Comprueba la REGLA CRITICA del Lider: cada sesion debe tener vinculado el
numero correcto del chofer, y ningun numero debe estar duplicado entre
sesiones (eso romperia la consistencia por entrega).

Uso:  python3 scripts/verify_waha_sessions.py
Sale con exit 0 si todo correcto, 1 si hay discrepancia.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# Numero esperado por sesion (fuente: directiva del Lider 2026-10-01)
ESPERADO = {
    "chofer_1": "584222560722@c.us",  # Yordanis
    "chofer_2": "584222560723@c.us",  # Evert
}


def load_api_key() -> str:
    if os.getenv("WAHA_API_KEY"):
        return os.getenv("WAHA_API_KEY", "")
    env_file = REPO / "config" / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("WAHA_API_KEY="):
                return line.split("=", 1)[1].strip()
    return ""


def main() -> int:
    base = os.getenv("WAHA_BASE_URL", "http://127.0.0.1:3000")
    key = load_api_key()
    if not key:
        print("FALTA WAHA_API_KEY (config/.env)")
        return 1

    req = urllib.request.Request(f"{base}/api/sessions")
    req.add_header("X-Api-Key", key)
    try:
        sessions = json.load(urllib.request.urlopen(req, timeout=15))
    except Exception as e:  # noqa: BLE001
        print(f"WAHA no accesible: {e}")
        return 1

    if not sessions:
        print("SIN SESIONES: ningun chofer vinculado")
        return 1

    ok = True
    for s in sessions:
        name = s.get("name")
        real = (s.get("me") or {}).get("id")
        esp = ESPERADO.get(name)
        match = real == esp and s.get("status") == "WORKING"
        if not match:
            ok = False
        print(
            "  %-9s status=%-8s esperado=%-18s real=%-18s -> %s"
            % (name, s.get("status"), esp, real, "OK" if match else "DISCREPANCIA")
        )

    nums = [(s.get("me") or {}).get("id") for s in sessions]
    if len(nums) != len(set(nums)):
        ok = False
        print("  !! dos sesiones comparten el mismo numero")

    print(
        "\nRESULTADO:",
        "AMBOS VINCULADOS Y CORRECTOS" if ok else "REVISAR",
    )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
