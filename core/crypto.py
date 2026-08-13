"""
Módulo criptográfico centralizado — Estación H2O Maracaibo
===========================================================
Única fuente de verdad para hashing de teléfonos y datos sensibles.
Evita divergencias entre bridge, consumer, seed_data y futuros módulos.

Principios:
- Un solo LOG_SALT (desde config/.env, validado en bridge.py)
- Una sola función hash_phone() usada por TODOS los componentes
- Determinista, auditable, testeable
"""

import hashlib
from typing import Final

# LOG_SALT se inyecta desde bridge.py al importar este módulo
# (bridge.py valida que no sea el default inseguro antes de arrancar)
_LOG_SALT: str | None = None


def set_log_salt(salt: str) -> None:
    """Inyecta el LOG_SALT validado. Debe llamarse UNA VEZ al startup.
    Idempotente: permite re-set con el mismo valor (útil en tests)."""
    global _LOG_SALT
    if _LOG_SALT is not None:
        if salt == _LOG_SALT:
            return  # Idempotente: mismo valor, no-op
        raise RuntimeError("LOG_SALT ya fue inicializado con valor distinto — no se permite re-set")
    if not salt or salt == "change-this-in-production":
        # Respetar bypass de bridge.py para tests/dev
        import os

        if not os.getenv("BRIDGE_ALLOW_INSECURE_SALT"):
            raise ValueError("LOG_SALT inseguro: debe ser >= 32 chars aleatorios")
    _LOG_SALT = salt


def get_log_salt() -> str:
    """Retorna el LOG_SALT actual. Lanza si no inicializado."""
    if _LOG_SALT is None:
        raise RuntimeError("LOG_SALT no inicializado — llamar set_log_salt() primero")
    return _LOG_SALT


def hash_phone(phone: str) -> str:
    """
    Hash determinista de teléfono para usar como phone_hash en BD.

    Args:
        phone: Teléfono en formato E.164 (ej: +584121234567)

    Returns:
        str: SHA-256(LOG_SALT:phone)[:32] — 32 chars hex, colisión ~2^-128

    Raises:
        RuntimeError: si LOG_SALT no fue inicializado
        ValueError: si phone es vacío/None
    """
    if not phone:
        raise ValueError("phone no puede ser vacío")
    salt = get_log_salt()
    # Formato: "salt:phone" — el separador ':' evita colisiones por prefijos
    data = f"{salt}:{phone}".encode()
    return hashlib.sha256(data).hexdigest()[:32]


def hash_phone_legacy(phone: str) -> str:
    """
    Hash LEGACY usado por seed_data.py y consumer.py ANTES de la unificación.
    SHA-256(phone)[:16] — SIN salt, 16 chars.

    SOLO para migración de datos existentes. NO usar en código nuevo.
    """
    if not phone:
        raise ValueError("phone no puede ser vacío")
    return hashlib.sha256(phone.encode()).hexdigest()[:16]


# Constantes de dominio para consistencia
PHONE_HASH_LENGTH: Final[int] = 32
LEGACY_PHONE_HASH_LENGTH: Final[int] = 16


# Utilidad de verificación (útil en tests y migraciones)
def is_legacy_hash(hash_value: str) -> bool:
    """Detecta si un hash en BD es del formato legacy (16 chars)."""
    return len(hash_value) == LEGACY_PHONE_HASH_LENGTH


def is_current_hash(hash_value: str) -> bool:
    """Verifica si un hash tiene el formato actual (32 chars)."""
    return len(hash_value) == PHONE_HASH_LENGTH
