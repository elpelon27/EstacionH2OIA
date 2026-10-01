# FRENTE R1-INFRA — Infraestructura de Contenedores

## Mision

Endurecer y verificar la infraestructura de contenedores de Estacion H2O.
Este frente **NO toca logica de negocio ni esquema de base de datos**.
Su unico producto son archivos de infraestructura verificados.

## Worktree asignado (VERIFICADO 2026-10-01)

```
/mnt/ssd_trabajo/10-r1-infra     rama: 10-r1-infra
  base: 5cc44536 (snapshot: 20261001_060201)
  creado con: git worktree add /mnt/ssd_trabajo/10-r1-infra 10-r1-infra
```

El tronco `/mnt/ssd_trabajo/hermes-agent` esta PROHIBIDO para este frente.

## Archivos autorizados (lista blanca — lo demas esta vedado)

Solo puedes crear/modificar rutas bajo estos prefijos:

```
infra/                    compose, odoo/, waha/, nginx/, prometheus/,
                          grafana/, loki/, promtail/, paperless/,
                          open-notebook/, systemd/
scripts/                  ONLY: waha_health_check.sh, waha_link_device.sh,
                          generate_waha_env.sh, verify_waha_sessions.py,
                          health_check.py
systemd/                  unidades de servicio
monitoring/               prometheus/rules, grafana/dashboards
```

### EXPRESAMENTE PROHIBIDO

```
agentes/                  solo lees, nunca escribes (salvo tu reporte)
api/, core/, db/          NO tocar (son de R2 y R3)
tests/                    NO crear ni editar tests (son de R3)
cualquier .py de negocio  NO
```

## Regla critica de WAHA (dato REAL del lider — violacion destruye vinculacion)

WAHA guarda las credenciales de los choferes en:

```
/app/.sessions/webjs     ← DENTRO del contenedor
```

**NO** en el volumen `/sessions` (ese queda vacio).

Por tanto:
- Hacer `docker rm` sobre el contenedor de WAHA **SIN** montar `/app/.sessions`
  **DESTRUYE la vinculacion de los choferes**. Es un dano real e irreversible.
- Antes de CUALQUIER operacion destructiva sobre el contenedor WAHA,
  ejecutar respaldo:

```bash
docker cp waha:/app/.sessions/webjs <destino>
```

Esta regla esta en `~/.hermes/skills/devops/waha-vinculacion-y-rotacion/`
y es de cumplimiento obligatorio. Si tu tarea toca WAHA, citar el respaldo
en tu reporte.

## Inventario REAL de infra/ verificado en disco

```
infra/docker-compose.base.yml
infra/grafana/
infra/loki/
infra/nginx/
infra/odoo/
infra/open-notebook/
infra/paperless/
infra/prometheus/
infra/promtail/
infra/systemd/
infra/waha/
```

NOTA: **NO** existe `infra/91-whatsapp-monitor.py`. Fue una ruta inventada
en sesion anterior. Queda retirada.

## Tareas de este frente

### T1 — Auditar healthchecks de los servicios
Revisar cada `docker-compose*.yml` bajo `infra/` y verificar que los
healthchecks sean reales y no den falsos positivos.
Precedente real: `67dd5209 fix(waha): healthcheck daba unhealthy por 401
(falta X-Api-Key)` — ese es el tipo de fallo a buscar.

### T2 — Verificar respaldo de sesiones WAHA
Confirmar que existe procedimiento de respaldo de `/app/.sessions/webjs`
y que esta documentado. Si no existe, crearlo bajo `scripts/`.

### T3 — Validar sintaxis de todos los compose
Ejecutar `docker compose config` (o equivalente) sobre cada archivo y
reportar la salida REAL.

## Gates de validacion (debes ejecutarlos y pegar la salida)

```bash
# G1 — sintaxis de compose
docker compose -f infra/docker-compose.base.yml config >/dev/null && echo "G1 OK"

# G2 — sintaxis de scripts
bash -n scripts/waha_health_check.sh && echo "G2 OK"

# G3 — nada tocado fuera de la lista blanca
git status --porcelain
```

## Formato de reporte obligatorio

Devuelve EXACTAMENTE este bloque (relleno con salidas reales):

```
FRENTE: r1-infra
WORKTREE: /mnt/ssd_trabajo/10-r1-infra
ARCHIVOS_MODIFICADOS:
  - <ruta>
COMMITS:
  - <sha> <mensaje>
EVIDENCIA:
  $ git worktree list
  <salida real>
GATES:
  - G1 compose:  <salida real, incluyendo errores>
  - G2 bash -n:  <salida real>
  - G3 status:   <salida real>
RIESGOS:
  - <riesgo concreto, o "ninguno">
BLOQUEADO:
  - <dependencia no resuelta, o "ninguna">
```

Si BLOQUEADO no esta vacio: frenar. No adivinar. No disfrazar.

## Protocolo de detencion

Ante un supuesto no verificable con comando: DETENTE y reporta.
El lider prefiere un freno honesto a un informe falso.
