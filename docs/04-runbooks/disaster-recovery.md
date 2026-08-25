# Runbook — Recuperación ante Desastres

> **Sistema**: Estación H2O (Hermes + Valentina + Odoo + Cloudflare)
> **Propietario**: Luis Martinez (@elpelon27)
> **Última revisión**: 2026-08-24
> **Alcance**: Restauración de `conversations.db` (Hermes), Odoo PostgreSQL,
> failover de túnel Cloudflare, disco lleno, corrupción SQLite y contactos de
> emergencia. Procedimientos ejecutables paso a paso.

---

## 0. Tabla de contenido

1. [Contactos de emergencia](#1-contactos-de-emergencia)
2. [Orden de recuperación](#2-orden-de-recuperación)
3. [Disco lleno](#3-disco-lleno)
4. [Corrupción SQLite (`conversations.db`)](#4-corrupción-sqlite-conversationsdb)
5. [Restaurar `conversations.db` (Hermes `state.db`)](#5-restaurar-conversationsdb-hermes-statedb)
6. [Restaurar Odoo PostgreSQL](#6-restaurar-odoo-postgresql)
7. [Failover Cloudflare (túnel)](#7-failover-cloudflare-túnel)
8. [Verificación post-recuperación](#8-verificación-post-recuperación)

---

## 1. Contactos de emergencia

> **Antes de ejecutar cualquier restauración destructiva**: notificar al
> propietario y registrar la hora en el canal de incidentes.

| Rol | Persona | Contacto | Disponibilidad |
|-----|---------|----------|----------------|
| Líder / Propietario | Luis Martinez | `@elpelon27` (Telegram/WhatsApp) — **tel: +58-XXX-XXXXXXX** | 24/7 |
| Respaldo técnico | _<asignar>_ | _<tel>_ | Horario laboral |
| Proveedor ISP / hosting | _<nombre ISP>_ | _<tel de soporte>_ | 24/7 |
| Cloudflare (Zero Trust) | — | Dashboard: `https://one.dash.cloudflare.com/` | Web — sin teléfono directo |
| Odoo partner / soporte | Self-hosted (Community) | — | N/A |

> **Completar antes de un incidente real**: rellenar los campos marcados
> `_<...>_`. En una emergencia no se tiene tiempo de buscar el teléfono.
> Guardar también un respaldo físico (impreso) de esta tabla.

**Canal de incidentes**: registrar cada paso con timestamp en
`~/incidents/<AAAA-MM-DD>-<síntoma>.md` (crear el directorio si no existe).

---

## 2. Orden de recuperación

> Principio: **estabilizar antes de restaurar, restaurar antes de reconectar.**
> No tiene sentido volver a exponer un servicio sobre datos corruptos.

Prioridad de componentes, del más crítico (caída primero) al menos crítico:

| # | Componente | Por qué primero | RTO objetivo |
|---|------------|-----------------|--------------|
| 1 | **Disco / sistema de archivos** | Un disco lleno o roto bloquea toda escritura: Hermes no guarda sesiones, Odoo no factura, los logs se pierden. Es la condición previa de todo lo demás. | 15 min |
| 2 | **`conversations.db` (Hermes `state.db`)** | Memoria conversacional de Valentina + histórico de sesiones. Sin ella, el agente pierde continuidad y contesta fuera de contexto. | 30 min |
| 3 | **Odoo PostgreSQL** | Fuente de verdad financiera: inventario, ventas, nómina, facturación SENIAT. Detiene la operación comercial. | 1 h |
| 4 | **Túnel Cloudflare** | Conectividad pública (WhatsApp gateway, Odoo web). Sin túnel, los servicios están arriba pero inalcanzables desde fuera. | 30 min |
| 5 | **Servicios secundarios** (Grafana/Loki/Prometheus, Dify, Weaviate) | Observabilidad y RAG. Importantes pero no bloquean la operación. | 4 h |

**Reglas de oro**:

- Nunca restaurar sobre el archivo activo sin haber copiado el estado actual a
  un `.broken-<fecha>` (puede ser la única pista del fallo).
- Toda restauración se hace primero con el servicio correspondiente **detenido**.
- Se verifica cada componente (§8) antes de declarar el incidente cerrado.

---

## 3. Disco lleno

### Síntomas
- `No space left on device` en logs de Hermes, Odoo o `journalctl`.
- Odoo devuelve HTTP 500 al guardar; Hermes no persiste sesiones.
- `df -h` muestra `Use%` ≥ 99 en `/` (`/dev/sdb3`) o en `/mnt/ssd_trabajo`
  (`/dev/sda1`).
- SQLite reporta `database or disk is full` / `SQLITE_FULL`.

### Prerrequisitos
- Acceso `sudo` en el host.

### Pasos

```bash
# 3.1 Diagnosticar dónde se consumió el espacio
df -h / /mnt/ssd_trabajo
sudo du -hx --max-depth=1 / 2>/dev/null | sort -rh | head -20

# 3.2 Contenedores Docker — la causa #1 más frecuente
docker system df                       # volúmenes, imágenes, contenedores
docker system prune -a --volumes       # elimina contenedores parados, imágenes colgadas, redes sin usar
#   ↑ interactivo: confirma "y". No toca volúmenes nombrados de Odoo/Postgres.

# 3.3 Logs de journal — causa #2
journalctl --disk-usage
sudo journalctl --vacuum-size=200M     # recorta a 200 MB
sudo journalctl --vacuum-time=3d       # o conserva solo últimos 3 días

# 3.4 Hermes — caches y snapshots
du -sh ~/.hermes/hermes-agent/node_modules \
       ~/hermes-unified/cache ~/hermes-unified/sessions \
       ~/hermes-unified/state-snapshots ~/hermes-unified/image_cache 2>/dev/null
# Limpiar snapshots antiguos (>30 días) — NO tocar state.db
find ~/hermes-unified/state-snapshots -type f -mtime +30 -delete
# Caches: seguros de purgar
rm -rf ~/hermes-unified/image_cache/* ~/hermes-unified/cache/*

# 3.5 Backups antiguos en el disco secundario (libera el destino de backups)
ls -lh /mnt/ssd_trabajo/backups/ /mnt/ssd_trabajo/hermes-agent-backup-*.tar.gz
# Conservar los 2 más recientes; archivar el resto a almacenamiento externo.
```

### Verificación
```bash
df -h /            # Use% debe bajar de 99%
# Reiniciar el servicio que fallaba:
sudo systemctl restart cloudflared       # si el túnel reportó errores de escritura
```

### Notas
- **No borrar** `~/hermes-unified/state.db`, `state.db-wal`, `state.db-shm`
  ni los volúmenes Docker `odoo-db` — son los datos vivos.
- Si el disco secundario `/mnt/ssd_trabajo` está lleno, los backups dejan de
  escribirse; tratarlo como prioridad 1 también.
- Umbral preventivo: configurar alerta cuando `Use%` > 85 (ver runbook de
  observabilidad Prometheus/Grafana).

---

## 4. Corrupción SQLite (`conversations.db`)

> Aplica a `~/hermes-unified/state.db` (la base de conversaciones de Hermes)
> y por extensión a `~/hermes-unified/kanban.db` y
> `~/hermes-unified/verification_evidence.db`.

### Síntomas
- Hermes arranca pero las sesiones no cargan o aparecen vacías.
- `sqlite3 state.db "PRAGMA integrity_check;"` reporta errores
  (`freelist`, `page X is not a btree page`, `database disk image is malformed`).
- `SQLITE_CORRUPT` / `SQLITE_NOTADB` en `~/hermes-unified/logs/`.
- El tamaño de `state.db-wal` crece sin control y no se checkpointea.

### Prerrequisitos
- Tener un backup reciente en `/mnt/ssd_trabajo/backups/` (ver §5 si hace falta
  restaurar desde cero).
- `sqlite3` instalado: `sudo apt-get install -y sqlite3`.

### Pasos — Diagnóstico

```bash
cd ~/hermes-unified

# 4.1 Estado del archivo y modo WAL
ls -la state.db state.db-wal state.db-shm
file state.db                # debe decir "SQLite 3.x database"

# 4.2 Chequeo de integridad (no destructivo)
sqlite3 state.db "PRAGMA integrity_check;"
sqlite3 state.db "PRAGMA quick_check;"

# 4.3 Si integrity_check devuelve "ok", el problema es de lógica/aplicación,
#     no de corrupción de páginas. Saltar a "Notas" más abajo.
```

### Pasos — Recuperación sin perder datos (orden de menor a mayor invasividad)

```bash
# 4.4 DETENER Hermes para que no escriba durante la recuperación
#     (detener el gateway / el proceso CLI que use la base)
pkill -f "hermes" || true
fuser state.db 2>/dev/null     # confirmar que ningún proceso la tiene abierta

# 4.5 Guardar copia del estado corrupto (forense) — siempre
cp -a state.db state.db state.db.broken-$(date +%Y%m%d-%H%M)
cp -a state.db-wal state.db-wal.broken-$(date +%Y%m%d-%H%M) 2>/dev/null
cp -a state.db-shm state.db-shm.broken-$(date +%Y%m%d-%H%M) 2>/dev/null

# 4.6 Forzar checkpoint del WAL y reparar con .recover (exporta filas sanas)
sqlite3 state.db ".recover" > recovered.sql
#    Si .recover falla o devuelve vacío, ir al 4.8 (restaurar desde backup).

# 4.7 Reconstruir la base a partir del SQL recuperado
mv state.db state.db.unrecovered-$(date +%Y%m%d-%H%M)
mv state.db-wal state.db-wal.unrecovered-$(date +%Y%m%d-%H%M) 2>/dev/null
mv state.db-shm state.db-shm.unrecovered-$(date +%Y%m%d-%H%M) 2>/dev/null
sqlite3 state.db < recovered.sql
sqlite3 state.db "PRAGMA integrity_check;"   # debe decir "ok"
sqlite3 state.db "VACUUM;"                    # desfragmenta y compacta
sqlite3 state.db "PRAGMA journal_mode=WAL;"   # restablecer modo WAL
```

### Pasos — Restaurar desde backup (si `.recover` no recupera suficiente)

```bash
# 4.8 Detener Hermes (como 4.4) y reemplazar desde el backup más reciente.
#     Ver §5 para el procedimiento completo de restauración de state.db.
```

### Verificación
```bash
sqlite3 state.db "PRAGMA integrity_check;"          # -> ok
sqlite3 state.db "SELECT count(*) FROM sessions;"   # número razonable (>0)
# Reiniciar Hermes y comprobar que carga el historial
```

### Notas
- `.recover` (SQLite ≥ 3.29) rescata filas legibles pero **puede perder datos
  de páginas corruptas**. Comparar el conteo de filas antes/después.
- Si `state.db-wal` contiene transacciones no volcadas, a veces basta con
  **checkpointear a mano** sin reemplazar la base:
  `sqlite3 state.db "PRAGMA wal_checkpoint(TRUNCATE);"`.
- `VACUUM` requiere espacio libre igual al tamaño de la base; si el disco
  está lleno (§3), resolverlo **primero**.
- Mantener `journal_mode=WAL` + `synchronous=NORMAL` reduce la probabilidad
  de corrupción ante cortes de luz. No usar `synchronous=OFF` en producción.

---

## 5. Restaurar `conversations.db` (Hermes `state.db`)

> **Qué se restaura**: la base de conversaciones y estado de Hermes
> (`~/hermes-unified/state.db`) desde un respaldo en
> `/mnt/ssd_trabajo/backups/`. Incluye `kanban.db` y
> `verification_evidence.db` si existían en el backup.

### Prerrequisitos
- El servicio Hermes está **detenido** (gateway + CLI + desktop).
- Backup válido en `/mnt/ssd_trabajo/backups/` (ver §6.1 para localizarlo).
- `df -h /` con espacio suficiente (> 2× el tamaño de `state.db`).

### Pasos

```bash
# 5.1 Detener todos los procesos que usan state.db
pkill -f "hermes" || true
fuser ~/hermes-unified/state.db 2>/dev/null && echo "¡aún hay procesos!" || echo "libre"

# 5.2 Respaldo forense del estado actual (por si el backup resulta peor)
cd ~/hermes-unified
cp -a state.db state.db.pre-restore-$(date +%Y%m%d-%H%M)

# 5.3 Localizar el backup más reciente de Hermes
ls -lht /mnt/ssd_trabajo/backups/ | head -20
#     Buscar:  hermes-state-*.tar.gz  o  hermes-unified-*.tar.gz
#     o el tarball completo:  /mnt/ssd_trabajo/hermes-agent-backup-*.tar.gz

# 5.4 Inspeccionar el contenido del backup sin extraer
BACKUP="/mnt/ssd_trabajo/backups/hermes-state-ÚLTIMO.tar.gz"   # ajustar nombre
tar -tzf "$BACKUP" | grep -E "state\.db|kanban\.db|verification"

# 5.5 Extraer a un directorio temporal y validar integridad
mkdir -p /tmp/hermes-restore
tar -xzf "$BACKUP" -C /tmp/hermes-restore
sqlite3 /tmp/hermes-restore/state.db "PRAGMA integrity_check;"   # -> ok
sqlite3 /tmp/hermes-restore/state.db "SELECT count(*) FROM sessions;"

# 5.6 Reemplazar la base viva (y sus sidecars WAL) con la restaurada
mv state.db state.db.replaced-$(date +%Y%m%d-%H%M)
mv state.db-wal state.db-wal.replaced-$(date +%Y%m%d-%H%M) 2>/dev/null
mv state.db-shm state.db-shm.replaced-$(date +%Y%m%d-%H%M) 2>/dev/null
cp -a /tmp/hermes-restore/state.db      ~/hermes-unified/state.db
cp -a /tmp/hermes-restore/state.db-wal  ~/hermes-unified/state.db-wal  2>/dev/null
cp -a /tmp/hermes-restore/state.db-shm  ~/hermes-unified/state.db-shm  2>/dev/null
#     Permisos: debe quedar skynet:skynet y 0600 (archivo sensible)
chown skynet:skynet ~/hermes-unified/state.db*
chmod 600 ~/hermes-unified/state.db*

# 5.7 Restaurar también kanban.db y verification_evidence.db si estaban en el backup
for f in kanban.db verification_evidence.db; do
  [ -f "/tmp/hermes-restore/$f" ] && cp -a "/tmp/hermes-restore/$f" ~/hermes-unified/
done

# 5.8 Arrancar Hermes y verificar
#     (el comando exacto depende de cómo se lance el gateway/desktop)
```

### Verificación
```bash
cd ~/hermes-unified
sqlite3 state.db "PRAGMA integrity_check;"
sqlite3 state.db "SELECT count(*) FROM sessions;"          # > 0
sqlite3 state.db "PRAGMA journal_mode;"                    # -> wal
# Abrir una sesión conocida en Hermes y confirmar que el historial carga.
```

### Notas
- **Pérdida de datos**: se pierden las conversaciones posteriores a la fecha del
  backup. Avisar al usuario; no hay forma de recuperar lo no respaldado.
- Si `state.db-wal` del backup es más reciente que `state.db`, ambos deben
  restaurarse juntos (el WAL tiene las transacciones no checkpointeadas).
- El archivo `state.db` contiene datos sensibles (historial conversacional,
  tokens, credenciales de proveedores). Mantener `chmod 600`.
- Tras restaurar, **ejecutar un backup fresco** inmediatamente para tener un
  punto de partida limpio.

---

## 6. Restaurar Odoo PostgreSQL

> **Qué se restaura**: la base de datos Odoo 17 alojada en el contenedor
> Docker `odoo-db` (imagen `postgres:15`, puerto `127.0.0.1:5433`).
> Fuente de verdad financiera: inventario, ventas, nómina, facturación.

### Prerrequisitos
- Contenedor `odoo-db` corriendo o capaz de arrancar (`docker ps -a | grep odoo-db`).
- Backup de la base Odoo: dump `pg_dump` (formato custom `.dump` o SQL plano) en
  `/mnt/ssd_trabajo/backups/odoo/`.
- Credenciales de Postgres: usuario/clave configurados en el contenedor
>   (env `POSTGRES_USER` / `POSTGRES_PASSWORD` del contenedor `odoo-db`).
- Detener `odoo-web` antes de restaurar para evitar conexiones durante la carga.

### 6.1 Localizar el backup

```bash
ls -lht /mnt/ssd_trabajo/backups/odoo/ 2>/dev/null || ls -lht /mnt/ssd_trabajo/backups/ | grep -i odoo
#     Buscar:  odoo-<fecha>-<dbname>.dump   o   odoo-<dbname>.sql.gz
```

### 6.2 Restauración (dump formato custom `.dump` — recomendado)

```bash
# 6.2.1 Detener el frontend Odoo (que el backend siga o se reinicia al final)
docker stop odoo-web

# 6.2.2 Variables de conexión (ajustar al nombre real de la BD Odoo)
PGCONT="odoo-db"
PGPORT="5433"            # mapeado en el host: 127.0.0.1:5433 -> 5432 del contenedor
PGUSER="$(docker inspect "$PGCONT" --format '{{range .Config.Env}}{{println .}}{{end}}' \
          | grep -oP 'POSTGRES_USER=\K.*')"
PGDB="$(docker inspect "$PGCONT" --format '{{range .Config.Env}}{{println .}}{{end}}' \
          | grep -oP 'POSTGRES_DB=\K.*')"
[ -z "$PGUSER" ] && PGUSER="odoo"
[ -z "$PGDB"  ] && PGDB="postgres"
echo "user=$PGUSER db=$PGDB port=$PGPORT"

# 6.2.3 Backup forense de la base actual (antes de pisarla)
docker exec -u postgres "$PGCONT" pg_dump -U "$PGUSER" -Fc "$PGDB" \
  > /mnt/ssd_trabajo/backups/odoo/odoo-PRE-RESTORE-$(date +%Y%m%d-%H%M).dump

# 6.2.4 Descartar la base y reconstruir desde el backup elegido
DUMP="/mnt/ssd_trabajo/backups/odoo/odoo-ÚLTIMO.dump"     # ajustar nombre
#     Opción A: recrear la BD (limpia, recomendada si el dump es completo)
docker exec -u postgres "$PGCONT" dropdb   -U "$PGUSER" "$PGDB" --if-exists
docker exec -u postgres "$PGCONT" createdb -U "$PGUSER" "$PGDB"
cat "$DUMP" | docker exec -i -u postgres "$PGCONT" pg_restore -U "$PGUSER" -d "$PGDB" -Fc --clean --if-exists -v
#     Opción B (si el dump ya viene con CREATE DATABASE): usar --create y apuntar a 'postgres'
#     docker exec -i -u postgres "$PGCONT" pg_restore -U "$PGUSER" -d postgres --create -v < "$DUMP"
```

### 6.3 Restauración (dump SQL plano `.sql.gz`)

```bash
docker exec -u postgres "$PGCONT" dropdb   -U "$PGUSER" "$PGDB" --if-exists
docker exec -u postgres "$PGCONT" createdb -U "$PGUSER" "$PGDB"
zcat "$DUMP_SQL_GZ" | docker exec -i -u postgres "$PGCONT" psql -U "$PGUSER" -d "$PGDB" -v ON_ERROR_STOP=1
```

### 6.4 Arrancar Odoo y reconectar

```bash
# 6.4.1 Reiniciar el contenedor web (re-carga la BD restaurada)
docker start odoo-web
sleep 5
docker logs --tail 30 odoo-web

# 6.4.2 Si Odoo 17 necesita migración de esquema tras el restore, forzarla:
docker exec odoo-web odoo --config=/etc/odoo/odoo.conf --database="$PGDB" \
  --update=all --stop-after-init
#     ↑ solo si el dump venía de otra versión; en restore normal NO es necesario.
```

### Verificación
```bash
# Conteo de objetos clave (ajustar nombres reales de tablas Odoo)
docker exec -u postgres "$PGCONT" psql -U "$PGUSER" -d "$PGDB" -c \
  "SELECT count(*) FROM sale_order;"
docker exec -u postgres "$PGCONT" psql -U "$PGUSER" -d "$PGDB" -c \
  "SELECT count(*) FROM stock_move;"
# Web: abrir https://<dominio-odoo>/ y loguearse; verificar último pedido / inventario.
docker logs --tail 50 odoo-web | grep -iE "error|traceback" || echo "sin errores"
```

### Notas
- **Postgres 15 vs 16**: el contenedor `odoo-db` usa `postgres:15`; el host tiene
  además `postgresql@16-main.service` (Postgres 16). **Restaurar Odoo siempre
  contra el contenedor `odoo-db` (pg15)**, no contra el cluster del host.
- Un dump `pg_dump -Fc` (custom) es preferible al SQL plano: soporta
  restauración paralela y restauración selectiva de tablas.
- Si el inventario o las ventas están en cero tras restaurar, el dump estaba
  vacío o apuntaba a otra BD: revisar `PGDB` y el nombre del archivo.
- Tras restaurar, **ejecutar un backup fresco** de Odoo (§6.1 del runbook de
  backups) para fijar un punto de partida limpio.

---

## 7. Failover Cloudflare (túnel)

> **Qué se hace**: recuperar la conectividad pública de Hermes (gateway
> WhatsApp/Telegram) y Odoo web cuando el túnel `cloudflared` cae.
> El servicio corre como unidad systemd `cloudflared.service` y usa credenciales
> en `~/.cloudflared/` (`config.yml` + `cert.pem` + `<tunnel-uuid>.json`).

### 7.1 Diagnóstico — ¿caída de túnel o de Cloudflare?

```bash
systemctl status cloudflared --no-pager
#    Active: active (running) -> el servicio está arriba, el problema es de rutas/DNS.
#    Active: failed/inactive   -> el demonio cayó; ir a §7.2.

journalctl -u cloudflared -n 100 --no-pager | grep -iE "error|context|tunnel|register"
cloudflared --version

# ¿Es un corte general de Cloudflare?
#    https://www.cloudflarestatus.com/
```

### 7.2 Reiniciar el túnel (caso más común)

```bash
sudo systemctl restart cloudflared
sleep 5
systemctl status cloudflared --no-pager
journalctl -u cloudflared -n 20 --no-pager
#    Buscar: "Registered tunnel connection" (4 conexiones ok)
```

### 7.3 El túnel no arranca — credenciales o configuración

```bash
# 7.3.1 Verificar que los archivos de credenciales existen y son legibles
ls -la ~/.cloudflared/config.yml ~/.cloudflared/cert.pem ~/.cloudflared/*.json
#    config.yml define ingress: hostname -> servicio local (p.ej. odoo http://localhost:8069)
#    cert.pem + <uuid>.json son las credenciales del túnel; sin ellas no conecta.

# 7.3.2 Probar cloudflared a mano para ver el error real
sudo cloudflared tunnel --config ~/.cloudflared/config.yml run
#    Errores típicos:
#      "tunnel not found"      -> el UUID en config.yml no existe en la cuenta; verificar en el dashboard.
#      "origin certificate"    -> cert.pem caducado/dañado; regenerar (ver 7.4).
#      "context deadline"      -> firewall/salida a Internet bloquea api.cloudflare.com.

# 7.3.3 Conectividad de salida (DNS/firewall)
curl -sS -o /dev/null -w "%{http_code}\n" https://api.cloudflare.com/client/v4/user
ping -c2 1.1.1.1
```

### 7.4 Regenerar credenciales (solo si `cert.pem` está dañado/caducado)

```bash
# Requiere haber hecho login en cloudflared antes (o tener el token del túnel)
cloudflared tunnel login                          # abre navegador para autorizar la cuenta
#    Genera un nuevo cert.pem en ~/.cloudflared/cert.pem
#    Re-ejecutar la verificación de ingress: cloudflared tunnel route dns <TUNNEL> <dominio>
sudo systemctl restart cloudflared
```

### 7.5 Failover de DNS — apuntar el dominio a un destino alternativo

> Si el túnel no puede recuperarse (host caído por horas) y se necesita mantener
> el servicio accesible desde un servidor de contingencia:

```bash
# 7.5.1 Desde el dashboard Cloudflare (Zero Trust > Networks > Tunnels) o por CLI:
#    - Si hay un túnel de respaldo en otro host: cambiar el registro CNAME
#      del hostname público para apuntar al túnel secundario.
#    - Si solo hay un host: poner el hostname en "DNS only" (proxy desactivado)
#      y apuntar el A/AAAA al IP del servidor de contingencia, temporalmente.

# 7.5.2 Por CLI (si hay `cloudflared` autenticado):
cloudflared tunnel route dns <NOMBRE_TÚNEL_BACKUP> <dominio-publico>
#    Esto crea/actualiza el CNAME  <dominio> -> <tunnel>.cfargotunnel.com
```

### 7.6 Verificación end-to-end

```bash
# El hostname público debe resolver al túnel de Cloudflare
dig +short <dominio-publico>        # -> <uuid>.cfargotunnel.com (CNAME)
# Un request debe llegar al backend local
curl -sS -o /dev/null -w "HTTP %{http_code}  %{time_total}s\n" https://<dominio-publico>/
# El gateway de Hermes debe volver a recibir mensajes de WhatsApp/Telegram:
#   enviar un mensaje de prueba y ver que Valentina responde.
```

### Notas
- `cloudflared.service` está **habilitado** (`enabled`) — arranca solo tras
  reinicio del host. Tras un reboot, verificar estado igualmente.
- Si el corte es de **Cloudflare** (status page en rojo), no hay failover local
  posible; esperar y monitorizar `cloudflarestatus.com`.
- Mantener una copia fuera de línea de `~/.cloudflared/config.yml` y
  `cert.pem` (en el backup de `/mnt/ssd_trabajo/backups/`) para poder
  reconstruir el túnel desde cero si el host se formatea.
- El túnel expone servicios que escuchan en `localhost`; antes de reconectar,
  confirmar que **Odoo y el gateway Hermes ya están arriba** (§5, §6) para no
  exponer un backend caído.

---

## 8. Verificación post-recuperación

Checklist final — **no declarar el incidente cerrado hasta que todo marque ✅**.

```bash
# 8.1 Sistema
df -h / /mnt/ssd_trabajo                    # espacio saneado
uptime                                       # host estable, sin reboot por pánico

# 8.2 Hermes / conversaciones
sqlite3 ~/hermes-unified/state.db "PRAGMA integrity_check;"   # ok
systemctl is-active cloudflared             # active
# Enviar un mensaje de prueba por WhatsApp/Telegram y confirmar respuesta de Valentina.

# 8.3 Odoo
docker ps --format '{{.Names}}\t{{.Status}}' | grep -E 'odoo-web|odoo-db'   # Up
curl -sS -o /dev/null -w "%{http_code}\n" http://localhost:8069/web/login   # 200
# Loguearse en Odoo; verificar último pedido de venta y stock de botellones.

# 8.4 Conectividad pública
curl -sS -o /dev/null -w "%{http_code}\n" https://<dominio-publico>/        # 200

# 8.5 Observabilidad (prioridad 5 — no bloquea, pero conviene verificar)
docker ps --format '{{.Names}}\t{{.Status}}' | grep -E 'loki|prometheus|grafana'
```

### Registro del incidente

1. Anotar en `~/incidents/<AAAA-MM-DD>-<síntoma>.md`: causa raíz, hora de inicio,
   hora de recuperación, componentes tocados, datos perdidos (si los hubo).
2. Si hubo pérdida de datos, **actualizar el plan de backups** para reducir el
   RPO (frecuencia de backup) la próxima vez.
3. Si la causa fue disco lleno, **aumentar la monitorización** de capacidad
   (alerta en Grafana al 85 %).

---

## Apéndice A — Rutas y servicios de referencia

| Recurso | Ruta / Nombre | Notas |
|---------|---------------|-------|
| Conversaciones Hermes | `~/hermes-unified/state.db` | SQLite, WAL; sidecars `-wal`, `-shm` |
| Kanban | `~/hermes-unified/kanban.db` | SQLite, WAL |
| Evidencia de verificación | `~/hermes-unified/verification_evidence.db` | SQLite |
| Logs Hermes | `~/hermes-unified/logs/` | |
| Backups primarios | `/mnt/ssd_trabajo/backups/` | disco secundario `/dev/sda1` |
| Backups tarball Hermes | `/mnt/ssd_trabajo/hermes-agent-backup-*.tar.gz` | |
| Contenedor Odoo web | `odoo-web` (odoo:17.0) | `127.0.0.1:8069` |
| Contenedor Odoo DB | `odoo-db` (postgres:15) | `127.0.0.1:5433` -> 5432 |
| Postgres host | `postgresql@16-main.service` | NO usar para Odoo |
| Túnel Cloudflare | `cloudflared.service` (systemd) | credenciales `~/.cloudflared/` |
| Disco raíz | `/dev/sdb3` → `/` (108G) | vigilar `Use%` |
| Disco secundario | `/dev/sda1` → `/mnt/ssd_trabajo` | destino de backups |

## Apéndice B — Comandos de backup (referencia)

> Mantener los backups frescos es lo que hace que este runbook funcione.
> Programarlos con cron (ver runbook de backups / `cron/`).

```bash
# Backup Hermes state.db (en caliente, modo WAL permite snapshot consistente)
sqlite3 ~/hermes-unified/state.db ".backup '/mnt/ssd_trabajo/backups/hermes-state-$(date +%Y%m%d).db'"
tar -czf /mnt/ssd_trabajo/backups/hermes-state-$(date +%Y%m%d).tar.gz \
    -C ~ hermes-unified/state.db hermes-unified/kanban.db hermes-unified/verification_evidence.db

# Backup Odoo (dump formato custom, paralelizable)
docker exec -u postgres odoo-db pg_dump -U odoo -Fc -Z6 odoo > \
  /mnt/ssd_trabajo/backups/odoo/odoo-$(date +%Y%m%d).dump
#     Ajustar -U <usuario> y el nombre de la BD Odoo real.
```
