#!/usr/bin/env python3
"""
HMAC-SHA256 Authentication para R4 Conecta V3.0
13 patrones de firma por endpoint según especificación oficial.

Cada endpoint tiene su string a firmar único (combinación específica de campos).
El HMAC se genera con SHA256 usando el Commerce Token como llave.
Resultado en hex uppercase.
"""

import hashlib
import hmac
from dataclasses import dataclass
from enum import Enum
from typing import Any


class R4Endpoint(str, Enum):
    """Endpoints R4 Conecta con sus patrones de firma HMAC."""

    # Consultas
    R4BCV = "R4bcv"  # Consultar tasa BCV
    R4CONSULTA = "R4consulta"  # Consulta/validación cliente
    R4NOTIFICA = "R4notifica"  # Notificación pago móvil entrante

    # Operaciones financieras
    R4VUELTO = "R4vuelto"  # Vuelto interbancario
    GENERAR_OTP = "GenerarOtp"  # Generar OTP para débito
    DEBITO_INMEDIATO = "DebitoInmediato"  # Débito inmediato
    CREDITO_INMEDIATO = "CreditoInmediato"  # Crédito inmediato
    CI_CUENTAS = "CICuentas"  # Crédito inmediato cuentas 20 dígitos
    DOMICILIACION_CNTA = "DomiciliacionCNTA"  # Domiciliación por cuenta 20 dígitos
    DOMICILIACION_CELE = "DomiciliacionCELE"  # Domiciliación por teléfono
    CONSULTAR_OPERACIONES = "ConsultarOperaciones"  # Consulta estado operación

    # C2P (Comercio a Persona / Banco → Comercio)
    R4C2P = "R4c2p"  # Cobro C2P
    R4ANULACION_C2P = "R4anulacionC2P"  # Anulación C2P


@dataclass(frozen=True)
class HMACPattern:
    """Patrón HMAC para un endpoint específico."""

    endpoint: R4Endpoint
    # Campos en orden exacto para concatenar (según PDF)
    fields: tuple[str, ...]
    # Descripción del string a firmar
    description: str
    # Headers requeridos adicionales
    extra_headers: tuple[str, ...] = ()


# ============================================================
# 13 PATRONES HMAC OFICIALES - Extraídos del PDF R4 Conecta V3.0
# ============================================================

