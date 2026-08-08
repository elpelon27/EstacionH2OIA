#!/usr/bin/env python3
"""
============================================================================
Prometeo Approval System — Solicitud de validación asíncrona vía Telegram
Estación H2O · Maracaibo, Venezuela
============================================================================

Permite a Prometeo (agente IA) solicitar validación/contraseña al Líder
sin bloquear la ejecución. El Líder responde via Telegram cuando pueda.

Uso desde código de Prometeo:
    from core.prometeo_approval import request_approval

    # Solicitar contraseña sudo
    password = request_approval(
        type="sudo_password",
        prompt="Necesito sudo para copiar systemd unit a /etc/systemd/system/",
        context={"target": "/etc/systemd/system/valentina-bridge.service"},
        timeout_seconds=3600  # 1 hora
    )
    # El código continúa aquí cuando el Líder responde

    # Solicitar validación genérica
    approved = request_approval(
        type="validation",
        prompt="¿Confirmas rollback a commit abc123?",
        context={"commit": "abc123", "files": ["api/bridge.py"]},
        timeout_seconds=1800
    )

Arquitectura:
- Solicitudes se guardan como JSON en data/prometeo_approvals/pending/
- Prometeo Telegram Bot (prometeo_telegram.py) tiene background task que
  detecta nuevas solicitudes y notifica al Líder vía Telegram
- Líder usa /approve <id> <respuesta> o /pending para ver cola
- Respuestas se guardan en data/prometeo_approvals/completed/
- request_approval() hace polling hasta recibir respuesta o timeout
"""

import contextlib
import json
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

# Config
APPROVAL_DIR = Path("/mnt/ssd_trabajo/hermes-agent/data/prometeo_approvals")
PENDING_DIR = APPROVAL_DIR / "pending"
COMPLETED_DIR = APPROVAL_DIR / "completed"

# Asegurar directorios
PENDING_DIR.mkdir(parents=True, exist_ok=True)
COMPLETED_DIR.mkdir(parents=True, exist_ok=True)


ApprovalType = Literal["sudo_password", "validation", "confirmation", "input"]


class ApprovalRequest:
    """Solicitud de aprobación pendiente."""

    def __init__(
        self,
        approval_type: ApprovalType,
        prompt: str,
        context: dict[str, Any] | None = None,
        timeout_seconds: int = 3600,
        request_id: str | None = None,
    ):
        self.id = request_id or str(uuid.uuid4())[:8]
        self.type = approval_type
        self.prompt = prompt
        self.context = context or {}
        self.timeout_seconds = timeout_seconds
        self.created_at = datetime.now(UTC).isoformat()
        self.status: Literal["pending", "completed", "expired", "cancelled"] = "pending"
        self.response: Any = None
        self.responded_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "prompt": self.prompt,
            "context": self.context,
            "timeout_seconds": self.timeout_seconds,
            "created_at": self.created_at,
            "status": self.status,
            "response": self.response,
            "responded_at": self.responded_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ApprovalRequest":
        req = cls(
            approval_type=data["type"],
            prompt=data["prompt"],
            context=data.get("context", {}),
            timeout_seconds=data.get("timeout_seconds", 3600),
            request_id=data["id"],
        )
        req.status = data.get("status", "pending")
        req.response = data.get("response")
        req.responded_at = data.get("responded_at")
        return req

    def pending_path(self) -> Path:
        return PENDING_DIR / f"{self.id}.json"

    def completed_path(self) -> Path:
        return COMPLETED_DIR / f"{self.id}.json"

    def save_pending(self) -> None:
        self.pending_path().write_text(json.dumps(self.to_dict(), indent=2))

    def save_completed(self) -> None:
        self.completed_path().write_text(json.dumps(self.to_dict(), indent=2))
        # Limpiar pending
        with contextlib.suppress(Exception):
            self.pending_path().unlink(missing_ok=True)

    def is_expired(self) -> bool:
        if self.status != "pending":
            return False
        created = datetime.fromisoformat(self.created_at.replace("Z", "+00:00"))
        elapsed = (datetime.now(UTC) - created).total_seconds()
        return elapsed > self.timeout_seconds


