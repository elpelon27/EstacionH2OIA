# Runbook: CI/CD — Tests locales, cobertura, hooks y despliegue

> **Alcance.** Este runbook describe el flujo de calidad **antes de abrir un PR** y el
> chequeo de servicios **antes de un deploy**. Es obligatorio para todo cambio que
> toca `main` o que se publica en un entorno compartido (staging/producción).
>
> **Stack de calidad.** `ruff` (lint + formato), `mypy` (tipado estático),
> `detect-secrets` (prevención de fugas de credenciales), `pytest` (tests),
> `pytest-cov` (cobertura). Todo corre **localmente primero** y luego en CI.

---

## 1. Prerrequisitos — entorno de desarrollo

Antes de ejecutar cualquier comando de calidad, instala el entorno `dev` (contiene
`pytest`, `pytest-asyncio`, `ruff`, `mypy`, `detect-secrets`, `pytest-cov`):

```bash
#Desde la raíz del repositorio
uv sync --extra dev          # o: pip install -e ".[dev]"

#Verifica que las herramientas quedan en el PATH
ruff --version
mypy --version
detect-secrets --version
pytest --version
```

> **Regla de pines.** Las dependencias están *exact-pinned* (`==X.Y.Z`, sin rangos).
> No introduzcas rangos (`>=`, `~=`) al actualizar versiones: bump el pin, regenera
> `uv.lock` con `uv lock` y commitea ambos. Los rangos permiten que una versión
> nueva de una transitive llegue sin revisión.

