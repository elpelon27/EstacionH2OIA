"""
UnifiedMessenger: plantilla de integración multi-canal para vendedores.
Requiere que el implementador registre un `sender` por canal usando run_in_executor.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

MessageSender = Callable[[str, str], None]


def _noop(channel: str, content: str, dest: str) -> None:
    """Sender no-operativo: registra el intento y devuelve (no envía nada)."""
    print(f"[dry-run:{channel}] -> {dest}: {content[:60]}{'...' if len(content) > 60 else ''}")


@dataclass
class ObservabilityAggregator:
    """Agrega métricas de envío de mensajes WhatsApp/Telegram."""
    total_sent: int = 0

    def record(self, destination: str, body: str) -> None:
        # registro local mínimo: no red, no IO
        self.total_sent += 1


@dataclass
class UnifiedMessageSender:
    """
    Gateway unificado para enviar mensajes a múltiples canales sin acoplar
    al código de producción. Puntos de extensión: WhatsApp / Telegram / Email.
    """
    gateway: str = "blackhole"
    channel: str = "log"

    def __init__(self, channel: str = "log", config: dict[str, Any] | None = None) -> None:
        self.channel = channel
        self.config = config or {}
        self.audit = ObservabilityAggregator()
        self._init_secure_config()

    def _init_secure_config(self) -> None:
        self.secure = {
            "get_secure_config": lambda key: self.config.get(key),
            "get_secret": lambda key: f"sk-{key}",
        }
        self.secure_name = self.channel

    def _make_send(self, phone: str, message: str) -> None:
        """Crea y envía el mensaje. No-op placeholder: sin side effects reales."""
        print(f"[SANDBOX] {self.secure_name}: notificar {phone}: {message}")

    def send(self, phone: str, message: str) -> None:
        self._make_send(phone, message)

    def send_whatsapp(self, phone: str, message: str) -> None:
        self._make_send(phone, message)

    def notificar(self, phone: str, message: str) -> None:
        self._make_send(phone, message)

    def init_app(self, app: Any) -> None:
        return None  # integración Flask opcional
