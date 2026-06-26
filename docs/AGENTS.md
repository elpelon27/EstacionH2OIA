---
doc: AGENTS
version: 0.1.0
last_updated: 2026-06-25
updated_by: hermes-agent
---

# AGENTS — Catálogo de agentes Hermes

## Agentes productivos (Qwen local)
### Valentina (recepcionista WhatsApp)
- Modelo: qwen2.5:7b (local)
- Propósito: Atención a clientes vía WhatsApp
- Memoria: mem0 (Qdrant)
- Personalidad: ver docs/SOUL.md
- Prompt: docs/prompts/valentina.v1.md
- Estado: ⏸️ Pendiente (BLOQUE 10.12)

### Financial Shield (pagos + BCV)
- Modelo: qwen2.5:7b (local)
- Estado: ⏸️ Pendiente (Fase 2)

### Dispatcher (logística + rutas)
- Modelo: qwen2.5:7b (local)
- Estado: ⏸️ Pendiente (Fase 2)

### Notifier (Telegram al Líder)
- Modelo: ninguno (solo lógica)
- Estado: ⏸️ Pendiente (BLOQUE 10.11)

## Agentes de desarrollo (OpenRouter)
### Architect (Claude Sonnet 4.5)
- Modelo: anthropic/claude-sonnet-4.5
- Estado: ⏸️ Pendiente (Fase 1)

### Coder (DeepSeek V3.2)
- Modelo: deepseek/deepseek-chat-v3.2
- Estado: ⏸️ Pendiente (Fase 1)

### Reviewer (Gemini 2.5 Flash)
- Modelo: google/gemini-2.5-flash
- Estado: ⏸️ Pendiente (Fase 1)

### Hermes (orquestador + Fusion)
- Modelo: Fusion Tournament (4 modelos + GLM-5.2 juez)
- Estado: ⏸️ Pendiente (BLOQUE 10.11)

## Workload Router
| Trigger | Target | Agente |
|---------|--------|--------|
| whatsapp_message | qwen_local | Valentina |
| payment_received | qwen_local | Financial |
| dispatch_request | qwen_local | Dispatcher |
| architect_request | fusion | Hermes |
| code_generation_complex | openrouter:deepseek | Coder |
| code_generation_critical | fusion | Hermes |
| rag_history_query | openrouter:gemini | Reviewer |
| log_summary_daily | openrouter:glm | Hermes |
| prompt_validation | fusion | Hermes |
| bug_diagnosis | fusion | Hermes |

## Fusion Tournament — Criterios
| Criterio | Peso |
|----------|------|
| Coherencia | 25% |
| Seguridad | 25% |
| Adherencia a reglas | 20% |
| Completitud | 15% |
| Calidad técnica | 15% |

Si score ganador < 7.0 → escalar a humano (Telegram al Líder)
