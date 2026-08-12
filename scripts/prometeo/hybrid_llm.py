#!/usr/bin/env python3
"""
 ============================================================================
 Plan Híbrido LLM — 3 capas con fallback automático
 Estación H2O · Prometeo
 ============================================================================

Estrategia:
1. Nemotron 3 Ultra (primario) — mejor modelo, free credits
2. GLM 5.2 (backup 1) — excelente en español venezolano
3. DeepSeek V4 Pro (backup 2) — respaldo final

Comportamiento:
- Intenta primario → si falla, prueba backups en orden
- Tras trabajo exitoso con backup, ping primario → si responde, vuelve
- Cooldown 5 min tras fallo de cada provider
"""

import logging
import os
import time
import random
from openai import OpenAI, RateLimitError, APIStatusError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("hybrid_llm")

# ============================================================================
# Configuración de los 3 providers (todos vía NVIDIA NIM)
# ============================================================================

NIM_BASE_URL = "https://integrate.api.nvidia.com/v1"

PROVIDERS = [
    {
        "name": "Nemotron",
        "api_key": "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",
        "model": "nvidia/nemotron-3-ultra-550b-a55b",
        "display": "Nemotron 3 Ultra",
    },
    {
        "name": "GLM",
        "api_key": os.getenv(
            "NVIDIA_API_KEY",
            "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",
        ),
        "model": "z-ai/glm-5.2",
        "display": "GLM 5.2",
    },
    {
        "name": "DeepSeek",
        "api_key": "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",
        "model": "deepseek-ai/deepseek-v4-pro",
        "display": "DeepSeek V4 Pro",
    },
]

COOLDOWN_SECONDS = 300  # 5 min


class HybridLLM:
    """Cliente LLM con fallback automático de 3 capas."""

    def __init__(self):
        self.current_provider_idx = 0  # arrancamos con Nemotron (índice 0)
        self.failures = {p["name"]: 0 for p in PROVIDERS}
        self.last_failure_time: dict[str, float] = {p["name"]: 0.0 for p in PROVIDERS}
        self.clients = {}
        for p in PROVIDERS:
            if p["api_key"]:
                self.clients[p["name"]] = OpenAI(base_url=NIM_BASE_URL, api_key=p["api_key"])

        if not self.clients:
            raise RuntimeError("No hay API keys configuradas")

        logger.info(f"Hibrido inicializado: {len(self.clients)} providers")
        for i, p in enumerate(PROVIDERS):
            status = "✅" if p["name"] in self.clients else "❌"
            logger.info(f"  {i+1}. {status} {p['display']} ({p['model']})")

    def _try_provider(self, idx: int, messages: list, max_retries: int = 3, **kwargs) -> str | None:
        """Intenta un provider específico con reintentos y backoff. Retorna respuesta o None."""
        if idx >= len(PROVIDERS):
            return None

        p = PROVIDERS[idx]
        client = self.clients.get(p["name"])
        if not client:
            return None

        # Verificar cooldown
        if time.time() - self.last_failure_time[p["name"]] < COOLDOWN_SECONDS:
            return None

        for attempt in range(max_retries):
            try:
                completion = client.chat.completions.create(
                    model=p["model"], messages=messages, **kwargs
                )
                return completion.choices[0].message.content
            except (RateLimitError, APIStatusError) as e:
                # Detectar ResourceExhausted (429/quota exhausted)
                is_resource_exhausted = (
                    isinstance(e, RateLimitError) or
                    (isinstance(e, APIStatusError) and 
                     ("ResourceExhausted" in str(e) or 
                      "quota" in str(e).lower() or
                      "limit reached" in str(e).lower()))
                )
                
                if is_resource_exhausted and attempt < max_retries - 1:
                    wait_time = 120 + random.randint(0, 30)  # 120-150s con jitter
                    logger.warning(
                        f"{p['display']} quota agotada (intento {attempt + 1}/{max_retries}). "
                        f"Esperando {wait_time}s antes de reintentar..."
                    )
                    time.sleep(wait_time)
                    continue  # Reintentar
                
                # Otros errores de rate limit o errores no recuperables
                logger.warning(f"{p['display']} fallo: {str(e)[:200]}")
                self.failures[p["name"]] += 1
                self.last_failure_time[p["name"]] = time.time()
                return None
            except Exception as e:
                logger.warning(f"{p['display']} fallo: {str(e)[:200]}")
                self.failures[p["name"]] += 1
                self.last_failure_time[p["name"]] = time.time()
                return None
        
        return None

    def _ping_provider(self, idx: int) -> bool:
        """Ping rápido a un provider."""
        p = PROVIDERS[idx]
        client = self.clients.get(p["name"])
        if not client:
            return False
        try:
            client.chat.completions.create(
                model=p["model"], messages=[{"role": "user", "content": "ping"}], max_tokens=5
            )
            return True
        except Exception:
            return False

    def chat(self, prompt: str, system: str = None, **kwargs) -> str:
        """Chat con fallback automático de 3 capas."""
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        # Intentar provider actual
        response = self._try_provider(self.current_provider_idx, messages, **kwargs)
        if response:
            logger.info(f"OK: {PROVIDERS[self.current_provider_idx]['display']}")
            return response

        # Fallback: probar los otros 2 en orden
        logger.warning(f"Fallback: {PROVIDERS[self.current_provider_idx]['display']} fallo")
        for i in range(len(PROVIDERS)):
            if i == self.current_provider_idx:
                continue
            response = self._try_provider(i, messages, **kwargs)
            if response:
                logger.info(f"OK fallback: {PROVIDERS[i]['display']}")
                _old_idx = self.current_provider_idx
                self.current_provider_idx = i

                # Post-trabajo: ping al primario original
                if i != 0 and self._ping_provider(0):
                    logger.info(f"Primario ({PROVIDERS[0]['display']}) volvio")
                    self.current_provider_idx = 0
                    self.last_failure_time[PROVIDERS[0]["name"]] = 0

                return response

        raise RuntimeError("Todos los providers fallaron")

    def status(self) -> dict:
        """Estado actual del cliente híbrido."""
        current = PROVIDERS[self.current_provider_idx]
        return {
            "current_provider": current["display"],
            "current_model": current["model"],
            "providers_available": list(self.clients.keys()),
            "failures": dict(self.failures),
            "in_cooldown": [
                p["name"]
                for p in PROVIDERS
                if time.time() - self.last_failure_time[p["name"]] < COOLDOWN_SECONDS
            ],
        }


# ============================================================================
# Test
# ============================================================================

if __name__ == "__main__":
    from pathlib import Path

    env_path = Path.home() / ".hermes" / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                os.environ.setdefault(key.strip(), val.strip())

    print(f"\n{'='*60}")
    print("TEST SISTEMA HÍBRIDO 3 CAPAS")
    print(f"{'='*60}\n")

    llm = HybridLLM()
    print("\nEstado inicial:")
    print(llm.status())

    print(f"\n{'='*60}")
    print("Test chat:")
    print(f"{'='*60}\n")

    response = llm.chat(
        "Confirma que recibes el mensaje. Eres Prometeo, "
        "asistente de Luis Martinez. Saluda brevemente.",
        system="Eres Prometeo, ingeniero senior. Tono venezolano, firma 💧.",
        max_tokens=200,
        temperature=0.7,
    )
    print(f"\nRespuesta:\n{response}")

    print(f"\n{'='*60}")
    print("Estado final:")
    print(llm.status())
    print(f"{'='*60}")
