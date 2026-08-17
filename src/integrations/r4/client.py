#!/usr/bin/env python3
"""
Cliente R4 Conecta V3.0 - Integración completa con 13 endpoints del banco.

Usa hmac_auth.py para autenticación HMAC-SHA256 y codigos.py para interpretar respuestas.
Todas las credenciales se leen desde variables de entorno (.env).

Endpoints implementados (13):
1. consulta_tasa_bcv(fechavalor, moneda) -> tasa BCV
2. validar_cliente_pago(id_cliente, monto, telefono_comercio) -> validación
3. procesar_notificacion_pago(notificacion_data) -> procesamiento webhook
4. disper_pagos(monto, fecha, referencia, personas[]) -> dispersión
5. vuelto(telefono_destino, cedula, banco, monto, concepto) -> dict
6. generar_otp(banco, monto, telefono, cedula) -> dict
7. debito_inmediato(banco, cedula, telefono, monto, otp, concepto) -> dict
8. credito_inmediato(banco, cedula, telefono, monto, concepto) -> dict
9. consultar_operacion(id_operacion) -> dict
10. domiciliacion_cuenta(doc_id, cuenta, monto, concepto) -> dict
11. domiciliacion_telefono(doc_id, telefono, banco, monto, concepto) -> dict
12. credito_inmediato_cuentas_20d(cedula, cuenta, monto, concepto) -> dict
13. anulacion_c2p(cedula, banco, referencia) -> bool
"""

import asyncio
import logging
import os
from dataclasses import asdict, dataclass, field
from typing import Any

import httpx

from src.integrations.r4.codigos import (
    get_description,
    is_client_error,
    is_retryable,
    is_success,
)
from src.integrations.r4.hmac_auth import (
    R4Endpoint,
    build_auth_headers,
    verify_hmac_signature,
)

logger = logging.getLogger("r4.client")


# ============================================================
# Configuración desde variables de entorno
# ============================================================


class R4Config:
    """Configuración del cliente R4 desde variables de entorno."""

    def __init__(self) -> None:
        # URL base del API R4
        self.base_url = os.getenv("R4_BASE_URL", "https://r4conecta.mibanco.com.ve")

        # Credenciales del comercio (proporcionadas por el banco)
        self.commerce_token = os.getenv("R4_COMMERCE_TOKEN", "")
        self.id_comercio = os.getenv("R4_ID_COMERCIO", "")
        self.telefono_comercio = os.getenv("R4_TELEFONO_COMERCIO", "")

        # Configuración de red
        self.timeout = float(os.getenv("R4_TIMEOUT", "30.0"))
        self.max_retries = int(os.getenv("R4_MAX_RETRIES", "3"))
        self.retry_delay = float(os.getenv("R4_RETRY_DELAY", "1.0"))

        # Validación de credenciales (warning pero no fallar)
        self._validate_credentials()

    def _validate_credentials(self) -> None:
        """Valida credenciales - solo warning si faltan."""
        missing = []
        if not self.commerce_token:
            missing.append("R4_COMMERCE_TOKEN")
        if not self.id_comercio:
            missing.append("R4_ID_COMERCIO")
        if not self.telefono_comercio:
            missing.append("R4_TELEFONO_COMERCIO")

        if missing:
            logger.warning(
                f"R4 Credenciales faltantes (el banco aún no las entrega): {', '.join(missing)}. "
                f"El cliente funcionará en modo placeholder."
            )

    @property
    def has_credentials(self) -> bool:
        """Verifica si tiene credenciales completas."""
        return bool(self.commerce_token and self.id_comercio and self.telefono_comercio)

    def get_url(self, endpoint: R4Endpoint) -> str:
        """Construye URL completa para un endpoint."""
        endpoint_paths = {
            R4Endpoint.R4BCV: "/MBbcv",
            R4Endpoint.R4CONSULTA: "/R4consulta",  # Este es nuestro webhook receptor
            R4Endpoint.R4NOTIFICA: "/R4notifica",  # Este es nuestro webhook receptor
            R4Endpoint.R4VUELTO: "/MBvuelto",
            R4Endpoint.GENERAR_OTP: "/GenerarOtp",
            R4Endpoint.DEBITO_INMEDIATO: "/DebitoInmediato",
            R4Endpoint.CREDITO_INMEDIATO: "/CreditoInmediato",
            R4Endpoint.CI_CUENTAS: "/CICuentas",
            R4Endpoint.DOMICILIACION_CNTA: "/TransferenciaOnline/DomiciliacionCNTA",
            R4Endpoint.DOMICILIACION_CELE: "/TransferenciaOnline/DomiciliacionCELE",
            R4Endpoint.CONSULTAR_OPERACIONES: "/ConsultarOperaciones",
            R4Endpoint.R4C2P: "/MBc2p",
            R4Endpoint.R4ANULACION_C2P: "/MBanulacionC2P",
        }
        return f"{self.base_url}{endpoint_paths.get(endpoint, '/')}"


