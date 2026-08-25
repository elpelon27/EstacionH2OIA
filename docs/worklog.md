# WORKLOG — Piloto Automático #2 · 2026-08-24

## R4 Coverage (CRÍTICO — seguridad bancaria)

### webhooks.py: 31% → 89% ✓
- **Archivo creado:** `tests/unit/test_r4_webhooks_coverage.py` (117 tests)
- **Cobertura alcanzada:** 89% (objetivo: 80%)
- **Líneas cubiertas:**
  - R4WebhookConfig: init, defaults, validate, reset, commerce_secret fallback
  - Rate limiting: check_rate_limit (ok, exceeded, window cleanup)
  - IP whitelist: verify_ip_whitelist (allowed, rejected 403, X-Forwarded-For, no client)
  - Auth token: verify_auth_token (ok, missing 401, empty, mismatch 403, no config 503)
  - verify_rate_limit: middleware (ok, exceeded 429, forwarded_for)
  - security_dependency: chained verifications (ok, IP fail)
  - detect_webhook_format: MBconsulta, R4consulta, default
  - Pydantic models: R4ConsultaRequest, R4NotificaRequest (valid/invalid), responses
  - WebhookProcessResult: to_consulta_response, to_notifica_response, with_data
  - process_r4consulta: with pedidos, without pedidos, error graceful, V/E prefix normalization
  - process_r4notifica: CodigoRed!=00, no pedido, internal error, full success flow, ambiguous match, verify failed, Odoo sync success
  - process_mbconsulta: mapping to notifica, fallback partial
  - FastAPI endpoints: /consulta (success, invalid JSON, MBconsulta format), /notifica (success, invalid payload), /health
  - Router: prefix, routes, include_r4_webhooks
  - Logging: _log_full_request, _log_hmac_failure (3 variants)

### hmac_auth.py: 58% → 100% ✓
- **Cobertura alcanzada:** 100% (objetivo: 80%)
- **Líneas cubiertas:**
  - build_sign_string: R4BCV, R4CONSULTA, R4NOTIFICA, missing field, invalid endpoint, int values
  - compute_hmac_sha256: valid, empty, no secret, different secrets
  - verify_hmac_signature: valid, invalid, missing field, lowercase input
  - build_auth_headers: with/without commerce_id
  - get_sign_string_description: valid, invalid
  - All 12 sign_* convenience functions
  - __main__ block (via subprocess)

### Resultado final R4
- 116 tests passed, 1 skipped, 0 failed
- webhooks.py: 89% (31% → 89%)
- hmac_auth.py: 100% (58% → 100%)

## FASE 3 SOUL — Scripts de memoria v2.1

### scripts/consolidator.py
- Lee fs_audit_log (últimas 24h, limit=50)
- Extrae hechos con Ollama qwen2.5:7b local
- Indexa en Qdrant + escribe en Obsidian vault
- Registra en hermes_memory.db::consolidation_log
- Guardarraíl: 3 fallos consecutivos → detiene y notifica
- Dry-run verificado: Ollama procesa 50 audit logs sin colgarse

### scripts/decay_social.py
- Recorre interactions.db
- Aplica decay 0.99/día
- Archiva relevance < 0.1 a interactions_archive
- Dry-run verificado: 0 interacciones a archivar (BD nueva)

### scripts/decay_semantic.py
- Recorre Qdrant hermes_memory (402 points)
- Aplica decay 0.995/día
- Archiva relevance < 0.1 en hermes_memory.db::archive
- Dry-run verificado: 0 puntos a archivar (todos < 27 días)

### scripts/warming.py
- Lee cron_runs de hermes_memory.db
- Detecta patrones temporales (≥3 ejecuciones mismo día/hora)
- Pre-fetch top-10 chunks de Qdrant a Redis (TTL 2h)
- Dry-run verificado: sin patrones (cron_runs vacía), --force funciona
- Redis: import lazy (módulo redis no instalado en venv — se instala cuando se active)

## Runbooks
- RUNBOOK_CI-CD.md: ya existía en docs/02-arquitectura/runbooks/ (2.7KB)
- RUNBOOK_SwapBottles.md: ya existía en docs/02-arquitectura/runbooks/ (3.8KB)
- RUNBOOK_DisasterRecovery.md: ya existía en docs/02-arquitectura/runbooks/ (6.1KB)
- Subagentes verificaron y ampliaron el contenido existente

## Archivos creados
- tests/unit/test_r4_webhooks_coverage.py (117 tests, R4 coverage)
- scripts/consolidator.py (consolidador automático episódica→semántica)
- scripts/decay_social.py (decay exponencial capa Social)
- scripts/decay_semantic.py (decay exponencial capa Semántica)
- scripts/warming.py (warming selectivo Redis)

## .gitignore actualizado
- Añadido: `*.consolidator_failures` (archivo de tracking de fallos)

---

*Prometeo · Piloto Automático #2 · 2026-08-24 · 💧*
