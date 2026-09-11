#!/usr/bin/env python3
"""Whatsscanbot — LLM client PROPIO (DT-WSIMPORT 2F).

Cadena de fallback EXCLUSIVA del Whatsscanbot (decisión del Líder):
  1. deepseek/deepseek-v4-flash  (OpenRouter, PRIMARIO)
  2. z-ai/glm-5.3                (OpenRouter)
  3. z-ai/glm-5.2:free           (OpenRouter, rate-limited)
  4. qwen2.5:7b                  (Ollama local, SOLO emergencia,
                                  NUNCA para parseo — solo resúmenes)

NO usa scripts/llm_client.py general del repo (ese es del orquestador Hermes).
Usa OPENROUTER_API_KEY existente en config/.env.
task_type="summary" recorre la cadena con fallback y loguea el tier usado.
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any

import requests

logger = logging.getLogger("whatsscan.llm")

ROOT = Path("/mnt/ssd_trabajo/hermes-agent")

# Cadena de fallback (decisión del Líder 2026-09-10)
DEFAULT_CHAIN = [
    ("deepseek/deepseek-v4-flash", "openrouter"),
    ("z-ai/glm-5.3", "openrouter"),
    ("z-ai/glm-5.2:free", "openrouter"),
    ("qwen2.5:7b", "ollama"),
]

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OLLAMA_URL = "http://localhost:11434"

TIMEOUT_OR = 120
TIMEOUT_OL = 300


def _load_env() -> None:
    env_path = ROOT / "config" / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())


_load_env()


def _chain_from_env() -> list[tuple[str, str]]:
    """Permite override por WHATSSCAN_LLM_* en .env."""
    chain: list[tuple[str, str]] = []
    mapping = [
        ("WHATSSCAN_LLM_PRIMARY", "openrouter"),
        ("WHATSSCAN_LLM_FALLBACK_1", "openrouter"),
        ("WHATSSCAN_LLM_FALLBACK_2", "openrouter"),
        ("WHATSSCAN_LLM_FALLBACK_3", "ollama"),
    ]
    for var, backend in mapping:
        val = os.environ.get(var, "").strip()
        if val:
            chain.append((val, backend))
    return chain or DEFAULT_CHAIN


def summarize_chat(
    contact_name: str | None,
    phone: str | None,
    messages: list[dict[str, Any]],
    production: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Resumen del chat completo recorriendo la cadena de fallback.

    Returns: {"summary": str, "tier": "deepseek/deepseek-v4-flash",
              "backend": "openrouter", "elapsed_s": float}
    Raises RuntimeError si TODA la cadena falla.
    """
    chat_text = _format_messages(messages)
    prompt = (
        "Resumí esta conversación de WhatsApp de una distribuidora de agua "
        "(Estación H2O, Maracaibo). Respondé SOLO JSON con claves: "
        '"tema" (string breve), "pedidos_resumen" (string), '
        '"pagos_resumen" (string), "problemas_resumen" (string), '
        '"accion_siguiente" (string).\n\n'
        f"Contacto: {contact_name or 'desconocido'} ({phone or 'sin teléfono'})\n"
        f"Datos detectados por regex: {json.dumps(production or {}, ensure_ascii=False)}\n\n"
        f"CONVERSACIÓN:\n{chat_text}"
    )
    return _run_chain(prompt)


def _format_messages(messages: list[dict[str, Any]], max_chars: int = 60000) -> str:
    lines = []
    total = 0
    for m in messages:
        ts = m.get('timestamp', '?')
        sn = m.get('sender_name', '?')
        tx = m.get('message_text', '')
        line = f"[{ts}] {sn}: {tx}"
        if total + len(line) > max_chars:
            lines.append("... (truncado, historial extenso)")
            break
        lines.append(line)
        total += len(line)
    return "\n".join(lines)


def _run_chain(prompt: str) -> dict[str, Any]:
    last_err: Exception | None = None
    for model, backend in _chain_from_env():
        t0 = time.time()
        try:
            text = _call(model, backend, prompt)
            elapsed = time.time() - t0
            logger.info("LLM tier usado: %s (%s) en %.1fs", model, backend, elapsed)
            return {
                "summary": text,
                "tier": model,
                "backend": backend,
                "elapsed_s": round(elapsed, 1),
            }
        except Exception as e:  # noqa: BLE001 — cadena de fallback
            last_err = e
            logger.warning("tier %s (%s) FALLÓ: %s — paso al siguiente",
                           model, backend, e)
    raise RuntimeError(f"toda la cadena LLM falló: {last_err}")


def _call(model: str, backend: str, prompt: str) -> str:
    if backend == "openrouter":
        return _call_openrouter(model, prompt)
    return _call_ollama(model, prompt)


def _call_openrouter(model: str, prompt: str) -> str:
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY no configurada")
    r = requests.post(
        OPENROUTER_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
            "max_tokens": 1024,
        },
        timeout=TIMEOUT_OR,
    )
    r.raise_for_status()
    data = r.json()
    return data["choices"][0]["message"]["content"].strip()


def _call_ollama(model: str, prompt: str) -> str:
    r = requests.post(
        f"{OLLAMA_URL}/api/chat",
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "options": {"temperature": 0.3},
        },
        timeout=TIMEOUT_OL,
    )
    r.raise_for_status()
    return r.json()["message"]["content"].strip()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    # smoke test: resumen mínimo
    out = summarize_chat(
        "Test", "+584120000000",
        [{"timestamp": "2026-09-01T10:00:00", "sender_name": "Luis",
          "message_text": "Quiero 2 botellones y pago por PagoMovil"}],
    )
    print(json.dumps(out, ensure_ascii=False, indent=2))
