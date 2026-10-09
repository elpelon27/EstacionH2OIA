#!/usr/bin/env python3
"""
Webhooks R4 Conecta V3.0 - Endpoints FastAPI para notificaciones entrantes del banco.

Endpoints implementados:
1. POST /webhook/r4/consulta - Validación de cliente para pago móvil
2. POST /webhook/r4/notifica - Notificación de pago móvil entrante

Seguridad (PDF R4 CONECTA V3.0):
- IP whitelist (configurable via .env)
- Authorization header (UUID directo, sin "Bearer " prefix, sin HMAC)
- Rate limiting por IP

El HMAC es SOLO para peticiones salientes (client.py → banco).
Los webhooks entrantes usan Authorization: <UUID> + IP whitelist.
"""

import hmac
import logging
import os
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator

from src.integrations.r4.codigos import get_description

logger = logging.getLogger("r4.webhooks")


async def _enviar_whatsapp_directo(phone: str, text: str) -> bool:
    """Envía WhatsApp por Meta Graph API con un client httpx propio.

    Fallback best-effort cuando el módulo del bridge no está disponible
    en este contexto (p.ej. el webhook R4 corre en un proceso sin el
    httpx client compartido inicializado).
    """
    import os

    import httpx

    token = os.getenv("META_ACCESS_TOKEN", "")
    phone_id = os.getenv("META_PHONE_NUMBER_ID", "")
    if not token or not phone_id:
        logger.warning("WhatsApp directo: META token/phone_id no configurados")
        return False
    url = f"https://graph.facebook.com/{os.getenv('META_API_VERSION', 'v25.0')}/{phone_id}/messages"
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                url,
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json={
                    "messaging_product": "whatsapp",
                    "recipient_type": "individual",
                    "to": phone,
                    "type": "text",
                    "text": {"body": text, "preview_url": False},
                },
                timeout=10,
            )
            if resp.status_code == 200:
                logger.info("WhatsApp directo enviado a %s****", phone[:6])
                return True
            logger.error("WhatsApp directo: Meta API error %d", resp.status_code)
            return False
    except Exception as e:
        logger.warning("WhatsApp directo falló: %s", e)
        return False


def _obtener_enviador_whatsapp() -> Any:
    """Resuelve la función de envío de WhatsApp del módulo live del bridge.

    El bridge corre como `uvicorn bridge:app` (cwd=api/) → el módulo con el
    httpx client inicializado es `bridge`. La copia importada como `api.bridge`
    en este contexto tiene su propio _http_client=None (causaba el bug
    "http client not initialized"). Se prefiere el módulo con client listo.
    """
    import sys

    for mod_name in ("bridge", "api.bridge"):
        mod = sys.modules.get(mod_name)
        if mod is None:
            try:
                mod = __import__(mod_name)
            except Exception:
                continue
        send = getattr(mod, "_send_whatsapp_message", None)
        client = getattr(mod, "_http_client", None)
        if send is not None and client is not None:
            return send
    return None


# ============================================================
# Encolado a despacho desde el webhook bancario (2026-10-08 §1)
# ============================================================
# Causa raíz (diagnóstico 08-oct): el encolado a dispatch_queue SOLO ocurría
# en el flujo de conversación (Efectivo / "ya pagué"). El webhook R4 verificaba
# el pago y NO encolaba → pedidos pagados por Pago Móvil nunca llegaban al chofer.
# Esta función arma el INSERT desde la fila de fs_pedidos + clients, con
# idempotencia por fs_pedido_id (evita duplicado si el cliente además escribe
# "ya pagué" por el flujo manual).

_CARACAS_TZ = timezone(timedelta(hours=-4))  # America/Caracas UTC-4
WATCHDOG_UMBRAL_MIN = 15  # §2: pedidos pagados >15 min sin despachar → alerta


def _conv_db_path() -> str:
    """Ruta de conversations.db (misma fuente que api/bridge.py)."""
    return os.getenv("SQLITE_PATH", "/mnt/ssd_trabajo/hermes-agent/data/conversations.db")


def _dispatch_db_path() -> str:
    """Ruta de dispatch.db (misma fuente que api/bridge.py)."""
    return os.getenv(
        "DISPATCH_DB_PATH", "/mnt/ssd_trabajo/hermes-agent/data/dispatch.db"
    )


def _tasa_eur_ves_actual() -> float | None:
    """Última tasa EUR/VES de fs_tasas_cambio (mismo patrón que bridge._convert_eur_to_bs)."""
    import sqlite3

    try:
        conn = sqlite3.connect(_conv_db_path())
        row = conn.execute(
            "SELECT tasa FROM fs_tasas_cambio "
            "WHERE par='EUR/VES' ORDER BY registrado_at DESC LIMIT 1"
        ).fetchone()
        conn.close()
        if row and row[0] > 0:
            return float(row[0])
    except Exception:
        pass
    return None


