#!/usr/bin/env python3
"""
Tests de cobertura para R4 webhooks.py y hmac_auth.py.

Cubre:
- R4WebhookConfig: init, defaults, validate, reset
- Rate limiting: check_rate_limit (ok, exceeded, window cleanup)
- IP whitelist: verify_ip_whitelist (allowed, rejected, X-Forwarded-For)
- Auth token: verify_auth_token (ok, missing, empty, mismatch, no config)
- Rate limit middleware: verify_rate_limit
- security_dependency: chained verifications
- detect_webhook_format: MBconsulta, R4consulta, default
- Pydantic models: R4ConsultaRequest, R4NotificaRequest (valid/invalid)
- WebhookProcessResult: to_consulta_response, to_notifica_response
- process_r4consulta: with pedidos, without pedidos, error
- process_r4notifica: CodigoRed != 00, no pedido, success
- process_mbconsulta: mapping, fallback
- Router endpoints: /consulta, /notifica, /health
- HMAC: build_sign_string, compute_hmac_sha256, verify_hmac_signature,
  build_auth_headers, get_sign_string_description, all sign_* convenience funcs
"""

import hashlib
import hmac
import os
import sys
import time
from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

sys.path.insert(0, "/mnt/ssd_trabajo/hermes-agent")

from src.integrations.r4.hmac_auth import (
    R4Endpoint,
    build_auth_headers,
    build_sign_string,
    compute_hmac_sha256,
    get_sign_string_description,
    verify_hmac_signature,
)
from src.integrations.r4.webhooks import (
    MBConsultaResponse,
    R4ConsultaRequest,
    R4ConsultaResponse,
    R4NotificaRequest,
    R4NotificaResponse,
    R4WebhookConfig,
    WebhookProcessResult,
    _log_full_request,
    _log_hmac_failure,
    _rate_limit_store,
    check_rate_limit,
    detect_webhook_format,
    get_webhook_config,
    include_r4_webhooks,
    process_mbconsulta,
    process_r4consulta,
    process_r4notifica,
    reset_webhook_config,
    router,
    verify_auth_token,
    verify_ip_whitelist,
    verify_rate_limit,
)

# ============================================================
# Fixtures
# ============================================================

TEST_AUTH_TOKEN = "test-uuid-auth-token-12345"
TEST_COMMERCE_SECRET = "test-commerce-secret"
TEST_ALLOWED_IP = "192.168.1.100"


@pytest.fixture
def mock_config() -> Generator[R4WebhookConfig, None, None]:
    """Config con valores de test."""
    with patch.dict(
        os.environ,
        {
            "R4_WEBHOOK_AUTH_TOKEN": TEST_AUTH_TOKEN,
            "R4_COMMERCE_SECRET": TEST_COMMERCE_SECRET,
            "R4_WEBHOOK_ALLOWED_IPS": TEST_ALLOWED_IP,
            "R4_WEBHOOK_RATE_LIMIT": "5",
            "R4_WEBHOOK_RATE_WINDOW": "60",
        },
    ):
        reset_webhook_config()
        cfg = get_webhook_config()
        yield cfg
    reset_webhook_config()


@pytest.fixture
def clean_config() -> Generator[None, None, None]:
    """Reset config global."""
    reset_webhook_config()
    yield
    reset_webhook_config()


def _mock_request(ip: str = TEST_ALLOWED_IP, headers: dict[str, str] | None = None) -> MagicMock:
    """Crea un mock de Request FastAPI."""
    req = MagicMock()
    req.client = MagicMock()
    req.client.host = ip
    req.headers = headers or {}
    return req


# ============================================================
# R4WebhookConfig
# ============================================================


class TestR4WebhookConfig:
    def test_config_with_env(self, mock_config: R4WebhookConfig) -> None:
        assert TEST_ALLOWED_IP in mock_config.allowed_ips
        assert mock_config.auth_token == TEST_AUTH_TOKEN
        assert mock_config.commerce_secret == TEST_COMMERCE_SECRET
        assert mock_config.rate_limit_requests == 5
        assert mock_config.rate_limit_window == 60

    def test_config_defaults(self, clean_config: None) -> None:
        with patch.dict(
            os.environ,
            {"R4_WEBHOOK_ALLOWED_IPS": "", "R4_WEBHOOK_AUTH_TOKEN": ""},
            clear=False,
        ):
            reset_webhook_config()
            cfg = get_webhook_config()
            assert len(cfg.allowed_ips) == 3  # default IPs
            assert cfg.auth_token == ""

    def test_config_commerce_secret_fallback(self, clean_config: None) -> None:
        with patch.dict(
            os.environ,
            {
                "R4_COMMERCE_SECRET": "",
                "R4_COMMERCE_TOKEN": "fallback_token",
                "R4_WEBHOOK_AUTH_TOKEN": "auth",
                "R4_WEBHOOK_ALLOWED_IPS": "1.2.3.4",
            },
        ):
            reset_webhook_config()
            cfg = get_webhook_config()
            assert cfg.commerce_secret == "fallback_token"

    def test_reset_webhook_config(self, clean_config: None) -> None:
        with patch.dict(
            os.environ, {"R4_WEBHOOK_AUTH_TOKEN": "x", "R4_WEBHOOK_ALLOWED_IPS": "1.2.3.4"}
        ):
            cfg1 = get_webhook_config()
            reset_webhook_config()
            with patch.dict(
                os.environ, {"R4_WEBHOOK_AUTH_TOKEN": "y", "R4_WEBHOOK_ALLOWED_IPS": "5.6.7.8"}
            ):
                cfg2 = get_webhook_config()
                assert cfg1.auth_token == "x"
                assert cfg2.auth_token == "y"


# ============================================================
# Rate limiting
# ============================================================


