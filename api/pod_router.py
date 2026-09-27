#!/usr/bin/env python3
"""Router POD (Proof of Delivery) — Bloque 2 Fase 2.3.

Endpoints para la PWA de firma del chofer (Bloque 3):
  GET  /api/pod/{delivery_id}   → datos de la entrega para render
  POST /api/pod/submit          → guarda firma/foto/cédula, actualiza pod_status
  GET  /api/pod/status/{delivery_id} → estado del POD

Auth simple por token de vehículo: header X-Vehicle-Token
(config POD_VEHICLE_TOKENS = "token1:veh1,token2:veh2" o token único
POD_VEHICLE_TOKEN para todos). Read-only no requiere token de saldo:
el endpoint GET devuelve el saldo anterior SOLO como campo renderizado,
la PWA del chofer nunca lo solicita por separado.
"""

from __future__ import annotations

import base64
import binascii
import json
import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/pod", tags=["pod"])

DISPATCH_DB_PATH = os.getenv(
    "DISPATCH_DB_PATH", "/mnt/ssd_trabajo/hermes-agent/data/dispatch.db"
)

PHOTO_DIR = Path(os.getenv("POD_PHOTO_DIR", "/mnt/ssd_trabajo/hermes-agent/data/pod_photos"))
PHOTO_DIR.mkdir(parents=True, exist_ok=True)

MAX_SIGNATURE_B64 = 2_000_000  # ~1.4MB PNG
MAX_PHOTO_B64 = 8_000_000  # ~6MB JPEG


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DISPATCH_DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _verify_token(x_vehicle_token: str | None) -> None:
    """Auth simple: token fijo por env (todos los vehículos) o mapa token:vehicle."""
    tokens_map = os.getenv("POD_VEHICLE_TOKENS", "")
    single = os.getenv("POD_VEHICLE_TOKEN", "")
    if not (tokens_map or single):
        # Sin tokens configurados → denegado (fail-closed)
        raise HTTPException(status_code=503, detail="POD auth no configurado")
    if not x_vehicle_token:
        raise HTTPException(status_code=401, detail="Token requerido")
    if single and x_vehicle_token == single:
        return
    if tokens_map:
        for pair in tokens_map.split(","):
            if pair.strip() and x_vehicle_token == pair.strip().split(":")[0]:
                return
    raise HTTPException(status_code=401, detail="Token inválido")


def _previous_balance_eur(client_id: int) -> float | None:
    """Saldo anterior del cliente (solo crédito). Render server-side.

    Fuente: fs_pedidos/fs_cuentas_cobrar en conversations.db (pendientes).
    El chofer nunca llama esto directo: va incrusto en el GET del POD.
    """
    conv_path = os.getenv(
        "CONVERSATIONS_DB_PATH", "/mnt/ssd_trabajo/hermes-agent/data/conversations.db"
    )
    try:
        conn = sqlite3.connect(conv_path, check_same_thread=False)
        row = conn.execute(
            """SELECT COALESCE(SUM(monto_total_eur - monto_pagado_eur), 0) AS saldo
               FROM fs_pedidos WHERE cliente_telefono =
                 (SELECT phone FROM clients WHERE id = ? LIMIT 1)
               AND estado_pago IN ('pendiente','verificando')""",
            (client_id,),
        ).fetchone()
        conn.close()
        saldo = float(row[0]) if row else 0.0
        return saldo if saldo > 0 else None
    except Exception:
        return None


def _build_product_details(row: sqlite3.Row) -> str:
    """JSON de productos de la entrega con precios de Odoo (AGUA 1.00 / HIELO 1.20)."""
    agua = float(os.getenv("POD_PRECIO_AGUA", "1.00"))
    bottles = row["bottles_full"] or 0
    refill = row["bottles_on_site_refill"] or 0
    total = bottles * agua + refill * agua
    return json.dumps(
        {
            "items": [
                {"code": "AGUA19L", "qty": bottles + refill, "price": agua},
            ],
            "total": round(total, 2),
        }
    )


