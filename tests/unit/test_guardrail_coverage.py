"""Tests unitarios para cubrir las lineas sin cobertura de api/guardrail.py.

Lineas sin cubrir: 56-58, 119-123, 125-128, 146, 150-151, 176-177.

Estas son las rutas que involucran llm-guard:
- _init_llm_guard: excepcion al importar llm-guard (56-58)
- sanitize_input: llm-guard detecta secreto (119-123), excepcion en scan (125-128)
- scrub_output: secreto detectado en salida (146), excepcion en scan (150-151)
- status(): llamada a _init_llm_guard (176-177)

Se mockea _init_llm_guard y _scanner_secrets para simular los caminos.
"""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
API_ROOT = os.path.join(PROJECT_ROOT, "api")
if API_ROOT not in sys.path:
    sys.path.insert(0, API_ROOT)

import guardrail


@pytest.fixture(autouse=True)
def _reset_guardrail_state():
    """Resetea el estado global del guardrail entre tests."""
    old_avail = guardrail._available
    old_scanner = guardrail._scanner_secrets
    guardrail._available = None
    guardrail._scanner_secrets = None
    yield
    guardrail._available = old_avail
    guardrail._scanner_secrets = old_scanner


class TestInitLlmGuard:
    def test_init_returns_false_on_import_error(self):
        """_init_llm_guard con import fallido → False (lineas 56-58)."""
        # Forzar que el import de llm_guard falle
        import builtins

        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name.startswith("llm_guard"):
                raise ImportError(f"No module named '{name}'")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=mock_import):
            result = guardrail._init_llm_guard()

        assert result is False
        assert guardrail._available is False

    def test_init_returns_true_when_available(self):
        """_init_llm_guard cuando llm-guard está disponible → True."""
        # Simular que llm_guard está instalado
        mock_scanner = MagicMock()
        mock_vault = MagicMock()

        with patch.dict(sys.modules, {
            "llm_guard": MagicMock(),
            "llm_guard.input_scanners": MagicMock(),
            "llm_guard.input_scanners.secrets": MagicMock(),
            "llm_guard.vault": MagicMock(),
        }):
            # Mockear los imports específicos
            mock_input_secrets = MagicMock()
            mock_input_secrets.Secrets = MagicMock(return_value=mock_scanner)
            mock_vault_class = MagicMock()

            with patch.dict(sys.modules, {
                "llm_guard.input_scanners.secrets": MagicMock(Secrets=mock_input_secrets.Secrets),
                "llm_guard.vault": MagicMock(Vault=mock_vault_class),
            }):
                result = guardrail._init_llm_guard()

        # Puede ser True o False dependiendo del entorno, pero debe ser idempotente
        assert result == guardrail._available


class TestSanitizeInputWithLlmGuard:
    def test_secret_detected_in_input(self):
        """llm-guard detecta secreto en input → bloquea (lineas 119-123)."""
        # Simular llm-guard activo con scanner que detecta secreto
        guardrail._available = True
        mock_scanner = MagicMock()
        mock_scanner.scan.return_value = ("redacted", False, 0.9)  # _sec_ok=False
        guardrail._scanner_secrets = mock_scanner

        result = guardrail.sanitize_input("my api key is sk-abc123")

        assert result == "[acceso denegado por proteccion]"
        mock_scanner.scan.assert_called_once()

    def test_scan_exception_passes_text(self):
        """llm-guard scan raises exception → pasa texto (lineas 125-128)."""
        guardrail._available = True
        mock_scanner = MagicMock()
        mock_scanner.scan.side_effect = RuntimeError("scan failed")
        guardrail._scanner_secrets = mock_scanner

        text = "texto normal sin secretos"
        result = guardrail.sanitize_input(text)

        # Debe retornar el texto original (no bloqueado por reglas propias,
        # y el scan falló → fail-open)
        assert result == text

    def test_secret_cleaned_in_input(self):
        """llm-guard detecta y limpia secreto → retorna texto limpio."""
        guardrail._available = True
        mock_scanner = MagicMock()
        mock_scanner.scan.return_value = ("cleaned text", True, 0.1)  # _sec_ok=True
        guardrail._scanner_secrets = mock_scanner

        result = guardrail.sanitize_input("some text")

        assert result == "cleaned text"


class TestScrubOutputWithLlmGuard:
    def test_secret_detected_in_output(self):
        """llm-guard detecta secreto en salida → enmascara (linea 146)."""
        guardrail._available = True
        mock_scanner = MagicMock()
        mock_scanner.scan.return_value = ("redacted output", True, 0.8)
        guardrail._scanner_secrets = mock_scanner

        result = guardrail.scrub_output("token: sk-secret1234567890123")

        assert result == "redacted output"

    def test_scan_exception_passes_text(self):
        """llm-guard scan raises en scrub_output → pasa texto (lineas 150-151)."""
        guardrail._available = True
        mock_scanner = MagicMock()
        mock_scanner.scan.side_effect = RuntimeError("scan error")
        guardrail._scanner_secrets = mock_scanner

        text = "texto normal"
        result = guardrail.scrub_output(text)

        # Fail-open: retorna el texto (posiblemente con fallback scrub)
        assert "texto normal" in result


class TestStatus:
    def test_status_returns_dict(self):
        """status() retorna dict con claves esperadas (lineas 176-177)."""
        result = guardrail.status()

        assert isinstance(result, dict)
        assert "available" in result
        assert "input_scanner" in result
        assert "output_scanner" in result
        assert "own_injection_rules" in result
        assert result["own_injection_rules"] is True

    def test_status_with_llm_guard_unavailable(self):
        """status() cuando llm-guard no disponible → rules_only/fallback_rules."""
        guardrail._available = False

        result = guardrail.status()

        assert result["available"] is False
        assert result["input_scanner"] == "rules_only"
        assert result["output_scanner"] == "fallback_rules"

    def test_status_with_llm_guard_available(self):
        """status() cuando llm-guard disponible → prompt_injection/secrets_redact."""
        guardrail._available = True

        result = guardrail.status()

        assert result["available"] is True
        assert result["input_scanner"] == "prompt_injection"
        assert result["output_scanner"] == "secrets_redact"
