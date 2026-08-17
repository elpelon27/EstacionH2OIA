#!/usr/bin/env python3
"""IdxObsidian: indexa los 78 .md reales de docs/ en mem0 (Qdrant vector store).

- Lee la lista canónica de /tmp/doclist.txt (78 archivos, sin seguir symlinks).
- Por archivo: si supera ~14000 chars, trocea en bloques (~12000) por límite de línea.
- m.add(messages=..., user_id="obsidian_docs", metadata={source,title}).
- Persiste progreso en scripts/.idx_progress.json (continuable): archivos=lista {rel, source}
  ya completados se saltan.
"""

import json
import time
from pathlib import Path

ROOT = Path("/mnt/ssd_trabajo/hermes-agent")
PROGRESS = ROOT / "scripts" / ".idx_progress.json"
USER_ID = "obsidian_docs"
MAX_CHUNK = 12000
SPLIT_THRESHOLD = 14000


def get_model_config() -> dict[str, object]:
    return {
        "vector_store": {
            "provider": "qdrant",
            "config": {
                "url": "http://localhost:6333",
                "api_key": None,
                "collection_name": "hermes_memory",
            },
        },
        "embedder": {
            "provider": "ollama",
            "config": {
                "model": "nomic-embed-text:latest",
                "ollama_base_url": "http://localhost:11434",
            },
        },
        "llm": {
            "provider": "ollama",
            "config": {"model": "qwen2.5:7b", "ollama_base_url": "http://localhost:11434"},
        },
    }


def load_progress() -> dict[str, list[dict[str, object]]]:
    if PROGRESS.exists():
        return json.loads(PROGRESS.read_text())  # type: ignore[no-any-return]
    return {"done": []}


def save_progress(p: dict[str, list[dict[str, object]]]) -> None:
    PROGRESS.write_text(json.dumps(p, ensure_ascii=False, indent=1))
    # limpiar si supera tamaño razonable
    if PROGRESS.stat().st_size > 400_000:
        PROGRESS.write_text(json.dumps({"done": p["done"]}, ensure_ascii=False))


def chunk_text(text: str) -> list[str]:
    if len(text) <= SPLIT_THRESHOLD:
        return [text]
    # trocear en ~MAX_CHUNK chars respetando líneas
    chunks, cur = [], ""
    for line in text.split("\n"):
        if len(cur) + len(line) + 1 > MAX_CHUNK and cur:
            chunks.append(cur)
            cur = ""
        cur += line + "\n"
        if len(cur) > MAX_CHUNK:  # línea gigante: cortar duro
            chunks.append(cur)
            cur = ""
    if cur.strip():
        chunks.append(cur)
    return [c for c in chunks if c.strip()]


def main() -> None:
    from mem0 import Memory

    m = Memory.from_config(get_model_config())
    files = sorted(set(l.strip() for l in open("/tmp/doclist.txt") if l.strip()))
    progress = load_progress()
    done_sources = {d["source"] for d in progress["done"]}
    print(f"TOTAL archivos: {len(files)} | ya_completados: {len(done_sources)}", flush=True)
    t0 = time.time()
    ok = fail = 0
    for rel in files:
        if rel in done_sources:
            print(f"  [skip] {rel}", flush=True)
            continue
        try:
            text = Path(rel).read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            print(f"  [read-err] {rel}: {e}", flush=True)
            fail += 1
            continue
        chunks = chunk_text(text)
        title = Path(rel).stem
        for ci, ch in enumerate(chunks):
            try:
                res = m.add(
                    messages=[{"role": "user", "content": ch}],
                    user_id=USER_ID,
                    metadata={"source": rel, "title": title, "chunk": ci, "kind": "obsidian"},
                )
                n_mem = len(res.get("results", [])) if isinstance(res, dict) else 0
                print(
                    f"  [add] {rel} chunk {ci+1}/{len(chunks)} "
                    f"(memorias_extraidas={n_mem}) {time.time()-t0:.0f}s",
                    flush=True,
                )
            except Exception as e:
                print(f"  [add-err] {rel} chunk {ci}: {e}", flush=True)
                fail += 1
                time.sleep(2)
        progress["done"].append(
            {"source": rel, "title": title, "chunks": len(chunks), "ts": time.time()}
        )
        save_progress(progress)
        ok += 1
    dt = time.time() - t0
    print(
        f"DONE ok={ok} fail={fail} time={dt:.0f}s " f"total_completados={len(progress['done'])}",
        flush=True,
    )


if __name__ == "__main__":
    main()
