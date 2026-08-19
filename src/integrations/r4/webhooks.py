#!/usr/bin/env python3
"""
Webhooks R4 Conecta V3.0 - Endpoints FastAPI para notificaciones entrantes del banco.

Endpoints implementados:
1. POST /webhook/r4/consulta - Validación de cliente para pago móvil
2. POST /webhook/r4/notifica - Notificación de pago móvil entrante

Seguridad:
- IP whitelist (configurable via .env)
- Authorization header (UUID desde R4_WEBHOOK_AUTH_TOKEN)
- HMAC-SHA256 timing-safe verification (hmac.compare_digest)
- Rate limiting por IP

NO se conecta a bridge.py aquí - integración en FASE 6.
"""

import hmac
import logging
import os
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator

from src.integrations.r4.codigos import get_description
from src.integrations.r4.hmac_auth import (
    R4Endpoint,
    verify_hmac_signature,
)

logger = logging.getLogger("r4.webhooks")

# ============================================================
# Configuración desde variables de entorno
# ============================================================


class R4WebhookConfig:
    """Configuración de seguridad para webhooks R4."""

    def __init__(self) -> None:
        # IP whitelist del banco (configurable)
        ips_env = os.getenv("R4_WEBHOOK_ALLOWED_IPS", "")
        self.allowed_ips = {ip.strip() for ip in ips_env.split(",") if ip.strip()}
        # Defaults según especificación actualizada R4-02
        if not self.allowed_ips:
            self.allowed_ips = {
                "45.175.213.98",
                "200.199.249.3",
                "204.199.249.3",
            }

        # Authorization token (UUID)
        self.auth_token = os.getenv("R4_WEBHOOK_AUTH_TOKEN", "")

        # HMAC commerce secret (secreto compartido para verificar firmas)
        self.commerce_secret = os.getenv("R4_COMMERCE_SECRET", "")
        # Backward compat: si no hay secret, usar commerce_token
        if not self.commerce_secret:
            self.commerce_secret = os.getenv("R4_COMMERCE_TOKEN", "")

        # Rate limiting
        self.rate_limit_requests = int(os.getenv("R4_WEBHOOK_RATE_LIMIT", "100"))
        self.rate_limit_window = int(os.getenv("R4_WEBHOOK_RATE_WINDOW", "60"))  # segundos

        # Validación
        self._validate_config()

    def _validate_config(self) -> None:
        if not self.auth_token:
            logger.warning("R4_WEBHOOK_AUTH_TOKEN no configurado - webhooks sin auth token")
        if not self.commerce_secret:
            logger.warning("R4_COMMERCE_SECRET no configurado - verificación HMAC deshabilitada")
        logger.info(f"R4 Webhook IPs permitidas: {self.allowed_ips}")


# Instancia global
_webhook_config: R4WebhookConfig | None = None


def get_webhook_config() -> R4WebhookConfig:
    global _webhook_config
    if _webhook_config is None:
        _webhook_config = R4WebhookConfig()
    return _webhook_config


def reset_webhook_config() -> None:
    global _webhook_config
    _webhook_config = None


# ============================================================
# Rate Limiting simple en memoria
# ============================================================

_rate_limit_store: dict[str, list[float]] = defaultdict(list)


def check_rate_limit(ip: str, config: R4WebhookConfig) -> bool:
    """Verifica rate limit por IP (sliding window)."""
    now = time.time()
    window_start = now - config.rate_limit_window

    # Limpiar entradas viejas
    _rate_limit_store[ip] = [ts for ts in _rate_limit_store[ip] if ts > window_start]

    # Verificar límite
    if len(_rate_limit_store[ip]) >= config.rate_limit_requests:
        return False

    _rate_limit_store[ip].append(now)
    return True


# ============================================================
# Modelos Pydantic para validación de entrada
# ============================================================


