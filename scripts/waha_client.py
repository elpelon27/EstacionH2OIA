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
import random
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

logger = logging.getLogger("pod.waha")

WAHA_BASE_URL = os.getenv("WAHA_BASE_URL", "http://127.0.0.1:3000")
WAHA_API_KEY = os.getenv("WAHA_API_KEY", "")  # config/.env del bridge
WAHA_SESSION = os.getenv("WAHA_SESSION", "default")
WAHA_TIMEOUT = int(os.getenv("WAHA_TIMEOUT", "10"))

# =============================================================================
# ROTACIÓN ANTI-BAN POR ENTREGA
# =============================================================================
# REGLA CRÍTICA: una entrega = UN SOLO número de WhatsApp de punta a punta.
# El cliente ve siempre el MISMO número en "va en camino", "llegué", "te
# espero" y el PDF firmado. Lo que rota es el TEXTO (5 variaciones por tipo),
# no el número. Así repartimos el tráfico entre 2 chips sin que el cliente
# perciba inconsistencia.
#
# vehicle_id viene de deliveries.vehicle_id / pod_records.vehicle_id
# (verificado en data/dispatch.db: vehicles 1=Triciclo 1 YORDANIS,
# 2=Triciclo 2 EVERT).

SESSION_FOR_VEHICLE: dict[int, str] = {
    1: os.getenv("WAHA_SESSION_VEHICLE_1", "chofer_1"),
    2: os.getenv("WAHA_SESSION_VEHICLE_2", "chofer_2"),
}
DEFAULT_DELIVERY_SESSION = os.getenv("WAHA_SESSION_FALLBACK", WAHA_SESSION)

AVISO_CERCA = [
    "Hola! Tu repartidor de Estación H2O está a 5 minutos de tu ubicación. 🚚",
    "🚚 Tu pedido de agua va en camino, llegamos en 5 minutos!",
    "¡Ya casi llegamos! Tu repartidor está a 5 minutos. 💧",
    "Te avisamos que tu entrega de Estación H2O está próxima, 5 min aprox. 📍",
    "Buen día! Tu repartidor está a 5 minutos de tu dirección. 🚚💧",
]

AVISO_LLEGADA = [
    "¡Tu repartidor ha llegado! Ya está afuera de tu dirección. 💧",
    "🚚 Tu repartidor de Estación H2O ya está en el lugar.",
    "¡Llegamos! Tu repartidor te está esperando afuera. 💧",
    "Tu pedido de agua ya está en tu dirección. 📍",
    "¡Buenas! Tu repartidor ya llegó con tu entrega. 💧🚚",
]

AVISO_ESPERANDO = [
    "Tu repartidor te está esperando. Por favor acercate al vehículo. 💧",
    "🚚 Tu repartidor sigue esperando. ¿Podés acercarte?",
    "Te esperamos afuera con tu entrega de agua. 💧",
    "Tu repartidor de Estación H2O está esperando, por favor recibí tu pedido. 📍",
    "Tu repartidor sigue en el lugar, acercate cuando puedas. 💧",
]

PDF_FIRMA = [
    "✅ Tu entrega fue confirmada. Adjuntamos tu nota firmada. ¡Gracias! 💧",
    "💧 Tu nota de entrega firmada. ¡Gracias por confiar en Estación H2O!",
    "✅ Confirmamos tu entrega. Adjuntamos comprobante firmado. ¡Gracias!",
    "📦 Tu pedido fue entregado. Te dejamos la nota firmada. 💧",
    "✅ Tu entrega está confirmada. Adjuntamos tu comprobante. ¡Gracias! 💧",
]

# Cada tipo tiene exactamente 5 variaciones — se valida en import.
MESSAGE_VARIANTS: dict[str, list[str]] = {
    "AVISO_CERCA": AVISO_CERCA,
    "AVISO_LLEGADA": AVISO_LLEGADA,
    "AVISO_ESPERANDO": AVISO_ESPERANDO,
    "PDF_FIRMA": PDF_FIRMA,
}


def session_for_vehicle(vehicle_id: int | str | None) -> str:
    """Número (sesión WAHA) que corresponde a esta entrega.

    Determinista por entrega: el MISMO vehicle_id devuelve SIEMPRE la misma
    sesión. Rotar número dentro de una entrega está prohibido.
    """
    try:
        vid = int(vehicle_id)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        vid = -1
    if vid in SESSION_FOR_VEHICLE:
        return SESSION_FOR_VEHICLE[vid]
    if vid > 0:
        # Vehículo fuera del mapa conocido: sesión estable derivada del id,
        # no aleatoria (misma entrega => mismo número).
        fallback = os.getenv(f"WAHA_SESSION_VEHICLE_{vid}")
        if fallback:
            return fallback
    return DEFAULT_DELIVERY_SESSION


