#!/usr/bin/env python3
"""
E2E — CEREBRO ÚNICO (2026-10-10)
=================================
Pruebas obligatorias de la misión:
  1. Primer mensaje tras reinicio del bridge (< 2s, menú/respuesta sin LLM — medir).
  2. Flujo completo: saludo→"1"→"3 botellones"→dirección texto→GPS→efectivo→confirmación:
     cero re-envíos de menú, cero delegaciones a Dify.
  3. Off-menu → respuesta de Dify, no toca estado.
  4. Duplicado de Meta (mismo wamid 2 veces) → segunda ignorada (dedup).
  5. Estado tras pago completado = completed → nuevo saludo → flujo limpio.
  6. Regresión: pytest de la zona (los tests se corren aparte con pytest).

Uso (contra el bridge local http://localhost:8000):
    venv/bin/python3 scripts/e2e_cerebro_unico.py [--base-url http://localhost:8000]

Diseño:
- Ejercicio en vivo de _handle_deterministic + dedup (unidad, con BD de test),
  más medición de latencia del primer mensaje contra el endpoint /health y el
  webhook simulado. NO llama a Meta en producción: los envíos se mockean.
- Requiere VALENTINA_SINGLE_BRAIN=true en el .env para las aserciones del
  camino stateless (verifica y avisa si el flag está en false).
"""

import argparse
import asyncio
import os
import sys
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE_DIR, "api"))

# BD de test — NUNCA la de producción
os.environ["SQLITE_PATH"] = "/tmp/e2e_cerebro_unico.db"
for f in (
    "/tmp/e2e_cerebro_unico.db",
    "/tmp/e2e_cerebro_unico.db-wal",
    "/tmp/e2e_cerebro_unico.db-shm",
):
    if os.path.exists(f):
        os.unlink(f)
os.environ.setdefault("LOG_SALT", "e2e-cerebro-unico-salt")

# Cargar .env de producción ANTES de importar bridge (flag + C2P_ENABLED reales)
_env_path = os.path.join(BASE_DIR, "config", ".env")
if os.path.exists(_env_path):
    for _line in open(_env_path):
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip())

import httpx  # noqa: E402

import bridge  # noqa: E402

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    RESULTS.append((name, bool(cond), detail))
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


def reset(ph: str) -> None:
    bridge._clear_state(ph)


async def det(ph: str, text: str, msg_extra: dict | None = None, phone: str = "5841410000001") -> dict | None:
    m = {"type": "text", "text": {"body": text}}
    if msg_extra:
        m.update(msg_extra)
    r = await bridge._handle_deterministic(ph, text, phone, "Cliente E2E", m, {})
    return r


async def t1_primer_mensaje(base_url: str) -> None:
    print("\n[1] Primer mensaje tras reinicio — latencia < 2s, sin LLM")
    ph = "e2et1"
    reset(ph)
    t0 = time.perf_counter()
    r = await det(ph, "Buenos días")  # con tilde — la causa raíz del incidente
    dt = time.perf_counter() - t0
    check("respuesta determinística al saludo con tilde", r is not None)
    check(f"latencia {dt*1000:.0f}ms < 2000ms", dt < 2.0, f"{dt*1000:.0f}ms")
    state = bridge._get_state(ph).get("state")
    check("estado = gps_required (GPS-primero)", state == "gps_required", f"state={state}")
    if base_url:
        t0 = time.perf_counter()
        resp = httpx.get(f"{base_url}/health", timeout=5)
        dt = time.perf_counter() - t0
        check("/health responde 200", resp.status_code == 200, f"{dt*1000:.0f}ms")


async def t2_flujo_completo() -> None:
    print("\n[2] Flujo completo — cero delegaciones a Dify, cero re-envíos de menú")
    ph = "e2et2"
    reset(ph)
    # GPS-primero: el flujo real arranca saludo → ubicación (menú) → menú-1 → qty…
    r = await det(ph, "Buenos días")
    check("saludo: determinístico", r is not None, f"state={bridge._get_state(ph).get('state')}")
    loc = {"type": "location", "location": {"latitude": 10.66, "longitude": -71.6}}
    r = await bridge._handle_deterministic(ph, "", "5841410000001", "Cliente E2E", loc, {})
    check("GPS inicial: determinístico → menu_sent", r is not None, f"state={bridge._get_state(ph).get('state')}")
    for label, txt, extra in [
        ("menu-1", "1", {"type": "interactive", "_was_interactive": True}),
        ("qty texto", "3 botellones", None),
        ("dirección texto", "Av. Siempre Viva 123, cerca del parque", None),
    ]:
        r = await det(ph, txt, extra)
        st = bridge._get_state(ph).get("state")
        check(f"{label}: determinístico", r is not None, f"state={st}")
        # El menú NO puede aparecer como respuesta DENTRO de un pedido
        # (la aserción del incidente 08:34).
        if label in ("qty texto", "dirección texto"):
            check(
                f"{label}: sin re-envío de menú dentro del pedido",
                "¿En qué puedo servirle?" not in (r or {}).get("answer", "")
                and "Ver opciones" not in str((r or {}).get("interactive", "")),
            )
    # Pago efectivo (C2P_ENABLED=true en producción → opción 3)
    r = await det(ph, "3", {"_was_interactive": True})
    st = bridge._get_state(ph).get("state")
    check(
        "efectivo: determinístico → completed",
        st in ("completed", None) and r is not None,
        f"state={st}",
    )


