#!/usr/bin/env python3
"""Tests FASE 1: generador de PDF de nota de entrega firmada.

E2E con datos reales: fixture delivery en dispatch.db → pod_record
→ generate_pod_pdf → valida PDF con pypdf (abre, extrae texto,
verifica campos) y que la firma PNG queda incrustada (XObject /Image).
"""
import base64
import io
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, "/mnt/ssd_trabajo/hermes-agent")

DB = "/mnt/ssd_trabajo/hermes-agent/data/dispatch.db"

# Firma real: PNG generado con Pillow (canvas manuscrito simulado)
from PIL import Image, ImageDraw  # noqa: E402
from pypdf import PdfReader  # noqa: E402

from scripts.pod import generate_pdf as gp  # noqa: E402

img = Image.new("RGB", (300, 100), "white")
d = ImageDraw.Draw(img)
d.line([(20, 60), (60, 20), (100, 70), (150, 25), (210, 65), (280, 40)], fill="black", width=3)
d.text((15, 75), "firma de prueba POD", fill="black")
buf = io.BytesIO()
img.save(buf, "PNG")
SIG_B64 = base64.b64encode(buf.getvalue()).decode()

# PDFs de test a directorio temporal (no ensuciar data/pod_pdfs)
tmpdir = Path(tempfile.mkdtemp(prefix="pod_pdf_test_"))
gp._set_pdf_dir(tmpdir)

# Fixture: delivery + pod_record con datos reales en dispatch.db
conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
client = conn.execute("SELECT id, name, phone, address_text FROM clients LIMIT 1").fetchone()
vehicle = conn.execute("SELECT id FROM vehicles LIMIT 1").fetchone()
did = conn.execute(
    """INSERT INTO deliveries
       (dispatch_session_id, client_id, vehicle_id, order_sequence,
        status, bottles_full, bottles_on_site_refill)
       VALUES (1, ?, ?, 996, 'delivered', 4, 2)""",
    (client["id"], vehicle["id"]),
).lastrowid
conn.commit()
print(f"FIXTURE: delivery #{did} cliente {client['name']} {client['phone']}")

pod_record = {
    "delivery_id": did,
    "client_name": client["name"],
    "client_phone": client["phone"],
    "client_cedula": "V-12345678",
    "client_address": client["address_text"],
    "bottles_full": 4,
    "bottles_on_site_refill": 2,
    "empty_bottles_received": 5,
    "caps_received": 5,
    "previous_balance_eur": 12.50,
    "signature_canvas": SIG_B64,
    "signed_at": "2026-09-28T10:30:00+00:00",
    "pod_status": "signed",
}

try:
    # TEST 1: genera PDF con datos reales y retorna path
    path = gp.generate_pod_pdf(pod_record)
    assert path and Path(path).exists(), f"PDF no existe: {path}"
    assert Path(path).name.startswith(f"pod_{did}_"), Path(path).name
    assert path.endswith(".pdf")
    size = Path(path).stat().st_size
    assert size > 1000, f"PDF sospechosamente chico: {size} bytes"
    print(f"TEST1_OK: PDF generado {path} ({size} bytes)")

    # TEST 2: el PDF abre correctamente y contiene todos los campos
    reader = PdfReader(path)
    assert len(reader.pages) >= 1, "PDF sin páginas"
    text = reader.pages[0].extract_text()
    for expected in [
        "Estación H2O - Nota de Entrega",
        str(did),
        client["name"],
        client["phone"],
        "V-12345678",
        "Botellones vacíos recibidos: 5",
        "Tapas recibidas: 5",
        "Saldo anterior (crédito): 12,50 EUR",
        "Total a pagar (incluye saldo): 18,50 EUR",
        "Firmado digitalmente el 28/09/2026 10:30 AM",
    ]:
        assert expected in text, f"FALTA en PDF: {expected!r}"
    print("TEST2_OK: PDF abre y contiene todos los campos (cliente, swap, saldo, firma fecha)")

    # TEST 3: la firma queda incrustada como imagen
    page = reader.pages[0]
    xobjs = page.get("/Resources", {}).get("/XObject", {})
    has_img = False
    for name in xobjs:
        obj = xobjs[name].get_object()
        if obj.get("/Subtype") == "/Image":
            has_img = True
            w, h = obj.get("/Width"), obj.get("/Height")
            assert (w, h) == (300, 100), f"dimensión firma inesperada {w}x{h}"
    assert has_img, "PDF sin imagen incrustada (firma)"
    print("TEST3_OK: firma PNG incrustada como imagen 300x100 en el PDF")

    # TEST 4: sin saldo (contado) → línea alternativa correcta
    pod_record2 = dict(pod_record, previous_balance_eur=None)
    path2 = gp.generate_pod_pdf(pod_record2)
    text2 = PdfReader(path2).pages[0].extract_text()
    assert "Total a pagar: 6,00 EUR" in text2, "total contado incorrecto"
    assert "Saldo anterior" not in text2, "no debe mostrar saldo si es contado"
    print("TEST4_OK: sin crédito muestra 'Total a pagar: 6,00 EUR'")

    # TEST 5: firma data-URL de la PWA (data:image/png;base64,...)
    pod_record3 = dict(
        pod_record,
        signature_canvas=f"data:image/png;base64,{SIG_B64}",
        previous_balance_eur=None,
    )
    path3 = gp.generate_pod_pdf(pod_record3)
    page3 = PdfReader(path3).pages[0]
    xobjs3 = page3.get("/Resources", {}).get("/XObject", {})
    assert any(
        xobjs3[n].get_object().get("/Subtype") == "/Image" for n in xobjs3
    ), "firma data-URL no incrustada"
    print("TEST5_OK: firma en formato data-URL de PWA también se incrusta")

    # TEST 6: sin firma → no rompe, nota '(sin firma adjunta)'
    no_sig = {**pod_record, "signature_canvas": None, "previous_balance_eur": None}
    path4 = gp.generate_pod_pdf(no_sig)
    text4 = PdfReader(path4).pages[0].extract_text()
    assert "sin firma adjunta" in text4
    print("TEST6_OK: sin firma no rompe")

    print("ALL_FASE1_PDF_TESTS_PASSED")
finally:
    conn.execute("DELETE FROM deliveries WHERE id = ?", (did,))
    conn.commit()
    conn.close()
    print("CLEANUP_OK")
