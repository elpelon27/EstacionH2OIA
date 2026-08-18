#!/usr/bin/env python3
"""Calibration: time one mem0.add() chunk on a real doc."""

import sys
import time


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


from mem0 import Memory  # type: ignore[import-untyped]

m = Memory.from_config(get_model_config())

path = sys.argv[1]
text = open(path, encoding="utf-8").read()
chunk = text[:2500]  # ~ fragmento inicial
t0 = time.time()
res = m.add(
    messages=[{"role": "user", "content": chunk}],
    user_id="obsidian_docs",
    metadata={"source": path, "kind": "docs"},
)
dt = time.time() - t0
print(f"[add one chunk {len(chunk)} chars] {dt:.1f}s")
print("result:", str(res)[:300])
