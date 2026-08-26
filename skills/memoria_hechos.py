#!/usr/bin/env python3
"""
Memoria de hechos — grafo persistente de hechos pasados (Prometeo).

Orquesta la infraestructura de memoria tripartita existente (SOUL §6):
  - Qdrant `hermes_memory` (L3 semántica)  : recuperación vectorial
  - state.db  (L1 persistente de sesión)   : contador de sesiones/mensajes
  - Redis     (L2 caché)                   : estado de capa
  - vault Obsidian docs/                   : documento-hechos versionable (fuente de verdad)

No es un reemplazo de nada: reutiliza qdrant_client/mem0/ollama ya instalados.

Uso (desde /mnt/ssd_trabajo/hermes-agent):
  ./venv/bin/python3 skills/memoria_hechos.py --status
  ./venv/bin/python3 skills/memoria_hechos.py --recall "deuda técnica del proyecto"
  ./venv/bin/python3 skills/memoria_hechos.py --add "Tema" "Hecho..." \
      --conf certain|inferred|tentative

Realidad de datos (verificada, no asumida): SQLite síncrono, Embeddings nomic vía Ollama
:11434, Qdrant :6333 colección hermes_memory (768d).
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from qdrant_client import QdrantClient

# ─────────────────────────── rutas (no hardcodear en el cliente) ───────────
REPO = Path("/mnt/ssd_trabajo/hermes-agent")
VENV_PY = REPO / "venv" / "bin" / "python3"
QDRANT_URL = "http://localhost:6333"
OLLAMA_URL = "http://localhost:11434"
STATE_DB = Path("/home/skynet/hermes-unified/state.db")
HECHOS_FILE = REPO / "docs" / "memoria" / "hechos.json"  # grafo de hechos versionable
EMBED_MODEL = "nomic-embed-text:latest"
COLLECTION = "hermes_memory"
CONFIANZA = {"certain", "inferred", "tentative"}


# ─────────────────────────── persistencia de hechos ────────────────────────
def _load_hechos() -> list[dict[str, Any]]:
    """Carga el grafo de hechos desde el JSON del vault. Crea vacío si no existe."""
    if not HECHOS_FILE.exists():
        return []
    try:
        data = json.loads(HECHOS_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def _save_hechos(hechos: list[dict[str, Any]]) -> None:
    HECHOS_FILE.parent.mkdir(parents=True, exist_ok=True)
    HECHOS_FILE.write_text(
        json.dumps(hechos, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def cmd_add(tema: str, texto: str, conf: str) -> int:
    """Registra un hecho atómico nuevo en el grafo versionable."""
    if conf not in CONFIANZA:
        print(f"confianza inválida '{conf}'; usa {sorted(CONFIANZA)}")
        return 2
    if not tema.strip() or not texto.strip():
        print("tema y texto son obligatorios")
        return 2
    hechos = _load_hechos()
    hechos.append(
        {
            "id": len(hechos) + 1,
            "tema": tema.strip(),
            "hecho": texto.strip(),
            "confianza": conf,
            "fecha": datetime.now(UTC).strftime("%Y-%m-%d"),
        }
    )
    _save_hechos(hechos)
    print(f"+ hecho #{hechos[-1]['id']} [{conf}] {tema.strip()}: {texto.strip()}")
    return 0


# ─────────────────────────── capas tripartitas ─────────────────────────────
def _qdrant() -> QdrantClient:
    from qdrant_client import QdrantClient  # import tardío (solo si se usa)

    return QdrantClient(QDRANT_URL)


def _embed(text: str) -> list[float]:
    import json as _j
    import urllib.request

    req = urllib.request.Request(
        OLLAMA_URL + "/api/embeddings",
        data=_j.dumps({"model": EMBED_MODEL, "prompt": text}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        vec = _j.loads(r.read()).get("embedding", [])
        return [float(v) for v in vec]  # coerce para mypy (no-any-return)


def _redis_dbsize() -> str:
    r = subprocess.run(["redis-cli", "dbsize"], capture_output=True, text=True)
    return r.stdout.strip() or "n/a"


def _state_db() -> tuple[int, int]:
    con = sqlite3.connect(str(STATE_DB))
    try:
        n_s = con.execute("select count(*) from sessions").fetchone()[0]
        n_m = con.execute("select count(*) from messages").fetchone()[0]
    except sqlite3.Error:
        n_s = n_m = -1
    finally:
        con.close()
    return n_s, n_m


def cmd_status() -> int:
    """Estado del grafo de memoria tripartita + hechos versionables."""
    print("═" * 58)
    print(" GRAFO DE MEMORIA — estado")
    print("═" * 58)
    # L3 Qdrant
    q = _qdrant()
    info = q.get_collection(COLLECTION)
    puntos = info.points_count
    res = q.scroll(collection_name=COLLECTION, limit=500, with_payload=["source"])[0]
    fuentes = {
        p.payload.get("source")
        for p in res
        if p.payload is not None and p.payload.get("source")
    }
    print(f"L3 Qdrant [{COLLECTION}]: {puntos} pts, {len(fuentes)} archivos indexados")
    # L1 + L2
    n_s, n_m = _state_db()
    print(f"L1 state.db: {n_s} sesiones, {n_m} mensajes")
    print(f"L2 Redis dbsize: {_redis_dbsize()}")
    # grafo versionable
    hechos = _load_hechos()
    print(f"grafo hechos (docs/memoria/hechos.json): {len(hechos)} hechos")
    for h in hechos[-3:]:
        print(f"   #{h['id']} [{h['confianza']}] {h['tema']}: {h['hecho'][:70]}")
    print("═" * 58)
    ok = puntos is not None and puntos > 0 and n_s >= 0
    print("Verificación: OK" if ok else "Verificación: revisar capas")
    return 0


# ─────────────────────────── recuperación semántica ────────────────────────
def cmd_recall(query: str, limit: int = 4) -> int:
    """Búsqueda vectorial de hechos en Qdrant + top del grafo JSON coincidente."""
    vec = _embed(query)
    q = _qdrant()
    hits = q.query_points(
        collection_name=COLLECTION, query=vec, limit=limit, with_payload=True
    ).points
    print(f"RECALL: {query!r}\n")
    for h in hits:
        pl = h.payload or {}
        src = pl.get("source", "?")
        title = pl.get("title", "")
        # Robustez: algunos payloads guardan text/chunk como int (TypeError al rebanar).
        _raw = pl.get("text") or pl.get("chunk") or ""
        snippet = str(_raw)[:160]
        print(f"  [{h.score:.3f}] {title or src}")
        if title and title != src:
            print(f"        src={src}")
        if snippet:
            print(f"        {snippet}")
    # hechos versionables (empareje por tema, barato y determinista)
    import re as _re

    def _split_tokens(s: str) -> set[str]:
        # Descompone espacios, guiones y guiones bajos: 'sesion-2026-08-16' -> {sesion,2026}
        return {t for t in _re.split(r"[\s_-]+", s.lower()) if len(t) > 3}

    hechos = _load_hechos()
    tokens = _split_tokens(query)
    matches = [h for h in hechos if tokens.intersection(_split_tokens(h["tema"]))]
    if matches:
        print("\n  Grafo versionable (coincidencia por tema):")
        for hh in matches[-3:]:
            print(f"    #{hh['id']} [{hh['confianza']}] {hh['tema']}: {hh['hecho'][:100]}")
    return 0


# ─────────────────────────── CLI ───────────────────────────────────────────
def main() -> int:
    p = argparse.ArgumentParser(description="Memoria de hechos (Prometeo)")
    p.add_argument("--status", action="store_true", help="estado del grafo")
    p.add_argument("--recall", metavar="QUERY", help="búsqueda semántica")
    p.add_argument("--add", nargs=2, metavar=("TEMA", "TEXTO"), help="registrar hecho")
    p.add_argument(
        "--conf",
        default="inferred",
        choices=sorted(CONFIANZA),
        help="confianza del hecho (default: inferred)",
    )
    p.add_argument("--limit", type=int, default=4, help="resultados de recall")
    a = p.parse_args()

    if a.status:
        return cmd_status()
    if a.recall:
        return cmd_recall(a.recall, a.limit)
    if a.add:
        return cmd_add(a.add[0], a.add[1], a.conf)
    p.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
