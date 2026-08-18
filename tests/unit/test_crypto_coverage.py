"""Tests unitarios para core/crypto.py — funciones de hashing y PII.

Cubre las líneas sin cubrir:
- set_log_salt: re-set con valor distinto (RuntimeError), salt inseguro (ValueError)
- get_log_salt: sin inicializar (RuntimeError)
- hash_phone: phone vacío (ValueError), éxito
- hash_phone_legacy: phone vacío (ValueError), éxito
- is_legacy_hash / is_current_hash

El estado global _LOG_SALT se resetea entre tests mediante patch directo.
"""

import hashlib
import os
import sys

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import core.crypto as crypto_mod

# ============================================================================
# Fixtures — reset del estado global _LOG_SALT entre tests
# ============================================================================

@pytest.fixture(autouse=True)
def _reset_log_salt():
    """Resetea _LOG_SALT a None antes y después de cada test."""
    original = crypto_mod._LOG_SALT
    crypto_mod._LOG_SALT = None
    # Limpiar env var de bypass para que cada test controle su propio estado
    old_env = os.environ.pop("BRIDGE_ALLOW_INSECURE_SALT", None)
    yield
    crypto_mod._LOG_SALT = original
    if old_env is not None:
        os.environ["BRIDGE_ALLOW_INSECURE_SALT"] = old_env


# ============================================================================
# set_log_salt
# ============================================================================

class TestSetLogSalt:
    def test_sets_valid_salt(self):
        salt = "a" * 40  # salt seguro (>32 chars, no default)
        crypto_mod.set_log_salt(salt)
        assert salt == crypto_mod._LOG_SALT

    def test_idempotent_same_value(self):
        salt = "b" * 40
        crypto_mod.set_log_salt(salt)
        # Re-set con el mismo valor → no-op, no raise
        crypto_mod.set_log_salt(salt)
        assert salt == crypto_mod._LOG_SALT

    def test_reset_different_value_raises(self):
        """Re-set con valor distinto → RuntimeError."""
        crypto_mod.set_log_salt("c" * 40)
        with pytest.raises(RuntimeError, match="ya fue inicializado"):
            crypto_mod.set_log_salt("d" * 40)

    def test_insecure_salt_empty_raises(self):
        """Salt vacío sin bypass → ValueError."""
        with pytest.raises(ValueError, match="inseguro"):
            crypto_mod.set_log_salt("")

    def test_insecure_salt_default_raises(self):
        """Salt == 'change-this-in-production' sin bypass → ValueError."""
        with pytest.raises(ValueError, match="inseguro"):
            crypto_mod.set_log_salt("change-this-in-production")

    def test_insecure_salt_allowed_with_bypass(self):
        """Salt inseguro CON BRIDGE_ALLOW_INSECURE_SALT → lo permite (path dev/test)."""
        os.environ["BRIDGE_ALLOW_INSECURE_SALT"] = "1"
        crypto_mod.set_log_salt("")
        assert crypto_mod._LOG_SALT == ""

    def test_insecure_default_allowed_with_bypass(self):
        os.environ["BRIDGE_ALLOW_INSECURE_SALT"] = "1"
        crypto_mod.set_log_salt("change-this-in-production")
        assert crypto_mod._LOG_SALT == "change-this-in-production"


# ============================================================================
# get_log_salt
# ============================================================================

class TestGetLogSalt:
    def test_not_initialized_raises(self):
        with pytest.raises(RuntimeError, match="no inicializado"):
            crypto_mod.get_log_salt()

    def test_returns_initialized_salt(self):
        salt = "e" * 40
        crypto_mod.set_log_salt(salt)
        assert crypto_mod.get_log_salt() == salt


# ============================================================================
# hash_phone
# ============================================================================