Instala los hooks de pre-commit (sección [3](#3-pre-commit-hooks)):

```bash
pre-commit install            # instala el hook en .git/hooks/pre-commit
pre-commit install --hook-type pre-push   # refuerza también antes de push
```

---

## 2. Tests locales

### 2.1 Suite completa

```bash
#Corre toda la suite (respeta addopts: -m 'not integration')
pytest

#Salida verbosa, detiene en el primer fallo
pytest -v -x

#Solo un archivo / un directorio
pytest tests/test_foo.py
pytest tests/tools/

#Una prueba concreta por nombre
pytest -k "nombre_del_caso"
```

### 2.2 Marcadores — integración y exclusiones de plataforma

La suite usa marcadores para excluir lo costoso o lo plataforma-específico en CI
normal. Úsalos a propósito en local cuando lo necesites:

```bash
#Incluye las pruebas de integración (API keys reales, Modal, etc.)
pytest -m integration

#Solo las de Linux / macOS / Windows
pytest -m linux_only
pytest -m macos_only
pytest -m windows_only

#Las que requieren un servidor SSH alcanzable
pytest -m ssh
```

Marcadores disponibles (definidos en `pyproject.toml` → `[tool.pytest.ini_options]`):

| Marcador                | Cuándo usarlo                                                  |
|-------------------------|----------------------------------------------------------------|
| `integration`           | Requiere servicios externos (API keys, Modal). **Off en CI** por defecto. |
| `ssh`                   | Requiere un servidor SSH reachable. Se salta en CI normal.    |
| `linux_only` / `macos_only` / `windows_only` | Comportamiento nativo de plataforma; se salta en las demás. |
| `requires_wal`          | Necesita SQLite WAL real (no `journal_mode=DELETE`).          |
| `no_isolate`            | Opta por compartir estado mutable entre archivos.            |
| `real_concurrent_gate`  | Opta por NO usar el stub del detector de instancias concurrentes. |
| `real_agent_prewarm`    | Opta por NO usar el stub del pre-warm del agente diferido.    |

> **Convención de marcadores nuevos.** Si añades un marcador, decláralo en
> `markers = [...]` de `[tool.pytest.ini_options]`; si no, `pytest` avisa con
> `PytestUnknownMarkWarning` y el motivo del salto se vuelve opaco.

### 2.3 Ejecución aislada por archivo (subprocess isolation)

Cada archivo de test corre en su propio subprocess para evitar que el estado
mutable a nivel de módulo contamine archivos hermanos. Si una prueba depende de
estado compartido a propósito, márcala con `@pytest.mark.no_isolate`.

---

## 3. Pre-commit hooks

Los hooks corren **antes de cada commit** (y, opcionalmente, antes de cada push)
para que los errores baratos nunca lleguen a CI. Configuración canonical en
`.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.15.10          # mismo major.minor que ruff en [project.optional-dependencies].dev
    hooks:
      - id: ruff           # lint:  ruff check .
        args: [--fix]
      - id: ruff-format     # formato: ruff format .

  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.18.2
    hooks:
      - id: mypy
        additional_dependencies: []   # añade stubs de tus deps tipadas aquí
        args: [--strict, --ignore-missing-imports]

  - repo: https://github.com/Yelp/detect-secrets
    rev: v1.5.0
    hooks:
      - id: detect-secrets
        args: [--baseline, .secrets.baseline]
```

### 3.1 ruff — lint y formato

`ruff` hace de linter **y** formateador (reemplaza a flake8/isort/black). En
`[tool.ruff.lint]` solo está activo `PLW1514` (exige `encoding=` en `open()` /
`read_text()` / `write_text()` para evitar corrupción por locale en Windows).

```bash
#Lint con autocorrección
ruff check . --fix

#Formatea en sitio
ruff format .

#Sin tocar nada; solo reporta
ruff check .
ruff format --check .
```

> **Excepciones.** `tests/**`, `skills/**`, `optional-skills/**` y `plugins/**`
> ignoran `PLW1514` (los tests ejercitan casos de encoding a propósito; skills y
> plugins son parcialmente user-authored). No añadas reglas globales nuevas sin
> discutir el impacto en esos árboles.

### 3.2 mypy — tipado estático

```bash
#Chequeo estricto del paquete principal
mypy agent tools gateway hermes_cli --strict

#Reporte de errores sin fallar el comando (útil en CI con continue-on-error)
mypy . --strict --ignore-missing-imports
```

> **Política de deuda.** El objetivo es `--strict` en verde para los paquetes
> nucleares (`agent`, `tools`, `gateway`, `hermes_cli`). Si un subárbol aún tiene
> deuda, arrópalo con una sección `[tool.mypy-overrides]` o un `# type: ignore`
> **con comentario justificando el porqué**, nunca en silencio.

### 3.3 detect-secrets — prevención de fugas

`detect-secrets` impide commitear tokens, claves API y privados. Trabaja contra
una **baseline** (`# pragma: allowlist secret`) para los secretos legítimos que
sí deben vivir en el repo (p. ej. fixtures de test, ejemplos en docs).

```bash
#Genera la baseline inicial (solo la primera vez o al añadir secretos permitidos)
detect-secrets scan > .secrets.baseline

#Audita un archivo concreto (p. ej. tras un falso positivo)
detect-secrets scan --baseline .secrets.baseline path/al/archivo.py

#Escanea el árbol completo antes de commit
detect-secrets-hook --baseline .secrets.baseline
```

**Flujo cuando el hook bloquea un commit:**

1. Revisa el texto marcado. ¿Es un secreto real? → **no lo commites**; léelo de
   una variable de entorno o del gestor de secretos.
2. ¿Es un falso positivo o un valor de ejemplo? → añádelo a `.secrets.baseline`
   con `detect-secrets scan > .secrets.baseline` y commitea la baseline con un
   comentario que explique por qué es seguro.
3. **Nunca** evites el hook con `--no-verify` para un secreto real.

### 3.4 Ejecutar los hooks a mano

```bash
#Todos los hooks sobre todos los archivos staged
pre-commit run

#Un hook concreto
pre-commit run ruff --all-files
pre-commit run mypy --all-files
pre-commit run detect-secrets --all-files

#Sobre el árbol completo (no solo lo staged) — útil antes de un PR
pre-commit run --all-files

#Reinstala tras cambiar .pre-commit-config.yaml
pre-commit install
```

---

## 4. Cobertura

La cobertura se mide con `pytest-cov`. Reporta por consola y genera un XML
machine-readable que CI consume (p. ej. para umbrales o comentar el diff).

```bash
#Cobertura del paquete 'agent' (ajusta --cov al módulo relevante)
pytest --cov=agent --cov=tools --cov=gateway --cov-report=term-missing

#Reporte HTML navegable en htmlcov/
pytest --cov=agent --cov-report=html

#XML para CI + umbrales de fallo
pytest --cov=agent --cov-report=xml --cov-report=term \
       --cov-fail-under=80
```

| Acción                                          | Comando                                                       |
|-------------------------------------------------|---------------------------------------------------------------|
| Ver qué líneas no se cubren                     | `--cov-report=term-missing`                                  |
| Navegar el reporte en el navegador              | `pytest --cov=agent --cov-report=html` → `open htmlcov/index.html` |
| Exigir un umbral mínimo (CI)                    | `--cov-fail-under=80`                                        |
| Excluir código no medible (rama `if TYPE_CHECKING`, `_typing`)| directiva `# pragma: no cover` en la línea    |

> **Convención.** No persigas un 100 % cosmético: cubre las ramas de error reales
> y los caminos de falla. `# pragma: no cover` está permitido **con comentario**
> en ramas intrínsecamente no ejecutables (p. ej. guards de tipo). Las pruebas
> marcadas `integration` no contribuyen al total de CI normal; mídelas en el job
> de integración aparte.

---

## 5. Flujo git

### 5.1 Ramas y convención de nombres

```text
main               # siempre verde y deployable
  └─ feature/<tema>-<slug-corto>      # ej. feature/kanban-wal-repair
  └─ fix/<tema>-<slug-corto>          # ej. fix/double-free-on-reload
  └─ chore/<tema>-<slug-corto>       # ej. chore/bump-openai
```

- **Nunca** commites directamente sobre `main`. Todo cambio entra por PR.
- Sincroniza tu rama antes de abrir el PR:

```bash
git switch feature/foo
git fetch --prune
git rebase origin/main          # preferimos rebase sobre merge para mantener historial lineal
```

### 5.2 Mensajes de commit

Usa [Conventional Commits](https://www.conventionalcommits.org/):

```text
<type>(<alcance opcional>): <descripción imperativa en presente>

<cuerpo: por qué, no qué — el diff ya muestra el qué>

<footer: refs a issue, BREAKING CHANGE, co-authors>
```

Tipos: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `perf`, `ci`,
`build`, `revert`.

```text
fix(gateway): reintentar envío tras desconexión del canal

El gateway caía en un bucle de error cuando el canal se desconectaba
a mitad de un reenvío programado. Ahora se reintenta con backoff
exponencial y se notifica al usuario tras 3 intentos.

Refs: #4821
```

### 5.3 Flujo completo de un cambio

```bash
#1. Parte de main actualizado
git switch main
git pull --ff-only

#2. Crea la rama de trabajo
git switch -c feature/foo

#3. Desarrolla; haz commits atómicos y enfocados
git add -p              # stagea con criterio (hunks, no 'git add .' a ciegas)
git commit -m "feat(...): ..."

#4. Calidad local — las tres puertas que CI volverá a pasar
ruff check . --fix && ruff format .
mypy . --strict --ignore-missing-imports
pre-commit run --all-files
pytest --cov=agent --cov-report=term-missing

#5. Sube y abre el PR
git push -u origin feature/foo
gh pr create --fill --base main
```

### 5.4 Antes de push / merge

- [ ] `ruff check .` y `ruff format --check .` verdes.
- [ ] `mypy . --strict` verde (o deuda acotada y comentada).
- [ ] `detect-secrets` verde; baseline commitada si hubo allowlists.
- [ ] `pytest` verde; `--cov-fail-under` superado.
- [ ] Squash/rebase para que cada commit en `main` compile y pase tests por sí
      mismo (historial bisectable).
- [ ] El PR tiene descripción, contexto y refs a issues.

> **`--no-verify` está prohibido** salvo emergencia documentada con un
> `BREAKING`/nota en el PR. Si un hook falla, arréglalo; no lo silencies.

---

## 6. Verificar servicios antes de un deploy

Antes de promocionar a staging o producción, confirma que **los servicios de los
que depende el deploy responden**. No desploy sobre un backend caído.

### 6.1 Chequeos de salud (health checks)

```bash
#Gateway / API local
curl -fsS http://localhost:8000/healthz        # 200 + {"status":"ok"}
curl -fsS http://localhost:8000/readyz          # dependencias listas (DB, colas)

#Desde un host remoto (¡sustituye HOST y puerto!)
curl -fsS https://<HOST>/healthz
```

| Servicio          | Verificación                                     | Esperado            |
|-------------------|--------------------------------------------------|---------------------|
| API / Gateway     | `GET /healthz`                                   | `200`, `{"status":"ok"}` |
| Readiness         | `GET /readyz`                                    | `200`; dependencias listas |
| Base de datos     | conexión + `SELECT 1`                            | fila `(1,)`         |
| Broker de colas   | `redis-cli ping` / `rabbitmqctl status`          | `PONG` / ok         |
| Cache             | `redis-cli ping`                                 | `PONG`              |
| Almacén de blobs  | `mc ls`/`aws s3 ls` HEAD de bucket               | lista sin error     |
| DNS / TLS         | `curl -vI https://<HOST>`                         | `200`, cert válido  |

### 6.2 Puertos y procesos

```bash
#¿Está escuchando el puerto esperado?
ss -ltnp | grep ':8000'

#¿El proceso del servicio está vivo?
pgrep -af 'uvicorn|gunicorn|gateway' 

#Consumo de recursos antes de soltar carga
free -h && df -h / && uptime
```

### 6.3 Conectividad de dependencias externas

```bash
#Proveedores de modelo (latencia y credencial válida)
curl -sS -o /dev/null -w "%{http_code} %{time_total}s\n" \
  https://api.openai.com/v1/models \
  -H "Authorization: Bearer $OPENAI_API_KEY"

#DNS del proveedor
dig +short api.openai.com

#Salida a internet desde el host de deploy
curl -sS -o /dev/null -w "%{http_code}\n" https://1.1.1.1
```

### 6.4 Checklist de pre-deploy (no saltar)

1. **`main` está verde** en CI (ruff, mypy, detect-secrets, pytest, cobertura).
2. **Migraciones aplicadas** y verificadas (esquema idempotente, rollback planeado).
3. **Variables de entorno** cargadas desde el gestor de secretos — **nunca** del
   repo. `detect-secrets` + revisión de PR deben garantizar que ningún secreto
   vive en el código.
4. **Health checks** de todos los servicios dependientes verdes (sección 6.1).
5. **Backup/punto de restauración** de la base de datos confirmado (timestamp).
6. **Ventana de deploy** respetada (fuera de horas pico si hay riesgo).
7. **Comunicación** del cambio a las partes interesadas (changelog, canal de ops).
8. **Plan de rollback** documentado (imagen/tag anterior, comando de revierte).
9. **Smoke test post-deploy** en producción (flujo crítico end-to-end) y
   **monitorización** activa (logs/métricas) durante los primeros 15–30 min.

### 6.5 Post-deploy — verificar que quedó bien

```bash
#Health del nuevo despliegue
curl -fsS https://<HOST>/healthz && echo OK

#Trazas/logs recientes
journalctl -u <servicio> --since "5 min ago" --no-pager
# o: docker logs --since 5m <contenedor>

#Métricas clave (p. ej. tasa de error, latencia p95)
curl -s https://<HOST>/metrics | grep -E 'http_requests_(total|duration)'
```

Si algo se degrada tras el deploy: **rueda atrás primero, investiga después.**

```bash
#Rollback a la imagen/tag anterior conocida-buena
git tag -l 'v*' | tail            # identifica la última estable
# re-deploya esa versión y verifica healthz de nuevo
```

---

## 7. Matriz rápida — "¿qué corro antes de empujar?"

| Quiero…                     | Comando                                                            |
|-----------------------------|-------------------------------------------------------------------|
| Lintear y formatear         | `ruff check . --fix && ruff format .`                            |
| Tipar                       | `mypy . --strict --ignore-missing-imports`                        |
| Barrer secretos             | `detect-secrets-hook --baseline .secrets.baseline`               |
| Todos los hooks             | `pre-commit run --all-files`                                      |
| Tests rápidos (sin integr.) | `pytest`                                                          |
| Tests + integración         | `pytest -m integration`                                           |
| Cobertura con umbral        | `pytest --cov=agent --cov-report=term-missing --cov-fail-under=80` |
| Todo de una vez             | `pre-commit run --all-files && pytest --cov=agent --cov-fail-under=80` |

---

## 8. Troubleshooting

- **`pre-commit` no corre nada tras `git commit`.** Falta `pre-commit install`;
  reinstala con `pre-commit install --hook-type pre-commit`. Verifica
  `.git/hooks/pre-commit` existe y es ejecutable.
- **`mypy` reporta imports faltantes en deps de terceros.** Añade los stubs
  (`types-requests`, `pandas-stubs`, …) a `additional_dependencies` del hook
  mypy, o usa `--ignore-missing-imports` (preferible lo primero).
- **`detect-secrets` marca un falso positivo.** Regenera la baseline:
  `detect-secrets scan > .secrets.baseline`; revisa el diff; commitea la baseline
  con un comentario justificando el allowlist.
- **`ruff` y CI discrepan.** Asegúrate de tener la misma `rev` en
  `.pre-commit-config.yaml` que la versión pinneada en
  `[project.optional-dependencies].dev`. Una `rev` desalineada es la causa #1.
- **Cobertura baja sin código nuevo.** Revisa que `--cov` apunta al paquete
  correcto y que `testpaths` (en `[tool.pytest.ini_options]`) incluye los
  archivos nuevos; `pytest` no los descubre si están fuera de `testpaths`.
- **Deploy falla por `/readyz`.** Una dependencia (DB/cola/cache) no está lista.
  Resuelve la dependencia; **no** desploy con `readyz` rojo ni lo deshabilites
  para forzar el paso.

---

*Última revisión: 2026-08-24. Mantén este runbook sincronizado con
`pyproject.toml` y `.pre-commit-config.yaml` — si cambias una versión pinneada o
un marcador de pytest, actualiza también este documento.*