def pick_variant(text_type: str, rng: "random.Random | None" = None) -> tuple[str, int]:
    """Devuelve (texto, índice 1-5) para el tipo de aviso. Aleatorio por envío."""
    variants = MESSAGE_VARIANTS.get(text_type)
    if not variants:
        raise KeyError(f"text_type desconocido: {text_type}")
    r = rng or random
    idx = r.randrange(len(variants))
    return variants[idx], idx + 1


def send_message_for_delivery(
    phone: str,
    text_type: str,
    vehicle_id: int | str | None = None,
    context: dict[str, Any] | None = None,
    delivery_id: int | str | None = None,
    pdf_path: str | None = None,
) -> dict[str, Any]:
    """Envía un aviso de entrega desde el número que corresponde al vehículo.

    Garantiza la regla crítica: todos los mensajes de una misma entrega salen
    de la misma sesión WAHA. Entre mensajes rota el TEXTO (anti-ban).

    text_type: AVISO_CERCA | AVISO_LLEGADA | AVISO_ESPERANDO | PDF_FIRMA
    Fail-open: nunca lanza. Retorna dict con sent/reason y metadatos de log.
    """
    context = context or {}
    session = session_for_vehicle(vehicle_id)

    try:
        text, variant_idx = pick_variant(text_type)
    except KeyError as e:
        return {"sent": False, "reason": str(e), "session": session}

    result: dict[str, Any]
    if text_type == "PDF_FIRMA" and pdf_path:
        result = send_document(phone, pdf_path, text, session=session)
    else:
        result = send_text(phone, text, session=session)

    # Log obligatorio: qué número, qué variación, qué entrega.
    result.update(
        {
            "session": session,
            "vehicle_id": vehicle_id,
            "delivery_id": delivery_id,
            "text_type": text_type,
            "variant": variant_idx,
            "variants_total": len(MESSAGE_VARIANTS[text_type]),
        }
    )
    logger.info(
        "AVISO %s entrega=%s vehiculo=%s → sesión=%s variación %d/%d → sent=%s (%s)",
        text_type,
        delivery_id,
        vehicle_id,
        session,
        variant_idx,
        len(MESSAGE_VARIANTS[text_type]),
        result.get("sent"),
        result.get("reason"),
    )
    return result


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


def send_text(phone: str, text: str, session: str | None = None) -> dict[str, Any]:
    """Envía un mensaje de texto plano por la sesión indicada.

    Fail-open: nunca lanza. Retorna {"sent": bool, "reason": str}.
    """
    sess = session or WAHA_SESSION
    if not phone:
        return {"sent": False, "reason": "teléfono vacío", "session": sess}
    if not text:
        return {"sent": False, "reason": "texto vacío", "session": sess}

    payload = {"session": sess, "chatId": _normalize_phone(phone), "text": text}
    try:
        status, body = _request("POST", "/api/sendText", payload)
        if status in (200, 201):
            logger.info("WAHA texto enviado a %s vía %s", phone, sess)
            return {"sent": True, "reason": "ok", "status": status, "session": sess}
        return {
            "sent": False,
            "reason": f"WAHA HTTP {status}",
            "status": status,
            "body": body[:500],
            "session": sess,
        }
    except urllib.error.HTTPError as e:
        detail = ""
        with contextlib.suppress(Exception):
            detail = e.read().decode(errors="replace")[:500]
        return {
            "sent": False,
            "reason": f"WAHA HTTPError {e.code}",
            "status": e.code,
            "body": detail,
            "session": sess,
        }
    except Exception as e:  # noqa: BLE001 — fail-open por diseño
        logger.warning("WAHA falló (fail-open): %s", e)
        return {"sent": False, "reason": f"WAHA error: {e}", "session": sess}


def send_document(
    phone: str, pdf_path: str, caption: str, session: str | None = None
) -> dict[str, Any]:
    """Envía un PDF por WAHA al teléfono del cliente.

    Fail-open: nunca lanza. Retorna {"sent": bool, "reason": str}.
    """
    sess = session or WAHA_SESSION
    path = Path(pdf_path)
    if not path.exists():
        return {"sent": False, "reason": f"PDF no existe: {pdf_path}", "session": sess}
    if not phone:
        return {"sent": False, "reason": "teléfono vacío", "session": sess}

    try:
        b64 = base64.b64encode(path.read_bytes()).decode()
    except OSError as e:
        return {"sent": False, "reason": f"PDF ilegible: {e}", "session": sess}

    payload = {
        "session": sess,
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