class TestRateLimit:
    def test_rate_limit_allows_under_limit(self, mock_config: R4WebhookConfig) -> None:
        ip = "10.0.0.1"
        _rate_limit_store.clear()
        for _ in range(5):
            assert check_rate_limit(ip, mock_config) is True

    def test_rate_limit_blocks_over_limit(self, mock_config: R4WebhookConfig) -> None:
        ip = "10.0.0.2"
        _rate_limit_store.clear()
        for _ in range(5):
            check_rate_limit(ip, mock_config)
        assert check_rate_limit(ip, mock_config) is False

    def test_rate_limit_window_cleanup(self) -> None:
        ip = "10.0.0.3"
        _rate_limit_store.clear()
        # Simular timestamps viejos
        _rate_limit_store[ip] = [time.time() - 100, time.time() - 200]
        cfg = MagicMock()
        cfg.rate_limit_window = 60
        cfg.rate_limit_requests = 5
        result = check_rate_limit(ip, cfg)
        assert result is True
        # Los viejos se limpiaron
        assert len(_rate_limit_store[ip]) == 1


# ============================================================
# verify_ip_whitelist
# ============================================================


class TestIPWhitelist:
    @pytest.mark.asyncio
    async def test_ip_allowed(self, mock_config: R4WebhookConfig) -> None:
        req = _mock_request(ip=TEST_ALLOWED_IP)
        await verify_ip_whitelist(req, mock_config)  # no raise

    @pytest.mark.asyncio
    async def test_ip_rejected_403(self, mock_config: R4WebhookConfig) -> None:
        from fastapi import HTTPException

        req = _mock_request(ip="999.999.999.999")
        with pytest.raises(HTTPException) as exc_info:
            await verify_ip_whitelist(req, mock_config)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_ip_forwarded_for(self, mock_config: R4WebhookConfig) -> None:
        req = _mock_request(ip="10.0.0.99")
        req.headers = {"X-Forwarded-For": TEST_ALLOWED_IP}
        await verify_ip_whitelist(req, mock_config)  # no raise

    @pytest.mark.asyncio
    async def test_ip_no_client(self, mock_config: R4WebhookConfig) -> None:
        from fastapi import HTTPException

        req = MagicMock()
        req.client = None
        req.headers = {}
        with pytest.raises(HTTPException) as exc_info:
            await verify_ip_whitelist(req, mock_config)
        assert exc_info.value.status_code == 403


# ============================================================
# verify_auth_token
# ============================================================


class TestVerifyAuthToken:
    @pytest.mark.asyncio
    async def test_token_valid(self, mock_config: R4WebhookConfig) -> None:
        await verify_auth_token(TEST_AUTH_TOKEN, mock_config)  # no raise

    @pytest.mark.asyncio
    async def test_token_missing(self, mock_config: R4WebhookConfig) -> None:
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await verify_auth_token(None, mock_config)
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_token_empty_string(self, mock_config: R4WebhookConfig) -> None:
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await verify_auth_token("", mock_config)
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_token_mismatch(self, mock_config: R4WebhookConfig) -> None:
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await verify_auth_token("wrong-token", mock_config)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_no_auth_token_configured(self, clean_config: None) -> None:
        from fastapi import HTTPException

        with patch.dict(
            os.environ, {"R4_WEBHOOK_AUTH_TOKEN": "", "R4_WEBHOOK_ALLOWED_IPS": "1.2.3.4"}
        ):
            reset_webhook_config()
            cfg = get_webhook_config()
            with pytest.raises(HTTPException) as exc_info:
                await verify_auth_token("anything", cfg)
            assert exc_info.value.status_code == 503


# ============================================================
# verify_rate_limit (middleware)
# ============================================================


class TestVerifyRateLimitMiddleware:
    @pytest.mark.asyncio
    async def test_rate_limit_ok(self, mock_config: R4WebhookConfig) -> None:
        _rate_limit_store.clear()
        req = _mock_request(ip=TEST_ALLOWED_IP)
        await verify_rate_limit(req, mock_config)  # no raise

    @pytest.mark.asyncio
    async def test_rate_limit_exceeded_429(self, mock_config: R4WebhookConfig) -> None:
        from fastapi import HTTPException

        _rate_limit_store.clear()
        ip = "10.0.0.50"
        for _ in range(5):
            check_rate_limit(ip, mock_config)
        req = _mock_request(ip=ip)
        with pytest.raises(HTTPException) as exc_info:
            await verify_rate_limit(req, mock_config)
        assert exc_info.value.status_code == 429

    @pytest.mark.asyncio
    async def test_rate_limit_forwarded_for(self, mock_config: R4WebhookConfig) -> None:
        _rate_limit_store.clear()
        req = _mock_request(ip="10.0.0.99")
        req.headers = {"X-Forwarded-For": TEST_ALLOWED_IP}
        await verify_rate_limit(req, mock_config)  # no raise


# ============================================================
# detect_webhook_format
# ============================================================


class TestDetectWebhookFormat:
    def test_mbconsulta_detected(self) -> None:
        payload = {"TelefonoEmisor": "04145555555", "BancoEmisor": "0134", "Monto": "150.00"}
        assert detect_webhook_format(payload) == "MBconsulta"

    def test_r4consulta_detected(self) -> None:
        payload = {"IdCliente": "12345678", "TelefonoComercio": "04129999999", "Monto": "10.00"}
        assert detect_webhook_format(payload) == "R4consulta"

    def test_default_r4consulta(self) -> None:
        payload = {"Monto": "10.00"}
        assert detect_webhook_format(payload) == "R4consulta"


# ============================================================
# Pydantic models
# ============================================================