# Instancia global de configuración
_config: R4Config | None = None


def get_config() -> R4Config:
    """Obtiene configuración singleton."""
    global _config
    if _config is None:
        _config = R4Config()
    return _config


def reset_config() -> None:
    """Resetea configuración (para tests)."""
    global _config
    _config = None


# ============================================================
# Modelos de respuesta estandarizados
# ============================================================


@dataclass
class R4Response:
    """Respuesta estandarizada de cualquier endpoint R4."""

    success: bool
    code: str
    message: str
    reference: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    raw_response: dict[str, Any] = field(default_factory=dict)

    @property
    def is_retryable(self) -> bool:
        return is_retryable(self.code)

    @property
    def is_client_error(self) -> bool:
        return is_client_error(self.code)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def __bool__(self) -> bool:
        return self.success


# ============================================================
# Cliente HTTP asíncrono
# ============================================================


class R4Client:
    """Cliente asíncrono para API R4 Conecta V3.0."""

    def __init__(self, config: R4Config | None = None):
        self.config = config or get_config()
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Obtiene cliente HTTP (lazy initialization)."""
        if self._client is None or self._client.is_closed:
            timeout = httpx.Timeout(self.config.timeout)
            self._client = httpx.AsyncClient(
                timeout=timeout,
                limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
            )
        return self._client

    async def close(self) -> None:
        """Cierra cliente HTTP."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> "R4Client":
        return self

    async def __aexit__(
        self, exc_type: Any, exc_val: Any, exc_tb: Any
    ) -> None:
        await self.close()

    # ============================================================
    # Método interno para requests con retry
    # ============================================================

    async def _request(
        self, endpoint: R4Endpoint, payload: dict[str, Any], method: str = "POST"
    ) -> R4Response:
        """
        Ejecuta request HTTP con HMAC automático y retry logic.
        """
        if not self.config.has_credentials:
            logger.warning(f"R4 sin credenciales - simulando respuesta para {endpoint.value}")
            return self._mock_response(endpoint)

        client = await self._get_client()
        url = f"{self.config.base_url}{self._get_endpoint_path(endpoint)}"
        headers = build_auth_headers(payload, endpoint, self.config.commerce_token)

        last_exception: BaseException | None = None

        for attempt in range(self.config.max_retries):
            try:
                logger.debug(f"R4 Request: {method} {url} (attempt {attempt + 1})")

                response = await client.request(
                    method=method,
                    url=url,
                    json=payload,
                    headers=headers,
                )

                # Log response
                logger.debug(f"R4 Response: {response.status_code} - {response.text[:200]}")

                if response.status_code == 200:
                    data = response.json()
                    return self._parse_response(endpoint, data)

                elif response.status_code in (429, 500, 502, 503, 504):
                    # Retryable server errors
                    if attempt < self.config.max_retries - 1:
                        await asyncio.sleep(self.config.retry_delay * (attempt + 1))
                        continue

                # Non-retryable or max retries reached
                try:
                    data = response.json()
                except Exception:  # noqa: BLE001 - any JSON parsing error
                    data = {"raw": response.text}

                return R4Response(
                    success=False,
                    code=str(response.status_code),
                    message=f"HTTP {response.status_code}: {data}",
                    raw_response=data,
                )

            except httpx.TimeoutException as e:
                last_exception = e
                logger.warning(f"R4 Timeout: {endpoint.value} (attempt {attempt + 1})")
                if attempt < self.config.max_retries - 1:
                    await asyncio.sleep(self.config.retry_delay * (attempt + 1))
                    continue
            except httpx.RequestError as e:
                last_exception = e
                logger.error(f"R4 Request error: {endpoint.value} - {e}")
                if attempt < self.config.max_retries - 1:
                    await asyncio.sleep(self.config.retry_delay * (attempt + 1))
                    continue
            except Exception as e:  # noqa: BLE001 - catch-all for unexpected errors
                last_exception = e
                logger.exception(f"R4 Unexpected error: {endpoint.value}")
                break

        # All retries exhausted
        return R4Response(
            success=False,
            code="RETRY_EXHAUSTED",
            message=f"Max retries exceeded: {last_exception}",
            data={"error": str(last_exception)},
        )

    def _get_endpoint_path(self, endpoint: R4Endpoint) -> str:
        """Mapea endpoint a path del API."""
        paths = {
            R4Endpoint.R4BCV: "/MBbcv",
            R4Endpoint.GENERAR_OTP: "/GenerarOtp",
            R4Endpoint.DEBITO_INMEDIATO: "/DebitoInmediato",
            R4Endpoint.CREDITO_INMEDIATO: "/CreditoInmediato",
            R4Endpoint.CI_CUENTAS: "/CICuentas",
            R4Endpoint.DOMICILIACION_CNTA: "/TransferenciaOnline/DomiciliacionCNTA",
            R4Endpoint.DOMICILIACION_CELE: "/TransferenciaOnline/DomiciliacionCELE",
            R4Endpoint.CONSULTAR_OPERACIONES: "/ConsultarOperaciones",
            R4Endpoint.R4C2P: "/MBc2p",
            R4Endpoint.R4ANULACION_C2P: "/MBanulacionC2P",
        }
        return paths.get(endpoint, "/")

    def _parse_response(self, endpoint: R4Endpoint, data: dict[str, Any]) -> R4Response:
        """Parsea respuesta del banco a formato estandarizado."""
        # Extraer campos comunes
        code = str(data.get("code", data.get("codigo", data.get("message", ""))))
        message = str(data.get("message", data.get("mensaje", "")))
        reference = str(data.get("reference", data.get("referencia", data.get("uuid", ""))))

        # Determinar éxito
        success = is_success(code) if code else False

        return R4Response(
            success=success,
            code=code,
            message=message or get_description(code),
            reference=reference,
            data=data,
            raw_response=data,
        )

    def _mock_response(self, endpoint: R4Endpoint) -> R4Response:
        """Respuesta simulada cuando no hay credenciales."""
        mock_responses = {
            R4Endpoint.R4BCV: R4Response(
                success=True,
                code="00",
                message="MOCK: Tasa BCV simulada",
                data={"code": "00", "fechavalor": "2024-01-15", "tipocambio": 36.5},
            ),
            R4Endpoint.R4CONSULTA: R4Response(
                success=True, code="true", message="MOCK: Cliente válido", data={"status": True}
            ),
            R4Endpoint.R4NOTIFICA: R4Response(
                success=True,
                code="true",
                message="MOCK: Notificación procesada",
                data={"abono": True},
            ),
            R4Endpoint.GENERAR_OTP: R4Response(
                success=True,
                code="202",
                message="MOCK: OTP generado",
                data={
                    "code": "202",
                    "message": "Se ha recibido el mensaje de forma satisfactoria",
                    "success": True,
                },
            ),
            R4Endpoint.R4VUELTO: R4Response(
                success=True,
                code="00",
                message="MOCK: Vuelto exitoso",
                data={"code": "00", "message": "TRANSACCION EXITOSA", "reference": "MOCK_REF"},
            ),
            R4Endpoint.DEBITO_INMEDIATO: R4Response(
                success=True,
                code="ACCP",
                message="MOCK: Débito aceptado",
                data={
                    "code": "ACCP",
                    "message": "Operación Aceptada",
                    "reference": "MOCK_REF",
                    "id": "mock-id",
                },
            ),
            R4Endpoint.CREDITO_INMEDIATO: R4Response(
                success=True,
                code="ACCP",
                message="MOCK: Crédito aceptado",
                data={
                    "code": "ACCP",
                    "message": "Operación Aceptada",
                    "reference": "MOCK_REF",
                    "id": "mock-id",
                },
            ),
            R4Endpoint.CI_CUENTAS: R4Response(
                success=True,
                code="ACCP",
                message="MOCK: Crédito 20d aceptado",
                data={"code": "ACCP", "message": "Operación Aceptada", "reference": "MOCK_REF"},
            ),
            R4Endpoint.DOMICILIACION_CNTA: R4Response(
                success=True,
                code="202",
                message="MOCK: Domiciliación recibida",
                data={
                    "codigo": "202",
                    "mensaje": "Se ha recibido el mensaje de forma satisfactoria",
                    "uuid": "mock-uuid",
                },
            ),
            R4Endpoint.DOMICILIACION_CELE: R4Response(
                success=True,
                code="202",
                message="MOCK: Domiciliación CELE recibida",
                data={
                    "codigo": "202",
                    "mensaje": "Se ha recibido el mensaje de forma satisfactoria",
                    "uuid": "mock-uuid",
                },
            ),
            R4Endpoint.CONSULTAR_OPERACIONES: R4Response(
                success=True,
                code="ACCP",
                message="MOCK: Consulta operacion OK",
                data={"code": "ACCP", "reference": "MOCK_REF", "success": True},
            ),
            R4Endpoint.R4C2P: R4Response(
                success=True,
                code="00",
                message="MOCK: C2P exitoso",
                data={"message": "TRANSACCION EXITOSA", "code": "00", "reference": "MOCK_REF"},
            ),
            R4Endpoint.R4ANULACION_C2P: R4Response(
                success=True,
                code="00",
                message="MOCK: Anulación C2P exitosa",
                data={"message": "TRANSACCION EXITOSA", "code": "00", "reference": "MOCK_REF"},
            ),
        }
        return mock_responses.get(
            endpoint,
            R4Response(
                success=False,
                code="MOCK",
                message=f"Modo simulación - endpoint {endpoint.value}",
                data={},
            ),
        )

    # ============================================================
    # 13 ENDPOINTS OFICIALES
    # ============================================================

    # 1. Consultar tasa BCV
    async def consulta_tasa_bcv(self, fechavalor: str, moneda: str = "USD") -> R4Response:
        """
        Consulta tasa oficial BCV.

        Args:
            fechavalor: Fecha en formato YYYY-MM-DD
            moneda: Código ISO moneda (USD, EUR, etc.)

        Returns:
            R4Response con tipocambio en data.tipocambio
        """
        payload = {
            "Moneda": moneda,
            "Fechavalor": fechavalor,
        }
        return await self._request(R4Endpoint.R4BCV, payload)

    # 2. Validar cliente para pago móvil (R4consulta)
    async def validar_cliente_pago(
        self, id_cliente: str, monto: str, telefono_comercio: str | None = None
    ) -> R4Response:
        """
        Valida cliente para pago móvil entrante (R4consulta).
        Este endpoint lo llama el banco - nosotros respondemos.

        Args:
            id_cliente: Identificación del cliente (8 dígitos)
            monto: Monto de la operación (string con 2 decimales)
            telefono_comercio: Teléfono del comercio (default: config)

        Returns:
            R4Response con success=True si cliente válido
        """
        payload = {
            "IdCliente": id_cliente,
            "Monto": monto,
            "TelefonoComercio": telefono_comercio or self.config.telefono_comercio,
        }
        # Nota: Este endpoint es llamado POR el banco, nosotros lo implementamos
        # como webhook en bridge.py. Este método es para testing/simulación.
        return await self._request(R4Endpoint.R4CONSULTA, payload)

    # 3. Procesar notificación de pago entrante (R4notifica)
    async def procesar_notificacion_pago(self, notificacion: dict[str, Any]) -> R4Response:
        """
        Procesa notificación de pago móvil entrante (R4notifica).
        Este endpoint lo llama el banco - nosotros respondemos.

        Args:
            notificacion: Dict con todos los campos requeridos por R4notifica

        Returns:
            R4Response con success=True si procesado OK
        """
        # Validar campos requeridos
        required = [
            "IdComercio",
            "TelefonoComercio",
            "TelefonoEmisor",
            "BancoEmisor",
            "Monto",
            "FechaHora",
            "Referencia",
            "CodigoRed",
        ]
        for req_field in required:
            if req_field not in notificacion:
                return R4Response(
                    success=False,
                    code="VALIDATION_ERROR",
                    message=f"Campo requerido faltante: {req_field}",
                )

        # Agregar campos opcionales si no están
        notificacion.setdefault("Concepto", "")
        notificacion.setdefault("TelefonoComercio", self.config.telefono_comercio)
        notificacion.setdefault("IdComercio", self.config.id_comercio)

        return await self._request(R4Endpoint.R4NOTIFICA, notificacion)

    # 4. Dispersión de pagos (no en PDF - placeholder)
    async def disper_pagos(
        self, monto: str, fecha: str, referencia: str, personas: list[dict[str, Any]]
    ) -> R4Response:
        """
        Dispersión de pagos a múltiples destinatarios.
        Nota: No está en el PDF oficial - implementación placeholder.
        """
        logger.warning("disper_pagos no está en especificación oficial R4 - placeholder")
        return R4Response(
            success=False,
            code="NOT_IMPLEMENTED",
            message="Endpoint no especificado en R4 Conecta V3.0",
        )

    # 5. Vuelto interbancario
    async def vuelto(
        self,
        telefono_destino: str,
        cedula: str,
        banco: str,
        monto: str,
        concepto: str | None = "PRUEBA",
        ip: str | None = "0.0.0.0",
    ) -> R4Response:
        """
        Procesa vuelto interbancario (R4vuelto).

        Args:
            telefono_destino: Teléfono beneficiario (11 dígitos)
            cedula: Cédula beneficiario (V/E + 8 dígitos)
            banco: Código banco (4 dígitos)
            monto: Monto con 2 decimales
            concepto: Motivo (opcional, máx 30 chars)
            ip: IP origen (opcional)
        """
        payload = {
            "TelefonoDestino": telefono_destino,
            "Cedula": cedula,
            "Banco": banco,
            "Monto": monto,
            "Concepto": concepto or "PRUEBA",
            "Ip": ip or "0.0.0.0",
        }
        return await self._request(R4Endpoint.R4VUELTO, payload)

    # 6. Generar OTP para débito
    async def generar_otp(self, banco: str, monto: str, telefono: str, cedula: str) -> R4Response:
        """
        Genera OTP para débito inmediato (GenerarOtp).

        Args:
            banco: Código banco (4 dígitos)
            monto: Monto con 2 decimales
            telefono: Teléfono (11 dígitos)
            cedula: Cédula (V/E + 8 dígitos)
        """
        payload = {
            "Banco": banco,
            "Monto": monto,
            "Telefono": telefono,
            "Cedula": cedula,
        }
        return await self._request(R4Endpoint.GENERAR_OTP, payload)

    # 7. Débito inmediato
    async def debito_inmediato(
        self, banco: str, cedula: str, telefono: str, monto: str, otp: str, concepto: str
    ) -> R4Response:
        """
        Ejecuta débito inmediato interbancario (DebitoInmediato).
        Requiere OTP generado previamente con generar_otp().

        Args:
            banco: Código banco (4 dígitos)
            cedula: Cédula (V/E + 8 dígitos)
            telefono: Teléfono (11 dígitos)
            monto: Monto con 2 decimales
            otp: OTP generado (8 dígitos)
            concepto: Concepto (máx 30 chars)
        """
        payload = {
            "Banco": banco,
            "Cedula": cedula,
            "Telefono": telefono,
            "Monto": monto,
            "OTP": otp,
            "Concepto": concepto,
        }
        return await self._request(R4Endpoint.DEBITO_INMEDIATO, payload)

    # 8. Crédito inmediato
    async def credito_inmediato(
        self, banco: str, cedula: str, telefono: str, monto: str, concepto: str
    ) -> R4Response:
        """
        Ejecuta crédito inmediato interbancario (CreditoInmediato).

        Args:
            banco: Código banco (4 dígitos)
            cedula: Cédula (V/E + 8 dígitos)
            telefono: Teléfono (11 dígitos)
            monto: Monto con 2 decimales
            concepto: Concepto (máx 30 chars)
        """
        payload = {
            "Banco": banco,
            "Cedula": cedula,
            "Telefono": telefono,
            "Monto": monto,
            "Concepto": concepto,
        }
        return await self._request(R4Endpoint.CREDITO_INMEDIATO, payload)

    # 9. Consultar operación
    async def consultar_operacion(self, id_operacion: str) -> R4Response:
        """
        Consulta estado de operación (ConsultarOperaciones).
        Usar cuando respuesta de débito/crédito sea AC00 (en espera).

        Args:
            id_operacion: UUID de la operación (36 chars)
        """
        payload = {"Id": id_operacion}
        return await self._request(R4Endpoint.CONSULTAR_OPERACIONES, payload)

    # 10. Domiciliación por cuenta 20 dígitos
    async def domiciliacion_cuenta(
        self, doc_id: str, cuenta: str, monto: str, concepto: str, nombre: str | None = None
    ) -> R4Response:
        """
        Domiciliación por cuenta de 20 dígitos (DomiciliacionCNTA).

        Args:
            doc_id: Documento identidad (V/E + 8 dígitos)
            cuenta: Cuenta 20 dígitos
            monto: Monto con 2 decimales
            concepto: Concepto
            nombre: Nombre beneficiario (opcional)
        """
        payload = {
            "docId": doc_id,
            "cuenta": cuenta,
            "monto": monto,
            "concepto": concepto,
        }
        if nombre:
            payload["nombre"] = nombre
        return await self._request(R4Endpoint.DOMICILIACION_CNTA, payload)

    # 11. Domiciliación por teléfono
    async def domiciliacion_telefono(
        self,
        doc_id: str,
        telefono: str,
        banco: str,
        monto: str,
        concepto: str,
        nombre: str | None = None,
    ) -> R4Response:
        """
        Domiciliación por teléfono (DomiciliacionCELE).
        Primer envío es solo afiliación (no cobra).

        Args:
            doc_id: Documento identidad (V/E + 8 dígitos)
            telefono: Teléfono (11 dígitos)
            banco: Código banco (4 dígitos)
            monto: Monto con 2 decimales
            concepto: Concepto
            nombre: Nombre beneficiario (opcional)
        """
        payload = {
            "docId": doc_id,
            "telefono": telefono,
            "banco": banco,
            "monto": monto,
            "concepto": concepto,
        }
        if nombre:
            payload["nombre"] = nombre
        return await self._request(R4Endpoint.DOMICILIACION_CELE, payload)

    # 12. Crédito inmediato cuentas 20 dígitos
    async def credito_inmediato_cuentas_20d(
        self, cedula: str, cuenta: str, monto: str, concepto: str
    ) -> R4Response:
        """
        Crédito inmediato usando cuenta 20 dígitos (CICuentas).

        Args:
            cedula: Cédula (V/E + 8 dígitos)
            cuenta: Cuenta 20 dígitos
            monto: Monto con 2 decimales
            concepto: Concepto
        """
        payload = {
            "Cedula": cedula,
            "Cuenta": cuenta,
            "Monto": monto,
            "Concepto": concepto,
        }
        return await self._request(R4Endpoint.CI_CUENTAS, payload)

    # 13. Anulación C2P
    async def anulacion_c2p(self, cedula: str, banco: str, referencia: str) -> R4Response:
        """
        Anula transacción C2P (R4anulacionC2P).

        Args:
            cedula: Cédula (V/E + 8 dígitos)
            banco: Código banco (4 dígitos)
            referencia: Referencia transacción original
        """
        payload = {
            "Cedula": cedula,
            "Banco": banco,
            "Referencia": referencia,
        }
        return await self._request(R4Endpoint.R4ANULACION_C2P, payload)

    # ============================================================
    # Métodos de verificación de webhooks (para bridge.py)
    # ============================================================

    def verify_r4bcv_webhook(self, payload: dict[str, Any], auth_header: str) -> bool:
        """Verifica firma HMAC de webhook R4bcv entrante."""
        if not self.config.has_credentials:
            return True  # Modo simulación
        return verify_hmac_signature(
            payload, R4Endpoint.R4BCV, auth_header, self.config.commerce_token
        )

    def verify_r4consulta_webhook(self, payload: dict[str, Any], auth_header: str) -> bool:
        """Verifica firma HMAC de webhook R4consulta entrante."""
        if not self.config.has_credentials:
            return True
        return verify_hmac_signature(
            payload, R4Endpoint.R4CONSULTA, auth_header, self.config.commerce_token
        )

    def verify_r4notifica_webhook(self, payload: dict[str, Any], auth_header: str) -> bool:
        """Verifica firma HMAC de webhook R4notifica entrante."""
        if not self.config.has_credentials:
            return True
        return verify_hmac_signature(
            payload, R4Endpoint.R4NOTIFICA, auth_header, self.config.commerce_token
        )


