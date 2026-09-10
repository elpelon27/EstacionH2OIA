"""Tests de endpoints HTTP del bridge: /webhook/meta (GET+POST) y seguridad.

Cobertura de DT-12: los endpoints de Meta webhook con firma HMAC válida/inválida,
verify token, payload inválido y kill switch. Usa los mismos env vars de test que
test_bridge_network.py (META_APP_SECRET='test', META_VERIFY_TOKEN) para no depender
de secretos reales de config/.env.
"""

import hashlib
import hmac
import json
import os
import sys

import pytest
from fastapi.testclient import TestClient

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

# Bypass LOG_SALT + env de test, ANTES de importar el bridge (mismo patrón que
# test_bridge_network.py).
os.environ["BRIDGE_ALLOW_INSECURE_SALT"] = "1"
os.environ.setdefault("META_APP_SECRET", "test")
os.environ.setdefault("META_VERIFY_TOKEN", "test_verify_token")
os.environ.setdefault("META_ACCESS_TOKEN", "")
os.environ.setdefault("META_PHONE_NUMBER_ID", "")
os.environ.setdefault("DIFY_API_KEY", "")

from api.bridge import (  # noqa: E402
    META_APP_SECRET,
    META_VERIFY_TOKEN,
    _validate_meta_payload,
    _verify_meta_signature,
    app,
)


@pytest.fixture(scope="module")
def client():
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def _sign(secret: str, body: bytes) -> str:
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def _signed_headers(body: bytes) -> dict[str, str]:
    """Firma el body con el META_APP_SECRET que el bridge tenga cargado."""
    return {"X-Hub-Signature-256": _sign(META_APP_SECRET, body)}


def _payload_status() -> bytes:
    return json.dumps(
        {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                # contacts requeridos por _validate_meta_payload
                                # aunque Meta no los envía en status updates reales
                                # (véase nota en la clase TestMetaWebhookPost)
                                "contacts": [{"wa_id": "584145555555"}],
                                "statuses": [{"status": "delivered", "id": "wamid.X"}],
                            }
                        }
                    ]
                }
            ]
        }
    ).encode()


class TestMetaWebhookGet:
    """GET /webhook/meta — verificación de suscripción (hub.challenge)."""

    def test_verify_token_correcto(self, client):
        r = client.get(
            "/webhook/meta",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": META_VERIFY_TOKEN,
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
                "hub.verify_token": META_VERIFY_TOKEN,
                "hub.challenge": "challenge_abc",
            },
        )
        assert r.status_code == 403

    def test_sin_parametros(self, client):
        r = client.get("/webhook/meta")
        assert r.status_code == 403


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
        r = client.post(
            "/webhook/meta", content=body, headers=_signed_headers(body)
        )
        assert r.status_code == 200
        assert r.json()["reason"] == "status_update"

    def test_signature_valida_json_invalido_400(self, client):
        body = b"no-soy-json{{"
        r = client.post(
            "/webhook/meta", content=body, headers=_signed_headers(body)
        )
        assert r.status_code == 400

    def test_signature_valida_payload_estructura_invalida_400(self, client):
        body = json.dumps({"otra": "cosa"}).encode()
        r = client.post(
            "/webhook/meta", content=body, headers=_signed_headers(body)
        )
        assert r.status_code == 400

    def test_entry_vacio_400(self, client):
        # entry=[] falla _validate_meta_payload (400) antes del catch KeyError/IndexError
        body = json.dumps({"entry": []}).encode()
        r = client.post(
            "/webhook/meta", content=body, headers=_signed_headers(body)
        )
        assert r.status_code == 400

    def test_kill_switch_activo_ignored(self, client, monkeypatch):
        body = _payload_status()
        monkeypatch.setattr(
            "api.bridge._is_kill_switch_active", lambda: True, raising=True
        )
        r = client.post(
            "/webhook/meta", content=body, headers=_signed_headers(body)
        )
        assert r.status_code == 200
        assert r.json()["status"] == "ignored"


class TestVerifySignatureUnit:
    """Unit tests de _verify_meta_signature."""

    def test_firma_correcta(self):
        body = b"payload"
        assert _verify_meta_signature(body, _sign(META_APP_SECRET, body)) is True

    def test_firma_incorrecta(self):
        assert _verify_meta_signature(b"payload", "sha256=bad") is False

    def test_header_vacio(self):
        assert _verify_meta_signature(b"payload", "") is False

    def test_header_sin_prefijo(self):
        body = b"payload"
        digest = hmac.new(META_APP_SECRET.encode(), body, hashlib.sha256).hexdigest()
        assert _verify_meta_signature(body, digest) is False


class TestValidateMetaPayloadUnit:
    """_validate_meta_payload: estructura mínima Meta Cloud API."""

    def _valid(self):
        return {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "contacts": [{"wa_id": "584145555555"}],
                                "messages": [{"id": "wamid.1", "type": "text"}],
                            }
                        }
                    ]
                }
            ]
        }

    def test_payload_valido(self):
        assert _validate_meta_payload(self._valid()) is True

    def test_sin_entry(self):
        assert _validate_meta_payload({}) is False

    def test_entry_no_lista(self):
        assert _validate_meta_payload({"entry": "x"}) is False

    def test_sin_changes(self):
        d = self._valid()
        d["entry"][0]["changes"] = []
        assert _validate_meta_payload(d) is False

    def test_sin_contacts(self):
        d = self._valid()
        del d["entry"][0]["changes"][0]["value"]["contacts"]
        assert _validate_meta_payload(d) is False

    def test_wa_id_no_digitos(self):
        d = self._valid()
        d["entry"][0]["changes"][0]["value"]["contacts"][0]["wa_id"] = "abc-def"
        assert _validate_meta_payload(d) is False