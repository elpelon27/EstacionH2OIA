# Cadena de Fallback LLM — 3 Tiers con Routing por Tipo de Tarea

Estado: IMPLEMENTADO · 2026-09-02 · `scripts/llm_client.py`

## Diseño

`LLMClient` (en `scripts/llm_client.py`) implementa una cadena de fallback
de 3 tiers que se intentan en orden hasta que uno responda:

| # | Tier | Modelo | Endpoint | Técnico | Chat |
|---|------|--------|----------|---------|------|
| 1 | `glm-5.3-paid` | `z-ai/glm-5.3` | OpenRouter | ✅ | ✅ |
| 2 | `glm-5.2-free` | `z-ai/glm-5.2:free` | OpenRouter | ✅ | ✅ |
| 3 | `ollama-local` | `qwen2.5:7b` | `http://localhost:11434/v1` | ❌ | ✅ |

### Routing por tipo de tarea

- `complete(messages, task_type='chat')` — puede usar cualquiera de los 3 tiers.
- `complete(messages, task_type='technical')` — SOLO tiers 1 y 2 (pagados).
  Si ambos fallan (p. ej. HTTP 402 sin créditos), retorna:
  ```json
  {"error": "NO_PAID_LLM_AVAILABLE",
   "message": "Sin créditos en OpenRouter. Para tareas técnicas necesito
              GLM 5.3 pagado o GLM 5.2 free. Agregá créditos en
              https://openrouter.ai/settings/credits"}
  ```

### Detección de tarea técnica (heurística)

`detect_task_type(texto)` en `scripts/llm_client.py` marca `technical` si
aparece alguna keyword: arreglá/fix, modificá, escribí, creá, implementá,
refactor, cambiá el código, commit, push, desarrollá, script, función,
clase, método, editá el archivo, borrá, agregá al .env, sed -i, nano,
git, pr, merge, patch. Si no → `chat`.

## REGLA DEL LÍDER (grabada en piedra)

> **Ollama local = SOLO para chat conversacional.**
> NUNCA para: código, fixes, desarrollo, scripts, modificaciones al repo.
> Para tareas técnicas, RECHAZAR si no hay modelo pagado disponible.

Esto está forzado en código: el tier 3 tiene `technical_ok: False` y se
saltea para `task_type='technical'`, sin importar el estado de los créditos.

## Variables de entorno (config/.env)

```
OPENROUTER_API_KEY=your-openrouter-api-key-here
OPENROUTER_MODEL_PAID=z-ai/glm-5.3
OPENROUTER_MODEL_FREE=z-ai/glm-5.2:free
OLLAMA_MODEL=qwen2.5:7b
OLLAMA_BASE_URL=http://localhost:11434/v1
LLM_TIMEOUT=60
```

`llm_client.py` carga `config/.env` automáticamente (con `setdefault`, no
pisa variables ya presentes en el entorno).

## Logging

- Cada invocación OK: `LLM OK via <tier> model=<model> task_type=<t> latency=<s>`
- Cada fallo de tier: `LLM FAIL <tier>: <Excepción>`
- Tier fallado >5 veces en sesión: WARNING con el conteo
- Caída a Ollama en chat: INFO "modo degradado"
- Tarea técnica rechazada: WARNING "tarea técnica rechazada"

## Consumidores

- `scripts/prometeo/prometeo.py` — CLI Prometeo (migrado)
- `skills/prometeo_telegram.py` — Bot Telegram (migrado)

Ambos usan `LLMClient` + `detect_task_type` y devuelven el mensaje
`NO_PAID_LLM_AVAILABLE` al usuario cuando corresponde.
