# 🛡️ R4/Agentes — Dictamen de Guardrails (evaluación técnica)

**Fecha**: 2026-08-13 · **Autor**: Prometeo · **Estado**: ANÁLISIS — sin cambios en producción
**Ámbito**: protección del stack de agentes (bridge :8000, Valentina WhatsApp, Dispatcher Telegram, pagos R4)

---

## 1. REALIDAD ACTUAL (verificada en servidor, no asumida)

| Capa | Qué hay activo | Tipo de defensa | Cubre |
|------|----------------|-----------------|-------|
| Hermes `tool_loop_guardrails` (config.yaml:64) | warnings + (opcional) hard stop | **Mecánica** (bucles de herramientas) | Loop infinito, failure repetido |
| `_sanitize_input_text` (bridge.py:736) | límite 2000 chars, borra ctrl chars, normaliza whitespace | **Bytes** (higiene de entrada) | Inyección de bytes, basura |
| `core/judge.py` "respetar guardrails" | solo criterio de rúbrica del evaluador | Ninguna | — (cosmético) |
| Librerías guardrails en venv | **NINGUNA instalada** | — | — |

> **Brecha real**: no hay barrera SEMÁNTICA sobre el modelo. Con webhooks
> (WhatsApp/Telegram = input hostil) + agentes autónomos + pagos bancarios,
> la inyección de prompt, fuga de secretos en salida y modulación de contenido
> están sin capa dedicada.

---

## 2. EVALUACIÓN DE LAS 4 OPCIONES PROPUESTAS

| Herramienta | Categoría REAL | Encaje en este stack | Verdict |
|-------------|----------------|----------------------|---------|
| **NVIDIA NeMo Guardrails** | Framework de "rails" (Colang) para gobernar comportamiento multiagente | Duplica control: el orquestador YA es Hermes. Overhead alto, integración competiría con SOUL/Hermes | ⚠️ NO prioritario |
| **Guardrails AI** | Validación de SALIDA (schemas/validadores) | Útil para forzar formatos en respuestas de pago; solapado con Pydantic que ya usamos | ⚠️ Secundario |
| **llm-guard (protectai)** | Sanitización entrada/salida: prompt-injection, secretos, PII, toxicidad | **Mejor ajuste**: ligero, escáneres puntuales, wrapper en bridge de bajo riesgo. Ataca la brecha real | ✅ RECOMENDADO |
| **NVIDIA garak** | **Auditoría adversarial** (red-team/fuzzer de LLM, NO runtime) | No es barrera activa: se ejecuta PUNTUAL para auditar antes de producción bancaria | 🔍 Auditoría única |

> Punto clave de honestidad técnica: **garak no es un guardrail de producción**.
> Es un prober/red-team. Mezclarlo en la "configuración de guardrails activos" es
> un error de categoría — útil como auditoría previa, nunca como barrera runtime.

---

## 3. RECOMENDACIÓN (en capas, mapa→amenaza)

1. **A corto plazo y bajo costo** → **llm-guard** como wrapper en el bridge:
   - ENTRADA: escáner de prompt-injection antes de que el mensaje llegue al LLM.
   - SALIDA: escáner de secretos (evitar fuga de tokens/credenciales en respuestas).
   - Encaje: función pre/post-proceso — sin reescribir la orquestación.
2. **Activación nativa Hermes** → `hard_stop_enabled: true` para cortar autómatas en bucle (hoy solo advierte).
3. **Auditoría PUNTUAL** → correr **garak** una vez antes de validar pagos bancarios en producción.
4. **Solo si surge necesidad multiagente** → reevaluar NeMo Guardrails / Guardrails AI. No hoy.

---

## 4. PLAN DE EJECUCIÓN (TODO = T2, requiere tu aprobación)

> Nada de esto se ha ejecutado. Modifican el venv compartido y el bridge en
> producción (Valentina/Dispatcher/pagos) → confirmación obligatoria.

- [ ] (T2) `pip install llm-guard` en `venv/`
- [ ] (T2) Wrapper `guardrail_wrapper.py`: escáner entrada (injection) + salida (secretos)
- [ ] (T2) Cablear en `api/bridge.py` (punto de sanitización + salidas de agentes)
- [ ] (T2) Activar `hard_stop_enabled: true` en config.yaml de Hermes
- [ ] (T2) `garak` en modo escaneo de inyección → informe de hallazgos (sin afectar datos ni contaminar modelo)
- [ ] (T2) Tests de regresión: webhooks WhatsApp/Telegram siguen respondiendo ok
- [ ] Reiniciar bridge y verificar `/health` + `/metrics`

---

## 5. DECISIÓN PENDIENTE
> Esperando confirmación de Luis sobre: instalar llm-guard ahora (recomendado y
> de menor riesgo) vs. solo auditoría garak vs. ambos. Sin respuesta → no se toca
> producción. Análisis queda disponible en el vault.
---

## 6. IMPLEMENTACIÓN 2026-08-13 (EJECUTADA — llm-guard + hard_stop)

### 6.1 Estado final
- ✅ `hard_stop_enabled: true` en config.yaml Hermes (inistal vía `hermes config`)
- ✅ `llm-guard 0.3.16` instalado en venv
- ✅ `api/guardrail.py` creado (wrapper fail-open, lazy init)
- ✅ Cableado en bridge: `sanitize_input(query)` en `_call_dify` (ENTRADA),
    `scrub_output(text)` en `_send_whatsapp_message` (SALIDA)
- ✅ Tests: 17/17 batería guardrail (0 falsos positivos) + 27 passed regresión + health OK

### 6.2 Hallazgos críticos corregidos en el camino
1. **FALSO POSITIVO en español**: el modelo PromptInjection de llm-guard (entrenado en
   inglés) marca frases legítimas como `quiero un botellon por favor` (risk 0.70) como
   inyección. → DECISIÓN: el bloqueo de entrada lo deciden SOLO las reglas propias
   determinísticas (ampliadas a ES-EN); llm-guard NO decide bloqueo de entrada.
2. **CUDA/Pascal**: torch 2.13 (CUDA 13) no trae kernel para GTX 1070 (compute 6.1) →
   `CUDA error: no kernel image`. → Se fuerza `CUDA_VISIBLE_DEVICES=""` (CPU). El motor
   de inferencia principal es NIM remoto; los validadores en CPU son correctos.
3. **Secrets scanner firma distinta** en 0.3.16: `Secrets(redact_mode='all')`, `.scan(text)`
   (1 arg). Sensitive (output) usa 2 args y enmascara teléfonos → NO se usa en salida
   (rompe respuestas legítimas). Salida = Secrets + fallback regex (SIEMPRE se ejecuta).
4. **Fallback de salida se saltaba** por `return` prematuro cuando llm-guard estaba activo
   → corregido: el fallback regex corre siempre (Bearer, sk-, access_token).

### 6.3 Resultado operativo
- Entrada: inyección ES/EN bloqueada (reglas propias), secretos pegados neutralizados (llm-guard)
- Salida: secretos (sk-, Bearer, tokens) enmascarados (llm-guard + fallback doble)
- Fail-open: si algo falla, se loguea y el texto pasa (jamás se rompe el flujo de WhatsApp)
