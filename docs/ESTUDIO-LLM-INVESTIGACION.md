# ESTUDIO — Mejor LLM vía OpenRouter para la investigación de los 4 hermanos

**Fecha:** 2026-10-11 · **Autor:** ZCode (diseño/arquitectura) · **Decisión del Líder:**
las misiones las ejecuta HERMES AGENT con modelo por API (OpenRouter); el modelo
local queda descartado como investigador de cimientos ("es un error").

## Requisitos del cargo
1. **Investigación bibliográfica científica** por lotes (pensum UCV/UFV), con regla
   anti-invento y citas verificadas.
2. **Resumir sin perder información**: fidelidad a datos cuantitativos (tablas,
   constantes, rangos) — VERIFICADO EN VIVO con deepseek-v4-flash (test THI/leche:
   conservó el 100% de los números).
3. Contexto largo: los lotes leen documentos/PDFs completos.
4. Uso nocturno desatendido: barato por volumen, estable, con respaldo.

## Precios verificados EN VIVO del catálogo OpenRouter (2026-10-11, USD/1M tokens)

| Modelo | Input | Output | Contexto | Observación |
|---|---|---|---|---|
| **deepseek/deepseek-v4-flash** | **$0.030** | **$1.280** | 1M | ⭐ RECOMENDADO primario |
| z-ai/glm-5.3-flash | $0.150 | $0.500 | 1M | ⭐ respaldo (casa) |
| deepseek/deepseek-v4-pro | $0.209 | $0.418 | 1M | promo/off-peak vigente |
| deepseek/deepseek-v4.1-flash | $0.300 | $1.200 | 1M | |
| z-ai/glm-5.3-flashx | $0.370 | $1.250 | 1M | |
| z-ai/glm-5.3 (técnico actual) | $0.039 | $4.800 | 1M | in barato, OUT caro: mal para apuntes largos |
| moonshotai/kimi-k2.5 | $0.500 | $2.500 | 262K | agente fuerte, ctx corto |
| google/gemini-3-flash-preview | $0.500 | $3.000 | 1M | opción premium fidelidad |
| google/gemini-3.6-flash | $0.750 | $3.750 | 1M | |
| anthropic/claude-sonnet-5 | $2.000 | $10.000 | 1M | hitos de síntesis solamente |
| openai/gpt-5.2 | $1.750 | $14.000 | 400K | no se justifica aquí |

Nota: deepseek-v4-flash es **razonador** — el thinking consume tokens de salida,
por eso llm_client le da `max_tokens_default: 16000` (bug encontrado y corregido
en la prueba: con 200 tokens devolvía content vacío).

## Carga semanal y costo (28 jornadas = 4 hermanos × 7 noches)

Supuestos por jornada agéntica (prompt + documentos leídos + contexto reenviado
en el bucle + apuntes/hechos generados):

| Escenario | por jornada | tokens/semana |
|---|---|---|
| Ligero | 150k in / 20k out | 4.2M in / 0.56M out |
| **Medio (planeado)** | **400k in / 40k out** | **11.2M in / 1.12M out** |
| Pesado | 800k in / 80k out | 22.4M in / 2.24M out |

### Costo semanal USD (incluye fee 5.5% de créditos OpenRouter)

| Modelo | Ligero | **Medio** | Pesado |
|---|---|---|---|
| deepseek-v4-flash | $0.89 | **$1.87** | $3.74 |
| glm-5.3-flash | $0.96 | **$2.36** | $4.73 |
| deepseek-v4-pro | $1.19* | **$2.96** | $5.92 |
| glm-5.3-flashx | $2.34 | **$5.85** | $11.70 |
| kimi-k2.5 | $3.54 | **$8.86** | $17.72 |
| gemini-3-flash-preview | $3.99 | **$9.45** | $18.91 |
| gemini-3.6-flash | $5.30 | **$13.29** | $26.57 |
| **gpt-5.2** | $14.88 | **$37.22** | $74.44 |
| **claude-sonnet-5** | $14.17 | **$35.45** | $70.91 |

*pro promocional; el precio "peak" documentado llega a ~$19/sem medio.

## Recomendación (instalada)

- **Primario: `deepseek/deepseek-v4-flash`** — mejor calidad-precio del mercado
  para este cargo: 1M contexto, calidad agéntica creciente (OpenRouter reporta
  ganancia real de share agéntico en V4), fidelidad numérica probada en vivo, y
  ~$1.9/semana a carga media (hasta $3.7 en pesada). Costo de oportunidad del
  local (qwen): $0 pero sin capacidad agéntica real (noche 10-10 lo demostró).
- **Respaldo: `z-ai/glm-5.3-flash`** — mismo proveedor de la casa, 1M ctx,
  $2.4-4.7/sem. Si DeepSeek cae o sube de precio, no se detiene la noche.
- **Premium opcional (no cableado): `google/gemini-3-flash-preview`** — si la
  validación detectara pérdida de fidelidad en resúmenes muy largos, es el
  siguiente escalón ($9.5-19/sem). Claude Sonnet 5 / GPT-5.2 solo para hitos de
  síntesis trimestrales puntuales, no para la rutina nocturna.

## Cableado (ya instalado)

- `scripts/llm_client.py`: tier `task_type="research"` con cadena
  deepseek-v4-flash → glm-5.3-flash (timeout 600s, 16k tokens default).
- `config/.env`: `OPENROUTER_MODEL_RESEARCH` / `OPENROUTER_MODEL_RESEARCH_BACKUP`.
- `scripts/misiones/mision_nocturna.py --ejecutar <hermano-id>`: Hermes ejecuta
  la misión del hermano (prompt del plan + lote/jornada actual) vía tier research;
  salida a `harvest-bibliografica/lotes/<fecha>-<nombre>.log` con tier/modelo
  anotados. ZCode despacha, vigila y valida (dos ojos).
- Presupuesto observado: el costo real por jornada queda registrado en usage
  (llm_client lo loguea); la validación matutina puede acumularlo para alertar
  si el gasto semanal se desvía >30% de lo planeado.

## Fuentes
- Catálogo OpenRouter en vivo (api/v1/models, 2026-10-11) — precios usados.
- OpenRouter: "DeepSeek V4 Is Earning Agentic Token Share" (jul-2026).
- Fireworks "Best LLMs for coding 2026" (AA Coding Index V4-Pro vs Kimi K2.6).
- VentureBeat: Sonnet 4.6 $3/$15; Sonnet 5 (jun-2026) $2/$10.
- Introl/Evolink: GPT-5.2 (400K ctx) vs Gemini 3 Pro (1M ctx) benchmarks.
