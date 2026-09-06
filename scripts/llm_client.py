#!/usr/bin/env python3
"""
============================================================================
LLMClient — Cadena de fallback LLM de 3 tiers con routing por tipo de tarea
============================================================================
Tiers (en orden):
  1. glm-5.3-paid   (z-ai/glm-5.3, OpenRouter)      → técnico + chat
  2. glm-5.2-free   (z-ai/glm-5.2:free, OpenRouter)  → técnico + chat
  3. ollama-local   (qwen2.5:7b, localhost:11434)     → SOLO chat

REGLA DEL LÍDER (grabada en piedra):
  Ollama local = SOLO para chat conversacional.
  NUNCA para: código, fixes, desarrollo, scripts, modificaciones al repo.
  Para tareas técnicas sin modelo pagado disponible → rechazar
  con NO_PAID_LLM_AVAILABLE.

Ver docs/LLM_FALLBACK.md para el diseño completo.
Tier adicional (no está en la cadena de chat): "gemini-3-pro-preview",
invocado explícitamente con task_type="video" (análisis de videos,
claude-watch).
"""

import logging
import os
import time

import httpx

logger = logging.getLogger("llm_client")


def _load_env_file(path: str = "/mnt/ssd_trabajo/hermes-agent/config/.env") -> None:
    """Carga config/.env si las variables aún no están en el entorno."""
    if not os.path.exists(path):
        return
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    os.environ.setdefault(k.strip(), v.strip())
    except OSError as e:
        logger.warning("No se pudo leer %s: %s", path, e)


_load_env_file()