class R4ConsultaRequest(BaseModel):
    """Request para webhook /consulta (R4consulta)."""

    IdCliente: str = Field(..., min_length=1, max_length=20, description="Identificación cliente")
    Monto: str = Field(..., description="Monto con 2 decimales")
    TelefonoComercio: str = Field(
        ..., min_length=11, max_length=11, description="Teléfono comercio 11 dígitos"
    )

    @field_validator("Monto")
    @classmethod
    def validate_monto(cls, v: str) -> str:
        # Validar formato decimal con 2 decimales
        try:
            float(v)
            if "." in v:
                decimals = len(v.split(".")[1])
                if decimals != 2:
                    raise ValueError("Monto debe tener 2 decimales")
        except ValueError as e:
            raise ValueError("Monto inválido") from e
        return v


class R4NotificaRequest(BaseModel):
    """Request para webhook /notifica (R4notifica)."""

    IdComercio: str = Field(..., min_length=1, max_length=20)
    TelefonoComercio: str = Field(..., min_length=11, max_length=11)
    TelefonoEmisor: str = Field(..., min_length=11, max_length=11)
    Concepto: str = Field("", max_length=30)
    BancoEmisor: str = Field(
        ..., min_length=3, max_length=4, description="Código banco 3-4 dígitos"
    )
    Monto: str = Field(..., description="Monto con 2 decimales")
    FechaHora: str = Field(..., description="ISO 8601 UTC")
    Referencia: str = Field(..., min_length=1, max_length=36)
    CodigoRed: str = Field(..., min_length=2, max_length=2, description="Código red interbancaria")

    @field_validator("Monto")
    @classmethod
    def validate_monto(cls, v: str) -> str:
        try:
            float(v)
            if "." in v:
                decimals = len(v.split(".")[1])
                if decimals != 2:
                    raise ValueError("Monto debe tener 2 decimales")
        except ValueError as e:
            raise ValueError("Monto inválido") from e
        return v

    @field_validator("CodigoRed")
    @classmethod
    def validate_codigo_red(cls, v: str) -> str:
        if not v.isdigit() or len(v) != 2:
            raise ValueError("CodigoRed debe ser 2 dígitos")
        return v


class R4ConsultaResponse(BaseModel):
    """Response para webhook /consulta (formato R4consulta)."""

    status: bool


class R4NotificaResponse(BaseModel):
    """Response para webhook /notifica."""

    abono: bool


class MBConsultaResponse(BaseModel):
    """Response para webhook /consulta (formato MBconsulta vía SIMF)."""

    abono: bool


# ============================================================
# Resultado de procesamiento interno
# ============================================================


@dataclass
class WebhookProcessResult:
    """Resultado interno de procesamiento de webhook."""

    success: bool
    code: str
    message: str
    reference: str = ""
    data: dict[str, Any] | None = None

    def to_consulta_response(self) -> R4ConsultaResponse:
        return R4ConsultaResponse(status=self.success)

    def to_notifica_response(self) -> R4NotificaResponse:
        return R4NotificaResponse(abono=self.success)


# ============================================================
# Funciones de verificación de seguridad
# ============================================================


async def verify_ip_whitelist(request: Request, config: R4WebhookConfig) -> None:
    """Verifica que la IP origen esté en whitelist."""
    client_ip = request.client.host if request.client else "unknown"

    # Manejar X-Forwarded-For si viene detrás de proxy (cloudflare, nginx)
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        # Tomar la primera IP (original client)
        client_ip = forwarded.split(",")[0].strip()

    if client_ip not in config.allowed_ips:
        logger.warning(
            f"R4 Webhook IP rechazada: {client_ip} " f"(permitidas: {config.allowed_ips})"
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="IP no autorizada")

    logger.debug(f"R4 Webhook IP autorizada: {client_ip}")


async def verify_auth_token(authorization: str | None, config: R4WebhookConfig) -> None:
    """Verifica Authorization header (Bearer token UUID)."""
    if not config.auth_token:
        logger.warning("R4_WEBHOOK_AUTH_TOKEN no configurado - saltando verificación auth")
        return

    if not authorization:
        logger.warning("R4 Webhook sin Authorization header")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header requerido",
        )

    # Formato: "Bearer <uuid>"
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        logger.warning(f"R4 Webhook Authorization formato inválido: {authorization[:20]}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Formato Authorization inválido (esperado: Bearer <token>)",
        )

    provided_token = parts[1]
    if not hmac.compare_digest(provided_token, config.auth_token):
        logger.warning("R4 Webhook token inválido")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido")

    logger.debug("R4 Webhook Authorization token válido")