def _alertar_lider(mensaje: str) -> None:
    """Alerta al Telegram del Líder. Fire-and-forget, nunca lanza (§1/§2).

    Usa el bot de Telegram del bridge si el módulo live está disponible
    (mismo TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID); si no, envío directo.
    """
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "1663148211")  # Líder por defecto
    if not token:
        logger.warning("Alerta Líder sin TELEGRAM_BOT_TOKEN: %s", mensaje[:120])
        return
    try:
        import httpx

        url = f"https://api.telegram.org/bot{token}/sendMessage"
        with httpx.Client(timeout=10) as client:
            resp = client.post(url, json={"chat_id": chat_id, "text": mensaje})
            if resp.status_code != 200:
                logger.warning("Alerta Líder Telegram HTTP %d", resp.status_code)
    except Exception as e:
        logger.warning("Alerta Líder falló: %s", e)


def _direcciones_desde_clients(cliente_telefono: str) -> tuple[float | None, float | None, str]:
    """Busca lat/lng/dirección del cliente en dispatch.db (clients).

    Tabla poblada por el flujo /clasificar del bridge. Si no hay → campos
    vacíos (el chofer puede llamar al cliente).
    """
    import sqlite3

    try:
        conn = sqlite3.connect(_dispatch_db_path())
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT lat, lng, address_text FROM clients WHERE phone = ? "
            "ORDER BY updated_at DESC LIMIT 1",
            (cliente_telefono,),
        ).fetchone()
        conn.close()
        if row:
            lat = float(row["lat"]) if row["lat"] is not None else None
            lng = float(row["lng"]) if row["lng"] is not None else None
            return lat, lng, row["address_text"] or ""
    except Exception as e:
        logger.warning("Buscando dirección en clients falló: %s", e)
    return None, None, ""


def _enqueue_delivery_from_fs(pedido: Any) -> dict[str, Any]:
    """Encola la entrega en dispatch_queue a partir de la fila de fs_pedidos.

    Idempotente: si ya existe fila en dispatch_queue con ese fs_pedido_id
    (de un flujo manual "ya pagué" anterior), NO inserta — retorna existing=True.

    Retorna {"enqueued": bool, "existing": bool, "order_id": int|None}.
    NUNCA lanza: si falla devuelve {"enqueued": False, ...} y el llamador
    decide (log CRÍTICO + alerta al Líder, sin romper la respuesta al banco).
    """
    import sqlite3

    fs_pedido_id = getattr(pedido, "id", None)
    cliente_telefono = getattr(pedido, "cliente_telefono", "") or ""
    cliente_nombre = getattr(pedido, "cliente_nombre", "") or ""
    total_eur = float(getattr(pedido, "monto_total_eur", 0.0) or 0.0)
    metodo_pago = getattr(pedido, "metodo_pago", "") or "pagomovil"
    qty_bot = int(getattr(pedido, "botellones_cantidad", 0) or 0)
    qty_hielo = int(getattr(pedido, "hielo_cantidad", 0) or 0)

    try:
        conn = sqlite3.connect(_conv_db_path())
        conn.execute("PRAGMA foreign_keys = ON")
    except Exception as e:
        logger.error("Abriendo conversations.db para encolar: %s", e)
        return {"enqueued": False, "existing": False, "order_id": None, "error": str(e)}

    try:
        # Idempotencia: ya hay fila con este fs_pedido_id?
        row = conn.execute(
            "SELECT id FROM dispatch_queue WHERE fs_pedido_id = ? LIMIT 1",
            (fs_pedido_id,),
        ).fetchone()
        if row:
            logger.info(
                "Encolado idempotente: fs_pedido=%s ya está en dispatch_queue (#%s)",
                fs_pedido_id,
                row[0],
            )
            return {"enqueued": False, "existing": True, "order_id": row[0]}

        # GPS/dirección desde clients (dispatch.db); si no hay, campos vacíos
        lat, lng, address = _direcciones_desde_clients(cliente_telefono)

        tasa = _tasa_eur_ves_actual()
        total_bs = float(round(total_eur * tasa, 2)) if tasa else None
        gps_url = f"https://maps.google.com/?q={lat},{lng}" if lat and lng else ""

        parts = []
        if qty_bot > 0:
            parts.append(f"{qty_bot} botellones de agua")
        if qty_hielo > 0:
            parts.append(f"{qty_hielo} bolsas de hielo")
        producto_desc = " + ".join(parts) if parts else "productos"

        cur = conn.execute(
            """
            INSERT INTO dispatch_queue (
                fs_pedido_id, cliente_nombre, cliente_telefono, producto_desc,
                total_eur, total_bs, metodo_pago,
                gps_lat, gps_lng, gps_url, direccion,
                estado, creado_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)
            """,
            (
                fs_pedido_id,
                cliente_nombre,
                cliente_telefono,
                producto_desc,
                total_eur,
                total_bs,
                metodo_pago,
                lat,
                lng,
                gps_url,
                address,
                datetime.now(_CARACAS_TZ).isoformat(),
            ),
        )
        order_id = int(cur.lastrowid or 0)
        conn.commit()
        logger.info(
            "📦 [webhook R4] Entrega encolada en dispatch_queue #%s "
            "(fs_pedido=%s, %s botellones, €%.2f)",
            order_id,
            fs_pedido_id,
            qty_bot,
            total_eur,
        )

        # Despertar al consumer loop del bridge (procesamiento sub-segundo)
        try:
            from skills.dispatch.consumer import notify_consumer

            notify_consumer()
        except Exception:
            pass  # fail silently: consumer hace poll cada 5s igualmente

        return {"enqueued": True, "existing": False, "order_id": order_id}
    except Exception as e:
        logger.error("Encolando entrega desde webhook R4: %s", e, exc_info=True)
        return {"enqueued": False, "existing": False, "order_id": None, "error": str(e)}
    finally:
        conn.close()


