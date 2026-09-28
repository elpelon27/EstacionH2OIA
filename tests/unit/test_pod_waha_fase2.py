#!/usr/bin/env python3
"""Tests FASE 2: envío de PDF firmado vía WAHA al firmar POD.

E2E con dispatch.db real + mocks inyectados en waha_client:
  1. POST /api/pod/submit signed → genera PDF (thread)
  2. WAHA mock envía documento (captura chatId/caption/PDF base64)
  3. WAHA no conectado → fail-open: no rompe, PDF queda en disco
  4. Nivel 1: cliente que NUNCA escribió a Valentina recibe igual
     (WAHA inicia la conversación, sin ventana 24h de Meta Cloud API)
"""
import base64
import io
import os
import sqlite3
import sys
import time
from pathlib import Path
from unittest import mock

os.environ["POD_VEHICLE_TOKEN"] = "test-token-fase2"
sys.path.insert(0, "/mnt/ssd_trabajo/hermes-agent")

DB = "/mnt/ssd_trabajo/hermes-agent/data/dispatch.db"
PDF_DIR = Path("/mnt/ssd_trabajo/hermes-agent/data/pod_pdfs")
H = {"X-Vehicle-Token": "test-token-fase2"}

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

from api.pod_router import router  # noqa: E402
from scripts import waha_client  # noqa: E402

app = FastAPI()
app.include_router(router)
c = TestClient(app)

# Firma PNG real
img = Image.new("RGB", (300, 100), "white")
d = ImageDraw.Draw(img)
d.line([(20, 60), (60, 20), (100, 70), (280, 40)], fill="black", width=3)
buf = io.BytesIO()
img.save(buf, "PNG")
SIG_B64 = base64.b64encode(buf.getvalue()).decode()


def wait_for(cond, timeout=10, what="condición"):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if cond():
            return True
        time.sleep(0.2)
    raise AssertionError(f"TIMEOUT esperando: {what}")


# Fixture: delivery con cliente Nivel 1 (restaurant: nunca escribe primero)
conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
nivel1 = conn.execute(
    "SELECT id, name, phone, address_text FROM clients WHERE client_type != 'retail' LIMIT 1"
).fetchone() or conn.execute("SELECT id, name, phone, address_text FROM clients LIMIT 1").fetchone()
vehicle = conn.execute("SELECT id FROM vehicles LIMIT 1").fetchone()
did = conn.execute(
    """INSERT INTO deliveries
       (dispatch_session_id, client_id, vehicle_id, order_sequence,
        status, bottles_full, bottles_on_site_refill)
       VALUES (1, ?, ?, 995, 'delivered', 3, 1)""",
    (nivel1["id"], vehicle["id"]),
).lastrowid
conn.commit()
print(f"FIXTURE: delivery #{did} — cliente {nivel1['name']} ({nivel1['phone']})")

sent_calls: list[dict] = []

# Limpieza de PDFs de test previos (del mismo delivery)
for old in PDF_DIR.glob(f"pod_{did}_*.pdf") if PDF_DIR.exists() else []:
    old.unlink()