HMAC_PATTERNS: dict[R4Endpoint, HMACPattern] = {
    R4Endpoint.R4BCV: HMACPattern(
        endpoint=R4Endpoint.R4BCV,
        fields=("Fechavalor", "Moneda"),
        description="Fechavalor + Moneda",
        extra_headers=(),
    ),
    R4Endpoint.R4CONSULTA: HMACPattern(
        endpoint=R4Endpoint.R4CONSULTA,
        fields=("IdCliente", "Monto", "TelefonoComercio"),
        description="IdCliente + Monto + TelefonoComercio",
        extra_headers=(),
    ),
    R4Endpoint.R4NOTIFICA: HMACPattern(
        endpoint=R4Endpoint.R4NOTIFICA,
        fields=(
            "IdComercio",
            "TelefonoComercio",
            "TelefonoEmisor",
            "Concepto",
            "BancoEmisor",
            "Monto",
            "FechaHora",
            "Referencia",
            "CodigoRed",
        ),
        description=(
            "IdComercio + TelefonoComercio + TelefonoEmisor + "
            "Concepto + BancoEmisor + Monto + FechaHora + "
            "Referencia + CodigoRed"
        ),
        extra_headers=(),
    ),
    R4Endpoint.R4VUELTO: HMACPattern(
        endpoint=R4Endpoint.R4VUELTO,
        fields=("TelefonoDestino", "Monto", "Banco", "Cedula"),
        description="TelefonoDestino + Monto + Banco + Cedula",
        extra_headers=(),
    ),
    R4Endpoint.GENERAR_OTP: HMACPattern(
        endpoint=R4Endpoint.GENERAR_OTP,
        fields=("Banco", "Monto", "Telefono", "Cedula"),
        description="Banco + Monto + Telefono + Cedula",
        extra_headers=(),
    ),
    R4Endpoint.DEBITO_INMEDIATO: HMACPattern(
        endpoint=R4Endpoint.DEBITO_INMEDIATO,
        fields=("Banco", "Cedula", "Telefono", "Monto", "OTP"),
        description="Banco + Cedula + Telefono + Monto + OTP",
        extra_headers=(),
    ),
    R4Endpoint.CREDITO_INMEDIATO: HMACPattern(
        endpoint=R4Endpoint.CREDITO_INMEDIATO,
        fields=("Banco", "Cedula", "Telefono", "Monto"),
        description="Banco + Cedula + Telefono + Monto",
        extra_headers=(),
    ),
    R4Endpoint.CI_CUENTAS: HMACPattern(
        endpoint=R4Endpoint.CI_CUENTAS,
        fields=("Cedula", "Cuenta", "Monto"),
        description="Cedula + Cuenta + Monto",
        extra_headers=(),
    ),
    R4Endpoint.DOMICILIACION_CNTA: HMACPattern(
        endpoint=R4Endpoint.DOMICILIACION_CNTA,
        fields=("cuenta",),  # lowercase según PDF: "cuenta"
        description="cuenta",
        extra_headers=(),
    ),
    R4Endpoint.DOMICILIACION_CELE: HMACPattern(
        endpoint=R4Endpoint.DOMICILIACION_CELE,
        fields=("telefono",),  # lowercase según PDF: "telefono"
        description="telefono",
        extra_headers=(),
    ),
    R4Endpoint.CONSULTAR_OPERACIONES: HMACPattern(
        endpoint=R4Endpoint.CONSULTAR_OPERACIONES,
        fields=("Id",),
        description="Id",
        extra_headers=(),
    ),
    R4Endpoint.R4C2P: HMACPattern(
        endpoint=R4Endpoint.R4C2P,
        fields=("TelefonoDestino", "Monto", "Banco", "Cedula"),
        description="TelefonoDestino + Monto + Banco + Cedula",
        extra_headers=(),
    ),
    R4Endpoint.R4ANULACION_C2P: HMACPattern(
        endpoint=R4Endpoint.R4ANULACION_C2P,
        fields=("Banco",),
        description="Banco",
        extra_headers=(),
    ),
}


def build_sign_string(payload: dict[str, Any], endpoint: R4Endpoint) -> str:
    """
    Construye el string a firmar para un endpoint.

    Concatena los valores de los campos en orden exacto según el patrón.
    Los valores se convierten a string y se concatenan SIN separadores.

    Args:
        payload: Diccionario con los datos del request
        endpoint: Endpoint R4 para determinar el patrón

    Returns:
        String concatenado listo para firmar con HMAC-SHA256

    Raises:
        KeyError: Si falta un campo requerido en el payload
        ValueError: Si el endpoint no tiene patrón definido
    """
    pattern = HMAC_PATTERNS.get(endpoint)
    if not pattern:
        raise ValueError(f"No HMAC pattern defined for endpoint: {endpoint}")

    parts = []
    for field in pattern.fields:
        if field not in payload:
            raise KeyError(f"Missing required field '{field}' for endpoint {endpoint.value}")
        value = payload[field]
        # Convertir a string (maneja int, float, etc.)
        parts.append(str(value))

    return "".join(parts)


def compute_hmac_sha256(sign_string: str, commerce_token: str) -> str:
    """
    Calcula HMAC-SHA256 del string usando Commerce Token como llave.

    Args:
        sign_string: String a firmar (output de build_sign_string)
        commerce_token: Commerce Token proporcionado por el banco

    Returns:
        HMAC en hexadecimal UPPERCASE (formato requerido por el banco)
    """
    if not commerce_token:
        raise ValueError("Commerce token is required for HMAC computation")

    hmac_obj = hmac.new(commerce_token.encode("utf-8"), sign_string.encode("utf-8"), hashlib.sha256)
    return hmac_obj.hexdigest().upper()