# ============================================================
# Watchdog §2 (2026-10-08): pedido pagado sin despachar >15 min
# ============================================================

def _watchdog_pagados_sin_cola() -> list[dict[str, Any]]:
    """Detecta fs_pedidos pagados hace >15 min sin fila en dispatch_queue.

    Alerta UNA sola vez por pedido: usa la tabla fs_verificacion_log como
    registro de alerta (columna notas='watchdog_despacho_alertado'), insertada
    idempotente tras alertar. Sin auto-corrección: solo detecta y alerta.
    """
    import sqlite3
    from datetime import datetime as _dt

    # umbral en UTC ISO — mismo formato que fs_pedidos.creado_at (comparación
    # de strings ISO: mezclar -04:00 con +00:00 rompe el orden lexicográfico)
    umbral = datetime.now(UTC) - timedelta(minutes=WATCHDOG_UMBRAL_MIN)
    umbral_iso = umbral.isoformat()
    encontrados: list[dict[str, Any]] = []

    try:
        conn = sqlite3.connect(_conv_db_path())
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT p.id, p.cliente_telefono, p.cliente_nombre,
                   p.monto_total_eur, p.creado_at
            FROM fs_pedidos p
            WHERE p.estado_pago = 'pagado'
              AND p.id NOT IN (SELECT fs_pedido_id FROM dispatch_queue
                               WHERE fs_pedido_id IS NOT NULL)
              AND p.id NOT IN (SELECT fs_pedido_id FROM fs_verificacion_log
                               WHERE resultado_detalle = 'watchdog_despacho_alertado')
              AND p.creado_at < ?
            """,
            (umbral_iso,),
        ).fetchall()

        for row in rows:
            # Minutos desde creado_at (que es ISO UTC en fs_pedidos)
            try:
                creado = _dt.fromisoformat(row["creado_at"].replace("Z", "+00:00"))
            except Exception:
                creado = None
            minutos = (
                int((datetime.now(UTC) - creado).total_seconds() // 60) if creado else 0
            )
            if minutos < WATCHDOG_UMBRAL_MIN:
                continue
            encontrados.append(
                {
                    "fs_pedido_id": row["id"],
                    "telefono": row["cliente_telefono"],
                    "nombre": row["cliente_nombre"],
                    "total_eur": row["monto_total_eur"],
                    "minutos": minutos,
                }
            )
        conn.close()
    except Exception as e:
        logger.warning("Watchdog pagados-sin-cola falló: %s", e)
        return encontrados

    return encontrados


def watchdog_ciclo_despacho() -> int:
    """Un ciclo del watchdog §2: alerta al Líder por Telegram. Retorna nº alertas nuevas."""
    encontrados = _watchdog_pagados_sin_cola()
    if not encontrados:
        return 0

    import sqlite3

    alertadas = 0
    for p in encontrados:
        try:
            conn = sqlite3.connect(_conv_db_path())
            # Schema real de fs_verificacion_log: intento/accion/resultado_detalle/timestamp
            # (no evento/notas — ver src/financial/database.py:178). Se usa como registro
            # de "ya alertado" para la idempotencia del watchdog (una alerta por pedido).
            conn.execute(
                "INSERT INTO fs_verificacion_log "
                "(fs_pedido_id, intento, metodo_verificacion, accion, resultado_detalle, timestamp) "
                "VALUES (?, 0, 'watchdog', 'escalo_humano', 'watchdog_despacho_alertado', ?)",
                (p["fs_pedido_id"], datetime.now(UTC).isoformat()),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning("Watchdog: marcando alerta fs_pedido=%s: %s", p["fs_pedido_id"], e)

        msg = (
            f"⚠️ <b>WATCHDOG DESPACHO</b>\n"
            f"Pedido #{p['fs_pedido_id']} PAGADO hace {p['minutos']} min "
            f"<b>SIN encolar a despacho</b>.\n"
            f"👤 {p['nombre'] or '(sin nombre)'}\n"
            f"📱 {p['telefono']}\n"
            f"💰 €{p['total_eur']:.2f}\n"
            f"Revisar webhook R4 / encolado manual."
        )
        _alertar_lider(msg)
        alertadas += 1
    logger.warning("Watchdog despacho: %d pedidos pagados sin despachar", alertadas)
    return alertadas

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
        logger.warning(f"R4 Webhook IP rechazada: {client_ip} (permitidas: {config.allowed_ips})")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="IP no autorizada")

    logger.debug(f"R4 Webhook IP autorizada: {client_ip}")


async def verify_auth_token(authorization: str | None, config: R4WebhookConfig) -> None:
    """
    Verifica Authorization header (UUID directo, sin 'Bearer ' prefix).

    Según PDF R4 CONECTA V3.0 (págs 7 y 9): los webhooks entrantes del banco
    usan Authorization: <UUID> directamente, SIN prefijo 'Bearer ' y SIN HMAC.
    El HMAC es SOLO para peticiones salientes (client.py → banco).
    """
    if not config.auth_token:
        logger.error("R4_WEBHOOK_AUTH_TOKEN no configurado - RECHAZANDO webhook")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Token de webhook no configurado",
        )

    if not authorization:
        logger.warning("R4 Webhook sin Authorization header")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header requerido",
        )

    # PDF V3.0: el banco envía el UUID directamente como Authorization
    # Comparación timing-safe contra el token configurado
    if not hmac.compare_digest(authorization, config.auth_token):
        logger.warning(
            "R4 Webhook token inválido (recibido: %s...)",
            authorization[:12] if len(authorization) > 12 else authorization,
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Token inválido")

    logger.debug("R4 Webhook Authorization token válido")


# NOTA: HMAC eliminado de webhooks entrantes según PDF R4 CONECTA V3.0.
# El HMAC es SOLO para peticiones salientes (client.py → banco).
# Los webhooks entrantes usan Authorization: <UUID> + IP whitelist únicamente.


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
) -> R4WebhookConfig:
    """
    Dependencia que ejecuta todas las verificaciones de seguridad.

    Según PDF R4 CONECTA V3.0: webhooks entrantes usan:
    1. IP Whitelist (banco IPs)
    2. Rate Limiting
    3. Authorization: <UUID> directo (sin Bearer, sin HMAC)

    NO hay HMAC en webhooks entrantes. El HMAC es solo para
    peticiones salientes (client.py → banco).
    """
    config = get_webhook_config()

    # 1. IP Whitelist - 403 si no coincide
    await verify_ip_whitelist(request, config)

    # 2. Rate Limiting - 429 si excede
    await verify_rate_limit(request, config)

    # 3. Authorization Token - 403 si no coincide
    await verify_auth_token(authorization, config)

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

    Usa el mismo flujo que R4notifica.
    """
    # Delegar al mismo flujo de process_r4notifica
    try:
        notifica_payload = R4NotificaRequest(**payload)
        return await process_r4notifica(notifica_payload, config)
    except Exception as e:
        logger.warning("MBconsulta: no se pudo mapear a R4NotificaRequest: %s", e)
        telefono_emisor = payload.get("TelefonoEmisor", "N/A")
        banco_emisor = payload.get("BancoEmisor", "N/A")
        monto = payload.get("Monto", "N/A")
        referencia = payload.get("Referencia", payload.get("reference", "N/A"))
        logger.info(
            f"MBconsulta recibido: TelefonoEmisor={telefono_emisor}, "
            f"BancoEmisor={banco_emisor}, Monto={monto}, Referencia={referencia}"
        )
        return WebhookProcessResult(
            success=True,
            code="00",
            message="MBconsulta procesado (mapeo parcial)",
            reference=str(referencia),
        )


