#!/usr/bin/env python3
"""Generador de PDF de nota de entrega firmada (POD).

produce data/pod_pdfs/pod_<delivery_id>_<timestamp>.pdf con:
  - Header "Estación H2O - Nota de Entrega"
  - Fecha/hora de entrega, datos del cliente (nombre, teléfono, cédula)
  - Dirección de entrega
  - Tabla de productos (cantidades, precios, total)
  - Botellones vacíos recibidos (swap) y tapas recibidas
  - Saldo anterior (si crédito)
  - Total a pagar
  - Firma manuscrita incrustada (PNG base64 del canvas de la PWA)
  - Línea "Firmado digitalmente el <fecha>"

Librería: fpdf2 (reportlab no instalado en este venv).

Uso:
  from scripts.pod.generate_pdf import generate_pod_pdf
  path = generate_pod_pdf(pod_record)   # pod_record: dict o sqlite3.Row
"""
from __future__ import annotations

import base64
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fpdf import FPDF

PDF_DIR = Path(
    "/mnt/ssd_trabajo/hermes-agent/data/pod_pdfs"
)  # override en tests con _set_pdf_dir

PRECIO_AGUA = 1.00  # EUR, igual que _build_product_details en pod_router


def _set_pdf_dir(path: Path) -> None:
    """Permite a los tests redirigir la salida a un directorio temporal."""
    global PDF_DIR
    PDF_DIR = Path(path)


def _fmt_money(v: float) -> str:
    return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _get(row: sqlite3.Row | dict[str, Any], key: str, default: Any = None) -> Any:
    if isinstance(row, dict):
        return row.get(key, default)
    try:
        return row[key]
    except (KeyError, IndexError):
        return default


def _delivery_datetime(row: sqlite3.Row | dict[str, Any]) -> str:
    signed = _get(row, "signed_at")
    if signed:
        try:
            return datetime.fromisoformat(signed).strftime("%d/%m/%Y %I:%M %p")
        except ValueError:
            return str(signed)
    return datetime.now(UTC).strftime("%d/%m/%Y %I:%M %p")


def _signature_image(sig_b64: str | None) -> Path | None:
    """Decodifica el PNG base64 del canvas y lo guarda en un buffer temporal.

    Retorna path a un PNG en memoria/disco que fpdf2 puede incrustar,
    o None si no hay firma válida.
    """
    if not sig_b64:
        return None
    try:
        # Aceptar data URL de la PWA: "data:image/png;base64,...."
        if sig_b64.startswith("data:"):
            sig_b64 = sig_b64.split(",", 1)[1]
        raw = base64.b64decode(sig_b64, validate=True)
    except Exception:
        return None
    if not raw.startswith(b"\x89PNG"):
        return None
    tmp = PDF_DIR / "_sig_tmp.png"
    try:
        tmp.write_bytes(raw)
        return tmp
    except OSError:
        return None


class _NotaPDF(FPDF):
    """A4 portrait con footer de página."""

    def footer(self) -> None:
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(120, 120, 120)
        self.cell(0, 10, f"Estación H2O · Nota de Entrega · Página {self.page_no()}", align="C")