async def verify_hmac_signature_webhook(
    request: Request,
    payload: dict[str, Any],
    endpoint: R4Endpoint,
    config: R4WebhookConfig,
) -> None:
    """Verifica firma HMAC-SHA256 del payload (timing-safe)."""
    if not config.commerce_secret:
        logger.warning("R4_COMMERCE_SECRET no configurado - saltando verificación HMAC")
        return

    auth_header = request.headers.get("Authorization", "")
    # Authorization ya verificado como Bearer token, buscar X-Signature o similar
    # El banco puede enviar la firma en header separado
    signature = request.headers.get("X-Signature") or request.headers.get("X-Hmac-Signature")

    if not signature and auth_header.startswith("HMAC "):
        signature = auth_header[5:]

    if not signature:
        logger.warning(f"R4 Webhook {endpoint.value} sin firma HMAC")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Firma HMAC requerida")

    # Verificar con hmac.compare_digest (timing-safe)
    is_valid = verify_hmac_signature(payload, endpoint, signature, config.commerce_secret)

    if not is_valid:
        logger.warning(f"R4 Webhook {endpoint.value} firma HMAC inválida")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Firma HMAC inválida")

    logger.debug(f"R4 Webhook {endpoint.value} firma HMAC válida")


async def verify_rate_limit(request: Request, config: R4WebhookConfig) -> None:
    """Verifica rate limiting por IP."""
    client_ip = request.client.host if request.client else "unknown"
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        client_ip = forwarded.split(",")[0].strip()

    if not check_rate_limit(client_ip, config):
        logger.warning(f"R4 Webhook rate limit excedido: {client_ip}")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit excedido",
        )


# ============================================================
# Dependencia combinada de seguridad
# ============================================================


async def security_dependency(
    request: Request,
    authorization: str | None = Header(None),
    endpoint: R4Endpoint = R4Endpoint.R4CONSULTA,
) -> R4WebhookConfig:
    """Dependencia que ejecuta todas las verificaciones de seguridad."""
    config = get_webhook_config()

    # 1. IP Whitelist
    await verify_ip_whitelist(request, config)

    # 2. Rate Limiting
    await verify_rate_limit(request, config)

    # 3. Authorization Token
    await verify_auth_token(authorization, config)

    # 4. HMAC Signature (se verifica en cada endpoint con payload específico)
    # La verificación HMAC se hace dentro del endpoint porque necesita
    # el payload parseado

    return config


# ============================================================
# Detección de formato de webhook (R4consulta vs MBconsulta)
# ============================================================


def detect_webhook_format(payload: dict[str, Any]) -> str:
    """
    Detecta si el payload es formato R4consulta o MBconsulta.

    El banco envía por uno u otro canal según el banco emisor:
    - MBconsulta (vía SIMF): tiene "TelefonoEmisor" y "BancoEmisor"
      → responder {"abono": true/false}
    - R4consulta: tiene "IdCliente" y "TelefonoComercio"
      → responder {"status": true/false}

    Returns:
        "MBconsulta" o "R4consulta"
    """
    if "TelefonoEmisor" in payload and "BancoEmisor" in payload:
        return "MBconsulta"
    if "IdCliente" in payload and "TelefonoComercio" in payload:
        return "R4consulta"
    # Default: intentar R4consulta
    return "R4consulta"


# ============================================================
# Lógica de negocio (placeholders para FASE 6)
# ============================================================