class LLMClient:
    """Cliente LLM con cadena de fallback de 3 tiers y routing por tarea."""

    def __init__(self) -> None:
        self.tier_chain = [
            {
                "name": "glm-5.3-paid",
                "model": os.getenv("OPENROUTER_MODEL_PAID", "z-ai/glm-5.3"),
                "base_url": "https://openrouter.ai/api/v1",
                "api_key": os.getenv("OPENROUTER_API_KEY", ""),
                "technical_ok": True,
                "chat_ok": True,
            },
            {
                "name": "glm-5.2-free",
                "model": os.getenv("OPENROUTER_MODEL_FREE", "z-ai/glm-5.2:free"),
                "base_url": "https://openrouter.ai/api/v1",
                "api_key": os.getenv("OPENROUTER_API_KEY", ""),
                "technical_ok": True,
                "chat_ok": True,
            },
            {
                # Tier dedicado a análisis de video (claude-watch).
                # NO entra en la cadena de chat/técnico: se invoca explícitamente
                # con task_type="video".
                "name": "gemini-3-pro-preview",
                "model": os.getenv(
                    "OPENROUTER_MODEL_VIDEO", "google/gemini-3.1-pro-preview"
                ),
                "base_url": "https://openrouter.ai/api/v1",
                "api_key": os.getenv("OPENROUTER_API_KEY", ""),
                "technical_ok": True,
                "chat_ok": True,
                "video_ok": True,
            },
            {
                "name": "ollama-local",
                "model": os.getenv("OLLAMA_MODEL", "qwen2.5:7b"),
                "base_url": os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
                "api_key": "ollama",
                "technical_ok": False,
                "chat_ok": True,
            },
        ]
        self.timeout = int(os.getenv("LLM_TIMEOUT", "60"))
        # Contador de fallos por tier para el WARNING de degradación
        self._fail_counts: dict[str, int] = {t["name"]: 0 for t in self.tier_chain}

    def complete(
        self, messages: list[dict], task_type: str = "chat", **kwargs: object
    ) -> dict:
        """Intenta cada tier en orden. Devuelve
        {'content': str, 'tier': str, 'model': str} o, en tareas técnicas
        sin LLM pagado disponible, {'error': 'NO_PAID_LLM_AVAILABLE', ...}.
        """
        last_error: Exception | None = None
        for tier in self.tier_chain:
            if task_type == "technical" and not tier["technical_ok"]:
                logger.warning("SKIP %s: no apto para tareas técnicas", tier["name"])
                continue
            if task_type == "video":
                if not tier.get("video_ok"):
                    continue
            if task_type == "chat" and not tier["chat_ok"]:
                continue
            try:
                t0 = time.monotonic()
                resp = self._call(tier, messages, **kwargs)  # type: ignore[arg-type]
                latency = time.monotonic() - t0
                self._fail_counts[tier["name"]] = 0
                logger.info(
                    "LLM OK via %s model=%s task_type=%s latency=%.2fs",
                    tier["name"], tier["model"], task_type, latency,
                )
                if tier["name"] == "ollama-local":
                    logger.info("Modo degradado: chat atendido por Ollama local")
                return resp
            except (
                httpx.HTTPStatusError,
                httpx.ReadTimeout,
                httpx.ConnectError,
                httpx.HTTPError,
                ConnectionError,
                TimeoutError,
            ) as e:
                logger.warning("LLM FAIL %s: %s", tier["name"], type(e).__name__)
                self._fail_counts[tier["name"]] += 1
                if self._fail_counts[tier["name"]] > 5:
                    logger.warning(
                        "Tier %s falló %d veces en esta sesión",
                        tier["name"], self._fail_counts[tier["name"]],
                    )
                last_error = e
                continue
        if task_type == "technical":
            logger.warning("Tarea técnica rechazada: sin LLM pagado disponible")
            return {
                "error": "NO_PAID_LLM_AVAILABLE",
                "message": (
                    "Sin créditos en OpenRouter. Para tareas técnicas necesito "
                    "GLM 5.3 pagado o GLM 5.2 free. Agregá créditos en "
                    "https://openrouter.ai/settings/credits"
                ),
            }
        raise RuntimeError(f"Todos los tiers fallaron: {last_error}")

    def _call(
        self, tier: dict, messages: list[dict], **kwargs: object
    ) -> dict:
        url = f"{tier['base_url']}/chat/completions"
        headers = {"Authorization": f"Bearer {tier['api_key']}"}
        if "openrouter" in tier["name"]:
            headers["HTTP-Referer"] = "hermes-agent"
            headers["X-Title"] = "Hermes Agent"
        body = {
            "model": tier["model"],
            "messages": messages,
            "temperature": kwargs.get("temperature", 0.7),
            "max_tokens": kwargs.get("max_tokens", 4096),
        }
        r = httpx.post(url, json=body, headers=headers, timeout=self.timeout)
        r.raise_for_status()
        data = r.json()
        # BUG 5 fix: loguear token usage (viene en el response, sin API key extra)
        usage = data.get("usage") or {}
        if usage:
            logger.info(
                "LLM usage %s: in=%s, out=%s",
                tier["name"],
                usage.get("prompt_tokens", "?"),
                usage.get("completion_tokens", "?"),
            )
        return {
            "content": data["choices"][0]["message"]["content"],
            "tier": tier["name"],
            "model": tier["model"],
            "usage": usage,
        }


# ============================================================================
# Detección de tipo de tarea (heurística por keywords del Líder)
# ============================================================================

TECHNICAL_KEYWORDS = (
    "arreglá", "arregla", "arreglar", "fix", "modificá", "modifica",
    "escribí", "escribe", "creá", "crea", "implementá", "implementa",
    "refactor", "cambiá el código", "cambia el código", "commit", "push",
    "desarrollá", "desarrolla", "script", "función", "funcion",
    "clase", "método", "metodo", "editá el archivo", "edita el archivo",
    "borrá", "borra", "agregá al .env", "agrega al .env", "sed -i",
    "nano", "git ", " pr", "merge", "patch",
)


def detect_task_type(user_input: str) -> str:
    """Heurística: si aparece alguna keyword técnica → 'technical', si no → 'chat'."""
    low = user_input.lower()
    for kw in TECHNICAL_KEYWORDS:
        if kw in low:
            return "technical"
    return "chat"