@router.get("/{delivery_id}")
async def get_pod(
    delivery_id: int,
    x_vehicle_token: str | None = Header(default=None),
) -> dict[str, Any]:
    """Datos de la entrega para renderizar la nota en la PWA."""
    _verify_token(x_vehicle_token)
    conn = _get_conn()
    try:
        row = conn.execute(
            """SELECT d.id, d.status, d.pod_id, d.pod_status, d.bottles_full,
                      d.bottles_on_site_refill, d.bottles_empty_pickup,
                      c.id AS client_id, c.name AS client_name, c.phone,
                      c.address_text, d.vehicle_id
               FROM deliveries d JOIN clients c ON d.client_id = c.id
               WHERE d.id = ?""",
            (delivery_id,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Entrega no encontrada")
        return {
            "delivery_id": row["id"],
            "status": row["status"],
            "pod_status": row["pod_status"] or "pending",
            "client_name": row["client_name"],
            "client_phone": row["phone"],
            "address": row["address_text"],
            "vehicle_id": row["vehicle_id"],
            "bottles_full": row["bottles_full"],
            "bottles_refill": row["bottles_on_site_refill"],
            "empty_pickup": row["bottles_empty_pickup"],
            "product_details": json.loads(_build_product_details(row)),
            "previous_balance_eur": _previous_balance_eur(row["client_id"]),
        }
    finally:
        conn.close()


class PodSubmit(BaseModel):
    delivery_id: int
    client_cedula: str = Field(default="", max_length=20)
    signature_canvas: str | None = None  # base64 PNG
    photo_proof: str | None = None  # base64 JPEG
    empty_bottles_received: int = 0
    caps_received: int = 0
    pod_status: str = Field(default="signed", pattern="^(signed|photo_only|refused)$")
    offline_created: int = 0
    signed_at: str | None = None  # ISO8601 (si fue firmado offline)


def _save_photo(delivery_id: int, photo_b64: str) -> str:
    """Guarda la foto en disco, retorna el path relativo."""
    try:
        raw = base64.b64decode(photo_b64, validate=True)
    except (binascii.Error, ValueError) as e:
        raise HTTPException(status_code=400, detail=f"Foto base64 inválida: {e}") from e
    if len(raw) > 6_500_000:
        raise HTTPException(status_code=413, detail="Foto demasiado grande")
    stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    path = PHOTO_DIR / f"pod_{delivery_id}_{stamp}.jpg"
    path.write_bytes(raw)
    return str(path)


@router.post("/submit")
async def submit_pod(
    payload: PodSubmit,
    x_vehicle_token: str | None = Header(default=None),
) -> dict[str, Any]:
    """Recibe la firma/foto de la entrega y actualiza el pod_record."""
    _verify_token(x_vehicle_token)
    if payload.pod_status == "signed" and not payload.signature_canvas:
        raise HTTPException(status_code=400, detail="Firma requerida para status=signed")
    if payload.pod_status in ("photo_only", "refused") and not payload.photo_proof:
        raise HTTPException(
            status_code=400, detail=f"Foto requerida para status={payload.pod_status}"
        )
    if payload.signature_canvas and len(payload.signature_canvas) > MAX_SIGNATURE_B64:
        raise HTTPException(status_code=413, detail="Firma demasiado grande")

    conn = _get_conn()
    try:
        d = conn.execute(
            """SELECT d.id, d.vehicle_id, c.phone, c.name, c.id AS client_id
               FROM deliveries d JOIN clients c ON d.client_id = c.id
               WHERE d.id = ?""",
            (payload.delivery_id,),
        ).fetchone()
        if not d:
            raise HTTPException(status_code=404, detail="Entrega no encontrada")

        photo_path = (
            _save_photo(payload.delivery_id, payload.photo_proof)
            if payload.photo_proof
            else None
        )
        now = payload.signed_at or datetime.now(UTC).isoformat()

        existing = conn.execute(
            "SELECT id FROM pod_records WHERE delivery_id = ? ORDER BY id DESC LIMIT 1",
            (payload.delivery_id,),
        ).fetchone()
        if existing:
            pod_id = existing["id"]
            conn.execute(
                """UPDATE pod_records SET
                       client_cedula = ?, signature_canvas = ?, photo_proof = ?,
                       empty_bottles_received = ?, caps_received = ?,
                       signed_at = ?, pod_status = ?,
                       offline_created = ?, synced_to_odoo = 0
                   WHERE id = ?""",
                (
                    payload.client_cedula,
                    payload.signature_canvas,
                    photo_path,
                    payload.empty_bottles_received,
                    payload.caps_received,
                    now,
                    payload.pod_status,
                    payload.offline_created,
                    pod_id,
                ),
            )
        else:
            cur = conn.execute(
                """INSERT INTO pod_records
                       (delivery_id, client_phone, client_name, client_cedula,
                        signature_canvas, photo_proof,
                        empty_bottles_received, caps_received,
                        signed_at, pod_status, offline_created, synced_to_odoo, vehicle_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)""",
                (
                    payload.delivery_id,
                    d["phone"],
                    d["name"],
                    payload.client_cedula,
                    payload.signature_canvas,
                    photo_path,
                    payload.empty_bottles_received,
                    payload.caps_received,
                    now,
                    payload.pod_status,
                    payload.offline_created,
                    d["vehicle_id"],
                ),
            )
            pod_id = int(cur.lastrowid or 0)

        conn.execute(
            "UPDATE deliveries SET pod_id = ?, pod_status = ? WHERE id = ?",
            (pod_id, payload.pod_status, payload.delivery_id),
        )
        conn.commit()
        return {"status": "ok", "pod_id": pod_id, "pod_status": payload.pod_status}
    finally:
        conn.close()


@router.get("/status/{delivery_id}")
async def pod_status(
    delivery_id: int,
    x_vehicle_token: str | None = Header(default=None),
) -> dict[str, Any]:
    """Estado del POD: pending/signed/photo_only/refused + sync Odoo."""
    _verify_token(x_vehicle_token)
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT id, pod_status, synced_to_odoo, synced_at, signed_at FROM pod_records "
            "WHERE delivery_id = ? ORDER BY id DESC LIMIT 1",
            (delivery_id,),
        ).fetchone()
        if not row:
            return {"delivery_id": delivery_id, "pod_status": "pending", "synced_to_odoo": 0}
        return {
            "delivery_id": delivery_id,
            "pod_id": row["id"],
            "pod_status": row["pod_status"],
            "signed_at": row["signed_at"],
            "synced_to_odoo": row["synced_to_odoo"],
            "synced_at": row["synced_at"],
        }
    finally:
        conn.close()