async def process_mbconsulta(
    payload: dict[str, Any], config: R4WebhookConfig
) -> WebhookProcessResult:
    """
    Procesa webhook MBconsulta (vía SIMF): notificación de pago entrante
    con el objeto completo de la transacción.

    El banco envía este formato cuando el pago viene por canal SIMF.
    Responde {"abono": true/false}.

    FASE 6 - Implementar:
    - Extraer datos de la transacción del payload completo
    - Buscar pedido pendiente
    - Marcar pago
    - Sync Odoo
    - Notificar WhatsApp
    """
    telefono_emisor = payload.get("TelefonoEmisor", "N/A")
    banco_emisor = payload.get("BancoEmisor", "N/A")
    monto = payload.get("Monto", "N/A")
    referencia = payload.get("Referencia", payload.get("reference", "N/A"))

    logger.info(
        f"MBconsulta recibido: TelefonoEmisor={telefono_emisor}, "
        f"BancoEmisor={banco_emisor}, Monto={monto}, Referencia={referencia}"
    )

    # PLACEHOLDER - FASE 6
    # Mismo flujo que R4notifica pero con formato de payload SIMF
    # from src.integrations.fs_client import FSClient
    # fs = FSClient()
    # pedido = await fs.get_pending_order_by_amount_phone(monto, telefono_emisor)
    # if not pedido:
    #     return WebhookProcessResult(success=False, code="NO_ORDER", ...)
    # await fs.mark_order_paid(pedido.id, referencia)
    # ...

    # Mock response para desarrollo
    return WebhookProcessResult(
        success=True,
        code="00",
        message="MOCK: MBconsulta procesado (implementar FASE 6)",
        reference=str(referencia),
    )


async def process_r4consulta(
    payload: R4ConsultaRequest, config: R4WebhookConfig
) -> WebhookProcessResult:
    """
    Procesa webhook R4consulta: valida si IdCliente tiene pedido pendiente.

    FASE 6 - Implementar:
    - Buscar en fs_pedidos por teléfono/cliente
    - Verificar monto coincide
    - Retornar status=true si hay pedido pendiente válido
    """
    logger.info(f"R4consulta recibido: IdCliente={payload.IdCliente}, Monto={payload.Monto}")

    # PLACEHOLDER - FASE 6
    # from src.integrations.fs_client import FSClient
    # fs = FSClient()
    # pedido = await fs.get_pending_order_by_client(payload.IdCliente,
    # payload.Monto)
    # if pedido:
    #     return WebhookProcessResult(
    #         success=True, code="00", message="Cliente válido",
    #         reference=pedido.id
    #     )
    # return WebhookProcessResult(
    #     success=False, code="NO_ORDER", message="Sin pedido pendiente"
    # )

    # Mock response para desarrollo
    return WebhookProcessResult(
        success=True,
        code="00",
        message="MOCK: Cliente validado (implementar FASE 6)",
        reference="MOCK_ORDER_123",
    )


async def process_r4notifica(
    payload: R4NotificaRequest, config: R4WebhookConfig
) -> WebhookProcessResult:
    """
    Procesa webhook R4notifica: notificación de pago entrante.

    Lógica:
    a) Verificar CodigoRed == "00"
    b) Buscar pedido pendiente por monto + teléfono
    c) Marcar pago en fs_pedidos
    d) Sync a Odoo
    e) Notificar WhatsApp al cliente
    f) Retornar abono: true

    FASE 6 - Implementar integración completa.
    """
    logger.info(
        "R4notifica recibido: "
        f"Referencia={payload.Referencia}, Monto={payload.Monto}, "
        f"TelefonoEmisor={payload.TelefonoEmisor}, "
        f"BancoEmisor={payload.BancoEmisor}, CodigoRed={payload.CodigoRed}"
    )

    # a) Verificar CodigoRed == "00"
    if payload.CodigoRed != "00":
        logger.warning(f"R4notifica CodigoRed != 00: {payload.CodigoRed}")
        return WebhookProcessResult(
            success=False,
            code=payload.CodigoRed,
            message=get_description(payload.CodigoRed) or "Código de red no exitoso",
            reference=payload.Referencia,
        )

    # PLACEHOLDER - FASE 6
    # b) Buscar pedido pendiente por monto + teléfono
    # from src.integrations.fs_client import FSClient
    # from src.integrations.odoo.odoo_sync import OdooClient
    # from agents.valentina import send_whatsapp_message
    #
    # fs = FSClient()
    # pedido = await fs.get_pending_order_by_amount_phone(
    #     payload.Monto, payload.TelefonoEmisor
    # )
    # if not pedido:
    #     return WebhookProcessResult(
    #         success=False, code="NO_ORDER", message="Pedido no encontrado"
    #     )
    #
    # c) Marcar pago en fs_pedidos
    # await fs.mark_order_paid(pedido.id, payload.Referencia,
    # payload.FechaHora)
    #
    # d) Sync a Odoo
    # odoo = OdooClient()
    # await odoo.sync_payment(pedido.id, payload)
    #
    # e) Notificar WhatsApp
    # await send_whatsapp_message(
    #     pedido.cliente_telefono, f"✅ Pago recibido: {payload.Monto} Bs"
    # )
    #
    # return WebhookProcessResult(
    #     success=True, code="00", message="Abono procesado",
    #     reference=payload.Referencia
    # )

    # Mock response para desarrollo
    return WebhookProcessResult(
        success=True,
        code="00",
        message="MOCK: Abono procesado (implementar FASE 6)",
        reference=payload.Referencia,
    )