async def process_r4consulta(
    payload: R4ConsultaRequest, config: R4WebhookConfig
) -> WebhookProcessResult:
    """
    Procesa webhook R4consulta: valida si IdCliente tiene pedido pendiente.

    El banco llama este endpoint ANTES de procesar un pago móvil entrante.
    Si respondemos status=true, el banco procede a enviar R4notifica.
    Si respondemos status=false, el banco REVIERTE el pago.
    """
    logger.info(f"R4consulta recibido: IdCliente={payload.IdCliente}, Monto={payload.Monto}")

    # Normalizar IdCliente (puede venir con prefijo V/E)
    id_cliente = payload.IdCliente
    if id_cliente.startswith(("V", "E", "v", "e")):
        id_cliente = id_cliente[1:]

    # Buscar pedidos pendientes para este cliente
    try:
        from src.financial.database import buscar_pedidos_por_telefono_monto

        pedidos = buscar_pedidos_por_telefono_monto(
            telefono_emisor=id_cliente,
            monto_str=payload.Monto,
            estados_permitidos=["pendiente", "verificando", "parcial", "vencido"],
        )

        if pedidos:
            logger.info(
                f"R4consulta: cliente {id_cliente} ACEPTADO, {len(pedidos)} pedido(s) pendiente(s)"
            )
            return WebhookProcessResult(
                success=True,
                code="00",
                message=f"Cliente válido con {len(pedidos)} pedido(s) pendiente(s)",
                reference=str(pedidos[0].id),
            )
        else:
            # No hay pedido pendiente pero aceptamos el pago (el banco lo notificará)
            logger.info(f"R4consulta: cliente {id_cliente} sin pedido pendiente, aceptando")
            return WebhookProcessResult(
                success=True,
                code="00",
                message="Cliente aceptado sin pedido pendiente",
                reference="",
            )
    except Exception as e:
        logger.error(f"R4consulta: error buscando pedidos: {e}", exc_info=True)
        # En caso de error, aceptar el pago para no bloquear al banco
        return WebhookProcessResult(
            success=True,
            code="00",
            message="Error interno, aceptando",
            reference="",
        )


