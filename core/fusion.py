"""Fusion Tournament — 4 modelos compiten en paralelo.

Lanza los 4 modelos de OpenRouter simultáneamente con asyncio.gather,
recolecta las 4 respuestas, y las pasa al Judge (GLM-5.2) para evaluación.

El Judge retorna la mejor respuesta + score + razón.

Si score ganador < FUSION_MIN_SCORE (7.0), se escala a humano.
"""

import asyncio
from typing import Any

from core.config import get_settings
from core.judge import Judge
from core.logger import get_logger
from core.openrouter_client import get_openrouter

logger = get_logger("fusion")


class FusionTournament:
    """Orquestador del tournament de 4 modelos."""

    def __init__(self) -> None:
        self.judge = Judge()
        self.settings = get_settings()

    async def run(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 1024,
    ) -> dict[str, Any]:
        """Ejecutar tournament completo.

        Args:
            messages: prompt del usuario [{role, content}, ...]
            temperature: temperatura para los 4 modelos
            max_tokens: máximo tokens de respuesta

        Returns:
            dict con:
                - winner_response: mejor respuesta
                - winner_model: modelo ganador
                - score: score 0-10
                - reason: razón de la selección
                - all_responses: las 4 respuestas + scores
                - total_cost_usd: costo total del tournament
        """
        models = self.settings.fusion_models_list
        logger.info("fusion_tournament_start", models=models, message_count=len(messages))

        # 1. Lanzar 4 modelos en paralelo
        responses = await self._run_models_parallel(models, messages, temperature, max_tokens)

        # 2. Judge evalúa las 4 respuestas
        judgment = await self.judge.evaluate(prompt=messages, responses=responses)

        # 3. Calcular costo total
        total_cost = sum(r.get("cost_usd", 0) for r in responses if r.get("success"))
        total_cost += judgment.get("judge_cost_usd", 0)

        # 4. Verificar si score < mínimo → escalar a humano
        needs_human = judgment["winner_score"] < self.settings.fusion_min_score

        logger.info(
            "fusion_tournament_complete",
            winner_model=judgment["winner_model"],
            winner_score=judgment["winner_score"],
            needs_human=needs_human,
            total_cost_usd=round(total_cost, 6),
            successful_responses=sum(1 for r in responses if r.get("success")),
        )

        return {
            "winner_response": judgment["winner_response"],
            "winner_model": judgment["winner_model"],
            "score": judgment["winner_score"],
            "reason": judgment["reason"],
            "needs_human_escalation": needs_human,
            "all_responses": [
                {
                    "model": r["model"],
                    "response": r.get("response", ""),
                    "success": r.get("success", False),
                    "error": r.get("error"),
                    "cost_usd": r.get("cost_usd", 0),
                    "score": judgment["scores"].get(r["model"], {}).get("score", 0),
                }
                for r in responses
            ],
            "total_cost_usd": round(total_cost, 6),
        }

    async def _run_models_parallel(
        self,
        models: list[str],
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
    ) -> list[dict[str, Any]]:
        """Ejecutar todos los modelos en paralelo con asyncio.gather.

        Usa return_exceptions=True para que si un modelo falla,
        los otros continúen.
        """
        client = await get_openrouter()

        tasks = [
            client.chat(messages=messages, model=m, temperature=temperature, max_tokens=max_tokens)
            for m in models
        ]

        results_raw = await asyncio.gather(*tasks, return_exceptions=True)

        responses: list[dict[str, Any]] = []
        for model, result in zip(models, results_raw, strict=True):
            if isinstance(result, Exception):
                logger.warning(
                    "fusion_model_error",
                    model=model,
                    error=str(result),
                )
                responses.append(
                    {
                        "model": model,
                        "success": False,
                        "error": str(result),
                        "response": "",
                        "cost_usd": 0.0,
                    }
                )
            else:
                responses.append(
                    {
                        "model": model,
                        "success": True,
                        "response": result["response"],  # type: ignore[index]
                        "cost_usd": result["cost_usd"],  # type: ignore[index]
                        "usage": result["usage"],  # type: ignore[index]
                    }
                )

        return responses


# Singleton
_fusion_instance: FusionTournament | None = None


def get_fusion() -> FusionTournament:
    """Obtener instancia singleton del Fusion Tournament."""
    global _fusion_instance
    if _fusion_instance is None:
        _fusion_instance = FusionTournament()
    return _fusion_instance