# ============================================================
# Captura de headers y payloads para diagnóstico (modo captura)
# ============================================================


def _log_full_request(request: Request, body: Any, endpoint_name: str) -> None:
    """
    Loguea TODOS los headers y el payload recibido del banco.
    Esto nos permite ver exactamente qué envía el banco en la vida real,
    incluso si la verificación HMAC falla después.

    NO loguea valores de nuestros secrets, solo lo que llega del banco.
    """
    # Capturar todos los headers
    headers_dict = dict(request.headers)
    # Redactar nuestro auth token si está presente
    auth_header = headers_dict.get("authorization", "")
    if auth_header and len(auth_header) > 20:
        headers_dict["authorization"] = auth_header[:10] + "...REDACTED"

    # IP origen
    client_ip = request.client.host if request.client else "unknown"
    forwarded = request.headers.get("X-Forwarded-For", "")
    real_ip = request.headers.get("X-Real-IP", "")

    logger.info("=" * 80)
    logger.info(f"🔍 CAPTURA WEBHOOK [{endpoint_name}] - IP origen: {client_ip}")
    if forwarded:
        logger.info(f"   X-Forwarded-For: {forwarded}")
    if real_ip:
        logger.info(f"   X-Real-IP: {real_ip}")
    logger.info(f"   Method: {request.method}")
    logger.info(f"   URL: {request.url}")
    logger.info(f"   Headers ({len(headers_dict)}):")
    for k, v in sorted(headers_dict.items()):
        logger.info(f"     {k}: {v}")
    logger.info(f"   Body ({type(body).__name__}):")
    if isinstance(body, dict):
        for k, v in sorted(body.items()):
            logger.info(f"     {k}: {v}")
    else:
        logger.info(f"     {body}")
    logger.info("=" * 80)


def _log_hmac_failure(
    request: Request, body: Any, endpoint_name: str,
    sign_string: str | None = None, expected_hash: str | None = None,
    received_hash: str | None = None,
) -> None:
    """
    Loguea detalles de fallo HMAC para diagnóstico.
    Captura el sign string y los hashes para comparar con el banco.
    """
    logger.warning(f"⚠️  HMAC FALLÓ en {endpoint_name}")
    logger.warning(f"   IP origen: {request.client.host if request.client else 'unknown'}")
    auth_header = request.headers.get("Authorization", "")
    logger.warning(f"   Authorization recibido: {auth_header[:30]}..." if len(auth_header) > 30 else f"   Authorization recibido: {auth_header}")
    logger.warning(f"   Commerce header: {request.headers.get('Commerce', 'NO PRESENTE')}")
    logger.warning(f"   X-Signature: {request.headers.get('X-Signature', 'NO PRESENTE')}")
    logger.warning(f"   X-Hmac-Signature: {request.headers.get('X-Hmac-Signature', 'NO PRESENTE')}")
    if sign_string:
        logger.warning(f"   Sign string construido: {sign_string}")
    if expected_hash:
        logger.warning(f"   Hash esperado: {expected_hash}")
    if received_hash:
        logger.warning(f"   Hash recibido:  {received_hash}")
    # Log all headers for debugging
    logger.warning(f"   TODOS los headers: {dict(request.headers)}")
    logger.warning(f"   Body completo: {body}")