async def process_r4notifica(
    payload: R4NotificaRequest, config: R4WebhookConfig
) -> WebhookProcessResult:
    """
    Procesa webhook R4notifica: notificación de pago entrante.

    Flujo:
    a) Verificar CodigoRed == "00" (transacción aprobada)
    b) Buscar pedido pendiente por monto_total_ves + telefono_emisor
    c) verificar_pago_manual() → INSERT fs_pagos + UPDATE fs_pedidos estado='pagado'
    d) Sync pago a Odoo (account.payment) — best-effort, no bloquea
    e) Enviar WhatsApp: "✅ Pago confirmado. Gracias. 💧"
    f) Retornar abono: true

    El banco envía Monto en VES (Bolívares). Los pedidos guardan
    monto_total_ves y monto_total_eur.
    """
    logger.info(
        "R4notifica recibido: "
        f"Referencia={payload.Referencia}, Monto={payload.Monto}, "
        f"TelefonoEmisor={payload.TelefonoEmisor}, "
        f"BancoEmisor={payload.BancoEmisor}, CodigoRed={payload.CodigoRed}"
    )

    # a) Verificar CodigoRed == "00" (APROBADO)
    if payload.CodigoRed != "00":
        logger.warning(f"R4notifica CodigoRed != 00: {payload.CodigoRed}")
        return WebhookProcessResult(
            success=False,
            code=payload.CodigoRed,
            message=get_description(payload.CodigoRed) or "Código de red no exitoso",
            reference=payload.Referencia,
        )

    # b) Buscar pedido pendiente por monto VES + teléfono emisor
    # usar la función existente en src/financial/database.py
    try:
        from src.financial.database import (
            buscar_pedidos_por_telefono_monto,
            seleccionar_mejor_match,
        )

        # Normalizar teléfono emisor
        telefono_emisor = payload.TelefonoEmisor
        if telefono_emisor.startswith(("V", "E", "v", "e")):
            telefono_emisor = telefono_emisor[1:]

        # Conversión VES→EUR ANTES de casar (regla de negocio):
        # el saldo vive en EUR (monto_total_eur fijo); el banco envía Monto
        # en VES. Se usa la tasa BCV del DÍA DEL PAGO (la tasa_eur_ves del
        # pedido puede ser distinta y NO debe afectar la casación).
        # Si no hay tasa disponible, se re-intenta tras encontrar el pedido
        # usando su propio monto EUR como fallback (ver más abajo).
        from src.financial.currency import convert_ves_to_eur, get_eur_ves_rate

        monto_ves = float(payload.Monto)
        tasa_pago = await get_eur_ves_rate()
        if tasa_pago:
            monto_busqueda_eur = convert_ves_to_eur(monto_ves, tasa_pago)
        else:
            logger.warning(
                "R4notifica: tasa EUR/VES no disponible, no se puede convertir "
                "VES→EUR para casar emisor=%s monto=%s VES ref=%s",
                telefono_emisor,
                payload.Monto,
                payload.Referencia,
            )
            monto_busqueda_eur = None

        if monto_busqueda_eur is not None:
            # Casar en EUR contra monto_total_eur (±1% interno)
            pedidos = buscar_pedidos_por_telefono_monto(
                telefono_emisor=telefono_emisor,
                monto_str=f"{monto_busqueda_eur:.2f}",
                estados_permitidos=["pendiente", "verificando", "parcial", "vencido"],
            )
        else:
            pedidos = []

        if not pedidos:
            logger.warning(
                "R4notifica: no hay pedido pendiente para emisor=%s monto=%s VES "
                "(%.2f EUR, tasa=%.2f) ref=%s",
                telefono_emisor,
                payload.Monto,
                monto_busqueda_eur or -1.0,
                tasa_pago or 0,
                payload.Referencia,
            )
            # Responder abono=True al banco (el pago llegó aunque no tengamos pedido)
            return WebhookProcessResult(
                success=True,
                code="00",
                message="NO_ORDER: Pago recibido sin pedido pendiente",
                reference=payload.Referencia,
            )

        # Seleccionar mejor match (scoring: teléfono exacto + monto exacto + reciente)
        # El scoring compara montos: pasar el EUR convertido, no el VES crudo.
        if monto_busqueda_eur is not None:
            pedido = seleccionar_mejor_match(pedidos, telefono_emisor, monto_busqueda_eur)
        else:
            # Sin tasa disponible: no hay EUR convertible confiable; si hay un
            # único candidato por teléfono, tomarlo (el monto ya no discrimina).
            pedido = pedidos[0] if len(pedidos) == 1 else None

        if not pedido:
            logger.warning(
                "R4notifica: no se pudo seleccionar match único entre %d candidatos",
                len(pedidos),
            )
            return WebhookProcessResult(
                success=True,
                code="00",
                message="AMBIGUOUS_MATCH: múltiples pedidos coinciden",
                reference=payload.Referencia,
            )

        fs_pedido_id = pedido.id
        assert fs_pedido_id is not None, "pedido.id no debería ser None"

        # c) Verificar pago via Financial Shield (método manual = confirmación bancaria)
        # convertir monto VES → EUR para el Financial Shield que trabaja en EUR
        # (la tasa y la conversión ya se obtuvieron arriba, antes de la casación)
        monto_eur = (
            convert_ves_to_eur(monto_ves, tasa_pago)
            if tasa_pago
            else pedido.monto_total_eur
        )

        logger.info(
            "R4notifica: match pedido_id=%d monto_ves=%.2f monto_eur=%.2f (tasa=%.2f)",
            fs_pedido_id,
            monto_ves,
            monto_eur,
            tasa_pago or 0,
        )

        from src.financial.verificacion import verificar_pago_manual

        resultado = await verificar_pago_manual(
            fs_pedido_id=fs_pedido_id,
            monto_eur=monto_eur,
            metodo_pago="pagomovil",
            referencia=payload.Referencia,
            verificado_por="banco_r4",
        )

        if not resultado.get("success"):
            logger.error("R4notifica: verificar_pago_manual falló: %s", resultado)
            return WebhookProcessResult(
                success=False,
                code="VERIFY_FAILED",
                message=resultado.get("mensaje", "Verificación falló"),
                reference=payload.Referencia,
            )

        logger.info(
            "R4notifica: pago VERIFICADO pedido_fs=%d ref=%s estado=%s",
            fs_pedido_id,
            payload.Referencia,
            resultado.get("nuevo_estado"),
        )

        # 2026-10-08 §1: ENCOLAR ENTREGA A DESPACHO tras verificación bancaria.
        # Antes el encolado solo ocurría en el flujo de conversación (Efectivo /
        # "ya pagué") → pedidos pagados por Pago Móvil nunca llegaban al chofer.
        # Idempotente (por fs_pedido_id). Si falla: log CRÍTICO + alerta al
        # Líder, pero NO romper la respuesta abono=True al banco.
        try:
            enc = _enqueue_delivery_from_fs(pedido)
            if enc.get("enqueued"):
                logger.info(
                    "R4notifica: entrega encolada a despacho order_id=%s (fs_pedido=%s)",
                    enc.get("order_id"),
                    fs_pedido_id,
                )
            elif not enc.get("existing"):
                logger.critical(
                    "R4notifica: FALLO encolando entrega fs_pedido=%s: %s — "
                    "el pedido está PAGADO pero NO está en dispatch_queue",
                    fs_pedido_id,
                    enc.get("error", "unknown"),
                )
                _alertar_lider(
                    f"⚠️ <b>ALERTA DESPACHO</b>\n"
                    f"Pedido #{fs_pedido_id} verificado PAGADO por banco R4 "
                    f"pero NO se pudo encolar a despacho.\n"
                    f"Error: {enc.get('error', 'desconocido')}\n"
                    f"Revisar y encolar manualmente."
                )
            # existing=True → ya encolado por otro flujo: no hacer nada
        except Exception as enc_err:
            logger.critical(
                "R4notifica: excepción encolando entrega fs_pedido=%s: %s",
                fs_pedido_id,
                enc_err,
                exc_info=True,
            )
            _alertar_lider(
                f"⚠️ <b>ALERTA DESPACHO</b>\n"
                f"Excepción encolando pedido #{fs_pedido_id} pagado: {enc_err}\n"
                f"Revisar y encolar manualmente."
            )

        # d) Sync a Odoo (best-effort, no bloquea si falla)
        try:
            import os

            from src.integrations.odoo.odoo_sync import OdooClient, OdooConfig

            odoo_cfg = OdooConfig(
                url=os.getenv("ODOO_URL", "http://localhost:8069"),
                db=os.getenv("ODOO_DB", ""),
                username=os.getenv("ODOO_USERNAME", ""),
                password=os.getenv("ODOO_PASSWORD", ""),
            )
            odoo = OdooClient(odoo_cfg)
            if odoo.connect():
                # Buscar factura relacionada al pedido en Odoo
                # El pedido_id de Odoo está en pedido.pedido_id (no fs_pedido_id)
                facturas = (
                    odoo.execute_kw(
                        "account.move",
                        "search_read",
                        [[("ref", "=", str(pedido.pedido_id))]],
                        {"fields": ["id"], "limit": 1},
                    )
                    if pedido.pedido_id
                    else []
                )
                if facturas:
                    odoo.register_payment(
                        invoice_id=facturas[0]["id"],
                        amount=monto_eur,
                        payment_method="pago_movil",
                        reference=payload.Referencia,
                    )
                    logger.info("R4notifica: pago syncado a Odoo factura=%s", facturas[0]["id"])
                else:
                    logger.info(
                        "R4notifica: no se encontró factura Odoo para pedido_id=%s",
                        pedido.pedido_id,
                    )
            else:
                logger.warning("R4notifica: no se pudo conectar a Odoo, sync omitido")
        except Exception as odoo_err:
            # Odoo es best-effort: el pago ya está verificado en fs_pedidos
            logger.warning("R4notifica: Odoo sync falló (no bloquea): %s", odoo_err)

        # e) Enviar WhatsApp al cliente
        try:
            # Resolver el módulo LIVE del bridge (con httpx client inicializado).
            # `from api.bridge import ...` cargaba una copia fría del módulo
            # (client=None) → "http client not initialized" (bug 2026-09-12).
            send_fn = _obtener_enviador_whatsapp()

            # Normalizar teléfono para Meta: formato internacional sin '+'
            tel = pedido.cliente_telefono or ""
            tel = tel.lstrip("+")
            if tel.startswith("58") and len(tel) == 12:
                pass  # ya tiene prefijo 58
            elif tel.startswith("0"):
                tel = "58" + tel[1:]
            elif len(tel) == 10:
                tel = "58" + tel

            if not tel:
                logger.warning("R4notifica: sin teléfono para enviar WhatsApp")
            else:
                msg = "✅ Pago confirmado. Gracias. 💧"
                if send_fn is not None:
                    sent = await send_fn(tel, msg)
                else:
                    # Sin módulo live disponible: envío directo best-effort
                    sent = await _enviar_whatsapp_directo(tel, msg)
                logger.info(
                    "R4notifica: WhatsApp enviado a %s: %s", tel[:6] + "****", sent
                )
        except Exception as wa_err:
            # Best-effort: el pago ya está verificado, no revertir nada
            logger.warning("R4notifica: WhatsApp falló (no bloquea): %s", wa_err)

        # f) Respuesta al banco
        return WebhookProcessResult(
            success=True,
            code="00",
            message=f"Pago verificado: pedido {fs_pedido_id}",
            reference=payload.Referencia,
            data={
                "fs_pedido_id": fs_pedido_id,
                "monto_eur": monto_eur,
                "nuevo_estado": resultado.get("nuevo_estado"),
            },
        )

    except Exception as e:
        logger.error("R4notifica: error procesando pago: %s", e, exc_info=True)
        # Responder abono=True al banco para que no reintente innecesariamente
        # pero loggear el error para investigación
        return WebhookProcessResult(
            success=True,
            code="INTERNAL_ERROR",
            message=f"Error interno: {e}",
            reference=payload.Referencia,
        )