class TestPydanticModels:
    def test_consulta_request_valid(self) -> None:
        req = R4ConsultaRequest(
            IdCliente="V12345678", Monto="150.00", TelefonoComercio="04125555555"
        )
        assert req.IdCliente == "V12345678"

    def test_consulta_request_monto_invalid(self) -> None:
        with pytest.raises(ValidationError):
            R4ConsultaRequest(IdCliente="V12345678", Monto="abc", TelefonoComercio="04125555555")

    def test_consulta_request_monto_wrong_decimals(self) -> None:
        with pytest.raises(ValidationError):
            R4ConsultaRequest(IdCliente="V12345678", Monto="150.0", TelefonoComercio="04125555555")

    def test_consulta_request_monto_no_decimals(self) -> None:
        # "150" (sin decimales) → float() pasa pero "." no está en v,
        # así que el validador NO rechaza — el campo pasa.
        # Este test documenta ese comportamiento (aceptado, no exception).
        req = R4ConsultaRequest(IdCliente="V12345678", Monto="150", TelefonoComercio="04125555555")
        assert req.Monto == "150"

    def test_notifica_request_valid(self) -> None:
        req = R4NotificaRequest(
            IdComercio="13536734",
            TelefonoComercio="04125555555",
            TelefonoEmisor="04145555555",
            Concepto="PAGO",
            BancoEmisor="0134",
            Monto="150.00",
            FechaHora="2024-12-05T16:50:48Z",
            Referencia="83736278",
            CodigoRed="00",
        )
        assert req.Referencia == "83736278"

    def test_notifica_request_codigo_red_invalid(self) -> None:
        with pytest.raises(ValidationError):
            R4NotificaRequest(
                IdComercio="13536734",
                TelefonoComercio="04125555555",
                TelefonoEmisor="04145555555",
                Concepto="PAGO",
                BancoEmisor="0134",
                Monto="150.00",
                FechaHora="2024-12-05T16:50:48Z",
                Referencia="83736278",
                CodigoRed="AB",
            )

    def test_notifica_request_codigo_red_non_digit(self) -> None:
        with pytest.raises(ValidationError):
            R4NotificaRequest(
                IdComercio="13536734",
                TelefonoComercio="04125555555",
                TelefonoEmisor="04145555555",
                Concepto="PAGO",
                BancoEmisor="0134",
                Monto="150.00",
                FechaHora="2024-12-05T16:50:48Z",
                Referencia="83736278",
                CodigoRed="0A",
            )

    def test_notifica_request_monto_invalid(self) -> None:
        with pytest.raises(ValidationError):
            R4NotificaRequest(
                IdComercio="13536734",
                TelefonoComercio="04125555555",
                TelefonoEmisor="04145555555",
                Concepto="PAGO",
                BancoEmisor="0134",
                Monto="xyz",
                FechaHora="2024-12-05T16:50:48Z",
                Referencia="83736278",
                CodigoRed="00",
            )

    def test_consulta_response(self) -> None:
        resp = R4ConsultaResponse(status=True)
        assert resp.status is True

    def test_notifica_response(self) -> None:
        resp = R4NotificaResponse(abono=False)
        assert resp.abono is False

    def test_mbconsulta_response(self) -> None:
        resp = MBConsultaResponse(abono=True)
        assert resp.abono is True


# ============================================================
# WebhookProcessResult
# ============================================================


class TestWebhookProcessResult:
    def test_to_consulta_response(self) -> None:
        result = WebhookProcessResult(success=True, code="00", message="ok")
        resp = result.to_consulta_response()
        assert resp.status is True

    def test_to_notifica_response(self) -> None:
        result = WebhookProcessResult(success=False, code="99", message="fail")
        resp = result.to_notifica_response()
        assert resp.abono is False

    def test_with_data(self) -> None:
        result = WebhookProcessResult(
            success=True,
            code="00",
            message="ok",
            reference="ref123",
            data={"key": "value"},
        )
        assert result.data == {"key": "value"}
        assert result.reference == "ref123"


# ============================================================
# process_r4consulta
# ============================================================


class TestProcessR4Consulta:
    @pytest.mark.asyncio
    async def test_consulta_with_pedidos(self, mock_config: R4WebhookConfig) -> None:
        payload = R4ConsultaRequest(
            IdCliente="V12345678", Monto="150.00", TelefonoComercio="04125555555"
        )
        mock_pedido = MagicMock()
        mock_pedido.id = 42
        with patch(
            "src.financial.database.buscar_pedidos_por_telefono_monto", return_value=[mock_pedido]
        ):
            result = await process_r4consulta(payload, mock_config)
        assert result.success is True
        assert result.code == "00"

    @pytest.mark.asyncio
    async def test_consulta_without_pedidos(self, mock_config: R4WebhookConfig) -> None:
        payload = R4ConsultaRequest(
            IdCliente="V99999999", Monto="999.99", TelefonoComercio="04125555555"
        )
        with patch("src.financial.database.buscar_pedidos_por_telefono_monto", return_value=[]):
            result = await process_r4consulta(payload, mock_config)
        assert result.success is True
        assert result.code == "00"

    @pytest.mark.asyncio
    async def test_consulta_error_graceful(self, mock_config: R4WebhookConfig) -> None:
        payload = R4ConsultaRequest(
            IdCliente="V12345678", Monto="150.00", TelefonoComercio="04125555555"
        )
        with patch(
            "src.financial.database.buscar_pedidos_por_telefono_monto",
            side_effect=Exception("DB error"),
        ):
            result = await process_r4consulta(payload, mock_config)
        assert result.success is True  # graceful: acepta aunque falle
        assert result.code == "00"

    @pytest.mark.asyncio
    async def test_consulta_normalize_ve_prefix(self, mock_config: R4WebhookConfig) -> None:
        payload = R4ConsultaRequest(
            IdCliente="E12345678", Monto="150.00", TelefonoComercio="04125555555"
        )
        with patch(
            "src.financial.database.buscar_pedidos_por_telefono_monto", return_value=[]
        ) as mock_fn:
            await process_r4consulta(payload, mock_config)
            # Verificar que se normalizó el prefijo E
            call_args = mock_fn.call_args
            assert call_args.kwargs["telefono_emisor"] == "12345678"


# ============================================================
# process_r4notifica
# ============================================================


