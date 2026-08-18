# Runbook: CI/CD Pipeline

**Ultima actualizacion**: 2026-08-17
**Owner**: Prometeo (autonomo)
**Critico**: No (pero bloquea merges si falla)

---

## Pipeline CI/CD

El repo usa GitHub Actions con workflow en `.github/workflows/ci.yml`.

### Trigger
- Push a cualquier rama
- Pull Request a `main` o `feat/*`

### Stages del pipeline

#### 1. Lint (ruff)
```bash
source venv/bin/activate
ruff check core/ api/ src/ skills/ scripts/ tests/
```
Falla si hay errores no auto-fixables. Auto-fixes se aplican con `ruff check --fix`.

#### 2. Type Check (mypy)
```bash
source venv/bin/activate
mypy src/ skills/ scripts/ api/
```
Gate: `python_version=3.12, strict=true` (pyproject.toml).
Actualmente: **0 errores en 89 archivos**.

#### 3. Tests (pytest)
```bash
source venv/bin/activate
python3 -m pytest tests/ -v --cov=. --cov-report=term-missing
```
Suite actual: **580 passed, 14 skipped, 0 failures**.
Coverage core/: **61%**.

### Ejecutar localmente

```bash
cd /mnt/ssd_trabajo/hermes-agent
source venv/bin/activate

# Lint
ruff check core/ api/ src/ skills/ scripts/ tests/

# Type check
mypy src/ skills/ scripts/ api/

# Tests completos
python3 -m pytest tests/ -v

# Tests con coverage
python3 -m pytest tests/ --cov=. --cov-report=term-missing

# Tests rapidos (solo unit, sin integration)
python3 -m pytest tests/unit/ -q

# Un solo archivo
python3 -m pytest tests/unit/test_bridge.py -v
```

### Pre-commit hook

El repo tiene un pre-commit hook que ejecuta ruff + mypy antes de permitir commits.
Para bypass (emergencias): `git commit --no-verify` (NO recomendado en produccion).

### Que hacer si CI falla

#### ruff falla
1. `ruff check --fix core/ api/ src/ skills/ scripts/ tests/` — auto-fix
2. `ruff check core/ api/ src/ skills/ scripts/ tests/` — verificar que quedan 0 errores
3. Commit los cambios

#### mypy falla
1. Leer el error: `archivo:linea: error: mensaje [tipo]`
2. Tipos comunes:
   - `unused-ignore`: borrar el comentario `# type: ignore`
   - `import-untyped`: agregar `# type: ignore[import-untyped]` al import
   - `union-attr`: agregar `if x is not None:` o `assert x is not None`
   - `arg-type`: ajustar tipo en firma de funcion
3. Verificar: `mypy <archivo.py>`
4. Commit

#### pytest falla
1. Leer el error: `pytest tests/unit/test_foo.py::test_bar -v`
2. Si es test nuevo del subagente: verificar que no contamine `sys.modules`
3. Si es test de integracion: verificar que SQLite tmp este configurado
4. Si es import circular: verificar que no haya imports cruzados entre api/ y core/

### Dependencias

- Python 3.12.3 (system)
- venv en `/mnt/ssd_trabajo/hermes-agent/venv/`
- Dependencias en `pyproject.toml` (`[project.dependencies]` + `[project.optional-dependencies].dev`)
