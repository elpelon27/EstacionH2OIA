#!/usr/bin/env python3
"""Capturas reales de la PWA con Playwright (Tarea 2, Bloque final)."""
import sys

from playwright.sync_api import sync_playwright

BASE = "http://localhost:8000"
URL = f"{BASE}/pod/9999?token=h2o-pod-2026-veh1"
OUT = "/mnt/ssd_trabajo/hermes-agent/docs/screenshots"
TOKEN = "h2o-pod-2026-veh1"

with sync_playwright() as pw:
    browser = pw.chromium.launch()
    # Viewport de celular 5.5"
    ctx = browser.new_context(
        viewport={"width": 390, "height": 780},
        device_scale_factor=2,
        is_mobile=True,
        has_touch=True,
    )
    page = ctx.new_page()

    # a) Pantalla de PIN
    page.goto(URL, wait_until="networkidle")
    page.wait_for_selector("#pin-overlay", state="visible", timeout=8000)
    page.screenshot(path=f"{OUT}/pod_01_pin.png")
    print("CAPTURE_1_PIN_OK")

    # b) Ingresar PIN → pantalla de datos
    page.fill("#pin", "1379")
    page.click("#btn-pin")
    page.wait_for_selector("#app", state="visible", timeout=8000)
    page.wait_for_timeout(600)  # deja cargar datos
    page.screenshot(path=f"{OUT}/pod_02_datos.png")
    print("CAPTURE_2_DATOS_OK")

    # c) Scroll al canvas de firma + dibujar una firma real
    page.locator("#canvas").scroll_into_view_if_needed()
    box = page.locator("#canvas").bounding_box()
    assert box, "canvas no encontrado"
    # Dibujo con el "dedo" (touch): curva tipo firma
    cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    # Pointer events: simular trazos
    points = [(0.2, 0.7), (0.3, 0.3), (0.4, 0.6), (0.5, 0.25), (0.6, 0.55), (0.75, 0.35), (0.85, 0.6)]
    prev = None
    for fx, fy in points:
        x = box["x"] + box["width"] * fx
        y = box["y"] + box["height"] * fy
        if prev is None:
            page.mouse.move(x, y)
            page.mouse.down()
        else:
            # pequeños pasos para trazo continuo
            steps = 5
            for s in range(1, steps + 1):
                page.mouse.move(prev[0] + (x - prev[0]) * s / steps,
                                prev[1] + (y - prev[1]) * s / steps)
        prev = (x, y)
    page.mouse.up()
    page.wait_for_timeout(300)
    # verificar que la firma efectivamente dibujó algo
    has_draw = page.evaluate(
        "() => { const c=document.getElementById('canvas'); const d=c.getContext('2d').getImageData(0,0,c.width,c.height).data; for (let i=3;i<d.length;i+=4) if (d[i]>0) return true; return false; }"
    )
    assert has_draw, "el canvas quedo vacio — la firma no se dibujo"
    page.screenshot(path=f"{OUT}/pod_03_firma.png")
    print("CAPTURE_3_FIRMA_OK (con trazo real verificado)")

    # d) Llenar cédula y confirmar → pantalla de éxito
    page.fill("#cedula", "V-12345678")
    page.fill("#vacios", "3")
    page.fill("#tapas", "1")
    page.locator("#btn-confirmar").scroll_into_view_if_needed()
    with page.expect_response(lambda r: "/api/pod/submit" in r.url, timeout=10000) as resp_info:
        page.click("#btn-confirmar")
    assert resp_info.value.ok, "submit falló"
    page.wait_for_timeout(600)
    page.screenshot(path=f"{OUT}/pod_04_exito.png", full_page=True)
    print("CAPTURE_4_EXITO_OK")

    browser.close()
    print("ALL_CAPTURES_OK")