class TestProcessR4Notifica:
    @pytest.mark.asyncio
    async def test_notifica_codigo_red_not_00(self, mock_config: R4WebhookConfig) -> None:
        payload = R4NotificaRequest(
            IdComercio="13536734",
            TelefonoComercio="04125555555",
            TelefonoEmisor="04145555555",
            Concepto="PAGO",
            BancoEmisor="0134",
            Monto="150.00",
            FechaHora="2024-12-05T16:50:48Z",
            Referencia="83736278",
            CodigoRed="99",
        )
        result = await process_r4notifica(payload, mock_config)
        assert result.success is False
        assert result.code == "99"

    @pytest.mark.asyncio
    async def test_notifica_no_pedido_found(self, mock_config: R4WebhookConfig) -> None:
        payload = R4NotificaRequest(
            IdComercio="13536734",
            TelefonoComercio="04125555555",
            TelefonoEmisor="04145555555",
            Concepto="PAGO",
            BancoEmisor="0134",
            Monto="150.00",
            FechaHora="2024-12-05T16:50:48Z",
            Referencia="83736278",
            CodigoRed="00",
        )
        with patch("src.financial.database.buscar_pedidos_por_telefono_monto", return_value=[]):
            result = await process_r4notifica(payload, mock_config)
        assert result.success is True
        assert "NO_ORDER" in result.message

    @pytest.mark.asyncio
    async def test_notifica_internal_error(self, mock_config: R4WebhookConfig) -> None:
        payload = R4NotificaRequest(
            IdComercio="13536734",
            TelefonoComercio="04125555555",
            TelefonoEmisor="04145555555",
            Concepto="PAGO",
            BancoEmisor="0134",
            Monto="150.00",
            FechaHora="2024-12-05T16:50:48Z",
            Referencia="83736278",
            CodigoRed="00",
        )
        with patch(
            "src.financial.database.buscar_pedidos_por_telefono_monto",
            side_effect=Exception("DB error"),
        ):
            result = await process_r4notifica(payload, mock_config)
        assert result.success is True  # graceful al banco
        assert result.code == "INTERNAL_ERROR"


# ============================================================
# process_mbconsulta
# ============================================================


class TestProcessMBConsulta:
    @pytest.mark.asyncio
    async def test_mbconsulta_mapping_to_notifica(self, mock_config: R4WebhookConfig) -> None:
        payload = {
            "IdComercio": "13536734",
            "TelefonoComercio": "04125555555",
            "TelefonoEmisor": "04145555555",
            "Concepto": "PAGO",
            "BancoEmisor": "0134",
            "Monto": "150.00",
            "FechaHora": "2024-12-05T16:50:48Z",
            "Referencia": "83736278",
            "CodigoRed": "00",
        }
        with patch("src.financial.database.buscar_pedidos_por_telefono_monto", return_value=[]):
            result = await process_mbconsulta(payload, mock_config)
        assert result.success is True

    @pytest.mark.asyncio
    async def test_mbconsulta_fallback_partial(self, mock_config: R4WebhookConfig) -> None:
        payload = {
            "TelefonoEmisor": "04145555555",
            "BancoEmisor": "0134",
            "Monto": "150.00",
            "Referencia": "83736278",
        }
        with patch(
            "src.integrations.r4.webhooks.R4NotificaRequest",
            side_effect=Exception("missing fields"),
        ):
            result = await process_mbconsulta(payload, mock_config)
        assert result.success is True
        assert result.code == "00"


# ============================================================
# HMAC auth tests
# ============================================================


class TestHMACBuildSignString:
    def test_build_sign_string_r4bcv(self) -> None:
        payload = {"Fechavalor": "2024-07-23", "Moneda": "USD"}
        result = build_sign_string(payload, R4Endpoint.R4BCV)
        assert result == "2024-07-23USD"

    def test_build_sign_string_r4consulta(self) -> None:
        payload = {"IdCliente": "123", "Monto": "50.00", "TelefonoComercio": "0412"}
        result = build_sign_string(payload, R4Endpoint.R4CONSULTA)
        assert result == "12350.000412"

    def test_build_sign_string_r4notifica(self) -> None:
        payload = {
            "IdComercio": "1",
            "TelefonoComercio": "2",
            "TelefonoEmisor": "3",
            "Concepto": "4",
            "BancoEmisor": "5",
            "Monto": "6",
            "FechaHora": "7",
            "Referencia": "8",
            "CodigoRed": "00",
        }
        result = build_sign_string(payload, R4Endpoint.R4NOTIFICA)
        assert result == "1234567800"

    def test_build_sign_string_missing_field(self) -> None:
        payload = {"Fechavalor": "2024-07-23"}  # missing Moneda
        with pytest.raises(KeyError):
            build_sign_string(payload, R4Endpoint.R4BCV)

    def test_build_sign_string_invalid_endpoint(self) -> None:
        payload = {"test": "1"}
        with pytest.raises(ValueError):
            build_sign_string(payload, "INVALID_ENDPOINT")  # type: ignore[arg-type]

    def test_build_sign_string_int_values(self) -> None:
        payload = {"IdCliente": 123, "Monto": 50.0, "TelefonoComercio": "0412"}
        result = build_sign_string(payload, R4Endpoint.R4CONSULTA)
        assert "123" in result and "50.0" in result


class TestHMACCompute:
    def test_compute_hmac_sha256(self) -> None:
        result = compute_hmac_sha256("test_string", "secret_key")
        expected = hmac.new(b"secret_key", b"test_string", hashlib.sha256).hexdigest().upper()
        assert result == expected

    def test_compute_hmac_empty_string(self) -> None:
        result = compute_hmac_sha256("", "secret")
        assert isinstance(result, str)
        assert len(result) == 64

    def test_compute_hmac_no_secret(self) -> None:
        with pytest.raises(ValueError):
            compute_hmac_sha256("test", "")

    def test_compute_hmac_different_secrets_different_output(self) -> None:
        r1 = compute_hmac_sha256("test", "secret1")
        r2 = compute_hmac_sha256("test", "secret2")
        assert r1 != r2


