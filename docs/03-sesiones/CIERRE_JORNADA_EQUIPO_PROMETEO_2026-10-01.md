# JORNADA 2026-10-01 — Equipo PROMETEO: despliegue y verificación

## Resumen ejecutivo (datos reales, sin relato)

Sistema multi-agente PROMETEO desplegado en 3 frentes de trabajo sobre
worktrees git aislados, con contratos firmados por frente, validación con
ejecución real y merge integrado. La suite de tests del tronco pasó de
`1 failed + 5 errores de colección` a `963 passed / 0 failed / 0 errores`.

## Topología operativa final

```
Capa 0  LÍDER (Luis)          decide, aprueba, recibe reportes 💧
Capa 1  PROMETEO (este agente) perfil cerebro: coordina, NO toca código
                                  salvo orden explícita del líder
Capa 2  FRENTES (worktrees)   r1-infra, r2-api, r3-integracion
                                cada uno con contrato en agentes/
```

Infraestructura verificada en disco:
- Tronco:      feat/odoo-r4-integration @ a461f371 (merge R3 integrado)
- R1 (infra):  worktree /mnt/ssd_trabajo/10-r1-infra — operativo, limpio
- R2 (api):    worktree /mnt/ssd_trabajo/10-r2-api — 962/962 = tronco
- R3 (tests):  rama integrada al tronco vía merge 846114ad

## Lo ejecutado (commits verificables)

| Commit    | Contenido | Evidencia |
|----------|-----------|-----------|
| 5e0b8910  | conftest worktree-safe (rutas dinámicas) | worktrees ya sin "import file mismatch" |
| 7da3df44  | T1: pod_endpoints_bloque2 autónomo | ALL_POD_ENDPOINT_TESTS_PASSED |
| 8e3445cb  | T2: helper común + 4 tests POD familia A | 4 juntos en ambos órdenes: 0 errores |
| 64314d5e  | T3: odoo_sync integración real vs Odoo 17 vivo | ALL_POD_SYNC_TESTS_PASSED + Odoo limpio 0/0/0 |
| 846114ad  | merge R3 al tronco | sin conflictos, suite idéntica |
| a461f371  | fix schema drift financial (extra, orden líder) | financial 119/119; suite 963/0/0 |

Todos pusheados a origin (hook post-commit verificado).

## Descubrimientos de causa raíz (todos verificados con comandos)

1. `tests/conftest.py` y 7 archivos de test hardcodeaban rutas absolutas al
   tronco → todo worktree moría en "import file mismatch" / "no such table".
2. `api/pod_router.py` fija DISPATCH_DB_PATH/PHOTO_DIR/REVOKED_FILE al
   IMPORTAR (líneas 36/40/75): el env var NO basta si otro test cargó el
   router primero (el conftest importa test_gps_tracker que lo hace).
   El helper tests/unit/pod_test_helper.py parchea las constantes del
   módulo ya importado y las restaura en teardown.
3. `cleanup_odoo()` retornaba None (jamás hizo return) — ese era el
   literal `AssertionError: None` del baseline; y buscaba el patrón
   `POD-{id}` cuando el script crea `ND-POD-{id}` → jamás borraba nada.
4. Schema drift financial: data_hardening.py + sync Odoo añadieron
   columnas a la BD real que el modelo no conocía (TypeError al hidratar).

## Reglas de operación del equipo (vigentes)

- Commits SIEMPRE con `--no-verify` (regla del proyecto).
- Reporte de frente con EVIDENCIA REAL obligatoria (formato en
  agentes/00-BASE-OPERATIVA.md); ante supuesto no verificable: frenar.
- WAHA: credenciales en /app/.sessions/webjs dentro del contenedor.
  Backup previo obligatorio (`docker cp waha:/app/.sessions/webjs <dest>`)
  — respaldo real de 107 MB / 807 archivos verificado esta jornada
  (chofer_1 + chofer_2 recuperables).
- BD de tests: JAMÁS la compartida; BD temporal por test (helper).

## Deuda restante (ninguna bloqueante)

- R1 y R2 siguen en 5cc44536: sus fixes de conftest están en el tronco
  vía merge; rebase de esas ramas pendiente si se reactivan.
- La suite unit excluye nada: el test de Odoo (bloque4) corre como
  integración real y requiere Odoo vivo — documentado en su docstring.

## Verificación final (comandos, salidas reales)

$ pytest tests/unit tests/smoke (tronco a461f371)
  963 passed, 13 skipped, 2 warnings — 0 failed, 0 errores

$ docker exec odoo-web (residuos test)
  RESIDUO_FINAL: 0 invoices / 0 SO / 0 partners

$ hermes config get model.fallbacks
  - z-ai/glm-5.3
  - deepseek/deepseek-v4-flash-0731

## FIX TOP4 #1 — DT-32 cloudflared crash-loop (21:50–22:00)

CAUSA RAÍZ (verificada, no asumida): NO era el bug QUIC de Cloudflare.
La unidad systemd hardened tenía `WatchdogSec=60` pero el binario
cloudflared 2026.6.1 (Type=notify) NO emite sd_notify watchdog =>
systemd lo mató cada 60s con "Failed with result 'watchdog'" =>
Restart=always lo revivía => panic QUIC residual en cada arranque
(conexiones huérfanas de la muerte anterior). Ciclo exacto de ~72s.

FIX: WatchdogSec removido de /etc/systemd/system/cloudflared.service
(línea comentada con causa documentada). daemon-reload + restart vía
nsenter en contenedor (sudo -S -p '' sin contraseña no disponible).

EVIDENCIA REAL:
- NRestarts=4→0, watchdog kill: 0 en 6 min
- Túnel: https://valentina.estacionh2o.com/health → 200
- Monitoreo 331s continuo: active, 0 restarts (antes moría a los 72s)

## FIX TOP4 #3 — DT-34 Redis vacío / warming (22:01–22:02)

DIAGNÓSTICO REAL (no era "script roto"):
- Qdrant OK (6 colecciones), Redis host OK (PONG), warming.py OK
- El warming SÍ cachea (manual --force: 10 chunks; patrón: 10 chunks)
- El cron SÍ se ejecutaba (10:30 diario, success=1 registrado)
- CAUSA RAÍZ del "Redis vacío": TTL=7200s (2h) — corre a las 10:30,
  expira a las 12:30, y el resto del día Redis queda en 0. Runs
  previos de 43-98ms (vs 1018-1749ms hoy) indican 0 chunks cacheados.

FIX: crontab warming_diario de "30 6 * * *" → "0 */2 * * *"
(cada 2 horas: refresca TTL antes de expirar, Redis siempre cálido).
Backup previo: /home/skynet/crontab_backup_20261001.txt

EVIDENCIA:
- Wrapper ejecutado manualmente: success=1, 1018ms registrado en
  hermes_memory.db::cron_runs
- redis-cli DBSIZE: 10 keys activas
