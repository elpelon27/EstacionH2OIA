#!/usr/bin/env python3
"""Verifica búsqueda semántica devolviendo resultados con payload/source legible."""

import time


def cfg() -> dict[str, object]:
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


from mem0 import Memory

m = Memory.from_config(cfg())
for q in [
    "catálogo de agentes hermes",
    "arquitectura odoo estación h2o",
    "deuda técnica pendiente",
]:
    t0 = time.time()
    res = m.search(query=q, user_id="obsidian_docs", limit=5)
    print(f"\n=== QUERY: {q} ({time.time()-t0:.1f}s) ===")
    results = res.get("results", []) if isinstance(res, dict) else res
    if not results:
        print("  (sin resultados en user_id=obsidian_docs)")
    for r in results[:5]:
        md = r.get("metadata", {})
        print("  -", (r.get("memory") or "")[:90].replace("\n", " "))
        print("      src:", md.get("source"), "| score:", round(r.get("score", 0), 3))