class TestHMACVerifySignature:
    def test_verify_signature_valid(self) -> None:
        payload = {"Fechavalor": "2024-07-23", "Moneda": "USD"}
        sign_str = build_sign_string(payload, R4Endpoint.R4BCV)
        expected = compute_hmac_sha256(sign_str, "my_secret")
        assert verify_hmac_signature(payload, R4Endpoint.R4BCV, expected, "my_secret") is True

    def test_verify_signature_invalid(self) -> None:
        payload = {"Fechavalor": "2024-07-23", "Moneda": "USD"}
        assert verify_hmac_signature(payload, R4Endpoint.R4BCV, "WRONG", "my_secret") is False

    def test_verify_signature_missing_field(self) -> None:
        payload = {"Fechavalor": "2024-07-23"}  # missing Moneda
        assert verify_hmac_signature(payload, R4Endpoint.R4BCV, "anything", "secret") is False

    def test_verify_signature_lowercase_input(self) -> None:
        payload = {"Fechavalor": "2024-07-23", "Moneda": "USD"}
        sign_str = build_sign_string(payload, R4Endpoint.R4BCV)
        expected = compute_hmac_sha256(sign_str, "my_secret")
        # verify normalizes to uppercase
        assert (
            verify_hmac_signature(payload, R4Endpoint.R4BCV, expected.lower(), "my_secret") is True
        )


class TestHMACBuildAuthHeaders:
    def test_build_auth_headers_with_commerce_id(self) -> None:
        payload = {"Fechavalor": "2024-07-23", "Moneda": "USD"}
        headers = build_auth_headers(payload, R4Endpoint.R4BCV, "secret", "commerce_id")
        assert "Authorization" in headers
        assert headers["Commerce"] == "commerce_id"
        assert headers["Content-Type"] == "application/json"

    def test_build_auth_headers_without_commerce_id(self) -> None:
        payload = {"Fechavalor": "2024-07-23", "Moneda": "USD"}
        headers = build_auth_headers(payload, R4Endpoint.R4BCV, "secret")
        assert headers["Commerce"] == "secret"  # fallback to secret


class TestHMACGetDescription:
    def test_get_description_valid(self) -> None:
        desc = get_sign_string_description(R4Endpoint.R4BCV)
        assert "Fechavalor" in desc

    def test_get_description_invalid_endpoint(self) -> None:
        # Non-existent endpoint returns "no tiene patrón" message
        fake = MagicMock()
        fake.value = "FAKE"
        desc = get_sign_string_description(fake)
        assert "no tiene patrón" in desc


class TestHMACConvenienceFunctions:
    def test_sign_r4bcv(self) -> None:
        payload = {"Fechavalor": "2024-07-23", "Moneda": "USD"}
        headers = __import__("src.integrations.r4.hmac_auth", fromlist=["sign_r4bcv"]).sign_r4bcv(
            payload, "secret", "id"
        )
        assert "Authorization" in headers

    def test_sign_r4consulta(self) -> None:
        payload = {"IdCliente": "1", "Monto": "10.00", "TelefonoComercio": "0412"}
        from src.integrations.r4.hmac_auth import sign_r4consulta

        headers = sign_r4consulta(payload, "secret", "id")
        assert "Authorization" in headers

    def test_sign_r4notifica(self) -> None:
        payload = {
            "IdComercio": "1",
            "TelefonoComercio": "2",
            "TelefonoEmisor": "3",
            "Concepto": "4",
            "BancoEmisor": "5",
            "Monto": "6",
            "FechaHora": "7",
            "Referencia": "8",
            "CodigoRed": "00",
        }
        from src.integrations.r4.hmac_auth import sign_r4notifica

        headers = sign_r4notifica(payload, "secret", "id")
        assert "Authorization" in headers

    def test_sign_r4vuelto(self) -> None:
        payload = {"TelefonoDestino": "1", "Monto": "10.00", "Banco": "2", "Cedula": "3"}
        from src.integrations.r4.hmac_auth import sign_r4vuelto

        headers = sign_r4vuelto(payload, "secret")
        assert "Authorization" in headers

    def test_sign_generar_otp(self) -> None:
        payload = {"Banco": "1", "Monto": "10.00", "Telefono": "2", "Cedula": "3"}
        from src.integrations.r4.hmac_auth import sign_generar_otp

        headers = sign_generar_otp(payload, "secret")
        assert "Authorization" in headers

    def test_sign_debito_inmediato(self) -> None:
        payload = {"Banco": "1", "Cedula": "2", "Telefono": "3", "Monto": "10.00", "OTP": "4"}
        from src.integrations.r4.hmac_auth import sign_debito_inmediato

        headers = sign_debito_inmediato(payload, "secret")
        assert "Authorization" in headers

    def test_sign_credito_inmediato(self) -> None:
        payload = {"Banco": "1", "Cedula": "2", "Telefono": "3", "Monto": "10.00"}
        from src.integrations.r4.hmac_auth import sign_credito_inmediato

        headers = sign_credito_inmediato(payload, "secret")
        assert "Authorization" in headers

    def test_sign_ci_cuentas(self) -> None:
        payload = {"Cedula": "1", "Cuenta": "2", "Monto": "10.00"}
        from src.integrations.r4.hmac_auth import sign_ci_cuentas

        headers = sign_ci_cuentas(payload, "secret")
        assert "Authorization" in headers

    def test_sign_domiciliacion_cnta(self) -> None:
        payload = {"cuenta": "12345"}
        from src.integrations.r4.hmac_auth import sign_domiciliacion_cnta

        headers = sign_domiciliacion_cnta(payload, "secret")
        assert "Authorization" in headers

    def test_sign_domiciliacion_cele(self) -> None:
        payload = {"telefono": "04125555555"}
        from src.integrations.r4.hmac_auth import sign_domiciliacion_cele

        headers = sign_domiciliacion_cele(payload, "secret")
        assert "Authorization" in headers

    def test_sign_consultar_operaciones(self) -> None:
        payload = {"Id": "123"}
        from src.integrations.r4.hmac_auth import sign_consultar_operaciones

        headers = sign_consultar_operaciones(payload, "secret")
        assert "Authorization" in headers

    def test_sign_r4c2p(self) -> None:
        payload = {"TelefonoDestino": "1", "Monto": "10.00", "Banco": "2", "Cedula": "3"}
        from src.integrations.r4.hmac_auth import sign_r4c2p

        headers = sign_r4c2p(payload, "secret")
        assert "Authorization" in headers

    def test_sign_r4anulacion_c2p(self) -> None:
        payload = {"Banco": "1"}
        from src.integrations.r4.hmac_auth import sign_r4anulacion_c2p

        headers = sign_r4anulacion_c2p(payload, "secret")
        assert "Authorization" in headers

    def test_hmac_main_block_executes(self) -> None:
        """Cubre el bloque __main__ de hmac_auth.py ejecutándolo como subprocess."""
        import subprocess
        import sys

        env = os.environ.copy()
        env["R4_COMMERCE_SECRET"] = "test_secret"
        env["R4_COMMERCE_ID"] = "test_id"
        result = subprocess.run(
            [sys.executable, "src/integrations/r4/hmac_auth.py"],
            capture_output=True,
            text=True,
            timeout=10,
            env=env,
            cwd="/mnt/ssd_trabajo/hermes-agent",
        )
        assert result.returncode == 0
        assert "HMAC Patterns R4 Conecta V3.0" in result.stdout
        assert "Verify OK: True" in result.stdout