def generate_pod_pdf(pod_record: sqlite3.Row | dict[str, Any]) -> str:
    """Genera el PDF de la nota firmada. Retorna el path absoluto del PDF."""
    PDF_DIR.mkdir(parents=True, exist_ok=True)

    delivery_id = int(_get(pod_record, "delivery_id", 0) or 0)
    stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    out_path = PDF_DIR / f"pod_{delivery_id}_{stamp}.pdf"

    name = str(_get(pod_record, "client_name", "") or "")
    phone = str(_get(pod_record, "client_phone", "") or "")
    cedula = str(_get(pod_record, "client_cedula", "") or "")
    address = str(_get(pod_record, "client_address", _get(pod_record, "address", "")) or "")
    empties = int(_get(pod_record, "empty_bottles_received", 0) or 0)
    caps = int(_get(pod_record, "caps_received", 0) or 0)
    signed_dt = _delivery_datetime(pod_record)

    # Productos: product_details_json si existe; si no, bottles_full + refill
    bottles_full = int(_get(pod_record, "bottles_full", 0) or 0)
    refill = int(_get(pod_record, "bottles_on_site_refill", 0) or 0)
    items: list[dict[str, Any]] = []
    total = float(_get(pod_record, "total_eur", 0) or 0)
    pd_json = _get(pod_record, "product_details_json")
    if pd_json:
        try:
            parsed = json.loads(str(pd_json))
            items = list(parsed.get("items", []))
            total = float(parsed.get("total", total))
        except (ValueError, TypeError, AttributeError):
            items = []
    if not items and (bottles_full + refill) > 0:
        qty = bottles_full + refill
        items = [{"code": "AGUA19L", "qty": qty, "price": PRECIO_AGUA}]
        total = round(qty * PRECIO_AGUA, 2)

    saldo_anterior = _get(pod_record, "previous_balance_eur")
    saldo_anterior = float(saldo_anterior) if saldo_anterior not in (None, "") else None

    pdf = _NotaPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()

    # ---- Header ----
    pdf.set_font("Helvetica", "B", 16)
    pdf.set_text_color(0, 80, 140)
    pdf.cell(0, 10, "Estación H2O - Nota de Entrega", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 7, f"Nota #{delivery_id} · Fecha y hora de entrega: {signed_dt}", align="C")
    pdf.ln(10)

    # ---- Datos del cliente ----
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, "Datos del cliente", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, f"Nombre: {name}")
    pdf.ln(6)
    pdf.cell(0, 6, f"Teléfono: {phone}")
    pdf.ln(6)
    pdf.cell(0, 6, f"Cédula: {cedula or '—'}")
    pdf.ln(6)
    pdf.cell(0, 6, f"Dirección de entrega: {address or '—'}")
    pdf.ln(10)

    # ---- Tabla de productos ----
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, "Productos entregados", new_y="NEXT")
    col_w = [95, 30, 35, 30]
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_fill_color(0, 80, 140)
    pdf.set_text_color(255, 255, 255)
    headers = ["Producto", "Cant.", "Precio (EUR)", "Subtotal (EUR)"]
    for header, w in zip(headers, col_w, strict=True):
        pdf.cell(w, 7, header, border=1, fill=True, align="C")
    pdf.ln(7)
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Helvetica", "", 9)
    if items:
        for it in items:
            it_qty = float(it.get("qty", 0) or 0)
            price = float(it.get("price", 0) or 0)
            pdf.cell(col_w[0], 7, f"Agua 19L ({it.get('code', 'AGUA19L')})", border=1)
            pdf.cell(col_w[1], 7, f"{it_qty:g}", border=1, align="C")
            pdf.cell(col_w[2], 7, _fmt_money(price), border=1, align="R")
            pdf.cell(col_w[3], 7, _fmt_money(it_qty * price), border=1, align="R")
            pdf.ln(7)
    else:
        pdf.cell(sum(col_w), 7, "Sin productos registrados", border=1, align="C")
        pdf.ln(7)
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(sum(col_w) - col_w[-1], 7, "Total productos", border=1, align="R")
    pdf.cell(col_w[-1], 7, _fmt_money(total), border=1, align="R")
    pdf.ln(12)

    # ---- Swap de envases ----
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, "Devolución de envases", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, f"Botellones vacíos recibidos: {empties}")
    pdf.ln(6)
    pdf.cell(0, 6, f"Tapas recibidas: {caps}")
    pdf.ln(10)

    # ---- Saldo y total ----
    pdf.set_font("Helvetica", "B", 11)
    if saldo_anterior is not None and saldo_anterior > 0:
        pdf.cell(0, 7, f"Saldo anterior (crédito): {_fmt_money(saldo_anterior)} EUR")
        pdf.ln(7)
        pdf.cell(0, 7, f"Total a pagar (incluye saldo): {_fmt_money(total + saldo_anterior)} EUR")
    else:
        pdf.cell(0, 7, f"Total a pagar: {_fmt_money(total)} EUR")
    pdf.ln(12)

    # ---- Firma ----
    sig_path = _signature_image(_get(pod_record, "signature_canvas"))
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, "Firma del cliente", new_y="NEXT")
    if sig_path and sig_path.exists():
        try:
            pdf.image(str(sig_path), w=90)
        finally:
            sig_path.unlink(missing_ok=True)  # temporal
    else:
        pdf.set_font("Helvetica", "I", 10)
        pdf.cell(0, 10, "(sin firma adjunta)")
        pdf.ln(10)
    pdf.set_draw_color(80, 80, 80)
    pdf.line(20, pdf.get_y(), 120, pdf.get_y())
    pdf.ln(8)
    pdf.set_font("Helvetica", "I", 9)
    pdf.cell(0, 6, f"Firmado digitalmente el {signed_dt}")

    pdf.output(str(out_path))
    return str(out_path)