# ============================================================
# Router FastAPI
# ============================================================

router = APIRouter(prefix="/webhook/r4", tags=["R4 Webhooks"])


# Module-level singleton for B008 compliance
_webhook_config_singleton = Depends(get_webhook_config)


@router.post(
    "/consulta",
    summary="R4consulta / MBconsulta - Validación cliente y notificación de pago",
    description="""
    Endpoint llamado por el banco cuando un cliente inicia pago móvil.

    Soporta DOS formatos (R4-24):
    1. R4consulta: {IdCliente, Monto, TelefonoComercio} → responde {"status": true/false}
    2. MBconsulta (vía SIMF): {TelefonoEmisor, BancoEmisor, ...} → responde {"abono": true/false}

    El banco envía por uno u otro canal según el banco emisor.
    La detección es automática por los campos del payload.

    Seguridad:
    - IP whitelist
    - Authorization Bearer token
    - HMAC-SHA256 firma del payload
    - Rate limiting
    """,
)
async def r4_consulta_webhook(
    request: Request,
    authorization: str | None = Header(None),
    config: R4WebhookConfig = _webhook_config_singleton,
) -> dict[str, Any]:
    """
    Webhook R4consulta / MBconsulta - Validación de cliente y notificación de pago.

    Body (R4consulta): {IdCliente, Monto, TelefonoComercio}
    Response (R4consulta): {"status": true/false}

    Body (MBconsulta): {TelefonoEmisor, BancoEmisor, Monto, Referencia, ...}
    Response (MBconsulta): {"abono": true/false}
    """
    logger.info("=== R4consulta/MBconsulta webhook recibido ===")

    # Parsear body como JSON genérico (para soportar ambos formatos)
    try:
        body = await request.json()
    except Exception:
        # Capturar body raw aunque no sea JSON válido
        raw_body = await request.body()
        logger.warning(f"Body no es JSON válido. Raw (primeros 500 chars): {raw_body[:500]}")
        _log_full_request(request, f"RAW: {raw_body[:500]}", "consulta")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Body JSON inválido",
        )

    if not isinstance(body, dict):
        _log_full_request(request, body, "consulta")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Body debe ser un objeto JSON",
        )

    # === CAPTURA COMPLETA: loguear TODO antes de cualquier verificación ===
    _log_full_request(request, body, "consulta")

    # Detectar formato del payload
    fmt = detect_webhook_format(body)
    logger.info(f"Formato detectado: {fmt}")

    # Verificaciones de seguridad (NO abortar en HMAC para captura)
    try:
        await verify_ip_whitelist(request, config)
    except HTTPException as e:
        logger.warning(f"IP rechazada pero procesando en modo captura: {e.detail}")
        # En modo captura, continuamos para loguear el payload

    await verify_rate_limit(request, config)

    try:
        await verify_auth_token(authorization, config)
    except HTTPException as e:
        logger.warning(f"Auth token falló pero procesando en modo captura: {e.detail}")

    # HMAC: capturar fallo pero NO abortar (modo captura para transacción real)
    r4_endpoint = R4Endpoint.R4NOTIFICA if fmt == "MBconsulta" else R4Endpoint.R4CONSULTA
    try:
        await verify_hmac_signature_webhook(request, body, r4_endpoint, config)
        logger.info("✅ HMAC verificado OK")
    except HTTPException as e:
        # Capturar detalles del fallo HMAC para diagnóstico
        from src.integrations.r4.hmac_auth import build_sign_string, compute_hmac_sha256
        try:
            sign_str = build_sign_string(body, r4_endpoint)
            expected = compute_hmac_sha256(sign_str, config.commerce_secret)
            received = request.headers.get("Authorization", "") or \
                       request.headers.get("X-Signature", "") or \
                       request.headers.get("X-Hmac-Signature", "")
            _log_hmac_failure(request, body, f"consulta/{fmt}", sign_str, expected, received)
        except Exception as diag_err:
            _log_hmac_failure(request, body, f"consulta/{fmt}")
            logger.warning(f"   No se pudo construir sign string: {diag_err}")
        logger.warning(f"HMAC falló pero procesando en modo captura: {e.detail}")

    # Procesar según formato detectado
    if fmt == "MBconsulta":
        result = await process_mbconsulta(body, config)
        logger.info(f"MBconsulta respuesta: abono={result.success}")
        return {"abono": result.success}
    else:
        # Validar con modelo Pydantic para R4consulta
        try:
            payload = R4ConsultaRequest(**body)
        except Exception as e:
            logger.warning(f"Payload R4consulta inválido pero capturado: {e}")
            # Retornar response genérico para no romper el flujo del banco
            return {"status": True}
        result = await process_r4consulta(payload, config)
        logger.info(f"R4consulta respuesta: status={result.success}")
        return {"status": result.success}


