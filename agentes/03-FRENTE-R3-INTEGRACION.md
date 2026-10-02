# FRENTE R3-INTEGRACION — Integraciones externas y deuda de tests

## Mision

Reparar los 5 errores de tests preexistentes (deuda real heredada, nadie
del equipo actual los rompio) y mantener las integraciones externas
(Odoo, WAHA, POD, PWA) bajo prueba.

## Worktree asignado (VERIFICADO 2026-10-01)

```
/mnt/ssd_trabajo/10-r3-integracion     rama: 10-r3-integracion
  base: 5cc44536 (snapshot: 20261001_060201)
  creado con: git worktree add /mnt/ssd_trabajo/10-r3-integracion 10-r3-integracion
  conftest.py ya actualizado con fix de rutas dinamicas (copiado del tronco)
```

## Diagnostico REAL de los 5 errores (verificado con pytest --tb=long)

CAUSA COMUN: estos 5 archivos ejecutan codigo en NIVEL DE MODULO
(fuera de funciones test) durante la recolección. Al importarse,
hacen peticiones HTTP reales (TestClient) contra la BD real. Dos familias:

### Familia A — esquema faltante en la BD (4 de 5)

```
E  sqlite3.OperationalError: no such table: deliveries
   ../hermes-agent/api/pod_router.py:210  (desde test_pod_endpoints_bloque2)
```

Afecta: test_killswitch_bloque5 (linea 49), test_pod_endpoints_bloque2
(linea 40), test_pod_waha_fase2 (linea 82), test_pwa_bloque3 (linea 72).
Los tests tocan endpoints que leen tablas (`deliveries`, etc.) que NO
existen en la BD que usan. El fixture `patch_dispatch_db` de
tests/conftest.py YA crea esas tablas — pero estos tests no lo usan
porque ejecutan en modulo-level, ANTES de que pytest aplique fixtures.

### Familia B — bug en el propio test (1 de 5)

```
E  NameError: name 'did2' is not defined
   tests/unit/test_pod_endpoints_bloque2.py:128
```

Un identificador `did2` que no existe en el archivo.

### Familia C — dependencia de servicio vivo (1 de 5)

```
test_pod_odoo_sync_bloque4 (linea 110): ejecuta scripts/pod_odoo_sync.py
en main() y el script falla (traceback en linea 285→290). Depende de
Odoo real o de BD con datos.
```

## Tareas de este frente (EN ORDEN)

### T1 — Familia B (la mas barata): arreglar NameError did2
Leer tests/unit/test_pod_endpoints_bloque2.py:128, entender que
quiso ser `did2` (probablemente una segunda delivery creada antes),
definirlo o corregir la referencia.

### T2 — Familia A: mover codigo de modulo-level a funciones test
Cada uno de los 4 archivos: envolver las llamadas module-level en
funciones `def test_...()` y usar el fixture `patch_dispatch_db`
que YA existe en conftest (crea todas las tablas: bottles, clients,
vehicles, deliveries, gps_tracks, dispatch_queue, zones...).
NO crear fixtures nuevas: el conftest ya las tiene.

### T3 — Familia C: decidir el destino de test_pod_odoo_sync_bloque4
Investigar si el script requiere Odoo vivo. Si es asi: marcarlo
`@pytest.mark.integration` y excluirlo de la suite unitaria por
defecto (documentandolo), o mockear la conexion Odoo. NO borrarlo.

### T4 — Rebasar rama sobre el tronco cuando el fix del conftest se integre
La rama 10-r3-integracion nacio en 5cc44536 (ANTES del fix conftest).
El conftest.py fixeado ya fue copiado al worktree a mano. Al integrar,
asegurarse de rebase o merge con feat/odoo-r4-integration.

## FUERA de tu permiso

```
infra/ scripts/ systemd/    → R1
core/ api/                  → R2 (solo si el fix de tests LO REQUIERE,
                              y documentandolo en el reporte)
agentes/                    → solo lectura, salvo tu reporte
```

## Entorno correcto (VERIFICADO)

```bash
/mnt/ssd_trabajo/hermes-agent/venv/bin/python3   # SIEMPRE este interprete
PYTHONDONTWRITEBYTECODE=1                          # evitar contaminacion pycache
-p no:cacheprovider                                # idem cache pytest
```

## Gates de validacion (salida REAL obligatoria)

```bash
# G1 — los 5 archivos recolectan sin error
venv/bin/python3 -m pytest tests/unit/test_killswitch_bloque5.py \
  tests/unit/test_pod_endpoints_bloque2.py tests/unit/test_pod_odoo_sync_bloque4.py \
  tests/unit/test_pod_waha_fase2.py tests/unit/test_pwa_bloque3.py \
  --collect-only -q -p no:cacheprovider

# G2 — la suite completa NO regresa: mismo piso o mejor que el tronco
#      (tronco 2026-10-01: 962 passed / 1 failed / 5 errors)
venv/bin/python3 -m pytest tests/unit tests/smoke -q --tb=no \
  -p no:cacheprovider --continue-on-collection-errors

# G3 — arbol limpio tras el trabajo
git status --porcelain
```

Meta verificable: **0 errores de recoleccion** en G1, y en G2 pasar de
5 errors a 0 errors (los tests reparados deben PASAR o quedar marcados
integration con justificacion, nunca borrados en silencio).

## Formato de reporte obligatorio

```
FRENTE: r3-integracion
WORKTREE: /mnt/ssd_trabajo/10-r3-integracion
ARCHIVOS_MODIFICADOS:
  - <ruta>
COMMITS:
  - <sha> <mensaje>
EVIDENCIA:
  $ <comando>
  <salida real>
GATES:
  - G1 recoleccion: <salida>
  - G2 suite:       <salida>
  - G3 estado:      <salida>
RIESGOS:
  - <riesgo, o "ninguno">
BLOQUEADO:
  - <dependencia, o "ninguna">
```

## Protocolo de detencion

Supuesto no verificable con comando → DETENTE y reporta.
El lider prefiere un freno honesto a un informe falso.