class TestHashPhone:
    def test_empty_phone_raises(self):
        crypto_mod.set_log_salt("f" * 40)
        with pytest.raises(ValueError, match="no puede ser vacío"):
            crypto_mod.hash_phone("")

    def test_hash_is_deterministic(self):
        crypto_mod.set_log_salt("g" * 40)
        h1 = crypto_mod.hash_phone("+584122560721")
        h2 = crypto_mod.hash_phone("+584122560721")
        assert h1 == h2

    def test_hash_is_32_chars(self):
        crypto_mod.set_log_salt("h" * 40)
        h = crypto_mod.hash_phone("+584122560721")
        assert len(h) == 32

    def test_hash_includes_salt(self):
        """El hash cambia si cambia el salt (no es legacy sin salt)."""
        crypto_mod.set_log_salt("salt_A" * 10)
        h_a = crypto_mod.hash_phone("+584122560721")

        crypto_mod._LOG_SALT = None
        crypto_mod.set_log_salt("salt_B" * 10)
        h_b = crypto_mod.hash_phone("+584122560721")

        assert h_a != h_b

    def test_hash_format_matches_manual(self):
        """Verifica que el hash es SHA-256(salt:phone)[:32]."""
        salt = "mysalt" * 10
        crypto_mod.set_log_salt(salt)
        phone = "+584122560721"
        expected = hashlib.sha256(f"{salt}:{phone}".encode()).hexdigest()[:32]
        assert crypto_mod.hash_phone(phone) == expected

    def test_not_initialized_raises(self):
        with pytest.raises(RuntimeError, match="no inicializado"):
            crypto_mod.hash_phone("+584122560721")


# ============================================================================
# hash_phone_legacy
# ============================================================================

class TestHashPhoneLegacy:
    def test_empty_phone_raises(self):
        with pytest.raises(ValueError, match="no puede ser vacío"):
            crypto_mod.hash_phone_legacy("")

    def test_hash_is_16_chars(self):
        h = crypto_mod.hash_phone_legacy("+584122560721")
        assert len(h) == 16

    def test_hash_is_deterministic(self):
        h1 = crypto_mod.hash_phone_legacy("+584122560721")
        h2 = crypto_mod.hash_phone_legacy("+584122560721")
        assert h1 == h2

    def test_hash_format_matches_manual(self):
        phone = "+584122560721"
        expected = hashlib.sha256(phone.encode()).hexdigest()[:16]
        assert crypto_mod.hash_phone_legacy(phone) == expected

    def test_no_salt_dependency(self):
        """Legacy hash no depende de LOG_SALT."""
        h1 = crypto_mod.hash_phone_legacy("+584122560721")
        # Set salt y verificar que el hash legacy no cambia
        crypto_mod.set_log_salt("somesalt" * 10)
        h2 = crypto_mod.hash_phone_legacy("+584122560721")
        assert h1 == h2


# ============================================================================
# is_legacy_hash / is_current_hash
# ============================================================================

class TestHashFormatChecks:
    def test_is_legacy_hash_true(self):
        h = "a" * 16
        assert crypto_mod.is_legacy_hash(h) is True

    def test_is_legacy_hash_false_for_32(self):
        h = "a" * 32
        assert crypto_mod.is_legacy_hash(h) is False

    def test_is_current_hash_true(self):
        h = "a" * 32
        assert crypto_mod.is_current_hash(h) is True

    def test_is_current_hash_false_for_16(self):
        h = "a" * 16
        assert crypto_mod.is_current_hash(h) is False

    def test_is_legacy_hash_false_for_other_length(self):
        assert crypto_mod.is_legacy_hash("a" * 20) is False

    def test_is_current_hash_false_for_other_length(self):
        assert crypto_mod.is_current_hash("a" * 20) is False

    def test_hashes_from_functions_match_format(self):
        """Los hashes generados por las funciones coinciden con los detectores."""
        crypto_mod.set_log_salt("x" * 40)
        current = crypto_mod.hash_phone("+584122560721")
        legacy = crypto_mod.hash_phone_legacy("+584122560721")

        assert crypto_mod.is_current_hash(current) is True
        assert crypto_mod.is_legacy_hash(current) is False
        assert crypto_mod.is_legacy_hash(legacy) is True
        assert crypto_mod.is_current_hash(legacy) is False


# ============================================================================
# Constantes
# ============================================================================

class TestConstants:
    def test_phone_hash_length(self):
        assert crypto_mod.PHONE_HASH_LENGTH == 32

    def test_legacy_phone_hash_length(self):
        assert crypto_mod.LEGACY_PHONE_HASH_LENGTH == 16