async def t3_offmenu_no_toca_estado() -> None:
    print("\n[3] Off-menu — respuesta de Dify stateless, no toca estado")
    ph = "e2et3"
    reset(ph)
    bridge._set_state(ph, {"state": "menu_sent"})
    r = await det(ph, "cuánto cuesta el hielo extra?")
    check("off-menu NO es determinístico (va al LLM)", r is None)
    check(
        "flag VALENTINA_SINGLE_BRAIN=true en este proceso",
        bridge.VALENTINA_SINGLE_BRAIN is True,
        f"flag={bridge.VALENTINA_SINGLE_BRAIN}",
    )
    st = bridge._get_state(ph).get("state")
    check("estado intacto tras off-menu", st == "menu_sent", f"state={st}")
    # El camino R2+R3 del webhook manda SIN conversation_id: verificamos que
    # _call_dify persiste NADA. Mockeamos el httpx client.
    captured: dict = {}

    class FakeResp:
        status_code = 200

        def json(self):
            return {"answer": "Claro, el hielo sale €1.20 la bolsa. ¿Desea ver el menú?", "conversation_id": "conv-fake"}

    class FakeClient:
        async def post(self, url, headers=None, json=None, timeout=None):
            captured["payload"] = json
            return FakeResp()

    bridge._http_client = FakeClient()
    out = await bridge._call_dify("[estado: menu_sent; cliente dice]: hola?", "5841410000001", None)
    check(
        "Dify responde (mock) o sin API key (esperado en test)",
        out is None or bool(out.get("answer")),
    )
    if "payload" in captured:
        check(
            "query con estado inyectado y SIN conversation_id",
            "estado" in captured["payload"]["query"] and "conversation_id" not in captured["payload"],
            str(captured["payload"].get("query", ""))[:60],
        )
    else:
        check("payload capturado (DIFY_API_KEY presente)", False, "sin API key → _call_dify salió antes")


async def t4_dedup() -> None:
    print("\n[4] Dedup de Meta — mismo wamid 2 veces → segunda ignorada")
    mid = f"wamid.e2e.{int(time.time())}"
    first = bridge._is_duplicate(mid)
    second = bridge._is_duplicate(mid)
    check("primera no es duplicada", first is False)
    check("segunda SÍ es duplicada (ignorada)", second is True)


async def t5_completado_reinicio() -> None:
    print("\n[5] Tras pago completado → nuevo saludo → flujo limpio")
    ph = "e2et5"
    reset(ph)
    r = await det(ph, "Buenas tardes")
    check("saludo determinístico", r is not None)
    st = bridge._get_state(ph).get("state")
    check("estado arranca en gps_required", st == "gps_required", f"state={st}")
    # completar y volver a saludar
    loc = {"type": "location", "location": {"latitude": 10.66, "longitude": -71.6}}
    await bridge._handle_deterministic(ph, "", "5841410000001", "Cliente E2E", loc, {})
    bridge._set_state(ph, {"state": "completed"})
    r = await det(ph, "Hola")
    check("post-completed: saludo vuelve a gps_required limpio", r is not None)
    check(
        "estado limpio",
        bridge._get_state(ph).get("state") == "gps_required",
        f"state={bridge._get_state(ph).get('state')}",
    )


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=os.getenv("E2E_BASE_URL", "http://localhost:8000"))
    args = parser.parse_args()

    print("=" * 60)
    print("E2E CEREBRO ÚNICO — Valentina Bridge (2026-10-10)")
    print("=" * 60)

    # cargar .env de producción para C2P_ENABLED / flag reales
    env_path = os.path.join(BASE_DIR, "config", ".env")
    if os.path.exists(env_path):
        for line in open(env_path):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())

    bridge._init_db()

    await t1_primer_mensaje(args.base_url)
    await t2_flujo_completo()
    await t3_offmenu_no_toca_estado()
    await t4_dedup()
    await t5_completado_reinicio()

    print("\n" + "=" * 60)
    failed = [r for r in RESULTS if not r[1]]
    print(f"RESULTADO: {len(RESULTS) - len(failed)}/{len(RESULTS)} PASS, {len(failed)} FAIL")
    for name, ok, detail in RESULTS:
        if not ok:
            print(f"  FAIL: {name} {detail}")
    print("=" * 60)
    sys.exit(0 if not failed else 1)


if __name__ == "__main__":
    asyncio.run(main())