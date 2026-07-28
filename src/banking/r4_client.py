"""R4 Banco - Cliente HTTP + HMAC-SHA256 para R4 Conecta V3.0"""

import asyncio
import hashlib
import hmac
import logging
import os
from datetime import datetime
from typing import Any

import httpx

from src.banking.r4_endpoints import ENDPOINTS, SIGN_STRINGS

logger = logging.getLogger("r4banco.client")


class R4BankError(Exception):
    """Error devuelto por el banco (code, message)"""

    def __init__(self, code: str, message: str, raw: dict = None):
        self.code = code
        self.message = message
        self.raw = raw
        super().__init__(f"R4BankError[{code}]: {message}")


class R4AuthError(Exception):
    """Error de autenticación/firma HMAC"""

    pass


class R4ValidationError(Exception):
    """Error de validación de request/response"""

    pass


class R4Client:
    """Cliente HTTP para R4 Conecta V3.0 con firma HMAC automática"""

    def __init__(
        self,
        commerce_token: str,
        hmac_key: str,
        base_url: str = "https://r4conecta.mibanco.com.ve/",
        timeout: float = 10.0,
        max_retries: int = 3,
    ):
        self.commerce_token = commerce_token
        self.hmac_key = hmac_key.encode() if isinstance(hmac_key, str) else hmac_key
        self.base_url = base_url.rstrip("/") + "/"
        self.timeout = timeout
        self.max_retries = max_retries

        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout),
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
        )

    def _build_sign_string(self, endpoint_key: str, payload: dict[str, Any]) -> str:
        """
        Construye el string a firmar según el manual R4 V3.0.
        Cada endpoint tiene su propio formato (ver SIGN_STRINGS en r4_endpoints.py)
        """
        template = SIGN_STRINGS.get(endpoint_key, "")
        if not template:
            logger.warning(f"No sign template for endpoint {endpoint_key}, using empty")
            return ""

        # Reemplazar placeholders con valores del payload
        sign_str = template
        for key, value in payload.items():
            placeholder = f"{{{key}}}"
            if placeholder in sign_str:
                sign_str = sign_str.replace(placeholder, str(value))

        return sign_str

    def _generate_hmac(self, sign_string: str) -> str:
        """Genera HMAC-SHA256 hex del string usando commerce_token como llave"""
        if not sign_string:
            return ""
        signature = hmac.new(self.hmac_key, sign_string.encode(), hashlib.sha256).hexdigest()
        return signature.upper()

    def _build_headers(self, endpoint_key: str, payload: dict[str, Any]) -> dict[str, str]:
        """Construye headers completos para el endpoint"""
        sign_string = self._build_sign_string(endpoint_key, payload)
        auth_token = self._generate_hmac(sign_string)

        return {
            "Content-Type": "application/json",
            "Authorization": auth_token,
            "Commerce": self.commerce_token,
        }

    async def _request_with_retry(
        self,
        method: str,
        endpoint_key: str,
        payload: dict[str, Any],
        extra_headers: dict[str, str] = None,
    ) -> dict[str, Any]:
        """Ejecuta request con retry exponencial"""
        url = self.base_url + ENDPOINTS[endpoint_key]
        headers = self._build_headers(endpoint_key, payload)
        if extra_headers:
            headers.update(extra_headers)

        last_error = None
        for attempt in range(self.max_retries):
            try:
                logger.debug(
                    f"R4 {method} {url} attempt={attempt+1} payload_keys={list(payload.keys())}"
                )

                if method.upper() == "GET":
                    response = await self._client.get(url, headers=headers, params=payload)
                else:
                    response = await self._client.post(url, headers=headers, json=payload)

                response.raise_for_status()
                data = response.json()

                # Verificar códigos de error del banco
                if isinstance(data, dict):
                    code = data.get("code") or data.get("codigo") or data.get("status")
                    if code and str(code) not in ("00", "202", "ACCP", "true", True):
                        raise R4BankError(
                            code=str(code),
                            message=data.get("message") or data.get("mensaje") or str(data),
                            raw=data,
                        )

                logger.info(
                    "R4 %s OK code=%s",
                    endpoint_key,
                    data.get("code") if isinstance(data, dict) else "N/A",
                )
                return data

            except httpx.HTTPStatusError as e:
                last_error = f"HTTP {e.response.status_code}: {e.response.text}"
                logger.warning(f"R4 {endpoint_key} HTTP error attempt {attempt+1}: {last_error}")
            except R4BankError:
                raise
            except Exception as e:
                last_error = str(e)
                logger.warning(f"R4 {endpoint_key} error attempt {attempt+1}: {last_error}")

            if attempt < self.max_retries - 1:
                wait = 2**attempt  # 1s, 2s, 4s...
                logger.info(f"R4 retry in {wait}s...")
                await asyncio.sleep(wait)

        raise R4BankError("RETRY_EXHAUSTED", f"Max retries exceeded: {last_error}")

    # ==================== MÉTODOS PÚBLICOS POR ENDPOINT ====================

    async def consultar_tasa_bcv(
        self, moneda: str = "USD", fecha_valor: str = None
    ) -> dict[str, Any]:
        """Consulta tasa BCV oficial. Endpoint: MBbcv"""
        if not fecha_valor:
            fecha_valor = datetime.now().strftime("%Y-%m-%d")
        payload = {"Moneda": moneda, "Fechavalor": fecha_valor}
        return await self._request_with_retry("POST", "bcv", payload)

    async def consultar_cliente(
        self, id_cliente: str, monto: str = None, telefono_comercio: str = None
    ) -> dict[str, Any]:
        """Consulta/validación cliente para pago móvil. Endpoint: R4consulta"""
        payload = {"IdCliente": id_cliente}
        if monto:
            payload["Monto"] = monto
        if telefono_comercio:
            payload["TelefonoComercio"] = telefono_comercio
        return await self._request_with_retry("POST", "consulta", payload)

    async def notificar_pago_movil(self, payload: dict[str, Any]) -> dict[str, Any]:
        """
        Recibe notificación de pago móvil entrante (P2P/P2C).
        NOTA: Este endpoint lo LLAMA EL BANCO a nuestro webhook.
        Este método es para TESTING: simular llamada saliente.
        """
        return await self._request_with_retry("POST", "notifica", payload)

    async def cobro_c2p(
        self,
        telefono_destino: str,
        cedula: str,
        concepto: str,
        banco: str,
        ip: str,
        monto: str,
        otp: str,
    ) -> dict[str, Any]:
        """Cobro C2P (Cobro a Proveedor/Persona). Endpoint: MBc2p"""
        payload = {
            "TelefonoDestino": telefono_destino,
            "Cedula": cedula,
            "Concepto": concepto,
            "Banco": banco,
            "Ip": ip,
            "Monto": monto,
            "Otp": otp,
        }
        return await self._request_with_retry("POST", "c2p", payload)

    async def anular_c2p(
        self, referencia: str, monto: str, banco: str, telefono: str
    ) -> dict[str, Any]:
        """Anulación C2P. Endpoint: MBanulacionC2P"""
        payload = {
            "Referencia": referencia,
            "Monto": monto,
            "Banco": banco,
            "Telefono": telefono,
        }
        return await self._request_with_retry("POST", "anulacion_c2p", payload)

    async def consultar_operacion(self, operacion_id: str) -> dict[str, Any]:
        """Consultar estado de operación (cuando devuelve AC00). Endpoint: ConsultarOperaciones"""
        payload = {"Id": operacion_id}
        return await self._request_with_retry("POST", "consultar_ops", payload)

    async def credito_inmediato(
        self,
        banco: str,
        cedula: str,
        telefono: str,
        monto: str,
        concepto: str,
    ) -> dict[str, Any]:
        """Crédito inmediato a teléfono. Endpoint: CreditoInmediato"""
        payload = {
            "Banco": banco,
            "Cedula": cedula,
            "Telefono": telefono,
            "Monto": monto,
            "Concepto": concepto,
        }
        return await self._request_with_retry("POST", "credito_inmediato", payload)

    async def credito_inmediato_cuenta(
        self,
        cedula: str,
        cuenta: str,
        monto: str,
        concepto: str,
    ) -> dict[str, Any]:
        """Crédito inmediato a cuenta 20 dígitos. Endpoint: CICuentas"""
        payload = {
            "Cedula": cedula,
            "Cuenta": cuenta,
            "Monto": monto,
            "Concepto": concepto,
        }
        return await self._request_with_retry("POST", "credito_inmediato_cuenta", payload)

    async def domiciliacion_cuenta(
        self,
        doc_id: str,
        nombre: str,
        cuenta: str,
        monto: str,
        concepto: str,
    ) -> dict[str, Any]:
        """Domiciliación por cuenta 20 dígitos. Endpoint: TransferenciaOnline/DomiciliacionCNTA"""
        payload = {
            "docId": doc_id,
            "nombre": nombre,
            "cuenta": cuenta,
            "monto": monto,
            "concepto": concepto,
        }
        return await self._request_with_retry("POST", "domiciliacion_cuenta", payload)

    async def domiciliacion_celular(
        self,
        doc_id: str,
        telefono: str,
        nombre: str,
        banco: str,
        monto: str,
        concepto: str,
    ) -> dict[str, Any]:
        """Domiciliación por teléfono. Endpoint: TransferenciaOnline/DomiciliacionCELE"""
        payload = {
            "docId": doc_id,
            "telefono": telefono,
            "nombre": nombre,
            "banco": banco,
            "monto": monto,
            "concepto": concepto,
        }
        return await self._request_with_retry("POST", "domiciliacion_cel", payload)

    async def generar_otp(
        self,
        banco: str,
        monto: str,
        telefono: str,
        cedula: str,
    ) -> dict[str, Any]:
        """Generar OTP para débito inmediato. Endpoint: GenerarOtp"""
        payload = {
            "Banco": banco,
            "Monto": monto,
            "Telefono": telefono,
            "Cedula": cedula,
        }
        return await self._request_with_retry("POST", "generar_otp", payload)

    async def debito_inmediato(
        self,
        banco: str,
        monto: str,
        telefono: str,
        cedula: str,
        nombre: str,
        otp: str,
        concepto: str,
    ) -> dict[str, Any]:
        """Débito inmediato (requiere OTP previo). Endpoint: DebitoInmediato"""
        payload = {
            "Banco": banco,
            "Monto": monto,
            "Telefono": telefono,
            "Cedula": cedula,
            "Nombre": nombre,
            "OTP": otp,
            "Concepto": concepto,
        }
        return await self._request_with_retry("POST", "debito_inmediato", payload)

    async def vuelto(
        self,
        telefono_destino: str,
        cedula: str,
        banco: str,
        monto: str,
        concepto: str = "PRUEBA",
        ip: str = "0.0.0.0",
    ) -> dict[str, Any]:
        """Vuelto (transferencia a teléfono). Endpoint: MBvuelto"""
        payload = {
            "TelefonoDestino": telefono_destino,
            "Cedula": cedula,
            "Banco": banco,
            "Monto": monto,
            "Concepto": concepto,
            "Ip": ip,
        }
        return await self._request_with_retry("POST", "vuelto", payload)

    async def dispersar_pagos(
        self,
        monto_total: str,
        fecha: str,  # MM/DD/YYYY
        referencia: str,
        personas: list,  # lista de dicts con nombres, documento, destino, montoPart
    ) -> dict[str, Any]:
        """Gestión de pagos (dispersión). Endpoint: R4pagos"""
        payload = {
            "monto": monto_total,
            "fecha": fecha,
            "Referencia": referencia,
            "personas": personas,
        }
        return await self._request_with_retry("POST", "dispersar", payload)

    async def close(self):
        """Cerrar cliente HTTP"""
        await self._client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()


# ==================== FACTORY ====================


def get_r4_client() -> R4Client:
    """Factory que lee credenciales de variables de entorno"""
    commerce_token = os.getenv("R4_COMMERCE_TOKEN")
    hmac_key = os.getenv("R4_HMAC_KEY")
    base_url = os.getenv("R4_BASE_URL", "https://r4conecta.mibanco.com.ve/")
    timeout = float(os.getenv("R4_TIMEOUT", "10"))

    if not commerce_token or not hmac_key:
        raise ValueError("R4_COMMERCE_TOKEN y R4_HMAC_KEY son requeridos en .env")

    return R4Client(
        commerce_token=commerce_token,
        hmac_key=hmac_key,
        base_url=base_url,
        timeout=timeout,
    )
