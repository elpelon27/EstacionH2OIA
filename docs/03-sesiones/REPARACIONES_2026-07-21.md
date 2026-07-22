# 🔧 Registro de Reparaciones — Loop P0 + P1 (2026-07-21)

**Sesión**: Prometeo x Líder @elpelon27  
**Trigger**: Orden "loop de reparaciones en la tabla"  
**Fuente**: docs/05-tech-debt/ANALISIS_ARQUITECTURA_2026-07-21.md (36 fallas: 11 P0 + 13 P1 + 12 P2)  
**Política**: Cada reparación appenda una entrada aquí ANTES de commitear. Trazabilidad completa: archivo:línea, antes/después, verificación, commit hash.

---

## Loop 1 — P0 Bloqueantes (secuencia: r1 → r11)

### ✅ r1 — `_init_db()` missing `dispatch_queue`
- **Archivo**: `api/bridge.py:317-380`
- **Cambio**: Añadido `CREATE TABLE IF NOT EXISTS dispatch_queue (17 cols)` + 3 indices (`idx_orders_phone_hash`, `idx_orders_created_at`, `idx_dispatch_queue_estado`). Bonus: `PRAGMA journal_mode=WAL` + `PRAGMA synchronous=NORMAL` activados persistente en init.
- **Verificación**: `python3 api.bridge._init_db()`. Resultado: journal_mode=wal ✅, dispatch_queue table creada ✅, 3 indices nuevos ✅. foreign_keys=0 (pragmas per-conexión, se ajusta en r2).
- **Estado**: COMPLETADO
- **Timestamp**: 2026-07-22 07:09 -04

### ✅ r2 — `PRAGMA foreign_keys=0` en ambas DBs (FKs declarados nunca enforced)
- **Archivos**: 
  - `skills/dispatcher.py:84-93` (helpers `get_dispatch_db` + `get_conv_db`)
  - `api/bridge.py:380-388` (nuevo helper `_get_db_with_fk(path, row_factory)`)
  - `api/bridge.py:_nearest_zone_id` y `_sync_client_to_dispatch_db` migrados al helper
- **Cambio**: Añadido `conn.execute("PRAGMA foreign_keys = ON")` en cada connect() del dispatcher (2 helpers centralizados usados por todas las funciones). En bridge.py, nuevo helper `_get_db_with_fk` activa FK + soporta row_factory, usado en INSERT críticos (sync_client, nearest_zone_id). Las 9 conexiones read-only restantes de bridge se dejan sin pragma (low risk).
- **Verificación**: Test con coords Bella Vista (10.651, -71.622) → zone_id=1 (FK a zones.id). `_sync_client_to_dispatch_db` crea client con FK válida. Sin error.
- **Estado**: COMPLETADO
- **Timestamp**: 2026-07-22 07:12 -04

### ✅ r3 — `journal_mode=delete` (no WAL) → database is locked en concurrencia
- **Conversations.db**: Resuelto en r1 (PRAGMA `journal_mode=WAL` + `synchronous=NORMAL` activados en `_init_db`). `PRAGMA journal_mode` retorna `('wal',)`. Persiste en archivo.
- **Dispatch.db**: Aplicado manualmente con `sqlite3 data/dispatch.db "PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;"`. Verificado: journal_mode=wal ✅, synchronous=2 (NORMAL) ✅.
- **Estado**: COMPLETADO (ambas BDs en WAL mode)
- **Timestamp**: 2026-07-22 07:13 -04

### ⚠️ r4 — systemd /etc desincronizado del repo (DRIFT no resuelto sin sudo)
- **Archivos**: 
  - `/etc/systemd/system/valentina-bridge.service` (678 bytes, en uso por systemd)
  - `systemd/valentina-bridge.service` repoarchivo (más completo: hardening, deps check, MemMax, StartLimit, CPUQuota, etc.)
- **Drift confirmado**: Repo incluye `ExecStartPre` deps check, `NoNewPrivileges`, `ProtectSystem=strict`, `ProtectKernelTunables`, `SystemCallFilter=@system-service` y otras 8 hardening directives que /etc NO tiene. /etc tiene las básicas (MemMax, Restart, RestartSec).
- **Acción requerida (Líder)**:
  ```bash
  sudo cp /mnt/ssd_trabajo/hermes-agent/systemd/valentina-bridge.service /etc/systemd/system/valentina-bridge.service
  sudo systemctl daemon-reload
  sudo systemctl restart valentina-bridge.service
  sudo systemctl status valentina-bridge.service --no-pager | head -10
  ```
- **Estado**: BLOQUEADO (falta sudo password interactiva) — Registrado para que Líder aplique el 1-liner manualmente
- **Timestamp**: 2026-07-22 07:13 -04
