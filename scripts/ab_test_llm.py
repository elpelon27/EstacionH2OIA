#!/usr/bin/env python3
"""A/B de modelos LLM para el chatflow de Valentina (misión 2026-10-09, API única OpenRouter).

Envía el mismo set de conversaciones REALES de la semana a un endpoint Dify
(chatflow producción o duplicado "Valentina-API-Test"), mide latencia por mensaje
y guarda transcripciones + métricas JSON para comparar candidatos:

    glm-4.7-flash vs glm-5.3-flash vs deepseek-chat  (vs qwen2.5:7b local = baseline)

Uso:
    venv/bin/python3 scripts/ab_test_llm.py --label local-qwen2.5           # baseline producción
    venv/bin/python3 scripts/ab_test_llm.py --label glm-4.7-flash \
        --api-url http://localhost/v1/chat-messages --api-key app-xxxx     # duplicado API-Test

El modelo lo define el nodo LLM del chatflow apuntado (se cambia en la consola
Dify entre corridas; este script no toca configuración). Gana el candidato MÁS
BARATO que cumpla: p95 < 8s, 0 salidas de formato, español/dirección correctos.

Salida: logs/ab_test/<timestamp>_<label>/  (transcripcion.txt + metricas.json)
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ENV_PATH = REPO / "config" / ".env"
OUT_DIR = REPO / "logs" / "ab_test"

# Conversaciones reales de la semana (misión §3.2): menú → pedido → dirección → pago.
# Cada conversación es una secuencia; se avanza solo si la respuesta del flujo es no-vacía.
CONVERSATIONS: list[list[str]] = [
    ["Buenas", "3 botellones", "Sector Tierra Negra avenida 13, entre calles 68 y 69, Lead Academy", "ya pague"],
    ["1", "quiero agua", "2 botellones", "ya pague"],
    ["mandame tres como la vez pasada"],
    ["no me llegó el recibo de la vez pasada"],
]


def load_env(key: str) -> str:
    with open(ENV_PATH, encoding="utf-8") as f:
        for line in f:
            if line.strip().startswith(f"{key}="):
                return line.strip().split("=", 1)[1].strip()
    raise SystemExit(f"FALTA {key} en config/.env")


def send(base_url: str, api_key: str, msg: str, conv_id: str | None) -> tuple[float, str, str]:
    """POST /v1/chat-messages (blocking mode). Devuelve (latencia_s, respuesta, conversation_id)."""
    payload = {
        "inputs": {},
        "query": msg,
        "response_mode": "blocking",
        "user": "ab-test-hermes",
        "auto_generate_name": False,
    }
    if conv_id:
        payload["conversation_id"] = conv_id
    req = urllib.request.Request(
        base_url,
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")[:500]
        raise RuntimeError(f"HTTP {e.code}: {body}") from e
    dt = time.monotonic() - t0
    answer = (data.get("answer") or "").strip()
    return dt, answer, data.get("conversation_id") or ""


def pct(values: list[float], p: float) -> float:
    if not values:
        return float("nan")
    s = sorted(values)
    k = max(0, min(len(s) - 1, round(p / 100 * (len(s) - 1))))
    return s[k]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True, help="etiqueta de la corrida (p.ej. local-qwen2.5, glm-4.7-flash)")
    ap.add_argument("--api-url", default=load_env("DIFY_API_URL"))
    ap.add_argument("--api-key", default=load_env("DIFY_API_KEY"))
    ap.add_argument("--repeats", type=int, default=1, help="repeticiones de todo el set")
    args = ap.parse_args()

    run_dir = OUT_DIR / f"{datetime.now():%Y%m%d_%H%M%S}_{args.label}"
    run_dir.mkdir(parents=True, exist_ok=True)

    latencies: list[float] = []
    errors: list[str] = []
    transcript_lines: list[str] = []
    print(f"=== A/B Valentina — corrida '{args.label}' contra {args.api_url} ===")

    for rep in range(args.repeats):
        for ci, convo in enumerate(CONVERSATIONS):
            conv_id = None
            transcript_lines.append(f"\n--- Conversación {ci + 1} (rep {rep + 1}) ---")
            for msg in convo:
                try:
                    dt, answer, conv_id_new = send(args.api_url, args.api_key, msg, conv_id)
                except Exception as e:  # noqa: BLE001 — registrar y seguir con la siguiente conversación
                    err = f"conversación {ci + 1} rep {rep + 1} tras '{msg[:30]}': {e}"
                    errors.append(err)
                    transcript_lines.append(f"[ERROR] {err}")
                    break
                latencies.append(dt)
                if conv_id_new and not conv_id:
                    conv_id = conv_id_new
                transcript_lines.append(f"CLIENTE> {msg}")
                transcript_lines.append(f"VALENTINA ({dt:.2f}s)> {answer}")

    metrics = {
        "label": args.label,
        "api_url": args.api_url,
        "n_messages": len(latencies),
        "n_errors": len(errors),
        "latency_s": {
            "mean": round(statistics.mean(latencies), 2) if latencies else None,
            "p50": round(pct(latencies, 50), 2) if latencies else None,
            "p95": round(pct(latencies, 95), 2) if latencies else None,
        },
        "p95_under_8s": bool(latencies) and pct(latencies, 95) < 8,
        "errors": errors,
    }
    (run_dir / "transcripcion.txt").write_text("\n".join(transcript_lines), encoding="utf-8")
    (run_dir / "metricas.json").write_text(json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(metrics, indent=2, ensure_ascii=False))
    print(f"Guardado en: {run_dir}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
