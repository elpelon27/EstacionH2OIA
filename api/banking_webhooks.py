"""R4 Banco - Webhooks FastAPI para integración con R4 Conecta V3.0

Endpoints:
- POST /webhook/banco/R4notifica  - Notificación pago móvil entrante (P2P/P2C)
- POST /webhook/banco/R4consulta   - Consulta/validación cliente (banco → nosotros)
"""
import logging
import hmac
import hashlib
from typing import Optional

from fastapi import APIRouter, Request, HTTPException, Header, Depends
from pydantic import BaseModel

from src.banking.r4_endpoints import is_bank_ip_allowed, get_response_meaning, is_success_code
from src.banking.r4_models import (
    R4NotificaRequest,
    R4NotificaResponse,
    R4ConsultaRequest,
    R4ConsultaResponse,
)
from src.financial import verificacion  # type: ignore[import-not-found]
from src.financial.database import (
    buscar_pedidos_por_telefono_monto,
    seleccionar_mejor_match,
)

logger = logging.getLogger("r4banco.webhooks")

router = APIRouter(prefix="/webhook/banco", tags=["R4 Banco"])


# ============================================================================
# DEPENDENCIAS DE VALIDACIÓN
# ============================================================================

async def validate_bank_ip(request: Request) -> None:
    """Valida que la IP del request esté en whitelist del banco"""
    client_ip = request.client.host if request.client else "unknown"
    
    # Cloudflare envía IP real en CF-Connecting-IP
    cf_ip = request.headers.get("CF-Connecting-IP")
    real_ip = cf_ip or client_ip
    
    if not is_bank_ip_allowed(real_ip):
        logger.warning("IP no autorizada intentando acceder a webhook R4: %s", real_ip)
        raise HTTPException(status_code=403, detail="IP no autorizada")
    
    logger.info("Webhook R4 desde IP autorizada: %s", real_ip)


async def validate_hmac_signature(
    request: Request,
    authorization: Optional[str] = Header(None),
    commerce: Optional[str] = Header(None, alias="Commerce"),
) -> None:
    """
    Valida firma HMAC-SHA256 del banco.
    
    Según manual: Authorization = HMAC-SHA256 Hex de (string_a_firmar) usando Commerce token como llave.
    El string a firmar varía por endpoint (ver r4_endpoints.SIGN_STRINGS).
    """
    # Si no hay headers de auth, puede ser testing local
    if not authorization or not commerce:
        logger.debug("Sin headers Authorization/Commerce - posible test local")
        return
    
    # TODO: Implementar validación HMAC real cuando tengamos credenciales
    # Por ahora solo log
    logger.info("HMAC validation pending - commerce=%s auth_present=%s", commerce[:8] if commerce else None, bool(authorization))
    
    # Estructura esperada cuando tengamos credenciales:
    # body = await request.body()
    # string_to_sign = construir_string_firma(endpoint, body, headers)
    # expected_signature = hmac.new(commerce_token_bytes, string_to_sign.encode(), hashlib.sha256).hexdigest()
    # if not hmac.compare_digest(expected_signature, authorization):
    #     raise HTTPException(401, "Firma HMAC inválida")


# ============================================================================
# ENDPOINT: NOTIFICACIÓN PAGO MÓVIL ENTRANTE (R4notifica)
# ============================================================================

@router.post(
    "/R4notifica",
    response_model=R4NotificaResponse,
    dependencies=[Depends(validate_bank_ip), Depends(validate_hmac_signature)],
    summary="Webhook notificación pago móvil entrante P2P/P2C",
    description="""
    El banco llama este endpoint cuando un cliente hace un Pago Móvil a nuestro comercio.
    
    Flujo:
    1. Validar IP en whitelist
    2. Validar HMAC signature
    3. Buscar fs_pedido match (teléfono emisor + monto + estado pendiente)
    4. Si match único: verificar_pago_manual() → actualiza fs_pedidos + fs_pagos + fs_audit_log
    5. Responder {"abono": true} o {"abono": false}
    """
)
async def webhook_r4_notifica(
    payload: R4NotificaRequest,
    request: Request,
) -> R4NotificaResponse:
    logger.info(
        "R4notifica recibido: comercio=%s emisor=%s monto=%s ref=%s banco=%s codigo_red=%s",
        payload.IdComercio,
        payload.TelefonoEmisor,
        payload.Monto,
        payload.Referencia,
        payload.BancoEmisor,
        payload.CodigoRed,
    )
    
    # Verificar código de red = aprobado
    if payload.CodigoRed != "00":
        logger.warning(
            "Pago móvil con CodigoRed no aprobado: %s (%s)",
            payload.CodigoRed,
            get_response_meaning(payload.CodigoRed),
        )
        return R4NotificaResponse(abono=False)
    
    # Normalizar teléfono emisor (quitar prefijos V/E si vienen)
    telefono_emisor = payload.TelefonoEmisor
    if telefono_emisor.startswith(("V", "E", "v", "e")):
        telefono_emisor = telefono_emisor[1:]
    
    # Buscar pedido financiero coincidente
    try:
        monto = float(payload.Monto)
    except ValueError:
        logger.error("Monto inválido en notifica: %s", payload.Monto)
        return R4NotificaResponse(abono=False)
    
    # Buscar en BD: teléfono LIKE %emisor% + monto ≈ + estado IN (pendiente,verificando,parcial)
    pedidos = buscar_pedidos_por_telefono_monto(
        telefono_emisor=telefono_emisor,
        monto_str=str(monto),
        estados_permitidos=["pendiente", "verificando", "parcial"],
    )
    
    if not pedidos:
        logger.info("No hay pedido pendiente para emisor=%s monto=%.2f", telefono_emisor, monto)
        return R4NotificaResponse(abono=False)
    
    # Seleccionar mejor match (usa scoring: teléfono exacto + monto exacto + reciente)
    pedido = seleccionar_mejor_match(pedidos, telefono_emisor, monto)
    
    if not pedido:
        logger.warning("No se pudo seleccionar match único entre %d candidatos", len(pedidos))
        return R4NotificaResponse(abono=False)
    
    fs_pedido_id = pedido.id
    assert fs_pedido_id is not None, "pedido.id no debería ser None"
    # Verificar pago via Financial Shield (método manual = confirmación bancaria)
    try:
        resultado = await verificacion.verificar_pago_manual(
            fs_pedido_id=fs_pedido_id,
            monto_eur=monto,  # El monto viene en la moneda del pedido (EUR en nuestro sistema)
            metodo_pago="pagomovil",
            referencia=payload.Referencia,
            verificado_por="banco_r4",
        )
        
        if resultado.get("verificado"):
            logger.info("✅ Pago móvil VERIFICADO por banco R4: fs_pedido=%d ref=%s", fs_pedido_id, payload.Referencia)
            return R4NotificaResponse(abono=True)
        else:
            logger.warning("Pago móvil NO verificado: %s", resultado)
            return R4NotificaResponse(abono=False)
            
    except Exception as e:
        logger.error("Error procesando verificación pago móvil: %s", e, exc_info=True)
        return R4NotificaResponse(abono=False)


