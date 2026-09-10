"""Tests de endpoints HTTP del bridge: /webhook/meta (GET+POST) y seguridad.

Cobertura de DT-12: los endpoints de Meta webhook con firma HMAC válida/inválida,
verify token, payload inválido y kill switch.
"""

import hashlib
import hmac
import json
import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

# El bridge se importa con env vars de test para no tocar producción.
os.environ.setdefault("META_APP_SECRET", "test_secret")
os.environ.setdefault("META_VERIFY_TOKEN", "test_verify_token")


@pytest.fixture(scope="module")
def client():
    # Import tardío: bridge.py lee env vars al importar
    from api.bridge import app

    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def _sign(secret: str, body: bytes) -> str:
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


class TestMetaWebhookGet:
    """GET /webhook/meta — verificación de suscripción (hub.challenge)."""

    def test_verify_token_correcto(self, client):
        r = client.get(
            "/webhook/meta",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": "test_verify_token",
                "hub.challenge": "challenge_abc",
            },
        )
        assert r.status_code == 200
        assert r.text == "challenge_abc"

    def test_verify_token_incorrecto(self, client):
        r = client.get(
            "/webhook/meta",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": "wrong_token",
                "hub.challenge": "challenge_abc",
            },
        )
        assert r.status_code == 403

    def test_mode_incorrecto(self, client):
        r = client.get(
            "/webhook/meta",
            params={
                "hub.mode": "other",
                "hub.verify_token": "test_verify_token",
                "hub.challenge": "challenge_abc",
            },
        )
        assert r.status_code == 403

    def test_sin_parametros(self, client):
        r = client.get("/webhook/meta")
        assert r.status_code == 403


def _payload_status() -> bytes:
    return json.dumps(
        {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "statuses": [{"status": "delivered", "id": "wamid.X"}]
                            }
                        }
                    ]
                }
            ]
        }
    ).encode()


class TestMetaWebhookPost:
    """POST /webhook/meta — HMAC, payload, dedup, status updates."""

    def test_sin_signature_403(self, client):
        r = client.post("/webhook/meta", content=b"{}", headers={})
        assert r.status_code == 403
        assert "signature" in r.json()["detail"].lower()

    def test_signature_invalida_403(self, client):
        body = b'{"entry": []}'
        r = client.post(
            "/webhook/meta",
            content=body,
            headers={"X-Hub-Signature-256": "sha256=deadbeef"},
        )
        assert r.status_code == 403

    def test_signature_valida_status_update_ignored(self, client):
        body = _payload_status()
        sig = _sign("test_secret", body)
        r = client.post(
            "/webhook/meta", content=body, headers={"X-Hub-Signature-256": sig}
        )
        assert r.status_code == 200
        assert r.json()["status"] == "ignored"
        assert r.json()["reason"] == "status_update"

    def test_signature_valida_json_invalido_400(self, client):
        body = b"no-soy-json{{"
        sig = _sign("test_secret", body)
        r = client.post(
            "/webhook/meta", content=body, headers={"X-Hub-Signature-256": sig}
        )
        assert r.status_code == 400

    def test_signature_valida_payload_estructura_invalida_400(self, client):
        body = json.dumps({"otra": "cosa"}).encode()
        sig = _sign("test_secret", body)
        r = client.post(
            "/webhook/meta", content=body, headers={"X-Hub-Signature-256": sig}
        )
        assert r.status_code == 400

    def test_entry_vacio_ignored(self, client):
        body = json.dumps({"entry": []}).encode()
        sig = _sign("test_secret", body)
        r = client.post(
            "/webhook/meta", content=body, headers={"X-Hub-Signature-256": sig}
        )
        assert r.status_code == 200

    def test_sin_messages_ignored(self, client):
        body = json.dumps(
            {"entry": [{"changes": [{"value": {}}]}]}
        ).encode()
        sig = _sign("test_secret", body)
        r = client.post(
            "/webhook/meta", content=body, headers={"X-Hub-Signature-256": sig}
        )
        assert r.status_code == 200
        assert r.json()["status"] == "ignored"

    def test_kill_switch_activo_ignored(self, client):
        body = _payload_status()
        sig = _sign("test_secret", body)
        with patch("api.bridge._is_kill_switch_active", return_value=True):
            r = client.post(
                "/webhook/meta", content=body, headers={"X-Hub-Signature-256": sig}
            )
        assert r.status_code == 200
        assert r.json()["status"] == "ignored"


class TestVerifySignatureUnit:
    """Unit tests de _verify_meta_signature."""

    def test_firma_correcta(self):
        from api.bridge import _verify_meta_signature

        body = b"payload"
        sig = _sign("test_secret", body)
        assert _verify_meta_signature(body, sig) is True

    def test_firma_incorrecta(self):
        from api.bridge import _verify_meta_signature

        assert _verify_meta_signature(b"payload", "sha256=bad") is False

    def test_header_vacio(self):
        from api.bridge import _verify_meta_signature

        assert _verify_meta_signature(b"payload", "") is False

    def test_header_sin_prefijo(self):
        from api.bridge import _verify_meta_signature

        body = b"payload"
        digest = hmac.new(b"test_secret", body, hashlib.sha256).hexdigest()
        assert _verify_meta_signature(body, digest) is False


class TestValidateMetaPayloadUnit:
    def test_payload_minimo_valido(self):
        from api.bridge import _validate_meta_payload

        assert _validate_meta_payload({"entry": [{"changes": [{"value": {}}]}]}) is True

    def test_payload_sin_entry(self):
        from api.bridge import _validate_meta_payload

        assert _validate_meta_payload({}) is False