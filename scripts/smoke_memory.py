#!/usr/bin/env python3
"""Smoke test: mem0 + Qdrant + Ollama embedding/LLM."""

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
            "config": {
                "model": "qwen2.5:7b",
                "ollama_base_url": "http://localhost:11434",
            },
        },
    }


t0 = time.time()
from mem0 import Memory

m = Memory.from_config(get_model_config())
print(f"[init] mem0 client ok in {time.time()-t0:.1f}s")

# search semántica real
t0 = time.time()
sr = m.search(query="arquitectura de Estación H2O", user_id="hermes-agent", limit=3)
dt = time.time() - t0
print(
    f"[search semantic] {dt:.1f}s type={type(sr).__name__} n={len(sr) if isinstance(sr, list) else '-'}"
)
if isinstance(sr, list):
    for r in sr[:3]:
        print("   ->", str(r)[:200])
print("SMOKE_OK")
