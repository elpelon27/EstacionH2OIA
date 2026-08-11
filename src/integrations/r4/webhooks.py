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
from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, Field, validator

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

    def __init__(self):
        # IP whitelist del banco (configurable)
        ips_env = os.getenv("R4_WEBHOOK_ALLOWED_IPS", "")
        self.allowed_ips = {ip.strip() for ip in ips_env.split(",") if ip.strip()}
        # Defaults según especificación
        if not self.allowed_ips:
            self.allowed_ips = {
                "45.175.213.98",
                "200.74.203.91",
                "204.199.249.3",
            }

        # Authorization token (UUID)
        self.auth_token = os.getenv("R4_WEBHOOK_AUTH_TOKEN", "")

        # HMAC commerce token (mismo que cliente)
        self.commerce_token = os.getenv("R4_COMMERCE_TOKEN", "")

        # Rate limiting
        self.rate_limit_requests = int(os.getenv("R4_WEBHOOK_RATE_LIMIT", "100"))
        self.rate_limit_window = int(os.getenv("R4_WEBHOOK_RATE_WINDOW", "60"))  # segundos

        # Validación
        self._validate_config()

    def _validate_config(self):
        if not self.auth_token:
            logger.warning("R4_WEBHOOK_AUTH_TOKEN no configurado - webhooks sin auth token")
        if not self.commerce_token:
            logger.warning("R4_COMMERCE_TOKEN no configurado - verificación HMAC deshabilitada")
        logger.info(f"R4 Webhook IPs permitidas: {self.allowed_ips}")


# Instancia global
_webhook_config: R4WebhookConfig | None = None


def get_webhook_config() -> R4WebhookConfig:
    global _webhook_config
    if _webhook_config is None:
        _webhook_config = R4WebhookConfig()
    return _webhook_config


def reset_webhook_config():
    global _webhook_config
    _webhook_config = None


# ============================================================
# Rate Limiting simple en memoria
# ============================================================

import time
from collections import defaultdict

_rate_limit_store: dict[str, list] = defaultdict(list)


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

    @validator("Monto")
    def validate_monto(cls, v):
        # Validar formato decimal con 2 decimales
        try:
            float(v)
            if "." in v:
                decimals = len(v.split(".")[1])
                if decimals != 2:
                    raise ValueError("Monto debe tener 2 decimales")
        except ValueError:
            raise ValueError("Monto inválido")
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

    @validator("Monto")
    def validate_monto(cls, v):
        try:
            float(v)
            if "." in v:
                decimals = len(v.split(".")[1])
                if decimals != 2:
                    raise ValueError("Monto debe tener 2 decimales")
        except ValueError:
            raise ValueError("Monto inválido")
        return v

    @validator("CodigoRed")
    def validate_codigo_red(cls, v):
        if not v.isdigit() or len(v) != 2:
            raise ValueError("CodigoRed debe ser 2 dígitos")
        return v


class R4ConsultaResponse(BaseModel):
    """Response para webhook /consulta."""

    status: bool


class R4NotificaResponse(BaseModel):
    """Response para webhook /notifica."""

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
        logger.warning(f"R4 Webhook IP rechazada: {client_ip} (permitidas: {config.allowed_ips})")
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
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authorization header requerido"
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
    request: Request, payload: dict[str, Any], endpoint: R4Endpoint, config: R4WebhookConfig
) -> None:
    """Verifica firma HMAC-SHA256 del payload (timing-safe)."""
    if not config.commerce_token:
        logger.warning("R4_COMMERCE_TOKEN no configurado - saltando verificación HMAC")
        return

    auth_header = request.headers.get("Authorization", "")
    # Authorization ya verificado como Bearer token, buscar X-Signature o similar
    # El banco puede enviar la firma en header separado
    signature = request.headers.get("X-Signature") or request.headers.get("X-Hmac-Signature")

    if not signature:
        # Intentar extraer del Authorization si viene combinado
        # Formato alternativo: "HMAC <signature>"
        if auth_header.startswith("HMAC "):
            signature = auth_header[5:]

    if not signature:
        logger.warning(f"R4 Webhook {endpoint.value} sin firma HMAC")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Firma HMAC requerida")

    # Verificar con hmac.compare_digest (timing-safe)
    is_valid = verify_hmac_signature(payload, endpoint, signature, config.commerce_token)

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
            status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Rate limit excedido"
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
    # La verificación HMAC se hace dentro del endpoint porque necesita el payload parseado

    return config


# ============================================================
# Lógica de negocio (placeholders para FASE 6)
# ============================================================


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
    # pedido = await fs.get_pending_order_by_client(payload.IdCliente, payload.Monto)
    # if pedido:
    #     return WebhookProcessResult(success=True, code="00", message="Cliente válido", reference=pedido.id)
    # return WebhookProcessResult(success=False, code="NO_ORDER", message="Sin pedido pendiente")

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
        f"R4notifica recibido: Referencia={payload.Referencia}, "
        f"Monto={payload.Monto}, TelefonoEmisor={payload.TelefonoEmisor}, "
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
    # pedido = await fs.get_pending_order_by_amount_phone(payload.Monto, payload.TelefonoEmisor)
    # if not pedido:
    #     return WebhookProcessResult(success=False, code="NO_ORDER", message="Pedido no encontrado")
    #
    # c) Marcar pago en fs_pedidos
    # await fs.mark_order_paid(pedido.id, payload.Referencia, payload.FechaHora)
    #
    # d) Sync a Odoo
    # odoo = OdooClient()
    # await odoo.sync_payment(pedido.id, payload)
    #
    # e) Notificar WhatsApp
    # await send_whatsapp_message(pedido.cliente_telefono, f"✅ Pago recibido: {payload.Monto} Bs")
    #
    # return WebhookProcessResult(success=True, code="00", message="Abono procesado", reference=payload.Referencia)

    # Mock response para desarrollo
    return WebhookProcessResult(
        success=True,
        code="00",
        message="MOCK: Abono procesado (implementar FASE 6)",
        reference=payload.Referencia,
    )


