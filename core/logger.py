"""Logger estructurado con structlog + sanitización PII.

Máscaras automáticas:
- API keys (OpenRouter, Telegram, GitHub)
- Referencias de pago
- Números de teléfono

IMPORTANTE: patrones más específicos van PRIMERO para que no sean
parcialmente matcheados por patrones más genéricos (como phone).
"""

import logging
import re
from typing import Any

import structlog

# Patrones PII ordenados de MÁS específico a MENOS específico
# payment_ref ANTES de phone para que phone no rompa las refs
_PATTERNS = [
    # API keys específicos (primero)
    (re.compile(r"sk-or-v1-[a-zA-Z0-9-_]{20,}"), "[OPENROUTER_KEY]"),
    (re.compile(r"\d{8,10}:AA[A-Za-z0-9_-]{30,}"), "[TELEGRAM_TOKEN]"),
    (re.compile(r"ghp_[a-zA-Z0-9]{30,}"), "[GITHUB_PAT]"),
    (re.compile(r"github_pat_[a-zA-Z0-9_]{20,}"), "[GITHUB_PAT]"),
    # Referencias de pago alfanuméricas (antes que phone)
    (re.compile(r"\b[A-Z]{2,}\d{6,}\b"), "[PAYMENT_REF]"),
    # Teléfono (después de tokens y refs)
    (re.compile(r"(?<!\d)\+?\d{10,15}(?!\d)"), "[PHONE]"),
]


def mask_pii(value: Any) -> Any:
    """Enmascarar PII en strings recursivamente."""
    if isinstance(value, str):
        masked = value
        for pattern, replacement in _PATTERNS:
            masked = pattern.sub(replacement, masked)
        return masked
    if isinstance(value, dict):
        return {k: mask_pii(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return type(value)(mask_pii(v) for v in value)
    return value


def _pii_processor(logger: Any, method_name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    """Processor de structlog: enmascara PII antes de renderizar."""
    for key, value in event_dict.items():
        event_dict[key] = mask_pii(value)
    return event_dict


def setup_logging(log_level: str = "INFO") -> None:
    """Configurar structlog con JSON output y PII sanitization."""
    level = getattr(logging, log_level.upper(), logging.INFO)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            _pii_processor,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = "hermes") -> Any:
    """Obtener logger configurado."""
    return structlog.get_logger(name)
