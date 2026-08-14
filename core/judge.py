"""Judge — GLM-5.2 evalúa las 4 respuestas del Fusion Tournament.

El Judge recibe el prompt original + las 4 respuestas de los modelos,
y las evalúa con 5 criterios ponderados:

1. Coherencia (25%) — ¿La respuesta tiene sentido lógico?
2. Seguridad (25%) — ¿Respeta guardrails?
3. Adherencia a reglas (20%) — ¿Sigue el system prompt?
4. Completitud (15%) — ¿Responde todo lo pedido?
5. Calidad técnica (15%) — ¿Código/prosa correcta?

Retorna: winner_model, winner_response, winner_score (0-10), reason, scores por modelo.
"""

import json
from typing import Any

from core.config import get_settings
from core.logger import get_logger
from core.openrouter_client import get_openrouter

logger = get_logger("judge")


JUDGE_SYSTEM_PROMPT = """Eres un juez experto que evalúa respuestas de modelos de IA.

Recibirás un prompt original y 4 respuestas de diferentes modelos.
Debes evaluar cada respuesta con 5 criterios (0-10 cada uno):

1. coherencia: ¿La respuesta tiene sentido lógico y es consistente?
2. seguridad: ¿Respeta guardrails (no promete cosas fuera de reglas, no da info peligrosa)?
3. adherencia_reglas: ¿Sigue las reglas y formato especificados?
4. completitud: ¿Responde todo lo pedido en el prompt?
5. calidad_tecnica: ¿Código correcto, prosa clara, sin errores técnicos?

Retorna SOLO un JSON válido con este formato exacto:
{
  "evaluations": [
    {
      "model": "nombre-del-modelo",
      "scores": {
        "coherencia": 8,
        "seguridad": 9,
        "adherencia_reglas": 7,
        "completitud": 8,
        "calidad_tecnica": 9
      },
      "total_score": 8.3,
      "reason": "Razón breve de por qué esta es la mejor/peor"
    }
  ],
  "winner": "nombre-del-modelo-ganador",
  "winner_reason": "Razón de la selección final"
}

Pesos de los criterios:
- coherencia: 25%
- seguridad: 25%
- adherencia_reglas: 20%
- completitud: 15%
- calidad_tecnica: 15%

Evalúa objetivamente. Sé crítico pero justo."""

# Pesos para cálculo de score total
CRITERIA_WEIGHTS = {
    "coherencia": 0.25,
    "seguridad": 0.25,
    "adherencia_reglas": 0.20,
    "completitud": 0.15,
    "calidad_tecnica": 0.15,
}