# ============================================================================
# ENDPOINT: CONSULTA/VALIDACIÓN CLIENTE (R4consulta)
# ============================================================================

@router.post(
    "/R4consulta",
    response_model=R4ConsultaResponse,
    dependencies=[Depends(validate_bank_ip), Depends(validate_hmac_signature)],
    summary="Consulta validación cliente para pago móvil",
    description="""
    El banco llama este endpoint ANTES de procesar un pago móvil entrante.
    Debemos validar si el IdCliente (teléfono) existe en nuestro sistema.
    
    Si respondemos {"status": true} → banco procede a notificar transacción
    Si respondemos {"status": false} → banco REVIERTE el pago
    """
)
async def webhook_r4_consulta(
    payload: R4ConsultaRequest,
    request: Request,
) -> R4ConsultaResponse:
    logger.info(
        "R4consulta recibido: IdCliente=%s Monto=%s TelefonoComercio=%s",
        payload.IdCliente,
        payload.Monto,
        payload.TelefonoComercio,
    )
    
    # Normalizar IdCliente (puede venir con prefijo V/E)
    id_cliente = payload.IdCliente
    if id_cliente.startswith(("V", "E", "v", "e")):
        id_cliente = id_cliente[1:]
    
    # Verificar si existe en BD (fs_pedidos, fs_cuentas_cobrar, o tabla clientes)
    # Por ahora: si es un teléfono válido venezolano, aceptar
    # TODO: Implementar búsqueda real en BD
    
    # Validación básica: 10-11 dígitos
    if id_cliente.isdigit() and len(id_cliente) in (10, 11):
        logger.info("Cliente %s ACEPTADO para pago móvil", id_cliente)
        return R4ConsultaResponse(status=True)
    
    logger.warning("Cliente %s RECHAZADO - formato inválido", id_cliente)
    return R4ConsultaResponse(status=False)


# ============================================================================
# ENDPOINT: CONSULTA VÍA SIMF (MBconsulta) - Opcional
# ============================================================================

class MBNotificaRequest(BaseModel):
    """Request vía SIMF (formato alternativo del manual)"""
    IdComercio: str
    TelefonoComercio: str
    TelefonoEmisor: str
    Concepto: str
    BancoEmisor: str
    Monto: str
    FechaHora: str
    Referencia: str
    CodigoRed: str


class MBNotificaResponse(BaseModel):
    abono: bool


@router.post(
    "/MBconsulta",
    response_model=MBNotificaResponse,
    dependencies=[Depends(validate_bank_ip)],
    include_in_schema=False,  # Ocultar de docs si no se usa
)
async def webhook_mb_consulta(
    payload: MBNotificaRequest,
    request: Request,
) -> MBNotificaResponse:
    """Endpoint alternativo vía SIMF (manual página 8)"""
    logger.info("MBconsulta recibido: comercio=%s emisor=%s monto=%s", 
                payload.IdComercio, payload.TelefonoEmisor, payload.Monto)
    
    # Misma lógica que R4notifica
    if payload.CodigoRed != "00":
        return MBNotificaResponse(abono=False)
    
    # TODO: Implementar búsqueda y verificación
    return MBNotificaResponse(abono=False)


# ============================================================================
# HEALTH CHECK
# ============================================================================

@router.get("/health", summary="Health check R4 Banco")
async def health_check():
    return {
        "service": "R4 Banco Webhooks",
        "status": "healthy",
        "endpoints": [
            "/webhook/banco/R4notifica",
            "/webhook/banco/R4consulta",
            "/webhook/banco/MBconsulta",
        ],
    }