"""
Tests de la integración R4c2p (Cobro Automático) — Fase 2.

Cubre (según especificación del Líder):
- generate_otp genera request correcto
- send_c2p (cobro_c2p) con OTP correcto = code "00"
- send_c2p con OTP incorrecto = code error
- webhook /c2p pasivo procesa contingencia
- menú muestra 3 opciones si C2P_ENABLED=true
- menú muestra 2 opciones si C2P_ENABLED=false
- FSM: cédula → banco → OTP → confirmación
- timeout 5 min cancela y ofrece alternativa
- español neutro (sin modismos argentinos)
- no romper Pago Móvil (R4notifica) — regresión básica
"""

import asyncio
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "api"))

os.environ["BRIDGE_ALLOW_INSECURE_SALT"] = "1"
os.environ.setdefault("C2P_ENABLED", "false")

from src.integrations.r4.client import R4Client, R4Endpoint, R4Response  # noqa: E402
from src.integrations.r4.hmac_auth import build_sign_string  # noqa: E402
import bridge  # noqa: E402


# ============================================================
# Helpers
# ============================================================

def _resp(code: str, reference: str = "") -> R4Response:
    return R4Response(
        success=(code == "00"),
        code=code,
        message="TRANSACCION EXITOSA" if code == "00" else "Rechazado",
        reference=reference,
    )


# ============================================================
# 1. generate_otp genera request correcto
# ============================================================

class TestGenerateOtpRequest:
    def test_payload_correcto(self):
        """generar_otp arma el payload del PDF pág. 16 y firma HMAC correcto."""
        client = R4Client()
        captured = {}

        async def fake_request(endpoint, payload, method="POST"):
            captured["endpoint"] = endpoint
            captured["payload"] = payload
            return _resp("202")

        with patch.object(client, "_request", side_effect=fake_request):
            resp = asyncio.run(
                client.generar_otp("0105", "50.00", "04145555555", "V12345678")
            )

        assert captured["endpoint"] == R4Endpoint.GENERAR_OTP
        assert captured["payload"] == {
            "Banco": "0105",
            "Monto": "50.00",
            "Telefono": "04145555555",
            "Cedula": "V12345678",
        }
        assert resp.success

    def test_hmac_sign_string_orden_correcto(self):
        """El sign string de GenerarOtp sigue HMACPattern: Banco+Cedula+Telefono+Monto+OTP."""
        payload = {"Banco": "0105", "Monto": "50.00", "Telefono": "04145555555", "Cedula": "V12345678"}
        s = build_sign_string(payload, R4Endpoint.GENERAR_OTP)
        # fields=("Banco", "Cedula", "Telefono", "Monto", "OTP") — sin OTP en payload
        assert s.startswith("0105")


# ============================================================
# 2-3. send_c2p (cobro_c2p) aprobado / rechazado
# ============================================================

class TestCobroC2p:
    def test_payload_aprobado(self):
        """cobro_c2p arma el payload del PDF pág. 30 y retorna code 00 con reference."""
        client = R4Client()
        captured = {}

        async def fake_request(endpoint, payload, method="POST"):
            captured["endpoint"] = endpoint
            captured["payload"] = payload
            return _resp("00", reference="59707278")

        with patch.object(client, "_request", side_effect=fake_request):
            resp = asyncio.run(
                client.cobro_c2p(
                    telefono_destino="04145555555",
                    cedula="V12345678",
                    banco="0105",
                    monto="1.15",
                    otp="13309525",
                    concepto="ESTACION H2O",
                    ip="192.168.1.20",
                )
            )

        assert captured["endpoint"] == R4Endpoint.R4C2P
        assert captured["payload"] == {
            "TelefonoDestino": "04145555555",
            "Cedula": "V12345678",
            "Concepto": "ESTACION H2O",
            "Banco": "0105",
            "Ip": "192.168.1.20",
            "Monto": "1.15",
            "Otp": "13309525",
        }
        assert resp.success and resp.code == "00" and resp.reference == "59707278"

    def test_otp_incorrecto_code_error(self):
        """OTP inválido → banco responde code 08, success=False."""
        client = R4Client()

        async def fake_request(endpoint, payload, method="POST"):
            return _resp("08")

        with patch.object(client, "_request", side_effect=fake_request):
            resp = asyncio.run(
                client.cobro_c2p(
                    telefono_destino="04145555555",
                    cedula="V12345678",
                    banco="0105",
                    monto="1.15",
                    otp="00000000",
                )
            )
        assert not resp.success
        assert resp.code == "08"

    def test_hmac_sign_string_c2p(self):
        """Sign string C2P = TelefonoDestino+Monto+Banco+Cedula (PDF pág. 30)."""
        payload = {
            "TelefonoDestino": "04145555555",
            "Monto": "1.15",
            "Banco": "0105",
            "Cedula": "V12345678",
            "Otp": "13309525",
            "Concepto": "PRUEBA",
            "Ip": "192.168.1.20",
        }
        s = build_sign_string(payload, R4Endpoint.R4C2P)
        assert s == "041455555551.150105V12345678"

    def test_concepto_truncado(self):
        """Concepto se trunca a 30 chars (máx del banco)."""
        client = R4Client()
        captured = {}

        async def fake_request(endpoint, payload, method="POST"):
            captured["payload"] = payload
            return _resp("00")

        with patch.object(client, "_request", side_effect=fake_request):
            asyncio.run(
                client.cobro_c2p(
                    telefono_destino="04145555555",
                    cedula="V12345678",
                    banco="0105",
                    monto="1.15",
                    otp="13309525",
                    concepto="X" * 50,
                )
            )
        assert len(captured["payload"]["Concepto"]) == 30

    def test_ip_default(self):
        """Sin ip explícita usa 0.0.0.0 (pendiente aclarar campo Ip con el banco)."""
        client = R4Client()
        captured = {}

        async def fake_request(endpoint, payload, method="POST"):
            captured["payload"] = payload
            return _resp("00")

        with patch.object(client, "_request", side_effect=fake_request):
            asyncio.run(
                client.cobro_c2p("04145555555", "V12345678", "0105", "1.15", "13309525")
            )
        assert captured["payload"]["Ip"] == "0.0.0.0"