# ============================================================
# Funciones de logging (mantenidas para referencia)
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
    request: Request,
    body: Any,
    endpoint_name: str,
    sign_string: str | None = None,
    expected_hash: str | None = None,
    received_hash: str | None = None,
) -> None:
    """
    Loguea detalles de fallo HMAC para diagnóstico.
    Captura el sign string y los hashes para comparar con el banco.
    """
    logger.warning(f"⚠️  HMAC FALLÓ en {endpoint_name}")
    logger.warning(f"   IP origen: {request.client.host if request.client else 'unknown'}")
    auth_header = request.headers.get("Authorization", "")
    logger.warning(
        f"   Authorization recibido: {auth_header[:30]}..."
        if len(auth_header) > 30
        else f"   Authorization recibido: {auth_header}"
    )
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

    Seguridad (PDF R4 CONECTA V3.0):
    - IP whitelist
    - Authorization: <UUID> directo (sin Bearer, sin HMAC)
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

    # === SEGURIDAD: validación estricta (sin modo captura) ===
    # 1. IP Whitelist
    await verify_ip_whitelist(request, config)
    # 2. Rate Limiting
    await verify_rate_limit(request, config)
    # 3. Authorization Token (UUID directo)
    await verify_auth_token(authorization, config)

    # Parsear body como JSON
    try:
        body = await request.json()
    except Exception:
        raw_body = await request.body()
        decoded = raw_body[:500].decode("utf-8", errors="replace")
        logger.warning(f"Body no es JSON válido. Raw (primeros 500 chars): {decoded}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Body JSON inválido",
        ) from None

    if not isinstance(body, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Body debe ser un objeto JSON",
        )

    # Log resumido del request (sin secrets)
    client_ip = request.headers.get("CF-Connecting-IP") or request.headers.get(
        "X-Forwarded-For", "unknown"
    )
    logger.info(f"Webhook consulta desde IP={client_ip} formato={detect_webhook_format(body)}")

    # Detectar formato del payload
    fmt = detect_webhook_format(body)
    logger.info(f"Formato detectado: {fmt}")

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
            logger.warning(f"Payload R4consulta inválido: {e}")
            return {"status": False}
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

    Seguridad (PDF R4 CONECTA V3.0):
    - IP whitelist
    - Authorization: <UUID> directo (sin Bearer, sin HMAC)
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

    # === SEGURIDAD: validación estricta (sin modo captura) ===
    # 1. IP Whitelist
    await verify_ip_whitelist(request, config)
    # 2. Rate Limiting
    await verify_rate_limit(request, config)
    # 3. Authorization Token (UUID directo)
    await verify_auth_token(authorization, config)

    # Parsear body como JSON
    try:
        body = await request.json()
    except Exception:
        raw_body = await request.body()
        decoded = raw_body[:500].decode("utf-8", errors="replace")
        logger.warning(f"Body no es JSON válido. Raw (primeros 500 chars): {decoded}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Body JSON inválido",
        ) from None

    # Validar con modelo Pydantic
    try:
        payload = R4NotificaRequest(**body)
    except Exception as e:
        logger.warning(f"Payload R4notifica inválido: {e}")
        return {"abono": False}

    # Log resumido (sin secrets)
    client_ip = request.headers.get("CF-Connecting-IP") or request.headers.get(
        "X-Forwarded-For", "unknown"
    )
    logger.info(
        f"Webhook notifica desde IP={client_ip}: ref={payload.Referencia} "
        f"monto={payload.Monto} emisor={payload.TelefonoEmisor} cod={payload.CodigoRed}"
    )

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