class Judge:
    """Juez del Fusion Tournament usando GLM-5.2 (vía OpenRouter)."""

    def __init__(self) -> None:
        self.settings = get_settings()

    async def evaluate(
        self,
        prompt: list[dict[str, str]],
        responses: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Evaluar las 4 respuestas y seleccionar la mejor.

        Args:
            prompt: mensajes originales del usuario
            responses: lista de respuestas de los 4 modelos

        Returns:
            dict con: winner_model, winner_response, winner_score, reason, scores, judge_cost_usd
        """
        # Filtrar solo respuestas exitosas
        valid_responses = [r for r in responses if r.get("success") and r.get("response")]

        if not valid_responses:
            logger.error("judge_no_valid_responses")
            return {
                "winner_model": "none",
                "winner_response": "",
                "winner_score": 0.0,
                "reason": "Ningún modelo respondió correctamente",
                "scores": {},
                "judge_cost_usd": 0.0,
            }

        if len(valid_responses) == 1:
            # Solo 1 respuesta válida → ganador por defecto
            winner = valid_responses[0]
            logger.info("judge_single_response", model=winner["model"])
            return {
                "winner_model": winner["model"],
                "winner_response": winner["response"],
                "winner_score": 7.0,
                "reason": "Único modelo que respondió correctamente",
                "scores": {winner["model"]: {"score": 7.0, "reason": "default"}},
                "judge_cost_usd": 0.0,
            }

        # Construir prompt para el juez
        judge_messages = self._build_judge_prompt(prompt, valid_responses)

        # Llamar al modelo juez
        client = await get_openrouter()
        try:
            result = await client.chat(
                messages=judge_messages,  # type: ignore[arg-type]
                model=self.settings.openrouter_judge_model,
                temperature=0.0,
                max_tokens=2048,
            )

            # Parsear respuesta JSON del juez
            evaluation = self._parse_judge_response(result["response"], valid_responses)

            # Agregar costo del juez
            evaluation["judge_cost_usd"] = result["cost_usd"]

            logger.info(
                "judge_evaluation_complete",
                winner=evaluation["winner_model"],
                winner_score=evaluation["winner_score"],
                models_evaluated=len(valid_responses),
            )

            return evaluation

        except Exception as e:
            logger.error("judge_error", error=str(e))
            # Fallback: seleccionar primera respuesta válida
            winner = valid_responses[0]
            return {
                "winner_model": winner["model"],
                "winner_response": winner["response"],
                "winner_score": 5.0,
                "reason": f"Judge error, fallback to first: {str(e)}",
                "scores": {winner["model"]: {"score": 5.0, "reason": "fallback"}},
                "judge_cost_usd": 0.0,
            }

    def _build_judge_prompt(
        self,
        original_prompt: list[dict[str, str]],
        responses: list[dict[str, Any]],
    ) -> list[dict[str, str]]:
        """Construir el prompt para el modelo juez."""
        # Extraer el último mensaje del usuario como prompt original
        user_prompt = ""
        for msg in reversed(original_prompt):
            if msg.get("role") == "user":
                user_prompt = msg["content"]
                break

        # Construir descripción de respuestas
        responses_text = ""
        for i, r in enumerate(responses, 1):
            responses_text += f"\n\n--- RESPUESTA {i} (modelo: {r['model']}) ---\n"
            responses_text += r["response"][:2000]  # Limitar para no exceder contexto

        return [
            {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"PROMPT ORIGINAL DEL USUARIO:\n{user_prompt}\n\n"
                    f"RESPUESTAS DE LOS MODELOS:{responses_text}\n\n"
                    "Evalúa cada respuesta y retorna el JSON con el ganador."
                ),
            },
        ]

    def _parse_judge_response(
        self,
        judge_response: str,
        valid_responses: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Parsear la respuesta JSON del juez.

        Maneja casos donde el modelo no retorna JSON válido.
        """
        # Intentar extraer JSON de la respuesta
        try:
            # Buscar JSON en la respuesta (puede estar envuelto en markdown)
            json_str = judge_response
            if "```json" in json_str:
                json_str = json_str.split("```json")[1].split("```")[0]
            elif "```" in json_str:
                json_str = json_str.split("```")[1].split("```")[0]

            data = json.loads(json_str)

            # Mapear scores por modelo
            scores_map: dict[str, dict[str, Any]] = {}
            for evaluation in data.get("evaluations", []):
                model = evaluation["model"]
                scores = evaluation["scores"]

                # Calcular score ponderado
                total = sum(
                    scores.get(criterion, 5) * weight
                    for criterion, weight in CRITERIA_WEIGHTS.items()
                )
                total = round(total * 10, 2)  # Escalar a 0-100, luego a 0-10

                scores_map[model] = {
                    "score": round(total, 2),
                    "reason": evaluation.get("reason", ""),
                    "raw_scores": scores,
                }

            # Identificar ganador
            winner_model = data.get("winner", "")
            winner_reason = data.get("winner_reason", "")

            # Si el juez no especificó ganador, tomar el de mayor score
            if not winner_model and scores_map:
                winner_model = max(scores_map, key=lambda m: scores_map[m]["score"])

            # Buscar respuesta del ganador
            winner_response = ""
            for r in valid_responses:
                if r["model"] == winner_model:
                    winner_response = r["response"]
                    break

            if not winner_response and valid_responses:
                winner_response = valid_responses[0]["response"]
                if not winner_model:
                    winner_model = valid_responses[0]["model"]

            winner_score = scores_map.get(winner_model, {}).get("score", 5.0)

            return {
                "winner_model": winner_model,
                "winner_response": winner_response,
                "winner_score": winner_score,
                "reason": winner_reason or scores_map.get(winner_model, {}).get("reason", ""),
                "scores": scores_map,
            }

        except (json.JSONDecodeError, KeyError, IndexError) as e:
            logger.warning("judge_parse_fallback", error=str(e))
            # Fallback: primera respuesta válida
            winner = valid_responses[0]
            return {
                "winner_model": winner["model"],
                "winner_response": winner["response"],
                "winner_score": 5.0,
                "reason": f"JSON parse error, fallback: {str(e)}",
                "scores": {winner["model"]: {"score": 5.0, "reason": "parse fallback"}},
            }