# ============================================================
# Router FastAPI
# ============================================================

router = APIRouter(prefix="/webhook/r4", tags=["R4 Webhooks"])


@router.post(
    "/consulta",
    response_model=R4ConsultaResponse,
    summary="R4consulta - Validación cliente para pago móvil",
    description="""
    Endpoint llamado por el banco cuando un cliente inicia pago móvil.
    Debemos responder si el cliente tiene un pedido pendiente válido.
    
    Seguridad:
    - IP whitelist
    - Authorization Bearer token
    - HMAC-SHA256 firma del payload
    - Rate limiting
    """,
)
async def r4_consulta_webhook(
    request: Request,
    payload: R4ConsultaRequest,
    authorization: str | None = Header(None),
    config: R4WebhookConfig = Depends(lambda: get_webhook_config()),
) -> R4ConsultaResponse:
    """
    Webhook R4consulta - Validación de cliente.

    Body: {IdCliente, Monto, TelefonoComercio}
    Response: {"status": true/false}
    """
    logger.info("=== R4consulta webhook recibido ===")

    # Verificaciones de seguridad
    await verify_ip_whitelist(request, config)
    await verify_rate_limit(request, config)
    await verify_auth_token(authorization, config)
    await verify_hmac_signature_webhook(request, payload.dict(), R4Endpoint.R4CONSULTA, config)

    # Procesar lógica de negocio
    result = await process_r4consulta(payload, config)

    logger.info(f"R4consulta respuesta: status={result.success}")
    return result.to_consulta_response()


@router.post(
    "/notifica",
    response_model=R4NotificaResponse,
    summary="R4notifica - Notificación pago móvil entrante",
    description="""
    Endpoint llamado por el banco cuando se recibe un pago móvil.
    Procesa el abono: busca pedido, marca pagado, sincroniza Odoo, notifica WhatsApp.
    
    Seguridad:
    - IP whitelist
    - Authorization Bearer token
    - HMAC-SHA256 firma del payload (9 campos)
    - Rate limiting
    """,
)
async def r4_notifica_webhook(
    request: Request,
    payload: R4NotificaRequest,
    authorization: str | None = Header(None),
    config: R4WebhookConfig = Depends(lambda: get_webhook_config()),
) -> R4NotificaResponse:
    """
    Webhook R4notifica - Notificación de pago entrante.

    Body: {IdComercio, TelefonoComercio, TelefonoEmisor, Concepto,
           BancoEmisor, Monto, FechaHora, Referencia, CodigoRed}
    Response: {"abono": true/false}
    """
    logger.info("=== R4notifica webhook recibido ===")

    # Verificaciones de seguridad
    await verify_ip_whitelist(request, config)
    await verify_rate_limit(request, config)
    await verify_auth_token(authorization, config)
    await verify_hmac_signature_webhook(request, payload.dict(), R4Endpoint.R4NOTIFICA, config)

    # Procesar lógica de negocio
    result = await process_r4notifica(payload, config)

    logger.info(f"R4notifica respuesta: abono={result.success}")
    return result.to_notifica_response()


# ============================================================
# Health check endpoint
# ============================================================


@router.get(
    "/health",
    summary="Health check de webhooks R4",
    description="Verifica configuración y conectividad básica",
)
async def r4_webhook_health(config: R4WebhookConfig = Depends(get_webhook_config)):
    """Health check para webhooks R4."""
    return {
        "status": "ok",
        "service": "r4-webhooks",
        "config": {
            "allowed_ips_count": len(config.allowed_ips),
            "has_auth_token": bool(config.auth_token),
            "has_commerce_token": bool(config.commerce_token),
            "rate_limit": f"{config.rate_limit_requests} req/{config.rate_limit_window}s",
        },
        "endpoints": [
            {"path": "/webhook/r4/consulta", "method": "POST", "description": "R4consulta"},
            {"path": "/webhook/r4/notifica", "method": "POST", "description": "R4notifica"},
        ],
    }


# ============================================================
# Función para registrar en FastAPI app (FASE 6)
# ============================================================


def include_r4_webhooks(app) -> None:
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

    async def test_webhooks():
        print("=== Test R4 Webhooks (config only) ===")

        config = get_webhook_config()
        print(f"Allowed IPs: {config.allowed_ips}")
        print(f"Auth token: {'SET' if config.auth_token else 'NOT SET'}")
        print(f"Commerce token: {'SET' if config.commerce_token else 'NOT SET'}")
        print(f"Rate limit: {config.rate_limit_requests}/{config.rate_limit_window}s")

        # Test models
        consulta = R4ConsultaRequest(
            IdCliente="V12345678", Monto="150.00", TelefonoComercio="04125555555"
        )
        print(f"\nR4ConsultaRequest: {consulta.dict()}")

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