@router.post(
    "/c2p",
    summary="C2P - Hook pasivo de contingencia (NO vía principal)",
    description="""
    Hook de contingencia para una eventual notificación asincrónica de C2P.

    IMPORTANTE: el PDF R4 CONECTA V3.0 (pág. 30) documenta que la respuesta
    de R4c2p es SÍNCRONA (code + reference en el POST /MBc2p). NO existe
    webhook documentado para C2P. Este endpoint queda como hook pasivo:
    loggea la notificación y procesa el pago SOLO si el pedido sigue
    pendiente (idempotente: si ya fue confirmado por la vía síncrona,
    solo loggea y responde 200 sin duplicar).

    Seguridad (mismo modelo que /consulta y /notifica, PDF págs. 7 y 9):
    - IP whitelist
    - Authorization: UUID directo (sin Bearer, sin HMAC en webhooks entrantes)
    - Rate limiting
    """,
)
async def r4_c2p_webhook(
    request: Request,
    authorization: str | None = Header(None),
    config: R4WebhookConfig = _webhook_config_singleton,
) -> dict[str, Any]:
    """
    Hook pasivo C2P — contingencia asincrónica.

    Body supuesto (a validar con el banco; formato NO documentado):
        {"TelefonoDestino", "Cedula", "Monto", "Referencia", "code"}

    Response: {"status": true/false}
    """
    logger.info("=== C2P webhook pasivo recibido (contingencia) ===")

    # === SEGURIDAD: mismo modelo estricto que /consulta y /notifica ===
    await verify_ip_whitelist(request, config)
    await verify_rate_limit(request, config)
    await verify_auth_token(authorization, config)

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Body JSON inválido",
        ) from None

    if not isinstance(body, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Body debe ser un objeto JSON",
        )

    client_ip = request.headers.get("CF-Connecting-IP") or request.headers.get(
        "X-Forwarded-For", "unknown"
    )
    # Log resumido SIN secrets (el formato real no está documentado)
    keys = sorted(body.keys())
    logger.info("C2P pasivo desde IP=%s campos=%s", client_ip, keys)

    code = str(body.get("code", body.get("codigo", "")))
    reference = str(body.get("Referencia", body.get("reference", "")))
    telefono = str(body.get("TelefonoDestino", body.get("Telefono", "")))

    # Solo procesar aprobaciones (code "00"); todo lo demás se loggea y ack
    if code != "00":
        logger.info(
            "C2P pasivo: notificación no aprobatoria (code=%s) — solo log", code
        )
        return {"status": True}

    # Aprobación: intentar marcar el pedido SOLO si sigue pendiente.
    # procesar_pago_c2p_async es idempotente por referencia y tolera
    # pedidos ya pagados por la vía síncrona (primer ganador marca).
    try:
        monto = str(body.get("Monto", "0"))
        procesado = await procesar_pago_c2p_async(
            telefono=telefono, monto=monto, referencia=reference
        )
        logger.info(
            "C2P pasivo: referencia=%s procesado=%s (idempotente)", reference, procesado
        )
    except Exception as e:  # noqa: BLE001 - contingencia: nunca romper el webhook
        logger.warning("C2P pasivo: fallo procesando pago (no bloquea): %s", e)

    # Siempre ack al banco: la vía principal es la respuesta síncrona.
    return {"status": True}