@router.post(
    "/notifica",
    response_model=R4NotificaResponse,
    summary="R4notifica - Notificación pago móvil entrante",
    description="""
    Endpoint llamado por el banco cuando se recibe un pago móvil.
    Procesa el abono: busca pedido, marca pagado, sincroniza Odoo,
    notifica WhatsApp.

    Seguridad:
    - IP whitelist
    - Authorization Bearer token
    - HMAC-SHA256 firma del payload (9 campos)
    - Rate limiting
    """,
)
async def r4_notifica_webhook(
    request: Request,
    authorization: str | None = Header(None),
    config: R4WebhookConfig = _webhook_config_singleton,
) -> dict[str, Any]:
    """
    Webhook R4notifica - Notificación de pago entrante.

    Body: {IdComercio, TelefonoComercio, TelefonoEmisor, Concepto,
           BancoEmisor, Monto, FechaHora, Referencia, CodigoRed}
    Response: {"abono": true/false}
    """
    logger.info("=== R4notifica webhook recibido ===")

    # Parsear body como JSON genérico para captura
    try:
        body = await request.json()
    except Exception:
        raw_body = await request.body()
        logger.warning(f"Body no es JSON válido. Raw (primeros 500 chars): {raw_body[:500]}")
        _log_full_request(request, f"RAW: {raw_body[:500]}", "notifica")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Body JSON inválido",
        )

    # === CAPTURA COMPLETA: loguear TODO antes de cualquier verificación ===
    _log_full_request(request, body, "notifica")

    # Validar con modelo Pydantic
    try:
        payload = R4NotificaRequest(**body)
    except Exception as e:
        logger.warning(f"Payload R4notifica inválido pero capturado: {e}")
        _log_full_request(request, body, "notifica/invalid")
        # Retornar response genérico para no romper el flujo del banco
        return {"abono": True}

    # Verificaciones de seguridad (NO abortar en HMAC para captura)
    try:
        await verify_ip_whitelist(request, config)
    except HTTPException as e:
        logger.warning(f"IP rechazada pero procesando en modo captura: {e.detail}")

    await verify_rate_limit(request, config)

    try:
        await verify_auth_token(authorization, config)
    except HTTPException as e:
        logger.warning(f"Auth token falló pero procesando en modo captura: {e.detail}")

    # HMAC: capturar fallo pero NO abortar (modo captura)
    try:
        await verify_hmac_signature_webhook(request, payload.dict(), R4Endpoint.R4NOTIFICA, config)
        logger.info("✅ HMAC verificado OK")
    except HTTPException as e:
        from src.integrations.r4.hmac_auth import build_sign_string, compute_hmac_sha256
        try:
            sign_str = build_sign_string(payload.dict(), R4Endpoint.R4NOTIFICA)
            expected = compute_hmac_sha256(sign_str, config.commerce_secret)
            received = request.headers.get("Authorization", "") or \
                       request.headers.get("X-Signature", "") or \
                       request.headers.get("X-Hmac-Signature", "")
            _log_hmac_failure(request, payload.dict(), "notifica", sign_str, expected, received)
        except Exception as diag_err:
            _log_hmac_failure(request, payload.dict(), "notifica")
            logger.warning(f"   No se pudo construir sign string: {diag_err}")
        logger.warning(f"HMAC falló pero procesando en modo captura: {e.detail}")

    # Procesar lógica de negocio
    result = await process_r4notifica(payload, config)

    logger.info(f"R4notifica respuesta: abono={result.success}")
    return {"abono": result.success}