# ============================================================
# Router / FastAPI integration
# ============================================================


class TestRouter:
    def test_router_prefix(self) -> None:
        assert router.prefix == "/webhook/r4"

    def test_router_has_consulta(self) -> None:
        paths = [r.path for r in router.routes]
        assert any("/consulta" in p for p in paths)

    def test_router_has_notifica(self) -> None:
        paths = [r.path for r in router.routes]
        assert any("/notifica" in p for p in paths)

    def test_router_has_health(self) -> None:
        paths = [r.path for r in router.routes]
        assert any("/health" in p for p in paths)

    def test_include_r4_webhooks(self) -> None:
        app = MagicMock()
        include_r4_webhooks(app)
        app.include_router.assert_called_once_with(router)


# ============================================================
# security_dependency (chained verification)
# ============================================================


class TestSecurityDependency:
    @pytest.mark.asyncio
    async def test_security_dependency_ok(self, mock_config: R4WebhookConfig) -> None:
        from src.integrations.r4.webhooks import security_dependency

        req = _mock_request(ip=TEST_ALLOWED_IP)
        req.headers = {}
        with (
            patch("src.integrations.r4.webhooks.verify_ip_whitelist", new_callable=AsyncMock),
            patch("src.integrations.r4.webhooks.verify_rate_limit", new_callable=AsyncMock),
            patch("src.integrations.r4.webhooks.verify_auth_token", new_callable=AsyncMock),
            patch("src.integrations.r4.webhooks.get_webhook_config", return_value=mock_config),
        ):
            result = await security_dependency(req, TEST_AUTH_TOKEN)
            assert result == mock_config

    @pytest.mark.asyncio
    async def test_security_dependency_ip_fail(self, mock_config: R4WebhookConfig) -> None:
        from fastapi import HTTPException

        from src.integrations.r4.webhooks import security_dependency

        req = _mock_request(ip="bad_ip")
        with (
            patch(
                "src.integrations.r4.webhooks.verify_ip_whitelist",
                new_callable=AsyncMock,
                side_effect=HTTPException(status_code=403, detail="IP no"),
            ),
            patch("src.integrations.r4.webhooks.get_webhook_config", return_value=mock_config),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await security_dependency(req, TEST_AUTH_TOKEN)
            assert exc_info.value.status_code == 403


# ============================================================
# FastAPI endpoint integration (httpx ASGI transport)
# ============================================================


class TestFastAPIEndpoints:
    """Test the actual FastAPI router endpoints with httpx."""

    @pytest.mark.asyncio
    async def test_consulta_endpoint_success(self, mock_config: R4WebhookConfig) -> None:
        import httpx
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(router)

        with (
            patch(
                "src.integrations.r4.webhooks.verify_ip_whitelist",
                new_callable=AsyncMock,
            ),
            patch(
                "src.integrations.r4.webhooks.verify_rate_limit",
                new_callable=AsyncMock,
            ),
            patch(
                "src.integrations.r4.webhooks.verify_auth_token",
                new_callable=AsyncMock,
            ),
            patch(
                "src.integrations.r4.webhooks.process_r4consulta",
                new_callable=AsyncMock,
                return_value=WebhookProcessResult(
                    success=True, code="00", message="ok", reference="ref1"
                ),
            ),
        ):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                resp = await client.post(
                    "/webhook/r4/consulta",
                    json={
                        "IdCliente": "V12345678",
                        "Monto": "150.00",
                        "TelefonoComercio": "04125555555",
                    },
                    headers={"authorization": TEST_AUTH_TOKEN},
                )
            assert resp.status_code == 200
            assert resp.json() == {"status": True}

    @pytest.mark.asyncio
    async def test_consulta_endpoint_invalid_json(self, mock_config: R4WebhookConfig) -> None:
        import httpx
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(router)

        with (
            patch(
                "src.integrations.r4.webhooks.verify_ip_whitelist",
                new_callable=AsyncMock,
            ),
            patch(
                "src.integrations.r4.webhooks.verify_rate_limit",
                new_callable=AsyncMock,
            ),
            patch(
                "src.integrations.r4.webhooks.verify_auth_token",
                new_callable=AsyncMock,
            ),
        ):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                resp = await client.post(
                    "/webhook/r4/consulta",
                    content=b"not json",
                    headers={"authorization": TEST_AUTH_TOKEN},
                )
            assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_consulta_endpoint_mbconsulta_format(self, mock_config: R4WebhookConfig) -> None:
        import httpx
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(router)

        with (
            patch(
                "src.integrations.r4.webhooks.verify_ip_whitelist",
                new_callable=AsyncMock,
            ),
            patch(
                "src.integrations.r4.webhooks.verify_rate_limit",
                new_callable=AsyncMock,
            ),
            patch(
                "src.integrations.r4.webhooks.verify_auth_token",
                new_callable=AsyncMock,
            ),
            patch(
                "src.integrations.r4.webhooks.process_mbconsulta",
                new_callable=AsyncMock,
                return_value=WebhookProcessResult(success=True, code="00", message="mb ok"),
            ),
        ):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                resp = await client.post(
                    "/webhook/r4/consulta",
                    json={
                        "TelefonoEmisor": "04145555555",
                        "BancoEmisor": "0134",
                        "Monto": "150.00",
                        "Referencia": "83736278",
                    },
                    headers={"authorization": TEST_AUTH_TOKEN},
                )
            assert resp.status_code == 200
            assert resp.json() == {"abono": True}

    @pytest.mark.asyncio
    async def test_notifica_endpoint_success(self, mock_config: R4WebhookConfig) -> None:
        import httpx
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(router)

        with (
            patch(
                "src.integrations.r4.webhooks.verify_ip_whitelist",
                new_callable=AsyncMock,
            ),
            patch(
                "src.integrations.r4.webhooks.verify_rate_limit",
                new_callable=AsyncMock,
            ),
            patch(
                "src.integrations.r4.webhooks.verify_auth_token",
                new_callable=AsyncMock,
            ),
            patch(
                "src.integrations.r4.webhooks.process_r4notifica",
                new_callable=AsyncMock,
                return_value=WebhookProcessResult(
                    success=True, code="00", message="ok", reference="ref1"
                ),
            ),
        ):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                resp = await client.post(
                    "/webhook/r4/notifica",
                    json={
                        "IdComercio": "13536734",
                        "TelefonoComercio": "04125555555",
                        "TelefonoEmisor": "04145555555",
                        "Concepto": "PAGO",
                        "BancoEmisor": "0134",
                        "Monto": "150.00",
                        "FechaHora": "2024-12-05T16:50:48Z",
                        "Referencia": "83736278",
                        "CodigoRed": "00",
                    },
                    headers={"authorization": TEST_AUTH_TOKEN},
                )
            assert resp.status_code == 200
            assert resp.json() == {"abono": True}

    @pytest.mark.asyncio
    async def test_notifica_endpoint_invalid_payload(self, mock_config: R4WebhookConfig) -> None:
        import httpx
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(router)

        with (
            patch(
                "src.integrations.r4.webhooks.verify_ip_whitelist",
                new_callable=AsyncMock,
            ),
            patch(
                "src.integrations.r4.webhooks.verify_rate_limit",
                new_callable=AsyncMock,
            ),
            patch(
                "src.integrations.r4.webhooks.verify_auth_token",
                new_callable=AsyncMock,
            ),
        ):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                resp = await client.post(
                    "/webhook/r4/notifica",
                    json={"invalid": "payload"},
                    headers={"authorization": TEST_AUTH_TOKEN},
                )
            assert resp.status_code == 200
            assert resp.json() == {"abono": False}

    @pytest.mark.asyncio
    async def test_health_endpoint(self, mock_config: R4WebhookConfig) -> None:
        import httpx
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(router)

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.get("/webhook/r4/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "endpoints" in data


# ============================================================
# Logging functions
# ============================================================


class TestLoggingFunctions:
    def test_log_full_request(self) -> None:
        req = MagicMock()
        req.client = MagicMock()
        req.client.host = "1.2.3.4"
        req.headers = {"content-type": "application/json", "authorization": "a" * 30}
        req.method = "POST"
        req.url = "http://test/webhook"
        _log_full_request(req, {"key": "value"}, "test_endpoint")

    def test_log_full_request_no_auth(self) -> None:
        req = MagicMock()
        req.client = MagicMock()
        req.client.host = "1.2.3.4"
        req.headers = {}
        req.method = "POST"
        req.url = "http://test/webhook"
        _log_full_request(req, "string_body", "test_endpoint")

    def test_log_full_request_no_client(self) -> None:
        req = MagicMock()
        req.client = None
        req.headers = {}
        req.method = "POST"
        req.url = "http://test/webhook"
        _log_full_request(req, {}, "test_endpoint")

    def test_log_hmac_failure(self) -> None:
        req = MagicMock()
        req.client = MagicMock()
        req.client.host = "1.2.3.4"
        req.headers = {"Authorization": "short"}
        _log_hmac_failure(req, {"data": "test"}, "test_endpoint")

    def test_log_hmac_failure_with_sign_string(self) -> None:
        req = MagicMock()
        req.client = MagicMock()
        req.client.host = "1.2.3.4"
        req.headers = {"Authorization": "a" * 50}
        _log_hmac_failure(
            req,
            {"data": "test"},
            "test_endpoint",
            sign_string="test_sign",
            expected_hash="expected123",
            received_hash="received456",
        )


# ============================================================
# process_r4notifica — full flow with mocked dependencies
# ============================================================


class TestProcessR4NotificaFull:
    @pytest.mark.asyncio
    async def test_notifica_success_with_pedido(self, mock_config: R4WebhookConfig) -> None:
        """Cubre el flujo completo de process_r4notifica con pedido encontrado."""
        payload = R4NotificaRequest(
            IdComercio="13536734",
            TelefonoComercio="04125555555",
            TelefonoEmisor="04145555555",
            Concepto="PAGO",
            BancoEmisor="0134",
            Monto="150.00",
            FechaHora="2024-12-05T16:50:48Z",
            Referencia="83736278",
            CodigoRed="00",
        )

        mock_pedido = MagicMock()
        mock_pedido.id = 42
        mock_pedido.pedido_id = 100
        mock_pedido.cliente_telefono = "04145555555"
        mock_pedido.monto_total_eur = 15.0

        with (
            patch(
                "src.financial.database.buscar_pedidos_por_telefono_monto",
                return_value=[mock_pedido],
            ),
            patch(
                "src.financial.database.seleccionar_mejor_match",
                return_value=mock_pedido,
            ),
            patch(
                "src.financial.verificacion.verificar_pago_manual",
                new_callable=AsyncMock,
                return_value={"success": True, "nuevo_estado": "pagado"},
            ),
            patch(
                "src.financial.currency.get_eur_ves_rate",
                new_callable=AsyncMock,
                return_value=100.0,
            ),
            patch(
                "src.integrations.odoo.odoo_sync.OdooClient",
            ) as mock_odoo_cls,
            patch(
                "api.bridge._send_whatsapp_message",
                new_callable=AsyncMock,
                return_value=True,
            ),
        ):
            mock_odoo_instance = MagicMock()
            mock_odoo_instance.connect.return_value = False
            mock_odoo_cls.return_value = mock_odoo_instance

            result = await process_r4notifica(payload, mock_config)

        assert result.success is True
        assert result.code == "00"
        assert result.reference == "83736278"

    @pytest.mark.asyncio
    async def test_notifica_ambiguous_match(self, mock_config: R4WebhookConfig) -> None:
        """Cubre el caso AMBIGUOUS_MATCH: múltiples pedidos, sin match único."""
        payload = R4NotificaRequest(
            IdComercio="13536734",
            TelefonoComercio="04125555555",
            TelefonoEmisor="04145555555",
            Concepto="PAGO",
            BancoEmisor="0134",
            Monto="150.00",
            FechaHora="2024-12-05T16:50:48Z",
            Referencia="83736278",
            CodigoRed="00",
        )

        mock_pedido1 = MagicMock()
        mock_pedido1.id = 42
        mock_pedido2 = MagicMock()
        mock_pedido2.id = 43

        with (
            patch(
                "src.financial.database.buscar_pedidos_por_telefono_monto",
                return_value=[mock_pedido1, mock_pedido2],
            ),
            patch(
                "src.financial.database.seleccionar_mejor_match",
                return_value=None,
            ),
        ):
            result = await process_r4notifica(payload, mock_config)

        assert result.success is True
        assert "AMBIGUOUS" in result.message

    @pytest.mark.asyncio
    async def test_notifica_verify_failed(self, mock_config: R4WebhookConfig) -> None:
        """Cubre el caso donde verificar_pago_manual falla."""
        payload = R4NotificaRequest(
            IdComercio="13536734",
            TelefonoComercio="04125555555",
            TelefonoEmisor="04145555555",
            Concepto="PAGO",
            BancoEmisor="0134",
            Monto="150.00",
            FechaHora="2024-12-05T16:50:48Z",
            Referencia="83736278",
            CodigoRed="00",
        )

        mock_pedido = MagicMock()
        mock_pedido.id = 42
        mock_pedido.pedido_id = 100
        mock_pedido.cliente_telefono = "04145555555"
        mock_pedido.monto_total_eur = 15.0

        with (
            patch(
                "src.financial.database.buscar_pedidos_por_telefono_monto",
                return_value=[mock_pedido],
            ),
            patch(
                "src.financial.database.seleccionar_mejor_match",
                return_value=mock_pedido,
            ),
            patch(
                "src.financial.verificacion.verificar_pago_manual",
                new_callable=AsyncMock,
                return_value={"success": False, "mensaje": "Ya pagado"},
            ),
            patch(
                "src.financial.currency.get_eur_ves_rate",
                new_callable=AsyncMock,
                return_value=100.0,
            ),
        ):
            result = await process_r4notifica(payload, mock_config)

        assert result.success is False
        assert result.code == "VERIFY_FAILED"

    @pytest.mark.asyncio
    async def test_notifica_with_odoo_sync_success(self, mock_config: R4WebhookConfig) -> None:
        """Cubre el flujo con sync a Odoo exitoso."""
        payload = R4NotificaRequest(
            IdComercio="13536734",
            TelefonoComercio="04125555555",
            TelefonoEmisor="04145555555",
            Concepto="PAGO",
            BancoEmisor="0134",
            Monto="150.00",
            FechaHora="2024-12-05T16:50:48Z",
            Referencia="83736278",
            CodigoRed="00",
        )

        mock_pedido = MagicMock()
        mock_pedido.id = 42
        mock_pedido.pedido_id = 100
        mock_pedido.cliente_telefono = "4145555555"
        mock_pedido.monto_total_eur = 15.0

        with (
            patch(
                "src.financial.database.buscar_pedidos_por_telefono_monto",
                return_value=[mock_pedido],
            ),
            patch(
                "src.financial.database.seleccionar_mejor_match",
                return_value=mock_pedido,
            ),
            patch(
                "src.financial.verificacion.verificar_pago_manual",
                new_callable=AsyncMock,
                return_value={"success": True, "nuevo_estado": "pagado"},
            ),
            patch(
                "src.financial.currency.get_eur_ves_rate",
                new_callable=AsyncMock,
                return_value=100.0,
            ),
            patch(
                "src.integrations.odoo.odoo_sync.OdooClient",
            ) as mock_odoo_cls,
            patch(
                "api.bridge._send_whatsapp_message",
                new_callable=AsyncMock,
                return_value=True,
            ),
        ):
            mock_odoo_instance = MagicMock()
            mock_odoo_instance.connect.return_value = True
            mock_odoo_instance.execute_kw.return_value = [{"id": 200}]
            mock_odoo_cls.return_value = mock_odoo_instance

            result = await process_r4notifica(payload, mock_config)

        assert result.success is True
        mock_odoo_instance.register_payment.assert_called_once()