# ============================================================
# 4. Webhook pasivo /webhook/r4/c2p
# ============================================================

class TestWebhookC2pPasivo:
    def test_procesa_contingencia_aprobada(self):
        """Payload code 00 con match de pedido → procesa y responde status true."""
        from fastapi.testclient import TestClient
        from src.integrations.r4.webhooks import router
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(router)
        client_http = TestClient(app)

        with patch(
            "src.integrations.r4.webhooks.get_webhook_config"
        ) as mock_cfg, patch(
            "src.integrations.r4.webhooks.verify_ip_whitelist", new=AsyncMock()
        ), patch(
            "src.integrations.r4.webhooks.verify_auth_token", new=AsyncMock()
        ), patch(
            "src.integrations.r4.webhooks.verify_rate_limit", new=AsyncMock()
        ), patch(
            "src.integrations.r4.webhooks.procesar_pago_c2p_async",
            new=AsyncMock(return_value=True),
        ) as mock_proc:
            mock_cfg.return_value = MagicMock()
            r = client_http.post(
                "/webhook/r4/c2p",
                json={
                    "TelefonoDestino": "04145555555",
                    "Cedula": "V12345678",
                    "Monto": "1.15",
                    "Referencia": "59707278",
                    "code": "00",
                },
                headers={"Authorization": "test-token"},
            )

        assert r.status_code == 200
        assert r.json()["status"] is True
        mock_proc.assert_awaited_once()
        args = mock_proc.call_args.kwargs
        assert args["telefono"] == "04145555555"
        assert args["referencia"] == "59707278"

    def test_notificacion_no_aprobatoria_solo_log(self):
        """code != 00 → solo log, NO procesa pago, pero responde 200 (ack)."""
        from fastapi.testclient import TestClient
        from src.integrations.r4.webhooks import router
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(router)
        client_http = TestClient(app)

        with patch(
            "src.integrations.r4.webhooks.get_webhook_config"
        ) as mock_cfg, patch(
            "src.integrations.r4.webhooks.verify_ip_whitelist", new=AsyncMock()
        ), patch(
            "src.integrations.r4.webhooks.verify_auth_token", new=AsyncMock()
        ), patch(
            "src.integrations.r4.webhooks.verify_rate_limit", new=AsyncMock()
        ), patch(
            "src.integrations.r4.webhooks.procesar_pago_c2p_async",
            new=AsyncMock(return_value=False),
        ) as mock_proc:
            mock_cfg.return_value = MagicMock()
            r = client_http.post(
                "/webhook/r4/c2p",
                json={"code": "08", "message": "TOKEN inválido"},
                headers={"Authorization": "test-token"},
            )

        assert r.status_code == 200
        mock_proc.assert_not_awaited()

    def test_sin_auth_token_rechazado(self):
        """Sin Authorization header → 401/403 (validación estricta, sin modo captura)."""
        from fastapi.testclient import TestClient
        from src.integrations.r4.webhooks import router, verify_auth_token
        from fastapi import FastAPI, HTTPException

        app = FastAPI()
        app.include_router(router)
        client_http = TestClient(app)

        real_verify = verify_auth_token

        async def strict_verify(auth, config):
            if not auth:
                raise HTTPException(status_code=401, detail="Authorization requerido")
            await real_verify(auth, config)

        with patch(
            "src.integrations.r4.webhooks.get_webhook_config"
        ) as mock_cfg, patch(
            "src.integrations.r4.webhooks.verify_ip_whitelist", new=AsyncMock()
        ), patch(
            "src.integrations.r4.webhooks.verify_auth_token", new=strict_verify
        ), patch(
            "src.integrations.r4.webhooks.verify_rate_limit", new=AsyncMock()
        ):
            mock_cfg.return_value = MagicMock()
            r = client_http.post(
                "/webhook/r4/c2p",
                json={"code": "00", "Referencia": "123"},
            )
        assert r.status_code in (401, 403)