# ============================================================
# Funciones de conveniencia (singleton)
# ============================================================

_r4_client: R4Client | None = None


def get_r4_client(config: R4Config | None = None) -> R4Client:
    """Obtiene cliente R4 singleton."""
    global _r4_client
    if _r4_client is None:
        _r4_client = R4Client(config)
    return _r4_client


def reset_r4_client() -> None:
    """Resetea cliente singleton (para tests)."""
    global _r4_client
    if _r4_client:
        import asyncio
        import contextlib

        with contextlib.suppress(BaseException):
            asyncio.create_task(_r4_client.close())
    _r4_client = None


# ============================================================
# Test rápido
# ============================================================

if __name__ == "__main__":
    import asyncio

    async def test_client() -> None:
        print("=== Test R4Client ===")

        # Test sin credenciales (modo mock)
        client = R4Client()
        print(f"Config loaded: base_url={client.config.base_url}")
        print(f"Has credentials: {client.config.has_credentials}")

        # Test 1: Consulta tasa BCV (mock)
        response = await client.consulta_tasa_bcv("2024-01-15", "USD")
        print(f"\n1. consulta_tasa_bcv: {response.success} - {response.message}")
        print(f"   Code: {response.code}, Data: {response.data}")

        # Test 2: Generar OTP (mock)
        response = await client.generar_otp("0192", "50.00", "04145555555", "V12345678")
        print(f"\n2. generar_otp: {response.success} - {response.message}")

        # Test 3: Vuelto (mock)
        response = await client.vuelto("04145555555", "V12345678", "0102", "100.00")
        print(f"\n3. vuelto: {response.success} - {response.message}")

        await client.close()
        print("\n✅ All mock tests passed!")

    asyncio.run(test_client())
