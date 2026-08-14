"""
Guardrail wrapper para Valentina Bridge — capa semántica de protección.

Cubre la brecha que la sanitización por bytes (_sanitize_input_text) no toca:
- ENTRADA:  prompt-injection sobre el texto del usuario antes de llegar al LLM (Dify)
- SALIDA:   fuga de secretos (tokens, credenciales, números de cuenta) en respuestas
            que se envían al cliente (WhatsApp/Telegram)

Diseño (fail-open con ruido, NUNCA fail-hard):
- Si llm-guard no está instalado o falla, se registra una vez y se pasa el texto
  sin bloquear -> jamás rompe el flujo de producción.
- Si llm-guard detecta amenaza: bloquea la entrada o enmascara la salida.

Patrón perezoso: el import y los escáneres se inicializan solo al primer uso.
"""

import logging
import os
import re
from typing import Any

logger = logging.getLogger("guardrail")

# ============================================================
# Inicialización perezosa de llm-guard (puede no estar instalado)
# ============================================================

_available: bool | None = None
_scanner_secrets: Any | None = None


def _init_llm_guard() -> bool:
    """Intenta cargar los escáneres de llm-guard una sola vez. Fail-open si no está."""
    global _available, _scanner_secrets
    if _available is not None:
        return _available

    # Forzar CPU para los validadores: torch moderno no trae kernel para la GTX 1070
    # (Pascal, compute 6.1) → CUDA error "no kernel image". El motor principal de
    # inferencia es remoto (NIM GLM 5.2), no esta GPU. CPU es correcto aquí.
    os.environ["CUDA_VISIBLE_DEVICES"] = ""

    try:
        from llm_guard.input_scanners.secrets import (
            Secrets as InputSecrets,  # type: ignore[import-untyped]
        )
        from llm_guard.vault import Vault  # type: ignore[import-untyped]

        vault = Vault()
        # Escáner de entrada: detecta secretos en el texto entrante (claves, tokens)
        _scanner_secrets = InputSecrets(redact_mode="all")
        _available = True
        logger.info(
            "Guardrail llm-guard ACTIVO (secrets ENTRADA+SALIDA; inyección por reglas propias)"
        )
    except Exception as e:  # noqa: BLE001 - cualquier fallo = fail-open
        _available = False
        logger.warning(
            "Guardrail llm-guard NO disponible (%s). Fallo abierto: sin barrera semántica.",
            e,
        )
    return _available


# ============================================================
# Reglas ligeras propias (funcionan sin llm-guard, refuerzo)
# ============================================================

# Patrones de prompt injection comunes (reglas propias, no dependen de la lib)
# Cubren inglés Y español (el modelo de llm-guard falla con español — ver dictamen).
_INJECTION_PATTERN = re.compile(
    r"(ignore (all )?(previous|prior) instructions)"
    r"|(ignore everything (above|before))"
    r"|(you are now|act as a (new|different|hacker))"
    r"|(system prompt|jailbreak)"
    r"|((disregard|forget) (your |all |the )?(rules|instructions|system))"
    r"|(reveal|show|print|display) (your|the) (system|internal|secret)"
    # Español
    r"|(ignora|ignorar) (todas? )?(las |tus |toda )?(instrucciones|reglas|ordenes|prompt|sistema)"
    r"|(ignora|ignorar|olvida|olvidar) (todo|toda) (lo|la) (anterior|anteriormente)"
    r"|(olvida|olvidar) (todas? )?(las |tus )?(instrucciones|reglas|ordenes)"
    r"|(eres (ahora|un hacker)|comportate como)"
    r"|(muestrame|muestra|revela|dime) (tu |el |la )?(prompt|sistema|clave|contraseña|password)"
    r"|(prompt del sistema|jailbreak)",
    re.IGNORECASE,
)


def _own_injection_check(text: str) -> bool:
    """Heurística propia de inyección de prompt (rápida, sin dependencias)."""
    return bool(_INJECTION_PATTERN.search(text))


# ============================================================
# API pública
# ============================================================


def sanitize_input(text: str) -> str:
    """
    Escanea texto del usuario ANTES de llegar al LLM.

    Si detecta inyección de prompt: retorna un placeholder inofensivo para que
    el flujo siga sin exponer el sistema. Si no: retorna el texto intacto.
    """
    if not text or not text.strip():
        return text

    # 1. Reglas propias (siempre activas)
    if _own_injection_check(text):
        logger.warning("Guardrail ENTRADA: prompt-injection detectada (regla propia)")
        return "[mensaje bloqueado por proteccion]"

    # 2. llm-guard: detectar y neutralizar secretos pegados en el input
    if _init_llm_guard() and _scanner_secrets is not None:
        try:
            _sec_san, _sec_ok, _sec_risk = _scanner_secrets.scan(text)
            if not _sec_ok:
                logger.warning(
                    "Guardrail ENTRADA: secreto detectado en input (risk=%s) - se neutraliza",
                    _sec_risk,
                )
                return "[acceso denegado por proteccion]"
            return str(_sec_san)
        except Exception as e:  # noqa: BLE001
            logger.warning("Guardrail ENTRADA: fallo escaneo llm-guard (%s) - paso texto", e)

    return text


def scrub_output(text: str) -> str:
    """
    Escanea la respuesta que se enviará al cliente, enmascarando secretos.

    No bloquea la salida (un texto de servicio es legítimo); SOLO enmascara
    secretos que no deberían filtrarse al cliente.
    """
    if not text:
        return text

    # 1. llm-guard: detectar y neutralizar credenciales (tokens, keys) si está disponible
    if _init_llm_guard() and _scanner_secrets is not None:
        try:
            _sec_san, _sec_ok, _sec_risk = _scanner_secrets.scan(text)
            if _sec_san != text:
                logger.warning(
                    "Guardrail SALIDA: se enmascararon secretos en respuesta (risk=%s)", _sec_risk
                )
            text = str(_sec_san)
        except Exception as e:  # noqa: BLE001
            logger.warning("Guardrail SALIDA: fallo escaneo llm-guard (%s) - paso texto", e)

    # 2. Fallback propio: enmascarar patrones típicos de credenciales (SIEMPRE se ejecuta)
    #    (Bearer tokens, claves tipo sk-, números de cuenta largos)
    _fallback_scrub = [
        (re.compile(r"(Bearer\s+)[A-Za-z0-9._-]{20,}"), r"\1•••••"),
        (re.compile(r"(sk-[A-Za-z0-9_.-]{16,})"), "sk-•••••"),
        (
            re.compile(r"(access[_-]?token\s*[:=]?\s*)([A-Za-z0-9._-]{16,})", re.IGNORECASE),
            r"\1•••••",
        ),
    ]
    for pat, repl in _fallback_scrub:
        text = pat.sub(repl, text)

    return text


# ============================================================
# Resumen de estado (para health check)
# ============================================================


def status() -> dict[str, Any]:
    """Devuelve estado del guardrail para /health."""
    _init_llm_guard()
    return {
        "available": bool(_available),
        "input_scanner": "prompt_injection" if _available else "rules_only",
        "output_scanner": "secrets_redact" if _available else "fallback_rules",
        "own_injection_rules": True,
    }