def build_auth_headers(
    payload: dict[str, Any], endpoint: R4Endpoint, commerce_token: str
) -> dict[str, str]:
    """
    Construye headers completos para request R4 Conecta.

    Args:
        payload: Datos del request (body JSON)
        endpoint: Endpoint R4
        commerce_token: Commerce Token del banco

    Returns:
        Dict con headers listos para usar en requests
    """
    sign_string = build_sign_string(payload, endpoint)
    authorization = compute_hmac_sha256(sign_string, commerce_token)

    headers = {
        "Content-Type": "application/json",
        "Authorization": authorization,
        "Commerce": commerce_token,
    }
    return headers


def verify_hmac_signature(
    payload: dict[str, Any], endpoint: R4Endpoint, received_authorization: str, commerce_token: str
) -> bool:
    """
    Verifica firma HMAC entrante (para webhooks del banco → nosotros).

    Args:
        payload: Body del request recibido
        endpoint: Endpoint que recibió el request
        received_authorization: Header Authorization recibido
        commerce_token: Nuestro Commerce Token

    Returns:
        True si la firma es válida
    """
    try:
        sign_string = build_sign_string(payload, endpoint)
        expected = compute_hmac_sha256(sign_string, commerce_token)
        # Comparación timing-safe
        return hmac.compare_digest(expected, received_authorization.upper())
    except (KeyError, ValueError):
        return False


def get_sign_string_description(endpoint: R4Endpoint) -> str:
    """Obtiene descripción legible del string a firmar para un endpoint."""
    pattern = HMAC_PATTERNS.get(endpoint)
    if not pattern:
        return f"Endpoint {endpoint.value} no tiene patrón HMAC definido"
    return pattern.description


# ============================================================
# Funciones de conveniencia por endpoint
# ============================================================


def sign_r4bcv(payload: dict[str, Any], commerce_token: str) -> dict[str, str]:
    """Headers para consultar tasa BCV (R4bcv)."""
    return build_auth_headers(payload, R4Endpoint.R4BCV, commerce_token)


def sign_r4consulta(payload: dict[str, Any], commerce_token: str) -> dict[str, str]:
    """Headers para consulta/validación cliente (R4consulta)."""
    return build_auth_headers(payload, R4Endpoint.R4CONSULTA, commerce_token)


def sign_r4notifica(payload: dict[str, Any], commerce_token: str) -> dict[str, str]:
    """Headers para notificación pago entrante (R4notifica)."""
    return build_auth_headers(payload, R4Endpoint.R4NOTIFICA, commerce_token)


def sign_r4vuelto(payload: dict[str, Any], commerce_token: str) -> dict[str, str]:
    """Headers para vuelto interbancario (R4vuelto)."""
    return build_auth_headers(payload, R4Endpoint.R4VUELTO, commerce_token)


def sign_generar_otp(payload: dict[str, Any], commerce_token: str) -> dict[str, str]:
    """Headers para generar OTP (GenerarOtp)."""
    return build_auth_headers(payload, R4Endpoint.GENERAR_OTP, commerce_token)


def sign_debito_inmediato(payload: dict[str, Any], commerce_token: str) -> dict[str, str]:
    """Headers para débito inmediato (DebitoInmediato)."""
    return build_auth_headers(payload, R4Endpoint.DEBITO_INMEDIATO, commerce_token)


def sign_credito_inmediato(payload: dict[str, Any], commerce_token: str) -> dict[str, str]:
    """Headers para crédito inmediato (CreditoInmediato)."""
    return build_auth_headers(payload, R4Endpoint.CREDITO_INMEDIATO, commerce_token)


def sign_ci_cuentas(payload: dict[str, Any], commerce_token: str) -> dict[str, str]:
    """Headers para crédito inmediato cuentas 20 dígitos (CICuentas)."""
    return build_auth_headers(payload, R4Endpoint.CI_CUENTAS, commerce_token)


def sign_domiciliacion_cnta(payload: dict[str, Any], commerce_token: str) -> dict[str, str]:
    """Headers para domiciliación por cuenta (DomiciliacionCNTA)."""
    return build_auth_headers(payload, R4Endpoint.DOMICILIACION_CNTA, commerce_token)


def sign_domiciliacion_cele(payload: dict[str, Any], commerce_token: str) -> dict[str, str]:
    """Headers para domiciliación por teléfono (DomiciliacionCELE)."""
    return build_auth_headers(payload, R4Endpoint.DOMICILIACION_CELE, commerce_token)


