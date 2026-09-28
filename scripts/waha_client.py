#!/usr/bin/env python3
"""Cliente WAHA (WhatsApp HTTP API) para el numero secundario "Despachos H2O".

WAHA corre en Docker (devlikeapro/waha, puerto 3000) con sesiones montadas
en /mnt/ssd_trabajo/waha. A diferencia de la Meta Cloud API (Valentina,
ventana de 24h), WAHA puede INICIAR conversación → envía la copia firmada
de la nota de entrega a clientes Nivel 1 que nunca escriben primero.

Endpoint actual de WAHA: POST /api/sendFile
(sendDocument es el nombre legacy; verificado contra docs devlikeapro).

Fail-open por diseño: si WAHA no tiene sesión (sin chip aún) o falla,
NUNCA rompe el flujo POD — el PDF queda en data/pod_pdfs/ para envío
manual. Retorna dict {"sent": bool, "reason": str, ...}.
"""
from __future__ import annotations

import base64
import contextlib
import json
import logging
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

logger = logging.getLogger("pod.waha")

WAHA_BASE_URL = os.getenv("WAHA_BASE_URL", "http://127.0.0.1:3000")
WAHA_API_KEY = os.getenv("WAHA_API_KEY", "")  # config/.env del bridge
WAHA_SESSION = os.getenv("WAHA_SESSION", "default")
WAHA_TIMEOUT = int(os.getenv("WAHA_TIMEOUT", "10"))


def _request(method: str, path: str, payload: dict[str, Any] | None = None) -> tuple[int, str]:
    """POST/GET a WAHA con X-Api-Key. Retorna (status_code, body)."""
    url = f"{WAHA_BASE_URL}{path}"
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")
    if WAHA_API_KEY:
        req.add_header("X-Api-Key", WAHA_API_KEY)
    with urllib.request.urlopen(req, timeout=WAHA_TIMEOUT) as resp:
        return resp.status, resp.read().decode(errors="replace")


def is_session_ready() -> bool:
    """True si WAHA responde y hay una sesión WORKING (chip escaneado).

    Fail-safe: cualquier error (WAHA caído, sin API key, timeout) → False.
    """
    try:
        status, body = _request("GET", "/api/sessions")
    except Exception as e:  # noqa: BLE001 — fail-open por diseño
        logger.info("WAHA no accesible: %s", e)
        return False
    if status != 200:
        logger.info("WAHA /api/sessions status=%s", status)
        return False
    try:
        sessions = json.loads(body)
    except ValueError:
        return False
    ready = any(
        s.get("status") in ("WORKING", "logged") for s in sessions if isinstance(s, dict)
    )
    if not ready:
        estados = [s.get("status") for s in sessions if isinstance(s, dict)]
        logger.info(
            "WAHA sin sesión activa (estados: %s) — sin chip escaneado todavía",
            estados or "vacío",
        )
    return ready


def _normalize_phone(phone: str) -> str:
    """'+58 414-1234567' → '584141234567@c.us' (chatId de WhatsApp)."""
    digits = "".join(ch for ch in phone if ch.isdigit())
    return f"{digits}@c.us"


def send_document(phone: str, pdf_path: str, caption: str) -> dict[str, Any]:
    """Envía un PDF por WAHA al teléfono del cliente.

    Fail-open: nunca lanza. Retorna {"sent": bool, "reason": str}.
    """
    path = Path(pdf_path)
    if not path.exists():
        return {"sent": False, "reason": f"PDF no existe: {pdf_path}"}
    if not phone:
        return {"sent": False, "reason": "teléfono vacío"}

    try:
        b64 = base64.b64encode(path.read_bytes()).decode()
    except OSError as e:
        return {"sent": False, "reason": f"PDF ilegible: {e}"}

    payload = {
        "session": WAHA_SESSION,
        "chatId": _normalize_phone(phone),
        "file": {
            "mimetype": "application/pdf",
            "filename": path.name,
            "data": b64,
        },
        "caption": caption,
    }
    try:
        status, body = _request("POST", "/api/sendFile", payload)
        if status in (200, 201):
            ok_ret = {"sent": True, "reason": "ok", "status": status}
            logger.info("WAHA PDF enviado a %s (%s)", phone, path.name)
            return ok_ret
        return {
            "sent": False,
            "reason": f"WAHA HTTP {status}",
            "status": status,
            "body": body[:500],
        }
    except urllib.error.HTTPError as e:
        # 403/422 típico cuando la sesión no existe o no está WORKING
        detail = ""
        with contextlib.suppress(Exception):
            detail = e.read().decode(errors="replace")[:500]
        return {
            "sent": False,
            "reason": f"WAHA HTTPError {e.code}",
            "status": e.code,
            "body": detail,
        }
    except Exception as e:  # noqa: BLE001 — fail-open por diseño
        logger.warning("WAHA falló (fail-open): %s", e)
        return {"sent": False, "reason": f"WAHA error: {e}"}