def request_approval(
    approval_type: ApprovalType,
    prompt: str,
    context: dict[str, Any] | None = None,
    timeout_seconds: int = 3600,
    poll_interval: float = 5.0,
) -> Any:
    """
    Solicita aprobación al Líder vía Telegram y espera respuesta.

    Args:
        approval_type: Tipo de solicitud (sudo_password, validation, confirmation, input)
        prompt: Mensaje que verá el Líder
        context: Diccionario con datos adicionales para el Líder
        timeout_seconds: Tiempo máximo de espera (default 1 hora)
        poll_interval: Intervalo de polling en segundos (default 5s)

    Returns:
        - sudo_password: str (la contraseña ingresada)
        - validation/confirmation: bool (True si aprobó)
        - input: str (texto libre ingresado)

    Raises:
        TimeoutError: Si expira el timeout
        ValueError: Si la solicitud fue cancelada o expiró
    """
    req = ApprovalRequest(
        approval_type=approval_type,
        prompt=prompt,
        context=context,
        timeout_seconds=timeout_seconds,
    )
    req.save_pending()

    print(f"📋 [Approval {req.id}] Solicitud enviada al Líder vía Telegram: {prompt[:80]}...")

    # Polling hasta respuesta o timeout
    start_time = time.time()
    while time.time() - start_time < timeout_seconds:
        # Verificar si hay respuesta en completed
        completed_path = req.completed_path()
        if completed_path.exists():
            try:
                data = json.loads(completed_path.read_text())
                req = ApprovalRequest.from_dict(data)
                break
            except Exception:
                pass

        # Verificar expiración
        if req.is_expired():
            req.status = "expired"
            req.save_completed()
            raise TimeoutError(f"Solicitud {req.id} expiró tras {timeout_seconds}s")

        time.sleep(poll_interval)
    else:
        req.status = "expired"
        req.save_completed()
        raise TimeoutError(f"Solicitud {req.id} expiró tras {timeout_seconds}s")

    # Procesar respuesta según tipo
    if req.status != "completed":
        raise ValueError(f"Solicitud {req.id} terminó con estado: {req.status}")

    response = req.response

    if approval_type == "sudo_password":
        if not response or not isinstance(response, str):
            raise ValueError("Respuesta de contraseña inválida")
        return response

    elif approval_type in ("validation", "confirmation"):
        # Aceptar "sí", "si", "yes", "true", "1", "confirmo", "apruebo", "ok"
        if isinstance(response, str):
            resp_lower = response.lower().strip()
            # Check exact match or if any keyword is present in the response
            accepted = ("sí", "si", "yes", "true", "1", "confirmo", "apruebo", "ok", "s")
            return resp_lower in accepted or any(kw in resp_lower for kw in accepted)
        return bool(response)

    elif approval_type == "input":
        return str(response) if response is not None else ""

    return response


def get_pending_approvals() -> list[ApprovalRequest]:
    """Obtiene todas las solicitudes pendientes."""
    approvals = []
    for path in PENDING_DIR.glob("*.json"):
        try:
            data = json.loads(path.read_text())
            req = ApprovalRequest.from_dict(data)
            if req.is_expired():
                req.status = "expired"
                req.save_completed()
            else:
                approvals.append(req)
        except Exception:
            pass
    return sorted(approvals, key=lambda r: r.created_at)


def complete_approval(request_id: str, response: Any) -> bool:
    """
    Marca una solicitud como completada con la respuesta dada.
    Usado por el bot de Telegram cuando el Líder responde.
    """
    # Buscar en pending
    pending_path = PENDING_DIR / f"{request_id}.json"
    if not pending_path.exists():
        # Buscar en completed (ya respondida)
        completed_path = COMPLETED_DIR / f"{request_id}.json"
        if completed_path.exists():
            return False  # Ya procesada
        return False  # No existe

    try:
        data = json.loads(pending_path.read_text())
        req = ApprovalRequest.from_dict(data)
        req.status = "completed"
        req.response = response
        req.responded_at = datetime.now(UTC).isoformat()
        req.save_completed()
        print(f"✅ [Approval {request_id}] Completada con respuesta")
        return True
    except Exception as e:
        print(f"❌ Error completando approval {request_id}: {e}")
        return False


def cancel_approval(request_id: str) -> bool:
    """Cancela una solicitud pendiente."""
    pending_path = PENDING_DIR / f"{request_id}.json"
    if not pending_path.exists():
        return False

    try:
        data = json.loads(pending_path.read_text())
        req = ApprovalRequest.from_dict(data)
        req.status = "cancelled"
        req.save_completed()
        return True
    except Exception:
        return False


# CLI para testing manual
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Uso:")
        print("  python -m core.prometeo_approval request <type> <prompt> [context_json]")
        print("  python -m core.prometeo_approval pending")
        print("  python -m core.prometeo_approval complete <id> <response>")
        print("  python -m core.prometeo_approval cancel <id>")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "request":
        if len(sys.argv) < 4:
            print("Faltan argumentos: type prompt [context]")
            sys.exit(1)
        a_type: ApprovalType = sys.argv[2]  # type: ignore[assignment]
        prompt = sys.argv[3]
        context = json.loads(sys.argv[4]) if len(sys.argv) > 4 else {}
        try:
            result = request_approval(a_type, prompt, context, timeout_seconds=60)
            print(f"Resultado: {result}")
        except TimeoutError:
            print("Timeout")
        except Exception as e:
            print(f"Error: {e}")

    elif cmd == "pending":
        pending = get_pending_approvals()
        if not pending:
            print("Sin solicitudes pendientes")
        for req in pending:
            print(f"  {req.id} [{req.type}] {req.prompt[:60]}... ({req.created_at})")

    elif cmd == "complete":
        if len(sys.argv) < 4:
            print("Faltan argumentos: id response")
            sys.exit(1)
        req_id = sys.argv[2]
        response = sys.argv[3]
        if complete_approval(req_id, response):
            print(f"Solicitud {req_id} completada")
        else:
            print(f"Solicitud {req_id} no encontrada o ya procesada")

    elif cmd == "cancel":
        if len(sys.argv) < 3:
            print("Falta id")
            sys.exit(1)
        if cancel_approval(sys.argv[2]):
            print("Cancelada")
        else:
            print("No encontrada")
