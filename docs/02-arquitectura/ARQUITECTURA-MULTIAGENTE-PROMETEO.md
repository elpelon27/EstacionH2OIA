# 2026-10-01 — Arquitectura Multi-Agente PROMETEO (despliegue verificado)

## Qué se construyó

Sistema multi-agente con topología de 3 capas sobre worktrees git aislados:

```
Capa 0  LÍDER        decide, aprueba, recibe reportes
Capa 1  PROMETEO     perfil cerebro: coordina, NO toca código
Capa 2  FRENTES      r1-infra / r2-api / r3-integracion (worktrees)
```

**Contratos por frente** en `agentes/`:
- `00-BASE-OPERATIVA.md` — mapa real del repo, reglas duras, formato de
  reporte con evidencia obligatoria, protocolo de detención
- `01/02/03-FRENTE-*.md` — lista blanca de archivos, gates verificables,
  tareas, entorno correcto

**Principios validados con datos reales:**
- Dividir por frentes de trabajo (no capas técnicas) — cruces mínimos
- Los worktrees requieren rutas dinámicas (`__file__`-based): TODO
  hardcode al tronco rompe el aislamiento (7 archivos lo sufrían)
- `api/pod_router.py` fija constantes al importar → tests que lo usan
  necesitan parchear el módulo, no solo env vars
- BD de tests: JAMÁS la compartida; temporal por test (helper
  `tests/unit/pod_test_helper.py` reutilizable)

## Resultado verificado

- Suite completa: 1009 passed / 0 failed / 0 errores (baseline: 1F+5E)
- Odoo 17 vivo: 0 residuos de test
- Commits: 5e0b8910, 7da3df44, 8e3445cb, 64314d5e, 846114ad (merge R3),
  a461f371 (schema drift financial), 430b403f (docs)

## Fixes Top 4 (piloto automático, misma fecha)

- DT-32 cloudflared: causa raíz = WatchdogSec=60 sin sd_notify → kill
  cada 60s; panics QUIC eran síntoma. Fix: watchdog removido. 331s estable.
- DT-33 tests: 5 POD ya reparados + 3 e2e con password Odoo hardcodeada
  (leer de infra/odoo/.env). 1009/0/0 final.
- DT-34 Redis: warming corría 1x/día con TTL 2h → vacío 22h/día. Fix:
  cron cada 2h. DBSIZE=10 verificado.
- DT-31 Telegram: 15/15 comandos con handler real verificado vía
  setMyCommands/getMyCommands.

## Enlaces

- Reporte Top 4: [[REPORTE_FIX_TOP4]]
- Cierre de jornada: [[CIERRE_JORNADA_EQUIPO_PROMETEO_2026-10-01]]
- Contratos: `agentes/` en el repo
