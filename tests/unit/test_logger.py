"""Tests para core/logger.py."""

import io
from contextlib import redirect_stdout

from core.logger import get_logger, mask_pii, setup_logging


def test_mask_phone():
    """Teléfonos largos deben enmascararse."""
    assert mask_pii("+584122560721") == "[PHONE]"
    assert mask_pii("584122560721") == "[PHONE]"


def test_mask_openrouter_key():
    """API keys de OpenRouter deben enmascararse."""
    key = "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"
    masked = mask_pii(key)
    assert "sk-or-v1-" not in masked
    assert "[OPENROUTER_KEY]" in masked


def test_mask_telegram_token():
    """Tokens de Telegram deben enmascararse completos."""
    token = "8648954906:AAFo3BlCjcz_D5QY-d6OriuQ_VycoSYbXPQ"
    masked = mask_pii(token)
    assert "AAFo3BlCjcz" not in masked
    assert "[TELEGRAM_TOKEN]" in masked


def test_mask_github_pat():
    """GitHub PATs deben enmascararse completos."""
    pat = "ghp_abcdef1234567890abcdef1234567890abcdef"
    masked = mask_pii(pat)
    assert "ghp_" not in masked
    assert "[GITHUB_PAT]" in masked


def test_mask_payment_ref():
    """Referencias de pago largas deben enmascararse."""
    ref = "PAYREF1234567890"
    masked = mask_pii(ref)
    assert "PAYREF1234567890" not in masked
    assert "[PAYMENT_REF]" in masked


def test_mask_dict():
    """Debe enmascarar PII dentro de dicts."""
    data = {"phone": "+584122560721", "name": "Luis"}
    masked = mask_pii(data)
    assert masked["phone"] == "[PHONE]"
    assert masked["name"] == "Luis"


def test_mask_list():
    """Debe enmascarar PII dentro de listas."""
    data = ["+584122560721", "texto normal"]
    masked = mask_pii(data)
    assert masked[0] == "[PHONE]"
    assert masked[1] == "texto normal"


def test_mask_preserves_int():
    """No debe alterar valores no-string."""
    assert mask_pii(12345) == 12345
    assert mask_pii(3.14) == 3.14
    assert mask_pii(True) is True


def test_logger_setup():
    """setup_logging no debe lanzar excepciones."""
    setup_logging("INFO")
    logger = get_logger("test")
    logger.info("test_event", key="value")


def test_logger_masks_pii():
    """Logger debe enmascarar PII en output (structlog usa stdout)."""
    setup_logging("INFO")
    logger = get_logger("test_pii")

    buf = io.StringIO()
    with redirect_stdout(buf):
        logger.info("message_received", phone="+584122560721")

    output = buf.getvalue()
    assert "[PHONE]" in output
    assert "584122560721" not in output


def test_logger_masks_multiple_pii():
    """Logger debe enmascarar múltiples tipos de PII en un solo evento."""
    setup_logging("INFO")
    logger = get_logger("test_multi_pii")

    buf = io.StringIO()
    with redirect_stdout(buf):
        logger.info(
            "multi_event",
            phone="+584122560721",
            api_key="sk-or-v1-abc123def456ghi789jkl012mno345pqr678stu901vwx234yz567",
            token="8648954906:AAFo3BlCjcz_D5QY-d6OriuQ_VycoSYbXPQ",
        )

    output = buf.getvalue()
    assert "[PHONE]" in output
    assert "[OPENROUTER_KEY]" in output
    assert "[TELEGRAM_TOKEN]" in output
    assert "584122560721" not in output
    assert "AAFo3BlCjcz" not in output
