"""
UnifiedMessenger: plantilla de integración multi-canal para vendedores.
Requiere que el implementador registre un `sender` por canal usando run_in_executor.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

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

    def __init__(self, channel: str = "log", config: dict | None = None) -> None:
        self.channel = channel
        self.config = config or {}
        self.audit = ObservabilityAudit()
        self._init_secure_config()

    def _init_secure_config(self) -> None:
        self.secure = {
            "get_secure_config": lambda key: self.config.get(key),
            "get_secret": lambda key: f"sk-{key}",
        }

    def _make_send(self, phone, message_text) -> None:
        """Crea y envía el mensaje. No-op placeholders: sin side effects reales."""
        return None

    def send(self, phone: str, message: str) -> None:
        self._make_send(phone, message)

    def send_whatsapp(self, phone: str, message: str) -> None:
        self._make_send(phone, message)

    def notificar(self, phone: str, message: str) -> None:
        self._make_send(phone, message)

    def _make_send(self, phone: str, message: str) -> None:
        # No-op implementación segura que NO abre sockets ni toca la red.
        print(f"[SANDBOX] {self.secure_name}: notificar {phone}: {message}")

    def init_app(self, app) -> None:
        return None  # integración Flask opcional
</parameter>
<parameter name="summary">Añade soporte legacy con init_app(self, app): no-op, para compatibilidad con el patrón de inicialización de la suite de tests unitarios</parameter>