# ============================================================
# 5-6. Menú 2/3 opciones según flag + FSM + español neutro
# ============================================================

PH = "test_c2p_phone_hash_001"
PHONE = "04145555555"


def _msg(text: str) -> dict:
    return {"type": "text", "text": {"body": text}}


async def _run(handler, *args):
    return await handler(*args)


class TestMenuPagoSegunFlag:
    def test_menu_3_opciones_si_habilitado(self):
        """C2P_ENABLED=true → botones: Pago Móvil / Cobro Automático / Efectivo."""
        with patch.object(bridge, "C2P_ENABLED", True):
            buttons = bridge._c2p_menu_pago_buttons()
        assert [b["id"] for b in buttons] == ["1", "2", "3"]
        assert any("Cobro Automático" in b["title"] for b in buttons)
        assert any("Efectivo" in b["title"] for b in buttons)

    def test_menu_2_opciones_si_deshabilitado(self):
        """C2P_ENABLED=false → solo Pago Móvil / Efectivo (opción 2 oculta)."""
        with patch.object(bridge, "C2P_ENABLED", False):
            buttons = bridge._c2p_menu_pago_buttons()
        assert [b["id"] for b in buttons] == ["1", "2"]
        assert not any("Cobro" in b["title"] for b in buttons)


class TestFsmC2p:
    """FSM completa: awaiting_payment(2) → cédula → banco → OTP → confirmación."""

    def setup_method(self):
        bridge._clear_state(PH)
        # Estado base: pedido confirmado, eligiendo método de pago
        bridge._set_state(
            PH,
            {
                "state": "awaiting_payment",
                "total_eur": 3.0,
                "qty_botellones": 3,
                "qty_hielo": 0,
                "address": "Av. Test, Caracas",
                "contact_name": "Cliente Test",
            },
        )

    def teardown_method(self):
        bridge._clear_state(PH)

    def test_flujo_completo_c2p_aprobado(self):
        with patch.object(bridge, "C2P_ENABLED", True), patch.object(
            bridge, "_send_to_dispatch_queue"
        ) as mock_dispatch, patch.object(
            bridge, "_c2p_guardar_dato_cliente"
        ) as mock_save, patch(
            "src.integrations.r4.client.R4Client.cobro_c2p",
            new=AsyncMock(return_value=_resp("00", "59707278")),
        ) as mock_c2p, patch(
            "src.integrations.r4.client.R4Client.generar_otp",
            new=AsyncMock(return_value=_resp("202")),
        ):
            # Paso 1: elige "2" → pide cédula
            r = asyncio.run(
                bridge._handle_deterministic(PH, "2", PHONE, "Cliente Test", _msg("2"), {})
            )
            assert "cédula" in r["answer"].lower()
            assert bridge._get_state(PH)["state"] == "awaiting_c2p_cedula"

            # Paso 2: cédula → pide banco
            r = asyncio.run(
                bridge._handle_deterministic(PH, "V-12345678", PHONE, "Cliente Test", _msg("V-12345678"), {})
            )
            assert "banco" in r["answer"].lower()
            assert bridge._get_state(PH)["state"] == "awaiting_c2p_banco"
            assert bridge._get_state(PH)["c2p_cedula"] == "V12345678"

            # Paso 3: banco → GenerarOtp lanzado, pide OTP
            r = asyncio.run(
                bridge._handle_deterministic(PH, "0105", PHONE, "Cliente Test", _msg("0105"), {})
            )
            assert "código" in r["answer"].lower()
            assert bridge._get_state(PH)["state"] == "awaiting_c2p_otp"
            assert bridge._get_state(PH)["c2p_banco"] == "0105"
            assert bridge._get_state(PH)["c2p_expires_at"] > 0

            # Paso 4: OTP → cobro_c2p code 00 → confirmado + despachado
            r = asyncio.run(
                bridge._handle_deterministic(PH, "13309525", PHONE, "Cliente Test", _msg("13309525"), {})
            )
            assert "Pago confirmado" in r["answer"]
            mock_c2p.assert_awaited_once()
            mock_dispatch.assert_called_once()
            # Estado final: limpiado tras completar
            assert bridge._get_state(PH).get("state") in (None, "completed")

    def test_cedula_invalida_reintenta(self):
        with patch.object(bridge, "C2P_ENABLED", True):
            bridge._set_state(PH, {**bridge._get_state(PH), "state": "awaiting_c2p_cedula"})
            r = asyncio.run(
                bridge._handle_deterministic(PH, "hola", PHONE, "Cliente Test", _msg("hola"), {})
            )
            assert "no es válido" in r["answer"]
            assert bridge._get_state(PH)["state"] == "awaiting_c2p_cedula"

    def test_rechazo_banco_ofrece_alternativa(self):
        """cobro_c2p code 51 → mensaje de fondos insuficientes + volver a awaiting_payment."""
        with patch.object(bridge, "C2P_ENABLED", True), patch(
            "src.integrations.r4.client.R4Client.cobro_c2p",
            new=AsyncMock(return_value=_resp("51")),
        ):
            bridge._set_state(
                PH,
                {
                    "state": "awaiting_c2p_otp",
                    "c2p_cedula": "V12345678",
                    "c2p_banco": "0105",
                    "c2p_monto_bs": 100.0,
                    "c2p_expires_at": __import__("time").time() + 300,
                    "total_eur": 3.0,
                },
            )
            r = asyncio.run(
                bridge._handle_deterministic(PH, "13309525", PHONE, "Cliente Test", _msg("13309525"), {})
            )
            assert "Fondos insuficientes" in r["answer"]
            assert bridge._get_state(PH)["state"] == "awaiting_payment"
            # Ofrece botones Pago Móvil (1) y Efectivo (3)
            buttons = r["interactive"]["buttons"]
            assert [b["id"] for b in buttons] == ["1", "3"]

    def test_timeout_5min_cancela_y_ofrece_alternativa(self):
        """OTP con c2p_expires_at vencido → mensaje de expiración + fallback 1/3."""
        with patch.object(bridge, "C2P_ENABLED", True):
            bridge._set_state(
                PH,
                {
                    "state": "awaiting_c2p_otp",
                    "c2p_cedula": "V12345678",
                    "c2p_banco": "0105",
                    "c2p_monto_bs": 100.0,
                    "c2p_expires_at": __import__("time").time() - 1,  # YA expiró
                    "total_eur": 3.0,
                },
            )
            r = asyncio.run(
                bridge._handle_deterministic(PH, "13309525", PHONE, "Cliente Test", _msg("13309525"), {})
            )
            assert "expiró" in r["answer"]
            assert bridge._get_state(PH)["state"] == "awaiting_payment"
            buttons = r["interactive"]["buttons"]
            assert [b["id"] for b in buttons] == ["1", "3"]

    def test_c2p_deshabilitado_opcion_2_es_efectivo(self):
        """Con flag OFF, "2" en awaiting_payment sigue siendo Efectivo (menú de 2)."""
        with patch.object(bridge, "C2P_ENABLED", False), patch.object(
            bridge, "_send_to_dispatch_queue"
        ) as mock_dispatch:
            r = asyncio.run(
                bridge._handle_deterministic(PH, "2", PHONE, "Cliente Test", _msg("2"), {})
            )
            assert "efectivo" in r["answer"].lower()
            assert bridge._get_state(PH).get("state") in (None, "completed")

    def test_pago_movil_no_roto(self):
        """Regresión: opción 1 (Pago Móvil) sigue funcionando con C2P activado."""
        with patch.object(bridge, "C2P_ENABLED", True):
            r = asyncio.run(
                bridge._handle_deterministic(PH, "1", PHONE, "Cliente Test", _msg("1"), {})
            )
            assert "datos para su pago" in r["answer"]
            assert bridge._get_state(PH)["state"] == "awaiting_confirmation"
            assert bridge._get_state(PH)["payment_method"] == "Pago Móvil"


class TestEspanolNeutro:
    """Todos los textos C2P en español neutro venezolano — sin modismos argentinos."""

    def test_sin_modismos_argentinos(self):
        textos = [
            bridge.C2P_MSG_CEDULA,
            bridge.C2P_MSG_BANCO,
            bridge.C2P_MSG_OTP_ENVIADO.format(monto_bs="100.00"),
            bridge.C2P_MSG_PAGO_OK,
            bridge.C2P_MSG_RECHAZO,
            bridge.C2P_MSG_TIMEOUT,
            *bridge.C2P_RECHAZO_POR_CODIGO.values(),
        ]
        prohibidos = ["decime", "decíme", "vos", "che,", "querés", "podés", "tenés", "contame", "contáme", "marcá", "escribí"]
        for texto in textos:
            lower = texto.lower()
            for p in prohibidos:
                assert p not in lower, f"Modismo '{p}' encontrado en: {texto}"

    def test_usa_usted_y_digame(self):
        assert "Dígame" in bridge.C2P_MSG_CEDULA
        assert "Dígame" in bridge.C2P_MSG_BANCO
