"""Tests unitarios adicionales para helpers puros de api/bridge.py (DT-12).

Cubre helpers determinísticos no cubiertos por test_bridge.py existente:
- _sanitize_input_text: saneamiento de entrada de usuario
- _verify_meta_signature: HMAC-SHA256 de webhooks de Meta
"""

import os
import sys
from unittest.mock import patch

# Path setup (idéntico a test_bridge.py)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "api"))

os.environ["BRIDGE_ALLOW_INSECURE_SALT"] = "1"

import bridge  # noqa: E402


class TestSanitizeInputText:
    def test_vacio(self):
        assert bridge._sanitize_input_text("") == ""

    def test_none(self):
        assert bridge._sanitize_input_text(None) == ""

    def test_texto_normal(self):
        assert bridge._sanitize_input_text("Hola cliente") == "Hola cliente"

    def test_quita_caracteres_control(self):
        # \x00 y \x08 son control peligroso → se eliminan; \n se mantiene en clean
        result = bridge._sanitize_input_text("a\x00b\x08c")
        assert "\x00" not in result
        assert "\x08" not in result

    def test_trunca_largo(self):
        result = bridge._sanitize_input_text("x" * 2500)
        assert len(result) < 2500
        assert "truncado" in result

    def test_normaliza_whitespace(self):
        assert bridge._sanitize_input_text("  a    b   ") == "a b"

    def test_mantiene_newline_y_tab(self):
        # Tras la limpieza de control chars, \n\r\t se conservan (antes del strip)
        result = bridge._sanitize_input_text("linea1\nlinea2\tfin")
        assert "linea1" in result and "linea2" in result


class TestVerifyMetaSignature:
    def test_sin_app_secret_rechaza(self):
        with patch.object(bridge, "META_APP_SECRET", ""):
            assert bridge._verify_meta_signature(b"body", "sha256=x") is False

    def test_sin_header_rechaza(self):
        with patch.object(bridge, "META_APP_SECRET", "secret"):
            assert bridge._verify_meta_signature(b"body", "") is False

    def test_firma_valida(self):
        import hashlib
        import hmac

        app_secret = "test_secret"
        body = b'{"event": "ping"}'
        expected = "sha256=" + hmac.new(
            app_secret.encode(), body, hashlib.sha256
        ).hexdigest()
        with patch.object(bridge, "META_APP_SECRET", app_secret):
            assert bridge._verify_meta_signature(body, expected) is True

    def test_firma_invalida(self):
        with patch.object(bridge, "META_APP_SECRET", "test_secret"):
            assert bridge._verify_meta_signature(b"body", "sha256=deadbeef") is False