async def procesar_pago_c2p_async(
    telefono: str, monto: str, referencia: str
) -> bool:
    """
    Contingencia C2P: marca pedido pendiente como pagado si hay match
    teléfono+monto. Idempotente: si no hay pedido pendiente que matchee,
    NO hace nada (puede haber sido confirmado por la vía síncrona).

    Returns: True si marcó un pedido, False si no hubo match/ya pagado.
    """
    if not telefono or not monto:
        return False

    try:
        from src.financial.database import buscar_pedidos_por_telefono_monto
        from src.financial.verificacion import verificar_pago_manual

        pedidos = buscar_pedidos_por_telefono_monto(telefono, monto)
        if not pedidos:
            logger.info(
                "C2P pasivo: sin pedido pendiente tel=%s monto=%s (¿ya pagado?)",
                telefono[:4] + "***",
                monto,
            )
            return False

        for pedido in pedidos:
            if pedido.id is None:
                continue
            resultado = await verificar_pago_manual(
                fs_pedido_id=pedido.id,
                monto_eur=pedido.monto_total_eur,
                metodo_pago="c2p",
                referencia=referencia or "C2P-ASYNC",
                verificado_por="r4_c2p_webhook",
            )
            if resultado.get("success"):
                logger.info(
                    "C2P pasivo: pedido %s marcado pagado ref=%s",
                    pedido.id,
                    referencia,
                )
                return True
            logger.warning("C2P pasivo: verificar_pago_manual rechazó: %s", resultado)
            return False
    except Exception as e:  # noqa: BLE001
        logger.warning("C2P pasivo: error buscando/marcando pedido: %s", e)
    return False


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
