#!/usr/bin/env python3
"""
============================================================================
skill_generator — agente que convierte análisis de video en skills
============================================================================
Lee el JSON de output de claude-watch (docs/videos/<video-id>.json),
evalúa el campo "skill_proposal" y decide según criterios del Líder:

  - tutorial técnico        → SÍ genera skill
  - charla/conferencia      → NO (solo indexado en Qdrant)
  - documental              → NO (solo indexado)
  - entrenamiento            → SÍ genera skill
  - >3 procedimientos step-by-step → SÍ
  - default                  → NO

REGLA DEL LÍDER (fase inicial): NUNCA crea skills automáticamente.
Siempre corre en modo dry-run: muestra qué haría y el Líder confirma.
Solo con --confirm (aprobación explícita) escribe archivos y commitea.

Fase 3 (futura): el comando "sombrero" cargará la firma del skill.
============================================================================
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO = Path("/mnt/ssd_trabajo/hermes-agent")
sys.path.insert(0, str(REPO))

# Mapping tema → firma (para comando "sombrero", FASE 3)
FIRMAS: dict[str, str] = {
    "agropecuario": "🐄",
    "h2o": "💧",
    "trading": "📈",
}
FIRMA_DEFAULT = "🔧"  # técnico default

# Formatos de video → genera skill
FORMATOS_SI = {"tutorial", "tutorial técnico", "entrenamiento", "training"}
FORMATOS_NO = {"charla", "conferencia", "documental", "talk", "podcast"}
MIN_PROCEDIMIENTOS = 3

COMMIT_MSG = "feat: skill generado desde video ({video_id})"


def firma_para(tema: str) -> str:
    return FIRMAS.get((tema or "").lower().strip(), FIRMA_DEFAULT)


def _norm(s: str) -> str:
    return (s or "").lower().strip()


def decidir_skill(data: dict[str, Any]) -> tuple[bool, list[str]]:
    """Aplica los criterios del Líder. Devuelve (genera, razones)."""
    an: dict[str, Any] = data.get("analysis", {}) or {}
    razones: list[str] = []

    propuesta = an.get("skill_proposal")
    if not propuesta or propuesta == "null":
        razones.append("skill_proposal ausente o null → no apto")
        return False, razones

    formato = _norm(an.get("formato") or an.get("video_type") or "")
    if any(formato.startswith(f) for f in FORMATOS_SI):
        razones.append(f"formato '{formato}' → SÍ genera skill")
        return True, razones
    if any(formato.startswith(f) for f in FORMATOS_NO):
        razones.append(f"formato '{formato}' → NO (solo indexado en Qdrant)")
        return False, razones

    procedimientos = an.get("procedimientos") or an.get("step_by_step") or []
    n = len(procedimientos) if isinstance(procedimientos, list) else 0
    if n > MIN_PROCEDIMIENTOS:
        razones.append(f"{n} procedimientos step-by-step (>3) → SÍ genera skill")
        return True, razones

    # Heurística de respaldo: contenido en key_facts/tldr sugiere procedimiento
    texto = " ".join(an.get("tldr", []) + an.get("key_facts", [])).lower()
    markers = ("paso", "step", "primero", "luego", "finalmente", "instalá",
               "configurá", "ejecutá")
    hits = sum(1 for m in markers if m in texto)
    if hits >= 3:
        razones.append(f"lenguaje procedural detectado ({hits} marcadores) → SÍ")
        return True, razones

    razones.append("default → NO (solo indexado en Qdrant)")
    return False, razones


def construir_skill_md(data: dict[str, Any], tema: str, topic: str) -> str:
    an: dict[str, Any] = data.get("analysis", {}) or {}
    firma = firma_para(tema)
    hoy = datetime.now(UTC).date().isoformat()
    desc = an.get("descripcion") or an.get("tldr") or []
    if isinstance(desc, list):
        desc = "\n".join(f"- {d}" for d in desc) or "(sin descripción)"
    casos = an.get("casos_de_uso") or an.get("use_cases") or []
    if isinstance(casos, list):
        casos = "\n".join(f"- {c}" for c in casos) or "- Consultar knowledge base del video"
    return f"""# Skill: {topic}

Generado a partir de video: {data.get('url', '?')}
Fecha: {hoy}
Firma del skill: {firma} ({tema})

## Descripción
{desc}

## Cuándo invocarlo
{casos}

## Knowledge base
- Colección Qdrant: videos_h2o
- Filtro: tema={tema}

## Invocación
```python
from scripts.llm_client import LLMClient
llm = LLMClient()
# Consultar Qdrant filtrando por tema
# Pasar contexto al LLM
```
"""


def main() -> int:
    ap = argparse.ArgumentParser(
        prog="skill_generator",
        description="Evalúa el JSON de claude-watch y (con confirmación) "
                    "genera skills/from-video-<topic>/SKILL.md")
    ap.add_argument("--json", required=True,
                    help="Ruta al JSON de video (docs/videos/<id>.json)")
    ap.add_argument("--dry-run", action="store_true", default=True,
                    help="Mostrar qué haría sin hacerlo (default: Líder "
                         "revisa primero)")
    ap.add_argument("--confirm", action="store_true",
                    help="Confirmación del Líder: crea el skill y commitea")
    ap.add_argument("--skills-dir", default="skills")
    args = ap.parse_args()

    jpath = Path(args.json)
    if not jpath.is_absolute():
        jpath = (REPO / jpath).resolve()
    if not jpath.exists():
        print(f"ERROR: no existe {jpath}", file=sys.stderr)
        return 2

    data = json.loads(jpath.read_text(encoding="utf-8"))
    tema = data.get("tema", "otro")
    an = data.get("analysis", {}) or {}
    topic = an.get("skill_proposal") or ""

    genera, razones = decidir_skill(data)

    print(f"JSON: {jpath.name}")
    print(f"Tema: {tema} | Firma: {firma_para(tema)}")
    print(f"skill_proposal: {topic or '(null)'}")
    for r in razones:
        print(f"  • {r}")

    if not genera:
        print("RESULTADO: no apto para skill, solo indexado en Qdrant")
        return 0

    skill_dir = REPO / args.skills_dir / f"from-video-{topic}"
    skill_md = skill_dir / "SKILL.md"

    if not args.confirm:
        print("\n--- DRY-RUN (fase inicial: el Líder confirma primero) ---")
        print(f"Crearía: {skill_md.relative_to(REPO)}")
        print("\n" + "=" * 60)
        print(construir_skill_md(data, tema, topic))
        print("=" * 60)
        print("Commit: " + COMMIT_MSG.format(video_id=data.get("video_id", "?")))
        print("Para crear de verdad: python scripts/skill_generator.py "
              f"--json {jpath} --confirm")
        return 0

    # Modo confirmado: crear + commit separado
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_md.write_text(construir_skill_md(data, tema, topic),
                        encoding="utf-8")
    print(f"OK: creado {skill_md.relative_to(REPO)}")
    add = subprocess.run(
        ["git", "add", str(skill_md.relative_to(REPO))],
        cwd=REPO, capture_output=True, text=True)
    if add.returncode != 0:
        print(f"git add falló: {add.stderr}", file=sys.stderr)
        return 1
    commit = subprocess.run(
        ["git", "commit", "--no-verify", "-m",
         COMMIT_MSG.format(video_id=data.get("video_id", "?"))],
        cwd=REPO, capture_output=True, text=True)
    if commit.returncode != 0:
        print(f"git commit falló: {commit.stderr}", file=sys.stderr)
        return 1
    print("Commit: " + (commit.stdout.strip().splitlines()[0]
                       if commit.stdout else "ok"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