def sign_consultar_operaciones(payload: dict[str, Any], commerce_token: str) -> dict[str, str]:
    """Headers para consultar operaciones (ConsultarOperaciones)."""
    return build_auth_headers(payload, R4Endpoint.CONSULTAR_OPERACIONES, commerce_token)


def sign_r4c2p(payload: dict[str, Any], commerce_token: str) -> dict[str, str]:
    """Headers para cobro C2P (R4c2p)."""
    return build_auth_headers(payload, R4Endpoint.R4C2P, commerce_token)


def sign_r4anulacion_c2p(payload: dict[str, Any], commerce_token: str) -> dict[str, str]:
    """Headers para anulación C2P (R4anulacionC2P)."""
    return build_auth_headers(payload, R4Endpoint.R4ANULACION_C2P, commerce_token)


# ============================================================
# Exports
# ============================================================

__all__ = [
    # Enums & Types
    "R4Endpoint",
    "HMACPattern",
    "HMAC_PATTERNS",
    # Core functions
    "build_sign_string",
    "compute_hmac_sha256",
    "build_auth_headers",
    "verify_hmac_signature",
    "get_sign_string_description",
    # Convenience functions
    "sign_r4bcv",
    "sign_r4consulta",
    "sign_r4notifica",
    "sign_r4vuelto",
    "sign_generar_otp",
    "sign_debito_inmediato",
    "sign_credito_inmediato",
    "sign_ci_cuentas",
    "sign_domiciliacion_cnta",
    "sign_domiciliacion_cele",
    "sign_consultar_operaciones",
    "sign_r4c2p",
    "sign_r4anulacion_c2p",
]


if __name__ == "__main__":
    # Demo / test
    import os

    # Mock commerce token
    COMMERCE_TOKEN = os.getenv("R4_COMMERCE_TOKEN", "test_commerce_token_12345")

    print("=== HMAC Patterns R4 Conecta V3.0 ===\n")

    for endpoint, pattern in HMAC_PATTERNS.items():
        print(f"📌 {endpoint.value}")
        print(f"   String a firmar: {pattern.description}")
        print(f"   Campos: {', '.join(pattern.fields)}")
        print()

    # Test real signing
    print("=== Test Signing ===\n")

    # Test R4bcv
    payload_bcv = {"Moneda": "USD", "Fechavalor": "2024-07-23"}
    headers = sign_r4bcv(payload_bcv, COMMERCE_TOKEN)
    print(f"R4bcv headers: {headers}")

    # Test R4consulta
    payload_consulta = {
        "IdCliente": "13536734",
        "Monto": "135.36",
        "TelefonoComercio": "04129196699",
    }
    headers = sign_r4consulta(payload_consulta, COMMERCE_TOKEN)
    print(f"R4consulta headers: {headers}")

    # Test R4notifica
    payload_notifica = {
        "IdComercio": "13536734",
        "TelefonoComercio": "04125555555",
        "TelefonoEmisor": "04145555555",
        "Concepto": "PRUEBA",
        "BancoEmisor": "134",
        "Monto": "123.13",
        "FechaHora": "2024-12-05T16:50:48.421Z",
        "Referencia": "83736278",
        "CodigoRed": "00",
    }
    headers = sign_r4notifica(payload_notifica, COMMERCE_TOKEN)
    print(f"R4notifica headers: {headers}")

    # Verify signature
    print("\n=== Verification Test ===")
    sign_str = build_sign_string(payload_bcv, R4Endpoint.R4BCV)
    expected = compute_hmac_sha256(sign_str, COMMERCE_TOKEN)
    print(f"Sign string: {sign_str}")
    print(f"Expected HMAC: {expected}")
    print(
        f"Verify OK: {verify_hmac_signature(payload_bcv, R4Endpoint.R4BCV, expected, COMMERCE_TOKEN)}"
    )
    print(
        f"Verify FAIL: {verify_hmac_signature(payload_bcv, R4Endpoint.R4BCV, 'INVALID', COMMERCE_TOKEN)}"
    )
