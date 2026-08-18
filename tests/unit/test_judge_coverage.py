"""Tests unitarios para cubrir las lineas sin cobertura de core/judge.py.

Cubre:
- _parse_judge_response con JSON envuelto en ``` (no ```json) (linea 210)
- _parse_judge_response sin winner especificado → max score (linea 239)
- _parse_judge_response con winner que no esta en valid_responses → fallback (lineas 249-251)
"""

import os
import sys

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.judge import Judge


@pytest.fixture
def judge():
    return Judge()


class TestParseJudgeResponseCodeFences:
    def test_plain_code_fence_not_json(self, judge):
        """JSON envuelto en ``` (no ```json) → parsea correctamente (linea 210)."""
        judge_response = """```
{
  "evaluations": [
    {
      "model": "z-ai/glm-4.5",
      "scores": {
        "coherencia": 8, "seguridad": 9, "adherencia_reglas": 7,
        "completitud": 8, "calidad_tecnica": 9
      },
      "reason": "Buena"
    }
  ],
  "winner": "z-ai/glm-4.5",
  "winner_reason": "Mejor respuesta"
}
```"""

        responses = [{"model": "z-ai/glm-4.5", "response": "4"}]

        result = judge._parse_judge_response(judge_response, responses)

        assert result["winner_model"] == "z-ai/glm-4.5"
        assert result["winner_response"] == "4"
        assert result["winner_score"] > 0


class TestParseJudgeResponseNoWinner:
    def test_no_winner_takes_max_score(self, judge):
        """Si el juez no especifica winner → tomar el de mayor score (linea 239)."""
        judge_response = """{
  "evaluations": [
    {
      "model": "z-ai/glm-4.5",
      "scores": {
        "coherencia": 6, "seguridad": 7, "adherencia_reglas": 6,
        "completitud": 6, "calidad_tecnica": 7
      },
      "reason": "Regular"
    },
    {
      "model": "anthropic/claude-sonnet-4.5",
      "scores": {
        "coherencia": 9, "seguridad": 9, "adherencia_reglas": 9,
        "completitud": 9, "calidad_tecnica": 9
      },
      "reason": "Excelente"
    }
  ]
}"""

        responses = [
            {"model": "z-ai/glm-4.5", "response": "Respuesta regular"},
            {"model": "anthropic/claude-sonnet-4.5", "response": "Respuesta excelente"},
        ]

        result = judge._parse_judge_response(judge_response, responses)

        # El ganador debe ser el de mayor score (claude)
        assert result["winner_model"] == "anthropic/claude-sonnet-4.5"
        assert result["winner_response"] == "Respuesta excelente"
        assert result["winner_score"] > result["scores"]["z-ai/glm-4.5"]["score"]


class TestParseJudgeResponseWinnerNotFound:
    def test_winner_not_in_valid_responses(self, judge):
        """Winner especificado pero no esta en valid_responses → fallback (lineas 249-251)."""
        judge_response = """{
  "evaluations": [
    {
      "model": "z-ai/glm-4.5",
      "scores": {
        "coherencia": 8, "seguridad": 9, "adherencia_reglas": 7,
        "completitud": 8, "calidad_tecnica": 9
      },
      "reason": "Buena"
    }
  ],
  "winner": "nonexistent-model",
  "winner_reason": "Modelo fantasma"
}"""

        responses = [{"model": "z-ai/glm-4.5", "response": "4"}]

        result = judge._parse_judge_response(judge_response, responses)

        # winner_response debe caer al primer valid_response
        assert result["winner_response"] == "4"
        # winner_model sigue siendo "nonexistent-model" (especificado por el juez)
        assert result["winner_model"] == "nonexistent-model"

    def test_no_winner_and_empty_scores(self, judge):
        """Sin winner y scores_map vacio → fallback con score 5.0."""
        judge_response = """{
  "evaluations": []
}"""

        responses = [{"model": "z-ai/glm-4.5", "response": "4"}]

        result = judge._parse_judge_response(judge_response, responses)

        # scores_map vacio, winner_model vacio → fallback a primer valid_response
        assert result["winner_model"] == "z-ai/glm-4.5"
        assert result["winner_response"] == "4"
        assert result["winner_score"] == 5.0