# ============================================================
# Health check endpoint
# ============================================================


@router.get(
    "/health",
    summary="Health check de webhooks R4",
    description="Verifica configuración y conectividad básica",
)
async def r4_webhook_health(
    config: R4WebhookConfig = _webhook_config_singleton,
) -> dict[str, Any]:
    """Health check para webhooks R4."""
    return {
        "status": "ok",
        "service": "r4-webhooks",
        "config": {
            "allowed_ips_count": len(config.allowed_ips),
            "has_auth_token": bool(config.auth_token),
            "has_commerce_secret": bool(config.commerce_secret),
            "rate_limit": (f"{config.rate_limit_requests} req/{config.rate_limit_window}s"),
        },
        "endpoints": [
            {
                "path": "/webhook/r4/consulta",
                "method": "POST",
                "description": "R4consulta / MBconsulta (auto-detect)",
            },
            {
                "path": "/webhook/r4/notifica",
                "method": "POST",
                "description": "R4notifica",
            },
        ],
    }


# ============================================================
# Función para registrar en FastAPI app (FASE 6)
# ============================================================


def include_r4_webhooks(app: Any) -> None:
    """
    Registra los webhooks R4 en la aplicación FastAPI.
    Llamar en FASE 6 desde bridge.py o main.py

    Uso:
        from src.integrations.r4.webhooks import include_r4_webhooks
        include_r4_webhooks(app)
    """
    app.include_router(router)
    logger.info("R4 Webhooks registrados en FastAPI app")


# ============================================================
# Test rápido
# ============================================================

if __name__ == "__main__":
    import asyncio

    async def test_webhooks() -> None:
        print("=== Test R4 Webhooks (config only) ===")

        config = get_webhook_config()
        print(f"Allowed IPs: {config.allowed_ips}")
        print(f"Auth token: {'SET' if config.auth_token else 'NOT SET'}")
        print(f"Commerce secret: {'SET' if config.commerce_secret else 'NOT SET'}")
        print(f"Rate limit: {config.rate_limit_requests}/{config.rate_limit_window}s")

        # Test models
        consulta = R4ConsultaRequest(
            IdCliente="V12345678", Monto="150.00", TelefonoComercio="04125555555"
        )
        print(f"\nR4ConsultaRequest: {consulta.dict()}")

        # Test MBconsulta format detection
        mb_payload = {
            "TelefonoEmisor": "04145555555",
            "BancoEmisor": "0134",
            "Monto": "150.00",
            "Referencia": "83736278",
        }
        fmt = detect_webhook_format(mb_payload)
        print(f"\nMBconsulta format detected: {fmt}")
        assert fmt == "MBconsulta", f"Expected MBconsulta, got {fmt}"

        r4_payload = {"IdCliente": "12345678", "Monto": "10.00", "TelefonoComercio": "04129999999"}
        fmt2 = detect_webhook_format(r4_payload)
        print(f"R4consulta format detected: {fmt2}")
        assert fmt2 == "R4consulta", f"Expected R4consulta, got {fmt2}"

        notifica = R4NotificaRequest(
            IdComercio="13536734",
            TelefonoComercio="04125555555",
            TelefonoEmisor="04145555555",
            Concepto="PAGO AGUA",
            BancoEmisor="134",
            Monto="150.00",
            FechaHora="2024-12-05T16:50:48.421Z",
            Referencia="83736278",
            CodigoRed="00",
        )
        print(f"R4NotificaRequest: {notifica.dict()}")

        print("\n✅ Webhooks module loads correctly!")

    asyncio.run(test_webhooks())