try:
    # ---- TEST 3 primero (WAHA NO conectado → fail-open) ----
    with mock.patch.object(waha_client, "is_session_ready", return_value=False):
        r = c.post(
            "/api/pod/submit",
            json={
                "delivery_id": did,
                "client_cedula": "V-87654321",
                "signature_canvas": SIG_B64,
                "empty_bottles_received": 4,
                "caps_received": 4,
                "pod_status": "signed",
            },
            headers=H,
        )
        assert r.status_code == 200, r.text  # fail-open: el submit NO rompe
        pod_id = r.json()["pod_id"]
        print(f"TEST3_OK: submit OK con WAHA caído (fail-open), pod #{pod_id}")

        wait_for(
            lambda: any(PDF_DIR.glob(f"pod_{did}_*.pdf")),
            what=f"PDF pod_{did}_ en {PDF_DIR}",
        )
        pdf = next(PDF_DIR.glob(f"pod_{did}_*.pdf"))
        assert pdf.stat().st_size > 1000
        print(f"TEST3b_OK: PDF guardado en data/pod_pdfs/ para envío manual: {pdf.name}")

    # ---- TEST 1+2: re-submit con WAHA conectado (mock) → envía ----
    def fake_send_document(phone, pdf_path, caption):
        sent_calls.append(
            {"phone": phone, "pdf_path": pdf_path, "caption": caption}
        )
        return {"sent": True, "reason": "ok", "status": 200}

    with (
        mock.patch.object(waha_client, "is_session_ready", return_value=True),
        mock.patch.object(waha_client, "send_document", side_effect=fake_send_document),
    ):
        r = c.post(
            "/api/pod/submit",
            json={
                "delivery_id": did,
                "client_cedula": "V-87654321",
                "signature_canvas": SIG_B64,
                "empty_bottles_received": 4,
                "caps_received": 4,
                "pod_status": "signed",
            },
            headers=H,
        )
        assert r.status_code == 200, r.text
        wait_for(lambda: sent_calls, what="llamada a send_document")
        call = sent_calls[-1]
        assert Path(call["pdf_path"]).exists(), "PDF enviado no existe"
        assert call["caption"] == (
            "✅ Tu entrega fue confirmada. Adjuntamos tu nota firmada. ¡Gracias! 💧"
        )
        print(f"TEST1_OK: PDF generado al firmar y enviado ({Path(call['pdf_path']).name})")
        print(f"TEST2_OK: WAHA envía documento con caption correcto a {call['phone']}")

    # ---- TEST 4: Nivel 1 recibe SIN haber escrito a Valentina ----
    # El chatId se forma del teléfono del cliente en la DB (no de una
    # conversación previa). WAHA inicia la conversación → sin ventana 24h.
    assert sent_calls, "no hubo envío"
    phone_sent = sent_calls[-1]["phone"]
    assert phone_sent == nivel1["phone"], f"{phone_sent} != {nivel1['phone']}"
    norm = waha_client._normalize_phone(phone_sent)
    assert norm == f"{''.join(ch for ch in phone_sent if ch.isdigit())}@c.us"
    print(f"TEST4_OK: Nivel 1 ({phone_sent} → {norm}) recibe sin escribir primero (chatId directo)")

    # ---- TEST 5: photo_only NO dispara envío ----
    n_before = len(sent_calls)
    r = c.post(
        "/api/pod/submit",
        json={
            "delivery_id": did,
            "photo_proof": base64.b64encode(b"\xff\xd8-fake").decode(),
            "pod_status": "photo_only",
        },
        headers=H,
    )
    assert r.status_code == 200, r.text
    time.sleep(1.5)  # margen por si algo (incorrectamente) disparara
    assert len(sent_calls) == n_before, "photo_only no debe enviar PDF"
    print("TEST5_OK: photo_only no dispara envío de copia")

    # ---- TEST 6: send_document real contra WAHA vivo sin sesión ----
    # (integración real: contenedor up, 0 sesiones → sent=False, sin excepción)
    waha_live = waha_client.send_document(
        "+584141234567", str(next(PDF_DIR.glob(f'pod_{did}_*.pdf'))), "test"
    )
    assert waha_live["sent"] is False, waha_live
    assert "WAHA" in waha_live["reason"] or "HTTP" in waha_live["reason"]
    print(f"TEST6_OK: WAHA vivo sin sesión → fail-open real: {waha_live['reason'][:60]}")

    print("ALL_FASE2_WAHA_TESTS_PASSED")
finally:
    conn.execute("DELETE FROM pod_records WHERE delivery_id = ?", (did,))
    conn.execute("DELETE FROM deliveries WHERE id = ?", (did,))
    conn.commit()
    conn.close()
    for old in PDF_DIR.glob(f"pod_{did}_*.pdf") if PDF_DIR.exists() else []:
        old.unlink()
    print("CLEANUP_OK")
